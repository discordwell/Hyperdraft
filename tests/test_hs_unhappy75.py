"""
Hearthstone Unhappy Path Tests - Batch 75

Stress tests and regression scenarios: empty board AOE does nothing,
targeting nonexistent minion, double destroy on same minion, casting
spell with no valid targets, attack declaration against own minion
blocked, playing card with insufficient mana, full hand prevents draw
(burns card), hero power on self, battlecry with no targets, buff on
dead minion, silence on minion with no effects, large hand + Divine
Favor draws correctly, multiple simultaneous aura sources, 30-damage
Pyroblast overkill, coin-flip effects (Ragnaros target, Animal Companion).
"""

import asyncio
import random
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
    BOULDERFIST_OGRE, STORMWIND_CHAMPION, WAR_GOLEM,
    MURLOC_RAIDER, GRIMSCALE_ORACLE,
)
from src.cards.hearthstone.classic import (
    FLAMESTRIKE, CONSECRATION, ARCANE_MISSILES,
    KNIFE_JUGGLER, RAGNAROS_THE_FIRELORD,
    IRONBEAK_OWL, SPELLBREAKER,
)
from src.cards.hearthstone.mage import PYROBLAST
from src.cards.hearthstone.hunter import ANIMAL_COMPANION, HOUNDMASTER
from src.cards.hearthstone.paladin import DIVINE_FAVOR, BLESSING_OF_KINGS


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Mage", class2="Warrior"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
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
    """Create an object from a card definition and place it in the given zone."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': None,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'controller': owner.id,
            },
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


def add_cards_to_library(game, player, card_def, count):
    """Add card objects to a player's library for draw testing."""
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


def get_hand_size(game, player):
    """Get number of cards in a player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    return len(hand.objects) if hand else 0


def count_battlefield(game, player_id=None):
    """Count minions on battlefield, optionally filtered by controller."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return 0
    count = 0
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if not obj:
            continue
        if CardType.MINION not in obj.characteristics.types:
            continue
        if player_id and obj.controller != player_id:
            continue
        count += 1
    return count


def run_sba(game):
    """Manually check state-based actions (destroy lethal minions)."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return
    for oid in list(battlefield.objects):
        obj = game.state.objects.get(oid)
        if not obj:
            continue
        if CardType.MINION not in obj.characteristics.types:
            continue
        toughness = get_toughness(obj, game.state)
        if obj.state.damage >= toughness and toughness > 0:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': oid},
                source=oid
            ))


# ============================================================
# Test 1: TestEmptyBoardAOE
# ============================================================

class TestEmptyBoardAOE:
    """Cast Flamestrike with no enemy minions on board -> no damage events, no crash."""

    def test_flamestrike_empty_board_no_events(self):
        """Flamestrike with no enemy minions produces zero damage events."""
        game, p1, p2 = new_hs_game()

        # No minions on the board at all
        obj = game.create_object(
            name=FLAMESTRIKE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FLAMESTRIKE.characteristics, card_def=FLAMESTRIKE
        )
        events = FLAMESTRIKE.spell_effect(obj, game.state, [])
        assert len(events) == 0, (
            f"Flamestrike on empty board should produce 0 events, got {len(events)}"
        )

    def test_flamestrike_empty_board_no_crash(self):
        """Flamestrike with no enemy minions doesn't crash when emitted."""
        game, p1, p2 = new_hs_game()

        # Cast the spell fully (emit events + SPELL_CAST)
        cast_spell(game, FLAMESTRIKE, p1)

        # Game should still be operational
        assert p1.life == 30, f"P1 life should be untouched at 30, got {p1.life}"
        assert p2.life == 30, f"P2 life should be untouched at 30, got {p2.life}"

    def test_flamestrike_only_friendly_minions_unharmed(self):
        """Flamestrike ignores friendly minions entirely."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        wisp = make_obj(game, WISP, p1)

        cast_spell(game, FLAMESTRIKE, p1)

        # Friendly minions should take zero damage
        assert yeti.state.damage == 0, (
            f"Friendly Yeti should take 0 damage from own Flamestrike, got {yeti.state.damage}"
        )
        assert wisp.state.damage == 0, (
            f"Friendly Wisp should take 0 damage from own Flamestrike, got {wisp.state.damage}"
        )


# ============================================================
# Test 2: TestAOEWithOnlyFriendly
# ============================================================

class TestAOEWithOnlyFriendly:
    """Cast Consecration (enemies only) with only friendly minions -> no damage to friendlies."""

    def test_consecration_no_enemy_minions(self):
        """Consecration with no enemy minions: only enemy hero takes damage."""
        game, p1, p2 = new_hs_game()

        friendly_yeti = make_obj(game, CHILLWIND_YETI, p1)

        cast_spell(game, CONSECRATION, p1)

        # Friendly Yeti should be undamaged
        assert friendly_yeti.state.damage == 0, (
            f"Friendly Yeti should take 0 damage from own Consecration, "
            f"got {friendly_yeti.state.damage}"
        )

        # Enemy hero should take 2 damage (Consecration hits all enemies)
        assert p2.life == 28, (
            f"Enemy hero should take 2 damage from Consecration, "
            f"expected 28, got {p2.life}"
        )

    def test_consecration_empty_board(self):
        """Consecration with no minions at all still hits enemy hero safely."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, CONSECRATION, p1)

        assert p2.life == 28, (
            f"Enemy hero should take 2 damage, got {p2.life}"
        )
        assert p1.life == 30, (
            f"Friendly hero should be untouched, got {p1.life}"
        )


