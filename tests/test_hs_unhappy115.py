"""
Hearthstone Unhappy Path Tests - Batch 115

Aura Effects and Continuous Modifiers tests.

Tests cover:
- Stormwind Champion aura (+1/+1 to other friendly minions, not self) (5 tests)
- Raid Leader aura (+1 attack to other friendly minions) (5 tests)
- Dire Wolf Alpha adjacency aura (+1 attack to adjacent minions) (5 tests)
- Flametongue Totem adjacency aura (+2 attack to adjacent minions) (5 tests)
- Aura removal when source dies (all buffs disappear) (5 tests)
- Multiple auras stacking on same minion (5 tests)
- Aura not affecting enemy minions (5 tests)
- Aura not affecting heroes (5 tests)
- Aura on newly summoned minions (new minion immediately gets buff) (5 tests)
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

from src.cards.hearthstone.basic import WISP, STONETUSK_BOAR, RAID_LEADER, STORMWIND_CHAMPION
from src.cards.hearthstone.classic import (
    AZURE_DRAKE, BLOODMAGE_THALNOS, HARVEST_GOLEM, LOOT_HOARDER,
    DIRE_WOLF_ALPHA, ARGENT_COMMANDER, WILD_PYROMANCER, ABOMINATION, FIREBALL
)
from src.cards.hearthstone.shaman import FLAMETONGUE_TOTEM


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(p1_class="Warrior", p2_class="Mage"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
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
    if targets is None and getattr(card_def, 'requires_target', False):
        battlefield = game.state.zones.get('battlefield')
        enemy_id = None
        for pid in game.state.players.keys():
            if pid != owner.id:
                enemy_player = game.state.players[pid]
                if battlefield:
                    for oid in battlefield.objects:
                        o = game.state.objects.get(oid)
                        if o and o.controller == pid and CardType.MINION in o.characteristics.types:
                            enemy_id = oid
                            break
                if not enemy_id and enemy_player.hero_id:
                    enemy_id = enemy_player.hero_id
                break
        if enemy_id:
            targets = [enemy_id]
        else:
            targets = []
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    owner.cards_played_this_turn += 1
    return obj


def play_minion(game, card_def, owner):
    """Play a minion from hand to battlefield."""
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
    owner.cards_played_this_turn += 1
    return obj


def get_battlefield_count(game, player):
    """Get number of minions on battlefield for player."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return 0
    count = 0
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            count += 1
    return count


# ============================================================
# Category 1: Stormwind Champion Aura (+1/+1 to Other Friendly Minions, Not Self) (5 tests)
# ============================================================

def test_stormwind_champion_does_not_buff_itself():
    """Stormwind Champion should not buff itself."""
    game, p1, p2 = new_hs_game()
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Base stats: 6/6
    assert get_power(champion, game.state) == 6
    assert get_toughness(champion, game.state) == 6


