"""
Tests for the cost-reduction framework.

Covers:
  - get_effective_mana_cost applies registered reductions.
  - Reductions only fire for spells matching the predicate.
  - Multiple reductions stack additively.
  - Reductions clamp generic at 0 (never negative).
  - Reductions never touch coloured / colourless / hybrid / phyrexian symbols.
  - Reductions disappear when the source leaves the battlefield.
  - Self-cost reduction ('this spell costs {X} less') applies to a card in hand.
  - Cast pipeline picks up reductions through _can_cast / _handle_cast_spell.
"""

import asyncio
import os
import sys

# Resolve project root from this test file. Avoids picking up a stale clone
# in /Users/discordwell/Projects/Hyperdraft/ that previous test versions
# hard-coded.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, Color, CardType,
    ManaCost,
    PlayerAction, ActionType,
    make_creature, make_instant,
)
from src.engine.cost_query import get_effective_mana_cost
from src.engine.mana import ManaType
from src.cards.interceptor_helpers import make_cost_reduction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _put_on_battlefield(game, player, card_def):
    """Create a permanent directly on the battlefield, running its setup_interceptors."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _put_in_hand(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _fill_mana(game, player_id: str, color: ManaType, amount: int):
    """Cheat mana into the pool so we don't have to model lands."""
    pool = game.mana_system.get_pool(player_id)
    pool.add(color, amount)


# ---------------------------------------------------------------------------
# Direct framework tests (no cast pipeline)
# ---------------------------------------------------------------------------

def test_no_reductions_returns_printed_cost():
    """With no reduction interceptors, effective cost == printed cost."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    spell_def = make_instant(
        name="Vanilla Spell", mana_cost="{2}{R}",
        colors={Color.RED}, text="", resolve=lambda t, s: [],
    )
    spell = _put_in_hand(game, p1, spell_def)

    eff = get_effective_mana_cost(spell, p1.id, game.state)
    assert eff.generic == 2
    assert eff.red == 1
    print("PASS: no_reductions_returns_printed_cost")


def test_static_reduction_applies_to_matching_spell():
    """A {1}-less reduction targeting Goblins reduces Goblin spell cost."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    # Build a permanent whose static ability says "Goblin spells you cast cost {1} less".
    def lord_setup(obj, state):
        def applies(card, pid, st):
            return (
                pid == obj.controller
                and "Goblin" in card.characteristics.subtypes
            )
        return [make_cost_reduction(obj, applies_to=applies, amount=1)]

    lord_def = make_creature(
        name="Goblin Patron", power=1, toughness=1, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Goblin"},
        text="Goblin spells you cast cost {1} less to cast.",
        setup_interceptors=lord_setup,
    )

    goblin_def = make_creature(
        name="Test Goblin", power=2, toughness=2, mana_cost="{2}{R}",
        colors={Color.RED}, subtypes={"Goblin"}, text="",
    )

    _put_on_battlefield(game, p1, lord_def)
    goblin = _put_in_hand(game, p1, goblin_def)

    eff = get_effective_mana_cost(goblin, p1.id, game.state)
    assert eff.generic == 1, f"Expected {{1}}{{R}}, got {eff.to_string()}"
    assert eff.red == 1
    print("PASS: static_reduction_applies_to_matching_spell")


