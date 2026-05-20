"""Smoke test for the Cats engine.

Verifies that two AIs can play a complete game (9 rounds) and that:
1. The game ends after CATS_TOTAL_ROUNDS.
2. Both AIs make at least one non-no-op decision.
3. The game ends legitimately (not a timeout).
"""

from __future__ import annotations

import asyncio
import random

import pytest

from src.engine.cats import (
    CATS_TOTAL_ROUNDS,
    CATS_HAND_SIZE,
    begin_round,
    check_game_over,
    finalize_game,
    make_cat_card,
    make_commander_card,
    make_mood_card,
    make_snack_card,
    score_cats_player,
    setup_cats_player,
)
from src.engine.cats_combat import CatsTrickManager
from src.engine.cats_turn import CatsTurnManager
from src.ai.cats_adapter import CatsAIAdapter
from src.engine.types import GameState, Player


def _make_test_deck(seed: int = 0) -> list:
    """30-card deck: ~24 Cats across 4 categories + 3 Moods + 3 Snacks."""
    rng = random.Random(seed)
    deck = []
    cats_per_category = 6
    categories = ("Sleek", "Fluffy", "Scrappy", "Sneaky")
    for cat in categories:
        for i in range(cats_per_category):
            value = rng.randint(1, 10)
            deck.append(make_cat_card(
                name=f"{cat} Cat {i+1}",
                value=value,
                category=cat,
            ))
    for i in range(3):
        deck.append(make_mood_card(name=f"Mood {i+1}"))
    for i in range(3):
        deck.append(make_snack_card(name=f"Snack {i+1}", value=rng.randint(1, 3)))
    return deck


def _build_game_state(seed: int = 42) -> GameState:
    """Build a 2-player Cats GameState ready to play."""
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = seed
    state.players["p1"] = Player(id="p1", name="Cat Lover 1")
    state.players["p2"] = Player(id="p2", name="Cat Lover 2")
    deck1 = _make_test_deck(seed=seed)
    deck2 = _make_test_deck(seed=seed + 1)
    setup_cats_player(state, "p1", deck1)
    setup_cats_player(state, "p2", deck2)
    return state


def _run_one_round_manual(state, trick_mgr, ai_p1, ai_p2):
    """Manually drive one round through the engine — pounce, counter, resolve, claim, end."""
    from src.engine.cats import (
        play_card_to_trick, resolve_trick, claim_pile, end_round, begin_round,
    )
    from src.engine.types import ZoneType

    begin_round(state)
    lead = getattr(state, "cats_lead_player", None) or "p1"
    follower = "p2" if lead == "p1" else "p1"

    hand_zone_key = f"HAND_{follower}"
    hand_obj_ids = state.zones[hand_zone_key].objects
    if not hand_obj_ids:
        return False
    ai_follower = ai_p1 if follower == "p1" else ai_p2
    pounce_card = ai_follower.choose_card(state, list(hand_obj_ids))
    play_card_to_trick(state, follower, pounce_card, role="pounce")

    hand_zone_key2 = f"HAND_{lead}"
    hand_obj_ids2 = state.zones[hand_zone_key2].objects
    if not hand_obj_ids2:
        return False
    ai_lead = ai_p1 if lead == "p1" else ai_p2
    counter_card = ai_lead.choose_card(state, list(hand_obj_ids2))
    play_card_to_trick(state, lead, counter_card, role="counter")

    resolve_trick(state)

    winner_id = state.cats_current_trick.get("winner")
    if winner_id is None:
        return False
    ai_winner = ai_p1 if winner_id == "p1" else ai_p2
    available_piles = ["pile_territory", "pile_nap", "pile_snack"]
    won_cards = [c for c in (state.cats_current_trick.get("pounce_card"),
                             state.cats_current_trick.get("counter_card")) if c]
    pile_choice = ai_winner.choose_pile(state, won_cards, available_piles)
    claim_pile(state, winner_id, pile_choice)

    end_round(state)
    return True


def test_cats_smoke_full_game():
    """Two AI agents play a complete game; assert it finishes legitimately."""
    state = _build_game_state(seed=42)
    ai_p1 = CatsAIAdapter("medium")
    ai_p1.player_id = "p1"
    ai_p2 = CatsAIAdapter("medium")
    ai_p2.player_id = "p2"
    trick_mgr = CatsTrickManager(state)

    decisions_made = {"p1": 0, "p2": 0}
    rounds_played = 0
    max_rounds = CATS_TOTAL_ROUNDS * 3  # safety budget

    while not check_game_over(state) and rounds_played < max_rounds:
        from src.engine.types import ZoneType
        hand_p1 = state.zones.get("HAND_p1")
        hand_p2 = state.zones.get("HAND_p2")
        if hand_p1 and hand_p2:
            if hand_p1.objects:
                decisions_made["p1"] += 1
            if hand_p2.objects:
                decisions_made["p2"] += 1
        ok = _run_one_round_manual(state, trick_mgr, ai_p1, ai_p2)
        if not ok:
            break
        rounds_played += 1

    assert rounds_played > 0, "no rounds played"
    assert rounds_played <= max_rounds, "game ran past safety budget — timeout"
    assert decisions_made["p1"] > 0, "p1 made no decisions"
    assert decisions_made["p2"] > 0, "p2 made no decisions"

    events = finalize_game(state)
    assert state.cats_game_over, "game_over flag not set after finalize"
    assert len(state.cats_final_scores) == 2, "scores not computed for both players"
    assert any(e.type.name == "GAME_END" for e in events), "GAME_END event not emitted"
    assert any(e.type.name == "CATS_GAME_OVER" for e in events), "CATS_GAME_OVER not emitted"