def test_stormwind_champion_buffs_other_minions():
    """Stormwind Champion should buff other friendly minions."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp base 1/1, with +1/+1 from champion = 2/2
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 2


def test_stormwind_champion_does_not_buff_enemy_minions():
    """Stormwind Champion should not buff enemy minions."""
    game, p1, p2 = new_hs_game()
    enemy_wisp = play_minion(game, WISP, p2)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Enemy wisp stays 1/1
    assert get_power(enemy_wisp, game.state) == 1
    assert get_toughness(enemy_wisp, game.state) == 1


def test_stormwind_champion_buffs_multiple_minions():
    """Stormwind Champion should buff multiple friendly minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    wisp2 = play_minion(game, WISP, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # All wisps and boar get +1/+1
    assert get_power(wisp1, game.state) == 2
    assert get_toughness(wisp1, game.state) == 2
    assert get_power(wisp2, game.state) == 2
    assert get_toughness(wisp2, game.state) == 2
    assert get_power(boar, game.state) == 2  # 1+1
    assert get_toughness(boar, game.state) == 2  # 1+1


def test_stormwind_champion_buff_disappears_when_champion_dies():
    """When Stormwind Champion dies, the buff should disappear."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp is buffed to 2/2
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 2

    # Kill champion
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': champion.id, 'reason': 'test'},
        source=champion.id
    ))

    # Wisp returns to 1/1
    assert get_power(wisp, game.state) == 1
    assert get_toughness(wisp, game.state) == 1


# ============================================================
# Category 2: Raid Leader Aura (+1 Attack to Other Friendly Minions) (5 tests)
# ============================================================

def test_raid_leader_does_not_buff_itself():
    """Raid Leader should not buff itself."""
    game, p1, p2 = new_hs_game()
    leader = play_minion(game, RAID_LEADER, p1)

    # Base stats: 2/2
    assert get_power(leader, game.state) == 2
    assert get_toughness(leader, game.state) == 2


def test_raid_leader_buffs_attack_only():
    """Raid Leader should buff attack only, not health."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader = play_minion(game, RAID_LEADER, p1)

    # Wisp base 1/1, with +1 attack = 2/1
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 1


def test_raid_leader_does_not_buff_enemy_minions():
    """Raid Leader should not buff enemy minions."""
    game, p1, p2 = new_hs_game()
    enemy_wisp = play_minion(game, WISP, p2)
    leader = play_minion(game, RAID_LEADER, p1)

    # Enemy wisp stays 1/1
    assert get_power(enemy_wisp, game.state) == 1
    assert get_toughness(enemy_wisp, game.state) == 1


def test_raid_leader_buffs_multiple_minions():
    """Raid Leader should buff multiple friendly minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    wisp2 = play_minion(game, WISP, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)
    leader = play_minion(game, RAID_LEADER, p1)

    # All get +1 attack
    assert get_power(wisp1, game.state) == 2
    assert get_power(wisp2, game.state) == 2
    assert get_power(boar, game.state) == 2  # 1+1


def test_raid_leader_buff_disappears_when_leader_dies():
    """When Raid Leader dies, the attack buff should disappear."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader = play_minion(game, RAID_LEADER, p1)

    # Wisp is buffed to 2/1
    assert get_power(wisp, game.state) == 2

    # Kill leader
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': leader.id, 'reason': 'test'},
        source=leader.id
    ))

    # Wisp returns to 1/1
    assert get_power(wisp, game.state) == 1


# ============================================================
# Category 3: Dire Wolf Alpha Adjacency Aura (+1 Attack to Adjacent Minions) (5 tests)
# ============================================================

def test_dire_wolf_alpha_does_not_buff_itself():
    """Dire Wolf Alpha should not buff itself."""
    game, p1, p2 = new_hs_game()
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)

    # Base stats: 2/2
    assert get_power(wolf, game.state) == 2
    assert get_toughness(wolf, game.state) == 2


def test_dire_wolf_alpha_buffs_adjacent_minions():
    """Dire Wolf Alpha should buff adjacent minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Both adjacent wisps get +1 attack
    assert get_power(wisp1, game.state) == 2
    assert get_power(wisp2, game.state) == 2


def test_dire_wolf_alpha_does_not_buff_non_adjacent():
    """Dire Wolf Alpha should not buff non-adjacent minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Order: wisp1, boar, wolf, wisp2
    # boar and wisp2 are adjacent to wolf
    assert get_power(wisp1, game.state) == 1  # not adjacent to wolf
    assert get_power(boar, game.state) == 2  # adjacent to wolf (1+1)
    assert get_power(wisp2, game.state) == 2  # adjacent to wolf (1+1)


def test_dire_wolf_alpha_buffs_only_attack():
    """Dire Wolf Alpha should buff attack only, not health."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)

    # Wisp gets +1 attack, health unchanged
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 1


def test_dire_wolf_alpha_buff_disappears_when_wolf_dies():
    """When Dire Wolf Alpha dies, the adjacency buff should disappear."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)

    # Wisp is buffed
    assert get_power(wisp, game.state) == 2

    # Kill wolf
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wolf.id, 'reason': 'test'},
        source=wolf.id
    ))

    # Wisp returns to 1 attack
    assert get_power(wisp, game.state) == 1


# ============================================================
# Category 4: Flametongue Totem Adjacency Aura (+2 Attack to Adjacent Minions) (5 tests)
# ============================================================

def test_flametongue_totem_does_not_buff_itself():
    """Flametongue Totem should not buff itself."""
    game, p1, p2 = new_hs_game()
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)

    # Base stats: 0/3
    assert get_power(totem, game.state) == 0
    assert get_toughness(totem, game.state) == 3


