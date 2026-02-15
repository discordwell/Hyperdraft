"""
Hearthstone Unhappy Path Tests - Batch 78

Complete game flow simulations: aggro vs control multi-turn, zoo
flood the board, OTK combo setup over multiple turns, fatigue race
scenario, armor vs burst damage race, multiple draw engines running,
board clear + rebuild pattern, taunt wall vs charge minions, weapon
progression (equip->attack->reequip), hero power every turn, multiple
deathrattles on board during AOE, game ending conditions verified.
"""

import asyncio
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, STONETUSK_BOAR,
    MURLOC_RAIDER, FIERY_WAR_AXE, ARCANITE_REAPER,
    LEPER_GNOME, HARVEST_GOLEM, GOLDSHIRE_FOOTMAN,
    FROSTWOLF_GRUNT, IRONFUR_GRIZZLY, SEN_JIN_SHIELDMASTA,
    BOULDERFIST_OGRE,
)
from src.cards.hearthstone.classic import (
    FLAMESTRIKE, WOLFRIDER, LOOT_HOARDER, ABOMINATION,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Mage", class2="Warrior"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def new_hs_game_fresh_mana(class1="Mage", class2="Warrior"):
    """Create a fresh HS game with 0 mana (for multi-turn progression tests)."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
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


def play_minion(game, card_def, owner):
    """Play a minion from hand to battlefield (triggers ZONE_CHANGE interceptors)."""
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


def declare_attack(game, attacker_id, target_id):
    """Synchronously run an async declare_attack via a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        events = loop.run_until_complete(
            game.combat_manager.declare_attack(attacker_id, target_id)
        )
    finally:
        loop.close()
    return events


def add_cards_to_library(game, player, card_def, count):
    """Add card objects to a player's library for draw testing."""
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


def count_battlefield(game, player_id=None):
    """Count minions on battlefield, optionally filtered by controller."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return 0
    count = 0
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if not obj:
            continue
        if CardType.MINION not in obj.characteristics.types:
            continue
        if player_id and obj.controller != player_id:
            continue
        count += 1
    return count


def run_sba(game):
    """Manually check state-based actions (destroy lethal minions)."""
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
                source=oid
            ))


def end_turn(game, player):
    """Simulate end-of-turn phase for a player."""
    game.emit(Event(
        type=EventType.PHASE_END,
        payload={'phase': 'end', 'player': player.id},
        source='game'
    ))


def start_turn(game, player):
    """Simulate start-of-turn phase for a player (mana gain + refill)."""
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': player.id},
        source='game'
    ))
    game.mana_system.on_turn_start(player.id)


def equip_weapon(game, card_def, owner):
    """Equip a weapon by playing it from hand to battlefield with ZONE_CHANGE."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': owner.id,
        },
        source=obj.id
    ))
    return obj


# ============================================================
# Test 1: TestAggroRushdown
# ============================================================

