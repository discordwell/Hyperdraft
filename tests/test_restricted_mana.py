"""Restricted-mana framework tests.

Cards with "Spend this mana only to ..." produce mana units carrying a
spend-restriction predicate. ``ManaPool.can_pay`` / ``pay`` honour those
predicates when they receive ``for_card=...`` from the spell-cast path.
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.mana import (
    ManaCost, ManaPool, ManaType,
    parse_spend_restriction,
    restriction_subtype,
    restriction_card_type,
    restriction_min_mana_value,
    restriction_or,
)


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------


def _make_card(name, *, types, subtypes=None, mana_cost="{1}"):
    return CardDefinition(
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(
            types=set(types),
            subtypes=set(subtypes or []),
            colors=set(),
            mana_cost=mana_cost,
        ),
        text="",
    )


# ----------------------------------------------------------------------
# Pool-level unit tests (no game required)
# ----------------------------------------------------------------------


def test_restricted_unit_pays_matching_spell():
    """A {R} unit restricted to Elemental spells pays an Elemental's {R}."""
    pool = ManaPool()
    pool.add(
        ManaType.RED, 1,
        restriction=restriction_subtype("Elemental"),
        restriction_text="Elemental spells only",
    )
    elemental = _make_card("Burning Sprite", types={CardType.CREATURE}, subtypes={"Elemental"})
    cost = ManaCost.parse("{R}")

    assert pool.can_pay(cost, for_card=elemental), "restricted unit should pay matching spell"
    assert pool.pay(cost, for_card=elemental), "pay should succeed"
    assert pool.total() == 0, "unit should have been consumed"
    print("PASS: restricted unit pays matching spell")


def test_restricted_unit_refuses_non_matching_spell():
    """A {R} unit restricted to Elemental spells does NOT pay a Goblin's {R}."""
    pool = ManaPool()
    pool.add(
        ManaType.RED, 1,
        restriction=restriction_subtype("Elemental"),
        restriction_text="Elemental spells only",
    )
    goblin = _make_card("Goblin Guide", types={CardType.CREATURE}, subtypes={"Goblin"})
    cost = ManaCost.parse("{R}")

    assert not pool.can_pay(cost, for_card=goblin), "restricted unit must not pay non-matching spell"
    assert not pool.pay(cost, for_card=goblin), "pay should fail"
    assert pool.total() == 1, "unit must remain in pool after failed pay"
    print("PASS: restricted unit refuses non-matching spell")


def test_restricted_unit_refuses_when_no_card_supplied():
    """When ``for_card`` is None (e.g. activated-ability cost), restricted mana
    is treated as unspendable."""
    pool = ManaPool()
    pool.add(
        ManaType.GREEN, 1,
        restriction=restriction_subtype("Elemental"),
    )
    cost = ManaCost.parse("{G}")
    assert not pool.can_pay(cost), "restricted mana must not pay when no card given"
    assert not pool.pay(cost), "pay must fail"
    assert pool.total() == 1, "unit must remain"
    print("PASS: restricted unit refuses when no card supplied")


def test_unrestricted_pool_still_pays_anything():
    """An ordinary pool with no restrictions pays anything (sanity)."""
    pool = ManaPool()
    pool.add(ManaType.WHITE, 1)
    pool.add(ManaType.BLUE, 1)
    pool.add(ManaType.RED, 2)
    cost = ManaCost.parse("{W}{U}{1}")
    spell = _make_card("Random Spell", types={CardType.SORCERY}, mana_cost="{W}{U}{1}")

    assert pool.can_pay(cost, for_card=spell), "unrestricted pool pays for_card"
    # Pay without for_card too (no restrictions involved).
    assert pool.can_pay(cost), "unrestricted pool pays without for_card"
    assert pool.pay(cost), "pay should succeed"
    assert pool.total() == 1, "one extra red should remain"
    print("PASS: unrestricted pool still pays anything")


