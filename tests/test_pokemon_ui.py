"""
Pokemon TCG UI Backend Tests

Tests for the UI overhaul backend changes:
- Game log generation
- Graveyard serialization with Pokemon fields
- GameLogEntry model
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_pokemon_ui.py`", allow_module_level=True)

from src.engine.game import Game, make_pokemon, make_basic_energy, make_trainer_item
from src.engine.types import CardType, ZoneType, EventType, CardDefinition
from src.engine.pokemon_turn import PokemonTurnManager
from src.server.models import GameLogEntry, GameStateResponse
from src.server.session import GameSession


def run(coro):
    """Run async function synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def setup_pokemon_game():
    """Set up a basic Pokemon game with two players for testing."""
    pikachu = make_pokemon(
        name="Pikachu", hp=70, pokemon_type="L",
        evolution_stage="Basic",
        attacks=[{"name": "Thunder Shock", "cost": [{"type": "L", "count": 1}], "damage": 20, "text": ""}],
        image_url="https://example.com/pikachu.png",
    )
    charmander = make_pokemon(
        name="Charmander", hp=60, pokemon_type="R",
        evolution_stage="Basic",
        attacks=[{"name": "Scratch", "cost": [{"type": "R", "count": 1}], "damage": 10, "text": ""}],
        image_url="https://example.com/charmander.png",
    )
    fire_energy = make_basic_energy("Fire Energy", "R")
    lightning_energy = make_basic_energy("Lightning Energy", "L")

    potion = make_trainer_item(
        name="Potion",
        text="Heal 30 damage from 1 of your Pokemon.",
    )

    p1_deck = [pikachu] * 10 + [lightning_energy] * 10
    p2_deck = [charmander] * 10 + [fire_energy] * 10 + [potion] * 5

    game = Game(mode="pokemon")
    p1 = game.add_player("Ash")
    p2 = game.add_player("Misty")

    game.setup_pokemon_player(p1, p1_deck)
    game.setup_pokemon_player(p2, p2_deck)

    session = GameSession(
        id="test-ui",
        game=game,
        mode="human_vs_bot",
        player_ids=[p1.id, p2.id],
        player_names={p1.id: "Ash", p2.id: "Misty"},
        human_players={p1.id},
    )

    return game, session, p1.id, p2.id


# ============================================================
# Test 1: GameLogEntry model creation
# ============================================================
print("\n--- Test 1: GameLogEntry Model ---")
entry = GameLogEntry(turn=1, text="Pikachu attacked!", event_type="attack", player="p1", timestamp=1234567890.0)
check("GameLogEntry fields", entry.turn == 1 and entry.text == "Pikachu attacked!" and entry.event_type == "attack")
check("GameLogEntry player", entry.player == "p1")
check("GameLogEntry timestamp", entry.timestamp == 1234567890.0)


# ============================================================
# Test 2: Game log generation via _add_pkm_log
# ============================================================
print("\n--- Test 2: Game Log Generation ---")
game, session, p1_id, p2_id = setup_pokemon_game()

session._add_pkm_log("Turn 1 - Ash's turn.", "turn_start", p1_id)
session._add_pkm_log("Pikachu attacked with Thunder Shock for 20!", "attack", p1_id)
session._add_pkm_log("Ash attached Lightning Energy to Pikachu.", "energy", p1_id)

check("Log has 3 entries", len(session._game_log) == 3)
check("First entry is turn_start", session._game_log[0].event_type == "turn_start")
check("Second entry is attack", session._game_log[1].event_type == "attack")
check("Third entry is energy", session._game_log[2].event_type == "energy")
check("Entry text correct", "Thunder Shock" in session._game_log[1].text)


# ============================================================
# Test 3: Game state response includes game_log
# ============================================================
print("\n--- Test 3: Game State Response with Game Log ---")

# Run setup to get game into playable state
run(game.turn_manager.setup_game())

# Add some log entries
session._add_pkm_log("Game started.", "turn_start", p1_id)
session._add_pkm_log("Pikachu played.", "play_basic", p1_id)

state = session.get_client_state(p1_id)
check("State has game_log field", hasattr(state, 'game_log'))
check("game_log is list", isinstance(state.game_log, list))
check("game_log has entries", len(state.game_log) > 0)
check("game_log entries have text", all(e.text for e in state.game_log))


# ============================================================
# Test 4: Graveyard serialization with Pokemon fields
# ============================================================
print("\n--- Test 4: Graveyard Serialization ---")

# Find a Pokemon card in p2's hand to move to graveyard
hand_zone = game.state.zones.get(f"hand_{p2_id}")
pokemon_card_id = None
if hand_zone:
    for obj_id in hand_zone.objects:
        obj = game.state.objects.get(obj_id)
        if obj and obj.card_def and CardType.POKEMON in obj.characteristics.types:
            pokemon_card_id = obj_id
            break

    # If no Pokemon in hand, check bench
    if not pokemon_card_id:
        bench_zone = game.state.zones.get(f"bench_{p2_id}")
        if bench_zone and bench_zone.objects:
            pokemon_card_id = bench_zone.objects[0]
            bench_zone.objects.remove(pokemon_card_id)
        else:
            # Use active
            active_zone = game.state.zones.get(f"active_spot_{p2_id}")
            if active_zone and active_zone.objects:
                pokemon_card_id = active_zone.objects[0]
                active_zone.objects.remove(pokemon_card_id)
    else:
        hand_zone.objects.remove(pokemon_card_id)

if pokemon_card_id:
    card_obj = game.state.objects.get(pokemon_card_id)
    graveyard_key = f"graveyard_{p2_id}"
    if graveyard_key in game.state.zones:
        game.state.zones[graveyard_key].objects.append(pokemon_card_id)
        card_obj.zone = ZoneType.GRAVEYARD

    state2 = session.get_client_state(p2_id)
    graveyard = state2.graveyard.get(p2_id, [])

    # Find the Pokemon card in the graveyard
    pkm_cards = [c for c in graveyard if 'POKEMON' in c.types]
    check("Graveyard has Pokemon card", len(pkm_cards) > 0)
    if pkm_cards:
        card = pkm_cards[0]
        check("Graveyard card has hp", card.hp is not None)
        check("Graveyard card has pokemon_type", card.pokemon_type is not None)
        check("Graveyard card has image_url", card.image_url is not None)
        check("Graveyard card has attacks", isinstance(card.attacks, list) and len(card.attacks) > 0)
        check("Graveyard card name present", card.name != "")
else:
    check("Found Pokemon card for graveyard test", False, "No Pokemon card found")


# ============================================================
# Test 5: Game log capped at 50 entries
# ============================================================
print("\n--- Test 5: Game Log Cap ---")
game3, session3, p1_id3, p2_id3 = setup_pokemon_game()
run(game3.turn_manager.setup_game())

for i in range(60):
    session3._add_pkm_log(f"Event {i}", "test", p1_id3)

state3 = session3.get_client_state(p1_id3)
check("Game log capped at 50", len(state3.game_log) == 50)
check("Last entry is most recent", state3.game_log[-1].text == "Event 59")
check("First entry is 10th (offset by 10)", state3.game_log[0].text == "Event 10")


# ============================================================
# Summary
# ============================================================
print(f"\n{'='*50}")
print(f"Pokemon UI Backend Tests: {passed} passed, {failed} failed")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