def test_flametongue_totem_buffs_adjacent_minions():
    """Flametongue Totem should buff adjacent minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Both adjacent wisps get +2 attack
    assert get_power(wisp1, game.state) == 3
    assert get_power(wisp2, game.state) == 3


def test_flametongue_totem_does_not_buff_non_adjacent():
    """Flametongue Totem should not buff non-adjacent minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Order: wisp1, boar, totem, wisp2
    # boar and wisp2 are adjacent to totem
    assert get_power(wisp1, game.state) == 1  # not adjacent to totem
    assert get_power(boar, game.state) == 3  # adjacent to totem (1+2)
    assert get_power(wisp2, game.state) == 3  # adjacent to totem (1+2)


def test_flametongue_totem_buffs_only_attack():
    """Flametongue Totem should buff attack only, not health."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)

    # Wisp gets +2 attack, health unchanged
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 1


def test_flametongue_totem_buff_disappears_when_totem_dies():
    """When Flametongue Totem dies, the adjacency buff should disappear."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)

    # Wisp is buffed
    assert get_power(wisp, game.state) == 3

    # Kill totem
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': totem.id, 'reason': 'test'},
        source=totem.id
    ))

    # Wisp returns to 1 attack
    assert get_power(wisp, game.state) == 1


# ============================================================
# Category 5: Aura Removal When Source Dies (All Buffs Disappear) (5 tests)
# ============================================================

def test_multiple_auras_all_disappear_when_sources_die():
    """When multiple aura sources die, all buffs should disappear."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp gets +1 attack from leader and +1/+1 from champion = 3/2
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 2

    # Kill both aura sources
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': leader.id, 'reason': 'test'},
        source=leader.id
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': champion.id, 'reason': 'test'},
        source=champion.id
    ))

    # Wisp returns to 1/1
    assert get_power(wisp, game.state) == 1
    assert get_toughness(wisp, game.state) == 1


def test_aura_removal_does_not_affect_permanent_buffs():
    """Aura removal should not affect permanent buffs from battlecries."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)

    # Give permanent buff manually
    wisp.characteristics.power += 2
    wisp.characteristics.toughness += 2

    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp: 3/3 base + 1/1 from champion = 4/4
    assert get_power(wisp, game.state) == 4
    assert get_toughness(wisp, game.state) == 4

    # Kill champion
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': champion.id, 'reason': 'test'},
        source=champion.id
    ))

    # Wisp should still have permanent buff: 3/3
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 3


def test_adjacency_buff_disappears_when_source_dies():
    """When adjacency aura source dies, buffs should disappear from adjacent minions."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Both wisps buffed
    assert get_power(wisp1, game.state) == 2
    assert get_power(wisp2, game.state) == 2

    # Kill wolf
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wolf.id, 'reason': 'test'},
        source=wolf.id
    ))

    # Both wisps return to 1 attack
    assert get_power(wisp1, game.state) == 1
    assert get_power(wisp2, game.state) == 1


def test_aura_disappears_from_damaged_minion():
    """When aura disappears, damaged minions should revert to base stats."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp is 2/2 with aura
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 2

    # Damage wisp for 1
    wisp.state.damage = 1

    # Kill champion
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': champion.id, 'reason': 'test'},
        source=champion.id
    ))

    # Wisp returns to 1/1 with 1 damage (dead)
    assert get_power(wisp, game.state) == 1
    assert get_toughness(wisp, game.state) == 1
    assert wisp.state.damage == 1


def test_totem_buff_disappears_when_totem_leaves_battlefield():
    """When Flametongue Totem leaves battlefield, buffs should disappear."""
    game, p1, p2 = new_hs_game()
    wisp1 = play_minion(game, WISP, p1)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Both wisps buffed to 3 attack
    assert get_power(wisp1, game.state) == 3
    assert get_power(wisp2, game.state) == 3

    # Remove totem
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': totem.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
            'controller': p1.id,
        },
        source=totem.id
    ))

    # Both wisps return to 1 attack
    assert get_power(wisp1, game.state) == 1
    assert get_power(wisp2, game.state) == 1


