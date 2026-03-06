"""
Pokemon TCG AI Adapter

Adapts the AI system to play Pokemon TCG using the engine's turn structure.
Translates board state into decisions for energy attachment, evolution,
trainer plays, retreat, and attack selection.

Supports difficulty levels (easy, medium, hard, ultra) with progressively
smarter energy planning, KO math, weakness awareness, and prize tracking.
"""
import random
from typing import Optional, TYPE_CHECKING

from src.engine.types import (
    GameState, Event, EventType, ZoneType, CardType, PokemonType,
)
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_combat import PokemonCombatManager
from src.engine.pokemon_status import can_attack, can_retreat

if TYPE_CHECKING:
    from src.engine.types import GameObject


# Pokemon type effectiveness chart: attacker_type -> list of weak defender types
WEAKNESS_CHART: dict[str, list[str]] = {
    PokemonType.FIRE.value: [PokemonType.GRASS.value, PokemonType.METAL.value],
    PokemonType.WATER.value: [PokemonType.FIRE.value],
    PokemonType.GRASS.value: [PokemonType.WATER.value],
    PokemonType.LIGHTNING.value: [PokemonType.WATER.value],
    PokemonType.PSYCHIC.value: [PokemonType.FIGHTING.value],
    PokemonType.FIGHTING.value: [PokemonType.LIGHTNING.value, PokemonType.DARKNESS.value],
    PokemonType.DARKNESS.value: [PokemonType.PSYCHIC.value],
    PokemonType.METAL.value: [PokemonType.PSYCHIC.value],
}


