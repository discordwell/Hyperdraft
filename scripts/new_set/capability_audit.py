"""
capability_audit — root-cause diagnoser for the /new-set Stage 8 audit loop.

Replaces the old "card-revision only" balance loop. Reads a tournament JSON
plus optional event-log signals and produces structured findings classified
by category + severity, each routed to the right kind of fix agent.

Five finding categories:
  ai_omission         AI never used a category of legal action
  mechanic_dead_end   A named mechanic's trigger fired below threshold
  engine_omission     A primitive cards reference doesn't exist (TODO clusters)
  card_crash          Cards that errored during play
  archetype_weakness  Archetype loses uniformly AND no card-level lever explains it

Each finding routes to one of:
  ai_extension          → src/ai/<engine>_adapter.py
  card_revision         → src/cards/<engine>/<set>/<archetype>.py
  archetype_redesign    → multi-file rewrite within one archetype
  engine_extension      → src/engine/<engine>*.py (or types.py)
  mechanic_repair       → cards or AI, depending on the failure mode
  card_repair           → single card causing crashes

The orchestrating slash command consumes findings.json, dispatches fix
agents in parallel (one per finding), runs regression, and re-audits.
This module is pure-Python: no agent dispatch happens here.

JSON contract (input — extends the {set_summary, matchup, card_scores}
shape):

    {
      "set_summary":       { ... },
      "matchup":           { ... },
      "card_scores":       { ... },

      // OPTIONAL — capability detectors silently skip when absent
      "ai_action_counts":  { "DEPTHS_DETECT": 0, "DEPTHS_DEPLOY_VESSEL": 142, ... },
      "mechanic_triggers": { "WOLFPACK N": 0, "CRUSH-DIVE": 14, ... },
      "card_errors":       { "Card Name": "stack trace excerpt" },
      "available_actions": [ "DEPTHS_DETECT", "DEPTHS_DEPLOY_VESSEL", ... ]
    }

CLI:
    python -m scripts.new_set.capability_audit \\
        --tournament logs/balance_subs_round_1.json \\
        --set SUBS \\
        --archetypes SUBS_wolfpack,SUBS_silent_hunter,SUBS_carrier,SUBS_deep_strike \\
        --cycle 1 \\
        --out logs/audit_subs_round_1.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .coverage import stats_for_set, parse_card_ref


# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------
AI_OMISSION_THRESHOLD = 0          # action used 0 times → critical
AI_RARE_USE_THRESHOLD = 0.05       # < 5% of an "expected" baseline → high

MECHANIC_DEADEND_TRIGGER_THRESHOLD = 5     # < 5 trigger fires across tournament
MECHANIC_DEADEND_CARDS_THRESHOLD = 3       # ...and at least 3 cards reference it

ARCHETYPE_WEAKNESS_WINRATE = 0.20          # winrate ≤ 20% AND
ARCHETYPE_WEAKNESS_MIN_GAMES = 10          # ...at least 10 games
CONTRIB_VARIANCE_THRESHOLD = 0.05          # if no card has |contrib − median| > this,
                                           # weakness is structural, not card-level

ENGINE_OMISSION_TODO_CLUSTER = 4           # ≥4 TODOs sharing a substring → cluster

DEFAULT_MAX_AUDIT_CYCLES = 3


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class Finding:
    category: str            # ai_omission / mechanic_dead_end / engine_omission /
                             # card_crash / archetype_weakness
    severity: str            # critical / high / medium / low
    summary: str             # one-line human-readable
    evidence: dict[str, Any] # numbers backing the finding
    fix_dispatch: str        # ai_extension / card_revision / archetype_redesign /
                             # engine_extension / mechanic_repair / card_repair
    fix_brief: str           # what the fix-dispatch agent should be briefed to do


@dataclass
class AuditReport:
    set_label: str
    cycle: int
    findings: list[Finding] = field(default_factory=list)
    has_actionable_findings: bool = False
    skipped_detectors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_label": self.set_label,
            "cycle": self.cycle,
            "findings": [asdict(f) for f in self.findings],
            "has_actionable_findings": self.has_actionable_findings,
            "skipped_detectors": self.skipped_detectors,
        }


# =============================================================================
# Detectors — one per finding category. Each returns list[Finding].
# =============================================================================

def detect_ai_omissions(
    tournament: dict[str, Any],
) -> tuple[list[Finding], bool]:
    """Returns (findings, was_skipped). Skips if ai_action_counts absent."""
    counts = tournament.get("ai_action_counts")
    available = tournament.get("available_actions")
    if not counts:
        return [], True

    findings: list[Finding] = []

    # If we know the universe of available actions, check ones that are 0
    universe = available if available else list(counts.keys())
    for action_type in universe:
        n = int(counts.get(action_type, 0) or 0)
        if n == AI_OMISSION_THRESHOLD:
            findings.append(Finding(
                category="ai_omission",
                severity="critical",
                summary=f"AI never used action `{action_type}` across the tournament",
                evidence={"action_type": action_type, "occurrences": 0},
                fix_dispatch="ai_extension",
                fix_brief=(
                    f"Extend the AI adapter to recognise `{action_type}` as a "
                    f"legal play in its action-menu generator and add a "
                    f"heuristic for when to take it. Without this, every card "
                    f"that depends on this action is silently dead."
                ),
            ))
        elif n > 0 and available:
            # Soft check: is it under-used? Compare against the median of all
            # used actions in the same tournament.
            used = [int(c or 0) for c in counts.values() if int(c or 0) > 0]
            if used:
                median = statistics.median(used)
                if median > 0 and n / median < AI_RARE_USE_THRESHOLD:
                    findings.append(Finding(
                        category="ai_omission",
                        severity="high",
                        summary=(
                            f"AI used `{action_type}` only {n} times "
                            f"(< {AI_RARE_USE_THRESHOLD * 100:.0f}% of median {median})"
                        ),
                        evidence={
                            "action_type": action_type,
                            "occurrences": n,
                            "median_action_count": median,
                        },
                        fix_dispatch="ai_extension",
                        fix_brief=(
                            f"Tune the AI's heuristic for `{action_type}`. It's "
                            f"a legal action but the AI almost never picks it."
                        ),
                    ))
    return findings, False


def detect_mechanic_dead_ends(
    tournament: dict[str, Any],
) -> tuple[list[Finding], bool]:
    """Returns (findings, was_skipped). Skips if mechanic_triggers absent."""
    triggers = tournament.get("mechanic_triggers")
    if not triggers:
        return [], True

    findings: list[Finding] = []
    for mechanic, count in triggers.items():
        n = int(count or 0)
        if n < MECHANIC_DEADEND_TRIGGER_THRESHOLD:
            findings.append(Finding(
                category="mechanic_dead_end",
                severity="high" if n == 0 else "medium",
                summary=(
                    f"Mechanic `{mechanic}` triggered only {n} times across "
                    f"the tournament (< threshold {MECHANIC_DEADEND_TRIGGER_THRESHOLD})"
                ),
                evidence={"mechanic": mechanic, "trigger_count": n},
                fix_dispatch="mechanic_repair",
                fix_brief=(
                    f"Investigate why `{mechanic}` doesn't fire. Likely "
                    f"causes: (a) precondition is too narrow — the AI never "
                    f"creates the state that satisfies it; (b) the trigger "
                    f"is wired to the wrong event type; (c) cards using the "
                    f"mechanic aren't being deployed. Fix may be in the AI "
                    f"adapter, the cards' setup_interceptors, or the "
                    f"mechanic's preconditions in the design doc."
                ),
            ))
    return findings, False


def detect_engine_omissions(
    tournament: dict[str, Any],
) -> tuple[list[Finding], bool]:
    """Reads optional `engine_todo_clusters` section. Skip if absent."""
    clusters = tournament.get("engine_todo_clusters")
    if not clusters:
        return [], True

    findings: list[Finding] = []
    for cluster in clusters:
        size = int(cluster.get("affected_card_count", 0) or 0)
        primitive = cluster.get("primitive", "?")
        if size >= ENGINE_OMISSION_TODO_CLUSTER:
            findings.append(Finding(
                category="engine_omission",
                severity="critical" if size >= 8 else "high",
                summary=(
                    f"{size} cards reference engine primitive `{primitive}` "
                    f"which doesn't exist"
                ),
                evidence={
                    "primitive": primitive,
                    "affected_cards": cluster.get("cards", []),
                    "count": size,
                },
                fix_dispatch="engine_extension",
                fix_brief=(
                    f"Implement engine primitive `{primitive}`. {size} "
                    f"cards depend on it; without it those cards are "
                    f"silent no-ops. Add the primitive to the engine "
                    f"module, wire the event/query into the relevant "
                    f"interceptor priority, then re-run regression."
                ),
            ))
    return findings, False


def detect_card_crashes(
    tournament: dict[str, Any],
) -> tuple[list[Finding], bool]:
    """Reads optional `card_errors` section. Skip if absent."""
    errors = tournament.get("card_errors")
    if not errors:
        return [], True

    findings: list[Finding] = []
    for card_name, trace in errors.items():
        findings.append(Finding(
            category="card_crash",
            severity="critical",
            summary=f"Card `{card_name}` raised during play",
            evidence={"card": card_name, "trace_excerpt": str(trace)[:400]},
            fix_dispatch="card_repair",
            fix_brief=(
                f"Repair card `{card_name}`. Trace excerpt is in the "
                f"evidence field; root-cause it (likely a wrong event "
                f"payload key or a missing helper import). Fix in the "
                f"card's archetype file. Do NOT loosen the engine to "
                f"accept the card's broken output."
            ),
        ))
    return findings, False


def detect_archetype_weakness(
    tournament: dict[str, Any],
    set_label: str,
    archetypes: list[str],
) -> tuple[list[Finding], bool]:
    """An archetype is structurally weak if winrate is very low.
    Severity + dispatch routing depends on whether there's a per-card lever
    within THAT archetype's own cards (filtered by `<arch>::` prefix)
    that could explain the loss via revision alone, vs the archetype
    losing uniformly with no card-level lever (true structural problem).

    A 0% archetype always flags as HIGH severity and routes to
    archetype_redesign — no amount of card-stat tweaking saves a deck
    that lost every single game.
    """
    summary = tournament.get("set_summary") or {}
    card_scores = tournament.get("card_scores") or {}
    if not summary:
        return [], True

    findings: list[Finding] = []

    for arch in archetypes:
        rec = summary.get(arch)
        if not rec:
            continue
        wr = float(rec.get("winrate", 0.0) or 0.0)
        gp = int(rec.get("games_played", 0) or 0)
        if gp < ARCHETYPE_WEAKNESS_MIN_GAMES or wr > ARCHETYPE_WEAKNESS_WINRATE:
            continue

        # Filter card_scores to cards belonging to THIS archetype only,
        # via the `<arch>::Card Name` deck-label prefix.
        arch_cards: dict[str, dict] = {}
        for ref, stats in card_scores.items():
            parsed = parse_card_ref(ref)
            if parsed and parsed[0] == arch:
                arch_cards[parsed[1]] = stats
        rates = [
            float(s.get("win_rate_in_play", 0.0) or 0.0)
            for s in arch_cards.values()
            if int(s.get("in_play_at_end", 0) or 0) >= 5
        ]

        # Hard rule: 0% (or near-zero) winrate always = structural problem.
        # Card-stat revision can't lift a deck that lost every game.
        if wr <= 0.05:
            max_dev = (
                max(abs(r - statistics.median(rates)) for r in rates)
                if len(rates) >= 3 else None
            )
            findings.append(Finding(
                category="archetype_weakness",
                severity="high",
                summary=(
                    f"Archetype `{arch}` lost {gp - rec.get('wins', 0)}/{gp} "
                    f"games (winrate {wr:.2f}) — structural redesign required, "
                    f"card revision insufficient."
                ),
                evidence={
                    "archetype": arch, "winrate": wr, "games": gp,
                    "per_card_variance_max": max_dev,
                    "archetype_card_count": len(arch_cards),
                },
                fix_dispatch="archetype_redesign",
                fix_brief=(
                    f"Redesign `{arch}`. The archetype's gameplay loop "
                    f"isn't closing in actual games. Read its strategy "
                    f"summary in the design doc, identify which step of "
                    f"the loop isn't happening, and fix the cause — "
                    f"could be: (a) AI never plays the key cards (then "
                    f"archetype's plan needs simpler triggers), (b) "
                    f"archetype lacks reach / interaction / finisher "
                    f"density, (c) the archetype's resource curve is "
                    f"misaligned with the engine's tempo. NOT a "
                    f"per-card-stat problem — a 0% deck is too far "
                    f"from viable for stat tweaks."
                ),
            ))
            continue

        # Otherwise: check for per-card lever within this archetype.
        has_card_lever = False
        max_dev = None
        if len(rates) >= 3:
            median = statistics.median(rates)
            max_dev = max(abs(r - median) for r in rates)
            has_card_lever = max_dev > CONTRIB_VARIANCE_THRESHOLD

        if has_card_lever:
            findings.append(Finding(
                category="archetype_weakness",
                severity="medium",
                summary=(
                    f"Archetype `{arch}` underperforms ({wr:.2f}) — per-card "
                    f"variance present, solvable by card revision."
                ),
                evidence={
                    "archetype": arch, "winrate": wr, "games": gp,
                    "per_card_variance_max": max_dev,
                    "archetype_card_count": len(arch_cards),
                },
                fix_dispatch="card_revision",
                fix_brief=(
                    f"Boost `{arch}`'s underperforming cards. Identify "
                    f"per-card win-contribution outliers within the "
                    f"archetype and tune costs / stats / rules text on "
                    f"the lowest-contribution cards."
                ),
            ))
        else:
            findings.append(Finding(
                category="archetype_weakness",
                severity="high",
                summary=(
                    f"Archetype `{arch}` underperforms uniformly ({wr:.2f}) "
                    f"— no per-card lever, structural redesign required."
                ),
                evidence={
                    "archetype": arch, "winrate": wr, "games": gp,
                    "per_card_variance_max": max_dev,
                    "archetype_card_count": len(arch_cards),
                },
                fix_dispatch="archetype_redesign",
                fix_brief=(
                    f"Redesign `{arch}`. Card stats aren't the lever — "
                    f"the archetype's gameplay loop itself doesn't close. "
                    f"Read the archetype's strategy summary in the design "
                    f"doc and identify which step of the loop isn't "
                    f"happening in actual games."
                ),
            ))
    return findings, False


# =============================================================================
# Public API
# =============================================================================

def run_audit(
    tournament: dict[str, Any],
    set_label: str,
    archetypes: list[str],
    cycle: int,
) -> AuditReport:
    findings: list[Finding] = []
    skipped: list[str] = []

    detectors = [
        ("ai_omissions",     lambda: detect_ai_omissions(tournament)),
        ("mechanic_dead_ends", lambda: detect_mechanic_dead_ends(tournament)),
        ("engine_omissions", lambda: detect_engine_omissions(tournament)),
        ("card_crashes",     lambda: detect_card_crashes(tournament)),
        ("archetype_weakness", lambda: detect_archetype_weakness(
            tournament, set_label, archetypes
        )),
    ]

    for name, fn in detectors:
        results, was_skipped = fn()
        if was_skipped:
            skipped.append(name)
        findings.extend(results)

    actionable = bool([f for f in findings if f.severity in ("critical", "high")])

    return AuditReport(
        set_label=set_label,
        cycle=cycle,
        findings=findings,
        has_actionable_findings=actionable,
        skipped_detectors=skipped,
    )


def should_continue_audit_loop(
    report: AuditReport,
    *,
    cycle: int,
    max_cycles: int = DEFAULT_MAX_AUDIT_CYCLES,
) -> bool:
    """True if the orchestrator should run another audit cycle."""
    if not report.has_actionable_findings:
        return False
    if cycle >= max_cycles:
        return False
    return True


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tournament", type=Path, required=True)
    ap.add_argument("--set", dest="set_label", required=True)
    ap.add_argument("--archetypes", default="")
    ap.add_argument("--cycle", type=int, default=1)
    ap.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_AUDIT_CYCLES)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    tournament = json.loads(args.tournament.read_text(encoding="utf-8"))
    archetypes = [a.strip() for a in args.archetypes.split(",") if a.strip()]

    report = run_audit(tournament, args.set_label, archetypes, args.cycle)

    payload = json.dumps(report.to_dict(), indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(payload + "\n")

    if not should_continue_audit_loop(report, cycle=args.cycle, max_cycles=args.max_cycles):
        return 0
    return 2  # exit 2 = "more cycles needed"


if __name__ == "__main__":
    raise SystemExit(main())
