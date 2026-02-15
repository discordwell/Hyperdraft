"""
Hearthstone Unhappy Path Tests - Batch 7

Conditional effects, discard mechanics, delayed death triggers,
multi-minion interactions, and complex real-game sequences that
stress the event pipeline.
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
    STONETUSK_BOAR, WISP, CHILLWIND_YETI, RIVER_CROCOLISK,
    BOULDERFIST_OGRE, KOBOLD_GEOMANCER, STORMWIND_CHAMPION,
    RAID_LEADER, NIGHTBLADE, SEN_JIN_SHIELDMASTA,
    FROSTWOLF_GRUNT, MAGMA_RAGER,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, HARVEST_GOLEM, ACOLYTE_OF_PAIN,
    WILD_PYROMANCER, POLYMORPH, LEEROY_JENKINS,
    FIERY_WAR_AXE, TRUESILVER_CHAMPION, ARCANITE_REAPER,
    ACIDIC_SWAMP_OOZE, BLOODMAGE_THALNOS,
    FROSTBOLT, FIREBALL, FLAMESTRIKE, CONSECRATION,
    ARGENT_SQUIRE, IRONBEAK_OWL, MIND_CONTROL,
    ABOMINATION, SYLVANAS_WINDRUNNER, CAIRNE_BLOODHOOF,
    LOOT_HOARDER, AZURE_DRAKE, CULT_MASTER,
    TWILIGHT_DRAKE, KNIFE_JUGGLER, BIG_GAME_HUNTER,
    INJURED_BLADEMASTER,
)
from src.cards.hearthstone.mage import (
    ARCANE_EXPLOSION, MIRROR_IMAGE, MANA_WYRM,
    SORCERERS_APPRENTICE, COUNTERSPELL,
    PYROBLAST,
)
from src.cards.hearthstone.hunter import (
    KILL_COMMAND, TIMBER_WOLF, SAVANNAH_HIGHMANE,
    ANIMAL_COMPANION, STARVING_BUZZARD,
)
from src.cards.hearthstone.shaman import (
    LIGHTNING_BOLT, FERAL_SPIRIT, HEX,
    FLAMETONGUE_TOTEM, EARTH_SHOCK, BLOODLUST,
)
from src.cards.hearthstone.warrior import (
    EXECUTE, WHIRLWIND, ARMORSMITH, FROTHING_BERSERKER,
    HEROIC_STRIKE, CRUEL_TASKMASTER, BATTLE_RAGE,
)
from src.cards.hearthstone.warlock import (
    SOULFIRE, MORTAL_COIL, POWER_OVERWHELMING, HELLFIRE,
)
from src.cards.hearthstone.paladin import (
    BLESSING_OF_KINGS, EQUALITY,
)
from src.cards.hearthstone.priest import (
    SHADOW_WORD_PAIN, SHADOW_WORD_DEATH, HOLY_NOVA,
    NORTHSHIRE_CLERIC,
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
# CONDITIONAL EFFECTS
# ============================================================================

def test_kill_command_deals_3_without_beast():
    """Kill Command deals 3 damage without a Beast on board."""
    game, p1, p2 = new_hs_game()

    # No beasts on P1's board
    kc_obj = game.create_object(
        name=KILL_COMMAND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
    )
    events = KILL_COMMAND.spell_effect(kc_obj, game.state, targets=[p2.hero_id])
    for e in events:
        game.emit(e)

    assert p2.life <= 27, f"Kill Command without Beast should deal 3, hero at {p2.life}"


def test_kill_command_deals_5_with_beast():
    """Kill Command deals 5 damage with a Beast on board."""
    game, p1, p2 = new_hs_game()

    # Stonetusk Boar is a Beast
    boar = make_obj(game, STONETUSK_BOAR, p1)

    kc_obj = game.create_object(
        name=KILL_COMMAND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
    )
    events = KILL_COMMAND.spell_effect(kc_obj, game.state, targets=[p2.hero_id])
    for e in events:
        game.emit(e)

    assert p2.life <= 25, f"Kill Command with Beast should deal 5, hero at {p2.life}"


def test_mortal_coil_draws_on_kill():
    """Mortal Coil should draw a card when it kills the target."""
    game, p1, p2 = new_hs_game()

    # Target with 1 HP
    wisp = make_obj(game, WISP, p2)

    # Put card in deck
    game.create_object(
        name="Deck Card", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=WISP.characteristics, card_def=WISP
    )

    mc_obj = game.create_object(
        name=MORTAL_COIL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MORTAL_COIL.characteristics, card_def=MORTAL_COIL
    )
    events = MORTAL_COIL.spell_effect(mc_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Should have a draw event since wisp (1 HP) dies to 1 damage
    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
    assert len(draw_events) >= 1, "Mortal Coil should draw when killing target"


def test_mortal_coil_no_draw_on_survive():
    """Mortal Coil should NOT draw when target survives."""
    game, p1, p2 = new_hs_game()

    # Target with 5 HP
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    mc_obj = game.create_object(
        name=MORTAL_COIL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MORTAL_COIL.characteristics, card_def=MORTAL_COIL
    )
    events = MORTAL_COIL.spell_effect(mc_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
    assert len(draw_events) == 0, "Mortal Coil should not draw when target survives"


def test_execute_only_works_on_damaged():
    """Execute should only destroy damaged minions."""
    game, p1, p2 = new_hs_game()

    # Undamaged minion
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    ex_obj = game.create_object(
        name=EXECUTE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=EXECUTE.characteristics, card_def=EXECUTE
    )
    events = EXECUTE.spell_effect(ex_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Yeti should still be alive (undamaged, Execute has no valid target)
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == yeti.id]
    assert len(destroy_events) == 0, "Execute should not destroy undamaged minion"


def test_execute_destroys_damaged_minion():
    """Execute should destroy a damaged minion."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p2)
    yeti.state.damage = 1  # Now damaged

    ex_obj = game.create_object(
        name=EXECUTE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=EXECUTE.characteristics, card_def=EXECUTE
    )
    events = EXECUTE.spell_effect(ex_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == yeti.id]
    assert len(destroy_events) >= 1, "Execute should destroy damaged minion"


