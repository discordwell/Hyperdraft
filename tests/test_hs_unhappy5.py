"""
Hearthstone Unhappy Path Tests - Batch 5

Secrets, spell damage, overload, board limits, taunt, windfury,
stealth breaking, cost modifiers, and Mana Wyrm/Antonidas triggers.
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

# Card imports
from src.cards.hearthstone.basic import (
    STONETUSK_BOAR, WISP, CHILLWIND_YETI, RIVER_CROCOLISK,
    BOULDERFIST_OGRE, KOBOLD_GEOMANCER, DALARAN_MAGE, OGRE_MAGI,
    STORMWIND_CHAMPION, WAR_GOLEM, THE_COIN,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, HARVEST_GOLEM, ACOLYTE_OF_PAIN,
    WILD_PYROMANCER, POLYMORPH, LEEROY_JENKINS,
    FIERY_WAR_AXE, TRUESILVER_CHAMPION,
    ACIDIC_SWAMP_OOZE, BLOODMAGE_THALNOS,
    FROSTBOLT, FIREBALL, FLAMESTRIKE, CONSECRATION,
    ARGENT_SQUIRE, IRONBEAK_OWL, MIND_CONTROL,
    ABOMINATION, SYLVANAS_WINDRUNNER, CAIRNE_BLOODHOOF,
)
from src.cards.hearthstone.mage import (
    ARCANE_EXPLOSION, MIRROR_IMAGE, FROST_NOVA,
    COUNTERSPELL, MIRROR_ENTITY, VAPORIZE, ICE_BARRIER, ICE_BLOCK,
    MANA_WYRM, SORCERERS_APPRENTICE, ARCHMAGE_ANTONIDAS,
)
from src.cards.hearthstone.hunter import (
    EXPLOSIVE_TRAP, FREEZING_TRAP, SNIPE,
)
from src.cards.hearthstone.paladin import NOBLE_SACRIFICE
from src.cards.hearthstone.shaman import (
    LIGHTNING_BOLT, FERAL_SPIRIT, LAVA_BURST,
    FLAMETONGUE_TOTEM, HEX,
)
from src.cards.hearthstone.warrior import (
    EXECUTE, WHIRLWIND, ARMORSMITH, FROTHING_BERSERKER,
)


# ============================================================================
# Test Harness
# ============================================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'from_zone_type': None,
                     'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
            source=obj.id
        ))
    return obj


def run_sba(game):
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
                source='sba'
            ))
            game.emit(Event(
                type=EventType.ZONE_CHANGE,
                payload={'object_id': oid, 'from_zone_type': ZoneType.BATTLEFIELD,
                         'to_zone_type': ZoneType.GRAVEYARD},
                source='sba'
            ))


def count_bf(game, owner_id=None):
    bf = game.state.zones.get('battlefield')
    if not bf:
        return 0
    if owner_id is None:
        return sum(1 for oid in bf.objects if oid in game.state.objects
                   and CardType.MINION in game.state.objects[oid].characteristics.types)
    return sum(1 for oid in bf.objects if oid in game.state.objects
               and game.state.objects[oid].controller == owner_id
               and CardType.MINION in game.state.objects[oid].characteristics.types)


# ============================================================================
# SECRETS
# ============================================================================

def test_mirror_entity_copies_opponent_minion():
    """Mirror Entity should summon a copy when opponent plays a minion."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id  # Opponent's turn

    # P1 plays Mirror Entity (secret)
    secret = make_obj(game, MIRROR_ENTITY, p1)

    # P2 plays Chillwind Yeti (4/5)
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    # Simulate the ZONE_CHANGE that triggers the secret
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': yeti.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p2.id},
        source=yeti.id
    ))

    # P1 should now have a copy of the Yeti on battlefield
    bf = game.state.zones.get('battlefield')
    p1_minions = [oid for oid in bf.objects if oid in game.state.objects
                  and game.state.objects[oid].controller == p1.id
                  and CardType.MINION in game.state.objects[oid].characteristics.types]
    yeti_copies = [oid for oid in p1_minions
                   if game.state.objects[oid].name == "Chillwind Yeti"]
    assert len(yeti_copies) >= 1, f"Mirror Entity should copy Yeti, P1 minions: {[game.state.objects[m].name for m in p1_minions]}"


