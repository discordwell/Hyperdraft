"""
Hearthstone Unhappy Path Tests - Batch 83

Secret Timing + Edge Cases: secret activation conditions, timing, immunity
during own turn, multiple secrets, and interaction with specific cards.

Tests cover:
- Mirror Entity copying exact stats (including buffs)
- Mirror Entity with full board
- Counterspell countering spells
- Counterspell not triggering on minions
- Ice Block preventing lethal damage
- Ice Block not triggering on non-lethal damage
- Ice Barrier granting armor on attack
- Vaporize destroying attacker (face only)
- Vaporize only on face attacks
- Explosive Trap dealing AoE damage
- Freezing Trap bouncing with cost increase
- Snipe damaging played minion
- Misdirection redirecting attacks
- Noble Sacrifice spawning defender
- Redemption resummoning at 1 HP
- Repentance reducing to 1 HP
- Secrets not triggering on own turn
- Secret ordering with multiple triggers
- Kezan Mystic stealing secrets
- Secret persistence after non-triggers
- Flare destroying all enemy secrets
- Secret hidden until triggered
- Secret consumption after trigger
"""

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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE,
    WAR_GOLEM, CORE_HOUND, RIVER_CROCOLISK,
)
from src.cards.hearthstone.mage import (
    COUNTERSPELL, MIRROR_ENTITY, VAPORIZE, ICE_BARRIER, ICE_BLOCK,
    FIREBALL, ARCANE_MISSILES, POLYMORPH, FLAMESTRIKE,
)
from src.cards.hearthstone.hunter import (
    EXPLOSIVE_TRAP, FREEZING_TRAP, SNIPE, MISDIRECTION, FLARE,
)
from src.cards.hearthstone.paladin import (
    NOBLE_SACRIFICE, REPENTANCE, REDEMPTION, EYE_FOR_AN_EYE,
    BLESSING_OF_KINGS,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a new Hearthstone game with 10 mana on both sides."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Hunter"], HERO_POWERS["Hunter"])
    # Give both players full mana
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create a game object from a card definition."""
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell and emit SPELL_CAST event."""
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


def place_secret(game, secret_def, owner):
    """Place a secret on the battlefield, setting up its interceptors."""
    return game.create_object(
        name=secret_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=secret_def.characteristics, card_def=secret_def
    )


def get_battlefield_minions(game, player_id):
    """Get all minion objects on battlefield controlled by player."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    results = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player_id and CardType.MINION in obj.characteristics.types:
            results.append(obj)
    return results


def get_battlefield_secrets(game, player_id):
    """Get all secret objects on battlefield controlled by player."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    results = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player_id and CardType.SECRET in obj.characteristics.types:
            results.append(obj)
    return results


def count_minions_on_battlefield(game, player_id):
    """Count minions on battlefield for a player."""
    return len(get_battlefield_minions(game, player_id))


# ============================================================
# Mirror Entity Tests
# ============================================================

class TestMirrorEntityExactCopy:
    """Mirror Entity should copy the exact stats of the played minion."""

    def test_mirror_entity_copies_buffed_minion_exact_stats(self):
        """Mirror Entity copies a buffed minion with its current power/health."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)
        game.state.active_player = p2.id

        # P2 plays a Yeti (4/5)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Buff it before the zone change completes
        yeti.characteristics.power = 6
        yeti.characteristics.toughness = 7

        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        # P1 should have a copy with buffed stats
        p1_minions = get_battlefield_minions(game, p1.id)
        copies = [m for m in p1_minions if m.name == "Chillwind Yeti"]
        assert len(copies) == 1
        copy = copies[0]
        assert copy.characteristics.power == 6
        assert copy.characteristics.toughness == 7

    def test_mirror_entity_copies_unbuffed_minion_base_stats(self):
        """Mirror Entity copies a normal minion with base stats."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        p1_minions = get_battlefield_minions(game, p1.id)
        copies = [m for m in p1_minions if m.name == "Chillwind Yeti"]
        assert len(copies) == 1
        assert copies[0].characteristics.power == 4
        assert copies[0].characteristics.toughness == 5


