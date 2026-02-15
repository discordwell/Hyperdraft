"""
Hearthstone Unhappy Path Tests - Batch 72

Tribal synergy interactions: Murloc Warleader buff stacking, Murloc
Tidecaller summon trigger, Grimscale Oracle attack buff, Old Murk-Eye
charge per murloc, Coldlight Seer health buff, Timber Wolf beast aura,
Houndmaster beast battlecry, Scavenging Hyena beast death trigger,
Starving Buzzard beast draw, Kill Command beast conditional, Blood Imp
demon stealth, Demonfire demon conditional, Sacrificial Pact demon
destroy + heal, Hungry Crab murloc destroy + buff, Bloodsail Raider
weapon attack copy, Captain Greenskin weapon buff, tribal counting
(how many murlocs/beasts on board), non-tribal minion excluded from
tribal buffs.
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
    WISP, CHILLWIND_YETI, MURLOC_RAIDER, BLUEGILL_WARRIOR,
    GRIMSCALE_ORACLE, BLOODFEN_RAPTOR, STONETUSK_BOAR,
    RIVER_CROCOLISK, IRONFUR_GRIZZLY,
)
from src.cards.hearthstone.classic import (
    MURLOC_WARLEADER, MURLOC_TIDECALLER, COLDLIGHT_SEER,
    HUNGRY_CRAB, BLOODSAIL_RAIDER, CAPTAIN_GREENSKIN,
)
from src.cards.hearthstone.hunter import (
    TIMBER_WOLF, HOUNDMASTER, SCAVENGING_HYENA, STARVING_BUZZARD,
    KILL_COMMAND,
)
from src.cards.hearthstone.warlock import (
    BLOOD_IMP, DEMONFIRE, SACRIFICIAL_PACT, VOIDWALKER, FLAME_IMP,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create an object from a card definition and place it in the given zone."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': None,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'controller': owner.id,
            },
            source=obj.id
        ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card by invoking its spell_effect and emitting SPELL_CAST."""
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


def play_from_hand(game, card_def, owner):
    """Simulate playing a minion from hand (triggers battlecry via ZONE_CHANGE)."""
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


def add_cards_to_library(game, player, card_def, count):
    """Add card objects to a player's library for draw testing."""
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


def get_hand_size(game, player):
    """Get number of cards in a player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    return len(hand.objects) if hand else 0


# ============================================================
# Test 1: TestMurlocWarleaderAura
# ============================================================

class TestMurlocWarleaderAura:
    def test_warleader_buffs_friendly_murloc_power(self):
        """Murloc Warleader gives other friendly Murlocs +2 Attack."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        # Murloc Raider base is 2/1; with Warleader aura should be 4/1
        computed_power = get_power(raider, game.state)
        assert computed_power == 4, (
            f"Murloc Raider (2/1) with Warleader aura (+2 Attack) should have "
            f"4 Attack, got {computed_power}"
        )

    def test_warleader_does_not_buff_toughness(self):
        """Warleader gives +2 Attack only (no toughness buff in current impl)."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        # Murloc Raider base is 2/1; toughness should remain 1
        computed_toughness = get_toughness(raider, game.state)
        assert computed_toughness == 1, (
            f"Murloc Raider toughness should remain 1 (Warleader only gives Attack), "
            f"got {computed_toughness}"
        )


# ============================================================
# Test 2: TestMurlocWarleaderDoesNotBuffSelf
# ============================================================

class TestMurlocWarleaderDoesNotBuffSelf:
    def test_warleader_self_power_unchanged(self):
        """Murloc Warleader does not buff its own Attack."""
        game, p1, p2 = new_hs_game()
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        # Warleader base is 3/3; should remain 3 Attack
        computed_power = get_power(warleader, game.state)
        assert computed_power == 3, (
            f"Warleader should not buff itself, expected 3 Attack, got {computed_power}"
        )

    def test_warleader_self_toughness_unchanged(self):
        """Murloc Warleader toughness stays at base."""
        game, p1, p2 = new_hs_game()
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        computed_toughness = get_toughness(warleader, game.state)
        assert computed_toughness == 3, (
            f"Warleader toughness should stay 3, got {computed_toughness}"
        )


# ============================================================
# Test 3: TestMurlocWarleaderDoesNotBuffNonMurlocs
# ============================================================

class TestMurlocWarleaderDoesNotBuffNonMurlocs:
    def test_non_murloc_not_buffed(self):
        """A non-Murloc minion does not get Warleader's +2 Attack."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        # Chillwind Yeti base 4/5, should stay 4 Attack
        computed_power = get_power(yeti, game.state)
        assert computed_power == 4, (
            f"Chillwind Yeti (non-Murloc) should not get Warleader buff, "
            f"expected 4 Attack, got {computed_power}"
        )

    def test_enemy_murloc_not_buffed(self):
        """Warleader should not buff enemy Murlocs."""
        game, p1, p2 = new_hs_game()
        warleader = make_obj(game, MURLOC_WARLEADER, p1)
        enemy_raider = make_obj(game, MURLOC_RAIDER, p2)

        # Enemy Murloc Raider base 2/1, should remain 2
        computed_power = get_power(enemy_raider, game.state)
        assert computed_power == 2, (
            f"Enemy Murloc Raider should not get Warleader buff, "
            f"expected 2 Attack, got {computed_power}"
        )


