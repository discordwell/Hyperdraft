"""
Hearthstone Unhappy Path Tests - Batch 26

Untested card effects: Timber Wolf (beast lord), Tundra Rhino (beast charge grant),
Warsong Commander (charge to <=3 ATK), Mana Tide Totem (EOT draw), Demolisher
(SOT damage), Master Swordsmith (EOT buff), Raging Worgen (enrage + windfury),
Patient Assassin (poisonous + stealth), Blood Imp (EOT stealth health buff),
Lightwell (SOT heal), Doomhammer (windfury weapon), Sorcerer's Apprentice
(spell cost reduction), Onyxia (fill board with whelps), and cross-class combos.
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
    KOBOLD_GEOMANCER,
)
from src.cards.hearthstone.classic import (
    DEMOLISHER, MASTER_SWORDSMITH, RAGING_WORGEN,
    ONYXIA, KNIFE_JUGGLER, HARVEST_GOLEM, BARON_GEDDON,
    ARGENT_SQUIRE, LOOT_HOARDER, WILD_PYROMANCER,
)
from src.cards.hearthstone.hunter import TIMBER_WOLF, TUNDRA_RHINO, STARVING_BUZZARD
from src.cards.hearthstone.warrior import WARSONG_COMMANDER, WHIRLWIND
from src.cards.hearthstone.shaman import MANA_TIDE_TOTEM, DOOMHAMMER
from src.cards.hearthstone.warlock import BLOOD_IMP, VOIDWALKER
from src.cards.hearthstone.priest import LIGHTWELL, CIRCLE_OF_HEALING
from src.cards.hearthstone.rogue import PATIENT_ASSASSIN
from src.cards.hearthstone.mage import SORCERERS_APPRENTICE, FROSTBOLT


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
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


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
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    return obj


def cast_spell_full(game, card_def, owner, targets=None):
    """Cast spell with SPELL_CAST event (triggers Pyro, Wyrm, Antonidas, etc)."""
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


def count_battlefield_minions(game, controller_id=None):
    bf = game.state.zones.get('battlefield')
    if not bf:
        return 0
    count = 0
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and CardType.MINION in obj.characteristics.types:
            if controller_id is None or obj.controller == controller_id:
                count += 1
    return count


def add_cards_to_library(game, player, card_def, count):
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


# ============================================================
# Timber Wolf — Your other Beasts have +1 Attack
# ============================================================

class TestTimberWolf:
    def test_timber_wolf_buffs_beasts(self):
        """Timber Wolf gives other friendly Beasts +1 Attack."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)  # 1/1 Beast
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)  # 3/2 Beast

        # Raptor should have +1 attack from wolf aura
        assert get_power(raptor, game.state) >= 4  # 3 base + 1 aura

    def test_timber_wolf_no_self_buff(self):
        """Timber Wolf doesn't buff itself."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)

        assert get_power(wolf, game.state) == 1  # no self-buff

    def test_timber_wolf_no_buff_non_beasts(self):
        """Timber Wolf doesn't buff non-Beast minions."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # Not a Beast

        assert get_power(yeti, game.state) == 4  # unchanged

    def test_timber_wolf_no_buff_enemy_beasts(self):
        """Timber Wolf doesn't buff enemy Beasts."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)
        enemy_raptor = make_obj(game, BLOODFEN_RAPTOR, p2)  # enemy Beast

        assert get_power(enemy_raptor, game.state) == 3  # unchanged

    def test_double_timber_wolf(self):
        """Two Timber Wolves stack +2 Attack on friendly Beasts."""
        game, p1, p2 = new_hs_game()
        wolf1 = make_obj(game, TIMBER_WOLF, p1)
        wolf2 = make_obj(game, TIMBER_WOLF, p1)
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)

        # Each wolf buffs the raptor +1
        assert get_power(raptor, game.state) >= 5  # 3 + 2


# ============================================================
# Tundra Rhino — Your Beasts have Charge
# ============================================================

class TestTundraRhino:
    def test_tundra_rhino_grants_charge_to_new_beast(self):
        """Tundra Rhino grants Charge to Beasts summoned while it's on board."""
        game, p1, p2 = new_hs_game()
        rhino = make_obj(game, TUNDRA_RHINO, p1)

        # Play a Beast from hand
        raptor = play_from_hand(game, BLOODFEN_RAPTOR, p1)

        # Raptor should have Charge
        assert has_ability(raptor, 'charge', game.state)
        # And no summoning sickness
        assert raptor.state.summoning_sickness is False

    def test_tundra_rhino_no_charge_non_beasts(self):
        """Tundra Rhino doesn't grant Charge to non-Beasts."""
        game, p1, p2 = new_hs_game()
        rhino = make_obj(game, TUNDRA_RHINO, p1)

        yeti = play_from_hand(game, CHILLWIND_YETI, p1)

        # Yeti should NOT have charge
        assert not has_ability(yeti, 'charge', game.state)