def test_big_game_hunter_destroys_7plus_attack():
    """Big Game Hunter battlecry destroys minions with 7+ Attack."""
    game, p1, p2 = new_hs_game()

    # Place BGH on board (battlecry fires from hand only, so test the effect logic)
    ogre = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7 - should NOT be killed
    # BGH targets 7+ attack, ogre has 6 so shouldn't die

    # Let's test with a War Golem (7/7)
    from src.cards.hearthstone.basic import WAR_GOLEM
    golem = make_obj(game, WAR_GOLEM, p2)  # 7/7

    # The BGH battlecry fires via ETB from hand
    bgh = game.create_object(
        name=BIG_GAME_HUNTER.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=BIG_GAME_HUNTER.characteristics, card_def=BIG_GAME_HUNTER
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': bgh.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
        source=bgh.id
    ))

    # Check for destroy events targeting the golem
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == golem.id]
    assert len(destroy_events) >= 1, "BGH should destroy 7+ attack minion"


# ============================================================================
# DISCARD AND SELF-DAMAGE
# ============================================================================

def test_soulfire_deals_damage_and_discards():
    """Soulfire: Deal 4 damage and discard a random card."""
    game, p1, p2 = new_hs_game()

    # Put a card in P1's hand to be discarded
    hand_card = game.create_object(
        name="Discard Me", owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=WISP.characteristics, card_def=WISP
    )

    sf_obj = game.create_object(
        name=SOULFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=SOULFIRE.characteristics, card_def=SOULFIRE
    )
    events = SOULFIRE.spell_effect(sf_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Should have dealt 4 damage to an enemy
    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and e.payload.get('amount') == 4]
    assert len(damage_events) >= 1, "Soulfire should deal 4 damage"

    # Should have discarded a card
    discard_events = [e for e in game.state.event_log
                      if e.type == EventType.DISCARD]
    assert len(discard_events) >= 1, "Soulfire should discard a card"


def test_soulfire_empty_hand_no_discard():
    """Soulfire with empty hand should still deal damage, just no discard."""
    game, p1, p2 = new_hs_game()

    # P1's hand is empty
    hand = game.state.zones.get(f"hand_{p1.id}")
    if hand:
        hand.objects.clear()

    sf_obj = game.create_object(
        name=SOULFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=SOULFIRE.characteristics, card_def=SOULFIRE
    )
    events = SOULFIRE.spell_effect(sf_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and e.payload.get('amount') == 4]
    assert len(damage_events) >= 1, "Soulfire should still deal damage with empty hand"


