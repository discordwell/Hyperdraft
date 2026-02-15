"""
Hearthstone Unhappy Path Tests - Batch 12

Hunter class deep-dive (almost entirely untested), Warrior advanced cards
(Shield Slam, Brawl, Grommash, Commanding Shout, Warsong Commander),
and Druid Choose One mechanics (Wrath, Keeper, Nourish, Starfall, Cenarius,
Power of the Wild, Ancient of Lore).
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
    WISP, CHILLWIND_YETI, RIVER_CROCOLISK, BOULDERFIST_OGRE,
    BLOODFEN_RAPTOR,
)
from src.cards.hearthstone.classic import (
    HARVEST_GOLEM, FIERY_WAR_AXE, KNIFE_JUGGLER,
)
from src.cards.hearthstone.hunter import (
    HUNTERS_MARK, TRACKING, KILL_COMMAND, ANIMAL_COMPANION,
    HOUNDMASTER, MULTI_SHOT, TUNDRA_RHINO, STARVING_BUZZARD,
    SAVANNAH_HIGHMANE, BESTIAL_WRATH, DEADLY_SHOT, UNLEASH_THE_HOUNDS,
    SCAVENGING_HYENA, KING_KRUSH, FLARE, EXPLOSIVE_SHOT, ARCANE_SHOT,
)
from src.cards.hearthstone.warrior import (
    EXECUTE, WHIRLWIND, SHIELD_BLOCK, HEROIC_STRIKE,
    CLEAVE, ARMORSMITH, FROTHING_BERSERKER, SHIELD_SLAM,
    BRAWL, GROMMASH_HELLSCREAM, WARSONG_COMMANDER, COMMANDING_SHOUT,
    MORTAL_STRIKE, SLAM, INNER_RAGE, GOREHOWL,
)
from src.cards.hearthstone.druid import (
    WRATH, KEEPER_OF_THE_GROVE, NOURISH, POWER_OF_THE_WILD,
    STARFALL, CENARIUS, ANCIENT_OF_LORE, MARK_OF_NATURE,
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


def play_from_hand(game, card_def, owner):
    """Create in hand then emit ZONE_CHANGE to trigger battlecry."""
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
    """Helper to cast a spell properly."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets)
    for e in events:
        game.emit(e)
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


# ============================================================================
# HUNTER: Basic Spells
# ============================================================================

def test_hunters_mark_sets_health_to_1():
    """Hunter's Mark reduces a minion's Health to 1."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
    cast_spell(game, HUNTERS_MARK, p1, targets=[enemy.id])

    assert enemy.characteristics.toughness == 1, \
        f"Hunter's Mark should set toughness to 1, got {enemy.characteristics.toughness}"
    assert enemy.state.damage == 0, \
        f"Hunter's Mark should clear damage, got {enemy.state.damage}"


def test_tracking_draws_a_card():
    """Tracking draws a card from library."""
    game, p1, p2 = new_hs_game()

    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
    cast_spell(game, TRACKING, p1)

    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "Tracking should draw a card"


def test_arcane_shot_deals_2_to_target():
    """Arcane Shot deals 2 damage to a targeted character."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    cast_spell(game, ARCANE_SHOT, p1, targets=[enemy.id])

    assert enemy.state.damage >= 2, \
        f"Arcane Shot should deal 2 damage, got {enemy.state.damage}"


# ============================================================================
# HUNTER: Beast Synergies
# ============================================================================

def test_houndmaster_buffs_a_beast():
    """Houndmaster battlecry gives a friendly Beast +2/+2 and Taunt."""
    game, p1, p2 = new_hs_game()

    # Bloodfen Raptor is a 3/2 Beast
    raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
    hm = play_from_hand(game, HOUNDMASTER, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2
                 and e.payload.get('toughness_mod') == 2]
    assert len(pt_events) >= 1, "Houndmaster should buff a Beast +2/+2"

    kw_events = [e for e in game.state.event_log
                 if e.type == EventType.KEYWORD_GRANT
                 and e.payload.get('keyword') == 'taunt']
    assert len(kw_events) >= 1, "Houndmaster should give Beast Taunt"


def test_houndmaster_no_beast_no_buff():
    """Houndmaster battlecry does nothing without a friendly Beast."""
    game, p1, p2 = new_hs_game()

    # Wisp is NOT a Beast
    wisp = make_obj(game, WISP, p1)
    hm = play_from_hand(game, HOUNDMASTER, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2]
    assert len(pt_events) == 0, "Houndmaster should NOT buff non-Beast minions"


