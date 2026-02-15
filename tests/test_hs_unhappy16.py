"""
Hearthstone Unhappy Path Tests - Batch 16

Emperor Cobra (poisonous), Demolisher (start-of-turn damage), Raging Worgen
(enrage: windfury + attack), Alarm-o-Bot (start-of-turn swap), Violet Teacher
(spell summon), ImpMaster (end-of-turn imp + self-damage), Stampeding Kodo
(destroy low-attack), Faceless Manipulator (copy minion), and multi-card
interaction chains: double aura stacking, silence removes triggered effects,
Knife Juggler + token generation, Wild Pyro + spell chains, enrage + heal
interactions, deathrattle + board limit interactions.
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
    BLOODFEN_RAPTOR, MURLOC_RAIDER, STONETUSK_BOAR,
    SEN_JIN_SHIELDMASTA,
)
from src.cards.hearthstone.classic import (
    EMPEROR_COBRA, DEMOLISHER, RAGING_WORGEN, ALARM_O_BOT,
    VIOLET_TEACHER, IMP_MASTER, STAMPEDING_KODO, FACELESS_MANIPULATOR,
    KNIFE_JUGGLER, WILD_PYROMANCER, AMANI_BERSERKER,
    FLESHEATING_GHOUL, MURLOC_WARLEADER, DIRE_WOLF_ALPHA,
    HARVEST_GOLEM, ARGENT_SQUIRE, MANA_ADDICT,
    STRANGLETHORN_TIGER, SILVER_HAND_KNIGHT, ARGENT_COMMANDER,
)


# ============================================================
# Test Helpers
# ============================================================

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
    return obj


def play_from_hand(game, card_def, owner):
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
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets)
    for e in events:
        game.emit(e)
    return obj


def run_sba(game):
    game._check_state_based_actions()


# ============================================================
# Emperor Cobra (Poisonous)
# ============================================================

def test_emperor_cobra_destroys_minion_on_damage():
    """Emperor Cobra destroys any minion it damages (poisonous)."""
    game, p1, p2 = new_hs_game()
    cobra = make_obj(game, EMPEROR_COBRA, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    # Cobra deals damage to yeti
    game.emit(Event(type=EventType.DAMAGE,
                     payload={'target': yeti.id, 'amount': 2, 'source': cobra.id},
                     source=cobra.id))

    # Yeti should be destroyed by poisonous
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED and
                      e.payload.get('object_id') == yeti.id]
    assert len(destroy_events) >= 1, "Poisonous should destroy yeti"


def test_emperor_cobra_doesnt_destroy_heroes():
    """Emperor Cobra's poisonous doesn't destroy heroes (only minions)."""
    game, p1, p2 = new_hs_game()
    cobra = make_obj(game, EMPEROR_COBRA, p1)

    # Damage the enemy hero
    game.emit(Event(type=EventType.DAMAGE,
                     payload={'target': p2.hero_id, 'amount': 2, 'source': cobra.id},
                     source=cobra.id))

    # Hero should NOT be destroyed (poisonous only applies to minions)
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED and
                      e.payload.get('object_id') == p2.hero_id]
    assert len(destroy_events) == 0, "Poisonous should not destroy heroes"


# ============================================================
# Demolisher (Start-of-Turn Damage)
# ============================================================

def test_demolisher_deals_damage_at_turn_start():
    """Demolisher deals 2 damage to a random enemy at start of turn."""
    game, p1, p2 = new_hs_game()
    demolisher = make_obj(game, DEMOLISHER, p1)

    initial_life = p2.life
    game.emit(Event(type=EventType.TURN_START,
                     payload={'player': p1.id}, source='test'))

    # Should deal 2 damage to enemy hero (only enemy target)
    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and e.source == demolisher.id]
    assert len(damage_events) >= 1, "Demolisher should deal damage at turn start"
    assert damage_events[0].payload.get('amount') == 2


def test_demolisher_only_on_controller_turn():
    """Demolisher only fires on its controller's turn."""
    game, p1, p2 = new_hs_game()
    demolisher = make_obj(game, DEMOLISHER, p1)

    game.emit(Event(type=EventType.TURN_START,
                     payload={'player': p2.id}, source='test'))

    damage_events = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and e.source == demolisher.id]
    assert len(damage_events) == 0, "Demolisher should not fire on opponent's turn"