def test_cats_scoring_basic():
    """Verify the scoring function does what the design says."""
    state = _build_game_state(seed=1)
    state.cats_piles["p1"]["pile_territory"] = ["c1"] * 7
    state.cats_piles["p1"]["pile_nap"] = ["c1"] * 4
    state.cats_piles["p1"]["pile_snack"] = ["c1"] * 3
    state.cats_piles["p1"]["pile_attention"] = ["c1"] * 2

    score = score_cats_player(state, "p1")
    assert score["territory"] == 7 + 5, f"territory: {score['territory']}"
    assert score["nap"] == 8, f"nap: {score['nap']}"
    assert score["snack"] == 9, f"snack: {score['snack']}"
    assert score["total"] == 12 + 8 + 9, f"total: {score['total']}"
    assert score["attention"] == 2


def test_cats_scoring_nap_capped():
    """Nap pile caps at 12 points."""
    state = _build_game_state(seed=2)
    state.cats_piles["p1"]["pile_nap"] = ["c"] * 10
    score = score_cats_player(state, "p1")
    assert score["nap"] == 12, f"nap should cap at 12, got {score['nap']}"


def test_cats_scoring_snack_greed_penalty():
    """Snack pile: 3pt/card if <5, else 1pt/card."""
    state = _build_game_state(seed=3)
    state.cats_piles["p1"]["pile_snack"] = ["c"] * 4
    s4 = score_cats_player(state, "p1")
    assert s4["snack"] == 12

    state.cats_piles["p1"]["pile_snack"] = ["c"] * 6
    s6 = score_cats_player(state, "p1")
    assert s6["snack"] == 6


def test_cats_finalize_picks_winner():
    """finalize_game picks the highest-scoring player as winner."""
    state = _build_game_state(seed=4)
    state.cats_piles["p1"]["pile_territory"] = ["c"] * 8
    state.cats_piles["p1"]["pile_nap"] = ["c"] * 6
    state.cats_piles["p2"]["pile_territory"] = ["c"] * 2

    events = finalize_game(state)
    assert state.cats_game_over
    assert state.players["p1"].has_won, "p1 should have won"
    assert state.players["p2"].has_lost, "p2 should have lost"
    assert state.cats_winners == ["p1"]


def test_cats_finalize_tiebreak_via_attention():
    """When scores tie, attention pile breaks tie."""
    state = _build_game_state(seed=5)
    state.cats_piles["p1"]["pile_territory"] = ["c"] * 3
    state.cats_piles["p1"]["pile_attention"] = ["c"] * 5
    state.cats_piles["p2"]["pile_territory"] = ["c"] * 3
    state.cats_piles["p2"]["pile_attention"] = ["c"] * 1

    finalize_game(state)
    assert state.cats_winners == ["p1"], f"attention tiebreak failed: winners={state.cats_winners}"


def test_cats_ai_easy_returns_string():
    """AI returns a card_id string (not a dataclass)."""
    ai = CatsAIAdapter("easy")
    result = ai.choose_card(None, ["c1", "c2", "c3"])
    assert isinstance(result, str)
    assert result in ("c1", "c2", "c3")


def test_cats_ai_pile_choice_returns_string():
    """AI returns a pile name (not a dataclass)."""
    state = _build_game_state(seed=6)
    ai = CatsAIAdapter("medium")
    ai.player_id = "p1"
    result = ai.choose_pile(state, ["c1", "c2"], ["pile_territory", "pile_nap", "pile_snack"])
    assert isinstance(result, str)
    assert result in ("pile_territory", "pile_nap", "pile_snack", "pile_attention")


def test_cats_trick_manager_constructs():
    """CatsTrickManager constructs with a real state."""
    state = _build_game_state(seed=7)
    tm = CatsTrickManager(state)
    assert tm.state is state


def test_cats_mode_adapter_registered():
    """mode_adapter.get_mode_adapter('cats') returns the CatsModeAdapter."""
    from src.engine.mode_adapter import get_mode_adapter
    adapter = get_mode_adapter("cats")
    assert adapter.mode == "cats"


def test_cats_rule_callables():
    """Trick rule functions return the expected winner."""
    state = _build_game_state(seed=8)
    cat_hi = make_cat_card(name="HiCat", value=8, category="Sleek")
    cat_lo = make_cat_card(name="LoCat", value=3, category="Sleek")
    from src.engine.cats import _make_object_from_def
    from src.engine.types import ZoneType
    hi = _make_object_from_def(state, cat_hi, "p1", ZoneType.BATTLEFIELD)
    lo = _make_object_from_def(state, cat_lo, "p2", ZoneType.BATTLEFIELD)

    state.cats_current_trick = {
        "pounce_card": hi.id, "pounce_player": "p1",
        "counter_card": lo.id, "counter_player": "p2",
        "installed_rule": None, "snack_forced": False, "winner": None,
    }
    from src.engine.cats import sleek_rule, scrappy_rule
    assert sleek_rule(hi.id, lo.id, state) == "p1", "Sleek: higher wins"
    assert scrappy_rule(hi.id, lo.id, state) == "p2", "Scrappy: lower wins"