def test_scavenging_hyena_gains_on_beast_death():
    """Scavenging Hyena gains +2/+1 when a friendly Beast dies."""
    game, p1, p2 = new_hs_game()

    hyena = make_obj(game, SCAVENGING_HYENA, p1)  # 2/2 Beast
    raptor = make_obj(game, BLOODFEN_RAPTOR, p1)   # 3/2 Beast

    # Kill the raptor
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': raptor.id},
        source='test'
    ))

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('object_id') == hyena.id
                 and e.payload.get('power_mod') == 2
                 and e.payload.get('toughness_mod') == 1]
    assert len(pt_events) >= 1, "Hyena should gain +2/+1 when friendly Beast dies"


def test_scavenging_hyena_ignores_non_beast():
    """Scavenging Hyena does NOT gain stats when a non-Beast dies."""
    game, p1, p2 = new_hs_game()

    hyena = make_obj(game, SCAVENGING_HYENA, p1)
    wisp = make_obj(game, WISP, p1)  # Not a Beast

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wisp.id},
        source='test'
    ))

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('object_id') == hyena.id]
    assert len(pt_events) == 0, "Hyena should NOT trigger on non-Beast death"


def test_starving_buzzard_draws_on_beast_summon():
    """Starving Buzzard draws a card when a friendly Beast is summoned."""
    game, p1, p2 = new_hs_game()

    buzzard = make_obj(game, STARVING_BUZZARD, p1)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    # Summon a Beast (zone change to battlefield)
    raptor = play_from_hand(game, BLOODFEN_RAPTOR, p1)

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW
                   and e.payload.get('player') == p1.id]
    assert len(draw_events) >= 1, "Buzzard should draw when friendly Beast is summoned"


def test_tundra_rhino_grants_charge_to_beasts():
    """Tundra Rhino gives Charge to friendly Beasts when they enter."""
    game, p1, p2 = new_hs_game()

    rhino = make_obj(game, TUNDRA_RHINO, p1)

    raptor = play_from_hand(game, BLOODFEN_RAPTOR, p1)

    # Raptor should have charge and no summoning sickness
    has_charge = any(
        a.get('keyword') == 'charge'
        for a in (raptor.characteristics.abilities or [])
    )
    assert has_charge, "Beast summoned with Tundra Rhino should have Charge"
    assert not raptor.state.summoning_sickness, \
        "Beast with Charge should not have summoning sickness"


# ============================================================================
# HUNTER: Damage & Removal Spells
# ============================================================================

def test_multi_shot_hits_two_enemies():
    """Multi-Shot deals 3 damage to 2 random enemy minions."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, CHILLWIND_YETI, p2)
    e2 = make_obj(game, BOULDERFIST_OGRE, p2)
    e3 = make_obj(game, RIVER_CROCOLISK, p2)

    cast_spell(game, MULTI_SHOT, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 3]
    assert len(dmg_events) >= 2, \
        f"Multi-Shot should hit 2 targets for 3 damage each, got {len(dmg_events)}"


def test_multi_shot_one_enemy_hits_one():
    """Multi-Shot with only 1 enemy minion still deals 3 to it."""
    game, p1, p2 = new_hs_game()

    lone = make_obj(game, CHILLWIND_YETI, p2)
    cast_spell(game, MULTI_SHOT, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 3]
    assert len(dmg_events) >= 1, "Multi-Shot with 1 enemy should still deal 3"


def test_deadly_shot_destroys_random_enemy():
    """Deadly Shot destroys a random enemy minion."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, CHILLWIND_YETI, p2)
    e2 = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, DEADLY_SHOT, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'deadly_shot']
    assert len(destroy_events) >= 1, "Deadly Shot should destroy an enemy minion"


