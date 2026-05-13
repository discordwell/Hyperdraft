"""
Pokemon TCG AI — Attack + Evolution Scorer Registries

Card-name-aware bias hooks consulted by ``_score_attack`` and
``_score_evolution`` in ``scoring.py``. Mirrors the
``trainers.py / TRAINER_SCORERS`` pattern.

Registries:

- ``ATTACK_SCORERS: dict[tuple[card_name, attack_name], Callable]`` —
  consulted *in addition to* the base damage/weakness/KO-math logic.
  The base scorer runs first; the registry value is *added* on top.
  Signature: ``(adapter, attacker, attack, state, player_id) -> float``.

- ``EVOLUTION_SCORERS: dict[evolution_card_name, Callable]`` — consulted
  *in addition to* the base evolution logic. Signature:
  ``(adapter, base, evolution, state, player_id) -> float``.

These additive registries let set-specific scorers express archetype
biases (e.g. "Mirko Vosk's Lost Recall is hot when own LZ has 0-4
Pokemon" or "Jarad ex is preferred evolution when own discard has 2+
Pokemon") without rewriting the generic scoring core.

Importing this module at adapter load time pulls in set-specific
registrations via the side-effect import at the bottom (mirroring how
``trainers.py`` imports ``brv_spice_scorers``).
"""
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.types import GameObject, GameState


ATTACK_SCORERS: dict[tuple[str, str], Callable] = {}
EVOLUTION_SCORERS: dict[str, Callable] = {}


def attack_scorer(card_name: str, attack_name: str):
    """Register a bias function for a specific card+attack pair.

    The function's return value is *added* to ``_score_attack``'s base
    score (positive boosts the attack's appeal, negative suppresses it).
    """
    def decorator(fn):
        ATTACK_SCORERS[(card_name, attack_name)] = fn
        return fn
    return decorator


def evolution_scorer(card_name: str):
    """Register a bias function for evolving INTO ``card_name``.

    The function's return value is added to ``_score_evolution``'s base
    score for this evolution target.
    """
    def decorator(fn):
        EVOLUTION_SCORERS[card_name] = fn
        return fn
    return decorator


# ══════════════════════════════════════════════════════════════
#  Side-effect imports — register set-specific scorers
# ══════════════════════════════════════════════════════════════
# Importing modules with @attack_scorer / @evolution_scorer decorators
# populates the registries at module load time. Add new sets here.
from src.ai.pokemon import brv_spice_attack_scorers  # noqa: F401, E402
