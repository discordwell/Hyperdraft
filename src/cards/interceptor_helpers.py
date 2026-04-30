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
            if event.payload.get('object_id') != obj.id:
                return False
            # "Dies" means the object actually went to a graveyard. Replacement
            # effects (Rest in Peace, Unearth, etc.) can change the destination.
            resolved = state.objects.get(obj.id)
            return bool(resolved and resolved.zone == ZoneType.GRAVEYARD)

        # Sacrifice is also a "dies" event when it moves from battlefield to graveyard.
        if event.type == EventType.SACRIFICE:
            if event.payload.get('object_id') != obj.id:
                return False
            resolved = state.objects.get(obj.id)
            return bool(resolved and resolved.zone == ZoneType.GRAVEYARD)

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
    source_id = source_obj.id  # Capture for closures

    if power_mod != 0:
        def power_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_POWER:
                return False
            # Check that the source (lord) is on the battlefield
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
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
            # Check that the source (lord) is on the battlefield
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
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
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False

        # Check controller
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if controller_only and caster != obj.controller:
            return False

        # Check spell type
        if spell_type_filter:
            spell_types = set(event.payload.get('types', []))
            if not spell_types and event.payload.get('spell_type') is not None:
                spell_types = {event.payload.get('spell_type')}
            if not spell_types.intersection(spell_type_filter):
                return False

        # Check colors
        if color_filter:
            spell_colors = set(event.payload.get('colors', []))
            if not spell_colors and event.payload.get('color') is not None:
                spell_colors = {event.payload.get('color')}
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


# =============================================================================
# TARGETED TRIGGER HELPERS
# =============================================================================
# These helpers emit TARGET_REQUIRED events, letting the pipeline handle
# target selection and effect execution automatically.

def make_targeted_etb_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that requires targeting.

    Args:
        source_obj: The object with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', 'tap', 'pump', etc.)
        effect_params: Parameters for the effect (e.g., {'amount': 3} for damage)
        target_filter: Target filter type ('any', 'creature', 'opponent_creature',
                       'your_creature', 'opponent', 'player', 'nonland_permanent')
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)

    Example:
        # "When ~ enters, deal 2 damage to any target"
        make_targeted_etb_trigger(obj, effect='damage', effect_params={'amount': 2})

        # "When ~ enters, exile target creature an opponent controls"
        make_targeted_etb_trigger(obj, effect='exile', target_filter='opponent_creature')
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


def make_targeted_attack_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an attack trigger that requires targeting.

    Args:
        source_obj: The creature with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', 'tap', 'pump', etc.)
        effect_params: Parameters for the effect (e.g., {'amount': 2} for damage)
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)

    Example:
        # "When ~ attacks, deal 2 damage to any target"
        make_targeted_attack_trigger(obj, effect='damage', effect_params={'amount': 2})

        # "When ~ attacks, tap target creature an opponent controls"
        make_targeted_attack_trigger(obj, effect='tap', target_filter='opponent_creature')
    """
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_attack_trigger(source_obj, attack_effect)


def make_targeted_death_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create a death trigger that requires targeting.

    Args:
        source_obj: The creature with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', 'tap', 'pump', etc.)
        effect_params: Parameters for the effect (e.g., {'amount': 4} for damage)
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)

    Example:
        # "When ~ dies, deal 4 damage to any target"
        make_targeted_death_trigger(obj, effect='damage', effect_params={'amount': 4})
    """
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_death_trigger(source_obj, death_effect)


def make_targeted_damage_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None,
    combat_only: bool = False,
    noncombat_only: bool = False
) -> Interceptor:
    """
    Create a damage trigger that requires targeting.

    Args:
        source_obj: The creature with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', etc.)
        effect_params: Parameters for the effect
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)
        combat_only: If True, only trigger on combat damage
        noncombat_only: If True, only trigger on noncombat damage

    Example:
        # "When ~ deals combat damage, destroy target creature"
        make_targeted_damage_trigger(obj, effect='destroy', target_filter='creature',
                                     combat_only=True)
    """
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_damage_trigger(source_obj, damage_effect, combat_only=combat_only,
                               noncombat_only=noncombat_only)


def make_targeted_spell_cast_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None,
    controller_only: bool = True,
    spell_type_filter: set = None,
    color_filter: set = None
) -> Interceptor:
    """
    Create a spell cast trigger that requires targeting.

    Args:
        source_obj: The object with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', etc.)
        effect_params: Parameters for the effect
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)
        controller_only: If True, only trigger on spells cast by controller
        spell_type_filter: Only trigger on specific spell types (e.g., {CardType.INSTANT})
        color_filter: Only trigger on spells containing these colors

    Example:
        # "When you cast an instant or sorcery, deal 1 damage to any target"
        make_targeted_spell_cast_trigger(
            obj, effect='damage', effect_params={'amount': 1},
            spell_type_filter={CardType.INSTANT, CardType.SORCERY}
        )
    """
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_spell_cast_trigger(
        source_obj, spell_effect,
        controller_only=controller_only,
        spell_type_filter=spell_type_filter,
        color_filter=color_filter
    )


# =============================================================================
# DIVIDED DAMAGE/COUNTERS HELPERS
# =============================================================================

