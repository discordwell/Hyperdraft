"""
Smoke tests for the W4 deck-object tournament shim.

Verifies that `play_one_deck_game` accepts arbitrary `Deck` objects (using
existing `STANDARD_DECKS` so we don't depend on W2 shipping yet), produces a
GameResult with per-card stats, and that `run_deck_tournament` emits the
JSON shape consumed by `aggregate()` / `diff_tournaments.py`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import unittest

from scripts.play.custom_set_tournament import (
    GameResult,
    aggregate,
    play_one_deck_game,
    run_deck_tournament,
)
from src.ai import AIEngine
from src.ai.strategies import AggroStrategy, ControlStrategy
from src.decks.standard_decks import STANDARD_DECKS


class TestDeckTournamentShim(unittest.TestCase):
    """play_one_deck_game + run_deck_tournament integrate cleanly with arbitrary Decks."""

    def setUp(self) -> None:
        # Use existing STANDARD_DECKS so we don't depend on W2.
        self.assertIn("mono_red_aggro", STANDARD_DECKS)
        # Pick a control deck (dimir_control), but fall back to the next
        # available standard deck if it isn't in the registry.
        if "dimir_control" in STANDARD_DECKS:
            self.opp_id = "dimir_control"
        else:
            other = next(k for k in STANDARD_DECKS if k != "mono_red_aggro")
            self.opp_id = other

        self.deck_aggro = STANDARD_DECKS["mono_red_aggro"]
        self.deck_opp = STANDARD_DECKS[self.opp_id]

    def test_play_one_deck_game_returns_result(self) -> None:
        """A single deck-vs-deck game returns GameResult with populated stats."""
        ai1 = AIEngine(strategy=AggroStrategy(), difficulty="easy")
        ai2 = AIEngine(strategy=ControlStrategy(), difficulty="easy")

        result = asyncio.run(
            play_one_deck_game(
                self.deck_aggro,
                self.deck_opp,
                ai1,
                ai2,
                "std_red",
                "std_opp",
                max_turns=12,
                per_turn_timeout_s=2.0,
            )
        )

        self.assertIsInstance(result, GameResult)
        # Labels were stamped through the legacy field names (JSON compat).
        self.assertEqual(result.p1_domain, "std_red")
        self.assertEqual(result.p2_domain, "std_opp")
        # Winner is one of the two labels or None (draw / timeout).
        self.assertIn(result.winner_domain, {"std_red", "std_opp", None})
        # Per-card stats keyed by `<label>::<card name>` should not be empty
        # for any non-trivial game (60-card decks, 12 turns).
        # If the game errored we still want a useful failure message.
        self.assertIsInstance(result.card_stats, dict)
        # In a successful run there will be deck_copies entries for every
        # unique card. We require at least one card on each side to have a
        # non-zero deck_copies so the prefix logic worked for both labels.
        if result.error is None:
            self.assertGreater(len(result.card_stats), 0)
            p1_keys = [k for k in result.card_stats if k.startswith("std_red::")]
            p2_keys = [k for k in result.card_stats if k.startswith("std_opp::")]
            self.assertGreater(len(p1_keys), 0, "p1 label prefix not used")
            self.assertGreater(len(p2_keys), 0, "p2 label prefix not used")

    def test_run_deck_tournament_emits_legacy_json_shape(self) -> None:
        """The tournament runner JSON shape stays compatible with aggregate()."""
        deck_pool = {
            "std_red": self.deck_aggro,
            "std_opp": self.deck_opp,
        }
        out = run_deck_tournament(
            deck_pool,
            games_per_pair=1,
            max_turns=10,
            difficulty="easy",
            hard_timeout_s=12.0,
            ai_pair="midrange",
            verbose=False,
        )

        # Required top-level keys consumed by aggregate() / diff_tournaments.
        for key in ("domains", "games_per_pair", "max_turns", "deck_info", "results"):
            self.assertIn(key, out, f"missing key '{key}' in tournament output")
        self.assertEqual(set(out["domains"]), {"std_red", "std_opp"})
        self.assertEqual(out["games_per_pair"], 1)

        # Per-result records use the legacy domain field names.
        self.assertEqual(len(out["results"]), 1)
        rec = out["results"][0]
        for key in ("p1_domain", "p2_domain", "winner_domain", "card_stats"):
            self.assertIn(key, rec, f"per-game record missing '{key}'")

        # aggregate() must accept the output without raising.
        agg = aggregate(out)
        self.assertIn("set_summary", agg)
        self.assertIn("card_scores", agg)
        # set_summary keyed by deck label — both decks must show up.
        self.assertEqual(set(agg["set_summary"].keys()), {"std_red", "std_opp"})


if __name__ == "__main__":
    unittest.main()
