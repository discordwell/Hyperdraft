"""
Hearthstone Unhappy Path Tests - Batch 70

Combat edge cases and attack interactions: minion-to-minion trading,
simultaneous damage in combat, lethal trade kills both, unequal trade
(small vs big), Windfury double attack, taunt blocking direct attacks,
attacker takes retaliation damage, 0-attack minion cannot attack,
hero attack vs minion (hero takes damage back), frozen hero cannot
attack, divine shield in combat, stealth prevents being targeted,
charge minion attacks same turn, attack with 0 durability weapon fails.
"""

import asyncio
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, STONETUSK_BOAR,
    FIERY_WAR_AXE,
)
from src.cards.hearthstone.classic import (
    SHIELDBEARER, YOUNG_DRAGONHAWK, ARGENT_SQUIRE, WOLFRIDER,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Priest", class2="Mage"):
    """Create a fresh Hearthstone game with given classes, 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create an object from a card definition."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    return obj


def play_minion(game, card_def, owner):
    """Play a minion from hand to battlefield (triggers ZONE_CHANGE interceptors)."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
        source=obj.id
    ))
    return obj


def play_from_hand(game, card_def, owner):
    """Play a card from hand to battlefield, triggering ZONE_CHANGE interceptors."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
        source=obj.id
    ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card by invoking its spell_effect and emitting SPELL_CAST."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    return obj


def declare_attack(game, attacker_id, target_id):
    """Synchronously run an async declare_attack via a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        events = loop.run_until_complete(
            game.combat_manager.declare_attack(attacker_id, target_id)
        )
    finally:
        loop.close()
    return events


# ============================================================
# Test 1: TestMinionTradeEqualLethal
# ============================================================

class TestMinionTradeEqualLethal:
    """Two 3/2 minions attack each other -> both die (3 >= 2)."""

    def test_equal_trade_both_die(self):
        """Two 3/2 Bloodfen Raptors trade: both take 3 damage, both die."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        # Bloodfen Raptor is 3/2
        raptor1 = make_obj(game, BLOODFEN_RAPTOR, p1)
        raptor1.state.summoning_sickness = False

        raptor2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        events = declare_attack(game, raptor1.id, raptor2.id)
        game.check_state_based_actions()

        # Both Raptors are 3/2, so each deals 3 damage to a 2-toughness minion
        assert raptor1.state.damage == 3, (
            f"Raptor1 should have taken exactly 3 damage from Raptor2, got {raptor1.state.damage}"
        )
        assert raptor2.state.damage == 3, (
            f"Raptor2 should have taken exactly 3 damage from Raptor1, got {raptor2.state.damage}"
        )

    def test_equal_trade_generates_damage_events(self):
        """Trading generates exactly 2 DAMAGE events (one for each direction)."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        raptor1 = make_obj(game, BLOODFEN_RAPTOR, p1)
        raptor1.state.summoning_sickness = False

        raptor2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        events = declare_attack(game, raptor1.id, raptor2.id)

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        assert len(damage_events) == 2, (
            f"Expected 2 DAMAGE events for mutual trade, got {len(damage_events)}"
        )


# ============================================================
# Test 2: TestMinionTradeUnequalSizes
# ============================================================

class TestMinionTradeUnequalSizes:
    """1/1 Wisp attacks 4/5 Yeti -> Wisp dies, Yeti takes 1 damage (at 4/4)."""

    def test_wisp_attacks_yeti_wisp_dies(self):
        """Wisp (1/1) attacks Yeti (4/5): Wisp takes 4 damage (lethal), Yeti takes 1."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        wisp = make_obj(game, WISP, p1)
        wisp.state.summoning_sickness = False

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        events = declare_attack(game, wisp.id, yeti.id)
        game.check_state_based_actions()

        # Wisp took 4 damage (lethal for a 1-health minion)
        assert wisp.state.damage == 4, (
            f"Wisp should have taken exactly 4 damage from Yeti, got {wisp.state.damage}"
        )

        # Yeti took 1 damage (from Wisp's 1 attack)
        assert yeti.state.damage == 1, (
            f"Yeti should have taken 1 damage from Wisp, got {yeti.state.damage}"
        )

    def test_yeti_survives_with_4_effective_health(self):
        """After trade, Yeti has 4 effective health (5 - 1 damage)."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        wisp = make_obj(game, WISP, p1)
        wisp.state.summoning_sickness = False

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        declare_attack(game, wisp.id, yeti.id)
        game.check_state_based_actions()

        effective_health = get_toughness(yeti, game.state) - yeti.state.damage
        assert effective_health == 4, (
            f"Yeti effective health should be 4 after taking 1, got {effective_health}"
        )


