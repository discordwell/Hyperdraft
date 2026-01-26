"""
Interceptor Helper Functions

Common patterns for creating interceptors across all card sets.
"""

from typing import Callable, Optional, Any
from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    PendingChoice,
    new_id
)


# =============================================================================
# FILTER FACTORY FUNCTIONS
# =============================================================================

def other_creatures_you_control(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other creatures you control (excluding source)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def creatures_you_control(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: All creatures you control (including source)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def creatures_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Creatures you control with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def other_creatures_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other creatures you control with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def all_opponents(source: GameObject, state: GameState) -> list[str]:
    """Get list of opponent player IDs."""
    return [p_id for p_id in state.players.keys() if p_id != source.controller]


# =============================================================================
# ETB TRIGGER
# =============================================================================

def make_etb_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create an ETB (enters-the-battlefield) trigger interceptor.

    Args:
        source_obj: The object with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter (receives event, state, source_obj)

    Event: ZONE_CHANGE with to_zone_type == BATTLEFIELD and object_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('object_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# DEATH TRIGGER
# =============================================================================

def make_death_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a death trigger interceptor (when this creature dies).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: OBJECT_DESTROYED with object_id == source_obj.id
    Priority: REACT

    Note: The trigger fires during the REACT phase, BEFORE interceptor cleanup.
    This allows the creature to "see" its own death and trigger effects.
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        # Primary check: OBJECT_DESTROYED for this creature
        if event.type == EventType.OBJECT_DESTROYED:
            return event.payload.get('object_id') == obj.id

        # Fallback: ZONE_CHANGE from battlefield to graveyard (for exile->graveyard, etc.)
        if event.type == EventType.ZONE_CHANGE:
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                    event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

        return False

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='until_leaves'  # Stays registered to fire after leaving
    )


# =============================================================================
# ATTACK TRIGGER
# =============================================================================

def make_attack_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create an attack trigger interceptor (whenever this creature attacks).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: ATTACK_DECLARED with attacker_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# BLOCK TRIGGER
# =============================================================================

def make_block_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a block trigger interceptor (whenever this creature blocks).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: BLOCK_DECLARED with blocker_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.BLOCK_DECLARED and
                event.payload.get('blocker_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# DAMAGE TRIGGER
# =============================================================================

def make_damage_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    combat_only: bool = False,
    noncombat_only: bool = False,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a damage trigger interceptor (whenever this creature deals damage).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        combat_only: If True, only trigger on combat damage
        noncombat_only: If True, only trigger on noncombat damage
        filter_fn: Optional custom filter for additional conditions

    Event: DAMAGE with source == source_obj.id
    Payload: {'target': str, 'amount': int, 'source': str, 'is_combat': bool}
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False

        is_combat = event.payload.get('is_combat', False)
        if combat_only and not is_combat:
            return False
        if noncombat_only and is_combat:
            return False

        return True

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# STATIC P/T BOOST (LORD EFFECT)
# =============================================================================

def make_static_pt_boost(
    source_obj: GameObject,
    power_mod: int,
    toughness_mod: int,
    affects_filter: Callable[[GameObject, GameState], bool]
) -> list[Interceptor]:
    """
    Create +X/+Y static ability interceptors (lord effects).

    Args:
        source_obj: The object granting the bonus
        power_mod: Power modifier (+1, -1, etc.)
        toughness_mod: Toughness modifier
        affects_filter: Function(target, state) -> bool to determine which objects are affected

    Event: QUERY_POWER / QUERY_TOUGHNESS
    Priority: QUERY
    """
    interceptors = []

    if power_mod != 0:
        def power_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_POWER:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return affects_filter(target, state)

        def power_handler(event: Event, state: GameState) -> InterceptorResult:
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + power_mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ))

    if toughness_mod != 0:
        def toughness_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return affects_filter(target, state)

        def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + toughness_mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        ))

    return interceptors


# =============================================================================
# KEYWORD GRANT
# =============================================================================

