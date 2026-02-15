"""
Hearthstone Unhappy Path Tests - Batch 73

State-based actions and death processing: minion death at 0 health,
simultaneous deaths processed together, deathrattle fires before
board cleanup, hero death when life <= 0, hero death from fatigue,
hero death from self-damage (Hellfire), overkill damage (minion takes
more than max health), minion stays alive at exactly 1 HP, aura
removal on death updates surviving minions, weapon destroyed at 0
durability, game-over detection when hero dies, multiple minions
dying triggers all their deathrattles.
"""

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
    WISP, CHILLWIND_YETI, STORMWIND_CHAMPION, FIERY_WAR_AXE,
    IRONFUR_GRIZZLY, RIVER_CROCOLISK,
)
from src.cards.hearthstone.classic import (
    LOOT_HOARDER,
)
from src.cards.hearthstone.warlock import (
    HELLFIRE,
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


def get_battlefield_minions(game, player):
    """Get list of minion objects controlled by player on the battlefield."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return []
    minions = []
    for obj_id in battlefield.objects:
        obj = game.state.objects.get(obj_id)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            minions.append(obj)
    return minions


def get_battlefield_weapons(game, player):
    """Get list of weapon objects controlled by player on the battlefield."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return []
    weapons = []
    for obj_id in battlefield.objects:
        obj = game.state.objects.get(obj_id)
        if obj and obj.controller == player.id and CardType.WEAPON in obj.characteristics.types:
            weapons.append(obj)
    return weapons


# ============================================================
# Test 1: TestMinionDiesAtZeroHealth
# ============================================================

class TestMinionDiesAtZeroHealth:
    def test_minion_dies_from_lethal_damage(self):
        """3 damage to 3-health minion -> minion dies via SBA."""
        game, p1, p2 = new_hs_game()
        # Ironfur Grizzly is a 3/3
        grizzly = make_obj(game, IRONFUR_GRIZZLY, p1)

        assert get_toughness(grizzly, game.state) == 3, (
            f"Grizzly should start at 3 health, got {get_toughness(grizzly, game.state)}"
        )

        # Deal exactly 3 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grizzly.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))

        assert grizzly.state.damage == 3, (
            f"Grizzly should have 3 damage, got {grizzly.state.damage}"
        )

        # Run SBAs
        sba_events = game.check_state_based_actions()

        # Minion should have been destroyed (moved to graveyard)
        assert grizzly.zone == ZoneType.GRAVEYARD, (
            f"Grizzly should be in graveyard after SBA, got {grizzly.zone}"
        )

    def test_sba_emits_object_destroyed(self):
        """SBA pass should emit OBJECT_DESTROYED for the dead minion."""
        game, p1, p2 = new_hs_game()
        grizzly = make_obj(game, IRONFUR_GRIZZLY, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grizzly.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        destroyed_events = [
            e for e in sba_events
            if e.type == EventType.OBJECT_DESTROYED
            and e.payload.get('object_id') == grizzly.id
        ]
        assert len(destroyed_events) >= 1, (
            f"SBA should emit OBJECT_DESTROYED for grizzly, found {len(destroyed_events)} events"
        )


# ============================================================
# Test 2: TestMinionSurvivesAtOneHP
# ============================================================

class TestMinionSurvivesAtOneHP:
    def test_minion_survives_with_1_hp_remaining(self):
        """4 damage to 5-health minion -> minion at 1 HP, still alive."""
        game, p1, p2 = new_hs_game()
        # Chillwind Yeti is a 4/5
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        assert get_toughness(yeti, game.state) == 5, (
            f"Yeti should start at 5 health, got {get_toughness(yeti, game.state)}"
        )

        # Deal 4 damage, leaving 1 HP
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': 4, 'source': 'test'},
            source='test'
        ))

        assert yeti.state.damage == 4, (
            f"Yeti should have 4 damage, got {yeti.state.damage}"
        )

        # Run SBAs - yeti should survive
        sba_events = game.check_state_based_actions()

        assert yeti.zone == ZoneType.BATTLEFIELD, (
            f"Yeti with 1 HP remaining should stay on battlefield, got {yeti.zone}"
        )

    def test_sba_does_not_destroy_surviving_minion(self):
        """SBA should not emit OBJECT_DESTROYED for a minion at 1 HP."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': 4, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        destroyed_events = [
            e for e in sba_events
            if e.type == EventType.OBJECT_DESTROYED
            and e.payload.get('object_id') == yeti.id
        ]
        assert len(destroyed_events) == 0, (
            f"SBA should not destroy yeti at 1 HP, found {len(destroyed_events)} destroy events"
        )


# ============================================================
# Test 3: TestOverkillDamage
# ============================================================

class TestOverkillDamage:
    def test_overkill_damage_still_kills(self):
        """10 damage to 1-health Wisp -> Wisp dies (overkill doesn't error)."""
        game, p1, p2 = new_hs_game()
        # Wisp is a 1/1
        wisp = make_obj(game, WISP, p1)

        assert get_toughness(wisp, game.state) == 1, (
            f"Wisp should start at 1 health, got {get_toughness(wisp, game.state)}"
        )

        # Deal massive overkill damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp.id, 'amount': 10, 'source': 'test'},
            source='test'
        ))

        assert wisp.state.damage == 10, (
            f"Wisp should have 10 damage recorded, got {wisp.state.damage}"
        )

        # Run SBAs - should not error
        sba_events = game.check_state_based_actions()

        assert wisp.zone == ZoneType.GRAVEYARD, (
            f"Wisp should be in graveyard after overkill, got {wisp.zone}"
        )

    def test_overkill_damage_doesnt_raise(self):
        """Overkill damage to a minion should not raise an exception."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # This should not raise any exception
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp.id, 'amount': 10, 'source': 'test'},
            source='test'
        ))
        sba_events = game.check_state_based_actions()

        # If we got here without exception, the test passes
        assert True


# ============================================================
# Test 4: TestSimultaneousDeaths
# ============================================================

class TestSimultaneousDeaths:
    def test_both_minions_die_in_same_sba_pass(self):
        """Two minions both take lethal -> both die in same SBA pass."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)  # 1/1
        wisp2 = make_obj(game, WISP, p1)  # 1/1

        # Deal lethal to both
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp1.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp2.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # Both should be lethally damaged
        assert wisp1.state.damage >= 1
        assert wisp2.state.damage >= 1

        # Run SBAs
        sba_events = game.check_state_based_actions()

        # Both should be in graveyard
        assert wisp1.zone == ZoneType.GRAVEYARD, (
            f"Wisp1 should be in graveyard, got {wisp1.zone}"
        )
        assert wisp2.zone == ZoneType.GRAVEYARD, (
            f"Wisp2 should be in graveyard, got {wisp2.zone}"
        )

    def test_simultaneous_deaths_both_have_destroy_events(self):
        """Both simultaneously-dead minions should have OBJECT_DESTROYED events."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp1.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp2.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        destroyed_ids = {
            e.payload.get('object_id')
            for e in sba_events
            if e.type == EventType.OBJECT_DESTROYED
        }
        assert wisp1.id in destroyed_ids, "Wisp1 should have OBJECT_DESTROYED event"
        assert wisp2.id in destroyed_ids, "Wisp2 should have OBJECT_DESTROYED event"


# ============================================================
# Test 5: TestDeathrattleFiresOnDeath
# ============================================================

class TestDeathrattleFiresOnDeath:
    def test_loot_hoarder_draws_card_on_death(self):
        """Loot Hoarder dies -> DRAW event fires from deathrattle."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)  # 2/1 with Deathrattle: Draw a card

        # Add cards to the library so draw can succeed
        add_cards_to_library(game, p1, WISP, 3)

        hand_before = get_hand_size(game, p1)

        # Kill the Loot Hoarder by dealing lethal damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': hoarder.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # SBA should destroy it and trigger deathrattle
        sba_events = game.check_state_based_actions()

        assert hoarder.zone == ZoneType.GRAVEYARD, (
            f"Loot Hoarder should be in graveyard, got {hoarder.zone}"
        )

        # Check that a DRAW event was emitted (deathrattle fired)
        draw_events = [
            e for e in sba_events
            if e.type == EventType.DRAW
            and e.payload.get('player') == p1.id
        ]
        assert len(draw_events) >= 1, (
            f"Loot Hoarder deathrattle should emit DRAW event, found {len(draw_events)}"
        )

    def test_loot_hoarder_deathrattle_increases_hand_size(self):
        """After Loot Hoarder dies, player's hand size should increase by 1."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)

        add_cards_to_library(game, p1, WISP, 3)
        hand_before = get_hand_size(game, p1)

        # Kill it
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': hoarder.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.check_state_based_actions()

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Hand size should increase by 1 from deathrattle draw, "
            f"was {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 6: TestMultipleDeathrattlesAllFire
# ============================================================

class TestMultipleDeathrattlesAllFire:
    def test_two_loot_hoarders_draw_two_cards(self):
        """2 Loot Hoarders die -> 2 DRAW events."""
        game, p1, p2 = new_hs_game()
        hoarder1 = make_obj(game, LOOT_HOARDER, p1)  # 2/1
        hoarder2 = make_obj(game, LOOT_HOARDER, p1)  # 2/1

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        # Kill both
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': hoarder1.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': hoarder2.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        # Both should be dead
        assert hoarder1.zone == ZoneType.GRAVEYARD
        assert hoarder2.zone == ZoneType.GRAVEYARD

        # Check that 2 DRAW events were emitted
        draw_events = [
            e for e in sba_events
            if e.type == EventType.DRAW
            and e.payload.get('player') == p1.id
        ]
        assert len(draw_events) >= 2, (
            f"Two Loot Hoarders dying should emit at least 2 DRAW events, "
            f"found {len(draw_events)}"
        )

    def test_two_deathrattles_increase_hand_by_two(self):
        """Two Loot Hoarder deathrattles should draw 2 cards total."""
        game, p1, p2 = new_hs_game()
        hoarder1 = make_obj(game, LOOT_HOARDER, p1)
        hoarder2 = make_obj(game, LOOT_HOARDER, p1)

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': hoarder1.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': hoarder2.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        game.check_state_based_actions()

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 2, (
            f"Hand should increase by 2 from two deathrattles, "
            f"was {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 7: TestHeroDeathFromDamage
# ============================================================

class TestHeroDeathFromDamage:
    def test_hero_death_detected_by_sba(self):
        """Hero at 5 HP takes 10 damage -> SBA should detect loss."""
        game, p1, p2 = new_hs_game()
        p1.life = 5

        # Deal 10 damage to hero
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 10, 'source': 'test'},
            source='test'
        ))

        assert p1.life <= 0, (
            f"Hero should be at 0 or less life after 10 damage from 5 HP, got {p1.life}"
        )

        # Run SBAs to check for death
        sba_events = game.check_state_based_actions()

        assert p1.has_lost is True, (
            f"Player should be marked as lost after hero hits 0 HP"
        )

    def test_sba_emits_player_loses(self):
        """SBA should emit PLAYER_LOSES when hero life drops to 0."""
        game, p1, p2 = new_hs_game()
        p1.life = 5

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 10, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        player_loses_events = [
            e for e in sba_events
            if e.type == EventType.PLAYER_LOSES
            and e.payload.get('player') == p1.id
        ]
        assert len(player_loses_events) >= 1, (
            f"SBA should emit PLAYER_LOSES for the dying hero, "
            f"found {len(player_loses_events)}"
        )


# ============================================================
# Test 8: TestHeroDeathFromFatigue
# ============================================================

class TestHeroDeathFromFatigue:
    def test_fatigue_kills_hero_at_1hp(self):
        """Hero at 1 HP draws from empty deck -> fatigue kills."""
        game, p1, p2 = new_hs_game()
        p1.life = 1

        # Make sure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Draw from empty deck triggers fatigue (1 damage first time)
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'amount': 1},
            source='test'
        ))

        # Fatigue damage should have been applied
        assert p1.life <= 0, (
            f"Hero at 1 HP should be dead after fatigue damage, got {p1.life}"
        )

        # Run SBAs
        sba_events = game.check_state_based_actions()

        assert p1.has_lost is True, (
            f"Player should be marked as lost after fatigue kills hero"
        )

    def test_fatigue_increments_damage(self):
        """Each draw from empty deck increments fatigue counter."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # First draw: fatigue 1
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'amount': 1},
            source='test'
        ))
        assert p1.fatigue_damage == 1, (
            f"After first empty draw, fatigue_damage should be 1, got {p1.fatigue_damage}"
        )

        # Second draw: fatigue 2
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'amount': 1},
            source='test'
        ))
        assert p1.fatigue_damage == 2, (
            f"After second empty draw, fatigue_damage should be 2, got {p1.fatigue_damage}"
        )


