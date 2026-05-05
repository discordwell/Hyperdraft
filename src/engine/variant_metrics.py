"""Stable summaries for configurable game-rule variants."""

from __future__ import annotations

from typing import Any


MTG_BASELINE_RULES: dict[str, Any] = {
    "starting_life": 20,
    "opening_hand_size": 7,
    "draw_step_cards": 1,
    "max_mulligans": 7,
    "base_lands_allowed_per_turn": 1,
    "max_hand_size": 7,
    "first_player_draws": False,
    "empty_library_draw_loses": True,
    "clear_damage_on_cleanup": True,
}


def _state(obj: Any) -> Any:
    return getattr(obj, "state", obj)


def variant_rule_summary(game_or_state: Any) -> dict[str, Any]:
    """Return current rule knobs and deviations from the MTG baseline."""
    state = _state(game_or_state)
    rules = {
        key: getattr(state, key)
        for key in MTG_BASELINE_RULES
        if hasattr(state, key)
    }
    deviations = {
        key: {
            "baseline": MTG_BASELINE_RULES[key],
            "actual": value,
        }
        for key, value in rules.items()
        if value != MTG_BASELINE_RULES[key]
    }
    return {
        "schema_version": "hyperdraft.engine.variant_rules.v1",
        "game_mode": getattr(state, "game_mode", "mtg"),
        "rules": rules,
        "deviations": deviations,
        "deviation_count": len(deviations),
        "is_mtg_baseline": len(deviations) == 0 and getattr(state, "game_mode", "mtg") == "mtg",
    }


__all__ = ["MTG_BASELINE_RULES", "variant_rule_summary"]
