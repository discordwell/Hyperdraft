"""
Tests for the 2-color deckbuilder added to the custom-set tournament.

Covers:
1. `pick_two_color_pair` returns a sensible pair for a multicolor set.
2. `pick_two_color_pair` falls back to mono when below threshold.
3. `build_set_deck_2color` produces a 60-card deck with a sane mana base.
4. Every non-land card in the deck is castable in the chosen 2 colors.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cards.custom import CUSTOM_SETS
from src.engine.mana import ManaCost
from src.engine.types import CardType, Color

from scripts.play.custom_set_tournament import (
    pick_two_color_pair,
    build_set_deck_2color,
    _resolve_dual_land,
    DUAL_LAND_NAME_BY_PAIR,
    card_types,
)


def _cost_colors(cd) -> set:
    cs = (cd.characteristics.mana_cost or "")
    try:
        return ManaCost.parse(cs).colors or set()
    except Exception:
        return set()


def test_pick_two_color_pair_jjk_returns_BR():
    """JJK has 15 Black-Red multicolor cards (Sukuna/Cursed theme)."""
    primary, secondary = pick_two_color_pair(CUSTOM_SETS["JJK"])
    assert secondary is not None, "JJK should pick a 2-color pair"
    assert {primary, secondary} == {Color.BLACK, Color.RED}, (
        f"JJK top pair should be BR; got {primary.name}-{secondary.name}"
    )


def test_pick_two_color_pair_pkh_falls_back_to_mono():
    """PKH has 0 multicolor cards — must fall back to mono."""
    primary, secondary = pick_two_color_pair(CUSTOM_SETS["PKH"])
    assert secondary is None, (
        f"PKH should mono-fallback; got pair {primary.name}-{secondary}"
    )


def test_pick_two_color_pair_below_threshold_falls_back():
    """HPW has only 2 cards in its top pair — below the 5-card threshold."""
    primary, secondary = pick_two_color_pair(
        CUSTOM_SETS["HPW"], threshold=5,
    )
    assert secondary is None, (
        f"HPW should mono-fallback at threshold=5; got {primary.name}-{secondary}"
    )


def test_dual_land_registry_covers_all_10_pairs():
    """Every 2-color combination should map to an OTJ Desert dual."""
    pairs = [
        (Color.WHITE, Color.BLUE),  (Color.WHITE, Color.BLACK),
        (Color.WHITE, Color.RED),   (Color.WHITE, Color.GREEN),
        (Color.BLUE,  Color.BLACK), (Color.BLUE,  Color.RED),
        (Color.BLUE,  Color.GREEN), (Color.BLACK, Color.RED),
        (Color.BLACK, Color.GREEN), (Color.RED,   Color.GREEN),
    ]
    for a, b in pairs:
        key = frozenset({a, b})
        assert key in DUAL_LAND_NAME_BY_PAIR, f"Pair {a.name}-{b.name} missing from DUAL_LAND_NAME_BY_PAIR"
    assert len(DUAL_LAND_NAME_BY_PAIR) == 10


def test_resolve_dual_land_returns_otj_desert_for_BR():
    """BR dual should resolve to Jagged Barrens (OTJ Desert cycle)."""
    dual = _resolve_dual_land(Color.BLACK, Color.RED)
    assert dual is not None, "BR dual missing from ALL_CARDS — OTJ not loaded?"
    assert dual.name == "Jagged Barrens"
    # Must produce both colors via text parsing.
    text = (getattr(dual, "text", "") or "")
    assert "Add {B} or {R}" in text, (
        f"Jagged Barrens should produce {{B}} or {{R}}; text was: {text[:200]}"
    )


def test_build_set_deck_2color_jjk_BR_has_60_cards():
    """JJK in 2-color mode produces a 60-card deck with the BR mana base."""
    cards = CUSTOM_SETS["JJK"]
    primary, secondary = pick_two_color_pair(cards)
    deck, info = build_set_deck_2color("JJK", cards, primary, secondary)

    assert len(deck) == 60, f"Deck should be 60 cards; got {len(deck)}"
    assert info["spell_count"] == 36, f"36 spells expected; got {info['spell_count']}"
    assert info["land_count"] == 24, f"24 lands expected; got {info['land_count']}"
    assert info["dual_land"] == "Jagged Barrens", (
        f"BR deck should include Jagged Barrens dual; got {info['dual_land']}"
    )
    # Mana base must include both basic colors.
    land_names = {c.name for c in deck if CardType.LAND in card_types(c)}
    assert any("Swamp" in n or "Mountain" in n for n in land_names), (
        f"BR deck mana base should include Swamp + Mountain; got {land_names}"
    )


def test_build_set_deck_2color_only_castable_spells():
    """No spell in the 2-color deck should require an off-pair mana pip."""
    cards = CUSTOM_SETS["JJK"]
    primary, secondary = pick_two_color_pair(cards)
    deck, _ = build_set_deck_2color("JJK", cards, primary, secondary)
    allowed = {primary, secondary}
    offcolor = []
    for cd in deck:
        if CardType.LAND in card_types(cd):
            continue
        cc = _cost_colors(cd)
        if cc - allowed:
            offcolor.append((cd.name, [c.name for c in cc]))
    assert not offcolor, f"Deck contains off-color spells: {offcolor[:3]}"


def test_build_set_deck_2color_includes_multicolor_cards():
    """A 2-color JJK deck should actually contain BR multicolor cards."""
    cards = CUSTOM_SETS["JJK"]
    primary, secondary = pick_two_color_pair(cards)
    deck, _ = build_set_deck_2color("JJK", cards, primary, secondary)
    multi = [
        c for c in deck
        if CardType.LAND not in card_types(c)
        and len(_cost_colors(c)) == 2
    ]
    assert multi, (
        "Deck should contain at least one 2-color spell — that's the whole "
        "point of switching to 2-color mode."
    )


if __name__ == "__main__":
    test_pick_two_color_pair_jjk_returns_BR()
    test_pick_two_color_pair_pkh_falls_back_to_mono()
    test_pick_two_color_pair_below_threshold_falls_back()
    test_dual_land_registry_covers_all_10_pairs()
    test_resolve_dual_land_returns_otj_desert_for_BR()
    test_build_set_deck_2color_jjk_BR_has_60_cards()
    test_build_set_deck_2color_only_castable_spells()
    test_build_set_deck_2color_includes_multicolor_cards()
    print("\nALL 2-COLOR TOURNAMENT TESTS PASSED!")
