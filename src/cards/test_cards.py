"""
Test Cards

5 cards that exercise different engine mechanics:
1. Lightning Bolt - direct damage spell
2. Soul Warden - triggered ability (react)
3. Glorious Anthem - continuous effect (query)
4. Rhox Faithmender - replacement effect (transform)
5. Fog Bank - prevention effect (prevent)
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    make_creature, make_instant, make_enchantment,
    new_id
)


# =============================================================================
# 1. LIGHTNING BOLT - Direct Damage Spell
# =============================================================================
# "Deal 3 damage to any target."

def lightning_bolt_resolve(event: Event, state: GameState, target_id: str) -> list[Event]:
    """Resolution function for Lightning Bolt."""
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 3},
        source=event.payload.get('source'),
        controller=event.controller
    )]


LIGHTNING_BOLT = make_instant(
    name="Lightning Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Lightning Bolt deals 3 damage to any target.",
    resolve=lightning_bolt_resolve
)


# =============================================================================
# 2. SOUL WARDEN - Triggered Ability (REACT interceptor)
# =============================================================================
# "Whenever another creature enters the battlefield, you gain 1 life."

def soul_warden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Set up Soul Warden's triggered ability."""

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        # Check if something entered the battlefield
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Check if it's a creature (not self)
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return CardType.CREATURE in entering.characteristics.types

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
        duration='while_on_battlefield'
    )]


SOUL_WARDEN = make_creature(
    name="Soul Warden",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="Whenever another creature enters the battlefield, you gain 1 life.",
    setup_interceptors=soul_warden_setup
)


# =============================================================================
# 3. GLORIOUS ANTHEM - Continuous Effect (QUERY interceptor)
# =============================================================================
# "Creatures you control get +1/+1."

def glorious_anthem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Set up Glorious Anthem's continuous effect."""

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        # Only affect creatures we control
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
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


GLORIOUS_ANTHEM = make_enchantment(
    name="Glorious Anthem",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1.",
    setup_interceptors=glorious_anthem_setup
)


# =============================================================================
# 4. RHOX FAITHMENDER - Replacement Effect (TRANSFORM interceptor)
# =============================================================================
# "If you would gain life, you gain twice that much life instead."

def rhox_faithmender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Set up Rhox Faithmender's replacement effect."""

    def replace_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        player = event.payload.get('player')
        # Only replace life GAIN for our controller
        return amount > 0 and player == obj.controller

    def replace_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) * 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=replace_filter,
        handler=replace_handler,
        duration='while_on_battlefield'
    )]


RHOX_FAITHMENDER = make_creature(
    name="Rhox Faithmender",
    power=1,
    toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Rhino", "Monk"},
    text="Lifelink. If you would gain life, you gain twice that much life instead.",
    setup_interceptors=rhox_faithmender_setup
)


# =============================================================================
# 5. FOG BANK - Prevention Effect (PREVENT interceptor)
# =============================================================================
# "Prevent all combat damage that would be dealt to and dealt by Fog Bank."

def fog_bank_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Set up Fog Bank's prevention effect."""

    def prevent_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        # Prevent damage TO fog bank or FROM fog bank
        target = event.payload.get('target')
        source = event.source
        # For now, prevent all damage to/from this creature
        # (A full implementation would check for "combat damage" specifically)
        return target == obj.id or source == obj.id

    def prevent_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=prevent_filter,
        handler=prevent_handler,
        duration='while_on_battlefield'
    )]


FOG_BANK = make_creature(
    name="Fog Bank",
    power=0,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Wall"},
    text="Defender. Flying. Prevent all combat damage that would be dealt to and dealt by Fog Bank.",
    setup_interceptors=fog_bank_setup
)


# =============================================================================
# 6. TEST VEHICLE - For testing Crew mechanic
# =============================================================================
# "Crew 2"

from src.engine import make_artifact

TEST_VEHICLE = make_artifact(
    name="Test Vehicle",
    mana_cost="{2}",
    colors=set(),
    text="Crew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    power=3,
    toughness=3
)


# =============================================================================
# 7. GRIZZLY BEARS - Simple 2/2 creature for crewing
# =============================================================================

GRIZZLY_BEARS = make_creature(
    name="Grizzly Bears",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bear"},
    text="No abilities.",
)


# =============================================================================
# 8. ELVISH MYSTIC - Mana dork for crewing
# =============================================================================

ELVISH_MYSTIC = make_creature(
    name="Elvish Mystic",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}.",
)


# =============================================================================
# 9. BASIC LANDS - For mana
# =============================================================================

from src.engine import make_land

def forest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Set up Forest's mana ability."""
    # Note: Mana abilities should be instant-speed and not use the stack
    # For now, this is a simple placeholder
    return []

FOREST = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"},
    supertypes={"Basic"},
)

PLAINS = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"},
    supertypes={"Basic"},
)

MOUNTAIN = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"},
    supertypes={"Basic"},
)


# =============================================================================
# Card Registry
# =============================================================================

TEST_CARDS = {
    "Lightning Bolt": LIGHTNING_BOLT,
    "Soul Warden": SOUL_WARDEN,
    "Glorious Anthem": GLORIOUS_ANTHEM,
    "Rhox Faithmender": RHOX_FAITHMENDER,
    "Fog Bank": FOG_BANK,
    "Test Vehicle": TEST_VEHICLE,
    "Grizzly Bears": GRIZZLY_BEARS,
    "Elvish Mystic": ELVISH_MYSTIC,
    "Forest": FOREST,
    "Plains": PLAINS,
    "Mountain": MOUNTAIN,
}