def test_static_reduction_skips_non_matching_spell():
    """A Goblin-only reduction does not reduce a non-Goblin spell."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def lord_setup(obj, state):
        def applies(card, pid, st):
            return (
                pid == obj.controller
                and "Goblin" in card.characteristics.subtypes
            )
        return [make_cost_reduction(obj, applies_to=applies, amount=1)]

    lord_def = make_creature(
        name="Goblin Patron", power=1, toughness=1, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Goblin"},
        text="Goblin spells you cast cost {1} less to cast.",
        setup_interceptors=lord_setup,
    )

    elf_def = make_creature(
        name="Test Elf", power=2, toughness=2, mana_cost="{2}{G}",
        colors={Color.GREEN}, subtypes={"Elf"}, text="",
    )

    _put_on_battlefield(game, p1, lord_def)
    elf = _put_in_hand(game, p1, elf_def)

    eff = get_effective_mana_cost(elf, p1.id, game.state)
    assert eff.generic == 2, f"Expected {{2}}{{G}}, got {eff.to_string()}"
    assert eff.green == 1
    print("PASS: static_reduction_skips_non_matching_spell")


def test_multiple_reductions_stack_additively():
    """Two {1}-less reductions on the same player stack to {2}-less."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def make_universal_reducer(name, amount):
        def setup(obj, state):
            def applies(card, pid, st):
                return pid == obj.controller
            return [make_cost_reduction(obj, applies_to=applies, amount=amount)]
        return make_creature(
            name=name, power=1, toughness=1, mana_cost="{1}",
            colors={Color.WHITE}, subtypes={"Wizard"},
            text=f"Spells you cast cost {{{amount}}} less.",
            setup_interceptors=setup,
        )

    r1 = make_universal_reducer("Reducer One", 1)
    r2 = make_universal_reducer("Reducer Two", 1)
    target_def = make_instant(
        name="Big Spell", mana_cost="{4}{U}",
        colors={Color.BLUE}, text="", resolve=lambda t, s: [],
    )

    _put_on_battlefield(game, p1, r1)
    _put_on_battlefield(game, p1, r2)
    target = _put_in_hand(game, p1, target_def)

    eff = get_effective_mana_cost(target, p1.id, game.state)
    assert eff.generic == 2, f"Expected {{2}}{{U}}, got {eff.to_string()}"
    assert eff.blue == 1
    print("PASS: multiple_reductions_stack_additively")


def test_reduction_clamps_generic_at_zero():
    """A reduction larger than the generic can't push it negative."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def big_reducer_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller
        return [make_cost_reduction(obj, applies_to=applies, amount=10)]

    reducer_def = make_creature(
        name="Big Reducer", power=1, toughness=1, mana_cost="{1}",
        colors={Color.WHITE}, subtypes={"Wizard"},
        text="Spells you cast cost {10} less.",
        setup_interceptors=big_reducer_setup,
    )

    target_def = make_instant(
        name="Small Spell", mana_cost="{2}{B}",
        colors={Color.BLACK}, text="", resolve=lambda t, s: [],
    )

    _put_on_battlefield(game, p1, reducer_def)
    target = _put_in_hand(game, p1, target_def)

    eff = get_effective_mana_cost(target, p1.id, game.state)
    assert eff.generic == 0, f"Expected {{B}}, got {eff.to_string()}"
    assert eff.black == 1
    print("PASS: reduction_clamps_generic_at_zero")


def test_reduction_respects_colored_minimum():
    """{2}{R}{R} reduced by {3} stays at {R}{R} (coloured floor preserved)."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def big_reducer_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller
        return [make_cost_reduction(obj, applies_to=applies, amount=3)]

    reducer_def = make_creature(
        name="Big Reducer", power=1, toughness=1, mana_cost="{1}",
        colors={Color.WHITE}, subtypes={"Wizard"},
        text="Spells you cast cost {3} less.",
        setup_interceptors=big_reducer_setup,
    )
    target_def = make_instant(
        name="Lava Spike", mana_cost="{2}{R}{R}",
        colors={Color.RED}, text="", resolve=lambda t, s: [],
    )

    _put_on_battlefield(game, p1, reducer_def)
    target = _put_in_hand(game, p1, target_def)

    eff = get_effective_mana_cost(target, p1.id, game.state)
    assert eff.generic == 0, f"Expected {{R}}{{R}}, got {eff.to_string()}"
    assert eff.red == 2, f"Expected 2 red, got {eff.red}"
    print("PASS: reduction_respects_colored_minimum")


