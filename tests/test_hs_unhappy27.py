"""
Hearthstone Unhappy Path Tests - Batch 27

Battlecry effects (Youthful Brewmaster bounce, Blood Knight divine shield consume,
Coldlight Seer murloc buff, Arcane Golem mana crystal, Tinkmaster Overspark transform,
King Mukla bananas, Stampeding Kodo destroy), triggered effects (Lightwarden heal
trigger, Mana Addict spell trigger, Murloc Tidecaller summon trigger, Flesheating
Ghoul death trigger), end-of-turn legendaries (Hogger gnoll summon), and multi-card
interaction chains.
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
    BLOODFEN_RAPTOR, MURLOC_RAIDER, STONETUSK_BOAR, VOODOO_DOCTOR,
)
from src.cards.hearthstone.classic import (
    YOUTHFUL_BREWMASTER, COLDLIGHT_SEER, BLOOD_KNIGHT,
    ARCANE_GOLEM, TINKMASTER_OVERSPARK, LIGHTWARDEN, MANA_ADDICT,
    MURLOC_TIDECALLER, MURLOC_WARLEADER, HOGGER, KING_MUKLA,
    STAMPEDING_KODO, PRIESTESS_OF_ELUNE, ANGRY_CHICKEN,
    ARGENT_SQUIRE, FLESHEATING_GHOUL, KNIFE_JUGGLER,
    ABOMINATION, LOOT_HOARDER, HARVEST_GOLEM,
    SOUTHSEA_CAPTAIN,
)
from src.cards.hearthstone.mage import FROSTBOLT
from src.cards.hearthstone.warlock import HELLFIRE


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


def cast_spell_full(game, card_def, owner, targets=None):
    """Cast spell with SPELL_CAST event."""
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


# ============================================================
# Youthful Brewmaster — Battlecry: Return friendly minion to hand
# ============================================================

class TestYouthfulBrewmaster:
    def test_brewmaster_returns_friendly(self):
        """Youthful Brewmaster returns a random friendly minion to hand."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        brewmaster = play_from_hand(game, YOUTHFUL_BREWMASTER, p1)

        # Should have RETURN_TO_HAND event
        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND]
        assert len(return_events) >= 1

    def test_brewmaster_no_target_no_crash(self):
        """Brewmaster with no other friendly minions doesn't crash."""
        game, p1, p2 = new_hs_game()
        brewmaster = play_from_hand(game, YOUTHFUL_BREWMASTER, p1)

        # No crash, no RETURN_TO_HAND events
        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND]
        assert len(return_events) == 0


# ============================================================
# Blood Knight — BC: All lose Divine Shield, +3/+3 per shield
# ============================================================

class TestBloodKnight:
    def test_blood_knight_consumes_divine_shields(self):
        """Blood Knight removes all Divine Shields and gains +3/+3 per shield."""
        game, p1, p2 = new_hs_game()
        squire1 = make_obj(game, ARGENT_SQUIRE, p1)  # has divine shield
        squire2 = make_obj(game, ARGENT_SQUIRE, p2)  # enemy has divine shield

        bk = play_from_hand(game, BLOOD_KNIGHT, p1)

        # Both squires should lose divine shield
        assert squire1.state.divine_shield is False
        assert squire2.state.divine_shield is False

        # Blood Knight gains +3/+3 for each shield (2 shields = +6/+6)
        assert get_power(bk, game.state) >= 9  # 3 base + 6
        assert get_toughness(bk, game.state) >= 9

    def test_blood_knight_no_shields(self):
        """Blood Knight with no Divine Shields on board stays 3/3."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        bk = play_from_hand(game, BLOOD_KNIGHT, p1)

        assert get_power(bk, game.state) == 3
        assert get_toughness(bk, game.state) == 3


# ============================================================
# Coldlight Seer — BC: Give other Murlocs +2 Health
# ============================================================

class TestColdlightSeer:
    def test_coldlight_seer_buffs_murlocs(self):
        """Coldlight Seer gives friendly Murlocs +2 Health."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)  # 2/1 Murloc
        base_tough = get_toughness(raider, game.state)

        seer = play_from_hand(game, COLDLIGHT_SEER, p1)

        assert get_toughness(raider, game.state) >= base_tough + 2

    def test_coldlight_seer_no_buff_non_murlocs(self):
        """Coldlight Seer doesn't buff non-Murlocs."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        base_tough = get_toughness(yeti, game.state)

        seer = play_from_hand(game, COLDLIGHT_SEER, p1)

        assert get_toughness(yeti, game.state) == base_tough

    def test_coldlight_seer_no_buff_enemy_murlocs(self):
        """Coldlight Seer doesn't buff enemy Murlocs."""
        game, p1, p2 = new_hs_game()
        enemy_raider = make_obj(game, MURLOC_RAIDER, p2)
        base_tough = get_toughness(enemy_raider, game.state)

        seer = play_from_hand(game, COLDLIGHT_SEER, p1)

        assert get_toughness(enemy_raider, game.state) == base_tough