def make_divided_damage_etb_trigger(
    source_obj: GameObject,
    damage_amount: int,
    target_filter: str = 'any',
    max_targets: int = None,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that deals damage divided as you choose among targets.

    Example: "When ~ enters, deal 5 damage divided as you choose among any number of targets."

    Args:
        source_obj: The object with the trigger
        damage_amount: Total damage to divide (e.g., 5)
        target_filter: Target filter type ('any', 'creature', 'opponent_creature', etc.)
        max_targets: Max targets to select (default: damage_amount, since you must deal at least 1 each)
        prompt: Custom prompt text

    Returns:
        An ETB trigger interceptor
    """
    actual_max = max_targets if max_targets is not None else damage_amount

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': 'damage',
                'effect_params': {},  # Amount comes from divide_amount
                'target_filter': target_filter,
                'min_targets': 1,  # Must have at least 1 target
                'max_targets': actual_max,
                'optional': False,
                'divide_amount': damage_amount,
                'prompt': prompt or f"Deal {damage_amount} damage divided as you choose among any number of targets"
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


def make_divided_counters_etb_trigger(
    source_obj: GameObject,
    counter_amount: int,
    counter_type: str = '+1/+1',
    target_filter: str = 'creature',
    max_targets: int = None,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that puts counters divided as you choose among targets.

    Example: "When ~ enters, distribute 3 +1/+1 counters among any number of target creatures."

    Args:
        source_obj: The object with the trigger
        counter_amount: Total counters to distribute
        counter_type: Type of counter (default: '+1/+1')
        target_filter: Target filter type
        max_targets: Max targets to select
        prompt: Custom prompt text

    Returns:
        An ETB trigger interceptor
    """
    actual_max = max_targets if max_targets is not None else counter_amount

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': 'counter_add',
                'effect_params': {'counter_type': counter_type},
                'target_filter': target_filter,
                'min_targets': 1,
                'max_targets': actual_max,
                'optional': False,
                'divide_amount': counter_amount,
                'prompt': prompt or f"Distribute {counter_amount} {counter_type} counters among any number of target creatures"
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


# =============================================================================
# MULTI-EFFECT TARGETING HELPERS
# =============================================================================

def make_targeted_multi_effect_etb_trigger(
    source_obj: GameObject,
    effects: list[dict],
    target_filter: str = 'creature',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that applies multiple effects to targeted creature(s).

    Example: "When ~ enters, tap target creature. It doesn't untap during its controller's next untap step."

    Args:
        source_obj: The object with the trigger
        effects: List of effect dicts [{'effect': 'tap'}, {'effect': 'stun'}]
        target_filter: Target filter type
        min_targets: Minimum targets
        max_targets: Maximum targets
        optional: If True, may choose 0 targets
        prompt: Custom prompt text

    Supported effects:
        - 'tap' - Tap target
        - 'untap' - Untap target
        - 'stun' - Add stun counter (doesn't untap next untap step)
        - 'freeze' - Tap + stun combo
        - 'damage' with params: {'amount': N}
        - 'pump' with params: {'power_mod': N, 'toughness_mod': M}
        - 'counter_add' with params: {'counter_type': str, 'amount': N}
        - 'grant_keyword' with params: {'keyword': str}

    Returns:
        An ETB trigger interceptor
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effects': effects,  # Multi-effect list
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


def make_targeted_multi_effect_attack_trigger(
    source_obj: GameObject,
    effects: list[dict],
    target_filter: str = 'creature',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an attack trigger that applies multiple effects to targeted creature(s).

    Args:
        source_obj: The creature with the trigger
        effects: List of effect dicts
        target_filter: Target filter type
        min_targets: Minimum targets
        max_targets: Maximum targets
        optional: If True, may choose 0 targets
        prompt: Custom prompt text

    Returns:
        An attack trigger interceptor
    """
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effects': effects,
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_attack_trigger(source_obj, attack_effect)


# =============================================================================
# MODAL WITH TARGETING HELPERS
# =============================================================================

def make_modal_etb_trigger(
    source_obj: GameObject,
    modes: list[dict],
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger with modal choices, where some modes may require targeting.

    Example: "When ~ enters, choose one: Tap target creature; or Untap target creature."

    Args:
        source_obj: The object with the trigger
        modes: List of mode dicts, each with:
            - 'text': str - Description shown in UI
            - 'requires_targeting': bool - Whether this mode needs targets
            - 'effect': str - Effect type (for non-targeting or single-effect modes)
            - 'effects': list - Multi-effect list (overrides 'effect')
            - 'effect_params': dict - Parameters for the effect
            - 'target_filter': str - Target filter (only if requires_targeting)
            - 'min_targets': int - Min targets (default 1)
            - 'max_targets': int - Max targets (default 1)
            - 'optional': bool - If targets are optional
        min_modes: Minimum modes to choose (default 1)
        max_modes: Maximum modes to choose (default 1, use 2+ for "choose two")
        prompt: Custom prompt text

    Returns:
        An ETB trigger interceptor

    Example modes:
        modes=[
            {'text': 'Tap target creature', 'requires_targeting': True,
             'effect': 'tap', 'target_filter': 'creature'},
            {'text': 'Untap target creature', 'requires_targeting': True,
             'effect': 'untap', 'target_filter': 'creature'},
            {'text': 'Draw a card', 'requires_targeting': False,
             'effect': 'draw', 'effect_params': {'amount': 1}},
        ]
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Build options for UI
        options = []
        for i, mode in enumerate(modes):
            options.append({
                'id': str(i),
                'index': i,
                'label': mode.get('text', f'Mode {i + 1}'),
                'description': mode.get('description', ''),
                'requires_targeting': mode.get('requires_targeting', False)
            })

        # Create modal choice
        choice = PendingChoice(
            choice_type="modal_with_targeting",
            player=source_obj.controller,
            prompt=prompt or "Choose a mode:",
            options=options,
            source_id=source_obj.id,
            min_choices=min_modes,
            max_choices=max_modes,
            callback_data={
                'modes': modes,
                'controller': source_obj.controller
            }
        )
        state.pending_choice = choice
        return []  # Choice processing is handled when player submits

    return make_etb_trigger(source_obj, etb_effect)


# =============================================================================
# HEARTHSTONE-SPECIFIC HELPERS
# =============================================================================

def other_friendly_minions(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other minions you control (HS uses MINION, not CREATURE)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def friendly_minions(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: All minions you control including self."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def friendly_minions_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Your minions with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def other_friendly_minions_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other minions you control with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def get_enemy_targets(obj: GameObject, state: GameState) -> list[str]:
    """Get all valid enemy targets (hero + minions) for targeting effects."""
    enemies = []
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            enemies.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                enemies.append(mid)
    return enemies


def get_all_targets(obj: GameObject, state: GameState) -> list[str]:
    """Get all valid targets (all heroes + all minions) for targeting effects."""
    targets = []
    for pid, player in state.players.items():
        if player.hero_id:
            targets.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                targets.append(mid)
    return targets


def get_friendly_minions(obj: GameObject, state: GameState, exclude_self: bool = True) -> list[str]:
    """Get all friendly minion IDs on the battlefield."""
    minions = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller == obj.controller and CardType.MINION in m.characteristics.types:
                if not exclude_self or m.id != obj.id:
                    minions.append(mid)
    return minions


def get_enemy_minions(obj: GameObject, state: GameState) -> list[str]:
    """Get all enemy minion IDs on the battlefield."""
    minions = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                minions.append(mid)
    return minions


def get_all_minions(state: GameState) -> list[str]:
    """Get all minion IDs on the battlefield."""
    minions = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                minions.append(mid)
    return minions


def get_enemy_hero_id(obj: GameObject, state: GameState) -> str | None:
    """Get the opponent's hero object ID."""
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            return player.hero_id
    return None


def make_enrage_trigger(
    source_obj: GameObject,
    attack_bonus: int = 0,
    keywords: set[str] | None = None
) -> list[Interceptor]:
    """
    Create an Enrage effect: while damaged, gain +attack and/or keywords.

    Works via QUERY interceptors that check obj.state.damage > 0.
    """
    interceptors = []
    source_id = source_obj.id

    if attack_bonus > 0:
        def enrage_power_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_POWER:
                return False
            if event.payload.get('object_id') != source_id:
                return False
            source = state.objects.get(source_id)
            return bool(source and source.zone == ZoneType.BATTLEFIELD and source.state.damage > 0)

        def enrage_power_handler(event: Event, state: GameState) -> InterceptorResult:
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + attack_bonus
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=enrage_power_filter,
            handler=enrage_power_handler,
            duration='while_on_battlefield'
        ))

    if keywords:
        def enrage_ability_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_ABILITIES:
                return False
            if event.payload.get('object_id') != source_id:
                return False
            source = state.objects.get(source_id)
            return bool(source and source.zone == ZoneType.BATTLEFIELD and source.state.damage > 0)

        def enrage_ability_handler(event: Event, state: GameState) -> InterceptorResult:
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

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=enrage_ability_filter,
            handler=enrage_ability_handler,
            duration='while_on_battlefield'
        ))

    return interceptors