def test_unleash_the_hounds_summons_per_enemy():
    """Unleash the Hounds summons 1 Hound per enemy minion."""
    game, p1, p2 = new_hs_game()

    make_obj(game, WISP, p2)
    make_obj(game, WISP, p2)
    make_obj(game, WISP, p2)

    cast_spell(game, UNLEASH_THE_HOUNDS, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Hound']
    assert len(token_events) == 3, \
        f"Should summon 3 Hounds for 3 enemies, got {len(token_events)}"


def test_unleash_the_hounds_zero_enemies():
    """Unleash the Hounds with no enemy minions summons nothing."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, UNLEASH_THE_HOUNDS, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN]
    assert len(token_events) == 0, "No enemy minions = no Hounds"


def test_savannah_highmane_deathrattle():
    """Savannah Highmane DR summons two 2/2 Hyenas."""
    game, p1, p2 = new_hs_game()

    highmane = play_from_hand(game, SAVANNAH_HIGHMANE, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': highmane.id},
        source='test'
    ))

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Hyena']
    assert len(token_events) >= 2, \
        f"Highmane should summon 2 Hyenas on death, got {len(token_events)}"


def test_bestial_wrath_buffs_beast():
    """Bestial Wrath gives a friendly Beast +2 Attack and Immune this turn."""
    game, p1, p2 = new_hs_game()

    raptor = make_obj(game, BLOODFEN_RAPTOR, p1)  # 3/2 Beast
    cast_spell(game, BESTIAL_WRATH, p1, targets=[raptor.id])

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2]
    assert len(pt_events) >= 1, "Bestial Wrath should give +2 Attack"

    has_immune = any(
        a.get('keyword') == 'immune'
        for a in (raptor.characteristics.abilities or [])
    )
    assert has_immune, "Bestial Wrath should grant Immune"


def test_bestial_wrath_immune_removed_at_eot():
    """Bestial Wrath Immune is removed at end of turn."""
    game, p1, p2 = new_hs_game()

    raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
    cast_spell(game, BESTIAL_WRATH, p1, targets=[raptor.id])

    # Verify Immune is on
    has_immune = any(
        a.get('keyword') == 'immune'
        for a in (raptor.characteristics.abilities or [])
    )
    assert has_immune, "Should have Immune before end of turn"

    game.emit(Event(
        type=EventType.TURN_END,
        payload={'player': p1.id},
        source='test'
    ))

    has_immune_after = any(
        a.get('keyword') == 'immune'
        for a in (raptor.characteristics.abilities or [])
    )
    assert not has_immune_after, "Immune should be removed at end of turn"


def test_flare_removes_stealth_and_draws():
    """Flare removes Stealth from enemy minions and draws a card."""
    game, p1, p2 = new_hs_game()

    stealthy = make_obj(game, CHILLWIND_YETI, p2)
    stealthy.state.stealth = True
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, FLARE, p1)

    assert not stealthy.state.stealth, "Flare should remove Stealth"

    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "Flare should draw a card"


def test_explosive_shot_hits_primary_and_adjacent():
    """Explosive Shot deals 5 to primary target and 2 to adjacent."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, BOULDERFIST_OGRE, p2)
    e2 = make_obj(game, BOULDERFIST_OGRE, p2)
    e3 = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, EXPLOSIVE_SHOT, p1, targets=[e2.id])

    # Primary should take 5
    dmg5 = [e for e in game.state.event_log
             if e.type == EventType.DAMAGE and e.payload.get('amount') == 5]
    assert len(dmg5) >= 1, "Primary target should take 5 damage"

    # Adjacent should take 2 each
    dmg2 = [e for e in game.state.event_log
             if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg2) >= 1, "Adjacent targets should take 2 damage"


def test_king_krush_has_charge():
    """King Krush is an 8/8 Beast with Charge."""
    game, p1, p2 = new_hs_game()

    krush = make_obj(game, KING_KRUSH, p1)
    assert krush.characteristics.power == 8, f"King Krush should be 8 atk, got {krush.characteristics.power}"
    assert krush.characteristics.toughness == 8, f"King Krush should be 8 hp, got {krush.characteristics.toughness}"
    assert has_ability(krush, 'charge', game.state), "King Krush should have Charge"
    assert 'Beast' in krush.characteristics.subtypes, "King Krush should be a Beast"


# ============================================================================
# WARRIOR: Advanced Spells
# ============================================================================

def test_shield_slam_deals_damage_equal_to_armor():
    """Shield Slam deals damage equal to your current Armor."""
    game, p1, p2 = new_hs_game()

    p1.armor = 7
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, SHIELD_SLAM, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 7]
    assert len(dmg_events) >= 1, "Shield Slam should deal damage equal to armor (7)"


def test_shield_slam_zero_armor_no_damage():
    """Shield Slam with 0 armor does nothing."""
    game, p1, p2 = new_hs_game()

    p1.armor = 0
    enemy = make_obj(game, CHILLWIND_YETI, p2)

    cast_spell(game, SHIELD_SLAM, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE]
    assert len(dmg_events) == 0, "Shield Slam with 0 armor should deal no damage"


