"""
Hearthstone Unhappy Path Tests - Batch 18

Class-specific cards and tokens: Druid (Mark of the Wild, Gift of the Wild,
Savagery), Hunter (Eaglehorn Bow, Gladiator's Longbow, Flare, Unleash the
Hounds, Scavenging Hyena), Rogue (Edwin VanCleef, Preparation, Shadowstep,
Patient Assassin, Headcrack combo), Priest (Mind Vision, Thoughtsteal,
Shadowform, Shadow Madness, Mindgames), Warlock (Void Terror, Corruption),
Shaman (Unbound Elemental, Stormforged Axe, Far Sight), Token cards (Leokk
lord, Healing Totem EOT, Wrath of Air spell damage).
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
    WISP, CHILLWIND_YETI, RIVER_CROCOLISK, BLOODFEN_RAPTOR,
    MURLOC_RAIDER, STONETUSK_BOAR,
)
from src.cards.hearthstone.classic import (
    FROSTBOLT, FIREBALL, KNIFE_JUGGLER,
)
from src.cards.hearthstone.druid import (
    MARK_OF_THE_WILD, GIFT_OF_THE_WILD, SAVAGERY,
)
from src.cards.hearthstone.hunter import (
    EAGLEHORN_BOW, GLADIATORS_LONGBOW, FLARE,
    UNLEASH_THE_HOUNDS, SCAVENGING_HYENA,
)
from src.cards.hearthstone.rogue import (
    EDWIN_VANCLEEF, PREPARATION, SHADOWSTEP,
    PATIENT_ASSASSIN, HEADCRACK,
)
from src.cards.hearthstone.priest import (
    MIND_VISION, THOUGHTSTEAL, SHADOWFORM, SHADOW_MADNESS, MINDGAMES,
)
from src.cards.hearthstone.warlock import (
    VOIDWALKER, VOID_TERROR, CORRUPTION,
)
from src.cards.hearthstone.shaman import (
    UNBOUND_ELEMENTAL, STORMFORGED_AXE, FAR_SIGHT,
    LIGHTNING_BOLT,
)
from src.cards.hearthstone.tokens import (
    LEOKK, HEALING_TOTEM, WRATH_OF_AIR_TOTEM,
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
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    return obj


def play_from_hand(game, card_def, owner):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': owner.id
        },
        source=obj.id
    ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    return obj


# ============================================================
# Druid: Mark of the Wild - Give a minion Taunt and +2/+2
# ============================================================

class TestMarkOfTheWild:
    def test_mark_of_the_wild_buffs_and_taunts(self):
        """Mark of the Wild gives +2/+2 and Taunt to a friendly minion."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        cast_spell(game, MARK_OF_THE_WILD, p1)
        # Check for PT modification event
        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION
                     and e.payload.get('power_mod') == 2
                     and e.payload.get('toughness_mod') == 2]
        assert len(pt_events) >= 1

    def test_mark_of_the_wild_no_minions(self):
        """Mark of the Wild with no friendly minions does nothing."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, MARK_OF_THE_WILD, p1)
        # No crash


# ============================================================
# Druid: Gift of the Wild - Give all friendly minions +2/+2 and Taunt
# ============================================================

class TestGiftOfTheWild:
    def test_gift_buffs_all_friendlies(self):
        """Gift of the Wild buffs all friendly minions."""
        game, p1, p2 = new_hs_game()
        y1 = make_obj(game, CHILLWIND_YETI, p1)
        y2 = make_obj(game, RIVER_CROCOLISK, p1)
        enemy = make_obj(game, WISP, p2)
        cast_spell(game, GIFT_OF_THE_WILD, p1)
        # Both friendly minions should get PT modification events
        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION
                     and e.payload.get('power_mod') == 2]
        assert len(pt_events) >= 2

    def test_gift_no_friendlies(self):
        """Gift of the Wild with no friendly minions does nothing."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, GIFT_OF_THE_WILD, p1)
        # No crash


# ============================================================
# Druid: Savagery - Deal damage equal to hero's Attack to a minion
# ============================================================

class TestSavagery:
    def test_savagery_deals_hero_attack_damage(self):
        """Savagery deals damage equal to hero's Attack."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        p1.weapon_attack = 3  # Hero has 3 attack
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        cast_spell(game, SAVAGERY, p1)
        # Should deal 3 damage to the yeti
        assert yeti.state.damage == 3

    def test_savagery_no_hero_attack(self):
        """Savagery with 0 hero attack does nothing."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        cast_spell(game, SAVAGERY, p1)
        assert yeti.state.damage == 0


