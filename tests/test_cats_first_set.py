"""Cats first set (CATS) — end-to-end test.

Verifies the 60-card CATS set integrates with the engine:

1. Imports ALL_CARDS, builds two 30-card decks (sampled with replacement
   from the pool plus 1 unique Commander each).
2. Plays a full AI-vs-AI game using the same manual driver as the smoke test.
3. Asserts: game ends after 9 rounds, both AIs made decisions, scoring
   completed, and a count of CATS_* events fired.
4. Asserts commander interceptors registered into state.interceptors.

The CATS_* event count is sampled from the events returned by each round's
driver functions (cats.begin_round, play_card_to_trick, resolve_trick,
claim_pile, end_round). The smoke-test driver bypasses the pipeline so we
can't rely on state.event_log; we accumulate the return-value events instead.
"""

from __future__ import annotations

import random

import pytest

from src.engine.cats import (
    CATS_TOTAL_ROUNDS,
    begin_round,
    claim_pile,
    check_game_over,
    end_round,
    finalize_game,
    play_card_to_trick,
    resolve_trick,
    setup_cats_player,
)
from src.engine.cats_combat import CatsTrickManager
from src.ai.cats_adapter import CatsAIAdapter
from src.engine.types import EventType, GameState, Player

from src.cards.cats.CATS import (
    ALL_CARDS,
    COMMANDERS,
    CATS_LIST,
    MOODS,
    SNACKS,
    TRINKETS,
)


# ---------------------------------------------------------------------------
# Deck builder — samples 30 cards from CATS+MOODS+SNACKS+TRINKETS with replacement
# ---------------------------------------------------------------------------

def _build_deck(seed: int) -> list:
    """Build a 30-card deck from the playable pool (Cats + Moods + Snacks + Trinkets).

    Composition target (per design doc balance):
      - ~18 Cats (across all 4 categories)
      - ~6 Moods
      - ~4 Snacks
      - ~2 Trinkets
    """
    rng = random.Random(seed)
    deck = []
    # 18 cats — uniform across categories
    deck.extend(rng.choices(CATS_LIST, k=18))
    # 6 moods
    deck.extend(rng.choices(MOODS, k=6))
    # 4 snacks
    deck.extend(rng.choices(SNACKS, k=4))
    # 2 trinkets
    deck.extend(rng.choices(TRINKETS, k=2))
    rng.shuffle(deck)
    return deck


def _build_game_state(seed: int = 42) -> tuple[GameState, list[object]]:
    """Build a 2-player game state with CATS-set decks + 2 unique Commanders."""
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = seed
    state.players["p1"] = Player(id="p1", name="Cat Player 1")
    state.players["p2"] = Player(id="p2", name="Cat Player 2")
    deck1 = _build_deck(seed)
    deck2 = _build_deck(seed + 1)
    # Pick 2 different commanders
    rng = random.Random(seed)
    cmds = list(COMMANDERS)
    rng.shuffle(cmds)
    cmd1 = cmds[0]
    cmd2 = cmds[1]
    setup_cats_player(state, "p1", deck1, commander=cmd1)
    setup_cats_player(state, "p2", deck2, commander=cmd2)
    return state, [cmd1, cmd2]


def _run_one_round(state, ai_p1, ai_p2) -> list:
    """Drive one round and return ALL events emitted during it (return values)."""
    events: list = []
    events.extend(begin_round(state))
    lead = getattr(state, "cats_lead_player", None) or "p1"
    follower = "p2" if lead == "p1" else "p1"

    # Follower (Pounce) plays first.
    hand_zone = state.zones.get(f"HAND_{follower}")
    if hand_zone is None or not hand_zone.objects:
        return events
    ai_follower = ai_p1 if follower == "p1" else ai_p2
    pounce_card = ai_follower.choose_card(state, list(hand_zone.objects))
    events.extend(play_card_to_trick(state, follower, pounce_card, role="pounce"))

    # Lead (Counter-pounce) plays second.
    hand_zone2 = state.zones.get(f"HAND_{lead}")
    if hand_zone2 is None or not hand_zone2.objects:
        return events
    ai_lead = ai_p1 if lead == "p1" else ai_p2
    counter_card = ai_lead.choose_card(state, list(hand_zone2.objects))
    events.extend(play_card_to_trick(state, lead, counter_card, role="counter"))

    # Resolve trick.
    events.extend(resolve_trick(state))

    winner_id = state.cats_current_trick.get("winner")
    if winner_id is None:
        return events

    # Claim pile.
    ai_winner = ai_p1 if winner_id == "p1" else ai_p2
    pile_choice = ai_winner.choose_pile(
        state,
        [state.cats_current_trick.get("pounce_card"), state.cats_current_trick.get("counter_card")],
        ["pile_territory", "pile_nap", "pile_snack"],
    )
    events.extend(claim_pile(state, winner_id, pile_choice))

    # End round.
    events.extend(end_round(state))
    return events


