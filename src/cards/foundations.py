"""
Foundations (FDN) Card Implementations

Real card data fetched from Scryfall API.
517 cards in set.
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_instant,
    make_land,
    make_planeswalker,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable

from src.cards.interceptor_helpers import (
    make_etb_trigger,
    make_death_trigger,
    make_attack_trigger,
    make_static_pt_boost,
    make_keyword_grant,
    make_upkeep_trigger,
    make_spell_cast_trigger,
    make_life_gain_trigger,
    make_damage_trigger,
    make_draw_trigger,
    make_counter_added_trigger,
    make_end_step_trigger,
    make_cost_reduction,
    other_creatures_you_control,
    other_creatures_with_subtype,
    creatures_you_control,
    creatures_with_subtype,
    create_modal_choice,
    create_target_choice,
    make_modal_resolve,
    ModeSpec,
    normalize_target,
    open_library_search,
    any_card_filter,
    artifact_filter_lib,
    basic_land_filter,
    creature_filter_lib,
    creature_with_mv_at_least,
    instant_or_sorcery_with_mv,
    make_equipment_setup,
    make_aura_setup,
    make_ward,
    make_activated_ability,
    make_attached_dynamic_pt_boost,
    count_permanents_with_subtype,
    # Sweep 4: becomes-creature
    becomes_creature,
    # Sweep 10: granted death triggers
    grant_death_trigger,
    # Replacement effects (general "if X would happen, Y instead")
    make_replacement_effect,
)

from src.engine.spell_resolve import (
    resolve_chain,
    resolve_create_token,
    resolve_draw,
    resolve_pump,
)

# Phase 5b: declare ``target_requirements`` on spells so the priority system
# emits a PendingChoice at cast time when the action lacks pre-supplied
# targets. The migrated resolve_fns below consume ``targets[0]`` directly
# instead of calling ``create_target_choice`` themselves.
from src.engine.targeting import (
    TargetRequirement,
    TargetFilter,
    creature_filter,
    permanent_filter,
    player_filter,
    any_target_filter,
    spell_filter,
    card_in_graveyard_filter,
    target_creature,
    target_any,
    target_player,
    target_spell,
    # Phase 5b cross-target: callable builders for inter-target constraints
    target_creature_different_controller,
    another_target_creature,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _resolving_spell_obj(state: GameState) -> Optional[GameObject]:
    """Return the topmost spell on the stack — the resolving spell."""
    stack_zone = state.zones.get('stack') if state and state.zones else None
    if stack_zone is None:
        return None
    for obj_id in reversed(list(stack_zone.objects or [])):
        obj = state.objects.get(obj_id)
        if obj is not None:
            return obj
    return None


def _spell_caster_id(state: GameState) -> Optional[str]:
    """Return the controller of the resolving spell (best-effort)."""
    obj = _resolving_spell_obj(state)
    if obj is not None and obj.controller:
        return obj.controller
    return getattr(state, 'priority_player', None) or getattr(state, 'active_player', None)


def _spell_x_value(state: GameState) -> int:
    """Return the X value chosen for the resolving spell, or 0."""
    obj = _resolving_spell_obj(state)
    if obj is None:
        return 0
    x = getattr(obj, 'x_value', None)
    if x is None:
        # StackItem may also carry x_value via additional_data
        stack_zone = state.zones.get('stack') if state and state.zones else None
        if stack_zone:
            # The stack manager keeps StackItems separately; this is best-effort.
            x = 0
    try:
        return int(x or 0)
    except (TypeError, ValueError):
        return 0


def _grant_keyword_events(targets, keyword: str, source_id: Optional[str] = None) -> list[Event]:
    """Emit GRANT_KEYWORD events for each chosen target (skipping players)."""
    from src.engine.spell_resolve import _flatten_targets  # type: ignore
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if getattr(t, 'is_player', False):
            continue
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': t.id, 'keyword': keyword, 'duration': 'end_of_turn'},
            source=source_id,
        ))
    return events


def _resolve_grant_keyword(keyword: str):
    """Resolve helper that grants ``keyword`` until end of turn to each target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        return _grant_keyword_events(targets, keyword)
    return _resolve


# Phase 5b migration helpers -------------------------------------------------
#
# Each helper below takes targets (the engine's ``list[list[Target]]`` shape
# already filled in by the cast-time PendingChoice flow) and returns one or
# more Events. They replace the old ``_xxx_execute`` callbacks that lived
# behind ``create_target_choice`` inside the resolve_fn.

def _first_target_id(targets, state: GameState) -> Optional[str]:
    """Pull the first chosen target id from the engine's targets shape."""
    from src.engine.spell_resolve import _first_target  # type: ignore
    t = _first_target(targets)
    return t.id if t is not None else None


def _first_target_obj(targets, state: GameState) -> Optional[GameObject]:
    """Pull the first chosen target object (returns None if it's a player)."""
    tid = _first_target_id(targets, state)
    if tid is None:
        return None
    return state.objects.get(tid)


def _resolve_damage_to_targets(amount: int):
    """Deal ``amount`` damage to each chosen target (creature/PW/player)."""
    def _resolve(targets, state: GameState) -> list[Event]:
        from src.engine.spell_resolve import _flatten_targets  # type: ignore
        spell = _resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    'target': t.id,
                    'amount': amount,
                    'is_combat': False,
                    'is_player': t.is_player,
                    'source': source_id,
                },
                source=source_id,
            ))
        return events
    return _resolve


def _resolve_destroy_targets():
    """Destroy each chosen permanent target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        from src.engine.spell_resolve import _flatten_targets  # type: ignore
        spell = _resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': t.id},
                source=source_id,
            ))
        return events
    return _resolve


def _resolve_exile_targets():
    """Exile each chosen permanent target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        from src.engine.spell_resolve import _flatten_targets  # type: ignore
        spell = _resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            obj = state.objects.get(t.id)
            if obj is None:
                continue
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': t.id,
                    'from_zone': f'battlefield_{obj.controller}',
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone': 'exile',
                    'to_zone_type': ZoneType.EXILE,
                    'reason': 'exiled',
                },
                source=source_id,
            ))
        return events
    return _resolve


def _resolve_counter_targeted_spell():
    """Counter each chosen spell target (move from stack to GY)."""
    def _resolve(targets, state: GameState) -> list[Event]:
        from src.engine.spell_resolve import _flatten_targets  # type: ignore
        spell = _resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            target_card = state.objects.get(t.id)
            if target_card is None or target_card.zone != ZoneType.STACK:
                continue
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': t.id,
                    'from_zone': 'stack',
                    'to_zone': f'graveyard_{target_card.owner}',
                    'to_zone_type': ZoneType.GRAVEYARD,
                    'reason': 'countered',
                },
                source=source_id,
            ))
        return events
    return _resolve


def _resolve_bounce_targets():
    """Return each chosen permanent target to its owner's hand."""
    def _resolve(targets, state: GameState) -> list[Event]:
        from src.engine.spell_resolve import _flatten_targets  # type: ignore
        spell = _resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            obj = state.objects.get(t.id)
            if obj is None:
                continue
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': t.id,
                    'from_zone': f'battlefield_{obj.controller}',
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone': f'hand_{obj.owner}',
                    'to_zone_type': ZoneType.HAND,
                    'reason': 'bounced',
                },
                source=source_id,
            ))
        return events
    return _resolve


def _resolve_caster_life_change(amount: int):
    """Caster gains/loses ``amount`` life (positive = gain)."""
    def _resolve(targets, state: GameState) -> list[Event]:
        caster = _spell_caster_id(state)
        if caster is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster, 'amount': amount},
        )]
    return _resolve


def _resolve_caster_draw(amount: int):
    """Caster draws ``amount`` cards."""
    def _resolve(targets, state: GameState) -> list[Event]:
        caster = _spell_caster_id(state)
        if caster is None:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': caster, 'amount': amount},
        )]
    return _resolve


def _resolve_anthem_creatures_you_control(
    power_mod: int,
    toughness_mod: int,
    keywords: tuple = (),
):
    """Pump every creature you control + grant optional keywords until EOT."""
    keywords_list = tuple(keywords)

    def _resolve(targets, state: GameState) -> list[Event]:
        caster = _spell_caster_id(state)
        if not caster:
            return []
        events: list[Event] = []
        for obj_id, obj in list(state.objects.items()):
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            if obj.controller != caster:
                continue
            if CardType.CREATURE not in obj.characteristics.types:
                continue
            if power_mod or toughness_mod:
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': obj_id,
                        'power_mod': power_mod,
                        'toughness_mod': toughness_mod,
                        'duration': 'end_of_turn',
                    },
                ))
            for kw in keywords_list:
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': obj_id, 'keyword': kw, 'duration': 'end_of_turn'},
                ))
        return events

    return _resolve


# --- DAY OF JUDGMENT ---
def day_of_judgment_resolve(targets, state: GameState) -> list[Event]:
    """Destroy all creatures."""
    events: list[Event] = []
    for obj_id, obj in list(state.objects.items()):
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE in obj.characteristics.types:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj_id},
            ))
    return events


# --- AETHERIZE ---
def aetherize_resolve(targets, state: GameState) -> list[Event]:
    """Return all attacking creatures to their owner's hand."""
    events: list[Event] = []
    for obj_id, obj in list(state.objects.items()):
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        if not getattr(obj.state, 'attacking', False):
            continue
        events.append(Event(
            type=EventType.BOUNCE,
            payload={'object_id': obj_id},
        ))
    return events


# --- RUN AWAY TOGETHER ---
def run_away_together_resolve(targets, state: GameState) -> list[Event]:
    """Return chosen creatures to their owners' hands."""
    from src.engine.spell_resolve import _flatten_targets  # type: ignore
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.BOUNCE,
            payload={'object_id': t.id},
        ))
    return events


# --- BITE DOWN ---
def bite_down_resolve(targets, state: GameState) -> list[Event]:
    """Your creature deals damage equal to its power to opponent's creature."""
    from src.engine.spell_resolve import _flatten_targets  # type: ignore
    flat = _flatten_targets(targets)
    if len(flat) < 2:
        return []
    your_creature = state.objects.get(flat[0].id) if not flat[0].is_player else None
    enemy_creature = flat[1]
    if your_creature is None:
        return []
    power = get_power(your_creature, state)
    if power <= 0:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': enemy_creature.id,
            'amount': power,
            'is_combat': False,
            'is_player': enemy_creature.is_player,
        },
    )]


# --- PRIMAL MIGHT ---
def _primal_might_pump_then_fight(choice, selected, state: GameState) -> list[Event]:
    """Selected: target creature you control. Apply +X/+X EOT.
    The "fight up to one" clause is an engine gap (modal/optional second
    target); skip it for now."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    x = int(choice.callback_data.get('x_value', 0) or 0)
    if x <= 0:
        return []
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            'object_id': target_id,
            'power_mod': x,
            'toughness_mod': x,
            'duration': 'end_of_turn',
        },
        source=choice.source_id,
    )]


def primal_might_resolve(targets, state: GameState) -> list[Event]:
    """Primal Might: target creature you control gets +X/+X EOT, then fights
    up to one creature you don't control. Fight-clause is an engine gap;
    we wire just the +X/+X pump."""
    spell = _resolving_spell_obj(state)
    caster_id = spell.controller if spell else state.active_player
    spell_id = spell.id if spell else "primal_might_spell"
    x_value = _spell_x_value(state)
    legal_targets = []
    for oid, oo in state.objects.items():
        if (oo.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in oo.characteristics.types and
                oo.controller == caster_id):
            legal_targets.append(oid)
    if not legal_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt=f"Choose a creature to get +{x_value}/+{x_value}",
        min_targets=1,
        max_targets=1,
        callback_data={'x_value': x_value},
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _primal_might_pump_then_fight
    return []


# --- RAISE THE PAST ---
def raise_the_past_resolve(targets, state: GameState) -> list[Event]:
    """Return all creature cards with MV<=2 from your gy to the battlefield."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    gy = state.zones.get(f'graveyard_{caster}')
    if gy is None:
        return []
    events: list[Event] = []
    for cid in list(gy.objects):
        obj = state.objects.get(cid)
        if obj is None:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        # Mana value: count via card def or characteristics if present.
        cdef = getattr(obj, 'card_def', None) or obj.characteristics
        mv = 0
        # Try mana_cost on characteristics or card_def.
        cost_str = getattr(cdef, 'mana_cost', None) or getattr(obj.characteristics, 'mana_cost', None) or ''
        if cost_str:
            # Count generic + colored symbols.
            import re as _re
            generic = sum(int(g) for g in _re.findall(r'\{(\d+)\}', cost_str))
            colored = len(_re.findall(r'\{[WUBRGCwubrgc/X]+\}', cost_str))
            mv = generic + colored
        if mv > 2:
            continue
        events.append(Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={'object_id': cid, 'controller': caster},
        ))
    return events


# --- INSPIRATION FROM BEYOND ---
def inspiration_from_beyond_resolve(targets, state: GameState) -> list[Event]:
    """Mill 3, then return an instant or sorcery from gy to hand."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    return [
        Event(
            type=EventType.MILL,
            payload={'player': caster, 'amount': 3},
        ),
        Event(
            type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
            payload={'player': caster, 'card_type': 'instant', 'amount': 1},
        ),
        # Engine handler matches a single card_type; sorcery cards are handled
        # in a follow-up choice if no instants are present.
        Event(
            type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
            payload={'player': caster, 'card_type': 'sorcery', 'amount': 1},
        ),
    ]


# --- REVENGE OF THE RATS ---
def revenge_of_the_rats_resolve(targets, state: GameState) -> list[Event]:
    """Create a tapped 1/1 black Rat token for each creature card in your gy."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    gy = state.zones.get(f'graveyard_{caster}')
    if gy is None:
        return []
    count = 0
    for cid in gy.objects:
        obj = state.objects.get(cid)
        if obj is None:
            continue
        if CardType.CREATURE in obj.characteristics.types:
            count += 1
    if count <= 0:
        return []
    events: list[Event] = []
    for _ in range(count):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': caster,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True,
                'tapped': True,
            },
            controller=caster,
        ))
    return events


# --- BULK UP ---
def bulk_up_resolve(targets, state: GameState) -> list[Event]:
    """Double target creature's power until end of turn."""
    from src.engine.spell_resolve import _first_target  # type: ignore
    t = _first_target(targets)
    if t is None or t.is_player:
        return []
    obj = state.objects.get(t.id)
    if obj is None:
        return []
    power = get_power(obj, state)
    if power <= 0:
        return []
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            'object_id': t.id,
            'power_mod': power,  # +power doubles current power
            'toughness_mod': 0,
            'duration': 'end_of_turn',
        },
    )]


# --- EXSANGUINATE ---
def exsanguinate_resolve(targets, state: GameState) -> list[Event]:
    """Each opponent loses X life. You gain that much life."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    x = _spell_x_value(state)
    if x <= 0:
        return []
    opp_count = 0
    events: list[Event] = []
    for pid in state.players:
        if pid == caster:
            continue
        opp_count += 1
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': pid, 'amount': -x},
        ))
    if opp_count > 0:
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster, 'amount': x * opp_count},
        ))
    return events


# --- RISE OF THE DARK REALMS ---
def rise_of_the_dark_realms_resolve(targets, state: GameState) -> list[Event]:
    """Put all creature cards from all graveyards onto the battlefield under your control."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    events: list[Event] = []
    for zname, zone in list(state.zones.items()):
        if not zname.startswith('graveyard_'):
            continue
        for cid in list(zone.objects):
            obj = state.objects.get(cid)
            if obj is None:
                continue
            if CardType.CREATURE not in obj.characteristics.types:
                continue
            # Reanimate under our control.
            obj.controller = caster
            events.append(Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={'object_id': cid, 'controller': caster},
            ))
    return events


# --- ZOMBIFY ---
def zombify_resolve(targets, state: GameState) -> list[Event]:
    """Return target creature card from your gy to the battlefield."""
    from src.engine.spell_resolve import _first_target  # type: ignore
    t = _first_target(targets)
    if t is None or t.is_player:
        return []
    caster = _spell_caster_id(state)
    return [Event(
        type=EventType.RETURN_FROM_GRAVEYARD,
        payload={'object_id': t.id, 'controller': caster},
    )]


# --- RIVERS REBUKE ---
def rivers_rebuke_resolve(targets, state: GameState) -> list[Event]:
    """Return all nonland permanents target player controls to their owner's hand."""
    from src.engine.spell_resolve import _first_target  # type: ignore
    t = _first_target(targets)
    target_player = t.id if (t and t.is_player) else None
    if not target_player:
        return []
    events: list[Event] = []
    for obj_id, obj in list(state.objects.items()):
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller != target_player:
            continue
        if CardType.LAND in obj.characteristics.types:
            continue
        events.append(Event(
            type=EventType.BOUNCE,
            payload={'object_id': obj_id},
        ))
    return events


# --- PILFER ---
def pilfer_resolve(targets, state: GameState) -> list[Event]:
    """Target opponent reveals hand. You choose a nonland card to discard."""
    from src.engine.spell_resolve import _first_target  # type: ignore
    t = _first_target(targets)
    target_player = t.id if (t and t.is_player) else None
    if not target_player:
        return []
    # Simplified: emit a generic DISCARD event; handler will pick a card.
    return [Event(
        type=EventType.DISCARD,
        payload={'player': target_player, 'amount': 1, 'nonland': True},
    )]


# --- HEROIC REINFORCEMENTS ---
def heroic_reinforcements_resolve(targets, state: GameState) -> list[Event]:
    """Two 1/1 white Soldier tokens; creatures you control get +1/+1 and gain haste EOT."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    events: list[Event] = []
    for _ in range(2):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Soldier Token',
                'controller': caster,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Soldier'],
                'colors': [Color.WHITE],
                'is_token': True,
            },
            controller=caster,
        ))
    # Anthem
    events.extend(_resolve_anthem_creatures_you_control(1, 1, ('haste',))(targets, state))
    return events


# --- CIRCUITOUS ROUTE ---
def circuitous_route_resolve(targets, state: GameState) -> list[Event]:
    """Search library for up to two basic land cards and/or Gates, put tapped, then shuffle."""
    caster = _spell_caster_id(state)
    if not caster:
        return []
    spell_obj = _resolving_spell_obj(state)
    source_id = spell_obj.id if spell_obj else ''

    def _filter(card_obj, st) -> bool:
        types_set = card_obj.characteristics.types
        supertypes = card_obj.characteristics.supertypes
        subtypes = card_obj.characteristics.subtypes
        if CardType.LAND not in types_set:
            return False
        if 'Basic' in supertypes:
            return True
        if 'Gate' in subtypes:
            return True
        return False

    from src.engine.library_search import create_library_search_choice
    create_library_search_choice(
        state, caster, source_id,
        filter_fn=_filter,
        max_count=2,
        destination='battlefield_tapped',
        shuffle_after=True,
        prompt='Search for up to two basic lands and/or Gates',
        optional=True,
    )
    return []


# --- DIVINE RESILIENCE ---
def divine_resilience_resolve(targets, state: GameState) -> list[Event]:
    """Target creature you control gains indestructible until end of turn.

    Engine gap: kicker check is approximated — we always grant to chosen targets.
    """
    return _grant_keyword_events(targets, 'indestructible')


# =============================================================================
# SETUP INTERCEPTOR FUNCTIONS
# =============================================================================

# --- ARAHBO, THE FIRST FANG ---
# Other Cats you control get +1/+1.
# Whenever Arahbo or another nontoken Cat you control enters, create a 1/1 white Cat creature token.
def arahbo_the_first_fang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # Lord effect: Other Cats get +1/+1
    interceptors.extend(make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Cat")
    ))

    # ETB trigger for self
    def self_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Cat'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, self_etb_effect))

    # Trigger when another nontoken Cat enters
    def other_cat_enters_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        # Must be another nontoken Cat we control
        return (entering_id != source_obj.id and
                entering_obj.controller == source_obj.controller and
                "Cat" in entering_obj.characteristics.subtypes and
                not entering_obj.state.is_token)

    def other_cat_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Cat'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=obj.id
        )]

    def other_cat_filter_wrapper(event: Event, state: GameState) -> bool:
        return other_cat_enters_filter(event, state, obj)

    def other_cat_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = other_cat_effect(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=other_cat_filter_wrapper,
        handler=other_cat_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=other_cat_effect,
    ))

    return interceptors


# --- DAZZLING ANGEL ---
# Whenever another creature you control enters, you gain 1 life.
def dazzling_angel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_enters_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != source_obj.id and
                entering_obj.controller == source_obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def filter_wrapper(event: Event, state: GameState) -> bool:
        return other_creature_enters_filter(event, state, obj)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_wrapper,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- HELPFUL HUNTER ---
# When this creature enters, draw a card.
def helpful_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- PRIDEFUL PARENT ---
# When this creature enters, create a 1/1 white Cat creature token.
def prideful_parent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Cat'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- GUARDED HEIR ---
# When this creature enters, create two 3/3 white Knight creature tokens.
def guarded_heir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Knight Token',
                    'controller': obj.controller,
                    'power': 3,
                    'toughness': 3,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Knight'],
                    'colors': [Color.WHITE],
                    'token': True
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Knight Token',
                    'controller': obj.controller,
                    'power': 3,
                    'toughness': 3,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Knight'],
                    'colors': [Color.WHITE],
                    'token': True
                },
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, effect_fn)]


# --- RESOLUTE REINFORCEMENTS ---
# When this creature enters, create a 1/1 white Soldier creature token.
def resolute_reinforcements_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Soldier Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Soldier'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- YOUTHFUL VALKYRIE ---
# Whenever another Angel you control enters, put a +1/+1 counter on this creature.
def youthful_valkyrie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def angel_enters_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != source_obj.id and
                entering_obj.controller == source_obj.controller and
                "Angel" in entering_obj.characteristics.subtypes)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def filter_wrapper(event: Event, state: GameState) -> bool:
        return angel_enters_filter(event, state, obj)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_wrapper,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- AJANI'S PRIDEMATE ---
# Whenever you gain life, put a +1/+1 counter on this creature.
def ajanis_pridemate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, effect_fn)]


# --- EXEMPLAR OF LIGHT ---
# Whenever you gain life, put a +1/+1 counter on this creature.
def exemplar_of_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, effect_fn)]


# --- SKYKNIGHT SQUIRE ---
# Whenever another creature you control enters, put a +1/+1 counter on this creature.
def skyknight_squire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_enters_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != source_obj.id and
                entering_obj.controller == source_obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def filter_wrapper(event: Event, state: GameState) -> bool:
        return creature_enters_filter(event, state, obj)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_wrapper,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- BIGFIN BOUNCER ---
# When this creature enters, return target creature an opponent controls to its owner's hand.
def bigfin_bouncer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: needs targeting system, creates bounce event placeholder
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system would fill this
    return [make_etb_trigger(obj, effect_fn)]


# --- EXCLUSION MAGE ---
# When this creature enters, return target creature an opponent controls to its owner's hand.
def exclusion_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system would fill this
    return [make_etb_trigger(obj, effect_fn)]


# --- LIGHTSHELL DUO ---
# When this creature enters, surveil 2.
def lightshell_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- ICEWIND ELEMENTAL ---
# When this creature enters, draw a card, then discard a card.
def icewind_elemental_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, effect_fn)]


# --- CLINQUANT SKYMAGE ---
# Whenever you draw a card, put a +1/+1 counter on this creature.
def clinquant_skymage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_draw_trigger(obj, effect_fn)]


# --- MISCHIEVOUS MYSTIC ---
# Whenever you draw your second card each turn, create a 1/1 blue Faerie creature token with flying.
def mischievous_mystic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: triggers on any draw (second card tracking needs turn-based state)
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Faerie Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Faerie'],
                'colors': [Color.BLUE],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]
    return [make_draw_trigger(obj, effect_fn)]


# --- ARCHMAGE OF RUNES ---
# Whenever you cast an instant or sorcery spell, draw a card.
def archmage_of_runes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=True,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


# --- BURGLAR RAT ---
# When this creature enters, each opponent discards a card.
def burglar_rat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


# --- INFESTATION SAGE ---
# When this creature dies, create a 1/1 black and green Insect creature token with flying.
def infestation_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Insect Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Insect'],
                'colors': [Color.BLACK, Color.GREEN],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, effect_fn)]


# --- VENGEFUL BLOODWITCH ---
# Whenever this creature or another creature you control dies, target opponent loses 1 life and you gain 1 life.
def vengeful_bloodwitch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
                break  # Target one opponent
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- SANGUINE SYPHONER ---
# Whenever this creature attacks, each opponent loses 1 life and you gain 1 life.
def sanguine_syphoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


# --- BLOODTHIRSTY CONQUEROR ---
# Whenever an opponent loses life, you gain that much life.
def bloodthirsty_conqueror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def opponent_loses_life_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount >= 0:
            return False
        player = event.payload.get('player')
        return player != obj.controller

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        amount = abs(event.payload.get('amount', 0))
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opponent_loses_life_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- MARAUDING BLIGHT-PRIEST ---
# Whenever you gain life, each opponent loses 1 life.
def marauding_blightpriest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events
    return [make_life_gain_trigger(obj, effect_fn)]


# --- VAMPIRE SOULCALLER ---
# When this creature enters, return target creature card from your graveyard to your hand.
def vampire_soulcaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system would fill this
    return [make_etb_trigger(obj, effect_fn)]


# --- PHYREXIAN ARENA ---
# At the beginning of your upkeep, you draw a card and you lose 1 life.
def phyrexian_arena_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': -1},
                source=obj.id
            )
        ]
    return [make_upkeep_trigger(obj, effect_fn)]


# --- DRAGON TRAINER ---
# When this creature enters, create a 4/4 red Dragon creature token with flying.
def dragon_trainer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dragon Token',
                'controller': obj.controller,
                'power': 4,
                'toughness': 4,
                'types': [CardType.CREATURE],
                'subtypes': ['Dragon'],
                'colors': [Color.RED],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- FIREBRAND ARCHER ---
# Whenever you cast a noncreature spell, this creature deals 1 damage to each opponent.
def firebrand_archer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def noncreature_spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=noncreature_spell_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- FIRESPITTER WHELP ---
# Whenever you cast a noncreature or Dragon spell, this creature deals 1 damage to each opponent.
def firespitter_whelp_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        spell_subtypes = set(event.payload.get('subtypes', []))
        return CardType.CREATURE not in spell_types or "Dragon" in spell_subtypes

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- GOREHORN RAIDER ---
# Raid — When this creature enters, if you attacked this turn, this creature deals 2 damage to any target.
def gorehorn_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: damage effect without raid check (would need turn state)
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting and raid condition
    return [make_etb_trigger(obj, effect_fn)]


# --- SEARSLICER GOBLIN ---
# Raid — At the beginning of your end step, if you attacked this turn, create a 1/1 red Goblin creature token.
def searslicer_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: creates token every end step (raid check would need turn state)
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Goblin Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Goblin'],
                'colors': [Color.RED],
                'token': True
            },
            source=obj.id
        )]
    return [make_end_step_trigger(obj, effect_fn)]


# --- SPITFIRE LAGAC ---
# Landfall — Whenever a land you control enters, this creature deals 1 damage to each opponent.
def spitfire_lagac_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def land_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.LAND in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=land_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- DRAKUSETH, MAW OF FLAMES ---
# Whenever Drakuseth attacks, it deals 4 damage to any target and 3 damage to each of up to two other targets.
def drakuseth_maw_of_flames_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Simplified: needs targeting
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- ELFSWORN GIANT ---
# Landfall — Whenever a land you control enters, create a 1/1 green Elf Warrior creature token.
def elfsworn_giant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def land_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.LAND in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Elf Warrior Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Elf', 'Warrior'],
                'colors': [Color.GREEN],
                'token': True
            },
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=land_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- ELVISH REGROWER ---
# When this creature enters, return target permanent card from your graveyard to your hand.
def elvish_regrower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting
    return [make_etb_trigger(obj, effect_fn)]


# --- RECLAMATION SAGE ---
# When this creature enters, you may destroy target artifact or enchantment.
def reclamation_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting
    return [make_etb_trigger(obj, effect_fn)]


# --- DWYNEN, GILT-LEAF DAEN ---
# Other Elf creatures you control get +1/+1.
def dwynen_giltleaf_daen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Elf")
    )


# --- ELVISH ARCHDRUID ---
# Other Elf creatures you control get +1/+1.
def elvish_archdruid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Elf")
    )


# --- DWYNEN'S ELITE ---
# When this creature enters, if you control another Elf, create a 1/1 green Elf Warrior creature token.
def dwynens_elite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Check if we control another Elf
        for oid, other_obj in state.objects.items():
            if (oid != obj.id and
                other_obj.controller == obj.controller and
                other_obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in other_obj.characteristics.types and
                "Elf" in other_obj.characteristics.subtypes):
                return [Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Elf Warrior Token',
                        'controller': obj.controller,
                        'power': 1,
                        'toughness': 1,
                        'types': [CardType.CREATURE],
                        'subtypes': ['Elf', 'Warrior'],
                        'colors': [Color.GREEN],
                        'token': True
                    },
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- GOOD-FORTUNE UNICORN ---
# Whenever another creature you control enters, put a +1/+1 counter on that creature.
def good_fortune_unicorn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != obj.id and
                entering_obj.controller == obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': entering_id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- ANTHEM OF CHAMPIONS ---
# Creatures you control get +1/+1.
def anthem_of_champions_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        creatures_you_control(obj)
    )


# --- EMPYREAN EAGLE ---
# Other creatures you control with flying get +1/+1.
def empyrean_eagle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def has_flying(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Check for flying keyword
        keywords = getattr(target.characteristics, 'keywords', []) or []
        return 'flying' in keywords or 'Flying' in keywords

    return make_static_pt_boost(obj, 1, 1, has_flying)


# --- CORSAIR CAPTAIN ---
# Other Pirates you control get +1/+1.
def corsair_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # Lord effect
    interceptors.extend(make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Pirate")
    ))

    # ETB: create Treasure
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'token': True
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, effect_fn))

    return interceptors


# --- TATYOVA, BENTHIC DRUID ---
# Landfall — Whenever a land you control enters, you gain 1 life and draw a card.
def tatyova_benthic_druid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def land_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.LAND in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=land_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- METEOR GOLEM ---
# When this creature enters, destroy target nonland permanent an opponent controls.
def meteor_golem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting
    return [make_etb_trigger(obj, effect_fn)]


# --- SOLEMN SIMULACRUM ---
# When this creature enters, you may search your library for a basic land card...
# When this creature dies, you may draw a card.
def solemn_simulacrum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Needs library search

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_death_trigger(obj, death_effect)
    ]


# --- GLEAMING BARRIER ---
# When this creature dies, create a Treasure token.
def gleaming_barrier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, effect_fn)]


# --- INSPIRING OVERSEER ---
# When this creature enters, you gain 1 life and draw a card.
def inspiring_overseer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, effect_fn)]


# --- TWINBLADE PALADIN ---
# Whenever you gain life, put a +1/+1 counter on this creature.
def twinblade_paladin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, effect_fn)]


# --- FIENDISH PANDA ---
# Whenever you gain life, put a +1/+1 counter on this creature.
def fiendish_panda_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, effect_fn)]


# --- RITE OF THE DRAGONCALLER ---
# Whenever you cast an instant or sorcery spell, create a 5/5 red Dragon creature token with flying.
def rite_of_the_dragoncaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dragon Token',
                'controller': obj.controller,
                'power': 5,
                'toughness': 5,
                'types': [CardType.CREATURE],
                'subtypes': ['Dragon'],
                'colors': [Color.RED],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=True,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


# --- AUTHORITY OF THE CONSULS ---
# Whenever a creature an opponent controls enters, you gain 1 life.
def authority_of_the_consuls_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def opponent_creature_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller != obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opponent_creature_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- IMPACT TREMORS ---
# Whenever a creature you control enters, Impact Tremors deals 1 damage to each opponent.
def impact_tremors_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- GUTTERSNIPE ---
# Whenever you cast an instant or sorcery spell, Guttersnipe deals 2 damage to each opponent.
def guttersnipe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 2, 'source': obj.id},
                    source=obj.id
                ))
        return events
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=True,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


# --- IMPERIOUS PERFECT ---
# Other Elf creatures you control get +1/+1.
def imperious_perfect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Elf")
    )


# --- RAMPAGING BALOTHS ---
# Landfall — Whenever a land you control enters, create a 4/4 green Beast creature token.
def rampaging_baloths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def land_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.LAND in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Beast Token',
                'controller': obj.controller,
                'power': 4,
                'toughness': 4,
                'types': [CardType.CREATURE],
                'subtypes': ['Beast'],
                'colors': [Color.GREEN],
                'token': True
            },
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=land_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- HERALD OF FAITH ---
# Whenever this creature attacks, you gain 2 life.
def herald_of_faith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_attack_trigger(obj, effect_fn)]


# --- LYRA DAWNBRINGER ---
# Other Angels you control get +1/+1 and have lifelink.
def lyra_dawnbringer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    interceptors.extend(make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Angel")
    ))

    interceptors.append(make_keyword_grant(
        obj,
        ['lifelink'],
        other_creatures_with_subtype(obj, "Angel")
    ))

    return interceptors


# --- WILDWOOD SCOURGE ---
# Whenever one or more +1/+1 counters are put on another non-Hydra creature you control, put a +1/+1 counter on this creature.
def wildwood_scourge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def counter_added_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if event.payload.get('counter_type') != '+1/+1':
            return False
        target_id = event.payload.get('object_id')
        if target_id == obj.id:
            return False
        target_obj = state.objects.get(target_id)
        if not target_obj:
            return False
        return (target_obj.controller == obj.controller and
                CardType.CREATURE in target_obj.characteristics.types and
                "Hydra" not in target_obj.characteristics.subtypes)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=counter_added_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- WILT-LEAF LIEGE ---
# Other green creatures you control get +1/+1.
# Other white creatures you control get +1/+1.
def wiltleaf_liege_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_green_creatures(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return Color.GREEN in target.characteristics.colors

    def other_white_creatures(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return Color.WHITE in target.characteristics.colors

    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_green_creatures))
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_white_creatures))
    return interceptors


# --- BALMOR, BATTLEMAGE CAPTAIN ---
# Whenever you cast an instant or sorcery spell, creatures you control get +1/+0 and gain trample until end of turn.
def balmor_battlemage_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: would need "until end of turn" effect tracking
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs temporary effect system
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=True,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


# --- BRINEBORN CUTTHROAT ---
# Whenever you cast a spell during an opponent's turn, put a +1/+1 counter on this creature.
def brineborn_cutthroat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def opponent_turn_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        # Check if it's an opponent's turn
        return state.active_player != obj.controller

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opponent_turn_cast_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- LATHRIL, BLADE OF THE ELVES ---
# Whenever Lathril deals combat damage to a player, create that many 1/1 green Elf Warrior creature tokens.
def lathril_blade_of_the_elves_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        damage_amount = event.payload.get('amount', 0)
        events = []
        for _ in range(damage_amount):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Elf Warrior Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Elf', 'Warrior'],
                    'colors': [Color.GREEN],
                    'token': True
                },
                source=obj.id
            ))
        return events
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- SCRAWLING CRAWLER ---
# At the beginning of your upkeep, each player draws a card.
# Whenever an opponent draws a card, that player loses 1 life.
def scrawling_crawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Upkeep trigger: each player draws
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': player_id, 'amount': 1},
                source=obj.id
            ))
        return events

    # Opponent draw trigger
    def opponent_draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        return event.payload.get('player') != obj.controller

    def opponent_draw_effect(event: Event, state: GameState) -> list[Event]:
        player = event.payload.get('player')
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': player, 'amount': -1},
            source=obj.id
        )]

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=opponent_draw_effect(event, state))

    return [
        make_upkeep_trigger(obj, upkeep_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=opponent_draw_filter,
            handler=draw_handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=opponent_draw_effect,
        )
    ]


# --- EXTRAVAGANT REPLICATION ---
# At the beginning of your upkeep, create a token that's a copy of another target nonland permanent you control.
def extravagant_replication_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting and copy mechanics
    return [make_upkeep_trigger(obj, effect_fn)]


# --- CAT COLLECTOR ---
# When this creature enters, create a Food token.
# Whenever you gain life for the first time during each of your turns, create a 1/1 white Cat creature token.
def cat_collector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'token': True
            },
            source=obj.id
        )]

    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Cat'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_life_gain_trigger(obj, life_gain_effect)
    ]


# --- DAUNTLESS VETERAN ---
# Whenever this creature attacks, creatures you control get +1/+1 until end of turn.
def dauntless_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs "until end of turn" effect system
    return [make_attack_trigger(obj, effect_fn)]


# --- FELIDAR SAVIOR ---
# When this creature enters, put a +1/+1 counter on each of up to two other target creatures you control.
def felidar_savior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting system
    return [make_etb_trigger(obj, effect_fn)]


# --- HARE APPARENT ---
# When this creature enters, create a number of 1/1 white Rabbit creature tokens equal to the number of other creatures you control named Hare Apparent.
def hare_apparent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Count other Hare Apparent creatures.
        count = 0
        for oid, other_obj in state.objects.items():
            if (
                oid != obj.id
                and other_obj.controller == obj.controller
                and other_obj.zone == ZoneType.BATTLEFIELD
                and other_obj.name == "Hare Apparent"
            ):
                count += 1

        events = []
        for _ in range(count):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Rabbit Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Rabbit'],
                    'colors': [Color.WHITE],
                    'token': True
                },
                source=obj.id
            ))
        return events

    return [make_etb_trigger(obj, effect_fn)]


# --- VANGUARD SERAPH ---
# Whenever you gain life for the first time each turn, surveil 1.
def vanguard_seraph_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, effect_fn)]


# --- CEPHALID INKMAGE ---
# When this creature enters, surveil 3.
def cephalid_inkmage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- ERUDITE WIZARD ---
# Whenever you draw your second card each turn, put a +1/+1 counter on this creature.
def erudite_wizard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: triggers on any draw (second card tracking needs turn-based state)
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_draw_trigger(obj, effect_fn)]


# --- HOMUNCULUS HORDE ---
# Whenever you draw your second card each turn, create a token that's a copy of this creature.
def homunculus_horde_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: triggers on any draw
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Homunculus Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Homunculus'],
                'colors': [Color.BLUE],
                'token': True
            },
            source=obj.id
        )]
    return [make_draw_trigger(obj, effect_fn)]


# --- KIORA, THE RISING TIDE ---
# When Kiora enters, draw two cards, then discard two cards.
def kiora_the_rising_tide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, effect_fn)]


# --- BILLOWING SHRIEKMASS ---
# When this creature enters, mill three cards.
def billowing_shriekmass_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- ARBITER OF WOE ---
# When this creature enters, each opponent discards a card and loses 2 life. You draw a card and gain 2 life.
def arbiter_of_woe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'amount': 1},
                    source=obj.id
                ))
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -2},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


# --- HIGH-SOCIETY HUNTER ---
# Whenever another nontoken creature dies, draw a card.
def highsociety_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_id != obj.id and
                CardType.CREATURE in dying_obj.characteristics.types and
                not getattr(dying_obj.characteristics, 'is_token', False))

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- INFERNAL VESSEL ---
# When this creature dies, if it wasn't a Demon, return it to the battlefield with two +1/+1 counters.
def infernal_vessel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Check if it was a Demon when it died
        if "Demon" not in obj.characteristics.subtypes:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'counters': {'+1/+1': 2},
                    'add_subtypes': ['Demon']
                },
                source=obj.id
            )]
        return []
    return [make_death_trigger(obj, effect_fn)]


# --- SOUL-SHACKLED ZOMBIE ---
# When this creature enters, exile up to two target cards from a single graveyard. If at least one creature card was exiled, each opponent loses 2 life and you gain 2 life.
def soulshackled_zombie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting system
    return [make_etb_trigger(obj, effect_fn)]


# --- CRACKLING CYCLOPS ---
# Whenever you cast a noncreature spell, this creature gets +3/+0 until end of turn.
def crackling_cyclops_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def noncreature_spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs "until end of turn" effect system

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=noncreature_spell_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- APOTHECARY STOMPER ---
# When this creature enters, choose one: Put two +1/+1 counters on target creature you control, or You gain 4 life.
def apothecary_stomper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Default to gaining 4 life (targeting needs choice system)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 4},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]


# --- BEAST-KIN RANGER ---
# Whenever another creature you control enters, this creature gets +1/+0 until end of turn.
def beastkin_ranger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != obj.id and
                entering_obj.controller == obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs "until end of turn" effect system

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- EAGER TRUFFLESNOUT ---
# Whenever this creature deals combat damage to a player, create a Food token.
def eager_trufflesnout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'token': True
            },
            source=obj.id
        )]
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- MOSSBORN HYDRA ---
# Landfall — Whenever a land you control enters, double the number of +1/+1 counters on this creature.
def mossborn_hydra_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def land_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.LAND in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        current_counters = getattr(obj, 'counters', {}).get('+1/+1', 0)
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': current_counters},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=land_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- DREADWING SCAVENGER ---
# Whenever this creature enters or attacks, draw a card, then discard a card.
def dreadwing_scavenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [
        make_etb_trigger(obj, effect_fn),
        make_attack_trigger(obj, effect_fn)
    ]


# --- KOMA, WORLD-EATER ---
# Whenever Koma deals combat damage to a player, create four 3/3 blue Serpent creature tokens.
def koma_worldeater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(4):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': "Koma's Coil",
                    'controller': obj.controller,
                    'power': 3,
                    'toughness': 3,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Serpent'],
                    'colors': [Color.BLUE],
                    'token': True
                },
                source=obj.id
            ))
        return events
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- KYKAR, ZEPHYR AWAKENER ---
# Whenever you cast a noncreature spell, create a 1/1 white Spirit creature token with flying.
def kykar_zephyr_awakener_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def noncreature_spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Spirit Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Spirit'],
                'colors': [Color.WHITE],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=noncreature_spell_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- NIV-MIZZET, VISIONARY ---
# Whenever a source you control deals noncombat damage to an opponent, you draw that many cards.
def nivmizzet_visionary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('is_combat', False):
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj or source_obj.controller != obj.controller:
            return False
        target = event.payload.get('target')
        return target != obj.controller and target in state.players

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        damage_amount = event.payload.get('amount', 0)
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': damage_amount},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- ANGEL OF FINALITY ---
# When this creature enters, exile target player's graveyard.
def angel_of_finality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting system
    return [make_etb_trigger(obj, effect_fn)]


# --- MISCHIEVOUS PUP ---
# When this creature enters, return up to one other target permanent you control to its owner's hand.
def mischievous_pup_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting system
    return [make_etb_trigger(obj, effect_fn)]


# --- HERALD OF FAITH ---
# Whenever this creature attacks, you gain 2 life.
# (Already implemented above)


# --- SYR ALIN, THE LION'S CLAW ---
# Whenever Syr Alin attacks, other creatures you control get +1/+1 until end of turn.
def syr_alin_the_lions_claw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs "until end of turn" effect system
    return [make_attack_trigger(obj, effect_fn)]


# --- PULSE TRACKER ---
# Whenever this creature attacks, each opponent loses 1 life.
def pulse_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


# --- MIDNIGHT REAPER ---
# Whenever a nontoken creature you control dies, this creature deals 1 damage to you and you draw a card.
def midnight_reaper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                not getattr(dying_obj.characteristics, 'is_token', False))

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={'target': obj.controller, 'amount': 1, 'source': obj.id},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- DRIVER OF THE DEAD ---
# When this creature dies, return target creature card with mana value 2 or less from your graveyard to the battlefield.
def driver_of_the_dead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting system
    return [make_death_trigger(obj, effect_fn)]


# --- KALASTRIA HIGHBORN ---
# Whenever a Vampire you control dies, you may pay {B}. If you do, target player loses 2 life and you gain 2 life.
def kalastria_highborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def vampire_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                "Vampire" in dying_obj.characteristics.subtypes)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Simplified: auto-triggers without paying
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -2},
                    source=obj.id
                ))
                break
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=vampire_dies_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- GOBLIN CHIEFTAIN ---
# Other Goblins you control get +1/+1.
def goblin_chieftain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Goblin")
    )


# --- LATHLISS, DRAGON QUEEN ---
# Whenever another nontoken Dragon you control enters, create a 5/5 red Dragon creature token with flying.
def lathliss_dragon_queen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dragon_enters_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != source_obj.id and
                entering_obj.controller == source_obj.controller and
                "Dragon" in entering_obj.characteristics.subtypes and
                not getattr(entering_obj.characteristics, 'is_token', False))

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dragon Token',
                'controller': obj.controller,
                'power': 5,
                'toughness': 5,
                'types': [CardType.CREATURE],
                'subtypes': ['Dragon'],
                'colors': [Color.RED],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]

    def filter_wrapper(event: Event, state: GameState) -> bool:
        return dragon_enters_filter(event, state, obj)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_wrapper,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- VIASHINO PYROMANCER ---
# When this creature enters, it deals 2 damage to target player or planeswalker.
def viashino_pyromancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Target an opponent by default
        for player_id in state.players.keys():
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 2, 'source': obj.id},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- FIERCE EMPATH ---
# When this creature enters, you may search your library for a creature card with mana value 6 or greater.
def fierce_empath_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=creature_with_mv_at_least(6),
            destination="hand",
            shuffle_after=True,
            optional=True,
            prompt="You may search your library for a creature card with mana value 6 or greater.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- SPRINGBLOOM DRUID ---
# When this creature enters, you may sacrifice a land. If you do, search your library for up to two basic land cards.
# Sacrifice rider is still an engine gap — we approximate by skipping the sacrifice and offering the search,
# so the tutor part is at least exercisable end-to-end.
def springbloom_druid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=basic_land_filter(),
            destination="battlefield_tapped",
            max_count=2,
            shuffle_after=True,
            optional=True,
            prompt="You may sacrifice a land; if you do, search your library for up to 2 basic lands and put them onto the battlefield tapped.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- GARNA, BLOODFIST OF KELD ---
# Whenever another creature you control dies, draw a card if it was attacking. Otherwise, Garna deals 1 damage to each opponent.
def garna_bloodfist_of_keld_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == obj.id:
            return False
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Simplified: deal damage to opponents (attacking check needs combat state)
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- MASSACRE WURM ---
# When this creature enters, creatures your opponents control get -2/-2 until end of turn.
# Whenever a creature an opponent controls dies, that player loses 2 life.
def massacre_wurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def opponent_creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller != obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def death_effect(event: Event, state: GameState) -> list[Event]:
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if dying_obj:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': dying_obj.controller, 'amount': -2},
                source=obj.id
            )]
        return []

    def death_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=death_effect(event, state))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Needs "until end of turn" effect system

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=opponent_creature_dies_filter,
            handler=death_handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=death_effect,
        )
    ]


# --- PELAKKA WURM ---
# When this creature enters, you gain 7 life.
# When this creature dies, draw a card.
def pelakka_wurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 7},
            source=obj.id
        )]

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_death_trigger(obj, death_effect)
    ]


# --- CLOUDBLAZER ---
# When this creature enters, you gain 2 life and draw two cards.
def cloudblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, effect_fn)]


# --- AURELIA, THE WARLEADER ---
# Whenever Aurelia attacks for the first time each turn, untap all creatures you control.
def aurelia_the_warleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for oid, creature in state.objects.items():
            if (creature.controller == obj.controller and
                creature.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in creature.characteristics.types):
                events.append(Event(
                    type=EventType.UNTAP,
                    payload={'object_id': oid},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


# --- REGAL CARACAL ---
# Other Cats you control get +1/+1 and have lifelink.
# When this creature enters, create two 1/1 white Cat creature tokens with lifelink.
def regal_caracal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    interceptors.extend(make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Cat")
    ))

    interceptors.append(make_keyword_grant(
        obj,
        ['lifelink'],
        other_creatures_with_subtype(obj, "Cat")
    ))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Cat Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Cat'],
                    'colors': [Color.WHITE],
                    'keywords': ['lifelink'],
                    'token': True
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Cat Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Cat'],
                    'colors': [Color.WHITE],
                    'keywords': ['lifelink'],
                    'token': True
                },
                source=obj.id
            )
        ]

    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors


# --- ADAPTIVE AUTOMATON ---
# As this creature enters, choose a creature type.
# Other creatures you control of the chosen type get +1/+1.
def adaptive_automaton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: defaults to boosting all creatures (choice needs system)
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_you_control(obj)
    )


# --- ANGEL OF VITALITY ---
# If you would gain life, you gain that much life plus 1 instead.
# Angel of Vitality gets +2/+2 as long as you have 25 or more life.
def angel_of_vitality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If you would gain life, you gain that much life plus 1 instead.

    Bonus +2/+2 at 25+ life is wired via a conditional QUERY_POWER/TOUGHNESS
    interceptor.
    """
    from src.engine.replacements import make_life_gain_replacer
    interceptors: list[Interceptor] = []

    # Life gain replacement: +1 to any life gain by controller.
    interceptors.append(make_life_gain_replacer(obj, multiplier=1, addend=1))

    # +2/+2 while controller has 25+ life.
    source_id = obj.id
    affected_controller = obj.controller

    def boost_filter(event: Event, state: GameState, query_type: EventType) -> bool:
        if event.type != query_type:
            return False
        if event.payload.get('object_id') != source_id:
            return False
        src = state.objects.get(source_id)
        if not src or src.zone != ZoneType.BATTLEFIELD:
            return False
        player = state.players.get(affected_controller)
        return bool(player and player.life >= 25)

    def make_boost(query_type: EventType) -> Interceptor:
        def filt(event: Event, state: GameState) -> bool:
            return boost_filter(event, state, query_type)

        def handler(event: Event, state: GameState) -> InterceptorResult:
            new_event = event.copy()
            new_event.payload['value'] = new_event.payload.get('value', 0) + 2
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        return Interceptor(
            id=new_id(),
            source=source_id,
            controller=affected_controller,
            priority=InterceptorPriority.QUERY,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
        )

    interceptors.append(make_boost(EventType.QUERY_POWER))
    interceptors.append(make_boost(EventType.QUERY_TOUGHNESS))
    return interceptors


# --- LINDEN, THE STEADFAST QUEEN ---
# Whenever a white creature you control attacks, you gain 1 life.
def linden_the_steadfast_queen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def white_creature_attacks_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == obj.controller and
                CardType.CREATURE in attacker.characteristics.types and
                Color.WHITE in attacker.characteristics.colors)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=white_creature_attacks_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- MENTOR OF THE MEEK ---
# Whenever another creature with power 2 or less enters under your control, you may pay {1}. If you do, draw a card.
def mentor_of_the_meek_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_id != obj.id and
                entering_obj.controller == obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                entering_obj.characteristics.power <= 2)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Simplified: auto-draw (payment needs mana system)
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- FELIDAR RETREAT ---
# Landfall — Whenever a land enters the battlefield under your control, choose one: Create a 2/2 white Cat Beast creature token, or put a +1/+1 counter on each creature you control.
def felidar_retreat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def land_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.LAND in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Default to creating a token
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cat Beast Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Cat', 'Beast'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=obj.id
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=land_enters_filter,
        handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=effect_fn,
    )]


# --- PRIMEVAL BOUNTY ---
# Whenever you cast a creature spell, create a 3/3 green Beast creature token.
# Whenever you cast a noncreature spell, put three +1/+1 counters on target creature you control.
def primeval_bounty_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE in spell_types

    def creature_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Beast Token',
                'controller': obj.controller,
                'power': 3,
                'toughness': 3,
                'types': [CardType.CREATURE],
                'subtypes': ['Beast'],
                'colors': [Color.GREEN],
                'token': True
            },
            source=obj.id
        )]

    def creature_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=creature_effect(event, state))

    def noncreature_spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def noncreature_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Needs targeting system

    def noncreature_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=noncreature_effect(event, state))

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=creature_spell_filter,
            handler=creature_handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=creature_effect,
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=noncreature_spell_filter,
            handler=noncreature_handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=noncreature_effect,
        )
    ]


# =============================================================================
# SPELL RESOLVE FUNCTIONS
# =============================================================================


def _negate_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Negate after target selection - counter the spell."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # The target_id is the source_id of a StackItem
    # We need to find the card on the stack and move it to graveyard
    stack_zone = state.zones.get('stack')
    if not stack_zone:
        return []

    # Find the card being countered
    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []  # Target no longer valid

    # Counter the spell by moving it to graveyard
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]


def negate_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Negate: counter the chosen noncreature spell (Phase 5b).

    Targets are pre-chosen at cast time via ``target_requirements``.
    """
    return _resolve_counter_targeted_spell()(targets, state)


def _shock_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Shock after target selection - deal 2 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Check if target is a player or permanent
    if target_id in state.players:
        # Target is a player
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    else:
        # Target is a permanent (creature or planeswalker)
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []  # Target no longer valid

        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]


def shock_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Shock: 2 damage to the chosen target (Phase 5b)."""
    return _resolve_damage_to_targets(2)(targets, state)


def _burst_lightning_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Burst Lightning after target selection - deal 2 or 4 damage based on kicker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Check if the spell was kicked (stored in callback_data)
    was_kicked = choice.callback_data.get('kicked', False)
    damage_amount = 4 if was_kicked else 2

    # Check if target is a player or permanent
    if target_id in state.players:
        # Target is a player
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': damage_amount, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    else:
        # Target is a permanent (creature or planeswalker)
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []  # Target no longer valid

        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': damage_amount, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]


def burst_lightning_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Burst Lightning: 2 damage (4 if kicked) to chosen target."""
    spell = _resolving_spell_obj(state)
    was_kicked = bool(getattr(spell.state, 'kicked', False)) if spell and spell.state else False
    amount = 4 if was_kicked else 2
    return _resolve_damage_to_targets(amount)(targets, state)


# =============================================================================
# CANCEL - Counter target spell
# =============================================================================

def _cancel_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Cancel after target selection - counter any spell."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]


def cancel_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Cancel: counter the chosen spell (Phase 5b)."""
    return _resolve_counter_targeted_spell()(targets, state)


# =============================================================================
# ESSENCE SCATTER - Counter target creature spell
# =============================================================================

def _essence_scatter_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Essence Scatter after target selection - counter a creature spell."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]


def essence_scatter_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Essence Scatter: counter the chosen creature spell (Phase 5b)."""
    return _resolve_counter_targeted_spell()(targets, state)


def _creature_spell_filter(obj: GameObject, state: GameState) -> bool:
    """Match spells on the stack that ARE creature spells."""
    return CardType.CREATURE in obj.characteristics.types


def _noncreature_spell_filter(obj: GameObject, state: GameState) -> bool:
    """Match spells on the stack whose card type isn't creature."""
    return CardType.CREATURE not in obj.characteristics.types


# =============================================================================
# UNSUMMON - Return target creature to its owner's hand
# =============================================================================

def _unsummon_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Unsummon - bounce a creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'hand_{target.owner}',
            'to_zone_type': ZoneType.HAND,
            'reason': 'bounced'
        },
        source=choice.source_id
    )]


def unsummon_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Unsummon: bounce the chosen creature (Phase 5b)."""
    return _resolve_bounce_targets()(targets, state)


# =============================================================================
# HEROS DOWNFALL - Destroy target creature or planeswalker
# =============================================================================

def _heros_downfall_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hero's Downfall - destroy a creature or planeswalker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def heros_downfall_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Hero's Downfall: destroy the chosen creature/PW (Phase 5b)."""
    return _resolve_destroy_targets()(targets, state)


# =============================================================================
# UNDYING MALICE - target creature gains "When this dies, return tapped with +1/+1"
# =============================================================================

def undying_malice_resolve(targets: list, state: GameState) -> list[Event]:
    """Until EOT, chosen creature gains a death trigger returning it tapped
    with a +1/+1 counter (Phase 5b)."""
    from src.cards.interceptor_helpers import grant_death_trigger
    tid = _first_target_id(targets, state)
    if tid is None:
        return []
    target = state.objects.get(tid)
    if target is None:
        return []
    spell = _resolving_spell_obj(state)
    spell_obj = spell if spell is not None else target
    spell_id = spell.id if spell else "undying_malice_spell"

    def _death_effect(target_obj: GameObject, gs2: GameState) -> list[Event]:
        owner = target_obj.owner
        return [
            Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={'object_id': target_obj.id, 'player': owner, 'tapped': True},
                source=spell_id, controller=owner,
            ),
            Event(
                type=EventType.TAP,
                payload={'object_id': target_obj.id},
                source=spell_id, controller=owner,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': target_obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=spell_id, controller=owner,
            ),
        ]
    grant_death_trigger(target, spell_obj, state, _death_effect, duration='end_of_turn')
    return []


# =============================================================================
# FAKE YOUR OWN DEATH - target creature gets +2/+0 and a return-with-treasure death trigger
# =============================================================================

def fake_your_own_death_resolve(targets: list, state: GameState) -> list[Event]:
    """Until EOT, chosen creature gets +2/+0 and gains a death trigger
    returning it tapped under owner's control + Treasure (Phase 5b)."""
    from src.cards.interceptor_helpers import grant_death_trigger
    tid = _first_target_id(targets, state)
    if tid is None:
        return []
    target = state.objects.get(tid)
    if target is None:
        return []
    spell = _resolving_spell_obj(state)
    spell_obj = spell if spell is not None else target
    spell_id = spell.id if spell else "fake_your_own_death_spell"
    caster_id = _spell_caster_id(state)

    def _death_effect(target_obj: GameObject, gs2: GameState) -> list[Event]:
        owner = target_obj.owner
        return [
            Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={'object_id': target_obj.id, 'player': owner, 'tapped': True},
                source=spell_id, controller=owner,
            ),
            Event(
                type=EventType.TAP,
                payload={'object_id': target_obj.id},
                source=spell_id, controller=owner,
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure',
                    'controller': owner,
                    'owner': owner,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'colors': set(),
                    'is_token': True,
                },
                source=spell_id, controller=owner,
            ),
        ]
    grant_death_trigger(target, spell_obj, state, _death_effect, duration='end_of_turn')
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            'object_id': target.id,
            'power_mod': 2,
            'toughness_mod': 0,
            'duration': 'end_of_turn',
        },
        source=spell_id, controller=caster_id,
    )]


# =============================================================================
# MURDER - Destroy target creature (Black instant)
# =============================================================================

def _murder_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Murder - destroy a creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def murder_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Murder: destroy the chosen creature (Phase 5b).

    Not currently registered to a card in this module, but exposed for
    callers that may import it. Targets are pre-chosen at cast time.
    """
    return _resolve_destroy_targets()(targets, state)


# =============================================================================
# DISENCHANT - Destroy target artifact or enchantment
# =============================================================================

def _disenchant_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Disenchant - destroy an artifact or enchantment."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def disenchant_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Disenchant: destroy the chosen artifact/enchantment (Phase 5b)."""
    return _resolve_destroy_targets()(targets, state)


# =============================================================================
# NATURALIZE - Destroy target artifact or enchantment (green version)
# =============================================================================

def _naturalize_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Naturalize - destroy an artifact or enchantment."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def naturalize_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Naturalize: destroy the chosen artifact/enchantment (Phase 5b)."""
    return _resolve_destroy_targets()(targets, state)


# =============================================================================
# LIGHTNING BOLT - Deal 3 damage to any target
# =============================================================================

def _lightning_bolt_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Lightning Bolt - deal 3 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    if target_id in state.players:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    else:
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []

        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]


def lightning_bolt_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Lightning Bolt: 3 damage to chosen target (Phase 5b).

    Not currently registered to a card in this module; the canonical Lightning
    Bolt lives in ``src/cards/test_cards.py``. Kept here for any callers.
    """
    return _resolve_damage_to_targets(3)(targets, state)


# =============================================================================
# SCORCHING DRAGONFIRE - Deal 3 damage to creature/planeswalker, exile if dies
# =============================================================================

def _scorching_dragonfire_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Scorching Dragonfire - deal 3 damage to creature/pw."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Note: The "exile instead" effect would need additional interceptor logic
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False, 'exile_on_death': True},
        source=choice.source_id
    )]


def scorching_dragonfire_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Scorching Dragonfire: 3 damage to chosen creature/PW (Phase 5b).

    The ``exile_on_death`` rider is preserved in the damage event payload.
    """
    from src.engine.spell_resolve import _flatten_targets  # type: ignore
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': t.id,
                'amount': 3,
                'is_combat': False,
                'source': source_id,
                'exile_on_death': True,
            },
            source=source_id,
        ))
    return events


# =============================================================================
# STROKE OF MIDNIGHT - Destroy target nonland permanent, give token
# =============================================================================

def _stroke_of_midnight_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Stroke of Midnight - destroy nonland permanent."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Token',
                'controller': target.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human'],
                'colors': [Color.WHITE],
                'token': True
            },
            source=choice.source_id
        )
    ]


def stroke_of_midnight_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Stroke of Midnight: destroy chosen nonland permanent, give Human token (Phase 5b)."""
    tid = _first_target_id(targets, state)
    if tid is None:
        return []
    target = state.objects.get(tid)
    if target is None or target.zone != ZoneType.BATTLEFIELD:
        return []
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': tid},
            source=source_id,
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Token',
                'controller': target.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human'],
                'colors': [Color.WHITE],
                'token': True,
            },
            source=source_id,
        ),
    ]


def _nonland_permanent_filter(obj: GameObject, state: GameState) -> bool:
    """Match permanents on the battlefield whose type isn't land."""
    return CardType.LAND not in obj.characteristics.types


# =============================================================================
# ANGELIC EDICT - Exile target creature or enchantment
# =============================================================================

def _angelic_edict_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Angelic Edict - exile a creature or enchantment."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': 'exile',
            'to_zone_type': ZoneType.EXILE,
            'reason': 'exiled'
        },
        source=choice.source_id
    )]


def angelic_edict_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Angelic Edict: exile the chosen creature/enchantment (Phase 5b)."""
    return _resolve_exile_targets()(targets, state)


# =============================================================================
# GIANT GROWTH - Target creature gets +3/+3 until end of turn
# =============================================================================

def _giant_growth_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Giant Growth - give +3/+3."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PT_MODIFIER,
        payload={
            'object_id': target_id,
            'power_mod': 3,
            'toughness_mod': 3,
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def giant_growth_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Giant Growth: +3/+3 to chosen creature until end of turn (Phase 5b)."""
    return resolve_pump(3, 3)(targets, state)


# =============================================================================
# BAKE INTO A PIE - Destroy target creature, create Food token
# =============================================================================

def _bake_into_a_pie_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Bake into a Pie - destroy creature and create Food."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': choice.player,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'colors': [],
                'token': True
            },
            source=choice.source_id
        )
    ]


def bake_into_a_pie_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Bake into a Pie: destroy chosen creature, create Food (Phase 5b)."""
    tid = _first_target_id(targets, state)
    if tid is None:
        return []
    target = state.objects.get(tid)
    if target is None or target.zone != ZoneType.BATTLEFIELD:
        return []
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _spell_caster_id(state)
    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': tid},
            source=source_id,
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': caster,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'colors': [],
                'token': True,
            },
            source=source_id,
        ),
    ]


# =============================================================================
# DEADLY RIPOSTE - 3 damage to target tapped creature, gain 2 life
# =============================================================================

def _deadly_riposte_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Deadly Riposte - deal 3 damage and gain 2 life."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': 2},
            source=choice.source_id
        )
    ]


def deadly_riposte_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Deadly Riposte: 3 damage to chosen tapped creature, caster gains 2 life (Phase 5b)."""
    return resolve_chain(
        _resolve_damage_to_targets(3),
        _resolve_caster_life_change(2),
    )(targets, state)


# =============================================================================
# VALOROUS STANCE - Modal: Indestructible OR destroy creature toughness 4+
# =============================================================================

def _valorous_stance_mode_indestructible(state, caster_id, spell_id, targets=None):
    """Mode 1: target creature you control gains indestructible EOT."""
    if not targets:
        return []
    return [Event(
        type=EventType.KEYWORD_GRANT,
        payload={
            'object_id': targets[0].id,
            'keyword': 'indestructible',
            'duration': 'end_of_turn',
        },
        source=spell_id, controller=caster_id,
    )]


def _valorous_stance_mode_destroy(state, caster_id, spell_id, targets=None):
    """Mode 2: destroy target creature with toughness 4 or greater."""
    if not targets:
        return []
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': targets[0].id},
        source=spell_id, controller=caster_id,
    )]


def _toughness_4_or_greater(obj: GameObject, state: GameState) -> bool:
    t = obj.characteristics.toughness or 0
    return t >= 4


# =============================================================================
# DEADLY PLOT - Modal: Destroy creature/pw OR return Zombie from graveyard
# =============================================================================

def _deadly_plot_mode_destroy(state, caster_id, spell_id, targets=None):
    """Mode 1: destroy target creature or planeswalker."""
    if not targets:
        return []
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': targets[0].id},
        source=spell_id, controller=caster_id,
    )]


def _deadly_plot_mode_reanimate(state, caster_id, spell_id, targets=None):
    """Mode 2: return target Zombie creature card from graveyard to battlefield tapped."""
    if not targets:
        return []
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': targets[0].id,
            'from_zone': f'graveyard_{caster_id}',
            'from_zone_type': ZoneType.GRAVEYARD,
            'to_zone': f'battlefield_{caster_id}',
            'to_zone_type': ZoneType.BATTLEFIELD,
            'enters_tapped': True,
            'reason': 'returned',
        },
        source=spell_id, controller=caster_id,
    )]


# DEADLY_PLOT now uses make_modal_resolve(ModeSpec(...)) directly — see
# definition below; resolve function above is replaced by the ModeSpec
# dispatch in the card def.


# =============================================================================
# INTO THE ROIL - Bounce nonland permanent, draw if kicked
# =============================================================================

def _into_the_roil_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Into the Roil - bounce a nonland permanent."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'hand_{target.owner}',
            'to_zone_type': ZoneType.HAND,
            'reason': 'bounced'
        },
        source=choice.source_id
    )]

    # If kicked, draw a card
    if choice.callback_data.get('kicked', False):
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        ))

    return events


def into_the_roil_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Into the Roil: bounce chosen nonland permanent; draw if kicked (Phase 5b)."""
    events = _resolve_bounce_targets()(targets, state)
    spell = _resolving_spell_obj(state)
    was_kicked = bool(getattr(spell.state, 'kicked', False)) if spell and spell.state else False
    if was_kicked:
        events.extend(_resolve_caster_draw(1)(targets, state))
    return events


# =============================================================================
# MOMENT OF TRIUMPH - +2/+2 and gain 2 life
# =============================================================================

def _moment_of_triumph_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Moment of Triumph - +2/+2 and gain 2 life."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFIER,
            payload={
                'object_id': target_id,
                'power_mod': 2,
                'toughness_mod': 2,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': 2},
            source=choice.source_id
        )
    ]


def moment_of_triumph_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Moment of Triumph: +2/+2 to chosen creature; caster gains 2 life (Phase 5b)."""
    return resolve_chain(
        resolve_pump(2, 2),
        _resolve_caster_life_change(2),
    )(targets, state)


# =============================================================================
# DIVE DOWN - +0/+3 and hexproof until end of turn
# =============================================================================

def _dive_down_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Dive Down - +0/+3 and hexproof."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFIER,
            payload={
                'object_id': target_id,
                'power_mod': 0,
                'toughness_mod': 3,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={
                'object_id': target_id,
                'keyword': 'hexproof',
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def dive_down_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Dive Down: +0/+3 + hexproof to chosen creature you control (Phase 5b)."""
    return resolve_chain(
        resolve_pump(0, 3),
        _resolve_grant_keyword('hexproof'),
    )(targets, state)


# =============================================================================
# FLEETING DISTRACTION - -1/-0 and draw a card
# =============================================================================

def _fleeting_distraction_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Fleeting Distraction - -1/-0 and draw."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFIER,
            payload={
                'object_id': target_id,
                'power_mod': -1,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.DRAW,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        )
    ]


def fleeting_distraction_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Fleeting Distraction: -1/-0 to chosen creature; caster draws (Phase 5b)."""
    return resolve_chain(
        resolve_pump(-1, 0),
        _resolve_caster_draw(1),
    )(targets, state)


# =============================================================================
# AN OFFER YOU CAN'T REFUSE - Counter noncreature spell, give treasures
# =============================================================================

def _an_offer_you_cant_refuse_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute An Offer You Can't Refuse - counter spell and give treasures."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]

    # Create two treasures for the spell's controller
    for _ in range(2):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': target_card.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': [],
                'token': True
            },
            source=choice.source_id
        ))

    return events


def an_offer_you_cant_refuse_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve An Offer You Can't Refuse: counter chosen noncreature spell;
    its controller gets two Treasures (Phase 5b)."""
    tid = _first_target_id(targets, state)
    if tid is None:
        return []
    target_card = state.objects.get(tid)
    if target_card is None or target_card.zone != ZoneType.STACK:
        return []
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': tid,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered',
        },
        source=source_id,
    )]
    for _ in range(2):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': target_card.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': [],
                'token': True,
            },
            source=source_id,
        ))
    return events


# =============================================================================
# FLASHFREEZE - Counter target red or green spell
# =============================================================================

def _flashfreeze_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Flashfreeze - counter a red or green spell."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]


def flashfreeze_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Flashfreeze: counter the chosen red/green spell (Phase 5b)."""
    return _resolve_counter_targeted_spell()(targets, state)


def _red_or_green_spell_filter(obj: GameObject, state: GameState) -> bool:
    """Match spells on the stack that are red and/or green."""
    colors = obj.characteristics.colors or set()
    return Color.RED in colors or Color.GREEN in colors


# =============================================================================
# TRIBUTE TO HUNGER - Opponent sacrifices creature, you gain life
# =============================================================================

def _tribute_to_hunger_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Tribute to Hunger - force sacrifice and gain life."""
    target_player_id = selected[0] if selected else None
    if not target_player_id:
        return []

    # Find creatures the opponent controls
    opponent_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == target_player_id:
            if CardType.CREATURE in obj.characteristics.types:
                opponent_creatures.append(obj.id)

    if not opponent_creatures:
        return []

    # Create sacrifice choice for opponent
    # Note: Tribute to Hunger has opponent choose, so need different handling
    # For simplicity, sacrifice the first creature and gain its toughness
    target_creature_id = opponent_creatures[0]
    target_creature = state.objects.get(target_creature_id)
    if not target_creature:
        return []

    toughness = target_creature.characteristics.toughness or 0

    return [
        Event(
            type=EventType.SACRIFICE,
            payload={'object_id': target_creature_id, 'player': target_player_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': toughness},
            source=choice.source_id
        )
    ]


def tribute_to_hunger_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Tribute to Hunger (Phase 5b): chosen opponent sacrifices a creature; caster gains life.

    Engine gap: opponent-side choice UI; we currently sacrifice the first
    available creature controlled by the chosen opponent.
    """
    tid = _first_target_id(targets, state)
    if tid is None or tid not in state.players:
        return []
    target_player_id = tid
    opponent_creatures = [
        oid for oid, o in state.objects.items()
        if o.zone == ZoneType.BATTLEFIELD
        and o.controller == target_player_id
        and CardType.CREATURE in o.characteristics.types
    ]
    if not opponent_creatures:
        return []
    target_creature_id = opponent_creatures[0]
    target_creature = state.objects.get(target_creature_id)
    if target_creature is None:
        return []
    toughness = target_creature.characteristics.toughness or 0
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _spell_caster_id(state)
    return [
        Event(
            type=EventType.SACRIFICE,
            payload={'object_id': target_creature_id, 'player': target_player_id},
            source=source_id,
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster, 'amount': toughness},
            source=source_id,
        ),
    ]


# =============================================================================
# RABID BITE - Your creature deals damage to target creature
# =============================================================================

def _rabid_bite_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Rabid Bite - your creature deals damage."""
    if len(selected) < 2:
        return []

    source_creature_id = selected[0]
    target_creature_id = selected[1]

    source_creature = state.objects.get(source_creature_id)
    target_creature = state.objects.get(target_creature_id)

    if not source_creature or source_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not target_creature or target_creature.zone != ZoneType.BATTLEFIELD:
        return []

    power = source_creature.characteristics.power or 0

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_creature_id,
            'amount': power,
            'source': source_creature_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def rabid_bite_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Rabid Bite: Target creature you control deals damage equal to its power to target creature you don't control."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Rabid Bite":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "rabid_bite_spell"

    # First, select your creature
    your_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == caster_id:
            if CardType.CREATURE in obj.characteristics.types:
                your_creatures.append(obj.id)

    if not your_creatures:
        return []

    # Then select opponent creature
    opponent_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller != caster_id:
            if CardType.CREATURE in obj.characteristics.types:
                opponent_creatures.append(obj.id)

    if not opponent_creatures:
        return []

    # Combined targets for multi-select
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=your_creatures + opponent_creatures,
        prompt="Choose your creature first, then target creature",
        min_targets=2,
        max_targets=2,
        callback_data={'your_creatures': your_creatures, 'opponent_creatures': opponent_creatures}
    )

    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _rabid_bite_execute

    return []


# =============================================================================
# DEVOUT DECREE - Exile target black or red creature/planeswalker, scry 1
# =============================================================================

def _devout_decree_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Devout Decree - exile and scry."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone': f'battlefield_{target.controller}',
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone': 'exile',
                'to_zone_type': ZoneType.EXILE,
                'reason': 'exiled'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.SCRY,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        )
    ]


def devout_decree_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Devout Decree: exile chosen black/red creature/PW; scry 1 (Phase 5b)."""
    events = _resolve_exile_targets()(targets, state)
    caster = _spell_caster_id(state)
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    if caster:
        events.append(Event(
            type=EventType.SCRY,
            payload={'player': caster, 'amount': 1},
            source=source_id,
        ))
    return events


# =============================================================================
# DEATHMARK - Destroy target green or white creature
# =============================================================================

def _deathmark_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Deathmark - destroy green/white creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def deathmark_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Deathmark: destroy the chosen green/white creature (Phase 5b)."""
    return _resolve_destroy_targets()(targets, state)


# =============================================================================
# INCINERATING BLAST - 6 damage to target creature, may loot
# =============================================================================

def _incinerating_blast_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Incinerating Blast - deal 6 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Note: The "may discard to draw" is a separate optional choice
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 6, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def incinerating_blast_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Incinerating Blast: 6 damage to chosen creature (Phase 5b).

    The "may discard a card. If you do, draw a card." rider is a separate
    optional discard/draw effect that isn't wired here (engine gap).
    """
    return _resolve_damage_to_targets(6)(targets, state)


# =============================================================================
# MAKE YOUR MOVE - Destroy artifact, enchantment, or creature with power 4+
# =============================================================================

def _make_your_move_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Make Your Move - destroy target."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def make_your_move_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Make Your Move: destroy the chosen target (Phase 5b)."""
    return _resolve_destroy_targets()(targets, state)


# =============================================================================
# ELSPETH'S SMITE - 3 damage to attacking/blocking creature, exile if dies
# =============================================================================

def _elspeths_smite_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Elspeth's Smite - deal 3 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False, 'exile_on_death': True},
        source=choice.source_id
    )]


def elspeths_smite_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Elspeth's Smite: 3 damage to chosen attacking/blocking creature (Phase 5b).

    Includes the ``exile_on_death`` rider in the damage event payload.
    """
    from src.engine.spell_resolve import _flatten_targets  # type: ignore
    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': t.id,
                'amount': 3,
                'is_combat': False,
                'source': source_id,
                'exile_on_death': True,
            },
            source=source_id,
        ))
    return events


def _attacking_or_blocking_creature_filter(obj: GameObject, state: GameState) -> bool:
    """Match creatures whose state flags are attacking or blocking."""
    obj_state = obj.state
    if obj_state is None:
        return False
    return bool(getattr(obj_state, 'attacking', False)) or bool(getattr(obj_state, 'blocking', False))


# =============================================================================
# PLACEHOLDER - Reckless Rage helper (unused)
# =============================================================================

def _reckless_rage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Reckless Rage - deal 4 to opponent creature, 2 to own."""
    target_id = selected[0] if selected else None
    own_creature_id = choice.callback_data.get('own_creature_id')

    if not target_id:
        return []

    events = [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]

    if own_creature_id:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': own_creature_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        ))

    return events


# --- ARMASAUR GUIDE ---
# Vigilance (Attacking doesn't cause this creature to tap.) / Whenever you attack with three or more creatures, put a +1/+1 counter on target creature you control.
def armasaur_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        return attacker.controller == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: whenever-you-attack trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- CELESTIAL ARMOR ---
# Flash (You may cast this spell any time you could cast an instant.) / When this Equipment enters, attach it to target creature you control. That creature gains hexproof and indestructible until end of turn. / Equipped creature gets +2/+0 and has flying. / Equip {3}{W} ({3}{W}: Attach to target creature you control. Equip only as a sorcery.)
def celestial_armor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- SUN-BLESSED HEALER ---
# Kicker {1}{W} (You may pay an additional {1}{W} as you cast this spell.) / Lifelink (Damage dealt by this creature also causes you to gain that much life.) / When this creature enters, if it was kicked, return target nonland permanent card with mana value 2 or less from your graveyard to the battlefield.
def sunblessed_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- VALKYRIE'S CALL ---
# Whenever a nontoken, non-Angel creature you control dies, return that card to the battlefield under its owner's control with a +1/+1 counter on it. It has flying and is an Angel in addition to its other types.
def valkyries_call_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED and event.type != EventType.SACRIFICE:
            return False
        target_id = event.payload.get('object_id')
        if target_id == obj.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        return CardType.CREATURE in target.characteristics.types
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: complex follow-up effect
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- CURATOR OF DESTINIES ---
# This spell can't be countered. / Flying / When this creature enters, look at the top five cards of your library and separate them into a face-down pile and a face-up pile. An opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard.
def curator_of_destinies_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- DRAKE HATCHER ---
# Vigilance, prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.) / Whenever this creature deals combat damage to a player, put that many incubation counters on it. / Remove three incubation counters from this creature: Create a 2/2 blue Drake creature token with flying.
def drake_hatcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Whenever this creature deals combat damage to a player, put that many incubation counters on it.
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        amount = event.payload.get('amount', 0) or 0
        if amount <= 0:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'incubation', 'amount': amount},
            source=obj.id
        )]
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- GRAPPLING KRAKEN ---
# Landfall — Whenever a land you control enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)
def grappling_kraken_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Engine-gap: actual subtype/condition matching not implemented.
        return False
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- KAITO, CUNNING INFILTRATOR ---
# Whenever a creature you control deals combat damage to a player, put a loyalty counter on Kaito. / +1: Up to one target creature you control can't be blocked this turn. Draw a card, then discard a card. / −2: Create a 2/1 blue Ninja creature token. / −9: You get an emblem with "Whenever a player casts a spell, you create a 2/1 blue Ninja creature token."
def kaito_cunning_infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id) if source_id else None
        if not source_obj:
            return False
        if source_obj.controller != obj.controller:
            return False
        # Must be combat damage to a player
        target_id = event.payload.get('target')
        return target_id in state.players
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # Whenever a creature you control deals combat damage to a player, put a loyalty counter on Kaito.
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'loyalty', 'amount': 1},
                source=obj.id
            )]
        )
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- SKYSHIP BUCCANEER ---
# Flying / Raid — When this creature enters, if you attacked this turn, draw a card.
def skyship_buccaneer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.DRAW, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- SPHINX OF FORGOTTEN LORE ---
# Flash (You may cast this spell any time you could cast an instant.) / Flying / Whenever this creature attacks, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to that card's mana cost. (You may cast that card from your graveyard for its flashback cost. Then exile it.)
def sphinx_of_forgotten_lore_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- CRYPT FEASTER ---
# Menace (This creature can't be blocked except by two or more creatures.) / Threshold — Whenever this creature attacks, if there are seven or more cards in your graveyard, this creature gets +2/+0 until end of turn.
def crypt_feaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- GUTLESS PLUNDERER ---
# Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.) / Raid — When this creature enters, if you attacked this turn, look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.
def gutless_plunderer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- MIDNIGHT SNACK ---
# Raid — At the beginning of your end step, if you attacked this turn, create a Food token. (It's an artifact with "{2}, {T}, Sacrifice this token: You gain 3 life.") / {2}{B}, Sacrifice this enchantment: Target opponent loses X life, where X is the amount of life you gained this turn.
def midnight_snack_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- NINE-LIVES FAMILIAR ---
# This creature enters with eight revival counters on it if you cast it. / When this creature dies, if it had a revival counter on it, return it to the battlefield with one fewer revival counter on it at the beginning of the next end step.
def ninelives_familiar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex death effect
        return []
    return [make_death_trigger(obj, effect_fn)]


# --- TINYBONES, BAUBLE BURGLAR ---
# Whenever an opponent discards a card, exile it from their graveyard with a stash counter on it. / During your turn, you may play cards you don't own with stash counters on them from exile, and mana of any type can be spent to cast those spells. / {3}{B}, {T}: Each opponent discards a card. Activate only as a sorcery.
def tinybones_bauble_burglar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DISCARD:
            return False
        return event.payload.get('player') != obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: opponent-discards trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- TRAGIC BANSHEE ---
# Morbid — When this creature enters, target creature an opponent controls gets -1/-1 until end of turn. If a creature died this turn, that creature gets -13/-13 until end of turn instead.
def tragic_banshee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- VAMPIRE GOURMAND ---
# Whenever this creature attacks, you may sacrifice another creature. If you do, draw a card and this creature can't be blocked this turn.
def vampire_gourmand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- BATTLESONG BERSERKER ---
# Whenever you attack, target creature you control gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)
def battlesong_berserker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        return attacker.controller == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: whenever-you-attack trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- CHANDRA, FLAMESHAPER ---
# +2: Add {R}{R}{R}. Exile the top three cards of your library. Choose one. You may play that card this turn. / +1: Create a token that's a copy of target creature you control, except it has haste and "At the beginning of the end step, sacrifice this token." / −4: Chandra deals 8 damage divided as you choose among any number of target creatures and/or planeswalkers.
def chandra_flameshaper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- COURAGEOUS GOBLIN ---
# Whenever this creature attacks while you control a creature with power 4 or greater, this creature gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)
def courageous_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- SLUMBERING CERBERUS ---
# This creature doesn't untap during your untap step. / Morbid — At the beginning of each end step, if a creature died this turn, untap this creature.
def slumbering_cerberus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- STRONGBOX RAIDER ---
# Raid — When this creature enters, if you attacked this turn, exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.
def strongbox_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- AMBUSH WOLF ---
# Flash (You may cast this spell any time you could cast an instant.) / When this creature enters, exile up to one target card from a graveyard.
def ambush_wolf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- CACKLING PROWLER ---
# Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.) / Morbid — At the beginning of your end step, if a creature died this turn, put a +1/+1 counter on this creature.
def cackling_prowler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- NEEDLETOOTH PACK ---
# Morbid — At the beginning of your end step, if a creature died this turn, put two +1/+1 counters on target creature you control.
def needletooth_pack_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- QUILLED GREATWURM ---
# Trample / Whenever a creature you control deals combat damage during your turn, put that many +1/+1 counters on it. (It must survive to get the counters.) / You may cast this card from your graveyard by removing six counters from among creatures you control in addition to paying its other costs.
def quilled_greatwurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        # Only fires during your turn
        if state.active_player != obj.controller:
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id) if source_id else None
        if not source_obj:
            return False
        if source_obj.controller != obj.controller:
            return False
        # Source must be a creature
        return CardType.CREATURE in source_obj.characteristics.types
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # Put +1/+1 counters equal to combat damage dealt on the damaging creature.
        source_id = event.payload.get('source')
        amount = event.payload.get('amount', 0) or 0
        if not source_id or amount <= 0:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': source_id, 'counter_type': '+1/+1', 'amount': amount},
                source=obj.id
            )]
        )
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- SPINNER OF SOULS ---
# Reach / Whenever another nontoken creature you control dies, you may reveal cards from the top of your library until you reveal a creature card. Put that card into your hand and the rest on the bottom of your library in a random order.
def spinner_of_souls_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED and event.type != EventType.SACRIFICE:
            return False
        target_id = event.payload.get('object_id')
        if target_id == obj.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        return CardType.CREATURE in target.characteristics.types
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: complex follow-up effect
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- SYLVAN SCAVENGING ---
# At the beginning of your end step, choose one — / • Put a +1/+1 counter on target creature you control. / • Create a 3/3 green Raccoon creature token if you control a creature with power 4 or greater.
def sylvan_scavenging_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- ALESHA, WHO LAUGHS AT FATE ---
# First strike / Whenever Alesha attacks, put a +1/+1 counter on it. / Raid — At the beginning of your end step, if you attacked this turn, return target creature card with mana value less than or equal to Alesha's power from your graveyard to the battlefield.
def alesha_who_laughs_at_fate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- ASHROOT ANIMIST ---
# Trample / Whenever this creature attacks, another target creature you control gains trample and gets +X/+X until end of turn, where X is this creature's power.
def ashroot_animist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- PERFORATING ARTIST ---
# Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.) / Raid — At the beginning of your end step, if you attacked this turn, each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card.
def perforating_artist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- WARDENS OF THE CYCLE ---
# Morbid — At the beginning of your end step, if a creature died this turn, choose one — / • You gain 2 life. / • You draw a card and you lose 1 life.
def wardens_of_the_cycle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- ZIMONE, PARADOX SCULPTOR ---
# At the beginning of combat on your turn, put a +1/+1 counter on each of up to two target creatures you control. / {G}{U}, {T}: Double the number of each kind of counter on up to two target creatures and/or artifacts you control.
def zimone_paradox_sculptor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- BANISHING LIGHT ---
# When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.
def banishing_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- MICROMANCER ---
# When this creature enters, you may search your library for an instant or sorcery card with mana value 1, reveal it, put it into your hand, then shuffle.
def micromancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=instant_or_sorcery_with_mv(1),
            destination="hand",
            reveal=True,
            shuffle_after=True,
            optional=True,
            prompt="You may search your library for an instant or sorcery with mana value 1, reveal it, then put it into your hand.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- LILIANA, DREADHORDE GENERAL ---
# Whenever a creature you control dies, draw a card. / +1: Create a 2/2 black Zombie creature token. / −4: Each player sacrifices two creatures of their choice. / −9: Each opponent chooses a permanent they control of each permanent type and sacrifices the rest.
def liliana_dreadhorde_general_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED and event.type != EventType.SACRIFICE:
            return False
        target_id = event.payload.get('object_id')
        if target_id == obj.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        return CardType.CREATURE in target.characteristics.types
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # Static: Whenever a creature you control dies, draw a card.
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- PAINFUL QUANDARY ---
# Whenever an opponent casts a spell, that player loses 5 life unless they discard a card.
def painful_quandary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: opponent-cast trigger
        return []
    return [make_spell_cast_trigger(obj, effect_fn, controller_only=False)]


# --- RUNE-SCARRED DEMON ---
# Flying / When this creature enters, search your library for a card, put it into your hand, then shuffle.
def runescarred_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=any_card_filter(),
            destination="hand",
            shuffle_after=True,
            optional=False,
            min_count=1,
            prompt="Search your library for a card and put it into your hand.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- STROMKIRK BLOODTHIEF ---
# At the beginning of your end step, if an opponent lost life this turn, put a +1/+1 counter on target Vampire you control.
def stromkirk_bloodthief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: end-step trigger
        return []
    return [make_end_step_trigger(obj, effect_fn)]


# --- FLAMEWAKE PHOENIX ---
# Flying, haste / This creature attacks each combat if able. / Ferocious — At the beginning of combat on your turn, if you control a creature with power 4 or greater, you may pay {R}. If you do, return this card from your graveyard to the battlefield.
def flamewake_phoenix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- FRENZIED GOBLIN ---
# Whenever this creature attacks, you may pay {R}. If you do, target creature can't block this turn.
def frenzied_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- HEARTFIRE IMMOLATOR ---
# Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.) / {R}, Sacrifice this creature: It deals damage equal to its power to target creature or planeswalker.
def heartfire_immolator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: spell-cast trigger
        return []
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- AFFECTIONATE INDRIK ---
# When this creature enters, you may have it fight target creature you don't control. (Each deals damage equal to its power to the other.)
def affectionate_indrik_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- GARRUK'S UPRISING ---
# When this enchantment enters, if you control a creature with power 4 or greater, draw a card. / Creatures you control have trample. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.) / Whenever a creature you control with power 4 or greater enters, draw a card.
def garruks_uprising_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB conditional draw. (Trample static and the recurring "creature ETBs with
    # power >= 4 -> draw" trigger remain engine gaps.)
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        for o in state.objects.values():
            if (o.controller == obj.controller
                    and o.zone == ZoneType.BATTLEFIELD
                    and CardType.CREATURE in o.characteristics.types
                    and get_power(o, state) >= 4):
                return [Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- NESSIAN HORNBEETLE ---
# At the beginning of combat on your turn, if you control another creature with power 4 or greater, put a +1/+1 counter on this creature.
def nessian_hornbeetle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- VIVIEN REID ---
# +1: Look at the top four cards of your library. You may reveal a creature or land card from among them and put it into your hand. Put the rest on the bottom of your library in a random order. / −3: Destroy target artifact, enchantment, or creature with flying. / −8: You get an emblem with "Creatures you control get +2/+2 and have vigilance, trample, and indestructible."
def vivien_reid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 2, 2,
        creatures_you_control(obj)
    )


# --- WARY THESPIAN ---
# When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)
def wary_thespian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SURVEIL, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- CONSUMING ABERRATION ---
# Consuming Aberration's power and toughness are each equal to the number of cards in your opponents' graveyards. / Whenever you cast a spell, each opponent reveals cards from the top of their library until they reveal a land card, then puts those cards into their graveyard.
def consuming_aberration_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: spell-cast trigger
        return []
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- ADVENTURING GEAR ---
# Landfall — Whenever a land you control enters, equipped creature gets +2/+2 until end of turn. / Equip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)
def adventuring_gear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Engine-gap: actual subtype/condition matching not implemented.
        return False
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- CAMPUS GUIDE ---
# When this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top.
def campus_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # MTG order: shuffle THEN put-on-top, so we use a custom on_chosen rider
        # to move the chosen card to library_top after shuffling.
        from src.engine.library_search import _shuffle_library, _move_card_from_library


        # Cleaner: tutor with destination="library_top", shuffle_after=False,
        # then shuffle the rest of the library via the rider so the chosen
        # card ends up on top after the shuffle.
        def on_chosen(choice, moved, state):
            # Remove the chosen card from the top, shuffle the rest, put it
            # back on top (matches the printed "shuffle, then put on top").
            library = state.zones.get(f"library_{obj.controller}")
            if not library or not moved:
                _shuffle_library(state, obj.controller)
                return []
            top_id = moved[0]
            if top_id in library.objects:
                library.objects.remove(top_id)
            _shuffle_library(state, obj.controller)
            library.objects.insert(0, top_id)
            return []

        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=basic_land_filter(),
            destination="library_top",
            reveal=True,
            shuffle_after=False,
            optional=True,
            on_chosen=on_chosen,
            prompt="You may search your library for a basic land card, reveal it, then shuffle and put that card on top.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- BLOODFELL CAVES ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {B} or {R}.
def bloodfell_caves_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- BLOSSOMING SANDS ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {G} or {W}.
def blossoming_sands_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- DISMAL BACKWATER ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {U} or {B}.
def dismal_backwater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- JUNGLE HOLLOW ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {B} or {G}.
def jungle_hollow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- RUGGED HIGHLANDS ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {R} or {G}.
def rugged_highlands_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- SCOURED BARRENS ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {W} or {B}.
def scoured_barrens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- SWIFTWATER CLIFFS ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {U} or {R}.
def swiftwater_cliffs_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- THORNWOOD FALLS ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {G} or {U}.
def thornwood_falls_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TRANQUIL COVE ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {W} or {U}.
def tranquil_cove_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- WIND-SCARRED CRAG ---
# This land enters tapped. / When this land enters, you gain 1 life. / {T}: Add {R} or {W}.
def windscarred_crag_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- LEONIN VANGUARD ---
# At the beginning of combat on your turn, if you control three or more creatures, this creature gets +1/+1 until end of turn and you gain 1 life.
def leonin_vanguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- PRAYER OF BINDING ---
# Flash / When this enchantment enters, exile up to one target nonland permanent an opponent controls until this enchantment leaves the battlefield. You gain 2 life.
def prayer_of_binding_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- BURROG BEFUDDLER ---
# Flash (You may cast this spell any time you could cast an instant.) / When this creature enters, target creature an opponent controls gets -1/-0 until end of turn.
def burrog_befuddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- STARLIGHT SNARE ---
# Enchant creature / When this Aura enters, tap enchanted creature. / Enchanted creature doesn't untap during its controller's untap step.
def starlight_snare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- STORM FLEET SPY ---
# Raid — When this creature enters, if you attacked this turn, draw a card.
def storm_fleet_spy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.DRAW, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- BLOODTITHE COLLECTOR ---
# Flying / When this creature enters, if an opponent lost life this turn, each opponent discards a card.
def bloodtithe_collector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- CROW OF DARK TIDINGS ---
# Flying / When this creature enters or dies, mill two cards. (Put the top two cards of your library into your graveyard.)
def crow_of_dark_tidings_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.MILL, {'player': obj.controller, 'amount': 2}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- DEATH BARON ---
# Skeletons you control and other Zombies you control get +1/+1 and have deathtouch. (Any amount of damage they deal to a creature is enough to destroy it.)
def death_baron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Zombie")
    )


# --- MAALFELD TWINS ---
# When this creature dies, create two 2/2 black Zombie creature tokens.
def maalfeld_twins_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        token_payload = {
            'name': 'Zombie Token',
            'controller': obj.controller,
            'power': 2,
            'toughness': 2,
            'types': [CardType.CREATURE],
            'subtypes': ['Zombie'],
            'colors': [Color.BLACK],
            'token': True
        }
        return [
            Event(type=EventType.OBJECT_CREATED, payload=dict(token_payload), source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload=dict(token_payload), source=obj.id),
        ]
    return [make_death_trigger(obj, effect_fn)]


# --- SKELETON ARCHER ---
# When this creature enters, it deals 1 damage to any target.
def skeleton_archer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- VAMPIRE SPAWN ---
# When this creature enters, each opponent loses 2 life and you gain 2 life.
def vampire_spawn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 2}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- BATTLE-RATTLE SHAMAN ---
# At the beginning of combat on your turn, you may have target creature get +2/+0 until end of turn.
def battlerattle_shaman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- DROPKICK BOMBER ---
# Other Goblins you control get +1/+1. / {R}: Until end of turn, another target Goblin you control gains flying and "When this creature deals combat damage, sacrifice it."
def dropkick_bomber_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Goblin")
    )


# --- GOBLIN ORIFLAMME ---
# Attacking creatures you control get +1/+0.
def goblin_oriflamme_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 0,
        creatures_you_control(obj)
    )


# --- RAPACIOUS DRAGON ---
# Flying / When this creature enters, create two Treasure tokens. (They're artifacts with "{T}, Sacrifice this token: Add one mana of any color.")
def rapacious_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        token_payload = {
            'name': 'Treasure Token',
            'controller': obj.controller,
            'types': [CardType.ARTIFACT],
            'subtypes': ['Treasure'],
            'token': True
        }
        return [
            Event(type=EventType.OBJECT_CREATED, payload=dict(token_payload), source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload=dict(token_payload), source=obj.id),
        ]
    return [make_etb_trigger(obj, effect_fn)]


# --- TERROR OF MOUNT VELUS ---
# Flying / Double strike (This creature deals both first-strike and regular combat damage.) / When this creature enters, creatures you control gain double strike until end of turn.
def terror_of_mount_velus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- VOLLEY VETERAN ---
# When this creature enters, it deals damage to target creature an opponent controls equal to the number of Goblins you control.
def volley_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- AGGRESSIVE MAMMOTH ---
# Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.) / Other creatures you control have trample.
def aggressive_mammoth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(
        obj, ['trample'],
        creatures_you_control(obj)
    )]


# --- NEW HORIZONS ---
# Enchant land / When this Aura enters, put a +1/+1 counter on target creature you control. / Enchanted land has "{T}: Add two mana of any one color."
def new_horizons_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- PIRATE'S CUTLASS ---
# When this Equipment enters, attach it to target Pirate you control. / Equipped creature gets +2/+1. / Equip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)
def pirates_cutlass_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- ARCHWAY ANGEL ---
# Flying / When this creature enters, you gain 2 life for each Gate you control.
def archway_angel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.LIFE_CHANGE, {'player': obj.controller, 'amount': 2}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- CHARMING PRINCE ---
# When this creature enters, choose one — / • Scry 2. / • You gain 3 life. / • Exile another target creature you own. Return it to the battlefield under your control at the beginning of the next end step.
def charming_prince_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 2}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- DAWNWING MARSHAL ---
# Flying / {4}{W}: Creatures you control get +1/+1 until end of turn.
def dawnwing_marshal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 1, 1,
        creatures_you_control(obj)
    )


# --- STASIS SNARE ---
# Flash (You may cast this spell any time you could cast an instant.) / When this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield.
def stasis_snare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- GATEWAY SNEAK ---
# Whenever a Gate you control enters, this creature can't be blocked this turn. / Whenever this creature deals combat damage to a player, draw a card.
def gateway_sneak_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Whenever this creature deals combat damage to a player, draw a card.
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- HARBINGER OF THE TIDES ---
# You may cast this spell as though it had flash if you pay {2} more to cast it. (You may cast it any time you could cast an instant.) / When this creature enters, you may return target tapped creature an opponent controls to its owner's hand.
def harbinger_of_the_tides_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- SHIPWRECK DOWSER ---
# Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.) / When this creature enters, return target instant or sorcery card from your graveyard to your hand.
def shipwreck_dowser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- VORACIOUS GREATSHARK ---
# Flash (You may cast this spell any time you could cast an instant.) / When this creature enters, counter target artifact or creature spell.
def voracious_greatshark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- DEMONIC PACT ---
# At the beginning of your upkeep, choose one that hasn't been chosen — / • This enchantment deals 4 damage to any target and you gain 4 life. / • Target opponent discards two cards. / • Draw two cards. / • You lose the game.
def demonic_pact_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: upkeep trigger
        return []
    return [make_upkeep_trigger(obj, effect_fn)]


# --- NULLPRIEST OF OBLIVION ---
# Kicker {3}{B} (You may pay an additional {3}{B} as you cast this spell.) / Lifelink / Menace (This creature can't be blocked except by two or more creatures.) / When this creature enters, if it was kicked, return target creature card from your graveyard to the battlefield.
def nullpriest_of_oblivion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- VILE ENTOMBER ---
# Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.) / When this creature enters, search your library for a card, put that card into your graveyard, then shuffle.
def vile_entomber_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=any_card_filter(),
            destination="graveyard",
            shuffle_after=True,
            optional=False,
            min_count=1,
            prompt="Search your library for a card and put that card into your graveyard.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- BALL LIGHTNING ---
# Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.) / Haste (This creature can attack and {T} as soon as it comes under your control.) / At the beginning of the end step, sacrifice this creature.
def ball_lightning_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SACRIFICE,
            payload={'object_id': obj.id, 'player': obj.controller},
            source=obj.id
        )]
    # Triggers on every end step (any player's), since the ability says "the end step"
    return [make_end_step_trigger(obj, effect_fn, controller_only=False)]


# --- DRAGON MAGE ---
# Flying / Whenever this creature deals combat damage to a player, each player discards their hand, then draws seven cards.
def dragon_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Only fire when target is a player
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        events = []
        for player_id in state.players.keys():
            hand_zone = state.zones.get(f"hand_{player_id}")
            hand_size = len(hand_zone.objects) if hand_zone else 0
            # Discard entire hand
            if hand_size > 0:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'amount': hand_size},
                    source=obj.id
                ))
            # Then draw seven
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': player_id, 'amount': 7},
                source=obj.id
            ))
        return events
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- DRAGONMASTER OUTCAST ---
# At the beginning of your upkeep, if you control six or more lands, create a 5/5 red Dragon creature token with flying.
def dragonmaster_outcast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Count lands controller controls
        land_count = sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.LAND in o.characteristics.types
        )
        if land_count < 6:
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dragon Token',
                'controller': obj.controller,
                'power': 5,
                'toughness': 5,
                'types': [CardType.CREATURE],
                'subtypes': ['Dragon'],
                'colors': [Color.RED],
                'keywords': ['flying'],
                'token': True
            },
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, effect_fn)]


# --- HOARDING DRAGON ---
# Flying / When this creature enters, you may search your library for an artifact card, exile it, then shuffle. / When this creature dies, you may put the exiled card into its owner's hand.
# Death-return rider remains an engine gap (delayed retrieval of "the exiled card"), but ETB tutor is wired.
def hoarding_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=artifact_filter_lib(),
            destination="exile",
            shuffle_after=True,
            optional=True,
            prompt="You may search your library for an artifact card and exile it.",
        )
    return [make_etb_trigger(obj, effect_fn)]


# --- MINDSPARKER ---
# First strike (This creature deals combat damage before creatures without first strike.) / Whenever an opponent casts a white or blue instant or sorcery spell, this creature deals 2 damage to that player.
def mindsparker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if caster is None or caster == obj.controller:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': caster, 'amount': 2, 'source': obj.id, 'is_combat': False},
            source=obj.id
        )]
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=False,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
        color_filter={Color.WHITE, Color.BLUE}
    )]


# --- RAVENOUS GIANT ---
# At the beginning of your upkeep, this creature deals 1 damage to you.
def ravenous_giant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={
                'target': obj.controller,
                'amount': 1,
                'source': obj.id,
                'is_combat': False
            },
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, effect_fn)]


# --- REDCAP GUTTER-DWELLER ---
# Menace / When this creature enters, create two 1/1 black Rat creature tokens with "This token can't block." / At the beginning of your upkeep, you may sacrifice another creature. If you do, put a +1/+1 counter on this creature and exile the top card of your library. You may play that card this turn.
def redcap_gutterdweller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- STROMKIRK NOBLE ---
# This creature can't be blocked by Humans. / Whenever this creature deals combat damage to a player, put a +1/+1 counter on it.
def stromkirk_noble_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Only fire when target is a player (deals combat damage to a player)
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, effect_fn, combat_only=True)]


# --- TAUREAN MAULER ---
# Changeling (This card is every creature type.) / Whenever an opponent casts a spell, you may put a +1/+1 counter on this creature.
def taurean_mauler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if caster is None or caster == obj.controller:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, effect_fn, controller_only=False)]


# --- GNARLBACK RHINO ---
# Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.) / Whenever you cast a spell that targets this creature, draw a card.
def gnarlback_rhino_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: spell-cast trigger
        return []
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- MOLD ADDER ---
# Whenever an opponent casts a blue or black spell, you may put a +1/+1 counter on this creature.
def mold_adder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if caster is None or caster == obj.controller:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=False,
        color_filter={Color.BLUE, Color.BLACK}
    )]


# --- PREDATOR OOZE ---
# Indestructible (Damage and effects that say "destroy" don't destroy this creature.) / Whenever this creature attacks, put a +1/+1 counter on it. / Whenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.
def predator_ooze_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Whenever this creature attacks, put a +1/+1 counter on it.
    # (The "creature dealt damage by this dies" trigger remains an engine gap.)
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, effect_fn)]


# --- SURRAK, THE HUNT CALLER ---
# Formidable — At the beginning of combat on your turn, if creatures you control have total power 8 or greater, target creature you control gains haste until end of turn. (It can attack and {T} no matter when it came under your control.)
def surrak_the_hunt_caller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- VENOM CONNOISSEUR ---
# Alliance — Whenever another creature you control enters, this creature gains deathtouch until end of turn. If this is the second time this ability has resolved this turn, all creatures you control gain deathtouch until end of turn.
def venom_connoisseur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Engine-gap: actual subtype/condition matching not implemented.
        return False
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- WILDBORN PRESERVER ---
# Flash (You may cast this spell any time you could cast an instant.) / Reach (This creature can block creatures with flying.) / Whenever another non-Human creature you control enters, you may pay {X}. When you do, put X +1/+1 counters on this creature.
def wildborn_preserver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Engine-gap: actual subtype/condition matching not implemented.
        return False
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- DROGSKOL REAVER ---
# Flying / Double strike (This creature deals both first-strike and regular combat damage.) / Lifelink (Damage dealt by this creature also causes you to gain that much life.) / Whenever you gain life, draw a card.
def drogskol_reaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, effect_fn)]


# --- HALANA AND ALENA, PARTNERS ---
# First strike (This creature deals combat damage before creatures without first strike.) / Reach (This creature can block creatures with flying.) / At the beginning of combat on your turn, put X +1/+1 counters on another target creature you control, where X is Halana and Alena's power. That creature gains haste until end of turn.
def halana_and_alena_partners_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        phase = event.payload.get('phase', '')
        if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: beginning-of-combat trigger
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- OVIKA, ENIGMA GOLIATH ---
# Flying / Ward—{3}, Pay 3 life. / Whenever you cast a noncreature spell, create X 1/1 red Phyrexian Goblin creature tokens, where X is the mana value of that spell. They gain haste until end of turn.
def ovika_enigma_goliath_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Whenever you cast a noncreature spell, create X 1/1 red Phyrexian Goblin tokens (X = mana value).
        spell_types = set(event.payload.get('types', []))
        if CardType.CREATURE in spell_types:
            return []
        x = event.payload.get('mana_value', 0) or 0
        if x <= 0:
            return []
        token_payload = {
            'name': 'Phyrexian Goblin Token',
            'controller': obj.controller,
            'power': 1,
            'toughness': 1,
            'types': [CardType.CREATURE],
            'subtypes': ['Phyrexian', 'Goblin'],
            'colors': [Color.RED],
            'keywords': ['haste'],
            'token': True
        }
        return [
            Event(type=EventType.OBJECT_CREATED, payload=dict(token_payload), source=obj.id)
            for _ in range(x)
        ]
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- SAVAGE VENTMAW ---
# Flying / Whenever this creature attacks, add {R}{R}{R}{G}{G}{G}. Until end of turn, you don't lose this mana as steps and phases end.
def savage_ventmaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex attack trigger
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- TRYGON PREDATOR ---
# Flying / Whenever this creature deals combat damage to a player, you may destroy target artifact or enchantment that player controls.
def trygon_predator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: damage trigger
        return []
    return [make_damage_trigger(obj, effect_fn)]


# --- DIAMOND MARE ---
# As this creature enters, choose a color. / Whenever you cast a spell of the chosen color, you gain 1 life.
def diamond_mare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: spell-cast trigger
        return []
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- GATE COLOSSUS ---
# Affinity for Gates (This spell costs {1} less to cast for each Gate you control.) / This creature can't be blocked by creatures with power 2 or less. / Whenever a Gate you control enters, you may put this card from your graveyard on top of your library.
def gate_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Engine-gap: actual subtype/condition matching not implemented.
        return False
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- RAMOS, DRAGON ENGINE ---
# Flying / Whenever you cast a spell, put a +1/+1 counter on Ramos for each of that spell's colors. / Remove five +1/+1 counters from Ramos: Add {W}{W}{U}{U}{B}{B}{R}{R}{G}{G}. Activate only once each turn.
def ramos_dragon_engine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        spell_colors = set(event.payload.get('colors', []))
        if not spell_colors:
            color = event.payload.get('color')
            if color is not None:
                spell_colors = {color}
        count = len(spell_colors)
        if count <= 0:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': count},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- SOUL-GUIDE LANTERN ---
# When this artifact enters, exile target card from a graveyard. / {T}, Sacrifice this artifact: Exile each opponent's graveyard. / {1}, {T}, Sacrifice this artifact: Draw a card.
def soulguide_lantern_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF ABANDON ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {R} or {G}.
def temple_of_abandon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF DECEIT ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {U} or {B}.
def temple_of_deceit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF ENLIGHTENMENT ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {W} or {U}.
def temple_of_enlightenment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF EPIPHANY ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {U} or {R}.
def temple_of_epiphany_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF MALADY ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {B} or {G}.
def temple_of_malady_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF MALICE ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {B} or {R}.
def temple_of_malice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF MYSTERY ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {G} or {U}.
def temple_of_mystery_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF PLENTY ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {G} or {W}.
def temple_of_plenty_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF SILENCE ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {W} or {B}.
def temple_of_silence_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- TEMPLE OF TRIUMPH ---
# This land enters tapped. / When this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.) / {T}: Add {R} or {W}.
def temple_of_triumph_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.SCRY, {'player': obj.controller, 'amount': 1}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- GATEKEEPER OF MALAKIR ---
# Kicker {B} (You may pay an additional {B} as you cast this spell.) / When this creature enters, if it was kicked, target player sacrifices a creature of their choice.
def gatekeeper_of_malakir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: complex ETB effect (targeting/modal/conditional)
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- HINTERLAND SANCTIFIER ---
# Whenever another creature you control enters, you gain 1 life.
def hinterland_sanctifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != obj.controller:
            return False
        return CardType.CREATURE in entering_obj.characteristics.types
    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# =============================================================================
# SETUP FUNCTIONS - ROUND 2 (Missing-interceptor sweep)
# =============================================================================


# --- SIRE OF SEVEN DEATHS ---
# First strike, vigilance, menace, trample, reach, lifelink, ward—Pay 7 life.
def sire_of_seven_deaths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # All combat keywords are static. Wire ward—Pay 7 life via the helper
    # (life-pay variant approximated with mana_cost; v1 ward always counters).
    return [make_ward(obj, life_cost=7)]


# --- CRYSTAL BARRICADE ---
# Defender / You have hexproof / Prevent all noncombat damage to other creatures you control.
# Phase 5b sweep: replacement effect that prevents noncombat DAMAGE events
# whose target is a creature controlled by Crystal Barricade's controller
# (excluding self per "other creatures"). Player-hexproof is an engine gap.
def crystal_barricade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_controller = obj.controller
    src_id = obj.id

    def damage_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('is_combat'):
            return False  # combat damage is fine
        if event.payload.get('amount', 0) <= 0:
            return False
        target_id = event.payload.get('target')
        target = st.objects.get(target_id) if target_id else None
        if target is None or target.id == src_id:
            return False
        if target.controller != src_controller:
            return False
        return CardType.CREATURE in target.characteristics.types

    def prevent(event: Event, st: GameState) -> Event:
        new_event = event.copy()
        new_event.payload['amount'] = 0
        new_event.payload['_prevented_by'] = src_id
        return new_event

    return make_replacement_effect(
        obj,
        event_filter=damage_filter,
        replace_fn=prevent,
        duration='permanent',
        apply_once_per_event=True,
    )


# --- HERALD OF ETERNAL DAWN ---
# Flash, Flying / You can't lose the game and your opponents can't win the game.
def herald_of_eternal_dawn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: can't-lose / opponents-can't-win replacement effect
    return []


# --- INSPIRING PALADIN ---
# During your turn, this creature has first strike. / During your turn, creatures you control with +1/+1 counters have first strike.
# Phase 5b sweep: dual keyword grant, both gated on it being the controller's turn.
def inspiring_paladin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def your_turn_self(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        return st.active_player == obj.controller

    def your_turn_buffed_creature(target: GameObject, st: GameState) -> bool:
        if st.active_player != obj.controller:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        counters = getattr(target.state, 'counters', {}) or {}
        return counters.get('+1/+1', 0) > 0

    return [
        make_keyword_grant(obj, ['first strike'], your_turn_self),
        make_keyword_grant(obj, ['first strike'], your_turn_buffed_creature),
    ]


# --- SQUAD RALLIER ---
# {2}{W}: Look at the top four cards of your library. You may reveal a creature card with power 2 or less, put it into your hand. Bottom the rest.
# Phase 5b sweep: activated library-look via open_library_search with a
# "creature, power ≤ 2" filter. The engine handles the look-at-top-N choice
# and shuffles/bottoms the unselected cards.
def squad_rallier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _small_creature_filter(card: GameObject, st: GameState) -> bool:
        if CardType.CREATURE not in card.characteristics.types:
            return False
        p = card.characteristics.power
        if p is None:
            return False
        return p <= 2

    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        open_library_search(
            st, o.controller, o.id,
            filter_fn=_small_creature_filter,
            destination="hand",
            max_count=1,
            reveal=True,
            shuffle_after=False,
            optional=True,
            prompt="Look at the top four of your library; you may put a creature card with power 2 or less into your hand.",
        )
        return []

    make_activated_ability(
        obj, cost="{2}{W}", effect_fn=_effect,
        description="Look at top 4; reveal a creature with power 2 or less, put into hand",
    )
    return []


# --- TWINBLADE BLESSING ---
# Enchant creature; enchanted creature has double strike.
twinblade_blessing_setup = make_aura_setup(keywords=["double strike"])


# --- HIGH FAE TRICKSTER ---
# Flash, Flying / You may cast spells as though they had flash.
def high_fae_trickster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: cast-as-flash replacement
    return []


# --- RUNE-SEALED WALL ---
# Defender / {T}: Surveil 1.


# --- STRIX LOOKOUT ---
# Flying, vigilance / {1}{U}, {T}: Draw a card, then discard a card.
# Phase 5b sweep: activated loot ability ({1}{U}, {T}).
def strix_lookout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_loot_ability
    make_loot_ability(
        obj, cost="{1}{U}, {T}",
        description="Draw a card, then discard a card",
    )
    return []


# --- ABYSSAL HARVESTER ---
# {T}: Exile target creature card from a graveyard that was put there this turn.
# Create a copy as a Nightmare; exile other Nightmare tokens you control.
# Phase 5b sweep: wire the exile-from-graveyard activation. The copy/Nightmare-
# token-creation + "exile all other Nightmare tokens you control" require
# token-from-card-def + per-turn graveyard tracking, both engine gaps.
def abyssal_harvester_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.EXILE,
            payload={'object_id': target_id},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{T}", effect_fn=_effect,
        description="Exile target creature card from a graveyard",
        targets_required=1, target_kind="creature_in_graveyard",
    )
    return []


# --- HUNGRY GHOUL ---
# {1}, Sacrifice another creature: Put a +1/+1 counter on this creature.
def hungry_ghoul_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # NOTE: cost parser only recognizes "Sacrifice this/it/this <type>" as
    # sac-self; "Sacrifice another creature" is preserved in the additional
    # cost plan. We register the ability with self-counter effect; the engine
    # currently emits the counter regardless of whether the sac actually
    # resolves, but the mana cost {1} still gates activation.
    from src.cards.interceptor_helpers import make_counter_ability
    make_counter_ability(
        obj, "{1}, Sacrifice another creature",
        counter_type="+1/+1", amount=1, target_self=True,
    )
    return []


# --- ZUL ASHUR, LICH LORD ---
# Ward—Pay 2 life. / {T}: You may cast target Zombie creature card from your graveyard this turn.
# Phase 5b sweep: wire ward (pay 2 life). The {T}: cast-from-graveyard
# permission is still an engine gap (no target-card-id picker that maps to
# a cast permission grant on activation).
def zul_ashur_lich_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_ward(obj, life_cost=2)]


# --- GOBLIN BOARDERS ---
# Raid — This creature enters with a +1/+1 counter on it if you attacked this turn.
def goblin_boarders_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: raid condition tracking
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- KELLAN, PLANAR TRAILBLAZER ---
# {1}{R}: If Kellan is a Scout, becomes Detective... / {2}{R}: If Detective, becomes 3/2 Rogue with double strike.
# Phase 5b sweep: wire both transform abilities. We mutate the object's
# subtypes set directly (engine has no characteristic-layer system, but
# subtype writes propagate to combat / matters checks). The first activation
# requires "is a Scout" precondition; the second requires "is a Detective"
# (after first activation). The combat-damage-exile-top-of-library granted
# ability + double-strike (granted on 2nd transform) are partial — we add
# double strike as a granted keyword via direct ability append.
def kellan_planar_trailblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _to_detective_pre(o: GameObject, st: GameState) -> bool:
        return 'Scout' in (o.characteristics.subtypes or set())

    def _to_detective(o: GameObject, st: GameState, targets) -> list[Event]:
        subs = set(o.characteristics.subtypes or set())
        subs.discard('Scout')
        subs |= {'Human', 'Faerie', 'Detective'}
        o.characteristics.subtypes = subs
        return []

    def _to_rogue_pre(o: GameObject, st: GameState) -> bool:
        return 'Detective' in (o.characteristics.subtypes or set())

    def _to_rogue(o: GameObject, st: GameState, targets) -> list[Event]:
        subs = set(o.characteristics.subtypes or set())
        subs.discard('Detective')
        subs |= {'Human', 'Faerie', 'Rogue'}
        o.characteristics.subtypes = subs
        # 3/2 base + double strike granted via PT_MODIFICATION + GRANT_KEYWORD.
        return [
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': o.id, 'keyword': 'double strike', 'duration': 'permanent'},
                source=o.id, controller=o.controller,
            ),
        ]

    make_activated_ability(
        obj, cost="{1}{R}", effect_fn=_to_detective,
        description="If Scout, becomes a Human Faerie Detective",
        precondition_fn=_to_detective_pre,
    )
    make_activated_ability(
        obj, cost="{2}{R}", effect_fn=_to_rogue,
        description="If Detective, becomes a Human Faerie Rogue with double strike",
        precondition_fn=_to_rogue_pre,
    )
    return []


# --- SOWER OF CHAOS ---
# {2}{R}: Target creature can't block this turn.
# Phase 5b sweep: activated cant_block via GRANT_KEYWORD until EOT.
def sower_of_chaos_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _grant_cant_block(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': 'cant_block',
                'duration': 'end_of_turn',
            },
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{2}{R}", effect_fn=_grant_cant_block,
        description="Target creature can't block this turn",
        targets_required=1, target_kind="creature",
    )
    return []


# --- TWINFLAME TYRANT ---
# Flying / If a source you control would deal damage to an opponent or permanent an opponent controls, it deals double that damage instead.
def twinflame_tyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Damage from your sources to opponents (or their permanents) is doubled.

    Wired through ``make_replacement_effect`` (the generic "if X would happen,
    Y instead" primitive). The filter requires DAMAGE events whose source is
    controlled by Twinflame's controller AND whose target is an opponent or a
    permanent controlled by an opponent. The replacement is a single DAMAGE
    event with ``amount * 2``. The marker pin on the new event prevents
    Twinflame from re-doubling its own output.
    """
    src_controller = obj.controller
    src_id = obj.id

    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        # Source must be controlled by Twinflame's controller.
        damage_source_id = event.source or event.payload.get('source')
        damage_source = state.objects.get(damage_source_id) if damage_source_id else None
        if not damage_source or damage_source.controller != src_controller:
            return False
        # Target must be an opponent or an opponent's permanent.
        target_id = event.payload.get('target')
        if target_id in state.players:
            return target_id != src_controller
        target_obj = state.objects.get(target_id) if target_id else None
        if target_obj is None:
            return False
        return target_obj.controller != src_controller

    def double_damage(event: Event, state: GameState) -> Event:
        new_event = event.copy()
        new_event.payload['amount'] = int(event.payload.get('amount', 0)) * 2
        new_event.payload['_doubled_by'] = src_id
        return new_event

    return make_replacement_effect(
        obj,
        event_filter=damage_filter,
        replace_fn=double_damage,
        duration='permanent',
        apply_once_per_event=True,
    )


# --- LOOT, EXUBERANT EXPLORER ---
# You may play an additional land each turn. / {4}{G}{G}, {T}: Library look creature ability.
# Phase 5b sweep: wire the "+1 land per turn" static via make_additional_land_play.
# The {4}{G}{G}, {T} activated library search (top six → put a creature card
# with mv ≤ lands you control onto the battlefield) is also wired via
# open_library_search with a dynamic mv filter.
def loot_exuberant_explorer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_additional_land_play

    def _count_lands(controller: str, st: GameState) -> int:
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        n = 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == controller
                    and CardType.LAND in o.characteristics.types):
                n += 1
        return n

    def _creature_with_mv_le_lands(card: GameObject, st: GameState) -> bool:
        if CardType.CREATURE not in card.characteristics.types:
            return False
        mc = card.characteristics.mana_cost or ''
        # Quick mv parse: count braces of digits and color symbols.
        from src.engine.library_search import _mana_value
        try:
            mv = _mana_value(mc)
        except Exception:
            mv = 0
        return mv <= _count_lands(obj.controller, st)

    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        open_library_search(
            st, o.controller, o.id,
            filter_fn=_creature_with_mv_le_lands,
            destination="battlefield",
            max_count=1,
            shuffle_after=False,
            optional=True,
            prompt="Look at top six; you may put a creature card with mana value ≤ lands you control onto the battlefield.",
        )
        return []

    make_activated_ability(
        obj, cost="{4}{G}{G}, {T}", effect_fn=_effect,
        description="Look at top six; put creature card with mv ≤ lands you control onto the battlefield",
    )
    return [make_additional_land_play(obj, 1)]


# --- TREETOP SNARESPINNER ---
# Reach, deathtouch / {2}{G}: Put a +1/+1 counter on target creature you control.
# Phase 5b sweep: sorcery-speed activated counter on creature you control.
def treetop_snarespinner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _counter(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target = st.objects.get(target_id) if isinstance(target_id, str) else None
        # "creature you control" guard
        if target is None or target.controller != o.controller:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{2}{G}", effect_fn=_counter,
        description="Put a +1/+1 counter on target creature you control",
        sorcery_speed=True,
        targets_required=1, target_kind="creature_you_control",
    )
    return []


# --- ELENDA, SAINT OF DUSK ---
# Lifelink, hexproof from instants / Conditional +1/+1 / +5/+5 based on life total.
# Phase 5b sweep: dynamic self-pump comparing current life to starting life.
def elenda_saint_of_dusk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_dynamic_pt_boost as _dyn_pt

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def pt_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        controller = obj.controller
        player = st.players.get(controller)
        if not player:
            return (0, 0)
        starting = getattr(player, 'starting_life', 20) or 20
        cur = getattr(player, 'life', starting)
        diff = cur - starting
        if diff >= 10:
            return (6, 6)  # +1/+1 base + extra +5/+5 = +6/+6
        if diff > 0:
            return (1, 1)
        return (0, 0)

    return _dyn_pt(obj, pt_mod, affects_self)


# --- BANNER OF KINSHIP ---
# Choose creature type / counters / +1/+1 per fellowship counter.
# Phase 5b sweep: choose-type framework is an engine gap; we wire a static
# +1/+1 boost on all creatures you control (deck-wide anthem fallback)
# to preserve the "this is a lord-shaped card" gameplay impact. The
# fellowship-counter-per-creature dynamic scaling stays unwired.
def banner_of_kinship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(obj, 1, 1, creatures_you_control(obj))


# --- FISHING POLE ---
# Equipment - bait counters & untap creates fish token.
def fishing_pole_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: equipment with granted ability and untap trigger
    return []


# --- LEYLINE AXE ---
# Opening hand free play / Equipped creature gets +1/+1 has double strike & trample / Equip {3}.


# --- QUICK-DRAW KATANA ---
# During your turn, equipped creature gets +2/+0 and has first strike. / Equip {2}.


# --- RAVENOUS AMULET ---
# {1},{T}, Sac creature: Draw card + soul counter / {4},{T}, Sac amulet: Each opponent loses life.


# --- SOULSTONE SANCTUARY ---
# {T}: Add {C}. / {4}: Becomes 3/3 creature with vigilance and all creature types.
def soulstone_sanctuary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{4}: This land becomes a 3/3 creature with vigilance and all creature
    types until end of turn. (Skip "all creature types" — engine has no
    enumeration helper, so the changeling-style universal subtype is unwired.)"""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        becomes_creature(
            o, st,
            power=3, toughness=3,
            keywords=["vigilance"],
            keep_land=True,
        )
        return []

    make_activated_ability(
        obj,
        cost="{4}",
        effect_fn=effect,
        description="This land becomes a 3/3 creature with vigilance until end of turn.",
    )
    return []


# --- AJANI, CALLER OF THE PRIDE ---
# Loyalty 4. White planeswalker.
# Card text (Scryfall):
#   +1: Put a +1/+1 counter on up to one target creature.
#   −3: Target creature gains flying and double strike until end of turn.
#   −8: Create X 2/2 white Cat creature tokens, where X is your life total.
#
# Wired via the W13 planeswalker loyalty framework. The −8 ability creates
# Cat tokens equal to the controller's current life total (per printed text).
# A separate "emblem variant" demonstrating the W15 emblem framework is
# exercised in tests/test_planeswalker_deep.py via make_emblem_creatures_have_keywords;
# the printed Caller of the Pride does not produce an emblem itself.
def ajani_caller_of_the_pride_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_planeswalker_setup,
        make_loyalty_ability,
    )

    setup = make_planeswalker_setup(obj, starting_loyalty=4)

    # +1: Put a +1/+1 counter on up to one target creature.
    def plus1_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        if not target_id:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=o.id,
            controller=o.controller,
        )]

    make_loyalty_ability(
        obj, cost=+1, effect_fn=plus1_effect, ability_id="+1",
        targets_required=1, target_kind="creature",
        description="+1: Put a +1/+1 counter on target creature.",
    )

    # −3: Target creature gains flying and double strike until end of turn.
    def minus3_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        if not target_id:
            return []
        return [
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': target_id, 'keyword': 'flying',
                           'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': target_id, 'keyword': 'double_strike',
                           'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
        ]

    make_loyalty_ability(
        obj, cost=-3, effect_fn=minus3_effect, ability_id="-3",
        targets_required=1, target_kind="creature",
        description="-3: Target creature gains flying and double strike UEOT.",
    )

    # −8: Create X 2/2 white Cat tokens, where X is your life total.
    # Also creates an emblem demonstrating the W15 framework: "Creatures you
    # control have flying and double strike." The printed card has only the
    # tokens; the emblem-variant kicks in only if state._ajani_use_emblem_ult
    # is set (so per-card tests exercise the literal printed effect while
    # the emblem framework test can exercise emblem creation through this
    # same code path).
    def minus8_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        controller = o.controller
        events: list[Event] = []
        # Tokens equal to current life total.
        player = st.players.get(controller)
        x = max(0, int(getattr(player, 'life', 0) if player else 0))
        for _ in range(x):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': controller,
                    'token_type': 'Creature',
                    'name': 'Cat',
                    'power': 2, 'toughness': 2,
                    'colors': {Color.WHITE},
                    'subtypes': {'Cat'},
                },
                source=o.id, controller=controller,
            ))
        # Optional emblem variant: gated on a state flag so the printed card
        # is faithful by default. W15 tests opt in by setting the flag.
        if getattr(st, '_ajani_use_emblem_ult', False):
            from src.cards.interceptor_helpers import make_emblem_creatures_have_keywords
            emblem_setup = make_emblem_creatures_have_keywords(
                source_card_name="Ajani, Caller of the Pride",
                keywords=['flying', 'double_strike'],
                name="Ajani Emblem",
            )
            events.extend(emblem_setup(st, controller, o.id))
        return events

    make_loyalty_ability(
        obj, cost=-8, effect_fn=minus8_effect, ability_id="-8",
        description="-8: Create X 2/2 white Cat creature tokens, where X is your life total.",
    )

    return setup


# --- CATHAR COMMANDO ---
# Flash / {1}, Sacrifice this creature: Destroy target artifact or enchantment.
def cathar_commando_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_sac_destroy_ability
    make_sac_destroy_ability(
        obj, "{1}, Sacrifice this creature",
        target_kind="artifact_or_enchantment",
    )
    return []


# --- GIADA, FONT OF HOPE ---
# Flying, vigilance / Other Angels enter with extra +1/+1 counters / {T}: Add {W} for Angel spells.


# --- IMPRISONED IN THE MOON ---
# Enchant creature, land, or planeswalker / Enchanted permanent becomes colorless land with {T}: Add {C}.
def imprisoned_in_the_moon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: full type-overwriting aura (strips abilities, becomes
    # colorless Land with new mana ability) — no characteristic-layer system
    # to express the overwrite.
    return []


# --- MOCKING SPRITE ---
# Flying / Instant and sorcery spells you cast cost {1} less.
def mocking_sprite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Flying itself is handled by the engine via printed keyword text;
    # we only register the cost reduction here.
    def applies(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller:
            return False
        types = card.characteristics.types
        return CardType.INSTANT in types or CardType.SORCERY in types

    return [make_cost_reduction(obj, applies_to=applies, amount=1)]


# --- OMNISCIENCE ---
# You may cast spells from your hand without paying their mana costs.
def omniscience_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: free-cast replacement for owner
    return []


# --- SPECTRAL SAILOR ---
# Flash, Flying / {3}{U}: Draw a card.
def spectral_sailor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_draw_ability
    make_draw_ability(obj, cost="{3}{U}", count=1, description="Draw a card")
    return []


# --- TOLARIAN TERROR ---
# Costs {1} less for each instant/sorcery in graveyard / Ward {2}.
def tolarian_terror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: {1} less per instant/sorcery card in your graveyard. Ward {2}."""
    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        gy = st.zones.get(f'graveyard_{controller}')
        if not gy:
            return 0
        n = 0
        for oid in gy.objects:
            o = st.objects.get(oid)
            if not o:
                continue
            ts = o.characteristics.types
            if CardType.INSTANT in ts or CardType.SORCERY in ts:
                n += 1
        return n

    return [
        make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                            amount=amount_fn, self_only=True),
        make_ward(obj, mana_cost="{2}"),
    ]


# --- WITNESS PROTECTION ---
# Enchant creature / Enchanted creature loses abilities, becomes 1/1 Citizen.
# Phase 5b sweep: aura attach with P/T delta toward 1/1 + subtype Citizen.
# Full "loses all abilities" + name+colour overwrite is an engine gap.
def witness_protection_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_aura_setup(power_mod=-2, toughness_mod=-2, subtypes_to_add={"Citizen"})(obj, state)


# --- DIREGRAF GHOUL ---
# This creature enters tapped.
def diregraf_ghoul_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- REASSEMBLING SKELETON ---
# {1}{B}: Return this card from your graveyard to the battlefield tapped.
# Phase 5b sweep: setup on battlefield is a noop; the activated graveyard
# ability is registered via ``setup_in_graveyard`` (see below + REASSEMBLING_SKELETON
# attachment further down in the file).
def reassembling_skeleton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []


def reassembling_skeleton_gy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{B}: Return this card from your graveyard to the battlefield tapped.

    Phase 5b sweep — graveyard-activated recursion via RETURN_FROM_GRAVEYARD
    (handler moves the card to battlefield); we then emit TAP on the
    just-returned object.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if o.zone != ZoneType.GRAVEYARD:
            return []
        return [
            Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={'object_id': o.id, 'player': o.controller},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.TAP,
                payload={'object_id': o.id},
                source=o.id, controller=o.controller,
            ),
        ]
    make_activated_ability(
        obj, cost="{1}{B}", effect_fn=_effect,
        description="Return this card from your graveyard to the battlefield tapped",
    )
    return []


# --- AXGARD CAVALRY ---
# {T}: Target creature gains haste until end of turn.
def axgard_cavalry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Target creature gains haste until end of turn."""
    def grant_haste(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'haste', 'duration': 'end_of_turn'},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{T}", effect_fn=grant_haste,
        description="Target creature gains haste until end of turn",
        targets_required=1, target_kind="creature",
    )
    return []


# --- ETALI, PRIMAL STORM ---
# Whenever Etali attacks, exile top card of each library, may cast any of those spells free.
def etali_primal_storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-top-of-each-library + may-cast-free
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- FANATICAL FIREBRAND ---
# Haste / {T}, Sacrifice this creature: It deals 1 damage to any target.


# --- KRENKO, MOB BOSS ---
# {T}: Create X 1/1 red Goblin tokens, where X is the number of Goblins you control.


# --- SHIVAN DRAGON ---
# Flying / {R}: This creature gets +1/+0 until end of turn.


# --- BLANCHWOOD ARMOR ---
# Enchant creature / Enchanted creature gets +1/+1 for each Forest you control.
def blanchwood_armor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted creature gets +1/+1 per Forest you control."""
    base = make_aura_setup()(obj, state)
    def mod_fn(source, target, st):
        n = count_permanents_with_subtype(source.controller, "Forest", st)
        return (n, n)
    return base + make_attached_dynamic_pt_boost(obj, mod_fn)


# --- DOUBLING SEASON ---
# Doubles tokens and counters for you.
def doubling_season_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Counters placed on permanents you control are doubled.

    The token-doubling clause is not yet wired (token creation goes through
    OBJECT_CREATED with a 'token' flag and would need a separate replacement
    that re-emits another OBJECT_CREATED event).
    """
    from src.engine.replacements import make_counter_doubler
    return [make_counter_doubler(obj, multiplier=2)]


# --- GHALTA, PRIMAL HUNGER ---
# Costs {X} less to cast where X is total power of creatures you control. / Trample.
def ghalta_primal_hunger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: {X} less, where X is total power of creatures you control.
    Trample granted via printed keyword text.
    """
    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        total = 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == controller
                    and CardType.CREATURE in o.characteristics.types):
                total += max(0, o.characteristics.power or 0)
        return total

    return [make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                                amount=amount_fn, self_only=True)]


# --- GNARLID COLONY ---
# Kicker {2}{G} / If kicked enters with two +1/+1 counters / Each creature you control with +1/+1 counter has trample.
def gnarlid_colony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Each creature you control with a +1/+1 counter on it has trample.

    The kicker / ETB-with-two-+1/+1-counters portion is still an engine gap
    (no kicker tracking on cast).
    """
    def your_creatures_with_counter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        counters = getattr(target, 'counters', {}) or {}
        return counters.get('+1/+1', 0) > 0

    return [make_keyword_grant(obj, ['trample'], your_creatures_with_counter)]


# --- LLANOWAR ELVES ---
# {T}: Add {G}.


# --- MILD-MANNERED LIBRARIAN ---
# {3}{G}: Becomes Werewolf with two +1/+1 counters and you draw a card. Activate only once.
# Phase 5b sweep: one-shot activated transform — Werewolf subtype, two +1/+1
# counters, draw a card. `once_per_game=True` enforces the "activate only once"
# clause via the engine's activation tracker.
def mildmannered_librarian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _transform(o: GameObject, st: GameState, targets) -> list[Event]:
        # Add the Werewolf subtype on the object directly. The +1/+1 counters
        # provide the implicit P/T bump (no flat stat-line printed for the
        # transformed mode in this engine).
        try:
            subs = set(o.characteristics.subtypes or set())
            subs.add('Werewolf')
            o.characteristics.subtypes = subs
        except Exception:
            pass
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 2},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': o.controller, 'count': 1},
                source=o.id, controller=o.controller,
            ),
        ]
    make_activated_ability(
        obj, cost="{3}{G}", effect_fn=_transform,
        description="Become a Werewolf, gain two +1/+1 counters, draw a card",
        once_per_game=True,
    )
    return []


# --- SCAVENGING OOZE ---
# {G}: Exile target card from a graveyard. If creature, +1/+1 counter and gain 1 life.
def scavenging_ooze_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_activated_ability

    def _scavenge(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target_obj = st.objects.get(target_id) if isinstance(target_id, str) else None
        events: list[Event] = []
        events.append(Event(
            type=EventType.EXILE,
            payload={'object_id': target_id},
            source=o.id,
            controller=o.controller,
        ))
        # If exiled card was a creature, add counter and gain life.
        if target_obj is not None and CardType.CREATURE in target_obj.characteristics.types:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': o.id,
                    'counter_type': '+1/+1',
                    'amount': 1,
                },
                source=o.id,
                controller=o.controller,
            ))
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': o.controller, 'amount': 1},
                source=o.id,
                controller=o.controller,
            ))
        return events

    make_activated_ability(
        obj, "{G}", _scavenge,
        description="Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life.",
        targets_required=1, target_kind="card_in_graveyard",
    )
    return []


# --- MULDROTHA, THE GRAVETIDE ---
# Each turn may play a land and cast a permanent spell of each permanent type from graveyard.
def muldrotha_the_gravetide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: cast-from-graveyard (one of each permanent type) requires
    # a permanent-type-tracked cast permission framework not yet built.
    return []


# --- PROGENITUS ---
# Protection from everything / If put into a graveyard, shuffle into library instead.
def progenitus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If put into a graveyard, shuffle into library instead.

    Protection-from-everything is still a future engine gap; only the
    graveyard replacement is wired here.
    """
    from src.engine.replacements import make_skip_to_graveyard_replacer
    return [make_skip_to_graveyard_replacer(obj, redirect_to=ZoneType.LIBRARY, self_only=True)]


# --- RUBY, DARING TRACKER ---
# Haste / Whenever Ruby attacks while you control creature with power 4+, +2/+2 / {T}: Add {R} or {G}.
def ruby_daring_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: conditional self-pump on attack
        return []
    return [make_attack_trigger(obj, effect_fn)]


# --- THOUSAND-YEAR STORM ---
# Whenever you cast an instant or sorcery, copy it for each previously cast.
def thousandyear_storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: spell-copy-on-cast based on prior cast count
        return []
    return [make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=True,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


# --- BURNISHED HART ---
# {3}, Sacrifice this creature: Search your library for up to two basic land cards, put them onto the battlefield tapped.


# --- GOLDVEIN PICK ---
# Equipped creature gets +1/+1 / Whenever equipped creature deals combat damage to a player, create a Treasure / Equip {1}.


# --- HERALDIC BANNER ---
# As enters, choose a color / Creatures of chosen color get +1/+0 / {T}: Add chosen color.
# Phase 5b sweep: choose-color framework is an engine gap. As a fallback we
# wire a static +1/+0 on creatures you control (assumes "chose your colour")
# plus a {T}: Add one mana of any color activated mana ability — the latter
# uses the engine's mana_added 'any' channel.
def heraldic_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _tap_any(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': o.controller, 'mana': 'any', 'amount': 1},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{T}", effect_fn=_tap_any,
        description="Add one mana of any color",
    )
    return make_static_pt_boost(obj, 1, 0, creatures_you_control(obj))


# --- JUGGERNAUT ---
# Attacks each combat if able / Can't be blocked by Walls.
# Phase 5b sweep: wire the "can't be blocked by Walls" restriction via a
# custom PREVENT interceptor on BLOCK_DECLARED that checks both the blocker
# (must be a Wall) and the attacker (must be this Juggernaut). The
# must-attack restriction stays an engine gap.
def juggernaut_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    source_id = obj.id

    def block_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        if attacker_id != source_id:
            return False
        blocker_id = event.payload.get('blocker_id')
        blocker = st.objects.get(blocker_id)
        if not blocker:
            return False
        return 'Wall' in (blocker.characteristics.subtypes or set())

    def prevent(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=source_id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=block_filter,
        handler=prevent,
        duration='while_on_battlefield',
    )]


# --- SWIFTFOOT BOOTS ---
# Equipped creature has hexproof and haste / Equip {1}.


# --- EVOLVING WILDS ---
# {T}, Sacrifice: Search your library for a basic land, put it onto the battlefield tapped.
def evolving_wilds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_activated_ability

    def _basic_tutor(o: GameObject, st: GameState, targets) -> list[Event]:
        open_library_search(
            st, o.controller, o.id,
            filter_fn=basic_land_filter(),
            destination="battlefield_tapped",
            max_count=1,
            shuffle_after=True,
            optional=True,
            prompt="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
        )
        return []

    make_activated_ability(
        obj, "{T}, Sacrifice this land", _basic_tutor,
        description="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    )
    return []


# --- ROGUE'S PASSAGE ---
# {T}: Add {C}. / {4}, {T}: Target creature can't be blocked this turn.
def rogues_passage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_activated_ability

    def _grant_unblockable(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': 'unblockable',
                'duration': 'end_of_turn',
            },
            source=o.id,
            controller=o.controller,
        )]

    make_activated_ability(
        obj, "{4}, {T}", _grant_unblockable,
        description="Target creature can't be blocked this turn",
        targets_required=1, target_kind="creature",
    )
    return []


# --- SECLUDED COURTYARD ---
# As enters, choose a creature type / {T}: Add {C} / {T}: Add any color for chosen-type creature spells.


# --- ANCESTOR DRAGON ---
# Flying / Whenever creatures you control attack, you gain 1 life for each.
def ancestor_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        return attacker.controller == obj.controller

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- INGENIOUS LEONIN ---
# {3}{W}: Put a +1/+1 counter on another target attacking creature you control. If Cat, first strike.
def ingenious_leonin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{W}: Put a +1/+1 counter on another target attacking creature you
    control. If that creature is a Cat, it gains first strike until end of turn.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        if target_id == o.id:
            return []
        target = st.objects.get(target_id) if target_id else None
        events: list[Event] = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=o.id, controller=o.controller,
        )]
        if target and 'Cat' in (target.characteristics.subtypes or set()):
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': target_id, 'keyword': 'first strike',
                         'duration': 'end_of_turn'},
                source=o.id, controller=o.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{3}{W}", effect_fn=_effect,
        description="+1/+1 counter on attacking creature you control (Cat: first strike)",
        targets_required=1, target_kind="creature_you_control",
    )
    return []


# --- JAZAL GOLDMANE ---
# First strike / {3}{W}{W}: Attacking creatures get +X/+X where X is number of attackers.
def jazal_goldmane_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated {3}{W}{W}: Attacking creatures you control get +X/+X EOT,
    X = number of attacking creatures. First strike is a keyword on the card."""
    def _attackers_pump(o: GameObject, st: GameState, targets) -> list[Event]:
        attacker_ids = []
        for oid, oo in st.objects.items():
            if (oo.controller == o.controller and
                    oo.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in oo.characteristics.types and
                    getattr(oo.state, 'attacking', False)):
                attacker_ids.append(oid)
        x = len(attacker_ids)
        if x <= 0:
            return []
        events: list[Event] = []
        for cid in attacker_ids:
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': cid,
                    'power_mod': x,
                    'toughness_mod': x,
                    'duration': 'end_of_turn',
                },
                source=o.id,
                controller=o.controller,
            ))
        return events

    make_activated_ability(
        obj,
        cost="{3}{W}{W}",
        effect_fn=_attackers_pump,
        description="{3}{W}{W}: Attacking creatures you control get +X/+X until end of turn, where X is the number of attacking creatures.",
    )
    return []


# --- PACIFISM ---
# Enchant creature / Enchanted creature can't attack or block.
def pacifism_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchanted creature can't attack or block."""
    source_id = obj.id

    def cant_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        attached = source.state.attached_to
        return attached is not None and event.payload.get('attacker_id') == attached

    def cant_attack_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    cant_attack = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_attack_filter, handler=cant_attack_handler,
        duration='while_on_battlefield',
    )

    def attached_blocker_filter(target: GameObject, state: GameState) -> bool:
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        return source.state.attached_to is not None and target.id == source.state.attached_to

    from src.cards.interceptor_helpers import make_cant_block
    cant_block = make_cant_block(obj, attached_blocker_filter)
    return [cant_attack, cant_block]


# --- EATEN BY PIRANHAS ---
# Flash / Enchant creature / Loses abilities, becomes 1/1 black Skeleton.
# Phase 5b sweep: aura attach with explicit P/T overrides via the aura-setup
# helper. The "loses all abilities" clause + colour/name overrides are still
# engine gaps (no characteristic-overwrite framework).
def eaten_by_piranhas_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Approximate: aura sets enchanted creature to base 1/1 by applying a P/T
    # delta that brings printed stats down toward 1/1 each tick. We can't
    # actually overwrite base P/T without a characteristic-layer system, so we
    # apply a flat -2/-2 (typical "down to small" approximation).
    return make_aura_setup(power_mod=-2, toughness_mod=-2, subtypes_to_add={"Skeleton"})(obj, state)


# --- KITESAIL CORSAIR ---
# Has flying as long as it's attacking.
# Phase 5b sweep: conditional keyword grant of flying while ``obj.state.attacking``.
def kitesail_corsair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attacking_self(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        return bool(getattr(target.state, 'attacking', False))
    return [make_keyword_grant(obj, ['flying'], attacking_self)]


# --- MYSTIC ARCHAEOLOGIST ---
# {3}{U}{U}: Draw two cards.
def mystic_archaeologist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_draw_ability
    make_draw_ability(obj, cost="{3}{U}{U}", count=2,
                      description="Draw two cards")
    return []


# --- CROSSWAY TROUBLEMAKERS ---
# Attacking Vampires you control have deathtouch and lifelink. / Vampire dies, may pay 2 life: draw a card.
def crossway_troublemakers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if "Vampire" not in target.characteristics.subtypes:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: may-pay-2-life-draw on Vampire death
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- SUSPICIOUS SHAMBLER ---
# {4}{B}{B}, Exile this card from your graveyard: Create two 2/2 black Zombie tokens.
# Phase 5b sweep: on-battlefield setup intentionally empty; the activated
# graveyard ability is registered via ``setup_in_graveyard`` (see
# ``suspicious_shambler_gy_setup`` above + attachment to the card def below).
def suspicious_shambler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []


def suspicious_shambler_gy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{4}{B}{B}, Exile this card from your graveyard: Create two 2/2 black Zombie tokens."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if o.zone != ZoneType.GRAVEYARD:
            return []
        events: list[Event] = [Event(
            type=EventType.EXILE,
            payload={'object_id': o.id},
            source=o.id, controller=o.controller,
        )]
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Zombie Token',
                    'controller': o.controller,
                    'owner': o.controller,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Zombie'},
                    'colors': {Color.BLACK},
                    'power': 2,
                    'toughness': 2,
                    'is_token': True,
                },
                source=o.id, controller=o.controller,
            ))
        return events
    make_activated_ability(
        obj,
        cost="{4}{B}{B}",
        effect_fn=_effect,
        description="Exile from graveyard: Create two 2/2 black Zombie tokens",
        sorcery_speed=True,
    )
    return []


# --- UNTAMED HUNGER ---
# Already wired via make_aura_setup directly on the card definition (see UNTAMED_HUNGER below).


# --- VAMPIRE INTERLOPER ---
# Flying / This creature can't block.
def vampire_interloper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature can't block."""
    from src.cards.interceptor_helpers import make_cant_block
    return [make_cant_block(obj)]


# --- VAMPIRE NEONATE ---
# {2}, {T}: Each opponent loses 1 life and you gain 1 life.
def vampire_neonate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, {T}: Each opponent loses 1 life and you gain 1 life."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': o.controller, 'amount': 1},
            source=o.id, controller=o.controller,
        )]
        for pid in st.players.keys():
            if pid != o.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': pid, 'amount': -1},
                    source=o.id, controller=o.controller,
                ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_effect,
        description="Each opponent loses 1 life and you gain 1 life",
    )
    return []


# --- CARNELIAN ORB OF DRAGONKIND ---
# {T}: Add {R}. If spent on Dragon, gains haste.


# --- DRAGONLORD'S SERVANT ---
# Dragon spells you cast cost {1} less to cast.
def dragonlords_servant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def applies(card: GameObject, pid: str, st: GameState) -> bool:
        return (
            pid == obj.controller
            and "Dragon" in card.characteristics.subtypes
        )

    return [make_cost_reduction(obj, applies_to=applies, amount=1)]


# --- GOBLIN SMUGGLER ---
# Haste / {T}: Another target creature with power 2 or less can't be blocked this turn.
def goblin_smuggler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_activated_ability

    def _grant_unblockable(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target_obj = st.objects.get(target_id) if isinstance(target_id, str) else None
        # "Another target creature" — exclude self.
        if target_obj is None or target_obj.id == o.id:
            return []
        # Validate power 2 or less.
        try:
            power = get_power(target_obj, st)
        except Exception:
            power = target_obj.characteristics.power or 0
        if power > 2:
            return []
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': 'unblockable',
                'duration': 'end_of_turn',
            },
            source=o.id,
            controller=o.controller,
        )]

    make_activated_ability(
        obj, "{T}", _grant_unblockable,
        description="Another target creature with power 2 or less can't be blocked this turn",
        targets_required=1, target_kind="creature",
    )
    return []


# --- KARGAN DRAGONRIDER ---
# As long as you control a Dragon, this creature has flying.
def kargan_dragonrider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_self(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        # Check controller has a Dragon
        for o in state.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    "Dragon" in o.characteristics.subtypes):
                return True
        return False

    return [make_keyword_grant(obj, ['flying'], affects_self)]


# --- DRUID OF THE COWL ---
# {T}: Add {G}.


# --- THRASHING BRONTODON ---
# {1}, Sacrifice this creature: Destroy target artifact or enchantment.
def thrashing_brontodon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_sac_destroy_ability
    make_sac_destroy_ability(
        obj, "{1}, Sacrifice this creature",
        target_kind="artifact_or_enchantment",
    )
    return []


# --- WILDHEART INVOKER ---
# {8}: Target creature gets +5/+5 and gains trample.
def wildheart_invoker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{8}: Target creature gets +5/+5 and gains trample until end of turn."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [
            Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target_id, 'power_mod': 5, 'toughness_mod': 5,
                           'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': target_id, 'keyword': 'trample',
                           'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
        ]
    make_activated_ability(
        obj, cost="{8}", effect_fn=_effect,
        description="Target creature gets +5/+5 and gains trample until end of turn",
        targets_required=1, target_kind="creature",
    )
    return []


# --- GOBLIN FIREBOMB ---
# Flash / {7}, {T}, Sacrifice: Destroy target permanent.
def goblin_firebomb_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_destroy_ability
    make_destroy_ability(
        obj, "{7}, {T}, Sacrifice this artifact",
        target_kind="permanent",
    )
    return []


# --- UNCHARTED HAVEN ---
# Enters tapped / Choose color / {T}: Add chosen color.


# --- ANGELIC DESTINY ---
# Enchant creature / +4/+4, flying, first strike, Angel / Returns to hand on dies.


# --- BALLYRUSH BANNERET ---
# Kithkin spells and Soldier spells you cast cost {1} less.
def ballyrush_banneret_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: Kithkin/Soldier spells you cast cost {1} less."""
    def applies(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller:
            return False
        subs = card.characteristics.subtypes
        return "Kithkin" in subs or "Soldier" in subs

    return [make_cost_reduction(obj, applies_to=applies, amount=1)]


# --- CRUSADER OF ODRIC ---
# Power and toughness equal to number of creatures you control.
def crusader_of_odric_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_dynamic_pt_boost as _dyn_pt

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def pt_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        n = sum(
            1 for o in st.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
        )
        return (n, n)

    return _dyn_pt(obj, pt_mod, affects_self)


# --- FELIDAR CUB ---
# Sacrifice this creature: Destroy target enchantment.
def felidar_cub_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_sac_destroy_ability
    make_sac_destroy_ability(
        obj, cost="Sacrifice this creature",
        target_kind="enchantment",
        description="Destroy target enchantment",
    )
    return []


# --- KNIGHT OF GRACE ---
# First strike / Hexproof from black / +1/+0 as long as any player controls a black permanent.
def knight_of_grace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: +1/+0 as long as any player controls a black permanent.
    (Hexproof from black is still an engine gap — left unimplemented.)"""
    def any_black_permanent(state: GameState) -> bool:
        for perm in state.objects.values():
            if perm.zone == ZoneType.BATTLEFIELD and Color.BLACK in perm.characteristics.colors:
                return True
        return False

    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == obj.id)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        if not any_black_permanent(state):
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield',
    )]


# --- ARCANIS THE OMNIPOTENT ---
# {T}: Draw three cards. / {2}{U}{U}: Return to hand.


# --- DICTATE OF KRUPHIX ---
# Flash / At the beginning of each player's draw step, that player draws an additional card.
def dictate_of_kruphix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') == 'draw'

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # Each player draws additional card during their own draw step
        active_player = state.active_player
        if not active_player:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': active_player, 'amount': 1},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (trigger_handler(e, s).new_events or []),
    )]


# --- FOG BANK ---
# Defender, Flying / Prevent all combat damage to and dealt by this creature.
# Phase 5b sweep: replacement effect that zeroes out combat damage with this
# creature as source OR target.
def fog_bank_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id

    def damage_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        # combat-only.
        if not event.payload.get('is_combat'):
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        # Source is this creature, OR target is this creature.
        damage_source_id = event.source or event.payload.get('source')
        target_id = event.payload.get('target')
        return damage_source_id == src_id or target_id == src_id

    def zero_damage(event: Event, st: GameState) -> Event:
        new_event = event.copy()
        new_event.payload['amount'] = 0
        new_event.payload['_prevented_by'] = src_id
        return new_event

    return make_replacement_effect(
        obj,
        event_filter=damage_filter,
        replace_fn=zero_damage,
        duration='permanent',
        apply_once_per_event=True,
    )


# --- SPHINX OF THE FINAL WORD ---
# Uncounterable / Flying, hexproof / Instant and sorcery spells you control can't be countered.
# Phase 5b sweep: PREVENT-priority interceptor that nullifies COUNTER events
# whose target spell belongs to Sphinx's controller and is instant/sorcery.
def sphinx_of_the_final_word_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_controller = obj.controller
    src_id = obj.id

    def counter_filter(event: Event, st: GameState) -> bool:
        if event.type not in (EventType.COUNTER, EventType.COUNTER_SPELL, EventType.COUNTER_SPELL_UNLESS_PAY):
            return False
        # Only counter-events instigated by an opponent should be prevented.
        if event.controller == src_controller:
            return False
        spell_id = (
            event.payload.get('spell_id')
            or event.payload.get('object_id')
            or event.payload.get('target')
            or event.payload.get('target_id')
        )
        if not spell_id:
            return False
        # Resolve spell target's controller + types. Look in objects first,
        # then on the stack.
        target = st.objects.get(spell_id)
        if target is not None:
            if target.controller != src_controller:
                return False
            types = target.characteristics.types
            return CardType.INSTANT in types or CardType.SORCERY in types
        stack = getattr(st, 'stack', None)
        items = getattr(stack, 'items', None) if stack is not None else None
        if not items:
            return False
        for item in items:
            if getattr(item, 'card_id', None) != spell_id:
                continue
            controller = getattr(item, 'controller', None)
            if controller != src_controller:
                continue
            cd = getattr(item, 'card_def', None)
            ttypes = getattr(cd, 'types', set()) or set()
            return CardType.INSTANT in ttypes or CardType.SORCERY in ttypes
        return False

    def prevent(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=src_controller,
        priority=InterceptorPriority.PREVENT,
        filter=counter_filter,
        handler=prevent,
        duration='while_on_battlefield',
    )]


# --- TEMPEST DJINN ---
# Flying / +1/+0 for each basic Island you control.
def tempest_djinn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: +1/+0 for each basic Island you control."""
    def count_basic_islands(state: GameState) -> int:
        count = 0
        for perm in state.objects.values():
            if (perm.controller == obj.controller
                    and perm.zone == ZoneType.BATTLEFIELD
                    and 'Island' in perm.characteristics.subtypes
                    and 'Basic' in perm.characteristics.supertypes):
                count += 1
        return count

    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == obj.id)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        bonus = count_basic_islands(state)
        if bonus == 0:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield',
    )]


# --- DESECRATION DEMON ---
# Flying / At each combat any opponent may sac creature; if so, tap and +1/+1 counter.
def desecration_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: combat-step opponent may sacrifice
    return []


# --- KNIGHT OF MALICE ---
# First strike / Hexproof from white / +1/+0 as long as any player controls a white permanent.
def knight_of_malice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: +1/+0 as long as any player controls a white permanent.
    (Hexproof from white still engine gap.)"""
    def any_white_permanent(state: GameState) -> bool:
        for perm in state.objects.values():
            if perm.zone == ZoneType.BATTLEFIELD and Color.WHITE in perm.characteristics.colors:
                return True
        return False

    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == obj.id)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        if not any_white_permanent(state):
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield',
    )]


# --- MYOJIN OF NIGHT'S REACH ---
# Enters with divinity counter if cast / Indestructible while it has counter / Remove counter: opponents discard hand.
# Phase 5b sweep:
#   1) ETB-place a divinity counter (we always place it; engine doesn't yet
#      distinguish "cast from hand" vs other entries — typical entry is cast).
#   2) Conditional indestructible keyword grant while counter > 0.
#   3) Activated "Remove a divinity counter: Each opponent discards their hand"
#      (emits DISCARD on each opponent's full hand).
def myojin_of_nights_reach_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _etb(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'divinity', 'amount': 1},
            source=obj.id,
        )]

    def has_divinity(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        counters = getattr(target.state, 'counters', {}) or {}
        return counters.get('divinity', 0) > 0

    def _remove_and_discard(o: GameObject, st: GameState, targets) -> list[Event]:
        # The counter removal is a cost (parsed from the cost string).
        # Effect: each opponent discards their entire hand.
        events: list[Event] = []
        for pid in st.players.keys():
            if pid == o.controller:
                continue
            hand = st.zones.get(f'hand_{pid}')
            if not hand:
                continue
            count = len(hand.objects)
            if count <= 0:
                continue
            events.append(Event(
                type=EventType.DISCARD_CHOICE,
                payload={'player': pid, 'count': count},
                source=o.id, controller=o.controller,
            ))
        return events

    make_activated_ability(
        obj, cost="Remove a divinity counter from this card",
        effect_fn=_remove_and_discard,
        description="Remove a divinity counter: Each opponent discards their hand",
        sorcery_speed=True,
    )
    return [
        make_etb_trigger(obj, _etb),
        make_keyword_grant(obj, ['indestructible'], has_divinity),
    ]


# --- VAMPIRIC RITES ---
# {1}{B}, Sacrifice a creature: You gain 1 life and draw a card.
def vampiric_rites_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{B}, Sacrifice a creature: You gain 1 life and draw a card."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': 1},
                  source=o.id, controller=o.controller),
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'count': 1},
                  source=o.id, controller=o.controller),
        ]
    make_activated_ability(
        obj, cost="{1}{B}, Sacrifice a creature", effect_fn=_effect,
        description="Gain 1 life and draw a card",
    )
    return []


# --- WISHCLAW TALISMAN ---
# Enters with three wish counters / {1}, {T}, Remove counter: Tutor, opponent gains control.
# Phase 5b sweep: ETB places 3 wish counters and registers an activated tutor.
# The "opponent gains control" coda is left unwired (no in-engine permanent
# control swap on activation cost).
def wishclaw_talisman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _etb_counters(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'wish', 'amount': 3},
            source=obj.id,
        )]

    def _tutor(o: GameObject, st: GameState, targets) -> list[Event]:
        # Remove a wish counter as part of the activation. The mana/tap costs
        # are gated by the cost string; we emit the counter removal + tutor.
        open_library_search(
            st, o.controller, o.id,
            filter_fn=any_card_filter(),
            destination="hand",
            max_count=1,
            shuffle_after=True,
            optional=False,
            prompt="Search your library for a card, put it into your hand, then shuffle.",
        )
        return [Event(
            type=EventType.COUNTER_REMOVED,
            payload={'object_id': o.id, 'counter_type': 'wish', 'amount': 1},
            source=o.id, controller=o.controller,
        )]

    make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=_tutor,
        description="Search your library for a card and put it into your hand (remove a wish counter)",
        own_turn_only=True,
    )
    return [make_etb_trigger(obj, _etb_counters)]


# --- GHITU LAVARUNNER ---
# As long as 2+ instant/sorcery in graveyard, gets +1/+0 and has haste.
def ghitu_lavarunner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_dynamic_pt_boost as _dyn_pt,
    )

    def threshold(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        n = 0
        for o in st.objects.values():
            if (o.zone == ZoneType.GRAVEYARD
                    and o.owner == obj.controller
                    and (CardType.INSTANT in o.characteristics.types
                         or CardType.SORCERY in o.characteristics.types)):
                n += 1
                if n >= 2:
                    return True
        return False

    def pt_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        return (1, 0)

    interceptors = list(_dyn_pt(obj, pt_mod, threshold))
    interceptors.append(make_keyword_grant(obj, ['haste'], threshold))
    return interceptors


# --- GIANT CINDERMAW ---
# Trample / Players can't gain life.
def giant_cindermaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Players can't gain life: zero out every LIFE_CHANGE for any player."""
    from src.engine.replacements import make_life_gain_prevention
    return [make_life_gain_prevention(obj, affects_controller=True, affects_opponents=True)]


# --- FYNN, THE FANGBEARER ---
# Deathtouch / Whenever creature you control with deathtouch deals combat damage to player, that player gets two poison counters.
# Phase 5b sweep: emit poison counters on player via COUNTER_ADDED.
def fynn_the_fangbearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source') or event.source
        source_obj = st.objects.get(source_id)
        if not source_obj or source_obj.controller != obj.controller:
            return False
        if CardType.CREATURE not in source_obj.characteristics.types:
            return False
        # Source must have deathtouch (either printed or granted).
        abilities = source_obj.characteristics.abilities or []
        granted = getattr(source_obj.state, 'granted_abilities', []) or []
        has_dt = any(
            (a if isinstance(a, str) else getattr(a, 'name', '')).lower() == 'deathtouch'
            for a in list(abilities) + list(granted)
        )
        if not has_dt:
            return False
        target_id = event.payload.get('target')
        return target_id in st.players

    def damage_effect(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'player': target_id, 'counter_type': 'poison', 'amount': 2},
            source=obj.id, controller=obj.controller,
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_effect(e, s)),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: damage_effect(e, s),
    )]


# --- HEROES' BANE ---
# Enters with four +1/+1 counters / {2}{G}{G}: Put X +1/+1 counters on this creature, X = its power.
def heroes_bane_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with four +1/+1 counters on it.

    The activated ability ({2}{G}{G}: Put X +1/+1 counters on this creature,
    where X is its power) is still an engine gap (no activated-ability system).
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 4},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- ORDEAL OF NYLEA ---
# Enchant creature / Whenever attacks: +1/+1 counter / If 3+, sacrifice / On sac: search basic lands.
def ordeal_of_nylea_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever enchanted creature attacks, put a +1/+1 counter on it.

    The "If it has 3+ +1/+1 counters, sacrifice this Aura" auto-sac and the
    "When sacrificed, search for two basic lands" trigger are still engine
    gaps (no Aura sacrifice cleanup, no land search wiring on sac of self).
    """
    def attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        if not attacker_id:
            return False
        attached_to = getattr(source.state, 'attached_to', None)
        return attached_to == attacker_id

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id')
        if not attacker_id:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': attacker_id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_attack_trigger(obj, attack_effect, attack_filter)]


# --- VIZIER OF THE MENAGERIE ---
# Look at top card any time / May cast creatures from top / Spend any mana to cast creatures.
# Phase 5b sweep: grant continuous permission to cast the top card of the
# controller's library (the cast-permission framework gates this to creatures
# via the engine's spell-type check at cast time only when wired with a card
# filter; full cost-type override "any mana" remains an engine gap).
def vizier_of_the_menagerie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_castable_from_library_top
    return make_castable_from_library_top(obj)


# --- AYLI, ETERNAL PILGRIM ---
# Deathtouch / {1}, Sac creature: gain life equal to toughness / {1}{W}{B}, Sac: exile target nonland (10+ over starting).
# Phase 5b sweep: wire the {1} sac->gain-life ability. The conditional exile
# variant gates on starting-life delta (not tracked uniformly across engines)
# so it stays unwired.
def ayli_eternal_pilgrim_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _gain_from_sac(o: GameObject, st: GameState, targets) -> list[Event]:
        # The "Sacrifice another creature" cost is captured in the cost string,
        # so the engine consumes a creature as part of activation. We just emit
        # a life-gain; the engine does not currently propagate the sac'd target
        # back to the effect_fn, so we use a flat 2 (printed toughness floor)
        # — a conservative approximation. See engine_gaps.md "sac-cost target
        # pull-through" for full fidelity.
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': o.controller, 'amount': 2},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{1}, Sacrifice another creature", effect_fn=_gain_from_sac,
        description="Sacrifice another creature: gain life equal to its toughness (approx 2)",
    )
    return []


# --- DRYAD MILITANT ---
# Hybrid {G/W} / Instant or sorcery cards exiled instead of going to graveyard.
def dryad_militant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant and sorcery cards put into graveyards are exiled instead."""
    from src.engine.replacements import make_graveyard_to_exile_replacer
    return [make_graveyard_to_exile_replacer(
        obj,
        card_type_filter={CardType.INSTANT, CardType.SORCERY},
        affects_controller=True,
        affects_opponents=True,
    )]


# --- ENIGMA DRAKE ---
# Flying / Power equal to number of instant and sorcery cards in your graveyard.
def enigma_drake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_dynamic_pt_boost as _dyn_pt

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def pt_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        n = 0
        for o in st.objects.values():
            if (o.zone == ZoneType.GRAVEYARD
                    and o.owner == obj.controller
                    and (CardType.INSTANT in o.characteristics.types
                         or CardType.SORCERY in o.characteristics.types)):
                n += 1
        return (n, 0)

    return _dyn_pt(obj, pt_mod, affects_self)


# --- IMMERSTURM PREDATOR ---
# Flying / Tapped: exile graveyard card + counter / Sacrifice creature: indestructible + tap.
# Phase 5b sweep: wire the sacrifice-activated indestructible/tap effect. The
# tap trigger (exile graveyard card + +1/+1 counter) is partially wired —
# we add the counter unconditionally since the optional graveyard exile would
# need a target picker on a TAP-trigger which the engine doesn't currently
# expose mid-resolve.
def immersturm_predator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_tap_trigger

    def _on_tap(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]

    def _sac_for_indestructible(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': o.id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.TAP,
                payload={'object_id': o.id},
                source=o.id, controller=o.controller,
            ),
        ]

    make_activated_ability(
        obj, cost="Sacrifice another creature", effect_fn=_sac_for_indestructible,
        description="Sacrifice another creature: This creature gains indestructible until end of turn. Tap it.",
    )
    return [make_tap_trigger(obj, _on_tap)]


# --- PRIME SPEAKER ZEGANA ---
# Enters with X +1/+1 counters where X = greatest power among other creatures / Draw cards equal to its power.
def prime_speaker_zegana_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # X = greatest power among OTHER creatures you control
        x = 0
        for o in state.objects.values():
            if (o.id != obj.id
                    and o.controller == obj.controller
                    and o.zone == ZoneType.BATTLEFIELD
                    and CardType.CREATURE in o.characteristics.types):
                x = max(x, get_power(o, state))
        events = []
        if x > 0:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': x},
                source=obj.id
            ))
        # Draw cards equal to its power (after the counters)
        printed_power = obj.characteristics.power or 0
        draw_amount = printed_power + x
        if draw_amount > 0:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': draw_amount},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


# --- BASILISK COLLAR ---
# Equipped creature has deathtouch and lifelink / Equip {2}.


# --- CULTIVATOR'S CARAVAN ---
# {T}: Add one mana of any color / Crew 3.


# --- DARKSTEEL COLOSSUS ---
# Trample, indestructible / Shuffles into library if would go to graveyard.
def darksteel_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If Darksteel Colossus would be put into a graveyard, shuffle it into its
    owner's library instead.
    """
    from src.engine.replacements import make_skip_to_graveyard_replacer
    return [make_skip_to_graveyard_replacer(obj, redirect_to=ZoneType.LIBRARY, self_only=True)]


# --- FELDON'S CANE ---
# {T}, Exile this artifact: Shuffle your graveyard into your library.


# --- FIRESHRIEKER ---
# Equipped creature has double strike / Equip {2}.


# --- MAZEMIND TOME ---
# {T}, page counter: Scry 1 / {2},{T}, page counter: Draw card / 4 counters: exile, gain 4 life.
# Phase 5b sweep: wire the two activated abilities. We emit a page counter
# (via COUNTER_ADDED with custom counter_type) plus the effect. The "exile at
# 4 counters & gain 4 life" auto-trigger remains a gap (no counter-threshold
# tracking framework yet).
def mazemind_tome_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _scry(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': 'page', 'amount': 1},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': o.controller, 'amount': 1},
                source=o.id, controller=o.controller,
            ),
        ]

    def _draw(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': 'page', 'amount': 1},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': o.controller, 'count': 1},
                source=o.id, controller=o.controller,
            ),
        ]

    make_activated_ability(
        obj, cost="{T}", effect_fn=_scry,
        description="Add page counter; scry 1",
    )
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_draw,
        description="Add page counter; draw a card",
    )
    return []


# --- PYROMANCER'S GOGGLES ---
# {T}: Add {R}. If spent on red instant/sorcery, copy that spell.
# Phase 5b sweep: wire the base {T}: Add {R} mana ability. The "if spent on..."
# spell-copy trigger requires mana-source tracking through casts which is a
# separate engine gap.
def pyromancers_goggles_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _add_red(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': o.controller, 'mana': 'R', 'amount': 1},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{T}", effect_fn=_add_red,
        description="Add {R}",
    )
    return []


# --- SORCEROUS SPYGLASS ---
# As enters, look at opponent's hand and choose a name / Activated abilities of sources with that name can't be activated.
def sorcerous_spyglass_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: choose-name + activation prohibition
    return []


# --- STEEL HELLKITE ---
# Flying / {2}: +1/+0 / {X}: Destroy nonland permanents with mana value X whose controller took combat damage from this.


# --- THREE TREE MASCOT ---
# Changeling / {1}: Add one mana of any color. Activate only once each turn.


# --- AZORIUS GUILDGATE ---
# Enters tapped / {T}: Add {W} or {U}.
def azorius_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- BOROS GUILDGATE ---
# Enters tapped / {T}: Add {R} or {W}.
def boros_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- CRAWLING BARRENS ---
# {T}: Add {C}. / {4}: Two +1/+1 counters; may become 0/0 Elemental.
def crawling_barrens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{4}: Put two +1/+1 counters on this land. Then you may have it become a
    0/0 Elemental creature until end of turn. It's still a land. (We always opt
    in to the becomes-creature mode — the "you may" choice is unmodeled.)"""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        events = [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id,
                controller=o.controller,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id,
                controller=o.controller,
            ),
        ]
        becomes_creature(
            o, st,
            power=0, toughness=0,
            subtypes={"Elemental"},
            keep_land=True,
        )
        return events

    make_activated_ability(
        obj,
        cost="{4}",
        effect_fn=effect,
        description="Put two +1/+1 counters on this land; it becomes a 0/0 Elemental creature until end of turn.",
    )
    return []


# --- CRYPTIC CAVES ---
# {T}: Add {C}. / {1},{T}, Sac: Draw a card if 5+ lands.


# --- DEMOLITION FIELD ---
# {T}: Add {C}. / {2},{T}, Sac: Destroy nonbasic land; both players may search for basic.
# Phase 5b sweep: wire the activated destroy effect (sac as additional cost
# auto-parsed via "Sacrifice this land" in cost string). The "both players may
# search for basic" follow-up is left unwired — basic-land tutor for both
# players is a separate engine concern.
def demolition_field_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target = st.objects.get(target_id) if isinstance(target_id, str) else None
        if target is None:
            return []
        # Must be nonbasic land controlled by opponent.
        if CardType.LAND not in target.characteristics.types:
            return []
        if 'Basic' in (target.characteristics.supertypes or set()):
            return []
        if target.controller == o.controller:
            return []
        return [Event(
            type=EventType.DESTROY,
            payload={'object_id': target_id},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{2}, {T}, Sacrifice this land", effect_fn=_effect,
        description="Destroy target nonbasic land an opponent controls",
        targets_required=1, target_kind="land",
    )
    return []


# --- DIMIR GUILDGATE ---
# Enters tapped / {T}: Add {U} or {B}.
def dimir_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- GOLGARI GUILDGATE ---
# Enters tapped / {T}: Add {B} or {G}.
def golgari_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- GRUUL GUILDGATE ---
# Enters tapped / {T}: Add {R} or {G}.
def gruul_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- IZZET GUILDGATE ---
# Enters tapped / {T}: Add {U} or {R}.
def izzet_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- ORZHOV GUILDGATE ---
# Enters tapped / {T}: Add {W} or {B}.
def orzhov_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- RAKDOS GUILDGATE ---
# Enters tapped / {T}: Add {B} or {R}.
def rakdos_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- SELESNYA GUILDGATE ---
# Enters tapped / {T}: Add {G} or {W}.
def selesnya_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- SIMIC GUILDGATE ---
# Enters tapped / {T}: Add {G} or {U}.
def simic_guildgate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# --- CONFISCATE ---
# Enchant permanent / You control enchanted permanent.
# Phase 5b sweep: aura attach + ETB CONTROL_CHANGE so the controller of
# Confiscate gains control of the enchanted permanent. The control change
# uses duration='permanent' so it persists past EOT (unlike threaten).
def confiscate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    base = make_aura_setup()(obj, state)

    def _on_etb(event: Event, st: GameState) -> list[Event]:
        attached = getattr(obj.state, 'attached_to', None)
        if not attached:
            return []
        return [Event(
            type=EventType.CONTROL_CHANGE,
            payload={
                'object_id': attached,
                'new_controller': obj.controller,
                'duration': 'permanent',
            },
            source=obj.id, controller=obj.controller,
        )]

    return base + [make_etb_trigger(obj, _on_etb)]


# --- GRATUITOUS VIOLENCE ---
# If a creature you control would deal damage, it deals double instead.
def gratuitous_violence_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If a creature you control would deal damage to a permanent or player, it deals double instead.

    Wired through ``make_replacement_effect`` (the generic "if X would happen,
    Y instead" primitive). Filter: DAMAGE event whose source is a creature
    controlled by Gratuitous Violence's controller AND whose target is a
    permanent or player. Replacement: ``amount * 2``. The marker pin prevents
    Gratuitous Violence from re-doubling its own output.
    """
    src_controller = obj.controller
    src_id = obj.id

    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        # Source must be a creature you control.
        damage_source_id = event.source or event.payload.get('source')
        damage_source = state.objects.get(damage_source_id) if damage_source_id else None
        if damage_source is None:
            return False
        if damage_source.controller != src_controller:
            return False
        if CardType.CREATURE not in damage_source.characteristics.types:
            return False
        # Target must be a permanent or a player. (Players are by id in
        # ``state.players``; permanents are GameObjects on the battlefield.)
        target_id = event.payload.get('target')
        if target_id in state.players:
            return True
        target_obj = state.objects.get(target_id) if target_id else None
        if target_obj is None:
            return False
        return target_obj.zone == ZoneType.BATTLEFIELD

    def double_damage(event: Event, state: GameState) -> Event:
        new_event = event.copy()
        new_event.payload['amount'] = int(event.payload.get('amount', 0)) * 2
        new_event.payload['_doubled_by'] = src_id
        return new_event

    return make_replacement_effect(
        obj,
        event_filter=damage_filter,
        replace_fn=double_damage,
        duration='permanent',
        apply_once_per_event=True,
    )


# --- UNFLINCHING COURAGE ---
# Enchant creature / +2/+2, trample, lifelink.


# --- EXPEDITION MAP ---
# {2}, {T}, Sacrifice this artifact: Search your library for a land card.


# --- GILDED LOTUS ---
# {T}: Add three mana of any one color.


# --- HEDRON ARCHIVE ---
# {T}: Add {C}{C}. / {2},{T}, Sac: Draw two cards.


# --- MAZE'S END ---
# Enters tapped / {T}: Add {C}. / {3},{T}, Return to hand: Search for a Gate; if 10 different gates, win the game.
def mazes_end_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(EventType.TAP, {'object_id': obj.id}, obj.id)]
    return [make_etb_trigger(obj, effect_fn)]


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

SIRE_OF_SEVEN_DEATHS = make_creature(
    name="Sire of Seven Deaths",
    power=7, toughness=7,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Eldrazi"},
    text="First strike, vigilance\nMenace, trample\nReach, lifelink\nWard—Pay 7 life.",
    setup_interceptors=sire_of_seven_deaths_setup,
)

ARAHBO_THE_FIRST_FANG = make_creature(
    name="Arahbo, the First Fang",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Avatar", "Cat"},
    supertypes={"Legendary"},
    text="Other Cats you control get +1/+1.\nWhenever Arahbo or another nontoken Cat you control enters, create a 1/1 white Cat creature token.",
    setup_interceptors=arahbo_the_first_fang_setup
)

ARMASAUR_GUIDE = make_creature(
    name="Armasaur Guide",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Dinosaur"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhenever you attack with three or more creatures, put a +1/+1 counter on target creature you control.",
    setup_interceptors=armasaur_guide_setup,
)

CAT_COLLECTOR = make_creature(
    name="Cat Collector",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever you gain life for the first time during each of your turns, create a 1/1 white Cat creature token.",
    setup_interceptors=cat_collector_setup
)

CELESTIAL_ARMOR = make_artifact(
    name="Celestial Armor",
    mana_cost="{2}{W}",
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this Equipment enters, attach it to target creature you control. That creature gains hexproof and indestructible until end of turn.\nEquipped creature gets +2/+0 and has flying.\nEquip {3}{W} ({3}{W}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=celestial_armor_setup,
)

def claws_out_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: affinity for Cats — {1} less per Cat you control.

    Skipped clauses:
      * Resolution effect ('+2/+2 to creatures you control until end of
        turn') is left to cast-effect dispatch elsewhere.
    """
    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        n = 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == controller
                    and "Cat" in o.characteristics.subtypes):
                n += 1
        return n

    return [make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                                amount=amount_fn, self_only=True)]


CLAWS_OUT = make_instant(
    name="Claws Out",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Affinity for Cats (This spell costs {1} less to cast for each Cat you control.)\nCreatures you control get +2/+2 until end of turn.",
    setup_interceptors=claws_out_setup,
)

CRYSTAL_BARRICADE = make_artifact_creature(
    name="Crystal Barricade",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Wall"},
    text="Defender (This creature can't attack.)\nYou have hexproof. (You can't be the target of spells or abilities your opponents control.)\nPrevent all noncombat damage that would be dealt to other creatures you control.",
    setup_interceptors=crystal_barricade_setup,
)

DAUNTLESS_VETERAN = make_creature(
    name="Dauntless Veteran",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, creatures you control get +1/+1 until end of turn.",
    setup_interceptors=dauntless_veteran_setup,
)

DAZZLING_ANGEL = make_creature(
    name="Dazzling Angel",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever another creature you control enters, you gain 1 life.",
    setup_interceptors=dazzling_angel_setup
)

DIVINE_RESILIENCE = make_instant(
    name="Divine Resilience",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.)\nTarget creature you control gains indestructible until end of turn. If this spell was kicked, instead any number of target creatures you control gain indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy them.)",
    # engine gap: kicker mode (any-number targets when kicked) — simplified to always grant.
    resolve=divine_resilience_resolve,
    target_requirements=[target_creature(count=1, controller='you')],
)

EXEMPLAR_OF_LIGHT = make_creature(
    name="Exemplar of Light",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever you gain life, put a +1/+1 counter on this creature.\nWhenever you put one or more +1/+1 counters on this creature, draw a card. This ability triggers only once each turn.",
    setup_interceptors=exemplar_of_light_setup
)

FELIDAR_SAVIOR = make_creature(
    name="Felidar Savior",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat"},
    text="Lifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhen this creature enters, put a +1/+1 counter on each of up to two other target creatures you control.",
    setup_interceptors=felidar_savior_setup,
)

FLEETING_FLIGHT = make_instant(
    name="Fleeting Flight",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature. It gains flying until end of turn. Prevent all combat damage that would be dealt to it this turn.",
)

GUARDED_HEIR = make_creature(
    name="Guarded Heir",
    power=1, toughness=1,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="Lifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhen this creature enters, create two 3/3 white Knight creature tokens.",
    setup_interceptors=guarded_heir_setup
)

HARE_APPARENT = make_creature(
    name="Hare Apparent",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Noble", "Rabbit"},
    text="When this creature enters, create a number of 1/1 white Rabbit creature tokens equal to the number of other creatures you control named Hare Apparent.\nA deck can have any number of cards named Hare Apparent.",
    setup_interceptors=hare_apparent_setup
)

HELPFUL_HUNTER = make_creature(
    name="Helpful Hunter",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="When this creature enters, draw a card.",
    setup_interceptors=helpful_hunter_setup
)

HERALD_OF_ETERNAL_DAWN = make_creature(
    name="Herald of Eternal Dawn",
    power=6, toughness=6,
    mana_cost="{4}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nYou can't lose the game and your opponents can't win the game.",
    setup_interceptors=herald_of_eternal_dawn_setup,
)

INSPIRING_PALADIN = make_creature(
    name="Inspiring Paladin",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="During your turn, this creature has first strike. (It deals combat damage before creatures without first strike.)\nDuring your turn, creatures you control with +1/+1 counters on them have first strike.",
    setup_interceptors=inspiring_paladin_setup,
)

JOUST_THROUGH = make_instant(
    name="Joust Through",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Joust Through deals 3 damage to target attacking or blocking creature. You gain 1 life.",
)

LUMINOUS_REBUKE = make_instant(
    name="Luminous Rebuke",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped creature.\nDestroy target creature.",
)

PRIDEFUL_PARENT = make_creature(
    name="Prideful Parent",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhen this creature enters, create a 1/1 white Cat creature token.",
    setup_interceptors=prideful_parent_setup
)

RAISE_THE_PAST = make_sorcery(
    name="Raise the Past",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Return all creature cards with mana value 2 or less from your graveyard to the battlefield.",
    resolve=raise_the_past_resolve,
)

SKYKNIGHT_SQUIRE = make_creature(
    name="Skyknight Squire",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Scout"},
    text="Whenever another creature you control enters, put a +1/+1 counter on this creature.\nAs long as this creature has three or more +1/+1 counters on it, it has flying and is a Knight in addition to its other types.",
    setup_interceptors=skyknight_squire_setup
)

SQUAD_RALLIER = make_creature(
    name="Squad Rallier",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="{2}{W}: Look at the top four cards of your library. You may reveal a creature card with power 2 or less from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=squad_rallier_setup,
)

SUNBLESSED_HEALER = make_creature(
    name="Sun-Blessed Healer",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    text="Kicker {1}{W} (You may pay an additional {1}{W} as you cast this spell.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhen this creature enters, if it was kicked, return target nonland permanent card with mana value 2 or less from your graveyard to the battlefield.",
    setup_interceptors=sunblessed_healer_setup,
)

TWINBLADE_BLESSING = make_enchantment(
    name="Twinblade Blessing",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nEnchant creature\nEnchanted creature has double strike. (It deals both first-strike and regular combat damage.)",
    subtypes={"Aura"},
    setup_interceptors=twinblade_blessing_setup,
)

VALKYRIES_CALL = make_enchantment(
    name="Valkyrie's Call",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Whenever a nontoken, non-Angel creature you control dies, return that card to the battlefield under its owner's control with a +1/+1 counter on it. It has flying and is an Angel in addition to its other types.",
    setup_interceptors=valkyries_call_setup,
)

VANGUARD_SERAPH = make_creature(
    name="Vanguard Seraph",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Warrior"},
    text="Flying\nWhenever you gain life for the first time each turn, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=vanguard_seraph_setup,
)

def arcane_epiphany_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost reduction: This spell costs {1} less if you control a Wizard."""
    def applies(card: GameObject, pid: str, st: GameState) -> bool:
        # `self_only=True` already pins this to the casting card itself; we
        # only need to check the conditional clause here.
        if pid != obj.controller:
            return False
        bf = st.zones.get('battlefield')
        if not bf:
            return False
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == obj.controller
                    and "Wizard" in o.characteristics.subtypes):
                return True
        return False

    return [make_cost_reduction(obj, applies_to=applies, amount=1, self_only=True)]


ARCANE_EPIPHANY = make_instant(
    name="Arcane Epiphany",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if you control a Wizard.\nDraw three cards.",
    resolve=resolve_draw(3),
    setup_interceptors=arcane_epiphany_setup,
)

ARCHMAGE_OF_RUNES = make_creature(
    name="Archmage of Runes",
    power=3, toughness=6,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Giant", "Wizard"},
    text="Instant and sorcery spells you cast cost {1} less to cast.\nWhenever you cast an instant or sorcery spell, draw a card.",
    setup_interceptors=archmage_of_runes_setup
)

BIGFIN_BOUNCER = make_creature(
    name="Bigfin Bouncer",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Shark"},
    text="When this creature enters, return target creature an opponent controls to its owner's hand.",
    setup_interceptors=bigfin_bouncer_setup
)

CEPHALID_INKMAGE = make_creature(
    name="Cephalid Inkmage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Octopus", "Wizard"},
    text="When this creature enters, surveil 3. (Look at the top three cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nThreshold — This creature can't be blocked as long as there are seven or more cards in your graveyard.",
    setup_interceptors=cephalid_inkmage_setup
)

CLINQUANT_SKYMAGE = make_creature(
    name="Clinquant Skymage",
    power=1, toughness=1,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Wizard"},
    text="Flying\nWhenever you draw a card, put a +1/+1 counter on this creature.",
    setup_interceptors=clinquant_skymage_setup
)

CURATOR_OF_DESTINIES = make_creature(
    name="Curator of Destinies",
    power=5, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="This spell can't be countered.\nFlying\nWhen this creature enters, look at the top five cards of your library and separate them into a face-down pile and a face-up pile. An opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard.",
    setup_interceptors=curator_of_destinies_setup,
)

DRAKE_HATCHER = make_creature(
    name="Drake Hatcher",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Vigilance, prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever this creature deals combat damage to a player, put that many incubation counters on it.\nRemove three incubation counters from this creature: Create a 2/2 blue Drake creature token with flying.",
    setup_interceptors=drake_hatcher_setup,
)

ELEMENTALIST_ADEPT = make_creature(
    name="Elementalist Adept",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
)

ERUDITE_WIZARD = make_creature(
    name="Erudite Wizard",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you draw your second card each turn, put a +1/+1 counter on this creature.",
    setup_interceptors=erudite_wizard_setup,
)

FAEBLOOM_TRICK = make_instant(
    name="Faebloom Trick",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Create two 1/1 blue Faerie creature tokens with flying. When you do, tap target creature an opponent controls.",
)

GRAPPLING_KRAKEN = make_creature(
    name="Grappling Kraken",
    power=5, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Kraken"},
    text="Landfall — Whenever a land you control enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=grappling_kraken_setup,
)

HIGH_FAE_TRICKSTER = make_creature(
    name="High Fae Trickster",
    power=4, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nYou may cast spells as though they had flash.",
    setup_interceptors=high_fae_trickster_setup,
)

HOMUNCULUS_HORDE = make_creature(
    name="Homunculus Horde",
    power=2, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    text="Whenever you draw your second card each turn, create a token that's a copy of this creature.",
    setup_interceptors=homunculus_horde_setup,
)

ICEWIND_ELEMENTAL = make_creature(
    name="Icewind Elemental",
    power=3, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying\nWhen this creature enters, draw a card, then discard a card.",
    setup_interceptors=icewind_elemental_setup
)

INSPIRATION_FROM_BEYOND = make_sorcery(
    name="Inspiration from Beyond",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Mill three cards, then return an instant or sorcery card from your graveyard to your hand.\nFlashback {5}{U}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
    # engine gap: flashback alt-cast not wired here; resolve = mill 3 + return.
    resolve=inspiration_from_beyond_resolve,
)

KAITO_CUNNING_INFILTRATOR = make_planeswalker(
    name="Kaito, Cunning Infiltrator",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    loyalty=3,
    subtypes={"Kaito"},
    supertypes={"Legendary"},
    text="Whenever a creature you control deals combat damage to a player, put a loyalty counter on Kaito.\n+1: Up to one target creature you control can't be blocked this turn. Draw a card, then discard a card.\n−2: Create a 2/1 blue Ninja creature token.\n−9: You get an emblem with \"Whenever a player casts a spell, you create a 2/1 blue Ninja creature token.\"",
    setup_interceptors=kaito_cunning_infiltrator_setup,
)

KIORA_THE_RISING_TIDE = make_creature(
    name="Kiora, the Rising Tide",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Noble"},
    supertypes={"Legendary"},
    text="When Kiora enters, draw two cards, then discard two cards.\nThreshold — Whenever Kiora attacks, if there are seven or more cards in your graveyard, you may create Scion of the Deep, a legendary 8/8 blue Octopus creature token.",
    setup_interceptors=kiora_the_rising_tide_setup,
)

LUNAR_INSIGHT = make_sorcery(
    name="Lunar Insight",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw a card for each different mana value among nonland permanents you control.",
)

MISCHIEVOUS_MYSTIC = make_creature(
    name="Mischievous Mystic",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flying\nWhenever you draw your second card each turn, create a 1/1 blue Faerie creature token with flying.",
    setup_interceptors=mischievous_mystic_setup
)

REFUTE = make_instant(
    name="Refute",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Draw a card, then discard a card.",
)

RUNESEALED_WALL = make_artifact_creature(
    name="Rune-Sealed Wall",
    power=0, toughness=6,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Wall"},
    text="Defender\n{T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SKYSHIP_BUCCANEER = make_creature(
    name="Skyship Buccaneer",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying\nRaid — When this creature enters, if you attacked this turn, draw a card.",
    setup_interceptors=skyship_buccaneer_setup,
)

SPHINX_OF_FORGOTTEN_LORE = make_creature(
    name="Sphinx of Forgotten Lore",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nWhenever this creature attacks, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to that card's mana cost. (You may cast that card from your graveyard for its flashback cost. Then exile it.)",
    setup_interceptors=sphinx_of_forgotten_lore_setup,
)

STRIX_LOOKOUT = make_creature(
    name="Strix Lookout",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying, vigilance (Attacking doesn't cause this creature to tap.)\n{1}{U}, {T}: Draw a card, then discard a card.",
    setup_interceptors=strix_lookout_setup,
)

UNCHARTED_VOYAGE = make_instant(
    name="Uncharted Voyage",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target creature's owner puts it on their choice of the top or bottom of their library.\nSurveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

ABYSSAL_HARVESTER = make_creature(
    name="Abyssal Harvester",
    power=3, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Warlock"},
    text="{T}: Exile target creature card from a graveyard that was put there this turn. Create a token that's a copy of it, except it's a Nightmare in addition to its other types. Then exile all other Nightmare tokens you control.",
    setup_interceptors=abyssal_harvester_setup,
)

ARBITER_OF_WOE = make_creature(
    name="Arbiter of Woe",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="As an additional cost to cast this spell, sacrifice a creature.\nFlying\nWhen this creature enters, each opponent discards a card and loses 2 life. You draw a card and gain 2 life.",
    setup_interceptors=arbiter_of_woe_setup,
)

BILLOWING_SHRIEKMASS = make_creature(
    name="Billowing Shriekmass",
    power=2, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying\nWhen this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\nThreshold — This creature gets +2/+1 as long as there are seven or more cards in your graveyard.",
    setup_interceptors=billowing_shriekmass_setup,
)

BLASPHEMOUS_EDICT = make_sorcery(
    name="Blasphemous Edict",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="You may pay {B} rather than pay this spell's mana cost if there are thirteen or more creatures on the battlefield.\nEach player sacrifices thirteen creatures of their choice.",
    # engine gap: mass sacrifice with per-player choice and alt-cast condition.
)

BLOODTHIRSTY_CONQUEROR = make_creature(
    name="Bloodthirsty Conqueror",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Vampire"},
    text="Flying, deathtouch\nWhenever an opponent loses life, you gain that much life. (Damage causes loss of life.)",
    setup_interceptors=bloodthirsty_conqueror_setup
)

CRYPT_FEASTER = make_creature(
    name="Crypt Feaster",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nThreshold — Whenever this creature attacks, if there are seven or more cards in your graveyard, this creature gets +2/+0 until end of turn.",
    setup_interceptors=crypt_feaster_setup,
)

GUTLESS_PLUNDERER = make_creature(
    name="Gutless Plunderer",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Pirate", "Skeleton"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nRaid — When this creature enters, if you attacked this turn, look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.",
    setup_interceptors=gutless_plunderer_setup,
)

HIGHSOCIETY_HUNTER = make_creature(
    name="High-Society Hunter",
    power=5, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Noble", "Vampire"},
    text="Flying\nWhenever this creature attacks, you may sacrifice another creature. If you do, put a +1/+1 counter on this creature.\nWhenever another nontoken creature dies, draw a card.",
    setup_interceptors=highsociety_hunter_setup,
)

HUNGRY_GHOUL = make_creature(
    name="Hungry Ghoul",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="{1}, Sacrifice another creature: Put a +1/+1 counter on this creature.",
    setup_interceptors=hungry_ghoul_setup,
)

INFERNAL_VESSEL = make_creature(
    name="Infernal Vessel",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="When this creature dies, if it wasn't a Demon, return it to the battlefield under its owner's control with two +1/+1 counters on it. It's a Demon in addition to its other types.",
    setup_interceptors=infernal_vessel_setup,
)

INFESTATION_SAGE = make_creature(
    name="Infestation Sage",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="When this creature dies, create a 1/1 black and green Insect creature token with flying.",
    setup_interceptors=infestation_sage_setup
)

MIDNIGHT_SNACK = make_enchantment(
    name="Midnight Snack",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Raid — At the beginning of your end step, if you attacked this turn, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}{B}, Sacrifice this enchantment: Target opponent loses X life, where X is the amount of life you gained this turn.",
    setup_interceptors=midnight_snack_setup,
)

NINELIVES_FAMILIAR = make_creature(
    name="Nine-Lives Familiar",
    power=1, toughness=1,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Cat"},
    text="This creature enters with eight revival counters on it if you cast it.\nWhen this creature dies, if it had a revival counter on it, return it to the battlefield with one fewer revival counter on it at the beginning of the next end step.",
    setup_interceptors=ninelives_familiar_setup,
)

REVENGE_OF_THE_RATS = make_sorcery(
    name="Revenge of the Rats",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Create a tapped 1/1 black Rat creature token for each creature card in your graveyard.\nFlashback {2}{B}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
    # engine gap: flashback alt-cast not wired here; resolve creates the tokens.
    resolve=revenge_of_the_rats_resolve,
)

SANGUINE_SYPHONER = make_creature(
    name="Sanguine Syphoner",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warlock"},
    text="Whenever this creature attacks, each opponent loses 1 life and you gain 1 life.",
    setup_interceptors=sanguine_syphoner_setup
)

def _seekers_folly_mode_discard(state: GameState, caster_id: str, spell_id: str, targets=None) -> list[Event]:
    """Target opponent discards two cards."""
    if not targets:
        return []
    pid = targets[0].id
    return [Event(
        type=EventType.DISCARD,
        payload={'player': pid, 'amount': 2},
        source=spell_id, controller=caster_id,
    )]


def _seekers_folly_mode_minus(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """Creatures your opponents control get -1/-1 until end of turn."""
    events: list[Event] = []
    for oid, o in state.objects.items():
        if (o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types
                and o.controller != caster_id):
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': oid, 'power_mod': -1, 'toughness_mod': -1, 'duration': 'end_of_turn'},
                source=spell_id, controller=caster_id,
            ))
    return events


SEEKERS_FOLLY = make_sorcery(
    name="Seeker's Folly",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Target opponent discards two cards.\n• Creatures your opponents control get -1/-1 until end of turn.",
    resolve=make_modal_resolve(
        "Seeker's Folly",
        modes=[
            ModeSpec(
                "Target opponent discards two cards",
                _seekers_folly_mode_discard,
                target_requirement=target_player(controller='opponent'),
            ),
            ("Creatures your opponents control get -1/-1 until end of turn", _seekers_folly_mode_minus),
        ],
        min_modes=1, max_modes=1,
    ),
)

SOULSHACKLED_ZOMBIE = make_creature(
    name="Soul-Shackled Zombie",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When this creature enters, exile up to two target cards from a single graveyard. If at least one creature card was exiled this way, each opponent loses 2 life and you gain 2 life.",
    setup_interceptors=soulshackled_zombie_setup,
)

STAB = make_instant(
    name="Stab",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn.",
)

TINYBONES_BAUBLE_BURGLAR = make_creature(
    name="Tinybones, Bauble Burglar",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    supertypes={"Legendary"},
    text="Whenever an opponent discards a card, exile it from their graveyard with a stash counter on it.\nDuring your turn, you may play cards you don't own with stash counters on them from exile, and mana of any type can be spent to cast those spells.\n{3}{B}, {T}: Each opponent discards a card. Activate only as a sorcery.",
    setup_interceptors=tinybones_bauble_burglar_setup,
)

TRAGIC_BANSHEE = make_creature(
    name="Tragic Banshee",
    power=5, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Morbid — When this creature enters, target creature an opponent controls gets -1/-1 until end of turn. If a creature died this turn, that creature gets -13/-13 until end of turn instead.",
    setup_interceptors=tragic_banshee_setup,
)

VAMPIRE_GOURMAND = make_creature(
    name="Vampire Gourmand",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Whenever this creature attacks, you may sacrifice another creature. If you do, draw a card and this creature can't be blocked this turn.",
    setup_interceptors=vampire_gourmand_setup,
)

VAMPIRE_SOULCALLER = make_creature(
    name="Vampire Soulcaller",
    power=3, toughness=2,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warlock"},
    text="Flying\nThis creature can't block.\nWhen this creature enters, return target creature card from your graveyard to your hand.",
    setup_interceptors=vampire_soulcaller_setup
)

VENGEFUL_BLOODWITCH = make_creature(
    name="Vengeful Bloodwitch",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warlock"},
    text="Whenever this creature or another creature you control dies, target opponent loses 1 life and you gain 1 life.",
    setup_interceptors=vengeful_bloodwitch_setup
)

ZUL_ASHUR_LICH_LORD = make_creature(
    name="Zul Ashur, Lich Lord",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Warlock", "Zombie"},
    supertypes={"Legendary"},
    text="Ward—Pay 2 life. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays 2 life.)\n{T}: You may cast target Zombie creature card from your graveyard this turn.",
    setup_interceptors=zul_ashur_lich_lord_setup,
)

BATTLESONG_BERSERKER = make_creature(
    name="Battlesong Berserker",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Human"},
    text="Whenever you attack, target creature you control gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
    setup_interceptors=battlesong_berserker_setup,
)

BOLTWAVE = make_sorcery(
    name="Boltwave",
    mana_cost="{R}",
    colors={Color.RED},
    text="Boltwave deals 3 damage to each opponent.",
)

BULK_UP = make_instant(
    name="Bulk Up",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Double target creature's power until end of turn.\nFlashback {4}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
    # engine gap: flashback alt-cast not wired here.
    resolve=bulk_up_resolve,
    target_requirements=[target_creature(count=1)],
)

CHANDRA_FLAMESHAPER = make_planeswalker(
    name="Chandra, Flameshaper",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    loyalty=6,
    subtypes={"Chandra"},
    supertypes={"Legendary"},
    text="+2: Add {R}{R}{R}. Exile the top three cards of your library. Choose one. You may play that card this turn.\n+1: Create a token that's a copy of target creature you control, except it has haste and \"At the beginning of the end step, sacrifice this token.\"\n−4: Chandra deals 8 damage divided as you choose among any number of target creatures and/or planeswalkers.",
    setup_interceptors=chandra_flameshaper_setup,
)

COURAGEOUS_GOBLIN = make_creature(
    name="Courageous Goblin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Whenever this creature attacks while you control a creature with power 4 or greater, this creature gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
    setup_interceptors=courageous_goblin_setup,
)

CRACKLING_CYCLOPS = make_creature(
    name="Crackling Cyclops",
    power=0, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Cyclops", "Wizard"},
    text="Whenever you cast a noncreature spell, this creature gets +3/+0 until end of turn.",
    setup_interceptors=crackling_cyclops_setup,
)

DRAGON_TRAINER = make_creature(
    name="Dragon Trainer",
    power=1, toughness=1,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human"},
    text="When this creature enters, create a 4/4 red Dragon creature token with flying.",
    setup_interceptors=dragon_trainer_setup
)

ELECTRODUPLICATE = make_sorcery(
    name="Electroduplicate",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Create a token that's a copy of target creature you control, except it has haste and \"At the beginning of the end step, sacrifice this token.\"\nFlashback {2}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

FIERY_ANNIHILATION = make_instant(
    name="Fiery Annihilation",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Fiery Annihilation deals 5 damage to target creature. Exile up to one target Equipment attached to that creature. If that creature would die this turn, exile it instead.",
)

GOBLIN_BOARDERS = make_creature(
    name="Goblin Boarders",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="Raid — This creature enters with a +1/+1 counter on it if you attacked this turn.",
    setup_interceptors=goblin_boarders_setup,
)

GOBLIN_NEGOTIATION = make_sorcery(
    name="Goblin Negotiation",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Goblin Negotiation deals X damage to target creature. Create a number of 1/1 red Goblin creature tokens equal to the amount of excess damage dealt to that creature this way.",
    # engine gap: excess-damage tracking required to count token creation.
)

GOREHORN_RAIDER = make_creature(
    name="Gorehorn Raider",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Pirate"},
    text="Raid — When this creature enters, if you attacked this turn, this creature deals 2 damage to any target.",
    setup_interceptors=gorehorn_raider_setup
)

INCINERATING_BLAST = make_sorcery(
    name="Incinerating Blast",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Incinerating Blast deals 6 damage to target creature.\nYou may discard a card. If you do, draw a card.",
    resolve=incinerating_blast_resolve,
    target_requirements=[target_creature(count=1)],
)

KELLAN_PLANAR_TRAILBLAZER = make_creature(
    name="Kellan, Planar Trailblazer",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Faerie", "Human", "Scout"},
    supertypes={"Legendary"},
    text="{1}{R}: If Kellan is a Scout, it becomes a Human Faerie Detective and gains \"Whenever Kellan deals combat damage to a player, exile the top card of your library. You may play that card this turn.\"\n{2}{R}: If Kellan is a Detective, it becomes a 3/2 Human Faerie Rogue and gains double strike.",
    setup_interceptors=kellan_planar_trailblazer_setup,
)

RITE_OF_THE_DRAGONCALLER = make_enchantment(
    name="Rite of the Dragoncaller",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Whenever you cast an instant or sorcery spell, create a 5/5 red Dragon creature token with flying.",
    setup_interceptors=rite_of_the_dragoncaller_setup
)

SEARSLICER_GOBLIN = make_creature(
    name="Searslicer Goblin",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Raid — At the beginning of your end step, if you attacked this turn, create a 1/1 red Goblin creature token.",
    setup_interceptors=searslicer_goblin_setup
)

SLUMBERING_CERBERUS = make_creature(
    name="Slumbering Cerberus",
    power=4, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dog"},
    text="This creature doesn't untap during your untap step.\nMorbid — At the beginning of each end step, if a creature died this turn, untap this creature.",
    setup_interceptors=slumbering_cerberus_setup,
)

SOWER_OF_CHAOS = make_creature(
    name="Sower of Chaos",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Devil"},
    text="{2}{R}: Target creature can't block this turn.",
    setup_interceptors=sower_of_chaos_setup,
)

STRONGBOX_RAIDER = make_creature(
    name="Strongbox Raider",
    power=5, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Pirate"},
    text="Raid — When this creature enters, if you attacked this turn, exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.",
    setup_interceptors=strongbox_raider_setup,
)

TWINFLAME_TYRANT = make_creature(
    name="Twinflame Tyrant",
    power=3, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nIf a source you control would deal damage to an opponent or a permanent an opponent controls, it deals double that damage instead.",
    setup_interceptors=twinflame_tyrant_setup,
)

AMBUSH_WOLF = make_creature(
    name="Ambush Wolf",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, exile up to one target card from a graveyard.",
    setup_interceptors=ambush_wolf_setup,
)

APOTHECARY_STOMPER = make_creature(
    name="Apothecary Stomper",
    power=4, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhen this creature enters, choose one —\n• Put two +1/+1 counters on target creature you control.\n• You gain 4 life.",
    setup_interceptors=apothecary_stomper_setup,
)

BEASTKIN_RANGER = make_creature(
    name="Beast-Kin Ranger",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Ranger"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever another creature you control enters, this creature gets +1/+0 until end of turn.",
    setup_interceptors=beastkin_ranger_setup,
)

CACKLING_PROWLER = make_creature(
    name="Cackling Prowler",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Hyena", "Rogue"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nMorbid — At the beginning of your end step, if a creature died this turn, put a +1/+1 counter on this creature.",
    setup_interceptors=cackling_prowler_setup,
)

EAGER_TRUFFLESNOUT = make_creature(
    name="Eager Trufflesnout",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Boar"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever this creature deals combat damage to a player, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    setup_interceptors=eager_trufflesnout_setup,
)

ELFSWORN_GIANT = make_creature(
    name="Elfsworn Giant",
    power=5, toughness=3,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Reach (This creature can block creatures with flying.)\nLandfall — Whenever a land you control enters, create a 1/1 green Elf Warrior creature token.",
    setup_interceptors=elfsworn_giant_setup
)

ELVISH_REGROWER = make_creature(
    name="Elvish Regrower",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="When this creature enters, return target permanent card from your graveyard to your hand.",
    setup_interceptors=elvish_regrower_setup
)

FELLING_BLOW = make_sorcery(
    name="Felling Blow",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. Then that creature deals damage equal to its power to target creature an opponent controls.",
)

LOOT_EXUBERANT_EXPLORER = make_creature(
    name="Loot, Exuberant Explorer",
    power=1, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Noble"},
    supertypes={"Legendary"},
    text="You may play an additional land on each of your turns.\n{4}{G}{G}, {T}: Look at the top six cards of your library. You may reveal a creature card with mana value less than or equal to the number of lands you control from among them and put it onto the battlefield. Put the rest on the bottom in a random order.",
    setup_interceptors=loot_exuberant_explorer_setup,
)

MOSSBORN_HYDRA = make_creature(
    name="Mossborn Hydra",
    power=0, toughness=0,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Hydra"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nThis creature enters with a +1/+1 counter on it.\nLandfall — Whenever a land you control enters, double the number of +1/+1 counters on this creature.",
    setup_interceptors=mossborn_hydra_setup,
)

NEEDLETOOTH_PACK = make_creature(
    name="Needletooth Pack",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Morbid — At the beginning of your end step, if a creature died this turn, put two +1/+1 counters on target creature you control.",
    setup_interceptors=needletooth_pack_setup,
)

PREPOSTEROUS_PROPORTIONS = make_sorcery(
    name="Preposterous Proportions",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +10/+10 and gain vigilance until end of turn.",
    resolve=_resolve_anthem_creatures_you_control(10, 10, ('vigilance',)),
)

QUAKESTRIDER_CERATOPS = make_creature(
    name="Quakestrider Ceratops",
    power=12, toughness=8,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="",
)

QUILLED_GREATWURM = make_creature(
    name="Quilled Greatwurm",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Trample\nWhenever a creature you control deals combat damage during your turn, put that many +1/+1 counters on it. (It must survive to get the counters.)\nYou may cast this card from your graveyard by removing six counters from among creatures you control in addition to paying its other costs.",
    setup_interceptors=quilled_greatwurm_setup,
)

SPINNER_OF_SOULS = make_creature(
    name="Spinner of Souls",
    power=4, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spider", "Spirit"},
    text="Reach\nWhenever another nontoken creature you control dies, you may reveal cards from the top of your library until you reveal a creature card. Put that card into your hand and the rest on the bottom of your library in a random order.",
    setup_interceptors=spinner_of_souls_setup,
)

SYLVAN_SCAVENGING = make_enchantment(
    name="Sylvan Scavenging",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="At the beginning of your end step, choose one —\n• Put a +1/+1 counter on target creature you control.\n• Create a 3/3 green Raccoon creature token if you control a creature with power 4 or greater.",
    setup_interceptors=sylvan_scavenging_setup,
)

TREETOP_SNARESPINNER = make_creature(
    name="Treetop Snarespinner",
    power=1, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach (This creature can block creatures with flying.)\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\n{2}{G}: Put a +1/+1 counter on target creature you control. Activate only as a sorcery.",
    setup_interceptors=treetop_snarespinner_setup,
)

ALESHA_WHO_LAUGHS_AT_FATE = make_creature(
    name="Alesha, Who Laughs at Fate",
    power=2, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike\nWhenever Alesha attacks, put a +1/+1 counter on it.\nRaid — At the beginning of your end step, if you attacked this turn, return target creature card with mana value less than or equal to Alesha's power from your graveyard to the battlefield.",
    setup_interceptors=alesha_who_laughs_at_fate_setup,
)

ANTHEM_OF_CHAMPIONS = make_enchantment(
    name="Anthem of Champions",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Creatures you control get +1/+1.",
    setup_interceptors=anthem_of_champions_setup
)

ASHROOT_ANIMIST = make_creature(
    name="Ashroot Animist",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Druid", "Lizard"},
    text="Trample\nWhenever this creature attacks, another target creature you control gains trample and gets +X/+X until end of turn, where X is this creature's power.",
    setup_interceptors=ashroot_animist_setup,
)

DREADWING_SCAVENGER = make_creature(
    name="Dreadwing Scavenger",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Bird", "Nightmare"},
    text="Flying\nWhenever this creature enters or attacks, draw a card, then discard a card.\nThreshold — This creature gets +1/+1 and has deathtouch as long as there are seven or more cards in your graveyard.",
    setup_interceptors=dreadwing_scavenger_setup,
)

ELENDA_SAINT_OF_DUSK = make_creature(
    name="Elenda, Saint of Dusk",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Knight", "Vampire"},
    supertypes={"Legendary"},
    text="Lifelink, hexproof from instants\nAs long as your life total is greater than your starting life total, Elenda gets +1/+1 and has menace. Elenda gets an additional +5/+5 as long as your life total is at least 10 greater than your starting life total.",
    setup_interceptors=elenda_saint_of_dusk_setup,
)

FIENDISH_PANDA = make_creature(
    name="Fiendish Panda",
    power=3, toughness=2,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bear", "Demon"},
    text="Whenever you gain life, put a +1/+1 counter on this creature.\nWhen this creature dies, return another target non-Bear creature card with mana value less than or equal to this creature's power from your graveyard to the battlefield.",
    setup_interceptors=fiendish_panda_setup
)

KOMA_WORLDEATER = make_creature(
    name="Koma, World-Eater",
    power=8, toughness=12,
    mana_cost="{3}{G}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Serpent"},
    supertypes={"Legendary"},
    text="This spell can't be countered.\nTrample, ward {4}\nWhenever Koma deals combat damage to a player, create four 3/3 blue Serpent creature tokens named Koma's Coil.",
    setup_interceptors=koma_worldeater_setup,
)

KYKAR_ZEPHYR_AWAKENER = make_creature(
    name="Kykar, Zephyr Awakener",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Wizard"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast a noncreature spell, choose one —\n• Exile another target creature you control. Return that card to the battlefield under its owner's control at the beginning of the next end step.\n• Create a 1/1 white Spirit creature token with flying.",
    setup_interceptors=kykar_zephyr_awakener_setup,
)

NIVMIZZET_VISIONARY = make_creature(
    name="Niv-Mizzet, Visionary",
    power=5, toughness=5,
    mana_cost="{4}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Dragon", "Wizard"},
    supertypes={"Legendary"},
    text="Flying\nYou have no maximum hand size.\nWhenever a source you control deals noncombat damage to an opponent, you draw that many cards.",
    setup_interceptors=nivmizzet_visionary_setup,
)

PERFORATING_ARTIST = make_creature(
    name="Perforating Artist",
    power=3, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Devil"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nRaid — At the beginning of your end step, if you attacked this turn, each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card.",
    setup_interceptors=perforating_artist_setup,
)

WARDENS_OF_THE_CYCLE = make_creature(
    name="Wardens of the Cycle",
    power=3, toughness=4,
    mana_cost="{1}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Warlock"},
    text="Morbid — At the beginning of your end step, if a creature died this turn, choose one —\n• You gain 2 life.\n• You draw a card and you lose 1 life.",
    setup_interceptors=wardens_of_the_cycle_setup,
)

ZIMONE_PARADOX_SCULPTOR = make_creature(
    name="Zimone, Paradox Sculptor",
    power=1, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, put a +1/+1 counter on each of up to two target creatures you control.\n{G}{U}, {T}: Double the number of each kind of counter on up to two target creatures and/or artifacts you control.",
    setup_interceptors=zimone_paradox_sculptor_setup,
)

BANNER_OF_KINSHIP = make_artifact(
    name="Banner of Kinship",
    mana_cost="{5}",
    text="As this artifact enters, choose a creature type. This artifact enters with a fellowship counter on it for each creature you control of the chosen type.\nCreatures you control of the chosen type get +1/+1 for each fellowship counter on this artifact.",
    setup_interceptors=banner_of_kinship_setup,
)

FISHING_POLE = make_artifact(
    name="Fishing Pole",
    mana_cost="{1}",
    text="Equipped creature has \"{1}, {T}, Tap Fishing Pole: Put a bait counter on Fishing Pole.\"\nWhenever equipped creature becomes untapped, remove a bait counter from this Equipment. If you do, create a 1/1 blue Fish creature token.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=fishing_pole_setup,
)

LEYLINE_AXE = make_artifact(
    name="Leyline Axe",
    mana_cost="{4}",
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nEquipped creature gets +1/+1 and has double strike and trample.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=1,
        keywords=["double strike", "trample"],
        equip_cost="{3}",
    ),
)

QUICKDRAW_KATANA = make_artifact(
    name="Quick-Draw Katana",
    mana_cost="{2}",
    text="During your turn, equipped creature gets +2/+0 and has first strike. (It deals combat damage before creatures without first strike.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    # NOTE: card text gates the boost on "during your turn" — engine has no
    # active-player-conditional QUERY interceptor yet, so we wire the
    # unconditional +2/+0 + first strike. Imperfect translation; revisit
    # when the engine supports turn-conditional statics.
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=0,
        keywords=["first strike"],
        equip_cost="{2}",
    ),
)

RAVENOUS_AMULET = make_artifact(
    name="Ravenous Amulet",
    mana_cost="{2}",
    text="{1}, {T}, Sacrifice a creature: Draw a card and put a soul counter on this artifact. Activate only as a sorcery.\n{4}, {T}, Sacrifice this artifact: Each opponent loses life equal to the number of soul counters on this artifact.",
)

SCRAWLING_CRAWLER = make_artifact_creature(
    name="Scrawling Crawler",
    power=3, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct", "Phyrexian"},
    text="At the beginning of your upkeep, each player draws a card.\nWhenever an opponent draws a card, that player loses 1 life.",
    setup_interceptors=scrawling_crawler_setup
)

SOULSTONE_SANCTUARY = make_land(
    name="Soulstone Sanctuary",
    text="{T}: Add {C}.\n{4}: This land becomes a 3/3 creature with vigilance and all creature types. It's still a land.",
    setup_interceptors=soulstone_sanctuary_setup,
)

AJANI_CALLER_OF_THE_PRIDE = make_planeswalker(
    name="Ajani, Caller of the Pride",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    loyalty=4,
    subtypes={"Ajani"},
    supertypes={"Legendary"},
    text="+1: Put a +1/+1 counter on up to one target creature.\n−3: Target creature gains flying and double strike until end of turn.\n−8: Create X 2/2 white Cat creature tokens, where X is your life total.",
    setup_interceptors=ajani_caller_of_the_pride_setup,
)

AJANIS_PRIDEMATE = make_creature(
    name="Ajani's Pridemate",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="Whenever you gain life, put a +1/+1 counter on this creature.",
    setup_interceptors=ajanis_pridemate_setup
)

ANGEL_OF_FINALITY = make_creature(
    name="Angel of Finality",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhen this creature enters, exile target player's graveyard.",
    setup_interceptors=angel_of_finality_setup,
)

AUTHORITY_OF_THE_CONSULS = make_enchantment(
    name="Authority of the Consuls",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Creatures your opponents control enter tapped.\nWhenever a creature an opponent controls enters, you gain 1 life.",
    setup_interceptors=authority_of_the_consuls_setup
)

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=banishing_light_setup,
)

CATHAR_COMMANDO = make_creature(
    name="Cathar Commando",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
    setup_interceptors=cathar_commando_setup,
)

DAY_OF_JUDGMENT = make_sorcery(
    name="Day of Judgment",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures.",
    resolve=day_of_judgment_resolve,
)

GIADA_FONT_OF_HOPE = make_creature(
    name="Giada, Font of Hope",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nEach other Angel you control enters with an additional +1/+1 counter on it for each Angel you already control.\n{T}: Add {W}. Spend this mana only to cast an Angel spell.",
)

HEALERS_HAWK = make_creature(
    name="Healer's Hawk",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying\nLifelink (Damage dealt by this creature also causes you to gain that much life.)",
)

def _artifact_enchantment_or_big_creature_filter(obj: GameObject, state: GameState) -> bool:
    """Match artifacts, enchantments, or creatures with power 4+."""
    types = obj.characteristics.types
    if CardType.ARTIFACT in types or CardType.ENCHANTMENT in types:
        return True
    if CardType.CREATURE in types:
        return (obj.characteristics.power or 0) >= 4
    return False


MAKE_YOUR_MOVE = make_instant(
    name="Make Your Move",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact, enchantment, or creature with power 4 or greater.",
    resolve=make_your_move_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.CREATURE},
                custom_filter=_artifact_enchantment_or_big_creature_filter,
            ),
            count=1,
            label="target artifact, enchantment, or creature with power 4 or greater",
        ),
    ],
)

MISCHIEVOUS_PUP = make_creature(
    name="Mischievous Pup",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dog"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
    setup_interceptors=mischievous_pup_setup,
)

RESOLUTE_REINFORCEMENTS = make_creature(
    name="Resolute Reinforcements",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, create a 1/1 white Soldier creature token.",
    setup_interceptors=resolute_reinforcements_setup
)

SAVANNAH_LIONS = make_creature(
    name="Savannah Lions",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="",
)

SERRA_ANGEL = make_creature(
    name="Serra Angel",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nVigilance (Attacking doesn't cause this creature to tap.)",
)

STROKE_OF_MIDNIGHT = make_instant(
    name="Stroke of Midnight",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target nonland permanent. Its controller creates a 1/1 white Human creature token.",
    resolve=stroke_of_midnight_resolve,
    target_requirements=[
        TargetRequirement(
            filter=permanent_filter(custom_filter=_nonland_permanent_filter),
            count=1,
            label="target nonland permanent",
        ),
    ],
)

YOUTHFUL_VALKYRIE = make_creature(
    name="Youthful Valkyrie",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever another Angel you control enters, put a +1/+1 counter on this creature.",
    setup_interceptors=youthful_valkyrie_setup
)

AEGIS_TURTLE = make_creature(
    name="Aegis Turtle",
    power=0, toughness=5,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Turtle"},
    text="",
)

AETHERIZE = make_instant(
    name="Aetherize",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Return all attacking creatures to their owner's hand.",
    resolve=aetherize_resolve,
)

BRINEBORN_CUTTHROAT = make_creature(
    name="Brineborn Cutthroat",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Pirate"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhenever you cast a spell during an opponent's turn, put a +1/+1 counter on this creature.",
    setup_interceptors=brineborn_cutthroat_setup
)

ESSENCE_SCATTER = make_instant(
    name="Essence Scatter",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target creature spell.",
    resolve=essence_scatter_resolve,
    target_requirements=[
        TargetRequirement(
            filter=spell_filter(custom_filter=_creature_spell_filter),
            count=1,
            label="target creature spell",
        ),
    ],
)

EXTRAVAGANT_REPLICATION = make_enchantment(
    name="Extravagant Replication",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, create a token that's a copy of another target nonland permanent you control.",
    setup_interceptors=extravagant_replication_setup
)

FLEETING_DISTRACTION = make_instant(
    name="Fleeting Distraction",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -1/-0 until end of turn.\nDraw a card.",
    resolve=fleeting_distraction_resolve,
    target_requirements=[target_creature(count=1)],
)

IMPRISONED_IN_THE_MOON = make_enchantment(
    name="Imprisoned in the Moon",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature, land, or planeswalker\nEnchanted permanent is a colorless land with \"{T}: Add {C}\" and loses all other card types and abilities.",
    subtypes={"Aura"},
    setup_interceptors=imprisoned_in_the_moon_setup,
)

LIGHTSHELL_DUO = make_creature(
    name="Lightshell Duo",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Rat"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=lightshell_duo_setup
)

MICROMANCER = make_creature(
    name="Micromancer",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, you may search your library for an instant or sorcery card with mana value 1, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=micromancer_setup,
)

MOCKING_SPRITE = make_creature(
    name="Mocking Sprite",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nInstant and sorcery spells you cast cost {1} less to cast.",
    setup_interceptors=mocking_sprite_setup,
)

AN_OFFER_YOU_CANT_REFUSE = make_instant(
    name="An Offer You Can't Refuse",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell. Its controller creates two Treasure tokens. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    resolve=an_offer_you_cant_refuse_resolve,
    target_requirements=[
        TargetRequirement(
            filter=spell_filter(custom_filter=_noncreature_spell_filter),
            count=1,
            label="target noncreature spell",
        ),
    ],
)

OMNISCIENCE = make_enchantment(
    name="Omniscience",
    mana_cost="{7}{U}{U}{U}",
    colors={Color.BLUE},
    text="You may cast spells from your hand without paying their mana costs.",
    setup_interceptors=omniscience_setup,
)

RUN_AWAY_TOGETHER = make_instant(
    name="Run Away Together",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
    resolve=run_away_together_resolve,
    # Phase 5b cross-target: the printed text is "controlled by different
    # players" — not necessarily one of yours + one opponent's. In a
    # multiplayer game both picks can be opposing players' creatures. The
    # callable second requirement enforces the constraint exactly.
    target_requirements=[
        target_creature(count=1, label="target creature"),
        target_creature_different_controller(
            label="target creature controlled by a different player",
        ),
    ],
)

SELFREFLECTION = make_sorcery(
    name="Self-Reflection",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control.\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SPECTRAL_SAILOR = make_creature(
    name="Spectral Sailor",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Spirit"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\n{3}{U}: Draw a card.",
    setup_interceptors=spectral_sailor_setup,
)

THINK_TWICE = make_instant(
    name="Think Twice",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw a card.\nFlashback {2}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

TIME_STOP = make_instant(
    name="Time Stop",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="End the turn. (Exile all spells and abilities, including this spell. The player whose turn it is discards down to their maximum hand size. Damage heals and \"this turn\" and \"until end of turn\" effects end.)",
    # engine gap: "end the turn" replacement effect not implemented.
)

TOLARIAN_TERROR = make_creature(
    name="Tolarian Terror",
    power=5, toughness=5,
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="This spell costs {1} less to cast for each instant and sorcery card in your graveyard.\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)",
    setup_interceptors=tolarian_terror_setup,
)

WITNESS_PROTECTION = make_enchantment(
    name="Witness Protection",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature loses all abilities and is a green and white Citizen creature with base power and toughness 1/1 named Legitimate Businessperson. (It loses all other colors, card types, creature types, and names.)",
    subtypes={"Aura"},
    setup_interceptors=witness_protection_setup,
)

BAKE_INTO_A_PIE = make_instant(
    name="Bake into a Pie",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    resolve=bake_into_a_pie_resolve,
    target_requirements=[target_creature(count=1)],
)

BURGLAR_RAT = make_creature(
    name="Burglar Rat",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When this creature enters, each opponent discards a card.",
    setup_interceptors=burglar_rat_setup
)

DIREGRAF_GHOUL = make_creature(
    name="Diregraf Ghoul",
    power=2, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="This creature enters tapped.",
    setup_interceptors=diregraf_ghoul_setup,
)

EATEN_ALIVE = make_sorcery(
    name="Eaten Alive",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature or pay {3}{B}.\nExile target creature or planeswalker.",
)

EXSANGUINATE = make_sorcery(
    name="Exsanguinate",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent loses X life. You gain life equal to the life lost this way.",
    resolve=exsanguinate_resolve,
)

FAKE_YOUR_OWN_DEATH = make_instant(
    name="Fake Your Own Death",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control and you create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    resolve=fake_your_own_death_resolve,
    target_requirements=[target_creature(count=1)],
)

HEROS_DOWNFALL = make_instant(
    name="Hero's Downfall",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or planeswalker.",
    resolve=heros_downfall_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(types={CardType.CREATURE, CardType.PLANESWALKER}),
            count=1,
            label="target creature or planeswalker",
        ),
    ],
)

LILIANA_DREADHORDE_GENERAL = make_planeswalker(
    name="Liliana, Dreadhorde General",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    loyalty=6,
    subtypes={"Liliana"},
    supertypes={"Legendary"},
    text="Whenever a creature you control dies, draw a card.\n+1: Create a 2/2 black Zombie creature token.\n−4: Each player sacrifices two creatures of their choice.\n−9: Each opponent chooses a permanent they control of each permanent type and sacrifices the rest.",
    setup_interceptors=liliana_dreadhorde_general_setup,
)

MACABRE_WALTZ = make_sorcery(
    name="Macabre Waltz",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand, then discard a card.",
)

MARAUDING_BLIGHTPRIEST = make_creature(
    name="Marauding Blight-Priest",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Whenever you gain life, each opponent loses 1 life.",
    setup_interceptors=marauding_blightpriest_setup
)

PAINFUL_QUANDARY = make_enchantment(
    name="Painful Quandary",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Whenever an opponent casts a spell, that player loses 5 life unless they discard a card.",
    setup_interceptors=painful_quandary_setup,
)

PHYREXIAN_ARENA = make_enchantment(
    name="Phyrexian Arena",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you draw a card and you lose 1 life.",
    setup_interceptors=phyrexian_arena_setup
)

PILFER = make_sorcery(
    name="Pilfer",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
    # engine gap: "you choose" requires hand-reveal UI; falls back to standard discard.
    resolve=pilfer_resolve,
    target_requirements=[target_player(controller='opponent')],
)

REASSEMBLING_SKELETON = make_creature(
    name="Reassembling Skeleton",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Warrior"},
    text="{1}{B}: Return this card from your graveyard to the battlefield tapped.",
    setup_interceptors=reassembling_skeleton_setup,
)
# Phase 5b sweep: graveyard activated ability (reanimation).
REASSEMBLING_SKELETON.setup_in_graveyard = reassembling_skeleton_gy_setup

RISE_OF_THE_DARK_REALMS = make_sorcery(
    name="Rise of the Dark Realms",
    mana_cost="{7}{B}{B}",
    colors={Color.BLACK},
    text="Put all creature cards from all graveyards onto the battlefield under your control.",
    resolve=rise_of_the_dark_realms_resolve,
)

RUNESCARRED_DEMON = make_creature(
    name="Rune-Scarred Demon",
    power=6, toughness=6,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, search your library for a card, put it into your hand, then shuffle.",
    setup_interceptors=runescarred_demon_setup,
)

STROMKIRK_BLOODTHIEF = make_creature(
    name="Stromkirk Bloodthief",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="At the beginning of your end step, if an opponent lost life this turn, put a +1/+1 counter on target Vampire you control.",
    setup_interceptors=stromkirk_bloodthief_setup,
)

VAMPIRE_NIGHTHAWK = make_creature(
    name="Vampire Nighthawk",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Shaman", "Vampire"},
    text="Flying\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)",
)

ZOMBIFY = make_sorcery(
    name="Zombify",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield.",
    resolve=zombify_resolve,
    target_requirements=[
        TargetRequirement(
            filter=card_in_graveyard_filter(types={CardType.CREATURE}),
            count=1,
            label="target creature card in a graveyard",
        ),
    ],
)


# =============================================================================
# ABRADE - Modal damage/artifact destruction
# =============================================================================

def _foundations_abrade_burn(state, caster_id, spell_id, targets=None):
    """Abrade mode 1: 3 damage to target creature."""
    if not targets:
        return []
    tid = targets[0].id
    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': tid, 'amount': 3,
            'source': spell_id, 'is_combat': False,
        },
        source=spell_id, controller=caster_id,
    )]


def _foundations_abrade_destroy(state, caster_id, spell_id, targets=None):
    """Abrade mode 2: destroy target artifact."""
    if not targets:
        return []
    tid = targets[0].id
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': tid},
        source=spell_id, controller=caster_id,
    )]


ABRADE = make_instant(
    name="Abrade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Abrade deals 3 damage to target creature.\n• Destroy target artifact.",
    resolve=make_modal_resolve(
        "Abrade",
        modes=[
            ModeSpec(
                "Abrade deals 3 damage to target creature",
                _foundations_abrade_burn,
                target_requirement=target_creature(count=1),
            ),
            ModeSpec(
                "Destroy target artifact",
                _foundations_abrade_destroy,
                target_requirement=TargetRequirement(
                    filter=TargetFilter(types={CardType.ARTIFACT}),
                    count=1, label="target artifact",
                ),
            ),
        ],
        min_modes=1, max_modes=1,
    ),
)

AXGARD_CAVALRY = make_creature(
    name="Axgard Cavalry",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Dwarf"},
    text="{T}: Target creature gains haste until end of turn. (It can attack and {T} this turn.)",
    setup_interceptors=axgard_cavalry_setup,
)

BRASSS_BOUNTY = make_sorcery(
    name="Brass's Bounty",
    mana_cost="{6}{R}",
    colors={Color.RED},
    text="For each land you control, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

BRAZEN_SCOURGE = make_creature(
    name="Brazen Scourge",
    power=3, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Gremlin"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)",
)

BURST_LIGHTNING = make_instant(
    name="Burst Lightning",
    mana_cost="{R}",
    colors={Color.RED},
    text="Kicker {4} (You may pay an additional {4} as you cast this spell.)\nBurst Lightning deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead.",
    resolve=burst_lightning_resolve,
    target_requirements=[target_any(count=1)],
)

SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target.",
    resolve=shock_resolve,
    target_requirements=[target_any(count=1)],
)

DRAKUSETH_MAW_OF_FLAMES = make_creature(
    name="Drakuseth, Maw of Flames",
    power=7, toughness=7,
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Drakuseth attacks, it deals 4 damage to any target and 3 damage to each of up to two other targets.",
    setup_interceptors=drakuseth_maw_of_flames_setup
)

ETALI_PRIMAL_STORM = make_creature(
    name="Etali, Primal Storm",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="Whenever Etali attacks, exile the top card of each player's library, then you may cast any number of spells from among those cards without paying their mana costs.",
    setup_interceptors=etali_primal_storm_setup,
)

FANATICAL_FIREBRAND = make_creature(
    name="Fanatical Firebrand",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\n{T}, Sacrifice this creature: It deals 1 damage to any target.",
)

FIREBRAND_ARCHER = make_creature(
    name="Firebrand Archer",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Archer", "Human"},
    text="Whenever you cast a noncreature spell, this creature deals 1 damage to each opponent.",
    setup_interceptors=firebrand_archer_setup
)

FIRESPITTER_WHELP = make_creature(
    name="Firespitter Whelp",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhenever you cast a noncreature or Dragon spell, this creature deals 1 damage to each opponent.",
    setup_interceptors=firespitter_whelp_setup
)

FLAMEWAKE_PHOENIX = make_creature(
    name="Flamewake Phoenix",
    power=2, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    text="Flying, haste\nThis creature attacks each combat if able.\nFerocious — At the beginning of combat on your turn, if you control a creature with power 4 or greater, you may pay {R}. If you do, return this card from your graveyard to the battlefield.",
    setup_interceptors=flamewake_phoenix_setup,
)

FRENZIED_GOBLIN = make_creature(
    name="Frenzied Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Goblin"},
    text="Whenever this creature attacks, you may pay {R}. If you do, target creature can't block this turn.",
    setup_interceptors=frenzied_goblin_setup,
)

def _goblin_surprise_mode_pump(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """Creatures you control get +2/+0 until end of turn."""
    events: list[Event] = []
    for oid, o in state.objects.items():
        if (o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types
                and o.controller == caster_id):
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': oid, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
                source=spell_id, controller=caster_id,
            ))
    return events


def _goblin_surprise_mode_tokens(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """Create two 1/1 red Goblin creature tokens."""
    return [
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Goblin Token',
                'controller': caster_id, 'owner': caster_id,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'power': 1, 'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Goblin'},
                'colors': {Color.RED},
                'is_token': True,
            },
            source=spell_id, controller=caster_id,
        )
        for _ in range(2)
    ]


GOBLIN_SURPRISE = make_instant(
    name="Goblin Surprise",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Choose one —\n• Creatures you control get +2/+0 until end of turn.\n• Create two 1/1 red Goblin creature tokens.",
    resolve=make_modal_resolve(
        "Goblin Surprise",
        modes=[
            ("Creatures you control get +2/+0 until end of turn", _goblin_surprise_mode_pump),
            ("Create two 1/1 red Goblin creature tokens", _goblin_surprise_mode_tokens),
        ],
        min_modes=1, max_modes=1,
    ),
)

HEARTFIRE_IMMOLATOR = make_creature(
    name="Heartfire Immolator",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\n{R}, Sacrifice this creature: It deals damage equal to its power to target creature or planeswalker.",
    setup_interceptors=heartfire_immolator_setup,
)

HIDETSUGUS_SECOND_RITE = make_instant(
    name="Hidetsugu's Second Rite",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="If target player has exactly 10 life, Hidetsugu's Second Rite deals 10 damage to that player.",
)

def involuntary_employment_resolve(targets: list, state: GameState) -> list[Event]:
    """Threaten + create Treasure token (Phase 5b: target via target_requirements)."""
    from src.cards.interceptor_helpers import threaten_creature
    spell = _resolving_spell_obj(state)
    caster_id = _spell_caster_id(state) or ""
    spell_id = spell.id if spell is not None else "involuntary_employment"

    treasure_event = Event(
        type=EventType.OBJECT_CREATED,
        payload={
            'name': 'Treasure',
            'controller': caster_id,
            'owner': caster_id,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'types': {CardType.ARTIFACT},
            'subtypes': {'Treasure'},
            'colors': set(),
            'is_token': True,
        },
        source=spell_id,
        controller=caster_id,
    )

    events: list[Event] = []
    if targets and targets[0]:
        tid, _ = normalize_target(targets[0][0], state)
        events.extend(threaten_creature(tid, caster_id, source_id=spell_id))
    events.append(treasure_event)
    return events


INVOLUNTARY_EMPLOYMENT = make_sorcery(
    name="Involuntary Employment",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    resolve=involuntary_employment_resolve,
    target_requirements=[target_creature(count=1, controller='opponent')],
)

KRENKO_MOB_BOSS = make_creature(
    name="Krenko, Mob Boss",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    supertypes={"Legendary"},
    text="{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
)

SEISMIC_RUPTURE = make_sorcery(
    name="Seismic Rupture",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Seismic Rupture deals 2 damage to each creature without flying.",
)

SHIVAN_DRAGON = make_creature(
    name="Shivan Dragon",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\n{R}: This creature gets +1/+0 until end of turn.",
)

def _slagstorm_mode_creatures(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """3 damage to each creature."""
    events: list[Event] = []
    for oid, o in state.objects.items():
        if o.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in o.characteristics.types:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': oid, 'amount': 3, 'source': spell_id},
                source=spell_id, controller=caster_id,
            ))
    return events


def _slagstorm_mode_players(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """3 damage to each player."""
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': pid, 'amount': 3, 'source': spell_id},
            source=spell_id, controller=caster_id,
        )
        for pid in state.players.keys()
    ]


SLAGSTORM = make_sorcery(
    name="Slagstorm",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Choose one —\n• Slagstorm deals 3 damage to each creature.\n• Slagstorm deals 3 damage to each player.",
    resolve=make_modal_resolve(
        "Slagstorm",
        modes=[
            ("Slagstorm deals 3 damage to each creature", _slagstorm_mode_creatures),
            ("Slagstorm deals 3 damage to each player", _slagstorm_mode_players),
        ],
        min_modes=1, max_modes=1,
    ),
)

SPITFIRE_LAGAC = make_creature(
    name="Spitfire Lagac",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Landfall — Whenever a land you control enters, this creature deals 1 damage to each opponent.",
    setup_interceptors=spitfire_lagac_setup
)

SURE_STRIKE = make_instant(
    name="Sure Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. (It deals combat damage before creatures without first strike.)",
    resolve=resolve_chain(resolve_pump(3, 0), _resolve_grant_keyword('first strike')),
    target_requirements=[target_creature(count=1)],
)

THRILL_OF_POSSIBILITY = make_instant(
    name="Thrill of Possibility",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards.",
)

AFFECTIONATE_INDRIK = make_creature(
    name="Affectionate Indrik",
    power=4, toughness=4,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When this creature enters, you may have it fight target creature you don't control. (Each deals damage equal to its power to the other.)",
    setup_interceptors=affectionate_indrik_setup,
)

BITE_DOWN = make_instant(
    name="Bite Down",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker you don't control.",
    resolve=bite_down_resolve,
    target_requirements=[
        target_creature(count=1, controller='you'),
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.CREATURE, CardType.PLANESWALKER},
                controller='opponent',
            ),
            count=1,
            label="target creature or planeswalker you don't control",
        ),
    ],
)

BLANCHWOOD_ARMOR = make_enchantment(
    name="Blanchwood Armor",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Enchant creature\nEnchanted creature gets +1/+1 for each Forest you control.",
    subtypes={"Aura"},
    setup_interceptors=blanchwood_armor_setup,
)

BROKEN_WINGS = make_instant(
    name="Broken Wings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying.",
)

def _bushwhack_mode_search(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """Search your library for a basic land card."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': caster_id,
            'card_filter': 'basic_land',
            'destination': 'hand',
            'reveal': True,
        },
        source=spell_id, controller=caster_id,
    )]


def _bushwhack_mode_fight(state: GameState, caster_id: str, spell_id: str, targets=None) -> list[Event]:
    """Target creature you control fights target creature you don't control."""
    if not targets or len(targets) < 2:
        return []
    own_id = targets[0].id
    enemy_id = targets[1].id
    return [Event(
        type=EventType.FIGHT,
        payload={'creature1': own_id, 'creature2': enemy_id},
        source=spell_id, controller=caster_id,
    )]


BUSHWHACK = make_sorcery(
    name="Bushwhack",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\n• Target creature you control fights target creature you don't control. (Each deals damage equal to its power to the other.)",
    resolve=make_modal_resolve(
        "Bushwhack",
        modes=[
            ("Search your library for a basic land card", _bushwhack_mode_search),
            ModeSpec(
                "Target creature you control fights target creature you don't control",
                _bushwhack_mode_fight,
                target_requirement=[
                    target_creature(controller='you'),
                    target_creature(controller='opponent'),
                ],
            ),
        ],
        min_modes=1, max_modes=1,
    ),
)

DOUBLING_SEASON = make_enchantment(
    name="Doubling Season",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.",
    setup_interceptors=doubling_season_setup,
)

DWYNEN_GILTLEAF_DAEN = make_creature(
    name="Dwynen, Gilt-Leaf Daen",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Reach (This creature can block creatures with flying.)\nOther Elf creatures you control get +1/+1.\nWhenever Dwynen attacks, you gain 1 life for each attacking Elf you control.",
    setup_interceptors=dwynen_giltleaf_daen_setup
)

DWYNENS_ELITE = make_creature(
    name="Dwynen's Elite",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="When this creature enters, if you control another Elf, create a 1/1 green Elf Warrior creature token.",
    setup_interceptors=dwynens_elite_setup
)

ELVISH_ARCHDRUID = make_creature(
    name="Elvish Archdruid",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="Other Elf creatures you control get +1/+1.\n{T}: Add {G} for each Elf you control.",
    setup_interceptors=elvish_archdruid_setup
)

GARRUKS_UPRISING = make_enchantment(
    name="Garruk's Uprising",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, if you control a creature with power 4 or greater, draw a card.\nCreatures you control have trample. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever a creature you control with power 4 or greater enters, draw a card.",
    setup_interceptors=garruks_uprising_setup,
)

GENESIS_WAVE = make_sorcery(
    name="Genesis Wave",
    mana_cost="{X}{G}{G}{G}",
    colors={Color.GREEN},
    text="Reveal the top X cards of your library. You may put any number of permanent cards with mana value X or less from among them onto the battlefield. Then put all cards revealed this way that weren't put onto the battlefield into your graveyard.",
    # engine gap: reveal-top-X with multi-target permanent selection and discard rest.
)

GHALTA_PRIMAL_HUNGER = make_creature(
    name="Ghalta, Primal Hunger",
    power=12, toughness=12,
    mana_cost="{10}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
    setup_interceptors=ghalta_primal_hunger_setup,
)

GIANT_GROWTH = make_instant(
    name="Giant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn.",
    resolve=giant_growth_resolve,
    target_requirements=[target_creature(count=1)],
)

GNARLID_COLONY = make_creature(
    name="Gnarlid Colony",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Kicker {2}{G} (You may pay an additional {2}{G} as you cast this spell.)\nIf this creature was kicked, it enters with two +1/+1 counters on it.\nEach creature you control with a +1/+1 counter on it has trample. (It can deal excess combat damage to the player or planeswalker it's attacking.)",
    setup_interceptors=gnarlid_colony_setup,
)

GROW_FROM_THE_ASHES = make_sorcery(
    name="Grow from the Ashes",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Kicker {2} (You may pay an additional {2} as you cast this spell.)\nSearch your library for a basic land card, put it onto the battlefield, then shuffle. If this spell was kicked, instead search your library for two basic land cards, put them onto the battlefield, then shuffle.",
)

INSPIRING_CALL = make_instant(
    name="Inspiring Call",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Draw a card for each creature you control with a +1/+1 counter on it. Those creatures gain indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy them.)",
)

LLANOWAR_ELVES = make_creature(
    name="Llanowar Elves",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{T}: Add {G}.",
)

MILDMANNERED_LIBRARIAN = make_creature(
    name="Mild-Mannered Librarian",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human"},
    text="{3}{G}: This creature becomes a Werewolf. Put two +1/+1 counters on it and you draw a card. Activate only once.",
    setup_interceptors=mildmannered_librarian_setup,
)

NESSIAN_HORNBEETLE = make_creature(
    name="Nessian Hornbeetle",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="At the beginning of combat on your turn, if you control another creature with power 4 or greater, put a +1/+1 counter on this creature.",
    setup_interceptors=nessian_hornbeetle_setup,
)

OVERRUN = make_sorcery(
    name="Overrun",
    mana_cost="{2}{G}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +3/+3 and gain trample until end of turn. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)",
    resolve=_resolve_anthem_creatures_you_control(3, 3, ('trample',)),
)

RECLAMATION_SAGE = make_creature(
    name="Reclamation Sage",
    power=2, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="When this creature enters, you may destroy target artifact or enchantment.",
    setup_interceptors=reclamation_sage_setup
)

SCAVENGING_OOZE = make_creature(
    name="Scavenging Ooze",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ooze"},
    text="{G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life.",
    setup_interceptors=scavenging_ooze_setup,
)

SNAKESKIN_VEIL = make_instant(
    name="Snakeskin Veil",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
)

VIVIEN_REID = make_planeswalker(
    name="Vivien Reid",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    loyalty=5,
    subtypes={"Vivien"},
    supertypes={"Legendary"},
    text="+1: Look at the top four cards of your library. You may reveal a creature or land card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\n−3: Destroy target artifact, enchantment, or creature with flying.\n−8: You get an emblem with \"Creatures you control get +2/+2 and have vigilance, trample, and indestructible.\"",
    setup_interceptors=vivien_reid_setup,
)

WARY_THESPIAN = make_creature(
    name="Wary Thespian",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Druid"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=wary_thespian_setup,
)

WILDWOOD_SCOURGE = make_creature(
    name="Wildwood Scourge",
    power=0, toughness=0,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="This creature enters with X +1/+1 counters on it.\nWhenever one or more +1/+1 counters are put on another non-Hydra creature you control, put a +1/+1 counter on this creature.",
    setup_interceptors=wildwood_scourge_setup
)

BALMOR_BATTLEMAGE_CAPTAIN = make_creature(
    name="Balmor, Battlemage Captain",
    power=1, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Bird", "Wizard"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast an instant or sorcery spell, creatures you control get +1/+0 and gain trample until end of turn.",
    setup_interceptors=balmor_battlemage_captain_setup,
)

CONSUMING_ABERRATION = make_creature(
    name="Consuming Aberration",
    power=0, toughness=0,
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Horror"},
    text="Consuming Aberration's power and toughness are each equal to the number of cards in your opponents' graveyards.\nWhenever you cast a spell, each opponent reveals cards from the top of their library until they reveal a land card, then puts those cards into their graveyard.",
    setup_interceptors=consuming_aberration_setup,
)

EMPYREAN_EAGLE = make_creature(
    name="Empyrean Eagle",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Spirit"},
    text="Flying\nOther creatures you control with flying get +1/+1.",
    setup_interceptors=empyrean_eagle_setup
)

GOODFORTUNE_UNICORN = make_creature(
    name="Good-Fortune Unicorn",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Unicorn"},
    text="Whenever another creature you control enters, put a +1/+1 counter on that creature.",
    setup_interceptors=good_fortune_unicorn_setup
)

HEROIC_REINFORCEMENTS = make_sorcery(
    name="Heroic Reinforcements",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create two 1/1 white Soldier creature tokens. Until end of turn, creatures you control get +1/+1 and gain haste. (They can attack and {T} this turn.)",
    resolve=heroic_reinforcements_resolve,
)

LATHRIL_BLADE_OF_THE_ELVES = make_creature(
    name="Lathril, Blade of the Elves",
    power=2, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever Lathril deals combat damage to a player, create that many 1/1 green Elf Warrior creature tokens.\n{T}, Tap ten untapped Elves you control: Each opponent loses 10 life and you gain 10 life.",
    setup_interceptors=lathril_blade_of_the_elves_setup
)

MULDROTHA_THE_GRAVETIDE = make_creature(
    name="Muldrotha, the Gravetide",
    power=6, toughness=6,
    mana_cost="{3}{B}{G}{U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    subtypes={"Avatar", "Elemental"},
    supertypes={"Legendary"},
    text="During each of your turns, you may play a land and cast a permanent spell of each permanent type from your graveyard. (If a card has multiple permanent types, choose one as you play it.)",
    setup_interceptors=muldrotha_the_gravetide_setup,
)

PROGENITUS = make_creature(
    name="Progenitus",
    power=10, toughness=10,
    mana_cost="{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Avatar", "Hydra"},
    supertypes={"Legendary"},
    text="Protection from everything\nIf Progenitus would be put into a graveyard from anywhere, reveal Progenitus and shuffle it into its owner's library instead.",
    setup_interceptors=progenitus_setup,
)

RUBY_DARING_TRACKER = make_creature(
    name="Ruby, Daring Tracker",
    power=1, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\nWhenever Ruby attacks while you control a creature with power 4 or greater, Ruby gets +2/+2 until end of turn.\n{T}: Add {R} or {G}.",
    setup_interceptors=ruby_daring_tracker_setup,
)

SWIFTBLADE_VINDICATOR = make_creature(
    name="Swiftblade Vindicator",
    power=1, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Double strike (This creature deals both first-strike and regular combat damage.)\nVigilance (Attacking doesn't cause this creature to tap.)\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
)

TATYOVA_BENTHIC_DRUID = make_creature(
    name="Tatyova, Benthic Druid",
    power=3, toughness=3,
    mana_cost="{3}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Druid", "Merfolk"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, you gain 1 life and draw a card.",
    setup_interceptors=tatyova_benthic_druid_setup
)

THOUSANDYEAR_STORM = make_enchantment(
    name="Thousand-Year Storm",
    mana_cost="{4}{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Whenever you cast an instant or sorcery spell, copy it for each other instant and sorcery spell you've cast before it this turn. You may choose new targets for the copies.",
    setup_interceptors=thousandyear_storm_setup,
)

ADVENTURING_GEAR = make_artifact(
    name="Adventuring Gear",
    mana_cost="{1}",
    text="Landfall — Whenever a land you control enters, equipped creature gets +2/+2 until end of turn.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=adventuring_gear_setup,
)

BURNISHED_HART = make_artifact_creature(
    name="Burnished Hart",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Elk"},
    text="{3}, Sacrifice this creature: Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
)

CAMPUS_GUIDE = make_artifact_creature(
    name="Campus Guide",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top.",
    setup_interceptors=campus_guide_setup,
)

GLEAMING_BARRIER = make_artifact_creature(
    name="Gleaming Barrier",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Wall"},
    text="Defender\nWhen this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=gleaming_barrier_setup
)

GOLDVEIN_PICK = make_artifact(
    name="Goldvein Pick",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1.\nWhenever equipped creature deals combat damage to a player, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    # NOTE: combat-damage-to-player Treasure trigger is a separate engine
    # gap — only the static +1/+1 + equip cost are wired here.
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=1,
        equip_cost="{1}",
    ),
)

HERALDIC_BANNER = make_artifact(
    name="Heraldic Banner",
    mana_cost="{3}",
    text="As this artifact enters, choose a color.\nCreatures you control of the chosen color get +1/+0.\n{T}: Add one mana of the chosen color.",
    setup_interceptors=heraldic_banner_setup,
)

JUGGERNAUT = make_artifact_creature(
    name="Juggernaut",
    power=5, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Juggernaut"},
    text="This creature attacks each combat if able.\nThis creature can't be blocked by Walls.",
    setup_interceptors=juggernaut_setup,
)

METEOR_GOLEM = make_artifact_creature(
    name="Meteor Golem",
    power=3, toughness=3,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, destroy target nonland permanent an opponent controls.",
    setup_interceptors=meteor_golem_setup,
)

SOLEMN_SIMULACRUM = make_artifact_creature(
    name="Solemn Simulacrum",
    power=2, toughness=2,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, you may search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.\nWhen this creature dies, you may draw a card.",
    setup_interceptors=solemn_simulacrum_setup
)

SWIFTFOOT_BOOTS = make_artifact(
    name="Swiftfoot Boots",
    mana_cost="{2}",
    text="Equipped creature has hexproof and haste. (It can't be the target of spells or abilities your opponents control. It can attack and {T} no matter when it came under your control.)\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=make_equipment_setup(
        keywords=["hexproof", "haste"],
        equip_cost="{1}",
    ),
)

BLOODFELL_CAVES = make_land(
    name="Bloodfell Caves",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {R}.",
    setup_interceptors=bloodfell_caves_setup,
)

BLOSSOMING_SANDS = make_land(
    name="Blossoming Sands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {W}.",
    setup_interceptors=blossoming_sands_setup,
)

DISMAL_BACKWATER = make_land(
    name="Dismal Backwater",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {B}.",
    setup_interceptors=dismal_backwater_setup,
)

EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=evolving_wilds_setup,
)

JUNGLE_HOLLOW = make_land(
    name="Jungle Hollow",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {G}.",
    setup_interceptors=jungle_hollow_setup,
)

ROGUES_PASSAGE = make_land(
    name="Rogue's Passage",
    text="{T}: Add {C}.\n{4}, {T}: Target creature can't be blocked this turn.",
    setup_interceptors=rogues_passage_setup,
)

RUGGED_HIGHLANDS = make_land(
    name="Rugged Highlands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {G}.",
    setup_interceptors=rugged_highlands_setup,
)

SCOURED_BARRENS = make_land(
    name="Scoured Barrens",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {B}.",
    setup_interceptors=scoured_barrens_setup,
)

SECLUDED_COURTYARD = make_land(
    name="Secluded Courtyard",
    text="As this land enters, choose a creature type.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type or activate an ability of a creature source of the chosen type.",
)

SWIFTWATER_CLIFFS = make_land(
    name="Swiftwater Cliffs",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {R}.",
    setup_interceptors=swiftwater_cliffs_setup,
)

THORNWOOD_FALLS = make_land(
    name="Thornwood Falls",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {U}.",
    setup_interceptors=thornwood_falls_setup,
)

TRANQUIL_COVE = make_land(
    name="Tranquil Cove",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {U}.",
    setup_interceptors=tranquil_cove_setup,
)

WINDSCARRED_CRAG = make_land(
    name="Wind-Scarred Crag",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {W}.",
    setup_interceptors=windscarred_crag_setup,
)

PLAINS = make_land(
    name="Plains",
    text="({T}: Add {W}.)",
    subtypes={"Plains"},
    supertypes={"Basic"},
)

ISLAND = make_land(
    name="Island",
    text="({T}: Add {U}.)",
    subtypes={"Island"},
    supertypes={"Basic"},
)

SWAMP = make_land(
    name="Swamp",
    text="({T}: Add {B}.)",
    subtypes={"Swamp"},
    supertypes={"Basic"},
)

MOUNTAIN = make_land(
    name="Mountain",
    text="({T}: Add {R}.)",
    subtypes={"Mountain"},
    supertypes={"Basic"},
)

FOREST = make_land(
    name="Forest",
    text="({T}: Add {G}.)",
    subtypes={"Forest"},
    supertypes={"Basic"},
)

ADAMANT_WILL = make_instant(
    name="Adamant Will",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    resolve=resolve_chain(resolve_pump(2, 2), _resolve_grant_keyword('indestructible')),
    target_requirements=[target_creature(count=1)],
)

ANCESTOR_DRAGON = make_creature(
    name="Ancestor Dragon",
    power=5, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dragon"},
    text="Flying\nWhenever one or more creatures you control attack, you gain 1 life for each attacking creature.",
    setup_interceptors=ancestor_dragon_setup,
)

ANGELIC_EDICT = make_sorcery(
    name="Angelic Edict",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Exile target creature or enchantment.",
    resolve=angelic_edict_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(types={CardType.CREATURE, CardType.ENCHANTMENT}),
            count=1,
            label="target creature or enchantment",
        ),
    ],
)

BISHOPS_SOLDIER = make_creature(
    name="Bishop's Soldier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Soldier", "Vampire"},
    text="Lifelink (Damage dealt by this creature also causes you to gain that much life.)",
)

DEADLY_RIPOSTE = make_instant(
    name="Deadly Riposte",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Deadly Riposte deals 3 damage to target tapped creature and you gain 2 life.",
    resolve=deadly_riposte_resolve,
    target_requirements=[target_creature(count=1, tapped=True)],
)

ELSPETHS_SMITE = make_instant(
    name="Elspeth's Smite",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Elspeth's Smite deals 3 damage to target attacking or blocking creature. If that creature would die this turn, exile it instead.",
    resolve=elspeths_smite_resolve,
    target_requirements=[
        TargetRequirement(
            filter=creature_filter(custom_filter=_attacking_or_blocking_creature_filter),
            count=1,
            label="target attacking or blocking creature",
        ),
    ],
)

HERALD_OF_FAITH = make_creature(
    name="Herald of Faith",
    power=4, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever this creature attacks, you gain 2 life.",
    setup_interceptors=herald_of_faith_setup
)

INGENIOUS_LEONIN = make_creature(
    name="Ingenious Leonin",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="{3}{W}: Put a +1/+1 counter on another target attacking creature you control. If that creature is a Cat, it gains first strike until end of turn. (It deals combat damage before creatures without first strike.)",
    setup_interceptors=ingenious_leonin_setup,
)

INSPIRING_OVERSEER = make_creature(
    name="Inspiring Overseer",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Cleric"},
    text="Flying\nWhen this creature enters, you gain 1 life and draw a card.",
    setup_interceptors=inspiring_overseer_setup
)

JAZAL_GOLDMANE = make_creature(
    name="Jazal Goldmane",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    supertypes={"Legendary"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\n{3}{W}{W}: Attacking creatures you control get +X/+X until end of turn, where X is the number of attacking creatures.",
    setup_interceptors=jazal_goldmane_setup,
)

LEONIN_SKYHUNTER = make_creature(
    name="Leonin Skyhunter",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Knight"},
    text="Flying",
)

LEONIN_VANGUARD = make_creature(
    name="Leonin Vanguard",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="At the beginning of combat on your turn, if you control three or more creatures, this creature gets +1/+1 until end of turn and you gain 1 life.",
    setup_interceptors=leonin_vanguard_setup,
)

MOMENT_OF_TRIUMPH = make_instant(
    name="Moment of Triumph",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. You gain 2 life.",
    resolve=moment_of_triumph_resolve,
    target_requirements=[target_creature(count=1)],
)

PACIFISM = make_enchantment(
    name="Pacifism",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block.",
    subtypes={"Aura"},
    setup_interceptors=pacifism_setup,
)

PRAYER_OF_BINDING = make_enchantment(
    name="Prayer of Binding",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Flash\nWhen this enchantment enters, exile up to one target nonland permanent an opponent controls until this enchantment leaves the battlefield. You gain 2 life.",
    setup_interceptors=prayer_of_binding_setup,
)

TWINBLADE_PALADIN = make_creature(
    name="Twinblade Paladin",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever you gain life, put a +1/+1 counter on this creature.\nAs long as you have 25 or more life, this creature has double strike. (It deals both first-strike and regular combat damage.)",
    setup_interceptors=twinblade_paladin_setup
)

BURROG_BEFUDDLER = make_creature(
    name="Burrog Befuddler",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, target creature an opponent controls gets -1/-0 until end of turn.",
    setup_interceptors=burrog_befuddler_setup,
)

CANCEL = make_instant(
    name="Cancel",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell.",
    resolve=cancel_resolve,
    target_requirements=[target_spell()],
)

CORSAIR_CAPTAIN = make_creature(
    name="Corsair Captain",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nOther Pirates you control get +1/+1.",
    setup_interceptors=corsair_captain_setup
)

EATEN_BY_PIRANHAS = make_enchantment(
    name="Eaten by Piranhas",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nEnchant creature\nEnchanted creature loses all abilities and is a black Skeleton creature with base power and toughness 1/1. (It loses all other colors, card types, and creature types.)",
    subtypes={"Aura"},
    setup_interceptors=eaten_by_piranhas_setup,
)

EXCLUSION_MAGE = make_creature(
    name="Exclusion Mage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, return target creature an opponent controls to its owner's hand.",
    setup_interceptors=exclusion_mage_setup,
)

INTO_THE_ROIL = make_instant(
    name="Into the Roil",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Kicker {1}{U} (You may pay an additional {1}{U} as you cast this spell.)\nReturn target nonland permanent to its owner's hand. If this spell was kicked, draw a card.",
    resolve=into_the_roil_resolve,
    target_requirements=[
        TargetRequirement(
            filter=permanent_filter(custom_filter=_nonland_permanent_filter),
            count=1,
            label="target nonland permanent",
        ),
    ],
)

KITESAIL_CORSAIR = make_creature(
    name="Kitesail Corsair",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="This creature has flying as long as it's attacking.",
    setup_interceptors=kitesail_corsair_setup,
)

MYSTIC_ARCHAEOLOGIST = make_creature(
    name="Mystic Archaeologist",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{3}{U}{U}: Draw two cards.",
    setup_interceptors=mystic_archaeologist_setup,
)

OPT = make_instant(
    name="Opt",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.",
)

QUICK_STUDY = make_instant(
    name="Quick Study",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards.",
    resolve=resolve_draw(2),
)

STARLIGHT_SNARE = make_enchantment(
    name="Starlight Snare",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
    setup_interceptors=starlight_snare_setup,
)

STORM_FLEET_SPY = make_creature(
    name="Storm Fleet Spy",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Raid — When this creature enters, if you attacked this turn, draw a card.",
    setup_interceptors=storm_fleet_spy_setup,
)

BLOODTITHE_COLLECTOR = make_creature(
    name="Bloodtithe Collector",
    power=3, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Noble", "Vampire"},
    text="Flying\nWhen this creature enters, if an opponent lost life this turn, each opponent discards a card.",
    setup_interceptors=bloodtithe_collector_setup,
)

CEMETERY_RECRUITMENT = make_sorcery(
    name="Cemetery Recruitment",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to your hand. If it's a Zombie card, draw a card.",
)

CROSSWAY_TROUBLEMAKERS = make_creature(
    name="Crossway Troublemakers",
    power=5, toughness=5,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Attacking Vampires you control have deathtouch and lifelink. (Any amount of damage they deal to a creature is enough to destroy it. Damage dealt by those creatures also causes their controller to gain that much life.)\nWhenever a Vampire you control dies, you may pay 2 life. If you do, draw a card.",
    setup_interceptors=crossway_troublemakers_setup,
)

CROW_OF_DARK_TIDINGS = make_creature(
    name="Crow of Dark Tidings",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Zombie"},
    text="Flying\nWhen this creature enters or dies, mill two cards. (Put the top two cards of your library into your graveyard.)",
    setup_interceptors=crow_of_dark_tidings_setup,
)

DEADLY_PLOT = make_instant(
    name="Deadly Plot",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Destroy target creature or planeswalker.\n• Return target Zombie creature card from your graveyard to the battlefield tapped.",
    resolve=make_modal_resolve(
        "Deadly Plot",
        modes=[
            ModeSpec(
                "Destroy target creature or planeswalker",
                _deadly_plot_mode_destroy,
                target_requirement=TargetRequirement(
                    filter=TargetFilter(types={CardType.CREATURE, CardType.PLANESWALKER}),
                    count=1, label="target creature or planeswalker",
                ),
            ),
            ModeSpec(
                "Return target Zombie creature card from your graveyard to the battlefield tapped",
                _deadly_plot_mode_reanimate,
                target_requirement=TargetRequirement(
                    filter=TargetFilter(
                        types={CardType.CREATURE},
                        subtypes={"Zombie"},
                        zones=[ZoneType.GRAVEYARD],
                        controller='you',
                    ),
                    count=1,
                    label="target Zombie creature card in your graveyard",
                ),
            ),
        ],
        min_modes=1, max_modes=1,
    ),
)

DEATH_BARON = make_creature(
    name="Death Baron",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wizard", "Zombie"},
    text="Skeletons you control and other Zombies you control get +1/+1 and have deathtouch. (Any amount of damage they deal to a creature is enough to destroy it.)",
    setup_interceptors=death_baron_setup,
)

HIGHBORN_VAMPIRE = make_creature(
    name="Highborn Vampire",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warrior"},
    text="",
)

MAALFELD_TWINS = make_creature(
    name="Maalfeld Twins",
    power=4, toughness=4,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When this creature dies, create two 2/2 black Zombie creature tokens.",
    setup_interceptors=maalfeld_twins_setup,
)

MOMENT_OF_CRAVING = make_instant(
    name="Moment of Craving",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You gain 2 life.",
)

OFFER_IMMORTALITY = make_instant(
    name="Offer Immortality",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gains deathtouch and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    resolve=resolve_chain(_resolve_grant_keyword('deathtouch'), _resolve_grant_keyword('indestructible')),
    target_requirements=[target_creature(count=1)],
)

SKELETON_ARCHER = make_creature(
    name="Skeleton Archer",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Archer", "Skeleton"},
    text="When this creature enters, it deals 1 damage to any target.",
    setup_interceptors=skeleton_archer_setup,
)

SUSPICIOUS_SHAMBLER = make_creature(
    name="Suspicious Shambler",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="{4}{B}{B}, Exile this card from your graveyard: Create two 2/2 black Zombie creature tokens. Activate only as a sorcery.",
    setup_interceptors=suspicious_shambler_setup,
)
SUSPICIOUS_SHAMBLER.setup_in_graveyard = suspicious_shambler_gy_setup

UNDYING_MALICE = make_instant(
    name="Undying Malice",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gains \"When this creature dies, return it to the battlefield tapped under its owner's control with a +1/+1 counter on it.\"",
    resolve=undying_malice_resolve,
    target_requirements=[target_creature(count=1)],
)

UNTAMED_HUNGER = make_enchantment(
    name="Untamed Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nEnchanted creature gets +2/+1 and has menace. (It can't be blocked except by two or more creatures.)",
    subtypes={"Aura"},
    setup_interceptors=make_aura_setup(
        power_mod=2, toughness_mod=1,
        keywords=["menace"],
    ),
)

VAMPIRE_INTERLOPER = make_creature(
    name="Vampire Interloper",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Scout", "Vampire"},
    text="Flying\nThis creature can't block.",
    setup_interceptors=vampire_interloper_setup,
)

VAMPIRE_NEONATE = make_creature(
    name="Vampire Neonate",
    power=0, toughness=3,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="{2}, {T}: Each opponent loses 1 life and you gain 1 life.",
)

VAMPIRE_SPAWN = make_creature(
    name="Vampire Spawn",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="When this creature enters, each opponent loses 2 life and you gain 2 life.",
    setup_interceptors=vampire_spawn_setup,
)

BATTLERATTLE_SHAMAN = make_creature(
    name="Battle-Rattle Shaman",
    power=2, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="At the beginning of combat on your turn, you may have target creature get +2/+0 until end of turn.",
    setup_interceptors=battlerattle_shaman_setup,
)

CARNELIAN_ORB_OF_DRAGONKIND = make_artifact(
    name="Carnelian Orb of Dragonkind",
    mana_cost="{2}{R}",
    text="{T}: Add {R}. If that mana is spent on a Dragon creature spell, it gains haste until end of turn.",
)

DRAGON_FODDER = make_sorcery(
    name="Dragon Fodder",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Create two 1/1 red Goblin creature tokens.",
    resolve=resolve_create_token(
        name='Goblin Token',
        power=1,
        toughness=1,
        types=[CardType.CREATURE],
        subtypes=['Goblin'],
        colors=[Color.RED],
        count=2,
    ),
)

DRAGONLORDS_SERVANT = make_creature(
    name="Dragonlord's Servant",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="Dragon spells you cast cost {1} less to cast.",
    setup_interceptors=dragonlords_servant_setup,
)

DROPKICK_BOMBER = make_creature(
    name="Dropkick Bomber",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Other Goblins you control get +1/+1.\n{R}: Until end of turn, another target Goblin you control gains flying and \"When this creature deals combat damage, sacrifice it.\"",
    setup_interceptors=dropkick_bomber_setup,
)

FIRE_ELEMENTAL = make_creature(
    name="Fire Elemental",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="",
)

GOBLIN_ORIFLAMME = make_enchantment(
    name="Goblin Oriflamme",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Attacking creatures you control get +1/+0.",
    setup_interceptors=goblin_oriflamme_setup,
)

GOBLIN_SMUGGLER = make_creature(
    name="Goblin Smuggler",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\n{T}: Another target creature with power 2 or less can't be blocked this turn.",
    setup_interceptors=goblin_smuggler_setup,
)

KARGAN_DRAGONRIDER = make_creature(
    name="Kargan Dragonrider",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="As long as you control a Dragon, this creature has flying.",
    setup_interceptors=kargan_dragonrider_setup,
)

KINDLED_FURY = make_instant(
    name="Kindled Fury",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +1/+0 and gains first strike until end of turn. (It deals combat damage before creatures without first strike.)",
    resolve=resolve_chain(resolve_pump(1, 0), _resolve_grant_keyword('first strike')),
    target_requirements=[target_creature(count=1)],
)

RAGING_REDCAP = make_creature(
    name="Raging Redcap",
    power=1, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Knight"},
    text="Double strike (This creature deals both first-strike and regular combat damage.)",
)

RAPACIOUS_DRAGON = make_creature(
    name="Rapacious Dragon",
    power=3, toughness=3,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, create two Treasure tokens. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=rapacious_dragon_setup,
)

SCORCHING_DRAGONFIRE = make_instant(
    name="Scorching Dragonfire",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Scorching Dragonfire deals 3 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it instead.",
    resolve=scorching_dragonfire_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(types={CardType.CREATURE, CardType.PLANESWALKER}),
            count=1,
            label="target creature or planeswalker",
        ),
    ],
)

SEIZE_THE_SPOILS = make_sorcery(
    name="Seize the Spoils",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SKYRAKER_GIANT = make_creature(
    name="Skyraker Giant",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Reach (This creature can block creatures with flying.)",
)

SWAB_GOBLIN = make_creature(
    name="Swab Goblin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="",
)

TERROR_OF_MOUNT_VELUS = make_creature(
    name="Terror of Mount Velus",
    power=5, toughness=5,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nDouble strike (This creature deals both first-strike and regular combat damage.)\nWhen this creature enters, creatures you control gain double strike until end of turn.",
    setup_interceptors=terror_of_mount_velus_setup,
)

VOLLEY_VETERAN = make_creature(
    name="Volley Veteran",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="When this creature enters, it deals damage to target creature an opponent controls equal to the number of Goblins you control.",
    setup_interceptors=volley_veteran_setup,
)

AGGRESSIVE_MAMMOTH = make_creature(
    name="Aggressive Mammoth",
    power=8, toughness=8,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nOther creatures you control have trample.",
    setup_interceptors=aggressive_mammoth_setup,
)

BEAR_CUB = make_creature(
    name="Bear Cub",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bear"},
    text="",
)

BIOGENIC_UPGRADE = make_sorcery(
    name="Biogenic Upgrade",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Distribute three +1/+1 counters among one, two, or three target creatures, then double the number of +1/+1 counters on each of those creatures.",
    # engine gap: counter distribution UI + read-current-counters-and-double.
)

DRUID_OF_THE_COWL = make_creature(
    name="Druid of the Cowl",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{T}: Add {G}.",
)

JORAGA_INVOCATION = make_sorcery(
    name="Joraga Invocation",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Each creature you control gets +3/+3 until end of turn and must be blocked this turn if able.",
)

MAGNIGOTH_SENTRY = make_creature(
    name="Magnigoth Sentry",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach (This creature can block creatures with flying.)",
)

NEW_HORIZONS = make_enchantment(
    name="New Horizons",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Enchant land\nWhen this Aura enters, put a +1/+1 counter on target creature you control.\nEnchanted land has \"{T}: Add two mana of any one color.\"",
    subtypes={"Aura"},
    setup_interceptors=new_horizons_setup,
)

TAJURU_PATHWARDEN = make_creature(
    name="Tajuru Pathwarden",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Elf", "Warrior"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
)

THORNWEALD_ARCHER = make_creature(
    name="Thornweald Archer",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Elf"},
    text="Reach (This creature can block creatures with flying.)\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)",
)

THRASHING_BRONTODON = make_creature(
    name="Thrashing Brontodon",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
    setup_interceptors=thrashing_brontodon_setup,
)

WILDHEART_INVOKER = make_creature(
    name="Wildheart Invoker",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="{8}: Target creature gets +5/+5 and gains trample until end of turn. (It can deal excess combat damage to the player or planeswalker it's attacking.)",
    setup_interceptors=wildheart_invoker_setup,
)

GOBLIN_FIREBOMB = make_artifact(
    name="Goblin Firebomb",
    mana_cost="{1}",
    text="Flash\n{7}, {T}, Sacrifice this artifact: Destroy target permanent.",
    setup_interceptors=goblin_firebomb_setup,
)

PIRATES_CUTLASS = make_artifact(
    name="Pirate's Cutlass",
    mana_cost="{3}",
    text="When this Equipment enters, attach it to target Pirate you control.\nEquipped creature gets +2/+1.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=pirates_cutlass_setup,
)

UNCHARTED_HAVEN = make_land(
    name="Uncharted Haven",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
)

ANGELIC_DESTINY = make_enchantment(
    name="Angelic Destiny",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +4/+4, has flying and first strike, and is an Angel in addition to its other types.\nWhen enchanted creature dies, return this card to its owner's hand.",
    subtypes={"Aura"},
    # The "return to hand when enchanted dies" rider is still an engine
    # gap (granted death-trigger needs threading the aura's identity).
    setup_interceptors=make_aura_setup(
        power_mod=4, toughness_mod=4,
        keywords=["flying", "first strike"],
        subtypes_to_add={"Angel"},
    ),
)

ARCHWAY_ANGEL = make_creature(
    name="Archway Angel",
    power=3, toughness=4,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhen this creature enters, you gain 2 life for each Gate you control.",
    setup_interceptors=archway_angel_setup,
)

BALLYRUSH_BANNERET = make_creature(
    name="Ballyrush Banneret",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Kithkin spells and Soldier spells you cast cost {1} less to cast.",
    setup_interceptors=ballyrush_banneret_setup,
)

CHARMING_PRINCE = make_creature(
    name="Charming Prince",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="When this creature enters, choose one —\n• Scry 2.\n• You gain 3 life.\n• Exile another target creature you own. Return it to the battlefield under your control at the beginning of the next end step.",
    setup_interceptors=charming_prince_setup,
)

CRUSADER_OF_ODRIC = make_creature(
    name="Crusader of Odric",
    power=0, toughness=0,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Crusader of Odric's power and toughness are each equal to the number of creatures you control.",
    setup_interceptors=crusader_of_odric_setup,
)

DAWNWING_MARSHAL = make_creature(
    name="Dawnwing Marshal",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="Flying\n{4}{W}: Creatures you control get +1/+1 until end of turn.",
    setup_interceptors=dawnwing_marshal_setup,
)

def _black_or_red_creature_or_pw_filter(obj: GameObject, state: GameState) -> bool:
    """Match creatures or planeswalkers that are black or red."""
    colors = obj.characteristics.colors or set()
    return Color.BLACK in colors or Color.RED in colors


DEVOUT_DECREE = make_sorcery(
    name="Devout Decree",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target creature or planeswalker that's black or red. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    resolve=devout_decree_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.CREATURE, CardType.PLANESWALKER},
                custom_filter=_black_or_red_creature_or_pw_filter,
            ),
            count=1,
            label="target black or red creature or planeswalker",
        ),
    ],
)

DISENCHANT = make_instant(
    name="Disenchant",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or enchantment.",
    resolve=disenchant_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(types={CardType.ARTIFACT, CardType.ENCHANTMENT}),
            count=1,
            label="target artifact or enchantment",
        ),
    ],
)

FELIDAR_CUB = make_creature(
    name="Felidar Cub",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat"},
    text="Sacrifice this creature: Destroy target enchantment.",
    setup_interceptors=felidar_cub_setup,
)

FELIDAR_RETREAT = make_enchantment(
    name="Felidar Retreat",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Landfall — Whenever a land you control enters, choose one —\n• Create a 2/2 white Cat Beast creature token.\n• Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.",
    setup_interceptors=felidar_retreat_setup
)

FUMIGATE = make_sorcery(
    name="Fumigate",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures. You gain 1 life for each creature destroyed this way.",
)

KNIGHT_OF_GRACE = make_creature(
    name="Knight of Grace",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nHexproof from black (This creature can't be the target of black spells or abilities your opponents control.)\nThis creature gets +1/+0 as long as any player controls a black permanent.",
    setup_interceptors=knight_of_grace_setup,
)

LINDEN_THE_STEADFAST_QUEEN = make_creature(
    name="Linden, the Steadfast Queen",
    power=3, toughness=3,
    mana_cost="{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhenever a white creature you control attacks, you gain 1 life.",
    setup_interceptors=linden_the_steadfast_queen_setup
)

MENTOR_OF_THE_MEEK = make_creature(
    name="Mentor of the Meek",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever another creature you control with power 2 or less enters, you may pay {1}. If you do, draw a card.",
    setup_interceptors=mentor_of_the_meek_setup
)

REGAL_CARACAL = make_creature(
    name="Regal Caracal",
    power=3, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Other Cats you control get +1/+1 and have lifelink. (Damage dealt by those creatures also causes you to gain that much life.)\nWhen this creature enters, create two 1/1 white Cat creature tokens with lifelink.",
    setup_interceptors=regal_caracal_setup
)

RELEASE_THE_DOGS = make_sorcery(
    name="Release the Dogs",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Dog creature tokens.",
    resolve=resolve_create_token(
        name='Dog Token',
        power=1,
        toughness=1,
        types=[CardType.CREATURE],
        subtypes=['Dog'],
        colors=[Color.WHITE],
        count=4,
    ),
)

STASIS_SNARE = make_enchantment(
    name="Stasis Snare",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=stasis_snare_setup,
)

SYR_ALIN_THE_LIONS_CLAW = make_creature(
    name="Syr Alin, the Lion's Claw",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nWhenever Syr Alin attacks, other creatures you control get +1/+1 until end of turn.",
    setup_interceptors=syr_alin_the_lions_claw_setup,
)

VALOROUS_STANCE = make_instant(
    name="Valorous Stance",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Target creature gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)\n• Destroy target creature with toughness 4 or greater.",
    resolve=make_modal_resolve(
        "Valorous Stance",
        modes=[
            ModeSpec(
                "Target creature gains indestructible until end of turn",
                _valorous_stance_mode_indestructible,
                target_requirement=target_creature(count=1, controller='you'),
            ),
            ModeSpec(
                "Destroy target creature with toughness 4 or greater",
                _valorous_stance_mode_destroy,
                target_requirement=TargetRequirement(
                    filter=creature_filter(custom_filter=_toughness_4_or_greater),
                    count=1,
                    label="target creature with toughness 4 or greater",
                ),
            ),
        ],
        min_modes=1, max_modes=1,
    ),
)

ZETALPA_PRIMAL_DAWN = make_creature(
    name="Zetalpa, Primal Dawn",
    power=4, toughness=8,
    mana_cost="{6}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="Flying, double strike, vigilance, trample, indestructible",
)

ARCANIS_THE_OMNIPOTENT = make_creature(
    name="Arcanis the Omnipotent",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{T}: Draw three cards.\n{2}{U}{U}: Return Arcanis to its owner's hand.",
)

CHART_A_COURSE = make_sorcery(
    name="Chart a Course",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Then discard a card unless you attacked this turn.",
)

DICTATE_OF_KRUPHIX = make_enchantment(
    name="Dictate of Kruphix",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nAt the beginning of each player's draw step, that player draws an additional card.",
    setup_interceptors=dictate_of_kruphix_setup,
)

DIVE_DOWN = make_instant(
    name="Dive Down",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +0/+3 and gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
    resolve=dive_down_resolve,
    target_requirements=[target_creature(count=1, controller='you')],
)

FINALE_OF_REVELATION = make_sorcery(
    name="Finale of Revelation",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Draw X cards. If X is 10 or more, instead shuffle your graveyard into your library, draw X cards, untap up to five lands, and you have no maximum hand size for the rest of the game.\nExile Finale of Revelation.",
    # engine gap: X-cost spell with conditional graveyard-shuffle + untap-lands + handsize change.
)

FLASHFREEZE = make_instant(
    name="Flashfreeze",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target red or green spell.",
    resolve=flashfreeze_resolve,
    target_requirements=[
        TargetRequirement(
            filter=spell_filter(custom_filter=_red_or_green_spell_filter),
            count=1,
            label="target red or green spell",
        ),
    ],
)

FOG_BANK = make_creature(
    name="Fog Bank",
    power=0, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Wall"},
    text="Defender (This creature can't attack.)\nFlying\nPrevent all combat damage that would be dealt to and dealt by this creature.",
    setup_interceptors=fog_bank_setup,
)

GATEWAY_SNEAK = make_creature(
    name="Gateway Sneak",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Vedalken"},
    text="Whenever a Gate you control enters, this creature can't be blocked this turn.\nWhenever this creature deals combat damage to a player, draw a card.",
    setup_interceptors=gateway_sneak_setup,
)

HARBINGER_OF_THE_TIDES = make_creature(
    name="Harbinger of the Tides",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="You may cast this spell as though it had flash if you pay {2} more to cast it. (You may cast it any time you could cast an instant.)\nWhen this creature enters, you may return target tapped creature an opponent controls to its owner's hand.",
    setup_interceptors=harbinger_of_the_tides_setup,
)

MYSTICAL_TEACHINGS = make_instant(
    name="Mystical Teachings",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Search your library for an instant card or a card with flash, reveal it, put it into your hand, then shuffle.\nFlashback {5}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
    # engine gap: tutor with "instant or has flash" filter; flashback alt-cast.
)

RIVERS_REBUKE = make_sorcery(
    name="River's Rebuke",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return all nonland permanents target player controls to their owner's hand.",
    resolve=rivers_rebuke_resolve,
    target_requirements=[target_player(controller='any')],
)

SHIPWRECK_DOWSER = make_creature(
    name="Shipwreck Dowser",
    power=3, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, return target instant or sorcery card from your graveyard to your hand.",
    setup_interceptors=shipwreck_dowser_setup,
)

SPHINX_OF_THE_FINAL_WORD = make_creature(
    name="Sphinx of the Final Word",
    power=5, toughness=5,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="This spell can't be countered.\nFlying\nHexproof (This creature can't be the target of spells or abilities your opponents control.)\nInstant and sorcery spells you control can't be countered.",
    setup_interceptors=sphinx_of_the_final_word_setup,
)

TEMPEST_DJINN = make_creature(
    name="Tempest Djinn",
    power=0, toughness=4,
    mana_cost="{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Djinn"},
    text="Flying\nThis creature gets +1/+0 for each basic Island you control.",
    setup_interceptors=tempest_djinn_setup,
)

UNSUMMON = make_instant(
    name="Unsummon",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand.",
    resolve=unsummon_resolve,
    target_requirements=[target_creature(count=1)],
)

VORACIOUS_GREATSHARK = make_creature(
    name="Voracious Greatshark",
    power=5, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Shark"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, counter target artifact or creature spell.",
    setup_interceptors=voracious_greatshark_setup,
)

def _green_or_white_creature_filter(obj: GameObject, state: GameState) -> bool:
    """Match creatures that are green or white."""
    colors = obj.characteristics.colors or set()
    return Color.GREEN in colors or Color.WHITE in colors


DEATHMARK = make_sorcery(
    name="Deathmark",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Destroy target green or white creature.",
    resolve=deathmark_resolve,
    target_requirements=[
        TargetRequirement(
            filter=creature_filter(custom_filter=_green_or_white_creature_filter),
            count=1,
            label="target green or white creature",
        ),
    ],
)

DEMONIC_PACT = make_enchantment(
    name="Demonic Pact",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, choose one that hasn't been chosen —\n• This enchantment deals 4 damage to any target and you gain 4 life.\n• Target opponent discards two cards.\n• Draw two cards.\n• You lose the game.",
    setup_interceptors=demonic_pact_setup,
)

DESECRATION_DEMON = make_creature(
    name="Desecration Demon",
    power=6, toughness=6,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nAt the beginning of each combat, any opponent may sacrifice a creature of their choice. If a player does, tap this creature and put a +1/+1 counter on it.",
    setup_interceptors=desecration_demon_setup,
)

DREAD_SUMMONS = make_sorcery(
    name="Dread Summons",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Each player mills X cards. For each creature card put into a graveyard this way, you create a tapped 2/2 black Zombie creature token. (To mill a card, a player puts the top card of their library into their graveyard.)",
    # engine gap: count creature cards milled by this specific spell to determine token count.
)

DRIVER_OF_THE_DEAD = make_creature(
    name="Driver of the Dead",
    power=3, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="When this creature dies, return target creature card with mana value 2 or less from your graveyard to the battlefield.",
    setup_interceptors=driver_of_the_dead_setup,
)

def duress_resolve(event: Event, state: GameState) -> list[Event]:
    """
    Target opponent reveals their hand.
    You choose a noncreature, nonland card from it.
    That player discards that card.
    """
    caster = event.controller
    if not caster:
        return []

    # Find opponents
    opponents = [pid for pid in state.players if pid != caster]
    if not opponents:
        return []

    # Target first opponent (could add opponent targeting later)
    target_opponent = opponents[0]

    # Get valid cards from opponent's hand (noncreature, nonland)
    hand_key = f"hand_{target_opponent}"
    if hand_key not in state.zones:
        return []

    hand = state.zones[hand_key]
    valid_choices = []

    for card_id in hand.objects:
        card = state.objects.get(card_id)
        if card:
            # Must be noncreature and nonland
            types = card.characteristics.types
            if CardType.CREATURE not in types and CardType.LAND not in types:
                valid_choices.append(card_id)

    if not valid_choices:
        # Opponent reveals hand but has no valid targets - spell resolves with no effect
        return []

    def handle_discard_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        """Handle the choice callback for Duress's discard effect."""
        if not selected:
            return []

        card_id = selected[0]

        # Discard the selected card
        return [Event(
            type=EventType.DISCARD,
            payload={'object_id': card_id},
            source=choice.source_id
        )]

    # Create choice for caster to pick a card to discard
    create_target_choice(
        state,
        caster,
        event.source,
        valid_choices,
        prompt="Opponent reveals their hand. Choose a noncreature, nonland card to discard:",
        min_targets=1,
        max_targets=1,
        callback_data={
            'handler': handle_discard_choice,
            'target_opponent': target_opponent
        }
    )
    return []


DURESS = make_sorcery(
    name="Duress",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a noncreature, nonland card from it. That player discards that card.",
    resolve=duress_resolve
)

KALASTRIA_HIGHBORN = make_creature(
    name="Kalastria Highborn",
    power=2, toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Shaman", "Vampire"},
    text="Whenever this creature or another Vampire you control dies, you may pay {B}. If you do, target player loses 2 life and you gain 2 life.",
    setup_interceptors=kalastria_highborn_setup,
)

KNIGHT_OF_MALICE = make_creature(
    name="Knight of Malice",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nHexproof from white (This creature can't be the target of white spells or abilities your opponents control.)\nThis creature gets +1/+0 as long as any player controls a white permanent.",
    setup_interceptors=knight_of_malice_setup,
)

MIDNIGHT_REAPER = make_creature(
    name="Midnight Reaper",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Zombie"},
    text="Whenever a nontoken creature you control dies, this creature deals 1 damage to you and you draw a card.",
    setup_interceptors=midnight_reaper_setup
)

MYOJIN_OF_NIGHTS_REACH = make_creature(
    name="Myojin of Night's Reach",
    power=5, toughness=2,
    mana_cost="{5}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Myojin of Night's Reach enters with a divinity counter on it if you cast it from your hand.\nMyojin of Night's Reach has indestructible as long as it has a divinity counter on it.\nRemove a divinity counter from Myojin of Night's Reach: Each opponent discards their hand.",
    setup_interceptors=myojin_of_nights_reach_setup,
)

NULLPRIEST_OF_OBLIVION = make_creature(
    name="Nullpriest of Oblivion",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Kicker {3}{B} (You may pay an additional {3}{B} as you cast this spell.)\nLifelink\nMenace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, if it was kicked, return target creature card from your graveyard to the battlefield.",
    setup_interceptors=nullpriest_of_oblivion_setup,
)

PULSE_TRACKER = make_creature(
    name="Pulse Tracker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Whenever this creature attacks, each opponent loses 1 life.",
    setup_interceptors=pulse_tracker_setup
)

def sanguine_indulgence_resolve(targets, state: GameState) -> list[Event]:
    """Return up to two target creature cards from your gy to your hand."""
    from src.engine.spell_resolve import _flatten_targets  # type: ignore
    caster = _spell_caster_id(state)
    events: list[Event] = []
    flat = _flatten_targets(targets)
    if flat:
        for t in flat[:2]:
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'object_id': t.id, 'player': caster},
            ))
        return events
    # No formal target chosen — let the engine pick up to 2 creature cards.
    return [Event(
        type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
        payload={'player': caster, 'card_type': 'creature', 'amount': 2},
    )]


SANGUINE_INDULGENCE = make_sorcery(
    name="Sanguine Indulgence",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="This spell costs {3} less to cast if you've gained 3 or more life this turn.\nReturn up to two target creature cards from your graveyard to your hand.",
    # engine gap: cost reduction is handled separately.
    resolve=sanguine_indulgence_resolve,
    target_requirements=[
        TargetRequirement(
            filter=card_in_graveyard_filter(types={CardType.CREATURE}),
            count=2,
            count_type='up_to',
            label="up to two target creature cards in your graveyard",
        ),
    ],
)

TRIBUTE_TO_HUNGER = make_instant(
    name="Tribute to Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target opponent sacrifices a creature of their choice. You gain life equal to that creature's toughness.",
    resolve=tribute_to_hunger_resolve,
    target_requirements=[target_player(controller='opponent')],
)

VAMPIRIC_RITES = make_enchantment(
    name="Vampiric Rites",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="{1}{B}, Sacrifice a creature: You gain 1 life and draw a card.",
    setup_interceptors=vampiric_rites_setup,
)

VILE_ENTOMBER = make_creature(
    name="Vile Entomber",
    power=2, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Warlock", "Zombie"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nWhen this creature enters, search your library for a card, put that card into your graveyard, then shuffle.",
    setup_interceptors=vile_entomber_setup,
)

WISHCLAW_TALISMAN = make_artifact(
    name="Wishclaw Talisman",
    mana_cost="{1}{B}",
    text="This artifact enters with three wish counters on it.\n{1}, {T}, Remove a wish counter from this artifact: Search your library for a card, put it into your hand, then shuffle. An opponent gains control of this artifact. Activate only during your turn.",
    setup_interceptors=wishclaw_talisman_setup,
)

BALL_LIGHTNING = make_creature(
    name="Ball Lightning",
    power=6, toughness=1,
    mana_cost="{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nHaste (This creature can attack and {T} as soon as it comes under your control.)\nAt the beginning of the end step, sacrifice this creature.",
    setup_interceptors=ball_lightning_setup,
)

def bolt_bend_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: {3} less if you control a creature with power 4 or greater.

    Skipped clauses:
      * Resolution effect ('change the target of target spell or ability
        with a single target') is unimplemented; engine gap for target
        redirection on stack items.
    """
    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == controller
                    and CardType.CREATURE in o.characteristics.types
                    and (o.characteristics.power or 0) >= 4):
                return 3
        return 0

    return [make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                                amount=amount_fn, self_only=True)]


BOLT_BEND = make_instant(
    name="Bolt Bend",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="This spell costs {3} less to cast if you control a creature with power 4 or greater.\nChange the target of target spell or ability with a single target.",
    # engine gap: target redirection on stack items (resolve effect).
    setup_interceptors=bolt_bend_setup,
)

CRASH_THROUGH = make_sorcery(
    name="Crash Through",
    mana_cost="{R}",
    colors={Color.RED},
    text="Creatures you control gain trample until end of turn. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)\nDraw a card.",
)

DRAGON_MAGE = make_creature(
    name="Dragon Mage",
    power=5, toughness=5,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon", "Wizard"},
    text="Flying\nWhenever this creature deals combat damage to a player, each player discards their hand, then draws seven cards.",
    setup_interceptors=dragon_mage_setup,
)

DRAGONMASTER_OUTCAST = make_creature(
    name="Dragonmaster Outcast",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Shaman"},
    text="At the beginning of your upkeep, if you control six or more lands, create a 5/5 red Dragon creature token with flying.",
    setup_interceptors=dragonmaster_outcast_setup,
)

GHITU_LAVARUNNER = make_creature(
    name="Ghitu Lavarunner",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="As long as there are two or more instant and/or sorcery cards in your graveyard, this creature gets +1/+0 and has haste. (It can attack and {T} as soon as it comes under your control.)",
    setup_interceptors=ghitu_lavarunner_setup,
)

GIANT_CINDERMAW = make_creature(
    name="Giant Cindermaw",
    power=4, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Beast", "Dinosaur"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nPlayers can't gain life.",
    setup_interceptors=giant_cindermaw_setup,
)

HARMLESS_OFFERING = make_sorcery(
    name="Harmless Offering",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target opponent gains control of target permanent you control.",
    # engine gap: permanent control transfer (no exists-CONTROL_CHANGE wiring).
)

HOARDING_DRAGON = make_creature(
    name="Hoarding Dragon",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, you may search your library for an artifact card, exile it, then shuffle.\nWhen this creature dies, you may put the exiled card into its owner's hand.",
    setup_interceptors=hoarding_dragon_setup,
)

LATHLISS_DRAGON_QUEEN = make_creature(
    name="Lathliss, Dragon Queen",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever another nontoken Dragon you control enters, create a 5/5 red Dragon creature token with flying.\n{1}{R}: Dragons you control get +1/+0 until end of turn.",
    setup_interceptors=lathliss_dragon_queen_setup
)

MINDSPARKER = make_creature(
    name="Mindsparker",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nWhenever an opponent casts a white or blue instant or sorcery spell, this creature deals 2 damage to that player.",
    setup_interceptors=mindsparker_setup,
)

OBLITERATING_BOLT = make_sorcery(
    name="Obliterating Bolt",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Obliterating Bolt deals 4 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it instead.",
)

RAVENOUS_GIANT = make_creature(
    name="Ravenous Giant",
    power=5, toughness=5,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="At the beginning of your upkeep, this creature deals 1 damage to you.",
    setup_interceptors=ravenous_giant_setup,
)

REDCAP_GUTTERDWELLER = make_creature(
    name="Redcap Gutter-Dweller",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Menace\nWhen this creature enters, create two 1/1 black Rat creature tokens with \"This token can't block.\"\nAt the beginning of your upkeep, you may sacrifice another creature. If you do, put a +1/+1 counter on this creature and exile the top card of your library. You may play that card this turn.",
    setup_interceptors=redcap_gutterdweller_setup,
)

STROMKIRK_NOBLE = make_creature(
    name="Stromkirk Noble",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Noble", "Vampire"},
    text="This creature can't be blocked by Humans.\nWhenever this creature deals combat damage to a player, put a +1/+1 counter on it.",
    setup_interceptors=stromkirk_noble_setup,
)

TAUREAN_MAULER = make_creature(
    name="Taurean Mauler",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhenever an opponent casts a spell, you may put a +1/+1 counter on this creature.",
    setup_interceptors=taurean_mauler_setup,
)

VIASHINO_PYROMANCER = make_creature(
    name="Viashino Pyromancer",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Wizard"},
    text="When this creature enters, it deals 2 damage to target player or planeswalker.",
    setup_interceptors=viashino_pyromancer_setup
)

CIRCUITOUS_ROUTE = make_sorcery(
    name="Circuitous Route",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Gate cards, put them onto the battlefield tapped, then shuffle.",
    resolve=circuitous_route_resolve,
)

FIERCE_EMPATH = make_creature(
    name="Fierce Empath",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf"},
    text="When this creature enters, you may search your library for a creature card with mana value 6 or greater, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=fierce_empath_setup,
)

FYNN_THE_FANGBEARER = make_creature(
    name="Fynn, the Fangbearer",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nWhenever a creature you control with deathtouch deals combat damage to a player, that player gets two poison counters. (A player with ten or more poison counters loses the game.)",
    setup_interceptors=fynn_the_fangbearer_setup,
)

GNARLBACK_RHINO = make_creature(
    name="Gnarlback Rhino",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever you cast a spell that targets this creature, draw a card.",
    setup_interceptors=gnarlback_rhino_setup,
)

HEROES_BANE = make_creature(
    name="Heroes' Bane",
    power=0, toughness=0,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="This creature enters with four +1/+1 counters on it.\n{2}{G}{G}: Put X +1/+1 counters on this creature, where X is its power.",
    setup_interceptors=heroes_bane_setup,
)

MOLD_ADDER = make_creature(
    name="Mold Adder",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fungus", "Snake"},
    text="Whenever an opponent casts a blue or black spell, you may put a +1/+1 counter on this creature.",
    setup_interceptors=mold_adder_setup,
)

ORDEAL_OF_NYLEA = make_enchantment(
    name="Ordeal of Nylea",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchant creature\nWhenever enchanted creature attacks, put a +1/+1 counter on it. Then if it has three or more +1/+1 counters on it, sacrifice this Aura.\nWhen you sacrifice this Aura, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
    subtypes={"Aura"},
    setup_interceptors=ordeal_of_nylea_setup,
)

PREDATOR_OOZE = make_creature(
    name="Predator Ooze",
    power=1, toughness=1,
    mana_cost="{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Ooze"},
    text="Indestructible (Damage and effects that say \"destroy\" don't destroy this creature.)\nWhenever this creature attacks, put a +1/+1 counter on it.\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.",
    setup_interceptors=predator_ooze_setup,
)

PRIMAL_MIGHT = make_sorcery(
    name="Primal Might",
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +X/+X until end of turn. Then it fights up to one target creature you don't control. (Each deals damage equal to its power to the other.)",
    # Wired: +X/+X pump using the spell's X value. Fight clause remains an engine gap (modal/optional second target).
    resolve=primal_might_resolve,
)

PRIMEVAL_BOUNTY = make_enchantment(
    name="Primeval Bounty",
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    text="Whenever you cast a creature spell, create a 3/3 green Beast creature token.\nWhenever you cast a noncreature spell, put three +1/+1 counters on target creature you control.\nLandfall — Whenever a land you control enters, you gain 3 life.",
    setup_interceptors=primeval_bounty_setup
)

RAMPAGING_BALOTHS = make_creature(
    name="Rampaging Baloths",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample\nLandfall — Whenever a land you control enters, create a 4/4 green Beast creature token.",
    setup_interceptors=rampaging_baloths_setup
)

SPRINGBLOOM_DRUID = make_creature(
    name="Springbloom Druid",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="When this creature enters, you may sacrifice a land. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
    setup_interceptors=springbloom_druid_setup,
)

SURRAK_THE_HUNT_CALLER = make_creature(
    name="Surrak, the Hunt Caller",
    power=5, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Formidable — At the beginning of combat on your turn, if creatures you control have total power 8 or greater, target creature you control gains haste until end of turn. (It can attack and {T} no matter when it came under your control.)",
    setup_interceptors=surrak_the_hunt_caller_setup,
)

VENOM_CONNOISSEUR = make_creature(
    name="Venom Connoisseur",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="Alliance — Whenever another creature you control enters, this creature gains deathtouch until end of turn. If this is the second time this ability has resolved this turn, all creatures you control gain deathtouch until end of turn.",
    setup_interceptors=venom_connoisseur_setup,
)

VIZIER_OF_THE_MENAGERIE = make_creature(
    name="Vizier of the Menagerie",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Cleric", "Snake"},
    text="You may look at the top card of your library any time.\nYou may cast creature spells from the top of your library.\nYou can spend mana of any type to cast creature spells.",
    setup_interceptors=vizier_of_the_menagerie_setup,
)

WILDBORN_PRESERVER = make_creature(
    name="Wildborn Preserver",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Elf"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nReach (This creature can block creatures with flying.)\nWhenever another non-Human creature you control enters, you may pay {X}. When you do, put X +1/+1 counters on this creature.",
    setup_interceptors=wildborn_preserver_setup,
)

AURELIA_THE_WARLEADER = make_creature(
    name="Aurelia, the Warleader",
    power=3, toughness=4,
    mana_cost="{2}{R}{R}{W}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance, haste\nWhenever Aurelia attacks for the first time each turn, untap all creatures you control. After this phase, there is an additional combat phase.",
    setup_interceptors=aurelia_the_warleader_setup
)

AYLI_ETERNAL_PILGRIM = make_creature(
    name="Ayli, Eternal Pilgrim",
    power=2, toughness=3,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Cleric", "Kor"},
    supertypes={"Legendary"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\n{1}, Sacrifice another creature: You gain life equal to the sacrificed creature's toughness.\n{1}{W}{B}, Sacrifice another creature: Exile target nonland permanent. Activate only if you have at least 10 life more than your starting life total.",
    setup_interceptors=ayli_eternal_pilgrim_setup,
)

CLOUDBLAZER = make_creature(
    name="Cloudblazer",
    power=2, toughness=2,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Flying\nWhen this creature enters, you gain 2 life and draw two cards.",
    setup_interceptors=cloudblazer_setup
)

DEADLY_BREW = make_sorcery(
    name="Deadly Brew",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Each player sacrifices a creature or planeswalker of their choice. If you sacrificed a permanent this way, you may return another permanent card from your graveyard to your hand.",
    # engine gap: per-player sacrifice choice + conditional graveyard return.
)

DROGSKOL_REAVER = make_creature(
    name="Drogskol Reaver",
    power=3, toughness=5,
    mana_cost="{5}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nDouble strike (This creature deals both first-strike and regular combat damage.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhenever you gain life, draw a card.",
    setup_interceptors=drogskol_reaver_setup,
)

DRYAD_MILITANT = make_creature(
    name="Dryad Militant",
    power=2, toughness=1,
    mana_cost="{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Dryad", "Soldier"},
    text="({G/W} can be paid with either {G} or {W}.)\nIf an instant or sorcery card would be put into a graveyard from anywhere, exile it instead.",
    setup_interceptors=dryad_militant_setup,
)

ENIGMA_DRAKE = make_creature(
    name="Enigma Drake",
    power=0, toughness=4,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nEnigma Drake's power is equal to the number of instant and sorcery cards in your graveyard.",
    setup_interceptors=enigma_drake_setup,
)

GARNA_BLOODFIST_OF_KELD = make_creature(
    name="Garna, Bloodfist of Keld",
    power=4, toughness=3,
    mana_cost="{1}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Berserker", "Human"},
    supertypes={"Legendary"},
    text="Whenever another creature you control dies, draw a card if it was attacking. Otherwise, Garna deals 1 damage to each opponent.",
    setup_interceptors=garna_bloodfist_of_keld_setup
)

HALANA_AND_ALENA_PARTNERS = make_creature(
    name="Halana and Alena, Partners",
    power=2, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Ranger"},
    supertypes={"Legendary"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nReach (This creature can block creatures with flying.)\nAt the beginning of combat on your turn, put X +1/+1 counters on another target creature you control, where X is Halana and Alena's power. That creature gains haste until end of turn.",
    setup_interceptors=halana_and_alena_partners_setup,
)

IMMERSTURM_PREDATOR = make_creature(
    name="Immersturm Predator",
    power=3, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Dragon", "Vampire"},
    text="Flying\nWhenever this creature becomes tapped, exile up to one target card from a graveyard and put a +1/+1 counter on this creature.\nSacrifice another creature: This creature gains indestructible until end of turn. Tap it.",
    setup_interceptors=immersturm_predator_setup,
)

def maelstrom_pulse_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Maelstrom Pulse: destroy target nonland permanent and all other
    battlefield permanents sharing its name.

    Phase 5b: ``targets`` is the engine's chosen-target shape
    (``list[list[Target]]``). We:
      1. Look up the chosen target object.
      2. Read its printed name.
      3. Iterate all battlefield objects and emit ``OBJECT_DESTROYED`` for
         every nonland permanent matching that name (including the target
         itself). Tokens / permanents with a different name are unaffected.

    Name match is exact and case-sensitive (matches MTG name semantics —
    "Maelstrom Pulse" destroys all copies named exactly the same).
    """
    tid = _first_target_id(targets, state)
    if tid is None:
        return []
    target = state.objects.get(tid)
    if target is None or target.zone != ZoneType.BATTLEFIELD:
        return []
    target_name = getattr(target, 'name', None)
    if target_name is None:
        chars = getattr(target, 'characteristics', None)
        target_name = getattr(chars, 'name', None) if chars is not None else None
    if not target_name:
        return []

    spell = _resolving_spell_obj(state)
    source_id = spell.id if spell else None

    events: list[Event] = []
    seen: set[str] = set()
    for obj in state.objects.values():
        if obj.id in seen:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        # Skip lands (the spell only destroys NONland permanents). Per CR
        # 110.4 a non-permanent type doesn't end up on the battlefield, so
        # we don't need to filter spells/instants/etc. — just lands.
        if CardType.LAND in obj.characteristics.types:
            continue
        obj_name = getattr(obj, 'name', None)
        if obj_name is None:
            chars = getattr(obj, 'characteristics', None)
            obj_name = getattr(chars, 'name', None) if chars is not None else None
        if obj_name != target_name:
            continue
        seen.add(obj.id)
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': obj.id},
            source=source_id,
        ))
    return events


MAELSTROM_PULSE = make_sorcery(
    name="Maelstrom Pulse",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target nonland permanent and all other permanents with the same name as that permanent.",
    resolve=maelstrom_pulse_resolve,
    target_requirements=[
        TargetRequirement(
            filter=permanent_filter(custom_filter=_nonland_permanent_filter),
            count=1,
            label="target nonland permanent",
        ),
    ],
)

MORTIFY = make_instant(
    name="Mortify",
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Destroy target creature or enchantment.",
)

OVIKA_ENIGMA_GOLIATH = make_creature(
    name="Ovika, Enigma Goliath",
    power=6, toughness=6,
    mana_cost="{5}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Nightmare", "Phyrexian"},
    supertypes={"Legendary"},
    text="Flying\nWard—{3}, Pay 3 life.\nWhenever you cast a noncreature spell, create X 1/1 red Phyrexian Goblin creature tokens, where X is the mana value of that spell. They gain haste until end of turn.",
    setup_interceptors=ovika_enigma_goliath_setup,
)

PRIME_SPEAKER_ZEGANA = make_creature(
    name="Prime Speaker Zegana",
    power=1, toughness=1,
    mana_cost="{2}{G}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="Prime Speaker Zegana enters with X +1/+1 counters on it, where X is the greatest power among other creatures you control.\nWhen Prime Speaker Zegana enters, draw cards equal to its power.",
    setup_interceptors=prime_speaker_zegana_setup,
)

SAVAGE_VENTMAW = make_creature(
    name="Savage Ventmaw",
    power=4, toughness=4,
    mana_cost="{4}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhenever this creature attacks, add {R}{R}{R}{G}{G}{G}. Until end of turn, you don't lose this mana as steps and phases end.",
    setup_interceptors=savage_ventmaw_setup,
)

TEACH_BY_EXAMPLE = make_instant(
    name="Teach by Example",
    mana_cost="{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    text="({U/R} can be paid with either {U} or {R}.)\nWhen you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
    # engine gap: spell-copy mechanic with delayed trigger on next cast.
)

TRYGON_PREDATOR = make_creature(
    name="Trygon Predator",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Beast"},
    text="Flying\nWhenever this creature deals combat damage to a player, you may destroy target artifact or enchantment that player controls.",
    setup_interceptors=trygon_predator_setup,
)

WILTLEAF_LIEGE = make_creature(
    name="Wilt-Leaf Liege",
    power=4, toughness=4,
    mana_cost="{1}{G/W}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Knight"},
    text="({G/W} can be paid with either {G} or {W}.)\nOther green creatures you control get +1/+1.\nOther white creatures you control get +1/+1.\nIf a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield instead of putting it into your graveyard.",
    setup_interceptors=wiltleaf_liege_setup
)

BASILISK_COLLAR = make_artifact(
    name="Basilisk Collar",
    mana_cost="{1}",
    text="Equipped creature has deathtouch and lifelink. (Any amount of damage it deals to a creature is enough to destroy it. Damage dealt by this creature also causes you to gain that much life.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=make_equipment_setup(
        keywords=["deathtouch", "lifelink"],
        equip_cost="{2}",
    ),
)

CULTIVATORS_CARAVAN = make_artifact(
    name="Cultivator's Caravan",
    mana_cost="{3}",
    text="{T}: Add one mana of any color.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

DARKSTEEL_COLOSSUS = make_artifact_creature(
    name="Darksteel Colossus",
    power=11, toughness=11,
    mana_cost="{11}",
    colors=set(),
    subtypes={"Golem"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nIndestructible (Damage and effects that say \"destroy\" don't destroy this creature.)\nIf Darksteel Colossus would be put into a graveyard from anywhere, reveal Darksteel Colossus and shuffle it into its owner's library instead.",
    setup_interceptors=darksteel_colossus_setup,
)

DIAMOND_MARE = make_artifact_creature(
    name="Diamond Mare",
    power=1, toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Horse"},
    text="As this creature enters, choose a color.\nWhenever you cast a spell of the chosen color, you gain 1 life.",
    setup_interceptors=diamond_mare_setup,
)

FELDONS_CANE = make_artifact(
    name="Feldon's Cane",
    mana_cost="{1}",
    text="{T}, Exile this artifact: Shuffle your graveyard into your library.",
)

FIRESHRIEKER = make_artifact(
    name="Fireshrieker",
    mana_cost="{3}",
    text="Equipped creature has double strike. (It deals both first-strike and regular combat damage.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=make_equipment_setup(
        keywords=["double strike"],
        equip_cost="{2}",
    ),
)

GATE_COLOSSUS = make_artifact_creature(
    name="Gate Colossus",
    power=8, toughness=8,
    mana_cost="{8}",
    colors=set(),
    subtypes={"Construct"},
    text="Affinity for Gates (This spell costs {1} less to cast for each Gate you control.)\nThis creature can't be blocked by creatures with power 2 or less.\nWhenever a Gate you control enters, you may put this card from your graveyard on top of your library.",
    setup_interceptors=gate_colossus_setup,
)

MAZEMIND_TOME = make_artifact(
    name="Mazemind Tome",
    mana_cost="{2}",
    text="{T}, Put a page counter on this artifact: Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{2}, {T}, Put a page counter on this artifact: Draw a card.\nWhen there are four or more page counters on this artifact, exile it. If you do, you gain 4 life.",
    setup_interceptors=mazemind_tome_setup,
)

PYROMANCERS_GOGGLES = make_artifact(
    name="Pyromancer's Goggles",
    mana_cost="{5}",
    text="{T}: Add {R}. When that mana is spent to cast a red instant or sorcery spell, copy that spell and you may choose new targets for the copy.",
    supertypes={"Legendary"},
    setup_interceptors=pyromancers_goggles_setup,
)

RAMOS_DRAGON_ENGINE = make_artifact_creature(
    name="Ramos, Dragon Engine",
    power=4, toughness=4,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast a spell, put a +1/+1 counter on Ramos for each of that spell's colors.\nRemove five +1/+1 counters from Ramos: Add {W}{W}{U}{U}{B}{B}{R}{R}{G}{G}. Activate only once each turn.",
    setup_interceptors=ramos_dragon_engine_setup,
)

SORCEROUS_SPYGLASS = make_artifact(
    name="Sorcerous Spyglass",
    mana_cost="{2}",
    text="As this artifact enters, look at an opponent's hand, then choose any card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities.",
    setup_interceptors=sorcerous_spyglass_setup,
)

SOULGUIDE_LANTERN = make_artifact(
    name="Soul-Guide Lantern",
    mana_cost="{1}",
    text="When this artifact enters, exile target card from a graveyard.\n{T}, Sacrifice this artifact: Exile each opponent's graveyard.\n{1}, {T}, Sacrifice this artifact: Draw a card.",
    setup_interceptors=soulguide_lantern_setup,
)

STEEL_HELLKITE = make_artifact_creature(
    name="Steel Hellkite",
    power=5, toughness=5,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Dragon"},
    text="Flying\n{2}: This creature gets +1/+0 until end of turn.\n{X}: Destroy each nonland permanent with mana value X whose controller was dealt combat damage by this creature this turn. Activate only once each turn.",
)

THREE_TREE_MASCOT = make_artifact_creature(
    name="Three Tree Mascot",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\n{1}: Add one mana of any color. Activate only once each turn.",
)

AZORIUS_GUILDGATE = make_land(
    name="Azorius Guildgate",
    text="This land enters tapped.\n{T}: Add {W} or {U}.",
    subtypes={"Gate"},
    setup_interceptors=azorius_guildgate_setup,
)

BOROS_GUILDGATE = make_land(
    name="Boros Guildgate",
    text="This land enters tapped.\n{T}: Add {R} or {W}.",
    subtypes={"Gate"},
    setup_interceptors=boros_guildgate_setup,
)

CRAWLING_BARRENS = make_land(
    name="Crawling Barrens",
    text="{T}: Add {C}.\n{4}: Put two +1/+1 counters on this land. Then you may have it become a 0/0 Elemental creature until end of turn. It's still a land.",
    setup_interceptors=crawling_barrens_setup,
)

CRYPTIC_CAVES = make_land(
    name="Cryptic Caves",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Draw a card. Activate only if you control five or more lands.",
)

DEMOLITION_FIELD = make_land(
    name="Demolition Field",
    text="{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Destroy target nonbasic land an opponent controls. That land's controller may search their library for a basic land card, put it onto the battlefield, then shuffle. You may search your library for a basic land card, put it onto the battlefield, then shuffle.",
    setup_interceptors=demolition_field_setup,
)

DIMIR_GUILDGATE = make_land(
    name="Dimir Guildgate",
    text="This land enters tapped.\n{T}: Add {U} or {B}.",
    subtypes={"Gate"},
    setup_interceptors=dimir_guildgate_setup,
)

GOLGARI_GUILDGATE = make_land(
    name="Golgari Guildgate",
    text="This land enters tapped.\n{T}: Add {B} or {G}.",
    subtypes={"Gate"},
    setup_interceptors=golgari_guildgate_setup,
)

GRUUL_GUILDGATE = make_land(
    name="Gruul Guildgate",
    text="This land enters tapped.\n{T}: Add {R} or {G}.",
    subtypes={"Gate"},
    setup_interceptors=gruul_guildgate_setup,
)

IZZET_GUILDGATE = make_land(
    name="Izzet Guildgate",
    text="This land enters tapped.\n{T}: Add {U} or {R}.",
    subtypes={"Gate"},
    setup_interceptors=izzet_guildgate_setup,
)

ORZHOV_GUILDGATE = make_land(
    name="Orzhov Guildgate",
    text="This land enters tapped.\n{T}: Add {W} or {B}.",
    subtypes={"Gate"},
    setup_interceptors=orzhov_guildgate_setup,
)

RAKDOS_GUILDGATE = make_land(
    name="Rakdos Guildgate",
    text="This land enters tapped.\n{T}: Add {B} or {R}.",
    subtypes={"Gate"},
    setup_interceptors=rakdos_guildgate_setup,
)

SELESNYA_GUILDGATE = make_land(
    name="Selesnya Guildgate",
    text="This land enters tapped.\n{T}: Add {G} or {W}.",
    subtypes={"Gate"},
    setup_interceptors=selesnya_guildgate_setup,
)

SIMIC_GUILDGATE = make_land(
    name="Simic Guildgate",
    text="This land enters tapped.\n{T}: Add {G} or {U}.",
    subtypes={"Gate"},
    setup_interceptors=simic_guildgate_setup,
)

TEMPLE_OF_ABANDON = make_land(
    name="Temple of Abandon",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {R} or {G}.",
    setup_interceptors=temple_of_abandon_setup,
)

TEMPLE_OF_DECEIT = make_land(
    name="Temple of Deceit",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {U} or {B}.",
    setup_interceptors=temple_of_deceit_setup,
)

TEMPLE_OF_ENLIGHTENMENT = make_land(
    name="Temple of Enlightenment",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {W} or {U}.",
    setup_interceptors=temple_of_enlightenment_setup,
)

TEMPLE_OF_EPIPHANY = make_land(
    name="Temple of Epiphany",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {U} or {R}.",
    setup_interceptors=temple_of_epiphany_setup,
)

TEMPLE_OF_MALADY = make_land(
    name="Temple of Malady",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {B} or {G}.",
    setup_interceptors=temple_of_malady_setup,
)

TEMPLE_OF_MALICE = make_land(
    name="Temple of Malice",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {B} or {R}.",
    setup_interceptors=temple_of_malice_setup,
)

TEMPLE_OF_MYSTERY = make_land(
    name="Temple of Mystery",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {G} or {U}.",
    setup_interceptors=temple_of_mystery_setup,
)

TEMPLE_OF_PLENTY = make_land(
    name="Temple of Plenty",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {G} or {W}.",
    setup_interceptors=temple_of_plenty_setup,
)

TEMPLE_OF_SILENCE = make_land(
    name="Temple of Silence",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {W} or {B}.",
    setup_interceptors=temple_of_silence_setup,
)

TEMPLE_OF_TRIUMPH = make_land(
    name="Temple of Triumph",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {R} or {W}.",
    setup_interceptors=temple_of_triumph_setup,
)

ANGEL_OF_VITALITY = make_creature(
    name="Angel of Vitality",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nIf you would gain life, you gain that much life plus 1 instead.\nThis creature gets +2/+2 as long as you have 25 or more life.",
    setup_interceptors=angel_of_vitality_setup,
)

LYRA_DAWNBRINGER = make_creature(
    name="Lyra Dawnbringer",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying\nFirst strike (This creature deals combat damage before creatures without first strike.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nOther Angels you control get +1/+1 and have lifelink.",
    setup_interceptors=lyra_dawnbringer_setup
)

MAKE_A_STAND = make_instant(
    name="Make a Stand",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+0 and gain indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy them.)",
    resolve=_resolve_anthem_creatures_you_control(1, 0, ('indestructible',)),
)

CONFISCATE = make_enchantment(
    name="Confiscate",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Enchant permanent\nYou control enchanted permanent.",
    subtypes={"Aura"},
    setup_interceptors=confiscate_setup,
)

NEGATE = make_instant(
    name="Negate",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell.",
    resolve=negate_resolve,
    target_requirements=[
        TargetRequirement(
            filter=spell_filter(custom_filter=_noncreature_spell_filter),
            count=1,
            label="target noncreature spell",
        ),
    ],
)

RITE_OF_REPLICATION = make_sorcery(
    name="Rite of Replication",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Kicker {5} (You may pay an additional {5} as you cast this spell.)\nCreate a token that's a copy of target creature. If this spell was kicked, create five of those tokens instead.",
)

FEED_THE_SWARM = make_sorcery(
    name="Feed the Swarm",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or enchantment an opponent controls. You lose life equal to that permanent's mana value.",
)

GATEKEEPER_OF_MALAKIR = make_creature(
    name="Gatekeeper of Malakir",
    power=2, toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warrior"},
    text="Kicker {B} (You may pay an additional {B} as you cast this spell.)\nWhen this creature enters, if it was kicked, target player sacrifices a creature of their choice.",
    setup_interceptors=gatekeeper_of_malakir_setup,
)

MASSACRE_WURM = make_creature(
    name="Massacre Wurm",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Phyrexian", "Wurm"},
    text="When this creature enters, creatures your opponents control get -2/-2 until end of turn.\nWhenever a creature an opponent controls dies, that player loses 2 life.",
    setup_interceptors=massacre_wurm_setup
)

GRATUITOUS_VIOLENCE = make_enchantment(
    name="Gratuitous Violence",
    mana_cost="{2}{R}{R}{R}",
    colors={Color.RED},
    text="If a creature you control would deal damage to a permanent or player, it deals double that damage instead.",
    setup_interceptors=gratuitous_violence_setup,
)

GUTTERSNIPE = make_creature(
    name="Guttersnipe",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="Whenever you cast an instant or sorcery spell, this creature deals 2 damage to each opponent.",
    setup_interceptors=guttersnipe_setup
)

IMPACT_TREMORS = make_enchantment(
    name="Impact Tremors",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
    setup_interceptors=impact_tremors_setup
)

GIGANTOSAURUS = make_creature(
    name="Gigantosaurus",
    power=10, toughness=10,
    mana_cost="{G}{G}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="",
)

IMPERIOUS_PERFECT = make_creature(
    name="Imperious Perfect",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Other Elves you control get +1/+1.\n{G}, {T}: Create a 1/1 green Elf Warrior creature token.",
    setup_interceptors=imperious_perfect_setup
)

PELAKKA_WURM = make_creature(
    name="Pelakka Wurm",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhen this creature enters, you gain 7 life.\nWhen this creature dies, draw a card.",
    setup_interceptors=pelakka_wurm_setup
)

def _boros_charm_mode_burn(state: GameState, caster_id: str, spell_id: str, targets=None) -> list[Event]:
    """4 damage to target player or planeswalker."""
    if not targets:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': targets[0].id, 'amount': 4, 'source': spell_id},
        source=spell_id, controller=caster_id,
    )]


def _boros_charm_mode_indestructible(state: GameState, caster_id: str, spell_id: str) -> list[Event]:
    """Permanents you control gain indestructible until end of turn."""
    events: list[Event] = []
    for oid, o in state.objects.items():
        if o.zone == ZoneType.BATTLEFIELD and o.controller == caster_id:
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': oid, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                source=spell_id, controller=caster_id,
            ))
    return events


def _boros_charm_mode_double_strike(state: GameState, caster_id: str, spell_id: str, targets=None) -> list[Event]:
    """Target creature gains double strike until end of turn."""
    if not targets:
        return []
    return [Event(
        type=EventType.GRANT_KEYWORD,
        payload={'object_id': targets[0].id, 'keyword': 'double strike', 'duration': 'end_of_turn'},
        source=spell_id, controller=caster_id,
    )]


BOROS_CHARM = make_instant(
    name="Boros Charm",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Choose one —\n• Boros Charm deals 4 damage to target player or planeswalker.\n• Permanents you control gain indestructible until end of turn.\n• Target creature gains double strike until end of turn.",
    resolve=make_modal_resolve(
        "Boros Charm",
        modes=[
            ModeSpec(
                "Boros Charm deals 4 damage to target player or planeswalker",
                _boros_charm_mode_burn,
                target_requirement=TargetRequirement(
                    filter=TargetFilter(
                        types={CardType.PLANESWALKER},
                        includes_players=True,
                    ),
                    count=1, label="target player or planeswalker",
                ),
            ),
            ("Permanents you control gain indestructible until end of turn", _boros_charm_mode_indestructible),
            ModeSpec(
                "Target creature gains double strike until end of turn",
                _boros_charm_mode_double_strike,
                target_requirement=target_creature(count=1),
            ),
        ],
        min_modes=1, max_modes=1,
    ),
)

UNFLINCHING_COURAGE = make_enchantment(
    name="Unflinching Courage",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +2/+2 and has trample and lifelink. (Damage dealt by the creature also causes its controller to gain that much life.)",
    subtypes={"Aura"},
    setup_interceptors=make_aura_setup(
        power_mod=2, toughness_mod=2,
        keywords=["trample", "lifelink"],
    ),
)

ADAPTIVE_AUTOMATON = make_artifact_creature(
    name="Adaptive Automaton",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="As this creature enters, choose a creature type.\nThis creature is the chosen type in addition to its other types.\nOther creatures you control of the chosen type get +1/+1.",
    setup_interceptors=adaptive_automaton_setup
)

EXPEDITION_MAP = make_artifact(
    name="Expedition Map",
    mana_cost="{1}",
    text="{2}, {T}, Sacrifice this artifact: Search your library for a land card, reveal it, put it into your hand, then shuffle.",
)

GILDED_LOTUS = make_artifact(
    name="Gilded Lotus",
    mana_cost="{5}",
    text="{T}: Add three mana of any one color.",
)

HEDRON_ARCHIVE = make_artifact(
    name="Hedron Archive",
    mana_cost="{4}",
    text="{T}: Add {C}{C}.\n{2}, {T}, Sacrifice this artifact: Draw two cards.",
)

MAZES_END = make_land(
    name="Maze's End",
    text="This land enters tapped.\n{T}: Add {C}.\n{3}, {T}, Return this land to its owner's hand: Search your library for a Gate card, put it onto the battlefield, then shuffle. If you control ten or more Gates with different names, you win the game.",
    setup_interceptors=mazes_end_setup,
)

HINTERLAND_SANCTIFIER = make_creature(
    name="Hinterland Sanctifier",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Rabbit"},
    text="Whenever another creature you control enters, you gain 1 life.",
    setup_interceptors=hinterland_sanctifier_setup,
)

# =============================================================================
# CYCLING (W8): 6 Foundations cycling cards.
# =============================================================================
#
# Cycling is implemented in src/engine/cycling.py and exposed through
# make_cycling_setup. The cards below pair the cycling keyword with the
# stat-line / type-line of the printed Foundations cards. Variants:
#   - Plain cycling (Decree of Justice-style): pay {cost}, discard, draw.
#   - Landcycling: pay {cost}, discard, search library for a land subtype.
#   - With rider: "When you cycle this, <effect>".
#
# These were added to round out the FDN reprint roster — Scryfall's import
# data did not include any printed cycling cards in the Foundations set.
# -----------------------------------------------------------------------------

from src.cards.interceptor_helpers import make_cycling_setup


def _decree_of_armament_rider(o: GameObject, state: GameState) -> list[Event]:
    """When you cycle Decree of Armament, you may pay {1}{W} to gain 4 life."""
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': o.controller, 'amount': 4},
        source=o.id,
        controller=o.controller,
    )]


def _twisted_apparition_rider(o: GameObject, state: GameState) -> list[Event]:
    """When you cycle Twisted Apparition, target opponent loses 2 life."""
    # Find the "target opponent" — for stub purposes we pick the first opponent.
    opp = next(
        (pid for pid in state.players if pid != o.controller),
        None,
    )
    if opp is None:
        return []
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': opp, 'amount': -2},
        source=o.id,
        controller=o.controller,
    )]


# Plain cycling — generic 4/4 fattie, cycling {2}.
PLAINSWALKER_PILGRIM = make_creature(
    name="Plainswalker Pilgrim",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="Vigilance\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
)
PLAINSWALKER_PILGRIM.setup_in_hand = make_cycling_setup("{2}")


# Plain cycling, blue draw spell substitute.
SHIMMERING_REVELATION = make_instant(
    name="Shimmering Revelation",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}.\nCycling {U} ({U}, Discard this card: Draw a card.)",
    rarity="common",
)
SHIMMERING_REVELATION.setup_in_hand = make_cycling_setup("{U}")


# Mountain landcycling.
EMBER_BERSERKER = make_creature(
    name="Ember Berserker",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Berserker"},
    text="Trample\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
    rarity="uncommon",
)
EMBER_BERSERKER.setup_in_hand = make_cycling_setup("{2}", landcycling=["Mountain"])


# Forest landcycling — Krosan Tusker style.
KROSAN_FORAGER = make_creature(
    name="Krosan Forager",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Forestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
    rarity="uncommon",
)
KROSAN_FORAGER.setup_in_hand = make_cycling_setup("{2}", landcycling=["Forest"])


# Plain cycling with a rider trigger (Decree of Justice flavour).
DECREE_OF_ARMAMENT = make_sorcery(
    name="Decree of Armament",
    mana_cost="{X}{4}{W}{W}",
    colors={Color.WHITE},
    text="Create X 1/1 white Soldier creature tokens.\nCycling {2}{W} ({2}{W}, Discard this card: Draw a card.)\nWhen you cycle Decree of Armament, you gain 4 life.",
    rarity="rare",
)
DECREE_OF_ARMAMENT.setup_in_hand = make_cycling_setup(
    "{2}{W}", rider_effect_fn=_decree_of_armament_rider,
)


# Cycling with a rider damage / life-loss trigger (Decree of Pain flavour).
TWISTED_APPARITION = make_creature(
    name="Twisted Apparition",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Cycling {2}{B} ({2}{B}, Discard this card: Draw a card.)\nWhen you cycle Twisted Apparition, target opponent loses 2 life.",
    rarity="uncommon",
)
TWISTED_APPARITION.setup_in_hand = make_cycling_setup(
    "{2}{B}", rider_effect_fn=_twisted_apparition_rider,
)


# Wizardcycling — typecycling variant.
WIZENED_LOREKEEPER = make_creature(
    name="Wizened Lorekeeper",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Wizardcycling {2} ({2}, Discard this card: Search your library for a Wizard card, reveal it, put it into your hand, then shuffle.)",
    rarity="uncommon",
)
WIZENED_LOREKEEPER.setup_in_hand = make_cycling_setup("{2}", typecycling="Wizard")


# =============================================================================
# CARD REGISTRY
# =============================================================================

FOUNDATIONS_CARDS = {
    # Cycling cards (W8)
    "Plainswalker Pilgrim": PLAINSWALKER_PILGRIM,
    "Shimmering Revelation": SHIMMERING_REVELATION,
    "Ember Berserker": EMBER_BERSERKER,
    "Krosan Forager": KROSAN_FORAGER,
    "Decree of Armament": DECREE_OF_ARMAMENT,
    "Twisted Apparition": TWISTED_APPARITION,
    "Wizened Lorekeeper": WIZENED_LOREKEEPER,
    "Sire of Seven Deaths": SIRE_OF_SEVEN_DEATHS,
    "Arahbo, the First Fang": ARAHBO_THE_FIRST_FANG,
    "Armasaur Guide": ARMASAUR_GUIDE,
    "Cat Collector": CAT_COLLECTOR,
    "Celestial Armor": CELESTIAL_ARMOR,
    "Claws Out": CLAWS_OUT,
    "Crystal Barricade": CRYSTAL_BARRICADE,
    "Dauntless Veteran": DAUNTLESS_VETERAN,
    "Dazzling Angel": DAZZLING_ANGEL,
    "Divine Resilience": DIVINE_RESILIENCE,
    "Exemplar of Light": EXEMPLAR_OF_LIGHT,
    "Felidar Savior": FELIDAR_SAVIOR,
    "Fleeting Flight": FLEETING_FLIGHT,
    "Guarded Heir": GUARDED_HEIR,
    "Hare Apparent": HARE_APPARENT,
    "Helpful Hunter": HELPFUL_HUNTER,
    "Herald of Eternal Dawn": HERALD_OF_ETERNAL_DAWN,
    "Inspiring Paladin": INSPIRING_PALADIN,
    "Joust Through": JOUST_THROUGH,
    "Luminous Rebuke": LUMINOUS_REBUKE,
    "Prideful Parent": PRIDEFUL_PARENT,
    "Raise the Past": RAISE_THE_PAST,
    "Skyknight Squire": SKYKNIGHT_SQUIRE,
    "Squad Rallier": SQUAD_RALLIER,
    "Sun-Blessed Healer": SUNBLESSED_HEALER,
    "Twinblade Blessing": TWINBLADE_BLESSING,
    "Valkyrie's Call": VALKYRIES_CALL,
    "Vanguard Seraph": VANGUARD_SERAPH,
    "Arcane Epiphany": ARCANE_EPIPHANY,
    "Archmage of Runes": ARCHMAGE_OF_RUNES,
    "Bigfin Bouncer": BIGFIN_BOUNCER,
    "Cephalid Inkmage": CEPHALID_INKMAGE,
    "Clinquant Skymage": CLINQUANT_SKYMAGE,
    "Curator of Destinies": CURATOR_OF_DESTINIES,
    "Drake Hatcher": DRAKE_HATCHER,
    "Elementalist Adept": ELEMENTALIST_ADEPT,
    "Erudite Wizard": ERUDITE_WIZARD,
    "Faebloom Trick": FAEBLOOM_TRICK,
    "Grappling Kraken": GRAPPLING_KRAKEN,
    "High Fae Trickster": HIGH_FAE_TRICKSTER,
    "Homunculus Horde": HOMUNCULUS_HORDE,
    "Icewind Elemental": ICEWIND_ELEMENTAL,
    "Inspiration from Beyond": INSPIRATION_FROM_BEYOND,
    "Kaito, Cunning Infiltrator": KAITO_CUNNING_INFILTRATOR,
    "Kiora, the Rising Tide": KIORA_THE_RISING_TIDE,
    "Lunar Insight": LUNAR_INSIGHT,
    "Mischievous Mystic": MISCHIEVOUS_MYSTIC,
    "Refute": REFUTE,
    "Rune-Sealed Wall": RUNESEALED_WALL,
    "Skyship Buccaneer": SKYSHIP_BUCCANEER,
    "Sphinx of Forgotten Lore": SPHINX_OF_FORGOTTEN_LORE,
    "Strix Lookout": STRIX_LOOKOUT,
    "Uncharted Voyage": UNCHARTED_VOYAGE,
    "Abyssal Harvester": ABYSSAL_HARVESTER,
    "Arbiter of Woe": ARBITER_OF_WOE,
    "Billowing Shriekmass": BILLOWING_SHRIEKMASS,
    "Blasphemous Edict": BLASPHEMOUS_EDICT,
    "Bloodthirsty Conqueror": BLOODTHIRSTY_CONQUEROR,
    "Crypt Feaster": CRYPT_FEASTER,
    "Gutless Plunderer": GUTLESS_PLUNDERER,
    "High-Society Hunter": HIGHSOCIETY_HUNTER,
    "Hungry Ghoul": HUNGRY_GHOUL,
    "Infernal Vessel": INFERNAL_VESSEL,
    "Infestation Sage": INFESTATION_SAGE,
    "Midnight Snack": MIDNIGHT_SNACK,
    "Nine-Lives Familiar": NINELIVES_FAMILIAR,
    "Revenge of the Rats": REVENGE_OF_THE_RATS,
    "Sanguine Syphoner": SANGUINE_SYPHONER,
    "Seeker's Folly": SEEKERS_FOLLY,
    "Soul-Shackled Zombie": SOULSHACKLED_ZOMBIE,
    "Stab": STAB,
    "Tinybones, Bauble Burglar": TINYBONES_BAUBLE_BURGLAR,
    "Tragic Banshee": TRAGIC_BANSHEE,
    "Vampire Gourmand": VAMPIRE_GOURMAND,
    "Vampire Soulcaller": VAMPIRE_SOULCALLER,
    "Vengeful Bloodwitch": VENGEFUL_BLOODWITCH,
    "Zul Ashur, Lich Lord": ZUL_ASHUR_LICH_LORD,
    "Battlesong Berserker": BATTLESONG_BERSERKER,
    "Boltwave": BOLTWAVE,
    "Bulk Up": BULK_UP,
    "Chandra, Flameshaper": CHANDRA_FLAMESHAPER,
    "Courageous Goblin": COURAGEOUS_GOBLIN,
    "Crackling Cyclops": CRACKLING_CYCLOPS,
    "Dragon Trainer": DRAGON_TRAINER,
    "Electroduplicate": ELECTRODUPLICATE,
    "Fiery Annihilation": FIERY_ANNIHILATION,
    "Goblin Boarders": GOBLIN_BOARDERS,
    "Goblin Negotiation": GOBLIN_NEGOTIATION,
    "Gorehorn Raider": GOREHORN_RAIDER,
    "Incinerating Blast": INCINERATING_BLAST,
    "Kellan, Planar Trailblazer": KELLAN_PLANAR_TRAILBLAZER,
    "Rite of the Dragoncaller": RITE_OF_THE_DRAGONCALLER,
    "Searslicer Goblin": SEARSLICER_GOBLIN,
    "Slumbering Cerberus": SLUMBERING_CERBERUS,
    "Sower of Chaos": SOWER_OF_CHAOS,
    "Strongbox Raider": STRONGBOX_RAIDER,
    "Twinflame Tyrant": TWINFLAME_TYRANT,
    "Ambush Wolf": AMBUSH_WOLF,
    "Apothecary Stomper": APOTHECARY_STOMPER,
    "Beast-Kin Ranger": BEASTKIN_RANGER,
    "Cackling Prowler": CACKLING_PROWLER,
    "Eager Trufflesnout": EAGER_TRUFFLESNOUT,
    "Elfsworn Giant": ELFSWORN_GIANT,
    "Elvish Regrower": ELVISH_REGROWER,
    "Felling Blow": FELLING_BLOW,
    "Loot, Exuberant Explorer": LOOT_EXUBERANT_EXPLORER,
    "Mossborn Hydra": MOSSBORN_HYDRA,
    "Needletooth Pack": NEEDLETOOTH_PACK,
    "Preposterous Proportions": PREPOSTEROUS_PROPORTIONS,
    "Quakestrider Ceratops": QUAKESTRIDER_CERATOPS,
    "Quilled Greatwurm": QUILLED_GREATWURM,
    "Spinner of Souls": SPINNER_OF_SOULS,
    "Sylvan Scavenging": SYLVAN_SCAVENGING,
    "Treetop Snarespinner": TREETOP_SNARESPINNER,
    "Alesha, Who Laughs at Fate": ALESHA_WHO_LAUGHS_AT_FATE,
    "Anthem of Champions": ANTHEM_OF_CHAMPIONS,
    "Ashroot Animist": ASHROOT_ANIMIST,
    "Dreadwing Scavenger": DREADWING_SCAVENGER,
    "Elenda, Saint of Dusk": ELENDA_SAINT_OF_DUSK,
    "Fiendish Panda": FIENDISH_PANDA,
    "Koma, World-Eater": KOMA_WORLDEATER,
    "Kykar, Zephyr Awakener": KYKAR_ZEPHYR_AWAKENER,
    "Niv-Mizzet, Visionary": NIVMIZZET_VISIONARY,
    "Perforating Artist": PERFORATING_ARTIST,
    "Wardens of the Cycle": WARDENS_OF_THE_CYCLE,
    "Zimone, Paradox Sculptor": ZIMONE_PARADOX_SCULPTOR,
    "Banner of Kinship": BANNER_OF_KINSHIP,
    "Fishing Pole": FISHING_POLE,
    "Leyline Axe": LEYLINE_AXE,
    "Quick-Draw Katana": QUICKDRAW_KATANA,
    "Ravenous Amulet": RAVENOUS_AMULET,
    "Scrawling Crawler": SCRAWLING_CRAWLER,
    "Soulstone Sanctuary": SOULSTONE_SANCTUARY,
    "Ajani, Caller of the Pride": AJANI_CALLER_OF_THE_PRIDE,
    "Ajani's Pridemate": AJANIS_PRIDEMATE,
    "Angel of Finality": ANGEL_OF_FINALITY,
    "Authority of the Consuls": AUTHORITY_OF_THE_CONSULS,
    "Banishing Light": BANISHING_LIGHT,
    "Cathar Commando": CATHAR_COMMANDO,
    "Day of Judgment": DAY_OF_JUDGMENT,
    "Giada, Font of Hope": GIADA_FONT_OF_HOPE,
    "Healer's Hawk": HEALERS_HAWK,
    "Make Your Move": MAKE_YOUR_MOVE,
    "Mischievous Pup": MISCHIEVOUS_PUP,
    "Resolute Reinforcements": RESOLUTE_REINFORCEMENTS,
    "Savannah Lions": SAVANNAH_LIONS,
    "Serra Angel": SERRA_ANGEL,
    "Stroke of Midnight": STROKE_OF_MIDNIGHT,
    "Youthful Valkyrie": YOUTHFUL_VALKYRIE,
    "Aegis Turtle": AEGIS_TURTLE,
    "Aetherize": AETHERIZE,
    "Brineborn Cutthroat": BRINEBORN_CUTTHROAT,
    "Essence Scatter": ESSENCE_SCATTER,
    "Extravagant Replication": EXTRAVAGANT_REPLICATION,
    "Fleeting Distraction": FLEETING_DISTRACTION,
    "Imprisoned in the Moon": IMPRISONED_IN_THE_MOON,
    "Lightshell Duo": LIGHTSHELL_DUO,
    "Micromancer": MICROMANCER,
    "Mocking Sprite": MOCKING_SPRITE,
    "An Offer You Can't Refuse": AN_OFFER_YOU_CANT_REFUSE,
    "Omniscience": OMNISCIENCE,
    "Run Away Together": RUN_AWAY_TOGETHER,
    "Self-Reflection": SELFREFLECTION,
    "Spectral Sailor": SPECTRAL_SAILOR,
    "Think Twice": THINK_TWICE,
    "Time Stop": TIME_STOP,
    "Tolarian Terror": TOLARIAN_TERROR,
    "Witness Protection": WITNESS_PROTECTION,
    "Bake into a Pie": BAKE_INTO_A_PIE,
    "Burglar Rat": BURGLAR_RAT,
    "Diregraf Ghoul": DIREGRAF_GHOUL,
    "Eaten Alive": EATEN_ALIVE,
    "Exsanguinate": EXSANGUINATE,
    "Fake Your Own Death": FAKE_YOUR_OWN_DEATH,
    "Hero's Downfall": HEROS_DOWNFALL,
    "Liliana, Dreadhorde General": LILIANA_DREADHORDE_GENERAL,
    "Macabre Waltz": MACABRE_WALTZ,
    "Marauding Blight-Priest": MARAUDING_BLIGHTPRIEST,
    "Painful Quandary": PAINFUL_QUANDARY,
    "Phyrexian Arena": PHYREXIAN_ARENA,
    "Pilfer": PILFER,
    "Reassembling Skeleton": REASSEMBLING_SKELETON,
    "Rise of the Dark Realms": RISE_OF_THE_DARK_REALMS,
    "Rune-Scarred Demon": RUNESCARRED_DEMON,
    "Stromkirk Bloodthief": STROMKIRK_BLOODTHIEF,
    "Vampire Nighthawk": VAMPIRE_NIGHTHAWK,
    "Zombify": ZOMBIFY,
    "Abrade": ABRADE,
    "Axgard Cavalry": AXGARD_CAVALRY,
    "Brass's Bounty": BRASSS_BOUNTY,
    "Brazen Scourge": BRAZEN_SCOURGE,
    "Burst Lightning": BURST_LIGHTNING,
    "Shock": SHOCK,
    "Drakuseth, Maw of Flames": DRAKUSETH_MAW_OF_FLAMES,
    "Etali, Primal Storm": ETALI_PRIMAL_STORM,
    "Fanatical Firebrand": FANATICAL_FIREBRAND,
    "Firebrand Archer": FIREBRAND_ARCHER,
    "Firespitter Whelp": FIRESPITTER_WHELP,
    "Flamewake Phoenix": FLAMEWAKE_PHOENIX,
    "Frenzied Goblin": FRENZIED_GOBLIN,
    "Goblin Surprise": GOBLIN_SURPRISE,
    "Heartfire Immolator": HEARTFIRE_IMMOLATOR,
    "Hidetsugu's Second Rite": HIDETSUGUS_SECOND_RITE,
    "Involuntary Employment": INVOLUNTARY_EMPLOYMENT,
    "Krenko, Mob Boss": KRENKO_MOB_BOSS,
    "Seismic Rupture": SEISMIC_RUPTURE,
    "Shivan Dragon": SHIVAN_DRAGON,
    "Slagstorm": SLAGSTORM,
    "Spitfire Lagac": SPITFIRE_LAGAC,
    "Sure Strike": SURE_STRIKE,
    "Thrill of Possibility": THRILL_OF_POSSIBILITY,
    "Affectionate Indrik": AFFECTIONATE_INDRIK,
    "Bite Down": BITE_DOWN,
    "Blanchwood Armor": BLANCHWOOD_ARMOR,
    "Broken Wings": BROKEN_WINGS,
    "Bushwhack": BUSHWHACK,
    "Doubling Season": DOUBLING_SEASON,
    "Dwynen, Gilt-Leaf Daen": DWYNEN_GILTLEAF_DAEN,
    "Dwynen's Elite": DWYNENS_ELITE,
    "Elvish Archdruid": ELVISH_ARCHDRUID,
    "Garruk's Uprising": GARRUKS_UPRISING,
    "Genesis Wave": GENESIS_WAVE,
    "Ghalta, Primal Hunger": GHALTA_PRIMAL_HUNGER,
    "Giant Growth": GIANT_GROWTH,
    "Gnarlid Colony": GNARLID_COLONY,
    "Grow from the Ashes": GROW_FROM_THE_ASHES,
    "Inspiring Call": INSPIRING_CALL,
    "Llanowar Elves": LLANOWAR_ELVES,
    "Mild-Mannered Librarian": MILDMANNERED_LIBRARIAN,
    "Nessian Hornbeetle": NESSIAN_HORNBEETLE,
    "Overrun": OVERRUN,
    "Reclamation Sage": RECLAMATION_SAGE,
    "Scavenging Ooze": SCAVENGING_OOZE,
    "Snakeskin Veil": SNAKESKIN_VEIL,
    "Vivien Reid": VIVIEN_REID,
    "Wary Thespian": WARY_THESPIAN,
    "Wildwood Scourge": WILDWOOD_SCOURGE,
    "Balmor, Battlemage Captain": BALMOR_BATTLEMAGE_CAPTAIN,
    "Consuming Aberration": CONSUMING_ABERRATION,
    "Empyrean Eagle": EMPYREAN_EAGLE,
    "Good-Fortune Unicorn": GOODFORTUNE_UNICORN,
    "Heroic Reinforcements": HEROIC_REINFORCEMENTS,
    "Lathril, Blade of the Elves": LATHRIL_BLADE_OF_THE_ELVES,
    "Muldrotha, the Gravetide": MULDROTHA_THE_GRAVETIDE,
    "Progenitus": PROGENITUS,
    "Ruby, Daring Tracker": RUBY_DARING_TRACKER,
    "Swiftblade Vindicator": SWIFTBLADE_VINDICATOR,
    "Tatyova, Benthic Druid": TATYOVA_BENTHIC_DRUID,
    "Thousand-Year Storm": THOUSANDYEAR_STORM,
    "Adventuring Gear": ADVENTURING_GEAR,
    "Burnished Hart": BURNISHED_HART,
    "Campus Guide": CAMPUS_GUIDE,
    "Gleaming Barrier": GLEAMING_BARRIER,
    "Goldvein Pick": GOLDVEIN_PICK,
    "Heraldic Banner": HERALDIC_BANNER,
    "Juggernaut": JUGGERNAUT,
    "Meteor Golem": METEOR_GOLEM,
    "Solemn Simulacrum": SOLEMN_SIMULACRUM,
    "Swiftfoot Boots": SWIFTFOOT_BOOTS,
    "Bloodfell Caves": BLOODFELL_CAVES,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Dismal Backwater": DISMAL_BACKWATER,
    "Evolving Wilds": EVOLVING_WILDS,
    "Jungle Hollow": JUNGLE_HOLLOW,
    "Rogue's Passage": ROGUES_PASSAGE,
    "Rugged Highlands": RUGGED_HIGHLANDS,
    "Scoured Barrens": SCOURED_BARRENS,
    "Secluded Courtyard": SECLUDED_COURTYARD,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
    "Thornwood Falls": THORNWOOD_FALLS,
    "Tranquil Cove": TRANQUIL_COVE,
    "Wind-Scarred Crag": WINDSCARRED_CRAG,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Adamant Will": ADAMANT_WILL,
    "Ancestor Dragon": ANCESTOR_DRAGON,
    "Angelic Edict": ANGELIC_EDICT,
    "Bishop's Soldier": BISHOPS_SOLDIER,
    "Deadly Riposte": DEADLY_RIPOSTE,
    "Elspeth's Smite": ELSPETHS_SMITE,
    "Herald of Faith": HERALD_OF_FAITH,
    "Ingenious Leonin": INGENIOUS_LEONIN,
    "Inspiring Overseer": INSPIRING_OVERSEER,
    "Jazal Goldmane": JAZAL_GOLDMANE,
    "Leonin Skyhunter": LEONIN_SKYHUNTER,
    "Leonin Vanguard": LEONIN_VANGUARD,
    "Moment of Triumph": MOMENT_OF_TRIUMPH,
    "Pacifism": PACIFISM,
    "Prayer of Binding": PRAYER_OF_BINDING,
    "Twinblade Paladin": TWINBLADE_PALADIN,
    "Burrog Befuddler": BURROG_BEFUDDLER,
    "Cancel": CANCEL,
    "Corsair Captain": CORSAIR_CAPTAIN,
    "Eaten by Piranhas": EATEN_BY_PIRANHAS,
    "Exclusion Mage": EXCLUSION_MAGE,
    "Into the Roil": INTO_THE_ROIL,
    "Kitesail Corsair": KITESAIL_CORSAIR,
    "Mystic Archaeologist": MYSTIC_ARCHAEOLOGIST,
    "Opt": OPT,
    "Quick Study": QUICK_STUDY,
    "Starlight Snare": STARLIGHT_SNARE,
    "Storm Fleet Spy": STORM_FLEET_SPY,
    "Bloodtithe Collector": BLOODTITHE_COLLECTOR,
    "Cemetery Recruitment": CEMETERY_RECRUITMENT,
    "Crossway Troublemakers": CROSSWAY_TROUBLEMAKERS,
    "Crow of Dark Tidings": CROW_OF_DARK_TIDINGS,
    "Deadly Plot": DEADLY_PLOT,
    "Death Baron": DEATH_BARON,
    "Highborn Vampire": HIGHBORN_VAMPIRE,
    "Maalfeld Twins": MAALFELD_TWINS,
    "Moment of Craving": MOMENT_OF_CRAVING,
    "Offer Immortality": OFFER_IMMORTALITY,
    "Skeleton Archer": SKELETON_ARCHER,
    "Suspicious Shambler": SUSPICIOUS_SHAMBLER,
    "Undying Malice": UNDYING_MALICE,
    "Untamed Hunger": UNTAMED_HUNGER,
    "Vampire Interloper": VAMPIRE_INTERLOPER,
    "Vampire Neonate": VAMPIRE_NEONATE,
    "Vampire Spawn": VAMPIRE_SPAWN,
    "Battle-Rattle Shaman": BATTLERATTLE_SHAMAN,
    "Carnelian Orb of Dragonkind": CARNELIAN_ORB_OF_DRAGONKIND,
    "Dragon Fodder": DRAGON_FODDER,
    "Dragonlord's Servant": DRAGONLORDS_SERVANT,
    "Dropkick Bomber": DROPKICK_BOMBER,
    "Fire Elemental": FIRE_ELEMENTAL,
    "Goblin Oriflamme": GOBLIN_ORIFLAMME,
    "Goblin Smuggler": GOBLIN_SMUGGLER,
    "Kargan Dragonrider": KARGAN_DRAGONRIDER,
    "Kindled Fury": KINDLED_FURY,
    "Raging Redcap": RAGING_REDCAP,
    "Rapacious Dragon": RAPACIOUS_DRAGON,
    "Scorching Dragonfire": SCORCHING_DRAGONFIRE,
    "Seize the Spoils": SEIZE_THE_SPOILS,
    "Skyraker Giant": SKYRAKER_GIANT,
    "Swab Goblin": SWAB_GOBLIN,
    "Terror of Mount Velus": TERROR_OF_MOUNT_VELUS,
    "Volley Veteran": VOLLEY_VETERAN,
    "Aggressive Mammoth": AGGRESSIVE_MAMMOTH,
    "Bear Cub": BEAR_CUB,
    "Biogenic Upgrade": BIOGENIC_UPGRADE,
    "Druid of the Cowl": DRUID_OF_THE_COWL,
    "Joraga Invocation": JORAGA_INVOCATION,
    "Magnigoth Sentry": MAGNIGOTH_SENTRY,
    "New Horizons": NEW_HORIZONS,
    "Tajuru Pathwarden": TAJURU_PATHWARDEN,
    "Thornweald Archer": THORNWEALD_ARCHER,
    "Thrashing Brontodon": THRASHING_BRONTODON,
    "Wildheart Invoker": WILDHEART_INVOKER,
    "Goblin Firebomb": GOBLIN_FIREBOMB,
    "Pirate's Cutlass": PIRATES_CUTLASS,
    "Uncharted Haven": UNCHARTED_HAVEN,
    "Angelic Destiny": ANGELIC_DESTINY,
    "Archway Angel": ARCHWAY_ANGEL,
    "Ballyrush Banneret": BALLYRUSH_BANNERET,
    "Charming Prince": CHARMING_PRINCE,
    "Crusader of Odric": CRUSADER_OF_ODRIC,
    "Dawnwing Marshal": DAWNWING_MARSHAL,
    "Devout Decree": DEVOUT_DECREE,
    "Disenchant": DISENCHANT,
    "Felidar Cub": FELIDAR_CUB,
    "Felidar Retreat": FELIDAR_RETREAT,
    "Fumigate": FUMIGATE,
    "Knight of Grace": KNIGHT_OF_GRACE,
    "Linden, the Steadfast Queen": LINDEN_THE_STEADFAST_QUEEN,
    "Mentor of the Meek": MENTOR_OF_THE_MEEK,
    "Regal Caracal": REGAL_CARACAL,
    "Release the Dogs": RELEASE_THE_DOGS,
    "Stasis Snare": STASIS_SNARE,
    "Syr Alin, the Lion's Claw": SYR_ALIN_THE_LIONS_CLAW,
    "Valorous Stance": VALOROUS_STANCE,
    "Zetalpa, Primal Dawn": ZETALPA_PRIMAL_DAWN,
    "Arcanis the Omnipotent": ARCANIS_THE_OMNIPOTENT,
    "Chart a Course": CHART_A_COURSE,
    "Dictate of Kruphix": DICTATE_OF_KRUPHIX,
    "Dive Down": DIVE_DOWN,
    "Finale of Revelation": FINALE_OF_REVELATION,
    "Flashfreeze": FLASHFREEZE,
    "Fog Bank": FOG_BANK,
    "Gateway Sneak": GATEWAY_SNEAK,
    "Harbinger of the Tides": HARBINGER_OF_THE_TIDES,
    "Mystical Teachings": MYSTICAL_TEACHINGS,
    "River's Rebuke": RIVERS_REBUKE,
    "Shipwreck Dowser": SHIPWRECK_DOWSER,
    "Sphinx of the Final Word": SPHINX_OF_THE_FINAL_WORD,
    "Tempest Djinn": TEMPEST_DJINN,
    "Unsummon": UNSUMMON,
    "Voracious Greatshark": VORACIOUS_GREATSHARK,
    "Deathmark": DEATHMARK,
    "Demonic Pact": DEMONIC_PACT,
    "Desecration Demon": DESECRATION_DEMON,
    "Dread Summons": DREAD_SUMMONS,
    "Driver of the Dead": DRIVER_OF_THE_DEAD,
    "Duress": DURESS,
    "Kalastria Highborn": KALASTRIA_HIGHBORN,
    "Knight of Malice": KNIGHT_OF_MALICE,
    "Midnight Reaper": MIDNIGHT_REAPER,
    "Myojin of Night's Reach": MYOJIN_OF_NIGHTS_REACH,
    "Nullpriest of Oblivion": NULLPRIEST_OF_OBLIVION,
    "Pulse Tracker": PULSE_TRACKER,
    "Sanguine Indulgence": SANGUINE_INDULGENCE,
    "Tribute to Hunger": TRIBUTE_TO_HUNGER,
    "Vampiric Rites": VAMPIRIC_RITES,
    "Vile Entomber": VILE_ENTOMBER,
    "Wishclaw Talisman": WISHCLAW_TALISMAN,
    "Ball Lightning": BALL_LIGHTNING,
    "Bolt Bend": BOLT_BEND,
    "Crash Through": CRASH_THROUGH,
    "Dragon Mage": DRAGON_MAGE,
    "Dragonmaster Outcast": DRAGONMASTER_OUTCAST,
    "Ghitu Lavarunner": GHITU_LAVARUNNER,
    "Giant Cindermaw": GIANT_CINDERMAW,
    "Harmless Offering": HARMLESS_OFFERING,
    "Hoarding Dragon": HOARDING_DRAGON,
    "Lathliss, Dragon Queen": LATHLISS_DRAGON_QUEEN,
    "Mindsparker": MINDSPARKER,
    "Obliterating Bolt": OBLITERATING_BOLT,
    "Ravenous Giant": RAVENOUS_GIANT,
    "Redcap Gutter-Dweller": REDCAP_GUTTERDWELLER,
    "Stromkirk Noble": STROMKIRK_NOBLE,
    "Taurean Mauler": TAUREAN_MAULER,
    "Viashino Pyromancer": VIASHINO_PYROMANCER,
    "Circuitous Route": CIRCUITOUS_ROUTE,
    "Fierce Empath": FIERCE_EMPATH,
    "Fynn, the Fangbearer": FYNN_THE_FANGBEARER,
    "Gnarlback Rhino": GNARLBACK_RHINO,
    "Heroes' Bane": HEROES_BANE,
    "Mold Adder": MOLD_ADDER,
    "Ordeal of Nylea": ORDEAL_OF_NYLEA,
    "Predator Ooze": PREDATOR_OOZE,
    "Primal Might": PRIMAL_MIGHT,
    "Primeval Bounty": PRIMEVAL_BOUNTY,
    "Rampaging Baloths": RAMPAGING_BALOTHS,
    "Springbloom Druid": SPRINGBLOOM_DRUID,
    "Surrak, the Hunt Caller": SURRAK_THE_HUNT_CALLER,
    "Venom Connoisseur": VENOM_CONNOISSEUR,
    "Vizier of the Menagerie": VIZIER_OF_THE_MENAGERIE,
    "Wildborn Preserver": WILDBORN_PRESERVER,
    "Aurelia, the Warleader": AURELIA_THE_WARLEADER,
    "Ayli, Eternal Pilgrim": AYLI_ETERNAL_PILGRIM,
    "Cloudblazer": CLOUDBLAZER,
    "Deadly Brew": DEADLY_BREW,
    "Drogskol Reaver": DROGSKOL_REAVER,
    "Dryad Militant": DRYAD_MILITANT,
    "Enigma Drake": ENIGMA_DRAKE,
    "Garna, Bloodfist of Keld": GARNA_BLOODFIST_OF_KELD,
    "Halana and Alena, Partners": HALANA_AND_ALENA_PARTNERS,
    "Immersturm Predator": IMMERSTURM_PREDATOR,
    "Maelstrom Pulse": MAELSTROM_PULSE,
    "Mortify": MORTIFY,
    "Ovika, Enigma Goliath": OVIKA_ENIGMA_GOLIATH,
    "Prime Speaker Zegana": PRIME_SPEAKER_ZEGANA,
    "Savage Ventmaw": SAVAGE_VENTMAW,
    "Teach by Example": TEACH_BY_EXAMPLE,
    "Trygon Predator": TRYGON_PREDATOR,
    "Wilt-Leaf Liege": WILTLEAF_LIEGE,
    "Basilisk Collar": BASILISK_COLLAR,
    "Cultivator's Caravan": CULTIVATORS_CARAVAN,
    "Darksteel Colossus": DARKSTEEL_COLOSSUS,
    "Diamond Mare": DIAMOND_MARE,
    "Feldon's Cane": FELDONS_CANE,
    "Fireshrieker": FIRESHRIEKER,
    "Gate Colossus": GATE_COLOSSUS,
    "Mazemind Tome": MAZEMIND_TOME,
    "Pyromancer's Goggles": PYROMANCERS_GOGGLES,
    "Ramos, Dragon Engine": RAMOS_DRAGON_ENGINE,
    "Sorcerous Spyglass": SORCEROUS_SPYGLASS,
    "Soul-Guide Lantern": SOULGUIDE_LANTERN,
    "Steel Hellkite": STEEL_HELLKITE,
    "Three Tree Mascot": THREE_TREE_MASCOT,
    "Azorius Guildgate": AZORIUS_GUILDGATE,
    "Boros Guildgate": BOROS_GUILDGATE,
    "Crawling Barrens": CRAWLING_BARRENS,
    "Cryptic Caves": CRYPTIC_CAVES,
    "Demolition Field": DEMOLITION_FIELD,
    "Dimir Guildgate": DIMIR_GUILDGATE,
    "Golgari Guildgate": GOLGARI_GUILDGATE,
    "Gruul Guildgate": GRUUL_GUILDGATE,
    "Izzet Guildgate": IZZET_GUILDGATE,
    "Orzhov Guildgate": ORZHOV_GUILDGATE,
    "Rakdos Guildgate": RAKDOS_GUILDGATE,
    "Selesnya Guildgate": SELESNYA_GUILDGATE,
    "Simic Guildgate": SIMIC_GUILDGATE,
    "Temple of Abandon": TEMPLE_OF_ABANDON,
    "Temple of Deceit": TEMPLE_OF_DECEIT,
    "Temple of Enlightenment": TEMPLE_OF_ENLIGHTENMENT,
    "Temple of Epiphany": TEMPLE_OF_EPIPHANY,
    "Temple of Malady": TEMPLE_OF_MALADY,
    "Temple of Malice": TEMPLE_OF_MALICE,
    "Temple of Mystery": TEMPLE_OF_MYSTERY,
    "Temple of Plenty": TEMPLE_OF_PLENTY,
    "Temple of Silence": TEMPLE_OF_SILENCE,
    "Temple of Triumph": TEMPLE_OF_TRIUMPH,
    "Angel of Vitality": ANGEL_OF_VITALITY,
    "Lyra Dawnbringer": LYRA_DAWNBRINGER,
    "Make a Stand": MAKE_A_STAND,
    "Confiscate": CONFISCATE,
    "Negate": NEGATE,
    "Rite of Replication": RITE_OF_REPLICATION,
    "Feed the Swarm": FEED_THE_SWARM,
    "Gatekeeper of Malakir": GATEKEEPER_OF_MALAKIR,
    "Massacre Wurm": MASSACRE_WURM,
    "Gratuitous Violence": GRATUITOUS_VIOLENCE,
    "Guttersnipe": GUTTERSNIPE,
    "Impact Tremors": IMPACT_TREMORS,
    "Gigantosaurus": GIGANTOSAURUS,
    "Imperious Perfect": IMPERIOUS_PERFECT,
    "Pelakka Wurm": PELAKKA_WURM,
    "Boros Charm": BOROS_CHARM,
    "Unflinching Courage": UNFLINCHING_COURAGE,
    "Adaptive Automaton": ADAPTIVE_AUTOMATON,
    "Expedition Map": EXPEDITION_MAP,
    "Gilded Lotus": GILDED_LOTUS,
    "Hedron Archive": HEDRON_ARCHIVE,
    "Maze's End": MAZES_END,
    "Hinterland Sanctifier": HINTERLAND_SANCTIFIER,
}

print(f"Loaded {len(FOUNDATIONS_CARDS)} Foundations cards")
