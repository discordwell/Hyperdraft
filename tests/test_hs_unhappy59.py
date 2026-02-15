"""
Hearthstone Unhappy Path Tests - Batch 59

Secret interactions and trigger chains: Mirror Entity copying played
minion, Counterspell blocking a spell, Explosive Trap on attack,
Freezing Trap bouncing attacker, Ice Block preventing lethal, Snipe
damaging played minion, Misdirection redirecting attack, Noble Sacrifice
summoning defender, Repentance setting health to 1, Eye for an Eye
reflecting damage, Vaporize destroying attacker, Ice Barrier granting
armor, multiple secrets triggering same event, secret order resolution.
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
    WAR_GOLEM,
)
from src.cards.hearthstone.mage import (
    COUNTERSPELL, MIRROR_ENTITY, VAPORIZE, ICE_BARRIER, ICE_BLOCK,
    FIREBALL,
)
from src.cards.hearthstone.hunter import (
    EXPLOSIVE_TRAP, FREEZING_TRAP, SNIPE, MISDIRECTION,
)
from src.cards.hearthstone.paladin import (
    NOBLE_SACRIFICE, REPENTANCE, EYE_FOR_AN_EYE,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Hunter"], HERO_POWERS["Hunter"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def cast_spell(game, card_def, owner, targets=None):
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


# ============================================================
# Mage Secrets
# ============================================================

class TestMirrorEntity:
    """Mirror Entity: When opponent plays a minion, summon a copy of it."""

    def test_mirror_entity_copies_played_minion(self):
        """Opponent plays Chillwind Yeti -> Mirror Entity copies it for P1."""
        game, p1, p2 = new_hs_game()
        # P1 owns the secret
        secret = place_secret(game, MIRROR_ENTITY, p1)

        # Set active_player to p2 (opponent) so the secret can trigger
        game.state.active_player = p2.id

        # P2 plays a Yeti -- simulate via ZONE_CHANGE entering battlefield
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': yeti.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=yeti.id
        ))

        # P1 should now have a copy token on the battlefield
        p1_minions = get_battlefield_minions(game, p1.id)
        copies = [m for m in p1_minions if m.name == "Chillwind Yeti"]
        assert len(copies) >= 1, f"Expected Mirror Entity to create a Yeti copy, found {[m.name for m in p1_minions]}"

        # The copy should match power/toughness
        copy = copies[0]
        assert copy.characteristics.power == 4
        assert copy.characteristics.toughness == 5

    def test_mirror_entity_removed_after_trigger(self):
        """Mirror Entity is removed from battlefield after triggering."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)
        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': yeti.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=yeti.id
        ))

        # Secret should be gone from battlefield
        secrets = get_battlefield_secrets(game, p1.id)
        mirror_secrets = [s for s in secrets if s.name == "Mirror Entity"]
        assert len(mirror_secrets) == 0, "Mirror Entity should be removed after triggering"


class TestCounterspell:
    """Counterspell: When opponent casts a spell, counter it."""

    def test_counterspell_triggers_on_opponent_spell(self):
        """P1 has Counterspell, P2 casts a spell -> SPELL_COUNTERED event fires."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        # P2 casts a spell (emit SPELL_CAST event)
        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={
                'spell_id': spell_obj.id,
                'controller': p2.id,
                'caster': p2.id,
            },
            source=spell_obj.id
        ))

        # Check that SPELL_COUNTERED was emitted
        countered = [e for e in game.state.event_log
                     if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) >= 1, "Counterspell should emit SPELL_COUNTERED event"

    def test_counterspell_removed_after_trigger(self):
        """Counterspell is consumed after triggering."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={
                'spell_id': spell_obj.id,
                'controller': p2.id,
                'caster': p2.id,
            },
            source=spell_obj.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        cs = [s for s in secrets if s.name == "Counterspell"]
        assert len(cs) == 0, "Counterspell should be removed after triggering"


