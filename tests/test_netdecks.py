#!/usr/bin/env python3
"""
Test framework for playing netdecks against the AI.
Simulates a human player making decisions against the hard AI.

Can use either:
1. Built-in standard decks via deck_id (mono_red_aggro, dimir_control, etc.)
2. Custom card lists for testing specific interactions
"""

import urllib.request
import json
import time
import sys

BASE_URL = "http://localhost:8000/api/match"

# Available standard deck IDs:
# - mono_red_aggro, mono_green_ramp, dimir_control
# - boros_aggro, simic_tempo, lorwyn_faeries
# - avatar_airbender (partial), fire_nation_aggro (partial)

# Custom deck lists for testing (MTG Standard cards)
MONO_RED_AGGRO_CUSTOM = [
    # 1-drops (16)
    "Monastery Swiftspear", "Monastery Swiftspear", "Monastery Swiftspear", "Monastery Swiftspear",
    "Goblin Guide", "Goblin Guide", "Goblin Guide", "Goblin Guide",
    "Fervent Champion", "Fervent Champion", "Fervent Champion", "Fervent Champion",
    "Raging Goblin", "Raging Goblin", "Raging Goblin", "Raging Goblin",
    # 2-drops (8)
    "Embereth Veteran", "Embereth Veteran", "Embereth Veteran", "Embereth Veteran",
    "Torch Runner", "Torch Runner", "Torch Runner", "Torch Runner",
    # Burn spells (16)
    "Lightning Bolt", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt",
    "Shock", "Shock", "Shock", "Shock",
    "Lightning Strike", "Lightning Strike", "Lightning Strike", "Lightning Strike",
    "Monstrous Rage", "Monstrous Rage", "Monstrous Rage", "Monstrous Rage",
    # Lands (20)
    "Mountain", "Mountain", "Mountain", "Mountain", "Mountain",
    "Mountain", "Mountain", "Mountain", "Mountain", "Mountain",
    "Mountain", "Mountain", "Mountain", "Mountain", "Mountain",
    "Mountain", "Mountain", "Mountain", "Mountain", "Mountain",
]

DIMIR_CONTROL_CUSTOM = [
    # Creatures (8)
    "Fog Bank", "Fog Bank", "Fog Bank", "Fog Bank",
    "Slickshot Show-Off", "Slickshot Show-Off", "Slickshot Show-Off", "Slickshot Show-Off",
    # Counterspells (12)
    "Counterspell", "Counterspell", "Counterspell", "Counterspell",
    "Mana Leak", "Mana Leak", "Mana Leak", "Mana Leak",
    "Essence Scatter", "Essence Scatter", "Essence Scatter", "Essence Scatter",
    # Removal (8)
    "Go for the Throat", "Go for the Throat", "Go for the Throat", "Go for the Throat",
    "Torch the Tower", "Torch the Tower", "Torch the Tower", "Torch the Tower",
    # Card draw (8)
    "Brainstorm", "Brainstorm", "Brainstorm", "Brainstorm",
    "Deduce", "Deduce", "Deduce", "Deduce",
    # Lands (24)
    "Island", "Island", "Island", "Island", "Island",
    "Island", "Island", "Island", "Island", "Island",
    "Island", "Island",
    "Swamp", "Swamp", "Swamp", "Swamp", "Swamp",
    "Swamp", "Swamp", "Swamp", "Swamp", "Swamp",
    "Swamp", "Swamp",
]


def create_match(
    player_deck=None,
    ai_deck=None,
    player_deck_id=None,
    ai_deck_id=None,
    ai_difficulty: str = "ultra",
):
    """
    Create a new match with specified decks.

    Can use either deck_id (for built-in decks) or deck lists (for custom decks).
    """
    payload = {
        "player_name": "TestPlayer",
    }

    if ai_difficulty:
        payload["ai_difficulty"] = ai_difficulty

    # Player deck: prefer deck_id, fallback to card list
    if player_deck_id:
        payload["player_deck_id"] = player_deck_id
    elif player_deck:
        payload["player_deck"] = player_deck

    # AI deck: prefer deck_id, fallback to card list
    if ai_deck_id:
        payload["ai_deck_id"] = ai_deck_id
    elif ai_deck:
        payload["ai_deck"] = ai_deck

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}/create",
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


