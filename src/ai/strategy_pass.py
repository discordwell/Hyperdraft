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
        "variants": variants,
    }
    (out / "strategy_pass_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


__all__ = ["DEFAULT_DECK_SPECS", "run_strategy_pass_report"]