class PokemonAIAdapter:
    """
    Adapter that lets the AI play the Pokemon TCG.

    Handles turn execution for AI players in Pokemon mode:
    1. Use Abilities (if beneficial)
    2. Play Supporter (best available, 1 per turn)
    3. Play Basic Pokemon to bench (set up evolutions)
    4. Evolve Pokemon (upgrade when possible)
    5. Attach Energy (to Pokemon most likely to attack soon)
    6. Play Items (beneficial effects)
    7. Retreat if favorable (switch in better attacker)
    8. Attack (choose best attack by damage/effect)
    9. End turn
    """

    # Difficulty settings tuned for Pokemon TCG decision-making
    PKM_DIFFICULTY_SETTINGS = {
        'easy': {
            'random_factor': 0.4,
            'mistake_chance': 0.25,
            'use_board_eval': False,
            'use_weakness_aware': False,
            'use_ko_math': False,
            'use_prize_tracking': False,
            'use_energy_planning': False,
            'use_smart_retreat': False,
            'use_evolution_priority': False,
            'use_ability_eval': False,
        },
        'medium': {
            'random_factor': 0.15,
            'mistake_chance': 0.10,
            'use_board_eval': True,
            'use_weakness_aware': True,
            'use_ko_math': False,
            'use_prize_tracking': False,
            'use_energy_planning': True,
            'use_smart_retreat': False,
            'use_evolution_priority': True,
            'use_ability_eval': False,
        },
        'hard': {
            'random_factor': 0.05,
            'mistake_chance': 0.02,
            'use_board_eval': True,
            'use_weakness_aware': True,
            'use_ko_math': True,
            'use_prize_tracking': True,
            'use_energy_planning': True,
            'use_smart_retreat': True,
            'use_evolution_priority': True,
            'use_ability_eval': True,
        },
        'ultra': {
            'random_factor': 0.0,
            'mistake_chance': 0.0,
            'use_board_eval': True,
            'use_weakness_aware': True,
            'use_ko_math': True,
            'use_prize_tracking': True,
            'use_energy_planning': True,
            'use_smart_retreat': True,
            'use_evolution_priority': True,
            'use_ability_eval': True,
        },
    }

    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty
        # Per-player difficulty overrides (for bot-vs-bot with different levels)
        self.player_difficulties: dict[str, str] = {}

    # ── Helpers ──────────────────────────────────────────────────

    def _get_difficulty(self, player_id: str = None) -> str:
        if player_id and player_id in self.player_difficulties:
            return self.player_difficulties[player_id]
        return self.difficulty

    def _get_settings(self, player_id: str = None) -> dict:
        diff = self._get_difficulty(player_id)
        return self.PKM_DIFFICULTY_SETTINGS.get(diff, self.PKM_DIFFICULTY_SETTINGS['medium'])

    def _opponent_id(self, state: GameState, player_id: str) -> Optional[str]:
        for pid in state.players:
            if pid != player_id:
                return pid
        return None

    # ── Zone Queries ─────────────────────────────────────────────

    def _get_hand(self, state: GameState, player_id: str) -> list[str]:
        zone = state.zones.get(f"hand_{player_id}")
        return list(zone.objects) if zone else []

    def _get_active(self, state: GameState, player_id: str) -> Optional[str]:
        zone = state.zones.get(f"active_spot_{player_id}")
        if zone and zone.objects:
            return zone.objects[0]
        return None

    def _get_bench(self, state: GameState, player_id: str) -> list[str]:
        zone = state.zones.get(f"bench_{player_id}")
        return list(zone.objects) if zone else []

    def _get_all_in_play(self, state: GameState, player_id: str) -> list[str]:
        """All Pokemon in active spot + bench for player."""
        result = []
        active = self._get_active(state, player_id)
        if active:
            result.append(active)
        result.extend(self._get_bench(state, player_id))
        return result

    def _remaining_hp(self, pokemon: 'GameObject') -> int:
        """Remaining HP = max HP - (damage_counters * 10)."""
        hp = 0
        if pokemon.card_def:
            hp = pokemon.card_def.hp or 0
        return max(0, hp - pokemon.state.damage_counters * 10)

    def _max_hp(self, pokemon: 'GameObject') -> int:
        if pokemon.card_def:
            return pokemon.card_def.hp or 0
        return 0

    # ══════════════════════════════════════════════════════════════
    #  TURN EXECUTION
    # ══════════════════════════════════════════════════════════════

    async def take_turn(self, player_id: str, state: GameState, game) -> list[Event]:
        """
        Execute a full Pokemon TCG turn for the AI.

        Args:
            player_id: The AI player's ID
            state: Current game state
            game: The Game instance (for calling turn_manager methods)

        Returns:
            List of events generated during the turn
        """
        events: list[Event] = []
        turn_mgr = getattr(game, 'turn_manager', None)

        def _game_over() -> bool:
            return hasattr(game, 'is_game_over') and game.is_game_over()

        # Safety cap on total actions per turn
        max_actions = 30

        for _ in range(max_actions):
            if _game_over():
                return events

            action_taken = False

            # 1. Use Abilities
            ability_events = self._do_abilities(player_id, state, turn_mgr)
            if ability_events:
                events.extend(ability_events)
                action_taken = True
                if _game_over():
                    return events

            # 2. Play Supporter (1 per turn)
            supporter_events = self._do_play_supporter(player_id, state, turn_mgr)
            if supporter_events:
                events.extend(supporter_events)
                action_taken = True
                if _game_over():
                    return events

            # 3. Play Basic Pokemon to bench
            basic_events = self._do_play_basics(player_id, state, turn_mgr)
            if basic_events:
                events.extend(basic_events)
                action_taken = True

            # 4. Evolve Pokemon
            evolve_events = self._do_evolve(player_id, state, turn_mgr)
            if evolve_events:
                events.extend(evolve_events)
                action_taken = True

            # 5. Attach Energy (1 per turn)
            energy_events = self._do_attach_energy(player_id, state, turn_mgr)
            if energy_events:
                events.extend(energy_events)
                action_taken = True

            # 6. Play Items
            item_events = self._do_play_items(player_id, state, turn_mgr)
            if item_events:
                events.extend(item_events)
                action_taken = True
                if _game_over():
                    return events

            # 7. Retreat if favorable
            retreat_events = self._do_retreat(player_id, state, turn_mgr)
            if retreat_events:
                events.extend(retreat_events)
                action_taken = True

            # Only loop if we did something (to handle newly drawn cards, etc.)
            if not action_taken:
                break

        # 8. Attack (ends the turn)
        if not _game_over():
            attack_events = await self._do_attack(player_id, state, game)
            events.extend(attack_events)

        return events

    # ══════════════════════════════════════════════════════════════
    #  PHASE IMPLEMENTATIONS
    # ══════════════════════════════════════════════════════════════

    # ── 1. Abilities ─────────────────────────────────────────────

    def _do_abilities(self, player_id: str, state: GameState, turn_mgr) -> list[Event]:
        """Use beneficial abilities on in-play Pokemon."""
        settings = self._get_settings(player_id)
        events: list[Event] = []

        for pkm_id in self._get_all_in_play(state, player_id):
            pkm = state.objects.get(pkm_id)
            if not pkm or not pkm.card_def or not pkm.card_def.ability:
                continue

            ability = pkm.card_def.ability

            # Check per-turn usage if flagged
            if getattr(pkm.state, 'ability_used_this_turn', False):
                continue

            effect_fn = ability.get('effect_fn')
            if not effect_fn:
                continue

            # Easy: random chance to skip abilities
            if settings['random_factor'] > 0 and random.random() < settings['random_factor']:
                continue

            # Hard+: evaluate whether the ability is beneficial
            if settings['use_ability_eval']:
                if not self._should_use_ability(pkm, state, player_id):
                    continue

            if turn_mgr and hasattr(turn_mgr, '_use_ability'):
                ability_events = turn_mgr._use_ability(player_id, pkm_id)
                events.extend(ability_events)
                # Mark used to prevent infinite loops
                pkm.state.ability_used_this_turn = True

        return events

    def _should_use_ability(self, pokemon: 'GameObject', state: GameState,
                            player_id: str) -> bool:
        """Heuristic: is it beneficial to use this ability now?"""
        ability = pokemon.card_def.ability
        if not ability:
            return False

        ability_text = (ability.get('text', '') or '').lower()

        # Draw abilities: always beneficial unless hand is huge
        if 'draw' in ability_text:
            hand = self._get_hand(state, player_id)
            return len(hand) < 10

        # Heal abilities: beneficial if something is damaged
        if 'heal' in ability_text or 'remove' in ability_text:
            for pkm_id in self._get_all_in_play(state, player_id):
                pkm = state.objects.get(pkm_id)
                if pkm and pkm.state.damage_counters > 0:
                    return True
            return False

        # Damage abilities: always use
        if 'damage' in ability_text:
            return True

        # Energy acceleration: always use
        if 'energy' in ability_text:
            return True

        # Default: use it
        return True

    # ── 2. Supporter ─────────────────────────────────────────────

    def _do_play_supporter(self, player_id: str, state: GameState,
                           turn_mgr) -> list[Event]:
        """Play the best available Supporter card (1 per turn)."""
        player = state.players.get(player_id)
        if not player or player.supporter_played_this_turn:
            return []

        hand = self._get_hand(state, player_id)
        supporters = []
        for card_id in hand:
            obj = state.objects.get(card_id)
            if not obj:
                continue
            types = obj.characteristics.types if obj.characteristics else set()
            if CardType.SUPPORTER in types:
                score = self._score_trainer(obj, state, player_id)
                supporters.append((card_id, score))

        if not supporters:
            return []

        settings = self._get_settings(player_id)
        if settings['random_factor'] > 0:
            for i in range(len(supporters)):
                cid, sc = supporters[i]
                supporters[i] = (cid, sc + random.uniform(0, settings['random_factor'] * 30))

        supporters.sort(key=lambda x: x[1], reverse=True)

        # Mistake chance: suboptimal pick
        if len(supporters) >= 2 and random.random() < settings['mistake_chance']:
            chosen_id = random.choice(supporters[1:])[0]
        else:
            chosen_id = supporters[0][0]

        if turn_mgr and hasattr(turn_mgr, '_play_trainer'):
            return turn_mgr._play_trainer(player_id, chosen_id, 'supporter')
        return []

    # ── 3. Play Basics ───────────────────────────────────────────

    def _do_play_basics(self, player_id: str, state: GameState,
                        turn_mgr) -> list[Event]:
        """Play Basic Pokemon from hand to bench."""
        events: list[Event] = []
        bench = self._get_bench(state, player_id)

        if len(bench) >= 5:
            return events

        hand = self._get_hand(state, player_id)
        basics = []
        for card_id in hand:
            obj = state.objects.get(card_id)
            if not obj:
                continue
            types = obj.characteristics.types if obj.characteristics else set()
            if CardType.POKEMON not in types:
                continue
            if not obj.card_def or obj.card_def.evolution_stage != "Basic":
                continue
            basics.append((card_id, self._score_basic_play(obj, state, player_id)))

        if not basics:
            return events

        settings = self._get_settings(player_id)
        if settings['random_factor'] > 0:
            for i in range(len(basics)):
                cid, sc = basics[i]
                basics[i] = (cid, sc + random.uniform(0, settings['random_factor'] * 20))

        basics.sort(key=lambda x: x[1], reverse=True)

        slots = 5 - len(bench)
        for card_id, _ in basics[:slots]:
            if turn_mgr and hasattr(turn_mgr, '_play_basic'):
                play_events = turn_mgr._play_basic(player_id, card_id)
                events.extend(play_events)

        return events

    def _score_basic_play(self, card: 'GameObject', state: GameState,
                          player_id: str) -> float:
        """Score how valuable it is to bench this Basic Pokemon."""
        score = 10.0  # Base value: bench presence is good

        settings = self._get_settings(player_id)

        if not card.card_def:
            return score

        # Higher HP basics are more resilient
        hp = card.card_def.hp or 0
        score += hp / 20.0

        # Has evolutions in hand? Prioritize benching the base
        if settings['use_evolution_priority']:
            hand = self._get_hand(state, player_id)
            for cid in hand:
                evo = state.objects.get(cid)
                if evo and evo.card_def and evo.card_def.evolves_from == card.name:
                    score += 25.0
                    break

        # EX/V Pokemon: worth extra prizes if KO'd, but high HP
        if card.card_def.is_ex:
            score += 5.0  # Good stats, but risky (2 prizes)
            # In hard+, de-prioritize if we're behind on prizes
            if settings['use_prize_tracking']:
                opp_id = self._opponent_id(state, player_id)
                if opp_id:
                    player = state.players.get(player_id)
                    opponent = state.players.get(opp_id)
                    if player and opponent:
                        if player.prizes_remaining <= 2 and opponent.prizes_remaining > 2:
                            score -= 10.0  # Opponent close to winning, avoid giving 2 prizes

        # Has attacks that are immediately useful (low cost)
        for attack in (card.card_def.attacks or []):
            cost = attack.get('cost', [])
            total_cost = sum(c.get('count', 0) for c in cost)
            if total_cost <= 1:
                score += 5.0  # Can attack soon
                break

        return score

    # ── 4. Evolution ─────────────────────────────────────────────

    def _do_evolve(self, player_id: str, state: GameState,
                   turn_mgr) -> list[Event]:
        """Evolve Pokemon when possible."""
        events: list[Event] = []
        hand = self._get_hand(state, player_id)

        # Collect evolution cards in hand
        evo_cards = []
        for card_id in hand:
            obj = state.objects.get(card_id)
            if not obj or not obj.card_def:
                continue
            types = obj.characteristics.types if obj.characteristics else set()
            if CardType.POKEMON not in types:
                continue
            if not obj.card_def.evolves_from:
                continue
            evo_cards.append((card_id, obj))

        if not evo_cards:
            return events

        # Find targets for each evolution card
        in_play = self._get_all_in_play(state, player_id)

        for evo_id, evo_obj in evo_cards:
            best_target = None
            best_score = -1.0

            for pkm_id in in_play:
                pkm = state.objects.get(pkm_id)
                if not pkm:
                    continue

                # Check legality via turn manager
                if turn_mgr and hasattr(turn_mgr, 'can_evolve'):
                    ok, _ = turn_mgr.can_evolve(pkm_id, evo_id)
                    if not ok:
                        continue
                else:
                    # Fallback: name match
                    if pkm.name != evo_obj.card_def.evolves_from:
                        continue
                    if pkm.state.turns_in_play < 1:
                        continue
                    if pkm.state.evolved_this_turn:
                        continue

                score = self._score_evolution(pkm, evo_obj, state, player_id)
                if score > best_score:
                    best_score = score
                    best_target = pkm_id

            if best_target and turn_mgr and hasattr(turn_mgr, 'evolve_pokemon'):
                evo_events = turn_mgr.evolve_pokemon(best_target, evo_id)
                events.extend(evo_events)
                # Refresh in_play since the evolved Pokemon changed
                in_play = self._get_all_in_play(state, player_id)

        return events

    def _score_evolution(self, base: 'GameObject', evolution: 'GameObject',
                         state: GameState, player_id: str) -> float:
        """Score how good it is to evolve this Pokemon now."""
        score = 20.0  # Evolving is generally good

        settings = self._get_settings(player_id)

        if not evolution.card_def:
            return score

        # HP increase
        old_hp = self._max_hp(base)
        new_hp = evolution.card_def.hp or 0
        hp_gain = new_hp - old_hp
        score += hp_gain / 10.0

        # Better attacks
        for attack in (evolution.card_def.attacks or []):
            damage = attack.get('damage', 0)
            score += damage / 20.0

        # Active Pokemon benefits more from evolving (immediate impact)
        active_id = self._get_active(state, player_id)
        if active_id and base.id == active_id:
            score += 15.0

        # Damaged Pokemon benefits from HP increase (evolution keeps counters)
        if base.state.damage_counters > 0:
            remaining_after = new_hp - base.state.damage_counters * 10
            if remaining_after > 0 and self._remaining_hp(base) <= old_hp * 0.3:
                score += 10.0  # Was about to die, now has more room

        # Hard+: check if evolution has weakness advantage against opponent
        if settings['use_weakness_aware']:
            opp_active_id = self._get_active(state, self._opponent_id(state, player_id) or '')
            if opp_active_id:
                opp = state.objects.get(opp_active_id)
                if opp and opp.card_def and evolution.card_def.pokemon_type:
                    if opp.card_def.weakness_type == evolution.card_def.pokemon_type:
                        score += 15.0  # We hit weakness

        return score

    # ── 5. Energy Attachment ─────────────────────────────────────

    def _do_attach_energy(self, player_id: str, state: GameState,
                          turn_mgr) -> list[Event]:
        """Attach one energy card from hand to the best target."""
        player = state.players.get(player_id)
        if not player or player.energy_attached_this_turn:
            return []

        hand = self._get_hand(state, player_id)
        energy_cards = []
        for card_id in hand:
            obj = state.objects.get(card_id)
            if not obj:
                continue
            types = obj.characteristics.types if obj.characteristics else set()
            if CardType.ENERGY in types:
                energy_cards.append(card_id)

        if not energy_cards:
            return []

        # Score each (energy, target) pair and pick the best
        in_play = self._get_all_in_play(state, player_id)
        if not in_play:
            return []

        best_pair: Optional[tuple[str, str]] = None
        best_score = -999.0

        for energy_id in energy_cards:
            energy_obj = state.objects.get(energy_id)
            if not energy_obj:
                continue

            for pkm_id in in_play:
                pkm = state.objects.get(pkm_id)
                if not pkm:
                    continue
                score = self._score_energy_attachment(
                    energy_obj, pkm, state, player_id
                )
                if score > best_score:
                    best_score = score
                    best_pair = (energy_id, pkm_id)

        if not best_pair:
            return []

        if turn_mgr and hasattr(turn_mgr, '_attach_energy'):
            return turn_mgr._attach_energy(player_id, best_pair[0], best_pair[1])
        return []

    def _score_energy_attachment(self, energy: 'GameObject', pokemon: 'GameObject',
                                 state: GameState, player_id: str) -> float:
        """Score how good it is to attach this energy to this Pokemon."""
        score = 0.0
        settings = self._get_settings(player_id)

        if not pokemon.card_def:
            return score

        energy_system = PokemonEnergySystem(state)
        energy_type = energy_system._get_energy_type(energy)
        current_energy = energy_system.get_attached_energy(pokemon.id)
        total_current = energy_system.get_total_energy(pokemon.id)

        # Active Pokemon gets priority (can attack soonest)
        active_id = self._get_active(state, player_id)
        if active_id and pokemon.id == active_id:
            score += 20.0

        # Check each attack: does this energy bring us closer to attacking?
        for attack in (pokemon.card_def.attacks or []):
            cost = attack.get('cost', [])
            damage = attack.get('damage', 0)

            if not cost:
                continue

            # Count how many energy we still need after attaching this one
            needed_typed = 0
            needed_total = 0
            satisfied_typed = 0
            for req in cost:
                etype = req.get('type', 'C')
                count = req.get('count', 0)
                needed_total += count
                if etype != 'C':
                    needed_typed += count
                    have = current_energy.get(etype, 0)
                    still_need = max(0, count - have)
                    # Does this energy satisfy a typed need?
                    if etype == energy_type and still_need > 0:
                        satisfied_typed += 1

            energy_remaining_needed = needed_total - total_current - 1  # -1 for this attachment

            # Bonus for bringing an attack exactly online
            if energy_remaining_needed <= 0:
                score += 30.0 + damage / 5.0
            elif energy_remaining_needed == 1:
                score += 15.0 + damage / 10.0

            # Matching typed requirement is more valuable
            if satisfied_typed > 0:
                score += 15.0

        # Medium+: prefer Pokemon that can attack sooner
        if settings['use_energy_planning']:
            # Fewer energy needed -> higher priority
            min_energy_gap = 999
            for attack in (pokemon.card_def.attacks or []):
                cost = attack.get('cost', [])
                total_needed = sum(c.get('count', 0) for c in cost)
                gap = total_needed - total_current
                if gap < min_energy_gap:
                    min_energy_gap = gap
            if min_energy_gap < 999:
                score += max(0, 10 - min_energy_gap * 3)

        # Hard+: consider weakness matchup and KO potential
        if settings['use_ko_math']:
            opp_id = self._opponent_id(state, player_id)
            opp_active_id = self._get_active(state, opp_id or '') if opp_id else None
            if opp_active_id:
                opp = state.objects.get(opp_active_id)
                if opp and opp.card_def:
                    opp_remaining = self._remaining_hp(opp)
                    # Check if this Pokemon could KO the opponent's active
                    for attack in (pokemon.card_def.attacks or []):
                        dmg = attack.get('damage', 0)
                        if dmg <= 0:
                            continue
                        # Apply weakness
                        if (settings['use_weakness_aware'] and
                                pokemon.card_def.pokemon_type and
                                opp.card_def.weakness_type == pokemon.card_def.pokemon_type):
                            dmg *= 2
                        if dmg >= opp_remaining:
                            score += 20.0
                            break

        # Slightly penalize benched Pokemon that have plenty of energy already
        if active_id and pokemon.id != active_id and total_current >= 3:
            score -= 5.0

        return score

    # ── 6. Items ─────────────────────────────────────────────────

    def _do_play_items(self, player_id: str, state: GameState,
                       turn_mgr) -> list[Event]:
        """Play beneficial Item cards (no per-turn limit)."""
        events: list[Event] = []
        hand = self._get_hand(state, player_id)

        items = []
        for card_id in hand:
            obj = state.objects.get(card_id)
            if not obj:
                continue
            types = obj.characteristics.types if obj.characteristics else set()
            if CardType.ITEM in types:
                score = self._score_trainer(obj, state, player_id)
                items.append((card_id, score))

        if not items:
            return events

        settings = self._get_settings(player_id)
        if settings['random_factor'] > 0:
            for i in range(len(items)):
                cid, sc = items[i]
                items[i] = (cid, sc + random.uniform(0, settings['random_factor'] * 20))

        items.sort(key=lambda x: x[1], reverse=True)

        # Play all items with positive score
        for card_id, score in items:
            if score <= 0:
                break
            # Mistake chance: skip some items
            if random.random() < settings['mistake_chance']:
                continue
            if turn_mgr and hasattr(turn_mgr, '_play_trainer'):
                item_events = turn_mgr._play_trainer(player_id, card_id, 'item')
                events.extend(item_events)

        return events

    def _score_trainer(self, card: 'GameObject', state: GameState,
                       player_id: str) -> float:
        """Score a Trainer card (Item or Supporter) for play priority."""
        score = 10.0  # Base: trainers are generally helpful

        if not card.card_def:
            return score

        text = (card.card_def.text or '').lower()
        name = (card.card_def.name or '').lower()

        # Draw cards are high priority
        if 'draw' in text:
            hand_size = len(self._get_hand(state, player_id))
            if hand_size <= 3:
                score += 30.0
            elif hand_size <= 6:
                score += 15.0
            else:
                score += 5.0

        # Search effects (tutors)
        if 'search' in text or 'find' in text:
            score += 25.0

        # Healing
        if 'heal' in text or 'remove' in text and 'damage' in text:
            has_damaged = False
            for pkm_id in self._get_all_in_play(state, player_id):
                pkm = state.objects.get(pkm_id)
                if pkm and pkm.state.damage_counters > 0:
                    has_damaged = True
                    break
            if has_damaged:
                score += 20.0
            else:
                score -= 10.0  # Waste if nothing is damaged

        # Energy retrieval / acceleration
        if 'energy' in text and ('attach' in text or 'hand' in text):
            score += 20.0

        # Switching effects (gust, switch)
        if 'switch' in text:
            score += 15.0

        # Damage / removal
        if 'damage' in text and ('opponent' in text or 'enemy' in text or "opposing" in text):
            score += 20.0

        # Hand disruption
        if 'discard' in text and 'opponent' in text:
            score += 15.0

        # Pokemon Tool attachment
        types = card.characteristics.types if card.characteristics else set()
        if CardType.POKEMON_TOOL in types:
            in_play = self._get_all_in_play(state, player_id)
            if in_play:
                score += 15.0
            else:
                score -= 5.0

        return score

    # ── 7. Retreat ───────────────────────────────────────────────

    def _do_retreat(self, player_id: str, state: GameState,
                    turn_mgr) -> list[Event]:
        """Retreat the active Pokemon if a better attacker is on the bench."""
        player = state.players.get(player_id)
        if not player or player.retreated_this_turn:
            return []

        active_id = self._get_active(state, player_id)
        if not active_id:
            return []

        active = state.objects.get(active_id)
        if not active:
            return []

        # Check status: can we retreat?
        ok, _ = can_retreat(active_id, state)
        if not ok:
            return []

        settings = self._get_settings(player_id)

        # Easy difficulty: never retreats proactively
        if not settings['use_smart_retreat'] and not settings['use_board_eval']:
            return []

        # Check retreat cost feasibility
        retreat_cost = 0
        if active.card_def:
            retreat_cost = active.card_def.retreat_cost or 0

        if retreat_cost > 0:
            energy_system = PokemonEnergySystem(state)
            cost = [{'type': 'C', 'count': retreat_cost}]
            if not energy_system.can_pay_cost(active_id, cost):
                return []

        # Score active Pokemon as attacker
        active_score = self._score_attacker(active, state, player_id)

        # Find best bench alternative
        bench = self._get_bench(state, player_id)
        best_bench_id = None
        best_bench_score = -999.0

        for bench_id in bench:
            bench_pkm = state.objects.get(bench_id)
            if not bench_pkm:
                continue
            bench_score = self._score_attacker(bench_pkm, state, player_id)
            if bench_score > best_bench_score:
                best_bench_score = bench_score
                best_bench_id = bench_id

        if not best_bench_id:
            return []

        # Retreat threshold: bench Pokemon must be significantly better
        # Account for the cost of losing energy from retreat
        energy_penalty = retreat_cost * 5.0
        threshold = 15.0 + energy_penalty

        # Forced retreat scenarios (always retreat)
        forced = False

        # Active can't attack at all
        can_atk, _ = can_attack(active_id, state)
        if not can_atk:
            forced = True

        # Active has no available attacks (no energy)
        if not forced:
            combat_mgr = PokemonCombatManager(state)
            available_attacks = combat_mgr.get_available_attacks(active_id)
            if not available_attacks:
                # Only force if bench can attack
                bench_pkm = state.objects.get(best_bench_id)
                if bench_pkm:
                    bench_attacks = combat_mgr.get_available_attacks(best_bench_id)
                    if bench_attacks:
                        forced = True

        # Active is about to be KO'd (low HP, opponent can easily KO)
        if not forced and settings['use_ko_math']:
            remaining = self._remaining_hp(active)
            max_hp = self._max_hp(active)
            if max_hp > 0 and remaining <= max_hp * 0.2:
                # EX Pokemon: retreat to save 2 prizes
                if active.card_def and active.card_def.is_ex:
                    forced = True
                elif remaining <= 30:
                    forced = True

        if forced or best_bench_score > active_score + threshold:
            if turn_mgr and hasattr(turn_mgr, '_retreat'):
                return turn_mgr._retreat(player_id, best_bench_id)

        return []

    def _score_attacker(self, pokemon: 'GameObject', state: GameState,
                        player_id: str) -> float:
        """Score how effective this Pokemon is as the active attacker."""
        score = 0.0
        settings = self._get_settings(player_id)

        if not pokemon.card_def:
            return score

        remaining = self._remaining_hp(pokemon)
        max_hp = self._max_hp(pokemon)

        # HP score: survivability
        score += remaining / 10.0

        # Attack availability and damage output
        energy_system = PokemonEnergySystem(state)
        combat_mgr = PokemonCombatManager(state)
        available_attacks = combat_mgr.get_available_attacks(pokemon.id)

        if available_attacks:
            best_damage = max(a.get('damage', 0) for a in available_attacks)
            score += best_damage / 5.0
        else:
            score -= 20.0  # Can't attack = bad active

        # Status conditions
        if 'paralyzed' in pokemon.state.status_conditions:
            score -= 30.0
        if 'asleep' in pokemon.state.status_conditions:
            score -= 20.0
        if 'confused' in pokemon.state.status_conditions:
            score -= 10.0

        # Medium+: weakness matchup
        if settings['use_weakness_aware']:
            opp_id = self._opponent_id(state, player_id)
            opp_active_id = self._get_active(state, opp_id or '') if opp_id else None
            if opp_active_id:
                opp = state.objects.get(opp_active_id)
                if opp and opp.card_def:
                    # We hit their weakness -> good
                    if (pokemon.card_def.pokemon_type and
                            opp.card_def.weakness_type == pokemon.card_def.pokemon_type):
                        score += 20.0
                    # They hit our weakness -> bad
                    if (opp.card_def.pokemon_type and
                            pokemon.card_def.weakness_type == opp.card_def.pokemon_type):
                        score -= 15.0
                    # We resist them -> good
                    if hasattr(pokemon.card_def, 'resistance_type'):
                        if (opp.card_def.pokemon_type and
                                pokemon.card_def.resistance_type == opp.card_def.pokemon_type):
                            score += 10.0

        # Hard+: KO math
        if settings['use_ko_math'] and available_attacks:
            opp_id = self._opponent_id(state, player_id)
            opp_active_id = self._get_active(state, opp_id or '') if opp_id else None
            if opp_active_id:
                opp = state.objects.get(opp_active_id)
                if opp:
                    opp_remaining = self._remaining_hp(opp)
                    for attack in available_attacks:
                        dmg = attack.get('damage', 0)
                        # Factor in weakness
                        final_dmg = self._estimate_damage(pokemon, opp, dmg, state)
                        if final_dmg >= opp_remaining:
                            score += 30.0  # Can KO!
                            # Extra points for KO'ing EX (2 prizes)
                            if opp.card_def and opp.card_def.is_ex:
                                score += 15.0
                            break

        # Retreat cost: high retreat cost means this Pokemon is harder to swap out
        retreat_cost = pokemon.card_def.retreat_cost or 0
        score -= retreat_cost * 2.0

        # EX Pokemon risk: worth 2 prizes
        if pokemon.card_def.is_ex:
            score -= 5.0  # Slight penalty for risk
            if remaining <= max_hp * 0.3:
                score -= 10.0  # About to give up 2 prizes

        return score

    # ── 8. Attack ────────────────────────────────────────────────

    async def _do_attack(self, player_id: str, state: GameState,
                         game) -> list[Event]:
        """Choose and execute the best attack with the active Pokemon."""
        active_id = self._get_active(state, player_id)
        if not active_id:
            return []

        active = state.objects.get(active_id)
        if not active:
            return []

        # Check status conditions
        ok, _ = can_attack(active_id, state)
        if not ok:
            return []

        # Get available attacks
        combat_mgr = PokemonCombatManager(state)
        available_attacks = combat_mgr.get_available_attacks(active_id)
        if not available_attacks:
            return []

        # Score each attack
        settings = self._get_settings(player_id)
        scored_attacks = []

        for attack in available_attacks:
            score = self._score_attack(active, attack, state, player_id)
            scored_attacks.append((attack, score))

        if not scored_attacks:
            return []

        # Apply noise
        if settings['random_factor'] > 0:
            for i in range(len(scored_attacks)):
                atk, sc = scored_attacks[i]
                scored_attacks[i] = (atk, sc + random.uniform(0, settings['random_factor'] * 30))

        scored_attacks.sort(key=lambda x: x[1], reverse=True)

        # Mistake chance
        if len(scored_attacks) >= 2 and random.random() < settings['mistake_chance']:
            chosen = random.choice(scored_attacks[1:])[0]
        else:
            chosen = scored_attacks[0][0]

        attack_index = chosen.get('_index', 0)

        # Execute attack via turn manager (async) or combat manager (sync fallback)
        turn_mgr = getattr(game, 'turn_manager', None)
        if turn_mgr and hasattr(turn_mgr, '_execute_attack'):
            return await turn_mgr._execute_attack(player_id, attack_index)

        return combat_mgr.declare_attack(active_id, attack_index)

    def _score_attack(self, attacker: 'GameObject', attack: dict,
                      state: GameState, player_id: str) -> float:
        """Score how good this attack choice is."""
        score = 0.0
        settings = self._get_settings(player_id)

        damage = attack.get('damage', 0)
        score += damage / 5.0  # Base: more damage is better

        # Effect attacks with 0 damage may still be valuable
        effect_fn = attack.get('effect_fn')
        if effect_fn and damage == 0:
            score += 10.0  # Has an effect, probably useful

        attack_text = (attack.get('text', '') or '').lower()

        # Status effects are valuable
        if 'poison' in attack_text:
            score += 8.0
        if 'burn' in attack_text:
            score += 7.0
        if 'paralyze' in attack_text or 'paralyzed' in attack_text:
            score += 12.0
        if 'asleep' in attack_text or 'sleep' in attack_text:
            score += 8.0
        if 'confus' in attack_text:
            score += 6.0

        # Self-damage or recoil is bad
        if 'damage to itself' in attack_text or 'this pokemon' in attack_text and 'damage' in attack_text:
            score -= 10.0

        # Energy discard cost
        discard_cost = attack.get('discard_cost')
        if discard_cost:
            total_discard = sum(c.get('count', 0) for c in discard_cost)
            score -= total_discard * 8.0  # Losing energy is costly

        # Medium+: weakness-aware damage
        if settings['use_weakness_aware']:
            opp_id = self._opponent_id(state, player_id)
            opp_active_id = self._get_active(state, opp_id or '') if opp_id else None
            if opp_active_id and damage > 0:
                opp = state.objects.get(opp_active_id)
                if opp:
                    final_dmg = self._estimate_damage(attacker, opp, damage, state)
                    # Replace raw damage score with effective damage score
                    score = score - damage / 5.0 + final_dmg / 5.0

        # Hard+: KO math
        if settings['use_ko_math'] and damage > 0:
            opp_id = self._opponent_id(state, player_id)
            opp_active_id = self._get_active(state, opp_id or '') if opp_id else None
            if opp_active_id:
                opp = state.objects.get(opp_active_id)
                if opp:
                    opp_remaining = self._remaining_hp(opp)
                    final_dmg = self._estimate_damage(attacker, opp, damage, state)
                    if final_dmg >= opp_remaining:
                        score += 40.0  # KO bonus
                        if opp.card_def and opp.card_def.is_ex:
                            score += 20.0  # 2 prize KO

                        # Ultra: check if this wins the game (last prizes)
                        if settings['use_prize_tracking']:
                            player = state.players.get(player_id)
                            if player:
                                prize_value = 1
                                if opp.card_def and opp.card_def.is_ex:
                                    prize_value = opp.card_def.prize_count
                                if player.prizes_remaining <= prize_value:
                                    score += 100.0  # This wins the game!

        # Bench damage attacks
        if 'bench' in attack_text and 'damage' in attack_text:
            score += 5.0

        # Draw effects
        if 'draw' in attack_text:
            score += 5.0

        # Healing effects
        if 'heal' in attack_text:
            if attacker.state.damage_counters > 0:
                score += 8.0
            else:
                score -= 3.0  # No benefit if at full HP

        return score

    # ── Damage Estimation ────────────────────────────────────────

    def _estimate_damage(self, attacker: 'GameObject', defender: 'GameObject',
                         base_damage: int, state: GameState) -> int:
        """Estimate final damage after weakness/resistance."""
        damage = base_damage

        attacker_type = None
        if attacker.card_def:
            attacker_type = attacker.card_def.pokemon_type

        if attacker_type and defender.card_def:
            # Weakness: x2
            if defender.card_def.weakness_type == attacker_type:
                modifier = getattr(defender.card_def, 'weakness_modifier', 'x2')
                if modifier == "x2":
                    damage *= 2

            # Resistance: -30
            if hasattr(defender.card_def, 'resistance_type'):
                if defender.card_def.resistance_type == attacker_type:
                    resist_mod = getattr(defender.card_def, 'resistance_modifier', -30)
                    damage += resist_mod  # negative value

        return max(0, damage)

    # ── Board Evaluation ─────────────────────────────────────────

    def _evaluate_board(self, player_id: str, state: GameState) -> float:
        """
        Evaluate board state from player's perspective.

        Components:
        - Pokemon HP (30%): total remaining HP comparison
        - Board presence (25%): number of Pokemon in play
        - Energy (20%): total energy attached
        - Prize cards (15%): prizes remaining comparison
        - Hand size (10%): card advantage

        Returns: -1.0 (losing) to 1.0 (winning)
        """
        opp_id = self._opponent_id(state, player_id)
        if not opp_id:
            return 0.0

        player = state.players.get(player_id)
        opponent = state.players.get(opp_id)
        if not player or not opponent:
            return 0.0

        energy_system = PokemonEnergySystem(state)

        # HP comparison
        my_hp = sum(
            self._remaining_hp(state.objects[pid])
            for pid in self._get_all_in_play(state, player_id)
            if pid in state.objects
        )
        opp_hp = sum(
            self._remaining_hp(state.objects[pid])
            for pid in self._get_all_in_play(state, opp_id)
            if pid in state.objects
        )
        total_hp = my_hp + opp_hp
        hp_score = (my_hp - opp_hp) / total_hp if total_hp > 0 else 0.0

        # Board presence
        my_count = len(self._get_all_in_play(state, player_id))
        opp_count = len(self._get_all_in_play(state, opp_id))
        total_count = my_count + opp_count
        board_score = (my_count - opp_count) / max(total_count, 1)

        # Energy
        my_energy = sum(
            energy_system.get_total_energy(pid)
            for pid in self._get_all_in_play(state, player_id)
        )
        opp_energy = sum(
            energy_system.get_total_energy(pid)
            for pid in self._get_all_in_play(state, opp_id)
        )
        total_energy = my_energy + opp_energy
        energy_score = (my_energy - opp_energy) / max(total_energy, 1)

        # Prize cards (fewer remaining = winning)
        my_prizes = player.prizes_remaining
        opp_prizes = opponent.prizes_remaining
        total_prizes = my_prizes + opp_prizes
        # Inverted: fewer prizes remaining = better for us
        prize_score = (opp_prizes - my_prizes) / max(total_prizes, 1)

        # Hand size
        my_hand = len(self._get_hand(state, player_id))
        opp_hand_zone = state.zones.get(f"hand_{opp_id}")
        opp_hand = len(opp_hand_zone.objects) if opp_hand_zone else 0
        total_hand = my_hand + opp_hand
        hand_score = (my_hand - opp_hand) / max(total_hand, 1)

        total = (
            hp_score * 0.30 +
            board_score * 0.25 +
            energy_score * 0.20 +
            prize_score * 0.15 +
            hand_score * 0.10
        )
        return max(-1.0, min(1.0, total))

    # ── Promote Active (after KO) ───────────────────────────────

    def choose_promote(self, player_id: str, state: GameState) -> Optional[str]:
        """
        Choose which bench Pokemon to promote to active after a KO.

        Called by the turn manager when the active spot is empty.
        Returns the bench Pokemon ID to promote, or None.
        """
        bench = self._get_bench(state, player_id)
        if not bench:
            return None

        if len(bench) == 1:
            return bench[0]

        settings = self._get_settings(player_id)

        # Easy: random choice
        if settings['random_factor'] >= 0.3:
            return random.choice(bench)

        # Score each bench Pokemon as a potential active
        scored = []
        for pkm_id in bench:
            pkm = state.objects.get(pkm_id)
            if not pkm:
                continue
            score = self._score_attacker(pkm, state, player_id)
            scored.append((pkm_id, score))

        if not scored:
            return bench[0]

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]
