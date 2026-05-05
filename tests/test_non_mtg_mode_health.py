"""Regression coverage for non-MTG mode wiring."""

from src.engine import (
    Event,
    EventType,
    Game,
    mode_health_summary,
    non_mtg_health_report,
)


def test_non_mtg_health_report_passes_for_supported_modes():
    report = non_mtg_health_report()

    assert report["schema_version"] == "hyperdraft.engine.non_mtg_health.v1"
    assert report["passed"] is True
    assert report["failed_modes"] == []
    assert set(report["modes"]) == {"hearthstone", "pokemon", "yugioh"}


def test_hearthstone_mode_health_reports_defaults():
    summary = mode_health_summary("hearthstone")

    assert summary["passed"] is True
    assert summary["subsystems"] == {
        "mana_system": "HearthstoneManaSystem",
        "combat_manager": "HearthstoneCombatManager",
        "turn_manager": "HearthstoneTurnManager",
    }
    assert summary["rules"] == {"max_hand_size": 10, "hand_size_limit": 10}
    assert summary["flags"]["overdraw_burns"] is True
    assert summary["flags"]["max_minions_on_board"] == 7
    assert summary["zones"]["missing_p1_zones"] == []
    assert summary["zones"]["missing_shared_zones"] == []


def test_pokemon_mode_health_reports_extra_zones_and_serialization_flags():
    summary = mode_health_summary("pokemon")

    assert summary["passed"] is True
    assert summary["subsystems"]["mana_system"] == "PokemonEnergySystem"
    assert summary["subsystems"]["combat_manager"] == "PokemonCombatManager"
    assert summary["subsystems"]["turn_manager"] == "PokemonTurnManager"
    assert summary["rules"] == {"max_hand_size": 999, "hand_size_limit": None}
    assert summary["flags"]["delegates_start_to_session"] is True
    assert summary["flags"]["uses_pokemon_card_serializer"] is True
    assert summary["flags"]["includes_game_log_in_state"] is True
    assert "active_spot" in summary["zones"]["player_zone_names"]
    assert "prize_cards" in summary["zones"]["player_zone_names"]
    assert "lost_zone" in summary["zones"]["shared_zone_names"]
    assert "stadium_zone" in summary["zones"]["shared_zone_names"]


def test_yugioh_mode_health_reports_zones_and_no_mana():
    summary = mode_health_summary("yugioh")

    assert summary["passed"] is True
    assert summary["subsystems"]["mana_system"] is None
    assert summary["subsystems"]["combat_manager"] == "YugiohCombatManager"
    assert summary["subsystems"]["turn_manager"] == "YugiohTurnManager"
    assert summary["rules"] == {"max_hand_size": 6, "hand_size_limit": None}
    assert summary["flags"]["delegates_start_to_session"] is True
    assert summary["flags"]["skips_turn_order_setup"] is True
    assert "monster_zone" in summary["zones"]["player_zone_names"]
    assert "extra_deck" in summary["zones"]["player_zone_names"]
    assert summary["zones"]["missing_p2_zones"] == []


def test_unknown_mode_health_fails_explicitly():
    summary = mode_health_summary("unknown")

    assert summary["supported"] is False
    assert summary["passed"] is False
    assert summary["failures"] == ["unsupported mode: 'unknown'"]


def test_hearthstone_empty_draw_without_hero_still_applies_fatigue_damage():
    game = Game(mode="hearthstone")
    player = game.add_player("P1")

    game.pipeline.emit(Event(type=EventType.DRAW, payload={"player": player.id, "count": 2}))

    assert player.fatigue_damage == 2
    assert player.life == 17
    assert player.has_lost is False
