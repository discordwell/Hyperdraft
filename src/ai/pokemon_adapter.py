"""
Pokemon TCG AI Adapter

Adapts the AI system to play Pokemon TCG using the engine's turn structure.
Translates board state into decisions for energy attachment, evolution,
trainer plays, retreat, and attack selection.

Supports difficulty levels (easy, medium, hard, ultra) with progressively
smarter energy planning, KO math, weakness awareness, and prize tracking.
"""
import random
from dataclasses import dataclass, field
from typing import Optional, Callable, TYPE_CHECKING

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


# ══════════════════════════════════════════════════════════════
#  TURN CONTEXT — Per-turn board analysis
# ══════════════════════════════════════════════════════════════

@dataclass
class TurnContext:
    """Computed board analysis built once per turn, shared by all scoring functions."""
    # My state
    my_active: Optional[str] = None
    my_bench: list[str] = field(default_factory=list)
    my_hand_energy: list[str] = field(default_factory=list)
    my_hand_basics: list[str] = field(default_factory=list)
    my_hand_evolutions: list[str] = field(default_factory=list)
    my_hand_items: list[str] = field(default_factory=list)
    my_hand_supporters: list[str] = field(default_factory=list)
    my_prizes_remaining: int = 6

    # Opponent state
    opp_id: str = ''
    opp_active: Optional[str] = None
    opp_bench: list[str] = field(default_factory=list)
    opp_prizes_remaining: int = 6
    opp_hand_size: int = 0

    # Computed analysis
    can_ko_active: bool = False
    ko_attack_info: Optional[dict] = None
    opp_can_ko_me: bool = False
    opp_estimated_max_damage: int = 0
    my_weakness_exposed: bool = False
    their_weakness_exposed: bool = False
    evolution_map: dict = field(default_factory=dict)
    energy_needs: dict = field(default_factory=dict)
    prize_gap: int = 0
    game_phase: str = 'early'
    defensive_mode: bool = False
    retreat_urgency: float = 0.0
    has_switch_in_hand: bool = False


@dataclass
class EnergyPlan:
    """Multi-turn energy investment plan for a specific Pokemon + attack."""
    target_pokemon_id: str
    target_attack_index: int
    energy_type_needed: str
    turns_remaining: int
    priority: float
    created_turn: int


# ══════════════════════════════════════════════════════════════
#  TRAINER SCORER REGISTRY — Effect-aware scoring
# ══════════════════════════════════════════════════════════════

TRAINER_SCORERS: dict[str, Callable] = {}


def trainer_scorer(name: str):
    """Register a scoring function for a trainer card by name."""
    def decorator(fn):
        TRAINER_SCORERS[name] = fn
        return fn
    return decorator


@trainer_scorer("Professor's Research")
def _score_professors_research(ctx: TurnContext, state: GameState, player_id: str) -> float:
    hand_size = (len(ctx.my_hand_energy) + len(ctx.my_hand_basics) +
                 len(ctx.my_hand_evolutions) + len(ctx.my_hand_items) +
                 len(ctx.my_hand_supporters))
    if hand_size <= 2:
        return 50.0
    if hand_size <= 4:
        return 40.0
    if hand_size <= 6:
        return 25.0
    return 8.0


@trainer_scorer("Iono")
def _score_iono(ctx: TurnContext, state: GameState, player_id: str) -> float:
    score = 10.0
    # Disruption: opponent has big hand + few prizes = they draw fewer
    if ctx.opp_hand_size >= 5 and ctx.opp_prizes_remaining <= 3:
        score += 30.0
    elif ctx.opp_hand_size >= 4:
        score += ctx.opp_hand_size * 3
    # Self-refresh: good when our hand is bad
    my_hand_size = (len(ctx.my_hand_energy) + len(ctx.my_hand_basics) +
                    len(ctx.my_hand_evolutions) + len(ctx.my_hand_items) +
                    len(ctx.my_hand_supporters))
    if my_hand_size <= 2:
        score += 25.0
    # Penalized when we have few prizes (we'd draw fewer cards)
    if ctx.my_prizes_remaining <= 2:
        score -= 15.0
    return score


@trainer_scorer("Boss's Orders")
def _score_boss_orders(ctx: TurnContext, state: GameState, player_id: str) -> float:
    score = 5.0
    if not ctx.opp_bench:
        return -10.0
    # Find which bench target Boss's Orders would drag (weakest)
    worst_id = None
    worst_hp = 9999
    for pkm_id in ctx.opp_bench:
        pkm = state.objects.get(pkm_id)
        if pkm and pkm.card_def:
            remaining = (pkm.card_def.hp or 0) - pkm.state.damage_counters * 10
            if remaining < worst_hp:
                worst_hp = remaining
                worst_id = pkm_id
    if not worst_id:
        return score
    target = state.objects.get(worst_id)
    if not target:
        return score
    # Check if we can KO the dragged target
    if ctx.my_active:
        active = state.objects.get(ctx.my_active)
        if active and active.card_def:
            combat_mgr = PokemonCombatManager(state)
            for attack in combat_mgr.get_available_attacks(ctx.my_active):
                dmg = attack.get('damage', 0)
                if dmg > 0:
                    final_dmg = combat_mgr.calculate_damage(ctx.my_active, worst_id, dmg)
                    if final_dmg >= worst_hp:
                        prize_value = target.card_def.prize_count if target.card_def else 1
                        score += 30.0
                        if ctx.my_prizes_remaining <= prize_value:
                            score += 100.0
                        elif prize_value >= 2:
                            score += 15.0
                        break
    return score


@trainer_scorer("Nest Ball")
def _score_nest_ball(ctx: TurnContext, state: GameState, player_id: str) -> float:
    bench_count = len(ctx.my_bench)
    if bench_count >= 5:
        return -20.0
    score = 15.0
    if bench_count <= 1:
        score += 20.0
    if ctx.game_phase == 'early':
        score += 10.0
    if ctx.my_hand_evolutions:
        score += 10.0
    return score


