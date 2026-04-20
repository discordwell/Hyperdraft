"""
Targeting/choice/effect-execution handlers.

Resolves ``TARGET_REQUIRED`` into a ``PendingChoice`` and dispatches the
effect(s) (damage, destroy, pump, etc.) once the player has selected targets.
"""

from ...types import (
    Event, EventType, GameState, ZoneType, CardType, PendingChoice,
)


def _handle_target_required(event: Event, state: GameState):
    """
    Handle TARGET_REQUIRED event.

    Creates a PendingChoice for target selection and pauses game execution.
    When the player submits their choice, _execute_targeted_effect is called.

    Payload:
        source: str           - Object ID causing this targeting requirement
        controller: str       - Player who chooses targets (defaults to source controller)
        effect: str           - Effect type: 'damage', 'destroy', 'exile', 'bounce', etc.
        effect_params: dict   - Parameters for the effect (e.g., {'amount': 3} for damage)
        effects: list[dict]   - Multiple effects to apply (overrides effect/effect_params)
                                Each dict has: {'effect': str, 'params': dict}
        target_filter: str    - Filter type: 'any', 'creature', 'opponent_creature',
                                'your_creature', 'opponent', 'player', 'nonland_permanent'
        min_targets: int      - Minimum targets (default 1)
        max_targets: int      - Maximum targets (default 1)
        optional: bool        - If True, may choose 0 targets
        prompt: str           - UI text (auto-generated if not provided)
        divide_amount: int    - If set, creates a two-step choice: select targets, then allocate
                                the amount among them (e.g., "deal 5 damage divided as you choose")
    """
    from ...targeting import TargetingSystem

    source_id = event.payload.get('source')
    effect = event.payload.get('effect', 'damage')
    effect_params = event.payload.get('effect_params', {})
    effects = event.payload.get('effects')  # Multi-effect support
    target_filter_type = event.payload.get('target_filter', 'any')
    min_targets = event.payload.get('min_targets', 1)
    max_targets = event.payload.get('max_targets', 1)
    optional = event.payload.get('optional', False)
    prompt = event.payload.get('prompt')
    divide_amount = event.payload.get('divide_amount')  # For damage division

    # Get source object and controller
    source_obj = state.objects.get(source_id)
    if not source_obj:
        return

    controller_id = event.payload.get('controller', source_obj.controller)

    # Build target filter based on filter type
    target_requirement = _build_target_requirement(
        target_filter_type, source_obj, min_targets, max_targets, optional
    )

    # Check for pre-computed legal targets override (for complex targeting like
    # "destroy target creature that player controls")
    legal_targets_override = event.payload.get('legal_targets_override')

    if legal_targets_override is not None:
        # Use the override directly
        legal_targets = list(legal_targets_override)
    else:
        # Get legal targets using the targeting system
        targeting_system = TargetingSystem(state)
        legal_targets = targeting_system.get_legal_targets(
            target_requirement, source_obj, controller_id
        )

        # For 'any' and 'player'/'opponent' filters, add players to targets
        if target_filter_type in ('any', 'player'):
            for player_id in state.players:
                if player_id not in legal_targets:
                    legal_targets.append(player_id)
        elif target_filter_type == 'opponent':
            for player_id in state.players:
                if player_id != controller_id and player_id not in legal_targets:
                    legal_targets.append(player_id)

    # If no legal targets and not optional, ability fizzles
    if not legal_targets and not optional:
        return

    # If no legal targets but optional, skip silently
    if not legal_targets and optional:
        return

    # Adjust min_targets if optional
    actual_min = 0 if optional else min_targets

    # Generate prompt if not provided
    if not prompt:
        prompt = _generate_target_prompt(effect, effect_params, target_filter_type)

    # Build callback data
    callback_data = {
        'handler': _execute_targeted_effect,
        'effect': effect,
        'effect_params': effect_params,
        'source_id': source_id,
        'controller_id': controller_id,
    }

    # Multi-effect support: if effects list is provided, use it instead
    if effects:
        callback_data['effects'] = effects

    # Damage division support: pass divide_amount for two-step allocation
    if divide_amount:
        callback_data['divide_amount'] = divide_amount

    # Create PendingChoice
    choice = PendingChoice(
        choice_type="target_with_callback",
        player=controller_id,
        prompt=prompt,
        options=legal_targets,
        source_id=source_id,
        min_choices=actual_min,
        max_choices=min(max_targets, len(legal_targets)),
        callback_data=callback_data
    )
    state.pending_choice = choice


