"""
Yu-Gi-Oh! Stage 1 Tests

Tests for foundation: LP tracking, Normal/Tribute/Set/Flip Summon,
position change, all battle scenarios, draw phase, deck-out loss, turn phases.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game, make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import ZoneType, CardType, EventType


def make_test_game():
    """Create a game with two players set up for YGO testing."""
    game = Game(mode="yugioh")
    p1 = game.add_player("Player 1")
    p2 = game.add_player("Player 2")
    return game, p1, p2


def add_monsters_to_deck(game, player, count=10, atk=1500, def_val=1200, level=4):
    """Add simple monsters to a player's deck."""
    for i in range(count):
        card_def = make_ygo_monster(
            name=f"Test Monster {i+1}",
            atk=atk, def_val=def_val, level=level,
            attribute="DARK", ygo_monster_type="Normal",
        )
        game.create_object(
            name=card_def.name,
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics.__class__(types={CardType.YGO_MONSTER}),
            card_def=card_def,
        )


def add_card_to_hand(game, player, card_def):
    """Add a specific card directly to a player's hand."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics.__class__(types=set(card_def.characteristics.types)),
        card_def=card_def,
    )
    return obj


def get_hand_objects(game, player_id):
    """Get all objects in a player's hand."""
    hand_key = f"hand_{player_id}"
    zone = game.state.zones.get(hand_key)
    if not zone:
        return []
    return [game.state.objects[oid] for oid in zone.objects if oid in game.state.objects]


def get_monster_zone_objects(game, player_id):
    """Get all objects in a player's monster zone (non-None)."""
    zone_key = f"monster_zone_{player_id}"
    zone = game.state.zones.get(zone_key)
    if not zone:
        return []
    return [game.state.objects[oid] for oid in zone.objects
            if oid is not None and oid in game.state.objects]


def get_graveyard_objects(game, player_id):
    """Get all objects in a player's graveyard."""
    gy_key = f"graveyard_{player_id}"
    zone = game.state.zones.get(gy_key)
    if not zone:
        return []
    return [game.state.objects[oid] for oid in zone.objects if oid in game.state.objects]


# =============================================================================
# Tests
# =============================================================================

def test_game_creation():
    """Test that YGO game initializes correctly."""
    game, p1, p2 = make_test_game()
    assert game.state.game_mode == "yugioh"
    assert game.state.max_hand_size == 6
    assert p1.lp == 8000
    assert p2.lp == 8000
    # Check YGO zones exist
    assert f"monster_zone_{p1.id}" in game.state.zones
    assert f"spell_trap_zone_{p1.id}" in game.state.zones
    assert f"extra_deck_{p1.id}" in game.state.zones
    assert f"banished_{p1.id}" in game.state.zones
    print("  PASS: test_game_creation")


def test_lp_tracking():
    """Test Life Points start at 8000 and can be modified."""
    game, p1, p2 = make_test_game()
    assert p1.lp == 8000
    p1.lp -= 3000
    assert p1.lp == 5000
    p1.lp = 0
    assert p1.lp == 0
    print("  PASS: test_lp_tracking")


def test_normal_summon():
    """Test Normal Summoning a level 4 or lower monster."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    card_def = make_ygo_monster("Warrior", atk=1800, def_val=1200, level=4)
    obj = add_card_to_hand(game, p1, card_def)

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    turn_mgr.ygo_turn_state.normal_summon_used = False

    events = turn_mgr._do_normal_summon(p1.id, {'card_id': obj.id})
    assert len(events) > 0
    assert events[0].type == EventType.YGO_NORMAL_SUMMON
    assert obj.zone == ZoneType.MONSTER_ZONE
    assert obj.state.ygo_position == 'face_up_atk'
    assert turn_mgr.ygo_turn_state.normal_summon_used
    print("  PASS: test_normal_summon")


def test_normal_summon_once_per_turn():
    """Test that only one Normal Summon is allowed per turn."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    card1 = add_card_to_hand(game, p1, make_ygo_monster("Mon1", 1500, 1200, 4))
    card2 = add_card_to_hand(game, p1, make_ygo_monster("Mon2", 1600, 1000, 4))

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    turn_mgr.ygo_turn_state.normal_summon_used = False

    events1 = turn_mgr._do_normal_summon(p1.id, {'card_id': card1.id})
    assert len(events1) > 0

    events2 = turn_mgr._do_normal_summon(p1.id, {'card_id': card2.id})
    assert len(events2) == 0  # Should fail
    print("  PASS: test_normal_summon_once_per_turn")


