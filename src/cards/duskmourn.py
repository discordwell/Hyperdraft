"""
Duskmourn (DSK) Card Implementations

Real card data fetched from Scryfall API.
277 cards in set.
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_enchantment_creature,
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
    make_etb_trigger, make_death_trigger, make_attack_trigger, make_damage_trigger,
    make_static_pt_boost, make_keyword_grant, make_upkeep_trigger,
    make_life_gain_trigger, make_draw_trigger,
    make_end_step_trigger, make_spell_cast_trigger,
    make_targeted_etb_trigger, make_targeted_attack_trigger,
    other_creatures_you_control, creatures_you_control, other_creatures_with_subtype,
    create_modal_choice, create_target_choice,
    make_saga_setup,
    make_face_down_setup, make_manifest_etb_event,
    make_life_gain_replacer, make_graveyard_to_exile_replacer,
    make_replacement_interceptor,
    make_activated_ability, make_counter_ability, make_damage_ability,
    open_library_search, basic_land_filter,
    make_equipment_setup, make_aura_setup,
    make_room_setup, is_door_unlocked, make_attacks_alone_trigger,
    # Dynamic P/T helpers
    make_attached_dynamic_pt_boost,
    make_dynamic_pt_boost,
    count_permanents_of_type,
    # Sweep 4: becomes-creature
    becomes_creature,
    # Cost reduction
    make_cost_reduction,
    # Cycling
    make_cycling_setup,
    # Copy-token
    make_copy_token_event,
    # Survival (DSK keyword: at second main, if tapped)
    make_survival_trigger,
    # Eerie (DSK keyword: enchantment-ETB or fully unlock a Room)
    make_eerie_trigger,
    # W3 — Survival per-card helpers
    make_counter_transfer_on_death,
    track_exile_with, count_exiled_with,
    make_hand_to_battlefield_choice,
    reveal_top_n_with_distinct_filter,
    # Phase 5b modal helpers
    make_modal_resolve, ModeSpec, normalize_target,
    # DSK Impending mechanic
    make_impending_setup,
)
from src.engine.spell_resolve import (
    resolve_chain,
    resolve_create_token,
    resolve_draw,
    resolve_damage,
    resolve_destroy,
    resolve_exile,
    resolve_pump,
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
    target_same_opponent_creature,
)


# -----------------------------------------------------------------------------
# Phase 5b migration helpers (DSK-local copies; mirror src/cards/foundations.py)
# -----------------------------------------------------------------------------

def _dsk_resolving_spell_obj(state: GameState) -> Optional[GameObject]:
    """Return the topmost spell on the stack — the resolving spell."""
    stack_zone = state.zones.get('stack') if state and state.zones else None
    if stack_zone is None:
        return None
    for obj_id in reversed(list(stack_zone.objects or [])):
        obj = state.objects.get(obj_id)
        if obj is not None:
            return obj
    return None


def _dsk_spell_caster_id(state: GameState) -> Optional[str]:
    obj = _dsk_resolving_spell_obj(state)
    if obj is not None and obj.controller:
        return obj.controller
    return getattr(state, 'priority_player', None) or getattr(state, 'active_player', None)


def _dsk_first_target_id(targets) -> Optional[str]:
    t = _first_target(targets)
    return t.id if t is not None else None


def _dsk_first_target_obj(targets, state: GameState) -> Optional[GameObject]:
    tid = _dsk_first_target_id(targets)
    if tid is None:
        return None
    return state.objects.get(tid)


def _dsk_damage_to_targets(amount: int):
    """Deal ``amount`` damage to each chosen target (creature/PW/player)."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _dsk_resolving_spell_obj(state)
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


def _dsk_destroy_targets():
    """Destroy each chosen permanent target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _dsk_resolving_spell_obj(state)
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


def _dsk_exile_targets():
    """Exile each chosen permanent target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _dsk_resolving_spell_obj(state)
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


def _dsk_caster_life_change(amount: int):
    """Caster gains/loses ``amount`` life (positive = gain)."""
    def _resolve(targets, state: GameState) -> list[Event]:
        caster = _dsk_spell_caster_id(state)
        if caster is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster, 'amount': amount},
        )]
    return _resolve


def _dsk_pump_targets(power_mod: int, toughness_mod: int, duration: str = 'end_of_turn'):
    """Apply +N/+M to each chosen target."""
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _dsk_resolving_spell_obj(state)
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


def _dsk_grant_keywords_to_targets(*keywords: str, duration: str = 'end_of_turn'):
    """Grant keywords to each chosen target."""
    kw_list = tuple(keywords)
    def _resolve(targets, state: GameState) -> list[Event]:
        spell = _dsk_resolving_spell_obj(state)
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


def _make_typecycling_setup(mana_cost: str, land_subtype):
    """Local helper: typecycling activated ability registered via setup_in_hand.

    Cost: ``{mana}, Discard this card``. Effect emits a SEARCH_LIBRARY event
    for a basic land (with optional subtype). The SEARCH_LIBRARY handler is
    an engine gap, but the discard cost + activation registration still wire.
    """
    cost_text = f"{mana_cost}, Discard this card"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        payload = {
            'player': o.controller,
            'card_type': 'basic_land',
            'destination': 'hand',
        }
        if land_subtype:
            payload['subtype'] = land_subtype
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload=payload,
            source=o.id,
            controller=o.controller,
        )]

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        make_activated_ability(
            obj,
            cost=cost_text,
            effect_fn=_effect,
            description=f"Typecycling {mana_cost}",
            sorcery_speed=False,
        )
        return []

    return _setup


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS (Preserved from previous version)
# =============================================================================

def cult_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — gains lifelink until end of turn."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


def fear_of_abduction_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, exile target creature an opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'exile_until_leaves', 'filter': 'opponent_creature'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def friendly_ghost_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature gets +2/+4 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'pump_creature', 'power_mod': 2, 'toughness_mod': 4},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def ghostly_dancers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return an enchantment card from your graveyard to your hand
    (or unlock a locked door of a Room you control).
    Eerie portion (token on enchantment-enters / room-unlock) remains an engine gap; handled by Eerie agent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={'player': obj.controller, 'filter': 'enchantment', 'to': 'hand', 'optional': True},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def living_phone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, look at top 5 cards for a creature with power 2 or less."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIBRARY_SEARCH,
            payload={'player': obj.controller, 'count': 5, 'filter': 'creature_power_2_or_less'},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def optimistic_scavenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — put a +1/+1 counter on target creature (targets self as
    best-effort; engine gap: target choice inside trigger handler)."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


def orphans_of_the_wheat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, tap creatures you control for +1/+1 each."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP_FOR_EFFECT,
            payload={'source': obj.id, 'effect': 'pump_self', 'power_mod': 1, 'toughness_mod': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def splitskin_doll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, draw a card. Then discard unless you control another creature with power 2 or less."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id),
            Event(type=EventType.CONDITIONAL_DISCARD, payload={'player': obj.controller, 'condition': 'no_other_small_creature'}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def toby_beastie_befriender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Toby enters, create a 4/4 white Beast creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Beast',
                'power': 4,
                'toughness': 4,
                'colors': {Color.WHITE},
                'types': {CardType.CREATURE},
                'subtypes': {'Beast'},
                'text': "This creature can't attack or block alone."
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def clammy_prowler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, another target attacking creature can't be blocked this turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'cant_be_blocked', 'filter': 'other_attacking_creature'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def entity_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — draw a card."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


def erratic_apparition_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — this creature gets +1/+1 until end of turn."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


def fear_of_failed_tests_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, draw that many cards."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': amount}, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def fear_of_falling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, target creature defending player controls gets -2/-0."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'debuff', 'power_mod': -2, 'toughness_mod': 0, 'until': 'next_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def floodpits_drowner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, tap target creature an opponent controls and put a stun counter on it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'tap_and_stun', 'filter': 'opponent_creature'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def ghostly_keybearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, unlock a locked door of a Room you control."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.UNLOCK_DOOR,
            payload={'player': obj.controller},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def stalked_researcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — this creature can attack this turn as though it didn't have
    defender. Engine gap: combat._can_attack hard-checks the ``defender``
    keyword and we have no clean override yet, so we emit a marker
    ``GRANT_KEYWORD`` for ``attacks_despite_defender`` (effect_fn returns
    [] makes this trigger queueing-only; the marker keyword is set on
    obj's abilities list so the combat helper can opt-in later)."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': obj.id,
                'keyword': 'attacks_despite_defender',
                'duration': 'end_of_turn',
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


def tunnel_surveyor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 white Glimmer enchantment creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Glimmer',
                'power': 1,
                'toughness': 1,
                'colors': {Color.WHITE},
                'types': {CardType.CREATURE, CardType.ENCHANTMENT},
                'subtypes': {'Glimmer'}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def unwilling_vessel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance + Eerie (possession counter) + death trigger (X/X Spirit
    token with flying where X is counters on this creature)."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'possession', 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]

    def death_effect(event: Event, state: GameState) -> list[Event]:
        counter_count = sum(obj.state.counters.values()) if obj.state.counters else 0
        if counter_count > 0:
            return [Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'name': 'Spirit',
                    'power': counter_count,
                    'toughness': counter_count,
                    'colors': {Color.BLUE},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Spirit'},
                    'keywords': ['flying']
                },
                source=obj.id
            )]
        return []
    return [
        make_eerie_trigger(obj, eerie_effect),
        make_death_trigger(obj, death_effect),
    ]


def balemurk_leech_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — each opponent loses 1 life."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': pid, 'amount': -1},
                source=obj.id, controller=obj.controller,
            )
            for pid in state.players.keys()
            if pid != obj.controller
        ]
    return [make_eerie_trigger(obj, eerie_effect)]


def dashing_bloodsucker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — this creature gets +2/+0 and gains lifelink until end of turn."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': obj.id,
                    'power_mod': 2,
                    'toughness_mod': 0,
                    'duration': 'end_of_turn',
                },
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
                source=obj.id, controller=obj.controller,
            ),
        ]
    return [make_eerie_trigger(obj, eerie_effect)]


def doomsday_excruciator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, draw a card."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def fanatic_of_the_harrowing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, each player discards a card. If you discarded, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(type=EventType.DISCARD, payload={'player': player_id, 'count': 1}, source=obj.id))
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1, 'condition': 'if_discarded'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def fear_of_lost_teeth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, it deals 1 damage to any target and you gain 1 life."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.TARGET_REQUIRED, payload={'source': obj.id, 'effect': 'damage', 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_death_trigger(obj, death_effect)]


def miasma_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may discard cards. Each discarded causes -2/-2 to a target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OPTIONAL_DISCARD_FOR_EFFECT,
            payload={'player': obj.controller, 'effect': 'debuff_targets', 'power_mod': -2, 'toughness_mod': -2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def unstoppable_slasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    When this creature dies, if it had no counters, return it with two stun counters.

    The stun counters prevent the infinite loop:
    - First death: no counters → returns with 2 stun counters
    - Second death: has stun counters → stays dead
    """
    def death_effect(event: Event, state: GameState) -> list[Event]:
        counter_count = sum(obj.state.counters.values()) if obj.state.counters else 0
        if counter_count == 0:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone': f'graveyard_{obj.owner}',
                    'to_zone': 'battlefield',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'tapped': True,
                    'counters': {'stun': 2}
                },
                source=obj.id
            )]
        return []
    return [make_death_trigger(obj, death_effect)]


def vile_mutilator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, each opponent sacrifices a nontoken enchantment and a nontoken creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(type=EventType.SACRIFICE_REQUIRED, payload={'player': player_id, 'filter': 'nontoken_enchantment'}, source=obj.id))
                events.append(Event(type=EventType.SACRIFICE_REQUIRED, payload={'player': player_id, 'filter': 'nontoken_creature'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def boilerbilges_ripper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may sacrifice another creature or enchantment. If you do, deal 2 damage."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OPTIONAL_SACRIFICE_FOR_EFFECT,
            payload={'player': obj.controller, 'filter': 'creature_or_enchantment', 'effect': 'damage', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def clockwork_percussionist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, exile the top card of your library. You may play it until end of next turn."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXILE_FROM_TOP,
            payload={'player': obj.controller, 'count': 1, 'playable_until': 'end_of_next_turn'},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def fear_of_burning_alive_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it deals 4 damage to each opponent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(type=EventType.DAMAGE, payload={'target': player_id, 'amount': 4, 'source': obj.id}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def fear_of_missing_out_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, discard a card, then draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'count': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def infernal_phantom_eerie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — this creature gets +2/+0 until end of turn. When this creature
    dies, it deals damage equal to its power to any target. (Target choice
    is an engine gap — best-effort: targets controller's opponent.)"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2,
                'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id, controller=obj.controller,
        )]

    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Damage equal to power. Best-effort target: first opponent.
        power = get_power(obj, state) or 0
        if power <= 0:
            return []
        for pid in state.players.keys():
            if pid != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': power, 'source': obj.id},
                    source=obj.id, controller=obj.controller,
                )]
        return []

    return [
        make_eerie_trigger(obj, eerie_effect),
        make_death_trigger(obj, death_effect),
    ]


def most_valuable_slayer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack, target attacking creature gets +1/+0 and gains
    first strike until end of turn. Best-effort target selection picks the
    first attacker (engine gap: in-attack target choice)."""
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COMBAT_DECLARED:
            return False
        return event.payload.get('attacking_player') == obj.controller

    def handler(event: Event, state: GameState) -> InterceptorResult:
        attackers = list(event.payload.get('attackers') or [])
        if not attackers:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = attackers[0]
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.PT_MODIFICATION,
                      payload={'object_id': target_id, 'power_mod': 1,
                               'toughness_mod': 0, 'duration': 'end_of_turn'},
                      source=obj.id, controller=obj.controller),
                Event(type=EventType.GRANT_KEYWORD,
                      payload={'object_id': target_id, 'keyword': 'first strike',
                               'duration': 'end_of_turn'},
                      source=obj.id, controller=obj.controller),
            ],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def razorkin_hordecaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack, create a 1/1 red Gremlin creature token."""
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COMBAT_DECLARED:
            return False
        return event.payload.get('attacking_player') == obj.controller

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Gremlin Token',
                    'power': 1, 'toughness': 1,
                    'colors': {Color.RED},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Gremlin'},
                    'is_token': True,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                },
                source=obj.id, controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def razorkin_needlehead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an opponent draws a card, this creature deals 1 damage to them."""
    def draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        player = event.payload.get('player')
        return bool(player and player != obj.controller)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        opp = event.payload.get('player')
        if not opp:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DAMAGE,
                payload={'source': obj.id, 'target': opp, 'amount': 1, 'is_combat': False},
                source=obj.id, controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=draw_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def screaming_nemesis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Screaming Nemesis:
    - Haste (keyword)
    - Whenever this creature is dealt damage, it deals that much damage to any other target.
    - If a player is dealt damage this way, they can't gain life for the rest of the game.
    """
    # Grant haste
    if 'haste' not in [a.get('keyword') for a in obj.characteristics.abilities]:
        obj.characteristics.abilities.append({'keyword': 'haste'})

    # Track players who can't gain life
    players_cant_gain_life = set()

    def damage_to_self_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == obj.id

    def reflect_damage(event: Event, state: GameState) -> list[Event]:
        damage_amount = event.payload.get('amount', 0)
        if damage_amount <= 0:
            return []

        # Find a target - for now, pick first opponent (in real game, player chooses)
        # Can target any player or creature except self
        target_id = None
        for player_id in state.players:
            if player_id != obj.controller:
                target_id = player_id
                # Mark that this player can't gain life
                players_cant_gain_life.add(player_id)
                break

        if not target_id:
            # Target an opponent's creature if no opponent player found
            for other_obj in state.objects.values():
                if other_obj.id != obj.id and other_obj.zone == ZoneType.BATTLEFIELD:
                    if CardType.CREATURE in other_obj.characteristics.types:
                        if other_obj.controller != obj.controller:
                            target_id = other_obj.id
                            break

        if target_id:
            return [Event(
                type=EventType.DAMAGE,
                payload={'source': obj.id, 'target': target_id, 'amount': damage_amount},
                source=obj.id
            )]
        return []

    damage_reflect_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_to_self_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=reflect_damage(e, s)
        ),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=reflect_damage,
    )

    # Prevent life gain for marked players
    def prevent_life_gain_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        player_id = event.payload.get('player')
        amount = event.payload.get('amount', 0)
        # Only prevent positive life changes (gains) for marked players
        return player_id in players_cant_gain_life and amount > 0

    def prevent_life_gain(event: Event, state: GameState) -> InterceptorResult:
        # Set the amount to 0 to prevent the life gain
        event.payload['amount'] = 0
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)

    life_gain_prevention = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=prevent_life_gain_filter,
        handler=prevent_life_gain,
        duration='permanent'  # This effect lasts for the rest of the game!
    )

    return [damage_reflect_trigger, life_gain_prevention]


def vicious_clown_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control with power 2 or less enters, this creature gets +2/+0 until end of turn."""
    def enter_filter(event: Event, state: GameState) -> bool:
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
        if CardType.CREATURE not in entering_obj.characteristics.types:
            return False
        if entering_obj.controller != obj.controller:
            return False
        try:
            power = get_power(entering_obj, state)
        except Exception:
            power = entering_obj.characteristics.power or 0
        return power is not None and power <= 2

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 2, 'toughness_mod': 0,
                         'duration': 'end_of_turn'},
                source=obj.id, controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enter_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def anthropede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may discard a card or pay {2}. When you do, destroy target Room."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OPTIONAL_COST_FOR_EFFECT,
            payload={'player': obj.controller, 'costs': ['discard_card', 'pay_2'], 'effect': 'destroy_room'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def cryptid_inspector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a face-down permanent you control enters or a permanent is turned face up, put a +1/+1 counter on this creature."""
    def face_down_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            entering_id = event.payload.get('object_id')
            entering_obj = state.objects.get(entering_id)
            if entering_obj and entering_obj.controller == obj.controller:
                if event.payload.get('face_down', False):
                    return True
        if event.type == EventType.TURN_FACE_UP:
            target_id = event.payload.get('object_id')
            target_obj = state.objects.get(target_id)
            if target_obj and target_obj.controller == obj.controller:
                return True
        return False

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id, controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=face_down_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def flesh_burrower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, another target creature you control gains deathtouch until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'grant_deathtouch', 'filter': 'other_creature_you_control'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def grasping_longneck_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, you gain 2 life."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]


def omnivorous_flytrap_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium - Whenever this creature enters or attacks, if delirium, distribute two +1/+1 counters."""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CONDITIONAL_COUNTERS,
            payload={'source': obj.id, 'condition': 'delirium', 'counter_type': '+1/+1', 'count': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def spineseeker_centipede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, search your library for a basic land card and put it into your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIBRARY_SEARCH,
            payload={'player': obj.controller, 'filter': 'basic_land', 'destination': 'hand'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def threats_around_every_corner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, manifest dread.

    Manifest dread (CR-style): look at the top two cards of your library, put
    one onto the battlefield face-down as a 2/2 creature and the other into
    your graveyard. Here we approximate by manifesting the top card of the
    library directly (a fully player-driven choice goes through the
    LIBSEARCH_BEGIN choice system in a future pass).
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find the top card of the controller's library (if any); promote it
        # face-down onto the battlefield. We preserve its card_def so flipping
        # the card face-up later re-runs its real setup_interceptors.
        lib_key = f"library_{obj.controller}"
        lib_zone = state.zones.get(lib_key)
        top_card_def = None
        top_obj_id = None
        if lib_zone and lib_zone.objects:
            top_obj_id = lib_zone.objects[-1]  # top of library
            top_obj = state.objects.get(top_obj_id)
            if top_obj is not None:
                top_card_def = top_obj.card_def

        events: list[Event] = [
            # Marker event so other cards' triggers (e.g. Cryptid Inspector) can react.
            Event(type=EventType.MANIFEST_DREAD,
                  payload={'player': obj.controller},
                  source=obj.id),
            # Build the actual face-down 2/2 on the battlefield.
            make_manifest_etb_event(obj.controller,
                                    source_id=obj.id,
                                    card_def=top_card_def),
        ]

        # Remove the chosen card from the library so it doesn't get drawn next.
        # (Best-effort: if zones aren't available we just skip.)
        if top_obj_id and lib_zone and top_obj_id in lib_zone.objects:
            lib_zone.objects.remove(top_obj_id)
            # Mark the original library object as consumed; in a fuller
            # implementation we'd reuse it as the manifested object's card_def
            # carrier (we already pulled card_def above).

        return events
    return [make_etb_trigger(obj, etb_effect)]


def wickerfolk_thresher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium - Whenever this creature attacks with 4+ card types in graveyard, look at top card."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CONDITIONAL_EFFECT,
            payload={'source': obj.id, 'condition': 'delirium', 'effect': 'impulse_land'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def arabella_abandoned_doll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Arabella attacks, it deals X damage to each opponent and you gain X life, where X is creatures you control with power 2 or less."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        x = sum(1 for c in state.objects.values()
                if c.controller == obj.controller
                and CardType.CREATURE in c.characteristics.types
                and c.zone == ZoneType.BATTLEFIELD
                and get_power(c, state) <= 2)
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(type=EventType.DAMAGE, payload={'target': player_id, 'amount': x, 'source': obj.id}, source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': x}, source=obj.id))
        return events
    return [make_attack_trigger(obj, attack_effect)]


def fear_of_infinity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — you may return this card from graveyard to hand. Triggered
    from the graveyard so this uses a custom interceptor (the generic
    ``make_eerie_trigger`` gates on battlefield)."""
    return _fear_of_infinity_eerie_interceptors(obj)


def _fear_of_infinity_eerie_interceptors(obj: GameObject) -> list[Interceptor]:
    def trigger_filter(event: Event, state: GameState) -> bool:
        current = state.objects.get(obj.id)
        if current is None or current.zone != ZoneType.GRAVEYARD:
            return False

        # Branch 1: enchantment ETB controlled by this card's controller.
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            entering_id = event.payload.get('object_id')
            if not entering_id or entering_id == obj.id:
                return False
            entering = state.objects.get(entering_id)
            if entering is None:
                return False
            if CardType.ENCHANTMENT not in entering.characteristics.types:
                return False
            return entering.controller == current.controller

        # Branch 2: Room fully unlocked.
        if event.type == EventType.UNLOCK_DOOR:
            room_id = event.payload.get('object_id')
            if not room_id:
                return False
            room = state.objects.get(room_id)
            if room is None or room.controller != current.controller:
                return False
            doors = getattr(room.state, 'unlocked_doors', None)
            return isinstance(doors, list) and len(doors) >= 2

        return False

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone_type': ZoneType.HAND,
                'optional': True,  # "you may"
            },
            source=obj.id, controller=obj.controller,
        )]

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=handler,
        # Live for the lifetime of the graveyard residence. The duration
        # 'while_in_graveyard' would be ideal; we use 'forever' and rely on
        # the filter's zone gate.
        duration='forever',
        is_triggered_ability=True,
        effect_fn=effect_fn,
        description="Fear of Infinity Eerie (from graveyard)",
    )
    return [interceptor]


def gremlin_tamer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — create a 1/1 red Gremlin creature token."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Gremlin',
                'power': 1, 'toughness': 1,
                'colors': {Color.RED},
                'types': {CardType.CREATURE},
                'subtypes': {'Gremlin'},
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


def marina_vendrell_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Marina Vendrell enters, reveal the top seven cards of your library. Put all enchantment cards into your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.REVEAL_TOP,
            payload={'player': obj.controller, 'count': 7, 'filter': 'enchantment', 'destination': 'hand'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sawblade_skinripper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, Sacrifice another creature or enchantment: Put a +1/+1 counter on this creature.
    At the beginning of your end step, if you sacrificed one or more permanents this turn,
    this creature deals that much damage to any target."""
    # End-step variable damage uses an unimplemented per-turn sacrifice tracker.
    # Wire the activated +1/+1 ability as best-effort (framework can't enforce
    # 'sacrifice another creature or enchantment' as part of the cost yet).
    make_counter_ability(
        obj, cost="{2}, Sacrifice another creature or enchantment",
        counter_type="+1/+1", amount=1, target_self=True,
        description="Put a +1/+1 counter on this creature",
    )
    return []


def shrewd_storyteller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, put a +1/+1 counter on target creature. Targets self as a
    best-effort approximation (engine gap: target-choice inside Survival
    triggers).
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def shroudstomper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature enters or attacks, each opponent loses 2 life. You gain 2 life and draw a card."""
    def effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': player_id, 'amount': -2}, source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id))
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def the_swarmweaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When The Swarmweaver enters, create two 1/1 black and green Insect creature tokens with flying."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        token_payload = {
            'controller': obj.controller,
            'name': 'Insect',
            'power': 1,
            'toughness': 1,
            'colors': {Color.BLACK, Color.GREEN},
            'types': {CardType.CREATURE},
            'subtypes': {'Insect'},
            'keywords': ['flying']
        }
        return [
            Event(type=EventType.CREATE_TOKEN, payload=dict(token_payload), source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload=dict(token_payload), source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def undead_sprinter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample + haste are printed keywords. The cast-from-graveyard
    permission is registered via ``setup_in_graveyard`` below.

    Phase 5b — the alt-cast +1/+1 counter rider is still an engine gap:
    casting from graveyard goes through the standard cast path and we have
    no hook to detect the alt-route here. Wired the gate-permission half;
    counter rider deferred with a TODO.
    """
    return []


def undead_sprinter_gy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cast-from-graveyard permission gated on "a non-Zombie creature died
    this turn".

    Registers a QUERY-priority interceptor on ``QUERY_CAST_LEGALITY`` that
    flips ``allowed=True`` when:
      - the card_id matches this object,
      - the object is in its owner's graveyard,
      - at least one non-Zombie creature has died this turn (scans the
        ``turn_data['_died_counted_this_turn']`` set populated by the
        engine's system-level death tracker).

    The "enters with a +1/+1 counter when cast this way" rider is not
    wired — requires plumbing the cast-route metadata through to
    setup_interceptors, which is not in scope for the Phase 5b sweep.
    """
    from src.engine.cast_permission import ALLOWED_KEY

    def _non_zombie_died_this_turn(st: GameState) -> bool:
        td = getattr(st, 'turn_data', None) or {}
        died_ids = td.get('_died_counted_this_turn')
        if not died_ids:
            return False
        for cid in died_ids:
            cobj = st.objects.get(cid)
            if cobj is None:
                continue
            if CardType.CREATURE not in cobj.characteristics.types:
                continue
            if 'Zombie' in (cobj.characteristics.subtypes or set()):
                continue
            return True
        return False

    def cast_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_CAST_LEGALITY:
            return False
        if event.payload.get('card_id') != obj.id:
            return False
        candidate = st.objects.get(obj.id)
        if candidate is None or candidate.zone != ZoneType.GRAVEYARD:
            return False
        return _non_zombie_died_this_turn(st)

    def cast_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload[ALLOWED_KEY] = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=cast_filter,
        handler=cast_handler,
        duration='forever',
    )
    setattr(interceptor, '_cleanup_on_zone_change', True)
    return [interceptor]


def victor_valgavoths_seneschal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — escalating effect by resolution count this turn:
      1st: surveil 2
      2nd: each opponent discards a card
      3rd: return a creature card from a graveyard to the battlefield under
           your control (engine gap: target choice / graveyard-creature
           picker — best-effort emits a marker event)."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        # Reset the per-turn counter if the turn changed.
        current_turn = getattr(state, 'turn_number', 0)
        last_turn = getattr(obj.state, '_seneschal_last_turn', None)
        if last_turn != current_turn:
            obj.state._seneschal_last_turn = current_turn
            obj.state._seneschal_count = 0
        obj.state._seneschal_count = getattr(obj.state, '_seneschal_count', 0) + 1
        n = obj.state._seneschal_count

        events: list[Event] = []
        if n == 1:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'count': 2},
                source=obj.id, controller=obj.controller,
            ))
        elif n == 2:
            for pid in state.players.keys():
                if pid != obj.controller:
                    events.append(Event(
                        type=EventType.DISCARD,
                        payload={'player': pid, 'count': 1},
                        source=obj.id, controller=obj.controller,
                    ))
        else:  # n >= 3
            # Engine gap: pick a creature card from a graveyard and bring it
            # under controller's control. Emit a marker event so the wiring
            # is visible in the event log.
            events.append(Event(
                type=EventType.TARGET_REQUIRED,
                payload={
                    'source': obj.id,
                    'effect': 'reanimate_to_battlefield_under_your_control',
                    'filter': 'creature_in_any_graveyard',
                },
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_eerie_trigger(obj, eerie_effect)]


# =============================================================================
# AUTO-GENERATED SETUP STUBS (DSK)
# =============================================================================
# Many DSK mechanics (Survival, Rooms/UNLOCK_DOOR, manifest dread,
# Eerie, Delirium counter checks, ward, replacement of "to graveyard" with
# exile, life-total leylines, etc.) are partially or fully unimplemented in
# the engine. Setup functions below register triggers wherever a clean
# trigger pattern exists and otherwise return [] with an "engine gap" note.
#
# Impending is now wired via ``make_impending_setup`` (see the 5 Overlord
# cards in this module; framework lives in ``src/engine/impending.py`` and
# ``src/cards/interceptor_helpers.py``).

def _make_simple_etb_react(obj: GameObject, effect_fn) -> list[Interceptor]:
    """Helper: register an ETB trigger that fires effect_fn when present."""
    return [make_etb_trigger(obj, effect_fn)]


def acrobatic_cheerleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, put a flying counter on it. This ability triggers only once.

    The "only once" rider is enforced via a one-shot flag stored on obj.state.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        if getattr(obj.state, "_survival_fired_acrobatic", False):
            return []
        obj.state._survival_fired_acrobatic = True
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'flying', 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def dazzling_theater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room (Dazzling Theater / Prop Room) — convoke grant + untap-on-other-untap."""
    # engine gap: Room/Door unlock state, convoke grant, multi-player untap step
    return []


def dollmakers_shop_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Door 1 "Dollmaker's Shop": whenever non-Toy creatures you control
    attack a player, create a 1/1 white Toy artifact creature token.
    Door 2 "Porcelain Gallery": base P/T overwrite (engine gap)."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 1 is a recurring trigger; unlocking it doesn't do anything itself.
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Engine gap: base P/T overwrite + dynamic count.
        return []

    def dollmakers_shop_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever one or more non-Toy creatures you control attack a player,
        # create a 1/1 white Toy artifact creature token.
        FIRED_KEY = "_dollmakers_shop_fired_combat"

        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.COMBAT_DECLARED:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Dollmaker's Shop"):
                return False
            if event.payload.get('attacking_player') != o.controller:
                return False
            attackers = list(event.payload.get('attackers') or [])
            if not attackers:
                return False
            # At least one non-Toy attacker required.
            for aid in attackers:
                ao = state.objects.get(aid)
                if ao is None:
                    continue
                subs = ao.characteristics.subtypes or set()
                if 'Toy' not in subs:
                    return True
            return False

        def handler(event: Event, state: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'controller': o.controller,
                        'name': 'Toy Token',
                        'power': 1, 'toughness': 1,
                        'colors': {Color.WHITE},
                        'types': {CardType.ARTIFACT, CardType.CREATURE},
                        'subtypes': {'Toy'},
                        'is_token': True,
                        'to_zone_type': ZoneType.BATTLEFIELD,
                    },
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Dollmaker's Shop",
        door1_unlock_effect=door1_effect,
        door2_name="Porcelain Gallery",
        door2_cost="{4}{W}{W}",
        door2_unlock_effect=door2_effect,
        extra_setup=dollmakers_shop_extra,
    )(obj, state)


def fear_of_immobility_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: tap up to one creature; if opponent's, stun-counter it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'tap_and_maybe_stun', 'filter': 'any_creature'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def fear_of_surveillance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance + on attack, surveil 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


def glimmer_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, draw a card if you control a Glimmer creature. If you don't
    control a Glimmer creature, create a 1/1 white Glimmer enchantment
    creature token.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        # Check if controller controls a Glimmer creature.
        controls_glimmer = any(
            o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and 'Glimmer' in (o.characteristics.subtypes or set())
            for o in state.objects.values()
        )
        if controls_glimmer:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id, controller=obj.controller,
            )]
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Glimmer',
                'controller': obj.controller, 'owner': obj.controller,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'types': {CardType.CREATURE, CardType.ENCHANTMENT},
                'subtypes': {'Glimmer'},
                'colors': {Color.WHITE},
                'power': 1, 'toughness': 1,
                'is_token': True,
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def grand_entryway_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Glimmer token on unlock; +1/+1 counter on up to two creatures on Rotunda unlock."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Create a 1/1 white Glimmer enchantment creature token.
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': o.controller, 'name': 'Glimmer',
                'power': 1, 'toughness': 1,
                'colors': {Color.WHITE},
                'types': {CardType.ENCHANTMENT, CardType.CREATURE},
                'subtypes': {'Glimmer'},
            },
            source=o.id, controller=o.controller,
        )]

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Put a +1/+1 counter on each of up to two target creatures.
        legal = [
            cid for cid, gobj in st.objects.items()
            if (gobj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in gobj.characteristics.types)
        ]
        if not legal:
            return []

        def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
            picked: list[str] = []
            for s in selected or []:
                if isinstance(s, dict):
                    sid = s.get("id") or s.get("target_id")
                    if sid is not None:
                        picked.append(str(sid))
                else:
                    picked.append(str(s))
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': cid, 'counter_type': '+1/+1', 'count': 1},
                source=o.id, controller=o.controller,
            ) for cid in picked]

        from src.engine.types import PendingChoice
        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt="Choose up to two target creatures to receive +1/+1 counters",
            options=legal,
            source_id=o.id,
            min_choices=0,
            max_choices=min(2, len(legal)),
            callback_data={"handler": _on_choose},
        )
        return []

    return make_room_setup(
        door1_name="Grand Entryway",
        door1_unlock_effect=door1_effect,
        door2_name="Elegant Rotunda",
        door2_cost="{2}{W}",
        door2_unlock_effect=door2_effect,
    )(obj, state)