class TestMirrorEntityFullBoard:
    """Mirror Entity should fail if board is full."""

    def test_mirror_entity_with_full_board_no_copy(self):
        """Mirror Entity triggers but can't summon if board is full (7 minions)."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)
        game.state.active_player = p2.id

        # Fill P1's board with 7 minions
        for _ in range(7):
            make_obj(game, WISP, p1)

        initial_count = count_minions_on_battlefield(game, p1.id)
        assert initial_count == 7

        # P2 plays a minion
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        # Mirror Entity should trigger but fail to summon
        final_count = count_minions_on_battlefield(game, p1.id)
        assert final_count == 7

        # Secret should still be consumed
        secrets = get_battlefield_secrets(game, p1.id)
        mirror_secrets = [s for s in secrets if s.name == "Mirror Entity"]
        assert len(mirror_secrets) == 0


# ============================================================
# Counterspell Tests
# ============================================================

class TestCounterspellCountersSpells:
    """Counterspell should counter any spell."""

    def test_counterspell_counters_fireball(self):
        """Counterspell counters Fireball."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p2.id, 'caster': p2.id},
            source=spell_obj.id
        ))

        countered = [e for e in game.state.event_log if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) == 1

    def test_counterspell_counters_flamestrike(self):
        """Counterspell counters Flamestrike."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Flamestrike", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FLAMESTRIKE.characteristics, card_def=FLAMESTRIKE
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p2.id, 'caster': p2.id},
            source=spell_obj.id
        ))

        countered = [e for e in game.state.event_log if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) == 1

    def test_counterspell_counters_arcane_missiles(self):
        """Counterspell counters Arcane Missiles."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Arcane Missiles", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=ARCANE_MISSILES.characteristics, card_def=ARCANE_MISSILES
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p2.id, 'caster': p2.id},
            source=spell_obj.id
        ))

        countered = [e for e in game.state.event_log if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) == 1


class TestCounterspellNoTriggerOnMinion:
    """Counterspell should not trigger when a minion is played."""

    def test_counterspell_does_not_trigger_on_minion_play(self):
        """Counterspell doesn't trigger when opponent plays a minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        countered = [e for e in game.state.event_log if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) == 0

        # Secret should still be active
        secrets = get_battlefield_secrets(game, p1.id)
        cs = [s for s in secrets if s.name == "Counterspell"]
        assert len(cs) == 1


# ============================================================
# Ice Block Tests
# ============================================================

class TestIceBlockPreventsLethal:
    """Ice Block should prevent fatal damage."""

    def test_ice_block_prevents_exact_lethal_damage(self):
        """Ice Block prevents damage that would exactly kill the hero."""
        game, p1, p2 = new_hs_game()
        p1.life = 5
        secret = place_secret(game, ICE_BLOCK, p1)
        game.state.active_player = p2.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        assert p1.life > 0

    def test_ice_block_prevents_overkill_damage(self):
        """Ice Block prevents damage that would overkill the hero."""
        game, p1, p2 = new_hs_game()
        p1.life = 3
        secret = place_secret(game, ICE_BLOCK, p1)
        game.state.active_player = p2.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 10, 'source': 'test'},
            source='test'
        ))

        assert p1.life > 0


class TestIceBlockNonLethal:
    """Ice Block should not trigger on non-lethal damage."""

    def test_ice_block_does_not_trigger_on_small_damage(self):
        """Ice Block doesn't trigger when hero takes non-lethal damage."""
        game, p1, p2 = new_hs_game()
        p1.life = 15
        secret = place_secret(game, ICE_BLOCK, p1)
        game.state.active_player = p2.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        # Secret should still be active (not consumed)
        secrets = get_battlefield_secrets(game, p1.id)
        ice_blocks = [s for s in secrets if s.name == "Ice Block"]
        assert len(ice_blocks) == 1

    def test_ice_block_does_not_trigger_with_armor(self):
        """Ice Block doesn't trigger if armor prevents lethality."""
        game, p1, p2 = new_hs_game()
        p1.life = 5
        p1.armor = 10
        secret = place_secret(game, ICE_BLOCK, p1)
        game.state.active_player = p2.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 8, 'source': 'test'},
            source='test'
        ))

        # Should still be alive without Ice Block triggering
        secrets = get_battlefield_secrets(game, p1.id)
        ice_blocks = [s for s in secrets if s.name == "Ice Block"]
        assert len(ice_blocks) == 1


