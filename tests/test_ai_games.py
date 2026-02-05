"""
AI vs AI Game Testing

Runs multiple games between AI players with different strategies and decks
to stress test the engine and observe AI decision-making.
"""

import sys
import random
sys.path.insert(0, '.')

from src.engine import (
    Game, GameState, Event, EventType, Phase, ZoneType,
    CardType, ActionType, PlayerAction, Color,
    get_power, get_toughness
)
from src.engine.turn import TurnState
from src.ai import AIEngine
from src.ai.strategies import AggroStrategy, ControlStrategy, MidrangeStrategy
from src.ai.evaluator import BoardEvaluator
from src.cards.custom.lorwyn_custom import LORWYN_CUSTOM_CARDS


def get_cards_by_type(card_type: CardType) -> list:
    """Get all cards of a specific type from Lorwyn Custom."""
    return [
        card for card in LORWYN_CUSTOM_CARDS.values()
        if card_type in card.characteristics.types
    ]


def get_cards_by_color(color: Color) -> list:
    """Get all cards with a specific color from Lorwyn Custom."""
    return [
        card for card in LORWYN_CUSTOM_CARDS.values()
        if color in (card.characteristics.colors or set())
    ]


def get_cards_by_cmc(max_cmc: int) -> list:
    """Get all cards with CMC <= max_cmc from Lorwyn Custom."""
    from src.engine.mana import ManaCost
    results = []
    for card in LORWYN_CUSTOM_CARDS.values():
        if card.mana_cost:
            try:
                cost = ManaCost.parse(card.mana_cost)
                if cost.mana_value <= max_cmc:
                    results.append(card)
            except:
                pass
    return results


def build_kithkin_deck() -> list:
    """Build a mono-white Kithkin tribal deck."""
    deck = []

    # Get Kithkin creatures
    kithkin = [
        card for card in LORWYN_CUSTOM_CARDS.values()
        if 'Kithkin' in (card.characteristics.subtypes or set()) and CardType.CREATURE in card.characteristics.types
    ]

    # Sort by CMC for curve
    from src.engine.mana import ManaCost
    def get_cmc(card):
        if not card.mana_cost:
            return 0
        try:
            return ManaCost.parse(card.mana_cost).mana_value
        except:
            return 0

    kithkin.sort(key=get_cmc)

    # Take first 15 Kithkin (duplicates OK for testing)
    for card in kithkin[:15]:
        deck.extend([card] * 2)  # 2 copies each = 30 creatures

    # Add Plains - 24 lands for 54 total is fine for testing
    plains = LORWYN_CUSTOM_CARDS.get('Plains')
    if plains:
        deck.extend([plains] * 24)

    return deck[:60]  # Cap at 60


def build_merfolk_deck() -> list:
    """Build a mono-blue Merfolk tribal deck."""
    deck = []

    # Get Merfolk creatures
    merfolk = [
        card for card in LORWYN_CUSTOM_CARDS.values()
        if 'Merfolk' in (card.characteristics.subtypes or set()) and CardType.CREATURE in card.characteristics.types
    ]

    from src.engine.mana import ManaCost
    def get_cmc(card):
        if not card.mana_cost:
            return 0
        try:
            return ManaCost.parse(card.mana_cost).mana_value
        except:
            return 0

    merfolk.sort(key=get_cmc)

    for card in merfolk[:15]:
        deck.extend([card] * 2)

    island = LORWYN_CUSTOM_CARDS.get('Island')
    if island:
        deck.extend([island] * 24)

    return deck[:60]


def build_goblin_deck() -> list:
    """Build a mono-red Goblin tribal deck."""
    deck = []

    goblins = [
        card for card in LORWYN_CUSTOM_CARDS.values()
        if 'Goblin' in (card.characteristics.subtypes or set()) and CardType.CREATURE in card.characteristics.types
    ]

    from src.engine.mana import ManaCost
    def get_cmc(card):
        if not card.mana_cost:
            return 0
        try:
            return ManaCost.parse(card.mana_cost).mana_value
        except:
            return 0

    goblins.sort(key=get_cmc)

    for card in goblins[:15]:
        deck.extend([card] * 2)

    mountain = LORWYN_CUSTOM_CARDS.get('Mountain')
    if mountain:
        deck.extend([mountain] * 24)

    return deck[:60]