@trainer_scorer("Ultra Ball")
def _score_ultra_ball(ctx: TurnContext, state: GameState, player_id: str) -> float:
    total_hand = (len(ctx.my_hand_energy) + len(ctx.my_hand_basics) +
                  len(ctx.my_hand_evolutions) + len(ctx.my_hand_items) +
                  len(ctx.my_hand_supporters))
    if total_hand < 2:
        return -15.0
    score = 20.0
    if ctx.evolution_map:
        score += 10.0
    if ctx.game_phase == 'early':
        score += 5.0
    return score


@trainer_scorer("Switch")
def _score_switch(ctx: TurnContext, state: GameState, player_id: str) -> float:
    score = 5.0
    if not ctx.my_active or not ctx.my_bench:
        return -10.0
    active = state.objects.get(ctx.my_active)
    if not active:
        return score
    if 'paralyzed' in active.state.status_conditions:
        score += 40.0
    elif 'asleep' in active.state.status_conditions:
        score += 30.0
    elif 'confused' in active.state.status_conditions:
        score += 15.0
    if 'poisoned' in active.state.status_conditions:
        score += 10.0
    if 'burned' in active.state.status_conditions:
        score += 10.0
    combat_mgr = PokemonCombatManager(state)
    if not combat_mgr.get_available_attacks(ctx.my_active):
        score += 25.0
    if ctx.opp_can_ko_me:
        score += 20.0
        if active.card_def and active.card_def.is_ex:
            score += 15.0
    if ctx.defensive_mode:
        score += 20.0
    if active.card_def:
        score += (active.card_def.retreat_cost or 0) * 5
    score += ctx.retreat_urgency * 0.5
    return score


@trainer_scorer("Potion")
def _score_potion(ctx: TurnContext, state: GameState, player_id: str) -> float:
    best_value = 0.0
    for pkm_id in [ctx.my_active] + ctx.my_bench:
        if not pkm_id:
            continue
        pkm = state.objects.get(pkm_id)
        if not pkm or pkm.state.damage_counters == 0:
            continue
        heal_counters = min(3, pkm.state.damage_counters)
        value = heal_counters * 5.0
        if pkm.card_def:
            remaining = (pkm.card_def.hp or 0) - pkm.state.damage_counters * 10
            healed_hp = remaining + heal_counters * 10
            if remaining <= ctx.opp_estimated_max_damage and healed_hp > ctx.opp_estimated_max_damage:
                value += 30.0
            if pkm.card_def.is_ex:
                value += 5.0
        if ctx.defensive_mode:
            value += 10.0
        best_value = max(best_value, value)
    if best_value <= 0:
        return -10.0
    return best_value


@trainer_scorer("Super Rod")
def _score_super_rod(ctx: TurnContext, state: GameState, player_id: str) -> float:
    grave_key = f"graveyard_{player_id}"
    graveyard = state.zones.get(grave_key)
    if not graveyard or not graveyard.objects:
        return -10.0
    recoverable = 0
    for card_id in graveyard.objects:
        obj = state.objects.get(card_id)
        if not obj:
            continue
        types = obj.characteristics.types if obj.characteristics else set()
        if CardType.POKEMON in types or CardType.ENERGY in types:
            recoverable += 1
    if recoverable == 0:
        return -10.0
    score = min(recoverable, 3) * 8.0
    if ctx.game_phase == 'late':
        score += 15.0
    elif ctx.game_phase == 'mid':
        score += 5.0
    lib_key = f"library_{player_id}"
    library = state.zones.get(lib_key)
    if library and len(library.objects) <= 10:
        score += 10.0
    return score


@trainer_scorer("Rare Candy")
def _score_rare_candy(ctx: TurnContext, state: GameState, player_id: str) -> float:
    # Check for Basic in play + Stage 2 in hand pairing
    for pkm_id in [ctx.my_active] + ctx.my_bench:
        if not pkm_id:
            continue
        pkm = state.objects.get(pkm_id)
        if not pkm or not pkm.card_def:
            continue
        if pkm.card_def.evolution_stage != "Basic":
            continue
        if pkm.state.turns_in_play < 1:
            continue
        for evo_id in ctx.my_hand_evolutions:
            evo = state.objects.get(evo_id)
            if evo and evo.card_def and evo.card_def.evolution_stage == "Stage 2":
                return 35.0
    return -15.0


@trainer_scorer("Choice Belt")
def _score_choice_belt(ctx: TurnContext, state: GameState, player_id: str) -> float:
    score = 5.0
    if ctx.opp_active:
        opp = state.objects.get(ctx.opp_active)
        if opp and opp.card_def and opp.card_def.is_ex:
            score += 25.0
            if ctx.my_active:
                active = state.objects.get(ctx.my_active)
                if active and active.card_def:
                    opp_remaining = (opp.card_def.hp or 0) - opp.state.damage_counters * 10
                    combat_mgr = PokemonCombatManager(state)
                    for attack in combat_mgr.get_available_attacks(ctx.my_active):
                        dmg = attack.get('damage', 0)
                        if dmg > 0:
                            final_dmg = combat_mgr.calculate_damage(ctx.my_active, ctx.opp_active, dmg)
                            if final_dmg + 30 >= opp_remaining > final_dmg:
                                score += 40.0
                                break
    else:
        score -= 5.0
    return score


@trainer_scorer("Judge")
def _score_judge(ctx: TurnContext, state: GameState, player_id: str) -> float:
    score = 10.0
    my_hand_size = (len(ctx.my_hand_energy) + len(ctx.my_hand_basics) +
                    len(ctx.my_hand_evolutions) + len(ctx.my_hand_items) +
                    len(ctx.my_hand_supporters))
    if ctx.opp_hand_size >= 6:
        score += 20.0
    elif ctx.opp_hand_size >= 4:
        score += 10.0
    if my_hand_size <= 2:
        score += 15.0
    if my_hand_size >= 6:
        score -= 10.0
    return score