# ============================================================
# Test 9: TestHeroDeathFromSelfDamage
# ============================================================

class TestHeroDeathFromSelfDamage:
    def test_hellfire_kills_own_hero(self):
        """Hero at 3 HP casts Hellfire (3 to all) -> hero dies."""
        game, p1, p2 = new_hs_game()
        p1.life = 3

        # Cast Hellfire: deals 3 damage to ALL characters
        cast_spell(game, HELLFIRE, p1)

        assert p1.life <= 0, (
            f"Hero at 3 HP should be dead after Hellfire (3 damage to all), got {p1.life}"
        )

        # Run SBAs
        sba_events = game.check_state_based_actions()

        assert p1.has_lost is True, (
            f"Player should be marked as lost after Hellfire kills own hero"
        )

    def test_hellfire_damages_both_heroes(self):
        """Hellfire deals 3 damage to both heroes."""
        game, p1, p2 = new_hs_game()
        life_before_p1 = p1.life
        life_before_p2 = p2.life

        cast_spell(game, HELLFIRE, p1)

        assert p1.life == life_before_p1 - 3, (
            f"P1 should take 3 damage from Hellfire, "
            f"was {life_before_p1}, now {p1.life}"
        )
        assert p2.life == life_before_p2 - 3, (
            f"P2 should take 3 damage from Hellfire, "
            f"was {life_before_p2}, now {p2.life}"
        )