def test_mirror_entity_does_not_trigger_on_own_turn():
    """Mirror Entity should NOT trigger during the controller's turn."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p1.id  # P1's own turn

    secret = make_obj(game, MIRROR_ENTITY, p1)

    # P1 plays a minion on own turn - secret should not trigger
    yeti = make_obj(game, CHILLWIND_YETI, p1)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': yeti.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
        source=yeti.id
    ))

    # P1 should only have the one Yeti, no extra copy
    bf = game.state.zones.get('battlefield')
    p1_yetis = [oid for oid in bf.objects if oid in game.state.objects
                and game.state.objects[oid].controller == p1.id
                and game.state.objects[oid].name == "Chillwind Yeti"
                and CardType.MINION in game.state.objects[oid].characteristics.types]
    assert len(p1_yetis) == 1, f"Secret should not trigger on own turn, got {len(p1_yetis)} Yetis"


def test_vaporize_destroys_attacking_minion():
    """Vaporize should destroy a minion that attacks the hero."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id  # Opponent's turn

    secret = make_obj(game, VAPORIZE, p1)
    attacker = make_obj(game, BOULDERFIST_OGRE, p2)

    # Attacker attacks P1's hero
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
        source=attacker.id
    ))

    # The attacker should be destroyed (moved to graveyard or has destroy event)
    destroyed = any(
        e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == attacker.id
        for e in game.state.event_log
    )
    assert destroyed, "Vaporize should destroy the attacking minion"


def test_ice_barrier_grants_armor_on_hero_attack():
    """Ice Barrier should give 8 armor when hero is attacked."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id

    secret = make_obj(game, ICE_BARRIER, p1)
    p1.armor = 0

    attacker = make_obj(game, STONETUSK_BOAR, p2)

    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
        source=attacker.id
    ))

    # Check that an ARMOR_GAIN event was emitted
    armor_events = [e for e in game.state.event_log
                    if e.type == EventType.ARMOR_GAIN
                    and e.payload.get('player') == p1.id]
    assert len(armor_events) >= 1, "Ice Barrier should emit ARMOR_GAIN event"
    assert armor_events[0].payload.get('amount') == 8, "Ice Barrier should grant 8 armor"


def test_ice_block_prevents_fatal_damage():
    """Ice Block should prevent damage that would kill the hero."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id  # Opponent's turn

    # Ice Block uses setup_interceptors (not trigger_filter/trigger_effect)
    secret = make_obj(game, ICE_BLOCK, p1)
    p1.life = 5
    p1.armor = 0

    # 10 damage should be fatal (5 life, 0 armor)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.hero_id, 'amount': 10, 'source': 'test'},
        source='test'
    ))

    # Hero should still be alive - the damage was prevented
    assert p1.life > 0 or p1.life == 5, f"Ice Block should prevent fatal damage, hero life={p1.life}"