@trainer_scorer("Artazon")
def _score_artazon(ctx: TurnContext, state: GameState, player_id: str) -> float:
    bench_count = len(ctx.my_bench)
    if bench_count >= 5:
        return -15.0
    score = 12.0
    if bench_count <= 2:
        score += 15.0
    if ctx.game_phase == 'early':
        score += 10.0
    return score


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
            'random_factor': 0.5,
            'mistake_chance': 0.25,
            'use_context': False,
            'use_energy_commitment': False,
            'use_trainer_registry': False,
            'use_retreat_analysis': False,
            'use_ko_math': False,
            'use_prize_strategy': False,
            'use_lethal_check': False,
            'use_weakness_aware': False,
            'use_board_eval': False,
            'use_evolution_priority': False,
            'use_ability_eval': False,
            'use_anti_lethal': False,
            'use_action_reordering': False,
            'use_smart_retreat': False,
            'use_energy_planning': False,
            'use_prize_tracking': False,
        },
        'medium': {
            'random_factor': 0.15,
            'mistake_chance': 0.08,
            'use_context': True,
            'use_energy_commitment': False,
            'use_trainer_registry': True,
            'use_retreat_analysis': True,
            'use_ko_math': False,
            'use_prize_strategy': False,
            'use_lethal_check': False,
            'use_weakness_aware': True,
            'use_board_eval': True,
            'use_evolution_priority': True,
            'use_ability_eval': False,
            'use_anti_lethal': False,
            'use_action_reordering': False,
            'use_smart_retreat': False,
            'use_energy_planning': True,
            'use_prize_tracking': False,
        },
        'hard': {
            'random_factor': 0.03,
            'mistake_chance': 0.01,
            'use_context': True,
            'use_energy_commitment': True,
            'use_trainer_registry': True,
            'use_retreat_analysis': True,
            'use_ko_math': True,
            'use_prize_strategy': True,
            'use_lethal_check': True,
            'use_weakness_aware': True,
            'use_board_eval': True,
            'use_evolution_priority': True,
            'use_ability_eval': True,
            'use_anti_lethal': False,
            'use_action_reordering': False,
            'use_smart_retreat': True,
            'use_energy_planning': True,
            'use_prize_tracking': True,
        },
        'ultra': {
            'random_factor': 0.0,
            'mistake_chance': 0.0,
            'use_context': True,
            'use_energy_commitment': True,
            'use_trainer_registry': True,
            'use_retreat_analysis': True,
            'use_ko_math': True,
            'use_prize_strategy': True,
            'use_lethal_check': True,
            'use_weakness_aware': True,
            'use_board_eval': True,
            'use_evolution_priority': True,
            'use_ability_eval': True,
            'use_anti_lethal': True,
            'use_action_reordering': True,
            'use_smart_retreat': True,
            'use_energy_planning': True,
            'use_prize_tracking': True,
        },
    }

    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty
        # Per-player difficulty overrides (for bot-vs-bot with different levels)
        self.player_difficulties: dict[str, str] = {}
        self._energy_plans: dict[str, EnergyPlan] = {}
        self._current_context: Optional[TurnContext] = None

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
    #  TURN CONTEXT
    # ══════════════════════════════════════════════════════════════

    def _build_turn_context(self, player_id: str, state: GameState) -> TurnContext:
        """Compute board analysis for the current turn."""
        ctx = TurnContext()
        energy_system = PokemonEnergySystem(state)
        combat_mgr = PokemonCombatManager(state)

        # My state
        ctx.my_active = self._get_active(state, player_id)
        ctx.my_bench = self._get_bench(state, player_id)

        # Categorize hand
        for card_id in self._get_hand(state, player_id):
            obj = state.objects.get(card_id)
            if not obj:
                continue
            types = obj.characteristics.types if obj.characteristics else set()
            if CardType.ENERGY in types:
                ctx.my_hand_energy.append(card_id)
            elif CardType.POKEMON in types:
                if obj.card_def and obj.card_def.evolves_from:
                    ctx.my_hand_evolutions.append(card_id)
                else:
                    ctx.my_hand_basics.append(card_id)
            elif CardType.SUPPORTER in types:
                ctx.my_hand_supporters.append(card_id)
            elif CardType.ITEM in types or CardType.POKEMON_TOOL in types:
                ctx.my_hand_items.append(card_id)
                if obj.card_def and obj.card_def.name == 'Switch':
                    ctx.has_switch_in_hand = True

        player = state.players.get(player_id)
        ctx.my_prizes_remaining = player.prizes_remaining if player else 6

        # Opponent state
        ctx.opp_id = self._opponent_id(state, player_id) or ''
        if ctx.opp_id:
            ctx.opp_active = self._get_active(state, ctx.opp_id)
            ctx.opp_bench = self._get_bench(state, ctx.opp_id)
            opp_player = state.players.get(ctx.opp_id)
            ctx.opp_prizes_remaining = opp_player.prizes_remaining if opp_player else 6
            opp_hand = state.zones.get(f"hand_{ctx.opp_id}")
            ctx.opp_hand_size = len(opp_hand.objects) if opp_hand else 0

        # Can we KO their active?
        if ctx.my_active and ctx.opp_active:
            opp_obj = state.objects.get(ctx.opp_active)
            if opp_obj:
                opp_remaining = self._remaining_hp(opp_obj)
                for attack in combat_mgr.get_available_attacks(ctx.my_active):
                    dmg = attack.get('damage', 0)
                    if dmg > 0:
                        final_dmg = combat_mgr.calculate_damage(
                            ctx.my_active, ctx.opp_active, dmg)
                        if final_dmg >= opp_remaining:
                            ctx.can_ko_active = True
                            ctx.ko_attack_info = {
                                'attack_index': attack.get('_index', 0),
                                'damage': final_dmg,
                            }
                            break

        # Can opponent KO us?
        if ctx.my_active and ctx.opp_active:
            my_obj = state.objects.get(ctx.my_active)
            opp_obj = state.objects.get(ctx.opp_active)
            if my_obj and opp_obj and opp_obj.card_def:
                my_remaining = self._remaining_hp(my_obj)
                max_dmg = 0
                # Use get_available_attacks to only consider affordable attacks
                for attack in combat_mgr.get_available_attacks(ctx.opp_active):
                    dmg = attack.get('damage', 0)
                    if dmg > 0:
                        final_dmg = combat_mgr.calculate_damage(
                            ctx.opp_active, ctx.my_active, dmg)
                        max_dmg = max(max_dmg, final_dmg)
                ctx.opp_estimated_max_damage = max_dmg
                if max_dmg >= my_remaining:
                    ctx.opp_can_ko_me = True

        # Weakness checks
        if ctx.my_active and ctx.opp_active:
            my_obj = state.objects.get(ctx.my_active)
            opp_obj = state.objects.get(ctx.opp_active)
            if my_obj and my_obj.card_def and opp_obj and opp_obj.card_def:
                if (opp_obj.card_def.pokemon_type and
                        my_obj.card_def.weakness_type == opp_obj.card_def.pokemon_type):
                    ctx.my_weakness_exposed = True
                if (my_obj.card_def.pokemon_type and
                        opp_obj.card_def.weakness_type == my_obj.card_def.pokemon_type):
                    ctx.their_weakness_exposed = True

        # Evolution map: pokemon_name -> [evo_card_ids_in_hand]
        all_mine = ([ctx.my_active] if ctx.my_active else []) + ctx.my_bench
        for pkm_id in all_mine:
            pkm = state.objects.get(pkm_id)
            if not pkm:
                continue
            for evo_id in ctx.my_hand_evolutions:
                evo = state.objects.get(evo_id)
                if evo and evo.card_def and evo.card_def.evolves_from == pkm.name:
                    ctx.evolution_map.setdefault(pkm.name, []).append(evo_id)

        # Energy needs per Pokemon
        for pkm_id in all_mine:
            pkm = state.objects.get(pkm_id)
            if not pkm or not pkm.card_def:
                continue
            attached = energy_system.get_attached_energy(pkm_id)
            total_attached = energy_system.get_total_energy(pkm_id)
            attacks_ready = []
            closest_gap = 999
            best_ready_dmg = 0
            typed_needs: dict[str, int] = {}
            for i, attack in enumerate(pkm.card_def.attacks or []):
                cost = attack.get('cost', [])
                if energy_system.can_pay_cost(pkm_id, cost):
                    attacks_ready.append(i)
                    best_ready_dmg = max(best_ready_dmg, attack.get('damage', 0))
                total_cost = sum(c.get('count', 0) for c in cost)
                gap = max(0, total_cost - total_attached)
                closest_gap = min(closest_gap, gap)
                for req in cost:
                    etype = req.get('type', 'C')
                    count = req.get('count', 0)
                    if etype != 'C':
                        have = attached.get(etype, 0)
                        still_need = max(0, count - have)
                        if still_need > 0:
                            typed_needs[etype] = max(
                                typed_needs.get(etype, 0), still_need)
            ctx.energy_needs[pkm_id] = {
                'typed_needs': typed_needs,
                'attacks_ready': attacks_ready,
                'best_ready_damage': best_ready_dmg,
                'closest_gap': closest_gap if closest_gap < 999 else 0,
            }

        # Prize gap and game phase
        ctx.prize_gap = ctx.opp_prizes_remaining - ctx.my_prizes_remaining
        if ctx.my_prizes_remaining <= 2:
            ctx.game_phase = 'late'
        elif ctx.my_prizes_remaining <= 4:
            ctx.game_phase = 'mid'
        else:
            ctx.game_phase = 'early'

        # Retreat urgency
        if ctx.my_active:
            ctx.retreat_urgency = self._compute_retreat_urgency(
                ctx.my_active, ctx, state)

        return ctx

    def _compute_retreat_urgency(self, active_id: str, ctx: TurnContext,
                                 state: GameState) -> float:
        """Compute urgency (0-100) for retreating the active Pokemon."""
        active = state.objects.get(active_id)
        if not active:
            return 0.0

        urgency = 0.0

        # Can't attack at all
        combat_mgr = PokemonCombatManager(state)
        if not combat_mgr.get_available_attacks(active_id):
            urgency += 40.0

        # Status conditions
        if 'paralyzed' in active.state.status_conditions:
            urgency += 45.0
        elif 'asleep' in active.state.status_conditions:
            urgency += 30.0
        elif 'confused' in active.state.status_conditions:
            urgency += 15.0
        if 'poisoned' in active.state.status_conditions:
            urgency += 10.0
        if 'burned' in active.state.status_conditions:
            urgency += 10.0

        # Opponent can KO me next turn
        if ctx.opp_can_ko_me:
            urgency += 35.0
            if active.card_def and active.card_def.is_ex:
                urgency += 20.0

        # Weakness exposed
        if ctx.my_weakness_exposed:
            urgency += 15.0

        # Very low HP
        remaining = self._remaining_hp(active)
        max_hp = self._max_hp(active)
        if max_hp > 0 and remaining <= max_hp * 0.15:
            urgency += 25.0

        # Defensive mode: boost retreat urgency to protect from lethal
        if ctx.defensive_mode:
            urgency += 20.0

        return min(100.0, urgency)

    # ══════════════════════════════════════════════════════════════
    #  TURN EXECUTION
    # ══════════════════════════════════════════════════════════════

    async def take_turn(self, player_id: str, state: GameState, game) -> list[Event]:
        """
        Execute a full Pokemon TCG turn for the AI.

        Flow: context -> lethal check -> anti-lethal -> normal phases -> energy plan update
        """
        events: list[Event] = []
        turn_mgr = getattr(game, 'turn_manager', None)
        settings = self._get_settings(player_id)

        def _game_over() -> bool:
            return hasattr(game, 'is_game_over') and game.is_game_over()

        # Step 0: Build context
        if settings.get('use_context'):
            self._current_context = self._build_turn_context(player_id, state)
        else:
            self._current_context = None

        # Step 1: LETHAL CHECK — before anything else
        if settings.get('use_lethal_check') and self._current_context:
            lethal = self._check_lethal(self._current_context, state, player_id)
            if lethal:
                lethal_events = await self._execute_lethal_sequence(
                    lethal, player_id, state, game)
                self._current_context = None
                return lethal_events

        # Step 2: ANTI-LETHAL — go defensive if opponent can win
        if settings.get('use_anti_lethal') and self._current_context:
            if self._opponent_near_lethal(self._current_context, state, player_id):
                self._current_context.defensive_mode = True

        # Step 3: Normal turn phases
        max_actions = 30
        context_dirty = False

        for _ in range(max_actions):
            if _game_over():
                break

            # Rebuild context if hand changed significantly
            if context_dirty and settings.get('use_context'):
                self._current_context = self._build_turn_context(
                    player_id, state)
                context_dirty = False

            action_taken = False

            # 1. Use Abilities
            ability_events = self._do_abilities(player_id, state, turn_mgr)
            if ability_events:
                events.extend(ability_events)
                action_taken = True
                if _game_over():
                    break

            # 2. Play Supporter (1 per turn)
            supporter_events = self._do_play_supporter(
                player_id, state, turn_mgr)
            if supporter_events:
                events.extend(supporter_events)
                action_taken = True
                context_dirty = True  # Hand changed (draw effects)
                if _game_over():
                    break

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
                    break

            # 7. Retreat if favorable
            retreat_events = self._do_retreat(player_id, state, turn_mgr)
            if retreat_events:
                events.extend(retreat_events)
                action_taken = True

            if not action_taken:
                break

        # 8. Attack (ends the turn)
        if not _game_over():
            attack_events = await self._do_attack(player_id, state, game)
            events.extend(attack_events)

        # Step 4: Update energy plan for next turn
        if settings.get('use_energy_commitment'):
            self._update_energy_plan(player_id, state)

        self._current_context = None
        return events

    # ══════════════════════════════════════════════════════════════
    #  LETHAL DETECTION + ANTI-LETHAL
    # ══════════════════════════════════════════════════════════════

    def _check_lethal(self, ctx: TurnContext, state: GameState,
                      player_id: str) -> Optional[dict]:
        """Check if AI can win the game this turn. Returns lethal plan or None."""
        if ctx.my_prizes_remaining <= 0:
            return None

        combat_mgr = PokemonCombatManager(state)
        settings = self._get_settings(player_id)

        # Path 1: Direct KO of active
        if ctx.can_ko_active and ctx.opp_active:
            opp_obj = state.objects.get(ctx.opp_active)
            if opp_obj and opp_obj.card_def:
                prize_value = opp_obj.card_def.prize_count
                if ctx.my_prizes_remaining <= prize_value:
                    return {
                        'path': 1,
                        'attack_index': ctx.ko_attack_info['attack_index'],
                        'target_id': ctx.opp_active,
                    }

        # Path 2: Boss's Orders + KO
        player = state.players.get(player_id)
        if player and not player.supporter_played_this_turn:
            boss_card_id = None
            for card_id in ctx.my_hand_supporters:
                obj = state.objects.get(card_id)
                if obj and obj.card_def and obj.card_def.name == "Boss's Orders":
                    boss_card_id = card_id
                    break
            if boss_card_id and ctx.opp_bench and ctx.my_active:
                # Boss's Orders drags the weakest bench Pokemon
                worst_id = None
                worst_hp = 9999
                for pkm_id in ctx.opp_bench:
                    pkm = state.objects.get(pkm_id)
                    if pkm and pkm.card_def:
                        remaining = (pkm.card_def.hp or 0) - pkm.state.damage_counters * 10
                        if remaining < worst_hp:
                            worst_hp = remaining
                            worst_id = pkm_id
                if worst_id:
                    target = state.objects.get(worst_id)
                    if target and target.card_def:
                        prize_value = target.card_def.prize_count
                        if ctx.my_prizes_remaining <= prize_value:
                            for attack in combat_mgr.get_available_attacks(ctx.my_active):
                                dmg = attack.get('damage', 0)
                                if dmg > 0:
                                    final_dmg = combat_mgr.calculate_damage(
                                        ctx.my_active, worst_id, dmg)
                                    if final_dmg >= worst_hp:
                                        return {
                                            'path': 2,
                                            'attack_index': attack.get('_index', 0),
                                            'target_id': worst_id,
                                            'boss_card_id': boss_card_id,
                                        }

        # Path 3: Evolve/Energy first → KO (ultra only)
        if settings.get('use_action_reordering') and ctx.my_active and ctx.opp_active:
            active = state.objects.get(ctx.my_active)
            opp_obj = state.objects.get(ctx.opp_active)
            if active and opp_obj and active.card_def and opp_obj.card_def:
                opp_remaining = self._remaining_hp(opp_obj)
                prize_value = opp_obj.card_def.prize_count
                if ctx.my_prizes_remaining <= prize_value:
                    energy_system = PokemonEnergySystem(state)
                    turn_mgr_obj = getattr(state, '_game', None)
                    turn_mgr = getattr(turn_mgr_obj, 'turn_manager', None) if turn_mgr_obj else None

                    # Check if evolving enables a lethal attack
                    for evo_id in ctx.my_hand_evolutions:
                        evo = state.objects.get(evo_id)
                        if not evo or not evo.card_def:
                            continue
                        if evo.card_def.evolves_from != active.name:
                            continue
                        # Check legality
                        if turn_mgr and hasattr(turn_mgr, 'can_evolve'):
                            ok, _ = turn_mgr.can_evolve(ctx.my_active, evo_id)
                            if not ok:
                                continue
                        for i, attack in enumerate(evo.card_def.attacks or []):
                            dmg = attack.get('damage', 0)
                            if dmg <= 0:
                                continue
                            est_dmg = dmg
                            if (evo.card_def.pokemon_type and
                                    opp_obj.card_def.weakness_type == evo.card_def.pokemon_type):
                                est_dmg *= 2
                            if est_dmg >= opp_remaining:
                                cost = attack.get('cost', [])
                                if energy_system.can_pay_cost(ctx.my_active, cost):
                                    return {
                                        'path': 3,
                                        'attack_index': i,
                                        'target_id': ctx.opp_active,
                                        'evolve': (ctx.my_active, evo_id),
                                    }

                    # Check if attaching energy enables a lethal attack
                    if ctx.my_hand_energy and not player.energy_attached_this_turn:
                        for i, attack in enumerate(active.card_def.attacks or []):
                            dmg = attack.get('damage', 0)
                            cost = attack.get('cost', [])
                            if dmg <= 0:
                                continue
                            final_dmg = self._estimate_damage(
                                active, opp_obj, dmg, state)
                            if final_dmg < opp_remaining:
                                continue
                            # Already have energy for this attack?
                            if energy_system.can_pay_cost(ctx.my_active, cost):
                                continue  # Already lethal via Path 1
                            total_cost = sum(c.get('count', 0) for c in cost)
                            total_have = energy_system.get_total_energy(ctx.my_active)
                            if total_have + 1 >= total_cost:
                                return {
                                    'path': 3,
                                    'attack_index': i,
                                    'target_id': ctx.opp_active,
                                    'energy_first': True,
                                }

        return None

    async def _execute_lethal_sequence(self, lethal: dict, player_id: str,
                                       state: GameState, game) -> list[Event]:
        """Execute the winning sequence of actions."""
        events: list[Event] = []
        turn_mgr = getattr(game, 'turn_manager', None)

        if lethal['path'] == 2 and lethal.get('boss_card_id'):
            if turn_mgr and hasattr(turn_mgr, '_play_trainer'):
                boss_events = turn_mgr._play_trainer(
                    player_id, lethal['boss_card_id'], 'supporter')
                events.extend(boss_events)

        if lethal['path'] == 3:
            if lethal.get('evolve'):
                target_id, evo_id = lethal['evolve']
                if turn_mgr and hasattr(turn_mgr, 'evolve_pokemon'):
                    evo_events = turn_mgr.evolve_pokemon(target_id, evo_id)
                    events.extend(evo_events)
            if lethal.get('energy_first'):
                energy_events = self._do_attach_energy(
                    player_id, state, turn_mgr)
                events.extend(energy_events)

        # Execute the lethal attack
        attack_events = await self._do_attack(player_id, state, game)
        events.extend(attack_events)

        return events

    def _opponent_near_lethal(self, ctx: TurnContext, state: GameState,
                              player_id: str) -> bool:
        """Check if opponent could win next turn."""
        if ctx.opp_prizes_remaining > 2:
            return False
        if not ctx.opp_active or not ctx.my_active:
            return False
        my_obj = state.objects.get(ctx.my_active)
        if not my_obj or not my_obj.card_def:
            return False
        prize_value = my_obj.card_def.prize_count
        if ctx.opp_prizes_remaining <= prize_value and ctx.opp_can_ko_me:
            return True
        return False

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

        in_play = self._get_all_in_play(state, player_id)
        if not in_play:
            return []

        settings = self._get_settings(player_id)

        # Energy commitment mode: use multi-turn planning
        if settings.get('use_energy_commitment') and self._current_context:
            target_id = self._select_energy_target(
                self._current_context, state, player_id, energy_cards)
            if target_id:
                best_energy = self._pick_best_energy_for_target(
                    target_id, energy_cards, state)
                if best_energy and turn_mgr and hasattr(turn_mgr, '_attach_energy'):
                    return turn_mgr._attach_energy(
                        player_id, best_energy, target_id)

        # Greedy fallback: score each (energy, target) pair
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

    def _select_energy_target(self, ctx: TurnContext, state: GameState,
                              player_id: str, energy_cards: list[str]) -> Optional[str]:
        """Select the best Pokemon to attach energy to (multi-turn planning)."""
        energy_system = PokemonEnergySystem(state)

        # Priority 1: Lethal setup — attachment enables KO this turn
        if ctx.my_active and ctx.opp_active:
            active = state.objects.get(ctx.my_active)
            opp = state.objects.get(ctx.opp_active)
            if active and opp and active.card_def and opp.card_def:
                opp_remaining = self._remaining_hp(opp)
                for attack in (active.card_def.attacks or []):
                    dmg = attack.get('damage', 0)
                    cost = attack.get('cost', [])
                    if dmg <= 0:
                        continue
                    final_dmg = self._estimate_damage(active, opp, dmg, state)
                    if final_dmg >= opp_remaining:
                        if not energy_system.can_pay_cost(ctx.my_active, cost):
                            attached = energy_system.get_attached_energy(ctx.my_active)
                            for eid in energy_cards:
                                e_obj = state.objects.get(eid)
                                if e_obj:
                                    e_type = energy_system._get_energy_type(e_obj)
                                    test = dict(attached)
                                    test[e_type] = test.get(e_type, 0) + 1
                                    if self._can_pay_with(test, cost):
                                        return ctx.my_active

        # Priority 2: Follow existing plan
        plan = self._energy_plans.get(player_id)
        if plan and self._is_energy_plan_valid(plan, state):
            target = state.objects.get(plan.target_pokemon_id)
            if target:
                needs = ctx.energy_needs.get(plan.target_pokemon_id, {})
                typed_needs = needs.get('typed_needs', {})
                for eid in energy_cards:
                    e_obj = state.objects.get(eid)
                    if e_obj:
                        e_type = energy_system._get_energy_type(e_obj)
                        if e_type in typed_needs or not typed_needs:
                            return plan.target_pokemon_id

        # Priority 3: Evaluate new targets
        all_targets = ([ctx.my_active] if ctx.my_active else []) + ctx.my_bench
        best_id = None
        best_score = -999.0

        for pkm_id in all_targets:
            pkm = state.objects.get(pkm_id)
            if not pkm or not pkm.card_def:
                continue
            for i, attack in enumerate(pkm.card_def.attacks or []):
                score = self._score_investment_target(
                    pkm, attack, i, ctx, state)
                if score > best_score:
                    best_score = score
                    best_id = pkm_id
                    # Create/update energy plan
                    cost = attack.get('cost', [])
                    typed_needed = ''
                    for req in cost:
                        if req.get('type', 'C') != 'C':
                            typed_needed = req['type']
                            break
                    total_cost = sum(c.get('count', 0) for c in cost)
                    total_have = energy_system.get_total_energy(pkm_id)
                    turns = max(0, total_cost - total_have)
                    turn_num = getattr(state, 'turn_number', 0)
                    self._energy_plans[player_id] = EnergyPlan(
                        target_pokemon_id=pkm_id,
                        target_attack_index=i,
                        energy_type_needed=typed_needed,
                        turns_remaining=turns,
                        priority=score,
                        created_turn=turn_num,
                    )

        # Priority 4: Fallback to active
        if not best_id and ctx.my_active:
            return ctx.my_active

        return best_id

    def _score_investment_target(self, pokemon: 'GameObject', attack: dict,
                                 attack_index: int, ctx: TurnContext,
                                 state: GameState) -> float:
        """Score how good it is to invest energy in this Pokemon + attack combo."""
        energy_system = PokemonEnergySystem(state)

        damage = attack.get('damage', 0)
        cost = attack.get('cost', [])
        total_cost = sum(c.get('count', 0) for c in cost)
        total_have = energy_system.get_total_energy(pokemon.id)
        gap = max(0, total_cost - total_have)

        if total_cost == 0:
            return -10.0

        score = 0.0

        # Damage efficiency
        score += (damage / max(total_cost, 1)) * 3

        # Turns to online (closer = higher)
        score += max(0, (5 - gap)) * 10

        # Already invested: partially powered > starting fresh
        if total_have > 0 and gap > 0:
            score += total_have * 8

        # Already ready: lower priority (don't over-invest)
        if gap == 0:
            score -= 15.0

        # Weakness bonus
        if ctx.opp_active:
            opp = state.objects.get(ctx.opp_active)
            if opp and opp.card_def and pokemon.card_def:
                if (pokemon.card_def.pokemon_type and
                        opp.card_def.weakness_type == pokemon.card_def.pokemon_type):
                    score += 25.0

        # Active gets priority
        if pokemon.id == ctx.my_active:
            score += 15.0

        # EX risk: big attacks but prize penalty when behind
        if pokemon.card_def and pokemon.card_def.is_ex:
            score += 10.0
            if ctx.prize_gap < 0:
                score -= 10.0

        # Evolution potential: energy carries over
        if pokemon.name in ctx.evolution_map:
            score += 15.0

        # Late game: prioritize whoever can close the game
        if ctx.game_phase == 'late' and ctx.opp_active:
            opp = state.objects.get(ctx.opp_active)
            if opp and pokemon.card_def:
                opp_remaining = self._remaining_hp(opp)
                final_dmg = damage
                if (opp.card_def and pokemon.card_def.pokemon_type and
                        opp.card_def.weakness_type == pokemon.card_def.pokemon_type):
                    final_dmg *= 2
                if final_dmg >= opp_remaining:
                    score += 30.0

        return score

    def _pick_best_energy_for_target(self, target_id: str, energy_cards: list[str],
                                     state: GameState) -> Optional[str]:
        """Pick the best energy card to attach to the target."""
        target = state.objects.get(target_id)
        if not target or not target.card_def:
            return energy_cards[0] if energy_cards else None

        energy_system = PokemonEnergySystem(state)
        attached = energy_system.get_attached_energy(target_id)

        # Find what typed energy is needed
        typed_needs: dict[str, int] = {}
        for attack in (target.card_def.attacks or []):
            for req in attack.get('cost', []):
                etype = req.get('type', 'C')
                count = req.get('count', 0)
                if etype != 'C':
                    have = attached.get(etype, 0)
                    need = max(0, count - have)
                    if need > 0:
                        typed_needs[etype] = max(typed_needs.get(etype, 0), need)

        # Prefer matching typed energy
        for eid in energy_cards:
            e_obj = state.objects.get(eid)
            if e_obj:
                e_type = energy_system._get_energy_type(e_obj)
                if e_type in typed_needs:
                    return eid

        return energy_cards[0] if energy_cards else None

    def _can_pay_with(self, energy_counts: dict[str, int], cost: list[dict]) -> bool:
        """Check if energy_counts can pay the given cost."""
        available = dict(energy_counts)
        for req in cost:
            etype = req.get('type', 'C')
            count = req.get('count', 0)
            if etype == 'C':
                continue
            if available.get(etype, 0) < count:
                return False
            available[etype] -= count
        colorless_needed = sum(
            r.get('count', 0) for r in cost if r.get('type', 'C') == 'C')
        return sum(available.values()) >= colorless_needed

    def _is_energy_plan_valid(self, plan: EnergyPlan, state: GameState) -> bool:
        """Check if an energy plan is still valid."""
        target = state.objects.get(plan.target_pokemon_id)
        if not target:
            return False
        if target.zone not in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH):
            return False
        if not target.card_def:
            return False
        attacks = target.card_def.attacks or []
        if plan.target_attack_index >= len(attacks):
            return False
        energy_system = PokemonEnergySystem(state)
        cost = attacks[plan.target_attack_index].get('cost', [])
        if energy_system.can_pay_cost(target.id, cost):
            return False  # Plan completed
        return True

    def _update_energy_plan(self, player_id: str, state: GameState):
        """Update energy plan for next turn (invalidate if needed)."""
        plan = self._energy_plans.get(player_id)
        if plan and not self._is_energy_plan_valid(plan, state):
            del self._energy_plans[player_id]

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
        """Score a Trainer card using registry or text fallback."""
        settings = self._get_settings(player_id)
        name = card.card_def.name if card.card_def else ''

        if settings.get('use_trainer_registry') and self._current_context:
            scorer = TRAINER_SCORERS.get(name)
            if scorer:
                return scorer(self._current_context, state, player_id)

        return self._score_trainer_text_fallback(card, state, player_id)

    def _score_trainer_text_fallback(self, card: 'GameObject', state: GameState,
                                     player_id: str) -> float:
        """Text-based trainer scoring (original heuristic fallback)."""
        score = 10.0

        if not card.card_def:
            return score

        text = (card.card_def.text or '').lower()

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
                score -= 10.0

        # Energy retrieval / acceleration
        if 'energy' in text and ('attach' in text or 'hand' in text):
            score += 20.0

        # Switching effects
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
        if (not settings.get('use_retreat_analysis') and
                not settings.get('use_board_eval') and
                not settings.get('use_smart_retreat')):
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

        # Context-aware retreat analysis (medium+)
        if settings.get('use_retreat_analysis') and self._current_context:
            ctx = self._current_context
            urgency = ctx.retreat_urgency

            replacement_id, replacement_score = self._find_best_replacement(
                ctx, state, player_id)
            if not replacement_id:
                return []

            active_score = self._score_attacker(active, state, player_id)

            # Dynamic threshold by game phase
            phase_threshold = {'early': 20, 'mid': 12, 'late': 8}.get(
                ctx.game_phase, 15)
            energy_penalty = retreat_cost * 8
            if ctx.has_switch_in_hand:
                energy_penalty = 0  # Switch waives the energy cost

            # Urgency >= 50 forces retreat regardless
            if (urgency >= 50 or
                    replacement_score > active_score + phase_threshold + energy_penalty - urgency):
                if turn_mgr and hasattr(turn_mgr, '_retreat'):
                    return turn_mgr._retreat(player_id, replacement_id)
            return []

        # Fallback: original retreat logic
        active_score = self._score_attacker(active, state, player_id)

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

        energy_penalty = retreat_cost * 5.0
        threshold = 15.0 + energy_penalty
        forced = False

        can_atk, _ = can_attack(active_id, state)
        if not can_atk:
            forced = True

        if not forced:
            combat_mgr = PokemonCombatManager(state)
            available_attacks = combat_mgr.get_available_attacks(active_id)
            if not available_attacks:
                bench_pkm = state.objects.get(best_bench_id)
                if bench_pkm:
                    bench_attacks = combat_mgr.get_available_attacks(best_bench_id)
                    if bench_attacks:
                        forced = True

        if not forced and settings.get('use_ko_math'):
            remaining = self._remaining_hp(active)
            max_hp = self._max_hp(active)
            if max_hp > 0 and remaining <= max_hp * 0.2:
                if active.card_def and active.card_def.is_ex:
                    forced = True
                elif remaining <= 30:
                    forced = True

        if forced or best_bench_score > active_score + threshold:
            if turn_mgr and hasattr(turn_mgr, '_retreat'):
                return turn_mgr._retreat(player_id, best_bench_id)

        return []

    def _find_best_replacement(self, ctx: TurnContext, state: GameState,
                               player_id: str) -> tuple[Optional[str], float]:
        """Find best bench Pokemon to replace the active. Returns (id, score)."""
        settings = self._get_settings(player_id)
        best_id = None
        best_score = -999.0

        for pkm_id in ctx.my_bench:
            pkm = state.objects.get(pkm_id)
            if not pkm:
                continue
            score = self._score_attacker(pkm, state, player_id)

            # Sacrifice strategy: when behind >= 2 prizes, boost non-EX with
            # no energy as expendable stall candidates
            if (settings.get('use_prize_strategy') and ctx.prize_gap <= -2
                    and pkm.card_def and not pkm.card_def.is_ex):
                energy_count = len(pkm.state.attached_energy)
                if energy_count == 0:
                    score += 15.0

            if score > best_score:
                best_score = score
                best_id = pkm_id

        return best_id, best_score

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

                        # Check if this wins the game (last prizes)
                        if settings.get('use_prize_tracking') or settings.get('use_prize_strategy'):
                            player = state.players.get(player_id)
                            if player:
                                prize_value = opp.card_def.prize_count if opp.card_def else 1
                                if player.prizes_remaining <= prize_value:
                                    score += 100.0  # This wins the game!

                        # Prize strategy: target EX when behind
                        if settings.get('use_prize_strategy') and self._current_context:
                            if (self._current_context.prize_gap < 0 and
                                    opp.card_def and opp.card_def.is_ex):
                                score += 10.0

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
        if settings.get('random_factor', 0) >= 0.3:
            return random.choice(bench)

        # Build quick context for prize-aware promotion
        ctx = None
        if settings.get('use_context'):
            ctx = self._build_turn_context(player_id, state)

        # Score each bench Pokemon as a potential active
        scored = []
        for pkm_id in bench:
            pkm = state.objects.get(pkm_id)
            if not pkm:
                continue
            score = self._score_attacker(pkm, state, player_id)

            # Prize-aware: prefer non-EX when close to losing
            if (settings.get('use_prize_strategy') and ctx
                    and ctx.prize_gap <= -2
                    and pkm.card_def and pkm.card_def.is_ex):
                score -= 20.0

            scored.append((pkm_id, score))

        if not scored:
            return bench[0]

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]