def test_brawl_leaves_one_minion():
    """Brawl destroys all minions except one random survivor."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, WISP, p1)
    m2 = make_obj(game, WISP, p1)
    m3 = make_obj(game, WISP, p2)
    m4 = make_obj(game, WISP, p2)
    m5 = make_obj(game, WISP, p2)

    cast_spell(game, BRAWL, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'brawl']
    assert len(destroy_events) == 4, \
        f"Brawl with 5 minions should destroy 4, got {len(destroy_events)}"


def test_grommash_enrage_plus_6():
    """Grommash Hellscream has Enrage: +6 Attack."""
    game, p1, p2 = new_hs_game()

    grom = make_obj(game, GROMMASH_HELLSCREAM, p1)
    base_power = get_power(grom, game.state)

    # Damage Grommash to trigger enrage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': grom.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    enraged_power = get_power(grom, game.state)
    assert enraged_power >= base_power + 6, \
        f"Grommash enraged should be +6 attack (base {base_power} + 6 = {base_power + 6}), got {enraged_power}"


def test_grommash_has_charge():
    """Grommash Hellscream has Charge."""
    game, p1, p2 = new_hs_game()

    grom = make_obj(game, GROMMASH_HELLSCREAM, p1)
    assert has_ability(grom, 'charge', game.state), "Grommash should have Charge"


def test_warsong_commander_grants_charge_to_small_minion():
    """Warsong Commander gives Charge to minions with 3 or less Attack."""
    game, p1, p2 = new_hs_game()

    warsong = make_obj(game, WARSONG_COMMANDER, p1)

    # Play a minion with ≤3 attack from hand
    wisp = play_from_hand(game, WISP, p1)  # 1/1

    has_charge = any(
        a.get('keyword') == 'charge'
        for a in (wisp.characteristics.abilities or [])
    )
    assert has_charge, "Wisp (1 atk) should get Charge from Warsong Commander"
    assert not wisp.state.summoning_sickness, \
        "Minion with Charge should not have summoning sickness"


def test_commanding_shout_prevents_lethal():
    """Commanding Shout prevents friendly minions from going below 1 HP."""
    game, p1, p2 = new_hs_game()

    wisp = make_obj(game, WISP, p1)  # 1/1
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, COMMANDING_SHOUT, p1)

    # Deal 5 damage to the 1/1 wisp — should be capped to leave at 1 HP
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': wisp.id, 'amount': 5, 'source': 'test'},
        source='test'
    ))

    hp = get_toughness(wisp, game.state) - wisp.state.damage
    assert hp >= 1, \
        f"Commanding Shout should prevent lethal, HP is {hp}"


def test_mortal_strike_boosted_at_low_hp():
    """Mortal Strike deals 6 instead of 4 when hero is at 12 or less HP."""
    game, p1, p2 = new_hs_game()

    p1.life = 10
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, MORTAL_STRIKE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 6]
    assert len(dmg_events) >= 1, \
        "Mortal Strike at ≤12 HP should deal 6 damage"


def test_mortal_strike_normal_at_high_hp():
    """Mortal Strike deals 4 when hero is above 12 HP."""
    game, p1, p2 = new_hs_game()

    p1.life = 30
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, MORTAL_STRIKE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 4]
    assert len(dmg_events) >= 1, \
        "Mortal Strike at >12 HP should deal 4 damage"


def test_slam_draws_if_target_survives():
    """Slam deals 2 damage and draws a card if the minion survives."""
    game, p1, p2 = new_hs_game()

    # Yeti is 4/5, will survive 2 damage
    yeti = make_obj(game, CHILLWIND_YETI, p1)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, SLAM, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg_events) >= 1, "Slam should deal 2 damage"

    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "Slam should draw if minion survives"


def test_inner_rage_damage_plus_attack():
    """Inner Rage deals 1 damage and gives +2 Attack."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)

    cast_spell(game, INNER_RAGE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 1]
    assert len(dmg_events) >= 1, "Inner Rage should deal 1 damage"

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2]
    assert len(pt_events) >= 1, "Inner Rage should give +2 Attack"


# ============================================================================
# DRUID: Choose One Mechanics
# ============================================================================

def test_wrath_3_damage_mode():
    """Wrath Choose One: deals 3 damage when enemy has ≤3 HP remaining."""
    game, p1, p2 = new_hs_game()

    # River Crocolisk is 2/3 — exactly 3 health so Wrath should pick 3 damage mode
    enemy = make_obj(game, RIVER_CROCOLISK, p2)

    cast_spell(game, WRATH, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 3]
    assert len(dmg_events) >= 1, "Wrath should deal 3 to low-HP enemy"


def test_wrath_1_damage_and_draw_mode():
    """Wrath Choose One: deals 1 and draws when enemy has >3 HP."""
    game, p1, p2 = new_hs_game()

    # Boulderfist Ogre is 6/7 — AI should pick 1 damage + draw mode
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, WRATH, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 1]
    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]

    assert len(dmg_events) >= 1, "Wrath should deal 1 damage in draw mode"
    assert len(draw_events) >= 1, "Wrath should draw in draw mode"


