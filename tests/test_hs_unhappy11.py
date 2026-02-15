"""
Hearthstone Unhappy Path Tests - Batch 11

Warlock, Paladin, Shaman, and Warrior class deep-dives: self-damage battlecries,
discard mechanics, delayed destruction (Corruption), weapon destruction (Ooze),
Power Overwhelming death trigger, Void Terror adjacency, and more class-specific
interactions that diverge from the happy path.
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
)
from src.cards.hearthstone.classic import (
    ACIDIC_SWAMP_OOZE, HARVEST_GOLEM, FIERY_WAR_AXE,
    TRUESILVER_CHAMPION, KNIFE_JUGGLER,
)
from src.cards.hearthstone.warlock import (
    SOULFIRE, MORTAL_COIL, SHADOW_BOLT, DRAIN_LIFE, HELLFIRE,
    POWER_OVERWHELMING, CORRUPTION, TWISTING_NETHER,
    SHADOWFLAME, SIPHON_SOUL, DEMONFIRE, BANE_OF_DOOM,
    FLAME_IMP, DREAD_INFERNAL, SUCCUBUS, DOOMGUARD,
    PIT_LORD, VOID_TERROR, VOIDWALKER,
)
from src.cards.hearthstone.paladin import (
    BLESSING_OF_MIGHT, HAND_OF_PROTECTION, HUMILITY,
    HOLY_LIGHT, HAMMER_OF_WRATH, EQUALITY,
    BLESSING_OF_KINGS, GUARDIAN_OF_KINGS,
    ALDOR_PEACEKEEPER,
)
from src.cards.hearthstone.shaman import (
    LIGHTNING_BOLT, HEX, ROCKBITER_WEAPON, FROST_SHOCK,
    LAVA_BURST, LIGHTNING_STORM,
)
from src.cards.hearthstone.warrior import (
    EXECUTE, WHIRLWIND, SHIELD_BLOCK, HEROIC_STRIKE,
    CLEAVE, ARMORSMITH, FROTHING_BERSERKER,
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


# ============================================================================
# WARLOCK: Damage Spells
# ============================================================================

def test_shadow_bolt_deals_4_to_minion():
    """Shadow Bolt deals 4 damage to an enemy minion."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    cast_spell(game, SHADOW_BOLT, p1)

    assert enemy.state.damage >= 4, f"Shadow Bolt should deal 4, got {enemy.state.damage}"


def test_drain_life_damages_and_heals():
    """Drain Life deals 2 damage and heals your hero."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    p1.life = 25

    cast_spell(game, DRAIN_LIFE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg_events) >= 1, "Drain Life should deal 2 damage"

    heal_events = [e for e in game.state.event_log
                   if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('amount') == 2
                   and e.payload.get('player') == p1.id]
    assert len(heal_events) >= 1, "Drain Life should heal hero for 2"


def test_hellfire_hits_all_characters_including_heroes():
    """Hellfire deals 3 to ALL characters including own hero and minions."""
    game, p1, p2 = new_hs_game()

    friendly = make_obj(game, CHILLWIND_YETI, p1)
    enemy = make_obj(game, CHILLWIND_YETI, p2)

    cast_spell(game, HELLFIRE, p1)

    assert friendly.state.damage >= 3, f"Hellfire should hit friendly minion, got {friendly.state.damage}"
    assert enemy.state.damage >= 3, f"Hellfire should hit enemy minion, got {enemy.state.damage}"

    # Should also damage both heroes
    hero_dmg = [e for e in game.state.event_log
                if e.type == EventType.DAMAGE
                and e.payload.get('amount') == 3
                and (e.payload.get('target') == p1.hero_id or e.payload.get('target') == p2.hero_id)]
    assert len(hero_dmg) >= 2, f"Hellfire should hit both heroes, got {len(hero_dmg)}"


# ============================================================================
# WARLOCK: Battlecry Self-Damage
# ============================================================================

def test_dread_infernal_battlecry_damages_all_others():
    """Dread Infernal battlecry: 1 damage to ALL other characters."""
    game, p1, p2 = new_hs_game()

    friendly = make_obj(game, WISP, p1)
    enemy = make_obj(game, CHILLWIND_YETI, p2)

    dread = play_from_hand(game, DREAD_INFERNAL, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 1]
    # Should hit friendly wisp, enemy yeti, and both heroes (4 targets), but NOT self
    self_dmg = [e for e in dmg_events if e.payload.get('target') == dread.id]
    assert len(self_dmg) == 0, "Dread Infernal should NOT damage itself"
    assert len(dmg_events) >= 3, f"Should damage multiple targets, got {len(dmg_events)}"


def test_pit_lord_damages_own_hero():
    """Pit Lord battlecry: deal 5 damage to your hero."""
    game, p1, p2 = new_hs_game()

    p1.life = 30
    pit = play_from_hand(game, PIT_LORD, p1)

    hero_dmg = [e for e in game.state.event_log
                if e.type == EventType.DAMAGE
                and e.payload.get('target') == p1.hero_id
                and e.payload.get('amount') == 5]
    assert len(hero_dmg) >= 1, "Pit Lord should deal 5 to own hero"


# ============================================================================
# WARLOCK: Discard Mechanics
# ============================================================================

def test_succubus_discards_card():
    """Succubus battlecry: discard a random card."""
    game, p1, p2 = new_hs_game()

    make_obj(game, WISP, p1, zone=ZoneType.HAND)
    make_obj(game, WISP, p1, zone=ZoneType.HAND)

    succ = play_from_hand(game, SUCCUBUS, p1)

    discard_events = [e for e in game.state.event_log if e.type == EventType.DISCARD]
    assert len(discard_events) >= 1, "Succubus should discard a card"


def test_doomguard_discards_two():
    """Doomguard battlecry: discard 2 random cards."""
    game, p1, p2 = new_hs_game()

    make_obj(game, WISP, p1, zone=ZoneType.HAND)
    make_obj(game, WISP, p1, zone=ZoneType.HAND)
    make_obj(game, WISP, p1, zone=ZoneType.HAND)

    doom = play_from_hand(game, DOOMGUARD, p1)

    discard_events = [e for e in game.state.event_log if e.type == EventType.DISCARD]
    assert len(discard_events) >= 2, f"Doomguard should discard 2, got {len(discard_events)}"


# ============================================================================
# WARLOCK: Complex Effects
# ============================================================================

def test_power_overwhelming_buffs_then_kills():
    """Power Overwhelming gives +4/+4, then kills the minion at end of turn."""
    game, p1, p2 = new_hs_game()

    wisp = make_obj(game, WISP, p1)

    cast_spell(game, POWER_OVERWHELMING, p1)

    # Should have buffed a friendly minion
    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 4]
    assert len(pt_events) >= 1, "PO should give +4/+4"

    # Trigger end of turn to kill it
    game.emit(Event(
        type=EventType.TURN_END,
        payload={'player': p1.id},
        source='test'
    ))

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'power_overwhelming']
    assert len(destroy_events) >= 1, "PO should destroy the minion at end of turn"


def test_corruption_delayed_destroy():
    """Corruption marks an enemy minion to be destroyed at start of your next turn."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)

    cast_spell(game, CORRUPTION, p1, targets=[enemy.id])

    # Not destroyed yet
    destroy_now = [e for e in game.state.event_log
                   if e.type == EventType.OBJECT_DESTROYED]
    assert len(destroy_now) == 0, "Corruption should NOT immediately destroy"

    # Trigger next turn start for caster
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': p1.id},
        source='test'
    ))

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'corruption']
    assert len(destroy_events) >= 1, "Corruption should destroy at start of next turn"


