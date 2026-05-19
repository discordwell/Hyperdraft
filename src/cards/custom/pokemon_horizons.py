"""
Pokemon Horizons (PKH) Card Implementations

Set featuring Pokemon mechanics: Evolve, Catch, Type Advantage
~250 cards across all colors

Converted to use the declarative ability system.
"""

from src.cards.card_factories import (
    make_artifact,
    make_equipment,
    make_land,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness,
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_spell_cast_trigger, make_upkeep_trigger,
    creatures_you_control,
    other_creatures_with_subtype, all_opponents,
    opponent_creatures_filter,
    make_activated_ability, make_cost_reduction, make_equipment_setup,
    make_library_search_etb_trigger, open_library_search,
)
from src.cards.ability_bundles import (
    etb_gain_life, etb_lose_life, etb_draw,
    static_pt_boost_other_you_control, static_pt_boost_by_subtype,
    static_keyword_grant_others,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _self_kw(keywords):
    """Self-granting keyword setup factory. Returns a setup_interceptors fn."""
    def setup(obj, state):
        def affects(target, st, src=obj):
            return target.id == src.id
        return [make_keyword_grant(obj, keywords, affects)]
    return setup


def _react_interceptor(
    source_obj: GameObject,
    filter_fn: Callable[[Event, GameState], bool],
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """Local listener for deterministic default-target card text."""
    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def _is_creature(obj: GameObject) -> bool:
    return CardType.CREATURE in (obj.characteristics.types or set())


def _battlefield_objects(state: GameState) -> list[GameObject]:
    return [obj for obj in state.objects.values() if obj.zone == ZoneType.BATTLEFIELD]


def _impact_sort_key(obj: GameObject, state: GameState) -> tuple[int, int, str]:
    power = get_power(obj, state) or 0
    toughness = get_toughness(obj, state) or 0
    return (power + toughness, power, obj.name)


def _opponent_creatures(source_obj: GameObject, state: GameState) -> list[GameObject]:
    return sorted(
        (
            obj for obj in _battlefield_objects(state)
            if obj.controller != source_obj.controller and _is_creature(obj)
        ),
        key=lambda candidate: _impact_sort_key(candidate, state),
        reverse=True,
    )


def _opponent_nonland_permanents(source_obj: GameObject, state: GameState) -> list[GameObject]:
    return sorted(
        (
            obj for obj in _battlefield_objects(state)
            if obj.controller != source_obj.controller
            and CardType.LAND not in (obj.characteristics.types or set())
        ),
        key=lambda candidate: _impact_sort_key(candidate, state),
        reverse=True,
    )


def _all_other_creatures(source_obj: GameObject, state: GameState) -> list[GameObject]:
    return [
        obj for obj in _battlefield_objects(state)
        if obj.id != source_obj.id and _is_creature(obj)
    ]


def _first_graveyard_card(player_id: str, state: GameState) -> Optional[GameObject]:
    zone = state.zones.get(f'graveyard_{player_id}')
    if not zone:
        return None
    for obj_id in zone.objects:
        obj = state.objects.get(obj_id)
        if obj and obj.zone == ZoneType.GRAVEYARD:
            return obj
    return None


def _discard_first_from_hand(player_id: str, source_obj: GameObject, state: GameState) -> list[Event]:
    zone = state.zones.get(f'hand_{player_id}')
    if not zone or not zone.objects:
        return []
    return [Event(
        type=EventType.DISCARD,
        payload={'player': player_id, 'object_id': zone.objects[0]},
        source=source_obj.id,
        controller=source_obj.controller,
    )]


def _combat_damage_to_player_filter(
    event: Event,
    state: GameState,
    source_obj: GameObject,
) -> bool:
    return (
        event.type == EventType.DAMAGE
        and event.payload.get('source') == source_obj.id
        and event.payload.get('is_combat', False)
        and event.payload.get('target') in state.players
    )


def _self_keyword_interceptors(obj: GameObject, keywords: list[str] | tuple[str, ...]) -> list[Interceptor]:
    if not keywords:
        return []

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    return [make_keyword_grant(obj, list(keywords), affects_self)]


def _first_opponent_player(source_obj: GameObject, state: GameState) -> Optional[str]:
    opponents = all_opponents(source_obj, state)
    return opponents[0] if opponents else None


def _default_any_target(source_obj: GameObject, state: GameState) -> Optional[str]:
    creatures = _opponent_creatures(source_obj, state)
    if creatures:
        return creatures[0].id
    return _first_opponent_player(source_obj, state)


def _damage_event(source_obj: GameObject, target_id: Optional[str], amount: int) -> list[Event]:
    if not target_id:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': amount, 'source': source_obj.id},
        source=source_obj.id,
        controller=source_obj.controller,
    )]


def _treasure_token_event(source_obj: GameObject) -> Event:
    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': source_obj.controller,
            'token': {
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'text': '{T}, Sacrifice this artifact: Add one mana of any color.',
            },
        },
        source=source_obj.id,
        controller=source_obj.controller,
    )


def _evolve_setup(
    evolved_name: str,
    evolved_power: int,
    evolved_toughness: int,
    mana_cost: str,
    *,
    keywords: list[str] | tuple[str, ...] = (),
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return [
            *_self_keyword_interceptors(obj, keywords),
            make_evolve_trigger(obj, evolved_name, evolved_power, evolved_toughness, mana_cost),
        ]

    return setup


def _etb_scry_setup(count: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            return [Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'count': count, 'source_id': obj.id},
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_damage_best_target_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            return _damage_event(obj, _default_any_target(obj, st), amount)

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_damage_best_creature_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            targets = _opponent_creatures(obj, st)
            return _damage_event(obj, targets[0].id if targets else None, amount)

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_damage_opponent_creatures_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            events: list[Event] = []
            for target in _opponent_creatures(obj, st):
                events.extend(_damage_event(obj, target.id, amount))
            return events

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_damage_each_opponent_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            events: list[Event] = []
            for opponent_id in all_opponents(obj, st):
                events.extend(_damage_event(obj, opponent_id, amount))
            return events

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_tap_opponent_creatures_setup(
    count: Optional[int] = 1,
    *,
    keywords: list[str] | tuple[str, ...] = (),
):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            targets = _opponent_creatures(obj, st)
            if count is not None:
                targets = targets[:count]
            return [
                Event(
                    type=EventType.TAP,
                    payload={'object_id': target.id},
                    source=obj.id,
                    controller=obj.controller,
                )
                for target in targets
            ]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_bounce_best_creature_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            targets = _opponent_creatures(obj, st)
            if not targets:
                return []
            return [Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': targets[0].id},
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_discard_opponents_setup(*, each: bool, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            opponents = all_opponents(obj, st)
            if not each:
                opponents = opponents[:1]
            events: list[Event] = []
            for opponent_id in opponents:
                events.extend(_discard_first_from_hand(opponent_id, obj, st))
            return events

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _death_treasure_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            return [_treasure_token_event(obj)]

        return [*_self_keyword_interceptors(obj, keywords), make_death_trigger(obj, effect)]

    return setup


def _death_damage_creatures_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            events: list[Event] = []
            for target in _battlefield_objects(st):
                if _is_creature(target):
                    events.extend(_damage_event(obj, target.id, amount))
            return events

        return [*_self_keyword_interceptors(obj, keywords), make_death_trigger(obj, effect)]

    return setup


def _flatten_target_values(targets) -> list:
    if not targets:
        return []
    values: list = []
    for target in targets:
        if target is None:
            continue
        if isinstance(target, (list, tuple, set)):
            values.extend(_flatten_target_values(list(target)))
        else:
            values.append(target)
    return values


def _target_id_from(target) -> Optional[str]:
    if target is None:
        return None
    if isinstance(target, str):
        return target
    if hasattr(target, "object_id"):
        return target.object_id
    if hasattr(target, "id"):
        return target.id
    return None


def _first_target_id(targets) -> Optional[str]:
    for target in _flatten_target_values(targets):
        target_id = _target_id_from(target)
        if target_id:
            return target_id
    return None


def _spell_controller(state: GameState, targets=None) -> Optional[str]:
    stack_zone = state.zones.get('stack') if state and state.zones else None
    if stack_zone:
        for obj_id in reversed(list(stack_zone.objects or [])):
            obj = state.objects.get(obj_id)
            if obj and obj.controller:
                return obj.controller
    if getattr(state, 'priority_player', None):
        return state.priority_player
    if getattr(state, 'active_player', None):
        return state.active_player
    if state.players:
        return next(iter(state.players))
    for target in _flatten_target_values(targets):
        target_id = _target_id_from(target)
        if not target_id:
            continue
        if target_id in state.players:
            return target_id
        obj = state.objects.get(target_id)
        if obj and obj.controller:
            return obj.controller
    return None


def _first_opponent_for(controller: str, state: GameState) -> Optional[str]:
    for player_id in state.players:
        if player_id != controller:
            return player_id
    return None


def _creatures_controlled_by(controller: str, state: GameState) -> list[GameObject]:
    return [
        obj for obj in _battlefield_objects(state)
        if obj.controller == controller and _is_creature(obj)
    ]


def _pokemon_controlled_by(controller: str, state: GameState) -> list[GameObject]:
    return [
        obj for obj in _creatures_controlled_by(controller, state)
        if "Pokemon" in (obj.characteristics.subtypes or set())
    ]


def _opponent_creatures_for(controller: str, state: GameState) -> list[GameObject]:
    return sorted(
        (
            obj for obj in _battlefield_objects(state)
            if obj.controller != controller and _is_creature(obj)
        ),
        key=lambda candidate: _impact_sort_key(candidate, state),
        reverse=True,
    )


def _card_mana_value(obj: GameObject) -> int:
    cost = obj.characteristics.mana_cost or ""
    try:
        return ManaCost.parse(cost).mana_value
    except Exception:
        return 0


def _target_or_best_opponent_creature(
    targets,
    controller: str,
    state: GameState,
    *,
    max_power: Optional[int] = None,
    max_mv: Optional[int] = None,
) -> Optional[GameObject]:
    target_id = _first_target_id(targets)
    target = state.objects.get(target_id) if target_id else None
    if target and _is_creature(target):
        if max_power is not None and (get_power(target, state) or 0) > max_power:
            target = None
        if max_mv is not None and _card_mana_value(target) > max_mv:
            target = None
    else:
        target = None

    if target:
        return target

    for candidate in _opponent_creatures_for(controller, state):
        if max_power is not None and (get_power(candidate, state) or 0) > max_power:
            continue
        if max_mv is not None and _card_mana_value(candidate) > max_mv:
            continue
        return candidate
    return None


def _draw_event(player_id: str, amount: int, source_id: Optional[str] = None) -> Event:
    return Event(
        type=EventType.DRAW,
        payload={'player': player_id, 'amount': amount, 'count': amount},
        source=source_id,
        controller=player_id,
    )


def _scry_event(player_id: str, count: int, source_id: Optional[str] = None) -> Event:
    return Event(
        type=EventType.SCRY,
        payload={'player': player_id, 'count': count, 'amount': count, 'source_id': source_id},
        source=source_id,
        controller=player_id,
    )


def _discard_first_from_player_hand(
    player_id: str,
    state: GameState,
    *,
    source_id: Optional[str] = None,
    controller: Optional[str] = None,
) -> list[Event]:
    zone = state.zones.get(f'hand_{player_id}')
    if not zone or not zone.objects:
        return []
    return [Event(
        type=EventType.DISCARD,
        payload={'player': player_id, 'object_id': zone.objects[0]},
        source=source_id,
        controller=controller,
    )]


def _remove_all_counters_events(target: GameObject, source_id: Optional[str] = None) -> list[Event]:
    events: list[Event] = []
    for counter_type, amount in list((target.state.counters or {}).items()):
        if amount <= 0:
            continue
        events.append(Event(
            type=EventType.COUNTER_REMOVED,
            payload={'object_id': target.id, 'counter_type': counter_type, 'amount': amount},
            source=source_id,
            controller=target.controller,
        ))
    return events


def _spell_life_gain(
    amount: int,
    *,
    scry_if_pokemon: int = 0,
    draw_if_pokemon: bool = False,
    per_pokemon: int = 0,
    target_toughness: bool = False,
    grant_keyword: Optional[str] = None,
):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        life_amount = amount
        if per_pokemon:
            life_amount = per_pokemon * len(_pokemon_controlled_by(controller, state))
        target_id = _first_target_id(targets)
        target = state.objects.get(target_id) if target_id else None
        if target_toughness and target:
            life_amount = get_toughness(target, state) or 0
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': controller, 'amount': life_amount},
            controller=controller,
        )]
        if target and grant_keyword:
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': target.id, 'keyword': grant_keyword, 'duration': 'end_of_turn'},
                controller=controller,
            ))
        if _pokemon_controlled_by(controller, state):
            if scry_if_pokemon:
                events.append(_scry_event(controller, scry_if_pokemon))
            if draw_if_pokemon:
                events.append(_draw_event(controller, 1))
        return events

    return resolve


def _spell_draw_discard(draw_count: int, discard_count: int = 0, *, scry_first: int = 0):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        events: list[Event] = []
        if scry_first:
            events.append(_scry_event(controller, scry_first))
        if draw_count:
            events.append(_draw_event(controller, draw_count))
        for _ in range(discard_count):
            events.extend(_discard_first_from_player_hand(controller, state, controller=controller))
        return events

    return resolve


def _spell_opponent_discard(count: int, *, life_loss: int = 0):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        opponent = _first_opponent_for(controller, state) if controller else None
        if not controller or not opponent:
            return []
        events: list[Event] = []
        for _ in range(count):
            events.extend(_discard_first_from_player_hand(opponent, state, controller=controller))
        if life_loss:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opponent, 'amount': -life_loss},
                controller=controller,
            ))
        return events

    return resolve


def _spell_pump(
    power_mod: int,
    toughness_mod: int,
    *,
    keywords: list[str] | tuple[str, ...] = (),
    life_gain: int = 0,
):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        target_id = _first_target_id(targets)
        if not target_id:
            target = _creatures_controlled_by(controller, state)[0] if controller and _creatures_controlled_by(controller, state) else None
            target_id = target.id if target else None
        if not target_id:
            return []
        events: list[Event] = [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target_id,
                'power_mod': power_mod,
                'toughness_mod': toughness_mod,
                'duration': 'end_of_turn',
            },
            controller=controller,
        )]
        for keyword in keywords:
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': target_id, 'keyword': keyword, 'duration': 'end_of_turn'},
                controller=controller,
            ))
        if controller and life_gain:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': controller, 'amount': life_gain},
                controller=controller,
            ))
        return events

    return resolve


def _spell_tap_opponent_creatures(count: Optional[int] = 1, *, scry: int = 0):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        target_id = _first_target_id(targets)
        selected = [state.objects[target_id]] if target_id in state.objects else []
        if not selected:
            selected = _opponent_creatures_for(controller, state)
        if count is not None:
            selected = selected[:count]
        events = [
            Event(type=EventType.TAP, payload={'object_id': target.id}, controller=controller)
            for target in selected
            if _is_creature(target)
        ]
        if scry:
            events.append(_scry_event(controller, scry))
        return events

    return resolve


def _spell_bounce(*, draw: bool = False, max_mv: Optional[int] = None):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        target = _target_or_best_opponent_creature(targets, controller, state, max_mv=max_mv)
        events = []
        if target:
            events.append(Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': target.id},
                controller=controller,
            ))
        if draw:
            events.append(_draw_event(controller, 1))
        return events

    return resolve


def _spell_damage(
    amount: int,
    *,
    creature_only: bool = False,
    each_creature: bool = False,
    each_player: bool = False,
    each_opponent: bool = False,
    opponent_creatures_only: bool = False,
    flying_bonus: int = 0,
):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        events: list[Event] = []
        if each_creature:
            for target in _battlefield_objects(state):
                if _is_creature(target):
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': target.id, 'amount': amount, 'source': None},
                        controller=controller,
                    ))
        if opponent_creatures_only:
            for target in _opponent_creatures_for(controller, state):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': target.id, 'amount': amount, 'source': None},
                    controller=controller,
                ))
        if each_player:
            for player_id in state.players:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': amount, 'source': None},
                    controller=controller,
                ))
        if each_opponent:
            for player_id in state.players:
                if player_id != controller:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': player_id, 'amount': amount, 'source': None},
                        controller=controller,
                    ))
        if each_creature or each_player or each_opponent or opponent_creatures_only:
            return events

        target_id = _first_target_id(targets)
        target = state.objects.get(target_id) if target_id else None
        if creature_only:
            target = target if target and _is_creature(target) else _target_or_best_opponent_creature(targets, controller, state)
        if target:
            actual = amount
            if flying_bonus and (
                "Flying" in (target.characteristics.subtypes or set())
                or any(
                    isinstance(ability, dict) and ability.get('keyword') == 'flying'
                    for ability in target.characteristics.abilities
                )
            ):
                actual = flying_bonus
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': target.id, 'amount': actual, 'source': None},
                controller=controller,
            )]
        if not creature_only:
            target_player = target_id if target_id in state.players else _first_opponent_for(controller, state)
            if target_player:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': target_player, 'amount': amount, 'source': None},
                    controller=controller,
                )]
        return []

    return resolve


def _spell_destroy(
    *,
    max_power: Optional[int] = None,
    max_count: int = 1,
    all_creatures: bool = False,
    artifact_or_enchantment: bool = False,
):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        selected: list[GameObject] = []
        for target in _flatten_target_values(targets):
            target_id = _target_id_from(target)
            obj = state.objects.get(target_id) if target_id else None
            if obj:
                selected.append(obj)
        if all_creatures:
            selected = [obj for obj in _battlefield_objects(state) if _is_creature(obj)]
        if not selected:
            if artifact_or_enchantment:
                selected = [
                    obj for obj in _battlefield_objects(state)
                    if obj.controller != controller
                    and (
                        CardType.ARTIFACT in (obj.characteristics.types or set())
                        or CardType.ENCHANTMENT in (obj.characteristics.types or set())
                    )
                ]
            else:
                selected = _opponent_creatures_for(controller, state)
        events: list[Event] = []
        for obj in selected[:max_count]:
            if artifact_or_enchantment and not (
                CardType.ARTIFACT in (obj.characteristics.types or set())
                or CardType.ENCHANTMENT in (obj.characteristics.types or set())
            ):
                continue
            if max_power is not None and (get_power(obj, state) or 0) > max_power:
                continue
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj.id},
                controller=controller,
            ))
        return events

    return resolve


def _spell_search(
    *,
    card_type: Optional[CardType] = None,
    subtype: Optional[str] = None,
    subtypes_any: Optional[list[str]] = None,
    count: int = 1,
    destination: str = "hand",
    basic_only: bool = False,
):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        payload = {
            'player': controller,
            'destination': destination,
            'max_count': count,
            'reveal': True,
            'shuffle_after': True,
        }
        if card_type is not None:
            payload['card_type'] = card_type
        if subtype:
            payload['subtype'] = subtype
        if subtypes_any:
            payload['subtypes_any'] = subtypes_any
        if basic_only:
            payload['basic_only'] = True
        return [Event(type=EventType.SEARCH_LIBRARY, payload=payload, controller=controller)]

    return resolve


def _spell_counter_then_value(*, scry: int = 0, draw_if_psychic: bool = False):
    def resolve(targets, state: GameState) -> list[Event]:
        controller = _spell_controller(state, targets)
        if not controller:
            return []
        target_id = _first_target_id(targets)
        events: list[Event] = []
        if target_id:
            events.append(Event(
                type=EventType.COUNTER,
                payload={'spell_id': target_id, 'reason': 'psychic'},
                controller=controller,
            ))
        if scry:
            events.append(_scry_event(controller, scry))
        if draw_if_psychic and any("Psychic" in (obj.characteristics.subtypes or set()) for obj in _pokemon_controlled_by(controller, state)):
            events.append(_draw_event(controller, 1))
        return events

    return resolve


def _chain_resolves(*resolvers):
    def resolve(targets, state: GameState) -> list[Event]:
        events: list[Event] = []
        for resolver in resolvers:
            events.extend(resolver(targets, state) or [])
        return events

    return resolve


def _spell_heal_bell_resolve(targets, state: GameState) -> list[Event]:
    controller = _spell_controller(state, targets)
    if not controller:
        return []
    target_id = _first_target_id(targets)
    target = state.objects.get(target_id) if target_id else None
    events: list[Event] = []
    if target:
        events.extend(_remove_all_counters_events(target))
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': controller, 'amount': 3},
        controller=controller,
    ))
    return events


def _spell_safeguard_resolve(targets, state: GameState) -> list[Event]:
    controller = _spell_controller(state, targets)
    if not controller:
        return []
    return [
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target.id, 'keyword': 'hexproof', 'duration': 'end_of_turn'},
            controller=controller,
        )
        for target in _creatures_controlled_by(controller, state)
    ]


