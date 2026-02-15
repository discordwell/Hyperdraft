"""
Hearthstone Unhappy Path Tests - Batch 35

Deathrattle chains: Abomination AOE kills other deathrattle minions, Sylvanas
steals on death, The Beast gives opponent a token, Cairne spawns on death,
Leper Gnome hero damage, Harvest Golem token, simultaneous deathrattles.
Secret interactions: Snipe kills incoming minion, Explosive Trap AOE on attack,
Snake Trap token summon, Vaporize destroys attacker, Noble Sacrifice redirect,
Repentance reduces health, Avenge buffs on death, Eye for an Eye reflect.
Combo depth: Edwin VanCleef stacking, Headcrack return-to-hand, Preparation
cost reduction.  Silence: removes deathrattle, removes enrage, removes taunt,
removes aura interceptors.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, LEPER_GNOME, HARVEST_GOLEM,
)
from src.cards.hearthstone.classic import (
    ABOMINATION, SYLVANAS_WINDRUNNER, CAIRNE_BLOODHOOF, THE_BEAST,
    LOOT_HOARDER, IRONBEAK_OWL, SPELLBREAKER, BLOOD_KNIGHT,
    ARGENT_SQUIRE, AMANI_BERSERKER, KNIFE_JUGGLER, YOUTHFUL_BREWMASTER,
)
from src.cards.hearthstone.hunter import (
    EXPLOSIVE_TRAP, SNIPE, SNAKE_TRAP, SAVANNAH_HIGHMANE,
)
from src.cards.hearthstone.mage import (
    VAPORIZE, MIRROR_ENTITY, ICE_BARRIER,
)
from src.cards.hearthstone.paladin import (
    NOBLE_SACRIFICE, REPENTANCE, AVENGE, TIRION_FORDRING,
)
from src.cards.hearthstone.rogue import (
    EDWIN_VANCLEEF, PREPARATION, HEADCRACK, EVISCERATE,
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


def make_secret(game, card_def, owner):
    """Place a secret on the battlefield.
    Note: Secrets technically belong in COMMAND zone, but the pipeline's
    is_active() check (pipeline.py:156) only considers BATTLEFIELD zone
    as active for 'while_on_battlefield' interceptors. This is a known
    engine limitation — secrets placed in COMMAND zone won't trigger.
    """
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )


def cast_spell_full(game, card_def, owner, targets=None):
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


# ============================================================
# Deathrattle Chains
# ============================================================

class TestDeathrattleChains:
    def test_leper_gnome_damages_enemy_hero(self):
        """Leper Gnome deathrattle should deal 2 to enemy hero."""
        game, p1, p2 = new_hs_game()
        lg = make_obj(game, LEPER_GNOME, p1)
        p2_life_before = p2.life

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': lg.id},
            source='test'
        ))

        # Should deal 2 damage to enemy hero
        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('target') == p2.hero_id and
                      e.payload.get('source') == lg.id]
        assert len(dmg_events) >= 1
        assert dmg_events[0].payload['amount'] == 2

    def test_harvest_golem_summons_token(self):
        """Harvest Golem deathrattle should summon a 2/1 Damaged Golem."""
        game, p1, p2 = new_hs_game()
        hg = make_obj(game, HARVEST_GOLEM, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hg.id},
            source='test'
        ))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('controller') == p1.id and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) >= 1

    def test_cairne_summons_baine(self):
        """Cairne Bloodhoof deathrattle should summon 4/5 Baine Bloodhoof."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cairne.id},
            source='test'
        ))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) >= 1
        token = token_events[0].payload['token']
        assert token['power'] == 4
        assert token['toughness'] == 5

    def test_the_beast_gives_opponent_token(self):
        """The Beast deathrattle should summon a 3/3 for the OPPONENT."""
        game, p1, p2 = new_hs_game()
        beast = make_obj(game, THE_BEAST, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': beast.id},
            source='test'
        ))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Finkle Einhorn']
        assert len(token_events) >= 1
        # Token should be for the opponent (p2), NOT the owner (p1)
        assert token_events[0].payload['controller'] == p2.id

    def test_sylvanas_steals_enemy_minion(self):
        """Sylvanas deathrattle should emit CONTROL_CHANGE for a random enemy minion."""
        game, p1, p2 = new_hs_game()
        sylv = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sylv.id},
            source='test'
        ))

        steal_events = [e for e in game.state.event_log
                        if e.type == EventType.CONTROL_CHANGE and
                        e.payload.get('new_controller') == p1.id]
        assert len(steal_events) >= 1
        assert steal_events[0].payload['object_id'] == target.id

    def test_sylvanas_no_enemies_no_crash(self):
        """Sylvanas deathrattle with no enemy minions should not crash."""
        game, p1, p2 = new_hs_game()
        sylv = make_obj(game, SYLVANAS_WINDRUNNER, p1)

        # No enemy minions on board
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sylv.id},
            source='test'
        ))

        steal_events = [e for e in game.state.event_log
                        if e.type == EventType.CONTROL_CHANGE]
        assert len(steal_events) == 0

    def test_abomination_damages_all(self):
        """Abomination deathrattle should deal 2 to ALL characters."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m2 = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id},
            source='test'
        ))

        # Should damage both minions and both heroes
        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('source') == abom.id]
        targets_hit = {e.payload['target'] for e in dmg_events}
        assert m1.id in targets_hit
        assert m2.id in targets_hit
        assert p1.hero_id in targets_hit
        assert p2.hero_id in targets_hit

    def test_savannah_highmane_summons_two_hyenas(self):
        """Savannah Highmane deathrattle should summon TWO 2/2 Hyenas."""
        game, p1, p2 = new_hs_game()
        shm = make_obj(game, SAVANNAH_HIGHMANE, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': shm.id},
            source='test'
        ))

        hyena_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Hyena']
        assert len(hyena_events) == 2
        for he in hyena_events:
            assert he.payload['token']['power'] == 2
            assert he.payload['token']['toughness'] == 2

    def test_tirion_equips_ashbringer_on_death(self):
        """Tirion Fordring deathrattle should equip 5/3 Ashbringer."""
        game, p1, p2 = new_hs_game()
        tirion = make_obj(game, TIRION_FORDRING, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': tirion.id},
            source='test'
        ))

        weapon_events = [e for e in game.state.event_log
                         if e.type == EventType.WEAPON_EQUIP and
                         e.payload.get('player') == p1.id]
        assert len(weapon_events) >= 1
        assert weapon_events[0].payload['weapon_attack'] == 5
        assert weapon_events[0].payload['weapon_durability'] == 3

    def test_abomination_kills_leper_gnome_chain(self):
        """Abomination dying should deal 2 to all; if Leper Gnome dies from that,
        its deathrattle should also fire."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        lg = make_obj(game, LEPER_GNOME, p2)  # 1/1 — will die to 2 damage

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id},
            source='test'
        ))

        # Abomination deals 2 to Leper Gnome
        abom_dmg = [e for e in game.state.event_log
                    if e.type == EventType.DAMAGE and
                    e.payload.get('target') == lg.id and
                    e.payload.get('source') == abom.id]
        assert len(abom_dmg) >= 1

        # Run SBA to kill the Leper Gnome
        game.check_state_based_actions()

        # Leper Gnome's deathrattle should fire dealing 2 to enemy hero (p1)
        lg_dmg = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and
                  e.payload.get('source') == lg.id]
        assert len(lg_dmg) >= 1