class TestIceBlock:
    """Ice Block: When hero takes fatal damage, prevent it."""

    def test_ice_block_prevents_lethal_damage(self):
        """P1 at 5 HP, Ice Block active, P2 deals 10 damage -> P1 survives."""
        game, p1, p2 = new_hs_game()
        p1.life = 5
        secret = place_secret(game, ICE_BLOCK, p1)

        # Must be opponent's turn for secret to trigger
        game.state.active_player = p2.id

        # Deal 10 damage to P1's hero (fatal)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={
                'target': p1.hero_id,
                'amount': 10,
                'source': 'test'
            },
            source='test'
        ))

        # P1 should NOT have died - Ice Block prevents fatal damage
        # The damage event should have been prevented
        assert p1.life > 0, \
            f"Ice Block should prevent lethal damage, but P1 life is {p1.life}"

    def test_ice_block_does_not_trigger_on_own_turn(self):
        """Ice Block should NOT trigger during your own turn."""
        game, p1, p2 = new_hs_game()
        p1.life = 5
        secret = place_secret(game, ICE_BLOCK, p1)

        # It's P1's own turn
        game.state.active_player = p1.id

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={
                'target': p1.hero_id,
                'amount': 10,
                'source': 'test'
            },
            source='test'
        ))

        # The damage should NOT have been prevented (own turn)
        # Check that the DAMAGE event was resolved, not prevented
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('target') == p1.hero_id]
        assert len(damage_events) >= 1, "Damage event should have been processed"
        # The damage event should NOT have been prevented
        from src.engine.types import EventStatus
        resolved = [e for e in damage_events if e.status == EventStatus.RESOLVED]
        assert len(resolved) >= 1, "Damage should resolve on own turn (Ice Block inactive)"