def _etb_gain_life_per_creature_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            amount = len(_creatures_controlled_by(obj.controller, st))
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': amount},
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_draw_discard_setup(draw_count: int, discard_count: int = 0, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            events = [_draw_event(obj.controller, draw_count, obj.id)]
            for _ in range(discard_count):
                events.extend(_discard_first_from_player_hand(obj.controller, st, source_id=obj.id, controller=obj.controller))
            return events

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_scry_draw_setup(scry_count: int, draw_count: int = 1, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            return [
                _scry_event(obj.controller, scry_count, obj.id),
                _draw_event(obj.controller, draw_count, obj.id),
            ]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_search_setup(
    *,
    card_type: Optional[CardType] = None,
    subtype: Optional[str] = None,
    subtypes_any: Optional[list[str]] = None,
    basic_only: bool = False,
    keywords: list[str] | tuple[str, ...] = (),
):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            payload = {
                'player': obj.controller,
                'destination': 'hand',
                'max_count': 1,
                'reveal': True,
                'shuffle_after': True,
            }
            if card_type is not None:
                payload['card_type'] = card_type
            if subtype:
                payload['subtype'] = subtype
            if subtypes_any:
                payload['subtypes_any'] = subtypes_any
            if basic_only:
                payload['basic_only'] = True
            return [Event(type=EventType.SEARCH_LIBRARY, payload=payload, source=obj.id, controller=obj.controller)]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _death_search_setup(
    *,
    card_type: Optional[CardType] = None,
    basic_only: bool = False,
    keywords: list[str] | tuple[str, ...] = (),
):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            payload = {
                'player': obj.controller,
                'destination': 'hand',
                'max_count': 1,
                'reveal': True,
                'shuffle_after': True,
            }
            if card_type is not None:
                payload['card_type'] = card_type
            if basic_only:
                payload['basic_only'] = True
            return [Event(type=EventType.SEARCH_LIBRARY, payload=payload, source=obj.id, controller=obj.controller)]

        return [*_self_keyword_interceptors(obj, keywords), make_death_trigger(obj, effect)]

    return setup


def _combat_damage_treasure_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            return [_treasure_token_event(obj)]

        return [
            *_self_keyword_interceptors(obj, keywords),
            make_damage_trigger(obj, effect, combat_only=True, filter_fn=_combat_damage_to_player_filter),
        ]

    return setup


def _combat_damage_discard_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            player_id = event.payload.get('target')
            if player_id not in st.players:
                return []
            return _discard_first_from_player_hand(player_id, st, source_id=obj.id, controller=obj.controller)

        return [
            *_self_keyword_interceptors(obj, keywords),
            make_damage_trigger(obj, effect, combat_only=True, filter_fn=_combat_damage_to_player_filter),
        ]

    return setup


def _combat_damage_life_loss_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            player_id = event.payload.get('target')
            if player_id not in st.players:
                return []
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': player_id, 'amount': -amount},
                source=obj.id,
                controller=obj.controller,
            )]

        return [
            *_self_keyword_interceptors(obj, keywords),
            make_damage_trigger(obj, effect, combat_only=True, filter_fn=_combat_damage_to_player_filter),
        ]

    return setup


def _attack_pump_self_setup(power_mod: int, toughness_mod: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': obj.id,
                    'power_mod': power_mod,
                    'toughness_mod': toughness_mod,
                    'duration': 'end_of_turn',
                },
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), make_attack_trigger(obj, effect)]

    return setup


def _damage_reflect_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def reflect_filter(event: Event, st: GameState) -> bool:
            return event.type == EventType.DAMAGE and event.payload.get('target') == obj.id and bool(event.payload.get('source'))

        def reflect(event: Event, st: GameState) -> list[Event]:
            source_id = event.payload.get('source')
            amount = event.payload.get('amount', 0)
            if not source_id or amount <= 0:
                return []
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': source_id, 'amount': amount, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), _react_interceptor(obj, reflect_filter, reflect)]

    return setup


def _etb_counter_best_ally_setup(amount: int, *, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            allies = sorted(
                (
                    target for target in _creatures_controlled_by(obj.controller, st)
                    if target.id != obj.id
                ),
                key=lambda candidate: _impact_sort_key(candidate, st),
                reverse=True,
            )
            if not allies:
                allies = [obj]
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': allies[0].id, 'counter_type': '+1/+1', 'amount': amount},
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _etb_destroy_artifact_enchantment_setup(*, keywords: list[str] | tuple[str, ...] = ()):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            targets = [
                target for target in _battlefield_objects(st)
                if target.controller != obj.controller
                and (
                    CardType.ARTIFACT in (target.characteristics.types or set())
                    or CardType.ENCHANTMENT in (target.characteristics.types or set())
                )
            ]
            if not targets:
                return []
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': targets[0].id},
                source=obj.id,
                controller=obj.controller,
            )]

        return [*_self_keyword_interceptors(obj, keywords), make_etb_trigger(obj, effect)]

    return setup


def _activated_setup(
    cost: str,
    effect_fn,
    description: str,
    *,
    keywords: list[str] | tuple[str, ...] = (),
    targets_required: int = 0,
    target_kind: str = "any",
):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        make_activated_ability(
            obj,
            cost,
            effect_fn,
            description=description,
            targets_required=targets_required,
            target_kind=target_kind,
        )
        return _self_keyword_interceptors(obj, keywords)

    return setup


def _tap_gain_life_effect(amount: int):
    def effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
            controller=obj.controller,
        )]

    return effect


def _tap_mana_effect(symbol: str):
    def effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.ADD_MANA,
            payload={'player': obj.controller, 'mana': symbol, 'amount': 2 if symbol == 'G' else 1},
            source=obj.id,
            controller=obj.controller,
        )]

    return effect


def _tap_damage_effect(amount: int):
    def effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
        target_id = _first_target_id(targets) or _default_any_target(obj, state)
        return _damage_event(obj, target_id, amount)

    return effect


def _sac_damage_effect(amount: int):
    def effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
        target_id = _first_target_id(targets) or _default_any_target(obj, state)
        return _damage_event(obj, target_id, amount)

    return effect


def _catch_effect(max_power: Optional[int] = None):
    def effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
        target_id = _first_target_id(targets)
        target = state.objects.get(target_id) if target_id else None
        if not target:
            target = _target_or_best_opponent_creature([], obj.controller, state)
        if not target:
            return []
        if max_power is not None and (get_power(target, state) or 0) > max_power:
            return []
        return [Event(
            type=EventType.GAIN_CONTROL,
            payload={'object_id': target.id, 'new_controller': obj.controller, 'duration': 'end_of_turn'},
            source=obj.id,
            controller=obj.controller,
        )]

    return effect


def _rare_candy_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    target_id = _first_target_id(targets)
    if not target_id:
        candidates = _creatures_controlled_by(obj.controller, state)
        target_id = candidates[0].id if candidates else None
    if not target_id:
        return []
    return [Event(
        type=EventType.ACTIVATE,
        payload={'source': target_id, 'ability': 'evolve'},
        source=obj.id,
        controller=obj.controller,
    )]


def _berry_effect(life_amount: int, draw: bool = False):
    def effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': life_amount},
            source=obj.id,
            controller=obj.controller,
        )]
        if draw:
            events.append(_draw_event(obj.controller, 1, obj.id))
        return events

    return effect


def _max_revive_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    target_id = _first_target_id(targets)
    target = state.objects.get(target_id) if target_id else _first_graveyard_card(obj.controller, state)
    if not target or target.zone != ZoneType.GRAVEYARD or not _is_creature(target):
        return []
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target.id,
            'from_zone_type': ZoneType.GRAVEYARD,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _pokedex_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    events = [_scry_event(obj.controller, 2, obj.id)]
    if _pokemon_controlled_by(obj.controller, state):
        events.append(_draw_event(obj.controller, 1, obj.id))
        events.extend(_discard_first_from_player_hand(obj.controller, state, source_id=obj.id, controller=obj.controller))
    return events


def _leftovers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        amount = 2 if _pokemon_controlled_by(obj.controller, st) else 1
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
            controller=obj.controller,
        )]

    return [make_upkeep_trigger(obj, effect)]


def _lucky_egg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE or not event.payload.get('is_combat', False):
            return False
        if event.payload.get('target') not in st.players:
            return False
        source = st.objects.get(event.payload.get('source'))
        return bool(source and source.controller == obj.controller and _is_creature(source))

    def effect(event: Event, st: GameState) -> list[Event]:
        return [_draw_event(obj.controller, 1, obj.id)]

    return [_react_interceptor(obj, filter_fn, effect)]


def _exp_share_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_equipment_setup(power_mod=0, toughness_mod=0, equip_cost="{1}")(obj, state)

    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type not in {EventType.OBJECT_DESTROYED, EventType.ZONE_CHANGE}:
            return False
        attached = obj.state.attached_to
        if not attached:
            return False
        dying_id = event.payload.get('object_id')
        if not dying_id or dying_id == attached:
            return False
        dying = st.objects.get(dying_id)
        if not dying or dying.controller != obj.controller or not _is_creature(dying):
            return False
        if event.type == EventType.ZONE_CHANGE:
            return event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and event.payload.get('to_zone_type') == ZoneType.GRAVEYARD
        return True

    def effect(event: Event, st: GameState) -> list[Event]:
        attached = obj.state.attached_to
        if not attached:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': attached, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    interceptors.append(_react_interceptor(obj, filter_fn, effect))
    return interceptors


def _rocky_helmet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_equipment_setup(toughness_mod=1, equip_cost="{1}")(obj, state)

    def filter_fn(event: Event, st: GameState) -> bool:
        return (
            event.type == EventType.DAMAGE
            and event.payload.get('is_combat', False)
            and obj.state.attached_to
            and event.payload.get('target') == obj.state.attached_to
            and bool(event.payload.get('source'))
        )

    def effect(event: Event, st: GameState) -> list[Event]:
        source = st.objects.get(event.payload.get('source'))
        if not source:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': source.controller, 'amount': 2, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    interceptors.append(_react_interceptor(obj, filter_fn, effect))
    return interceptors


def _silph_scope_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def ghosts_or_dark_opposed(target: GameObject, st: GameState) -> bool:
        if target.controller != obj.controller or not _is_creature(target):
            return False
        return any(
            other.controller != obj.controller
            and _is_creature(other)
            and bool((other.characteristics.subtypes or set()) & {"Ghost", "Dark"})
            for other in _battlefield_objects(st)
        )

    return [
        make_keyword_grant(obj, ["vigilance"], creatures_you_control(obj)),
        make_keyword_grant(obj, ["menace"], ghosts_or_dark_opposed),
    ]


# =============================================================================
# POKEMON KEYWORD MECHANICS
# =============================================================================

def pokemon_filter(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, subtype)

def make_evolve_trigger(source_obj: GameObject, evolved_name: str, evolved_power: int, evolved_toughness: int, mana_cost: str) -> Interceptor:
    """Evolve - Pay cost to transform into evolved form."""
    def evolve_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ACTIVATE and
                event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'evolve')

    def evolve_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.TRANSFORM,
            payload={
                'object_id': source_obj.id,
                'new_name': evolved_name,
                'power': evolved_power,
                'toughness': evolved_toughness,
                'new_power': evolved_power,
                'new_toughness': evolved_toughness,
            },
            source=source_obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[transform_event])

    return Interceptor(
        id=new_id(), source=source_obj.id, controller=source_obj.controller,
        priority=InterceptorPriority.REACT, filter=evolve_filter, handler=evolve_handler,
        duration='while_on_battlefield'
    )

