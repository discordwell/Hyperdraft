"""
Tests for Hyperdraft Core Engine Systems

Tests the new Arena-style systems:
- Mana System
- Targeting System
- Stack Manager
- Turn Manager
- Priority System
- Combat Manager
"""

import pytest
import asyncio

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from src.engine import (
    # Core
    Game, GameState, GameObject, Player, Zone,
    Event, EventType, EventStatus,
    Characteristics, CardType, Color, ZoneType,
    new_id,

    # Mana
    ManaSystem, ManaPool, ManaCost, ManaType,
    parse_cost, color_identity,

    # Stack
    StackManager, StackItem, StackItemType, SpellBuilder,
    create_damage_spell,

    # Turn
    TurnManager, TurnState, Phase, Step,

    # Priority
    PrioritySystem, PlayerAction, ActionType, LegalAction,

    # Combat
    CombatManager, CombatState, AttackDeclaration, BlockDeclaration,

    # Targeting
    TargetingSystem, TargetFilter, TargetRequirement, Target,
    creature_filter, target_creature, target_any,

    # Helpers
    make_creature, make_instant,
)


# =============================================================================
# Mana System Tests
# =============================================================================

class TestManaCostParsing:
    """Test mana cost parsing."""

    def test_parse_simple_colored(self):
        cost = ManaCost.parse("{W}")
        assert cost.white == 1
        assert cost.blue == 0
        assert cost.mana_value == 1

    def test_parse_multiple_colors(self):
        cost = ManaCost.parse("{W}{U}{B}")
        assert cost.white == 1
        assert cost.blue == 1
        assert cost.black == 1
        assert cost.mana_value == 3

    def test_parse_generic_and_colored(self):
        cost = ManaCost.parse("{2}{R}{R}")
        assert cost.generic == 2
        assert cost.red == 2
        assert cost.mana_value == 4

    def test_parse_x_cost(self):
        cost = ManaCost.parse("{X}{R}{R}")
        assert cost.x_count == 1
        assert cost.red == 2
        assert cost.mana_value == 2  # X is 0 for mana value

    def test_parse_colorless(self):
        cost = ManaCost.parse("{C}{C}")
        assert cost.colorless == 2
        assert cost.mana_value == 2

    def test_parse_hybrid(self):
        cost = ManaCost.parse("{W/U}{W/U}")
        assert len(cost.hybrid) == 2
        assert cost.mana_value == 2

    def test_parse_phyrexian(self):
        cost = ManaCost.parse("{G/P}{G/P}")
        assert len(cost.phyrexian) == 2
        assert cost.mana_value == 2

    def test_parse_empty(self):
        cost = ManaCost.parse("")
        assert cost.is_free()
        assert cost.mana_value == 0

    def test_color_identity(self):
        cost = ManaCost.parse("{1}{W}{U}")
        colors = cost.colors
        assert Color.WHITE in colors
        assert Color.BLUE in colors
        assert Color.RED not in colors


class TestManaPool:
    """Test mana pool operations."""

    def test_add_and_count_mana(self):
        pool = ManaPool()
        pool.add(ManaType.WHITE, 2)
        pool.add(ManaType.BLUE, 1)

        assert pool.get_count(ManaType.WHITE) == 2
        assert pool.get_count(ManaType.BLUE) == 1
        assert pool.total() == 3

    def test_can_pay_simple_cost(self):
        pool = ManaPool()
        pool.add(ManaType.RED, 3)

        cost = ManaCost.parse("{R}{R}")
        assert pool.can_pay(cost) == True

        cost2 = ManaCost.parse("{R}{R}{R}{R}")
        assert pool.can_pay(cost2) == False

    def test_can_pay_generic(self):
        pool = ManaPool()
        pool.add(ManaType.WHITE, 2)
        pool.add(ManaType.BLUE, 1)

        cost = ManaCost.parse("{2}{W}")
        assert pool.can_pay(cost) == True

    def test_pay_removes_mana(self):
        pool = ManaPool()
        pool.add(ManaType.RED, 3)

        cost = ManaCost.parse("{R}{R}")
        assert pool.pay(cost) == True
        assert pool.total() == 1

    def test_empty_pool(self):
        pool = ManaPool()
        pool.add(ManaType.GREEN, 5)
        pool.empty()
        assert pool.total() == 0