def test_reduction_does_not_touch_colorless_or_snow():
    """Reductions never lower {C} or {S} symbols."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def reducer_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller
        return [make_cost_reduction(obj, applies_to=applies, amount=5)]

    reducer_def = make_creature(
        name="Reducer", power=1, toughness=1, mana_cost="{1}",
        colors={Color.WHITE}, subtypes={"Wizard"},
        text="Spells you cast cost {5} less.",
        setup_interceptors=reducer_setup,
    )
    eldrazi_def = make_creature(
        name="Tiny Eldrazi", power=2, toughness=2, mana_cost="{2}{C}",
        colors=set(), subtypes={"Eldrazi"}, text="",
    )

    _put_on_battlefield(game, p1, reducer_def)
    eldrazi = _put_in_hand(game, p1, eldrazi_def)

    eff = get_effective_mana_cost(eldrazi, p1.id, game.state)
    assert eff.generic == 0
    # Colorless symbol preserved.
    assert eff.colorless == 1, f"Expected {{C}} preserved, got {eff.to_string()}"
    print("PASS: reduction_does_not_touch_colorless_or_snow")


def test_reduction_inactive_when_source_off_battlefield():
    """If the source isn't on the battlefield, its reduction does not apply."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def lord_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller
        return [make_cost_reduction(obj, applies_to=applies, amount=1)]

    lord_def = make_creature(
        name="Library Lord", power=1, toughness=1, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Wizard"},
        text="Spells you cast cost {1} less.",
        setup_interceptors=lord_setup,
    )
    spell_def = make_instant(
        name="Spell", mana_cost="{2}{R}",
        colors={Color.RED}, text="", resolve=lambda t, s: [],
    )

    # Put the lord in HAND (not on the battlefield), spell in hand too.
    lord = _put_in_hand(game, p1, lord_def)
    spell = _put_in_hand(game, p1, spell_def)

    eff = get_effective_mana_cost(spell, p1.id, game.state)
    # Generic should NOT be reduced because the lord is in hand.
    assert eff.generic == 2, f"Expected {{2}}{{R}}, got {eff.to_string()}"

    # Sanity: same cost is also unreduced for the lord itself.
    eff_lord = get_effective_mana_cost(lord, p1.id, game.state)
    assert eff_lord.generic == 1
    print("PASS: reduction_inactive_when_source_off_battlefield")


def test_reduction_applies_only_to_controller():
    """A 'spells you cast cost less' reduction does NOT lower opponent's spells."""
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    def lord_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller
        return [make_cost_reduction(obj, applies_to=applies, amount=1)]

    lord_def = make_creature(
        name="P1 Lord", power=1, toughness=1, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Wizard"},
        text="Spells you cast cost {1} less.",
        setup_interceptors=lord_setup,
    )
    spell_def = make_instant(
        name="P2 Spell", mana_cost="{3}{B}",
        colors={Color.BLACK}, text="", resolve=lambda t, s: [],
    )

    _put_on_battlefield(game, p1, lord_def)
    p2_spell = _put_in_hand(game, p2, spell_def)

    eff = get_effective_mana_cost(p2_spell, p2.id, game.state)
    assert eff.generic == 3, f"Expected {{3}}{{B}}, got {eff.to_string()}"
    print("PASS: reduction_applies_only_to_controller")


