"""
Turn-state primitive trackers + COIN_FLIP helper.

This module wires a small set of system interceptors that maintain "did X
happen this turn" counters/flags inside ``state.turn_data``. Card scripts read
these via the accessors at the bottom of this file, and via the lightweight
re-exports in ``src/cards/interceptor_helpers.py`` (under ``# === TURN STATE
HELPERS ===``).

State storage (per turn, cleared in TurnManager._emit_turn_end):

  * ``life_gained_<player_id>``      -> int (sum of positive LIFE_CHANGE amounts)
  * ``life_lost_<player_id>``        -> int (sum of |negative LIFE_CHANGE amounts|)
  * ``spells_cast_<player_id>``      -> int (number of CAST/SPELL_CAST events)
  * ``attacked_alone_<player_id>``   -> bool (exactly one creature attacked this turn)
  * ``creatures_died_this_turn``     -> int (any controller — Morbid)
  * ``creatures_died_by_<player_id>``-> int (per-controller death count)
  * ``cards_drawn_<player_id>``      -> int (DRAW events × amount)
  * ``combat_damage_to_<player_id>`` -> int (sum of combat DAMAGE event amounts to player)

Plus a coin-flip primitive (``COIN_FLIP`` EventType + ``flip_coin``) which
uses ``state.rng_seed`` for determinism in tests.

Wired from ``Game._setup_system_interceptors`` via ``register_turn_state_tracker``.
"""

import random
from typing import TYPE_CHECKING, Optional

from .types import (
    Event, EventType, GameState, ZoneType, CardType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id,
)

if TYPE_CHECKING:
    from .game import Game


# =============================================================================
# Public read accessors (card-side helpers re-export these)
# =============================================================================

def life_gained_this_turn(player_id: str, state: GameState) -> int:
    """Total life gained this turn by ``player_id`` (sum of positive LIFE_CHANGE)."""
    td = getattr(state, "turn_data", None) or {}
    return int(td.get(f"life_gained_{player_id}", 0))


def life_lost_this_turn(player_id: str, state: GameState) -> int:
    """Total life lost this turn by ``player_id`` (sum of |negative LIFE_CHANGE|)."""
    td = getattr(state, "turn_data", None) or {}
    return int(td.get(f"life_lost_{player_id}", 0))


def spells_cast_this_turn(player_id: str, state: GameState) -> int:
    """Number of spells cast by ``player_id`` this turn (CAST/SPELL_CAST events)."""
    td = getattr(state, "turn_data", None) or {}
    return int(td.get(f"spells_cast_{player_id}", 0))


def nth_spell_this_turn(player_id: str, n: int, state: GameState) -> bool:
    """Return True iff the most recent CAST puts ``player_id``'s spell-count at exactly ``n``.

    Use immediately after a CAST/SPELL_CAST event resolves to test, e.g.,
    "the second spell you cast each turn" (Celebration in WOE):

        if nth_spell_this_turn(controller, 2, state): ...
    """
    return spells_cast_this_turn(player_id, state) == int(n)


def attacked_alone_this_turn(player_id: str, state: GameState) -> bool:
    """Return True iff exactly one creature attacked for ``player_id`` this turn."""
    td = getattr(state, "turn_data", None) or {}
    return bool(td.get(f"attacked_alone_{player_id}", False))


def creatures_died_this_turn(state: GameState, player_id: Optional[str] = None) -> int:
    """Return creature death count this turn (global if ``player_id`` is None)."""
    td = getattr(state, "turn_data", None) or {}
    if player_id is None:
        return int(td.get("creatures_died_this_turn", 0))
    return int(td.get(f"creatures_died_by_{player_id}", 0))


def cards_drawn_this_turn(player_id: str, state: GameState) -> int:
    """Total cards ``player_id`` drew this turn (sum of DRAW amounts)."""
    td = getattr(state, "turn_data", None) or {}
    return int(td.get(f"cards_drawn_{player_id}", 0))