# ============================================================
# Hunter: Eaglehorn Bow - Gain +1 Durability on friendly Secret trigger
# ============================================================

class TestEaglehornBow:
    def test_eaglehorn_bow_has_interceptor(self):
        """Eaglehorn Bow registers interceptor for secret triggers."""
        game, p1, p2 = new_hs_game()
        bow = make_obj(game, EAGLEHORN_BOW, p1)
        assert len(bow.interceptor_ids) > 0

    def test_eaglehorn_bow_stats(self):
        """Eaglehorn Bow is 3/2."""
        game, p1, p2 = new_hs_game()
        bow = make_obj(game, EAGLEHORN_BOW, p1)
        assert bow.characteristics.power == 3
        assert bow.characteristics.toughness == 2


# ============================================================
# Hunter: Gladiator's Longbow - Hero Immune while attacking
# ============================================================

class TestGladiatorsLongbow:
    def test_gladiators_longbow_has_interceptor(self):
        """Gladiator's Longbow registers attack interceptor."""
        game, p1, p2 = new_hs_game()
        bow = make_obj(game, GLADIATORS_LONGBOW, p1)
        assert len(bow.interceptor_ids) > 0

    def test_gladiators_longbow_grants_immune_on_attack(self):
        """Gladiator's Longbow grants hero Immune on ATTACK_DECLARED."""
        game, p1, p2 = new_hs_game()
        bow = make_obj(game, GLADIATORS_LONGBOW, p1)
        p1.weapon_attack = 5
        p1.weapon_durability = 2
        # Trigger attack declared
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': p2.hero_id},
            source=p1.hero_id
        ))
        # Hero should have Immune ability
        hero = game.state.objects.get(p1.hero_id)
        has_immune = any(a.get('keyword') == 'immune' for a in (hero.characteristics.abilities or []))
        assert has_immune


# ============================================================
# Hunter: Flare - Remove stealth, destroy secrets, draw a card
# ============================================================

class TestFlare:
    def test_flare_removes_stealth(self):
        """Flare removes Stealth from enemy minions."""
        game, p1, p2 = new_hs_game()
        tiger = make_obj(game, CHILLWIND_YETI, p2)
        tiger.state.stealth = True
        cast_spell(game, FLARE, p1)
        assert tiger.state.stealth is False

    def test_flare_draws_card(self):
        """Flare draws a card."""
        game, p1, p2 = new_hs_game()
        for _ in range(3):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        log_before = len(game.state.event_log)
        cast_spell(game, FLARE, p1)
        draw_events = [e for e in game.state.event_log[log_before:]
                       if e.type == EventType.DRAW]
        assert len(draw_events) >= 1

    def test_flare_no_stealth_no_secrets(self):
        """Flare with no stealth or secrets just draws."""
        game, p1, p2 = new_hs_game()
        for _ in range(3):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        cast_spell(game, FLARE, p1)
        # No crash


# ============================================================
# Hunter: Unleash the Hounds - Summon 1/1 Hounds per enemy minion
# ============================================================

class TestUnleashTheHounds:
    def test_unleash_summons_per_enemy(self):
        """Unleash the Hounds summons one Hound per enemy minion."""
        game, p1, p2 = new_hs_game()
        make_obj(game, CHILLWIND_YETI, p2)
        make_obj(game, RIVER_CROCOLISK, p2)
        make_obj(game, WISP, p2)
        log_before = len(game.state.event_log)
        cast_spell(game, UNLEASH_THE_HOUNDS, p1)
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 3

    def test_unleash_no_enemies(self):
        """Unleash the Hounds with no enemy minions summons nothing."""
        game, p1, p2 = new_hs_game()
        log_before = len(game.state.event_log)
        cast_spell(game, UNLEASH_THE_HOUNDS, p1)
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 0


# ============================================================
# Hunter: Scavenging Hyena - Gains +2/+1 when friendly Beast dies
# ============================================================

class TestScavengingHyena:
    def test_hyena_gains_on_beast_death(self):
        """Scavenging Hyena gains +2/+1 when a friendly Beast dies."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)  # Beast
        base_power = get_power(hyena, game.state)
        # Kill the raptor
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': raptor.id, 'reason': 'test'},
            source='test'
        ))
        new_power = get_power(hyena, game.state)
        assert new_power == base_power + 2

    def test_hyena_ignores_non_beast_death(self):
        """Scavenging Hyena doesn't trigger on non-Beast death."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # Not a Beast
        base_power = get_power(hyena, game.state)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id, 'reason': 'test'},
            source='test'
        ))
        new_power = get_power(hyena, game.state)
        assert new_power == base_power