def test_mixed_pool_pays_matching_with_both_units():
    """Mixed pool: 1 restricted-Elemental {R} + 1 unrestricted {R}.

    Casting a 2-cost Elemental spends both units. Casting a 1-cost non-Elemental
    spends only the unrestricted unit (the restricted unit is left in the pool).
    """
    elemental = _make_card("Big Elemental", types={CardType.CREATURE}, subtypes={"Elemental"}, mana_cost="{1}{R}")
    goblin = _make_card("Plain Goblin", types={CardType.CREATURE}, subtypes={"Goblin"}, mana_cost="{R}")

    # Scenario A: pay {1}{R} for an Elemental — both units used.
    pool = ManaPool()
    pool.add(ManaType.RED, 1, restriction=restriction_subtype("Elemental"))
    pool.add(ManaType.RED, 1)
    cost_a = ManaCost.parse("{1}{R}")
    assert pool.can_pay(cost_a, for_card=elemental)
    assert pool.pay(cost_a, for_card=elemental)
    assert pool.total() == 0

    # Scenario B: pay {R} for a non-Elemental — only the unrestricted unit goes.
    pool = ManaPool()
    pool.add(ManaType.RED, 1, restriction=restriction_subtype("Elemental"))
    pool.add(ManaType.RED, 1)
    cost_b = ManaCost.parse("{R}")
    assert pool.can_pay(cost_b, for_card=goblin), "unrestricted unit should cover {R}"
    assert pool.pay(cost_b, for_card=goblin)
    assert pool.total() == 1, "restricted unit should remain"
    remaining = pool.mana[0]
    assert remaining.restriction is not None, "remaining unit should be the restricted one"

    # Scenario C: only restricted mana available, paying for a non-matching
    # spell must fail.
    pool = ManaPool()
    pool.add(ManaType.RED, 1, restriction=restriction_subtype("Elemental"))
    assert not pool.can_pay(cost_b, for_card=goblin)
    assert not pool.pay(cost_b, for_card=goblin)
    assert pool.total() == 1
    print("PASS: mixed pool resolves correctly")


def test_unrestricted_preferred_over_restricted_in_generic_payment():
    """Generic costs prefer unrestricted mana to preserve restricted mana
    for the colored portion of the cost when possible.

    Pool: 1 unrestricted {R}, 1 restricted-to-Elemental {R}.
    Casting a 2-cost goblin (only {R}{R}-payable cost is impossible here, so
    use {1}{R}). Wait — both reds are red. Use a different example.

    Pool: 1 unrestricted {1}-generic-eligible {C}, 1 restricted-to-Elemental {R}.
    Casting {R} for an Elemental — should use the restricted {R} (correctly
    matching) and leave the unrestricted {C} alone.
    """
    pool = ManaPool()
    pool.add(ManaType.COLORLESS, 1)
    pool.add(ManaType.RED, 1, restriction=restriction_subtype("Elemental"))
    elemental = _make_card("Fire Sprite", types={CardType.CREATURE}, subtypes={"Elemental"})
    cost = ManaCost.parse("{R}")
    assert pool.pay(cost, for_card=elemental)
    assert pool.total() == 1
    remaining = pool.mana[0]
    assert remaining.color == ManaType.COLORLESS, "the colorless should remain"
    print("PASS: unrestricted preserved when only restricted satisfies the colored slot")


# ----------------------------------------------------------------------
# Predicate / parser unit tests
# ----------------------------------------------------------------------


def test_restriction_subtype_matches():
    pred = restriction_subtype("Elemental", "Elf")
    e = _make_card("X", types={CardType.CREATURE}, subtypes={"Elemental"})
    f = _make_card("Y", types={CardType.CREATURE}, subtypes={"Elf", "Druid"})
    g = _make_card("Z", types={CardType.CREATURE}, subtypes={"Goblin"})
    assert pred(e)
    assert pred(f)
    assert not pred(g)
    print("PASS: restriction_subtype matches multiple subtypes")