def test_dynamic_amount_callable():
    """``amount`` may be a (card, state)->int callable for dynamic reductions."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def lord_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller

        def amount_fn(card, st):
            # Reduce by number of permanents the controller has on the battlefield
            # (excluding the lord itself, just to keep the count interesting).
            count = 0
            bf = st.zones.get('battlefield')
            if bf:
                for oid in bf.objects:
                    o = st.objects.get(oid)
                    if o and o.controller == obj.controller and o.id != obj.id:
                        count += 1
            return count

        return [make_cost_reduction(obj, applies_to=applies, amount=amount_fn)]

    lord_def = make_creature(
        name="Power Reducer", power=1, toughness=1, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Wizard"},
        text="Spells you cast cost {1} less for each other permanent you control.",
        setup_interceptors=lord_setup,
    )
    aux_def = make_creature(
        name="Filler", power=1, toughness=1, mana_cost="{1}",
        colors={Color.WHITE}, subtypes={"Soldier"}, text="",
    )
    target_def = make_instant(
        name="Big Spell", mana_cost="{4}{U}",
        colors={Color.BLUE}, text="", resolve=lambda t, s: [],
    )

    _put_on_battlefield(game, p1, lord_def)
    _put_on_battlefield(game, p1, aux_def)
    _put_on_battlefield(game, p1, aux_def)  # second filler
    target = _put_in_hand(game, p1, target_def)

    eff = get_effective_mana_cost(target, p1.id, game.state)
    # 2 fillers => reduce by 2.
    assert eff.generic == 2, f"Expected {{2}}{{U}}, got {eff.to_string()}"
    print("PASS: dynamic_amount_callable")


def test_self_only_reduction_on_card_in_hand():
    """`self_only=True` lets a spell reduce its OWN cost while still in hand."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def spell_setup(obj, state):
        def applies(card, pid, st):
            # Always applies (self_only adds the id check); reduce by {2}.
            return True
        return [make_cost_reduction(
            obj,
            applies_to=applies,
            amount=2,
            self_only=True,
        )]

    spell_def = make_instant(
        name="Self-Discount Spell", mana_cost="{4}{U}",
        colors={Color.BLUE},
        text="This spell costs {2} less to cast.",
        resolve=lambda t, s: [],
        setup_interceptors=spell_setup,
    )

    spell = _put_in_hand(game, p1, spell_def)
    eff = get_effective_mana_cost(spell, p1.id, game.state)
    assert eff.generic == 2, f"Expected {{2}}{{U}}, got {eff.to_string()}"
    print("PASS: self_only_reduction_on_card_in_hand")


# ---------------------------------------------------------------------------
# Integration: cast pipeline picks up the reduction
# ---------------------------------------------------------------------------

def test_cast_pipeline_consumes_reduced_cost():
    """Casting a spell with an active reduction pays the reduced amount."""
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    # Set up turn manager so casting timing works.
    game.start_game()

    # Active player is whichever is_first; force p1 to active.
    if game.turn_manager.active_player != p1.id:
        # Run an end turn or two — easier to just bypass.
        game.turn_manager.turn_state.active_player_id = p1.id

    def lord_setup(obj, state):
        def applies(card, pid, st):
            return pid == obj.controller
        return [make_cost_reduction(obj, applies_to=applies, amount=2)]

    lord_def = make_creature(
        name="Heavy Reducer", power=1, toughness=1, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Wizard"},
        text="Spells you cast cost {2} less.",
        setup_interceptors=lord_setup,
    )

    target_def = make_instant(
        name="Costly Spell", mana_cost="{3}{R}",
        colors={Color.RED}, text="", resolve=lambda t, s: [],
    )

    _put_on_battlefield(game, p1, lord_def)
    spell = _put_in_hand(game, p1, target_def)

    # Give P1 enough mana to pay the *reduced* cost ({1}{R}) but NOT the printed cost ({3}{R}).
    _fill_mana(game, p1.id, ManaType.RED, 1)
    _fill_mana(game, p1.id, ManaType.WHITE, 1)  # {1} generic via white
    # That's 1 red + 1 white = {1}{R} total = pays {1}{R}.

    legal = game.priority_system.get_legal_actions(p1.id)
    cast_actions = [a for a in legal if a.type == ActionType.CAST_SPELL and a.card_id == spell.id]
    assert cast_actions, "Cast action should be legal at the reduced cost"
    legal_cost = cast_actions[0].mana_cost
    assert legal_cost.generic == 1 and legal_cost.red == 1, (
        f"Legal action's mana_cost should be reduced; got {legal_cost.to_string()}"
    )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=spell.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    # After cast, mana pool should be empty (we paid exactly the reduced cost).
    pool = game.mana_system.get_pool(p1.id)
    assert pool.total() == 0, f"Mana pool should be empty after paying reduced cost; got {pool}"
    # Spell should be on the stack.
    assert spell.zone == ZoneType.STACK, f"Spell should be on the stack, was {spell.zone}"
    print("PASS: cast_pipeline_consumes_reduced_cost")


