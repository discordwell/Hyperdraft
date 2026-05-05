"""Measurement-first strategy pass report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from src.ai.benchmark_scenarios import run_fixed_decision_benchmark
from src.decks.heuristics import analyze_deck_quality, build_heuristic_deck
from src.engine import Game, variant_rule_summary


DEFAULT_DECK_SPECS: tuple[tuple[str, str, list[str]], ...] = (
    ("aggro_r", "Aggro", ["R"]),
    ("tempo_u", "Tempo", ["U"]),
    ("midrange_g", "Midrange", ["G"]),
    ("control_wu", "Control", ["W", "U"]),
    ("ramp_g", "Ramp", ["G"]),
)


def _summarize_deck_metrics(deck_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    role_deficit_total = 0
    role_deficits_by_role: dict[str, int] = {}
    decks_with_flags = 0
    curve_error_total = 0
    fill_rates: list[float] = []
    functional_rates: list[float] = []
    textless_nonland_total = 0
    worst_curve_deck = ""
    worst_curve_error = -1

    for label, metrics in deck_metrics.items():
        for role, deficit in (metrics.get("role_deficits", {}) or {}).items():
            amount = int(deficit)
            role_deficit_total += amount
            role_deficits_by_role[role] = role_deficits_by_role.get(role, 0) + amount
        curve_error = int(metrics.get("curve_error", 0) or 0)
        curve_error_total += curve_error
        if curve_error > worst_curve_error:
            worst_curve_deck = label
            worst_curve_error = curve_error
        fill_rates.append(float(metrics.get("role_fill_rate", 0.0) or 0.0))
        functional_rates.append(float(metrics.get("functional_nonland_ratio", 0.0) or 0.0))
        textless_nonland_total += int(metrics.get("textless_nonland_count", 0) or 0)
        if metrics.get("quality_flags"):
            decks_with_flags += 1

    return {
        "deck_count": len(deck_metrics),
        "avg_role_fill_rate": round(sum(fill_rates) / len(fill_rates), 3) if fill_rates else 0.0,
        "avg_functional_nonland_ratio": round(sum(functional_rates) / len(functional_rates), 3) if functional_rates else 0.0,
        "textless_nonland_total": textless_nonland_total,
        "role_deficit_total": role_deficit_total,
        "role_deficits_by_role": dict(sorted(role_deficits_by_role.items())),
        "curve_error_total": curve_error_total,
        "worst_curve_error_deck": worst_curve_deck,
        "worst_curve_error": max(0, worst_curve_error),
        "decks_with_quality_flags": decks_with_flags,
    }


def _summarize_variants(variants: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "variant_count": len(variants),
        "mtg_baseline_count": sum(1 for metrics in variants.values() if metrics.get("is_mtg_baseline")),
        "deviation_total": sum(int(metrics.get("deviation_count", 0) or 0) for metrics in variants.values()),
    }


def _quality_gate(ai_summary: dict[str, Any], deck_summary: dict[str, Any], variant_summary: dict[str, Any]) -> dict[str, Any]:
    ai_passed = ai_summary.get("scenario_pass_rate") == 1.0 and ai_summary.get("target_accuracy") in (None, 1.0)
    decks_passed = (
        deck_summary.get("role_deficit_total") == 0
        and deck_summary.get("curve_error_total") == 0
        and deck_summary.get("decks_with_quality_flags") == 0
    )
    variants_passed = variant_summary.get("mtg_baseline_count") == 1
    return {
        "passed": bool(ai_passed and decks_passed and variants_passed),
        "ai_passed": bool(ai_passed),
        "decks_passed": bool(decks_passed),
        "variants_passed": bool(variants_passed),
    }


def run_strategy_pass_report(
    output_dir: str | Path,
    *,
    seed: int = 17,
    set_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Run the compact strategy-pass measurement suite and write a JSON report."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    card_sets = list(set_codes or ["FDN"])

    ai_summary = run_fixed_decision_benchmark(out / "ai", seed=seed)
    deck_metrics = {}
    for label, archetype, colors in DEFAULT_DECK_SPECS:
        deck = build_heuristic_deck(
            name=f"{label} metrics",
            archetype=archetype,
            colors=colors,
            set_codes=card_sets,
            seed=seed,
        )
        deck_metrics[label] = analyze_deck_quality(deck, set_codes=card_sets)
    deck_summary = _summarize_deck_metrics(deck_metrics)

    variants = {
        "mtg_baseline": variant_rule_summary(Game()),
        "high_resource": variant_rule_summary(Game(starting_life=25, first_player_draws=True, draw_step_cards=2)),
        "persistent_damage": variant_rule_summary(Game(clear_damage_on_cleanup=False)),
    }
    variant_summary = _summarize_variants(variants)
    quality_gate = _quality_gate(ai_summary, deck_summary, variant_summary)

    report = {
        "schema_version": "hyperdraft.strategy_pass.v1",
        "seed": seed,
        "set_codes": card_sets,
        "ai": ai_summary,
        "decks": deck_metrics,
        "deck_summary": deck_summary,
        "variants": variants,
        "variant_summary": variant_summary,
        "quality_gate": quality_gate,
    }
    (out / "strategy_pass_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


__all__ = ["DEFAULT_DECK_SPECS", "run_strategy_pass_report"]
