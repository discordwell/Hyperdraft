"""Hearthstone deckbuilding quality checks."""

from src.cards.hearthstone.decks import (
    DRUID_DECK,
    HEARTHSTONE_DECKS,
    HEARTHSTONE_DECK_ROLES,
    WARLOCK_DECK,
    analyze_all_decks,
    analyze_deck_quality,
    validate_deck,
)


def test_all_hearthstone_decks_have_clean_quality_metrics():
    summaries = analyze_all_decks()

    assert set(summaries) == set(HEARTHSTONE_DECKS)
    for hero_class, summary in summaries.items():
        assert summary["role"] == HEARTHSTONE_DECK_ROLES[hero_class]
        assert summary["size"] == 30, hero_class
        assert summary["early_count"] >= 8, hero_class
        assert summary["minion_count"] >= 10, hero_class
        assert summary["dead_zero_minion_count"] == 0, hero_class
        assert summary["quality_flags"] == [], hero_class
        assert summary["role_quality_flags"] == [], hero_class


def test_control_decks_have_defensive_stabilizers():
    summaries = analyze_all_decks()

    assert summaries["Warrior"]["taunt_count"] >= 1
    assert summaries["Priest"]["taunt_count"] >= 2
    assert "Sen'jin Shieldmasta" in [card.name for card in HEARTHSTONE_DECKS["Warrior"]]


def test_deck_role_metrics_cover_each_strategy_family():
    summaries = analyze_all_decks()

    assert summaries["Hunter"]["role"] == "aggro"
    assert summaries["Hunter"]["early_count"] >= 14
    assert summaries["Warlock"]["role"] == "aggro"
    assert summaries["Warlock"]["minion_count"] >= 16

    assert summaries["Mage"]["role"] == "tempo"
    assert summaries["Mage"]["burn_count"] >= 6
    assert summaries["Rogue"]["role"] == "tempo"
    assert summaries["Rogue"]["early_count"] >= 12

    assert summaries["Warrior"]["role"] == "control"
    assert summaries["Warrior"]["draw_count"] >= 4
    assert summaries["Priest"]["role"] == "control"
    assert summaries["Priest"]["early_count"] >= 10

    assert summaries["Druid"]["role"] == "ramp"
    assert summaries["Druid"]["early_minion_count"] >= 1
    assert summaries["Druid"]["draw_count"] >= 5
    assert summaries["Druid"]["taunt_count"] >= 4
    assert summaries["Druid"]["top_heavy_count"] <= 7


def test_midrange_decks_have_dense_turn_three_to_five_curve():
    summaries = analyze_all_decks()

    assert summaries["Paladin"]["role"] == "midrange"
    assert summaries["Paladin"]["midgame_count"] >= 12
    assert summaries["Shaman"]["role"] == "midrange"
    assert summaries["Shaman"]["midgame_count"] >= 12


def test_druid_ramp_deck_has_midgame_stabilizer_before_top_end():
    names = [card.name for card in DRUID_DECK]
    summary = analyze_deck_quality(DRUID_DECK)

    assert "Sen'jin Shieldmasta" in names
    assert "River Crocolisk" in names
    assert names.count("Savage Roar") == 1
    assert "Stormwind Champion" not in names
    assert summary["early_minion_count"] == 1
    assert summary["average_cost"] < 4.3
    assert summary["top_heavy_count"] == 7


def test_warlock_zoo_uses_real_one_drops_over_dead_zero_minions():
    names = [card.name for card in WARLOCK_DECK]
    summary = analyze_deck_quality(WARLOCK_DECK)

    assert "Wisp" not in names
    assert names.count("Leper Gnome") == 2
    assert summary["early_count"] >= 18
    assert summary["dead_zero_minion_count"] == 0


def test_validate_deck_enforces_legendary_singleton_rule():
    deck = list(HEARTHSTONE_DECKS["Mage"])
    legendary = next(card for card in HEARTHSTONE_DECKS["Warrior"] if card.rarity == "Legendary")
    deck[0] = legendary
    deck[1] = legendary

    valid, error = validate_deck(deck)

    assert valid is False
    assert "Legendary card" in error