def make_spell_damage_boost(source_obj: GameObject, amount: int = 1) -> Interceptor:
    """
    Create a Spell Damage +N interceptor.

    Increases damage from spells controlled by the same player by +N.
    """
    source_id = source_obj.id

    def spell_dmg_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('from_spell'):
            return False
        # Only boost spells from same controller
        source = state.objects.get(event.source)
        if not source:
            return False
        # Check source minion is still on battlefield
        boost_source = state.objects.get(source_id)
        if not boost_source or boost_source.zone != ZoneType.BATTLEFIELD:
            return False
        return source.controller == boost_source.controller

    def spell_dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + amount
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=spell_dmg_filter,
        handler=spell_dmg_handler,
        duration='while_on_battlefield'
    )


def make_end_of_turn_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """Create an end-of-turn trigger (HS: fires at PHASE_END with phase='end')."""
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_END:
            return False
        if event.payload.get('phase') != 'end':
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


def make_start_of_turn_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """Create a start-of-turn trigger (HS: fires at TURN_START)."""
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TURN_START:
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


def make_whenever_healed_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    self_only: bool = True
) -> Interceptor:
    """Create a 'whenever this minion is healed' trigger."""
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        if self_only:
            return event.payload.get('target') == source_id
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


def make_whenever_takes_damage_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """Create a 'whenever this minion takes damage' trigger."""
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == source_id

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


def make_modal_spell_trigger(
    source_obj: GameObject,
    modes: list[dict],
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: str = None,
    spell_type_filter: set = None,
    controller_only: bool = True
) -> Interceptor:
    """
    Create a spell cast trigger with modal choices.

    Similar to make_modal_etb_trigger but triggers on spell cast.

    Args:
        source_obj: The object with the trigger
        modes: List of mode dicts (same format as make_modal_etb_trigger)
        min_modes: Minimum modes to choose
        max_modes: Maximum modes to choose
        prompt: Custom prompt text
        spell_type_filter: Only trigger on specific spell types
        controller_only: Only trigger on controller's spells

    Returns:
        A spell cast trigger interceptor
    """
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        options = []
        for i, mode in enumerate(modes):
            options.append({
                'id': str(i),
                'index': i,
                'label': mode.get('text', f'Mode {i + 1}'),
                'description': mode.get('description', ''),
                'requires_targeting': mode.get('requires_targeting', False)
            })

        choice = PendingChoice(
            choice_type="modal_with_targeting",
            player=source_obj.controller,
            prompt=prompt or "Choose a mode:",
            options=options,
            source_id=source_obj.id,
            min_choices=min_modes,
            max_choices=max_modes,
            callback_data={
                'modes': modes,
                'controller': source_obj.controller
            }
        )
        state.pending_choice = choice
        return []

    return make_spell_cast_trigger(
        source_obj, spell_effect,
        controller_only=controller_only,
        spell_type_filter=spell_type_filter
    )


# =============================================================================
# Hearthstone Board Adjacency
# =============================================================================

def get_adjacent_minions(obj_id: str, state) -> tuple[str | None, str | None]:
    """
    Get the minion IDs adjacent (left and right) to obj_id on the battlefield.
    Returns (left_id, right_id) — either may be None if at the edge or no neighbor.
    Only considers minions controlled by the same player.
    """
    obj = state.objects.get(obj_id)
    if not obj:
        return (None, None)

    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return (None, None)

    # Build ordered list of minions for this controller
    controller_minions = []
    for mid in battlefield.objects:
        m = state.objects.get(mid)
        if m and m.controller == obj.controller and CardType.MINION in m.characteristics.types:
            controller_minions.append(mid)

    if obj_id not in controller_minions:
        return (None, None)

    idx = controller_minions.index(obj_id)
    left = controller_minions[idx - 1] if idx > 0 else None
    right = controller_minions[idx + 1] if idx < len(controller_minions) - 1 else None
    return (left, right)


def get_adjacent_enemy_minions(target_id: str, state) -> list[str]:
    """
    Get the enemy minion IDs adjacent to target_id on the battlefield.
    Used for Cone of Cold, Betrayal, etc. where we target an enemy minion
    and need its neighbors (among the enemy's board).
    Returns list of adjacent IDs (0-2 elements).
    """
    target = state.objects.get(target_id)
    if not target:
        return []

    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    # Build ordered list of minions for the target's controller
    controller_minions = []
    for mid in battlefield.objects:
        m = state.objects.get(mid)
        if m and m.controller == target.controller and CardType.MINION in m.characteristics.types:
            controller_minions.append(mid)

    if target_id not in controller_minions:
        return []

    idx = controller_minions.index(target_id)
    adjacent = []
    if idx > 0:
        adjacent.append(controller_minions[idx - 1])
    if idx < len(controller_minions) - 1:
        adjacent.append(controller_minions[idx + 1])
    return adjacent


# =============================================================================
# Hearthstone Cost Reduction Helpers
# =============================================================================

def make_cost_reduction_aura(obj, card_type_filter, amount, floor=0, state=None):
    """
    Create interceptors that add/remove a cost modifier while obj is on the battlefield.

    Directly applies the modifier immediately (setup_interceptors is only called
    when the object enters the battlefield), and registers cleanup interceptors
    for when it leaves.

    Args:
        obj: The source minion (e.g. Sorcerer's Apprentice)
        card_type_filter: CardType to reduce cost for (e.g. CardType.SPELL)
        amount: How much to reduce (positive = reduce, negative = increase)
        floor: Minimum cost (0 for most, 1 for Summoning Portal)
        state: GameState — used to directly add the modifier

    Returns list of Interceptors.
    """
    modifier_id = f"aura_{obj.id}"

    # Directly add the cost modifier now — setup_interceptors is only called
    # when the object is on the battlefield, so no need for an ETB interceptor.
    if state:
        player = state.players.get(obj.controller)
        if player:
            player.cost_modifiers.append({
                'id': modifier_id,
                'card_type': card_type_filter,
                'amount': amount,
                'duration': 'while_on_battlefield',
                'source': obj.id,
                'floor': floor,
            })

    def leave_filter(event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('object_id') == obj.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD)

    def remove_modifier(event, state):
        player = state.players.get(obj.controller)
        if player:
            player.cost_modifiers = [m for m in player.cost_modifiers if m.get('id') != modifier_id]
        return InterceptorResult(action=InterceptorAction.PASS)

    def death_filter(event, state) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=leave_filter,
            handler=remove_modifier,
            duration='permanent'
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=death_filter,
            handler=remove_modifier,
            duration='permanent'
        ),
    ]


