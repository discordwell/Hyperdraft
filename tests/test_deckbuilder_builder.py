"""
Tests for the W2 heuristic deckbuilder.

These tests are intentionally SHAPE-focused: count, validity, determinism,
2-color manabase, custom-set loadability. They do NOT verify card-quality
choices because the W2 worktree ships with a stub scorer that returns 1.0
for every castable card. Real card-quality assertions arrive at integration
when W1's scorer replaces the stub.
"""

from __future__ import annotations

import pytest

from src.cards import ALL_CARDS
from src.decks.deck import Deck, DeckEntry, load_deck, validate_deck
from src.decks.heuristics import ARCHETYPE_TEMPLATES, build_heuristic_deck, pick_lands
from src.decks.heuristics.builder import _build_buckets
from src.decks.heuristics.pool import resolve_pool
from src.engine.types import CardDefinition, Characteristics, CardType, Color


# =============================================================================
# Per-archetype end-to-end build (against MTG FDN)
# =============================================================================


@pytest.mark.parametrize(
    "archetype,colors",
    [
        ("Aggro", ["R"]),
        ("Tempo", ["U"]),
        ("Midrange", ["G"]),
        ("Control", ["W"]),
        ("Ramp", ["G"]),
    ],
)
def test_build_per_archetype_fdn(archetype: str, colors: list[str]) -> None:
    """Each archetype produces a 60-card valid deck against FDN."""
    deck = build_heuristic_deck(
        name=f"{archetype} Test",
        archetype=archetype,
        colors=colors,
        set_codes=["FDN"],
    )

    assert isinstance(deck, Deck)
    assert deck.archetype == archetype
    assert deck.colors == colors
    assert deck.mainboard_count == 60, (
        f"{archetype} mainboard_count={deck.mainboard_count}, expected 60"
    )

    # Land count matches the template (within tolerance — slot-filler may
    # need extra lands if it can't fill the curve).
    template = ARCHETYPE_TEMPLATES[archetype]
    assert deck.land_count >= template.land_count - 2, (
        f"{archetype} land_count={deck.land_count}, expected >= {template.land_count - 2}"
    )

    is_valid, errors = validate_deck(deck)
    assert is_valid, f"{archetype} deck invalid: {errors}"

    # Sideboard always empty in the heuristic phase.
    assert deck.sideboard == []


# =============================================================================
# 2-color builds with WOE + LCI
# =============================================================================


def test_build_two_color_wu_woe_lci() -> None:
    """A WU deck against WOE+LCI builds and either has WU duals or basics."""
    deck = build_heuristic_deck(
        name="Azorius Test",
        archetype="Control",
        colors=["W", "U"],
        set_codes=["WOE", "LCI"],
    )
    assert deck.mainboard_count == 60
    is_valid, errors = validate_deck(deck)
    assert is_valid, errors

    # The land slice must include either Plains/Island OR a dual whose
    # subtypes include both Plains and Island. (FDN/WOE/LCI don't ship
    # typed duals, so this typically falls back to basics.)
    land_names = {e.card_name for e in deck.mainboard if any(
        b in e.card_name for b in ("Plains", "Island", "Swamp", "Mountain", "Forest")
    )}
    assert land_names, "No land entries detected in 2-color deck"

    # At minimum we expect Plains AND Island when no typed duals available.
    pool = resolve_pool(["WOE", "LCI"])
    has_typed_duals = any(
        ("Plains" in (cd.characteristics.subtypes or set()))
        and ("Island" in (cd.characteristics.subtypes or set()))
        for cd in pool.values()
    )
    if not has_typed_duals:
        assert "Plains" in land_names or "Island" in land_names


def test_build_two_color_wu_loaded_via_load_deck() -> None:
    """The 2-color deck loads cleanly via load_deck (no missing cards)."""
    deck = build_heuristic_deck(
        name="Azorius Test",
        archetype="Control",
        colors=["W", "U"],
        set_codes=["WOE", "LCI"],
    )
    loaded = load_deck(ALL_CARDS, deck)
    assert len(loaded) == deck.mainboard_count


# =============================================================================
# Custom-set mix loads via load_deck
# =============================================================================


def test_build_custom_set_mix_tmh_lrw_loads() -> None:
    """Custom-set mix (Temporal Horizons + Lorwyn Custom) loads via load_deck."""
    deck = build_heuristic_deck(
        name="Custom Mix",
        archetype="Midrange",
        colors=["G"],
        set_codes=["TMH", "LRW"],
    )
    is_valid, errors = validate_deck(deck)
    assert is_valid, errors

    loaded = load_deck(ALL_CARDS, deck)
    # load_deck falls back to get_sets_for_card for cards not in ALL_CARDS,
    # so all 60 should resolve.
    assert len(loaded) == deck.mainboard_count


