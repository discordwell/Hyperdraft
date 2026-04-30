"""
Library search with player choice.

This module implements a generic "search your library for [filter] card" subsystem
that mirrors the targeting subsystem's PendingChoice pattern: open a choice,
let the player (or AI) pick from the filtered set of library cards, then resolve
by moving the chosen card(s) to a destination zone (hand/battlefield/graveyard/
library top/library bottom) and optionally shuffling.

Public API
----------
- create_library_search_choice(state, player_id, source_id, ...) -> PendingChoice
- library_search_with_callback(state, ..., on_chosen=...) -> PendingChoice
- _execute_library_search(choice, selected, state) -> list[Event]
  (registered as the choice's callback handler; called by Game._process_choice
  via the generic `callback_data['handler']` dispatch)

Card scripts typically don't import this module directly. Instead they call
helpers in `src/cards/interceptor_helpers.py` (see the LIBRARY SEARCH HELPERS
section), which build the choice with sensible defaults.

Destinations
------------
- "hand" (default)            -> chosen card(s) go to the searcher's hand
- "battlefield"               -> chosen card(s) enter the battlefield
- "battlefield_tapped"        -> chosen card(s) enter tapped
- "graveyard"                 -> chosen card(s) go to the searcher's graveyard
- "library_top"               -> chosen card(s) go on top of library
- "library_bottom"            -> chosen card(s) go on bottom of library
- "exile"                     -> chosen card(s) are exiled
"""

from __future__ import annotations

import random
from typing import Callable, Optional, Any

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    PendingChoice,
    ZoneType,
)


# =============================================================================
# Filter helper (resolved to objects by the system)
# =============================================================================

LibraryFilter = Callable[[GameObject, GameState], bool]


def collect_library_candidates(
    state: GameState,
    player_id: str,
    filter_fn: Optional[LibraryFilter],
) -> list[str]:
    """Return the IDs of all cards in `player_id`'s library matching `filter_fn`.

    If `filter_fn` is None, all cards in the library are eligible.
    """
    library_key = f"library_{player_id}"
    library = state.zones.get(library_key)
    if not library:
        return []

    candidates: list[str] = []
    for oid in library.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if filter_fn is None or filter_fn(obj, state):
            candidates.append(oid)
    return candidates


# =============================================================================
# Public: open a library-search choice
# =============================================================================

