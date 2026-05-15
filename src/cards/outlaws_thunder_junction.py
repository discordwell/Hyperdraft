"""
Outlaws_of_Thunder_Junction (OTJ) Card Implementations

Real card data fetched from Scryfall API.
276 cards in set.
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
    new_id, get_power, get_toughness,
    # OTJ Plot / Saddle helpers (see src/engine/plot_saddle.py)
    is_plotted, is_saddled,
    make_becomes_plotted_trigger, make_saddle_trigger, make_becomes_saddled_trigger,
    set_saddle_threshold,
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_static_pt_boost, make_keyword_grant, make_spell_cast_trigger,
    make_damage_trigger, make_upkeep_trigger, make_end_step_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, create_target_choice, create_modal_choice,
    make_crime_committed_trigger, is_crime_committed,
    open_library_search,
    # Phase 4: activated abilities
    make_activated_ability, make_destroy_ability, make_damage_ability,
    make_sac_destroy_ability,
    # Phase 3: equipment / aura statics
    make_equipment_setup, make_aura_setup,
    # Ward
    make_ward,
    # Dynamic P/T helpers
    count_permanents_with_subtype,
    count_permanents_of_type,
    # Sweep 4: becomes-creature
    becomes_creature,
    # Sweep 4b: becomes-copy-of (continuous-effect copy)
    becomes_copy_of,
    # Cost reduction
    make_cost_reduction,
    # Dynamic P/T
    make_dynamic_pt_boost,
    # W12: Spree (cost-per-mode)
    SpreeMode, make_spree_setup, make_spree_resolve,
    # Phase 5b modal + target normalize
    make_modal_resolve, ModeSpec, normalize_target,
    # Phase 5b alt-cost: Plot
    make_plot_setup,
)
from src.engine.turn_state import spells_cast_this_turn

from src.engine.spell_resolve import (
    resolve_chain,
    resolve_create_token,
    resolve_draw,
    resolve_pump,
    resolve_damage,
    resolve_destroy,
    resolve_exile,
    resolve_counter,
    resolve_life_change,
    _flatten_targets,
    _first_target,
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
    target_creature,
    target_any,
    target_player,
    target_spell,
    # Phase 5b cross-target builders
    another_target_creature,
)


# -----------------------------------------------------------------------------
# Phase 5b migration helpers (OTJ-local copies; mirror src/cards/foundations.py)
# -----------------------------------------------------------------------------

def _otj_resolving_spell_obj(state: GameState) -> Optional[GameObject]:
    """Return the topmost spell on the stack — the resolving spell."""
    stack_zone = state.zones.get('stack') if state and state.zones else None
    if stack_zone is None:
        return None
    for obj_id in reversed(list(stack_zone.objects or [])):
        obj = state.objects.get(obj_id)
        if obj is not None:
            return obj
    return None


def _otj_spell_caster_id(state: GameState) -> Optional[str]:
    obj = _otj_resolving_spell_obj(state)
    if obj is not None and obj.controller:
        return obj.controller
    return getattr(state, 'priority_player', None) or getattr(state, 'active_player', None)


def _otj_damage_to_targets(amount: int):
    """Deal ``amount`` damage to each chosen target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _otj_resolving_spell_obj(state)
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


def _otj_destroy_targets():
    """Destroy each chosen permanent target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _otj_resolving_spell_obj(state)
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


def _otj_pump_targets(power_mod: int, toughness_mod: int, duration: str = 'end_of_turn'):
    """Apply +N/+M to each chosen target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _otj_resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': t.id,
                    'power_mod': power_mod,
                    'toughness_mod': toughness_mod,
                    'duration': duration,
                },
                source=source_id,
            ))
        return events
    return _resolve


def _otj_grant_keywords_to_targets(*keywords: str, duration: str = 'end_of_turn'):
    """Grant keywords to each chosen target."""
    kw_list = tuple(keywords)
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _otj_resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            for kw in kw_list:
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': t.id, 'keyword': kw, 'duration': duration},
                    source=source_id,
                ))
        return events
    return _resolve


def _otj_counter_targets(amount: int = 1, counter_type: str = '+1/+1'):
    """Put counters on each chosen target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _otj_resolving_spell_obj(state)
        source_id = spell.id if spell else None
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': t.id,
                    'counter_type': counter_type,
                    'amount': amount,
                },
                source=source_id,
            ))
        return events
    return _resolve


def _otj_caster_life_change(amount: int):
    """Caster gains/loses ``amount`` life."""
    def _resolve(targets, state: GameState) -> list[Event]:
        caster = _otj_spell_caster_id(state)
        if caster is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster, 'amount': amount},
        )]
    return _resolve


def _otj_caster_draw(amount: int):
    """Caster draws ``amount`` cards."""
    def _resolve(targets, state: GameState) -> list[Event]:
        caster = _otj_spell_caster_id(state)
        if caster is None:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': caster, 'amount': amount},
        )]
    return _resolve


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

# Helper: Check if a creature is an outlaw (Assassin, Mercenary, Pirate, Rogue, Warlock)
OUTLAW_TYPES = {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}

def is_outlaw(obj: GameObject) -> bool:
    """Check if a creature is an outlaw type."""
    return bool(obj.characteristics.subtypes & OUTLAW_TYPES)


def other_outlaws_you_control(source: GameObject):
    """Filter: Other outlaws you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                is_outlaw(target) and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


# -----------------------------------------------------------------------------
# WHITE CARDS
# -----------------------------------------------------------------------------

def holy_cow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 2 life and scry 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sterling_supplier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, put a +1/+1 counter on another target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.id != obj.id and
                    o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_counter(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': selected[0], 'counter_type': '+1/+1', 'amount': 1},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Sterling Supplier: Put a +1/+1 counter on another target creature you control",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_counter
        return []
    return [make_etb_trigger(obj, etb_effect)]


def prosperity_tycoon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def stagecoach_security_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, creatures you control get +1/+1 and vigilance until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Creates temporary buff event
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump_all',
                'controller': obj.controller,
                'power_mod': 1,
                'toughness_mod': 1,
                'keywords': ['vigilance'],
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def wanted_griffin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a Mercenary token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def outlaw_medic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, draw a card."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def vengeful_townsfolk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more other creatures you control die, put a +1/+1 counter on this creature."""
    def other_creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj_id = event.payload.get('object_id')
        if dying_obj_id == source.id:
            return False
        dying_obj = state.objects.get(dying_obj_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def death_trigger_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_death_trigger(obj, death_trigger_effect, other_creature_dies_filter)]


def claim_jumper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if opponent controls more lands, search for Plains."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search not fully implemented - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


def frontier_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, look at top 5, may reveal Mount or Plains."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library manipulation not fully implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def shepherd_of_clouds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return target permanent card mv 3 or less from graveyard.
    Return that card to the battlefield instead if you control a Mount."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        gy_key = f"graveyard_{obj.controller}"
        gy = state.zones.get(gy_key)
        if not gy:
            return []
        permanent_types = {CardType.CREATURE, CardType.ARTIFACT,
                           CardType.ENCHANTMENT, CardType.LAND, CardType.PLANESWALKER}
        legal_targets = []
        for cid in gy.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            if not (card.characteristics.types & permanent_types):
                continue
            mv_str = card.characteristics.mana_cost or ""
            # Approximate mana value from cost string by counting digits & symbols
            mv = 0
            digits = ""
            for ch in mv_str:
                if ch.isdigit():
                    digits += ch
                elif ch.isalpha():
                    mv += 1
            if digits:
                try:
                    mv += int(digits)
                except ValueError:
                    pass
            if mv <= 3:
                legal_targets.append(cid)
        if not legal_targets:
            return []

        # Check if we control a Mount
        controls_mount = any(
            o.controller == obj.controller and
            o.zone == ZoneType.BATTLEFIELD and
            "Mount" in (o.characteristics.subtypes or set())
            for o in state.objects.values()
        )

        def handle_return(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            if controls_mount:
                # Reanimate to battlefield
                return [Event(
                    type=EventType.RETURN_FROM_GRAVEYARD,
                    payload={'object_id': tid, 'to': 'battlefield'},
                    source=choice.source_id,
                )]
            return [Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'object_id': tid, 'player': obj.controller},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Shepherd of the Clouds: Return target permanent card with mana value 3 or less from your graveyard",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_return
        return []
    return [make_etb_trigger(obj, etb_effect)]


def fortune_loyal_steed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Fortune enters, scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# BLUE CARDS
# -----------------------------------------------------------------------------

def harrier_strix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, tap target permanent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if o.zone == ZoneType.BATTLEFIELD and not o.state.tapped:
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_tap(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.TAP,
                payload={'object_id': selected[0]},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Harrier Strix: Tap target permanent",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_tap
        return []
    return [make_etb_trigger(obj, etb_effect)]


def loan_shark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you've cast two+ spells this turn, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check spell count this turn - simplified, always triggers for now
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def peerless_ropemaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return up to one target tapped creature to its owner's hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types and
                    o.state.tapped):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_bounce(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': selected[0]},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Peerless Ropemaster: Return up to one target tapped creature to its owner's hand",
            min_targets=0,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_bounce
        return []
    return [make_etb_trigger(obj, etb_effect)]


def outlaw_stitcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Zombie Rogue token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Zombie Rogue Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Zombie', 'Rogue'],
                'colors': [Color.BLUE, Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def geralf_the_fleshwright_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell during your turn other than your first, create a Zombie Rogue."""
    # Complex trigger - simplified placeholder
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Zombie Rogue Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Zombie', 'Rogue'],
                'colors': [Color.BLUE, Color.BLACK]
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]


def nimble_brigand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, draw a card."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def spring_splasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, target creature defending player controls gets -3/-0."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Approximate "defending player" as any opponent.
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types and
                    o.controller != obj.controller):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_debuff(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': selected[0], 'power_mod': -3, 'toughness_mod': 0,
                         'duration': 'end_of_turn'},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Spring Splasher: Target creature defending player controls gets -3/-0 until end of turn",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_debuff
        return []
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# BLACK CARDS
# -----------------------------------------------------------------------------

def ambush_gigapede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature an opponent controls gets -2/-2 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types and
                    o.controller != obj.controller):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_debuff(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': selected[0], 'power_mod': -2, 'toughness_mod': -2,
                         'duration': 'end_of_turn'},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Ambush Gigapede: Target creature an opponent controls gets -2/-2 until end of turn",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_debuff
        return []
    return [make_etb_trigger(obj, etb_effect)]


def desperate_bloodseeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target player mills two cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = list(state.players.keys())
        if not legal_targets:
            return []

        def handle_mill(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.MILL,
                payload={'player': selected[0], 'amount': 2},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Desperate Bloodseeker: Target player mills two cards",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_mill
        return []
    return [make_etb_trigger(obj, etb_effect)]


def nezumi_linkbreaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a Mercenary token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def vault_plunderer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target player draws a card and loses 1 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Can target self or opponent - simplified to self
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
    return [make_etb_trigger(obj, etb_effect)]


def rictus_robber_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if a creature died this turn, create a Zombie Rogue token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check if creature died this turn - simplified, always triggers
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Zombie Rogue Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Zombie', 'Rogue'],
                'colors': [Color.BLUE, Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rooftop_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, destroy target creature an opponent controls that was dealt damage this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types and
                    o.controller != obj.controller and
                    (o.state.damage > 0 or o.state.damage_marked > 0)):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_destroy(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.DESTROY,
                payload={'object_id': selected[0]},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Rooftop Assassin: Destroy target creature an opponent controls that was dealt damage this turn",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_destroy
        return []
    return [make_etb_trigger(obj, etb_effect)]


def gisa_the_hellraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Skeletons and Zombies you control get +1/+1 and have menace."""
    def affects_zombie_or_skeleton(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                ("Zombie" in target.characteristics.subtypes or
                 "Skeleton" in target.characteristics.subtypes) and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors = make_static_pt_boost(obj, 1, 1, affects_zombie_or_skeleton)
    interceptors.append(make_keyword_grant(obj, ['menace'], affects_zombie_or_skeleton))
    return interceptors


def hollow_marauder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, any number of target opponents each discard a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        opponents = [pid for pid in state.players.keys() if pid != obj.controller]
        if not opponents:
            return []

        def handle_discard(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.DISCARD,
                payload={'player': pid, 'amount': 1},
                source=choice.source_id,
            ) for pid in selected]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=opponents,
            prompt="Hollow Marauder: Choose any number of opponents to each discard a card",
            min_targets=0,
            max_targets=len(opponents),
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_discard
        return []
    return [make_etb_trigger(obj, etb_effect)]


def rakish_crew_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def tinybones_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Tinybones Joins Up enters, any number of target players each discard a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        all_players = list(state.players.keys())
        if not all_players:
            return []

        def handle_discard(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.DISCARD,
                payload={'player': pid, 'amount': 1},
                source=choice.source_id,
            ) for pid in selected]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=all_players,
            prompt="Tinybones Joins Up: Choose any number of target players to each discard a card",
            min_targets=0,
            max_targets=len(all_players),
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_discard
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# RED CARDS
# -----------------------------------------------------------------------------

def cunning_coyote_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, another target creature you control gets +1/+1 and gains haste until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.id != obj.id and
                    o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_pump(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            return [
                Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': tid, 'power_mod': 1, 'toughness_mod': 1,
                             'duration': 'end_of_turn'},
                    source=choice.source_id,
                ),
                Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': tid, 'keyword': 'haste', 'duration': 'end_of_turn'},
                    source=choice.source_id,
                ),
            ]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Cunning Coyote: Another target creature you control gets +1/+1 and gains haste until end of turn",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_pump
        return []
    return [make_etb_trigger(obj, etb_effect)]


def discerning_peddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may discard a card. If you do, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Approximate as a hard looting (engine doesn't expose may-discard-then-conditional-draw cleanly).
        hand_key = f"hand_{obj.controller}"
        hand = state.zones.get(hand_key)
        if not hand or not hand.objects:
            return []
        return [
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
        ]
    return [make_etb_trigger(obj, etb_effect)]


def hellspur_posse_boss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other outlaws you control have haste. When this enters, create two Mercenary tokens."""
    interceptors = []

    # Grant haste to other outlaws
    interceptors.append(make_keyword_grant(obj, ['haste'], other_outlaws_you_control(obj)))

    # ETB: Create two Mercenary tokens
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Mercenary Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Mercenary'],
                    'colors': [Color.RED]
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Mercenary Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Mercenary'],
                    'colors': [Color.RED]
                },
                source=obj.id
            )
        ]

    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors


def prickly_pair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def mine_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you control another outlaw, create a Treasure token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check for other outlaw - simplified
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def irascible_wolverine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, exile the top card of your library. Until end of turn, you may play that card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={'player': obj.controller, 'amount': 1, 'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def scalestorm_summoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, create a 3/1 red Dinosaur token if you control a creature with power 4+."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Check for power 4+ creature - simplified
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dinosaur Token',
                'controller': obj.controller,
                'power': 3,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Dinosaur'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def terror_of_the_peaks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control enters, this deals damage equal to that creature's power to any target."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return []
        power = entering_obj.characteristics.power or 0
        if power <= 0:
            return []

        # Legal targets: any creature on the battlefield, or any player.
        legal_targets = list(state.players.keys())
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    (CardType.CREATURE in o.characteristics.types or
                     CardType.PLANESWALKER in o.characteristics.types)):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_damage(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'target_id': target_id,
                         'amount': power, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt=f"Terror of the Peaks: Deal {power} damage to any target",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_damage
        return []

    return [make_etb_trigger(obj, creature_etb_effect, creature_etb_filter)]


def ertha_jo_frontier_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Ertha Jo enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# GREEN CARDS
# -----------------------------------------------------------------------------

def beastbond_outcaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you control a creature with power 4+, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check for power 4+ creature - simplified
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def goldvein_hydra_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create Treasure tokens equal to its power."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Would need to track power at death
        power = obj.characteristics.power or 0
        events = []
        for _ in range(power):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                    'colors': []
                },
                source=obj.id
            ))
        return events
    return [make_death_trigger(obj, death_effect)]


def outcaster_greenblade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, search for a basic land or Desert card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search - not fully implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def outcaster_trailblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, add one mana of any color. Whenever another power 4+ creature enters, draw a card."""
    interceptors = []

    # ETB mana
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': obj.controller, 'mana': 'any', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Draw on big creature ETB
    def big_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                (entering_obj.characteristics.power or 0) >= 4)

    def big_creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, big_creature_etb_effect, big_creature_etb_filter))
    return interceptors


def patient_naturalist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, mill three cards. Put a land card from among them into your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Mill effect
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def railway_brawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control enters, put +1/+1 counters on it equal to its power."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if entering_obj:
            power = entering_obj.characteristics.power or 0
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': entering_id, 'counter_type': '+1/+1', 'amount': power},
                source=obj.id
            )]
        return []

    return [make_etb_trigger(obj, creature_etb_effect, creature_etb_filter)]


def spinewoods_paladin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# MULTICOLOR CARDS
# -----------------------------------------------------------------------------

def annie_flash_the_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Annie Flash enters, if you cast it, return target permanent card mv 3 or less from graveyard to the battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        gy_key = f"graveyard_{obj.controller}"
        gy = state.zones.get(gy_key)
        if not gy:
            return []
        permanent_types = {CardType.CREATURE, CardType.ARTIFACT,
                           CardType.ENCHANTMENT, CardType.LAND, CardType.PLANESWALKER}
        legal_targets = []
        for cid in gy.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            if not (card.characteristics.types & permanent_types):
                continue
            mv_str = card.characteristics.mana_cost or ""
            mv = 0
            digits = ""
            for ch in mv_str:
                if ch.isdigit():
                    digits += ch
                elif ch.isalpha():
                    mv += 1
            if digits:
                try:
                    mv += int(digits)
                except ValueError:
                    pass
            if mv <= 3:
                legal_targets.append(cid)
        if not legal_targets:
            return []

        def handle_reanimate(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={'object_id': selected[0], 'to': 'battlefield', 'tapped': True},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Annie Flash: Return target permanent card with mana value 3 or less from your graveyard to the battlefield tapped",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_reanimate
        return []
    return [make_etb_trigger(obj, etb_effect)]


def annie_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    o.controller != obj.controller and
                    (CardType.CREATURE in o.characteristics.types or
                     CardType.PLANESWALKER in o.characteristics.types)):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_damage(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': tid, 'target_id': tid, 'amount': 5,
                         'source': choice.source_id, 'is_combat': False},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Annie Joins Up: Deal 5 damage to target creature or planeswalker an opponent controls",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_damage
        return []
    return [make_etb_trigger(obj, etb_effect)]


def baron_bertram_graywater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more tokens you control enter, create a 1/1 Vampire Rogue with lifelink."""
    def token_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        # Check if it's a token controlled by us
        return (entering_obj.controller == source.controller and
                entering_obj.state.is_token)

    def token_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Vampire Rogue Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Vampire', 'Rogue'],
                'colors': [Color.BLACK],
                'keywords': ['lifelink']
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, token_etb_effect, token_etb_filter)]


def bonny_pall_clearcutter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Bonny Pall enters, create Beau, a legendary blue Ox creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Beau',
                'controller': obj.controller,
                'power': 0,  # Variable based on lands
                'toughness': 0,
                'types': [CardType.CREATURE],
                'subtypes': ['Ox'],
                'supertypes': ['Legendary'],
                'colors': [Color.BLUE]
            },
            source=obj.id
        )]

    interceptors = [make_etb_trigger(obj, etb_effect)]

    # Whenever you attack, draw a card
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors


def bruse_tarl_roving_rancher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Oxen you control have double strike."""
    def affects_oxen(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                "Ox" in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    return [make_keyword_grant(obj, ['double_strike'], affects_oxen)]


def honest_rutstein_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Honest Rutstein enters, return target creature card from your graveyard to your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        gy_key = f"graveyard_{obj.controller}"
        gy = state.zones.get(gy_key)
        if not gy:
            return []
        legal_targets = []
        for cid in gy.objects:
            card = state.objects.get(cid)
            if card and CardType.CREATURE in card.characteristics.types:
                legal_targets.append(cid)
        if not legal_targets:
            return []

        def handle_return(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'object_id': selected[0], 'player': obj.controller},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Honest Rutstein: Return target creature card from your graveyard to your hand",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_return
        return []
    return [make_etb_trigger(obj, etb_effect)]


def intimidation_campaign_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, each opponent loses 1 life, you gain 1 life, and you draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
        # Each opponent loses 1 life
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def jem_lightfoote_sky_explorer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Check if no spell cast from hand - simplified
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def kellan_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a legendary creature you control enters, put a +1/+1 counter on each creature you control."""
    def legendary_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                "Legendary" in (entering_obj.characteristics.supertypes or set()))

    def legendary_etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events

    return [make_etb_trigger(obj, legendary_etb_effect, legendary_etb_filter)]


def kraum_violent_cacophony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, put a +1/+1 counter on Kraum and draw a card."""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]


def malcolm_the_eyes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, investigate."""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]


def miriam_herd_whisperer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Mount or Vehicle you control attacks, put a +1/+1 counter on it."""
    def mount_or_vehicle_attacks_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        # Check for Mount or Vehicle subtypes (Vehicle is an artifact subtype, not a CardType)
        subtypes = attacker.characteristics.subtypes
        return (attacker.controller == source.controller and
                ("Mount" in subtypes or "Vehicle" in subtypes))

    def mount_attack_effect(event: Event, state: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id')
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': attacker_id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_attack_trigger(obj, mount_attack_effect, mount_or_vehicle_attacks_filter)]


def ruthless_lawbringer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may sacrifice another creature. When you do, destroy target nonland permanent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Sacrifice + destroy - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def selvala_eager_trailblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a creature spell, create a Mercenary token."""
    def creature_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, creature_cast_effect, spell_type_filter={CardType.CREATURE})]


def vial_smasher_gleeful_grenadier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another outlaw you control enters, Vial Smasher deals 1 damage to target opponent."""
    def outlaw_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                is_outlaw(entering_obj))

    def outlaw_etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required - simplified to first opponent
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []

    return [make_etb_trigger(obj, outlaw_etb_effect, outlaw_etb_filter)]


def vraska_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Vraska Joins Up enters, put a deathtouch counter on each creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': 'deathtouch', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def wrangler_of_the_damned_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, create a Spirit token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Spirit Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Spirit'],
                'colors': [Color.WHITE],
                'keywords': ['flying']
            },
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


# -----------------------------------------------------------------------------
# ARTIFACT CREATURES
# -----------------------------------------------------------------------------

def oasis_gardener_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def silver_deputy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may search for a basic land or Desert card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def sterling_hound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, surveil 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# MORE SETUP FUNCTIONS
# -----------------------------------------------------------------------------

def slickshot_showoff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature spell, this creature gets +2/+0 until end of turn."""
    def noncreature_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target': obj.id,
                'power_mod': 2,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]

    def is_noncreature_spell(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    return [make_spell_cast_trigger(obj, noncreature_cast_effect, filter_fn=is_noncreature_spell)]


def razzledazzler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, put a +1/+1 counter on this creature."""
    def second_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, second_spell_effect)]


def ironfist_pulverizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, this deals 2 damage to target opponent."""
    def second_spell_effect(event: Event, state: GameState) -> list[Event]:
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 2, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []
    return [make_spell_cast_trigger(obj, second_spell_effect)]


def blacksnag_buzzard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature enters with a +1/+1 counter on it if a creature died this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - always adds counter
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def blood_hustler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, put a +1/+1 counter on this creature.
    (Once per turn.)"""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def raven_of_fell_omens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, each opponent loses 1 life and you gain 1 life.
    (Once per turn.)"""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': pid, 'amount': -1},
                    source=obj.id,
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        ))
        return events
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def canyon_crab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, draw and discard."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_end_step_trigger(obj, end_step_effect)]


def prairie_dog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, +1/+1 counter."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def inventive_wingsmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, put a flying counter."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'flying', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def nurturing_pixie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return up to one target non-Faerie, nonland permanent you control to its owner's hand.
    If a permanent was returned this way, put a +1/+1 counter on this creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.LAND not in o.characteristics.types and
                    "Faerie" not in (o.characteristics.subtypes or set())):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_bounce(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [
                Event(
                    type=EventType.RETURN_TO_HAND,
                    payload={'object_id': selected[0]},
                    source=choice.source_id,
                ),
                Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=choice.source_id,
                ),
            ]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Nurturing Pixie: Return up to one non-Faerie, nonland permanent you control to its owner's hand",
            min_targets=0,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_bounce
        return []
    return [make_etb_trigger(obj, etb_effect)]


def magda_the_hoardmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, create a tapped Treasure token.
    (Once per turn.)"""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True,
                'tapped': True,
            },
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def rodeo_pyromancers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your first spell each turn, add RR."""
    def first_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': obj.controller, 'mana': 'RR', 'amount': 2},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, first_spell_effect)]


def trained_arynx_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 2; whenever this creature attacks while saddled, it gains first strike until end of turn. Scry 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'first strike', 'duration': 'end_of_turn'},
                source=obj.id,
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
        ]
    return [make_saddle_trigger(obj, threshold=2, effect_fn=attack_effect)]


def bridled_bighorn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 2; vigilance; whenever this creature attacks while saddled, create a 1/1 white Sheep creature token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'name': 'Sheep Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Sheep'},
                'colors': {Color.WHITE},
                'is_token': True,
            },
            source=obj.id
        )]
    return [make_saddle_trigger(obj, threshold=2, effect_fn=attack_effect)]


def bounding_felidar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 2; whenever this creature attacks while saddled, put a +1/+1 counter on each other creature you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_saddle_trigger(obj, threshold=2, effect_fn=attack_effect)]


def caustic_bronco_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, reveal the top card and put it into your hand."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def duelist_of_the_mind_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Power is equal to the number of cards drawn this turn (base 0)."""
    # Crime-trigger draw rider is engine-gap (crime tracking not fully wired).
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def power_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        # Cards drawn-this-turn (controller). The standard tracker key is set by some draw paths;
        # fall back to 0 if missing.
        n = st.turn_data.get(f"{obj.controller}_cards_drawn_this_turn", 0)
        return (n, 0)

    return make_dynamic_pt_boost(obj, power_mod, affects_self)


# =============================================================================
# OTJ MISSING-CARD SETUP FUNCTIONS (auto-wired)
# =============================================================================
# Note: OTJ "crime" mechanic isn't engine-tracked; crime triggers are stubbed.
# Plot-only triggers ("when this card becomes plotted") are stubs as plot is
# not implemented. Saddle and "while saddled" triggers fire on attack as the
# best available approximation.

# -----------------------------------------------------------------------------
# WHITE MISSING SETUPS
# -----------------------------------------------------------------------------

def archangel_of_tithes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Tax-attack/tax-block static abilities."""
    # engine gap: no support for "creatures can't attack/block unless paying X"
    return []


def armored_armadillo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward {1}; activated {3}{W}: +X/+0 EOT, X = its toughness."""
    def _pump_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        # Compute X = source's toughness right now
        try:
            x = get_toughness(o, st)
        except Exception:
            x = o.characteristics.toughness or 0
        if x <= 0:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': o.id,
                'power_mod': x,
                'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=o.id,
            controller=o.controller,
        )]

    make_activated_ability(
        obj,
        cost="{3}{W}",
        effect_fn=_pump_effect,
        description="{3}{W}: This creature gets +X/+0 until end of turn, where X is its toughness.",
    )
    return [make_ward(obj, mana_cost="{1}")]


def aven_interrupter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB exile target spell -> plotted. Cost-up for graveyard/exile spells."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-and-plot a spell on the stack, plus opponent cost increase
        return []
    return [make_etb_trigger(obj, etb_effect)]


def dust_animus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Conditional ETB counters; plot."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Five+ untapped lands -> two +1/+1 counters and a lifelink counter
        events: list[Event] = []
        untapped_lands = 0
        for o in state.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.LAND in o.characteristics.types and
                    not o.state.tapped):
                untapped_lands += 1
        if untapped_lands >= 5:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
                source=obj.id,
            ))
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'lifelink', 'amount': 1},
                source=obj.id,
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def high_noon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Each player can't cast more than one spell each turn; activated damage."""
    # engine gap: spell-count restriction and sacrifice-for-damage activated ability
    return []


def lassoed_by_the_law_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB exile a nonland; ETB create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-until-leaves; we still emit the Mercenary token half
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Mercenary',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Mercenary'},
                'colors': {Color.RED},
                'is_token': True,
            },
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def mystical_tether_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB exile target artifact/creature an opponent controls until leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-until-leaves replacement effect not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def omenport_vigilante_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Has double strike if you've committed a crime this turn."""
    def affects_self_when_crime(target: GameObject, st: GameState) -> bool:
        return (target.id == obj.id and
                target.zone == ZoneType.BATTLEFIELD and
                is_crime_committed(obj.controller, st))
    return [make_keyword_grant(obj, ['double strike'], affects_self_when_crime)]


def sheriff_of_safe_passage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with +1/+1 counter plus one for each other creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        count = 1  # the base counter
        for o in state.objects.values():
            if (o.id != obj.id and
                    o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                count += 1
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': count},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sterling_keykeeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, {T}: Tap target non-Mount creature."""
    def tap_target(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target = st.objects.get(target_id) if isinstance(target_id, str) else None
        # Filter out Mounts
        if target and "Mount" in (target.characteristics.subtypes or set()):
            return []
        return [Event(
            type=EventType.TAP_TARGET,
            payload={'object_id': target_id},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=tap_target,
        description="Tap target non-Mount creature",
        targets_required=1, target_kind="creature",
    )
    return []


def thunder_lasso_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment: ETB attach; +1/+1 to equipped; tap on attack."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: auto-attach to a chosen creature; equipment static handled by aura layer elsewhere
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# BLUE MISSING SETUPS
# -----------------------------------------------------------------------------

def archmages_newt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to a player -> grant flashback to instant/sorcery in graveyard."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: granting flashback to a graveyard card not engine-tracked
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def daring_thunderthief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped (Flash is keyword-handled at cast time)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP,
            payload={'object_id': obj.id},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def deepmuck_desperado_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, each opponent mills three.
    (Once per turn.)"""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.MILL,
                    payload={'player': pid, 'amount': 3},
                    source=obj.id,
                ))
        return events
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def double_down_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an outlaw spell, copy that spell."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        # Try to read subtypes from the cast event; if outlaw, emit a copy event.
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id) if spell_id else None
        subtypes = set()
        if spell:
            subtypes = spell.characteristics.subtypes or set()
        else:
            subtypes = set(event.payload.get('subtypes', []) or [])
        if not (subtypes & OUTLAW_TYPES):
            return []
        return [Event(
            type=EventType.COPY_SPELL,
            payload={'spell_id': spell_id, 'controller': obj.controller},
            source=obj.id,
        )]
    return [make_spell_cast_trigger(obj, cast_effect)]


def emergent_haunting_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand
    this turn and this enchantment isn't a creature, it becomes a 3/3 Spirit creature
    with flying. (We approximate "from hand" via the engine's spells_cast counter.)"""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Only activate on controller's end step (handled by make_end_step_trigger).
        if spells_cast_this_turn(obj.controller, state) > 0:
            return []
        if CardType.CREATURE in obj.characteristics.types:
            return []
        becomes_creature(
            obj, state,
            power=3, toughness=3,
            subtypes={"Spirit"},
            keywords=["flying"],
            duration='while_on_battlefield',
        )
        return []

    return [make_end_step_trigger(obj, end_step_effect)]


def fblthp_lost_on_the_range_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward {2}; play-from-top-of-library + plot top card."""
    # engine gap: top-of-library plot/play permissions not engine-tracked.
    return [make_ward(obj, mana_cost="{2}")]


def geyser_drake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: during turns other than yours, spells you cast cost {1} less.
    Flying granted via printed keyword text.
    """
    def applies(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller:
            return False
        # Only during opponents' turns
        active = getattr(st, 'active_player', None)
        return active is not None and active != obj.controller

    return [make_cost_reduction(obj, applies_to=applies, amount=1)]


def the_key_to_the_vault_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment combat-damage trigger -> impulse exile + free cast."""
    # engine gap: equipment damage triggers + free-cast not engine-tracked
    return []


def marauding_sphinx_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, surveil 2 (once/turn)."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def shackle_slinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, tap or stun a creature."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: second-spell-per-turn detection + targeting + stun counters
        return []
    return [make_spell_cast_trigger(obj, cast_effect)]


def slickshot_lockpicker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB grant flashback to instant/sorcery in graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: flashback grant to a graveyard card not engine-tracked
        return []
    return [make_etb_trigger(obj, etb_effect)]


def slickshot_vaultbuster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """+2/+0 while you've committed a crime this turn."""
    def affects_self_when_crime(target: GameObject, st: GameState) -> bool:
        return (target.id == obj.id and
                target.zone == ZoneType.BATTLEFIELD and
                is_crime_committed(obj.controller, st))
    return make_static_pt_boost(obj, power_mod=2, toughness_mod=0,
                                affects_filter=affects_self_when_crime)


def stoic_sphinx_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hexproof as long as you haven't cast a spell this turn."""
    def affects_self_when_no_spells(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        return spells_cast_this_turn(st, obj.controller) == 0

    return [make_keyword_grant(obj, ['hexproof'], affects_self_when_no_spells)]


def stop_cold_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: ETB tap enchanted; enchanted loses abilities and doesn't untap."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura/enchanted-target manipulation not modeled
        return []
    return [make_etb_trigger(obj, etb_effect)]


def visage_bandit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Optional ETB-as-copy-of-creature; plot."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: enter-as-a-copy choice not modeled
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# BLACK MISSING SETUPS
# -----------------------------------------------------------------------------

def blood_hustler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime -> +1/+1 counter on this creature; activated drain.
    (Once per turn.) Activated drain ability not implemented."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def boneyard_desecrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{B}, Sacrifice another creature: Put a +1/+1 counter on this creature.

    The "if an outlaw was sacrificed, also create a Treasure" rider isn't
    enforced because the cost framework doesn't tell us what was sacrificed.
    """
    from src.cards.interceptor_helpers import make_counter_ability
    make_counter_ability(
        obj, cost="{1}{B}, Sacrifice another creature",
        counter_type="+1/+1", amount=1, target_self=True,
        description="Put a +1/+1 counter on this creature",
    )
    return []


def forsaken_miner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature can't block. (Crime trigger from graveyard is engine-gap.)"""
    from src.cards.interceptor_helpers import make_cant_block
    return [make_cant_block(obj)]


def kaervek_the_punisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime -> exile up to one target black card from your graveyard.
    The "copy it and may cast (you lose 2 life if you do)" rider is an engine
    gap (no graveyard-copy-cast flow); we still emit the exile and the
    associated 2-life loss as the simplification chosen here."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        gy_key = f"graveyard_{obj.controller}"
        gy = state.zones.get(gy_key)
        if not gy:
            return []
        legal_targets: list[str] = []
        for cid in gy.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            if Color.BLACK in (card.characteristics.colors or set()):
                legal_targets.append(cid)
        if not legal_targets:
            return []

        def handle_exile(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            return [
                Event(
                    type=EventType.EXILE,
                    payload={'object_id': tid},
                    source=choice.source_id,
                ),
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': -2},
                    source=choice.source_id,
                ),
            ]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Kaervek, the Punisher: Exile up to one target black card from your graveyard",
            min_targets=0,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_exile
        return []
    return [make_crime_committed_trigger(obj, crime_effect)]


def overzealous_muscle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime during your turn -> indestructible until end of turn."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        if state.active_player != obj.controller:
            return []
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect)]


def rattleback_apothecary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch (kw); crime -> menace or lifelink to your creature.
    Simplification: grant menace+lifelink to self until end of turn on crime."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': obj.id, 'keyword': 'menace', 'duration': 'end_of_turn'},
                  source=obj.id),
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': obj.id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
                  source=obj.id),
        ]
    return [make_crime_committed_trigger(obj, crime_effect)]