# =============================================================================
# Targeting System Tests
# =============================================================================

class TestTargetFilter:
    """Test target filtering."""

    def test_creature_filter(self):
        state = GameState()
        creature = GameObject(
            id="c1",
            name="Test Creature",
            owner="p1",
            controller="p1",
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE})
        )
        state.objects["c1"] = creature

        filt = creature_filter()
        assert filt.matches(creature, state, None) == True

    def test_controller_filter(self):
        state = GameState()
        creature = GameObject(
            id="c1",
            name="Test Creature",
            owner="p1",
            controller="p1",
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE})
        )
        source = GameObject(
            id="s1",
            name="Source",
            owner="p1",
            controller="p1",
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.INSTANT})
        )
        state.objects["c1"] = creature
        state.objects["s1"] = source

        # Filter for "you control"
        filt = creature_filter(controller='you')
        assert filt.matches(creature, state, source) == True

        # Change controller
        creature.controller = "p2"
        assert filt.matches(creature, state, source) == False


class TestTargetRequirement:
    """Test target requirements."""

    def test_exactly_one_target(self):
        req = target_creature()
        assert req.min_targets() == 1
        assert req.max_targets() == 1

    def test_up_to_targets(self):
        req = TargetRequirement(
            filter=creature_filter(),
            count=3,
            count_type='up_to'
        )
        assert req.min_targets() == 1
        assert req.max_targets() == 3


# =============================================================================
# Stack Manager Tests
# =============================================================================

class TestStackManager:
    """Test stack operations."""

    def test_push_and_pop(self):
        state = GameState()
        stack = StackManager(state)

        item = StackItem(
            id="item1",
            type=StackItemType.SPELL,
            source_id="card1",
            controller_id="p1"
        )

        stack.push(item)
        assert stack.size() == 1
        assert stack.top().id == "item1"

        popped = stack.pop()
        assert popped.id == "item1"
        assert stack.is_empty()

    def test_lifo_order(self):
        state = GameState()
        stack = StackManager(state)

        stack.push(StackItem(id="a", type=StackItemType.SPELL, source_id="", controller_id=""))
        stack.push(StackItem(id="b", type=StackItemType.SPELL, source_id="", controller_id=""))
        stack.push(StackItem(id="c", type=StackItemType.SPELL, source_id="", controller_id=""))

        assert stack.pop().id == "c"
        assert stack.pop().id == "b"
        assert stack.pop().id == "a"

    def test_counter_respects_uncounterable_flag(self):
        """A stack item flagged can_be_countered=False survives counter()."""
        state = GameState()
        stack = StackManager(state)
        stack.push(StackItem(id="immune", type=StackItemType.SPELL,
                             source_id="c1", controller_id="p1",
                             can_be_countered=False))
        events = stack.counter("immune")
        assert events == []                       # counter() refused
        assert stack.size() == 1                  # still on the stack
        assert stack.top().id == "immune"

    def test_counter_default_still_counters(self):
        """Default (counterable) items are still removed — the hook is additive."""
        state = GameState()
        stack = StackManager(state)
        stack.push(StackItem(id="normal", type=StackItemType.SPELL,
                             source_id="c1", controller_id="p1"))
        stack.counter("normal")
        assert stack.is_empty()                   # countered as before


# =============================================================================
# Turn Manager Tests
# =============================================================================

class TestTurnState:
    """Test turn state tracking."""

    def test_initial_state(self):
        ts = TurnState()
        assert ts.turn_number == 0
        assert ts.land_played == False
        assert ts.lands_allowed == 1

    def test_land_tracking(self):
        ts = TurnState()
        ts.lands_played_count = 1
        ts.land_played = True
        assert ts.lands_played_count >= ts.lands_allowed