def build_elf_deck() -> list:
    """Build a mono-green Elf tribal deck."""
    deck = []

    elves = [
        card for card in LORWYN_CUSTOM_CARDS.values()
        if 'Elf' in (card.characteristics.subtypes or set()) and CardType.CREATURE in card.characteristics.types
    ]

    from src.engine.mana import ManaCost
    def get_cmc(card):
        if not card.mana_cost:
            return 0
        try:
            return ManaCost.parse(card.mana_cost).mana_value
        except:
            return 0

    elves.sort(key=get_cmc)

    for card in elves[:15]:
        deck.extend([card] * 2)

    forest = LORWYN_CUSTOM_CARDS.get('Forest')
    if forest:
        deck.extend([forest] * 24)

    return deck[:60]


def setup_game_state(deck1: list, deck2: list) -> tuple[Game, str, str]:
    """Set up a game with two decks. Returns (game, player1_id, player2_id)."""
    game = Game()

    # Add players
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Load decks
    for card_def in deck1:
        game.add_card_to_library(p1.id, card_def)

    for card_def in deck2:
        game.add_card_to_library(p2.id, card_def)

    # Shuffle
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    # Draw opening hands
    game.draw_cards(p1.id, 7)
    game.draw_cards(p2.id, 7)

    return game, p1.id, p2.id


def get_legal_actions(game: Game, player_id: str) -> list:
    """Get legal actions for a player."""
    return game.priority_system.get_legal_actions(player_id)


def display_battlefield(game: Game, player_ids: list[str] = None):
    """Display the current battlefield state."""
    state = game.state

    print("\n" + "=" * 60)
    print("BATTLEFIELD STATE")
    print("=" * 60)

    if player_ids is None:
        player_ids = list(state.players.keys())

    for player_id in player_ids:
        player = state.players[player_id]
        print(f"\n{player.name} (Life: {player.life})")
        print("-" * 40)

        creatures = []
        lands = []
        other = []

        for obj_id, obj in state.objects.items():
            if obj.controller == player_id and obj.zone == ZoneType.BATTLEFIELD:
                power = get_power(obj, state)
                toughness = get_toughness(obj, state)
                damage = obj.damage_marked or 0

                if CardType.CREATURE in obj.characteristics.types:
                    status = []
                    if obj.state.tapped:
                        status.append("tapped")
                    if obj.summoning_sickness:
                        status.append("sick")
                    status_str = f" ({', '.join(status)})" if status else ""
                    creatures.append(f"  {obj.name} {power}/{toughness}{status_str}")
                elif CardType.LAND in obj.characteristics.types:
                    tap_str = " (tapped)" if obj.state.tapped else ""
                    lands.append(f"  {obj.name}{tap_str}")
                else:
                    other.append(f"  {obj.name}")

        if creatures:
            print(f"Creatures ({len(creatures)}):")
            for c in creatures:
                print(c)

        if lands:
            print(f"Lands ({len(lands)}):")
            # Group lands
            land_counts = {}
            for l in lands:
                land_counts[l] = land_counts.get(l, 0) + 1
            for land, count in land_counts.items():
                if count > 1:
                    print(f"{land} x{count}")
                else:
                    print(land)

        if other:
            print("Other:")
            for o in other:
                print(o)

        # Hand count
        hand_count = sum(1 for obj in state.objects.values()
                        if obj.owner == player_id and obj.zone == ZoneType.HAND)
        print(f"Cards in hand: {hand_count}")