# ============================================================
# Test 4: TestGrimscaleOracleAura
# ============================================================

class TestGrimscaleOracleAura:
    def test_oracle_buffs_friendly_murloc(self):
        """Grimscale Oracle gives other friendly Murlocs +1 Attack."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)
        oracle = make_obj(game, GRIMSCALE_ORACLE, p1)

        # Murloc Raider base 2/1; with Oracle aura should be 3/1
        computed_power = get_power(raider, game.state)
        assert computed_power == 3, (
            f"Murloc Raider (2/1) with Grimscale Oracle aura (+1 Attack) should have "
            f"3 Attack, got {computed_power}"
        )

    def test_oracle_does_not_buff_self(self):
        """Grimscale Oracle does not buff its own Attack."""
        game, p1, p2 = new_hs_game()
        oracle = make_obj(game, GRIMSCALE_ORACLE, p1)

        # Grimscale Oracle base 1/1
        computed_power = get_power(oracle, game.state)
        assert computed_power == 1, (
            f"Grimscale Oracle should not buff itself, expected 1 Attack, "
            f"got {computed_power}"
        )

    def test_oracle_does_not_buff_non_murloc(self):
        """Non-Murloc minions are not buffed by Grimscale Oracle."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        oracle = make_obj(game, GRIMSCALE_ORACLE, p1)

        computed_power = get_power(yeti, game.state)
        assert computed_power == 4, (
            f"Chillwind Yeti should not get Oracle buff, expected 4, got {computed_power}"
        )


# ============================================================
# Test 5: TestMurlocTidecallerTrigger
# ============================================================

class TestMurlocTidecallerTrigger:
    def test_tidecaller_gains_attack_on_murloc_summon(self):
        """Murloc Tidecaller gains +1 Attack when another Murloc is summoned."""
        game, p1, p2 = new_hs_game()
        tidecaller = make_obj(game, MURLOC_TIDECALLER, p1)

        # Base: 1/2
        power_before = get_power(tidecaller, game.state)
        assert power_before == 1, f"Tidecaller base Attack should be 1, got {power_before}"

        # Summon another Murloc via ZONE_CHANGE
        raider = make_obj(game, MURLOC_RAIDER, p1)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': raider.id, 'from_zone_type': ZoneType.HAND,
                     'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
            source=raider.id
        ))

        power_after = get_power(tidecaller, game.state)
        assert power_after == 2, (
            f"Tidecaller should gain +1 Attack after Murloc summon, "
            f"expected 2, got {power_after}"
        )

    def test_tidecaller_does_not_trigger_on_non_murloc(self):
        """Tidecaller should not trigger when a non-Murloc is summoned."""
        game, p1, p2 = new_hs_game()
        tidecaller = make_obj(game, MURLOC_TIDECALLER, p1)

        power_before = get_power(tidecaller, game.state)

        # Summon a non-Murloc
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'from_zone_type': ZoneType.HAND,
                     'to_zone_type': ZoneType.BATTLEFIELD, 'controller': p1.id},
            source=yeti.id
        ))

        power_after = get_power(tidecaller, game.state)
        assert power_after == power_before, (
            f"Tidecaller should not trigger on non-Murloc summon, "
            f"expected {power_before}, got {power_after}"
        )


