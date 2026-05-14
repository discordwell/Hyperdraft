"""
Set-level depth report.

Given an engine name and a card registry (a dict[str, CardDefinition]),
produces a SetReport with:
- Per-card axis scores + code fingerprint
- Axis-fingerprint diversity (catches shallow design space)
- Code-fingerprint diversity (catches literal reskins)
- Top reskin clusters
- Per-axis distribution histograms
- Thin-card list (cards scoring 0 on >=3 axes)
- Set-health verdict (median depth, diversity ratios)

Usage:
    from src.depth.report import score_registry, save_report
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(
        registry=BEYOND_RAVNICA_CARDS,
        engine="pokemon",
        set_code="BRV",
    )
    save_report(report, "logs/depth_v2_brv.json")
"""

from __future__ import annotations

import json
import statistics
import tomllib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .axis_scorer import AxisScores, CardScore, score_card
from .engine_profiles import EngineProfile, get_profile


# ---------------------------------------------------------------------------
# Per-engine threshold calibration.
# ---------------------------------------------------------------------------
#
# Each engine ships a TOML corpus under `src/depth/calibration/<engine>.toml`
# that declares both the threshold values and a reference set whose actual
# scores those thresholds were chosen to honor. See those files for the
# rationale.
#
# These module-level constants are the FALLBACK floor for engines that
# don't yet have a calibration corpus (e.g. brand-new TCG implementations).
# They mirror the original MTG-baseline calibration recorded in commit
# 7a982116: median 2, axis 0.10, code 0.40, thin 0.80. Add a corpus file
# rather than tweaking these — these are an emergency backstop, not the
# place to pin a new engine's gates.
MEDIAN_DEPTH_TARGET = 2
AXIS_DIVERSITY_TARGET = 0.10
CODE_DIVERSITY_TARGET = 0.40
THIN_RATIO_MAX = 0.80


@dataclass(frozen=True)
class CalibrationCorpus:
    """Loaded calibration TOML for one engine.

    Use `load_calibration(engine)` to populate; threshold consumers should
    read `.thresholds_dict()` rather than the raw fields so future
    threshold additions stay backward-compatible.
    """

    engine: str
    reference_set: str
    reference_module: str
    reference_registry: str
    median_depth: float
    axis_diversity: float
    code_diversity: float
    thin_ratio: float
    gates_passing_min: int
    source_path: Optional[Path] = None

    def thresholds_dict(self) -> dict[str, float]:
        return {
            "median_depth": self.median_depth,
            "axis_diversity": self.axis_diversity,
            "code_diversity": self.code_diversity,
            "thin_ratio": self.thin_ratio,
        }


_CALIBRATION_DIR = Path(__file__).parent / "calibration"
_CALIBRATION_CACHE: dict[str, Optional[CalibrationCorpus]] = {}


def _fallback_corpus(engine: str) -> CalibrationCorpus:
    """Engines without a TOML corpus use the module-level defaults."""
    return CalibrationCorpus(
        engine=engine,
        reference_set="",
        reference_module="",
        reference_registry="",
        median_depth=MEDIAN_DEPTH_TARGET,
        axis_diversity=AXIS_DIVERSITY_TARGET,
        code_diversity=CODE_DIVERSITY_TARGET,
        thin_ratio=THIN_RATIO_MAX,
        gates_passing_min=0,
        source_path=None,
    )


def load_calibration(engine: str) -> CalibrationCorpus:
    """Load `<engine>.toml` from `src/depth/calibration/`.

    Returns a fallback corpus pinned to the module-level defaults when the
    file is missing — this is the path a brand-new engine takes before its
    reference set has been picked.
    """
    key = engine.lower()
    if key in _CALIBRATION_CACHE:
        cached = _CALIBRATION_CACHE[key]
        if cached is not None:
            return cached
        return _fallback_corpus(key)

    path = _CALIBRATION_DIR / f"{key}.toml"
    if not path.is_file():
        _CALIBRATION_CACHE[key] = None
        return _fallback_corpus(key)

    with path.open("rb") as f:
        data = tomllib.load(f)

    thresholds = data.get("thresholds", {})
    expected = data.get("expected", {})

    corpus = CalibrationCorpus(
        engine=data.get("engine", key),
        reference_set=data.get("reference_set", ""),
        reference_module=data.get("reference_module", ""),
        reference_registry=data.get("reference_registry", ""),
        median_depth=float(thresholds.get("median_depth", MEDIAN_DEPTH_TARGET)),
        axis_diversity=float(thresholds.get("axis_diversity", AXIS_DIVERSITY_TARGET)),
        code_diversity=float(thresholds.get("code_diversity", CODE_DIVERSITY_TARGET)),
        thin_ratio=float(thresholds.get("thin_ratio", THIN_RATIO_MAX)),
        gates_passing_min=int(expected.get("gates_passing_min", 0)),
        source_path=path,
    )
    _CALIBRATION_CACHE[key] = corpus
    return corpus