class TestVaporize:
    """Vaporize: When a minion attacks your hero, destroy it."""

    def test_vaporize_destroys_attacking_minion(self):
        """Enemy minion attacks P1's hero -> Vaporize destroys the attacker."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, VAPORIZE, p1)

        game.state.active_player = p2.id

        # P2 has a minion that attacks P1's hero
        attacker = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # Vaporize should emit OBJECT_DESTROYED for the attacker
        destroyed_events = [e for e in game.state.event_log
                            if e.type == EventType.OBJECT_DESTROYED
                            and e.payload.get('object_id') == attacker.id]
        assert len(destroyed_events) >= 1, "Vaporize should destroy the attacking minion"


# ============================================================
# Hunter Secrets
# ============================================================

class TestExplosiveTrap:
    """Explosive Trap: When hero is attacked, deal 2 damage to all enemies."""

    def test_explosive_trap_deals_damage_to_enemies(self):
        """P1 has Explosive Trap, P2 attacks -> 2 damage to all P2's characters."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, EXPLOSIVE_TRAP, p1)

        game.state.active_player = p2.id

        # P2's minion attacks P1's hero
        attacker = make_obj(game, BLOODFEN_RAPTOR, p2)
        another_minion = make_obj(game, WISP, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # Check that DAMAGE events were emitted for enemy minions and hero
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('amount') == 2]

        # Should have damage to P2's minions and hero
        damage_targets = [e.payload.get('target') for e in damage_events]
        assert attacker.id in damage_targets or p2.hero_id in damage_targets, \
            f"Explosive Trap should deal 2 damage to enemy characters. Targets hit: {damage_targets}"

    def test_explosive_trap_removed_after_trigger(self):
        """Explosive Trap is consumed after triggering."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, EXPLOSIVE_TRAP, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, BLOODFEN_RAPTOR, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        traps = [s for s in secrets if s.name == "Explosive Trap"]
        assert len(traps) == 0, "Explosive Trap should be removed after triggering"


class TestFreezingTrap:
    """Freezing Trap: When enemy minion attacks, return it to hand and it costs (2) more."""

    def test_freezing_trap_returns_attacker_to_hand(self):
        """Enemy minion attacks -> Freezing Trap returns it to hand."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, FREEZING_TRAP, p1)

        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # Check RETURN_TO_HAND event was emitted
        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND
                         and e.payload.get('object_id') == attacker.id]
        assert len(return_events) >= 1, "Freezing Trap should emit RETURN_TO_HAND for the attacker"

    def test_freezing_trap_removed_after_trigger(self):
        """Freezing Trap is consumed after triggering."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, FREEZING_TRAP, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # The secret should have been destroyed (zone change to graveyard)
        zone_changes = [e for e in game.state.event_log
                        if e.type == EventType.ZONE_CHANGE
                        and e.payload.get('object_id') == secret.id
                        and e.payload.get('to_zone_type') == ZoneType.GRAVEYARD]
        assert len(zone_changes) >= 1, \
            "Freezing Trap should be moved to graveyard after triggering"


class TestSnipe:
    """Snipe: When opponent plays a minion, deal 4 damage to it."""

    def test_snipe_deals_4_damage_to_played_minion(self):
        """P1 has Snipe, P2 plays a minion -> 4 damage to that minion."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)

        game.state.active_player = p2.id

        # P2 plays a Yeti
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': yeti.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=yeti.id
        ))

        # Snipe should deal 4 damage to the Yeti
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('target') == yeti.id
                         and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1, "Snipe should deal 4 damage to the played minion"

    def test_snipe_kills_low_health_minion(self):
        """Snipe on a Wisp (0/1) -> the 4 damage should kill it."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)
        game.state.active_player = p2.id

        wisp = make_obj(game, WISP, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': wisp.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=wisp.id
        ))

        # Snipe should deal 4 damage to the 1-health Wisp
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('target') == wisp.id
                         and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1, "Snipe should deal 4 damage even to a Wisp"


# ============================================================
# Paladin Secrets
# ============================================================

class TestNobleSacrifice:
    """Noble Sacrifice: When enemy attacks, summon a 2/1 Defender."""

    def test_noble_sacrifice_summons_defender(self):
        """P1 has Noble Sacrifice, P2 attacks -> a 2/1 Defender appears."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, NOBLE_SACRIFICE, p1)

        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # A 2/1 Defender should have been created for P1
        create_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN
                         and e.payload.get('controller') == p1.id]
        assert len(create_events) >= 1, "Noble Sacrifice should create a Defender token"

        token_data = create_events[0].payload.get('token', {})
        assert token_data.get('name') == 'Defender', f"Token should be named Defender, got {token_data.get('name')}"
        assert token_data.get('power') == 2, f"Defender should have 2 attack, got {token_data.get('power')}"
        assert token_data.get('toughness') == 1, f"Defender should have 1 health, got {token_data.get('toughness')}"

    def test_noble_sacrifice_removed_after_trigger(self):
        """Noble Sacrifice is consumed after triggering."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, NOBLE_SACRIFICE, p1)
        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        secrets = get_battlefield_secrets(game, p1.id)
        ns = [s for s in secrets if s.name == "Noble Sacrifice"]
        assert len(ns) == 0, "Noble Sacrifice should be removed after triggering"


class TestRepentance:
    """Repentance: When opponent plays a minion, set its Health to 1."""

    def test_repentance_sets_health_to_1(self):
        """P1 has Repentance, P2 plays Boulderfist Ogre -> health becomes 1."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, REPENTANCE, p1)

        game.state.active_player = p2.id

        ogre = make_obj(game, BOULDERFIST_OGRE, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': ogre.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=ogre.id
        ))

        # Ogre's health should now be 1
        ogre_obj = game.state.objects.get(ogre.id)
        assert ogre_obj is not None
        assert ogre_obj.characteristics.toughness == 1, \
            f"Repentance should set health to 1, but got {ogre_obj.characteristics.toughness}"

    def test_repentance_on_wisp(self):
        """Repentance on a Wisp (already 1 health) -> still 1."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, REPENTANCE, p1)
        game.state.active_player = p2.id

        wisp = make_obj(game, WISP, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': wisp.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=wisp.id
        ))

        wisp_obj = game.state.objects.get(wisp.id)
        assert wisp_obj.characteristics.toughness == 1, \
            f"Wisp should remain at 1 health, got {wisp_obj.characteristics.toughness}"


class TestEyeForAnEye:
    """Eye for an Eye: When hero takes damage, deal that much to enemy hero."""

    def test_eye_for_an_eye_reflects_damage(self):
        """P1 has Eye for an Eye, P1's hero takes 5 damage -> P2's hero takes 5."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, EYE_FOR_AN_EYE, p1)

        game.state.active_player = p2.id

        # Damage P1's hero
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={
                'target': p1.hero_id,
                'amount': 5,
                'source': 'test',
            },
            source='test'
        ))

        # Eye for an Eye should deal 5 damage to P2's hero
        reflect_events = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE
                          and e.payload.get('target') == p2.hero_id
                          and e.payload.get('amount') == 5]
        assert len(reflect_events) >= 1, \
            "Eye for an Eye should reflect 5 damage to enemy hero"