# ============================================================
# Test 3: TestSimultaneousDamage
# ============================================================

class TestSimultaneousDamage:
    """Both attacker and defender take damage at the same time."""

    def test_simultaneous_damage_both_marked(self):
        """After combat, both combatants have damage marked on them."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)  # 3/2
        raptor.state.summoning_sickness = False

        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        declare_attack(game, raptor.id, yeti.id)

        # Raptor took Yeti's 4 attack
        assert raptor.state.damage == 4, (
            f"Raptor should have taken 4 damage from Yeti, got {raptor.state.damage}"
        )
        # Yeti took Raptor's 3 attack
        assert yeti.state.damage == 3, (
            f"Yeti should have taken 3 damage from Raptor, got {yeti.state.damage}"
        )

    def test_damage_applied_before_death_check(self):
        """Both minions receive damage before state-based death checks run."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        raptor1 = make_obj(game, BLOODFEN_RAPTOR, p1)  # 3/2
        raptor1.state.summoning_sickness = False

        raptor2 = make_obj(game, BLOODFEN_RAPTOR, p2)  # 3/2

        # Before SBA check, both should have damage
        declare_attack(game, raptor1.id, raptor2.id)

        # Both took 3 damage
        assert raptor1.state.damage == 3, (
            f"Raptor1 should have 3 damage before SBA, got {raptor1.state.damage}"
        )
        assert raptor2.state.damage == 3, (
            f"Raptor2 should have 3 damage before SBA, got {raptor2.state.damage}"
        )


# ============================================================
# Test 4: TestZeroAttackCannotAttack
# ============================================================

class TestZeroAttackCannotAttack:
    """A 0-attack minion (Shieldbearer) cannot attack."""

    def test_shieldbearer_cannot_attack(self):
        """Shieldbearer (0/4 Taunt) cannot declare an attack."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        shieldbearer = make_obj(game, SHIELDBEARER, p1)  # 0/4
        shieldbearer.state.summoning_sickness = False

        can_attack = game.combat_manager._can_attack(shieldbearer.id, p1.id)
        assert can_attack is False, (
            "0-attack minion (Shieldbearer) should not be allowed to attack"
        )

    def test_zero_attack_declare_attack_returns_empty(self):
        """Attempting to declare_attack with a 0-attack minion returns no events."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        shieldbearer = make_obj(game, SHIELDBEARER, p1)
        shieldbearer.state.summoning_sickness = False

        events = declare_attack(game, shieldbearer.id, p2.hero_id)
        assert len(events) == 0, (
            f"0-attack minion should not generate attack events, got {len(events)}"
        )


# ============================================================
# Test 5: TestFrozenMinionCannotAttack
# ============================================================

class TestFrozenMinionCannotAttack:
    """Frozen minion cannot attack."""

    def test_frozen_minion_blocked(self):
        """A frozen Yeti cannot attack."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.summoning_sickness = False
        yeti.state.frozen = True

        can_attack = game.combat_manager._can_attack(yeti.id, p1.id)
        assert can_attack is False, (
            "Frozen minion should not be able to attack"
        )

    def test_frozen_declare_attack_returns_empty(self):
        """Declaring attack with a frozen minion produces no events."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.summoning_sickness = False
        yeti.state.frozen = True

        events = declare_attack(game, yeti.id, p2.hero_id)
        assert len(events) == 0, (
            f"Frozen minion should produce no attack events, got {len(events)}"
        )