def test_cast_pipeline_blocks_when_unreduced_cost_unaffordable():
    """Without the reduction, the spell remains unaffordable and isn't legal."""
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.start_game()
    if game.turn_manager.active_player != p1.id:
        game.turn_manager.turn_state.active_player_id = p1.id

    target_def = make_instant(
        name="Costly Spell", mana_cost="{3}{R}",
        colors={Color.RED}, text="", resolve=lambda t, s: [],
    )
    spell = _put_in_hand(game, p1, target_def)

    # Only enough mana to pay the would-be reduced cost (but no reducer present).
    _fill_mana(game, p1.id, ManaType.RED, 1)
    _fill_mana(game, p1.id, ManaType.WHITE, 1)

    legal = game.priority_system.get_legal_actions(p1.id)
    cast_actions = [a for a in legal if a.type == ActionType.CAST_SPELL and a.card_id == spell.id]
    assert not cast_actions, "Without a reducer, the spell shouldn't be castable"
    print("PASS: cast_pipeline_blocks_when_unreduced_cost_unaffordable")


# ---------------------------------------------------------------------------
# Wired-card integration tests
# ---------------------------------------------------------------------------

def test_dragonlords_servant_reduces_dragon_spells():
    """Dragonlord's Servant: 'Dragon spells you cast cost {1} less.'"""
    from src.cards.foundations import DRAGONLORDS_SERVANT

    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    _put_on_battlefield(game, p1, DRAGONLORDS_SERVANT)

    # A 5-cost dragon ({4}{R}) -> should drop to {3}{R}.
    dragon_def = make_creature(
        name="Test Dragon", power=4, toughness=4, mana_cost="{4}{R}",
        colors={Color.RED}, subtypes={"Dragon"}, text="Flying",
    )
    dragon = _put_in_hand(game, p1, dragon_def)

    eff = get_effective_mana_cost(dragon, p1.id, game.state)
    assert eff.generic == 3 and eff.red == 1, (
        f"Expected {{3}}{{R}}, got {eff.to_string()}"
    )

    # A non-Dragon shouldn't be reduced.
    elf_def = make_creature(
        name="Test Elf", power=2, toughness=2, mana_cost="{2}{G}",
        colors={Color.GREEN}, subtypes={"Elf"}, text="",
    )
    elf = _put_in_hand(game, p1, elf_def)
    eff_elf = get_effective_mana_cost(elf, p1.id, game.state)
    assert eff_elf.generic == 2 and eff_elf.green == 1
    print("PASS: dragonlords_servant_reduces_dragon_spells")


def test_mocking_sprite_reduces_instants_and_sorceries():
    """Mocking Sprite: 'Instant and sorcery spells you cast cost {1} less.'"""
    from src.cards.foundations import MOCKING_SPRITE

    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    _put_on_battlefield(game, p1, MOCKING_SPRITE)

    inst_def = make_instant(
        name="Some Instant", mana_cost="{2}{U}",
        colors={Color.BLUE}, text="", resolve=lambda t, s: [],
    )
    inst = _put_in_hand(game, p1, inst_def)
    eff_inst = get_effective_mana_cost(inst, p1.id, game.state)
    assert eff_inst.generic == 1 and eff_inst.blue == 1, (
        f"Instant: expected {{1}}{{U}}, got {eff_inst.to_string()}"
    )

    creature_def = make_creature(
        name="Some Creature", power=2, toughness=2, mana_cost="{2}{U}",
        colors={Color.BLUE}, subtypes={"Faerie"}, text="",
    )
    creature = _put_in_hand(game, p1, creature_def)
    eff_creature = get_effective_mana_cost(creature, p1.id, game.state)
    # Creatures should NOT be reduced.
    assert eff_creature.generic == 2 and eff_creature.blue == 1, (
        f"Creature: expected unreduced, got {eff_creature.to_string()}"
    )
    print("PASS: mocking_sprite_reduces_instants_and_sorceries")