def test_tribute_summon_level5():
    """Test Tribute Summon for level 5-6 (1 tribute)."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Put a tribute on the field
    tribute_def = make_ygo_monster("Tribute Fodder", 1000, 1000, 3)
    tribute = add_card_to_hand(game, p1, tribute_def)
    turn_mgr._do_normal_summon(p1.id, {'card_id': tribute.id})
    turn_mgr.ygo_turn_state.normal_summon_used = False  # Reset for tribute summon

    # Level 5 monster in hand
    big_def = make_ygo_monster("Big Monster", 2400, 2000, level=5)
    big = add_card_to_hand(game, p1, big_def)

    events = turn_mgr._do_normal_summon(p1.id, {
        'card_id': big.id,
        'tribute_ids': [tribute.id],
    })
    assert len(events) > 0
    assert events[0].type == EventType.YGO_TRIBUTE_SUMMON
    assert big.zone == ZoneType.MONSTER_ZONE
    assert tribute.zone == ZoneType.GRAVEYARD
    print("  PASS: test_tribute_summon_level5")


def test_tribute_summon_level7():
    """Test Tribute Summon for level 7+ (2 tributes)."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Put 2 tributes on field
    t1 = add_card_to_hand(game, p1, make_ygo_monster("Fodder1", 1000, 1000, 3))
    turn_mgr._do_normal_summon(p1.id, {'card_id': t1.id})
    turn_mgr.ygo_turn_state.normal_summon_used = False

    t2 = add_card_to_hand(game, p1, make_ygo_monster("Fodder2", 1000, 1000, 3))
    turn_mgr._do_normal_summon(p1.id, {'card_id': t2.id})
    turn_mgr.ygo_turn_state.normal_summon_used = False

    # Level 7 monster
    boss = add_card_to_hand(game, p1, make_ygo_monster("Boss", 2800, 2500, level=7))
    events = turn_mgr._do_normal_summon(p1.id, {
        'card_id': boss.id,
        'tribute_ids': [t1.id, t2.id],
    })
    assert len(events) > 0
    assert events[0].type == EventType.YGO_TRIBUTE_SUMMON
    assert boss.zone == ZoneType.MONSTER_ZONE
    assert t1.zone == ZoneType.GRAVEYARD
    assert t2.zone == ZoneType.GRAVEYARD
    print("  PASS: test_tribute_summon_level7")


def test_set_monster():
    """Test Setting a monster face-down."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Sneaky", 1000, 2000, 4))
    events = turn_mgr._do_set_monster(p1.id, {'card_id': card.id})

    assert len(events) > 0
    assert card.zone == ZoneType.MONSTER_ZONE
    assert card.state.ygo_position == 'face_down_def'
    assert card.state.face_down
    assert card.state.turns_set == 0
    print("  PASS: test_set_monster")


def test_flip_summon():
    """Test Flip Summoning a face-down monster."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Flippy", 1200, 1500, 4))
    turn_mgr._do_set_monster(p1.id, {'card_id': card.id})

    # Cannot flip summon same turn it was set
    events = turn_mgr._do_flip_summon(p1.id, {'card_id': card.id})
    assert len(events) == 0

    # Simulate turn passing (increment turns_set)
    card.state.turns_set = 1

    events = turn_mgr._do_flip_summon(p1.id, {'card_id': card.id})
    assert len(events) > 0
    assert events[0].type == EventType.YGO_FLIP_SUMMON
    assert card.state.ygo_position == 'face_up_atk'
    assert not card.state.face_down
    print("  PASS: test_flip_summon")


