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
    # Lost Zone Engine — Cremate, Mirko Vosk, Jarad ex archetype.
    # ──────────────────────────────────────────────────────────
    'lz_engine': _preset(
        trainer_multipliers={
            'Cremate': 1.8,
            'Negate the Negation': 1.3,
            'Sanguine Sacrament': 1.5,  # also feeds LZ
        },
        attack_multipliers={
            ('Mirko Vosk, Mind Drinker', 'Lost Recall'): 2.0,
            ('Jarad, Golgari Lich Lord ex', 'Necrosurge'): 1.8,
            ('Jarad, Golgari Lich Lord ex', "Lich's Bargain"): 1.6,
        },
        evolution_multipliers={
            'Mirko Vosk, Mind Drinker': 2.0,
            'Jarad, Golgari Lich Lord ex': 2.0,
        },
    ),

    # ──────────────────────────────────────────────────────────
    # Bench Swarm — wide-board: Aurelia ex, Sanguine Sacrament.
    # ──────────────────────────────────────────────────────────
    'bench_swarm': _preset(
        attack_multipliers={
            ('Aurelia, the Warleader ex', 'Battalion Mark'): 2.0,
        },
        evolution_multipliers={
            'Aurelia, the Warleader ex': 1.8,
        },
        trainer_multipliers={
            'Sanguine Sacrament': 1.5,  # sac to save key bench
            'Tox-Pawpsule': 1.3,
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