# ============================================================
# Arcane Golem — Charge + BC: Give opponent a Mana Crystal
# ============================================================

class TestArcaneGolem:
    def test_arcane_golem_has_charge(self):
        """Arcane Golem has Charge."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, ARCANE_GOLEM, p1)
        assert has_ability(golem, 'charge', game.state)

    def test_arcane_golem_gives_opponent_mana(self):
        """Arcane Golem's battlecry gives opponent a Mana Crystal."""
        game, p1, p2 = new_hs_game()
        # Set opponent below 10 mana crystals so the BC has room
        p2.mana_crystals = 5
        p2.mana_crystals_available = 5
        mana_before = p2.mana_crystals

        golem = play_from_hand(game, ARCANE_GOLEM, p1)

        # Opponent gains a Mana Crystal
        assert p2.mana_crystals == mana_before + 1


# ============================================================
# Tinkmaster Overspark — BC: Transform random minion to 5/5 or 1/1
# ============================================================

class TestTinkmasterOverspark:
    def test_tinkmaster_transforms_minion(self):
        """Tinkmaster transforms a random minion into Devilsaur or Squirrel."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        tink = play_from_hand(game, TINKMASTER_OVERSPARK, p1)

        # Yeti should be transformed
        transform_events = [e for e in game.state.event_log
                            if e.type == EventType.TRANSFORM]
        assert len(transform_events) >= 1
        # Name should be either "Devilsaur" or "Squirrel"
        assert yeti.name in ("Devilsaur", "Squirrel")

    def test_tinkmaster_no_minions(self):
        """Tinkmaster with no other minions doesn't crash."""
        game, p1, p2 = new_hs_game()
        tink = play_from_hand(game, TINKMASTER_OVERSPARK, p1)
        # No crash
        assert True


# ============================================================
# King Mukla — BC: Give opponent 2 Bananas
# ============================================================

class TestKingMukla:
    def test_king_mukla_gives_bananas(self):
        """King Mukla gives opponent 2 Banana spells."""
        game, p1, p2 = new_hs_game()
        mukla = play_from_hand(game, KING_MUKLA, p1)

        # Should have ADD_TO_HAND events for opponent
        banana_events = [e for e in game.state.event_log
                         if e.type == EventType.ADD_TO_HAND
                         and e.payload.get('player') == p2.id]
        assert len(banana_events) == 2


# ============================================================
# Stampeding Kodo — BC: Destroy random enemy minion with <=2 ATK
# ============================================================

class TestStampedingKodo:
    def test_kodo_destroys_low_attack(self):
        """Stampeding Kodo destroys a random enemy minion with <=2 Attack."""
        random.seed(42)
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)  # 1/1

        kodo = play_from_hand(game, STAMPEDING_KODO, p1)

        # Should destroy the wisp
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED
                          and e.payload.get('object_id') == wisp.id]
        assert len(destroy_events) >= 1

    def test_kodo_no_valid_targets(self):
        """Kodo with no enemy minions with <=2 ATK does nothing."""
        game, p1, p2 = new_hs_game()
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

        kodo = play_from_hand(game, STAMPEDING_KODO, p1)

        # Ogre has 6 ATK > 2, should not be destroyed
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED
                          and e.payload.get('object_id') == ogre.id]
        assert len(destroy_events) == 0


# ============================================================
# Lightwarden — Whenever a character is healed, gain +2 Attack
# ============================================================