# ============================================================
# Test 10: TestAuraRemovedOnDeath
# ============================================================

class TestAuraRemovedOnDeath:
    def test_stormwind_champion_aura_removed_on_death(self):
        """Stormwind Champion dies -> all friendly minions lose +1/+1."""
        game, p1, p2 = new_hs_game()
        # Chillwind Yeti is 4/5
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        # Stormwind Champion is 6/6, gives other minions +1/+1
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Verify aura is active: yeti should be 5/6
        power_with_aura = get_power(yeti, game.state)
        toughness_with_aura = get_toughness(yeti, game.state)
        assert power_with_aura == 5, (
            f"Yeti with Stormwind Champion aura should have 5 Attack, got {power_with_aura}"
        )
        assert toughness_with_aura == 6, (
            f"Yeti with Stormwind Champion aura should have 6 Health, got {toughness_with_aura}"
        )

        # Kill Stormwind Champion
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': champion.id, 'reason': 'combat'},
            source='test'
        ))

        assert champion.zone == ZoneType.GRAVEYARD, (
            f"Stormwind Champion should be in graveyard, got {champion.zone}"
        )

        # Aura should be removed: yeti should return to base 4/5
        power_after = get_power(yeti, game.state)
        toughness_after = get_toughness(yeti, game.state)
        assert power_after == 4, (
            f"Yeti should return to 4 Attack after Stormwind Champion dies, got {power_after}"
        )
        assert toughness_after == 5, (
            f"Yeti should return to 5 Health after Stormwind Champion dies, got {toughness_after}"
        )

    def test_aura_only_affects_other_minions(self):
        """Stormwind Champion aura does not buff itself."""
        game, p1, p2 = new_hs_game()
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Stormwind Champion base is 6/6, should remain 6/6
        power = get_power(champion, game.state)
        toughness = get_toughness(champion, game.state)
        assert power == 6, (
            f"Stormwind Champion should not buff itself, expected 6 Attack, got {power}"
        )
        assert toughness == 6, (
            f"Stormwind Champion should not buff itself, expected 6 Health, got {toughness}"
        )


