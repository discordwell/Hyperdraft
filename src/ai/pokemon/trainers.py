"""
Pokemon TCG AI — Trainer Scorer Registry

TRAINER_SCORERS dict + @trainer_scorer decorator + all named scorer functions.
Each function signature: (ctx: TurnContext, state: GameState, player_id: str) -> float
"""
from typing import Callable, TYPE_CHECKING

from src.engine.types import GameState, CardType
from src.engine.pokemon_combat import PokemonCombatManager
from src.ai.pokemon.context import TurnContext

if TYPE_CHECKING:
    pass


# ══════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════

TRAINER_SCORERS: dict[str, Callable] = {}


def trainer_scorer(name: str):
    """Register a scoring function for a trainer card by name."""
    def decorator(fn):
        TRAINER_SCORERS[name] = fn
        return fn
    return decorator


# ══════════════════════════════════════════════════════════════
#  SCORER FUNCTIONS
# ══════════════════════════════════════════════════════════════

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