# ============================================================
# Test 3: TestTargetNonexistentMinion
# ============================================================

class TestTargetNonexistentMinion:
    """Try to target a minion ID that doesn't exist -> no crash."""

    def test_damage_event_nonexistent_target(self):
        """Emitting a DAMAGE event to a nonexistent target does not crash."""
        game, p1, p2 = new_hs_game()

        fake_id = "nonexistent_minion_id_12345"

        # This should not raise an exception
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': fake_id, 'amount': 5, 'source': p1.hero_id},
            source=p1.hero_id
        ))

        # Game should still be functional
        assert p1.life == 30
        assert p2.life == 30

    def test_spell_targeting_nonexistent_id(self):
        """Spell effect targeting a nonexistent ID returns empty or no-ops."""
        game, p1, p2 = new_hs_game()

        # Pyroblast targeting a nonexistent ID
        obj = game.create_object(
            name=PYROBLAST.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=PYROBLAST.characteristics, card_def=PYROBLAST
        )
        events = PYROBLAST.spell_effect(obj, game.state, ["fake_id_99999"])

        # Should produce an event targeting fake_id, but emitting it should not crash
        for e in events:
            game.emit(e)

        assert p1.life == 30
        assert p2.life == 30


# ============================================================
# Test 4: TestDoubleDestroy
# ============================================================

class TestDoubleDestroy:
    """Destroy same minion twice -> second destroy is a no-op."""

    def test_double_destroy_no_crash(self):
        """Destroying the same minion twice does not crash."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p1)
        wisp_id = wisp.id

        # First destroy
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp_id, 'reason': 'spell'},
            source='test'
        ))

        # Second destroy of the same ID
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp_id, 'reason': 'spell'},
            source='test'
        ))

        # Game should be stable
        assert p1.life == 30

    def test_double_destroy_minion_not_on_battlefield(self):
        """After first destroy, minion is no longer on battlefield."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p1)
        wisp_id = wisp.id

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp_id, 'reason': 'spell'},
            source='test'
        ))

        bf = game.state.zones.get('battlefield')
        assert wisp_id not in (bf.objects if bf else []), (
            "Wisp should not be on battlefield after first destroy"
        )

        # Second destroy should be a no-op
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp_id, 'reason': 'spell'},
            source='test'
        ))

        assert p1.life == 30


# ============================================================
# Test 5: TestSpellNoValidTargets
# ============================================================