def combat_damage_dealt_to_this_turn(player_id: str, state: GameState) -> int:
    """Total combat damage dealt to ``player_id`` this turn."""
    td = getattr(state, "turn_data", None) or {}
    return int(td.get(f"combat_damage_to_{player_id}", 0))


# =============================================================================
# Coin flip primitive
# =============================================================================

def _get_rng(state: GameState) -> random.Random:
    """Return the per-state RNG, lazily constructed from ``state.rng_seed``."""
    rng = getattr(state, "_rng", None)
    if rng is None:
        seed = getattr(state, "rng_seed", None)
        rng = random.Random(seed) if seed is not None else random.Random()
        state._rng = rng
    return rng


def flip_coin(state: GameState) -> bool:
    """Flip a fair coin. Returns True (heads) or False (tails).

    Uses ``state.rng_seed`` if set, otherwise a fresh ``random.Random()``. The
    same RNG instance is reused across calls within a single game state so the
    sequence is reproducible. To start a new sequence, set ``state.rng_seed``
    and either delete ``state._rng`` or reuse the state instance.
    """
    return _get_rng(state).choice([True, False])


def emit_coin_flip(state: GameState, player_id: Optional[str] = None,
                   source: Optional[str] = None) -> Event:
    """Build a COIN_FLIP marker event with a freshly-flipped result.

    Caller decides what to do with the result; observers can listen for
    ``EventType.COIN_FLIP`` to react. The result is also surfaced via
    ``event.payload['result']``.
    """
    result = flip_coin(state)
    return Event(
        type=EventType.COIN_FLIP,
        payload={"result": bool(result), "player": player_id},
        source=source,
        controller=player_id,
    )


# =============================================================================
# System interceptor handlers
# =============================================================================

def _life_change_filter(event: Event, state: GameState) -> bool:
    return event.type == EventType.LIFE_CHANGE


def _life_change_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    player_id = event.payload.get("player")
    amount = event.payload.get("amount", 0)
    # Object-targeted healing on a HERO routes to its owner; otherwise it's a
    # creature heal and shouldn't count toward player life-gain trackers.
    if not player_id:
        obj_id = event.payload.get("object_id") or event.payload.get("target")
        obj = state.objects.get(obj_id) if obj_id else None
        if obj and CardType.HERO in obj.characteristics.types:
            player_id = obj.owner
    if not player_id or player_id not in state.players:
        return InterceptorResult(action=InterceptorAction.PASS)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return InterceptorResult(action=InterceptorAction.PASS)
    if amount > 0:
        key = f"life_gained_{player_id}"
        td[key] = int(td.get(key, 0)) + amount
    elif amount < 0:
        key = f"life_lost_{player_id}"
        td[key] = int(td.get(key, 0)) + (-amount)
    return InterceptorResult(action=InterceptorAction.PASS)


def _cast_filter(event: Event, state: GameState) -> bool:
    return event.type in (EventType.CAST, EventType.SPELL_CAST)


def _cast_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    caster = (
        event.payload.get("caster")
        or event.payload.get("controller")
        or event.payload.get("player")
        or event.controller
    )
    if not caster:
        return InterceptorResult(action=InterceptorAction.PASS)
    key = f"spells_cast_{caster}"
    td[key] = int(td.get(key, 0)) + 1
    return InterceptorResult(action=InterceptorAction.PASS)


def _attack_declared_filter(event: Event, state: GameState) -> bool:
    # COMBAT_DECLARED is the consolidated "all attackers known" event the combat
    # manager fires after every per-attacker ATTACK_DECLARED. We piggy-back on
    # it because it carries the full attacker list on its payload.
    return event.type in (EventType.ATTACK_DECLARED, EventType.COMBAT_DECLARED)


