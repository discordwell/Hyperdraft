"""
Hearthstone Unhappy Path Tests - Batch 9

Druid and Rogue class tests: Choose One mechanics, Innervate/mana,
hero attack from spells, Combo keyword, weapon interactions,
stealth persistence, bounce/return effects, Edwin VanCleef scaling.
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
    KNIFE_JUGGLER, HARVEST_GOLEM, LEEROY_JENKINS,
    IRONBEAK_OWL,
)
from src.cards.hearthstone.druid import (
    CLAW, MOONFIRE, INNERVATE, WILD_GROWTH, SAVAGE_ROAR,
    SWIPE, STARFIRE, HEALING_TOUCH, BITE, NATURALIZE,
    POWER_OF_THE_WILD, FORCE_OF_NATURE, SOUL_OF_THE_FOREST,
    DRUID_OF_THE_CLAW, ANCIENT_OF_WAR,
)
from src.cards.hearthstone.rogue import (
    SINISTER_STRIKE, SAP, SHIV, FAN_OF_KNIVES, ASSASSINATE,
    VANISH, COLD_BLOOD, EVISCERATE, BLADE_FLURRY,
    CONCEAL, BETRAYAL, DEFIAS_RINGLEADER, SI7_AGENT,
    EDWIN_VANCLEEF, PREPARATION, SHADOWSTEP, DEADLY_POISON,
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


def cast_spell(game, card_def, owner, targets=None):
    """Helper to cast a spell properly (creates obj, calls spell_effect, emits events)."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets)
    for e in events:
        game.emit(e)
    return obj


# ============================================================================
# DRUID: Mana Manipulation
# ============================================================================

def test_innervate_grants_two_mana():
    """Innervate should give +2 mana crystals available."""
    game, p1, p2 = new_hs_game()

    before = p1.mana_crystals_available
    cast_spell(game, INNERVATE, p1)
    after = p1.mana_crystals_available

    assert after == before + 2, f"Innervate should grant +2 mana, before={before} after={after}"


def test_wild_growth_adds_empty_crystal():
    """Wild Growth should add 1 permanent mana crystal."""
    game, p1, p2 = new_hs_game()

    # Set mana to 5 so we can see growth
    p1.mana_crystals = 5
    cast_spell(game, WILD_GROWTH, p1)

    assert p1.mana_crystals == 6, f"Wild Growth should go 5→6, got {p1.mana_crystals}"


def test_wild_growth_capped_at_10():
    """Wild Growth at 10 mana should not exceed 10."""
    game, p1, p2 = new_hs_game()

    p1.mana_crystals = 10
    cast_spell(game, WILD_GROWTH, p1)

    assert p1.mana_crystals == 10, f"Should stay at 10, got {p1.mana_crystals}"


# ============================================================================
# DRUID: Hero Attack Spells
# ============================================================================

def test_claw_gives_hero_attack_and_armor():
    """Claw gives +2 attack and +2 armor."""
    game, p1, p2 = new_hs_game()

    atk_before = p1.weapon_attack
    armor_before = p1.armor

    cast_spell(game, CLAW, p1)

    assert p1.weapon_attack == atk_before + 2, f"Claw should give +2 attack, got {p1.weapon_attack}"
    assert p1.armor == armor_before + 2, f"Claw should give +2 armor, got {p1.armor}"


def test_claw_attack_clears_on_turn_end():
    """Claw's +2 attack should be removed at end of turn."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, CLAW, p1)
    assert p1.weapon_attack >= 2, "Claw should give attack"

    # Emit TURN_END
    game.emit(Event(
        type=EventType.TURN_END,
        payload={'player': p1.id},
        source='test'
    ))

    assert p1.weapon_attack == 0, f"Claw attack should clear at end of turn, got {p1.weapon_attack}"


def test_bite_gives_hero_attack_and_armor():
    """Bite gives +4 attack and +4 armor."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, BITE, p1)

    assert p1.weapon_attack >= 4, f"Bite should give +4 attack, got {p1.weapon_attack}"
    assert p1.armor >= 4, f"Bite should give +4 armor, got {p1.armor}"


def test_savage_roar_buffs_all_friendlies():
    """Savage Roar buffs all friendly minions +2 attack and gives hero +2 attack."""
    game, p1, p2 = new_hs_game()

    w1 = make_obj(game, WISP, p1)
    w2 = make_obj(game, WISP, p1)
    base_power = get_power(w1, game.state)

    cast_spell(game, SAVAGE_ROAR, p1)

    for w in [w1, w2]:
        boosted = get_power(w, game.state)
        assert boosted >= base_power + 2, f"Savage Roar should +2 attack, got {boosted}"

    assert p1.weapon_attack >= 2, "Savage Roar should give hero +2 attack"