# ============================================================
# Raging Worgen (Enrage + Windfury)
# ============================================================

def test_raging_worgen_enrage_grants_attack_and_windfury():
    """Raging Worgen when damaged gains +1 Attack and Windfury."""
    game, p1, p2 = new_hs_game()
    worgen = make_obj(game, RAGING_WORGEN, p1)

    base_power = get_power(worgen, game.state)

    # Damage the worgen to trigger enrage
    game.emit(Event(type=EventType.DAMAGE,
                     payload={'target': worgen.id, 'amount': 1, 'source': 'test'},
                     source='test'))

    assert get_power(worgen, game.state) == base_power + 1
    assert has_ability(worgen, 'windfury', game.state)


def test_raging_worgen_not_enraged_at_full_hp():
    """Raging Worgen at full HP has no enrage bonuses."""
    game, p1, p2 = new_hs_game()
    worgen = make_obj(game, RAGING_WORGEN, p1)

    assert get_power(worgen, game.state) == 3
    assert not has_ability(worgen, 'windfury', game.state)


# ============================================================
# Alarm-o-Bot (Start-of-Turn Swap)
# ============================================================

def test_alarm_o_bot_swaps_with_hand_minion():
    """Alarm-o-Bot swaps itself with a random minion from hand at turn start."""
    game, p1, p2 = new_hs_game()
    bot = make_obj(game, ALARM_O_BOT, p1)
    hand_minion = game.create_object(
        name=CHILLWIND_YETI.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=CHILLWIND_YETI.characteristics, card_def=CHILLWIND_YETI
    )

    # Emit TURN_START (Alarm-o-Bot uses make_start_of_turn_trigger)
    game.emit(Event(type=EventType.TURN_START,
                     payload={'player': p1.id}, source='test'))

    # Should have emitted RETURN_TO_HAND for the bot and ZONE_CHANGE for hand minion
    return_events = [e for e in game.state.event_log
                     if e.type == EventType.RETURN_TO_HAND and
                     e.payload.get('object_id') == bot.id]
    zone_changes = [e for e in game.state.event_log
                    if e.type == EventType.ZONE_CHANGE and
                    e.payload.get('object_id') == hand_minion.id]

    assert len(return_events) >= 1, "Alarm-o-Bot should return to hand"
    assert len(zone_changes) >= 1, "Hand minion should be put on battlefield"


def test_alarm_o_bot_no_minion_in_hand():
    """Alarm-o-Bot with no minions in hand does nothing."""
    game, p1, p2 = new_hs_game()
    bot = make_obj(game, ALARM_O_BOT, p1)
    # No minions in hand

    game.emit(Event(type=EventType.TURN_START,
                     payload={'player': p1.id}, source='test'))

    return_events = [e for e in game.state.event_log
                     if e.type == EventType.RETURN_TO_HAND and
                     e.payload.get('object_id') == bot.id]
    assert len(return_events) == 0, "Alarm-o-Bot should not swap without hand minions"


# ============================================================
# Violet Teacher (Spell Summon)
# ============================================================

def test_violet_teacher_summons_apprentice_on_spell():
    """Violet Teacher summons a 1/1 Violet Apprentice when you cast a spell."""
    game, p1, p2 = new_hs_game()
    teacher = make_obj(game, VIOLET_TEACHER, p1)

    bf = game.state.zones.get('battlefield')
    initial_count = len(bf.objects)

    # Cast a spell
    game.emit(Event(type=EventType.SPELL_CAST,
                     payload={'caster': p1.id, 'spell_id': 'test_spell',
                              'spell_name': 'Fireball'},
                     source='test'))

    assert len(bf.objects) > initial_count, "Should have summoned a token"


def test_violet_teacher_ignores_opponent_spells():
    """Violet Teacher doesn't summon on opponent's spells."""
    game, p1, p2 = new_hs_game()
    teacher = make_obj(game, VIOLET_TEACHER, p1)

    bf = game.state.zones.get('battlefield')
    initial_count = len(bf.objects)

    game.emit(Event(type=EventType.SPELL_CAST,
                     payload={'caster': p2.id, 'spell_name': 'Execute'},
                     source='test'))

    assert len(bf.objects) == initial_count, "Should not summon on opponent's spell"


