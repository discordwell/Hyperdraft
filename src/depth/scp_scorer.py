"""
SCP-engine depth scorer.

Unlike MTG/Pokemon/HS/YGO, SCP-engine sets (Mnestic Reset, Foundations
Beyond, …) carry their mechanic logic in **archetype-level engine handlers**
(``src/engine/scp.py``, ``src/engine/scp_turn.py``). Each card exposes
*metadata attributes* — ``scp_archetype``, ``scp_compleation_vector``,
``scp_on_reveal``, ``scp_alt_win`` — that the engine reads on each
relevant trigger.

The MTG-style AST scorer (``axis_scorer.score_card``) is blind to this
pattern because it only inspects ``setup_interceptors`` and the other
MTG/Pokemon callable slots. Pointing it at MNR or FBN scores 0/4 on every
health gate, which is a measurement bug, not a design bug.

This module scores SCP cards directly off the metadata fields, mapping the
shared five-axis rubric to SCP-specific signals:

* **S — State Coupling**: alt-win contribution, compleation vector,
  end-of-turn slots, and state-reading ``scp_keywords`` ("Mnestic",
  "Antimemetic", "Researched", "Compleation").
* **D — Decision Pressure**: branching trigger callables that the player
  resolves choices on (``scp_effect``, ``scp_on_test``,
  ``scp_on_test_fail``, ``scp_on_assign``, ``scp_on_activate`` …).
* **Z — Zone Movement**: zone-change triggers (``scp_on_reveal``,
  ``scp_on_contain``, ``scp_on_play``, ``scp_on_sacrifice`` …) plus
  movement keywords.
* **A — Asymmetry**: continuous-effect auras, alt-win pressure, high threat
  tier (containment ≥ 4 or hazard ≥ 4), and cross-player triggers
  (``scp_on_opponent_compleated`` etc.).
* **Y — Synergy Hook**: archetype binding, ``scp_bonus`` archetype
  conditional, and archetype-tagged keywords.

Returns the same :class:`SetReport` shape that
:func:`src.depth.report.score_registry` produces for AST-scored engines,
so calibration, CLI, and tests work without forking those paths.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

import statistics

from .axis_scorer import AxisScores, CardScore
from .ast_fingerprint import FeatureBag


# Keywords that, when present, signal each axis. Lowercased substring match.
_STATE_READING_KEYWORDS = ("mnestic", "antimeme", "antimemetic", "researched", "compleation")
_MOVEMENT_KEYWORDS = ("antimeme", "antimemetic", "containment", "expunge", "forget")
_ARCHETYPE_KEYWORDS = (
    "mnestic", "antimeme", "antimemetic", "compleation", "phyrexian",
    "eldrazi", "dragon", "leyline", "rift", "lich", "wurm", "spirit",
    "praetor", "planeswalker", "pact",
)


# ---------------------------------------------------------------------------
# Slot taxonomy — every scp_on_* / scp_effect callable mapped to one axis.
#
# Captured from a grep of `src/cards/scp/`. Cards may carry slots that the
# engine doesn't yet read; we count them for *design intent* regardless.
# Engine-gap is a separate concern from depth measurement.
# ---------------------------------------------------------------------------

_DECISION_SLOTS = frozenset({
    "scp_effect",
    "scp_on_test",
    "scp_on_test_fail",
    "scp_on_assign",
    "scp_on_open_dossier",
    "scp_on_activate",
    "scp_on_audit_return",
})

_ZONE_SLOTS = frozenset({
    "scp_on_reveal",
    "scp_on_contain",
    "scp_on_dragon_contain",
    "scp_on_archive",
    "scp_on_archive_stub",
    "scp_on_breach",
    "scp_on_play",
    "scp_on_sacrifice",
    "scp_on_anomaly_enter",
    "scp_on_memory_hole",
    "scp_on_rift_play",
})

_ASYMMETRY_SLOTS = frozenset({
    "scp_on_any_compleated",
    "scp_on_opponent_compleated",
    "scp_on_you_compleated",
    "scp_on_annihilation_wave_fire",
})

_STATE_END_SLOTS = frozenset({
    "scp_on_turn_end",
})

# Every callable slot, sorted for fingerprint stability.
_ALL_TRIGGER_SLOTS = sorted(
    _DECISION_SLOTS | _ZONE_SLOTS | _ASYMMETRY_SLOTS | _STATE_END_SLOTS
)


def _is_set(value) -> bool:
    """Truthy test that treats empty containers and zero as 'not set'."""
    if value is None or value == "" or value is False:
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, (list, dict, set, tuple, frozenset)) and len(value) == 0:
        return False
    return True


def _keywords_of(card_def) -> tuple[str, ...]:
    """Return scp_keywords as a lowercased tuple; empty if unset."""
    kw = getattr(card_def, "scp_keywords", None)
    if not kw:
        return ()
    return tuple(str(k).lower() for k in kw)


def _has_any_keyword(keywords: Iterable[str], needles: Iterable[str]) -> bool:
    """True if any needle appears as a substring of any keyword."""
    for kw in keywords:
        for needle in needles:
            if needle in kw:
                return True
    return False


def _count_callable_slots(card_def, slots: Iterable[str]) -> int:
    """How many of the given slot names hold a callable on this card."""
    return sum(1 for slot in slots if callable(getattr(card_def, slot, None)))


# ---------------------------------------------------------------------------
# Per-axis scoring.
# ---------------------------------------------------------------------------


def _score_state(card_def, keywords: tuple[str, ...]) -> int:
    """S — what game state does this card READ?"""
    score = 0
    if _is_set(getattr(card_def, "scp_alt_win", None)):
        score += 1  # alt-win contributors read the alt-win counter
    if _is_set(getattr(card_def, "scp_compleation_vector", 0)):
        score += 1  # vectors fire off scp_compleation per-object state
    if _has_any_keyword(keywords, _STATE_READING_KEYWORDS):
        score += 1
    if _count_callable_slots(card_def, _STATE_END_SLOTS) > 0:
        score += 1  # end-of-turn triggers read end-state
    return min(score, 3)


def _score_decision(card_def) -> int:
    """D — how many decision branches at resolution?"""
    return min(_count_callable_slots(card_def, _DECISION_SLOTS), 3)


def _score_zone(card_def, keywords: tuple[str, ...]) -> int:
    """Z — zone-change movement and resource transfer."""
    score = _count_callable_slots(card_def, _ZONE_SLOTS)
    if _has_any_keyword(keywords, _MOVEMENT_KEYWORDS):
        score += 1
    return min(score, 3)


def _score_asymmetry(card_def) -> int:
    """A — forces opponent response."""
    score = 0
    if _is_set(getattr(card_def, "scp_aura", None)):
        score += 1
    if _is_set(getattr(card_def, "scp_alt_win", None)):
        score += 1
    # High-threat anomalies / facilities pressure the opponent's containment
    # economy.
    containment = getattr(card_def, "scp_containment", 0) or 0
    hazard = getattr(card_def, "scp_hazard", 0) or 0
    if containment >= 4 or hazard >= 4:
        score += 1
    if _count_callable_slots(card_def, _ASYMMETRY_SLOTS) > 0:
        score += 1  # cross-player triggers create info imbalance
    return min(score, 3)


def _score_synergy(card_def, keywords: tuple[str, ...]) -> int:
    """Y — what does the card pull into the deck?"""
    score = 0
    if _is_set(getattr(card_def, "scp_archetype", None)):
        score += 1
    if _is_set(getattr(card_def, "scp_bonus", None)):
        score += 1
    if _has_any_keyword(keywords, _ARCHETYPE_KEYWORDS):
        score += 1
    return min(score, 3)


# ---------------------------------------------------------------------------
# Wired test + fingerprint.
# ---------------------------------------------------------------------------


# Non-callable mechanic-bearing fields. Any of these populated counts the
# card as wired even with no trigger callables.
_NONCALLABLE_MECHANIC_SLOTS = (
    "scp_alt_win",
    "scp_compleation_vector",
    "scp_aura",
    "scp_bonus",
    "scp_keywords",
)


def _is_wired(card_def) -> bool:
    """True if the card has any mechanic-bearing field populated.

    Identity-only fields (``scp_archetype``, ``scp_expansion``,
    ``scp_red_tape``) do **not** count. Stat-line (``scp_containment``,
    ``scp_hazard``, etc.) does not count.
    """
    for slot in _NONCALLABLE_MECHANIC_SLOTS:
        if _is_set(getattr(card_def, slot, None)):
            return True
    for slot in _ALL_TRIGGER_SLOTS:
        if callable(getattr(card_def, slot, None)):
            return True
    return False


def _code_fingerprint(card_def, keywords: tuple[str, ...]) -> str:
    """A reskin-detection fingerprint built from card-metadata shape.

    Two cards with identical fingerprints share an archetype, the same
    set of trigger slots, the same data-field presence pattern, and the
    same keyword set — everything but the per-instance values (stat-line,
    flavor, the specific alt-win key, the specific vector value).

    ``scp_alt_win`` is bucketed to ``w``/``-`` rather than embedding the
    raw key string: each Mandate ships a unique alt-win identifier, so
    embedding the raw value would explode every Mandate into its own
    cluster and defeat reskin detection precisely where it matters.
    """
    arch = getattr(card_def, "scp_archetype", None) or ""
    alt = "w" if _is_set(getattr(card_def, "scp_alt_win", None)) else "-"
    vec = "v" if _is_set(getattr(card_def, "scp_compleation_vector", 0)) else "-"
    aura = "a" if _is_set(getattr(card_def, "scp_aura", None)) else "-"
    bonus = "b" if _is_set(getattr(card_def, "scp_bonus", None)) else "-"
    # One bit per trigger slot, in sorted order — stable across runs.
    slot_bits = "".join(
        "1" if callable(getattr(card_def, slot, None)) else "0"
        for slot in _ALL_TRIGGER_SLOTS
    )
    kw_sig = "+".join(sorted(set(keywords)))
    return f"{arch}|{alt}{vec}{aura}{bonus}|{slot_bits}|{kw_sig}"


# ---------------------------------------------------------------------------
# Card-level entry point.
# ---------------------------------------------------------------------------


def score_scp_card(card_def) -> CardScore:
    """Score one SCP card. Mirrors :func:`axis_scorer.score_card` shape."""
    keywords = _keywords_of(card_def)
    if not _is_wired(card_def):
        # Unwired cards emit an empty fingerprint so they cannot accidentally
        # become a reskin cluster member downstream.
        return CardScore(
            name=getattr(card_def, "name", "<unknown>"),
            scores=AxisScores(),
            code_fingerprint="",
            features=FeatureBag(),
            callable_slots=(),
            is_unwired=True,
        )
    s = _score_state(card_def, keywords)
    d = _score_decision(card_def)
    z = _score_zone(card_def, keywords)
    a = _score_asymmetry(card_def)
    y = _score_synergy(card_def, keywords)
    # Slot names this card touches — useful for downstream debugging.
    slots: list[str] = []
    for slot in _ALL_TRIGGER_SLOTS:
        if callable(getattr(card_def, slot, None)):
            slots.append(slot)
    for slot in _NONCALLABLE_MECHANIC_SLOTS:
        if _is_set(getattr(card_def, slot, None)):
            slots.append(slot)
    return CardScore(
        name=getattr(card_def, "name", "<unknown>"),
        scores=AxisScores(state=s, decision=d, zone=z, asymmetry=a, synergy=y),
        code_fingerprint=_code_fingerprint(card_def, keywords),
        features=FeatureBag(),
        callable_slots=tuple(slots),
        is_unwired=False,
    )


# ---------------------------------------------------------------------------
# Registry-level entry point — produces a SetReport matching the MTG path.
# ---------------------------------------------------------------------------


def score_scp_registry(registry: dict, set_code: str, top_clusters: int = 10):
    """Score an SCP-engine card registry into a SetReport.

    Returns the same SetReport dataclass produced by the MTG-side scorer
    so calibration, CLI summary, and JSON output work without forking.
    """
    # Local import to avoid a circular dependency at module load.
    from .report import (
        AxisDistribution,
        ReskinCluster,
        SetReport,
        load_calibration,
    )

    per_card: list[CardScore] = []
    for name, card_def in registry.items():
        cs = score_scp_card(card_def)
        cs.name = name  # registry key wins (matches MTG path's convention)
        per_card.append(cs)

    wired = [cs for cs in per_card if not cs.is_unwired]
    report = SetReport(
        engine="scp",
        set_code=set_code,
        total_cards=len(per_card),
        wired_cards=len(wired),
    )

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
                "state": s.state, "decision": s.decision, "zone": s.zone,
                "asymmetry": s.asymmetry, "synergy": s.synergy,
                "total": s.total, "tier": s.tier,
            },
            "low_confidence_axes": list(s.low_confidence_axes),
            "axis_fingerprint": list(s.fingerprint),
            "code_fingerprint": cs.code_fingerprint,
            "callable_slots": list(cs.callable_slots),
            "is_unwired": cs.is_unwired,
            "helpers_called": [],
            "event_types": [],
            "zones_accessed": [],
        })

    if totals:
        report.median_total = float(statistics.median(totals))
        report.mean_total = round(statistics.mean(totals), 2)
    report.total_dist = {str(k): v for k, v in sorted(Counter(totals).items())}
    report.tier_counts = dict(tier_counts)

    distinct_axis = len(set(axis_fps))
    distinct_code = len(code_fp_clusters)
    report.distinct_axis_fingerprints = distinct_axis
    report.distinct_code_fingerprints = distinct_code
    if per_card:
        report.axis_diversity = round(distinct_axis / len(per_card), 3)
    if wired:
        report.code_diversity = round(distinct_code / len(wired), 3)

    clusters = sorted(code_fp_clusters.items(), key=lambda kv: -len(kv[1]))
    for fp, members in clusters[:top_clusters]:
        if len(members) < 2:
            continue
        report.top_reskin_clusters.append(ReskinCluster(
            fingerprint=fp,
            members=sorted(members),
            sample_helpers=[],
            sample_event_types=[],
            sample_zones=[],
        ))

    report.thin_cards = sorted(thin_cards)
    report.thin_ratio = round(len(thin_cards) / max(1, len(per_card)), 3)

    corpus = load_calibration("scp")
    median_target = corpus.median_depth
    axis_target = corpus.axis_diversity
    code_target = corpus.code_diversity
    thin_max = corpus.thin_ratio

    def verdict(cond: bool) -> str:
        return "PASS" if cond else "FAIL"

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