def start_match(match_id):
    """Start a match."""
    req = urllib.request.Request(f"{BASE_URL}/{match_id}/start", method='POST')
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


def get_state(match_id, player_id):
    """Get current game state."""
    url = f"{BASE_URL}/{match_id}/state?player_id={player_id}"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode())


def do_action(match_id, player_id, action_type, card_id=None, targets=None):
    """Perform an action."""
    payload = {
        "action_type": action_type,
        "player_id": player_id
    }
    if card_id:
        payload["card_id"] = card_id
    if targets:
        payload["targets"] = targets

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}/{match_id}/action",
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode())
        return result.get("new_state", result)

def submit_choice(match_id, player_id, choice_id, selected):
    """Submit a pending choice."""
    payload = {
        "choice_id": choice_id,
        "player_id": player_id,
        "selected": selected,
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}/{match_id}/choice",
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode())
        return result.get("new_state", result)


def pick_choice(choice: dict, state: dict, player_id: str) -> list:
    """Pick a reasonable default selection for a pending choice."""
    if not choice:
        return []

    choice_type = choice.get("choice_type")
    options = choice.get("options") or []
    min_choices = int(choice.get("min_choices", 1) or 0)
    max_choices = int(choice.get("max_choices", 1) or 0)

    # For information-reordering choices, default to "no-op".
    if choice_type in ("scry", "surveil") and min_choices == 0:
        return []

    # For targeting choices, prefer opponent-controlled objects (or the opponent player).
    if choice_type and choice_type.startswith("target"):
        try:
            opp_id = next(pid for pid in state.get("players", {}) if pid != player_id)
        except StopIteration:
            opp_id = None

        controller_by_id = {}
        for perm in state.get("battlefield", []) or []:
            perm_id = perm.get("id")
            if perm_id:
                controller_by_id[perm_id] = perm.get("controller")

        prioritized = []
        if opp_id:
            # Prefer directly targeting the opponent player if available.
            if opp_id in options:
                prioritized.append(opp_id)
            # Prefer opponent-controlled permanents.
            prioritized.extend([
                opt for opt in options
                if isinstance(opt, str) and controller_by_id.get(opt) == opp_id and opt not in prioritized
            ])

        # Append remaining options in original order.
        for opt in options:
            if opt not in prioritized:
                prioritized.append(opt)
        options = prioritized

    selected = []
    for opt in options:
        if isinstance(opt, dict):
            if opt.get("id") is not None:
                selected.append(opt["id"])
            elif opt.get("index") is not None:
                selected.append(opt["index"])
            else:
                selected.append(opt)
        else:
            selected.append(opt)

        if len(selected) >= max(1, min_choices):
            break

    if max_choices and len(selected) > max_choices:
        selected = selected[:max_choices]

    return selected