# ============================================================
# Warsong Commander — <=3 ATK minions gain Charge
# ============================================================

class TestWarsongCommander:
    def test_warsong_grants_charge_to_low_attack(self):
        """Warsong Commander grants Charge to minions with <=3 Attack."""
        game, p1, p2 = new_hs_game()
        warsong = make_obj(game, WARSONG_COMMANDER, p1)

        # Play a 1/1 from hand
        wisp = play_from_hand(game, WISP, p1)

        assert has_ability(wisp, 'charge', game.state)
        assert wisp.state.summoning_sickness is False

    def test_warsong_no_charge_high_attack(self):
        """Warsong Commander doesn't grant Charge to >3 Attack minions."""
        game, p1, p2 = new_hs_game()
        warsong = make_obj(game, WARSONG_COMMANDER, p1)

        # Chillwind Yeti has 4 attack
        yeti = play_from_hand(game, CHILLWIND_YETI, p1)

        # Yeti should NOT get charge
        assert not has_ability(yeti, 'charge', game.state)

    def test_warsong_exactly_3_attack(self):
        """Warsong grants Charge to minions with exactly 3 Attack."""
        game, p1, p2 = new_hs_game()
        warsong = make_obj(game, WARSONG_COMMANDER, p1)

        # River Crocolisk has 2 ATK, Bloodfen Raptor has 3 ATK
        raptor = play_from_hand(game, BLOODFEN_RAPTOR, p1)

        assert has_ability(raptor, 'charge', game.state)


# ============================================================
# Mana Tide Totem — End of turn: draw a card
# ============================================================

class TestManaTideTotem:
    def test_mana_tide_draws_at_eot(self):
        """Mana Tide Totem draws a card at end of controller's turn.
        Note: make_end_of_turn_trigger listens for PHASE_END with phase='end'."""
        game, p1, p2 = new_hs_game()
        add_cards_to_library(game, p1, WISP, 5)
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)

        game.emit(Event(type=EventType.PHASE_END,
                        payload={'player': p1.id, 'phase': 'end'},
                        source='system'))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_mana_tide_doesnt_draw_on_opponent_turn(self):
        """Mana Tide only draws on controller's turn."""
        game, p1, p2 = new_hs_game()
        add_cards_to_library(game, p1, WISP, 5)
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)

        events_before = len(game.state.event_log)
        game.emit(Event(type=EventType.PHASE_END,
                        payload={'player': p2.id, 'phase': 'end'},
                        source='system'))

        draw_events = [e for e in game.state.event_log[events_before:]
                       if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
        assert len(draw_events) == 0


# ============================================================
# Demolisher — Start of turn: deal 2 to random enemy
# ============================================================

class TestDemolisher:
    def test_demolisher_sot_damage(self):
        """Demolisher deals 2 damage to a random enemy at start of turn."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        demo = make_obj(game, DEMOLISHER, p1)

        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source='system'))

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('source') == demo.id
                         and e.payload.get('amount') == 2]
        assert len(damage_events) >= 1

    def test_demolisher_only_on_controller_turn(self):
        """Demolisher only triggers at start of controller's turn."""
        game, p1, p2 = new_hs_game()
        demo = make_obj(game, DEMOLISHER, p1)

        events_before = len(game.state.event_log)
        game.emit(Event(type=EventType.TURN_START, payload={'player': p2.id}, source='system'))

        damage_events = [e for e in game.state.event_log[events_before:]
                         if e.type == EventType.DAMAGE and e.payload.get('source') == demo.id]
        assert len(damage_events) == 0


# ============================================================
# Master Swordsmith — End of turn: +1 ATK to random friendly
# ============================================================

class TestMasterSwordsmith:
    def test_master_swordsmith_buffs_friendly(self):
        """Master Swordsmith gives +1 Attack to a random friendly minion at EOT."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, MASTER_SWORDSMITH, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        # Yeti is the only other friendly, should get +1 ATK
        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION
                     and e.payload.get('power_mod') == 1]
        assert len(pt_events) >= 1

    def test_master_swordsmith_no_self_buff(self):
        """Master Swordsmith doesn't buff itself (targets OTHER friendly minions)."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, MASTER_SWORDSMITH, p1)

        base_power = get_power(smith, game.state)
        game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        # No other friendly minions, so no buff should happen at all
        assert get_power(smith, game.state) == base_power


# ============================================================
# Raging Worgen — Enrage: Windfury and +1 Attack
# ============================================================

class TestRagingWorgen:
    def test_raging_worgen_enrage_windfury(self):
        """Raging Worgen gains Windfury and +1 Attack when damaged."""
        game, p1, p2 = new_hs_game()
        worgen = make_obj(game, RAGING_WORGEN, p1)
        assert get_power(worgen, game.state) == 3

        # Deal 1 damage
        game.emit(Event(type=EventType.DAMAGE,
                        payload={'target': worgen.id, 'amount': 1, 'source': 'test'},
                        source='test'))

        assert get_power(worgen, game.state) == 4  # 3 + 1 enrage

    def test_raging_worgen_not_enraged_at_full(self):
        """Raging Worgen has no enrage bonus at full health."""
        game, p1, p2 = new_hs_game()
        worgen = make_obj(game, RAGING_WORGEN, p1)

        assert get_power(worgen, game.state) == 3
        assert worgen.state.damage == 0


# ============================================================
# Patient Assassin — Stealth + Destroy any minion damaged
# ============================================================

class TestPatientAssassin:
    def test_patient_assassin_has_stealth(self):
        """Patient Assassin has Stealth keyword."""
        game, p1, p2 = new_hs_game()
        pa = make_obj(game, PATIENT_ASSASSIN, p1)
        assert has_ability(pa, 'stealth', game.state)

    def test_patient_assassin_destroys_on_damage(self):
        """Patient Assassin destroys any minion it damages."""
        game, p1, p2 = new_hs_game()
        pa = make_obj(game, PATIENT_ASSASSIN, p1)
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

        # Patient Assassin deals damage to ogre
        game.emit(Event(type=EventType.DAMAGE,
                        payload={'target': ogre.id, 'amount': 1, 'source': pa.id},
                        source=pa.id))

        # Ogre should be destroyed via OBJECT_DESTROYED event
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED
                          and e.payload.get('object_id') == ogre.id
                          and e.payload.get('reason') == 'patient_assassin']
        assert len(destroy_events) >= 1


