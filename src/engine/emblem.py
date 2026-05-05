"""Emblems (CR 113.1c).

Emblems are persistent global effects with no characteristics other than
``Emblem``. They sit conceptually in the command zone, never leave play, are
not destroyed by any effect, and have no stats / mana cost / abilities of
their own beyond the ones printed on them. The most common producers are
planeswalker ultimates ("you get an emblem with...").

The implementation tracks emblems on ``GameState.emblems`` (a list of
:class:`Emblem`) and registers their static interceptors on
``GameState.interceptors`` with ``duration='forever'`` so they persist across
turns and survive the source planeswalker's destruction.

Public API:

- :func:`create_emblem` — instantiate an Emblem and wire its interceptors.
- :class:`Emblem` — the lightweight pseudo-permanent record.

The :func:`make_emblem_setup` helper in :mod:`src.cards.interceptor_helpers`
wraps :func:`create_emblem` for use from a planeswalker's ultimate ``effect_fn``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .types import (
    Event,
    EventType,
    GameState,
    Interceptor,
    new_id,
)

EmblemStaticEffectsFn = Callable[["Emblem", GameState], list[Interceptor]]


@dataclass
class Emblem:
    """A pseudo-permanent that lives forever in the command zone.

    Attributes:
        id: Stable identifier (used as the source for the emblem's
            interceptors).
        controller: Player id that controls / owns the emblem.
        source_card_name: Name of the card whose ultimate created this
            emblem (e.g. ``"Ral, Crackling Wit"``). Informational; tests use
            it to look the emblem up.
        name: Display name for the emblem (defaults to
            ``"<source_card_name> Emblem"``).
        text: Reminder/oracle text describing the emblem's effect.
        interceptor_ids: ids of the interceptors registered on
            ``GameState.interceptors`` for this emblem's static effect(s).
    """
    id: str
    controller: str
    source_card_name: str
    name: str = ""
    text: str = ""
    interceptor_ids: list[str] = field(default_factory=list)


def create_emblem(
    state: GameState,
    *,
    controller: str,
    source_id: Optional[str],
    source_card_name: str,
    static_effects_fn: EmblemStaticEffectsFn,
    name: str = "",
    text: str = "",
) -> tuple[Emblem, list[Event]]:
    """Create an emblem and register its static effects.

    Args:
        state: the GameState to mutate.
        controller: player who controls the emblem.
        source_id: id of the source object that created the emblem (the
            planeswalker). Used as the ``source`` on the EMBLEM_CREATED event;
            the emblem itself uses its own id as its interceptor source so
            sweeps tied to the planeswalker leaving play don't tear down
            the emblem.
        source_card_name: display name of the source card.
        static_effects_fn: ``(emblem, state) -> list[Interceptor]``. Called
            once at creation time to build the persistent interceptors.
        name: optional explicit name (defaults to ``"<source_card_name> Emblem"``).
        text: oracle-style description string.

    Returns:
        ``(emblem, events)`` — the new Emblem and a one-element list with
        an EMBLEM_CREATED marker event ready to be emitted/returned.

    The Emblem and its interceptors are mutated into ``state.emblems`` and
    ``state.interceptors`` directly so the caller can simply hand the
    returned events back to the pipeline (or ignore them in tests).
    """
    emblem_id = new_id()
    display_name = name or f"{source_card_name} Emblem"
    emblem = Emblem(
        id=emblem_id,
        controller=controller,
        source_card_name=source_card_name,
        name=display_name,
        text=text,
    )

    # Lazily ensure GameState has the emblems list (older state objects
    # constructed before W15 may not have the attribute yet).
    if not hasattr(state, "emblems"):
        state.emblems = []  # type: ignore[attr-defined]
    state.emblems.append(emblem)  # type: ignore[attr-defined]

    # Build & register the interceptors. Each interceptor's ``source`` is
    # the emblem id (not the PW id) and its ``duration`` is forced to
    # ``"forever"`` so neither the planeswalker leaving play nor end-of-turn
    # cleanup will sweep it.
    interceptors: list[Interceptor] = []
    try:
        interceptors = static_effects_fn(emblem, state) or []
    except Exception:
        interceptors = []

    for interceptor in interceptors:
        # Ensure the interceptor is properly tagged. Cards may forget to set
        # source/controller; default them to the emblem.
        if not getattr(interceptor, "source", None):
            interceptor.source = emblem_id
        if not getattr(interceptor, "controller", None):
            interceptor.controller = controller
        # Force forever so cleanup_departed_interceptors / EOT sweeps skip it.
        interceptor.duration = "forever"
        # Stamp a fresh timestamp so layer ordering reflects creation time.
        try:
            interceptor.timestamp = state.next_timestamp()
        except Exception:
            interceptor.timestamp = 0

        state.interceptors[interceptor.id] = interceptor
        emblem.interceptor_ids.append(interceptor.id)

    event = Event(
        type=EventType.EMBLEM_CREATED,
        payload={
            "emblem_id": emblem_id,
            "controller": controller,
            "source_card": source_card_name,
            "name": display_name,
            "text": text,
        },
        source=source_id or emblem_id,
        controller=controller,
    )
    return emblem, [event]


def get_emblems(state: GameState) -> list[Emblem]:
    """Return the list of active emblems on the given state (defensive)."""
    return list(getattr(state, "emblems", []) or [])


def get_emblems_for_player(state: GameState, player_id: str) -> list[Emblem]:
    """Emblems controlled by a specific player."""
    return [e for e in get_emblems(state) if e.controller == player_id]


__all__ = [
    "Emblem",
    "create_emblem",
    "get_emblems",
    "get_emblems_for_player",
]