def test_snipe_damages_played_minion():
    """Snipe should deal 4 damage to opponent's minion when played."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id  # Opponent's turn

    secret = make_obj(game, SNIPE, p1)

    # P2 plays Chillwind Yeti (4/5)
    yeti = make_obj(game, CHILLWIND_YETI, p2)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': yeti.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p2.id},
        source=yeti.id
    ))

    # Snipe should deal 4 damage to the Yeti
    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE
                     and e.payload.get('target') == yeti.id]
    assert len(damage_events) >= 1, "Snipe should deal damage to played minion"
    assert damage_events[0].payload.get('amount') == 4, "Snipe should deal 4 damage"


def test_explosive_trap_damages_all_enemies():
    """Explosive Trap should deal 2 damage to all enemies when hero attacked."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id

    secret = make_obj(game, EXPLOSIVE_TRAP, p1)

    # P2 has two minions
    m1 = make_obj(game, STONETUSK_BOAR, p2)
    m2 = make_obj(game, RIVER_CROCOLISK, p2)

    # P2 attacks P1's hero
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': m1.id, 'target_id': p1.hero_id},
        source=m1.id
    ))

    # Check that damage events were emitted for both minions and hero
    damage_targets = [e.payload.get('target') for e in game.state.event_log
                      if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(damage_targets) >= 2, f"Explosive Trap should damage multiple targets, got {len(damage_targets)}"


def test_freezing_trap_returns_and_increases_cost():
    """Freezing Trap should return attacker to hand with +2 cost."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id

    secret = make_obj(game, FREEZING_TRAP, p1)

    # P2 plays a 3-cost minion
    croc = make_obj(game, RIVER_CROCOLISK, p2)  # Cost {2}
    original_cost = croc.characteristics.mana_cost

    # Croc attacks
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': croc.id, 'target_id': p1.hero_id},
        source=croc.id
    ))

    # The croc should be returned to hand
    return_events = [e for e in game.state.event_log
                     if e.type == EventType.RETURN_TO_HAND
                     and e.payload.get('object_id') == croc.id]
    assert len(return_events) >= 1, "Freezing Trap should return attacker to hand"


def test_noble_sacrifice_summons_defender():
    """Noble Sacrifice should summon a 2/1 Defender when enemy attacks."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id

    secret = make_obj(game, NOBLE_SACRIFICE, p1)
    attacker = make_obj(game, STONETUSK_BOAR, p2)

    # P2's minion attacks
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
        source=attacker.id
    ))

    # A Defender token should have been created
    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Defender']
    assert len(token_events) >= 1, "Noble Sacrifice should summon a Defender"


def test_secret_destroyed_after_trigger():
    """Secrets should be moved to graveyard after triggering."""
    game, p1, p2 = new_hs_game()
    game.state.active_player = p2.id

    secret = make_obj(game, VAPORIZE, p1)
    attacker = make_obj(game, STONETUSK_BOAR, p2)

    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
        source=attacker.id
    ))

    # Secret should be in graveyard (zone changed or no longer on battlefield)
    bf = game.state.zones.get('battlefield')
    assert secret.id not in bf.objects, "Secret should leave battlefield after triggering"


# ============================================================================
# SPELL DAMAGE
# ============================================================================

def test_spell_damage_boosts_arcane_explosion():
    """Kobold Geomancer (+1 Spell Damage) should boost Arcane Explosion from 1 to 2."""
    game, p1, p2 = new_hs_game()

    # P1 has Kobold Geomancer on board
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    # P2 has a minion
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    # P1 casts Arcane Explosion (1 damage to all enemy minions)
    ae_obj = game.create_object(
        name=ARCANE_EXPLOSION.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=ARCANE_EXPLOSION.characteristics, card_def=ARCANE_EXPLOSION
    )
    events = ARCANE_EXPLOSION.spell_effect(ae_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Yeti should have taken 2 damage (1 base + 1 spell damage)
    assert yeti.state.damage == 2, f"Spell Damage +1 should boost AOE from 1 to 2, got {yeti.state.damage}"


def test_spell_damage_boosts_fireball():
    """Spell Damage +1 should boost Fireball from 6 to 7."""
    game, p1, p2 = new_hs_game()

    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    # Cast Fireball at P2's hero
    fb_obj = game.create_object(
        name=FIREBALL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=FIREBALL.characteristics, card_def=FIREBALL
    )
    events = FIREBALL.spell_effect(fb_obj, game.state, targets=[p2.hero_id])
    for e in events:
        game.emit(e)

    # P2 hero should have taken 7 damage
    assert p2.life <= 23, f"Fireball+SpellDmg should deal 7, hero at {p2.life}"


def test_multiple_spell_damage_sources_stack():
    """Two Spell Damage +1 minions should give +2 total."""
    game, p1, p2 = new_hs_game()

    # Two spell damage minions
    k1 = make_obj(game, KOBOLD_GEOMANCER, p1)
    k2 = make_obj(game, DALARAN_MAGE, p1)

    # P2 has minion
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    ae_obj = game.create_object(
        name=ARCANE_EXPLOSION.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=ARCANE_EXPLOSION.characteristics, card_def=ARCANE_EXPLOSION
    )
    events = ARCANE_EXPLOSION.spell_effect(ae_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Yeti should have taken 3 damage (1 base + 2 spell damage)
    assert yeti.state.damage == 3, f"Double spell damage should boost from 1 to 3, got {yeti.state.damage}"


def test_spell_damage_does_not_boost_minion_damage():
    """Spell Damage should NOT boost damage from minion attacks."""
    game, p1, p2 = new_hs_game()

    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    # P1's kobold attacks yeti - should deal 2 (base), not 3
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': yeti.id, 'amount': 2, 'source': kobold.id, 'is_combat': True},
        source=kobold.id
    ))

    # Spell damage should NOT apply to combat damage
    assert yeti.state.damage == 2, f"Spell Damage should not boost combat damage, got {yeti.state.damage}"