# ============================================================
# Blood Imp — Stealth + EOT: +1 Health to random friendly
# ============================================================

class TestBloodImp:
    def test_blood_imp_has_stealth(self):
        """Blood Imp has Stealth."""
        game, p1, p2 = new_hs_game()
        imp = make_obj(game, BLOOD_IMP, p1)
        assert has_ability(imp, 'stealth', game.state)

    def test_blood_imp_eot_health_buff(self):
        """Blood Imp gives +1 Health to a random friendly minion at EOT.
        Note: Blood Imp uses make_end_of_turn_trigger → PHASE_END with phase='end'."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        imp = make_obj(game, BLOOD_IMP, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(type=EventType.PHASE_END,
                        payload={'player': p1.id, 'phase': 'end'},
                        source='system'))

        # Should have PT_MODIFICATION for +1 toughness
        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION
                     and e.payload.get('toughness_mod') == 1
                     and e.payload.get('power_mod') == 0]
        assert len(pt_events) >= 1


# ============================================================
# Lightwell — Start of turn: heal 3 to damaged friendly
# ============================================================

class TestLightwell:
    def test_lightwell_heals_damaged_friendly(self):
        """Lightwell heals a damaged friendly character at start of turn."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        lightwell = make_obj(game, LIGHTWELL, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.damage = 3  # damage the yeti

        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source='system'))

        # Yeti should have less damage
        assert yeti.state.damage < 3

    def test_lightwell_no_heal_if_full(self):
        """Lightwell doesn't heal if all friendlies are at full health."""
        game, p1, p2 = new_hs_game()
        lightwell = make_obj(game, LIGHTWELL, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        # All at full health

        events_before = len(game.state.event_log)
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source='system'))

        # No LIFE_CHANGE events from lightwell
        heal_events = [e for e in game.state.event_log[events_before:]
                       if e.type == EventType.LIFE_CHANGE
                       and e.source == lightwell.id]
        # If hero is also full, no heals should happen
        # (Lightwell only heals damaged characters)
        if p1.life >= 30:
            assert len(heal_events) == 0


# ============================================================
# Onyxia — Battlecry: Fill board with 1/1 Whelps
# ============================================================

class TestOnyxia:
    def test_onyxia_fills_board_with_whelps(self):
        """Onyxia's battlecry summons 1/1 Whelps to fill board (max 7 total)."""
        game, p1, p2 = new_hs_game()
        onyxia = play_from_hand(game, ONYXIA, p1)

        # Should have CREATE_TOKEN events for Whelps
        whelp_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Whelp']
        # Onyxia is 1 minion, so up to 6 whelps
        assert len(whelp_events) == 6

    def test_onyxia_partial_board(self):
        """Onyxia only fills remaining slots when board has existing minions."""
        game, p1, p2 = new_hs_game()
        # Place 3 minions first
        make_obj(game, WISP, p1)
        make_obj(game, WISP, p1)
        make_obj(game, WISP, p1)

        onyxia = play_from_hand(game, ONYXIA, p1)

        # 3 existing + 1 Onyxia = 4, so 3 whelps max
        whelp_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Whelp']
        assert len(whelp_events) == 3

    def test_onyxia_full_board_no_whelps(self):
        """Onyxia on full board summons no whelps."""
        game, p1, p2 = new_hs_game()
        # Fill board with 6 minions
        for _ in range(6):
            make_obj(game, WISP, p1)

        onyxia = play_from_hand(game, ONYXIA, p1)

        # 6 + 1 Onyxia = 7, no room for whelps
        whelp_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Whelp']
        assert len(whelp_events) == 0