def make_cant_attack(source_obj: GameObject) -> Interceptor:
    """
    Create a "Can't Attack" interceptor (HS: Ancient Watcher, Ragnaros).
    PREVENT interceptor on ATTACK_DECLARED when attacker is this object.
    Also marks the object with a 'cant_attack' keyword so has_ability() can find it.
    """
    # Mark with keyword so has_ability('cant_attack', ...) returns True
    if not any(a.get('keyword') == 'cant_attack' for a in source_obj.characteristics.abilities):
        source_obj.characteristics.abilities.append({'keyword': 'cant_attack'})

    source_id = source_obj.id

    def cant_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == source_id

    def cant_attack_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=source_obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_attack_filter,
        handler=cant_attack_handler,
        duration='while_on_battlefield'
    )


def add_one_shot_cost_reduction(player, card_type_filter, amount, duration='this_turn'):
    """
    Add a one-shot cost reduction modifier to a player.
    Used by Preparation ("next spell costs 3 less"), Kirin Tor Mage ("next Secret costs 0").

    Args:
        player: Player object to add modifier to
        card_type_filter: CardType to reduce (e.g. CardType.SPELL, CardType.SECRET)
        amount: How much to reduce
        duration: 'this_turn' (cleared at end of turn) or 'next_only' (consumed after one use)
    """
    player.cost_modifiers.append({
        'id': f"oneshot_{new_id()}",
        'card_type': card_type_filter,
        'amount': amount,
        'duration': duration,
        'uses_remaining': 1,
    })


# =============================================================================
# GAP-FILLER FILTERS (parity with src/engine/abilities/targets.py)
# =============================================================================

def all_creatures_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: Every creature on the battlefield (both players).

    Mirrors ``AllCreaturesFilter`` from the abilities DSL.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types)
    return filter_fn


def opponent_creatures_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: Creatures controlled by opponents of ``source``'s controller.

    Mirrors ``OpponentCreaturesFilter`` from the abilities DSL.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller != source.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types)
    return filter_fn


def nonland_permanents_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: Nonland permanents on the battlefield.

    Mirrors the ``NonlandPermanent`` trigger-target predicate.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.zone == ZoneType.BATTLEFIELD and
                CardType.LAND not in target.characteristics.types)
    return filter_fn


# =============================================================================
# GAP-FILLER INTERCEPTORS
# =============================================================================

def type_grant_interceptor(
    source_obj: GameObject,
    added_types: list[str],
    duration: str = 'while_on_battlefield',
    affects_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> Interceptor:
    """Create a QUERY_TYPES interceptor that adds subtypes to matching objects.

    Args:
        source_obj: The permanent granting the subtypes.
        added_types: List of subtype strings to inject (e.g. ``["Zombie"]``).
        duration: Interceptor duration tag (default: while_on_battlefield).
        affects_filter: Predicate ``(target, state) -> bool``. If omitted,
            grants to every object on the battlefield (same shape as TypeGrant
            with a permissive filter). Callers almost always want to pass a
            filter such as ``creatures_you_control(source_obj)``.

    Event: QUERY_TYPES. Transforms ``payload['subtypes']`` to include added_types.
    """
    source_id = source_obj.id
    types_to_add = list(added_types)
    filter_fn = affects_filter

    def type_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TYPES:
            return False
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if filter_fn is None:
            return True
        return filter_fn(target, state)

    def type_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        subtypes = set(new_event.payload.get('subtypes', set()))
        for t in types_to_add:
            subtypes.add(t)
        new_event.payload['subtypes'] = subtypes
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=type_filter,
        handler=type_handler,
        duration=duration,
    )


def make_cant_block(
    source_obj: GameObject,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> Interceptor:
    """Create a PREVENT interceptor on BLOCK_DECLARED.

    If ``filter_fn`` is None, prevents blocks only when the blocker *is*
    ``source_obj`` itself ("{this} can't block"). When given a filter, prevents
    any blocker matching the filter (lord-style "creatures you control can't
    block"). Mirrors ``CantBlockEffect`` from the abilities DSL.
    """
    source_id = source_obj.id
    predicate = filter_fn

    def cant_block_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        blocker_id = event.payload.get('blocker_id')
        if predicate is None:
            return blocker_id == source_id
        blocker = state.objects.get(blocker_id)
        if not blocker:
            return False
        return predicate(blocker, state)

    def cant_block_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_block_filter,
        handler=cant_block_handler,
        duration='while_on_battlefield',
    )


# =============================================================================
# REPLACEMENT HELPERS
# =============================================================================
# Thin re-exports of the framework defined in src/engine/replacements.py so
# card files can import everything they need from interceptor_helpers in the
# usual way.

from src.engine.replacements import (  # noqa: E402  (re-export below)
    make_replacement_interceptor,
    make_life_gain_replacer,
    make_life_gain_prevention,
    make_draw_replacer,
    make_counter_doubler,
    make_dies_to_exile_replacer,
    make_damage_doubler,
    make_skip_to_graveyard_replacer,
    make_graveyard_to_exile_replacer,
)


# =============================================================================
# LIBRARY SEARCH HELPERS
# =============================================================================
#
# These wrap src/engine/library_search.py with card-friendly defaults. Cards
# typically just need an ETB-style "search your library for an X, put it into
# your hand, then shuffle." All of these helpers create a PendingChoice on
# state.pending_choice and return [] (no events) — the card's effect_fn should
# return whatever this helper returns.
#
# Example (Rune-Scarred Demon):
#     def runescarred_demon_setup(obj, state):
#         def effect_fn(event, state):
#             return open_library_search(
#                 state, obj.controller, obj.id,
#                 filter_fn=any_card_filter(),
#                 destination="hand",
#             )
#         return [make_etb_trigger(obj, effect_fn)]


def open_library_search(
    state: GameState,
    player_id: str,
    source_id: str,
    *,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    min_count: int = 0,
    max_count: int = 1,
    destination: str = "hand",
    reveal: bool = False,
    shuffle_after: bool = True,
    tapped: bool = False,
    prompt: Optional[str] = None,
    optional: bool = True,
    on_chosen: Optional[Callable] = None,
    extra_callback_data: Optional[dict] = None,
) -> list[Event]:
    """Open a library-search PendingChoice. Returns [] (use as the effect_fn return).

    See `src.engine.library_search.create_library_search_choice` for full
    parameter documentation.
    """
    from src.engine.library_search import create_library_search_choice

    create_library_search_choice(
        state,
        player_id,
        source_id,
        filter_fn=filter_fn,
        min_count=min_count,
        max_count=max_count,
        destination=destination,
        reveal=reveal,
        shuffle_after=shuffle_after,
        tapped=tapped,
        prompt=prompt,
        optional=optional,
        on_chosen=on_chosen,
        extra_callback_data=extra_callback_data,
    )
    return []


