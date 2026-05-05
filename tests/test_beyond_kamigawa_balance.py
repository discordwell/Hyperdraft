"""Beyond Kamigawa Yu-Gi-Oh! custom-set balance checks."""

from src.cards.yugioh.beyond.kamigawa import (
    kamigawa_balance_flags,
    kamigawa_balance_summary,
)


def test_kamigawa_balance_summary_tracks_all_archetypes():
    summary = kamigawa_balance_summary()

    assert set(summary) == {
        "samurai", "ninja", "spirit_dragons", "moonfolk", "modified",
    }
    for archetype, profile in summary.items():
        assert profile["size"] == 40, archetype
        assert profile["extra_size"] == 5, archetype
        assert profile["monster_count"] >= 12, archetype
        assert profile["low_level_monster_count"] >= 8, archetype
        assert profile["removal_count"] >= 5, archetype
        assert profile["copy_violations"] == [], archetype
        assert profile["balance_flags"] == [], archetype


def test_kamigawa_archetype_identities_stay_distinct():
    summary = kamigawa_balance_summary()

    assert summary["samurai"]["monster_count"] >= 20
    assert summary["ninja"]["spell_count"] >= 12
    assert summary["spirit_dragons"]["boss_monster_count"] >= 5
    assert summary["moonfolk"]["draw_count"] >= summary["samurai"]["draw_count"]
    assert summary["modified"]["equip_identity_count"] >= 8


def test_kamigawa_balance_flags_detect_off_role_profiles():
    assert "moonfolk_low_card_flow" in kamigawa_balance_flags("moonfolk", {
        "size": 40,
        "extra_size": 5,
        "copy_violations": [],
        "monster_count": 15,
        "low_level_monster_count": 10,
        "removal_count": 14,
        "pressure_monster_count": 2,
        "draw_count": 2,
    })
    assert "modified_too_much_base_pressure" in kamigawa_balance_flags("modified", {
        "size": 40,
        "extra_size": 5,
        "copy_violations": [],
        "monster_count": 18,
        "low_level_monster_count": 14,
        "removal_count": 8,
        "pressure_monster_count": 9,
        "equip_identity_count": 10,
    })