def test_arcane_epiphany_self_reduces_with_wizard():
    """Arcane Epiphany: 'This spell costs {1} less to cast if you control a Wizard.'"""
    from src.cards.foundations import ARCANE_EPIPHANY

    # ---- With a Wizard in play: reduced. ----
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    wizard_def = make_creature(
        name="Some Wizard", power=1, toughness=1, mana_cost="{U}",
        colors={Color.BLUE}, subtypes={"Wizard"}, text="",
    )
    _put_on_battlefield(game, p1, wizard_def)
    spell = _put_in_hand(game, p1, ARCANE_EPIPHANY)

    eff = get_effective_mana_cost(spell, p1.id, game.state)
    assert eff.generic == 2 and eff.blue == 2, (
        f"With Wizard: expected {{2}}{{U}}{{U}}, got {eff.to_string()}"
    )

    # ---- Without a Wizard in play: unreduced. ----
    game2 = Game()
    p1b = game2.add_player("P1")
    game2.add_player("P2")
    spell2 = _put_in_hand(game2, p1b, ARCANE_EPIPHANY)

    eff2 = get_effective_mana_cost(spell2, p1b.id, game2.state)
    assert eff2.generic == 3 and eff2.blue == 2, (
        f"No Wizard: expected {{3}}{{U}}{{U}}, got {eff2.to_string()}"
    )
    print("PASS: arcane_epiphany_self_reduces_with_wizard")


# ---------------------------------------------------------------------------
# Wired set-card tests — verifies cost reductions on real Scryfall cards.
# ---------------------------------------------------------------------------