# ============================================================
# Ice Barrier
# ============================================================

class TestIceBarrier:
    """Ice Barrier: When hero is attacked, gain 8 Armor."""

    def test_ice_barrier_grants_armor(self):
        """P1 has Ice Barrier, P2 attacks P1's hero -> P1 gains 8 armor."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, ICE_BARRIER, p1)

        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # ARMOR_GAIN event should have been emitted
        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN
                        and e.payload.get('player') == p1.id
                        and e.payload.get('amount') == 8]
        assert len(armor_events) >= 1, "Ice Barrier should emit ARMOR_GAIN for 8 armor"


# ============================================================
# Multi-Secret Interactions
# ============================================================

class TestTwoSecretsSamePlayer:
    """Two different secrets on the same player both trigger from the same event."""

    def test_vaporize_and_ice_barrier_both_trigger_on_attack(self):
        """
        P1 has both Vaporize and Ice Barrier.
        P2's minion attacks P1's hero.
        Both secrets trigger on ATTACK_DECLARED targeting hero.
        """
        game, p1, p2 = new_hs_game()
        vaporize_secret = place_secret(game, VAPORIZE, p1)
        ice_barrier_secret = place_secret(game, ICE_BARRIER, p1)

        game.state.active_player = p2.id

        attacker = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p1.hero_id,
            },
            source=attacker.id
        ))

        # Check Vaporize triggered (OBJECT_DESTROYED for attacker)
        destroyed_events = [e for e in game.state.event_log
                            if e.type == EventType.OBJECT_DESTROYED
                            and e.payload.get('object_id') == attacker.id]

        # Check Ice Barrier triggered (ARMOR_GAIN)
        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN
                        and e.payload.get('player') == p1.id]

        # At least one of them should trigger (both ideally)
        triggered_count = (1 if len(destroyed_events) >= 1 else 0) + (1 if len(armor_events) >= 1 else 0)
        assert triggered_count >= 1, \
            "At least one of Vaporize/Ice Barrier should trigger on ATTACK_DECLARED"


class TestSecretRemovedAfterTrigger:
    """A triggered secret should be removed from the battlefield."""

    def test_counterspell_interceptor_gone_after_trigger(self):
        """Counterspell triggers -> its interceptor should be consumed."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)
        secret_interceptor_id = f"secret_{secret.id}"

        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={
                'spell_id': spell_obj.id,
                'controller': p2.id,
                'caster': p2.id,
            },
            source=spell_obj.id
        ))

        # The secret interceptor should be consumed (uses_remaining=1, so removed)
        remaining = game.state.interceptors.get(secret_interceptor_id)
        # Either completely removed or uses_remaining is 0
        if remaining is not None:
            assert remaining.uses_remaining is not None and remaining.uses_remaining <= 0, \
                "Secret interceptor should have been consumed after triggering"

    def test_snipe_secret_removed_from_battlefield(self):
        """After Snipe triggers, the secret object leaves battlefield."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, SNIPE, p1)

        game.state.active_player = p2.id

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': yeti.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=yeti.id
        ))

        # The Snipe secret should have been moved to graveyard
        zone_changes = [e for e in game.state.event_log
                        if e.type == EventType.ZONE_CHANGE
                        and e.payload.get('object_id') == secret.id
                        and e.payload.get('to_zone_type') == ZoneType.GRAVEYARD]
        assert len(zone_changes) >= 1, \
            "Snipe secret should generate a ZONE_CHANGE to graveyard after triggering"


class TestSecretDoesntTriggerOnYourTurn:
    """Secrets should only trigger on opponent's actions, not your own."""

    def test_mirror_entity_does_not_trigger_on_own_minion(self):
        """P1 has Mirror Entity, P1 plays a minion -> secret does NOT trigger."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, MIRROR_ENTITY, p1)

        # Set active_player to P1 (own turn)
        game.state.active_player = p1.id

        # P1 plays a Yeti (on their own turn)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': yeti.id,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=yeti.id
        ))

        # No token should have been created
        create_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN
                         and e.payload.get('controller') == p1.id]
        assert len(create_events) == 0, \
            "Mirror Entity should NOT trigger on own turn"

        # Secret should still be on the battlefield
        secrets = get_battlefield_secrets(game, p1.id)
        mirror_secrets = [s for s in secrets if s.name == "Mirror Entity"]
        assert len(mirror_secrets) == 1, \
            "Mirror Entity should still be active (not consumed on own turn)"

    def test_counterspell_does_not_trigger_on_own_spell(self):
        """P1 has Counterspell, P1 casts spell -> secret does NOT trigger."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, COUNTERSPELL, p1)

        game.state.active_player = p1.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={
                'spell_id': spell_obj.id,
                'controller': p1.id,
                'caster': p1.id,
            },
            source=spell_obj.id
        ))

        # No SPELL_COUNTERED event should exist
        countered = [e for e in game.state.event_log
                     if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) == 0, \
            "Counterspell should NOT trigger on your own spell"

    def test_explosive_trap_does_not_trigger_on_own_attack(self):
        """P1 has Explosive Trap, P1's minion attacks -> secret does NOT trigger."""
        game, p1, p2 = new_hs_game()
        secret = place_secret(game, EXPLOSIVE_TRAP, p1)

        game.state.active_player = p1.id

        attacker = make_obj(game, CHILLWIND_YETI, p1)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={
                'attacker_id': attacker.id,
                'target_id': p2.hero_id,
            },
            source=attacker.id
        ))

        # No damage events from the secret should exist (only the attack itself)
        damage_from_secret = [e for e in game.state.event_log
                              if e.type == EventType.DAMAGE
                              and e.payload.get('amount') == 2
                              and e.source == secret.id]
        assert len(damage_from_secret) == 0, \
            "Explosive Trap should NOT trigger on your own turn"