def create_library_search_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    filter_fn: Optional[LibraryFilter] = None,
    *,
    min_count: int = 0,
    max_count: int = 1,
    destination: str = "hand",
    reveal: bool = False,
    shuffle_after: bool = True,
    tapped: Optional[bool] = None,
    prompt: Optional[str] = None,
    optional: bool = True,
    on_chosen: Optional[Callable[[PendingChoice, list[str], GameState], list[Event]]] = None,
    extra_callback_data: Optional[dict] = None,
) -> Optional[PendingChoice]:
    """Open a player-choice library search.

    Creates a PendingChoice on `state` whose options are the IDs of library
    cards matching `filter_fn`. When the player submits a selection, the
    generic dispatch in Game._process_choice calls our handler
    (`_execute_library_search`) which moves the chosen cards to `destination`
    and (if `shuffle_after`) shuffles the library.

    Returns the PendingChoice, or None if the search couldn't be opened
    (e.g. an empty library and `optional=True`, or a non-optional search with
    no candidates — caller should treat None as "no effect").

    Args:
        state: Game state.
        player_id: The searching player.
        source_id: The card/ability id that's searching (for logs and triggers).
        filter_fn: Optional `(obj, state) -> bool` filter. None = any card.
        min_count: Minimum cards to choose. 0 enables "may search".
        max_count: Maximum cards to choose. Default 1.
        destination: One of "hand", "battlefield", "battlefield_tapped",
            "graveyard", "library_top", "library_bottom", "exile".
            Convenience: passing tapped=True with destination="battlefield"
            is equivalent to "battlefield_tapped".
        reveal: If True, emit a LIBSEARCH_REVEAL event for each chosen card
            (used by triggers / public-information cards).
        shuffle_after: If True (default), shuffle the library on completion.
            Set False for "look at top X", "library_top" (preserves order).
        tapped: If True and destination is "battlefield", forces tapped entry.
        prompt: Optional UI prompt. Auto-generated if not provided.
        optional: If True (default), min_count is allowed to be 0 and the
            player can choose to find nothing.
        on_chosen: Optional `(choice, selected, state) -> list[Event]` hook,
            run *after* the cards have been moved. Use this for "then do X"
            riders (e.g. "then put a +1/+1 counter on it").
        extra_callback_data: Extra keys to merge into callback_data so the
            on_chosen hook can read context.

    Example:
        # "Search your library for a basic Forest, put it onto the battlefield
        #  tapped, then shuffle."
        from src.engine.library_search import create_library_search_choice
        create_library_search_choice(
            state, obj.controller, obj.id,
            filter_fn=is_basic_with_subtype("Forest"),
            destination="battlefield_tapped",
            shuffle_after=True,
            prompt="Search for a basic Forest",
        )
    """
    if state is None or player_id not in state.players:
        return None

    library_key = f"library_{player_id}"
    if library_key not in state.zones:
        return None

    candidates = collect_library_candidates(state, player_id, filter_fn)

    # Normalize destination (compatibility shim for tapped=True).
    if tapped and destination == "battlefield":
        destination = "battlefield_tapped"

    # If optional and no candidates, gracefully no-op (no choice opened).
    actual_min = 0 if optional else min_count
    if not candidates and optional:
        # Still emit shuffle if requested, since "fail to find" cards still shuffle.
        if shuffle_after:
            _shuffle_library(state, player_id)
        return None

    actual_max = min(max_count, len(candidates))
    if actual_max < actual_min:
        actual_max = actual_min

    if not prompt:
        prompt = _default_prompt(destination, max_count, optional)

    callback_data: dict = {
        "handler": _execute_library_search,
        "destination": destination,
        "reveal": bool(reveal),
        "shuffle_after": bool(shuffle_after),
        "source_id": source_id,
        "controller_id": player_id,
        "max_count": int(max_count),
        "min_count": int(min_count),
        "on_chosen": on_chosen,
    }
    if extra_callback_data:
        for k, v in extra_callback_data.items():
            if k not in callback_data:
                callback_data[k] = v

    choice = PendingChoice(
        choice_type="library_search",
        player=player_id,
        prompt=prompt,
        options=candidates,
        source_id=source_id,
        min_choices=int(actual_min),
        max_choices=int(actual_max),
        callback_data=callback_data,
    )
    state.pending_choice = choice
    return choice


def library_search_with_callback(
    state: GameState,
    player_id: str,
    source_id: str,
    filter_fn: Optional[LibraryFilter] = None,
    *,
    on_chosen: Optional[Callable[[PendingChoice, list[str], GameState], list[Event]]] = None,
    **kwargs: Any,
) -> Optional[PendingChoice]:
    """Convenience wrapper that mirrors `target_with_callback` semantics.

    Equivalent to ``create_library_search_choice(..., on_chosen=on_chosen)``
    but reads more naturally at card sites where a custom rider is needed.
    """
    return create_library_search_choice(
        state, player_id, source_id, filter_fn,
        on_chosen=on_chosen,
        **kwargs,
    )


# =============================================================================
# Choice resolver (registered as callback_data['handler'])
# =============================================================================