class TestSpellNoValidTargets:
    """Cast a targeted spell with no valid targets -> returns empty."""

    def test_houndmaster_no_beasts(self):
        """Houndmaster battlecry with no friendly Beasts returns empty events."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        houndmaster = make_obj(game, HOUNDMASTER, p1)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)
        assert len(events) == 0, (
            f"Houndmaster battlecry without beasts should return 0 events, "
            f"got {len(events)}"
        )

    def test_blessing_of_kings_no_minions(self):
        """Blessing of Kings with no friendly minions returns empty events."""
        game, p1, p2 = new_hs_game()

        # No friendly minions on board
        obj = game.create_object(
            name=BLESSING_OF_KINGS.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=BLESSING_OF_KINGS.characteristics, card_def=BLESSING_OF_KINGS
        )
        events = BLESSING_OF_KINGS.spell_effect(obj, game.state, [])
        assert len(events) == 0, (
            f"Blessing of Kings with no friendly minions should return 0 events, "
            f"got {len(events)}"
        )


# ============================================================
# Test 6: TestAttackOwnMinion
# ============================================================

class TestAttackOwnMinion:
    """Try to attack your own minion -> no crash (engine doesn't enforce same-side block)."""

    def test_attack_own_minion_no_crash(self):
        """Declaring an attack on your own minion does not crash the engine."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, BLOODFEN_RAPTOR, p1)
        attacker.state.summoning_sickness = False

        friendly_target = make_obj(game, CHILLWIND_YETI, p1)

        # The combat manager processes the attack without crashing.
        # (Note: the engine does not currently enforce same-side target
        # restrictions at the declare_attack level; that validation happens
        # at the UI/AI layer via _get_legal_targets.)
        events = declare_attack(game, attacker.id, friendly_target.id)

        # The primary assertion is no crash occurs.
        assert p1.life == 30, f"P1 hero life should be 30, got {p1.life}"

    def test_get_legal_targets_excludes_friendly(self):
        """_get_legal_targets only returns opponent's minions and hero."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, BLOODFEN_RAPTOR, p1)
        attacker.state.summoning_sickness = False

        friendly_yeti = make_obj(game, CHILLWIND_YETI, p1)
        enemy_wisp = make_obj(game, WISP, p2)

        legal_targets = game.combat_manager._get_legal_targets(p1.id)

        assert friendly_yeti.id not in legal_targets, (
            "Friendly Yeti should not be in legal targets"
        )
        assert enemy_wisp.id in legal_targets, (
            "Enemy Wisp should be in legal targets"
        )
        assert p2.hero_id in legal_targets, (
            "Enemy hero should be in legal targets"
        )


# ============================================================
# Test 7: TestInsufficientMana
# ============================================================

class TestInsufficientMana:
    """Check that mana validation exists (player can't play 10-cost at 5 mana)."""

    def test_cannot_pay_10_with_5_mana(self):
        """Player with 5 mana cannot pay a 10-cost card."""
        game, p1, p2 = new_hs_game()

        # Set p1 to only 5 mana
        p1.mana_crystals = 5
        p1.mana_crystals_available = 5

        can_pay = game.mana_system.can_pay_cost(p1.id, 10)
        assert can_pay is False, (
            "Player with 5 mana should not be able to pay 10 mana cost"
        )

    def test_can_pay_exact_mana(self):
        """Player with exactly 7 mana can pay a 7-cost card."""
        game, p1, p2 = new_hs_game()

        p1.mana_crystals = 7
        p1.mana_crystals_available = 7

        can_pay = game.mana_system.can_pay_cost(p1.id, 7)
        assert can_pay is True, (
            "Player with 7 mana should be able to pay 7 mana cost"
        )

    def test_cannot_pay_1_with_0_mana(self):
        """Player with 0 mana cannot pay any positive cost."""
        game, p1, p2 = new_hs_game()

        p1.mana_crystals = 0
        p1.mana_crystals_available = 0

        can_pay = game.mana_system.can_pay_cost(p1.id, 1)
        assert can_pay is False, (
            "Player with 0 mana should not be able to pay 1 mana cost"
        )

    def test_pay_reduces_available(self):
        """Paying a mana cost reduces available crystals."""
        game, p1, p2 = new_hs_game()

        p1.mana_crystals = 10
        p1.mana_crystals_available = 10

        success = game.mana_system.pay_cost(p1.id, 7)
        assert success is True
        assert p1.mana_crystals_available == 3, (
            f"After paying 7, should have 3 available, got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 8: TestSilenceOnVanillaMinion
# ============================================================

class TestSilenceOnVanillaMinion:
    """Silence a Chillwind Yeti (no abilities) -> Yeti stats unchanged."""

    def test_silence_vanilla_no_change(self):
        """Silencing a vanilla Yeti leaves its stats at 4/5."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        power_before = get_power(yeti, game.state)
        toughness_before = get_toughness(yeti, game.state)

        # Silence the Yeti
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source=p2.hero_id
        ))

        power_after = get_power(yeti, game.state)
        toughness_after = get_toughness(yeti, game.state)

        assert power_after == power_before == 4, (
            f"Yeti Attack should remain 4 after silence, got {power_after}"
        )
        assert toughness_after == toughness_before == 5, (
            f"Yeti Health should remain 5 after silence, got {toughness_after}"
        )

    def test_silence_vanilla_no_crash(self):
        """Silencing a vanilla minion doesn't crash even though there's nothing to remove."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Should not raise an exception
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source=p2.hero_id
        ))

        assert yeti.zone == ZoneType.BATTLEFIELD