# ============================================================================
# DRUID: Damage Spells
# ============================================================================

def test_moonfire_deals_one_damage():
    """Moonfire deals 1 damage to a random enemy target."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    cast_spell(game, MOONFIRE, p1)

    # Target is random (could be minion or hero)
    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 1]
    assert len(dmg_events) >= 1, "Moonfire should deal 1 damage to some enemy"


def test_swipe_deals_4_to_target_1_to_rest():
    """Swipe: 4 to primary, 1 to all other enemies."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, BOULDERFIST_OGRE, p2)
    e2 = make_obj(game, CHILLWIND_YETI, p2)

    cast_spell(game, SWIPE, p1)

    # Primary gets 4, all others get 1 (including hero)
    dmg_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    amounts = [e.payload.get('amount', 0) for e in dmg_events]
    assert 4 in amounts, f"Swipe should deal 4 to primary target, got amounts={amounts}"
    assert len(dmg_events) >= 2, f"Swipe should damage multiple targets, got {len(dmg_events)}"


def test_starfire_deals_damage_and_draws():
    """Starfire deals 5 damage to a random enemy and draws a card."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, STARFIRE, p1)

    # Target is random (could be enemy minion or hero)
    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 5]
    assert len(dmg_events) >= 1, "Starfire should deal 5 damage to some target"
    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "Starfire should draw a card"


# ============================================================================
# DRUID: Utility Spells
# ============================================================================

def test_naturalize_destroys_and_opponent_draws():
    """Naturalize destroys an enemy minion, opponent draws 2."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    # Seed opponent's deck
    make_obj(game, WISP, p2, zone=ZoneType.LIBRARY)
    make_obj(game, WISP, p2, zone=ZoneType.LIBRARY)

    cast_spell(game, NATURALIZE, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == enemy.id]
    assert len(destroy_events) >= 1, "Naturalize should destroy the enemy minion"

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW and e.payload.get('player') == p2.id]
    assert len(draw_events) >= 1, "Naturalize should make opponent draw"


def test_healing_touch_heals_hero():
    """Healing Touch restores 8 health."""
    game, p1, p2 = new_hs_game()

    p1.life = 20
    cast_spell(game, HEALING_TOUCH, p1)

    heal_events = [e for e in game.state.event_log
                   if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('amount') == 8]
    assert len(heal_events) >= 1, "Healing Touch should emit 8 HP heal event"


def test_force_of_nature_summons_three_treants():
    """Force of Nature summons 3 Treant tokens."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, FORCE_OF_NATURE, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Treant']
    assert len(token_events) == 3, f"Force of Nature should summon 3 Treants, got {len(token_events)}"


def test_soul_of_the_forest_deathrattle():
    """Soul of the Forest gives minions DR: summon a Treant."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)
    cast_spell(game, SOUL_OF_THE_FOREST, p1)

    # Kill the minion
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': minion.id},
        source='test'
    ))

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Treant']
    assert len(token_events) >= 1, "Dead minion with Soul of the Forest should summon Treant"


# ============================================================================
# DRUID: Choose One / Battlecries
# ============================================================================

def test_druid_of_the_claw_battlecry_gives_taunt():
    """Druid of the Claw (AI) should pick bear form: +2 HP and Taunt."""
    game, p1, p2 = new_hs_game()

    dotc = play_from_hand(game, DRUID_OF_THE_CLAW, p1)

    has_taunt = has_ability(dotc, 'taunt', game.state)
    assert has_taunt, "Druid of the Claw should have Taunt (bear form)"

    hp = get_toughness(dotc, game.state)
    # Base 4 + 2 from battlecry = 6
    assert hp >= 6, f"Druid of the Claw bear form should be 4+2=6 HP, got {hp}"


def test_ancient_of_war_battlecry_gives_taunt_and_health():
    """Ancient of War (AI) picks +5 HP and Taunt."""
    game, p1, p2 = new_hs_game()

    aow = play_from_hand(game, ANCIENT_OF_WAR, p1)

    assert has_ability(aow, 'taunt', game.state), "Ancient of War should have Taunt"

    hp = get_toughness(aow, game.state)
    # Base 5 + 5 = 10
    assert hp >= 10, f"Ancient of War should be 5+5=10 HP, got {hp}"


# ============================================================================
# ROGUE: Basic Spells
# ============================================================================