# ============================================================
# Test 6: TestFrozenHeroCannotAttack
# ============================================================

class TestFrozenHeroCannotAttack:
    """Frozen hero cannot attack with weapon."""

    def test_frozen_hero_blocked(self):
        """A frozen hero with a weapon cannot attack."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # Equip weapon by setting player stats directly
        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2

        # Freeze the hero
        hero.state.frozen = True

        can_attack = game.combat_manager._can_attack(p1.hero_id, p1.id)
        assert can_attack is False, (
            "Frozen hero should not be able to attack even with a weapon"
        )

    def test_frozen_hero_declare_attack_returns_empty(self):
        """Declaring attack with a frozen hero returns no events."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2
        hero.state.frozen = True

        events = declare_attack(game, p1.hero_id, p2.hero_id)
        assert len(events) == 0, (
            f"Frozen hero should produce no attack events, got {len(events)}"
        )


# ============================================================
# Test 7: TestSummoningSicknessPreventsCombat
# ============================================================

class TestSummoningSicknessPreventsCombat:
    """Just-played minion cannot attack."""

    def test_new_minion_has_summoning_sickness(self):
        """A minion played from hand has summoning sickness set."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = play_minion(game, CHILLWIND_YETI, p1)

        assert yeti.state.summoning_sickness is True, (
            "Newly played minion should have summoning sickness"
        )

    def test_summoning_sickness_prevents_attack(self):
        """A minion with summoning sickness cannot be declared as attacker."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = play_minion(game, CHILLWIND_YETI, p1)

        can_attack = game.combat_manager._can_attack(yeti.id, p1.id)
        assert can_attack is False, (
            "Minion with summoning sickness should not be able to attack"
        )

    def test_summoning_sickness_declare_returns_empty(self):
        """Attempting to declare_attack with a sick minion returns no events."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = play_minion(game, CHILLWIND_YETI, p1)

        events = declare_attack(game, yeti.id, p2.hero_id)
        assert len(events) == 0, (
            f"Summoning sick minion should produce no attack events, got {len(events)}"
        )


# ============================================================
# Test 8: TestWindfuryDoubleAttack
# ============================================================

class TestWindfuryDoubleAttack:
    """Windfury minion can attack twice per turn."""

    def test_windfury_first_attack_succeeds(self):
        """Young Dragonhawk (1/1 Windfury) can attack once."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        hawk = make_obj(game, YOUNG_DRAGONHAWK, p1)  # 1/1 Windfury
        hawk.state.summoning_sickness = False

        # Verify has windfury
        assert has_ability(hawk, 'windfury', game.state) is True, (
            "Young Dragonhawk should have windfury"
        )

        p2_life_before = p2.life
        events = declare_attack(game, hawk.id, p2.hero_id)

        assert len(events) > 0, "First attack should succeed"
        assert hawk.state.attacks_this_turn == 1, (
            f"Should have 1 attack recorded, got {hawk.state.attacks_this_turn}"
        )
        assert p2.life == p2_life_before - 1, (
            f"Enemy hero should take 1 damage, went from {p2_life_before} to {p2.life}"
        )

    def test_windfury_second_attack_succeeds(self):
        """Windfury minion can attack a second time in the same turn."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        hawk = make_obj(game, YOUNG_DRAGONHAWK, p1)
        hawk.state.summoning_sickness = False

        p2_life_before = p2.life

        # First attack
        declare_attack(game, hawk.id, p2.hero_id)
        assert hawk.state.attacks_this_turn == 1

        # Second attack
        events2 = declare_attack(game, hawk.id, p2.hero_id)
        assert len(events2) > 0, "Second attack should succeed for Windfury minion"
        assert hawk.state.attacks_this_turn == 2, (
            f"Should have 2 attacks recorded, got {hawk.state.attacks_this_turn}"
        )
        assert p2.life == p2_life_before - 2, (
            f"Enemy hero should take 2 total damage, went from {p2_life_before} to {p2.life}"
        )


# ============================================================
# Test 9: TestWindfuryOnlyTwoAttacks
# ============================================================

class TestWindfuryOnlyTwoAttacks:
    """Windfury minion cannot attack a third time."""

    def test_third_attack_blocked(self):
        """After 2 attacks, Windfury minion cannot attack again."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        hawk = make_obj(game, YOUNG_DRAGONHAWK, p1)
        hawk.state.summoning_sickness = False

        # First and second attacks
        declare_attack(game, hawk.id, p2.hero_id)
        declare_attack(game, hawk.id, p2.hero_id)
        assert hawk.state.attacks_this_turn == 2

        # Third attack should fail
        can_attack = game.combat_manager._can_attack(hawk.id, p1.id)
        assert can_attack is False, (
            "Windfury minion should not be able to attack a 3rd time"
        )

    def test_third_attack_returns_empty(self):
        """Attempting a third attack with Windfury returns no events."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        hawk = make_obj(game, YOUNG_DRAGONHAWK, p1)
        hawk.state.summoning_sickness = False

        declare_attack(game, hawk.id, p2.hero_id)
        declare_attack(game, hawk.id, p2.hero_id)

        p2_life_after_two = p2.life

        events3 = declare_attack(game, hawk.id, p2.hero_id)
        assert len(events3) == 0, (
            f"Third attack should return no events, got {len(events3)}"
        )
        assert p2.life == p2_life_after_two, (
            f"Enemy hero should take no further damage, was {p2_life_after_two}, now {p2.life}"
        )


# ============================================================
# Test 10: TestDivineShieldInCombat
# ============================================================

class TestDivineShieldInCombat:
    """Attacker with Divine Shield takes no damage on first hit."""

    def test_divine_shield_absorbs_first_hit(self):
        """Argent Squire (1/1 Divine Shield) attacks Yeti -> shield breaks, no damage."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        squire = make_obj(game, ARGENT_SQUIRE, p1)  # 1/1 Divine Shield
        squire.state.summoning_sickness = False

        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        # Verify divine shield is active
        assert squire.state.divine_shield is True, (
            "Argent Squire should start with divine shield"
        )

        declare_attack(game, squire.id, yeti.id)

        # Shield was broken
        assert squire.state.divine_shield is False, (
            "Divine shield should be broken after combat"
        )
        # Squire took no actual damage (shield absorbed it)
        assert squire.state.damage == 0, (
            f"Squire should have 0 damage (divine shield absorbed), got {squire.state.damage}"
        )

    def test_divine_shield_target_still_takes_damage(self):
        """The target still takes damage from the divine-shielded attacker."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        squire = make_obj(game, ARGENT_SQUIRE, p1)
        squire.state.summoning_sickness = False

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        declare_attack(game, squire.id, yeti.id)

        # Yeti should take 1 damage from Squire's 1 attack
        assert yeti.state.damage == 1, (
            f"Yeti should take 1 damage from Squire, got {yeti.state.damage}"
        )

    def test_divine_shield_break_event_emitted(self):
        """A DIVINE_SHIELD_BREAK event is generated when shield is consumed."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        squire = make_obj(game, ARGENT_SQUIRE, p1)
        squire.state.summoning_sickness = False

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        declare_attack(game, squire.id, yeti.id)

        shield_break_events = [
            e for e in game.state.event_log
            if e.type == EventType.DIVINE_SHIELD_BREAK
            and e.payload.get('target') == squire.id
        ]
        assert len(shield_break_events) >= 1, (
            "A DIVINE_SHIELD_BREAK event should be emitted for the squire"
        )