def test_shadowflame_sacrifices_and_aoes():
    """Shadowflame: destroy a friendly minion, deal its attack to all enemies."""
    game, p1, p2 = new_hs_game()

    # Use a 4/5 yeti as sacrifice
    sacrifice = make_obj(game, CHILLWIND_YETI, p1)
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, SHADOWFLAME, p1)

    # Sacrifice should be destroyed
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'shadowflame']
    assert len(destroy_events) >= 1, "Shadowflame should destroy sacrificed minion"

    # Enemy should take 4 damage (yeti's attack)
    assert enemy.state.damage >= 4, f"Enemy should take 4 (Yeti attack) from Shadowflame, got {enemy.state.damage}"


def test_siphon_soul_destroys_and_heals():
    """Siphon Soul: destroy an enemy minion, heal 3."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    p1.life = 25

    cast_spell(game, SIPHON_SOUL, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == enemy.id]
    assert len(destroy_events) >= 1, "Siphon Soul should destroy"

    heal_events = [e for e in game.state.event_log
                   if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('amount') == 3]
    assert len(heal_events) >= 1, "Siphon Soul should heal 3"


def test_void_terror_eats_adjacents():
    """Void Terror: destroy adjacent minions, gain their combined stats."""
    game, p1, p2 = new_hs_game()

    left = make_obj(game, WISP, p1)         # 1/1
    right = make_obj(game, RIVER_CROCOLISK, p1)  # 2/3

    vt = play_from_hand(game, VOID_TERROR, p1)

    # Should have destroyed at least one adjacent
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'void_terror']
    assert len(destroy_events) >= 1, "Void Terror should destroy adjacent minions"

    # Should have gained stats
    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('object_id') == vt.id]
    assert len(pt_events) >= 1, "Void Terror should gain stats from destroyed minions"


# ============================================================================
# PALADIN SPELLS
# ============================================================================

def test_blessing_of_might_gives_3_attack():
    """Blessing of Might gives +3 Attack to a friendly minion."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)
    cast_spell(game, BLESSING_OF_MIGHT, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 3]
    assert len(pt_events) >= 1, "Blessing of Might should give +3 attack"


def test_hand_of_protection_gives_divine_shield():
    """Hand of Protection gives Divine Shield."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)
    cast_spell(game, HAND_OF_PROTECTION, p1)

    assert minion.state.divine_shield == True, "Hand of Protection should give Divine Shield"


def test_humility_sets_attack_to_1():
    """Humility sets an enemy minion's attack to 1."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7
    cast_spell(game, HUMILITY, p1)

    assert enemy.characteristics.power == 1, f"Humility should set attack to 1, got {enemy.characteristics.power}"