def test_restriction_card_type_matches():
    pred = restriction_card_type(CardType.ARTIFACT)
    a = _make_card("Sword", types={CardType.ARTIFACT})
    c = _make_card("Bear", types={CardType.CREATURE})
    assert pred(a)
    assert not pred(c)
    print("PASS: restriction_card_type matches")


def test_restriction_min_mana_value_matches():
    pred = restriction_min_mana_value(5, include_x=True)
    big = _make_card("Big", types={CardType.SORCERY}, mana_cost="{4}{G}")
    huge = _make_card("Huge", types={CardType.SORCERY}, mana_cost="{6}")
    small = _make_card("Small", types={CardType.SORCERY}, mana_cost="{1}{G}")
    x_spell = _make_card("Fireball", types={CardType.SORCERY}, mana_cost="{X}{R}")
    assert pred(big)
    assert pred(huge)
    assert not pred(small)
    assert pred(x_spell), "X spells should match by include_x"
    print("PASS: restriction_min_mana_value matches and respects include_x")


def test_parse_spend_restriction_elemental():
    info = parse_spend_restriction(
        "{T}: Add two mana in any combination of colors. "
        "Spend this mana only to cast Elemental spells."
    )
    assert info is not None, "parser should pick up Elemental restriction"
    pred, summary = info
    e = _make_card("Sprite", types={CardType.CREATURE}, subtypes={"Elemental"})
    g = _make_card("Goblin", types={CardType.CREATURE}, subtypes={"Goblin"})
    assert pred(e)
    assert not pred(g)
    assert "Elemental" in summary
    print(f"PASS: parser handles Elemental ({summary!r})")


def test_parse_spend_restriction_mana_value():
    info = parse_spend_restriction(
        "{T}: Add {G}{U}. Spend this mana only to cast spells with mana value 5 "
        "or greater or spells with {X} in their mana costs."
    )
    assert info is not None
    pred, _ = info
    big = _make_card("Big", types={CardType.SORCERY}, mana_cost="{4}{U}")
    small = _make_card("Small", types={CardType.SORCERY}, mana_cost="{U}")
    x_spell = _make_card("Stroke", types={CardType.SORCERY}, mana_cost="{X}{X}{U}")
    assert pred(big)
    assert not pred(small)
    assert pred(x_spell)
    print("PASS: parser handles mana value 5+ / X-cost")


def test_parse_spend_restriction_subtype_disjunction():
    info = parse_spend_restriction(
        "{T}: Add two mana of any one color. Spend this mana only to cast "
        "Mount or Vehicle spells."
    )
    assert info is not None
    pred, _ = info
    mount = _make_card("Horse", types={CardType.CREATURE}, subtypes={"Mount"})
    vehicle = _make_card("Truck", types={CardType.ARTIFACT}, subtypes={"Vehicle"})
    other = _make_card("Bear", types={CardType.CREATURE}, subtypes={"Bear"})
    assert pred(mount)
    assert pred(vehicle)
    assert not pred(other)
    print("PASS: parser handles 'Mount or Vehicle' disjunction")


def test_parse_spend_restriction_artifact_type():
    info = parse_spend_restriction(
        "{T}: Add {U}. Spend this mana only to cast an artifact spell."
    )
    assert info is not None
    pred, _ = info
    art = _make_card("Sword", types={CardType.ARTIFACT})
    creat = _make_card("Bear", types={CardType.CREATURE})
    assert pred(art)
    assert not pred(creat)
    print("PASS: parser handles 'an artifact spell'")


def test_parse_spend_restriction_returns_none_for_unrelated_text():
    assert parse_spend_restriction("") is None
    assert parse_spend_restriction(None) is None
    assert parse_spend_restriction("Flying. When this enters, draw a card.") is None
    print("PASS: parser returns None for non-restriction text")


# ----------------------------------------------------------------------
# Integration: produce restricted mana via mana ability dispatch
# ----------------------------------------------------------------------