class TestAggroRushdown:
    """P1 plays cheap minions turns 1-3, attacks face each turn. Verify damage accumulation."""

    def test_aggro_rushdown_damage_accumulates(self):
        """Play Stonetusk Boar each turn and attack face. Damage should accumulate."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        total_expected_damage = 0

        # Turn 1: Play Stonetusk Boar (1/1 Charge), attack face
        boar1 = make_obj(game, STONETUSK_BOAR, p1)
        # Charge allows attacking immediately
        events = declare_attack(game, boar1.id, p2.hero_id)
        assert len(events) > 0, "Charge minion should successfully attack"
        total_expected_damage += 1
        assert p2.life == 30 - total_expected_damage, (
            f"After turn 1 attack, P2 should be at {30 - total_expected_damage}, got {p2.life}"
        )

        # Turn 2: Play another Boar, attack with both
        boar2 = make_obj(game, STONETUSK_BOAR, p1)
        boar1.state.attacks_this_turn = 0  # Reset for new turn
        events1 = declare_attack(game, boar1.id, p2.hero_id)
        events2 = declare_attack(game, boar2.id, p2.hero_id)
        total_expected_damage += 2  # 1 + 1
        assert p2.life == 30 - total_expected_damage, (
            f"After turn 2 attacks, P2 should be at {30 - total_expected_damage}, got {p2.life}"
        )

        # Turn 3: Play Wolfrider (3/1 Charge), attack with all 3
        wolfrider = make_obj(game, WOLFRIDER, p1)
        boar1.state.attacks_this_turn = 0
        boar2.state.attacks_this_turn = 0
        declare_attack(game, boar1.id, p2.hero_id)
        declare_attack(game, boar2.id, p2.hero_id)
        declare_attack(game, wolfrider.id, p2.hero_id)
        total_expected_damage += 5  # 1 + 1 + 3
        assert p2.life == 30 - total_expected_damage, (
            f"After turn 3 attacks, P2 should be at {30 - total_expected_damage}, got {p2.life}"
        )

    def test_aggro_total_damage_over_three_turns(self):
        """Total damage dealt by aggro over 3 turns is correct."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        # Play 3 Stonetusk Boars (1/1 Charge)
        boars = []
        for _ in range(3):
            boars.append(make_obj(game, STONETUSK_BOAR, p1))

        # Turn 1: all 3 attack
        for boar in boars:
            declare_attack(game, boar.id, p2.hero_id)

        # Reset for turn 2
        for boar in boars:
            boar.state.attacks_this_turn = 0

        # Turn 2: all 3 attack again
        for boar in boars:
            declare_attack(game, boar.id, p2.hero_id)

        # Reset for turn 3
        for boar in boars:
            boar.state.attacks_this_turn = 0

        # Turn 3: all 3 attack again
        for boar in boars:
            declare_attack(game, boar.id, p2.hero_id)

        # 3 boars * 1 damage * 3 turns = 9 damage total
        assert p2.life == 21, (
            f"3 boars attacking 3 turns should deal 9 damage, P2 at {p2.life}"
        )


# ============================================================
# Test 2: TestBoardFlood
# ============================================================

class TestBoardFlood:
    """P1 fills board to 7 minions over 3 turns. Verify all present."""

    def test_board_fills_to_seven_over_three_turns(self):
        """Board fills to exactly 7 minions over 3 turns of play."""
        game, p1, p2 = new_hs_game()

        # Turn 1: Play 3 Wisps (0-cost)
        for _ in range(3):
            make_obj(game, WISP, p1)

        assert count_battlefield(game, p1.id) == 3, (
            f"After turn 1, should have 3 minions, got {count_battlefield(game, p1.id)}"
        )

        # Turn 2: Play 2 more Wisps
        for _ in range(2):
            make_obj(game, WISP, p1)

        assert count_battlefield(game, p1.id) == 5, (
            f"After turn 2, should have 5 minions, got {count_battlefield(game, p1.id)}"
        )

        # Turn 3: Play 2 more to cap at 7
        for _ in range(2):
            make_obj(game, WISP, p1)

        assert count_battlefield(game, p1.id) == 7, (
            f"After turn 3, should have 7 minions, got {count_battlefield(game, p1.id)}"
        )

    def test_board_flood_all_minions_are_alive(self):
        """All 7 flooded minions have zero damage."""
        game, p1, p2 = new_hs_game()

        minions = []
        for _ in range(7):
            minions.append(make_obj(game, WISP, p1))

        for i, minion in enumerate(minions):
            assert minion.state.damage == 0, (
                f"Minion {i} should have 0 damage, got {minion.state.damage}"
            )
            assert minion.zone == ZoneType.BATTLEFIELD, (
                f"Minion {i} should be on battlefield, got {minion.zone}"
            )


# ============================================================
# Test 3: TestBoardClearAndRebuild
# ============================================================

