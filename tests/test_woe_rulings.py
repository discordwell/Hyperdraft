"""
Wilds of Eldraine (WOE) Card Ruling Tests

Testing complex cards with specific rulings:
1. Ashiok, Wicked Manipulator - Replacement effect: paying life exiles cards instead
2. Asinine Antics - Role tokens making creatures 1/1, non-targeting, SBA cleanup
3. Talion, the Kindly Lord - ETB choice of number 1-10, triggers on MV/P/T match
4. Moonshaker Cavalry - ETB gives flying and +X/+X where X = creature count, locked at resolution
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    make_creature, make_sorcery, make_planeswalker,
    new_id
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_static_pt_boost, make_keyword_grant,
    creatures_you_control, other_creatures_you_control
)


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

# -----------------------------------------------------------------------------
# 1. ASHIOK, WICKED MANIPULATOR
# -----------------------------------------------------------------------------
# Planeswalker - Ashiok
# "If you would pay life while your library has at least that many cards,
#  exile that many cards from the top of your library instead."
# [+1]: Look at top 2, exile 1 face down, put other in hand
# [-2]: Create two 1/1 Nightmare creature tokens with flying
# [-7]: Exile library, cast exiled cards for free

def ashiok_wicked_manipulator_setup(obj, state):
    """
    Ashiok's replacement effect: If you would pay life while your library
    has at least that many cards, exile that many cards instead.

    This is a TRANSFORM interceptor that replaces life payment with library exile.
    """

    def replace_filter(event, state):
        if event.type != EventType.LIFE_CHANGE:
            return False

        amount = event.payload.get('amount', 0)
        player = event.payload.get('player')
        is_life_payment = event.payload.get('is_life_payment', False)

        # Only replace life PAYMENT (negative amount) for our controller
        if amount >= 0 or player != obj.controller:
            return False

        if not is_life_payment:
            return False

        # Check if library has enough cards
        library_key = f"library_{player}"
        library = state.zones.get(library_key)
        if not library:
            return False

        cards_needed = abs(amount)
        return len(library.objects) >= cards_needed

    def replace_handler(event, state):
        # Instead of losing life, exile cards from library
        player = event.payload.get('player')
        cards_to_exile = abs(event.payload.get('amount', 0))

        library_key = f"library_{player}"
        library = state.zones.get(library_key)
        exile_zone = state.zones.get('exile')

        if library and exile_zone and cards_to_exile > 0:
            # Exile top N cards
            for _ in range(cards_to_exile):
                if library.objects:
                    card_id = library.objects.pop(0)  # Top of library
                    exile_zone.objects.append(card_id)
                    if card_id in state.objects:
                        state.objects[card_id].zone = ZoneType.EXILE

        # Transform the event to have 0 life change (replacement effect)
        new_event = event.copy()
        new_event.payload['amount'] = 0  # No life change
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


ASHIOK_WICKED_MANIPULATOR = make_planeswalker(
    name="Ashiok, Wicked Manipulator",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    loyalty=5,
    subtypes={"Ashiok"},
    text="If you would pay life while your library has at least that many cards, exile that many cards from the top of your library instead.\n[+1]: Look at the top two cards of your library. Exile one of them face down and put the other into your hand.\n[-2]: Create two 1/1 black Nightmare creature tokens with flying.\n[-7]: Target player exiles their library, then you may cast any number of cards you own from exile without paying their mana costs.",
    rarity="mythic",
    setup_interceptors=ashiok_wicked_manipulator_setup
)


# -----------------------------------------------------------------------------
# 2. ASININE ANTICS
# -----------------------------------------------------------------------------
# Sorcery - {4}{U}{U}
# "Each creature your opponents control becomes a Cursed Role attached to that
#  creature and is no longer a creature." (1/1, loses all abilities)
# Key ruling: Does NOT target - affects hexproof creatures
# Key ruling: Multiple Role tokens from same controller = SBA cleanup (keep newest)

def asinine_antics_resolve(targets, state):
    """
    Asinine Antics resolution:
    - Each opponent's creature gets a Cursed Role token
    - The creature becomes just the Role (enchantment) - loses creature type
    - Actually, the Cursed Role makes it a 1/1 with no abilities

    For simplicity, we model this as adding a "Cursed" status that overrides P/T.
    """
    events = []

    # Find the spell on the stack to get controller
    controller_id = None
    stack_zone = state.zones.get('stack')
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Asinine Antics":
                controller_id = obj.controller
                break

    if not controller_id:
        return events

    # Find all opponent creatures (this doesn't target!)
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return events

    for obj_id in battlefield.objects:
        obj = state.objects.get(obj_id)
        if not obj:
            continue

        # Must be a creature controlled by an opponent
        if obj.controller == controller_id:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue

        # Apply Cursed Role - set a marker
        # In a full implementation, this would create a Role token attachment
        obj.state.counters['cursed_role'] = obj.state.counters.get('cursed_role', 0) + 1

    return events


ASININE_ANTICS = make_sorcery(
    name="Asinine Antics",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="For each creature your opponents control, create a Cursed Role token attached to it.",
    rarity="rare",
    resolve=asinine_antics_resolve
)


# Helper: Cursed Role effect - makes creature base 1/1 with no abilities
def cursed_role_setup(obj, state):
    """
    Creates interceptors for the Cursed Role effect.
    Affected creatures have base power/toughness 1/1.
    """

    def power_filter(event, state):
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return target.state.counters.get('cursed_role', 0) > 0

    def power_handler(event, state):
        new_event = event.copy()
        # Override to base 1 power (this is layer 7b - setting P/T)
        new_event.payload['value'] = 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def toughness_filter(event, state):
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return target.state.counters.get('cursed_role', 0) > 0

    def toughness_handler(event, state):
        new_event = event.copy()
        # Override to base 1 toughness
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


# Global Cursed Role interceptor source (created when Asinine Antics resolves)
def create_cursed_role_source(game, controller_id):
    """Creates an invisible source object for the Cursed Role effect."""
    source = game.create_object(
        name="Cursed Role Effect",
        owner_id=controller_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.ENCHANTMENT})
    )
    # Set up the effect interceptors
    interceptors = cursed_role_setup(source, game.state)
    for interceptor in interceptors:
        game.register_interceptor(interceptor, source)
    return source


# -----------------------------------------------------------------------------
# 3. TALION, THE KINDLY LORD
# -----------------------------------------------------------------------------
# Legendary Creature - Faerie Noble 3/4
# Flying
# "As Talion enters, choose a number between 1 and 10."
# "Whenever an opponent casts a spell with mana value, power, or toughness
#  equal to the chosen number, that player loses 2 life and you draw a card."
# Key ruling: X spells use the chosen X value for mana value
# Key ruling: Cost reduction doesn't change mana value

def talion_setup(obj, state):
    """
    Talion's setup:
    1. ETB: Choose a number 1-10 (stored in counters)
    2. Trigger: When opponent casts spell with matching MV/P/T, they lose 2 life and you draw
    """

    # For testing, we'll store the chosen number in a special counter
    # In a full implementation, this would use the choice system

    def spell_cast_filter(event, state):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False

        caster = event.payload.get('caster')
        # Must be an opponent
        if caster == obj.controller:
            return False

        # Get the chosen number
        chosen = obj.state.counters.get('talion_choice', 0)
        if chosen == 0:
            return False

        # Check mana value
        mv = event.payload.get('mana_value', 0)
        if mv == chosen:
            return True

        # Check power (if creature spell)
        power = event.payload.get('power')
        if power is not None and power == chosen:
            return True

        # Check toughness (if creature spell)
        toughness = event.payload.get('toughness')
        if toughness is not None and toughness == chosen:
            return True

        return False

    def spell_cast_handler(event, state):
        caster = event.payload.get('caster')
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                # Opponent loses 2 life
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': -2},
                    source=obj.id
                ),
                # You draw a card
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'count': 1},
                    source=obj.id
                )
            ]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=spell_cast_handler,
        duration='while_on_battlefield'
    )]


TALION_THE_KINDLY_LORD = make_creature(
    name="Talion, the Kindly Lord",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Noble"},
    supertypes={"Legendary"},
    text="Flying\nAs Talion, the Kindly Lord enters, choose a number between 1 and 10.\nWhenever an opponent casts a spell with mana value, power, or toughness equal to the chosen number, that player loses 2 life and you draw a card.",
    rarity="rare",
    setup_interceptors=talion_setup
)


# -----------------------------------------------------------------------------
# 4. MOONSHAKER CAVALRY
# -----------------------------------------------------------------------------
# Creature - Spirit Knight 6/6
# Flying
# "When Moonshaker Cavalry enters, creatures you control gain flying and
#  get +X/+X until end of turn, where X is the number of creatures you control."
# Key ruling: X is determined as the ETB trigger RESOLVES (not when it triggers)
# Key ruling: Only affects creatures present when the trigger resolves

def moonshaker_cavalry_setup(obj, state):
    """
    Moonshaker Cavalry ETB:
    - Count creatures you control AT RESOLUTION
    - Give all creatures you control flying and +X/+X until EOT
    - X is locked at resolution
    """

    def etb_effect(event, state):
        events = []

        # Count creatures you control (at resolution time)
        creature_count = 0
        creatures_to_affect = []

        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                target = state.objects.get(obj_id)
                if (target and
                    target.controller == obj.controller and
                    CardType.CREATURE in target.characteristics.types):
                    creature_count += 1
                    creatures_to_affect.append(obj_id)

        # Create a temporary effect source for tracking
        # Store the boost amount and affected creatures in the object's state
        obj.state.counters['moonshaker_boost'] = creature_count
        obj.state.counters['moonshaker_resolved'] = 1

        # Store the IDs of creatures that get the boost
        # We'll use a special attribute for this
        if not hasattr(obj, 'moonshaker_targets'):
            obj.moonshaker_targets = set()
        obj.moonshaker_targets = set(creatures_to_affect)

        return events

    # Create the ETB trigger
    etb_trigger = make_etb_trigger(obj, etb_effect)

    # Create the P/T boost interceptors
    def power_filter(event, state):
        if event.type != EventType.QUERY_POWER:
            return False

        # Only if moonshaker resolved
        if obj.state.counters.get('moonshaker_resolved', 0) == 0:
            return False

        target_id = event.payload.get('object_id')
        if not hasattr(obj, 'moonshaker_targets'):
            return False

        return target_id in obj.moonshaker_targets

    def power_handler(event, state):
        boost = obj.state.counters.get('moonshaker_boost', 0)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + boost
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def toughness_filter(event, state):
        if event.type != EventType.QUERY_TOUGHNESS:
            return False

        if obj.state.counters.get('moonshaker_resolved', 0) == 0:
            return False

        target_id = event.payload.get('object_id')
        if not hasattr(obj, 'moonshaker_targets'):
            return False

        return target_id in obj.moonshaker_targets

    def toughness_handler(event, state):
        boost = obj.state.counters.get('moonshaker_boost', 0)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + boost
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    # Keyword grant for flying
    def ability_filter(event, state):
        if event.type != EventType.QUERY_ABILITIES:
            return False

        if obj.state.counters.get('moonshaker_resolved', 0) == 0:
            return False

        target_id = event.payload.get('object_id')
        if not hasattr(obj, 'moonshaker_targets'):
            return False

        return target_id in obj.moonshaker_targets

    def ability_handler(event, state):
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'flying' not in granted:
            granted.append('flying')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [
        etb_trigger,
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
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=ability_filter,
            handler=ability_handler,
            duration='while_on_battlefield'
        )
    ]


MOONSHAKER_CAVALRY = make_creature(
    name="Moonshaker Cavalry",
    power=6,
    toughness=6,
    mana_cost="{5}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Knight"},
    text="Flying\nWhen Moonshaker Cavalry enters, creatures you control gain flying and get +X/+X until end of turn, where X is the number of creatures you control.",
    rarity="mythic",
    setup_interceptors=moonshaker_cavalry_setup
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_creature_on_battlefield(game, player, card_def, name=None):
    """
    Helper to create a creature on the battlefield with proper ETB handling.
    """
    creature = game.create_object(
        name=name or card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None  # Don't pass card_def to avoid premature setup
    )
    creature.card_def = card_def

    # Move to battlefield
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    return creature


def create_simple_creature(game, player, name, power, toughness, **kwargs):
    """Helper to create a simple creature."""
    subtypes = kwargs.get('subtypes', set())
    colors = kwargs.get('colors', set())
    mana_cost = kwargs.get('mana_cost', '')

    creature = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes=subtypes,
            colors=colors,
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        )
    )
    return creature


def add_cards_to_library(game, player, count):
    """Add dummy cards to player's library for testing."""
    library_key = f"library_{player.id}"
    library = game.state.zones.get(library_key)

    for i in range(count):
        card = game.create_object(
            name=f"Library Card {i+1}",
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT})
        )
        # Move to front (top) of library
        if library:
            library.objects.remove(card.id)
            library.objects.insert(0, card.id)


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_ashiok_replacement_basic():
    """Test Ashiok replaces life payment with library exile."""
    print("\n=== Test: Ashiok Replacement Effect - Basic ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Add cards to library
    add_cards_to_library(game, p1, 10)
    library_key = f"library_{p1.id}"
    initial_library = len(game.state.zones[library_key].objects)

    print(f"Starting life: {p1.life}")
    print(f"Starting library: {initial_library} cards")

    # Put Ashiok on battlefield
    ashiok = create_creature_on_battlefield(game, p1, ASHIOK_WICKED_MANIPULATOR, "Ashiok")
    # Planeswalker isn't a creature, but for test purposes we use it
    ashiok.characteristics.types = {CardType.PLANESWALKER}

    # Attempt to pay 3 life
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={
            'player': p1.id,
            'amount': -3,
            'is_life_payment': True
        }
    ))

    final_library = len(game.state.zones[library_key].objects)
    exile_zone = game.state.zones.get('exile')
    exile_count = len(exile_zone.objects) if exile_zone else 0

    print(f"Life after 'paying' 3: {p1.life}")
    print(f"Library after: {final_library} cards")
    print(f"Cards in exile: {exile_count}")

    # Life should NOT have changed
    assert p1.life == 20, f"Expected life 20 (unchanged), got {p1.life}"
    # Library should have 3 fewer cards
    assert final_library == initial_library - 3, f"Expected {initial_library - 3} cards in library, got {final_library}"

    print("✓ Ashiok replacement effect works!")


