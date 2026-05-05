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
    decks_with_flags = 0
    curve_error_total = 0
    fill_rates: list[float] = []

    for metrics in deck_metrics.values():
        role_deficit_total += sum(int(v) for v in metrics.get("role_deficits", {}).values())
        curve_error_total += int(metrics.get("curve_error", 0) or 0)
        fill_rates.append(float(metrics.get("role_fill_rate", 0.0) or 0.0))
        if metrics.get("quality_flags"):
            decks_with_flags += 1

    return {
        "deck_count": len(deck_metrics),
        "avg_role_fill_rate": round(sum(fill_rates) / len(fill_rates), 3) if fill_rates else 0.0,
        "role_deficit_total": role_deficit_total,
        "curve_error_total": curve_error_total,
        "decks_with_quality_flags": decks_with_flags,
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

    report = {
        "schema_version": "hyperdraft.strategy_pass.v1",
        "seed": seed,
        "set_codes": card_sets,
        "ai": ai_summary,
        "decks": deck_metrics,
        "deck_summary": deck_summary,
        "variants": variants,
    }
    (out / "strategy_pass_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


__all__ = ["DEFAULT_DECK_SPECS", "run_strategy_pass_report"]