def hardened_escort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """On attack, give +1/+0 + indestructible until EOT to another target creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'pump_and_grant_indestructible',
                     'filter': 'other_creature_you_control', 'power_mod': 1, 'toughness_mod': 0},
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_effect)]


def leyline_of_hope_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Life gains gain +1; +2/+2 to creatures while life >= start+7."""
    # Wire the life-gain replacement (+1 to every life gain you have).
    # engine gap: opening-hand free play; dynamic +2/+2 by life threshold.
    return [make_life_gain_replacer(obj, addend=1)]


def lionheart_glimmer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward 2; whenever you attack, creatures you control get +1/+1 until EOT."""
    # Wire the attack-step team pump as a COMBAT_DECLARED reaction; Ward is
    # left as an engine gap (handled elsewhere when ward becomes wirable).
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COMBAT_DECLARED:
            return False
        return event.payload.get('attacking_player') == obj.controller

    def handler(event: Event, state: GameState) -> InterceptorResult:
        events: list[Event] = []
        for target in list(state.objects.values()):
            if (target.controller == obj.controller and
                    CardType.CREATURE in target.characteristics.types and
                    target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': target.id, 'power_mod': 1,
                             'toughness_mod': 1, 'duration': 'end_of_turn'},
                    source=obj.id,
                ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    # engine gap: Ward 2.
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def overlord_of_the_mistmoors_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Impending 4—{2}{W}{W}; on enter or attack, create two 2/1 white flying Insect tokens."""
    def effect(event: Event, state: GameState) -> list[Event]:
        token = {
            'controller': obj.controller, 'name': 'Insect',
            'power': 2, 'toughness': 1,
            'colors': {Color.WHITE}, 'types': {CardType.CREATURE},
            'subtypes': {'Insect'}, 'keywords': ['flying'],
        }
        return [
            Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id),
        ]
    impending = make_impending_setup(
        impending_cost="{2}{W}{W}", time_counters=4,
    )(obj, state)
    return impending + [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def patched_plaything_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with two -1/-1 counters if cast from hand."""
    # engine gap: 'cast from hand' detection at ETB
    return []


def possessed_goat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}, Discard a card: Three +1/+1 counters and become Demon. Activate only once.

    The "becomes Demon in addition to its other types" portion is a static type
    addition (engine gap for activated abilities). Wire the +1/+1 counter half.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED,
                  payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 3},
                  source=o.id, controller=o.controller),
        ]
    make_activated_ability(
        obj, cost="{3}, Discard a card", effect_fn=_effect,
        description="Put three +1/+1 counters on this creature",
        once_per_turn=True,
    )
    return []


def reluctant_role_model_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, put a flying counter, lifelink counter, or +1/+1 counter on it.
    Whenever this creature or another creature you control dies, if it had
    counters on it, put those counters on up to one target creature.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        from src.engine.types import PendingChoice as _PendingChoice
        # The card text says "put a flying / lifelink / +1+1 counter on it".
        # Open a 3-mode modal so the controller (or the AI) chooses which.
        # Each mode emits a single COUNTER_ADDED on the source.
        def _on_modal(choice, selected, st):
            if not selected:
                return []
            sel = selected[0]
            mode = sel.get('index') if isinstance(sel, dict) else sel
            counter_type = {0: 'flying', 1: 'lifelink', 2: '+1/+1'}.get(int(mode), '+1/+1')
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': counter_type, 'amount': 1},
                source=obj.id, controller=obj.controller,
            )]

        choice = _PendingChoice(
            choice_type="modal",
            player=obj.controller,
            prompt="Reluctant Role Model — choose a counter to add",
            options=[
                {'index': 0, 'text': 'Flying counter'},
                {'index': 1, 'text': 'Lifelink counter'},
                {'index': 2, 'text': '+1/+1 counter'},
            ],
            source_id=obj.id,
            min_choices=1,
            max_choices=1,
            callback_data={'handler': _on_modal},
        )
        state.pending_choice = choice
        return []

    return [
        make_survival_trigger(obj, survival_effect),
        make_counter_transfer_on_death(obj),
    ]


def savior_of_the_small_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, return target creature card with mana value 3 or less from
    your graveyard to your hand.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
            payload={
                'player': obj.controller,
                'card_type': 'creature',
                'max_mv': 3,
                'amount': 1,
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def shardmages_rescue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — enchanted creature gets +1/+1 and (as long as this Aura entered
    this turn) has hexproof.

    Uses ``make_aura_setup`` for the +1/+1 portion and a custom
    QUERY_ABILITIES interceptor that grants 'hexproof' only while the Aura
    still has ``summoning_sickness`` (cleared at the next untap step, which
    matches the printed "as long as this Aura entered this turn" gate one
    turn-cycle of accuracy)."""
    base = make_aura_setup(power_mod=1, toughness_mod=1)(obj, state)

    def hexproof_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        source = state.objects.get(obj.id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        attached_to = getattr(source.state, 'attached_to', None)
        if not attached_to:
            return False
        if event.payload.get('object_id') != attached_to:
            return False
        # Only grant while the Aura entered this turn (proxied by
        # summoning_sickness — cleared at the next untap step).
        return bool(getattr(source.state, 'summoning_sickness', False))

    def hexproof_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'hexproof' not in granted:
            granted.append('hexproof')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    hexproof_int = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=hexproof_filter,
        handler=hexproof_handler,
        duration='while_on_battlefield',
    )
    return base + [hexproof_int]


def sheltered_by_ghosts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — exile-target-until-leaves on ETB, +1/+0 lifelink ward 2 on enchanted."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'exile_until_leaves',
                     'filter': 'opponent_nonland_permanent'},
            source=obj.id,
        )]
    aura_static_setup = make_aura_setup(
        power_mod=1, toughness_mod=0,
        keywords=["lifelink"],
        ward_cost="{2}",
    )
    return [make_etb_trigger(obj, etb_effect)] + aura_static_setup(obj, state)


def shepherding_spirits_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying + plainscycling — only static keywords, no triggered ability."""
    # engine gap: cycling activated ability
    return []


def surgical_suite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — return creature MV<=3 from GY; Hospital Room: +1/+1 on target attacker on attack."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Return target creature card with mana value 3 or less from your graveyard to the battlefield.
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={'player': o.controller, 'card_type': 'creature', 'max_mv': 3, 'amount': 1},
            source=o.id, controller=o.controller,
        )]

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring trigger ("Hospital Room"); the unlock itself does nothing.
        return []

    def hospital_room_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # While Hospital Room is unlocked, whenever you attack put a +1/+1 counter on
        # target attacking creature.
        def attack_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.COMBAT_DECLARED:
                return False
            current = state.objects.get(o.id)
            if current is None:
                return False
            if not is_door_unlocked(current, "Hospital Room"):
                return False
            return event.payload.get('attacking_player') == o.controller

        def handler(event: Event, state: GameState) -> InterceptorResult:
            attackers = list(event.payload.get('attackers') or [])
            if not attackers:
                return InterceptorResult(action=InterceptorAction.PASS)
            # Choose target attacker, then add a +1/+1 counter.
            def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
                tid = None
                if selected:
                    s = selected[0]
                    tid = s.get("id") if isinstance(s, dict) else str(s)
                if tid is None:
                    return []
                return [Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': tid, 'counter_type': '+1/+1', 'count': 1},
                    source=o.id, controller=o.controller,
                )]
            from src.engine.types import PendingChoice
            state.pending_choice = PendingChoice(
                choice_type="target_with_callback",
                player=o.controller,
                prompt="Choose an attacking creature to receive a +1/+1 counter",
                options=attackers,
                source_id=o.id,
                min_choices=1,
                max_choices=1,
                callback_data={"handler": _on_choose},
            )
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=attack_filter,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Surgical Suite",
        door1_unlock_effect=door1_effect,
        door2_name="Hospital Room",
        door2_cost="{3}{W}",
        door2_unlock_effect=door2_effect,
        extra_setup=hospital_room_extra,
    )(obj, state)


def trapped_in_the_screen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward 2; on ETB, exile target artifact/creature/enchantment until leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'exile_until_leaves',
                     'filter': 'opponent_artifact_creature_enchantment'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def unidentified_hovership_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: exile up to one creature with toughness 5-. On leaves, owner manifests dread."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'exile_until_leaves',
                     'filter': 'creature_toughness_5_or_less'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def unsettling_twins_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: manifest dread."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD, payload={'player': obj.controller}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def veteran_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, exile up to one target card from a graveyard.
    As long as there are three or more cards exiled with this creature, it
    gets +3/+3 and has hexproof.
    (Card text on this build is +3/+3 + hexproof; the task description quotes
    +1/+1 + lifelink. We follow the actual card text printed in the
    CardDefinition `text` above — this is the Scryfall-imported text.)
    """
    from src.engine.types import PendingChoice as _PendingChoice

    def survival_effect(event: Event, state: GameState) -> list[Event]:
        # Open a target choice over all cards in any graveyard. Player may
        # choose 0 or 1 ("up to one"). On selection, emit EXILE and record
        # the exiled id on this source's exiled_with_source tracker.
        legal: list[str] = []
        for pid in state.players.keys():
            gy = state.zones.get(f"graveyard_{pid}")
            if gy is None:
                continue
            legal.extend(gy.objects)
        if not legal:
            return []

        def _on_target(choice, selected, st):
            if not selected:
                return []
            target_id = selected[0]
            # Track exile-with-source bookkeeping.
            track_exile_with(st, obj.id, target_id)
            return [Event(
                type=EventType.EXILE,
                payload={'object_id': target_id},
                source=obj.id, controller=obj.controller,
            )]

        choice = _PendingChoice(
            choice_type="target",
            player=obj.controller,
            prompt="Veteran Survivor — exile up to one target card from a graveyard",
            options=legal,
            source_id=obj.id,
            min_choices=0,
            max_choices=1,
            callback_data={'handler': _on_target},
        )
        state.pending_choice = choice
        return []

    # Static ability: while this creature is on the battlefield AND
    # count_exiled_with(state, obj.id) >= 3, grant +3/+3 + hexproof.
    interceptors: list[Interceptor] = [make_survival_trigger(obj, survival_effect)]
    source_id = obj.id

    def _is_self(target: GameObject, state: GameState) -> bool:
        return target.id == source_id

    def _power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        src = state.objects.get(source_id)
        if src is None or src.zone != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('object_id') != source_id:
            return False
        return count_exiled_with(state, source_id) >= 3

    def _power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = new_event.payload.get('value', 0) + 3
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def _toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        src = state.objects.get(source_id)
        if src is None or src.zone != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('object_id') != source_id:
            return False
        return count_exiled_with(state, source_id) >= 3

    def _toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = new_event.payload.get('value', 0) + 3
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def _abilities_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        src = state.objects.get(source_id)
        if src is None or src.zone != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('object_id') != source_id:
            return False
        return count_exiled_with(state, source_id) >= 3

    def _abilities_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'hexproof' not in granted:
            granted.append('hexproof')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors.append(Interceptor(
        id=new_id(), source=source_id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_power_filter, handler=_power_handler,
        duration='while_on_battlefield',
    ))
    interceptors.append(Interceptor(
        id=new_id(), source=source_id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_toughness_filter, handler=_toughness_handler,
        duration='while_on_battlefield',
    ))
    interceptors.append(Interceptor(
        id=new_id(), source=source_id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_abilities_filter, handler=_abilities_handler,
        duration='while_on_battlefield',
    ))

    return interceptors


def the_wandering_rescuer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash + Convoke + Double strike + 'other tapped you control have hexproof'."""
    # engine gap: dynamic-hexproof grant to tapped creatures
    return []


def abhorrent_oculus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At each opponent's upkeep, manifest dread."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        if event.payload.get('player') == obj.controller:
            return []
        return [Event(type=EventType.MANIFEST_DREAD, payload={'player': obj.controller}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def bottomless_pool_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — bounce up to one creature; Locker Room: on team combat damage, draw."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Return up to one target creature to its owner's hand.
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': o.id, 'effect': 'bounce', 'filter': 'creature',
                     'min_targets': 0, 'max_targets': 1},
            source=o.id, controller=o.controller,
        )]

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring trigger ("Locker Room"); the unlock itself does nothing.
        return []

    def locker_room_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever creatures you control deal combat damage to a player, draw a card.
        # Fires once per damage-dealing event from a creature you control to a player.
        # Track damage events per turn so we don't double-fire on a single combat step.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.DAMAGE:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Locker Room"):
                return False
            if not event.payload.get('is_combat'):
                return False
            src_id = event.payload.get('source')
            src_obj = state.objects.get(src_id) if src_id else None
            if not src_obj or src_obj.controller != o.controller:
                return False
            if CardType.CREATURE not in src_obj.characteristics.types:
                return False
            target = event.payload.get('target')
            return isinstance(target, str) and target in state.players

        def handler(event: Event, state: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DRAW,
                    payload={'player': o.controller, 'count': 1},
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Bottomless Pool",
        door1_unlock_effect=door1_effect,
        door2_name="Locker Room",
        door2_cost="{4}{U}",
        door2_unlock_effect=door2_effect,
        extra_setup=locker_room_extra,
    )(obj, state)


def central_elevator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Door 1 search-for-Room tutor (Phase 5b Agent K).

    Door 1 ("Central Elevator"): "When you unlock this door, search your
    library for a Room card that doesn't have the same name as a Room you
    control, reveal it, put it into your hand, then shuffle."

    Door 2 ("Promising Stairs"): upkeep surveil 1. The eight-doors win clause
    remains an engine gap (alt win conditions).
    """
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        controller_id = o.controller
        # Collect names of Rooms the controller already has on the battlefield.
        own_room_names: set[str] = set()
        for other in st.objects.values():
            if other.zone != ZoneType.BATTLEFIELD:
                continue
            if other.controller != controller_id:
                continue
            subs = other.characteristics.subtypes or set()
            if 'Room' in subs:
                # The Room itself counts even if no doors are unlocked.
                own_room_names.add(other.name)

        def _is_non_collision_room(cobj: GameObject, _st: GameState) -> bool:
            if cobj is None:
                return False
            subs = cobj.characteristics.subtypes or set()
            if 'Room' not in subs:
                return False
            return cobj.name not in own_room_names

        from src.engine.library_search import create_library_search_choice
        create_library_search_choice(
            state=st,
            player_id=controller_id,
            source_id=o.id,
            filter_fn=_is_non_collision_room,
            min_count=0,
            max_count=1,
            destination='hand',
            reveal=True,
            shuffle_after=True,
            optional=True,
            prompt="Central Elevator — search your library for a Room with a different name",
        )
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring trigger ("Promising Stairs"); the unlock itself does nothing.
        return []

    def promising_stairs_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # At beginning of upkeep, surveil 1 if Promising Stairs is unlocked.
        # SKIP the win-the-game-on-8-doors clause (engine gap: alt win conditions).
        def upkeep_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'upkeep':
                return False
            if state.active_player != o.controller:
                return False
            current = state.objects.get(o.id)
            return current is not None and is_door_unlocked(current, "Promising Stairs")

        def upkeep_handler(event: Event, state: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.SURVEIL,
                    payload={'player': o.controller, 'count': 1},
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=upkeep_filter,
            handler=upkeep_handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (upkeep_handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Central Elevator",
        door1_unlock_effect=door1_effect,
        door2_name="Promising Stairs",
        door2_cost="{2}{U}",
        door2_unlock_effect=door2_effect,
        extra_setup=promising_stairs_extra,
    )(obj, state)


def creeping_peeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {U}, restricted-use mana for enchantments / unlock / face-up."""
    # engine gap: restricted mana production
    return []


def cursed_windbreaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — manifest dread on ETB then attach. Equipped creature has flying."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD,
                      payload={'player': obj.controller, 'then_attach': obj.id},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def daggermaw_megalodon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance + islandcycling 2 — keyword-only."""
    # engine gap: typecycling
    return []


def duskmourns_domination_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — control + -3/-0 + lose abilities on enchanted."""
    # engine gap: control transfer + ability removal aura
    return []


def fear_of_impostors_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash; ETB counter target spell, controller manifests dread."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'counter_then_manifest_dread', 'filter': 'spell'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def fear_of_isolation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Additional cost: bounce a permanent. Flying. No ETB trigger to wire."""
    # engine gap: additional cost on cast
    return []


def leyline_of_transformation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Choose a creature type; all your creatures (and creature spells, hand cards) gain it."""
    # engine gap: continuous typeshift across hidden zones
    return []


def marina_vendrells_grimoire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Multi-effect: ETB draw 5 if cast; no max hand size; loss-life trigger; gain-life trigger."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'count': 5, 'condition': 'if_cast'},
                      source=obj.id)]
    def gain_effect(event: Event, state: GameState) -> list[Event]:
        amt = int(event.payload.get('amount', 0))
        if amt <= 0:
            return []
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': amt}, source=obj.id)]
    return [
        make_etb_trigger(obj, etb_effect),
        make_life_gain_trigger(obj, gain_effect, controller_only=True),
    ]


def meat_locker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — tap up to one creature with 2 stun counters / draw 3 discard 1."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Tap up to one target creature, then put 2 stun counters on it.
        legal = [
            cid for cid, gobj in st.objects.items()
            if (gobj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in gobj.characteristics.types)
        ]
        if not legal:
            return []

        def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
            tid = None
            if selected:
                s = selected[0]
                tid = s.get("id") if isinstance(s, dict) else str(s)
            if tid is None:
                return []
            return [
                Event(type=EventType.TAP_TARGET,
                      payload={'object_id': tid},
                      source=o.id, controller=o.controller),
                Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': tid, 'counter_type': 'stun', 'count': 2},
                      source=o.id, controller=o.controller),
            ]

        from src.engine.types import PendingChoice
        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt="Choose up to one target creature to tap and stun",
            options=legal,
            source_id=o.id,
            min_choices=0,
            max_choices=1,
            callback_data={"handler": _on_choose},
        )
        return []

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Draw three cards, then discard a card.
        return [
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'count': 3},
                  source=o.id, controller=o.controller),
            Event(type=EventType.DISCARD,
                  payload={'player': o.controller, 'count': 1},
                  source=o.id, controller=o.controller),
        ]

    return make_room_setup(
        door1_name="Meat Locker",
        door1_unlock_effect=door1_effect,
        door2_name="Drowned Diner",
        door2_cost="{3}{U}{U}",
        door2_unlock_effect=door2_effect,
    )(obj, state)


def the_mindskinner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Unblockable + replace damage to opponents with mill."""
    # engine gap: damage-prevent-and-replace-with-mill
    return []


def mirror_room_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — door 1 creates a copy of target creature you control with
    "Reflection" added to its creature types. Door 2 ("Fractured Realm")
    is still SKIP (trigger-doubling is an unrelated engine gap)."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Find legal target creatures controlled by the room's controller.
        legal = [
            cid for cid, gobj in st.objects.items()
            if (gobj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in gobj.characteristics.types and
                gobj.controller == o.controller)
        ]
        if not legal:
            return []

        def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
            tid = None
            if selected:
                s = selected[0]
                tid = s.get("id") if isinstance(s, dict) else str(s)
            if not tid or tid not in st_inner.objects:
                return []
            return make_copy_token_event(
                target_id=tid,
                controller=o.controller,
                source_id=o.id,
                add_subtypes={"Reflection"},
            )

        from src.engine.types import PendingChoice
        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt="Choose a creature you control to copy (Mirror Room)",
            options=legal,
            source_id=o.id,
            min_choices=1,
            max_choices=1,
            callback_data={"handler": _on_choose},
        )
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # SKIP: "if a triggered ability ... triggers an additional time" — engine gap.
        return []

    return make_room_setup(
        door1_name="Mirror Room",
        door1_unlock_effect=door1_effect,
        door2_name="Fractured Realm",
        door2_cost="{5}{U}{U}",
        door2_unlock_effect=door2_effect,
    )(obj, state)


def overlord_of_the_floodpits_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Impending 4—{1}{U}{U}; on enter/attack, draw 2 discard 1."""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 2}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'count': 1}, source=obj.id),
        ]
    impending = make_impending_setup(
        impending_cost="{1}{U}{U}", time_counters=4,
    )(obj, state)
    return impending + [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def paranormal_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you manifest dread, return milled card to hand."""
    def manifest_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.MANIFEST_DREAD and
                event.payload.get('player') == obj.controller)

    def handler(event: Event, state: GameState):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'player': obj.controller, 'source': 'manifest_dread_milled'},
                source=obj.id,
            )],
        )
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=manifest_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def piranha_fly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying; enters tapped.

    Flying is on the printed-keywords list. The "enters tapped" line for a
    non-land creature isn't auto-detected by the ZONE_CHANGE handler (that
    path only inspects card text on lands), so we set the tapped state
    directly on the new battlefield instance.
    """
    obj.state.tapped = True
    return []


def scrabbling_skullcrab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — when an enchantment you control enters or you fully unlock a Room, mill 2 to target player."""
    def eerie_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            entering = state.objects.get(event.payload.get('object_id'))
            return bool(entering and entering.controller == obj.controller and
                        CardType.ENCHANTMENT in entering.characteristics.types)
        return False

    def handler(event: Event, state: GameState):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.TARGET_REQUIRED,
                payload={'source': obj.id, 'effect': 'mill', 'amount': 2, 'filter': 'player'},
                source=obj.id,
            )],
        )
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=eerie_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def silent_hallcreeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Unblockable; on combat damage to player, modal effect (one-of-three, no repeats)."""
    # engine gap: per-creature modal-no-repeat tracking
    return []


def stay_hidden_stay_silent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — tap enchanted creature on ETB; enchanted creature doesn't untap
    during its controller's untap step; {4}{U}{U} sorcery-speed: shuffle
    enchanted creature into its owner's library, then manifest dread.

    Pattern mirrors ``avatar_tla.watery_grasp_setup``.
    """
    base = make_aura_setup()(obj, state)

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target_id = getattr(obj.state, 'attached_to', None)
        if not target_id:
            return []
        return [Event(
            type=EventType.TAP_TARGET,
            payload={'object_id': target_id},
            source=obj.id, controller=obj.controller,
        )]

    def untap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.UNTAP:
            return False
        attached_to = getattr(obj.state, 'attached_to', None)
        if not attached_to:
            return False
        return event.payload.get('object_id') == attached_to

    def prevent_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    prevent_untap = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=untap_filter,
        handler=prevent_handler,
        duration='while_on_battlefield',
    )

    def _shuffle_then_manifest(o: GameObject, st: GameState, targets) -> list[Event]:
        attached_to = getattr(o.state, 'attached_to', None)
        if not attached_to:
            return []
        events: list[Event] = []
        tgt = st.objects.get(attached_to)
        if tgt is not None:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': attached_to,
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.LIBRARY,
                    'owner': tgt.owner,
                    'reason': 'stay_hidden_shuffle',
                },
                source=o.id, controller=o.controller,
            ))
            if hasattr(EventType, 'SHUFFLE'):
                events.append(Event(
                    type=EventType.SHUFFLE,
                    payload={'player': tgt.owner},
                    source=o.id, controller=o.controller,
                ))
        events.append(Event(
            type=EventType.MANIFEST_DREAD,
            payload={'player': o.controller},
            source=o.id, controller=o.controller,
        ))
        return events

    make_activated_ability(
        obj, cost="{4}{U}{U}",
        effect_fn=_shuffle_then_manifest,
        description="Shuffle enchanted creature into its owner's library, then manifest dread",
        sorcery_speed=True,
    )

    return base + [make_etb_trigger(obj, etb_effect), prevent_untap]


def the_tale_of_tamiyo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga I/II/III/IV.

    I, II, III — Mill 2 (engine gap: shared-card-type recursion + draw).
    IV — Exile any number of target instant/sorcery/Tamiyo planeswalker cards from your graveyard, copy them, you may cast the copies (engine gap: target multiple in graveyard + spell copy)."""
    def i_ii_iii(o, s):
        return [Event(
            type=EventType.MILL,
            payload={'player': o.controller, 'count': 2},
            source=o.id,
        )]

    def iv(_o, _s): return []  # engine gap: target multiple in GY + spell copy

    return make_saga_setup(obj, {1: i_ii_iii, 2: i_ii_iii, 3: i_ii_iii, 4: iv})


def unable_to_scream_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — enchanted is 0/2 Toy artifact, can't be turned face up if face down."""
    # engine gap: type/P/T overwrite aura, face-up restriction
    return []


def underwater_tunnel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Door 1 surveil 2 / Slimy Aquarium manifest dread + counter (manifest part SKIPPED)."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Surveil 2.
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': o.controller, 'count': 2},
            source=o.id, controller=o.controller,
        )]

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # SKIP the +1/+1 counter on the manifested creature (engine gap: chaining
        # the counter onto the *just-manifested* face-down). Just emit the
        # MANIFEST_DREAD; the counter portion is left as a no-op.
        return [Event(
            type=EventType.MANIFEST_DREAD,
            payload={'player': o.controller},
            source=o.id, controller=o.controller,
        )]

    return make_room_setup(
        door1_name="Underwater Tunnel",
        door1_unlock_effect=door1_effect,
        door2_name="Slimy Aquarium",
        door2_cost="{3}{U}",
        door2_unlock_effect=door2_effect,
    )(obj, state)


def appendage_amalgam_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash + on attack, surveil 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


def cackling_slasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch; enters with +1/+1 counter if a creature died this turn."""
    from src.cards.interceptor_helpers import make_morbid_etb_trigger
    def add_counter(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
    return [make_morbid_etb_trigger(obj, add_counter)]


def cracked_skull_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — peek + may discard a nonland on ETB; destroy on damage to enchanted."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'peek_and_choose_discard', 'filter': 'player'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def cynical_loner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature can't be blocked by Glimmers.
    Survival — At the beginning of your second main phase, if this creature
    is tapped, you may search your library for a card, put it into your
    graveyard, then shuffle.

    The "can't be blocked by Glimmers" half is a known engine gap (subtype-
    specific blocker restriction) — wire only the Survival half.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        # Emit a SEARCH_LIBRARY event with destination='graveyard'. The
        # engine handler routes this to a PendingChoice and on selection
        # moves the chosen card to the graveyard, shuffling after.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'destination': 'graveyard',
                'shuffle_after': True,
                'amount': 1,
                'min_count': 0,  # "you may"
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def defiled_crypt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Defiled Crypt: GY-leave -> Horror token (once/turn). Cadaver Lab: return creature from GY."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 1 is a recurring trigger ("Defiled Crypt"); the unlock itself does nothing.
        return []

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Cadaver Lab unlock: return target creature card from your graveyard to your hand.
        grave = st.zones.get(f"graveyard_{o.controller}")
        if not grave:
            return []
        legal = [
            cid for cid in grave.objects
            if (gobj := st.objects.get(cid)) is not None
            and CardType.CREATURE in gobj.characteristics.types
        ]
        if not legal:
            return []

        def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
            tid = None
            if selected:
                s = selected[0]
                tid = s.get("id") if isinstance(s, dict) else str(s)
            if tid is None:
                return []
            return [Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'player': o.controller, 'object_id': tid},
                source=o.id, controller=o.controller,
            )]

        from src.engine.types import PendingChoice
        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt="Choose a creature card from your graveyard to return to your hand",
            options=legal,
            source_id=o.id,
            min_choices=1,
            max_choices=1,
            callback_data={"handler": _on_choose},
        )
        return []

    def defiled_crypt_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever one or more cards leave your graveyard, create a 2/2 black Horror
        # enchantment creature token. Limit once per turn.
        # We track the last turn it fired in obj.state.<key>.
        FIRED_KEY = "_defiled_crypt_fired_turn"

        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.ZONE_CHANGE:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Defiled Crypt"):
                return False
            # Card leaving graveyard.
            if event.payload.get('from_zone_type') != ZoneType.GRAVEYARD:
                return False
            moving = state.objects.get(event.payload.get('object_id'))
            if moving is None or moving.owner != o.controller:
                return False
            # Once per turn.
            turn_no = getattr(state, "turn_number", None)
            if turn_no is None:
                turn_no = getattr(getattr(state, "turn_state", None), "turn_number", 0)
            if getattr(current.state, FIRED_KEY, None) == turn_no:
                return False
            return True

        def handler(event: Event, state: GameState) -> InterceptorResult:
            current = state.objects.get(o.id)
            if current is not None:
                turn_no = getattr(state, "turn_number", None)
                if turn_no is None:
                    turn_no = getattr(getattr(state, "turn_state", None), "turn_number", 0)
                setattr(current.state, FIRED_KEY, turn_no)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        'controller': o.controller, 'name': 'Horror',
                        'power': 2, 'toughness': 2,
                        'colors': {Color.BLACK},
                        'types': {CardType.ENCHANTMENT, CardType.CREATURE},
                        'subtypes': {'Horror'},
                    },
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Defiled Crypt",
        door1_unlock_effect=door1_effect,
        door2_name="Cadaver Lab",
        door2_cost="{B}",
        door2_unlock_effect=door2_effect,
        extra_setup=defiled_crypt_extra,
    )(obj, state)


def derelict_attic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Derelict Attic: draw 2 lose 2. Widow's Walk: attacks-alone -> +1/+0 + deathtouch EOT."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Draw two cards and lose 2 life.
        return [
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'count': 2},
                  source=o.id, controller=o.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': -2},
                  source=o.id, controller=o.controller),
        ]

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring trigger ("Widow's Walk"); the unlock itself does nothing.
        return []

    def widows_walk_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever a creature you control attacks alone, it gets +1/+0 and gains
        # deathtouch until end of turn (only while Widow's Walk is unlocked).
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.COMBAT_DECLARED:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Widow's Walk"):
                return False
            if event.payload.get('attacking_player') != o.controller:
                return False
            attackers = list(event.payload.get('attackers') or [])
            return len(attackers) == 1

        def handler(event: Event, state: GameState) -> InterceptorResult:
            attackers = list(event.payload.get('attackers') or [])
            tid = attackers[0] if attackers else None
            if tid is None:
                return InterceptorResult(action=InterceptorAction.PASS)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[
                    Event(type=EventType.PT_MODIFICATION,
                          payload={'object_id': tid, 'power_mod': 1, 'toughness_mod': 0,
                                   'duration': 'end_of_turn'},
                          source=o.id, controller=o.controller),
                    Event(type=EventType.GRANT_KEYWORD,
                          payload={'object_id': tid, 'keyword': 'deathtouch',
                                   'duration': 'end_of_turn'},
                          source=o.id, controller=o.controller),
                ],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Derelict Attic",
        door1_unlock_effect=door1_effect,
        door2_name="Widow's Walk",
        door2_cost="{3}{B}",
        door2_unlock_effect=door2_effect,
        extra_setup=widows_walk_extra,
    )(obj, state)


def fear_of_the_dark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """On attack, if defender has no Glimmers, gains menace + deathtouch EOT."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CONDITIONAL_EFFECT,
            payload={'source': obj.id, 'condition': 'defender_no_glimmer',
                     'effect': 'grant_menace_and_deathtouch_eot'},
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_effect)]