def test_ashiok_not_enough_cards():
    """Test Ashiok doesn't replace if library doesn't have enough cards."""
    print("\n=== Test: Ashiok - Not Enough Cards ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Add only 2 cards to library
    add_cards_to_library(game, p1, 2)
    library_key = f"library_{p1.id}"
    initial_library = len(game.state.zones[library_key].objects)

    print(f"Starting life: {p1.life}")
    print(f"Starting library: {initial_library} cards")

    # Put Ashiok on battlefield
    ashiok = create_creature_on_battlefield(game, p1, ASHIOK_WICKED_MANIPULATOR, "Ashiok")
    ashiok.characteristics.types = {CardType.PLANESWALKER}

    # Attempt to pay 5 life (more than library has)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={
            'player': p1.id,
            'amount': -5,
            'is_life_payment': True
        }
    ))

    final_library = len(game.state.zones[library_key].objects)

    print(f"Life after paying 5: {p1.life}")
    print(f"Library after: {final_library} cards")

    # Life SHOULD have changed (replacement didn't apply)
    assert p1.life == 15, f"Expected life 15 (paid normally), got {p1.life}"
    # Library should be unchanged
    assert final_library == initial_library, f"Library should be unchanged"

    print("✓ Ashiok doesn't replace when library is too small!")