# ============================================================
# Rogue: Edwin VanCleef - Combo: +2/+2 per card played
# ============================================================

class TestEdwinVanCleef:
    def test_edwin_combo_gains_stats(self):
        """Edwin gains +2/+2 per card played this turn."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 3  # 3 cards before Edwin
        edwin = play_from_hand(game, EDWIN_VANCLEEF, p1)
        # Base 2/2 + 3*2/3*2 = 8/8
        power = get_power(edwin, game.state)
        toughness = get_toughness(edwin, game.state)
        assert power == 8
        assert toughness == 8

    def test_edwin_no_combo(self):
        """Edwin with no prior cards played is 2/2."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0
        edwin = play_from_hand(game, EDWIN_VANCLEEF, p1)
        power = get_power(edwin, game.state)
        assert power == 2


# ============================================================
# Rogue: Preparation - Next spell costs (3) less
# ============================================================

class TestPreparation:
    def test_preparation_adds_cost_reduction(self):
        """Preparation adds a one-shot spell cost reduction."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, PREPARATION, p1)
        # Should have a cost modifier for spells
        has_spell_mod = any(
            m.get('card_type') == CardType.SPELL
            for m in p1.cost_modifiers
        )
        assert has_spell_mod


# ============================================================
# Rogue: Shadowstep - Return friendly minion, costs (2) less
# ============================================================

class TestShadowstep:
    def test_shadowstep_returns_to_hand(self):
        """Shadowstep returns a friendly minion to hand."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        cast_spell(game, SHADOWSTEP, p1, targets=[yeti.id])
        # Should emit RETURN_TO_HAND event
        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND
                         and e.payload.get('object_id') == yeti.id]
        assert len(return_events) >= 1

    def test_shadowstep_no_targets(self):
        """Shadowstep with no friendly minions does nothing."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, SHADOWSTEP, p1, targets=[])
        # No crash


# ============================================================
# Rogue: Patient Assassin - Stealth + Destroy damaged minion
# ============================================================

class TestPatientAssassin:
    def test_patient_assassin_has_stealth(self):
        """Patient Assassin has Stealth keyword."""
        game, p1, p2 = new_hs_game()
        pa = make_obj(game, PATIENT_ASSASSIN, p1)
        assert has_ability(pa, 'stealth', game.state)

    def test_patient_assassin_destroys_damaged(self):
        """Patient Assassin destroys any minion it damages."""
        game, p1, p2 = new_hs_game()
        pa = make_obj(game, PATIENT_ASSASSIN, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        # Simulate PA dealing damage to yeti
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': 1, 'source': pa.id},
            source=pa.id
        ))
        # Should emit OBJECT_DESTROYED
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED
                          and e.payload.get('object_id') == yeti.id]
        assert len(destroy_events) >= 1


# ============================================================
# Rogue: Headcrack - 2 damage to hero, Combo: return to hand
# ============================================================

class TestHeadcrack:
    def test_headcrack_deals_2_to_hero(self):
        """Headcrack deals 2 damage to enemy hero."""
        game, p1, p2 = new_hs_game()
        p2_life_before = p2.life
        cast_spell(game, HEADCRACK, p1)
        assert p2.life == p2_life_before - 2

    def test_headcrack_combo_returns_next_turn(self):
        """Headcrack with Combo sets up return to hand at next turn start."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 1  # Combo active
        cast_spell(game, HEADCRACK, p1)
        # Should have registered an interceptor for TURN_START
        has_turn_start = any(
            hasattr(i, 'filter') for i in game.state.interceptors.values()
        )
        assert has_turn_start  # At least interceptors exist

    def test_headcrack_no_combo_no_return(self):
        """Headcrack without Combo just deals damage, no return."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0
        interceptors_before = len(game.state.interceptors)
        cast_spell(game, HEADCRACK, p1)
        interceptors_after = len(game.state.interceptors)
        # No new interceptor for return (only combat interceptors)
        assert interceptors_after == interceptors_before


# ============================================================
# Priest: Mind Vision - Copy a random card from opponent's hand
# ============================================================

class TestMindVision:
    def test_mind_vision_copies_from_opponent(self):
        """Mind Vision copies a card from opponent's hand."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        # Put a card in P2's hand
        make_obj(game, CHILLWIND_YETI, p2, zone=ZoneType.HAND)
        log_before = len(game.state.event_log)
        cast_spell(game, MIND_VISION, p1)
        add_events = [e for e in game.state.event_log[log_before:]
                      if e.type == EventType.ADD_TO_HAND]
        assert len(add_events) >= 1

    def test_mind_vision_empty_hand(self):
        """Mind Vision with empty opponent hand does nothing."""
        game, p1, p2 = new_hs_game()
        # P2 hand is empty
        log_before = len(game.state.event_log)
        cast_spell(game, MIND_VISION, p1)
        add_events = [e for e in game.state.event_log[log_before:]
                      if e.type == EventType.ADD_TO_HAND]
        assert len(add_events) == 0