class TestLightwarden:
    def test_lightwarden_gains_attack_on_heal(self):
        """Lightwarden gains +2 Attack when any character is healed."""
        game, p1, p2 = new_hs_game()
        warden = make_obj(game, LIGHTWARDEN, p1)
        base_power = get_power(warden, game.state)

        # Emit a healing event
        game.emit(Event(type=EventType.LIFE_CHANGE,
                        payload={'player': p1.id, 'amount': 2},
                        source='test'))

        assert get_power(warden, game.state) >= base_power + 2

    def test_lightwarden_stacks(self):
        """Lightwarden stacks +2 Attack per heal event."""
        game, p1, p2 = new_hs_game()
        warden = make_obj(game, LIGHTWARDEN, p1)
        base_power = get_power(warden, game.state)

        game.emit(Event(type=EventType.LIFE_CHANGE,
                        payload={'player': p1.id, 'amount': 2},
                        source='test'))
        game.emit(Event(type=EventType.LIFE_CHANGE,
                        payload={'player': p2.id, 'amount': 2},
                        source='test'))

        assert get_power(warden, game.state) >= base_power + 4  # 2 heals * +2


# ============================================================
# Mana Addict — Whenever you cast a spell, gain +2 Attack this turn
# ============================================================

class TestManaAddict:
    def test_mana_addict_gains_attack_on_spell(self):
        """Mana Addict gains +2 Attack when you cast a spell."""
        game, p1, p2 = new_hs_game()
        addict = make_obj(game, MANA_ADDICT, p1)
        base_power = get_power(addict, game.state)

        cast_spell_full(game, FROSTBOLT, p1)

        assert get_power(addict, game.state) >= base_power + 2

    def test_mana_addict_no_trigger_from_opponent(self):
        """Mana Addict doesn't trigger from opponent's spells."""
        game, p1, p2 = new_hs_game()
        addict = make_obj(game, MANA_ADDICT, p1)
        base_power = get_power(addict, game.state)

        cast_spell_full(game, FROSTBOLT, p2)

        assert get_power(addict, game.state) == base_power


# ============================================================
# Murloc Tidecaller — Whenever a Murloc is summoned, +1 Attack
# ============================================================

class TestMurlocTidecaller:
    def test_tidecaller_gains_on_murloc_summon(self):
        """Murloc Tidecaller gains +1 Attack when another Murloc is summoned."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)
        base_power = get_power(tc, game.state)

        play_from_hand(game, MURLOC_RAIDER, p1)

        assert get_power(tc, game.state) >= base_power + 1

    def test_tidecaller_no_trigger_non_murloc(self):
        """Tidecaller doesn't trigger from non-Murloc summons."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)
        base_power = get_power(tc, game.state)

        play_from_hand(game, WISP, p1)

        assert get_power(tc, game.state) == base_power

    def test_tidecaller_multiple_murlocs(self):
        """Tidecaller gains for each Murloc summoned."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)
        base_power = get_power(tc, game.state)

        play_from_hand(game, MURLOC_RAIDER, p1)
        play_from_hand(game, MURLOC_RAIDER, p1)

        assert get_power(tc, game.state) >= base_power + 2


# ============================================================
# Hogger — EOT: Summon 2/2 Gnoll with Taunt
# ============================================================

class TestHogger:
    def test_hogger_summons_gnoll(self):
        """Hogger summons a 2/2 Gnoll with Taunt at end of turn."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)

        game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Gnoll']
        assert len(token_events) >= 1

    def test_hogger_gnoll_has_taunt(self):
        """Hogger's Gnoll token has Taunt keyword."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)

        game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Gnoll']
        assert len(token_events) >= 1
        gnoll_token = token_events[0].payload['token']
        assert 'taunt' in (gnoll_token.get('keywords', set()) or set())

    def test_hogger_multiple_turns(self):
        """Hogger summons a Gnoll each turn."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)

        for _ in range(3):
            game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Gnoll']
        assert len(token_events) >= 3


# ============================================================
# Angry Chicken — Enrage: +5 Attack
# ============================================================

class TestAngryChicken:
    def test_angry_chicken_enrage(self):
        """Angry Chicken gains +5 Attack when damaged (enrage)."""
        game, p1, p2 = new_hs_game()
        chicken = make_obj(game, ANGRY_CHICKEN, p1)
        assert get_power(chicken, game.state) == 1

        # Note: Angry Chicken is 1/1, so 1 damage would kill it
        # Need to buff health first or test the enrage trigger directly
        # Let's give it health first
        game.emit(Event(type=EventType.PT_MODIFICATION,
                        payload={'object_id': chicken.id, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
                        source='test'))

        game.emit(Event(type=EventType.DAMAGE,
                        payload={'target': chicken.id, 'amount': 1, 'source': 'test'},
                        source='test'))

        assert get_power(chicken, game.state) >= 6  # 1 + 5 enrage


# ============================================================
# Priestess of Elune — BC: Restore 4 Health to hero
# ============================================================

class TestPriestessOfElune:
    def test_priestess_heals_hero(self):
        """Priestess of Elune heals own hero for 4 on battlecry."""
        game, p1, p2 = new_hs_game()
        p1.life = 20

        priestess = play_from_hand(game, PRIESTESS_OF_ELUNE, p1)

        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE
                       and e.payload.get('player') == p1.id
                       and e.payload.get('amount') == 4]
        assert len(heal_events) >= 1