def play_turn(game: Game, player_id: str, opponent_id: str, ai: AIEngine, turn_num: int, verbose: bool = True) -> bool:
    """
    Play a full turn for the given player using the AI.
    Returns True if the game should continue.
    """
    state = game.state
    player = state.players[player_id]
    opponent = state.players[opponent_id]

    if verbose:
        print(f"\n{'='*60}")
        print(f"TURN {turn_num}: {player.name}'s turn")
        print(f"Life: {player.name}={player.life}, {opponent.name}={opponent.life}")
        print(f"{'='*60}")

    # Set up turn state on the TurnManager (not GameState)
    game.turn_manager.turn_state.active_player_id = player_id
    game.turn_manager.turn_state.lands_played_count = 0
    game.turn_manager.turn_state.land_played = False
    game.turn_manager.turn_state.lands_allowed = 1
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    # Also update GameState's lands tracking
    state.lands_played_this_turn = 0
    state.lands_allowed_this_turn = 1

    # Untap permanents
    for obj_id, obj in state.objects.items():
        if obj.controller == player_id and obj.zone == ZoneType.BATTLEFIELD:
            if obj.state.tapped:
                obj.state.tapped = False

    # Clear summoning sickness for creatures that have been around
    for obj_id, obj in state.objects.items():
        if obj.controller == player_id and obj.zone == ZoneType.BATTLEFIELD:
            if hasattr(obj, 'entered_this_turn') and not obj.entered_this_turn:
                obj.summoning_sickness = False
            if hasattr(obj, 'turns_on_battlefield'):
                if obj.turns_on_battlefield > 0:
                    obj.summoning_sickness = False

    # Draw a card (skip on turn 1 for player 1)
    if turn_num > 1 or player_id == 'player2':
        game.draw_cards(player_id)
        if verbose:
            print(f"{player.name} draws a card")

    # Main phase 1 - play lands and cast creatures
    actions_taken = 0
    max_actions = 20  # Prevent infinite loops
    skipped_cards = set()  # Cards we've tried and can't afford

    while actions_taken < max_actions:
        legal_actions = get_legal_actions(game, player_id)

        if not legal_actions:
            break

        # Get AI decision
        action = ai.get_action(player_id, state, legal_actions)

        if action.type == ActionType.PASS:
            break

        # Execute action
        if action.type == ActionType.PLAY_LAND and action.card_id:
            card = state.objects.get(action.card_id)
            if card and verbose:
                print(f"  -> {player.name} plays {card.name}")

            # Move to battlefield - must update zone lists properly
            if card:
                # Remove from hand
                hand_key = f"hand_{player_id}"
                hand_zone = state.zones.get(hand_key)
                if hand_zone and card.id in hand_zone.objects:
                    hand_zone.objects.remove(card.id)

                # Add to battlefield
                bf_zone = state.zones.get('battlefield')
                if bf_zone:
                    bf_zone.objects.append(card.id)

                card.zone = ZoneType.BATTLEFIELD
                game.turn_manager.turn_state.land_played = True
                game.turn_manager.turn_state.lands_played_count += 1
                state.lands_played_this_turn += 1

                # Register interceptors if setup function exists
                if card.card_def and card.card_def.setup_interceptors:
                    interceptors = card.card_def.setup_interceptors(card, state)
                    for interceptor in interceptors:
                        state.interceptors[interceptor.id] = interceptor
                        card.interceptor_ids.append(interceptor.id)

        elif action.type == ActionType.CAST_SPELL and action.card_id:
            card = state.objects.get(action.card_id)
            if not card:
                continue

            # Skip cards we've already tried and couldn't afford
            if action.card_id in skipped_cards:
                continue

            # Pay mana (simplified - just tap lands)
            from src.engine.mana import ManaCost
            cost = ManaCost.parse(card.characteristics.mana_cost or "")
            mana_needed = cost.mana_value

            # Count untapped lands
            lands_to_tap = []
            for obj_id, obj in state.objects.items():
                if (obj.controller == player_id and
                    obj.zone == ZoneType.BATTLEFIELD and
                    CardType.LAND in obj.characteristics.types and
                    not obj.state.tapped):
                    lands_to_tap.append(obj)

            # Check if we can afford it
            if len(lands_to_tap) < mana_needed:
                skipped_cards.add(action.card_id)
                continue

            if verbose:
                print(f"  -> {player.name} casts {card.name}")

            # Tap lands to pay
            for land in lands_to_tap[:mana_needed]:
                land.state.tapped = True

            # Move creature to battlefield - must update zone lists properly
            if CardType.CREATURE in card.characteristics.types:
                # Remove from hand
                hand_key = f"hand_{player_id}"
                hand_zone = state.zones.get(hand_key)
                if hand_zone and card.id in hand_zone.objects:
                    hand_zone.objects.remove(card.id)

                # Add to battlefield
                bf_zone = state.zones.get('battlefield')
                if bf_zone:
                    bf_zone.objects.append(card.id)

                card.zone = ZoneType.BATTLEFIELD
                card.summoning_sickness = True
                card.entered_this_turn = True
                card.turns_on_battlefield = 0

                # Fire ETB trigger
                game.emit(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': card.id,
                        'from_zone': ZoneType.HAND,
                        'to_zone': ZoneType.BATTLEFIELD
                    },
                    source=card.id
                ))

                # Register interceptors
                if card.card_def and card.card_def.setup_interceptors:
                    interceptors = card.card_def.setup_interceptors(card, state)
                    for interceptor in interceptors:
                        state.interceptors[interceptor.id] = interceptor
                        card.interceptor_ids.append(interceptor.id)

        elif action.type == ActionType.ACTIVATE_ABILITY and action.source_id:
            if verbose:
                source = state.objects.get(action.source_id)
                if source:
                    print(f"  -> {player.name} activates ability of {source.name}")

        actions_taken += 1

    # Combat phase
    game.turn_manager.turn_state.phase = Phase.COMBAT

    # Get legal attackers
    legal_attackers = []
    for obj_id, obj in state.objects.items():
        if (obj.controller == player_id and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            not obj.state.tapped and
            not obj.summoning_sickness):
            legal_attackers.append(obj_id)

    if legal_attackers:
        # AI decides attacks
        evaluator = BoardEvaluator(state)
        attacks = ai.get_attack_declarations(player_id, state, legal_attackers)

        if attacks:
            if verbose:
                print(f"\n  COMBAT:")

            for attack in attacks:
                attacker = state.objects.get(attack.attacker_id)
                if attacker:
                    attacker.state.tapped = True
                    power = get_power(attacker, state)
                    if verbose:
                        print(f"    {attacker.name} ({power}/{get_toughness(attacker, state)}) attacks")

            # Defender gets to block
            # Blockers step
            legal_blockers = []
            for obj_id, obj in state.objects.items():
                if (obj.controller == opponent_id and
                    obj.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in obj.characteristics.types and
                    not obj.state.tapped):
                    legal_blockers.append(obj_id)

            # Get opponent AI (use the same AI for simplicity)
            blocks = ai.get_block_declarations(opponent_id, state, attacks, legal_blockers)

            blocked_attackers = set()
            for block in blocks:
                blocked_attackers.add(block.attacker_id)
                blocker = state.objects.get(block.blocker_id)
                attacker = state.objects.get(block.attacker_id)
                if blocker and attacker and verbose:
                    print(f"    {blocker.name} blocks {attacker.name}")

            # Damage step
            # Damage step

            for attack in attacks:
                attacker = state.objects.get(attack.attacker_id)
                if not attacker:
                    continue

                power = get_power(attacker, state)

                if attack.attacker_id in blocked_attackers:
                    # Find blockers
                    for block in blocks:
                        if block.attacker_id == attack.attacker_id:
                            blocker = state.objects.get(block.blocker_id)
                            if blocker:
                                # Attacker damages blocker
                                blocker_tough = get_toughness(blocker, state)
                                blocker.damage_marked = (blocker.damage_marked or 0) + power

                                # Blocker damages attacker
                                blocker_power = get_power(blocker, state)
                                attacker.damage_marked = (attacker.damage_marked or 0) + blocker_power

                                if verbose:
                                    print(f"    Combat: {attacker.name} and {blocker.name} trade blows")
                else:
                    # Unblocked - damage to player
                    opponent.life -= power
                    if verbose:
                        print(f"    {attacker.name} deals {power} damage to {opponent.name}")

                    game.emit(Event(
                        type=EventType.DAMAGE,
                        payload={
                            'source': attack.attacker_id,
                            'target': opponent_id,
                            'amount': power,
                            'is_combat': True
                        },
                        source=attack.attacker_id
                    ))

            # Check for creature deaths (state-based actions)
            creatures_to_kill = []
            for obj_id, obj in state.objects.items():
                if (obj.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in obj.characteristics.types):
                    toughness = get_toughness(obj, state)
                    damage = obj.damage_marked or 0
                    if damage >= toughness:
                        creatures_to_kill.append(obj_id)

            for obj_id in creatures_to_kill:
                obj = state.objects.get(obj_id)
                if obj:
                    if verbose:
                        print(f"    {obj.name} dies!")

                    # Remove from battlefield
                    bf_zone = state.zones.get('battlefield')
                    if bf_zone and obj_id in bf_zone.objects:
                        bf_zone.objects.remove(obj_id)

                    # Add to graveyard
                    gy_key = f"graveyard_{obj.owner}"
                    gy_zone = state.zones.get(gy_key)
                    if gy_zone:
                        gy_zone.objects.append(obj_id)

                    obj.zone = ZoneType.GRAVEYARD
                    obj.damage_marked = 0

                    # Clean up interceptors
                    for int_id in obj.interceptor_ids:
                        if int_id in state.interceptors:
                            del state.interceptors[int_id]
                    obj.interceptor_ids.clear()

    # End step - clear damage
    for obj_id, obj in state.objects.items():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            obj.damage_marked = 0
            obj.entered_this_turn = False
            if hasattr(obj, 'turns_on_battlefield'):
                obj.turns_on_battlefield += 1
            else:
                obj.turns_on_battlefield = 1

    # Check for game end
    if opponent.life <= 0:
        print(f"\n{'*'*60}")
        print(f"GAME OVER! {player.name} wins!")
        print(f"{'*'*60}")
        return False

    if player.life <= 0:
        print(f"\n{'*'*60}")
        print(f"GAME OVER! {opponent.name} wins!")
        print(f"{'*'*60}")
        return False

    return True