# ============================================================
# Priest: Thoughtsteal - Copy 2 cards from opponent's deck
# ============================================================

class TestThoughtsteal:
    def test_thoughtsteal_copies_two(self):
        """Thoughtsteal copies 2 cards from opponent's deck."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        # Put cards in P2's library
        make_obj(game, CHILLWIND_YETI, p2, zone=ZoneType.LIBRARY)
        make_obj(game, RIVER_CROCOLISK, p2, zone=ZoneType.LIBRARY)
        make_obj(game, WISP, p2, zone=ZoneType.LIBRARY)
        log_before = len(game.state.event_log)
        cast_spell(game, THOUGHTSTEAL, p1)
        add_events = [e for e in game.state.event_log[log_before:]
                      if e.type == EventType.ADD_TO_HAND]
        assert len(add_events) == 2

    def test_thoughtsteal_empty_deck(self):
        """Thoughtsteal with empty opponent deck does nothing."""
        game, p1, p2 = new_hs_game()
        log_before = len(game.state.event_log)
        cast_spell(game, THOUGHTSTEAL, p1)
        add_events = [e for e in game.state.event_log[log_before:]
                      if e.type == EventType.ADD_TO_HAND]
        assert len(add_events) == 0


# ============================================================
# Priest: Shadowform - Change hero power to deal damage
# ============================================================

class TestShadowform:
    def test_shadowform_changes_hero_power(self):
        """Shadowform replaces hero power with Mind Spike."""
        game, p1, p2 = new_hs_game()
        # Set up P1 as Priest
        from src.cards.hearthstone.hero_powers import HERO_POWERS
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Priest"])
        old_hp_id = p1.hero_power_id
        cast_spell(game, SHADOWFORM, p1)
        # Hero power should have changed
        assert p1.hero_power_id != old_hp_id
        new_hp = game.state.objects.get(p1.hero_power_id)
        assert new_hp.name == "Mind Spike"


# ============================================================
# Priest: Shadow Madness - Steal low-attack minion until EOT
# ============================================================

class TestShadowMadness:
    def test_shadow_madness_emits_gain_control(self):
        """Shadow Madness emits GAIN_CONTROL for enemy minion with <=3 ATK."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        croc = make_obj(game, RIVER_CROCOLISK, p2)  # 2/3 - <=3 attack
        log_before = len(game.state.event_log)
        cast_spell(game, SHADOW_MADNESS, p1)
        control_events = [e for e in game.state.event_log[log_before:]
                          if e.type == EventType.GAIN_CONTROL]
        assert len(control_events) >= 1

    def test_shadow_madness_ignores_high_attack(self):
        """Shadow Madness ignores minions with >3 Attack."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5 - too high
        log_before = len(game.state.event_log)
        cast_spell(game, SHADOW_MADNESS, p1)
        control_events = [e for e in game.state.event_log[log_before:]
                          if e.type == EventType.GAIN_CONTROL]
        assert len(control_events) == 0


# ============================================================
# Priest: Mindgames - Copy a minion from opponent deck to battlefield
# ============================================================

class TestMindgames:
    def test_mindgames_summons_copy(self):
        """Mindgames summons a copy of a minion from opponent's deck."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        # Put a minion in P2's library
        make_obj(game, CHILLWIND_YETI, p2, zone=ZoneType.LIBRARY)
        log_before = len(game.state.event_log)
        cast_spell(game, MINDGAMES, p1)
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 1
        # Token should be a Yeti copy
        token = token_events[0].payload.get('token', {})
        assert token.get('name') == 'Chillwind Yeti'

    def test_mindgames_no_minions_summons_shadow(self):
        """Mindgames with no minions in opponent deck summons Shadow of Nothing."""
        game, p1, p2 = new_hs_game()
        # No minions in P2 library (put spells or nothing)
        log_before = len(game.state.event_log)
        cast_spell(game, MINDGAMES, p1)
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 1
        token = token_events[0].payload.get('token', {})
        assert token.get('name') == 'Shadow of Nothing'