def servant_of_the_stinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage -> if crime, may sacrifice for tutor."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: crime tracking + library tutor not engine-tracked
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def tinybones_the_pickpocket_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player -> may cast nonland card from their graveyard."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: cross-player-graveyard cast permission not engine-tracked
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def unscrupulous_contractor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may sacrifice a creature. When you do, target player draws two cards and loses 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Approximate: skip the optional sacrifice (engine gap), but offer the
        # target choice for draw/life-loss so the visible payoff fires.
        legal_players = list(state.players.keys())
        if not legal_players:
            return []

        def handle_payoff(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            return [
                Event(
                    type=EventType.DRAW,
                    payload={'player': tid, 'amount': 2},
                    source=choice.source_id,
                ),
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': tid, 'amount': -2},
                    source=choice.source_id,
                ),
            ]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_players,
            prompt="Unscrupulous Contractor: Target player draws two cards and loses 2 life",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_payoff
        return []
    return [make_etb_trigger(obj, etb_effect)]


def vadmir_new_blood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime -> +1/+1 counter (once/turn); menace+lifelink at 4+ counters."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    def has_threshold(target: GameObject, st: GameState) -> bool:
        return (target.id == obj.id and
                target.zone == ZoneType.BATTLEFIELD and
                int(target.state.counters.get('+1/+1', 0)) >= 4)

    return [
        make_crime_committed_trigger(obj, crime_effect, once_per_turn=True),
        make_keyword_grant(obj, ['menace', 'lifelink'], has_threshold),
    ]


# -----------------------------------------------------------------------------
# RED MISSING SETUPS
# -----------------------------------------------------------------------------

def brimstone_roundup_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, create a Mercenary."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: per-turn Nth-spell counting not implemented
        return []
    return [make_spell_cast_trigger(obj, cast_effect)]


def calamity_galloping_inferno_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 1; haste; saddled-attack: copy a creature that saddled it (best-effort: spawn a token copy of one saddler)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Pick the first nonlegendary saddler we can find and copy it twice.
        events: list[Event] = []
        for sid in (obj.state.saddled_by_this_turn or []):
            saddler = state.objects.get(sid)
            if not saddler or 'Legendary' in (saddler.characteristics.supertypes or set()):
                continue
            # Two attacking copies (per card text: "Repeat this process once.")
            for _ in range(2):
                events.append(Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        'controller': obj.controller,
                        'name': f"{saddler.name} Copy",
                        'power': saddler.characteristics.power or 0,
                        'toughness': saddler.characteristics.toughness or 0,
                        'types': set(saddler.characteristics.types),
                        'subtypes': set(saddler.characteristics.subtypes or set()),
                        'colors': set(saddler.characteristics.colors or set()),
                        'tapped': True,
                        'attacking': True,
                        'is_token': True,
                        'sacrifice_at_next_end_step': True,
                    },
                    source=obj.id,
                ))
            break
        return events
    return [make_saddle_trigger(obj, threshold=1, effect_fn=attack_effect)]


def deadeye_duelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach (kw); {1}, {T}: This creature deals 1 damage to target opponent."""
    make_damage_ability(
        obj, cost="{1}, {T}", damage=1,
        description="Deadeye Duelist deals 1 damage to target opponent",
        target_kind="opponent",
    )
    return []


def demonic_ruckus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted +1/+1, menace, trample; LTB cantrip; plot."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]
    return [make_death_trigger(obj, death_effect)]


def ferocification_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of combat on your turn, choose one:
      - Target creature you control gets +2/+0 UEOT.
      - Target creature you control gains menace and haste UEOT.
    Wired as a beginning-of-combat REACT that opens a modal target choice;
    the choice handler emits PT_MODIFICATION or GRANT_KEYWORD events on the
    chosen creature."""
    def beginning_of_combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START and event.payload.get('phase') not in ('combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller

    def open_modal(event: Event, state: GameState) -> InterceptorResult:
        legal_targets: list[str] = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)
        if not legal_targets:
            return InterceptorResult(action=InterceptorAction.PASS)

        def handle_modal(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            mode = (choice.callback_data or {}).get('mode_index', 0)
            tid = selected[0]
            if mode == 1:
                return [
                    Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={'object_id': tid, 'keyword': 'menace', 'duration': 'end_of_turn'},
                        source=choice.source_id,
                    ),
                    Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={'object_id': tid, 'keyword': 'haste', 'duration': 'end_of_turn'},
                        source=choice.source_id,
                    ),
                ]
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': tid, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
                source=choice.source_id,
            )]

        # Default: choose mode 0 (+2/+0) and prompt for the target.
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Ferocification: target creature you control gets +2/+0 UEOT (mode 0) or gains menace+haste UEOT (mode 1)",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_modal
        choice.callback_data['mode_index'] = 0
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=beginning_of_combat_filter,
        handler=open_modal,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (open_modal(e, s).new_events or []),
    )]


def gila_courser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 1; saddled-attack: exile top of library; you may play it until end of (next) turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={'player': obj.controller, 'amount': 1, 'until': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_saddle_trigger(obj, threshold=1, effect_fn=attack_effect)]


def hellspur_brute_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: affinity for outlaws — {1} less per Assassin/Mercenary/Pirate/Rogue/Warlock you control.
    Trample granted via printed keyword text.
    """
    OUTLAW_TYPES = {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}

    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        n = 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == controller
                    and o.characteristics.subtypes & OUTLAW_TYPES):
                n += 1
        return n

    return [make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                                amount=amount_fn, self_only=True)]


def longhorn_sharpshooter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; when this card becomes plotted, it deals 2 damage to any target. Plot {3}{R}."""
    def becomes_plotted_effect(event: Event, state: GameState) -> list[Event]:
        # Best-effort: damage any opponent (caller may target a creature instead).
        opponent = next((p for p in state.players if p != obj.controller), None)
        if opponent is None:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': opponent, 'amount': 2, 'is_combat': False, 'is_player': True},
            source=obj.id,
        )]
    return [make_becomes_plotted_trigger(obj, becomes_plotted_effect)]


def magebane_lizard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a player casts a noncreature spell, deal damage equal to their noncreature count this turn."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        # Read the spell's types
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id) if spell_id else None
        types = set()
        if spell:
            types = spell.characteristics.types or set()
        else:
            types = set(event.payload.get('types', []) or [])
        if CardType.CREATURE in types:
            return []
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if caster is None:
            return []
        # engine gap: precise per-turn noncreature spell count not engine-tracked.
        # Use 1 damage as a conservative approximation.
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': caster, 'amount': 1, 'source': obj.id, 'is_combat': False},
            source=obj.id,
        )]
    return [make_spell_cast_trigger(obj, cast_effect, controller_only=False)]


def quilled_charger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 2; whenever this creature attacks while saddled, +1/+2 and menace until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 2, 'duration': 'end_of_turn'},
                source=obj.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'menace', 'duration': 'end_of_turn'},
                source=obj.id,
            ),
        ]
    return [make_saddle_trigger(obj, threshold=2, effect_fn=attack_effect)]


def reckless_lackey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{R}, Sacrifice this creature: Draw a card and create a Treasure token."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'count': 1},
                  source=o.id, controller=o.controller),
            Event(type=EventType.OBJECT_CREATED,
                  payload={
                      'name': 'Treasure',
                      'controller': o.controller,
                      'owner': o.controller,
                      'to_zone_type': ZoneType.BATTLEFIELD,
                      'types': {CardType.ARTIFACT},
                      'subtypes': {'Treasure'},
                      'colors': set(),
                      'is_token': True,
                  },
                  source=o.id, controller=o.controller),
        ]
    make_activated_ability(
        obj, cost="{2}{R}, Sacrifice this creature", effect_fn=_effect,
        description="Draw a card and create a Treasure token",
    )
    return []


def resilient_roadrunner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste, protection from Coyotes; {3}: conditional unblockable activated."""
    def conditional_unblockable(o: GameObject, st: GameState, targets) -> list[Event]:
        # engine gap: "can't be blocked this turn except by creatures with haste"
        # is not modeled. Register as a no-op effect for now so the ability is
        # discoverable and the cost is paid.
        return []
    make_activated_ability(
        obj, cost="{3}", effect_fn=conditional_unblockable,
        description="This creature can't be blocked this turn except by creatures with haste",
    )
    return []


def stingerback_terror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """-1/-1 for each card in your hand. (Plot is engine-gap.)"""
    from src.cards.interceptor_helpers import count_cards_in_hand
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def pt_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        n = count_cards_in_hand(obj.controller, st)
        return (-n, -n)

    return make_dynamic_pt_boost(obj, pt_mod, affects_self)


# -----------------------------------------------------------------------------
# GREEN MISSING SETUPS
# -----------------------------------------------------------------------------

def aloe_alchemist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample; when this card becomes plotted, target creature gets +3/+2 and gains trample
    until end of turn. Plot {1}{G}.
    (Best-effort: pump self if on battlefield, else first creature you control.)"""
    def becomes_plotted_effect(event: Event, state: GameState) -> list[Event]:
        # Find a creature to pump: prefer self if on battlefield, else any creature you control.
        target_id = None
        if obj.zone == ZoneType.BATTLEFIELD:
            target_id = obj.id
        else:
            for o in state.objects.values():
                if (o.controller == obj.controller and
                        o.zone == ZoneType.BATTLEFIELD and
                        CardType.CREATURE in o.characteristics.types):
                    target_id = o.id
                    break
        if target_id is None:
            return []
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': target_id, 'power_mod': 3, 'toughness_mod': 2, 'duration': 'end_of_turn'},
                source=obj.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': target_id, 'keyword': 'trample', 'duration': 'end_of_turn'},
                source=obj.id,
            ),
        ]
    return [make_becomes_plotted_trigger(obj, becomes_plotted_effect)]


def bristlepack_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender; conditional attack permission."""
    # engine gap: conditional attack-as-though-no-defender not engine-tracked
    return []


def bristly_bill_spine_sower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall: +1/+1 counter on target creature; activated counter doubling."""
    def land_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.id == source.id:
            return False
        if CardType.LAND not in target.characteristics.types:
            return False
        return target.controller == source.controller

    def land_etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target-selection on landfall; emit self-counter as fallback
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    return [make_etb_trigger(obj, land_etb_effect, land_etb_filter)]


def cactarantula_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: {1} less if you control a Desert. Reach granted via printed keyword.

    Skipped clauses:
      * 'Whenever this creature becomes the target of a spell or ability an
        opponent controls, you may draw a card.' (Engine gap: targeted-by-
        opponent trigger.)
    """
    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == controller
                    and "Desert" in o.characteristics.subtypes):
                return 1
        return 0

    return [make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                                amount=amount_fn, self_only=True)]


def colossal_rattlewurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Conditional flash; trample; activated graveyard-exile tutor."""
    # engine gap: conditional flash on battlefield. Trample wired via abilities list.
    return []


def colossal_rattlewurm_gy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{G}, Exile this card from your graveyard: Search your library for a
    Desert card, put it onto the battlefield tapped, then shuffle."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if o.zone != ZoneType.GRAVEYARD:
            return []
        return [
            Event(
                type=EventType.EXILE,
                payload={'object_id': o.id},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': o.controller,
                    'card_type': CardType.LAND,
                    'subtype': 'Desert',
                    'destination': 'battlefield_tapped',
                },
                source=o.id, controller=o.controller,
            ),
        ]
    make_activated_ability(
        obj,
        cost="{1}{G}",
        effect_fn=_effect,
        description="Exile from graveyard: Search library for a Desert, battlefield tapped",
    )
    return []


def drover_grizzly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddled-attack: creatures you control gain trample until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: saddle gating; emit team trample grant as best-effort
        events: list[Event] = []
        for o in state.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': o.id, 'keyword': 'trample', 'duration': 'end_of_turn'},
                    source=obj.id,
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


def freestrider_commando_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with two +1/+1 counters if it wasn't cast or no mana was spent
    (e.g. from plot). Plot {3}{G}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # If `plot_cast_used` is set, the card was cast for free via plot; place
        # the counters. The flag is set by cast_plotted_spell(); see
        # src/engine/plot_saddle.py.
        if not obj.state.plot_cast_used:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def freestrider_lookout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; whenever you commit a crime, may put a land from top 5.
    Simplification: surveil 1 (once/turn) since "reveal top N, may put a land
    onto the battlefield tapped" is not engine-modeled."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def giant_beaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 3; vigilance; saddled-attack puts +1/+1 counter on a creature that saddled it this turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Drop a counter on each creature that saddled this Mount this turn.
        events: list[Event] = []
        for sid in (obj.state.saddled_by_this_turn or []):
            if sid in state.objects:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': sid, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id,
                ))
        return events
    return [make_saddle_trigger(obj, threshold=3, effect_fn=attack_effect)]


def hardbristle_bandit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mana ability; crime -> untap (once/turn)."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.UNTAP,
            payload={'object_id': obj.id},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def intrepid_stablemaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; {T}: Add two mana of any one color. Spend this mana only to cast Mount or Vehicle spells."""
    def restricted_mana(o: GameObject, st: GameState, targets) -> list[Event]:
        # engine gap: spend-only-on-Mount/Vehicle restricted mana is not modeled.
        # Register the ability so it surfaces; the basic {T}: Add {G} mana ability
        # is handled by the card-factory mana parser.
        return []
    make_activated_ability(
        obj, cost="{T}", effect_fn=restricted_mana,
        description="Add two mana of any one color. Spend this mana only to cast Mount or Vehicle spells",
    )
    return []


def ornery_tumblewagg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of combat on your turn: +1/+1 counter on target creature.
    Saddle 2; whenever this attacks while saddled: double the number of
    +1/+1 counters on target creature (we approximate via a fresh batch of
    counters equal to its current +1/+1 counters).

    The card text wants "target creature" generically; we restrict to a
    creature you control to keep the prompt actionable in AI vs AI."""
    def beginning_of_combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START and event.payload.get('phase') not in ('combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller

    def open_counter_target(event: Event, state: GameState) -> InterceptorResult:
        legal_targets: list[str] = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)
        if not legal_targets:
            return InterceptorResult(action=InterceptorAction.PASS)

        def handle_counter(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': selected[0], 'counter_type': '+1/+1', 'amount': 1},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Ornery Tumblewagg: +1/+1 counter on target creature",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_counter
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    boc_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=beginning_of_combat_filter,
        handler=open_counter_target,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (open_counter_target(e, s).new_events or []),
    )

    def saddled_attack_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets: list[str] = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_double(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            target = gs.objects.get(tid)
            if not target:
                return []
            current = (target.state.counters or {}).get('+1/+1', 0)
            if current <= 0:
                return []
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': tid, 'counter_type': '+1/+1', 'amount': current},
                source=choice.source_id,
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Ornery Tumblewagg: double the number of +1/+1 counters on target creature",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_double
        return []

    set_saddle_threshold(obj.card_def, 2) if obj.card_def else None
    obj.state.saddle_threshold = 2
    return [boc_interceptor, make_saddle_trigger(obj, threshold=2, effect_fn=saddled_attack_effect)]


def rambling_possum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 1; saddled-attack: +1/+2 (the optional bounce of saddlers is left to player choice and not auto-wired)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 2, 'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_saddle_trigger(obj, threshold=1, effect_fn=attack_effect)]


def raucous_entertainer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn."""
    def counters_on_etb_creatures(o: GameObject, st: GameState, targets) -> list[Event]:
        # engine gap: per-turn ETB tracking is not engine-tracked. The ability
        # is registered and discoverable so the cost is paid; the conditional
        # counter-distribution is a no-op pending an entered-this-turn marker.
        return []
    make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=counters_on_etb_creatures,
        description="Put a +1/+1 counter on each creature you control that entered this turn",
    )
    return []


def reach_for_the_sky_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: +3/+2 reach; LTB draw."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]
    return [make_death_trigger(obj, death_effect)]


def spinewoods_armadillo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach (kw); Ward {3}; activated discard-tutor + life gain."""
    # engine gap: complex discard-cost activated tutor not engine-tracked.
    return [make_ward(obj, mana_cost="{3}")]


def stubborn_burrowfiend_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 2; whenever this creature becomes saddled for the first time each turn,
    mill two cards, then this creature gets +X/+X until end of turn, where X is the
    number of creature cards in your graveyard."""
    def becomes_saddled_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        )]
        # Count creature cards already in the GY (mill resolves separately).
        gy_key = f"graveyard_{obj.controller}"
        gy = state.zones.get(gy_key)
        x = 0
        if gy:
            for cid in gy.objects:
                co = state.objects.get(cid)
                if co and CardType.CREATURE in (co.characteristics.types or set()):
                    x += 1
        if x > 0:
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': x, 'toughness_mod': x, 'duration': 'end_of_turn'},
                source=obj.id,
            ))
        return events

    # Stash threshold so pay_saddle_cost() validates correctly.
    set_saddle_threshold(obj.card_def, 2) if obj.card_def else None
    obj.state.saddle_threshold = 2
    return [make_becomes_saddled_trigger(obj, becomes_saddled_effect, first_time_only=True)]


def voracious_varmint_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance (kw); {1}, Sacrifice this creature: Destroy target artifact or enchantment."""
    make_sac_destroy_ability(
        obj, cost="{1}, Sacrifice this creature",
        target_kind="artifact_or_enchantment",
        description="Destroy target artifact or enchantment",
    )
    return []


# -----------------------------------------------------------------------------
# MULTICOLOR / LEGENDARY MISSING SETUPS
# -----------------------------------------------------------------------------

def akul_the_unrepentant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, trample (kw); activated 3-sac put-creature-from-hand."""
    # engine gap: complex activated sacrifice ability not engine-tracked
    return []


def assimilation_aegis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment ETB exile; copy effect on attach."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment exile-until-leaves + copy-on-attach not engine-tracked
        return []
    return [make_etb_trigger(obj, etb_effect)]


def at_knifepoint_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Outlaws have first strike on your turn; crime -> Mercenary token (once/turn).
    Static "outlaws have first strike on your turn" not modeled; crime token wired."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Mercenary',
                'types': {CardType.CREATURE},
                'subtypes': {'Human', 'Mercenary'},
                'colors': {Color.RED},
                'power': 1, 'toughness': 1,
                'is_token': True,
            },
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def breeches_the_blastmaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace; second-spell-each-turn coin-flip copy/damage."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: 2nd-spell tracking + coin flip + spell copy not engine-tracked
        return []
    return [make_spell_cast_trigger(obj, cast_effect)]


def cactusfolk_sureshot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; ward {2}; combat-start trample/haste to power-4+ creatures."""
    def beginning_of_combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START and event.payload.get('phase') not in ('combat', 'beginning_of_combat'):
            return False
        return state.active_player == obj.controller

    def boost_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events: list[Event] = []
        for o in state.objects.values():
            if (o.id != obj.id and
                    o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                power = o.characteristics.power or 0
                if power >= 4:
                    new_events.append(Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={'object_id': o.id, 'keyword': 'trample', 'duration': 'end_of_turn'},
                        source=obj.id,
                    ))
                    new_events.append(Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={'object_id': o.id, 'keyword': 'haste', 'duration': 'end_of_turn'},
                        source=obj.id,
                    ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=beginning_of_combat_filter,
        handler=boost_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (boost_handler(e, s).new_events or []),
    )]


def congregation_gryff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saddle 3; flying, lifelink (kw); saddled-attack +X/+X where X is Mounts you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        x = 0
        for o in state.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    'Mount' in (o.characteristics.subtypes or set())):
                x += 1
        if x <= 0:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': x, 'toughness_mod': x, 'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_saddle_trigger(obj, threshold=3, effect_fn=attack_effect)]


def doc_aurlock_grizzled_genius_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spells you cast from your graveyard or from exile cost {2} less.

    Plot-cost reduction is engine-side (priority handler checks plot cost at
    cast time); we wire just the graveyard/exile zone-of-cast reduction here.
    """
    def applies(card: GameObject, pid: str, state: GameState) -> bool:
        if card is None or pid != obj.controller:
            return False
        return card.zone in (ZoneType.GRAVEYARD, ZoneType.EXILE)
    return [make_cost_reduction(obj, applies_to=applies, amount=2)]


def eriette_the_beguiler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink; aura-attach -> gain control while enchanted."""
    # engine gap: aura-attach trigger + control-conditional-on-attached not engine-tracked
    return []


def ghired_mirror_of_the_wilds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste (kw); grants nontoken creatures a tap-copy-token ability."""
    # engine gap: granting activated abilities to other creatures not engine-tracked
    return []


def the_gitrog_ravenous_ride_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample, haste (kw); combat-damage saddler-sac for X-cards-and-lands."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: saddler tracking + draw/lands-from-hand chain not engine-tracked
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def jolene_plundering_pugilist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack with one or more power-4+ creatures, create a Treasure."""
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        if attacker.controller != obj.controller:
            return False
        return (attacker.characteristics.power or 0) >= 4

    def make_treasure(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True,
            },
            source=obj.id,
        )]

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=make_treasure(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=make_treasure,
    )]


def kambal_profiteering_mayor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Token ETB triggers (mirror your opponent's; drain on yours)."""
    # engine gap: token-batch ETB triggers + token copy of opponent token not engine-tracked
    return []


def kellan_the_kid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, lifelink (kw); cast-from-not-hand may free-cast or play a land."""
    # engine gap: zone-of-cast trigger + free-cast permission not engine-tracked
    return []


def laughing_jasper_flint_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, exile the top X cards of target
    opponent's library, where X is the number of outlaws you control.

    Wired: upkeep trigger emitting EXILE_FROM_TOP from the first opponent.
    The "may cast those cards / mana of any type" cross-library cast
    permission and the static "creatures you don't own are also Mercenaries"
    type-override remain engine gaps."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        x = 0
        for o in state.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types and
                    is_outlaw(o)):
                x += 1
        if x <= 0:
            return []
        target_player = None
        for pid in state.players.keys():
            if pid != obj.controller:
                target_player = pid
                break
        if not target_player:
            return []
        return [Event(
            type=EventType.EXILE_FROM_TOP,
            payload={'player': target_player, 'amount': x},
            source=obj.id,
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def lazav_familiar_stranger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime -> +1/+1 counter on Lazav (once per turn).
    Skipped: optional graveyard-exile and copy-of-creature rider (engine gap)."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def lilah_undefeated_slickshot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Prowess; multicolored instant/sorcery -> exile and plot instead."""
    # engine gap: prowess + alternative-resolution exile-to-plot not engine-tracked
    return []


def marchesa_dealer_of_death_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime -> may pay {1} to scry-like draw.
    Simplification: skip the optional cost; just scry 1 on crime."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect)]


def obeka_splitter_of_seconds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace (kw); combat damage to player -> extra upkeeps."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: extra-upkeep insertion not engine-tracked
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def oko_the_ringleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of combat on your turn, Oko becomes a copy of up to
    one target creature you control until end of turn, except he has hexproof.

    The loyalty activated abilities (+1/-1/-5) remain an engine gap.
    """
    def combat_start_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START
                and event.payload.get('phase') == 'combat'
                and state.active_player == obj.controller)

    def combat_handler(event: Event, state: GameState):
        # Find legal targets: creatures Oko's controller controls.
        bf = state.zones.get('battlefield')
        legal: list[str] = []
        if bf is not None:
            for cid in bf.objects:
                cand = state.objects.get(cid)
                if cand is None:
                    continue
                if cand.controller != obj.controller:
                    continue
                if CardType.CREATURE not in cand.characteristics.types:
                    continue
                legal.append(cid)
        if not legal:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

        def handle_pick(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            chosen_id = selected[0]
            chosen = gs.objects.get(chosen_id)
            if chosen is None:
                return []
            becomes_copy_of(
                obj, chosen, gs,
                duration='end_of_turn',
                except_keywords=['hexproof'],
            )
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal,
            prompt="Oko: choose up to one target creature you control",
            min_targets=0,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_pick
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_start_filter,
        handler=combat_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (combat_handler(e, s).new_events or []),
    )]


def rakdos_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Rakdos Joins Up enters, return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.
    Legendary-dies damage trigger is left as an engine gap."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        gy_key = f"graveyard_{obj.controller}"
        gy = state.zones.get(gy_key)
        if not gy:
            return []
        legal_targets = []
        for cid in gy.objects:
            card = state.objects.get(cid)
            if card and CardType.CREATURE in card.characteristics.types:
                legal_targets.append(cid)
        if not legal_targets:
            return []

        def handle_reanimate(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            return [
                Event(
                    type=EventType.RETURN_FROM_GRAVEYARD,
                    payload={'object_id': tid, 'to': 'battlefield'},
                    source=choice.source_id,
                ),
                Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': tid, 'counter_type': '+1/+1', 'amount': 2},
                    source=choice.source_id,
                ),
            ]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Rakdos Joins Up: Return target creature card from your graveyard with two +1/+1 counters",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_reanimate
        return []
    return [make_etb_trigger(obj, etb_effect)]


def rakdos_the_muscle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice another creature, exile cards equal to its
    mana value from the top of target player's library.

    Wired: sacrifice REACT trigger -> EXILE_FROM_TOP from the first opposing
    player's library, count = the sacrificed creature's mana value
    (approximate: 1 per mana symbol, digits parsed as integers). The
    "may play those cards / mana of any type" cross-library cast permission
    is left as an engine gap. The activated indestructible-and-tap ability
    is also a separate engine gap (activated abilities)."""
    from src.engine.library_search import _mana_value as _mv

    def sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        if event.payload.get('object_id') == obj.id:
            return False
        sacrificed = state.objects.get(event.payload.get('object_id'))
        if not sacrificed:
            return False
        if sacrificed.controller != obj.controller:
            return False
        return CardType.CREATURE in sacrificed.characteristics.types

    def exile_effect(event: Event, state: GameState) -> list[Event]:
        sacrificed = state.objects.get(event.payload.get('object_id'))
        if not sacrificed:
            return []
        mv = _mv(sacrificed.characteristics.mana_cost or "")
        if mv <= 0:
            return []
        # Best-effort: pick first opponent.
        target_player = None
        for pid in state.players.keys():
            if pid != obj.controller:
                target_player = pid
                break
        if not target_player:
            return []
        return [Event(
            type=EventType.EXILE_FROM_TOP,
            payload={'player': target_player, 'amount': mv},
            source=obj.id,
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sacrifice_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=exile_effect(e, s)),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=exile_effect,
    )]


def riku_of_many_paths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a modal spell, choose up to X modes."""
    # engine gap: modal-spell mode count not engine-tracked
    return []


def roxanne_starfall_savant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Roxanne enters or attacks, create a tapped colorless artifact token named Meteorite with
    'When this token enters, it deals 2 damage to any target' and '{T}: Add one mana of any color.'
    The token's complex granted abilities are an engine gap; we still emit the token creation."""
    def make_meteorite(source_id: str) -> Event:
        return Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Meteorite',
                'types': {CardType.ARTIFACT},
                'subtypes': set(),
                'colors': set(),
                'is_token': True,
                'tapped': True,
            },
            source=source_id,
        )

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [make_meteorite(obj.id)]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [make_meteorite(obj.id)]

    return [make_etb_trigger(obj, etb_effect), make_attack_trigger(obj, attack_effect)]


def satoru_the_infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace (kw); ETB-batch where none were cast -> draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: detection of "wasn't cast or no mana was spent" not engine-tracked
        return []
    return [make_etb_trigger(obj, etb_effect)]


def seraphic_steed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike, lifelink (kw); saddled-attack -> 3/3 white Angel token with flying."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: saddle gating; emit token as best-effort
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Angel',
                'power': 3,
                'toughness': 3,
                'types': {CardType.CREATURE},
                'subtypes': {'Angel'},
                'colors': {Color.WHITE},
                'is_token': True,
                'keywords': ['flying'],
            },
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_effect)]


def taii_wakeen_perfect_shot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a source you control deals noncombat damage to a creature
    equal to that creature's toughness, draw a card.

    Wired: REACT-priority interceptor on DAMAGE; on each event we check
    source-controller, target is a creature on the battlefield, damage is
    noncombat, and amount equals the creature's toughness. The activated
    {X},{T} damage-scaling replacement remains an engine gap (no
    activated-ability harness yet)."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('is_combat', False):
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        damage_source_id = event.source or event.payload.get('source')
        damage_source = state.objects.get(damage_source_id) if damage_source_id else None
        if not damage_source or damage_source.controller != obj.controller:
            return False
        target_id = event.payload.get('target') or event.payload.get('target_id')
        target = state.objects.get(target_id) if target_id else None
        if not target:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        toughness = get_toughness(target, state)
        return amount == toughness

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=draw_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (draw_handler(e, s).new_events or []),
    )]


def vraska_the_silencer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch (kw); opponent-nontoken-creature-dies -> may pay {1} to steal as Treasure."""
    def opp_creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying = state.objects.get(event.payload.get('object_id'))
        if not dying:
            return False
        return (CardType.CREATURE in dying.characteristics.types and
                dying.controller != source.controller and
                not dying.state.is_token)

    def death_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional pay {1} + reanimate-as-treasure not engine-tracked
        return []

    return [make_death_trigger(obj, death_effect, opp_creature_dies_filter)]


def wylie_duke_atiin_hero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance (kw); becomes-tapped -> gain 1, draw 1."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
        ]

    def tap_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == obj.id)

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=tap_effect(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=tap_filter,
        handler=tap_handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=tap_effect,
    )]


# -----------------------------------------------------------------------------
# ARTIFACT MISSING SETUPS
# -----------------------------------------------------------------------------

def bandits_haul_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crime -> add a 'loot' counter on this artifact (once per turn).
    The {2}, {T}, remove-two-loot-counters: draw-a-card activated ability is
    a separate engine gap (activated abilities)."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'loot', 'amount': 1},
            source=obj.id,
        )]
    return [make_crime_committed_trigger(obj, crime_effect, once_per_turn=True)]


def boom_box_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{6}, {T}, Sacrifice this artifact: Destroy up to one target artifact, up to one target creature, and up to one target land."""
    def destroy_three_targets(o: GameObject, st: GameState, targets) -> list[Event]:
        # engine gap: framework only supports a single target_kind; the multi-mode
        # "up to one of each" pattern would need bespoke targeting. Best-effort:
        # destroy each chosen target if the harness manages to feed any in.
        events: list[Event] = []
        for t in targets or []:
            target_id = getattr(t, "object_id", None) or t
            if isinstance(target_id, str):
                events.append(Event(
                    type=EventType.DESTROY,
                    payload={'object_id': target_id},
                    source=o.id, controller=o.controller,
                ))
        return events
    make_activated_ability(
        obj, cost="{6}, {T}, Sacrifice this artifact",
        effect_fn=destroy_three_targets,
        description="Destroy up to one target artifact, up to one target creature, and up to one target land",
    )
    return []


