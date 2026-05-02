#!/usr/bin/env python3
"""
Netdeck calibration as a PROGRESS METRIC, not a pass-bar.

Builds heuristic hybrid decks for each archetype represented in
`src/decks/netdecks.py:NETDECKS`, runs them against same-archetype
netdecks (intra-archetype calibration) and against the top netdeck of
each *other* archetype (cross-archetype context), and emits a JSON +
Markdown report. Appends one line per run to a JSONL history file.

Crucially:
- No thresholds. No pass/fail. Never raises on bad numbers.
- The user's framing: "the best human efforts here will almost certainly
  be better than the best AI. At least for now." Numbers are expected
  to be low; track them over time.

Usage:
    python scripts/play/netdeck_calibration.py \\
        --games 5 \\
        --archetypes Aggro,Midrange,Control \\
        --top-n 2 \\
        --out logs/calibration_<ts>.json \\
        --md logs/calibration_<ts>.md \\
        --history logs/calibration_history.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Default sensible color identities per archetype. Configurable via CLI.
DEFAULT_COLORS_FOR_ARCHETYPE: dict[str, list[str]] = {
    "Aggro": ["R"],
    "Midrange": ["B", "G"],
    "Control": ["W", "U"],
    "Tempo": ["U", "R"],
    "Ramp": ["G"],
    "Combo": ["U", "R"],
}


def _git_sha() -> str:
    """Best-effort short git sha. Returns 'unknown' on any failure."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _standard_set_codes() -> list[str]:
    """
    Return set codes whose `set_type` is `standard` or `universes_beyond`,
    excluding custom sets and the test set. Order is stable (insertion order
    of SETS dict).
    """
    from src.cards.set_registry import SETS  # local import; cheap

    allowed = {"standard", "universes_beyond"}
    return [code for code, info in SETS.items() if info.set_type in allowed]


def _group_netdecks_by_archetype() -> dict[str, list[tuple[str, Any]]]:
    """
    Group NETDECKS by archetype, returning a dict
    {archetype: [(deck_id, Deck), ...]}.

    Order within each archetype follows the natural NETDECKS dict order
    (insertion order in netdecks.py), which roughly tracks "representativeness"
    since the canonical entries are listed first.
    """
    from src.decks.netdecks import NETDECKS  # local import

    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for deck_id, deck in NETDECKS.items():
        grouped[deck.archetype].append((deck_id, deck))
    return dict(grouped)


def _resolve_colors_for_archetype(
    archetype: str,
    overrides: dict[str, list[str]],
) -> list[str]:
    """Pick colors for a hybrid build of `archetype`."""
    if archetype in overrides:
        return overrides[archetype]
    return DEFAULT_COLORS_FOR_ARCHETYPE.get(archetype, ["R"])  # safe fallback


def _build_hybrid_deck_for_archetype(
    archetype: str,
    colors: list[str],
    set_codes: list[str],
):
    """
    Build a hybrid heuristic deck for `archetype`. Lazy-imports
    `build_heuristic_deck` from W2's heuristics package so this script
    can be imported (e.g., by tests) even if W2 hasn't merged.
    """
    from src.decks.heuristics.builder import build_heuristic_deck  # lazy

    name = f"Hybrid_{archetype}"
    return build_heuristic_deck(
        name=name,
        archetype=archetype,
        colors=colors,
        set_codes=set_codes,
    )


def _run_tournament(
    deck_pool: dict[str, Any],
    games_per_pair: int,
    *,
    max_turns: int = 14,
    difficulty: str = "hard",
) -> dict[str, Any]:
    """
    Lazy-imports W4's `run_deck_tournament` and runs the round-robin.
    Falls back gracefully (raises informative ImportError) if W4 hasn't
    merged yet.
    """
    try:
        from scripts.play.custom_set_tournament import run_deck_tournament  # lazy
    except ImportError as e:
        raise ImportError(
            "run_deck_tournament not available yet — depends on W4 "
            f"(scripts/play/custom_set_tournament.py). Underlying error: {e}"
        ) from e

    return run_deck_tournament(
        deck_pool,
        games_per_pair=games_per_pair,
        max_turns=max_turns,
        difficulty=difficulty,
    )