def _attack_declared_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)

    if event.type == EventType.COMBAT_DECLARED:
        # Authoritative path: payload carries every attacker.
        attackers = event.payload.get("attackers") or []
        attacking_player = event.payload.get("attacking_player")
        if attacking_player:
            # Initialize tracker even when the list is empty so callers can
            # distinguish "no combat yet" (None/missing key) from "0 attackers".
            attacked_count = 0
            for aid in attackers:
                obj = state.objects.get(aid)
                if obj and obj.controller == attacking_player:
                    attacked_count += 1
            td[f"attackers_count_{attacking_player}"] = attacked_count
            td[f"attacked_alone_{attacking_player}"] = (attacked_count == 1)
        return InterceptorResult(action=InterceptorAction.PASS)

    # ATTACK_DECLARED fallback for paths that emit only per-attacker events.
    attacker_id = event.payload.get("attacker_id") or event.payload.get("attacker")
    attacking_player = event.payload.get("attacking_player")
    if not attacking_player and attacker_id:
        obj = state.objects.get(attacker_id)
        if obj:
            attacking_player = obj.controller
    if not attacking_player:
        return InterceptorResult(action=InterceptorAction.PASS)

    key_count = f"attackers_count_{attacking_player}"
    new_count = int(td.get(key_count, 0)) + 1
    td[key_count] = new_count
    td[f"attacked_alone_{attacking_player}"] = (new_count == 1)
    return InterceptorResult(action=InterceptorAction.PASS)


def _object_destroyed_filter(event: Event, state: GameState) -> bool:
    if event.type != EventType.OBJECT_DESTROYED:
        return False
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id) if obj_id else None
    if obj is None:
        return False
    return CardType.CREATURE in obj.characteristics.types


def _object_destroyed_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    td["creatures_died_this_turn"] = int(td.get("creatures_died_this_turn", 0)) + 1
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id) if obj_id else None
    controller = obj.controller if obj else None
    if controller:
        key = f"creatures_died_by_{controller}"
        td[key] = int(td.get(key, 0)) + 1
    return InterceptorResult(action=InterceptorAction.PASS)


def _zone_change_to_graveyard_filter(event: Event, state: GameState) -> bool:
    """Catch creatures going from BATTLEFIELD to GRAVEYARD via ZONE_CHANGE.

    Some pipelines emit ZONE_CHANGE without firing OBJECT_DESTROYED separately
    (e.g. SBA path), and we want creatures_died_this_turn to count those too.
    """
    if event.type != EventType.ZONE_CHANGE:
        return False
    if event.payload.get("from_zone_type") != ZoneType.BATTLEFIELD:
        return False
    if event.payload.get("to_zone_type") != ZoneType.GRAVEYARD:
        return False
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id) if obj_id else None
    if obj is None:
        return False
    return CardType.CREATURE in obj.characteristics.types


def _zone_change_to_graveyard_handler(event: Event, state: GameState) -> InterceptorResult:
    """Same as _object_destroyed_handler but guards against double-counting.

    Many code paths emit BOTH OBJECT_DESTROYED and ZONE_CHANGE; we tag events
    we've already counted by source/object id so we don't double-up. The tag
    is per-turn (lives in turn_data) so the next turn it resets cleanly.
    """
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    obj_id = event.payload.get("object_id")
    if not obj_id:
        return InterceptorResult(action=InterceptorAction.PASS)
    counted = td.setdefault("_died_counted_this_turn", set())
    if not isinstance(counted, set):
        counted = set()
        td["_died_counted_this_turn"] = counted
    if obj_id in counted:
        return InterceptorResult(action=InterceptorAction.PASS)
    counted.add(obj_id)
    td["creatures_died_this_turn"] = int(td.get("creatures_died_this_turn", 0)) + 1
    obj = state.objects.get(obj_id)
    controller = obj.controller if obj else None
    if controller:
        key = f"creatures_died_by_{controller}"
        td[key] = int(td.get(key, 0)) + 1
    return InterceptorResult(action=InterceptorAction.PASS)