def funeral_room_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Funeral Room: drain 1 on creature-you-control death. Awakening Hall: mass reanimate."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 1 is a recurring trigger ("Funeral Room"); the unlock itself does nothing.
        return []

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Awakening Hall: return all creature cards from your graveyard to the battlefield.
        grave = st.zones.get(f"graveyard_{o.controller}")
        if not grave:
            return []
        events: list[Event] = []
        for cid in list(grave.objects):
            gobj = st.objects.get(cid)
            if gobj is None or CardType.CREATURE not in gobj.characteristics.types:
                continue
            events.append(Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={'player': o.controller, 'object_id': cid},
                source=o.id, controller=o.controller,
            ))
        return events

    def funeral_room_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever a creature you control dies, each opponent loses 1 life and
        # you gain 1 life (only while Funeral Room is unlocked).
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.OBJECT_DESTROYED:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Funeral Room"):
                return False
            target = state.objects.get(event.payload.get('object_id'))
            if target is None:
                return False
            return (CardType.CREATURE in target.characteristics.types and
                    target.controller == o.controller)

        def handler(event: Event, state: GameState) -> InterceptorResult:
            events: list[Event] = []
            for pid in state.players.keys():
                if pid != o.controller:
                    events.append(Event(
                        type=EventType.LIFE_CHANGE,
                        payload={'player': pid, 'amount': -1},
                        source=o.id, controller=o.controller,
                    ))
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': o.controller, 'amount': 1},
                source=o.id, controller=o.controller,
            ))
            return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Funeral Room",
        door1_unlock_effect=door1_effect,
        door2_name="Awakening Hall",
        door2_cost="{6}{B}{B}",
        door2_unlock_effect=door2_effect,
        extra_setup=funeral_room_extra,
    )(obj, state)


def grievous_wound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchant player — can't gain life, half-life-on-damage."""
    # engine gap: enchant-player auras and half-life damage replacement
    return []


def innocuous_rat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, manifest dread."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD, payload={'player': obj.controller}, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]


def killers_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — manifest dread + auto-attach. Equipped has menace."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD,
                      payload={'player': obj.controller, 'then_attach': obj.id},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def leyline_of_the_void_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Replacement: opp graveyard -> exile."""
    # engine gap: opening-hand free play.
    return [make_graveyard_to_exile_replacer(
        obj, affects_controller=False, affects_opponents=True,
    )]


def meathook_massacre_ii_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each player sacs X creatures of their choice; creature-death triggers w/ pay-3-life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for pid in state.players.keys():
            events.append(Event(
                type=EventType.SACRIFICE_REQUIRED,
                payload={'player': pid, 'filter': 'creature', 'count_var': 'X'},
                source=obj.id,
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def nowhere_to_run_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash; ETB -3/-3 to opp creature; opp creatures lose hexproof, no ward triggers."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'debuff', 'power_mod': -3, 'toughness_mod': -3,
                     'filter': 'opponent_creature', 'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def osseous_sticktwister_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink + Delirium end-step: each opp may sac/discard or take damage = power."""
    # engine gap: Delirium card-type-count check + complex modal opponent choice
    return []


def overlord_of_the_balemurk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Impending 5—{1}{B}; on enter/attack, mill 4 + may return creature/PW from GY."""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL, payload={'player': obj.controller, 'count': 4}, source=obj.id)]
    impending = make_impending_setup(
        impending_cost="{1}{B}", time_counters=5,
    )(obj, state)
    return impending + [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def popular_egotist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1B}, sac creature/enchantment for indestructible+tap; sac-trigger drain 1."""
    def sac_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.SACRIFICE and
                event.controller == obj.controller and
                event.payload.get('object_id') != obj.id)

    def handler(event: Event, state: GameState):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.TARGET_REQUIRED,
                    payload={'source': obj.id, 'effect': 'life_drain', 'amount': 1,
                             'filter': 'opponent'},
                    source=obj.id,
                ),
            ],
        )
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sac_filter, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def spectral_snatcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward — discard a card. Swampcycling 2 — keyword-only."""
    # engine gap: ward, typecycling
    return []


def sporogenic_infection_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura — sac on ETB, destroy enchanted on damage."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SACRIFICE_REQUIRED,
            payload={'source': obj.id, 'filter': 'creature_other_than_enchanted', 'target_player': 'choose'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def unholy_annex_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Unholy Annex: end-step draw + drain (Demon-conditional). Ritual Chamber: 6/6 Demon flying."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 1 is a recurring end-step trigger ("Unholy Annex"); the unlock itself
        # does nothing.
        return []

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Ritual Chamber: create a 6/6 black Demon creature token with flying.
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': o.controller, 'name': 'Demon',
                'power': 6, 'toughness': 6,
                'colors': {Color.BLACK},
                'types': {CardType.CREATURE},
                'subtypes': {'Demon'},
                'keywords': ['flying'],
            },
            source=o.id, controller=o.controller,
        )]

    def unholy_annex_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # At the beginning of your end step, draw a card. If you control a Demon,
        # each opponent loses 2 life and you gain 2 life. Otherwise, lose 2 life.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'end_step':
                return False
            if state.active_player != o.controller:
                return False
            current = state.objects.get(o.id)
            return current is not None and is_door_unlocked(current, "Unholy Annex")

        def handler(event: Event, state: GameState) -> InterceptorResult:
            events: list[Event] = [Event(
                type=EventType.DRAW,
                payload={'player': o.controller, 'count': 1},
                source=o.id, controller=o.controller,
            )]
            controls_demon = any(
                gobj.zone == ZoneType.BATTLEFIELD
                and gobj.controller == o.controller
                and 'Demon' in gobj.characteristics.subtypes
                for gobj in state.objects.values()
            )
            if controls_demon:
                for pid in state.players.keys():
                    if pid != o.controller:
                        events.append(Event(
                            type=EventType.LIFE_CHANGE,
                            payload={'player': pid, 'amount': -2},
                            source=o.id, controller=o.controller,
                        ))
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': 2},
                    source=o.id, controller=o.controller,
                ))
            else:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': -2},
                    source=o.id, controller=o.controller,
                ))
            return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Unholy Annex",
        door1_unlock_effect=door1_effect,
        door2_name="Ritual Chamber",
        door2_cost="{3}{B}{B}",
        door2_unlock_effect=door2_effect,
        extra_setup=unholy_annex_extra,
    )(obj, state)


def valgavoth_terror_eater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Replacement (cards-not-yours -> exile) + cast-from-exile permission."""
    # Wire the opponents'-graveyard-to-exile replacement; the rule's
    # "you didn't control" qualifier nearly always coincides with cards going
    # to an opponent's graveyard, so this captures the intended effect.
    # engine gap: cast-from-exile permission for cards exiled this way.
    return [make_graveyard_to_exile_replacer(
        obj, affects_controller=False, affects_opponents=True,
    )]


def valgavoths_faithful_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{B}, Sacrifice this creature: Return target creature card from your
    graveyard to the battlefield. Activate only as a sorcery."""
    def reanimate(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target = st.objects.get(target_id) if target_id else None
        if not target or target.zone != ZoneType.GRAVEYARD:
            return []
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{3}{B}, Sacrifice this creature", effect_fn=reanimate,
        description="Return target creature card from your graveyard to the battlefield",
        sorcery_speed=True,
        targets_required=1, target_kind="creature_card_in_graveyard",
    )
    return []


def bedhead_beastie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace + mountaincycling 2 — keyword-only."""
    # engine gap: typecycling
    return []


def chainsaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — ETB damage; on creature death, rev counter; +X/+0 by counters."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'damage', 'amount': 3, 'filter': 'any_creature'},
            source=obj.id,
        )]

    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        return bool(target and CardType.CREATURE in target.characteristics.types and
                    target.zone == ZoneType.GRAVEYARD)

    def rev_handler(event: Event, state: GameState):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.COUNTER_ADDED,
                              payload={'object_id': obj.id, 'counter_type': 'rev', 'count': 1},
                              source=obj.id)],
        )

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=death_filter, handler=rev_handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (rev_handler(e, s).new_events or []),
        ),
    ]


def charred_foyer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Charred Foyer: at the beginning of your upkeep, impulse-exile
    the top card and grant 'play it this turn'. Warped Space: alt-cast {0}
    once each turn for spells you cast from exile (engine gap — wired
    placeholder)."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 1 is a recurring upkeep trigger; the unlock itself does nothing.
        # The trigger is registered in extra_setup below.
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 ("Warped Space") is a once-per-turn alternative cost for
        # spells cast from exile. Tracking pay-{0}-instead requires the
        # exile-as-cast-zone permission to thread into the cost path; this
        # is the standing engine gap, so the unlock itself is a no-op.
        return []

    def charred_foyer_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # While Charred Foyer is unlocked, at the beginning of your upkeep,
        # exile the top card of your library; you may play it this turn.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'upkeep':
                return False
            if state.active_player != o.controller:
                return False
            current = state.objects.get(o.id)
            return current is not None and is_door_unlocked(current, "Charred Foyer")

        def handler(event: Event, state: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.IMPULSE_DRAW,
                    payload={'player': o.controller, 'count': 1},
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Charred Foyer",
        door1_unlock_effect=door1_effect,
        door2_name="Warped Space",
        door2_cost="{4}{R}{R}",
        door2_unlock_effect=door2_effect,
        extra_setup=charred_foyer_extra,
    )(obj, state)


def cursed_recording_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cast trigger — time counter; spell-copy activated."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'time', 'count': 1, 'check_threshold': 7},
            source=obj.id,
        )]
    return [make_spell_cast_trigger(obj, cast_effect, controller_only=True,
                                    spell_type_filter={CardType.INSTANT, CardType.SORCERY})]


def fear_of_being_hunted_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste; must-be-blocked. Keyword-only."""
    # engine gap: must-be-blocked restriction
    return []


def glassworks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Glassworks: 4 damage to opp creature. Shattered Yard: 1 damage each opp at end step."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Glassworks: deal 4 damage to target creature an opponent controls.
        legal = [
            cid for cid, gobj in st.objects.items()
            if (gobj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in gobj.characteristics.types and
                gobj.controller != o.controller)
        ]
        if not legal:
            return []

        def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
            tid = None
            if selected:
                s = selected[0]
                tid = s.get("id") if isinstance(s, dict) else str(s)
            if tid is None:
                return []
            return [Event(
                type=EventType.DAMAGE,
                payload={'source': o.id, 'target': tid, 'amount': 4, 'is_combat': False},
                source=o.id, controller=o.controller,
            )]

        from src.engine.types import PendingChoice
        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt="Choose a creature an opponent controls to deal 4 damage to",
            options=legal,
            source_id=o.id,
            min_choices=1,
            max_choices=1,
            callback_data={"handler": _on_choose},
        )
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring end-step trigger ("Shattered Yard"); the unlock
        # itself does nothing.
        return []

    def shattered_yard_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # At the beginning of each end step, Shattered Yard deals 1 damage to
        # each opponent.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'end_step':
                return False
            current = state.objects.get(o.id)
            return current is not None and is_door_unlocked(current, "Shattered Yard")

        def handler(event: Event, state: GameState) -> InterceptorResult:
            events: list[Event] = []
            for pid in state.players.keys():
                if pid != o.controller:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'source': o.id, 'target': pid, 'amount': 1, 'is_combat': False},
                        source=o.id, controller=o.controller,
                    ))
            return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Glassworks",
        door1_unlock_effect=door1_effect,
        door2_name="Shattered Yard",
        door2_cost="{4}{R}",
        door2_unlock_effect=door2_effect,
        extra_setup=shattered_yard_extra,
    )(obj, state)


def hand_that_feeds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium — on attack with 4+ types in GY, +2/+0 menace EOT."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CONDITIONAL_EFFECT,
            payload={'source': obj.id, 'condition': 'delirium', 'effect': 'self_pump_menace',
                     'power_mod': 2, 'toughness_mod': 0},
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_effect)]


def irreverent_gremlin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace + small-creature-enter loot."""
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target or target.id == source.id:
            return False
        if target.controller != source.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        try:
            return get_power(target, state) <= 2
        except Exception:
            return False

    def effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.OPTIONAL_DISCARD_FOR_EFFECT,
                  payload={'player': obj.controller, 'effect': 'draw_card', 'once_per_turn': True},
                  source=obj.id),
        ]

    return [make_etb_trigger(obj, effect, filter_fn=filter_fn)]


def leyline_of_resonance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell-copy on cast targeting single own creature."""
    # engine gap: free spell copy with new targets
    return []


def aleyline_of_resonance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """A-version: pay {1} to copy."""
    # engine gap: optional pay-to-copy
    return []


def norin_swift_survivalist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Norin can't block. (Second clause — 'becomes blocked' exile-and-impulse
    trigger — is an engine gap; combat doesn't emit a per-attacker BECAME_BLOCKED
    event today.) Wire only the printed cant_block static."""
    def self_filter(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    return [make_keyword_grant(obj, ['cant_block'], self_filter)]


def overlord_of_the_boilerbilges_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Impending 4—{2}{R}{R}; on enter/attack, deal 4 to any target."""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'damage', 'amount': 4, 'filter': 'any_target'},
            source=obj.id,
        )]
    impending = make_impending_setup(
        impending_cost="{2}{R}{R}", time_counters=4,
    )(obj, state)
    return impending + [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def painters_studio_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Painter's Studio: exile top 2 (cross-turn play SKIPPED). Defaced Gallery: attackers +1/+0."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # SKIP: "exile top 2 cards, may play them until end of next turn" requires
        # cross-turn impulse-play tracking that's an engine gap.
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring trigger ("Defaced Gallery"); the unlock itself does nothing.
        return []

    def defaced_gallery_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever you attack, attacking creatures you control get +1/+0 until
        # end of turn.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.COMBAT_DECLARED:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Defaced Gallery"):
                return False
            return event.payload.get('attacking_player') == o.controller

        def handler(event: Event, state: GameState) -> InterceptorResult:
            attackers = list(event.payload.get('attackers') or [])
            events = [Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': aid, 'power_mod': 1, 'toughness_mod': 0,
                         'duration': 'end_of_turn'},
                source=o.id, controller=o.controller,
            ) for aid in attackers]
            return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Painter's Studio",
        door1_unlock_effect=door1_effect,
        door2_name="Defaced Gallery",
        door2_cost="{1}{R}",
        door2_unlock_effect=door2_effect,
        extra_setup=defaced_gallery_extra,
    )(obj, state)


def piggy_bank_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create Treasure."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller, 'name': 'Treasure',
                'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'},
                'colors': set(),
            },
            source=obj.id,
        )]
    return [make_death_trigger(obj, death_effect)]


def ragged_playmate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, {T}: Target creature with power 2 or less can't be blocked this turn."""
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
        obj, cost="{1}, {T}", effect_fn=_grant_unblockable,
        description="Target creature with power 2 or less can't be blocked this turn",
        targets_required=1, target_kind="creature_power_le_2",
    )
    return []


def rampaging_soulrager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static +3/+0 if 2+ unlocked doors among Rooms you control."""
    def affects_self_when_doors(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        # Count total unlocked doors across all Rooms the controller owns.
        unlocked = 0
        for o in st.objects.values():
            if (o.controller == obj.controller
                    and o.zone == ZoneType.BATTLEFIELD
                    and 'Room' in (o.characteristics.subtypes or set())):
                doors = getattr(o.state, "unlocked_doors", None) or []
                unlocked += len(doors)
        return unlocked >= 2

    def pt_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        return (3, 0)

    return make_dynamic_pt_boost(obj, pt_mod, affects_self_when_doors)


def ripchain_razorkin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{R}, Sacrifice a land: Draw a card."""
    from src.cards.interceptor_helpers import make_draw_ability
    make_draw_ability(obj, cost="{2}{R}, Sacrifice a land", count=1,
                      description="Draw a card")
    return []


def the_rollercrusher_ride_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium — double noncombat damage; ETB X damage to up to X creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'damage_each', 'amount': 'X',
                     'filter': 'creature', 'max_targets': 'X'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def ticket_booth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Ticket Booth: manifest dread (SKIPPED). Tunnel of Hate: target attacker double strike EOT."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # SKIP: manifest dread on door 1 — engine gap (manifest dread isn't fully wired).
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a recurring trigger ("Tunnel of Hate"); the unlock itself does nothing.
        return []

    def tunnel_of_hate_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Whenever you attack, target attacking creature gains double strike until
        # end of turn.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.COMBAT_DECLARED:
                return False
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Tunnel of Hate"):
                return False
            return event.payload.get('attacking_player') == o.controller

        def handler(event: Event, state: GameState) -> InterceptorResult:
            attackers = list(event.payload.get('attackers') or [])
            if not attackers:
                return InterceptorResult(action=InterceptorAction.PASS)

            def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
                tid = None
                if selected:
                    s = selected[0]
                    tid = s.get("id") if isinstance(s, dict) else str(s)
                if tid is None:
                    return []
                return [Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': tid, 'keyword': 'double strike',
                             'duration': 'end_of_turn'},
                    source=o.id, controller=o.controller,
                )]

            from src.engine.types import PendingChoice
            state.pending_choice = PendingChoice(
                choice_type="target_with_callback",
                player=o.controller,
                prompt="Choose an attacking creature to gain double strike",
                options=attackers,
                source_id=o.id,
                min_choices=1,
                max_choices=1,
                callback_data={"handler": _on_choose},
            )
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Ticket Booth",
        door1_unlock_effect=door1_effect,
        door2_name="Tunnel of Hate",
        door2_cost="{4}{R}{R}",
        door2_unlock_effect=door2_effect,
        extra_setup=tunnel_of_hate_extra,
    )(obj, state)


def altanak_the_thricecalled_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample; whenever targeted by opponent, draw."""
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST, EventType.ACTIVATE):
            return False
        targets = event.payload.get('targets') or []
        if not isinstance(targets, (list, set, tuple)):
            return False
        if obj.id not in targets:
            return False
        return event.controller is not None and event.controller != obj.controller

    def handler(event: Event, state: GameState):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW,
                              payload={'player': obj.controller, 'count': 1}, source=obj.id)],
        )
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn, handler=handler,
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lambda e, s: (handler(e, s).new_events or []),
    )]


def balustrade_wurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample, haste (printed keywords). The "uncounterable" and
    delirium-gated graveyard reanimate live in ``balustrade_wurm_gy_setup``
    via ``setup_in_graveyard``."""
    return []


def balustrade_wurm_gy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{G}{G}: Return this card from your graveyard to the battlefield
    with a finality counter on it. Activate only if there are four or more
    card types among cards in your graveyard and only as a sorcery."""
    DELIRIUM_TYPES = {
        CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT,
        CardType.LAND, CardType.PLANESWALKER, CardType.INSTANT,
        CardType.SORCERY,
    }
    tribal = getattr(CardType, 'TRIBAL', None)
    if tribal is not None:
        DELIRIUM_TYPES.add(tribal)
    battle = getattr(CardType, 'BATTLE', None)
    if battle is not None:
        DELIRIUM_TYPES.add(battle)

    def _has_delirium(st: GameState, player_id: str) -> bool:
        gy = st.zones.get(f"graveyard_{player_id}")
        if not gy:
            return False
        seen: set = set()
        for oid in gy.objects:
            o = st.objects.get(oid)
            if not o:
                continue
            for t in o.characteristics.types:
                if t in DELIRIUM_TYPES:
                    seen.add(t)
                    if len(seen) >= 4:
                        return True
        return len(seen) >= 4

    def _delirium_gate(card: GameObject, st: GameState) -> bool:
        return _has_delirium(st, card.controller)

    def _reanimate_self(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': o.id,
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'counters': {'finality': 1},
                },
                source=o.id, controller=o.controller,
            ),
        ]

    make_activated_ability(
        obj, cost="{2}{G}{G}", effect_fn=_reanimate_self,
        description=("Return Balustrade Wurm from your graveyard to the "
                     "battlefield with a finality counter on it"),
        sorcery_speed=True,
        precondition_fn=_delirium_gate,
    )
    return []


def bashful_beastie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, manifest dread."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD, payload={'player': obj.controller}, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]


def cautious_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, you gain 2 life.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def defiant_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, manifest dread.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANIFEST_DREAD,
            payload={'controller': obj.controller, 'source_id': obj.id},
            source=obj.id,
        )]

    return [make_survival_trigger(obj, survival_effect)]


def fear_of_exposure_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Additional cost: tap two; Trample."""
    # engine gap: additional cost
    return []


frantic_strength_setup = make_aura_setup(
    power_mod=2, toughness_mod=2, keywords=["trample"]
)


def greenhouse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Greenhouse: lands tap for any color (SKIP color choice). Rickety Gazebo: mill 4 + return up to 2 perms."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 1 is a continuous static ("Lands you control have ..."); the
        # unlock itself does nothing. The static is wired in extra_setup.
        return []

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Mill 4 cards, then return up to two permanent cards from among them
        # to your hand. Mill events tag those cards in the graveyard; the
        # follow-up RETURN_TO_HAND_FROM_GRAVEYARD asks the chooser to pick
        # up to 2 permanents (best-effort: we just enable a generic permanent
        # graveyard-return; the engine's "from among the milled cards"
        # narrowing is an engine gap).
        return [
            Event(type=EventType.MILL,
                  payload={'player': o.controller, 'count': 4},
                  source=o.id, controller=o.controller),
            Event(type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                  payload={'player': o.controller, 'card_type': 'permanent',
                           'amount': 2, 'optional': True},
                  source=o.id, controller=o.controller),
        ]

    def greenhouse_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # SKIP the actual mana-of-any-color granting (engine gap: granting
        # activated mana abilities to all lands you control with player color
        # choice). Track only that the static would be active.
        return []

    return make_room_setup(
        door1_name="Greenhouse",
        door1_unlock_effect=door1_effect,
        door2_name="Rickety Gazebo",
        door2_cost="{3}{G}",
        door2_unlock_effect=door2_effect,
        extra_setup=greenhouse_extra,
    )(obj, state)


def hauntwoods_shrieker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """On attack, manifest dread; activated reveal-and-flip."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD, payload={'player': obj.controller}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


def hedge_shredder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vehicle — mill 2 on attack; lands milled go onto battlefield tapped."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL, payload={'player': obj.controller, 'count': 2,
                                                     'optional': True}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


def house_cartographer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if this creature
    is tapped, reveal cards from the top of your library until you reveal a
    land card. Put that card into your hand and the rest on the bottom of
    your library in a random order.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.REVEAL_UNTIL_LAND,
            payload={'player': obj.controller},
            source=obj.id, controller=obj.controller,
        )]
    return [make_survival_trigger(obj, survival_effect)]


def insidious_fungus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, Sacrifice this: choose one — destroy artifact / destroy enchantment /
    draw a card. The "may play a land from your hand tapped" rider on mode 2
    requires a play-from-hand permission inside a resolve callback (engine gap)."""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        modes = [
            {"index": 0, "text": "Destroy target artifact"},
            {"index": 1, "text": "Destroy target enchantment"},
            {"index": 2, "text": "Draw a card"},
        ]
        choice = create_modal_choice(
            state=st, player_id=o.controller, source_id=o.id,
            modes=modes, min_modes=1, max_modes=1,
            prompt="Insidious Fungus — choose one:",
        )

        def _handler(ch, selected_modes, gs: GameState) -> list[Event]:
            if not selected_modes:
                return []
            mode = selected_modes[0]
            if mode == 2:
                return [Event(
                    type=EventType.DRAW,
                    payload={'player': o.controller, 'count': 1},
                    source=o.id, controller=o.controller,
                )]

            # Modes 0/1: chain a target-choice for destroy artifact/enchantment.
            if mode == 0:
                type_filter = CardType.ARTIFACT
                prompt_text = "Insidious Fungus — destroy target artifact"
            else:
                type_filter = CardType.ENCHANTMENT
                prompt_text = "Insidious Fungus — destroy target enchantment"

            legal = [
                oid for oid, oo in gs.objects.items()
                if oo.zone == ZoneType.BATTLEFIELD
                and type_filter in oo.characteristics.types
            ]
            if not legal:
                return []

            def _execute(_ch, selected_targets, st2: GameState) -> list[Event]:
                if not selected_targets:
                    return []
                return [Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': selected_targets[0]},
                    source=o.id, controller=o.controller,
                )]

            target_choice = create_target_choice(
                state=gs, player_id=o.controller, source_id=o.id,
                legal_targets=legal,
                prompt=prompt_text,
                min_targets=1, max_targets=1,
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _execute
            return []

        choice.choice_type = "modal_with_callback"
        choice.callback_data['handler'] = _handler
        return []

    make_activated_ability(
        obj, "{2}, Sacrifice this creature", effect,
        description="Modal: destroy artifact/enchantment or draw a card",
    )
    return []


def kona_rescue_beastie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if Kona is
    tapped, you may put a permanent card from your hand onto the battlefield.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        # Open a hand-to-battlefield choice over the controller's hand,
        # filtered to permanent cards only. Optional ("you may").
        return make_hand_to_battlefield_choice(
            state, obj.controller, obj.id,
            optional=True,
            prompt="Kona — choose a permanent card from your hand to put onto the battlefield",
        )
    return [make_survival_trigger(obj, survival_effect)]


def leyline_of_mutation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Alt cost WUBRG for any spell."""
    # engine gap: alternative casting cost
    return []


def moldering_gym_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Moldering Gym: search basic land tapped. Weight Room: manifest dread + 3 counters (manifest SKIPPED)."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Search your library for a basic land card, put it onto the battlefield
        # tapped, then shuffle.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': o.controller, 'filter': 'basic_land',
                     'destination': 'battlefield', 'tapped': True,
                     'shuffle_after': True, 'amount': 1},
            source=o.id, controller=o.controller,
        )]

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # SKIP: manifest dread + counter the manifested creature — engine gap.
        return []

    return make_room_setup(
        door1_name="Moldering Gym",
        door1_unlock_effect=door1_effect,
        door2_name="Weight Room",
        door2_cost="{5}{G}",
        door2_unlock_effect=door2_effect,
    )(obj, state)


def overlord_of_the_hauntwoods_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Impending 4—{1}{G}{G}; on enter/attack, create tapped omni-basic land token."""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller, 'name': 'Everywhere',
                'types': {CardType.LAND}, 'subtypes': {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'},
                'colors': set(), 'tapped': True,
            },
            source=obj.id,
        )]
    impending = make_impending_setup(
        impending_cost="{1}{G}{G}", time_counters=4,
    )(obj, state)
    return impending + [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]


def patchwork_beastie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium — can't attack/block unless 4 types in GY. Upkeep mill optional."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL,
                      payload={'player': obj.controller, 'count': 1, 'optional': True},
                      source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def rootwise_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste; Survival — At the beginning of your second main phase, if this
    creature is tapped, put three +1/+1 counters on up to one target land you
    control. That land becomes a 0/0 Elemental creature in addition to its
    other types. It gains haste until your next turn.

    Best-effort target selection (engine gap: Survival target choice): pick
    the first non-creature land controlled by ``obj.controller``. Animation
    uses ``duration='until_your_next_turn'`` so the land stays a creature
    through the opponent's turn and reverts at the controller's next TURN_START.
    """
    from src.cards.interceptor_helpers import make_until_next_turn_animation

    def survival_effect(event: Event, state: GameState) -> list[Event]:
        # Find the first land controlled by us that isn't already a creature.
        target_land = None
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for oid in battlefield.objects:
                cand = state.objects.get(oid)
                if cand is None:
                    continue
                if cand.controller != obj.controller:
                    continue
                if CardType.LAND not in cand.characteristics.types:
                    continue
                if CardType.CREATURE in cand.characteristics.types:
                    continue
                target_land = cand
                break
        if target_land is None:
            return []

        # Animate "until your next turn" — controller is obj.controller (the
        # Rootwise's controller), since the duration is keyed off *their* turn.
        make_until_next_turn_animation(
            target_land,
            state,
            controller=obj.controller,
            power=0,
            toughness=0,
            subtypes={"Elemental"},
            keywords=["haste"],
            keep_land=True,
        )

        # Three +1/+1 counters on the targeted land (now a creature).
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': target_land.id,
                'counter_type': '+1/+1',
                'amount': 3,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [make_survival_trigger(obj, survival_effect)]


def slavering_branchsnapper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample; forestcycling 2 — keyword-only."""
    # engine gap: typecycling
    return []


def tyvar_the_pummeler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap-creature for indestructible; activated {3}{G}{G}: team +X/+X EOT,
    X = greatest power among creatures you control. Skip the tap-cost line
    (engine gap: tap-another-creature as cost)."""
    def _team_pump(o: GameObject, st: GameState, targets) -> list[Event]:
        max_power = 0
        creature_ids = []
        for oid, oo in st.objects.items():
            if (oo.controller == o.controller and
                    oo.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in oo.characteristics.types):
                creature_ids.append(oid)
                try:
                    p = get_power(oo, st)
                except Exception:
                    p = oo.characteristics.power or 0
                if p > max_power:
                    max_power = p
        if max_power <= 0 or not creature_ids:
            return []
        events: list[Event] = []
        for cid in creature_ids:
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': cid,
                    'power_mod': max_power,
                    'toughness_mod': max_power,
                    'duration': 'end_of_turn',
                },
                source=o.id,
                controller=o.controller,
            ))
        return events

    make_activated_ability(
        obj,
        cost="{3}{G}{G}",
        effect_fn=_team_pump,
        description="{3}{G}{G}: Creatures you control get +X/+X until end of turn, where X is the greatest power among creatures you control.",
    )
    return []


def walkin_closet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Walk-In Closet: lands from GY (continuous). Forgotten Cellar: cast from GY + exile-instead."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Walk-In Closet's static is "You may play lands from your graveyard."
        # On unlock we issue a permanent grant for the controller. The handler
        # treats unset duration as the default ("this_turn"); we want forever.
        return [Event(
            type=EventType.GRANT_PLAY_LANDS_FROM_GRAVEYARD,
            payload={'player': o.controller, 'duration': 'forever'},
            source=o.id, controller=o.controller,
        )]

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Forgotten Cellar: this turn, you may cast spells from your graveyard;
        # this turn, "to graveyard" is replaced with "to exile".
        return [
            Event(type=EventType.GRANT_CAST_FROM_GRAVEYARD,
                  payload={'player': o.controller, 'duration': 'this_turn'},
                  source=o.id, controller=o.controller),
            Event(type=EventType.GRANT_EXILE_INSTEAD_OF_GRAVEYARD,
                  payload={'player': o.controller, 'duration': 'this_turn'},
                  source=o.id, controller=o.controller),
        ]

    def walkin_closet_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Re-grant the lands-from-graveyard permission whenever a turn rolls
        # over, so it remains active while Walk-In Closet is unlocked.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.TURN_START:
                return False
            current = state.objects.get(o.id)
            return current is not None and is_door_unlocked(current, "Walk-In Closet")

        def handler(event: Event, state: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.GRANT_PLAY_LANDS_FROM_GRAVEYARD,
                    payload={'player': o.controller, 'duration': 'this_turn'},
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Walk-In Closet",
        door1_unlock_effect=door1_effect,
        door2_name="Forgotten Cellar",
        door2_cost="{3}{G}{G}",
        door2_unlock_effect=door2_effect,
        extra_setup=walkin_closet_extra,
    )(obj, state)


def wary_watchdog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB or death: surveil 1."""
    def surveil_event() -> Event:
        return Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'count': 1}, source=obj.id)

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [surveil_event()]

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [surveil_event()]

    return [make_etb_trigger(obj, etb_effect), make_death_trigger(obj, death_effect)]