def _extract_matchup_record(
    results: list[dict[str, Any]],
    label_a: str,
    label_b: str,
) -> dict[str, int]:
    """
    Count W/L/D for `label_a` vs `label_b` from a list of game results.
    Tolerates both `winner_domain` and `winner_label` keys.
    """
    rec = {"wins": 0, "losses": 0, "draws": 0, "errors": 0}
    for r in results:
        p1 = r.get("p1_label") or r.get("p1_domain")
        p2 = r.get("p2_label") or r.get("p2_domain")
        if p1 not in (label_a, label_b) or p2 not in (label_a, label_b):
            continue
        if p1 == p2:
            continue
        if r.get("error"):
            rec["errors"] += 1
            continue
        winner = r.get("winner_label") or r.get("winner_domain")
        if winner is None:
            rec["draws"] += 1
        elif winner == label_a:
            rec["wins"] += 1
        elif winner == label_b:
            rec["losses"] += 1
        # else: malformed; ignore
    return rec


def _compute_calibration(
    args: argparse.Namespace,
    color_overrides: dict[str, list[str]],
) -> dict[str, Any]:
    """
    Build the deck pool, run the tournament, and structure the result
    into the calibration JSON shape. Pure function aside from the
    tournament call.
    """
    set_codes = _standard_set_codes()
    grouped = _group_netdecks_by_archetype()

    # Decide which archetypes to calibrate
    if args.archetypes:
        requested = [a.strip() for a in args.archetypes.split(",") if a.strip()]
    else:
        requested = list(grouped.keys())

    # Filter to archetypes that actually have at least one netdeck
    archetypes = [a for a in requested if grouped.get(a)]
    skipped = [a for a in requested if not grouped.get(a)]

    # Build hybrid decks + collect netdeck representatives
    deck_pool: dict[str, Any] = {}
    hybrid_labels: dict[str, str] = {}     # archetype -> hybrid label
    netdeck_labels_by_arch: dict[str, list[str]] = {}  # archetype -> [netdeck labels]

    build_errors: list[dict[str, str]] = []

    for arch in archetypes:
        colors = _resolve_colors_for_archetype(arch, color_overrides)
        try:
            hybrid_deck = _build_hybrid_deck_for_archetype(arch, colors, set_codes)
        except Exception as e:  # pragma: no cover — defensive; never gate
            build_errors.append({
                "archetype": arch,
                "error": f"{type(e).__name__}: {e}",
            })
            continue
        h_label = f"hybrid_{arch.lower()}"
        hybrid_labels[arch] = h_label
        deck_pool[h_label] = hybrid_deck

        # Same-archetype netdecks (top-N)
        same_arch_netdecks = grouped.get(arch, [])[: max(1, args.top_n)]
        netdeck_labels_by_arch[arch] = []
        for deck_id, nd in same_arch_netdecks:
            label = f"netdeck_{deck_id}"
            deck_pool[label] = nd
            netdeck_labels_by_arch[arch].append(label)

    # Cross-archetype context: top netdeck of each *other* archetype
    cross_labels_by_arch: dict[str, list[str]] = {}
    for arch in archetypes:
        cross_labels: list[str] = []
        for other_arch, decks in grouped.items():
            if other_arch == arch:
                continue
            if not decks:
                continue
            deck_id, nd = decks[0]
            label = f"netdeck_{deck_id}"
            if label not in deck_pool:
                deck_pool[label] = nd
            cross_labels.append(label)
        cross_labels_by_arch[arch] = cross_labels

    # Run the tournament
    tournament_error: Optional[str] = None
    tournament_raw: dict[str, Any] = {}
    started = time.perf_counter()
    if deck_pool:
        try:
            tournament_raw = _run_tournament(
                deck_pool,
                games_per_pair=args.games,
                max_turns=args.max_turns,
                difficulty=args.difficulty,
            )
        except Exception as e:
            tournament_error = f"{type(e).__name__}: {e}"
            tournament_raw = {"results": [], "error": tournament_error}
    elapsed = time.perf_counter() - started

    results = tournament_raw.get("results") or []

    # Aggregate per archetype
    per_archetype: dict[str, dict[str, Any]] = {}
    per_matchup: dict[str, dict[str, int]] = {}

    for arch in archetypes:
        h_label = hybrid_labels.get(arch)
        if not h_label:
            per_archetype[arch] = {
                "hybrid_label": None,
                "colors": _resolve_colors_for_archetype(arch, color_overrides),
                "same_archetype": [],
                "cross_archetype": [],
                "same_archetype_winrate": 0.0,
                "cross_archetype_winrate": 0.0,
                "build_error": next(
                    (be["error"] for be in build_errors if be["archetype"] == arch),
                    None,
                ),
            }
            continue

        # Same-archetype matchups
        same_arch_records: list[dict[str, Any]] = []
        for nd_label in netdeck_labels_by_arch.get(arch, []):
            rec = _extract_matchup_record(results, h_label, nd_label)
            key = f"{h_label} vs {nd_label}"
            per_matchup[key] = rec
            played = rec["wins"] + rec["losses"] + rec["draws"]
            wr = (rec["wins"] / played) if played else 0.0
            same_arch_records.append({
                "opponent": nd_label,
                "opponent_name": deck_pool[nd_label].name if nd_label in deck_pool else nd_label,
                "wins": rec["wins"],
                "losses": rec["losses"],
                "draws": rec["draws"],
                "errors": rec["errors"],
                "games_played": played,
                "winrate": round(wr, 3),
            })

        # Cross-archetype matchups
        cross_records: list[dict[str, Any]] = []
        for nd_label in cross_labels_by_arch.get(arch, []):
            rec = _extract_matchup_record(results, h_label, nd_label)
            key = f"{h_label} vs {nd_label}"
            per_matchup[key] = rec
            played = rec["wins"] + rec["losses"] + rec["draws"]
            wr = (rec["wins"] / played) if played else 0.0
            cross_records.append({
                "opponent": nd_label,
                "opponent_name": deck_pool[nd_label].name if nd_label in deck_pool else nd_label,
                "wins": rec["wins"],
                "losses": rec["losses"],
                "draws": rec["draws"],
                "errors": rec["errors"],
                "games_played": played,
                "winrate": round(wr, 3),
            })

        # Aggregates
        sa_w = sum(r["wins"] for r in same_arch_records)
        sa_l = sum(r["losses"] for r in same_arch_records)
        sa_d = sum(r["draws"] for r in same_arch_records)
        sa_total = sa_w + sa_l + sa_d
        sa_wr = (sa_w / sa_total) if sa_total else 0.0

        cr_w = sum(r["wins"] for r in cross_records)
        cr_l = sum(r["losses"] for r in cross_records)
        cr_d = sum(r["draws"] for r in cross_records)
        cr_total = cr_w + cr_l + cr_d
        cr_wr = (cr_w / cr_total) if cr_total else 0.0

        per_archetype[arch] = {
            "hybrid_label": h_label,
            "colors": _resolve_colors_for_archetype(arch, color_overrides),
            "same_archetype": same_arch_records,
            "cross_archetype": cross_records,
            "same_archetype_wins": sa_w,
            "same_archetype_losses": sa_l,
            "same_archetype_draws": sa_d,
            "same_archetype_winrate": round(sa_wr, 3),
            "cross_archetype_wins": cr_w,
            "cross_archetype_losses": cr_l,
            "cross_archetype_draws": cr_d,
            "cross_archetype_winrate": round(cr_wr, 3),
            "build_error": None,
        }

    args_dict = {
        "games": args.games,
        "top_n": args.top_n,
        "archetypes": archetypes,
        "skipped_archetypes": skipped,
        "set_codes": set_codes,
        "color_overrides": color_overrides,
        "max_turns": args.max_turns,
        "difficulty": args.difficulty,
    }

    return {
        "date": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "args": args_dict,
        "per_archetype": per_archetype,
        "per_matchup": per_matchup,
        "elapsed_s": round(elapsed, 2),
        "tournament_error": tournament_error,
        "build_errors": build_errors,
    }