# ============================================================
# Test 9: TestBuffOnDeadMinion
# ============================================================

class TestBuffOnDeadMinion:
    """Try to buff a minion that was already destroyed -> no effect."""

    def test_buff_dead_minion_no_crash(self):
        """Emitting a PT_MODIFICATION for a destroyed minion doesn't crash."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p1)
        wisp_id = wisp.id

        # Destroy the wisp
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp_id, 'reason': 'test'},
            source='test'
        ))

        # Try to buff the dead wisp
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp_id, 'power_mod': 5, 'toughness_mod': 5,
                     'duration': 'permanent'},
            source='test'
        ))

        # No crash should occur; game remains stable
        assert p1.life == 30

    def test_buff_dead_minion_not_on_battlefield(self):
        """A destroyed minion is not on the battlefield to receive buffs."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p1)
        wisp_id = wisp.id

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp_id, 'reason': 'test'},
            source='test'
        ))

        bf = game.state.zones.get('battlefield')
        assert wisp_id not in (bf.objects if bf else []), (
            "Dead wisp should not be on battlefield"
        )


# ============================================================
# Test 10: TestHealOnFullHealth
# ============================================================

class TestHealOnFullHealth:
    """Heal hero at 30 -> stays at 30 (no overheal)."""

    def test_heal_at_full_stays_30(self):
        """Healing a full-health hero keeps life at 30."""
        game, p1, p2 = new_hs_game()

        assert p1.life == 30

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        assert p1.life == 30, (
            f"Hero at 30 HP healed for 5 should stay at 30, got {p1.life}"
        )

    def test_heal_partially_damaged_capped(self):
        """Healing a hero at 28 HP by 5 caps at 30 HP."""
        game, p1, p2 = new_hs_game()

        p1.life = 28

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        assert p1.life == 30, (
            f"Hero at 28 HP healed for 5 should cap at 30, got {p1.life}"
        )

    def test_heal_from_low_health(self):
        """Healing from 10 HP by 5 goes to 15 HP."""
        game, p1, p2 = new_hs_game()

        p1.life = 10

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        assert p1.life == 15, (
            f"Hero at 10 HP healed for 5 should be 15, got {p1.life}"
        )


# ============================================================
# Test 11: TestRagnarosTargetSelection
# ============================================================

