"""Hearthstone deckbuilding quality checks."""

from src.cards.hearthstone.decks import (
    HEARTHSTONE_DECKS,
    WARLOCK_DECK,
    analyze_all_decks,
    analyze_deck_quality,
    validate_deck,
)


def test_all_hearthstone_decks_have_clean_quality_metrics():
    summaries = analyze_all_decks()

    assert set(summaries) == set(HEARTHSTONE_DECKS)
    for hero_class, summary in summaries.items():
        assert summary["size"] == 30, hero_class
        assert summary["early_count"] >= 8, hero_class
        assert summary["minion_count"] >= 10, hero_class
        assert summary["dead_zero_minion_count"] == 0, hero_class
        assert summary["quality_flags"] == [], hero_class


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
