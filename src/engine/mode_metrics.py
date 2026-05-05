"""Structural health metrics for supported non-MTG game modes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .game import Game


NON_MTG_MODES: tuple[str, ...] = ("hearthstone", "pokemon", "yugioh")

MODE_HEALTH_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "hearthstone": {
        "adapter": "hearthstone",
        "max_hand_size": 10,
        "hand_size_limit": 10,
        "mana_system": "HearthstoneManaSystem",
        "combat_manager": "HearthstoneCombatManager",
        "turn_manager": "HearthstoneTurnManager",
        "player_zones": ("library", "hand", "graveyard"),
        "shared_zones": ("battlefield", "stack", "exile", "command"),
        "flags": {
            "delegates_start_to_session": False,
            "skips_turn_order_setup": False,
            "uses_pokemon_card_serializer": False,
            "includes_game_log_in_state": False,
            "overdraw_burns": True,
            "max_minions_on_board": 7,
        },
    },
    "pokemon": {
        "adapter": "pokemon",
        "max_hand_size": 999,
        "hand_size_limit": None,
        "mana_system": "PokemonEnergySystem",
        "combat_manager": "PokemonCombatManager",
        "turn_manager": "PokemonTurnManager",
        "player_zones": (
            "library",
            "hand",
            "graveyard",
            "active_spot",
            "bench",
            "prize_cards",
        ),
        "shared_zones": (
            "battlefield",
            "stack",
            "exile",
            "command",
            "lost_zone",
            "stadium_zone",
        ),
        "flags": {
            "delegates_start_to_session": True,
            "skips_turn_order_setup": False,
            "uses_pokemon_card_serializer": True,
            "includes_game_log_in_state": True,
            "overdraw_burns": False,
            "max_minions_on_board": None,
        },
    },
    "yugioh": {
        "adapter": "yugioh",
        "max_hand_size": 6,
        "hand_size_limit": None,
        "mana_system": None,
        "combat_manager": "YugiohCombatManager",
        "turn_manager": "YugiohTurnManager",
        "player_zones": (
            "library",
            "hand",
            "graveyard",
            "monster_zone",
            "spell_trap_zone",
            "field_spell_zone",
            "pendulum_zone",
            "extra_deck",
            "banished",
        ),
        "shared_zones": ("battlefield", "stack", "exile", "command"),
        "flags": {
            "delegates_start_to_session": True,
            "skips_turn_order_setup": True,
            "uses_pokemon_card_serializer": False,
            "includes_game_log_in_state": True,
            "overdraw_burns": False,
            "max_minions_on_board": None,
        },
    },
}


def _class_name(value: object | None) -> str | None:
    if value is None:
        return None
    return value.__class__.__name__


def _expect_equal(
    failures: list[str],
    label: str,
    expected: object,
    actual: object,
) -> None:
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


def _player_zone_keys(zone_names: Iterable[str], player_id: str) -> list[str]:
    return [f"{zone_name}_{player_id}" for zone_name in zone_names]


def mode_health_summary(mode: str) -> dict[str, Any]:
    """Return a deterministic structural health report for one game mode."""

    expected = MODE_HEALTH_EXPECTATIONS.get(mode)
    if expected is None:
        return {
            "schema_version": "hyperdraft.engine.mode_health.v1",
            "requested_mode": mode,
            "supported": False,
            "passed": False,
            "failures": [f"unsupported mode: {mode!r}"],
        }

    game = Game(mode=mode)
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    adapter = game.mode_adapter

    actual_player_zone_keys = set(game.state.zones)
    expected_p1_zones = set(_player_zone_keys(expected["player_zones"], p1.id))
    expected_p2_zones = set(_player_zone_keys(expected["player_zones"], p2.id))
    expected_shared_zones = set(expected["shared_zones"])

    missing_p1_zones = sorted(expected_p1_zones - actual_player_zone_keys)
    missing_p2_zones = sorted(expected_p2_zones - actual_player_zone_keys)
    missing_shared_zones = sorted(expected_shared_zones - actual_player_zone_keys)

    flags = {
        "delegates_start_to_session": adapter.delegates_start_to_session(),
        "skips_turn_order_setup": adapter.skips_turn_order_setup(),
        "uses_pokemon_card_serializer": adapter.uses_pokemon_card_serializer(),
        "includes_game_log_in_state": adapter.includes_game_log_in_state(),
        "overdraw_burns": adapter.overdraw_burns(game.state),
        "max_minions_on_board": adapter.max_minions_on_board(p1.id, game.state),
    }

    subsystems = {
        "mana_system": _class_name(game.mana_system),
        "combat_manager": _class_name(game.combat_manager),
        "turn_manager": _class_name(game.turn_manager),
    }

    rules = {
        "max_hand_size": game.state.max_hand_size,
        "hand_size_limit": adapter.hand_size_limit(p1, game.state),
    }

    failures: list[str] = []
    _expect_equal(failures, "adapter", expected["adapter"], adapter.mode)
    _expect_equal(failures, "state.game_mode", mode, game.state.game_mode)
    for key, expected_value in expected["flags"].items():
        _expect_equal(failures, f"flags.{key}", expected_value, flags[key])
    for key in ("mana_system", "combat_manager", "turn_manager"):
        _expect_equal(failures, f"subsystems.{key}", expected[key], subsystems[key])
    for key in ("max_hand_size", "hand_size_limit"):
        _expect_equal(failures, f"rules.{key}", expected[key], rules[key])
    if missing_p1_zones:
        failures.append(f"missing P1 zones: {missing_p1_zones}")
    if missing_p2_zones:
        failures.append(f"missing P2 zones: {missing_p2_zones}")
    if missing_shared_zones:
        failures.append(f"missing shared zones: {missing_shared_zones}")

    return {
        "schema_version": "hyperdraft.engine.mode_health.v1",
        "requested_mode": mode,
        "resolved_adapter_mode": adapter.mode,
        "state_game_mode": game.state.game_mode,
        "supported": True,
        "passed": not failures,
        "failures": failures,
        "subsystems": subsystems,
        "rules": rules,
        "flags": flags,
        "zones": {
            "player_zone_names": list(expected["player_zones"]),
            "shared_zone_names": list(expected["shared_zones"]),
            "missing_p1_zones": missing_p1_zones,
            "missing_p2_zones": missing_p2_zones,
            "missing_shared_zones": missing_shared_zones,
            "zone_count": len(game.state.zones),
        },
    }


def non_mtg_health_report(modes: Iterable[str] = NON_MTG_MODES) -> dict[str, Any]:
    """Return a combined health report for all supported non-MTG modes."""

    mode_names = tuple(modes)
    summaries = {mode: mode_health_summary(mode) for mode in mode_names}
    failed_modes = sorted(mode for mode, summary in summaries.items() if not summary["passed"])
    return {
        "schema_version": "hyperdraft.engine.non_mtg_health.v1",
        "mode_count": len(mode_names),
        "modes": summaries,
        "failed_modes": failed_modes,
        "passed": not failed_modes,
    }