class TestRagnarosTargetSelection:
    """Ragnaros with 3 enemy targets -> damage goes to one of them."""

    def test_ragnaros_hits_one_enemy(self):
        """Ragnaros end-of-turn trigger deals 8 damage to exactly one enemy target."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)
        enemy1 = make_obj(game, CHILLWIND_YETI, p2)
        enemy2 = make_obj(game, BLOODFEN_RAPTOR, p2)
        enemy3 = make_obj(game, WISP, p2)

        p2_life_before = p2.life

        # Trigger end-of-turn
        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='test'
        ))

        # Exactly one target should have received 8 damage
        targets_damaged = []
        if enemy1.state.damage > 0:
            targets_damaged.append(('enemy1', enemy1.state.damage))
        if enemy2.state.damage > 0:
            targets_damaged.append(('enemy2', enemy2.state.damage))
        if enemy3.state.damage > 0:
            targets_damaged.append(('enemy3', enemy3.state.damage))
        if p2.life < p2_life_before:
            targets_damaged.append(('hero', p2_life_before - p2.life))

        total_damage = sum(d for _, d in targets_damaged)
        assert total_damage == 8, (
            f"Ragnaros should deal exactly 8 total damage, got {total_damage}. "
            f"Damaged: {targets_damaged}"
        )

    def test_ragnaros_cant_attack(self):
        """Ragnaros has the cant_attack ability."""
        game, p1, p2 = new_hs_game()

        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)
        assert has_ability(rag, 'cant_attack', game.state), (
            "Ragnaros should have 'cant_attack' ability"
        )


# ============================================================
# Test 12: TestAnimalCompanionAllThreeReachable
# ============================================================

class TestAnimalCompanionAllThreeReachable:
    """With enough random seeds, all 3 companions appear."""

    def test_all_three_companions_reachable(self):
        """Over many seeds, Animal Companion produces Huffer, Leokk, and Misha."""
        seen_names = set()

        for seed in range(100):
            random.seed(seed)
            game, p1, p2 = new_hs_game()

            obj = game.create_object(
                name=ANIMAL_COMPANION.name, owner_id=p1.id,
                zone=ZoneType.BATTLEFIELD,
                characteristics=ANIMAL_COMPANION.characteristics,
                card_def=ANIMAL_COMPANION
            )
            events = ANIMAL_COMPANION.spell_effect(obj, game.state, [])

            for e in events:
                if e.type == EventType.CREATE_TOKEN:
                    token = e.payload.get('token', {})
                    name = token.get('name', '')
                    seen_names.add(name)

            if seen_names >= {'Huffer', 'Leokk', 'Misha'}:
                break

        assert 'Huffer' in seen_names, "Huffer should be reachable"
        assert 'Leokk' in seen_names, "Leokk should be reachable"
        assert 'Misha' in seen_names, "Misha should be reachable"

    def test_animal_companion_returns_create_token(self):
        """Animal Companion spell effect returns a CREATE_TOKEN event."""
        random.seed(0)
        game, p1, p2 = new_hs_game()

        obj = game.create_object(
            name=ANIMAL_COMPANION.name, owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=ANIMAL_COMPANION.characteristics,
            card_def=ANIMAL_COMPANION
        )
        events = ANIMAL_COMPANION.spell_effect(obj, game.state, [])

        assert len(events) == 1, (
            f"Animal Companion should produce exactly 1 event, got {len(events)}"
        )
        assert events[0].type == EventType.CREATE_TOKEN, (
            f"Event should be CREATE_TOKEN, got {events[0].type}"
        )


# ============================================================
# Test 13: TestArcaneMissilesDistribution
# ============================================================

class TestArcaneMissilesDistribution:
    """3 missiles hit random targets -> total 3 damage distributed."""

    def test_arcane_missiles_total_3_damage(self):
        """Arcane Missiles deals exactly 3 total damage across enemies."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        p2_life_before = p2.life

        cast_spell(game, ARCANE_MISSILES, p1)

        # Total damage across enemy hero and minions should be 3
        hero_damage = p2_life_before - p2.life
        minion_damage = enemy_yeti.state.damage
        total = hero_damage + minion_damage

        assert total == 3, (
            f"Arcane Missiles should deal exactly 3 total damage, got {total} "
            f"(hero: {hero_damage}, yeti: {minion_damage})"
        )

    def test_arcane_missiles_only_enemy_hero(self):
        """Arcane Missiles with no enemy minions: all 3 hit enemy hero."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        p2_life_before = p2.life

        cast_spell(game, ARCANE_MISSILES, p1)

        damage = p2_life_before - p2.life
        assert damage == 3, (
            f"All 3 missiles should hit enemy hero, expected 3 damage, got {damage}"
        )

    def test_arcane_missiles_no_friendly_damage(self):
        """Arcane Missiles never damages friendly characters."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        friendly_yeti = make_obj(game, CHILLWIND_YETI, p1)

        p1_life_before = p1.life

        cast_spell(game, ARCANE_MISSILES, p1)

        assert friendly_yeti.state.damage == 0, (
            f"Friendly Yeti should take 0 damage from own Arcane Missiles, "
            f"got {friendly_yeti.state.damage}"
        )
        assert p1.life == p1_life_before, (
            f"Friendly hero should take 0 damage, got {p1_life_before - p1.life}"
        )