def test_change_position():
    """Test changing a monster's battle position."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Switcher", 1500, 1500, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': card.id})
    assert card.state.ygo_position == 'face_up_atk'

    events = turn_mgr._do_change_position(p1.id, {'card_id': card.id})
    assert len(events) > 0
    assert card.state.ygo_position == 'face_up_def'

    # Cannot change again same turn
    events2 = turn_mgr._do_change_position(p1.id, {'card_id': card.id})
    assert len(events2) == 0
    print("  PASS: test_change_position")


def test_atk_vs_atk_attacker_wins():
    """Test ATK vs ATK battle where attacker has higher ATK."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # P1: ATK 2000
    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Attacker", 2000, 1500, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    # P2: ATK 1500
    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Defender", 1500, 1200, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    # Defender destroyed, P2 takes 500 damage
    assert def_card.zone == ZoneType.GRAVEYARD
    assert p2.lp == 7500
    print("  PASS: test_atk_vs_atk_attacker_wins")


def test_atk_vs_atk_defender_wins():
    """Test ATK vs ATK battle where defender has higher ATK."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Weak", 1200, 1000, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Strong", 2000, 1500, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    assert atk_card.zone == ZoneType.GRAVEYARD
    assert def_card.zone == ZoneType.MONSTER_ZONE
    assert p1.lp == 7200  # 8000 - 800
    print("  PASS: test_atk_vs_atk_defender_wins")


def test_atk_vs_atk_tie():
    """Test ATK vs ATK battle with equal ATK (both destroyed)."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Equal1", 1500, 1000, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Equal2", 1500, 1000, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    assert atk_card.zone == ZoneType.GRAVEYARD
    assert def_card.zone == ZoneType.GRAVEYARD
    assert p1.lp == 8000  # No damage
    assert p2.lp == 8000
    print("  PASS: test_atk_vs_atk_tie")


def test_atk_vs_def_attacker_wins():
    """Test ATK vs DEF battle where attacker has higher ATK."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Attacker", 2000, 1000, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Wall", 800, 1500, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})
    def_card.state.ygo_position = 'face_up_def'  # Put in DEF position

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    assert def_card.zone == ZoneType.GRAVEYARD  # Destroyed
    assert p2.lp == 8000  # No damage in ATK vs DEF
    print("  PASS: test_atk_vs_def_attacker_wins")


def test_atk_vs_def_defender_wins():
    """Test ATK vs DEF where DEF is higher (attacker takes damage)."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Weak", 1000, 1000, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Wall", 500, 2000, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})
    def_card.state.ygo_position = 'face_up_def'

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    assert def_card.zone == ZoneType.MONSTER_ZONE  # Not destroyed
    assert atk_card.zone == ZoneType.MONSTER_ZONE  # Not destroyed
    assert p1.lp == 7000  # 8000 - 1000 (2000-1000)
    print("  PASS: test_atk_vs_def_defender_wins")


def test_atk_vs_def_tie():
    """Test ATK vs DEF where ATK = DEF (no destruction, no damage)."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("A", 1500, 1000, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("B", 500, 1500, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})
    def_card.state.ygo_position = 'face_up_def'

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    assert atk_card.zone == ZoneType.MONSTER_ZONE
    assert def_card.zone == ZoneType.MONSTER_ZONE
    assert p1.lp == 8000
    assert p2.lp == 8000
    print("  PASS: test_atk_vs_def_tie")


def test_direct_attack():
    """Test direct attack when opponent has no monsters."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Direct", 2500, 2000, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, None, p2.id)

    assert p2.lp == 5500  # 8000 - 2500
    print("  PASS: test_direct_attack")


def test_lp_zero_loss():
    """Test that reducing LP to 0 sets has_lost."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # 8000 ATK monster to one-shot
    atk_card = add_card_to_hand(game, p1, make_ygo_monster("OTK", 8000, 0, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, None, p2.id)

    assert p2.lp == 0
    assert p2.has_lost
    print("  PASS: test_lp_zero_loss")


def test_deck_out_loss():
    """Test that drawing from an empty deck causes a loss."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    # Empty the library
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    turn_mgr._draw_cards(p1.id, 1)
    assert p1.has_lost
    print("  PASS: test_deck_out_loss")


