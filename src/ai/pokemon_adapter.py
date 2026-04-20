"""
Compatibility shim — real code lives in src/ai/pokemon/

Preserves the old import path:
    from src.ai.pokemon_adapter import PokemonAIAdapter
"""
from src.ai.pokemon.adapter import PokemonAIAdapter
from src.ai.pokemon.context import TurnContext, EnergyPlan
from src.ai.pokemon.trainers import TRAINER_SCORERS, trainer_scorer

__all__ = ["PokemonAIAdapter", "TurnContext", "EnergyPlan",
           "TRAINER_SCORERS", "trainer_scorer"]