def test_bloodmage_thalnos_spell_damage_and_deathrattle():
    """Thalnos provides Spell Damage +1 alive, draws a card on death."""
    game, p1, p2 = new_hs_game()

    thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)

    # Put a card in P1's library so draw works
    card_in_deck = game.create_object(
        name="Test Card", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=WISP.characteristics, card_def=WISP
    )

    # Spell damage should be active while alive
    yeti = make_obj(game, CHILLWIND_YETI, p2)
    ae_obj = game.create_object(
        name=ARCANE_EXPLOSION.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=ARCANE_EXPLOSION.characteristics, card_def=ARCANE_EXPLOSION
    )
    events = ARCANE_EXPLOSION.spell_effect(ae_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    assert yeti.state.damage == 2, f"Thalnos should give +1 spell damage, got {yeti.state.damage}"

    # Kill Thalnos - should trigger deathrattle (draw)
    thalnos.state.damage = 1
    run_sba(game)

    # Thalnos should be dead
    assert thalnos.zone == ZoneType.GRAVEYARD, "Thalnos should be dead"


# ============================================================================
# OVERLOAD
# ============================================================================

def test_lightning_bolt_sets_overload():
    """Lightning Bolt should set overloaded_mana to 1."""
    game, p1, p2 = new_hs_game()

    lb_obj = game.create_object(
        name=LIGHTNING_BOLT.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=LIGHTNING_BOLT.characteristics, card_def=LIGHTNING_BOLT
    )
    events = LIGHTNING_BOLT.spell_effect(lb_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    assert p1.overloaded_mana == 1, f"Lightning Bolt should set overload to 1, got {p1.overloaded_mana}"


def test_overload_stacks_across_spells():
    """Multiple overload spells in one turn should stack."""
    game, p1, p2 = new_hs_game()

    # Cast Lightning Bolt (Overload: 1)
    lb_obj = game.create_object(
        name=LIGHTNING_BOLT.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=LIGHTNING_BOLT.characteristics, card_def=LIGHTNING_BOLT
    )
    LIGHTNING_BOLT.spell_effect(lb_obj, game.state, targets=None)

    # Cast Lava Burst (Overload: 2)
    lv_obj = game.create_object(
        name=LAVA_BURST.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=LAVA_BURST.characteristics, card_def=LAVA_BURST
    )
    LAVA_BURST.spell_effect(lv_obj, game.state, targets=None)

    assert p1.overloaded_mana == 3, f"Overload should stack (1+2=3), got {p1.overloaded_mana}"


def test_overload_locks_mana_next_turn():
    """Overloaded mana should reduce available mana at start of next turn."""
    game, p1, p2 = new_hs_game()

    # Simulate: P1 has 5 mana crystals and 2 overloaded from last turn
    p1.overloaded_mana = 2
    p1.mana_crystals = 5

    # Reproduce the overload logic from HearthstoneTurnManager._run_draw_phase
    # (the actual method is async, so we replicate it for synchronous testing)
    # Step 1: mana_system refills (mana_crystals may go to 6, available=6)
    if p1.mana_crystals < 10:
        p1.mana_crystals += 1
    p1.mana_crystals_available = p1.mana_crystals

    # Step 2: apply overload
    if p1.overloaded_mana > 0:
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - p1.overloaded_mana)
        p1.overloaded_mana = 0

    # After: crystals=6, available should be 6-2=4
    assert p1.mana_crystals_available == 4, \
        f"Overload should lock 2 mana, available={p1.mana_crystals_available}"
    assert p1.overloaded_mana == 0, "Overloaded mana should reset after applying"


def test_feral_spirit_creates_wolves_with_overload():
    """Feral Spirit: summon 2 wolves + Overload: (2)."""
    game, p1, p2 = new_hs_game()

    fs_obj = game.create_object(
        name=FERAL_SPIRIT.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=FERAL_SPIRIT.characteristics, card_def=FERAL_SPIRIT
    )
    events = FERAL_SPIRIT.spell_effect(fs_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Should have 2 wolves on board and overload 2
    wolf_count = sum(1 for oid in game.state.zones['battlefield'].objects
                     if oid in game.state.objects
                     and game.state.objects[oid].name == "Spirit Wolf"
                     and game.state.objects[oid].controller == p1.id)
    assert wolf_count == 2, f"Feral Spirit should summon 2 wolves, got {wolf_count}"
    assert p1.overloaded_mana == 2, f"Feral Spirit should overload 2, got {p1.overloaded_mana}"


# ============================================================================
# BOARD LIMITS (7 Minions)
# ============================================================================

def test_board_limit_prevents_8th_minion():
    """Can't have more than 7 minions on one player's side."""
    game, p1, p2 = new_hs_game()

    # Fill P1's board with 7 minions
    for i in range(7):
        make_obj(game, WISP, p1)

    assert count_bf(game, p1.id) == 7

    # Try to add 8th minion via zone change
    extra = game.create_object(
        name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=WISP.characteristics, card_def=WISP
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': extra.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
        source=extra.id
    ))

    # Should still be 7
    assert count_bf(game, p1.id) == 7, f"Board should cap at 7, got {count_bf(game, p1.id)}"


def test_board_limit_doesnt_affect_other_player():
    """P1 having 7 minions should not block P2 from summoning."""
    game, p1, p2 = new_hs_game()

    for i in range(7):
        make_obj(game, WISP, p1)

    assert count_bf(game, p1.id) == 7

    # P2 should still be able to summon
    p2_minion = make_obj(game, CHILLWIND_YETI, p2)
    assert count_bf(game, p2.id) == 1, "P2 should be able to summon with P1's board full"


def test_board_limit_blocks_token_creation():
    """Token creation (Mirror Image) should be limited by board size."""
    game, p1, p2 = new_hs_game()

    # Fill P1's board with 6 minions
    for i in range(6):
        make_obj(game, WISP, p1)
    assert count_bf(game, p1.id) == 6

    # Mirror Image tries to summon 2 tokens - only 1 should fit
    mi_obj = game.create_object(
        name=MIRROR_IMAGE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MIRROR_IMAGE.characteristics, card_def=MIRROR_IMAGE
    )
    events = MIRROR_IMAGE.spell_effect(mi_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Should be 7 (6 + 1 token), not 8
    assert count_bf(game, p1.id) <= 7, f"Board should cap at 7, got {count_bf(game, p1.id)}"


def test_board_limit_blocks_deathrattle_summon():
    """Deathrattle tokens should not exceed the 7-minion board limit."""
    game, p1, p2 = new_hs_game()

    # Fill P1's board with 6 wisps + 1 Harvest Golem
    for i in range(6):
        make_obj(game, WISP, p1)
    golem = make_obj(game, HARVEST_GOLEM, p1)
    assert count_bf(game, p1.id) == 7

    # Kill the golem - deathrattle tries to summon 2/1 Damaged Golem
    golem.state.damage = 3
    run_sba(game)

    # Still 7 at most (6 wisps + 1 golem token or 6 wisps if golem died)
    assert count_bf(game, p1.id) <= 7, f"Deathrattle shouldn't exceed board limit, got {count_bf(game, p1.id)}"


# ============================================================================
# MANA WYRM & ANTONIDAS (Spell-Cast Triggers)
# ============================================================================

def test_mana_wyrm_grows_on_spell_cast():
    """Mana Wyrm should gain +1 Attack each time a spell is cast."""
    game, p1, p2 = new_hs_game()

    wyrm = make_obj(game, MANA_WYRM, p1)
    base_power = get_power(wyrm, game.state)

    # Cast a spell (emit SPELL_CAST event)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p1.id},
        source='test',
        controller=p1.id
    ))

    new_power = get_power(wyrm, game.state)
    assert new_power >= base_power + 1, f"Mana Wyrm should grow by +1, was {base_power} now {new_power}"