def _execute_library_search(
    choice: PendingChoice,
    selected: list,
    state: GameState,
) -> list[Event]:
    """Resolve a library_search PendingChoice.

    Called by Game._process_choice once the player submits their selection.
    For non-battlefield destinations (hand/graveyard/exile/library_*) we
    perform the move directly; for battlefield destinations we instead
    return a ZONE_CHANGE event so the regular pipeline runs ETB triggers
    and setup_interceptors. The on_chosen rider runs after all moves.
    """
    cb = choice.callback_data or {}
    player_id = choice.player
    destination = cb.get("destination", "hand")
    reveal = bool(cb.get("reveal", False))
    shuffle_after = bool(cb.get("shuffle_after", True))
    on_chosen = cb.get("on_chosen")

    # Normalize selection into a list of card ids that are actually in the
    # library (defensive against stale options).
    selected_ids = _normalize_selected(selected, choice.options, state, player_id)

    moved: list[str] = []
    follow_ups: list[Event] = []
    battlefield_zone_changes: list[Event] = []

    for cid in selected_ids:
        if destination in ("battlefield", "battlefield_tapped"):
            # Use ZONE_CHANGE so the pipeline fires ETB triggers properly.
            obj = state.objects.get(cid)
            library = state.zones.get(f"library_{player_id}")
            if obj is None or library is None or cid not in library.objects:
                continue
            obj.controller = player_id
            payload = {
                "object_id": cid,
                "from_zone": f"library_{player_id}",
                "from_zone_type": ZoneType.LIBRARY,
                "to_zone": "battlefield",
                "to_zone_type": ZoneType.BATTLEFIELD,
                "source_id": cb.get("source_id"),
                "library_search_destination": destination,
            }
            if destination == "battlefield_tapped":
                # The zone handler reads payload['tapped'] AFTER resetting
                # obj.state.tapped to False, so we must communicate via payload.
                payload["tapped"] = True
            battlefield_zone_changes.append(Event(
                type=EventType.ZONE_CHANGE,
                payload=payload,
                source=cb.get("source_id"),
                controller=player_id,
            ))
            moved.append(cid)
        elif _move_card_from_library(state, player_id, cid, destination):
            moved.append(cid)
            if reveal:
                follow_ups.append(Event(
                    type=EventType.LIBSEARCH_REVEAL,
                    payload={
                        "player": player_id,
                        "object_id": cid,
                        "source_id": cb.get("source_id"),
                        "destination": destination,
                    },
                    source=cb.get("source_id"),
                    controller=player_id,
                ))

    # Battlefield zone-changes go FIRST so ETB triggers fire before shuffle.
    follow_ups = battlefield_zone_changes + follow_ups

    if shuffle_after:
        _shuffle_library(state, player_id)

    # Always emit a completion marker so card scripts can hang triggers off
    # "after a successful tutor".
    follow_ups.append(Event(
        type=EventType.LIBSEARCH_COMPLETE,
        payload={
            "player": player_id,
            "selected": list(moved),
            "destination": destination,
            "shuffled": shuffle_after,
            "source_id": cb.get("source_id"),
        },
        source=cb.get("source_id"),
        controller=player_id,
    ))

    # Run the on_chosen rider, if any (e.g. "then put a +1/+1 counter on it").
    if on_chosen is not None:
        try:
            extra = on_chosen(choice, moved, state) or []
        except Exception:
            extra = []
        if extra:
            follow_ups.extend(extra)

    return follow_ups


# =============================================================================
# Internals
# =============================================================================

def _default_prompt(destination: str, max_count: int, optional: bool) -> str:
    """Generate a friendly default prompt for a library search."""
    qty = "a card" if max_count == 1 else f"up to {max_count} cards"
    dest_phrase = {
        "hand": "put it into your hand" if max_count == 1 else "put them into your hand",
        "battlefield": "put it onto the battlefield" if max_count == 1 else "put them onto the battlefield",
        "battlefield_tapped": (
            "put it onto the battlefield tapped" if max_count == 1
            else "put them onto the battlefield tapped"
        ),
        "graveyard": "put it into your graveyard" if max_count == 1 else "put them into your graveyard",
        "library_top": "put it on top of your library" if max_count == 1 else "put them on top of your library",
        "library_bottom": "put it on the bottom of your library" if max_count == 1 else "put them on the bottom of your library",
        "exile": "exile it" if max_count == 1 else "exile them",
    }.get(destination, "put it into your hand")
    lead = "You may search" if optional else "Search"
    return f"{lead} your library for {qty}, then {dest_phrase}."


def _normalize_selected(
    selected: list,
    options: list,
    state: GameState,
    player_id: str,
) -> list[str]:
    """Normalize the AI/UI selection payload to a list of legal library IDs."""
    if not selected:
        return []
    # Selection might be raw IDs or option dicts; PendingChoice options are IDs.
    ids: list[str] = []
    valid = set(options)
    library = state.zones.get(f"library_{player_id}")
    library_ids = set(library.objects) if library else set()
    for s in selected:
        cid = s.get("id") if isinstance(s, dict) else s
        if cid is None:
            continue
        if cid in valid and cid in library_ids:
            ids.append(cid)
    return ids