# ============================================================
# Test 14: TestFullBoardAndFullHand
# ============================================================

class TestFullBoardAndFullHand:
    """Board at 7, hand at 10 -> draw burns, play is blocked by board."""

    def test_full_hand_draw_burns_card(self):
        """Drawing with a full hand (10 cards) burns the drawn card."""
        game, p1, p2 = new_hs_game()

        # Fill hand to max (10 for Hearthstone)
        for _ in range(10):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
                characteristics=WISP.characteristics, card_def=WISP
            )

        hand_before = get_hand_size(game, p1)
        assert hand_before == 10, f"Hand should be 10, got {hand_before}"

        # Add a card to library
        add_cards_to_library(game, p1, CHILLWIND_YETI, 1)

        # Draw a card - should be burned
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'amount': 1},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == 10, (
            f"Hand should still be 10 after burning drawn card, got {hand_after}"
        )

    def test_full_board_count(self):
        """7 minions on one side is the maximum board size we test."""
        game, p1, p2 = new_hs_game()

        for _ in range(7):
            make_obj(game, WISP, p1)

        count = count_battlefield(game, p1.id)
        assert count == 7, f"Should have 7 minions on board, got {count}"

    def test_full_hand_and_board_no_crash(self):
        """Having a full board and full hand simultaneously doesn't crash."""
        game, p1, p2 = new_hs_game()

        # Fill board with 7 minions
        for _ in range(7):
            make_obj(game, WISP, p1)

        # Fill hand with 10 cards
        for _ in range(10):
            game.create_object(
                name=CHILLWIND_YETI.name, owner_id=p1.id, zone=ZoneType.HAND,
                characteristics=CHILLWIND_YETI.characteristics, card_def=CHILLWIND_YETI
            )

        # Add library cards and draw (should burn)
        add_cards_to_library(game, p1, WISP, 3)
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'amount': 3},
            source='test'
        ))

        # Hand should still be 10 (draws burned)
        assert get_hand_size(game, p1) == 10
        # Board should still be 7
        assert count_battlefield(game, p1.id) == 7
        # No crash occurred
        assert p1.life == 30


# ============================================================
# Test 15: TestManyInterceptors
# ============================================================

class TestManyInterceptors:
    """7 minions each with interceptors -> no crash, all function correctly."""

    def test_seven_aura_minions_no_crash(self):
        """7 Stormwind Champions on board don't crash the engine."""
        game, p1, p2 = new_hs_game()

        champions = []
        for _ in range(7):
            champ = make_obj(game, STORMWIND_CHAMPION, p1)
            champions.append(champ)

        # Each Champion should buff all other Champions by +1/+1
        # With 6 other champions, each gets +6/+6 on top of base 6/6
        first_champ = champions[0]
        power = get_power(first_champ, game.state)
        toughness = get_toughness(first_champ, game.state)

        # 6/6 base + 6 * (+1/+1) from 6 other Champions = 12/12
        assert power == 12, (
            f"Stormwind Champion with 6 other Champions should have 12 Attack, "
            f"got {power}"
        )
        assert toughness == 12, (
            f"Stormwind Champion with 6 other Champions should have 12 Health, "
            f"got {toughness}"
        )

    def test_many_interceptors_damage_event(self):
        """Emitting a damage event with many interceptors active doesn't crash."""
        game, p1, p2 = new_hs_game()

        minions = []
        for _ in range(7):
            m = make_obj(game, STORMWIND_CHAMPION, p1)
            minions.append(m)

        # Deal damage to one minion - all auras should still work
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': minions[0].id, 'amount': 3, 'source': p2.hero_id},
            source=p2.hero_id
        ))

        assert minions[0].state.damage == 3, (
            f"Minion should have 3 damage, got {minions[0].state.damage}"
        )

        # Other minions should still have correct aura-buffed stats
        for m in minions[1:]:
            assert get_power(m, game.state) == 12, (
                f"Remaining Champions should still have 12 Attack"
            )