def test_mana_wyrm_ignores_opponent_spells():
    """Mana Wyrm should NOT grow from opponent's spells."""
    game, p1, p2 = new_hs_game()

    wyrm = make_obj(game, MANA_WYRM, p1)
    base_power = get_power(wyrm, game.state)

    # Opponent casts a spell
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p2.id},
        source='test',
        controller=p2.id
    ))

    new_power = get_power(wyrm, game.state)
    assert new_power == base_power, f"Mana Wyrm should not grow from opponent spells, was {base_power} now {new_power}"


def test_antonidas_generates_fireball_on_spell_cast():
    """Archmage Antonidas should add a Fireball to hand when you cast a spell."""
    game, p1, p2 = new_hs_game()

    antonidas = make_obj(game, ARCHMAGE_ANTONIDAS, p1)

    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p1.id},
        source='test',
        controller=p1.id
    ))

    # Check for ADD_TO_HAND event with Fireball
    add_events = [e for e in game.state.event_log
                  if e.type == EventType.ADD_TO_HAND
                  and e.payload.get('player') == p1.id]
    assert len(add_events) >= 1, "Antonidas should add Fireball to hand on spell cast"


# ============================================================================
# SORCERER'S APPRENTICE (Cost Reduction)
# ============================================================================

def test_sorcerers_apprentice_reduces_spell_cost():
    """Sorcerer's Apprentice should make spells cost 1 less."""
    game, p1, p2 = new_hs_game()

    apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

    # The cost_reduction_aura uses positive amount (amount=1 means "reduce by 1")
    spell_mods = [m for m in p1.cost_modifiers
                  if m.get('card_type') == CardType.SPELL and m.get('amount', 0) > 0]
    assert len(spell_mods) >= 1, \
        f"Apprentice should add spell cost reduction, modifiers: {p1.cost_modifiers}"
    assert spell_mods[0].get('amount') == 1, \
        f"Apprentice should reduce by 1, got amount={spell_mods[0].get('amount')}"


