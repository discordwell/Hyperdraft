"""Cats — trick-taking + pile-building card game engine core.

Engine module for the Cats game. See ``docs/games/cats.md`` for the design.

State convention: this engine uses **flat attribute-attached state on GameState**:
    state.cats_round_number: int       — 1..9
    state.cats_lead_player: Optional[str] — who plays Counter-pounce this round
    state.cats_current_rule: Optional[Callable] — installed Category Rule
    state.cats_current_trick: dict     — transient {pounce_card, pounce_player, counter_card, counter_player, snack_forced, winner}
    state.cats_commanders: dict[str, str] — player_id -> commander obj id
    state.cats_game_over: bool
    state.cats_final_scores: dict[str, dict] — populated by finalize_game
    state.cats_piles: dict[str, dict[str, list[str]]] — {player_id: {pile_name: [obj_id, ...]}}
    state.cats_pile_trinkets: dict[str, dict[str, list[str]]] — {player_id: {pile_name: [trinket_obj_id, ...]}}

Public API (consumed by cats_combat.py, cats_turn.py, cats_adapter.py):
    setup_cats_player(state, player_id, deck, commander=None)
    begin_round(state) -> list[Event]
    play_card_to_trick(state, player_id, card_obj_id, role=None) -> list[Event]
    install_category_rule(state, pounce_card) -> None
    resolve_trick(state) -> list[Event]
    claim_pile(state, winner_id, target_pile) -> list[Event]
    end_round(state) -> list[Event]
    check_game_over(state) -> bool
    finalize_game(state) -> list[Event]
    score_cats_player(state, player_id) -> dict[str, int]

Trick rules:
    sleek_rule, fluffy_rule, scrappy_rule, sneaky_rule, CATS_CATEGORY_RULES

Constants:
    CATS_TOTAL_ROUNDS = 9
    CATS_HAND_SIZE = 5
    CATS_PILE_CAPS = {"pile_territory": 8, "pile_nap": 6, "pile_snack": 5, "pile_attention": 999}
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.engine.types import (
    CardDefinition,
    CardType,
    Characteristics,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    Zone,
    ZoneType,
    new_id,
)


# =============================================================================
# Constants
# =============================================================================

CATS_TOTAL_ROUNDS = 9
CATS_HAND_SIZE = 5
CATS_DECK_SIZE = 30

CATS_PILE_CAPS: dict[str, int] = {
    "pile_territory": 8,
    "pile_nap": 6,
    "pile_snack": 5,
    "pile_attention": 999,
}

CATS_CATEGORIES = ("Sleek", "Fluffy", "Scrappy", "Sneaky")

PILE_NAME_TO_ZONE: dict[str, ZoneType] = {
    "pile_territory": ZoneType.CATS_PILE_TERRITORY,
    "pile_nap": ZoneType.CATS_PILE_NAP,
    "pile_snack": ZoneType.CATS_PILE_SNACK,
    "pile_attention": ZoneType.CATS_PILE_ATTENTION,
}


# =============================================================================
# Trick rule callables
# =============================================================================

def _value_of(state: GameState, obj_id: str) -> int:
    """Read the Value of a played card. Moods are Value 0. Falls back to characteristics.power."""
    obj = state.objects.get(obj_id)
    if obj is None:
        return 0
    card_def = obj.card_def
    if card_def is not None:
        if CardType.CATS_MOOD in getattr(card_def.characteristics, "types", set()):
            return 0
        v = getattr(card_def, "cats_value", None)
        if v is not None:
            return int(v)
    if obj.characteristics and obj.characteristics.power is not None:
        return int(obj.characteristics.power)
    return 0


def _pile_total(state: GameState, player_id: str) -> int:
    """Total cards across the three scoring piles (for Fluffy tiebreaker)."""
    piles = getattr(state, "cats_piles", {}).get(player_id, {})
    return sum(len(piles.get(p, [])) for p in ("pile_territory", "pile_nap", "pile_snack"))


def _sneaky_value(state: GameState, obj_id: str) -> int:
    obj = state.objects.get(obj_id)
    if obj is None:
        return 0
    card_def = obj.card_def
    if card_def is not None:
        v = getattr(card_def, "cats_sneaky_value", None)
        if v is not None:
            return int(v)
    return _value_of(state, obj_id)


def sleek_rule(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Highest value wins. Ties → counter-pounce player (lead) wins."""
    va = _value_of(state, card_a_id)
    vb = _value_of(state, card_b_id)
    trick = getattr(state, "cats_current_trick", {}) or {}
    if va > vb:
        return trick.get("pounce_player", "")
    if vb > va:
        return trick.get("counter_player", "")
    return trick.get("counter_player", "") or trick.get("pounce_player", "")