class TestBoardClearAndRebuild:
    """P1 builds board, P2 casts Flamestrike, P1 rebuilds next turn."""

    def test_flamestrike_clears_small_minions(self):
        """Flamestrike (4 damage) kills all P1 minions with 4 or less health."""
        game, p1, p2 = new_hs_game()

        # P1 builds a board of small minions (Wisps, Raptors, Murloc Raiders)
        wisp1 = make_obj(game, WISP, p1)           # 1/1
        wisp2 = make_obj(game, WISP, p1)           # 1/1
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)  # 3/2
        raider = make_obj(game, MURLOC_RAIDER, p1)    # 2/1

        assert count_battlefield(game, p1.id) == 4

        # P2 casts Flamestrike (deal 4 damage to all enemy minions)
        cast_spell(game, FLAMESTRIKE, p2)
        run_sba(game)

        # All P1 minions had <= 4 health, so all should be destroyed
        assert count_battlefield(game, p1.id) == 0, (
            f"All P1 minions should be dead after Flamestrike, "
            f"but {count_battlefield(game, p1.id)} remain"
        )

    def test_rebuild_after_board_clear(self):
        """P1 can rebuild a full board after P2 Flamestrikes."""
        game, p1, p2 = new_hs_game()

        # P1 builds initial board
        for _ in range(4):
            make_obj(game, WISP, p1)

        assert count_battlefield(game, p1.id) == 4

        # P2 Flamestrikes
        cast_spell(game, FLAMESTRIKE, p2)
        run_sba(game)
        assert count_battlefield(game, p1.id) == 0

        # P1 rebuilds next turn
        for _ in range(5):
            make_obj(game, CHILLWIND_YETI, p1)

        assert count_battlefield(game, p1.id) == 5, (
            f"P1 should have rebuilt to 5 minions, got {count_battlefield(game, p1.id)}"
        )

    def test_flamestrike_doesnt_kill_big_minion(self):
        """Flamestrike (4 damage) does not kill a 6/7 Boulderfist Ogre."""
        game, p1, p2 = new_hs_game()

        ogre = make_obj(game, BOULDERFIST_OGRE, p1)  # 6/7
        wisp = make_obj(game, WISP, p1)               # 1/1

        cast_spell(game, FLAMESTRIKE, p2)
        run_sba(game)

        # Ogre should survive (7 health - 4 damage = 3 remaining)
        assert ogre.state.damage == 4, (
            f"Ogre should have 4 damage from Flamestrike, got {ogre.state.damage}"
        )
        assert ogre.zone == ZoneType.BATTLEFIELD, (
            "Ogre should survive Flamestrike (7 health > 4 damage)"
        )
        # Wisp should be dead
        assert count_battlefield(game, p1.id) == 1, (
            "Only Ogre should survive, wisp should be dead"
        )


# ============================================================
# Test 4: TestFatigueRace
# ============================================================

class TestFatigueRace:
    """Both players draw from empty decks for 3 turns. Verify correct fatigue damage."""

    def test_fatigue_damage_increments(self):
        """Each empty-deck draw deals incrementing fatigue damage: 1, 2, 3..."""
        game, p1, p2 = new_hs_game()

        # Ensure libraries are empty
        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        # Draw 1: fatigue = 1 damage
        p1.fatigue_damage = 0
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))
        assert p1.life == 29, (
            f"After 1st fatigue draw, P1 should be at 29 HP, got {p1.life}"
        )

        # Draw 2: fatigue = 2 damage (total 3)
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))
        assert p1.life == 27, (
            f"After 2nd fatigue draw, P1 should be at 27 HP, got {p1.life}"
        )

        # Draw 3: fatigue = 3 damage (total 6)
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))
        assert p1.life == 24, (
            f"After 3rd fatigue draw, P1 should be at 24 HP, got {p1.life}"
        )

    def test_fatigue_race_both_players(self):
        """Both players take fatigue: P1 draws 3 times, P2 draws 3 times."""
        game, p1, p2 = new_hs_game()

        # Empty both libraries
        for pid in [p1.id, p2.id]:
            lib_key = f"library_{pid}"
            if lib_key in game.state.zones:
                game.state.zones[lib_key].objects.clear()

        p1.fatigue_damage = 0
        p2.fatigue_damage = 0

        # Simulate 3 "turns" of fatigue draws for each player
        for turn in range(1, 4):
            game.emit(Event(
                type=EventType.DRAW,
                payload={'player': p1.id, 'count': 1},
                source='test'
            ))
            game.emit(Event(
                type=EventType.DRAW,
                payload={'player': p2.id, 'count': 1},
                source='test'
            ))

        # P1: 1 + 2 + 3 = 6 damage -> 30 - 6 = 24
        assert p1.life == 24, (
            f"P1 should be at 24 HP after 3 fatigue draws, got {p1.life}"
        )
        # P2: same
        assert p2.life == 24, (
            f"P2 should be at 24 HP after 3 fatigue draws, got {p2.life}"
        )

    def test_fatigue_counter_tracks_correctly(self):
        """The fatigue_damage counter increments per draw from empty deck."""
        game, p1, p2 = new_hs_game()

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        p1.fatigue_damage = 0

        for expected in range(1, 4):
            game.emit(Event(
                type=EventType.DRAW,
                payload={'player': p1.id, 'count': 1},
                source='test'
            ))
            assert p1.fatigue_damage == expected, (
                f"After draw {expected}, fatigue_damage should be {expected}, "
                f"got {p1.fatigue_damage}"
            )


