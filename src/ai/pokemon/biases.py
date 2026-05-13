"""
Pokemon TCG AI — Bias Presets

``POKEMON_BIAS_PRESETS`` is an orthogonal axis to ``difficulty``. Where
difficulty controls *capability* (mistake rate, planning depth,
heuristic feature flags), bias controls *style* (which archetype the AI
plays toward).

Each preset is a dict of multiplicative weights on the named scorer
registries (``TRAINER_SCORERS``, ``ATTACK_SCORERS``, ``EVOLUTION_SCORERS``).
A multiplier of 2.0 doubles the score; 0.0 zeroes it out; 1.0 is
neutral. Missing keys default to 1.0 (no change).

Schema (all keys optional — each preset overrides only what it needs):

  ``trainer_multipliers``:  dict[card_name, float]
  ``attack_multipliers``:   dict[(card_name, attack_name), float]
  ``evolution_multipliers`` dict[evolution_name, float]
  ``global_attack_pressure``: float — multiplier applied to all attack
                              scorers (boost aggression).
  ``global_trainer_bias``:    float — multiplier applied to all trainer
                              scorers (boost utility / disruption play).

Presets the LLM coach (`/ultra-loop`) will tune per iteration. Symbol
name is ``POKEMON_BIAS_PRESETS`` exactly so the loop's grep-discovery
in `.claude/commands/ultra-loop.md` picks it up.

Six presets ship initially — one for each BRV archetype:

- ``balanced`` — vanilla (all multipliers default 1.0).
- ``aggro_burn`` — push damage early, deemphasize Trainers.
- ``control_disrupt`` — heavy Trainer use, hand disruption preferred.
- ``lz_engine`` — Lost Zone archetype: Cremate, Mirko Vosk, Jarad ex.
- ``bench_swarm`` — wide-board: Aurelia ex, Sanguine Sacrament.
- ``energy_denial`` — Voidmage, Pithing Drone, Niv-Mizzet's Quandary.
"""

from __future__ import annotations


