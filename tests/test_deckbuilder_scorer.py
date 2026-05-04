"""
Unit tests for the W1 heuristic deckbuilder primitives:

* ``score_card`` (scorer.py)
* ``ARCHETYPE_TEMPLATES`` (archetypes.py)
* ``resolve_pool`` (pool.py)

Most tests build synthetic ``CardDefinition`` objects so we can isolate one
score term at a time. Two tests exercise the real registries
(``resolve_pool`` union and collision precedence) to catch integration
issues.

Run with:
    python -m pytest tests/test_deckbuilder_scorer.py -v
"""

from __future__ import annotations

import math

import pytest

from src.decks.heuristics import (
    ARCHETYPE_TEMPLATES,
    ArchetypeTemplate,
    resolve_pool,
    role_of,
    score_card,
)
from src.engine.types import (
    CardDefinition,
    Characteristics,
    CardType,
    Color,
)


# =============================================================================
# Synthetic card builders
# =============================================================================


def _make_creature(
    *,
    name: str = "Test Creature",
    mana_cost: str = "{2}",
    power: int = 2,
    toughness: int = 2,
    colors: set[Color] | None = None,
    keywords: list[str] | None = None,
    text: str = "",
    rarity: str | None = None,
    setup_interceptors=None,
    resolve=None,
) -> CardDefinition:
    if colors is None:
        # Infer from mana_cost colored pips
        colors = set()
        for c, color in [
            ("{W}", Color.WHITE),
            ("{U}", Color.BLUE),
            ("{B}", Color.BLACK),
            ("{R}", Color.RED),
            ("{G}", Color.GREEN),
        ]:
            if c in mana_cost:
                colors.add(color)
    abilities = []
    if keywords:
        abilities = [{"keyword": k.lower()} for k in keywords]
    chars = Characteristics(
        types={CardType.CREATURE},
        colors=colors,
        mana_cost=mana_cost,
        power=power,
        toughness=toughness,
        abilities=abilities,
    )
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=chars,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
        resolve=resolve,
    )


def _make_spell(
    *,
    name: str = "Test Spell",
    mana_cost: str = "{1}",
    types: set[CardType] | None = None,
    colors: set[Color] | None = None,
    text: str = "",
    rarity: str | None = None,
    setup_interceptors=None,
    resolve=None,
) -> CardDefinition:
    if types is None:
        types = {CardType.INSTANT}
    if colors is None:
        colors = set()
        for c, color in [
            ("{W}", Color.WHITE),
            ("{U}", Color.BLUE),
            ("{B}", Color.BLACK),
            ("{R}", Color.RED),
            ("{G}", Color.GREEN),
        ]:
            if c in mana_cost:
                colors.add(color)
    chars = Characteristics(
        types=types,
        colors=colors,
        mana_cost=mana_cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=chars,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
        resolve=resolve,
    )


# =============================================================================
# Tests
# =============================================================================


def test_castability_rejection_off_color_returns_inf():
    """An {U}{U} spell in a mono-red deck must score +inf."""
    counterspell = _make_spell(
        name="Counterspell",
        mana_cost="{U}{U}",
        text="Counter target spell.",
    )
    assert score_card(counterspell, "Control", ["U"]) != math.inf
    assert score_card(counterspell, "Aggro", ["R"]) == math.inf
    # Multi-pip off-color also rejected
    assert score_card(counterspell, "Aggro", ["W", "B"]) == math.inf


def test_castability_hybrid_pip_accepted_if_either_color_present():
    """A {W/U} hybrid is castable in a mono-white or mono-blue deck."""
    hybrid = _make_spell(name="Hybrid", mana_cost="{W/U}")
    assert score_card(hybrid, "Midrange", ["W"]) != math.inf
    assert score_card(hybrid, "Midrange", ["U"]) != math.inf
    assert score_card(hybrid, "Midrange", ["R"]) == math.inf


