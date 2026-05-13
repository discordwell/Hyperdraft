"""
Pokemon TCG AI — Scoring Functions

_score_attacker, _score_attack, _score_evolution, _score_energy_attachment,
_score_energy_target (via _score_investment_target), _score_retreat_urgency
(via _compute_retreat_urgency), _score_basic_play, _score_trainer,
_score_trainer_text_fallback, _evaluate_board, _estimate_damage, helpers.

All functions are free functions that accept the adapter as their first
argument so they can call adapter helpers and read difficulty settings.
"""
import random
from typing import Optional, TYPE_CHECKING

from src.engine.types import GameState, CardType, ZoneType
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_combat import PokemonCombatManager
from src.ai.pokemon.context import TurnContext, EnergyPlan
from src.ai.pokemon.trainers import TRAINER_SCORERS
from src.ai.pokemon.attacks import ATTACK_SCORERS, EVOLUTION_SCORERS

if TYPE_CHECKING:
    from src.engine.types import GameObject


# ══════════════════════════════════════════════════════════════
#  DAMAGE ESTIMATION
# ══════════════════════════════════════════════════════════════

def _estimate_damage(attacker: 'GameObject', defender: 'GameObject',
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


# ══════════════════════════════════════════════════════════════
#  RETREAT URGENCY
# ══════════════════════════════════════════════════════════════

def _compute_retreat_urgency(adapter, active_id: str, ctx: TurnContext,
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
    remaining = adapter._remaining_hp(active)
    max_hp = adapter._max_hp(active)
    if max_hp > 0 and remaining <= max_hp * 0.15:
        urgency += 25.0

    # Defensive mode: boost retreat urgency to protect from lethal
    if ctx.defensive_mode:
        urgency += 20.0

    return min(100.0, urgency)


# ══════════════════════════════════════════════════════════════
#  ATTACKER SCORING
# ══════════════════════════════════════════════════════════════

def _score_attacker(adapter, pokemon: 'GameObject', state: GameState,
                    player_id: str) -> float:
    """Score how effective this Pokemon is as the active attacker."""
    score = 0.0
    settings = adapter._get_settings(player_id)

    if not pokemon.card_def:
        return score

    remaining = adapter._remaining_hp(pokemon)
    max_hp = adapter._max_hp(pokemon)

    # HP score: survivability
    score += remaining / 10.0

    # Attack availability and damage output
    energy_system = PokemonEnergySystem(state)
    combat_mgr = PokemonCombatManager(state)
    available_attacks = combat_mgr.get_available_attacks(pokemon.id)

    if available_attacks:
        best_damage = max(a.get('damage', 0) for a in available_attacks)
        score += best_damage / 5.0
        if settings.get('use_attack_pressure'):
            opp_id = adapter._opponent_id(state, player_id)
            opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
            best_effective = best_damage
            if opp_active_id:
                opp = state.objects.get(opp_active_id)
                if opp:
                    best_effective = max(
                        _estimate_damage(pokemon, opp, a.get('damage', 0), state)
                        for a in available_attacks
                    )
                    if best_effective >= adapter._remaining_hp(opp):
                        score += 25.0
            score += best_effective / 4.0
    else:
        score -= 20.0  # Can't attack = bad active
        if settings.get('use_attack_pressure'):
            score -= 35.0

    # Status conditions
    if 'paralyzed' in pokemon.state.status_conditions:
        score -= 30.0
    if 'asleep' in pokemon.state.status_conditions:
        score -= 20.0
    if 'confused' in pokemon.state.status_conditions:
        score -= 10.0

    # Medium+: weakness matchup
    if settings['use_weakness_aware']:
        opp_id = adapter._opponent_id(state, player_id)
        opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
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
        opp_id = adapter._opponent_id(state, player_id)
        opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
        if opp_active_id:
            opp = state.objects.get(opp_active_id)
            if opp:
                opp_remaining = adapter._remaining_hp(opp)
                for attack in available_attacks:
                    dmg = attack.get('damage', 0)
                    # Factor in weakness
                    final_dmg = _estimate_damage(pokemon, opp, dmg, state)
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


# ══════════════════════════════════════════════════════════════
#  ATTACK SCORING
# ══════════════════════════════════════════════════════════════

def _score_attack(adapter, attacker: 'GameObject', attack: dict,
                  state: GameState, player_id: str) -> float:
    """Score how good this attack choice is."""
    score = 0.0
    settings = adapter._get_settings(player_id)

    damage = attack.get('damage', 0)
    score += damage / 5.0  # Base: more damage is better
    final_damage = damage
    opp = None
    opp_remaining: Optional[int] = None
    prize_value = 1
    winning_ko = False

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
        opp_id = adapter._opponent_id(state, player_id)
        opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
        if opp_active_id and damage > 0:
            opp = state.objects.get(opp_active_id)
            if opp:
                final_dmg = _estimate_damage(attacker, opp, damage, state)
                final_damage = final_dmg
                # Replace raw damage score with effective damage score
                score = score - damage / 5.0 + final_dmg / 5.0

    # Hard+: KO math
    if settings['use_ko_math'] and damage > 0:
        opp_id = adapter._opponent_id(state, player_id)
        opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
        if opp_active_id:
            opp = state.objects.get(opp_active_id)
            if opp:
                opp_remaining = adapter._remaining_hp(opp)
                final_dmg = _estimate_damage(attacker, opp, damage, state)
                final_damage = final_dmg
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
                                winning_ko = True
                                score += 100.0  # This wins the game!

                    # Prize strategy: target EX when behind
                    if settings.get('use_prize_strategy') and adapter._current_context:
                        if (adapter._current_context.prize_gap < 0 and
                                opp.card_def and opp.card_def.is_ex):
                            score += 10.0

    # Codex: prefer efficient prize-taking damage over wasteful overkill, and
    # be much stricter about attacks that spend attached Energy unless they
    # take prizes immediately.
    if settings.get('use_resource_conservation') and damage > 0:
        if opp is None:
            opp_id = adapter._opponent_id(state, player_id)
            opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
            opp = state.objects.get(opp_active_id) if opp_active_id else None
        if opp:
            if opp_remaining is None:
                opp_remaining = adapter._remaining_hp(opp)
            final_damage = _estimate_damage(attacker, opp, damage, state)
            useful_damage = min(final_damage, max(0, opp_remaining))
            score = score - final_damage / 5.0 + useful_damage / 4.0
            if opp_remaining > 0 and final_damage > opp_remaining:
                score -= min(8.0, (final_damage - opp_remaining) / 20.0)
            if final_damage >= opp_remaining:
                prize_value = opp.card_def.prize_count if opp.card_def else 1
                score += prize_value * 8.0
                player = state.players.get(player_id)
                winning_ko = bool(player and player.prizes_remaining <= prize_value)

        text_discard_penalty = 0.0
        if 'discard all energy' in attack_text:
            text_discard_penalty = 18.0
        elif 'discard 2 energy' in attack_text or 'discard two energy' in attack_text:
            text_discard_penalty = 14.0
        elif 'discard an energy' in attack_text or 'discard 1 energy' in attack_text:
            text_discard_penalty = 7.0

        if text_discard_penalty:
            if winning_ko:
                text_discard_penalty *= 0.1
            elif opp_remaining is not None and final_damage >= opp_remaining:
                text_discard_penalty *= 0.35
            score -= text_discard_penalty

    if settings.get('use_attack_pressure') and damage > 0:
        if opp is None:
            opp_id = adapter._opponent_id(state, player_id)
            opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
            opp = state.objects.get(opp_active_id) if opp_active_id else None
        if opp:
            if opp_remaining is None:
                opp_remaining = adapter._remaining_hp(opp)
            final_damage = _estimate_damage(attacker, opp, damage, state)
            if final_damage < opp_remaining:
                score += final_damage / 10.0
                if opp_remaining - final_damage <= 80:
                    score += 10.0
            else:
                score += 12.0

        library = state.zones.get(f"library_{player_id}")
        library_count = len(library.objects) if library else 0
        if 'draw' in attack_text:
            if library_count <= 6:
                score -= 60.0
            elif library_count <= 12:
                score -= 30.0

    if (settings.get('use_prize_strategy') or settings.get('use_resource_conservation')):
        library = state.zones.get(f"library_{player_id}")
        library_count = len(library.objects) if library else 0
        draw_amount = 0
        if 'draw 7' in attack_text:
            draw_amount = 7
        elif 'draw 4' in attack_text:
            draw_amount = 4
        elif 'draw 3' in attack_text:
            draw_amount = 3
        elif 'draw 2' in attack_text:
            draw_amount = 2
        elif 'draw' in attack_text:
            draw_amount = 1
        if draw_amount:
            remaining_after = library_count - draw_amount
            if remaining_after < 0:
                score -= 120.0
            elif remaining_after <= 1:
                score -= 70.0
            elif library_count <= 6:
                score -= 35.0

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

    # Card-name-aware bias (set-specific scorers in src/ai/pokemon/attacks.py).
    # Additive — runs *after* the generic logic so it tunes rather than
    # replacing. ATTACK_SCORERS key = (card_name, attack_name).
    if attacker.card_def:
        card_name = attacker.card_def.name
        attack_name = attack.get('name', '')
        scorer = ATTACK_SCORERS.get((card_name, attack_name))
        if scorer:
            try:
                score += scorer(adapter, attacker, attack, state, player_id)
            except Exception:
                pass
        # Bias preset multipliers (POKEMON_BIAS_PRESETS in biases.py).
        # Scales the final score by the active preset's per-card +
        # global_attack_pressure multipliers.
        try:
            from src.ai.pokemon.biases import apply_attack_bias
            preset = adapter.get_bias_preset(player_id)
            score = apply_attack_bias(preset, card_name, attack_name, score)
        except Exception:
            pass

    return score


# ══════════════════════════════════════════════════════════════
#  EVOLUTION SCORING
# ══════════════════════════════════════════════════════════════

def _score_evolution(adapter, base: 'GameObject', evolution: 'GameObject',
                     state: GameState, player_id: str) -> float:
    """Score how good it is to evolve this Pokemon now."""
    score = 20.0  # Evolving is generally good

    settings = adapter._get_settings(player_id)

    if not evolution.card_def:
        return score

    # HP increase
    old_hp = adapter._max_hp(base)
    new_hp = evolution.card_def.hp or 0
    hp_gain = new_hp - old_hp
    score += hp_gain / 10.0

    # Better attacks
    for attack in (evolution.card_def.attacks or []):
        damage = attack.get('damage', 0)
        score += damage / 20.0

    # Active Pokemon benefits more from evolving (immediate impact)
    active_id = adapter._get_active(state, player_id)
    if active_id and base.id == active_id:
        score += 15.0

    # Damaged Pokemon benefits from HP increase (evolution keeps counters)
    if base.state.damage_counters > 0:
        remaining_after = new_hp - base.state.damage_counters * 10
        if remaining_after > 0 and adapter._remaining_hp(base) <= old_hp * 0.3:
            score += 10.0  # Was about to die, now has more room

    # Hard+: check if evolution has weakness advantage against opponent
    if settings['use_weakness_aware']:
        opp_active_id = adapter._get_active(
            state, adapter._opponent_id(state, player_id) or '')
        if opp_active_id:
            opp = state.objects.get(opp_active_id)
            if opp and opp.card_def and evolution.card_def.pokemon_type:
                if opp.card_def.weakness_type == evolution.card_def.pokemon_type:
                    score += 15.0  # We hit weakness

    # Card-name-aware evolution bias. Additive — runs after the generic
    # evolution logic. EVOLUTION_SCORERS key = evolution card name.
    name = evolution.card_def.name if evolution.card_def else ''
    scorer = EVOLUTION_SCORERS.get(name)
    if scorer:
        try:
            score += scorer(adapter, base, evolution, state, player_id)
        except Exception:
            pass

    # Bias preset multiplier (POKEMON_BIAS_PRESETS).
    if name:
        try:
            from src.ai.pokemon.biases import apply_evolution_bias
            preset = adapter.get_bias_preset(player_id)
            score = apply_evolution_bias(preset, name, score)
        except Exception:
            pass

    return score


# ══════════════════════════════════════════════════════════════
#  BASIC PLAY SCORING
# ══════════════════════════════════════════════════════════════

def _score_basic_play(adapter, card: 'GameObject', state: GameState,
                      player_id: str) -> float:
    """Score how valuable it is to bench this Basic Pokemon."""
    score = 10.0  # Base value: bench presence is good

    settings = adapter._get_settings(player_id)

    if not card.card_def:
        return score

    # Higher HP basics are more resilient
    hp = card.card_def.hp or 0
    score += hp / 20.0

    has_matching_evolution = False

    # Has evolutions in hand? Prioritize benching the base
    if settings['use_evolution_priority']:
        hand = adapter._get_hand(state, player_id)
        for cid in hand:
            evo = state.objects.get(cid)
            if evo and evo.card_def and evo.card_def.evolves_from == card.name:
                has_matching_evolution = True
                score += 25.0
                break

    # EX/V Pokemon: worth extra prizes if KO'd, but high HP
    if card.card_def.is_ex:
        score += 5.0  # Good stats, but risky (2 prizes)
        # In hard+, de-prioritize if we're behind on prizes
        if settings['use_prize_tracking']:
            opp_id = adapter._opponent_id(state, player_id)
            if opp_id:
                player = state.players.get(player_id)
                opponent = state.players.get(opp_id)
                if player and opponent:
                    if opponent.prizes_remaining <= card.card_def.prize_count:
                        score -= 70.0  # Do not expose the opponent's last prizes.
                    elif opponent.prizes_remaining <= 2:
                        score -= 20.0
                    elif player.prizes_remaining <= 2 and opponent.prizes_remaining > 2:
                        score -= 10.0

    # Has attacks that are immediately useful (low cost)
    for attack in (card.card_def.attacks or []):
        cost = attack.get('cost', [])
        total_cost = sum(c.get('count', 0) for c in cost)
        if total_cost <= 1:
            score += 5.0  # Can attack soon
            break

    if settings.get('use_setup_consistency'):
        bench_count = len(adapter._get_bench(state, player_id))
        ability_text = ''
        if card.card_def.ability:
            ability_text = (card.card_def.ability.get('text', '') or '').lower()
        card_text = ((card.card_def.text or '') + ' ' + ability_text).lower()

        if bench_count <= 1:
            score += 18.0
        elif bench_count <= 2:
            score += 8.0

        if 'draw' in card_text:
            score += 14.0
        if 'search' in card_text or 'put it into your hand' in card_text:
            score += 16.0
        if 'attach' in card_text and 'energy' in card_text:
            score += 12.0

        has_low_cost_attack = any(
            sum(req.get('count', 0) for req in attack.get('cost', [])) <= 1
            for attack in (card.card_def.attacks or [])
        )
        if bench_count >= 3 and not has_matching_evolution:
            if not ability_text and hp <= 90 and not has_low_cost_attack:
                score -= 12.0
        if bench_count >= 4 and not has_matching_evolution and not ability_text:
            score -= 8.0

    return score


# ══════════════════════════════════════════════════════════════
#  ENERGY ATTACHMENT SCORING
# ══════════════════════════════════════════════════════════════

def _score_energy_attachment(adapter, energy: 'GameObject', pokemon: 'GameObject',
                             state: GameState, player_id: str) -> float:
    """Score how good it is to attach this energy to this Pokemon."""
    score = 0.0
    settings = adapter._get_settings(player_id)

    if not pokemon.card_def:
        return score

    energy_system = PokemonEnergySystem(state)
    energy_type = energy_system._get_energy_type(energy)
    current_energy = energy_system.get_attached_energy(pokemon.id)
    total_current = energy_system.get_total_energy(pokemon.id)

    # Active Pokemon gets priority (can attack soonest)
    active_id = adapter._get_active(state, player_id)
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
        opp_id = adapter._opponent_id(state, player_id)
        opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
        if opp_active_id:
            opp = state.objects.get(opp_active_id)
            if opp and opp.card_def:
                opp_remaining = adapter._remaining_hp(opp)
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

    if settings.get('use_attack_pressure'):
        for attack in (pokemon.card_def.attacks or []):
            damage = attack.get('damage', 0)
            if damage <= 0:
                continue
            cost = attack.get('cost', [])
            total_needed = sum(req.get('count', 0) for req in cost)
            gap_after_attach = max(0, total_needed - total_current - 1)
            meaningful = damage >= 50
            if not meaningful and settings.get('use_ko_math'):
                opp_id = adapter._opponent_id(state, player_id)
                opp_active_id = adapter._get_active(state, opp_id or '') if opp_id else None
                opp = state.objects.get(opp_active_id) if opp_active_id else None
                meaningful = bool(opp and damage >= adapter._remaining_hp(opp))
            if not meaningful:
                continue
            if gap_after_attach == 0:
                if active_id and pokemon.id == active_id:
                    score += 35.0 + damage / 4.0
                else:
                    score += 18.0 + damage / 8.0
            elif gap_after_attach == 1:
                score += 8.0 + damage / 15.0

    return score


def _score_investment_target(adapter, pokemon: 'GameObject', attack: dict,
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

    if adapter._get_settings(getattr(pokemon, 'controller', None)).get('use_attack_pressure'):
        final_damage = damage
        meaningful_pressure = damage >= 50
        if ctx.opp_active:
            opp = state.objects.get(ctx.opp_active)
            if opp and pokemon.card_def:
                final_damage = adapter._estimate_damage(pokemon, opp, damage, state)
                remaining = adapter._remaining_hp(opp)
                if final_damage >= remaining:
                    score += 40.0
                    meaningful_pressure = True
                elif remaining - final_damage <= 80:
                    score += 14.0
        if meaningful_pressure:
            if pokemon.id == ctx.my_active:
                if gap == 1:
                    score += 55.0 + final_damage / 5.0
                elif gap == 2:
                    score += 24.0 + final_damage / 10.0
            else:
                if gap == 1:
                    score += 28.0 + final_damage / 8.0
                elif gap == 2 and ctx.my_active:
                    score += 12.0

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
            opp_remaining = adapter._remaining_hp(opp)
            final_dmg = damage
            if (opp.card_def and pokemon.card_def.pokemon_type and
                    opp.card_def.weakness_type == pokemon.card_def.pokemon_type):
                final_dmg *= 2
            if final_dmg >= opp_remaining:
                score += 30.0

    return score


# ══════════════════════════════════════════════════════════════
#  TRAINER SCORING
# ══════════════════════════════════════════════════════════════

def _score_trainer(adapter, card: 'GameObject', state: GameState,
                   player_id: str) -> float:
    """Score a Trainer card using registry or text fallback.

    Bias preset multipliers (`get_bias_preset(player_id)`) are applied
    AFTER the base scorer + attack-pressure / resource-conservation
    adjustments — so the preset scales the final number, not the
    intermediate.
    """
    settings = adapter._get_settings(player_id)
    name = card.card_def.name if card.card_def else ''

    if settings.get('use_trainer_registry') and adapter._current_context:
        scorer = TRAINER_SCORERS.get(name)
        if scorer:
            score = scorer(adapter._current_context, state, player_id)
            if settings.get('use_attack_pressure'):
                score = _adjust_trainer_for_attack_pressure(
                    adapter, card, state, player_id, score)
            if settings.get('use_resource_conservation'):
                score = _adjust_trainer_for_deck_risk(
                    adapter, card, state, player_id, score)
            return _apply_bias_trainer(adapter, name, score, player_id)

    score = _score_trainer_text_fallback(adapter, card, state, player_id)
    if settings.get('use_attack_pressure'):
        score = _adjust_trainer_for_attack_pressure(
            adapter, card, state, player_id, score)
    if settings.get('use_resource_conservation'):
        score = _adjust_trainer_for_deck_risk(
            adapter, card, state, player_id, score)
    return _apply_bias_trainer(adapter, name, score, player_id)


def _apply_bias_trainer(adapter, card_name: str, score: float,
                        player_id: str) -> float:
    """Apply the active bias preset's trainer multiplier."""
    try:
        from src.ai.pokemon.biases import apply_trainer_bias
        preset = adapter.get_bias_preset(player_id)
        return apply_trainer_bias(preset, card_name, score)
    except Exception:
        return score


def _adjust_trainer_for_attack_pressure(adapter, card: 'GameObject',
                                        state: GameState, player_id: str,
                                        score: float) -> float:
    """Codex-only boost for cards that turn a passive board into attacks."""
    if not card.card_def or not adapter._current_context:
        return score

    ctx = adapter._current_context
    name = card.card_def.name
    text = (card.card_def.text or '').lower()
    active_ready = bool(
        ctx.my_active and ctx.energy_needs.get(ctx.my_active, {}).get('attacks_ready')
    )
    active_gap = (
        ctx.energy_needs.get(ctx.my_active, {}).get('closest_gap', 0)
        if ctx.my_active else 0
    )
    library = state.zones.get(f"library_{player_id}")
    library_count = len(library.objects) if library else 0

    if not active_ready:
        if name in {"Nest Ball", "Ultra Ball"}:
            score += 12.0
        if name == "Rare Candy" and ctx.my_hand_evolutions:
            score += 18.0
        if name == "Professor's Research" and library_count >= 16:
            score += 10.0
        if 'search your deck' in text:
            score += 6.0

    if active_gap <= 1 and active_gap > 0:
        if 'energy' in text and ('attach' in text or 'hand' in text):
            score += 14.0

    if ctx.opp_active and ctx.my_active:
        opp = state.objects.get(ctx.opp_active)
        active = state.objects.get(ctx.my_active)
        if opp and active and active.card_def:
            remaining = adapter._remaining_hp(opp)
            best_ready_damage = ctx.energy_needs.get(
                ctx.my_active, {}).get('best_ready_damage', 0)
            if 0 < best_ready_damage < remaining <= best_ready_damage + 40:
                if name == "Boss's Orders":
                    score -= 10.0
                elif name in {"Switch", "Potion"}:
                    score -= 4.0

    return score


def _adjust_trainer_for_deck_risk(adapter, card: 'GameObject',
                                  state: GameState, player_id: str,
                                  score: float) -> float:
    """Codex-only guardrail for Pokemon's deck-out loss condition."""
    if not card.card_def:
        return score

    library = state.zones.get(f"library_{player_id}")
    library_count = len(library.objects) if library else 0
    hand_size = len(adapter._get_hand(state, player_id))
    name = card.card_def.name
    text = (card.card_def.text or '').lower()

    player = state.players.get(player_id)
    draw_amount = 0
    if name == "Professor's Research":
        draw_amount = 7
        if hand_size >= 5:
            score -= 14.0
    elif name == "Iono":
        draw_amount = player.prizes_remaining if player else 0
    elif name == "Judge":
        draw_amount = 4
    elif 'draw 7' in text:
        draw_amount = 7
    elif 'draw 4' in text:
        draw_amount = 4
    elif 'draw 3' in text:
        draw_amount = 3
    elif 'draw 2' in text:
        draw_amount = 2

    if draw_amount:
        remaining_after = library_count - draw_amount
        if remaining_after <= 0:
            score -= 160.0
        elif remaining_after <= 3:
            score -= 110.0
        elif remaining_after <= 6:
            score -= 80.0
        elif remaining_after <= 10:
            score -= 35.0

    if name in {"Nest Ball", "Ultra Ball"} or 'search your deck' in text:
        if library_count <= 4:
            score -= 70.0
        elif library_count <= 8:
            score -= 50.0
        elif library_count <= 12:
            score -= 25.0

    if name == "Super Rod" and library_count <= 10:
        score += 30.0

    return score


def _score_trainer_text_fallback(adapter, card: 'GameObject', state: GameState,
                                 player_id: str) -> float:
    """Text-based trainer scoring (original heuristic fallback)."""
    score = 10.0

    if not card.card_def:
        return score

    text = (card.card_def.text or '').lower()

    # Draw cards are high priority
    if 'draw' in text:
        hand_size = len(adapter._get_hand(state, player_id))
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
        for pkm_id in adapter._get_all_in_play(state, player_id):
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
        in_play = adapter._get_all_in_play(state, player_id)
        if in_play:
            score += 15.0
        else:
            score -= 5.0

    return score


# ══════════════════════════════════════════════════════════════
#  BOARD EVALUATION
# ══════════════════════════════════════════════════════════════

def _evaluate_board(adapter, player_id: str, state: GameState) -> float:
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
    opp_id = adapter._opponent_id(state, player_id)
    if not opp_id:
        return 0.0

    player = state.players.get(player_id)
    opponent = state.players.get(opp_id)
    if not player or not opponent:
        return 0.0

    energy_system = PokemonEnergySystem(state)

    # HP comparison
    my_hp = sum(
        adapter._remaining_hp(state.objects[pid])
        for pid in adapter._get_all_in_play(state, player_id)
        if pid in state.objects
    )
    opp_hp = sum(
        adapter._remaining_hp(state.objects[pid])
        for pid in adapter._get_all_in_play(state, opp_id)
        if pid in state.objects
    )
    total_hp = my_hp + opp_hp
    hp_score = (my_hp - opp_hp) / total_hp if total_hp > 0 else 0.0

    # Board presence
    my_count = len(adapter._get_all_in_play(state, player_id))
    opp_count = len(adapter._get_all_in_play(state, opp_id))
    total_count = my_count + opp_count
    board_score = (my_count - opp_count) / max(total_count, 1)

    # Energy
    my_energy = sum(
        energy_system.get_total_energy(pid)
        for pid in adapter._get_all_in_play(state, player_id)
    )
    opp_energy = sum(
        energy_system.get_total_energy(pid)
        for pid in adapter._get_all_in_play(state, opp_id)
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
    my_hand = len(adapter._get_hand(state, player_id))
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