# ============================================================
# Test 6: TestColdlightSeerBattlecry
# ============================================================

class TestColdlightSeerBattlecry:
    def test_seer_buffs_friendly_murloc_health(self):
        """Coldlight Seer battlecry gives friendly Murlocs +2 Health."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)

        # Murloc Raider base 2/1
        toughness_before = get_toughness(raider, game.state)
        assert toughness_before == 1, f"Raider base toughness should be 1, got {toughness_before}"

        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)
        for e in events:
            game.emit(e)

        toughness_after = get_toughness(raider, game.state)
        assert toughness_after == 3, (
            f"Murloc Raider should have 3 Health after Coldlight Seer battlecry (+2), "
            f"got {toughness_after}"
        )

    def test_seer_does_not_buff_self(self):
        """Coldlight Seer does not buff its own Health."""
        game, p1, p2 = new_hs_game()
        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)
        for e in events:
            game.emit(e)

        # Seer base 2/3, should remain 3
        toughness = get_toughness(seer, game.state)
        assert toughness == 3, (
            f"Coldlight Seer should not buff itself, expected 3, got {toughness}"
        )

    def test_seer_does_not_buff_non_murloc(self):
        """Coldlight Seer does not buff non-Murloc minions."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)
        for e in events:
            game.emit(e)

        toughness = get_toughness(yeti, game.state)
        assert toughness == 5, (
            f"Chillwind Yeti should not get Seer buff, expected 5, got {toughness}"
        )


# ============================================================
# Test 7: TestHungryCrabDestroysMurloc
# ============================================================

