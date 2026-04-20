"""Smoke tests for text_render and ability_bundles.

Verifies:
  - render_* functions produce the expected literal strings (template form
    with ``{this}`` placeholder intact).
  - substitute_card_name handles both presence and absence of placeholders.
  - Each bundle returns (Interceptor | list[Interceptor], non-empty str).
"""

import sys
from pathlib import Path

# Make the repo root importable when pytest is invoked from any cwd.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from src.cards import text_render as tr
from src.cards import ability_bundles as ab
from src.engine import (
    GameObject, Characteristics, CardType, ZoneType, ObjectState, Interceptor, new_id,
)


# -----------------------------------------------------------------------------
# Fixture: a minimal GameObject we can pass to bundle helpers
# -----------------------------------------------------------------------------

def _make_test_obj() -> GameObject:
    chars = Characteristics(
        types={CardType.CREATURE},
        subtypes=set(),
        supertypes=set(),
        colors=set(),
        mana_cost="{1}",
        power=2,
        toughness=2,
    )
    return GameObject(
        id=new_id(),
        name="Test Creature",
        controller="p1",
        owner="p1",
        zone=ZoneType.BATTLEFIELD,
        characteristics=chars,
        state=ObjectState(),
    )


# -----------------------------------------------------------------------------
# render_* literal assertions
# -----------------------------------------------------------------------------

def test_render_keyword():
    assert tr.render_keyword("flying") == "Flying"
    assert tr.render_keyword("trample") == "Trample"


def test_render_keyword_list():
    assert tr.render_keyword_list(["flying"]) == "Flying"
    assert tr.render_keyword_list(["flying", "trample"]) == "Flying, Trample"
    assert (
        tr.render_keyword_list(["flying", "trample", "haste"])
        == "Flying, Trample, Haste"
    )


def test_render_etb_gain_life():
    assert (
        tr.render_etb_gain_life(3)
        == "When {this} enters the battlefield, you gain 3 life."
    )


def test_render_etb_lose_life():
    assert (
        tr.render_etb_lose_life(2)
        == "When {this} enters the battlefield, each opponent loses 2 life."
    )


def test_render_etb_draw():
    assert (
        tr.render_etb_draw(1)
        == "When {this} enters the battlefield, draw a card."
    )
    assert (
        tr.render_etb_draw(2)
        == "When {this} enters the battlefield, draw two cards."
    )


def test_render_etb_deal_damage():
    assert (
        tr.render_etb_deal_damage(3, "each opponent")
        == "When {this} enters the battlefield, {this} deals 3 damage to each opponent."
    )


def test_render_etb_create_token():
    assert (
        tr.render_etb_create_token(1, 1, "Soldier")
        == "When {this} enters the battlefield, create a 1/1 Soldier creature token."
    )
    assert (
        tr.render_etb_create_token(2, 2, "Zombie", count=3)
        == "When {this} enters the battlefield, create three 2/2 Zombie creature tokens."
    )


def test_render_death_drain():
    assert (
        tr.render_death_drain(2)
        == "When {this} dies, each opponent loses 2 life and you gain 2 life."
    )


def test_render_death_draw():
    assert tr.render_death_draw(1) == "When {this} dies, draw a card."


def test_render_attack_deal_damage():
    assert (
        tr.render_attack_deal_damage(1, "each opponent")
        == "Whenever {this} attacks, {this} deals 1 damage to each opponent."
    )


def test_render_attack_add_counters():
    assert (
        tr.render_attack_add_counters("+1/+1", 1)
        == "Whenever {this} attacks, put a +1/+1 counter on {this}."
    )
    assert (
        tr.render_attack_add_counters("charge", 2)
        == "Whenever {this} attacks, put two charge counters on {this}."
    )


def test_render_static_pt_boost():
    assert (
        tr.render_static_pt_boost(1, 1, "other creatures you control")
        == "Other creatures you control get +1/+1."
    )
    # Negative modifier
    assert (
        tr.render_static_pt_boost(-1, -1, "all creatures")
        == "All creatures get -1/-1."
    )


def test_render_static_keyword_grant():
    assert (
        tr.render_static_keyword_grant(["flying"], "other creatures you control")
        == "Other creatures you control have flying."
    )
    assert (
        tr.render_static_keyword_grant(["flying", "trample"], "creatures you control")
        == "Creatures you control have flying and trample."
    )


def test_render_upkeep_gain_life():
    assert (
        tr.render_upkeep_gain_life(1)
        == "At the beginning of your upkeep, you gain 1 life."
    )


def test_render_spell_cast_draw():
    assert tr.render_spell_cast_draw(1) == "Whenever you cast a spell, draw a card."


def test_render_composite_and_conjunction():
    assert tr.render_composite(["", "A.", "B."]) == "A. B."
    assert tr.render_effect_conjunction(["gain 1 life"]) == "gain 1 life"
    assert (
        tr.render_effect_conjunction(["gain 1 life", "draw a card"])
        == "gain 1 life and draw a card"
    )
    assert (
        tr.render_effect_conjunction(["a", "b", "c"])
        == "a, b, and c"
    )


# -----------------------------------------------------------------------------
# substitute_card_name
# -----------------------------------------------------------------------------

def test_substitute_without_placeholder():
    assert (
        tr.substitute_card_name("Deal 1 damage to each opponent.", "Yuji")
        == "Deal 1 damage to each opponent."
    )


def test_substitute_with_placeholder():
    assert (
        tr.substitute_card_name("When {this} attacks, draw a card.", "Yuji")
        == "When Yuji attacks, draw a card."
    )


def test_substitute_multiple_placeholders():
    template = "When {this} enters, {this} deals 1 damage to each opponent."
    assert (
        tr.substitute_card_name(template, "Totoro")
        == "When Totoro enters, Totoro deals 1 damage to each opponent."
    )


# -----------------------------------------------------------------------------
# Bundle helpers — structural smoke tests
# -----------------------------------------------------------------------------

def _assert_single_bundle(result):
    """A bundle returning a single interceptor must yield (Interceptor, str)."""
    assert isinstance(result, tuple) and len(result) == 2
    itc, txt = result
    assert isinstance(itc, Interceptor)
    assert isinstance(txt, str) and txt.strip()


def _assert_list_bundle(result):
    """A bundle returning multiple interceptors must yield (list[Interceptor], str)."""
    assert isinstance(result, tuple) and len(result) == 2
    itcs, txt = result
    assert isinstance(itcs, list)
    assert all(isinstance(i, Interceptor) for i in itcs)
    assert isinstance(txt, str) and txt.strip()


def test_bundle_etb_gain_life():
    obj = _make_test_obj()
    _assert_single_bundle(ab.etb_gain_life(obj, 3))


def test_bundle_etb_lose_life():
    _assert_single_bundle(ab.etb_lose_life(_make_test_obj(), 2))


def test_bundle_etb_draw():
    _assert_single_bundle(ab.etb_draw(_make_test_obj(), 1))


def test_bundle_etb_create_token():
    _assert_single_bundle(
        ab.etb_create_token(_make_test_obj(), 1, 1, "Soldier", count=2)
    )


def test_bundle_etb_deal_damage():
    _assert_single_bundle(ab.etb_deal_damage(_make_test_obj(), 3))
    with pytest.raises(ValueError):
        ab.etb_deal_damage(_make_test_obj(), 1, target="bad")


def test_bundle_death_drain():
    _assert_single_bundle(ab.death_drain(_make_test_obj(), 2))


def test_bundle_death_draw():
    _assert_single_bundle(ab.death_draw(_make_test_obj(), 1))


def test_bundle_attack_deal_damage():
    _assert_single_bundle(ab.attack_deal_damage(_make_test_obj(), 1))


def test_bundle_attack_add_counters():
    _assert_single_bundle(ab.attack_add_counters(_make_test_obj(), "+1/+1", 1))


def test_bundle_static_pt_boost_all():
    _assert_list_bundle(ab.static_pt_boost_all_you_control(_make_test_obj(), 1, 1))


def test_bundle_static_pt_boost_other():
    _assert_list_bundle(ab.static_pt_boost_other_you_control(_make_test_obj(), 1, 1))


def test_bundle_static_pt_boost_by_subtype():
    _assert_list_bundle(
        ab.static_pt_boost_by_subtype(_make_test_obj(), 1, 1, "Elf")
    )


def test_bundle_static_keyword_grant_others():
    _assert_list_bundle(
        ab.static_keyword_grant_others(_make_test_obj(), ["flying"])
    )


def test_bundle_upkeep_gain_life():
    _assert_single_bundle(ab.upkeep_gain_life(_make_test_obj(), 1))


def test_bundle_spell_cast_draw():
    _assert_single_bundle(ab.spell_cast_draw(_make_test_obj()))


# -----------------------------------------------------------------------------
# Gap-filler filter smoke tests
# -----------------------------------------------------------------------------

def test_gap_filters_callable():
    from src.cards.interceptor_helpers import (
        all_creatures_filter,
        opponent_creatures_filter,
        nonland_permanents_filter,
    )
    obj = _make_test_obj()
    assert callable(all_creatures_filter())
    assert callable(opponent_creatures_filter(obj))
    assert callable(nonland_permanents_filter())


def test_gap_interceptors_build():
    from src.cards.interceptor_helpers import (
        type_grant_interceptor, make_cant_block,
    )
    obj = _make_test_obj()
    itc1 = type_grant_interceptor(obj, ["Zombie"])
    itc2 = make_cant_block(obj)
    assert isinstance(itc1, Interceptor)
    assert isinstance(itc2, Interceptor)