def make_keyword_grant(
    source_obj: GameObject,
    keywords: list[str],
    affects_filter: Callable[[GameObject, GameState], bool]
) -> Interceptor:
    """
    Create a keyword-granting interceptor (static ability).

    Args:
        source_obj: The object granting the keywords
        keywords: List of keyword names to grant (e.g., ['flying', 'vigilance'])
        affects_filter: Function(target, state) -> bool to determine which objects receive keywords

    Event: QUERY_ABILITIES
    Payload: {'object_id': str, 'granted': list[str]}
    Priority: QUERY
    """
    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return affects_filter(target, state)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in keywords:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# SPELL CAST TRIGGER
# =============================================================================

def make_spell_cast_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True,
    spell_type_filter: Optional[set[CardType]] = None,
    color_filter: Optional[set[Color]] = None,
    mana_value_min: Optional[int] = None,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a spell cast trigger interceptor.

    Args:
        source_obj: The object with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger on spells cast by controller (default True)
        spell_type_filter: Only trigger on specific spell types (e.g., {CardType.INSTANT})
        color_filter: Only trigger on spells containing these colors
        mana_value_min: Only trigger on spells with MV >= this value
        filter_fn: Optional custom filter for additional conditions

    Event: CAST
    Payload: {'spell_id': str, 'caster': str, 'mana_value': int, 'colors': set, 'types': set}
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False

        # Check controller
        if controller_only and event.payload.get('caster') != obj.controller:
            return False

        # Check spell type
        if spell_type_filter:
            spell_types = set(event.payload.get('types', []))
            if not spell_types.intersection(spell_type_filter):
                return False

        # Check colors
        if color_filter:
            spell_colors = set(event.payload.get('colors', []))
            if not spell_colors.intersection(color_filter):
                return False

        # Check mana value
        if mana_value_min is not None:
            mv = event.payload.get('mana_value', 0)
            if mv < mana_value_min:
                return False

        return True

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# TAP TRIGGER
# =============================================================================

def make_tap_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a tap trigger interceptor (whenever this permanent is tapped).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: TAP with object_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# UPKEEP TRIGGER
# =============================================================================

def make_upkeep_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create an upkeep trigger interceptor (at the beginning of upkeep).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger on controller's upkeep

    Event: PHASE_START with phase == 'upkeep'
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        if controller_only and state.active_player != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# END STEP TRIGGER
# =============================================================================

def make_end_step_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create an end step trigger interceptor (at the beginning of end step).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger on controller's end step

    Event: PHASE_START with phase == 'end_step'
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'end_step':
            return False
        if controller_only and state.active_player != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# LIFE CHANGE TRIGGER
# =============================================================================

def make_life_gain_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create a life gain trigger (whenever you gain life).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger when controller gains life

    Event: LIFE_CHANGE with amount > 0
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        if controller_only and event.payload.get('player') != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


def make_life_loss_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    opponent_only: bool = True
) -> Interceptor:
    """
    Create a life loss trigger (whenever an opponent loses life).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        opponent_only: If True, only trigger when opponents lose life

    Event: LIFE_CHANGE with amount < 0
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount >= 0:
            return False
        if opponent_only and event.payload.get('player') == source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# DRAW TRIGGER
# =============================================================================

def make_draw_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create a draw trigger (whenever you draw a card).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger when controller draws

    Event: DRAW
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        if controller_only and event.payload.get('player') != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# COUNTER ADDED TRIGGER
# =============================================================================

def make_counter_added_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    counter_type: Optional[str] = None,
    self_only: bool = True
) -> Interceptor:
    """
    Create a counter added trigger.

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        counter_type: Specific counter type to trigger on (None = any)
        self_only: If True, only trigger when counters are added to this permanent

    Event: COUNTER_ADDED
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if self_only and event.payload.get('object_id') != source_obj.id:
            return False
        if counter_type and event.payload.get('counter_type') != counter_type:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# ADDITIONAL LAND PLAY (Static Ability)
# =============================================================================