def _spawn(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def test_priority_dispatch_attaches_restriction_to_pool():
    """Activating "{T}: Add {R}. Spend only to cast Elemental spells" should
    place a restricted unit in the pool that can ONLY pay Elemental costs."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        land_def = CardDefinition(
            name="Elemental Lord Tap-Land", mana_cost="",
            characteristics=Characteristics(
                types={CardType.LAND}, subtypes={"Land"},
                colors=set(), mana_cost="",
            ),
            text="{T}: Add {R}. Spend this mana only to cast Elemental spells.",
        )
        land = _spawn(game, p1, land_def)
        land.state.summoning_sickness = False

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [
            a for a in actions
            if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == land.id
        ]
        assert mana_actions, "expected a mana action"

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=land.id,
            ability_id=mana_actions[0].ability_id,
        )
        events = await game.priority_system._handle_activate_ability(action)
        mana_events = [e for e in events if e.type == EventType.MANA_PRODUCED]
        assert mana_events, "expected MANA_PRODUCED"
        assert "restriction" in mana_events[0].payload, "MANA_PRODUCED should advertise restriction"

        # The pool should now have one restricted RED unit.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 1
        unit = pool.mana[0]
        assert unit.color == ManaType.RED
        assert unit.restriction is not None

        elemental = _make_card("Fire Sprite", types={CardType.CREATURE}, subtypes={"Elemental"})
        goblin = _make_card("Goblin Guide", types={CardType.CREATURE}, subtypes={"Goblin"})
        cost = ManaCost.parse("{R}")
        assert pool.can_pay(cost, for_card=elemental), "restricted mana pays Elemental"
        assert not pool.can_pay(cost, for_card=goblin), "restricted mana refuses Goblin"
        print("PASS: priority dispatch attaches restriction to pool")

    asyncio.get_event_loop().run_until_complete(_run())


def test_giada_restricts_to_angels_end_to_end():
    """Giada, Font of Hope's restricted {W} should pay {W} for an Angel but
    refuse to pay a non-Angel."""
    async def _run():
        from src.cards.foundations import GIADA_FONT_OF_HOPE

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        giada = _spawn(game, p1, GIADA_FONT_OF_HOPE)
        giada.state.summoning_sickness = False
        # Bump timestamp past entered_zone_at so tap is allowed.
        game.state.next_timestamp(); game.state.next_timestamp()

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [
            a for a in actions
            if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == giada.id
        ]
        assert mana_actions, "Giada should expose a mana ability"
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=giada.id,
            ability_id=mana_actions[0].ability_id,
        )
        await game.priority_system._handle_activate_ability(action)

        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 1
        assert pool.mana[0].restriction is not None
        assert pool.mana[0].color == ManaType.WHITE

        angel_def = _make_card("Tiny Angel", types={CardType.CREATURE}, subtypes={"Angel"}, mana_cost="{W}")
        bear_def = _make_card("Tiny Bear", types={CardType.CREATURE}, subtypes={"Bear"}, mana_cost="{W}")

        cost = ManaCost.parse("{W}")
        assert pool.can_pay(cost, for_card=angel_def), "Giada's mana pays Angels"
        assert not pool.can_pay(cost, for_card=bear_def), "Giada's mana refuses Bears"
        # ManaSystem.pay_cost should also honour the restriction.
        assert not game.mana_system.pay_cost(p1.id, cost, for_card=bear_def)
        assert pool.total() == 1, "pool unchanged after refused payment"
        assert game.mana_system.pay_cost(p1.id, cost, for_card=angel_def)
        assert pool.total() == 0
        print("PASS: Giada restricted-{W} pays Angels but refuses Bears")

    asyncio.get_event_loop().run_until_complete(_run())


def test_troyan_restricts_to_mv5_or_x_spells_end_to_end():
    """Troyan, Gutsy Explorer's restricted {G}{U} should only pay spells
    with mana value 5+ or with {X} in their cost."""
    async def _run():
        from src.cards.wilds_of_eldraine import TROYAN_GUTSY_EXPLORER

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        troyan = _spawn(game, p1, TROYAN_GUTSY_EXPLORER)
        troyan.state.summoning_sickness = False
        game.state.next_timestamp(); game.state.next_timestamp()

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [
            a for a in actions
            if a.ability_id and a.ability_id.startswith("mana:")
            and a.source_id == troyan.id
            and "Add {G}{U}" in a.description
        ]
        assert mana_actions, f"Troyan should expose its mana ability; got {[a.description for a in actions]}"
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=troyan.id,
            ability_id=mana_actions[0].ability_id,
        )
        await game.priority_system._handle_activate_ability(action)

        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 2
        assert all(u.restriction is not None for u in pool.mana)
        assert {u.color for u in pool.mana} == {ManaType.GREEN, ManaType.BLUE}

        big = _make_card("Krakenwolf", types={CardType.CREATURE}, subtypes={"Wolf"}, mana_cost="{3}{G}{U}")
        small = _make_card("Tiny Frog", types={CardType.CREATURE}, subtypes={"Frog"}, mana_cost="{G}{U}")
        x_spell = _make_card("Stroke of Genius", types={CardType.SORCERY}, mana_cost="{X}{2}{U}")

        big_cost = ManaCost.parse(big.mana_cost or "")
        small_cost = ManaCost.parse(small.mana_cost or "")
        x_cost = ManaCost.parse(x_spell.mana_cost or "")

        # Big spell (MV 5) should pass on the colored part. Note the {G}{U}
        # portion is what's payable from the pool; we test only that aspect.
        assert pool.can_pay(ManaCost.parse("{G}{U}"), for_card=big), "MV 5 spell pays {G}{U}"
        assert not pool.can_pay(ManaCost.parse("{G}{U}"), for_card=small), "MV 2 spell rejected"
        assert pool.can_pay(ManaCost.parse("{G}{U}"), for_card=x_spell), "X spell pays via include_x"
        print("PASS: Troyan restricted-{G}{U} obeys MV 5+ / X-cost rule")

    asyncio.get_event_loop().run_until_complete(_run())


def test_flamebraider_restricts_to_elementals_end_to_end():
    """Flamebraider produces "any-color" restricted mana that can pay an
    Elemental and refuse a non-Elemental."""
    async def _run():
        from src.cards.lorwyn_eclipsed import FLAMEBRAIDER

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        fb = _spawn(game, p1, FLAMEBRAIDER)
        fb.state.summoning_sickness = False
        game.state.next_timestamp(); game.state.next_timestamp()

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [
            a for a in actions
            if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == fb.id
        ]
        assert mana_actions
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=fb.id,
            ability_id=mana_actions[0].ability_id,
        )
        await game.priority_system._handle_activate_ability(action)
        pool = game.mana_system.get_pool(p1.id)
        # Two units (any-color fallback yields colorless).
        assert pool.total() == 2
        assert all(u.restriction is not None for u in pool.mana)

        elem = _make_card("Fire Sprite", types={CardType.CREATURE}, subtypes={"Elemental"}, mana_cost="{1}{R}")
        goblin = _make_card("Goblin Guide", types={CardType.CREATURE}, subtypes={"Goblin"}, mana_cost="{1}{R}")

        # Pool has 2 colorless. We can pay {2} for an Elemental (generic)
        # but not {2} for a non-Elemental.
        assert pool.can_pay(ManaCost.parse("{2}"), for_card=elem)
        assert not pool.can_pay(ManaCost.parse("{2}"), for_card=goblin)
        print("PASS: Flamebraider restricted any-color pays Elementals only")

    asyncio.get_event_loop().run_until_complete(_run())


def test_priority_dispatch_no_restriction_when_text_lacks_clause():
    """Existing "{T}: Add {R}." (no spend restriction) should still produce
    unrestricted mana — sanity check."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        land_def = CardDefinition(
            name="Mountain", mana_cost="",
            characteristics=Characteristics(
                types={CardType.LAND}, subtypes={"Mountain"},
                colors=set(), mana_cost="",
            ),
            text="{T}: Add {R}.",
        )
        land = _spawn(game, p1, land_def)
        land.state.summoning_sickness = False

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [
            a for a in actions
            if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == land.id
        ]
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=land.id,
            ability_id=mana_actions[0].ability_id,
        )
        await game.priority_system._handle_activate_ability(action)
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 1
        assert pool.mana[0].restriction is None, "plain Mountain mana should be unrestricted"
        print("PASS: plain mana ability remains unrestricted")

    asyncio.get_event_loop().run_until_complete(_run())