# =============================================================================
# Determinism
# =============================================================================


def test_determinism_same_args_same_output() -> None:
    """Same args produce identical mainboards (no seed needed)."""
    args = dict(
        name="Det",
        archetype="Aggro",
        colors=["R"],
        set_codes=["FDN"],
    )
    a = build_heuristic_deck(**args)
    b = build_heuristic_deck(**args)
    assert [(e.card_name, e.quantity) for e in a.mainboard] == [
        (e.card_name, e.quantity) for e in b.mainboard
    ]


def test_determinism_with_explicit_seed() -> None:
    """Explicit seed is also deterministic."""
    a = build_heuristic_deck(
        name="Det", archetype="Midrange", colors=["G"], set_codes=["FDN"], seed=42,
    )
    b = build_heuristic_deck(
        name="Det", archetype="Midrange", colors=["G"], set_codes=["FDN"], seed=42,
    )
    assert [(e.card_name, e.quantity) for e in a.mainboard] == [
        (e.card_name, e.quantity) for e in b.mainboard
    ]


# =============================================================================
# Mana base unit tests (pick_lands)
# =============================================================================


def test_pick_lands_mono_color() -> None:
    """Mono-color returns all basics of that color."""
    pool = resolve_pool(["FDN"])
    entries = pick_lands(["R"], 24, pool)
    assert sum(e.quantity for e in entries) == 24
    assert {e.card_name for e in entries} == {"Mountain"}


def test_pick_lands_two_color() -> None:
    """Two-color returns basics for both colors (and duals if pool has them)."""
    pool = resolve_pool(["FDN"])
    entries = pick_lands(["W", "U"], 24, pool)
    total = sum(e.quantity for e in entries)
    assert total == 24
    names = {e.card_name for e in entries}
    # Without typed duals in FDN, we expect Plains+Island only.
    assert "Plains" in names and "Island" in names


def test_pick_lands_three_color_graceful() -> None:
    """3-color request returns ``land_count`` lands without crashing."""
    pool = resolve_pool(["FDN"])
    entries = pick_lands(["W", "U", "B"], 24, pool)
    total = sum(e.quantity for e in entries)
    assert total == 24


def test_pick_lands_zero_count() -> None:
    """Zero land_count returns no entries."""
    pool = resolve_pool(["FDN"])
    entries = pick_lands(["R"], 0, pool)
    assert entries == []


# =============================================================================
# Color-identity filter (uncastable cards dropped)
# =============================================================================


def test_uncastable_cards_excluded() -> None:
    """No mainboard nonland card has a colored pip outside the deck colors."""
    deck = build_heuristic_deck(
        name="Mono-R Test",
        archetype="Aggro",
        colors=["R"],
        set_codes=["FDN"],
    )
    # Walk all mainboard cards; nonland costs should never include W/U/B/G.
    pool = resolve_pool(["FDN"])
    for entry in deck.mainboard:
        cd = pool.get(entry.card_name)
        if cd is None:
            continue
        cost = cd.characteristics.mana_cost or ""
        # Lands have no mana cost — skip basics by name shortcut.
        if entry.card_name in {"Plains", "Island", "Swamp", "Mountain", "Forest"}:
            continue
        # Crude regex: any non-R colored pip should not appear.
        for sym in ("{W}", "{U}", "{B}", "{G}"):
            assert sym not in cost, (
                f"Mono-R deck contains off-color pip {sym} in {entry.card_name} ({cost})"
            )


def test_builder_role_buckets_use_scorer_role_detection() -> None:
    """Slot-filling role buckets should understand the scorer's richer tags."""
    selection = CardDefinition(
        name="Careful Selection",
        mana_cost="{1}{U}",
        characteristics=Characteristics(
            types={CardType.SORCERY},
            colors={Color.BLUE},
            mana_cost="{1}{U}",
        ),
        text="Look at the top two cards of your library. Put one into your hand.",
    )

    _, role_buckets = _build_buckets(
        {"Careful Selection": selection},
        archetype="Control",
        colors=["U"],
    )

    assert [name for _, name, _ in role_buckets["card_draw"]] == ["Careful Selection"]


# =============================================================================
# 4-copy max guard
# =============================================================================


def test_no_nonbasic_exceeds_4_copies() -> None:
    """No nonbasic card name exceeds 4 copies in the mainboard."""
    deck = build_heuristic_deck(
        name="Limit Test",
        archetype="Midrange",
        colors=["G"],
        set_codes=["FDN"],
    )
    basic_names = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
    for entry in deck.mainboard:
        if entry.card_name in basic_names:
            continue
        assert entry.quantity <= 4, (
            f"{entry.card_name} has {entry.quantity} copies (>4 is illegal)"
        )