def baseball_bat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — ETB attach to your creature; +1/+1; on attack tap a creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={'source': obj.id, 'effect': 'attach_to_target', 'filter': 'creature_you_control'},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def broodspinner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; ETB surveil 2; {4BG}{T}+sac: tokens equal to types in GY."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'count': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def disturbing_mirth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: optional sac for draw 2; on sac of self, manifest dread."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OPTIONAL_SACRIFICE_FOR_EFFECT,
            payload={'player': obj.controller, 'filter': 'enchantment_or_creature_other',
                     'effect': 'draw', 'count': 2},
            source=obj.id,
        )]

    def sac_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.SACRIFICE and
                event.payload.get('object_id') == obj.id)

    def sac_handler(event: Event, state: GameState):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.MANIFEST_DREAD,
                              payload={'player': obj.controller}, source=obj.id)],
        )
    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=sac_filter, handler=sac_handler,
            duration='until_leaves',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (sac_handler(e, s).new_events or []),
        ),
    ]


def growing_dread_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash; ETB manifest dread; whenever a permanent you control is turned
    face up, put a +1/+1 counter on it."""
    from src.cards.interceptor_helpers import make_turned_face_up_trigger

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD, payload={'player': obj.controller}, source=obj.id)]

    def face_up_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('object_id')
        if not target_id:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'count': 1},
            source=obj.id,
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        # "Whenever a permanent you control is turned face up" — fire for self
        # and any other creature obj.controller controls.
        make_turned_face_up_trigger(obj, face_up_effect, self_or_other_yours="both"),
    ]


def inquisitive_glimmer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: enchantment spells you cast cost {1} less to cast.

    Skipped clauses:
      * 'Unlock costs you pay cost {1} less.' (Engine gap: room/unlock-cost
        is a separate cost path not currently surfaced through QUERY_COST.)
    """
    def applies(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller:
            return False
        return CardType.ENCHANTMENT in card.characteristics.types

    return [make_cost_reduction(obj, applies_to=applies, amount=1)]


def the_jolly_balloon_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste; {1}, {T}: Create a token that's a copy of another target creature
    you control, except it's a 1/1 red Balloon creature in addition to its
    other colors and types and it has flying and haste. Sacrifice it at the
    beginning of the next end step. Activate only as a sorcery.

    Wires the copy-token activated ability. The delayed end-of-next-turn
    sacrifice is an engine gap (delayed-trigger cleanup), so the token
    persists past the end step but the copy itself is correctly created."""
    def _copy_token(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        if not target_id or target_id not in st.objects:
            return []
        # Build the copy with the Balloon subtype + flying/haste add-ons.
        # The card adds Balloon as a subtype (in addition to copied subtypes)
        # and changes the copy to a 1/1 red. flying/haste keywords get layered on.
        return make_copy_token_event(
            target_id=target_id,
            controller=o.controller,
            source_id=o.id,
            add_subtypes={"Balloon"},
            except_power=1, except_toughness=1,
            except_keywords=["flying", "haste"],
        )

    make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=_copy_token,
        description="Copy target creature as a 1/1 red Balloon with flying and haste",
        sorcery_speed=True,
        targets_required=1, target_kind="other_creature_you_control",
    )
    return []


def kaito_bane_of_nightmares_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Planeswalker — ninjutsu, conditional creature, loyalty abilities."""
    # engine gap: planeswalker mechanics
    return []


def nashi_searcher_in_the_dark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace; on combat damage to player, mill that many; pull legendary/enchantment cards."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        amt = int(event.payload.get('amount', 0))
        if amt <= 0:
            return []
        return [Event(type=EventType.MILL,
                      payload={'player': obj.controller, 'count': amt,
                               'pull_to_hand_filter': 'legendary_or_enchantment',
                               'fallback_counter_self': True},
                      source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def niko_light_of_hope_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two Shard tokens; activated copy-from-creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        token = {
            'controller': obj.controller, 'name': 'Shard',
            'types': {CardType.ENCHANTMENT}, 'subtypes': {'Shard'},
            'colors': set(),
        }
        return [
            Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id),
        ]
    return [make_etb_trigger(obj, etb_effect)]


def oblivious_bookworm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End-step optional draw; conditional discard unless face-up event happened this turn."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MAY_PAY_DRAW,
            payload={'player': obj.controller,
                     'effect': 'draw_then_conditional_discard',
                     'condition': 'face_up_event_this_turn'},
            source=obj.id,
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def restricted_office_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Restricted Office: destroy creatures power>=3. Lecture Hall: other permanents you control hexproof."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Destroy all creatures with power 3 or greater.
        events: list[Event] = []
        for cid, gobj in list(st.objects.items()):
            if gobj.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in gobj.characteristics.types:
                continue
            try:
                p = get_power(gobj, st)
            except Exception:
                p = gobj.characteristics.power or 0
            if p is None:
                continue
            if p >= 3:
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': cid},
                    source=o.id, controller=o.controller,
                ))
        return events

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a continuous static ("Lecture Hall"); unlock itself does nothing.
        return []

    def lecture_hall_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # Other permanents you control have hexproof, while Lecture Hall is unlocked.
        def affects_filter(target: GameObject, state: GameState) -> bool:
            current = state.objects.get(o.id)
            if current is None or not is_door_unlocked(current, "Lecture Hall"):
                return False
            if target.id == o.id:
                return False
            if target.zone != ZoneType.BATTLEFIELD:
                return False
            return target.controller == o.controller

        return [make_keyword_grant(o, ['hexproof'], affects_filter)]

    return make_room_setup(
        door1_name="Restricted Office",
        door1_unlock_effect=door1_effect,
        door2_name="Lecture Hall",
        door2_cost="{5}{U}{U}",
        door2_unlock_effect=door2_effect,
        extra_setup=lecture_hall_extra,
    )(obj, state)


def rip_spawn_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival — At the beginning of your second main phase, if Rip is
    tapped, reveal the top X cards of your library, where X is its power.
    Put any number of creature and/or Vehicle cards with different powers
    from among them into your hand. Put the rest on the bottom of your
    library in a random order.
    """
    def survival_effect(event: Event, state: GameState) -> list[Event]:
        # X = Rip's current power (state-time look-up).
        try:
            x = int(get_power(obj, state))
        except Exception:
            x = obj.characteristics.power or 0
        if x <= 0:
            return []

        def _is_creature_or_vehicle(cobj: GameObject, _st: GameState) -> bool:
            chars = cobj.characteristics
            if CardType.CREATURE in (chars.types or set()):
                return True
            subs = chars.subtypes or set()
            return 'Vehicle' in subs

        return reveal_top_n_with_distinct_filter(
            state, obj.controller, obj.id, x,
            filter_fn=_is_creature_or_vehicle,
            distinct_attr='power',
            destination='hand',
            remainder='bottom_random',
            prompt=("Rip — choose any number of creature and/or Vehicle cards "
                    "(with different powers) to put into your hand"),
        )
    return [make_survival_trigger(obj, survival_effect)]


def roaring_furnace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Roaring Furnace: hand-size damage to opp creature. Steaming Sauna: no max hand (SKIPPED) + end-step draw."""
    def door1_effect(o: GameObject, st: GameState) -> list[Event]:
        # Damage = number of cards in your hand to target creature an opponent controls.
        hand = st.zones.get(f"hand_{o.controller}")
        amount = len(hand.objects) if hand else 0
        legal = [
            cid for cid, gobj in st.objects.items()
            if (gobj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in gobj.characteristics.types and
                gobj.controller != o.controller)
        ]
        if not legal or amount <= 0:
            return []

        def _on_choose(choice, selected, st_inner: GameState) -> list[Event]:
            tid = None
            if selected:
                s = selected[0]
                tid = s.get("id") if isinstance(s, dict) else str(s)
            if tid is None:
                return []
            return [Event(
                type=EventType.DAMAGE,
                payload={'source': o.id, 'target': tid, 'amount': amount, 'is_combat': False},
                source=o.id, controller=o.controller,
            )]

        from src.engine.types import PendingChoice
        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt=f"Choose a creature an opponent controls to deal {amount} damage to",
            options=legal,
            source_id=o.id,
            min_choices=1,
            max_choices=1,
            callback_data={"handler": _on_choose},
        )
        return []

    def door2_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # Door 2 is a static + recurring trigger ("Steaming Sauna"); unlock itself does nothing.
        return []

    def steaming_sauna_extra(o: GameObject, st: GameState) -> list[Interceptor]:
        # SKIP "no max hand size" — engine gap (max-hand-size adjustments aren't
        # currently first-class). Wire the end-step draw.
        def filt(event: Event, state: GameState) -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'end_step':
                return False
            if state.active_player != o.controller:
                return False
            current = state.objects.get(o.id)
            return current is not None and is_door_unlocked(current, "Steaming Sauna")

        def handler(event: Event, state: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DRAW,
                    payload={'player': o.controller, 'count': 1},
                    source=o.id, controller=o.controller,
                )],
            )

        return [Interceptor(
            id=new_id(),
            source=o.id,
            controller=o.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration='while_on_battlefield',
            is_triggered_ability=True,
            effect_fn=lambda e, s: (handler(e, s).new_events or []),
        )]

    return make_room_setup(
        door1_name="Roaring Furnace",
        door1_unlock_effect=door1_effect,
        door2_name="Steaming Sauna",
        door2_cost="{3}{U}{U}",
        door2_unlock_effect=door2_effect,
        extra_setup=steaming_sauna_extra,
    )(obj, state)


def smoky_lounge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room — Smoky Lounge: restricted-use {R}{R} (SKIPPED). Misty Salon: X/X Spirit (X = unlocked door names you control)."""
    def door1_effect(_o: GameObject, _st: GameState) -> list[Event]:
        # SKIP: restricted-use mana (mana that may only be spent to cast Room
        # spells and unlock doors) is an engine gap.
        return []

    def door2_effect(o: GameObject, st: GameState) -> list[Event]:
        # Create an X/X blue Spirit creature token with flying, where X is the
        # number of unlocked doors among Rooms you control (count distinct door
        # names across all Rooms the controller controls).
        x = 0
        for gobj in st.objects.values():
            if gobj.zone != ZoneType.BATTLEFIELD:
                continue
            if gobj.controller != o.controller:
                continue
            if 'Room' not in gobj.characteristics.subtypes:
                continue
            doors = getattr(gobj.state, 'unlocked_doors', None)
            if isinstance(doors, list):
                x += len(doors)
        if x <= 0:
            x = 1  # 0/0 tokens die immediately, but keep a safety floor.
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': o.controller, 'name': 'Spirit',
                'power': x, 'toughness': x,
                'colors': {Color.BLUE},
                'types': {CardType.CREATURE},
                'subtypes': {'Spirit'},
                'keywords': ['flying'],
            },
            source=o.id, controller=o.controller,
        )]

    return make_room_setup(
        door1_name="Smoky Lounge",
        door1_unlock_effect=door1_effect,
        door2_name="Misty Salon",
        door2_cost="{3}{U}",
        door2_unlock_effect=door2_effect,
    )(obj, state)


def winter_misanthropic_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward 2; upkeep each player draws 2; Delirium hand-size cap."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': pid, 'count': 2}, source=obj.id)
                for pid in state.players.keys()]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def zimone_allquestioning_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if a land entered this turn and you
    control a prime number of lands, create Primo, the Indivisible (legendary
    0/0 green/blue Fractal token), then put that many +1/+1 counters on it.

    "Land entered" is proxied by ``state.lands_played_this_turn > 0``. The
    engine doesn't yet track lands-that-entered-from-effects (e.g.
    Cultivate-style searches), so this is a tight upper bound on accuracy
    for the common case."""
    PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71}

    def _count_lands(st: GameState, player_id: str) -> int:
        return sum(
            1 for o in st.objects.values()
            if (o.zone == ZoneType.BATTLEFIELD and
                o.controller == player_id and
                CardType.LAND in o.characteristics.types)
        )

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if int(getattr(state, 'lands_played_this_turn', 0) or 0) <= 0:
            return []
        land_count = _count_lands(state, obj.controller)
        if land_count not in PRIMES:
            return []
        return [
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller, 'name': 'Primo, the Indivisible',
                    'power': 0, 'toughness': 0,
                    'colors': {Color.GREEN, Color.BLUE},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Fractal'},
                    'supertypes': {'Legendary'},
                    'counters': {'+1/+1': land_count},
                },
                source=obj.id, controller=obj.controller,
            ),
        ]

    return [make_end_step_trigger(obj, end_step_effect)]


def attackinthebox_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Optional +4/+0 on attack; if so, sacrifice at end step."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OPTIONAL_COST_FOR_EFFECT,
            payload={'source': obj.id, 'effect': 'pump_self_then_delayed_sac',
                     'power_mod': 4, 'toughness_mod': 0},
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_effect)]


def bear_trap_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash; {3}, {T}, Sacrifice this artifact: It deals 3 damage to target creature."""
    make_damage_ability(
        obj, cost="{3}, {T}, Sacrifice this artifact",
        damage=3, target_kind="creature",
        description="Deal 3 damage to target creature",
    )
    return []


def conductive_machete_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — manifest dread + auto-attach. Equipped +2/+1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD,
                      payload={'player': obj.controller, 'then_attach': obj.id},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def dissection_tools_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — manifest dread + auto-attach. Equipped +2/+2 deathtouch lifelink."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD,
                      payload={'player': obj.controller, 'then_attach': obj.id},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def friendly_teddy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, each player draws a card."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': pid, 'count': 1}, source=obj.id)
                for pid in state.players.keys()]
    return [make_death_trigger(obj, death_effect)]


def ghost_vacuum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Exile target card from a graveyard.
    {6}, {T}, Sacrifice: bring exiled creatures back as 1/1 Spirits with flying counter (engine gap).
    """
    def _exile_from_gy(o: GameObject, st: GameState, targets) -> list[Event]:
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
        obj, cost="{T}", effect_fn=_exile_from_gy,
        description="Exile target card from a graveyard",
        targets_required=1, target_kind="card_in_graveyard",
    )
    # engine gap: re-create exiled-with-this creatures as 1/1 Spirits with a flying counter.
    return []


def glimmerlight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment — ETB: create Glimmer token. Equipped +1/+1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller, 'name': 'Glimmer',
                'power': 1, 'toughness': 1,
                'colors': {Color.WHITE},
                'types': {CardType.CREATURE, CardType.ENCHANTMENT},
                'subtypes': {'Glimmer'},
            },
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


def haunted_screen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{7}: Put seven +1/+1 counters on this artifact. It becomes a 0/0 Spirit
    creature in addition to its other types. Activate only once.

    NOTE: 'Activate only once' is approximated with once_per_turn=True. (Real
    rule restricts the ability to a single use over the whole game; the engine
    has no permanent-ability latch yet, so the once-per-turn approximation will
    fire each turn instead of at most once total.)
    Mana abilities ({T}: {W}/{B}; {T},Pay 1 life: {G}/{U}/{R}) are still an
    engine gap — not wired here.
    """
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        events: list[Event] = []
        for _ in range(7):
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id,
                controller=o.controller,
            ))
        becomes_creature(o, st, power=0, toughness=0, subtypes={"Spirit"})
        return events

    make_activated_ability(
        obj,
        cost="{7}",
        effect_fn=effect,
        description="Put seven +1/+1 counters on this artifact. It becomes a 0/0 Spirit creature.",
        once_per_turn=True,
    )
    return []


def keys_to_the_house_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, {T}, Sacrifice this artifact: Search your library for a basic land card,
    reveal it, put it into your hand, then shuffle.
    {3}, {T}, Sacrifice this artifact: Lock or unlock a door of target Room you control
    (engine gap — Room mechanic)."""
    def _basic_to_hand(o: GameObject, st: GameState, targets) -> list[Event]:
        open_library_search(
            st, o.controller, o.id,
            filter_fn=basic_land_filter(),
            destination="hand",
            max_count=1,
            shuffle_after=True,
            reveal=True,
            optional=True,
            prompt="Search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
        )
        return []

    make_activated_ability(
        obj, cost="{1}, {T}, Sacrifice this artifact", effect_fn=_basic_to_hand,
        description="Search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
    )
    # engine gap: Room mechanic (lock/unlock doors).
    return []


def malevolent_chandelier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying; {2}: Put target card from a graveyard on the bottom of its owner's library.
    Activate only as a sorcery."""
    def _gy_to_library_bottom(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        target_obj = st.objects.get(target_id) if isinstance(target_id, str) else None
        owner = target_obj.owner if target_obj else None
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone_type': ZoneType.LIBRARY,
                'to_zone_owner': owner,
                'library_position': 'bottom',
            },
            source=o.id, controller=o.controller,
        )]

    make_activated_ability(
        obj, cost="{2}", effect_fn=_gy_to_library_bottom,
        description="Put target card from a graveyard on the bottom of its owner's library",
        sorcery_speed=True,
        targets_required=1, target_kind="card_in_graveyard",
    )
    return []


def marvin_murderous_mimic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Has all activated abilities of differently-named creatures you control.

    Implemented via the ability-mirror registry (src/engine/activated.py).
    The mirror is consulted at state-time, so creatures entering / leaving
    the battlefield automatically expand / contract Marvin's ability set.
    """
    from src.engine.activated import register_ability_mirror

    def _marvin_mirror_predicate(marvin: GameObject, st: GameState) -> list[GameObject]:
        out: list[GameObject] = []
        for c in st.objects.values():
            if c.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in c.characteristics.types:
                continue
            if c.controller != marvin.controller:
                continue
            if c.id == marvin.id:
                continue
            if c.name == marvin.name:
                continue
            out.append(c)
        return out

    register_ability_mirror(obj, _marvin_mirror_predicate)
    return []


# Note: ``terramorphic_expanse_setup`` is defined further below
# (Phase 4 activated-ability sweep). The earlier strict-noop stub at this
# position was a leftover; removed 2026-05-16. See line ~9485 for the
# real implementation.


# =============================================================================
# PHASE 2B VANILLA-SPELL RESOLVES
# =============================================================================

# Glimmerburst: "Draw two cards. Create a 1/1 white Glimmer enchantment
# creature token."
glimmerburst_resolve = resolve_chain(
    resolve_draw(2),
    resolve_create_token(
        name="Glimmer Token",
        power=1, toughness=1,
        types=[CardType.ENCHANTMENT, CardType.CREATURE],
        subtypes=["Glimmer"],
        colors=[Color.WHITE],
        count=1,
    ),
)

# Midnight Mayhem: "Create three 1/1 red Gremlin creature tokens."
# (Note: the keyword grant to all Gremlins until end of turn is an
# anthem-style temporary effect; tracked as engine gap. Tokens are
# created with the right subtype so the rest can be wired later.)
midnight_mayhem_resolve = resolve_create_token(
    name="Gremlin Token",
    power=1, toughness=1,
    types=[CardType.CREATURE],
    subtypes=["Gremlin"],
    colors=[Color.RED],
    count=3,
)


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ACROBATIC_CHEERLEADER = make_creature(
    name="Acrobatic Cheerleader",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, put a flying counter on it. This ability triggers only once.",
    setup_interceptors=acrobatic_cheerleader_setup,
)

CULT_HEALER = make_creature(
    name="Cult Healer",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Doctor", "Human"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gains lifelink until end of turn.",
    setup_interceptors=cult_healer_setup
)

DAZZLING_THEATER = make_enchantment(
    name="Dazzling Theater",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Dazzling Theater {3}{W}:\nCreature spells you cast have convoke. (Your creatures can help cast those spells. Each creature you tap while casting a creature spell pays for {1} or one mana of that creature's color.)\n//\nProp Room {2}{W}:\nUntap each creature you control during each other player's untap step.",
    subtypes={"Room"},
    setup_interceptors=dazzling_theater_setup,
)

DOLLMAKERS_SHOP = make_enchantment(
    name="Dollmaker's Shop",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Dollmaker's Shop {1}{W}:\nWhenever one or more non-Toy creatures you control attack a player, create a 1/1 white Toy artifact creature token.\n//\nPorcelain Gallery {4}{W}{W}:\nCreatures you control have base power and toughness each equal to the number of creatures you control.",
    subtypes={"Room"},
    setup_interceptors=dollmakers_shop_setup,
)

EMERGE_FROM_THE_COCOON = make_sorcery(
    name="Emerge from the Cocoon",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield. You gain 3 life.",
)


def enduring_innocence_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Enduring Innocence abilities:
    1. Lifelink (handled via keyword/damage interceptor)
    2. Whenever one or more other creatures you control with power 2 or less enter,
       draw a card. This ability triggers only once each turn.
    3. When dies, if it was a creature, return as enchantment.
    """
    is_creature = CardType.CREATURE in obj.characteristics.types

    # Track if we've triggered this turn (for once-per-turn limit)
    triggered_this_turn = [False]

    # Trigger 1: Lifelink - convert damage dealt to life gain
    def lifelink_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('source') == source.id

    def lifelink_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id
        )]

    lifelink_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: lifelink_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=lifelink_effect(e, s)
        ),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=lifelink_effect,
    )

    # Trigger 2: Draw when small creatures enter (once per turn)
    def small_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if triggered_this_turn[0]:
            return False
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Check if the entering object is another creature we control with power <= 2
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:  # "other creatures"
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source.controller:
            return False
        if CardType.CREATURE not in entering_obj.characteristics.types:
            return False
        power = get_power(entering_obj, state)
        return power <= 2

    def draw_on_small_creature(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn[0] = True
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )]

    small_creature_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: small_creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draw_on_small_creature(e, s)
        ),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=draw_on_small_creature,
    )

    # Reset once-per-turn at turn start
    def turn_start_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.TURN_START:
            return False
        return event.payload.get('player') == source.controller

    def reset_trigger(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn[0] = False
        return []

    turn_reset_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: turn_start_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=reset_trigger(e, s)
        ),
        duration='while_on_battlefield'
    )

    interceptors = [lifelink_trigger, small_creature_trigger, turn_reset_interceptor]

    # Trigger 3: Return as enchantment when dies (only if currently a creature)
    if is_creature:
        def death_effect(event: Event, state: GameState) -> list[Event]:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone': f'graveyard_{obj.owner}',
                    'to_zone': 'battlefield',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'as_enchantment_only': True,
                },
                source=obj.id
            )]

        death_trigger = make_death_trigger(obj, death_effect)
        interceptors.append(death_trigger)

    return interceptors


ENDURING_INNOCENCE = make_enchantment_creature(
    name="Enduring Innocence",
    power=2, toughness=1,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Glimmer", "Sheep"},
    text="Lifelink\nWhenever one or more other creatures you control with power 2 or less enter, draw a card. This ability triggers only once each turn.\nWhen Enduring Innocence dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
    setup_interceptors=enduring_innocence_setup
)

def _ethereal_armor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted creature gets +1/+1 per enchantment you control and first strike."""
    base = make_aura_setup(keywords=["first strike"])(obj, state)
    def mod_fn(source, target, st):
        n = count_permanents_of_type(source.controller, CardType.ENCHANTMENT, st)
        return (n, n)
    return base + make_attached_dynamic_pt_boost(obj, mod_fn)


ETHEREAL_ARMOR = make_enchantment(
    name="Ethereal Armor",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +1/+1 for each enchantment you control and has first strike.",
    subtypes={"Aura"},
    setup_interceptors=_ethereal_armor_setup,
)

def _exorcise_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Exorcise after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    target_types = target.characteristics.types
    is_artifact = CardType.ARTIFACT in target_types
    is_enchantment = CardType.ENCHANTMENT in target_types
    is_big_creature = (CardType.CREATURE in target_types and
                       get_power(target, state) >= 4)

    if not (is_artifact or is_enchantment or is_big_creature):
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'battlefield',
            'to_zone': f'exile_{target.owner}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.EXILE
        },
        source=choice.source_id
    )]


def exorcise_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Exorcise: Exile target artifact, enchantment, or creature with power 4+ (Phase 5b)."""
    return _dsk_exile_targets()(targets, state)


def _exorcise_target_filter(obj: GameObject, state: GameState) -> bool:
    """Custom filter: artifact, enchantment, or creature with power >= 4."""
    types = obj.characteristics.types
    if CardType.ARTIFACT in types or CardType.ENCHANTMENT in types:
        return True
    if CardType.CREATURE in types and get_power(obj, state) >= 4:
        return True
    return False


EXORCISE = make_sorcery(
    name="Exorcise",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target artifact, enchantment, or creature with power 4 or greater.",
    resolve=exorcise_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.CREATURE},
                custom_filter=_exorcise_target_filter,
            ),
            count=1,
            label="target artifact, enchantment, or creature with power 4 or greater",
        ),
    ],
)

FEAR_OF_ABDUCTION = make_enchantment_creature(
    name="Fear of Abduction",
    power=5, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="As an additional cost to cast this spell, exile a creature you control.\nFlying\nWhen this creature enters, exile target creature an opponent controls.\nWhen this creature leaves the battlefield, put each card exiled with it into its owner's hand.",
    setup_interceptors=fear_of_abduction_setup
)

FEAR_OF_IMMOBILITY = make_enchantment_creature(
    name="Fear of Immobility",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="When this creature enters, tap up to one target creature. If an opponent controls that creature, put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=fear_of_immobility_setup,
)

FEAR_OF_SURVEILLANCE = make_enchantment_creature(
    name="Fear of Surveillance",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="Vigilance\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=fear_of_surveillance_setup,
)

FRIENDLY_GHOST = make_creature(
    name="Friendly Ghost",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nWhen this creature enters, target creature gets +2/+4 until end of turn.",
    setup_interceptors=friendly_ghost_setup
)

GHOSTLY_DANCERS = make_creature(
    name="Ghostly Dancers",
    power=2, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nWhen this creature enters, return an enchantment card from your graveyard to your hand or unlock a locked door of a Room you control.\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, create a 3/1 white Spirit creature token with flying.",
    setup_interceptors=ghostly_dancers_setup
)

GLIMMER_SEEKER = make_creature(
    name="Glimmer Seeker",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, draw a card if you control a Glimmer creature. If you don't control a Glimmer creature, create a 1/1 white Glimmer enchantment creature token.",
    setup_interceptors=glimmer_seeker_setup,
)

GRAND_ENTRYWAY = make_enchantment(
    name="Grand Entryway",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Grand Entryway {1}{W}:\nWhen you unlock this door, create a 1/1 white Glimmer enchantment creature token.\n//\nElegant Rotunda {2}{W}:\nWhen you unlock this door, put a +1/+1 counter on each of up to two target creatures.",
    subtypes={"Room"},
    setup_interceptors=grand_entryway_setup,
)

HARDENED_ESCORT = make_creature(
    name="Hardened Escort",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, another target creature you control gets +1/+0 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    setup_interceptors=hardened_escort_setup,
)

def _jump_scare_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Jump Scare after target selection."""
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
            type=EventType.PUMP,
            payload={'object_id': target_id, 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'flying', 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def jump_scare_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Jump Scare: Target creature gets +2/+2, gains flying until EOT (Phase 5b).

    NOTE: the "becomes a Horror enchantment creature" type change is an engine
    gap; the legacy execute helper already dropped it.
    """
    return resolve_chain(
        _dsk_pump_targets(2, 2),
        _dsk_grant_keywords_to_targets('flying'),
    )(targets, state)


JUMP_SCARE = make_instant(
    name="Jump Scare",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Until end of turn, target creature gets +2/+2, gains flying, and becomes a Horror enchantment creature in addition to its other types.",
    resolve=jump_scare_resolve,
    target_requirements=[target_creature(count=1)],
)

LEYLINE_OF_HOPE = make_enchantment(
    name="Leyline of Hope",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nIf you would gain life, you gain that much life plus 1 instead.\nAs long as you have at least 7 life more than your starting life total, creatures you control get +2/+2.",
    setup_interceptors=leyline_of_hope_setup,
)

LIONHEART_GLIMMER = make_enchantment_creature(
    name="Lionheart Glimmer",
    power=2, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Glimmer"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhenever you attack, creatures you control get +1/+1 until end of turn.",
    setup_interceptors=lionheart_glimmer_setup,
)

LIVING_PHONE = make_artifact_creature(
    name="Living Phone",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Toy"},
    text="When this creature dies, look at the top five cards of your library. You may reveal a creature card with power 2 or less from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=living_phone_setup
)

OPTIMISTIC_SCAVENGER = make_creature(
    name="Optimistic Scavenger",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, put a +1/+1 counter on target creature.",
    setup_interceptors=optimistic_scavenger_setup
)

ORPHANS_OF_THE_WHEAT = make_creature(
    name="Orphans of the Wheat",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="Whenever this creature attacks, tap any number of untapped creatures you control. This creature gets +1/+1 until end of turn for each creature tapped this way.",
    setup_interceptors=orphans_of_the_wheat_setup
)

OVERLORD_OF_THE_MISTMOORS = make_enchantment_creature(
    name="Overlord of the Mistmoors",
    power=6, toughness=6,
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{2}{W}{W} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, create two 2/1 white Insect creature tokens with flying.",
    setup_interceptors=overlord_of_the_mistmoors_setup,
)

PATCHED_PLAYTHING = make_artifact_creature(
    name="Patched Plaything",
    power=4, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Toy"},
    text="Double strike\nThis creature enters with two -1/-1 counters on it if you cast it from your hand.",
    setup_interceptors=patched_plaything_setup,
)

def possessed_goat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}, Discard a card: Put three +1/+1 counters on this creature... Activate only once.

    Wires the +1/+1 counter portion (engine gap: become-Demon type/color overlay)."""
    make_counter_ability(
        obj, cost="{3}, Discard a card",
        counter_type="+1/+1", amount=3, target_self=True,
        once_per_turn=True,
        description="Put three +1/+1 counters on this creature",
    )
    return []


POSSESSED_GOAT = make_creature(
    name="Possessed Goat",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Goat"},
    text="{3}, Discard a card: Put three +1/+1 counters on this creature and it becomes a black Demon in addition to its other colors and types. Activate only once.",
    setup_interceptors=possessed_goat_setup,
)

RELUCTANT_ROLE_MODEL = make_creature(
    name="Reluctant Role Model",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, put a flying, lifelink, or +1/+1 counter on it.\nWhenever this creature or another creature you control dies, if it had counters on it, put those counters on up to one target creature.",
    setup_interceptors=reluctant_role_model_setup,
)

SAVIOR_OF_THE_SMALL = make_creature(
    name="Savior of the Small",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Kor", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, return target creature card with mana value 3 or less from your graveyard to your hand.",
    setup_interceptors=savior_of_the_small_setup,
)

SEIZED_FROM_SLUMBER = make_instant(
    name="Seized from Slumber",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped creature.\nDestroy target creature.",
)

SHARDMAGES_RESCUE = make_enchantment(
    name="Shardmage's Rescue",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Flash\nEnchant creature you control\nAs long as this Aura entered this turn, enchanted creature has hexproof.\nEnchanted creature gets +1/+1.",
    subtypes={"Aura"},
    setup_interceptors=shardmages_rescue_setup,
)

SHELTERED_BY_GHOSTS = make_enchantment(
    name="Sheltered by Ghosts",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature you control\nWhen this Aura enters, exile target nonland permanent an opponent controls until this Aura leaves the battlefield.\nEnchanted creature gets +1/+0 and has lifelink and ward {2}.",
    subtypes={"Aura"},
    setup_interceptors=sheltered_by_ghosts_setup,
)

SHEPHERDING_SPIRITS = make_creature(
    name="Shepherding Spirits",
    power=4, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=shepherding_spirits_setup,
)
SHEPHERDING_SPIRITS.setup_in_hand = make_cycling_setup("{2}", typecycling="Plains")

def _split_up_execute_mode(choice, selected, state: GameState) -> list[Event]:
    """
    Execute the chosen mode for Split Up after player selection.

    Args:
        choice: The PendingChoice that was answered
        selected: List containing the selected mode dict
        state: Current game state

    Returns:
        List of OBJECT_DESTROYED events for the chosen set of creatures
    """
    # selected[0] is the mode dict, e.g. {"index": 0, "text": "Destroy all tapped creatures."}
    selected_mode = selected[0]
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode
    destroy_tapped = mode_index == 0

    # Gather creatures to destroy based on chosen mode
    events = []
    for obj_id, obj in state.objects.items():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue

        # Mode 0 = tapped, Mode 1 = untapped
        if destroy_tapped and obj.state.tapped:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj.id},
                source=choice.source_id
            ))
        elif not destroy_tapped and not obj.state.tapped:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj.id},
                source=choice.source_id
            ))

    return events