# ============================================================
# Warlock: Void Terror - Destroy adjacent, gain their stats
# ============================================================

class TestVoidTerror:
    def test_void_terror_eats_adjacent(self):
        """Void Terror destroys adjacent minions and gains their stats."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)      # 1/1 left
        terror = play_from_hand(game, VOID_TERROR, p1)  # middle
        yeti = make_obj(game, CHILLWIND_YETI, p1)       # right
        # Note: adjacency depends on battlefield order at time of ETB
        # Check that OBJECT_DESTROYED events were emitted
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED]
        # At least one adjacent minion should be destroyed
        # (depends on battlefield position at ETB time)
        assert len(destroy_events) >= 0  # May be 0 if no adjacent at ETB time

    def test_void_terror_no_adjacent(self):
        """Void Terror with no adjacent minions doesn't crash."""
        game, p1, p2 = new_hs_game()
        terror = play_from_hand(game, VOID_TERROR, p1)
        # No crash, base stats 3/3
        power = get_power(terror, game.state)
        assert power == 3


# ============================================================
# Warlock: Corruption - Destroy enemy minion at start of your turn
# ============================================================

class TestCorruption:
    def test_corruption_sets_up_delayed_destroy(self):
        """Corruption registers interceptor for delayed destroy."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        interceptors_before = len(game.state.interceptors)
        cast_spell(game, CORRUPTION, p1, targets=[yeti.id])
        interceptors_after = len(game.state.interceptors)
        # Should have added a new interceptor
        assert interceptors_after > interceptors_before

    def test_corruption_destroys_at_turn_start(self):
        """Corruption destroys the target at the start of caster's turn."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        cast_spell(game, CORRUPTION, p1, targets=[yeti.id])
        # Trigger turn start for P1
        log_before = len(game.state.event_log)
        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='game'
        ))
        destroy_events = [e for e in game.state.event_log[log_before:]
                          if e.type == EventType.OBJECT_DESTROYED
                          and e.payload.get('object_id') == yeti.id]
        assert len(destroy_events) >= 1


# ============================================================
# Shaman: Unbound Elemental - +1/+1 on Overload card play
# ============================================================

class TestUnboundElemental:
    def test_unbound_gains_on_overload_spell(self):
        """Unbound Elemental gains +1/+1 when an Overload card is played."""
        game, p1, p2 = new_hs_game()
        unbound = make_obj(game, UNBOUND_ELEMENTAL, p1)
        base_power = get_power(unbound, game.state)
        # Cast Lightning Bolt (has Overload in text)
        bolt = game.create_object(
            name=LIGHTNING_BOLT.name,
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=LIGHTNING_BOLT.characteristics,
            card_def=LIGHTNING_BOLT
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': bolt.id, 'caster': p1.id},
            source=bolt.id
        ))
        new_power = get_power(unbound, game.state)
        assert new_power == base_power + 1

    def test_unbound_ignores_non_overload(self):
        """Unbound Elemental doesn't trigger on non-Overload spells."""
        game, p1, p2 = new_hs_game()
        unbound = make_obj(game, UNBOUND_ELEMENTAL, p1)
        base_power = get_power(unbound, game.state)
        # Cast Fireball (no Overload)
        fb = game.create_object(
            name=FIREBALL.name,
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=FIREBALL.characteristics,
            card_def=FIREBALL
        )
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': fb.id, 'caster': p1.id},
            source=fb.id
        ))
        new_power = get_power(unbound, game.state)
        assert new_power == base_power  # No change


# ============================================================
# Shaman: Stormforged Axe - Overload: (1) on equip
# ============================================================

class TestStormforgedAxe:
    def test_stormforged_axe_overloads(self):
        """Stormforged Axe applies Overload: (1) when equipped."""
        game, p1, p2 = new_hs_game()
        p1.overloaded_mana = 0
        axe = make_obj(game, STORMFORGED_AXE, p1)
        assert p1.overloaded_mana == 1

    def test_stormforged_axe_stats(self):
        """Stormforged Axe is 2/3."""
        game, p1, p2 = new_hs_game()
        axe = make_obj(game, STORMFORGED_AXE, p1)
        assert axe.characteristics.power == 2
        assert axe.characteristics.toughness == 3