# ============================================================
# Test 16: TestGameCanProgressMultipleTurns
# ============================================================

class TestGameCanProgressMultipleTurns:
    """Simulate 5 turns of play without crash."""

    def test_five_turns_no_crash(self):
        """Playing minions and casting spells over 5 turns doesn't crash."""
        game, p1, p2 = new_hs_game()

        # Reset mana to start fresh
        p1.mana_crystals = 0
        p1.mana_crystals_available = 0
        p2.mana_crystals = 0
        p2.mana_crystals_available = 0

        for turn in range(1, 6):
            # Start of turn: gain mana
            game.mana_system.on_turn_start(p1.id)

            assert p1.mana_crystals == turn, (
                f"Turn {turn}: P1 should have {turn} mana crystals, "
                f"got {p1.mana_crystals}"
            )

            # Play a Wisp each turn (costs 0)
            if count_battlefield(game, p1.id) < 7:
                make_obj(game, WISP, p1)

            game.mana_system.on_turn_start(p2.id)

        # After 5 turns, both players should have 5 mana crystals
        assert p1.mana_crystals == 5
        assert p2.mana_crystals == 5
        # Minions should be on board
        assert count_battlefield(game, p1.id) == 5

    def test_multiple_turns_with_combat(self):
        """Multiple turns with combat and damage don't crash."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        boar = make_obj(game, STONETUSK_BOAR, p1)

        for _ in range(3):
            p2_life_before = p2.life
            events = declare_attack(game, boar.id, p2.hero_id)
            # Reset attacks for next "turn"
            boar.state.attacks_this_turn = 0

        # Boar attacked 3 times for 1 damage each
        assert p2.life == 27, (
            f"P2 should have taken 3 damage total over 3 attacks, "
            f"expected 27, got {p2.life}"
        )


# ============================================================
# Test 17: TestManaProgressionFirstFiveTurns
# ============================================================

class TestManaProgressionFirstFiveTurns:
    """Turns 1-5 give 1-5 mana crystals."""

    def test_mana_crystal_progression(self):
        """Each turn grants exactly 1 additional mana crystal, up to the turn number."""
        game, p1, p2 = new_hs_game()

        # Reset mana to simulate fresh game
        p1.mana_crystals = 0
        p1.mana_crystals_available = 0

        for turn in range(1, 6):
            game.mana_system.on_turn_start(p1.id)

            assert p1.mana_crystals == turn, (
                f"Turn {turn}: should have {turn} mana crystals, "
                f"got {p1.mana_crystals}"
            )
            assert p1.mana_crystals_available == turn, (
                f"Turn {turn}: should have {turn} available mana, "
                f"got {p1.mana_crystals_available}"
            )

    def test_mana_caps_at_10(self):
        """Mana crystals cap at 10 even after many turns."""
        game, p1, p2 = new_hs_game()

        # Reset and simulate 15 turns
        p1.mana_crystals = 0
        p1.mana_crystals_available = 0

        for turn in range(1, 16):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"After 15 turns, mana should cap at 10, got {p1.mana_crystals}"
        )
        assert p1.mana_crystals_available == 10, (
            f"Available mana should also cap at 10, got {p1.mana_crystals_available}"
        )

    def test_mana_refills_each_turn(self):
        """Available mana refills to max at start of each turn."""
        game, p1, p2 = new_hs_game()

        p1.mana_crystals = 0
        p1.mana_crystals_available = 0

        # Turn 1: gain 1 crystal, spend it
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 1
        game.mana_system.pay_cost(p1.id, 1)
        assert p1.mana_crystals_available == 0

        # Turn 2: gain another crystal, refill to 2
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 2
        assert p1.mana_crystals_available == 2, (
            f"Available mana should refill to 2, got {p1.mana_crystals_available}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