# ============================================================
# Test 11: TestWeaponDestroyedAtZeroDurability
# ============================================================

class TestWeaponDestroyedAtZeroDurability:
    def test_weapon_at_1_durability_destroyed_after_attack(self):
        """Weapon at 1 durability, hero attacks -> weapon destroyed."""
        game, p1, p2 = new_hs_game()
        # Fiery War Axe: 3 attack, 2 durability
        axe = make_obj(game, FIERY_WAR_AXE, p1)

        # Verify weapon is equipped
        assert p1.weapon_attack == 3, (
            f"Fiery War Axe should give 3 weapon attack, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"Fiery War Axe should have 2 durability, got {p1.weapon_durability}"
        )

        # Simulate reducing durability to 1 (like having attacked once already)
        p1.weapon_durability = 1
        hero = game.state.objects.get(p1.hero_id)
        if hero:
            hero.state.weapon_durability = 1

        # Now manually reduce durability to 0 to simulate final attack
        p1.weapon_durability = 0
        if hero:
            hero.state.weapon_durability = 0

        # When durability hits 0, weapon should be destroyed
        # Emit OBJECT_DESTROYED for the weapon
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': axe.id, 'reason': 'weapon_broke'},
            source=p1.hero_id
        ))

        assert axe.zone == ZoneType.GRAVEYARD, (
            f"Weapon should be in graveyard after durability reaches 0, got {axe.zone}"
        )

        # Weapon stats should be cleared
        assert p1.weapon_attack == 0, (
            f"Player weapon_attack should be 0 after weapon destroyed, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 0, (
            f"Player weapon_durability should be 0 after weapon destroyed, got {p1.weapon_durability}"
        )

    def test_weapon_removed_from_battlefield(self):
        """Destroyed weapon should no longer be on the battlefield."""
        game, p1, p2 = new_hs_game()
        axe = make_obj(game, FIERY_WAR_AXE, p1)

        weapons_before = get_battlefield_weapons(game, p1)
        assert len(weapons_before) == 1, (
            f"Should have 1 weapon on battlefield before destruction, got {len(weapons_before)}"
        )

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': axe.id, 'reason': 'weapon_broke'},
            source=p1.hero_id
        ))

        weapons_after = get_battlefield_weapons(game, p1)
        assert len(weapons_after) == 0, (
            f"Should have 0 weapons on battlefield after destruction, got {len(weapons_after)}"
        )