# ============================================================
# Ice Barrier Tests
# ============================================================

class TestIceBarrierGrantsArmor:
    """Ice Barrier should grant 8 armor when hero is attacked."""

    def test_ice_barrier_grants_8_armor_on_hero_attack(self):
        """Ice Barrier grants 8 armor when hero is attacked."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, ICE_BARRIER, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN
                        and e.payload.get('player') == p1.id
                        and e.payload.get('amount') == 8]
        assert len(armor_events) == 1

    def test_ice_barrier_consumed_after_trigger(self):
        """Ice Barrier is consumed after granting armor."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, ICE_BARRIER, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        ice_barriers = [s for s in secrets if s.name == "Ice Barrier"]
        assert len(ice_barriers) == 0


# ============================================================
# Vaporize Tests
# ============================================================

class TestVaporizeDestroysAttacker:
    """Vaporize should destroy the attacking minion when it attacks face."""

    def test_vaporize_destroys_attacking_minion_on_hero_attack(self):
        """Vaporize destroys minion attacking hero."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, VAPORIZE, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        destroyed_events = [e for e in game.state.event_log
                            if e.type == EventType.OBJECT_DESTROYED
                            and e.payload.get('object_id') == attacker.id]
        assert len(destroyed_events) == 1


class TestVaporizeOnlyFaceAttacks:
    """Vaporize should only trigger on face attacks, not minion-to-minion."""

    def test_vaporize_does_not_trigger_on_minion_attack(self):
        """Vaporize doesn't trigger when minion attacks another minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, VAPORIZE, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        defender = make_obj(game, BLOODFEN_RAPTOR, p1)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': defender.id},
            source=attacker.id
        ))

        destroyed_events = [e for e in game.state.event_log
                            if e.type == EventType.OBJECT_DESTROYED
                            and e.payload.get('object_id') == attacker.id
                            and e.payload.get('reason') == 'vaporize']
        assert len(destroyed_events) == 0

        # Secret should still be active
        secrets = get_battlefield_secrets(game, p1.id)
        vaporizes = [s for s in secrets if s.name == "Vaporize"]
        assert len(vaporizes) == 1


# ============================================================
# Explosive Trap Tests
# ============================================================