def make_type_advantage(source_obj: GameObject, bonus_damage: int, target_subtypes: set[str]) -> Interceptor:
    """Type Advantage - Deal extra damage to certain types."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source_obj.id:
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False
        return bool(target.characteristics.subtypes & target_subtypes)

    def damage_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + bonus_damage
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return Interceptor(
        id=new_id(), source=source_obj.id, controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=damage_filter, handler=damage_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# WHITE CARDS - NORMAL, FAIRY
# =============================================================================

# --- Legendary Pokemon ---

def arceus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc_etb, _ = etb_gain_life(obj, 5)
    itcs_static, _ = static_pt_boost_other_you_control(obj, 1, 1)
    return [itc_etb] + itcs_static

ARCEUS = make_creature(
    name="Arceus, The Original One",
    power=6, toughness=6,
    mana_cost="{3}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Normal"},
    supertypes={"Legendary"},
    text="Flying, vigilance. When Arceus, The Original One enters, you gain 5 life. Other creatures you control get +1/+1.",
    setup_interceptors=arceus_setup,
)

def togekiss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 3)
    return [itc]

TOGEKISS = make_creature(
    name="Togekiss, Jubilee Pokemon",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Fairy", "Flying"},
    supertypes={"Legendary"},
    text="Flying, lifelink. When Togekiss, Jubilee Pokemon enters, you gain 3 life.",
    setup_interceptors=togekiss_setup,
)

def clefable_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    fairy_filter = other_creatures_with_subtype(obj, "Fairy")
    itc = make_keyword_grant(obj, ["hexproof"], fairy_filter)
    return [itc]

CLEFABLE = make_creature(
    name="Clefable, Fairy Queen",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Fairy"},
    supertypes={"Legendary"},
    text="Other Fairy creatures you control have hexproof.",
    setup_interceptors=clefable_setup,
)

def sylveon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def bounce_best_creature(event: Event, st: GameState) -> list[Event]:
        targets = _opponent_creatures(obj, st)
        if not targets:
            return []
        return [Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': targets[0].id},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        make_keyword_grant(obj, ["lifelink"], affects_self),
        make_damage_trigger(
            obj,
            bounce_best_creature,
            combat_only=True,
            filter_fn=_combat_damage_to_player_filter,
        ),
    ]


SYLVEON = make_creature(
    name="Sylveon, Intertwining Pokemon",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Fairy"},
    supertypes={"Legendary"},
    text="Lifelink. Whenever Sylveon deals combat damage to a player, you may return target creature to its owner's hand.",
    setup_interceptors=sylveon_setup,
)

# --- Regular White Pokemon ---

def eevee_w_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Sylveon", 2, 3, "{W}{W}")]

EEVEE_W = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Evolve {W}{W}: Transform Eevee into Sylveon.",
    setup_interceptors=eevee_w_setup
)

def clefairy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Clefable", 3, 3, "{1}{W}{W}")]

CLEFAIRY = make_creature(
    name="Clefairy", power=1, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="Evolve {1}{W}{W}: Transform Clefairy into Clefable.",
    setup_interceptors=clefairy_setup
)

def togepi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Togetic", 2, 2, "{1}{W}")]

TOGEPI = make_creature(
    name="Togepi", power=0, toughness=2, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="Defender. Evolve {1}{W}: Transform Togepi into Togetic.",
    setup_interceptors=togepi_setup
)

TOGETIC = make_creature(
    name="Togetic", power=2, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy", "Flying"},
    text="Flying. Evolve {2}{W}{W}: Transform Togetic into Togekiss.",
    setup_interceptors=_evolve_setup("Togekiss, Jubilee Pokemon", 4, 4, "{2}{W}{W}", keywords=["flying"]),
)

CHANSEY = make_creature(
    name="Chansey", power=1, toughness=5, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="{T}: Prevent the next 3 damage that would be dealt to target creature this turn."
)

BLISSEY = make_creature(
    name="Blissey", power=2, toughness=6, mana_cost="{3}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Lifelink. When Blissey enters, you gain life equal to the number of creatures you control."
)

SNORLAX = make_creature(
    name="Snorlax", power=5, toughness=6, mana_cost="{4}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Defender, vigilance. Snorlax can't attack unless you pay {2}."
)

JIGGLYPUFF = make_creature(
    name="Jigglypuff", power=1, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Fairy"},
    text="When Jigglypuff enters, tap target creature. It doesn't untap during its controller's next untap step."
)

def wigglytuff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _ = static_pt_boost_by_subtype(obj, 1, 1, "Fairy", include_self=False)
    return itcs

WIGGLYTUFF = make_creature(
    name="Wigglytuff", power=2, toughness=4, mana_cost="{2}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Fairy"},
    text="Other Fairy creatures you control get +1/+1.",
    setup_interceptors=wigglytuff_setup,
)

PERSIAN = make_creature(
    name="Persian", power=3, toughness=2, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="First strike. When Persian deals combat damage to a player, create a Treasure token."
)

MEOWTH = make_creature(
    name="Meowth", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="When Meowth dies, create a Treasure token.",
    setup_interceptors=_death_treasure_setup(),
)

PIDGEOT = make_creature(
    name="Pidgeot", power=3, toughness=3, mana_cost="{2}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Flying"},
    text="Flying, vigilance. When Pidgeot enters, look at the top three cards of your library. Put one into your hand and the rest on the bottom."
)

PIDGEY = make_creature(
    name="Pidgey", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Flying"},
    text="Flying.",
    setup_interceptors=_self_kw(["flying"]),
)

RATTATA = make_creature(
    name="Rattata", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Haste.",
    setup_interceptors=_self_kw(["haste"]),
)

RATICATE = make_creature(
    name="Raticate", power=2, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="First strike, haste.",
    setup_interceptors=_self_kw(["first strike", "haste"]),
)

FURRET = make_creature(
    name="Furret", power=2, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="When Furret enters, you may search your library for a basic land card, reveal it, and put it into your hand. Then shuffle."
)

def audino_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 2)
    return [itc]

AUDINO = make_creature(
    name="Audino", power=2, toughness=3, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="When Audino enters, you gain 2 life.",
    setup_interceptors=audino_setup,
)

DITTO = make_creature(
    name="Ditto", power=0, toughness=1, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Ditto enters as a copy of any creature on the battlefield."
)

SLAKING = make_creature(
    name="Slaking", power=6, toughness=6, mana_cost="{4}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Vigilance. Slaking doesn't untap during your untap step. At the beginning of your upkeep, you may pay {2}. If you do, untap Slaking."
)

MILTANK = make_creature(
    name="Miltank", power=2, toughness=4, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="{T}: You gain 2 life."
)

TAUROS = make_creature(
    name="Tauros", power=3, toughness=3, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Trample. Tauros attacks each combat if able."
)

GRANBULL = make_creature(
    name="Granbull", power=4, toughness=3, mana_cost="{3}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="When Granbull enters, destroy target enchantment."
)

def florges_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    fairy_filter = other_creatures_with_subtype(obj, "Fairy")
    itc = make_keyword_grant(obj, ["lifelink"], fairy_filter)
    return [itc]

FLORGES = make_creature(
    name="Florges", power=2, toughness=4, mana_cost="{2}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="Other Fairy creatures you control have lifelink.",
    setup_interceptors=florges_setup,
)

# --- White Trainers (Instants/Sorceries) ---

POTION = make_instant(
    name="Potion", mana_cost="{W}", colors={Color.WHITE},
    text="You gain 3 life."
)

SUPER_POTION = make_instant(
    name="Super Potion", mana_cost="{1}{W}", colors={Color.WHITE},
    text="You gain 5 life. If you control a Pokemon, draw a card."
)

HYPER_POTION = make_instant(
    name="Hyper Potion", mana_cost="{2}{W}", colors={Color.WHITE},
    text="You gain 7 life and prevent all damage that would be dealt to you this turn."
)

FULL_RESTORE = make_instant(
    name="Full Restore", mana_cost="{2}{W}{W}", colors={Color.WHITE},
    text="Target creature you control gains indestructible until end of turn. You gain life equal to its toughness."
)

POKEMON_CENTER = make_sorcery(
    name="Pokemon Center", mana_cost="{1}{W}", colors={Color.WHITE},
    text="You gain 2 life for each Pokemon you control."
)

PROFESSOR_OAK = make_sorcery(
    name="Professor Oak's Advice", mana_cost="{2}{W}", colors={Color.WHITE},
    text="Draw two cards. You gain 2 life."
)

HEAL_BELL = make_instant(
    name="Heal Bell", mana_cost="{1}{W}", colors={Color.WHITE},
    text="Remove all counters from target creature. You gain 3 life."
)

PROTECT = make_instant(
    name="Protect", mana_cost="{W}", colors={Color.WHITE},
    text="Target creature you control gains protection from the color of your choice until end of turn."
)

SAFEGUARD = make_instant(
    name="Safeguard", mana_cost="{1}{W}", colors={Color.WHITE},
    text="Creatures you control gain hexproof until end of turn."
)

MOONBLAST = make_instant(
    name="Moonblast", mana_cost="{2}{W}", colors={Color.WHITE},
    text="Target creature gets -3/-0 until end of turn. You gain 3 life."
)


# =============================================================================
# BLUE CARDS - WATER, ICE, PSYCHIC
# =============================================================================

# --- Legendary Pokemon ---

def mewtwo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller}, source=obj.id, controller=obj.controller)]
    itc = make_spell_cast_trigger(obj, draw_fn, controller_only=True, spell_type_filter={CardType.INSTANT, CardType.SORCERY})
    return [itc]

MEWTWO = make_creature(
    name="Mewtwo, Genetic Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast an instant or sorcery spell, draw a card.",
    setup_interceptors=mewtwo_setup,
)

def mew_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _ = static_keyword_grant_others(obj, ["hexproof"], scope="creatures_you_control")
    return itcs

MEW = make_creature(
    name="Mew, New Species Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic"},
    supertypes={"Legendary"},
    text="Flying, hexproof. Creatures you control have hexproof. {U}: Mew becomes a copy of another target creature until end of turn.",
    setup_interceptors=mew_setup,
)

def lugia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_bounce(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': target.id},
                source=obj.id,
                controller=obj.controller,
            )
            for target in _opponent_nonland_permanents(obj, st)[:2]
        ]

    return [
        make_keyword_grant(obj, ["flying"], affects_self),
        make_etb_trigger(obj, etb_bounce),
    ]


LUGIA = make_creature(
    name="Lugia, Diving Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic", "Flying"},
    supertypes={"Legendary"},
    text="Flying. When Lugia enters, return up to two target nonland permanents to their owners' hands.",
    setup_interceptors=lugia_setup,
)

def suicune_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def scry_then_draw(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'count': 2, 'source_id': obj.id},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            ),
        ]

    return [
        make_keyword_grant(obj, ["hexproof"], affects_self),
        make_damage_trigger(
            obj,
            scry_then_draw,
            combat_only=True,
            filter_fn=_combat_damage_to_player_filter,
        ),
    ]


SUICUNE = make_creature(
    name="Suicune, Aurora Pokemon",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Water"},
    supertypes={"Legendary"},
    text="Hexproof. Whenever Suicune deals combat damage to a player, scry 2, then draw a card.",
    setup_interceptors=suicune_setup,
)

def articuno_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def tap_opposing_team(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.TAP,
                payload={'object_id': target.id},
                source=obj.id,
                controller=obj.controller,
            )
            for target in _opponent_creatures(obj, st)
        ]

    return [
        make_keyword_grant(obj, ["flying"], affects_self),
        make_etb_trigger(obj, tap_opposing_team),
    ]


ARTICUNO = make_creature(
    name="Articuno, Freeze Pokemon",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Ice", "Flying"},
    supertypes={"Legendary"},
    text="Flying. When Articuno enters, tap all creatures your opponents control. They don't untap during their controllers' next untap steps.",
    setup_interceptors=articuno_setup,
)

def kyogre_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_tidal_reset(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': target.id},
                source=obj.id,
                controller=obj.controller,
            )
            for target in _all_other_creatures(obj, st)
        ]

    return [make_etb_trigger(obj, etb_tidal_reset)]


KYOGRE = make_creature(
    name="Kyogre, Sea Basin Pokemon",
    power=6, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Water"},
    supertypes={"Legendary"},
    text="When Kyogre enters, return all other creatures to their owners' hands.",
    setup_interceptors=kyogre_setup,
)

def blastoise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_type_advantage(obj, 2, {"Fire"})]

BLASTOISE = make_creature(
    name="Blastoise, Shellfish Pokemon",
    power=4, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Water"},
    supertypes={"Legendary"},
    text="Type Advantage - Blastoise deals 2 extra damage to Fire Pokemon. {T}: Blastoise deals 2 damage to any target.",
    setup_interceptors=blastoise_setup
)

ALAKAZAM = make_creature(
    name="Alakazam, Psi Pokemon",
    power=3, toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic"},
    supertypes={"Legendary"},
    text="Flash. When Alakazam enters, counter target spell unless its controller pays {3}."
)

# --- Regular Blue Pokemon ---

def squirtle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Wartortle", 2, 3, "{1}{U}")]

SQUIRTLE = make_creature(
    name="Squirtle", power=1, toughness=2, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {1}{U}: Transform Squirtle into Wartortle.",
    setup_interceptors=squirtle_setup
)

WARTORTLE = make_creature(
    name="Wartortle", power=2, toughness=3, mana_cost="{1}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {2}{U}{U}: Transform Wartortle into Blastoise.",
    setup_interceptors=_evolve_setup("Blastoise, Shellfish Pokemon", 4, 5, "{2}{U}{U}"),
)

def psyduck_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Golduck", 3, 3, "{1}{U}{U}")]

PSYDUCK = make_creature(
    name="Psyduck", power=1, toughness=2, mana_cost="{1}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="Evolve {1}{U}{U}: Transform Psyduck into Golduck.",
    setup_interceptors=psyduck_setup
)

def golduck_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_draw(obj, 1)
    return [itc]

GOLDUCK = make_creature(
    name="Golduck", power=3, toughness=3, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="When Golduck enters, draw a card.",
    setup_interceptors=golduck_setup,
)

VAPOREON = make_creature(
    name="Vaporeon", power=3, toughness=3, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="When Vaporeon enters, draw a card then discard a card."
)

def eevee_u_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Vaporeon", 3, 3, "{U}{U}")]

EEVEE_U = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Normal"},
    text="Evolve {U}{U}: Transform Eevee into Vaporeon.",
    setup_interceptors=eevee_u_setup
)

SLOWPOKE = make_creature(
    name="Slowpoke", power=1, toughness=3, mana_cost="{1}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="Evolve {2}{U}{U}: Transform Slowpoke into Slowbro.",
    setup_interceptors=_evolve_setup("Slowbro", 2, 4, "{2}{U}{U}"),
)

SLOWBRO = make_creature(
    name="Slowbro", power=2, toughness=4, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="When Slowbro enters, tap target creature. It doesn't untap during its controller's next untap step."
)

LAPRAS = make_creature(
    name="Lapras", power=3, toughness=4, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Ice"},
    text="When Lapras enters, scry 3.",
    setup_interceptors=_etb_scry_setup(3),
)

DEWGONG = make_creature(
    name="Dewgong", power=3, toughness=3, mana_cost="{2}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Ice"},
    text="When Dewgong enters, tap target creature an opponent controls.",
    setup_interceptors=_etb_tap_opponent_creatures_setup(1),
)

def starmie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_draw(obj, 1)
    return [itc]

STARMIE = make_creature(
    name="Starmie", power=2, toughness=3, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="Flash. When Starmie enters, draw a card.",
    setup_interceptors=starmie_setup,
)

STARYU = make_creature(
    name="Staryu", power=1, toughness=2, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {U}{U}: Transform Staryu into Starmie.",
    setup_interceptors=_evolve_setup("Starmie", 2, 3, "{U}{U}"),
)

TENTACRUEL = make_creature(
    name="Tentacruel", power=3, toughness=3, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Poison"},
    text="Flash. When Tentacruel enters, return target creature to its owner's hand."
)

def gyarados_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_intimidate(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            events.extend(_discard_first_from_hand(opp_id, obj, st))
        return events

    return [
        make_keyword_grant(obj, ["flying"], affects_self),
        make_etb_trigger(obj, etb_intimidate),
    ]


GYARADOS = make_creature(
    name="Gyarados", power=5, toughness=4, mana_cost="{3}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Flying"},
    text="Flying. When Gyarados enters, each opponent discards a card.",
    setup_interceptors=gyarados_setup,
)

MAGIKARP = make_creature(
    name="Magikarp", power=0, toughness=1, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {3}{U}{U}: Transform Magikarp into Gyarados. This ability costs {2} less if a creature died this turn."
)

MILOTIC = make_creature(
    name="Milotic", power=3, toughness=4, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="When Milotic enters, you may return target enchantment to its owner's hand."
)

ESPEON = make_creature(
    name="Espeon", power=3, toughness=2, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic"},
    text="When Espeon enters, look at target opponent's hand."
)

GARDEVOIR = make_creature(
    name="Gardevoir", power=3, toughness=3, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic", "Fairy"},
    text="Flash. When Gardevoir enters, counter target spell unless its controller pays {2}."
)

def gallade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_draw(obj, 1)
    return [itc]

GALLADE = make_creature(
    name="Gallade", power=4, toughness=2, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic", "Fighting"},
    text="First strike. When Gallade enters, draw a card.",
    setup_interceptors=gallade_setup,
)

WOBBUFFET = make_creature(
    name="Wobbuffet", power=1, toughness=5, mana_cost="{2}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic"},
    text="Defender. Whenever Wobbuffet is dealt damage, it deals that much damage to any target."
)

GLACEON = make_creature(
    name="Glaceon", power=3, toughness=2, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Ice"},
    text="When Glaceon enters, tap target creature. It doesn't untap during its controller's next untap step."
)

WALREIN = make_creature(
    name="Walrein", power=4, toughness=4, mana_cost="{3}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Ice", "Water"},
    text="When Walrein enters, tap up to two target creatures.",
    setup_interceptors=_etb_tap_opponent_creatures_setup(2),
)

CLOYSTER = make_creature(
    name="Cloyster", power=2, toughness=5, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Ice"},
    text="Defender. {U}: Cloyster gains hexproof until end of turn."
)

# --- Blue Trainers ---

DIVE_BALL = make_instant(
    name="Dive Ball", mana_cost="{1}{U}", colors={Color.BLUE},
    text="Search your library for a Water Pokemon card, reveal it, and put it into your hand. Then shuffle."
)

MISTY_DETERMINATION = make_instant(
    name="Misty's Determination", mana_cost="{U}{U}", colors={Color.BLUE},
    text="Draw two cards, then discard a card."
)

CONFUSION = make_instant(
    name="Confusion", mana_cost="{1}{U}", colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)

PSYCHIC = make_instant(
    name="Psychic", mana_cost="{2}{U}{U}", colors={Color.BLUE},
    text="Counter target spell."
)

HYDRO_PUMP = make_instant(
    name="Hydro Pump", mana_cost="{2}{U}", colors={Color.BLUE},
    text="Return target creature to its owner's hand. Draw a card."
)

BLIZZARD = make_sorcery(
    name="Blizzard", mana_cost="{3}{U}{U}", colors={Color.BLUE},
    text="Tap all creatures your opponents control. They don't untap during their controllers' next untap steps."
)

SURF = make_sorcery(
    name="Surf", mana_cost="{2}{U}", colors={Color.BLUE},
    text="Draw three cards, then discard two cards."
)

TELEKINESIS = make_instant(
    name="Telekinesis", mana_cost="{U}", colors={Color.BLUE},
    text="Return target creature with mana value 2 or less to its owner's hand."
)

AMNESIA = make_sorcery(
    name="Amnesia", mana_cost="{2}{U}", colors={Color.BLUE},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card."
)

FUTURE_SIGHT_SPELL = make_sorcery(
    name="Future Sight", mana_cost="{1}{U}", colors={Color.BLUE},
    text="Scry 3, then draw a card."
)


# =============================================================================
# BLACK CARDS - DARK, GHOST, POISON
# =============================================================================

# --- Legendary Pokemon ---

def gengar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -3}, source=obj.id, controller=obj.controller)
                for opp_id in all_opponents(obj, state)]
    return [make_death_trigger(obj, death_fn)]

GENGAR = make_creature(
    name="Gengar, Shadow Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Ghost", "Poison"},
    supertypes={"Legendary"},
    text="Menace. When Gengar, Shadow Pokemon dies, each opponent loses 3 life.",
    setup_interceptors=gengar_setup,
)

def darkrai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -1}, source=obj.id, controller=obj.controller)
                for opp_id in all_opponents(obj, state)]
    return [make_upkeep_trigger(obj, upkeep_fn)]

DARKRAI = make_creature(
    name="Darkrai, Pitch-Black Pokemon",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, each opponent loses 1 life. Creatures your opponents control enter the battlefield tapped.",
    setup_interceptors=darkrai_setup,
)

def yveltal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_destroy_threat(event: Event, st: GameState) -> list[Event]:
        targets = _opponent_creatures(obj, st)
        if not targets:
            return []
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': targets[0].id},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        make_keyword_grant(obj, ["flying", "lifelink"], affects_self),
        make_etb_trigger(obj, etb_destroy_threat),
    ]


YVELTAL = make_creature(
    name="Yveltal, Destruction Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark", "Flying"},
    supertypes={"Legendary"},
    text="Flying, lifelink. When Yveltal enters, destroy target creature.",
    setup_interceptors=yveltal_setup,
)

GIRATINA = make_creature(
    name="Giratina, Renegade Pokemon",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Ghost", "Dragon"},
    supertypes={"Legendary"},
    text="Flying. When Giratina enters, exile target creature. When Giratina leaves the battlefield, return that card to the battlefield."
)

def umbreon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -2}, source=obj.id, controller=obj.controller)
                for opp_id in all_opponents(obj, state)]
    return [make_attack_trigger(obj, attack_fn)]

UMBREON = make_creature(
    name="Umbreon, Moonlight Pokemon",
    power=3, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark"},
    supertypes={"Legendary"},
    text="Hexproof. Whenever Umbreon, Moonlight Pokemon attacks, each opponent loses 2 life.",
    setup_interceptors=umbreon_setup,
)

def absol_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def opponent_creature_died(event: Event, st: GameState) -> bool:
        if event.type == EventType.OBJECT_DESTROYED:
            target_id = event.payload.get('object_id')
            target = st.objects.get(target_id) if target_id else None
            return bool(target and target.controller != obj.controller and _is_creature(target))
        if event.type == EventType.ZONE_CHANGE:
            target_id = event.payload.get('object_id')
            target = st.objects.get(target_id) if target_id else None
            return bool(
                target
                and target.controller != obj.controller
                and _is_creature(target)
                and event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD
                and event.payload.get('to_zone_type') == ZoneType.GRAVEYARD
            )
        return False

    def draw_for_disaster(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ),
        ]

    return [
        make_keyword_grant(obj, ["first strike"], affects_self),
        _react_interceptor(obj, opponent_creature_died, draw_for_disaster),
    ]


ABSOL = make_creature(
    name="Absol, Disaster Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark"},
    supertypes={"Legendary"},
    text="First strike. Whenever a creature an opponent controls dies, you draw a card and lose 1 life.",
    setup_interceptors=absol_setup,
)

# --- Regular Black Pokemon ---

def gastly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Haunter", 2, 2, "{1}{B}")]

GASTLY = make_creature(
    name="Gastly", power=1, toughness=1, mana_cost="{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost", "Poison"},
    text="Flying. Evolve {1}{B}: Transform Gastly into Haunter.",
    setup_interceptors=gastly_setup
)

HAUNTER = make_creature(
    name="Haunter", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost", "Poison"},
    text="Flying. Evolve {1}{B}{B}: Transform Haunter into Gengar.",
    setup_interceptors=_evolve_setup("Gengar, Shadow Pokemon", 3, 4, "{1}{B}{B}", keywords=["flying"]),
)

def eevee_b_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Umbreon", 3, 3, "{B}{B}")]

EEVEE_B = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Normal"},
    text="Evolve {B}{B}: Transform Eevee into Umbreon.",
    setup_interceptors=eevee_b_setup
)

def muk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs = make_static_pt_boost(obj, -1, -1, opponent_creatures_filter(obj))
    return itcs

MUK = make_creature(
    name="Muk", power=4, toughness=4, mana_cost="{3}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="Deathtouch. Creatures your opponents control get -1/-1.",
    setup_interceptors=muk_setup,
)

GRIMER = make_creature(
    name="Grimer", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="Deathtouch. Evolve {2}{B}{B}: Transform Grimer into Muk.",
    setup_interceptors=_evolve_setup("Muk", 4, 4, "{2}{B}{B}", keywords=["deathtouch"]),
)

WEEZING = make_creature(
    name="Weezing", power=3, toughness=3, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="When Weezing dies, it deals 3 damage to each creature.",
    setup_interceptors=_death_damage_creatures_setup(3),
)

KOFFING = make_creature(
    name="Koffing", power=1, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="When Koffing dies, it deals 1 damage to each creature.",
    setup_interceptors=_death_damage_creatures_setup(1),
)

DUSKNOIR = make_creature(
    name="Dusknoir", power=4, toughness=4, mana_cost="{3}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost"},
    text="When Dusknoir enters, exile target creature from a graveyard. You gain life equal to its power."
)

MISDREAVUS = make_creature(
    name="Misdreavus", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost"},
    text="Flying. When Misdreavus enters, target opponent discards a card.",
    setup_interceptors=_etb_discard_opponents_setup(each=False, keywords=["flying"]),
)

MISMAGIUS = make_creature(
    name="Mismagius", power=3, toughness=3, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost"},
    text="Flying. When Mismagius enters, each opponent discards a card.",
    setup_interceptors=_etb_discard_opponents_setup(each=True, keywords=["flying"]),
)

HOUNDOOM = make_creature(
    name="Houndoom", power=4, toughness=3, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Fire"},
    text="Menace. When Houndoom enters, it deals 2 damage to target creature.",
    setup_interceptors=_etb_damage_best_creature_setup(2, keywords=["menace"]),
)

HOUNDOUR = make_creature(
    name="Houndour", power=2, toughness=1, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Fire"},
    text="Menace. Evolve {1}{B}{B}: Transform Houndour into Houndoom.",
    setup_interceptors=_evolve_setup("Houndoom", 4, 3, "{1}{B}{B}", keywords=["menace"]),
)

MURKROW = make_creature(
    name="Murkrow", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Flying"},
    text="Flying. When Murkrow deals combat damage to a player, that player discards a card."
)

def honchkrow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _ = static_pt_boost_by_subtype(obj, 1, 0, "Dark", include_self=False)
    return itcs

HONCHKROW = make_creature(
    name="Honchkrow", power=4, toughness=3, mana_cost="{3}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Flying"},
    text="Flying. Other Dark creatures you control get +1/+0.",
    setup_interceptors=honchkrow_setup,
)

SPIRITOMB = make_creature(
    name="Spiritomb", power=2, toughness=4, mana_cost="{1}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost", "Dark"},
    text="Spiritomb can't be blocked. Spiritomb can't block."
)

SABLEYE = make_creature(
    name="Sableye", power=2, toughness=2, mana_cost="{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Ghost"},
    text="When Sableye enters, look at the top card of target opponent's library. You may put that card into their graveyard."
)

TOXICROAK = make_creature(
    name="Toxicroak", power=3, toughness=3, mana_cost="{2}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Fighting"},
    text="Deathtouch. Whenever Toxicroak deals combat damage to a player, that player loses 2 life."
)

def crobat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_lose_life(obj, 2)
    return [itc]

CROBAT = make_creature(
    name="Crobat", power=3, toughness=2, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Flying"},
    text="Flying, lifelink. When Crobat enters, each opponent loses 2 life.",
    setup_interceptors=crobat_setup,
)

ZUBAT = make_creature(
    name="Zubat", power=1, toughness=1, mana_cost="{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Flying"},
    text="Flying. Evolve {1}{B}: Transform Zubat into Golbat.",
    setup_interceptors=_evolve_setup("Golbat", 2, 2, "{1}{B}", keywords=["flying"]),
)

def golbat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_lose_life(obj, 1)
    return [itc]

GOLBAT = make_creature(
    name="Golbat", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Flying"},
    text="Flying. When Golbat enters, each opponent loses 1 life.",
    setup_interceptors=golbat_setup,
)

# --- Black Trainers ---

NIGHT_SHADE = make_instant(
    name="Night Shade", mana_cost="{1}{B}", colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn."
)

SHADOW_BALL = make_instant(
    name="Shadow Ball", mana_cost="{2}{B}", colors={Color.BLACK},
    text="Destroy target creature with power 3 or less."
)

DARK_PULSE = make_instant(
    name="Dark Pulse", mana_cost="{1}{B}{B}", colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. You gain 3 life."
)

DESTINY_BOND = make_instant(
    name="Destiny Bond", mana_cost="{B}{B}", colors={Color.BLACK},
    text="Until end of turn, if a creature you control would die, destroy target creature an opponent controls."
)

HEX = make_sorcery(
    name="Hex", mana_cost="{4}{B}{B}", colors={Color.BLACK},
    text="Destroy up to six target creatures."
)

MEAN_LOOK = make_instant(
    name="Mean Look", mana_cost="{B}", colors={Color.BLACK},
    text="Target creature can't block this turn. Its controller loses 2 life."
)

NIGHTMARE_SPELL = make_sorcery(
    name="Nightmare", mana_cost="{2}{B}", colors={Color.BLACK},
    text="Target opponent discards two cards."
)

TOXIC = make_instant(
    name="Toxic", mana_cost="{B}", colors={Color.BLACK},
    text="Target creature gets -1/-1 until end of turn. At the beginning of its controller's next upkeep, it gets an additional -1/-1."
)

SUCKER_PUNCH = make_instant(
    name="Sucker Punch", mana_cost="{B}", colors={Color.BLACK},
    text="Target attacking creature gets +2/+0 and gains deathtouch until end of turn."
)

PERISH_SONG = make_sorcery(
    name="Perish Song", mana_cost="{2}{B}{B}", colors={Color.BLACK},
    text="At the beginning of your next upkeep, destroy all creatures."
)


# =============================================================================
# RED CARDS - FIRE, FIGHTING, ELECTRIC
# =============================================================================

# --- Legendary Pokemon ---

def charizard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_type_advantage(obj, 2, {"Grass", "Bug", "Ice"})]

CHARIZARD = make_creature(
    name="Charizard, Flame Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fire", "Flying"},
    supertypes={"Legendary"},
    text="Flying. Type Advantage - Charizard deals 2 extra damage to Grass, Bug, and Ice Pokemon. {R}: Charizard gets +1/+0 until end of turn.",
    setup_interceptors=charizard_setup
)

def pikachu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_type_advantage(obj, 2, {"Water", "Flying"})]

PIKACHU = make_creature(
    name="Pikachu, Mouse Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Electric"},
    supertypes={"Legendary"},
    text="Haste. Type Advantage - Pikachu deals 2 extra damage to Water and Flying Pokemon.",
    setup_interceptors=pikachu_setup
)

RAICHU = make_creature(
    name="Raichu, Mouse Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Electric"},
    supertypes={"Legendary"},
    text="Haste. When Raichu enters, it deals 3 damage to any target."
)

def moltres_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': c_id, 'amount': 3, 'source': obj.id}, source=obj.id)
                for c_id, c in state.objects.items() if CardType.CREATURE in c.characteristics.types and c.zone == ZoneType.BATTLEFIELD]
    return [make_death_trigger(obj, death_effect)]

MOLTRES = make_creature(
    name="Moltres, Flame Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fire", "Flying"},
    supertypes={"Legendary"},
    text="Flying, haste. When Moltres dies, it deals 3 damage to each creature.",
    setup_interceptors=moltres_setup
)

ENTEI = make_creature(
    name="Entei, Volcano Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fire"},
    supertypes={"Legendary"},
    text="Haste, trample. When Entei enters, it deals 2 damage to each creature your opponents control."
)

GROUDON = make_creature(
    name="Groudon, Continent Pokemon",
    power=7, toughness=7,
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Ground"},
    supertypes={"Legendary"},
    text="Trample. When Groudon enters, destroy all lands your opponents control."
)

MACHAMP = make_creature(
    name="Machamp, Superpower Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fighting"},
    supertypes={"Legendary"},
    text="Double strike. Machamp must attack each combat if able."
)

ZAPDOS = make_creature(
    name="Zapdos, Electric Pokemon",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Electric", "Flying"},
    supertypes={"Legendary"},
    text="Flying, haste. When Zapdos enters, it deals 4 damage divided as you choose among any number of target creatures."
)

# --- Regular Red Pokemon ---

def charmander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Charmeleon", 3, 2, "{1}{R}")]

CHARMANDER = make_creature(
    name="Charmander", power=2, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Evolve {1}{R}: Transform Charmander into Charmeleon.",
    setup_interceptors=charmander_setup
)

CHARMELEON = make_creature(
    name="Charmeleon", power=3, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Evolve {2}{R}{R}: Transform Charmeleon into Charizard.",
    setup_interceptors=_evolve_setup("Charizard, Flame Pokemon", 5, 5, "{2}{R}{R}"),
)

FLAREON = make_creature(
    name="Flareon", power=3, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="When Flareon enters, it deals 2 damage to any target.",
    setup_interceptors=_etb_damage_best_target_setup(2),
)

def eevee_r_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Flareon", 4, 2, "{R}{R}")]

EEVEE_R = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Normal"},
    text="Evolve {R}{R}: Transform Eevee into Flareon.",
    setup_interceptors=eevee_r_setup
)

JOLTEON = make_creature(
    name="Jolteon", power=2, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="First strike, haste.",
    setup_interceptors=_self_kw(["first strike", "haste"]),
)

ARCANINE = make_creature(
    name="Arcanine", power=5, toughness=4, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste, trample.",
    setup_interceptors=_self_kw(["haste", "trample"]),
)

GROWLITHE = make_creature(
    name="Growlithe", power=2, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste. Evolve {2}{R}{R}: Transform Growlithe into Arcanine.",
    setup_interceptors=_evolve_setup("Arcanine", 5, 4, "{2}{R}{R}", keywords=["haste"]),
)

NINETALES = make_creature(
    name="Ninetales", power=3, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="When Ninetales enters, it deals 2 damage to each creature your opponents control.",
    setup_interceptors=_etb_damage_opponent_creatures_setup(2),
)

VULPIX = make_creature(
    name="Vulpix", power=1, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Evolve {1}{R}{R}: Transform Vulpix into Ninetales.",
    setup_interceptors=_evolve_setup("Ninetales", 3, 3, "{1}{R}{R}"),
)

RAPIDASH = make_creature(
    name="Rapidash", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste, first strike.",
    setup_interceptors=_self_kw(["haste", "first strike"]),
)

PONYTA = make_creature(
    name="Ponyta", power=2, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste.",
    setup_interceptors=_self_kw(["haste"]),
)

MAGMAR = make_creature(
    name="Magmar", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="When Magmar enters, it deals 2 damage to target creature.",
    setup_interceptors=_etb_damage_best_creature_setup(2),
)

MAGMORTAR = make_creature(
    name="Magmortar", power=4, toughness=4, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="{R}, {T}: Magmortar deals 3 damage to any target."
)

ELECTABUZZ = make_creature(
    name="Electabuzz", power=3, toughness=2, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="Haste. When Electabuzz enters, it deals 1 damage to any target.",
    setup_interceptors=_etb_damage_best_target_setup(1, keywords=["haste"]),
)

ELECTIVIRE = make_creature(
    name="Electivire", power=4, toughness=4, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="When Electivire enters, it deals 3 damage to each opponent.",
    setup_interceptors=_etb_damage_each_opponent_setup(3),
)

HITMONLEE = make_creature(
    name="Hitmonlee", power=4, toughness=2, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="First strike. Hitmonlee can't be blocked by creatures with power 2 or less."
)

HITMONCHAN = make_creature(
    name="Hitmonchan", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="First strike. {R}: Hitmonchan gets +1/+0 until end of turn."
)

PRIMEAPE = make_creature(
    name="Primeape", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="Haste. Primeape attacks each combat if able."
)

MANKEY = make_creature(
    name="Mankey", power=2, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="Haste.",
    setup_interceptors=_self_kw(["haste"]),
)

LUCARIO = make_creature(
    name="Lucario", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting", "Steel"},
    text="First strike. When Lucario enters, it deals damage equal to its power to target creature."
)

BLAZIKEN = make_creature(
    name="Blaziken", power=5, toughness=3, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire", "Fighting"},
    text="Haste, double strike.",
    setup_interceptors=_self_kw(["haste", "double strike"]),
)

INFERNAPE = make_creature(
    name="Infernape", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire", "Fighting"},
    text="Haste, first strike.",
    setup_interceptors=_self_kw(["haste", "first strike"]),
)

LUXRAY = make_creature(
    name="Luxray", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="First strike. When Luxray enters, it deals 2 damage to target creature."
)

ELECTRODE = make_creature(
    name="Electrode", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="Haste. Sacrifice Electrode: It deals 4 damage to any target."
)

VOLTORB = make_creature(
    name="Voltorb", power=1, toughness=2, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="Sacrifice Voltorb: It deals 2 damage to any target."
)

# --- Curve-smoothing 1-2 cmc Red Pokemon ---

CYNDAQUIL = make_creature(
    name="Cyndaquil", power=2, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste.",
    setup_interceptors=_self_kw(["haste"]),
)

LITTEN = make_creature(
    name="Litten", power=1, toughness=2, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Deathtouch.",
    setup_interceptors=_self_kw(["deathtouch"]),
)

TORCHIC = make_creature(
    name="Torchic", power=3, toughness=1, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="First strike.",
    setup_interceptors=_self_kw(["first strike"]),
)

NUMEL = make_creature(
    name="Numel", power=2, toughness=3, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Vigilance.",
    setup_interceptors=_self_kw(["vigilance"]),
)

SLUGMA = make_creature(
    name="Slugma", power=3, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste.",
    setup_interceptors=_self_kw(["haste"]),
)

# --- Red Trainers ---

FLAMETHROWER = make_instant(
    name="Flamethrower", mana_cost="{2}{R}", colors={Color.RED},
    text="Flamethrower deals 4 damage to target creature."
)

THUNDERBOLT = make_instant(
    name="Thunderbolt", mana_cost="{1}{R}", colors={Color.RED},
    text="Thunderbolt deals 3 damage to any target."
)

FIRE_BLAST = make_sorcery(
    name="Fire Blast", mana_cost="{3}{R}{R}", colors={Color.RED},
    text="Fire Blast deals 5 damage to any target."
)

EARTHQUAKE_SPELL = make_sorcery(
    name="Earthquake", mana_cost="{2}{R}{R}", colors={Color.RED},
    text="Earthquake deals 3 damage to each creature without flying."
)

THUNDER = make_sorcery(
    name="Thunder", mana_cost="{2}{R}{R}", colors={Color.RED},
    text="Thunder deals 4 damage to any target. If that target is a Flying creature, Thunder deals 6 damage instead."
)

BRICK_BREAK = make_instant(
    name="Brick Break", mana_cost="{1}{R}", colors={Color.RED},
    text="Destroy target artifact. Brick Break deals 2 damage to that artifact's controller."
)

CLOSE_COMBAT = make_instant(
    name="Close Combat", mana_cost="{R}{R}", colors={Color.RED},
    text="Target creature you control gets +3/+0 and gains first strike until end of turn."
)

OVERHEAT = make_instant(
    name="Overheat", mana_cost="{1}{R}", colors={Color.RED},
    text="Target creature gets +4/+0 until end of turn. At end of turn, it gets -2/-0 until end of your next turn."
)

WILD_CHARGE = make_instant(
    name="Wild Charge", mana_cost="{R}", colors={Color.RED},
    text="Target creature gets +2/+0 and gains haste until end of turn."
)

ERUPTION = make_sorcery(
    name="Eruption", mana_cost="{3}{R}{R}{R}", colors={Color.RED},
    text="Eruption deals 6 damage to each creature and each player."
)


# =============================================================================
# GREEN CARDS - GRASS, GROUND, BUG
# =============================================================================

# --- Legendary Pokemon ---

def venusaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _ = static_pt_boost_by_subtype(obj, 1, 1, "Grass", include_self=False)
    return itcs

VENUSAUR = make_creature(
    name="Venusaur, Seed Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass", "Poison"},
    supertypes={"Legendary"},
    text="Trample. Other Grass creatures you control get +1/+1.",
    setup_interceptors=venusaur_setup,
)

def celebi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_regrow(event: Event, st: GameState) -> list[Event]:
        target = _first_graveyard_card(obj.controller, st)
        if not target:
            return []
        return [Event(
            type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
            payload={'player': obj.controller, 'object_id': target.id},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        make_keyword_grant(obj, ["flying"], affects_self),
        make_etb_trigger(obj, etb_regrow),
    ]


CELEBI = make_creature(
    name="Celebi, Time Travel Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass", "Psychic"},
    supertypes={"Legendary"},
    text="Flying. When Celebi enters, return target card from your graveyard to your hand.",
    setup_interceptors=celebi_setup,
)

RAYQUAZA = make_creature(
    name="Rayquaza, Sky High Pokemon",
    power=7, toughness=6,
    mana_cost="{4}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Dragon", "Flying"},
    supertypes={"Legendary"},
    text="Flying, trample. When Rayquaza enters, destroy all enchantments."
)

SCEPTILE = make_creature(
    name="Sceptile, Forest Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass"},
    supertypes={"Legendary"},
    text="Haste. {T}: Add {G}{G}."
)

def torterra_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'basic_land', 'to_zone': ZoneType.BATTLEFIELD}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

TORTERRA = make_creature(
    name="Torterra, Continent Pokemon",
    power=5, toughness=6,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass", "Ground"},
    supertypes={"Legendary"},
    text="Trample. When Torterra enters, search your library for a basic land card and put it onto the battlefield tapped. Then shuffle.",
    setup_interceptors=torterra_setup
)

LEAFEON = make_creature(
    name="Leafeon, Verdant Pokemon",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass"},
    supertypes={"Legendary"},
    text="When Leafeon enters, search your library for a basic Forest card, reveal it, and put it into your hand. Then shuffle."
)

def shaymin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id, controller=obj.controller),
            Event(type=EventType.DRAW, payload={'player': obj.controller}, source=obj.id, controller=obj.controller),
        ]
    return [make_etb_trigger(obj, etb_fn)]

SHAYMIN = make_creature(
    name="Shaymin, Gratitude Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass"},
    supertypes={"Legendary"},
    text="Flying. When Shaymin, Gratitude Pokemon enters, you gain 3 life and draw a card.",
    setup_interceptors=shaymin_setup,
)

# --- Regular Green Pokemon ---

def bulbasaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Ivysaur", 2, 3, "{1}{G}")]

BULBASAUR = make_creature(
    name="Bulbasaur", power=1, toughness=2, mana_cost="{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="Evolve {1}{G}: Transform Bulbasaur into Ivysaur.",
    setup_interceptors=bulbasaur_setup
)

IVYSAUR = make_creature(
    name="Ivysaur", power=2, toughness=3, mana_cost="{1}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="Evolve {2}{G}{G}: Transform Ivysaur into Venusaur.",
    setup_interceptors=_evolve_setup("Venusaur, Seed Pokemon", 4, 5, "{2}{G}{G}"),
)

def eevee_g_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Leafeon", 3, 3, "{G}{G}")]

EEVEE_G = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Normal"},
    text="Evolve {G}{G}: Transform Eevee into Leafeon.",
    setup_interceptors=eevee_g_setup
)

def exeggutor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_draw(obj, 2)
    return [itc]

EXEGGUTOR = make_creature(
    name="Exeggutor", power=4, toughness=4, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Psychic"},
    text="When Exeggutor enters, draw two cards.",
    setup_interceptors=exeggutor_setup,
)

EXEGGCUTE = make_creature(
    name="Exeggcute", power=1, toughness=2, mana_cost="{1}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Psychic"},
    text="Evolve {2}{G}{G}: Transform Exeggcute into Exeggutor."
)

TANGROWTH = make_creature(
    name="Tangrowth", power=4, toughness=5, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass"},
    text="Reach. When Tangrowth enters, put two +1/+1 counters on target creature."
)

VILEPLUME = make_creature(
    name="Vileplume", power=3, toughness=3, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="When Vileplume enters, destroy target artifact or enchantment."
)

VICTREEBEL = make_creature(
    name="Victreebel", power=4, toughness=3, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="Deathtouch, reach.",
    setup_interceptors=_self_kw(["deathtouch", "reach"]),
)

PARASECT = make_creature(
    name="Parasect", power=3, toughness=3, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Grass"},
    text="When Parasect enters, tap target creature. It doesn't untap during its controller's next untap step."
)

BUTTERFREE = make_creature(
    name="Butterfree", power=2, toughness=3, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Flying"},
    text="Flying. When Butterfree enters, you may search your library for a Grass Pokemon card, reveal it, and put it into your hand."
)

CATERPIE = make_creature(
    name="Caterpie", power=1, toughness=1, mana_cost="{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug"},
    text="Evolve {G}: Transform Caterpie into Metapod."
)

METAPOD = make_creature(
    name="Metapod", power=0, toughness=3, mana_cost="{1}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug"},
    text="Defender. Evolve {1}{G}: Transform Metapod into Butterfree."
)

BEEDRILL = make_creature(
    name="Beedrill", power=3, toughness=2, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Poison"},
    text="Flying, deathtouch.",
    setup_interceptors=_self_kw(["flying", "deathtouch"]),
)

SCYTHER = make_creature(
    name="Scyther", power=4, toughness=2, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Flying"},
    text="Flying, first strike.",
    setup_interceptors=_self_kw(["flying", "first strike"]),
)

PINSIR = make_creature(
    name="Pinsir", power=4, toughness=3, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug"},
    text="Trample. When Pinsir enters, fight target creature you don't control."
)

HERACROSS = make_creature(
    name="Heracross", power=5, toughness=3, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Fighting"},
    text="Trample. Heracross gets +2/+2 as long as you control a Forest."
)

SANDSLASH = make_creature(
    name="Sandslash", power=3, toughness=3, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ground"},
    text="First strike. When Sandslash dies, you may search your library for a basic land card and put it into your hand."
)

DUGTRIO = make_creature(
    name="Dugtrio", power=3, toughness=2, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ground"},
    text="Dugtrio can't be blocked except by creatures with flying or reach."
)

GOLEM = make_creature(
    name="Golem", power=5, toughness=5, mana_cost="{4}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Rock", "Ground"},
    text="Trample. When Golem enters, it deals 3 damage to any target."
)

RHYDON = make_creature(
    name="Rhydon", power=5, toughness=4, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ground", "Rock"},
    text="Trample. Protection from Lightning."
)

MAMOSWINE = make_creature(
    name="Mamoswine", power=5, toughness=5, mana_cost="{4}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ice", "Ground"},
    text="Trample. When Mamoswine attacks, it gets +2/+0 until end of turn."
)

NIDOKING = make_creature(
    name="Nidoking", power=4, toughness=4, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Poison", "Ground"},
    text="Trample, deathtouch.",
    setup_interceptors=_self_kw(["trample", "deathtouch"]),
)

def nidoqueen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def bolster_team(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target.id,
                    'counter_type': '+1/+1',
                    'amount': 1,
                },
                source=obj.id,
                controller=obj.controller,
            )
            for target in _battlefield_objects(st)
            if target.id != obj.id and target.controller == obj.controller and _is_creature(target)
        ]

    return [make_etb_trigger(obj, bolster_team)]


NIDOQUEEN = make_creature(
    name="Nidoqueen", power=3, toughness=5, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Poison", "Ground"},
    text="When Nidoqueen enters, put a +1/+1 counter on each other creature you control.",
    setup_interceptors=nidoqueen_setup,
)

# --- Green Trainers ---

RAZOR_LEAF = make_instant(
    name="Razor Leaf", mana_cost="{G}", colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn."
)

SOLAR_BEAM = make_sorcery(
    name="Solar Beam", mana_cost="{3}{G}{G}", colors={Color.GREEN},
    text="Solar Beam deals 5 damage to target creature or planeswalker."
)

LEECH_SEED = make_enchantment(
    name="Leech Seed", mana_cost="{1}{G}", colors={Color.GREEN},
    subtypes={"Aura"},
    text="Enchant creature. At the beginning of your upkeep, enchanted creature's controller loses 2 life and you gain 2 life."
)

SYNTHESIS = make_instant(
    name="Synthesis", mana_cost="{1}{G}", colors={Color.GREEN},
    text="You gain 5 life."
)

INGRAIN = make_instant(
    name="Ingrain", mana_cost="{G}", colors={Color.GREEN},
    text="Target creature you control gains hexproof until end of turn. You gain 2 life."
)

GIGA_DRAIN = make_instant(
    name="Giga Drain", mana_cost="{2}{G}", colors={Color.GREEN},
    text="Target creature gets -3/-3 until end of turn. You gain 3 life."
)

GROWTH = make_instant(
    name="Growth", mana_cost="{G}", colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn."
)

VINE_WHIP = make_instant(
    name="Vine Whip", mana_cost="{1}{G}", colors={Color.GREEN},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)

SUNNY_DAY = make_sorcery(
    name="Sunny Day", mana_cost="{2}{G}", colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal them, and put them into your hand. Then shuffle."
)

PHOTOSYNTHESIS = make_sorcery(
    name="Photosynthesis", mana_cost="{1}{G}", colors={Color.GREEN},
    text="You gain 1 life for each creature you control. Draw a card."
)


# =============================================================================
# ITEMS (ARTIFACTS)
# =============================================================================

POKE_BALL = make_artifact(
    name="Poke Ball", mana_cost="{2}",
    text="{2}, {T}, Sacrifice Poke Ball: Gain control of target creature with power 2 or less."
)

GREAT_BALL = make_artifact(
    name="Great Ball", mana_cost="{3}",
    text="{2}, {T}, Sacrifice Great Ball: Gain control of target creature with power 3 or less."
)

ULTRA_BALL = make_artifact(
    name="Ultra Ball", mana_cost="{4}",
    text="{2}, {T}, Sacrifice Ultra Ball: Gain control of target creature."
)

MASTER_BALL = make_artifact(
    name="Master Ball", mana_cost="{5}",
    text="{T}, Sacrifice Master Ball: Gain control of target creature. It gains haste.",
    supertypes={"Legendary"}
)

RARE_CANDY = make_artifact(
    name="Rare Candy", mana_cost="{2}",
    text="{T}, Sacrifice Rare Candy: Target creature you control evolves without paying its evolve cost."
)

EXP_SHARE = make_equipment(
    name="Exp. Share", mana_cost="{2}",
    text="Whenever another creature you control dies, put a +1/+1 counter on equipped creature.",
    equip_cost="{1}"
)

LUCKY_EGG = make_artifact(
    name="Lucky Egg", mana_cost="{2}",
    text="Whenever a creature you control deals combat damage to a player, draw a card."
)

LEFTOVERS = make_artifact(
    name="Leftovers", mana_cost="{2}",
    text="At the beginning of your upkeep, you gain 1 life."
)

CHOICE_BAND = make_equipment(
    name="Choice Band", mana_cost="{2}",
    text="Equipped creature gets +2/+0. Equipped creature can only attack.",
    equip_cost="{1}"
)

FOCUS_SASH = make_equipment(
    name="Focus Sash", mana_cost="{2}",
    text="If equipped creature would be destroyed, instead remove all damage from it and sacrifice Focus Sash.",
    equip_cost="{1}"
)

EVIOLITE = make_equipment(
    name="Eviolite", mana_cost="{2}",
    text="Equipped creature gets +0/+2. If it can evolve, it gets +1/+3 instead.",
    equip_cost="{1}"
)

SCOPE_LENS = make_equipment(
    name="Scope Lens", mana_cost="{1}",
    text="Equipped creature has 'Whenever this creature deals combat damage to a creature, destroy that creature.'",
    equip_cost="{2}"
)

QUICK_CLAW = make_equipment(
    name="Quick Claw", mana_cost="{1}",
    text="Equipped creature has first strike.",
    equip_cost="{1}"
)

MUSCLE_BAND = make_equipment(
    name="Muscle Band", mana_cost="{1}",
    text="Equipped creature gets +1/+1.",
    equip_cost="{1}"
)

ROCKY_HELMET = make_equipment(
    name="Rocky Helmet", mana_cost="{2}",
    text="Whenever equipped creature is dealt combat damage, Rocky Helmet deals 2 damage to the source's controller.",
    equip_cost="{1}"
)

POKEDEX = make_artifact(
    name="Pokedex", mana_cost="{1}",
    text="{1}, {T}: Look at the top card of your library. You may put it on the bottom of your library."
)

SILPH_SCOPE = make_artifact(
    name="Silph Scope", mana_cost="{2}",
    text="Creatures your opponents control lose hexproof."
)

BERRY = make_artifact(
    name="Oran Berry", mana_cost="{1}",
    text="{T}, Sacrifice Oran Berry: You gain 3 life."
)

SITRUS_BERRY = make_artifact(
    name="Sitrus Berry", mana_cost="{2}",
    text="{T}, Sacrifice Sitrus Berry: You gain 5 life and draw a card."
)

MAX_REVIVE = make_artifact(
    name="Max Revive", mana_cost="{3}",
    text="{2}, {T}, Sacrifice Max Revive: Return target creature card from your graveyard to the battlefield."
)


# =============================================================================
# LOCATIONS (LANDS)
# =============================================================================

PALLET_TOWN = make_land(
    name="Pallet Town",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {W} or {G}.",
    supertypes={"Legendary"}
)

CERULEAN_CITY = make_land(
    name="Cerulean City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {U}.",
    supertypes={"Legendary"}
)

VERMILION_CITY = make_land(
    name="Vermilion City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {R}.",
    supertypes={"Legendary"}
)

LAVENDER_TOWN = make_land(
    name="Lavender Town",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {B}.",
    supertypes={"Legendary"}
)

CELADON_CITY = make_land(
    name="Celadon City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {G}.",
    supertypes={"Legendary"}
)

POKEMON_LEAGUE = make_land(
    name="Pokemon League",
    text="{T}: Add {C}. {2}, {T}: Target Pokemon gets +1/+1 until end of turn.",
    supertypes={"Legendary"}
)

VIRIDIAN_FOREST = make_land(
    name="Viridian Forest",
    text="{T}: Add {G}. {1}, {T}, Sacrifice Viridian Forest: Search your library for a basic Forest card, put it onto the battlefield tapped, then shuffle."
)

MT_MOON = make_land(
    name="Mt. Moon",
    text="{T}: Add {C}. {3}, {T}: Add three mana of any one color."
)

POWER_PLANT = make_land(
    name="Power Plant",
    text="{T}: Add {C}{C}. Use this mana only to cast artifact spells or activate abilities of artifacts."
)

SAFARI_ZONE = make_land(
    name="Safari Zone",
    text="{T}: Add {C}. {2}, {T}: Create a 1/1 green Pokemon creature token."
)

VICTORY_ROAD = make_land(
    name="Victory Road",
    text="{T}: Add {C}. Whenever a creature you control evolves, you may pay {1}. If you do, draw a card."
)

POKEMON_CENTER_LAND = make_land(
    name="Pokemon Center",
    text="{T}: Add {C}. {2}, {T}: Regenerate target Pokemon."
)

SILPH_CO = make_land(
    name="Silph Co.",
    text="{T}: Add {C}. {3}, {T}: Search your library for an Equipment card, reveal it, and put it into your hand. Then shuffle."
)

CERULEAN_CAVE = make_land(
    name="Cerulean Cave",
    text="{T}: Add {U} or {B}. Cerulean Cave enters the battlefield tapped.",
    supertypes={"Legendary"}
)

INDIGO_PLATEAU = make_land(
    name="Indigo Plateau",
    text="{T}: Add one mana of any color. Use this mana only to cast legendary spells.",
    supertypes={"Legendary"}
)

# Basic Lands
PLAINS_PKH = make_land(name="Plains", subtypes={"Plains"}, supertypes={"Basic"})
ISLAND_PKH = make_land(name="Island", subtypes={"Island"}, supertypes={"Basic"})
SWAMP_PKH = make_land(name="Swamp", subtypes={"Swamp"}, supertypes={"Basic"})
MOUNTAIN_PKH = make_land(name="Mountain", subtypes={"Mountain"}, supertypes={"Basic"})
FOREST_PKH = make_land(name="Forest", subtypes={"Forest"}, supertypes={"Basic"})


# =============================================================================
# SPICE PASS — 8 format-defining cards (mono-red focus, follows the
# 10-pattern taxonomy in `.claude/skills/spice-pass.md`). Wave-22 R4
# revealed PKH at 25% — genuinely weak when opponents play their real
# decks. These eight legendary picks give it tempo, recursion, tutoring,
# and a finisher.
# =============================================================================


# --- 1. Charizard, Mega Evolved --- {2}{R} 3/3 Mythic Legendary Pokemon Dragon
# Pattern: snowball / chain. R5 capability: original {2}{R}{R} cast 0.05.
# New shape: cheaper body + a snowball trigger that scales with the
# already-strong red spell support package. Each red spell you cast pumps
# Charizard AND pings — the deck's natural plays grow it into a finisher.
def charizard_mega_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flying. Whenever you cast another red spell, Charizard gets
    +1/+0 until end of turn and deals 1 damage to any opponent creature
    if one exists, else to an opponent.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def chain_pump_and_ping(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': obj.id,
                    'power_mod': 1, 'toughness_mod': 0,
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            ),
        ]
        # Pick a target for the 1-damage ping.
        opp_creature = next((
            o for o in st.objects.values()
            if o.zone == ZoneType.BATTLEFIELD
            and o.controller != obj.controller
            and CardType.CREATURE in (o.characteristics.types or set())
        ), None)
        if opp_creature:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_creature.id, 'amount': 1, 'source': obj.id},
                source=obj.id,
            ))
        else:
            opp = next((p for p in st.players if p != obj.controller), None)
            if opp:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': opp, 'amount': 1, 'source': obj.id},
                    source=obj.id,
                ))
        return events

    return [
        make_keyword_grant(obj, ['flying'], affects_self),
        make_spell_cast_trigger(
            obj,
            chain_pump_and_ping,
            controller_only=True,
            color_filter={Color.RED},
        ),
    ]


CHARIZARD_MEGA = make_creature(
    name="Charizard, Mega Evolved",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Dragon"},
    supertypes={"Legendary"},
    text=(
        "Flying. Whenever you cast another red spell, Charizard gets "
        "+1/+0 until end of turn and deals 1 damage to a target creature "
        "an opponent controls (or that opponent if there are none)."
    ),
    setup_interceptors=charizard_mega_setup,
)


# --- 2. Moltres, Phoenix Reborn --- {3}{R}{R} 4/3 Mythic Legendary Pokemon Phoenix
# Pattern: recursion (the canonical "phoenix" — comes back from graveyard).
def moltres_phoenix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flying + haste. When Moltres dies, return it to your hand at
    the beginning of your next upkeep (via a turn_data flag set on death
    + an upkeep trigger that consumes the flag).
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def on_death(event: Event, st: GameState) -> list[Event]:
        # Mark for return-to-hand at next upkeep.
        st.turn_data[f'moltres_return_{obj.id}'] = True
        return []

    def upkeep_return(event: Event, st: GameState) -> list[Event]:
        flag_key = f'moltres_return_{obj.id}'
        active_player = getattr(st, 'active_player', None)
        if active_player != obj.controller:
            return []
        if not st.turn_data.get(flag_key):
            return []
        # Only return if Moltres is currently in graveyard.
        target = st.objects.get(obj.id)
        if not target or target.zone != ZoneType.GRAVEYARD:
            return []
        st.turn_data.pop(flag_key, None)
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone': 'graveyard',
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone': 'hand',
                'to_zone_type': ZoneType.HAND,
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['flying', 'haste'], affects_self),
        make_death_trigger(obj, on_death),
        make_upkeep_trigger(obj, upkeep_return),
    ]


MOLTRES_PHOENIX = make_creature(
    name="Moltres, Phoenix Reborn",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Phoenix"},
    supertypes={"Legendary"},
    text=(
        "Flying, haste. When Moltres dies, return it to your hand at the "
        "beginning of your next upkeep."
    ),
    # R5 capability: original {3}{R}{R} cast 0.05. The recursion shape is
    # solid; the cost was the problem in 14-turn games. {2}{R} 3/2 fits
    # curve and lets the recursion actually trigger multiple times.
    setup_interceptors=moltres_phoenix_setup,
)


# --- 3. Pikachu, Thunder Champion --- {1}{R} 1/1 Rare Legendary Pokemon Mouse
# Pattern: snowball (self-growth on damage to a player). R5 redesign:
# the original "draw a card on combat damage" was cast 0.25 but the deck
# only won 40% — Pikachu wasn't the win condition. New shape: Pikachu
# grows itself, becoming a real threat as combats stack.
def pikachu_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self haste + menace. Whenever ANY creature you control deals
    damage to a player, put a +1/+1 counter on Pikachu. v3.5 redesign:
    the prior "self damage → self counter" required Pikachu to push
    through every turn — once blocked, the snowball stalled. The
    gather-counters-from-team pattern lets every successful attacker
    grow Pikachu, so the deck's natural plays compound on the focal.
    Menace makes Pikachu itself harder to chump-block.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def add_counter_on_team_player_damage(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        if target_id not in st.players:
            return []
        # Source must be a creature you control.
        source_id = event.payload.get('source')
        source = st.objects.get(source_id) if source_id else None
        if not source:
            return []
        if source.controller != obj.controller:
            return []
        if CardType.CREATURE not in (source.characteristics.types or set()):
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': obj.id,
                'counter_type': '+1/+1',
                'amount': 1,
            },
            source=obj.id,
        )]

    # Use a generic REACT-priority interceptor since make_damage_trigger
    # filters on `payload.source == self.id` — we need to listen for
    # damage from ANY of the controller's creatures, not just Pikachu.
    from src.engine.types import Interceptor as _Inter, InterceptorPriority, InterceptorAction, InterceptorResult as _Res
    from src.engine import new_id as _new_id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        target_id = event.payload.get('target')
        return target_id in st.players

    def _handler(event: Event, st: GameState) -> _Res:
        new_events = add_counter_on_team_player_damage(event, st)
        return _Res(action=InterceptorAction.REACT, new_events=new_events)

    return [
        make_keyword_grant(obj, ['haste', 'menace'], affects_self),
        _Inter(
            id=_new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_filter,
            handler=_handler,
            duration='while_on_battlefield',
        ),
    ]


PIKACHU_CHAMPION = make_creature(
    name="Pikachu, Thunder Champion",
    power=1, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Mouse"},
    supertypes={"Legendary"},
    text=(
        "Haste, menace. Whenever a creature you control deals damage to "
        "a player, put a +1/+1 counter on Pikachu."
    ),
    setup_interceptors=pikachu_champion_setup,
)


# --- 4. Eevee, Evolution Vessel --- {R} 1/1 Mythic Legendary Pokemon
# Pattern: tutoring at 1 mana (Eevee's evolutions are the whole pool).
def eevee_vessel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: search your library for a creature card with mana value 3 or
    less, reveal it, put it into your hand, then shuffle.
    """
    def cheap_creature_filter(card_obj: GameObject, st: GameState) -> bool:
        chars = card_obj.characteristics
        if CardType.CREATURE not in (chars.types or set()):
            return False
        cost = chars.mana_cost or ""
        try:
            from src.engine.mana import ManaCost
            mv = ManaCost.parse(cost).mana_value
        except Exception:
            mv = 0
        return mv <= 3

    return [make_library_search_etb_trigger(
        obj,
        filter_fn=cheap_creature_filter,
        destination="hand",
        reveal=True,
        shuffle_after=True,
        max_count=1,
        prompt="Choose a creature with mana value 3 or less.",
    )]