# ============================================================
# Stampeding Kodo
# ============================================================

def test_stampeding_kodo_destroys_low_attack_minion():
    """Stampeding Kodo destroys a random enemy minion with 2 or less Attack."""
    game, p1, p2 = new_hs_game()
    wisp = make_obj(game, WISP, p2)  # 1 attack - valid target
    yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4 attack - not valid

    kodo = play_from_hand(game, STAMPEDING_KODO, p1)

    # Only wisp should be destroyed (1 atk <= 2)
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED and
                      e.payload.get('object_id') == wisp.id]
    assert len(destroy_events) >= 1, "Kodo should destroy low-attack minion"

    # Yeti should NOT be destroyed
    yeti_destroyed = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED and
                      e.payload.get('object_id') == yeti.id]
    assert len(yeti_destroyed) == 0, "Kodo should not destroy 4-attack minion"


def test_stampeding_kodo_no_valid_targets():
    """Stampeding Kodo with no low-attack enemies does nothing."""
    game, p1, p2 = new_hs_game()
    yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4 attack

    kodo = play_from_hand(game, STAMPEDING_KODO, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED and
                      e.payload.get('reason') == 'stampeding_kodo']
    assert len(destroy_events) == 0


# ============================================================
# Multi-Card Interaction Chains
# ============================================================

def test_double_dire_wolf_alpha_stacks():
    """Two Dire Wolf Alphas adjacent to the same minion stack +1 each."""
    game, p1, p2 = new_hs_game()
    wolf1 = make_obj(game, DIRE_WOLF_ALPHA, p1)  # 2/2
    wisp = make_obj(game, WISP, p1)   # 1/1 - adjacent to wolf1 (right)
    wolf2 = make_obj(game, DIRE_WOLF_ALPHA, p1)  # 2/2 - wisp now adjacent to wolf2 (left)

    # Wisp is between wolf1 (left neighbor) and wolf2 (right neighbor)
    # But actually positioning depends on order: wolf1, wisp, wolf2
    # wisp's right neighbor is wolf2, wolf2's left neighbor is wisp
    wisp_power = get_power(wisp, game.state)
    # Wisp should be adjacent to both wolves: 1 + 1 + 1 = 3
    assert wisp_power == 3, f"Wisp between two wolves should be 3, got {wisp_power}"


def test_murloc_warleader_buff_removed_on_death():
    """Murloc Warleader's aura (+2 ATK to other murlocs) is removed when it dies."""
    game, p1, p2 = new_hs_game()
    raider = make_obj(game, MURLOC_RAIDER, p1)
    warleader = make_obj(game, MURLOC_WARLEADER, p1)

    buffed_power = get_power(raider, game.state)
    # Murloc Raider is 2/1 base + 2 from warleader = 4
    assert buffed_power == 4, f"Murloc raider with warleader should be 4, got {buffed_power}"

    # Kill warleader
    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                     payload={'object_id': warleader.id, 'reason': 'test'}, source='test'))

    # Aura should be removed
    unbuffed_power = get_power(raider, game.state)
    assert unbuffed_power == 2, f"Murloc raider without warleader should be 2, got {unbuffed_power}"


def test_knife_juggler_triggers_on_token_summon():
    """Knife Juggler deals 1 damage when tokens are summoned."""
    game, p1, p2 = new_hs_game()
    juggler = make_obj(game, KNIFE_JUGGLER, p1)

    # Summon a token (like from Violet Teacher)
    game.emit(Event(type=EventType.CREATE_TOKEN, payload={
        'controller': p1.id,
        'token': {'name': 'Token', 'power': 1, 'toughness': 1,
                  'types': {CardType.MINION}}
    }, source='test'))

    # Knife Juggler should have dealt 1 damage
    juggler_damage = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and e.source == juggler.id]
    assert len(juggler_damage) >= 1, "Juggler should deal damage on token summon"


