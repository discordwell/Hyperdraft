"""
Hearthstone AI Adapter

Adapts the existing AIEngine to work with Hearthstone's turn-based gameplay.
Translates between Hearthstone game state and AI decision-making.
"""
import random
from typing import Optional, TYPE_CHECKING

from .engine import AIEngine
from .evaluator import BoardEvaluator

if TYPE_CHECKING:
    from src.engine.types import GameState, Event, GameObject


class HearthstoneAIAdapter:
    """
    Adapter that lets AIEngine play Hearthstone.

    Handles turn execution for AI players in Hearthstone mode:
    1. Play cards from hand (following mana curve)
    2. Use hero power if beneficial
    3. Attack with minions (face vs trade decisions)
    4. End turn
    """

    def __init__(self, ai_engine: Optional[AIEngine] = None, difficulty: str = "medium"):
        """
        Initialize the adapter.

        Args:
            ai_engine: Existing AIEngine instance (or creates new one)
            difficulty: AI difficulty level
        """
        self.ai_engine = ai_engine or AIEngine(difficulty=difficulty)
        self.evaluator = None  # Created per-turn with current state
        self.difficulty = difficulty

    async def take_turn(self, player_id: str, game_state: 'GameState', game) -> list['Event']:
        """
        Execute a full Hearthstone turn for the AI.

        Args:
            player_id: The AI player's ID
            game_state: Current game state
            game: The Game instance (for actions)

        Returns:
            List of events generated during the turn
        """
        # Create evaluator for this turn
        if not self.evaluator:
            self.evaluator = BoardEvaluator(game_state)

        events = []

        # Play cards phase (safety limit prevents infinite loops)
        max_plays = 15
        for _ in range(max_plays):
            if not self._should_continue_playing(game_state, player_id):
                break
            card_action = self._choose_card_to_play(game_state, player_id, game)
            if card_action:
                play_events = await self._execute_card_play(card_action, game_state, game)
                events.extend(play_events)
            else:
                break

        # Hero power phase
        if self._should_use_hero_power(game_state, player_id):
            power_events = await self._use_hero_power(player_id, game_state, game)
            events.extend(power_events)

        # Attack phase
        attack_events = await self._execute_attacks(player_id, game_state, game)
        events.extend(attack_events)

        return events

    def _should_continue_playing(self, state: 'GameState', player_id: str) -> bool:
        """Check if AI should try to play more cards."""
        player = state.players.get(player_id)
        if not player:
            return False

        # Reserve 2 mana for hero power if not yet used
        reserved = 2 if not player.hero_power_used and player.mana_crystals >= 2 else 0
        available_for_cards = player.mana_crystals_available - reserved

        # No mana left for cards
        if available_for_cards <= 0:
            return False

        # Hand is empty
        hand_zone = state.zones.get(f'hand_{player_id}')
        if not hand_zone or not hand_zone.objects:
            return False

        return True

    def _choose_card_to_play(self, state: 'GameState', player_id: str, game) -> Optional[dict]:
        """
        Choose which card to play from hand.

        Returns dict with: {'card_id': str, 'targets': list}
        """
        player = state.players.get(player_id)
        if not player:
            return None

        hand_zone = state.zones.get(f'hand_{player_id}')
        if not hand_zone:
            return None

        playable_cards = []

        # Reserve 2 mana for hero power if not yet used
        reserved = 2 if not player.hero_power_used and player.mana_crystals >= 2 else 0
        available_for_cards = player.mana_crystals_available - reserved

        # Check board limit for minions
        from src.engine.types import CardType
        board_full = False
        if state.game_mode == "hearthstone":
            battlefield = state.zones.get('battlefield')
            if battlefield:
                minion_count = sum(
                    1 for oid in battlefield.objects
                    if oid in state.objects
                    and state.objects[oid].controller == player_id
                    and CardType.MINION in state.objects[oid].characteristics.types
                )
                board_full = minion_count >= 7

        for card_id in hand_zone.objects:
            card = state.objects.get(card_id)
            if not card:
                continue

            # Skip minions if board is full
            if board_full and CardType.MINION in card.characteristics.types:
                continue

            # Check mana cost (accounting for hero power reservation)
            cost = self._get_mana_cost(card)
            if cost > available_for_cards:
                continue

            playable_cards.append({
                'card_id': card_id,
                'card': card,
                'cost': cost,
                'score': self._score_card_play(card, state, player_id)
            })

        if not playable_cards:
            return None

        # Sort by score (higher is better)
        playable_cards.sort(key=lambda x: x['score'], reverse=True)

        # Add some randomness based on difficulty
        if self.difficulty == 'easy':
            # 40% chance to pick random card
            if random.random() < 0.4:
                chosen = random.choice(playable_cards)
            else:
                chosen = playable_cards[0]
        elif self.difficulty == 'medium':
            # Pick from top 50%
            top_half = max(1, len(playable_cards) // 2)
            chosen = random.choice(playable_cards[:top_half])
        else:
            # Hard/Ultra: Pick best
            chosen = playable_cards[0]

        return {
            'card_id': chosen['card_id'],
            'card': chosen['card'],
            'targets': []  # TODO: Target selection
        }

    def _get_mana_cost(self, card: 'GameObject') -> int:
        """Extract mana cost from card."""
        if not card.characteristics or not card.characteristics.mana_cost:
            return 0

        # Parse mana cost like "{3}" or "{2}{R}"
        cost_str = card.characteristics.mana_cost
        total = 0

        # Simple parser: extract numbers from {}
        import re
        numbers = re.findall(r'\{(\d+)\}', cost_str)
        for num in numbers:
            total += int(num)

        return total

    def _score_card_play(self, card: 'GameObject', state: 'GameState', player_id: str) -> float:
        """
        Score how good it is to play this card right now.

        Higher score = better play.
        """
        score = 0.0

        from src.engine.types import CardType

        # Base score: mana efficiency (play higher cost cards)
        cost = self._get_mana_cost(card)
        score += cost * 10

        # Minions are generally good
        if CardType.MINION in card.characteristics.types:
            power = card.characteristics.power or 0
            toughness = card.characteristics.toughness or 0
            score += (power + toughness) * 5

            # Charge/Haste is valuable (immediate impact)
            if 'charge' in card.characteristics.keywords or 'haste' in card.characteristics.keywords:
                score += 20

            # Taunt is defensive (good for control)
            if 'taunt' in card.characteristics.keywords:
                score += 10

        # Spells are situational
        if CardType.SPELL in card.characteristics.types:
            # Prefer spells when we need to answer threats
            enemy_minions = self._count_enemy_minions(state, player_id)
            if enemy_minions > 2:
                score += 15

        return score

    def _count_enemy_minions(self, state: 'GameState', player_id: str) -> int:
        """Count how many minions opponents control."""
        from src.engine.types import CardType
        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return 0

        count = 0
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.controller != player_id:
                if CardType.MINION in obj.characteristics.types:
                    count += 1

        return count

    async def _execute_card_play(self, card_action: dict, state: 'GameState', game) -> list['Event']:
        """Play the chosen card."""
        from src.engine.types import Event, EventType

        card_id = card_action['card_id']
        card = card_action['card']

        # Move card to battlefield or resolve spell
        events = []

        # Deduct mana
        player_id = card.owner
        player = state.players.get(player_id)
        if player:
            cost = self._get_mana_cost(card)
            player.mana_crystals_available -= cost

        # Cast the card
        from src.engine.types import CardType

        from src.engine.types import ZoneType

        if CardType.MINION in card.characteristics.types:
            # Check board limit (7 minions max in Hearthstone)
            if state.game_mode == "hearthstone":
                battlefield = state.zones.get('battlefield')
                if battlefield:
                    minion_count = sum(
                        1 for oid in battlefield.objects
                        if oid in state.objects
                        and state.objects[oid].controller == player_id
                        and CardType.MINION in state.objects[oid].characteristics.types
                    )
                    if minion_count >= 7:
                        # Refund mana and skip
                        player.mana_crystals_available += cost
                        return events

            # Play minion to battlefield via ZONE_CHANGE event (triggers ETB)
            zone_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': card_id,
                    'from_zone': f'hand_{player_id}',
                    'from_zone_type': ZoneType.HAND,
                    'to_zone': 'battlefield',
                    'to_zone_type': ZoneType.BATTLEFIELD
                },
                source=card_id
            )
            if game.pipeline:
                game.pipeline.emit(zone_event)
            events.append(zone_event)

        elif CardType.SPELL in card.characteristics.types:
            # Cast spell - emit zone change to graveyard (triggers spell effects via interceptors)
            zone_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': card_id,
                    'from_zone': f'hand_{player_id}',
                    'from_zone_type': ZoneType.HAND,
                    'to_zone': f'graveyard_{player_id}',
                    'to_zone_type': ZoneType.GRAVEYARD
                },
                source=card_id
            )
            if game.pipeline:
                game.pipeline.emit(zone_event)
            events.append(zone_event)

        return events

    def _should_use_hero_power(self, state: 'GameState', player_id: str) -> bool:
        """Check if AI should use hero power this turn."""
        player = state.players.get(player_id)
        if not player:
            return False

        # Already used
        if player.hero_power_used:
            return False

        # Not enough mana (hero powers cost 2)
        if player.mana_crystals_available < 2:
            return False

        # Use hero power if we have leftover mana
        # (Better than wasting mana)
        return True

    async def _use_hero_power(self, player_id: str, state: 'GameState', game) -> list['Event']:
        """Activate hero power."""
        from src.engine.types import Event, EventType, EventStatus

        player = state.players.get(player_id)
        if not player or not player.hero_power_id:
            return []

        events = []

        # Emit hero power activation event
        power_event = Event(
            type=EventType.HERO_POWER_ACTIVATE,
            payload={'hero_power_id': player.hero_power_id, 'player': player_id},
            source=player.hero_power_id
        )
        if game.pipeline:
            processed_events = game.pipeline.emit(power_event)

            # Only deduct mana if event wasn't prevented
            if any(e.status == EventStatus.PREVENTED for e in processed_events):
                return events

            events.extend(processed_events)
        else:
            events.append(power_event)

        # Deduct mana after successful activation
        player.mana_crystals_available -= 2

        return events

    async def _execute_attacks(self, player_id: str, state: 'GameState', game) -> list['Event']:
        """
        Execute attack phase.

        For each available attacker:
        1. Check if can attack (not frozen, attacks_this_turn < max)
        2. Choose target (face vs trade)
        3. Execute attack
        """
        events = []

        attackers = self._get_available_attackers(state, player_id)

        for attacker_id in attackers:
            target_id = self._choose_attack_target(attacker_id, state, player_id)

            if target_id:
                attack_events = await self._execute_attack(attacker_id, target_id, game)
                events.extend(attack_events)

        return events

    def _get_available_attackers(self, state: 'GameState', player_id: str) -> list[str]:
        """Find all minions that can attack."""
        from src.engine.types import CardType

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []

        attackers = []

        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller != player_id:
                continue

            # Must be a minion
            if CardType.MINION not in obj.characteristics.types:
                continue

            # Can't be frozen
            if obj.state.frozen:
                continue

            # Check if already attacked (or has charge/haste)
            has_charge = 'charge' in obj.characteristics.keywords or 'haste' in obj.characteristics.keywords

            # Summoning sickness check
            if obj.state.summoning_sickness and not has_charge:
                continue

            # Check attack count
            if obj.state.attacks_this_turn >= 1:
                # Windfury allows 2 attacks
                if 'windfury' not in obj.characteristics.keywords:
                    continue
                if obj.state.attacks_this_turn >= 2:
                    continue

            attackers.append(obj_id)

        return attackers

    def _choose_attack_target(self, attacker_id: str, state: 'GameState', player_id: str) -> Optional[str]:
        """
        Choose what to attack with this minion.

        Returns target ID (minion or enemy hero).
        """
        from src.engine.types import CardType

        attacker = state.objects.get(attacker_id)
        if not attacker:
            return None

        # Find enemy player
        enemy_id = None
        for pid, player in state.players.items():
            if pid != player_id:
                enemy_id = pid
                break

        if not enemy_id:
            return None

        enemy_player = state.players[enemy_id]

        # Check for Taunt minions (MUST attack them)
        taunt_minions = self._get_enemy_taunt_minions(state, player_id)
        if taunt_minions:
            # Must attack a taunt minion
            # Pick the one we can kill without dying
            for taunt_id in taunt_minions:
                if self._is_favorable_trade(attacker_id, taunt_id, state):
                    return taunt_id
            # No favorable trades, just hit the first one
            return taunt_minions[0]

        # No taunt requirement - decide between face and trades
        enemy_minions = self._get_enemy_minions(state, player_id)

        # Strategy decision
        strategy = self.ai_engine.strategy.name if hasattr(self.ai_engine.strategy, 'name') else 'midrange'

        # Aggro: Prefer face
        if strategy == 'aggro' or self.difficulty == 'easy':
            # Check if we can lethal
            attacker_power = attacker.characteristics.power or 0
            if enemy_player.life <= attacker_power:
                return enemy_player.hero_id  # Kill shot!

            # Otherwise, mostly go face
            if random.random() < 0.8:
                return enemy_player.hero_id

        # Control/Midrange: Look for good trades
        for enemy_id in enemy_minions:
            if self._is_favorable_trade(attacker_id, enemy_id, state):
                return enemy_id

        # No good trades, go face
        return enemy_player.hero_id

    def _get_enemy_taunt_minions(self, state: 'GameState', player_id: str) -> list[str]:
        """Find all enemy minions with Taunt."""
        from src.engine.types import CardType

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []

        taunt_minions = []

        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller == player_id:
                continue

            if CardType.MINION in obj.characteristics.types:
                # Stealthed taunts don't enforce taunt (can't be targeted)
                if 'taunt' in obj.characteristics.keywords and not obj.state.stealth:
                    taunt_minions.append(obj_id)

        return taunt_minions

    def _get_enemy_minions(self, state: 'GameState', player_id: str) -> list[str]:
        """Get all enemy minions."""
        from src.engine.types import CardType

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []

        enemy_minions = []

        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller == player_id:
                continue

            if CardType.MINION in obj.characteristics.types:
                enemy_minions.append(obj_id)

        return enemy_minions

    def _is_favorable_trade(self, attacker_id: str, defender_id: str, state: 'GameState') -> bool:
        """
        Check if attacking defender is a favorable trade.

        Favorable = We kill it and survive, or both die but ours is cheaper.
        """
        from src.engine.queries import get_power, get_toughness

        attacker = state.objects.get(attacker_id)
        defender = state.objects.get(defender_id)

        if not attacker or not defender:
            return False

        attacker_power = get_power(attacker, state)
        attacker_health = get_toughness(attacker, state) - attacker.state.damage

        defender_power = get_power(defender, state)
        defender_health = get_toughness(defender, state) - defender.state.damage

        # We kill it
        we_kill = attacker_power >= defender_health

        # We survive
        we_survive = defender_power < attacker_health

        # Favorable if we kill and survive
        if we_kill and we_survive:
            return True

        # Or if both die but defender is bigger (good trade)
        if we_kill and not we_survive:
            defender_stats = defender_power + defender_health
            attacker_stats = attacker_power + attacker_health
            return defender_stats >= attacker_stats

        return False

    async def _execute_attack(self, attacker_id: str, target_id: str, game) -> list['Event']:
        """Execute an attack."""
        if hasattr(game, 'combat_manager') and hasattr(game.combat_manager, 'declare_attack'):
            return await game.combat_manager.declare_attack(attacker_id, target_id)
        return []