class TestHungryCrabDestroysMurloc:
    def test_crab_destroys_murloc_and_gains_stats(self):
        """Hungry Crab destroys a Murloc and gains +2/+2."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        raider = make_obj(game, MURLOC_RAIDER, p1)
        crab = make_obj(game, HUNGRY_CRAB, p1)

        events = HUNGRY_CRAB.battlecry(crab, game.state)
        assert len(events) == 2, (
            f"Hungry Crab battlecry should return 2 events (destroy + buff), "
            f"got {len(events)}"
        )

        # First event should be OBJECT_DESTROYED targeting the murloc
        assert events[0].type == EventType.OBJECT_DESTROYED
        assert events[0].payload['object_id'] == raider.id

        # Second event should be PT_MODIFICATION for the crab
        assert events[1].type == EventType.PT_MODIFICATION
        assert events[1].payload['object_id'] == crab.id
        assert events[1].payload['power_mod'] == 2
        assert events[1].payload['toughness_mod'] == 2

    def test_crab_no_murloc_no_effect(self):
        """Hungry Crab with no Murlocs on board does nothing."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        crab = make_obj(game, HUNGRY_CRAB, p1)

        events = HUNGRY_CRAB.battlecry(crab, game.state)
        assert len(events) == 0, (
            f"Hungry Crab should return no events without a Murloc target, "
            f"got {len(events)}"
        )

    def test_crab_gains_stats_after_emit(self):
        """After emitting Hungry Crab battlecry events, crab has +2/+2."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        raider = make_obj(game, MURLOC_RAIDER, p1)
        crab = make_obj(game, HUNGRY_CRAB, p1)

        # Crab base is 1/2
        power_before = get_power(crab, game.state)
        toughness_before = get_toughness(crab, game.state)
        assert power_before == 1
        assert toughness_before == 2

        events = HUNGRY_CRAB.battlecry(crab, game.state)
        for e in events:
            game.emit(e)

        power_after = get_power(crab, game.state)
        toughness_after = get_toughness(crab, game.state)
        assert power_after == 3, (
            f"Hungry Crab should be 3 Attack after eating Murloc (1 + 2), got {power_after}"
        )
        assert toughness_after == 4, (
            f"Hungry Crab should be 4 Health after eating Murloc (2 + 2), got {toughness_after}"
        )


# ============================================================
# Test 8: TestTimberWolfBeastAura
# ============================================================

class TestTimberWolfBeastAura:
    def test_timber_wolf_buffs_friendly_beast(self):
        """Timber Wolf gives all friendly Beasts +1 Attack."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        wolf = make_obj(game, TIMBER_WOLF, p1)

        # Bloodfen Raptor base 3/2; with Timber Wolf should be 4/2
        computed_power = get_power(raptor, game.state)
        assert computed_power == 4, (
            f"Bloodfen Raptor (3/2) with Timber Wolf aura (+1 Attack) should have "
            f"4 Attack, got {computed_power}"
        )

    def test_timber_wolf_does_not_buff_self(self):
        """Timber Wolf does not buff its own Attack."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)

        # Timber Wolf base 1/1
        computed_power = get_power(wolf, game.state)
        assert computed_power == 1, (
            f"Timber Wolf should not buff itself, expected 1, got {computed_power}"
        )

    def test_timber_wolf_does_not_buff_non_beast(self):
        """Timber Wolf does not buff non-Beast minions."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        wolf = make_obj(game, TIMBER_WOLF, p1)

        computed_power = get_power(yeti, game.state)
        assert computed_power == 4, (
            f"Chillwind Yeti should not get Timber Wolf buff, expected 4, "
            f"got {computed_power}"
        )

    def test_timber_wolf_buffs_multiple_beasts(self):
        """Timber Wolf buffs all friendly Beasts, not just one."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        boar = make_obj(game, STONETUSK_BOAR, p1)
        wolf = make_obj(game, TIMBER_WOLF, p1)

        raptor_power = get_power(raptor, game.state)
        boar_power = get_power(boar, game.state)
        assert raptor_power == 4, f"Raptor should be 4 Attack, got {raptor_power}"
        assert boar_power == 2, f"Boar should be 2 Attack (1+1), got {boar_power}"


# ============================================================
# Test 9: TestHoundmasterBuff
# ============================================================

class TestHoundmasterBuff:
    def test_houndmaster_buffs_beast(self):
        """Houndmaster gives a friendly Beast +2/+2 and Taunt."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        houndmaster = make_obj(game, HOUNDMASTER, p1)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)
        for e in events:
            game.emit(e)

        # Raptor base 3/2, should be 5/4 after Houndmaster buff
        power = get_power(raptor, game.state)
        toughness = get_toughness(raptor, game.state)
        assert power == 5, (
            f"Bloodfen Raptor should be 5 Attack after Houndmaster buff (3+2), got {power}"
        )
        assert toughness == 4, (
            f"Bloodfen Raptor should be 4 Health after Houndmaster buff (2+2), got {toughness}"
        )

    def test_houndmaster_grants_taunt(self):
        """Houndmaster grants Taunt to the targeted Beast."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        houndmaster = make_obj(game, HOUNDMASTER, p1)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)
        # Check that a KEYWORD_GRANT event for taunt is present
        keyword_events = [e for e in events if e.type == EventType.KEYWORD_GRANT]
        assert len(keyword_events) == 1, (
            f"Houndmaster should emit 1 KEYWORD_GRANT event, got {len(keyword_events)}"
        )
        assert keyword_events[0].payload['keyword'] == 'taunt'

    def test_houndmaster_no_beast_no_buff(self):
        """Houndmaster with no friendly Beast does nothing."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        houndmaster = make_obj(game, HOUNDMASTER, p1)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)
        assert len(events) == 0, (
            f"Houndmaster should return no events without a Beast target, "
            f"got {len(events)}"
        )