def make_library_search_etb_trigger(
    source_obj: GameObject,
    *,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    destination: str = "hand",
    reveal: bool = False,
    shuffle_after: bool = True,
    tapped: bool = False,
    max_count: int = 1,
    optional: bool = True,
    prompt: Optional[str] = None,
    on_chosen: Optional[Callable] = None,
) -> Interceptor:
    """Convenience: ETB trigger that opens a library search with the given filter.

    Common pattern for tutor creatures like Rune-Scarred Demon, Fierce Empath,
    Vile Entomber, Hoarding Dragon, Campus Guide, etc.
    """
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state,
            source_obj.controller,
            source_obj.id,
            filter_fn=filter_fn,
            destination=destination,
            reveal=reveal,
            shuffle_after=shuffle_after,
            tapped=tapped,
            max_count=max_count,
            optional=optional,
            prompt=prompt,
            on_chosen=on_chosen,
        )
    return make_etb_trigger(source_obj, effect_fn)


# --- Library filter shortcuts (re-exports of the engine module's factories) ---

def basic_land_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: any basic land card."""
    from src.engine.library_search import is_basic_land
    return is_basic_land()


def basic_subtype_filter(subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: a basic with the given subtype (e.g. 'Forest', 'Mountain')."""
    from src.engine.library_search import is_basic_with_subtype
    return is_basic_with_subtype(subtype)


def creature_filter_lib() -> Callable[[GameObject, GameState], bool]:
    """Filter: any creature card."""
    from src.engine.library_search import is_card_type
    return is_card_type(CardType.CREATURE)


def artifact_filter_lib() -> Callable[[GameObject, GameState], bool]:
    """Filter: any artifact card."""
    from src.engine.library_search import is_card_type
    return is_card_type(CardType.ARTIFACT)


def enchantment_filter_lib() -> Callable[[GameObject, GameState], bool]:
    """Filter: any enchantment card."""
    from src.engine.library_search import is_card_type
    return is_card_type(CardType.ENCHANTMENT)


def creature_with_mv_at_least(min_mv: int) -> Callable[[GameObject, GameState], bool]:
    """Filter: creature card with mana value >= min_mv."""
    from src.engine.library_search import is_creature_with_mv_at_least
    return is_creature_with_mv_at_least(min_mv)


def instant_or_sorcery_with_mv(target_mv: int) -> Callable[[GameObject, GameState], bool]:
    """Filter: instant or sorcery with exactly target_mv mana value."""
    from src.engine.library_search import is_instant_or_sorcery_with_mv
    return is_instant_or_sorcery_with_mv(target_mv)


def subtype_filter_lib(subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: any card with the given subtype (e.g. 'Aura', 'Equipment')."""
    from src.engine.library_search import is_subtype
    return is_subtype(subtype)


def any_card_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: any card in library (unconditional tutor)."""
    from src.engine.library_search import any_card
    return any_card()


# === SAGA HELPERS ===
# MTG Saga subsystem helpers. The engine-level event handling lives in
# ``src/engine/saga.py``; this section provides the card-level helper that
# wires up a Saga's ETB lore counter, draw-step lore counter, chapter
# triggers, and final-chapter sacrifice.


def make_saga_setup(
    source_obj: GameObject,
    chapter_handlers: dict[int, Callable[[GameObject, GameState], list[Event]]],
    final_chapter: Optional[int] = None,
) -> list[Interceptor]:
    """
    Build the interceptors for a Saga enchantment.

    Args:
        source_obj: The Saga ``GameObject``.
        chapter_handlers: ``{chapter_number: effect_fn}``. Each ``effect_fn``
            takes ``(saga_obj, state)`` and returns a list of follow-up events
            to emit when that chapter triggers. Multiple chapters that share an
            ability (e.g. "I, II — ...") should map to the same callable.
        final_chapter: Optional explicit final-chapter number. If omitted, it
            is inferred from the rules text (``"Sacrifice after <ROMAN>."``)
            and falls back to ``max(chapter_handlers)``.

    Returns:
        A list of interceptors:

        1. ``REACT`` on ZONE_CHANGE -> battlefield (this Saga): emits
           ``SAGA_LORE_ADDED`` so chapter I fires immediately on entry.
        2. ``REACT`` on PHASE_START phase ``'draw'`` while controller is the
           active player: emits ``SAGA_LORE_ADDED`` for the next chapter.
        3. ``REACT`` on ``SAGA_CHAPTER`` for this Saga: dispatches to the
           registered chapter handler and queues a final-chapter SACRIFICE
           event.

    Notes:
        * Chapter handlers may return ``[]`` for chapters whose effect is not
          fully implementable yet (e.g. interactive targeting). The Saga still
          ticks through every chapter and is sacrificed normally.
        * ``source_obj.card_def._saga_final_chapter`` is set to ``final_chapter``
          if provided; the engine reads that override when computing the final
          chapter for this Saga.
    """
    saga_id = source_obj.id
    controller_id = source_obj.controller

    # Resolve the final chapter:
    #   1. explicit argument
    #   2. card_def._saga_final_chapter override (set by previous calls)
    #   3. text parse via engine helper (fallback inside engine)
    #   4. last fallback: max chapter in handlers
    if final_chapter is None:
        from src.engine.saga import _saga_final_chapter as _engine_final
        final_chapter = _engine_final(source_obj)
        if chapter_handlers:
            final_chapter = max(final_chapter, max(chapter_handlers.keys()))
    # Stash explicit override on the card_def so the engine handler honors it
    # consistently across the Saga's lifetime.
    if source_obj.card_def is not None:
        try:
            source_obj.card_def._saga_final_chapter = int(final_chapter)
        except Exception:
            pass

    # ---------------------------------------------------------------- ETB lore
    def etb_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get('object_id') == saga_id
            and event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD
        )

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SAGA_LORE_ADDED,
                payload={'object_id': saga_id, 'amount': 1},
                source=saga_id,
                controller=controller_id,
            )],
        )

    etb_interceptor = Interceptor(
        id=new_id(),
        source=saga_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield',
    )

    # --------------------------------------------- Draw-step lore (post-draw)
    def draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'draw':
            return False
        # Only on this Saga's controller's turn.
        saga = state.objects.get(saga_id)
        if saga is None or saga.zone != ZoneType.BATTLEFIELD:
            return False
        if state.active_player != saga.controller:
            return False
        return True

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SAGA_LORE_ADDED,
                payload={'object_id': saga_id, 'amount': 1},
                source=saga_id,
                controller=controller_id,
            )],
        )

    draw_interceptor = Interceptor(
        id=new_id(),
        source=saga_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=draw_filter,
        handler=draw_handler,
        duration='while_on_battlefield',
    )

    # ----------------------------------------- Chapter dispatcher + sacrifice
    handlers_by_chapter = dict(chapter_handlers or {})

    def chapter_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.SAGA_CHAPTER
            and event.payload.get('object_id') == saga_id
        )

    def chapter_handler(event: Event, state: GameState) -> InterceptorResult:
        chapter = int(event.payload.get('chapter', 0) or 0)
        # Use the live final_chapter — _saga_final_chapter() reads from card_def.
        from src.engine.saga import _saga_final_chapter as _engine_final
        live_final = _engine_final(source_obj) if source_obj else final_chapter
        new_events: list[Event] = []
        # Dispatch the chapter effect (if any).
        cb = handlers_by_chapter.get(chapter)
        if cb is not None:
            try:
                produced = cb(source_obj, state) or []
            except Exception:
                produced = []
            new_events.extend(list(produced))
        # Final chapter -> sacrifice the Saga.
        if chapter >= int(live_final or 0):
            new_events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': saga_id, 'player': controller_id},
                source=saga_id,
                controller=controller_id,
            ))