def list_calibrations() -> list[str]:
    """Return the names of engines that ship a calibration TOML corpus."""
    if not _CALIBRATION_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _CALIBRATION_DIR.glob("*.toml") if p.is_file()
    )


def reset_calibration_cache() -> None:
    """Drop the in-memory corpus cache. Tests use this to verify edits to
    a calibration TOML take effect without forcing a full process reload."""
    _CALIBRATION_CACHE.clear()


@dataclass
class ReskinCluster:
    """A group of cards sharing one code-fingerprint."""

    fingerprint: str
    members: list[str]
    sample_helpers: list[str]
    sample_event_types: list[str]
    sample_zones: list[str]

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class AxisDistribution:
    """Per-axis distribution of scores across the set."""

    counts: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0, 3: 0})

    def add(self, score: int) -> None:
        self.counts[score] = self.counts.get(score, 0) + 1

    def as_dict(self) -> dict[str, int]:
        return {str(k): v for k, v in sorted(self.counts.items())}


@dataclass
class SetReport:
    """Aggregate depth report for one card registry."""

    engine: str
    set_code: str
    total_cards: int
    wired_cards: int  # cards with any callable
    per_card: list[dict] = field(default_factory=list)

    # Per-axis distribution
    state_dist: AxisDistribution = field(default_factory=AxisDistribution)
    decision_dist: AxisDistribution = field(default_factory=AxisDistribution)
    zone_dist: AxisDistribution = field(default_factory=AxisDistribution)
    asymmetry_dist: AxisDistribution = field(default_factory=AxisDistribution)
    synergy_dist: AxisDistribution = field(default_factory=AxisDistribution)

    # Total-depth distribution
    total_dist: dict[str, int] = field(default_factory=dict)
    median_total: float = 0.0
    mean_total: float = 0.0

    # Tier counts
    tier_counts: dict[str, int] = field(default_factory=dict)

    # Diversity
    distinct_axis_fingerprints: int = 0
    distinct_code_fingerprints: int = 0
    axis_diversity: float = 0.0
    code_diversity: float = 0.0

    # Reskin clusters (top N by member count)
    top_reskin_clusters: list[ReskinCluster] = field(default_factory=list)

    # Thin cards: scored 0 on ≥3 axes.
    thin_cards: list[str] = field(default_factory=list)
    thin_ratio: float = 0.0

    # Verdict (PASS / WARN / FAIL on each health check)
    health_checks: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # AxisDistribution serialization
        for axis in ("state_dist", "decision_dist", "zone_dist",
                     "asymmetry_dist", "synergy_dist"):
            d[axis] = self.__getattribute__(axis).as_dict()
        return d


# ---------------------------------------------------------------------------
# Building the report.
# ---------------------------------------------------------------------------