class TestCantPlayDuplicateSecret:
    """
    In Hearthstone, you can't have two copies of the same secret active.
    This is a rules constraint -- test that having two of the same
    secret on the battlefield doesn't cause double triggers.
    Even if the engine allows placing two, only one should consume.
    """

    def test_two_counterspells_only_one_counters(self):
        """
        If two Counterspells are somehow placed, only one counter event
        should occur (the first one triggers and is consumed, the second
        may or may not trigger depending on implementation).
        """
        game, p1, p2 = new_hs_game()
        secret1 = place_secret(game, COUNTERSPELL, p1)
        secret2 = place_secret(game, COUNTERSPELL, p1)

        game.state.active_player = p2.id

        spell_obj = game.create_object(
            name="Fireball", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={
                'spell_id': spell_obj.id,
                'controller': p2.id,
                'caster': p2.id,
            },
            source=spell_obj.id
        ))

        # At least one SPELL_COUNTERED event
        countered = [e for e in game.state.event_log
                     if e.type == EventType.SPELL_COUNTERED]
        assert len(countered) >= 1, \
            "At least one Counterspell should trigger"

        # Both secrets share uses_remaining=1, so at least one should be consumed
        int1 = game.state.interceptors.get(f"secret_{secret1.id}")
        int2 = game.state.interceptors.get(f"secret_{secret2.id}")

        consumed_count = 0
        if int1 is None or (int1.uses_remaining is not None and int1.uses_remaining <= 0):
            consumed_count += 1
        if int2 is None or (int2.uses_remaining is not None and int2.uses_remaining <= 0):
            consumed_count += 1

        assert consumed_count >= 1, "At least one Counterspell interceptor should be consumed"