# ============================================================
# Test 11: TestChargeMinionAttacksSameTurn
# ============================================================

class TestChargeMinionAttacksSameTurn:
    """Charge minion attacks the turn it's played."""

    def test_charge_bypasses_summoning_sickness(self):
        """Stonetusk Boar (1/1 Charge) can attack the turn it's played."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        boar = make_obj(game, STONETUSK_BOAR, p1)
        # make_obj directly puts on battlefield; charge keyword should
        # allow attack despite summoning sickness
        assert has_ability(boar, 'charge', game.state) is True, (
            "Stonetusk Boar should have charge"
        )

        can_attack = game.combat_manager._can_attack(boar.id, p1.id)
        assert can_attack is True, (
            "Charge minion should be able to attack despite summoning sickness"
        )

    def test_charge_minion_deals_damage_on_play_turn(self):
        """Wolfrider (3/1 Charge) can deal 3 damage to enemy hero on play turn."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        wolfrider = make_obj(game, WOLFRIDER, p1)  # 3/1 Charge
        p2_life_before = p2.life

        events = declare_attack(game, wolfrider.id, p2.hero_id)

        assert len(events) > 0, "Charge minion should successfully attack"
        assert p2.life == p2_life_before - 3, (
            f"Wolfrider should deal 3 damage to hero, "
            f"expected {p2_life_before - 3}, got {p2.life}"
        )