def _format_record(rec: dict[str, Any]) -> str:
    """Format a single matchup record line: 'W-L-D (XX%)'."""
    return (
        f"{rec.get('wins', 0)}W-"
        f"{rec.get('losses', 0)}L-"
        f"{rec.get('draws', 0)}D "
        f"({rec.get('winrate', 0.0) * 100:.0f}%)"
    )


def _render_markdown(report: dict[str, Any]) -> str:
    """Render the calibration report as Markdown with the required Notes section."""
    lines: list[str] = []
    date = report.get("date", "")
    short_date = date.split("T")[0] if "T" in date else date
    lines.append(f"# Hybrid Builder Calibration — {short_date}")
    lines.append("")

    git_sha = report.get("git_sha") or ""
    if git_sha and git_sha != "unknown":
        lines.append(f"_git: {git_sha[:8]}_")
        lines.append("")

    archetypes = list(report.get("per_archetype", {}).keys())

    if not archetypes:
        lines.append("_No archetypes calibrated. (Are there any netdecks for the requested archetypes?)_")
        lines.append("")

    for arch in archetypes:
        data = report["per_archetype"][arch]
        lines.append(f"## {arch}")
        h_label = data.get("hybrid_label")
        colors = data.get("colors", [])
        if h_label:
            lines.append(f"  Hybrid build: `{h_label}` — colors={''.join(colors)}")
        if data.get("build_error"):
            lines.append(f"  build_error: {data['build_error']}")
            lines.append("")
            continue

        # Same-archetype matchups
        same = data.get("same_archetype", [])
        if same:
            for r in same:
                opp_name = r.get("opponent_name") or r.get("opponent")
                lines.append(
                    f"  {h_label} vs {opp_name} (netdeck): {_format_record(r)}"
                )
            sa_w = data.get("same_archetype_wins", 0)
            sa_l = data.get("same_archetype_losses", 0)
            sa_d = data.get("same_archetype_draws", 0)
            sa_wr = data.get("same_archetype_winrate", 0.0)
            lines.append(
                f"  Same-archetype: {sa_w}W-{sa_l}L-{sa_d}D "
                f"avg {sa_wr * 100:.0f}%"
            )
        else:
            lines.append("  (no same-archetype netdecks available)")

        # Cross-archetype context
        cross = data.get("cross_archetype", [])
        if cross:
            cr_w = data.get("cross_archetype_wins", 0)
            cr_l = data.get("cross_archetype_losses", 0)
            cr_d = data.get("cross_archetype_draws", 0)
            opp_archs = sorted({_archetype_from_label(r["opponent"]) for r in cross})
            opp_label = "/".join(opp_archs) if opp_archs else "other"
            lines.append(
                f"  Cross-archetype: {cr_w}W-{cr_l}L-{cr_d}D "
                f"(vs {opp_label} netdecks)"
            )
        lines.append("")

    if report.get("tournament_error"):
        lines.append("## Errors")
        lines.append(f"  tournament_error: {report['tournament_error']}")
        lines.append("")

    # ALWAYS include the Notes section. This is the load-bearing framing.
    lines.append("## Notes")
    lines.append(
        "  Calibration is informational. Numbers are expected to be low (often <40%)"
    )
    lines.append(
        "  vs hand-tuned netdecks. Track week-over-week to see whether builder"
    )
    lines.append("  improvements move the curve.")
    lines.append("")

    return "\n".join(lines)