def gold_pan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB Treasure; +1/+1 to equipped; equip {1}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True,
            },
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


lavaspur_boots_setup = make_equipment_setup(
    power_mod=1, toughness_mod=0, keywords=["haste"], equip_cost="{1}",
    ward_cost="{1}",
)


def luxurious_locomotive_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vehicle: attack creates Treasure per crewer; Crew 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: crewers-this-turn tracking; emit a single Treasure as best-effort
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True,
            },
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_effect)]


def mobile_homestead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vehicle: conditional haste; attack peeks for land."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: top-of-library reveal-and-may-play-land not engine-tracked
        return []
    return [make_attack_trigger(obj, attack_effect)]


def tomb_trawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}: Put target card from your graveyard on the bottom of your library."""
    def graveyard_to_bottom(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target = st.objects.get(target_id) if isinstance(target_id, str) else None
        if not target or target.zone != ZoneType.GRAVEYARD:
            return []
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone': f'library_{target.owner}',
                'to_zone_type': ZoneType.LIBRARY,
                'position': 'bottom',
            },
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{2}", effect_fn=graveyard_to_bottom,
        description="Put target card from your graveyard on the bottom of your library",
        targets_required=1, target_kind="graveyard_card",
    )
    return []


# -----------------------------------------------------------------------------
# LAND MISSING SETUPS (Cycle: ETB tapped + 1 damage to opponent + dual color)
# -----------------------------------------------------------------------------

def _ping_land_etb_effect(obj: GameObject, state: GameState) -> Callable[[Event, GameState], list[Event]]:
    """Build an ETB effect that deals 1 damage to an opponent (first found)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Pick the first opponent as a best-effort target.
        for pid in state.players.keys():
            if pid != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id,
                )]
        return []
    return etb_effect


def abraded_bluffs_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB-tapped Desert that pings an opponent for 1; taps for {R}/{W}."""
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def arid_archway_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this land enters, return a land you control to its owner's hand.
    If another Desert was returned this way, surveil 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.LAND in o.characteristics.types):
                legal_targets.append(oid)
        if not legal_targets:
            return []

        def handle_bounce(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            target = gs.objects.get(tid)
            events: list[Event] = [Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': tid},
                source=choice.source_id,
            )]
            if target and tid != obj.id and "Desert" in (target.characteristics.subtypes or set()):
                events.append(Event(
                    type=EventType.SURVEIL,
                    payload={'player': obj.controller, 'amount': 1},
                    source=choice.source_id,
                ))
            return events

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Arid Archway: Return a land you control to its owner's hand",
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_bounce
        return []
    return [make_etb_trigger(obj, etb_effect)]


def bristling_backwoods_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def conduit_pylons_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB surveil 1; mana abilities."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def creosote_heath_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def eroded_canyon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def festering_gulch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def forlorn_flats_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def jagged_barrens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def lonely_arroyo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def lush_oasis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def sandstorm_verge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mana ability + {3}, {T}: Target creature can't block this turn. Activate only as a sorcery."""
    def cant_block_target(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.CANT_BLOCK,
            payload={'object_id': target_id, 'duration': 'end_of_turn'},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{3}, {T}", effect_fn=cant_block_target,
        description="Target creature can't block this turn. Activate only as a sorcery.",
        sorcery_speed=True,
        targets_required=1, target_kind="creature",
    )
    return []


def soured_springs_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _ping_land_etb_effect(obj, state))]


def bucolic_ranch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mana abilities + {3}, {T}: Look at top card; if Mount, may put in hand or on bottom."""
    def peek_for_mount(o: GameObject, st: GameState, targets) -> list[Event]:
        # engine gap: conditional library-peek + may-reveal-and-put-into-hand for
        # a specific subtype is not modeled. Register a discoverable ability that
        # surveils as a best-effort approximation (look + sort top of library).
        return [Event(
            type=EventType.SCRY,
            payload={'player': o.controller, 'count': 1},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{3}, {T}", effect_fn=peek_for_mount,
        description="Look at the top card of your library. If it's a Mount card, you may reveal it and put it into your hand. If you don't put it into your hand, you may put it on the bottom of your library.",
    )
    return []


def blooming_marsh_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Conditional ETB tapped: tapped unless you control 2 or fewer other lands."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        other_lands = 0
        for o in state.objects.values():
            if (o.id != obj.id and
                    o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.LAND in o.characteristics.types):
                other_lands += 1
        if other_lands <= 2:
            return []  # enters untapped
        return [Event(
            type=EventType.TAP,
            payload={'object_id': obj.id},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def botanical_sanctum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return blooming_marsh_setup(obj, state)


def concealed_courtyard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return blooming_marsh_setup(obj, state)


def inspiring_vantage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return blooming_marsh_setup(obj, state)


def spirebluff_canal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return blooming_marsh_setup(obj, state)


# -----------------------------------------------------------------------------
# PLANESWALKER MISSING SETUPS
# -----------------------------------------------------------------------------

def jace_reawakened_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Planeswalker with cast-restriction and loyalty abilities."""
    # engine gap: planeswalker cast restriction + loyalty abilities not engine-tracked
    return []


# =============================================================================
# PHASE 2B VANILLA-SPELL RESOLVES
# =============================================================================

def _spell_caster_and_id(state: GameState, name: str) -> tuple[Optional[str], Optional[str]]:
    """Find the resolving spell on the stack by name. Returns (caster_id, spell_id)."""
    stack_zone = state.zones.get('stack')
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == name:
                return obj.controller, obj.id
    return state.active_player, None


# --- RUSTLER_RAMPAGE: Spree (untap creatures / double strike) ----------------

def rustler_rampage_resolve(targets: list, state: GameState) -> list[Event]:
    """Spree modal: untap all creatures target player controls, and/or grant double strike to target creature."""
    caster_id, spell_id = _spell_caster_and_id(state, "Rustler Rampage")
    spell_id = spell_id or "rustler_rampage_spell"

    # Always at least surface a target choice for "target creature gains double strike"
    valid_creatures = [
        obj.id for obj in state.objects.values()
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
    ]
    if not valid_creatures:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_creatures,
        prompt="Rustler Rampage: target creature gains double strike",
        min_targets=0,
        max_targets=1,
    )
    choice.choice_type = "target_with_callback"
    def _execute(choice, selected, state: GameState) -> list[Event]:
        events: list[Event] = []
        # Untap-all opponent creatures portion (auto-applied for active opponents).
        spell = state.objects.get(choice.source_id)
        ctrl = spell.controller if spell else state.active_player
        for obj in state.objects.values():
            if (obj.zone == ZoneType.BATTLEFIELD
                    and CardType.CREATURE in obj.characteristics.types
                    and obj.controller != ctrl):
                events.append(Event(
                    type=EventType.UNTAP,
                    payload={'object_id': obj.id},
                    source=choice.source_id,
                ))
        # Double strike grant
        if selected:
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': selected[0], 'keyword': 'double_strike', 'duration': 'end_of_turn'},
                source=choice.source_id,
            ))
        return events
    choice.callback_data['handler'] = _execute
    return []


# --- SEIZE_THE_SECRETS: Draw two cards (with crime cost reduction = engine gap)

def seize_the_secrets_resolve(targets: list, state: GameState) -> list[Event]:
    """Draw two cards. (Cost reduction handled at cast-time, not resolve.)"""
    caster_id, _ = _spell_caster_and_id(state, "Seize the Secrets")
    if not caster_id:
        return []
    return [Event(type=EventType.DRAW, payload={'player': caster_id, 'amount': 2})]


# --- STEP_BETWEEN_WORLDS: Each player may shuffle, then draw 7 ----------------

def step_between_worlds_resolve(targets: list, state: GameState) -> list[Event]:
    """Each player shuffles their hand and graveyard into their library, then draws seven cards.

    Auto-takes the option for each player (AI/test default). Exiling Step Between
    Worlds itself is handled by the engine via the spell going to the graveyard
    after resolution; we cannot easily redirect a sorcery to exile from the resolve
    without engine support, so we leave that as a minor deviation.
    """
    events: list[Event] = []
    for pid in state.players:
        graveyard = state.zones.get(f'graveyard_{pid}')
        hand = state.zones.get(f'hand_{pid}')
        # Shuffle each card from hand+graveyard back into the library.
        for zone in (hand, graveyard):
            if zone is None:
                continue
            for obj_id in list(zone.objects):
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': obj_id,
                        'to_zone': f'library_{pid}',
                        'to_zone_type': ZoneType.LIBRARY,
                    },
                ))
        events.append(Event(type=EventType.DRAW, payload={'player': pid, 'amount': 7}))
    return events


# --- CORRUPTED_CONVICTION: Draw two cards (sac is additional cost = engine gap)

def corrupted_conviction_resolve(targets: list, state: GameState) -> list[Event]:
    """Draw two cards. The sacrifice is an additional cost paid at cast time."""
    caster_id, _ = _spell_caster_and_id(state, "Corrupted Conviction")
    if not caster_id:
        return []
    return [Event(type=EventType.DRAW, payload={'player': caster_id, 'amount': 2})]


# --- FULL_STEAM_AHEAD: Pump all your creatures + trample/can't-be-double-blocked

def full_steam_ahead_resolve(targets: list, state: GameState) -> list[Event]:
    """Each creature you control gets +2/+2 and gains trample until end of turn."""
    caster_id, spell_id = _spell_caster_and_id(state, "Full Steam Ahead")
    spell_id = spell_id or "full_steam_ahead_spell"
    if not caster_id:
        return []
    events: list[Event] = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD
                and obj.controller == caster_id
                and CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': obj.id,
                    'power_mod': 2,
                    'toughness_mod': 2,
                    'duration': 'end_of_turn',
                },
                source=spell_id,
            ))
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'trample', 'duration': 'end_of_turn'},
                source=spell_id,
            ))
    return events


# --- MAP_THE_FRONTIER: Tutor up to two basic land/Desert cards ---------------

def map_the_frontier_resolve(targets: list, state: GameState) -> list[Event]:
    """Search your library for up to two basic land cards and/or Desert cards, BF tapped."""
    caster_id, spell_id = _spell_caster_and_id(state, "Map the Frontier")
    spell_id = spell_id or "map_the_frontier_spell"
    if not caster_id:
        return []

    def _land_filter(obj: GameObject, st: GameState) -> bool:
        ch = obj.characteristics
        is_basic = "Basic" in (ch.supertypes or set())
        is_desert = "Desert" in (ch.subtypes or set())
        return CardType.LAND in ch.types and (is_basic or is_desert)

    return open_library_search(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        filter_fn=_land_filter,
        max_count=2,
        destination='battlefield',
        tapped=True,
        prompt="Search your library for up to two basic land cards and/or Desert cards",
        optional=True,
    )


# --- RISE_OF_THE_VARMINTS: Create X 2/1 green Varmint tokens, X = creatures in GY

def rise_of_the_varmints_resolve(targets: list, state: GameState) -> list[Event]:
    """Create X 2/1 green Varmint tokens, where X is creature cards in your graveyard."""
    caster_id, spell_id = _spell_caster_and_id(state, "Rise of the Varmints")
    spell_id = spell_id or "rise_of_the_varmints_spell"
    if not caster_id:
        return []
    graveyard = state.zones.get(f'graveyard_{caster_id}')
    x = 0
    if graveyard:
        for obj_id in graveyard.objects:
            obj = state.objects.get(obj_id)
            if obj and CardType.CREATURE in obj.characteristics.types:
                x += 1

    events: list[Event] = []
    for _ in range(x):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Varmint Token',
                'controller': caster_id,
                'power': 2,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Varmint'],
                'colors': [Color.GREEN],
                'is_token': True,
            },
            source=spell_id,
            controller=caster_id,
        ))
    return events


# --- TUMBLEWEED_RISING: Create an X/X green Elemental, X = greatest power -----

def tumbleweed_rising_resolve(targets: list, state: GameState) -> list[Event]:
    """Create an X/X green Elemental token, X = greatest power among creatures you control."""
    caster_id, spell_id = _spell_caster_and_id(state, "Tumbleweed Rising")
    spell_id = spell_id or "tumbleweed_rising_spell"
    if not caster_id:
        return []
    x = 0
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD
                and obj.controller == caster_id
                and CardType.CREATURE in obj.characteristics.types):
            try:
                p = get_power(obj, state)
            except Exception:
                p = 0
            if p is not None and p > x:
                x = p
    return [Event(
        type=EventType.OBJECT_CREATED,
        payload={
            'name': 'Elemental Token',
            'controller': caster_id,
            'power': x,
            'toughness': x,
            'types': [CardType.CREATURE],
            'subtypes': ['Elemental'],
            'colors': [Color.GREEN],
            'is_token': True,
        },
        source=spell_id,
        controller=caster_id,
    )]


# --- PILLAGE_THE_BOG: Look at top 2*lands, put 1 into hand --------------------

def pillage_the_bog_resolve(targets: list, state: GameState) -> list[Event]:
    """Look at the top 2*L cards (L = lands you control), put 1 into hand, rest on bottom random."""
    caster_id, spell_id = _spell_caster_and_id(state, "Pillage the Bog")
    spell_id = spell_id or "pillage_the_bog_spell"
    if not caster_id:
        return []
    lands = sum(
        1 for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD
            and obj.controller == caster_id
            and CardType.LAND in obj.characteristics.types)
    )
    n = max(0, lands * 2)
    if n == 0:
        return []
    library = state.zones.get(f'library_{caster_id}')
    if library is None or not library.objects:
        return []
    # Look at top n; put one in hand, rest on bottom in random order.
    top_ids = list(library.objects[:n])
    if not top_ids:
        return []
    chosen = top_ids[0]  # AI/default: take the first card
    rest = top_ids[1:]
    import random as _random
    _random.shuffle(rest)
    events: list[Event] = []
    events.append(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': chosen,
            'to_zone': f'hand_{caster_id}',
            'to_zone_type': ZoneType.HAND,
        },
        source=spell_id,
    ))
    for r_id in rest:
        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': r_id,
                'to_zone': f'library_{caster_id}',
                'to_zone_type': ZoneType.LIBRARY,
                'position': 'bottom',
            },
            source=spell_id,
        ))
    return events


# =============================================================================
# PHASE 5B FINAL BATCH: SPREE MIGRATIONS (cost-per-mode wired)
# =============================================================================
# Migrated from bespoke modal-with-callback resolves to the SpreeMode
# pattern. Each effect_fn has the canonical
# ``(spell, state, targets) -> list[Event]`` signature.
# Where a mode requires engine capability we can't yet express (control
# exchange, "owner chooses top/bottom of library", delayed triggers,
# "may put creature card from hand to battlefield", etc.) the effect_fn
# emits what it can and leaves a comment explaining the remaining gap.

# --- GETAWAY_GLAMER -----------------------------------------------------------

def _getaway_glamer_flicker(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: exile nontoken creature, return at next end step."""
    if not spell or not targets:
        return []
    target_id = targets[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if target.is_token:
        return []
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'to_zone': 'exile',
            'to_zone_type': ZoneType.EXILE,
            'reason': 'flickered',
            'return_at_end_step': True,
            'return_owner': target.owner,
        },
        source=spell.id,
    )]


def _getaway_glamer_destroy_if_smallest(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: destroy target creature if no other creature has greater power."""
    if not spell or not targets:
        return []
    target_id = targets[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    target_power = get_power(target, state) or 0
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and obj.id != target_id
                and CardType.CREATURE in obj.characteristics.types):
            if (get_power(obj, state) or 0) > target_power:
                return []  # spell fizzles - another creature has greater power
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=spell.id,
    )]


_GETAWAY_GLAMER_MODES = [
    SpreeMode(
        name="Flicker", extra_cost="{1}",
        effect_fn=_getaway_glamer_flicker, target_kind="creature",
        targets_required=1,
        description="Exile target nontoken creature. Return it at the beginning of the next end step.",
        legal_targets_filter=lambda spell, state: [
            obj.id for obj in state.objects.values()
            if obj.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in obj.characteristics.types
            and not obj.is_token
        ],
    ),
    SpreeMode(
        name="Conditional destroy", extra_cost="{2}",
        effect_fn=_getaway_glamer_destroy_if_smallest, target_kind="creature",
        targets_required=1,
        description="Destroy target creature if no other creature has greater power.",
    ),
]


# --- ONE_LAST_JOB -------------------------------------------------------------

def _one_last_job_creature_mv(state: GameState, obj_id: str) -> int:
    """Compute mana value of a graveyard card (used by Lively Dirge too)."""
    obj = state.objects.get(obj_id)
    if obj is None:
        return 0
    try:
        from src.engine.mana import ManaCost
        return ManaCost.parse(obj.characteristics.mana_cost or '').mana_value
    except Exception:
        return 0


def _one_last_job_reanimate_creature(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: reanimate target creature card from your graveyard."""
    if not spell or not targets:
        return []
    target = state.objects.get(targets[0])
    if target is None:
        return []
    owner = target.owner or target.controller
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target.id,
            'to_zone': f'battlefield_{owner}',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=spell.id,
    )]


def _one_last_job_reanimate_mount_vehicle(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: reanimate target Mount or Vehicle card from your graveyard."""
    return _one_last_job_reanimate_creature(spell, state, targets)


def _one_last_job_reanimate_aura_equipment(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: reanimate target Aura or Equipment card.

    NOTE: "Attached to a creature you control" requires picking the attachment
    target; we surface only the reanimation. Aura/Equipment without attachment
    just enters and falls off, which is engine-faithful for the simpler case.
    """
    return _one_last_job_reanimate_creature(spell, state, targets)


def _one_last_job_legal_creatures(spell, state):
    """Creature cards in the caster's graveyard."""
    caster = spell.controller
    gy = state.zones.get(f'graveyard_{caster}')
    if gy is None:
        return []
    return [
        oid for oid in gy.objects
        if (obj := state.objects.get(oid)) is not None
        and CardType.CREATURE in obj.characteristics.types
    ]


def _one_last_job_legal_mounts_vehicles(spell, state):
    caster = spell.controller
    gy = state.zones.get(f'graveyard_{caster}')
    if gy is None:
        return []
    out: list[str] = []
    for oid in gy.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        subs = obj.characteristics.subtypes or set()
        if 'Mount' in subs or 'Vehicle' in subs:
            out.append(oid)
    return out


def _one_last_job_legal_aura_equipment(spell, state):
    caster = spell.controller
    gy = state.zones.get(f'graveyard_{caster}')
    if gy is None:
        return []
    out: list[str] = []
    for oid in gy.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        subs = obj.characteristics.subtypes or set()
        types = obj.characteristics.types
        if 'Aura' in subs or 'Equipment' in subs or CardType.ENCHANTMENT in types:
            out.append(oid)
    return out


_ONE_LAST_JOB_MODES = [
    SpreeMode(
        name="Reanimate creature", extra_cost="{2}",
        effect_fn=_one_last_job_reanimate_creature, target_kind="creature_in_your_graveyard",
        targets_required=1,
        description="Return target creature card from your graveyard to the battlefield.",
        legal_targets_filter=_one_last_job_legal_creatures,
    ),
    SpreeMode(
        name="Reanimate Mount/Vehicle", extra_cost="{1}",
        effect_fn=_one_last_job_reanimate_mount_vehicle, target_kind="creature_in_your_graveyard",
        targets_required=1,
        description="Return target Mount or Vehicle card from your graveyard to the battlefield.",
        legal_targets_filter=_one_last_job_legal_mounts_vehicles,
    ),
    SpreeMode(
        name="Reanimate Aura/Equipment", extra_cost="{1}",
        effect_fn=_one_last_job_reanimate_aura_equipment, target_kind="creature_in_your_graveyard",
        targets_required=1,
        description="Return target Aura or Equipment card from your graveyard to the battlefield.",
        legal_targets_filter=_one_last_job_legal_aura_equipment,
    ),
]


# --- PHANTOM_INTERFERENCE -----------------------------------------------------

def _phantom_interference_spirit(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: create a 2/2 white Spirit token with flying."""
    if not spell:
        return []
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': spell.controller,
            'name': 'Spirit',
            'power': 2,
            'toughness': 2,
            'types': {CardType.CREATURE},
            'subtypes': {'Spirit'},
            'colors': {Color.WHITE},
            'abilities': ['flying'],
            'is_token': True,
        },
        source=spell.id,
    )]


def _phantom_interference_counter(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: counter target spell unless its controller pays {2}.

    Engine simplification: emit COUNTER_SPELL_UNLESS_PAY; the engine's
    counter-spell glue will handle the cost prompt.
    """
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.COUNTER_SPELL_UNLESS_PAY,
        payload={
            'spell_id': targets[0],
            'amount': 2,
        },
        source=spell.id,
    )]


def _phantom_interference_legal_spells(spell, state):
    """Other spells on the stack."""
    stack_zone = state.zones.get('stack')
    if not stack_zone:
        return []
    return [
        oid for oid in stack_zone.objects
        if oid != spell.id and state.objects.get(oid) is not None
    ]


_PHANTOM_INTERFERENCE_MODES = [
    SpreeMode(
        name="Spirit token", extra_cost="{3}",
        effect_fn=_phantom_interference_spirit,
        description="Create a 2/2 white Spirit creature token with flying.",
    ),
    SpreeMode(
        name="Counter unless pay", extra_cost="{1}",
        effect_fn=_phantom_interference_counter, target_kind="spell",
        targets_required=1,
        description="Counter target spell unless its controller pays {2}.",
        legal_targets_filter=_phantom_interference_legal_spells,
    ),
]


# --- SHIFTING_GRIFT -----------------------------------------------------------
# Printed text (OTJ): "Each player chooses a permanent they control. Exchange
# control of those permanents." Wired with chained PendingChoices in Agent K
# Phase 5b — caster picks first, then a chained handler opens an opponent
# choice; the second handler emits two GAIN_CONTROL events to swap.

def _shifting_grift_collect_permanents(state: GameState, player_id: str) -> list[str]:
    out: list[str] = []
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller != player_id:
            continue
        out.append(obj.id)
    return out


def shifting_grift_resolve(targets, state: GameState) -> list[Event]:
    """Resolve Shifting Grift.

    Each player chooses a permanent they control; control of those permanents
    is then exchanged. Caster picks first via a PendingChoice; the chained
    handler opens an opponent PendingChoice; the final handler emits two
    GAIN_CONTROL events (one each direction) with duration='permanent' so
    the swap is durable.
    """
    spell = _otj_resolving_spell_obj(state)
    if spell is None:
        return []
    caster = spell.controller
    source_id = spell.id

    opponents = [pid for pid in state.players if pid != caster]
    if not opponents:
        return []

    caster_perms = _shifting_grift_collect_permanents(state, caster)
    if not caster_perms:
        return []

    # If multiple opponents, pick the one with the most permanents (greedy
    # "best target" heuristic). Treat absence of opponents with any permanent
    # as a graceful no-op.
    eligible_opps = [
        pid for pid in opponents
        if _shifting_grift_collect_permanents(state, pid)
    ]
    if not eligible_opps:
        return []
    eligible_opps.sort(
        key=lambda pid: -len(_shifting_grift_collect_permanents(state, pid))
    )
    opp = eligible_opps[0]

    caster_options = [
        {"id": cid, "label": (state.objects.get(cid).name if state.objects.get(cid) else cid)}
        for cid in caster_perms
    ]

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    def _on_caster_pick(choice, caster_selected, _state, _src=source_id, _caster=caster,
                       _opp=opp):
        caster_pick_id = None
        for raw in caster_selected or []:
            if isinstance(raw, dict):
                caster_pick_id = raw.get("id") or raw.get("value")
            else:
                caster_pick_id = raw
            if caster_pick_id is not None:
                break
        if caster_pick_id is None:
            return []
        # Refresh the opponent's permanents (board state may have changed
        # between the caster's pick and now, e.g. SBA-driven deaths).
        opp_perms = _shifting_grift_collect_permanents(_state, _opp)
        if not opp_perms:
            return []
        opp_options = [
            {"id": cid, "label": (_state.objects.get(cid).name if _state.objects.get(cid) else cid)}
            for cid in opp_perms
        ]

        def _on_opp_pick(_choice2, opp_selected, _state2, _cpick=caster_pick_id,
                         _c=_caster, _o=_opp, _src2=_src):
            opp_pick_id = None
            for raw in opp_selected or []:
                if isinstance(raw, dict):
                    opp_pick_id = raw.get("id") or raw.get("value")
                else:
                    opp_pick_id = raw
                if opp_pick_id is not None:
                    break
            if opp_pick_id is None:
                return []
            # Re-validate that both permanents are still on the battlefield.
            cobj = _state2.objects.get(_cpick)
            oobj = _state2.objects.get(opp_pick_id)
            if cobj is None or oobj is None:
                return []
            if cobj.zone != ZoneType.BATTLEFIELD or oobj.zone != ZoneType.BATTLEFIELD:
                return []
            return [
                Event(
                    type=EventType.GAIN_CONTROL,
                    payload={
                        'object_id': _cpick,
                        'new_controller': _o,
                        'duration': 'permanent',
                    },
                    source=_src2,
                ),
                Event(
                    type=EventType.GAIN_CONTROL,
                    payload={
                        'object_id': opp_pick_id,
                        'new_controller': _c,
                        'duration': 'permanent',
                    },
                    source=_src2,
                ),
            ]

        # Opponent's heuristic pick: their cheapest permanent (don't give the
        # caster a free upgrade). Sort by mana value, ascending.
        def _opp_value(pid):
            o = _state.objects.get(pid)
            if o is None:
                return (0, "")
            try:
                mv = (o.characteristics.mana_cost.total()
                      if o.characteristics.mana_cost else 0)
            except Exception:
                mv = 0
            return (mv, o.name or pid)
        opp_heuristic = sorted(opp_perms, key=_opp_value)[:1]

        return create_choice_and_resolve(
            _state,
            choice_type="shifting_grift_opp_pick",
            player_id=_opp,
            prompt="Shifting Grift — choose a permanent you control to give up",
            options=opp_options,
            source_id=_src,
            min_choices=1,
            max_choices=1,
            handler=_on_opp_pick,
            heuristic_pick=opp_heuristic,
        )

    # Caster's heuristic pick: the most valuable permanent (give us their best).
    # Sort by mana value, descending; tie-break on power+toughness, then name.
    def _caster_value(cid):
        o = state.objects.get(cid)
        if o is None:
            return (0, 0, "")
        try:
            mv = (o.characteristics.mana_cost.total()
                  if o.characteristics.mana_cost else 0)
        except Exception:
            mv = 0
        pt = (o.characteristics.power or 0) + (o.characteristics.toughness or 0)
        return (-mv, -pt, o.name or cid)
    caster_heuristic = sorted(caster_perms, key=_caster_value)[:1]

    return create_choice_and_resolve(
        state,
        choice_type="shifting_grift_caster_pick",
        player_id=caster,
        prompt="Shifting Grift — choose a permanent you control to give up",
        options=caster_options,
        source_id=source_id,
        min_choices=1,
        max_choices=1,
        handler=_on_caster_pick,
        heuristic_pick=caster_heuristic,
    )


# --- THREE_STEPS_AHEAD --------------------------------------------------------

def _three_steps_ahead_pump(spell, state: GameState, targets) -> list[Event]:
    """Mode 0 (+{1}): until end of turn, target creature you control gets +1/+1
    and has flash, hexproof, and ward {2}.

    Phase 5b: ``targets`` is the engine's chosen-target id list for this
    Spree mode (one target, count=1). We emit:
      - PT_MODIFICATION +1/+1 EOT
      - GRANT_KEYWORD flash EOT
      - GRANT_KEYWORD hexproof EOT
      - GRANT_KEYWORD ward EOT  (ward cost is not parameterised by GRANT_KEYWORD;
        the keyword grant is the closest engine-supported handle today —
        see ``engine_gaps.md`` for the punch list)
    """
    if not spell or not targets:
        return []
    target_id = targets[0]
    if not target_id:
        return []
    return [
        Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target_id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
            source=spell.id,
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'flash', 'duration': 'end_of_turn'},
            source=spell.id,
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'},
            source=spell.id,
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'ward', 'duration': 'end_of_turn'},
            source=spell.id,
        ),
    ]


def _three_steps_ahead_draw_three(spell, state: GameState, targets) -> list[Event]:
    """Mode 1 (+{2}): draw three cards."""
    if not spell:
        return []
    return [
        Event(type=EventType.DRAW,
              payload={'player': spell.controller, 'amount': 3},
              source=spell.id),
    ]


def _three_steps_ahead_copy_this_spell(spell, state: GameState, targets) -> list[Event]:
    """Mode 2 (+{3}): create a copy of this spell. You may choose new targets
    for the copy.

    Per CR 706, the copy preserves the original's chosen targets / modes /
    resolve_fn. Implementation note: by the time a Spree mode's effect_fn
    fires, ``StackManager.resolve_top`` has already popped the spell's
    ``StackItem``, so we can't look it up via ``stack.get_item`` and emit
    ``COPY_STACK_ITEM`` for the engine to handle. Instead we mint a fresh
    ``StackItem`` mirroring the resolving spell (same card_id /
    controller_id / resolve_fn) marked ``is_copy=True`` and push it
    directly. The copy resolves like any other stack item and won't move
    the spell card to the graveyard (CR 706.10b — copies cease to exist).

    NOTE (follow-up): the printed text allows the caster to choose new
    targets for the copy. v1 keeps the original spell's targets. A future
    enhancement should prompt the caster via a chained
    ``target_with_callback`` PendingChoice — see
    ``_virtue_of_knowledge_adventure`` in ``wilds_of_eldraine.py`` for the
    canonical "may choose new targets" retarget walker.
    """
    if not spell:
        return []
    game = getattr(state, '_game', None)
    stack = getattr(game, 'stack', None) if game else None
    if stack is None:
        return []

    # Mint a fresh StackItem matching the resolving spell. The original
    # is already popped from the stack (StackManager.resolve_top pops
    # before invoking resolve_fn), so we rebuild from the spell GameObject
    # and the card_def. The copy is flagged ``is_copy=True`` so the engine
    # skips the "move spell to graveyard" branch on resolution.
    from src.engine.stack import StackItem, StackItemType
    card_def = getattr(spell, 'card_def', None)
    resolve_fn = getattr(card_def, 'resolve', None)
    copy_item = StackItem(
        id="",  # StackManager.push assigns a fresh id
        type=StackItemType.SPELL,
        source_id=spell.id,
        controller_id=spell.controller,
        card_id=spell.id,
        resolve_fn=resolve_fn,
        chosen_targets=[],  # v1 — see follow-up note above
        chosen_modes=[],
        is_copy=True,
    )
    stack.push(copy_item)

    # Return no follow-up events. We don't emit COPY_STACK_ITEM here because:
    #   1. The original StackItem is already popped, so the engine's handler
    #      (which calls ``stack.push_copy(stack_item_id)``) couldn't find it.
    #   2. Passing the freshly-pushed ``copy_item.id`` would cause the handler
    #      to push *another* copy on top of our manual push (double-copy bug).
    # The manual ``stack.push(copy_item)`` above is sufficient — the copy is
    # on the stack and will resolve normally.
    return []


def _three_steps_ahead_legal_your_creature(spell, state):
    """Creatures the caster controls — for the +1/+1 pump mode."""
    return [
        obj.id for obj in state.objects.values()
        if obj.zone == ZoneType.BATTLEFIELD
        and obj.controller == spell.controller
        and CardType.CREATURE in obj.characteristics.types
    ]


_THREE_STEPS_AHEAD_MODES = [
    SpreeMode(
        name="Pump your creature", extra_cost="{1}",
        effect_fn=_three_steps_ahead_pump, target_kind="your_creature",
        targets_required=1,
        description=("Until end of turn, target creature you control gets +1/+1 "
                     "and has flash, hexproof, and ward {2}."),
        legal_targets_filter=_three_steps_ahead_legal_your_creature,
    ),
    SpreeMode(
        name="Draw three", extra_cost="{2}",
        effect_fn=_three_steps_ahead_draw_three,
        description="Draw three cards.",
    ),
    SpreeMode(
        name="Copy this spell", extra_cost="{3}",
        effect_fn=_three_steps_ahead_copy_this_spell,
        description=("Create a copy of this spell. You may choose new targets "
                     "for the copy."),
    ),
]


# --- INSATIABLE_AVARICE -------------------------------------------------------

