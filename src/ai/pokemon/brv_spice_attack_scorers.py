"""
BRV Spice Pack v1 — Per-Card Attack + Evolution Scorers

Card-name-aware bias hooks for the spice attacks and evolution lines
that the heuristic AI was previously ignoring. These augment the base
scoring in ``src/ai/pokemon/scoring.py``; the base scorers run first,
then these add (or subtract) bias.

What this fixes (pre-Phase-2 event trace findings):

- Mirko Vosk's Lost Recall fired 0× in 10 games — base scorer saw 70
  damage with a "Look at top 4" flavor text and ranked it below
  vanilla 80-damage attacks. The bias here boosts it when own LZ has
  capacity (≤4 LZ Pokemon) AND opp deck is fat (≥30 cards to mill).
- Aurelia ex's Battalion Mark fired 0× — base scorer saw 0 damage
  ("each Benched Pokemon may do 10 to opp Active") and ranked it dead
  last. Bias scales by bench count.
- Voidmage's Energy Drain fired 0× — 10 damage looks unspicy. Bias
  pushes it up because energy denial compounds.
- Jarad ex's Necrosurge — base scorer saw 80 base damage but couldn't
  predict the LZ-count payoff. Bias adds value per own LZ Pokemon.
- Obzedat ex's Spectral Decree — modal attack; base scorer didn't see
  the modes. Bias values it when (a) opp bench has KO-eligible target
  OR (b) we're behind on prizes.

Evolution scorers similarly bias the AI toward Mirko Vosk / Jarad ex /
Obzedat ex / Aurelia ex when their archetype prerequisites are met.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.ai.pokemon.attacks import attack_scorer, evolution_scorer

if TYPE_CHECKING:
    from src.engine.types import GameObject, GameState


# ══════════════════════════════════════════════════════════════
#  Shared helpers
# ══════════════════════════════════════════════════════════════


def _own_lz_pokemon_count(player_id: str, state) -> int:
    lost = state.zones.get('lost_zone')
    if not lost:
        return 0
    n = 0
    for cid in lost.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        from src.engine.types import CardType
        if CardType.POKEMON in obj.characteristics.types and obj.controller == player_id:
            n += 1
    return n


def _opp_deck_size(adapter, state, player_id: str) -> int:
    opp_id = adapter._opponent_id(state, player_id)
    if not opp_id:
        return 0
    lib = state.zones.get(f"library_{opp_id}")
    return len(lib.objects) if lib else 0


def _opp_bench_ko_eligible(adapter, state, player_id: str, hp_threshold: int = 30) -> bool:
    opp_id = adapter._opponent_id(state, player_id)
    if not opp_id:
        return False
    bench = state.zones.get(f"bench_{opp_id}")
    if not bench:
        return False
    for pid in bench.objects:
        obj = state.objects.get(pid) if pid else None
        if not obj or not obj.card_def:
            continue
        remaining = (obj.card_def.hp or 0) - (getattr(obj.state, 'damage_counters', 0) * 10)
        if 0 < remaining <= hp_threshold:
            return True
    return False


def _own_discard_pokemon_count(player_id: str, state) -> int:
    grave = state.zones.get(f"graveyard_{player_id}")
    if not grave:
        return 0
    from src.engine.types import CardType
    n = 0
    for cid in grave.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if CardType.POKEMON in obj.characteristics.types:
            n += 1
    return n


def _bench_count(player_id: str, state) -> int:
    bench = state.zones.get(f"bench_{player_id}")
    if not bench:
        return 0
    return sum(1 for o in bench.objects if o)


# ══════════════════════════════════════════════════════════════
#  ATTACK SCORERS
# ══════════════════════════════════════════════════════════════


@attack_scorer("Mirko Vosk, Mind Drinker", "Lost Recall")
def _bias_mirko_lost_recall(adapter, attacker, attack, state, player_id) -> float:
    """Build-around for LZ archetype. Hot when own LZ has room (≤4
    Pokemon) AND opp deck is fat (≥30) — milling pays off most when
    Jarad ex's Necrosurge counter is still ramping up.
    """
    lz_count = _own_lz_pokemon_count(player_id, state)
    deck_size = _opp_deck_size(adapter, state, player_id)
    bonus = 30.0  # base bias — promote above similar-damage attacks
    if 0 <= lz_count <= 4:
        bonus += 20.0
    if deck_size >= 30:
        bonus += 15.0
    elif deck_size <= 10:
        bonus -= 10.0  # opp near deck-out — diminishing returns
    return bonus


@attack_scorer("Aurelia, the Warleader ex", "Battalion Mark")
def _bias_aurelia_battalion_mark(adapter, attacker, attack, state, player_id) -> float:
    """Wide-board archetype anchor. The base scorer sees 0 damage and
    ranks this dead-last; we boost by bench count because each Benched
    Pokemon contributes 10 dmg counter to opp Active.
    """
    bench_n = _bench_count(player_id, state)
    if bench_n == 0:
        return -40.0  # no benched Pokemon means no damage
    bonus = 25.0  # base — recognize the modal damage source
    bonus += bench_n * 8.0  # +8 per bench Pokemon
    if bench_n >= 3:
        bonus += 20.0  # big-army payoff
    return bonus


@attack_scorer("Voidmage Apprentice", "Energy Drain")
def _bias_voidmage_energy_drain(adapter, attacker, attack, state, player_id) -> float:
    """Cheap energy-denial Basic — 10 damage looks unspicy but each
    successful drain compounds over the game. Bias up across the board,
    bigger when opp Active is leaning on a setup attack.
    """
    bonus = 18.0  # always-good for tempo
    opp_id = adapter._opponent_id(state, player_id)
    if opp_id:
        opp_active_id = adapter._get_active(state, opp_id)
        if opp_active_id:
            opp_active = state.objects.get(opp_active_id)
            if opp_active:
                attached = getattr(opp_active.state, 'attached_energy', []) or []
                # +5 per attached energy on opp Active (more to strip).
                bonus += len(attached) * 5.0
                if opp_active.card_def and opp_active.card_def.is_ex:
                    bonus += 10.0
    return bonus


@attack_scorer("Obzedat, Ghost Council ex", "Spectral Decree")
def _bias_obzedat_spectral_decree(adapter, attacker, attack, state, player_id) -> float:
    """Modal attack. Mode A KOs a bench Pokemon ≤30 HP; mode B prize-taxes.

    Hot when opp has KO-eligible bench (mode A's target exists) OR
    we're behind on prizes (mode B's tax matters more).
    """
    bonus = 20.0
    if _opp_bench_ko_eligible(adapter, state, player_id, hp_threshold=30):
        bonus += 30.0
    # Prize gap: we're behind = tax matters more.
    if adapter._current_context and adapter._current_context.prize_gap < 0:
        bonus += 15.0
    # Late-game KO finishers love this.
    if adapter._current_context and adapter._current_context.game_phase == 'late':
        bonus += 10.0
    return bonus


@attack_scorer("Jarad, Golgari Lich Lord ex", "Necrosurge")
def _bias_jarad_necrosurge(adapter, attacker, attack, state, player_id) -> float:
    """Payoff attack for the LZ-engine archetype. Base 80 damage + 2
    counters per LZ Pokemon. The base scorer can't see the LZ counter
    payoff; we add it explicitly.
    """
    lz_count = _own_lz_pokemon_count(player_id, state)
    bonus = 10.0
    bonus += lz_count * 6.0  # +6 per LZ Pokemon (≈ 20 dmg of value each)
    if lz_count >= 3:
        bonus += 15.0  # threshold bonus — LZ archetype "online"
    return bonus


@attack_scorer("Jarad, Golgari Lich Lord ex", "Lich's Bargain")
def _bias_jarad_lichs_bargain(adapter, attacker, attack, state, player_id) -> float:
    """Setup attack — moves a discard-pile Pokemon to LZ + draws 1.
    Hot when we have Pokemon in discard waiting AND haven't built up
    much LZ yet (sets up Necrosurge).
    """
    grave_pkm = _own_discard_pokemon_count(player_id, state)
    if grave_pkm == 0:
        return -10.0  # no Pokemon to feed LZ
    lz_count = _own_lz_pokemon_count(player_id, state)
    bonus = 15.0
    bonus += grave_pkm * 4.0  # more discard Pokemon = more LZ runway
    if lz_count <= 2:
        bonus += 10.0  # early LZ ramp — sets up Necrosurge later
    return bonus


@attack_scorer("Voidmage Apprentice", "*")  # fallback for any other Voidmage attacks
@attack_scorer("Jace, Memory Adept", "Mental Triage")
def _bias_jace_mental_triage(adapter, attacker, attack, state, player_id) -> float:
    """Discard an Item from opp hand; opp draws 1. Strong vs opp
    Item-heavy decks (Nest Ball, Rare Candy, etc.). The base scorer
    sees 30 damage as middling; we bias up because hand disruption
    compounds.
    """
    opp_id = adapter._opponent_id(state, player_id)
    if not opp_id:
        return 0.0
    opp_hand = state.zones.get(f"hand_{opp_id}")
    if not opp_hand:
        return 0.0
    from src.engine.types import CardType
    items_in_opp_hand = 0
    for cid in opp_hand.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if CardType.ITEM in obj.characteristics.types:
            items_in_opp_hand += 1
    if items_in_opp_hand == 0:
        return 0.0
    bonus = 12.0
    bonus += items_in_opp_hand * 6.0
    return bonus


# ══════════════════════════════════════════════════════════════
#  EVOLUTION SCORERS
# ══════════════════════════════════════════════════════════════


@evolution_scorer("Mirko Vosk, Mind Drinker")
def _bias_evolve_mirko(adapter, base, evolution, state, player_id) -> float:
    """Strong evolve-into-Mirko bias when the LZ archetype is starting
    to come online (we have <=5 LZ Pokemon and opp's deck is reachable
    to mill)."""
    lz = _own_lz_pokemon_count(player_id, state)
    deck = _opp_deck_size(adapter, state, player_id)
    bonus = 0.0
    if lz <= 5 and deck >= 30:
        bonus += 25.0
    elif lz >= 6:
        bonus -= 5.0  # already milled enough; Mirko less critical
    return bonus


@evolution_scorer("Jarad, Golgari Lich Lord ex")
def _bias_evolve_jarad(adapter, base, evolution, state, player_id) -> float:
    """Bias toward evolving to Jarad ex when our discard has Pokemon to
    feed Necrosurge with."""
    grave_pkm = _own_discard_pokemon_count(player_id, state)
    if grave_pkm >= 2:
        return 30.0
    if grave_pkm >= 1:
        return 15.0
    return 0.0  # no benefit yet; vanilla evolution score still works


@evolution_scorer("Obzedat, Ghost Council ex")
def _bias_evolve_obzedat(adapter, base, evolution, state, player_id) -> float:
    """Bias toward Obzedat ex when we're behind on prizes (the prize-tax
    mode B matters more) OR opp has bench KO-eligible (mode A targets)."""
    bonus = 0.0
    if adapter._current_context and adapter._current_context.prize_gap < 0:
        bonus += 20.0
    if _opp_bench_ko_eligible(adapter, state, player_id):
        bonus += 15.0
    return bonus


@evolution_scorer("Aurelia, the Warleader ex")
def _bias_evolve_aurelia(adapter, base, evolution, state, player_id) -> float:
    """Bias toward Aurelia ex when we have 3+ Bench Pokemon — that's
    when Battalion Mark turns into a multi-target ping."""
    bench_n = _bench_count(player_id, state)
    if bench_n >= 3:
        return 25.0
    if bench_n >= 2:
        return 10.0
    return -10.0  # too few bench Pokemon for the payoff


@evolution_scorer("Lazav, Dimir Mastermind ex")
def _bias_evolve_lazav(adapter, base, evolution, state, player_id) -> float:
    """Bias toward Lazav ex evolution. Iter 4 (item 4 from /ultra-loop
    next-pass): when the cross-turn opp-deck observation shows opp has
    NO Darkness-type attacker after turn 5+, Lazav ex's 280 HP becomes
    an effectively unkillable wall (Boros's max DPS is 80 — needs 4 hits
    + the wall heals 30 with one Potion). Bias up hard in that case.

    Without observation data (early turns), default to a small bonus
    since Lazav ex is the deck's primary win condition.
    """
    bonus = 5.0  # Lazav ex is always strong
    ctx = adapter._current_context
    if ctx is None:
        return bonus
    # Lazav ex's weakness type is Darkness ("D"). If opp hasn't shown
    # any Darkness attackers by turn 5+, the wall is online.
    if ctx.turn_number >= 5 and 'D' not in ctx.opp_observed_types:
        bonus += 25.0  # opp can't easily KO Lazav ex
    return bonus