class TestPhaseAndStep:
    """Test phase and step enums."""

    def test_all_phases_exist(self):
        assert Phase.BEGINNING
        assert Phase.PRECOMBAT_MAIN
        assert Phase.COMBAT
        assert Phase.POSTCOMBAT_MAIN
        assert Phase.ENDING

    def test_all_steps_exist(self):
        assert Step.UNTAP
        assert Step.UPKEEP
        assert Step.DRAW
        assert Step.DECLARE_ATTACKERS
        assert Step.DECLARE_BLOCKERS
        assert Step.COMBAT_DAMAGE
        assert Step.END_STEP
        assert Step.CLEANUP


# =============================================================================
# Combat Manager Tests
# =============================================================================

class TestCombatState:
    """Test combat state."""

    def test_initial_state(self):
        cs = CombatState()
        assert len(cs.attackers) == 0
        assert len(cs.blockers) == 0
        assert len(cs.blocked_attackers) == 0

    def test_attack_declaration(self):
        cs = CombatState()
        decl = AttackDeclaration(
            attacker_id="c1",
            defending_player_id="p2"
        )
        cs.attackers.append(decl)
        assert len(cs.attackers) == 1

    def test_block_declaration(self):
        cs = CombatState()
        atk = AttackDeclaration(attacker_id="c1", defending_player_id="p2")
        blk = BlockDeclaration(blocker_id="c2", blocking_attacker_id="c1")

        cs.attackers.append(atk)
        cs.blockers.append(blk)
        cs.blocked_attackers.add("c1")

        assert "c1" in cs.blocked_attackers


class TestMustAttack:
    """CR 508.1a 'attacks each combat if able' — the additive must-attack hook."""

    def _setup(self, *, give_keyword):
        from src.engine.combat import CombatManager
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        abilities = [{'keyword': 'attacks_each_combat'}] if give_keyword else []
        ch = Characteristics(types={CardType.CREATURE}, power=2, toughness=1,
                             abilities=abilities)
        creature = game.create_object(name="Brute", owner_id=p1.id,
                                      zone=ZoneType.BATTLEFIELD, characteristics=ch)
        cm = CombatManager(game.state)   # no turn_manager -> active = first player
        return cm, p1, p2, creature

    def test_flagged_creature_is_forced(self):
        cm, p1, p2, creature = self._setup(give_keyword=True)
        decls = cm._apply_must_attack(p1.id, [creature.id], [])
        assert any(d.attacker_id == creature.id for d in decls), \
            "a creature that attacks-each-combat must be forced to attack"
        forced = next(d for d in decls if d.attacker_id == creature.id)
        assert forced.defending_player_id == p2.id

    def test_unflagged_creature_not_forced(self):
        """Additive: a plain creature is never forced."""
        cm, p1, p2, creature = self._setup(give_keyword=False)
        decls = cm._apply_must_attack(p1.id, [creature.id], [])
        assert decls == [], "an ordinary creature must not be forced to attack"

    def test_already_declared_not_duplicated(self):
        cm, p1, p2, creature = self._setup(give_keyword=True)
        existing = [AttackDeclaration(attacker_id=creature.id, defending_player_id=p2.id)]
        decls = cm._apply_must_attack(p1.id, [creature.id], existing)
        assert len([d for d in decls if d.attacker_id == creature.id]) == 1, \
            "a creature already attacking must not be added twice"


class TestAttackDespiteDefender:
    """The additive 'can attack as though it didn't have defender' override."""

    def _make_defender(self):
        from src.engine.combat import CombatManager
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        ch = Characteristics(types={CardType.CREATURE}, power=0, toughness=3,
                             abilities=[{'keyword': 'defender'}])
        creature = game.create_object(name="Wall", owner_id=p1.id,
                                      zone=ZoneType.BATTLEFIELD, characteristics=ch)
        creature.entered_zone_at = -1   # no summoning sickness
        cm = CombatManager(game.state)
        return cm, p1, creature

    def test_defender_blocks_attack_by_default(self):
        cm, p1, creature = self._make_defender()
        assert cm._can_attack(creature.id, p1.id) is False, \
            "a Defender creature cannot attack without the override"

    def test_override_lets_defender_attack(self):
        cm, p1, creature = self._make_defender()
        creature.state.can_attack_despite_defender = True
        assert cm._can_attack(creature.id, p1.id) is True, \
            "the override should let a Defender creature attack"

    def test_override_does_not_help_a_tapped_creature(self):
        """Additive: the override only bypasses Defender, not other rules."""
        cm, p1, creature = self._make_defender()
        creature.state.can_attack_despite_defender = True
        creature.state.tapped = True
        assert cm._can_attack(creature.id, p1.id) is False, \
            "the override must not override the tapped restriction"


