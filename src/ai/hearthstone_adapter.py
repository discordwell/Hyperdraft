"""
Hearthstone AI Adapter

Adapts the existing AIEngine to work with Hearthstone's turn-based gameplay.
Translates between Hearthstone game state and AI decision-making.
"""
import random
from typing import Optional, TYPE_CHECKING

from .engine import AIEngine
from .evaluator import BoardEvaluator
from src.engine.types import ZoneType

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
        # Per-player difficulty overrides (for bot-vs-bot with different difficulties)
        self.player_difficulties: dict[str, str] = {}

    def _get_difficulty(self, player_id: str = None) -> str:
        """Get difficulty for a specific player, falling back to default."""
        if player_id and player_id in self.player_difficulties:
            return self.player_difficulties[player_id]
        return self.difficulty

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
                # Check SBAs after each card play (battlecries may kill minions)
                if hasattr(game, 'turn_manager') and hasattr(game.turn_manager, '_check_state_based_actions'):
                    await game.turn_manager._check_state_based_actions()
                # Stop immediately if someone died mid-turn
                if game.is_game_over():
                    return events
            else:
                break

        # Hero power phase (use leftover mana for hero power)
        if self._should_use_hero_power(game_state, player_id):
            power_events = await self._use_hero_power(player_id, game_state, game)
            events.extend(power_events)
            # Check SBAs after hero power (damage may kill hero/minions)
            if hasattr(game, 'turn_manager') and hasattr(game.turn_manager, '_check_state_based_actions'):
                await game.turn_manager._check_state_based_actions()
            if game.is_game_over():
                return events

            # After hero power, try to play more cards with remaining mana
            for _ in range(max_plays):
                if not self._should_continue_playing(game_state, player_id):
                    break
                card_action = self._choose_card_to_play(game_state, player_id, game)
                if card_action:
                    play_events = await self._execute_card_play(card_action, game_state, game)
                    events.extend(play_events)
                    # Check SBAs after each card play
                    if hasattr(game, 'turn_manager') and hasattr(game.turn_manager, '_check_state_based_actions'):
                        await game.turn_manager._check_state_based_actions()
                    if game.is_game_over():
                        return events
                else:
                    break

        # Attack phase
        attack_events = await self._execute_attacks(player_id, game_state, game)
        events.extend(attack_events)

        return events

    def _should_continue_playing(self, state: 'GameState', player_id: str) -> bool:
        """Check if AI should try to play more cards."""
        player = state.players.get(player_id)
        if not player:
            return False

        # No mana left (but allow 0-cost cards like Wisp and Backstab)
        if player.mana_crystals_available < 0:
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

        available_for_cards = player.mana_crystals_available

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

            # Skip targeted spells with no valid targets
            if CardType.SPELL in card.characteristics.types:
                card_def = card.card_def
                if card_def and getattr(card_def, 'requires_target', False):
                    targets = self._choose_spell_targets(card, state, player_id)
                    if not targets:
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
        diff = self._get_difficulty(player_id)
        if diff == 'easy':
            # 40% chance to pick random card
            if random.random() < 0.4:
                chosen = random.choice(playable_cards)
            else:
                chosen = playable_cards[0]
        elif diff == 'medium':
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

        # Weapons provide repeated value (attack over multiple turns)
        if CardType.WEAPON in card.characteristics.types:
            weapon_attack = card.characteristics.power or 0
            weapon_durability = card.characteristics.toughness or 0
            score += weapon_attack * weapon_durability * 5
            # Don't play weapon if we already have one equipped
            player = state.players.get(player_id)
            if player and player.weapon_durability > 0:
                score -= 30  # Deprioritize replacing existing weapon

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
            # Emit SPELL_CAST event (triggers "whenever you cast a spell" effects)
            spell_cast_event = Event(
                type=EventType.SPELL_CAST,
                payload={'spell_id': card_id, 'caster': player_id},
                source=card_id
            )
            if game.pipeline:
                game.pipeline.emit(spell_cast_event)
            events.append(spell_cast_event)

            # Execute spell effect BEFORE moving to graveyard
            card_def = card.card_def
            if card_def and hasattr(card_def, 'spell_effect') and card_def.spell_effect:
                targets = self._choose_spell_targets(card, state, player_id)
                effect_events = card_def.spell_effect(card, state, targets)
                for ev in effect_events:
                    if game.pipeline:
                        game.pipeline.emit(ev)
                    events.append(ev)

            # Move spell to graveyard AFTER effect resolves
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

        elif CardType.WEAPON in card.characteristics.types:
            # Play weapon to battlefield (triggers equip interceptor via ZONE_CHANGE)
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

        return events

    def _choose_spell_targets(self, card: 'GameObject', state: 'GameState', player_id: str) -> list[list[str]]:
        """Choose targets for a spell. Returns list of target lists."""
        from src.engine.types import CardType

        card_def = card.card_def
        if not card_def or not card_def.requires_target:
            return []

        # Find an enemy target (prefer minions with highest health, fall back to hero)
        enemy_minions = []
        enemy_hero_id = None

        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller != player_id:
                    if CardType.MINION in obj.characteristics.types and not obj.state.stealth:
                        enemy_minions.append(obj_id)

        for pid, player in state.players.items():
            if pid != player_id and player.hero_id:
                enemy_hero_id = player.hero_id

        # For damage spells, prefer enemy hero; for transform/control, prefer minions
        spell_name = card_def.name.lower() if card_def.name else ''
        if 'backstab' in spell_name:
            # Backstab only works on undamaged minions
            undamaged = [m for m in enemy_minions if state.objects[m].state.damage == 0]
            if undamaged:
                from src.engine.queries import get_toughness
                best = max(undamaged, key=lambda m: get_toughness(state.objects[m], state))
                return [[best]]
            return []  # No valid targets, don't waste the card
        elif 'polymorph' in spell_name or 'mind control' in spell_name:
            # These only target minions, not heroes — pick highest-threat (power)
            if enemy_minions:
                from src.engine.queries import get_power as _gp
                best = max(enemy_minions, key=lambda m: _gp(state.objects[m], state))
                return [[best]]
            return []  # No valid minion targets, don't waste the card
        else:
            # Damage spells - target enemy hero
            if enemy_hero_id:
                return [[enemy_hero_id]]

        # Fallback
        if enemy_minions:
            return [[enemy_minions[0]]]
        if enemy_hero_id:
            return [[enemy_hero_id]]
        return []

    def _should_use_hero_power(self, state: 'GameState', player_id: str) -> bool:
        """Check if AI should use hero power this turn."""
        player = state.players.get(player_id)
        if not player:
            return False

        # Already used
        if player.hero_power_used:
            return False

        # Not enough mana — read actual cost from hero power object
        hp_cost = 2
        if player.hero_power_id:
            hp_obj = state.objects.get(player.hero_power_id)
            if hp_obj:
                hp_cost = self._get_mana_cost(hp_obj) or 2
        if player.mana_crystals_available < hp_cost:
            return False

        # Check if hero power creates tokens and board is full
        # (Shaman Totemic Call, Paladin Reinforce can't be used with 7 minions)
        if player.hero_power_id:
            from src.engine.types import CardType
            hero_power_obj = state.objects.get(player.hero_power_id)
            if hero_power_obj and hero_power_obj.card_def:
                hp_text = (hero_power_obj.card_def.text or '').lower()
                if 'summon' in hp_text:
                    battlefield = state.zones.get('battlefield')
                    if battlefield:
                        minion_count = sum(
                            1 for oid in battlefield.objects
                            if oid in state.objects
                            and state.objects[oid].controller == player_id
                            and CardType.MINION in state.objects[oid].characteristics.types
                        )
                        if minion_count >= 7:
                            return False

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

            # Only deduct mana if the hero power event itself wasn't prevented
            if power_event.status == EventStatus.PREVENTED:
                return events

            events.extend(processed_events)
        else:
            events.append(power_event)

        # Deduct mana after successful activation (use actual cost)
        hp_cost = 2
        hp_obj = state.objects.get(player.hero_power_id)
        if hp_obj:
            hp_cost = self._get_mana_cost(hp_obj) or 2
        player.mana_crystals_available -= hp_cost

        return events

    async def _execute_attacks(self, player_id: str, state: 'GameState', game) -> list['Event']:
        """
        Execute attack phase.

        For each available attacker:
        1. Check if can attack (not frozen, attacks_this_turn < max)
        2. Choose target (face vs trade)
        3. Execute attack
        4. Check state-based actions (remove dead minions)

        Re-checks for available attackers after each pass to handle
        Windfury (2 attacks per turn) and other multi-attack effects.
        """
        events = []
        max_attack_rounds = 20  # Safety limit (7 minions x 2 windfury + hero = 15 max)

        for _ in range(max_attack_rounds):
            attackers = self._get_available_attackers(state, player_id)
            if not attackers:
                break

            made_attack = False
            for attacker_id in attackers:
                # Verify attacker is still on the battlefield
                attacker = state.objects.get(attacker_id)
                if not attacker or attacker.zone != ZoneType.BATTLEFIELD:
                    continue

                target_id = self._choose_attack_target(attacker_id, state, player_id)

                if target_id:
                    attack_events = await self._execute_attack(attacker_id, target_id, game)
                    events.extend(attack_events)
                    made_attack = True

                    # Check state-based actions after each attack (remove dead minions)
                    if hasattr(game, 'turn_manager') and hasattr(game.turn_manager, '_check_state_based_actions'):
                        await game.turn_manager._check_state_based_actions()
                    # Stop if someone died from combat damage
                    if game.is_game_over():
                        return events

            if not made_attack:
                break

        return events

    def _get_available_attackers(self, state: 'GameState', player_id: str) -> list[str]:
        """Find all minions and heroes that can attack."""
        from src.engine.types import CardType
        from src.engine.queries import get_power, has_ability

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []

        attackers = []

        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller != player_id:
                continue

            is_minion = CardType.MINION in obj.characteristics.types
            is_hero = CardType.HERO in obj.characteristics.types

            if not is_minion and not is_hero:
                continue

            # 0-attack minions can't attack
            if is_minion and get_power(obj, state) <= 0:
                continue

            # Heroes need a weapon to attack
            if is_hero:
                player = state.players.get(player_id)
                if not player or player.weapon_attack <= 0:
                    continue

            # Can't be frozen
            if obj.state.frozen:
                continue

            # Check if already attacked (or has charge/haste)
            has_charge = has_ability(obj, 'charge', state) or has_ability(obj, 'haste', state)

            # Summoning sickness check (only for minions)
            if is_minion and obj.state.summoning_sickness and not has_charge:
                has_rush = has_ability(obj, 'rush', state)
                if not has_rush:
                    continue

            # Check attack count
            max_attacks = 2 if has_ability(obj, 'windfury', state) else 1
            if obj.state.attacks_this_turn >= max_attacks:
                continue

            attackers.append(obj_id)

        return attackers

    def _choose_attack_target(self, attacker_id: str, state: 'GameState', player_id: str) -> Optional[str]:
        """
        Choose what to attack with this minion/hero.

        Returns target ID (minion or enemy hero).
        """
        from src.engine.types import CardType
        from src.engine.queries import get_power, has_ability

        attacker = state.objects.get(attacker_id)
        if not attacker:
            return None

        # Rush minions with summoning sickness can only attack minions
        is_rush_restricted = (
            CardType.MINION in attacker.characteristics.types and
            attacker.state.summoning_sickness and
            has_ability(attacker, 'rush', state) and
            not has_ability(attacker, 'charge', state)
        )

        # Find enemy player
        enemy_pid = None
        for pid, player in state.players.items():
            if pid != player_id:
                enemy_pid = pid
                break

        if not enemy_pid:
            return None

        enemy_player = state.players[enemy_pid]

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

        # Rush-restricted minions can only hit minions
        if is_rush_restricted:
            if enemy_minions:
                for minion_id in enemy_minions:
                    if self._is_favorable_trade(attacker_id, minion_id, state):
                        return minion_id
                return enemy_minions[0]
            return None  # No valid targets for Rush minion

        # Strategy decision
        strategy = self.ai_engine.strategy.name if hasattr(self.ai_engine.strategy, 'name') else 'midrange'

        # Aggro: Prefer face
        if strategy == 'aggro' or self._get_difficulty(player_id) == 'easy':
            # Check if we can lethal (account for armor)
            attacker_power = get_power(attacker, state)
            if CardType.HERO in attacker.characteristics.types:
                player = state.players.get(player_id)
                if player:
                    attacker_power = player.weapon_attack
            effective_hp = enemy_player.life + enemy_player.armor
            if effective_hp <= attacker_power:
                return enemy_player.hero_id  # Kill shot!

            # Otherwise, mostly go face
            if random.random() < 0.8:
                return enemy_player.hero_id

        # Control/Midrange: Look for good trades
        for minion_id in enemy_minions:
            if self._is_favorable_trade(attacker_id, minion_id, state):
                return minion_id

        # No good trades, go face
        return enemy_player.hero_id

    def _get_enemy_taunt_minions(self, state: 'GameState', player_id: str) -> list[str]:
        """Find all enemy minions with Taunt."""
        from src.engine.types import CardType
        from src.engine.queries import has_ability

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
                if has_ability(obj, 'taunt', state) and not obj.state.stealth:
                    taunt_minions.append(obj_id)

        return taunt_minions

    def _get_enemy_minions(self, state: 'GameState', player_id: str) -> list[str]:
        """Get all targetable enemy minions (excludes stealthed)."""
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
                # Can't target stealthed minions
                if obj.state.stealth:
                    continue
                enemy_minions.append(obj_id)

        return enemy_minions

    def _is_favorable_trade(self, attacker_id: str, defender_id: str, state: 'GameState') -> bool:
        """
        Check if attacking defender is a favorable trade.

        Favorable = We kill it and survive, or both die but ours is cheaper.
        """
        from src.engine.types import CardType
        from src.engine.queries import get_power, get_toughness

        attacker = state.objects.get(attacker_id)
        defender = state.objects.get(defender_id)

        if not attacker or not defender:
            return False

        attacker_power = get_power(attacker, state)
        # Heroes attack with weapon, not base power
        if CardType.HERO in attacker.characteristics.types:
            player = state.players.get(attacker.controller)
            if player:
                attacker_power = player.weapon_attack
        # Hero effective HP is player.life + armor (not toughness - damage)
        if CardType.HERO in attacker.characteristics.types:
            player = state.players.get(attacker.controller)
            attacker_health = (player.life + player.armor) if player else 0
        else:
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
