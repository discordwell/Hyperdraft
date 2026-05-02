#!/usr/bin/env python3
"""
Deck Tournament — arbitrary-Deck round-robin runner.

Wraps `run_deck_tournament` (scripts/play/custom_set_tournament.py) with a
CLI that resolves `--decks` entries in the form `<label>:<source>:<args>`:

    label    Opaque string used as the JSON key + _card_ref prefix.
    source   One of: hybrid | standard | netdeck | polished
    args     Source-specific colon-delimited arguments.

Sources:

    standard:<deck_id>
        Look up `STANDARD_DECKS[deck_id]` from src/decks/standard_decks.py.

    netdeck:<deck_id>
        Look up `NETDECKS[deck_id]` from src/decks/netdecks.py. The literal
        key is tried first; if not found the same key with `_netdeck` suffix
        is tried (e.g. `dimir_midrange` → `dimir_midrange_netdeck`).

    hybrid:<archetype>:<colors>:<set_codes>
        Build a heuristic deck via `src.decks.heuristics.builder.build_heuristic_deck`.
        `colors` is a string of single-letter color codes (e.g. "WUR").
        `set_codes` is a comma-separated set list (e.g. "FDN,WOE").
        Lazy import — only the entries that use this source pay the import cost.

    polished:<archetype>:<colors>:<set_codes>
        Like `hybrid`, then synchronously polish via the LLM service. Falls
        back to the raw heuristic deck if Ollama is unavailable.

Usage:

    python scripts/play/deck_tournament.py \\
        --decks 'h_aggro:hybrid:Aggro:R:FDN' \\
                'std_red:standard:mono_red_aggro' \\
                'netdeck_dimir:netdeck:dimir_midrange' \\
        --games 5 --out logs/deck_tournament.json

The output JSON shape matches `run_tournament_sequential` exactly so
`scripts/play/diff_tournaments.py` works without modification.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.play.custom_set_tournament import (  # noqa: E402
    aggregate,
    render_tier_report,
    run_deck_tournament,
)


def _resolve_standard(deck_id: str):
    """Resolve a STANDARD_DECKS entry by id."""
    from src.decks.standard_decks import STANDARD_DECKS
    if deck_id not in STANDARD_DECKS:
        available = ", ".join(sorted(STANDARD_DECKS.keys()))
        raise ValueError(
            f"Unknown standard deck '{deck_id}'. Available: {available}"
        )
    return STANDARD_DECKS[deck_id]


def _resolve_netdeck(deck_id: str):
    """Resolve a NETDECKS entry by id, tolerating an implicit `_netdeck` suffix."""
    from src.decks.netdecks import NETDECKS
    if deck_id in NETDECKS:
        return NETDECKS[deck_id]
    suffixed = f"{deck_id}_netdeck"
    if suffixed in NETDECKS:
        return NETDECKS[suffixed]
    available = ", ".join(sorted(NETDECKS.keys())[:8]) + " ..."
    raise ValueError(
        f"Unknown netdeck '{deck_id}' (also tried '{suffixed}'). "
        f"Sample: {available}"
    )


def _resolve_hybrid(label: str, archetype: str, colors_str: str, set_codes_str: str):
    """Build a heuristic deck via build_heuristic_deck (lazy import)."""
    try:
        # Lazy import — W2 owns this module.
        from src.decks.heuristics.builder import build_heuristic_deck
    except Exception as e:  # pragma: no cover - depends on W2 shipping
        raise RuntimeError(
            f"Hybrid source unavailable (build_heuristic_deck not importable): {e}. "
            f"This source requires W2's heuristic builder package."
        ) from e

    colors = [c for c in colors_str.upper() if c in {"W", "U", "B", "R", "G"}]
    set_codes = [s.strip() for s in set_codes_str.split(",") if s.strip()]
    if not colors:
        raise ValueError(f"Hybrid source for '{label}': empty colors '{colors_str}'")
    if not set_codes:
        raise ValueError(f"Hybrid source for '{label}': empty set_codes '{set_codes_str}'")
    return build_heuristic_deck(label, archetype, colors, set_codes)


def _resolve_polished(label: str, archetype: str, colors_str: str, set_codes_str: str):
    """Build then polish a hybrid deck. Falls back to raw skeleton on LLM failure."""
    skeleton = _resolve_hybrid(label, archetype, colors_str, set_codes_str)
    try:
        # Lazy LLM imports; W3 owns polish_deck.
        from src.server.services.llm_deckbuilder import LLMDeckBuilderService
        service = LLMDeckBuilderService()
        if not getattr(service, "is_available", False):
            print(
                f"  [{label}] LLM unavailable; using raw heuristic skeleton.",
                flush=True,
            )
            return skeleton
        polish_fn = getattr(service, "polish_deck", None)
        if polish_fn is None:
            print(
                f"  [{label}] polish_deck not yet implemented; using raw skeleton.",
                flush=True,
            )
            return skeleton
        # polish_deck is async per the W3 spec — run it synchronously.
        import asyncio
        set_codes = [s.strip() for s in set_codes_str.split(",") if s.strip()]
        polished = asyncio.run(polish_fn(skeleton, set_codes=set_codes))
        # Result may be either a dict-shaped payload or a Deck. Prefer the
        # already-typed Deck returned alongside the audit.
        if hasattr(polished, "mainboard"):
            return polished
        if isinstance(polished, dict) and "deck" in polished:
            from src.decks.deck import Deck
            return Deck.from_dict(polished["deck"]) if isinstance(polished["deck"], dict) else polished["deck"]
        return skeleton
    except Exception as e:
        print(f"  [{label}] LLM polish failed ({e}); using raw skeleton.", flush=True)
        return skeleton


def _parse_deck_spec(spec: str):
    """
    Parse '<label>:<source>:<args>' and return (label, Deck).

    Source-specific arg counts:
        standard / netdeck : 1 arg     (deck_id)
        hybrid / polished  : 3 args    (archetype, colors, set_codes)
    """
    parts = spec.split(":")
    if len(parts) < 3:
        raise ValueError(
            f"--decks entry '{spec}' must be '<label>:<source>:<args>' "
            f"(at least 3 colon-delimited parts)"
        )
    label, source = parts[0], parts[1].lower()
    args = parts[2:]

    if source == "standard":
        if len(args) != 1:
            raise ValueError(f"standard source needs 1 arg (deck_id), got {args}")
        return label, _resolve_standard(args[0])

    if source == "netdeck":
        if len(args) != 1:
            raise ValueError(f"netdeck source needs 1 arg (deck_id), got {args}")
        return label, _resolve_netdeck(args[0])

    if source in ("hybrid", "polished"):
        if len(args) != 3:
            raise ValueError(
                f"{source} source needs 3 args (archetype, colors, set_codes), got {args}"
            )
        archetype, colors_str, set_codes_str = args
        if source == "hybrid":
            return label, _resolve_hybrid(label, archetype, colors_str, set_codes_str)
        return label, _resolve_polished(label, archetype, colors_str, set_codes_str)

    raise ValueError(
        f"Unknown source '{source}' in '{spec}'. "
        f"Expected one of: hybrid, standard, netdeck, polished."
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Round-robin tournament over arbitrary Deck objects.",
    )
    parser.add_argument(
        "--decks",
        nargs="+",
        required=True,
        help="Deck specs in the form '<label>:<source>:<args>'.",
    )
    parser.add_argument("--games", type=int, default=5, help="games per pair")
    parser.add_argument("--max-turns", type=int, default=14)
    parser.add_argument("--difficulty", default="hard")
    parser.add_argument(
        "--hard-timeout",
        type=float,
        default=8.0,
        help="SIGALRM hard wall cap per game (seconds)",
    )
    parser.add_argument(
        "--ai",
        default=None,
        help="Single AI strategy name (aggro|control|midrange) for both seats.",
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output JSON path. Includes raw results + aggregate matrix.",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Optional human-readable tier report path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-batch progress output.",
    )
    args = parser.parse_args(argv)

    deck_pool: dict = {}
    for spec in args.decks:
        label, deck = _parse_deck_spec(spec)
        if label in deck_pool:
            raise ValueError(f"Duplicate deck label '{label}'.")
        deck_pool[label] = deck

    n = len(deck_pool)
    n_pairs = n * (n - 1) // 2
    total_games = n_pairs * args.games
    print(
        f"Deck tournament: {n} decks, {n_pairs} pairs, "
        f"{args.games} games/pair = {total_games} games. "
        f"max_turns={args.max_turns}, difficulty={args.difficulty}",
        flush=True,
    )

    results = run_deck_tournament(
        deck_pool,
        games_per_pair=args.games,
        max_turns=args.max_turns,
        difficulty=args.difficulty,
        hard_timeout_s=args.hard_timeout,
        ai_pair=args.ai,
        verbose=not args.quiet,
    )

    agg = aggregate(results)
    report = render_tier_report(agg)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({**results, "aggregate": agg}, f, indent=2, default=str)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        print(f"Tier report -> {report_path}", flush=True)

    print(report)
    print(f"\nRaw results -> {out_path}")
    elapsed = results.get("elapsed_s", 0)
    if total_games:
        print(
            f"Total wall time: {elapsed:.0f}s "
            f"({elapsed / total_games:.2f}s/game)",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