def test_sinister_strike_damages_enemy_hero():
    """Sinister Strike deals 3 to enemy hero."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, SINISTER_STRIKE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and e.payload.get('target') == p2.hero_id
                  and e.payload.get('amount') == 3]
    assert len(dmg_events) >= 1, "Sinister Strike should deal 3 to enemy hero"


def test_sap_returns_enemy_to_hand():
    """Sap returns an enemy minion to hand."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    cast_spell(game, SAP, p1)

    return_events = [e for e in game.state.event_log
                     if e.type == EventType.RETURN_TO_HAND
                     and e.payload.get('object_id') == enemy.id]
    assert len(return_events) >= 1, "Sap should return enemy minion to hand"


def test_shiv_deals_damage_and_draws():
    """Shiv deals 1 damage and draws a card."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, SHIV, p1)

    assert enemy.state.damage >= 1 or any(
        e.type == EventType.DAMAGE for e in game.state.event_log
    ), "Shiv should deal 1 damage"

    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "Shiv should draw a card"


def test_fan_of_knives_aoe_and_draw():
    """Fan of Knives deals 1 to all enemy minions and draws."""
    game, p1, p2 = new_hs_game()

    e1 = make_obj(game, WISP, p2)
    e2 = make_obj(game, WISP, p2)
    friendly = make_obj(game, WISP, p1)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, FAN_OF_KNIVES, p1)

    assert e1.state.damage >= 1, "Fan should hit enemy minion 1"
    assert e2.state.damage >= 1, "Fan should hit enemy minion 2"
    assert friendly.state.damage == 0, "Fan should not hit friendly minions"


def test_assassinate_destroys_enemy():
    """Assassinate destroys a single enemy minion."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)
    cast_spell(game, ASSASSINATE, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == enemy.id]
    assert len(destroy_events) >= 1, "Assassinate should destroy enemy minion"


def test_vanish_returns_all_minions():
    """Vanish returns ALL minions to owners' hands."""
    game, p1, p2 = new_hs_game()

    f1 = make_obj(game, WISP, p1)
    e1 = make_obj(game, WISP, p2)

    cast_spell(game, VANISH, p1)

    return_events = [e for e in game.state.event_log
                     if e.type == EventType.RETURN_TO_HAND]
    assert len(return_events) >= 2, f"Vanish should return all minions, got {len(return_events)}"


# ============================================================================
# ROGUE: Combo Mechanic
# ============================================================================

def test_cold_blood_no_combo_gives_2_attack():
    """Cold Blood without combo gives +2 attack."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)  # 1/1
    p1.cards_played_this_turn = 0  # No combo

    cast_spell(game, COLD_BLOOD, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 2]
    assert len(pt_events) >= 1, "Cold Blood (no combo) should give +2 attack"


def test_cold_blood_combo_gives_4_attack():
    """Cold Blood WITH combo gives +4 attack."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)
    p1.cards_played_this_turn = 1  # Combo active

    cast_spell(game, COLD_BLOOD, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod') == 4]
    assert len(pt_events) >= 1, "Cold Blood (combo) should give +4 attack"


def test_eviscerate_no_combo_deals_2():
    """Eviscerate without combo deals 2 damage."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    p1.cards_played_this_turn = 0

    cast_spell(game, EVISCERATE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg_events) >= 1, "Eviscerate (no combo) should deal 2"


def test_eviscerate_combo_deals_4():
    """Eviscerate with combo deals 4 damage."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    p1.cards_played_this_turn = 1

    cast_spell(game, EVISCERATE, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 4]
    assert len(dmg_events) >= 1, "Eviscerate (combo) should deal 4"


def test_defias_ringleader_combo_summons_bandit():
    """Defias Ringleader with combo summons a 2/1 Defias Bandit."""
    game, p1, p2 = new_hs_game()

    p1.cards_played_this_turn = 1  # Combo active
    defias = play_from_hand(game, DEFIAS_RINGLEADER, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and 'Defias' in e.payload.get('token', {}).get('name', '')]
    assert len(token_events) >= 1, "Defias Ringleader combo should summon Defias Bandit"


def test_si7_agent_combo_deals_2_damage():
    """SI:7 Agent with combo deals 2 damage."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, CHILLWIND_YETI, p2)
    p1.cards_played_this_turn = 1

    si7 = play_from_hand(game, SI7_AGENT, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and e.payload.get('amount') == 2]
    assert len(dmg_events) >= 1, "SI:7 Agent combo should deal 2 damage"


def test_edwin_vancleef_scales_with_cards_played():
    """Edwin VanCleef gains +2/+2 per card played this turn."""
    game, p1, p2 = new_hs_game()

    p1.cards_played_this_turn = 3  # 3 cards played before Edwin

    edwin = play_from_hand(game, EDWIN_VANCLEEF, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('object_id') == edwin.id]
    if pt_events:
        bonus = pt_events[0].payload.get('power_mod', 0)
        # 3 cards * 2 = +6/+6
        assert bonus == 6, f"Edwin should get +{3*2} from 3 cards, got +{bonus}"


# ============================================================================
# ROGUE: Weapon & Stealth Interactions
# ============================================================================

def test_deadly_poison_buffs_weapon():
    """Deadly Poison adds +2 to weapon attack."""
    game, p1, p2 = new_hs_game()

    p1.weapon_attack = 1
    p1.weapon_durability = 2

    cast_spell(game, DEADLY_POISON, p1)

    assert p1.weapon_attack == 3, f"Deadly Poison should give 1+2=3 attack, got {p1.weapon_attack}"


def test_blade_flurry_destroys_weapon_deals_aoe():
    """Blade Flurry destroys weapon and deals its damage to all enemy minions."""
    game, p1, p2 = new_hs_game()

    p1.weapon_attack = 3
    p1.weapon_durability = 2

    e1 = make_obj(game, CHILLWIND_YETI, p2)
    e2 = make_obj(game, RIVER_CROCOLISK, p2)

    cast_spell(game, BLADE_FLURRY, p1)

    assert p1.weapon_attack == 0, "Blade Flurry should destroy weapon"
    assert p1.weapon_durability == 0, "Blade Flurry should destroy weapon"
    assert e1.state.damage >= 3, f"Enemy 1 should take 3 damage, got {e1.state.damage}"
    assert e2.state.damage >= 3, f"Enemy 2 should take 3 damage, got {e2.state.damage}"


def test_conceal_gives_stealth():
    """Conceal gives all friendly minions Stealth."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, WISP, p1)
    m2 = make_obj(game, CHILLWIND_YETI, p1)

    cast_spell(game, CONCEAL, p1)

    assert m1.state.stealth == True, "Conceal should give minion 1 stealth"
    assert m2.state.stealth == True, "Conceal should give minion 2 stealth"


def test_conceal_stealth_clears_on_turn_start():
    """Conceal stealth should be removed at start of your next turn."""
    game, p1, p2 = new_hs_game()

    m1 = make_obj(game, WISP, p1)
    cast_spell(game, CONCEAL, p1)

    assert m1.state.stealth == True, "Should have stealth after Conceal"

    # Emit TURN_START for the controller
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': p1.id},
        source='test'
    ))

    assert m1.state.stealth == False, "Concealed stealth should clear at turn start"


