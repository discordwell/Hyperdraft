"""
Hearthstone AI Adapter

Adapts the existing AIEngine to work with Hearthstone's turn-based gameplay.
Translates between Hearthstone game state and AI decision-making.

Supports difficulty levels (easy, medium, hard, ultra) with progressively
smarter board evaluation, lethal detection, synergy scoring, and targeting.
"""
import re
import random
from typing import Optional, TYPE_CHECKING

from .engine import AIEngine
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

    # Hearthstone-specific difficulty settings
    HS_DIFFICULTY_SETTINGS = {
        'easy': {
            'random_factor': 0.4,
            'mistake_chance': 0.25,
            'use_board_eval': False,
            'use_lethal_calc': False,
            'use_smart_targeting': False,
            'use_synergy_scoring': False,
            'use_smart_hero_power': False,
            'use_archetype_detect': False,
        },
        'medium': {
            'random_factor': 0.15,
            'mistake_chance': 0.10,
            'use_board_eval': True,
            'use_lethal_calc': False,
            'use_smart_targeting': False,
            'use_synergy_scoring': False,
            'use_smart_hero_power': False,
            'use_archetype_detect': False,
        },
        'hard': {
            'random_factor': 0.05,
            'mistake_chance': 0.02,
            'use_board_eval': True,
            'use_lethal_calc': True,
            'use_smart_targeting': True,
            'use_synergy_scoring': True,
            'use_smart_hero_power': True,
            'use_archetype_detect': False,
        },
        'ultra': {
            'random_factor': 0.0,
            'mistake_chance': 0.0,
            'use_board_eval': True,
            'use_lethal_calc': True,
            'use_smart_targeting': True,
            'use_synergy_scoring': True,
            'use_smart_hero_power': True,
            'use_archetype_detect': True,
        },
    }

    def __init__(self, ai_engine: Optional[AIEngine] = None, difficulty: str = "medium"):
        self.ai_engine = ai_engine or AIEngine(difficulty=difficulty)
        self.difficulty = difficulty
        # Per-player difficulty overrides (for bot-vs-bot with different difficulties)
        self.player_difficulties: dict[str, str] = {}
        # Cache for deck archetype detection (computed once per player per game)
        self._cached_archetype: dict[str, str] = {}

    def _get_difficulty(self, player_id: str = None) -> str:
        """Get difficulty for a specific player, falling back to default."""
        if player_id and player_id in self.player_difficulties:
            return self.player_difficulties[player_id]
        return self.difficulty

    def _get_hs_settings(self, player_id: str = None) -> dict:
        """Get HS difficulty settings for a player."""
        diff = self._get_difficulty(player_id)
        return self.HS_DIFFICULTY_SETTINGS.get(diff, self.HS_DIFFICULTY_SETTINGS['medium'])

    # ─── Turn Execution ─────────────────────────────────────────

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
        events = []
        settings = self._get_hs_settings(player_id)

        # Early hero power: draw effects (Life Tap) should fire before card plays
        if settings['use_smart_hero_power'] and self._should_use_hero_power_early(game_state, player_id):
            power_events = await self._use_hero_power(player_id, game_state, game)
            events.extend(power_events)
            if hasattr(game, 'turn_manager') and hasattr(game.turn_manager, '_check_state_based_actions'):
                await game.turn_manager._check_state_based_actions()
            if game.is_game_over():
                return events

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

    # ─── Card Play ───────────────────────────────────────────────

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

            # Check mana cost (accounting for hero power reservation and cost modifiers)
            cost = self._get_mana_cost(card, state, player_id)
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

        # Apply difficulty-based noise to scores
        settings = self._get_hs_settings(player_id)
        if settings['random_factor'] > 0:
            for item in playable_cards:
                item['score'] += random.uniform(0, settings['random_factor'] * 50)

        # Sort by score (higher is better)
        playable_cards.sort(key=lambda x: x['score'], reverse=True)

        # Mistake chance: pick a suboptimal card
        if len(playable_cards) >= 2 and random.random() < settings['mistake_chance']:
            chosen = random.choice(playable_cards[1:])
        else:
            chosen = playable_cards[0]

        return {
            'card_id': chosen['card_id'],
            'card': chosen['card'],
            'targets': []  # TODO: Target selection
        }

    def _score_card_play(self, card: 'GameObject', state: 'GameState', player_id: str) -> float:
        """
        Score how good it is to play this card right now.

        Higher score = better play. Enhanced with synergy scoring at hard+.
        """
        score = 0.0
        settings = self._get_hs_settings(player_id)

        from src.engine.types import CardType

        # Base score: mana efficiency (play higher cost cards)
        cost = self._get_mana_cost(card)
        score += cost * 10

        card_text = ''
        if card.card_def and card.card_def.text:
            card_text = card.card_def.text.lower()

        card_name = ''
        if card.card_def and card.card_def.name:
            card_name = card.card_def.name.lower()

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

            # ── Synergy scoring (hard+) ──
            if settings['use_synergy_scoring']:
                friendly_count = len(self._get_friendly_minions(state, player_id))

                # Battlecry buff cards need a board
                if 'give a friendly minion' in card_text or 'give a friendly' in card_text:
                    if friendly_count == 0:
                        score -= 20  # No targets for buff
                    else:
                        score += friendly_count * 5

                # Lord effects scale with board
                if 'your other minions' in card_text or 'your other' in card_text:
                    score += friendly_count * 8

                # Knife Juggler synergy
                if self._board_has_card(state, player_id, 'Knife Juggler'):
                    score += 10

        # Spells are situational
        if CardType.SPELL in card.characteristics.types:
            enemy_minions = self._count_enemy_minions(state, player_id)
            if enemy_minions > 2:
                score += 15

            # ── Synergy scoring (hard+) ──
            if settings['use_synergy_scoring']:
                # AOE efficiency
                if 'all enemy' in card_text or 'all minions' in card_text:
                    if enemy_minions >= 2:
                        score += enemy_minions * 10
                    else:
                        score -= 15  # Waste of AOE on <2 targets

                # The Coin: only play if enables an on-curve play
                if card_name == 'the coin' or cost == 0 and 'gain 1 mana' in card_text:
                    player = state.players.get(player_id)
                    if player:
                        boosted_mana = player.mana_crystals_available + 1
                        hand_zone = state.zones.get(f'hand_{player_id}')
                        has_on_curve = False
                        if hand_zone:
                            for cid in hand_zone.objects:
                                c = state.objects.get(cid)
                                if c and c != card and self._get_mana_cost(c) == boosted_mana:
                                    has_on_curve = True
                                    break
                        if not has_on_curve:
                            score -= 30  # Don't waste The Coin

        # Weapons provide repeated value (attack over multiple turns)
        if CardType.WEAPON in card.characteristics.types:
            weapon_attack = card.characteristics.power or 0
            weapon_durability = card.characteristics.toughness or 0
            score += weapon_attack * weapon_durability * 5
            # Don't play weapon if we already have one equipped
            player = state.players.get(player_id)
            if player and player.weapon_durability > 0:
                if settings['use_synergy_scoring']:
                    # Penalize by lost durability value
                    lost_value = player.weapon_attack * player.weapon_durability
                    score -= lost_value * 5
                else:
                    score -= 30  # Basic deprioritize

        # Board evaluation bonus (medium+)
        if settings['use_board_eval']:
            board_score = self._evaluate_board_state(player_id, state)
            # Losing board → prefer tempo plays (minions); winning → prefer value
            if board_score < -0.3:
                if CardType.MINION in card.characteristics.types:
                    score += 10  # Need board presence
                if 'taunt' in card.characteristics.keywords:
                    score += 15  # Need defense

        return score

    def _get_mana_cost(self, card: 'GameObject', state: 'GameState' = None, player_id: str = None) -> int:
        """Extract mana cost from card, applying cost modifiers."""
        if not card.characteristics or not card.characteristics.mana_cost:
            return 0

        # Parse mana cost like "{3}" or "{2}{R}"
        cost_str = card.characteristics.mana_cost
        total = 0

        # Simple parser: extract numbers from {}
        numbers = re.findall(r'\{(\d+)\}', cost_str)
        for num in numbers:
            total += int(num)

        # Apply cost modifiers from player
        if state and player_id:
            player = state.players.get(player_id)
            if player:
                from src.engine.types import CardType
                card_types = card.characteristics.types
                floor = 0
                for mod in player.cost_modifiers:
                    mod_type = mod.get('card_type')
                    if mod_type and mod_type in card_types:
                        total -= mod.get('amount', 0)
                        mod_floor = mod.get('floor', 0)
                        if mod_floor > floor:
                            floor = mod_floor
                total = max(floor, total)

        # Dynamic self-cost (Sea Giant, Mountain Giant, Molten Giant, etc.)
        if card.card_def and hasattr(card.card_def, 'dynamic_cost') and card.card_def.dynamic_cost:
            total = max(0, card.card_def.dynamic_cost(card, state))

        return max(0, total)

    async def _execute_card_play(self, card_action: dict, state: 'GameState', game) -> list['Event']:
        """Play the chosen card."""
        from src.engine.types import Event, EventType

        card_id = card_action['card_id']
        card = card_action['card']

        # Move card to battlefield or resolve spell
        events = []

        player_id = card.owner
        player = state.players.get(player_id)
        cost = self._get_mana_cost(card, state, player_id) if player else 0

        # Cast the card
        from src.engine.types import CardType

        from src.engine.types import ZoneType

        if CardType.MINION in card.characteristics.types:
            # Check board limit BEFORE deducting mana (7 minions max in Hearthstone)
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
                        return events

            # Deduct mana after board-full check
            if player:
                player.mana_crystals_available -= cost

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
            # Deduct mana
            if player:
                player.mana_crystals_available -= cost

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
            # Defer SBA checks so AOE damage resolves simultaneously
            card_def = card.card_def
            if card_def and hasattr(card_def, 'spell_effect') and card_def.spell_effect:
                targets_nested = self._choose_spell_targets(card, state, player_id)
                # Flatten nested target lists: [[id1], [id2]] -> [id1, id2]
                targets = [t for sublist in targets_nested for t in sublist]
                effect_events = card_def.spell_effect(card, state, targets)
                try:
                    if game.pipeline:
                        game.pipeline.sba_deferred = True
                    for ev in effect_events:
                        if game.pipeline:
                            game.pipeline.emit(ev)
                        events.append(ev)
                finally:
                    if game.pipeline:
                        game.pipeline.sba_deferred = False
                # Single SBA check after all spell damage resolves
                if hasattr(game, 'turn_manager') and hasattr(game.turn_manager, '_check_state_based_actions'):
                    await game.turn_manager._check_state_based_actions()

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
            # Deduct mana
            if player:
                player.mana_crystals_available -= cost

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

        # Track cards played this turn (for Combo, etc.) and consume cost modifiers
        if player:
            player.cards_played_this_turn += 1
            # Consume one-shot cost modifiers that apply to this card type
            new_modifiers = []
            for mod in player.cost_modifiers:
                if mod.get('uses_remaining') is not None:
                    mod_type = mod.get('card_type')
                    if mod_type and mod_type in card.characteristics.types:
                        mod['uses_remaining'] -= 1
                        if mod['uses_remaining'] <= 0:
                            continue  # Consumed, don't keep
                new_modifiers.append(mod)
            player.cost_modifiers = new_modifiers

        return events

    # ─── Board Evaluation ────────────────────────────────────────

    def _calculate_minion_value(self, minion: 'GameObject', state: 'GameState') -> float:
        """
        Calculate the board value of a minion, accounting for keywords.

        Used by board evaluation and trade decisions.
        """
        from src.engine.queries import get_power, get_toughness, has_ability

        power = get_power(minion, state)
        health = get_toughness(minion, state) - minion.state.damage
        value = float(power + health)

        # Keyword bonuses
        if has_ability(minion, 'taunt', state):
            value += 2
        if has_ability(minion, 'divine_shield', state) or minion.state.divine_shield:
            value += 2
        if has_ability(minion, 'charge', state) or has_ability(minion, 'haste', state):
            value += 1.5
        if has_ability(minion, 'windfury', state):
            value += power  # Double damage potential
        if minion.state.stealth or has_ability(minion, 'stealth', state):
            value += 1
        # Deathrattle
        keywords = minion.characteristics.keywords or set()
        if 'deathrattle' in keywords:
            value += 1
        elif minion.card_def and minion.card_def.text and 'deathrattle' in minion.card_def.text.lower():
            value += 1

        return value

    def _evaluate_board_state(self, player_id: str, state: 'GameState') -> float:
        """
        Evaluate the board from player_id's perspective.

        Weighted scoring:
        - Life (30%): effective HP comparison with urgency penalties
        - Board (40%): minion values via _calculate_minion_value
        - Cards (15%): hand size difference
        - Mana (10%): mana crystal difference, weighted less late game
        - Weapon (5%): weapon attack * durability

        Returns: -1.0 (losing) to 1.0 (winning)
        """
        from src.engine.types import CardType

        opponent_id = self._get_opponent_id(state, player_id)
        if not opponent_id:
            return 0.0

        player = state.players.get(player_id)
        opponent = state.players.get(opponent_id)
        if not player or not opponent:
            return 0.0

        # ── Life (30%) ──
        my_hp = player.life + player.armor
        opp_hp = opponent.life + opponent.armor
        total_hp = my_hp + opp_hp
        life_score = (my_hp - opp_hp) / total_hp if total_hp > 0 else 0.0
        if my_hp <= 5:
            life_score -= 0.3
        if opp_hp <= 5:
            life_score += 0.3
        life_score = max(-1.0, min(1.0, life_score))

        # ── Board (40%) ──
        my_board_value = 0.0
        opp_board_value = 0.0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if not obj or CardType.MINION not in obj.characteristics.types:
                    continue
                mv = self._calculate_minion_value(obj, state)
                if obj.controller == player_id:
                    my_board_value += mv
                elif obj.controller == opponent_id:
                    opp_board_value += mv
        total_board = my_board_value + opp_board_value
        board_score = (my_board_value - opp_board_value) / (total_board + 1)

        # ── Cards (15%) ──
        my_hand = state.zones.get(f'hand_{player_id}')
        opp_hand = state.zones.get(f'hand_{opponent_id}')
        my_hand_size = len(my_hand.objects) if my_hand else 0
        opp_hand_size = len(opp_hand.objects) if opp_hand else 0
        card_score = (my_hand_size - opp_hand_size) * 0.15
        if my_hand_size == 0 and opp_hand_size > 0:
            card_score -= 0.3
        elif opp_hand_size == 0 and my_hand_size > 0:
            card_score += 0.3
        card_score = max(-1.0, min(1.0, card_score))

        # ── Mana (10%) ──
        my_mana = player.mana_crystals
        opp_mana = opponent.mana_crystals
        total_mana = my_mana + opp_mana
        late_game_factor = 0.5 if total_mana >= 16 else 1.0
        mana_score = ((my_mana - opp_mana) / (total_mana + 1)) * late_game_factor if total_mana > 0 else 0.0

        # ── Weapon (5%) ──
        my_weapon = player.weapon_attack * player.weapon_durability if player.weapon_durability > 0 else 0
        opp_weapon = opponent.weapon_attack * opponent.weapon_durability if opponent.weapon_durability > 0 else 0
        weapon_max = max(my_weapon, opp_weapon, 1)
        weapon_score = (my_weapon - opp_weapon) / (weapon_max * 2)

        # ── Combined ──
        total = (
            life_score * 0.30 +
            board_score * 0.40 +
            card_score * 0.15 +
            mana_score * 0.10 +
            weapon_score * 0.05
        )
        return max(-1.0, min(1.0, total))

    # ─── Threat Scoring ──────────────────────────────────────────

    def _score_threat(self, minion: 'GameObject', state: 'GameState') -> float:
        """
        Score how threatening an enemy minion is. Higher = remove first.

        Base: power*2 + health (attack matters more for threats).
        Keyword multipliers and text-based bonuses applied on top.
        """
        from src.engine.queries import get_power, get_toughness, has_ability

        power = get_power(minion, state)
        health = get_toughness(minion, state) - minion.state.damage
        score = float(power * 2 + health)

        if has_ability(minion, 'charge', state) or has_ability(minion, 'haste', state):
            score *= 1.5
        if has_ability(minion, 'taunt', state):
            score *= 1.3
        if has_ability(minion, 'windfury', state):
            score *= 1.8
        if has_ability(minion, 'divine_shield', state) or minion.state.divine_shield:
            score *= 1.2

        # Text-based bonuses
        text = ''
        if minion.card_def and minion.card_def.text:
            text = minion.card_def.text.lower()
        if 'draw' in text:
            score += 3
        if 'summon' in text:
            score += 2
        if 'your other minions' in text or 'your other' in text:
            score += 3  # Lord effect

        return score

    # ─── Lethal Calculator ───────────────────────────────────────

    def _calculate_lethal(self, player_id: str, state: 'GameState') -> dict:
        """
        Calculate if the AI has lethal across all damage sources.

        Accounts for:
        1. Attack damage from available attackers
        2. Taunt wall (must kill taunts first, subtracts from attack damage)
        3. Burn spell damage from hand
        4. Hero power damage if mana remains

        Returns:
            dict with is_lethal, total_damage, attack_damage, burn_damage
        """
        from src.engine.types import CardType
        from src.engine.queries import get_power, get_toughness, has_ability

        result = {'is_lethal': False, 'total_damage': 0, 'attack_damage': 0, 'burn_damage': 0}

        opponent_id = self._get_opponent_id(state, player_id)
        if not opponent_id:
            return result

        opponent = state.players.get(opponent_id)
        player = state.players.get(player_id)
        if not opponent or not player:
            return result

        effective_hp = opponent.life + opponent.armor

        # 1. Sum attack damage from available attackers
        attack_damage = 0
        attackers = self._get_available_attackers(state, player_id)
        for att_id in attackers:
            att = state.objects.get(att_id)
            if not att:
                continue
            if CardType.HERO in att.characteristics.types:
                if player.weapon_attack > 0 and player.weapon_durability > 0:
                    attack_damage += player.weapon_attack
            else:
                power = get_power(att, state)
                if has_ability(att, 'windfury', state):
                    remaining_attacks = 2 - att.state.attacks_this_turn
                    attack_damage += power * max(remaining_attacks, 0)
                else:
                    attack_damage += power

        # 2. Subtract taunt wall
        taunt_wall = 0
        taunt_minions = self._get_enemy_taunt_minions(state, player_id)
        for t_id in taunt_minions:
            t = state.objects.get(t_id)
            if t:
                t_health = get_toughness(t, state) - t.state.damage
                if has_ability(t, 'divine_shield', state) or t.state.divine_shield:
                    t_health += t_health  # Need an extra full hit
                taunt_wall += t_health

        attack_through = max(0, attack_damage - taunt_wall)

        # 3. Burn spell damage from hand
        burn_damage = 0
        available_mana = player.mana_crystals_available
        burn_mana_spent = 0

        hand_zone = state.zones.get(f'hand_{player_id}')
        if hand_zone:
            burn_spells = []
            for card_id in hand_zone.objects:
                card = state.objects.get(card_id)
                if not card or CardType.SPELL not in card.characteristics.types:
                    continue
                card_def = card.card_def
                if not card_def:
                    continue
                text = (card_def.text or '').lower()
                dmg_match = re.search(r'deal\s+(\d+)\s+damage', text)
                if dmg_match:
                    dmg = int(dmg_match.group(1))
                    spell_cost = self._get_mana_cost(card)
                    # Skip AOE-only spells (can't target face)
                    can_go_face = 'all enemy' not in text and 'all minions' not in text
                    if can_go_face:
                        burn_spells.append((card_id, dmg, spell_cost))

            # Sort by damage efficiency
            burn_spells.sort(key=lambda x: x[1] / max(x[2], 1), reverse=True)
            for _, dmg, spell_cost in burn_spells:
                if burn_mana_spent + spell_cost <= available_mana:
                    burn_damage += dmg
                    burn_mana_spent += spell_cost

        # 4. Hero power damage
        hero_power_damage = 0
        if not player.hero_power_used and player.hero_power_id:
            hp_obj = state.objects.get(player.hero_power_id)
            if hp_obj:
                hp_cost = self._get_mana_cost(hp_obj) or 2
                if available_mana - burn_mana_spent >= hp_cost:
                    hp_text = (hp_obj.card_def.text or '').lower() if hp_obj.card_def else ''
                    hp_dmg = re.search(r'deal\s+(\d+)\s+damage', hp_text)
                    if hp_dmg:
                        hero_power_damage = int(hp_dmg.group(1))

        total_damage = attack_through + burn_damage + hero_power_damage
        result['is_lethal'] = total_damage >= effective_hp
        result['total_damage'] = total_damage
        result['attack_damage'] = attack_through
        result['burn_damage'] = burn_damage + hero_power_damage
        return result

    # ─── Spell Targeting ─────────────────────────────────────────

    def _choose_spell_targets(self, card: 'GameObject', state: 'GameState', player_id: str) -> list[list[str]]:
        """Choose targets for a spell. Returns list of target lists."""
        card_def = card.card_def
        if not card_def or not card_def.requires_target:
            return []

        settings = self._get_hs_settings(player_id)
        if settings['use_smart_targeting']:
            return self._smart_spell_targeting(card, state, player_id)
        return self._basic_spell_targeting(card, state, player_id)

    def _basic_spell_targeting(self, card: 'GameObject', state: 'GameState', player_id: str) -> list[list[str]]:
        """Original name-matching spell targeting for easy/medium."""
        from src.engine.types import CardType

        card_def = card.card_def

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
            undamaged = [m for m in enemy_minions
                         if m in state.objects and state.objects[m].state.damage == 0]
            if undamaged:
                from src.engine.queries import get_toughness
                best = max(undamaged, key=lambda m: get_toughness(state.objects[m], state))
                return [[best]]
            return []  # No valid targets, don't waste the card
        elif 'polymorph' in spell_name or 'mind control' in spell_name:
            # These only target minions, not heroes — pick highest-threat (power)
            valid_minions = [m for m in enemy_minions if m in state.objects]
            if valid_minions:
                from src.engine.queries import get_power as _gp
                best = max(valid_minions, key=lambda m: _gp(state.objects[m], state))
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

    def _smart_spell_targeting(self, card: 'GameObject', state: 'GameState', player_id: str) -> list[list[str]]:
        """Category-based spell targeting for hard/ultra."""
        from src.engine.types import CardType
        from src.engine.queries import get_toughness

        card_def = card.card_def
        text = (card_def.text or '').lower() if card_def else ''

        enemy_minions = self._get_enemy_minions(state, player_id)
        enemy_hero_id = None
        for pid, player in state.players.items():
            if pid != player_id and player.hero_id:
                enemy_hero_id = player.hero_id

        # Category: Transform / Take Control → always highest threat minion
        if 'transform' in text or 'take control' in text or 'destroy' in text:
            valid = [m for m in enemy_minions if m in state.objects]
            if valid:
                best = max(valid, key=lambda m: self._score_threat(state.objects[m], state))
                return [[best]]
            return []

        # Category: Undamaged condition → filter valid, pick highest health
        if 'undamaged' in text:
            undamaged = [m for m in enemy_minions
                         if m in state.objects and state.objects[m].state.damage == 0]
            if undamaged:
                best = max(undamaged, key=lambda m: get_toughness(state.objects[m], state))
                return [[best]]
            return []

        # Category: Burn / damage spell with target
        dmg_match = re.search(r'deal\s+(\d+)\s+damage', text)
        if dmg_match:
            # Check lethal: if burn to face wins the game, go face
            settings = self._get_hs_settings(player_id)
            if settings['use_lethal_calc']:
                lethal_info = self._calculate_lethal(player_id, state)
                if lethal_info['is_lethal'] and enemy_hero_id:
                    return [[enemy_hero_id]]

            # Otherwise, target highest threat minion
            valid = [m for m in enemy_minions if m in state.objects]
            if valid:
                best = max(valid, key=lambda m: self._score_threat(state.objects[m], state))
                return [[best]]
            # No minions, go face
            if enemy_hero_id:
                return [[enemy_hero_id]]
            return []

        # Category: Buff spell → target own minions
        if '+' in text or 'give' in text or 'gains' in text:
            friendly = self._get_friendly_minions(state, player_id)
            if friendly:
                # Pick highest value friendly to buff
                best = max(friendly, key=lambda m: self._calculate_minion_value(state.objects[m], state)
                           if m in state.objects else 0)
                return [[best]]
            return []

        # Fallback: target enemy hero for damage, minion otherwise
        if enemy_hero_id:
            return [[enemy_hero_id]]
        if enemy_minions:
            return [[enemy_minions[0]]]
        return []

    # ─── Hero Power ──────────────────────────────────────────────

    def _should_use_hero_power_early(self, state: 'GameState', player_id: str) -> bool:
        """Check if hero power should be used BEFORE card plays (draw effects)."""
        player = state.players.get(player_id)
        if not player or not player.hero_power_id:
            return False

        if player.hero_power_used:
            return False

        hp_obj = state.objects.get(player.hero_power_id)
        if not hp_obj or not hp_obj.card_def:
            return False

        hp_text = (hp_obj.card_def.text or '').lower()

        # Only early-use for draw effects (Life Tap)
        if 'draw' not in hp_text:
            return False

        hp_cost = self._get_mana_cost(hp_obj) or 2
        if player.mana_crystals_available < hp_cost:
            return False

        # Smart checks: skip if hand is nearly full or life is dangerously low
        hand = state.zones.get(f'hand_{player_id}')
        if hand and len(hand.objects) >= 8:
            return False
        if player.life <= 6:
            return False

        return True

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

        # Smart hero power logic (hard+)
        settings = self._get_hs_settings(player_id)
        if settings['use_smart_hero_power'] and player.hero_power_id:
            hp_obj = state.objects.get(player.hero_power_id)
            if hp_obj and hp_obj.card_def:
                hp_text = (hp_obj.card_def.text or '').lower()

                # Life Tap (draw): skip if hand >= 8 or life <= 6
                if 'draw' in hp_text:
                    hand = state.zones.get(f'hand_{player_id}')
                    if hand and len(hand.objects) >= 8:
                        return False
                    if player.life <= 6:
                        return False

                # Lesser Heal: skip if at full HP and no damaged friendlies
                elif 'restore' in hp_text or 'heal' in hp_text:
                    if player.life >= player.max_life:
                        friendly_minions = self._get_friendly_minions(state, player_id)
                        has_damaged = any(
                            state.objects[mid].state.damage > 0
                            for mid in friendly_minions
                            if mid in state.objects
                        )
                        if not has_damaged:
                            return False

                # Shapeshift (+1 Attack): use only if hero can attack
                elif '+1 attack' in hp_text or 'shapeshift' in hp_text:
                    # Skip if hero is frozen or already attacked
                    hero = state.objects.get(player.hero_id) if player.hero_id else None
                    if hero and hero.state.frozen:
                        return False

                # Summon with board >= 6: skip (leave room)
                elif 'summon' in hp_text:
                    from src.engine.types import CardType
                    battlefield = state.zones.get('battlefield')
                    if battlefield:
                        minion_count = sum(
                            1 for oid in battlefield.objects
                            if oid in state.objects
                            and state.objects[oid].controller == player_id
                            and CardType.MINION in state.objects[oid].characteristics.types
                        )
                        if minion_count >= 6:
                            return False

                # Armor Up: always use (no conditions)
                # Fireblast: always use (targeting handled by game system)

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
        player.hero_power_used = True

        return events

    # ─── Attack Phase ────────────────────────────────────────────

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

            # Heroes need a weapon with durability to attack
            if is_hero:
                player = state.players.get(player_id)
                if not player or player.weapon_attack <= 0 or player.weapon_durability <= 0:
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

        Enhanced with lethal detection, archetype-based face ratio,
        and threat-aware trade decisions at hard+ difficulty.

        Returns target ID (minion or enemy hero).
        """
        from src.engine.types import CardType
        from src.engine.queries import get_power, has_ability

        attacker = state.objects.get(attacker_id)
        if not attacker:
            return None

        settings = self._get_hs_settings(player_id)

        # Rush minions with summoning sickness can only attack minions
        is_rush_restricted = (
            CardType.MINION in attacker.characteristics.types and
            attacker.state.summoning_sickness and
            has_ability(attacker, 'rush', state) and
            not has_ability(attacker, 'charge', state)
        )

        # Find enemy player
        enemy_pid = self._get_opponent_id(state, player_id)
        if not enemy_pid:
            return None

        enemy_player = state.players.get(enemy_pid)
        if not enemy_player:
            return None

        # Check for Taunt minions (MUST attack them)
        taunt_minions = self._get_enemy_taunt_minions(state, player_id)
        if taunt_minions:
            # Pick the one we can kill without dying, preferring highest threat
            favorable_taunts = [
                (t_id, self._score_threat(state.objects[t_id], state))
                for t_id in taunt_minions
                if t_id in state.objects and self._is_favorable_trade(attacker_id, t_id, state, player_id)
            ]
            if favorable_taunts:
                favorable_taunts.sort(key=lambda x: x[1], reverse=True)
                return favorable_taunts[0][0]
            # No favorable trades, just hit the first one
            return taunt_minions[0]

        # No taunt requirement - decide between face and trades
        enemy_minions = self._get_enemy_minions(state, player_id)

        # Rush-restricted minions can only hit minions
        if is_rush_restricted:
            if enemy_minions:
                if settings['use_smart_targeting']:
                    # Pick highest threat favorable trade
                    favorable = [
                        (m, self._score_threat(state.objects[m], state))
                        for m in enemy_minions
                        if m in state.objects and self._is_favorable_trade(attacker_id, m, state, player_id)
                    ]
                    if favorable:
                        favorable.sort(key=lambda x: x[1], reverse=True)
                        return favorable[0][0]
                else:
                    for minion_id in enemy_minions:
                        if self._is_favorable_trade(attacker_id, minion_id, state, player_id):
                            return minion_id
                return enemy_minions[0]
            return None  # No valid targets for Rush minion

        # Lethal check (hard+): if we can kill, go face
        if settings['use_lethal_calc']:
            lethal_info = self._calculate_lethal(player_id, state)
            if lethal_info['is_lethal']:
                return enemy_player.hero_id

        # Single-attacker lethal check (all difficulties)
        attacker_power = get_power(attacker, state)
        if CardType.HERO in attacker.characteristics.types:
            player = state.players.get(player_id)
            if player:
                attacker_power = player.weapon_attack
        effective_hp = enemy_player.life + enemy_player.armor
        if effective_hp <= attacker_power:
            return enemy_player.hero_id  # Kill shot!

        # Determine face-vs-trade ratio based on archetype
        if settings['use_archetype_detect']:
            archetype = self._detect_deck_archetype(player_id, state)
        else:
            archetype = self.ai_engine.strategy.name if hasattr(self.ai_engine.strategy, 'name') else 'midrange'

        face_ratio = {'aggro': 0.8, 'control': 0.2, 'midrange': 0.5}.get(archetype, 0.5)

        # Easy AI is more face-oriented
        if self._get_difficulty(player_id) == 'easy':
            face_ratio = 0.8

        # Apply mistake: occasionally just go face regardless
        if random.random() < settings['mistake_chance'] and enemy_player.hero_id:
            return enemy_player.hero_id

        # Look for favorable trades, sorted by threat
        if settings['use_smart_targeting'] and enemy_minions:
            favorable = [
                (m, self._score_threat(state.objects[m], state))
                for m in enemy_minions
                if m in state.objects and self._is_favorable_trade(attacker_id, m, state, player_id)
            ]
            if favorable:
                favorable.sort(key=lambda x: x[1], reverse=True)
                # Trade or face based on archetype ratio
                if random.random() >= face_ratio:
                    return favorable[0][0]
        else:
            # Basic trade evaluation
            for minion_id in enemy_minions:
                if self._is_favorable_trade(attacker_id, minion_id, state, player_id):
                    # Aggro: mostly go face
                    if random.random() >= face_ratio:
                        return minion_id

        # No good trades or chose to go face
        return enemy_player.hero_id

    def _is_favorable_trade(self, attacker_id: str, defender_id: str,
                            state: 'GameState', player_id: str = None) -> bool:
        """
        Check if attacking defender is a favorable trade.

        Favorable = We kill it and survive, or both die but theirs is worth more.
        Enhanced at hard+ with overkill prevention, divine shield awareness,
        and value-based trade evaluation.
        """
        from src.engine.types import CardType
        from src.engine.queries import get_power, get_toughness, has_ability

        attacker = state.objects.get(attacker_id)
        defender = state.objects.get(defender_id)

        if not attacker or not defender:
            return False

        attacker_power = get_power(attacker, state)
        is_minion_attacker = CardType.MINION in attacker.characteristics.types

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

        # Divine shield awareness: can't kill in one hit
        defender_has_shield = (
            has_ability(defender, 'divine_shield', state) or defender.state.divine_shield
        )

        settings = self._get_hs_settings(player_id) if player_id else self.HS_DIFFICULTY_SETTINGS.get('medium')

        if defender_has_shield and settings.get('use_board_eval'):
            # With divine shield, first hit pops shield, no damage
            # Only favorable if we survive and can attack again (windfury)
            if has_ability(attacker, 'windfury', state) and attacker_power >= defender_health:
                # Windfury: first hit pops shield, second hit kills
                we_kill = True
                we_survive = defender_power < attacker_health
            else:
                we_kill = False  # Can't kill through shield in one attack
                we_survive = defender_power < attacker_health
                # Still might be worth popping shield with small minions
                if is_minion_attacker and attacker_power <= 2 and we_survive:
                    return True  # Small minion popping shield is fine
                return False
        else:
            we_kill = attacker_power >= defender_health
            we_survive = defender_power < attacker_health

        # We kill it and survive — generally favorable
        if we_kill and we_survive:
            # Overkill prevention (hard+)
            if settings.get('use_board_eval') and is_minion_attacker:
                if attacker_power >= 6 and defender_health <= 1:
                    return False  # Don't waste big minion on 1-health target
            return True

        # Both die — check if the trade is worth it
        if we_kill and not we_survive:
            if settings.get('use_board_eval') and is_minion_attacker:
                # Value trading: only if their minion is worth >= 1.2x ours
                att_value = self._calculate_minion_value(attacker, state)
                def_value = self._calculate_minion_value(defender, state)
                return def_value >= att_value * 1.2

            # Basic: stat comparison
            defender_stats = defender_power + defender_health
            attacker_stats = attacker_power + attacker_health
            return defender_stats >= attacker_stats

        return False

    async def _execute_attack(self, attacker_id: str, target_id: str, game) -> list['Event']:
        """Execute an attack."""
        if hasattr(game, 'combat_manager') and hasattr(game.combat_manager, 'declare_attack'):
            return await game.combat_manager.declare_attack(attacker_id, target_id)
        return []

    # ─── Deck Archetype Detection ────────────────────────────────

    def _detect_deck_archetype(self, player_id: str, state: 'GameState') -> str:
        """
        Detect deck archetype based on card costs and types.

        Heuristic:
        - Aggro: >60% cards cost <= 3 mana
        - Control: >30% spells
        - Default: midrange

        Cached per player per game.
        """
        if player_id in self._cached_archetype:
            return self._cached_archetype[player_id]

        from src.engine.types import CardType

        total_cards = 0
        cheap_cards = 0
        spell_count = 0

        for zone_name in [f'hand_{player_id}', f'library_{player_id}']:
            zone = state.zones.get(zone_name)
            if not zone:
                continue
            for card_id in zone.objects:
                card = state.objects.get(card_id)
                if not card:
                    continue
                total_cards += 1
                cost = self._get_mana_cost(card)
                if cost <= 3:
                    cheap_cards += 1
                if CardType.SPELL in card.characteristics.types:
                    spell_count += 1

        if total_cards == 0:
            archetype = 'midrange'
        elif cheap_cards / total_cards > 0.6:
            archetype = 'aggro'
        elif spell_count / total_cards > 0.3:
            archetype = 'control'
        else:
            archetype = 'midrange'

        self._cached_archetype[player_id] = archetype
        return archetype

    # ─── Helpers ─────────────────────────────────────────────────

    def _get_opponent_id(self, state: 'GameState', player_id: str) -> Optional[str]:
        """Get the opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return None

    def _board_has_card(self, state: 'GameState', player_id: str, card_name: str) -> bool:
        """Check if a card with the given name is on the board under player's control."""
        from src.engine.types import CardType

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return False

        name_lower = card_name.lower()
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.controller == player_id:
                if CardType.MINION in obj.characteristics.types:
                    obj_name = ''
                    if obj.card_def and obj.card_def.name:
                        obj_name = obj.card_def.name.lower()
                    if obj_name == name_lower:
                        return True
        return False

    def _get_friendly_minions(self, state: 'GameState', player_id: str) -> list[str]:
        """Get all friendly minion IDs on the battlefield."""
        from src.engine.types import CardType

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []

        result = []
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.controller == player_id and CardType.MINION in obj.characteristics.types:
                result.append(obj_id)
        return result

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