def test_curve_aggro_prefers_two_drop_over_five_drop():
    """For Aggro (sweet=2), a {1}{R} should score better than a {4}{R}."""
    two_drop = _make_creature(name="Goblin", mana_cost="{1}{R}", power=2, toughness=2)
    five_drop = _make_creature(name="Dragon", mana_cost="{4}{R}", power=4, toughness=4)
    s2 = score_card(two_drop, "Aggro", ["R"])
    s5 = score_card(five_drop, "Aggro", ["R"])
    # Drop both wired-bonus + rarity to isolate curve+body:
    assert s2 < s5, f"Expected 2-drop ({s2}) to score better than 5-drop ({s5}) for Aggro"


def test_two_color_decks_penalize_early_double_pip_cards():
    """Two-color decks should prefer comparable early cards with easier costs."""
    single_pip = _make_creature(name="Easy Bear", mana_cost="{1}{W}", power=2, toughness=2)
    double_pip = _make_creature(name="Hard Bear", mana_cost="{W}{W}", power=2, toughness=2)

    two_color_single = score_card(single_pip, "Aggro", ["W", "U"])
    two_color_double = score_card(double_pip, "Aggro", ["W", "U"])
    mono_single = score_card(single_pip, "Aggro", ["W"])
    mono_double = score_card(double_pip, "Aggro", ["W"])

    assert two_color_single < two_color_double
    assert mono_single == mono_double


def test_curve_control_prefers_four_drop_over_two_drop():
    """For Control (sweet=4), a {3}{U} should score better than {1}{U}."""
    two_drop = _make_creature(name="Twoer", mana_cost="{1}{U}", power=2, toughness=2)
    four_drop = _make_creature(name="Fourer", mana_cost="{3}{U}", power=2, toughness=2)
    s2 = score_card(two_drop, "Control", ["U"])
    s4 = score_card(four_drop, "Control", ["U"])
    assert s4 < s2, f"Expected 4-drop ({s4}) better than 2-drop ({s2}) for Control"


def test_body_efficiency_better_stats_lower_score():
    """A 3/3 for {2} should score lower than a 2/2 for {2} (same CMC)."""
    weak = _make_creature(name="Weak", mana_cost="{2}", power=2, toughness=2)
    strong = _make_creature(name="Strong", mana_cost="{2}", power=3, toughness=3)
    sw = score_card(weak, "Aggro", [])
    ss = score_card(strong, "Aggro", [])
    assert ss < sw, f"Expected strong body ({ss}) better than weak ({sw})"


def test_body_efficiency_efficient_3_3_for_2_beats_2_2_for_3():
    """A 3/3 for {2} (eff=3.0) beats a 2/2 for {3} (eff=1.33)."""
    great = _make_creature(name="Great", mana_cost="{2}", power=3, toughness=3)
    bad = _make_creature(name="Bad", mana_cost="{3}", power=2, toughness=2)
    sg = score_card(great, "Midrange", [])
    sb = score_card(bad, "Midrange", [])
    assert sg < sb, f"3/3 for 2 ({sg}) should beat 2/2 for 3 ({sb})"


def test_keyword_haste_helps_aggro_more_than_control():
    """A haste creature should score better in Aggro than in Control
    (relative to the same body without haste)."""
    haste_text = "Haste"
    haste_creature = _make_creature(
        name="Haster",
        mana_cost="{1}{R}",
        power=2,
        toughness=2,
        text=haste_text,
    )
    vanilla = _make_creature(
        name="Vanilla",
        mana_cost="{1}{R}",
        power=2,
        toughness=2,
        text="",
    )
    aggro_haste_diff = score_card(haste_creature, "Aggro", ["R"]) - score_card(vanilla, "Aggro", ["R"])
    control_haste_diff = score_card(haste_creature, "Control", ["R"]) - score_card(vanilla, "Control", ["R"])

    # Aggro favors haste: haste creature should be MORE preferred (lower score)
    # vs vanilla in aggro than in control.
    assert aggro_haste_diff < 0, "haste should help in Aggro"
    assert aggro_haste_diff < control_haste_diff, (
        f"haste should help Aggro more than Control "
        f"(aggro_diff={aggro_haste_diff}, control_diff={control_haste_diff})"
    )