def test_setup_game():
    """Test game setup: shuffle, draw 5, coin flip."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    # Add cards to decks
    add_monsters_to_deck(game, p1, 40)
    add_monsters_to_deck(game, p2, 40)

    events = asyncio.get_event_loop().run_until_complete(turn_mgr.setup_game())

    # Both players should have 5 cards in hand
    h1 = get_hand_objects(game, p1.id)
    h2 = get_hand_objects(game, p2.id)
    assert len(h1) == 5, f"P1 hand size: {len(h1)}"
    assert len(h2) == 5, f"P2 hand size: {len(h2)}"

    # A first player should be set
    assert turn_mgr.ygo_turn_state.first_player_id is not None
    print("  PASS: test_setup_game")


def test_flip_face_down_in_battle():
    """Test that attacking a face-down monster flips it face-up."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Attacker", 1800, 1200, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Hidden", 500, 2100, 4))
    turn_mgr._do_set_monster(p2.id, {'card_id': def_card.id})

    assert def_card.state.face_down

    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = turn_mgr._inline_resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)

    # Face-down should now be face-up
    assert not def_card.state.face_down
    # ATK 1800 vs DEF 2100 -> attacker takes 300 damage, no destruction
    assert p1.lp == 7700
    print("  PASS: test_flip_face_down_in_battle")


def test_set_spell_trap():
    """Test setting a trap card face-down."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    trap_def = make_ygo_trap("Test Trap", ygo_trap_type="Normal", text="Do something")
    trap = add_card_to_hand(game, p1, trap_def)

    events = turn_mgr._do_set_spell_trap(p1.id, {'card_id': trap.id})
    assert len(events) > 0
    assert trap.zone == ZoneType.SPELL_TRAP_ZONE
    assert trap.state.face_down
    assert trap.state.turns_set == 0
    print("  PASS: test_set_spell_trap")


def test_monster_zone_limit():
    """Test that only 5 monsters can be on the field."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Fill 5 monster slots
    for i in range(5):
        card = add_card_to_hand(game, p1, make_ygo_monster(f"Mon{i}", 1000, 1000, 4))
        turn_mgr.ygo_turn_state.normal_summon_used = False
        turn_mgr._do_normal_summon(p1.id, {'card_id': card.id})

    # 6th should fail
    card6 = add_card_to_hand(game, p1, make_ygo_monster("Mon6", 1000, 1000, 4))
    turn_mgr.ygo_turn_state.normal_summon_used = False
    events = turn_mgr._do_normal_summon(p1.id, {'card_id': card6.id})
    assert len(events) == 0  # No space
    assert card6.zone == ZoneType.HAND  # Still in hand
    print("  PASS: test_monster_zone_limit")


def test_combat_manager():
    """Test the YugiohCombatManager separately."""
    game, p1, p2 = make_test_game()
    combat = game.combat_manager
    turn_mgr = game.turn_manager
    combat.turn_manager = turn_mgr
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Set up monsters
    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Fighter", 2000, 1500, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr.ygo_turn_state.active_player_id = p2.id
    def_card = add_card_to_hand(game, p2, make_ygo_monster("Target", 1600, 1400, 4))
    turn_mgr._do_normal_summon(p2.id, {'card_id': def_card.id})

    # Check can_attack
    can, reason = combat.can_attack(atk_card.id)
    assert can, reason

    # Check targets
    targets = combat.get_attack_targets(atk_card.id, p2.id)
    assert len(targets) == 1
    assert targets[0]['id'] == def_card.id

    # Resolve attack
    turn_mgr.ygo_turn_state.active_player_id = p1.id
    events = combat.resolve_attack(p1.id, atk_card.id, def_card.id, p2.id)
    assert def_card.zone == ZoneType.GRAVEYARD
    assert p2.lp == 7600  # 8000 - 400
    print("  PASS: test_combat_manager")


def test_direct_attack_with_combat_manager():
    """Test direct attack via combat manager."""
    game, p1, p2 = make_test_game()
    combat = game.combat_manager
    turn_mgr = game.turn_manager
    combat.turn_manager = turn_mgr
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    atk_card = add_card_to_hand(game, p1, make_ygo_monster("Direct", 3000, 2500, 4))
    turn_mgr._do_normal_summon(p1.id, {'card_id': atk_card.id})

    events = combat.resolve_attack(p1.id, atk_card.id, None, p2.id)
    assert p2.lp == 5000  # 8000 - 3000
    print("  PASS: test_direct_attack_with_combat_manager")