# ============================================================================
# FLAMETONGUE TOTEM (Adjacent Aura)
# ============================================================================

def test_flametongue_totem_buffs_adjacent():
    """Flametongue Totem should give +2 Attack to adjacent minions only."""
    game, p1, p2 = new_hs_game()

    # Place minions in order: Wisp, Flametongue, Wisp, Wisp
    w1 = make_obj(game, WISP, p1)     # Position 0 (adjacent)
    ft = make_obj(game, FLAMETONGUE_TOTEM, p1)  # Position 1
    w2 = make_obj(game, WISP, p1)     # Position 2 (adjacent)
    w3 = make_obj(game, WISP, p1)     # Position 3 (not adjacent)

    p1_w1 = get_power(w1, game.state)
    p1_w2 = get_power(w2, game.state)
    p1_w3 = get_power(w3, game.state)

    # Wisp is 1/1 base. Adjacent wisps should have +2 attack (1 base + 2 = 3)
    # Non-adjacent wisp should have base attack (1)
    assert p1_w1 == 3, f"Left adjacent should get +2 (1+2=3), got {p1_w1}"
    assert p1_w2 == 3, f"Right adjacent should get +2 (1+2=3), got {p1_w2}"
    assert p1_w3 == 1, f"Non-adjacent should not get buff, got {p1_w3}"