def _insatiable_avarice_tutor(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: search your library for a card; shuffle, put on top."""
    if not spell:
        return []
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': spell.controller,
            'destination': 'library_top',
        },
        source=spell.id,
    )]


def _insatiable_avarice_draw_loss(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: target player draws three cards and loses 3 life."""
    if not spell or not targets:
        return []
    pid = targets[0]
    if pid not in state.players:
        return []
    return [
        Event(type=EventType.DRAW,
              payload={'player': pid, 'amount': 3},
              source=spell.id),
        Event(type=EventType.LIFE_CHANGE,
              payload={'player': pid, 'amount': -3},
              source=spell.id),
    ]


_INSATIABLE_AVARICE_MODES = [
    SpreeMode(
        name="Tutor to top", extra_cost="{2}",
        effect_fn=_insatiable_avarice_tutor,
        description="Search your library for a card, shuffle, then put that card on top.",
    ),
    SpreeMode(
        name="Player draws 3, loses 3", extra_cost="{B}{B}",
        effect_fn=_insatiable_avarice_draw_loss, target_kind="player",
        targets_required=1,
        description="Target player draws three cards and loses 3 life.",
    ),
]


# --- LIVELY_DIRGE -------------------------------------------------------------

def _lively_dirge_tutor_to_graveyard(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: search library for a card and put it into your graveyard, then shuffle."""
    if not spell:
        return []
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': spell.controller,
            'destination': 'graveyard',
        },
        source=spell.id,
    )]


def _lively_dirge_reanimate(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: return up to two creature cards w/ total MV<=4 from graveyard to battlefield."""
    if not spell or not targets:
        return []
    events: list[Event] = []
    total_mv = 0
    for tid in targets:
        obj = state.objects.get(tid)
        if obj is None:
            continue
        mv = _one_last_job_creature_mv(state, tid)
        if total_mv + mv > 4:
            break
        total_mv += mv
        owner = obj.owner or obj.controller
        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': tid,
                'to_zone': f'battlefield_{owner}',
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=spell.id,
        ))
    return events


def _lively_dirge_legal_creatures_mv4(spell, state):
    """Creatures in caster's graveyard with MV<=4."""
    caster = spell.controller
    gy = state.zones.get(f'graveyard_{caster}')
    if gy is None:
        return []
    out: list[str] = []
    for oid in gy.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        if _one_last_job_creature_mv(state, oid) <= 4:
            out.append(oid)
    return out


_LIVELY_DIRGE_MODES = [
    SpreeMode(
        name="Tutor to graveyard", extra_cost="{1}",
        effect_fn=_lively_dirge_tutor_to_graveyard,
        description="Search your library for a card, put it into your graveyard, then shuffle.",
    ),
    SpreeMode(
        name="Reanimate up to two", extra_cost="{2}",
        effect_fn=_lively_dirge_reanimate, target_kind="creature_in_your_graveyard",
        targets_required=2,
        description="Return up to two creature cards with total mana value 4 or less from your graveyard to the battlefield.",
        legal_targets_filter=_lively_dirge_legal_creatures_mv4,
    ),
]


# --- RUSH_OF_DREAD ------------------------------------------------------------
# Mode 0 (sacrifice half) and Mode 1 (discard half) open a PendingChoice owned
# by the targeted opponent (Agent K, Phase 5b). Mode 2 (lose half life) is
# unconditional.

def _rush_of_dread_resolve_target_opponent(targets, state: GameState) -> Optional[str]:
    """Normalize the first target to an opponent player id (or None)."""
    if not targets:
        return None
    first = targets[0]
    pid, is_player = normalize_target(first, state)
    if pid is None or not is_player:
        return None
    if pid not in state.players:
        return None
    return pid


def _rush_of_dread_sacrifice_half(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: target opponent sacrifices half their creatures, rounded up.

    Opens a PendingChoice owned by the targeted opponent so that player picks
    which of their creatures to sacrifice. Handler emits ``OBJECT_DESTROYED``
    events tagged ``reason='sacrifice'`` for each chosen creature.
    """
    if not spell:
        return []
    opp = _rush_of_dread_resolve_target_opponent(targets, state)
    if opp is None:
        return []

    creatures: list[str] = []
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller != opp:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        creatures.append(obj.id)
    n = len(creatures)
    if n == 0:
        return []
    pick_count = (n + 1) // 2  # ceil(n/2)

    options = []
    for cid in creatures:
        c_obj = state.objects.get(cid)
        options.append({"id": cid, "label": (c_obj.name if c_obj else cid)})

    source_id = spell.id

    def _handler(choice, selected, _state, _src=source_id, _opts=list(creatures)):
        picked_ids: list[str] = []
        for raw in selected or []:
            if isinstance(raw, dict):
                pid_v = raw.get("id") or raw.get("value")
            else:
                pid_v = raw
            if pid_v in _opts and pid_v not in picked_ids:
                picked_ids.append(pid_v)
        return [
            Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': cid, 'reason': 'sacrifice'},
                source=_src,
            )
            for cid in picked_ids
        ]

    # Heuristic: opponent picks the creatures with the lowest power/toughness
    # (i.e. the least valuable). Stable sort by (power+toughness, name).
    def _value(cid):
        o = state.objects.get(cid)
        if o is None:
            return (0, "")
        p = o.characteristics.power or 0
        t = o.characteristics.toughness or 0
        return (p + t, o.name or cid)

    heuristic = sorted(creatures, key=_value)[:pick_count]

    from src.engine.pending_choice_helpers import create_choice_and_resolve
    return create_choice_and_resolve(
        state,
        choice_type="rush_of_dread_sacrifice",
        player_id=opp,
        prompt=f"Rush of Dread — sacrifice {pick_count} creature(s) you control",
        options=options,
        source_id=source_id,
        min_choices=pick_count,
        max_choices=pick_count,
        handler=_handler,
        heuristic_pick=heuristic,
    )


def _rush_of_dread_discard_half(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: target opponent discards half their hand, rounded up.

    Opens a PendingChoice owned by the targeted opponent so that player picks
    which cards in hand to discard. Handler emits ``DISCARD`` events targeting
    each chosen card. Falls back to a count-only ``DISCARD`` event if no cards
    are present.
    """
    if not spell:
        return []
    opp = _rush_of_dread_resolve_target_opponent(targets, state)
    if opp is None:
        return []

    hand_key = f"hand_{opp}"
    hand = state.zones.get(hand_key)
    cards = list(hand.objects) if hand else []
    n = len(cards)
    if n == 0:
        return []
    pick_count = (n + 1) // 2  # ceil(n/2)

    options = []
    for cid in cards:
        c_obj = state.objects.get(cid)
        options.append({"id": cid, "label": (c_obj.name if c_obj else cid)})

    source_id = spell.id

    def _handler(choice, selected, _state, _src=source_id, _opts=list(cards), _pid=opp):
        picked_ids: list[str] = []
        for raw in selected or []:
            if isinstance(raw, dict):
                cid_v = raw.get("id") or raw.get("value")
            else:
                cid_v = raw
            if cid_v in _opts and cid_v not in picked_ids:
                picked_ids.append(cid_v)
        return [
            Event(
                type=EventType.DISCARD,
                payload={'player': _pid, 'card_id': cid},
                source=_src,
            )
            for cid in picked_ids
        ]

    # Heuristic: opponent dumps highest-MV cards (most expensive in hand).
    def _value(cid):
        o = state.objects.get(cid)
        if o is None:
            return (0, "")
        mv = 0
        try:
            mv = (o.characteristics.mana_cost.total() if o.characteristics.mana_cost else 0)
        except Exception:
            mv = 0
        # Sort descending by MV (so multiply by -1 for ascending sort).
        return (-mv, o.name or cid)

    heuristic = sorted(cards, key=_value)[:pick_count]

    from src.engine.pending_choice_helpers import create_choice_and_resolve
    return create_choice_and_resolve(
        state,
        choice_type="rush_of_dread_discard",
        player_id=opp,
        prompt=f"Rush of Dread — discard {pick_count} card(s) from your hand",
        options=options,
        source_id=source_id,
        min_choices=pick_count,
        max_choices=pick_count,
        handler=_handler,
        heuristic_pick=heuristic,
    )


def _rush_of_dread_lose_half_life(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: target opponent loses half their life, rounded up."""
    if not spell or not targets:
        return []
    opp = _rush_of_dread_resolve_target_opponent(targets, state)
    if opp is None:
        # Back-compat: the original handler accepted a raw player id.
        first = targets[0]
        if isinstance(first, str) and first in state.players:
            opp = first
        else:
            return []
    player = state.players.get(opp)
    if player is None:
        return []
    life = getattr(player, 'life', 20)
    loss = (life + 1) // 2
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': opp, 'amount': -loss},
        source=spell.id,
    )]


_RUSH_OF_DREAD_MODES = [
    SpreeMode(
        name="Sacrifice half", extra_cost="{1}",
        effect_fn=_rush_of_dread_sacrifice_half, target_kind="opponent",
        targets_required=1,
        description="Target opponent sacrifices half the creatures they control, rounded up.",
    ),
    SpreeMode(
        name="Discard half", extra_cost="{2}",
        effect_fn=_rush_of_dread_discard_half, target_kind="opponent",
        targets_required=1,
        description="Target opponent discards half the cards in their hand, rounded up.",
    ),
    SpreeMode(
        name="Lose half life", extra_cost="{2}",
        effect_fn=_rush_of_dread_lose_half_life, target_kind="opponent",
        targets_required=1,
        description="Target opponent loses half their life, rounded up.",
    ),
]


# --- GREAT_TRAIN_HEIST --------------------------------------------------------
# Mode 0: extra-combat-phase is an engine gap; we still untap creatures.
# Mode 2: delayed Treasure trigger is an engine gap.

def _great_train_heist_untap(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: untap all creatures you control. Extra combat phase is engine gap."""
    if not spell:
        return []
    events: list[Event] = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and obj.controller == spell.controller
                and CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.UNTAP,
                payload={'object_id': obj.id},
                source=spell.id,
            ))
    return events


def _great_train_heist_anthem(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: creatures you control get +1/+0 and gain first strike EOT."""
    if not spell:
        return []
    events: list[Event] = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and obj.controller == spell.controller
                and CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0,
                         'duration': 'end_of_turn'},
                source=spell.id,
            ))
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'first_strike',
                         'duration': 'end_of_turn'},
                source=spell.id,
            ))
    return events


def _great_train_heist_treasure_trigger(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: choose target opponent; delayed treasure trigger is engine gap."""
    return []


_GREAT_TRAIN_HEIST_MODES = [
    SpreeMode(
        name="Untap creatures", extra_cost="{2}{R}",
        effect_fn=_great_train_heist_untap,
        description="Untap all creatures you control. (extra combat phase is engine gap)",
    ),
    SpreeMode(
        name="+1/+0 first strike", extra_cost="{2}",
        effect_fn=_great_train_heist_anthem,
        description="Creatures you control get +1/+0 and gain first strike until end of turn.",
    ),
    SpreeMode(
        name="Treasure trigger", extra_cost="{R}",
        effect_fn=_great_train_heist_treasure_trigger, target_kind="opponent",
        targets_required=1,
        description="Choose target opponent. (delayed Treasure trigger is engine gap)",
    ),
]


# --- RETURN_THE_FAVOR ---------------------------------------------------------
# Phase 5b regular-instant migration: target an opponent's instant or sorcery
# spell on the stack and copy it via COPY_STACK_ITEM.

def return_the_favor_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Return the Favor: copy target instant/sorcery spell you don't
    control via ``COPY_STACK_ITEM``.

    Phase 5b: ``targets`` is the engine's chosen-target shape
    (``list[list[Target]]`` — one inner list per ``target_requirements``
    entry). The first chosen target is the opposing spell on the stack;
    we look up its StackItem id and emit COPY_STACK_ITEM keeping the
    original's chosen targets.

    NOTE (follow-up): printed text allows the caster to choose new targets
    for the copy. v1 keeps the original spell's targets (``new_targets``
    omitted from the event payload). A future enhancement should walk the
    original's ``target_requirements`` and prompt the caster via a chained
    ``target_with_callback`` PendingChoice — see
    ``_virtue_of_knowledge_adventure`` in ``wilds_of_eldraine.py`` for the
    canonical "may choose new targets" retarget walker.
    """
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    controller = spell.controller if spell else None

    # Pull the first target id (the targeted opposing spell on the stack).
    target_card_id: Optional[str] = None
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        target_card_id = t.id
        break
    if not target_card_id:
        return []

    # Locate the StackItem for the targeted spell. Spells on the stack are
    # tracked both as a GameObject in ZoneType.STACK and as a StackItem in
    # the StackManager. ``StackItem.card_id`` references the GameObject.
    game = getattr(state, '_game', None)
    stack = getattr(game, 'stack', None) if game else None
    if stack is None:
        return []
    stack_item_id: Optional[str] = None
    for sitem in stack.get_items():
        if sitem.card_id == target_card_id and getattr(sitem, "can_be_copied", True):
            stack_item_id = sitem.id
            break
    if stack_item_id is None:
        return []
    return [Event(
        type=EventType.COPY_STACK_ITEM,
        payload={
            'stack_item_id': stack_item_id,
            # new_targets omitted: keep original spell's targets (v1 — no
            # retarget prompt).
        },
        source=source_id,
        controller=controller,
    )]


# --- DANCE_OF_THE_TUMBLEWEEDS -------------------------------------------------

def _dance_tumbleweeds_tutor(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: search library for basic land or Desert; put onto battlefield."""
    if not spell:
        return []
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': spell.controller,
            'card_type': CardType.LAND,
            'basic_only': True,
            'destination': 'battlefield_tapped',
        },
        source=spell.id,
    )]


def _dance_tumbleweeds_elemental(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: create X/X green Elemental, X = lands you control."""
    if not spell:
        return []
    x = sum(
        1 for o in state.objects.values()
        if o.zone == ZoneType.BATTLEFIELD
        and o.controller == spell.controller
        and CardType.LAND in o.characteristics.types
    )
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': spell.controller,
            'name': 'Elemental',
            'power': x,
            'toughness': x,
            'types': {CardType.CREATURE},
            'subtypes': {'Elemental'},
            'colors': {Color.GREEN},
            'is_token': True,
        },
        source=spell.id,
    )]


_DANCE_OF_THE_TUMBLEWEEDS_MODES = [
    SpreeMode(
        name="Tutor basic land", extra_cost="{1}",
        effect_fn=_dance_tumbleweeds_tutor,
        description="Search your library for a basic land card or a Desert card, put it onto the battlefield, then shuffle.",
    ),
    SpreeMode(
        name="X/X Elemental", extra_cost="{3}",
        effect_fn=_dance_tumbleweeds_elemental,
        description="Create an X/X green Elemental creature token, where X is the number of lands you control.",
    ),
]


# --- SMUGGLERS_SURPRISE -------------------------------------------------------

def _smugglers_surprise_mill(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: mill 4. Optional recovery is engine gap."""
    if not spell:
        return []
    return [Event(
        type=EventType.MILL,
        payload={'player': spell.controller, 'amount': 4},
        source=spell.id,
    )]


def _smugglers_surprise_cheat_creatures(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: put up to two creatures from hand onto battlefield. Engine gap."""
    return []


def _smugglers_surprise_power4_buff(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: creatures you control with power >= 4 gain hexproof + indestructible EOT."""
    if not spell:
        return []
    events: list[Event] = []
    for obj in state.objects.values():
        if not (obj.zone == ZoneType.BATTLEFIELD and obj.controller == spell.controller
                and CardType.CREATURE in obj.characteristics.types):
            continue
        try:
            p = get_power(obj, state)
        except Exception:
            p = 0
        if p is not None and p >= 4:
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'hexproof',
                         'duration': 'end_of_turn'},
                source=spell.id,
            ))
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'indestructible',
                         'duration': 'end_of_turn'},
                source=spell.id,
            ))
    return events


_SMUGGLERS_SURPRISE_MODES = [
    SpreeMode(
        name="Mill 4", extra_cost="{2}",
        effect_fn=_smugglers_surprise_mill,
        description="Mill four cards. (recovery rider is engine gap)",
    ),
    SpreeMode(
        name="Cheat creatures", extra_cost="{4}{G}",
        effect_fn=_smugglers_surprise_cheat_creatures,
        description="Up to two creatures from hand to battlefield. (engine gap)",
    ),
    SpreeMode(
        name="Power 4+ hexproof/indestructible", extra_cost="{1}",
        effect_fn=_smugglers_surprise_power4_buff,
        description="Creatures you control with power 4 or greater gain hexproof and indestructible until end of turn.",
    ),
]


# --- TRASH_THE_TOWN -----------------------------------------------------------

def _trash_the_town_counters(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: put two +1/+1 counters on target creature."""
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': targets[0], 'counter_type': '+1/+1', 'amount': 2},
        source=spell.id,
    )]


def _trash_the_town_trample(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: target creature gains trample EOT."""
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.GRANT_KEYWORD,
        payload={'object_id': targets[0], 'keyword': 'trample',
                 'duration': 'end_of_turn'},
        source=spell.id,
    )]


def _trash_the_town_draw_trigger(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: target creature gains "deal combat damage -> draw 2" EOT.

    Engine simplification: emit a TEMPORARY_EFFECT with the trigger metadata;
    the engine's combat-damage path may not yet honor this rider, so this is a
    forward-compatible marker.
    """
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'grant_combat_damage_trigger',
            'target_id': targets[0],
            'trigger': 'draw_two',
            'duration': 'end_of_turn',
        },
        source=spell.id,
    )]


_TRASH_THE_TOWN_MODES = [
    SpreeMode(
        name="Two +1/+1 counters", extra_cost="{2}",
        effect_fn=_trash_the_town_counters, target_kind="creature",
        targets_required=1,
        description="Put two +1/+1 counters on target creature.",
    ),
    SpreeMode(
        name="Trample", extra_cost="{1}",
        effect_fn=_trash_the_town_trample, target_kind="creature",
        targets_required=1,
        description="Target creature gains trample until end of turn.",
    ),
    SpreeMode(
        name="Combat-damage draw", extra_cost="{1}",
        effect_fn=_trash_the_town_draw_trigger, target_kind="creature",
        targets_required=1,
        description="Target creature gains 'whenever this creature deals combat damage to a player, draw two cards' until end of turn.",
    ),
]


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ANOTHER_ROUND = make_sorcery(
    name="Another Round",
    mana_cost="{X}{X}{2}{W}",
    colors={Color.WHITE},
    text="Exile any number of creatures you control, then return them to the battlefield under their owner's control. Then repeat this process X more times.",
)

ARCHANGEL_OF_TITHES = make_creature(
    name="Archangel of Tithes",
    power=3, toughness=5,
    mana_cost="{1}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nAs long as this creature is untapped, creatures can't attack you or planeswalkers you control unless their controller pays {1} for each of those creatures.\nAs long as this creature is attacking, creatures can't block unless their controller pays {1} for each of those creatures.",
    setup_interceptors=archangel_of_tithes_setup,
)

ARMORED_ARMADILLO = make_creature(
    name="Armored Armadillo",
    power=0, toughness=4,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Armadillo"},
    text="Ward {1} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\n{3}{W}: This creature gets +X/+0 until end of turn, where X is its toughness.",
    setup_interceptors=armored_armadillo_setup,
)

AVEN_INTERRUPTER = make_creature(
    name="Aven Interrupter",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Rogue"},
    text="Flash\nFlying\nWhen this creature enters, exile target spell. It becomes plotted. (Its owner may cast it as a sorcery on a later turn without paying its mana cost.)\nSpells your opponents cast from graveyards or from exile cost {2} more to cast.",
    setup_interceptors=aven_interrupter_setup,
)

BOUNDING_FELIDAR = make_creature(
    name="Bounding Felidar",
    power=4, toughness=7,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat", "Mount"},
    text="Whenever this creature attacks while saddled, put a +1/+1 counter on each other creature you control. You gain 1 life for each of those creatures.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=bounding_felidar_setup,
)

# =============================================================================
# BOVINE INTERVENTION - Targeted removal with token compensation
# =============================================================================

def _bovine_intervention_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Bovine Intervention after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Verify target is still an artifact or creature
    types = target.characteristics.types
    if CardType.ARTIFACT not in types and CardType.CREATURE not in types:
        return []

    controller = target.controller
    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller,
                'name': 'Ox',
                'power': 2,
                'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Ox'},
                'colors': {Color.WHITE},
                'is_token': True
            },
            source=choice.source_id
        )
    ]


def bovine_intervention_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Bovine Intervention (Phase 5b): Destroy artifact/creature + create Ox token for owner."""
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        target_obj = state.objects.get(t.id)
        controller = target_obj.controller if target_obj else None
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': t.id},
            source=source_id,
        ))
        if controller is not None:
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': controller,
                    'name': 'Ox',
                    'power': 2,
                    'toughness': 2,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Ox'},
                    'colors': {Color.WHITE},
                    'is_token': True,
                },
                source=source_id,
            ))
    return events


BOVINE_INTERVENTION = make_instant(
    name="Bovine Intervention",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or creature. Its controller creates a 2/2 white Ox creature token.",
    resolve=bovine_intervention_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(types={CardType.ARTIFACT, CardType.CREATURE}),
            count=1,
            label="target artifact or creature",
        ),
    ],
)

BRIDLED_BIGHORN = make_creature(
    name="Bridled Bighorn",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Mount", "Sheep"},
    text="Vigilance\nWhenever this creature attacks while saddled, create a 1/1 white Sheep creature token.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=bridled_bighorn_setup,
)

CLAIM_JUMPER = make_creature(
    name="Claim Jumper",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mercenary", "Rabbit"},
    text="Vigilance\nWhen this creature enters, if an opponent controls more lands than you, you may search your library for a Plains card and put it onto the battlefield tapped. Then if an opponent controls more lands than you, repeat this process once. If you search your library this way, shuffle.",
    setup_interceptors=claim_jumper_setup,
)

DUST_ANIMUS = make_creature(
    name="Dust Animus",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nIf you control five or more untapped lands, this creature enters with two +1/+1 counters and a lifelink counter on it.\nPlot {1}{W} (You may pay {1}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=dust_animus_setup,
)
# Phase 5b: register Plot {1}{W} as a hand-zone activated ability.
DUST_ANIMUS.setup_in_hand = make_plot_setup(plot_cost="{1}{W}")

# =============================================================================
# ERIETTE'S LULLABY - Destroy tapped creature + life gain
# =============================================================================

def _eriettes_lullaby_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Eriette's Lullaby after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Verify still tapped
    if not target.state.tapped:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': controller, 'amount': 2},
            source=choice.source_id
        )
    ]


def eriettes_lullaby_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Eriette's Lullaby (Phase 5b): Destroy tapped creature + 2 life."""
    return resolve_chain(
        _otj_destroy_targets(),
        _otj_caster_life_change(2),
    )(targets, state)


ERIETTES_LULLABY = make_sorcery(
    name="Eriette's Lullaby",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target tapped creature. You gain 2 life.",
    resolve=eriettes_lullaby_resolve,
    target_requirements=[target_creature(count=1, tapped=True)],
)

# =============================================================================
# FINAL SHOWDOWN - Spree board wipe / ability removal / protection
# =============================================================================

# =============================================================================
# FINAL SHOWDOWN - Spree (W12 cost-per-mode wired)
# =============================================================================
# Spree (Choose one or more additional costs.)
# + {1} — All creatures lose all abilities until end of turn.
# + {1} — Choose a creature you control. It gains indestructible until end of turn.
# + {3}{W}{W} — Destroy all creatures.

def _final_showdown_lose_abilities(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: all creatures lose all abilities until end of turn."""
    spell_id = spell.id if spell else None
    events: list[Event] = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            events.append(Event(
                type=EventType.TEMPORARY_EFFECT,
                payload={'effect': 'lose_all_abilities', 'target_id': obj.id, 'duration': 'end_of_turn'},
                source=spell_id,
            ))
    return events


def _final_showdown_indestructible(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: choose a creature you control; it gains indestructible until EOT.

    Target chosen via chained PendingChoice at resolve time.
    """
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={'effect': 'grant_keywords', 'target_id': targets[0], 'keywords': ['indestructible'], 'duration': 'end_of_turn'},
        source=spell.id,
    )]


def _final_showdown_destroy_all(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: destroy all creatures."""
    spell_id = spell.id if spell else None
    events: list[Event] = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj.id},
                source=spell_id,
            ))
    return events


_FINAL_SHOWDOWN_MODES = [
    SpreeMode(name="Lose abilities", extra_cost="{1}",
              effect_fn=_final_showdown_lose_abilities,
              description="All creatures lose all abilities until end of turn."),
    SpreeMode(name="Indestructible", extra_cost="{1}",
              effect_fn=_final_showdown_indestructible, target_kind="your_creature",
              targets_required=1,
              description="A creature you control gains indestructible until end of turn."),
    SpreeMode(name="Wrath", extra_cost="{3}{W}{W}",
              effect_fn=_final_showdown_destroy_all,
              description="Destroy all creatures."),
]


FINAL_SHOWDOWN = make_instant(
    name="Final Showdown",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — All creatures lose all abilities until end of turn.\n+ {1} — Choose a creature you control. It gains indestructible until end of turn.\n+ {3}{W}{W} — Destroy all creatures.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_FINAL_SHOWDOWN_MODES),
    resolve=make_spree_resolve(_FINAL_SHOWDOWN_MODES),
)

FORTUNE_LOYAL_STEED = make_creature(
    name="Fortune, Loyal Steed",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Mount"},
    supertypes={"Legendary"},
    text="When Fortune enters, scry 2.\nWhenever Fortune attacks while saddled, at end of combat, exile it and up to one creature that saddled it this turn, then return those cards to the battlefield under their owner's control.\nSaddle 1",
    setup_interceptors=fortune_loyal_steed_setup,
)

FRONTIER_SEEKER = make_creature(
    name="Frontier Seeker",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When this creature enters, look at the top five cards of your library. You may reveal a Mount creature card or a Plains card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=frontier_seeker_setup,
)


GETAWAY_GLAMER = make_instant(
    name="Getaway Glamer",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Exile target nontoken creature. Return it to the battlefield under its owner's control at the beginning of the next end step.\n+ {2} — Destroy target creature if no other creature has greater power.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_GETAWAY_GLAMER_MODES),
    resolve=make_spree_resolve(_GETAWAY_GLAMER_MODES),
)

HIGH_NOON = make_enchantment(
    name="High Noon",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Each player can't cast more than one spell each turn.\n{4}{R}, Sacrifice this enchantment: It deals 5 damage to any target.",
    setup_interceptors=high_noon_setup,
)

HOLY_COW = make_creature(
    name="Holy Cow",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Ox"},
    text="Flash\nFlying\nWhen this creature enters, you gain 2 life and scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    setup_interceptors=holy_cow_setup,
)

INVENTIVE_WINGSMITH = make_creature(
    name="Inventive Wingsmith",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Dwarf"},
    text="At the beginning of your end step, if you haven't cast a spell from your hand this turn and this creature doesn't have a flying counter on it, put a flying counter on it.",
    setup_interceptors=inventive_wingsmith_setup,
)

LASSOED_BY_THE_LAW = make_enchantment(
    name="Lassoed by the Law",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.\nWhen this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=lassoed_by_the_law_setup,
)

MYSTICAL_TETHER = make_enchantment(
    name="Mystical Tether",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="You may cast this spell as though it had flash if you pay {2} more to cast it.\nWhen this enchantment enters, exile target artifact or creature an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=mystical_tether_setup,
)

NURTURING_PIXIE = make_creature(
    name="Nurturing Pixie",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhen this creature enters, return up to one target non-Faerie, nonland permanent you control to its owner's hand. If a permanent was returned this way, put a +1/+1 counter on this creature.",
    setup_interceptors=nurturing_pixie_setup,
)

OMENPORT_VIGILANTE = make_creature(
    name="Omenport Vigilante",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="This creature has double strike as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=omenport_vigilante_setup,
)

ONE_LAST_JOB = make_sorcery(
    name="One Last Job",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Return target creature card from your graveyard to the battlefield.\n+ {1} — Return target Mount or Vehicle card from your graveyard to the battlefield.\n+ {1} — Return target Aura or Equipment card from your graveyard to the battlefield attached to a creature you control.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_ONE_LAST_JOB_MODES),
    resolve=make_spree_resolve(_ONE_LAST_JOB_MODES),
)

OUTLAW_MEDIC = make_creature(
    name="Outlaw Medic",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rogue"},
    text="Lifelink\nWhen this creature dies, draw a card.",
    setup_interceptors=outlaw_medic_setup,
)

PRAIRIE_DOG = make_creature(
    name="Prairie Dog",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Squirrel"},
    text="Lifelink\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, put a +1/+1 counter on this creature.\n{4}{W}: Until end of turn, if you would put one or more +1/+1 counters on a creature you control, put that many plus one +1/+1 counters on it instead.",
    setup_interceptors=prairie_dog_setup,
)

PROSPERITY_TYCOON = make_creature(
    name="Prosperity Tycoon",
    power=4, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="When this creature enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\n{2}, Sacrifice a token: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it.)",
    setup_interceptors=prosperity_tycoon_setup,
)

# =============================================================================
# REQUISITION RAID - Spree artifact/enchantment destruction + counters
# =============================================================================

def _requisition_raid_artifact_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Requisition Raid artifact destruction mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.ARTIFACT not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _requisition_raid_enchantment_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Requisition Raid enchantment destruction mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.ENCHANTMENT not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _requisition_raid_counters_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Requisition Raid counters mode."""
    target_player = selected[0] if selected else None
    if not target_player:
        return []

    events = []
    for obj in state.objects.values():
        if obj.controller == target_player and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=choice.source_id
                ))

    return events


def _requisition_raid_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Requisition Raid modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Destroy target artifact
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.ARTIFACT in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an artifact to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _requisition_raid_artifact_execute
            return events

    # Mode 1: Destroy target enchantment
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.ENCHANTMENT in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an enchantment to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _requisition_raid_enchantment_execute
            return events

    # Mode 2: Put a +1/+1 counter on each creature target player controls
    if 2 in selected_modes:
        valid_targets = list(state.players.keys())

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a player to give +1/+1 counters to their creatures",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _requisition_raid_counters_execute

    return events


def requisition_raid_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Requisition Raid - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — Destroy target artifact.
    + {1} — Destroy target enchantment.
    + {1} — Put a +1/+1 counter on each creature target player controls.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Requisition Raid":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "requisition_raid_spell"

    modes = [
        {"index": 0, "text": "Destroy target artifact."},
        {"index": 1, "text": "Destroy target enchantment."},
        {"index": 2, "text": "Put a +1/+1 counter on each creature target player controls."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=3,
        prompt="Requisition Raid - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _requisition_raid_mode_execute

    return []


# =============================================================================
# REQUISITION RAID - Spree (W12 cost-per-mode wired)
# =============================================================================
# Spree (Choose one or more additional costs.)
# + {1} — Destroy target artifact.
# + {1} — Destroy target enchantment.
# + {1} — Put a +1/+1 counter on each creature target player controls.
#
# Per-mode targets are gathered via chained PendingChoices: each targeted
# mode opens a target_with_callback prompt during resolve, the handler runs
# the mode's effect with the chosen target, then chains to the next mode.

def _requisition_raid_destroy_artifact(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: destroy target artifact (target chosen via PendingChoice chain)."""
    if not spell or not targets:
        return []
    return [Event(type=EventType.OBJECT_DESTROYED,
                  payload={'object_id': targets[0]}, source=spell.id)]


def _requisition_raid_destroy_enchantment(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: destroy target enchantment (target chosen via PendingChoice chain)."""
    if not spell or not targets:
        return []
    return [Event(type=EventType.OBJECT_DESTROYED,
                  payload={'object_id': targets[0]}, source=spell.id)]


def _requisition_raid_counters(spell, state: GameState, targets) -> list[Event]:
    """Mode 2: +1/+1 counter on each creature target player controls."""
    if not spell or not targets:
        return []
    target_player = targets[0]
    events: list[Event] = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD
                and obj.controller == target_player
                and CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=spell.id,
            ))
    return events


_REQUISITION_RAID_MODES = [
    SpreeMode(name="Destroy artifact", extra_cost="{1}",
              effect_fn=_requisition_raid_destroy_artifact, target_kind="artifact",
              targets_required=1,
              description="Destroy target artifact."),
    SpreeMode(name="Destroy enchantment", extra_cost="{1}",
              effect_fn=_requisition_raid_destroy_enchantment, target_kind="enchantment",
              targets_required=1,
              description="Destroy target enchantment."),
    SpreeMode(name="Pump player's creatures", extra_cost="{1}",
              effect_fn=_requisition_raid_counters, target_kind="player",
              targets_required=1,
              description="Put a +1/+1 counter on each creature target player controls."),
]


REQUISITION_RAID = make_sorcery(
    name="Requisition Raid",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Destroy target artifact.\n+ {1} — Destroy target enchantment.\n+ {1} — Put a +1/+1 counter on each creature target player controls.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_REQUISITION_RAID_MODES),
    resolve=make_spree_resolve(_REQUISITION_RAID_MODES),
)


# =============================================================================
# RUSTLER RAMPAGE - Spree (W12 cost-per-mode wired)
# =============================================================================
# Spree (Choose one or more additional costs.)
# + {1} — Untap all creatures target player controls.
# + {1} — Target creature gains double strike until end of turn.
#
# Per-mode targets are gathered via chained PendingChoices at resolve time.

def _rustler_rampage_untap(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: untap all creatures target player controls."""
    if not spell or not targets:
        return []
    target_player = targets[0]
    events: list[Event] = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD
                and obj.controller == target_player
                and CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.UNTAP,
                payload={'object_id': obj.id},
                source=spell.id,
            ))
    return events


def _rustler_rampage_double_strike(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: target creature gains double strike until EOT."""
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.GRANT_KEYWORD,
        payload={'object_id': targets[0], 'keyword': 'double_strike', 'duration': 'end_of_turn'},
        source=spell.id,
    )]