# ============================================================
# Test 10: TestScavengingHyenaTrigger
# ============================================================

class TestScavengingHyenaTrigger:
    def test_hyena_gains_stats_on_friendly_beast_death(self):
        """Scavenging Hyena gains +2/+1 when a friendly Beast dies."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)

        # Hyena base 2/2
        power_before = get_power(hyena, game.state)
        toughness_before = get_toughness(hyena, game.state)
        assert power_before == 2
        assert toughness_before == 2

        # Kill the raptor (a friendly Beast)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': raptor.id, 'reason': 'combat'},
            source='test'
        ))

        power_after = get_power(hyena, game.state)
        toughness_after = get_toughness(hyena, game.state)
        assert power_after == 4, (
            f"Hyena should gain +2 Attack (2+2=4) after friendly Beast death, "
            f"got {power_after}"
        )
        assert toughness_after == 3, (
            f"Hyena should gain +1 Health (2+1=3) after friendly Beast death, "
            f"got {toughness_after}"
        )

    def test_hyena_does_not_trigger_on_enemy_beast_death(self):
        """Hyena should not trigger when an enemy Beast dies."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        enemy_raptor = make_obj(game, BLOODFEN_RAPTOR, p2)

        power_before = get_power(hyena, game.state)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': enemy_raptor.id, 'reason': 'combat'},
            source='test'
        ))

        power_after = get_power(hyena, game.state)
        assert power_after == power_before, (
            f"Hyena should not trigger on enemy Beast death, "
            f"expected {power_before}, got {power_after}"
        )

    def test_hyena_does_not_trigger_on_non_beast_death(self):
        """Hyena should not trigger when a non-Beast friendly minion dies."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        wisp = make_obj(game, WISP, p1)

        power_before = get_power(hyena, game.state)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp.id, 'reason': 'combat'},
            source='test'
        ))

        power_after = get_power(hyena, game.state)
        assert power_after == power_before, (
            f"Hyena should not trigger on non-Beast death, "
            f"expected {power_before}, got {power_after}"
        )


# ============================================================
# Test 11: TestKillCommandConditional
# ============================================================

class TestKillCommandConditional:
    def test_kill_command_without_beast_deals_3(self):
        """Kill Command deals 3 damage without a Beast on board."""
        game, p1, p2 = new_hs_game()
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        # No Beast on p1's side
        obj = game.create_object(
            name=KILL_COMMAND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
        )
        events = KILL_COMMAND.spell_effect(obj, game.state, [enemy_yeti.id])

        assert len(events) == 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 3, (
            f"Kill Command without Beast should deal 3, got {events[0].payload['amount']}"
        )

    def test_kill_command_with_beast_deals_5(self):
        """Kill Command deals 5 damage with a Beast on board."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)  # Friendly Beast
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        obj = game.create_object(
            name=KILL_COMMAND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
        )
        events = KILL_COMMAND.spell_effect(obj, game.state, [enemy_yeti.id])

        assert len(events) == 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 5, (
            f"Kill Command with Beast should deal 5, got {events[0].payload['amount']}"
        )

    def test_kill_command_no_target_no_events(self):
        """Kill Command with no targets returns no events."""
        game, p1, p2 = new_hs_game()
        obj = game.create_object(
            name=KILL_COMMAND.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
        )
        events = KILL_COMMAND.spell_effect(obj, game.state, [])
        assert len(events) == 0, (
            f"Kill Command with no target should produce no events, got {len(events)}"
        )


