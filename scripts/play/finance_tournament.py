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

async def run_tournament(
    games_per_pair: int = 10,
    difficulty: str = "medium",
    archetypes: dict | None = None,
) -> dict:
    tracker = CardTracker()

    arch_dict = archetypes if archetypes is not None else ARCHETYPES

    # Record deck compositions
    decks: dict[str, list] = {}
    for domain, builder in arch_dict.items():
        deck = builder()
        decks[domain] = deck
        tracker.record_deck(domain, deck)

    arch_wins: dict[str, int] = defaultdict(int)
    arch_games: dict[str, int] = defaultdict(int)
    # Per-pair tracking: pair_wins[d1][d2] = number of games d1 beat d2
    pair_wins: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pair_games: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    arch_list = list(arch_dict.keys())
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

            # Per-pair track (canonical pair = sorted tuple but use d1,d2)
            pair_games[d1][d2] += 1
            pair_games[d2][d1] += 1
            if winner:
                arch_wins[winner] += 1
                if winner == d1:
                    pair_wins[d1][d2] += 1
                elif winner == d2:
                    pair_wins[d2][d1] += 1

    # Build set_summary
    set_summary: dict[str, dict[str, Any]] = {}
    for domain in arch_dict:
        games = arch_games[domain]
        wins = arch_wins[domain]
        set_summary[domain] = {
            "winrate": round(wins / games, 3) if games else 0.0,
            "games": games,
            "games_played": games,
        }

    # Build matchup table: matchup_table[d1][d2] = d1's winrate vs d2 (None on diagonal)
    matchup_table: dict[str, dict[str, Any]] = {}
    for d1 in arch_dict:
        matchup_table[d1] = {}
        for d2 in arch_dict:
            if d1 == d2:
                matchup_table[d1][d2] = None
                continue
            n = pair_games[d1][d2]
            matchup_table[d1][d2] = round(pair_wins[d1][d2] / n, 3) if n else 0.0

    return {
        "card_scores": tracker.to_card_scores(),
        "set_summary": set_summary,
        "matchup_table": matchup_table,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_custom_decks(path: str) -> dict[str, dict[str, Any]]:
    """Load custom decks JSON. Returns {name: {"rationale": str, "cards": list[str]}}."""
    from src.cards.finance import FINANCE_CARDS
    with open(path) as fh:
        payload = json.load(fh)
    decks = payload.get("decks") or {}
    out: dict[str, dict[str, Any]] = {}
    for name, spec in decks.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("cards"), list):
            raise ValueError(f"Deck {name!r} missing 'cards' list")
        cards = list(spec["cards"])
        if len(cards) != 40:
            raise ValueError(f"Deck {name!r} has {len(cards)} cards, expected 40")
        bad = [c for c in cards if c not in FINANCE_CARDS]
        if bad:
            raise ValueError(f"Deck {name!r} has unknown cards: {bad}")
        out[name] = {"rationale": spec.get("rationale", ""), "cards": cards}
    return out


def _make_custom_builder(card_names: list[str]):
    """Return a builder lambda producing a fresh CardDefinition list each call."""
    def builder():
        from src.cards.finance import FINANCE_CARDS
        return [FINANCE_CARDS[c] for c in card_names]
    return builder


def main() -> int:
    parser = argparse.ArgumentParser(description="FINA archetype balance tournament")
    parser.add_argument("--games", type=int, default=10, help="games per matchup pair")
    parser.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--out", default="logs/fina_tournament.json")
    parser.add_argument("--include-candidates", action="store_true",
                        help="Include FINA_CANDIDATE_DECKS in the tournament alongside starters")
    parser.add_argument("--decks-file", type=str, default=None,
                        help="JSON file with extra named decks (each must have 40 cards from FINANCE_CARDS)")
    parser.add_argument("--decks", type=str, default=None,
                        help="Comma-separated deck names. Restricts the tournament matrix to these names. "
                             "Names may refer to starters (FINA_high_frequency, etc.) or custom decks "
                             "loaded via --decks-file. Default: run all known decks.")
    args = parser.parse_args()

    archetypes: dict[str, Any] = dict(ARCHETYPES)

    if args.include_candidates:
        from src.cards.finance.fina.decks import FINA_CANDIDATE_DECKS
        archetypes.update(FINA_CANDIDATE_DECKS)

    custom_rationales: dict[str, str] = {}
    if args.decks_file:
        custom = _load_custom_decks(args.decks_file)
        print(f"\n=== Loaded {len(custom)} custom decks from {args.decks_file} ===")
        for name, spec in custom.items():
            archetypes[name] = _make_custom_builder(spec["cards"])
            custom_rationales[name] = spec["rationale"]
            print(f"  {name}: {spec['rationale']}")
        print()

    if args.decks:
        wanted = [n.strip() for n in args.decks.split(",") if n.strip()]
        unknown = [n for n in wanted if n not in archetypes]
        if unknown:
            print(f"ERROR: unknown deck names: {unknown}")
            print(f"Known: {list(archetypes.keys())}")
            return 2
        archetypes = {n: archetypes[n] for n in wanted}

    n_pairs = len(archetypes) * (len(archetypes) - 1) // 2
    label = "starters + candidates" if args.include_candidates else "tournament"
    if args.decks_file:
        label = f"custom ({args.decks_file})"
    print(f"=== FINA Balance Tournament — {args.games} games × {n_pairs} pairs ({label}, {len(archetypes)} decks) ===")

    result = asyncio.run(run_tournament(args.games, args.difficulty, archetypes=archetypes))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {out_path}")

    print("\n--- Archetype summary ---")
    sorted_decks = sorted(result["set_summary"].items(),
                          key=lambda kv: -kv[1]["winrate"])
    for domain, stats in sorted_decks:
        print(f"  {domain}: winrate={stats['winrate']:.1%}  games={stats['games']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
