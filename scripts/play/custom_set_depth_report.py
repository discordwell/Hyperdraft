"""Report mechanical depth for custom existing-game sets.

v2 (May 2026): replaces the legacy typography metric (word count + clause
separators + keyword set-membership) with a five-axis mechanical-depth
heuristic that catches reskins. The legacy fields are preserved with a
`legacy_` prefix for one release cycle so the spice loops can diff old
vs. new during migration.

!! depth_v2_median IS NOT A FREE-STANDING TARGET. !! The slice-N median-lift
retrofit gamed exactly this number by auto-wiring cards to emit generic
SCRY/SURVEIL/MILL/LIFE_CHANGE info-pulse events that did not match the cards'
printed text. The v2 scorer (`src/depth/axis_scorer.py`) now text-gates the
Asymmetry axis, so an info-pulse with no corroborating rules text scores 0 and
cannot move the median. Depth must come from REAL, text-matching effects that
pass strict /test-interceptors — never from emitting filler event types. If you
find yourself adding `_<set>_s<N>_*` / "median-lift" / "thin-bust" stub helpers
to raise this report's numbers, STOP: that is the prohibited pattern this guard
exists to defeat.

See:
- `src/depth/` for the v2 implementation
- `docs/sets/pkm_brv_depth_audit.md` for an example audit deliverable
- `/Users/discordwell/.claude/plans/async-moseying-bear.md` for the rubric design
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.depth import score_card, get_profile  # noqa: E402
from src.depth.report import score_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Legacy typography metric — kept for one release cycle as legacy_*.
# ---------------------------------------------------------------------------

CLAUSE_RE = re.compile(
    r"[.;:]|\bwhen\b|\bwhenever\b|\bat\b|\bif\b|\bunless\b|\buntil\b|"
    r"\bthen\b|\bchoose\b|\btarget\b|\bonce\b|\bafter\b|\bbefore\b|"
    r"\bactivate\b|\bequip\b|\bevolve\b|\bdiscard\b|\bsacrifice\b|"
    r"\bsearch\b|\bdraw\b|\bdestroy\b|\breturn\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[A-Za-z0-9+/-]+")


def _legacy_text_blob(card) -> str:
    parts: list[str] = []
    text = getattr(card, "text", "") or ""
    if text:
        parts.append(text)
    ability = getattr(card, "ability", None)
    if isinstance(ability, dict):
        parts.extend(str(ability.get(k, "")) for k in ("name", "text") if ability.get(k))
    for attack in getattr(card, "attacks", []) or []:
        if not isinstance(attack, dict):
            continue
        for key in ("name", "text"):
            val = attack.get(key)
            if val:
                parts.append(str(val))
        damage = attack.get("damage", 0)
        if damage:
            parts.append(f"damage {damage}")
    for field_name in ("ygo_spell_type", "ygo_trap_type", "ygo_monster_type"):
        val = getattr(card, field_name, None)
        if val:
            parts.append(str(val))
    return " ".join(parts)


def _legacy_card_depth(card) -> dict:
    """Original word-count + keyword scorer. Kept for diffing during the v1→v2
    migration cycle. DO NOT use as the primary metric."""
    text = _legacy_text_blob(card)
    chars = getattr(card, "characteristics", None)
    keywords = set()
    if chars is not None:
        keywords |= set(getattr(chars, "keywords", set()) or set())
    for ability in getattr(card, "abilities", []) or []:
        if isinstance(ability, dict) and ability.get("keyword"):
            keywords.add(str(ability["keyword"]).lower())
    words = len(WORD_RE.findall(text))
    clauses = len(CLAUSE_RE.findall(text))
    wired = int(any(
        getattr(card, attr, None)
        for attr in (
            "setup_interceptors", "setup_in_graveyard", "setup_in_hand",
            "battlecry", "deathrattle", "spell_effect", "resolve",
        )
    ))
    wired += sum(
        1
        for attack in getattr(card, "attacks", []) or []
        if isinstance(attack, dict) and attack.get("effect_fn")
    )
    if getattr(card, "ability", None) and getattr(card, "ability", {}).get("effect_fn"):
        wired += 1
    score = words + clauses * 4 + len(keywords) * 3 + min(wired, 3) * 8
    return {
        "legacy_score": score,
        "legacy_words": words,
        "legacy_clauses": clauses,
        "legacy_keywords": sorted(keywords),
        "legacy_wired_hooks": wired,
        "legacy_thin_threshold_default": 28,
    }


# ---------------------------------------------------------------------------
# Set registry — each set is bound to one engine profile.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DepthSet:
    label: str
    registry_path: str  # human-readable
    import_path: str
    registry_name: str
    engine: str  # depth profile key


SETS = {
    "modern_mtg": DepthSet(
        label="Modern MTG benchmark",
        registry_path="src.cards.bloomburrow:BLOOMBURROW_CARDS",
        import_path="src.cards.bloomburrow",
        registry_name="BLOOMBURROW_CARDS",
        engine="mtg",
    ),
    "mtg_pkh": DepthSet(
        label="MTG PKH",
        registry_path="src.cards.custom.pokemon_horizons:POKEMON_HORIZONS_CARDS",
        import_path="src.cards.custom.pokemon_horizons",
        registry_name="POKEMON_HORIZONS_CARDS",
        engine="mtg",
    ),
    "hearthstone_custom": DepthSet(
        label="Hearthstone custom",
        registry_path="src.cards.hearthstone.decks:custom",
        import_path="src.cards.hearthstone.decks",
        registry_name="custom",
        engine="hearthstone",
    ),
    "pokemon_brv": DepthSet(
        label="Pokemon Beyond Ravnica",
        registry_path="src.cards.pokemon.beyond.ravnica:BEYOND_RAVNICA_CARDS",
        import_path="src.cards.pokemon.beyond.ravnica",
        registry_name="BEYOND_RAVNICA_CARDS",
        engine="pokemon",
    ),
    "ygo_bk": DepthSet(
        label="YGO Beyond Kamigawa",
        registry_path="src.cards.yugioh.beyond.kamigawa:BEYOND_KAMIGAWA_CARDS",
        import_path="src.cards.yugioh.beyond.kamigawa",
        registry_name="BEYOND_KAMIGAWA_CARDS",
        engine="yugioh",
    ),
    # ---- Custom MTG sets in src/cards/custom/ ----
    # All score against the MTG engine profile. Added 2026-05-18 so the v2
    # depth audit can reach every custom set in one CLI sweep.
    "mtg_lrw": DepthSet(
        label="MTG Fae but Mid",
        registry_path="src.cards.custom.fae_but_mid:FAE_BUT_MID_CARDS",
        import_path="src.cards.custom.fae_but_mid",
        registry_name="FAE_BUT_MID_CARDS",
        engine="mtg",
    ),
    "mtg_tmh": DepthSet(
        label="MTG Temporal Horizons",
        registry_path="src.cards.custom.temporal_horizons:TEMPORAL_HORIZONS_CARDS",
        import_path="src.cards.custom.temporal_horizons",
        registry_name="TEMPORAL_HORIZONS_CARDS",
        engine="mtg",
    ),
    "mtg_swr": DepthSet(
        label="MTG Star Wars",
        registry_path="src.cards.custom.star_wars:STAR_WARS_CARDS",
        import_path="src.cards.custom.star_wars",
        registry_name="STAR_WARS_CARDS",
        engine="mtg",
    ),
    "mtg_dbz": DepthSet(
        label="MTG Dragon Ball",
        registry_path="src.cards.custom.dragon_ball:DRAGON_BALL_CARDS",
        import_path="src.cards.custom.dragon_ball",
        registry_name="DRAGON_BALL_CARDS",
        engine="mtg",
    ),
    "mtg_nrt": DepthSet(
        label="MTG Naruto",
        registry_path="src.cards.custom.naruto:NARUTO_CARDS",
        import_path="src.cards.custom.naruto",
        registry_name="NARUTO_CARDS",
        engine="mtg",
    ),
    "mtg_jjk": DepthSet(
        label="MTG Jujutsu Kaisen",
        registry_path="src.cards.custom.jujutsu_kaisen:JUJUTSU_KAISEN_CARDS",
        import_path="src.cards.custom.jujutsu_kaisen",
        registry_name="JUJUTSU_KAISEN_CARDS",
        engine="mtg",
    ),
    "mtg_aot": DepthSet(
        label="MTG Attack on Titan",
        registry_path="src.cards.custom.attack_on_titan:ATTACK_ON_TITAN_CARDS",
        import_path="src.cards.custom.attack_on_titan",
        registry_name="ATTACK_ON_TITAN_CARDS",
        engine="mtg",
    ),
    "mtg_hpw": DepthSet(
        label="MTG Harry Potter",
        registry_path="src.cards.custom.harry_potter:HARRY_POTTER_CARDS",
        import_path="src.cards.custom.harry_potter",
        registry_name="HARRY_POTTER_CARDS",
        engine="mtg",
    ),
    "mtg_mvl": DepthSet(
        label="MTG Marvel Avengers",
        registry_path="src.cards.custom.marvel_avengers:MARVEL_AVENGERS_CARDS",
        import_path="src.cards.custom.marvel_avengers",
        registry_name="MARVEL_AVENGERS_CARDS",
        engine="mtg",
    ),
    "mtg_mha": DepthSet(
        label="MTG My Hero Academia",
        registry_path="src.cards.custom.my_hero_academia:MY_HERO_ACADEMIA_CARDS",
        import_path="src.cards.custom.my_hero_academia",
        registry_name="MY_HERO_ACADEMIA_CARDS",
        engine="mtg",
    ),
    "mtg_ltr": DepthSet(
        label="MTG Lord of the Rings",
        registry_path="src.cards.custom.lord_of_the_rings:LORD_OF_THE_RINGS_CARDS",
        import_path="src.cards.custom.lord_of_the_rings",
        registry_name="LORD_OF_THE_RINGS_CARDS",
        engine="mtg",
    ),
    "mtg_zld": DepthSet(
        label="MTG Legend of Zelda",
        registry_path="src.cards.custom.legend_of_zelda:LEGEND_OF_ZELDA_CARDS",
        import_path="src.cards.custom.legend_of_zelda",
        registry_name="LEGEND_OF_ZELDA_CARDS",
        engine="mtg",
    ),
    "mtg_ghb": DepthSet(
        label="MTG Studio Ghibli",
        registry_path="src.cards.custom.studio_ghibli:STUDIO_GHIBLI_CARDS",
        import_path="src.cards.custom.studio_ghibli",
        registry_name="STUDIO_GHIBLI_CARDS",
        engine="mtg",
    ),
    "mtg_dms": DepthSet(
        label="MTG Demon Slayer",
        registry_path="src.cards.custom.demon_slayer:DEMON_SLAYER_CARDS",
        import_path="src.cards.custom.demon_slayer",
        registry_name="DEMON_SLAYER_CARDS",
        engine="mtg",
    ),
    "mtg_opc": DepthSet(
        label="MTG One Piece",
        registry_path="src.cards.custom.one_piece:ONE_PIECE_CARDS",
        import_path="src.cards.custom.one_piece",
        registry_name="ONE_PIECE_CARDS",
        engine="mtg",
    ),
    "mtg_spmc": DepthSet(
        label="MTG Spider-Man (custom)",
        registry_path="src.cards.custom.man_of_pider:SPIDER_MAN_CUSTOM_CARDS",
        import_path="src.cards.custom.man_of_pider",
        registry_name="SPIDER_MAN_CUSTOM_CARDS",
        engine="mtg",
    ),
    "mtg_finc": DepthSet(
        label="MTG Final Fantasy (custom)",
        registry_path="src.cards.custom.princess_catholicon:FINAL_FANTASY_CUSTOM_CARDS",
        import_path="src.cards.custom.princess_catholicon",
        registry_name="FINAL_FANTASY_CUSTOM_CARDS",
        engine="mtg",
    ),
    "mtg_tlac": DepthSet(
        label="MTG Avatar: TLA (custom)",
        registry_path="src.cards.custom.penultimate_avatar:AVATAR_TLA_CUSTOM_CARDS",
        import_path="src.cards.custom.penultimate_avatar",
        registry_name="AVATAR_TLA_CUSTOM_CARDS",
        engine="mtg",
    ),
}

# Convenience group for "all custom MTG sets" (excludes modern_mtg benchmark).
CUSTOM_MTG_SET_KEYS: tuple[str, ...] = (
    "mtg_pkh", "mtg_lrw", "mtg_tmh", "mtg_swr", "mtg_dbz", "mtg_nrt",
    "mtg_jjk", "mtg_aot", "mtg_hpw", "mtg_mvl", "mtg_mha", "mtg_ltr",
    "mtg_zld", "mtg_ghb", "mtg_dms", "mtg_opc", "mtg_spmc", "mtg_finc",
    "mtg_tlac",
)


def _import_module(path: str):
    import importlib
    with contextlib.redirect_stdout(sys.stderr):
        return importlib.import_module(path)


def _dedupe_cards(cards: Iterable) -> list:
    seen: set[int] = set()
    unique = []
    for card in cards:
        if id(card) in seen:
            continue
        seen.add(id(card))
        unique.append(card)
    return unique


def _load_cards(spec: DepthSet) -> tuple[list, Optional[dict]]:
    """Return (card_list, registry_dict_or_None). registry_dict is non-None when
    the source is a dict keyed by card name — used by the v2 scorer to map
    names to definitions for cluster reporting."""
    module = _import_module(spec.import_path)
    if spec.registry_name == "custom":
        cards = []
        with contextlib.redirect_stdout(sys.stderr):
            from src.cards.hearthstone.stormrift import STORMRIFT_DECKS
            from src.cards.hearthstone.frierenrift import FRIERENRIFT_DECKS
            from src.cards.hearthstone.riftclash import RIFTCLASH_DECKS
            custom_decks = {
                **{f"Stormrift {n}": d for n, d in STORMRIFT_DECKS.items()},
                **{f"Frierenrift {n}": d for n, d in FRIERENRIFT_DECKS.items()},
                **{f"Riftclash {n}": d for n, d in RIFTCLASH_DECKS.items()},
            }
            for deck in custom_decks.values():
                cards.extend(deck)
        return _dedupe_cards(cards), None
    registry = getattr(module, spec.registry_name)
    if isinstance(registry, dict):
        return list(registry.values()), registry
    return list(registry), None


# ---------------------------------------------------------------------------
# v2 + legacy per-card scoring.
# ---------------------------------------------------------------------------


def card_depth(card, profile=None) -> dict:
    """Score one card with the v2 rubric, with legacy fields appended.

    Returns a dict with primary `depth_v2_score`, `axis_scores`,
    `axis_fingerprint`, `code_fingerprint`, plus legacy_*.

    Back-compat (v1): also exposes `score`, `wired_hooks` aliases mapping
    onto the legacy fields, so existing depth-gate tests keep working.
    Calling without `profile` defaults to the MTG profile."""
    if profile is None:
        profile = get_profile("mtg")
    legacy = _legacy_card_depth(card)
    cs = score_card(card, profile)
    s = cs.scores
    return {
        "name": cs.name or getattr(card, "name", "unknown"),
        # v2 primary metric — 0-15
        "depth_v2_score": s.total,
        "axis_scores": {
            "state": s.state,
            "decision": s.decision,
            "zone": s.zone,
            "asymmetry": s.asymmetry,
            "synergy": s.synergy,
        },
        "tier": s.tier,
        "axis_fingerprint": list(s.fingerprint),
        "code_fingerprint": cs.code_fingerprint,
        "low_confidence_axes": list(s.low_confidence_axes),
        "callable_slots": list(cs.callable_slots),
        "is_unwired": cs.is_unwired,
        # legacy fields (one cycle)
        **legacy,
        # v1 back-compat aliases
        "score": legacy["legacy_score"],
        "wired_hooks": legacy["legacy_wired_hooks"],
        "text": _legacy_text_blob(card),
    }


def summarize_set(cards: list, *, engine: str = "mtg", registry: Optional[dict] = None,
                  thin_threshold: int = 28) -> dict:
    """Score a card list. When `registry` (a name→card dict) is provided, also
    run the full v2 set-level diversity report (reskin clusters etc.).

    Back-compat (v1): also exposes `avg_score`, `thin_count`, `thin_pct`,
    `wired_pct` aliases mapping onto the legacy fields, so existing
    depth-gate tests keep working. `engine` defaults to 'mtg'."""
    profile = get_profile(engine)
    rows = [card_depth(card, profile) for card in cards if getattr(card, "name", None)]
    if not rows:
        return {
            "card_count": 0,
            "depth_v2_median": 0,
            "depth_v2_mean": 0,
            "axis_diversity": 0,
            "code_diversity": 0,
            "thin_ratio": 0,
            "health_checks": {},
            "tier_counts": {},
            "top_reskin_clusters": [],
            # legacy
            "legacy_avg_score": 0,
            "legacy_median_score": 0,
            "legacy_thin_count": 0,
            "legacy_thin_pct": 0,
            "legacy_wired_pct": 0,
            # v1 back-compat aliases
            "avg_score": 0,
            "thin_count": 0,
            "thin_pct": 0,
            "wired_pct": 0,
        }
    totals_v2 = [r["depth_v2_score"] for r in rows]
    legacy_scores = [r["legacy_score"] for r in rows]
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    thin_v2 = [r for r in rows if sum(1 for v in r["axis_scores"].values() if v == 0) >= 3]
    legacy_thin = [r for r in rows if r["legacy_score"] < thin_threshold]

    # When we have the registry dict, run the full v2 set report for the
    # diversity ratios and reskin clusters (these need the merged FeatureBag
    # across attacks/abilities).
    diversity = {}
    if registry is not None:
        report = score_registry(registry, engine=engine, set_code="ad-hoc")
        diversity = {
            "axis_diversity": report.axis_diversity,
            "code_diversity": report.code_diversity,
            "distinct_axis_fingerprints": report.distinct_axis_fingerprints,
            "distinct_code_fingerprints": report.distinct_code_fingerprints,
            "top_reskin_clusters": [
                {"fingerprint": c.fingerprint, "size": c.size, "members": c.members[:10],
                 "helpers": c.sample_helpers}
                for c in report.top_reskin_clusters[:10]
            ],
            "health_checks": report.health_checks,
            "per_axis_distribution": {
                "state": report.state_dist.as_dict(),
                "decision": report.decision_dist.as_dict(),
                "zone": report.zone_dist.as_dict(),
                "asymmetry": report.asymmetry_dist.as_dict(),
                "synergy": report.synergy_dist.as_dict(),
            },
        }

    legacy_avg = round(statistics.mean(legacy_scores), 2)
    legacy_thin_count = len(legacy_thin)
    legacy_thin_pct = round(legacy_thin_count / len(rows) * 100, 1)
    legacy_wired_pct = round(
        sum(1 for r in rows if r["legacy_wired_hooks"] > 0) / len(rows) * 100, 1,
    )
    return {
        "card_count": len(rows),
        # v2 primary
        "depth_v2_mean": round(statistics.mean(totals_v2), 2),
        "depth_v2_median": round(statistics.median(totals_v2), 2),
        "tier_counts": tiers,
        "v2_thin_count": len(thin_v2),
        "v2_thin_ratio": round(len(thin_v2) / len(rows), 3),
        **diversity,
        # legacy (one cycle)
        "legacy_avg_score": legacy_avg,
        "legacy_median_score": round(statistics.median(legacy_scores), 2),
        "legacy_avg_words": round(statistics.mean(r["legacy_words"] for r in rows), 2),
        "legacy_thin_threshold": thin_threshold,
        "legacy_thin_count": legacy_thin_count,
        "legacy_thin_pct": legacy_thin_pct,
        "legacy_wired_pct": legacy_wired_pct,
        # v1 back-compat aliases (depth-gate tests, build_report consumers)
        "avg_score": legacy_avg,
        "thin_count": legacy_thin_count,
        "thin_pct": legacy_thin_pct,
        "wired_pct": legacy_wired_pct,
        # Sort thinnest by legacy_score first (v1 semantics — this is the
        # historical "thinnest cards" list), then v2 as tiebreaker.
        "thinnest": [
            {"name": r["name"], "depth_v2_score": r["depth_v2_score"],
             "axis_scores": r["axis_scores"], "legacy_score": r["legacy_score"],
             "text": r["text"][:180]}
            for r in sorted(rows, key=lambda r: (r["legacy_score"], r["depth_v2_score"], r["name"]))[:12]
        ],
    }


def build_report(set_names: list[str], thin_threshold: int) -> dict:
    # schema_version stays at v1 for back-compat with existing report
    # consumers (depth-gate tests, compare_custom_set_depth_reports). The v2
    # axis-scorer + diversity report ride alongside as extra keys.
    report = {
        "schema_version": "hyperdraft.custom_set_depth_report.v1",
        "schema_version_v2": "hyperdraft.custom_set_depth_report.v2",
        "thin_threshold": thin_threshold,
        "sets": {},
    }
    benchmark_v2_mean: Optional[float] = None
    benchmark_legacy_avg: Optional[float] = None
    if "modern_mtg" not in set_names:
        set_names = ["modern_mtg", *set_names]
    for name in set_names:
        spec = SETS[name]
        cards, registry = _load_cards(spec)
        summary = summarize_set(cards, engine=spec.engine, registry=registry,
                                thin_threshold=thin_threshold)
        summary["label"] = spec.label
        summary["registry"] = spec.registry_path
        summary["engine"] = spec.engine
        report["sets"][name] = summary
        if name == "modern_mtg":
            benchmark_v2_mean = summary["depth_v2_mean"]
            benchmark_legacy_avg = summary["legacy_avg_score"]
    if benchmark_v2_mean:
        for summary in report["sets"].values():
            summary["v2_benchmark_ratio"] = round(summary["depth_v2_mean"] / max(benchmark_v2_mean, 0.01), 3)
            if benchmark_legacy_avg:
                ratio = round(
                    summary["legacy_avg_score"] / max(benchmark_legacy_avg, 0.01), 3
                )
                summary["legacy_benchmark_ratio"] = ratio
                # v1 back-compat alias
                summary["benchmark_ratio"] = ratio
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sets", nargs="+",
        default=["mtg_pkh", "hearthstone_custom", "pokemon_brv", "ygo_bk"],
        choices=sorted(SETS),
        help="Set keys to report. modern_mtg is included as a benchmark automatically.",
    )
    parser.add_argument(
        "--all-custom-mtg", action="store_true",
        help="Shortcut for --sets covering every custom MTG set in src/cards/custom/.",
    )
    parser.add_argument("--thin-threshold", type=int, default=28,
                        help="Legacy thin threshold (kept for diffing during migration)")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    set_names = list(CUSTOM_MTG_SET_KEYS) if args.all_custom_mtg else args.sets
    report = build_report(set_names, args.thin_threshold)
    payload = json.dumps(report, indent=None if args.compact else 2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