_RUSTLER_RAMPAGE_MODES = [
    SpreeMode(name="Untap all", extra_cost="{1}",
              effect_fn=_rustler_rampage_untap, target_kind="player",
              targets_required=1,
              description="Untap all creatures target player controls."),
    SpreeMode(name="Double strike", extra_cost="{1}",
              effect_fn=_rustler_rampage_double_strike, target_kind="creature",
              targets_required=1,
              description="Target creature gains double strike until end of turn."),
]


RUSTLER_RAMPAGE = make_instant(
    name="Rustler Rampage",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Untap all creatures target player controls.\n+ {1} — Target creature gains double strike until end of turn.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_RUSTLER_RAMPAGE_MODES),
    resolve=make_spree_resolve(_RUSTLER_RAMPAGE_MODES),
)

SHEPHERD_OF_THE_CLOUDS = make_creature(
    name="Shepherd of the Clouds",
    power=4, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Pegasus"},
    text="Flying, vigilance\nWhen this creature enters, return target permanent card with mana value 3 or less from your graveyard to your hand. Return that card to the battlefield instead if you control a Mount.",
    setup_interceptors=shepherd_of_clouds_setup,
)

SHERIFF_OF_SAFE_PASSAGE = make_creature(
    name="Sheriff of Safe Passage",
    power=0, toughness=0,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="This creature enters with a +1/+1 counter on it plus an additional +1/+1 counter on it for each other creature you control.\nPlot {1}{W} (You may pay {1}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=sheriff_of_safe_passage_setup,
)
# Phase 5b: register Plot {1}{W} as a hand-zone activated ability.
SHERIFF_OF_SAFE_PASSAGE.setup_in_hand = make_plot_setup(plot_cost="{1}{W}")

STAGECOACH_SECURITY = make_creature(
    name="Stagecoach Security",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, creatures you control get +1/+1 and gain vigilance until end of turn.\nPlot {3}{W} (You may pay {3}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=stagecoach_security_setup,
)
# Phase 5b: register Plot {3}{W} as a hand-zone activated ability.
STAGECOACH_SECURITY.setup_in_hand = make_plot_setup(plot_cost="{3}{W}")

# =============================================================================
# STEER CLEAR - Conditional damage to attacker/blocker
# =============================================================================

def _steer_clear_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Steer Clear after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Check if controller has a Mount (stored at cast time in callback_data)
    has_mount = choice.callback_data.get('has_mount', False)
    damage = 4 if has_mount else 2

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': damage,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def steer_clear_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Steer Clear (Phase 5b): 2 dmg (4 if Mount controller) to atk/blk creature."""
    caster = _otj_spell_caster_id(state)
    has_mount = any(
        obj.controller == caster and obj.zone == ZoneType.BATTLEFIELD and
        CardType.CREATURE in obj.characteristics.types and
        'Mount' in obj.characteristics.subtypes
        for obj in state.objects.values()
    )
    damage = 4 if has_mount else 2
    return _otj_damage_to_targets(damage)(targets, state)


def _attacking_or_blocking_creature_filter(obj: GameObject, state: GameState) -> bool:
    if CardType.CREATURE not in obj.characteristics.types:
        return False
    return bool(getattr(obj.state, 'attacking', False) or getattr(obj.state, 'blocking', False))


STEER_CLEAR = make_instant(
    name="Steer Clear",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Steer Clear deals 2 damage to target attacking or blocking creature. Steer Clear deals 4 damage to that creature instead if you controlled a Mount as you cast this spell.",
    resolve=steer_clear_resolve,
    target_requirements=[
        TargetRequirement(
            filter=creature_filter(custom_filter=_attacking_or_blocking_creature_filter),
            count=1,
            label="target attacking or blocking creature",
        ),
    ],
)

STERLING_KEYKEEPER = make_creature(
    name="Sterling Keykeeper",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="{2}, {T}: Tap target non-Mount creature.",
    setup_interceptors=sterling_keykeeper_setup,
)

STERLING_SUPPLIER = make_creature(
    name="Sterling Supplier",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Soldier"},
    text="Flying\nWhen this creature enters, put a +1/+1 counter on another target creature you control.",
    setup_interceptors=sterling_supplier_setup,
)

# =============================================================================
# TAKE UP THE SHIELD - Combat trick with counter + abilities
# =============================================================================

def _take_up_the_shield_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Take Up the Shield after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [
        Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': target_id,
                'keywords': ['lifelink', 'indestructible'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def take_up_the_shield_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Take Up the Shield (Phase 5b): +1/+1 counter + lifelink/indestructible EOT."""
    return resolve_chain(
        _otj_counter_targets(amount=1, counter_type='+1/+1'),
        _otj_grant_keywords_to_targets('lifelink', 'indestructible'),
    )(targets, state)


TAKE_UP_THE_SHIELD = make_instant(
    name="Take Up the Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature. It gains lifelink and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    resolve=take_up_the_shield_resolve,
    target_requirements=[target_creature(count=1)],
)

THUNDER_LASSO = make_artifact(
    name="Thunder Lasso",
    mana_cost="{2}{W}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+1.\nWhenever equipped creature attacks, tap target creature defending player controls.\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=thunder_lasso_setup,
)

TRAINED_ARYNX = make_creature(
    name="Trained Arynx",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat", "Mount"},
    text="Whenever this creature attacks while saddled, it gains first strike until end of turn. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=trained_arynx_setup,
)

VENGEFUL_TOWNSFOLK = make_creature(
    name="Vengeful Townsfolk",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="Whenever one or more other creatures you control die, put a +1/+1 counter on this creature.",
    setup_interceptors=vengeful_townsfolk_setup,
)

WANTED_GRIFFIN = make_creature(
    name="Wanted Griffin",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying\nWhen this creature dies, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=wanted_griffin_setup,
)

ARCHMAGES_NEWT = make_creature(
    name="Archmage's Newt",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Mount", "Salamander"},
    text="Whenever this creature deals combat damage to a player, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost. That card gains flashback {0} until end of turn instead if this creature is saddled. (You may cast that card from your graveyard for its flashback cost. Then exile it.)\nSaddle 3",
    setup_interceptors=archmages_newt_setup,
)

CANYON_CRAB = make_creature(
    name="Canyon Crab",
    power=0, toughness=5,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Crab"},
    text="{1}{U}: This creature gets +2/-2 until end of turn.\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card, then discard a card.",
    setup_interceptors=canyon_crab_setup,
)

DARING_THUNDERTHIEF = make_creature(
    name="Daring Thunder-Thief",
    power=4, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Turtle"},
    text="Flash\nThis creature enters tapped.",
    setup_interceptors=daring_thunderthief_setup,
)

DEEPMUCK_DESPERADO = make_creature(
    name="Deepmuck Desperado",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Homarid", "Mercenary"},
    text="Whenever you commit a crime, each opponent mills three cards. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=deepmuck_desperado_setup,
)

DJINN_OF_FOOLS_FALL = make_creature(
    name="Djinn of Fool's Fall",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Djinn"},
    text="Flying\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)
# Phase 5b: register Plot {3}{U} as a hand-zone activated ability.
DJINN_OF_FOOLS_FALL.setup_in_hand = make_plot_setup(plot_cost="{3}{U}")

DOUBLE_DOWN = make_enchantment(
    name="Double Down",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an outlaw spell, copy that spell. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. Copies of permanent spells become tokens.)",
    setup_interceptors=double_down_setup,
)

DUELIST_OF_THE_MIND = make_creature(
    name="Duelist of the Mind",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Human"},
    text="Flying, vigilance\nDuelist of the Mind's power is equal to the number of cards you've drawn this turn.\nWhenever you commit a crime, you may draw a card. If you do, discard a card. This ability triggers only once each turn.",
    setup_interceptors=duelist_of_the_mind_setup,
)

EMERGENT_HAUNTING = make_enchantment(
    name="Emergent Haunting",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="At the beginning of your end step, if you haven't cast a spell from your hand this turn and this enchantment isn't a creature, it becomes a 3/3 Spirit creature with flying in addition to its other types.\n{2}{U}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=emergent_haunting_setup,
)

# =============================================================================
# FAILED FORDING - Bounce + surveil if Desert
# =============================================================================

def _failed_fording_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Failed Fording after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.LAND in target.characteristics.types:
        return []

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'to_zone': f'hand_{target.owner}',
            'to_zone_type': ZoneType.HAND,
            'reason': 'bounced'
        },
        source=choice.source_id
    )]

    # Check if controller controls a Desert
    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player
    has_desert = False
    for obj in state.objects.values():
        if obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.LAND in obj.characteristics.types:
                if 'Desert' in obj.characteristics.subtypes:
                    has_desert = True
                    break

    if has_desert:
        events.append(Event(
            type=EventType.SURVEIL,
            payload={'player': controller, 'amount': 1},
            source=choice.source_id
        ))

    return events


def failed_fording_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Failed Fording (Phase 5b): Bounce nonland permanent + Desert surveil 1."""
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _otj_spell_caster_id(state)
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
    # If controller has a Desert, surveil 1.
    if caster is not None:
        has_desert = any(
            obj.controller == caster and obj.zone == ZoneType.BATTLEFIELD and
            'Desert' in obj.characteristics.subtypes
            for obj in state.objects.values()
        )
        if has_desert:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': caster, 'amount': 1},
                source=source_id,
            ))
    return events


def _otj_nonland_permanent_filter(obj: GameObject, state: GameState) -> bool:
    return CardType.LAND not in obj.characteristics.types


FAILED_FORDING = make_instant(
    name="Failed Fording",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If you control a Desert, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    resolve=failed_fording_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER},
                custom_filter=_otj_nonland_permanent_filter,
            ),
            count=1,
            label="target nonland permanent",
        ),
    ],
)

FBLTHP_LOST_ON_THE_RANGE = make_creature(
    name="Fblthp, Lost on the Range",
    power=1, toughness=1,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    supertypes={"Legendary"},
    text="Ward {2}\nYou may look at the top card of your library any time.\nThe top card of your library has plot. The plot cost is equal to its mana cost.\nYou may plot nonland cards from the top of your library.",
    setup_interceptors=fblthp_lost_on_the_range_setup,
)

def _fleeting_reflection_pick_source(choice, selected, state: GameState) -> list[Event]:
    """Step 2 of Fleeting Reflection: target creature picked above becomes a copy
    of this second target. ``choice.callback_data['target_obj_id']`` carries the
    creature picked in step 1."""
    target_obj_id = choice.callback_data.get('target_obj_id')
    target_obj = state.objects.get(target_obj_id) if target_obj_id else None
    if target_obj is None:
        return []

    # Untap step 1's target.
    events: list[Event] = [Event(
        type=EventType.UNTAP_TARGET,
        payload={'object_id': target_obj.id},
        source=choice.source_id,
    )]

    if not selected:
        # "Up to one other target" — no second target picked, so the
        # target keeps hexproof+untap but doesn't become a copy of anything.
        return events

    source_id = selected[0]
    if source_id == target_obj.id:
        # Must be "another" creature.
        return events
    source_obj = state.objects.get(source_id)
    if source_obj is None:
        return events

    becomes_copy_of(
        target_obj, source_obj, state,
        duration='end_of_turn',
    )
    return events


def _fleeting_reflection_pick_target(choice, selected, state: GameState) -> list[Event]:
    """Step 1 of Fleeting Reflection: pick the controller's creature that gains
    hexproof / untap / becomes-a-copy. After confirmation, open a second
    pending_choice asking for the creature to copy."""
    if not selected:
        return []
    target_obj_id = selected[0]
    target = state.objects.get(target_obj_id)
    if target is None:
        return []

    # Hexproof until end of turn — register a temporary keyword grant by adding
    # a small QUERY interceptor on the target. Use the standard pattern:
    def hex_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_ABILITIES
                and event.payload.get('object_id') == target.id)

    def hex_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []) or [])
        if 'hexproof' not in granted:
            granted.append('hexproof')
        new_event.payload['granted'] = granted
        existing_value = new_event.payload.get('value')
        if isinstance(existing_value, (set, list)):
            new_event.payload['value'] = set(existing_value) | {'hexproof'}
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    hex_ic = Interceptor(
        id=new_id(),
        source=target.id,
        controller=target.controller,
        priority=InterceptorPriority.QUERY,
        filter=hex_filter,
        handler=hex_handler,
        duration='end_of_turn',
    )
    hex_ic.timestamp = state.next_timestamp()
    state.interceptors[hex_ic.id] = hex_ic

    # Now build the "up to one other target creature" choice.
    legal_sources: list[str] = []
    bf = state.zones.get('battlefield')
    if bf is not None:
        for cid in bf.objects:
            cand = state.objects.get(cid)
            if cand is None or cand.id == target.id:
                continue
            if CardType.CREATURE not in cand.characteristics.types:
                continue
            legal_sources.append(cid)

    if not legal_sources:
        # Up-to-one — still allowed to pick none. Apply untap directly.
        return [Event(
            type=EventType.UNTAP_TARGET,
            payload={'object_id': target.id},
            source=choice.source_id,
        )]

    sub_choice = create_target_choice(
        state=state,
        player_id=choice.player,
        source_id=choice.source_id,
        legal_targets=legal_sources,
        prompt="Fleeting Reflection: choose up to one other creature to copy (or skip)",
        min_targets=0,
        max_targets=1,
    )
    sub_choice.choice_type = "target_with_callback"
    sub_choice.callback_data['handler'] = _fleeting_reflection_pick_source
    sub_choice.callback_data['target_obj_id'] = target.id
    return []


def fleeting_reflection_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Fleeting Reflection: pick controller's creature, then pick another
    creature whose copy it becomes for this turn."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Fleeting Reflection":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "fleeting_reflection_spell"

    legal_targets = []
    for cid, cobj in state.objects.items():
        if cobj.zone != ZoneType.BATTLEFIELD:
            continue
        if cobj.controller != caster_id:
            continue
        if CardType.CREATURE not in cobj.characteristics.types:
            continue
        legal_targets.append(cid)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Fleeting Reflection: choose target creature you control",
        min_targets=1,
        max_targets=1,
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _fleeting_reflection_pick_target
    return []


FLEETING_REFLECTION = make_instant(
    name="Fleeting Reflection",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Untap that creature. Until end of turn, it becomes a copy of up to one other target creature.",
    resolve=fleeting_reflection_resolve,
)

GERALF_THE_FLESHWRIGHT = make_creature(
    name="Geralf, the Fleshwright",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell during your turn other than your first spell that turn, create a 2/2 blue and black Zombie Rogue creature token.\nWhenever a Zombie you control enters, put a +1/+1 counter on it for each other Zombie that entered the battlefield under your control this turn.",
    setup_interceptors=geralf_the_fleshwright_setup,
)

GEYSER_DRAKE = make_creature(
    name="Geyser Drake",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nDuring turns other than yours, spells you cast cost {1} less to cast.",
    setup_interceptors=geyser_drake_setup,
)

HARRIER_STRIX = make_creature(
    name="Harrier Strix",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying\nWhen this creature enters, tap target permanent.\n{2}{U}: Draw a card, then discard a card.",
    setup_interceptors=harrier_strix_setup,
)

# Phase 5b: migrate Jailbreak Scheme to SpreeMode pattern.
def _jailbreak_counter_unblockable(spell, state, targets):
    """Mode 0: +1/+1 counter on target creature + unblockable this turn."""
    if not targets:
        return []
    target_id = targets[0].id if hasattr(targets[0], "id") else targets[0]
    return [
        Event(type=EventType.COUNTER_ADDED,
              payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
              source=spell.id),
        Event(type=EventType.GRANT_KEYWORD,
              payload={'object_id': target_id, 'keyword': 'unblockable',
                       'duration': 'end_of_turn'},
              source=spell.id),
    ]


def _jailbreak_bounce_to_library(spell, state, targets):
    """Mode 1: put target artifact/creature on top or bottom of library.

    Engine simplification: bounce to the top of the owner's library
    (owner's choice would require a PendingChoice from that owner; we
    pick top as the more common outcome).
    """
    if not targets:
        return []
    target_id = targets[0].id if hasattr(targets[0], "id") else targets[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [
        Event(type=EventType.ZONE_CHANGE,
              payload={
                  'object_id': target_id,
                  'from_zone_type': ZoneType.BATTLEFIELD,
                  'to_zone_type': ZoneType.LIBRARY,
                  'to_top': True,
              },
              source=spell.id),
    ]


_JAILBREAK_SCHEME_MODES = [
    SpreeMode(
        name="Counter + Evasion", extra_cost="{3}",
        effect_fn=_jailbreak_counter_unblockable,
        target_kind="creature", targets_required=1,
        description="Put a +1/+1 counter on target creature. It can't be blocked this turn.",
    ),
    SpreeMode(
        name="Library bounce", extra_cost="{2}",
        effect_fn=_jailbreak_bounce_to_library,
        target_kind="permanent", targets_required=1,
        description="Target artifact or creature's owner puts it on top of their library.",
        legal_targets_filter=lambda spell, state: [
            obj.id for obj in state.objects.values()
            if obj.zone == ZoneType.BATTLEFIELD
            and (CardType.ARTIFACT in obj.characteristics.types
                 or CardType.CREATURE in obj.characteristics.types)
        ],
    ),
]


JAILBREAK_SCHEME = make_sorcery(
    name="Jailbreak Scheme",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {3} — Put a +1/+1 counter on target creature. It can't be blocked this turn.\n+ {2} — Target artifact or creature's owner puts it on their choice of the top or bottom of their library.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_JAILBREAK_SCHEME_MODES),
    resolve=make_spree_resolve(_JAILBREAK_SCHEME_MODES),
)

THE_KEY_TO_THE_VAULT = make_artifact(
    name="The Key to the Vault",
    mana_cost="{1}{U}",
    text="Whenever equipped creature deals combat damage to a player, look at that many cards from the top of your library. You may exile a nonland card from among them. Put the rest on the bottom of your library in a random order. You may cast the exiled card without paying its mana cost.\nEquip {2}{U}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    setup_interceptors=the_key_to_the_vault_setup,
)

LOAN_SHARK = make_creature(
    name="Loan Shark",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Shark"},
    text="When this creature enters, if you've cast two or more spells this turn, draw a card.\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=loan_shark_setup,
)
# Phase 5b: register Plot {3}{U} as a hand-zone activated ability.
LOAN_SHARK.setup_in_hand = make_plot_setup(plot_cost="{3}{U}")

MARAUDING_SPHINX = make_creature(
    name="Marauding Sphinx",
    power=3, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Sphinx"},
    text="Flying, vigilance, ward {2}\nWhenever you commit a crime, surveil 2. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=marauding_sphinx_setup,
)

# =============================================================================
# METAMORPHIC BLAST - Spree transform/draw
# =============================================================================

def _metamorphic_blast_rabbit_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Metamorphic Blast rabbit mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'become_creature',
            'target_id': target_id,
            'name': 'Rabbit',
            'power': 0,
            'toughness': 1,
            'colors': {Color.WHITE},
            'subtypes': {'Rabbit'},
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def _metamorphic_blast_draw_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Metamorphic Blast draw mode."""
    target_player = selected[0] if selected else None
    if not target_player:
        return []

    return [Event(
        type=EventType.DRAW,
        payload={'player': target_player, 'amount': 2},
        source=choice.source_id
    )]


def _metamorphic_blast_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Metamorphic Blast modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Turn target creature into a 0/1 white Rabbit
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to become a 0/1 white Rabbit",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _metamorphic_blast_rabbit_execute
            return events

    # Mode 1: Target player draws two cards
    if 1 in selected_modes:
        valid_targets = list(state.players.keys())

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a player to draw two cards",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _metamorphic_blast_draw_execute

    return events


def metamorphic_blast_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Metamorphic Blast - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — Target creature becomes a white Rabbit with base power and toughness 0/1.
    + {3} — Target player draws two cards.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Metamorphic Blast":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "metamorphic_blast_spell"

    modes = [
        {"index": 0, "text": "Target creature becomes a white Rabbit with base P/T 0/1."},
        {"index": 1, "text": "Target player draws two cards."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Metamorphic Blast - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _metamorphic_blast_mode_execute

    return []


# Phase 5b: migrate Metamorphic Blast to SpreeMode pattern.
def _metamorphic_blast_rabbit(spell, state, targets):
    """Mode 0: target creature becomes a white 0/1 Rabbit until EOT."""
    if not targets:
        return []
    target_id = targets[0].id if hasattr(targets[0], "id") else targets[0]
    # Use a PT_SET-ish event; the engine's becomes-creature handling is in
    # interceptor_helpers. For a minimal effect, emit PT_MODIFICATION events.
    # Simpler: emit PT_SET-equivalent and let the becomes_creature helper handle it.
    from src.cards.interceptor_helpers import becomes_creature as _becomes_creature
    target = state.objects.get(target_id)
    if target is None:
        return []
    _becomes_creature(
        target, state,
        power=0, toughness=1,
        subtypes={"Rabbit"},
    )
    return []


def _metamorphic_blast_draw_two(spell, state, targets):
    """Mode 1: target player draws two cards."""
    if not targets:
        return []
    target_id = targets[0].id if hasattr(targets[0], "id") else targets[0]
    return [
        Event(type=EventType.DRAW_CARD,
              payload={'player': target_id, 'amount': 2},
              source=spell.id),
    ]


_METAMORPHIC_BLAST_MODES = [
    SpreeMode(
        name="Rabbit", extra_cost="{1}",
        effect_fn=_metamorphic_blast_rabbit,
        target_kind="creature", targets_required=1,
        description="Target creature becomes a 0/1 white Rabbit until end of turn.",
    ),
    SpreeMode(
        name="Draw two", extra_cost="{3}",
        effect_fn=_metamorphic_blast_draw_two,
        target_kind="player", targets_required=1,
        description="Target player draws two cards.",
    ),
]


METAMORPHIC_BLAST = make_instant(
    name="Metamorphic Blast",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Until end of turn, target creature becomes a white Rabbit with base power and toughness 0/1.\n+ {3} — Target player draws two cards.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_METAMORPHIC_BLAST_MODES),
    resolve=make_spree_resolve(_METAMORPHIC_BLAST_MODES),
)

NIMBLE_BRIGAND = make_creature(
    name="Nimble Brigand",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="This creature can't be blocked if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nWhenever this creature deals combat damage to a player, draw a card.",
    setup_interceptors=nimble_brigand_setup,
)

OUTLAW_STITCHER = make_creature(
    name="Outlaw Stitcher",
    power=1, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a 2/2 blue and black Zombie Rogue creature token, then put two +1/+1 counters on that token for each spell you've cast this turn other than the first.\nPlot {4}{U} (You may pay {4}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=outlaw_stitcher_setup,
)
# Phase 5b: register Plot {4}{U} as a hand-zone activated ability.
OUTLAW_STITCHER.setup_in_hand = make_plot_setup(plot_cost="{4}{U}")

PEERLESS_ROPEMASTER = make_creature(
    name="Peerless Ropemaster",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, return up to one target tapped creature to its owner's hand.",
    setup_interceptors=peerless_ropemaster_setup,
)


PHANTOM_INTERFERENCE = make_instant(
    name="Phantom Interference",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {3} — Create a 2/2 white Spirit creature token with flying.\n+ {1} — Counter target spell unless its controller pays {2}.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_PHANTOM_INTERFERENCE_MODES),
    resolve=make_spree_resolve(_PHANTOM_INTERFERENCE_MODES),
)

PLAN_THE_HEIST = make_sorcery(
    name="Plan the Heist",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Surveil 3 if you have no cards in hand. Then draw three cards. (To surveil 3, look at the top three cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)
# Phase 5b: register Plot {3}{U} as a hand-zone activated ability.
PLAN_THE_HEIST.setup_in_hand = make_plot_setup(plot_cost="{3}{U}")

RAZZLEDAZZLER = make_creature(
    name="Razzle-Dazzler",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature. It can't be blocked this turn.",
    setup_interceptors=razzledazzler_setup,
)

SEIZE_THE_SECRETS = make_sorcery(
    name="Seize the Secrets",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nDraw two cards.",
    resolve=seize_the_secrets_resolve,
)

SHACKLE_SLINGER = make_creature(
    name="Shackle Slinger",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="Whenever you cast your second spell each turn, choose target creature an opponent controls. If it's tapped, put a stun counter on it. Otherwise, tap it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=shackle_slinger_setup,
)

SHIFTING_GRIFT = make_sorcery(
    name="Shifting Grift",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Each player chooses a permanent they control. Exchange control of those permanents.",
    resolve=shifting_grift_resolve,
)

SLICKSHOT_LOCKPICKER = make_creature(
    name="Slickshot Lockpicker",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost. (You may cast that card from your graveyard for its flashback cost. Then exile it.)\nPlot {2}{U} (You may pay {2}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=slickshot_lockpicker_setup,
)
# Phase 5b: register Plot {2}{U} as a hand-zone activated ability.
SLICKSHOT_LOCKPICKER.setup_in_hand = make_plot_setup(plot_cost="{2}{U}")

SLICKSHOT_VAULTBUSTER = make_creature(
    name="Slickshot Vault-Buster",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Vigilance\nThis creature gets +2/+0 as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=slickshot_vaultbuster_setup,
)

SPRING_SPLASHER = make_creature(
    name="Spring Splasher",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast", "Frog"},
    text="Whenever this creature attacks, target creature defending player controls gets -3/-0 until end of turn.",
    setup_interceptors=spring_splasher_setup,
)

STEP_BETWEEN_WORLDS = make_sorcery(
    name="Step Between Worlds",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Each player may shuffle their hand and graveyard into their library. Each player who does draws seven cards. Exile Step Between Worlds.\nPlot {4}{U}{U} (You may pay {4}{U}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    resolve=step_between_worlds_resolve,
)
# Phase 5b: register Plot {4}{U}{U} as a hand-zone activated ability.
STEP_BETWEEN_WORLDS.setup_in_hand = make_plot_setup(plot_cost="{4}{U}{U}")

STOIC_SPHINX = make_creature(
    name="Stoic Sphinx",
    power=5, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flash\nFlying\nThis creature has hexproof as long as you haven't cast a spell this turn.",
    setup_interceptors=stoic_sphinx_setup,
)

STOP_COLD = make_enchantment(
    name="Stop Cold",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant artifact or creature\nWhen this Aura enters, tap enchanted permanent.\nEnchanted permanent loses all abilities and doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
    setup_interceptors=stop_cold_setup,
)

# =============================================================================
# TAKE THE FALL - Conditional debuff + cantrip
# =============================================================================

def _take_the_fall_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Take the Fall after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    has_outlaw = choice.callback_data.get('has_outlaw', False)
    power_mod = -4 if has_outlaw else -1

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    return [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': target_id,
                'power_mod': power_mod,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.DRAW,
            payload={'player': controller, 'amount': 1},
            source=choice.source_id
        )
    ]


def take_the_fall_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Take the Fall (Phase 5b): -1/-0 (or -4/-0 with outlaw) + draw."""
    caster = _otj_spell_caster_id(state)
    has_outlaw = False
    if caster is not None:
        for obj in state.objects.values():
            if obj.controller == caster and obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    subtypes = obj.characteristics.subtypes or set()
                    if subtypes & OUTLAW_TYPES:
                        has_outlaw = True
                        break
    power_mod = -4 if has_outlaw else -1
    return resolve_chain(
        _otj_pump_targets(power_mod, 0),
        _otj_caster_draw(1),
    )(targets, state)


TAKE_THE_FALL = make_instant(
    name="Take the Fall",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -1/-0 until end of turn. It gets -4/-0 until end of turn instead if you control an outlaw. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nDraw a card.",
    resolve=take_the_fall_resolve,
    target_requirements=[target_creature(count=1)],
)

# =============================================================================
# THIS TOWN AIN'T BIG ENOUGH - Bounce up to 2 permanents
# =============================================================================

def _this_town_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute This Town Ain't Big Enough after target selection."""
    events = []
    for target_id in selected:
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            continue

        if CardType.LAND in target.characteristics.types:
            continue

        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone': f'battlefield_{target.controller}',
                'to_zone': f'hand_{target.owner}',
                'to_zone_type': ZoneType.HAND,
                'reason': 'bounced'
            },
            source=choice.source_id
        ))

    return events


def this_town_aint_big_enough_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve This Town Ain't Big Enough (Phase 5b): Bounce up to 2 nonland permanents."""
    spell = _otj_resolving_spell_obj(state)
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


THIS_TOWN_AINT_BIG_ENOUGH = make_instant(
    name="This Town Ain't Big Enough",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="This spell costs {3} less to cast if it targets a permanent you control.\nReturn up to two target nonland permanents to their owners' hands.",
    resolve=this_town_aint_big_enough_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER},
                custom_filter=_otj_nonland_permanent_filter,
            ),
            count=2,
            count_type='up_to',
            label="up to two target nonland permanents",
        ),
    ],
)


THREE_STEPS_AHEAD = make_instant(
    name="Three Steps Ahead",
    mana_cost="{U}",
    colors={Color.BLUE},
    text=(
        "Spree (Choose one or more additional costs.)\n"
        "+ {1} — Until end of turn, target creature you control gets +1/+1 "
        "and has flash, hexproof, and ward {2}.\n"
        "+ {2} — Draw three cards.\n"
        "+ {3} — Create a copy of this spell. You may choose new targets for "
        "the copy."
    ),
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_THREE_STEPS_AHEAD_MODES),
    resolve=make_spree_resolve(_THREE_STEPS_AHEAD_MODES),
)

VISAGE_BANDIT = make_creature(
    name="Visage Bandit",
    power=2, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Shapeshifter"},
    text="You may have this creature enter as a copy of a creature you control, except it's a Shapeshifter Rogue in addition to its other types.\nPlot {2}{U} (You may pay {2}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=visage_bandit_setup,
)
# Phase 5b: register Plot {2}{U} as a hand-zone activated ability.
VISAGE_BANDIT.setup_in_hand = make_plot_setup(plot_cost="{2}{U}")

AMBUSH_GIGAPEDE = make_creature(
    name="Ambush Gigapede",
    power=6, toughness=2,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Flash\nWhen this creature enters, target creature an opponent controls gets -2/-2 until end of turn.",
    setup_interceptors=ambush_gigapede_setup,
)

BINDING_NEGOTIATION = make_sorcery(
    name="Binding Negotiation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a face-up exiled card they own into their graveyard.",
)

BLACKSNAG_BUZZARD = make_creature(
    name="Blacksnag Buzzard",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bird"},
    text="Flying\nThis creature enters with a +1/+1 counter on it if a creature died this turn.\nPlot {1}{B} (You may pay {1}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=blacksnag_buzzard_setup,
)
# Phase 5b: register Plot {1}{B} as a hand-zone activated ability.
BLACKSNAG_BUZZARD.setup_in_hand = make_plot_setup(plot_cost="{1}{B}")

BLOOD_HUSTLER = make_creature(
    name="Blood Hustler",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Whenever you commit a crime, put a +1/+1 counter on this creature. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\n{3}{B}: Target opponent loses 1 life and you gain 1 life.",
    setup_interceptors=blood_hustler_setup,
)

BONEYARD_DESECRATOR = make_creature(
    name="Boneyard Desecrator",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Mercenary", "Zombie"},
    text="Menace\n{1}{B}, Sacrifice another creature: Put a +1/+1 counter on this creature. If an outlaw was sacrificed this way, create a Treasure token. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
    setup_interceptors=boneyard_desecrator_setup,
)

CAUSTIC_BRONCO = make_creature(
    name="Caustic Bronco",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horse", "Mount", "Snake"},
    text="Whenever this creature attacks, reveal the top card of your library and put it into your hand. You lose life equal to that card's mana value if this creature isn't saddled. Otherwise, each opponent loses that much life.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=caustic_bronco_setup,
)

# =============================================================================
# CONSUMING ASHES - Exile creature + conditional surveil
# =============================================================================

def _consuming_ashes_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Consuming Ashes after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Calculate mana value
    mana_value = 0
    mana_cost = target.characteristics.mana_cost or ""
    for char in mana_cost:
        if char.isdigit():
            mana_value += int(char)
        elif char in 'WUBRGC':
            mana_value += 1

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'to_zone': 'exile',
            'to_zone_type': ZoneType.EXILE,
            'reason': 'exiled'
        },
        source=choice.source_id
    )]

    # Surveil 2 if mana value 3 or less
    if mana_value <= 3:
        events.append(Event(
            type=EventType.SURVEIL,
            payload={'player': controller, 'amount': 2},
            source=choice.source_id
        ))

    return events