def print_state(state, player_id, verbose=True):
    """Print game state summary."""
    me = state["players"][player_id]
    opp_id = [p for p in state["players"] if p != player_id][0]
    opp = state["players"][opp_id]

    print(f"\n{'='*60}")
    print(f"Turn {state['turn_number']} | {state['phase']}/{state['step']}")
    print(f"Active: {'ME' if state['active_player'] == player_id else 'OPP'} | Priority: {'ME' if state['priority_player'] == player_id else 'OPP'}")
    print(f"{'='*60}")
    print(f"LIFE: Me={me['life']} | Opp={opp['life']}")
    print(f"LIBRARY: Me={me['library_size']} | Opp={opp['library_size']}")

    # Battlefield
    my_perms = [p for p in state["battlefield"] if p["controller"] == player_id]
    opp_perms = [p for p in state["battlefield"] if p["controller"] == opp_id]

    my_lands = [p for p in my_perms if "LAND" in p["types"]]
    my_creatures = [p for p in my_perms if "CREATURE" in p["types"]]
    opp_lands = [p for p in opp_perms if "LAND" in p["types"]]
    opp_creatures = [p for p in opp_perms if "CREATURE" in p["types"]]

    untapped_lands = len([l for l in my_lands if not l["tapped"]])
    tapped_lands = len([l for l in my_lands if l["tapped"]])

    print(f"\nMY BOARD:")
    print(f"  Lands: {untapped_lands} untapped, {tapped_lands} tapped")
    if my_creatures:
        for c in my_creatures:
            status = " (tapped)" if c["tapped"] else ""
            print(f"  - {c['name']} {c['power']}/{c['toughness']}{status}")

    print(f"\nOPP BOARD:")
    print(f"  Lands: {len([l for l in opp_lands if not l['tapped']])} untapped, {len([l for l in opp_lands if l['tapped']])} tapped")
    if opp_creatures:
        for c in opp_creatures:
            status = " (tapped)" if c["tapped"] else ""
            print(f"  - {c['name']} {c['power']}/{c['toughness']}{status}")

    # Hand
    print(f"\nMY HAND ({len(state['hand'])}):")
    for i, card in enumerate(state['hand']):
        print(f"  [{i}] {card['name']} - {card['mana_cost']}")

    # Stack
    if state["stack"]:
        print(f"\nSTACK:")
        for item in state["stack"]:
            print(f"  - {item.get('source_name', 'Unknown')}")

    # Legal actions
    if verbose and state["legal_actions"]:
        print(f"\nLEGAL ACTIONS:")
        for i, action in enumerate(state["legal_actions"]):
            print(f"  [{i}] {action['type']}: {action['description']}")


def smart_play(state, player_id):
    """
    Make intelligent plays for mono-red aggro.
    Returns (action_type, card_id, targets) or None for pass.
    """
    if state["priority_player"] != player_id:
        return ("PASS", None, None)

    legal = state["legal_actions"]
    action_types = [a["type"] for a in legal]
    phase = state["phase"]
    active = state["active_player"]

    opp_id = [p for p in state["players"] if p != player_id][0]
    opp_life = state["players"][opp_id]["life"]

    # Get my available mana (count untapped lands)
    my_lands = [p for p in state["battlefield"]
                if p["controller"] == player_id and "LAND" in p["types"] and not p["tapped"]]
    available_mana = len(my_lands)

    # Main phase logic
    if phase in ["PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"] and active == player_id:
        # Play a land first
        land_actions = [a for a in legal if a["type"] == "PLAY_LAND"]
        if land_actions:
            return ("PLAY_LAND", land_actions[0]["card_id"], None)

        # Cast creatures (prioritize by mana cost - play cheap ones first)
        cast_actions = [a for a in legal if a["type"] == "CAST_SPELL"]
        creature_casts = []
        for ca in cast_actions:
            card = next((c for c in state["hand"] if c["id"] == ca["card_id"]), None)
            if card and "CREATURE" in card["types"]:
                # Count mana cost
                cost = card["mana_cost"].count('{')
                creature_casts.append((cost, ca, card))

        # Sort by cost (cheapest first)
        creature_casts.sort(key=lambda x: x[0])
        if creature_casts:
            _, action, card = creature_casts[0]
            return ("CAST_SPELL", action["card_id"], None)

        # Cast noncreature spells that don't require explicit targets (card draw, filtering, etc.).
        # This increases coverage for the pending choice system (e.g. "look at top N, reorder").
        noncreature_casts = []
        for ca in cast_actions:
            if ca.get("requires_targets"):
                continue
            card = next((c for c in state["hand"] if c["id"] == ca["card_id"]), None)
            if not card:
                continue
            if "CREATURE" in card["types"] or "LAND" in card["types"]:
                continue
            cost = (card.get("mana_cost") or "").count('{')
            noncreature_casts.append((cost, ca, card))

        noncreature_casts.sort(key=lambda x: x[0])
        if noncreature_casts:
            _, action, _card = noncreature_casts[0]
            return ("CAST_SPELL", action["card_id"], None)

        # Cast burn at opponent's face if they're low
        for ca in cast_actions:
            card = next((c for c in state["hand"] if c["id"] == ca["card_id"]), None)
            if card and "INSTANT" in card["types"]:
                # Check if it's a burn spell
                if "damage" in card.get("text", "").lower() or card["name"] in ["Lightning Bolt", "Shock", "Lightning Strike"]:
                    # Target opponent
                    return ("CAST_SPELL", ca["card_id"], [[opp_id]])

    # Combat - attack with everything
    # (Combat is handled automatically by the AI system for human players via callbacks)

    return ("PASS", None, None)