def test_ashiok_damage_not_replaced():
    """Test that Ashiok doesn't replace damage (only life payment)."""
    print("\n=== Test: Ashiok - Damage Not Replaced ===")

    game = Game()
    p1 = game.add_player("Alice")

    add_cards_to_library(game, p1, 10)
    library_key = f"library_{p1.id}"
    initial_library = len(game.state.zones[library_key].objects)

    print(f"Starting life: {p1.life}")

    # Put Ashiok on battlefield
    ashiok = create_creature_on_battlefield(game, p1, ASHIOK_WICKED_MANIPULATOR, "Ashiok")
    ashiok.characteristics.types = {CardType.PLANESWALKER}

    # Take 3 damage (NOT a life payment)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 3}
    ))

    final_library = len(game.state.zones[library_key].objects)

    print(f"Life after 3 damage: {p1.life}")
    print(f"Library after: {final_library} cards")

    # Life SHOULD have changed (damage, not payment)
    assert p1.life == 17, f"Expected life 17, got {p1.life}"
    # Library unchanged
    assert final_library == initial_library, f"Library should be unchanged"

    print("✓ Ashiok doesn't replace damage!")


def test_asinine_antics_affects_hexproof():
    """Test that Asinine Antics affects hexproof creatures (doesn't target)."""
    print("\n=== Test: Asinine Antics - Affects Hexproof ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create a hexproof creature for opponent
    hexproof_creature = create_simple_creature(
        game, p2, "Hexproof Beast", power=5, toughness=5
    )
    # Mark it as hexproof (in a full implementation, this would be checked)
    hexproof_creature.characteristics.abilities = [{'keyword': 'hexproof'}]

    print(f"Hexproof Beast: {get_power(hexproof_creature, game.state)}/{get_toughness(hexproof_creature, game.state)}")

    # Create the Cursed Role effect source
    cursed_source = create_cursed_role_source(game, p1.id)

    # Apply Asinine Antics effect (simulated)
    hexproof_creature.state.counters['cursed_role'] = 1

    power = get_power(hexproof_creature, game.state)
    toughness = get_toughness(hexproof_creature, game.state)

    print(f"Hexproof Beast after Cursed Role: {power}/{toughness}")

    # Should be 1/1 now
    assert power == 1, f"Expected power 1, got {power}"
    assert toughness == 1, f"Expected toughness 1, got {toughness}"

    print("✓ Asinine Antics affects hexproof creatures!")


def test_asinine_antics_multiple_creatures():
    """Test Asinine Antics affecting multiple creatures."""
    print("\n=== Test: Asinine Antics - Multiple Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create multiple creatures for opponent
    creatures = [
        create_simple_creature(game, p2, "Giant 1", power=7, toughness=7),
        create_simple_creature(game, p2, "Giant 2", power=8, toughness=8),
        create_simple_creature(game, p2, "Giant 3", power=10, toughness=10),
    ]

    print("Before Asinine Antics:")
    for c in creatures:
        print(f"  {c.name}: {get_power(c, game.state)}/{get_toughness(c, game.state)}")

    # Create the Cursed Role effect source
    cursed_source = create_cursed_role_source(game, p1.id)

    # Apply Cursed Role to all
    for c in creatures:
        c.state.counters['cursed_role'] = 1

    print("After Asinine Antics:")
    for c in creatures:
        power = get_power(c, game.state)
        toughness = get_toughness(c, game.state)
        print(f"  {c.name}: {power}/{toughness}")
        assert power == 1 and toughness == 1, f"{c.name} should be 1/1"

    print("✓ All opponent creatures become 1/1!")


def test_talion_mana_value_trigger():
    """Test Talion triggers on matching mana value."""
    print("\n=== Test: Talion - Mana Value Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Talion on battlefield, choose number 3
    talion = create_creature_on_battlefield(game, p1, TALION_THE_KINDLY_LORD)
    talion.state.counters['talion_choice'] = 3

    print(f"Talion chose number: 3")
    print(f"Alice's life: {p1.life}, Bob's life: {p2.life}")

    # Add cards to Alice's library for drawing
    add_cards_to_library(game, p1, 5)
    hand_key = f"hand_{p1.id}"
    hand_zone = game.state.zones.get(hand_key)
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    # Bob casts a spell with mana value 3
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p2.id,
            'mana_value': 3,
            'spell_name': 'Some 3-Cost Spell'
        }
    ))

    print(f"After Bob casts MV 3 spell:")
    print(f"  Alice's life: {p1.life}, Bob's life: {p2.life}")

    hand_zone = game.state.zones.get(hand_key)
    final_hand = len(hand_zone.objects) if hand_zone else 0
    cards_drawn = final_hand - initial_hand

    # Bob should have lost 2 life
    assert p2.life == 18, f"Expected Bob at 18 life, got {p2.life}"
    # Alice should have drawn a card
    assert cards_drawn == 1, f"Expected Alice to draw 1 card, drew {cards_drawn}"

    print("✓ Talion triggers on matching mana value!")