def test_position_blocks_attack():
    """Test that DEF position monsters cannot attack."""
    game, p1, p2 = make_test_game()
    combat = game.combat_manager
    turn_mgr = game.turn_manager
    combat.turn_manager = turn_mgr

    card = add_card_to_hand(game, p1, make_ygo_monster("Defender", 1000, 2000, 4))
    turn_mgr.ygo_turn_state.active_player_id = p1.id
    turn_mgr._do_normal_summon(p1.id, {'card_id': card.id})
    card.state.ygo_position = 'face_up_def'

    can, reason = combat.can_attack(card.id)
    assert not can
    assert "ATK position" in reason
    print("  PASS: test_position_blocks_attack")


def test_special_summon():
    """Test Special Summoning a monster."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Put monster in GY (simulate)
    card_def = make_ygo_monster("Revived", 2500, 2100, 7)
    card = game.create_object(
        name=card_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=card_def.characteristics.__class__(types={CardType.YGO_MONSTER}),
        card_def=card_def,
    )
    gy_key = f"graveyard_{p1.id}"
    game.state.zones[gy_key].objects.append(card.id)

    events = turn_mgr._do_special_summon(p1.id, {'card_id': card.id, 'position': 'face_up_atk'})
    assert len(events) > 0
    assert card.zone == ZoneType.MONSTER_ZONE
    # Normal summon should NOT be consumed
    assert not turn_mgr.ygo_turn_state.normal_summon_used
    print("  PASS: test_special_summon")


def test_setup_yugioh_player():
    """Test the setup_yugioh_player convenience method."""
    game = Game(mode="yugioh")
    p1 = game.add_player("Test Player")

    main_deck = [make_ygo_monster(f"Mon{i}", 1500, 1200, 4) for i in range(40)]
    extra_deck = [make_ygo_monster("Fusion", 2500, 2100, 7, ygo_monster_type="Fusion")]

    game.setup_yugioh_player(p1, main_deck, extra_deck)

    assert p1.lp == 8000
    library_key = f"library_{p1.id}"
    assert len(game.state.zones[library_key].objects) == 40

    extra_key = f"extra_deck_{p1.id}"
    assert len(game.state.zones[extra_key].objects) == 1
    print("  PASS: test_setup_yugioh_player")


def test_ai_action_logging_callback():
    """Test that AI actions trigger the log callback."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    logged = []
    turn_mgr.action_log_callback = lambda text, event_type, player: logged.append((text, event_type, player))
    turn_mgr.ai_players.add(p1.id)

    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("AI Monster", 1800, 1200, 4))
    turn_mgr._execute_action(p1.id, {'action_type': 'normal_summon', 'card_id': card.id})

    assert len(logged) == 1, f"Expected 1 log entry, got {len(logged)}"
    assert "Normal Summoned AI Monster" in logged[0][0]
    assert logged[0][1] == "summon"
    assert logged[0][2] == p1.id
    print("  PASS: test_ai_action_logging_callback")


def test_ai_logging_skipped_for_humans():
    """Test that human actions don't trigger the AI log callback."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    logged = []
    turn_mgr.action_log_callback = lambda text, event_type, player: logged.append((text, event_type, player))
    # p1 is NOT in ai_players

    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Human Monster", 1800, 1200, 4))
    turn_mgr._execute_action(p1.id, {'action_type': 'normal_summon', 'card_id': card.id})

    assert len(logged) == 0, "Human actions should not trigger AI log callback"
    print("  PASS: test_ai_logging_skipped_for_humans")


def test_turn_number_increments():
    """Test that turn_number increments on run_turn and is accessible via property."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    # Add enough cards for the game to not deck-out
    add_monsters_to_deck(game, p1, 40)
    add_monsters_to_deck(game, p2, 40)

    asyncio.get_event_loop().run_until_complete(turn_mgr.setup_game())

    assert turn_mgr.turn_number == 0, f"Should start at 0, got {turn_mgr.turn_number}"
    assert turn_mgr.turn_state.turn_number == 0

    # Make both players AI so run_turn completes without blocking
    turn_mgr.ai_players.add(p1.id)
    turn_mgr.ai_players.add(p2.id)

    # First turn
    asyncio.get_event_loop().run_until_complete(turn_mgr.run_turn())
    assert turn_mgr.turn_number == 1, f"Expected 1, got {turn_mgr.turn_number}"
    assert turn_mgr.turn_state.turn_number == 1

    # Second turn
    asyncio.get_event_loop().run_until_complete(turn_mgr.run_turn())
    assert turn_mgr.turn_number == 2, f"Expected 2, got {turn_mgr.turn_number}"
    assert turn_mgr.turn_state.turn_number == 2
    print("  PASS: test_turn_number_increments")


