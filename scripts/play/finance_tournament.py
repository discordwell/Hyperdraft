"""
Finance TCG — archetype tournament runner.

Runs all FINA archetype matchups (6 pairs × N games), tracks per-card and
per-archetype stats, then writes a tournament JSON compatible with
scripts/new_set/balance_loop.py.

Usage:
    python -m scripts.play.finance_tournament \\
        --games 10 --out logs/fina_round_1.json

JSON output shape (same contract as custom_set_tournament.py):
    {
      "card_scores": {
        "FINA_high_frequency::Speed Trade": {
          "games": 10, "deck_copies": 20, "cast": 8,
          "cast_per_copy": 0.4, "in_play_at_end": 3, "win_rate_in_play": 0.67
        }, ...
      },
      "set_summary": {
        "FINA_high_frequency": {"winrate": 0.55, "games": 30},
        ...
      }
    }
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.game import Game                                    # noqa: E402
from src.engine.finance import setup_finance_player                 # noqa: E402
from src.engine.finance_turn import FinanceTurnManager             # noqa: E402
from src.engine.finance_combat import FinanceCombatManager         # noqa: E402
from src.engine.types import ZoneType                               # noqa: E402
from src.ai.finance_adapter import FinanceAIAdapter                 # noqa: E402
from src.cards.finance.fina.decks import (                         # noqa: E402
    build_high_frequency_deck,
    build_derivatives_deck,
    build_quant_deck,
    build_dark_arbitrage_deck,
    FINA_STARTER_DECKS,
)

MAX_TURNS = 60

ARCHETYPES = {
    "FINA_high_frequency": build_high_frequency_deck,
    "FINA_derivatives":    build_derivatives_deck,
    "FINA_quant":          build_quant_deck,
    "FINA_dark_arbitrage": build_dark_arbitrage_deck,
}


# ---------------------------------------------------------------------------
# Card stat tracker
# ---------------------------------------------------------------------------

class CardTracker:
    """Tracks per-card play and win stats across all games."""

    def __init__(self):
        # card_ref → {games, deck_copies, cast, in_play_at_end_wins, in_play_at_end_total}
        self._data: dict[str, dict[str, int]] = defaultdict(lambda: {
            "games": 0, "deck_copies": 0, "cast": 0,
            "in_play_at_end_wins": 0, "in_play_at_end_total": 0,
        })

    def record_deck(self, domain: str, deck: list) -> None:
        for card_def in deck:
            ref = f"{domain}::{card_def.name}"
            self._data[ref]["deck_copies"] += 1

    def record_game_for_deck(self, domain: str, deck: list) -> None:
        for card_def in deck:
            ref = f"{domain}::{card_def.name}"
            self._data[ref]["games"] += 1

    def record_cast(self, domain: str, card_name: str) -> None:
        ref = f"{domain}::{card_name}"
        self._data[ref]["cast"] += 1

    def record_in_play_at_end(self, domain: str, card_name: str, *, won: bool) -> None:
        ref = f"{domain}::{card_name}"
        self._data[ref]["in_play_at_end_total"] += 1
        if won:
            self._data[ref]["in_play_at_end_wins"] += 1

    def to_card_scores(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for ref, d in self._data.items():
            copies = d["deck_copies"] or 1
            games = d["games"] or 1
            cast = d["cast"]
            in_play = d["in_play_at_end_total"]
            in_play_wins = d["in_play_at_end_wins"]
            out[ref] = {
                "games": d["games"],
                "deck_copies": d["deck_copies"],
                "cast": cast,
                "cast_per_copy": round(cast / copies, 3),
                "in_play_at_end": in_play,
                "win_rate_in_play": round(in_play_wins / in_play, 3) if in_play else 0.0,
            }
        return out


# ---------------------------------------------------------------------------
# AI wrapper that records casts
# ---------------------------------------------------------------------------

class TrackingAI:
    """Wraps FinanceAIAdapter to record card plays for stat tracking."""

    def __init__(self, inner: FinanceAIAdapter, domain: str, tracker: CardTracker):
        self.inner = inner
        self.domain = domain
        self.tracker = tracker
        self._name_by_id: dict[str, str] = {}  # obj_id → card name
        self.plays = 0

    def register_deck(self, deck: list) -> None:
        for cd in deck:
            # Pre-register card names so we can look them up by obj_id after play
            self._name_by_id[cd.name] = cd.name  # just name mapping for now

    def notify_card_played(self, card_name: str) -> None:
        self.tracker.record_cast(self.domain, card_name)
        self.plays += 1

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def choose_play_action(self, state, player_id):
        action = self.inner.choose_play_action(state, player_id)
        if action and action.get("type") == "play_card":
            card_id = action.get("card_id")
            # Try to resolve the card name from hand
            if card_id:
                for zone_obj in state.zones.get(player_id, {}).get(ZoneType.HAND, []):
                    if hasattr(zone_obj, "id") and zone_obj.id == card_id:
                        card_name = getattr(zone_obj, "name", None)
                        if card_name:
                            self.notify_card_played(card_name)
                        break
        return action

    def choose_attackers(self, state, player_id):
        return self.inner.choose_attackers(state, player_id)

    def choose_blockers(self, state, attacker_ids, player_id):
        return self.inner.choose_blockers(state, attacker_ids, player_id)

    def choose_discard(self, state, player_id, hand):
        return self.inner.choose_discard(state, player_id, hand)

    def mulligan_decision(self, state, player_id, hand=None):
        return self.inner.mulligan_decision(state, player_id, hand or [])


# ---------------------------------------------------------------------------
# Single game runner
# ---------------------------------------------------------------------------

async def _run_game(
    domain1: str,
    domain2: str,
    deck1: list,
    deck2: list,
    tracker: CardTracker,
    difficulty: str = "medium",
) -> dict:
    result = {
        "domain1": domain1, "domain2": domain2,
        "winner": None, "turns": 0,
        "crashed": False, "error": None,
    }

    try:
        game = Game(mode="finance")
        p1 = game.add_player(f"P1-{domain1}")
        p2 = game.add_player(f"P2-{domain2}")

        setup_finance_player(game, p1)
        setup_finance_player(game, p2)

        for cd in deck1:
            game.add_card_to_library(p1.id, cd)
        for cd in deck2:
            game.add_card_to_library(p2.id, cd)

        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        tm = FinanceTurnManager(game.state)
        game.turn_manager = tm
        tm.set_turn_order([p1.id, p2.id])

        ai1 = TrackingAI(FinanceAIAdapter(difficulty=difficulty), domain1, tracker)
        ai2 = TrackingAI(FinanceAIAdapter(difficulty=difficulty), domain2, tracker)
        tm.set_ai_handler(p1.id, ai1)
        tm.set_ai_handler(p2.id, ai2)
        tm.ai_players.add(p1.id)
        tm.ai_players.add(p2.id)

        try:
            tm.finance_combat_manager = FinanceCombatManager(game.state, game.pipeline)
        except Exception:
            pass

        turns = 0
        for _ in range(MAX_TURNS):
            if game.is_game_over():
                break
            active_id = p1.id if turns % 2 == 0 else p2.id
            await tm.run_turn(active_id)
            turns += 1

        result["turns"] = turns

        # Determine winner
        if p1.has_lost and not p2.has_lost:
            result["winner"] = domain2
        elif p2.has_lost and not p1.has_lost:
            result["winner"] = domain1
        elif p1.life <= 0 and p2.life > 0:
            result["winner"] = domain2
        elif p2.life <= 0 and p1.life > 0:
            result["winner"] = domain1
        elif p1.life > p2.life:
            result["winner"] = domain1
        else:
            result["winner"] = domain2  # timeout: higher life wins

        winner = result["winner"]

        # Record battlefield at end
        for pid, domain in [(p1.id, domain1), (p2.id, domain2)]:
            won = (domain == winner)
            bf = game.state.zones.get(pid, {}).get(ZoneType.BATTLEFIELD, [])
            for obj in bf:
                name = getattr(obj, "name", None)
                if name:
                    tracker.record_in_play_at_end(domain, name, won=won)

    except Exception as e:
        result["crashed"] = True
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"

    return result


# ---------------------------------------------------------------------------
# Tournament runner
# ---------------------------------------------------------------------------

async def run_tournament(games_per_pair: int = 10, difficulty: str = "medium") -> dict:
    tracker = CardTracker()

    # Record deck compositions
    decks: dict[str, list] = {}
    for domain, builder in ARCHETYPES.items():
        deck = builder()
        decks[domain] = deck
        tracker.record_deck(domain, deck)

    arch_wins: dict[str, int] = defaultdict(int)
    arch_games: dict[str, int] = defaultdict(int)

    arch_list = list(ARCHETYPES.keys())
    matchups = [
        (arch_list[i], arch_list[j])
        for i in range(len(arch_list))
        for j in range(i + 1, len(arch_list))
    ]

    total = len(matchups) * games_per_pair
    done = 0

    for d1, d2 in matchups:
        for g in range(games_per_pair):
            # Alternate who goes first
            if g % 2 == 0:
                first, second = d1, d2
            else:
                first, second = d2, d1

            deck_a = decks[first]
            deck_b = decks[second]

            tracker.record_game_for_deck(first, deck_a)
            tracker.record_game_for_deck(second, deck_b)
            arch_games[first] += 1
            arch_games[second] += 1

            result = await _run_game(
                first, second, deck_a, deck_b, tracker, difficulty
            )
            done += 1
            winner = result.get("winner")
            status = "CRASH" if result["crashed"] else f"T{result['turns']} win={winner}"
            print(f"  [{done}/{total}] {first[:12]} vs {second[:12]} → {status}")

            if winner:
                arch_wins[winner] += 1

    # Build set_summary
    set_summary: dict[str, dict[str, Any]] = {}
    for domain in ARCHETYPES:
        games = arch_games[domain]
        wins = arch_wins[domain]
        set_summary[domain] = {
            "winrate": round(wins / games, 3) if games else 0.0,
            "games": games,
            "games_played": games,
        }

    return {
        "card_scores": tracker.to_card_scores(),
        "set_summary": set_summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="FINA archetype balance tournament")
    parser.add_argument("--games", type=int, default=10, help="games per matchup pair")
    parser.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--out", default="logs/fina_tournament.json")
    args = parser.parse_args()

    print(f"=== FINA Balance Tournament — {args.games} games × 6 pairs ===")
    result = asyncio.run(run_tournament(args.games, args.difficulty))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {out_path}")

    print("\n--- Archetype summary ---")
    for domain, stats in result["set_summary"].items():
        print(f"  {domain}: winrate={stats['winrate']:.1%}  games={stats['games']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