def run_game_with_id(
    verbose=True,
    player_deck=None,
    ai_deck=None,
    player_deck_id=None,
    ai_deck_id=None,
    description=None,
    ai_difficulty: str = "ultra",
):
    """Run a full game and return (final_state, player_id)."""
    state = run_game(
        verbose=verbose,
        player_deck=player_deck,
        ai_deck=ai_deck,
        player_deck_id=player_deck_id,
        ai_deck_id=ai_deck_id,
        description=description,
        return_player_id=True,
        ai_difficulty=ai_difficulty,
    )
    return state


def run_game(
    verbose=True,
    player_deck=None,
    ai_deck=None,
    player_deck_id=None,
    ai_deck_id=None,
    description=None,
    return_player_id=False,
    ai_difficulty: str = "ultra",
):
    """Run a full game with smart plays."""
    print("Creating match...")
    result = create_match(
        player_deck=player_deck,
        ai_deck=ai_deck,
        player_deck_id=player_deck_id,
        ai_deck_id=ai_deck_id,
        ai_difficulty=ai_difficulty,
    )
    match_id = result["match_id"]
    player_id = result["player_id"]
    print(f"Match ID: {match_id}, Player ID: {player_id}")

    print("Starting match...")
    start_match(match_id)
    time.sleep(0.5)

    state = get_state(match_id, player_id)
    last_turn = 0
    action_count = 0
    max_actions = 500

    game_desc = description or "Player vs AI"
    print("\n" + "="*60)
    print(f"GAME START - {game_desc}")
    print("="*60)

    while not state.get("is_game_over") and action_count < max_actions:
        # Handle pending choices for the player (targets, modal, scry, etc.)
        pending_choice = state.get("pending_choice")
        if pending_choice and pending_choice.get("player") == player_id:
            selected = pick_choice(pending_choice, state, player_id)
            if verbose:
                print(f"  >> Choice: {pending_choice.get('choice_type')} {pending_choice.get('prompt')}")
            try:
                state = submit_choice(match_id, player_id, pending_choice["id"], selected)
            except Exception as e:
                print(f"Choice error: {e}")
            action_count += 1
            time.sleep(0.01)
            continue

        # Print state on turn change
        if state["turn_number"] != last_turn:
            if verbose:
                print_state(state, player_id, verbose=False)
            last_turn = state["turn_number"]

        # Make a play
        action_type, card_id, targets = smart_play(state, player_id)

        if verbose and action_type != "PASS":
            if card_id:
                card = next((c for c in state["hand"] if c["id"] == card_id), None)
                if card:
                    print(f"  >> Playing: {card['name']}")
                else:
                    print(f"  >> Action: {action_type}")

        try:
            state = do_action(match_id, player_id, action_type, card_id, targets)
        except Exception as e:
            print(f"Error: {e}")
            # Try to recover
            state = do_action(match_id, player_id, "PASS")

        action_count += 1
        time.sleep(0.01)

    # Final state
    print("\n" + "="*60)
    print("GAME OVER")
    print("="*60)
    print_state(state, player_id, verbose=True)

    me = state["players"][player_id]
    opp_id = [p for p in state["players"] if p != player_id][0]
    opp = state["players"][opp_id]

    if state.get("is_game_over"):
        winner = state.get("winner")
        if winner == player_id:
            print("\n*** VICTORY! ***")
        elif winner:
            print("\n*** DEFEAT ***")
        else:
            print("\n*** DRAW ***")
    else:
        print(f"\nGame did not complete after {action_count} actions")

    print(f"Final: Me={me['life']} vs Opp={opp['life']}")
    print(f"Total actions: {action_count}")

    if return_player_id:
        return state, player_id
    return state