# ============================================================
# Test 5: TestWeaponProgression
# ============================================================

class TestWeaponProgression:
    """Warrior equips weapon, attacks 2 turns, weapon breaks, equips new weapon."""

    def test_weapon_equip_sets_stats(self):
        """Equipping Fiery War Axe gives 3 attack, 2 durability."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        equip_weapon(game, FIERY_WAR_AXE, p1)

        assert p1.weapon_attack == 3, (
            f"Fiery War Axe should give 3 attack, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"Fiery War Axe should have 2 durability, got {p1.weapon_durability}"
        )

    def test_weapon_attack_reduces_durability(self):
        """Attacking with weapon reduces durability by 1."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        equip_weapon(game, FIERY_WAR_AXE, p1)

        # Attack with hero
        events = declare_attack(game, p1.hero_id, p2.hero_id)
        assert len(events) > 0, "Hero with weapon should successfully attack"

        assert p1.weapon_durability == 1, (
            f"After 1 attack, durability should be 1, got {p1.weapon_durability}"
        )
        assert p2.life == 27, (
            f"P2 should take 3 damage from Fiery War Axe, got life {p2.life}"
        )

    def test_weapon_breaks_after_last_durability(self):
        """Weapon breaks (0 attack, 0 durability) after using last charge."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        equip_weapon(game, FIERY_WAR_AXE, p1)

        # Attack 1
        declare_attack(game, p1.hero_id, p2.hero_id)
        p1_hero = game.state.objects[p1.hero_id]
        p1_hero.state.attacks_this_turn = 0  # Reset for next turn

        # Attack 2 (last durability)
        declare_attack(game, p1.hero_id, p2.hero_id)

        assert p1.weapon_durability == 0, (
            f"Weapon should be broken (0 durability), got {p1.weapon_durability}"
        )
        assert p1.weapon_attack == 0, (
            f"Weapon attack should be 0 after breaking, got {p1.weapon_attack}"
        )

    def test_reequip_after_break(self):
        """After weapon breaks, equipping a new weapon works correctly."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        equip_weapon(game, FIERY_WAR_AXE, p1)

        # Use both durability charges
        declare_attack(game, p1.hero_id, p2.hero_id)
        p1_hero = game.state.objects[p1.hero_id]
        p1_hero.state.attacks_this_turn = 0
        declare_attack(game, p1.hero_id, p2.hero_id)

        # Weapon should be broken
        assert p1.weapon_attack == 0
        assert p1.weapon_durability == 0

        # Equip new weapon (Arcanite Reaper: 5/2)
        p1_hero.state.attacks_this_turn = 0
        equip_weapon(game, ARCANITE_REAPER, p1)

        assert p1.weapon_attack == 5, (
            f"New weapon should give 5 attack, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"New weapon should have 2 durability, got {p1.weapon_durability}"
        )

        # Attack with new weapon
        events = declare_attack(game, p1.hero_id, p2.hero_id)
        assert len(events) > 0, "Should be able to attack with new weapon"
        # P2 took: 3 + 3 + 5 = 11 damage total
        assert p2.life == 19, (
            f"P2 should have taken 11 total damage (3+3+5), life at {p2.life}"
        )

    def test_full_weapon_progression_sequence(self):
        """Full sequence: equip -> attack twice -> break -> reequip -> attack."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # Equip Fiery War Axe (3/2)
        equip_weapon(game, FIERY_WAR_AXE, p1)
        assert p1.weapon_attack == 3 and p1.weapon_durability == 2

        p1_hero = game.state.objects[p1.hero_id]

        # Turn 1: Attack face
        declare_attack(game, p1.hero_id, p2.hero_id)
        assert p1.weapon_durability == 1
        assert p2.life == 27
        p1_hero.state.attacks_this_turn = 0

        # Turn 2: Attack face again (weapon breaks)
        declare_attack(game, p1.hero_id, p2.hero_id)
        assert p1.weapon_durability == 0
        assert p1.weapon_attack == 0
        assert p2.life == 24
        p1_hero.state.attacks_this_turn = 0

        # Can't attack without weapon
        can_attack = game.combat_manager._can_attack(p1.hero_id, p1.id)
        assert can_attack is False, "Hero without weapon should not be able to attack"

        # Turn 3: Equip Arcanite Reaper (5/2), attack
        equip_weapon(game, ARCANITE_REAPER, p1)
        assert p1.weapon_attack == 5
        assert p1.weapon_durability == 2

        declare_attack(game, p1.hero_id, p2.hero_id)
        assert p2.life == 19, (
            f"After final attack, P2 should be at 19, got {p2.life}"
        )


# ============================================================
# Test 6: TestHeroPowerEveryTurn
# ============================================================

class TestHeroPowerEveryTurn:
    """Hero power used each of 3 turns. Verify it resets each turn."""

    def test_hero_power_usable_each_turn(self):
        """Mage hero power (Fireblast) can be used once per turn for 3 turns."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        loop = asyncio.new_event_loop()
        try:
            # Turn 1
            p1.hero_power_used = False
            p1.mana_crystals_available = 10
            result = loop.run_until_complete(game.use_hero_power(p1.id))
            assert result is True, "Hero power should succeed on turn 1"
            assert p1.hero_power_used is True
            assert p2.life == 29, f"Fireblast should deal 1 damage, P2 at {p2.life}"

            # Try to use again same turn - should fail
            result2 = loop.run_until_complete(game.use_hero_power(p1.id))
            assert result2 is False, "Hero power should fail when already used this turn"
            assert p2.life == 29, "No extra damage from failed hero power"

            # Turn 2: Reset hero power
            p1.hero_power_used = False
            p1.mana_crystals_available = 10
            result3 = loop.run_until_complete(game.use_hero_power(p1.id))
            assert result3 is True, "Hero power should succeed after reset on turn 2"
            assert p2.life == 28, f"After 2 Fireblasts, P2 should be at 28, got {p2.life}"

            # Turn 3: Reset again
            p1.hero_power_used = False
            p1.mana_crystals_available = 10
            result4 = loop.run_until_complete(game.use_hero_power(p1.id))
            assert result4 is True, "Hero power should succeed on turn 3"
            assert p2.life == 27, f"After 3 Fireblasts, P2 should be at 27, got {p2.life}"
        finally:
            loop.close()

    def test_hero_power_costs_mana(self):
        """Using hero power deducts 2 mana."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        p1.mana_crystals_available = 5

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(game.use_hero_power(p1.id))
            assert result is True
            assert p1.mana_crystals_available == 3, (
                f"Hero power should cost 2 mana, have {p1.mana_crystals_available} left"
            )
        finally:
            loop.close()

    def test_hero_power_insufficient_mana(self):
        """Hero power fails with insufficient mana."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        p1.mana_crystals_available = 1  # Need 2 for hero power

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(game.use_hero_power(p1.id))
            assert result is False, "Hero power should fail with only 1 mana"
            assert p2.life == 30, "No damage dealt when hero power fails"
        finally:
            loop.close()