# === CRIME HELPERS ===
# =============================================================================
# OTJ Crime mechanic: a player commits a crime when they target an opponent,
# an opponent's permanent, or a card in an opponent's graveyard with a spell
# or ability.
#
# Crime detection is wired in:
#   - src/engine/game.py        (after target choices resolve)
#   - src/engine/priority.py    (when a spell with pre-chosen targets is cast)
#
# These helpers thinly wrap the engine API so card scripts don't import
# ``src.engine.crime`` directly.

def is_crime_committed(player: str, state: GameState) -> bool:
    """Return True if ``player`` has committed a crime this turn."""
    from src.engine.crime import is_crime_committed as _impl
    return _impl(player, state)


def crime_count(player: str, state: GameState) -> int:
    """Return how many crimes ``player`` has committed this turn."""
    from src.engine.crime import crime_count as _impl
    return _impl(player, state)


def make_crime_committed_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    once_per_turn: bool = False,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None,
) -> Interceptor:
    """Create a "whenever you commit a crime" trigger.

    Fires on ``EventType.CRIME_COMMITTED`` for the source's controller.

    Args:
        source_obj: The object with the trigger.
        effect_fn: Function(event, state) -> list[Event] when trigger fires.
        once_per_turn: If True, only fires once per turn (uses
            ``state.turn_data['crime_trigger_<source_id>_<turn>']``).
        filter_fn: Optional extra filter ``(event, state, source) -> bool``.

    Event: CRIME_COMMITTED
    Payload: {'player': str, 'targets': list, 'source': str}
    Priority: REACT
    """
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CRIME_COMMITTED:
            return False
        # Look up the source object live (the closure capture may be stale
        # if the controller changed via Gain Control etc.).
        live = state.objects.get(source_id, source_obj)
        if event.payload.get('player') != live.controller:
            return False
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            if state.turn_data.get(key):
                return False
        if filter_fn is not None and not filter_fn(event, state, live):
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            state.turn_data[key] = True
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    chapter_interceptor = Interceptor(
        id=new_id(),
        source=saga_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=chapter_filter,
        handler=chapter_handler,
        duration='while_on_battlefield',
    )

    return [etb_interceptor, draw_interceptor, chapter_interceptor]


# =============================================================================
# WARP HELPERS
# =============================================================================
#
# Edge of Eternities (EOE) Warp mechanic.
#
# Warp lets a card be cast from your hand for an alternate (warp) cost. The
# resulting permanent is exiled at the beginning of the next end step, and
# may then be cast again from exile on a later turn (paying its printed mana
# cost). Each card may only be warp-cast once per game.
#
# The actual cast wiring (alternate cost, end-step exile registration) lives
# in ``src/engine/warp.py`` and ``src/engine/priority.py``. The helper below
# is for card scripts that want to attach a Warp ability to a card.
#
# Usage:
#
#     CARD = make_creature(
#         name="Nova Hellkite",
#         power=4, toughness=4,
#         mana_cost="{4}{R}{R}",
#         text="Flying, haste\nWhen this creature enters, it deals 1 damage "
#              "to target creature an opponent controls.\nWarp {2}{R} (...)",
#         setup_interceptors=make_warp_setup(
#             "{2}{R}",
#             inner_setup=nova_hellkite_etb_setup,  # optional
#         ),
#     )
#
# The ``inner_setup`` argument lets you compose Warp with the card's
# existing ETB/death/etc. setup function. If None, only Warp's bookkeeping
# is set up (rare — most warp cards have other abilities).


def make_warp_setup(
    warp_cost: str,
    inner_setup: Optional[Callable[[GameObject, GameState], list[Interceptor]]] = None,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    """Wrap a card's setup_interceptors with Warp end-step-exile bookkeeping.

    The returned function:
      1. Calls ``inner_setup`` if provided, collecting its interceptors.
      2. If the object is currently warp-pending (was cast for its warp
         cost), schedules the one-shot end-step exile interceptor.

    The ``warp_cost`` argument is currently informational; the engine
    parses the cost from the card's rules text. Passing it explicitly keeps
    card definitions self-documenting.

    Args:
        warp_cost: The warp cost string (e.g. "{2}{R}{R}"). Informational.
        inner_setup: Optional existing setup_interceptors function to compose.

    Returns:
        A new setup_interceptors function suitable for ``CardDefinition``.
    """
    # Imported lazily to avoid a circular import at module load time.
    from src.engine.warp import (
        is_warp_pending,
        schedule_warp_exile_for_object,
    )

    def _warp_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors: list[Interceptor] = []
        if inner_setup is not None:
            try:
                inner = inner_setup(obj, state) or []
                interceptors.extend(inner)
            except Exception as e:
                # Don't crash the cast pipeline if the inner setup raises;
                # log and continue. Matches existing engine resilience.
                import logging
                logging.getLogger(__name__).warning(
                    "Warp inner_setup for %s raised: %s", obj.name, e
                )

        if is_warp_pending(obj):
            interceptor = schedule_warp_exile_for_object(state, obj, obj.controller)
            if interceptor is not None and interceptor.id in state.interceptors:
                # Already registered against obj.interceptor_ids by
                # schedule_warp_exile_for_object; do not duplicate here.
                pass

        return interceptors

    # Annotate so `make_warp_setup` results are easy to spot in debugging.
    _warp_setup.__name__ = (
        f"warp_setup({warp_cost})"
        if inner_setup is None
        else f"warp_setup({warp_cost})+{getattr(inner_setup, '__name__', 'inner')}"
    )
    setattr(_warp_setup, "_warp_cost", warp_cost)
    setattr(_warp_setup, "_warp_inner", inner_setup)
    return _warp_setup

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )
# === SPM MECHANICS HELPERS ===
# =============================================================================
# Helpers for the Marvel's Spider-Man set's two alt-cast mechanics:
#   * Web-slinging — alt cost from hand: pay {alt_cost} AND return a tapped
#     creature you control to its owner's hand instead of the spell's mana cost.
#   * Mayhem — alt cost from graveyard if the card was discarded this turn
#     (sorcery-speed timing).
#
# The engine's priority/cast layer already understands the printed Mayhem cost
# (see ``priority._get_mayhem_cost``) and tags resulting cast events with
# ``payload['mayhem']=True``. These helpers add the *card-side* book-keeping:
# they (a) stamp the alt cost onto the card definition so it survives the
# engine's cast-cost lookups, and (b) register a DISCARD interceptor so we
# can populate ``state.turn_data['discarded_card_ids']`` for downstream
# triggers that don't go through the priority layer.
# =============================================================================


