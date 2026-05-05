"""Stormrift custom Hearthstone balance checks."""

from src.engine.game import Game
from src.engine.types import Event, EventType
from src.cards.hearthstone.stormrift import (
    EMBER_CHANNELER,
    FROST_RIFT,
    GLACIEL_HERO,
    IGNIS_HERO,
    PYROMANCER_DECK,
    RIFT_SPARK,
    STORMRIFT_DECKS,
    VOID_DRAIN,
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
        assert profile["balance_flags"] == [], faction


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


def test_cryomancer_hero_power_matches_control_role():
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_hearthstone_player(p1, GLACIEL_HERO, FROST_RIFT)
    game.setup_hearthstone_player(p2, IGNIS_HERO, RIFT_SPARK)

    events = game.pipeline.emit(Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={"hero_power_id": p1.hero_power_id, "player": p1.id},
        source=p1.hero_power_id,
    ))

    assert "Gain 3 Armor" in GLACIEL_HERO.text
    assert "Gain 3 Armor" in FROST_RIFT.text
    assert any(
        event.type == EventType.ARMOR_GAIN and event.payload["amount"] == 3
        for event in events
    )


def test_stormrift_faction_role_scores_stay_distinct():
    summary = stormrift_balance_summary()
    pyro = summary["Pyromancer"]
    cryo = summary["Cryomancer"]

    assert pyro["pressure_score"] > cryo["pressure_score"]
    assert pyro["hero_power_damage"] == 2
    assert pyro["charge_minions"] >= 3
    assert pyro["burn_cards"] >= 18

    assert cryo["defense_score"] > pyro["defense_score"]
    assert cryo["hero_power_armor"] == 3
    assert cryo["armor_score"] >= 6
    assert cryo["freeze_cards"] >= 4
    assert cryo["taunt_count"] >= 7


def test_void_drain_offsets_pyromancer_pressure():
    events = VOID_DRAIN.spell_effect(type("Obj", (), {"id": "void", "controller": "p1"})(), type(
        "State",
        (),
        {
            "zones": {},
            "objects": {},
            "players": {"p1": object(), "p2": object()},
        },
    )())

    assert "Gain 3 Armor" in VOID_DRAIN.text
    assert any(
        event.payload.get("amount") == 3
        for event in events
        if event.type.name == "ARMOR_GAIN"
    )
