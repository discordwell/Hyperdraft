"""
Hyperdraft Engine

Everything is an Event. Everything else is an Interceptor.

Core systems:
- Event Pipeline: Process events through interceptor chain
- Turn Manager: Phase/step structure
- Priority System: Action handling and response windows
- Stack Manager: LIFO spell/ability resolution
- Combat Manager: Attack/block/damage
- Mana System: Cost parsing and payment
- Targeting System: Legal targets and validation
"""

import asyncio


class _CompatEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Back-compat for tests that still call asyncio.get_event_loop() directly."""

    def get_event_loop(self):
        local = getattr(self, "_local", None)
        current = getattr(local, "_loop", None) if local is not None else None
        if current is not None:
            return current

        loop = self.new_event_loop()
        self.set_event_loop(loop)
        return loop


if not isinstance(asyncio.get_event_loop_policy(), _CompatEventLoopPolicy):
    asyncio.set_event_loop_policy(_CompatEventLoopPolicy())

from .types import (
    # IDs
    new_id,

    # Events
    Event, EventType, EventStatus,

    # Interceptors
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    InterceptorHandler, EventFilter,

    # Game objects
    GameObject, Characteristics, ObjectState,
    CardType, Color, ZoneType,

    # Pokemon
    PokemonType,

    # Other
    Player, Zone, GameState, CardDefinition, CardFace,

    # Player choice system
    PendingChoice,
)

from .pipeline import EventPipeline

from .queries import (
    get_power, get_toughness, get_types, get_subtypes, get_supertypes,
    get_colors, has_ability, is_creature
)

from .game import (
    Game,
    make_creature, make_instant, make_enchantment,
    make_sorcery, make_artifact, make_land, make_planeswalker,
    make_pokemon, make_trainer_item, make_trainer_supporter,
    make_trainer_stadium, make_pokemon_tool, make_basic_energy,
)

from .mana import (
    ManaSystem, ManaPool, ManaCost, ManaType, ManaUnit,
    parse_cost, color_identity
)

from .stack import (
    StackManager, StackItem, StackItemType, StackEvent, SpellBuilder,
    create_damage_spell, create_draw_spell, create_destroy_spell, create_counter_spell
)

from .turn import (
    TurnManager, TurnState, Phase, Step
)

from .priority import (
    PrioritySystem, PlayerAction, ActionType, LegalAction, ActionValidator
)

from .combat import (
    CombatManager, CombatState, AttackDeclaration, BlockDeclaration, DamageAssignment
)

from .targeting import (
    TargetingSystem, TargetFilter, TargetRequirement, Target, TargetType,
    creature_filter, permanent_filter, player_filter, any_target_filter,
    spell_filter, card_in_graveyard_filter,
    target_creature, target_any, target_player, target_spell
)

from .plot_saddle import (
    is_plotted, can_cast_plotted,
    pay_plot_cost, cast_plotted_spell,
    make_becomes_plotted_trigger,
    is_saddled, pay_saddle_cost,
    make_saddle_trigger, make_becomes_saddled_trigger,
    set_saddle_threshold, reset_saddled_at_eot,
)

from .variant_metrics import MTG_BASELINE_RULES, variant_rule_summary
from .mode_metrics import NON_MTG_MODES, mode_health_summary, non_mtg_health_report

from .tiered import (
    TierDefinition,
    make_tiered_setup,
    make_tiered_resolve,
    compute_affordable_tiers,
    get_chosen_tier_index,
    get_chosen_tier_indices,
    clear_chosen_tier,
    TURN_DATA_TIER_KEY,
)

from .spree import (
    SpreeMode,
    make_spree_setup,
    make_spree_resolve,
    compute_affordable_spree_modes,
    get_chosen_spree_modes,
    record_spree_choice,
    clear_spree_choice,
    open_spree_choice,
    total_spree_extra_cost,
    is_spree_card,
    get_spree_modes,
    get_spree_minmax,
    TURN_DATA_SPREE_KEY,
)

__all__ = [
    # IDs
    'new_id',

    # Events
    'Event', 'EventType', 'EventStatus',

    # Interceptors
    'Interceptor', 'InterceptorPriority', 'InterceptorAction', 'InterceptorResult',
    'InterceptorHandler', 'EventFilter',

    # Game objects
    'GameObject', 'Characteristics', 'ObjectState',
    'CardType', 'Color', 'ZoneType',

    # Other
    'Player', 'Zone', 'GameState', 'CardDefinition', 'CardFace',

    # Player choice system
    'PendingChoice',

    # Pipeline
    'EventPipeline',

    # Queries
    'get_power', 'get_toughness', 'get_types', 'get_subtypes', 'get_supertypes',
    'get_colors', 'has_ability', 'is_creature',

    # Game
    'Game', 'make_creature', 'make_instant', 'make_enchantment',
    'make_sorcery', 'make_artifact', 'make_land', 'make_planeswalker',

    # Mana
    'ManaSystem', 'ManaPool', 'ManaCost', 'ManaType', 'ManaUnit',
    'parse_cost', 'color_identity',

    # Stack
    'StackManager', 'StackItem', 'StackItemType', 'StackEvent', 'SpellBuilder',
    'create_damage_spell', 'create_draw_spell', 'create_destroy_spell', 'create_counter_spell',

    # Turn
    'TurnManager', 'TurnState', 'Phase', 'Step',

    # Priority
    'PrioritySystem', 'PlayerAction', 'ActionType', 'LegalAction', 'ActionValidator',

    # Combat
    'CombatManager', 'CombatState', 'AttackDeclaration', 'BlockDeclaration', 'DamageAssignment',

    # Targeting
    'TargetingSystem', 'TargetFilter', 'TargetRequirement', 'Target', 'TargetType',
    'creature_filter', 'permanent_filter', 'player_filter', 'any_target_filter',
    'spell_filter', 'card_in_graveyard_filter',
    'target_creature', 'target_any', 'target_player', 'target_spell',

    # OTJ Plot / Saddle
    'is_plotted', 'can_cast_plotted',
    'pay_plot_cost', 'cast_plotted_spell',
    'make_becomes_plotted_trigger',
    'is_saddled', 'pay_saddle_cost',
    'make_saddle_trigger', 'make_becomes_saddled_trigger',
    'set_saddle_threshold', 'reset_saddled_at_eot',

    # Variant metrics
    'MTG_BASELINE_RULES', 'variant_rule_summary',

    # Mode metrics
    'NON_MTG_MODES', 'mode_health_summary', 'non_mtg_health_report',

    # FIN Tiered cost
    'TierDefinition', 'make_tiered_setup', 'make_tiered_resolve',
    'compute_affordable_tiers', 'get_chosen_tier_index',
    'get_chosen_tier_indices', 'clear_chosen_tier', 'TURN_DATA_TIER_KEY',

    # OTJ Spree cost-per-mode
    'SpreeMode', 'make_spree_setup', 'make_spree_resolve',
    'compute_affordable_spree_modes', 'get_chosen_spree_modes',
    'record_spree_choice', 'clear_spree_choice', 'open_spree_choice',
    'total_spree_extra_cost', 'is_spree_card', 'get_spree_modes',
    'get_spree_minmax', 'TURN_DATA_SPREE_KEY',
]