def run_matchup(player_deck_id, ai_deck_id, games=3, verbose=False, ai_difficulty: str = "ultra"):
    """Test a specific matchup multiple times."""
    wins = 0
    losses = 0
    draws = 0

    print(f"\n{'='*60}")
    print(f"MATCHUP TEST: {player_deck_id} vs {ai_deck_id}")
    print(f"Running {games} games...")
    print("="*60)

    for i in range(games):
        print(f"\n--- Game {i+1}/{games} ---")
        state, player_id = run_game_with_id(
            verbose=verbose,
            player_deck_id=player_deck_id,
            ai_deck_id=ai_deck_id,
            description=f"{player_deck_id} vs {ai_deck_id}",
            ai_difficulty=ai_difficulty,
        )

        if state.get("is_game_over"):
            winner = state.get("winner")
            if winner == player_id:
                wins += 1
            elif winner:
                losses += 1
            else:
                draws += 1
        else:
            # Game didn't finish (hit action limit)
            draws += 1

    print(f"\n{'='*60}")
    print(f"MATCHUP RESULTS: {player_deck_id} vs {ai_deck_id}")
    print(f"Wins: {wins}, Losses: {losses}, Draws: {draws}")
    print(f"Win rate: {wins/games*100:.1f}%")
    print("="*60)

    return {"wins": wins, "losses": losses, "draws": draws}


def run_all_matchups(games_per_matchup=2, ai_difficulty: str = "ultra"):
    """Test all viable deck matchups."""
    # Decks with all cards available
    complete_decks = [
        "mono_red_aggro",
        "mono_green_ramp",
        "dimir_control",
        "boros_aggro",
        "simic_tempo",
        "lorwyn_faeries",
    ]

    results = {}
    for player_deck in complete_decks[:3]:  # Test first 3 as player
        for ai_deck in complete_decks[:3]:  # Against first 3 as AI
            if player_deck != ai_deck:
                key = f"{player_deck} vs {ai_deck}"
                results[key] = run_matchup(player_deck, ai_deck, games=games_per_matchup, ai_difficulty=ai_difficulty)

    print("\n\n" + "="*60)
    print("OVERALL RESULTS")
    print("="*60)
    for matchup, result in results.items():
        print(f"{matchup}: {result['wins']}W-{result['losses']}L-{result['draws']}D")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test netdecks against the AI")
    parser.add_argument("--player", "-p", default=None, help="Player deck ID")
    parser.add_argument("--ai", "-a", default=None, help="AI deck ID")
    parser.add_argument("--custom", action="store_true", help="Use custom deck lists")
    parser.add_argument("--ai-difficulty", default="ultra", help="AI difficulty (easy, medium, hard, ultra)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--games", "-g", type=int, default=1, help="Number of games")
    parser.add_argument("--all", action="store_true", help="Test all matchups")

    args = parser.parse_args()

    if args.all:
        run_all_matchups(games_per_matchup=args.games, ai_difficulty=args.ai_difficulty)
    elif args.player and args.ai:
        run_matchup(args.player, args.ai, games=args.games, verbose=args.verbose, ai_difficulty=args.ai_difficulty)
    elif args.custom:
        run_game(
            verbose=args.verbose,
            player_deck=MONO_RED_AGGRO_CUSTOM,
            ai_deck=DIMIR_CONTROL_CUSTOM,
            description="Custom Mono-Red vs Custom Dimir",
            ai_difficulty=args.ai_difficulty,
        )
    else:
        # Default: run one game with built-in decks
        run_game(
            verbose=args.verbose,
            player_deck_id="mono_red_aggro",
            ai_deck_id="dimir_control",
            description="Mono-Red Aggro vs Dimir Control",
            ai_difficulty=args.ai_difficulty,
        )