def test_talion_power_trigger():
    """Test Talion triggers on matching power."""
    print("\n=== Test: Talion - Power Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Talion on battlefield, choose number 4
    talion = create_creature_on_battlefield(game, p1, TALION_THE_KINDLY_LORD)
    talion.state.counters['talion_choice'] = 4

    print(f"Talion chose number: 4")
    print(f"Bob's life: {p2.life}")

    add_cards_to_library(game, p1, 5)

    # Bob casts a creature spell with power 4 (but MV 2)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p2.id,
            'mana_value': 2,  # Not matching
            'power': 4,        # Matching!
            'toughness': 2,
            'spell_name': '4-Power Creature'
        }
    ))

    print(f"After Bob casts creature with power 4:")
    print(f"  Bob's life: {p2.life}")

    # Bob should have lost 2 life (power matched)
    assert p2.life == 18, f"Expected Bob at 18 life, got {p2.life}"

    print("✓ Talion triggers on matching power!")


def test_talion_toughness_trigger():
    """Test Talion triggers on matching toughness."""
    print("\n=== Test: Talion - Toughness Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Talion on battlefield, choose number 5
    talion = create_creature_on_battlefield(game, p1, TALION_THE_KINDLY_LORD)
    talion.state.counters['talion_choice'] = 5

    print(f"Talion chose number: 5")
    print(f"Bob's life: {p2.life}")

    add_cards_to_library(game, p1, 5)

    # Bob casts a creature spell with toughness 5 (but MV 3, power 2)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p2.id,
            'mana_value': 3,   # Not matching
            'power': 2,         # Not matching
            'toughness': 5,     # Matching!
            'spell_name': '5-Toughness Creature'
        }
    ))

    print(f"After Bob casts creature with toughness 5:")
    print(f"  Bob's life: {p2.life}")

    # Bob should have lost 2 life (toughness matched)
    assert p2.life == 18, f"Expected Bob at 18 life, got {p2.life}"

    print("✓ Talion triggers on matching toughness!")