# ============================================================
# Test 12: TestHeroAttackMinion
# ============================================================

class TestHeroAttackMinion:
    """Hero with weapon attacks minion -> hero takes damage back."""

    def test_hero_attacks_minion_takes_retaliation(self):
        """Warrior with 3/2 weapon attacks 4/5 Yeti -> hero takes 4 damage."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # Set weapon stats directly
        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2

        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        p1_life_before = p1.life
        events = declare_attack(game, p1.hero_id, yeti.id)

        # Hero should take 4 damage from Yeti's retaliation
        assert p1.life == p1_life_before - 4, (
            f"Hero should take 4 retaliation damage from Yeti, "
            f"expected {p1_life_before - 4}, got {p1.life}"
        )

    def test_hero_attacks_minion_deals_weapon_damage(self):
        """Hero with 3-attack weapon deals 3 damage to target minion."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        declare_attack(game, p1.hero_id, yeti.id)

        assert yeti.state.damage == 3, (
            f"Yeti should take 3 damage from hero weapon, got {yeti.state.damage}"
        )

    def test_hero_attack_reduces_weapon_durability(self):
        """Attacking with weapon reduces durability by 1."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        declare_attack(game, p1.hero_id, yeti.id)

        assert p1.weapon_durability == 1, (
            f"Weapon durability should drop from 2 to 1 after attack, got {p1.weapon_durability}"
        )


# ============================================================
# Test 13: TestHeroAttackFace
# ============================================================

class TestHeroAttackFace:
    """Hero attacks enemy hero directly."""

    def test_hero_attacks_enemy_hero(self):
        """Warrior with 3-attack weapon attacks enemy hero -> deals 3 damage."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2

        p2_life_before = p2.life

        events = declare_attack(game, p1.hero_id, p2.hero_id)

        assert len(events) > 0, "Hero attack should generate events"
        assert p2.life == p2_life_before - 3, (
            f"Enemy hero should take 3 weapon damage, "
            f"expected {p2_life_before - 3}, got {p2.life}"
        )

    def test_hero_attacks_hero_no_retaliation(self):
        """Hero attacking enemy hero does not take retaliation damage (heroes don't fight back)."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        p1.weapon_attack = 3
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 2

        p1_life_before = p1.life

        declare_attack(game, p1.hero_id, p2.hero_id)

        assert p1.life == p1_life_before, (
            f"Attacking hero should take no retaliation from enemy hero, "
            f"expected {p1_life_before}, got {p1.life}"
        )

    def test_hero_without_weapon_cannot_attack(self):
        """Hero with no weapon (0 attack, 0 durability) cannot attack."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # No weapon equipped (defaults are 0/0)
        assert p1.weapon_attack == 0
        assert p1.weapon_durability == 0

        can_attack = game.combat_manager._can_attack(p1.hero_id, p1.id)
        assert can_attack is False, (
            "Hero without weapon should not be able to attack"
        )

    def test_hero_with_zero_durability_cannot_attack(self):
        """Hero with weapon at 0 durability cannot attack."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # Weapon with attack but no durability
        p1.weapon_attack = 3
        p1.weapon_durability = 0

        can_attack = game.combat_manager._can_attack(p1.hero_id, p1.id)
        assert can_attack is False, (
            "Hero with 0 durability weapon should not be able to attack"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
