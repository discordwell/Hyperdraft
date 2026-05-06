"""
balance_loop — tournament JSON analyzer for the /new-set pipeline.

Consumes the aggregate JSON produced by `scripts/play/custom_set_tournament.py`
(or any tournament runner emitting the same `{set_summary, matchup,
card_scores}` shape) and emits a flagged-cards / flagged-archetypes report
the orchestrator uses to decide whether to revise cards and re-run.

Design notes
------------
This module deliberately does *not* run games. The pipeline owns deck
construction + tournament invocation; this analyzer is engine-agnostic
and pure-Python so it can be unit-tested without spinning up an engine.

Per-card metric: `win_contribution`
    Within the cards belonging to `set_label`, we compute a z-score on
    `win_rate_in_play` (the per-card field already produced by the
    aggregator: fraction of games where the card was on the board at end
    *and* its side won). Cards with too few in-play samples are excluded
    from the median to prevent noise dominating the outlier signal.

    Flagging:
      - |z| >= Z_FLAG_THRESHOLD             → "overpowered" / "underpowered"
      - in_play_at_end < MIN_IN_PLAY_SAMPLES → "low_sample" (advisory only)

Per-archetype metric: `winrate`
    `set_summary[domain]["winrate"]`. Outside [LOW_WINRATE, HIGH_WINRATE]
    the archetype is flagged.

Convergence: `should_continue_loop`
    Returns False when no cards or archetypes are flagged on the latest
    cycle, or when the cycle counter hits the cap (default 10 — matches
    /new-set's pipeline default).

CLI:
    python -m scripts.new_set.balance_loop \\
        --tournament logs/round_3.json \\
        --set MYSET \\
        --archetypes MYSET_aggro,MYSET_control,MYSET_combo \\
        --out logs/round_3_flags.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable

from .coverage import parse_card_ref, stats_for_set


# ---------------------------------------------------------------------------
# Tunable thresholds. Pipeline can override via CLI flags.
# ---------------------------------------------------------------------------
Z_FLAG_THRESHOLD = 1.5            # |z| ≥ this on win_rate_in_play → flagged
MIN_IN_PLAY_SAMPLES = 5           # cards with fewer in-play samples are advisory only
LOW_WINRATE = 0.40                # archetype winrate below this → underpowered
HIGH_WINRATE = 0.60               # archetype winrate above this → overpowered
DEFAULT_MAX_CYCLES = 10
MIN_GAMES_FOR_ARCH_FLAG = 10      # don't flag archetype until it has ≥ N games


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class CardFlag:
    name: str
    win_rate_in_play: float
    z_score: float
    in_play_samples: int
    cast: int
    direction: str       # "overpowered" | "underpowered" | "low_sample"
    reason: str


@dataclass
class ArchetypeFlag:
    domain: str
    winrate: float
    games: int
    direction: str       # "overpowered" | "underpowered"
    reason: str


@dataclass
class BalanceReport:
    set_label: str
    cycle: int
    flagged_cards: list[CardFlag] = field(default_factory=list)
    flagged_archetypes: list[ArchetypeFlag] = field(default_factory=list)
    median_win_rate_in_play: float = 0.0
    sample_size_excluded: int = 0
    converged: bool = False
    error: str | None = None         # set when the round can't be analyzed
                                     # (no card data, missing summary, etc.)
    cards_analyzed: int = 0          # how many cards from this set had stats

    def has_flags(self) -> bool:
        return bool(self.flagged_cards) or bool(self.flagged_archetypes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_label": self.set_label,
            "cycle": self.cycle,
            "flagged_cards": [asdict(c) for c in self.flagged_cards],
            "flagged_archetypes": [asdict(a) for a in self.flagged_archetypes],
            "median_win_rate_in_play": round(self.median_win_rate_in_play, 4),
            "sample_size_excluded": self.sample_size_excluded,
            "converged": self.converged,
            "error": self.error,
            "cards_analyzed": self.cards_analyzed,
        }


# =============================================================================
# Metric computation
# =============================================================================

def _stdev_safe(values: list[float]) -> float:
    """Sample stdev, returns 0.0 if fewer than 2 values."""
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def _z_score(x: float, mean: float, sd: float) -> float:
    if sd <= 0.0:
        return 0.0
    return (x - mean) / sd


def compute_card_flags(
    card_scores: dict[str, dict[str, Any]],
    set_label: str,
    *,
    z_threshold: float = Z_FLAG_THRESHOLD,
    min_samples: int = MIN_IN_PLAY_SAMPLES,
) -> tuple[list[CardFlag], float, int]:
    """
    Returns (flags, median_win_rate_in_play, count_excluded_for_low_samples).

    Cards with `in_play_at_end < min_samples` are not used to compute the
    median/stdev (their win_rate_in_play is high-variance), but they are
    still emitted as advisory `low_sample` flags so the pipeline can see
    them.
    """
    set_stats = stats_for_set(card_scores, set_label)

    high_sample: list[tuple[str, dict[str, Any]]] = []
    low_sample: list[tuple[str, dict[str, Any]]] = []
    for name, stats in set_stats.items():
        in_play = int(stats.get("in_play_at_end", 0) or 0)
        if in_play >= min_samples:
            high_sample.append((name, stats))
        else:
            low_sample.append((name, stats))

    flags: list[CardFlag] = []

    if not high_sample:
        # No data to compute a median against — every card is low-sample.
        for name, stats in low_sample:
            flags.append(CardFlag(
                name=name,
                win_rate_in_play=float(stats.get("win_rate_in_play", 0.0) or 0.0),
                z_score=0.0,
                in_play_samples=int(stats.get("in_play_at_end", 0) or 0),
                cast=int(stats.get("cast", 0) or 0),
                direction="low_sample",
                reason=f"<{min_samples} in-play samples; no set baseline.",
            ))
        return flags, 0.0, len(low_sample)

    rates = [float(s.get("win_rate_in_play", 0.0) or 0.0) for _, s in high_sample]
    mean = statistics.mean(rates)
    sd = _stdev_safe(rates)
    median = statistics.median(rates)

    for name, stats in high_sample:
        rate = float(stats.get("win_rate_in_play", 0.0) or 0.0)
        z = _z_score(rate, mean, sd)
        if z >= z_threshold:
            flags.append(CardFlag(
                name=name,
                win_rate_in_play=rate,
                z_score=round(z, 3),
                in_play_samples=int(stats.get("in_play_at_end", 0) or 0),
                cast=int(stats.get("cast", 0) or 0),
                direction="overpowered",
                reason=f"win_rate_in_play={rate:.2f} is {z:.2f}σ above set mean ({mean:.2f}).",
            ))
        elif z <= -z_threshold:
            flags.append(CardFlag(
                name=name,
                win_rate_in_play=rate,
                z_score=round(z, 3),
                in_play_samples=int(stats.get("in_play_at_end", 0) or 0),
                cast=int(stats.get("cast", 0) or 0),
                direction="underpowered",
                reason=f"win_rate_in_play={rate:.2f} is {z:.2f}σ below set mean ({mean:.2f}).",
            ))

    # Advisory low-sample notes — don't double-emit if the card is already
    # in a high-sample flag.
    for name, stats in low_sample:
        flags.append(CardFlag(
            name=name,
            win_rate_in_play=float(stats.get("win_rate_in_play", 0.0) or 0.0),
            z_score=0.0,
            in_play_samples=int(stats.get("in_play_at_end", 0) or 0),
            cast=int(stats.get("cast", 0) or 0),
            direction="low_sample",
            reason=f"only {stats.get('in_play_at_end', 0)} in-play samples — "
                   f"need ≥ {min_samples} for a confident verdict.",
        ))

    return flags, median, len(low_sample)


def compute_archetype_flags(
    set_summary: dict[str, dict[str, Any]],
    archetypes: Iterable[str],
    *,
    low: float = LOW_WINRATE,
    high: float = HIGH_WINRATE,
    min_games: int = MIN_GAMES_FOR_ARCH_FLAG,
) -> list[ArchetypeFlag]:
    """Flag archetype decks whose winrate is outside [low, high]."""
    flags: list[ArchetypeFlag] = []
    for domain in archetypes:
        rec = set_summary.get(domain)
        if not rec:
            continue
        wr = float(rec.get("winrate", 0.0) or 0.0)
        gp = int(rec.get("games_played", 0) or 0)
        if gp < min_games:
            continue   # not enough games to conclude
        if wr < low:
            flags.append(ArchetypeFlag(
                domain=domain,
                winrate=round(wr, 3),
                games=gp,
                direction="underpowered",
                reason=f"archetype winrate {wr:.2f} below floor {low:.2f}.",
            ))
        elif wr > high:
            flags.append(ArchetypeFlag(
                domain=domain,
                winrate=round(wr, 3),
                games=gp,
                direction="overpowered",
                reason=f"archetype winrate {wr:.2f} above ceiling {high:.2f}.",
            ))
    return flags


# =============================================================================
# Public API: full analysis + convergence
# =============================================================================

def analyze_round(
    tournament: dict[str, Any],
    set_label: str,
    archetypes: list[str],
    cycle: int,
    *,
    z_threshold: float = Z_FLAG_THRESHOLD,
    min_samples: int = MIN_IN_PLAY_SAMPLES,
    low_winrate: float = LOW_WINRATE,
    high_winrate: float = HIGH_WINRATE,
) -> BalanceReport:
    """
    Run a single balance round's analysis. Returns a BalanceReport with
    `converged=True` when no actionable flags exist (low-sample advisories
    do not block convergence).

    Empty / malformed tournament data is detected up-front and returned as
    `converged=False` with an `error` string — *never* false-positive
    converge on no data. The pipeline should treat that as a hard failure
    of the tournament step, not a clean exit.
    """
    card_scores = tournament.get("card_scores") or {}
    set_summary = tournament.get("set_summary") or {}

    # Hard guard: refuse to converge on no data.
    if not card_scores:
        return BalanceReport(
            set_label=set_label, cycle=cycle,
            converged=False,
            error="tournament JSON has empty / missing card_scores",
        )
    set_card_scores = stats_for_set(card_scores, set_label)
    if not set_card_scores:
        return BalanceReport(
            set_label=set_label, cycle=cycle,
            converged=False,
            error=(f"no card_scores entries match set_label {set_label!r} — "
                   f"check that deck labels are <{set_label}>_<archetype>"),
        )

    card_flags, median, excluded = compute_card_flags(
        card_scores, set_label,
        z_threshold=z_threshold,
        min_samples=min_samples,
    )
    arch_flags = compute_archetype_flags(
        set_summary, archetypes,
        low=low_winrate, high=high_winrate,
    )

    # Convergence: only actionable flags count.
    actionable_card_flags = [c for c in card_flags if c.direction != "low_sample"]
    converged = not actionable_card_flags and not arch_flags

    return BalanceReport(
        set_label=set_label,
        cycle=cycle,
        flagged_cards=card_flags,
        flagged_archetypes=arch_flags,
        median_win_rate_in_play=median,
        sample_size_excluded=excluded,
        converged=converged,
        cards_analyzed=len(set_card_scores),
    )


def should_continue_loop(
    report: BalanceReport,
    *,
    max_cycles: int = DEFAULT_MAX_CYCLES,
) -> bool:
    """
    Pipeline control predicate: True if the orchestrator should run
    another revision+test cycle.

    Stops when:
      - the report converged (no actionable flags), or
      - cycle counter is at or above max_cycles.
    """
    if report.converged:
        return False
    if report.cycle >= max_cycles:
        return False
    return True


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tournament", type=Path, required=True,
                    help="Tournament aggregate JSON.")
    ap.add_argument("--set", dest="set_label", required=True,
                    help="Set domain label (e.g. MYSET).")
    ap.add_argument("--archetypes", default="",
                    help="Comma-separated archetype domain labels.")
    ap.add_argument("--cycle", type=int, default=1,
                    help="Cycle number for this report.")
    ap.add_argument("--z-threshold", type=float, default=Z_FLAG_THRESHOLD)
    ap.add_argument("--min-samples", type=int, default=MIN_IN_PLAY_SAMPLES)
    ap.add_argument("--low-winrate", type=float, default=LOW_WINRATE)
    ap.add_argument("--high-winrate", type=float, default=HIGH_WINRATE)
    ap.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES)
    ap.add_argument("--out", type=Path, default=None,
                    help="Write JSON report here, default stdout.")
    args = ap.parse_args()

    tournament = json.loads(args.tournament.read_text(encoding="utf-8"))
    archetypes = [a.strip() for a in args.archetypes.split(",") if a.strip()]

    report = analyze_round(
        tournament,
        args.set_label,
        archetypes,
        cycle=args.cycle,
        z_threshold=args.z_threshold,
        min_samples=args.min_samples,
        low_winrate=args.low_winrate,
        high_winrate=args.high_winrate,
    )

    payload = json.dumps(report.to_dict(), indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(payload + "\n")

    if not should_continue_loop(report, max_cycles=args.max_cycles):
        return 0      # pipeline can stop iterating
    return 2          # exit code 2 = "more revisions needed"


if __name__ == "__main__":
    raise SystemExit(main())