def test_tribute_summon_rejected_without_tributes():
    """Test that Level 5+ Normal Summon fails without tribute IDs."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Big Mon", 2400, 2100, 6))
    events = turn_mgr._do_normal_summon(p1.id, {'card_id': card.id})
    assert len(events) == 0, "Level 6 should fail without tributes"
    assert card.zone == ZoneType.HAND, "Card should remain in hand"
    assert not turn_mgr.ygo_turn_state.normal_summon_used, "Normal summon should not be consumed"
    print("  PASS: test_tribute_summon_rejected_without_tributes")


def test_ai_battle_phase_logging():
    """Test that AI attacks and battle damage are logged via callback."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    logged = []
    turn_mgr.action_log_callback = lambda text, event_type, player: logged.append((text, event_type, player))
    turn_mgr.ai_players.add(p1.id)

    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Summon an attacker for p1
    card = add_card_to_hand(game, p1, make_ygo_monster("Attacker", 1800, 1200, 4))
    turn_mgr._execute_action(p1.id, {'action_type': 'normal_summon', 'card_id': card.id})
    logged.clear()  # Clear the summon log

    # Mock AI battle handler: attack directly once, then end
    call_count = [0]
    class MockAI:
        def get_battle_action(self, player_id, state, yts):
            call_count[0] += 1
            if call_count[0] == 1:
                return {'action_type': 'declare_attack', 'attacker_id': card.id, 'target_id': None}
            return {'action_type': 'end_phase'}
    turn_mgr.ygo_ai_handler = MockAI()

    # Run battle phase with direct attack (no opponent monsters)
    import asyncio
    events = asyncio.get_event_loop().run_until_complete(
        turn_mgr._run_battle_phase(p1.id)
    )

    attack_logs = [l for l in logged if l[1] == 'attack']
    damage_logs = [l for l in logged if l[1] == 'damage']
    assert len(attack_logs) >= 1, f"Expected attack log, got {attack_logs}"
    assert "Attacker attacks directly" in attack_logs[0][0]
    assert len(damage_logs) >= 1, f"Expected damage log, got {damage_logs}"
    assert "1800" in damage_logs[0][0]
    print("  PASS: test_ai_battle_phase_logging")


def test_failed_action_no_log():
    """Test that a failed action does not trigger the AI log callback."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager

    logged = []
    turn_mgr.action_log_callback = lambda text, event_type, player: logged.append((text, event_type, player))
    turn_mgr.ai_players.add(p1.id)

    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Use normal summon first
    card1 = add_card_to_hand(game, p1, make_ygo_monster("First Mon", 1500, 1200, 4))
    turn_mgr._execute_action(p1.id, {'action_type': 'normal_summon', 'card_id': card1.id})
    assert len(logged) == 1  # First summon logged

    logged.clear()

    # Try a second normal summon — should fail (already used)
    card2 = add_card_to_hand(game, p1, make_ygo_monster("Second Mon", 1500, 1200, 4))
    turn_mgr._execute_action(p1.id, {'action_type': 'normal_summon', 'card_id': card2.id})
    assert len(logged) == 0, f"Failed action should not log, got {logged}"
    assert card2.zone == ZoneType.HAND, "Card should remain in hand"
    print("  PASS: test_failed_action_no_log")


def test_ai_log_uses_player_name():
    """Test that AI logs use the player name, not generic 'AI'."""
    game = Game(mode="yugioh")
    p1 = game.add_player("Yugi Muto")
    p2 = game.add_player("Seto Kaiba")
    turn_mgr = game.turn_manager

    logged = []
    turn_mgr.action_log_callback = lambda text, event_type, player: logged.append((text, event_type, player))
    turn_mgr.ai_players.add(p1.id)

    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Mystical Elf", 800, 2000, 4))
    turn_mgr._execute_action(p1.id, {'action_type': 'set_monster', 'card_id': card.id})

    assert len(logged) == 1, f"Expected 1 log entry, got {len(logged)}"
    assert "Yugi Muto" in logged[0][0], f"Expected player name in log, got: {logged[0][0]}"
    assert "AI" not in logged[0][0], f"Should not contain generic 'AI', got: {logged[0][0]}"
    print("  PASS: test_ai_log_uses_player_name")


def test_face_down_monster_cannot_attack():
    """Test that a face-down (set) monster cannot declare an attack."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Set Mon", 1500, 1200, 4))
    events = turn_mgr._do_set_monster(p1.id, {'card_id': card.id})
    assert len(events) > 0, "Set should succeed"
    assert card.state.ygo_position == 'face_down_def'

    # Try to attack with this face-down monster
    attack_events = turn_mgr._resolve_attack(p1.id, card.id, None, p2.id)
    assert len(attack_events) == 0, f"Face-down monster attack should return no events, got {len(attack_events)}"

    # Also check combat manager's can_attack
    if hasattr(turn_mgr, '_combat_manager') and turn_mgr._combat_manager:
        can, reason = turn_mgr._combat_manager.can_attack(card.id)
        assert not can, f"can_attack should be False for face-down, got True"

    print("  PASS: test_face_down_monster_cannot_attack")