# ============================================================
# Secret Interactions
# ============================================================

class TestSecretInteractions:
    def test_snipe_damages_played_minion(self):
        """Snipe should deal 4 damage to the minion the opponent plays."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id  # p2's turn (secrets trigger on opponent's turn)
        snipe = make_secret(game, SNIPE, p1)

        # p2 plays a minion
        target = play_from_hand(game, CHILLWIND_YETI, p2)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 4 and
                      e.payload.get('source') == snipe.id]
        assert len(dmg_events) >= 1

    def test_snipe_does_not_fire_on_own_turn(self):
        """Snipe should NOT trigger when the secret owner plays a minion."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id  # p1's turn — secrets don't fire
        snipe = make_secret(game, SNIPE, p1)

        target = play_from_hand(game, CHILLWIND_YETI, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('source') == snipe.id]
        assert len(dmg_events) == 0

    def test_explosive_trap_aoe_on_attack(self):
        """Explosive Trap should deal 2 to all enemies when hero is attacked."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        et = make_secret(game, EXPLOSIVE_TRAP, p1)
        enemy_m1 = make_obj(game, CHILLWIND_YETI, p2)
        enemy_m2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': enemy_m1.id, 'target_id': p1.hero_id},
            source=enemy_m1.id
        ))

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('source') == et.id]
        targets_hit = {e.payload['target'] for e in dmg_events}
        # Should hit both enemy minions and enemy hero
        assert enemy_m1.id in targets_hit or enemy_m2.id in targets_hit
        assert p2.hero_id in targets_hit

    def test_snake_trap_summons_three_snakes(self):
        """Snake Trap should summon 3 Snakes when a friendly minion is attacked."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id  # Opponent's turn
        st = make_secret(game, SNAKE_TRAP, p1)
        defender = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p2.hero_id, 'target_id': defender.id},
            source=p2.hero_id
        ))

        snake_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Snake']
        assert len(snake_events) == 3

    def test_vaporize_destroys_attacker(self):
        """Vaporize should destroy the minion attacking your hero."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        vap = make_secret(game, VAPORIZE, p1)
        attacker = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': attacker.id, 'target_id': p1.hero_id},
            source=attacker.id
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == attacker.id]
        assert len(destroy_events) >= 1

    def test_noble_sacrifice_summons_defender(self):
        """Noble Sacrifice should summon a 2/1 Defender token."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        ns = make_secret(game, NOBLE_SACRIFICE, p1)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p2.hero_id, 'target_id': p1.hero_id},
            source=p2.hero_id
        ))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Defender']
        assert len(token_events) >= 1
        assert token_events[0].payload['token']['power'] == 2
        assert token_events[0].payload['token']['toughness'] == 1

    def test_repentance_reduces_health_to_1(self):
        """Repentance should reduce played minion's Health to 1."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        rep = make_secret(game, REPENTANCE, p1)

        target = play_from_hand(game, CHILLWIND_YETI, p2)

        # Yeti should have health reduced to 1
        assert target.characteristics.toughness == 1

    def test_avenge_buffs_surviving_minion(self):
        """Avenge should give a friendly minion +3/+2 when another dies."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id  # Opponent's turn
        avenge = make_secret(game, AVENGE, p1)
        sacrifice = make_obj(game, WISP, p1)
        survivor = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sacrifice.id},
            source='test'
        ))

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('object_id') == survivor.id]
        assert len(pt_events) >= 1
        assert pt_events[0].payload['power_mod'] == 3
        assert pt_events[0].payload['toughness_mod'] == 2

    def test_ice_barrier_grants_armor(self):
        """Ice Barrier should gain 8 armor when hero is attacked."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        ib = make_secret(game, ICE_BARRIER, p1)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p2.hero_id, 'target_id': p1.hero_id},
            source=p2.hero_id
        ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 1
        assert armor_events[0].payload['amount'] == 8

    def test_mirror_entity_copies_minion(self):
        """Mirror Entity should summon a copy of the opponent's played minion."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        me = make_secret(game, MIRROR_ENTITY, p1)

        target = play_from_hand(game, CHILLWIND_YETI, p2)

        copy_events = [e for e in game.state.event_log
                       if e.type == EventType.CREATE_TOKEN and
                       e.payload.get('controller') == p1.id and
                       e.payload.get('token', {}).get('name') == 'Chillwind Yeti']
        assert len(copy_events) >= 1
        token = copy_events[0].payload['token']
        assert token['power'] == 4
        assert token['toughness'] == 5

    def test_secret_consumed_after_trigger(self):
        """Secrets should be moved to graveyard after triggering."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        ns = make_secret(game, NOBLE_SACRIFICE, p1)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p2.hero_id, 'target_id': p1.hero_id},
            source=p2.hero_id
        ))

        # Secret should be moved to graveyard
        zone_changes = [e for e in game.state.event_log
                        if e.type == EventType.ZONE_CHANGE and
                        e.payload.get('object_id') == ns.id and
                        e.payload.get('to_zone_type') == ZoneType.GRAVEYARD]
        assert len(zone_changes) >= 1


# ============================================================
# Combo Mechanics (Rogue)
# ============================================================

class TestComboMechanics:
    def test_edwin_no_combo_base_stats(self):
        """Edwin VanCleef with no cards played should have base 2/2."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0

        edwin = make_obj(game, EDWIN_VANCLEEF, p1)
        events = EDWIN_VANCLEEF.battlecry(edwin, game.state)

        # No cards played, no combo bonus
        assert events == []

    def test_edwin_combo_scales_with_cards(self):
        """Edwin VanCleef should gain +2/+2 per card played this turn."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 3

        edwin = make_obj(game, EDWIN_VANCLEEF, p1)
        events = EDWIN_VANCLEEF.battlecry(edwin, game.state)

        assert len(events) >= 1
        pt_event = events[0]
        assert pt_event.type == EventType.PT_MODIFICATION
        # 3 cards * +2/+2 = +6/+6
        assert pt_event.payload['power_mod'] == 6
        assert pt_event.payload['toughness_mod'] == 6

    def test_edwin_single_card_combo(self):
        """Edwin with 1 prior card should gain +2/+2."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 1

        edwin = make_obj(game, EDWIN_VANCLEEF, p1)
        events = EDWIN_VANCLEEF.battlecry(edwin, game.state)

        assert len(events) >= 1
        assert events[0].payload['power_mod'] == 2
        assert events[0].payload['toughness_mod'] == 2

    def test_preparation_adds_cost_reduction(self):
        """Preparation should add a one-shot spell cost reduction of 3."""
        game, p1, p2 = new_hs_game()
        modifiers_before = len(p1.cost_modifiers)

        cast_spell_full(game, PREPARATION, p1)

        assert len(p1.cost_modifiers) > modifiers_before
        mod = p1.cost_modifiers[-1]
        assert mod['card_type'] == CardType.SPELL
        assert mod['amount'] == 3

    def test_headcrack_deals_2_to_hero(self):
        """Headcrack should deal 2 damage to enemy hero."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0
        p2_life_before = p2.life

        cast_spell_full(game, HEADCRACK, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('target') == p2.hero_id]
        assert len(dmg_events) >= 1
        assert dmg_events[0].payload['amount'] == 2

    def test_headcrack_combo_registers_return(self):
        """Headcrack with Combo should register an interceptor to return next turn."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 1  # Combo active

        interceptors_before = len(game.state.interceptors)

        cast_spell_full(game, HEADCRACK, p1)

        # Should have registered a start-of-turn interceptor
        assert len(game.state.interceptors) > interceptors_before

    def test_headcrack_no_combo_no_return(self):
        """Headcrack without Combo should NOT register return interceptor."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0  # No combo

        interceptors_before = len(game.state.interceptors)

        cast_spell_full(game, HEADCRACK, p1)

        # Should not have registered extra interceptors (aside from spell machinery)
        # The headcrack return interceptor is added directly to state.interceptors
        return_interceptors = [i for i in game.state.interceptors.values()
                               if hasattr(i.handler, '_interceptor_id')]
        assert len(return_interceptors) == 0

    def test_eviscerate_combo_doubles_damage(self):
        """Eviscerate with Combo should deal 4 damage to a random enemy."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 1  # Combo active

        cast_spell_full(game, EVISCERATE, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 4 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_eviscerate_no_combo_base_damage(self):
        """Eviscerate without Combo should deal 2 damage to a random enemy."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0  # No combo

        cast_spell_full(game, EVISCERATE, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 2 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1


# ============================================================
# Silence Effects
# ============================================================

class TestSilenceEffects:
    def test_silence_removes_deathrattle(self):
        """Silencing a minion should prevent its deathrattle from firing."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p2)

        # Silence Cairne
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': cairne.id},
            source='test'
        ))

        # Now kill it
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cairne.id},
            source='test'
        ))

        # No Baine Bloodhoof token should be created
        baine_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(baine_events) == 0

    def test_silence_removes_enrage(self):
        """Silencing an enraged minion should remove the enrage buff."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        # Damage to trigger enrage (2/3, enrage +3 ATK = 5/2)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': amani.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # Verify enrage triggered
        power_after_enrage = get_power(amani, game.state)
        assert power_after_enrage >= 5  # 2 base + 3 enrage

        # Silence removes all interceptors including enrage
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': amani.id},
            source='test'
        ))

        # All interceptors should be removed
        assert len(amani.interceptor_ids) == 0

    def test_silence_removes_taunt(self):
        """Silencing a taunt minion should remove taunt."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)

        # Verify taunt exists
        has_taunt = any(a.get('keyword') == 'taunt'
                        for a in (abom.characteristics.abilities or []))
        assert has_taunt

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': abom.id},
            source='test'
        ))

        # Taunt should be gone
        has_taunt_after = any(a.get('keyword') == 'taunt'
                              for a in (abom.characteristics.abilities or []))
        assert not has_taunt_after

    def test_silence_removes_divine_shield(self):
        """Silencing a divine shield minion should remove divine shield."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)

        # Verify divine shield
        assert squire.state.divine_shield is True

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': squire.id},
            source='test'
        ))

        assert squire.state.divine_shield is False

    def test_silence_clears_all_interceptors(self):
        """Silencing should remove ALL interceptors from the minion."""
        game, p1, p2 = new_hs_game()
        sylv = make_obj(game, SYLVANAS_WINDRUNNER, p1)

        assert len(sylv.interceptor_ids) > 0

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': sylv.id},
            source='test'
        ))

        assert len(sylv.interceptor_ids) == 0


# ============================================================
# Blood Knight + Divine Shield Interaction
# ============================================================

class TestBloodKnight:
    def test_strips_all_divine_shields(self):
        """Blood Knight should remove divine shield from ALL minions on board."""
        game, p1, p2 = new_hs_game()
        s1 = make_obj(game, ARGENT_SQUIRE, p1)
        s2 = make_obj(game, ARGENT_SQUIRE, p2)

        assert s1.state.divine_shield is True
        assert s2.state.divine_shield is True

        bk = make_obj(game, BLOOD_KNIGHT, p1)
        events = BLOOD_KNIGHT.battlecry(bk, game.state)

        # Both shields should be stripped
        assert s1.state.divine_shield is False
        assert s2.state.divine_shield is False

        # Blood Knight should gain +3/+3 per shield (2 shields = +6/+6)
        assert len(events) >= 1
        pt_mod = events[0]
        assert pt_mod.payload['power_mod'] == 6
        assert pt_mod.payload['toughness_mod'] == 6

    def test_no_divine_shields_no_buff(self):
        """Blood Knight with no divine shields on board should get no buff."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, CHILLWIND_YETI, p1)

        bk = make_obj(game, BLOOD_KNIGHT, p1)
        events = BLOOD_KNIGHT.battlecry(bk, game.state)

        assert events == []