def score_registry(
    registry: dict,
    engine: str,
    set_code: str,
    profile: Optional[EngineProfile] = None,
    top_clusters: int = 10,
) -> SetReport:
    """Score every card in a registry, return a populated SetReport.

    SCP-engine sets carry their mechanics in metadata fields rather than
    callable slots, so they route to the dedicated metadata-driven scorer
    in :mod:`src.depth.scp_scorer` instead of the AST path used by
    MTG/Pokemon/Hearthstone/YGO.
    """
    if engine.lower() == "scp":
        from .scp_scorer import score_scp_registry
        return score_scp_registry(registry, set_code, top_clusters=top_clusters)
    prof = profile or get_profile(engine)

    per_card: list[CardScore] = []
    for name, card_def in registry.items():
        cs = score_card(card_def, prof)
        cs.name = name  # ensure registry key wins over card_def.name
        per_card.append(cs)

    wired = [cs for cs in per_card if not cs.is_unwired]
    report = SetReport(
        engine=engine,
        set_code=set_code,
        total_cards=len(per_card),
        wired_cards=len(wired),
    )

    # Per-card serialization + distribution
    totals: list[int] = []
    tier_counts: Counter[str] = Counter()
    axis_fps: list[tuple[int, int, int, int, int]] = []
    code_fp_clusters: dict[str, list[str]] = defaultdict(list)
    code_fp_samples: dict[str, CardScore] = {}
    thin_cards: list[str] = []

    for cs in per_card:
        s = cs.scores
        report.state_dist.add(s.state)
        report.decision_dist.add(s.decision)
        report.zone_dist.add(s.zone)
        report.asymmetry_dist.add(s.asymmetry)
        report.synergy_dist.add(s.synergy)
        totals.append(s.total)
        tier_counts[s.tier] += 1
        axis_fps.append(s.fingerprint)
        if not cs.is_unwired:
            code_fp_clusters[cs.code_fingerprint].append(cs.name)
            code_fp_samples.setdefault(cs.code_fingerprint, cs)
        if s.axes_zero_count() >= 3:
            thin_cards.append(cs.name)
        report.per_card.append({
            "name": cs.name,
            "scores": {
                "state": s.state,
                "decision": s.decision,
                "zone": s.zone,
                "asymmetry": s.asymmetry,
                "synergy": s.synergy,
                "total": s.total,
                "tier": s.tier,
            },
            "low_confidence_axes": list(s.low_confidence_axes),
            "axis_fingerprint": list(s.fingerprint),
            "code_fingerprint": cs.code_fingerprint,
            "callable_slots": list(cs.callable_slots),
            "is_unwired": cs.is_unwired,
            "helpers_called": sorted(cs.features.helpers_called),
            "event_types": sorted(cs.features.event_types),
            "zones_accessed": sorted(cs.features.zones_accessed),
        })

    # Totals / tiers
    if totals:
        report.median_total = float(statistics.median(totals))
        report.mean_total = round(statistics.mean(totals), 2)
    report.total_dist = {str(k): v for k, v in sorted(Counter(totals).items())}
    report.tier_counts = dict(tier_counts)

    # Diversity
    distinct_axis = len(set(axis_fps))
    distinct_code = len(code_fp_clusters)
    report.distinct_axis_fingerprints = distinct_axis
    report.distinct_code_fingerprints = distinct_code
    if per_card:
        report.axis_diversity = round(distinct_axis / len(per_card), 3)
    if wired:
        report.code_diversity = round(distinct_code / len(wired), 3)

    # Top reskin clusters
    clusters = sorted(code_fp_clusters.items(), key=lambda kv: -len(kv[1]))
    for fp, members in clusters[:top_clusters]:
        if len(members) < 2:
            continue
        sample = code_fp_samples[fp]
        report.top_reskin_clusters.append(ReskinCluster(
            fingerprint=fp,
            members=sorted(members),
            sample_helpers=sorted(sample.features.helpers_called),
            sample_event_types=sorted(sample.features.event_types),
            sample_zones=sorted(sample.features.zones_accessed),
        ))

    # Thin
    report.thin_cards = sorted(thin_cards)
    report.thin_ratio = round(len(thin_cards) / max(1, len(per_card)), 3)

    # Health — gates pulled from the per-engine calibration corpus when one
    # exists, else from the module-level defaults.
    corpus = load_calibration(engine)
    median_target = corpus.median_depth
    axis_target = corpus.axis_diversity
    code_target = corpus.code_diversity
    thin_max = corpus.thin_ratio

    def verdict(cond: bool) -> str:
        return "PASS" if cond else "FAIL"

    # median_depth: render integer thresholds without ".0" so the header
    # matches the BLB regression history ("median_depth >= 2").
    if float(median_target).is_integer():
        median_label = f"median_depth >= {int(median_target)}"
    else:
        median_label = f"median_depth >= {median_target:g}"

    report.health_checks = {
        median_label: verdict(report.median_total >= median_target),
        f"axis_diversity >= {axis_target:.2f}": verdict(report.axis_diversity >= axis_target),
        f"code_diversity >= {code_target:.2f}": verdict(report.code_diversity >= code_target),
        f"thin_ratio <= {thin_max:.2f}": verdict(report.thin_ratio <= thin_max),
    }
    return report


# ---------------------------------------------------------------------------
# Serialization.
# ---------------------------------------------------------------------------


