"""
Pokemon TCG AI — Lethal Detection & Anti-Lethal

_check_lethal       — Can we win this turn?
_execute_lethal_sequence — Execute the winning action sequence
_opponent_near_lethal   — Can opponent win next turn?
"""
from typing import Optional, TYPE_CHECKING

from src.engine.types import GameState, Event
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_combat import PokemonCombatManager
from src.ai.pokemon.context import TurnContext

if TYPE_CHECKING:
    pass


def _check_lethal(adapter, ctx: TurnContext, state: GameState,
                  player_id: str) -> Optional[dict]:
    """Check if AI can win the game this turn. Returns lethal plan or None."""
    if ctx.my_prizes_remaining <= 0:
        return None

    combat_mgr = PokemonCombatManager(state)
    settings = adapter._get_settings(player_id)

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
            opp_remaining = adapter._remaining_hp(opp_obj)
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
                        final_dmg = adapter._estimate_damage(active, opp_obj, dmg, state)
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


async def _execute_lethal_sequence(adapter, lethal: dict, player_id: str,
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
            energy_events = adapter._do_attach_energy(player_id, state, turn_mgr)
            events.extend(energy_events)

    # Execute the lethal attack
    attack_events = await adapter._do_attack(player_id, state, game)
    events.extend(attack_events)

    return events


def _opponent_near_lethal(ctx: TurnContext, state: GameState,
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