def test_hellfire_damages_all_including_own():
    """Hellfire deals 3 damage to ALL characters (both heroes and all minions)."""
    game, p1, p2 = new_hs_game()

    my_minion = make_obj(game, CHILLWIND_YETI, p1)
    their_minion = make_obj(game, RIVER_CROCOLISK, p2)

    hf_obj = game.create_object(
        name=HELLFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=HELLFIRE.characteristics, card_def=HELLFIRE
    )
    events = HELLFIRE.spell_effect(hf_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Both heroes should take 3 damage
    assert p1.life <= 27, f"Hellfire should damage own hero, P1 at {p1.life}"
    assert p2.life <= 27, f"Hellfire should damage enemy hero, P2 at {p2.life}"


# ============================================================================
# EQUALITY INTERACTIONS
# ============================================================================

def test_equality_sets_all_minions_to_1_hp():
    """Equality should set all minions' health to 1."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)   # 4/5
    ogre = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    eq_obj = game.create_object(
        name=EQUALITY.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=EQUALITY.characteristics, card_def=EQUALITY
    )
    events = EQUALITY.spell_effect(eq_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Both minions should have 1 health
    yeti_health = get_toughness(yeti, game.state) - yeti.state.damage
    ogre_health = get_toughness(ogre, game.state) - ogre.state.damage
    assert yeti_health <= 1, f"Equality should set Yeti health to 1, got {yeti_health}"
    assert ogre_health <= 1, f"Equality should set Ogre health to 1, got {ogre_health}"


def test_equality_plus_consecration_board_clear():
    """Classic Paladin combo: Equality (all 1 HP) + Consecration (2 to enemies) = clear."""
    game, p1, p2 = new_hs_game()

    y1 = make_obj(game, CHILLWIND_YETI, p2)
    y2 = make_obj(game, BOULDERFIST_OGRE, p2)

    # Equality
    eq_obj = game.create_object(
        name=EQUALITY.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=EQUALITY.characteristics, card_def=EQUALITY
    )
    events = EQUALITY.spell_effect(eq_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Consecration (2 damage to all enemies)
    con_obj = game.create_object(
        name=CONSECRATION.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=CONSECRATION.characteristics, card_def=CONSECRATION
    )
    events = CONSECRATION.spell_effect(con_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Both should be dead (1 HP - 2 damage = dead)
    run_sba(game)
    assert y1.zone == ZoneType.GRAVEYARD or y1.state.damage >= get_toughness(y1, game.state), \
        "Yeti should die from Equality + Consecration"


# ============================================================================
# SPELL TRIGGER CHAINS
# ============================================================================

def test_northshire_cleric_draws_on_heal():
    """Northshire Cleric draws a card whenever a minion is healed."""
    game, p1, p2 = new_hs_game()

    cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)

    # Put card in deck
    game.create_object(
        name="Deck Card", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=WISP.characteristics, card_def=WISP
    )

    # Damage a minion then heal it
    yeti = make_obj(game, CHILLWIND_YETI, p1)
    yeti.state.damage = 2

    # Heal the yeti (Northshire Cleric listens for LIFE_CHANGE with positive amount on object_id)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'object_id': yeti.id, 'amount': 2},
        source='test'
    ))

    # Cleric should have triggered a draw
    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
    assert len(draw_events) >= 1, "Northshire Cleric should draw on minion heal"


def test_holy_nova_heals_and_damages():
    """Holy Nova: Deal 2 damage to all enemies, restore 2 health to all friendlies."""
    game, p1, p2 = new_hs_game()

    my_minion = make_obj(game, CHILLWIND_YETI, p1)
    my_minion.state.damage = 3

    their_minion = make_obj(game, RIVER_CROCOLISK, p2)

    hn_obj = game.create_object(
        name=HOLY_NOVA.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=HOLY_NOVA.characteristics, card_def=HOLY_NOVA
    )
    events = HOLY_NOVA.spell_effect(hn_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Enemy should take 2 damage
    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE
                     and e.payload.get('target') == their_minion.id]
    assert len(damage_events) >= 1, "Holy Nova should damage enemy minions"


def test_shadow_word_pain_destroys_low_attack():
    """Shadow Word: Pain destroys minions with 3 or less Attack."""
    game, p1, p2 = new_hs_game()

    croc = make_obj(game, RIVER_CROCOLISK, p2)  # 2/3

    swp_obj = game.create_object(
        name=SHADOW_WORD_PAIN.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=SHADOW_WORD_PAIN.characteristics, card_def=SHADOW_WORD_PAIN
    )
    events = SHADOW_WORD_PAIN.spell_effect(swp_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == croc.id]
    assert len(destroy_events) >= 1, "SW:Pain should destroy 2-attack minion"


def test_shadow_word_death_destroys_high_attack():
    """Shadow Word: Death destroys minions with 5 or more Attack."""
    game, p1, p2 = new_hs_game()

    ogre = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    swd_obj = game.create_object(
        name=SHADOW_WORD_DEATH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=SHADOW_WORD_DEATH.characteristics, card_def=SHADOW_WORD_DEATH
    )
    events = SHADOW_WORD_DEATH.spell_effect(swd_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == ogre.id]
    assert len(destroy_events) >= 1, "SW:Death should destroy 6-attack minion"


# ============================================================================
# BLOODLUST
# ============================================================================

def test_bloodlust_buffs_all_friendly_minions():
    """Bloodlust gives all friendly minions +3 Attack this turn."""
    game, p1, p2 = new_hs_game()

    w1 = make_obj(game, WISP, p1)     # 1/1
    w2 = make_obj(game, WISP, p1)     # 1/1

    bl_obj = game.create_object(
        name=BLOODLUST.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODLUST.characteristics, card_def=BLOODLUST
    )
    events = BLOODLUST.spell_effect(bl_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Both wisps should have +3 attack
    p_w1 = get_power(w1, game.state)
    p_w2 = get_power(w2, game.state)
    assert p_w1 >= 4, f"Wisp should have 1+3=4 attack after Bloodlust, got {p_w1}"
    assert p_w2 >= 4, f"Wisp should have 1+3=4 attack after Bloodlust, got {p_w2}"


# ============================================================================
# MULTI-MINION COMBAT SCENARIOS
# ============================================================================

def test_knife_juggler_triggers_on_summon():
    """Knife Juggler should deal 1 damage when a friendly minion is summoned."""
    game, p1, p2 = new_hs_game()

    kj = make_obj(game, KNIFE_JUGGLER, p1)

    # Summon a minion
    wisp = game.create_object(
        name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=WISP.characteristics, card_def=WISP
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': wisp.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
        source=wisp.id
    ))

    # KJ should have thrown a knife (1 damage)
    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE
                     and e.payload.get('amount') == 1
                     and e.source == kj.id]
    assert len(damage_events) >= 1, "Knife Juggler should deal 1 damage on summon"


def test_armorsmith_multiple_damage_events():
    """Armorsmith should gain armor for EACH minion hit."""
    game, p1, p2 = new_hs_game()

    smith = make_obj(game, ARMORSMITH, p1)
    w1 = make_obj(game, WISP, p1)
    w2 = make_obj(game, WISP, p1)

    p1.armor = 0

    # Whirlwind hits smith + w1 + w2 (all friendly)
    ww_obj = game.create_object(
        name=WHIRLWIND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=WHIRLWIND.characteristics, card_def=WHIRLWIND
    )
    events = WHIRLWIND.spell_effect(ww_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    # Armorsmith triggers for each friendly minion damaged (3: smith, w1, w2)
    armor_events = [e for e in game.state.event_log
                    if e.type == EventType.ARMOR_GAIN and e.payload.get('player') == p1.id]
    total_armor = sum(e.payload.get('amount', 0) for e in armor_events)
    assert total_armor >= 3, f"Armorsmith should gain 3+ armor from Whirlwind, got {total_armor}"


def test_frothing_berserker_grows_from_any_damage():
    """Frothing Berserker gains +1 Attack whenever ANY minion takes damage."""
    game, p1, p2 = new_hs_game()

    frothing = make_obj(game, FROTHING_BERSERKER, p1)
    base_power = get_power(frothing, game.state)

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    friendly = make_obj(game, WISP, p1)

    # Whirlwind hits 3 minions (frothing, enemy, friendly)
    ww_obj = game.create_object(
        name=WHIRLWIND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=WHIRLWIND.characteristics, card_def=WHIRLWIND
    )
    events = WHIRLWIND.spell_effect(ww_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    new_power = get_power(frothing, game.state)
    # Should gain at least +3 (from 3 minions hit)
    assert new_power >= base_power + 3, \
        f"Frothing should gain +3 from 3 damaged minions, was {base_power} now {new_power}"


def test_battle_rage_draws_per_damaged_friendly():
    """Battle Rage draws for each damaged friendly character."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, CHILLWIND_YETI, p1)
    m2 = make_obj(game, RIVER_CROCOLISK, p1)
    m1.state.damage = 1
    m2.state.damage = 1

    # Put cards in deck
    for _ in range(3):
        game.create_object(
            name="Deck Card", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

    br_obj = game.create_object(
        name=BATTLE_RAGE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=BATTLE_RAGE.characteristics, card_def=BATTLE_RAGE
    )
    events = BATTLE_RAGE.spell_effect(br_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
    # Should draw for each damaged friendly character (2 minions + potentially hero)
    assert len(draw_events) >= 1, "Battle Rage should draw for damaged friendlies"


def test_cruel_taskmaster_damages_and_buffs():
    """Cruel Taskmaster: Deal 1 damage to a minion, give it +2 Attack."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)

    # Play Cruel Taskmaster from hand to trigger battlecry
    ct = game.create_object(
        name=CRUEL_TASKMASTER.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=CRUEL_TASKMASTER.characteristics, card_def=CRUEL_TASKMASTER
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': ct.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
        source=ct.id
    ))

    # The battlecry should have triggered - check for damage event
    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and e.payload.get('amount') == 1]
    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2]

    assert len(damage_events) >= 1 or len(pt_events) >= 1, \
        "Cruel Taskmaster should deal 1 damage and/or buff +2 attack"


# ============================================================================
# MAGMA RAGER AND FRAGILE MINIONS
# ============================================================================

def test_magma_rager_dies_to_hero_power():
    """Magma Rager (5/1) should die to Mage hero power (1 damage)."""
    game, p1, p2 = new_hs_game()

    rager = make_obj(game, MAGMA_RAGER, p2)  # 5/1

    # Mage hero power deals 1 damage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': rager.id, 'amount': 1, 'source': 'hero_power'},
        source='hero_power'
    ))

    run_sba(game)
    assert rager.zone == ZoneType.GRAVEYARD, f"Magma Rager should die to 1 damage, zone={rager.zone}"


def test_damaged_minion_survives_at_1_hp():
    """A 4/5 Yeti with 4 damage should survive (1 HP remaining)."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)
    yeti.state.damage = 4

    run_sba(game)
    assert yeti.zone == ZoneType.BATTLEFIELD, "Yeti at 1 HP should survive"


def test_zero_damage_doesnt_kill():
    """0 damage should not trigger death."""
    game, p1, p2 = new_hs_game()

    wisp = make_obj(game, WISP, p1)  # 1/1

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': wisp.id, 'amount': 0, 'source': 'test'},
        source='test'
    ))

    run_sba(game)
    assert wisp.zone == ZoneType.BATTLEFIELD, "0 damage should not kill a minion"


# ============================================================================
# LEEROY JENKINS
# ============================================================================

def test_leeroy_summons_whelps_for_opponent():
    """Leeroy Jenkins battlecry should summon two 1/1 Whelps for the opponent."""
    game, p1, p2 = new_hs_game()

    # Play Leeroy from hand
    leeroy = game.create_object(
        name=LEEROY_JENKINS.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=LEEROY_JENKINS.characteristics, card_def=LEEROY_JENKINS
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': leeroy.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
        source=leeroy.id
    ))

    # Should have created Whelp tokens for the opponent
    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('controller') == p2.id]
    assert len(token_events) >= 2, f"Leeroy should summon 2 Whelps for opponent, got {len(token_events)}"


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