def _object_destroyed_with_dedup_handler(event: Event, state: GameState) -> InterceptorResult:
    """Dedup wrapper used in place of _object_destroyed_handler.

    Both this and the ZONE_CHANGE handler share a turn_data set so a single
    death counts once even if both events fire.
    """
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    obj_id = event.payload.get("object_id")
    if not obj_id:
        return InterceptorResult(action=InterceptorAction.PASS)
    counted = td.setdefault("_died_counted_this_turn", set())
    if not isinstance(counted, set):
        counted = set()
        td["_died_counted_this_turn"] = counted
    if obj_id in counted:
        return InterceptorResult(action=InterceptorAction.PASS)
    counted.add(obj_id)
    td["creatures_died_this_turn"] = int(td.get("creatures_died_this_turn", 0)) + 1
    obj = state.objects.get(obj_id)
    controller = obj.controller if obj else None
    if controller:
        key = f"creatures_died_by_{controller}"
        td[key] = int(td.get(key, 0)) + 1
    return InterceptorResult(action=InterceptorAction.PASS)


def _draw_filter(event: Event, state: GameState) -> bool:
    return event.type == EventType.DRAW


def _draw_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    player_id = event.payload.get("player")
    if not player_id:
        return InterceptorResult(action=InterceptorAction.PASS)
    amount = event.payload.get("amount")
    if amount is None:
        amount = event.payload.get("count", 1)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 1
    if amount <= 0:
        return InterceptorResult(action=InterceptorAction.PASS)
    key = f"cards_drawn_{player_id}"
    td[key] = int(td.get(key, 0)) + amount
    return InterceptorResult(action=InterceptorAction.PASS)


def _combat_damage_filter(event: Event, state: GameState) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if not event.payload.get("is_combat"):
        return False
    target = event.payload.get("target")
    return target is not None and target in state.players


def _combat_damage_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    target = event.payload.get("target")
    amount = event.payload.get("amount", 0)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return InterceptorResult(action=InterceptorAction.PASS)
    key = f"combat_damage_to_{target}"
    td[key] = int(td.get(key, 0)) + amount
    return InterceptorResult(action=InterceptorAction.PASS)


def _coin_flip_filter(event: Event, state: GameState) -> bool:
    return event.type == EventType.COIN_FLIP


def _coin_flip_handler(event: Event, state: GameState) -> InterceptorResult:
    """No-op pass-through. Listeners can register their own observers; this
    interceptor exists so that bare ``COIN_FLIP`` events emitted via
    ``pipeline.emit`` traverse the pipeline cleanly without "no handler"
    warnings (the pipeline tolerates missing handlers but having a system
    observer makes the event easy to observe in tests/log)."""
    return InterceptorResult(action=InterceptorAction.PASS)


# =============================================================================
# Registration
# =============================================================================

def register_turn_state_tracker(game: "Game") -> None:
    """Register the turn-state system interceptors on ``game``.

    Called from ``Game._setup_system_interceptors``.
    """
    register = game.register_interceptor

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_life_change_filter,
        handler=_life_change_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_cast_filter,
        handler=_cast_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_attack_declared_filter,
        handler=_attack_declared_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_object_destroyed_filter,
        handler=_object_destroyed_with_dedup_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_zone_change_to_graveyard_filter,
        handler=_zone_change_to_graveyard_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_draw_filter,
        handler=_draw_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_combat_damage_filter,
        handler=_combat_damage_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_coin_flip_filter,
        handler=_coin_flip_handler,
        duration="forever",
    ))


__all__ = [
    # Accessors
    "life_gained_this_turn",
    "life_lost_this_turn",
    "spells_cast_this_turn",
    "nth_spell_this_turn",
    "attacked_alone_this_turn",
    "creatures_died_this_turn",
    "cards_drawn_this_turn",
    "combat_damage_dealt_to_this_turn",
    # Coin flip
    "flip_coin",
    "emit_coin_flip",
    # Registration
    "register_turn_state_tracker",
]
