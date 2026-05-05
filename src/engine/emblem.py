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
    CardType,
    Event,
    EventType,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    PendingChoice,
    ZoneType,
    new_id,
)

EmblemStaticEffectsFn = Callable[["Emblem", GameState], list[Interceptor]]
EmblemEventFilter = Callable[[Event, GameState, "Emblem"], bool]


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


# ---------------------------------------------------------------------------
# Triggered-ability emblem helpers (W22 + W15)
# ---------------------------------------------------------------------------


def _default_any_target(emblem: "Emblem", state: GameState) -> Optional[str]:
    """Pick a sensible default "any target" for emblems that fire in
    auto-resolve mode (tests, AI fallback when no priority window is open).

    Strategy (in order):
      1. The first opponent (player id) found in turn order.
      2. The first creature/planeswalker controlled by an opponent on the
         battlefield (in case the future engine prefers permanent targets).
      3. ``None`` (caller should fizzle quietly).
    """
    controller = emblem.controller
    # Prefer the active opponent in player order.
    for pid in state.players:
        if pid != controller:
            return pid
    # Fall back to any opposing battlefield permanent.
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller == controller:
            continue
        types = obj.characteristics.types
        if CardType.CREATURE in types or CardType.PLANESWALKER in types:
            return obj.id
    return None


def make_emblem_damage_target_react(
    emblem: "Emblem",
    *,
    event_filter: EmblemEventFilter,
    amount: int,
    description: str = "",
    default_target_fn: Optional[Callable[["Emblem", GameState], Optional[str]]] = None,
) -> Interceptor:
    """Build a triggered-ability interceptor for an emblem that deals ``amount``
    damage to "any target" whenever the underlying ``event_filter`` matches.

    This is the canonical pattern for emblems like Ral, Crackling Wit's
    ult ("Whenever you cast an instant or sorcery spell, this emblem deals
    4 damage to any target.") under the W22 triggered-ability framework:

    * The returned interceptor is marked ``is_triggered_ability=True``, so the
      pipeline enqueues a :class:`TriggeredStackItem` rather than firing
      ``handler`` inline (CR 603.2 / 603.3).
    * On stack resolution the trigger's ``effect_fn`` runs and either:

      - **Auto-resolve mode** (``state.options.auto_resolve_triggers=True``,
        the default for tests): selects a default target via
        ``default_target_fn`` (or :func:`_default_any_target`) and emits a
        plain :class:`Event` of type :data:`EventType.DAMAGE`. This keeps
        existing tests deterministic while we wire real targeting.
      - **Interactive mode**: emits a :data:`EventType.TARGET_REQUIRED`
        event so the targeting handler opens a ``PendingChoice`` of
        ``target_filter='any'`` (creatures / planeswalkers / players) for
        the emblem's controller. When the player submits, the targeting
        handler synthesises the corresponding ``DAMAGE`` event.

    Args:
        emblem: the :class:`Emblem` that owns this trigger.
        event_filter: ``(event, state, emblem) -> bool`` — return True when
            the trigger should fire (e.g. "instant or sorcery cast by
            ``emblem.controller``").
        amount: damage amount.
        description: optional description used by the
            :class:`TriggeredStackItem` for logging / UI.
        default_target_fn: optional override for auto-resolve mode's
            default target picker. Defaults to :func:`_default_any_target`.

    Returns:
        a fully wired :class:`Interceptor` ready to be returned from a
        ``static_effects_fn``.
    """
    pick_default = default_target_fn or _default_any_target

    def _filter(event: Event, state: GameState) -> bool:
        try:
            return bool(event_filter(event, state, emblem))
        except Exception:
            return False

    def _enumerate_any_targets(state: GameState) -> list[str]:
        """Build the option list for "any target": creatures + planeswalkers
        on the battlefield, plus every player in the game.

        Note: the standard ``TARGET_REQUIRED`` handler can't be reused here
        because it expects ``state.objects[source_id]`` to resolve — and
        emblems live on ``state.emblems``, not ``state.objects``. We
        therefore enumerate legal targets directly and open the choice
        ourselves.
        """
        options: list[str] = []
        for obj in state.objects.values():
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            types = obj.characteristics.types
            if CardType.CREATURE in types or CardType.PLANESWALKER in types:
                options.append(obj.id)
        for pid in state.players:
            if pid not in options:
                options.append(pid)
        return options

    def _resolve_effect(event: Event, state: GameState) -> list[Event]:
        """Trigger resolution body (called by W22's stack/auto-drain path)."""
        # Decide: auto-resolve (pick default target) vs interactive (open
        # a PendingChoice for the controller).
        opts = getattr(state, "options", None)
        auto = bool(getattr(opts, "auto_resolve_triggers", True)) if opts is not None else True

        if auto:
            target = pick_default(emblem, state)
            if target is None:
                return []
            return [Event(
                type=EventType.DAMAGE,
                payload={
                    'target': target,
                    'amount': int(amount),
                    'source': emblem.id,
                    'is_combat': False,
                },
                source=emblem.id,
                controller=emblem.controller,
            )]

        # Interactive: build a target_with_callback PendingChoice for "any
        # target". When the player submits, the callback emits the DAMAGE
        # event with the chosen target. Submission events flow back to
        # callers via ``Game.submit_choice``.
        legal = _enumerate_any_targets(state)
        if not legal:
            # No legal targets — trigger fizzles (CR 608.2b).
            return []

        def _on_target_chosen(choice: PendingChoice, selected: list, state2: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            if isinstance(target_id, dict):
                target_id = target_id.get('id') or target_id.get('value') or target_id.get('target')
            if target_id is None:
                return []
            return [Event(
                type=EventType.DAMAGE,
                payload={
                    'target': target_id,
                    'amount': int(amount),
                    'source': emblem.id,
                    'is_combat': False,
                },
                source=emblem.id,
                controller=emblem.controller,
            )]

        choice = PendingChoice(
            choice_type="target_with_callback",
            player=emblem.controller,
            prompt=description or f'Deal {int(amount)} damage to any target',
            options=legal,
            source_id=emblem.id,
            min_choices=1,
            max_choices=1,
            callback_data={'handler': _on_target_chosen},
        )
        state.pending_choice = choice
        # The DAMAGE event will be emitted by the choice callback.
        return []

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        # Defensive fallback path: the pipeline only calls ``handler`` for
        # plain REACT interceptors. With ``is_triggered_ability=True`` the
        # pipeline reads ``effect_fn`` instead — but if a future caller
        # accidentally drops the marker we still fire correctly.
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_resolve_effect(event, state),
        )

    interceptor = Interceptor(
        id=new_id(),
        source=emblem.id,
        controller=emblem.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration='forever',
    )
    # W22 hooks: the pipeline consults these when ``is_triggered_ability``
    # is set, queueing a TriggeredStackItem rather than firing inline.
    interceptor.is_triggered_ability = True
    interceptor.effect_fn = _resolve_effect
    interceptor.description = description or f'Emblem deals {int(amount)} damage to any target'
    return interceptor


__all__ = [
    "Emblem",
    "create_emblem",
    "get_emblems",
    "get_emblems_for_player",
    "make_emblem_damage_target_react",
]
