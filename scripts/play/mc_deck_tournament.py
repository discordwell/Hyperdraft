"""
Minecraft TCG deck-on-deck tournament harness.

Sister to scripts/play/variant_tournament.py — that one fixes the deck
and varies the AI bias; this one fixes the AI bias and varies the
deck. Used to test deck construction hypotheses ("does loading up on
Workers actually win?") and to evaluate LLM-designed decks against
benchmarks.

Usage:
    # Built-in starter decks only (builder, miner, raider)
    PYTHONPATH=. python scripts/play/mc_deck_tournament.py \\
        --bias balanced --games 4

    # Mix custom decks (from JSON) with starters
    PYTHONPATH=. python scripts/play/mc_deck_tournament.py \\
        --decks-file logs/mc_decks_v1.json \\
        --decks worker_engine,worker_max,builder,miner,raider \\
        --bias balanced --games 4 --out logs/mc_deck_tourney_v1.json

JSON shape for --decks-file:
    {
      "version": 1,
      "decks": {
        "worker_engine": {
          "rationale": "Load up on Workers (~25% density) ...",
          "cards": ["Steve's Helper", "Steve's Helper", "Bed", ...]
        },
        ...
      }
    }
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DeckGameOutcome:
    p1_deck: str
    p2_deck: str
    bias: str
    winner_deck: Optional[str]
    turns: int
    duration_s: float
    error: Optional[str] = None
    card_stats: dict = field(default_factory=dict)  # populated when --log-interceptor-fires


def _resolve_decks(deck_names: list[str], custom: dict[str, list]) -> dict[str, list]:
    """Resolve deck names → list[CardDefinition], using custom JSON-loaded
    decks first then falling back to MINECRAFT_STARTER_DECKS."""
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS, MINECRAFT_CARDS
    out: dict[str, list] = {}
    for name in deck_names:
        if name in custom:
            cards = []
            for cname in custom[name]:
                if cname not in MINECRAFT_CARDS:
                    raise ValueError(f"Custom deck {name!r} references unknown card {cname!r}")
                cards.append(MINECRAFT_CARDS[cname])
            out[name] = cards
        elif name in MINECRAFT_STARTER_DECKS:
            out[name] = MINECRAFT_STARTER_DECKS[name]()
        else:
            raise ValueError(f"Unknown deck: {name!r}. Custom: {list(custom)}. Starters: {list(MINECRAFT_STARTER_DECKS)}")
    return out


async def _run_one(
    deck1: list, deck2: list,
    p1_label: str, p2_label: str,
    bias: str,
    max_turns: int,
    log_interceptor_fires: bool = False,
) -> DeckGameOutcome:
    from scripts.play.minecraft_capability_test import play_one_minecraft_game
    start = time.perf_counter()
    r = await play_one_minecraft_game(
        deck1, deck2, p1_label=p1_label, p2_label=p2_label,
        bias_p1=bias, bias_p2=bias,
        max_turns=max_turns,
    )
    return DeckGameOutcome(
        p1_deck=p1_label,
        p2_deck=p2_label,
        bias=bias,
        winner_deck=r.winner_label,
        turns=r.turns,
        duration_s=r.duration_s,
        error=r.error,
        card_stats=r.card_stats if log_interceptor_fires else {},
    )


async def run_deck_tournament(
    deck_pool: dict[str, list],
    bias: str = "balanced",
    games_per_pair: int = 4,
    max_turns: int = 30,
    verbose: bool = True,
    log_interceptor_fires: bool = False,
) -> list[DeckGameOutcome]:
    """Round-robin: every deck pair plays N games (alternating seats so
    first-player advantage cancels). Both seats run the same AI bias."""
    deck_labels = list(deck_pool.keys())
    pairings: list[tuple[str, str]] = []
    for i, d1 in enumerate(deck_labels):
        for d2 in deck_labels[i + 1:]:
            for g in range(games_per_pair):
                if g % 2 == 0:
                    pairings.append((d1, d2))
                else:
                    pairings.append((d2, d1))

    if verbose:
        print(f"\n=== Deck tournament ===", flush=True)
        print(f"  decks ({len(deck_labels)}): {', '.join(deck_labels)}", flush=True)
        print(f"  bias (both seats): {bias}", flush=True)
        print(f"  games per pair: {games_per_pair}", flush=True)
        print(f"  total games: {len(pairings)}", flush=True)
        print(f"  max_turns: {max_turns}", flush=True)

    started = time.perf_counter()
    outcomes: list[DeckGameOutcome] = []
    for i, (d1, d2) in enumerate(pairings):
        try:
            outcome = await _run_one(
                deck_pool[d1], deck_pool[d2], d1, d2, bias, max_turns,
                log_interceptor_fires=log_interceptor_fires,
            )
        except Exception as exc:
            outcome = DeckGameOutcome(
                p1_deck=d1, p2_deck=d2, bias=bias,
                winner_deck=None, turns=0, duration_s=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )
        outcomes.append(outcome)
        if verbose and (i + 1) % max(1, len(pairings) // 10) == 0:
            elapsed = time.perf_counter() - started
            pct = (i + 1) * 100 // len(pairings)
            print(f"    {pct:3d}% ({i+1}/{len(pairings)})  elapsed={elapsed:.1f}s",
                  flush=True)
    return outcomes


def _aggregate_card_scores(outcomes: list[DeckGameOutcome]) -> dict[str, dict[str, int]]:
    """Fold per-game card_stats into the card_scores shape for the P5a punchlist.

    Each outcome carries stats keyed by "DECK_LABEL::Card Name". We accumulate:
      - appearances: games the card was in the deck (deck_copies > 0 in that game)
      - plays: total times the card entered play (cast count)
      - wins: games where it appeared AND the deck won
      - losses: games where it appeared AND the deck lost
    """
    agg: dict[str, dict[str, int]] = defaultdict(lambda: {
        "appearances": 0, "plays": 0, "wins": 0, "losses": 0
    })
    for o in outcomes:
        if not o.card_stats:
            continue
        winner = o.winner_deck
        for ref, cs in o.card_stats.items():
            if not cs.get("deck_copies", 0):
                continue
            deck_label = ref.split("::", 1)[0]
            a = agg[ref]
            a["appearances"] += 1
            a["plays"] += int(cs.get("cast", 0))
            if winner is not None and deck_label == winner:
                a["wins"] += 1
            elif winner is not None and deck_label != winner:
                a["losses"] += 1
    return {k: dict(v) for k, v in agg.items()}


def aggregate(outcomes: list[DeckGameOutcome], deck_labels: list[str]) -> dict[str, Any]:
    wins = defaultdict(lambda: defaultdict(int))
    games = defaultdict(lambda: defaultdict(int))
    overall_wins = defaultdict(int)
    overall_games = defaultdict(int)
    error_count = 0
    draw_count = 0

    for o in outcomes:
        if o.error and o.winner_deck is None:
            error_count += 1
        if o.winner_deck is None:
            draw_count += 1
        a, b = o.p1_deck, o.p2_deck
        games[a][b] += 1
        games[b][a] += 1
        overall_games[a] += 1
        overall_games[b] += 1
        if o.winner_deck == a:
            wins[a][b] += 1
            overall_wins[a] += 1
        elif o.winner_deck == b:
            wins[b][a] += 1
            overall_wins[b] += 1

    matrix: dict[str, dict[str, Optional[float]]] = {}
    for a in deck_labels:
        matrix[a] = {}
        for b in deck_labels:
            if a == b:
                matrix[a][b] = None
                continue
            n = games[a][b]
            matrix[a][b] = round(wins[a][b] / n, 3) if n else 0.0

    ranking = sorted(
        deck_labels,
        key=lambda d: (overall_wins[d] / overall_games[d]) if overall_games[d] else 0,
        reverse=True,
    )
    return {
        "decks": deck_labels,
        "win_matrix": matrix,
        "ranking": [
            {
                "deck": d,
                "wins": overall_wins[d],
                "games": overall_games[d],
                "winrate": round(overall_wins[d] / overall_games[d], 3) if overall_games[d] else 0.0,
            }
            for d in ranking
        ],
        "totals": {
            "games": len(outcomes),
            "draws": draw_count,
            "errors": error_count,
        },
    }


def render_report(aggregated: dict[str, Any], bias: str) -> str:
    decks = aggregated["decks"]
    matrix = aggregated["win_matrix"]
    ranking = aggregated["ranking"]

    width = max(8, max(len(d) for d in decks) + 1)
    lines: list[str] = []
    lines.append("\n" + "=" * 60)
    lines.append(f"DECK TOURNAMENT — WIN MATRIX (bias={bias})")
    lines.append("=" * 60)
    header = " " * (width + 1) + "".join(f"{d:>{width}}" for d in decks)
    lines.append(header)
    for a in decks:
        row = f"{a:<{width}} "
        for b in decks:
            cell = matrix[a][b]
            if cell is None:
                row += f"{'--':>{width}}"
            else:
                row += f"{cell:>{width}.2f}"
        lines.append(row)

    lines.append("\n" + "=" * 60)
    lines.append("RANKING")
    lines.append("=" * 60)
    lines.append(f"{'Rank':<6}{'Deck':<{width}}{'Winrate':>10}{'W':>6}{'G':>6}")
    for i, e in enumerate(ranking, 1):
        lines.append(f"{i:<6}{e['deck']:<{width}}{e['winrate']:>10.3f}{e['wins']:>6}{e['games']:>6}")

    lines.append("\n" + "=" * 60)
    lines.append("VERDICT")
    lines.append("=" * 60)
    if ranking:
        winner = ranking[0]
        loser = ranking[-1]
        margin = winner["winrate"] - loser["winrate"]
        lines.append(f"Best: {winner['deck']!r} ({winner['winrate']:.1%} WR)")
        lines.append(f"Worst: {loser['deck']!r} ({loser['winrate']:.1%} WR). Margin {margin:.1%}.")
        if margin < 0.10:
            lines.append("  Margin under 10% — decks are roughly equivalent under this AI bias.")
        else:
            lines.append(f"  Lean toward {winner['deck']!r} construction principles.")

    totals = aggregated["totals"]
    lines.append(f"\nTotal games: {totals['games']}   draws: {totals['draws']}   errors: {totals['errors']}")
    return "\n".join(lines)


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decks", type=str, default=None,
                        help="Comma-separated deck names. Default: builder,miner,raider")
    parser.add_argument("--decks-file", type=str, default=None,
                        help="JSON file with extra named decks")
    parser.add_argument("--bias", type=str, default="balanced",
                        help="AI bias preset for both seats (default balanced)")
    parser.add_argument("--games", type=int, default=4,
                        help="Games per deck pair (default 4)")
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--log-interceptor-fires", action="store_true", default=False,
                        help="Collect per-card telemetry; adds card_scores to output JSON")
    args = parser.parse_args()

    custom: dict[str, list[str]] = {}
    rationales: dict[str, str] = {}
    if args.decks_file:
        with open(args.decks_file) as fh:
            payload = json.load(fh)
        for name, spec in (payload.get("decks") or {}).items():
            if not isinstance(spec, dict) or not isinstance(spec.get("cards"), list):
                raise ValueError(f"Deck {name!r} missing 'cards' list")
            custom[name] = list(spec["cards"])
            rationales[name] = spec.get("rationale", "")

    deck_names = (args.decks.split(",") if args.decks
                  else (list(custom.keys()) + ["builder", "miner", "raider"]
                        if custom
                        else ["builder", "miner", "raider"]))

    deck_pool = _resolve_decks(deck_names, custom)
    if rationales:
        print("\n=== Custom decks loaded ===", flush=True)
        for name in custom:
            if name in deck_names:
                print(f"  {name} ({len(custom[name])} cards): "
                      f"{rationales.get(name, '<no rationale>')}", flush=True)

    outcomes = asyncio.run(run_deck_tournament(
        deck_pool, bias=args.bias,
        games_per_pair=args.games,
        max_turns=args.max_turns,
        log_interceptor_fires=args.log_interceptor_fires,
    ))
    aggregated = aggregate(outcomes, deck_names)
    print(render_report(aggregated, args.bias))

    if args.out:
        payload: dict[str, Any] = {
            "bias": args.bias,
            "decks": deck_names,
            "games_per_pair": args.games,
            # Strip card_stats from individual outcomes to keep output compact
            "outcomes": [{k: v for k, v in o.__dict__.items() if k != "card_stats"}
                         for o in outcomes],
            "aggregated": aggregated,
        }
        if args.log_interceptor_fires:
            payload["card_scores"] = _aggregate_card_scores(outcomes)
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    _cli()