# ============================================================
# Test 7: TestTauntWallVsCharge
# ============================================================

class TestTauntWallVsCharge:
    """P1 builds taunt wall, P2 has charge minions -> P2 must attack taunt first."""

    def test_charge_blocked_by_taunt(self):
        """Charge minion cannot bypass taunt to hit face."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id

        # P1 plays taunt minions
        footman = make_obj(game, GOLDSHIRE_FOOTMAN, p1)   # 1/2 Taunt
        grunt = make_obj(game, FROSTWOLF_GRUNT, p1)       # 2/2 Taunt
        senjin = make_obj(game, SEN_JIN_SHIELDMASTA, p1)  # 3/5 Taunt

        # P2 plays a charge minion
        boar = make_obj(game, STONETUSK_BOAR, p2)

        # Try to go face - should be blocked by taunt
        p2_events = declare_attack(game, boar.id, p1.hero_id)

        assert len(p2_events) == 0, (
            "Charge minion should be blocked from attacking face when taunts are present"
        )
        assert p1.life == 30, (
            f"P1 should be at 30 HP since taunt blocked face attack, got {p1.life}"
        )

    def test_charge_can_attack_taunt_minion(self):
        """Charge minion can attack a taunt minion."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id

        footman = make_obj(game, GOLDSHIRE_FOOTMAN, p1)  # 1/2 Taunt

        boar = make_obj(game, STONETUSK_BOAR, p2)

        events = declare_attack(game, boar.id, footman.id)

        assert len(events) > 0, "Attack on taunt should succeed"
        assert footman.state.damage == 1, (
            f"Footman should take 1 damage from Boar, got {footman.state.damage}"
        )

    def test_face_attack_allowed_after_taunts_removed(self):
        """After all taunts are dead, charge can go face."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id

        # Single taunt: 1/2 Goldshire Footman
        footman = make_obj(game, GOLDSHIRE_FOOTMAN, p1)

        # Destroy the taunt
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': footman.id},
            source='test'
        ))

        # Now P2's charge can attack face
        boar = make_obj(game, STONETUSK_BOAR, p2)
        events = declare_attack(game, boar.id, p1.hero_id)

        assert len(events) > 0, "Should attack face after taunt is gone"
        assert p1.life == 29, (
            f"P1 should take 1 damage, got {p1.life}"
        )

    def test_multiple_taunts_all_block(self):
        """Multiple taunt minions all block face attacks."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p2.id

        # Three taunts
        t1 = make_obj(game, GOLDSHIRE_FOOTMAN, p1)  # 1/2 Taunt
        t2 = make_obj(game, FROSTWOLF_GRUNT, p1)    # 2/2 Taunt
        t3 = make_obj(game, IRONFUR_GRIZZLY, p1)    # 3/3 Taunt

        # 3 charge minions try to go face
        for _ in range(3):
            boar = make_obj(game, STONETUSK_BOAR, p2)
            events = declare_attack(game, boar.id, p1.hero_id)
            assert len(events) == 0, "Should be blocked by taunt"

        assert p1.life == 30, (
            f"P1 should still be at 30 with taunts up, got {p1.life}"
        )


