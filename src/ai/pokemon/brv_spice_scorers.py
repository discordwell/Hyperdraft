"""
BRV Spice Pack v1 — Per-Card Trainer Scorers

Card-name-aware bias functions for the 10 spice Trainers in Pokemon
Beyond Ravnica. Each function follows the standard ``@trainer_scorer``
signature ``(ctx: TurnContext, state: GameState, player_id: str) -> float``
and registers into ``src.ai.pokemon.trainers.TRAINER_SCORERS``.

Why these biases exist: pre-Phase-2 event traces showed several spice
Trainers were *never played* by the heuristic AI in 10 games because
the generic text-fallback scorer (`_score_trainer_text_fallback`)
either gave them generic mid scores OR couldn't detect their context
gating. These named scorers encode:

- "Don't play me when my effect has no target" (Negate the Negation
  without a Tool in play, Dimir Interrogation with empty opp hand).
- "Play me when my payoff is hot" (Cremate when hand has burnable cards
  AND own Lost Zone is empty so the LZ archetype is just starting).
- "Bias toward my archetype" (Pithing Drone when own Active is the
  primary attacker and lacks a Tool).

Phase 2 contract: these are *bias modifiers*. The text-fallback path
remains for cards without a named scorer. ``_score_trainer`` consults
the registry first, then applies attack-pressure / resource-conservation
adjustments downstream. So a bias of +30 here actually flows into the
attack-pressure pipeline and may grow further.

Imported by ``trainers.py`` so registration happens at module load.
"""

from __future__ import annotations

from src.engine.types import GameState, CardType
from src.ai.pokemon.context import TurnContext
from src.ai.pokemon.trainers import trainer_scorer


# ══════════════════════════════════════════════════════════════
#  Shared utilities
# ══════════════════════════════════════════════════════════════


def _opp_hand_objects(ctx: TurnContext, state: GameState) -> list:
    """Return the actual GameObjects sitting in opp's hand. ``ctx`` exposes
    only the count (info-asymmetry rule), but the *resolving* card peeks
    via state; AI bias gets the same peek for scoring symmetry."""
    if not ctx.opp_id:
        return []
    zone = state.zones.get(f"hand_{ctx.opp_id}")
    if not zone:
        return []
    return [state.objects.get(cid) for cid in zone.objects if state.objects.get(cid)]


def _opp_has_attached_tool(ctx: TurnContext, state: GameState) -> bool:
    """True if any opp Pokemon has a Tool attached."""
    for pid in [ctx.opp_active] + list(ctx.opp_bench):
        if not pid:
            continue
        obj = state.objects.get(pid)
        if obj and getattr(obj.state, 'attached_tool', None):
            return True
    return False


def _opp_poisoned_count(ctx: TurnContext, state: GameState) -> int:
    n = 0
    for pid in [ctx.opp_active] + list(ctx.opp_bench):
        if not pid:
            continue
        obj = state.objects.get(pid)
        if obj and 'poisoned' in (getattr(obj.state, 'status_conditions', None) or set()):
            n += 1
    return n


def _own_lost_zone_count(player_id: str, state: GameState) -> int:
    lost = state.zones.get('lost_zone')
    if not lost:
        return 0
    return sum(1 for cid in lost.objects
               if (state.objects.get(cid) and state.objects[cid].controller == player_id))


def _opp_bench_ko_eligible(ctx: TurnContext, state: GameState, hp_threshold: int = 30) -> bool:
    """True if opp has a benched Pokemon with effective HP <= threshold."""
    for pid in ctx.opp_bench:
        if not pid:
            continue
        obj = state.objects.get(pid)
        if not obj or not obj.card_def:
            continue
        remaining = (obj.card_def.hp or 0) - (getattr(obj.state, 'damage_counters', 0) * 10)
        if 0 < remaining <= hp_threshold:
            return True
    return False


def _opp_active_has_energy(ctx: TurnContext, state: GameState) -> bool:
    if not ctx.opp_active:
        return False
    obj = state.objects.get(ctx.opp_active)
    if not obj:
        return False
    return bool(getattr(obj.state, 'attached_energy', None))


# ══════════════════════════════════════════════════════════════
#  ITEMS
# ══════════════════════════════════════════════════════════════