def fluffy_rule(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Highest value wins. Ties → fewer cards across scoring piles wins."""
    va = _value_of(state, card_a_id)
    vb = _value_of(state, card_b_id)
    trick = getattr(state, "cats_current_trick", {}) or {}
    pp = trick.get("pounce_player", "")
    cp = trick.get("counter_player", "")
    if va > vb:
        return pp
    if vb > va:
        return cp
    pp_total = _pile_total(state, pp)
    cp_total = _pile_total(state, cp)
    if pp_total < cp_total:
        return pp
    if cp_total < pp_total:
        return cp
    return cp or pp


def scrappy_rule(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Lowest value wins. Ties → fewer cards in piles wins."""
    va = _value_of(state, card_a_id)
    vb = _value_of(state, card_b_id)
    trick = getattr(state, "cats_current_trick", {}) or {}
    pp = trick.get("pounce_player", "")
    cp = trick.get("counter_player", "")
    if va < vb:
        return pp
    if vb < va:
        return cp
    pp_total = _pile_total(state, pp)
    cp_total = _pile_total(state, cp)
    if pp_total < cp_total:
        return pp
    if cp_total < pp_total:
        return cp
    return cp or pp


def sneaky_rule(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Hidden sneaky_value: highest secret value wins."""
    sa = _sneaky_value(state, card_a_id)
    sb = _sneaky_value(state, card_b_id)
    trick = getattr(state, "cats_current_trick", {}) or {}
    pp = trick.get("pounce_player", "")
    cp = trick.get("counter_player", "")
    if sa > sb:
        return pp
    if sb > sa:
        return cp
    return cp or pp


CATS_CATEGORY_RULES: dict[str, Callable[[str, str, GameState], str]] = {
    "Sleek": sleek_rule,
    "Fluffy": fluffy_rule,
    "Scrappy": scrappy_rule,
    "Sneaky": sneaky_rule,
}


# =============================================================================
# Setup
# =============================================================================

def _make_object_from_def(state: GameState, card_def: CardDefinition, owner: str, zone: ZoneType) -> GameObject:
    """Create a GameObject from a CardDefinition. Mirrors how the engine builds objects."""
    from copy import deepcopy
    chars = deepcopy(card_def.characteristics)
    obj = GameObject(
        id=new_id(),
        name=card_def.name,
        owner=owner,
        controller=owner,
        zone=zone,
        characteristics=chars,
        card_def=card_def,
    )
    obj._state_ref = state
    obj.created_at = state.next_timestamp()
    obj.entered_zone_at = obj.created_at
    state.objects[obj.id] = obj
    return obj


def _ensure_zone(state: GameState, zone_type: ZoneType, owner: Optional[str]) -> Zone:
    """Get-or-create a zone keyed by (type, owner)."""
    zone_key = f"{zone_type.name}_{owner or 'shared'}"
    z = state.zones.get(zone_key)
    if z is None:
        z = Zone(type=zone_type, owner=owner)
        state.zones[zone_key] = z
    return z


def _init_cats_state(state: GameState) -> None:
    """Initialize all state.cats_* fields if missing. Idempotent."""
    if not hasattr(state, "cats_round_number"):
        state.cats_round_number = 1
    if not hasattr(state, "cats_lead_player"):
        state.cats_lead_player = None
    if not hasattr(state, "cats_current_rule"):
        state.cats_current_rule = None
    if not hasattr(state, "cats_current_trick"):
        state.cats_current_trick = _empty_trick()
    if not hasattr(state, "cats_commanders"):
        state.cats_commanders = {}
    if not hasattr(state, "cats_game_over"):
        state.cats_game_over = False
    if not hasattr(state, "cats_final_scores"):
        state.cats_final_scores = {}
    if not hasattr(state, "cats_piles"):
        state.cats_piles = {}
    if not hasattr(state, "cats_pile_trinkets"):
        state.cats_pile_trinkets = {}
    if not hasattr(state, "cats_winners"):
        state.cats_winners = []


def _empty_trick() -> dict:
    return {
        "pounce_card": None,
        "pounce_player": None,
        "counter_card": None,
        "counter_player": None,
        "installed_rule": None,
        "snack_forced": False,
        "winner": None,
    }


def setup_cats_player(
    state: GameState,
    player_id: str,
    deck: list[CardDefinition],
    commander: Optional[CardDefinition] = None,
) -> None:
    """Initialize a player for the Cats engine."""
    _init_cats_state(state)
    if player_id not in state.players:
        state.players[player_id] = Player(id=player_id, name=player_id)

    if state.rng_seed is not None:
        rng = random.Random(state.rng_seed)
    else:
        rng = random
    deck_copy = list(deck)
    rng.shuffle(deck_copy)

    library = _ensure_zone(state, ZoneType.LIBRARY, player_id)
    library.objects.clear()
    for cd in deck_copy:
        obj = _make_object_from_def(state, cd, player_id, ZoneType.LIBRARY)
        library.objects.append(obj.id)

    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    hand.objects.clear()
    for _ in range(CATS_HAND_SIZE):
        if not library.objects:
            break
        obj_id = library.objects.pop(0)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.HAND
        obj.entered_zone_at = state.next_timestamp()
        hand.objects.append(obj_id)

    state.cats_piles.setdefault(player_id, {
        "pile_territory": [],
        "pile_nap": [],
        "pile_snack": [],
        "pile_attention": [],
    })
    state.cats_pile_trinkets.setdefault(player_id, {
        "pile_territory": [],
        "pile_nap": [],
        "pile_snack": [],
        "pile_attention": [],
    })
    for pile_name, zone_type in PILE_NAME_TO_ZONE.items():
        _ensure_zone(state, zone_type, player_id)
    _ensure_zone(state, ZoneType.GRAVEYARD, player_id)  # discard

    if commander is not None:
        cmd_obj = _make_object_from_def(state, commander, player_id, ZoneType.COMMAND)
        cmd_zone = _ensure_zone(state, ZoneType.COMMAND, player_id)
        cmd_zone.objects.append(cmd_obj.id)
        state.cats_commanders[player_id] = cmd_obj.id
        if commander.setup_interceptors is not None:
            try:
                interceptors = commander.setup_interceptors(cmd_obj, state)
                for ic in interceptors or []:
                    state.interceptors[ic.id] = ic
                    cmd_obj.interceptor_ids.append(ic.id)
            except Exception:
                pass


# =============================================================================
# Public round-flow API
# =============================================================================

def _player_ids(state: GameState) -> list[str]:
    return list(state.players.keys())


def _category_of(state: GameState, card_obj_id: str) -> Optional[str]:
    obj = state.objects.get(card_obj_id)
    if obj is None:
        return None
    card_def = obj.card_def
    if card_def is not None:
        cat = getattr(card_def, "cats_category", None)
        if cat in CATS_CATEGORIES:
            return cat
    return None


def _dispatch_interceptors(
    state: GameState,
    event: Event,
    priorities: tuple[InterceptorPriority, ...] = (InterceptorPriority.TRANSFORM, InterceptorPriority.REACT),
) -> tuple[Event, list[Event]]:
    """Lightweight in-process dispatcher.

    Walks state.interceptors, applies those matching ``event``, in priority order.
    Returns (possibly-transformed event, list of REACT-emitted follow-up events).

    This is intentionally tiny — it covers the CATS_QUERY_PILE_SCORE / CATS_TRICK_RULE_QUERY
    paths without dragging in the full pipeline. The TurnManager will route through the
    real pipeline when it's wired; until then, this lets card interceptors fire under
    the smoke driver too.
    """
    new_events: list[Event] = []
    current_event = event
    for priority in priorities:
        for ic in list(state.interceptors.values()):
            if ic.priority != priority:
                continue
            try:
                if not ic.filter(current_event, state):
                    continue
            except Exception:
                continue
            try:
                result = ic.handler(current_event, state)
            except Exception:
                continue
            if not isinstance(result, InterceptorResult):
                if isinstance(result, list):
                    new_events.extend(result)
                continue
            if result.action == InterceptorAction.TRANSFORM and result.transformed_event is not None:
                current_event = result.transformed_event
            elif result.action == InterceptorAction.REPLACE and result.transformed_event is not None:
                current_event = result.transformed_event
            elif result.action == InterceptorAction.REACT:
                new_events.extend(result.new_events)
            elif result.action == InterceptorAction.PREVENT:
                return current_event, new_events
    return current_event, new_events


def _run_setup_on_pile_entry(state: GameState, obj: GameObject) -> None:
    """Run setup_interceptors for a card that just entered a pile.

    Pile triggers (on_enter_pile, pile-tap activations) need their interceptors
    registered when the card lands. Mirrors how setup_interceptors fires for
    Commanders, but scoped to pile entry instead of game start.
    """
    if obj is None or obj.card_def is None:
        return
    fn = obj.card_def.setup_interceptors
    if fn is None:
        return
    try:
        new_interceptors = fn(obj, state) or []
    except Exception:
        return
    for ic in new_interceptors:
        if ic.id in state.interceptors:
            continue
        state.interceptors[ic.id] = ic
        if ic.id not in obj.interceptor_ids:
            obj.interceptor_ids.append(ic.id)


def install_category_rule(state: GameState, pounce_card_obj_id: str) -> None:
    """Set state.cats_current_rule based on the Pounce card's category."""
    _init_cats_state(state)
    category = _category_of(state, pounce_card_obj_id)
    if category and category in CATS_CATEGORY_RULES:
        rule = CATS_CATEGORY_RULES[category]
        state.cats_current_rule = rule
        if state.cats_current_trick is not None:
            state.cats_current_trick["installed_rule"] = rule
    else:
        # Default to Sleek if Pounce card has no category (e.g. a Mood — Moods don't install rules)
        state.cats_current_rule = sleek_rule
        if state.cats_current_trick is not None:
            state.cats_current_trick["installed_rule"] = sleek_rule


def begin_round(state: GameState) -> list[Event]:
    """Start of a new round. Reset trick, fire CATS_ROUND_START."""
    _init_cats_state(state)
    state.cats_current_trick = _empty_trick()
    state.cats_current_rule = None

    if state.cats_lead_player is None:
        pids = _player_ids(state)
        if pids:
            state.cats_lead_player = pids[0]

    events = [Event(
        type=EventType.CATS_ROUND_START,
        payload={"round_number": state.cats_round_number, "lead_player": state.cats_lead_player},
        source=None,
    )]
    return events


def play_card_to_trick(
    state: GameState,
    player_id: str,
    card_obj_id: str,
    role: Optional[str] = None,
) -> list[Event]:
    """Player commits a card to the current trick. role='pounce' or 'counter' (auto-detected if None)."""
    _init_cats_state(state)
    trick = state.cats_current_trick
    if trick is None:
        trick = _empty_trick()
        state.cats_current_trick = trick

    if role is None:
        role = "pounce" if trick.get("pounce_card") is None else "counter"

    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    if card_obj_id in hand.objects:
        hand.objects.remove(card_obj_id)

    obj = state.objects.get(card_obj_id)
    if obj is not None:
        obj.entered_zone_at = state.next_timestamp()

    if role == "pounce":
        trick["pounce_card"] = card_obj_id
        trick["pounce_player"] = player_id
        install_category_rule(state, card_obj_id)
    else:
        trick["counter_card"] = card_obj_id
        trick["counter_player"] = player_id

    if obj is not None and obj.card_def is not None:
        if CardType.CATS_SNACK in getattr(obj.card_def.characteristics, "types", set()):
            trick["snack_forced"] = True

    return [Event(
        type=EventType.CATS_CARD_PLAYED,
        payload={"player": player_id, "card_id": card_obj_id, "role": role},
        source=card_obj_id,
    )]


def resolve_trick(state: GameState) -> list[Event]:
    """Determine winner of the current trick, fire CATS_TRICK_RESOLVE."""
    _init_cats_state(state)
    trick = state.cats_current_trick or {}
    pounce_card = trick.get("pounce_card")
    counter_card = trick.get("counter_card")
    if pounce_card is None or counter_card is None:
        return []

    # Let Mood interceptors REPLACE the rule via CATS_TRICK_RULE_QUERY.
    base_rule = trick.get("installed_rule") or state.cats_current_rule or sleek_rule
    query = Event(
        type=EventType.CATS_TRICK_RULE_QUERY,
        payload={"rule": base_rule, "pounce_card": pounce_card, "counter_card": counter_card},
        source=None,
    )
    transformed, _ = _dispatch_interceptors(state, query, priorities=(InterceptorPriority.TRANSFORM,))
    rule = transformed.payload.get("rule", base_rule) if transformed else base_rule
    if not callable(rule):
        rule = base_rule

    try:
        winner_id = rule(pounce_card, counter_card, state)
    except Exception:
        winner_id = sleek_rule(pounce_card, counter_card, state)

    trick["winner"] = winner_id
    pp = trick.get("pounce_player")
    cp = trick.get("counter_player")
    loser_id = pp if winner_id == cp else cp

    winning_cards = []
    losing_cards = []
    if winner_id == pp:
        winning_cards = [pounce_card]
        losing_cards = [counter_card]
    else:
        winning_cards = [counter_card]
        losing_cards = [pounce_card]

    events = [
        Event(
            type=EventType.CATS_TRICK_RESOLVE,
            payload={
                "winner": winner_id,
                "loser": loser_id,
                "winning_cards": winning_cards,
                "losing_cards": losing_cards,
                "cards": [pounce_card, counter_card],
            },
            source=None,
        )
    ]
    for cid in winning_cards:
        events.append(Event(
            type=EventType.CATS_TRICK_RESOLVE,
            payload={"phase": "on_win", "card_id": cid, "winner": winner_id},
            source=cid,
        ))
    for cid in losing_cards:
        events.append(Event(
            type=EventType.CATS_TRICK_RESOLVE,
            payload={"phase": "on_lose", "card_id": cid, "winner": winner_id},
            source=cid,
        ))
    return events


def _pile_is_full(state: GameState, player_id: str, pile_name: str) -> bool:
    piles = state.cats_piles.get(player_id, {})
    cap = CATS_PILE_CAPS.get(pile_name, 999)
    return len(piles.get(pile_name, [])) >= cap


def claim_pile(state: GameState, winner_id: str, target_pile: str) -> list[Event]:
    """Move trick cards to target pile (with Snack-force + cap overflow to attention)."""
    _init_cats_state(state)
    trick = state.cats_current_trick or {}
    cards = [c for c in (trick.get("pounce_card"), trick.get("counter_card")) if c]
    if not cards:
        return []

    if trick.get("snack_forced") and target_pile != "pile_snack":
        target_pile = "pile_snack"
    if target_pile not in PILE_NAME_TO_ZONE:
        target_pile = "pile_attention"
    if _pile_is_full(state, winner_id, target_pile) and target_pile != "pile_attention":
        target_pile = "pile_attention"

    events: list[Event] = []
    piles = state.cats_piles.setdefault(winner_id, {
        "pile_territory": [], "pile_nap": [], "pile_snack": [], "pile_attention": [],
    })
    target_zone = _ensure_zone(state, PILE_NAME_TO_ZONE[target_pile], winner_id)
    for cid in cards:
        piles[target_pile].append(cid)
        target_zone.objects.append(cid)
        obj = state.objects.get(cid)
        if obj is not None:
            obj.controller = winner_id
            obj.zone = PILE_NAME_TO_ZONE[target_pile]
            obj.entered_zone_at = state.next_timestamp()
            obj.state.tapped = False  # untapped on entry
            _run_setup_on_pile_entry(state, obj)
        events.append(Event(
            type=EventType.CATS_CLAIM_PILE,
            payload={"player": winner_id, "pile": target_pile, "card_id": cid},
            source=cid,
        ))
        # Fan out so on_enter_pile filters on a per-card payload too.
        events.append(Event(
            type=EventType.CATS_CLAIM_PILE,
            payload={"phase": "on_enter_pile", "player": winner_id, "pile": target_pile, "card_id": cid},
            source=cid,
        ))
        _, reactions = _dispatch_interceptors(
            state,
            events[-1],
            priorities=(InterceptorPriority.REACT,),
        )
        events.extend(reactions)

    cap = CATS_PILE_CAPS.get(target_pile, 999)
    if len(piles[target_pile]) >= cap and target_pile != "pile_attention":
        events.append(Event(
            type=EventType.CATS_PILE_CAPPED,
            payload={"player": winner_id, "pile": target_pile},
            source=None,
        ))

    state.cats_current_trick = _empty_trick()
    return events


def _refill_hand_if_empty(state: GameState, player_id: str) -> None:
    """If a player's hand is empty, refill from library (or reshuffle discard if library empty)."""
    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    if hand.objects:
        return
    library = _ensure_zone(state, ZoneType.LIBRARY, player_id)
    discard = _ensure_zone(state, ZoneType.GRAVEYARD, player_id)
    if not library.objects and discard.objects:
        if state.rng_seed is not None:
            rng = random.Random(state.rng_seed + state.cats_round_number)
        else:
            rng = random
        recycled = list(discard.objects)
        rng.shuffle(recycled)
        for cid in recycled:
            obj = state.objects.get(cid)
            if obj is not None:
                obj.zone = ZoneType.LIBRARY
        library.objects = recycled
        discard.objects = []
    for _ in range(CATS_HAND_SIZE):
        if not library.objects:
            break
        cid = library.objects.pop(0)
        obj = state.objects.get(cid)
        if obj is not None:
            obj.zone = ZoneType.HAND
            obj.entered_zone_at = state.next_timestamp()
        hand.objects.append(cid)


def end_round(state: GameState) -> list[Event]:
    """End-of-round phase. Refill hands if both empty, increment round counter, rotate lead."""
    _init_cats_state(state)
    pids = _player_ids(state)
    all_empty = all(
        not _ensure_zone(state, ZoneType.HAND, pid).objects for pid in pids
    )
    if all_empty:
        for pid in pids:
            _refill_hand_if_empty(state, pid)

    events = [Event(
        type=EventType.CATS_ROUND_END,
        payload={"round_number": state.cats_round_number},
        source=None,
    )]

    state.cats_round_number += 1

    if len(pids) >= 2 and state.cats_lead_player:
        cur_idx = pids.index(state.cats_lead_player) if state.cats_lead_player in pids else 0
        state.cats_lead_player = pids[(cur_idx + 1) % len(pids)]

    state.cats_current_trick = _empty_trick()
    state.cats_current_rule = None
    return events


def check_game_over(state: GameState) -> bool:
    """Return True if round_number has exceeded CATS_TOTAL_ROUNDS."""
    _init_cats_state(state)
    if state.cats_round_number > CATS_TOTAL_ROUNDS:
        return True
    return False


def _query_pile_score(state: GameState, player_id: str, pile_name: str, base_score: int) -> int:
    """Run CATS_QUERY_PILE_SCORE so Trinket interceptors can rewrite a pile's contribution."""
    query = Event(
        type=EventType.CATS_QUERY_PILE_SCORE,
        payload={"player": player_id, "pile": pile_name, "score": base_score},
        source=None,
    )
    transformed, _ = _dispatch_interceptors(state, query, priorities=(InterceptorPriority.TRANSFORM,))
    new_score = transformed.payload.get("score", base_score) if transformed else base_score
    try:
        return int(new_score)
    except (TypeError, ValueError):
        return base_score


def score_cats_player(state: GameState, player_id: str) -> dict[str, int]:
    """Compute final score breakdown for a player.

    Returns {'territory': X, 'nap': Y, 'snack': Z, 'total': T, 'attention': N}.
    Trinket interceptors on CATS_QUERY_PILE_SCORE can rewrite each pile's contribution
    via TRANSFORM-priority handlers.
    """
    _init_cats_state(state)
    piles = state.cats_piles.get(player_id, {})
    trinkets = state.cats_pile_trinkets.get(player_id, {})

    terr_cards = piles.get("pile_territory", [])
    terr_score = len(terr_cards)
    terr_score += 2 * len(trinkets.get("pile_territory", []))
    if len(terr_cards) >= 6:
        terr_score += 5
    terr_score = _query_pile_score(state, player_id, "pile_territory", terr_score)

    nap_cards = piles.get("pile_nap", [])
    nap_score = min(2 * len(nap_cards), 12)
    nap_score = _query_pile_score(state, player_id, "pile_nap", nap_score)

    snack_cards = piles.get("pile_snack", [])
    if len(snack_cards) < 5:
        snack_score = 3 * len(snack_cards)
    else:
        snack_score = len(snack_cards)
    snack_score = _query_pile_score(state, player_id, "pile_snack", snack_score)

    attention_count = len(piles.get("pile_attention", []))
    total = terr_score + nap_score + snack_score
    return {
        "territory": terr_score,
        "nap": nap_score,
        "snack": snack_score,
        "total": total,
        "attention": attention_count,
    }


def finalize_game(state: GameState) -> list[Event]:
    """Compute scores, declare winner(s), emit GAME_END + PLAYER_WINS/LOSES + CATS_GAME_OVER."""
    _init_cats_state(state)
    state.cats_game_over = True
    pids = _player_ids(state)
    scores = {pid: score_cats_player(state, pid) for pid in pids}
    state.cats_final_scores = scores

    if not pids:
        return [Event(
            type=EventType.GAME_END,
            payload={"reason": "day_complete", "scores": {}, "winners": []},
            source=None,
        )]

    max_total = max(s["total"] for s in scores.values())
    leaders = [pid for pid, s in scores.items() if s["total"] == max_total]
    if len(leaders) == 1:
        winners = leaders
    else:
        max_attention = max(scores[pid]["attention"] for pid in leaders)
        attn_winners = [pid for pid in leaders if scores[pid]["attention"] == max_attention]
        winners = attn_winners if len(attn_winners) == 1 else attn_winners

    state.cats_winners = list(winners)

    events: list[Event] = [
        Event(
            type=EventType.CATS_GAME_OVER,
            payload={"scores": scores, "winners": list(winners)},
            source=None,
        ),
    ]
    if len(winners) == 1:
        wp = winners[0]
        winner_player = state.players.get(wp)
        if winner_player is not None:
            winner_player.has_won = True
        for pid in pids:
            if pid != wp:
                losing_player = state.players.get(pid)
                if losing_player is not None:
                    losing_player.has_lost = True
        events.append(Event(
            type=EventType.PLAYER_WINS,
            payload={"player": wp, "scores": scores},
            source=None,
        ))
        for pid in pids:
            if pid != wp:
                events.append(Event(
                    type=EventType.PLAYER_LOSES,
                    payload={"player": pid, "scores": scores},
                    source=None,
                ))
    events.append(Event(
        type=EventType.GAME_END,
        payload={"reason": "day_complete", "scores": scores, "winners": list(winners)},
        source=None,
    ))
    return events


# =============================================================================
# CardDefinition extension helpers (for Stage 4 set authors)
# =============================================================================

def make_cat_card(
    *,
    name: str,
    value: int,
    category: str,
    cost: Optional[str] = None,
    text: str = "",
    rarity: str = "common",
    domain: str = "CATS",
    setup_interceptors: Optional[Callable] = None,
    sneaky_value: Optional[int] = None,
) -> CardDefinition:
    """Build a Cat card. Value 1-10, category in CATS_CATEGORIES."""
    if category not in CATS_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    chars = Characteristics(
        types={CardType.CATS_CAT},
        subtypes={"Cat", category},
        power=value,
        toughness=value,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.cats_value = value
    card_def.cats_category = category
    if category == "Sneaky":
        card_def.cats_sneaky_value = sneaky_value if sneaky_value is not None else value
    return card_def


def make_mood_card(
    *,
    name: str,
    text: str = "",
    rarity: str = "common",
    domain: str = "CATS",
    setup_interceptors: Optional[Callable] = None,
    rule_fn: Optional[Callable] = None,
) -> CardDefinition:
    """Build a Mood card. Value 0 by definition."""
    chars = Characteristics(types={CardType.CATS_MOOD}, subtypes={"Mood"}, power=0, toughness=0)
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.cats_value = 0
    card_def.cats_category = None
    if rule_fn is not None:
        card_def.cats_mood_rule = rule_fn
    return card_def


def make_snack_card(
    *,
    name: str,
    value: int = 1,
    text: str = "",
    rarity: str = "common",
    domain: str = "CATS",
    setup_interceptors: Optional[Callable] = None,
) -> CardDefinition:
    """Build a Snack card. Forces trick into Snack pile."""
    chars = Characteristics(types={CardType.CATS_SNACK}, subtypes={"Snack"}, power=value, toughness=value)
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.cats_value = value
    card_def.cats_category = None
    return card_def


def make_trinket_card(
    *,
    name: str,
    text: str = "",
    rarity: str = "common",
    domain: str = "CATS",
    setup_interceptors: Optional[Callable] = None,
    attaches_to: Optional[str] = None,
) -> CardDefinition:
    """Build a Trinket card. Attaches to a pile when played."""
    chars = Characteristics(types={CardType.CATS_TRINKET}, subtypes={"Trinket"}, power=0, toughness=0)
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.cats_value = 0
    card_def.cats_attaches_to = attaches_to  # e.g. "pile_territory"
    return card_def


def make_commander_card(
    *,
    name: str,
    text: str = "",
    rarity: str = "mythic",
    domain: str = "CATS",
    setup_interceptors: Optional[Callable] = None,
) -> CardDefinition:
    """Build a Commander Cat card. Lives in command zone, always-on passive."""
    chars = Characteristics(types={CardType.CATS_COMMANDER}, subtypes={"Cat", "Commander"}, power=0, toughness=0)
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    return card_def


# =============================================================================
# Mode adapter
# =============================================================================

def _cats_mode_adapter_class():
    """Build the CatsModeAdapter class lazily to dodge the mode_adapter <-> cats import cycle."""
    from src.engine.mode_adapter import GameModeAdapter

    class CatsModeAdapter(GameModeAdapter):
        """Mode adapter for the Cats engine.

        Most defaults inherit MTG; Cats overrides only what differs:
          - no mana
          - no hand-size cap (default None already)
          - empty-library does NOT lose the game (deck recycles from discard)
        """

        mode = "cats"

        def overdraw_burns(self, state) -> bool:
            return False

        def handle_empty_library_draw(self, player, state):
            """Cats decks recycle from discard on empty — never auto-lose."""
            return []

    return CatsModeAdapter


def CatsModeAdapter(*args, **kwargs):
    """Public constructor — produces a CatsModeAdapter instance via the lazy class builder."""
    cls = _cats_mode_adapter_class()
    return cls(*args, **kwargs)