def make_web_slinging_setup(
    alt_cost,
    *,
    on_websling_cast: Optional[Callable] = None,
):
    """Build a ``setup_interceptors`` function that wires Web-slinging.

    ``alt_cost`` is the web-slinging mana cost (a string like ``"{W}"`` or a
    pre-parsed ``ManaCost``). It is stamped onto ``obj.card_def.web_slinging_cost``
    so the priority/cast layer (and any hand-cast option logic) can see it
    without re-parsing the rules text.

    ``on_websling_cast`` is an optional callback invoked when *this card* is
    cast via web-slinging. It receives ``(event, state, obj)`` and returns a
    list of follow-up events. Use it for Sensational Save and similar
    "if cast for its web-slinging cost, ..." triggers.
    """
    from src.engine.spm_mechanics import register_web_slinging, track_web_slinging_cast

    def setup(obj, state):
        # Stamp the alt cost on the CardDefinition so other systems can see it.
        if getattr(obj, "card_def", None) is not None:
            register_web_slinging(obj.card_def, alt_cost)

        source_id = obj.id

        # React to the moment *this card* is cast for its web-slinging cost.
        # Convention: the cast event sets payload['web_slinging']=True when the
        # alt cost is paid (mirrors the existing payload['mayhem'] flag).
        # We always install the tracking interceptor so downstream "if this was
        # cast via web-slinging" ETB triggers can ask state.turn_data.
        def cast_filter(event: Event, state: GameState) -> bool:
            if event.type not in (EventType.CAST, EventType.SPELL_CAST):
                return False
            payload = event.payload or {}
            if not payload.get('web_slinging'):
                return False
            return payload.get('spell_id') == source_id or payload.get('card_id') == source_id

        def cast_handler(event: Event, state: GameState) -> InterceptorResult:
            payload = event.payload or {}
            try:
                returned_mv = int(payload.get('web_slinging_returned_mv', 0) or 0)
            except (TypeError, ValueError):
                returned_mv = 0
            track_web_slinging_cast(state, source_id, returned_mv)

            new_events: list = []
            if on_websling_cast is not None:
                new_events = list(on_websling_cast(event, state, obj) or [])
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=cast_filter,
            handler=cast_handler,
            duration='forever',
        )]

    return setup


def make_mayhem_setup(
    mayhem_cost,
    *,
    on_mayhem_cast: Optional[Callable] = None,
):
    """Build a ``setup_interceptors`` function that wires Mayhem.

    ``mayhem_cost`` is the alt cast cost (string or ``ManaCost``) and is
    stamped onto ``obj.card_def.mayhem_cost`` so it survives lookup and is
    visible to the engine's graveyard-cast option list.

    The returned setup also installs a DISCARD interceptor that records this
    card's id in ``state.turn_data['discarded_card_ids']`` whenever it is
    discarded, so downstream cards can ask "was this discarded this turn?"
    without consulting ``ObjectState.last_discarded_turn`` directly.

    ``on_mayhem_cast`` is an optional callback invoked when this card is
    cast via mayhem (mirrors ``make_web_slinging_setup``).
    """
    from src.engine.spm_mechanics import register_mayhem, track_discard

    def setup(obj, state):
        if getattr(obj, "card_def", None) is not None:
            register_mayhem(obj.card_def, mayhem_cost)

        interceptors: list = []

        source_id = obj.id

        # Discard tracker: record this object's id in turn_data when it's
        # discarded. Active forever so it works in any zone (hand at the moment
        # of discard, graveyard afterwards).
        def discard_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.DISCARD:
                return False
            payload = event.payload or {}
            return payload.get('object_id') == source_id

        def discard_handler(event: Event, state: GameState) -> InterceptorResult:
            track_discard(state, source_id)
            return InterceptorResult(action=InterceptorAction.PASS)

        interceptors.append(Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=discard_filter,
            handler=discard_handler,
            duration='forever',
        ))

        if on_mayhem_cast is not None:
            def cast_filter(event: Event, state: GameState) -> bool:
                if event.type not in (EventType.CAST, EventType.SPELL_CAST):
                    return False
                payload = event.payload or {}
                if not payload.get('mayhem'):
                    return False
                return payload.get('spell_id') == source_id or payload.get('card_id') == source_id

            def cast_handler(event: Event, state: GameState) -> InterceptorResult:
                new_events = on_mayhem_cast(event, state, obj) or []
                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=list(new_events),
                )

            interceptors.append(Interceptor(
                id=new_id(),
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.REACT,
                filter=cast_filter,
                handler=cast_handler,
                duration='forever',
            ))

        return interceptors

    return setup


def combine_setups(*setup_fns):
    """Combine multiple ``setup_interceptors`` callables into one.

    Convenience helper for cards whose setup is "wire web-slinging AND wire
    an ETB trigger AND wire a static effect". Each returned setup runs in
    order; their interceptor lists are concatenated. ``None`` entries are
    skipped.
    """
    fns = tuple(fn for fn in setup_fns if fn is not None)

    def combined(obj, state):
        out: list = []
        for fn in fns:
            try:
                got = fn(obj, state) or []
            except Exception:
                got = []
            out.extend(got)
        return out

    return combined
# === LANDER HELPERS ===
# =============================================================================
# Edge of Eternities — Lander mechanic. Re-exports + trigger helpers for cards
# that create Lander tokens on ETB / death.
from src.engine.lander import (
    make_lander_token_event,
    make_lander_token_events,
    is_lander,
    landers_sacced_this_turn,
)


def make_lander_etb_trigger(obj):
    """ETB: create one Lander token for obj.controller."""
    def filt(event, state):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[make_lander_token_event(obj.controller, source_obj_id=obj.id)],
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_lander_death_trigger(obj):
    """Death: create one Lander token for obj.controller."""
    def filt(event, state):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[make_lander_token_event(obj.controller, source_obj_id=obj.id)],
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_lander_for_each_player_death_trigger(obj):
    """Death: each player gets a Lander token (used by 'Each player' effects)."""
    def filt(event, state):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    def handler(event, state):
        events = []
        for pid in state.players.keys():
            events.append(make_lander_token_event(pid, source_obj_id=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration='while_on_battlefield',
    )


# =============================================================================
# === VOID HELPERS ===
# =============================================================================
# EOE Void mechanic. Engine logic in src/engine/void.py tracks
# state.turn_data['void_<player>'] each turn. These card-side helpers
# wrap that check around common trigger patterns.
from src.engine.void import is_void_active  # noqa: E402  (re-export)


def make_void_end_step_trigger(obj, effect_fn):
    """Beginning of YOUR end step: if void, run effect_fn. effect_fn(event, state) -> list[Event]."""
    def filt(event, state):
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'end':
            return False
        if state.active_player != obj.controller:
            return False
        return is_void_active(obj.controller, state)

    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=filt, handler=handler,
        duration='while_on_battlefield',
    )