def run_game(deck1: list, deck2: list, ai1: AIEngine, ai2: AIEngine,
             max_turns: int = 30, verbose: bool = True) -> str:
    """
    Run a full game between two decks with two AIs.
    Returns the winner's name or 'draw'.
    """
    game, p1_id, p2_id = setup_game_state(deck1, deck2)
    state = game.state

    if verbose:
        print("\n" + "=" * 60)
        print("NEW GAME")
        print("=" * 60)
        print(f"Player 1 (Alice): {ai1.strategy.__class__.__name__}, {ai1.difficulty}")
        print(f"Player 2 (Bob): {ai2.strategy.__class__.__name__}, {ai2.difficulty}")
        print(f"Deck 1: {len(deck1)} cards")
        print(f"Deck 2: {len(deck2)} cards")

    turn = 1
    current_player = p1_id
    player_ids = [p1_id, p2_id]

    while turn <= max_turns:
        ai = ai1 if current_player == p1_id else ai2
        other_player = p2_id if current_player == p1_id else p1_id

        if not play_turn(game, current_player, other_player, ai, turn, verbose):
            # Game ended
            p1 = state.players[p1_id]
            p2 = state.players[p2_id]
            winner = p1.name if p2.life <= 0 else p2.name
            return winner

        # Switch player
        if current_player == p2_id:
            turn += 1
        current_player = p2_id if current_player == p1_id else p1_id

        # Show battlefield every few turns
        if verbose and turn % 3 == 0:
            display_battlefield(game, player_ids)

    if verbose:
        print(f"\nGame ended in a draw after {max_turns} turns")
        display_battlefield(game, player_ids)

    return 'draw'


def main():
    """Run AI game tests."""
    print("=" * 60)
    print("HYPERDRAFT AI VS AI TESTING")
    print("=" * 60)

    # Build decks
    print("\nBuilding tribal decks...")
    kithkin_deck = build_kithkin_deck()
    merfolk_deck = build_merfolk_deck()
    goblin_deck = build_goblin_deck()
    elf_deck = build_elf_deck()

    print(f"Kithkin deck: {len(kithkin_deck)} cards")
    print(f"Merfolk deck: {len(merfolk_deck)} cards")
    print(f"Goblin deck: {len(goblin_deck)} cards")
    print(f"Elf deck: {len(elf_deck)} cards")

    # Create AIs with different strategies
    aggro_ai = AIEngine(strategy=AggroStrategy(), difficulty='hard')
    control_ai = AIEngine(strategy=ControlStrategy(), difficulty='hard')
    midrange_ai = AIEngine(strategy=MidrangeStrategy(), difficulty='hard')

    # Try Ultra AI (falls back to heuristics if no LLM)
    try:
        ultra_ai = AIEngine.create_ultra_bot()
        print("\nUsing Ultra AI with LLM support")
    except Exception as e:
        print(f"\nUltra AI unavailable ({e}), using Hard Midrange instead")
        ultra_ai = AIEngine(strategy=MidrangeStrategy(), difficulty='hard')

    # Game 1: Kithkin vs Merfolk (Aggro vs Control)
    print("\n" + "=" * 60)
    print("GAME 1: Kithkin (Aggro) vs Merfolk (Control)")
    print("=" * 60)
    winner1 = run_game(kithkin_deck, merfolk_deck, aggro_ai, control_ai, max_turns=20, verbose=True)

    # Game 2: Goblin vs Elf (Aggro vs Midrange)
    print("\n" + "=" * 60)
    print("GAME 2: Goblin (Aggro) vs Elf (Midrange)")
    print("=" * 60)
    winner2 = run_game(goblin_deck, elf_deck, aggro_ai, midrange_ai, max_turns=20, verbose=True)

    # Game 3: Elf vs Kithkin (Ultra vs Hard)
    print("\n" + "=" * 60)
    print("GAME 3: Elf (Ultra) vs Kithkin (Hard)")
    print("=" * 60)
    winner3 = run_game(elf_deck, kithkin_deck, ultra_ai, aggro_ai, max_turns=20, verbose=True)

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Game 1 (Kithkin vs Merfolk): {winner1}")
    print(f"Game 2 (Goblin vs Elf): {winner2}")
    print(f"Game 3 (Elf vs Kithkin): {winner3}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