def consuming_ashes_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Consuming Ashes (Phase 5b): Exile creature + conditional surveil-2."""
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _otj_spell_caster_id(state)
    events: list[Event] = []
    triggered_surveil = False
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
        # Check mana value <= 3
        try:
            mv = int(obj.card_def.mana_cost.replace('{', '').replace('}', '').replace('X', '0').replace('W', '1').replace('U', '1').replace('B', '1').replace('R', '1').replace('G', '1').replace('C', '1')) if obj.card_def and obj.card_def.mana_cost else 0
        except (ValueError, AttributeError):
            mv = 0
        if mv <= 3:
            triggered_surveil = True
    if triggered_surveil and caster is not None:
        events.append(Event(
            type=EventType.SURVEIL,
            payload={'player': caster, 'amount': 2},
            source=source_id,
        ))
    return events


CONSUMING_ASHES = make_instant(
    name="Consuming Ashes",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature. If it had mana value 3 or less, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    resolve=consuming_ashes_resolve,
    target_requirements=[target_creature(count=1)],
)

CORRUPTED_CONVICTION = make_instant(
    name="Corrupted Conviction",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards.",
    resolve=corrupted_conviction_resolve,
)

# =============================================================================
# DESERT'S DUE - Scaled debuff based on Deserts
# =============================================================================

def _deserts_due_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Desert's Due after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    # Count Deserts
    desert_count = 0
    for obj in state.objects.values():
        if obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.LAND in obj.characteristics.types:
                if 'Desert' in obj.characteristics.subtypes:
                    desert_count += 1

    # Base -2/-2 plus -1/-1 per Desert
    total_mod = -2 - desert_count

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'pump',
            'target_id': target_id,
            'power_mod': total_mod,
            'toughness_mod': total_mod,
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def deserts_due_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Desert's Due (Phase 5b): -2/-2 (+ extra -1/-1 per Desert) EOT."""
    caster = _otj_spell_caster_id(state)
    desert_count = 0
    if caster is not None:
        for obj in state.objects.values():
            if (obj.controller == caster and obj.zone == ZoneType.BATTLEFIELD and
                    'Desert' in obj.characteristics.subtypes):
                desert_count += 1
    total_mod = -2 - desert_count
    return _otj_pump_targets(total_mod, total_mod)(targets, state)


DESERTS_DUE = make_instant(
    name="Desert's Due",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. It gets an additional -1/-1 until end of turn for each Desert you control.",
    resolve=deserts_due_resolve,
    target_requirements=[target_creature(count=1)],
)

DESPERATE_BLOODSEEKER = make_creature(
    name="Desperate Bloodseeker",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Lifelink\nWhen this creature enters, target player mills two cards. (They put the top two cards of their library into their graveyard.)",
    setup_interceptors=desperate_bloodseeker_setup,
)

# =============================================================================
# FAKE YOUR OWN DEATH - Combat trick + death trigger
# =============================================================================

def fake_your_own_death_resolve(targets: list, state: GameState) -> list[Event]:
    """Fake Your Own Death (Phase 5b): targets[0][0] is the creature buffed."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Fake Your Own Death":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "fake_your_own_death_spell"

    if not targets or not targets[0]:
        return []
    tid, _ = normalize_target(targets[0][0], state)
    target = state.objects.get(tid)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': tid,
                'power_mod': 2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=spell_id, controller=caster_id,
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_death_trigger',
                'target_id': tid,
                'trigger': 'return_and_treasure',
                'duration': 'end_of_turn',
            },
            source=spell_id, controller=caster_id,
        ),
    ]


FAKE_YOUR_OWN_DEATH = make_instant(
    name="Fake Your Own Death",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control and you create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    resolve=fake_your_own_death_resolve,
    target_requirements=[target_creature(count=1)],
)

FORSAKEN_MINER = make_creature(
    name="Forsaken Miner",
    power=2, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    text="This creature can't block.\nWhenever you commit a crime, you may pay {B}. If you do, return this card from your graveyard to the battlefield. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=forsaken_miner_setup,
)

GISA_THE_HELLRAISER = make_creature(
    name="Gisa, the Hellraiser",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward—{2}, Pay 2 life.\nSkeletons and Zombies you control get +1/+1 and have menace.\nWhenever you commit a crime, create two tapped 2/2 blue and black Zombie Rogue creature tokens. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=gisa_the_hellraiser_setup,
)

HOLLOW_MARAUDER = make_creature(
    name="Hollow Marauder",
    power=4, toughness=2,
    mana_cost="{6}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Specter"},
    text="This spell costs {1} less to cast for each creature card in your graveyard.\nFlying\nWhen this creature enters, any number of target opponents each discard a card. For each of those opponents who didn't discard a card with mana value 4 or greater, draw a card.",
    setup_interceptors=hollow_marauder_setup,
)

INSATIABLE_AVARICE = make_sorcery(
    name="Insatiable Avarice",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Search your library for a card, then shuffle and put that card on top.\n+ {B}{B} — Target player draws three cards and loses 3 life.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_INSATIABLE_AVARICE_MODES),
    resolve=make_spree_resolve(_INSATIABLE_AVARICE_MODES),
)

KAERVEK_THE_PUNISHER = make_creature(
    name="Kaervek, the Punisher",
    power=3, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, exile up to one target black card from your graveyard and copy it. You may cast the copy. If you do, you lose 2 life. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime. Copies of permanent spells become tokens.)",
    setup_interceptors=kaervek_the_punisher_setup,
)

LIVELY_DIRGE = make_sorcery(
    name="Lively Dirge",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a card, put it into your graveyard, then shuffle.\n+ {2} — Return up to two creature cards with total mana value 4 or less from your graveyard to the battlefield.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_LIVELY_DIRGE_MODES),
    resolve=make_spree_resolve(_LIVELY_DIRGE_MODES),
)

MOURNERS_SURPRISE = make_sorcery(
    name="Mourner's Surprise",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return up to one target creature card from your graveyard to your hand. Create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

# =============================================================================
# NEUTRALIZE THE GUARDS - Mass debuff to opponent's creatures + surveil
# =============================================================================

def neutralize_the_guards_resolve(targets: list, state: GameState) -> list[Event]:
    """Neutralize the Guards (Phase 5b): targets[0][0] is the target opponent."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Neutralize the Guards":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "neutralize_the_guards_spell"

    if not targets or not targets[0]:
        return []
    target_player, _ = normalize_target(targets[0][0], state)
    events: list[Event] = []
    for obj in state.objects.values():
        if obj.controller == target_player and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                events.append(Event(
                    type=EventType.TEMPORARY_EFFECT,
                    payload={
                        'effect': 'pump',
                        'target_id': obj.id,
                        'power_mod': -1, 'toughness_mod': -1,
                        'duration': 'end_of_turn',
                    },
                    source=spell_id, controller=caster_id,
                ))
    events.append(Event(
        type=EventType.SURVEIL,
        payload={'player': caster_id, 'amount': 2},
        source=spell_id, controller=caster_id,
    ))
    return events


NEUTRALIZE_THE_GUARDS = make_instant(
    name="Neutralize the Guards",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Creatures target opponent controls get -1/-1 until end of turn. Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    resolve=neutralize_the_guards_resolve,
    target_requirements=[target_player(controller='opponent')],
)

NEZUMI_LINKBREAKER = make_creature(
    name="Nezumi Linkbreaker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Warlock"},
    text="When this creature dies, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=nezumi_linkbreaker_setup,
)

OVERZEALOUS_MUSCLE = make_creature(
    name="Overzealous Muscle",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Mercenary", "Ogre"},
    text="Whenever you commit a crime during your turn, this creature gains indestructible until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime. Damage and effects that say \"destroy\" don't destroy a creature with indestructible.)",
    setup_interceptors=overzealous_muscle_setup,
)

PITILESS_CARNAGE = make_sorcery(
    name="Pitiless Carnage",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Sacrifice any number of permanents you control, then draw that many cards.\nPlot {1}{B}{B} (You may pay {1}{B}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)
# Phase 5b: register Plot {1}{B}{B} as a hand-zone activated ability.
PITILESS_CARNAGE.setup_in_hand = make_plot_setup(plot_cost="{1}{B}{B}")

RAKISH_CREW = make_enchantment(
    name="Rakish Crew",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever an outlaw you control dies, each opponent loses 1 life and you gain 1 life. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
    setup_interceptors=rakish_crew_setup,
)

RATTLEBACK_APOTHECARY = make_creature(
    name="Rattleback Apothecary",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Gorgon", "Warlock"},
    text="Deathtouch\nWhenever you commit a crime, target creature you control gains your choice of menace or lifelink until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=rattleback_apothecary_setup,
)

RAVEN_OF_FELL_OMENS = make_creature(
    name="Raven of Fell Omens",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bird"},
    text="Flying\nWhenever you commit a crime, each opponent loses 1 life and you gain 1 life. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=raven_of_fell_omens_setup,
)

RICTUS_ROBBER = make_creature(
    name="Rictus Robber",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Zombie"},
    text="When this creature enters, if a creature died this turn, create a 2/2 blue and black Zombie Rogue creature token.\nPlot {2}{B} (You may pay {2}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=rictus_robber_setup,
)
# Phase 5b: register Plot {2}{B} as a hand-zone activated ability.
RICTUS_ROBBER.setup_in_hand = make_plot_setup(plot_cost="{2}{B}")

ROOFTOP_ASSASSIN = make_creature(
    name="Rooftop Assassin",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Vampire"},
    text="Flash\nFlying, lifelink\nWhen this creature enters, destroy target creature an opponent controls that was dealt damage this turn.",
    setup_interceptors=rooftop_assassin_setup,
)

RUSH_OF_DREAD = make_sorcery(
    name="Rush of Dread",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Target opponent sacrifices half the creatures they control of their choice, rounded up.\n+ {2} — Target opponent discards half the cards in their hand, rounded up.\n+ {2} — Target opponent loses half their life, rounded up.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_RUSH_OF_DREAD_MODES),
    resolve=make_spree_resolve(_RUSH_OF_DREAD_MODES),
)

SERVANT_OF_THE_STINGER = make_creature(
    name="Servant of the Stinger",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Deathtouch\nWhenever this creature deals combat damage to a player, if you've committed a crime this turn, you may sacrifice this creature. If you do, search your library for a card, put it into your hand, then shuffle. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=servant_of_the_stinger_setup,
)

def _shoot_the_sheriff_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Shoot the Sheriff after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Verify target is still valid (on battlefield and not an outlaw)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid

    if CardType.CREATURE not in target.characteristics.types:
        return []  # Not a creature

    # Check if target is now an outlaw (subtypes may have changed)
    outlaw_types = {'Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock'}
    subtypes = target.characteristics.subtypes or set()
    if subtypes & outlaw_types:
        return []  # Target is now an outlaw, spell fizzles

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def shoot_the_sheriff_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Shoot the Sheriff (Phase 5b): Destroy target non-outlaw creature."""
    return _otj_destroy_targets()(targets, state)


def _non_outlaw_creature_filter(obj: GameObject, state: GameState) -> bool:
    """Custom filter: creature that's not an outlaw type."""
    if CardType.CREATURE not in obj.characteristics.types:
        return False
    return not (obj.characteristics.subtypes or set()) & OUTLAW_TYPES


SHOOT_THE_SHERIFF = make_instant(
    name="Shoot the Sheriff",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target non-outlaw creature. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. Everyone else is fair game.)",
    resolve=shoot_the_sheriff_resolve,
    target_requirements=[
        TargetRequirement(
            filter=creature_filter(custom_filter=_non_outlaw_creature_filter),
            count=1,
            label="target non-outlaw creature",
        ),
    ],
)

# =============================================================================
# SKULDUGGERY - Two-target pump/debuff
# =============================================================================

def _skulduggery_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Skulduggery after target selection."""
    if len(selected) < 2:
        return []

    your_creature = selected[0]
    opponent_creature = selected[1]

    events = []

    # Your creature gets +1/+1
    your_obj = state.objects.get(your_creature)
    if your_obj and your_obj.zone == ZoneType.BATTLEFIELD:
        events.append(Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': your_creature,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ))

    # Opponent's creature gets -1/-1
    opp_obj = state.objects.get(opponent_creature)
    if opp_obj and opp_obj.zone == ZoneType.BATTLEFIELD:
        events.append(Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': opponent_creature,
                'power_mod': -1,
                'toughness_mod': -1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ))

    return events


def skulduggery_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Skulduggery (Phase 5b): +1/+1 to your creature, -1/-1 to theirs.

    Two TargetRequirements: targets[0]=your creature, targets[1]=their creature.
    """
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    if targets and len(targets) >= 1 and targets[0]:
        t = targets[0][0]
        cid = t.id if hasattr(t, 'id') else t
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': cid, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=source_id,
        ))
    if targets and len(targets) >= 2 and targets[1]:
        t = targets[1][0]
        cid = t.id if hasattr(t, 'id') else t
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': cid, 'power_mod': -1, 'toughness_mod': -1, 'duration': 'end_of_turn'},
            source=source_id,
        ))
    return events


SKULDUGGERY = make_instant(
    name="Skulduggery",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature you control gets +1/+1 and target creature an opponent controls gets -1/-1.",
    resolve=skulduggery_resolve,
    target_requirements=[
        target_creature(count=1, controller='you'),
        target_creature(count=1, controller='opponent'),
    ],
)

TINYBONES_JOINS_UP = make_enchantment(
    name="Tinybones Joins Up",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When Tinybones Joins Up enters, any number of target players each discard a card.\nWhenever a legendary creature you control enters, any number of target players each mill a card and lose 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=tinybones_joins_up_setup,
)

TINYBONES_THE_PICKPOCKET = make_creature(
    name="Tinybones, the Pickpocket",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell.",
    setup_interceptors=tinybones_the_pickpocket_setup,
)

TREASURE_DREDGER = make_creature(
    name="Treasure Dredger",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{1}, {T}, Pay 1 life: Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

# =============================================================================
# UNFORTUNATE ACCIDENT - Spree removal/token creation
# =============================================================================

def _unfortunate_accident_destroy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Unfortunate Accident destroy mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _unfortunate_accident_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Unfortunate Accident modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 1: Create a Mercenary token (process this first as it doesn't need targeting)
    if 1 in selected_modes:
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller_id,
                'name': 'Mercenary',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Mercenary'},
                'colors': {Color.RED},
                'is_token': True
            },
            source=spell_id
        ))

    # Mode 0: Destroy target creature
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _unfortunate_accident_destroy_execute
            return events  # Process token creation then wait for target

    return events


def unfortunate_accident_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Unfortunate Accident - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {2}{B} — Destroy target creature.
    + {1} — Create a 1/1 red Mercenary creature token.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Unfortunate Accident":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "unfortunate_accident_spell"

    modes = [
        {"index": 0, "text": "Destroy target creature."},
        {"index": 1, "text": "Create a 1/1 red Mercenary creature token."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Unfortunate Accident - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _unfortunate_accident_mode_execute

    return []


# Phase 5b: migrate Unfortunate Accident to SpreeMode pattern (cost-per-mode).
def _unfortunate_accident_destroy(spell, state, targets):
    """Mode 0: destroy target creature."""
    if not targets:
        return []
    target_id = targets[0].id if hasattr(targets[0], "id") else targets[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.CREATURE not in target.characteristics.types:
        return []
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=spell.id,
    )]


def _unfortunate_accident_token(spell, state, targets):
    """Mode 1: create a 1/1 red Mercenary token."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': spell.controller,
            'name': 'Mercenary',
            'power': 1, 'toughness': 1,
            'types': {CardType.CREATURE},
            'subtypes': {'Mercenary'},
            'colors': {Color.RED},
            'is_token': True,
        },
        source=spell.id,
    )]


_UNFORTUNATE_ACCIDENT_MODES = [
    SpreeMode(
        name="Destroy", extra_cost="{2}{B}",
        effect_fn=_unfortunate_accident_destroy,
        target_kind="creature", targets_required=1,
        description="Destroy target creature.",
    ),
    SpreeMode(
        name="Mercenary token", extra_cost="{1}",
        effect_fn=_unfortunate_accident_token,
        description="Create a 1/1 red Mercenary creature token.",
    ),
]


UNFORTUNATE_ACCIDENT = make_instant(
    name="Unfortunate Accident",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {2}{B} — Destroy target creature.\n+ {1} — Create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_UNFORTUNATE_ACCIDENT_MODES),
    resolve=make_spree_resolve(_UNFORTUNATE_ACCIDENT_MODES),
)

UNSCRUPULOUS_CONTRACTOR = make_creature(
    name="Unscrupulous Contractor",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="When this creature enters, you may sacrifice a creature. When you do, target player draws two cards and loses 2 life.\nPlot {2}{B} (You may pay {2}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=unscrupulous_contractor_setup,
)
# Phase 5b: register Plot {2}{B} as a hand-zone activated ability.
UNSCRUPULOUS_CONTRACTOR.setup_in_hand = make_plot_setup(plot_cost="{2}{B}")

VADMIR_NEW_BLOOD = make_creature(
    name="Vadmir, New Blood",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, put a +1/+1 counter on Vadmir. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nAs long as Vadmir has four or more +1/+1 counters on it, it has menace and lifelink.",
    setup_interceptors=vadmir_new_blood_setup,
)

VAULT_PLUNDERER = make_creature(
    name="Vault Plunderer",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, target player draws a card and loses 1 life.",
    setup_interceptors=vault_plunderer_setup,
)

BRIMSTONE_ROUNDUP = make_enchantment(
    name="Brimstone Roundup",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever you cast your second spell each turn, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=brimstone_roundup_setup,
)

CALAMITY_GALLOPING_INFERNO = make_creature(
    name="Calamity, Galloping Inferno",
    power=4, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Horse", "Mount"},
    supertypes={"Legendary"},
    text="Haste\nWhenever Calamity attacks while saddled, choose a nonlegendary creature that saddled it this turn and create a tapped and attacking token that's a copy of it. Sacrifice that token at the beginning of the next end step. Repeat this process once.\nSaddle 1",
    setup_interceptors=calamity_galloping_inferno_setup,
)

# =============================================================================
# CAUGHT IN THE CROSSFIRE - Spree mass damage to outlaws/non-outlaws
# =============================================================================

# =============================================================================
# CAUGHT IN THE CROSSFIRE - Spree (W12 cost-per-mode wired)
# =============================================================================
# Spree (Choose one or more additional costs.)
# + {1} — Caught in the Crossfire deals 2 damage to each outlaw creature.
# + {1} — Caught in the Crossfire deals 2 damage to each non-outlaw creature.

_CITC_OUTLAW_TYPES = {'Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock'}


def _caught_in_the_crossfire_mode_outlaws(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: 2 damage to each outlaw creature."""
    spell_id = spell.id if spell else None
    events: list[Event] = []
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        subtypes = obj.characteristics.subtypes or set()
        if subtypes & _CITC_OUTLAW_TYPES:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': obj.id, 'amount': 2, 'source': spell_id, 'is_combat': False},
                source=spell_id,
            ))
    return events


def _caught_in_the_crossfire_mode_non_outlaws(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: 2 damage to each non-outlaw creature."""
    spell_id = spell.id if spell else None
    events: list[Event] = []
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        subtypes = obj.characteristics.subtypes or set()
        if not (subtypes & _CITC_OUTLAW_TYPES):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': obj.id, 'amount': 2, 'source': spell_id, 'is_combat': False},
                source=spell_id,
            ))
    return events


_CAUGHT_IN_THE_CROSSFIRE_MODES = [
    SpreeMode(
        name="Outlaws",
        extra_cost="{1}",
        effect_fn=_caught_in_the_crossfire_mode_outlaws,
        description="Deals 2 damage to each outlaw creature.",
    ),
    SpreeMode(
        name="Non-outlaws",
        extra_cost="{1}",
        effect_fn=_caught_in_the_crossfire_mode_non_outlaws,
        description="Deals 2 damage to each non-outlaw creature.",
    ),
]


CAUGHT_IN_THE_CROSSFIRE = make_instant(
    name="Caught in the Crossfire",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Caught in the Crossfire deals 2 damage to each outlaw creature. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\n+ {1} — Caught in the Crossfire deals 2 damage to each non-outlaw creature.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_CAUGHT_IN_THE_CROSSFIRE_MODES),
    resolve=make_spree_resolve(_CAUGHT_IN_THE_CROSSFIRE_MODES),
)

CUNNING_COYOTE = make_creature(
    name="Cunning Coyote",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Coyote"},
    text="Haste\nWhen this creature enters, another target creature you control gets +1/+1 and gains haste until end of turn.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=cunning_coyote_setup,
)
# Phase 5b: register Plot {1}{R} as a hand-zone activated ability.
CUNNING_COYOTE.setup_in_hand = make_plot_setup(plot_cost="{1}{R}")

DEADEYE_DUELIST = make_creature(
    name="Deadeye Duelist",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="Reach\n{1}, {T}: This creature deals 1 damage to target opponent.",
    setup_interceptors=deadeye_duelist_setup,
)

DEMONIC_RUCKUS = make_enchantment(
    name="Demonic Ruckus",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Enchant creature\nEnchanted creature gets +1/+1 and has menace and trample.\nWhen this Aura is put into a graveyard from the battlefield, draw a card.\nPlot {R} (You may pay {R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    subtypes={"Aura"},
    setup_interceptors=demonic_ruckus_setup,
)
# Phase 5b: register Plot {R} as a hand-zone activated ability.
DEMONIC_RUCKUS.setup_in_hand = make_plot_setup(plot_cost="{R}")

DISCERNING_PEDDLER = make_creature(
    name="Discerning Peddler",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, you may discard a card. If you do, draw a card.",
    setup_interceptors=discerning_peddler_setup,
)

# =============================================================================
# EXPLOSIVE DERAILMENT - Spree damage/artifact destruction
# =============================================================================

def _explosive_derailment_damage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Explosive Derailment damage mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': 4,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def _explosive_derailment_artifact_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Explosive Derailment artifact destruction mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.ARTIFACT not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _explosive_derailment_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Explosive Derailment modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Deal 4 damage to target creature
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to deal 4 damage to",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _explosive_derailment_damage_execute
            return events

    # Mode 1: Destroy target artifact
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.ARTIFACT in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an artifact to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _explosive_derailment_artifact_execute

    return events


def explosive_derailment_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Explosive Derailment - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {2} — Explosive Derailment deals 4 damage to target creature.
    + {2} — Destroy target artifact.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Explosive Derailment":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "explosive_derailment_spell"

    modes = [
        {"index": 0, "text": "Deal 4 damage to target creature."},
        {"index": 1, "text": "Destroy target artifact."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Explosive Derailment - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _explosive_derailment_mode_execute

    return []


# =============================================================================
# EXPLOSIVE DERAILMENT - Spree (W12 cost-per-mode wired)
# =============================================================================
# Spree (Choose one or more additional costs.)
# + {2} — Explosive Derailment deals 4 damage to target creature.
# + {2} — Destroy target artifact.
#
# Per-mode targets are gathered via chained PendingChoices at resolve time.

def _explosive_derailment_damage(spell, state: GameState, targets) -> list[Event]:
    """Mode 0: 4 damage to target creature."""
    if not spell or not targets:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': targets[0], 'amount': 4, 'source': spell.id, 'is_combat': False},
        source=spell.id,
    )]


def _explosive_derailment_destroy_artifact(spell, state: GameState, targets) -> list[Event]:
    """Mode 1: destroy target artifact."""
    if not spell or not targets:
        return []
    return [Event(type=EventType.OBJECT_DESTROYED,
                  payload={'object_id': targets[0]}, source=spell.id)]


_EXPLOSIVE_DERAILMENT_MODES = [
    SpreeMode(name="Damage", extra_cost="{2}",
              effect_fn=_explosive_derailment_damage, target_kind="creature",
              targets_required=1,
              description="Explosive Derailment deals 4 damage to target creature."),
    SpreeMode(name="Destroy artifact", extra_cost="{2}",
              effect_fn=_explosive_derailment_destroy_artifact, target_kind="artifact",
              targets_required=1,
              description="Destroy target artifact."),
]


EXPLOSIVE_DERAILMENT = make_instant(
    name="Explosive Derailment",
    mana_cost="{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Explosive Derailment deals 4 damage to target creature.\n+ {2} — Destroy target artifact.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_EXPLOSIVE_DERAILMENT_MODES),
    resolve=make_spree_resolve(_EXPLOSIVE_DERAILMENT_MODES),
)

FEROCIFICATION = make_enchantment(
    name="Ferocification",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of combat on your turn, choose one —\n• Target creature you control gets +2/+0 until end of turn.\n• Target creature you control gains menace and haste until end of turn.",
    setup_interceptors=ferocification_setup,
)

GILA_COURSER = make_creature(
    name="Gila Courser",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Mount"},
    text="Whenever this creature attacks while saddled, exile the top card of your library. Until the end of your next turn, you may play that card.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=gila_courser_setup,
)

GREAT_TRAIN_HEIST = make_instant(
    name="Great Train Heist",
    mana_cost="{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {2}{R} — Untap all creatures you control. If it's your combat phase, there is an additional combat phase after this phase.\n+ {2} — Creatures you control get +1/+0 and gain first strike until end of turn.\n+ {R} — Choose target opponent. Whenever a creature you control deals combat damage to that player this turn, create a tapped Treasure token.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_GREAT_TRAIN_HEIST_MODES),
    resolve=make_spree_resolve(_GREAT_TRAIN_HEIST_MODES),
)

# =============================================================================
# HELL TO PAY - X damage with treasure creation
# =============================================================================

def _hell_to_pay_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hell to Pay after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    x_value = choice.callback_data.get('x_value', 0)
    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    # Calculate toughness to determine excess damage
    from src.engine import get_toughness
    toughness = get_toughness(target, state)

    events = [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': x_value,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]

    # Calculate excess damage (damage beyond toughness)
    excess = max(0, x_value - toughness)
    if excess > 0:
        for _ in range(excess):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': controller,
                    'name': 'Treasure',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'is_token': True,
                    'enters_tapped': True
                },
                source=choice.source_id
            ))

    return events


def hell_to_pay_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Hell to Pay (Phase 5b): X damage to creature (treasure-on-excess is engine gap)."""
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    x_value = getattr(spell, 'x_value', 0) if spell else 0
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': t.id,
                'amount': x_value,
                'source': source_id,
                'is_combat': False,
                'is_player': False,
            },
            source=source_id,
        ))
    return events


HELL_TO_PAY = make_sorcery(
    name="Hell to Pay",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Hell to Pay deals X damage to target creature. Create a number of tapped Treasure tokens equal to the amount of excess damage dealt to that creature this way.",
    resolve=hell_to_pay_resolve,
    target_requirements=[target_creature(count=1)],
)

HELLSPUR_BRUTE = make_creature(
    name="Hellspur Brute",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Mercenary", "Minotaur"},
    text="Affinity for outlaws (This spell costs {1} less to cast for each Assassin, Mercenary, Pirate, Rogue, and/or Warlock you control.)\nTrample",
    setup_interceptors=hellspur_brute_setup,
)

HELLSPUR_POSSE_BOSS = make_creature(
    name="Hellspur Posse Boss",
    power=2, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Rogue"},
    text="Other outlaws you control have haste. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhen this creature enters, create two 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=hellspur_posse_boss_setup,
)

HIGHWAY_ROBBERY = make_sorcery(
    name="Highway Robbery",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="You may discard a card or sacrifice a land. If you do, draw two cards.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)
# Phase 5b: register Plot {1}{R} as a hand-zone activated ability.
HIGHWAY_ROBBERY.setup_in_hand = make_plot_setup(plot_cost="{1}{R}")

IRASCIBLE_WOLVERINE = make_creature(
    name="Irascible Wolverine",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Wolverine"},
    text="When this creature enters, exile the top card of your library. Until end of turn, you may play that card.\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=irascible_wolverine_setup,
)
# Phase 5b: register Plot {2}{R} as a hand-zone activated ability.
IRASCIBLE_WOLVERINE.setup_in_hand = make_plot_setup(plot_cost="{2}{R}")

IRONFIST_PULVERIZER = make_creature(
    name="Iron-Fist Pulverizer",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Reach\nWhenever you cast your second spell each turn, this creature deals 2 damage to target opponent. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    setup_interceptors=ironfist_pulverizer_setup,
)

LONGHORN_SHARPSHOOTER = make_creature(
    name="Longhorn Sharpshooter",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Rogue"},
    text="Reach\nWhen this card becomes plotted, it deals 2 damage to any target.\nPlot {3}{R} (You may pay {3}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=longhorn_sharpshooter_setup,
)
# Phase 5b: register Plot {3}{R} as a hand-zone activated ability. The
# existing setup_interceptors wires the "When this card becomes plotted,
# deals 2 damage to any target" trigger; this setup_in_hand adds the
# Plot activation that fires the PLOT_BECOMES_PLOTTED event.
LONGHORN_SHARPSHOOTER.setup_in_hand = make_plot_setup(plot_cost="{3}{R}")

MAGDA_THE_HOARDMASTER = make_creature(
    name="Magda, the Hoardmaster",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Dwarf"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, create a tapped Treasure token. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nSacrifice three Treasures: Create a 4/4 red Scorpion Dragon creature token with flying and haste. Activate only as a sorcery.",
    setup_interceptors=magda_the_hoardmaster_setup,
)

MAGEBANE_LIZARD = make_creature(
    name="Magebane Lizard",
    power=1, toughness=4,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Whenever a player casts a noncreature spell, this creature deals damage to that player equal to the number of noncreature spells they've cast this turn.",
    setup_interceptors=magebane_lizard_setup,
)

MINE_RAIDER = make_creature(
    name="Mine Raider",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Trample\nWhen this creature enters, if you control another outlaw, create a Treasure token. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=mine_raider_setup,
)

OUTLAWS_FURY = make_instant(
    name="Outlaws' Fury",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn. If you control an outlaw, exile the top card of your library. Until the end of your next turn, you may play that card. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

PRICKLY_PAIR = make_creature(
    name="Prickly Pair",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Mercenary", "Plant"},
    text="When this creature enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=prickly_pair_setup,
)

# =============================================================================
# QUICK DRAW - Combat trick with ability manipulation
# =============================================================================

def _quick_draw_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Quick Draw after target selection."""
    if len(selected) < 2:
        return []

    creature_target = selected[0]
    opponent_target = selected[1]

    creature = state.objects.get(creature_target)
    if not creature or creature.zone != ZoneType.BATTLEFIELD:
        return []

    events = [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': creature_target,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': creature_target,
                'keywords': ['first_strike'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]

    # Remove first strike and double strike from opponent's creatures
    for obj in state.objects.values():
        if obj.controller == opponent_target and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                events.append(Event(
                    type=EventType.TEMPORARY_EFFECT,
                    payload={
                        'effect': 'remove_keywords',
                        'target_id': obj.id,
                        'keywords': ['first_strike', 'double_strike'],
                        'duration': 'end_of_turn'
                    },
                    source=choice.source_id
                ))

    return events


def quick_draw_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Quick Draw (Phase 5b): +1/+1 first-strike to creature you control + remove FS/DS from opponent creatures.

    Two TargetRequirements: targets[0]=your creature, targets[1]=opponent.
    """
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    # Boost your creature.
    if targets and len(targets) >= 1 and targets[0]:
        t = targets[0][0]
        cid = t.id if hasattr(t, 'id') else t
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': cid, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=source_id,
        ))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': cid, 'keyword': 'first_strike', 'duration': 'end_of_turn'},
            source=source_id,
        ))
    # Strip FS/DS from creatures controlled by chosen opponent.
    if targets and len(targets) >= 2 and targets[1]:
        opp = targets[1][0]
        opp_id = opp.id if hasattr(opp, 'id') else opp
        for obj in state.objects.values():
            if (obj.controller == opp_id and obj.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in obj.characteristics.types):
                for kw in ('first_strike', 'double_strike'):
                    events.append(Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={
                            'object_id': obj.id,
                            'keyword': kw,
                            'duration': 'end_of_turn',
                            'remove': True,
                        },
                        source=source_id,
                    ))
    return events


QUICK_DRAW = make_instant(
    name="Quick Draw",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +1/+1 and gains first strike until end of turn. Creatures target opponent controls lose first strike and double strike until end of turn.",
    resolve=quick_draw_resolve,
    target_requirements=[
        target_creature(count=1, controller='you'),
        target_player(controller='opponent'),
    ],
)

QUILLED_CHARGER = make_creature(
    name="Quilled Charger",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Mount", "Porcupine"},
    text="Whenever this creature attacks while saddled, it gets +1/+2 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=quilled_charger_setup,
)

RECKLESS_LACKEY = make_creature(
    name="Reckless Lackey",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="First strike, haste\n{2}{R}, Sacrifice this creature: Draw a card and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=reckless_lackey_setup,
)

RESILIENT_ROADRUNNER = make_creature(
    name="Resilient Roadrunner",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bird"},
    text="Haste, protection from Coyotes\n{3}: This creature can't be blocked this turn except by creatures with haste.",
    setup_interceptors=resilient_roadrunner_setup,
)

RETURN_THE_FAVOR = make_instant(
    name="Return the Favor",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text=(
        "Copy target instant or sorcery spell you don't control. You may "
        "choose new targets for the copy."
    ),
    resolve=return_the_favor_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.INSTANT, CardType.SORCERY},
                zones=[ZoneType.STACK],
                controller='opponent',
            ),
            count=1,
            label="target instant or sorcery spell you don't control",
        ),
    ],
)

RODEO_PYROMANCERS = make_creature(
    name="Rodeo Pyromancers",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mercenary"},
    text="Whenever you cast your first spell each turn, add {R}{R}.",
    setup_interceptors=rodeo_pyromancers_setup,
)