def _move_card_from_library(
    state: GameState,
    player_id: str,
    card_id: str,
    destination: str,
) -> bool:
    """Move a card from a player's library to `destination`. Returns True on success.

    Note: battlefield destinations are NOT handled here — they're routed through
    ZONE_CHANGE events by `_execute_library_search` so the pipeline can fire
    ETB triggers and run setup_interceptors via the normal path.
    """
    library_key = f"library_{player_id}"
    library = state.zones.get(library_key)
    if not library or card_id not in library.objects:
        return False
    obj = state.objects.get(card_id)
    if obj is None:
        return False

    library.objects.remove(card_id)

    if destination == "hand":
        dest = state.zones.get(f"hand_{player_id}")
        if dest is None:
            return False
        dest.objects.append(card_id)
        obj.zone = ZoneType.HAND
    elif destination == "graveyard":
        dest = state.zones.get(f"graveyard_{player_id}")
        if dest is None:
            return False
        dest.objects.append(card_id)
        obj.zone = ZoneType.GRAVEYARD
    elif destination == "library_top":
        # Insert at top (index 0). Caller should typically pass shuffle_after=False.
        library.objects.insert(0, card_id)
        # Card never actually leaves the library zone.
    elif destination == "library_bottom":
        library.objects.append(card_id)
    elif destination == "exile":
        dest = state.zones.get("exile")
        if dest is None:
            return False
        dest.objects.append(card_id)
        obj.zone = ZoneType.EXILE
    else:
        # Unknown destination: default to hand to avoid losing the card.
        dest = state.zones.get(f"hand_{player_id}")
        if dest is None:
            return False
        dest.objects.append(card_id)
        obj.zone = ZoneType.HAND

    obj.entered_zone_at = state.timestamp
    return True


def _shuffle_library(state: GameState, player_id: str) -> None:
    library = state.zones.get(f"library_{player_id}")
    if library is None:
        return
    random.shuffle(library.objects)


# =============================================================================
# Common filter factories (re-exportable; also wrapped in interceptor_helpers)
# =============================================================================

def is_card_type(card_type) -> LibraryFilter:
    """Filter: card has the given CardType (e.g. CardType.CREATURE)."""
    def fn(obj: GameObject, state: GameState) -> bool:
        return card_type in obj.characteristics.types
    return fn


def is_basic_land() -> LibraryFilter:
    """Filter: card is a basic land."""
    def fn(obj: GameObject, state: GameState) -> bool:
        return "Basic" in (obj.characteristics.supertypes or set())
    return fn


def is_basic_with_subtype(subtype: str) -> LibraryFilter:
    """Filter: card is a basic land with the given subtype (e.g. 'Forest')."""
    def fn(obj: GameObject, state: GameState) -> bool:
        return (
            "Basic" in (obj.characteristics.supertypes or set())
            and subtype in (obj.characteristics.subtypes or set())
        )
    return fn


def _mana_value(mana_cost: Optional[str]) -> int:
    """Approximate mana value from a printed cost string like '{2}{G}{G}'.

    Numeric symbols add their numeric value, every other symbol counts as 1
    (colored, hybrid, phyrexian, generic-X are treated as 1 because we don't
    have an X value bound here). Good enough for filter checks like
    "creature with MV >= 6".
    """
    if not mana_cost:
        return 0
    mv = 0
    cur = ""
    inside = False
    for ch in mana_cost:
        if ch == "{":
            inside = True
            cur = ""
        elif ch == "}":
            if cur.isdigit():
                mv += int(cur)
            elif cur.upper() == "X":
                # X has no defined value at filter-check time; ignore.
                pass
            else:
                mv += 1
            inside = False
            cur = ""
        elif inside:
            cur += ch
    return mv


def is_creature_with_mv_at_least(min_mv: int) -> LibraryFilter:
    """Filter: creature card with mana value >= min_mv."""
    from .types import CardType

    def fn(obj: GameObject, state: GameState) -> bool:
        if CardType.CREATURE not in obj.characteristics.types:
            return False
        return _mana_value(obj.characteristics.mana_cost) >= min_mv
    return fn


def is_instant_or_sorcery_with_mv(target_mv: int) -> LibraryFilter:
    """Filter: instant or sorcery with exactly target_mv mana value."""
    from .types import CardType

    def fn(obj: GameObject, state: GameState) -> bool:
        types = obj.characteristics.types
        if CardType.INSTANT not in types and CardType.SORCERY not in types:
            return False
        return _mana_value(obj.characteristics.mana_cost) == target_mv
    return fn


def is_subtype(subtype: str) -> LibraryFilter:
    """Filter: card has the given subtype (e.g. 'Aura', 'Equipment')."""
    def fn(obj: GameObject, state: GameState) -> bool:
        return subtype in (obj.characteristics.subtypes or set())
    return fn


def any_card() -> LibraryFilter:
    """Filter: any card in library (used for unconditional tutors)."""
    def fn(obj: GameObject, state: GameState) -> bool:
        return True
    return fn