def split_up_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Split Up: Choose one —
    • Destroy all tapped creatures.
    • Destroy all untapped creatures.

    Creates a modal choice for the player. Returns empty events to pause resolution.
    The actual destruction happens when the player submits their choice.
    """
    # Find the spell on the stack to determine who cast it
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Split Up":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "split_up_spell"

    # Create modal choice for the player
    modes = [
        {"index": 0, "text": "Destroy all tapped creatures."},
        {"index": 1, "text": "Destroy all untapped creatures."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Split Up - Choose one:"
    )

    # Override choice_type to use custom handler path in game.py
    # (modal choices don't call handlers by default, they just store selection)
    choice.choice_type = "modal_with_callback"

    # Add the callback handler to execute the chosen mode
    choice.callback_data['handler'] = _split_up_execute_mode

    # Return empty events to pause resolution until choice is submitted
    return []


SPLIT_UP = make_sorcery(
    name="Split Up",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Destroy all tapped creatures.\n• Destroy all untapped creatures.",
    resolve=split_up_resolve,
)

SPLITSKIN_DOLL = make_artifact_creature(
    name="Splitskin Doll",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Toy"},
    text="When this creature enters, draw a card. Then discard a card unless you control another creature with power 2 or less.",
    setup_interceptors=splitskin_doll_setup
)

SURGICAL_SUITE = make_enchantment(
    name="Surgical Suite",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Surgical Suite {1}{W}:\nWhen you unlock this door, return target creature card with mana value 3 or less from your graveyard to the battlefield.\n//\nHospital Room {3}{W}:\nWhenever you attack, put a +1/+1 counter on target attacking creature.",
    subtypes={"Room"},
    setup_interceptors=surgical_suite_setup,
)

TOBY_BEASTIE_BEFRIENDER = make_creature(
    name="Toby, Beastie Befriender",
    power=1, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Toby enters, create a 4/4 white Beast creature token with \"This token can't attack or block alone.\"\nAs long as you control four or more creature tokens, creature tokens you control have flying.",
    setup_interceptors=toby_beastie_befriender_setup
)

TRAPPED_IN_THE_SCREEN = make_enchantment(
    name="Trapped in the Screen",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Ward {2} (Whenever this enchantment becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this enchantment enters, exile target artifact, creature, or enchantment an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=trapped_in_the_screen_setup,
)

UNIDENTIFIED_HOVERSHIP = make_artifact(
    name="Unidentified Hovership",
    mana_cost="{1}{W}{W}",
    text="Flying\nWhen this Vehicle enters, exile up to one target creature with toughness 5 or less.\nWhen this Vehicle leaves the battlefield, the exiled card's owner manifests dread.\nCrew 1",
    subtypes={"Vehicle"},
    setup_interceptors=unidentified_hovership_setup,
)

UNSETTLING_TWINS = make_creature(
    name="Unsettling Twins",
    power=2, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="When this creature enters, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    setup_interceptors=unsettling_twins_setup,
)

UNWANTED_REMAKE = make_instant(
    name="Unwanted Remake",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Destroy target creature. Its controller manifests dread. (That player looks at the top two cards of their library, then puts one onto the battlefield face down as a 2/2 creature and the other into their graveyard. If it's a creature card, it can be turned face up any time for its mana cost.)",
)

VETERAN_SURVIVOR = make_creature(
    name="Veteran Survivor",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, exile up to one target card from a graveyard.\nAs long as there are three or more cards exiled with this creature, it gets +3/+3 and has hexproof. (It can't be the target of spells or abilities your opponents control.)",
    setup_interceptors=veteran_survivor_setup,
)

THE_WANDERING_RESCUER = make_creature(
    name="The Wandering Rescuer",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Samurai"},
    supertypes={"Legendary"},
    text="Flash\nConvoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nDouble strike\nOther tapped creatures you control have hexproof.",
    setup_interceptors=the_wandering_rescuer_setup,
)

ABHORRENT_OCULUS = make_creature(
    name="Abhorrent Oculus",
    power=5, toughness=5,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Eye"},
    text="As an additional cost to cast this spell, exile six cards from your graveyard.\nFlying\nAt the beginning of each opponent's upkeep, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    setup_interceptors=abhorrent_oculus_setup,
)

BOTTOMLESS_POOL = make_enchantment(
    name="Bottomless Pool",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Bottomless Pool {U}:\nWhen you unlock this door, return up to one target creature to its owner's hand.\n//\nLocker Room {4}{U}:\nWhenever one or more creatures you control deal combat damage to a player, draw a card.",
    subtypes={"Room"},
    setup_interceptors=bottomless_pool_setup,
)

CENTRAL_ELEVATOR = make_enchantment(
    name="Central Elevator",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Central Elevator {3}{U}:\nWhen you unlock this door, search your library for a Room card that doesn't have the same name as a Room you control, reveal it, put it into your hand, then shuffle.\n//\nPromising Stairs {2}{U}:\nAt the beginning of your upkeep, surveil 1. You win the game if there are eight or more different names among unlocked doors of Rooms you control.",
    subtypes={"Room"},
    setup_interceptors=central_elevator_setup,
)

CLAMMY_PROWLER = make_enchantment_creature(
    name="Clammy Prowler",
    power=2, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Horror"},
    text="Whenever this creature attacks, another target attacking creature can't be blocked this turn.",
    setup_interceptors=clammy_prowler_setup
)

CREEPING_PEEPER = make_creature(
    name="Creeping Peeper",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Eye"},
    text="{T}: Add {U}. Spend this mana only to cast an enchantment spell, unlock a door, or turn a permanent face up.",
    setup_interceptors=creeping_peeper_setup,
)

CURSED_WINDBREAKER = make_artifact(
    name="Cursed Windbreaker",
    mana_cost="{2}{U}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature has flying.\nEquip {3}",
    subtypes={"Equipment"},
    setup_interceptors=cursed_windbreaker_setup,
)

DAGGERMAW_MEGALODON = make_creature(
    name="Daggermaw Megalodon",
    power=5, toughness=7,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Shark"},
    text="Vigilance\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=daggermaw_megalodon_setup,
)
DAGGERMAW_MEGALODON.setup_in_hand = make_cycling_setup("{2}", typecycling="Island")

DONT_MAKE_A_SOUND = make_instant(
    name="Don't Make a Sound",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If they do, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

DUSKMOURNS_DOMINATION = make_enchantment(
    name="Duskmourn's Domination",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nYou control enchanted creature.\nEnchanted creature gets -3/-0 and loses all abilities.",
    subtypes={"Aura"},
    setup_interceptors=duskmourns_domination_setup,
)


def enduring_curiosity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Enduring Curiosity abilities:
    1. Whenever a creature you control deals combat damage to a player, draw a card.
    2. When Enduring Curiosity dies, if it was a creature, return it to the battlefield
       as an enchantment (not a creature).

    Note: When this returns from graveyard as an enchantment (CardType.CREATURE removed),
    setup is called again but will skip the death trigger since it's no longer a creature.
    """
    # Check if currently a creature (for conditional death trigger)
    is_creature = CardType.CREATURE in obj.characteristics.types

    # Trigger 1: Draw on combat damage from any creature you control
    def combat_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        # Check if damage is combat damage
        if not event.payload.get('is_combat_damage', False):
            return False
        # Check if target is a player
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return False
        # Check if source is a creature we control
        damage_source_id = event.payload.get('source')
        damage_source = state.objects.get(damage_source_id)
        if not damage_source:
            return False
        if damage_source.controller != source.controller:
            return False
        if CardType.CREATURE not in damage_source.characteristics.types:
            return False
        return True

    def draw_on_combat_damage(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )]

    combat_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: combat_damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draw_on_combat_damage(e, s)
        ),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=draw_on_combat_damage,
    )

    interceptors = [combat_trigger]

    # Trigger 2: Return as enchantment when dies (only if currently a creature)
    if is_creature:
        def death_effect(event: Event, state: GameState) -> list[Event]:
            # Return to battlefield as an enchantment only
            # This is a special zone change that modifies the object
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone': f'graveyard_{obj.owner}',
                    'to_zone': 'battlefield',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'as_enchantment_only': True,  # Flag to remove creature type
                },
                source=obj.id
            )]

        death_trigger = make_death_trigger(obj, death_effect)
        interceptors.append(death_trigger)

    return interceptors


ENDURING_CURIOSITY = make_enchantment_creature(
    name="Enduring Curiosity",
    power=4, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Cat", "Glimmer"},
    text="Flash\nWhenever a creature you control deals combat damage to a player, draw a card.\nWhen Enduring Curiosity dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
    setup_interceptors=enduring_curiosity_setup
)

ENTER_THE_ENIGMA = make_sorcery(
    name="Enter the Enigma",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature can't be blocked this turn.\nDraw a card.",
)

ENTITY_TRACKER = make_creature(
    name="Entity Tracker",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="Flash\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, draw a card.",
    setup_interceptors=entity_tracker_setup
)

ERRATIC_APPARITION = make_creature(
    name="Erratic Apparition",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying, vigilance\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +1/+1 until end of turn.",
    setup_interceptors=erratic_apparition_setup
)

FEAR_OF_FAILED_TESTS = make_enchantment_creature(
    name="Fear of Failed Tests",
    power=2, toughness=7,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Whenever this creature deals combat damage to a player, draw that many cards.",
    setup_interceptors=fear_of_failed_tests_setup
)

FEAR_OF_FALLING = make_enchantment_creature(
    name="Fear of Falling",
    power=4, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Flying\nWhenever this creature attacks, target creature defending player controls gets -2/-0 and loses flying until your next turn.",
    setup_interceptors=fear_of_falling_setup
)

FEAR_OF_IMPOSTORS = make_enchantment_creature(
    name="Fear of Impostors",
    power=3, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Flash\nWhen this creature enters, counter target spell. Its controller manifests dread. (That player looks at the top two cards of their library, then puts one onto the battlefield face down as a 2/2 creature and the other into their graveyard. If it's a creature card, it can be turned face up any time for its mana cost.)",
    setup_interceptors=fear_of_impostors_setup,
)

FEAR_OF_ISOLATION = make_enchantment_creature(
    name="Fear of Isolation",
    power=2, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="As an additional cost to cast this spell, return a permanent you control to its owner's hand.\nFlying",
    setup_interceptors=fear_of_isolation_setup,
)

FLOODPITS_DROWNER = make_creature(
    name="Floodpits Drowner",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk"},
    text="Flash\nVigilance\nWhen this creature enters, tap target creature an opponent controls and put a stun counter on it.\n{1}{U}, {T}: Shuffle this creature and target creature with a stun counter on it into their owners' libraries.",
    setup_interceptors=floodpits_drowner_setup
)

def _get_out_mode_counter(state, caster_id, spell_id, targets=None):
    """Get Out mode 1: counter target creature/enchantment spell."""
    if not targets:
        return []
    return [Event(
        type=EventType.SPELL_COUNTERED,
        payload={'spell_id': targets[0].id},
        source=spell_id, controller=caster_id,
    )]


def _get_out_mode_return(state, caster_id, spell_id, targets=None):
    """Get Out mode 2: return one or two creatures/enchantments you own to hand."""
    if not targets:
        return []
    events: list[Event] = []
    for t in targets:
        target = state.objects.get(t.id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': t.id,
                    'from_zone': 'battlefield',
                    'to_zone': f'hand_{target.owner}',
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.HAND,
                },
                source=spell_id, controller=caster_id,
            ))
    return events


GET_OUT = make_instant(
    name="Get Out",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Counter target creature or enchantment spell.\n• Return one or two target creatures and/or enchantments you own to your hand.",
    resolve=make_modal_resolve(
        "Get Out",
        modes=[
            ModeSpec(
                "Counter target creature or enchantment spell",
                _get_out_mode_counter,
                target_requirement=TargetRequirement(
                    filter=TargetFilter(
                        types={CardType.CREATURE, CardType.ENCHANTMENT},
                        zones=[ZoneType.STACK],
                    ),
                    count=1,
                    label="target creature or enchantment spell",
                ),
            ),
            ModeSpec(
                "Return one or two target creatures and/or enchantments you own to your hand",
                _get_out_mode_return,
                target_requirement=TargetRequirement(
                    filter=TargetFilter(
                        types={CardType.CREATURE, CardType.ENCHANTMENT},
                        controller='you',
                    ),
                    count=2, count_type='up_to', optional=False,
                    label="one or two target creatures and/or enchantments you own",
                ),
            ),
        ],
        min_modes=1, max_modes=1,
    ),
)

GHOSTLY_KEYBEARER = make_creature(
    name="Ghostly Keybearer",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying\nWhenever this creature deals combat damage to a player, unlock a locked door of up to one target Room you control.",
    setup_interceptors=ghostly_keybearer_setup
)

GLIMMERBURST = make_instant(
    name="Glimmerburst",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Create a 1/1 white Glimmer enchantment creature token.",
    resolve=glimmerburst_resolve,
)

LEYLINE_OF_TRANSFORMATION = make_enchantment(
    name="Leyline of Transformation",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nAs this enchantment enters, choose a creature type.\nCreatures you control are the chosen type in addition to their other types. The same is true for creature spells you control and creature cards you own that aren't on the battlefield.",
    setup_interceptors=leyline_of_transformation_setup,
)

MARINA_VENDRELLS_GRIMOIRE = make_artifact(
    name="Marina Vendrell's Grimoire",
    mana_cost="{5}{U}",
    text="When Marina Vendrell's Grimoire enters, if you cast it, draw five cards.\nYou have no maximum hand size and don't lose the game for having 0 or less life.\nWhenever you gain life, draw that many cards.\nWhenever you lose life, discard that many cards. Then if you have no cards in hand, you lose the game.",
    supertypes={"Legendary"},
    setup_interceptors=marina_vendrells_grimoire_setup,
)

MEAT_LOCKER = make_enchantment(
    name="Meat Locker",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Meat Locker {2}{U}:\nWhen you unlock this door, tap up to one target creature and put two stun counters on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\n//\nDrowned Diner {3}{U}{U}:\nWhen you unlock this door, draw three cards, then discard a card.",
    subtypes={"Room"},
    setup_interceptors=meat_locker_setup,
)

THE_MINDSKINNER = make_enchantment_creature(
    name="The Mindskinner",
    power=10, toughness=1,
    mana_cost="{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    supertypes={"Legendary"},
    text="The Mindskinner can't be blocked.\nIf a source you control would deal damage to an opponent, prevent that damage and each opponent mills that many cards.",
    setup_interceptors=the_mindskinner_setup,
)

MIRROR_ROOM = make_enchantment(
    name="Mirror Room",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Mirror Room {2}{U}:\nWhen you unlock this door, create a token that's a copy of target creature you control, except it's a Reflection in addition to its other creature types.\n//\nFractured Realm {5}{U}{U}:\nIf a triggered ability of a permanent you control triggers, that ability triggers an additional time.",
    subtypes={"Room"},
    setup_interceptors=mirror_room_setup,
)

OVERLORD_OF_THE_FLOODPITS = make_enchantment_creature(
    name="Overlord of the Floodpits",
    power=5, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{1}{U}{U} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nFlying\nWhenever this permanent enters or attacks, draw two cards, then discard a card.",
    setup_interceptors=overlord_of_the_floodpits_setup,
)

PARANORMAL_ANALYST = make_creature(
    name="Paranormal Analyst",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="Whenever you manifest dread, put a card you put into your graveyard this way into your hand.",
    setup_interceptors=paranormal_analyst_setup,
)

PIRANHA_FLY = make_creature(
    name="Piranha Fly",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Insect"},
    text="Flying\nThis creature enters tapped.",
    setup_interceptors=piranha_fly_setup,
)

SCRABBLING_SKULLCRAB = make_creature(
    name="Scrabbling Skullcrab",
    power=0, toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Crab", "Skeleton"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, target player mills two cards. (They put the top two cards of their library into their graveyard.)",
    setup_interceptors=scrabbling_skullcrab_setup,
)

SILENT_HALLCREEPER = make_enchantment_creature(
    name="Silent Hallcreeper",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Horror"},
    text="This creature can't be blocked.\nWhenever this creature deals combat damage to a player, choose one that hasn't been chosen —\n• Put two +1/+1 counters on this creature.\n• Draw a card.\n• This creature becomes a copy of another target creature you control.",
    setup_interceptors=silent_hallcreeper_setup,
)

STALKED_RESEARCHER = make_creature(
    name="Stalked Researcher",
    power=3, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Defender\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature can attack this turn as though it didn't have defender.",
    setup_interceptors=stalked_researcher_setup
)

STAY_HIDDEN_STAY_SILENT = make_enchantment(
    name="Stay Hidden, Stay Silent",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\n{4}{U}{U}: Shuffle enchanted creature into its owner's library, then manifest dread. Activate only as a sorcery.",
    subtypes={"Aura"},
    setup_interceptors=stay_hidden_stay_silent_setup,
)

THE_TALE_OF_TAMIYO = make_enchantment(
    name="The Tale of Tamiyo",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III — Mill two cards. If two cards that share a card type were milled this way, draw a card and repeat this process.\nIV — Exile any number of target instant, sorcery, and/or Tamiyo planeswalker cards from your graveyard. Copy them. You may cast any number of the copies.",
    subtypes={"Saga"},
    supertypes={"Legendary"},
    setup_interceptors=the_tale_of_tamiyo_setup,
)

TUNNEL_SURVEYOR = make_creature(
    name="Tunnel Surveyor",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="When this creature enters, create a 1/1 white Glimmer enchantment creature token.",
    setup_interceptors=tunnel_surveyor_setup
)

def _twist_reality_target_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Twist Reality mode 0 (counter spell) after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.SPELL_COUNTERED,
        payload={'spell_id': target_id},
        source=choice.source_id
    )]


def _twist_reality_mode_selected(choice, selected, state: GameState) -> list[Event]:
    """Handle Twist Reality mode selection."""
    selected_mode = selected[0]
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    if mode_index == 1:
        # Mode 1: Manifest dread (no targeting needed)
        return [Event(
            type=EventType.MANIFEST_DREAD,
            payload={'player': choice.player},
            source=choice.source_id
        )]

    # Mode 0: Counter target spell
    stack_zone = state.zones.get('stack')
    legal_targets = []
    if stack_zone:
        for obj_id in stack_zone.objects:
            if obj_id != choice.source_id:
                obj = state.objects.get(obj_id)
                if obj and obj.zone == ZoneType.STACK:
                    legal_targets.append(obj_id)

    if not legal_targets:
        return []

    target_choice = create_target_choice(
        state=state,
        player_id=choice.player,
        source_id=choice.source_id,
        legal_targets=legal_targets,
        prompt="Twist Reality - Choose a spell to counter",
        min_targets=1,
        max_targets=1,
        callback_data={'handler': _twist_reality_target_execute}
    )

    return []


def twist_reality_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Twist Reality: Choose one -
    - Counter target spell.
    - Manifest dread.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Twist Reality":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "twist_reality_spell"

    modes = [
        {"index": 0, "text": "Counter target spell."},
        {"index": 1, "text": "Manifest dread."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Twist Reality - Choose one:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _twist_reality_mode_selected

    return []


TWIST_REALITY = make_instant(
    name="Twist Reality",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Counter target spell.\n• Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    resolve=twist_reality_resolve,
)

UNABLE_TO_SCREAM = make_enchantment(
    name="Unable to Scream",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature loses all abilities and is a Toy artifact creature with base power and toughness 0/2 in addition to its other types.\nAs long as enchanted creature is face down, it can't be turned face up.",
    subtypes={"Aura"},
    setup_interceptors=unable_to_scream_setup,
)

UNDERWATER_TUNNEL = make_enchantment(
    name="Underwater Tunnel",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Underwater Tunnel {U}:\nWhen you unlock this door, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n//\nSlimy Aquarium {3}{U}:\nWhen you unlock this door, manifest dread, then put a +1/+1 counter on that creature.",
    subtypes={"Room"},
    setup_interceptors=underwater_tunnel_setup,
)

def _unnerving_grasp_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Unnerving Grasp after target selection."""
    events = []

    # Bounce target if one was selected
    if selected:
        target_id = selected[0]
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone': 'battlefield',
                    'to_zone': f'hand_{target.owner}',
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.HAND
                },
                source=choice.source_id
            ))

    # Always manifest dread
    events.append(Event(
        type=EventType.MANIFEST_DREAD,
        payload={'player': choice.player},
        source=choice.source_id
    ))

    return events


def unnerving_grasp_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Unnerving Grasp (Phase 5b): Return up to one nonland permanent + manifest dread."""
    spell = _dsk_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _dsk_spell_caster_id(state)
    events: list[Event] = []
    # Bounce chosen target (if any — count_type='up_to' allows zero).
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
                'from_zone': 'battlefield',
                'to_zone': f'hand_{obj.owner}',
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.HAND,
            },
            source=source_id,
        ))
    # Always manifest dread.
    if caster is not None:
        events.append(Event(
            type=EventType.MANIFEST_DREAD,
            payload={'player': caster},
            source=source_id,
        ))
    return events


def _nonland_permanent_filter(obj: GameObject, state: GameState) -> bool:
    """Custom filter for 'target nonland permanent'."""
    return CardType.LAND not in obj.characteristics.types


UNNERVING_GRASP = make_sorcery(
    name="Unnerving Grasp",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Return up to one target nonland permanent to its owner's hand. Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    resolve=unnerving_grasp_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER},
                custom_filter=_nonland_permanent_filter,
            ),
            count=1,
            count_type='up_to',
            label="target nonland permanent",
        ),
    ],
)

UNWILLING_VESSEL = make_creature(
    name="Unwilling Vessel",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Vigilance\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, put a possession counter on this creature.\nWhen this creature dies, create an X/X blue Spirit creature token with flying, where X is the number of counters on this creature.",
    setup_interceptors=unwilling_vessel_setup
)

def _vanish_from_sight_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Vanish from Sight after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [
        Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone': 'battlefield',
                'to_zone': f'library_{target.owner}',
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.LIBRARY,
                'library_position': 'top_or_bottom'  # Owner chooses
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.SURVEIL,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        )
    ]

    return events


def vanish_from_sight_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Vanish from Sight (Phase 5b): Library-top/bottom + surveil 1."""
    spell = _dsk_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _dsk_spell_caster_id(state)
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
                'from_zone': 'battlefield',
                'to_zone': f'library_{obj.owner}',
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.LIBRARY,
                'library_position': 'top_or_bottom',
            },
            source=source_id,
        ))
    if caster is not None:
        events.append(Event(
            type=EventType.SURVEIL,
            payload={'player': caster, 'amount': 1},
            source=source_id,
        ))
    return events


VANISH_FROM_SIGHT = make_instant(
    name="Vanish from Sight",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target nonland permanent's owner puts it on their choice of the top or bottom of their library. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    resolve=vanish_from_sight_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(
                types={CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER},
                custom_filter=_nonland_permanent_filter,
            ),
            count=1,
            label="target nonland permanent",
        ),
    ],
)

APPENDAGE_AMALGAM = make_enchantment_creature(
    name="Appendage Amalgam",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flash\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=appendage_amalgam_setup,
)

BALEMURK_LEECH = make_creature(
    name="Balemurk Leech",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Leech"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, each opponent loses 1 life.",
    setup_interceptors=balemurk_leech_setup
)

CACKLING_SLASHER = make_creature(
    name="Cackling Slasher",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="Deathtouch\nThis creature enters with a +1/+1 counter on it if a creature died this turn.",
    setup_interceptors=cackling_slasher_setup,
)

def _come_back_wrong_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Come Back Wrong after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Destroy target creature, then return it under caster's control
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={
            'object_id': target_id,
            'return_under_control': choice.player,
            'sacrifice_at_end_step': True
        },
        source=choice.source_id
    )]


def come_back_wrong_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Come Back Wrong (Phase 5b): Destroy + reanimate to your side."""
    spell = _dsk_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    caster = _dsk_spell_caster_id(state)
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={
                'object_id': t.id,
                'return_under_control': caster,
                'sacrifice_at_end_step': True,
            },
            source=source_id,
        ))
    return events


COME_BACK_WRONG = make_sorcery(
    name="Come Back Wrong",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If a creature card is put into a graveyard this way, return it to the battlefield under your control. Sacrifice it at the beginning of your next end step.",
    resolve=come_back_wrong_resolve,
    target_requirements=[target_creature(count=1)],
)

COMMUNE_WITH_EVIL = make_sorcery(
    name="Commune with Evil",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Look at the top four cards of your library. Put one of them into your hand and the rest into your graveyard. You gain 3 life.",
)

CRACKED_SKULL = make_enchantment(
    name="Cracked Skull",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nWhen this Aura enters, look at target player's hand. You may choose a nonland card from it. That player discards that card.\nWhen enchanted creature is dealt damage, destroy it.",
    subtypes={"Aura"},
    setup_interceptors=cracked_skull_setup,
)

CYNICAL_LONER = make_creature(
    name="Cynical Loner",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Survivor"},
    text="This creature can't be blocked by Glimmers.\nSurvival — At the beginning of your second main phase, if this creature is tapped, you may search your library for a card, put it into your graveyard, then shuffle.",
    setup_interceptors=cynical_loner_setup,
)

DASHING_BLOODSUCKER = make_creature(
    name="Dashing Bloodsucker",
    power=2, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warrior"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +2/+0 and gains lifelink until end of turn.",
    setup_interceptors=dashing_bloodsucker_setup
)

DEFILED_CRYPT = make_enchantment(
    name="Defiled Crypt",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Defiled Crypt {3}{B}:\nWhenever one or more cards leave your graveyard, create a 2/2 black Horror enchantment creature token. This ability triggers only once each turn.\n//\nCadaver Lab {B}:\nWhen you unlock this door, return target creature card from your graveyard to your hand.",
    subtypes={"Room"},
    setup_interceptors=defiled_crypt_setup,
)

DEMONIC_COUNSEL = make_sorcery(
    name="Demonic Counsel",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Search your library for a Demon card, reveal it, put it into your hand, then shuffle.\nDelirium — If there are four or more card types among cards in your graveyard, instead search your library for any card, put it into your hand, then shuffle.",
)

DERELICT_ATTIC = make_enchantment(
    name="Derelict Attic",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Derelict Attic {2}{B}:\nWhen you unlock this door, you draw two cards and you lose 2 life.\n//\nWidow's Walk {3}{B}:\nWhenever a creature you control attacks alone, it gets +1/+0 and gains deathtouch until end of turn.",
    subtypes={"Room"},
    setup_interceptors=derelict_attic_setup,
)

DOOMSDAY_EXCRUCIATOR = make_creature(
    name="Doomsday Excruciator",
    power=6, toughness=6,
    mana_cost="{B}{B}{B}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, if it was cast, each player exiles all but the bottom six cards of their library face down.\nAt the beginning of your upkeep, draw a card.",
    setup_interceptors=doomsday_excruciator_setup
)


def enduring_tenacity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Enduring Tenacity abilities:
    1. Whenever you gain life, target opponent loses that much life.
    2. When dies, if it was a creature, return as enchantment.
    """
    is_creature = CardType.CREATURE in obj.characteristics.types

    # Trigger 1: Life gain causes opponent life loss
    def life_gain_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        # Check if this is life gain for our controller
        if event.payload.get('player') != source.controller:
            return False
        amount = event.payload.get('amount', 0)
        return amount > 0  # Positive = gain

    def drain_opponent(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        # Find an opponent
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -amount},
                    source=obj.id
                )]
        return []

    life_drain_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: life_gain_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=drain_opponent(e, s)
        ),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=drain_opponent,
    )

    interceptors = [life_drain_trigger]

    # Trigger 2: Return as enchantment when dies (only if currently a creature)
    if is_creature:
        def death_effect(event: Event, state: GameState) -> list[Event]:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone': f'graveyard_{obj.owner}',
                    'to_zone': 'battlefield',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'as_enchantment_only': True,
                },
                source=obj.id
            )]

        death_trigger = make_death_trigger(obj, death_effect)
        interceptors.append(death_trigger)

    return interceptors


ENDURING_TENACITY = make_enchantment_creature(
    name="Enduring Tenacity",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Glimmer", "Snake"},
    text="Whenever you gain life, target opponent loses that much life.\nWhen Enduring Tenacity dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
    setup_interceptors=enduring_tenacity_setup
)

FANATIC_OF_THE_HARROWING = make_creature(
    name="Fanatic of the Harrowing",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="When this creature enters, each player discards a card. If you discarded a card this way, draw a card.",
    setup_interceptors=fanatic_of_the_harrowing_setup
)

FEAR_OF_LOST_TEETH = make_enchantment_creature(
    name="Fear of Lost Teeth",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="When this creature dies, it deals 1 damage to any target and you gain 1 life.",
    setup_interceptors=fear_of_lost_teeth_setup
)

FEAR_OF_THE_DARK = make_enchantment_creature(
    name="Fear of the Dark",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Whenever this creature attacks, if defending player controls no Glimmer creatures, it gains menace and deathtouch until end of turn. (A creature with menace can't be blocked except by two or more creatures.)",
    setup_interceptors=fear_of_the_dark_setup,
)

def _final_vengeance_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Final Vengeance after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'battlefield',
            'to_zone': f'exile_{target.owner}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.EXILE
        },
        source=choice.source_id
    )]


def final_vengeance_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Final Vengeance (Phase 5b): Exile target creature."""
    return _dsk_exile_targets()(targets, state)


FINAL_VENGEANCE = make_sorcery(
    name="Final Vengeance",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature or enchantment.\nExile target creature.",
    resolve=final_vengeance_resolve,
    target_requirements=[target_creature(count=1)],
)

FUNERAL_ROOM = make_enchantment(
    name="Funeral Room",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Funeral Room {2}{B}:\nWhenever a creature you control dies, each opponent loses 1 life and you gain 1 life.\n//\nAwakening Hall {6}{B}{B}:\nWhen you unlock this door, return all creature cards from your graveyard to the battlefield.",
    subtypes={"Room"},
    setup_interceptors=funeral_room_setup,
)