SCALESTORM_SUMMONER = make_creature(
    name="Scalestorm Summoner",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warlock"},
    text="Whenever this creature attacks, create a 3/1 red Dinosaur creature token if you control a creature with power 4 or greater.",
    setup_interceptors=scalestorm_summoner_setup,
)

# =============================================================================
# SCORCHING SHOT - Simple damage spell
# =============================================================================

def _scorching_shot_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Scorching Shot after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': 5,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def scorching_shot_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Scorching Shot (Phase 5b): 5 damage to creature."""
    return _otj_damage_to_targets(5)(targets, state)


SCORCHING_SHOT = make_sorcery(
    name="Scorching Shot",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Scorching Shot deals 5 damage to target creature.",
    resolve=scorching_shot_resolve,
    target_requirements=[target_creature(count=1)],
)

SLICKSHOT_SHOWOFF = make_creature(
    name="Slickshot Show-Off",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bird", "Wizard"},
    text="Flying, haste\nWhenever you cast a noncreature spell, this creature gets +2/+0 until end of turn.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=slickshot_showoff_setup,
)
# Phase 5b: register Plot {1}{R} as a hand-zone activated ability.
SLICKSHOT_SHOWOFF.setup_in_hand = make_plot_setup(plot_cost="{1}{R}")

STINGERBACK_TERROR = make_creature(
    name="Stingerback Terror",
    power=7, toughness=7,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon", "Scorpion"},
    text="Flying, trample\nThis creature gets -1/-1 for each card in your hand.\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=stingerback_terror_setup,
)
# Phase 5b: register Plot {2}{R} as a hand-zone activated ability.
STINGERBACK_TERROR.setup_in_hand = make_plot_setup(plot_cost="{2}{R}")

# =============================================================================
# TAKE FOR A RIDE - Threaten effect
# =============================================================================

def take_for_a_ride_resolve(targets: list, state: GameState) -> list[Event]:
    """Take for a Ride (Phase 5b): targets[0][0] is the creature to threaten."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Take for a Ride":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "take_for_a_ride_spell"
    if not targets or not targets[0]:
        return []
    tid, _ = normalize_target(targets[0][0], state)
    target = state.objects.get(tid)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'gain_control',
                'target_id': tid,
                'new_controller': caster_id,
                'duration': 'end_of_turn',
            },
            source=spell_id, controller=caster_id,
        ),
        Event(
            type=EventType.UNTAP,
            payload={'object_id': tid},
            source=spell_id, controller=caster_id,
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': tid,
                'keywords': ['haste'],
                'duration': 'end_of_turn',
            },
            source=spell_id, controller=caster_id,
        ),
    ]


TAKE_FOR_A_RIDE = make_sorcery(
    name="Take for a Ride",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Take for a Ride has flash as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nGain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.",
    resolve=take_for_a_ride_resolve,
    target_requirements=[target_creature(count=1, controller='opponent')],
)

TERROR_OF_THE_PEAKS = make_creature(
    name="Terror of the Peaks",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nSpells your opponents cast that target this creature cost an additional 3 life to cast.\nWhenever another creature you control enters, this creature deals damage equal to that creature's power to any target.",
    setup_interceptors=terror_of_the_peaks_setup,
)

# =============================================================================
# THUNDER SALVO - Scaled damage based on spells cast
# =============================================================================

def _thunder_salvo_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Thunder Salvo after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    damage = choice.callback_data.get('damage', 2)

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': damage,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def thunder_salvo_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Thunder Salvo (Phase 5b): 2 + other-spells damage to creature."""
    caster = _otj_spell_caster_id(state)
    other_spells = getattr(state, 'spells_cast_this_turn', {}).get(caster, 0)
    damage = 2 + max(0, other_spells - 1)  # -1 because Thunder Salvo itself counts
    return _otj_damage_to_targets(damage)(targets, state)


THUNDER_SALVO = make_instant(
    name="Thunder Salvo",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Thunder Salvo deals X damage to target creature, where X is 2 plus the number of other spells you've cast this turn.",
    resolve=thunder_salvo_resolve,
    target_requirements=[target_creature(count=1)],
)

TRICK_SHOT = make_instant(
    name="Trick Shot",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Trick Shot deals 6 damage to target creature and 2 damage to up to one other target creature token.",
)

ALOE_ALCHEMIST = make_creature(
    name="Aloe Alchemist",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Warlock"},
    text="Trample\nWhen this card becomes plotted, target creature gets +3/+2 and gains trample until end of turn.\nPlot {1}{G} (You may pay {1}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=aloe_alchemist_setup,
)
# Phase 5b: register Plot {1}{G} as a hand-zone activated ability.
ALOE_ALCHEMIST.setup_in_hand = make_plot_setup(plot_cost="{1}{G}")

ANKLE_BITER = make_creature(
    name="Ankle Biter",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Snake"},
    text="Deathtouch",
)

BEASTBOND_OUTCASTER = make_creature(
    name="Beastbond Outcaster",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, if you control a creature with power 4 or greater, draw a card.\nPlot {1}{G} (You may pay {1}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=beastbond_outcaster_setup,
)
# Phase 5b: register Plot {1}{G} as a hand-zone activated ability.
BEASTBOND_OUTCASTER.setup_in_hand = make_plot_setup(plot_cost="{1}{G}")

# =============================================================================
# BETRAYAL AT THE VAULT - One creature damages two others
# =============================================================================

def betrayal_at_the_vault_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Betrayal at the Vault (Phase 5b): targets[0][0] is your creature (damage
    source); targets[1] is the list of 2 other creatures taking damage.
    """
    from src.engine import get_power
    if not targets or len(targets) < 2 or not targets[0] or not targets[1]:
        return []
    own_tid, _ = normalize_target(targets[0][0], state)
    own = state.objects.get(own_tid)
    if not own or own.zone != ZoneType.BATTLEFIELD:
        return []
    power = get_power(own, state)
    events: list[Event] = []
    for entry in targets[1]:
        tid, _ = normalize_target(entry, state)
        if tid == own_tid:
            continue  # "other" target
        obj = state.objects.get(tid)
        if not obj or obj.zone != ZoneType.BATTLEFIELD:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': tid, 'amount': power,
                'source': own_tid, 'is_combat': False,
            },
            source=own_tid,
        ))
    return events


BETRAYAL_AT_THE_VAULT = make_instant(
    name="Betrayal at the Vault",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to each of two other target creatures.",
    resolve=betrayal_at_the_vault_resolve,
    # Phase 5b cross-target: the two "other" targets must differ from the
    # first pick (your damage source). The callable builder excludes the
    # source-creature ID from the legal options for the second requirement.
    target_requirements=[
        target_creature(count=1, controller='you', label="target creature you control"),
        another_target_creature(
            count=2,
            label="two other target creatures",
        ),
    ],
)

BRISTLEPACK_SENTRY = make_creature(
    name="Bristlepack Sentry",
    power=3, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wolf"},
    text="Defender\nAs long as you control a creature with power 4 or greater, this creature can attack as though it didn't have defender.",
    setup_interceptors=bristlepack_sentry_setup,
)

BRISTLY_BILL_SPINE_SOWER = make_creature(
    name="Bristly Bill, Spine Sower",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Plant"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on target creature.\n{3}{G}{G}: Double the number of +1/+1 counters on each creature you control.",
    setup_interceptors=bristly_bill_spine_sower_setup,
)

CACTARANTULA = make_creature(
    name="Cactarantula",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spider"},
    text="This spell costs {1} less to cast if you control a Desert.\nReach\nWhenever this creature becomes the target of a spell or ability an opponent controls, you may draw a card.",
    setup_interceptors=cactarantula_setup,
)

COLOSSAL_RATTLEWURM = make_creature(
    name="Colossal Rattlewurm",
    power=6, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Colossal Rattlewurm has flash as long as you control a Desert.\nTrample\n{1}{G}, Exile this card from your graveyard: Search your library for a Desert card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=colossal_rattlewurm_setup,
)
COLOSSAL_RATTLEWURM.setup_in_graveyard = colossal_rattlewurm_gy_setup

DANCE_OF_THE_TUMBLEWEEDS = make_sorcery(
    name="Dance of the Tumbleweeds",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a basic land card or a Desert card, put it onto the battlefield, then shuffle.\n+ {3} — Create an X/X green Elemental creature token, where X is the number of lands you control.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_DANCE_OF_THE_TUMBLEWEEDS_MODES),
    resolve=make_spree_resolve(_DANCE_OF_THE_TUMBLEWEEDS_MODES),
)

DROVER_GRIZZLY = make_creature(
    name="Drover Grizzly",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Bear", "Mount"},
    text="Whenever this creature attacks while saddled, creatures you control gain trample until end of turn.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=drover_grizzly_setup,
)

FREESTRIDER_COMMANDO = make_creature(
    name="Freestrider Commando",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Mercenary"},
    text="This creature enters with two +1/+1 counters on it if it wasn't cast or no mana was spent to cast it.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=freestrider_commando_setup,
)
# Phase 5b: register Plot {3}{G} as a hand-zone activated ability.
FREESTRIDER_COMMANDO.setup_in_hand = make_plot_setup(plot_cost="{3}{G}")

FREESTRIDER_LOOKOUT = make_creature(
    name="Freestrider Lookout",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Rogue"},
    text="Reach\nWhenever you commit a crime, look at the top five cards of your library. You may put a land card from among them onto the battlefield tapped. Put the rest on the bottom of your library in a random order. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=freestrider_lookout_setup,
)

FULL_STEAM_AHEAD = make_sorcery(
    name="Full Steam Ahead",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Until end of turn, each creature you control gets +2/+2 and gains trample and \"This creature can't be blocked by more than one creature.\"",
    resolve=full_steam_ahead_resolve,
)

GIANT_BEAVER = make_creature(
    name="Giant Beaver",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beaver", "Mount"},
    text="Vigilance\nWhenever this creature attacks while saddled, put a +1/+1 counter on target creature that saddled it this turn.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=giant_beaver_setup,
)

# =============================================================================
# GOLD RUSH - Treasure creation + optional pump
# =============================================================================

def _gold_rush_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Gold Rush after target selection."""
    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = [
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True
            },
            source=choice.source_id
        )
    ]

    # If a target was selected, pump it
    if selected:
        target_id = selected[0]
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            # Count treasures (including the one we just created)
            treasure_count = 1  # The one we're creating
            for obj in state.objects.values():
                if obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
                    if CardType.ARTIFACT in obj.characteristics.types:
                        if 'Treasure' in obj.characteristics.subtypes:
                            treasure_count += 1

            pump = treasure_count * 2
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': target_id,
                    'power_mod': pump,
                    'toughness_mod': pump,
                    'duration': 'end_of_turn',
                },
                source=choice.source_id,
            ))

    return events


def gold_rush_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Gold Rush (Phase 5b): Treasure token + up-to-1 creature gets +2/+2 per Treasure."""
    spell = _otj_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _otj_spell_caster_id(state)
    events: list[Event] = []
    if caster is not None:
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': caster,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True,
            },
            source=source_id,
        ))
    treasure_count = 1  # the new one
    if caster is not None:
        for obj in state.objects.values():
            if (obj.controller == caster and obj.zone == ZoneType.BATTLEFIELD and
                    'Treasure' in obj.characteristics.subtypes):
                treasure_count += 1
    pump = 2 * treasure_count
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': t.id, 'power_mod': pump, 'toughness_mod': pump, 'duration': 'end_of_turn'},
            source=source_id,
        ))
    return events


GOLD_RUSH = make_instant(
    name="Gold Rush",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create a Treasure token. Until end of turn, up to one target creature gets +2/+2 for each Treasure you control.",
    resolve=gold_rush_resolve,
    target_requirements=[
        TargetRequirement(filter=creature_filter(), count=1, count_type='up_to', label="up to one target creature"),
    ],
)

GOLDVEIN_HYDRA = make_creature(
    name="Goldvein Hydra",
    power=0, toughness=0,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="Vigilance, trample, haste\nThis creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a number of tapped Treasure tokens equal to its power.",
    setup_interceptors=goldvein_hydra_setup,
)

HARDBRISTLE_BANDIT = make_creature(
    name="Hardbristle Bandit",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Rogue"},
    text="{T}: Add one mana of any color.\nWhenever you commit a crime, untap this creature. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=hardbristle_bandit_setup,
)

INTREPID_STABLEMASTER = make_creature(
    name="Intrepid Stablemaster",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="Reach\n{T}: Add {G}.\n{T}: Add two mana of any one color. Spend this mana only to cast Mount or Vehicle spells.",
    setup_interceptors=intrepid_stablemaster_setup,
)

MAP_THE_FRONTIER = make_sorcery(
    name="Map the Frontier",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Desert cards, put them onto the battlefield tapped, then shuffle.",
    resolve=map_the_frontier_resolve,
)

ORNERY_TUMBLEWAGG = make_creature(
    name="Ornery Tumblewagg",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Brushwagg", "Mount"},
    text="At the beginning of combat on your turn, put a +1/+1 counter on target creature.\nWhenever this creature attacks while saddled, double the number of +1/+1 counters on target creature.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=ornery_tumblewagg_setup,
)

OUTCASTER_GREENBLADE = make_creature(
    name="Outcaster Greenblade",
    power=1, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mercenary"},
    text="When this creature enters, search your library for a basic land card or a Desert card, reveal it, put it into your hand, then shuffle.\nThis creature gets +1/+1 for each Desert you control.",
    setup_interceptors=outcaster_greenblade_setup,
)

OUTCASTER_TRAILBLAZER = make_creature(
    name="Outcaster Trailblazer",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, add one mana of any color.\nWhenever another creature you control with power 4 or greater enters, draw a card.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=outcaster_trailblazer_setup,
)
# Phase 5b: register Plot {2}{G} as a hand-zone activated ability.
OUTCASTER_TRAILBLAZER.setup_in_hand = make_plot_setup(plot_cost="{2}{G}")

PATIENT_NATURALIST = make_creature(
    name="Patient Naturalist",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When this creature enters, mill three cards. Put a land card from among the milled cards into your hand. If you can't, create a Treasure token. (To mill three cards, put the top three cards of your library into your graveyard.)",
    setup_interceptors=patient_naturalist_setup,
)

RAILWAY_BRAWLER = make_creature(
    name="Railway Brawler",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Warrior"},
    text="Reach, trample\nWhenever another creature you control enters, put X +1/+1 counters on it, where X is its power.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=railway_brawler_setup,
)
# Phase 5b: register Plot {3}{G} as a hand-zone activated ability.
RAILWAY_BRAWLER.setup_in_hand = make_plot_setup(plot_cost="{3}{G}")

RAMBLING_POSSUM = make_creature(
    name="Rambling Possum",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Mount", "Possum"},
    text="Whenever this creature attacks while saddled, it gets +1/+2 until end of turn. Then you may return any number of creatures that saddled it this turn to their owner's hand.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=rambling_possum_setup,
)

RAUCOUS_ENTERTAINER = make_creature(
    name="Raucous Entertainer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bard", "Plant"},
    text="{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn.",
    setup_interceptors=raucous_entertainer_setup,
)

REACH_FOR_THE_SKY = make_enchantment(
    name="Reach for the Sky",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nEnchanted creature gets +3/+2 and has reach.\nWhen this Aura is put into a graveyard from the battlefield, draw a card.",
    subtypes={"Aura"},
    setup_interceptors=reach_for_the_sky_setup,
)

RISE_OF_THE_VARMINTS = make_sorcery(
    name="Rise of the Varmints",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Create X 2/1 green Varmint creature tokens, where X is the number of creature cards in your graveyard.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    resolve=rise_of_the_varmints_resolve,
)
# Phase 5b: register Plot {2}{G} as a hand-zone activated ability.
RISE_OF_THE_VARMINTS.setup_in_hand = make_plot_setup(plot_cost="{2}{G}")

SMUGGLERS_SURPRISE = make_instant(
    name="Smuggler's Surprise",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Mill four cards. You may put up to two creature and/or land cards from among the milled cards into your hand.\n+ {4}{G} — You may put up to two creature cards from your hand onto the battlefield.\n+ {1} — Creatures you control with power 4 or greater gain hexproof and indestructible until end of turn.",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_SMUGGLERS_SURPRISE_MODES),
    resolve=make_spree_resolve(_SMUGGLERS_SURPRISE_MODES),
)

# =============================================================================
# SNAKESKIN VEIL - Protection + counter
# =============================================================================

def _snakeskin_veil_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Snakeskin Veil after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [
        Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': target_id,
                'keywords': ['hexproof'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def snakeskin_veil_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Snakeskin Veil (Phase 5b): +1/+1 counter + hexproof EOT.
    """
    return resolve_chain(
        _otj_counter_targets(amount=1, counter_type='+1/+1'),
        _otj_grant_keywords_to_targets('hexproof'),
    )(targets, state)


SNAKESKIN_VEIL = make_instant(
    name="Snakeskin Veil",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
    resolve=snakeskin_veil_resolve,
    target_requirements=[target_creature(count=1, controller='you')],
)

SPINEWOODS_ARMADILLO = make_creature(
    name="Spinewoods Armadillo",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Armadillo"},
    text="Reach\nWard {3} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {3}.)\n{1}{G}, Discard this card: Search your library for a basic land card or a Desert card, reveal it, put it into your hand, then shuffle. You gain 3 life.",
    setup_interceptors=spinewoods_armadillo_setup,
)

SPINEWOODS_PALADIN = make_creature(
    name="Spinewoods Paladin",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="Trample\nWhen this creature enters, you gain 3 life.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=spinewoods_paladin_setup,
)
# Phase 5b: register Plot {3}{G} as a hand-zone activated ability.
SPINEWOODS_PALADIN.setup_in_hand = make_plot_setup(plot_cost="{3}{G}")

STUBBORN_BURROWFIEND = make_creature(
    name="Stubborn Burrowfiend",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Beast", "Mount"},
    text="Whenever this creature becomes saddled for the first time each turn, mill two cards, then this creature gets +X/+X until end of turn, where X is the number of creature cards in your graveyard.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=stubborn_burrowfiend_setup,
)

# =============================================================================
# THROW FROM THE SADDLE - Pump + fight effect
# =============================================================================

def _throw_from_the_saddle_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Throw from the Saddle after target selection."""
    if len(selected) < 2:
        return []

    your_creature_id = selected[0]
    opponent_creature_id = selected[1]

    your_creature = state.objects.get(your_creature_id)
    opponent_creature = state.objects.get(opponent_creature_id)

    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not opponent_creature or opponent_creature.zone != ZoneType.BATTLEFIELD:
        return []

    events = []

    # Check if it's a Mount
    is_mount = 'Mount' in your_creature.characteristics.subtypes

    if is_mount:
        # Put a +1/+1 counter on it
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': your_creature_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ))
    else:
        # Gets +1/+1 until end of turn
        events.append(Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': your_creature_id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ))

    # Deal damage equal to power to target creature
    from src.engine import get_power
    power = get_power(your_creature, state)
    if is_mount:
        power += 1  # Account for the counter we're adding

    events.append(Event(
        type=EventType.DAMAGE,
        payload={
            'target': opponent_creature_id,
            'amount': power,
            'source': your_creature_id,
            'is_combat': False
        },
        source=choice.source_id
    ))

    return events


def throw_from_the_saddle_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Throw from the Saddle: Target creature you control gets +1/+1 until end of turn.
    Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage equal to its
    power to target creature you don't control.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Throw from the Saddle":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "throw_from_the_saddle_spell"

    # Find your creatures and opponent creatures
    your_creatures = []
    opponent_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                if obj.controller == caster_id:
                    your_creatures.append(obj.id)
                else:
                    opponent_creatures.append(obj.id)

    if not your_creatures or not opponent_creatures:
        return []

    # Combined targeting
    all_targets = your_creatures + opponent_creatures

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=all_targets,
        prompt="Choose your creature to pump, then opponent's creature to damage",
        min_targets=2,
        max_targets=2,
        callback_data={'your_creatures': your_creatures, 'opponent_creatures': opponent_creatures}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _throw_from_the_saddle_execute

    return []


THROW_FROM_THE_SADDLE = make_sorcery(
    name="Throw from the Saddle",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+1 until end of turn. Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage equal to its power to target creature you don't control.",
    resolve=throw_from_the_saddle_resolve,
)


TRASH_THE_TOWN = make_instant(
    name="Trash the Town",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Put two +1/+1 counters on target creature.\n+ {1} — Target creature gains trample until end of turn.\n+ {1} — Until end of turn, target creature gains \"Whenever this creature deals combat damage to a player, draw two cards.\"",
    setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=_TRASH_THE_TOWN_MODES),
    resolve=make_spree_resolve(_TRASH_THE_TOWN_MODES),
)

TUMBLEWEED_RISING = make_sorcery(
    name="Tumbleweed Rising",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create an X/X green Elemental creature token, where X is the greatest power among creatures you control.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    resolve=tumbleweed_rising_resolve,
)
# Phase 5b: register Plot {2}{G} as a hand-zone activated ability.
TUMBLEWEED_RISING.setup_in_hand = make_plot_setup(plot_cost="{2}{G}")

VORACIOUS_VARMINT = make_creature(
    name="Voracious Varmint",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Varmint"},
    text="Vigilance\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
    setup_interceptors=voracious_varmint_setup,
)

AKUL_THE_UNREPENTANT = make_creature(
    name="Akul the Unrepentant",
    power=5, toughness=5,
    mana_cost="{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Dragon", "Rogue", "Scorpion"},
    supertypes={"Legendary"},
    text="Flying, trample\nSacrifice three other creatures: You may put a creature card from your hand onto the battlefield. Activate only as a sorcery and only once each turn.",
    setup_interceptors=akul_the_unrepentant_setup,
)

ANNIE_FLASH_THE_VETERAN = make_creature(
    name="Annie Flash, the Veteran",
    power=4, toughness=5,
    mana_cost="{3}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flash\nWhen Annie Flash enters, if you cast it, return target permanent card with mana value 3 or less from your graveyard to the battlefield tapped.\nWhenever Annie Flash becomes tapped, exile the top two cards of your library. You may play those cards this turn.",
    setup_interceptors=annie_flash_the_veteran_setup,
)

ANNIE_JOINS_UP = make_enchantment(
    name="Annie Joins Up",
    mana_cost="{1}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    text="When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls.\nIf a triggered ability of a legendary creature you control triggers, that ability triggers an additional time.",
    supertypes={"Legendary"},
    setup_interceptors=annie_joins_up_setup,
)

ASSIMILATION_AEGIS = make_artifact(
    name="Assimilation Aegis",
    mana_cost="{1}{W}{U}",
    text="When this Equipment enters, exile up to one target creature until this Equipment leaves the battlefield.\nWhenever this Equipment becomes attached to a creature, for as long as this Equipment remains attached to it, that creature becomes a copy of a creature card exiled with this Equipment.\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=assimilation_aegis_setup,
)

AT_KNIFEPOINT = make_enchantment(
    name="At Knifepoint",
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="During your turn, outlaws you control have first strike. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhenever you commit a crime, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\" This ability triggers only once each turn.",
    setup_interceptors=at_knifepoint_setup,
)

BADLANDS_REVIVAL = make_sorcery(
    name="Badlands Revival",
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Return up to one target creature card from your graveyard to the battlefield. Return up to one target permanent card from your graveyard to your hand.",
)

BARON_BERTRAM_GRAYWATER = make_creature(
    name="Baron Bertram Graywater",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Noble", "Vampire"},
    supertypes={"Legendary"},
    text="Whenever one or more tokens you control enter, create a 1/1 black Vampire Rogue creature token with lifelink. This ability triggers only once each turn.\n{1}{B}, Sacrifice another creature or artifact: Draw a card.",
    setup_interceptors=baron_bertram_graywater_setup,
)

BONNY_PALL_CLEARCUTTER = make_creature(
    name="Bonny Pall, Clearcutter",
    power=6, toughness=5,
    mana_cost="{3}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Giant", "Scout"},
    supertypes={"Legendary"},
    text="Reach\nWhen Bonny Pall enters, create Beau, a legendary blue Ox creature token with \"Beau's power and toughness are each equal to the number of lands you control.\"\nWhenever you attack, draw a card, then you may put a land card from your hand or graveyard onto the battlefield.",
    setup_interceptors=bonny_pall_clearcutter_setup,
)

BREECHES_THE_BLASTMAKER = make_creature(
    name="Breeches, the Blastmaker",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Goblin", "Pirate"},
    supertypes={"Legendary"},
    text="Menace\nWhenever you cast your second spell each turn, you may sacrifice an artifact. If you do, flip a coin. When you win the flip, copy that spell. You may choose new targets for the copy. When you lose the flip, Breeches deals damage equal to that spell's mana value to any target.",
    setup_interceptors=breeches_the_blastmaker_setup,
)

BRUSE_TARL_ROVING_RANCHER = make_creature(
    name="Bruse Tarl, Roving Rancher",
    power=4, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Oxen you control have double strike.\nWhenever Bruse Tarl enters or attacks, exile the top card of your library. If it's a land card, create a 2/2 white Ox creature token. Otherwise, you may cast it until the end of your next turn.",
    setup_interceptors=bruse_tarl_roving_rancher_setup,
)

CACTUSFOLK_SURESHOT = make_creature(
    name="Cactusfolk Sureshot",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Mercenary", "Plant"},
    text="Reach\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nAt the beginning of combat on your turn, other creatures you control with power 4 or greater gain trample and haste until end of turn.",
    setup_interceptors=cactusfolk_sureshot_setup,
)

CONGREGATION_GRYFF = make_creature(
    name="Congregation Gryff",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hippogriff", "Mount"},
    text="Flying, lifelink\nWhenever this creature attacks while saddled, it gets +X/+X until end of turn, where X is the number of Mounts you control.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=congregation_gryff_setup,
)

DOC_AURLOCK_GRIZZLED_GENIUS = make_creature(
    name="Doc Aurlock, Grizzled Genius",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bear", "Druid"},
    supertypes={"Legendary"},
    text="Spells you cast from your graveyard or from exile cost {2} less to cast.\nPlotting cards from your hand costs {2} less.",
    setup_interceptors=doc_aurlock_grizzled_genius_setup,
)

ERIETTE_THE_BEGUILER = make_creature(
    name="Eriette, the Beguiler",
    power=4, toughness=4,
    mana_cost="{1}{W}{U}{B}",
    colors={Color.BLACK, Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever an Aura you control becomes attached to a nonland permanent an opponent controls with mana value less than or equal to that Aura's mana value, gain control of that permanent for as long as that Aura is attached to it.",
    setup_interceptors=eriette_the_beguiler_setup,
)

ERTHA_JO_FRONTIER_MENTOR = make_creature(
    name="Ertha Jo, Frontier Mentor",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Advisor", "Kor"},
    supertypes={"Legendary"},
    text="When Ertha Jo enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets for the copy.",
    setup_interceptors=ertha_jo_frontier_mentor_setup,
)

FORM_A_POSSE = make_sorcery(
    name="Form a Posse",
    mana_cost="{X}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create X 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

GHIRED_MIRROR_OF_THE_WILDS = make_creature(
    name="Ghired, Mirror of the Wilds",
    power=3, toughness=3,
    mana_cost="{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Haste\nNontoken creatures you control have \"{T}: Create a token that's a copy of target token you control that entered this turn.\"",
    setup_interceptors=ghired_mirror_of_the_wilds_setup,
)

THE_GITROG_RAVENOUS_RIDE = make_creature(
    name="The Gitrog, Ravenous Ride",
    power=6, toughness=5,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Frog", "Horror", "Mount"},
    supertypes={"Legendary"},
    text="Trample, haste\nWhenever The Gitrog deals combat damage to a player, you may sacrifice a creature that saddled it this turn. If you do, draw X cards, then put up to X land cards from your hand onto the battlefield tapped, where X is the sacrificed creature's power.\nSaddle 1",
    setup_interceptors=the_gitrog_ravenous_ride_setup,
)

HONEST_RUTSTEIN = make_creature(
    name="Honest Rutstein",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Honest Rutstein enters, return target creature card from your graveyard to your hand.\nCreature spells you cast cost {1} less to cast.",
    setup_interceptors=honest_rutstein_setup,
)

INTIMIDATION_CAMPAIGN = make_enchantment(
    name="Intimidation Campaign",
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="When this enchantment enters, each opponent loses 1 life, you gain 1 life, and you draw a card.\nWhenever you commit a crime, you may return this enchantment to its owner's hand. (It returns only from the battlefield. Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=intimidation_campaign_setup,
)

JEM_LIGHTFOOTE_SKY_EXPLORER = make_creature(
    name="Jem Lightfoote, Sky Explorer",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card.",
    setup_interceptors=jem_lightfoote_sky_explorer_setup,
)

JOLENE_PLUNDERING_PUGILIST = make_creature(
    name="Jolene, Plundering Pugilist",
    power=4, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever you attack with one or more creatures with power 4 or greater, create a Treasure token.\n{1}{R}, Sacrifice a Treasure: Jolene deals 1 damage to any target.",
    setup_interceptors=jolene_plundering_pugilist_setup,
)

KAMBAL_PROFITEERING_MAYOR = make_creature(
    name="Kambal, Profiteering Mayor",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Whenever one or more tokens your opponents control enter, for each of them, create a tapped token that's a copy of it. This ability triggers only once each turn.\nWhenever one or more tokens you control enter, each opponent loses 1 life and you gain 1 life.",
    setup_interceptors=kambal_profiteering_mayor_setup,
)

KELLAN_JOINS_UP = make_enchantment(
    name="Kellan Joins Up",
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    text="When Kellan Joins Up enters, you may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted. (You may cast it as a sorcery on a later turn without paying its mana cost.)\nWhenever a legendary creature you control enters, put a +1/+1 counter on each creature you control.",
    supertypes={"Legendary"},
    setup_interceptors=kellan_joins_up_setup,
)

KELLAN_THE_KID = make_creature(
    name="Kellan, the Kid",
    power=3, toughness=3,
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Faerie", "Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nWhenever you cast a spell from anywhere other than your hand, you may cast a permanent spell with equal or lesser mana value from your hand without paying its mana cost. If you don't, you may put a land card from your hand onto the battlefield.",
    setup_interceptors=kellan_the_kid_setup,
)

KRAUM_VIOLENT_CACOPHONY = make_creature(
    name="Kraum, Violent Cacophony",
    power=2, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Horror", "Zombie"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast your second spell each turn, put a +1/+1 counter on Kraum and draw a card.",
    setup_interceptors=kraum_violent_cacophony_setup,
)

LAUGHING_JASPER_FLINT = make_creature(
    name="Laughing Jasper Flint",
    power=4, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Lizard", "Rogue"},
    supertypes={"Legendary"},
    text="Creatures you control but don't own are Mercenaries in addition to their other types.\nAt the beginning of your upkeep, exile the top X cards of target opponent's library, where X is the number of outlaws you control. Until end of turn, you may cast spells from among those cards, and mana of any type can be spent to cast those spells.",
    setup_interceptors=laughing_jasper_flint_setup,
)

LAZAV_FAMILIAR_STRANGER = make_creature(
    name="Lazav, Familiar Stranger",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Shapeshifter"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, put a +1/+1 counter on Lazav. Then you may exile a card from a graveyard. If a creature card was exiled this way, you may have Lazav become a copy of that card until end of turn. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=lazav_familiar_stranger_setup,
)

LILAH_UNDEFEATED_SLICKSHOT = make_creature(
    name="Lilah, Undefeated Slickshot",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever you cast a multicolored instant or sorcery spell from your hand, exile that spell instead of putting it into your graveyard as it resolves. If you do, it becomes plotted. (You may cast it as a sorcery on a later turn without paying its mana cost.)",
    setup_interceptors=lilah_undefeated_slickshot_setup,
)

MAKE_YOUR_OWN_LUCK = make_sorcery(
    name="Make Your Own Luck",
    mana_cost="{3}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Look at the top three cards of your library. You may exile a nonland card from among them. If you do, it becomes plotted. Put the rest into your hand. (You may cast it as a sorcery on a later turn without paying its mana cost.)",
)

MALCOLM_THE_EYES = make_creature(
    name="Malcolm, the Eyes",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Pirate", "Siren"},
    supertypes={"Legendary"},
    text="Flying, haste\nWhenever you cast your second spell each turn, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=malcolm_the_eyes_setup,
)

MARCHESA_DEALER_OF_DEATH = make_creature(
    name="Marchesa, Dealer of Death",
    power=3, toughness=4,
    mana_cost="{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, you may pay {1}. If you do, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=marchesa_dealer_of_death_setup,
)

MIRIAM_HERD_WHISPERER = make_creature(
    name="Miriam, Herd Whisperer",
    power=3, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Druid", "Human"},
    supertypes={"Legendary"},
    text="During your turn, Mounts and Vehicles you control have hexproof.\nWhenever a Mount or Vehicle you control attacks, put a +1/+1 counter on it.",
    setup_interceptors=miriam_herd_whisperer_setup,
)

OBEKA_SPLITTER_OF_SECONDS = make_creature(
    name="Obeka, Splitter of Seconds",
    power=2, toughness=5,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Ogre", "Warlock"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Obeka deals combat damage to a player, you get that many additional upkeep steps after this phase.",
    setup_interceptors=obeka_splitter_of_seconds_setup,
)

OKO_THE_RINGLEADER = make_planeswalker(
    name="Oko, the Ringleader",
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    loyalty=3,
    subtypes={"Oko"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, Oko becomes a copy of up to one target creature you control until end of turn, except he has hexproof.\n+1: Draw two cards. If you've committed a crime this turn, discard a card. Otherwise, discard two cards.\n−1: Create a 3/3 green Elk creature token.\n−5: For each other nonland permanent you control, create a token that's a copy of that permanent.",
    setup_interceptors=oko_the_ringleader_setup,
)

PILLAGE_THE_BOG = make_sorcery(
    name="Pillage the Bog",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Look at the top X cards of your library, where X is twice the number of lands you control. Put one of them into your hand and the rest on the bottom of your library in a random order.\nPlot {1}{B}{G} (You may pay {1}{B}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    resolve=pillage_the_bog_resolve,
)
# Phase 5b: register Plot {1}{B}{G} as a hand-zone activated ability.
PILLAGE_THE_BOG.setup_in_hand = make_plot_setup(plot_cost="{1}{B}{G}")

RAKDOS_JOINS_UP = make_enchantment(
    name="Rakdos Joins Up",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When Rakdos Joins Up enters, return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.\nWhenever a legendary creature you control dies, Rakdos Joins Up deals damage equal to that creature's power to target opponent.",
    supertypes={"Legendary"},
    setup_interceptors=rakdos_joins_up_setup,
)

RAKDOS_THE_MUSCLE = make_creature(
    name="Rakdos, the Muscle",
    power=6, toughness=5,
    mana_cost="{2}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Mercenary"},
    supertypes={"Legendary"},
    text="Flying, trample\nWhenever you sacrifice another creature, exile cards equal to its mana value from the top of target player's library. Until your next end step, you may play those cards, and mana of any type can be spent to cast those spells.\nSacrifice another creature: Rakdos gains indestructible until end of turn. Tap it. Activate only once each turn.",
    setup_interceptors=rakdos_the_muscle_setup,
)

RIKU_OF_MANY_PATHS = make_creature(
    name="Riku of Many Paths",
    power=3, toughness=3,
    mana_cost="{G}{U}{R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a modal spell, choose up to X, where X is the number of times you chose a mode for that spell —\n• Exile the top card of your library. Until the end of your next turn, you may play it.\n• Put a +1/+1 counter on Riku. It gains trample until end of turn.\n• Create a 1/1 blue Bird creature token with flying.",
    setup_interceptors=riku_of_many_paths_setup,
)

ROXANNE_STARFALL_SAVANT = make_creature(
    name="Roxanne, Starfall Savant",
    power=4, toughness=3,
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Cat", "Druid"},
    supertypes={"Legendary"},
    text="Whenever Roxanne enters or attacks, create a tapped colorless artifact token named Meteorite with \"When this token enters, it deals 2 damage to any target\" and \"{T}: Add one mana of any color.\"\nWhenever you tap an artifact token for mana, add one mana of any type that artifact token produced.",
    setup_interceptors=roxanne_starfall_savant_setup,
)

RUTHLESS_LAWBRINGER = make_creature(
    name="Ruthless Lawbringer",
    power=3, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Assassin", "Vampire"},
    text="When this creature enters, you may sacrifice another creature. When you do, destroy target nonland permanent.",
    setup_interceptors=ruthless_lawbringer_setup,
)

SATORU_THE_INFILTRATOR = make_creature(
    name="Satoru, the Infiltrator",
    power=2, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Ninja", "Rogue"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Satoru and/or one or more other nontoken creatures you control enter, if none of them were cast or no mana was spent to cast them, draw a card.",
    setup_interceptors=satoru_the_infiltrator_setup,
)

SELVALA_EAGER_TRAILBLAZER = make_creature(
    name="Selvala, Eager Trailblazer",
    power=4, toughness=5,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever you cast a creature spell, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\n{T}: Choose a color. Add one mana of that color for each different power among creatures you control.",
    setup_interceptors=selvala_eager_trailblazer_setup,
)

SERAPHIC_STEED = make_creature(
    name="Seraphic Steed",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Mount", "Unicorn"},
    text="First strike, lifelink\nWhenever this creature attacks while saddled, create a 3/3 white Angel creature token with flying.\nSaddle 4 (Tap any number of other creatures you control with total power 4 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=seraphic_steed_setup,
)

# =============================================================================
# SLICK SEQUENCE - Damage + conditional draw
# =============================================================================

def _slick_sequence_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Slick Sequence after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': 2,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]

    # Check if we've cast another spell this turn
    cast_another = choice.callback_data.get('cast_another_spell', False)
    if cast_another:
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': controller, 'amount': 1},
            source=choice.source_id
        ))

    return events


def slick_sequence_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Slick Sequence (Phase 5b): 2 dmg + conditional draw (if cast another)."""
    caster = _otj_spell_caster_id(state)
    spells_cast = getattr(state, 'spells_cast_this_turn', {}).get(caster, 0)
    cast_another = spells_cast > 1
    events = _otj_damage_to_targets(2)(targets, state)
    if cast_another and caster is not None:
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': caster, 'amount': 1},
        ))
    return events