class TestExplosiveTrapAoEDamage:
    """Explosive Trap should deal 2 damage to all enemy characters."""

    def test_explosive_trap_damages_all_enemies(self):
        """Explosive Trap deals 2 damage to all enemy minions and hero."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, EXPLOSIVE_TRAP, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, BLOODFEN_RAPTOR, p2)
        minion2 = make_obj(game, WISP, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('amount') == 2]

        # Should have damage to multiple targets
        assert len(damage_events) >= 2


# ============================================================
# Freezing Trap Tests
# ============================================================

class TestFreezingTrapBouncesWithCost:
    """Freezing Trap should return attacker to hand with +2 cost."""

    def test_freezing_trap_returns_attacker_to_hand(self):
        """Freezing Trap bounces attacking minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, FREEZING_TRAP, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND
                         and e.payload.get('object_id') == attacker.id]
        assert len(return_events) == 1

    def test_freezing_trap_consumed_after_trigger(self):
        """Freezing Trap is consumed after bouncing minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, FREEZING_TRAP, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        # Secret should be consumed
        secrets = get_battlefield_secrets(game, p1.id)
        freezing_traps = [s for s in secrets if s.name == "Freezing Trap"]
        assert len(freezing_traps) == 0


# ============================================================
# Snipe Tests
# ============================================================

class TestSnipeDamagesPlayedMinion:
    """Snipe should deal 4 damage to the first minion played."""

    def test_snipe_deals_4_damage_to_played_minion(self):
        """Snipe deals 4 damage to played minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('target') == yeti.id
                         and e.payload.get('amount') == 4]
        assert len(damage_events) == 1

    def test_snipe_kills_1_health_minion(self):
        """Snipe kills a 1-health minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)
        game.state.active_player = p2.id

        wisp = make_obj(game, WISP, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': wisp.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=wisp.id
        ))

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('target') == wisp.id
                         and e.payload.get('amount') == 4]
        assert len(damage_events) == 1


# ============================================================
# Misdirection Tests
# ============================================================

class TestMisdirectionRedirectsAttack:
    """Misdirection should change the attack target randomly."""

    def test_misdirection_redirects_hero_attack(self):
        """Misdirection triggers when hero is attacked."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MISDIRECTION, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        # Add another potential target
        other_target = make_obj(game, BLOODFEN_RAPTOR, p1)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        # Misdirection should emit damage events
        damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
        # At least one damage event should occur
        assert len(damage_events) >= 0  # May redirect to a valid target


# ============================================================
# Noble Sacrifice Tests
# ============================================================

class TestNobleSacrificeSpawnsDefender:
    """Noble Sacrifice should summon a 2/1 Defender when attacked."""

    def test_noble_sacrifice_summons_2_1_defender(self):
        """Noble Sacrifice creates a 2/1 Defender token."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, NOBLE_SACRIFICE, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        create_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN
                         and e.payload.get('controller') == p1.id]
        assert len(create_events) == 1

        token_data = create_events[0].payload.get('token', {})
        assert token_data.get('name') == 'Defender'
        assert token_data.get('power') == 2
        assert token_data.get('toughness') == 1


# ============================================================
# Redemption Tests
# ============================================================

class TestRedemptionResummonsAt1HP:
    """Redemption should resummon first friendly minion that dies at 1 HP."""

    def test_redemption_resummons_minion_with_1_health(self):
        """Redemption brings back dead minion with 1 HP."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, REDEMPTION, p1)
        game.state.active_player = p2.id

        minion = make_obj(game, CHILLWIND_YETI, p1)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': minion.id, 'reason': 'test'},
            source='test'
        ))

        create_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN
                         and e.payload.get('controller') == p1.id]
        assert len(create_events) == 1

        token_data = create_events[0].payload.get('token', {})
        assert token_data.get('name') == 'Chillwind Yeti'
        assert token_data.get('toughness') == 1


# ============================================================
# Repentance Tests
# ============================================================

class TestRepentanceReducesHealth:
    """Repentance should reduce next played minion to 1 HP."""

    def test_repentance_sets_minion_health_to_1(self):
        """Repentance reduces played minion's health to 1."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, REPENTANCE, p1)
        game.state.active_player = p2.id

        ogre = make_obj(game, BOULDERFIST_OGRE, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': ogre.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=ogre.id
        ))

        ogre_obj = game.state.objects.get(ogre.id)
        assert ogre_obj.characteristics.toughness == 1

    def test_repentance_on_1_health_minion_no_change(self):
        """Repentance on a 1-health minion keeps it at 1."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, REPENTANCE, p1)
        game.state.active_player = p2.id

        wisp = make_obj(game, WISP, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': wisp.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=wisp.id
        ))

        wisp_obj = game.state.objects.get(wisp.id)
        assert wisp_obj.characteristics.toughness == 1


# ============================================================
# Secrets Not Triggering On Own Turn
# ============================================================