# ============================================================
# Cross-mechanic: Blood Knight + Argent Squire army
# ============================================================

class TestBloodKnightArmy:
    def test_blood_knight_consumes_3_shields(self):
        """Blood Knight consuming 3 Divine Shields becomes 12/12."""
        game, p1, p2 = new_hs_game()
        s1 = make_obj(game, ARGENT_SQUIRE, p1)
        s2 = make_obj(game, ARGENT_SQUIRE, p1)
        s3 = make_obj(game, ARGENT_SQUIRE, p2)

        bk = play_from_hand(game, BLOOD_KNIGHT, p1)

        # 3 shields * +3/+3 = +9/+9 → 12/12
        assert get_power(bk, game.state) >= 12
        assert get_toughness(bk, game.state) >= 12
        # All shields consumed
        assert s1.state.divine_shield is False
        assert s2.state.divine_shield is False
        assert s3.state.divine_shield is False


# ============================================================
# Cross-mechanic: Murloc synergy chain
# ============================================================

class TestMurlocSynergyChain:
    def test_tidecaller_warleader_seer_chain(self):
        """Murloc Tidecaller on board, play Warleader, then Seer — verify chain."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)  # 1/2 Murloc
        tc_base_power = get_power(tc, game.state)

        warleader = play_from_hand(game, MURLOC_WARLEADER, p1)
        # Tidecaller should trigger +1 from Warleader summon
        assert get_power(tc, game.state) >= tc_base_power + 1

        seer = play_from_hand(game, COLDLIGHT_SEER, p1)
        # Tidecaller should trigger again (+1 from Seer summon)
        # Seer also gives +2 Health to other murlocs
        assert get_power(tc, game.state) >= tc_base_power + 2


# ============================================================
# Cross-mechanic: Hogger + Knife Juggler
# ============================================================

class TestHoggerJugglerCombo:
    def test_hogger_gnoll_triggers_juggler(self):
        """Hogger's EOT Gnoll summon should trigger Knife Juggler."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='system'))

        # Gnoll summoned → Knife Juggler should trigger
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN
                        and e.payload.get('token', {}).get('name') == 'Gnoll']
        assert len(token_events) >= 1

        # Juggler should have fired (1 damage to random enemy)
        juggle_damage = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('source') == juggler.id
                         and e.payload.get('amount') == 1]
        assert len(juggle_damage) >= 1


# ============================================================
# Cross-mechanic: Lightwarden + Priestess of Elune
# ============================================================

class TestLightwardenPriestessCombo:
    def test_lightwarden_triggers_on_priestess_heal(self):
        """Lightwarden gains +2 Attack when Priestess heals hero."""
        game, p1, p2 = new_hs_game()
        p1.life = 20
        warden = make_obj(game, LIGHTWARDEN, p1)
        base_power = get_power(warden, game.state)

        priestess = play_from_hand(game, PRIESTESS_OF_ELUNE, p1)

        # Priestess heals 4 → Lightwarden gains +2
        assert get_power(warden, game.state) >= base_power + 2


# ============================================================
# Cross-mechanic: Flesheating Ghoul + mass destruction
# ============================================================

class TestFlesheatingGhoulMassDeath:
    def test_ghoul_stacks_on_mass_destroy(self):
        """Flesheating Ghoul gains +1 Attack for each minion destroyed."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        base_power = get_power(ghoul, game.state)

        # Create and destroy multiple enemy minions
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)
        w3 = make_obj(game, WISP, p2)

        for w in [w1, w2, w3]:
            game.emit(Event(type=EventType.OBJECT_DESTROYED,
                            payload={'object_id': w.id},
                            source='test'))

        assert get_power(ghoul, game.state) >= base_power + 3  # +1 per death