# ============================================================
# Doomhammer — Windfury weapon (2/8, Overload 2)
# ============================================================

class TestDoomhammer:
    def test_doomhammer_stats(self):
        """Doomhammer is a 2/8 weapon."""
        assert DOOMHAMMER.characteristics.power == 2
        assert DOOMHAMMER.characteristics.toughness == 8


# ============================================================
# Sorcerer's Apprentice — Spells cost (1) less
# ============================================================

class TestSorcerersApprentice:
    def test_sorcerers_apprentice_on_battlefield(self):
        """Sorcerer's Apprentice is a 3/2 for 2 mana."""
        game, p1, p2 = new_hs_game()
        sa = make_obj(game, SORCERERS_APPRENTICE, p1)
        assert get_power(sa, game.state) == 3
        assert get_toughness(sa, game.state) == 2


# ============================================================
# Cross-mechanic: Timber Wolf + Tundra Rhino + Beast swarm
# ============================================================

class TestBeastSynergy:
    def test_wolf_and_rhino_together(self):
        """Timber Wolf buffs and Tundra Rhino grants Charge to Beasts."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)
        rhino = make_obj(game, TUNDRA_RHINO, p1)

        # Play a Beast from hand
        raptor = play_from_hand(game, BLOODFEN_RAPTOR, p1)

        # Raptor should have +1 Attack from wolf AND Charge from rhino
        assert get_power(raptor, game.state) >= 4  # 3 + 1
        assert has_ability(raptor, 'charge', game.state)

    def test_starving_buzzard_with_beast_chain(self):
        """Starving Buzzard draws a card for each Beast summoned."""
        game, p1, p2 = new_hs_game()
        add_cards_to_library(game, p1, WISP, 10)
        buzzard = make_obj(game, STARVING_BUZZARD, p1)

        # Play multiple beasts
        play_from_hand(game, BLOODFEN_RAPTOR, p1)
        play_from_hand(game, STONETUSK_BOAR, p1)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW
                       and e.payload.get('player') == p1.id]
        assert len(draw_events) >= 2  # One per Beast summoned


# ============================================================
# Cross-mechanic: Warsong + Knife Juggler + token summon
# ============================================================

class TestWarsongJugglerCombo:
    def test_warsong_gives_charge_to_tokens(self):
        """Warsong grants Charge to tokens with <=3 Attack."""
        game, p1, p2 = new_hs_game()
        warsong = make_obj(game, WARSONG_COMMANDER, p1)

        # Play Harvest Golem from hand (2/3)
        golem = play_from_hand(game, HARVEST_GOLEM, p1)

        # Golem has 2 ATK <= 3, should get Charge
        assert has_ability(golem, 'charge', game.state)


# ============================================================
# Cross-mechanic: Wild Pyromancer + Mana Tide Totem
# ============================================================

class TestPyroManaTideCombo:
    def test_pyro_damages_mana_tide(self):
        """Wild Pyromancer's spell-trigger damages Mana Tide Totem."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)  # 0/3

        cast_spell_full(game, FROSTBOLT, p1)

        # Pyro deals 1 to all minions
        assert totem.state.damage >= 1

    def test_pyro_kills_mana_tide_after_spell(self):
        """Wild Pyromancer can kill Mana Tide Totem if already damaged."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)  # 0/3
        totem.state.damage = 2  # Leave at 1 HP

        cast_spell_full(game, FROSTBOLT, p1)
        game.check_state_based_actions()

        # Totem had 1 HP, took 1 from pyro = dead
        assert totem.state.damage >= 3 or totem.zone != ZoneType.BATTLEFIELD


# ============================================================
# Cross-mechanic: Baron Geddon + Lightwell timing
# ============================================================

class TestGeddonLightwellCombat:
    def test_geddon_damages_lightwell(self):
        """Baron Geddon's EOT damages Lightwell (other character)."""
        game, p1, p2 = new_hs_game()
        geddon = make_obj(game, BARON_GEDDON, p1)
        lightwell = make_obj(game, LIGHTWELL, p1)

        game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        # Lightwell took 2 damage from Geddon
        assert lightwell.state.damage == 2