def _build_target_requirement(
    filter_type: str,
    source_obj,
    min_targets: int,
    max_targets: int,
    optional: bool
):
    """Build a TargetRequirement based on filter type string."""
    from ...targeting import (
        TargetRequirement,
        creature_filter, any_target_filter, permanent_filter, player_filter,
    )

    # Map filter types to TargetFilter constructors
    if filter_type == 'any':
        tf = any_target_filter()
    elif filter_type == 'creature':
        tf = creature_filter()
    elif filter_type == 'opponent_creature':
        tf = creature_filter(controller='opponent')
    elif filter_type == 'your_creature':
        tf = creature_filter(controller='you')
    elif filter_type == 'other_creature_you_control':
        tf = creature_filter(controller='you', exclude_self=True)
    elif filter_type == 'opponent':
        tf = player_filter(controller='opponent')
    elif filter_type == 'player':
        tf = player_filter()
    elif filter_type == 'nonland_permanent':
        tf = permanent_filter()
        # Exclude lands
        tf.types = {CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER}
    elif filter_type == 'permanent':
        tf = permanent_filter()
    elif filter_type == 'creature_in_your_graveyard':
        tf = creature_filter(controller='you')
        tf.zones = {ZoneType.GRAVEYARD}
    elif filter_type == 'creature_in_graveyard':
        tf = creature_filter()
        tf.zones = {ZoneType.GRAVEYARD}
    else:
        # Default to any target
        tf = any_target_filter()

    count_type = 'up_to' if optional else 'exactly'

    return TargetRequirement(
        filter=tf,
        count=max_targets,
        count_type=count_type,
        optional=optional
    )


def _generate_target_prompt(effect: str, effect_params: dict, filter_type: str) -> str:
    """Generate a user-friendly prompt for target selection."""
    # Build target description
    target_desc = {
        'any': 'any target',
        'creature': 'target creature',
        'opponent_creature': "target creature you don't control",
        'your_creature': 'target creature you control',
        'other_creature_you_control': 'another target creature you control',
        'opponent': 'target opponent',
        'player': 'target player',
        'nonland_permanent': 'target nonland permanent',
        'permanent': 'target permanent',
        'creature_in_your_graveyard': 'target creature card in your graveyard',
        'creature_in_graveyard': 'target creature card in a graveyard',
    }.get(filter_type, 'a target')

    # Build effect description
    if effect == 'damage':
        amount = effect_params.get('amount', 0)
        return f"Deal {amount} damage to {target_desc}"
    elif effect == 'destroy':
        return f"Destroy {target_desc}"
    elif effect == 'exile':
        return f"Exile {target_desc}"
    elif effect == 'bounce':
        return f"Return {target_desc} to its owner's hand"
    elif effect == 'tap':
        return f"Tap {target_desc}"
    elif effect == 'untap':
        return f"Untap {target_desc}"
    elif effect == 'pump':
        power = effect_params.get('power_mod', 0)
        toughness = effect_params.get('toughness_mod', 0)
        sign_p = '+' if power >= 0 else ''
        sign_t = '+' if toughness >= 0 else ''
        return f"{target_desc} gets {sign_p}{power}/{sign_t}{toughness} until end of turn"
    elif effect == 'counter_add':
        counter_type = effect_params.get('counter_type', '+1/+1')
        amount = effect_params.get('amount', 1)
        return f"Put {amount} {counter_type} counter(s) on {target_desc}"
    elif effect == 'grant_keyword':
        keyword = effect_params.get('keyword', 'an ability')
        return f"{target_desc} gains {keyword} until end of turn"
    elif effect == 'life_change':
        amount = effect_params.get('amount', 0)
        if amount >= 0:
            return f"{target_desc} gains {amount} life"
        else:
            return f"{target_desc} loses {abs(amount)} life"
    elif effect == 'graveyard_to_hand':
        return f"Return {target_desc} to its owner's hand"
    else:
        return f"Choose {target_desc}"