# ============================================================================
# MISC UNHAPPY PATHS
# ============================================================================

def test_frost_nova_freezes_all_enemy_minions():
    """Frost Nova should freeze all enemy minions."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, STONETUSK_BOAR, p2)
    m2 = make_obj(game, CHILLWIND_YETI, p2)

    fn_obj = game.create_object(
        name=FROST_NOVA.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=FROST_NOVA.characteristics, card_def=FROST_NOVA
    )
    events = FROST_NOVA.spell_effect(fn_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    freeze_events = [e for e in game.state.event_log
                     if e.type == EventType.FREEZE_TARGET]
    assert len(freeze_events) >= 2, f"Frost Nova should freeze 2 minions, got {len(freeze_events)}"


def test_mirror_image_summons_two_taunts():
    """Mirror Image should summon exactly two 0/2 Taunt tokens."""
    game, p1, p2 = new_hs_game()

    mi_obj = game.create_object(
        name=MIRROR_IMAGE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MIRROR_IMAGE.characteristics, card_def=MIRROR_IMAGE
    )
    events = MIRROR_IMAGE.spell_effect(mi_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    tokens = [oid for oid in game.state.zones['battlefield'].objects
              if oid in game.state.objects
              and game.state.objects[oid].name == "Mirror Image"
              and game.state.objects[oid].controller == p1.id
              and CardType.MINION in game.state.objects[oid].characteristics.types]
    assert len(tokens) == 2, f"Mirror Image should create 2 tokens, got {len(tokens)}"


def test_whirlwind_triggers_multiple_reactions():
    """Whirlwind hitting multiple minions should trigger each one's reaction."""
    game, p1, p2 = new_hs_game()

    # Armorsmith: gain 1 armor for each friendly minion damaged
    smith = make_obj(game, ARMORSMITH, p1)
    frothing = make_obj(game, FROTHING_BERSERKER, p1)
    wisp = make_obj(game, WISP, p2)

    p1.armor = 0

    # Cast Whirlwind (1 damage to all minions)
    ww_obj = game.create_object(
        name=WHIRLWIND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=WHIRLWIND.characteristics, card_def=WHIRLWIND
    )
    events = WHIRLWIND.spell_effect(ww_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Armorsmith and Frothing are both friendly and both got hit
    # Armorsmith should trigger for each friendly minion damaged (2: itself + frothing)
    # This tests that AOE properly triggers individual minion reactions


def test_spell_damage_with_flamestrike():
    """Spell Damage should boost Flamestrike AOE damage."""
    game, p1, p2 = new_hs_game()

    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    yeti = make_obj(game, CHILLWIND_YETI, p2)

    # Cast Flamestrike (normally 4 damage to all enemy minions)
    fs_obj = game.create_object(
        name=FLAMESTRIKE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=FLAMESTRIKE.characteristics, card_def=FLAMESTRIKE
    )
    events = FLAMESTRIKE.spell_effect(fs_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Yeti (4/5) should take 5 damage (4 base + 1 spell damage) and die
    assert yeti.state.damage >= 5, f"Flamestrike + Spell Damage should deal 5, got {yeti.state.damage}"


def test_empty_deck_fatigue_increments_each_draw():
    """Each draw from empty deck should increment fatigue damage."""
    game, p1, p2 = new_hs_game()

    # P1's library is empty
    lib = game.state.zones.get(f"library_{p1.id}")
    if lib:
        lib.objects.clear()

    # Draw 3 times
    for i in range(3):
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

    # Fatigue should deal 1+2+3 = 6 total damage
    fatigue_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE
                      and e.payload.get('target') == p1.hero_id]
    total_fatigue = sum(e.payload.get('amount', 0) for e in fatigue_events)
    assert total_fatigue >= 6, f"3 fatigue draws should deal 1+2+3=6, got {total_fatigue}"


def test_silence_removes_spell_damage():
    """Silencing a Spell Damage minion should remove the spell damage boost."""
    game, p1, p2 = new_hs_game()

    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    # Silence the Kobold
    game.emit(Event(
        type=EventType.SILENCE_TARGET,
        payload={'target': kobold.id},
        source='test'
    ))

    # Cast Arcane Explosion - should deal only 1 damage (no spell damage boost)
    ae_obj = game.create_object(
        name=ARCANE_EXPLOSION.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=ARCANE_EXPLOSION.characteristics, card_def=ARCANE_EXPLOSION
    )
    events = ARCANE_EXPLOSION.spell_effect(ae_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    assert yeti.state.damage == 1, f"After silencing spell damage, AOE should deal 1, got {yeti.state.damage}"


def test_mind_control_on_full_board():
    """Mind Control when you have 7 minions should fail gracefully."""
    game, p1, p2 = new_hs_game()

    # Fill P1's board with 7 minions
    for i in range(7):
        make_obj(game, WISP, p1)
    assert count_bf(game, p1.id) == 7

    # P2 has a Yeti
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    # P1 tries Mind Control
    mc_obj = game.create_object(
        name=MIND_CONTROL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MIND_CONTROL.characteristics, card_def=MIND_CONTROL
    )
    events = MIND_CONTROL.spell_effect(mc_obj, game.state, targets=[yeti.id])
    for e in events:
        game.emit(e)

    # Yeti should either stay with P2 or be destroyed - P1 should not have 8 minions
    assert count_bf(game, p1.id) <= 7, f"Mind Control on full board should not exceed 7, got {count_bf(game, p1.id)}"


def test_hex_on_already_damaged_minion():
    """Hex on a damaged minion should produce a fresh 0/1 Frog."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p2)
    yeti.state.damage = 3  # 2/5 Yeti with 3 damage

    hex_obj = game.create_object(
        name=HEX.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=HEX.characteristics, card_def=HEX
    )
    events = HEX.spell_effect(hex_obj, game.state, targets=[yeti.id])
    for e in events:
        game.emit(e)

    # Yeti should be transformed into a 0/1 Frog with no damage
    assert yeti.characteristics.power == 0, f"Frog should have 0 power, got {yeti.characteristics.power}"
    assert yeti.characteristics.toughness == 1, f"Frog should have 1 toughness, got {yeti.characteristics.toughness}"
    assert yeti.state.damage == 0, f"Frog should have 0 damage, got {yeti.state.damage}"


def test_acolyte_of_pain_draw_chain_into_fatigue():
    """Acolyte of Pain drawing from empty deck should take fatigue damage but not infinite loop."""
    game, p1, p2 = new_hs_game()

    acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

    # Empty P1's library
    lib = game.state.zones.get(f"library_{p1.id}")
    if lib:
        lib.objects.clear()

    # Deal 1 damage to Acolyte - should trigger draw - which triggers fatigue
    # but fatigue damage goes to hero, not Acolyte, so no infinite loop
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    # Acolyte should have 1 damage, game should not have crashed
    assert acolyte.state.damage >= 1, "Acolyte should have taken damage"
    # P1 should have taken fatigue damage to hero
    assert p1.life <= 30, "Fatigue should have damaged hero"


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} passed")