def _give_in_to_violence_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Give In to Violence after target selection."""
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
            type=EventType.PUMP,
            payload={'object_id': target_id, 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def give_in_to_violence_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Give In to Violence (Phase 5b): +2/+2 + lifelink until EOT."""
    return resolve_chain(
        _dsk_pump_targets(2, 2),
        _dsk_grant_keywords_to_targets('lifelink'),
    )(targets, state)


GIVE_IN_TO_VIOLENCE = make_instant(
    name="Give In to Violence",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+2 and gains lifelink until end of turn.",
    resolve=give_in_to_violence_resolve,
    target_requirements=[target_creature(count=1)],
)

GRIEVOUS_WOUND = make_enchantment(
    name="Grievous Wound",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Enchant player\nEnchanted player can't gain life.\nWhenever enchanted player is dealt damage, they lose half their life, rounded up.",
    subtypes={"Aura"},
    setup_interceptors=grievous_wound_setup,
)

INNOCUOUS_RAT = make_creature(
    name="Innocuous Rat",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When this creature dies, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    setup_interceptors=innocuous_rat_setup,
)

KILLERS_MASK = make_artifact(
    name="Killer's Mask",
    mana_cost="{2}{B}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature has menace.\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=killers_mask_setup,
)

LETS_PLAY_A_GAME = make_sorcery(
    name="Let's Play a Game",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Delirium — Choose one. If there are four or more card types among cards in your graveyard, choose one or more instead.\n• Creatures your opponents control get -1/-1 until end of turn.\n• Each opponent discards two cards.\n• Each opponent loses 3 life and you gain 3 life.",
)

LEYLINE_OF_THE_VOID = make_enchantment(
    name="Leyline of the Void",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nIf a card would be put into an opponent's graveyard from anywhere, exile it instead.",
    setup_interceptors=leyline_of_the_void_setup,
)

def _live_or_die_target_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Live or Die after target selection."""
    target_id = selected[0] if selected else None
    mode_index = choice.callback_data.get('mode', 0)

    if not target_id:
        return []

    if mode_index == 0:
        # Mode 0: Return creature card from graveyard to battlefield
        target = state.objects.get(target_id)
        if not target or target.zone not in [ZoneType.GRAVEYARD]:
            return []
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone': f'graveyard_{target.owner}',
                'to_zone': 'battlefield',
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone_type': ZoneType.BATTLEFIELD
            },
            source=choice.source_id
        )]
    else:
        # Mode 1: Destroy target creature
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


def _live_or_die_mode_selected(choice, selected, state: GameState) -> list[Event]:
    """Handle Live or Die mode selection, then prompt for target."""
    selected_mode = selected[0]
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    # Find legal targets based on mode
    legal_targets = []
    if mode_index == 0:
        # Return creature card from graveyard
        for obj in state.objects.values():
            if obj.zone == ZoneType.GRAVEYARD and obj.owner == choice.player:
                if CardType.CREATURE in obj.characteristics.types:
                    legal_targets.append(obj.id)
        prompt = "Choose a creature card from your graveyard to return"
    else:
        # Destroy creature on battlefield
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
                legal_targets.append(obj.id)
        prompt = "Choose a creature to destroy"

    if not legal_targets:
        return []

    target_choice = create_target_choice(
        state=state,
        player_id=choice.player,
        source_id=choice.source_id,
        legal_targets=legal_targets,
        prompt=f"Live or Die - {prompt}",
        min_targets=1,
        max_targets=1,
        callback_data={'handler': _live_or_die_target_execute, 'mode': mode_index}
    )

    return []


def live_or_die_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Live or Die: Choose one -
    - Return target creature card from your graveyard to the battlefield.
    - Destroy target creature.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Live or Die":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "live_or_die_spell"

    modes = [
        {"index": 0, "text": "Return target creature card from your graveyard to the battlefield."},
        {"index": 1, "text": "Destroy target creature."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Live or Die - Choose one:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _live_or_die_mode_selected

    return []


LIVE_OR_DIE = make_instant(
    name="Live or Die",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Return target creature card from your graveyard to the battlefield.\n• Destroy target creature.",
    resolve=live_or_die_resolve,
)

MEATHOOK_MASSACRE_II = make_enchantment(
    name="Meathook Massacre II",
    mana_cost="{X}{X}{B}{B}{B}{B}",
    colors={Color.BLACK},
    text="When Meathook Massacre II enters, each player sacrifices X creatures of their choice.\nWhenever a creature you control dies, you may pay 3 life. If you do, return that card under your control with a finality counter on it.\nWhenever a creature an opponent controls dies, they may pay 3 life. If they don't, return that card under your control with a finality counter on it.",
    supertypes={"Legendary"},
    setup_interceptors=meathook_massacre_ii_setup,
)

MIASMA_DEMON = make_creature(
    name="Miasma Demon",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, you may discard any number of cards. When you do, up to that many target creatures each get -2/-2 until end of turn.",
    setup_interceptors=miasma_demon_setup
)

# =============================================================================
# SPELL RESOLVE FUNCTIONS (Removal and Damage)
# =============================================================================

def _murder_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Murder after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Verify target is still valid
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


def murder_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Murder: Destroy target creature (Phase 5b).

    Targets are pre-chosen at cast time via ``target_requirements``.
    """
    return _dsk_destroy_targets()(targets, state)


MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature.",
    resolve=murder_resolve,
    target_requirements=[target_creature(count=1)],
)

NOWHERE_TO_RUN = make_enchantment(
    name="Nowhere to Run",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Flash\nWhen this enchantment enters, target creature an opponent controls gets -3/-3 until end of turn.\nCreatures your opponents control can be the targets of spells and abilities as though they didn't have hexproof. Ward abilities of those creatures don't trigger.",
    setup_interceptors=nowhere_to_run_setup,
)

OSSEOUS_STICKTWISTER = make_artifact_creature(
    name="Osseous Sticktwister",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Scarecrow"},
    text="Lifelink\nDelirium — At the beginning of your end step, if there are four or more card types among cards in your graveyard, each opponent may sacrifice a nonland permanent of their choice or discard a card. Then this creature deals damage equal to its power to each opponent who didn't sacrifice a permanent or discard a card this way.",
    setup_interceptors=osseous_sticktwister_setup,
)

OVERLORD_OF_THE_BALEMURK = make_enchantment_creature(
    name="Overlord of the Balemurk",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Horror"},
    text="Impending 5—{1}{B} (If you cast this spell for its impending cost, it enters with five time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, mill four cards, then you may return a non-Avatar creature card or a planeswalker card from your graveyard to your hand.",
    setup_interceptors=overlord_of_the_balemurk_setup,
)

POPULAR_EGOTIST = make_creature(
    name="Popular Egotist",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{1}{B}, Sacrifice another creature or enchantment: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it.)\nWhenever you sacrifice a permanent, target opponent loses 1 life and you gain 1 life.",
    setup_interceptors=popular_egotist_setup,
)

RESURRECTED_CULTIST = make_creature(
    name="Resurrected Cultist",
    power=4, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="Delirium — {2}{B}{B}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are four or more card types among cards in your graveyard and only as a sorcery. (If a creature with a finality counter on it would die, exile it instead.)",
)

SPECTRAL_SNATCHER = make_creature(
    name="Spectral Snatcher",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Ward—Discard a card. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player discards a card.)\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=spectral_snatcher_setup,
)
SPECTRAL_SNATCHER.setup_in_hand = _make_typecycling_setup("{2}", "Swamp")

SPOROGENIC_INFECTION = make_enchantment(
    name="Sporogenic Infection",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nWhen this Aura enters, target player sacrifices a creature of their choice other than enchanted creature.\nWhen enchanted creature is dealt damage, destroy it.",
    subtypes={"Aura"},
    setup_interceptors=sporogenic_infection_setup,
)

UNHOLY_ANNEX = make_enchantment(
    name="Unholy Annex",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Unholy Annex {2}{B}:\nAt the beginning of your end step, draw a card. If you control a Demon, each opponent loses 2 life and you gain 2 life. Otherwise, you lose 2 life.\n//\nRitual Chamber {3}{B}{B}:\nWhen you unlock this door, create a 6/6 black Demon creature token with flying.",
    subtypes={"Room"},
    setup_interceptors=unholy_annex_setup,
)

UNSTOPPABLE_SLASHER = make_creature(
    name="Unstoppable Slasher",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Zombie"},
    text="Deathtouch\nWhenever this creature deals combat damage to a player, they lose half their life, rounded up.\nWhen this creature dies, if it had no counters on it, return it to the battlefield tapped under its owner's control with two stun counters on it.",
    setup_interceptors=unstoppable_slasher_setup
)

VALGAVOTH_TERROR_EATER = make_creature(
    name="Valgavoth, Terror Eater",
    power=9, toughness=9,
    mana_cost="{6}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Elder"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nWard—Sacrifice three nonland permanents.\nIf a card you didn't control would be put into an opponent's graveyard from anywhere, exile it instead.\nDuring your turn, you may play cards exiled with Valgavoth. If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost.",
    setup_interceptors=valgavoth_terror_eater_setup,
)

VALGAVOTHS_FAITHFUL = make_creature(
    name="Valgavoth's Faithful",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="{3}{B}, Sacrifice this creature: Return target creature card from your graveyard to the battlefield. Activate only as a sorcery.",
    setup_interceptors=valgavoths_faithful_setup,
)

VILE_MUTILATOR = make_creature(
    name="Vile Mutilator",
    power=6, toughness=5,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="As an additional cost to cast this spell, sacrifice a creature or enchantment.\nFlying, trample\nWhen this creature enters, each opponent sacrifices a nontoken enchantment of their choice, then sacrifices a nontoken creature of their choice.",
    setup_interceptors=vile_mutilator_setup
)

def _winters_intervention_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Winter's Intervention after target selection."""
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
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': 2},
            source=choice.source_id
        )
    ]


def winters_intervention_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Winter's Intervention (Phase 5b): 2 dmg + 2 life."""
    return resolve_chain(
        _dsk_damage_to_targets(2),
        _dsk_caster_life_change(2),
    )(targets, state)


WINTERS_INTERVENTION = make_instant(
    name="Winter's Intervention",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Winter's Intervention deals 2 damage to target creature. You gain 2 life.",
    resolve=winters_intervention_resolve,
    target_requirements=[target_creature(count=1)],
)


def _withering_torment_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Withering Torment after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    target_types = target.characteristics.types
    if CardType.CREATURE not in target_types and CardType.ENCHANTMENT not in target_types:
        return []

    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': -2},
            source=choice.source_id
        )
    ]


def withering_torment_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Withering Torment (Phase 5b): Destroy creature/enchantment, lose 2 life."""
    return resolve_chain(
        _dsk_destroy_targets(),
        _dsk_caster_life_change(-2),
    )(targets, state)


WITHERING_TORMENT = make_instant(
    name="Withering Torment",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or enchantment. You lose 2 life.",
    resolve=withering_torment_resolve,
    target_requirements=[
        TargetRequirement(
            filter=TargetFilter(types={CardType.CREATURE, CardType.ENCHANTMENT}),
            count=1,
            label="target creature or enchantment",
        ),
    ],
)

BEDHEAD_BEASTIE = make_creature(
    name="Bedhead Beastie",
    power=5, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=bedhead_beastie_setup,
)
BEDHEAD_BEASTIE.setup_in_hand = make_cycling_setup("{2}", typecycling="Mountain")

def _betrayers_bargain_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Betrayer's Bargain after target selection."""
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
            'is_combat': False,
            'exile_on_death': True
        },
        source=choice.source_id
    )]


def betrayers_bargain_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Betrayer's Bargain (Phase 5b): 5 damage to creature (exile-on-die is engine gap).

    The legacy execute helper already attached `exile_on_death=True` on the
    damage event; we preserve that for downstream replacement effects.
    """
    spell = _dsk_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    for t in _flatten_targets(targets):
        if t.is_player:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': t.id,
                'amount': 5,
                'source': source_id,
                'is_combat': False,
                'is_player': False,
                'exile_on_death': True,
            },
            source=source_id,
        ))
    return events


BETRAYERS_BARGAIN = make_instant(
    name="Betrayer's Bargain",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, sacrifice a creature or enchantment or pay {2}.\nBetrayer's Bargain deals 5 damage to target creature. If that creature would die this turn, exile it instead.",
    resolve=betrayers_bargain_resolve,
    target_requirements=[target_creature(count=1)],
)

BOILERBILGES_RIPPER = make_creature(
    name="Boilerbilges Ripper",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="When this creature enters, you may sacrifice another creature or enchantment. When you do, this creature deals 2 damage to any target.",
    setup_interceptors=boilerbilges_ripper_setup
)

CHAINSAW = make_artifact(
    name="Chainsaw",
    mana_cost="{1}{R}",
    text="When this Equipment enters, it deals 3 damage to up to one target creature.\nWhenever one or more creatures die, put a rev counter on this Equipment.\nEquipped creature gets +X/+0, where X is the number of rev counters on this Equipment.\nEquip {3}",
    subtypes={"Equipment"},
    setup_interceptors=chainsaw_setup,
)

CHARRED_FOYER = make_enchantment(
    name="Charred Foyer",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Charred Foyer {3}{R}:\nAt the beginning of your upkeep, exile the top card of your library. You may play it this turn.\n//\nWarped Space {4}{R}{R}:\nOnce each turn, you may pay {0} rather than pay the mana cost for a spell you cast from exile.",
    subtypes={"Room"},
    setup_interceptors=charred_foyer_setup,
)

CLOCKWORK_PERCUSSIONIST = make_artifact_creature(
    name="Clockwork Percussionist",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Monkey", "Toy"},
    text="Haste\nWhen this creature dies, exile the top card of your library. You may play it until the end of your next turn.",
    setup_interceptors=clockwork_percussionist_setup
)

CURSED_RECORDING = make_artifact(
    name="Cursed Recording",
    mana_cost="{2}{R}{R}",
    text="Whenever you cast an instant or sorcery spell, put a time counter on this artifact. Then if there are seven or more time counters on it, remove those counters and it deals 20 damage to you.\n{T}: When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
    setup_interceptors=cursed_recording_setup,
)

DIVERSION_SPECIALIST = make_creature(
    name="Diversion Specialist",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\n{1}, Sacrifice another creature or enchantment: Exile the top card of your library. You may play it this turn.",
)


def enduring_courage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Enduring Courage abilities:
    1. Whenever another creature you control enters, it gets +2/+0 and gains haste until end of turn.
    2. When dies, if it was a creature, return as enchantment.
    """
    is_creature = CardType.CREATURE in obj.characteristics.types

    # Track creatures we've buffed this turn (to clean up at end of turn)
    buffed_creature_interceptors = []

    # Trigger 1: Buff creatures that enter
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:  # "another creature"
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source.controller:
            return False
        if CardType.CREATURE not in entering_obj.characteristics.types:
            return False
        return True

    def buff_entering_creature(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return []

        # Create a +2/+0 power boost interceptor for this creature
        def power_boost_filter(e: Event, s: GameState) -> bool:
            if e.type != EventType.QUERY_POWER:
                return False
            return e.payload.get('object_id') == entering_id

        def power_boost_handler(e: Event, s: GameState) -> InterceptorResult:
            current = e.payload.get('value', 0)
            e.payload['value'] = current + 2
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=e)

        power_interceptor = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=power_boost_filter,
            handler=power_boost_handler,
            duration='until_end_of_turn'
        )
        power_interceptor.timestamp = state.next_timestamp()
        state.interceptors[power_interceptor.id] = power_interceptor
        buffed_creature_interceptors.append(power_interceptor.id)

        # Grant haste by adding to creature's abilities
        if 'haste' not in [a.get('keyword') for a in entering_obj.characteristics.abilities]:
            entering_obj.characteristics.abilities.append({'keyword': 'haste', 'until_end_of_turn': True})

        return []

    etb_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=buff_entering_creature(e, s)
        ),
        duration='while_on_battlefield',
        is_triggered_ability=True,
        effect_fn=buff_entering_creature,
    )

    # Clean up at end of turn
    def end_of_turn_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.TURN_END:
            return False
        return True

    def cleanup_buffs(event: Event, state: GameState) -> list[Event]:
        # Remove power boost interceptors
        for int_id in buffed_creature_interceptors[:]:
            if int_id in state.interceptors:
                del state.interceptors[int_id]
            buffed_creature_interceptors.remove(int_id)
        return []

    cleanup_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: end_of_turn_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=cleanup_buffs(e, s)
        ),
        duration='while_on_battlefield'
    )

    interceptors = [etb_trigger, cleanup_interceptor]

    # Trigger 2: Return as enchantment when dies (only if currently a creature)
    if is_creature:
        def death_effect(event: Event, state: GameState) -> list[Event]:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone': f'graveyard_{obj.owner}',
                    'to_zone': 'battlefield',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'as_enchantment_only': True,
                },
                source=obj.id
            )]

        death_trigger = make_death_trigger(obj, death_effect)
        interceptors.append(death_trigger)

    return interceptors


ENDURING_COURAGE = make_enchantment_creature(
    name="Enduring Courage",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dog", "Glimmer"},
    text="Whenever another creature you control enters, it gets +2/+0 and gains haste until end of turn.\nWhen Enduring Courage dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
    setup_interceptors=enduring_courage_setup
)

FEAR_OF_BEING_HUNTED = make_enchantment_creature(
    name="Fear of Being Hunted",
    power=4, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="Haste\nThis creature must be blocked if able.",
    setup_interceptors=fear_of_being_hunted_setup,
)

FEAR_OF_BURNING_ALIVE = make_enchantment_creature(
    name="Fear of Burning Alive",
    power=4, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="When this creature enters, it deals 4 damage to each opponent.\nDelirium — Whenever a source you control deals noncombat damage to an opponent, if there are four or more card types among cards in your graveyard, this creature deals that amount of damage to target creature that player controls.",
    setup_interceptors=fear_of_burning_alive_setup
)

FEAR_OF_MISSING_OUT = make_enchantment_creature(
    name="Fear of Missing Out",
    power=2, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="When this creature enters, discard a card, then draw a card.\nDelirium — Whenever this creature attacks for the first time each turn, if there are four or more card types among cards in your graveyard, untap target creature. After this phase, there is an additional combat phase.",
    setup_interceptors=fear_of_missing_out_setup
)

GLASSWORKS = make_enchantment(
    name="Glassworks",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Glassworks {2}{R}:\nWhen you unlock this door, this Room deals 4 damage to target creature an opponent controls.\n//\nShattered Yard {4}{R}:\nAt the beginning of your end step, this Room deals 1 damage to each opponent.",
    subtypes={"Room"},
    setup_interceptors=glassworks_setup,
)

GRAB_THE_PRIZE = make_sorcery(
    name="Grab the Prize",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards. If the discarded card wasn't a land card, Grab the Prize deals 2 damage to each opponent.",
)

HAND_THAT_FEEDS = make_creature(
    name="Hand That Feeds",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Mutant"},
    text="Delirium — Whenever this creature attacks while there are four or more card types among cards in your graveyard, it gets +2/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
    setup_interceptors=hand_that_feeds_setup,
)

def _impossible_inferno_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Impossible Inferno after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.CREATURE not in target.characteristics.types:
        return []

    events = [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 6, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]

    # Delirium check - if 4+ card types in graveyard, exile top card and can play it
    # Note: Full delirium implementation would require checking graveyard card types
    # For now, the damage is the core functionality

    return events


def impossible_inferno_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Impossible Inferno (Phase 5b): 6 damage to creature.

    Delirium bonus exile-top is an engine gap and is dropped.
    """
    return _dsk_damage_to_targets(6)(targets, state)


IMPOSSIBLE_INFERNO = make_instant(
    name="Impossible Inferno",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Impossible Inferno deals 6 damage to target creature.\nDelirium — If there are four or more card types among cards in your graveyard, exile the top card of your library. You may play it until the end of your next turn.",
    resolve=impossible_inferno_resolve,
    target_requirements=[target_creature(count=1)],
)

INFERNAL_PHANTOM = make_creature(
    name="Infernal Phantom",
    power=2, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +2/+0 until end of turn.\nWhen this creature dies, it deals damage equal to its power to any target.",
    setup_interceptors=infernal_phantom_eerie_setup
)

IRREVERENT_GREMLIN = make_creature(
    name="Irreverent Gremlin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Gremlin"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever another creature you control with power 2 or less enters, you may discard a card. If you do, draw a card. Do this only once each turn.",
    setup_interceptors=irreverent_gremlin_setup,
)

LEYLINE_OF_RESONANCE = make_enchantment(
    name="Leyline of Resonance",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nWhenever you cast an instant or sorcery spell that targets only a single creature you control, copy that spell. You may choose new targets for the copy.",
    setup_interceptors=leyline_of_resonance_setup,
)

ALEYLINE_OF_RESONANCE = make_enchantment(
    name="A-Leyline of Resonance",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nWhenever you cast an instant or sorcery spell that targets only a single creature you control, you may pay {1}. If you do, copy that spell. You may choose new targets for the copy.",
    setup_interceptors=aleyline_of_resonance_setup,
)

MOST_VALUABLE_SLAYER = make_creature(
    name="Most Valuable Slayer",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Whenever you attack, target attacking creature gets +1/+0 and gains first strike until end of turn.",
    setup_interceptors=most_valuable_slayer_setup
)

NORIN_SWIFT_SURVIVALIST = make_creature(
    name="Norin, Swift Survivalist",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Coward", "Human"},
    supertypes={"Legendary"},
    text="Norin can't block.\nWhenever a creature you control becomes blocked, you may exile it. You may play that card from exile this turn.",
    setup_interceptors=norin_swift_survivalist_setup,
)

OVERLORD_OF_THE_BOILERBILGES = make_enchantment_creature(
    name="Overlord of the Boilerbilges",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{2}{R}{R} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, it deals 4 damage to any target.",
    setup_interceptors=overlord_of_the_boilerbilges_setup,
)

PAINTERS_STUDIO = make_enchantment(
    name="Painter's Studio",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Painter's Studio {2}{R}:\nWhen you unlock this door, exile the top two cards of your library. You may play them until the end of your next turn.\n//\nDefaced Gallery {1}{R}:\nWhenever you attack, attacking creatures you control get +1/+0 until end of turn.",
    subtypes={"Room"},
    setup_interceptors=painters_studio_setup,
)

PIGGY_BANK = make_artifact_creature(
    name="Piggy Bank",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Boar", "Toy"},
    text="When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=piggy_bank_setup,
)

def pyroclasm_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Pyroclasm: Deal 2 damage to each creature.
    No targeting required.
    """
    stack_zone = state.zones.get('stack')
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Pyroclasm":
                spell_id = obj.id
                break

    if spell_id is None:
        spell_id = "pyroclasm_spell"

    events = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': obj.id, 'amount': 2, 'source': spell_id, 'is_combat': False},
                source=spell_id
            ))

    return events


PYROCLASM = make_sorcery(
    name="Pyroclasm",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Pyroclasm deals 2 damage to each creature.",
    resolve=pyroclasm_resolve,
)

RAGGED_PLAYMATE = make_artifact_creature(
    name="Ragged Playmate",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Toy"},
    text="{1}, {T}: Target creature with power 2 or less can't be blocked this turn.",
    setup_interceptors=ragged_playmate_setup,
)

RAMPAGING_SOULRAGER = make_creature(
    name="Rampaging Soulrager",
    power=1, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="This creature gets +3/+0 as long as there are two or more unlocked doors among Rooms you control.",
    setup_interceptors=rampaging_soulrager_setup,
)

RAZORKIN_HORDECALLER = make_creature(
    name="Razorkin Hordecaller",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Clown", "Human"},
    text="Haste\nWhenever you attack, create a 1/1 red Gremlin creature token.",
    setup_interceptors=razorkin_hordecaller_setup
)

RAZORKIN_NEEDLEHEAD = make_creature(
    name="Razorkin Needlehead",
    power=2, toughness=2,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="This creature has first strike during your turn.\nWhenever an opponent draws a card, this creature deals 1 damage to them.",
    setup_interceptors=razorkin_needlehead_setup
)

RIPCHAIN_RAZORKIN = make_creature(
    name="Ripchain Razorkin",
    power=5, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Human"},
    text="Reach\n{2}{R}, Sacrifice a land: Draw a card.",
    setup_interceptors=ripchain_razorkin_setup,
)

THE_ROLLERCRUSHER_RIDE = make_enchantment(
    name="The Rollercrusher Ride",
    mana_cost="{X}{2}{R}",
    colors={Color.RED},
    text="Delirium — If a source you control would deal noncombat damage to a permanent or player while there are four or more card types among cards in your graveyard, it deals double that damage instead.\nWhen The Rollercrusher Ride enters, it deals X damage to each of up to X target creatures.",
    supertypes={"Legendary"},
    setup_interceptors=the_rollercrusher_ride_setup,
)

def _scorching_dragonfire_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Scorching Dragonfire after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    target_types = target.characteristics.types
    if CardType.CREATURE not in target_types and CardType.PLANESWALKER not in target_types:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': 3,
            'source': choice.source_id,
            'is_combat': False,
            'exile_on_death': True
        },
        source=choice.source_id
    )]


def scorching_dragonfire_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Scorching Dragonfire (Phase 5b): 3 damage (exile-on-die is engine gap)."""
    spell = _dsk_resolving_spell_obj(state)
    source_id = spell.id if spell else None
    events: list[Event] = []
    for t in _flatten_targets(targets):
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': t.id,
                'amount': 3,
                'source': source_id,
                'is_combat': False,
                'is_player': t.is_player,
                'exile_on_death': True,
            },
            source=source_id,
        ))
    return events


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

SCREAMING_NEMESIS = make_creature(
    name="Screaming Nemesis",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Haste\nWhenever this creature is dealt damage, it deals that much damage to any other target. If a player is dealt damage this way, they can't gain life for the rest of the game.",
    setup_interceptors=screaming_nemesis_setup
)

TICKET_BOOTH = make_enchantment(
    name="Ticket Booth",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Ticket Booth {2}{R}:\nWhen you unlock this door, manifest dread.\n//\nTunnel of Hate {4}{R}{R}:\nWhenever you attack, target attacking creature gains double strike until end of turn.",
    subtypes={"Room"},
    setup_interceptors=ticket_booth_setup,
)

# Trial of Agony: two opponent creatures, same controller. That opponent
# chooses one to take 5 damage; the other can't block this turn.
def trial_of_agony_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Trial of Agony.

    Cast-time provides exactly two target creature IDs (both controlled by the
    same opponent). The controlling opponent opens a PendingChoice to pick
    which of the two takes the damage; the other gains 'cant_block' EOT.
    """
    spell = _dsk_resolving_spell_obj(state)
    source_id = spell.id if spell else None

    flat = _flatten_targets(targets)
    ids: list[str] = [t.id for t in flat if not t.is_player]
    if len(ids) < 2:
        return []
    # Pick the first two unique creatures still on battlefield.
    valid: list[str] = []
    for tid in ids:
        if tid in valid:
            continue
        obj = state.objects.get(tid)
        if obj is None or obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        valid.append(tid)
        if len(valid) >= 2:
            break
    if len(valid) < 2:
        return []

    a_id, b_id = valid[0], valid[1]
    obj_a = state.objects.get(a_id)
    obj_b = state.objects.get(b_id)
    if obj_a is None or obj_b is None:
        return []
    # Both creatures share a controller; that's the choosing opponent.
    chooser = obj_a.controller
    if chooser is None:
        return []

    # If the engine has no pending-choice helper plumbed, fall back to dealing
    # damage to the first creature and 'can't block' to the second.
    try:
        from src.engine.pending_choice_helpers import create_choice_and_resolve
    except ImportError:
        return [
            Event(type=EventType.DAMAGE,
                  payload={'target': a_id, 'amount': 5, 'source': source_id,
                           'is_combat': False, 'is_player': False},
                  source=source_id),
            Event(type=EventType.CANT_BLOCK,
                  payload={'object_id': b_id, 'duration': 'end_of_turn'},
                  source=source_id),
        ]

    options: list = [
        {"id": a_id, "label": obj_a.name or a_id},
        {"id": b_id, "label": obj_b.name or b_id},
    ]

    def _handler(choice, selected, st, _a=a_id, _b=b_id, _src=source_id):
        # The chosen creature takes 5 damage; the other can't block.
        picked = None
        if selected:
            raw = selected[0]
            if isinstance(raw, dict):
                picked = raw.get("id") or raw.get("value")
            else:
                picked = raw
        if picked is None:
            picked = _a
        damaged = picked
        blocked = _b if picked == _a else _a
        return [
            Event(type=EventType.DAMAGE,
                  payload={'target': damaged, 'amount': 5, 'source': _src,
                           'is_combat': False, 'is_player': False},
                  source=_src),
            Event(type=EventType.CANT_BLOCK,
                  payload={'object_id': blocked, 'duration': 'end_of_turn'},
                  source=_src),
        ]

    # The chooser is an opponent of the caster; the heuristic pick should
    # spare their bigger creature, but a simple default (option 0 = a_id) is
    # acceptable for AI as the engine resolves the choice from the chooser's
    # perspective.
    return create_choice_and_resolve(
        state,
        choice_type="trial_of_agony_pick",
        player_id=chooser,
        prompt="Trial of Agony — choose which of your creatures takes 5 damage",
        options=options,
        source_id=source_id or "trial_of_agony",
        min_choices=1,
        max_choices=1,
        handler=_handler,
        heuristic_pick=[a_id],
    )


TRIAL_OF_AGONY = make_sorcery(
    name="Trial of Agony",
    mana_cost="{R}",
    colors={Color.RED},
    text="Choose two target creatures controlled by the same opponent. That player chooses one of those creatures. Trial of Agony deals 5 damage to that creature, and the other can't block this turn.",
    resolve=trial_of_agony_resolve,
    target_requirements=[
        target_creature(count=1, controller='opponent',
                        label="target creature an opponent controls"),
        target_same_opponent_creature(
            label="another creature controlled by the same opponent",
        ),
    ],
)

def _turn_inside_out_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Turn Inside Out after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.PUMP,
        payload={'object_id': target_id, 'power': 3, 'toughness': 0, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def turn_inside_out_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Turn Inside Out (Phase 5b): +3/+0 EOT (death-trigger manifest-dread is engine gap)."""
    return _dsk_pump_targets(3, 0)(targets, state)


TURN_INSIDE_OUT = make_instant(
    name="Turn Inside Out",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 until end of turn. When it dies this turn, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    resolve=turn_inside_out_resolve,
    target_requirements=[target_creature(count=1)],
)

def _untimely_malfunction_target_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Untimely Malfunction after target selection."""
    mode_index = choice.callback_data.get('mode', 0)

    if not selected:
        return []

    events = []
    if mode_index == 0:
        # Mode 0: Destroy target artifact
        target_id = selected[0]
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=choice.source_id
            ))
    elif mode_index == 1:
        # Mode 1: Change target - complex, would need additional selection
        # For now, just mark the spell as having its target changed
        target_id = selected[0]
        events.append(Event(
            type=EventType.TARGET_CHANGED,
            payload={'spell_id': target_id},
            source=choice.source_id
        ))
    else:
        # Mode 2: Creatures can't block
        for target_id in selected:
            target = state.objects.get(target_id)
            if target and target.zone == ZoneType.BATTLEFIELD:
                events.append(Event(
                    type=EventType.CANT_BLOCK,
                    payload={'object_id': target_id, 'duration': 'end_of_turn'},
                    source=choice.source_id
                ))

    return events