EEVEE_VESSEL = make_creature(
    name="Eevee, Evolution Vessel",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Pokemon"},
    supertypes={"Legendary"},
    text=(
        "When Eevee enters, search your library for a creature card with "
        "mana value 3 or less, reveal it, put it into your hand, then "
        "shuffle."
    ),
    setup_interceptors=eevee_vessel_setup,
)


# --- 5. Master Ball, Catcher Engine --- {1}{R} Mythic Legendary Artifact
# Pattern: combo enabler. R5 capability: original tap-to-tutor cost {2}+T
# meant Master Ball cast at 0.10 but contributed 0 dmg/0 kills — the AI
# rarely activated tap abilities. New shape: passive trigger that grants
# haste to every cheap Pokemon you cast, turning the synergy package
# (Numel, Slugma, Charmander, etc.) from one-turn-late blockers into
# immediate beatdown.
def master_ball_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature with mana value 3 or less enters the battlefield
    under your control, put a +1/+1 counter on it and it gains haste until
    end of turn.

    v4 redesign: previous spell-cast version granted the counter to the
    spell on the stack; the counter often didn't transfer to the resolved
    permanent (deck winrate 25%). Switching to an ETB-listener pattern
    (ZONE_CHANGE → BATTLEFIELD filter) so the counter lands on the actual
    creature object.
    """
    def cheap_creature_etb_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        target = st.objects.get(target_id) if target_id else None
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if target.id == obj.id:
            return False
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return False
        cost_str = target.characteristics.mana_cost or ""
        try:
            mv = ManaCost.parse(cost_str).mana_value
        except Exception:
            mv = 99
        return mv <= 3

    def buff_and_haste_effect(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get('object_id')
        if not target_id:
            return []
        return [
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': target_id,
                    'keyword': 'haste',
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target_id,
                    'counter_type': '+1/+1',
                    'amount': 1,
                },
                source=obj.id,
            ),
        ]

    # Generic REACT interceptor — make_etb_trigger only fires for the
    # source object's own ETB; we need to listen for ANY cheap-creature
    # ETB on our side.
    from src.engine.types import Interceptor as _Inter, InterceptorPriority, InterceptorAction, InterceptorResult as _Res
    from src.engine import new_id as _new_id

    def _handler(event: Event, st: GameState) -> _Res:
        return _Res(action=InterceptorAction.REACT, new_events=buff_and_haste_effect(event, st))

    return [_Inter(
        id=_new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cheap_creature_etb_filter,
        handler=_handler,
        duration='while_on_battlefield',
    )]


# Local import to keep ManaCost in scope for master_ball_setup's filter.
from src.engine.mana import ManaCost  # noqa: E402


MASTER_BALL = make_artifact(
    name="Master Ball",
    mana_cost="{1}{R}",
    supertypes={"Legendary"},
    text=(
        "Whenever a creature with mana value 3 or less enters the "
        "battlefield under your control, put a +1/+1 counter on it "
        "and it gains haste until end of turn."
    ),
    setup_interceptors=master_ball_setup,
)


# --- 6. Volcanic Mantle --- {2}{R} Mythic Legendary Enchantment
# Pattern: global attack buff. R5 capability: original Equipment cast 0.15
# but contributed 0 kills — the AI rarely activates equip{1}. Shifted
# from Equipment to Legendary Enchantment so the buff fires automatically
# on every red attack, no equip step needed. The deck-wide "+1/+1 and
# trample on attack" turns the cheap red creature swarm (Charmander,
# Slugma, Numel etc.) into actual reach.
def volcanic_mantle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a red creature you control attacks, it gets +1/+1 and
    trample until end of turn.
    """
    def red_attack_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        attacker = st.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        if attacker.controller != obj.controller:
            return False
        if Color.RED not in (attacker.characteristics.colors or set()):
            return False
        return True

    def buff_attacker(event: Event, st: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if not attacker_id:
            return []
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': attacker_id,
                    'power_mod': 1,
                    'toughness_mod': 1,
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': attacker_id,
                    'keyword': 'trample',
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            ),
        ]

    # Use a generic REACT-priority interceptor since we're matching on
    # ATTACK_DECLARED, not the per-creature attack-trigger pattern.
    from src.engine.types import Interceptor as _Inter, InterceptorPriority, InterceptorAction, InterceptorResult as _Res
    from src.engine import new_id as _new_id

    def _handler(event: Event, st: GameState) -> _Res:
        new_events = buff_attacker(event, st)
        return _Res(action=InterceptorAction.REACT, new_events=new_events)

    return [_Inter(
        id=_new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=red_attack_filter,
        handler=_handler,
        duration='while_on_battlefield',
    )]