def _preset(**overrides) -> dict:
    """Build a preset by overlaying ``overrides`` on the empty default."""
    out = {
        'trainer_multipliers': {},
        'attack_multipliers': {},
        'evolution_multipliers': {},
        'global_attack_pressure': 1.0,
        'global_trainer_bias': 1.0,
    }
    for k, v in overrides.items():
        if k.endswith('_multipliers') and isinstance(v, dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


POKEMON_BIAS_PRESETS: dict[str, dict] = {
    # ──────────────────────────────────────────────────────────
    # Vanilla — default behavior, no per-archetype tuning.
    # ──────────────────────────────────────────────────────────
    'balanced': _preset(),

    # ──────────────────────────────────────────────────────────
    # Aggro Burn — push damage early; deemphasize utility Trainers.
    # ──────────────────────────────────────────────────────────
    'aggro_burn': _preset(
        global_attack_pressure=1.4,
        global_trainer_bias=0.7,
        attack_multipliers={
            ('Voidmage Apprentice', 'Energy Drain'): 1.5,
            ('Aurelia, the Warleader ex', 'Battalion Mark'): 1.3,
        },
        trainer_multipliers={
            # Aggro doesn't want to play Cremate (slow LZ setup).
            'Cremate': 0.4,
            'Tezzy\'s Test': 0.6,
            # But Pithing Drone protects our attacker — keep it.
            'Pithing Drone': 1.3,
        },
    ),

    # ──────────────────────────────────────────────────────────
    # Control / Disrupt — Trainer-heavy, hand disruption, prize tax.
    # ──────────────────────────────────────────────────────────
    'control_disrupt': _preset(
        global_trainer_bias=1.4,
        trainer_multipliers={
            'Dimir Interrogation': 2.0,
            'Jace, Memory Adept': 1.8,
            'Tezzy\'s Test': 1.6,
            'Niv-Mizzet\'s Quandary': 1.8,
            'Sanguine Sacrament': 1.4,
            'Tox-Pawpsule': 1.5,
        },
        attack_multipliers={
            ('Voidmage Apprentice', 'Energy Drain'): 1.4,
        },
        evolution_multipliers={
            'Obzedat, Ghost Council ex': 1.5,
        },
    ),

    # ──────────────────────────────────────────────────────────
    # Lost Zone Engine — name retained for legacy Jarad/Cremate variant,
    # but the actual brv:dimir deck (iter 1) ships Lazav ex / Mirko Vosk
    # as the win line. Weights cover both lines so the preset works for
    # either deck composition.
    # ──────────────────────────────────────────────────────────
    'lz_engine': _preset(
        trainer_multipliers={
            'Cremate': 1.8,
            'Negate the Negation': 1.3,
            'Sanguine Sacrament': 1.5,  # also feeds LZ
            # iter 1: Dimir Blend Energy is the T2 tempo card —
            # free P+D attach skips a turn of manual attaching.
            'Dimir Blend Energy': 1.6,
            # iter 1: Nest Ball solves the empty-bench failure mode
            # (Lazav ex's 280 HP doesn't save you from `no_pokemon`).
            'Nest Ball': 1.5,
            # iter 1: Ultra Ball auto-discards Energy first — harmful
            # to Dimir's P/D curve when hand is energy-thin. Cap at 0.7.
            'Ultra Ball': 0.7,
            # iter 1: Dimir Interrogation whiffs when opp hand <4.
            # Slight down-weight; preset doesn't have state-aware logic.
            'Dimir Interrogation': 0.9,
            # iter 2: Duskmantle is a clutch tech card (Confused via
            # Trainer mill) — saved a 2-turn window when opp Reckoner
            # confusion-tails self-KO'd. Best vs Trainer-heavy decks.
            'Duskmantle, House of Shadow': 1.3,
            # iter 2: Rare Candy is frequently dead — requires Lazlet
            # in play AND Lazav ex in hand. With 4-copy Lazlet
            # starvation (0 drawn in 22 turns), Rare Candy bricks.
            'Rare Candy': 0.8,
            # iter 3: Tox-Pawpsule was decisive vs Boros — between-turn
            # poison ticks killed opp Reckoner (50→20→0) without Dimir
            # spending an attack. Forces opp into retreat-or-die when
            # they lack Switch. Add at 1.4× (matching control_disrupt's
            # 1.5×); cap at 2.0×.
            'Tox-Pawpsule': 1.4,
        },
        attack_multipliers={
            ('Mirko Vosk, Mind Drinker', 'Lost Recall'): 2.0,
            ('Jarad, Golgari Lich Lord ex', 'Necrosurge'): 1.8,
            ('Jarad, Golgari Lich Lord ex', "Lich's Bargain"): 1.6,
            # iter 1: Lazav ex is the actual win-condition attack in
            # brv:dimir. Shadowstrike {P}{P}{D}{D} for 200 + mill 4.
            ('Lazav, Dimir Mastermind ex', 'Shadowstrike'): 2.0,
            # iter 3: Veiled Whisper is the workhorse — not just the
            # setup attack. 2-energy {P}{D} for 80 dmg one-shots BRV's
            # typical 60-90 HP basics + Stage 1s; only Stage 2 ex (280
            # HP) need Shadowstrike's 4-energy overkill. KO'd 5 of 6
            # Boros Pokemon in iter 3 prize race. Bump 1.3→1.6, cap at
            # the 2.0× ceiling shared with Shadowstrike.
            ('Lazav, Dimir Mastermind ex', 'Veiled Whisper'): 1.6,
            # iter 2: Mirklet Tiny Bite is the Plan-C chip attack when
            # both Stage 2 lines are stalled. 1-cost backup pressure.
            ('Mirklet', 'Tiny Bite'): 1.2,
            # v2-iter1: Voidmage Energy Drain is the Boros disruption
            # answer — vs the Gideon+Feather 100-dmg/turn combo, draining
            # Boros's Active Fire energy slows the kill chain ~1 turn per
            # cycle. Pilot A's Voidmage benched but never fired (no P
            # attached). 1.3× nudges the heuristic to attach P + attack.
            ('Voidmage Apprentice', 'Energy Drain'): 1.3,
        },
        evolution_multipliers={
            'Mirko Vosk, Mind Drinker': 2.0,
            'Jarad, Golgari Lich Lord ex': 2.0,
            # iter 1: Lazav line is the actual win path. Stage 2.
            'Lazav, Dimir Mastermind ex': 2.0,
            # iter 1: Lazander is the intermediate Stage 1; prioritize
            # over Mirko Vosk when both are options and energy is tight.
            'Lazander': 1.5,
            # iter 2: Lazlet is the Stage 0 evolver gating the Lazav ex
            # line. 4-copy starvation in iter 2 (0 drawn in 22 turns).
            # Bias-bump prioritizes hitting it via tutors. Cap at 1.6.
            'Lazlet': 1.6,
        },
    ),

    # ──────────────────────────────────────────────────────────
    # Bench Swarm — wide-board: Aurelia ex, Sanguine Sacrament.
    # ──────────────────────────────────────────────────────────
    'bench_swarm': _preset(
        attack_multipliers={
            ('Aurelia, the Warleader ex', 'Battalion Mark'): 2.0,
            # iter 1: Feather, the Redeemed is a confirmed secondary
            # win condition (120 HP, R+C 80 + Trainer recursion).
            # v2-iter1: Bumped 1.4 → 1.6 — Feather Redeemed Recursion took
            # 3 KOs this game (Lazander, Lazav ex, Lazlet) and was the
            # primary kill engine alongside Gideon. Pilot B won with 0/2
            # Aurelia ex drawn — Feather is a legitimate co-equal apex.
            ('Feather, the Redeemed', 'Redeemed Recursion'): 1.6,
            # v2-iter2: Feathlet Halo Bash 30 dmg is fine early-game
            # pressure when no Aurelin is in hand. Pilot B's iter 2
            # T4 Halo Bash for 30 → Lazander 70→40 was the only second
            # attack of the entire game. Encourages bench-the-Feathlet
            # + attack rather than holding for the evolve. 1.2 cap.
            ('Feathlet', 'Halo Bash'): 1.2,
        },
        evolution_multipliers={
            'Aurelia, the Warleader ex': 1.8,
            # iter 1: Aurelin (Stage 1) is the first scaling step and
            # was under-prioritized in pilot's decision logs.
            'Aurelin': 1.5,
        },
        trainer_multipliers={
            'Sanguine Sacrament': 1.5,  # sac to save key bench
            'Tox-Pawpsule': 1.3,
            # iter 1: Boss's Orders + cheap-attacker line confirmed as
            # the surgical kill vs tanky-Active opponents. Pull a
            # 1-prize bench Pokemon to Active, KO for prize, bypass
            # the 280 HP wall. Already at 1.6×; iter 2 confirms — don't
            # bump further (over-tuning risks Boss's Orders being played
            # when no high-value bench target exists).
            "Boss's Orders": 1.6,
            # v2-iter2: Boros Cluestone bumped 1.3 → 1.5. Energy
            # starvation cost the game — Cluestone is the only
            # repeatable typed-energy tutor in the deck. Cap at 1.5
            # (don't push past 2.0 — Cluestone splits the deck's
            # energy density when over-played).
            'Boros Cluestone': 1.5,
            # v2-iter2 ENGINE BUG GUARD: Switch is broken (consumed
            # but does not actually swap Active↔Bench). Heavy down-
            # weight at the bias level until Bug 6 fixed. Encoder
            # also returns -100 in TRAINER_SCORERS for belt-and-
            # suspenders. TODO: re-enable when engine Bug 6 lands.
            'Switch': 0.3,
            # v2-iter2 ENGINE BUG GUARD: Potion is broken (consumed
            # but does not heal damage counters). Heavy down-weight
            # at the bias level until Bug 7 fixed. Encoder also
            # returns -100 in TRAINER_SCORERS. TODO: re-enable when
            # engine Bug 7 lands.
            'Potion': 0.4,
            # iter 1: Sunhome heals BOTH actives. Against a tank that
            # we can't KO, the mutual heal favors opp. Down-weight.
            'Sunhome, Fortress of the Legion': 0.7,
            # iter 1: Ultra Ball auto-discards Energy first — Boros
            # is 2-color and energy-thin, so this discards Fire/Fighting
            # before utility cards. Engine-wide pitfall.
            'Ultra Ball': 0.7,
            # iter 2: Boros Blend Energy + retreat is a 1-turn ramp
            # combo (saved game T18 — wrong-typed Active swapped for
            # fresh Basic, Blend gives R+F immediately).
            # v2-iter2: Boros Blend is the ONLY direct-attach-to-Active
            # in the deck; without it, T2 Active has 1 manual attach max.
            # Pilot B's energy-starvation loss (Fighting depleted by T8)
            # would have been worse without the T2 Blend. Keep at 1.4.
            'Boros Blend Energy': 1.4,
            # iter 2: Gideon Blackblade is a confirmed kill-spell
            # finisher (Supporter, 20 dmg + 20 heal, doesn't end
            # turn). Won iter 2 by KO'ing opp's lone Mirklet at 10 HP
            # → empty bench → no_pokemon. Save for opp Active ≤ 20 HP.
            # v2-iter1: RETRACTING iter 3's "ends turn" claim — Pilot B
            # confirmed via 2 plays (T19, T29) that Gideon does NOT end
            # turn. It's a free 20+heal stapled to attack EVERY turn.
            # Bumped 1.8 → 2.0 (cap) so the heuristic plays it whenever
            # the Supporter slot is open, not just as a finisher.
            'Gideon Blackblade': 2.0,
        },
    ),

    # ──────────────────────────────────────────────────────────
    # Energy Denial — Voidmage / Pithing Drone / Niv-Mizzet's Quandary.
    # ──────────────────────────────────────────────────────────
    'energy_denial': _preset(
        attack_multipliers={
            ('Voidmage Apprentice', 'Energy Drain'): 1.8,
        },
        trainer_multipliers={
            'Pithing Drone': 1.6,
            'Niv-Mizzet\'s Quandary': 1.7,
            # Energy-denial archetype loves cards that lock opp energy
            # out of useful position — both these fit.
            'Tox-Pawpsule': 1.2,  # status sticks while we deny energy
        },
    ),
}


# Public API — used by adapter.py to look up the active preset.

def get_preset(name: str | None) -> dict:
    """Return the preset dict for ``name`` (case-insensitive), or
    'balanced' as fallback. Always returns a populated dict so callers
    don't have to None-check."""
    if not name:
        return POKEMON_BIAS_PRESETS['balanced']
    key = str(name).strip().lower()
    return POKEMON_BIAS_PRESETS.get(key, POKEMON_BIAS_PRESETS['balanced'])


def apply_trainer_bias(preset: dict, card_name: str, base_score: float) -> float:
    """Apply preset bias to a trainer's base score."""
    if not preset:
        return base_score
    mult = preset.get('trainer_multipliers', {}).get(card_name, 1.0)
    global_mult = preset.get('global_trainer_bias', 1.0)
    return base_score * mult * global_mult


def apply_attack_bias(preset: dict, card_name: str, attack_name: str, base_score: float) -> float:
    """Apply preset bias to an attack's base score."""
    if not preset:
        return base_score
    mult = preset.get('attack_multipliers', {}).get((card_name, attack_name), 1.0)
    global_mult = preset.get('global_attack_pressure', 1.0)
    return base_score * mult * global_mult


def apply_evolution_bias(preset: dict, evolution_name: str, base_score: float) -> float:
    """Apply preset bias to an evolution's base score."""
    if not preset:
        return base_score
    mult = preset.get('evolution_multipliers', {}).get(evolution_name, 1.0)
    return base_score * mult