def _archetype_from_label(label: str) -> str:
    """Best-effort extraction of an archetype hint from a netdeck label."""
    # Conservative: don't try to be clever. Caller passes through the report.
    # We do a lightweight reverse-lookup against NETDECKS at call-time.
    try:
        from src.decks.netdecks import NETDECKS  # lazy
        if label.startswith("netdeck_"):
            deck_id = label[len("netdeck_"):]
            d = NETDECKS.get(deck_id)
            if d:
                return d.archetype
    except Exception:
        pass
    return "?"


def _append_history(history_path: Path, report: dict[str, Any]) -> None:
    """Append one JSONL line summarizing this run's per-archetype winrate."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    per_arch_wr = {
        arch: data.get("same_archetype_winrate", 0.0)
        for arch, data in report.get("per_archetype", {}).items()
    }
    line = {
        "date": report.get("date"),
        "git_sha": report.get("git_sha"),
        "per_archetype_winrate": per_arch_wr,
        "args": report.get("args", {}),
    }
    with open(history_path, "a") as f:
        f.write(json.dumps(line) + "\n")


def _parse_color_overrides(args: argparse.Namespace) -> dict[str, list[str]]:
    """Pick up --colors-for-{archetype} flags from argparse namespace."""
    overrides: dict[str, list[str]] = {}
    for arch in DEFAULT_COLORS_FOR_ARCHETYPE.keys():
        attr = f"colors_for_{arch.lower()}"
        val = getattr(args, attr, None)
        if val:
            overrides[arch] = [c.strip().upper() for c in val.split(",") if c.strip()]
    return overrides


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Netdeck calibration — progress metric, NOT a pass-bar."
    )
    parser.add_argument(
        "--games", type=int, default=5,
        help="games per matchup pair (default 5)",
    )
    parser.add_argument(
        "--archetypes", type=str, default=None,
        help="comma-separated archetypes (default: all archetypes with ≥1 netdeck)",
    )
    parser.add_argument(
        "--top-n", type=int, default=2,
        help="representative netdecks per archetype (default 2)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=14,
        help="max turns per game (default 14)",
    )
    parser.add_argument(
        "--difficulty", type=str, default="hard",
        help="AI difficulty (default hard)",
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parser.add_argument(
        "--out", type=str, default=f"logs/calibration_{timestamp}.json",
        help="JSON output path",
    )
    parser.add_argument(
        "--md", type=str, default=None,
        help="Markdown report path (default: same as --out with .md extension)",
    )
    parser.add_argument(
        "--history", type=str, default="logs/calibration_history.jsonl",
        help="JSONL history file (append-only)",
    )

    # Color override flags
    for arch in DEFAULT_COLORS_FOR_ARCHETYPE.keys():
        parser.add_argument(
            f"--colors-for-{arch.lower()}",
            type=str,
            default=None,
            help=f"comma-separated colors for {arch} hybrid build",
        )

    args = parser.parse_args(argv)

    color_overrides = _parse_color_overrides(args)

    # Compute calibration. NEVER raise on bad numbers.
    report = _compute_calibration(args, color_overrides)

    # Resolve paths
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.md:
        md_path = Path(args.md)
        if not md_path.is_absolute():
            md_path = REPO_ROOT / md_path
    else:
        md_path = out_path.with_suffix(".md")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    history_path = Path(args.history)
    if not history_path.is_absolute():
        history_path = REPO_ROOT / history_path

    # Write outputs
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    md = _render_markdown(report)
    with open(md_path, "w") as f:
        f.write(md)

    _append_history(history_path, report)

    # Print human-readable summary
    print(md)
    print(f"\nJSON     -> {out_path}")
    print(f"Markdown -> {md_path}")
    print(f"History  -> {history_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