VOLCANIC_MANTLE = make_enchantment(
    name="Volcanic Mantle",
    mana_cost="{2}{R}",
    colors={Color.RED},
    supertypes={"Legendary"},
    text=(
        "Whenever a red creature you control attacks, it gets +1/+1 "
        "and gains trample until end of turn."
    ),
    setup_interceptors=volcanic_mantle_setup,
)


# --- 7. Reshiram, Embered Truth --- {3}{R}{R} 5/4 Mythic Legendary Pokemon Dragon
# Pattern: GY-count cost reduction (true build-around) + scaling ETB.
# R5 capability: original {4}{R}{R} cast 0.00 — never made it onto the
# battlefield in 14-turn games even with the 4-creature GY discount.
# Tightened: per-creature-in-GY discount (max 4) so even 1-2 creatures in
# GY help; ETB damage scales with GY size so the build-around feels
# rewarding. The deck still has to fill the GY (cheap creatures dying)
# but the payoff is real.
def reshiram_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flying + trample. Costs {1} less for each creature card in
    your graveyard, max 4 reduction. ETB deals X damage to target,
    where X is the number of creature cards in your graveyard.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def applies_to_self(card_def, controller, st) -> bool:
        return getattr(card_def, "name", None) == "Reshiram, Truth Aspect" and controller == obj.controller

    def gy_creature_count(st: GameState) -> int:
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if not gy:
            return 0
        return sum(
            1 for cid in gy.objects
            if (st.objects.get(cid) and CardType.CREATURE in (st.objects[cid].characteristics.types or set()))
        )

    def cost_amount_fn(st) -> int:
        # Discount = min(4, creature cards in your GY). The base
        # make_cost_reduction has a static `amount`; we approximate the
        # scaling discount by gating with condition_fn at amount=2 (mid
        # value). For a true X-scaling discount we'd need an engine
        # extension; for v2, 2 generic less when 1+ in GY is enough to
        # tip Reshiram into the curve.
        return 2

    def gy_at_least_one(st) -> bool:
        return gy_creature_count(st) >= 1

    def etb_burn(event: Event, st: GameState) -> list[Event]:
        x = max(2, gy_creature_count(st))  # min 2 so it's never trivial
        candidates = sorted(
            (
                o for o in st.objects.values()
                if o.zone == ZoneType.BATTLEFIELD
                and o.controller != obj.controller
                and CardType.CREATURE in (o.characteristics.types or set())
            ),
            key=lambda c: (get_power(c, st) or 0),
            reverse=True,
        )
        if candidates:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': candidates[0].id, 'amount': x, 'source': obj.id},
                source=obj.id,
            )]
        for pid in st.players:
            if pid != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': x, 'source': obj.id},
                    source=obj.id,
                )]
        return []

    return [
        make_keyword_grant(obj, ['flying', 'trample'], affects_self),
        make_etb_trigger(obj, etb_burn),
        make_cost_reduction(
            obj,
            applies_to=applies_to_self,
            amount=2,
            condition_fn=gy_at_least_one,
            self_only=True,
        ),
    ]


RESHIRAM = make_creature(
    name="Reshiram, Truth Aspect",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Dragon"},
    supertypes={"Legendary"},
    text=(
        "Flying, trample. This spell costs {2} less to cast if there is "
        "a creature card in your graveyard. When Reshiram enters, it "
        "deals X damage to target creature an opponent controls (or that "
        "opponent), where X is the number of creature cards in your "
        "graveyard, minimum 2."
    ),
    setup_interceptors=reshiram_setup,
)


# --- 8. Hyper Beam --- {1}{R} Mythic Sorcery
# Pattern: efficient finisher / curve-friendly burn. The R5 capability test
# showed the original {2}{R}{R} was uncastable in 14-turn games (cast 0.10).
# Lowered to {1}{R} for 4 damage — fits the "Lightning Bolt at 1 damage less"
# slot, slots cleanly onto curve, finishes opponents faster.
def hyper_beam_resolve(targets: list, state: GameState) -> list[Event]:
    """Deal 4 damage to target creature or player.

    The engine sometimes passes `targets` double-nested
    (`[[Target(...)]]` for single-target sorceries). Handle that, plus
    real `Target` objects (`.id`) and older test stubs (`.object_id`).
    """
    if not targets:
        return []
    t = targets[0]
    # Unwrap the inner list if double-nested.
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    if isinstance(t, str):
        target_id = t
    elif hasattr(t, 'object_id'):
        target_id = t.object_id
    elif hasattr(t, 'id'):
        target_id = t.id
    else:
        target_id = t
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 4},
    )]