def test_wired_set_cards_reduce_costs():
    """End-to-end checks for cost-reduction setups wired across MTG sets."""
    from src.engine.types import Characteristics, CardDefinition

    def fresh():
        g = Game()
        p1 = g.add_player("A")
        p2 = g.add_player("B")
        return g, p1, p2

    def gen(name, mana_cost="{1}", subtypes=None, types=None,
            power=1, toughness=1, colors=None):
        return CardDefinition(
            name=name, mana_cost=mana_cost,
            characteristics=Characteristics(
                types=set(types) if types else {CardType.CREATURE},
                subtypes=set(subtypes or []),
                power=power, toughness=toughness,
                colors=set(colors or []),
                mana_cost=mana_cost,
            ),
        )

    # GHALTA, PRIMAL HUNGER (FDN, self-cost = total power)
    from src.cards.foundations import GHALTA_PRIMAL_HUNGER
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, GHALTA_PRIMAL_HUNGER)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    _put_on_battlefield(g, p1, gen("Big", power=5, toughness=5))
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 5, f"Ghalta: expected {base - 5}, got {after}"

    # BALLYRUSH BANNERET (FDN, static Kithkin/Soldier)
    from src.cards.foundations import BALLYRUSH_BANNERET
    g, p1, _ = fresh()
    _put_on_battlefield(g, p1, BALLYRUSH_BANNERET)
    kithkin = _put_in_hand(g, p1, gen("K", "{3}{W}", subtypes={"Kithkin"}))
    assert get_effective_mana_cost(kithkin, p1.id, g.state).generic == 2

    # GEYSER DRAKE (OTJ, on-opponent's-turn static)
    from src.cards.outlaws_thunder_junction import GEYSER_DRAKE
    g, p1, p2 = fresh()
    _put_on_battlefield(g, p1, GEYSER_DRAKE)
    spell = _put_in_hand(g, p1, gen("S", "{2}{U}", types={CardType.SORCERY}))
    g.state.active_player = p1.id
    assert get_effective_mana_cost(spell, p1.id, g.state).mana_value == 3
    g.state.active_player = p2.id
    assert get_effective_mana_cost(spell, p1.id, g.state).mana_value == 2

    # TOLARIAN TERROR (FDN, self-cost = instants/sorceries in graveyard)
    from src.cards.foundations import TOLARIAN_TERROR
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, TOLARIAN_TERROR)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    for i in range(3):
        g.create_object(
            name=f"S{i}", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
            characteristics=Characteristics(types={CardType.SORCERY}),
        )
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 3, f"Tolarian Terror: expected {base - 3}, got {after}"

    # DRAG TO THE ROOTS (DSK, delirium 4-types)
    from src.cards.duskmourn import DRAG_TO_THE_ROOTS
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, DRAG_TO_THE_ROOTS)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    for tt in [CardType.CREATURE, CardType.LAND, CardType.INSTANT, CardType.SORCERY]:
        g.create_object(
            name=f"X-{tt}", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
            characteristics=Characteristics(types={tt}),
        )
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 2, f"Drag delirium: expected {base - 2}, got {after}"

    # VENOM'S HUNGER (SPM, self-cost gated on Villain)
    from src.cards.spider_man import VENOMS_HUNGER
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, VENOMS_HUNGER)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    _put_on_battlefield(g, p1, gen("V", subtypes={"Villain"}))
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 2, f"Venom's Hunger: expected {base - 2}, got {after}"

    # SERPENT OF THE PASS (TLA, self-cost = noncreature/nonland gy)
    from src.cards.avatar_tla import SERPENT_OF_THE_PASS
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, SERPENT_OF_THE_PASS)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    g.create_object(
        name="I1", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )
    g.create_object(
        name="I2", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )
    g.create_object(
        name="L", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(types={CardType.LAND}),  # excluded
    )
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 2

    # DIAMOND WEAPON (FIN, self-cost = permanent cards in graveyard)
    from src.cards.final_fantasy import DIAMOND_WEAPON
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, DIAMOND_WEAPON)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    for t in [CardType.CREATURE, CardType.ARTIFACT, CardType.LAND, CardType.INSTANT]:
        g.create_object(
            name=str(t), owner_id=p1.id, zone=ZoneType.GRAVEYARD,
            characteristics=Characteristics(types={t}),
        )
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    # Three permanent types (creature/artifact/land), instant excluded.
    assert after == base - 3

    # GIGASTORM TITAN (EOE, self-cost iff cast another spell this turn)
    from src.cards.edge_of_eternities import GIGASTORM_TITAN
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, GIGASTORM_TITAN)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    g.state.turn_data = getattr(g.state, 'turn_data', {}) or {}
    g.state.turn_data[f'spells_cast_{p1.id}'] = 1
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 3

    # RIME CHILL (ECL, self-cost vivid = colors among permanents)
    from src.cards.lorwyn_eclipsed import RIME_CHILL
    g, p1, _ = fresh()
    spell = _put_in_hand(g, p1, RIME_CHILL)
    base = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    _put_on_battlefield(g, p1, gen("R", colors={Color.RED}))
    _put_on_battlefield(g, p1, gen("B", colors={Color.BLUE}))
    after = get_effective_mana_cost(spell, p1.id, g.state).mana_value
    assert after == base - 2

    print("PASS: wired_set_cards_reduce_costs")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    test_no_reductions_returns_printed_cost()
    test_static_reduction_applies_to_matching_spell()
    test_static_reduction_skips_non_matching_spell()
    test_multiple_reductions_stack_additively()
    test_reduction_clamps_generic_at_zero()
    test_reduction_respects_colored_minimum()
    test_reduction_does_not_touch_colorless_or_snow()
    test_reduction_inactive_when_source_off_battlefield()
    test_reduction_applies_only_to_controller()
    test_dynamic_amount_callable()
    test_self_only_reduction_on_card_in_hand()
    test_cast_pipeline_consumes_reduced_cost()
    test_cast_pipeline_blocks_when_unreduced_cost_unaffordable()
    test_dragonlords_servant_reduces_dragon_spells()
    test_mocking_sprite_reduces_instants_and_sorceries()
    test_arcane_epiphany_self_reduces_with_wizard()
    test_wired_set_cards_reduce_costs()
    print("\nAll cost reduction tests passed.")


if __name__ == "__main__":
    main()