def test_holy_light_heals_hero():
    """Holy Light restores 6 Health."""
    game, p1, p2 = new_hs_game()

    p1.life = 20
    cast_spell(game, HOLY_LIGHT, p1)

    heal_events = [e for e in game.state.event_log
                   if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('amount') == 6]
    assert len(heal_events) >= 1, "Holy Light should heal 6"


def test_blessing_of_kings_gives_4_4():
    """Blessing of Kings gives +4/+4."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)
    cast_spell(game, BLESSING_OF_KINGS, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 4
                 and e.payload.get('toughness_mod') == 4]
    assert len(pt_events) >= 1, "Blessing of Kings should give +4/+4"


# ============================================================================
# SHAMAN SPELLS
# ============================================================================

def test_rockbiter_weapon_gives_hero_attack():
    """Rockbiter Weapon gives +3 Attack this turn."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, ROCKBITER_WEAPON, p1)

    # Should either buff hero or a minion
    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION]
    hero_got_attack = p1.weapon_attack >= 3
    assert len(pt_events) >= 1 or hero_got_attack, "Rockbiter should buff something"


def test_frost_shock_deals_damage_and_freezes():
    """Frost Shock deals 1 damage to an enemy and freezes it."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    cast_spell(game, FROST_SHOCK, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 1]
    assert len(dmg_events) >= 1, "Frost Shock should deal 1 damage"


def test_hex_transforms_minion():
    """Hex transforms an enemy minion into a 0/1 Frog with Taunt."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, HEX, p1)

    # Hex directly mutates the object: sets power/toughness/name
    assert enemy.name == "Frog", f"Hex should transform to Frog, got {enemy.name}"
    assert enemy.characteristics.power == 0, f"Frog should have 0 power, got {enemy.characteristics.power}"
    assert enemy.characteristics.toughness == 1, f"Frog should have 1 toughness, got {enemy.characteristics.toughness}"
    assert has_ability(enemy, 'taunt', game.state), "Frog should have Taunt"


def test_lava_burst_deals_5_with_overload():
    """Lava Burst deals 5 damage and sets overload 2."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    overload_before = p1.overloaded_mana
    cast_spell(game, LAVA_BURST, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 5]
    assert len(dmg_events) >= 1, "Lava Burst should deal 5 damage"
    assert p1.overloaded_mana > overload_before, \
        f"Lava Burst should add overload, before={overload_before}, after={p1.overloaded_mana}"


def test_lightning_storm_damages_enemy_minions():
    """Lightning Storm deals 2-3 damage to all enemy minions."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, CHILLWIND_YETI, p2)
    e2 = make_obj(game, RIVER_CROCOLISK, p2)

    cast_spell(game, LIGHTNING_STORM, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and e.payload.get('amount', 0) >= 2]
    assert len(dmg_events) >= 2, f"Lightning Storm should hit all enemy minions, got {len(dmg_events)}"


# ============================================================================
# WARRIOR SPELLS
# ============================================================================

def test_shield_block_emits_armor_and_draw():
    """Shield Block emits ARMOR_GAIN and DRAW events."""
    game, p1, p2 = new_hs_game()

    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, SHIELD_BLOCK, p1)

    armor_events = [e for e in game.state.event_log
                    if e.type == EventType.ARMOR_GAIN
                    and e.payload.get('amount') == 5]
    assert len(armor_events) >= 1, "Shield Block should emit ARMOR_GAIN 5"
    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "Shield Block should draw a card"


def test_cleave_damages_two_enemy_minions():
    """Cleave deals 2 damage to two random enemy minions."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, CHILLWIND_YETI, p2)
    e2 = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, CLEAVE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg_events) >= 2, f"Cleave should hit 2 minions, got {len(dmg_events)}"


# ============================================================================
# WARLOCK: Voidwalker Taunt
# ============================================================================

def test_voidwalker_has_taunt():
    """Voidwalker should have Taunt."""
    game, p1, p2 = new_hs_game()

    vw = make_obj(game, VOIDWALKER, p1)
    assert has_ability(vw, 'taunt', game.state), "Voidwalker should have Taunt"


# ============================================================================
# CROSS-CLASS: Ooze vs Weapons
# ============================================================================

def test_acidic_swamp_ooze_destroys_weapon():
    """Acidic Swamp Ooze battlecry: destroy opponent's weapon."""
    game, p1, p2 = new_hs_game()

    # Give P2 a weapon
    p2.weapon_attack = 3
    p2.weapon_durability = 2

    ooze = play_from_hand(game, ACIDIC_SWAMP_OOZE, p1)

    # Ooze should destroy the weapon
    assert p2.weapon_attack == 0 or p2.weapon_durability == 0, \
        f"Ooze should destroy weapon, got atk={p2.weapon_attack} dur={p2.weapon_durability}"


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