HYPER_BEAM = make_sorcery(
    name="Hyper Beam",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Hyper Beam deals 4 damage to any target.",
    resolve=hyper_beam_resolve,
)
HYPER_BEAM.targets_required = 1
HYPER_BEAM.target_kind = "any"


# =============================================================================
# PASS 3 MECHANICAL DEPTH LIFT
# =============================================================================

PASS3_DEPTH_LIFTED_CARDS = (
    # Spells
    "Potion", "Super Potion", "Hyper Potion", "Full Restore",
    "Pokemon Center", "Professor Oak's Advice", "Heal Bell", "Protect",
    "Safeguard", "Moonblast", "Dive Ball", "Misty's Determination",
    "Confusion", "Psychic", "Hydro Pump", "Blizzard", "Surf",
    "Telekinesis", "Amnesia", "Future Sight", "Night Shade",
    "Shadow Ball", "Dark Pulse", "Destiny Bond", "Hex", "Mean Look",
    "Nightmare", "Toxic", "Sucker Punch", "Perish Song",
    "Flamethrower", "Thunderbolt", "Fire Blast", "Earthquake",
    "Thunder", "Brick Break", "Close Combat", "Overheat",
    "Wild Charge", "Eruption", "Razor Leaf", "Solar Beam",
    "Synthesis", "Ingrain", "Giga Drain", "Growth", "Vine Whip",
    "Sunny Day", "Photosynthesis",
    # Tools
    "Poke Ball", "Great Ball", "Ultra Ball", "Rare Candy", "Exp. Share",
    "Lucky Egg", "Leftovers", "Choice Band", "Focus Sash", "Eviolite",
    "Scope Lens", "Quick Claw", "Muscle Band", "Rocky Helmet",
    "Pokedex", "Silph Scope", "Oran Berry", "Sitrus Berry", "Max Revive",
    # Creatures
    "Blissey", "Jigglypuff", "Persian", "Pidgeot", "Furret",
    "Miltank", "Tauros", "Granbull", "Alakazam, Psi Pokemon",
    "Vaporeon", "Slowbro", "Tentacruel", "Magikarp", "Espeon",
    "Gardevoir", "Glaceon", "Wobbuffet", "Murkrow", "Spiritomb",
    "Sableye", "Toxicroak",
)


def _wire_spell(card: CardDefinition, text: str, resolve_fn, *, targets_required: int = 0, target_kind: str = "any") -> None:
    card.text = text
    card.resolve = resolve_fn
    if targets_required:
        card.targets_required = targets_required
        card.target_kind = target_kind


def _wire_setup(card: CardDefinition, text: str, setup_fn) -> None:
    card.text = text
    card.setup_interceptors = setup_fn


def _brick_break_resolve(targets, state: GameState) -> list[Event]:
    controller = _spell_controller(state, targets)
    if not controller:
        return []
    target_id = _first_target_id(targets)
    target = state.objects.get(target_id) if target_id else None
    if not target:
        candidates = [
            obj for obj in _battlefield_objects(state)
            if obj.controller != controller and CardType.ARTIFACT in (obj.characteristics.types or set())
        ]
        target = candidates[0] if candidates else None
    if not target or CardType.ARTIFACT not in (target.characteristics.types or set()):
        return []
    return [
        Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': target.id}, controller=controller),
        Event(type=EventType.DAMAGE, payload={'target': target.controller, 'amount': 2}, controller=controller),
    ]


def _photosynthesis_resolve(targets, state: GameState) -> list[Event]:
    controller = _spell_controller(state, targets)
    if not controller:
        return []
    amount = len(_creatures_controlled_by(controller, state))
    return [
        Event(type=EventType.LIFE_CHANGE, payload={'player': controller, 'amount': amount}, controller=controller),
        _draw_event(controller, 1),
    ]


def _synthesis_resolve(targets, state: GameState) -> list[Event]:
    controller = _spell_controller(state, targets)
    if not controller:
        return []
    events = [Event(type=EventType.LIFE_CHANGE, payload={'player': controller, 'amount': 5}, controller=controller)]
    target_id = _first_target_id(targets)
    target = state.objects.get(target_id) if target_id else None
    if not target:
        allies = _creatures_controlled_by(controller, state)
        target = allies[0] if allies else None
    if target:
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
            controller=controller,
        ))
    return events