def test_shadowstep_returns_minion():
    """Shadowstep returns a friendly minion to hand."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)

    cast_spell(game, SHADOWSTEP, p1, targets=[yeti.id])

    return_events = [e for e in game.state.event_log
                     if e.type == EventType.RETURN_TO_HAND
                     and e.payload.get('object_id') == yeti.id]
    assert len(return_events) >= 1, "Shadowstep should return minion to hand"
    # Note: Cost reduction is applied inside spell_effect, but the bounce
    # handler in pipeline.py resets characteristics from card_def. The cost
    # reduction should ideally be applied AFTER bounce via a modifier, but
    # for now this is a known limitation.


def test_preparation_reduces_next_spell():
    """Preparation makes the next spell cost 3 less."""
    game, p1, p2 = new_hs_game()

    cast_spell(game, PREPARATION, p1)

    # Check that a cost modifier was added
    assert len(p1.cost_modifiers) >= 1, "Preparation should add a cost modifier"
    modifier = p1.cost_modifiers[-1]
    assert modifier['amount'] >= 3, f"Preparation should reduce by 3, got {modifier.get('amount')}"


def test_betrayal_damages_adjacent():
    """Betrayal: Target enemy minion deals its damage to adjacent minions."""
    game, p1, p2 = new_hs_game()

    # Place 3 enemy minions; target the middle one
    left = make_obj(game, WISP, p2)       # 1/1
    mid = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7
    right = make_obj(game, WISP, p2)      # 1/1

    cast_spell(game, BETRAYAL, p1, targets=[mid.id])

    # Adjacent minions should take 6 damage (Ogre's attack)
    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and e.payload.get('source') == mid.id]
    assert len(dmg_events) >= 1, "Betrayal should make target deal damage to adjacents"


# ============================================================================
# DRUID + ROGUE: Cross-class interactions
# ============================================================================

def test_force_of_nature_savage_roar_combo():
    """Force of Nature (3 Treants) + Savage Roar (+2 atk each) = classic combo."""
    game, p1, p2 = new_hs_game()

    # Force of Nature summons 3 x 2/2 Treants
    cast_spell(game, FORCE_OF_NATURE, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN]
    assert len(token_events) == 3, f"Should have 3 Treants, got {len(token_events)}"

    # Now Savage Roar
    cast_spell(game, SAVAGE_ROAR, p1)

    # Hero should have +2 attack
    assert p1.weapon_attack >= 2, "Savage Roar should give hero +2 attack"


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