def test_role_detection_removal_counterspell_card_draw():
    """The role tagger should classify representative card text correctly."""
    removal = _make_spell(
        name="Bolt", mana_cost="{R}",
        text="Lightning Bolt deals 3 damage to any target.",
    )
    counter = _make_spell(
        name="Counterspell", mana_cost="{U}{U}",
        text="Counter target spell.",
    )
    draw = _make_spell(
        name="Divination", mana_cost="{2}{U}",
        types={CardType.SORCERY},
        text="Draw two cards.",
    )
    ramp = _make_spell(
        name="Rampant Growth", mana_cost="{1}{G}",
        types={CardType.SORCERY},
        text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    )
    vanilla = _make_creature(name="Bear", mana_cost="{1}{G}", power=2, toughness=2, text="")

    assert role_of(removal) == "removal"
    assert role_of(counter) == "counterspell"
    assert role_of(draw) == "card_draw"
    assert role_of(ramp) == "ramp"
    assert role_of(vanilla) == "utility"


def test_role_weighting_archetype_dependent():
    """A counterspell scores poorly in Aggro and well in Control.

    We compare the same card in two archetypes — Control should rate it
    lower than Aggro because Control rewards counterspells (-1.0) and Aggro
    punishes them (+1.0). The full score difference is:

        delta_role  = -2.0  (Control favored vs Aggro)
        delta_curve = +2.0  (Control's sweet=4 hurts a 2-cost; Aggro sweet=2 helps)

    To isolate the role term, we pick a 4-cost counterspell so the curve
    cost is identical in both directions: |4-2|=2 (Aggro) vs |4-4|=0
    (Control). Net difference: -2.0 (role) + -2.0 (curve) = -4.0.
    """
    counter = _make_spell(
        name="Big Counter", mana_cost="{2}{U}{U}",
        text="Counter target spell.",
    )
    s_aggro = score_card(counter, "Aggro", ["U"])
    s_control = score_card(counter, "Control", ["U"])
    assert math.isfinite(s_aggro)
    assert math.isfinite(s_control)
    assert s_control < s_aggro, (
        f"counterspell should score better for Control ({s_control}) "
        f"than Aggro ({s_aggro})"
    )
    assert s_aggro - s_control >= 3.0, (
        f"role weight + curve effect should produce a noticeable gap "
        f"(aggro={s_aggro}, control={s_control})"
    )


def test_rarity_tiebreaker_mythic_lower_than_common():
    """Two otherwise-identical cards: the mythic scores lower."""
    common = _make_creature(
        name="C", mana_cost="{2}", power=2, toughness=2, rarity="common"
    )
    mythic = _make_creature(
        name="M", mana_cost="{2}", power=2, toughness=2, rarity="mythic"
    )
    sc = score_card(common, "Aggro", [])
    sm = score_card(mythic, "Aggro", [])
    assert sm < sc, f"mythic ({sm}) should beat common ({sc})"
    # And the gap should be small (rarity is a tiebreaker, not a hammer):
    assert abs(sm - sc) <= 1.5


def test_wired_bonus_setup_interceptors_lowers_score():
    """A creature with setup_interceptors scores lower than a pure-vanilla one."""

    def _dummy_setup(_obj, _state):
        return []

    vanilla = _make_creature(name="V", mana_cost="{2}", power=2, toughness=2)
    wired = _make_creature(
        name="W", mana_cost="{2}", power=2, toughness=2,
        setup_interceptors=_dummy_setup,
    )
    sv = score_card(vanilla, "Midrange", [])
    sw = score_card(wired, "Midrange", [])
    assert sw < sv, f"wired ({sw}) should beat vanilla ({sv})"
    # The gap should be ~0.5 per the documented constant.
    assert abs((sv - sw) - 0.5) < 1e-6