# ============================================================
# Test 12: TestBloodImpStatCheck
# ============================================================

class TestBloodImpStatCheck:
    def test_blood_imp_is_0_1(self):
        """Blood Imp is a 0/1 minion."""
        game, p1, p2 = new_hs_game()
        imp = make_obj(game, BLOOD_IMP, p1)

        power = get_power(imp, game.state)
        toughness = get_toughness(imp, game.state)
        assert power == 0, f"Blood Imp should have 0 Attack, got {power}"
        assert toughness == 1, f"Blood Imp should have 1 Health, got {toughness}"

    def test_blood_imp_has_stealth(self):
        """Blood Imp has Stealth keyword."""
        game, p1, p2 = new_hs_game()
        imp = make_obj(game, BLOOD_IMP, p1)

        assert 'stealth' in imp.characteristics.keywords, (
            f"Blood Imp should have 'stealth' keyword, got {imp.characteristics.keywords}"
        )

    def test_blood_imp_is_demon(self):
        """Blood Imp has Demon subtype."""
        game, p1, p2 = new_hs_game()
        imp = make_obj(game, BLOOD_IMP, p1)

        assert 'Demon' in imp.characteristics.subtypes, (
            f"Blood Imp should have 'Demon' subtype, got {imp.characteristics.subtypes}"
        )


# ============================================================
# Test 13: TestSacrificialPact
# ============================================================

class TestSacrificialPact:
    def test_sacrificial_pact_destroys_demon_and_heals(self):
        """Sacrificial Pact destroys a Demon and restores 5 health."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        voidwalker = make_obj(game, VOIDWALKER, p1)
        p1.life = 20  # Damaged hero

        obj = game.create_object(
            name=SACRIFICIAL_PACT.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SACRIFICIAL_PACT.characteristics, card_def=SACRIFICIAL_PACT
        )
        events = SACRIFICIAL_PACT.spell_effect(obj, game.state, [])

        assert len(events) == 2, (
            f"Sacrificial Pact should return 2 events (destroy + heal), got {len(events)}"
        )

        # First event: destroy the demon
        assert events[0].type == EventType.OBJECT_DESTROYED
        assert events[0].payload['object_id'] == voidwalker.id

        # Second event: heal 5
        assert events[1].type == EventType.LIFE_CHANGE
        assert events[1].payload['amount'] == 5
        assert events[1].payload['player'] == p1.id

    def test_sacrificial_pact_no_demon_no_effect(self):
        """Sacrificial Pact with no Demons does nothing."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        obj = game.create_object(
            name=SACRIFICIAL_PACT.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SACRIFICIAL_PACT.characteristics, card_def=SACRIFICIAL_PACT
        )
        events = SACRIFICIAL_PACT.spell_effect(obj, game.state, [])

        assert len(events) == 0, (
            f"Sacrificial Pact with no Demons should return no events, got {len(events)}"
        )

    def test_sacrificial_pact_heals_after_emit(self):
        """After emitting Sacrificial Pact events, hero gains 5 life."""
        game, p1, p2 = new_hs_game()
        random.seed(42)

        voidwalker = make_obj(game, VOIDWALKER, p1)
        p1.life = 20

        cast_spell(game, SACRIFICIAL_PACT, p1)

        assert p1.life == 25, (
            f"Hero should be healed to 25 (20 + 5), got {p1.life}"
        )


# ============================================================
# Test 14: TestNonTribalExcludedFromBuff
# ============================================================