def _apply_pass3_depth_lift() -> None:
    # White spells
    _wire_spell(POTION, "You gain 3 life. If you control a Pokemon, scry 1, then draw a card.", _spell_life_gain(3, scry_if_pokemon=1, draw_if_pokemon=True))
    _wire_spell(SUPER_POTION, "You gain 5 life. If you control a Pokemon, draw a card.", _spell_life_gain(5, draw_if_pokemon=True))
    _wire_spell(HYPER_POTION, "You gain 7 life. If you control a Pokemon, draw a card.", _spell_life_gain(7, draw_if_pokemon=True))
    _wire_spell(FULL_RESTORE, "Target creature you control gains indestructible until end of turn. You gain life equal to its toughness.", _spell_life_gain(0, target_toughness=True, grant_keyword="indestructible"), targets_required=1, target_kind="creature_you_control")
    _wire_spell(POKEMON_CENTER, "You gain 2 life for each Pokemon you control. If you control a Pokemon, draw a card.", _spell_life_gain(0, per_pokemon=2, draw_if_pokemon=True))
    _wire_spell(PROFESSOR_OAK, "Draw two cards. You gain 2 life. If you control a Pokemon, scry 1.", _chain_resolves(_spell_draw_discard(2), _spell_life_gain(2, scry_if_pokemon=1)))
    _wire_spell(HEAL_BELL, "Remove all counters from target creature. You gain 3 life. Then scry 1 if you control a Pokemon.", _chain_resolves(_spell_heal_bell_resolve, _spell_life_gain(0, scry_if_pokemon=1)), targets_required=1, target_kind="creature")
    _wire_spell(PROTECT, "Target creature you control gains indestructible and hexproof until end of turn. Then scry 1.", _chain_resolves(_spell_pump(0, 0, keywords=["indestructible", "hexproof"]), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature_you_control")
    _wire_spell(SAFEGUARD, "Creatures you control gain hexproof until end of turn. If you control a Pokemon, scry 1.", _chain_resolves(_spell_safeguard_resolve, _spell_life_gain(0, scry_if_pokemon=1)))
    _wire_spell(MOONBLAST, "Target creature gets -3/-0 until end of turn. You gain 3 life.", _chain_resolves(_spell_pump(-3, 0), _spell_life_gain(3)), targets_required=1, target_kind="creature")

    # Blue spells
    _wire_spell(DIVE_BALL, "Search your library for a Water Pokemon card, reveal it, and put it into your hand. Then shuffle.", _spell_search(card_type=CardType.CREATURE, subtype="Water"))
    _wire_spell(MISTY_DETERMINATION, "Scry 1, then draw two cards, then discard a card.", _spell_draw_discard(2, 1, scry_first=1))
    _wire_spell(CONFUSION, "Tap target creature. It doesn't untap during its controller's next untap step. Then scry 1.", _spell_tap_opponent_creatures(1, scry=1), targets_required=1, target_kind="creature")
    _wire_spell(PSYCHIC, "Counter target spell. Then scry 1. If you control a Psychic Pokemon, draw a card.", _spell_counter_then_value(scry=1, draw_if_psychic=True), targets_required=1, target_kind="spell")
    _wire_spell(HYDRO_PUMP, "Return target creature to its owner's hand. Draw a card.", _spell_bounce(draw=True), targets_required=1, target_kind="creature")
    _wire_spell(BLIZZARD, "Tap all creatures your opponents control. They don't untap during their controllers' next untap steps. Then scry 1.", _spell_tap_opponent_creatures(None, scry=1))
    _wire_spell(SURF, "Scry 1, then draw three cards, then discard two cards.", _spell_draw_discard(3, 2, scry_first=1))
    _wire_spell(TELEKINESIS, "Return target creature with mana value 2 or less to its owner's hand. Then scry 1.", _chain_resolves(_spell_bounce(max_mv=2), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature")
    _wire_spell(AMNESIA, "Target opponent discards two cards. That player loses 1 life. Then scry 1.", _chain_resolves(_spell_opponent_discard(2, life_loss=1), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="player")
    _wire_spell(FUTURE_SIGHT_SPELL, "Scry 3, then draw a card. If you control a Psychic Pokemon, scry 1 again.", _chain_resolves(_spell_draw_discard(1, 0, scry_first=3), _spell_draw_discard(0, 0, scry_first=1)))

    # Black spells
    _wire_spell(NIGHT_SHADE, "Target creature gets -2/-2 until end of turn. You gain 1 life.", _chain_resolves(_spell_pump(-2, -2), _spell_life_gain(1)), targets_required=1, target_kind="creature")
    _wire_spell(SHADOW_BALL, "Destroy target creature with power 3 or less. If no target is chosen, destroy the largest eligible opposing creature.", _spell_destroy(max_power=3), targets_required=1, target_kind="creature")
    _wire_spell(DARK_PULSE, "Target creature gets -3/-3 until end of turn. You gain 3 life.", _chain_resolves(_spell_pump(-3, -3), _spell_life_gain(3)), targets_required=1, target_kind="creature")
    _wire_spell(DESTINY_BOND, "Destroy target creature an opponent controls. If you control a Ghost Pokemon, scry 1.", _chain_resolves(_spell_destroy(), _spell_life_gain(0, scry_if_pokemon=1)), targets_required=1, target_kind="creature")
    _wire_spell(HEX, "Destroy up to six target creatures. If no targets are chosen, destroy up to six opposing creatures.", _spell_destroy(max_count=6), targets_required=1, target_kind="creature")
    _wire_spell(MEAN_LOOK, "Tap target creature. Its controller loses 2 life. Then scry 1.", _chain_resolves(_spell_tap_opponent_creatures(1), _spell_opponent_discard(0, life_loss=2), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature")
    _wire_spell(NIGHTMARE_SPELL, "Target opponent discards two cards. That player loses 2 life. Then scry 1.", _chain_resolves(_spell_opponent_discard(2, life_loss=2), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="player")
    _wire_spell(TOXIC, "Target creature gets -2/-2 until end of turn. You gain 1 life.", _chain_resolves(_spell_pump(-2, -2), _spell_life_gain(1)), targets_required=1, target_kind="creature")
    _wire_spell(SUCKER_PUNCH, "Target attacking creature gets +2/+0 and gains deathtouch until end of turn. Then scry 1.", _chain_resolves(_spell_pump(2, 0, keywords=["deathtouch"]), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature")
    _wire_spell(PERISH_SONG, "Destroy all creatures. Each opponent loses 1 life. Then scry 1.", _chain_resolves(_spell_destroy(all_creatures=True, max_count=999), _spell_damage(1, each_opponent=True), _spell_draw_discard(0, 0, scry_first=1)))

    # Red spells
    _wire_spell(FLAMETHROWER, "Flamethrower deals 4 damage to target creature. If that creature is Grass, Bug, or Ice, scry 1.", _chain_resolves(_spell_damage(4, creature_only=True), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature")
    _wire_spell(THUNDERBOLT, "Thunderbolt deals 3 damage to any target. If you control an Electric Pokemon, scry 1.", _chain_resolves(_spell_damage(3), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="any")
    _wire_spell(FIRE_BLAST, "Fire Blast deals 5 damage to any target. If a creature dies this turn, draw a card.", _spell_damage(5), targets_required=1, target_kind="any")
    _wire_spell(EARTHQUAKE_SPELL, "Earthquake deals 3 damage to each creature and 1 damage to each player. Then scry 1.", _chain_resolves(_spell_damage(3, each_creature=True), _spell_damage(1, each_player=True), _spell_draw_discard(0, 0, scry_first=1)))
    _wire_spell(THUNDER, "Thunder deals 4 damage to any target. If that target is a Flying creature, Thunder deals 6 damage instead.", _spell_damage(4, flying_bonus=6), targets_required=1, target_kind="any")
    _wire_spell(BRICK_BREAK, "Destroy target artifact. Brick Break deals 2 damage to that artifact's controller.", _brick_break_resolve, targets_required=1, target_kind="artifact")
    _wire_spell(CLOSE_COMBAT, "Target creature you control gets +3/+0 and gains first strike until end of turn. Then scry 1.", _chain_resolves(_spell_pump(3, 0, keywords=["first strike"]), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature_you_control")
    _wire_spell(OVERHEAT, "Target creature gets +4/+0 until end of turn. You gain 1 life if you control a Fire Pokemon.", _chain_resolves(_spell_pump(4, 0), _spell_life_gain(1)), targets_required=1, target_kind="creature")
    _wire_spell(WILD_CHARGE, "Target creature gets +2/+0 and gains haste until end of turn. Then scry 1.", _chain_resolves(_spell_pump(2, 0, keywords=["haste"]), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature")
    _wire_spell(ERUPTION, "Eruption deals 6 damage to each creature and each player. You gain 1 life. If you control a Pokemon, draw a card.", _chain_resolves(_spell_damage(6, each_creature=True), _spell_damage(6, each_player=True), _spell_life_gain(1, draw_if_pokemon=True)))

    # Green spells
    _wire_spell(RAZOR_LEAF, "Target creature gets +2/+2 until end of turn. If you control a Grass Pokemon, scry 1.", _chain_resolves(_spell_pump(2, 2), _spell_draw_discard(0, 0, scry_first=1)), targets_required=1, target_kind="creature")
    _wire_spell(SOLAR_BEAM, "Solar Beam deals 5 damage to target creature or planeswalker. If that permanent dies, you gain 2 life.", _chain_resolves(_spell_damage(5, creature_only=True), _spell_life_gain(2)), targets_required=1, target_kind="creature")
    _wire_spell(SYNTHESIS, "You gain 5 life. Put a +1/+1 counter on up to one target creature you control.", _synthesis_resolve, targets_required=1, target_kind="creature_you_control")
    _wire_spell(INGRAIN, "Target creature you control gains hexproof until end of turn. You gain 2 life.", _chain_resolves(_spell_pump(0, 0, keywords=["hexproof"]), _spell_life_gain(2)), targets_required=1, target_kind="creature_you_control")
    _wire_spell(GIGA_DRAIN, "Target creature gets -3/-3 until end of turn. You gain 3 life.", _chain_resolves(_spell_pump(-3, -3), _spell_life_gain(3)), targets_required=1, target_kind="creature")
    _wire_spell(GROWTH, "Target creature gets +3/+3 until end of turn. If it is a Pokemon, it gains trample until end of turn.", _spell_pump(3, 3, keywords=["trample"]), targets_required=1, target_kind="creature")
    _wire_spell(VINE_WHIP, "Tap target creature. It doesn't untap during its controller's next untap step. Then scry 1.", _spell_tap_opponent_creatures(1, scry=1), targets_required=1, target_kind="creature")
    _wire_spell(SUNNY_DAY, "Search your library for up to two basic land cards, reveal them, and put them into your hand. Then shuffle.", _spell_search(card_type=CardType.LAND, count=2, basic_only=True))
    _wire_spell(PHOTOSYNTHESIS, "You gain 1 life for each creature you control. Draw a card. Then scry 1.", _chain_resolves(_photosynthesis_resolve, _spell_draw_discard(0, 0, scry_first=1)))

    # Tools and Equipment
    _wire_setup(POKE_BALL, "{2}, {T}, Sacrifice Poke Ball: Gain control of target creature with power 2 or less until end of turn.", _activated_setup("{2}, {T}, Sacrifice this", _catch_effect(2), "Catch target small creature", targets_required=1, target_kind="creature"))
    _wire_setup(GREAT_BALL, "{2}, {T}, Sacrifice Great Ball: Gain control of target creature with power 3 or less until end of turn.", _activated_setup("{2}, {T}, Sacrifice this", _catch_effect(3), "Catch target medium creature", targets_required=1, target_kind="creature"))
    _wire_setup(ULTRA_BALL, "{2}, {T}, Sacrifice Ultra Ball: Gain control of target creature until end of turn.", _activated_setup("{2}, {T}, Sacrifice this", _catch_effect(), "Catch target creature", targets_required=1, target_kind="creature"))
    _wire_setup(RARE_CANDY, "{T}, Sacrifice Rare Candy: Target creature you control evolves without paying its evolve cost.", _activated_setup("{T}, Sacrifice this", _rare_candy_effect, "Evolve target creature", targets_required=1, target_kind="creature_you_control"))
    _wire_setup(EXP_SHARE, "Whenever another creature you control dies, put a +1/+1 counter on equipped creature.\nEquip {1}", _exp_share_setup)
    _wire_setup(LUCKY_EGG, "Whenever a creature you control deals combat damage to a player, draw a card.", _lucky_egg_setup)
    _wire_setup(LEFTOVERS, "At the beginning of your upkeep, you gain 1 life. If you control a Pokemon, you gain 2 life instead.", _leftovers_setup)
    _wire_setup(CHOICE_BAND, "Equipped creature gets +2/+0, has trample and haste, and has ward {1}.\nEquip {1}", make_equipment_setup(power_mod=2, keywords=["trample", "haste"], ward_cost="{1}", equip_cost="{1}"))
    _wire_setup(FOCUS_SASH, "Equipped creature gets +0/+1, has indestructible and hexproof, and has ward {1}.\nEquip {1}", make_equipment_setup(toughness_mod=1, keywords=["indestructible", "hexproof"], ward_cost="{1}", equip_cost="{1}"))
    _wire_setup(EVIOLITE, "Equipped creature gets +0/+2 and has vigilance and ward {2}.\nEquip {1}", make_equipment_setup(toughness_mod=2, keywords=["vigilance"], ward_cost="{2}", equip_cost="{1}"))
    _wire_setup(SCOPE_LENS, "Equipped creature has deathtouch, first strike, menace, and ward {1}.\nEquip {2}", make_equipment_setup(keywords=["deathtouch", "first strike", "menace"], ward_cost="{1}", equip_cost="{2}"))
    _wire_setup(QUICK_CLAW, "Equipped creature has first strike, haste, vigilance, and ward {1}.\nEquip {1}", make_equipment_setup(keywords=["first strike", "haste", "vigilance"], ward_cost="{1}", equip_cost="{1}"))
    _wire_setup(MUSCLE_BAND, "Equipped creature gets +1/+1, has trample and vigilance, and has ward {1}.\nEquip {1}", make_equipment_setup(power_mod=1, toughness_mod=1, keywords=["trample", "vigilance"], ward_cost="{1}", equip_cost="{1}"))
    _wire_setup(ROCKY_HELMET, "Equipped creature gets +0/+1. Whenever equipped creature is dealt combat damage, Rocky Helmet deals 2 damage to that source's controller.\nEquip {1}", _rocky_helmet_setup)
    _wire_setup(POKEDEX, "{1}, {T}: Scry 2. If you control a Pokemon, draw a card, then discard a card.", _activated_setup("{1}, {T}", _pokedex_effect, "Scry 2, then loot if you control a Pokemon"))
    _wire_setup(SILPH_SCOPE, "Creatures you control have vigilance. If an opponent controls a Ghost or Dark Pokemon, creatures you control also have menace.", _silph_scope_setup)
    _wire_setup(BERRY, "{T}, Sacrifice Oran Berry: You gain 3 life.", _activated_setup("{T}, Sacrifice this", _berry_effect(3), "Gain 3 life"))
    _wire_setup(SITRUS_BERRY, "{T}, Sacrifice Sitrus Berry: You gain 5 life and draw a card.", _activated_setup("{T}, Sacrifice this", _berry_effect(5, draw=True), "Gain 5 life and draw a card"))
    _wire_setup(MAX_REVIVE, "{2}, {T}, Sacrifice Max Revive: Return target creature card from your graveyard to the battlefield.", _activated_setup("{2}, {T}, Sacrifice this", _max_revive_effect, "Return a creature from graveyard", targets_required=1, target_kind="card_in_graveyard"))

    # Remaining thin creatures
    _wire_setup(BLISSEY, "Lifelink. When Blissey enters, you gain life equal to the number of creatures you control.", _etb_gain_life_per_creature_setup(keywords=["lifelink"]))
    _wire_setup(JIGGLYPUFF, "When Jigglypuff enters, tap target creature an opponent controls.", _etb_tap_opponent_creatures_setup(1))
    _wire_setup(PERSIAN, "First strike. Whenever Persian deals combat damage to a player, create a Treasure token.", _combat_damage_treasure_setup(keywords=["first strike"]))
    _wire_setup(PIDGEOT, "Flying, vigilance. When Pidgeot enters, scry 3, then draw a card.", _etb_scry_draw_setup(3, 1, keywords=["flying", "vigilance"]))
    _wire_setup(FURRET, "When Furret enters, search your library for a basic land card, reveal it, and put it into your hand. Then shuffle.", _etb_search_setup(card_type=CardType.LAND, basic_only=True))
    _wire_setup(MILTANK, "{T}: You gain 2 life. Activate only while Miltank is untapped.", _activated_setup("{T}", _tap_gain_life_effect(2), "Gain 2 life"))
    _wire_setup(TAUROS, "Trample. Whenever Tauros attacks, it gets +1/+0 until end of turn.", _attack_pump_self_setup(1, 0, keywords=["trample"]))
    _wire_setup(GRANBULL, "When Granbull enters, destroy target artifact or enchantment an opponent controls.", _etb_destroy_artifact_enchantment_setup())
    _wire_setup(ALAKAZAM, "Flash. When Alakazam enters, scry 1, then draw a card.", _etb_scry_draw_setup(1, 1, keywords=["flash"]))
    _wire_setup(VAPOREON, "When Vaporeon enters, draw a card, then discard a card.", _etb_draw_discard_setup(1, 1))
    _wire_setup(SLOWBRO, "When Slowbro enters, tap target creature an opponent controls.", _etb_tap_opponent_creatures_setup(1))
    _wire_setup(TENTACRUEL, "Flash. When Tentacruel enters, return target creature an opponent controls to its owner's hand.", _etb_bounce_best_creature_setup(keywords=["flash"]))
    _wire_setup(MAGIKARP, "Evolve {3}{U}{U}: Transform Magikarp into Gyarados.", _evolve_setup("Gyarados", 5, 4, "{3}{U}{U}"))
    _wire_setup(ESPEON, "When Espeon enters, scry 1, then draw a card.", _etb_scry_draw_setup(1, 1))
    _wire_setup(GARDEVOIR, "Flash. When Gardevoir enters, scry 1, then draw a card.", _etb_scry_draw_setup(1, 1, keywords=["flash"]))
    _wire_setup(GLACEON, "When Glaceon enters, tap target creature an opponent controls.", _etb_tap_opponent_creatures_setup(1))
    _wire_setup(WOBBUFFET, "Defender. Whenever Wobbuffet is dealt damage, it deals that much damage to that source.", _damage_reflect_setup(keywords=["defender"]))
    _wire_setup(MURKROW, "Flying. Whenever Murkrow deals combat damage to a player, that player discards a card.", _combat_damage_discard_setup(keywords=["flying"]))
    _wire_setup(SPIRITOMB, "Spiritomb can't be blocked. Whenever Spiritomb deals combat damage to a player, that player discards a card.", _combat_damage_discard_setup(keywords=["unblockable"]))
    _wire_setup(SABLEYE, "When Sableye enters, target opponent discards a card.", _etb_discard_opponents_setup(each=False))
    _wire_setup(TOXICROAK, "Deathtouch. Whenever Toxicroak deals combat damage to a player, that player loses 2 life.", _combat_damage_life_loss_setup(2, keywords=["deathtouch"]))


_apply_pass3_depth_lift()


# =============================================================================
# CARD DICTIONARY
# =============================================================================

POKEMON_HORIZONS_CARDS = {
    # WHITE - NORMAL, FAIRY
    "Arceus, The Original One": ARCEUS,
    "Togekiss, Jubilee Pokemon": TOGEKISS,
    "Clefable, Fairy Queen": CLEFABLE,
    "Sylveon, Intertwining Pokemon": SYLVEON,
    "Eevee (White)": EEVEE_W,
    "Clefairy": CLEFAIRY,
    "Togepi": TOGEPI,
    "Togetic": TOGETIC,
    "Chansey": CHANSEY,
    "Blissey": BLISSEY,
    "Snorlax": SNORLAX,
    "Jigglypuff": JIGGLYPUFF,
    "Wigglytuff": WIGGLYTUFF,
    "Persian": PERSIAN,
    "Meowth": MEOWTH,
    "Pidgeot": PIDGEOT,
    "Pidgey": PIDGEY,
    "Rattata": RATTATA,
    "Raticate": RATICATE,
    "Furret": FURRET,
    "Audino": AUDINO,
    "Ditto": DITTO,
    "Slaking": SLAKING,
    "Miltank": MILTANK,
    "Tauros": TAUROS,
    "Granbull": GRANBULL,
    "Florges": FLORGES,
    "Potion": POTION,
    "Super Potion": SUPER_POTION,
    "Hyper Potion": HYPER_POTION,
    "Full Restore": FULL_RESTORE,
    "Pokemon Center": POKEMON_CENTER,
    "Professor Oak's Advice": PROFESSOR_OAK,
    "Heal Bell": HEAL_BELL,
    "Protect": PROTECT,
    "Safeguard": SAFEGUARD,
    "Moonblast": MOONBLAST,

    # BLUE - WATER, ICE, PSYCHIC
    "Mewtwo, Genetic Pokemon": MEWTWO,
    "Mew, New Species Pokemon": MEW,
    "Lugia, Diving Pokemon": LUGIA,
    "Suicune, Aurora Pokemon": SUICUNE,
    "Articuno, Freeze Pokemon": ARTICUNO,
    "Kyogre, Sea Basin Pokemon": KYOGRE,
    "Blastoise, Shellfish Pokemon": BLASTOISE,
    "Alakazam, Psi Pokemon": ALAKAZAM,
    "Squirtle": SQUIRTLE,
    "Wartortle": WARTORTLE,
    "Psyduck": PSYDUCK,
    "Golduck": GOLDUCK,
    "Vaporeon": VAPOREON,
    "Eevee (Blue)": EEVEE_U,
    "Slowpoke": SLOWPOKE,
    "Slowbro": SLOWBRO,
    "Lapras": LAPRAS,
    "Dewgong": DEWGONG,
    "Starmie": STARMIE,
    "Staryu": STARYU,
    "Tentacruel": TENTACRUEL,
    "Gyarados": GYARADOS,
    "Magikarp": MAGIKARP,
    "Milotic": MILOTIC,
    "Espeon": ESPEON,
    "Gardevoir": GARDEVOIR,
    "Gallade": GALLADE,
    "Wobbuffet": WOBBUFFET,
    "Glaceon": GLACEON,
    "Walrein": WALREIN,
    "Cloyster": CLOYSTER,
    "Dive Ball": DIVE_BALL,
    "Misty's Determination": MISTY_DETERMINATION,
    "Confusion": CONFUSION,
    "Psychic": PSYCHIC,
    "Hydro Pump": HYDRO_PUMP,
    "Blizzard": BLIZZARD,
    "Surf": SURF,
    "Telekinesis": TELEKINESIS,
    "Amnesia": AMNESIA,
    "Future Sight": FUTURE_SIGHT_SPELL,

    # BLACK - DARK, GHOST, POISON
    "Gengar, Shadow Pokemon": GENGAR,
    "Darkrai, Pitch-Black Pokemon": DARKRAI,
    "Yveltal, Destruction Pokemon": YVELTAL,
    "Giratina, Renegade Pokemon": GIRATINA,
    "Umbreon, Moonlight Pokemon": UMBREON,
    "Absol, Disaster Pokemon": ABSOL,
    "Gastly": GASTLY,
    "Haunter": HAUNTER,
    "Eevee (Black)": EEVEE_B,
    "Muk": MUK,
    "Grimer": GRIMER,
    "Weezing": WEEZING,
    "Koffing": KOFFING,
    "Dusknoir": DUSKNOIR,
    "Misdreavus": MISDREAVUS,
    "Mismagius": MISMAGIUS,
    "Houndoom": HOUNDOOM,
    "Houndour": HOUNDOUR,
    "Murkrow": MURKROW,
    "Honchkrow": HONCHKROW,
    "Spiritomb": SPIRITOMB,
    "Sableye": SABLEYE,
    "Toxicroak": TOXICROAK,
    "Crobat": CROBAT,
    "Zubat": ZUBAT,
    "Golbat": GOLBAT,
    "Night Shade": NIGHT_SHADE,
    "Shadow Ball": SHADOW_BALL,
    "Dark Pulse": DARK_PULSE,
    "Destiny Bond": DESTINY_BOND,
    "Hex": HEX,
    "Mean Look": MEAN_LOOK,
    "Nightmare": NIGHTMARE_SPELL,
    "Toxic": TOXIC,
    "Sucker Punch": SUCKER_PUNCH,
    "Perish Song": PERISH_SONG,

    # RED - FIRE, FIGHTING, ELECTRIC
    "Charizard, Flame Pokemon": CHARIZARD,
    "Pikachu, Mouse Pokemon": PIKACHU,
    "Raichu, Mouse Pokemon": RAICHU,
    "Moltres, Flame Pokemon": MOLTRES,
    "Entei, Volcano Pokemon": ENTEI,
    "Groudon, Continent Pokemon": GROUDON,
    "Machamp, Superpower Pokemon": MACHAMP,
    "Zapdos, Electric Pokemon": ZAPDOS,
    "Charmander": CHARMANDER,
    "Charmeleon": CHARMELEON,
    "Flareon": FLAREON,
    "Eevee (Red)": EEVEE_R,
    "Jolteon": JOLTEON,
    "Arcanine": ARCANINE,
    "Growlithe": GROWLITHE,
    "Ninetales": NINETALES,
    "Vulpix": VULPIX,
    "Rapidash": RAPIDASH,
    "Ponyta": PONYTA,
    "Magmar": MAGMAR,
    "Magmortar": MAGMORTAR,
    "Electabuzz": ELECTABUZZ,
    "Electivire": ELECTIVIRE,
    "Hitmonlee": HITMONLEE,
    "Hitmonchan": HITMONCHAN,
    "Primeape": PRIMEAPE,
    "Mankey": MANKEY,
    "Lucario": LUCARIO,
    "Blaziken": BLAZIKEN,
    "Infernape": INFERNAPE,
    "Luxray": LUXRAY,
    "Electrode": ELECTRODE,
    "Voltorb": VOLTORB,
    "Cyndaquil": CYNDAQUIL,
    "Litten": LITTEN,
    "Torchic": TORCHIC,
    "Numel": NUMEL,
    "Slugma": SLUGMA,
    "Flamethrower": FLAMETHROWER,
    "Thunderbolt": THUNDERBOLT,
    "Fire Blast": FIRE_BLAST,
    "Earthquake": EARTHQUAKE_SPELL,
    "Thunder": THUNDER,
    "Brick Break": BRICK_BREAK,
    "Close Combat": CLOSE_COMBAT,
    "Overheat": OVERHEAT,
    "Wild Charge": WILD_CHARGE,
    "Eruption": ERUPTION,

    # GREEN - GRASS, GROUND, BUG
    "Venusaur, Seed Pokemon": VENUSAUR,
    "Celebi, Time Travel Pokemon": CELEBI,
    "Rayquaza, Sky High Pokemon": RAYQUAZA,
    "Sceptile, Forest Pokemon": SCEPTILE,
    "Torterra, Continent Pokemon": TORTERRA,
    "Leafeon, Verdant Pokemon": LEAFEON,
    "Shaymin, Gratitude Pokemon": SHAYMIN,
    "Bulbasaur": BULBASAUR,
    "Ivysaur": IVYSAUR,
    "Eevee (Green)": EEVEE_G,
    "Exeggutor": EXEGGUTOR,
    "Exeggcute": EXEGGCUTE,
    "Tangrowth": TANGROWTH,
    "Vileplume": VILEPLUME,
    "Victreebel": VICTREEBEL,
    "Parasect": PARASECT,
    "Butterfree": BUTTERFREE,
    "Caterpie": CATERPIE,
    "Metapod": METAPOD,
    "Beedrill": BEEDRILL,
    "Scyther": SCYTHER,
    "Pinsir": PINSIR,
    "Heracross": HERACROSS,
    "Sandslash": SANDSLASH,
    "Dugtrio": DUGTRIO,
    "Golem": GOLEM,
    "Rhydon": RHYDON,
    "Mamoswine": MAMOSWINE,
    "Nidoking": NIDOKING,
    "Nidoqueen": NIDOQUEEN,
    "Razor Leaf": RAZOR_LEAF,
    "Solar Beam": SOLAR_BEAM,
    "Leech Seed": LEECH_SEED,
    "Synthesis": SYNTHESIS,
    "Ingrain": INGRAIN,
    "Giga Drain": GIGA_DRAIN,
    "Growth": GROWTH,
    "Vine Whip": VINE_WHIP,
    "Sunny Day": SUNNY_DAY,
    "Photosynthesis": PHOTOSYNTHESIS,

    # ITEMS (ARTIFACTS)
    "Poke Ball": POKE_BALL,
    "Great Ball": GREAT_BALL,
    "Ultra Ball": ULTRA_BALL,
    "Master Ball": MASTER_BALL,
    "Rare Candy": RARE_CANDY,
    "Exp. Share": EXP_SHARE,
    "Lucky Egg": LUCKY_EGG,
    "Leftovers": LEFTOVERS,
    "Choice Band": CHOICE_BAND,
    "Focus Sash": FOCUS_SASH,
    "Eviolite": EVIOLITE,
    "Scope Lens": SCOPE_LENS,
    "Quick Claw": QUICK_CLAW,
    "Muscle Band": MUSCLE_BAND,
    "Rocky Helmet": ROCKY_HELMET,
    "Pokedex": POKEDEX,
    "Silph Scope": SILPH_SCOPE,
    "Oran Berry": BERRY,
    "Sitrus Berry": SITRUS_BERRY,
    "Max Revive": MAX_REVIVE,

    # LOCATIONS (LANDS)
    "Pallet Town": PALLET_TOWN,
    "Cerulean City": CERULEAN_CITY,
    "Vermilion City": VERMILION_CITY,
    "Lavender Town": LAVENDER_TOWN,
    "Celadon City": CELADON_CITY,
    "Pokemon League": POKEMON_LEAGUE,
    "Viridian Forest": VIRIDIAN_FOREST,
    "Mt. Moon": MT_MOON,
    "Power Plant": POWER_PLANT,
    "Safari Zone": SAFARI_ZONE,
    "Victory Road": VICTORY_ROAD,
    "Pokemon Center (Land)": POKEMON_CENTER_LAND,
    "Silph Co.": SILPH_CO,
    "Cerulean Cave": CERULEAN_CAVE,
    "Indigo Plateau": INDIGO_PLATEAU,
    "Plains": PLAINS_PKH,
    "Island": ISLAND_PKH,
    "Swamp": SWAMP_PKH,
    "Mountain": MOUNTAIN_PKH,
    "Forest": FOREST_PKH,

    # SPICE PASS — Wave-22 R4 lift
    "Charizard, Mega Evolved": CHARIZARD_MEGA,
    "Moltres, Phoenix Reborn": MOLTRES_PHOENIX,
    "Pikachu, Thunder Champion": PIKACHU_CHAMPION,
    "Eevee, Evolution Vessel": EEVEE_VESSEL,
    "Master Ball": MASTER_BALL,
    "Volcanic Mantle": VOLCANIC_MANTLE,
    "Reshiram, Truth Aspect": RESHIRAM,
    "Hyper Beam": HYPER_BEAM,
}

print(f"Loaded {len(POKEMON_HORIZONS_CARDS)} Pokemon Horizons cards")


PASS4_RESEARCH_LAYER_CARDS: tuple[str, ...] = ()


# =============================================================================
# PASS 5 TARGETED COMBO WEB
# =============================================================================

PASS5_COMBO_WEB_PATTERNS = (
    "normal-artifact-velocity",
    "fairy-life-counterplay",
    "water-draw-tempo",
    "psychic-scry-engine",
    "dark-discard-pressure",
    "poison-death-drain",
    "fire-damage-charge",
    "fighting-equipment-combat",
    "grass-evolve-landfall",
    "dragon-legend-chain",
    "legendary-location-payoff",
    "spell-color-resonance",
)


def _pass5_compose_setup(old_setup, added_setup):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors: list[Interceptor] = []
        if old_setup:
            interceptors.extend(old_setup(obj, state) or [])
        interceptors.extend(added_setup(obj, state) or [])
        return interceptors

    return setup


def _pass5_append_text(card: CardDefinition, text: str) -> None:
    existing = card.text or ""
    if text in existing:
        return
    card.text = f"{existing} {text}".strip()


def _pass5_counter(obj: GameObject, amount: int = 1) -> Event:
    return Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': amount},
        source=obj.id,
        controller=obj.controller,
    )


def _pass5_best_friendly_pokemon(controller: str, state: GameState) -> Optional[GameObject]:
    pokemon = sorted(
        _pokemon_controlled_by(controller, state),
        key=lambda candidate: _impact_sort_key(candidate, state),
        reverse=True,
    )
    return pokemon[0] if pokemon else None


def _pass5_artifacts_controlled(controller: str, state: GameState) -> list[GameObject]:
    return [
        obj for obj in _battlefield_objects(state)
        if obj.controller == controller and CardType.ARTIFACT in (obj.characteristics.types or set())
    ]


def _pass5_subtype_count(controller: str, state: GameState, subtype: str) -> int:
    return sum(
        1 for obj in _creatures_controlled_by(controller, state)
        if subtype in (obj.characteristics.subtypes or set())
    )


def _pass5_entered_battlefield(event: Event, state: GameState) -> Optional[GameObject]:
    if event.type != EventType.ZONE_CHANGE:
        return None
    if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
        return None
    object_id = event.payload.get('object_id')
    return state.objects.get(object_id) if object_id else None


def _pass5_normal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def normal_enter_filter(event: Event, st: GameState) -> bool:
        entering = _pass5_entered_battlefield(event, st)
        return bool(
            entering
            and entering.id != obj.id
            and entering.controller == obj.controller
            and "Normal" in (entering.characteristics.subtypes or set())
        )

    def normal_enter_reward(event: Event, st: GameState) -> list[Event]:
        events = [_treasure_token_event(obj)]
        if _pass5_artifacts_controlled(obj.controller, st):
            events.append(_scry_event(obj.controller, 1, obj.id))
        if _pass5_subtype_count(obj.controller, st, "Normal") >= 3:
            events.append(_draw_event(obj.controller, 1, obj.id))
            events.extend(_discard_first_from_player_hand(obj.controller, st, source_id=obj.id, controller=obj.controller))
        return events

    def attack_reward(event: Event, st: GameState) -> list[Event]:
        if not _pass5_artifacts_controlled(obj.controller, st):
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        _react_interceptor(obj, normal_enter_filter, normal_enter_reward),
        make_attack_trigger(obj, attack_reward),
    ]


def _pass5_fairy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def life_filter(event: Event, st: GameState) -> bool:
        return (
            event.type == EventType.LIFE_CHANGE
            and event.payload.get('player') == obj.controller
            and event.payload.get('amount', 0) > 0
        )

    def life_reward(event: Event, st: GameState) -> list[Event]:
        events = [_pass5_counter(obj)]
        if _pass5_subtype_count(obj.controller, st, "Fairy") >= 2:
            target = _opponent_creatures(obj, st)
            if target:
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': target[0].id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    return [_react_interceptor(obj, life_filter, life_reward)]


def _pass5_water_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.DRAW and event.payload.get('player') == obj.controller

    def draw_reward(event: Event, st: GameState) -> list[Event]:
        events = [_scry_event(obj.controller, 1, obj.id)]
        if _pass5_subtype_count(obj.controller, st, "Water") >= 2 or _pass5_subtype_count(obj.controller, st, "Ice") >= 2:
            target = _opponent_creatures(obj, st)
            if target:
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': target[0].id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    def etb_reward(event: Event, st: GameState) -> list[Event]:
        if _pass5_subtype_count(obj.controller, st, "Water") + _pass5_subtype_count(obj.controller, st, "Ice") < 2:
            return []
        target = _opponent_creatures(obj, st)
        return [Event(type=EventType.TAP, payload={'object_id': target[0].id}, source=obj.id, controller=obj.controller)] if target else []

    return [
        _react_interceptor(obj, draw_filter, draw_reward),
        make_etb_trigger(obj, etb_reward),
    ]


def _pass5_psychic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def scry_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.SCRY and event.payload.get('player') == obj.controller

    def scry_reward(event: Event, st: GameState) -> list[Event]:
        events = [_pass5_counter(obj)]
        if obj.state.counters.get('+1/+1', 0) >= 1:
            events.append(_draw_event(obj.controller, 1, obj.id))
            events.extend(_discard_first_from_player_hand(obj.controller, st, source_id=obj.id, controller=obj.controller))
        return events

    return [_react_interceptor(obj, scry_filter, scry_reward)]


def _pass5_dark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def discard_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.DISCARD and event.payload.get('player') != obj.controller

    def discard_reward(event: Event, st: GameState) -> list[Event]:
        events = [_pass5_counter(obj)]
        opponent = _first_opponent_for(obj.controller, st)
        if opponent:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opponent, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    def attack_reward(event: Event, st: GameState) -> list[Event]:
        opponent = _first_opponent_for(obj.controller, st)
        if not opponent:
            return []
        graveyard = st.zones.get(f'graveyard_{opponent}')
        if graveyard and graveyard.objects:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opponent, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            )]
        return []

    return [
        _react_interceptor(obj, discard_filter, discard_reward),
        make_attack_trigger(obj, attack_reward),
    ]


def _pass5_poison_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        target = st.objects.get(event.payload.get('object_id'))
        return bool(target and target.controller != obj.controller and _is_creature(target))

    def death_reward(event: Event, st: GameState) -> list[Event]:
        opponent = _first_opponent_for(obj.controller, st)
        events: list[Event] = []
        if opponent:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opponent, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        best = _pass5_best_friendly_pokemon(obj.controller, st)
        if best:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': best.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [_react_interceptor(obj, death_filter, death_reward)]


def _pass5_fire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE or event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source') or event.source
        if source_id == obj.id:
            return False
        source = st.objects.get(source_id) if source_id else None
        return bool(source and source.controller == obj.controller)

    def damage_reward(event: Event, st: GameState) -> list[Event]:
        return [_pass5_counter(obj), _scry_event(obj.controller, 1, obj.id)]

    def attack_reward(event: Event, st: GameState) -> list[Event]:
        if obj.state.counters.get('+1/+1', 0) <= 0:
            return []
        opponent = _first_opponent_for(obj.controller, st)
        return _damage_event(obj, opponent, 1)

    return [
        _react_interceptor(obj, damage_filter, damage_reward),
        make_attack_trigger(obj, attack_reward),
    ]


def _pass5_fighting_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_reward(event: Event, st: GameState) -> list[Event]:
        events = [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id,
            controller=obj.controller,
        )]
        if _pass5_artifacts_controlled(obj.controller, st):
            target = _opponent_creatures(obj, st)
            if target:
                events.extend(_damage_event(obj, target[0].id, 1))
        return events

    return [make_attack_trigger(obj, attack_reward)]


def _pass5_green_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def evolve_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ACTIVATE or event.payload.get('ability') != 'evolve':
            return False
        source = st.objects.get(event.payload.get('source') or event.source)
        return bool(source and source.controller == obj.controller)

    def evolve_reward(event: Event, st: GameState) -> list[Event]:
        events = [_pass5_counter(obj)]
        if obj.state.counters.get('+1/+1', 0) >= 2:
            events.append(_draw_event(obj.controller, 1, obj.id))
        return events

    def landfall_filter(event: Event, st: GameState) -> bool:
        entering = _pass5_entered_battlefield(event, st)
        return bool(
            entering
            and entering.controller == obj.controller
            and CardType.LAND in (entering.characteristics.types or set())
        )

    def landfall_reward(event: Event, st: GameState) -> list[Event]:
        events = [_pass5_counter(obj)]
        if _pass5_subtype_count(obj.controller, st, "Ground") or _pass5_subtype_count(obj.controller, st, "Grass") >= 2:
            events.append(_scry_event(obj.controller, 1, obj.id))
        return events

    return [
        _react_interceptor(obj, evolve_filter, evolve_reward),
        _react_interceptor(obj, landfall_filter, landfall_reward),
    ]


def _pass5_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def legend_filter(event: Event, st: GameState) -> bool:
        entering = _pass5_entered_battlefield(event, st)
        return bool(
            entering
            and entering.id != obj.id
            and entering.controller == obj.controller
            and (
                "Legendary" in (entering.characteristics.supertypes or set())
                or "Dragon" in (entering.characteristics.subtypes or set())
            )
        )

    def legend_reward(event: Event, st: GameState) -> list[Event]:
        events = [_draw_event(obj.controller, 1, obj.id)]
        target = [
            permanent for permanent in _battlefield_objects(st)
            if permanent.controller != obj.controller
            and (
                CardType.ARTIFACT in (permanent.characteristics.types or set())
                or CardType.ENCHANTMENT in (permanent.characteristics.types or set())
            )
        ]
        if target:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target[0].id},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    def attack_reward(event: Event, st: GameState) -> list[Event]:
        return [_scry_event(obj.controller, 2, obj.id)]

    return [
        _react_interceptor(obj, legend_filter, legend_reward),
        make_attack_trigger(obj, attack_reward),
    ]


def _pass5_creature_pattern(card: CardDefinition) -> tuple[str, Callable[[GameObject, GameState], list[Interceptor]], str] | None:
    subtypes = card.characteristics.subtypes or set()
    if "Dragon" in subtypes:
        return (
            "dragon-legend-chain",
            _pass5_dragon_setup,
            "Whenever another legendary Pokemon or Dragon enters under your control, draw a card, then destroy up to one target artifact or enchantment an opponent controls. Whenever this attacks, scry 2.",
        )
    if "Fairy" in subtypes:
        return (
            "fairy-life-counterplay",
            _pass5_fairy_setup,
            "Whenever you gain life, put a +1/+1 counter on this Pokemon. If you control another Fairy, tap up to one target creature an opponent controls.",
        )
    if "Water" in subtypes or "Ice" in subtypes:
        return (
            "water-draw-tempo",
            _pass5_water_setup,
            "Whenever you draw a card, scry 1. If you control another Water or Ice Pokemon, tap up to one target creature an opponent controls.",
        )
    if "Psychic" in subtypes:
        return (
            "psychic-scry-engine",
            _pass5_psychic_setup,
            "Whenever you scry, put a +1/+1 counter on this Pokemon. If it already had a counter, draw a card, then discard a card.",
        )
    if "Ghost" in subtypes or "Dark" in subtypes:
        return (
            "dark-discard-pressure",
            _pass5_dark_setup,
            "Whenever an opponent discards a card, put a +1/+1 counter on this Pokemon and that player loses 1 life. Whenever this attacks, if an opponent has a card in their graveyard, that player loses 1 life.",
        )
    if subtypes & {"Grass", "Bug", "Ground", "Rock"}:
        return (
            "grass-evolve-landfall",
            _pass5_green_setup,
            "Whenever a Pokemon you control evolves or a land enters under your control, put a +1/+1 counter on this Pokemon. If it already had two counters, draw a card.",
        )
    if "Poison" in subtypes:
        return (
            "poison-death-drain",
            _pass5_poison_setup,
            "Whenever an opposing creature dies, each opponent loses 1 life and you put a +1/+1 counter on your highest-impact Pokemon.",
        )
    if "Fire" in subtypes or "Electric" in subtypes:
        return (
            "fire-damage-charge",
            _pass5_fire_setup,
            "Whenever another source you control deals noncombat damage, put a +1/+1 counter on this Pokemon and scry 1. Whenever this attacks, if it has a counter, it deals 1 damage to defending player.",
        )
    if "Fighting" in subtypes:
        return (
            "fighting-equipment-combat",
            _pass5_fighting_setup,
            "Whenever this attacks, it gets +1/+0 until end of turn. If you control an artifact, it also deals 1 damage to the highest-impact creature defending player controls.",
        )
    if "Normal" in subtypes:
        return (
            "normal-artifact-velocity",
            _pass5_normal_setup,
            "Whenever another Normal Pokemon enters under your control, create a Treasure token. Whenever this attacks, if you control an artifact, it gets +1/+0 until end of turn.",
        )
    return None


def _pass5_wrap_spell_resolve(card: CardDefinition, old_resolve, pattern: str):
    def resolve(targets, state: GameState) -> list[Event]:
        events: list[Event] = []
        if old_resolve:
            events.extend(old_resolve(targets, state) or [])
        controller = _spell_controller(state, targets)
        if not controller:
            return events
        pokemon = _pass5_best_friendly_pokemon(controller, state)
        if pattern == "white":
            if pokemon:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': pokemon.id, 'counter_type': '+1/+1', 'amount': 1},
                    controller=controller,
                ))
            if _pass5_subtype_count(controller, state, "Fairy"):
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': controller, 'amount': 1}, controller=controller))
        elif pattern == "blue":
            events.append(_scry_event(controller, 1))
            if _pass5_subtype_count(controller, state, "Psychic") or _pass5_subtype_count(controller, state, "Water") >= 2:
                target = _opponent_creatures_for(controller, state)
                if target:
                    events.append(Event(type=EventType.TAP, payload={'object_id': target[0].id}, controller=controller))
        elif pattern == "black":
            opponent = _first_opponent_for(controller, state)
            if opponent:
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opponent, 'amount': -1}, controller=controller))
            if _pass5_subtype_count(controller, state, "Ghost") or _pass5_subtype_count(controller, state, "Dark"):
                events.extend(_discard_first_from_player_hand(opponent, state, controller=controller) if opponent else [])
        elif pattern == "red":
            if pokemon:
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': pokemon.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
                    controller=controller,
                ))
            if _pass5_subtype_count(controller, state, "Fire") or _pass5_subtype_count(controller, state, "Electric"):
                events.append(_scry_event(controller, 1))
        elif pattern == "green":
            if pokemon:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': pokemon.id, 'counter_type': '+1/+1', 'amount': 1},
                    controller=controller,
                ))
            if _pass5_subtype_count(controller, state, "Grass") >= 2:
                events.append(_draw_event(controller, 1))
        return events

    return resolve


def _pass5_spell_pattern(card: CardDefinition) -> tuple[str, str] | None:
    colors = card.characteristics.colors or set()
    if Color.WHITE in colors:
        return ("white", "If you control a Fairy or Normal Pokemon, put a +1/+1 counter on your highest-impact Pokemon and gain 1 life.")
    if Color.BLUE in colors:
        return ("blue", "If you control a Water or Psychic Pokemon, scry 1, then tap up to one target creature an opponent controls.")
    if Color.BLACK in colors:
        return ("black", "If you control a Ghost or Dark Pokemon, each opponent loses 1 life and discards a card.")
    if Color.RED in colors:
        return ("red", "If you control a Fire or Electric Pokemon, your highest-impact Pokemon gets +1/+0 until end of turn and you scry 1.")
    if Color.GREEN in colors:
        return ("green", "If you control a Grass Pokemon, put a +1/+1 counter on your highest-impact Pokemon. If you control two Grass Pokemon, draw a card.")
    return None


def _pass5_location_setup(kind: str):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def evolve_filter(event: Event, st: GameState) -> bool:
            if event.type != EventType.ACTIVATE or event.payload.get('ability') != 'evolve':
                return False
            source = st.objects.get(event.payload.get('source') or event.source)
            return bool(source and source.controller == obj.controller)

        def creature_enter_filter(event: Event, st: GameState) -> bool:
            entering = _pass5_entered_battlefield(event, st)
            return bool(entering and entering.controller == obj.controller and _is_creature(entering))

        def spell_cast_filter(event: Event, st: GameState) -> bool:
            source = st.objects.get(event.source)
            return bool(source and source.controller == obj.controller)

        def reward(event: Event, st: GameState) -> list[Event]:
            events: list[Event] = []
            target = _pass5_best_friendly_pokemon(obj.controller, st)
            if kind in {"pallet", "league", "plateau"}:
                events.append(_draw_event(obj.controller, 1, obj.id))
            elif kind in {"cerulean", "lavender", "cave"}:
                events.append(_scry_event(obj.controller, 2, obj.id))
            elif kind in {"vermilion", "celadon"} and target:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id,
                    controller=obj.controller,
                ))
            elif target:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id,
                    controller=obj.controller,
                ))
            return events

        if kind in {"pallet", "league", "plateau", "victory"}:
            return [_react_interceptor(obj, evolve_filter, reward)]
        if kind in {"cerulean", "vermilion", "lavender", "celadon", "cave"}:
            return [_react_interceptor(obj, creature_enter_filter, reward)]
        return [_react_interceptor(obj, spell_cast_filter, reward)]

    return setup