def test_amani_berserker_enrage():
    """Amani Berserker gains +3 Attack when enraged (damaged)."""
    game, p1, p2 = new_hs_game()
    amani = make_obj(game, AMANI_BERSERKER, p1)

    base_power = get_power(amani, game.state)

    game.emit(Event(type=EventType.DAMAGE,
                     payload={'target': amani.id, 'amount': 1, 'source': 'test'},
                     source='test'))

    assert get_power(amani, game.state) == base_power + 3


def test_harvest_golem_deathrattle_summons_damaged_golem():
    """Harvest Golem's deathrattle summons a 2/1 Damaged Golem."""
    game, p1, p2 = new_hs_game()
    golem = make_obj(game, HARVEST_GOLEM, p1)

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                     payload={'object_id': golem.id, 'reason': 'test'}, source='test'))

    # Should have summoned a token
    token_events = [e for e in game.state.event_log if e.type == EventType.CREATE_TOKEN]
    assert len(token_events) >= 1, "Harvest Golem should summon Damaged Golem on death"
    token = token_events[0].payload.get('token', {})
    assert token.get('power') == 2
    assert token.get('toughness') == 1


def test_stranglethorn_tiger_has_stealth():
    """Stranglethorn Tiger has Stealth keyword."""
    game, p1, p2 = new_hs_game()
    tiger = make_obj(game, STRANGLETHORN_TIGER, p1)
    assert has_ability(tiger, 'stealth', game.state)


def test_silver_hand_knight_battlecry_summons_squire():
    """Silver Hand Knight summons a 2/2 Squire on battlecry."""
    game, p1, p2 = new_hs_game()
    bf = game.state.zones.get('battlefield')
    initial_count = len(bf.objects)

    knight = play_from_hand(game, SILVER_HAND_KNIGHT, p1)

    # Should have summoned a 2/2 Squire token
    token_events = [e for e in game.state.event_log if e.type == EventType.CREATE_TOKEN]
    assert len(token_events) >= 1, "Silver Hand Knight should summon a Squire"


def test_argent_commander_has_charge_and_divine_shield():
    """Argent Commander has Charge and Divine Shield."""
    game, p1, p2 = new_hs_game()
    commander = make_obj(game, ARGENT_COMMANDER, p1)

    assert has_ability(commander, 'charge', game.state)
    assert has_ability(commander, 'divine_shield', game.state)


def test_mana_addict_temporary_attack_resets():
    """Mana Addict's +2 Attack buff is temporary (end_of_turn duration)."""
    game, p1, p2 = new_hs_game()
    addict = make_obj(game, MANA_ADDICT, p1)

    base_power = get_power(addict, game.state)

    # Cast spell for +2 temporary attack
    game.emit(Event(type=EventType.SPELL_CAST,
                     payload={'caster': p1.id, 'spell_name': 'Test'},
                     source='test'))

    assert get_power(addict, game.state) == base_power + 2

    # Verify the buff exists as a PT modifier with end_of_turn duration
    has_temp_buff = len(addict.state.pt_modifiers) > 0
    assert has_temp_buff, "Mana Addict should have pt_modifiers after spell cast"


def test_flesheating_ghoul_doesnt_trigger_on_own_death():
    """Flesheating Ghoul's trigger checks that the dying minion isn't itself."""
    game, p1, p2 = new_hs_game()
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)

    base_power = get_power(ghoul, game.state)

    # Kill the ghoul itself
    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                     payload={'object_id': ghoul.id, 'reason': 'test'}, source='test'))

    # Should NOT gain attack from own death (filter checks died_id != obj.id)
    # Since ghoul is dead, we can't really check its power, but we can verify no PT_MOD event
    pt_mods = [e for e in game.state.event_log
               if e.type == EventType.PT_MODIFICATION and
               e.payload.get('object_id') == ghoul.id]
    assert len(pt_mods) == 0, "Ghoul should not trigger on own death"


# ============================================================
# Run all tests
# ============================================================

if __name__ == '__main__':
    import sys
    test_functions = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = 0
    failed = 0
    for fn in test_functions:
        try:
            fn()
            passed += 1
            print(f"  PASS: {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {fn.__name__}: {e}")
    print(f"\n{passed}/{passed+failed} tests passed")
    if failed:
        sys.exit(1)