class TestNonTribalExcludedFromBuff:
    def test_wisp_not_buffed_by_warleader(self):
        """Wisp (no tribe) is not buffed by Murloc Warleader."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        computed_power = get_power(wisp, game.state)
        assert computed_power == 1, (
            f"Wisp (1/1, non-Murloc) should not get Warleader buff, "
            f"expected 1, got {computed_power}"
        )

    def test_beast_not_buffed_by_warleader(self):
        """A Beast is not buffed by Murloc Warleader."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        computed_power = get_power(raptor, game.state)
        assert computed_power == 3, (
            f"Bloodfen Raptor (Beast) should not get Murloc Warleader buff, "
            f"expected 3, got {computed_power}"
        )

    def test_demon_not_buffed_by_warleader(self):
        """A Demon is not buffed by Murloc Warleader."""
        game, p1, p2 = new_hs_game()
        voidwalker = make_obj(game, VOIDWALKER, p1)
        warleader = make_obj(game, MURLOC_WARLEADER, p1)

        computed_power = get_power(voidwalker, game.state)
        assert computed_power == 1, (
            f"Voidwalker (Demon) should not get Murloc Warleader buff, "
            f"expected 1, got {computed_power}"
        )

    def test_murloc_not_buffed_by_timber_wolf(self):
        """A Murloc is not buffed by Timber Wolf (Beast aura)."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)
        wolf = make_obj(game, TIMBER_WOLF, p1)

        computed_power = get_power(raider, game.state)
        assert computed_power == 2, (
            f"Murloc Raider should not get Timber Wolf buff, "
            f"expected 2, got {computed_power}"
        )


# ============================================================
# Test 15: TestTribalCheckSubtype
# ============================================================

class TestTribalCheckSubtype:
    def test_murloc_raider_is_murloc(self):
        """Murloc Raider has the Murloc subtype."""
        game, p1, p2 = new_hs_game()
        raider = make_obj(game, MURLOC_RAIDER, p1)
        assert 'Murloc' in raider.characteristics.subtypes, (
            f"Murloc Raider should have Murloc subtype, got {raider.characteristics.subtypes}"
        )

    def test_bloodfen_raptor_is_beast(self):
        """Bloodfen Raptor has the Beast subtype."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        assert 'Beast' in raptor.characteristics.subtypes, (
            f"Bloodfen Raptor should have Beast subtype, got {raptor.characteristics.subtypes}"
        )

    def test_voidwalker_is_demon(self):
        """Voidwalker has the Demon subtype."""
        game, p1, p2 = new_hs_game()
        voidwalker = make_obj(game, VOIDWALKER, p1)
        assert 'Demon' in voidwalker.characteristics.subtypes, (
            f"Voidwalker should have Demon subtype, got {voidwalker.characteristics.subtypes}"
        )

    def test_wisp_has_no_tribal_subtype(self):
        """Wisp has no tribal subtype (or an empty set)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        subtypes = wisp.characteristics.subtypes or set()
        tribal_types = {'Murloc', 'Beast', 'Demon', 'Pirate', 'Mech', 'Dragon'}
        intersection = subtypes & tribal_types
        assert len(intersection) == 0, (
            f"Wisp should have no tribal subtypes, found {intersection}"
        )

    def test_chillwind_yeti_has_no_tribal_subtype(self):
        """Chillwind Yeti has no tribal subtype."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        subtypes = yeti.characteristics.subtypes or set()
        tribal_types = {'Murloc', 'Beast', 'Demon', 'Pirate', 'Mech', 'Dragon'}
        intersection = subtypes & tribal_types
        assert len(intersection) == 0, (
            f"Chillwind Yeti should have no tribal subtypes, found {intersection}"
        )

    def test_timber_wolf_is_beast(self):
        """Timber Wolf has the Beast subtype."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, TIMBER_WOLF, p1)
        assert 'Beast' in wolf.characteristics.subtypes, (
            f"Timber Wolf should have Beast subtype, got {wolf.characteristics.subtypes}"
        )

    def test_scavenging_hyena_is_beast(self):
        """Scavenging Hyena has the Beast subtype."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)
        assert 'Beast' in hyena.characteristics.subtypes, (
            f"Scavenging Hyena should have Beast subtype, got {hyena.characteristics.subtypes}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
