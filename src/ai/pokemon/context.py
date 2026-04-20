"""
Pokemon TCG AI — Turn Context

TurnContext dataclass and EnergyPlan dataclass.
_build_turn_context is a free function that takes a PokemonAIAdapter-like
object so it can call helper methods, but lives here for import hygiene.
"""
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from src.engine.types import GameState, CardType
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_combat import PokemonCombatManager

if TYPE_CHECKING:
    from src.engine.types import GameObject


# ══════════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════════

@dataclass
class TurnContext:
    """Computed board analysis built once per turn, shared by all scoring functions."""
    # My state
    my_active: Optional[str] = None
    my_bench: list[str] = field(default_factory=list)
    my_hand_energy: list[str] = field(default_factory=list)
    my_hand_basics: list[str] = field(default_factory=list)
    my_hand_evolutions: list[str] = field(default_factory=list)
    my_hand_items: list[str] = field(default_factory=list)
    my_hand_supporters: list[str] = field(default_factory=list)
    my_prizes_remaining: int = 6

    # Opponent state
    opp_id: str = ''
    opp_active: Optional[str] = None
    opp_bench: list[str] = field(default_factory=list)
    opp_prizes_remaining: int = 6
    opp_hand_size: int = 0

    # Computed analysis
    can_ko_active: bool = False
    ko_attack_info: Optional[dict] = None
    opp_can_ko_me: bool = False
    opp_estimated_max_damage: int = 0
    my_weakness_exposed: bool = False
    their_weakness_exposed: bool = False
    evolution_map: dict = field(default_factory=dict)
    energy_needs: dict = field(default_factory=dict)
    prize_gap: int = 0
    game_phase: str = 'early'
    defensive_mode: bool = False
    retreat_urgency: float = 0.0
    has_switch_in_hand: bool = False


@dataclass
class EnergyPlan:
    """Multi-turn energy investment plan for a specific Pokemon + attack."""
    target_pokemon_id: str
    target_attack_index: int
    energy_type_needed: str
    turns_remaining: int
    priority: float
    created_turn: int
