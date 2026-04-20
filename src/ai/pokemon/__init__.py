"""
src.ai.pokemon — Pokemon TCG AI package

Re-exports the public API so callers can use:
    from src.ai.pokemon import PokemonAIAdapter
    from src.ai.pokemon.adapter import PokemonAIAdapter
"""
from src.ai.pokemon.context import TurnContext, EnergyPlan
from src.ai.pokemon.trainers import TRAINER_SCORERS, trainer_scorer
from src.ai.pokemon.adapter import PokemonAIAdapter

__all__ = [
    "PokemonAIAdapter",
    "TurnContext",
    "EnergyPlan",
    "TRAINER_SCORERS",
    "trainer_scorer",
]