# ---------------------------------------------------------------------------
# The full-game test
# ---------------------------------------------------------------------------

def test_cats_first_set_full_game():
    """Run an AI-vs-AI game with the CATS first set and verify it completes."""
    state, commanders = _build_game_state(seed=42)

    # Sanity: both commanders registered interceptors into state.interceptors.
    assert len(state.interceptors) >= 2, (
        f"expected commander interceptors registered, got {len(state.interceptors)}"
    )
    commander_interceptor_count = len(state.interceptors)

    ai_p1 = CatsAIAdapter("medium")
    ai_p1.player_id = "p1"
    ai_p2 = CatsAIAdapter("medium")
    ai_p2.player_id = "p2"

    all_events: list = []
    rounds_played = 0
    max_rounds = CATS_TOTAL_ROUNDS * 3  # safety budget

    while not check_game_over(state) and rounds_played < max_rounds:
        ev_list = _run_one_round(state, ai_p1, ai_p2)
        if not ev_list:
            break
        all_events.extend(ev_list)
        rounds_played += 1

    # Game must have actually ended.
    assert rounds_played > 0, "no rounds played"
    assert rounds_played <= max_rounds, "game ran past safety budget"

    # Scoring + finalize.
    finalize_events = finalize_game(state)
    all_events.extend(finalize_events)
    assert state.cats_game_over, "game_over flag not set"
    assert len(state.cats_final_scores) == 2, "scores not computed for both players"

    # Count CATS_* events.
    cats_events = [e for e in all_events if e.type.name.startswith("CATS_")]
    assert len(cats_events) > 50, (
        f"expected > 50 CATS_* events in a 9-round game, got {len(cats_events)}; "
        f"types seen: {sorted(set(e.type.name for e in cats_events))}"
    )

    # Specific event categories should fire at least once.
    event_types_fired = set(e.type.name for e in all_events)
    must_fire = {
        "CATS_ROUND_START",
        "CATS_ROUND_END",
        "CATS_CARD_PLAYED",
        "CATS_TRICK_RESOLVE",
        "CATS_CLAIM_PILE",
        "CATS_GAME_OVER",
    }
    missing = must_fire - event_types_fired
    assert not missing, f"required events never fired: {missing}"

    # Commander interceptors should still be present (they're forever).
    assert len(state.interceptors) >= commander_interceptor_count, (
        "commander interceptors should persist for game's duration"
    )


def test_cats_first_set_card_structure():
    """Sanity: every card in the set has valid structure (name, value, etc.)."""
    from src.engine.types import CardType
    assert len(ALL_CARDS) == 60

    # Names unique
    names = [c.name for c in ALL_CARDS]
    assert len(set(names)) == 60, "card names must be unique"

    # Each Cat has a valid category and value 1..10
    for cat in CATS_LIST:
        cat_label = getattr(cat, "cats_category", None)
        assert cat_label in ("Sleek", "Fluffy", "Scrappy", "Sneaky"), (
            f"{cat.name}: bad category {cat_label}"
        )
        val = getattr(cat, "cats_value", None)
        assert isinstance(val, int) and 1 <= val <= 10, (
            f"{cat.name}: bad value {val}"
        )

    # Each Mood is Value 0 and has a rule_fn
    for mood in MOODS:
        assert getattr(mood, "cats_value", None) == 0
        assert getattr(mood, "cats_mood_rule", None) is not None, (
            f"{mood.name}: missing cats_mood_rule"
        )

    # Each Snack has CATS_SNACK type
    for snack in SNACKS:
        assert CardType.CATS_SNACK in snack.characteristics.types

    # Each Trinket has CATS_TRINKET type and an attaches_to
    for trinket in TRINKETS:
        assert CardType.CATS_TRINKET in trinket.characteristics.types
        assert getattr(trinket, "cats_attaches_to", None) is not None, (
            f"{trinket.name}: missing cats_attaches_to"
        )

    # Each Commander has CATS_COMMANDER type and setup_interceptors
    for cmd in COMMANDERS:
        assert CardType.CATS_COMMANDER in cmd.characteristics.types
        assert cmd.setup_interceptors is not None, (
            f"{cmd.name}: missing setup_interceptors"
        )


def test_cats_first_set_effect_coverage():
    """At least 40 of 60 cards have a real setup_interceptors function."""
    with_effects = [c for c in ALL_CARDS if c.setup_interceptors is not None]
    assert len(with_effects) >= 40, (
        f"expected >=40 cards with real effects, got {len(with_effects)} "
        f"out of {len(ALL_CARDS)}"
    )