# =============================================================================
# Priority System Tests
# =============================================================================

class TestActionType:
    """Test action types."""

    def test_all_actions_exist(self):
        assert ActionType.PASS
        assert ActionType.CAST_SPELL
        assert ActionType.ACTIVATE_ABILITY
        assert ActionType.PLAY_LAND


class TestPlayerAction:
    """Test player action creation."""

    def test_pass_action(self):
        action = PlayerAction(type=ActionType.PASS, player_id="p1")
        assert action.type == ActionType.PASS
        assert action.player_id == "p1"

    def test_cast_action(self):
        action = PlayerAction(
            type=ActionType.CAST_SPELL,
            player_id="p1",
            card_id="bolt",
            targets=[[Target(id="opp", is_player=True)]]
        )
        assert action.card_id == "bolt"
        assert len(action.targets) == 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestGameIntegration:
    """Test full game integration."""

    def test_game_creation(self):
        game = Game()
        assert game.state is not None
        assert game.mana_system is not None
        assert game.stack is not None
        assert game.turn_manager is not None
        assert game.priority_system is not None
        assert game.combat_manager is not None
        assert game.targeting_system is not None

    def test_add_players(self):
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")

        assert len(game.state.players) == 2
        assert p1.life == 20
        assert p2.life == 20

    def test_draw_cards(self):
        game = Game()
        p1 = game.add_player("Alice")

        # Add some cards to library
        card_def = make_creature("Test", 2, 2)
        for _ in range(10):
            game.add_card_to_library(p1.id, card_def)

        # Draw cards
        game.draw_cards(p1.id, 3)
        hand = game.get_hand(p1.id)
        assert len(hand) == 3

    def test_mana_operations(self):
        game = Game()
        p1 = game.add_player("Alice")

        game.add_mana(p1.id, ManaType.RED, 3)
        assert game.can_pay_cost(p1.id, "{R}{R}")
        assert game.pay_cost(p1.id, "{R}{R}")
        # Should have 1 red left
        assert game.can_pay_cost(p1.id, "{R}")
        assert not game.can_pay_cost(p1.id, "{R}{R}")

    def test_game_state_serialization(self):
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")

        state_dict = game.get_game_state_for_player(p1.id)

        assert 'turn_number' in state_dict
        assert 'phase' in state_dict
        assert 'players' in state_dict
        assert 'battlefield' in state_dict
        assert 'stack' in state_dict
        assert 'hand' in state_dict


class TestSpellCasting:
    """Test spell casting flow."""

    def test_spell_goes_on_stack(self):
        game = Game()
        p1 = game.add_player("Alice")

        # Create a spell in hand
        bolt_def = make_instant("Lightning Bolt", "{R}", {Color.RED},
                                "Deal 3 damage to any target.")
        bolt = game.create_object(
            name="Lightning Bolt",
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=bolt_def.characteristics,
            card_def=bolt_def
        )

        # Add mana
        game.add_mana(p1.id, ManaType.RED, 1)

        # Cast it (simplified - no targets for this test)
        item = game.cast_spell(bolt.id, p1.id)

        assert game.stack.size() == 1
        assert game.stack.top().source_id == bolt.id


class TestCombatFlow:
    """Test combat phase flow."""

    def test_combat_manager_queries(self):
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")

        # Create creature
        creature_def = make_creature("Grizzly Bears", 2, 2, "{1}{G}")
        creature = game.create_object(
            name="Grizzly Bears",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=creature_def.characteristics,
            card_def=creature_def
        )

        # Should be able to find legal attackers
        legal = game.combat_manager._get_legal_attackers(p1.id)
        # Note: may be empty due to summoning sickness in real game


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