def _untimely_malfunction_mode_selected(choice, selected, state: GameState) -> list[Event]:
    """Handle Untimely Malfunction mode selection."""
    selected_mode = selected[0]
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    legal_targets = []
    min_targets = 1
    max_targets = 1

    if mode_index == 0:
        # Destroy target artifact
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.ARTIFACT in obj.characteristics.types:
                legal_targets.append(obj.id)
        prompt = "Choose an artifact to destroy"
    elif mode_index == 1:
        # Change the target of a spell/ability
        stack_zone = state.zones.get('stack')
        if stack_zone:
            for obj_id in stack_zone.objects:
                if obj_id != choice.source_id:
                    obj = state.objects.get(obj_id)
                    if obj and obj.zone == ZoneType.STACK:
                        legal_targets.append(obj_id)
        prompt = "Choose a spell or ability to change its target"
    else:
        # Mode 2: One or two creatures can't block
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
                legal_targets.append(obj.id)
        prompt = "Choose one or two creatures that can't block"
        max_targets = 2

    if not legal_targets:
        return []

    target_choice = create_target_choice(
        state=state,
        player_id=choice.player,
        source_id=choice.source_id,
        legal_targets=legal_targets,
        prompt=f"Untimely Malfunction - {prompt}",
        min_targets=min_targets,
        max_targets=max_targets,
        callback_data={'handler': _untimely_malfunction_target_execute, 'mode': mode_index}
    )

    return []


def untimely_malfunction_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Untimely Malfunction: Choose one -
    - Destroy target artifact.
    - Change the target of target spell or ability with a single target.
    - One or two target creatures can't block this turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Untimely Malfunction":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "untimely_malfunction_spell"

    modes = [
        {"index": 0, "text": "Destroy target artifact."},
        {"index": 1, "text": "Change the target of target spell or ability with a single target."},
        {"index": 2, "text": "One or two target creatures can't block this turn."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Untimely Malfunction - Choose one:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _untimely_malfunction_mode_selected

    return []


UNTIMELY_MALFUNCTION = make_instant(
    name="Untimely Malfunction",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Destroy target artifact.\n• Change the target of target spell or ability with a single target.\n• One or two target creatures can't block this turn.",
    resolve=untimely_malfunction_resolve,
)

def vengeful_possession_resolve(targets: list, state: GameState) -> list[Event]:
    """Vengeful Possession (Phase 5b): targets[0][0] is the creature to threaten."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Vengeful Possession":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "vengeful_possession_spell"
    if not targets or not targets[0]:
        return []
    tid, _ = normalize_target(targets[0][0], state)
    return [
        Event(
            type=EventType.GAIN_CONTROL,
            payload={
                'object_id': tid,
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
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': tid, 'keyword': 'haste', 'duration': 'end_of_turn'},
            source=spell_id, controller=caster_id,
        ),
    ]


VENGEFUL_POSSESSION = make_sorcery(
    name="Vengeful Possession",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap it. It gains haste until end of turn. You may discard a card. If you do, draw a card.",
    resolve=vengeful_possession_resolve,
    target_requirements=[target_creature(count=1, controller='opponent')],
)

VICIOUS_CLOWN = make_creature(
    name="Vicious Clown",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Clown", "Human"},
    text="Whenever another creature you control with power 2 or less enters, this creature gets +2/+0 until end of turn.",
    setup_interceptors=vicious_clown_setup
)

def _violent_urge_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Violent Urge after target selection."""
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
            type=EventType.PUMP,
            payload={'object_id': target_id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'first_strike', 'duration': 'end_of_turn'},
            source=choice.source_id
        )
        # Note: Delirium would grant double strike instead - would need graveyard check
    ]


def violent_urge_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Violent Urge (Phase 5b): +1/+0 + first strike (delirium double strike is engine gap)."""
    return resolve_chain(
        _dsk_pump_targets(1, 0),
        _dsk_grant_keywords_to_targets('first_strike'),
    )(targets, state)


VIOLENT_URGE = make_instant(
    name="Violent Urge",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +1/+0 and gains first strike until end of turn.\nDelirium — If there are four or more card types among cards in your graveyard, that creature gains double strike until end of turn.",
    resolve=violent_urge_resolve,
    target_requirements=[target_creature(count=1)],
)

WALTZ_OF_RAGE = make_sorcery(
    name="Waltz of Rage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to each other creature. Until end of turn, whenever a creature you control dies, exile the top card of your library. You may play it until the end of your next turn.",
)

ALTANAK_THE_THRICECALLED = make_creature(
    name="Altanak, the Thrice-Called",
    power=9, toughness=9,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Insect"},
    supertypes={"Legendary"},
    text="Trample\nWhenever Altanak becomes the target of a spell or ability an opponent controls, draw a card.\n{1}{G}, Discard this card: Return target land card from your graveyard to the battlefield tapped.",
    setup_interceptors=altanak_the_thricecalled_setup,
)

ANTHROPEDE = make_creature(
    name="Anthropede",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Reach\nWhen this creature enters, you may discard a card or pay {2}. When you do, destroy target Room.",
    setup_interceptors=anthropede_setup
)

BALUSTRADE_WURM = make_creature(
    name="Balustrade Wurm",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="This spell can't be countered.\nTrample, haste\nDelirium — {2}{G}{G}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are four or more card types among cards in your graveyard and only as a sorcery.",
    setup_interceptors=balustrade_wurm_setup,
)
BALUSTRADE_WURM.setup_in_graveyard = balustrade_wurm_gy_setup

BASHFUL_BEASTIE = make_creature(
    name="Bashful Beastie",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When this creature dies, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    setup_interceptors=bashful_beastie_setup,
)

def _break_down_the_door_target_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Break Down the Door after target selection (for modes 0 and 1)."""
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
            'from_zone': 'battlefield',
            'to_zone': f'exile_{target.owner}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.EXILE
        },
        source=choice.source_id
    )]


def _break_down_the_door_mode_selected(choice, selected, state: GameState) -> list[Event]:
    """Handle Break Down the Door mode selection."""
    selected_mode = selected[0]
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    if mode_index == 2:
        # Mode 2: Manifest dread (no targeting needed)
        return [Event(
            type=EventType.MANIFEST_DREAD,
            payload={'player': choice.player},
            source=choice.source_id
        )]

    # Modes 0 and 1 require targeting
    legal_targets = []
    if mode_index == 0:
        # Exile artifact
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.ARTIFACT in obj.characteristics.types:
                legal_targets.append(obj.id)
        prompt = "Choose an artifact to exile"
    else:
        # Exile enchantment
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.ENCHANTMENT in obj.characteristics.types:
                legal_targets.append(obj.id)
        prompt = "Choose an enchantment to exile"

    if not legal_targets:
        return []

    target_choice = create_target_choice(
        state=state,
        player_id=choice.player,
        source_id=choice.source_id,
        legal_targets=legal_targets,
        prompt=f"Break Down the Door - {prompt}",
        min_targets=1,
        max_targets=1,
        callback_data={'handler': _break_down_the_door_target_execute, 'mode': mode_index}
    )

    return []


def break_down_the_door_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Break Down the Door: Choose one -
    - Exile target artifact.
    - Exile target enchantment.
    - Manifest dread.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Break Down the Door":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "break_down_the_door_spell"

    modes = [
        {"index": 0, "text": "Exile target artifact."},
        {"index": 1, "text": "Exile target enchantment."},
        {"index": 2, "text": "Manifest dread."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Break Down the Door - Choose one:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _break_down_the_door_mode_selected

    return []


BREAK_DOWN_THE_DOOR = make_instant(
    name="Break Down the Door",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Exile target artifact.\n• Exile target enchantment.\n• Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    resolve=break_down_the_door_resolve,
)

CATHARTIC_PARTING = make_sorcery(
    name="Cathartic Parting",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="The owner of target artifact or enchantment an opponent controls shuffles it into their library. You may shuffle up to four target cards from your graveyard into your library.",
)

CAUTIOUS_SURVIVOR = make_creature(
    name="Cautious Survivor",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, you gain 2 life.",
    setup_interceptors=cautious_survivor_setup,
)

def _coordinated_clobbering_target_enemy(choice, selected, state: GameState) -> list[Event]:
    """Execute Coordinated Clobbering - select enemy creature to deal damage to."""
    your_creatures = choice.callback_data.get('your_creatures', [])
    target_id = selected[0] if selected else None

    if not target_id or not your_creatures:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = []
    for creature_id in your_creatures:
        creature = state.objects.get(creature_id)
        if creature and creature.zone == ZoneType.BATTLEFIELD:
            power = get_power(creature, state)
            # Tap your creature
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': creature_id},
                source=choice.source_id
            ))
            # Deal damage
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': power, 'source': creature_id, 'is_combat': False},
                source=choice.source_id
            ))

    return events


def _coordinated_clobbering_select_yours(choice, selected, state: GameState) -> list[Event]:
    """After selecting your creatures, now select enemy creature."""
    if not selected:
        return []

    # Find opponent's creatures
    caster_id = choice.player
    legal_targets = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller != caster_id):
            legal_targets.append(obj.id)

    if not legal_targets:
        return []

    target_choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=choice.source_id,
        legal_targets=legal_targets,
        prompt="Coordinated Clobbering - Choose an opponent's creature to damage",
        min_targets=1,
        max_targets=1,
        callback_data={'handler': _coordinated_clobbering_target_enemy, 'your_creatures': selected}
    )

    return []


def coordinated_clobbering_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Coordinated Clobbering: Tap one or two untapped creatures you control.
    They each deal damage equal to their power to target creature an opponent controls.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Coordinated Clobbering":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "coordinated_clobbering_spell"

    # Find untapped creatures you control
    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller == caster_id and
            not obj.state.tapped)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Coordinated Clobbering - Choose one or two untapped creatures you control",
        min_targets=1,
        max_targets=2,
        callback_data={'handler': _coordinated_clobbering_select_yours}
    )

    return []


COORDINATED_CLOBBERING = make_sorcery(
    name="Coordinated Clobbering",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Tap one or two target untapped creatures you control. They each deal damage equal to their power to target creature an opponent controls.",
    resolve=coordinated_clobbering_resolve,
)

CRYPTID_INSPECTOR = make_creature(
    name="Cryptid Inspector",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Vigilance\nWhenever a face-down permanent you control enters and whenever this creature or another permanent you control is turned face up, put a +1/+1 counter on this creature.",
    setup_interceptors=cryptid_inspector_setup
)

DEFIANT_SURVIVOR = make_creature(
    name="Defiant Survivor",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    setup_interceptors=defiant_survivor_setup,
)


def enduring_vitality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Enduring Vitality abilities:
    1. Vigilance (keyword - doesn't tap when attacking)
    2. Creatures you control have "{T}: Add one mana of any color."
    3. When dies, if it was a creature, return as enchantment.
    """
    is_creature = CardType.CREATURE in obj.characteristics.types

    # Grant vigilance to self (if creature)
    if is_creature and 'vigilance' not in [a.get('keyword') for a in obj.characteristics.abilities]:
        obj.characteristics.abilities.append({'keyword': 'vigilance'})

    # Ability: Grant mana ability to all creatures you control
    # This responds to ACTIVATE events for creatures we control
    def mana_ability_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        # Check if this is a mana tap activation for a creature we control
        if event.payload.get('ability_type') != 'mana_tap':
            return False
        target_id = event.payload.get('object_id')
        target_obj = state.objects.get(target_id)
        if not target_obj:
            return False
        if target_obj.controller != source.controller:
            return False
        if CardType.CREATURE not in target_obj.characteristics.types:
            return False
        if target_obj.zone != ZoneType.BATTLEFIELD:
            return False
        if target_obj.state.tapped:
            return False  # Can't tap already tapped creature
        return True

    def produce_mana(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('object_id')
        target_obj = state.objects.get(target_id)
        if not target_obj:
            return []

        # Get the color requested (default to colorless)
        color = event.payload.get('color', Color.COLORLESS)

        # Tap the creature and produce mana
        return [
            Event(
                type=EventType.TAP,
                payload={'object_id': target_id},
                source=obj.id
            ),
            Event(
                type=EventType.MANA_PRODUCED,
                payload={'player': obj.controller, 'color': color, 'amount': 1},
                source=target_id
            )
        ]

    mana_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: mana_ability_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=produce_mana(e, s)
        ),
        duration='while_on_battlefield'
    )

    # Also grant the mana ability as a queryable ability on creatures
    def grant_mana_ability_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target_obj = state.objects.get(target_id)
        if not target_obj:
            return False
        if target_obj.controller != source.controller:
            return False
        if CardType.CREATURE not in target_obj.characteristics.types:
            return False
        return True

    def add_mana_ability(event: Event, state: GameState) -> InterceptorResult:
        abilities = event.payload.get('abilities', [])
        abilities.append({'activated': 'mana_tap', 'cost': '{T}', 'effect': 'Add one mana of any color'})
        event.payload['abilities'] = abilities
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)

    ability_grant_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=lambda e, s: grant_mana_ability_filter(e, s, obj),
        handler=lambda e, s: add_mana_ability(e, s),
        duration='while_on_battlefield'
    )

    interceptors = [mana_interceptor, ability_grant_interceptor]

    # Death trigger: Return as enchantment (only if currently a creature)
    if is_creature:
        def death_effect(event: Event, state: GameState) -> list[Event]:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone': f'graveyard_{obj.owner}',
                    'to_zone': 'battlefield',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'as_enchantment_only': True,
                },
                source=obj.id
            )]

        death_trigger = make_death_trigger(obj, death_effect)
        interceptors.append(death_trigger)

    return interceptors


ENDURING_VITALITY = make_enchantment_creature(
    name="Enduring Vitality",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elk", "Glimmer"},
    text="Vigilance\nCreatures you control have \"{T}: Add one mana of any color.\"\nWhen Enduring Vitality dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
    setup_interceptors=enduring_vitality_setup
)

FEAR_OF_EXPOSURE = make_enchantment_creature(
    name="Fear of Exposure",
    power=5, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Nightmare"},
    text="As an additional cost to cast this spell, tap two untapped creatures and/or lands you control.\nTrample",
    setup_interceptors=fear_of_exposure_setup,
)

FLESH_BURROWER = make_creature(
    name="Flesh Burrower",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Deathtouch\nWhenever this creature attacks, another target creature you control gains deathtouch until end of turn.",
    setup_interceptors=flesh_burrower_setup
)

FRANTIC_STRENGTH = make_enchantment(
    name="Frantic Strength",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nEnchanted creature gets +2/+2 and has trample.",
    subtypes={"Aura"},
    setup_interceptors=frantic_strength_setup,
)

GRASPING_LONGNECK = make_enchantment_creature(
    name="Grasping Longneck",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horror"},
    text="Reach\nWhen this creature dies, you gain 2 life.",
    setup_interceptors=grasping_longneck_setup
)

GREENHOUSE = make_enchantment(
    name="Greenhouse",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Greenhouse {2}{G}:\nLands you control have \"{T}: Add one mana of any color.\"\n//\nRickety Gazebo {3}{G}:\nWhen you unlock this door, mill four cards, then return up to two permanent cards from among them to your hand.",
    subtypes={"Room"},
    setup_interceptors=greenhouse_setup,
)

HAUNTWOODS_SHRIEKER = make_creature(
    name="Hauntwoods Shrieker",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Mutant"},
    text="Whenever this creature attacks, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\n{1}{G}: Reveal target face-down permanent. If it's a creature card, you may turn it face up.",
    setup_interceptors=hauntwoods_shrieker_setup,
)

HEDGE_SHREDDER = make_artifact(
    name="Hedge Shredder",
    mana_cost="{2}{G}{G}",
    text="Whenever this Vehicle attacks, you may mill two cards.\nWhenever one or more land cards are put into your graveyard from your library, put them onto the battlefield tapped.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    setup_interceptors=hedge_shredder_setup,
)

def _horrid_vigor_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Horrid Vigor after target selection."""
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
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'deathtouch', 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def horrid_vigor_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Horrid Vigor (Phase 5b): deathtouch + indestructible EOT."""
    return _dsk_grant_keywords_to_targets('deathtouch', 'indestructible')(targets, state)


HORRID_VIGOR = make_instant(
    name="Horrid Vigor",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gains deathtouch and indestructible until end of turn.",
    resolve=horrid_vigor_resolve,
    target_requirements=[target_creature(count=1)],
)

HOUSE_CARTOGRAPHER = make_creature(
    name="House Cartographer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, reveal cards from the top of your library until you reveal a land card. Put that card into your hand and the rest on the bottom of your library in a random order.",
    setup_interceptors=house_cartographer_setup,
)

INSIDIOUS_FUNGUS = make_creature(
    name="Insidious Fungus",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fungus"},
    text="{2}, Sacrifice this creature: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n• Draw a card. Then you may put a land card from your hand onto the battlefield tapped.",
    setup_interceptors=insidious_fungus_setup,
)

KONA_RESCUE_BEASTIE = make_creature(
    name="Kona, Rescue Beastie",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Survivor"},
    supertypes={"Legendary"},
    text="Survival — At the beginning of your second main phase, if Kona is tapped, you may put a permanent card from your hand onto the battlefield.",
    setup_interceptors=kona_rescue_beastie_setup,
)

LEYLINE_OF_MUTATION = make_enchantment(
    name="Leyline of Mutation",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nYou may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.",
    setup_interceptors=leyline_of_mutation_setup,
)

def _manifest_dread_resolve(event: Event, state: GameState) -> list[Event]:
    """Resolve Manifest Dread: top card of library becomes a face-down 2/2."""
    controller = event.controller or event.payload.get('controller')
    if not controller:
        return []
    lib_key = f"library_{controller}"
    lib_zone = state.zones.get(lib_key)
    top_card_def = None
    if lib_zone and lib_zone.objects:
        top_obj_id = lib_zone.objects[-1]
        top_obj = state.objects.get(top_obj_id)
        if top_obj is not None:
            top_card_def = top_obj.card_def
        # Remove from library — the chosen card becomes the manifested creature.
        lib_zone.objects.remove(top_obj_id)
    return [
        Event(type=EventType.MANIFEST_DREAD, payload={'player': controller}, source=event.source),
        make_manifest_etb_event(controller, source_id=event.source, card_def=top_card_def),
    ]


MANIFEST_DREAD = make_sorcery(
    name="Manifest Dread",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    resolve=_manifest_dread_resolve,
)

MOLDERING_GYM = make_enchantment(
    name="Moldering Gym",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Moldering Gym {2}{G}:\nWhen you unlock this door, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\n//\nWeight Room {5}{G}:\nWhen you unlock this door, manifest dread, then put three +1/+1 counters on that creature.",
    subtypes={"Room"},
    setup_interceptors=moldering_gym_setup,
)

MONSTROUS_EMERGENCE = make_sorcery(
    name="Monstrous Emergence",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, choose a creature you control or reveal a creature card from your hand.\nMonstrous Emergence deals damage equal to the power of the creature you chose or the card you revealed to target creature.",
)

OMNIVOROUS_FLYTRAP = make_creature(
    name="Omnivorous Flytrap",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Delirium — Whenever this creature enters or attacks, if there are four or more card types among cards in your graveyard, distribute two +1/+1 counters among one or two target creatures. Then if there are six or more card types among cards in your graveyard, double the number of +1/+1 counters on those creatures.",
    setup_interceptors=omnivorous_flytrap_setup
)

OVERGROWN_ZEALOT = make_creature(
    name="Overgrown Zealot",
    power=0, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{T}: Add one mana of any color.\n{T}: Add two mana of any one color. Spend this mana only to turn permanents face up.",
)

OVERLORD_OF_THE_HAUNTWOODS = make_enchantment_creature(
    name="Overlord of the Hauntwoods",
    power=6, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{1}{G}{G} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, create a tapped colorless land token named Everywhere that is every basic land type.",
    setup_interceptors=overlord_of_the_hauntwoods_setup,
)

PATCHWORK_BEASTIE = make_artifact_creature(
    name="Patchwork Beastie",
    power=3, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Delirium — This creature can't attack or block unless there are four or more card types among cards in your graveyard.\nAt the beginning of your upkeep, you may mill a card. (You may put the top card of your library into your graveyard.)",
    setup_interceptors=patchwork_beastie_setup,
)

ROOTWISE_SURVIVOR = make_creature(
    name="Rootwise Survivor",
    power=3, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Survivor"},
    text="Haste\nSurvival — At the beginning of your second main phase, if this creature is tapped, put three +1/+1 counters on up to one target land you control. That land becomes a 0/0 Elemental creature in addition to its other types. It gains haste until your next turn.",
    setup_interceptors=rootwise_survivor_setup,
)

SAY_ITS_NAME = make_sorcery(
    name="Say Its Name",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Mill three cards. Then you may return a creature or land card from your graveyard to your hand.\nExile this card and two other cards named Say Its Name from your graveyard: Search your graveyard, hand, and/or library for a card named Altanak, the Thrice-Called and put it onto the battlefield. If you search your library this way, shuffle. Activate only as a sorcery.",
)

SLAVERING_BRANCHSNAPPER = make_creature(
    name="Slavering Branchsnapper",
    power=7, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard"},
    text="Trample\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=slavering_branchsnapper_setup,
)
SLAVERING_BRANCHSNAPPER.setup_in_hand = make_cycling_setup("{2}", typecycling="Forest")

SPINESEEKER_CENTIPEDE = make_creature(
    name="Spineseeker Centipede",
    power=2, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="When this creature enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nDelirium — This creature gets +1/+2 and has vigilance as long as there are four or more card types among cards in your graveyard.",
    setup_interceptors=spineseeker_centipede_setup
)

THREATS_AROUND_EVERY_CORNER = make_enchantment(
    name="Threats Around Every Corner",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, manifest dread.\nWhenever a face-down permanent you control enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=threats_around_every_corner_setup
)

TWITCHING_DOLL = make_artifact_creature(
    name="Twitching Doll",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spider", "Toy"},
    text="{T}: Add one mana of any color. Put a nest counter on this creature.\n{T}, Sacrifice this creature: Create a 2/2 green Spider creature token with reach for each counter on this creature. Activate only as a sorcery.",
)

TYVAR_THE_PUMMELER = make_creature(
    name="Tyvar, the Pummeler",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Tap another untapped creature you control: Tyvar gains indestructible until end of turn. Tap it.\n{3}{G}{G}: Creatures you control get +X/+X until end of turn, where X is the greatest power among creatures you control.",
    setup_interceptors=tyvar_the_pummeler_setup,
)

def _dsk_get_spell_and_caster(state: GameState, spell_name: str) -> tuple:
    """Locate (spell_id, caster_id) for a spell on the stack by name."""
    stack_zone = state.zones.get('stack')
    spell_id = None
    caster_id = None
    if stack_zone:
        for oid in stack_zone.objects:
            obj = state.objects.get(oid)
            if obj and obj.name == spell_name:
                spell_id = obj.id
                caster_id = obj.controller
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = f"{spell_name.lower().replace(' ', '_').replace(chr(39), '')}_spell"
    return spell_id, caster_id


def under_the_skin_resolve(targets: list, state: GameState) -> list[Event]:
    """Under the Skin: Manifest dread. (Skip the optional graveyard return rider —
    engine gap for "you may" graveyard-to-hand on a permanent card.)"""
    spell_id, caster_id = _dsk_get_spell_and_caster(state, "Under the Skin")
    return [Event(
        type=EventType.MANIFEST_DREAD,
        payload={'controller': caster_id, 'source_id': spell_id},
        source=spell_id,
    )]


def valgavoths_onslaught_resolve(targets: list, state: GameState) -> list[Event]:
    """Valgavoth's Onslaught: Manifest dread X times. (Skip the +1/+1 counter
    rider on each manifested creature — engine gap: no per-manifest tracking.)"""
    spell_id, caster_id = _dsk_get_spell_and_caster(state, "Valgavoth's Onslaught")
    # Recover the X value the caster paid. The engine stores it on the spell
    # object's state as ``x_value`` if known, otherwise default to 0.
    x_value = 0
    spell_obj = state.objects.get(spell_id)
    if spell_obj is not None:
        x_value = int(getattr(spell_obj.state, 'x_value', 0) or 0)
    if x_value <= 0:
        return []
    return [
        Event(
            type=EventType.MANIFEST_DREAD,
            payload={'controller': caster_id, 'source_id': spell_id},
            source=spell_id,
        )
        for _ in range(x_value)
    ]


UNDER_THE_SKIN = make_sorcery(
    name="Under the Skin",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nYou may return a permanent card from your graveyard to your hand.",
    resolve=under_the_skin_resolve,
)

VALGAVOTHS_ONSLAUGHT = make_sorcery(
    name="Valgavoth's Onslaught",
    mana_cost="{X}{X}{G}",
    colors={Color.GREEN},
    text="Manifest dread X times, then put X +1/+1 counters on each of those creatures. (To manifest dread, look at the top two cards of your library, then put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    resolve=valgavoths_onslaught_resolve,
)

WALKIN_CLOSET = make_enchantment(
    name="Walk-In Closet",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Walk-In Closet {2}{G}:\nYou may play lands from your graveyard.\n//\nForgotten Cellar {3}{G}{G}:\nWhen you unlock this door, you may cast spells from your graveyard this turn, and if a card would be put into your graveyard from anywhere this turn, exile it instead.",
    subtypes={"Room"},
    setup_interceptors=walkin_closet_setup,
)

WARY_WATCHDOG = make_creature(
    name="Wary Watchdog",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dog"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=wary_watchdog_setup,
)

WICKERFOLK_THRESHER = make_artifact_creature(
    name="Wickerfolk Thresher",
    power=5, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Scarecrow"},
    text="Delirium — Whenever this creature attacks, if there are four or more card types among cards in your graveyard, look at the top card of your library. If it's a land card, you may put it onto the battlefield. If you don't put the card onto the battlefield, put it into your hand.",
    setup_interceptors=wickerfolk_thresher_setup
)

ARABELLA_ABANDONED_DOLL = make_artifact_creature(
    name="Arabella, Abandoned Doll",
    power=1, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Toy"},
    supertypes={"Legendary"},
    text="Whenever Arabella attacks, it deals X damage to each opponent and you gain X life, where X is the number of creatures you control with power 2 or less.",
    setup_interceptors=arabella_abandoned_doll_setup
)

BASEBALL_BAT = make_artifact(
    name="Baseball Bat",
    mana_cost="{G}{W}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+1.\nWhenever equipped creature attacks, tap up to one target creature.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=baseball_bat_setup,
)

BEASTIE_BEATDOWN = make_sorcery(
    name="Beastie Beatdown",
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Choose target creature you control and target creature an opponent controls.\nDelirium — If there are four or more card types among cards in your graveyard, put two +1/+1 counters on the creature you control.\nThe creature you control deals damage equal to its power to the creature an opponent controls.",
)

BROODSPINNER = make_creature(
    name="Broodspinner",
    power=2, toughness=3,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spider"},
    text="Reach\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n{4}{B}{G}, {T}, Sacrifice this creature: Create a number of 1/1 black and green Insect creature tokens with flying equal to the number of card types among cards in your graveyard.",
    setup_interceptors=broodspinner_setup,
)

DISTURBING_MIRTH = make_enchantment(
    name="Disturbing Mirth",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When this enchantment enters, you may sacrifice another enchantment or creature. If you do, draw two cards.\nWhen you sacrifice this enchantment, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
    setup_interceptors=disturbing_mirth_setup,
)

def drag_to_the_roots_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-cost: delirium — {2} less if four or more card types are among
    cards in your graveyard.

    Skipped clauses:
      * Resolution effect ('destroy target nonland permanent') uses cast-
        effect dispatch elsewhere, not wired here.
    """
    DELIRIUM_TYPES = {
        CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT,
        CardType.LAND, CardType.PLANESWALKER, CardType.INSTANT,
        CardType.SORCERY,
    }
    # Tribal exists in some sets; include if defined.
    tribal = getattr(CardType, 'TRIBAL', None)
    if tribal is not None:
        DELIRIUM_TYPES.add(tribal)
    battle = getattr(CardType, 'BATTLE', None)
    if battle is not None:
        DELIRIUM_TYPES.add(battle)

    def amount_fn(card: GameObject, st: GameState) -> int:
        controller = obj.controller
        gy = st.zones.get(f'graveyard_{controller}')
        if not gy:
            return 0
        seen = set()
        for oid in gy.objects:
            o = st.objects.get(oid)
            if not o:
                continue
            for t in o.characteristics.types:
                if t in DELIRIUM_TYPES:
                    seen.add(t)
                    if len(seen) >= 4:
                        return 2
        return 2 if len(seen) >= 4 else 0

    return [make_cost_reduction(obj, applies_to=lambda c, p, s: True,
                                amount=amount_fn, self_only=True)]


DRAG_TO_THE_ROOTS = make_instant(
    name="Drag to the Roots",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Delirium — This spell costs {2} less to cast as long as there are four or more card types among cards in your graveyard.\nDestroy target nonland permanent.",
    setup_interceptors=drag_to_the_roots_setup,
)

FEAR_OF_INFINITY = make_enchantment_creature(
    name="Fear of Infinity",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Nightmare"},
    text="Flying, lifelink\nThis creature can't block.\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, you may return this card from your graveyard to your hand.",
)
# Eerie fires from the graveyard for this card — see fear_of_infinity_setup.
FEAR_OF_INFINITY.setup_in_graveyard = fear_of_infinity_setup

GREMLIN_TAMER = make_creature(
    name="Gremlin Tamer",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, create a 1/1 red Gremlin creature token.",
    setup_interceptors=gremlin_tamer_setup
)

GROWING_DREAD = make_enchantment(
    name="Growing Dread",
    mana_cost="{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    text="Flash\nWhen this enchantment enters, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nWhenever you turn a permanent face up, put a +1/+1 counter on it.",
    setup_interceptors=growing_dread_setup,
)

INQUISITIVE_GLIMMER = make_enchantment_creature(
    name="Inquisitive Glimmer",
    power=2, toughness=3,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Fox", "Glimmer"},
    text="Enchantment spells you cast cost {1} less to cast.\nUnlock costs you pay cost {1} less.",
    setup_interceptors=inquisitive_glimmer_setup,
)

INTRUDING_SOULRAGER = make_creature(
    name="Intruding Soulrager",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Spirit"},
    text="Vigilance\n{T}, Sacrifice a Room: This creature deals 2 damage to each opponent. Draw a card.",
)

THE_JOLLY_BALLOON_MAN = make_creature(
    name="The Jolly Balloon Man",
    power=1, toughness=4,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Clown", "Human"},
    supertypes={"Legendary"},
    text="Haste\n{1}, {T}: Create a token that's a copy of another target creature you control, except it's a 1/1 red Balloon creature in addition to its other colors and types and it has flying and haste. Sacrifice it at the beginning of the next end step. Activate only as a sorcery.",
    setup_interceptors=the_jolly_balloon_man_setup,
)

KAITO_BANE_OF_NIGHTMARES = make_planeswalker(
    name="Kaito, Bane of Nightmares",
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    loyalty=4,
    subtypes={"Kaito"},
    supertypes={"Legendary"},
    text="Ninjutsu {1}{U}{B} ({1}{U}{B}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nDuring your turn, as long as Kaito has one or more loyalty counters on him, he's a 3/4 Ninja creature and has hexproof.\n+1: You get an emblem with \"Ninjas you control get +1/+1.\"\n0: Surveil 2. Then draw a card for each opponent who lost life this turn.\n−2: Tap target creature. Put two stun counters on it.",
    setup_interceptors=kaito_bane_of_nightmares_setup,
)

MARINA_VENDRELL = make_creature(
    name="Marina Vendrell",
    power=3, toughness=5,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Marina Vendrell enters, reveal the top seven cards of your library. Put all enchantment cards from among them into your hand and the rest on the bottom of your library in a random order.\n{T}: Lock or unlock a door of target Room you control. Activate only as a sorcery.",
    setup_interceptors=marina_vendrell_setup
)

