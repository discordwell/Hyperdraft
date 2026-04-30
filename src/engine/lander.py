"""
EOE Lander mechanic — token construction, sacrifice tracking, search resolution.

A **Lander token** is a colorless artifact with subtype ``Lander`` and the activated
ability:

    "{2}, {T}, Sacrifice this token: Search your library for a basic land card,
     put it onto the battlefield tapped, then shuffle."

Cards in Edge of Eternities create Lander tokens (often as a graveyard/ETB
trigger), and a small number of cards reference *whether* you have sacrificed
one this turn. The system here provides the building blocks:

  * :func:`make_lander_token_event` — canonical OBJECT_CREATED Event for a
    Lander token. Card files should call this instead of constructing the
    payload by hand so the token name/typeline/colors stay consistent.
  * :func:`is_lander` — predicate; checks both subtype and (legacy) name.
  * :func:`landers_sacced_this_turn` — public read accessor for the per-turn
    counter (``state.turn_data['landers_sacced_<player>']``).
  * :func:`mark_lander_sacrificed` — public write accessor, used by both the
    system interceptor below and any direct-resolution path.
  * :func:`register_lander_tracker` — wires the system interceptors into
    ``Game._setup_system_interceptors``.

Library-search dependency
-------------------------
The full "{2}, {T}, Sacrifice: search library for a basic land, put it onto
the battlefield tapped, then shuffle" activated ability requires the
``library_search`` subsystem (a separate parallel agent). Until that lands,
:func:`make_lander_search_event` emits a ``LANDER_SEARCH_LAND`` event that:

  * If a registered ``library_search`` resolver is available
    (``state.turn_data['_library_search_resolver']``), delegates to it.
  * Otherwise, falls back to a best-effort stub that scans the controller's
    library for the first basic land (``CardType.LAND`` + a basic subtype),
    moves it onto the battlefield tapped, and shuffles. Cards that do not need
    the search resolved (e.g. they only care that a Lander was sacrificed)
    keep working unchanged.

The stub is a placeholder; once the library_search subsystem ships, replace
the body of :func:`_resolve_lander_search` with a delegated call.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional

from .types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)

if TYPE_CHECKING:
    from .game import Game


# =============================================================================
# Constants
# =============================================================================

LANDER_TOKEN_NAME = "Lander Token"
LANDER_SUBTYPE = "Lander"

# The five MTG basic land subtypes (excluding Wastes which is colorless and
# doesn't appear on a basic land card with a basic subtype).
BASIC_LAND_SUBTYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})


# =============================================================================
# Token construction
# =============================================================================

def make_lander_token_event(controller: str, source_obj_id: Optional[str] = None) -> Event:
    """Build the canonical OBJECT_CREATED Event for a single Lander token.

    Card files should prefer this over building the payload inline.

    Args:
        controller: Player ID who controls (and owns) the new Lander token.
        source_obj_id: Object ID that caused the creation (for trigger source
            tracking). Optional.

    Returns:
        An OBJECT_CREATED Event that, when resolved, produces a colorless
        artifact token with the ``Lander`` subtype on the battlefield. Note
        that Hyperdraft does not yet implement the activated ability text on
        the token itself; the activated ability is resolved via
        :func:`make_lander_search_event` (typically called by AI/UI when the
        token is activated).
    """
    return Event(
        type=EventType.OBJECT_CREATED,
        payload={
            "name": LANDER_TOKEN_NAME,
            "controller": controller,
            "owner": controller,
            "types": [CardType.ARTIFACT],
            "subtypes": [LANDER_SUBTYPE],
            "colors": [],
            "is_token": True,
        },
        source=source_obj_id,
        controller=controller,
    )


def make_lander_token_events(
    controller: str,
    count: int = 1,
    source_obj_id: Optional[str] = None,
) -> list[Event]:
    """Build N OBJECT_CREATED Events for Lander tokens. Convenience wrapper."""
    if count <= 0:
        return []
    return [make_lander_token_event(controller, source_obj_id) for _ in range(count)]


# =============================================================================
# Predicates
# =============================================================================

def is_lander(obj: GameObject) -> bool:
    """Return True if ``obj`` is a Lander token.

    Recognized via subtype (canonical) or legacy name match (fallback for
    cards that may have created a Lander before this module existed).
    """
    if obj is None:
        return False
    chars = getattr(obj, "characteristics", None)
    if chars is None:
        return False
    subtypes = getattr(chars, "subtypes", None) or set()
    if LANDER_SUBTYPE in subtypes:
        return True
    # Legacy/stringly-typed fallback. Some scripts created tokens named
    # "Lander Token" without the subtype before this helper existed.
    return obj.name == LANDER_TOKEN_NAME


# =============================================================================
# "Sacrificed a Lander this turn" tracking
# =============================================================================

def _key(player_id: str) -> str:
    return f"landers_sacced_{player_id}"


def landers_sacced_this_turn(player_id: str, state: GameState) -> int:
    """How many Landers ``player_id`` has sacrificed this turn (>= 0)."""
    td = getattr(state, "turn_data", None) or {}
    return int(td.get(_key(player_id), 0) or 0)


def did_sac_lander_this_turn(player_id: str, state: GameState) -> bool:
    """Convenience: True if ``player_id`` sacrificed at least one Lander this turn."""
    return landers_sacced_this_turn(player_id, state) > 0


def mark_lander_sacrificed(player_id: str, state: GameState, amount: int = 1) -> None:
    """Public writer. Idempotent / additive on the per-turn counter."""
    td = getattr(state, "turn_data", None)
    if td is None:
        return
    key = _key(player_id)
    td[key] = int(td.get(key, 0) or 0) + max(0, int(amount))


# =============================================================================
# System interceptor: maintain the per-turn counter
# =============================================================================

def _zone_change_to_graveyard_or_exile_filter(event: Event, state: GameState) -> bool:
    """Match ZONE_CHANGE moving a Lander off the battlefield as a sacrifice.

    The system-level SACRIFICE TRANSFORM interceptor in :mod:`game` rewrites
    SACRIFICE events into ZONE_CHANGE events with ``payload['reason'] ==
    'sacrifice'``. We accept either ``reason``, ``cause``, or
    ``from_sacrifice`` as the sacrifice marker so we stay forward-compatible
    with card scripts that use any of those keys.
    """
    if event.type != EventType.ZONE_CHANGE:
        return False
    if event.payload.get("from_zone_type") != ZoneType.BATTLEFIELD:
        return False
    to_zone_type = event.payload.get("to_zone_type")
    # Sacrifice usually goes to graveyard; "exile instead of graveyard" replacements
    # would route to exile. Either way, the Lander left the battlefield as a sac.
    if to_zone_type not in (ZoneType.GRAVEYARD, ZoneType.EXILE):
        return False
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id)
    if obj is None or not is_lander(obj):
        return False
    # Only count sacrifices (not destroys/exiles).
    if (
        event.payload.get("cause") == "sacrifice"
        or event.payload.get("reason") == "sacrifice"
        or event.payload.get("from_sacrifice") is True
    ):
        return True
    return False


def _zone_change_to_graveyard_handler(event: Event, state: GameState) -> InterceptorResult:
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id)
    if obj is None or not obj.controller:
        return InterceptorResult(action=InterceptorAction.PASS)
    mark_lander_sacrificed(obj.controller, state, 1)
    return InterceptorResult(
        action=InterceptorAction.REACT,
        new_events=[
            Event(
                type=EventType.LANDER_SACRIFICED,
                payload={"player": obj.controller, "object_id": obj_id},
                source=event.source,
            )
        ],
    )


def _sacrifice_filter(event: Event, state: GameState) -> bool:
    """Match SACRIFICE events targeting a Lander.

    The SACRIFICE handler emits a follow-up ZONE_CHANGE *without* a 'cause'
    payload key, so we also subscribe to SACRIFICE directly to be robust.
    """
    if event.type != EventType.SACRIFICE:
        return False
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id)
    return obj is not None and is_lander(obj)


def _sacrifice_handler(event: Event, state: GameState) -> InterceptorResult:
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id)
    if obj is None or not obj.controller:
        return InterceptorResult(action=InterceptorAction.PASS)
    mark_lander_sacrificed(obj.controller, state, 1)
    return InterceptorResult(
        action=InterceptorAction.REACT,
        new_events=[
            Event(
                type=EventType.LANDER_SACRIFICED,
                payload={"player": obj.controller, "object_id": obj_id},
                source=event.source,
            )
        ],
    )


# =============================================================================
# Search-library activation (stubbed — depends on library_search subsystem)
# =============================================================================

def make_lander_search_event(player_id: str, source_obj_id: Optional[str] = None) -> Event:
    """Emit the LANDER_SEARCH_LAND event resolved by :func:`_resolve_lander_search`.

    This represents the "search your library for a basic land card, put it
    onto the battlefield tapped, then shuffle" portion of the Lander activated
    ability. The corresponding "tap + sacrifice" cost is the responsibility of
    the activator (UI/AI) to issue first via TAP and SACRIFICE events.
    """
    return Event(
        type=EventType.LANDER_SEARCH_LAND,
        payload={"player": player_id},
        source=source_obj_id,
        controller=player_id,
    )


def _is_basic_land(obj: GameObject) -> bool:
    chars = getattr(obj, "characteristics", None)
    if chars is None:
        return False
    if CardType.LAND not in (getattr(chars, "types", None) or set()):
        return False
    subtypes = getattr(chars, "subtypes", None) or set()
    if subtypes & BASIC_LAND_SUBTYPES:
        # Either supertype "Basic" is set, or the card is named after a basic
        # subtype. Most basic land card defs have the subtype set.
        return True
    # Some basic lands are encoded with the supertype "Basic". Accept either.
    supertypes = getattr(chars, "supertypes", None) or set()
    return "Basic" in supertypes and bool(subtypes & BASIC_LAND_SUBTYPES)


def _resolve_lander_search(event: Event, state: GameState) -> InterceptorResult:
    """Stub resolver for LANDER_SEARCH_LAND.

    Behavior:
      1. If ``state.turn_data['_library_search_resolver']`` is callable, defer
         to it (this is the integration hook for the library_search subsystem
         once it lands). The resolver is called as
         ``resolver(event, state, basic_land=True, tapped=True)`` and is
         expected to return ``InterceptorResult`` (or None to fall through).
      2. Otherwise, perform a best-effort scan of the controller's library:
         find the first basic land, move it to the battlefield tapped, then
         shuffle. If no basic land is found, do nothing (the activation still
         counts as having sacrificed the Lander; that's tracked separately).

    Replace step 2's body with a clean delegated call once library_search
    ships its public API.
    """
    player_id = event.payload.get("player") or event.controller
    if not player_id or player_id not in state.players:
        return InterceptorResult(action=InterceptorAction.PASS)

    # ---- Integration hook for the library_search subsystem ------------------
    td = getattr(state, "turn_data", None) or {}
    resolver = td.get("_library_search_resolver")
    if callable(resolver):
        try:
            result = resolver(event, state, basic_land=True, tapped=True)
            if result is not None:
                return result
        except Exception:
            # Fall through to the stub on any resolver exception.
            pass

    # ---- Best-effort stub ---------------------------------------------------
    library_key = f"library_{player_id}"
    library = state.zones.get(library_key)
    battlefield = state.zones.get("battlefield")
    if library is None or battlefield is None:
        return InterceptorResult(action=InterceptorAction.PASS)

    chosen_id: Optional[str] = None
    for cid in library.objects:
        cobj = state.objects.get(cid)
        if cobj is not None and _is_basic_land(cobj):
            chosen_id = cid
            break

    if chosen_id is not None:
        # Move chosen card from library -> battlefield, tapped.
        try:
            library.objects.remove(chosen_id)
        except ValueError:
            pass
        battlefield.objects.append(chosen_id)
        cobj = state.objects.get(chosen_id)
        if cobj is not None:
            cobj.zone = ZoneType.BATTLEFIELD
            cobj.entered_zone_at = state.next_timestamp()
            if hasattr(cobj.state, "tapped"):
                cobj.state.tapped = True

    # Shuffle the library regardless (matches printed text "then shuffle").
    if library.objects:
        random.shuffle(library.objects)

    return InterceptorResult(action=InterceptorAction.PASS)


# =============================================================================
# Registration
# =============================================================================

def register_lander_tracker(game: "Game") -> None:
    """Register Lander system interceptors. Called from
    :meth:`Game._setup_system_interceptors`.

    Two cooperating interceptors maintain the per-turn sacrifice counter:

      * SACRIFICE-event observer (catches direct SACRIFICE events).
      * ZONE_CHANGE observer with cause=='sacrifice' (catches the follow-up
        zone movement and any future code paths that bypass SACRIFICE).

    Both increment the same ``turn_data['landers_sacced_<player>']`` key, so
    the second observer is a no-op safety net unless the SACRIFICE event was
    skipped. (We only count once per sacrifice in practice because the
    pipeline emits ZONE_CHANGE *without* the cause key by default, so the
    ZONE_CHANGE filter rejects it. Card scripts that directly issue a
    ZONE_CHANGE with cause='sacrifice' will still be counted.)

    A third interceptor resolves LANDER_SEARCH_LAND to perform the
    search-and-shuffle portion of the Lander activated ability. This depends
    on the library_search subsystem; until that lands, the resolver uses a
    stub that scans the library for the first basic land.
    """
    register = game.register_interceptor

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_sacrifice_filter,
        handler=_sacrifice_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_zone_change_to_graveyard_or_exile_filter,
        handler=_zone_change_to_graveyard_handler,
        duration="forever",
    ))

    # Search resolver runs in REACT (after the event has been "resolved" by
    # the pipeline; LANDER_SEARCH_LAND has no built-in handler so REACT is the
    # right time to mutate library/battlefield as a side-effect).
    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: e.type == EventType.LANDER_SEARCH_LAND,
        handler=_resolve_lander_search,
        duration="forever",
    ))


__all__ = [
    "LANDER_TOKEN_NAME",
    "LANDER_SUBTYPE",
    "BASIC_LAND_SUBTYPES",
    "make_lander_token_event",
    "make_lander_token_events",
    "is_lander",
    "landers_sacced_this_turn",
    "did_sac_lander_this_turn",
    "mark_lander_sacrificed",
    "make_lander_search_event",
    "register_lander_tracker",
]
