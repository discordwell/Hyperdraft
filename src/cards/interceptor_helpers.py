"""
Interceptor Helper Functions

Common patterns for creating interceptors across all card sets.
"""

from typing import Callable, Optional
from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
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

    Event: ZONE_CHANGE with from_zone_type == BATTLEFIELD, to_zone_type == GRAVEYARD
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == obj.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

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