def _execute_targeted_effect(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
    """
    Execute the targeted effect after player selects targets.

    Called as the callback handler when a target_with_callback choice resolves.

    If divide_amount is present in callback_data, this doesn't execute effects directly.
    Instead, it returns a special marker event that triggers the allocation phase.
    """
    if not selected:
        return []  # No targets selected (optional effect)

    source_id = choice.callback_data.get('source_id')
    divide_amount = choice.callback_data.get('divide_amount')

    # Check for damage division - need to create allocation choice instead of executing
    if divide_amount:
        return _create_divide_allocation_choice(choice, selected, state)

    # Check for multi-effect support
    effects = choice.callback_data.get('effects')
    if effects:
        return _execute_multi_effects(effects, selected, source_id, state)

    # Standard single effect execution
    effect = choice.callback_data.get('effect', 'damage')
    effect_params = choice.callback_data.get('effect_params', {})

    events = []

    for target_id in selected:
        if effect == 'damage':
            amount = effect_params.get('amount', 0)
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': amount, 'source': source_id, 'is_combat': False},
                source=source_id
            ))

        elif effect == 'destroy':
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'exile':
            events.append(Event(
                type=EventType.EXILE,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'bounce':
            # Return to hand
            obj = state.objects.get(target_id)
            if obj:
                owner_hand = f"hand_{obj.owner}"
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': target_id,
                        'from_zone': 'battlefield',
                        'to_zone': owner_hand,
                        'from_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone_type': ZoneType.HAND
                    },
                    source=source_id
                ))

        elif effect == 'tap':
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'untap':
            events.append(Event(
                type=EventType.UNTAP,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'pump':
            power_mod = effect_params.get('power_mod', 0)
            toughness_mod = effect_params.get('toughness_mod', 0)
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': target_id,
                    'power_mod': power_mod,
                    'toughness_mod': toughness_mod,
                    'duration': 'end_of_turn'
                },
                source=source_id
            ))

        elif effect == 'counter_add':
            counter_type = effect_params.get('counter_type', '+1/+1')
            amount = effect_params.get('amount', 1)
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target_id,
                    'counter_type': counter_type,
                    'amount': amount
                },
                source=source_id
            ))

        elif effect == 'counter_remove':
            counter_type = effect_params.get('counter_type', '+1/+1')
            amount = effect_params.get('amount', 1)
            events.append(Event(
                type=EventType.COUNTER_REMOVED,
                payload={
                    'object_id': target_id,
                    'counter_type': counter_type,
                    'amount': amount
                },
                source=source_id
            ))

        elif effect == 'grant_keyword':
            keyword = effect_params.get('keyword', '')
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': target_id,
                    'keyword': keyword,
                    'duration': effect_params.get('duration', 'end_of_turn')
                },
                source=source_id
            ))

        elif effect == 'life_change':
            # For effects targeting players
            amount = effect_params.get('amount', 0)
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_id, 'amount': amount},
                source=source_id
            ))

        elif effect == 'graveyard_to_hand':
            # Return target card from graveyard to owner's hand
            target_obj = state.objects.get(target_id)
            if target_obj and target_obj.zone == ZoneType.GRAVEYARD:
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': target_id,
                        'from_zone': f'graveyard_{target_obj.owner}',
                        'to_zone': f'hand_{target_obj.owner}',
                        'to_zone_type': ZoneType.HAND
                    },
                    source=source_id
                ))

    return events


def _create_divide_allocation_choice(
    original_choice: PendingChoice,
    selected_targets: list,
    state: GameState
) -> list[Event]:
    """
    Create a divide_allocation PendingChoice after targets are selected.

    This is the second step in damage division: allocate the amount among targets.
    """
    divide_amount = original_choice.callback_data.get('divide_amount')
    source_id = original_choice.callback_data.get('source_id')
    controller_id = original_choice.callback_data.get('controller_id')
    effect = original_choice.callback_data.get('effect', 'damage')
    effect_params = original_choice.callback_data.get('effect_params', {})

    # Build options with target info for the UI
    options = []
    for target_id in selected_targets:
        obj = state.objects.get(target_id)
        if obj:
            options.append({
                'id': target_id,
                'name': obj.name,
                'type': 'creature' if hasattr(obj, 'characteristics') else 'permanent'
            })
        elif target_id in state.players:
            player = state.players[target_id]
            options.append({
                'id': target_id,
                'name': player.name,
                'type': 'player',
                'life': player.life
            })
        else:
            options.append({'id': target_id, 'name': target_id, 'type': 'unknown'})

    choice = PendingChoice(
        choice_type="divide_allocation",
        player=controller_id,
        prompt=f"Allocate {divide_amount} {effect} among {len(selected_targets)} target(s)",
        options=options,
        source_id=source_id,
        min_choices=1,  # Must allocate to at least 1 target
        max_choices=len(selected_targets),
        callback_data={
            'handler': _execute_divided_effect,
            'total_amount': divide_amount,
            'effect': effect,
            'effect_params': effect_params,
            'source_id': source_id,
            'selected_targets': selected_targets,
            'counter_type': effect_params.get('counter_type', '+1/+1'),
        }
    )
    state.pending_choice = choice

    return []  # Don't execute effects yet - wait for allocation