def make_void_attack_trigger(obj, effect_fn):
    """When obj attacks: if void, run effect_fn."""
    def filt(event, state):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('attacker_id') != obj.id and event.payload.get('attacker') != obj.id:
            return False
        return is_void_active(obj.controller, state)

    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=filt, handler=handler,
        duration='while_on_battlefield',
    )


# =============================================================================
# === STATION HELPERS ===
# =============================================================================
# EOE Station mechanic. A Spacecraft / Planet has thresholds keyed by charge
# counter count; when count >= threshold, the card gains stats and abilities.
# Implementation: register QUERY_POWER, QUERY_TOUGHNESS, QUERY_TYPES,
# and QUERY_ABILITIES interceptors that check the current charge count and
# return the appropriate tier.
from src.engine.station import get_station_charge  # noqa: E402  (re-export)


def make_station_creature_setup(obj, thresholds):
    """Wire a Spacecraft/Planet to become a creature when charge crosses a
    threshold.

    `thresholds` is a list of (min_charge, {power, toughness, keywords})
    in ascending min_charge order. The highest-applicable tier wins.

    Example:
        thresholds = [
            (3, {'power': 4, 'toughness': 3, 'keywords': ['flying']}),
            (5, {'power': 5, 'toughness': 4, 'keywords': ['flying', 'vigilance']}),
        ]
    """
    def best_tier(state):
        charge = get_station_charge(obj)
        match = None
        for min_c, props in thresholds:
            if charge >= min_c:
                match = props
        return match

    def power_filter(event, state):
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == obj.id)

    def power_handler(event, state):
        tier = best_tier(state)
        if tier is None or 'power' not in tier:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = tier['power']
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def tough_filter(event, state):
        return (event.type == EventType.QUERY_TOUGHNESS
                and event.payload.get('object_id') == obj.id)

    def tough_handler(event, state):
        tier = best_tier(state)
        if tier is None or 'toughness' not in tier:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = tier['toughness']
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def types_filter(event, state):
        return (event.type == EventType.QUERY_TYPES
                and event.payload.get('object_id') == obj.id)

    def types_handler(event, state):
        tier = best_tier(state)
        if tier is None:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        types = set(new_event.payload.get('value', set()))
        types.add(CardType.CREATURE)
        new_event.payload['value'] = types
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def kw_filter(event, state):
        return (event.type == EventType.QUERY_ABILITIES
                and event.payload.get('object_id') == obj.id)

    def kw_handler(event, state):
        tier = best_tier(state)
        if tier is None or 'keywords' not in tier:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        kws = set(new_event.payload.get('value', set()))
        for kw in tier['keywords']:
            kws.add(kw)
        new_event.payload['value'] = kws
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=power_filter,
                    handler=power_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=tough_filter,
                    handler=tough_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=types_filter,
                    handler=types_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=kw_filter,
                    handler=kw_handler, duration='while_on_battlefield'),
    ]


# =============================================================================
# === TURN STATE HELPERS ===
# =============================================================================
# Engine-side trackers live in src/engine/turn_state.py and are wired by
# Game._setup_system_interceptors. These card-side re-exports give card
# scripts a single import surface for "did X happen this turn" checks and
# for the coin flip primitive.
from src.engine.turn_state import (  # noqa: E402  (re-exports)
    life_gained_this_turn,
    life_lost_this_turn,
    spells_cast_this_turn,
    nth_spell_this_turn,
    attacked_alone_this_turn,
    creatures_died_this_turn,
    cards_drawn_this_turn,
    combat_damage_dealt_to_this_turn,
    flip_coin,
    emit_coin_flip,
)


def make_coin_flip_event(state, player_id=None, source=None):
    """Build a COIN_FLIP marker event with a freshly-flipped result.

    Convenience wrapper around :func:`emit_coin_flip` for card scripts.
    """
    return emit_coin_flip(state, player_id=player_id, source=source)


def make_life_gain_threshold_trigger(obj, threshold, effect_fn,
                                     who="controller"):
    """Trigger when ``obj.controller`` (or "any" player) crosses a life-gained
    threshold this turn.

    Listens to LIFE_CHANGE; on the event that pushes the running total at or
    above ``threshold``, fires ``effect_fn(event, state) -> list[Event]``.
    Fires once per turn (uses turn_data flag).
    """
    flag_key = f"_life_gain_threshold_{obj.id}"

    def filt(event, state):
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get("amount", 0)
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return False
        if amount <= 0:
            return False
        target_player = event.payload.get("player")
        if not target_player:
            return False
        if who == "controller" and target_player != obj.controller:
            return False
        td = getattr(state, "turn_data", None) or {}
        if td.get(flag_key):
            return False
        return life_gained_this_turn(target_player, state) >= threshold

    def handler(event, state):
        td = getattr(state, "turn_data", None)
        if td is not None:
            td[flag_key] = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )


def make_nth_spell_cast_trigger(obj, n, effect_fn):
    """Trigger when controller casts their Nth spell this turn (e.g. Celebration).

    ``effect_fn(event, state) -> list[Event]``. Fires whenever a CAST/SPELL_CAST
    event lifts ``spells_cast_<controller>`` to exactly ``n``. The trigger
    re-fires each turn at the Nth spell.
    """
    def filt(event, state):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = (
            event.payload.get("caster")
            or event.payload.get("controller")
            or event.payload.get("player")
            or event.controller
        )
        if caster != obj.controller:
            return False
        # Engine tracker increments BEFORE this REACT-priority observer runs
        # because the system tracker is also REACT priority but registered
        # earlier. Defensive: also accept off-by-one.
        count = spells_cast_this_turn(caster, state)
        return count == int(n)

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )


def make_morbid_etb_trigger(obj, effect_fn):
    """Morbid ETB: fire effect_fn only if a creature died this turn.

    ``effect_fn(event, state) -> list[Event]``.
    """
    def filt(event, state):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("object_id") != obj.id:
            return False
        if event.payload.get("to_zone_type") != ZoneType.BATTLEFIELD:
            return False
        return creatures_died_this_turn(state) >= 1

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )


def make_attacks_alone_trigger(obj, effect_fn):
    """Trigger when ``obj`` attacks alone (and that's its controller's only
    attacker this turn).

    ``effect_fn(event, state) -> list[Event]``. Reads
    ``attacked_alone_<controller>`` after COMBAT_DECLARED so the answer is
    authoritative for the just-declared combat step.
    """
    def filt(event, state):
        if event.type != EventType.COMBAT_DECLARED:
            return False
        attacking_player = event.payload.get("attacking_player")
        if attacking_player != obj.controller:
            return False
        attackers = event.payload.get("attackers") or []
        if list(attackers) != [obj.id]:
            return False
        return True

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )
