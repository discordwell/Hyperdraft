"""CATS — Archetype-deck tests.

Verifies the 4 tournament archetype decks defined in
`src.cards.cats.CATS.decks` are well-formed, playable, and that the
tournament runner in `scripts.play.cats_tournament` produces a result dict.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make repo root importable for the scripts/play module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.cards.cats.CATS.decks import CATS_DECKS
from src.cards.cats.CATS import COMMANDERS as ALL_COMMANDERS
from src.engine.cats import (
    CATS_TOTAL_ROUNDS,
    check_game_over,
    finalize_game,
    setup_cats_player,
)
from src.engine.types import CardType, GameState, Player
from src.ai.cats_adapter import CatsAIAdapter


# ---------------------------------------------------------------------------
# Test 1 — All 4 decks are legal: 30 cards, 1 commander, no banned cards.
# ---------------------------------------------------------------------------

def test_all_decks_legal():
    """Each of the 4 decks is a (commander, list[30 CardDefinition]) tuple."""
    assert len(CATS_DECKS) == 4, f"expected 4 decks, got {len(CATS_DECKS)}"

    expected_names = {"Couch Empire", "Naptime Tyrants", "Snack Rush", "Shadow Cats"}
    assert set(CATS_DECKS.keys()) == expected_names

    commander_names = {c.name for c in ALL_COMMANDERS}

    for name, (commander, deck) in CATS_DECKS.items():
        # Commander must be one of the 6 pre-game commanders.
        assert commander is not None, f"{name}: commander is None"
        assert commander.name in commander_names, (
            f"{name}: commander {commander.name!r} not in known commanders"
        )
        assert CardType.CATS_COMMANDER in commander.characteristics.types, (
            f"{name}: commander missing CATS_COMMANDER type"
        )

        # Deck must be exactly 30 cards.
        assert isinstance(deck, list), f"{name}: deck not a list"
        assert len(deck) == 30, f"{name}: expected 30 cards, got {len(deck)}"

        # No banned cards (Commanders may not appear in deck list — they live in command zone).
        for cd in deck:
            assert CardType.CATS_COMMANDER not in cd.characteristics.types, (
                f"{name}: commander card {cd.name!r} found in deck list "
                f"(commanders must be passed via the commander slot only)"
            )


# ---------------------------------------------------------------------------
# Test 2 — Each deck plays a complete game without crashing.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("deck_name", list(CATS_DECKS.keys()))
def test_deck_plays_complete_game(deck_name: str):
    """The named deck can play a full 9-round game vs itself, no crash."""
    commander, deck = CATS_DECKS[deck_name]

    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = 123 + hash(deck_name) % 1000
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    setup_cats_player(state, "p1", list(deck), commander=commander)
    setup_cats_player(state, "p2", list(deck), commander=commander)

    ai_p1 = CatsAIAdapter("medium"); ai_p1.player_id = "p1"
    ai_p2 = CatsAIAdapter("medium"); ai_p2.player_id = "p2"

    # Use the tournament's round driver (extracted helper).
    from scripts.play.cats_tournament import _run_one_round_manual

    rounds_played = 0
    max_rounds = CATS_TOTAL_ROUNDS * 3
    while not check_game_over(state) and rounds_played < max_rounds:
        ok = _run_one_round_manual(state, ai_p1, ai_p2)
        rounds_played += 1
        if not ok:
            break

    assert rounds_played > 0, f"{deck_name}: no rounds played"
    finalize_game(state)
    assert state.cats_game_over, f"{deck_name}: game_over not set"
    assert len(state.cats_final_scores) == 2, (
        f"{deck_name}: expected 2 final scores, got {len(state.cats_final_scores)}"
    )


# ---------------------------------------------------------------------------
# Test 3 — The tournament runner exists and produces a result dict.
# ---------------------------------------------------------------------------

def test_tournament_runner_produces_results():
    """run_tournament() returns a dict of {(a,b): match_dict} with sane shape."""
    from scripts.play.cats_tournament import run_tournament

    # 1 game per pairing — fast smoke run.
    results = run_tournament(games_per_pairing=1)

    deck_names = list(CATS_DECKS.keys())
    n = len(deck_names)
    expected_pairings = n * (n - 1) // 2
    assert len(results) == expected_pairings, (
        f"expected {expected_pairings} pairings, got {len(results)}"
    )

    for (a, b), match in results.items():
        assert a in CATS_DECKS and b in CATS_DECKS
        assert a in match and b in match and "ties" in match
        games = match[a] + match[b] + match["ties"]
        assert games == 1, f"pairing {a} vs {b} expected 1 game, got {games}"