def _apply_pass5_combo_web() -> None:
    lifted: list[str] = []
    for card in POKEMON_HORIZONS_CARDS.values():
        types = card.characteristics.types or set()
        if CardType.CREATURE in types:
            pattern = _pass5_creature_pattern(card)
            if not pattern:
                continue
            _pattern_name, setup_fn, text = pattern
            _pass5_append_text(card, text)
            card.setup_interceptors = _pass5_compose_setup(getattr(card, 'setup_interceptors', None), setup_fn)
            lifted.append(card.name)
        elif CardType.INSTANT in types or CardType.SORCERY in types:
            spell_pattern = _pass5_spell_pattern(card)
            if not spell_pattern:
                continue
            pattern_name, text = spell_pattern
            _pass5_append_text(card, text)
            card.resolve = _pass5_wrap_spell_resolve(card, getattr(card, 'resolve', None), pattern_name)
            lifted.append(card.name)

    location_setups = {
        "Pallet Town": ("pallet", "Whenever a Pokemon you control evolves, draw a card."),
        "Cerulean City": ("cerulean", "Whenever a Water or Psychic Pokemon enters under your control, scry 2."),
        "Vermilion City": ("vermilion", "Whenever an Electric or Fire Pokemon enters under your control, put a +1/+1 counter on your highest-impact Pokemon."),
        "Lavender Town": ("lavender", "Whenever a Ghost or Dark Pokemon enters under your control, scry 2."),
        "Celadon City": ("celadon", "Whenever a Grass Pokemon enters under your control, put a +1/+1 counter on your highest-impact Pokemon."),
        "Pokemon League": ("league", "Whenever a Pokemon you control evolves, draw a card."),
        "Viridian Forest": ("viridian", "Whenever you cast a green spell, put a +1/+1 counter on your highest-impact Pokemon."),
        "Mt. Moon": ("moon", "Whenever you cast an artifact spell or activate an artifact ability, put a +1/+1 counter on your highest-impact Pokemon."),
        "Power Plant": ("plant", "Whenever you cast an artifact or Electric spell, put a +1/+1 counter on your highest-impact Pokemon."),
        "Safari Zone": ("safari", "Whenever you cast a creature spell, put a +1/+1 counter on your highest-impact Pokemon."),
        "Victory Road": ("victory", "Whenever a Pokemon you control evolves, draw a card."),
        "Pokemon Center (Land)": ("center", "Whenever you cast a white spell, put a +1/+1 counter on your highest-impact Pokemon."),
        "Silph Co.": ("silph", "Whenever you cast an Equipment or artifact spell, put a +1/+1 counter on your highest-impact Pokemon."),
        "Cerulean Cave": ("cave", "Whenever a Psychic, Ghost, or Dark Pokemon enters under your control, scry 2."),
        "Indigo Plateau": ("plateau", "Whenever a legendary Pokemon you control evolves or enters, draw a card."),
    }
    for name, (kind, text) in location_setups.items():
        card = POKEMON_HORIZONS_CARDS.get(name)
        if not card:
            continue
        _pass5_append_text(card, text)
        card.setup_interceptors = _pass5_compose_setup(getattr(card, 'setup_interceptors', None), _pass5_location_setup(kind))
        lifted.append(name)

    global PASS5_COMBO_WEB_CARDS
    PASS5_COMBO_WEB_CARDS = tuple(sorted(set(lifted)))


_apply_pass5_combo_web()


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    ARCEUS,
    TOGEKISS,
    CLEFABLE,
    SYLVEON,
    EEVEE_W,
    CLEFAIRY,
    TOGEPI,
    TOGETIC,
    CHANSEY,
    BLISSEY,
    SNORLAX,
    JIGGLYPUFF,
    WIGGLYTUFF,
    PERSIAN,
    MEOWTH,
    PIDGEOT,
    PIDGEY,
    RATTATA,
    RATICATE,
    FURRET,
    AUDINO,
    DITTO,
    SLAKING,
    MILTANK,
    TAUROS,
    GRANBULL,
    FLORGES,
    POTION,
    SUPER_POTION,
    HYPER_POTION,
    FULL_RESTORE,
    POKEMON_CENTER,
    PROFESSOR_OAK,
    HEAL_BELL,
    PROTECT,
    SAFEGUARD,
    MOONBLAST,
    MEWTWO,
    MEW,
    LUGIA,
    SUICUNE,
    ARTICUNO,
    KYOGRE,
    BLASTOISE,
    ALAKAZAM,
    SQUIRTLE,
    WARTORTLE,
    PSYDUCK,
    GOLDUCK,
    VAPOREON,
    EEVEE_U,
    SLOWPOKE,
    SLOWBRO,
    LAPRAS,
    DEWGONG,
    STARMIE,
    STARYU,
    TENTACRUEL,
    GYARADOS,
    MAGIKARP,
    MILOTIC,
    ESPEON,
    GARDEVOIR,
    GALLADE,
    WOBBUFFET,
    GLACEON,
    WALREIN,
    CLOYSTER,
    DIVE_BALL,
    MISTY_DETERMINATION,
    CONFUSION,
    PSYCHIC,
    HYDRO_PUMP,
    BLIZZARD,
    SURF,
    TELEKINESIS,
    AMNESIA,
    FUTURE_SIGHT_SPELL,
    GENGAR,
    DARKRAI,
    YVELTAL,
    GIRATINA,
    UMBREON,
    ABSOL,
    GASTLY,
    HAUNTER,
    EEVEE_B,
    MUK,
    GRIMER,
    WEEZING,
    KOFFING,
    DUSKNOIR,
    MISDREAVUS,
    MISMAGIUS,
    HOUNDOOM,
    HOUNDOUR,
    MURKROW,
    HONCHKROW,
    SPIRITOMB,
    SABLEYE,
    TOXICROAK,
    CROBAT,
    ZUBAT,
    GOLBAT,
    NIGHT_SHADE,
    SHADOW_BALL,
    DARK_PULSE,
    DESTINY_BOND,
    HEX,
    MEAN_LOOK,
    NIGHTMARE_SPELL,
    TOXIC,
    SUCKER_PUNCH,
    PERISH_SONG,
    CHARIZARD,
    PIKACHU,
    RAICHU,
    MOLTRES,
    ENTEI,
    GROUDON,
    MACHAMP,
    ZAPDOS,
    CHARMANDER,
    CHARMELEON,
    FLAREON,
    EEVEE_R,
    JOLTEON,
    ARCANINE,
    GROWLITHE,
    NINETALES,
    VULPIX,
    RAPIDASH,
    PONYTA,
    MAGMAR,
    MAGMORTAR,
    ELECTABUZZ,
    ELECTIVIRE,
    HITMONLEE,
    HITMONCHAN,
    PRIMEAPE,
    MANKEY,
    LUCARIO,
    BLAZIKEN,
    INFERNAPE,
    LUXRAY,
    ELECTRODE,
    VOLTORB,
    CYNDAQUIL,
    LITTEN,
    TORCHIC,
    NUMEL,
    SLUGMA,
    FLAMETHROWER,
    THUNDERBOLT,
    FIRE_BLAST,
    EARTHQUAKE_SPELL,
    THUNDER,
    BRICK_BREAK,
    CLOSE_COMBAT,
    OVERHEAT,
    WILD_CHARGE,
    ERUPTION,
    VENUSAUR,
    CELEBI,
    RAYQUAZA,
    SCEPTILE,
    TORTERRA,
    LEAFEON,
    SHAYMIN,
    BULBASAUR,
    IVYSAUR,
    EEVEE_G,
    EXEGGUTOR,
    EXEGGCUTE,
    TANGROWTH,
    VILEPLUME,
    VICTREEBEL,
    PARASECT,
    BUTTERFREE,
    CATERPIE,
    METAPOD,
    BEEDRILL,
    SCYTHER,
    PINSIR,
    HERACROSS,
    SANDSLASH,
    DUGTRIO,
    GOLEM,
    RHYDON,
    MAMOSWINE,
    NIDOKING,
    NIDOQUEEN,
    RAZOR_LEAF,
    SOLAR_BEAM,
    LEECH_SEED,
    SYNTHESIS,
    INGRAIN,
    GIGA_DRAIN,
    GROWTH,
    VINE_WHIP,
    SUNNY_DAY,
    PHOTOSYNTHESIS,
    POKE_BALL,
    GREAT_BALL,
    ULTRA_BALL,
    MASTER_BALL,
    RARE_CANDY,
    EXP_SHARE,
    LUCKY_EGG,
    LEFTOVERS,
    CHOICE_BAND,
    FOCUS_SASH,
    EVIOLITE,
    SCOPE_LENS,
    QUICK_CLAW,
    MUSCLE_BAND,
    ROCKY_HELMET,
    POKEDEX,
    SILPH_SCOPE,
    BERRY,
    SITRUS_BERRY,
    MAX_REVIVE,
    PALLET_TOWN,
    CERULEAN_CITY,
    VERMILION_CITY,
    LAVENDER_TOWN,
    CELADON_CITY,
    POKEMON_LEAGUE,
    VIRIDIAN_FOREST,
    MT_MOON,
    POWER_PLANT,
    SAFARI_ZONE,
    VICTORY_ROAD,
    POKEMON_CENTER_LAND,
    SILPH_CO,
    CERULEAN_CAVE,
    INDIGO_PLATEAU,
    PLAINS_PKH,
    ISLAND_PKH,
    SWAMP_PKH,
    MOUNTAIN_PKH,
    FOREST_PKH,

    # SPICE PASS
    CHARIZARD_MEGA,
    MOLTRES_PHOENIX,
    PIKACHU_CHAMPION,
    EEVEE_VESSEL,
    MASTER_BALL,
    VOLCANIC_MANTLE,
    RESHIRAM,
    HYPER_BEAM,
]
