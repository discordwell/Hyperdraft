"""
Variant tournament harness — discover a format's meta by running named
AI variants in a round-robin against each other.

Use this when porting the spice-pass methodology to a new engine:
before trusting capability scores, run a variant tournament to find
out what playing the format actually rewards. Then tune the AI to
lean into the winning variant, THEN run capability tests.

Usage:
    # Minecraft
    python scripts/play/variant_tournament.py --engine minecraft \
        --variants balanced,aggro,ramp,explore,workers,random,largest \
        --decks builder,miner,raider --games 6 \
        --out logs/mc_variants.json

    # MTG (uses existing aggro/control/midrange/ultra strategies)
    python scripts/play/variant_tournament.py --engine mtg \
        --variants aggro,control,midrange,ultra \
        --decks MONO_RED_AGGRO,MONO_BLUE_CONTROL,MONO_GREEN_RAMP \
        --games 6 --out logs/mtg_variants.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Engine dispatch
# ---------------------------------------------------------------------------


@dataclass
class GameOutcome:
    p1_variant: str
    p2_variant: str
    p1_deck_label: str
    p2_deck_label: str
    winner_variant: Optional[str]  # "p1_variant" or "p2_variant" or None
    turns: int
    duration_s: float
    error: Optional[str] = None


# Engine adapters: (deck_resolver, variant_runner, default_decks, default_variants)
# Each engine plugs in its game runner and variant universe.

def _mc_decks(deck_names: list[str]) -> dict[str, list]:
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS
    out = {}
    for name in deck_names:
        factory = MINECRAFT_STARTER_DECKS.get(name)
        if not factory:
            raise ValueError(f"Unknown MC deck: {name!r}. "
                             f"Available: {list(MINECRAFT_STARTER_DECKS.keys())}")
        out[name] = factory()
    return out


async def _mc_run_one(
    deck1: list, deck2: list,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
) -> GameOutcome:
    from scripts.play.minecraft_capability_test import play_one_minecraft_game
    start = time.perf_counter()
    r = await play_one_minecraft_game(
        deck1, deck2, p1_label=p1_variant, p2_label=p2_variant,
        bias_p1=p1_variant, bias_p2=p2_variant,
        max_turns=max_turns,
    )
    return GameOutcome(
        p1_variant=p1_variant,
        p2_variant=p2_variant,
        p1_deck_label=p1_label,
        p2_deck_label=p2_label,
        winner_variant=r.winner_label,
        turns=r.turns,
        duration_s=r.duration_s,
        error=r.error,
    )


def _mtg_decks(deck_names: list[str]) -> dict[str, list]:
    from src.decks import standard_decks as sd
    from src.decks.deck import load_deck
    from src.cards import ALL_CARDS
    out = {}
    for name in deck_names:
        deck_obj = getattr(sd, name, None)
        if deck_obj is None:
            available = [n for n in dir(sd) if not n.startswith("_") and n.isupper()]
            raise ValueError(f"Unknown MTG deck: {name!r}. Available: {available[:10]}...")
        out[name] = load_deck(ALL_CARDS, deck_obj)
    return out


async def _mtg_run_one(
    deck1: list, deck2: list,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
) -> GameOutcome:
    from scripts.play.custom_set_tournament import play_one_game, make_ai
    ai1 = make_ai(p1_variant)
    ai2 = make_ai(p2_variant)
    start = time.perf_counter()
    r = await play_one_game(
        deck1, deck2, ai1, ai2,
        p1_label=p1_variant, p2_label=p2_variant,
        max_turns=max_turns,
    )
    return GameOutcome(
        p1_variant=p1_variant,
        p2_variant=p2_variant,
        p1_deck_label=p1_label,
        p2_deck_label=p2_label,
        winner_variant=r.winner_domain,
        turns=r.turns,
        duration_s=r.duration_s,
        error=r.error,
    )


ENGINES: dict[str, dict] = {
    "minecraft": {
        "deck_resolver": _mc_decks,
        "run_one": _mc_run_one,
        "default_decks": ["builder", "miner", "raider"],
        "default_variants": ["balanced", "aggro", "ramp", "explore", "workers", "random", "largest"],
        "default_max_turns": 30,
    },
    "mtg": {
        "deck_resolver": _mtg_decks,
        "run_one": _mtg_run_one,
        "default_decks": ["MONO_RED_AGGRO", "DIMIR_CONTROL", "MONO_GREEN_RAMP", "BOROS_AGGRO"],
        "default_variants": ["aggro", "control", "midrange"],
        "default_max_turns": 20,
    },
}


# ---------------------------------------------------------------------------
# Tournament loop
# ---------------------------------------------------------------------------


async def run_variant_tournament(
    engine: str,
    deck_pool: dict[str, list],
    variants: list[str],
    games_per_pair_per_deck: int = 4,
    max_turns: Optional[int] = None,
    verbose: bool = True,
) -> list[GameOutcome]:
    """
    Round-robin: every variant pair plays N games on every deck pair
    (synergy-against-itself eliminated; deck pair = one deck per seat).

    Pair list: for variants V and decks D, pairings = C(|V|, 2) * |D|^2 * N.
    To keep cost down, default sweep is variants pairs * decks (each
    deck with same deck on both sides) * N games.
    """
    cfg = ENGINES.get(engine)
    if not cfg:
        raise ValueError(f"Unknown engine: {engine!r}. Available: {list(ENGINES)}")
    run_one = cfg["run_one"]
    if max_turns is None:
        max_turns = cfg["default_max_turns"]

    deck_labels = list(deck_pool.keys())
    pairings: list[tuple[str, str, str, str]] = []

    # All variant pairs (i < j), each deck combination, alternating seats
    # so first-player advantage cancels.
    for i, v1 in enumerate(variants):
        for v2 in variants[i + 1:]:
            for deck_name in deck_labels:
                deck = deck_pool[deck_name]
                for g in range(games_per_pair_per_deck):
                    if g % 2 == 0:
                        pairings.append((v1, v2, deck_name, deck_name))
                    else:
                        pairings.append((v2, v1, deck_name, deck_name))

    if verbose:
        print(f"\n=== Variant tournament: {engine} ===", flush=True)
        print(f"  variants ({len(variants)}): {', '.join(variants)}", flush=True)
        print(f"  decks ({len(deck_labels)}): {', '.join(deck_labels)}", flush=True)
        print(f"  games per pair per deck: {games_per_pair_per_deck}", flush=True)
        print(f"  total games: {len(pairings)}", flush=True)
        print(f"  max_turns: {max_turns}", flush=True)

    started = time.perf_counter()
    outcomes: list[GameOutcome] = []
    for i, (v1, v2, d1_label, d2_label) in enumerate(pairings):
        deck1 = deck_pool[d1_label]
        deck2 = deck_pool[d2_label]
        try:
            outcome = await run_one(deck1, deck2, v1, v2, d1_label, d2_label, max_turns)
        except Exception as exc:
            outcome = GameOutcome(
                p1_variant=v1, p2_variant=v2,
                p1_deck_label=d1_label, p2_deck_label=d2_label,
                winner_variant=None, turns=0, duration_s=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )
        outcomes.append(outcome)
        if verbose and (i + 1) % max(1, len(pairings) // 10) == 0:
            elapsed = time.perf_counter() - started
            pct = (i + 1) * 100 // len(pairings)
            print(f"    {pct:3d}% ({i+1}/{len(pairings)})  elapsed={elapsed:.1f}s",
                  flush=True)

    return outcomes


# ---------------------------------------------------------------------------
# Aggregation + reporting
# ---------------------------------------------------------------------------


def aggregate(outcomes: list[GameOutcome], variants: list[str]) -> dict[str, Any]:
    # Pairwise win matrix: matrix[a][b] = wins when a was a player vs b.
    wins = defaultdict(lambda: defaultdict(int))
    games = defaultdict(lambda: defaultdict(int))
    overall_wins = defaultdict(int)
    overall_games = defaultdict(int)
    error_count = 0
    draw_count = 0

    for o in outcomes:
        if o.error and o.winner_variant is None:
            error_count += 1
        if o.winner_variant is None:
            draw_count += 1
        a, b = o.p1_variant, o.p2_variant
        games[a][b] += 1
        games[b][a] += 1
        overall_games[a] += 1
        overall_games[b] += 1
        if o.winner_variant == a:
            wins[a][b] += 1
            overall_wins[a] += 1
        elif o.winner_variant == b:
            wins[b][a] += 1
            overall_wins[b] += 1

    matrix = {}
    for a in variants:
        matrix[a] = {}
        for b in variants:
            if a == b:
                matrix[a][b] = None
                continue
            n = games[a][b]
            matrix[a][b] = round(wins[a][b] / n, 3) if n else 0.0

    ranking = sorted(
        variants,
        key=lambda v: (overall_wins[v] / overall_games[v]) if overall_games[v] else 0,
        reverse=True,
    )

    return {
        "variants": variants,
        "win_matrix": matrix,
        "ranking": [
            {
                "variant": v,
                "wins": overall_wins[v],
                "games": overall_games[v],
                "winrate": round(overall_wins[v] / overall_games[v], 3) if overall_games[v] else 0.0,
            }
            for v in ranking
        ],
        "totals": {
            "games": len(outcomes),
            "draws": draw_count,
            "errors": error_count,
        },
    }


def render_report(aggregated: dict[str, Any]) -> str:
    variants = aggregated["variants"]
    matrix = aggregated["win_matrix"]
    ranking = aggregated["ranking"]

    lines: list[str] = []
    width = max(8, max(len(v) for v in variants) + 1)
    lines.append("\n" + "=" * 60)
    lines.append("VARIANT TOURNAMENT — WIN MATRIX")
    lines.append("=" * 60)
    header = " " * (width + 1) + "".join(f"{v:>{width}}" for v in variants)
    lines.append(header)
    for a in variants:
        row = f"{a:<{width}} "
        for b in variants:
            cell = matrix[a][b]
            if cell is None:
                row += f"{'--':>{width}}"
            else:
                row += f"{cell:>{width}.2f}"
        lines.append(row)

    lines.append("\n" + "=" * 60)
    lines.append("OVERALL RANKING")
    lines.append("=" * 60)
    lines.append(f"{'Rank':<6}{'Variant':<{width}}{'Winrate':>10}{'W':>6}{'G':>6}")
    for i, entry in enumerate(ranking, 1):
        lines.append(
            f"{i:<6}{entry['variant']:<{width}}"
            f"{entry['winrate']:>10.3f}{entry['wins']:>6}{entry['games']:>6}"
        )

    lines.append("\n" + "=" * 60)
    lines.append("DISCOVERED META")
    lines.append("=" * 60)
    if ranking:
        winner = ranking[0]
        loser = ranking[-1]
        margin = winner["winrate"] - loser["winrate"]
        lines.append(
            f"Best variant: {winner['variant']!r} ({winner['winrate']:.1%} winrate)."
        )
        lines.append(
            f"Worst variant: {loser['variant']!r} ({loser['winrate']:.1%}). "
            f"Margin {margin:.1%}."
        )
        if margin < 0.10:
            lines.append(
                "  Margin under 10% — variants are roughly equal. "
                "Either the format is balanced or the variant set isn't "
                "expressing meaningful strategic differences yet."
            )
        else:
            lines.append(
                f"  Lean further into {winner['variant']!r}: increase its "
                f"key bonuses, or design more cards that reward its plan."
            )

    totals = aggregated["totals"]
    lines.append(
        f"\nTotal games: {totals['games']}   draws: {totals['draws']}   "
        f"errors: {totals['errors']}"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=list(ENGINES.keys()), required=True)
    parser.add_argument("--variants", type=str, default=None,
                        help="Comma-separated variant names. Default: engine's default set.")
    parser.add_argument("--decks", type=str, default=None,
                        help="Comma-separated deck names. Default: engine's default set.")
    parser.add_argument("--games", type=int, default=4,
                        help="Games per variant pair per deck (default 4).")
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    cfg = ENGINES[args.engine]
    variants = (args.variants.split(",") if args.variants
                else list(cfg["default_variants"]))
    deck_names = (args.decks.split(",") if args.decks
                  else list(cfg["default_decks"]))

    deck_pool = cfg["deck_resolver"](deck_names)

    outcomes = asyncio.run(run_variant_tournament(
        args.engine, deck_pool, variants,
        games_per_pair_per_deck=args.games,
        max_turns=args.max_turns,
    ))

    aggregated = aggregate(outcomes, variants)
    print(render_report(aggregated))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({
                "engine": args.engine,
                "variants": variants,
                "decks": deck_names,
                "games_per_pair_per_deck": args.games,
                "outcomes": [o.__dict__ for o in outcomes],
                "aggregated": aggregated,
            }, fh, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    _cli()