def test_wired_bonus_resolve_lowers_score_more_than_setup():
    """A spell with resolve= scores far lower than a setup-only card."""

    def _dummy_resolve(_event, _state):
        return []

    def _dummy_setup(_obj, _state):
        return []

    setup_only = _make_spell(
        name="SOnly", mana_cost="{2}",
        setup_interceptors=_dummy_setup,
    )
    resolve_only = _make_spell(
        name="ROnly", mana_cost="{2}",
        resolve=_dummy_resolve,
    )
    s_setup = score_card(setup_only, "Midrange", [])
    s_resolve = score_card(resolve_only, "Midrange", [])
    assert s_resolve < s_setup, (
        f"resolve ({s_resolve}) should beat setup-only ({s_setup}) per "
        "custom_set_tournament:148-158"
    )
    # Gap should reflect the documented -5.5 vs -0.5 = ~5.0 difference.
    assert (s_setup - s_resolve) > 4.0


def test_archetype_templates_has_all_six_keys():
    """ARCHETYPE_TEMPLATES exposes Aggro, Midrange, Control, Tempo, Ramp, Combo."""
    expected = {"Aggro", "Midrange", "Control", "Tempo", "Ramp", "Combo"}
    assert set(ARCHETYPE_TEMPLATES.keys()) == expected
    for name, tmpl in ARCHETYPE_TEMPLATES.items():
        assert isinstance(tmpl, ArchetypeTemplate), name
        assert tmpl.name == name
        # Sensible non-zero structure
        assert tmpl.land_count > 0, name
        assert tmpl.mainboard_size == 60
        assert tmpl.sideboard_size == 15
        assert sum(tmpl.curve_targets.values()) > 0, name
        assert sum(tmpl.role_targets.values()) > 0, name
        # Curve total should be land-budget complementary (within tolerance)
        nonland_target = tmpl.mainboard_size - tmpl.land_count
        assert sum(tmpl.curve_targets.values()) <= nonland_target + 1, name


def test_resolve_pool_basic_union_is_larger_than_single_set():
    """resolve_pool(['FDN','OTJ']) > resolve_pool(['FDN'])."""
    fdn = resolve_pool(["FDN"])
    fdn_otj = resolve_pool(["FDN", "OTJ"])
    assert len(fdn) > 0
    assert len(fdn_otj) > len(fdn), (
        f"Combined pool ({len(fdn_otj)}) should be larger than FDN alone ({len(fdn)})"
    )


def test_resolve_pool_collision_precedence_first_wins():
    """If a card name appears in both sets, the earlier-listed set wins."""
    from src.cards.set_registry import SET_TO_CARDS

    fdn_cards = SET_TO_CARDS.get("FDN", {})
    otj_cards = SET_TO_CARDS.get("OTJ", {})
    overlap = set(fdn_cards.keys()) & set(otj_cards.keys())
    if not overlap:
        # No overlap to test against; build a pool and confirm it doesn't crash.
        pool = resolve_pool(["FDN", "OTJ"])
        assert len(pool) == len(fdn_cards) + len(otj_cards)
        return

    pick = next(iter(overlap))
    fdn_first = resolve_pool(["FDN", "OTJ"])
    otj_first = resolve_pool(["OTJ", "FDN"])
    assert fdn_first[pick] is fdn_cards[pick]
    assert otj_first[pick] is otj_cards[pick]


def test_resolve_pool_unknown_set_silently_skipped():
    """Unknown set codes don't crash; they're just ignored."""
    pool = resolve_pool(["FDN", "ZZZNOTREAL"])
    fdn = resolve_pool(["FDN"])
    assert len(pool) == len(fdn)


def test_resolve_pool_empty_input_returns_empty_dict():
    assert resolve_pool([]) == {}


def test_score_is_deterministic():
    """Scoring is pure: same inputs → same float."""
    creature = _make_creature(name="X", mana_cost="{1}{R}", power=2, toughness=2,
                              text="Haste", rarity="rare")
    s1 = score_card(creature, "Aggro", ["R"])
    s2 = score_card(creature, "Aggro", ["R"])
    s3 = score_card(creature, "Aggro", ["R"])
    assert s1 == s2 == s3
