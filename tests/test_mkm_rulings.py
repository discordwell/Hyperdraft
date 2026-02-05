"""
Murders at Karlov Manor (MKM) Rulings Tests

Testing complex card interactions from Murders at Karlov Manor:
1. Doorkeeper Thrull - Prevents artifacts/creatures from causing triggers
2. Massacre Girl, Known Killer - Wither, death trigger with last known toughness
3. Judith, Carnage Connoisseur - Grants deathtouch/lifelink to spells
4. Leyline of the Guildpact - All nonland permanents are all colors, lands are all basic types
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    get_power, get_toughness, get_types, get_colors,
    Characteristics, make_creature, make_enchantment, make_land,
    new_id
)


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

# -----------------------------------------------------------------------------
# Doorkeeper Thrull
# 2W - Creature - Thrull (1/4)
# Artifacts and creatures entering or leaving the battlefield don't cause
# abilities to trigger.
# -----------------------------------------------------------------------------

def doorkeeper_thrull_setup(obj, state):
    """
    Doorkeeper Thrull prevents artifacts and creatures from causing triggers.

    Key rulings:
    - PREVENTS triggered abilities (REACT phase)
    - Does NOT prevent replacement effects (TRANSFORM phase)
    - Checks the permanent as it exists with continuous effects applied
    """

    def prevent_filter(event: Event, state) -> bool:
        # We want to intercept REACT-phase events that are triggered by
        # zone changes involving artifacts/creatures
        if event.type != EventType.ZONE_CHANGE:
            return False

        # Check if this is entering or leaving the battlefield
        from_zone = event.payload.get('from_zone_type')
        to_zone = event.payload.get('to_zone_type')

        is_entering = to_zone == ZoneType.BATTLEFIELD
        is_leaving = from_zone == ZoneType.BATTLEFIELD

        if not (is_entering or is_leaving):
            return False

        # Check if the object is an artifact or creature
        obj_id = event.payload.get('object_id')
        entering_obj = state.objects.get(obj_id)
        if not entering_obj:
            return False

        # Use get_types to respect continuous effects
        obj_types = get_types(entering_obj, state)

        return CardType.ARTIFACT in obj_types or CardType.CREATURE in obj_types

    def prevent_triggers_handler(event: Event, state) -> InterceptorResult:
        """
        This interceptor runs at TRANSFORM priority to mark the event
        so that REACT interceptors (triggers) know to skip it.
        """
        new_event = event.copy()
        new_event.payload['triggers_prevented'] = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=prevent_filter,
            handler=prevent_triggers_handler,
            duration='while_on_battlefield'
        )
    ]


DOORKEEPER_THRULL = make_creature(
    name="Doorkeeper Thrull",
    power=1,
    toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Thrull"},
    text="Artifacts and creatures entering or leaving the battlefield don't cause abilities to trigger.",
    setup_interceptors=doorkeeper_thrull_setup
)


# -----------------------------------------------------------------------------
# Massacre Girl, Known Killer
# 2BB - Legendary Creature - Human Assassin (4/4)
# Wither (This deals damage to creatures in the form of -1/-1 counters.)
# Whenever a creature you control with a -1/-1 counter on it dies, draw a card.
# -----------------------------------------------------------------------------

def massacre_girl_setup(obj, state):
    """
    Massacre Girl grants wither to all your creatures and has a death trigger.

    Key rulings:
    - Wither applies to ALL damage from your creatures (not just Massacre Girl)
    - Death trigger uses "last known toughness" to check for -1/-1 counters
    """
    interceptors = []

    # Wither effect: Transform damage from your creatures into -1/-1 counters
    def wither_filter(event: Event, state) -> bool:
        if event.type != EventType.DAMAGE:
            return False

        # Check if source is a creature we control
        source_id = event.payload.get('source')
        if not source_id:
            return False

        source = state.objects.get(source_id)
        if not source:
            return False

        # Must be our creature
        if source.controller != obj.controller:
            return False

        if CardType.CREATURE not in source.characteristics.types:
            return False

        # Target must be a creature (wither only applies to creatures)
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False

        return CardType.CREATURE in target.characteristics.types

    def wither_handler(event: Event, state) -> InterceptorResult:
        """Convert damage to -1/-1 counters."""
        amount = event.payload.get('amount', 0)
        target_id = event.payload.get('target')

        # Instead of dealing damage, we add -1/-1 counters
        # Return a COUNTER_ADDED event and prevent the damage
        counter_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': target_id,
                'counter_type': '-1/-1',
                'amount': amount
            },
            source=event.source
        )

        return InterceptorResult(
            action=InterceptorAction.REPLACE,
            new_events=[counter_event]
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=wither_filter,
        handler=wither_handler,
        duration='while_on_battlefield'
    ))

    # Death trigger: When a creature with -1/-1 counter dies, draw a card
    # Store last known information when creatures die
    def death_trigger_filter(event: Event, state) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False

        obj_id = event.payload.get('object_id')
        dying_obj = state.objects.get(obj_id)

        if not dying_obj:
            return False

        # Must be a creature we control
        if dying_obj.controller != obj.controller:
            return False

        if CardType.CREATURE not in dying_obj.characteristics.types:
            return False

        # Check for -1/-1 counters - using LAST KNOWN information
        # (the object still exists in state at this point during REACT phase)
        return dying_obj.state.counters.get('-1/-1', 0) > 0

    def death_trigger_handler(event: Event, state) -> InterceptorResult:
        """Draw a card when creature with -1/-1 counter dies."""
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id
            )]
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_trigger_filter,
        handler=death_trigger_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


MASSACRE_GIRL = make_creature(
    name="Massacre Girl, Known Killer",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Wither. Whenever a creature you control with a -1/-1 counter on it dies, draw a card.",
    setup_interceptors=massacre_girl_setup
)


# -----------------------------------------------------------------------------
# Judith, Carnage Connoisseur
# 3BR - Legendary Creature - Human Shaman (3/4)
# Whenever you cast an instant or sorcery spell, choose one:
# - That spell gains deathtouch and lifelink.
# - When that spell resolves, if it dealt damage, you draw a card and lose 1 life.
# -----------------------------------------------------------------------------

def judith_setup(obj, state):
    """
    Judith grants deathtouch/lifelink to spells.

    Key rulings:
    - The SPELL must deal the damage, not something it causes to deal damage
    - If a spell causes another object to deal damage, that damage doesn't
      get deathtouch/lifelink from Judith
    - The trigger resolves BEFORE the spell (goes on stack above it)
    """
    interceptors = []

    # TRANSFORM interceptor to mark spell cast events with Judith's grant
    def spell_cast_filter(event: Event, state) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False

        # Must be our spell
        if event.payload.get('caster') != obj.controller:
            return False

        # Must be instant or sorcery
        spell_types = event.payload.get('types', set())
        return CardType.INSTANT in spell_types or CardType.SORCERY in spell_types

    def grant_keywords_handler(event: Event, state) -> InterceptorResult:
        """
        When we cast an instant/sorcery, mark it as having deathtouch/lifelink.
        This is a simplification - in a full implementation, we'd offer the choice.
        """
        new_event = event.copy()
        new_event.payload['judith_granted'] = ['deathtouch', 'lifelink']
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,  # Use TRANSFORM to modify the event
        filter=spell_cast_filter,
        handler=grant_keywords_handler,
        duration='while_on_battlefield'
    ))

    # Interceptor to modify damage events from Judith-buffed spells
    def damage_filter(event: Event, state) -> bool:
        if event.type != EventType.DAMAGE:
            return False

        # Check if source spell was granted Judith's keywords
        source_id = event.payload.get('source')
        if not source_id:
            return False

        source = state.objects.get(source_id)
        if not source:
            return False

        # The source must be the SPELL itself, not another permanent
        if source.zone != ZoneType.STACK:
            return False

        # Check if Judith granted keywords (stored on the spell object)
        return getattr(source, '_judith_keywords', False)

    def apply_keywords_handler(event: Event, state) -> InterceptorResult:
        """Apply deathtouch/lifelink to spell damage."""
        new_event = event.copy()
        new_event.payload['has_deathtouch'] = True
        new_event.payload['has_lifelink'] = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return interceptors


JUDITH = make_creature(
    name="Judith, Carnage Connoisseur",
    power=3,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Shaman"},
    text="Whenever you cast an instant or sorcery spell, choose one: That spell gains deathtouch and lifelink; or When that spell resolves, if it dealt damage, you draw a card and lose 1 life.",
    setup_interceptors=judith_setup
)


# -----------------------------------------------------------------------------
# Leyline of the Guildpact
# GGGGWWWWUUUURRRRBBBB (or free in opening hand)
# This card is all colors.
# If Leyline of the Guildpact is in your opening hand, you may begin the
# game with it on the battlefield.
# Each nonland permanent you control is all colors.
# Each land you control is every basic land type in addition to its other types.
# -----------------------------------------------------------------------------

def leyline_of_the_guildpact_setup(obj, state):
    """
    Leyline of the Guildpact affects types and colors.

    Key rulings:
    - Layer 4 (Types): Lands gain all basic land types
    - Layer 5 (Colors): Nonland permanents become all colors
    - Lands gain the mana abilities associated with basic land types
    - The land type addition is "in addition to" existing types
    """
    interceptors = []

    ALL_COLORS = {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}

    # Color-changing effect for nonland permanents (Layer 5)
    def color_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_COLORS:
            return False

        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False

        # Must be a permanent we control on the battlefield
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False

        # Must be a nonland permanent
        return CardType.LAND not in target.characteristics.types

    def color_handler(event: Event, state) -> InterceptorResult:
        """Make nonland permanents all colors."""
        new_event = event.copy()
        new_event.payload['value'] = ALL_COLORS.copy()
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=color_filter,
        handler=color_handler,
        duration='while_on_battlefield'
    ))

    # Type-changing effect for lands (Layer 4)
    def type_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_TYPES:
            return False

        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False

        # Must be a land we control on the battlefield
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False

        return CardType.LAND in target.characteristics.types

    def type_handler(event: Event, state) -> InterceptorResult:
        """Add all basic land types to lands (in addition to existing types)."""
        current_types = event.payload.get('value', set())
        new_event = event.copy()
        # We don't change the CardTypes, but for subtypes we'd add basic land types
        # This is a simplification - subtypes are tracked separately
        new_event.payload['value'] = current_types
        new_event.payload['added_subtypes'] = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=type_filter,
        handler=type_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


LEYLINE_OF_THE_GUILDPACT = make_enchantment(
    name="Leyline of the Guildpact",
    mana_cost="{G}{G}{G}{G}{W}{W}{W}{W}{U}{U}{U}{U}{R}{R}{R}{R}{B}{B}{B}{B}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="This card is all colors. If Leyline of the Guildpact is in your opening hand, you may begin the game with it on the battlefield. Each nonland permanent you control is all colors. Each land you control is every basic land type in addition to its other types.",
    setup_interceptors=leyline_of_the_guildpact_setup
)


# =============================================================================
# HELPER CARDS FOR TESTING
# =============================================================================

# Soul Warden - for testing trigger prevention
def soul_warden_setup(obj, state):
    """Whenever another creature enters, gain 1 life."""

    def trigger_filter(event: Event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False

        # Check if triggers are prevented (by Doorkeeper Thrull)
        if event.payload.get('triggers_prevented'):
            return False

        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False

        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False

        entering = state.objects.get(entering_id)
        if not entering:
            return False

        return CardType.CREATURE in entering.characteristics.types

    def trigger_handler(event: Event, state) -> InterceptorResult:
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


# Arcbound Worker - Enters with +1/+1 counter (replacement effect)
def arcbound_worker_setup(obj, state):
    """Enters with a +1/+1 counter - this is a replacement effect, not a trigger."""

    def etb_filter(event: Event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return event.payload.get('object_id') == obj.id

    def etb_handler(event: Event, state) -> InterceptorResult:
        """Replacement effect - modify the zone change to include counters."""
        new_event = event.copy()
        new_event.payload['counters'] = {'+1/+1': 1}
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield'
    )]


ARCBOUND_WORKER = make_creature(
    name="Arcbound Worker",
    power=0,
    toughness=0,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Artifact", "Creature"},
    text="Modular 1 (This creature enters the battlefield with a +1/+1 counter on it.)",
    types={CardType.ARTIFACT},
    setup_interceptors=arcbound_worker_setup
)


# =============================================================================
# TESTS
# =============================================================================

def test_doorkeeper_thrull_prevents_etb_trigger():
    """
    Test that Doorkeeper Thrull prevents ETB triggers from creatures.
    Soul Warden should NOT gain life when a creature enters.
    """
    print("\n=== Test: Doorkeeper Thrull Prevents ETB Triggers ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Soul Warden on battlefield
    game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    # Put Doorkeeper Thrull on battlefield
    game.create_object(
        name="Doorkeeper Thrull",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=DOORKEEPER_THRULL.characteristics,
        card_def=DOORKEEPER_THRULL
    )

    print(f"Starting life: {p1.life}")

    # Create a creature and have it enter the battlefield
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2)
    )

    # Emit the zone change event
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Life after creature ETB (with Doorkeeper Thrull): {p1.life}")

    # Soul Warden should NOT have triggered
    assert p1.life == 20, f"Expected 20 (trigger prevented), got {p1.life}"
    print("OK Doorkeeper Thrull prevented Soul Warden's trigger!")


def test_doorkeeper_thrull_allows_replacement_effects():
    """
    Test that Doorkeeper Thrull does NOT prevent replacement effects.
    Arcbound Worker should still enter with its +1/+1 counter.
    """
    print("\n=== Test: Doorkeeper Thrull Allows Replacement Effects ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Doorkeeper Thrull on battlefield
    game.create_object(
        name="Doorkeeper Thrull",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=DOORKEEPER_THRULL.characteristics,
        card_def=DOORKEEPER_THRULL
    )

    # Create Arcbound Worker
    worker = game.create_object(
        name="Arcbound Worker",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ARCBOUND_WORKER.characteristics,
        card_def=ARCBOUND_WORKER
    )

    # Emit the zone change event
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': worker.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    # Check that the worker has its +1/+1 counter
    counters = worker.state.counters.get('+1/+1', 0)
    print(f"Arcbound Worker +1/+1 counters: {counters}")

    # Replacement effect should work even with Doorkeeper Thrull
    assert counters == 1, f"Expected 1 counter (replacement effect), got {counters}"

    # Worker should be 1/1 (0/0 base + 1 counter)
    power = get_power(worker, game.state)
    toughness = get_toughness(worker, game.state)
    print(f"Arcbound Worker stats: {power}/{toughness}")

    assert power == 1 and toughness == 1, f"Expected 1/1, got {power}/{toughness}"
    print("OK Replacement effects work through Doorkeeper Thrull!")


def test_doorkeeper_thrull_no_effect_without_it():
    """
    Control test: Without Doorkeeper Thrull, triggers should work normally.
    """
    print("\n=== Test: Soul Warden Works Without Doorkeeper Thrull ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Soul Warden on battlefield
    game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    print(f"Starting life: {p1.life}")

    # Create a creature and have it enter the battlefield
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2)
    )

    # Emit the zone change event
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Life after creature ETB (no Doorkeeper): {p1.life}")

    # Soul Warden SHOULD trigger
    assert p1.life == 21, f"Expected 21 (Soul Warden triggered), got {p1.life}"
    print("OK Soul Warden triggers normally without Doorkeeper Thrull!")


def test_massacre_girl_wither():
    """
    Test that Massacre Girl's wither converts damage to -1/-1 counters.
    """
    print("\n=== Test: Massacre Girl's Wither ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Massacre Girl on battlefield
    massacre_girl = game.create_object(
        name="Massacre Girl, Known Killer",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MASSACRE_GIRL.characteristics,
        card_def=MASSACRE_GIRL
    )

    # Put an opponent's creature on battlefield
    enemy = game.create_object(
        name="Enemy Creature",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=3, toughness=3)
    )

    print(f"Enemy creature before damage: {get_power(enemy, game.state)}/{get_toughness(enemy, game.state)}")
    print(f"Enemy damage marked: {enemy.state.damage}")
    print(f"Enemy -1/-1 counters: {enemy.state.counters.get('-1/-1', 0)}")

    # Massacre Girl deals 4 damage to the enemy creature
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'target': enemy.id,
            'amount': 4,
            'source': massacre_girl.id,
            'is_combat': True
        },
        source=massacre_girl.id
    ))

    print(f"Enemy creature after wither damage: {get_power(enemy, game.state)}/{get_toughness(enemy, game.state)}")
    print(f"Enemy damage marked: {enemy.state.damage}")
    print(f"Enemy -1/-1 counters: {enemy.state.counters.get('-1/-1', 0)}")

    # Should have 4 -1/-1 counters instead of damage
    counters = enemy.state.counters.get('-1/-1', 0)
    assert counters == 4, f"Expected 4 -1/-1 counters, got {counters}"

    # Damage should be 0 (wither converts to counters)
    assert enemy.state.damage == 0, f"Expected 0 damage, got {enemy.state.damage}"

    # Creature should be -1/-1 (3 base - 4 counters)
    power = get_power(enemy, game.state)
    toughness = get_toughness(enemy, game.state)
    assert power == -1 and toughness == -1, f"Expected -1/-1, got {power}/{toughness}"

    print("OK Wither converts damage to -1/-1 counters!")


def test_massacre_girl_death_trigger():
    """
    Test that Massacre Girl triggers on death of creatures with -1/-1 counters.
    Uses last known toughness to determine if creature had counters.
    """
    print("\n=== Test: Massacre Girl Death Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set up library for drawing
    library_key = f"library_{p1.id}"
    for i in range(5):
        card = game.create_object(
            name=f"Card {i}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.CREATURE})
        )

    hand_key = f"hand_{p1.id}"
    starting_hand = len(game.state.zones.get(hand_key, []).objects) if hand_key in game.state.zones else 0

    print(f"Starting hand size: {starting_hand}")
    print(f"Library size: {len(game.state.zones[library_key].objects)}")

    # Put Massacre Girl on battlefield
    massacre_girl = game.create_object(
        name="Massacre Girl, Known Killer",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MASSACRE_GIRL.characteristics,
        card_def=MASSACRE_GIRL
    )

    # Put a creature with -1/-1 counter on battlefield
    creature = game.create_object(
        name="Doomed Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2)
    )
    creature.state.counters['-1/-1'] = 1

    print(f"Creature with counter: {get_power(creature, game.state)}/{get_toughness(creature, game.state)}")
    print(f"Counters: {creature.state.counters}")

    # Destroy the creature
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': creature.id}
    ))

    # Check hand size - should have drawn a card
    current_hand = len(game.state.zones.get(hand_key, []).objects) if hand_key in game.state.zones else 0
    print(f"Hand size after death: {current_hand}")

    assert current_hand == starting_hand + 1, f"Expected {starting_hand + 1} cards in hand, got {current_hand}"
    print("OK Massacre Girl drew a card from death trigger!")


def test_massacre_girl_no_trigger_without_counter():
    """
    Test that Massacre Girl does NOT trigger for creatures without -1/-1 counters.
    """
    print("\n=== Test: Massacre Girl No Trigger Without Counter ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set up library for drawing
    library_key = f"library_{p1.id}"
    for i in range(5):
        game.create_object(
            name=f"Card {i}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.CREATURE})
        )

    hand_key = f"hand_{p1.id}"
    starting_hand = len(game.state.zones.get(hand_key, []).objects) if hand_key in game.state.zones else 0

    # Put Massacre Girl on battlefield
    game.create_object(
        name="Massacre Girl, Known Killer",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MASSACRE_GIRL.characteristics,
        card_def=MASSACRE_GIRL
    )

    # Put a creature WITHOUT -1/-1 counter on battlefield
    creature = game.create_object(
        name="Normal Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2)
    )

    print(f"Creature without counter: {creature.state.counters}")

    # Destroy the creature
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': creature.id}
    ))

    # Check hand size - should NOT have drawn
    current_hand = len(game.state.zones.get(hand_key, []).objects) if hand_key in game.state.zones else 0
    print(f"Hand size after death (no counter): {current_hand}")

    assert current_hand == starting_hand, f"Expected {starting_hand} cards in hand (no draw), got {current_hand}"
    print("OK Massacre Girl correctly did not trigger without counter!")


def test_leyline_makes_nonland_all_colors():
    """
    Test that Leyline of the Guildpact makes nonland permanents all colors.
    """
    print("\n=== Test: Leyline Makes Nonland Permanents All Colors ===")

    game = Game()
    p1 = game.add_player("Alice")

    ALL_COLORS = {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}

    # Create a mono-red creature
    creature = game.create_object(
        name="Red Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            power=2,
            toughness=2
        )
    )

    # Create a colorless artifact
    artifact = game.create_object(
        name="Colorless Artifact",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.ARTIFACT})
    )

    print(f"Creature colors before Leyline: {get_colors(creature, game.state)}")
    print(f"Artifact colors before Leyline: {get_colors(artifact, game.state)}")

    # Put Leyline on battlefield
    game.create_object(
        name="Leyline of the Guildpact",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LEYLINE_OF_THE_GUILDPACT.characteristics,
        card_def=LEYLINE_OF_THE_GUILDPACT
    )

    creature_colors = get_colors(creature, game.state)
    artifact_colors = get_colors(artifact, game.state)

    print(f"Creature colors with Leyline: {creature_colors}")
    print(f"Artifact colors with Leyline: {artifact_colors}")

    assert creature_colors == ALL_COLORS, f"Expected all colors, got {creature_colors}"
    assert artifact_colors == ALL_COLORS, f"Expected all colors, got {artifact_colors}"
    print("OK Leyline makes nonland permanents all colors!")


def test_leyline_does_not_affect_lands_colors():
    """
    Test that Leyline does NOT make lands all colors (lands are not nonland).
    """
    print("\n=== Test: Leyline Does Not Affect Land Colors ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a basic Forest (green-producing but colorless card)
    forest = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes={"Forest"},
            colors=set()  # Lands are colorless
        )
    )

    print(f"Forest colors before Leyline: {get_colors(forest, game.state)}")

    # Put Leyline on battlefield
    game.create_object(
        name="Leyline of the Guildpact",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LEYLINE_OF_THE_GUILDPACT.characteristics,
        card_def=LEYLINE_OF_THE_GUILDPACT
    )

    forest_colors = get_colors(forest, game.state)
    print(f"Forest colors with Leyline: {forest_colors}")

    # Lands should remain colorless (Leyline only affects nonland permanents for colors)
    assert forest_colors == set(), f"Expected no colors (lands unaffected), got {forest_colors}"
    print("OK Leyline does not change land colors!")


def test_leyline_only_affects_your_permanents():
    """
    Test that Leyline only affects permanents you control.
    """
    print("\n=== Test: Leyline Only Affects Your Permanents ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    ALL_COLORS = {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}

    # Alice has a red creature
    alice_creature = game.create_object(
        name="Alice's Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            power=2,
            toughness=2
        )
    )

    # Bob has a blue creature
    bob_creature = game.create_object(
        name="Bob's Creature",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.BLUE},
            power=2,
            toughness=2
        )
    )

    # Alice puts Leyline on battlefield
    game.create_object(
        name="Leyline of the Guildpact",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LEYLINE_OF_THE_GUILDPACT.characteristics,
        card_def=LEYLINE_OF_THE_GUILDPACT
    )

    alice_colors = get_colors(alice_creature, game.state)
    bob_colors = get_colors(bob_creature, game.state)

    print(f"Alice's creature colors: {alice_colors}")
    print(f"Bob's creature colors: {bob_colors}")

    assert alice_colors == ALL_COLORS, f"Expected Alice's creature all colors, got {alice_colors}"
    assert bob_colors == {Color.BLUE}, f"Expected Bob's creature blue only, got {bob_colors}"
    print("OK Leyline only affects your permanents!")


def test_judith_grants_keywords_to_spell():
    """
    Test that Judith grants deathtouch/lifelink when casting instant/sorcery.
    """
    print("\n=== Test: Judith Grants Keywords to Spells ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Judith on battlefield
    game.create_object(
        name="Judith, Carnage Connoisseur",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=JUDITH.characteristics,
        card_def=JUDITH
    )

    # Cast an instant spell
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'types': {CardType.INSTANT},
            'spell_id': 'test_spell'
        }
    ))

    # Check if Judith's trigger modified the event in the event log
    # The event log contains the RESOLVED (post-transform) events
    cast_event = None
    for e in game.state.event_log:
        if e.type in (EventType.CAST, EventType.SPELL_CAST):
            cast_event = e
            break

    assert cast_event is not None, "Cast event should be in event log"
    judith_granted = cast_event.payload.get('judith_granted', [])
    print(f"Judith granted keywords: {judith_granted}")

    assert 'deathtouch' in judith_granted, "Expected deathtouch to be granted"
    assert 'lifelink' in judith_granted, "Expected lifelink to be granted"
    print("OK Judith grants deathtouch and lifelink to spells!")


def test_judith_ignores_creature_spells():
    """
    Test that Judith only triggers for instant/sorcery, not creature spells.
    """
    print("\n=== Test: Judith Ignores Creature Spells ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Judith on battlefield
    game.create_object(
        name="Judith, Carnage Connoisseur",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=JUDITH.characteristics,
        card_def=JUDITH
    )

    # Cast a creature spell
    events = game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'types': {CardType.CREATURE},
            'spell_id': 'creature_spell'
        }
    ))

    # Check that Judith did NOT grant keywords
    for e in events:
        if e.type in (EventType.CAST, EventType.SPELL_CAST):
            judith_granted = e.payload.get('judith_granted', [])
            assert judith_granted == [], f"Expected no grants for creature spell, got {judith_granted}"

    print("OK Judith correctly ignores creature spells!")


def test_multiple_leylines():
    """
    Test that multiple Leylines don't cause issues (colors should still be all 5).
    """
    print("\n=== Test: Multiple Leylines ===")

    game = Game()
    p1 = game.add_player("Alice")

    ALL_COLORS = {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}

    # Create a creature
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            power=2,
            toughness=2
        )
    )

    # Put TWO Leylines on battlefield
    for i in range(2):
        game.create_object(
            name=f"Leyline of the Guildpact {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=LEYLINE_OF_THE_GUILDPACT.characteristics,
            card_def=LEYLINE_OF_THE_GUILDPACT
        )

    creature_colors = get_colors(creature, game.state)
    print(f"Creature colors with 2 Leylines: {creature_colors}")

    assert creature_colors == ALL_COLORS, f"Expected all colors, got {creature_colors}"
    print("OK Multiple Leylines work correctly!")


def test_massacre_girl_wither_applies_to_all_your_creatures():
    """
    Test that Massacre Girl's wither applies to ALL creatures you control.
    """
    print("\n=== Test: Wither Applies to All Your Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Massacre Girl on battlefield
    game.create_object(
        name="Massacre Girl, Known Killer",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MASSACRE_GIRL.characteristics,
        card_def=MASSACRE_GIRL
    )

    # Put another creature you control
    other_creature = game.create_object(
        name="Other Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2)
    )

    # Put an opponent's creature on battlefield
    enemy = game.create_object(
        name="Enemy Creature",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=3, toughness=3)
    )

    # Other creature deals damage to enemy (should have wither)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'target': enemy.id,
            'amount': 2,
            'source': other_creature.id,
            'is_combat': True
        },
        source=other_creature.id
    ))

    counters = enemy.state.counters.get('-1/-1', 0)
    damage = enemy.state.damage

    print(f"Enemy -1/-1 counters: {counters}")
    print(f"Enemy damage: {damage}")

    # Should have counters instead of damage
    assert counters == 2, f"Expected 2 -1/-1 counters, got {counters}"
    assert damage == 0, f"Expected 0 damage (wither), got {damage}"
    print("OK Wither applies to all your creatures!")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_mkm_tests():
    """Run all MKM ruling tests."""
    print("=" * 60)
    print("MURDERS AT KARLOV MANOR (MKM) RULINGS TESTS")
    print("=" * 60)

    # Doorkeeper Thrull tests
    test_doorkeeper_thrull_no_effect_without_it()
    test_doorkeeper_thrull_prevents_etb_trigger()
    test_doorkeeper_thrull_allows_replacement_effects()

    # Massacre Girl tests
    test_massacre_girl_wither()
    test_massacre_girl_death_trigger()
    test_massacre_girl_no_trigger_without_counter()
    test_massacre_girl_wither_applies_to_all_your_creatures()

    # Leyline tests
    test_leyline_makes_nonland_all_colors()
    test_leyline_does_not_affect_lands_colors()
    test_leyline_only_affects_your_permanents()
    test_multiple_leylines()

    # Judith tests
    test_judith_grants_keywords_to_spell()
    test_judith_ignores_creature_spells()

    print("\n" + "=" * 60)
    print("ALL MKM RULINGS TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_mkm_tests()