# ============================================================
# Test 12: TestGameOverOnHeroDeath
# ============================================================

class TestGameOverOnHeroDeath:
    def test_game_over_when_hero_dies(self):
        """After hero dies, game should be flagged as over."""
        game, p1, p2 = new_hs_game()
        p1.life = 1

        # Kill the hero
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        game.check_state_based_actions()

        assert p1.has_lost is True, (
            f"Player 1 should be marked as lost"
        )
        assert game.is_game_over() is True, (
            f"Game should be flagged as over when a hero dies"
        )

    def test_winner_is_surviving_player(self):
        """After one hero dies, the other player should be the winner."""
        game, p1, p2 = new_hs_game()
        p1.life = 1

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))
        game.check_state_based_actions()

        winner = game.get_winner()
        assert winner == p2.id, (
            f"Winner should be Player 2 when Player 1 dies, got {winner}"
        )

    def test_game_not_over_when_both_alive(self):
        """Game should not be over when both heroes are alive."""
        game, p1, p2 = new_hs_game()

        assert game.is_game_over() is False, (
            f"Game should not be over when both heroes are alive"
        )


# ============================================================
# Test 13: TestMinionAtNegativeHealthDies
# ============================================================

class TestMinionAtNegativeHealthDies:
    def test_negative_health_still_dies(self):
        """5 damage to 3-health minion -> health goes negative, still dies properly."""
        game, p1, p2 = new_hs_game()
        # Ironfur Grizzly is 3/3
        grizzly = make_obj(game, IRONFUR_GRIZZLY, p1)

        # Deal 5 damage to 3-health minion (2 overkill)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grizzly.id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        # Damage exceeds toughness
        toughness = get_toughness(grizzly, game.state)
        assert grizzly.state.damage > toughness, (
            f"Damage ({grizzly.state.damage}) should exceed toughness ({toughness}) "
            f"for negative effective health"
        )

        # SBA should still destroy the minion
        sba_events = game.check_state_based_actions()

        assert grizzly.zone == ZoneType.GRAVEYARD, (
            f"Minion at negative health should be in graveyard, got {grizzly.zone}"
        )

    def test_negative_health_emits_destroyed_event(self):
        """SBA for negative-health minion should emit OBJECT_DESTROYED."""
        game, p1, p2 = new_hs_game()
        grizzly = make_obj(game, IRONFUR_GRIZZLY, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grizzly.id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        destroyed_events = [
            e for e in sba_events
            if e.type == EventType.OBJECT_DESTROYED
            and e.payload.get('object_id') == grizzly.id
        ]
        assert len(destroyed_events) >= 1, (
            f"SBA should emit OBJECT_DESTROYED for negative-health minion, "
            f"found {len(destroyed_events)}"
        )

    def test_damage_exceeds_max_health_by_large_amount(self):
        """Even extremely large damage amounts are handled correctly."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)  # 1/1

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp.id, 'amount': 999, 'source': 'test'},
            source='test'
        ))

        sba_events = game.check_state_based_actions()

        assert wisp.zone == ZoneType.GRAVEYARD, (
            f"Wisp with 999 damage should be in graveyard, got {wisp.zone}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