def _execute_divided_effect(
    choice: PendingChoice,
    allocations: dict,
    state: GameState
) -> list[Event]:
    """
    Execute the divided effect based on player's allocation.

    Args:
        allocations: Dict mapping target_id -> amount allocated
    """
    source_id = choice.callback_data.get('source_id')
    effect = choice.callback_data.get('effect', 'damage')
    total_amount = choice.callback_data.get('total_amount', 0)

    # Validate total allocation equals required amount
    total_allocated = sum(allocations.values())
    if total_allocated != total_amount:
        # Invalid allocation - this shouldn't happen if UI validates
        return []

    events = []

    for target_id, amount in allocations.items():
        if amount <= 0:
            continue

        if effect == 'damage':
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    'target': target_id,
                    'amount': amount,
                    'source': source_id,
                    'is_combat': False
                },
                source=source_id
            ))
        elif effect == 'counter_add':
            counter_type = choice.callback_data.get('counter_type', '+1/+1')
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target_id,
                    'counter_type': counter_type,
                    'amount': amount
                },
                source=source_id
            ))
        elif effect == 'life_change':
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_id, 'amount': amount},
                source=source_id
            ))

    return events


def _execute_multi_effects(
    effects: list[dict],
    selected_targets: list,
    source_id: str,
    state: GameState
) -> list[Event]:
    """
    Execute multiple effects on selected targets.

    Used for cards like "Tap target creature. It doesn't untap during next untap step."

    Args:
        effects: List of effect specs [{'effect': 'tap'}, {'effect': 'stun'}]
    """
    events = []

    for target_id in selected_targets:
        for effect_spec in effects:
            effect = effect_spec.get('effect')
            params = effect_spec.get('params', {})

            effect_events = _create_effect_event(effect, params, target_id, source_id, state)
            events.extend(effect_events)

    return events


def _create_effect_event(
    effect: str,
    params: dict,
    target_id: str,
    source_id: str,
    state: GameState
) -> list[Event]:
    """Create event(s) for a single effect application."""
    events = []

    if effect == 'damage':
        amount = params.get('amount', 0)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': amount, 'source': source_id, 'is_combat': False},
            source=source_id
        ))

    elif effect == 'destroy':
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'exile':
        events.append(Event(
            type=EventType.EXILE,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'bounce':
        obj = state.objects.get(target_id)
        if obj:
            owner_hand = f"hand_{obj.owner}"
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone': 'battlefield',
                    'to_zone': owner_hand,
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.HAND
                },
                source=source_id
            ))

    elif effect == 'tap':
        events.append(Event(
            type=EventType.TAP,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'untap':
        events.append(Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'stun':
        # "Doesn't untap during next untap step" - add stun counter
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1},
            source=source_id
        ))

    elif effect == 'freeze':
        # Tap + stun combo (tap and doesn't untap)
        events.append(Event(
            type=EventType.TAP,
            payload={'object_id': target_id},
            source=source_id
        ))
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1},
            source=source_id
        ))

    elif effect == 'pump':
        power_mod = params.get('power_mod', 0)
        toughness_mod = params.get('toughness_mod', 0)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target_id,
                'power_mod': power_mod,
                'toughness_mod': toughness_mod,
                'duration': 'end_of_turn'
            },
            source=source_id
        ))

    elif effect == 'counter_add':
        counter_type = params.get('counter_type', '+1/+1')
        amount = params.get('amount', 1)
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': target_id,
                'counter_type': counter_type,
                'amount': amount
            },
            source=source_id
        ))

    elif effect == 'grant_keyword':
        keyword = params.get('keyword', '')
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': keyword,
                'duration': params.get('duration', 'end_of_turn')
            },
            source=source_id
        ))

    elif effect == 'life_change':
        amount = params.get('amount', 0)
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target_id, 'amount': amount},
            source=source_id
        ))

    return events