# ----------------------------------------------------------------------
# Backwards-compat sanity: existing call without for_card still works
# ----------------------------------------------------------------------


def test_pool_pay_without_for_card_unchanged():
    """``pool.pay(cost)`` with no for_card and no restricted mana is unchanged."""
    pool = ManaPool()
    pool.add(ManaType.WHITE, 2)
    pool.add(ManaType.BLUE, 1)
    cost = ManaCost.parse("{W}{U}")
    assert pool.can_pay(cost)
    assert pool.pay(cost)
    assert pool.total() == 1
    print("PASS: legacy pay-without-for_card still works")


def test_can_cast_falls_through_to_lands_with_restricted_pool():
    """``ManaSystem.can_cast`` should still allow casting via untapped lands
    even when the pool only has restricted mana that doesn't apply."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Untapped Plains in play.
        plains_def = CardDefinition(
            name="Plains", mana_cost="",
            characteristics=Characteristics(
                types={CardType.LAND}, subtypes={"Plains"},
                colors=set(), mana_cost="",
            ),
            text="{T}: Add {W}.",
        )
        plains = _spawn(game, p1, plains_def)
        plains.state.tapped = False

        # Pool has a single restricted-{W} that cannot pay a Bear.
        game.mana_system.produce_mana_restricted(
            p1.id, ManaType.WHITE, 1,
            restriction=restriction_subtype("Angel"),
            restriction_text="Angel spells",
        )

        # A Bear card costs {W} too.
        bear = _make_card("Tundra Bear", types={CardType.CREATURE}, subtypes={"Bear"}, mana_cost="{W}")
        cost = ManaCost.parse("{W}")
        # The pool alone cannot pay (Angel-only mana).
        assert not game.mana_system.get_pool(p1.id).can_pay(cost, for_card=bear)
        # But can_cast should fall through to the untapped Plains.
        assert game.mana_system.can_cast(p1.id, cost, for_card=bear)
        print("PASS: can_cast considers untapped lands when pool is restricted")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_restricted_unit_pays_matching_spell()
    test_restricted_unit_refuses_non_matching_spell()
    test_restricted_unit_refuses_when_no_card_supplied()
    test_unrestricted_pool_still_pays_anything()
    test_mixed_pool_pays_matching_with_both_units()
    test_unrestricted_preferred_over_restricted_in_generic_payment()

    test_restriction_subtype_matches()
    test_restriction_card_type_matches()
    test_restriction_min_mana_value_matches()
    test_parse_spend_restriction_elemental()
    test_parse_spend_restriction_mana_value()
    test_parse_spend_restriction_subtype_disjunction()
    test_parse_spend_restriction_artifact_type()
    test_parse_spend_restriction_returns_none_for_unrelated_text()

    test_priority_dispatch_attaches_restriction_to_pool()
    test_giada_restricts_to_angels_end_to_end()
    test_troyan_restricts_to_mv5_or_x_spells_end_to_end()
    test_flamebraider_restricts_to_elementals_end_to_end()
    test_priority_dispatch_no_restriction_when_text_lacks_clause()
    test_pool_pay_without_for_card_unchanged()
    test_can_cast_falls_through_to_lands_with_restricted_pool()

    print("\nAll restricted-mana tests passed!")