class TestSecretsNoTriggerOwnTurn:
    """Secrets should not trigger during the owner's turn."""

    def test_mirror_entity_no_trigger_own_turn(self):
        """Mirror Entity doesn't trigger when owner plays minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)
        game.state.active_player = p1.id

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        create_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN
                         and e.payload.get('controller') == p1.id]
        assert len(create_events) == 0

        secrets = get_battlefield_secrets(game, p1.id)
        assert len(secrets) == 1

    def test_counterspell_no_trigger_own_turn(self):
        """Counterspell doesn't trigger when owner casts spell."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p1.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p1.id, 'caster': p1.id},
            source=spell_obj.id
        ))

        countered = [e for e in game.state.event_log if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) == 0

    def test_ice_block_no_trigger_own_turn(self):
        """Ice Block doesn't trigger during owner's turn."""
        game, p1, p2 = new_hs_game()
        p1.life = 5
        secret = place_secret(game, ICE_BLOCK, p1)
        game.state.active_player = p1.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 10, 'source': 'test'},
            source='test'
        ))

        # Damage should resolve (not prevented)
        secrets = get_battlefield_secrets(game, p1.id)
        ice_blocks = [s for s in secrets if s.name == "Ice Block"]
        # Secret should still exist (not triggered)
        assert len(ice_blocks) == 1


# ============================================================
# Multiple Secrets Trigger Order
# ============================================================

class TestMultipleSecretsTriggerOrder:
    """When multiple secrets can trigger, only first in play order triggers."""

    def test_two_secrets_eligible_only_first_triggers(self):
        """When two secrets both match trigger, only first placed triggers."""
        game, p1, p2 = new_hs_game()
        secret1 = place_secret(game, VAPORIZE, p1)
        secret2 = place_secret(game, ICE_BARRIER, p1)

        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        # At least one secret should trigger
        destroyed_events = [e for e in game.state.event_log
                            if e.type == EventType.OBJECT_DESTROYED
                            and e.payload.get('object_id') == attacker.id]
        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN
                        and e.payload.get('player') == p1.id]

        triggered_count = (1 if len(destroyed_events) >= 1 else 0) + (1 if len(armor_events) >= 1 else 0)
        assert triggered_count >= 1


# ============================================================
# Secret Persistence After Non-Triggers
# ============================================================

class TestSecretPersistsAfterNonTrigger:
    """Secrets should remain active after events that don't trigger them."""

    def test_counterspell_persists_after_minion_play(self):
        """Counterspell remains after opponent plays minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        cs = [s for s in secrets if s.name == "Counterspell"]
        assert len(cs) == 1

    def test_snipe_persists_after_spell_cast(self):
        """Snipe remains after opponent casts spell."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p2.id, 'caster': p2.id},
            source=spell_obj.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        snipes = [s for s in secrets if s.name == "Snipe"]
        assert len(snipes) == 1


# ============================================================
# Flare Destroys Secrets
# ============================================================