@trainer_scorer("Dimir Interrogation")
def _score_dimir_interrogation(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Yank a Pokemon from opp hand to bottom of deck; opp draws 1.

    Strong when opp has a fat hand with Pokemon (we deny their evo line
    or backup attacker). Bad when opp hand is empty (nothing to target).
    """
    if ctx.opp_hand_size <= 0:
        return -50.0
    opp_hand = _opp_hand_objects(ctx, state)
    pokemon_in_hand = sum(
        1 for o in opp_hand
        if o and o.characteristics and CardType.POKEMON in o.characteristics.types
    )
    if pokemon_in_hand == 0:
        return -30.0
    score = 25.0
    if ctx.opp_hand_size >= 4:
        score += 15.0
    if pokemon_in_hand >= 2:
        score += 15.0
    # Early game when opp is setting up: extra value.
    if ctx.game_phase == 'early':
        score += 10.0
    return score


@trainer_scorer("Tox-Pawpsule")
def _score_tox_pawpsule(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Poison opp Active + place damage counters per opp Poisoned Pokemon.

    Always at least baseline good (free poison + damage). Big when we
    already have opp Pokemon poisoned (scaling bonus).
    """
    if not ctx.opp_active:
        return -20.0
    opp_active = state.objects.get(ctx.opp_active)
    if not opp_active:
        return -20.0
    if 'poisoned' in (getattr(opp_active.state, 'status_conditions', None) or set()):
        # Opp Active already poisoned — re-application is a no-op for the
        # status, but the scaling damage still lands.
        score = 10.0
    else:
        score = 25.0
    poisoned = _opp_poisoned_count(ctx, state)
    score += poisoned * 12.0  # +12 per existing Poisoned Pokemon
    # Defending mode bonus — passive damage chip while we stabilize.
    if ctx.defensive_mode:
        score += 8.0
    # iter3 fix (Pilot A "Tox-Pawpsule decisive on T10 — poisoned Reckoner
    # died to between-turn ticks without me attacking, exploiting Boros's
    # no-Switch retreat lock"). When opp Active can't easily switch out
    # (paralyzed OR no bench to retreat into), poison ticks are nearly free.
    opp_status = getattr(opp_active.state, 'status_conditions', None) or set()
    opp_locked = ('paralyzed' in opp_status) or (len([b for b in ctx.opp_bench if b]) == 0)
    if opp_locked:
        score += 15.0
    return score


@trainer_scorer("Cremate")
def _score_cremate(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Send up to 3 Pokemon/Energy from hand to Lost Zone (LZ-engine
    feeder). Strong when (a) hand has burnable cards AND (b) own LZ
    archetype needs feeding (Jarad ex's Necrosurge, Mirko Vosk synergy).
    """
    burnable = len(ctx.my_hand_energy) + len(ctx.my_hand_basics)
    if burnable < 2:
        return -25.0
    lz_count = _own_lost_zone_count(player_id, state)
    score = 15.0
    if burnable >= 3:
        score += 20.0
    # Big bonus if we're building toward Necrosurge (LZ count payoff) but
    # haven't quite arrived yet.
    if 0 <= lz_count <= 4:
        score += 15.0
    elif lz_count >= 5:
        # Already deep into LZ; marginal value, but still feeds Jarad.
        score += 5.0
    return score


@trainer_scorer("Negate the Negation")
def _score_negate_the_negation(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Discard opp Tools + mill opp deck-top to LZ per Tool removed.

    Hard-gated: useless if opp has no Tool attached. If they do, big
    value — disrupts their archetype AND feeds opp's library into LZ.
    """
    if not _opp_has_attached_tool(ctx, state):
        return -100.0
    score = 40.0
    # Pile on if opp has 2+ Tools (rare but possible with multi-tool
    # archetypes).
    tool_count = 0
    for pid in [ctx.opp_active] + list(ctx.opp_bench):
        if not pid:
            continue
        obj = state.objects.get(pid)
        if obj and getattr(obj.state, 'attached_tool', None):
            tool_count += 1
    if tool_count >= 2:
        score += 25.0
    return score


@trainer_scorer("Pithing Drone")
def _score_pithing_drone(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Attach a death-rattle energy-denial Tool. Strong when our Active
    is a fragile high-investment Pokemon (an ex without much HP buffer)
    and isn't already wearing a Tool.
    """
    if not ctx.my_active:
        return -20.0
    active = state.objects.get(ctx.my_active)
    if not active:
        return -20.0
    if getattr(active.state, 'attached_tool', None):
        return -50.0  # already has a Tool
    score = 12.0
    if active.card_def and active.card_def.is_ex:
        score += 25.0
    # Bigger when opp can plausibly KO us (deters their reach).
    if ctx.opp_can_ko_me:
        score += 20.0
    # Late game: ex-trading punishes mistakes; denial hurts more.
    if ctx.game_phase == 'late':
        score += 8.0
    return score


# ══════════════════════════════════════════════════════════════
#  SUPPORTERS
# ══════════════════════════════════════════════════════════════


@trainer_scorer("Niv-Mizzet's Quandary")
def _score_niv_mizzets_quandary(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Force opp to switch + move up to 2 of their energy to the new Active.

    Best when opp has a built-up bench Pokemon (forcing them to swap a
    powered attacker for an under-energy bench Pokemon). Mediocre when
    opp bench is empty (nothing to swap to).
    """
    if not ctx.opp_bench:
        return -40.0
    # Count opp bench Pokemon with attached energy — those are the
    # juicy swap targets.
    energized_bench = 0
    for pid in ctx.opp_bench:
        obj = state.objects.get(pid) if pid else None
        if obj and getattr(obj.state, 'attached_energy', []):
            energized_bench += 1
    score = 15.0
    if energized_bench >= 1:
        score += 30.0
    if energized_bench >= 2:
        score += 15.0
    # If opp Active is a key threat (ex), force-switching is even better.
    if ctx.opp_active:
        opp_active = state.objects.get(ctx.opp_active)
        if opp_active and opp_active.card_def and opp_active.card_def.is_ex:
            score += 20.0
    return score


@trainer_scorer("Sanguine Sacrament")
def _score_sanguine_sacrament(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Sac own Pokemon (+ attached) to LZ; heal 2 others fully.

    Strong when (a) we have a damaged Pokemon worth saving AND (b) we
    have a low-value bench Pokemon to sacrifice. Useless if all our
    Pokemon are full HP or we have nothing to sacrifice.
    """
    damaged_count = 0
    max_dmg_counters = 0
    sacrifice_candidate = False
    for pid in [ctx.my_active] + list(ctx.my_bench):
        if not pid:
            continue
        obj = state.objects.get(pid)
        if not obj or not obj.card_def:
            continue
        dmg = getattr(obj.state, 'damage_counters', 0) or 0
        if dmg > 0:
            damaged_count += 1
            max_dmg_counters = max(max_dmg_counters, dmg)
        # A "low value" sacrifice candidate: no attached energy AND not ex.
        if (not getattr(obj.state, 'attached_energy', None)
                and not obj.card_def.is_ex):
            sacrifice_candidate = True
    if damaged_count == 0:
        return -30.0
    if not sacrifice_candidate:
        return -15.0
    score = 5.0 + max_dmg_counters * 6.0  # more damage saved = more value
    if damaged_count >= 2:
        score += 15.0
    if ctx.defensive_mode:
        score += 10.0
    return score


@trainer_scorer("Jace, Memory Adept")
def _score_jace_memory_adept(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Note: Jace is a *Pokemon* (a Basic with an attack), NOT a Trainer.
    This entry exists because the AI's basic-play scorer may consult
    trainer scorers for some heuristic paths; if not, ignored.

    For coverage symmetry with the other spice cards.
    """
    return 8.0


@trainer_scorer("Tezzy's Test")
def _score_tezzys_test(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Modal Supporter: draw 3 / tutor Item / disrupt Trainer.

    Always has at least one good mode available, so baseline value is
    high. Best when:
    - hand is small (draw 3 most useful)
    - we have evolution lines that want Item tutoring
    - opp has setup Trainers in hand
    """
    my_hand_size = (len(ctx.my_hand_energy) + len(ctx.my_hand_basics) +
                    len(ctx.my_hand_evolutions) + len(ctx.my_hand_items) +
                    len(ctx.my_hand_supporters))
    score = 18.0
    if my_hand_size <= 3:
        score += 20.0
    # Tutor mode: useful if we have evolution lines waiting on Items.
    if ctx.my_hand_evolutions:
        score += 10.0
    # Disrupt mode: useful when opp hand is big and likely has Trainers.
    if ctx.opp_hand_size >= 4:
        score += 12.0
    return score


@trainer_scorer("Obzedat, Ghost Council ex")
def _score_obzedat_ex(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Note: Obzedat ex is a Pokemon, not a Trainer. This entry exists
    for symmetry — the basic-play / evolution scoring path consults
    TRAINER_SCORERS in some configurations. Real Obzedat ex tuning
    happens via the Phase 2b evolution scorer.
    """
    return 5.0


# ══════════════════════════════════════════════════════════════
#  Cards that are NOT Trainers but get a placeholder entry to
#  avoid the text-fallback misclassifying them (defensive only).
# ══════════════════════════════════════════════════════════════


@trainer_scorer("Mirko Vosk, Mind Drinker")
def _score_mirko_vosk(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Mirko is a Pokemon (Stage 1). The scorer is reached only if the
    text-fallback ever consults the registry for non-Trainer cards;
    returns a neutral score so it doesn't accidentally score as a
    Trainer."""
    return 5.0


@trainer_scorer("Voidmage Apprentice")
def _score_voidmage_apprentice(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Voidmage is a Pokemon (Basic). See Mirko comment."""
    return 5.0


@trainer_scorer("Aurelia, the Warleader ex")
def _score_aurelia_ex(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Aurelia ex is a Pokemon (Stage 2 ex). See Mirko comment."""
    return 5.0


@trainer_scorer("Jarad, Golgari Lich Lord ex")
def _score_jarad_ex(ctx: TurnContext, state: GameState, player_id: str) -> float:
    """Jarad ex is a Pokemon (Stage 2 ex). See Mirko comment."""
    return 5.0