def test_defense_position_cannot_attack():
    """Test that a face-up DEF position monster cannot attack."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    card = add_card_to_hand(game, p1, make_ygo_monster("Def Mon", 1000, 2000, 4))
    # Normal summon then change to DEF position
    turn_mgr._do_normal_summon(p1.id, {'card_id': card.id})
    assert card.state.ygo_position == 'face_up_atk'

    turn_mgr._do_change_position(p1.id, {'card_id': card.id})
    assert card.state.ygo_position == 'face_up_def'

    # Try to attack — should fail
    attack_events = turn_mgr._resolve_attack(p1.id, card.id, None, p2.id)
    assert len(attack_events) == 0, f"DEF position attack should return no events, got {len(attack_events)}"
    print("  PASS: test_defense_position_cannot_attack")


def test_end_phase_discard():
    """Test that End Phase forces discard to 6 cards."""
    game, p1, p2 = make_test_game()
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = p1.id

    # Give player 8 cards in hand
    for i in range(8):
        add_card_to_hand(game, p1, make_ygo_monster(f"Excess{i}", 1000, 1000, 4))

    hand_before = len(get_hand_objects(game, p1.id))
    assert hand_before == 8

    events = turn_mgr._run_end_phase(p1.id)

    hand_after = len(get_hand_objects(game, p1.id))
    assert hand_after == 6, f"Expected 6, got {hand_after}"
    assert len(events) == 2  # 2 discards
    print("  PASS: test_end_phase_discard")


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Yu-Gi-Oh! Stage 1 Tests")
    print("=" * 60)

    tests = [
        test_game_creation,
        test_lp_tracking,
        test_normal_summon,
        test_normal_summon_once_per_turn,
        test_tribute_summon_level5,
        test_tribute_summon_level7,
        test_set_monster,
        test_flip_summon,
        test_change_position,
        test_atk_vs_atk_attacker_wins,
        test_atk_vs_atk_defender_wins,
        test_atk_vs_atk_tie,
        test_atk_vs_def_attacker_wins,
        test_atk_vs_def_defender_wins,
        test_atk_vs_def_tie,
        test_direct_attack,
        test_lp_zero_loss,
        test_deck_out_loss,
        test_setup_game,
        test_flip_face_down_in_battle,
        test_set_spell_trap,
        test_monster_zone_limit,
        test_combat_manager,
        test_direct_attack_with_combat_manager,
        test_position_blocks_attack,
        test_special_summon,
        test_setup_yugioh_player,
        test_ai_action_logging_callback,
        test_ai_logging_skipped_for_humans,
        test_turn_number_increments,
        test_tribute_summon_rejected_without_tributes,
        test_ai_battle_phase_logging,
        test_failed_action_no_log,
        test_ai_log_uses_player_name,
        test_face_down_monster_cannot_attack,
        test_defense_position_cannot_attack,
        test_end_phase_discard,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 60}")
    if failed > 0:
        sys.exit(1)
