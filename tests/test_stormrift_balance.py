"""Stormrift custom Hearthstone balance checks."""

from src.cards.hearthstone.stormrift import (
    EMBER_CHANNELER,
    IGNIS_HERO,
    PYROMANCER_DECK,
    RIFT_SPARK,
    STORMRIFT_DECKS,
    stormrift_balance_summary,
)


def test_stormrift_balance_summary_tracks_both_factions():
    summary = stormrift_balance_summary()

    assert set(summary) == {"Pyromancer", "Cryomancer"}
    for faction, profile in summary.items():
        assert profile["size"] == 30, faction
        assert profile["early_count"] >= 10, faction
        assert profile["minion_count"] >= 12, faction
        assert profile["spell_count"] >= 8, faction


def test_pyromancer_has_enough_resilient_early_minions_for_rift_storm():
    summary = stormrift_balance_summary()["Pyromancer"]
    names = [card.name for card in PYROMANCER_DECK]

    assert names.count("Pyroclasm Adept") == 1
    assert names.count("Rift Walker") == 1
    assert EMBER_CHANNELER.characteristics.toughness == 4
    assert summary["early_resilient_minions"] >= 5
    assert summary["early_durable_minions"] >= 3
    assert summary["fragile_one_health_minions"] <= 3


def test_stormrift_deck_registry_lengths_are_stable():
    assert {faction: len(deck) for faction, deck in STORMRIFT_DECKS.items()} == {
        "Pyromancer": 30,
        "Cryomancer": 30,
    }


def test_pyromancer_hero_power_matches_aggro_role():
    assert "Deal 2 damage" in IGNIS_HERO.text
    assert "Deal 2 damage" in RIFT_SPARK.text