def save_report(report: SetReport, path: str | Path) -> None:
    """Write the report to JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=False))


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


_KNOWN_SETS: dict[str, tuple[str, str, str]] = {
    # (engine, registry_module, registry_name)
    "BRV": ("pokemon", "src.cards.pokemon.beyond.ravnica", "BEYOND_RAVNICA_CARDS"),
    "SVS": ("pokemon", "src.cards.pokemon.sv_starter", "SV_STARTER_CARDS"),
    "ECL": ("mtg", "src.cards.lorwyn_eclipsed", "LORWYN_ECLIPSED_CARDS"),
    "TH": ("mtg", "src.cards.custom.temporal_horizons", "TEMPORAL_HORIZONS_CARDS"),
    "LOR": ("mtg", "src.cards.custom.lorwyn_custom", "LORWYN_CUSTOM_CARDS"),
    "WOE": ("mtg", "src.cards.wilds_of_eldraine", "WILDS_OF_ELDRAINE_CARDS"),
    "BLB": ("mtg", "src.cards.bloomburrow", "BLOOMBURROW_CARDS"),
    "DSK": ("mtg", "src.cards.duskmourn", "DUSKMOURN_CARDS"),
    "MKM": ("mtg", "src.cards.murders_karlov_manor", "MURDERS_KARLOV_MANOR_CARDS"),
    "FDN": ("mtg", "src.cards.foundations", "FOUNDATIONS_CARDS"),
    "LCI": ("mtg", "src.cards.lost_caverns_ixalan", "LOST_CAVERNS_IXALAN_CARDS"),
    "STORMRIFT": ("hearthstone", "src.cards.hearthstone.stormrift", "STORMRIFT_CARDS"),
    "YGO_OPT": ("yugioh", "src.cards.yugioh.ygo_optimized", "YGO_OPTIMIZED_CARDS"),
    "YGO_CLASSIC": ("yugioh", "src.cards.yugioh.ygo_classic", "YGO_CLASSIC_CARDS"),
    "YGO_STARTER": ("yugioh", "src.cards.yugioh.ygo_starter", "YGO_STARTER_CARDS"),
    "MNR": ("scp", "src.cards.scp.mnestic_reset", "MNR_CARDS"),
    "FBN": ("scp", "src.cards.scp.foundations_beyond", "FBN_CARDS"),
}


def _load_registry(set_code: str) -> tuple[str, dict]:
    """Resolve a set code to (engine_name, card_registry_dict).
    Tries _KNOWN_SETS first, then guesses common module-level names."""
    if set_code in _KNOWN_SETS:
        engine, module, name = _KNOWN_SETS[set_code]
        import importlib
        mod = importlib.import_module(module)
        reg = getattr(mod, name, None)
        if not isinstance(reg, dict):
            raise RuntimeError(f"{module}.{name} is not a dict (got {type(reg).__name__})")
        return engine, reg
    raise KeyError(
        f"Unknown set code: {set_code}. Known: {sorted(_KNOWN_SETS)}. "
        f"Pass --engine + --module + --registry directly to override."
    )


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Score a card set's mechanical depth.")
    parser.add_argument("--set", required=True, help="Set code (BRV, ECL, TH, etc.)")
    parser.add_argument("--engine", help="Override engine profile (else inferred from set code)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument("--summary-only", action="store_true",
                        help="Print only the set-level summary, not per-card detail")
    args = parser.parse_args(argv)

    engine_inferred, registry = _load_registry(args.set)
    engine = args.engine or engine_inferred
    report = score_registry(registry, engine=engine, set_code=args.set)

    if args.out:
        save_report(report, args.out)
        print(f"Wrote {args.out}")

    # Summary
    print(f"\n=== Depth Report: {args.set} ({engine}) ===")
    print(f"Cards: {report.total_cards}  Wired: {report.wired_cards}")
    print(f"Median depth: {report.median_total}  Mean: {report.mean_total}")
    print(f"Tier counts: {report.tier_counts}")
    print(f"Axis diversity: {report.axis_diversity}  ({report.distinct_axis_fingerprints}/{report.total_cards} distinct)")
    print(f"Code diversity: {report.code_diversity}  ({report.distinct_code_fingerprints}/{report.wired_cards} distinct)")
    print(f"Thin cards: {len(report.thin_cards)} ({report.thin_ratio:.1%})")
    print(f"\nHealth checks:")
    for k, v in report.health_checks.items():
        print(f"  {k:30s} {v}")
    if report.top_reskin_clusters:
        print(f"\nTop reskin clusters (size >= 2):")
        for c in report.top_reskin_clusters:
            print(f"  [{c.fingerprint}] {c.size} cards: {', '.join(c.members[:5])}{'...' if c.size>5 else ''}")
            print(f"    helpers: {c.sample_helpers}")
    if not args.summary_only and report.per_card:
        print(f"\nFirst 10 cards:")
        for entry in report.per_card[:10]:
            s = entry["scores"]
            print(f"  {entry['name']:36s} S={s['state']} D={s['decision']} Z={s['zone']} "
                  f"A={s['asymmetry']} Y={s['synergy']} | {s['total']} ({s['tier']})")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