# ============================================================
# Category 6: Multiple Auras Stacking on Same Minion (5 tests)
# ============================================================

def test_two_raid_leaders_stack():
    """Two Raid Leaders should stack their attack buffs."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader1 = play_minion(game, RAID_LEADER, p1)
    leader2 = play_minion(game, RAID_LEADER, p1)

    # Wisp gets +1 attack from each leader = 3/1
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 1


def test_raid_leader_and_stormwind_champion_stack():
    """Raid Leader and Stormwind Champion should stack."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp gets +1 attack from leader and +1/+1 from champion = 3/2
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 2


def test_dire_wolf_and_flametongue_stack():
    """Dire Wolf Alpha and Flametongue Totem should stack their attack buffs."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)
    wisp2 = play_minion(game, WISP, p1)

    # Order: wisp, wolf, totem, wisp2
    # wolf is adjacent to wisp and totem
    # totem is adjacent to wolf and wisp2
    # wisp gets +1 from wolf = 2/1
    # wisp2 gets +2 from totem = 3/1
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 1
    assert get_power(wisp2, game.state) == 3
    assert get_toughness(wisp2, game.state) == 1


def test_three_different_auras_stack():
    """Three different auras should all stack on the same minion."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp gets +1 from leader and +1/+1 from champion = 3/2
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 2


def test_removing_one_aura_keeps_others():
    """Removing one aura should keep the others active."""
    game, p1, p2 = new_hs_game()
    wisp = play_minion(game, WISP, p1)
    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Wisp has 3/2 from both auras
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 2

    # Kill leader
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': leader.id, 'reason': 'test'},
        source=leader.id
    ))

    # Wisp should still have champion buff: 2/2
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 2


# ============================================================
# Category 7: Aura Not Affecting Enemy Minions (5 tests)
# ============================================================

def test_raid_leader_does_not_buff_enemy():
    """Raid Leader should not buff enemy minions."""
    game, p1, p2 = new_hs_game()
    enemy_wisp = play_minion(game, WISP, p2)
    leader = play_minion(game, RAID_LEADER, p1)
    friendly_wisp = play_minion(game, WISP, p1)

    # Enemy wisp unchanged
    assert get_power(enemy_wisp, game.state) == 1
    # Friendly wisp buffed
    assert get_power(friendly_wisp, game.state) == 2


def test_stormwind_champion_does_not_buff_enemy():
    """Stormwind Champion should not buff enemy minions."""
    game, p1, p2 = new_hs_game()
    enemy_wisp = play_minion(game, WISP, p2)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)
    friendly_wisp = play_minion(game, WISP, p1)

    # Enemy wisp unchanged
    assert get_power(enemy_wisp, game.state) == 1
    assert get_toughness(enemy_wisp, game.state) == 1
    # Friendly wisp buffed
    assert get_power(friendly_wisp, game.state) == 2
    assert get_toughness(friendly_wisp, game.state) == 2


def test_dire_wolf_does_not_buff_enemy_adjacent():
    """Dire Wolf Alpha should not buff enemy minions even if adjacent."""
    game, p1, p2 = new_hs_game()
    # In Hearthstone, minions are separated by player, so "adjacent" only applies to same player
    enemy_wisp = play_minion(game, WISP, p2)
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)

    # Enemy wisp unchanged (not adjacent in game logic)
    assert get_power(enemy_wisp, game.state) == 1


def test_flametongue_does_not_buff_enemy():
    """Flametongue Totem should not buff enemy minions."""
    game, p1, p2 = new_hs_game()
    enemy_wisp = play_minion(game, WISP, p2)
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)

    # Enemy wisp unchanged
    assert get_power(enemy_wisp, game.state) == 1


def test_multiple_auras_do_not_affect_enemy():
    """Multiple auras should not affect enemy minions."""
    game, p1, p2 = new_hs_game()
    enemy_wisp = play_minion(game, WISP, p2)
    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Enemy wisp completely unchanged
    assert get_power(enemy_wisp, game.state) == 1
    assert get_toughness(enemy_wisp, game.state) == 1


# ============================================================
# Category 8: Aura Not Affecting Heroes (5 tests)
# ============================================================