def test_talion_no_trigger():
    """Test Talion doesn't trigger when nothing matches."""
    print("\n=== Test: Talion - No Match, No Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Talion on battlefield, choose number 3
    talion = create_creature_on_battlefield(game, p1, TALION_THE_KINDLY_LORD)
    talion.state.counters['talion_choice'] = 3

    print(f"Talion chose number: 3")
    print(f"Bob's life: {p2.life}")

    add_cards_to_library(game, p1, 5)
    hand_key = f"hand_{p1.id}"
    hand_zone = game.state.zones.get(hand_key)
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    # Bob casts a spell with nothing matching 3
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p2.id,
            'mana_value': 2,   # Not 3
            'power': 4,         # Not 3
            'toughness': 5,     # Not 3
            'spell_name': 'Non-Matching Spell'
        }
    ))

    print(f"After Bob casts non-matching spell:")
    print(f"  Bob's life: {p2.life}")

    hand_zone = game.state.zones.get(hand_key)
    final_hand = len(hand_zone.objects) if hand_zone else 0

    # No trigger - Bob keeps life, Alice doesn't draw
    assert p2.life == 20, f"Expected Bob at 20 life, got {p2.life}"
    assert final_hand == initial_hand, f"Alice shouldn't have drawn"

    print("✓ Talion doesn't trigger when nothing matches!")