# ============================================================
# Test 8: TestMultipleDeathrattlesDuringAOE
# ============================================================

class TestMultipleDeathrattlesDuringAOE:
    """3 deathrattle minions on board, AOE kills all -> all 3 deathrattles fire."""

    def test_three_leper_gnomes_all_fire_deathrattle(self):
        """3 Leper Gnomes (deathrattle: 2 damage to enemy hero) killed by AOE -> 6 damage."""
        game, p1, p2 = new_hs_game()

        # P1 plays 3 Leper Gnomes (1/1, deathrattle: 2 damage to enemy hero)
        gnomes = []
        for _ in range(3):
            gnomes.append(play_minion(game, LEPER_GNOME, p1))

        assert count_battlefield(game, p1.id) == 3

        p2_life_before = p2.life

        # P2 casts Flamestrike (4 damage to all enemy minions)
        cast_spell(game, FLAMESTRIKE, p2)

        # Run SBAs to process deaths
        game.check_state_based_actions()

        # All gnomes should be dead
        assert count_battlefield(game, p1.id) == 0, (
            f"All Leper Gnomes should be dead, but {count_battlefield(game, p1.id)} remain"
        )

        # Each Leper Gnome deathrattle deals 2 damage to enemy hero (P2)
        # 3 gnomes * 2 damage = 6 damage to P2
        expected_p2_life = p2_life_before - 6
        assert p2.life == expected_p2_life, (
            f"3 Leper Gnome deathrattles should deal 6 damage to P2, "
            f"expected {expected_p2_life}, got {p2.life}"
        )

    def test_harvest_golems_spawn_tokens_on_aoe_death(self):
        """3 Harvest Golems killed by AOE should each spawn a Damaged Golem token."""
        game, p1, p2 = new_hs_game()

        # Play 3 Harvest Golems (2/3, deathrattle: summon 2/1 Damaged Golem)
        golems = []
        for _ in range(3):
            golems.append(play_minion(game, HARVEST_GOLEM, p1))

        assert count_battlefield(game, p1.id) == 3

        # Flamestrike deals 4 damage, killing all Harvest Golems (3 health < 4)
        cast_spell(game, FLAMESTRIKE, p2)
        game.check_state_based_actions()

        # Check that CREATE_TOKEN events were emitted for the deathrattles
        create_token_events = [
            e for e in game.state.event_log
            if e.type == EventType.CREATE_TOKEN
            and e.payload.get('token', {}).get('name') == 'Damaged Golem'
        ]
        assert len(create_token_events) >= 3, (
            f"Expected at least 3 CREATE_TOKEN events for Damaged Golems, "
            f"got {len(create_token_events)}"
        )

    def test_mixed_deathrattles_all_fire(self):
        """Mix of Leper Gnome and Loot Hoarder deathrattles all fire on AOE."""
        game, p1, p2 = new_hs_game()

        # Add library cards for Loot Hoarder draw
        add_cards_to_library(game, p1, WISP, 3)

        # Play 2 Leper Gnomes and 1 Loot Hoarder
        play_minion(game, LEPER_GNOME, p1)   # 1/1, DR: 2 damage to enemy hero
        play_minion(game, LEPER_GNOME, p1)   # 1/1, DR: 2 damage to enemy hero
        play_minion(game, LOOT_HOARDER, p1)  # 2/1, DR: draw a card

        assert count_battlefield(game, p1.id) == 3

        # Flamestrike kills all
        cast_spell(game, FLAMESTRIKE, p2)
        game.check_state_based_actions()

        # All should be dead
        assert count_battlefield(game, p1.id) == 0, (
            f"All minions should be dead, but {count_battlefield(game, p1.id)} remain"
        )

        # P2 should have taken 4 damage (2 Leper Gnome deathrattles * 2)
        assert p2.life == 26, (
            f"2 Leper Gnome deathrattles should deal 4 damage to P2, "
            f"expected 26, got {p2.life}"
        )