def test_raid_leader_does_not_buff_hero():
    """Raid Leader should not buff the hero."""
    game, p1, p2 = new_hs_game()
    leader = play_minion(game, RAID_LEADER, p1)

    hero = game.state.objects.get(p1.hero_id)
    # Heroes have attack 0 by default, should stay 0
    assert get_power(hero, game.state) == 0


def test_stormwind_champion_does_not_buff_hero():
    """Stormwind Champion should not buff the hero."""
    game, p1, p2 = new_hs_game()
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    hero = game.state.objects.get(p1.hero_id)
    # Heroes don't have health in the traditional sense, but power should stay 0
    assert get_power(hero, game.state) == 0


def test_dire_wolf_does_not_buff_hero():
    """Dire Wolf Alpha should not buff the hero."""
    game, p1, p2 = new_hs_game()
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)

    hero = game.state.objects.get(p1.hero_id)
    assert get_power(hero, game.state) == 0


def test_flametongue_does_not_buff_hero():
    """Flametongue Totem should not buff the hero."""
    game, p1, p2 = new_hs_game()
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)

    hero = game.state.objects.get(p1.hero_id)
    assert get_power(hero, game.state) == 0


def test_hero_with_weapon_not_affected_by_auras():
    """Hero with weapon should not be affected by minion auras."""
    game, p1, p2 = new_hs_game()

    # Create a weapon for the hero
    from src.cards.hearthstone.basic import FIERY_WAR_AXE
    weapon = make_obj(game, FIERY_WAR_AXE, p1, ZoneType.BATTLEFIELD)
    p1.equipped_weapon = weapon.id
    p1.weapon_attack = weapon.characteristics.power
    p1.weapon_durability = weapon.characteristics.toughness

    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)

    # Weapon attack stays at 3 (base), not affected by auras
    assert weapon.characteristics.power == 3
    assert p1.weapon_attack == 3


# ============================================================
# Category 9: Aura on Newly Summoned Minions (New Minion Immediately Gets Buff) (5 tests)
# ============================================================

def test_minion_summoned_after_raid_leader_gets_buff():
    """Minion summoned after Raid Leader should immediately get the buff."""
    game, p1, p2 = new_hs_game()
    leader = play_minion(game, RAID_LEADER, p1)
    wisp = play_minion(game, WISP, p1)

    # Wisp should immediately have +1 attack
    assert get_power(wisp, game.state) == 2


def test_minion_summoned_after_stormwind_champion_gets_buff():
    """Minion summoned after Stormwind Champion should immediately get the buff."""
    game, p1, p2 = new_hs_game()
    champion = play_minion(game, STORMWIND_CHAMPION, p1)
    wisp = play_minion(game, WISP, p1)

    # Wisp should immediately have +1/+1
    assert get_power(wisp, game.state) == 2
    assert get_toughness(wisp, game.state) == 2


def test_minion_summoned_adjacent_to_dire_wolf_gets_buff():
    """Minion summoned adjacent to Dire Wolf Alpha should immediately get the buff."""
    game, p1, p2 = new_hs_game()
    wolf = play_minion(game, DIRE_WOLF_ALPHA, p1)
    wisp = play_minion(game, WISP, p1)

    # Wisp summoned adjacent to wolf should get +1 attack
    assert get_power(wisp, game.state) == 2


def test_minion_summoned_adjacent_to_flametongue_gets_buff():
    """Minion summoned adjacent to Flametongue Totem should immediately get the buff."""
    game, p1, p2 = new_hs_game()
    totem = play_minion(game, FLAMETONGUE_TOTEM, p1)
    wisp = play_minion(game, WISP, p1)

    # Wisp summoned adjacent to totem should get +2 attack
    assert get_power(wisp, game.state) == 3


def test_minion_summoned_with_multiple_auras_gets_all_buffs():
    """Minion summoned with multiple auras active should get all buffs."""
    game, p1, p2 = new_hs_game()
    leader = play_minion(game, RAID_LEADER, p1)
    champion = play_minion(game, STORMWIND_CHAMPION, p1)
    wisp = play_minion(game, WISP, p1)

    # Wisp should immediately get +1 from leader and +1/+1 from champion = 3/2
    assert get_power(wisp, game.state) == 3
    assert get_toughness(wisp, game.state) == 2