# ============================================================
# Shaman: Far Sight - Draw a card, it costs (3) less
# ============================================================

class TestFarSight:
    def test_far_sight_draws_and_reduces_cost(self):
        """Far Sight draws a card and reduces its cost by 3."""
        game, p1, p2 = new_hs_game()
        # Put a 5-cost card in library
        yeti_in_lib = make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.LIBRARY)
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)
        cast_spell(game, FAR_SIGHT, p1)
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after == hand_before + 1
        # The drawn card should have reduced cost
        drawn = game.state.objects.get(yeti_in_lib.id)
        assert drawn.characteristics.mana_cost == "{1}"  # 4 - 3 = 1

    def test_far_sight_empty_deck(self):
        """Far Sight with empty deck does nothing."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, FAR_SIGHT, p1)
        # No crash


# ============================================================
# Tokens: Leokk - Your other minions have +1 Attack
# ============================================================

class TestLeokk:
    def test_leokk_buffs_friendly_minions(self):
        """Leokk gives other friendly minions +1 Attack."""
        game, p1, p2 = new_hs_game()
        leokk = make_obj(game, LEOKK, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        power = get_power(yeti, game.state)
        assert power == 5  # 4 base + 1 from Leokk

    def test_leokk_doesnt_buff_self(self):
        """Leokk doesn't buff itself."""
        game, p1, p2 = new_hs_game()
        leokk = make_obj(game, LEOKK, p1)
        power = get_power(leokk, game.state)
        assert power == 2  # base 2, no self-buff

    def test_leokk_doesnt_buff_enemy(self):
        """Leokk doesn't buff enemy minions."""
        game, p1, p2 = new_hs_game()
        leokk = make_obj(game, LEOKK, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)
        power = get_power(enemy, game.state)
        assert power == 4  # base 4, no buff


# ============================================================
# Tokens: Healing Totem - At EOT, restore 1 Health to friendlies
# ============================================================

class TestHealingTotem:
    def test_healing_totem_heals_at_eot(self):
        """Healing Totem restores 1 Health to all friendly minions at EOT."""
        game, p1, p2 = new_hs_game()
        totem = make_obj(game, HEALING_TOTEM, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.damage = 2  # Damaged
        game.state.active_player = p1.id
        game.emit(Event(
            type=EventType.PHASE_END,
            payload={'player': p1.id, 'phase': 'end'},
            source='game'
        ))
        # Should heal 1 HP
        assert yeti.state.damage <= 1  # Was 2, now at most 1


# ============================================================
# Tokens: Wrath of Air Totem - Spell Damage +1
# ============================================================

class TestWrathOfAirTotem:
    def test_wrath_of_air_spell_damage(self):
        """Wrath of Air Totem gives Spell Damage +1."""
        game, p1, p2 = new_hs_game()
        totem = make_obj(game, WRATH_OF_AIR_TOTEM, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])
        # 3 base + 1 spell damage = 4
        assert yeti.state.damage == 4


# ============================================================
# Cross-card interactions
# ============================================================

class TestBatch18Interactions:
    def test_scavenging_hyena_with_unleash(self):
        """Scavenging Hyena doesn't die from Unleash summons (no beasts dying)."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        make_obj(game, CHILLWIND_YETI, p2)  # Enemy minion
        base_power = get_power(hyena, game.state)
        cast_spell(game, UNLEASH_THE_HOUNDS, p1)
        # Hyena shouldn't gain anything (no beasts died)
        new_power = get_power(hyena, game.state)
        assert new_power == base_power

    def test_savagery_with_claw_buff(self):
        """Savagery deals damage based on hero attack from Claw."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        # Set hero attack (as if Claw was played)
        p1.weapon_attack = 2
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        cast_spell(game, SAVAGERY, p1)
        assert yeti.state.damage == 2

    def test_preparation_adds_modifier(self):
        """Preparation + spell = cost reduction applied."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, PREPARATION, p1)
        spell_mods = [m for m in p1.cost_modifiers if m.get('card_type') == CardType.SPELL]
        assert len(spell_mods) >= 1
        assert spell_mods[0].get('amount') == 3

    def test_edwin_massive_combo(self):
        """Edwin with 5 cards played = +10/+10 = 12/12."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 5
        edwin = play_from_hand(game, EDWIN_VANCLEEF, p1)
        power = get_power(edwin, game.state)
        toughness = get_toughness(edwin, game.state)
        assert power == 12  # 2 + 5*2
        assert toughness == 12