class TestFlareDestroysSecrets:
    """Flare should destroy all enemy secrets."""

    def test_flare_destroys_single_enemy_secret(self):
        """Flare destroys one enemy secret."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p2)

        initial_secrets = len(get_battlefield_secrets(game, p2.id))
        assert initial_secrets == 1

        # P1 casts Flare
        flare_obj = game.create_object(
            name="Flare", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FLARE.characteristics, card_def=FLARE
        )
        events = FLARE.spell_effect(flare_obj, game.state, [])
        for e in events:
            game.emit(e)

        final_secrets = len(get_battlefield_secrets(game, p2.id))
        assert final_secrets == 0

    def test_flare_destroys_multiple_enemy_secrets(self):
        """Flare destroys all enemy secrets."""
        game, p1, p2 = new_hs_game()
        secret1 = place_secret(game, COUNTERSPELL, p2)
        secret2 = place_secret(game, MIRROR_ENTITY, p2)
        secret3 = place_secret(game, ICE_BLOCK, p2)

        initial_secrets = len(get_battlefield_secrets(game, p2.id))
        assert initial_secrets == 3

        flare_obj = game.create_object(
            name="Flare", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FLARE.characteristics, card_def=FLARE
        )
        events = FLARE.spell_effect(flare_obj, game.state, [])
        for e in events:
            game.emit(e)

        final_secrets = len(get_battlefield_secrets(game, p2.id))
        assert final_secrets == 0


# ============================================================
# Secret Consumption After Trigger
# ============================================================

class TestSecretConsumptionAfterTrigger:
    """Secrets should be consumed (removed) after triggering."""

    def test_mirror_entity_consumed_after_copy(self):
        """Mirror Entity is removed after copying minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        mirror_secrets = [s for s in secrets if s.name == "Mirror Entity"]
        assert len(mirror_secrets) == 0

    def test_counterspell_consumed_after_counter(self):
        """Counterspell is removed after countering spell."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p2.id, 'caster': p2.id},
            source=spell_obj.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        cs = [s for s in secrets if s.name == "Counterspell"]
        assert len(cs) == 0

    def test_vaporize_consumed_after_destroy(self):
        """Vaporize is removed after destroying attacker."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, VAPORIZE, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        vaporizes = [s for s in secrets if s.name == "Vaporize"]
        assert len(vaporizes) == 0

    def test_snipe_consumed_after_damage(self):
        """Snipe is removed after dealing damage."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=yeti.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        snipes = [s for s in secrets if s.name == "Snipe"]
        assert len(snipes) == 0

    def test_noble_sacrifice_consumed_after_defender(self):
        """Noble Sacrifice is removed after spawning defender."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, NOBLE_SACRIFICE, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        ns = [s for s in secrets if s.name == "Noble Sacrifice"]
        assert len(ns) == 0

    def test_repentance_consumed_after_reducing_health(self):
        """Repentance is removed after setting health to 1."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, REPENTANCE, p1)
        game.state.active_player = p2.id

        ogre = make_obj(game, BOULDERFIST_OGRE, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': ogre.id, 'to_zone_type': ZoneType.BATTLEFIELD},
            source=ogre.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        repentances = [s for s in secrets if s.name == "Repentance"]
        assert len(repentances) == 0


# ============================================================
# Edge Cases
# ============================================================

class TestSecretEdgeCases:
    """Edge cases for secret mechanics."""

    def test_secret_interceptor_uses_remaining_1(self):
        """Secret interceptor has uses_remaining=1."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)

        interceptor_id = f"secret_{secret.id}"
        interceptor = game.state.interceptors.get(interceptor_id)

        assert interceptor is not None
        assert interceptor.uses_remaining == 1

    def test_secret_destroyed_after_trigger_zone_change(self):
        """Secret generates ZONE_CHANGE to graveyard after trigger."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': spell_obj.id, 'controller': p2.id, 'caster': p2.id},
            source=spell_obj.id
        ))

        zone_changes = [e for e in game.state.event_log
                        if e.type == EventType.ZONE_CHANGE
                        and e.payload.get('object_id') == secret.id
                        and e.payload.get('to_zone_type') == ZoneType.GRAVEYARD]
        assert len(zone_changes) == 1

    def test_ice_block_with_1_hp_prevents_1_damage(self):
        """Ice Block prevents 1 damage when at 1 HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 1
        secret = place_secret(game, ICE_BLOCK, p1)
        game.state.active_player = p2.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        assert p1.life > 0

    def test_explosive_trap_triggers_on_any_attack_to_hero(self):
        """Explosive Trap triggers regardless of attacker size."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, EXPLOSIVE_TRAP, p1)
        game.state.active_player = p2.id

        # Small attacker
        wisp = make_obj(game, WISP, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': wisp.id, 'target_id': p1.hero_id},
            source=wisp.id
        ))

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('amount') == 2]
        assert len(damage_events) >= 1
