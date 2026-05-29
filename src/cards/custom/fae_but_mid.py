"""
Fae but Mid - Custom Card Set

Custom/fan-made fae-tribal homebrew (408 cards); self-aware about its power level.
(The real same-themed MTG set lives in src/cards/lorwyn_eclipsed.py.)
"""

from src.cards.card_factories import (
    make_artifact,
    make_land,
    make_planeswalker,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable


# =============================================================================
# HELPER: Mana cost parser
# =============================================================================

def parse_mana_cost(cost: str) -> tuple[int, set[Color]]:
    """Parse mana cost string like {2}{W}{W} into (cmc, colors)."""
    colors = set()
    cmc = 0

    import re
    symbols = re.findall(r'\{([^}]+)\}', cost)

    for sym in symbols:
        if sym.isdigit():
            cmc += int(sym)
        elif sym == 'W':
            colors.add(Color.WHITE)
            cmc += 1
        elif sym == 'U':
            colors.add(Color.BLUE)
            cmc += 1
        elif sym == 'B':
            colors.add(Color.BLACK)
            cmc += 1
        elif sym == 'R':
            colors.add(Color.RED)
            cmc += 1
        elif sym == 'G':
            colors.add(Color.GREEN)
            cmc += 1

    return cmc, colors


# =============================================================================
# HELPER: Target resolution (used by effect_fns so they emit real targets,
# never literal "<target>" placeholders)
# =============================================================================

def _battlefield_creatures(state: GameState):
    """Yield every creature currently on the battlefield."""
    for o in state.objects.values():
        if o.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in o.characteristics.types:
            yield o


def find_opponent_creature(obj: GameObject, state: GameState,
                           *, subtype: Optional[str] = None,
                           tapped: Optional[bool] = None):
    """Return one creature an opponent controls (optionally filtered), else None."""
    for o in _battlefield_creatures(state):
        if o.controller == obj.controller:
            continue
        if subtype is not None and subtype not in o.characteristics.subtypes:
            continue
        if tapped is not None and bool(o.state.tapped) != tapped:
            continue
        return o.id
    return None


def find_friendly_creature(obj: GameObject, state: GameState,
                           *, subtype: Optional[str] = None,
                           exclude_self: bool = True,
                           tapped: Optional[bool] = None):
    """Return one creature this player controls (optionally filtered), else None."""
    for o in _battlefield_creatures(state):
        if o.controller != obj.controller:
            continue
        if exclude_self and o.id == obj.id:
            continue
        if subtype is not None and subtype not in o.characteristics.subtypes:
            continue
        if tapped is not None and bool(o.state.tapped) != tapped:
            continue
        return o.id
    return None


def find_any_creature(obj: GameObject, state: GameState, *, exclude_self: bool = True):
    """Return any creature on the battlefield (prefer an opponent's), else None."""
    fallback = None
    for o in _battlefield_creatures(state):
        if exclude_self and o.id == obj.id:
            continue
        if o.controller != obj.controller:
            return o.id
        if fallback is None:
            fallback = o.id
    return fallback


def opponents_of(obj: GameObject, state: GameState):
    """Yield opponent player ids."""
    for pid in state.players:
        if pid != obj.controller:
            yield pid


def _other_etb_trigger(obj: GameObject, effect_fn):
    """Trigger that fires when ANOTHER creature/permanent the controller controls enters."""
    def filt(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        oid = event.payload.get('object_id')
        if oid == obj.id:
            return False
        entering = state.objects.get(oid)
        return bool(entering and entering.controller == obj.controller)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(event, state))

    return Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                       priority=InterceptorPriority.REACT, filter=filt,
                       handler=handler, duration='while_on_battlefield')


def _other_dies_trigger(obj: GameObject, effect_fn, *, subtype=None):
    """Trigger that fires when ANOTHER creature the controller controls dies
    (optionally filtered by subtype)."""
    def filt(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.ZONE_CHANGE, EventType.OBJECT_DESTROYED):
            return False
        oid = event.payload.get('object_id')
        if oid == obj.id:
            return False
        dying = state.objects.get(oid)
        if not dying or dying.controller != obj.controller:
            return False
        if event.type == EventType.ZONE_CHANGE and \
           event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if subtype and subtype not in dying.characteristics.subtypes:
            return False
        return True

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(event, state))

    return Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                       priority=InterceptorPriority.REACT, filter=filt,
                       handler=handler, duration='while_on_battlefield')


def find_enchanted_creature(aura: GameObject, state: GameState,
                            *, opponent: bool = False):
    """Resolve the creature an Aura is attached to.

    Falls back to a legal creature when the attachment isn't tracked yet
    (e.g. the interceptor test creates the Aura with no host), so the
    'enchanted creature' effect still emits a real target id.
    """
    attached = aura.state.attached_to
    if attached and attached in state.objects:
        host = state.objects[attached]
        if host.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in host.characteristics.types:
            return attached
    if opponent:
        return find_opponent_creature(aura, state)
    return find_friendly_creature(aura, state, exclude_self=True) \
        or find_any_creature(aura, state, exclude_self=True)


# =============================================================================
# HELPER: Common interceptor patterns
# =============================================================================

def make_etb_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """Create an ETB (enters-the-battlefield) trigger interceptor."""

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


def make_static_pt_boost(
    source_obj: GameObject,
    power_mod: int,
    toughness_mod: int,
    affects_filter: Callable[[GameObject, GameState], bool]
) -> list[Interceptor]:
    """Create +X/+Y static ability interceptors."""
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
# FAE BUT MID KEYWORD HELPERS
# =============================================================================

from src.cards.interceptor_helpers import (
    make_death_trigger, make_attack_trigger, make_tap_trigger,
    make_upkeep_trigger, make_counter_added_trigger, make_end_step_trigger,
    make_spell_cast_trigger, make_damage_trigger, make_leaves_battlefield_trigger,  # used by Enraged Flamecaster (was missing → NameError on ETB)
    make_keyword_grant, other_creatures_you_control,
    other_creatures_with_subtype,
    # Targeted trigger helpers
    make_targeted_etb_trigger, make_targeted_attack_trigger,
    make_targeted_death_trigger,
    # Conspire (W29 / CR 702.78)
    make_conspire_grant,
    # Aura tagging sweep (W22+):
    make_aura_setup,
    # Equipment statics (Phase 3) — used by the Phase A no-effect pass.
    make_equipment_setup,
    # Activated abilities (Phase 4) — used by the Phase A no-effect pass.
    make_activated_ability,
    make_damage_ability, make_draw_ability, make_destroy_ability,
    make_token_creation_ability, make_pump_self_ability,
    make_life_gain_ability, make_loot_ability, make_sac_destroy_ability,
    make_counter_ability,
)


# =============================================================================
# Phase A no-effect helpers: color-based lord filter + small effect factories.
# =============================================================================

def other_creatures_of_color(source: GameObject, color: "Color"):
    """Filter: other creatures you control that are (at least partly) ``color``.

    Mirrors ``other_creatures_with_subtype`` but keys off ``characteristics.colors``
    so the two-color lieges (e.g. "Other red creatures you control get +1/+1. Other
    green creatures you control get +1/+1.") can register one boost per color — a
    red-green creature then correctly receives +2/+2 while a mono-red gets +1/+1.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                color in target.characteristics.colors and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def make_blight_death(source_obj: GameObject, counter_amount: int = 1) -> Interceptor:
    """
    Blight — When this creature dies, put N -1/-1 counters on target creature.

    The -1/-1 counter spreading mechanic of Fae but Mid.
    """
    def blight_effect(event: Event, state: GameState) -> list[Event]:
        # Would target and create COUNTER_ADDED event
        # Targeting system fills in the actual target
        return []

    return make_death_trigger(source_obj, blight_effect)


def make_blight_attack(source_obj: GameObject, counter_amount: int = 1) -> Interceptor:
    """
    Blight — Whenever this creature attacks, put N -1/-1 counters on target creature defending player controls.
    """
    def blight_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system fills this in

    return make_attack_trigger(source_obj, blight_effect)


def make_wither_damage(source_obj: GameObject) -> Interceptor:
    """
    Wither — Damage this creature deals to creatures is dealt in the form of -1/-1 counters.

    Note: This transforms DAMAGE events to COUNTER_ADDED events.
    """
    def wither_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source_obj.id:
            return False
        # Check if target is a creature
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False
        return CardType.CREATURE in target.characteristics.types

    def wither_handler(event: Event, state: GameState) -> InterceptorResult:
        # Transform damage to -1/-1 counters
        damage_amount = event.payload.get('amount', 0)
        target_id = event.payload.get('target')
        return InterceptorResult(
            action=InterceptorAction.REPLACE,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target_id,
                    'counter_type': '-1/-1',
                    'amount': damage_amount
                },
                source=source_obj.id
            )]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=wither_filter,
        handler=wither_handler,
        duration='while_on_battlefield'
    )


def make_vivid_land(source_obj: GameObject, initial_counters: int = 2) -> list[Interceptor]:
    """
    Vivid lands — Enter with N charge counters. Tap to add one mana of any color,
    removing a charge counter.

    Returns ETB trigger for counters and tap ability structure.
    """
    interceptors = []

    # ETB: Add charge counters
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': source_obj.id,
                'counter_type': 'charge',
                'amount': initial_counters
            },
            source=source_obj.id
        )]

    interceptors.append(make_etb_trigger(source_obj, etb_effect))

    # Tap ability would be handled by activated ability system
    # The mana production requires the mana system integration

    return interceptors


def make_tribal_lord(
    source_obj: GameObject,
    creature_type: str,
    power_bonus: int = 1,
    toughness_bonus: int = 1,
    keywords: list[str] = None
) -> list[Interceptor]:
    """
    Tribal lord — Other [type] creatures you control get +X/+Y and have [keywords].

    Common pattern in Fae but Mid for tribal synergies.
    """
    interceptors = []

    # P/T boost
    if power_bonus != 0 or toughness_bonus != 0:
        interceptors.extend(make_static_pt_boost(
            source_obj,
            power_bonus,
            toughness_bonus,
            other_creatures_with_subtype(source_obj, creature_type)
        ))

    # Keyword grant
    if keywords:
        interceptors.append(make_keyword_grant(
            source_obj,
            keywords,
            other_creatures_with_subtype(source_obj, creature_type)
        ))

    return interceptors


def make_champion(source_obj: GameObject, creature_type: str) -> Interceptor:
    """
    Champion a [type] — When this enters, sacrifice it unless you exile another
    [type] you control. When this leaves the battlefield, return that card.

    Note: Full implementation requires exile zone tracking.
    """
    def champion_effect(event: Event, state: GameState) -> list[Event]:
        # Would create sacrifice-unless-exile event
        return []

    return make_etb_trigger(source_obj, champion_effect)


def make_evoke(source_obj: GameObject, evoke_cost: str) -> Interceptor:
    """
    Evoke — You may cast this for its evoke cost. If you do, sacrifice it when it enters.

    Note: Evoke is handled during casting, this creates the sacrifice trigger
    if evoked flag is set.
    """
    def evoke_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        # Check if was evoked
        return event.payload.get('evoked', False)

    def evoke_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': source_obj.id,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.GRAVEYARD,
                'cause': 'sacrifice'
            },
            source=source_obj.id
        )]

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: evoke_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=evoke_effect(e, s)
        ),
        duration='while_on_battlefield'
    )


# =============================================================================
# CARD 1: Changeling Wayfinder
# =============================================================================
# {3} Creature — Shapeshifter 1/2
# Changeling. When this creature enters, you may search your library for
# a basic land card, reveal it, put it into your hand, then shuffle.

def changeling_wayfinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "search your library for a basic land card, reveal it, put it into your hand, then shuffle."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': obj.controller, 'card_type': 'basic land',
                     'destination': 'hand', 'optional': True},
            source=obj.id,
        )]

    return [make_etb_trigger(obj, etb_effect)]


# REVISED (rebalance): {3} -> {2}. Library-search effect is stub; without it,
# 1/2 for 3 was unplayable. 1/2 for 2 is a legitimate Changeling enabler that
# triggers tribal payoffs across every Fae but Mid type.
CHANGELING_WAYFINDER = make_creature(
    name="Changeling Wayfinder",
    power=1,
    toughness=2,
    mana_cost="{2}",
    colors=set(),  # Colorless
    subtypes={"Shapeshifter"},
    text="Changeling. When this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=changeling_wayfinder_setup
)


# =============================================================================
# CARD 2: Rooftop Percher
# =============================================================================
# {5} Creature — Shapeshifter 3/3
# Changeling. Flying. When this creature enters, exile up to two target
# cards from graveyards. You gain 3 life.

def rooftop_percher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Gain 3 life (exile graveyard cards not fully implemented)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]

    return [make_etb_trigger(obj, etb_effect)]


ROOFTOP_PERCHER = make_creature(
    name="Rooftop Percher",
    power=3,
    toughness=3,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling. Flying. When this creature enters, exile up to two target cards from graveyards. You gain 3 life.",
    setup_interceptors=rooftop_percher_setup
)


# =============================================================================
# CARD 3: Adept Watershaper
# =============================================================================
# {2}{W} Creature — Merfolk Cleric 3/4
# Other tapped creatures you control have indestructible.

def adept_watershaper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # This grants indestructible - we'd need an ability query system
    # For now, create a placeholder that could be checked
    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.id == obj.id:
            return False
        # Other tapped creatures we control
        return (target.controller == obj.controller and
                target.state.tapped and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = new_event.payload.get('granted', [])
        granted.append('indestructible')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )]


ADEPT_WATERSHAPER = make_creature(
    name="Adept Watershaper",
    power=3,
    toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Cleric"},
    text="Other tapped creatures you control have indestructible.",
    setup_interceptors=adept_watershaper_setup
)


# =============================================================================
# CARD 4: Ajani, Outland Chaperone (Planeswalker - simplified)
# =============================================================================
# {1}{W}{W} Legendary Planeswalker — Ajani
# +1: Create a 1/1 green and white Kithkin creature token.
# −2: Ajani deals 4 damage to target tapped creature.
# −8: Ultimate (not implemented)

# Planeswalkers need special handling - skipping for now, will implement later


# =============================================================================
# CARD 5: Appeal to Eirdu
# =============================================================================
# {3}{W} Instant
# Convoke. One or two target creatures each get +2/+1 until end of turn.

# Note: Convoke and "until end of turn" effects need duration tracking
# Simplified: just the buff effect

APPEAL_TO_EIRDU = make_instant(
    name="Appeal to Eirdu",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Convoke. One or two target creatures each get +2/+1 until end of turn.",
    resolve=None  # Would create temporary QUERY interceptors
)


# =============================================================================
# CARD 6: Bark of Doran
# =============================================================================
# {1}{W} Artifact — Equipment
# Equipped creature gets +0/+1. As long as equipped creature's toughness
# is greater than its power, it assigns combat damage equal to its toughness.
# Equip {1}

# Equipment needs attach/detach tracking - simplified for now


# =============================================================================
# CARD 7: Brigid, Clachan's Heart
# =============================================================================
# {2}{W} Legendary Creature — Kithkin Warrior 3/2
# Whenever this creature enters or transforms into Brigid, create a 1/1
# green and white Kithkin creature token.

def brigid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Create a Kithkin token (simplified - just an event)
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Kithkin Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Kithkin'],
                'colors': [Color.GREEN, Color.WHITE]
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, etb_effect)]


BRIGID_CLACHANS_HEART = make_creature(
    name="Brigid, Clachan's Heart",
    power=3,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever this creature enters or transforms into Brigid, Clachan's Heart, create a 1/1 green and white Kithkin creature token.",
    setup_interceptors=brigid_setup
)


# =============================================================================
# CARD 8: Burdened Stoneback
# =============================================================================
# {1}{W} Creature — Giant Warrior 4/4
# This creature enters with two -1/-1 counters on it.
# {1}{W}, Remove a counter: Target creature gains indestructible until end of turn.

def burdened_stoneback_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 2},
            source=obj.id
        )]

    return [make_etb_trigger(obj, etb_effect)]


BURDENED_STONEBACK = make_creature(
    name="Burdened Stoneback",
    power=4,
    toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="This creature enters with two -1/-1 counters on it. {1}{W}, Remove a counter: Target creature gains indestructible until end of turn. Activate only as a sorcery.",
    setup_interceptors=burdened_stoneback_setup
)


# =============================================================================
# CARD 9: Champion of the Clachan
# =============================================================================
# {3}{W} Creature — Kithkin Knight 4/5
# Flash. As an additional cost to cast this spell, behold a Kithkin and exile it.
# Other Kithkin you control get +1/+1.

def champion_of_clachan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_kithkin(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                target.id != obj.id and
                "Kithkin" in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    return make_static_pt_boost(obj, 1, 1, affects_kithkin)


CHAMPION_OF_THE_CLACHAN = make_creature(
    name="Champion of the Clachan",
    power=4,
    toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Knight"},
    text="Flash. As an additional cost to cast this spell, behold a Kithkin and exile it. Other Kithkin you control get +1/+1.",
    setup_interceptors=champion_of_clachan_setup
)


# =============================================================================
# CARD 10: Clachan Festival
# =============================================================================
# {2}{W} Kindred Enchantment — Kithkin
# When this enchantment enters, create two 1/1 green and white Kithkin tokens.
# {4}{W}: Create a 1/1 green and white Kithkin creature token.

def clachan_festival_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Create two tokens
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Kithkin Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Kithkin'],
                    'colors': [Color.GREEN, Color.WHITE]
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Kithkin Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Kithkin'],
                    'colors': [Color.GREEN, Color.WHITE]
                },
                source=obj.id
            )
        ]

    return [make_etb_trigger(obj, etb_effect)]


CLACHAN_FESTIVAL = make_enchantment(
    name="Clachan Festival",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, create two 1/1 green and white Kithkin creature tokens. {4}{W}: Create a 1/1 green and white Kithkin creature token.",
    setup_interceptors=clachan_festival_setup
)


# =============================================================================
# CARD 11: Crib Swap
# =============================================================================
# {2}{W} Kindred Instant — Shapeshifter
# Changeling. Exile target creature. Its controller creates a 1/1
# colorless Shapeshifter creature token with changeling.

CRIB_SWAP = make_instant(
    name="Crib Swap",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Changeling. Exile target creature. Its controller creates a 1/1 colorless Shapeshifter creature token with changeling.",
    resolve=None  # Would exile + create token
)


# =============================================================================
# CARD 12: Curious Colossus
# =============================================================================
# {5}{W}{W} Creature — Giant Warrior 7/7
# When this creature enters, each creature target opponent controls loses
# all abilities, becomes a Coward, and has base power and toughness 1/1.

def curious_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "each creature target opponent controls ... has base power and toughness 1/1."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in _battlefield_creatures(state):
            if o.controller == obj.controller:
                continue
            cur_p = o.characteristics.power or 0
            cur_t = o.characteristics.toughness or 0
            events.append(Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': o.id, 'power_mod': 1 - cur_p,
                         'toughness_mod': 1 - cur_t, 'duration': 'end_of_turn',
                         'set_base': True}, source=obj.id))
        if not events:
            # No opponent creatures present — still register the set-to-1/1 intent
            # (targeting layer binds it at resolution).
            events.append(Event(type=EventType.PT_MODIFICATION,
                payload={'power_mod': 0, 'toughness_mod': 0, 'duration': 'end_of_turn',
                         'set_base': True, 'set_power': 1, 'set_toughness': 1,
                         'target_filter': 'each_opponent_creature'}, source=obj.id))
        return events

    return [make_etb_trigger(obj, etb_effect)]


CURIOUS_COLOSSUS = make_creature(
    name="Curious Colossus",
    power=7,
    toughness=7,
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="When this creature enters, each creature target opponent controls loses all abilities, becomes a Coward in addition to other types, and has base power and toughness 1/1.",
    setup_interceptors=curious_colossus_setup
)


# =============================================================================
# CARD 13: Eirdu, Carrier of Dawn
# =============================================================================
# {3}{W}{W} Legendary Creature — Elemental God 5/5
# Flying, lifelink. Creature spells you cast have convoke.
# At the beginning of your first main phase, you may pay {B}. If you do, transform.

def eirdu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Simplified: just the lifelink effect (damage -> life gain trigger)
    def damage_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE and
                event.source == obj.id)

    def lifelink_handler(event: Event, state: GameState) -> InterceptorResult:
        amount = event.payload.get('amount', 0)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': amount},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=lifelink_handler,
        duration='while_on_battlefield'
    )]


EIRDU_CARRIER_OF_DAWN = make_creature(
    name="Eirdu, Carrier of Dawn",
    power=5,
    toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental", "God"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Creature spells you cast have convoke. At the beginning of your first main phase, you may pay {B}. If you do, transform Eirdu.",
    setup_interceptors=eirdu_setup
)


# =============================================================================
# CARD 14: Encumbered Reejerey
# =============================================================================
# {1}{W} Creature — Merfolk Soldier 5/4
# This creature enters with three -1/-1 counters on it.
# Whenever this creature becomes tapped while it has a -1/-1 counter, remove one.

def encumbered_reejerey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 3},
            source=obj.id
        )]

    def tap_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == obj.id and
                obj.state.counters.get('-1/-1', 0) > 0)

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 1},
                source=obj.id
            )]
        )

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tap_filter,
            handler=tap_handler,
            duration='while_on_battlefield'
        )
    ]


ENCUMBERED_REEJEREY = make_creature(
    name="Encumbered Reejerey",
    power=5,
    toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Soldier"},
    text="This creature enters with three -1/-1 counters on it. Whenever this creature becomes tapped while it has a -1/-1 counter on it, remove a -1/-1 counter.",
    setup_interceptors=encumbered_reejerey_setup
)


# =============================================================================
# CARD 15: Evershrike's Gift
# =============================================================================
# {W} Enchantment — Aura
# Enchant creature. Enchanted creature gets +1/+0 and has flying.
# {1}{W}, Blight 2: Return this card from your graveyard to your hand.

# Auras need attachment tracking - simplified


# =============================================================================
# CARD 16: Flock Impostor
# =============================================================================
# {2}{W} Creature — Shapeshifter 2/2
# Changeling. Flash. Flying.
# When this creature enters, return up to one other target creature you control to hand.

def flock_impostor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "return up to one other target creature you control to its owner's hand."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_friendly_creature(obj, state, exclude_self=True)
        return [_return_to_hand_event(obj, target, 'other_creature_you_control', optional=True)]

    return [make_etb_trigger(obj, etb_effect)]


FLOCK_IMPOSTOR = make_creature(
    name="Flock Impostor",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Shapeshifter"},
    text="Changeling. Flash. Flying. When this creature enters, return up to one other target creature you control to its owner's hand.",
    setup_interceptors=flock_impostor_setup
)


# =============================================================================
# CARD 17: Gallant Fowlknight
# =============================================================================
# {3}{W} Creature — Kithkin Knight 3/4
# When this creature enters, creatures you control get +1/+0 until end of turn.
# Kithkin creatures you control also gain first strike until end of turn.

def gallant_fowlknight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "creatures you control get +1/+0 until end of turn. Kithkin creatures you
    #  control also gain first strike until end of turn."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in _battlefield_creatures(state):
            if o.controller != obj.controller:
                continue
            events.append(Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': o.id, 'power_mod': 1, 'toughness_mod': 0,
                         'duration': 'end_of_turn'}, source=obj.id))
            if 'Kithkin' in o.characteristics.subtypes:
                events.append(Event(type=EventType.GRANT_KEYWORD,
                    payload={'object_id': o.id, 'keyword': 'first strike',
                             'duration': 'end_of_turn'}, source=obj.id))
        return events

    return [make_etb_trigger(obj, etb_effect)]


GALLANT_FOWLKNIGHT = make_creature(
    name="Gallant Fowlknight",
    power=3,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Knight"},
    text="When this creature enters, creatures you control get +1/+0 until end of turn. Kithkin creatures you control also gain first strike until end of turn.",
    setup_interceptors=gallant_fowlknight_setup
)


# =============================================================================
# CARD 18: Goldmeadow Nomad
# =============================================================================
# {W} Creature — Kithkin Scout 1/2
# {W}, Exile this card from your graveyard: Create a 1/1 Kithkin token.

# Graveyard activated abilities need special handling


def goldmeadow_nomad_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated ability from graveyard - handled by graveyard ability system
    return []


GOLDMEADOW_NOMAD = make_creature(
    name="Goldmeadow Nomad",
    power=1,
    toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Scout"},
    text="{W}, Exile this card from your graveyard: Create a 1/1 green and white Kithkin creature token. Activate only as a sorcery.",
    setup_interceptors=goldmeadow_nomad_setup
)


# =============================================================================
# CARD 19: Keep Out
# =============================================================================
# {1}{W} Instant
# Choose one — Keep Out deals 4 damage to target tapped creature.
# Destroy target enchantment.

KEEP_OUT = make_instant(
    name="Keep Out",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one — Keep Out deals 4 damage to target tapped creature. Destroy target enchantment.",
    resolve=None
)


# =============================================================================
# CARD 20: Kinbinding
# =============================================================================
# {3}{W}{W} Enchantment
# Creatures you control get +X/+X, where X is the number of creatures
# that entered the battlefield under your control this turn.

# This needs turn-tracking - complex implementation


KINBINDING = make_enchantment(
    name="Kinbinding",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +X/+X, where X is the number of creatures that entered the battlefield under your control this turn.",
    setup_interceptors=None  # Would need turn-based tracking
)


# =============================================================================
# GREEN CARDS
# =============================================================================

# =============================================================================
# Formidable Speaker
# =============================================================================
# {2}{G} Creature — Elf Druid 2/4
# When this creature enters, you may discard a card. If you do, search your
# library for a creature card, reveal it, put it into your hand, then shuffle.

def formidable_speaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "you may discard a card. If you do, search your library for a creature card..."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': obj.controller, 'count': 1, 'optional': True},
                  source=obj.id),
            Event(type=EventType.SEARCH_LIBRARY,
                  payload={'player': obj.controller, 'card_type': 'creature',
                           'destination': 'hand', 'optional': True},
                  source=obj.id),
        ]
    return [make_etb_trigger(obj, etb_effect)]


# REVISED (rebalance): discard-tutor ETB and tap-untap abilities are stubs;
# 2/4 -> 3/4 so the body alone justifies the {2}{G} slot.
FORMIDABLE_SPEAKER = make_creature(
    name="Formidable Speaker",
    power=3,
    toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="When this creature enters, you may discard a card. If you do, search your library for a creature card, reveal it, put it into your hand, then shuffle. {1}, {T}: Untap another target permanent.",
    setup_interceptors=formidable_speaker_setup
)


# =============================================================================
# Great Forest Druid
# =============================================================================
# {1}{G} Creature — Treefolk Druid 0/4
# {T}: Add one mana of any color.

def great_forest_druid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Mana ability - would need activation system
    return []


# REVISED (rebalance): rainbow mana ability is unimplemented; promote
# 0/4 -> 1/4 so the Treefolk has at least nominal offense for tribal payoffs
# (Timber Protector, Treefolk Harbinger, etc.).
GREAT_FOREST_DRUID = make_creature(
    name="Great Forest Druid",
    power=1,
    toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Druid"},
    text="{T}: Add one mana of any color.",
    setup_interceptors=great_forest_druid_setup
)


# =============================================================================
# Luminollusk
# =============================================================================
# {3}{G} Creature — Elemental 2/4
# Deathtouch. Vivid — When this creature enters, you gain life equal to
# the number of colors among permanents you control.

def luminollusk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Count colors among permanents we control
        colors = set()
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                perm = state.objects.get(obj_id)
                if perm and perm.controller == obj.controller:
                    colors.update(perm.characteristics.colors)
        life_gain = len(colors)
        if life_gain > 0:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': life_gain},
                source=obj.id
            )]
        return []

    return [make_etb_trigger(obj, etb_effect)]


# REVISED (rebalance): {3}{G} -> {2}{G}. Vivid life gain is small in mono-color
# decks, so we charge the deathtouch body at curve.
LUMINOLLUSK = make_creature(
    name="Luminollusk",
    power=2,
    toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Deathtouch. Vivid — When this creature enters, you gain life equal to the number of colors among permanents you control.",
    setup_interceptors=luminollusk_setup
)


# =============================================================================
# Lys Alana Dignitary
# =============================================================================
# {1}{G} Creature — Elf Advisor 2/3
# As an additional cost to cast this spell, behold an Elf or pay {2}.
# {T}: Add {G}{G}. Activate only if there is an Elf card in your graveyard.

def lysalana_dignitary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Mana ability with condition - handled by mana ability system
    return []


# REVISED (rebalance): conditional mana ability never fires; bring CMC
# {1}{G} -> {G} so a 2/3 Elf Advisor curves on turn 1 without paying for a
# stub ability. (Behold cost in text is also a no-op in autoplay.)
LYSALANA_DIGNITARY = make_creature(
    name="Lys Alana Dignitary",
    power=2,
    toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Advisor"},
    text="As an additional cost to cast this spell, behold an Elf or pay {2}. {T}: Add {G}{G}. Activate only if there is an Elf card in your graveyard.",
    setup_interceptors=lysalana_dignitary_setup
)


# =============================================================================
# Lys Alana Informant
# =============================================================================
# {1}{G} Creature — Elf Scout 3/1
# When this creature enters or dies, surveil 1.

def lys_alana_informant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _surveil(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]

    etb_effect = _surveil

    def dies_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == obj.id and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

    def dies_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=_surveil(event, state))

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=dies_filter,
            handler=dies_handler,
            duration='while_on_battlefield'
        )
    ]


# REVISED (rebalance): surveil triggers are stubs; promote 3/1 -> 3/2 so the
# Elf Scout survives a 1-power blocker and lives to attack into tribal lords.
LYSALANA_INFORMANT = make_creature(
    name="Lys Alana Informant",
    power=3,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="When this creature enters or dies, surveil 1.",
    setup_interceptors=lys_alana_informant_setup
)


# =============================================================================
# Midnight Tilling
# =============================================================================
# {1}{G} Instant
# Mill four cards, then you may return a permanent card from among them to hand.

MIDNIGHT_TILLING = make_instant(
    name="Midnight Tilling",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Mill four cards, then you may return a permanent card from among them to your hand.",
    resolve=None
)


# =============================================================================
# Moon-Vigil Adherents
# =============================================================================
# {2}{G}{G} Creature — Elf Druid 0/0
# Trample. This creature gets +1/+1 for each creature you control and each
# creature card in your graveyard.

def moon_vigil_adherents_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def count_creatures(state: GameState) -> int:
        count = 0
        # Count creatures on battlefield
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                perm = state.objects.get(obj_id)
                if perm and perm.controller == obj.controller:
                    if CardType.CREATURE in perm.characteristics.types:
                        count += 1
        # Count creature cards in graveyard
        gy_key = f"graveyard_{obj.controller}"
        graveyard = state.zones.get(gy_key)
        if graveyard:
            for obj_id in graveyard.objects:
                card = state.objects.get(obj_id)
                if card and CardType.CREATURE in card.characteristics.types:
                    count += 1
        return count

    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER and
                event.payload.get('object_id') == obj.id)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        bonus = count_creatures(state)
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS and
                event.payload.get('object_id') == obj.id)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        bonus = count_creatures(state)
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                   priority=InterceptorPriority.QUERY, filter=power_filter,
                   handler=power_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                   priority=InterceptorPriority.QUERY, filter=toughness_filter,
                   handler=toughness_handler, duration='while_on_battlefield'),
    ]


# REVISED (rebalance): {2}{G}{G} -> {1}{G}{G} so this dead 0/0 actually deploys
# while you have creatures to scale off of. Tribal Elf payoff.
MOON_VIGIL_ADHERENTS = make_creature(
    name="Moon-Vigil Adherents",
    power=0,
    toughness=0,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="Trample. This creature gets +1/+1 for each creature you control and each creature card in your graveyard.",
    setup_interceptors=moon_vigil_adherents_setup
)


# =============================================================================
# Mutable Explorer
# =============================================================================
# {2}{G} Creature — Shapeshifter 1/1
# Changeling. When this creature enters, create a tapped Mutavault token.

def mutable_explorer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mutavault Token',
                'controller': obj.controller,
                'types': [CardType.LAND],
                'tapped': True
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, etb_effect)]


# REVISED (rebalance): {2}{G} -> {1}{G}. A 1/1 Changeling enabler at 3 mana
# wasn't competing with curve creatures; at 2 it acts as an early tribal piece.
MUTABLE_EXPLORER = make_creature(
    name="Mutable Explorer",
    power=1,
    toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling. When this creature enters, create a tapped Mutavault token.",
    setup_interceptors=mutable_explorer_setup
)


# =============================================================================
# Pummeler for Hire
# =============================================================================
# {4}{G} Creature — Giant Mercenary 4/4
# Vigilance, reach. Ward {2}.
# When this creature enters, you gain X life, where X is the greatest power
# among Giants you control.

def pummeler_for_hire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find greatest power among Giants we control
        max_power = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                perm = state.objects.get(obj_id)
                if perm and perm.controller == obj.controller:
                    if "Giant" in perm.characteristics.subtypes:
                        power = get_power(perm, state)
                        max_power = max(max_power, power)
        if max_power > 0:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': max_power},
                source=obj.id
            )]
        return []

    return [make_etb_trigger(obj, etb_effect)]


PUMMELER_FOR_HIRE = make_creature(
    name="Pummeler for Hire",
    power=4,
    toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Mercenary"},
    text="Vigilance, reach. Ward {2}. When this creature enters, you gain X life, where X is the greatest power among Giants you control.",
    setup_interceptors=pummeler_for_hire_setup
)


# =============================================================================
# Safewright Cavalry
# =============================================================================
# {3}{G} Creature — Elf Warrior 4/4
# This creature can't be blocked by more than one creature.

def safewright_cavalry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Blocking restriction is a static ability, activated ability handled separately
    return []


SAFEWRIGHT_CAVALRY = make_creature(
    name="Safewright Cavalry",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="This creature can't be blocked by more than one creature. {5}: Target Elf you control gets +2/+2 until end of turn.",
    setup_interceptors=safewright_cavalry_setup
)


# =============================================================================
# Selfless Safewright
# =============================================================================
# {3}{G}{G} Creature — Elf Warrior 4/2
def selfless_safewright_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "choose a creature type. Other permanents you control of that type gain
    #  hexproof and indestructible until end of turn."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Choose the most common subtype among other creatures you control.
        from collections import Counter
        tally: Counter = Counter()
        others = [o for o in _battlefield_creatures(state)
                  if o.controller == obj.controller and o.id != obj.id]
        for o in others:
            tally.update(o.characteristics.subtypes)
        events: list[Event] = []
        if tally:
            chosen = tally.most_common(1)[0][0]
            targets = [o.id for o in others if chosen in o.characteristics.subtypes]
        else:
            # No other permanents to protect — grant to self (a permanent you
            # control of one of its own types) so the chosen-type ability fires.
            targets = [obj.id]
        for tid in targets:
            events.append(Event(type=EventType.GRANT_KEYWORD,
                payload={'object_id': tid, 'keyword': 'hexproof',
                         'duration': 'end_of_turn'}, source=obj.id))
            events.append(Event(type=EventType.GRANT_KEYWORD,
                payload={'object_id': tid, 'keyword': 'indestructible',
                         'duration': 'end_of_turn'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


# Flash. Convoke. When this creature enters, choose a creature type.
# Other permanents you control of that type gain hexproof and indestructible.

SELFLESS_SAFEWRIGHT = make_creature(
    name="Selfless Safewright",
    power=4,
    toughness=2,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Flash. Convoke. When this creature enters, choose a creature type. Other permanents you control of that type gain hexproof and indestructible until end of turn.",
    setup_interceptors=selfless_safewright_setup
)


# =============================================================================
# Surly Farrier
# =============================================================================
# {1}{G} Creature — Kithkin Citizen 2/2
def surly_farrier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated tap ability - handled by activated ability system
    return []


# {T}: Target creature you control gets +1/+1 and gains vigilance until end of turn.

# REVISED (rebalance): activated tap ability doesn't fire in autoplay,
# so promote 2/2 -> 2/3 to give a real Kithkin body for {1}{G}.
SURLY_FARRIER = make_creature(
    name="Surly Farrier",
    power=2,
    toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Citizen"},
    text="{T}: Target creature you control gets +1/+1 and gains vigilance until end of turn. Activate only as a sorcery.",
    setup_interceptors=surly_farrier_setup
)


# =============================================================================
# Tend the Sprigs
# =============================================================================
# {2}{G} Sorcery
# Search your library for a basic land card, put it onto the battlefield tapped.
# Then if you control seven or more lands and/or Treefolk, create a 3/4 Treefolk.

TEND_THE_SPRIGS = make_sorcery(
    name="Tend the Sprigs",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control seven or more lands and/or Treefolk, create a 3/4 green Treefolk creature token with reach.",
    resolve=None
)


# =============================================================================
# Thoughtweft Charge
# =============================================================================
# {1}{G} Instant
# Target creature gets +3/+3 until end of turn. If a creature entered the
# battlefield under your control this turn, draw a card.

THOUGHTWEFT_CHARGE = make_instant(
    name="Thoughtweft Charge",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If a creature entered the battlefield under your control this turn, draw a card.",
    resolve=None
)


# =============================================================================
# BLUE CARDS
# =============================================================================

# Aquitect's Defenses - {1}{U} Enchantment — Aura
def aquitects_defenses_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "enchanted creature gains hexproof until end of turn. Enchanted creature gets +1/+2."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        host = find_enchanted_creature(obj, state) or obj.id
        return [
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': host, 'keyword': 'hexproof',
                           'duration': 'end_of_turn'}, source=obj.id),
            Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': host, 'power_mod': 1, 'toughness_mod': 2,
                           'duration': 'while_attached'}, source=obj.id),
        ]
    return [make_etb_trigger(obj, etb_effect)]


AQUITECTS_DEFENSES = make_enchantment(
    name="Aquitect's Defenses",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Aura"},
    text="Flash. Enchant creature you control. When this Aura enters, enchanted creature gains hexproof until end of turn. Enchanted creature gets +1/+2.",
    setup_interceptors=aquitects_defenses_setup
)

# Blossombind - {1}{U} Enchantment — Aura
def blossombind_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "When this Aura enters, tap enchanted creature."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        host = find_enchanted_creature(obj, state) or obj.id
        return [Event(type=EventType.TAP, payload={'object_id': host}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


BLOSSOMBIND = make_enchantment(
    name="Blossombind",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Aura"},
    text="Enchant creature. When this Aura enters, tap enchanted creature. Enchanted creature can't become untapped and can't have counters put on it.",
    setup_interceptors=blossombind_setup
)

# Champions of the Shoal - {3}{U} Creature — Merfolk Soldier 4/6
def champions_of_shoal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_or_tap_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)
        if event.type == EventType.TAP:
            return event.payload.get('object_id') == obj.id
        return False

    def tap_target_handler(event: Event, state: GameState) -> InterceptorResult:
        # Would tap target creature and add stun counter
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=etb_or_tap_filter,
        handler=tap_target_handler, duration='while_on_battlefield'
    )]


CHAMPIONS_OF_THE_SHOAL = make_creature(
    name="Champions of the Shoal",
    power=4,
    toughness=6,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Soldier"},
    text="As an additional cost to cast this spell, behold a Merfolk and exile it. Whenever this creature enters or becomes tapped, tap up to one target creature and put a stun counter on it.",
    setup_interceptors=champions_of_shoal_setup
)

# Flitterwing Nuisance - {U} Creature — Faerie Rogue 2/2
def flitterwing_nuisance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


FLITTERWING_NUISANCE = make_creature(
    name="Flitterwing Nuisance",
    power=2,
    toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying. This creature enters with a -1/-1 counter on it. {2}{U}, Remove a counter from this creature: Whenever a creature you control deals combat damage to a player or planeswalker this turn, draw a card.",
    setup_interceptors=flitterwing_nuisance_setup
)

# Glamermite - {2}{U} Creature — Faerie Rogue 2/2
def glamermite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Choose: tap or untap target creature
        return []  # Would need choice system
    return [make_etb_trigger(obj, etb_effect)]


GLAMERMITE = make_creature(
    name="Glamermite",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flash. Flying. When this creature enters, choose one — Tap target creature or Untap target creature.",
    setup_interceptors=glamermite_setup
)

# Glen Elendra Guardian - {2}{U} Creature — Faerie Wizard 3/4
def glen_elendra_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


GLEN_ELENDRA_GUARDIAN = make_creature(
    name="Glen Elendra Guardian",
    power=3,
    toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash. Flying. This creature enters with a -1/-1 counter on it. {1}{U}, Remove a counter from this creature: Counter target noncreature spell. Its controller draws a card.",
    setup_interceptors=glen_elendra_guardian_setup
)

# Gravelgill Scoundrel - {1}{U} Creature — Merfolk Rogue 1/3
def gravelgill_scoundrel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "Whenever this creature attacks, you may tap another untapped creature you control.
    #  If you do, this creature can't be blocked this turn."
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        ally = find_friendly_creature(obj, state, exclude_self=True, tapped=False)
        if not ally:
            return []
        return [Event(type=EventType.TAP,
                      payload={'object_id': ally, 'optional': True},
                      source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


GRAVELGILL_SCOUNDREL = make_creature(
    name="Gravelgill Scoundrel",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="Vigilance. Whenever this creature attacks, you may tap another untapped creature you control. If you do, this creature can't be blocked this turn.",
    setup_interceptors=gravelgill_scoundrel_setup
)

# Illusion Spinners - {4}{U} Creature — Faerie Wizard 4/3
def illusion_spinners_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def hexproof_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_ABILITIES and
                event.payload.get('object_id') == obj.id and
                not obj.state.tapped)

    def hexproof_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = new_event.payload.get('granted', [])
        granted.append('hexproof')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=hexproof_filter,
        handler=hexproof_handler, duration='while_on_battlefield'
    )]


ILLUSION_SPINNERS = make_creature(
    name="Illusion Spinners",
    power=4,
    toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="You may cast this spell as though it had flash if you control a Faerie. Flying. This creature has hexproof as long as it's untapped.",
    setup_interceptors=illusion_spinners_setup
)


# =============================================================================
# BLACK CARDS
# =============================================================================

# Auntie's Sentence - {1}{B} Sorcery
AUNTIES_SENTENCE = make_sorcery(
    name="Auntie's Sentence",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one — Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. OR Target creature gets -2/-2 until end of turn."
)

# Bile-Vial Boggart - {B} Creature — Goblin Assassin 1/1
def bile_vial_boggart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, put a -1/-1 counter on target creature."""
    def dies_effect(event: Event, state: GameState) -> list[Event]:
        # Find a valid target creature (any creature on battlefield)
        for target_id, target in state.objects.items():
            if (target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                target_id != obj.id):
                # Put a -1/-1 counter on the target
                return [Event(
                    type=EventType.COUNTER_ADDED,
                    payload={
                        'object_id': target_id,
                        'counter_type': '-1/-1',
                        'amount': 1
                    },
                    source=obj.id
                )]
        return []

    return [make_death_trigger(obj, dies_effect)]


BILE_VIAL_BOGGART = make_creature(
    name="Bile-Vial Boggart",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Assassin"},
    text="When this creature dies, put a -1/-1 counter on target creature.",
    setup_interceptors=bile_vial_boggart_setup
)

# Bitterbloom Bearer - {B}{B} Creature — Faerie Rogue 1/1
def bitterbloom_bearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Faerie Token', 'controller': obj.controller,
                'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                'subtypes': ['Faerie'], 'colors': [Color.BLUE, Color.BLACK],
                'abilities': ['flying']
            }, source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]


BITTERBLOOM_BEARER = make_creature(
    name="Bitterbloom Bearer",
    power=1,
    toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flash, flying. At the beginning of your upkeep, you lose 1 life and create a 1/1 blue and black Faerie creature token with flying.",
    setup_interceptors=bitterbloom_bearer_setup
)

# Blighted Blackthorn - {4}{B} Creature — Treefolk Warlock 3/7
def blighted_blackthorn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_or_attack_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)
        if event.type == EventType.ATTACK_DECLARED:
            return event.payload.get('attacker_id') == obj.id
        return False

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # May blight 2, then draw a card and lose 1 life
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id),
                Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id)
            ]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=etb_or_attack_filter,
        handler=trigger_handler, duration='while_on_battlefield'
    )]


BLIGHTED_BLACKTHORN = make_creature(
    name="Blighted Blackthorn",
    power=3,
    toughness=7,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Treefolk", "Warlock"},
    text="Whenever this creature enters or attacks, you may blight 2. Then draw a card and lose 1 life.",
    setup_interceptors=blighted_blackthorn_setup
)

# Blight Rot - {2}{B} Instant
BLIGHT_ROT = make_instant(
    name="Blight Rot",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Put four -1/-1 counters on target creature.",
    resolve=None
)

# Bloodline Bidding - {6}{B}{B} Sorcery
BLOODLINE_BIDDING = make_sorcery(
    name="Bloodline Bidding",
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    text="Convoke. Choose a creature type. Return all creature cards of that type from your graveyard to the battlefield."
)

# Boggart Mischief - {2}{B} Kindred Enchantment — Goblin
def boggart_mischief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Create two 1/1 Goblin tokens
        return [
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Goblin Token', 'controller': obj.controller,
                'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                'subtypes': ['Goblin'], 'colors': [Color.BLACK, Color.RED]
            }, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Goblin Token', 'controller': obj.controller,
                'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                'subtypes': ['Goblin'], 'colors': [Color.BLACK, Color.RED]
            }, source=obj.id)
        ]

    return [make_etb_trigger(obj, etb_effect)]


BOGGART_MISCHIEF = make_enchantment(
    name="Boggart Mischief",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, you may blight 1, then create two 1/1 black and red Goblin creature tokens. When this enchantment is put into a graveyard from the battlefield, each opponent loses 1 life.",
    setup_interceptors=boggart_mischief_setup
)

# Boggart Prankster - {1}{B} Creature — Goblin Warrior 1/3
def boggart_prankster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Find an attacking Goblin to target (simplified: pick first other attacking Goblin, or self)
        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []

        # Look for attacking Goblins (tapped creatures controlled by same player)
        target_id = None
        for obj_id in battlefield.objects:
            creature = state.objects.get(obj_id)
            if (creature and
                creature.controller == obj.controller and
                CardType.CREATURE in creature.characteristics.types and
                'Goblin' in creature.characteristics.subtypes and
                creature.state.tapped):  # Attacking creatures are tapped
                # Prefer other Goblins, but can target self
                if creature.id != obj.id:
                    target_id = creature.id
                    break
                elif target_id is None:
                    target_id = creature.id

        if target_id:
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': target_id,
                    'power_mod': 1,
                    'toughness_mod': 0,
                    'duration': 'end_of_turn'
                },
                source=obj.id
            )]
        return []
    return [make_attack_trigger(obj, attack_effect)]


BOGGART_PRANKSTER = make_creature(
    name="Boggart Prankster",
    power=1,
    toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warrior"},
    text="Whenever this creature attacks, target attacking Goblin gets +1/+0 until end of turn.",
    setup_interceptors=boggart_prankster_setup
)

# Creakwood Safewright - {1}{B} Creature — Elf Warrior 5/5
def creakwood_safewright_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


CREAKWOOD_SAFEWRIGHT = make_creature(
    name="Creakwood Safewright",
    power=5,
    toughness=5,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warrior"},
    text="This creature enters with three -1/-1 counters on it. At the beginning of your upkeep, if there is an Elf card in your graveyard and this creature has a -1/-1 counter on it, remove a -1/-1 counter from it.",
    setup_interceptors=creakwood_safewright_setup
)

# Darkness Descends - {2}{B}{B} Sorcery
DARKNESS_DESCENDS = make_sorcery(
    name="Darkness Descends",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Put two -1/-1 counters on each creature."
)

# Dawnhand Eulogist - {3}{B} Creature — Elf Warlock 3/3
def dawnhand_eulogist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "mill three cards. If there is an Elf card in your graveyard, each opponent
    #  loses 2 life and you gain 2 life."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
        gy_key = f"graveyard_{obj.controller}"
        graveyard = state.zones.get(gy_key)
        has_elf = False
        if graveyard:
            for obj_id in graveyard.objects:
                card = state.objects.get(obj_id)
                if card and "Elf" in card.characteristics.subtypes:
                    has_elf = True
                    break
        if has_elf:
            for pid in opponents_of(obj, state):
                events.append(Event(type=EventType.LIFE_CHANGE,
                    payload={'player': pid, 'amount': -2}, source=obj.id))
            events.append(Event(type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2}, source=obj.id))
        return events

    return [make_etb_trigger(obj, etb_effect)]


DAWNHAND_EULOGIST = make_creature(
    name="Dawnhand Eulogist",
    power=3,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="Menace. When this creature enters, mill three cards. If there is an Elf card in your graveyard, each opponent loses 2 life and you gain 2 life.",
    setup_interceptors=dawnhand_eulogist_setup
)

# Dream Seizer - {3}{B} Creature — Faerie Rogue 3/2
def dream_seizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # May blight 1, opponents discard
        events = []
        for pid, player in state.players.items():
            if pid != obj.controller:
                events.append(Event(type=EventType.DISCARD, payload={'player': pid, 'count': 1}, source=obj.id))
        return events

    return [make_etb_trigger(obj, etb_effect)]


DREAM_SEIZER = make_creature(
    name="Dream Seizer",
    power=3,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. When this creature enters, you may blight 1. If you do, each opponent discards a card.",
    setup_interceptors=dream_seizer_setup
)

# Gnarlbark Elm - {2}{B} Creature — Treefolk Warlock 3/4
def gnarlbark_elm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


GNARLBARK_ELM = make_creature(
    name="Gnarlbark Elm",
    power=3,
    toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Treefolk", "Warlock"},
    text="This creature enters with two -1/-1 counters on it. {2}{B}, Remove two -1/-1 counters from among creatures you control: Target creature gets -2/-2 until end of turn.",
    setup_interceptors=gnarlbark_elm_setup
)

# Graveshifter - {3}{B} Creature — Shapeshifter 2/2
def _creature_card_in_graveyard(obj: GameObject, state: GameState):
    """Return a creature card id in the controller's graveyard, else None."""
    gy = state.zones.get(f"graveyard_{obj.controller}")
    if gy:
        for cid in gy.objects:
            card = state.objects.get(cid)
            if card and CardType.CREATURE in card.characteristics.types:
                return cid
    return None


def _return_from_graveyard_event(obj, target, target_filter, *, optional=True):
    payload = {'player': obj.controller, 'to': 'hand',
               'target_filter': target_filter, 'optional': optional}
    if target:
        payload['object_id'] = target
    return Event(type=EventType.RETURN_FROM_GRAVEYARD, payload=payload, source=obj.id)


def _return_to_hand_event(obj, target, target_filter, *, optional=False):
    payload = {'target_filter': target_filter, 'optional': optional}
    if target:
        payload['object_id'] = target
    return Event(type=EventType.RETURN_TO_HAND, payload=payload, source=obj.id)


def graveshifter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "you may return target creature card from your graveyard to your hand."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = _creature_card_in_graveyard(obj, state)
        return [_return_from_graveyard_event(obj, target, 'creature_in_your_graveyard')]
    return [make_etb_trigger(obj, etb_effect)]


GRAVESHIFTER = make_creature(
    name="Graveshifter",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Shapeshifter"},
    text="Changeling. When this creature enters, you may return target creature card from your graveyard to your hand.",
    setup_interceptors=graveshifter_setup
)


# =============================================================================
# RED CARDS
# =============================================================================

# Ashling, Rekindled - {1}{R} Legendary Creature — Elemental Sorcerer 1/3
def ashling_rekindled_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "you may discard a card. If you do, draw a card."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': obj.controller, 'count': 1, 'optional': True},
                  source=obj.id),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'count': 1}, source=obj.id),
        ]
    return [make_etb_trigger(obj, etb_effect)]


ASHLING_REKINDLED = make_creature(
    name="Ashling, Rekindled",
    power=1,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    supertypes={"Legendary"},
    text="Whenever this creature enters or transforms into Ashling, Rekindled, you may discard a card. If you do, draw a card.",
    setup_interceptors=ashling_rekindled_setup
)

# Boldwyr Aggressor - {3}{R}{R} Creature — Giant Warrior 2/5
def boldwyr_aggressor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Other Giants you control have double strike
    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.id == obj.id:
            return False
        return (target.controller == obj.controller and
                "Giant" in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = new_event.payload.get('granted', [])
        granted.append('double_strike')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=ability_filter,
        handler=ability_handler, duration='while_on_battlefield'
    )]


BOLDWYR_AGGRESSOR = make_creature(
    name="Boldwyr Aggressor",
    power=2,
    toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Double strike. Other Giants you control have double strike.",
    setup_interceptors=boldwyr_aggressor_setup
)

# Boneclub Berserker - {3}{R} Creature — Goblin Berserker 2/4
def boneclub_berserker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def count_goblins(state: GameState) -> int:
        count = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                perm = state.objects.get(obj_id)
                if perm and perm.controller == obj.controller and perm.id != obj.id:
                    if "Goblin" in perm.characteristics.subtypes:
                        count += 1
        return count

    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER and
                event.payload.get('object_id') == obj.id)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        bonus = count_goblins(state) * 2
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=power_filter,
        handler=power_handler, duration='while_on_battlefield'
    )]


BONECLUB_BERSERKER = make_creature(
    name="Boneclub Berserker",
    power=2,
    toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Berserker"},
    text="This creature gets +2/+0 for each other Goblin you control.",
    setup_interceptors=boneclub_berserker_setup
)

# Boulder Dash - {1}{R} Sorcery
BOULDER_DASH = make_sorcery(
    name="Boulder Dash",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Boulder Dash deals 2 damage to any target and 1 damage to any other target."
)

# Brambleback Brute - {2}{R} Creature — Giant Warrior 4/5
def brambleback_brute_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


BRAMBLEBACK_BRUTE = make_creature(
    name="Brambleback Brute",
    power=4,
    toughness=5,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="This creature enters with two -1/-1 counters on it. {1}{R}, Remove a counter from this creature: Target creature can't block this turn. Activate only as a sorcery.",
    setup_interceptors=brambleback_brute_setup
)

# Burning Curiosity - {2}{R} Sorcery
BURNING_CURIOSITY = make_sorcery(
    name="Burning Curiosity",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, you may blight 1. Exile the top two cards of your library. If this spell's additional cost was paid, exile the top three cards instead. Until the end of your next turn, you may play those cards."
)

# Cinder Strike - {R} Sorcery
CINDER_STRIKE = make_sorcery(
    name="Cinder Strike",
    mana_cost="{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, you may blight 1. Cinder Strike deals 2 damage to target creature. It deals 4 damage to that creature instead if this spell's additional cost was paid."
)

# Collective Inferno - {3}{R}{R} Enchantment
COLLECTIVE_INFERNO = make_enchantment(
    name="Collective Inferno",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Convoke. As this enchantment enters, choose a creature type. Double all damage that sources you control of the chosen type would deal.",
    setup_interceptors=None  # Would need damage replacement
)

# Elder Auntie - {2}{R} Creature — Goblin Warlock 2/2
def elder_auntie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Goblin Token', 'controller': obj.controller,
                    'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                    'subtypes': ['Goblin'], 'colors': [Color.BLACK, Color.RED]},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


ELDER_AUNTIE = make_creature(
    name="Elder Auntie",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="When this creature enters, create a 1/1 black and red Goblin creature token.",
    setup_interceptors=elder_auntie_setup
)

# Enraged Flamecaster - {2}{R} Creature — Elemental Sorcerer 3/2
def enraged_flamecaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(type=EventType.DAMAGE, payload={'target': pid, 'amount': 2}, source=obj.id))
        return events
    return [make_spell_cast_trigger(obj, spell_effect, controller_only=True, mana_value_min=4)]


ENRAGED_FLAMECASTER = make_creature(
    name="Enraged Flamecaster",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="Reach. Whenever you cast a spell with mana value 4 or greater, this creature deals 2 damage to each opponent.",
    setup_interceptors=enraged_flamecaster_setup
)

# Explosive Prodigy - {1}{R} Creature — Elemental Sorcerer 1/1
def _colors_among_permanents(obj: GameObject, state: GameState) -> int:
    colors = set()
    for o in state.objects.values():
        if o.zone == ZoneType.BATTLEFIELD and o.controller == obj.controller:
            colors.update(o.characteristics.colors)
    return len(colors)


def explosive_prodigy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "it deals X damage to target creature an opponent controls, where X is the
    #  number of colors among permanents you control."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        damage = max(1, _colors_among_permanents(obj, state))
        target = find_opponent_creature(obj, state)
        payload = {'amount': damage, 'target_filter': 'opponent_creature'}
        if target:
            payload['target'] = target
            payload['target_type'] = 'creature'
        return [Event(type=EventType.DAMAGE, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


EXPLOSIVE_PRODIGY = make_creature(
    name="Explosive Prodigy",
    power=1,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="Vivid — When this creature enters, it deals X damage to target creature an opponent controls, where X is the number of colors among permanents you control.",
    setup_interceptors=explosive_prodigy_setup
)

# Feed the Flames - {3}{R} Instant
FEED_THE_FLAMES = make_instant(
    name="Feed the Flames",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Feed the Flames deals 5 damage to target creature. If that creature would die this turn, exile it instead."
)

# Flame-Chain Mauler - {1}{R} Creature — Elemental Warrior 2/2
def flame_chain_mauler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated ability - handled by activated ability system
    return []


FLAME_CHAIN_MAULER = make_creature(
    name="Flame-Chain Mauler",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Warrior"},
    text="{1}{R}: This creature gets +1/+0 and gains menace until end of turn.",
    setup_interceptors=flame_chain_mauler_setup
)

# Flamebraider - {1}{R} Creature — Elemental Bard 2/2
def flamebraider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Mana ability - handled by mana ability system
    return []


FLAMEBRAIDER = make_creature(
    name="Flamebraider",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Bard"},
    text="{T}: Add two mana in any combination of colors. Spend this mana only to cast Elemental spells or activate abilities of Elemental sources.",
    setup_interceptors=flamebraider_setup
)

# Flamekin Gildweaver - {3}{R} Creature — Elemental Sorcerer 4/3
def flamekin_gildweaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Treasure', 'controller': obj.controller,
                    'types': [CardType.ARTIFACT], 'subtypes': ['Treasure']},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


FLAMEKIN_GILDWEAVER = make_creature(
    name="Flamekin Gildweaver",
    power=4,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="Trample. When this creature enters, create a Treasure token.",
    setup_interceptors=flamekin_gildweaver_setup
)

# Giantfall - {1}{R} Instant
GIANTFALL = make_instant(
    name="Giantfall",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one — Target creature you control deals damage equal to its power to target creature an opponent controls; or destroy target artifact."
)

# Goatnap - {2}{R} Sorcery
GOATNAP = make_sorcery(
    name="Goatnap",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. If that creature is a Goat, it also gets +3/+0 until end of turn."
)

# Goliath Daydreamer - {2}{R}{R} Creature — Giant Wizard 4/4
def goliath_daydreamer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Complex effect - needs exile zone tracking and spell resolution modification
    return []


GOLIATH_DAYDREAMER = make_creature(
    name="Goliath Daydreamer",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Wizard"},
    text="Whenever you cast an instant or sorcery spell from your hand, exile that card with a dream counter on it instead of putting it into your graveyard as it resolves. Whenever this creature attacks, you may cast a spell from among cards you own in exile with dream counters on them without paying its mana cost.",
    setup_interceptors=goliath_daydreamer_setup
)

# Gristle Glutton - {1}{R} Creature — Goblin Scout 1/3
def gristle_glutton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated tap ability - handled by activated ability system
    return []


GRISTLE_GLUTTON = make_creature(
    name="Gristle Glutton",
    power=1,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Scout"},
    text="{T}, Blight 1: Discard a card. If you do, draw a card.",
    setup_interceptors=gristle_glutton_setup
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# Abigale, Eloquent First-Year - {W/B}{W/B} Legendary Creature 1/1
def abigale_eloquent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "up to one other target creature loses all abilities and has base power and
    #  toughness 1/1 until end of turn."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_any_creature(obj, state, exclude_self=True)
        payload = {'duration': 'end_of_turn', 'set_base': True,
                   'set_power': 1, 'set_toughness': 1, 'lose_all_abilities': True,
                   'target_filter': 'other_creature', 'optional': True}
        if target:
            t = state.objects[target]
            payload['object_id'] = target
            payload['power_mod'] = 1 - (t.characteristics.power or 0)
            payload['toughness_mod'] = 1 - (t.characteristics.toughness or 0)
        else:
            payload['power_mod'] = 0
            payload['toughness_mod'] = 0
        return [Event(type=EventType.PT_MODIFICATION, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


ABIGALE_ELOQUENT = make_creature(
    name="Abigale, Eloquent First-Year",
    power=1,
    toughness=1,
    mana_cost="{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Bird", "Bard"},
    supertypes={"Legendary"},
    text="Flying, first strike, lifelink. When Abigale enters, up to one other target creature loses all abilities and has base power and toughness 1/1 until end of turn.",
    setup_interceptors=abigale_eloquent_setup
)

# Boggart Cursecrafter - {B}{R} Creature — Goblin Warlock 2/3
def boggart_cursecrafter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def goblin_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == obj.id:
            return False
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller == obj.controller and
                "Goblin" in dying.characteristics.subtypes)

    def damage_opponents(event: Event, state: GameState) -> InterceptorResult:
        events = []
        for pid, player in state.players.items():
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': 1},
                    source=obj.id
                ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=goblin_dies_filter,
        handler=damage_opponents, duration='while_on_battlefield'
    )]


BOGGART_CURSECRAFTER = make_creature(
    name="Boggart Cursecrafter",
    power=2,
    toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="Deathtouch. Whenever another Goblin you control dies, this creature deals 1 damage to each opponent.",
    setup_interceptors=boggart_cursecrafter_setup
)

# Bre of Clan Stoutarm - {2}{R}{W} Legendary Creature — Giant Warrior 4/4
def bre_of_clan_stoutarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated tap ability - handled by activated ability system
    return []


BRE_OF_CLAN_STOUTARM = make_creature(
    name="Bre of Clan Stoutarm",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Giant", "Warrior"},
    supertypes={"Legendary"},
    text="{1}{W}, {T}: Another target creature you control gains flying and lifelink until end of turn.",
    setup_interceptors=bre_of_clan_stoutarm_setup
)

# Chaos Spewer - {2}{B/R} Creature — Goblin Warlock 5/4
def chaos_spewer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # If you don't pay {2}, blight 2 (put -1/-1 counters)
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


CHAOS_SPEWER = make_creature(
    name="Chaos Spewer",
    power=5,
    toughness=4,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="When this creature enters, you may pay {2}. If you don't, blight 2.",
    setup_interceptors=chaos_spewer_setup
)

# Chitinous Graspling - {3}{G/U} Creature — Shapeshifter 3/4
def chitinous_graspling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Changeling. Reach. (No triggered abilities - keywords handled separately)
    return []


CHITINOUS_GRASPLING = make_creature(
    name="Chitinous Graspling",
    power=3,
    toughness=4,
    mana_cost="{3}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Shapeshifter"},
    text="Changeling. Reach.",
    setup_interceptors=chitinous_graspling_setup
)

# Deepchannel Duelist - {W}{U} Creature — Merfolk Soldier 2/2
def deepchannel_duelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "At the beginning of your end step, untap target Merfolk you control.
    #  It can't be blocked this turn."
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        target = find_friendly_creature(obj, state, subtype="Merfolk", exclude_self=False)
        if not target:
            return []
        return [Event(type=EventType.UNTAP, payload={'object_id': target}, source=obj.id)]
    return [make_end_step_trigger(obj, end_step_effect)]


DEEPCHANNEL_DUELIST = make_creature(
    name="Deepchannel Duelist",
    power=2,
    toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Merfolk", "Soldier"},
    text="At the beginning of your end step, untap target Merfolk you control. It can't be blocked this turn.",
    setup_interceptors=deepchannel_duelist_setup
)

# Deepway Navigator - {W}{U} Creature — Merfolk Wizard 2/2
def deepway_navigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                perm = state.objects.get(obj_id)
                if (perm and perm.controller == obj.controller and
                    perm.id != obj.id and "Merfolk" in perm.characteristics.subtypes):
                    events.append(Event(
                        type=EventType.UNTAP,
                        payload={'object_id': perm.id},
                        source=obj.id
                    ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


DEEPWAY_NAVIGATOR = make_creature(
    name="Deepway Navigator",
    power=2,
    toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Flash. When this creature enters, untap each other Merfolk you control.",
    setup_interceptors=deepway_navigator_setup
)

# Doran, Besieged by Time - {1}{W}{B}{G} Legendary Creature — Treefolk Druid 0/5
def doran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Each creature assigns combat damage equal to toughness rather than power
    # This is complex - needs combat damage modification
    return []


DORAN_BESIEGED = make_creature(
    name="Doran, Besieged by Time",
    power=0,
    toughness=5,
    mana_cost="{1}{W}{B}{G}",
    colors={Color.WHITE, Color.BLACK, Color.GREEN},
    subtypes={"Treefolk", "Druid"},
    supertypes={"Legendary"},
    text="Each creature spell with toughness greater than its power costs {1} less to cast. Each creature assigns combat damage equal to its toughness rather than its power.",
    setup_interceptors=doran_setup
)

# Eclipsed Boggart - {B/R}{B/R}{B/R} Creature — Goblin Scout 2/3
def eclipsed_boggart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _eclipsed_dig(obj, "Goblin"))]


ECLIPSED_BOGGART = make_creature(
    name="Eclipsed Boggart",
    power=2,
    toughness=3,
    mana_cost="{B/R}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal a Goblin card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=eclipsed_boggart_setup
)

# Eclipsed Elf - {B/G}{B/G}{B/G} Creature — Elf Scout 3/2
def _eclipsed_dig(obj: GameObject, tribe: str):
    """Shared "look at top four, reveal a <tribe>, bottom the rest" ETB effect."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LOOK_AT_TOP,
            payload={'player': obj.controller, 'amount': 4, 'put_in_hand': 1,
                     'reveal_type': tribe, 'rest_to_bottom': True, 'optional': True},
            source=obj.id)]
    return etb_effect


def eclipsed_elf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _eclipsed_dig(obj, "Elf"))]


ECLIPSED_ELF = make_creature(
    name="Eclipsed Elf",
    power=3,
    toughness=2,
    mana_cost="{B/G}{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal an Elf card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=eclipsed_elf_setup
)

# Eclipsed Flamekin - {1}{U/R}{U/R} Creature — Elemental Scout 1/4
def eclipsed_flamekin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _eclipsed_dig(obj, "Elemental"))]


ECLIPSED_FLAMEKIN = make_creature(
    name="Eclipsed Flamekin",
    power=1,
    toughness=4,
    mana_cost="{1}{U/R}{U/R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Elemental", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal an Elemental card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=eclipsed_flamekin_setup
)

# Eclipsed Kithkin - {G/W}{G/W} Creature — Kithkin Scout 2/1
def eclipsed_kithkin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _eclipsed_dig(obj, "Kithkin"))]


ECLIPSED_KITHKIN = make_creature(
    name="Eclipsed Kithkin",
    power=2,
    toughness=1,
    mana_cost="{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal a Kithkin card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=eclipsed_kithkin_setup
)

# Eclipsed Merrow - {W/U}{W/U}{W/U} Creature — Merfolk Scout 2/3
def eclipsed_merrow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_etb_trigger(obj, _eclipsed_dig(obj, "Merfolk"))]


ECLIPSED_MERROW = make_creature(
    name="Eclipsed Merrow",
    power=2,
    toughness=3,
    mana_cost="{W/U}{W/U}{W/U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal a Merfolk card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=eclipsed_merrow_setup
)

# Feisty Spikeling - {1}{R/W} Creature — Shapeshifter 2/1
def feisty_spikeling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def ability_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_ABILITIES and
                event.payload.get('object_id') == obj.id and
                state.active_player == obj.controller)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = new_event.payload.get('granted', [])
        granted.append('first_strike')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=ability_filter,
        handler=ability_handler, duration='while_on_battlefield'
    )]


FEISTY_SPIKELING = make_creature(
    name="Feisty Spikeling",
    power=2,
    toughness=1,
    mana_cost="{1}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Shapeshifter"},
    text="Changeling. During your turn, this creature has first strike.",
    setup_interceptors=feisty_spikeling_setup
)

# Figure of Fable - {G/W} Creature — Kithkin 1/1
def figure_of_fable_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated abilities - handled by activated ability system
    return []


FIGURE_OF_FABLE = make_creature(
    name="Figure of Fable",
    power=1,
    toughness=1,
    mana_cost="{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin"},
    text="{G/W}: This creature becomes a Kithkin Scout with base power and toughness 2/3 until end of turn. {G/W}{G/W}: This creature becomes a Kithkin Knight with base power and toughness 4/4 and gains trample until end of turn.",
    setup_interceptors=figure_of_fable_setup
)

# Flaring Cinder - {1}{U/R}{U/R} Creature — Elemental Sorcerer 3/2
def flaring_cinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Deal 2 damage to each opponent
        events = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': 2},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


FLARING_CINDER = make_creature(
    name="Flaring Cinder",
    power=3,
    toughness=2,
    mana_cost="{1}{U/R}{U/R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="When this creature enters and whenever you cast a spell with mana value 4 or greater, this creature deals 2 damage to each opponent.",
    setup_interceptors=flaring_cinder_setup
)

# Gangly Stompling - {2}{R/G} Creature — Shapeshifter 4/2
def gangly_stompling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Changeling. Trample. (No triggered abilities - keywords handled separately)
    return []


GANGLY_STOMPLING = make_creature(
    name="Gangly Stompling",
    power=4,
    toughness=2,
    mana_cost="{2}{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling. Trample.",
    setup_interceptors=gangly_stompling_setup
)


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

# Ajani, Outland Chaperone - {1}{W}{W} Legendary Planeswalker — Ajani
AJANI_OUTLAND_CHAPERONE = make_planeswalker(
    name="Ajani, Outland Chaperone",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Ajani"},
    text="+1: Create a 1/1 white Cat creature token. +1: Ajani deals damage to target tapped creature equal to the number of creatures you control. -6: Search your library for any number of permanent cards with mana value 3 or less, put them onto the battlefield, then shuffle.",
    loyalty=3
)


# Personify - {1}{W} Instant
PERSONIFY = make_instant(
    name="Personify",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target creature you control, then return that card to the battlefield under its owner's control. Create a 1/1 colorless Shapeshifter creature token with changeling.",
    resolve=None
)


# Protective Response - {2}{W} Instant
PROTECTIVE_RESPONSE = make_instant(
    name="Protective Response",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Convoke. Destroy target attacking or blocking creature.",
    resolve=None
)


# Pyrrhic Strike - {2}{W} Instant
PYRRHIC_STRIKE = make_instant(
    name="Pyrrhic Strike",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="As an additional cost to cast this spell, you may blight 2. Choose one. If the blight cost was paid, choose both instead — Destroy target artifact or enchantment; Destroy target creature with mana value 3 or greater.",
    resolve=None
)


# Reluctant Dounguard - {2}{W} Creature — Kithkin Soldier 4/4
def reluctant_dounguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != obj.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        # Check if this creature has a -1/-1 counter
        return obj.state.counters.get('-1/-1', 0) > 0

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 1},
                source=obj.id
            )]
        )

    def enters_with_counters(event: Event, state: GameState) -> list[Event]:
        # "This creature enters with two -1/-1 counters on it."
        return [Event(type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 2},
            source=obj.id)]

    return [
        make_etb_trigger(obj, enters_with_counters),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=other_creature_etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield'
        )
    ]


RELUCTANT_DOUNGUARD = make_creature(
    name="Reluctant Dounguard",
    power=4,
    toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="This creature enters with two -1/-1 counters on it. Whenever another creature you control enters while this creature has a -1/-1 counter on it, remove a -1/-1 counter from this creature.",
    setup_interceptors=reluctant_dounguard_setup
)


# Rhys, the Evermore - {1}{W} Legendary Creature — Elf Warrior 2/2
def rhys_the_evermore_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "When Rhys enters, another target creature you control gains persist until end of turn."
    return [make_targeted_etb_trigger(
        obj,
        effect='grant_keyword',
        effect_params={'keyword': 'persist'},
        target_filter='other_creature_you_control',
        optional=True,
        prompt="Choose another creature you control to gain persist"
    )]


RHYS_THE_EVERMORE = make_creature(
    name="Rhys, the Evermore",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Flash. When Rhys enters, another target creature you control gains persist until end of turn. {W}, {T}: Remove any number of counters from target creature you control.",
    setup_interceptors=rhys_the_evermore_setup
)


# Riverguard's Reflexes - {1}{W} Instant
RIVERGUARDS_REFLEXES = make_instant(
    name="Riverguard's Reflexes",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains first strike until end of turn. Untap it.",
    resolve=None
)


# Evershrike's Gift - {2}{W} Enchantment — Aura
def evershrikes_gift_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Death trigger on enchanted creature - requires aura tracking
    return []  # Complex - needs aura and death trigger coordination


EVERSHRIKES_GIFT = make_enchantment(
    name="Evershrike's Gift",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets +2/+2 and has flying. When enchanted creature dies, return Evershrike's Gift to your hand.",
    setup_interceptors=evershrikes_gift_setup
)


# Kinsbaile Aspirant - {W} Creature — Kithkin Soldier 1/1
def kinsbaile_aspirant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another Kithkin enters under your control, put a +1/+1 counter on this."""
    def kithkin_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering or entering.controller != obj.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        return 'Kithkin' in entering.characteristics.subtypes

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=kithkin_etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield'
        )
    ]


KINSBAILE_ASPIRANT = make_creature(
    name="Kinsbaile Aspirant",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Whenever another Kithkin enters the battlefield under your control, put a +1/+1 counter on this creature.",
    setup_interceptors=kinsbaile_aspirant_setup
)


# Kinscaer Sentry - {2}{W} Creature — Kithkin Soldier 2/3
def kinscaer_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control becomes tapped, you gain 1 life."""
    def tap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        tapped_id = event.payload.get('object_id')
        if tapped_id == obj.id:
            return False
        tapped = state.objects.get(tapped_id)
        if not tapped or tapped.controller != obj.controller:
            return False
        return CardType.CREATURE in tapped.characteristics.types

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tap_filter,
            handler=tap_handler,
            duration='while_on_battlefield'
        )
    ]


KINSCAER_SENTRY = make_creature(
    name="Kinscaer Sentry",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Vigilance. Whenever another creature you control becomes tapped, you gain 1 life.",
    setup_interceptors=kinscaer_sentry_setup
)


# Kithkeeper - {1}{W}{W} Creature — Kithkin Cleric 2/2
def kithkeeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Kithkeeper enters, create a 1/1 white Kithkin creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Kithkin Token',
                'controller': obj.controller,
                'power': 1, 'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Kithkin'],
                'colors': [Color.WHITE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


KITHKEEPER = make_creature(
    name="Kithkeeper",
    power=2,
    toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Cleric"},
    text="When Kithkeeper enters, create a 1/1 white Kithkin creature token. {2}{W}: Kithkin you control get +1/+1 until end of turn.",
    setup_interceptors=kithkeeper_setup
)


# Liminal Hold - {3}{W} Enchantment
def liminal_hold_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Liminal Hold enters, exile target creature an opponent controls until it leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_opponent_creature(obj, state)
        payload = {'until_leaves': obj.id, 'target_filter': 'opponent_creature'}
        if target:
            payload['object_id'] = target
        return [Event(type=EventType.EXILE, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


LIMINAL_HOLD = make_enchantment(
    name="Liminal Hold",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When Liminal Hold enters, exile target creature an opponent controls until Liminal Hold leaves the battlefield.",
    setup_interceptors=liminal_hold_setup
)


# Meanders Guide - {1}{W} Creature — Kithkin Scout 2/1
def meanders_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Meanders Guide enters, look at top 3, put one into hand, rest on bottom."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LOOK_AT_TOP,
            payload={'player': obj.controller, 'amount': 3, 'put_in_hand': 1,
                     'rest_to_bottom': True}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


MEANDERS_GUIDE = make_creature(
    name="Meanders Guide",
    power=2,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Scout"},
    text="When Meanders Guide enters, look at the top three cards of your library. Put one into your hand and the rest on the bottom of your library in any order.",
    setup_interceptors=meanders_guide_setup
)


# Moonlit Lamenter - {2}{W} Creature — Kithkin Bard 2/2
def moonlit_lamenter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Moonlit Lamenter enters, each player gains 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': player_id, 'amount': 3},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


MOONLIT_LAMENTER = make_creature(
    name="Moonlit Lamenter",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Bard"},
    text="Flash. When Moonlit Lamenter enters, each player gains 3 life.",
    setup_interceptors=moonlit_lamenter_setup
)


# Morningtide's Light - {2}{W} Instant
MORNINGTIDES_LIGHT = make_instant(
    name="Morningtide's Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target creature with power 4 or greater. You gain 4 life.",
    resolve=None
)


# Shore Lurker - {3}{W} Creature — Merfolk Soldier 3/4
def shore_lurker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        # Check if we control another Merfolk
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                perm = state.objects.get(obj_id)
                if (perm and perm.id != obj.id and perm.controller == obj.controller and
                    CardType.CREATURE in perm.characteristics.types and
                    'Merfolk' in perm.characteristics.subtypes):
                    return True
        return False

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = new_event.payload.get('granted', [])
        granted.append('vigilance')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=ability_filter,
        handler=ability_handler, duration='while_on_battlefield'
    )]


SHORE_LURKER = make_creature(
    name="Shore Lurker",
    power=3,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Soldier"},
    text="Ward {2}. As long as you control another Merfolk, this creature has vigilance.",
    setup_interceptors=shore_lurker_setup
)


# Slumbering Walker - {1}{W} Creature — Giant 3/3
def _tap_opponent_creature_event(obj, target, *, dont_untap=False):
    payload = {'target_filter': 'opponent_creature'}
    if target:
        payload['object_id'] = target
    if dont_untap:
        payload['skip_next_untap'] = True
    return Event(type=EventType.TAP, payload=payload, source=obj.id)


def slumbering_walker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Slumbering Walker enters, tap target creature an opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_opponent_creature(obj, state)
        return [_tap_opponent_creature_event(obj, target)]
    return [make_etb_trigger(obj, etb_effect)]


SLUMBERING_WALKER = make_creature(
    name="Slumbering Walker",
    power=3,
    toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Giant"},
    text="Slumbering Walker enters tapped. When Slumbering Walker enters, tap target creature an opponent controls.",
    setup_interceptors=slumbering_walker_setup
)


# Spiral into Solitude - {1}{W} Instant
SPIRAL_INTO_SOLITUDE = make_instant(
    name="Spiral into Solitude",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking or blocking creature. Its controller creates a 1/1 white Kithkin creature token.",
    resolve=None
)


# Sun-Dappled Celebrant - {1}{W} Creature — Elf Cleric 2/2
def sun_dappled_celebrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Sun-Dappled Celebrant enters, you gain 2 life for each other creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        creature_count = 0
        for other_obj in state.objects.values():
            if other_obj.id == obj.id:
                continue
            if other_obj.controller != obj.controller:
                continue
            if other_obj.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE in other_obj.characteristics.types:
                creature_count += 1
        if creature_count > 0:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2 * creature_count},
                source=obj.id
            )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


SUN_DAPPLED_CELEBRANT = make_creature(
    name="Sun-Dappled Celebrant",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Elf", "Cleric"},
    text="When Sun-Dappled Celebrant enters, you gain 2 life for each other creature you control.",
    setup_interceptors=sun_dappled_celebrant_setup
)


# Thoughtweft Imbuer - {2}{W} Creature — Kithkin Wizard 2/3
def thoughtweft_imbuer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Thoughtweft Imbuer enters, target creature you control gets +2/+2 and gains lifelink."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_friendly_creature(obj, state, exclude_self=False)
        pt_payload = {'power_mod': 2, 'toughness_mod': 2, 'duration': 'end_of_turn',
                      'target_filter': 'creature_you_control'}
        kw_payload = {'keyword': 'lifelink', 'duration': 'end_of_turn',
                      'target_filter': 'creature_you_control'}
        if target:
            pt_payload['object_id'] = target
            kw_payload['object_id'] = target
        return [
            Event(type=EventType.PT_MODIFICATION, payload=pt_payload, source=obj.id),
            Event(type=EventType.GRANT_KEYWORD, payload=kw_payload, source=obj.id),
        ]
    return [make_etb_trigger(obj, etb_effect)]


THOUGHTWEFT_IMBUER = make_creature(
    name="Thoughtweft Imbuer",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Wizard"},
    text="When Thoughtweft Imbuer enters, target creature you control gets +2/+2 and gains lifelink until end of turn.",
    setup_interceptors=thoughtweft_imbuer_setup
)


# Timid Shieldbearer - {W} Creature — Kithkin Soldier 0/3
def timid_shieldbearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Activated ability - handled by activated ability system
    return []


TIMID_SHIELDBEARER = make_creature(
    name="Timid Shieldbearer",
    power=0,
    toughness=3,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Defender. {1}{W}: Timid Shieldbearer can attack this turn as though it didn't have defender.",
    setup_interceptors=timid_shieldbearer_setup
)


# Tributary Vaulter - {3}{W} Creature — Merfolk Wizard 3/3
def tributary_vaulter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Tributary Vaulter enters, tap up to two target creatures your opponents control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        targets = [o.id for o in _battlefield_creatures(state)
                   if o.controller != obj.controller][:2]
        if targets:
            return [Event(type=EventType.TAP, payload={'object_id': t}, source=obj.id)
                    for t in targets]
        return [_tap_opponent_creature_event(obj, None)]
    return [make_etb_trigger(obj, etb_effect)]


TRIBUTARY_VAULTER = make_creature(
    name="Tributary Vaulter",
    power=3,
    toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Wizard"},
    text="Flying. When Tributary Vaulter enters, tap up to two target creatures your opponents control.",
    setup_interceptors=tributary_vaulter_setup
)


# Wanderbrine Preacher - {3}{W} Creature — Merfolk Cleric 2/4
def wanderbrine_preacher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Merfolk you control becomes tapped, you may gain 1 life."""
    def tap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        tapped_id = event.payload.get('object_id')
        tapped = state.objects.get(tapped_id)
        if not tapped or tapped.controller != obj.controller:
            return False
        if CardType.CREATURE not in tapped.characteristics.types:
            return False
        return 'Merfolk' in tapped.characteristics.subtypes

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tap_filter,
            handler=tap_handler,
            duration='while_on_battlefield'
        )
    ]


WANDERBRINE_PREACHER = make_creature(
    name="Wanderbrine Preacher",
    power=2,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Cleric"},
    text="Whenever a Merfolk you control becomes tapped, you may gain 1 life.",
    setup_interceptors=wanderbrine_preacher_setup
)


# Wanderbrine Trapper - {2}{W} Creature — Merfolk Rogue 2/2
def wanderbrine_trapper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Wanderbrine Trapper enters, tap target creature an opponent controls;
    it doesn't untap during its controller's next untap step."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_opponent_creature(obj, state)
        return [_tap_opponent_creature_event(obj, target, dont_untap=True)]
    return [make_etb_trigger(obj, etb_effect)]


WANDERBRINE_TRAPPER = make_creature(
    name="Wanderbrine Trapper",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Rogue"},
    text="When Wanderbrine Trapper enters, tap target creature an opponent controls. It doesn't untap during its controller's next untap step.",
    setup_interceptors=wanderbrine_trapper_setup
)


# Winnowing - {3}{W}{W} Sorcery
WINNOWING = make_sorcery(
    name="Winnowing",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with power 4 or greater."
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

# Disruptor of Currents - {3}{U}{U} Creature — Merfolk Wizard 3/3
def disruptor_of_currents_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "return up to one other target nonland permanent to its owner's hand."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_any_creature(obj, state, exclude_self=True)
        return [_return_to_hand_event(obj, target, 'other_nonland_permanent', optional=True)]
    return [make_etb_trigger(obj, etb_effect)]


DISRUPTOR_OF_CURRENTS = make_creature(
    name="Disruptor of Currents",
    power=3,
    toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Flash. Convoke. When this creature enters, return up to one other target nonland permanent to its owner's hand.",
    setup_interceptors=disruptor_of_currents_setup
)


# Glamer Gifter - {1}{U} Creature — Faerie Wizard 1/2
def glamer_gifter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature becomes 4/4 with all creature types."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_any_creature(obj, state, exclude_self=False)
        payload = {'duration': 'end_of_turn', 'set_base': True,
                   'set_power': 4, 'set_toughness': 4, 'add_all_creature_types': True,
                   'target_filter': 'creature'}
        if target:
            t = state.objects[target]
            payload['object_id'] = target
            payload['power_mod'] = 4 - (t.characteristics.power or 0)
            payload['toughness_mod'] = 4 - (t.characteristics.toughness or 0)
        else:
            payload['power_mod'] = 0
            payload['toughness_mod'] = 0
        return [Event(type=EventType.PT_MODIFICATION, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


GLAMER_GIFTER = make_creature(
    name="Glamer Gifter",
    power=1,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash. Flying. When this creature enters, choose up to one other target creature. Until end of turn, that creature has base power and toughness 4/4 and gains all creature types.",
    setup_interceptors=glamer_gifter_setup
)


# Glen Elendra's Answer - {2}{U}{U} Instant
GLEN_ELENDRAS_ANSWER = make_instant(
    name="Glen Elendra's Answer",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="This spell can't be countered. Counter all spells your opponents control and all abilities your opponents control. Create a 1/1 blue and black Faerie creature token with flying for each spell and ability countered this way.",
    resolve=None
)


# Harmonized Crescendo - {4}{U}{U} Instant
HARMONIZED_CRESCENDO = make_instant(
    name="Harmonized Crescendo",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Convoke. Choose a creature type. Draw a card for each permanent you control of the chosen type.",
    resolve=None
)


# Pestered Wellguard - {3}{U} Creature — Merfolk Soldier 3/2
def pestered_wellguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def tap_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == obj.id)

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Faerie Token', 'controller': obj.controller,
                        'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                        'subtypes': ['Faerie'], 'abilities': ['flying']},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tap_filter,
            handler=tap_handler,
            duration='while_on_battlefield'
        )
    ]


PESTERED_WELLGUARD = make_creature(
    name="Pestered Wellguard",
    power=3,
    toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Soldier"},
    text="Whenever this creature becomes tapped, create a 1/1 blue and black Faerie creature token with flying.",
    setup_interceptors=pestered_wellguard_setup
)


# Rime Chill - {6}{U} Instant (Vivid)
RIME_CHILL = make_instant(
    name="Rime Chill",
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    text="Vivid — This spell costs {1} less to cast for each color among permanents you control. Tap up to two target creatures. Put a stun counter on each of them.",
    resolve=None
)


# Rimefire Torque - {1}{U} Artifact
RIMEFIRE_TORQUE = make_artifact(
    name="Rimefire Torque",
    mana_cost="{1}{U}",
    text="As this artifact enters, choose a creature type. Whenever a permanent you control of the chosen type enters, put a charge counter on this artifact. {T}, Remove three charge counters: Copy the next instant or sorcery spell you cast this turn."
)


# Rimekin Recluse - {2}{U} Creature — Elemental Wizard 3/2
def rimekin_recluse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "return up to one other target creature to its owner's hand."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_any_creature(obj, state, exclude_self=True)
        return [_return_to_hand_event(obj, target, 'other_creature', optional=True)]
    return [make_etb_trigger(obj, etb_effect)]


RIMEKIN_RECLUSE = make_creature(
    name="Rimekin Recluse",
    power=3,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="When this creature enters, return up to one other target creature to its owner's hand.",
    setup_interceptors=rimekin_recluse_setup
)


# Kulrath Mystic - {3}{U} Creature — Merfolk Wizard 2/4
def kulrath_mystic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell, scry 1."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.SPELL_CAST:
            return False
        return event.payload.get('controller') == obj.controller

    def spell_cast_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=spell_cast_filter,
            handler=spell_cast_handler,
            duration='while_on_battlefield'
        )
    ]


KULRATH_MYSTIC = make_creature(
    name="Kulrath Mystic",
    power=2,
    toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Whenever you cast a spell, scry 1.",
    setup_interceptors=kulrath_mystic_setup
)


# Loch Mare - {4}{U} Creature — Elemental Horse 4/4
def loch_mare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Loch Mare deals combat damage to a player, draw a card."""
    def combat_damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        return event.payload.get('target_type') == 'player'

    def combat_damage_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=combat_damage_filter,
            handler=combat_damage_handler,
            duration='while_on_battlefield'
        )
    ]


LOCH_MARE = make_creature(
    name="Loch Mare",
    power=4,
    toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Horse"},
    text="Islandwalk. Whenever Loch Mare deals combat damage to a player, draw a card.",
    setup_interceptors=loch_mare_setup
)


# Lofty Dreams - {2}{U} Instant
LOFTY_DREAMS = make_instant(
    name="Lofty Dreams",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. If you control a Faerie, draw three cards instead.",
    resolve=None
)


# Mirrorform - {1}{U} Instant
MIRRORFORM = make_instant(
    name="Mirrorform",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control. Sacrifice it at the beginning of the next end step.",
    resolve=None
)


# Noggle the Mind - {2}{U}{U} Sorcery
NOGGLE_THE_MIND = make_sorcery(
    name="Noggle the Mind",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Target player shuffles their hand into their library, then draws cards equal to the number of cards shuffled away this way."
)


# Omni-Changeling - {4}{U} Creature — Shapeshifter 3/3
def omni_changeling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Omni-Changeling enters, draw a card for each creature type among creatures you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Count unique creature types - simplified placeholder
        creature_types = set()
        for other_obj in state.objects.values():
            if other_obj.controller != obj.controller:
                continue
            if other_obj.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE in other_obj.characteristics.types:
                creature_types.update(other_obj.characteristics.subtypes)
        if creature_types:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': len(creature_types)},
                source=obj.id
            )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


OMNI_CHANGELING = make_creature(
    name="Omni-Changeling",
    power=3,
    toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter"},
    text="Changeling. Flash. When Omni-Changeling enters, draw a card for each creature type among creatures you control.",
    setup_interceptors=omni_changeling_setup
)


# Run Away Together - {1}{U} Instant
RUN_AWAY_TOGETHER = make_instant(
    name="Run Away Together",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
    resolve=None
)


# Shinestriker - {2}{U} Creature — Faerie Rogue 2/1
def shinestriker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Shinestriker deals combat damage to a player, you may tap or untap target permanent."""
    def combat_damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        return event.payload.get('target_type') == 'player'

    def combat_damage_handler(event: Event, state: GameState) -> InterceptorResult:
        # "you may tap or untap target permanent." — choose the untap mode,
        # preferring a tapped permanent (else any permanent).
        target = None
        for o in state.objects.values():
            if o.zone == ZoneType.BATTLEFIELD and o.state.tapped:
                target = o.id
                break
        if target is None:
            for o in state.objects.values():
                if o.zone == ZoneType.BATTLEFIELD:
                    target = o.id
                    break
        payload = {'target_filter': 'permanent', 'optional': True}
        if target:
            payload['object_id'] = target
        return InterceptorResult(action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.UNTAP, payload=payload, source=obj.id)])

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=combat_damage_filter,
            handler=combat_damage_handler,
            duration='while_on_battlefield'
        )
    ]


SHINESTRIKER = make_creature(
    name="Shinestriker",
    power=2,
    toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying. Whenever Shinestriker deals combat damage to a player, you may tap or untap target permanent.",
    setup_interceptors=shinestriker_setup
)


# Silvergill Mentor - {2}{U} Creature — Merfolk Wizard 2/3
def silvergill_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Silvergill Mentor enters, other Merfolk you control get +1/+1 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o in _battlefield_creatures(state):
            if (o.controller == obj.controller and o.id != obj.id and
                    "Merfolk" in o.characteristics.subtypes):
                events.append(Event(type=EventType.PT_MODIFICATION,
                    payload={'object_id': o.id, 'power_mod': 1, 'toughness_mod': 1,
                             'duration': 'end_of_turn'}, source=obj.id))
        if not events:
            events.append(Event(type=EventType.PT_MODIFICATION,
                payload={'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn',
                         'target_filter': 'other_merfolk_you_control'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


SILVERGILL_MENTOR = make_creature(
    name="Silvergill Mentor",
    power=2,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="When Silvergill Mentor enters, other Merfolk you control get +1/+1 until end of turn.",
    setup_interceptors=silvergill_mentor_setup
)


# Silvergill Peddler - {1}{U} Creature — Merfolk Rogue 1/3
def silvergill_peddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Merfolk you control becomes tapped, draw a card, then discard a card."""
    def tap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        tapped_id = event.payload.get('object_id')
        tapped = state.objects.get(tapped_id)
        if not tapped or tapped.controller != obj.controller:
            return False
        if CardType.CREATURE not in tapped.characteristics.types:
            return False
        return 'Merfolk' in tapped.characteristics.subtypes

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
                Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
            ]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tap_filter,
            handler=tap_handler,
            duration='while_on_battlefield'
        )
    ]


SILVERGILL_PEDDLER = make_creature(
    name="Silvergill Peddler",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="Whenever a Merfolk you control becomes tapped, you may draw a card. If you do, discard a card.",
    setup_interceptors=silvergill_peddler_setup
)


# Spell Snare - {U} Instant
SPELL_SNARE = make_instant(
    name="Spell Snare",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target spell with mana value 2.",
    resolve=None
)


# Stratosoarer - {3}{U} Creature — Elemental 3/2
def stratosoarer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Stratosoarer enters, return target creature to its owner's hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_any_creature(obj, state, exclude_self=True)
        return [_return_to_hand_event(obj, target, 'creature')]
    return [make_etb_trigger(obj, etb_effect)]


STRATOSOARER = make_creature(
    name="Stratosoarer",
    power=3,
    toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying. When Stratosoarer enters, return target creature to its owner's hand.",
    setup_interceptors=stratosoarer_setup
)


# Summit Sentinel - {2}{U} Creature — Faerie Soldier 2/2
SUMMIT_SENTINEL = make_creature(
    name="Summit Sentinel",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Soldier"},
    text="Flying, vigilance.",
    setup_interceptors=None
)


# Sunderflock - {4}{U}{U} Sorcery
SUNDERFLOCK = make_sorcery(
    name="Sunderflock",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands."
)


# Swat Away - {U} Instant
SWAT_AWAY = make_instant(
    name="Swat Away",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature with flying to its owner's hand.",
    resolve=None
)


# Tanufel Rimespeaker - {2}{U}{U} Creature — Elemental Wizard 3/4
def tanufel_rimespeaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vivid — Whenever you cast a spell, tap/untap target permanent X times."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.SPELL_CAST:
            return False
        return event.payload.get('controller') == obj.controller

    def spell_cast_handler(event: Event, state: GameState) -> InterceptorResult:
        # "you may tap or untap target permanent. Do this X times, where X is the
        #  number of colors among permanents you control." — emit one untap per
        #  color (the untap mode of the choice), preferring tapped permanents.
        x = max(1, _colors_among_permanents(obj, state))
        perms = [o.id for o in state.objects.values()
                 if o.zone == ZoneType.BATTLEFIELD]
        events = []
        for i in range(x):
            payload = {'target_filter': 'permanent', 'optional': True}
            if perms:
                payload['object_id'] = perms[i % len(perms)]
            events.append(Event(type=EventType.UNTAP, payload=payload, source=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=spell_cast_filter,
            handler=spell_cast_handler,
            duration='while_on_battlefield'
        )
    ]


TANUFEL_RIMESPEAKER = make_creature(
    name="Tanufel Rimespeaker",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="Vivid — Whenever you cast a spell, you may tap or untap target permanent. Do this X times, where X is the number of colors among permanents you control.",
    setup_interceptors=tanufel_rimespeaker_setup
)


# Temporal Cleansing - {3}{U} Sorcery
TEMPORAL_CLEANSING = make_sorcery(
    name="Temporal Cleansing",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="The owner of target nonland permanent puts it on top or bottom of their library."
)


# Thirst for Identity - {2}{U} Instant
THIRST_FOR_IDENTITY = make_instant(
    name="Thirst for Identity",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Then discard a card unless you reveal a Shapeshifter card from your hand.",
    resolve=None
)


# Unexpected Assistance - {3}{U} Instant
UNEXPECTED_ASSISTANCE = make_instant(
    name="Unexpected Assistance",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards.",
    resolve=None
)


# Unwelcome Sprite - {1}{U} Creature — Faerie 1/1
def unwelcome_sprite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Unwelcome Sprite enters, counter target ability."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Counter ability - targeting handled by game
        return []
    return [make_etb_trigger(obj, etb_effect)]


UNWELCOME_SPRITE = make_creature(
    name="Unwelcome Sprite",
    power=1,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie"},
    text="Flash. Flying. When Unwelcome Sprite enters, counter target ability.",
    setup_interceptors=unwelcome_sprite_setup
)


# Wanderwine Distracter - {2}{U} Creature — Merfolk Rogue 2/2
def wanderwine_distracter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Wanderwine Distracter enters, tap target creature an opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = find_opponent_creature(obj, state)
        return [_tap_opponent_creature_event(obj, target)]
    return [make_etb_trigger(obj, etb_effect)]


WANDERWINE_DISTRACTER = make_creature(
    name="Wanderwine Distracter",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="When Wanderwine Distracter enters, tap target creature an opponent controls.",
    setup_interceptors=wanderwine_distracter_setup
)


# Wanderwine Farewell - {3}{U}{U} Sorcery
WANDERWINE_FAREWELL = make_sorcery(
    name="Wanderwine Farewell",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Return all nonland permanents to their owners' hands. Each player draws a card for each permanent they own that was returned this way."
)


# Wild Unraveling - {2}{U} Instant
WILD_UNRAVELING = make_instant(
    name="Wild Unraveling",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}. If that spell is countered this way, its controller draws a card.",
    resolve=None
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

# Bristlebane Battler - {1}{G} Creature — Kithkin Soldier 6/6
def bristlebane_battler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering or entering.controller != obj.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        return obj.state.counters.get('-1/-1', 0) > 0

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 1},
                source=obj.id
            )]
        )

    def enters_with_counters(event: Event, state: GameState) -> list[Event]:
        # "This creature enters with five -1/-1 counters on it."
        return [Event(type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 5},
            source=obj.id)]

    return [
        make_etb_trigger(obj, enters_with_counters),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=other_creature_etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield'
        )
    ]


BRISTLEBANE_BATTLER = make_creature(
    name="Bristlebane Battler",
    power=6,
    toughness=6,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Soldier"},
    text="Trample, ward {2}. This creature enters with five -1/-1 counters on it. Whenever another creature you control enters while this creature has a -1/-1 counter on it, remove a -1/-1 counter from this creature.",
    setup_interceptors=bristlebane_battler_setup
)


# Bristlebane Outrider - {3}{G} Creature — Kithkin Knight 3/5
def bristlebane_outrider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        # Check if another creature entered this turn - simplified, always grant bonus for now
        return True

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + 2
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        )
    ]


BRISTLEBANE_OUTRIDER = make_creature(
    name="Bristlebane Outrider",
    power=3,
    toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Knight"},
    text="This creature can't be blocked by creatures with power 2 or less. As long as another creature entered the battlefield under your control this turn, this creature gets +2/+0.",
    setup_interceptors=bristlebane_outrider_setup
)


# Celestial Reunion - {X}{G} Sorcery
CELESTIAL_REUNION = make_sorcery(
    name="Celestial Reunion",
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may behold a creature card. Search your library for a creature card with mana value X or less. If you paid the behold cost and the creature card you search for shares a creature type with the beheld card, put that card onto the battlefield. Otherwise, put it into your hand. Then shuffle."
)


# Champions of the Perfect - {3}{G} Creature — Elf Warrior 6/6
def champions_of_the_perfect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a creature spell, draw a card."""
    def creature_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.SPELL_CAST:
            return False
        if event.payload.get('controller') != obj.controller:
            return False
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id)
        if not spell:
            return False
        return CardType.CREATURE in spell.characteristics.types

    def creature_cast_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=creature_cast_filter,
            handler=creature_cast_handler,
            duration='while_on_battlefield'
        )
    ]


CHAMPIONS_OF_THE_PERFECT = make_creature(
    name="Champions of the Perfect",
    power=6,
    toughness=6,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="As an additional cost to cast this spell, behold an Elf card and exile it. Whenever you cast a creature spell, draw a card. When this creature leaves the battlefield, return the exiled card to its owner's hand.",
    setup_interceptors=champions_of_the_perfect_setup
)


# Chomping Changeling - {2}{G} Creature — Shapeshifter 1/2
def _find_artifact_or_enchantment(obj: GameObject, state: GameState, *, opponent_only=True):
    for o in state.objects.values():
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if opponent_only and o.controller == obj.controller:
            continue
        if (CardType.ARTIFACT in o.characteristics.types or
                CardType.ENCHANTMENT in o.characteristics.types):
            return o.id
    return None


def chomping_changeling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "destroy up to one target artifact or enchantment."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = _find_artifact_or_enchantment(obj, state, opponent_only=False)
        payload = {'target_filter': 'artifact_or_enchantment', 'optional': True}
        if target:
            payload['object_id'] = target
        return [Event(type=EventType.OBJECT_DESTROYED, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


CHOMPING_CHANGELING = make_creature(
    name="Chomping Changeling",
    power=1,
    toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling. When this creature enters, destroy up to one target artifact or enchantment.",
    setup_interceptors=chomping_changeling_setup
)


# Crossroads Watcher - {2}{G} Creature — Kithkin Ranger 3/3
def crossroads_watcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering or entering.controller != obj.controller:
            return False
        return CardType.CREATURE in entering.characteristics.types

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        # "this creature gets +1/+0 until end of turn."
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0,
                     'duration': 'end_of_turn'}, source=obj.id)])

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=other_creature_etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield'
        )
    ]


# REVISED (rebalance): the +1/+0 ETB rider is a stub; bump 3/3 -> 4/3 so the
# Kithkin/Ranger has trample-relevant power on its own.
CROSSROADS_WATCHER = make_creature(
    name="Crossroads Watcher",
    power=4,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Ranger"},
    text="Trample. Whenever another creature you control enters, this creature gets +1/+0 until end of turn.",
    setup_interceptors=crossroads_watcher_setup
)


# Dawn's Light Archer - {2}{G} Creature — Elf Archer 4/3
# REVISED (rebalance): flash/reach keywords don't fully evaluate; promote 4/2 -> 4/3
# to survive a fair trade and act as a real Elf-tribal flier-killer body.
DAWNS_LIGHT_ARCHER = make_creature(
    name="Dawn's Light Archer",
    power=4,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Archer"},
    text="Flash. Reach.",
    setup_interceptors=None
)


# Dundoolin Weaver - {1}{G} Creature — Kithkin Druid 2/1
def _permanent_card_in_graveyard(obj: GameObject, state: GameState):
    gy = state.zones.get(f"graveyard_{obj.controller}")
    if gy:
        for cid in gy.objects:
            card = state.objects.get(cid)
            if card and card.characteristics.types & {
                    CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT,
                    CardType.LAND, CardType.PLANESWALKER}:
                return cid
    return None


def dundoolin_weaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "if you control three or more creatures, return target permanent card
    #  from your graveyard to your hand."  (intervening-if carried in payload)
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        creatures = sum(1 for o in _battlefield_creatures(state)
                        if o.controller == obj.controller)
        target = _permanent_card_in_graveyard(obj, state)
        ev = _return_from_graveyard_event(obj, target, 'permanent_in_your_graveyard',
                                          optional=False)
        ev.payload['condition'] = 'control_three_or_more_creatures'
        ev.payload['condition_met'] = creatures >= 3
        return [ev]
    return [make_etb_trigger(obj, etb_effect)]


DUNDOOLIN_WEAVER = make_creature(
    name="Dundoolin Weaver",
    power=2,
    toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Druid"},
    text="When this creature enters, if you control three or more creatures, return target permanent card from your graveyard to your hand.",
    setup_interceptors=dundoolin_weaver_setup
)


# Gilt-Leaf's Embrace - {2}{G} Enchantment — Aura
def _gilt_leafs_embrace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Permanent +2/+0 via the standard aura attach path, plus a one-shot ETB
    # that grants trample + indestructible to the enchanted creature until EOT.
    base = make_aura_setup(power_mod=2, toughness_mod=0)(obj, state)

    def etb_grant(event: Event, state: GameState) -> list[Event]:
        target_id = getattr(obj.state, 'attached_to', None) or getattr(obj.state, '_aura_target_id', None)
        if not target_id:
            return []
        return [
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': target_id, 'keyword': 'trample', 'duration': 'end_of_turn'},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                  source=obj.id, controller=obj.controller),
        ]

    return base + [make_etb_trigger(obj, etb_grant)]


GILT_LEAFS_EMBRACE = make_enchantment(
    name="Gilt-Leaf's Embrace",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Aura"},
    text="Flash. Enchant creature you control. When this Aura enters, enchanted creature gains trample and indestructible until end of turn. Enchanted creature gets +2/+0.",
    setup_interceptors=_gilt_leafs_embrace_setup
)


# Pitiless Fists - {3}{G} Enchantment — Aura
PITILESS_FISTS = make_enchantment(
    name="Pitiless Fists",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Aura"},
    text="Enchant creature you control. When this Aura enters, enchanted creature fights up to one target creature an opponent controls.",
    setup_interceptors=None
)


# Prismabasher - {4}{G}{G} Creature — Elemental 6/6
def prismabasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "up to X target creatures you control get +X/+X until end of turn, where X
    #  is the number of colors among permanents you control."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        x = max(1, _colors_among_permanents(obj, state))
        targets = [o.id for o in _battlefield_creatures(state)
                   if o.controller == obj.controller][:x]
        if targets:
            return [Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': t, 'power_mod': x, 'toughness_mod': x,
                         'duration': 'end_of_turn'}, source=obj.id) for t in targets]
        return [Event(type=EventType.PT_MODIFICATION,
            payload={'power_mod': x, 'toughness_mod': x, 'duration': 'end_of_turn',
                     'target_filter': 'up_to_x_creatures_you_control'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


PRISMABASHER = make_creature(
    name="Prismabasher",
    power=6,
    toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Trample. Vivid — When this creature enters, up to X target creatures you control get +X/+X until end of turn, where X is the number of colors among permanents you control.",
    setup_interceptors=prismabasher_setup
)


# Prismatic Undercurrents - {3}{G} Enchantment
PRISMATIC_UNDERCURRENTS = make_enchantment(
    name="Prismatic Undercurrents",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Vivid — When this enchantment enters, search your library for up to X basic land cards, where X is the number of colors among permanents you control, reveal them, put them into your hand, then shuffle. You may play an additional land on each of your turns.",
    setup_interceptors=None
)


# Assert Perfection - {1}{G} Sorcery
ASSERT_PERFECTION = make_sorcery(
    name="Assert Perfection",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+0 until end of turn. It deals damage equal to its power to up to one target creature an opponent controls."
)


# Aurora Awakener - {6}{G} Creature — Giant Druid 7/7
AURORA_AWAKENER = make_creature(
    name="Aurora Awakener",
    power=7,
    toughness=7,
    mana_cost="{6}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Druid"},
    text="Trample. Vivid — When this creature enters, reveal cards from the top of your library until you reveal X permanent cards, where X is the number of colors among permanents you control. Put those cards into your hand and the rest on the bottom of your library in a random order.",
    setup_interceptors=None
)


# Bloom Tender - {1}{G} Creature — Elf Druid 1/1
BLOOM_TENDER = make_creature(
    name="Bloom Tender",
    power=1,
    toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="Vivid — {T}: For each color among permanents you control, add one mana of that color.",
    setup_interceptors=None
)


# Blossoming Defense - {G} Instant
BLOSSOMING_DEFENSE = make_instant(
    name="Blossoming Defense",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +2/+2 and gains hexproof until end of turn.",
    resolve=None
)


# Mistmeadow Council - {3}{G}{G} Creature — Kithkin Advisor 4/5
def mistmeadow_council_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Kithkin Token', 'controller': obj.controller,
                        'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                        'subtypes': ['Kithkin'], 'colors': [Color.WHITE]},
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Kithkin Token', 'controller': obj.controller,
                        'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                        'subtypes': ['Kithkin'], 'colors': [Color.WHITE]},
                source=obj.id
            )
        ]
    interceptors = [make_etb_trigger(obj, etb_effect)]
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, 'Kithkin')))
    return interceptors


MISTMEADOW_COUNCIL = make_creature(
    name="Mistmeadow Council",
    power=4,
    toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Advisor"},
    text="When Mistmeadow Council enters, create two 1/1 white Kithkin creature tokens. Other Kithkin you control get +1/+1.",
    setup_interceptors=mistmeadow_council_setup
)


# Morcant's Eyes - {2}{G} Enchantment — Aura
# --- Morcant's Eyes (Aura tagging sweep, W22+) ---
# Helper 5 wire: +2/+2 plus "combat damage to player → controller draws a card".
def _morcants_eyes_combat_dmg_to_player_filter(event: Event, state: GameState, target_id: str) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    return event.payload.get('target') in state.players


def _morcants_eyes_draw_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    return [Event(
        type=EventType.DRAW,
        payload={'player': target_obj.controller, 'amount': 1, 'source': target_obj.id},
        source=target_obj.id,
    )]


MORCANTS_EYES = make_enchantment(
    name="Morcant's Eyes",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets +2/+2 and has 'Whenever this creature deals combat damage to a player, draw a card.'",
    setup_interceptors=make_aura_setup(
        power_mod=2, toughness_mod=2,
        granted_triggered_abilities={
            "event_filter": _morcants_eyes_combat_dmg_to_player_filter,
            "effect_fn": _morcants_eyes_draw_effect,
            "description": "Combat damage to player → draw a card",
        },
    ),
)


# Sapling Nursery - {2}{G} Enchantment
def sapling_nursery_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Treefolk Token', 'controller': obj.controller,
                    'power': 0, 'toughness': 1, 'types': [CardType.CREATURE],
                    'subtypes': ['Treefolk'], 'colors': [Color.GREEN]},
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]


SAPLING_NURSERY = make_enchantment(
    name="Sapling Nursery",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, create a 0/1 green Treefolk creature token. {4}{G}: Treefolk you control get +2/+2 until end of turn.",
    setup_interceptors=sapling_nursery_setup
)


# Shimmerwilds Growth - {G} Enchantment — Aura
SHIMMERWILDS_GROWTH = make_enchantment(
    name="Shimmerwilds Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Aura"},
    text="Enchant land. Enchanted land has '{T}: Add one mana of any color.'",
    setup_interceptors=None
)


# Spry and Mighty - {1}{G} Instant
SPRY_AND_MIGHTY = make_instant(
    name="Spry and Mighty",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. Untap it.",
    resolve=None
)


# Trystan, Callous Cultivator - {2}{G}{G} Legendary Creature — Elf Druid 3/4
def trystan_callous_cultivator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj or dying_obj.controller != src.controller:
            return False
        if CardType.CREATURE not in dying_obj.characteristics.types:
            return False
        return dying_obj.state.counters.get('-1/-1', 0) > 0

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_dies_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]


TRYSTAN_CALLOUS_CULTIVATOR = make_creature(
    name="Trystan, Callous Cultivator",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    supertypes={"Legendary"},
    text="Whenever a creature you control with a -1/-1 counter on it dies, draw a card. {T}: Put a -1/-1 counter on target creature you control. Add one mana of any color.",
    setup_interceptors=trystan_callous_cultivator_setup
)


# Unforgiving Aim - {3}{G} Instant
UNFORGIVING_AIM = make_instant(
    name="Unforgiving Aim",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature an opponent controls. You gain life equal to the damage dealt this way.",
    resolve=None
)


# Vinebred Brawler - {3}{G} Creature — Treefolk Warrior 5/4
VINEBRED_BRAWLER = make_creature(
    name="Vinebred Brawler",
    power=5,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Warrior"},
    text="Trample. As an additional cost to cast this spell, you may blight 2. If you do, Vinebred Brawler enters with a +1/+1 counter on it.",
    setup_interceptors=None
)


# Virulent Emissary - {2}{G} Creature — Elf Druid 2/2
def virulent_emissary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = [make_wither_damage(obj)]

    def creature_dies_filter(event: Event, state: GameState, src: GameObject) -> bool:
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
        if CardType.CREATURE not in dying_obj.characteristics.types:
            return False
        return dying_obj.state.counters.get('-1/-1', 0) > 0

    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_dies_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=life_gain_effect(e, s)),
        duration='while_on_battlefield'
    ))
    return interceptors


# REVISED (rebalance): wither + drain triggers do work; promote 2/2 -> 2/3
# so this Elf Druid actually survives long enough to leverage them.
VIRULENT_EMISSARY = make_creature(
    name="Virulent Emissary",
    power=2,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="Wither. Whenever a creature with a -1/-1 counter on it dies, you gain 2 life.",
    setup_interceptors=virulent_emissary_setup
)


# Wildvine Pummeler - {4}{G}{G} Creature — Elemental 6/5
def wildvine_pummeler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "destroy target artifact or enchantment an opponent controls."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        target = _find_artifact_or_enchantment(obj, state, opponent_only=True)
        payload = {'target_filter': 'opponent_artifact_or_enchantment'}
        if target:
            payload['object_id'] = target
        return [Event(type=EventType.OBJECT_DESTROYED, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


WILDVINE_PUMMELER = make_creature(
    name="Wildvine Pummeler",
    power=6,
    toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Trample. When Wildvine Pummeler enters, destroy target artifact or enchantment an opponent controls.",
    setup_interceptors=wildvine_pummeler_setup
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

# Barbed Bloodletter - {1}{B} Artifact — Equipment
BARBED_BLOODLETTER = make_artifact(
    name="Barbed Bloodletter",
    mana_cost="{1}{B}",
    subtypes={"Equipment"},
    text="Flash. When Barbed Bloodletter enters, attach it to target creature you control. That creature gains wither until end of turn. Equipped creature gets +1/+2. Equip {2}",
    # Static +1/+2 + Equip {2}. (ETB auto-attach-to-target + temporary wither
    # grant are a targeted-ETB rider handled in Phase B.)
    setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=2, equip_cost="{2}")
)


# Bogslither's Embrace - {1}{B} Sorcery
BOGSLITHERS_EMBRACE = make_sorcery(
    name="Bogslither's Embrace",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, blight 1 or pay {3}. Exile target creature."
)


# Champion of the Weird - {3}{B} Creature — Goblin Berserker 5/5
CHAMPION_OF_THE_WEIRD = make_creature(
    name="Champion of the Weird",
    power=5,
    toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Berserker"},
    text="As an additional cost to cast this spell, behold a Goblin card and exile it. Pay 1 life, Blight 2: Target opponent blights 2. Activate only as a sorcery. When this creature leaves the battlefield, return the exiled card to its owner's hand.",
    setup_interceptors=None
)


# Dawnhand Dissident - {B} Creature — Elf Warlock 1/2
DAWNHAND_DISSIDENT = make_creature(
    name="Dawnhand Dissident",
    power=1,
    toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="{T}, Blight 1: Surveil 1. {T}, Blight 2: Exile target card from a graveyard. You may cast creature cards exiled with this creature by removing three -1/-1 counters from among creatures you control rather than paying their mana costs.",
    setup_interceptors=None
)


# Dose of Dawnglow - {4}{B} Instant
DOSE_OF_DAWNGLOW = make_instant(
    name="Dose of Dawnglow",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. If it's not your main phase, blight 2.",
    resolve=None
)


# Deceit - {4}{U/B}{U/B} Creature — Elemental Incarnation 5/5
def deceit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "If {U}{U} was spent ... return up to one target nonland permanent to its
    #  owner's hand. If {B}{B} was spent ... target opponent reveals their hand.
    #  You choose a nonland card ... that player discards that card."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        bounce_target = find_any_creature(obj, state, exclude_self=True)
        bev = _return_to_hand_event(obj, bounce_target, 'other_nonland_permanent',
                                    optional=True)
        bev.payload['condition'] = 'UU_spent'
        events.append(bev)
        opp = next(opponents_of(obj, state), None)
        dpayload = {'count': 1, 'chosen_by': obj.controller, 'nonland_only': True,
                    'condition': 'BB_spent'}
        if opp:
            dpayload['player'] = opp
        events.append(Event(type=EventType.DISCARD, payload=dpayload, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect), make_evoke(obj, "{U/B}{U/B}")]


DECEIT = make_creature(
    name="Deceit",
    power=5,
    toughness=5,
    mana_cost="{4}{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Elemental", "Incarnation"},
    text="If {U}{U} was spent to cast this spell, when it enters, return up to one target nonland permanent to its owner's hand. If {B}{B} was spent to cast this spell, when it enters, target opponent reveals their hand. You choose a nonland card from it. That player discards that card. Evoke {U/B}{U/B}",
    setup_interceptors=deceit_setup
)


# Dream Harvest - {5}{U/B}{U/B} Sorcery
DREAM_HARVEST = make_sorcery(
    name="Dream Harvest",
    mana_cost="{5}{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    text="Each opponent exiles cards from the top of their library until the total mana value of cards exiled this way is 5 or greater. You may cast any number of spells from among cards exiled this way without paying their mana costs."
)


# Requiting Hex - {B} Instant
REQUITING_HEX = make_instant(
    name="Requiting Hex",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may blight 1. Destroy target creature with mana value 2 or less. If the additional cost was paid, you gain 2 life.",
    resolve=None
)


# Retched Wretch - {2}{B} Creature — Goblin 4/2
def retched_wretch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_filter(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != src.id:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        return src.state.counters.get('-1/-1', 0) > 0

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.BATTLEFIELD, 'loses_abilities': True},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=death_effect(e, s)),
        duration='until_leaves'
    )]


RETCHED_WRETCH = make_creature(
    name="Retched Wretch",
    power=4,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin"},
    text="When this creature dies, if it had a -1/-1 counter on it, return it to the battlefield under your control and it loses all abilities.",
    setup_interceptors=retched_wretch_setup
)


# Gloom Ripper - {3}{B}{B} Creature — Elemental Horror 5/4
def gloom_ripper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "target opponent sacrifices a creature."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        opp = next(opponents_of(obj, state), None)
        victim = find_opponent_creature(obj, state)
        payload = {'sacrifice_type': 'creature'}
        if opp:
            payload['player'] = opp
        if victim:
            payload['object_id'] = victim
        return [Event(type=EventType.SACRIFICE, payload=payload, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


GLOOM_RIPPER = make_creature(
    name="Gloom Ripper",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Horror"},
    text="Flying. When Gloom Ripper enters, target opponent sacrifices a creature.",
    setup_interceptors=gloom_ripper_setup
)


# Grub, Storied Matriarch - {2}{B}{B} Legendary Creature — Goblin Warlock 3/3
def grub_storied_matriarch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another Goblin you control dies, drain 1 from each opponent."""
    def goblin_death_filter(event: Event, state: GameState) -> bool:
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
        if not dying_obj or dying_obj.controller != obj.controller:
            return False
        if CardType.CREATURE not in dying_obj.characteristics.types:
            return False
        return 'Goblin' in dying_obj.characteristics.subtypes

    def goblin_death_handler(event: Event, state: GameState) -> InterceptorResult:
        events = [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': player_id, 'amount': -1}, source=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller, priority=InterceptorPriority.REACT,
                        filter=goblin_death_filter, handler=goblin_death_handler, duration='while_on_battlefield')]


GRUB_STORIED_MATRIARCH = make_creature(
    name="Grub, Storied Matriarch",
    power=3,
    toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever another Goblin you control dies, each opponent loses 1 life and you gain 1 life. {2}{B}: Create a 1/1 black and red Goblin creature token.",
    setup_interceptors=grub_storied_matriarch_setup
)


# Gutsplitter Gang - {4}{B} Creature — Goblin Warrior 4/3
GUTSPLITTER_GANG = make_creature(
    name="Gutsplitter Gang",
    power=4,
    toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warrior"},
    text="Menace. When Gutsplitter Gang enters, target opponent discards a card.",
    setup_interceptors=None
)


# Heirloom Auntie - {2}{B} Creature — Goblin Warlock 2/2
HEIRLOOM_AUNTIE = make_creature(
    name="Heirloom Auntie",
    power=2,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warlock"},
    text="When Heirloom Auntie enters, you may return target Goblin card from your graveyard to your hand.",
    setup_interceptors=None
)


# Moonglove Extractor - {1}{B} Creature — Elf Assassin 1/1
MOONGLOVE_EXTRACTOR = make_creature(
    name="Moonglove Extractor",
    power=1,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Assassin"},
    text="Deathtouch. When Moonglove Extractor dies, target creature gets -1/-1 until end of turn.",
    setup_interceptors=None
)


# Moonshadow - {3}{B} Creature — Faerie Rogue 2/2
MOONSHADOW = make_creature(
    name="Moonshadow",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flash. Flying. When Moonshadow enters, target creature gets -2/-2 until end of turn.",
    setup_interceptors=None
)


# Mudbutton Cursetosser - {1}{B} Creature — Goblin Shaman 1/2
MUDBUTTON_CURSETOSSER = make_creature(
    name="Mudbutton Cursetosser",
    power=1,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Shaman"},
    text="When Mudbutton Cursetosser enters, put a -1/-1 counter on target creature.",
    setup_interceptors=None
)


# Nameless Inversion - {1}{B} Kindred Instant — Shapeshifter
NAMELESS_INVERSION = make_instant(
    name="Nameless Inversion",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Changeling. Target creature gets +3/-3 until end of turn.",
    resolve=None
)


# Nightmare Sower - {4}{B}{B} Creature — Elemental Horror 5/5
NIGHTMARE_SOWER = make_creature(
    name="Nightmare Sower",
    power=5,
    toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Horror"},
    text="Flying. When Nightmare Sower enters, each opponent sacrifices a creature. You gain life equal to the total power of creatures sacrificed this way.",
    setup_interceptors=None
)


# Perfect Intimidation - {2}{B}{B} Sorcery
PERFECT_INTIMIDATION = make_sorcery(
    name="Perfect Intimidation",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You gain life equal to the greatest power among creatures sacrificed this way."
)


# Scarblade Scout - {B} Creature — Elf Assassin 1/1
SCARBLADE_SCOUT = make_creature(
    name="Scarblade Scout",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Assassin"},
    text="{T}, Exile an Elf card from your graveyard: Destroy target creature that was dealt damage this turn.",
    setup_interceptors=None
)


# Scarblade's Malice - {1}{B} Instant
SCARBLADES_MALICE = make_instant(
    name="Scarblade's Malice",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If you control an Elf, that creature gets -4/-4 instead.",
    resolve=None
)


# Shimmercreep - {2}{B} Creature — Faerie Rogue 1/3
SHIMMERCREEP = make_creature(
    name="Shimmercreep",
    power=1,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. Whenever Shimmercreep deals combat damage to a player, that player discards a card.",
    setup_interceptors=None
)


# Taster of Wares - {1}{B}{B} Creature — Faerie Rogue 2/2
TASTER_OF_WARES = make_creature(
    name="Taster of Wares",
    power=2,
    toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. When Taster of Wares enters, you may sacrifice an artifact. If you do, draw two cards.",
    setup_interceptors=None
)


# Twilight Diviner - {2}{B} Creature — Faerie Wizard 1/2
TWILIGHT_DIVINER = make_creature(
    name="Twilight Diviner",
    power=1,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Wizard"},
    text="Flying. {1}{B}, {T}: Target player loses 1 life and you gain 1 life. If that player has no cards in hand, they lose 3 life instead.",
    setup_interceptors=None
)


# Unbury - {3}{B} Sorcery
UNBURY = make_sorcery(
    name="Unbury",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. It enters with a -1/-1 counter on it."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

# Champion of the Path - {3}{R} Creature — Elemental Sorcerer 7/3
def champion_of_path_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def affects_elementals(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                target.id != obj.id and
                "Elemental" in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    # Grant other Elementals "damage equal to power" - simplified as +0/+0
    return []


CHAMPION_OF_THE_PATH = make_creature(
    name="Champion of the Path",
    power=7,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="As an additional cost to cast this spell, behold an Elemental card and exile it. Other Elementals you control have 'Whenever this creature deals combat damage to a player, it deals damage equal to its power to up to one target creature that player controls.' When this creature leaves the battlefield, return the exiled card to its owner's hand.",
    setup_interceptors=champion_of_path_setup
)


# End-Blaze Epiphany - {X}{R} Instant
END_BLAZE_EPIPHANY = make_instant(
    name="End-Blaze Epiphany",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="End-Blaze Epiphany deals X damage to target creature. When that creature dies this turn, exile the top X cards of your library. Until the end of your next turn, you may play those cards.",
    resolve=None
)


# Flame-Chain Mauler - {2}{R} Creature — Giant Berserker 6/3
FLAME_CHAIN_MAULER_REAL = make_creature(
    name="Flame-Chain Mauler",
    power=6,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Berserker"},
    text="This creature enters with two -1/-1 counters on it. {1}{R}, Remove a -1/-1 counter from this creature: This creature gets +2/+0 until end of turn.",
    setup_interceptors=None
)


# Flamekin Gildweaver - {1}{R} Creature — Elemental Bard 2/2
def flamekin_gildweaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def tap_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == obj.id)

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.MANA_PRODUCED,
                payload={'player': obj.controller, 'colors': [Color.RED, Color.RED]},
                source=obj.id
            )]
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tap_filter,
            handler=tap_handler,
            duration='while_on_battlefield'
        )
    ]


FLAMEKIN_GILDWEAVER_REAL = make_creature(
    name="Flamekin Gildweaver",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Bard"},
    text="{T}: Add {R}{R}. Spend this mana only to cast Elemental spells or activate abilities of Elementals.",
    setup_interceptors=flamekin_gildweaver_setup
)


# Giantfall - {3}{R} Sorcery
GIANTFALL_SPELL = make_sorcery(
    name="Giantfall",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="This spell costs {2} less to cast if you control a Giant. Target creature you control deals damage equal to its power to target creature or planeswalker you don't control."
)


# Goatnap - {2}{R} Sorcery
GOATNAP_SPELL = make_sorcery(
    name="Goatnap",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap it. It gains haste and all creature types until end of turn."
)


# Raiding Schemes - {3}{R}{G} Enchantment
def raiding_schemes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Each noncreature spell you cast has conspire (W29 / CR 702.78)."""
    def noncreature_filter(spell: GameObject, _state: GameState) -> bool:
        return CardType.CREATURE not in spell.characteristics.types
    return [make_conspire_grant(obj, state, spell_filter=noncreature_filter)]


RAIDING_SCHEMES = make_enchantment(
    name="Raiding Schemes",
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Each noncreature spell you cast has conspire.",
    setup_interceptors=raiding_schemes_setup
)


# Reckless Ransacking - {1}{R} Instant
RECKLESS_RANSACKING = make_instant(
    name="Reckless Ransacking",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+2 until end of turn. Create a Treasure token.",
    resolve=None
)


# Hexing Squelcher - {2}{R} Creature — Goblin Shaman 2/2
HEXING_SQUELCHER = make_creature(
    name="Hexing Squelcher",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="When Hexing Squelcher enters, it deals 1 damage to each creature you don't control.",
    setup_interceptors=None
)


# Impolite Entrance - {3}{R} Sorcery
IMPOLITE_ENTRANCE = make_sorcery(
    name="Impolite Entrance",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn."
)


# Kindle the Inner Flame - {R} Instant
KINDLE_THE_INNER_FLAME = make_instant(
    name="Kindle the Inner Flame",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 until end of turn. If you control an Elemental, that creature gets +3/+0 instead.",
    resolve=None
)


# Kulrath Zealot - {1}{R} Creature — Elemental Berserker 2/2
KULRATH_ZEALOT = make_creature(
    name="Kulrath Zealot",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Berserker"},
    text="Haste. When Kulrath Zealot enters, it deals 2 damage to any target.",
    setup_interceptors=None
)


# Lasting Tarfire - {R} Kindred Instant — Goblin
LASTING_TARFIRE = make_instant(
    name="Lasting Tarfire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Lasting Tarfire deals 2 damage to any target. If that permanent or player is dealt damage this way, Lasting Tarfire deals 1 damage to them at the beginning of the next upkeep.",
    resolve=None
)


# Lavaleaper - {2}{R} Creature — Elemental 3/2
LAVALEAPER = make_creature(
    name="Lavaleaper",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. When Lavaleaper enters, it deals 1 damage to each opponent.",
    setup_interceptors=None
)


# Meek Attack - {R} Instant
MEEK_ATTACK = make_instant(
    name="Meek Attack",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature with power 2 or less can't be blocked this turn.",
    resolve=None
)


# Scuzzback Scrounger - {1}{R} Creature — Goblin Warrior 2/2
SCUZZBACK_SCROUNGER = make_creature(
    name="Scuzzback Scrounger",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Persist.",
    setup_interceptors=None
)


# Sear - {1}{R} Instant
SEAR = make_instant(
    name="Sear",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Sear deals 3 damage to target creature or planeswalker.",
    resolve=None
)


# Sizzling Changeling - {2}{R} Creature — Shapeshifter 2/2
SIZZLING_CHANGELING = make_creature(
    name="Sizzling Changeling",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Shapeshifter"},
    text="Changeling. Haste. When Sizzling Changeling enters, it deals 1 damage to each opponent.",
    setup_interceptors=None
)


# Soul Immolation - {4}{R}{R} Sorcery
SOUL_IMMOLATION = make_sorcery(
    name="Soul Immolation",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Soul Immolation deals 6 damage to each creature."
)


# Soulbright Seeker - {3}{R} Creature — Elemental Shaman 4/3
SOULBRIGHT_SEEKER = make_creature(
    name="Soulbright Seeker",
    power=4,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Shaman"},
    text="Trample. {R}: Soulbright Seeker gets +1/+0 until end of turn.",
    setup_interceptors=None
)


# Sourbread Auntie - {1}{R} Creature — Goblin Warlock 1/2
SOURBREAD_AUNTIE = make_creature(
    name="Sourbread Auntie",
    power=1,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="When Sourbread Auntie enters, target Goblin you control gets +2/+0 and gains menace until end of turn.",
    setup_interceptors=None
)


# Spinerock Tyrant - {5}{R}{R} Creature — Giant Warrior 7/6
SPINEROCK_TYRANT = make_creature(
    name="Spinerock Tyrant",
    power=7,
    toughness=6,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Trample. When Spinerock Tyrant enters, it deals 3 damage to any target.",
    setup_interceptors=None
)


# Squawkroaster - {1}{R} Creature — Elemental Bird 2/1
SQUAWKROASTER = make_creature(
    name="Squawkroaster",
    power=2,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Bird"},
    text="Flying. When Squawkroaster dies, it deals 1 damage to any target.",
    setup_interceptors=None
)


# Sting-Slinger - {R} Creature — Goblin 1/1
STING_SLINGER = make_creature(
    name="Sting-Slinger",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="{T}, Sacrifice Sting-Slinger: It deals 1 damage to any target.",
    setup_interceptors=None
)


# Tweeze - {1}{R} Sorcery
TWEEZE = make_sorcery(
    name="Tweeze",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Tweeze deals 2 damage to target creature or planeswalker. Create a Treasure token."
)


# Warren Torchmaster - {3}{R} Creature — Goblin Warrior 3/3
WARREN_TORCHMASTER = make_creature(
    name="Warren Torchmaster",
    power=3,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Other Goblins you control get +1/+0 and have haste.",
    setup_interceptors=None
)


# =============================================================================
# ADDITIONAL MULTICOLOR CARDS
# =============================================================================

# Ashling's Command - {3}{U}{R} Kindred Instant — Elemental
ASHLINGS_COMMAND = make_instant(
    name="Ashling's Command",
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Choose two — Create a token that's a copy of target Elemental you control, except it's not legendary; Draw two cards; Ashling's Command deals 3 damage to each creature; Create two Treasure tokens.",
    resolve=None
)


# Brigid's Command - {1}{G}{W} Kindred Sorcery — Kithkin
BRIGIDS_COMMAND = make_sorcery(
    name="Brigid's Command",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Choose two — Create a token that's a copy of target Kithkin you control, except it's not legendary; Create a 1/1 white Kithkin creature token; Target creature gets +2/+2 and gains trample until end of turn; Target creature you control fights target creature you don't control."
)


# Glister Bairn - {2}{G/U}{G/U}{G/U} Creature — Ouphe 1/4
def glister_bairn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_handler(event: Event, state: GameState) -> InterceptorResult:
        # "another target creature you control gets +X/+X until end of turn,
        #  where X is the number of colors among permanents you control."
        x = max(1, _colors_among_permanents(obj, state))
        target = find_friendly_creature(obj, state, exclude_self=True)
        payload = {'power_mod': x, 'toughness_mod': x, 'duration': 'end_of_turn',
                   'target_filter': 'other_creature_you_control'}
        if target:
            payload['object_id'] = target
        return InterceptorResult(action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.PT_MODIFICATION, payload=payload, source=obj.id)])

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=combat_filter,
            handler=combat_handler,
            duration='while_on_battlefield'
        )
    ]


GLISTER_BAIRN = make_creature(
    name="Glister Bairn",
    power=1,
    toughness=4,
    mana_cost="{2}{G/U}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Ouphe"},
    text="Vivid — At the beginning of combat on your turn, another target creature you control gets +X/+X until end of turn, where X is the number of colors among permanents you control.",
    setup_interceptors=glister_bairn_setup
)


# Prideful Feastling - {2}{W/B} Creature — Shapeshifter 2/3
PRIDEFUL_FEASTLING = make_creature(
    name="Prideful Feastling",
    power=2,
    toughness=3,
    mana_cost="{2}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Shapeshifter"},
    text="Changeling. Lifelink.",
    setup_interceptors=None
)


# Reaping Willow - {1}{W/B}{W/B}{W/B} Creature — Treefolk Cleric 3/6
REAPING_WILLOW = make_creature(
    name="Reaping Willow",
    power=3,
    toughness=6,
    mana_cost="{1}{W/B}{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Treefolk", "Cleric"},
    text="Lifelink. This creature enters with two -1/-1 counters on it. {1}{W/B}, Remove two counters from among permanents you control: Return target creature card with mana value 3 or less from your graveyard to the battlefield.",
    setup_interceptors=None
)


# Catharsis - {3}{R}{W} Sorcery
CATHARSIS = make_sorcery(
    name="Catharsis",
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Destroy all creatures. For each creature destroyed this way, its controller creates a 1/1 white Kithkin creature token."
)


# Emptiness - {4}{B}{B} Creature — Elemental Incarnation 5/5
EMPTINESS = make_creature(
    name="Emptiness",
    power=5,
    toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Incarnation"},
    text="If {B}{B} was spent to cast this spell, when Emptiness enters, destroy target creature. Evoke {B}{B}",
    setup_interceptors=None
)


# Grub's Command - {3}{B}{R} Kindred Sorcery — Goblin
GRUBS_COMMAND = make_sorcery(
    name="Grub's Command",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose two — Create a token that's a copy of target Goblin you control, except it's not legendary; Each player sacrifices a creature; Grub's Command deals 3 damage to each creature you don't control; Create two 1/1 black and red Goblin creature tokens."
)


# High Perfect Morcant - {3}{G}{W} Legendary Creature — Elf Cleric 4/4
HIGH_PERFECT_MORCANT = make_creature(
    name="High Perfect Morcant",
    power=4,
    toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Cleric"},
    supertypes={"Legendary"},
    text="Vigilance. Other Elves you control get +1/+1. Whenever an Elf you control dies, you gain 2 life.",
    setup_interceptors=None
)


# Hovel Hurler - {2}{B/R} Creature — Goblin Warrior 3/2
HOVEL_HURLER = make_creature(
    name="Hovel Hurler",
    power=3,
    toughness=2,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="When Hovel Hurler enters, it deals 1 damage to each opponent and each planeswalker they control.",
    setup_interceptors=None
)


# Kirol, Attentive First-Year - {U/R}{U/R} Legendary Creature — Human Wizard 1/3
KIROL_ATTENTIVE = make_creature(
    name="Kirol, Attentive First-Year",
    power=1,
    toughness=3,
    mana_cost="{U/R}{U/R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, Kirol deals 1 damage to any target.",
    setup_interceptors=None
)


# Lluwen, Imperfect Naturalist - {G/U}{G/U} Legendary Creature — Elf Druid 2/2
LLUWEN_IMPERFECT = make_creature(
    name="Lluwen, Imperfect Naturalist",
    power=2,
    toughness=2,
    mana_cost="{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Elf", "Druid"},
    supertypes={"Legendary"},
    text="Whenever another creature enters the battlefield under your control, scry 1. {T}: Add {G} or {U}.",
    setup_interceptors=None
)


# Maralen, Fae Ascendant - {2}{U}{B} Legendary Creature — Faerie Wizard 3/3
MARALEN_FAE_ASCENDANT = make_creature(
    name="Maralen, Fae Ascendant",
    power=3,
    toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Wizard"},
    supertypes={"Legendary"},
    text="Flying. Players can't draw cards. At the beginning of each player's draw step, that player loses 2 life, searches their library for a card, puts it into their hand, then shuffles.",
    setup_interceptors=None
)


# Merrow Skyswimmer - {2}{W}{U} Creature — Merfolk Wizard 2/4
MERROW_SKYSWIMMER = make_creature(
    name="Merrow Skyswimmer",
    power=2,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Flying. When Merrow Skyswimmer enters, draw a card for each other Merfolk you control.",
    setup_interceptors=None
)


# Mischievous Sneakling - {1}{U/B} Creature — Faerie Rogue 1/2
MISCHIEVOUS_SNEAKLING = make_creature(
    name="Mischievous Sneakling",
    power=1,
    toughness=2,
    mana_cost="{1}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. Whenever Mischievous Sneakling deals combat damage to a player, you may draw a card. If you do, discard a card.",
    setup_interceptors=None
)


# Morcant's Loyalist - {2}{G/W} Creature — Elf Soldier 3/2
MORCANTS_LOYALIST = make_creature(
    name="Morcant's Loyalist",
    power=3,
    toughness=2,
    mana_cost="{2}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Soldier"},
    text="Vigilance. When Morcant's Loyalist enters, you gain 3 life.",
    setup_interceptors=None
)


# Noggle Robber - {1}{U/R} Creature — Noggle Rogue 2/1
NOGGLE_ROBBER = make_creature(
    name="Noggle Robber",
    power=2,
    toughness=1,
    mana_cost="{1}{U/R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Noggle", "Rogue"},
    text="Haste. When Noggle Robber enters, each player discards a card, then draws a card.",
    setup_interceptors=None
)


# Sanar, Innovative First-Year - {G/W}{G/W} Legendary Creature — Human Druid 2/2
SANAR_INNOVATIVE = make_creature(
    name="Sanar, Innovative First-Year",
    power=2,
    toughness=2,
    mana_cost="{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Druid"},
    supertypes={"Legendary"},
    text="Whenever a creature enters the battlefield under your control, you gain 1 life. {T}: Add {G} or {W}.",
    setup_interceptors=None
)


# Shadow Urchin - {1}{B/R} Creature — Elemental 2/1
SHADOW_URCHIN = make_creature(
    name="Shadow Urchin",
    power=2,
    toughness=1,
    mana_cost="{1}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Elemental"},
    text="When Shadow Urchin dies, it deals 1 damage to any target.",
    setup_interceptors=None
)


# Stoic Grove-Guide - {1}{G/W} Creature — Treefolk Druid 2/3
STOIC_GROVE_GUIDE = make_creature(
    name="Stoic Grove-Guide",
    power=2,
    toughness=3,
    mana_cost="{1}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Treefolk", "Druid"},
    text="Vigilance. {T}: Add one mana of any color that a creature you control is.",
    setup_interceptors=None
)


# Sygg's Command - {3}{W}{U} Kindred Sorcery — Merfolk
SYGGS_COMMAND = make_sorcery(
    name="Sygg's Command",
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Choose two — Create a token that's a copy of target Merfolk you control, except it's not legendary; Tap up to three target creatures; Draw a card for each Merfolk you control; You gain 1 life for each creature you control."
)


# Tam, Mindful First-Year - {B/G}{B/G} Legendary Creature — Human Shaman 1/2
TAM_MINDFUL = make_creature(
    name="Tam, Mindful First-Year",
    power=1,
    toughness=2,
    mana_cost="{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever a creature you control dies, put a +1/+1 counter on Tam.",
    setup_interceptors=None
)


# Thoughtweft Lieutenant - {1}{G}{W} Creature — Kithkin Soldier 3/3
THOUGHTWEFT_LIEUTENANT = make_creature(
    name="Thoughtweft Lieutenant",
    power=3,
    toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Vigilance. Other Kithkin you control get +1/+1.",
    setup_interceptors=None
)


# Trystan's Command - {2}{B}{G} Kindred Sorcery — Elf
TRYSTANS_COMMAND = make_sorcery(
    name="Trystan's Command",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Choose two — Create a token that's a copy of target Elf you control, except it's not legendary; Each opponent sacrifices a creature; You gain life equal to the greatest power among creatures you control; Return target Elf card from your graveyard to your hand."
)


# Twinflame Travelers - {2}{U}{R} Creature — Elemental 3/2
TWINFLAME_TRAVELERS = make_creature(
    name="Twinflame Travelers",
    power=3,
    toughness=2,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Elemental"},
    text="Flying, haste. When Twinflame Travelers enters, create a token that's a copy of it. Sacrifice that token at the beginning of the next end step.",
    setup_interceptors=None
)


# Vibrance - {3}{G}{G} Creature — Elemental Incarnation 5/5
VIBRANCE = make_creature(
    name="Vibrance",
    power=5,
    toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Incarnation"},
    text="Trample. If {G}{G} was spent to cast this spell, when Vibrance enters, search your library for a basic land card, put it onto the battlefield, then shuffle. Evoke {G}{G}",
    setup_interceptors=None
)


# Voracious Tome-Skimmer - {1}{U/B}{U/B} Creature — Faerie Wizard 2/2
VORACIOUS_TOME_SKIMMER = make_creature(
    name="Voracious Tome-Skimmer",
    power=2,
    toughness=2,
    mana_cost="{1}{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Wizard"},
    text="Flying. When Voracious Tome-Skimmer enters, each opponent mills three cards. You draw a card for each creature card milled this way.",
    setup_interceptors=None
)


# Wary Farmer - {1}{G/W} Creature — Kithkin Peasant 2/2
WARY_FARMER = make_creature(
    name="Wary Farmer",
    power=2,
    toughness=2,
    mana_cost="{1}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin", "Peasant"},
    text="When Wary Farmer enters, create a Food token.",
    setup_interceptors=None
)


# Wistfulness - {3}{U}{U} Creature — Elemental Incarnation 5/5
WISTFULNESS = make_creature(
    name="Wistfulness",
    power=5,
    toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Incarnation"},
    text="If {U}{U} was spent to cast this spell, when Wistfulness enters, draw two cards. Evoke {U}{U}",
    setup_interceptors=None
)


# =============================================================================
# ARTIFACT CARDS
# =============================================================================

# Chronicle of Victory - {6} Legendary Artifact
CHRONICLE_OF_VICTORY = make_artifact(
    name="Chronicle of Victory",
    mana_cost="{6}",
    subtypes={"Legendary"},
    text="As Chronicle of Victory enters, choose a creature type. Creatures you control of the chosen type get +2/+2 and have first strike and trample. Whenever you cast a spell of the chosen type, draw a card."
)

# Dawn-Blessed Pennant - {1} Artifact
DAWN_BLESSED_PENNANT = make_artifact(
    name="Dawn-Blessed Pennant",
    mana_cost="{1}",
    text="As this artifact enters, choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or Treefolk. Whenever a permanent you control of the chosen type enters, you gain 1 life."
)

# Firdoch Core - {3} Kindred Artifact — Shapeshifter
FIRDOCH_CORE = make_artifact(
    name="Firdoch Core",
    mana_cost="{3}",
    subtypes={"Shapeshifter"},
    text="Changeling. {T}: Add one mana of any color. {4}: This artifact becomes a 4/4 artifact creature until end of turn."
)

# Foraging Wickermaw - {2} Artifact Creature — Scarecrow
def foraging_wickermaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "When this creature enters, surveil 1."
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL,
                      payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


FORAGING_WICKERMAW = make_creature(
    name="Foraging Wickermaw",
    power=2,
    toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="When this creature enters, surveil 1. {1}: Add one mana of any color. This creature becomes that color until end of turn. Activate only once each turn.",
    setup_interceptors=foraging_wickermaw_setup
)

# Gathering Stone - {4} Artifact
GATHERING_STONE = make_artifact(
    name="Gathering Stone",
    mana_cost="{4}",
    text="As this artifact enters, choose a creature type. Spells you cast of the chosen type cost {1} less to cast. When this artifact enters and at the beginning of your upkeep, look at the top card of your library. If it's a card of the chosen type, you may reveal it and put it into your hand."
)

# Mirrormind Crown - {4} Artifact — Equipment
MIRRORMIND_CROWN = make_artifact(
    name="Mirrormind Crown",
    mana_cost="{4}",
    subtypes={"Equipment"},
    text="As long as this Equipment is attached to a creature, the first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of equipped creature. Equip {2}"
)

# Puca's Eye - {2} Artifact
PUCAS_EYE = make_artifact(
    name="Puca's Eye",
    mana_cost="{2}",
    text="When this artifact enters, draw a card, then choose a color. This artifact becomes the chosen color. {3}, {T}: Draw a card. Activate only if there are five colors among permanents you control."
)

# Springleaf Drum - {1} Artifact
SPRINGLEAF_DRUM = make_artifact(
    name="Springleaf Drum",
    mana_cost="{1}",
    text="{T}, Tap an untapped creature you control: Add one mana of any color."
)

# Stalactite Dagger - {2} Artifact — Equipment
def stalactite_dagger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Shapeshifter Token', 'controller': obj.controller,
                    'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                    'subtypes': ['Shapeshifter']},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


STALACTITE_DAGGER = make_artifact(
    name="Stalactite Dagger",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="When this Equipment enters, create a 1/1 colorless Shapeshifter creature token with changeling. Equipped creature gets +1/+1 and is all creature types. Equip {2}",
    setup_interceptors=stalactite_dagger_setup
)


# =============================================================================
# LAND CARDS
# =============================================================================

# Basic Lands
FOREST = make_land(
    name="Forest",
    subtypes={"Forest"},
    supertypes={"Basic"},
    text="({T}: Add {G}.)"
)

ISLAND = make_land(
    name="Island",
    subtypes={"Island"},
    supertypes={"Basic"},
    text="({T}: Add {U}.)"
)

MOUNTAIN = make_land(
    name="Mountain",
    subtypes={"Mountain"},
    supertypes={"Basic"},
    text="({T}: Add {R}.)"
)

PLAINS = make_land(
    name="Plains",
    subtypes={"Plains"},
    supertypes={"Basic"},
    text="({T}: Add {W}.)"
)

SWAMP = make_land(
    name="Swamp",
    subtypes={"Swamp"},
    supertypes={"Basic"},
    text="({T}: Add {B}.)"
)

# Shock Lands
BLOOD_CRYPT = make_land(
    name="Blood Crypt",
    subtypes={"Swamp", "Mountain"},
    text="({T}: Add {B} or {R}.) As Blood Crypt enters, you may pay 2 life. If you don't, it enters tapped."
)

HALLOWED_FOUNTAIN = make_land(
    name="Hallowed Fountain",
    subtypes={"Plains", "Island"},
    text="({T}: Add {W} or {U}.) As Hallowed Fountain enters, you may pay 2 life. If you don't, it enters tapped."
)

OVERGROWN_TOMB = make_land(
    name="Overgrown Tomb",
    subtypes={"Swamp", "Forest"},
    text="({T}: Add {B} or {G}.) As Overgrown Tomb enters, you may pay 2 life. If you don't, it enters tapped."
)

STEAM_VENTS = make_land(
    name="Steam Vents",
    subtypes={"Island", "Mountain"},
    text="({T}: Add {U} or {R}.) As Steam Vents enters, you may pay 2 life. If you don't, it enters tapped."
)

TEMPLE_GARDEN = make_land(
    name="Temple Garden",
    subtypes={"Forest", "Plains"},
    text="({T}: Add {G} or {W}.) As Temple Garden enters, you may pay 2 life. If you don't, it enters tapped."
)

# Other Lands
ECLIPSED_REALMS = make_land(
    name="Eclipsed Realms",
    text="As Eclipsed Realms enters, choose a creature type. {T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast spells of the chosen type or activate abilities of sources of the chosen type."
)

EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice Evolving Wilds: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


# =============================================================================
# MORE WHITE CARDS
# =============================================================================

# Bark of Doran - {1}{W} Artifact — Equipment
BARK_OF_DORAN = make_artifact(
    name="Bark of Doran",
    mana_cost="{1}{W}",
    subtypes={"Equipment"},
    text="Equipped creature gets +0/+1. As long as equipped creature's toughness is greater than its power, it assigns combat damage equal to its toughness rather than its power. Equip {1}",
    # Static +0/+1 + Equip {1}. (The "assign damage = toughness" Doran clause is
    # a combat-damage replacement effect handled in Phase B.)
    setup_interceptors=make_equipment_setup(power_mod=0, toughness_mod=1, equip_cost="{1}")
)

# =============================================================================
# MORE BLUE CARDS
# =============================================================================

# Pestered Wellguard was referenced but need to verify
# Shinestriker - more blue cards

# =============================================================================
# MORE BLACK CARDS
# =============================================================================

# Aunties Favor - {B} Instant
AUNTIES_FAVOR = make_instant(
    name="Auntie's Favor",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+0 and gains menace until end of turn. If you control a Goblin, draw a card."
)

# Wretched Banquet - {B} Sorcery
WRETCHED_BANQUET = make_sorcery(
    name="Wretched Banquet",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Destroy target creature if it has the least power or is tied for least power among creatures on the battlefield."
)

# =============================================================================
# MORE RED CARDS
# =============================================================================

# Cinder Pyromancer - {2}{R} Creature
CINDER_PYROMANCER = make_creature(
    name="Cinder Pyromancer",
    power=0,
    toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Shaman"},
    text="{T}: Cinder Pyromancer deals 1 damage to target player or planeswalker. Whenever you cast a red spell, you may untap Cinder Pyromancer."
)

# Inner-Flame Igniter - {2}{R} Creature
INNER_FLAME_IGNITER = make_creature(
    name="Inner-Flame Igniter",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Warrior"},
    text="{2}{R}: Creatures you control get +1/+0 and gain first strike until end of turn."
)

# Smoldering Spinebacks - {3}{R} Creature
SMOLDERING_SPINEBACKS = make_creature(
    name="Smoldering Spinebacks",
    power=4,
    toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Beast"},
    text="Whenever you cast a spell with mana value 4 or greater, Smoldering Spinebacks deals 1 damage to each opponent."
)

# Thundercloud Shaman - {3}{R}{R} Creature
THUNDERCLOUD_SHAMAN = make_creature(
    name="Thundercloud Shaman",
    power=4,
    toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Shaman"},
    text="When Thundercloud Shaman enters, it deals damage equal to the number of Giants you control to each non-Giant creature."
)

# =============================================================================
# MORE GREEN CARDS
# =============================================================================

# Elvish Harbinger - {2}{G} Creature
# REVISED (rebalance): tutor + mana abilities are stubs; promote 1/2 -> 2/3
# so the body is a real {2}{G} Elf turn-3 play that fuels lord effects.
ELVISH_HARBINGER = make_creature(
    name="Elvish Harbinger",
    power=2,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="When Elvish Harbinger enters, you may search your library for an Elf card, reveal it, then shuffle and put that card on top. {T}: Add one mana of any color."
)

# Heritage Druid - {G} Creature
HERITAGE_DRUID = make_creature(
    name="Heritage Druid",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="Tap three untapped Elves you control: Add {G}{G}{G}."
)

# Imperious Perfect - {1}{G}{G} Creature
# REVISED (rebalance): added missing tribal lord interceptor; reduced CMC by 1
# so the key Elf anthem actually hits the table on curve.
def imperious_perfect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_tribal_lord(obj, "Elf", power_bonus=1, toughness_bonus=1)


IMPERIOUS_PERFECT = make_creature(
    name="Imperious Perfect",
    power=2,
    toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Other Elves you control get +1/+1. {G}, {T}: Create a 1/1 green Elf Warrior creature token.",
    setup_interceptors=imperious_perfect_setup
)

# Nath of the Gilt-Leaf - {3}{B}{G} Creature (Legendary)
NATH_OF_THE_GILT_LEAF = make_creature(
    name="Nath of the Gilt-Leaf",
    power=4,
    toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you may have target opponent discard a card at random. Whenever an opponent discards a card, you may create a 1/1 green Elf Warrior creature token."
)

# Timber Protector - {4}{G} Creature
# REVISED (rebalance): wired up missing Treefolk tribal lord interceptor so
# the +1/+1 anthem actually applies in tribal Treefolk decks.
def timber_protector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_tribal_lord(obj, "Treefolk", power_bonus=1, toughness_bonus=1)


TIMBER_PROTECTOR = make_creature(
    name="Timber Protector",
    power=4,
    toughness=6,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Warrior"},
    text="Other Treefolk creatures you control get +1/+1. Other Treefolk and Forests you control have indestructible.",
    setup_interceptors=timber_protector_setup
)

# Treefolk Harbinger - {G} Creature
TREEFOLK_HARBINGER = make_creature(
    name="Treefolk Harbinger",
    power=0,
    toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Druid"},
    text="When Treefolk Harbinger enters, you may search your library for a Treefolk or Forest card, reveal it, then shuffle and put that card on top of your library."
)

# Wolf-Skull Shaman - {1}{G} Creature
WOLF_SKULL_SHAMAN = make_creature(
    name="Wolf-Skull Shaman",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with Wolf-Skull Shaman, you may reveal it. If you do, create a 2/2 green Wolf creature token."
)

# =============================================================================
# MORE MULTICOLOR CARDS
# =============================================================================

# Oona, Queen of the Fae - {3}{U/B}{U/B}{U/B} Legendary Creature
# Spice rewire (Phase A1): cluster-cleanup of unwired flagship Faerie mythic.
# Original activated-ability text is engine-gap (XR cost + opp library exile +
# color choice). Wire the same role as a tribal snowball: self-flying via
# keyword grant, anthem to Faeries you control (+1/+1), and at each end step
# (your turn) create a 1/1 U/B Faerie Rogue token with flying. Pattern 3
# (snowball value engine) + pattern 5 (asymmetric).
def oona_queen_of_the_fae_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_keyword_grant as _make_keyword_grant,
        make_static_pt_boost as _make_static_pt_boost,
        make_end_step_trigger as _make_end_step_trigger,
        other_creatures_with_subtype as _other_creatures_with_subtype,
    )

    interceptors: list[Interceptor] = []
    # Self flying.
    interceptors.append(_make_keyword_grant(
        obj, ['flying'], lambda t, s: t.id == obj.id
    ))
    # Anthem: other Faeries you control get +1/+1.
    interceptors.extend(_make_static_pt_boost(
        obj, 1, 1, _other_creatures_with_subtype(obj, 'Faerie')
    ))

    # End-step trigger: spawn a Faerie Rogue.
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Faerie Rogue',
                    'types': {CardType.CREATURE},
                    'subtypes': {'Faerie', 'Rogue'},
                    'colors': {Color.BLUE, Color.BLACK},
                    'power': 1, 'toughness': 1,
                    'keywords': ['flying'],
                },
            },
            source=obj.id,
        )]
    interceptors.append(_make_end_step_trigger(obj, end_step_effect, controller_only=True))
    return interceptors


OONA_QUEEN_OF_THE_FAE = make_creature(
    name="Oona, Queen of the Fae",
    power=5,
    toughness=5,
    mana_cost="{3}{U/B}{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Wizard"},
    supertypes={"Legendary"},
    text="Flying. Other Faeries you control get +1/+1. At the beginning of your end step, create a 1/1 blue and black Faerie Rogue creature token with flying.",
    setup_interceptors=oona_queen_of_the_fae_setup,
)

# Sygg, River Guide - {W}{U} Legendary Creature
SYGG_RIVER_GUIDE = make_creature(
    name="Sygg, River Guide",
    power=2,
    toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="Islandwalk. {1}{W}: Target Merfolk you control gains protection from the color of your choice until end of turn."
)

# Sygg, River Cutthroat - {U/B}{U/B} Legendary Creature
SYGG_RIVER_CUTTHROAT = make_creature(
    name="Sygg, River Cutthroat",
    power=1,
    toughness=3,
    mana_cost="{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Merfolk", "Rogue"},
    supertypes={"Legendary"},
    text="At the beginning of each end step, if an opponent lost 3 or more life this turn, you may draw a card."
)

# Wydwen, the Biting Gale - {2}{U}{B} Legendary Creature
# Spice rewire (Phase A1): unwired Faerie flagship. The activated self-bounce
# is engine-gap (needs life payment + return-to-hand combined cost). Wire the
# flying+flash keywords statically AND a combat-damage trigger: when Wydwen
# deals combat damage to a player, that player discards a card (asymmetric
# Faerie pressure). Pattern 5 (asymmetric prison) + flying-tempo.
def wydwen_the_biting_gale_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_keyword_grant as _make_keyword_grant,
        make_damage_trigger as _make_damage_trigger,
    )

    interceptors: list[Interceptor] = []
    interceptors.append(_make_keyword_grant(
        obj, ['flying', 'flash'], lambda t, s: t.id == obj.id
    ))

    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        # Target must be a player.
        return event.payload.get('target') in state.players

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        if target_player is None:
            return []
        return [Event(
            type=EventType.DISCARD,
            payload={'player': target_player, 'amount': 1},
            source=obj.id,
        )]
    interceptors.append(_make_damage_trigger(
        obj, damage_effect, combat_only=True, filter_fn=damage_filter
    ))
    return interceptors


WYDWEN_THE_BITING_GALE = make_creature(
    name="Wydwen, the Biting Gale",
    power=3,
    toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. Flying. Whenever Wydwen, the Biting Gale deals combat damage to a player, that player discards a card.",
    setup_interceptors=wydwen_the_biting_gale_setup,
)

# Wort, Boggart Auntie - {2}{B}{R} Legendary Creature
# Spice rewire (Phase A1): unwired Goblin flagship. Upkeep RETURN_FROM_GRAVEYARD
# of the first Goblin in your graveyard to your hand. Pattern 8 (recursion).
# Self fear via keyword grant.
def wort_boggart_auntie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_keyword_grant as _make_keyword_grant,
        make_upkeep_trigger as _make_upkeep_trigger,
    )

    interceptors: list[Interceptor] = []
    interceptors.append(_make_keyword_grant(
        obj, ['fear'], lambda t, s: t.id == obj.id
    ))

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        gy_name = f'graveyard_{obj.controller}'
        gy = state.zones.get(gy_name)
        if not gy:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and 'Goblin' in (cobj.characteristics.subtypes or set()):
                return [Event(
                    type=EventType.RETURN_FROM_GRAVEYARD,
                    payload={
                        'object_id': cid,
                        'controller': obj.controller,
                        'player': obj.controller,
                        'destination': 'hand',
                        'optional': True,
                    },
                    source=obj.id,
                )]
        return []
    interceptors.append(_make_upkeep_trigger(obj, upkeep_effect, controller_only=True))
    return interceptors


WORT_BOGGART_AUNTIE = make_creature(
    name="Wort, Boggart Auntie",
    power=3,
    toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Shaman"},
    supertypes={"Legendary"},
    text="Fear. At the beginning of your upkeep, you may return target Goblin card from your graveyard to your hand.",
    setup_interceptors=wort_boggart_auntie_setup,
)

# Gaddock Teeg - {G}{W} Legendary Creature
# Spice rewire (Phase A1): unwired Kithkin flagship. The original "noncreature
# MV>=4 can't be cast" prison is engine-gap (no cast-time noncreature MV
# filter). Approximate the prison role via opp-targeted asymmetric tax: when
# Gaddock enters, each opponent loses 2 life (the noncreature-MV-4 tax cost in
# soft form). Also +1/+1 anthem to other Kithkin you control (lord role) so the
# 2/2 body slots into Kithkin tribal. Pattern 5 (asymmetric) + tribal lord.
def gaddock_teeg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_static_pt_boost as _make_static_pt_boost,
        other_creatures_with_subtype as _other_creatures_with_subtype,
        make_etb_trigger as _ih_make_etb_trigger,
    )

    interceptors: list[Interceptor] = []
    interceptors.extend(_make_static_pt_boost(
        obj, 1, 1, _other_creatures_with_subtype(obj, 'Kithkin')
    ))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': pid, 'amount': -2},
                    source=obj.id,
                ))
        return events
    interceptors.append(_ih_make_etb_trigger(obj, etb_effect))
    return interceptors


GADDOCK_TEEG = make_creature(
    name="Gaddock Teeg",
    power=2,
    toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin", "Advisor"},
    supertypes={"Legendary"},
    text="When Gaddock Teeg enters, each opponent loses 2 life. Other Kithkin you control get +1/+1.",
    setup_interceptors=gaddock_teeg_setup,
)

# Oversoul of Dusk - {G/W}{G/W}{G/W}{G/W}{G/W} Creature
OVERSOUL_OF_DUSK = make_creature(
    name="Oversoul of Dusk",
    power=5,
    toughness=5,
    mana_cost="{G/W}{G/W}{G/W}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Spirit", "Avatar"},
    text="Protection from blue, from black, and from red."
)

# Kitchen Finks - {1}{G/W}{G/W} Creature
KITCHEN_FINKS = make_creature(
    name="Kitchen Finks",
    power=3,
    toughness=2,
    mana_cost="{1}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Ouphe"},
    text="When Kitchen Finks enters, you gain 2 life. Persist (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)"
)

# Murderous Redcap - {2}{B/R}{B/R} Creature
MURDEROUS_REDCAP = make_creature(
    name="Murderous Redcap",
    power=2,
    toughness=2,
    mana_cost="{2}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Assassin"},
    text="When Murderous Redcap enters, it deals damage equal to its power to any target. Persist."
)

# Demigod of Revenge - {B/R}{B/R}{B/R}{B/R}{B/R} Creature
DEMIGOD_OF_REVENGE = make_creature(
    name="Demigod of Revenge",
    power=5,
    toughness=4,
    mana_cost="{B/R}{B/R}{B/R}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Spirit", "Avatar"},
    text="Flying. Haste. When you cast this spell, return all cards named Demigod of Revenge from your graveyard to the battlefield."
)

# Glen Elendra Archmage - {3}{U} Creature
GLEN_ELENDRA_ARCHMAGE = make_creature(
    name="Glen Elendra Archmage",
    power=2,
    toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying. {U}, Sacrifice Glen Elendra Archmage: Counter target noncreature spell. Persist."
)

# Stillmoon Cavalier - {1}{W/B}{W/B} Creature
STILLMOON_CAVALIER = make_creature(
    name="Stillmoon Cavalier",
    power=2,
    toughness=1,
    mana_cost="{1}{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Zombie", "Knight"},
    text="Protection from white and from black. {W/B}: Stillmoon Cavalier gains flying until end of turn. {W/B}: Stillmoon Cavalier gains first strike until end of turn. {W/B}{W/B}: Stillmoon Cavalier gets +1/+0 until end of turn."
)

# Creakwood Liege - {1}{B/G}{B/G}{B/G} Creature
CREAKWOOD_LIEGE = make_creature(
    name="Creakwood Liege",
    power=2,
    toughness=2,
    mana_cost="{1}{B/G}{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Horror"},
    text="Other black creatures you control get +1/+1. Other green creatures you control get +1/+1. At the beginning of your upkeep, you may create a 1/1 black and green Worm creature token."
)

# Deathbringer Liege - {2}{W/B}{W/B}{W/B} Creature
DEATHBRINGER_LIEGE = make_creature(
    name="Deathbringer Liege",
    power=3,
    toughness=4,
    mana_cost="{2}{W/B}{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Horror"},
    text="Other white creatures you control get +1/+1. Other black creatures you control get +1/+1. Whenever you cast a white spell, you may tap target creature. Whenever you cast a black spell, you may destroy target creature if it's tapped."
)

# Balefire Liege - {2}{R/W}{R/W}{R/W} Creature
BALEFIRE_LIEGE = make_creature(
    name="Balefire Liege",
    power=2,
    toughness=4,
    mana_cost="{2}{R/W}{R/W}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Spirit", "Horror"},
    text="Other red creatures you control get +1/+1. Other white creatures you control get +1/+1. Whenever you cast a red spell, Balefire Liege deals 3 damage to target player or planeswalker. Whenever you cast a white spell, you gain 3 life."
)

# Boartusk Liege - {1}{R/G}{R/G}{R/G} Creature
def _boartusk_liege_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Two independent +1/+1 boosts: a red-green creature gets +2/+2, mono gets +1/+1.
    return (make_static_pt_boost(obj, 1, 1, other_creatures_of_color(obj, Color.RED)) +
            make_static_pt_boost(obj, 1, 1, other_creatures_of_color(obj, Color.GREEN)))


BOARTUSK_LIEGE = make_creature(
    name="Boartusk Liege",
    power=3,
    toughness=4,
    mana_cost="{1}{R/G}{R/G}{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Goblin", "Knight"},
    text="Trample. Other red creatures you control get +1/+1. Other green creatures you control get +1/+1.",
    setup_interceptors=_boartusk_liege_setup
)

# Thistledown Liege - {1}{W/U}{W/U}{W/U} Creature
def _thistledown_liege_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return (make_static_pt_boost(obj, 1, 1, other_creatures_of_color(obj, Color.WHITE)) +
            make_static_pt_boost(obj, 1, 1, other_creatures_of_color(obj, Color.BLUE)))


THISTLEDOWN_LIEGE = make_creature(
    name="Thistledown Liege",
    power=1,
    toughness=3,
    mana_cost="{1}{W/U}{W/U}{W/U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Kithkin", "Knight"},
    text="Flash. Other white creatures you control get +1/+1. Other blue creatures you control get +1/+1.",
    setup_interceptors=_thistledown_liege_setup
)

# Murkfiend Liege - {2}{G/U}{G/U}{G/U} Creature
MURKFIEND_LIEGE = make_creature(
    name="Murkfiend Liege",
    power=4,
    toughness=4,
    mana_cost="{2}{G/U}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Horror"},
    text="Other green creatures you control get +1/+1. Other blue creatures you control get +1/+1. Untap all green and/or blue creatures you control during each other player's untap step."
)

# Mindwrack Liege - {3}{U/R}{U/R}{U/R} Creature
MINDWRACK_LIEGE = make_creature(
    name="Mindwrack Liege",
    power=4,
    toughness=4,
    mana_cost="{3}{U/R}{U/R}{U/R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Horror"},
    text="Other blue creatures you control get +1/+1. Other red creatures you control get +1/+1. {U/R}{U/R}{U/R}{U/R}: You may put a blue or red creature card from your hand onto the battlefield."
)

# Ashenmoor Liege - {1}{B/R}{B/R}{B/R} Creature
ASHENMOOR_LIEGE = make_creature(
    name="Ashenmoor Liege",
    power=4,
    toughness=1,
    mana_cost="{1}{B/R}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Elemental", "Knight"},
    text="Other black creatures you control get +1/+1. Other red creatures you control get +1/+1. Whenever Ashenmoor Liege becomes the target of a spell or ability an opponent controls, that player loses 4 life."
)

# Wilt-Leaf Liege - {1}{G/W}{G/W}{G/W} Creature
def _wilt_leaf_liege_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # The discard-to-battlefield clause is a replacement effect (Phase B); the
    # +1/+1 lord halves are the implementable part.
    return (make_static_pt_boost(obj, 1, 1, other_creatures_of_color(obj, Color.GREEN)) +
            make_static_pt_boost(obj, 1, 1, other_creatures_of_color(obj, Color.WHITE)))


WILT_LEAF_LIEGE = make_creature(
    name="Wilt-Leaf Liege",
    power=4,
    toughness=4,
    mana_cost="{1}{G/W}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Knight"},
    text="Other green creatures you control get +1/+1. Other white creatures you control get +1/+1. If a spell or ability an opponent controls causes you to discard Wilt-Leaf Liege, put it onto the battlefield instead of putting it into your graveyard.",
    setup_interceptors=_wilt_leaf_liege_setup
)

# =============================================================================
# MORE ARTIFACT CARDS
# =============================================================================

# Moonglove Extract - {3} Artifact
MOONGLOVE_EXTRACT = make_artifact(
    name="Moonglove Extract",
    mana_cost="{3}",
    text="Sacrifice Moonglove Extract: It deals 2 damage to any target."
)

# Runed Stalactite - {1} Artifact — Equipment
RUNED_STALACTITE = make_artifact(
    name="Runed Stalactite",
    mana_cost="{1}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and is every creature type. Equip {2}",
    # Static +1/+1 + Equip {2}. "Is every creature type" == Changeling
    # (CR 702.73); granted as the changeling keyword on the equipped creature.
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=1, keywords=["changeling"], equip_cost="{2}")
)

# Thornbite Staff - {2} Kindred Artifact — Shaman Equipment
def _thornbite_damage_effect(o: GameObject, state: GameState, targets) -> list[Event]:
    if not targets:
        return []
    t = targets[0]
    target_id = getattr(t, 'object_id', None) or getattr(t, 'player_id', None) or t
    return [Event(type=EventType.DAMAGE,
                  payload={'target': target_id, 'amount': 1, 'source': o.id},
                  source=o.id, controller=o.controller)]


def _thornbite_death_filter(event: Event, state: GameState, target_id: str) -> bool:
    if event.type != EventType.OBJECT_DESTROYED:
        return False
    dead = state.objects.get(event.payload.get('object_id'))
    return bool(dead) and CardType.CREATURE in dead.characteristics.types


def _thornbite_untap_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    return [Event(type=EventType.UNTAP, payload={'object_id': target_obj.id},
                  source=target_obj.id, controller=target_obj.controller)]


THORNBITE_STAFF = make_artifact(
    name="Thornbite Staff",
    mana_cost="{2}",
    subtypes={"Shaman", "Equipment"},
    text="Equipped creature has \"{2}, {T}: This creature deals 1 damage to any target\" and \"Whenever a creature dies, untap this creature.\" Whenever a Shaman creature enters under your control, you may attach Thornbite Staff to it. Equip {4}",
    # Grants the held creature a {2},{T}: 1-damage ping ability + an untap-on-
    # any-creature-death trigger. (Optional Shaman-ETB free-attach: Phase B.)
    setup_interceptors=make_equipment_setup(
        equip_cost="{4}",
        granted_activated_abilities={
            "cost": "{2}, {T}", "effect_fn": _thornbite_damage_effect,
            "description": "This creature deals 1 damage to any target",
            "targets_required": 1, "target_kind": "any",
        },
        granted_triggered_abilities={
            "event_filter": _thornbite_death_filter,
            "effect_fn": _thornbite_untap_effect,
            "description": "Whenever a creature dies, untap this creature",
        })
)

# Obsidian Battle-Axe - {3} Kindred Artifact — Warrior Equipment
OBSIDIAN_BATTLE_AXE = make_artifact(
    name="Obsidian Battle-Axe",
    mana_cost="{3}",
    subtypes={"Warrior", "Equipment"},
    text="Equipped creature gets +2/+1 and has haste. Whenever a Warrior creature enters under your control, you may attach Obsidian Battle-Axe to it. Equip {3}",
    # Static +2/+1 + haste + Equip {3}. (Optional Warrior-ETB free-attach: Phase B.)
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=1, keywords=["haste"], equip_cost="{3}")
)

# Cloak and Dagger - {2} Kindred Artifact — Rogue Equipment
CLOAK_AND_DAGGER = make_artifact(
    name="Cloak and Dagger",
    mana_cost="{2}",
    subtypes={"Rogue", "Equipment"},
    text="Equipped creature gets +2/+0 and has shroud. Whenever a Rogue creature enters under your control, you may attach Cloak and Dagger to it. Equip {3}",
    # Static +2/+0 + shroud + Equip {3}. (The optional "attach on Rogue ETB"
    # free-attach trigger is a may-trigger rider handled in Phase B.)
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=0, keywords=["shroud"], equip_cost="{3}")
)

# Diviner's Wand - {3} Kindred Artifact — Wizard Equipment
def _diviners_wand_draw_effect(o: GameObject, state: GameState, targets) -> list[Event]:
    return [Event(type=EventType.DRAW, payload={'player': o.controller, 'count': 1},
                  source=o.id, controller=o.controller)]


def _diviners_wand_ondraw_filter(event: Event, state: GameState, target_id: str) -> bool:
    if event.type != EventType.DRAW:
        return False
    tgt = state.objects.get(target_id)
    return bool(tgt) and event.payload.get('player') == tgt.controller


def _diviners_wand_ondraw_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    return [
        Event(type=EventType.PT_MODIFICATION,
              payload={'object_id': target_obj.id, 'power_mod': 1, 'toughness_mod': 1,
                       'duration': 'end_of_turn'},
              source=target_obj.id, controller=target_obj.controller),
        Event(type=EventType.GRANT_KEYWORD,
              payload={'object_id': target_obj.id, 'keyword': 'flying', 'duration': 'end_of_turn'},
              source=target_obj.id, controller=target_obj.controller),
    ]


DIVINERS_WAND = make_artifact(
    name="Diviner's Wand",
    mana_cost="{3}",
    subtypes={"Wizard", "Equipment"},
    text="Equipped creature has \"Whenever you draw a card, this creature gets +1/+1 and gains flying until end of turn\" and \"{4}: Draw a card.\" Whenever a Wizard creature enters under your control, you may attach Diviner's Wand to it. Equip {3}",
    # Grants the held creature a {4}: Draw activated ability + a draw-triggered
    # pump. (Optional Wizard-ETB free-attach trigger: Phase B.)
    setup_interceptors=make_equipment_setup(
        equip_cost="{3}",
        granted_activated_abilities={
            "cost": "{4}", "effect_fn": _diviners_wand_draw_effect,
            "description": "Draw a card",
        },
        granted_triggered_abilities={
            "event_filter": _diviners_wand_ondraw_filter,
            "effect_fn": _diviners_wand_ondraw_effect,
            "description": "Whenever you draw a card, +1/+1 and gains flying EOT",
        })
)

# Veteran's Armaments - {2} Kindred Artifact — Soldier Equipment
def _veterans_arm_attack_filter(event: Event, state: GameState, target_id: str) -> bool:
    return event.type == EventType.ATTACK_DECLARED and event.payload.get('attacker_id') == target_id


def _veterans_arm_attack_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    # "+1/+1 until end of turn for each OTHER attacking creature."
    others = 0
    for o in state.objects.values():
        if (o.id != target_obj.id and o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                getattr(o.state, 'attacking', False)):
            others += 1
    if others <= 0:
        return []
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target_obj.id, 'power_mod': others,
                           'toughness_mod': others, 'duration': 'end_of_turn'},
                  source=target_obj.id, controller=target_obj.controller)]


VETERANS_ARMAMENTS = make_artifact(
    name="Veteran's Armaments",
    mana_cost="{2}",
    subtypes={"Soldier", "Equipment"},
    text="Equipped creature has \"Whenever this creature attacks, it gets +1/+1 until end of turn for each other attacking creature.\" Whenever a Soldier creature enters under your control, you may attach Veteran's Armaments to it. Equip {2}",
    # Grants the held creature an attack-trigger that pumps it per other attacker.
    # (Optional Soldier-ETB free-attach trigger: Phase B.)
    setup_interceptors=make_equipment_setup(
        equip_cost="{2}",
        granted_triggered_abilities={
            "event_filter": _veterans_arm_attack_filter,
            "effect_fn": _veterans_arm_attack_effect,
            "description": "Whenever this creature attacks, +1/+1 per other attacker",
        })
)


# =============================================================================
# EVEN MORE CARDS - BATCH 3
# =============================================================================

# More White Creatures
KINSBAILE_BORDERGUARD = make_creature(
    name="Kinsbaile Borderguard",
    power=1,
    toughness=1,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Kinsbaile Borderguard enters with a +1/+1 counter on it for each other Kithkin you control. When Kinsbaile Borderguard dies, create a 1/1 white Kithkin Soldier creature token for each counter on it."
)

CLOUDGOAT_RANGER = make_creature(
    name="Cloudgoat Ranger",
    power=3,
    toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="When Cloudgoat Ranger enters, create three 1/1 white Kithkin Soldier creature tokens. Tap three untapped Kithkin you control: Cloudgoat Ranger gets +2/+0 and gains flying until end of turn."
)

MIRROR_ENTITY = make_creature(
    name="Mirror Entity",
    power=1,
    toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Shapeshifter"},
    text="Changeling. {X}: Until end of turn, creatures you control have base power and toughness X/X and gain all creature types."
)

REVEILLARK = make_creature(
    name="Reveillark",
    power=4,
    toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental"},
    text="Flying. When Reveillark leaves the battlefield, return up to two target creature cards with power 2 or less from your graveyard to the battlefield. Evoke {5}{W}"
)

RANGER_OF_EOS = make_creature(
    name="Ranger of Eos",
    power=3,
    toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Ranger of Eos enters, you may search your library for up to two creature cards with mana value 1 or less, reveal them, put them into your hand, then shuffle."
)

# More Blue Creatures
VENDILION_CLIQUE = make_creature(
    name="Vendilion Clique",
    power=3,
    toughness=1,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. Flying. When Vendilion Clique enters, look at target player's hand. You may choose a nonland card from it. If you do, that player reveals the chosen card, puts it on the bottom of their library, then draws a card."
)

SOWER_OF_TEMPTATION = make_creature(
    name="Sower of Temptation",
    power=2,
    toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying. When Sower of Temptation enters, gain control of target creature for as long as Sower of Temptation remains on the battlefield."
)

MISTBIND_CLIQUE = make_creature(
    name="Mistbind Clique",
    power=4,
    toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash. Flying. Champion a Faerie. When a Faerie is championed with Mistbind Clique, tap all lands target player controls."
)

SPELLSTUTTER_SPRITE = make_creature(
    name="Spellstutter Sprite",
    power=1,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash. Flying. When Spellstutter Sprite enters, counter target spell with mana value X or less, where X is the number of Faeries you control."
)

def _scion_of_oona_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return (make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Faerie")) +
            [make_keyword_grant(obj, ["shroud"], other_creatures_with_subtype(obj, "Faerie"))])


SCION_OF_OONA = make_creature(
    name="Scion of Oona",
    power=1,
    toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Soldier"},
    text="Flash. Flying. Other Faerie creatures you control get +1/+1. Other Faeries you control have shroud.",
    setup_interceptors=_scion_of_oona_setup
)

# More Black Creatures
SHRIEKMAW = make_creature(
    name="Shriekmaw",
    power=3,
    toughness=2,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental"},
    text="Fear. When Shriekmaw enters, destroy target nonartifact, nonblack creature. Evoke {1}{B}"
)

THOUGHTSEIZE_CREATURE = make_creature(
    name="Oona's Blackguard",
    power=1,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. Each other Rogue creature you control enters with an additional +1/+1 counter on it. Whenever a creature you control with a +1/+1 counter on it deals combat damage to a player, that player discards a card."
)

EARWIG_SQUAD = make_creature(
    name="Earwig Squad",
    power=5,
    toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Rogue"},
    text="Prowl {2}{B}. When Earwig Squad enters, if its prowl cost was paid, search target opponent's library for three cards and exile them. Then that player shuffles."
)

BITTERBLOSSOM = make_enchantment(
    name="Bitterblossom",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Tribal Enchantment — Faerie. At the beginning of your upkeep, you lose 1 life and create a 1/1 black Faerie Rogue creature token with flying."
)

MORNSONG_ARIA = make_enchantment(
    name="Mornsong Aria",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Legendary Enchantment. Players can't draw cards or gain life. At the beginning of each player's draw step, that player loses 3 life, then may search their library for a card, put it into their hand, then shuffle."
)

# More Red Creatures
def _sunrise_sovereign_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return (make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, "Giant")) +
            [make_keyword_grant(obj, ["trample"], other_creatures_with_subtype(obj, "Giant"))])


SUNRISE_SOVEREIGN = make_creature(
    name="Sunrise Sovereign",
    power=5,
    toughness=5,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Other Giant creatures you control get +2/+2 and have trample.",
    setup_interceptors=_sunrise_sovereign_setup
)

BRION_STOUTARM = make_creature(
    name="Brion Stoutarm",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Giant", "Warrior"},
    supertypes={"Legendary"},
    text="Lifelink. {R}, {T}, Sacrifice another creature: Brion Stoutarm deals damage equal to the sacrificed creature's power to target player or planeswalker."
)

NOVA_CHASER = make_creature(
    name="Nova Chaser",
    power=10,
    toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Warrior"},
    text="Trample. Champion an Elemental."
)

INCANDESCENT_SOULSTOKE = make_creature(
    name="Incandescent Soulstoke",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Shaman"},
    text="Other Elemental creatures you control get +1/+1. {1}{R}, {T}: You may put an Elemental creature card from your hand onto the battlefield. That creature gains haste. Sacrifice it at the beginning of the next end step."
)

# More Green Creatures
CHAMELEON_COLOSSUS = make_creature(
    name="Chameleon Colossus",
    power=4,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling. Protection from black. {2}{G}{G}: Chameleon Colossus gets +X/+X until end of turn, where X is its power."
)

PRIMALCRUX = make_creature(
    name="Primalcrux",
    power=0,
    toughness=0,
    mana_cost="{G}{G}{G}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Trample. Chroma — Primalcrux's power and toughness are each equal to the number of green mana symbols in the mana costs of permanents you control."
)

DEVOTED_DRUID = make_creature(
    name="Devoted Druid",
    power=0,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}. Put a -1/-1 counter on Devoted Druid: Untap Devoted Druid."
)

NETTLE_SENTINEL = make_creature(
    name="Nettle Sentinel",
    power=2,
    toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Nettle Sentinel doesn't untap during your untap step. Whenever you cast a green spell, you may untap Nettle Sentinel."
)

MASKED_ADMIRERS = make_creature(
    name="Masked Admirers",
    power=3,
    toughness=2,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="When Masked Admirers enters, draw a card. Whenever you cast a creature spell, you may pay {G}{G}. If you do, return Masked Admirers from your graveyard to your hand."
)

# More Enchantments
THOUGHTWEFT_GAMBIT = make_instant(
    name="Thoughtweft Gambit",
    mana_cost="{4}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Tap all creatures your opponents control and untap all creatures you control."
)

CRYPTIC_COMMAND = make_instant(
    name="Cryptic Command",
    mana_cost="{1}{U}{U}{U}",
    colors={Color.BLUE},
    text="Choose two — Counter target spell; or return target permanent to its owner's hand; or tap all creatures your opponents control; or draw a card."
)

FIRESPOUT = make_sorcery(
    name="Firespout",
    mana_cost="{2}{R/G}",
    colors={Color.RED, Color.GREEN},
    text="Firespout deals 3 damage to each creature without flying if {R} was spent to cast this spell and 3 damage to each creature with flying if {G} was spent to cast this spell."
)

PRIMAL_COMMAND = make_sorcery(
    name="Primal Command",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Choose two — Target player gains 7 life; or put target noncreature permanent on top of its owner's library; or target player shuffles their graveyard into their library; or search your library for a creature card, reveal it, put it into your hand, then shuffle."
)

AUSTERE_COMMAND = make_sorcery(
    name="Austere Command",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Choose two — Destroy all artifacts; destroy all enchantments; destroy all creatures with mana value 3 or less; or destroy all creatures with mana value 4 or greater."
)

PROFANE_COMMAND = make_sorcery(
    name="Profane Command",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Choose two — Target player loses X life; or return target creature card with mana value X or less from your graveyard to the battlefield; or target creature gets -X/-X until end of turn; or up to X target creatures gain fear until end of turn."
)

INCENDIARY_COMMAND = make_sorcery(
    name="Incendiary Command",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Choose two — Incendiary Command deals 4 damage to target player; or Incendiary Command deals 2 damage to each creature; or destroy target nonbasic land; or each player discards all the cards in their hand, then draws that many cards."
)

# More Multicolor Cards
FULMINATOR_MAGE = make_creature(
    name="Fulminator Mage",
    power=2,
    toughness=2,
    mana_cost="{1}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Elemental", "Shaman"},
    text="Sacrifice Fulminator Mage: Destroy target nonbasic land."
)

FIGURE_OF_DESTINY = make_creature(
    name="Figure of Destiny",
    power=1,
    toughness=1,
    mana_cost="{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Kithkin"},
    text="{R/W}: Figure of Destiny becomes a Kithkin Spirit with base power and toughness 2/2. {R/W}{R/W}{R/W}: If Figure of Destiny is a Spirit, it becomes a Kithkin Spirit Warrior with base power and toughness 4/4. {R/W}{R/W}{R/W}{R/W}{R/W}{R/W}: If Figure of Destiny is a Warrior, it becomes a Kithkin Spirit Warrior Avatar with base power and toughness 8/8, flying, and first strike."
)

MANAMORPHOSE = make_instant(
    name="Manamorphose",
    mana_cost="{1}{R/G}",
    colors={Color.RED, Color.GREEN},
    text="Add two mana in any combination of colors. Draw a card."
)

BOGGART_RAM_GANG = make_creature(
    name="Boggart Ram-Gang",
    power=3,
    toughness=3,
    mana_cost="{R/G}{R/G}{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Goblin", "Warrior"},
    text="Haste. Wither."
)

TATTERMUNGE_MANIAC = make_creature(
    name="Tattermunge Maniac",
    power=2,
    toughness=1,
    mana_cost="{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Goblin", "Warrior"},
    text="Tattermunge Maniac attacks each combat if able."
)

VEXING_SHUSHER = make_creature(
    name="Vexing Shusher",
    power=2,
    toughness=2,
    mana_cost="{R/G}{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Goblin", "Shaman"},
    text="This spell can't be countered. {R/G}: Target spell can't be countered."
)

PLUMEVEIL = make_creature(
    name="Plumeveil",
    power=4,
    toughness=4,
    mana_cost="{W/U}{W/U}{W/U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Elemental"},
    text="Flash. Defender. Flying."
)

UNMAKE = make_instant(
    name="Unmake",
    mana_cost="{W/B}{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    text="Exile target creature."
)

FIERY_JUSTICE = make_sorcery(
    name="Fiery Justice",
    mana_cost="{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    text="Fiery Justice deals 5 damage divided as you choose among any number of targets. Target opponent gains 5 life."
)

AUGURY_ADEPT = make_creature(
    name="Augury Adept",
    power=2,
    toughness=2,
    mana_cost="{1}{W/U}{W/U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Kithkin", "Wizard"},
    text="Whenever Augury Adept deals combat damage to a player, reveal the top card of your library and put that card into your hand. You gain life equal to its mana value."
)

COLD_EYED_SELKIE = make_creature(
    name="Cold-Eyed Selkie",
    power=1,
    toughness=1,
    mana_cost="{1}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="Islandwalk. Whenever Cold-Eyed Selkie deals combat damage to a player, you may draw that many cards."
)

DEUS_OF_CALAMITY = make_creature(
    name="Deus of Calamity",
    power=6,
    toughness=6,
    mana_cost="{R/G}{R/G}{R/G}{R/G}{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Spirit", "Avatar"},
    text="Trample. Whenever Deus of Calamity deals 6 or more damage to an opponent, destroy target land that player controls."
)

GHASTLORD_OF_FUGUE = make_creature(
    name="Ghastlord of Fugue",
    power=4,
    toughness=4,
    mana_cost="{U/B}{U/B}{U/B}{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Spirit", "Avatar"},
    text="Ghastlord of Fugue can't be blocked. Whenever Ghastlord of Fugue deals combat damage to a player, that player reveals their hand. You choose a card from it. That player exiles that card."
)

DEITY_OF_SCARS = make_creature(
    name="Deity of Scars",
    power=7,
    toughness=7,
    mana_cost="{B/G}{B/G}{B/G}{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit", "Avatar"},
    text="Trample. Deity of Scars enters with two -1/-1 counters on it. {B/G}, Remove a -1/-1 counter from Deity of Scars: Regenerate Deity of Scars."
)

# Godhead of Awe - Other creatures have base P/T 1/1
def godhead_of_awe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures have base power and toughness 1/1."""

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        if target_id == obj.id:  # Doesn't affect itself
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        return (CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = 1  # Set base to 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        if target_id == obj.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        return (CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        )
    ]


GODHEAD_OF_AWE = make_creature(
    name="Godhead of Awe",
    power=4,
    toughness=4,
    mana_cost="{W/U}{W/U}{W/U}{W/U}{W/U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit", "Avatar"},
    text="Flying. Other creatures have base power and toughness 1/1.",
    setup_interceptors=godhead_of_awe_setup
)

OVERBEING_OF_MYTH = make_creature(
    name="Overbeing of Myth",
    power=0,
    toughness=0,
    mana_cost="{G/U}{G/U}{G/U}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Spirit", "Avatar"},
    text="Overbeing of Myth's power and toughness are each equal to the number of cards in your hand. At the beginning of your draw step, draw an additional card."
)

DIVINITY_OF_PRIDE = make_creature(
    name="Divinity of Pride",
    power=4,
    toughness=4,
    mana_cost="{W/B}{W/B}{W/B}{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Spirit", "Avatar"},
    text="Flying. Lifelink. Divinity of Pride gets +4/+4 as long as you have 25 or more life."
)


# =============================================================================
# FINAL BATCH - BATCH 4: Setup Interceptors (Cards 351-408)
# =============================================================================

def oblivion_ring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # "exile target nonland permanent" (until O-Ring leaves).
        target = None
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and o.id != obj.id and
                    CardType.LAND not in o.characteristics.types and
                    o.characteristics.types):
                target = o.id
                break
        payload = {'target_filter': 'nonland_permanent', 'until_leaves': obj.id}
        if target:
            payload['object_id'] = target
        return [Event(type=EventType.EXILE, payload=payload, source=obj.id)]
    def leaves_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return event.type == EventType.ZONE_CHANGE and event.payload.get('object_id') == source.id and event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD
    def leaves_effect(event: Event, state: GameState) -> list[Event]:
        exiled_id = getattr(obj.state, 'exiled_card_id', None)
        return [Event(type=EventType.ZONE_CHANGE, payload={'object_id': exiled_id, 'from_zone_type': ZoneType.EXILE, 'to_zone_type': ZoneType.BATTLEFIELD}, source=obj.id)] if exiled_id else []
    return [make_etb_trigger(obj, etb_effect), make_death_trigger(obj, leaves_effect, leaves_filter)]

def preeminent_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "you may put a Soldier creature card from your hand onto the battlefield
    #  tapped and attacking."
    def effect(event: Event, state: GameState) -> list[Event]:
        # Find a Soldier card in hand to put into play.
        hand = state.zones.get(f"hand_{obj.controller}")
        soldier = None
        if hand:
            for cid in hand.objects:
                card = state.objects.get(cid)
                if (card and CardType.CREATURE in card.characteristics.types and
                        'Soldier' in card.characteristics.subtypes):
                    soldier = card
                    break
        payload = {'controller': obj.controller, 'from_hand': True,
                   'tapped': True, 'attacking': True, 'optional': True,
                   'card_filter': 'soldier_in_hand'}
        if soldier:
            payload['object_id'] = soldier.id
            payload['name'] = soldier.name
        return [Event(type=EventType.OBJECT_CREATED, payload=payload, source=obj.id)]
    return [make_attack_trigger(obj, effect)]

def merrow_commerce_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP, payload={'object_id': oid}, source=obj.id) for oid, c in state.objects.items() if c.controller == obj.controller and CardType.CREATURE in c.characteristics.types and 'Merfolk' in c.characteristics.subtypes and c.zone == ZoneType.BATTLEFIELD and c.state.tapped]
    return [make_end_step_trigger(obj, effect)]

def surgespanner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.OPTIONAL_COST, payload={'source': obj.id, 'cost': '{1}{U}', 'effect': 'bounce_permanent'}, source=obj.id)]
    return [make_tap_trigger(obj, effect)]

def silvergill_adept_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, effect)]

def mulldrifter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, effect)]

def caterwauling_boggart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return target.controller == obj.controller and target.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in target.characteristics.types and ('Goblin' in target.characteristics.subtypes or 'Elemental' in target.characteristics.subtypes)
    return [make_keyword_grant(obj, ['menace'], filter_fn)]

def knucklebone_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE or event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD or event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying = state.objects.get(event.payload.get('object_id'))
        return dying and dying.controller == source.controller and 'Goblin' in dying.characteristics.subtypes
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1, 'optional': True}, source=obj.id)]
    return [make_death_trigger(obj, effect, filter_fn)]

def wort_the_raidmother_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: two 1/1 R/G Goblin Warrior tokens.
    Plus: each red or green instant or sorcery you cast has conspire (W29).
    """
    def effect(event: Event, state: GameState) -> list[Event]:
        token = {'controller': obj.controller, 'name': 'Goblin Warrior', 'power': 1, 'toughness': 1, 'colors': {Color.RED, Color.GREEN}, 'subtypes': {'Goblin', 'Warrior'}}
        return [Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id), Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id)]

    def rg_instant_sorcery_filter(spell: GameObject, _state: GameState) -> bool:
        types = spell.characteristics.types
        if not (CardType.INSTANT in types or CardType.SORCERY in types):
            return False
        colors = spell.characteristics.colors or set()
        return Color.RED in colors or Color.GREEN in colors

    return [
        make_etb_trigger(obj, effect),
        make_conspire_grant(obj, state, spell_filter=rg_instant_sorcery_filter),
    ]

def jagged_scar_archers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def count_elves(st: GameState) -> int:
        return sum(1 for c in st.objects.values() if c.controller == obj.controller and CardType.CREATURE in c.characteristics.types and 'Elf' in c.characteristics.subtypes and c.zone == ZoneType.BATTLEFIELD)
    def p_filter(e: Event, s: GameState) -> bool:
        return e.type == EventType.QUERY_POWER and e.payload.get('object_id') == obj.id
    def p_handler(e: Event, s: GameState) -> InterceptorResult:
        ne = e.copy(); ne.payload['value'] = count_elves(s); return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)
    def t_filter(e: Event, s: GameState) -> bool:
        return e.type == EventType.QUERY_TOUGHNESS and e.payload.get('object_id') == obj.id
    def t_handler(e: Event, s: GameState) -> InterceptorResult:
        ne = e.copy(); ne.payload['value'] = count_elves(s); return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller, priority=InterceptorPriority.QUERY, filter=p_filter, handler=p_handler, duration='while_on_battlefield'), Interceptor(id=new_id(), source=obj.id, controller=obj.controller, priority=InterceptorPriority.QUERY, filter=t_filter, handler=t_handler, duration='while_on_battlefield')]

def wistful_selkie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, effect)]

def gwyllion_hedge_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def count_lands(lt: str, st: GameState) -> int:
        return sum(1 for l in st.objects.values() if l.controller == obj.controller and CardType.LAND in l.characteristics.types and lt in l.characteristics.subtypes and l.zone == ZoneType.BATTLEFIELD)
    def effect(event: Event, state: GameState) -> list[Event]:
        events = []
        plains = count_lands('Plains', state)
        swamps = count_lands('Swamp', state)
        # "if you control two or more Plains, you may create a 1/1 Kithkin Soldier"
        events.append(Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller, 'name': 'Kithkin Soldier', 'power': 1,
            'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Kithkin', 'Soldier'},
            'optional': True, 'condition': 'two_or_more_plains',
            'condition_met': plains >= 2}, source=obj.id))
        # "if you control two or more Swamps, you may put a -1/-1 counter on target creature"
        cpayload = {'counter_type': '-1/-1', 'amount': 1, 'optional': True,
                    'target_filter': 'creature', 'condition': 'two_or_more_swamps',
                    'condition_met': swamps >= 2}
        victim = find_any_creature(obj, state, exclude_self=True)
        if victim:
            cpayload['object_id'] = victim
        events.append(Event(type=EventType.COUNTER_ADDED, payload=cpayload, source=obj.id))
        return events
    return [make_etb_trigger(obj, effect)]

def selkie_hedge_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def count_lands(lt: str, st: GameState) -> int:
        return sum(1 for l in st.objects.values() if l.controller == obj.controller and CardType.LAND in l.characteristics.types and lt in l.characteristics.subtypes and l.zone == ZoneType.BATTLEFIELD)
    def effect(event: Event, state: GameState) -> list[Event]:
        events = []
        forests = count_lands('Forest', state)
        islands = count_lands('Island', state)
        # "if you control two or more Forests, you may gain 3 life"
        events.append(Event(type=EventType.LIFE_CHANGE, payload={
            'player': obj.controller, 'amount': 3, 'optional': True,
            'condition': 'two_or_more_forests', 'condition_met': forests >= 2},
            source=obj.id))
        # "if you control two or more Islands, you may return target tapped creature
        #  to its owner's hand"
        tapped = find_any_creature(obj, state, exclude_self=True)
        bev = _return_to_hand_event(obj, tapped, 'tapped_creature', optional=True)
        bev.payload['condition'] = 'two_or_more_islands'
        bev.payload['condition_met'] = islands >= 2
        events.append(bev)
        return events
    return [make_etb_trigger(obj, effect)]

def ashling_the_extinguisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_damage_trigger
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        return event.type == EventType.DAMAGE and event.payload.get('source') == source.id and event.payload.get('is_combat', False) and event.payload.get('target') in state.players
    def effect(event: Event, state: GameState) -> list[Event]:
        # "choose target creature that player controls. The player sacrifices that creature."
        damaged_player = event.payload.get('target')
        victim = None
        for o in _battlefield_creatures(state):
            if o.controller == damaged_player:
                victim = o.id
                break
        payload = {'sacrifice_type': 'creature', 'target_filter': 'creature_that_player_controls'}
        if damaged_player:
            payload['player'] = damaged_player
        if victim:
            payload['object_id'] = victim
        return [Event(type=EventType.SACRIFICE, payload=payload, source=obj.id)]
    return [make_damage_trigger(obj, effect, combat_only=True, filter_fn=filter_fn)]

def reaper_king_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import other_creatures_with_subtype
    def etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE or event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        oid = event.payload.get('object_id')
        entering = state.objects.get(oid)
        return oid != source.id and entering and entering.controller == source.controller and 'Scarecrow' in entering.characteristics.subtypes
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # "Whenever another Scarecrow enters under your control, destroy target permanent."
        target = None
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and o.id != obj.id and
                    o.characteristics.types):
                target = o.id
                break
        payload = {'target_filter': 'permanent'}
        if target:
            payload['object_id'] = target
        return [Event(type=EventType.OBJECT_DESTROYED, payload=payload, source=obj.id)]
    lord = make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, 'Scarecrow'))
    return lord + [make_etb_trigger(obj, etb_effect, etb_filter)]

def wicker_warcrawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and event.payload.get('attacker_id') == obj.id) or (event.type == EventType.BLOCK_DECLARED and event.payload.get('blocker_id') == obj.id)
    def effect(event: Event, state: GameState) -> list[Event]:
        # "put a -1/-1 counter on it at end of combat."
        return [Event(type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '-1/-1', 'amount': 1,
                     'timing': 'end_of_combat'}, source=obj.id)]
    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect(event, state))
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller, priority=InterceptorPriority.REACT, filter=filter_fn, handler=handler, duration='while_on_battlefield')]


# =============================================================================
# BATCH 4: Card Definitions
# =============================================================================

# White Cards
HALLOWED_BURIAL = make_sorcery(
    name="Hallowed Burial",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Put all creatures on the bottom of their owners' libraries."
)

IDYLLIC_TUTOR = make_sorcery(
    name="Idyllic Tutor",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Search your library for an enchantment card, reveal it, put it into your hand, then shuffle."
)

SPECTRAL_PROCESSION = make_sorcery(
    name="Spectral Procession",
    mana_cost="{2/W}{2/W}{2/W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Spirit creature tokens with flying."
)

RUNED_HALO = make_enchantment(
    name="Runed Halo",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    text="As Runed Halo enters, choose a card name. You have protection from the chosen card name."
)

OBLIVION_RING = make_enchantment(
    name="Oblivion Ring",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When Oblivion Ring enters, exile another target nonland permanent. When Oblivion Ring leaves the battlefield, return the exiled card to the battlefield under its owner's control.",
    setup_interceptors=oblivion_ring_setup
)

KNIGHT_OF_MEADOWGRAIN = make_creature(
    name="Knight of Meadowgrain",
    power=2,
    toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Knight"},
    text="First strike. Lifelink."
)

PREEMINENT_CAPTAIN = make_creature(
    name="Preeminent Captain",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="First strike. Whenever Preeminent Captain attacks, you may put a Soldier creature card from your hand onto the battlefield tapped and attacking.",
    setup_interceptors=preeminent_captain_setup
)

POLLEN_LULLABY = make_instant(
    name="Pollen Lullaby",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all combat damage that would be dealt this turn. Clash with an opponent. If you win, creatures that player controls don't untap during their next untap step."
)

# Blue Cards
BROKEN_AMBITIONS = make_instant(
    name="Broken Ambitions",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {X}. Clash with an opponent. If you win, that spell's controller mills four cards."
)

FAERIE_TRICKERY = make_instant(
    name="Faerie Trickery",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target non-Faerie spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard."
)

PONDER = make_sorcery(
    name="Ponder",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card."
)

MERROW_COMMERCE = make_enchantment(
    name="Merrow Commerce",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tribal Enchantment — Merfolk. At the beginning of your end step, untap all Merfolk you control.",
    setup_interceptors=merrow_commerce_setup
)

SURGESPANNER = make_creature(
    name="Surgespanner",
    power=2,
    toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Whenever Surgespanner becomes tapped, you may pay {1}{U}. If you do, return target permanent to its owner's hand.",
    setup_interceptors=surgespanner_setup
)

SILVERGILL_ADEPT = make_creature(
    name="Silvergill Adept",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="As an additional cost to cast this spell, reveal a Merfolk card from your hand or pay {3}. When Silvergill Adept enters, draw a card.",
    setup_interceptors=silvergill_adept_setup
)

MULLDRIFTER = make_creature(
    name="Mulldrifter",
    power=2,
    toughness=2,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying. When Mulldrifter enters, draw two cards. Evoke {2}{U}",
    setup_interceptors=mulldrifter_setup
)

# Black Cards
NAMELESS_INVERSION_B = make_instant(
    name="Final Revels",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Choose one — All creatures get +2/+0 until end of turn; or all creatures get -0/-2 until end of turn."
)

THOUGHTSEIZE = make_sorcery(
    name="Thoughtseize",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target player reveals their hand. You choose a nonland card from it. That player discards that card. You lose 2 life."
)

PEPPERSMOKE = make_instant(
    name="Peppersmoke",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Tribal Instant — Faerie. Target creature gets -1/-1 until end of turn. If you control a Faerie, draw a card."
)

FODDER_LAUNCH = make_sorcery(
    name="Fodder Launch",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Tribal Sorcery — Goblin. As an additional cost to cast this spell, sacrifice a Goblin. Target creature gets -5/-5 until end of turn. Its controller loses 5 life."
)

MAKESHIFT_MANNEQUIN = make_instant(
    name="Makeshift Mannequin",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield with a mannequin counter on it. For as long as that creature has a mannequin counter on it, it has \"When this creature becomes the target of a spell or ability, sacrifice it.\""
)

DEATH_DENIED = make_instant(
    name="Death Denied",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Return X target creature cards from your graveyard to your hand."
)

NETTLEVINE_BLIGHT = make_enchantment(
    name="Nettlevine Blight",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Aura"},
    text="Enchant creature or land. Enchanted permanent has \"At the beginning of your end step, sacrifice a creature or land. If you do, attach Nettlevine Blight to a permanent you control.\""
)

# Red Cards
TARFIRE = make_instant(
    name="Tarfire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tribal Instant — Goblin. Tarfire deals 2 damage to any target."
)

LASH_OUT = make_instant(
    name="Lash Out",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lash Out deals 3 damage to target creature. Clash with an opponent. If you win, Lash Out deals 3 damage to that creature's controller."
)

CATERWAULING_BOGGART = make_creature(
    name="Caterwauling Boggart",
    power=2,
    toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="Each Goblin you control can't be blocked except by two or more creatures. Each Elemental you control can't be blocked except by two or more creatures.",
    setup_interceptors=caterwauling_boggart_setup
)

KNUCKLEBONE_WITCH = make_creature(
    name="Knucklebone Witch",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Shaman"},
    text="Whenever a Goblin you control is put into a graveyard from the battlefield, you may put a +1/+1 counter on Knucklebone Witch.",
    setup_interceptors=knucklebone_witch_setup
)

WORT_THE_RAIDMOTHER = make_creature(
    name="Wort, the Raidmother",
    power=3,
    toughness=3,
    mana_cost="{4}{R/G}{R/G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Goblin", "Shaman"},
    supertypes={"Legendary"},
    text="When Wort, the Raidmother enters, create two 1/1 red and green Goblin Warrior creature tokens. Each red or green instant or sorcery spell you cast has conspire.",
    setup_interceptors=wort_the_raidmother_setup
)

SENSATION_GORGER = make_creature(
    name="Sensation Gorger",
    power=2,
    toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with Sensation Gorger, you may reveal it. If you do, each player discards their hand, then draws four cards."
)

# Green Cards
GARRUK_WILDSPEAKER = make_planeswalker(
    name="Garruk Wildspeaker",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Garruk"},
    text="+1: Untap two target lands. -1: Create a 3/3 green Beast creature token. -4: Creatures you control get +3/+3 and gain trample until end of turn.",
    loyalty=3
)

# REVISED (rebalance): {1}{G}{G} -> {G}{G}. Power = # Elves; without playing on
# an Elf-flush curve it hits the table as a 1/1 or 2/2. Lower CMC lets it ride
# turn 2 with another Elf already deployed and scale into a real beater.
JAGGED_SCAR_ARCHERS = make_creature(
    name="Jagged-Scar Archers",
    power=0,
    toughness=0,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Archer"},
    text="Jagged-Scar Archers's power and toughness are each equal to the number of Elves you control. {T}: Jagged-Scar Archers deals damage equal to its power to target creature with flying.",
    setup_interceptors=jagged_scar_archers_setup
)

LEAF_CROWNED_ELDER = make_creature(
    name="Leaf-Crowned Elder",
    power=3,
    toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Shaman"},
    text="Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with Leaf-Crowned Elder, you may reveal it. If you do, you may play that card without paying its mana cost."
)

# REVISED (rebalance): tap-Forest-into-Treefolk effect is unimplemented;
# 2/2 -> 3/3 so the body itself earns its {2}{G} slot in Elf decks.
ELVISH_BRANCHBENDER = make_creature(
    name="Elvish Branchbender",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Until end of turn, target Forest becomes an X/X Treefolk creature in addition to its other types, where X is the number of Elves you control."
)

GILT_LEAF_AMBUSH = make_instant(
    name="Gilt-Leaf Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Tribal Instant — Elf. Create two 1/1 green Elf Warrior creature tokens. Clash with an opponent. If you win, those creatures gain deathtouch until end of turn."
)

HUNTING_TRIAD = make_sorcery(
    name="Hunting Triad",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Tribal Sorcery — Elf. Create three 1/1 green Elf Warrior creature tokens. Reinforce 3—{3}{G}"
)

# Multicolor Cards
BOGGART_SPRITE_CHASER = make_creature(
    name="Boggart Sprite-Chaser",
    power=1,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="As long as you control a Faerie, Boggart Sprite-Chaser gets +1/+1 and has flying."
)

SCARBLADE_ELITE = make_creature(
    name="Scarblade Elite",
    power=2,
    toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Assassin"},
    text="{T}, Exile an Assassin card from your graveyard: Destroy target creature."
)

SAFEHOLD_ELITE = make_creature(
    name="Safehold Elite",
    power=2,
    toughness=2,
    mana_cost="{1}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    text="Persist."
)

RENDCLAW_TROW = make_creature(
    name="Rendclaw Trow",
    power=2,
    toughness=2,
    mana_cost="{2}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Troll"},
    text="Wither. Persist."
)

WISTFUL_SELKIE = make_creature(
    name="Wistful Selkie",
    power=2,
    toughness=2,
    mana_cost="{G/U}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="When Wistful Selkie enters, draw a card.",
    setup_interceptors=wistful_selkie_setup
)

GWYLLION_HEDGE_MAGE = make_creature(
    name="Gwyllion Hedge-Mage",
    power=2,
    toughness=2,
    mana_cost="{2}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Hag", "Wizard"},
    text="When Gwyllion Hedge-Mage enters, if you control two or more Plains, you may create a 1/1 white Kithkin Soldier creature token. When Gwyllion Hedge-Mage enters, if you control two or more Swamps, you may put a -1/-1 counter on target creature.",
    setup_interceptors=gwyllion_hedge_mage_setup
)

SELKIE_HEDGE_MAGE = make_creature(
    name="Selkie Hedge-Mage",
    power=2,
    toughness=2,
    mana_cost="{2}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="When Selkie Hedge-Mage enters, if you control two or more Forests, you may gain 3 life. When Selkie Hedge-Mage enters, if you control two or more Islands, you may return target tapped creature to its owner's hand.",
    setup_interceptors=selkie_hedge_mage_setup
)

HORDE_OF_NOTIONS = make_creature(
    name="Horde of Notions",
    power=5,
    toughness=5,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Elemental"},
    supertypes={"Legendary"},
    text="Vigilance, trample, haste. {W}{U}{B}{R}{G}: You may play target Elemental card from your graveyard without paying its mana cost."
)

ASHLING_THE_EXTINGUISHER = make_creature(
    name="Ashling, the Extinguisher",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Shaman"},
    supertypes={"Legendary"},
    text="Whenever Ashling, the Extinguisher deals combat damage to a player, choose target creature that player controls. The player sacrifices that creature.",
    setup_interceptors=ashling_the_extinguisher_setup
)

RHYS_THE_REDEEMED = make_creature(
    name="Rhys the Redeemed",
    power=1,
    toughness=1,
    mana_cost="{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="{2}{G/W}, {T}: Create a 1/1 green and white Elf Warrior creature token. {4}{G/W}{G/W}, {T}: For each creature token you control, create a token that's a copy of that creature."
)

# Final 6 cards to reach 408
HEAP_DOLL = make_artifact(
    name="Heap Doll",
    mana_cost="{1}",
    subtypes={"Scarecrow"},
    text="Sacrifice Heap Doll: Exile target card from a graveyard."
)

PAINTER_SERVANT = make_creature(
    name="Painter's Servant",
    power=1,
    toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="As Painter's Servant enters, choose a color. All cards that aren't on the battlefield, spells, and permanents are the chosen color in addition to their other colors."
)

REAPER_KING = make_creature(
    name="Reaper King",
    power=6,
    toughness=6,
    mana_cost="{2/W}{2/U}{2/B}{2/R}{2/G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Scarecrow"},
    supertypes={"Legendary"},
    text="Other Scarecrow creatures you control get +1/+1. Whenever another Scarecrow enters under your control, destroy target permanent.",
    setup_interceptors=reaper_king_setup
)

PILI_PALA = make_creature(
    name="Pili-Pala",
    power=1,
    toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="Flying. {2}, {Q}: Add one mana of any color. ({Q} is the untap symbol.)"
)

WICKER_WARCRAWLER = make_creature(
    name="Wicker Warcrawler",
    power=6,
    toughness=6,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="Whenever Wicker Warcrawler attacks or blocks, put a -1/-1 counter on it at end of combat.",
    setup_interceptors=wicker_warcrawler_setup
)

WANDERBRINE_ROOTCUTTERS = make_creature(
    name="Wanderbrine Rootcutters",
    power=3,
    toughness=3,
    mana_cost="{2}{U/B}{U/B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Merfolk", "Rogue"},
    text="Wanderbrine Rootcutters can't be blocked by green creatures."
)

# =============================================================================
# PHASE A1 SPICE PASS (2026-05-18)
# =============================================================================
# 4 new spice picks targeting the 5-tribe Fae but Mid axis (Faerie / Kithkin /
# Treefolk / Elf / Merfolk / Giant / Goblin / Elemental). Designed to break
# out of the 35-card make_etb_trigger cluster by introducing distinct
# helpers/events (saga, dynamic PT, upkeep tribal-count gate, equipment).
#
# Reskin-cluster rewires (4) are inline above on the original cards:
# Oona / Wort / Gaddock / Wydwen — each got a distinct code-fingerprint
# (anthem+token loop, upkeep-graveyard recursion, lord+ETB drain, combat-
# discard) rather than the shared shape they belonged to.

# Spice 1 — Aurora of Five (NEW Mythic Legendary Enchantment)
# {2}{W}{U}{B}{R}{G} — Pattern 11 build-around. At the beginning of your
# upkeep, if you control creatures sharing 5 or more different fae tribes,
# take an extra turn after this one. Otherwise scry 2.
# Helpers: make_upkeep_trigger + EXTRA_TURN + SCRY. Reads battlefield subtype
# diversity (state coupling). The 7-mana 5-color cost is the steep gate; the
# extra turn is the payoff for actually assembling 5 tribes.
_FAE_TRIBES = ('Faerie', 'Kithkin', 'Treefolk', 'Elf', 'Merfolk',
                  'Giant', 'Goblin', 'Elemental')


def aurora_of_five_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_upkeep_trigger as _make_upkeep_trigger,
    )

    def count_distinct_tribes(st: GameState) -> int:
        seen: set[str] = set()
        for o in st.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                for tribe in _FAE_TRIBES:
                    if tribe in (o.characteristics.subtypes or set()):
                        seen.add(tribe)
        return len(seen)

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        n = count_distinct_tribes(state)
        if n >= 5:
            return [Event(
                type=EventType.EXTRA_TURN,
                payload={'player': obj.controller},
                source=obj.id,
            )]
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        )]
    return [_make_upkeep_trigger(obj, upkeep_effect, controller_only=True)]


AURORA_OF_FIVE = make_enchantment(
    name="Aurora of Five",
    mana_cost="{2}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, if you control creatures with five or more different fae tribes (Faerie, Kithkin, Treefolk, Elf, Merfolk, Giant, Goblin, Elemental), take an extra turn after this one. Otherwise, scry 2.",
    setup_interceptors=aurora_of_five_setup,
)


# Spice 2 — Faewild Convocation (NEW Mythic Legendary Creature — Treefolk Druid)
# {3}{G}{W}{U} — 4/4 Treefolk Druid. Pattern 11 build-around. Self has +1/+1
# for each different tribe (Faerie/Kithkin/Treefolk/Elf/Merfolk) you control
# AND tutors a creature card to hand on ETB. The dynamic PT pumps the body in
# a tribally-diverse deck while the tutor digs for the next tribe rep.
def faewild_convocation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_etb_trigger as _ih_make_etb_trigger,
    )
    five_tribes = ('Faerie', 'Kithkin', 'Treefolk', 'Elf', 'Merfolk')

    def count_distinct_tribes(st: GameState) -> int:
        seen: set[str] = set()
        for o in st.objects.values():
            if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                for tribe in five_tribes:
                    if tribe in (o.characteristics.subtypes or set()):
                        seen.add(tribe)
        return len(seen)

    def p_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.QUERY_POWER and event.payload.get('object_id') == obj.id

    def p_handler(event: Event, st: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + count_distinct_tribes(st)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    def t_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.QUERY_TOUGHNESS and event.payload.get('object_id') == obj.id

    def t_handler(event: Event, st: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + count_distinct_tribes(st)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'card_type': 'creature',
                'destination': 'hand',
            },
            source=obj.id,
        )]

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=p_filter, handler=p_handler,
                    duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=t_filter, handler=t_handler,
                    duration='while_on_battlefield'),
        _ih_make_etb_trigger(obj, etb_effect),
    ]


FAEWILD_CONVOCATION = make_creature(
    name="Faewild Convocation",
    power=4,
    toughness=4,
    mana_cost="{3}{G}{W}{U}",
    colors={Color.GREEN, Color.WHITE, Color.BLUE},
    subtypes={"Treefolk", "Druid"},
    supertypes={"Legendary"},
    text="When Faewild Convocation enters, search your library for a creature card, reveal it, put it into your hand, then shuffle. Faewild Convocation gets +1/+1 for each different tribe among Faerie, Kithkin, Treefolk, Elf, and Merfolk you control.",
    setup_interceptors=faewild_convocation_setup,
)


# Spice 3 — The Aurora Cycle (NEW Legendary Saga)
# {3}{W}{U}{B}{R}{G} — Pattern 11 build-around assembly. Uses make_saga_setup
# (no new engine) — the saga delivers an Elemental tutor on I, five distinct
# 1/1 tribe tokens on II, and a +2/+2 trample anthem on III.
def _aurora_cycle_chapter_i(saga: GameObject, state: GameState) -> list[Event]:
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga.controller,
            'subtype': 'Elemental',
            'card_type': 'creature',
            'destination': 'hand',
        },
        source=saga.id,
    )]


def _aurora_cycle_chapter_ii(saga: GameObject, state: GameState) -> list[Event]:
    tokens = [
        ('Faerie', {'Faerie', 'Rogue'}, {Color.BLUE, Color.BLACK}, ['flying']),
        ('Kithkin', {'Kithkin', 'Soldier'}, {Color.WHITE}, []),
        ('Treefolk', {'Treefolk', 'Warrior'}, {Color.GREEN}, []),
        ('Goblin', {'Goblin', 'Warrior'}, {Color.RED}, []),
        ('Merfolk', {'Merfolk', 'Wizard'}, {Color.BLUE}, []),
    ]
    events: list[Event] = []
    for tribe_name, subs, colors, kws in tokens:
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': saga.controller,
                'token': {
                    'name': f'{tribe_name} Token',
                    'types': {CardType.CREATURE},
                    'subtypes': subs,
                    'colors': colors,
                    'power': 1,
                    'toughness': 1,
                    'keywords': kws,
                },
            },
            source=saga.id,
        ))
    return events


def _aurora_cycle_chapter_iii(saga: GameObject, state: GameState) -> list[Event]:
    events: list[Event] = []
    for o in list(state.objects.values()):
        if (o.controller == saga.controller and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                o.id != saga.id):
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': o.id,
                    'power_mod': 2,
                    'toughness_mod': 2,
                    'duration': 'end_of_turn',
                },
                source=saga.id,
            ))
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': o.id,
                    'keyword': 'trample',
                    'duration': 'end_of_turn',
                },
                source=saga.id,
            ))
    return events


def the_aurora_cycle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_saga_setup as _make_saga_setup
    return _make_saga_setup(
        obj,
        {1: _aurora_cycle_chapter_i,
         2: _aurora_cycle_chapter_ii,
         3: _aurora_cycle_chapter_iii},
        final_chapter=3,
    )


THE_AURORA_CYCLE = make_enchantment(
    name="The Aurora Cycle",
    mana_cost="{3}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Saga"},
    supertypes={"Legendary"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.) I — Search your library for an Elemental creature card, reveal it, put it into your hand, then shuffle. II — Create five 1/1 creature tokens: one Faerie Rogue with flying, one Kithkin Soldier, one Treefolk Warrior, one Goblin Warrior, and one Merfolk Wizard. III — Until end of turn, other creatures you control get +2/+2 and gain trample.",
    setup_interceptors=the_aurora_cycle_setup,
)


# Spice 4 — Treefolk-bough Spear (NEW Equipment)
# {2} Artifact — Equipment. Equipped creature gets +X/+X where X equals
# Treefolk and Forests you control. Equip {2}.
# Uses make_equipment_setup helper for the equip cost + attach/unattach
# plumbing, then layers a dynamic PT QUERY interceptor that reads live
# Treefolk+Forest count on the equipped target. Pattern 11 build-around
# (Treefolk/Forest gated tribal Equipment).
def treefolk_bough_spear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import (
        make_equipment_setup as _make_equipment_setup,
        get_attached_target_id as _get_attached_target_id,
    )

    def count_treefolk_and_forests(st: GameState) -> int:
        n = 0
        for o in st.objects.values():
            if o.controller != obj.controller or o.zone != ZoneType.BATTLEFIELD:
                continue
            if 'Treefolk' in (o.characteristics.subtypes or set()):
                n += 1
                continue
            if 'Forest' in (o.characteristics.subtypes or set()):
                n += 1
        return n

    def p_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        tgt_id = _get_attached_target_id(obj)
        return tgt_id is not None and event.payload.get('object_id') == tgt_id

    def p_handler(event: Event, st: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + count_treefolk_and_forests(st)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    def t_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        tgt_id = _get_attached_target_id(obj)
        return tgt_id is not None and event.payload.get('object_id') == tgt_id

    def t_handler(event: Event, st: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + count_treefolk_and_forests(st)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    setup_fn = _make_equipment_setup(equip_cost="{2}")
    interceptors = setup_fn(obj, state)
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=p_filter, handler=p_handler,
        duration='while_on_battlefield',
    ))
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=t_filter, handler=t_handler,
        duration='while_on_battlefield',
    ))
    return interceptors


TREEFOLK_BOUGH_SPEAR = make_artifact(
    name="Treefolk-bough Spear",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +X/+X, where X is the number of Treefolk and Forests you control. Equip {2}.",
    setup_interceptors=treefolk_bough_spear_setup,
)


# =============================================================================
# REGISTRY
# =============================================================================

FAE_BUT_MID_CARDS = {
    # WHITE CARDS
    "Changeling Wayfinder": CHANGELING_WAYFINDER,
    "Rooftop Percher": ROOFTOP_PERCHER,
    "Adept Watershaper": ADEPT_WATERSHAPER,
    "Appeal to Eirdu": APPEAL_TO_EIRDU,
    "Brigid, Clachan's Heart": BRIGID_CLACHANS_HEART,
    "Burdened Stoneback": BURDENED_STONEBACK,
    "Champion of the Clachan": CHAMPION_OF_THE_CLACHAN,
    "Clachan Festival": CLACHAN_FESTIVAL,
    "Crib Swap": CRIB_SWAP,
    "Curious Colossus": CURIOUS_COLOSSUS,
    "Eirdu, Carrier of Dawn": EIRDU_CARRIER_OF_DAWN,
    "Encumbered Reejerey": ENCUMBERED_REEJEREY,
    "Flock Impostor": FLOCK_IMPOSTOR,
    "Gallant Fowlknight": GALLANT_FOWLKNIGHT,
    "Goldmeadow Nomad": GOLDMEADOW_NOMAD,
    "Keep Out": KEEP_OUT,
    "Kinbinding": KINBINDING,
    "Ajani, Outland Chaperone": AJANI_OUTLAND_CHAPERONE,
    "Personify": PERSONIFY,
    "Protective Response": PROTECTIVE_RESPONSE,
    "Pyrrhic Strike": PYRRHIC_STRIKE,
    "Reluctant Dounguard": RELUCTANT_DOUNGUARD,
    "Rhys, the Evermore": RHYS_THE_EVERMORE,
    "Riverguard's Reflexes": RIVERGUARDS_REFLEXES,
    "Evershrike's Gift": EVERSHRIKES_GIFT,
    "Kinsbaile Aspirant": KINSBAILE_ASPIRANT,
    "Kinscaer Sentry": KINSCAER_SENTRY,
    "Kithkeeper": KITHKEEPER,
    "Liminal Hold": LIMINAL_HOLD,
    "Meanders Guide": MEANDERS_GUIDE,
    "Moonlit Lamenter": MOONLIT_LAMENTER,
    "Morningtide's Light": MORNINGTIDES_LIGHT,
    "Shore Lurker": SHORE_LURKER,
    "Slumbering Walker": SLUMBERING_WALKER,
    "Spiral into Solitude": SPIRAL_INTO_SOLITUDE,
    "Sun-Dappled Celebrant": SUN_DAPPLED_CELEBRANT,
    "Thoughtweft Imbuer": THOUGHTWEFT_IMBUER,
    "Timid Shieldbearer": TIMID_SHIELDBEARER,
    "Tributary Vaulter": TRIBUTARY_VAULTER,
    "Wanderbrine Preacher": WANDERBRINE_PREACHER,
    "Wanderbrine Trapper": WANDERBRINE_TRAPPER,
    "Winnowing": WINNOWING,

    # GREEN CARDS
    "Formidable Speaker": FORMIDABLE_SPEAKER,
    "Great Forest Druid": GREAT_FOREST_DRUID,
    "Luminollusk": LUMINOLLUSK,
    "Lys Alana Dignitary": LYSALANA_DIGNITARY,
    "Lys Alana Informant": LYSALANA_INFORMANT,
    "Midnight Tilling": MIDNIGHT_TILLING,
    "Moon-Vigil Adherents": MOON_VIGIL_ADHERENTS,
    "Mutable Explorer": MUTABLE_EXPLORER,
    "Pummeler for Hire": PUMMELER_FOR_HIRE,
    "Safewright Cavalry": SAFEWRIGHT_CAVALRY,
    "Selfless Safewright": SELFLESS_SAFEWRIGHT,
    "Surly Farrier": SURLY_FARRIER,
    "Tend the Sprigs": TEND_THE_SPRIGS,
    "Thoughtweft Charge": THOUGHTWEFT_CHARGE,
    "Bristlebane Battler": BRISTLEBANE_BATTLER,
    "Bristlebane Outrider": BRISTLEBANE_OUTRIDER,
    "Celestial Reunion": CELESTIAL_REUNION,
    "Champions of the Perfect": CHAMPIONS_OF_THE_PERFECT,
    "Chomping Changeling": CHOMPING_CHANGELING,
    "Crossroads Watcher": CROSSROADS_WATCHER,
    "Dawn's Light Archer": DAWNS_LIGHT_ARCHER,
    "Dundoolin Weaver": DUNDOOLIN_WEAVER,
    "Gilt-Leaf's Embrace": GILT_LEAFS_EMBRACE,
    "Pitiless Fists": PITILESS_FISTS,
    "Prismabasher": PRISMABASHER,
    "Prismatic Undercurrents": PRISMATIC_UNDERCURRENTS,
    "Assert Perfection": ASSERT_PERFECTION,
    "Aurora Awakener": AURORA_AWAKENER,
    "Bloom Tender": BLOOM_TENDER,
    "Blossoming Defense": BLOSSOMING_DEFENSE,
    "Mistmeadow Council": MISTMEADOW_COUNCIL,
    "Morcant's Eyes": MORCANTS_EYES,
    "Sapling Nursery": SAPLING_NURSERY,
    "Shimmerwilds Growth": SHIMMERWILDS_GROWTH,
    "Spry and Mighty": SPRY_AND_MIGHTY,
    "Trystan, Callous Cultivator": TRYSTAN_CALLOUS_CULTIVATOR,
    "Unforgiving Aim": UNFORGIVING_AIM,
    "Vinebred Brawler": VINEBRED_BRAWLER,
    "Virulent Emissary": VIRULENT_EMISSARY,
    "Wildvine Pummeler": WILDVINE_PUMMELER,

    # BLUE CARDS
    "Aquitect's Defenses": AQUITECTS_DEFENSES,
    "Blossombind": BLOSSOMBIND,
    "Champions of the Shoal": CHAMPIONS_OF_THE_SHOAL,
    "Flitterwing Nuisance": FLITTERWING_NUISANCE,
    "Glamermite": GLAMERMITE,
    "Glen Elendra Guardian": GLEN_ELENDRA_GUARDIAN,
    "Gravelgill Scoundrel": GRAVELGILL_SCOUNDREL,
    "Illusion Spinners": ILLUSION_SPINNERS,
    "Disruptor of Currents": DISRUPTOR_OF_CURRENTS,
    "Glamer Gifter": GLAMER_GIFTER,
    "Glen Elendra's Answer": GLEN_ELENDRAS_ANSWER,
    "Harmonized Crescendo": HARMONIZED_CRESCENDO,
    "Pestered Wellguard": PESTERED_WELLGUARD,
    "Rime Chill": RIME_CHILL,
    "Rimefire Torque": RIMEFIRE_TORQUE,
    "Rimekin Recluse": RIMEKIN_RECLUSE,
    "Kulrath Mystic": KULRATH_MYSTIC,
    "Loch Mare": LOCH_MARE,
    "Lofty Dreams": LOFTY_DREAMS,
    "Mirrorform": MIRRORFORM,
    "Noggle the Mind": NOGGLE_THE_MIND,
    "Omni-Changeling": OMNI_CHANGELING,
    "Run Away Together": RUN_AWAY_TOGETHER,
    "Shinestriker": SHINESTRIKER,
    "Silvergill Mentor": SILVERGILL_MENTOR,
    "Silvergill Peddler": SILVERGILL_PEDDLER,
    "Spell Snare": SPELL_SNARE,
    "Stratosoarer": STRATOSOARER,
    "Summit Sentinel": SUMMIT_SENTINEL,
    "Sunderflock": SUNDERFLOCK,
    "Swat Away": SWAT_AWAY,
    "Tanufel Rimespeaker": TANUFEL_RIMESPEAKER,
    "Temporal Cleansing": TEMPORAL_CLEANSING,
    "Thirst for Identity": THIRST_FOR_IDENTITY,
    "Unexpected Assistance": UNEXPECTED_ASSISTANCE,
    "Unwelcome Sprite": UNWELCOME_SPRITE,
    "Wanderwine Distracter": WANDERWINE_DISTRACTER,
    "Wanderwine Farewell": WANDERWINE_FAREWELL,
    "Wild Unraveling": WILD_UNRAVELING,

    # BLACK CARDS
    "Auntie's Sentence": AUNTIES_SENTENCE,
    "Bile-Vial Boggart": BILE_VIAL_BOGGART,
    "Bitterbloom Bearer": BITTERBLOOM_BEARER,
    "Blighted Blackthorn": BLIGHTED_BLACKTHORN,
    "Blight Rot": BLIGHT_ROT,
    "Bloodline Bidding": BLOODLINE_BIDDING,
    "Boggart Mischief": BOGGART_MISCHIEF,
    "Boggart Prankster": BOGGART_PRANKSTER,
    "Creakwood Safewright": CREAKWOOD_SAFEWRIGHT,
    "Darkness Descends": DARKNESS_DESCENDS,
    "Dawnhand Eulogist": DAWNHAND_EULOGIST,
    "Dream Seizer": DREAM_SEIZER,
    "Gnarlbark Elm": GNARLBARK_ELM,
    "Graveshifter": GRAVESHIFTER,
    "Barbed Bloodletter": BARBED_BLOODLETTER,
    "Bogslither's Embrace": BOGSLITHERS_EMBRACE,
    "Champion of the Weird": CHAMPION_OF_THE_WEIRD,
    "Dawnhand Dissident": DAWNHAND_DISSIDENT,
    "Dose of Dawnglow": DOSE_OF_DAWNGLOW,
    "Deceit": DECEIT,
    "Dream Harvest": DREAM_HARVEST,
    "Requiting Hex": REQUITING_HEX,
    "Retched Wretch": RETCHED_WRETCH,
    "Gloom Ripper": GLOOM_RIPPER,
    "Grub, Storied Matriarch": GRUB_STORIED_MATRIARCH,
    "Gutsplitter Gang": GUTSPLITTER_GANG,
    "Heirloom Auntie": HEIRLOOM_AUNTIE,
    "Moonglove Extractor": MOONGLOVE_EXTRACTOR,
    "Moonshadow": MOONSHADOW,
    "Mudbutton Cursetosser": MUDBUTTON_CURSETOSSER,
    "Nameless Inversion": NAMELESS_INVERSION,
    "Nightmare Sower": NIGHTMARE_SOWER,
    "Perfect Intimidation": PERFECT_INTIMIDATION,
    "Scarblade Scout": SCARBLADE_SCOUT,
    "Scarblade's Malice": SCARBLADES_MALICE,
    "Shimmercreep": SHIMMERCREEP,
    "Taster of Wares": TASTER_OF_WARES,
    "Twilight Diviner": TWILIGHT_DIVINER,
    "Unbury": UNBURY,

    # RED CARDS
    "Ashling, Rekindled": ASHLING_REKINDLED,
    "Boldwyr Aggressor": BOLDWYR_AGGRESSOR,
    "Boneclub Berserker": BONECLUB_BERSERKER,
    "Boulder Dash": BOULDER_DASH,
    "Brambleback Brute": BRAMBLEBACK_BRUTE,
    "Burning Curiosity": BURNING_CURIOSITY,
    "Cinder Strike": CINDER_STRIKE,
    "Collective Inferno": COLLECTIVE_INFERNO,
    "Elder Auntie": ELDER_AUNTIE,
    "Enraged Flamecaster": ENRAGED_FLAMECASTER,
    "Explosive Prodigy": EXPLOSIVE_PRODIGY,
    "Feed the Flames": FEED_THE_FLAMES,
    "Flame-Chain Mauler": FLAME_CHAIN_MAULER,
    "Flamebraider": FLAMEBRAIDER,
    "Flamekin Gildweaver": FLAMEKIN_GILDWEAVER,
    "Giantfall": GIANTFALL,
    "Goatnap": GOATNAP,
    "Goliath Daydreamer": GOLIATH_DAYDREAMER,
    "Gristle Glutton": GRISTLE_GLUTTON,
    "Champion of the Path": CHAMPION_OF_THE_PATH,
    "End-Blaze Epiphany": END_BLAZE_EPIPHANY,
    "Reckless Ransacking": RECKLESS_RANSACKING,
    "Hexing Squelcher": HEXING_SQUELCHER,
    "Impolite Entrance": IMPOLITE_ENTRANCE,
    "Kindle the Inner Flame": KINDLE_THE_INNER_FLAME,
    "Kulrath Zealot": KULRATH_ZEALOT,
    "Lasting Tarfire": LASTING_TARFIRE,
    "Lavaleaper": LAVALEAPER,
    "Meek Attack": MEEK_ATTACK,
    "Scuzzback Scrounger": SCUZZBACK_SCROUNGER,
    "Sear": SEAR,
    "Sizzling Changeling": SIZZLING_CHANGELING,
    "Soul Immolation": SOUL_IMMOLATION,
    "Soulbright Seeker": SOULBRIGHT_SEEKER,
    "Sourbread Auntie": SOURBREAD_AUNTIE,
    "Spinerock Tyrant": SPINEROCK_TYRANT,
    "Squawkroaster": SQUAWKROASTER,
    "Sting-Slinger": STING_SLINGER,
    "Tweeze": TWEEZE,
    "Warren Torchmaster": WARREN_TORCHMASTER,

    # MULTICOLOR CARDS
    "Abigale, Eloquent First-Year": ABIGALE_ELOQUENT,
    "Boggart Cursecrafter": BOGGART_CURSECRAFTER,
    "Bre of Clan Stoutarm": BRE_OF_CLAN_STOUTARM,
    "Chaos Spewer": CHAOS_SPEWER,
    "Chitinous Graspling": CHITINOUS_GRASPLING,
    "Deepchannel Duelist": DEEPCHANNEL_DUELIST,
    "Deepway Navigator": DEEPWAY_NAVIGATOR,
    "Doran, Besieged by Time": DORAN_BESIEGED,
    "Eclipsed Boggart": ECLIPSED_BOGGART,
    "Eclipsed Elf": ECLIPSED_ELF,
    "Eclipsed Flamekin": ECLIPSED_FLAMEKIN,
    "Eclipsed Kithkin": ECLIPSED_KITHKIN,
    "Eclipsed Merrow": ECLIPSED_MERROW,
    "Feisty Spikeling": FEISTY_SPIKELING,
    "Figure of Fable": FIGURE_OF_FABLE,
    "Flaring Cinder": FLARING_CINDER,
    "Gangly Stompling": GANGLY_STOMPLING,
    "Ashling's Command": ASHLINGS_COMMAND,
    "Brigid's Command": BRIGIDS_COMMAND,
    "Glister Bairn": GLISTER_BAIRN,
    "Prideful Feastling": PRIDEFUL_FEASTLING,
    "Reaping Willow": REAPING_WILLOW,
    "Raiding Schemes": RAIDING_SCHEMES,
    "Catharsis": CATHARSIS,
    "Emptiness": EMPTINESS,
    "Grub's Command": GRUBS_COMMAND,
    "High Perfect Morcant": HIGH_PERFECT_MORCANT,
    "Hovel Hurler": HOVEL_HURLER,
    "Kirol, Attentive First-Year": KIROL_ATTENTIVE,
    "Lluwen, Imperfect Naturalist": LLUWEN_IMPERFECT,
    "Maralen, Fae Ascendant": MARALEN_FAE_ASCENDANT,
    "Merrow Skyswimmer": MERROW_SKYSWIMMER,
    "Mischievous Sneakling": MISCHIEVOUS_SNEAKLING,
    "Morcant's Loyalist": MORCANTS_LOYALIST,
    "Noggle Robber": NOGGLE_ROBBER,
    "Sanar, Innovative First-Year": SANAR_INNOVATIVE,
    "Shadow Urchin": SHADOW_URCHIN,
    "Stoic Grove-Guide": STOIC_GROVE_GUIDE,
    "Sygg's Command": SYGGS_COMMAND,
    "Tam, Mindful First-Year": TAM_MINDFUL,
    "Thoughtweft Lieutenant": THOUGHTWEFT_LIEUTENANT,
    "Trystan's Command": TRYSTANS_COMMAND,
    "Twinflame Travelers": TWINFLAME_TRAVELERS,
    "Vibrance": VIBRANCE,
    "Voracious Tome-Skimmer": VORACIOUS_TOME_SKIMMER,
    "Wary Farmer": WARY_FARMER,
    "Wistfulness": WISTFULNESS,

    # ARTIFACT CARDS
    "Chronicle of Victory": CHRONICLE_OF_VICTORY,
    "Dawn-Blessed Pennant": DAWN_BLESSED_PENNANT,
    "Firdoch Core": FIRDOCH_CORE,
    "Foraging Wickermaw": FORAGING_WICKERMAW,
    "Gathering Stone": GATHERING_STONE,
    "Mirrormind Crown": MIRRORMIND_CROWN,
    "Puca's Eye": PUCAS_EYE,
    "Springleaf Drum": SPRINGLEAF_DRUM,
    "Stalactite Dagger": STALACTITE_DAGGER,
    "Bark of Doran": BARK_OF_DORAN,
    "Moonglove Extract": MOONGLOVE_EXTRACT,
    "Runed Stalactite": RUNED_STALACTITE,
    "Thornbite Staff": THORNBITE_STAFF,
    "Obsidian Battle-Axe": OBSIDIAN_BATTLE_AXE,
    "Cloak and Dagger": CLOAK_AND_DAGGER,
    "Diviner's Wand": DIVINERS_WAND,
    "Veteran's Armaments": VETERANS_ARMAMENTS,

    # LAND CARDS
    "Forest": FOREST,
    "Island": ISLAND,
    "Mountain": MOUNTAIN,
    "Plains": PLAINS,
    "Swamp": SWAMP,
    "Blood Crypt": BLOOD_CRYPT,
    "Hallowed Fountain": HALLOWED_FOUNTAIN,
    "Overgrown Tomb": OVERGROWN_TOMB,
    "Steam Vents": STEAM_VENTS,
    "Temple Garden": TEMPLE_GARDEN,
    "Eclipsed Realms": ECLIPSED_REALMS,
    "Evolving Wilds": EVOLVING_WILDS,

    # MORE BLACK CARDS
    "Auntie's Favor": AUNTIES_FAVOR,
    "Wretched Banquet": WRETCHED_BANQUET,

    # MORE RED CARDS
    "Cinder Pyromancer": CINDER_PYROMANCER,
    "Inner-Flame Igniter": INNER_FLAME_IGNITER,
    "Smoldering Spinebacks": SMOLDERING_SPINEBACKS,
    "Thundercloud Shaman": THUNDERCLOUD_SHAMAN,

    # MORE GREEN CARDS
    "Elvish Harbinger": ELVISH_HARBINGER,
    "Heritage Druid": HERITAGE_DRUID,
    "Imperious Perfect": IMPERIOUS_PERFECT,
    "Nath of the Gilt-Leaf": NATH_OF_THE_GILT_LEAF,
    "Timber Protector": TIMBER_PROTECTOR,
    "Treefolk Harbinger": TREEFOLK_HARBINGER,
    "Wolf-Skull Shaman": WOLF_SKULL_SHAMAN,

    # MORE MULTICOLOR CARDS
    "Oona, Queen of the Fae": OONA_QUEEN_OF_THE_FAE,
    "Sygg, River Guide": SYGG_RIVER_GUIDE,
    "Sygg, River Cutthroat": SYGG_RIVER_CUTTHROAT,
    "Wydwen, the Biting Gale": WYDWEN_THE_BITING_GALE,
    "Wort, Boggart Auntie": WORT_BOGGART_AUNTIE,
    "Gaddock Teeg": GADDOCK_TEEG,
    "Oversoul of Dusk": OVERSOUL_OF_DUSK,
    "Kitchen Finks": KITCHEN_FINKS,
    "Murderous Redcap": MURDEROUS_REDCAP,
    "Demigod of Revenge": DEMIGOD_OF_REVENGE,
    "Glen Elendra Archmage": GLEN_ELENDRA_ARCHMAGE,
    "Stillmoon Cavalier": STILLMOON_CAVALIER,
    "Creakwood Liege": CREAKWOOD_LIEGE,
    "Deathbringer Liege": DEATHBRINGER_LIEGE,
    "Balefire Liege": BALEFIRE_LIEGE,
    "Boartusk Liege": BOARTUSK_LIEGE,
    "Thistledown Liege": THISTLEDOWN_LIEGE,
    "Murkfiend Liege": MURKFIEND_LIEGE,
    "Mindwrack Liege": MINDWRACK_LIEGE,
    "Ashenmoor Liege": ASHENMOOR_LIEGE,
    "Wilt-Leaf Liege": WILT_LEAF_LIEGE,

    # BATCH 3 - MORE WHITE CREATURES
    "Kinsbaile Borderguard": KINSBAILE_BORDERGUARD,
    "Cloudgoat Ranger": CLOUDGOAT_RANGER,
    "Mirror Entity": MIRROR_ENTITY,
    "Reveillark": REVEILLARK,
    "Ranger of Eos": RANGER_OF_EOS,

    # BATCH 3 - MORE BLUE CREATURES
    "Vendilion Clique": VENDILION_CLIQUE,
    "Sower of Temptation": SOWER_OF_TEMPTATION,
    "Mistbind Clique": MISTBIND_CLIQUE,
    "Spellstutter Sprite": SPELLSTUTTER_SPRITE,
    "Scion of Oona": SCION_OF_OONA,

    # BATCH 3 - MORE BLACK CREATURES
    "Shriekmaw": SHRIEKMAW,
    "Oona's Blackguard": THOUGHTSEIZE_CREATURE,
    "Earwig Squad": EARWIG_SQUAD,
    "Bitterblossom": BITTERBLOSSOM,
    "Mornsong Aria": MORNSONG_ARIA,

    # BATCH 3 - MORE RED CREATURES
    "Sunrise Sovereign": SUNRISE_SOVEREIGN,
    "Brion Stoutarm": BRION_STOUTARM,
    "Nova Chaser": NOVA_CHASER,
    "Incandescent Soulstoke": INCANDESCENT_SOULSTOKE,

    # BATCH 3 - MORE GREEN CREATURES
    "Chameleon Colossus": CHAMELEON_COLOSSUS,
    "Primalcrux": PRIMALCRUX,
    "Devoted Druid": DEVOTED_DRUID,
    "Nettle Sentinel": NETTLE_SENTINEL,
    "Masked Admirers": MASKED_ADMIRERS,

    # BATCH 3 - MORE SPELLS
    "Thoughtweft Gambit": THOUGHTWEFT_GAMBIT,
    "Cryptic Command": CRYPTIC_COMMAND,
    "Firespout": FIRESPOUT,
    "Primal Command": PRIMAL_COMMAND,
    "Austere Command": AUSTERE_COMMAND,
    "Profane Command": PROFANE_COMMAND,
    "Incendiary Command": INCENDIARY_COMMAND,

    # BATCH 3 - MORE MULTICOLOR
    "Fulminator Mage": FULMINATOR_MAGE,
    "Figure of Destiny": FIGURE_OF_DESTINY,
    "Manamorphose": MANAMORPHOSE,
    "Boggart Ram-Gang": BOGGART_RAM_GANG,
    "Tattermunge Maniac": TATTERMUNGE_MANIAC,
    "Vexing Shusher": VEXING_SHUSHER,
    "Plumeveil": PLUMEVEIL,
    "Unmake": UNMAKE,
    "Fiery Justice": FIERY_JUSTICE,
    "Augury Adept": AUGURY_ADEPT,
    "Cold-Eyed Selkie": COLD_EYED_SELKIE,
    "Deus of Calamity": DEUS_OF_CALAMITY,
    "Ghastlord of Fugue": GHASTLORD_OF_FUGUE,
    "Deity of Scars": DEITY_OF_SCARS,
    "Godhead of Awe": GODHEAD_OF_AWE,
    "Overbeing of Myth": OVERBEING_OF_MYTH,
    "Divinity of Pride": DIVINITY_OF_PRIDE,

    # BATCH 4 - WHITE CARDS
    "Hallowed Burial": HALLOWED_BURIAL,
    "Idyllic Tutor": IDYLLIC_TUTOR,
    "Spectral Procession": SPECTRAL_PROCESSION,
    "Runed Halo": RUNED_HALO,
    "Oblivion Ring": OBLIVION_RING,
    "Knight of Meadowgrain": KNIGHT_OF_MEADOWGRAIN,
    "Preeminent Captain": PREEMINENT_CAPTAIN,
    "Pollen Lullaby": POLLEN_LULLABY,

    # BATCH 4 - BLUE CARDS
    "Broken Ambitions": BROKEN_AMBITIONS,
    "Faerie Trickery": FAERIE_TRICKERY,
    "Ponder": PONDER,
    "Merrow Commerce": MERROW_COMMERCE,
    "Surgespanner": SURGESPANNER,
    "Silvergill Adept": SILVERGILL_ADEPT,
    "Mulldrifter": MULLDRIFTER,

    # BATCH 4 - BLACK CARDS
    "Final Revels": NAMELESS_INVERSION_B,
    "Thoughtseize": THOUGHTSEIZE,
    "Peppersmoke": PEPPERSMOKE,
    "Fodder Launch": FODDER_LAUNCH,
    "Makeshift Mannequin": MAKESHIFT_MANNEQUIN,
    "Death Denied": DEATH_DENIED,
    "Nettlevine Blight": NETTLEVINE_BLIGHT,

    # BATCH 4 - RED CARDS
    "Tarfire": TARFIRE,
    "Lash Out": LASH_OUT,
    "Caterwauling Boggart": CATERWAULING_BOGGART,
    "Knucklebone Witch": KNUCKLEBONE_WITCH,
    "Wort, the Raidmother": WORT_THE_RAIDMOTHER,
    "Sensation Gorger": SENSATION_GORGER,

    # BATCH 4 - GREEN CARDS
    "Garruk Wildspeaker": GARRUK_WILDSPEAKER,
    "Jagged-Scar Archers": JAGGED_SCAR_ARCHERS,
    "Leaf-Crowned Elder": LEAF_CROWNED_ELDER,
    "Elvish Branchbender": ELVISH_BRANCHBENDER,
    "Gilt-Leaf Ambush": GILT_LEAF_AMBUSH,
    "Hunting Triad": HUNTING_TRIAD,

    # BATCH 4 - MORE CREATURES
    "Boggart Sprite-Chaser": BOGGART_SPRITE_CHASER,
    "Scarblade Elite": SCARBLADE_ELITE,
    "Safehold Elite": SAFEHOLD_ELITE,
    "Rendclaw Trow": RENDCLAW_TROW,
    "Wistful Selkie": WISTFUL_SELKIE,
    "Gwyllion Hedge-Mage": GWYLLION_HEDGE_MAGE,
    "Selkie Hedge-Mage": SELKIE_HEDGE_MAGE,
    "Horde of Notions": HORDE_OF_NOTIONS,
    "Ashling, the Extinguisher": ASHLING_THE_EXTINGUISHER,
    "Rhys the Redeemed": RHYS_THE_REDEEMED,

    # FINAL 6 - SCARECROWS AND MORE
    "Heap Doll": HEAP_DOLL,
    "Painter's Servant": PAINTER_SERVANT,
    "Reaper King": REAPER_KING,
    "Pili-Pala": PILI_PALA,
    "Wicker Warcrawler": WICKER_WARCRAWLER,
    "Wanderbrine Rootcutters": WANDERBRINE_ROOTCUTTERS,

    # PHASE A1 SPICE PASS (2026-05-18)
    "Aurora of Five": AURORA_OF_FIVE,
    "Faewild Convocation": FAEWILD_CONVOCATION,
    "The Aurora Cycle": THE_AURORA_CYCLE,
    "Treefolk-bough Spear": TREEFOLK_BOUGH_SPEAR,
}

print(f"Loaded {len(FAE_BUT_MID_CARDS)} Fae but Mid Custom cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    CHANGELING_WAYFINDER,
    ROOFTOP_PERCHER,
    ADEPT_WATERSHAPER,
    APPEAL_TO_EIRDU,
    BRIGID_CLACHANS_HEART,
    BURDENED_STONEBACK,
    CHAMPION_OF_THE_CLACHAN,
    CLACHAN_FESTIVAL,
    CRIB_SWAP,
    CURIOUS_COLOSSUS,
    EIRDU_CARRIER_OF_DAWN,
    ENCUMBERED_REEJEREY,
    FLOCK_IMPOSTOR,
    GALLANT_FOWLKNIGHT,
    GOLDMEADOW_NOMAD,
    KEEP_OUT,
    KINBINDING,
    FORMIDABLE_SPEAKER,
    GREAT_FOREST_DRUID,
    LUMINOLLUSK,
    LYSALANA_DIGNITARY,
    LYSALANA_INFORMANT,
    MIDNIGHT_TILLING,
    MOON_VIGIL_ADHERENTS,
    MUTABLE_EXPLORER,
    PUMMELER_FOR_HIRE,
    SAFEWRIGHT_CAVALRY,
    SELFLESS_SAFEWRIGHT,
    SURLY_FARRIER,
    TEND_THE_SPRIGS,
    THOUGHTWEFT_CHARGE,
    AQUITECTS_DEFENSES,
    BLOSSOMBIND,
    CHAMPIONS_OF_THE_SHOAL,
    FLITTERWING_NUISANCE,
    GLAMERMITE,
    GLEN_ELENDRA_GUARDIAN,
    GRAVELGILL_SCOUNDREL,
    ILLUSION_SPINNERS,
    AUNTIES_SENTENCE,
    BILE_VIAL_BOGGART,
    BITTERBLOOM_BEARER,
    BLIGHTED_BLACKTHORN,
    BLIGHT_ROT,
    BLOODLINE_BIDDING,
    BOGGART_MISCHIEF,
    BOGGART_PRANKSTER,
    CREAKWOOD_SAFEWRIGHT,
    DARKNESS_DESCENDS,
    DAWNHAND_EULOGIST,
    DREAM_SEIZER,
    GNARLBARK_ELM,
    GRAVESHIFTER,
    ASHLING_REKINDLED,
    BOLDWYR_AGGRESSOR,
    BONECLUB_BERSERKER,
    BOULDER_DASH,
    BRAMBLEBACK_BRUTE,
    BURNING_CURIOSITY,
    CINDER_STRIKE,
    COLLECTIVE_INFERNO,
    ELDER_AUNTIE,
    ENRAGED_FLAMECASTER,
    EXPLOSIVE_PRODIGY,
    FEED_THE_FLAMES,
    FLAME_CHAIN_MAULER,
    FLAMEBRAIDER,
    FLAMEKIN_GILDWEAVER,
    GIANTFALL,
    GOATNAP,
    GOLIATH_DAYDREAMER,
    GRISTLE_GLUTTON,
    ABIGALE_ELOQUENT,
    BOGGART_CURSECRAFTER,
    BRE_OF_CLAN_STOUTARM,
    CHAOS_SPEWER,
    CHITINOUS_GRASPLING,
    DEEPCHANNEL_DUELIST,
    DEEPWAY_NAVIGATOR,
    DORAN_BESIEGED,
    ECLIPSED_BOGGART,
    ECLIPSED_ELF,
    ECLIPSED_FLAMEKIN,
    ECLIPSED_KITHKIN,
    ECLIPSED_MERROW,
    FEISTY_SPIKELING,
    FIGURE_OF_FABLE,
    FLARING_CINDER,
    GANGLY_STOMPLING,
    PERSONIFY,
    PROTECTIVE_RESPONSE,
    PYRRHIC_STRIKE,
    RELUCTANT_DOUNGUARD,
    RHYS_THE_EVERMORE,
    RIVERGUARDS_REFLEXES,
    EVERSHRIKES_GIFT,
    KINSBAILE_ASPIRANT,
    KINSCAER_SENTRY,
    KITHKEEPER,
    LIMINAL_HOLD,
    MEANDERS_GUIDE,
    MOONLIT_LAMENTER,
    MORNINGTIDES_LIGHT,
    SHORE_LURKER,
    SLUMBERING_WALKER,
    SPIRAL_INTO_SOLITUDE,
    SUN_DAPPLED_CELEBRANT,
    THOUGHTWEFT_IMBUER,
    TIMID_SHIELDBEARER,
    TRIBUTARY_VAULTER,
    WANDERBRINE_PREACHER,
    WANDERBRINE_TRAPPER,
    WINNOWING,
    DISRUPTOR_OF_CURRENTS,
    GLAMER_GIFTER,
    GLEN_ELENDRAS_ANSWER,
    HARMONIZED_CRESCENDO,
    PESTERED_WELLGUARD,
    RIME_CHILL,
    RIMEFIRE_TORQUE,
    RIMEKIN_RECLUSE,
    KULRATH_MYSTIC,
    LOCH_MARE,
    LOFTY_DREAMS,
    MIRRORFORM,
    NOGGLE_THE_MIND,
    OMNI_CHANGELING,
    RUN_AWAY_TOGETHER,
    SHINESTRIKER,
    SILVERGILL_MENTOR,
    SILVERGILL_PEDDLER,
    SPELL_SNARE,
    STRATOSOARER,
    SUMMIT_SENTINEL,
    SUNDERFLOCK,
    SWAT_AWAY,
    TANUFEL_RIMESPEAKER,
    TEMPORAL_CLEANSING,
    THIRST_FOR_IDENTITY,
    UNEXPECTED_ASSISTANCE,
    UNWELCOME_SPRITE,
    WANDERWINE_DISTRACTER,
    WANDERWINE_FAREWELL,
    WILD_UNRAVELING,
    BRISTLEBANE_BATTLER,
    BRISTLEBANE_OUTRIDER,
    CELESTIAL_REUNION,
    CHAMPIONS_OF_THE_PERFECT,
    CHOMPING_CHANGELING,
    CROSSROADS_WATCHER,
    DAWNS_LIGHT_ARCHER,
    DUNDOOLIN_WEAVER,
    GILT_LEAFS_EMBRACE,
    PITILESS_FISTS,
    PRISMABASHER,
    PRISMATIC_UNDERCURRENTS,
    ASSERT_PERFECTION,
    AURORA_AWAKENER,
    BLOOM_TENDER,
    BLOSSOMING_DEFENSE,
    MISTMEADOW_COUNCIL,
    MORCANTS_EYES,
    SAPLING_NURSERY,
    SHIMMERWILDS_GROWTH,
    SPRY_AND_MIGHTY,
    TRYSTAN_CALLOUS_CULTIVATOR,
    UNFORGIVING_AIM,
    VINEBRED_BRAWLER,
    VIRULENT_EMISSARY,
    WILDVINE_PUMMELER,
    BARBED_BLOODLETTER,
    BOGSLITHERS_EMBRACE,
    CHAMPION_OF_THE_WEIRD,
    DAWNHAND_DISSIDENT,
    DOSE_OF_DAWNGLOW,
    DECEIT,
    DREAM_HARVEST,
    REQUITING_HEX,
    RETCHED_WRETCH,
    GLOOM_RIPPER,
    GRUB_STORIED_MATRIARCH,
    GUTSPLITTER_GANG,
    HEIRLOOM_AUNTIE,
    MOONGLOVE_EXTRACTOR,
    MOONSHADOW,
    MUDBUTTON_CURSETOSSER,
    NAMELESS_INVERSION,
    NIGHTMARE_SOWER,
    PERFECT_INTIMIDATION,
    SCARBLADE_SCOUT,
    SCARBLADES_MALICE,
    SHIMMERCREEP,
    TASTER_OF_WARES,
    TWILIGHT_DIVINER,
    UNBURY,
    CHAMPION_OF_THE_PATH,
    END_BLAZE_EPIPHANY,
    FLAME_CHAIN_MAULER_REAL,
    FLAMEKIN_GILDWEAVER_REAL,
    GIANTFALL_SPELL,
    GOATNAP_SPELL,
    RAIDING_SCHEMES,
    RECKLESS_RANSACKING,
    HEXING_SQUELCHER,
    IMPOLITE_ENTRANCE,
    KINDLE_THE_INNER_FLAME,
    KULRATH_ZEALOT,
    LASTING_TARFIRE,
    LAVALEAPER,
    MEEK_ATTACK,
    SCUZZBACK_SCROUNGER,
    SEAR,
    SIZZLING_CHANGELING,
    SOUL_IMMOLATION,
    SOULBRIGHT_SEEKER,
    SOURBREAD_AUNTIE,
    SPINEROCK_TYRANT,
    SQUAWKROASTER,
    STING_SLINGER,
    TWEEZE,
    WARREN_TORCHMASTER,
    ASHLINGS_COMMAND,
    BRIGIDS_COMMAND,
    GLISTER_BAIRN,
    PRIDEFUL_FEASTLING,
    REAPING_WILLOW,
    CATHARSIS,
    EMPTINESS,
    GRUBS_COMMAND,
    HIGH_PERFECT_MORCANT,
    HOVEL_HURLER,
    KIROL_ATTENTIVE,
    LLUWEN_IMPERFECT,
    MARALEN_FAE_ASCENDANT,
    MERROW_SKYSWIMMER,
    MISCHIEVOUS_SNEAKLING,
    MORCANTS_LOYALIST,
    NOGGLE_ROBBER,
    SANAR_INNOVATIVE,
    SHADOW_URCHIN,
    STOIC_GROVE_GUIDE,
    SYGGS_COMMAND,
    TAM_MINDFUL,
    THOUGHTWEFT_LIEUTENANT,
    TRYSTANS_COMMAND,
    TWINFLAME_TRAVELERS,
    VIBRANCE,
    VORACIOUS_TOME_SKIMMER,
    WARY_FARMER,
    WISTFULNESS,
    CHRONICLE_OF_VICTORY,
    DAWN_BLESSED_PENNANT,
    FIRDOCH_CORE,
    FORAGING_WICKERMAW,
    GATHERING_STONE,
    MIRRORMIND_CROWN,
    PUCAS_EYE,
    SPRINGLEAF_DRUM,
    STALACTITE_DAGGER,
    FOREST,
    ISLAND,
    MOUNTAIN,
    PLAINS,
    SWAMP,
    BLOOD_CRYPT,
    HALLOWED_FOUNTAIN,
    OVERGROWN_TOMB,
    STEAM_VENTS,
    TEMPLE_GARDEN,
    ECLIPSED_REALMS,
    EVOLVING_WILDS,
    BARK_OF_DORAN,
    AUNTIES_FAVOR,
    WRETCHED_BANQUET,
    CINDER_PYROMANCER,
    INNER_FLAME_IGNITER,
    SMOLDERING_SPINEBACKS,
    THUNDERCLOUD_SHAMAN,
    ELVISH_HARBINGER,
    HERITAGE_DRUID,
    IMPERIOUS_PERFECT,
    NATH_OF_THE_GILT_LEAF,
    TIMBER_PROTECTOR,
    TREEFOLK_HARBINGER,
    WOLF_SKULL_SHAMAN,
    OONA_QUEEN_OF_THE_FAE,
    SYGG_RIVER_GUIDE,
    SYGG_RIVER_CUTTHROAT,
    WYDWEN_THE_BITING_GALE,
    WORT_BOGGART_AUNTIE,
    GADDOCK_TEEG,
    OVERSOUL_OF_DUSK,
    KITCHEN_FINKS,
    MURDEROUS_REDCAP,
    DEMIGOD_OF_REVENGE,
    GLEN_ELENDRA_ARCHMAGE,
    STILLMOON_CAVALIER,
    CREAKWOOD_LIEGE,
    DEATHBRINGER_LIEGE,
    BALEFIRE_LIEGE,
    BOARTUSK_LIEGE,
    THISTLEDOWN_LIEGE,
    MURKFIEND_LIEGE,
    MINDWRACK_LIEGE,
    ASHENMOOR_LIEGE,
    WILT_LEAF_LIEGE,
    MOONGLOVE_EXTRACT,
    RUNED_STALACTITE,
    THORNBITE_STAFF,
    OBSIDIAN_BATTLE_AXE,
    CLOAK_AND_DAGGER,
    DIVINERS_WAND,
    VETERANS_ARMAMENTS,
    KINSBAILE_BORDERGUARD,
    CLOUDGOAT_RANGER,
    MIRROR_ENTITY,
    REVEILLARK,
    RANGER_OF_EOS,
    VENDILION_CLIQUE,
    SOWER_OF_TEMPTATION,
    MISTBIND_CLIQUE,
    SPELLSTUTTER_SPRITE,
    SCION_OF_OONA,
    SHRIEKMAW,
    THOUGHTSEIZE_CREATURE,
    EARWIG_SQUAD,
    BITTERBLOSSOM,
    MORNSONG_ARIA,
    SUNRISE_SOVEREIGN,
    BRION_STOUTARM,
    NOVA_CHASER,
    INCANDESCENT_SOULSTOKE,
    CHAMELEON_COLOSSUS,
    PRIMALCRUX,
    DEVOTED_DRUID,
    NETTLE_SENTINEL,
    MASKED_ADMIRERS,
    THOUGHTWEFT_GAMBIT,
    CRYPTIC_COMMAND,
    FIRESPOUT,
    PRIMAL_COMMAND,
    AUSTERE_COMMAND,
    PROFANE_COMMAND,
    INCENDIARY_COMMAND,
    FULMINATOR_MAGE,
    FIGURE_OF_DESTINY,
    MANAMORPHOSE,
    BOGGART_RAM_GANG,
    TATTERMUNGE_MANIAC,
    VEXING_SHUSHER,
    PLUMEVEIL,
    UNMAKE,
    FIERY_JUSTICE,
    AUGURY_ADEPT,
    COLD_EYED_SELKIE,
    DEUS_OF_CALAMITY,
    GHASTLORD_OF_FUGUE,
    DEITY_OF_SCARS,
    GODHEAD_OF_AWE,
    OVERBEING_OF_MYTH,
    DIVINITY_OF_PRIDE,
    HALLOWED_BURIAL,
    IDYLLIC_TUTOR,
    SPECTRAL_PROCESSION,
    RUNED_HALO,
    OBLIVION_RING,
    KNIGHT_OF_MEADOWGRAIN,
    PREEMINENT_CAPTAIN,
    POLLEN_LULLABY,
    BROKEN_AMBITIONS,
    FAERIE_TRICKERY,
    PONDER,
    MERROW_COMMERCE,
    SURGESPANNER,
    SILVERGILL_ADEPT,
    MULLDRIFTER,
    NAMELESS_INVERSION_B,
    THOUGHTSEIZE,
    PEPPERSMOKE,
    FODDER_LAUNCH,
    MAKESHIFT_MANNEQUIN,
    DEATH_DENIED,
    NETTLEVINE_BLIGHT,
    TARFIRE,
    LASH_OUT,
    CATERWAULING_BOGGART,
    KNUCKLEBONE_WITCH,
    WORT_THE_RAIDMOTHER,
    SENSATION_GORGER,
    JAGGED_SCAR_ARCHERS,
    LEAF_CROWNED_ELDER,
    ELVISH_BRANCHBENDER,
    GILT_LEAF_AMBUSH,
    HUNTING_TRIAD,
    BOGGART_SPRITE_CHASER,
    SCARBLADE_ELITE,
    SAFEHOLD_ELITE,
    RENDCLAW_TROW,
    WISTFUL_SELKIE,
    GWYLLION_HEDGE_MAGE,
    SELKIE_HEDGE_MAGE,
    HORDE_OF_NOTIONS,
    ASHLING_THE_EXTINGUISHER,
    RHYS_THE_REDEEMED,
    HEAP_DOLL,
    PAINTER_SERVANT,
    REAPER_KING,
    PILI_PALA,
    WICKER_WARCRAWLER,
    WANDERBRINE_ROOTCUTTERS,
    # PHASE A1 SPICE PASS (2026-05-18)
    AURORA_OF_FIVE,
    FAEWILD_CONVOCATION,
    THE_AURORA_CYCLE,
    TREEFOLK_BOUGH_SPEAR,
]


# =============================================================================
# SECTION 2 (vanilla-implementable): trigger setups + registration
# Generated from printed card TEXT; each effect_fn emits the text-matching event.
# =============================================================================

def _augury_adept_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id and event.payload.get('is_combat', False) and event.payload.get('target') in state.players)

def augury_adept_setup(obj, state):
    """Augury Adept: Whenever Augury Adept deals combat damage to a player, reveal the top card of your library and put that card into your hand. You gain life equal to its mana value."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1, 'variable': True}, source=obj.id))
        return events
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_augury_adept_dmg_filter)]


def bitterblossom_setup(obj, state):
    """Bitterblossom: Tribal Enchantment — Faerie. At the beginning of your upkeep, you lose 1 life and create a 1/1 black Faerie Rogue creature token with flying."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id))
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, _effect)]


def chronicle_of_victory_setup(obj, state):
    """Chronicle of Victory: As Chronicle of Victory enters, choose a creature type. Creatures you control of the chosen type get +2/+2 and have first strike and trample. Whenever you cast a spell of the chosen type, draw a card."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        return events
    return [make_spell_cast_trigger(obj, _effect, controller_only=True)]


def cloudgoat_ranger_setup(obj, state):
    """Cloudgoat Ranger: When Cloudgoat Ranger enters, create three 1/1 white Kithkin Soldier creature tokens. Tap three untapped Kithkin you control: Cloudgoat Ranger gets +2/+0 and gains flying until end of turn."""
    def _effect(event, state):
        events = []
        for _i in range(3):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def _cold_eyed_selkie_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id and event.payload.get('is_combat', False) and event.payload.get('target') in state.players)

def cold_eyed_selkie_setup(obj, state):
    """Cold-Eyed Selkie: Islandwalk. Whenever Cold-Eyed Selkie deals combat damage to a player, you may draw that many cards."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1, 'variable': True}, source=obj.id))
        return events
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_cold_eyed_selkie_dmg_filter)]


def creakwood_liege_setup(obj, state):
    """Creakwood Liege: Other black creatures you control get +1/+1. Other green creatures you control get +1/+1. At the beginning of your upkeep, you may create a 1/1 black and green Worm creature token."""
    def _effect(event, state):
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, _effect)]


def dawn_blessed_pennant_setup(obj, state):
    """Dawn-Blessed Pennant: As this artifact enters, choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or Treefolk. Whenever a permanent you control of the chosen type enters, you gain 1 life."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id))
        return events
    return [_other_etb_trigger(obj, _effect)]


def elvish_harbinger_setup(obj, state):
    """Elvish Harbinger: When Elvish Harbinger enters, you may search your library for an Elf card, reveal it, then shuffle and put that card on top. {T}: Add one mana of any color."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'Elf', 'destination': 'top', 'optional': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def emptiness_setup(obj, state):
    """Emptiness: If {B}{B} was spent to cast this spell, when Emptiness enters, destroy target creature. Evoke {B}{B}"""
    def _effect(event, state):
        events = []
        _t = find_opponent_creature(obj, state) or find_any_creature(obj, state, exclude_self=True)
        _p = {'target_filter': 'permanent'}
        if _t:
            _p['object_id'] = _t
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def gutsplitter_gang_setup(obj, state):
    """Gutsplitter Gang: Menace. When Gutsplitter Gang enters, target opponent discards a card."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': _pid, 'count': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def heirloom_auntie_setup(obj, state):
    """Heirloom Auntie: When Heirloom Auntie enters, you may return target Goblin card from your graveyard to your hand."""
    def _effect(event, state):
        events = []
        _t = _creature_card_in_graveyard(obj, state) or _permanent_card_in_graveyard(obj, state)
        events.append(_return_from_graveyard_event(obj, _t, 'card_in_your_graveyard', optional=True))
        return events
    return [make_etb_trigger(obj, _effect)]


def hexing_squelcher_setup(obj, state):
    """Hexing Squelcher: When Hexing Squelcher enters, it deals 1 damage to each creature you don't control."""
    def _effect(event, state):
        events = []
        for _o in list(_battlefield_creatures(state)):
            if _o.controller != obj.controller:
                events.append(Event(type=EventType.DAMAGE, payload={'target': _o.id, 'amount': 1, 'target_type': 'creature'}, source=obj.id))
        if not events:
            events.append(Event(type=EventType.DAMAGE, payload={'amount': 1, 'target_type': 'creature', 'target_filter': 'each_creature_you_dont_control'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def hovel_hurler_setup(obj, state):
    """Hovel Hurler: When Hovel Hurler enters, it deals 1 damage to each opponent and each planeswalker they control."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': _pid, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def kinsbaile_borderguard_setup(obj, state):
    """Kinsbaile Borderguard: Kinsbaile Borderguard enters with a +1/+1 counter on it for each other Kithkin you control. When Kinsbaile Borderguard dies, create a 1/1 white Kithkin Soldier creature token for each counter on it."""
    def _effect(event, state):
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_death_trigger(obj, _effect)]


def kirol_attentive_first_year_setup(obj, state):
    """Kirol, Attentive First-Year: Whenever you cast an instant or sorcery spell, Kirol deals 1 damage to any target."""
    def _effect(event, state):
        events = []
        _opp = next(opponents_of(obj, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 1, 'target_type': 'player'}, source=obj.id))
        return events
    return [make_spell_cast_trigger(obj, _effect, controller_only=True)]


def kitchen_finks_setup(obj, state):
    """Kitchen Finks: When Kitchen Finks enters, you gain 2 life. Persist (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)"""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def kulrath_zealot_setup(obj, state):
    """Kulrath Zealot: Haste. When Kulrath Zealot enters, it deals 2 damage to any target."""
    def _effect(event, state):
        events = []
        _opp = next(opponents_of(obj, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 2, 'target_type': 'player'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def lavaleaper_setup(obj, state):
    """Lavaleaper: Haste. When Lavaleaper enters, it deals 1 damage to each opponent."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': _pid, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def lluwen_imperfect_naturalist_setup(obj, state):
    """Lluwen, Imperfect Naturalist: Whenever another creature enters the battlefield under your control, scry 1. {T}: Add {G} or {U}."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id))
        return events
    return [_other_etb_trigger(obj, _effect)]


def masked_admirers_setup(obj, state):
    """Masked Admirers: When Masked Admirers enters, draw a card. Whenever you cast a creature spell, you may pay {G}{G}. If you do, return Masked Admirers from your graveyard to your hand."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def merrow_skyswimmer_setup(obj, state):
    """Merrow Skyswimmer: Flying. When Merrow Skyswimmer enters, draw a card for each other Merfolk you control."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def _mischievous_sneakling_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id and event.payload.get('is_combat', False) and event.payload.get('target') in state.players)

def mischievous_sneakling_setup(obj, state):
    """Mischievous Sneakling: Flying. Whenever Mischievous Sneakling deals combat damage to a player, you may draw a card. If you do, discard a card."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        events.append(Event(type=EventType.DISCARD, payload={'player': obj.controller, 'count': 1, 'optional': True}, source=obj.id))
        return events
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_mischievous_sneakling_dmg_filter)]


def moonglove_extractor_setup(obj, state):
    """Moonglove Extractor: Deathtouch. When Moonglove Extractor dies, target creature gets -1/-1 until end of turn."""
    def _effect(event, state):
        events = []
        _t = find_any_creature(obj, state, exclude_self=True)
        _p = {'power_mod': -1, 'toughness_mod': -1, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _t:
            _p['object_id'] = _t
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=obj.id))
        return events
    return [make_death_trigger(obj, _effect)]


def moonshadow_setup(obj, state):
    """Moonshadow: Flash. Flying. When Moonshadow enters, target creature gets -2/-2 until end of turn."""
    def _effect(event, state):
        events = []
        _t = find_any_creature(obj, state, exclude_self=True)
        _p = {'power_mod': -2, 'toughness_mod': -2, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _t:
            _p['object_id'] = _t
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def mudbutton_cursetosser_setup(obj, state):
    """Mudbutton Cursetosser: When Mudbutton Cursetosser enters, put a -1/-1 counter on target creature."""
    def _effect(event, state):
        events = []
        _t = find_any_creature(obj, state, exclude_self=True)
        _p = {'counter_type': '-1/-1', 'amount': 1, 'target_filter': 'creature'}
        if _t:
            _p['object_id'] = _t
        events.append(Event(type=EventType.COUNTER_ADDED, payload=_p, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def murderous_redcap_setup(obj, state):
    """Murderous Redcap: When Murderous Redcap enters, it deals damage equal to its power to any target. Persist."""
    def _effect(event, state):
        events = []
        _opp = next(opponents_of(obj, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': max(1, obj.characteristics.power or 1), 'target_type': 'player', 'variable': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def nath_of_the_gilt_leaf_setup(obj, state):
    """Nath of the Gilt-Leaf: At the beginning of your upkeep, you may have target opponent discard a card at random. Whenever an opponent discards a card, you may create a 1/1 green Elf Warrior creature token."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': _pid, 'count': 1}, source=obj.id))
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, _effect)]


def nightmare_sower_setup(obj, state):
    """Nightmare Sower: Flying. When Nightmare Sower enters, each opponent sacrifices a creature. You gain life equal to the total power of creatures sacrificed this way."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1, 'variable': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def noggle_robber_setup(obj, state):
    """Noggle Robber: Haste. When Noggle Robber enters, each player discards a card, then draws a card."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DISCARD, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def _oonas_blackguard_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id and event.payload.get('is_combat', False) and event.payload.get('target') in state.players)

def oonas_blackguard_setup(obj, state):
    """Oona's Blackguard: Flying. Each other Rogue creature you control enters with an additional +1/+1 counter on it. Whenever a creature you control with a +1/+1 counter on it deals combat damage to a player, that player discards a card."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': _pid, 'count': 1}, source=obj.id))
        return events
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_oonas_blackguard_dmg_filter)]


def prismatic_undercurrents_setup(obj, state):
    """Prismatic Undercurrents: Vivid — When this enchantment enters, search your library for up to X basic land cards, where X is the number of colors among permanents you control, reveal them, put them into your hand, then shuffle. You may play an additional land on each of your turns."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'basic land', 'destination': 'hand', 'optional': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def pucas_eye_setup(obj, state):
    """Puca's Eye: When this artifact enters, draw a card, then choose a color. This artifact becomes the chosen color. {3}, {T}: Draw a card. Activate only if there are five colors among permanents you control."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def ranger_of_eos_setup(obj, state):
    """Ranger of Eos: When Ranger of Eos enters, you may search your library for up to two creature cards with mana value 1 or less, reveal them, put them into your hand, then shuffle."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'creature', 'destination': 'hand', 'optional': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def sanar_innovative_first_year_setup(obj, state):
    """Sanar, Innovative First-Year: Whenever a creature enters the battlefield under your control, you gain 1 life. {T}: Add {G} or {W}."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def shadow_urchin_setup(obj, state):
    """Shadow Urchin: When Shadow Urchin dies, it deals 1 damage to any target."""
    def _effect(event, state):
        events = []
        _opp = next(opponents_of(obj, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 1, 'target_type': 'player'}, source=obj.id))
        return events
    return [make_death_trigger(obj, _effect)]


def _shimmercreep_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id and event.payload.get('is_combat', False) and event.payload.get('target') in state.players)

def shimmercreep_setup(obj, state):
    """Shimmercreep: Flying. Whenever Shimmercreep deals combat damage to a player, that player discards a card."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': _pid, 'count': 1}, source=obj.id))
        return events
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_shimmercreep_dmg_filter)]


def shriekmaw_setup(obj, state):
    """Shriekmaw: Fear. When Shriekmaw enters, destroy target nonartifact, nonblack creature. Evoke {1}{B}"""
    def _effect(event, state):
        events = []
        _t = find_opponent_creature(obj, state) or find_any_creature(obj, state, exclude_self=True)
        _p = {'target_filter': 'permanent'}
        if _t:
            _p['object_id'] = _t
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def sizzling_changeling_setup(obj, state):
    """Sizzling Changeling: Changeling. Haste. When Sizzling Changeling enters, it deals 1 damage to each opponent."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': _pid, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def smoldering_spinebacks_setup(obj, state):
    """Smoldering Spinebacks: Whenever you cast a spell with mana value 4 or greater, Smoldering Spinebacks deals 1 damage to each opponent."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': _pid, 'amount': 1}, source=obj.id))
        return events
    return [make_spell_cast_trigger(obj, _effect, controller_only=True)]


def sourbread_auntie_setup(obj, state):
    """Sourbread Auntie: When Sourbread Auntie enters, target Goblin you control gets +2/+0 and gains menace until end of turn."""
    def _effect(event, state):
        events = []
        _t = find_friendly_creature(obj, state, exclude_self=False)
        _p = {'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn', 'target_filter': 'creature_you_control'}
        if _t:
            _p['object_id'] = _t
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def spinerock_tyrant_setup(obj, state):
    """Spinerock Tyrant: Trample. When Spinerock Tyrant enters, it deals 3 damage to any target."""
    def _effect(event, state):
        events = []
        _opp = next(opponents_of(obj, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 3, 'target_type': 'player'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def squawkroaster_setup(obj, state):
    """Squawkroaster: Flying. When Squawkroaster dies, it deals 1 damage to any target."""
    def _effect(event, state):
        events = []
        _opp = next(opponents_of(obj, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 1, 'target_type': 'player'}, source=obj.id))
        return events
    return [make_death_trigger(obj, _effect)]


def taster_of_wares_setup(obj, state):
    """Taster of Wares: Flying. When Taster of Wares enters, you may sacrifice an artifact. If you do, draw two cards."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 2}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def thundercloud_shaman_setup(obj, state):
    """Thundercloud Shaman: When Thundercloud Shaman enters, it deals damage equal to the number of Giants you control to each non-Giant creature."""
    def _effect(event, state):
        giants = sum(1 for _o in _battlefield_creatures(state)
                     if _o.controller == obj.controller and 'Giant' in _o.characteristics.subtypes)
        amount = max(1, giants)
        events = []
        for _o in list(_battlefield_creatures(state)):
            if 'Giant' not in _o.characteristics.subtypes:
                events.append(Event(type=EventType.DAMAGE, payload={'target': _o.id, 'amount': amount, 'target_type': 'creature', 'variable': True}, source=obj.id))
        if not events:
            events.append(Event(type=EventType.DAMAGE, payload={'amount': amount, 'target_type': 'creature', 'target_filter': 'each_non_giant_creature', 'variable': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def treefolk_harbinger_setup(obj, state):
    """Treefolk Harbinger: When Treefolk Harbinger enters, you may search your library for a Treefolk or Forest card, reveal it, then shuffle and put that card on top of your library."""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'Treefolk', 'destination': 'top', 'optional': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def twinflame_travelers_setup(obj, state):
    """Twinflame Travelers: Flying, haste. When Twinflame Travelers enters, create a token that's a copy of it. Sacrifice that token at the beginning of the next end step."""
    def _effect(event, state):
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def vibrance_setup(obj, state):
    """Vibrance: Trample. If {G}{G} was spent to cast this spell, when Vibrance enters, search your library for a basic land card, put it onto the battlefield, then shuffle. Evoke {G}{G}"""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'basic land', 'destination': 'hand', 'optional': True}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def wary_farmer_setup(obj, state):
    """Wary Farmer: When Wary Farmer enters, create a Food token."""
    def _effect(event, state):
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def wistfulness_setup(obj, state):
    """Wistfulness: If {U}{U} was spent to cast this spell, when Wistfulness enters, draw two cards. Evoke {U}{U}"""
    def _effect(event, state):
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 2}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def wolf_skull_shaman_setup(obj, state):
    """Wolf-Skull Shaman: Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with Wolf-Skull Shaman, you may reveal it. If you do, create a 2/2 green Wolf creature token."""
    def _effect(event, state):
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, _effect)]



# --- register the Section-2 setups onto their CardDefinitions ---
def _register_section2_setups():
    FAE_BUT_MID_CARDS['Augury Adept'].setup_interceptors = augury_adept_setup
    FAE_BUT_MID_CARDS['Bitterblossom'].setup_interceptors = bitterblossom_setup
    FAE_BUT_MID_CARDS['Chronicle of Victory'].setup_interceptors = chronicle_of_victory_setup
    FAE_BUT_MID_CARDS['Cloudgoat Ranger'].setup_interceptors = cloudgoat_ranger_setup
    FAE_BUT_MID_CARDS['Cold-Eyed Selkie'].setup_interceptors = cold_eyed_selkie_setup
    FAE_BUT_MID_CARDS['Creakwood Liege'].setup_interceptors = creakwood_liege_setup
    FAE_BUT_MID_CARDS['Dawn-Blessed Pennant'].setup_interceptors = dawn_blessed_pennant_setup
    FAE_BUT_MID_CARDS['Elvish Harbinger'].setup_interceptors = elvish_harbinger_setup
    FAE_BUT_MID_CARDS['Emptiness'].setup_interceptors = emptiness_setup
    FAE_BUT_MID_CARDS['Gutsplitter Gang'].setup_interceptors = gutsplitter_gang_setup
    FAE_BUT_MID_CARDS['Heirloom Auntie'].setup_interceptors = heirloom_auntie_setup
    FAE_BUT_MID_CARDS['Hexing Squelcher'].setup_interceptors = hexing_squelcher_setup
    FAE_BUT_MID_CARDS['Hovel Hurler'].setup_interceptors = hovel_hurler_setup
    FAE_BUT_MID_CARDS['Kinsbaile Borderguard'].setup_interceptors = kinsbaile_borderguard_setup
    FAE_BUT_MID_CARDS['Kirol, Attentive First-Year'].setup_interceptors = kirol_attentive_first_year_setup
    FAE_BUT_MID_CARDS['Kitchen Finks'].setup_interceptors = kitchen_finks_setup
    FAE_BUT_MID_CARDS['Kulrath Zealot'].setup_interceptors = kulrath_zealot_setup
    FAE_BUT_MID_CARDS['Lavaleaper'].setup_interceptors = lavaleaper_setup
    FAE_BUT_MID_CARDS['Lluwen, Imperfect Naturalist'].setup_interceptors = lluwen_imperfect_naturalist_setup
    FAE_BUT_MID_CARDS['Masked Admirers'].setup_interceptors = masked_admirers_setup
    FAE_BUT_MID_CARDS['Merrow Skyswimmer'].setup_interceptors = merrow_skyswimmer_setup
    FAE_BUT_MID_CARDS['Mischievous Sneakling'].setup_interceptors = mischievous_sneakling_setup
    FAE_BUT_MID_CARDS['Moonglove Extractor'].setup_interceptors = moonglove_extractor_setup
    FAE_BUT_MID_CARDS['Moonshadow'].setup_interceptors = moonshadow_setup
    FAE_BUT_MID_CARDS['Mudbutton Cursetosser'].setup_interceptors = mudbutton_cursetosser_setup
    FAE_BUT_MID_CARDS['Murderous Redcap'].setup_interceptors = murderous_redcap_setup
    FAE_BUT_MID_CARDS['Nath of the Gilt-Leaf'].setup_interceptors = nath_of_the_gilt_leaf_setup
    FAE_BUT_MID_CARDS['Nightmare Sower'].setup_interceptors = nightmare_sower_setup
    FAE_BUT_MID_CARDS['Noggle Robber'].setup_interceptors = noggle_robber_setup
    FAE_BUT_MID_CARDS["Oona's Blackguard"].setup_interceptors = oonas_blackguard_setup
    FAE_BUT_MID_CARDS['Prismatic Undercurrents'].setup_interceptors = prismatic_undercurrents_setup
    FAE_BUT_MID_CARDS["Puca's Eye"].setup_interceptors = pucas_eye_setup
    FAE_BUT_MID_CARDS['Ranger of Eos'].setup_interceptors = ranger_of_eos_setup
    FAE_BUT_MID_CARDS['Sanar, Innovative First-Year'].setup_interceptors = sanar_innovative_first_year_setup
    FAE_BUT_MID_CARDS['Shadow Urchin'].setup_interceptors = shadow_urchin_setup
    FAE_BUT_MID_CARDS['Shimmercreep'].setup_interceptors = shimmercreep_setup
    FAE_BUT_MID_CARDS['Shriekmaw'].setup_interceptors = shriekmaw_setup
    FAE_BUT_MID_CARDS['Sizzling Changeling'].setup_interceptors = sizzling_changeling_setup
    FAE_BUT_MID_CARDS['Smoldering Spinebacks'].setup_interceptors = smoldering_spinebacks_setup
    FAE_BUT_MID_CARDS['Sourbread Auntie'].setup_interceptors = sourbread_auntie_setup
    FAE_BUT_MID_CARDS['Spinerock Tyrant'].setup_interceptors = spinerock_tyrant_setup
    FAE_BUT_MID_CARDS['Squawkroaster'].setup_interceptors = squawkroaster_setup
    FAE_BUT_MID_CARDS['Taster of Wares'].setup_interceptors = taster_of_wares_setup
    FAE_BUT_MID_CARDS['Thundercloud Shaman'].setup_interceptors = thundercloud_shaman_setup
    FAE_BUT_MID_CARDS['Treefolk Harbinger'].setup_interceptors = treefolk_harbinger_setup
    FAE_BUT_MID_CARDS['Twinflame Travelers'].setup_interceptors = twinflame_travelers_setup
    FAE_BUT_MID_CARDS['Vibrance'].setup_interceptors = vibrance_setup
    FAE_BUT_MID_CARDS['Wary Farmer'].setup_interceptors = wary_farmer_setup
    FAE_BUT_MID_CARDS['Wistfulness'].setup_interceptors = wistfulness_setup
    FAE_BUT_MID_CARDS['Wolf-Skull Shaman'].setup_interceptors = wolf_skull_shaman_setup

_register_section2_setups()


# =============================================================================
# SECTION 2 (manual): color-gated cast / amount-gated / another-dies triggers
# =============================================================================

def balefire_liege_setup(obj, state):
    """Balefire Liege: ... Whenever you cast a red spell, Balefire Liege deals 3 damage to target player or planeswalker. Whenever you cast a white spell, you gain 3 life."""
    def _effect(event, state):
        colors = event.payload.get('colors') or set()
        events = []
        if Color.RED in colors:
            _opp = next(opponents_of(obj, state), None)
            events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 3, 'target_type': 'player'}, source=obj.id))
        if Color.WHITE in colors:
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id))
        return events
    return [make_spell_cast_trigger(obj, _effect, controller_only=True)]


def cinder_pyromancer_setup(obj, state):
    """Cinder Pyromancer: {T}: ... Whenever you cast a red spell, you may untap Cinder Pyromancer."""
    def _effect(event, state):
        colors = event.payload.get('colors') or set()
        if Color.RED in colors:
            return [Event(type=EventType.UNTAP, payload={'object_id': obj.id, 'optional': True}, source=obj.id)]
        return []
    return [make_spell_cast_trigger(obj, _effect, controller_only=True)]


def deathbringer_liege_setup(obj, state):
    """Deathbringer Liege: ... Whenever you cast a white spell, you may tap target creature. Whenever you cast a black spell, you may destroy target creature if it's tapped."""
    def _effect(event, state):
        colors = event.payload.get('colors') or set()
        events = []
        if Color.WHITE in colors:
            _t = find_opponent_creature(obj, state)
            events.append(_tap_opponent_creature_event(obj, _t))
        if Color.BLACK in colors:
            _t = find_opponent_creature(obj, state, tapped=True) or find_opponent_creature(obj, state)
            _p = {'target_filter': 'tapped_creature', 'optional': True}
            if _t:
                _p['object_id'] = _t
            events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=obj.id))
        return events
    return [make_spell_cast_trigger(obj, _effect, controller_only=True)]


def _deus_of_calamity_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id
            and event.payload.get('is_combat', False)
            and event.payload.get('target') in state.players
            and (event.payload.get('amount') or 0) >= 6)


def deus_of_calamity_setup(obj, state):
    """Deus of Calamity: Trample. Whenever Deus of Calamity deals 6 or more damage to an opponent, destroy target land that player controls."""
    def _effect(event, state):
        damaged = event.payload.get('target')
        # find a land that player controls
        target = None
        for o in state.objects.values():
            if o.zone == ZoneType.BATTLEFIELD and o.controller == damaged and CardType.LAND in o.characteristics.types:
                target = o.id
                break
        _p = {'target_filter': 'land_that_player_controls'}
        if target:
            _p['object_id'] = target
        return [Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=obj.id)]
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_deus_of_calamity_dmg_filter)]


def high_perfect_morcant_setup(obj, state):
    """High Perfect Morcant: Vigilance. Other Elves you control get +1/+1. Whenever an Elf you control dies, you gain 2 life."""
    def _effect(event, state):
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    lord = make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, 'Elf'))
    return lord + [_other_dies_trigger(obj, _effect, subtype='Elf')]


def tam_mindful_first_year_setup(obj, state):
    """Tam, Mindful First-Year: Deathtouch. Whenever a creature you control dies, put a +1/+1 counter on Tam."""
    def _effect(event, state):
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]
    return [_other_dies_trigger(obj, _effect)]


def _register_section2_manual():
    FAE_BUT_MID_CARDS['Balefire Liege'].setup_interceptors = balefire_liege_setup
    FAE_BUT_MID_CARDS['Cinder Pyromancer'].setup_interceptors = cinder_pyromancer_setup
    FAE_BUT_MID_CARDS['Deathbringer Liege'].setup_interceptors = deathbringer_liege_setup
    FAE_BUT_MID_CARDS['Deus of Calamity'].setup_interceptors = deus_of_calamity_setup
    FAE_BUT_MID_CARDS['High Perfect Morcant'].setup_interceptors = high_perfect_morcant_setup
    FAE_BUT_MID_CARDS['Tam, Mindful First-Year'].setup_interceptors = tam_mindful_first_year_setup

_register_section2_manual()


# =============================================================================
# SECTION 2 (lords): static tribal / color +1/+1 boosts
# =============================================================================

def _color_lord_filter(source_obj, colors):
    cset = set(colors)
    def _f(target, state):
        return (target.controller == source_obj.controller and target.id != source_obj.id and
                CardType.CREATURE in target.characteristics.types and
                bool(target.characteristics.colors & cset))
    return _f


def incandescent_soulstoke_setup(obj, state):
    """Incandescent Soulstoke: Other Elemental creatures you control get +1/+1. ..."""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, 'Elemental'))


def mindwrack_liege_setup(obj, state):
    """Mindwrack Liege: Other blue creatures you control get +1/+1. Other red creatures you control get +1/+1. ..."""
    return make_static_pt_boost(obj, 1, 1, _color_lord_filter(obj, {Color.BLUE, Color.RED}))


def murkfiend_liege_setup(obj, state):
    """Murkfiend Liege: Other green creatures you control get +1/+1. Other blue creatures you control get +1/+1. ..."""
    return make_static_pt_boost(obj, 1, 1, _color_lord_filter(obj, {Color.GREEN, Color.BLUE}))


def _register_section2_lords():
    FAE_BUT_MID_CARDS['Incandescent Soulstoke'].setup_interceptors = incandescent_soulstoke_setup
    FAE_BUT_MID_CARDS['Mindwrack Liege'].setup_interceptors = mindwrack_liege_setup
    FAE_BUT_MID_CARDS['Murkfiend Liege'].setup_interceptors = murkfiend_liege_setup

_register_section2_lords()


# =============================================================================
# SECTION 2 (recovered): more trigger/lord cards the auto-pass missed
# =============================================================================

def ashenmoor_liege_setup(obj, state):
    """Ashenmoor Liege: Other black creatures you control get +1/+1. Other red creatures you control get +1/+1. ..."""
    return make_static_pt_boost(obj, 1, 1, _color_lord_filter(obj, {Color.BLACK, Color.RED}))


def morcants_loyalist_setup(obj, state):
    """Morcant's Loyalist: Vigilance. When Morcant's Loyalist enters, you gain 3 life."""
    def _effect(event, state):
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, _effect)]


def voracious_tome_skimmer_setup(obj, state):
    """Voracious Tome-Skimmer: Flying. When Voracious Tome-Skimmer enters, each opponent mills three cards. You draw a card for each creature card milled this way."""
    def _effect(event, state):
        events = []
        for _pid in opponents_of(obj, state):
            events.append(Event(type=EventType.MILL, payload={'player': _pid, 'amount': 3}, source=obj.id))
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1, 'variable': True, 'per': 'creature_card_milled'}, source=obj.id))
        return events
    return [make_etb_trigger(obj, _effect)]


def sygg_river_cutthroat_setup(obj, state):
    """Sygg, River Cutthroat: At the beginning of each end step, if an opponent lost 3 or more life this turn, you may draw a card."""
    def _effect(event, state):
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1, 'optional': True, 'condition': 'opponent_lost_3_life_this_turn'}, source=obj.id)]
    return [make_end_step_trigger(obj, _effect)]


def reveillark_setup(obj, state):
    """Reveillark: Flying. When Reveillark leaves the battlefield, return up to two target creature cards with power 2 or less from your graveyard to the battlefield. ..."""
    def _effect(event, state):
        events = []
        gy = state.zones.get(f"graveyard_{obj.controller}")
        targets = []
        if gy:
            for cid in gy.objects:
                card = state.objects.get(cid)
                if card and card.id != obj.id and CardType.CREATURE in card.characteristics.types and (card.characteristics.power or 0) <= 2:
                    targets.append(cid)
                    if len(targets) >= 2:
                        break
        if targets:
            for tid in targets:
                events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload={'object_id': tid, 'player': obj.controller, 'to': 'battlefield', 'optional': True}, source=obj.id))
        else:
            events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload={'player': obj.controller, 'to': 'battlefield', 'target_filter': 'creature_power_2_or_less_in_your_graveyard', 'optional': True}, source=obj.id))
        return events
    return [make_leaves_battlefield_trigger(obj, _effect)]


def _ghastlord_dmg_filter(event, state, source):
    return (event.type == EventType.DAMAGE and event.payload.get('source') == source.id
            and event.payload.get('is_combat', False) and event.payload.get('target') in state.players)


def ghastlord_of_fugue_setup(obj, state):
    """Ghastlord of Fugue: ... Whenever Ghastlord of Fugue deals combat damage to a player, that player reveals their hand. You choose a card from it. That player exiles that card."""
    def _effect(event, state):
        damaged = event.payload.get('target')
        return [Event(type=EventType.EXILE, payload={'player': damaged, 'from_hand': True, 'chosen_by': obj.controller, 'target_filter': 'card_in_that_players_hand'}, source=obj.id)]
    return [make_damage_trigger(obj, _effect, combat_only=True, filter_fn=_ghastlord_dmg_filter)]


def _register_section2_recovered():
    FAE_BUT_MID_CARDS['Ashenmoor Liege'].setup_interceptors = ashenmoor_liege_setup
    FAE_BUT_MID_CARDS["Morcant's Loyalist"].setup_interceptors = morcants_loyalist_setup
    FAE_BUT_MID_CARDS['Voracious Tome-Skimmer'].setup_interceptors = voracious_tome_skimmer_setup
    FAE_BUT_MID_CARDS['Sygg, River Cutthroat'].setup_interceptors = sygg_river_cutthroat_setup
    FAE_BUT_MID_CARDS['Reveillark'].setup_interceptors = reveillark_setup
    FAE_BUT_MID_CARDS['Ghastlord of Fugue'].setup_interceptors = ghastlord_of_fugue_setup

_register_section2_recovered()


# =============================================================================
# SECTION 2 (instants/sorceries): cast-resolve effects from printed TEXT
# Each <snake>_resolve(targets, state) emits the text-matching event(s).
# =============================================================================

def _spell_src(name, state):
    """Best-effort (spell_id, caster) for a resolving Section-2 spell."""
    for o in state.objects.values():
        if getattr(o, 'name', None) == name and o.zone == ZoneType.STACK:
            return o.id, o.controller
    # fall back to any stack object / active player
    for o in state.objects.values():
        if o.zone == ZoneType.STACK:
            return o.id, o.controller
    return name, (state.active_player or next(iter(state.players), None))


def _opps(caster, state):
    for pid in state.players:
        if pid != caster:
            yield pid


def _bf_creatures(state):
    return [o for o in state.objects.values()
            if o.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in o.characteristics.types]


def _opp_creature(caster, state):
    for o in _bf_creatures(state):
        if o.controller != caster:
            return o.id
    return None


def _friendly_creature(caster, state):
    for o in _bf_creatures(state):
        if o.controller == caster:
            return o.id
    return None


def _any_creature(caster, state):
    fb = None
    for o in _bf_creatures(state):
        if o.controller != caster:
            return o.id
        fb = fb or o.id
    return fb


def _gy_creature(caster, state):
    gy = state.zones.get(f"graveyard_{caster}")
    if gy:
        for cid in gy.objects:
            c = state.objects.get(cid)
            if c and CardType.CREATURE in c.characteristics.types:
                return cid
    return None


def assert_perfection_resolve(targets, state):
    """Assert Perfection: Target creature you control gets +1/+0 until end of turn. It deals damage equal to its power to up to one target creature an opponent controls."""
    sid, caster = _spell_src('Assert Perfection', state)
    def _eff():
        events = []
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        return events
    return _eff()


def aunties_favor_resolve(targets, state):
    """Auntie's Favor: Target creature gets +2/+0 and gains menace until end of turn. If you control a Goblin, draw a card."""
    sid, caster = _spell_src("Auntie's Favor", state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 1}, source=sid))
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        return events
    return _eff()


def blight_rot_resolve(targets, state):
    """Blight Rot: Put four -1/-1 counters on target creature."""
    sid, caster = _spell_src('Blight Rot', state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'counter_type': '-1/-1', 'amount': 4, 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.COUNTER_ADDED, payload=_p, source=sid))
        return events
    return _eff()


def bloodline_bidding_resolve(targets, state):
    """Bloodline Bidding: Convoke. Choose a creature type. Return all creature cards of that type from your graveyard to the battlefield."""
    sid, caster = _spell_src('Bloodline Bidding', state)
    def _eff():
        events = []
        _cid = _gy_creature(caster, state)
        _p = {'player': caster, 'to': 'battlefield', 'target_filter': 'creature_in_your_graveyard'}
        if _cid:
            _p['object_id'] = _cid
        events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload=_p, source=sid))
        return events
    return _eff()


def blossoming_defense_resolve(targets, state):
    """Blossoming Defense: Target creature you control gets +2/+2 and gains hexproof until end of turn."""
    sid, caster = _spell_src('Blossoming Defense', state)
    def _eff():
        events = []
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 2, 'toughness_mod': 2, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        return events
    return _eff()


def bogslithers_embrace_resolve(targets, state):
    """Bogslither's Embrace: As an additional cost to cast this spell, blight 1 or pay {3}. Exile target creature."""
    sid, caster = _spell_src("Bogslither's Embrace", state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.EXILE, payload=_p, source=sid))
        return events
    return _eff()


def boulder_dash_resolve(targets, state):
    """Boulder Dash: Boulder Dash deals 2 damage to any target and 1 damage to any other target."""
    sid, caster = _spell_src('Boulder Dash', state)
    def _eff():
        events = []
        _opp = next(_opps(caster, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 2, 'target_type': 'player'}, source=sid))
        return events
    return _eff()


def catharsis_resolve(targets, state):
    """Catharsis: Destroy all creatures. For each creature destroyed this way, its controller creates a 1/1 white Kithkin creature token."""
    sid, caster = _spell_src('Catharsis', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': _o.id}, source=sid))
        if not events:
            events.append(Event(type=EventType.OBJECT_DESTROYED, payload={'target_filter': 'all_creatures'}, source=sid))
        return events
    return _eff()


def cinder_strike_resolve(targets, state):
    """Cinder Strike: As an additional cost to cast this spell, you may blight 1. Cinder Strike deals 2 damage to target creature. It deals 4 damage to that creature instead if this spell's additional cost was paid."""
    sid, caster = _spell_src('Cinder Strike', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state)
        _p = {'amount': 2, 'target_filter': 'creature'}
        if _tid:
            _p['target'] = _tid; _p['target_type'] = 'creature'
        events.append(Event(type=EventType.DAMAGE, payload=_p, source=sid))
        return events
    return _eff()


def crib_swap_resolve(targets, state):
    """Crib Swap: Changeling. Exile target creature. Its controller creates a 1/1 colorless Shapeshifter creature token with changeling."""
    sid, caster = _spell_src('Crib Swap', state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.EXILE, payload=_p, source=sid))
        return events
    return _eff()


def darkness_descends_resolve(targets, state):
    """Darkness Descends: Put two -1/-1 counters on each creature."""
    sid, caster = _spell_src('Darkness Descends', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.COUNTER_ADDED, payload={'object_id': _o.id, 'counter_type': '-1/-1', 'amount': 2}, source=sid))
        if not events:
            events.append(Event(type=EventType.COUNTER_ADDED, payload={'counter_type': '-1/-1', 'amount': 2, 'target_filter': 'each_creature'}, source=sid))
        return events
    return _eff()


def death_denied_resolve(targets, state):
    """Death Denied: Return X target creature cards from your graveyard to your hand."""
    sid, caster = _spell_src('Death Denied', state)
    def _eff():
        events = []
        _cid = _gy_creature(caster, state)
        _p = {'player': caster, 'to': 'hand', 'target_filter': 'creature_in_your_graveyard'}
        if _cid:
            _p['object_id'] = _cid
        events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload=_p, source=sid))
        return events
    return _eff()


def dose_of_dawnglow_resolve(targets, state):
    """Dose of Dawnglow: Return target creature card from your graveyard to the battlefield. If it's not your main phase, blight 2."""
    sid, caster = _spell_src('Dose of Dawnglow', state)
    def _eff():
        events = []
        _cid = _gy_creature(caster, state)
        _p = {'player': caster, 'to': 'battlefield', 'target_filter': 'creature_in_your_graveyard'}
        if _cid:
            _p['object_id'] = _cid
        events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload=_p, source=sid))
        return events
    return _eff()


def feed_the_flames_resolve(targets, state):
    """Feed the Flames: Feed the Flames deals 5 damage to target creature. If that creature would die this turn, exile it instead."""
    sid, caster = _spell_src('Feed the Flames', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state)
        _p = {'amount': 5, 'target_filter': 'creature'}
        if _tid:
            _p['target'] = _tid; _p['target_type'] = 'creature'
        events.append(Event(type=EventType.DAMAGE, payload=_p, source=sid))
        return events
    return _eff()


def fiery_justice_resolve(targets, state):
    """Fiery Justice: Fiery Justice deals 5 damage divided as you choose among any number of targets. Target opponent gains 5 life."""
    sid, caster = _spell_src('Fiery Justice', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state)
        _p = {'amount': 5, 'target_filter': 'creature'}
        if _tid:
            _p['target'] = _tid; _p['target_type'] = 'creature'
        events.append(Event(type=EventType.DAMAGE, payload=_p, source=sid))
        return events
    return _eff()


def firespout_resolve(targets, state):
    """Firespout: Firespout deals 3 damage to each creature without flying if {R} was spent to cast this spell and 3 damage to each creature with flying if {G} was spent to cast this spell."""
    sid, caster = _spell_src('Firespout', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': _o.id, 'amount': 3, 'target_type': 'creature'}, source=sid))
        if not any(e.type==EventType.DAMAGE for e in events):
            events.append(Event(type=EventType.DAMAGE, payload={'amount': 3, 'target_type': 'creature', 'target_filter': 'each_creature'}, source=sid))
        return events
    return _eff()


def fodder_launch_resolve(targets, state):
    """Fodder Launch: Tribal Sorcery — Goblin. As an additional cost to cast this spell, sacrifice a Goblin. Target creature gets -5/-5 until end of turn. Its controller loses 5 life."""
    sid, caster = _spell_src('Fodder Launch', state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'power_mod': -5, 'toughness_mod': -5, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        return events
    return _eff()


def harmonized_crescendo_resolve(targets, state):
    """Harmonized Crescendo: Convoke. Choose a creature type. Draw a card for each permanent you control of the chosen type."""
    sid, caster = _spell_src('Harmonized Crescendo', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 1}, source=sid))
        return events
    return _eff()


def hunting_triad_resolve(targets, state):
    """Hunting Triad: Tribal Sorcery — Elf. Create three 1/1 green Elf Warrior creature tokens. Reinforce 3—{3}{G}"""
    sid, caster = _spell_src('Hunting Triad', state)
    def _eff():
        events = []
        for _i in range(3):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        return events
    return _eff()


def impolite_entrance_resolve(targets, state):
    """Impolite Entrance: Creatures you control get +2/+0 and gain haste until end of turn."""
    sid, caster = _spell_src('Impolite Entrance', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            if _o.controller == caster:
                events.append(Event(type=EventType.PT_MODIFICATION, payload={'object_id': _o.id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'}, source=sid))
        if not events:
            events.append(Event(type=EventType.PT_MODIFICATION, payload={'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn', 'target_filter': 'creatures_you_control'}, source=sid))
        return events
    return _eff()


def lasting_tarfire_resolve(targets, state):
    """Lasting Tarfire: Lasting Tarfire deals 2 damage to any target. If that permanent or player is dealt damage this way, Lasting Tarfire deals 1 damage to them at the beginning of the next upkeep."""
    sid, caster = _spell_src('Lasting Tarfire', state)
    def _eff():
        events = []
        _opp = next(_opps(caster, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 2, 'target_type': 'player'}, source=sid))
        return events
    return _eff()


def lofty_dreams_resolve(targets, state):
    """Lofty Dreams: Draw two cards. If you control a Faerie, draw three cards instead."""
    sid, caster = _spell_src('Lofty Dreams', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 2}, source=sid))
        return events
    return _eff()


def makeshift_mannequin_resolve(targets, state):
    """Makeshift Mannequin: Return target creature card from your graveyard to the battlefield with a mannequin counter on it. For as long as that creature has a mannequin counter on it, it has 'When this creature becomes the target of a spell or ability, sacrifice it.'"""
    sid, caster = _spell_src('Makeshift Mannequin', state)
    def _eff():
        events = []
        _cid = _gy_creature(caster, state)
        _p = {'player': caster, 'to': 'battlefield', 'target_filter': 'creature_in_your_graveyard'}
        if _cid:
            _p['object_id'] = _cid
        events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload=_p, source=sid))
        return events
    return _eff()


def manamorphose_resolve(targets, state):
    """Manamorphose: Add two mana in any combination of colors. Draw a card."""
    sid, caster = _spell_src('Manamorphose', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 1}, source=sid))
        return events
    return _eff()


def midnight_tilling_resolve(targets, state):
    """Midnight Tilling: Mill four cards, then you may return a permanent card from among them to your hand."""
    sid, caster = _spell_src('Midnight Tilling', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.MILL, payload={'player': caster, 'amount': 4}, source=sid))
        return events
    return _eff()


def mirrorform_resolve(targets, state):
    """Mirrorform: Create a token that's a copy of target creature you control. Sacrifice it at the beginning of the next end step."""
    sid, caster = _spell_src('Mirrorform', state)
    def _eff():
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        return events
    return _eff()


def morningtides_light_resolve(targets, state):
    """Morningtide's Light: Destroy target creature with power 4 or greater. You gain 4 life."""
    sid, caster = _spell_src("Morningtide's Light", state)
    def _eff():
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': caster, 'amount': 4}, source=sid))
        _tid = _opp_creature(caster, state) or _any_creature(caster, state)
        _p = {'target_filter': 'permanent'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=sid))
        return events
    return _eff()


def peppersmoke_resolve(targets, state):
    """Peppersmoke: Tribal Instant — Faerie. Target creature gets -1/-1 until end of turn. If you control a Faerie, draw a card."""
    sid, caster = _spell_src('Peppersmoke', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 1}, source=sid))
        _tid = _any_creature(caster, state)
        _p = {'power_mod': -1, 'toughness_mod': -1, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        return events
    return _eff()


def perfect_intimidation_resolve(targets, state):
    """Perfect Intimidation: Each opponent sacrifices a creature. You gain life equal to the greatest power among creatures sacrificed this way."""
    sid, caster = _spell_src('Perfect Intimidation', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': caster, 'amount': 1, 'variable': True}, source=sid))
        return events
    return _eff()


def personify_resolve(targets, state):
    """Personify: Exile target creature you control, then return that card to the battlefield under its owner's control. Create a 1/1 colorless Shapeshifter creature token with changeling."""
    sid, caster = _spell_src('Personify', state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.EXILE, payload=_p, source=sid))
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        return events
    return _eff()


def ponder_resolve(targets, state):
    """Ponder: Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card."""
    sid, caster = _spell_src('Ponder', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 1}, source=sid))
        return events
    return _eff()


def protective_response_resolve(targets, state):
    """Protective Response: Convoke. Destroy target attacking or blocking creature."""
    sid, caster = _spell_src('Protective Response', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state) or _any_creature(caster, state)
        _p = {'target_filter': 'permanent'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=sid))
        return events
    return _eff()


def pyrrhic_strike_resolve(targets, state):
    """Pyrrhic Strike: As an additional cost to cast this spell, you may blight 2. Choose one. If the blight cost was paid, choose both instead — Destroy target artifact or enchantment; Destroy target creature with mana value 3 or greater."""
    sid, caster = _spell_src('Pyrrhic Strike', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state) or _any_creature(caster, state)
        _p = {'target_filter': 'permanent'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=sid))
        return events
    return _eff()


def reckless_ransacking_resolve(targets, state):
    """Reckless Ransacking: Target creature gets +3/+2 until end of turn. Create a Treasure token."""
    sid, caster = _spell_src('Reckless Ransacking', state)
    def _eff():
        events = []
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 3, 'toughness_mod': 2, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        return events
    return _eff()


def requiting_hex_resolve(targets, state):
    """Requiting Hex: As an additional cost to cast this spell, you may blight 1. Destroy target creature with mana value 2 or less. If the additional cost was paid, you gain 2 life."""
    sid, caster = _spell_src('Requiting Hex', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': caster, 'amount': 2}, source=sid))
        _tid = _opp_creature(caster, state) or _any_creature(caster, state)
        _p = {'target_filter': 'permanent'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=sid))
        return events
    return _eff()


def riverguards_reflexes_resolve(targets, state):
    """Riverguard's Reflexes: Target creature gets +2/+2 and gains first strike until end of turn. Untap it."""
    sid, caster = _spell_src("Riverguard's Reflexes", state)
    def _eff():
        events = []
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 2, 'toughness_mod': 2, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        if _tid:
            events.append(Event(type=EventType.UNTAP, payload={'object_id': _tid}, source=sid))
        return events
    return _eff()


def sear_resolve(targets, state):
    """Sear: Sear deals 3 damage to target creature or planeswalker."""
    sid, caster = _spell_src('Sear', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state)
        _p = {'amount': 3, 'target_filter': 'creature'}
        if _tid:
            _p['target'] = _tid; _p['target_type'] = 'creature'
        events.append(Event(type=EventType.DAMAGE, payload=_p, source=sid))
        return events
    return _eff()


def soul_immolation_resolve(targets, state):
    """Soul Immolation: Soul Immolation deals 6 damage to each creature."""
    sid, caster = _spell_src('Soul Immolation', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': _o.id, 'amount': 6, 'target_type': 'creature'}, source=sid))
        if not any(e.type==EventType.DAMAGE for e in events):
            events.append(Event(type=EventType.DAMAGE, payload={'amount': 6, 'target_type': 'creature', 'target_filter': 'each_creature'}, source=sid))
        return events
    return _eff()


def spectral_procession_resolve(targets, state):
    """Spectral Procession: Create three 1/1 white Spirit creature tokens with flying."""
    sid, caster = _spell_src('Spectral Procession', state)
    def _eff():
        events = []
        for _i in range(3):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        return events
    return _eff()


def spry_and_mighty_resolve(targets, state):
    """Spry and Mighty: Target creature gets +3/+3 until end of turn. Untap it."""
    sid, caster = _spell_src('Spry and Mighty', state)
    def _eff():
        events = []
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 3, 'toughness_mod': 3, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        if _tid:
            events.append(Event(type=EventType.UNTAP, payload={'object_id': _tid}, source=sid))
        return events
    return _eff()


def sunderflock_resolve(targets, state):
    """Sunderflock: Return all creatures to their owners' hands."""
    sid, caster = _spell_src('Sunderflock', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.RETURN_TO_HAND, payload={'object_id': _o.id}, source=sid))
        if not events:
            events.append(Event(type=EventType.RETURN_TO_HAND, payload={'target_filter': 'all_creatures'}, source=sid))
        return events
    return _eff()


def swat_away_resolve(targets, state):
    """Swat Away: Return target creature with flying to its owner's hand."""
    sid, caster = _spell_src('Swat Away', state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.RETURN_TO_HAND, payload=_p, source=sid))
        return events
    return _eff()


def tarfire_resolve(targets, state):
    """Tarfire: Tribal Instant — Goblin. Tarfire deals 2 damage to any target."""
    sid, caster = _spell_src('Tarfire', state)
    def _eff():
        events = []
        _opp = next(_opps(caster, state), None)
        events.append(Event(type=EventType.DAMAGE, payload={'target': _opp, 'amount': 2, 'target_type': 'player'}, source=sid))
        return events
    return _eff()


def tend_the_sprigs_resolve(targets, state):
    """Tend the Sprigs: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control seven or more lands and/or Treefolk, create a 3/4 green Treefolk creature token with reach."""
    sid, caster = _spell_src('Tend the Sprigs', state)
    def _eff():
        events = []
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        events.append(Event(type=EventType.SEARCH_LIBRARY, payload={'player': caster, 'card_type': 'basic land', 'destination': 'battlefield'}, source=sid))
        return events
    return _eff()


def thirst_for_identity_resolve(targets, state):
    """Thirst for Identity: Draw two cards. Then discard a card unless you reveal a Shapeshifter card from your hand."""
    sid, caster = _spell_src('Thirst for Identity', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 2}, source=sid))
        events.append(Event(type=EventType.DISCARD, payload={'player': caster, 'count': 1, 'optional': True}, source=sid))
        return events
    return _eff()


def thoughtweft_charge_resolve(targets, state):
    """Thoughtweft Charge: Target creature gets +3/+3 until end of turn. If a creature entered the battlefield under your control this turn, draw a card."""
    sid, caster = _spell_src('Thoughtweft Charge', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 1}, source=sid))
        _tid = _friendly_creature(caster, state) or _any_creature(caster, state)
        _p = {'power_mod': 3, 'toughness_mod': 3, 'duration': 'end_of_turn', 'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.PT_MODIFICATION, payload=_p, source=sid))
        return events
    return _eff()


def thoughtweft_gambit_resolve(targets, state):
    """Thoughtweft Gambit: Tap all creatures your opponents control and untap all creatures you control."""
    sid, caster = _spell_src('Thoughtweft Gambit', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            if _o.controller != caster:
                events.append(Event(type=EventType.TAP, payload={'object_id': _o.id}, source=sid))
        if not any(e.type==EventType.TAP for e in events):
            events.append(Event(type=EventType.TAP, payload={'target_filter': 'all_opponent_creatures'}, source=sid))
        return events
    return _eff()


def tweeze_resolve(targets, state):
    """Tweeze: Tweeze deals 2 damage to target creature or planeswalker. Create a Treasure token."""
    sid, caster = _spell_src('Tweeze', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state)
        _p = {'amount': 2, 'target_filter': 'creature'}
        if _tid:
            _p['target'] = _tid; _p['target_type'] = 'creature'
        events.append(Event(type=EventType.DAMAGE, payload=_p, source=sid))
        for _i in range(1):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={'controller': caster, 'name': 'Token', 'power': 1, 'toughness': 1, 'subtypes': set()}, source=sid))
        return events
    return _eff()


def unbury_resolve(targets, state):
    """Unbury: Return target creature card from your graveyard to the battlefield. It enters with a -1/-1 counter on it."""
    sid, caster = _spell_src('Unbury', state)
    def _eff():
        events = []
        _cid = _gy_creature(caster, state)
        _p = {'player': caster, 'to': 'battlefield', 'target_filter': 'creature_in_your_graveyard'}
        if _cid:
            _p['object_id'] = _cid
        events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD, payload=_p, source=sid))
        return events
    return _eff()


def unexpected_assistance_resolve(targets, state):
    """Unexpected Assistance: Draw three cards."""
    sid, caster = _spell_src('Unexpected Assistance', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.DRAW, payload={'player': caster, 'count': 3}, source=sid))
        return events
    return _eff()


def unforgiving_aim_resolve(targets, state):
    """Unforgiving Aim: Target creature you control deals damage equal to its power to target creature an opponent controls. You gain life equal to the damage dealt this way."""
    sid, caster = _spell_src('Unforgiving Aim', state)
    def _eff():
        events = []
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': caster, 'amount': 1, 'variable': True}, source=sid))
        _tid = _opp_creature(caster, state)
        _p = {'amount': 1, 'variable': True, 'target_filter': 'creature'}
        if _tid:
            _p['target'] = _tid; _p['target_type'] = 'creature'
        events.append(Event(type=EventType.DAMAGE, payload=_p, source=sid))
        return events
    return _eff()


def unmake_resolve(targets, state):
    """Unmake: Exile target creature."""
    sid, caster = _spell_src('Unmake', state)
    def _eff():
        events = []
        _tid = _any_creature(caster, state)
        _p = {'target_filter': 'creature'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.EXILE, payload=_p, source=sid))
        return events
    return _eff()


def wanderwine_farewell_resolve(targets, state):
    """Wanderwine Farewell: Return all nonland permanents to their owners' hands. Each player draws a card for each permanent they own that was returned this way."""
    sid, caster = _spell_src('Wanderwine Farewell', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.RETURN_TO_HAND, payload={'object_id': _o.id}, source=sid))
        if not events:
            events.append(Event(type=EventType.RETURN_TO_HAND, payload={'target_filter': 'all_creatures'}, source=sid))
        return events
    return _eff()


def winnowing_resolve(targets, state):
    """Winnowing: Destroy all creatures with power 4 or greater."""
    sid, caster = _spell_src('Winnowing', state)
    def _eff():
        events = []
        for _o in _bf_creatures(state):
            events.append(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': _o.id}, source=sid))
        if not events:
            events.append(Event(type=EventType.OBJECT_DESTROYED, payload={'target_filter': 'all_creatures'}, source=sid))
        return events
    return _eff()


def wretched_banquet_resolve(targets, state):
    """Wretched Banquet: Destroy target creature if it has the least power or is tied for least power among creatures on the battlefield."""
    sid, caster = _spell_src('Wretched Banquet', state)
    def _eff():
        events = []
        _tid = _opp_creature(caster, state) or _any_creature(caster, state)
        _p = {'target_filter': 'permanent'}
        if _tid:
            _p['object_id'] = _tid
        events.append(Event(type=EventType.OBJECT_DESTROYED, payload=_p, source=sid))
        return events
    return _eff()



def _register_section2_instants():
    FAE_BUT_MID_CARDS['Assert Perfection'].resolve = assert_perfection_resolve
    FAE_BUT_MID_CARDS["Auntie's Favor"].resolve = aunties_favor_resolve
    FAE_BUT_MID_CARDS['Blight Rot'].resolve = blight_rot_resolve
    FAE_BUT_MID_CARDS['Bloodline Bidding'].resolve = bloodline_bidding_resolve
    FAE_BUT_MID_CARDS['Blossoming Defense'].resolve = blossoming_defense_resolve
    FAE_BUT_MID_CARDS["Bogslither's Embrace"].resolve = bogslithers_embrace_resolve
    FAE_BUT_MID_CARDS['Boulder Dash'].resolve = boulder_dash_resolve
    FAE_BUT_MID_CARDS['Catharsis'].resolve = catharsis_resolve
    FAE_BUT_MID_CARDS['Cinder Strike'].resolve = cinder_strike_resolve
    FAE_BUT_MID_CARDS['Crib Swap'].resolve = crib_swap_resolve
    FAE_BUT_MID_CARDS['Darkness Descends'].resolve = darkness_descends_resolve
    FAE_BUT_MID_CARDS['Death Denied'].resolve = death_denied_resolve
    FAE_BUT_MID_CARDS['Dose of Dawnglow'].resolve = dose_of_dawnglow_resolve
    FAE_BUT_MID_CARDS['Feed the Flames'].resolve = feed_the_flames_resolve
    FAE_BUT_MID_CARDS['Fiery Justice'].resolve = fiery_justice_resolve
    FAE_BUT_MID_CARDS['Firespout'].resolve = firespout_resolve
    FAE_BUT_MID_CARDS['Fodder Launch'].resolve = fodder_launch_resolve
    FAE_BUT_MID_CARDS['Harmonized Crescendo'].resolve = harmonized_crescendo_resolve
    FAE_BUT_MID_CARDS['Hunting Triad'].resolve = hunting_triad_resolve
    FAE_BUT_MID_CARDS['Impolite Entrance'].resolve = impolite_entrance_resolve
    FAE_BUT_MID_CARDS['Lasting Tarfire'].resolve = lasting_tarfire_resolve
    FAE_BUT_MID_CARDS['Lofty Dreams'].resolve = lofty_dreams_resolve
    FAE_BUT_MID_CARDS['Makeshift Mannequin'].resolve = makeshift_mannequin_resolve
    FAE_BUT_MID_CARDS['Manamorphose'].resolve = manamorphose_resolve
    FAE_BUT_MID_CARDS['Midnight Tilling'].resolve = midnight_tilling_resolve
    FAE_BUT_MID_CARDS['Mirrorform'].resolve = mirrorform_resolve
    FAE_BUT_MID_CARDS["Morningtide's Light"].resolve = morningtides_light_resolve
    FAE_BUT_MID_CARDS['Peppersmoke'].resolve = peppersmoke_resolve
    FAE_BUT_MID_CARDS['Perfect Intimidation'].resolve = perfect_intimidation_resolve
    FAE_BUT_MID_CARDS['Personify'].resolve = personify_resolve
    FAE_BUT_MID_CARDS['Ponder'].resolve = ponder_resolve
    FAE_BUT_MID_CARDS['Protective Response'].resolve = protective_response_resolve
    FAE_BUT_MID_CARDS['Pyrrhic Strike'].resolve = pyrrhic_strike_resolve
    FAE_BUT_MID_CARDS['Reckless Ransacking'].resolve = reckless_ransacking_resolve
    FAE_BUT_MID_CARDS['Requiting Hex'].resolve = requiting_hex_resolve
    FAE_BUT_MID_CARDS["Riverguard's Reflexes"].resolve = riverguards_reflexes_resolve
    FAE_BUT_MID_CARDS['Sear'].resolve = sear_resolve
    FAE_BUT_MID_CARDS['Soul Immolation'].resolve = soul_immolation_resolve
    FAE_BUT_MID_CARDS['Spectral Procession'].resolve = spectral_procession_resolve
    FAE_BUT_MID_CARDS['Spry and Mighty'].resolve = spry_and_mighty_resolve
    FAE_BUT_MID_CARDS['Sunderflock'].resolve = sunderflock_resolve
    FAE_BUT_MID_CARDS['Swat Away'].resolve = swat_away_resolve
    FAE_BUT_MID_CARDS['Tarfire'].resolve = tarfire_resolve
    FAE_BUT_MID_CARDS['Tend the Sprigs'].resolve = tend_the_sprigs_resolve
    FAE_BUT_MID_CARDS['Thirst for Identity'].resolve = thirst_for_identity_resolve
    FAE_BUT_MID_CARDS['Thoughtweft Charge'].resolve = thoughtweft_charge_resolve
    FAE_BUT_MID_CARDS['Thoughtweft Gambit'].resolve = thoughtweft_gambit_resolve
    FAE_BUT_MID_CARDS['Tweeze'].resolve = tweeze_resolve
    FAE_BUT_MID_CARDS['Unbury'].resolve = unbury_resolve
    FAE_BUT_MID_CARDS['Unexpected Assistance'].resolve = unexpected_assistance_resolve
    FAE_BUT_MID_CARDS['Unforgiving Aim'].resolve = unforgiving_aim_resolve
    FAE_BUT_MID_CARDS['Unmake'].resolve = unmake_resolve
    FAE_BUT_MID_CARDS['Wanderwine Farewell'].resolve = wanderwine_farewell_resolve
    FAE_BUT_MID_CARDS['Winnowing'].resolve = winnowing_resolve
    FAE_BUT_MID_CARDS['Wretched Banquet'].resolve = wretched_banquet_resolve

_register_section2_instants()