SLICK_SEQUENCE = make_instant(
    name="Slick Sequence",
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Slick Sequence deals 2 damage to any target. If you've cast another spell this turn, draw a card.",
    resolve=slick_sequence_resolve,
    target_requirements=[target_any(count=1)],
)

TAII_WAKEEN_PERFECT_SHOT = make_creature(
    name="Taii Wakeen, Perfect Shot",
    power=2, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever a source you control deals noncombat damage to a creature equal to that creature's toughness, draw a card.\n{X}, {T}: If a source you control would deal noncombat damage to a permanent or player this turn, it deals that much damage plus X instead.",
    setup_interceptors=taii_wakeen_perfect_shot_setup,
)

VIAL_SMASHER_GLEEFUL_GRENADIER = make_creature(
    name="Vial Smasher, Gleeful Grenadier",
    power=3, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever another outlaw you control enters, Vial Smasher deals 1 damage to target opponent. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
    setup_interceptors=vial_smasher_gleeful_grenadier_setup,
)

VRASKA_JOINS_UP = make_enchantment(
    name="Vraska Joins Up",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="When Vraska Joins Up enters, put a deathtouch counter on each creature you control.\nWhenever a legendary creature you control deals combat damage to a player, draw a card.",
    supertypes={"Legendary"},
    setup_interceptors=vraska_joins_up_setup,
)

VRASKA_THE_SILENCER = make_creature(
    name="Vraska, the Silencer",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Assassin", "Gorgon"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever a nontoken creature an opponent controls dies, you may pay {1}. If you do, return that card to the battlefield tapped under your control. It's a Treasure artifact with \"{T}, Sacrifice this artifact: Add one mana of any color,\" and it loses all other card types.",
    setup_interceptors=vraska_the_silencer_setup,
)

WRANGLER_OF_THE_DAMNED = make_creature(
    name="Wrangler of the Damned",
    power=1, toughness=4,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, create a 2/2 white Spirit creature token with flying.",
    setup_interceptors=wrangler_of_the_damned_setup,
)

WYLIE_DUKE_ATIIN_HERO = make_creature(
    name="Wylie Duke, Atiin Hero",
    power=4, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Ranger"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever Wylie Duke becomes tapped, you gain 1 life and draw a card.",
    setup_interceptors=wylie_duke_atiin_hero_setup,
)

BANDITS_HAUL = make_artifact(
    name="Bandit's Haul",
    mana_cost="{3}",
    text="Whenever you commit a crime, put a loot counter on this artifact. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\n{T}: Add one mana of any color.\n{2}, {T}, Remove two loot counters from this artifact: Draw a card.",
    setup_interceptors=bandits_haul_setup,
)

BOOM_BOX = make_artifact(
    name="Boom Box",
    mana_cost="{2}",
    text="{6}, {T}, Sacrifice this artifact: Destroy up to one target artifact, up to one target creature, and up to one target land.",
    setup_interceptors=boom_box_setup,
)

GOLD_PAN = make_artifact(
    name="Gold Pan",
    mana_cost="{2}",
    text="When this Equipment enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=gold_pan_setup,
)

LAVASPUR_BOOTS = make_artifact(
    name="Lavaspur Boots",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste and ward {1}. (Whenever it becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\nEquip {1}",
    subtypes={"Equipment"},
    setup_interceptors=lavaspur_boots_setup,
)

LUXURIOUS_LOCOMOTIVE = make_artifact(
    name="Luxurious Locomotive",
    mana_cost="{5}",
    text="Whenever this Vehicle attacks, create a Treasure token for each creature that crewed it this turn. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")\nCrew 1. Activate only once each turn. (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    setup_interceptors=luxurious_locomotive_setup,
)

MOBILE_HOMESTEAD = make_artifact(
    name="Mobile Homestead",
    mana_cost="{2}",
    text="This Vehicle has haste as long as you control a Mount.\nWhenever this Vehicle attacks, look at the top card of your library. If it's a land card, you may put it onto the battlefield tapped.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    setup_interceptors=mobile_homestead_setup,
)

OASIS_GARDENER = make_artifact_creature(
    name="Oasis Gardener",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="When this creature enters, you gain 2 life.\n{T}: Add one mana of any color.",
    setup_interceptors=oasis_gardener_setup,
)

REDROCK_SENTINEL = make_artifact_creature(
    name="Redrock Sentinel",
    power=2, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Golem"},
    text="Defender\n{2}, {T}, Sacrifice a land: Draw a card and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SILVER_DEPUTY = make_artifact_creature(
    name="Silver Deputy",
    power=1, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Mercenary"},
    text="When this creature enters, you may search your library for a basic land card or a Desert card, reveal it, then shuffle and put it on top.\n{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.",
    setup_interceptors=silver_deputy_setup,
)

STERLING_HOUND = make_artifact_creature(
    name="Sterling Hound",
    power=3, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Dog"},
    text="When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=sterling_hound_setup,
)

TOMB_TRAWLER = make_artifact_creature(
    name="Tomb Trawler",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="{2}: Put target card from your graveyard on the bottom of your library.",
    setup_interceptors=tomb_trawler_setup,
)

ABRADED_BLUFFS = make_land(
    name="Abraded Bluffs",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {R} or {W}.",
    subtypes={"Desert"},
    setup_interceptors=abraded_bluffs_setup,
)

ARID_ARCHWAY = make_land(
    name="Arid Archway",
    text="This land enters tapped.\nWhen this land enters, return a land you control to its owner's hand. If another Desert was returned this way, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}{C}.",
    subtypes={"Desert"},
    setup_interceptors=arid_archway_setup,
)

BRISTLING_BACKWOODS = make_land(
    name="Bristling Backwoods",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {R} or {G}.",
    subtypes={"Desert"},
    setup_interceptors=bristling_backwoods_setup,
)

CONDUIT_PYLONS = make_land(
    name="Conduit Pylons",
    text="When this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.",
    subtypes={"Desert"},
    setup_interceptors=conduit_pylons_setup,
)

CREOSOTE_HEATH = make_land(
    name="Creosote Heath",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {G} or {W}.",
    subtypes={"Desert"},
    setup_interceptors=creosote_heath_setup,
)

ERODED_CANYON = make_land(
    name="Eroded Canyon",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {U} or {R}.",
    subtypes={"Desert"},
    setup_interceptors=eroded_canyon_setup,
)

FESTERING_GULCH = make_land(
    name="Festering Gulch",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {B} or {G}.",
    subtypes={"Desert"},
    setup_interceptors=festering_gulch_setup,
)

FORLORN_FLATS = make_land(
    name="Forlorn Flats",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {W} or {B}.",
    subtypes={"Desert"},
    setup_interceptors=forlorn_flats_setup,
)

JAGGED_BARRENS = make_land(
    name="Jagged Barrens",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {B} or {R}.",
    subtypes={"Desert"},
    setup_interceptors=jagged_barrens_setup,
)

LONELY_ARROYO = make_land(
    name="Lonely Arroyo",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {W} or {U}.",
    subtypes={"Desert"},
    setup_interceptors=lonely_arroyo_setup,
)

LUSH_OASIS = make_land(
    name="Lush Oasis",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {G} or {U}.",
    subtypes={"Desert"},
    setup_interceptors=lush_oasis_setup,
)

MIRAGE_MESA = make_land(
    name="Mirage Mesa",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
    subtypes={"Desert"},
)

SANDSTORM_VERGE = make_land(
    name="Sandstorm Verge",
    text="{T}: Add {C}.\n{3}, {T}: Target creature can't block this turn. Activate only as a sorcery.",
    subtypes={"Desert"},
    setup_interceptors=sandstorm_verge_setup,
)

SOURED_SPRINGS = make_land(
    name="Soured Springs",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {U} or {B}.",
    subtypes={"Desert"},
    setup_interceptors=soured_springs_setup,
)

BUCOLIC_RANCH = make_land(
    name="Bucolic Ranch",
    text="{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a Mount spell.\n{3}, {T}: Look at the top card of your library. If it's a Mount card, you may reveal it and put it into your hand. If you don't put it into your hand, you may put it on the bottom of your library.",
    subtypes={"Desert"},
    setup_interceptors=bucolic_ranch_setup,
)

BLOOMING_MARSH = make_land(
    name="Blooming Marsh",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {B} or {G}.",
    setup_interceptors=blooming_marsh_setup,
)

BOTANICAL_SANCTUM = make_land(
    name="Botanical Sanctum",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {G} or {U}.",
    setup_interceptors=botanical_sanctum_setup,
)

CONCEALED_COURTYARD = make_land(
    name="Concealed Courtyard",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {W} or {B}.",
    setup_interceptors=concealed_courtyard_setup,
)

INSPIRING_VANTAGE = make_land(
    name="Inspiring Vantage",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {R} or {W}.",
    setup_interceptors=inspiring_vantage_setup,
)

SPIREBLUFF_CANAL = make_land(
    name="Spirebluff Canal",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {U} or {R}.",
    setup_interceptors=spirebluff_canal_setup,
)

JACE_REAWAKENED = make_planeswalker(
    name="Jace Reawakened",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    loyalty=3,
    subtypes={"Jace"},
    supertypes={"Legendary"},
    text="You can't cast Jace Reawakened during your first, second, or third turns of the game.\n+1: Draw a card, then discard a card.\n+1: You may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted.\n−6: Until end of turn, whenever you cast a spell, copy it. You may choose new targets for the copy.",
    setup_interceptors=jace_reawakened_setup,
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

# =============================================================================
# CARD REGISTRY
# =============================================================================

OUTLAWS_THUNDER_JUNCTION_CARDS = {
    "Another Round": ANOTHER_ROUND,
    "Archangel of Tithes": ARCHANGEL_OF_TITHES,
    "Armored Armadillo": ARMORED_ARMADILLO,
    "Aven Interrupter": AVEN_INTERRUPTER,
    "Bounding Felidar": BOUNDING_FELIDAR,
    "Bovine Intervention": BOVINE_INTERVENTION,
    "Bridled Bighorn": BRIDLED_BIGHORN,
    "Claim Jumper": CLAIM_JUMPER,
    "Dust Animus": DUST_ANIMUS,
    "Eriette's Lullaby": ERIETTES_LULLABY,
    "Final Showdown": FINAL_SHOWDOWN,
    "Fortune, Loyal Steed": FORTUNE_LOYAL_STEED,
    "Frontier Seeker": FRONTIER_SEEKER,
    "Getaway Glamer": GETAWAY_GLAMER,
    "High Noon": HIGH_NOON,
    "Holy Cow": HOLY_COW,
    "Inventive Wingsmith": INVENTIVE_WINGSMITH,
    "Lassoed by the Law": LASSOED_BY_THE_LAW,
    "Mystical Tether": MYSTICAL_TETHER,
    "Nurturing Pixie": NURTURING_PIXIE,
    "Omenport Vigilante": OMENPORT_VIGILANTE,
    "One Last Job": ONE_LAST_JOB,
    "Outlaw Medic": OUTLAW_MEDIC,
    "Prairie Dog": PRAIRIE_DOG,
    "Prosperity Tycoon": PROSPERITY_TYCOON,
    "Requisition Raid": REQUISITION_RAID,
    "Rustler Rampage": RUSTLER_RAMPAGE,
    "Shepherd of the Clouds": SHEPHERD_OF_THE_CLOUDS,
    "Sheriff of Safe Passage": SHERIFF_OF_SAFE_PASSAGE,
    "Stagecoach Security": STAGECOACH_SECURITY,
    "Steer Clear": STEER_CLEAR,
    "Sterling Keykeeper": STERLING_KEYKEEPER,
    "Sterling Supplier": STERLING_SUPPLIER,
    "Take Up the Shield": TAKE_UP_THE_SHIELD,
    "Thunder Lasso": THUNDER_LASSO,
    "Trained Arynx": TRAINED_ARYNX,
    "Vengeful Townsfolk": VENGEFUL_TOWNSFOLK,
    "Wanted Griffin": WANTED_GRIFFIN,
    "Archmage's Newt": ARCHMAGES_NEWT,
    "Canyon Crab": CANYON_CRAB,
    "Daring Thunder-Thief": DARING_THUNDERTHIEF,
    "Deepmuck Desperado": DEEPMUCK_DESPERADO,
    "Djinn of Fool's Fall": DJINN_OF_FOOLS_FALL,
    "Double Down": DOUBLE_DOWN,
    "Duelist of the Mind": DUELIST_OF_THE_MIND,
    "Emergent Haunting": EMERGENT_HAUNTING,
    "Failed Fording": FAILED_FORDING,
    "Fblthp, Lost on the Range": FBLTHP_LOST_ON_THE_RANGE,
    "Fleeting Reflection": FLEETING_REFLECTION,
    "Geralf, the Fleshwright": GERALF_THE_FLESHWRIGHT,
    "Geyser Drake": GEYSER_DRAKE,
    "Harrier Strix": HARRIER_STRIX,
    "Jailbreak Scheme": JAILBREAK_SCHEME,
    "The Key to the Vault": THE_KEY_TO_THE_VAULT,
    "Loan Shark": LOAN_SHARK,
    "Marauding Sphinx": MARAUDING_SPHINX,
    "Metamorphic Blast": METAMORPHIC_BLAST,
    "Nimble Brigand": NIMBLE_BRIGAND,
    "Outlaw Stitcher": OUTLAW_STITCHER,
    "Peerless Ropemaster": PEERLESS_ROPEMASTER,
    "Phantom Interference": PHANTOM_INTERFERENCE,
    "Plan the Heist": PLAN_THE_HEIST,
    "Razzle-Dazzler": RAZZLEDAZZLER,
    "Seize the Secrets": SEIZE_THE_SECRETS,
    "Shackle Slinger": SHACKLE_SLINGER,
    "Shifting Grift": SHIFTING_GRIFT,
    "Slickshot Lockpicker": SLICKSHOT_LOCKPICKER,
    "Slickshot Vault-Buster": SLICKSHOT_VAULTBUSTER,
    "Spring Splasher": SPRING_SPLASHER,
    "Step Between Worlds": STEP_BETWEEN_WORLDS,
    "Stoic Sphinx": STOIC_SPHINX,
    "Stop Cold": STOP_COLD,
    "Take the Fall": TAKE_THE_FALL,
    "This Town Ain't Big Enough": THIS_TOWN_AINT_BIG_ENOUGH,
    "Three Steps Ahead": THREE_STEPS_AHEAD,
    "Visage Bandit": VISAGE_BANDIT,
    "Ambush Gigapede": AMBUSH_GIGAPEDE,
    "Binding Negotiation": BINDING_NEGOTIATION,
    "Blacksnag Buzzard": BLACKSNAG_BUZZARD,
    "Blood Hustler": BLOOD_HUSTLER,
    "Boneyard Desecrator": BONEYARD_DESECRATOR,
    "Caustic Bronco": CAUSTIC_BRONCO,
    "Consuming Ashes": CONSUMING_ASHES,
    "Corrupted Conviction": CORRUPTED_CONVICTION,
    "Desert's Due": DESERTS_DUE,
    "Desperate Bloodseeker": DESPERATE_BLOODSEEKER,
    "Fake Your Own Death": FAKE_YOUR_OWN_DEATH,
    "Forsaken Miner": FORSAKEN_MINER,
    "Gisa, the Hellraiser": GISA_THE_HELLRAISER,
    "Hollow Marauder": HOLLOW_MARAUDER,
    "Insatiable Avarice": INSATIABLE_AVARICE,
    "Kaervek, the Punisher": KAERVEK_THE_PUNISHER,
    "Lively Dirge": LIVELY_DIRGE,
    "Mourner's Surprise": MOURNERS_SURPRISE,
    "Neutralize the Guards": NEUTRALIZE_THE_GUARDS,
    "Nezumi Linkbreaker": NEZUMI_LINKBREAKER,
    "Overzealous Muscle": OVERZEALOUS_MUSCLE,
    "Pitiless Carnage": PITILESS_CARNAGE,
    "Rakish Crew": RAKISH_CREW,
    "Rattleback Apothecary": RATTLEBACK_APOTHECARY,
    "Raven of Fell Omens": RAVEN_OF_FELL_OMENS,
    "Rictus Robber": RICTUS_ROBBER,
    "Rooftop Assassin": ROOFTOP_ASSASSIN,
    "Rush of Dread": RUSH_OF_DREAD,
    "Servant of the Stinger": SERVANT_OF_THE_STINGER,
    "Shoot the Sheriff": SHOOT_THE_SHERIFF,
    "Skulduggery": SKULDUGGERY,
    "Tinybones Joins Up": TINYBONES_JOINS_UP,
    "Tinybones, the Pickpocket": TINYBONES_THE_PICKPOCKET,
    "Treasure Dredger": TREASURE_DREDGER,
    "Unfortunate Accident": UNFORTUNATE_ACCIDENT,
    "Unscrupulous Contractor": UNSCRUPULOUS_CONTRACTOR,
    "Vadmir, New Blood": VADMIR_NEW_BLOOD,
    "Vault Plunderer": VAULT_PLUNDERER,
    "Brimstone Roundup": BRIMSTONE_ROUNDUP,
    "Calamity, Galloping Inferno": CALAMITY_GALLOPING_INFERNO,
    "Caught in the Crossfire": CAUGHT_IN_THE_CROSSFIRE,
    "Cunning Coyote": CUNNING_COYOTE,
    "Deadeye Duelist": DEADEYE_DUELIST,
    "Demonic Ruckus": DEMONIC_RUCKUS,
    "Discerning Peddler": DISCERNING_PEDDLER,
    "Explosive Derailment": EXPLOSIVE_DERAILMENT,
    "Ferocification": FEROCIFICATION,
    "Gila Courser": GILA_COURSER,
    "Great Train Heist": GREAT_TRAIN_HEIST,
    "Hell to Pay": HELL_TO_PAY,
    "Hellspur Brute": HELLSPUR_BRUTE,
    "Hellspur Posse Boss": HELLSPUR_POSSE_BOSS,
    "Highway Robbery": HIGHWAY_ROBBERY,
    "Irascible Wolverine": IRASCIBLE_WOLVERINE,
    "Iron-Fist Pulverizer": IRONFIST_PULVERIZER,
    "Longhorn Sharpshooter": LONGHORN_SHARPSHOOTER,
    "Magda, the Hoardmaster": MAGDA_THE_HOARDMASTER,
    "Magebane Lizard": MAGEBANE_LIZARD,
    "Mine Raider": MINE_RAIDER,
    "Outlaws' Fury": OUTLAWS_FURY,
    "Prickly Pair": PRICKLY_PAIR,
    "Quick Draw": QUICK_DRAW,
    "Quilled Charger": QUILLED_CHARGER,
    "Reckless Lackey": RECKLESS_LACKEY,
    "Resilient Roadrunner": RESILIENT_ROADRUNNER,
    "Return the Favor": RETURN_THE_FAVOR,
    "Rodeo Pyromancers": RODEO_PYROMANCERS,
    "Scalestorm Summoner": SCALESTORM_SUMMONER,
    "Scorching Shot": SCORCHING_SHOT,
    "Slickshot Show-Off": SLICKSHOT_SHOWOFF,
    "Stingerback Terror": STINGERBACK_TERROR,
    "Take for a Ride": TAKE_FOR_A_RIDE,
    "Terror of the Peaks": TERROR_OF_THE_PEAKS,
    "Thunder Salvo": THUNDER_SALVO,
    "Trick Shot": TRICK_SHOT,
    "Aloe Alchemist": ALOE_ALCHEMIST,
    "Ankle Biter": ANKLE_BITER,
    "Beastbond Outcaster": BEASTBOND_OUTCASTER,
    "Betrayal at the Vault": BETRAYAL_AT_THE_VAULT,
    "Bristlepack Sentry": BRISTLEPACK_SENTRY,
    "Bristly Bill, Spine Sower": BRISTLY_BILL_SPINE_SOWER,
    "Cactarantula": CACTARANTULA,
    "Colossal Rattlewurm": COLOSSAL_RATTLEWURM,
    "Dance of the Tumbleweeds": DANCE_OF_THE_TUMBLEWEEDS,
    "Drover Grizzly": DROVER_GRIZZLY,
    "Freestrider Commando": FREESTRIDER_COMMANDO,
    "Freestrider Lookout": FREESTRIDER_LOOKOUT,
    "Full Steam Ahead": FULL_STEAM_AHEAD,
    "Giant Beaver": GIANT_BEAVER,
    "Gold Rush": GOLD_RUSH,
    "Goldvein Hydra": GOLDVEIN_HYDRA,
    "Hardbristle Bandit": HARDBRISTLE_BANDIT,
    "Intrepid Stablemaster": INTREPID_STABLEMASTER,
    "Map the Frontier": MAP_THE_FRONTIER,
    "Ornery Tumblewagg": ORNERY_TUMBLEWAGG,
    "Outcaster Greenblade": OUTCASTER_GREENBLADE,
    "Outcaster Trailblazer": OUTCASTER_TRAILBLAZER,
    "Patient Naturalist": PATIENT_NATURALIST,
    "Railway Brawler": RAILWAY_BRAWLER,
    "Rambling Possum": RAMBLING_POSSUM,
    "Raucous Entertainer": RAUCOUS_ENTERTAINER,
    "Reach for the Sky": REACH_FOR_THE_SKY,
    "Rise of the Varmints": RISE_OF_THE_VARMINTS,
    "Smuggler's Surprise": SMUGGLERS_SURPRISE,
    "Snakeskin Veil": SNAKESKIN_VEIL,
    "Spinewoods Armadillo": SPINEWOODS_ARMADILLO,
    "Spinewoods Paladin": SPINEWOODS_PALADIN,
    "Stubborn Burrowfiend": STUBBORN_BURROWFIEND,
    "Throw from the Saddle": THROW_FROM_THE_SADDLE,
    "Trash the Town": TRASH_THE_TOWN,
    "Tumbleweed Rising": TUMBLEWEED_RISING,
    "Voracious Varmint": VORACIOUS_VARMINT,
    "Akul the Unrepentant": AKUL_THE_UNREPENTANT,
    "Annie Flash, the Veteran": ANNIE_FLASH_THE_VETERAN,
    "Annie Joins Up": ANNIE_JOINS_UP,
    "Assimilation Aegis": ASSIMILATION_AEGIS,
    "At Knifepoint": AT_KNIFEPOINT,
    "Badlands Revival": BADLANDS_REVIVAL,
    "Baron Bertram Graywater": BARON_BERTRAM_GRAYWATER,
    "Bonny Pall, Clearcutter": BONNY_PALL_CLEARCUTTER,
    "Breeches, the Blastmaker": BREECHES_THE_BLASTMAKER,
    "Bruse Tarl, Roving Rancher": BRUSE_TARL_ROVING_RANCHER,
    "Cactusfolk Sureshot": CACTUSFOLK_SURESHOT,
    "Congregation Gryff": CONGREGATION_GRYFF,
    "Doc Aurlock, Grizzled Genius": DOC_AURLOCK_GRIZZLED_GENIUS,
    "Eriette, the Beguiler": ERIETTE_THE_BEGUILER,
    "Ertha Jo, Frontier Mentor": ERTHA_JO_FRONTIER_MENTOR,
    "Form a Posse": FORM_A_POSSE,
    "Ghired, Mirror of the Wilds": GHIRED_MIRROR_OF_THE_WILDS,
    "The Gitrog, Ravenous Ride": THE_GITROG_RAVENOUS_RIDE,
    "Honest Rutstein": HONEST_RUTSTEIN,
    "Intimidation Campaign": INTIMIDATION_CAMPAIGN,
    "Jem Lightfoote, Sky Explorer": JEM_LIGHTFOOTE_SKY_EXPLORER,
    "Jolene, Plundering Pugilist": JOLENE_PLUNDERING_PUGILIST,
    "Kambal, Profiteering Mayor": KAMBAL_PROFITEERING_MAYOR,
    "Kellan Joins Up": KELLAN_JOINS_UP,
    "Kellan, the Kid": KELLAN_THE_KID,
    "Kraum, Violent Cacophony": KRAUM_VIOLENT_CACOPHONY,
    "Laughing Jasper Flint": LAUGHING_JASPER_FLINT,
    "Lazav, Familiar Stranger": LAZAV_FAMILIAR_STRANGER,
    "Lilah, Undefeated Slickshot": LILAH_UNDEFEATED_SLICKSHOT,
    "Make Your Own Luck": MAKE_YOUR_OWN_LUCK,
    "Malcolm, the Eyes": MALCOLM_THE_EYES,
    "Marchesa, Dealer of Death": MARCHESA_DEALER_OF_DEATH,
    "Miriam, Herd Whisperer": MIRIAM_HERD_WHISPERER,
    "Obeka, Splitter of Seconds": OBEKA_SPLITTER_OF_SECONDS,
    "Oko, the Ringleader": OKO_THE_RINGLEADER,
    "Pillage the Bog": PILLAGE_THE_BOG,
    "Rakdos Joins Up": RAKDOS_JOINS_UP,
    "Rakdos, the Muscle": RAKDOS_THE_MUSCLE,
    "Riku of Many Paths": RIKU_OF_MANY_PATHS,
    "Roxanne, Starfall Savant": ROXANNE_STARFALL_SAVANT,
    "Ruthless Lawbringer": RUTHLESS_LAWBRINGER,
    "Satoru, the Infiltrator": SATORU_THE_INFILTRATOR,
    "Selvala, Eager Trailblazer": SELVALA_EAGER_TRAILBLAZER,
    "Seraphic Steed": SERAPHIC_STEED,
    "Slick Sequence": SLICK_SEQUENCE,
    "Taii Wakeen, Perfect Shot": TAII_WAKEEN_PERFECT_SHOT,
    "Vial Smasher, Gleeful Grenadier": VIAL_SMASHER_GLEEFUL_GRENADIER,
    "Vraska Joins Up": VRASKA_JOINS_UP,
    "Vraska, the Silencer": VRASKA_THE_SILENCER,
    "Wrangler of the Damned": WRANGLER_OF_THE_DAMNED,
    "Wylie Duke, Atiin Hero": WYLIE_DUKE_ATIIN_HERO,
    "Bandit's Haul": BANDITS_HAUL,
    "Boom Box": BOOM_BOX,
    "Gold Pan": GOLD_PAN,
    "Lavaspur Boots": LAVASPUR_BOOTS,
    "Luxurious Locomotive": LUXURIOUS_LOCOMOTIVE,
    "Mobile Homestead": MOBILE_HOMESTEAD,
    "Oasis Gardener": OASIS_GARDENER,
    "Redrock Sentinel": REDROCK_SENTINEL,
    "Silver Deputy": SILVER_DEPUTY,
    "Sterling Hound": STERLING_HOUND,
    "Tomb Trawler": TOMB_TRAWLER,
    "Abraded Bluffs": ABRADED_BLUFFS,
    "Arid Archway": ARID_ARCHWAY,
    "Bristling Backwoods": BRISTLING_BACKWOODS,
    "Conduit Pylons": CONDUIT_PYLONS,
    "Creosote Heath": CREOSOTE_HEATH,
    "Eroded Canyon": ERODED_CANYON,
    "Festering Gulch": FESTERING_GULCH,
    "Forlorn Flats": FORLORN_FLATS,
    "Jagged Barrens": JAGGED_BARRENS,
    "Lonely Arroyo": LONELY_ARROYO,
    "Lush Oasis": LUSH_OASIS,
    "Mirage Mesa": MIRAGE_MESA,
    "Sandstorm Verge": SANDSTORM_VERGE,
    "Soured Springs": SOURED_SPRINGS,
    "Bucolic Ranch": BUCOLIC_RANCH,
    "Blooming Marsh": BLOOMING_MARSH,
    "Botanical Sanctum": BOTANICAL_SANCTUM,
    "Concealed Courtyard": CONCEALED_COURTYARD,
    "Inspiring Vantage": INSPIRING_VANTAGE,
    "Spirebluff Canal": SPIREBLUFF_CANAL,
    "Jace Reawakened": JACE_REAWAKENED,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(OUTLAWS_THUNDER_JUNCTION_CARDS)} Outlaws_of_Thunder_Junction cards")