# ============================================================
# Test 9: TestGameEndDetection
# ============================================================

class TestGameEndDetection:
    """Play until one hero dies. Verify game-over flag."""

    def test_game_over_when_hero_dies(self):
        """Setting a player's life to 0 and checking SBA marks them as lost."""
        game, p1, p2 = new_hs_game()

        assert game.is_game_over() is False, "Game should not be over at start"

        # Deal 30 damage to P2
        p2.life = 0
        game.check_state_based_actions()

        assert p2.has_lost is True, "P2 should be marked as lost"
        assert game.is_game_over() is True, "Game should be over when a player has lost"

    def test_winner_is_surviving_player(self):
        """The surviving player is returned as winner."""
        game, p1, p2 = new_hs_game()

        p2.life = 0
        game.check_state_based_actions()

        winner = game.get_winner()
        assert winner == p1.id, (
            f"Winner should be P1 ({p1.id}), got {winner}"
        )

    def test_game_over_from_damage_event(self):
        """Dealing lethal damage via DAMAGE event and running SBA triggers game over."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        # Put a 30-damage attack scenario
        # Set P2 to 3 HP, then attack with a 4-power minion
        p2.life = 3

        boar = make_obj(game, STONETUSK_BOAR, p1)  # 1/1 Charge

        # Deal enough damage to kill P2
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 5, 'source': boar.id},
            source=boar.id
        ))

        # P2 life should go negative
        assert p2.life <= 0, f"P2 life should be <= 0, got {p2.life}"

        game.check_state_based_actions()
        assert p2.has_lost is True, "P2 should have lost"
        assert game.is_game_over() is True, "Game should be over"

    def test_game_not_over_while_both_alive(self):
        """Game is not over when both heroes have positive life."""
        game, p1, p2 = new_hs_game()

        p1.life = 1
        p2.life = 1

        game.check_state_based_actions()

        assert game.is_game_over() is False, (
            "Game should not be over when both players have positive life"
        )

    def test_draw_when_both_die(self):
        """Both players at 0 life => both lost, game is over and is a draw."""
        game, p1, p2 = new_hs_game()

        p1.life = 0
        p2.life = 0

        game.check_state_based_actions()

        assert p1.has_lost is True
        assert p2.has_lost is True
        assert game.is_game_over() is True
        assert game.is_draw() is True, "Both players dead should be a draw"


# ============================================================
# Test 10: TestTenTurnManaProgression
# ============================================================

class TestTenTurnManaProgression:
    """Simulate 10 turn starts. Verify mana at 1,2,3...10."""

    def test_mana_increments_one_through_ten(self):
        """Each turn start grants +1 mana crystal, from 1 up to 10."""
        game, p1, p2 = new_hs_game_fresh_mana()

        for turn in range(1, 11):
            game.mana_system.on_turn_start(p1.id)

            expected = min(turn, 10)
            assert p1.mana_crystals == expected, (
                f"Turn {turn}: should have {expected} mana crystals, "
                f"got {p1.mana_crystals}"
            )
            assert p1.mana_crystals_available == expected, (
                f"Turn {turn}: should have {expected} available mana, "
                f"got {p1.mana_crystals_available}"
            )

    def test_mana_caps_at_ten(self):
        """Mana does not exceed 10 even after 15 turns."""
        game, p1, p2 = new_hs_game_fresh_mana()

        for turn in range(1, 16):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"Mana crystals should cap at 10, got {p1.mana_crystals}"
        )
        assert p1.mana_crystals_available == 10, (
            f"Available mana should cap at 10, got {p1.mana_crystals_available}"
        )

    def test_mana_refills_each_turn(self):
        """Spending mana and then starting a new turn refills to the new maximum."""
        game, p1, p2 = new_hs_game_fresh_mana()

        # Turn 1: gain 1, spend 1
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 1
        game.mana_system.pay_cost(p1.id, 1)
        assert p1.mana_crystals_available == 0

        # Turn 2: gain to 2, refill to 2
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 2
        assert p1.mana_crystals_available == 2

        # Spend 1
        game.mana_system.pay_cost(p1.id, 1)
        assert p1.mana_crystals_available == 1

        # Turn 3: gain to 3, refill to 3
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 3
        assert p1.mana_crystals_available == 3

    def test_both_players_mana_independent(self):
        """Each player's mana progression is independent."""
        game, p1, p2 = new_hs_game_fresh_mana()

        # P1 gets 5 turns of mana
        for _ in range(5):
            game.mana_system.on_turn_start(p1.id)

        # P2 gets 3 turns of mana
        for _ in range(3):
            game.mana_system.on_turn_start(p2.id)

        assert p1.mana_crystals == 5, (
            f"P1 should have 5 mana crystals, got {p1.mana_crystals}"
        )
        assert p2.mana_crystals == 3, (
            f"P2 should have 3 mana crystals, got {p2.mana_crystals}"
        )

    def test_mana_at_each_turn_exact(self):
        """Verify exact mana values at each of the first 10 turns."""
        game, p1, p2 = new_hs_game_fresh_mana()

        expected_mana = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        for i, expected in enumerate(expected_mana, start=1):
            game.mana_system.on_turn_start(p1.id)
            assert p1.mana_crystals == expected, (
                f"Turn {i}: mana crystals should be {expected}, got {p1.mana_crystals}"
            )
            assert p1.mana_crystals_available == expected, (
                f"Turn {i}: available mana should be {expected}, "
                f"got {p1.mana_crystals_available}"
            )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