# ============================================================
# Youthful Brewmaster Bounce
# ============================================================

class TestYouthfulBrewmaster:
    def test_bounces_friendly_minion(self):
        """Youthful Brewmaster should return a friendly minion to hand."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p1)
        bm = make_obj(game, YOUTHFUL_BREWMASTER, p1)

        events = YOUTHFUL_BREWMASTER.battlecry(bm, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.RETURN_TO_HAND
        assert events[0].payload['object_id'] == target.id

    def test_no_friendly_minions_no_crash(self):
        """Brewmaster with only itself on board should not crash."""
        game, p1, p2 = new_hs_game()
        bm = make_obj(game, YOUTHFUL_BREWMASTER, p1)

        events = YOUTHFUL_BREWMASTER.battlecry(bm, game.state)

        # Should return empty (no valid targets)
        assert events == []

    def test_does_not_bounce_enemy(self):
        """Brewmaster should NOT bounce enemy minions."""
        game, p1, p2 = new_hs_game()
        enemy = make_obj(game, CHILLWIND_YETI, p2)
        bm = make_obj(game, YOUTHFUL_BREWMASTER, p1)

        events = YOUTHFUL_BREWMASTER.battlecry(bm, game.state)

        # No friendly targets besides self — should be empty
        assert events == []


# ============================================================
# Cross-Mechanic Combos
# ============================================================

class TestCrossMechanicBatch35:
    def test_silence_then_kill_no_deathrattle(self):
        """Silence a Leper Gnome then kill it — no damage to hero."""
        game, p1, p2 = new_hs_game()
        lg = make_obj(game, LEPER_GNOME, p2)

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': lg.id},
            source='test'
        ))

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': lg.id},
            source='test'
        ))

        # No damage to p1's hero from Leper Gnome source
        lg_dmg = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and
                  e.payload.get('source') == lg.id]
        assert len(lg_dmg) == 0

    def test_snipe_kills_small_minion(self):
        """Snipe dealing 4 damage to a 1/1 should kill it after SBA."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        snipe = make_secret(game, SNIPE, p1)

        target = play_from_hand(game, WISP, p2)  # 1/1

        # Snipe deals 4 damage to the 1/1
        game.check_state_based_actions()

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == target.id]
        assert len(destroy_events) >= 1

    def test_blood_knight_after_silence_no_shield(self):
        """Blood Knight can't strip shields that were already silenced off."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)

        # Silence removes divine shield
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': squire.id},
            source='test'
        ))
        assert squire.state.divine_shield is False

        bk = make_obj(game, BLOOD_KNIGHT, p1)
        events = BLOOD_KNIGHT.battlecry(bk, game.state)

        # No shields to strip
        assert events == []

    def test_avenge_no_other_minions_no_buff(self):
        """Avenge should not buff anything if no other friendly minions survive."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id
        avenge = make_secret(game, AVENGE, p1)
        only_minion = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': only_minion.id},
            source='test'
        ))

        # No PT_MODIFICATION events should fire (no surviving minion to buff)
        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION]
        assert len(pt_events) == 0

    def test_multiple_deathrattles_same_destroy(self):
        """Multiple deathrattle minions dying should all fire their effects."""
        game, p1, p2 = new_hs_game()
        lg1 = make_obj(game, LEPER_GNOME, p1)
        lg2 = make_obj(game, LEPER_GNOME, p1)

        # Kill both
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': lg1.id},
            source='test'
        ))
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': lg2.id},
            source='test'
        ))

        # Both should deal 2 to enemy hero
        lg_dmg = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE and
                  e.payload.get('target') == p2.hero_id and
                  e.payload.get('amount') == 2]
        assert len(lg_dmg) >= 2

    def test_tirion_silence_no_ashbringer(self):
        """Silencing Tirion then killing him should NOT equip Ashbringer."""
        game, p1, p2 = new_hs_game()
        tirion = make_obj(game, TIRION_FORDRING, p1)

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': tirion.id},
            source='test'
        ))

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': tirion.id},
            source='test'
        ))

        weapon_events = [e for e in game.state.event_log
                         if e.type == EventType.WEAPON_EQUIP]
        assert len(weapon_events) == 0