def make_additional_land_play(
    source_obj: GameObject,
    count: int = 1
) -> Interceptor:
    """
    Create a static ability that grants additional land plays.

    Used for cards like Exploration ("You may play an additional land on each of your turns").

    This interceptor fires at the beginning of each of the controller's turns to
    increase their lands_allowed_this_turn count.

    Args:
        source_obj: The permanent granting additional land plays
        count: Number of additional lands allowed (default 1)

    Event: TURN_START for controller
    Priority: REACT

    Example usage:
        EXPLORATION = make_enchantment(
            name="Exploration",
            mana_cost="{G}",
            colors={Color.GREEN},
            text="You may play an additional land on each of your turns.",
            setup_interceptors=lambda obj, state: [make_additional_land_play(obj, 1)]
        )
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TURN_START:
            return False
        # Only on controller's turn
        return event.payload.get('player') == source_obj.controller

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # Directly modify the GameState land allowance
        # This is safe because interceptors run during event processing
        state.lands_allowed_this_turn += count
        return InterceptorResult(
            action=InterceptorAction.PASS  # No new events, just modified state
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# PLAYER CHOICE HELPERS
# =============================================================================

def create_modal_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    modes: list[dict],
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: str = "Choose a mode:"
) -> PendingChoice:
    """
    Create a modal spell choice.

    Args:
        state: The game state
        player_id: Player who makes the choice
        source_id: Card/ability that needs the choice
        modes: List of mode options, each as {"index": int, "text": str}
        min_modes: Minimum modes to choose (default 1)
        max_modes: Maximum modes to choose (default 1, use 2+ for "choose two")
        prompt: UI prompt text

    Example:
        # Choose one:
        choice = create_modal_choice(
            state, controller_id, spell_id,
            modes=[
                {"index": 0, "text": "Target creature gets +2/+2 until end of turn"},
                {"index": 1, "text": "Target creature gains flying until end of turn"},
            ]
        )

        # Choose two:
        choice = create_modal_choice(
            state, controller_id, spell_id,
            modes=[...],
            min_modes=2,
            max_modes=2,
            prompt="Choose two:"
        )
    """
    choice = PendingChoice(
        choice_type="modal",
        player=player_id,
        prompt=prompt,
        options=modes,
        source_id=source_id,
        min_choices=min_modes,
        max_choices=max_modes
    )
    state.pending_choice = choice
    return choice


def create_scry_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    scry_count: int = None
) -> PendingChoice:
    """
    Create a scry choice.

    Args:
        state: The game state
        player_id: Player who is scrying
        source_id: Card/ability causing the scry
        card_ids: IDs of the top cards being scryed
        scry_count: Number being scryed (defaults to len(card_ids))

    Returns the PendingChoice. Player selects which cards go to bottom.
    Cards not selected stay on top in their original order.

    Example:
        # Scry 2
        top_cards = get_top_cards(library, 2)
        choice = create_scry_choice(state, player_id, source_id, top_cards)
    """
    count = scry_count or len(card_ids)
    choice = PendingChoice(
        choice_type="scry",
        player=player_id,
        prompt=f"Scry {count}: Choose cards to put on the bottom of your library",
        options=card_ids,
        source_id=source_id,
        min_choices=0,
        max_choices=len(card_ids),
        callback_data={"scry_count": count}
    )
    state.pending_choice = choice
    return choice


def create_surveil_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    surveil_count: int = None
) -> PendingChoice:
    """
    Create a surveil choice.

    Args:
        state: The game state
        player_id: Player who is surveilling
        source_id: Card/ability causing the surveil
        card_ids: IDs of the top cards being surveilled
        surveil_count: Number being surveilled (defaults to len(card_ids))

    Returns the PendingChoice. Player selects which cards go to graveyard.
    Cards not selected stay on top.

    Example:
        # Surveil 2
        top_cards = get_top_cards(library, 2)
        choice = create_surveil_choice(state, player_id, source_id, top_cards)
    """
    count = surveil_count or len(card_ids)
    choice = PendingChoice(
        choice_type="surveil",
        player=player_id,
        prompt=f"Surveil {count}: Choose cards to put into your graveyard",
        options=card_ids,
        source_id=source_id,
        min_choices=0,
        max_choices=len(card_ids),
        callback_data={"surveil_count": count}
    )
    state.pending_choice = choice
    return choice


def create_target_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    legal_targets: list[str],
    prompt: str = "Choose a target",
    min_targets: int = 1,
    max_targets: int = 1,
    callback_data: dict = None
) -> PendingChoice:
    """
    Create a target selection choice.

    Args:
        state: The game state
        player_id: Player choosing targets
        source_id: Card/ability that needs targets
        legal_targets: List of valid target IDs
        prompt: UI prompt text
        min_targets: Minimum targets required
        max_targets: Maximum targets allowed
        callback_data: Additional data for when choice resolves

    Example:
        # ETB ability: "Exile target creature"
        legal = get_legal_creature_targets(state, controller_id)
        choice = create_target_choice(
            state, controller_id, permanent_id,
            legal_targets=legal,
            prompt="Choose a creature to exile"
        )
    """
    choice = PendingChoice(
        choice_type="target",
        player=player_id,
        prompt=prompt,
        options=legal_targets,
        source_id=source_id,
        min_choices=min_targets,
        max_choices=max_targets,
        callback_data=callback_data or {}
    )
    state.pending_choice = choice
    return choice


def create_discard_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    discard_count: int,
    prompt: str = None
) -> PendingChoice:
    """
    Create a discard choice.

    Args:
        state: The game state
        player_id: Player who must discard
        source_id: Card/ability causing the discard
        card_ids: IDs of cards in player's hand
        discard_count: Number of cards to discard

    Example:
        # "Discard two cards"
        hand_ids = [c.id for c in get_hand(player_id)]
        choice = create_discard_choice(state, player_id, source_id, hand_ids, 2)
    """
    choice = PendingChoice(
        choice_type="discard",
        player=player_id,
        prompt=prompt or f"Choose {discard_count} card(s) to discard",
        options=card_ids,
        source_id=source_id,
        min_choices=min(discard_count, len(card_ids)),
        max_choices=min(discard_count, len(card_ids))
    )
    state.pending_choice = choice
    return choice


def create_sacrifice_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    permanent_ids: list[str],
    sacrifice_count: int,
    prompt: str = None
) -> PendingChoice:
    """
    Create a sacrifice choice.

    Args:
        state: The game state
        player_id: Player who must sacrifice
        source_id: Card/ability causing the sacrifice
        permanent_ids: IDs of permanents that can be sacrificed
        sacrifice_count: Number of permanents to sacrifice

    Example:
        # "Sacrifice a creature"
        creature_ids = [c.id for c in get_creatures_you_control(state, player_id)]
        choice = create_sacrifice_choice(state, player_id, source_id, creature_ids, 1)
    """
    choice = PendingChoice(
        choice_type="sacrifice",
        player=player_id,
        prompt=prompt or f"Choose {sacrifice_count} permanent(s) to sacrifice",
        options=permanent_ids,
        source_id=source_id,
        min_choices=min(sacrifice_count, len(permanent_ids)),
        max_choices=min(sacrifice_count, len(permanent_ids))
    )
    state.pending_choice = choice
    return choice


def create_may_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    prompt: str,
    yes_handler: Callable[['PendingChoice', GameState], list[Event]] = None,
    no_handler: Callable[['PendingChoice', GameState], list[Event]] = None
) -> PendingChoice:
    """
    Create a "you may" choice.

    Args:
        state: The game state
        player_id: Player making the choice
        source_id: Card/ability offering the choice
        prompt: Question text (e.g., "Pay {2} to draw a card?")
        yes_handler: Function to call if player chooses yes
        no_handler: Function to call if player chooses no

    Example:
        # "You may pay {2}. If you do, draw a card."
        choice = create_may_choice(
            state, player_id, source_id,
            prompt="Pay {2} to draw a card?",
            yes_handler=lambda c, s: pay_and_draw(c, s)
        )
    """
    choice = PendingChoice(
        choice_type="may",
        player=player_id,
        prompt=prompt,
        options=[True, False],  # Yes or No
        source_id=source_id,
        min_choices=1,
        max_choices=1,
        callback_data={
            'yes_handler': yes_handler,
            'no_handler': no_handler
        }
    )
    state.pending_choice = choice
    return choice


def create_order_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    destination: str = "library_top",
    prompt: str = None
) -> PendingChoice:
    """
    Create a card ordering choice.

    Args:
        state: The game state
        player_id: Player ordering the cards
        source_id: Card/ability causing the ordering
        card_ids: IDs of cards to order
        destination: Where cards go ("library_top", "library_bottom", etc.)
        prompt: UI prompt text

    Example:
        # "Put them back in any order"
        choice = create_order_choice(
            state, player_id, source_id,
            card_ids=revealed_cards,
            prompt="Put these cards on top of your library in any order"
        )
    """
    choice = PendingChoice(
        choice_type="order",
        player=player_id,
        prompt=prompt or f"Arrange these {len(card_ids)} cards in order",
        options=card_ids,
        source_id=source_id,
        min_choices=len(card_ids),
        max_choices=len(card_ids),
        callback_data={"destination": destination}
    )
    state.pending_choice = choice
    return choice


def create_hand_reveal_choice(
    state: GameState,
    choosing_player_id: str,
    source_id: str,
    target_player_id: str,
    card_filter: Callable[[GameObject], bool] = None,
    min_choices: int = 1,
    max_choices: int = 1,
    prompt: str = None,
    handler: Callable = None,
    callback_data: dict = None
) -> PendingChoice:
    """
    Create a choice for revealing a player's hand and selecting cards from it.

    Args:
        state: The game state
        choosing_player_id: Player who makes the choice (typically the caster)
        source_id: Card/ability that needs the choice
        target_player_id: Player whose hand is being revealed
        card_filter: Optional filter function(card) -> bool for valid choices
        min_choices: Minimum cards to choose (0 for "may" effects)
        max_choices: Maximum cards to choose
        prompt: UI prompt text
        handler: Callback function(choice, selected, state) -> list[Event]
        callback_data: Additional data for when choice resolves

    Example:
        # Duress: Choose a noncreature, nonland card
        def noncreature_nonland(card):
            types = card.characteristics.types
            return CardType.CREATURE not in types and CardType.LAND not in types

        choice = create_hand_reveal_choice(
            state, caster_id, spell_id, opponent_id,
            card_filter=noncreature_nonland,
            handler=lambda c, s, gs: [Event(type=EventType.DISCARD, ...)]
        )
    """
    hand_key = f"hand_{target_player_id}"
    if hand_key not in state.zones:
        return None

    hand = state.zones[hand_key]
    valid_choices = []

    for card_id in hand.objects:
        card = state.objects.get(card_id)
        if card:
            if card_filter is None or card_filter(card):
                valid_choices.append(card_id)

    if not valid_choices and min_choices > 0:
        # No valid targets and selection is required - cannot create choice
        return None

    # Build callback data
    cb_data = callback_data.copy() if callback_data else {}
    cb_data['target_player'] = target_player_id
    if handler:
        cb_data['handler'] = handler

    choice = PendingChoice(
        choice_type="hand_reveal",
        player=choosing_player_id,
        prompt=prompt or "Choose a card from opponent's hand",
        options=valid_choices,
        source_id=source_id,
        min_choices=min(min_choices, len(valid_choices)),
        max_choices=min(max_choices, len(valid_choices)),
        callback_data=cb_data
    )
    state.pending_choice = choice
    return choice


# =============================================================================
# LEAVES-THE-BATTLEFIELD TRIGGER
# =============================================================================

def make_leaves_battlefield_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a leaves-the-battlefield trigger interceptor.

    Args:
        source_obj: The object with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: ZONE_CHANGE with from_zone_type == BATTLEFIELD and object_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return True

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='until_leaves'  # Fire once when leaving
    )