def test_keeper_of_the_grove_damage_mode():
    """Keeper of the Grove Choose One: 2 damage when no high-value silence target."""
    game, p1, p2 = new_hs_game()

    # Enemy with no interceptors — KotG should pick damage mode
    enemy = make_obj(game, CHILLWIND_YETI, p2)

    keeper = play_from_hand(game, KEEPER_OF_THE_GROVE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg_events) >= 1, "Keeper should deal 2 damage to enemy without interceptors"


def test_nourish_ramp_mode():
    """Nourish Choose One: gain 2 Mana Crystals when below 8."""
    game, p1, p2 = new_hs_game()

    p1.mana_crystals = 5
    cast_spell(game, NOURISH, p1)

    assert p1.mana_crystals == 7, \
        f"Nourish ramp should set crystals to 7, got {p1.mana_crystals}"


def test_nourish_draw_mode():
    """Nourish Choose One: draw 3 cards when at 8+ mana crystals."""
    game, p1, p2 = new_hs_game()

    p1.mana_crystals = 10
    for _ in range(5):
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, NOURISH, p1)

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW
                   and e.payload.get('count') == 3]
    assert len(draw_events) >= 1, "Nourish at 10 mana should draw 3"


def test_starfall_aoe_mode():
    """Starfall Choose One: AOE 2 to all enemy minions when ≥3 enemies."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, CHILLWIND_YETI, p2)
    e2 = make_obj(game, CHILLWIND_YETI, p2)
    e3 = make_obj(game, CHILLWIND_YETI, p2)

    cast_spell(game, STARFALL, p1)

    dmg2 = [e for e in game.state.event_log
             if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg2) >= 3, \
        f"Starfall AOE should hit all 3 enemies for 2, got {len(dmg2)} hits"


def test_starfall_single_target_mode():
    """Starfall Choose One: 5 damage to one when <3 enemies."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, STARFALL, p1)

    dmg5 = [e for e in game.state.event_log
             if e.type == EventType.DAMAGE and e.payload.get('amount') == 5]
    assert len(dmg5) >= 1, "Starfall single should deal 5 to one enemy"


def test_cenarius_buff_mode():
    """Cenarius Choose One: +2/+2 to all friendly minions when ≥3 on board."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, WISP, p1)
    m2 = make_obj(game, WISP, p1)
    m3 = make_obj(game, WISP, p1)

    cenarius = play_from_hand(game, CENARIUS, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2
                 and e.payload.get('toughness_mod') == 2]
    assert len(pt_events) >= 3, \
        f"Cenarius buff mode should buff 3+ minions, got {len(pt_events)}"


def test_cenarius_summon_mode():
    """Cenarius Choose One: summon two 2/4 Treants with Taunt when <3 minions."""
    game, p1, p2 = new_hs_game()

    cenarius = play_from_hand(game, CENARIUS, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Treant']
    assert len(token_events) >= 2, \
        f"Cenarius summon mode should create 2 Treants, got {len(token_events)}"


def test_power_of_the_wild_buff_mode():
    """Power of the Wild Choose One: +1/+1 to minions when ≥2 friendly."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, WISP, p1)
    m2 = make_obj(game, WISP, p1)

    cast_spell(game, POWER_OF_THE_WILD, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 1
                 and e.payload.get('toughness_mod') == 1]
    assert len(pt_events) >= 2, \
        f"PotW buff mode should buff 2 minions, got {len(pt_events)}"


def test_power_of_the_wild_panther_mode():
    """Power of the Wild Choose One: summon 3/2 Panther when <2 friendly."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, POWER_OF_THE_WILD, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Panther']
    assert len(token_events) >= 1, "PotW should summon Panther with no minions"


def test_ancient_of_lore_draw_mode():
    """Ancient of Lore Choose One: draw 2 cards when hero has ≥15 HP."""
    game, p1, p2 = new_hs_game()

    p1.life = 30
    for _ in range(5):
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    aol = play_from_hand(game, ANCIENT_OF_LORE, p1)

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW
                   and e.payload.get('count') == 2]
    assert len(draw_events) >= 1, "AoL at 30 HP should draw 2"


def test_ancient_of_lore_heal_mode():
    """Ancient of Lore Choose One: heal 5 when hero has <15 HP."""
    game, p1, p2 = new_hs_game()

    p1.life = 10
    life_before = p1.life

    aol = play_from_hand(game, ANCIENT_OF_LORE, p1)

    assert p1.life > life_before, \
        f"AoL at low HP should heal, was {life_before}, now {p1.life}"


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