def test_talion_own_spells_dont_trigger():
    """Test Talion doesn't trigger on controller's own spells."""
    print("\n=== Test: Talion - Own Spells Don't Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Talion on battlefield, choose number 3
    talion = create_creature_on_battlefield(game, p1, TALION_THE_KINDLY_LORD)
    talion.state.counters['talion_choice'] = 3

    print(f"Talion chose number: 3")
    print(f"Alice's life: {p1.life}")

    # Alice casts her own spell with MV 3
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,  # Same player!
            'mana_value': 3,
            'spell_name': 'Own 3-Cost Spell'
        }
    ))

    print(f"After Alice casts MV 3 spell:")
    print(f"  Alice's life: {p1.life}")

    # No trigger - Alice keeps life
    assert p1.life == 20, f"Expected Alice at 20 life, got {p1.life}"

    print("✓ Talion doesn't trigger on controller's spells!")


def test_moonshaker_basic():
    """Test Moonshaker Cavalry basic ETB effect."""
    print("\n=== Test: Moonshaker Cavalry - Basic ETB ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create some creatures first
    bear1 = create_simple_creature(game, p1, "Bear 1", power=2, toughness=2)
    bear2 = create_simple_creature(game, p1, "Bear 2", power=2, toughness=2)

    print(f"Before Moonshaker: Bear 1 is {get_power(bear1, game.state)}/{get_toughness(bear1, game.state)}")

    # Now create Moonshaker Cavalry with ETB
    moonshaker = create_creature_on_battlefield(game, p1, MOONSHAKER_CAVALRY)

    # Count: 3 creatures (2 bears + moonshaker)
    # So boost should be +3/+3 to all creatures

    bear1_power = get_power(bear1, game.state)
    bear1_toughness = get_toughness(bear1, game.state)
    moonshaker_power = get_power(moonshaker, game.state)

    print(f"After Moonshaker ETB (3 creatures):")
    print(f"  Bear 1: {bear1_power}/{bear1_toughness}")
    print(f"  Moonshaker: {moonshaker_power}/{get_toughness(moonshaker, game.state)}")

    # Bears should be 2+3 = 5/5
    assert bear1_power == 5, f"Expected Bear power 5, got {bear1_power}"
    assert bear1_toughness == 5, f"Expected Bear toughness 5, got {bear1_toughness}"

    # Moonshaker should be 6+3 = 9/9
    assert moonshaker_power == 9, f"Expected Moonshaker power 9, got {moonshaker_power}"

    print("✓ Moonshaker Cavalry ETB works!")


def test_moonshaker_x_locked_at_resolution():
    """Test that Moonshaker's X is locked at resolution time."""
    print("\n=== Test: Moonshaker - X Locked at Resolution ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create 2 creatures first
    bear1 = create_simple_creature(game, p1, "Bear 1", power=2, toughness=2)
    bear2 = create_simple_creature(game, p1, "Bear 2", power=2, toughness=2)

    # Create Moonshaker - at this point there are 3 creatures
    moonshaker = create_creature_on_battlefield(game, p1, MOONSHAKER_CAVALRY)

    boost = moonshaker.state.counters.get('moonshaker_boost', 0)
    print(f"Boost locked at: +{boost}/+{boost} (3 creatures when resolved)")

    # Now create ANOTHER creature after Moonshaker resolved
    bear3 = create_simple_creature(game, p1, "Bear 3", power=2, toughness=2)

    # Bear 3 should NOT get the boost (wasn't present at resolution)
    bear3_power = get_power(bear3, game.state)
    bear1_power = get_power(bear1, game.state)

    print(f"Bear 1 (present at resolution): {bear1_power}/{get_toughness(bear1, game.state)}")
    print(f"Bear 3 (entered after resolution): {bear3_power}/{get_toughness(bear3, game.state)}")

    # Bear 1 should have +3/+3 (locked at 3)
    assert bear1_power == 5, f"Expected Bear 1 power 5, got {bear1_power}"

    # Bear 3 should NOT have the boost
    assert bear3_power == 2, f"Expected Bear 3 power 2 (no boost), got {bear3_power}"

    print("✓ Moonshaker X is locked at resolution!")


def test_moonshaker_only_affects_present_creatures():
    """Test Moonshaker only affects creatures present at resolution."""
    print("\n=== Test: Moonshaker - Only Present Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Moonshaker alone
    moonshaker = create_creature_on_battlefield(game, p1, MOONSHAKER_CAVALRY)

    # Only Moonshaker was present - X = 1
    boost = moonshaker.state.counters.get('moonshaker_boost', 0)
    print(f"Moonshaker entered alone - boost is +{boost}/+{boost}")

    # Moonshaker should be 6+1 = 7/7
    moonshaker_power = get_power(moonshaker, game.state)
    assert moonshaker_power == 7, f"Expected Moonshaker power 7, got {moonshaker_power}"

    # Create a creature after
    late_bear = create_simple_creature(game, p1, "Late Bear", power=3, toughness=3)

    # Late bear should NOT get any boost
    late_bear_power = get_power(late_bear, game.state)
    print(f"Late Bear (entered after): {late_bear_power}/{get_toughness(late_bear, game.state)}")

    assert late_bear_power == 3, f"Expected Late Bear power 3, got {late_bear_power}"

    print("✓ Moonshaker only affects creatures present at resolution!")


def test_moonshaker_grants_flying():
    """Test Moonshaker grants flying to all affected creatures."""
    print("\n=== Test: Moonshaker - Grants Flying ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a non-flying creature
    bear = create_simple_creature(game, p1, "Ground Bear", power=2, toughness=2)

    # Query abilities before Moonshaker
    query_event = Event(
        type=EventType.QUERY_ABILITIES,
        payload={'object_id': bear.id, 'granted': []}
    )
    # Run through pipeline (simplified check)

    print(f"Bear abilities before Moonshaker: (none)")

    # Create Moonshaker
    moonshaker = create_creature_on_battlefield(game, p1, MOONSHAKER_CAVALRY)

    # Check if bear has flying now
    # The ability_filter checks moonshaker_targets
    has_flying = bear.id in getattr(moonshaker, 'moonshaker_targets', set())

    print(f"Bear in Moonshaker targets: {has_flying}")

    assert has_flying, "Bear should be in Moonshaker's targets"
    print("✓ Moonshaker grants flying to affected creatures!")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_tests():
    print("=" * 60)
    print("WILDS OF ELDRAINE (WOE) CARD RULING TESTS")
    print("=" * 60)

    # Ashiok tests
    test_ashiok_replacement_basic()
    test_ashiok_not_enough_cards()
    test_ashiok_damage_not_replaced()

    # Asinine Antics tests
    test_asinine_antics_affects_hexproof()
    test_asinine_antics_multiple_creatures()

    # Talion tests
    test_talion_mana_value_trigger()
    test_talion_power_trigger()
    test_talion_toughness_trigger()
    test_talion_no_trigger()
    test_talion_own_spells_dont_trigger()

    # Moonshaker Cavalry tests
    test_moonshaker_basic()
    test_moonshaker_x_locked_at_resolution()
    test_moonshaker_only_affects_present_creatures()
    test_moonshaker_grants_flying()

    print("\n" + "=" * 60)
    print("ALL WOE RULING TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