MIDNIGHT_MAYHEM = make_sorcery(
    name="Midnight Mayhem",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create three 1/1 red Gremlin creature tokens. Gremlins you control gain menace, lifelink, and haste until end of turn. (A creature with menace can't be blocked except by two or more creatures.)",
    resolve=midnight_mayhem_resolve,
)

NASHI_SEARCHER_IN_THE_DARK = make_creature(
    name="Nashi, Searcher in the Dark",
    power=2, toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Ninja", "Rat", "Wizard"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Nashi deals combat damage to a player, you mill that many cards. You may put any number of legendary and/or enchantment cards from among them into your hand. If you put no cards into your hand this way, put a +1/+1 counter on Nashi.",
    setup_interceptors=nashi_searcher_in_the_dark_setup,
)

NIKO_LIGHT_OF_HOPE = make_creature(
    name="Niko, Light of Hope",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Niko enters, create two Shard tokens. (They're enchantments with \"{2}, Sacrifice this token: Scry 1, then draw a card.\")\n{2}, {T}: Exile target nonlegendary creature you control. Shards you control become copies of it until the next end step. Return it to the battlefield under its owner's control at the beginning of the next end step.",
    setup_interceptors=niko_light_of_hope_setup,
)

OBLIVIOUS_BOOKWORM = make_creature(
    name="Oblivious Bookworm",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Wizard"},
    text="At the beginning of your end step, you may draw a card. If you do, discard a card unless a permanent entered the battlefield face down under your control this turn or you turned a permanent face up this turn.",
    setup_interceptors=oblivious_bookworm_setup,
)

PEER_PAST_THE_VEIL = make_instant(
    name="Peer Past the Veil",
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Discard your hand. Then draw X cards, where X is the number of card types among cards in your graveyard.",
)

RESTRICTED_OFFICE = make_enchantment(
    name="Restricted Office",
    mana_cost="{2}{W}{W}",
    colors={Color.BLUE, Color.WHITE},
    text="Restricted Office {2}{W}{W}:\nWhen you unlock this door, destroy all creatures with power 3 or greater.\n//\nLecture Hall {5}{U}{U}:\nOther permanents you control have hexproof.",
    subtypes={"Room"},
    setup_interceptors=restricted_office_setup,
)

RIP_SPAWN_HUNTER = make_creature(
    name="Rip, Spawn Hunter",
    power=4, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Survivor"},
    supertypes={"Legendary"},
    text="Survival — At the beginning of your second main phase, if Rip is tapped, reveal the top X cards of your library, where X is its power. Put any number of creature and/or Vehicle cards with different powers from among them into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=rip_spawn_hunter_setup,
)

RITE_OF_THE_MOTH = make_sorcery(
    name="Rite of the Moth",
    mana_cost="{1}{W}{B}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)\nFlashback {3}{W}{W}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

ROARING_FURNACE = make_enchantment(
    name="Roaring Furnace",
    mana_cost="{1}{R}",
    colors={Color.BLUE, Color.RED},
    text="Roaring Furnace {1}{R}:\nWhen you unlock this door, this Room deals damage equal to the number of cards in your hand to target creature an opponent controls.\n//\nSteaming Sauna {3}{U}{U}:\nYou have no maximum hand size.\nAt the beginning of your end step, draw a card.",
    subtypes={"Room"},
    setup_interceptors=roaring_furnace_setup,
)

SAWBLADE_SKINRIPPER = make_creature(
    name="Sawblade Skinripper",
    power=3, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Assassin", "Human"},
    text="Menace\n{2}, Sacrifice another creature or enchantment: Put a +1/+1 counter on this creature.\nAt the beginning of your end step, if you sacrificed one or more permanents this turn, this creature deals that much damage to any target.",
    setup_interceptors=sawblade_skinripper_setup
)

SHREWD_STORYTELLER = make_creature(
    name="Shrewd Storyteller",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, put a +1/+1 counter on target creature.",
    setup_interceptors=shrewd_storyteller_setup
)

SHROUDSTOMPER = make_creature(
    name="Shroudstomper",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}{B}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Elemental"},
    text="Deathtouch\nWhenever this creature enters or attacks, each opponent loses 2 life. You gain 2 life and draw a card.",
    setup_interceptors=shroudstomper_setup
)

def skullsnap_nuisance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie — surveil 1."""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id, controller=obj.controller,
        )]
    return [make_eerie_trigger(obj, eerie_effect)]


SKULLSNAP_NUISANCE = make_creature(
    name="Skullsnap Nuisance",
    power=1, toughness=4,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Insect", "Skeleton"},
    text="Flying\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=skullsnap_nuisance_setup,
)

SMOKY_LOUNGE = make_enchantment(
    name="Smoky Lounge",
    mana_cost="{2}{R}",
    colors={Color.BLUE, Color.RED},
    text="Smoky Lounge {2}{R}:\nAt the beginning of your first main phase, add {R}{R}. Spend this mana only to cast Room spells and unlock doors.\n//\nMisty Salon {3}{U}:\nWhen you unlock this door, create an X/X blue Spirit creature token with flying, where X is the number of unlocked doors among Rooms you control.",
    subtypes={"Room"},
    setup_interceptors=smoky_lounge_setup,
)

THE_SWARMWEAVER = make_artifact_creature(
    name="The Swarmweaver",
    power=2, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Scarecrow"},
    supertypes={"Legendary"},
    text="When The Swarmweaver enters, create two 1/1 black and green Insect creature tokens with flying.\nDelirium — As long as there are four or more card types among cards in your graveyard, Insects and Spiders you control get +1/+1 and have deathtouch.",
    setup_interceptors=the_swarmweaver_setup
)

UNDEAD_SPRINTER = make_creature(
    name="Undead Sprinter",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Zombie"},
    text="Trample, haste\nYou may cast this card from your graveyard if a non-Zombie creature died this turn. If you do, this creature enters with a +1/+1 counter on it.",
    setup_interceptors=undead_sprinter_setup
)
UNDEAD_SPRINTER.setup_in_graveyard = undead_sprinter_gy_setup

VICTOR_VALGAVOTHS_SENESCHAL = make_creature(
    name="Victor, Valgavoth's Seneschal",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, surveil 2 if this is the first time this ability has resolved this turn. If it's the second time, each opponent discards a card. If it's the third time, put a creature card from a graveyard onto the battlefield under your control.",
    setup_interceptors=victor_valgavoths_seneschal_setup
)

WILDFIRE_WICKERFOLK = make_artifact_creature(
    name="Wildfire Wickerfolk",
    power=3, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Scarecrow"},
    text="Haste\nDelirium — This creature gets +1/+1 and has trample as long as there are four or more card types among cards in your graveyard.",
)

WINTER_MISANTHROPIC_GUIDE = make_creature(
    name="Winter, Misanthropic Guide",
    power=3, toughness=4,
    mana_cost="{1}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward {2}\nAt the beginning of your upkeep, each player draws two cards.\nDelirium — As long as there are four or more card types among cards in your graveyard, each opponent's maximum hand size is equal to seven minus the number of those card types.",
    setup_interceptors=winter_misanthropic_guide_setup,
)

ZIMONE_ALLQUESTIONING = make_creature(
    name="Zimone, All-Questioning",
    power=1, toughness=1,
    mana_cost="{1}{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if a land entered the battlefield under your control this turn and you control a prime number of lands, create Primo, the Indivisible, a legendary 0/0 green and blue Fractal creature token, then put that many +1/+1 counters on it. (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, and 31 are prime numbers.)",
    setup_interceptors=zimone_allquestioning_setup,
)

ATTACKINTHEBOX = make_artifact_creature(
    name="Attack-in-the-Box",
    power=2, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Toy"},
    text="Whenever this creature attacks, you may have it get +4/+0 until end of turn. If you do, sacrifice it at the beginning of the next end step.",
    setup_interceptors=attackinthebox_setup,
)

BEAR_TRAP = make_artifact(
    name="Bear Trap",
    mana_cost="{1}",
    text="Flash\n{3}, {T}, Sacrifice this artifact: It deals 3 damage to target creature.",
    setup_interceptors=bear_trap_setup,
)

CONDUCTIVE_MACHETE = make_artifact(
    name="Conductive Machete",
    mana_cost="{4}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature gets +2/+1.\nEquip {4}",
    subtypes={"Equipment"},
    setup_interceptors=conductive_machete_setup,
)

DISSECTION_TOOLS = make_artifact(
    name="Dissection Tools",
    mana_cost="{5}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature.\nEquipped creature gets +2/+2 and has deathtouch and lifelink.\nEquip—Sacrifice a creature.",
    subtypes={"Equipment"},
    setup_interceptors=dissection_tools_setup,
)

FOUND_FOOTAGE = make_artifact(
    name="Found Footage",
    mana_cost="{1}",
    text="You may look at face-down creatures your opponents control any time.\n{2}, Sacrifice this artifact: Surveil 2, then draw a card. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    subtypes={"Clue"},
)

FRIENDLY_TEDDY = make_artifact_creature(
    name="Friendly Teddy",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Bear", "Toy"},
    text="When this creature dies, each player draws a card.",
    setup_interceptors=friendly_teddy_setup,
)

GHOST_VACUUM = make_artifact(
    name="Ghost Vacuum",
    mana_cost="{1}",
    text="{T}: Exile target card from a graveyard.\n{6}, {T}, Sacrifice this artifact: Put each creature card exiled with this artifact onto the battlefield under your control with a flying counter on it. Each of them is a 1/1 Spirit in addition to its other types. Activate only as a sorcery.",
    setup_interceptors=ghost_vacuum_setup,
)

GLIMMERLIGHT = make_artifact(
    name="Glimmerlight",
    mana_cost="{2}",
    text="When this Equipment enters, create a 1/1 white Glimmer enchantment creature token.\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=glimmerlight_setup,
)

HAUNTED_SCREEN = make_artifact(
    name="Haunted Screen",
    mana_cost="{3}",
    text="{T}: Add {W} or {B}.\n{T}, Pay 1 life: Add {G}, {U}, or {R}.\n{7}: Put seven +1/+1 counters on this artifact. It becomes a 0/0 Spirit creature in addition to its other types. Activate only once.",
    setup_interceptors=haunted_screen_setup,
)

KEYS_TO_THE_HOUSE = make_artifact(
    name="Keys to the House",
    mana_cost="{1}",
    text="{1}, {T}, Sacrifice this artifact: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\n{3}, {T}, Sacrifice this artifact: Lock or unlock a door of target Room you control. Activate only as a sorcery.",
    setup_interceptors=keys_to_the_house_setup,
)

MALEVOLENT_CHANDELIER = make_artifact_creature(
    name="Malevolent Chandelier",
    power=4, toughness=4,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Construct"},
    text="Flying\n{2}: Put target card from a graveyard on the bottom of its owner's library. Activate only as a sorcery.",
    setup_interceptors=malevolent_chandelier_setup,
)

MARVIN_MURDEROUS_MIMIC = make_artifact_creature(
    name="Marvin, Murderous Mimic",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Toy"},
    supertypes={"Legendary"},
    text="Marvin has all activated abilities of creatures you control that don't have the same name as this creature.",
    setup_interceptors=marvin_murderous_mimic_setup,
)

SAW = make_artifact(
    name="Saw",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0.\nWhenever equipped creature attacks, you may sacrifice a permanent other than that creature or this Equipment. If you do, draw a card.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=make_equipment_setup(power_mod=2, toughness_mod=0, equip_cost="{2}"),
)

ABANDONED_CAMPGROUND = make_land(
    name="Abandoned Campground",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {W} or {U}.",
)

BLAZEMIRE_VERGE = make_land(
    name="Blazemire Verge",
    text="{T}: Add {B}.\n{T}: Add {R}. Activate only if you control a Swamp or a Mountain.",
)

BLEEDING_WOODS = make_land(
    name="Bleeding Woods",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {R} or {G}.",
)

ETCHED_CORNFIELD = make_land(
    name="Etched Cornfield",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {G} or {W}.",
)

FLOODFARM_VERGE = make_land(
    name="Floodfarm Verge",
    text="{T}: Add {W}.\n{T}: Add {U}. Activate only if you control a Plains or an Island.",
)

GLOOMLAKE_VERGE = make_land(
    name="Gloomlake Verge",
    text="{T}: Add {U}.\n{T}: Add {B}. Activate only if you control an Island or a Swamp.",
)

HUSHWOOD_VERGE = make_land(
    name="Hushwood Verge",
    text="{T}: Add {G}.\n{T}: Add {W}. Activate only if you control a Forest or a Plains.",
)

LAKESIDE_SHACK = make_land(
    name="Lakeside Shack",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {G} or {U}.",
)

MURKY_SEWER = make_land(
    name="Murky Sewer",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {U} or {B}.",
)

NEGLECTED_MANOR = make_land(
    name="Neglected Manor",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {W} or {B}.",
)

PECULIAR_LIGHTHOUSE = make_land(
    name="Peculiar Lighthouse",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {U} or {R}.",
)

RAUCOUS_CARNIVAL = make_land(
    name="Raucous Carnival",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {R} or {W}.",
)

RAZORTRAP_GORGE = make_land(
    name="Razortrap Gorge",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {B} or {R}.",
)

STRANGLED_CEMETERY = make_land(
    name="Strangled Cemetery",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {B} or {G}.",
)

def terramorphic_expanse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, Sacrifice this land: Search your library for a basic land card,
    put it onto the battlefield tapped, then shuffle."""
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
        obj, cost="{T}, Sacrifice this land", effect_fn=_basic_tutor,
        description="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    )
    return []


TERRAMORPHIC_EXPANSE = make_land(
    name="Terramorphic Expanse",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=terramorphic_expanse_setup,
)

THORNSPIRE_VERGE = make_land(
    name="Thornspire Verge",
    text="{T}: Add {R}.\n{T}: Add {G}. Activate only if you control a Mountain or a Forest.",
)

VALGAVOTHS_LAIR = make_enchantment(
    name="Valgavoth's Lair",
    mana_cost="",
    colors=set(),
    text="Hexproof\nThis land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
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

DUSKMOURN_CARDS = {
    "Acrobatic Cheerleader": ACROBATIC_CHEERLEADER,
    "Cult Healer": CULT_HEALER,
    "Dazzling Theater": DAZZLING_THEATER,
    "Dollmaker's Shop": DOLLMAKERS_SHOP,
    "Emerge from the Cocoon": EMERGE_FROM_THE_COCOON,
    "Enduring Innocence": ENDURING_INNOCENCE,
    "Ethereal Armor": ETHEREAL_ARMOR,
    "Exorcise": EXORCISE,
    "Fear of Abduction": FEAR_OF_ABDUCTION,
    "Fear of Immobility": FEAR_OF_IMMOBILITY,
    "Fear of Surveillance": FEAR_OF_SURVEILLANCE,
    "Friendly Ghost": FRIENDLY_GHOST,
    "Ghostly Dancers": GHOSTLY_DANCERS,
    "Glimmer Seeker": GLIMMER_SEEKER,
    "Grand Entryway": GRAND_ENTRYWAY,
    "Hardened Escort": HARDENED_ESCORT,
    "Jump Scare": JUMP_SCARE,
    "Leyline of Hope": LEYLINE_OF_HOPE,
    "Lionheart Glimmer": LIONHEART_GLIMMER,
    "Living Phone": LIVING_PHONE,
    "Optimistic Scavenger": OPTIMISTIC_SCAVENGER,
    "Orphans of the Wheat": ORPHANS_OF_THE_WHEAT,
    "Overlord of the Mistmoors": OVERLORD_OF_THE_MISTMOORS,
    "Patched Plaything": PATCHED_PLAYTHING,
    "Possessed Goat": POSSESSED_GOAT,
    "Reluctant Role Model": RELUCTANT_ROLE_MODEL,
    "Savior of the Small": SAVIOR_OF_THE_SMALL,
    "Seized from Slumber": SEIZED_FROM_SLUMBER,
    "Shardmage's Rescue": SHARDMAGES_RESCUE,
    "Sheltered by Ghosts": SHELTERED_BY_GHOSTS,
    "Shepherding Spirits": SHEPHERDING_SPIRITS,
    "Split Up": SPLIT_UP,
    "Splitskin Doll": SPLITSKIN_DOLL,
    "Surgical Suite": SURGICAL_SUITE,
    "Toby, Beastie Befriender": TOBY_BEASTIE_BEFRIENDER,
    "Trapped in the Screen": TRAPPED_IN_THE_SCREEN,
    "Unidentified Hovership": UNIDENTIFIED_HOVERSHIP,
    "Unsettling Twins": UNSETTLING_TWINS,
    "Unwanted Remake": UNWANTED_REMAKE,
    "Veteran Survivor": VETERAN_SURVIVOR,
    "The Wandering Rescuer": THE_WANDERING_RESCUER,
    "Abhorrent Oculus": ABHORRENT_OCULUS,
    "Bottomless Pool": BOTTOMLESS_POOL,
    "Central Elevator": CENTRAL_ELEVATOR,
    "Clammy Prowler": CLAMMY_PROWLER,
    "Creeping Peeper": CREEPING_PEEPER,
    "Cursed Windbreaker": CURSED_WINDBREAKER,
    "Daggermaw Megalodon": DAGGERMAW_MEGALODON,
    "Don't Make a Sound": DONT_MAKE_A_SOUND,
    "Duskmourn's Domination": DUSKMOURNS_DOMINATION,
    "Enduring Curiosity": ENDURING_CURIOSITY,
    "Enter the Enigma": ENTER_THE_ENIGMA,
    "Entity Tracker": ENTITY_TRACKER,
    "Erratic Apparition": ERRATIC_APPARITION,
    "Fear of Failed Tests": FEAR_OF_FAILED_TESTS,
    "Fear of Falling": FEAR_OF_FALLING,
    "Fear of Impostors": FEAR_OF_IMPOSTORS,
    "Fear of Isolation": FEAR_OF_ISOLATION,
    "Floodpits Drowner": FLOODPITS_DROWNER,
    "Get Out": GET_OUT,
    "Ghostly Keybearer": GHOSTLY_KEYBEARER,
    "Glimmerburst": GLIMMERBURST,
    "Leyline of Transformation": LEYLINE_OF_TRANSFORMATION,
    "Marina Vendrell's Grimoire": MARINA_VENDRELLS_GRIMOIRE,
    "Meat Locker": MEAT_LOCKER,
    "The Mindskinner": THE_MINDSKINNER,
    "Mirror Room": MIRROR_ROOM,
    "Overlord of the Floodpits": OVERLORD_OF_THE_FLOODPITS,
    "Paranormal Analyst": PARANORMAL_ANALYST,
    "Piranha Fly": PIRANHA_FLY,
    "Scrabbling Skullcrab": SCRABBLING_SKULLCRAB,
    "Silent Hallcreeper": SILENT_HALLCREEPER,
    "Stalked Researcher": STALKED_RESEARCHER,
    "Stay Hidden, Stay Silent": STAY_HIDDEN_STAY_SILENT,
    "The Tale of Tamiyo": THE_TALE_OF_TAMIYO,
    "Tunnel Surveyor": TUNNEL_SURVEYOR,
    "Twist Reality": TWIST_REALITY,
    "Unable to Scream": UNABLE_TO_SCREAM,
    "Underwater Tunnel": UNDERWATER_TUNNEL,
    "Unnerving Grasp": UNNERVING_GRASP,
    "Unwilling Vessel": UNWILLING_VESSEL,
    "Vanish from Sight": VANISH_FROM_SIGHT,
    "Appendage Amalgam": APPENDAGE_AMALGAM,
    "Balemurk Leech": BALEMURK_LEECH,
    "Cackling Slasher": CACKLING_SLASHER,
    "Come Back Wrong": COME_BACK_WRONG,
    "Commune with Evil": COMMUNE_WITH_EVIL,
    "Cracked Skull": CRACKED_SKULL,
    "Cynical Loner": CYNICAL_LONER,
    "Dashing Bloodsucker": DASHING_BLOODSUCKER,
    "Defiled Crypt": DEFILED_CRYPT,
    "Demonic Counsel": DEMONIC_COUNSEL,
    "Derelict Attic": DERELICT_ATTIC,
    "Doomsday Excruciator": DOOMSDAY_EXCRUCIATOR,
    "Enduring Tenacity": ENDURING_TENACITY,
    "Fanatic of the Harrowing": FANATIC_OF_THE_HARROWING,
    "Fear of Lost Teeth": FEAR_OF_LOST_TEETH,
    "Fear of the Dark": FEAR_OF_THE_DARK,
    "Final Vengeance": FINAL_VENGEANCE,
    "Funeral Room": FUNERAL_ROOM,
    "Give In to Violence": GIVE_IN_TO_VIOLENCE,
    "Grievous Wound": GRIEVOUS_WOUND,
    "Innocuous Rat": INNOCUOUS_RAT,
    "Killer's Mask": KILLERS_MASK,
    "Let's Play a Game": LETS_PLAY_A_GAME,
    "Leyline of the Void": LEYLINE_OF_THE_VOID,
    "Live or Die": LIVE_OR_DIE,
    "Meathook Massacre II": MEATHOOK_MASSACRE_II,
    "Miasma Demon": MIASMA_DEMON,
    "Murder": MURDER,
    "Nowhere to Run": NOWHERE_TO_RUN,
    "Osseous Sticktwister": OSSEOUS_STICKTWISTER,
    "Overlord of the Balemurk": OVERLORD_OF_THE_BALEMURK,
    "Popular Egotist": POPULAR_EGOTIST,
    "Resurrected Cultist": RESURRECTED_CULTIST,
    "Spectral Snatcher": SPECTRAL_SNATCHER,
    "Sporogenic Infection": SPOROGENIC_INFECTION,
    "Unholy Annex": UNHOLY_ANNEX,
    "Unstoppable Slasher": UNSTOPPABLE_SLASHER,
    "Valgavoth, Terror Eater": VALGAVOTH_TERROR_EATER,
    "Valgavoth's Faithful": VALGAVOTHS_FAITHFUL,
    "Vile Mutilator": VILE_MUTILATOR,
    "Winter's Intervention": WINTERS_INTERVENTION,
    "Withering Torment": WITHERING_TORMENT,
    "Bedhead Beastie": BEDHEAD_BEASTIE,
    "Betrayer's Bargain": BETRAYERS_BARGAIN,
    "Boilerbilges Ripper": BOILERBILGES_RIPPER,
    "Chainsaw": CHAINSAW,
    "Charred Foyer": CHARRED_FOYER,
    "Clockwork Percussionist": CLOCKWORK_PERCUSSIONIST,
    "Cursed Recording": CURSED_RECORDING,
    "Diversion Specialist": DIVERSION_SPECIALIST,
    "Enduring Courage": ENDURING_COURAGE,
    "Fear of Being Hunted": FEAR_OF_BEING_HUNTED,
    "Fear of Burning Alive": FEAR_OF_BURNING_ALIVE,
    "Fear of Missing Out": FEAR_OF_MISSING_OUT,
    "Glassworks": GLASSWORKS,
    "Grab the Prize": GRAB_THE_PRIZE,
    "Hand That Feeds": HAND_THAT_FEEDS,
    "Impossible Inferno": IMPOSSIBLE_INFERNO,
    "Infernal Phantom": INFERNAL_PHANTOM,
    "Irreverent Gremlin": IRREVERENT_GREMLIN,
    "Leyline of Resonance": LEYLINE_OF_RESONANCE,
    "A-Leyline of Resonance": ALEYLINE_OF_RESONANCE,
    "Most Valuable Slayer": MOST_VALUABLE_SLAYER,
    "Norin, Swift Survivalist": NORIN_SWIFT_SURVIVALIST,
    "Overlord of the Boilerbilges": OVERLORD_OF_THE_BOILERBILGES,
    "Painter's Studio": PAINTERS_STUDIO,
    "Piggy Bank": PIGGY_BANK,
    "Pyroclasm": PYROCLASM,
    "Ragged Playmate": RAGGED_PLAYMATE,
    "Rampaging Soulrager": RAMPAGING_SOULRAGER,
    "Razorkin Hordecaller": RAZORKIN_HORDECALLER,
    "Razorkin Needlehead": RAZORKIN_NEEDLEHEAD,
    "Ripchain Razorkin": RIPCHAIN_RAZORKIN,
    "The Rollercrusher Ride": THE_ROLLERCRUSHER_RIDE,
    "Scorching Dragonfire": SCORCHING_DRAGONFIRE,
    "Screaming Nemesis": SCREAMING_NEMESIS,
    "Ticket Booth": TICKET_BOOTH,
    "Trial of Agony": TRIAL_OF_AGONY,
    "Turn Inside Out": TURN_INSIDE_OUT,
    "Untimely Malfunction": UNTIMELY_MALFUNCTION,
    "Vengeful Possession": VENGEFUL_POSSESSION,
    "Vicious Clown": VICIOUS_CLOWN,
    "Violent Urge": VIOLENT_URGE,
    "Waltz of Rage": WALTZ_OF_RAGE,
    "Altanak, the Thrice-Called": ALTANAK_THE_THRICECALLED,
    "Anthropede": ANTHROPEDE,
    "Balustrade Wurm": BALUSTRADE_WURM,
    "Bashful Beastie": BASHFUL_BEASTIE,
    "Break Down the Door": BREAK_DOWN_THE_DOOR,
    "Cathartic Parting": CATHARTIC_PARTING,
    "Cautious Survivor": CAUTIOUS_SURVIVOR,
    "Coordinated Clobbering": COORDINATED_CLOBBERING,
    "Cryptid Inspector": CRYPTID_INSPECTOR,
    "Defiant Survivor": DEFIANT_SURVIVOR,
    "Enduring Vitality": ENDURING_VITALITY,
    "Fear of Exposure": FEAR_OF_EXPOSURE,
    "Flesh Burrower": FLESH_BURROWER,
    "Frantic Strength": FRANTIC_STRENGTH,
    "Grasping Longneck": GRASPING_LONGNECK,
    "Greenhouse": GREENHOUSE,
    "Hauntwoods Shrieker": HAUNTWOODS_SHRIEKER,
    "Hedge Shredder": HEDGE_SHREDDER,
    "Horrid Vigor": HORRID_VIGOR,
    "House Cartographer": HOUSE_CARTOGRAPHER,
    "Insidious Fungus": INSIDIOUS_FUNGUS,
    "Kona, Rescue Beastie": KONA_RESCUE_BEASTIE,
    "Leyline of Mutation": LEYLINE_OF_MUTATION,
    "Manifest Dread": MANIFEST_DREAD,
    "Moldering Gym": MOLDERING_GYM,
    "Monstrous Emergence": MONSTROUS_EMERGENCE,
    "Omnivorous Flytrap": OMNIVOROUS_FLYTRAP,
    "Overgrown Zealot": OVERGROWN_ZEALOT,
    "Overlord of the Hauntwoods": OVERLORD_OF_THE_HAUNTWOODS,
    "Patchwork Beastie": PATCHWORK_BEASTIE,
    "Rootwise Survivor": ROOTWISE_SURVIVOR,
    "Say Its Name": SAY_ITS_NAME,
    "Slavering Branchsnapper": SLAVERING_BRANCHSNAPPER,
    "Spineseeker Centipede": SPINESEEKER_CENTIPEDE,
    "Threats Around Every Corner": THREATS_AROUND_EVERY_CORNER,
    "Twitching Doll": TWITCHING_DOLL,
    "Tyvar, the Pummeler": TYVAR_THE_PUMMELER,
    "Under the Skin": UNDER_THE_SKIN,
    "Valgavoth's Onslaught": VALGAVOTHS_ONSLAUGHT,
    "Walk-In Closet": WALKIN_CLOSET,
    "Wary Watchdog": WARY_WATCHDOG,
    "Wickerfolk Thresher": WICKERFOLK_THRESHER,
    "Arabella, Abandoned Doll": ARABELLA_ABANDONED_DOLL,
    "Baseball Bat": BASEBALL_BAT,
    "Beastie Beatdown": BEASTIE_BEATDOWN,
    "Broodspinner": BROODSPINNER,
    "Disturbing Mirth": DISTURBING_MIRTH,
    "Drag to the Roots": DRAG_TO_THE_ROOTS,
    "Fear of Infinity": FEAR_OF_INFINITY,
    "Gremlin Tamer": GREMLIN_TAMER,
    "Growing Dread": GROWING_DREAD,
    "Inquisitive Glimmer": INQUISITIVE_GLIMMER,
    "Intruding Soulrager": INTRUDING_SOULRAGER,
    "The Jolly Balloon Man": THE_JOLLY_BALLOON_MAN,
    "Kaito, Bane of Nightmares": KAITO_BANE_OF_NIGHTMARES,
    "Marina Vendrell": MARINA_VENDRELL,
    "Midnight Mayhem": MIDNIGHT_MAYHEM,
    "Nashi, Searcher in the Dark": NASHI_SEARCHER_IN_THE_DARK,
    "Niko, Light of Hope": NIKO_LIGHT_OF_HOPE,
    "Oblivious Bookworm": OBLIVIOUS_BOOKWORM,
    "Peer Past the Veil": PEER_PAST_THE_VEIL,
    "Restricted Office": RESTRICTED_OFFICE,
    "Rip, Spawn Hunter": RIP_SPAWN_HUNTER,
    "Rite of the Moth": RITE_OF_THE_MOTH,
    "Roaring Furnace": ROARING_FURNACE,
    "Sawblade Skinripper": SAWBLADE_SKINRIPPER,
    "Shrewd Storyteller": SHREWD_STORYTELLER,
    "Shroudstomper": SHROUDSTOMPER,
    "Skullsnap Nuisance": SKULLSNAP_NUISANCE,
    "Smoky Lounge": SMOKY_LOUNGE,
    "The Swarmweaver": THE_SWARMWEAVER,
    "Undead Sprinter": UNDEAD_SPRINTER,
    "Victor, Valgavoth's Seneschal": VICTOR_VALGAVOTHS_SENESCHAL,
    "Wildfire Wickerfolk": WILDFIRE_WICKERFOLK,
    "Winter, Misanthropic Guide": WINTER_MISANTHROPIC_GUIDE,
    "Zimone, All-Questioning": ZIMONE_ALLQUESTIONING,
    "Attack-in-the-Box": ATTACKINTHEBOX,
    "Bear Trap": BEAR_TRAP,
    "Conductive Machete": CONDUCTIVE_MACHETE,
    "Dissection Tools": DISSECTION_TOOLS,
    "Found Footage": FOUND_FOOTAGE,
    "Friendly Teddy": FRIENDLY_TEDDY,
    "Ghost Vacuum": GHOST_VACUUM,
    "Glimmerlight": GLIMMERLIGHT,
    "Haunted Screen": HAUNTED_SCREEN,
    "Keys to the House": KEYS_TO_THE_HOUSE,
    "Malevolent Chandelier": MALEVOLENT_CHANDELIER,
    "Marvin, Murderous Mimic": MARVIN_MURDEROUS_MIMIC,
    "Saw": SAW,
    "Abandoned Campground": ABANDONED_CAMPGROUND,
    "Blazemire Verge": BLAZEMIRE_VERGE,
    "Bleeding Woods": BLEEDING_WOODS,
    "Etched Cornfield": ETCHED_CORNFIELD,
    "Floodfarm Verge": FLOODFARM_VERGE,
    "Gloomlake Verge": GLOOMLAKE_VERGE,
    "Hushwood Verge": HUSHWOOD_VERGE,
    "Lakeside Shack": LAKESIDE_SHACK,
    "Murky Sewer": MURKY_SEWER,
    "Neglected Manor": NEGLECTED_MANOR,
    "Peculiar Lighthouse": PECULIAR_LIGHTHOUSE,
    "Raucous Carnival": RAUCOUS_CARNIVAL,
    "Razortrap Gorge": RAZORTRAP_GORGE,
    "Strangled Cemetery": STRANGLED_CEMETERY,
    "Terramorphic Expanse": TERRAMORPHIC_EXPANSE,
    "Thornspire Verge": THORNSPIRE_VERGE,
    "Valgavoth's Lair": VALGAVOTHS_LAIR,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(DUSKMOURN_CARDS)} Duskmourn cards")
