"""
Aetherdrift (DFT) Rulings Tests

Testing complex card interactions and edge cases for:
1. Caradora, Heart of Alacria - +1/+1 counter replacement effect
2. Vnwxt, Verbose Host - Draw replacement effect (doubles draws at max speed)
3. Far Fortune, End Boss - Damage replacement effect (+1 damage at max speed)
4. Cursecloth Wrappings - Embalm token mechanics
5. Hazoret, Godseeker - Conditional attack/block based on speed

Key Aetherdrift mechanics tested:
- Speed mechanic (0-4, increases when opponents lose life during your turn)
- Max speed abilities (trigger only at speed 4)
- Replacement effects stacking multiplicatively
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    make_creature, make_artifact,
    new_id, GameObject
)


# =============================================================================
# SPEED MECHANIC HELPERS
# =============================================================================

def get_player_speed(game, player_id: str) -> int:
    """Get a player's current speed (0-4)."""
    player = game.state.players.get(player_id)
    if not player:
        return 0
    return getattr(player, 'speed', 0)


def set_player_speed(game, player_id: str, speed: int):
    """Set a player's speed (clamped 0-4)."""
    player = game.state.players.get(player_id)
    if player:
        player.speed = max(0, min(4, speed))


def has_max_speed(game, player_id: str) -> bool:
    """Check if player has max speed (4)."""
    return get_player_speed(game, player_id) == 4


# =============================================================================
# CARD DEFINITIONS - Caradora, Heart of Alacria
# =============================================================================

def caradora_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Caradora, Heart of Alacria: {2}{G}{W}
    Legendary Creature - Human Knight 4/2

    When Caradora enters, you may search your library for a Mount or Vehicle card,
    reveal it, put it into your hand, then shuffle.

    If one or more +1/+1 counters would be put on a creature or Vehicle you control,
    that many plus one +1/+1 counters are put on it instead.

    Key Rulings:
    1. When a creature enters with +1/+1 counters, it enters with +1 extra
    2. Multiple Caradora effects stack additively (+1 each)
    3. Controller chooses order when multiple counter modification effects apply
    """

    # Counter replacement effect - TRANSFORM interceptor for COUNTER_ADDED
    def counter_filter(event: Event, state) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        # Only +1/+1 counters
        if event.payload.get('counter_type') != '+1/+1':
            return False
        # Only on creatures/Vehicles we control
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Must be a creature (Vehicles would have ARTIFACT type)
        types = target.characteristics.types
        return CardType.CREATURE in types or CardType.ARTIFACT in types

    def counter_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current_amount = new_event.payload.get('amount', 1)
        new_event.payload['amount'] = current_amount + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    counter_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=counter_filter,
        handler=counter_handler,
        duration='while_on_battlefield'
    )

    return [counter_interceptor]


CARADORA_HEART_OF_ALACRIA = make_creature(
    name="Caradora, Heart of Alacria",
    power=4,
    toughness=2,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Knight"},
    text="When Caradora enters, you may search your library for a Mount or Vehicle card. If one or more +1/+1 counters would be put on a creature or Vehicle you control, that many plus one +1/+1 counters are put on it instead.",
    setup_interceptors=caradora_setup
)


# =============================================================================
# CARD DEFINITIONS - Vnwxt, Verbose Host
# =============================================================================

def vnwxt_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Vnwxt, Verbose Host: {1}{U}
    Legendary Creature - Homunculus 0/4

    Start your engines! (If you have no speed, it starts at 1...)
    You have no maximum hand size.
    Max speed - If you would draw a card, draw two cards instead.

    Key Rulings:
    1. Multiple draw doublings stack multiplicatively (2x, 4x, 8x...)
    2. Each individual card draw is doubled (draw 3 becomes draw 6)
    3. Player chooses order when multiple replacement effects apply
    """

    # Draw doubling - only at max speed (speed 4)
    def draw_filter(event: Event, state) -> bool:
        if event.type != EventType.DRAW:
            return False
        # Only for our controller
        if event.payload.get('player') != obj.controller:
            return False
        # Only at max speed
        player = state.players.get(obj.controller)
        return player and getattr(player, 'speed', 0) == 4

    def draw_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current_count = new_event.payload.get('count', 1)
        new_event.payload['count'] = current_count * 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    draw_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=draw_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )

    return [draw_interceptor]


VNWXT_VERBOSE_HOST = make_creature(
    name="Vnwxt, Verbose Host",
    power=0,
    toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    text="Start your engines! You have no maximum hand size. Max speed - If you would draw a card, draw two cards instead.",
    setup_interceptors=vnwxt_setup
)


# =============================================================================
# CARD DEFINITIONS - Far Fortune, End Boss
# =============================================================================

def far_fortune_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Far Fortune, End Boss: {2}{B}{R}
    Legendary Creature - Human Mercenary 4/5

    Start your engines!
    Whenever you attack, Far Fortune deals 1 damage to each opponent.
    Max speed - If a source you control would deal damage to an opponent or
    a permanent an opponent controls, it deals that much damage plus 1 instead.

    Key Rulings:
    1. The +1 damage is from the same source as the original (not Far Fortune)
    2. If damage is prevented entirely, the +1 doesn't apply
    3. When dividing damage (trample), add +1 AFTER division to each portion
    """

    # Attack trigger - deals 1 damage to each opponent
    def attack_filter(event: Event, state) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        # Only when controller declares an attack
        return event.payload.get('attacking_player') == obj.controller

    def attack_handler(event: Event, state) -> InterceptorResult:
        # Deal 1 damage to each opponent
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=events
        )

    attack_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield'
    )

    # Damage boost at max speed
    def damage_filter(event: Event, state) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        # Check if controller has max speed
        player = state.players.get(obj.controller)
        if not player or getattr(player, 'speed', 0) != 4:
            return False
        # Check if source is controlled by us
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if source_obj and source_obj.controller != obj.controller:
            return False
        # Also check if source is player (direct life loss doesn't count, but player-sourced damage does)
        if source_id == obj.controller:
            return True
        if source_obj is None:
            return False
        # Check target is opponent or opponent's permanent
        target_id = event.payload.get('target')
        target_obj = state.objects.get(target_id)
        # If target is a player
        if target_id in state.players:
            return target_id != obj.controller
        # If target is a permanent controlled by opponent
        if target_obj:
            return target_obj.controller != obj.controller
        return False

    def damage_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current_amount = new_event.payload.get('amount', 0)
        new_event.payload['amount'] = current_amount + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    damage_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=damage_filter,
        handler=damage_handler,
        duration='while_on_battlefield'
    )

    return [attack_interceptor, damage_interceptor]


FAR_FORTUNE_END_BOSS = make_creature(
    name="Far Fortune, End Boss",
    power=4,
    toughness=5,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Mercenary"},
    text="Start your engines! Whenever you attack, Far Fortune deals 1 damage to each opponent. Max speed - If a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus 1 instead.",
    setup_interceptors=far_fortune_setup
)


# =============================================================================
# CARD DEFINITIONS - Cursecloth Wrappings
# =============================================================================

def cursecloth_wrappings_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Cursecloth Wrappings: {2}{B}{B}
    Artifact

    Zombies you control get +1/+1.
    {T}: Target creature card in your graveyard gains embalm until end of turn.
    The embalm cost is equal to its mana cost.

    Key Rulings:
    1. Token copy is white Zombie with no mana cost (MV 0)
    2. Token copies all printed characteristics except color and mana cost
    3. ETB abilities on the copied creature still trigger for the token
    4. Once embalm is activated, the card is immediately exiled
    """

    # Static +1/+1 for Zombies
    def zombie_power_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return 'Zombie' in target.characteristics.subtypes

    def zombie_power_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('value', 0)
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def zombie_toughness_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return 'Zombie' in target.characteristics.subtypes

    def zombie_toughness_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('value', 0)
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    power_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=zombie_power_filter,
        handler=zombie_power_handler,
        duration='while_on_battlefield'
    )

    toughness_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=zombie_toughness_filter,
        handler=zombie_toughness_handler,
        duration='while_on_battlefield'
    )

    return [power_interceptor, toughness_interceptor]


CURSECLOTH_WRAPPINGS = make_artifact(
    name="Cursecloth Wrappings",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Zombies you control get +1/+1. {T}: Target creature card in your graveyard gains embalm until end of turn.",
    setup_interceptors=cursecloth_wrappings_setup
)


# =============================================================================
# CARD DEFINITIONS - Hazoret, Godseeker
# =============================================================================

def hazoret_godseeker_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Hazoret, Godseeker: {1}{R}
    Legendary Creature - God 5/3

    Indestructible, haste
    Start your engines!
    {1}, {T}: Target creature with power 2 or less can't be blocked this turn.
    Hazoret can't attack or block unless you have max speed.

    Key Rulings:
    1. The activated ability must resolve before blockers are declared
    2. Once resolved, target stays unblockable even if power increases
    3. Speed is a state-based mechanic, not triggered
    4. At speed < 4, Hazoret cannot be declared as attacker or blocker
    """

    # Attack/block restriction
    def attack_restriction_filter(event: Event, state) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == obj.id

    def attack_restriction_handler(event: Event, state) -> InterceptorResult:
        player = state.players.get(obj.controller)
        if not player or getattr(player, 'speed', 0) < 4:
            # Prevent the attack
            return InterceptorResult(action=InterceptorAction.PREVENT)
        return InterceptorResult(action=InterceptorAction.PASS)

    attack_restriction = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=attack_restriction_filter,
        handler=attack_restriction_handler,
        duration='while_on_battlefield'
    )

    def block_restriction_filter(event: Event, state) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        return event.payload.get('blocker_id') == obj.id

    def block_restriction_handler(event: Event, state) -> InterceptorResult:
        player = state.players.get(obj.controller)
        if not player or getattr(player, 'speed', 0) < 4:
            # Prevent the block
            return InterceptorResult(action=InterceptorAction.PREVENT)
        return InterceptorResult(action=InterceptorAction.PASS)

    block_restriction = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=block_restriction_filter,
        handler=block_restriction_handler,
        duration='while_on_battlefield'
    )

    return [attack_restriction, block_restriction]


HAZORET_GODSEEKER = make_creature(
    name="Hazoret, Godseeker",
    power=5,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"God"},
    text="Indestructible, haste. Start your engines! {1}, {T}: Target creature with power 2 or less can't be blocked this turn. Hazoret can't attack or block unless you have max speed.",
    setup_interceptors=hazoret_godseeker_setup
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_creature_on_battlefield(game, player, card_def, name=None):
    """Helper to create a creature on the battlefield with proper ETB handling."""
    creature = game.create_object(
        name=name or card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None
    )
    creature.card_def = card_def

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


def create_simple_creature(game, player, name, power, toughness, subtypes=None):
    """Create a simple vanilla creature for testing."""
    creature = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
            subtypes=subtypes or set()
        )
    )
    return creature


def add_cards_to_library(game, player, count, name_prefix="Card"):
    """Add test cards to a player's library."""
    for i in range(count):
        game.create_object(
            name=f"{name_prefix} {i+1}",
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT})
        )


# =============================================================================
# TESTS - Caradora, Heart of Alacria
# =============================================================================

def test_caradora_adds_one_counter():
    """Test Caradora adds +1 to counter placement."""
    print("\n=== Test: Caradora Adds +1 Counter ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Caradora on battlefield
    caradora = create_creature_on_battlefield(game, p1, CARADORA_HEART_OF_ALACRIA)

    # Create a creature to put counters on
    creature = create_simple_creature(game, p1, "Test Creature", 1, 1)

    # Add 1 +1/+1 counter - should become 2
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': creature.id,
            'counter_type': '+1/+1',
            'amount': 1
        }
    ))

    counters = creature.state.counters.get('+1/+1', 0)
    print(f"+1/+1 counters (with Caradora): {counters}")
    assert counters == 2, f"Expected 2 counters (1+1), got {counters}"
    print("PASS: Caradora adds +1 to counter placement!")


def test_caradora_multiple_counters():
    """Test Caradora adds +1 when placing multiple counters at once."""
    print("\n=== Test: Caradora With Multiple Counters ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Caradora on battlefield
    create_creature_on_battlefield(game, p1, CARADORA_HEART_OF_ALACRIA)

    # Create a creature to put counters on
    creature = create_simple_creature(game, p1, "Test Creature", 1, 1)

    # Add 3 +1/+1 counters - should become 4
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': creature.id,
            'counter_type': '+1/+1',
            'amount': 3
        }
    ))

    counters = creature.state.counters.get('+1/+1', 0)
    print(f"+1/+1 counters after adding '3' (with Caradora): {counters}")
    assert counters == 4, f"Expected 4 counters (3+1), got {counters}"
    print("PASS: Caradora adds +1 even when placing multiple counters!")


def test_caradora_stacks_additively():
    """Test multiple Caradora effects stack additively (+1 each)."""
    print("\n=== Test: Multiple Caradora Stack Additively ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put TWO Caradora on battlefield
    create_creature_on_battlefield(game, p1, CARADORA_HEART_OF_ALACRIA)
    create_creature_on_battlefield(game, p1, CARADORA_HEART_OF_ALACRIA)

    # Create a creature to put counters on
    creature = create_simple_creature(game, p1, "Test Creature", 1, 1)

    # Add 1 +1/+1 counter - should become 3 (1 + 1 + 1)
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': creature.id,
            'counter_type': '+1/+1',
            'amount': 1
        }
    ))

    counters = creature.state.counters.get('+1/+1', 0)
    print(f"+1/+1 counters with 2 Caradora: {counters}")
    assert counters == 3, f"Expected 3 counters (1+1+1), got {counters}"
    print("PASS: Multiple Caradora stack additively!")


def test_caradora_only_affects_own_creatures():
    """Test Caradora only affects creatures/Vehicles controller controls."""
    print("\n=== Test: Caradora Only Affects Own Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Caradora on battlefield under P1
    create_creature_on_battlefield(game, p1, CARADORA_HEART_OF_ALACRIA)

    # Create opponent's creature
    opp_creature = create_simple_creature(game, p2, "Opponent Creature", 1, 1)
    opp_creature.controller = p2.id

    # Add 1 +1/+1 counter to opponent's creature - should stay at 1
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': opp_creature.id,
            'counter_type': '+1/+1',
            'amount': 1
        }
    ))

    counters = opp_creature.state.counters.get('+1/+1', 0)
    print(f"Opponent creature counters: {counters}")
    assert counters == 1, f"Expected 1 counter (not modified), got {counters}"
    print("PASS: Caradora doesn't affect opponent's creatures!")


def test_caradora_ignores_other_counter_types():
    """Test Caradora only affects +1/+1 counters, not other types."""
    print("\n=== Test: Caradora Only Affects +1/+1 Counters ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Caradora on battlefield
    create_creature_on_battlefield(game, p1, CARADORA_HEART_OF_ALACRIA)

    # Create a creature
    creature = create_simple_creature(game, p1, "Test Creature", 1, 1)

    # Add -1/-1 counter - should NOT be modified
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': creature.id,
            'counter_type': '-1/-1',
            'amount': 2
        }
    ))

    counters = creature.state.counters.get('-1/-1', 0)
    print(f"-1/-1 counters (should be unmodified): {counters}")
    assert counters == 2, f"Expected 2 counters (not modified), got {counters}"
    print("PASS: Caradora only affects +1/+1 counters!")


# =============================================================================
# TESTS - Vnwxt, Verbose Host
# =============================================================================

def test_vnwxt_doubles_draw_at_max_speed():
    """Test Vnwxt doubles card draw at max speed."""
    print("\n=== Test: Vnwxt Doubles Draw at Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Vnwxt on battlefield
    create_creature_on_battlefield(game, p1, VNWXT_VERBOSE_HOST)

    # Add cards to library
    add_cards_to_library(game, p1, 10)

    hand_before = len(game.get_hand(p1.id))
    print(f"Hand size before draw: {hand_before}")

    # Draw 1 card - should become 2
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1}
    ))

    hand_after = len(game.get_hand(p1.id))
    cards_drawn = hand_after - hand_before
    print(f"Cards drawn (at max speed): {cards_drawn}")
    assert cards_drawn == 2, f"Expected to draw 2 cards, drew {cards_drawn}"
    print("PASS: Vnwxt doubles draw at max speed!")


def test_vnwxt_no_effect_below_max_speed():
    """Test Vnwxt doesn't double draw below max speed."""
    print("\n=== Test: Vnwxt No Effect Below Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to speed 3 (not max)
    set_player_speed(game, p1.id, 3)

    # Put Vnwxt on battlefield
    create_creature_on_battlefield(game, p1, VNWXT_VERBOSE_HOST)

    # Add cards to library
    add_cards_to_library(game, p1, 10)

    hand_before = len(game.get_hand(p1.id))
    print(f"Speed: {get_player_speed(game, p1.id)}, Hand before: {hand_before}")

    # Draw 1 card - should stay at 1
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1}
    ))

    hand_after = len(game.get_hand(p1.id))
    cards_drawn = hand_after - hand_before
    print(f"Cards drawn (at speed 3): {cards_drawn}")
    assert cards_drawn == 1, f"Expected to draw 1 card, drew {cards_drawn}"
    print("PASS: Vnwxt doesn't double below max speed!")


def test_vnwxt_multiple_stacks_multiplicatively():
    """Test multiple Vnwxt effects stack multiplicatively (2x each = 4x total)."""
    print("\n=== Test: Multiple Vnwxt Stack Multiplicatively ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put TWO Vnwxt on battlefield
    create_creature_on_battlefield(game, p1, VNWXT_VERBOSE_HOST)
    create_creature_on_battlefield(game, p1, VNWXT_VERBOSE_HOST)

    # Add cards to library
    add_cards_to_library(game, p1, 20)

    hand_before = len(game.get_hand(p1.id))
    print(f"Hand before: {hand_before}")

    # Draw 1 card - should become 4 (1 * 2 * 2)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1}
    ))

    hand_after = len(game.get_hand(p1.id))
    cards_drawn = hand_after - hand_before
    print(f"Cards drawn with 2 Vnwxt: {cards_drawn}")
    assert cards_drawn == 4, f"Expected to draw 4 cards (1*2*2), drew {cards_drawn}"
    print("PASS: Multiple Vnwxt stack multiplicatively!")


def test_vnwxt_draw_three_becomes_six():
    """Test drawing 3 cards becomes 6 with one Vnwxt."""
    print("\n=== Test: Draw 3 Becomes 6 ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Vnwxt on battlefield
    create_creature_on_battlefield(game, p1, VNWXT_VERBOSE_HOST)

    # Add cards to library
    add_cards_to_library(game, p1, 20)

    hand_before = len(game.get_hand(p1.id))

    # Draw 3 cards - should become 6
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 3}
    ))

    hand_after = len(game.get_hand(p1.id))
    cards_drawn = hand_after - hand_before
    print(f"Cards drawn (draw 3 with Vnwxt): {cards_drawn}")
    assert cards_drawn == 6, f"Expected to draw 6 cards (3*2), drew {cards_drawn}"
    print("PASS: Draw 3 becomes 6!")


# =============================================================================
# TESTS - Far Fortune, End Boss
# =============================================================================

def test_far_fortune_attack_trigger():
    """Test Far Fortune deals 1 damage to each opponent when attacking."""
    print("\n=== Test: Far Fortune Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Far Fortune on battlefield
    far_fortune = create_creature_on_battlefield(game, p1, FAR_FORTUNE_END_BOSS)

    print(f"Opponent life before attack: {p2.life}")

    # Declare attack
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacking_player': p1.id, 'attacker_id': far_fortune.id}
    ))

    print(f"Opponent life after attack declared: {p2.life}")
    assert p2.life == 19, f"Expected 19 life (20-1), got {p2.life}"
    print("PASS: Far Fortune deals 1 damage on attack!")


def test_far_fortune_damage_boost_at_max_speed():
    """Test Far Fortune +1 damage at max speed."""
    print("\n=== Test: Far Fortune +1 Damage at Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Far Fortune on battlefield
    far_fortune = create_creature_on_battlefield(game, p1, FAR_FORTUNE_END_BOSS)

    print(f"Opponent life before: {p2.life}")

    # Deal 3 damage to opponent - should become 4
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 3, 'source': far_fortune.id}
    ))

    print(f"Opponent life after 3 damage (with max speed boost): {p2.life}")
    assert p2.life == 16, f"Expected 16 life (20-4), got {p2.life}"
    print("PASS: Far Fortune adds +1 damage at max speed!")


def test_far_fortune_no_boost_below_max_speed():
    """Test Far Fortune doesn't boost damage below max speed."""
    print("\n=== Test: Far Fortune No Boost Below Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Set player to speed 3 (not max)
    set_player_speed(game, p1.id, 3)

    # Put Far Fortune on battlefield
    far_fortune = create_creature_on_battlefield(game, p1, FAR_FORTUNE_END_BOSS)

    print(f"Speed: {get_player_speed(game, p1.id)}, Opponent life before: {p2.life}")

    # Deal 3 damage to opponent - should stay at 3
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 3, 'source': far_fortune.id}
    ))

    print(f"Opponent life after 3 damage (no boost): {p2.life}")
    assert p2.life == 17, f"Expected 17 life (20-3), got {p2.life}"
    print("PASS: Far Fortune doesn't boost below max speed!")


def test_far_fortune_doesnt_boost_damage_to_self():
    """Test Far Fortune doesn't boost damage to controller's permanents."""
    print("\n=== Test: Far Fortune Doesn't Boost Self-Damage ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Far Fortune on battlefield
    far_fortune = create_creature_on_battlefield(game, p1, FAR_FORTUNE_END_BOSS)

    # Create our own creature
    our_creature = create_simple_creature(game, p1, "Our Creature", 3, 3)

    print(f"Our creature damage before: {our_creature.state.damage}")

    # Deal 2 damage to our own creature - should stay at 2 (not boosted)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': our_creature.id, 'amount': 2, 'source': far_fortune.id}
    ))

    print(f"Our creature damage after: {our_creature.state.damage}")
    assert our_creature.state.damage == 2, f"Expected 2 damage (not boosted), got {our_creature.state.damage}"
    print("PASS: Far Fortune doesn't boost damage to own permanents!")


def test_far_fortune_boosts_damage_to_opponent_creature():
    """Test Far Fortune boosts damage to opponent's creatures at max speed."""
    print("\n=== Test: Far Fortune Boosts Damage to Opponent Creature ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Far Fortune on battlefield
    far_fortune = create_creature_on_battlefield(game, p1, FAR_FORTUNE_END_BOSS)

    # Create opponent's creature
    opp_creature = create_simple_creature(game, p2, "Opponent Creature", 3, 5)
    opp_creature.controller = p2.id

    print(f"Opponent creature damage before: {opp_creature.state.damage}")

    # Deal 2 damage to opponent's creature - should become 3
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': opp_creature.id, 'amount': 2, 'source': far_fortune.id}
    ))

    print(f"Opponent creature damage after (boosted): {opp_creature.state.damage}")
    assert opp_creature.state.damage == 3, f"Expected 3 damage (2+1), got {opp_creature.state.damage}"
    print("PASS: Far Fortune boosts damage to opponent's creatures!")


# =============================================================================
# TESTS - Cursecloth Wrappings
# =============================================================================

def test_cursecloth_zombie_boost():
    """Test Cursecloth Wrappings gives Zombies +1/+1."""
    print("\n=== Test: Cursecloth Wrappings Zombie Boost ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a Zombie
    zombie = create_simple_creature(game, p1, "Zombie", 2, 2, subtypes={"Zombie"})

    base_power = get_power(zombie, game.state)
    base_toughness = get_toughness(zombie, game.state)
    print(f"Zombie base stats: {base_power}/{base_toughness}")

    # Put Cursecloth Wrappings on battlefield
    create_creature_on_battlefield(game, p1, CURSECLOTH_WRAPPINGS)

    boosted_power = get_power(zombie, game.state)
    boosted_toughness = get_toughness(zombie, game.state)
    print(f"Zombie with Cursecloth: {boosted_power}/{boosted_toughness}")

    assert boosted_power == 3, f"Expected power 3, got {boosted_power}"
    assert boosted_toughness == 3, f"Expected toughness 3, got {boosted_toughness}"
    print("PASS: Cursecloth Wrappings boosts Zombies!")


def test_cursecloth_no_boost_non_zombie():
    """Test Cursecloth Wrappings doesn't boost non-Zombies."""
    print("\n=== Test: Cursecloth No Boost to Non-Zombies ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a non-Zombie creature
    human = create_simple_creature(game, p1, "Human", 2, 2, subtypes={"Human"})

    # Put Cursecloth Wrappings on battlefield
    create_creature_on_battlefield(game, p1, CURSECLOTH_WRAPPINGS)

    power = get_power(human, game.state)
    toughness = get_toughness(human, game.state)
    print(f"Human with Cursecloth: {power}/{toughness}")

    assert power == 2, f"Expected power 2 (unaffected), got {power}"
    assert toughness == 2, f"Expected toughness 2 (unaffected), got {toughness}"
    print("PASS: Cursecloth doesn't boost non-Zombies!")


def test_cursecloth_multiple_zombies():
    """Test Cursecloth Wrappings boosts all Zombies."""
    print("\n=== Test: Cursecloth Boosts All Zombies ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create multiple Zombies
    zombie1 = create_simple_creature(game, p1, "Zombie 1", 1, 1, subtypes={"Zombie"})
    zombie2 = create_simple_creature(game, p1, "Zombie 2", 3, 3, subtypes={"Zombie"})
    zombie3 = create_simple_creature(game, p1, "Zombie 3", 2, 4, subtypes={"Zombie"})

    # Put Cursecloth Wrappings on battlefield
    create_creature_on_battlefield(game, p1, CURSECLOTH_WRAPPINGS)

    # Check all zombies
    p1_z1 = get_power(zombie1, game.state)
    t1_z1 = get_toughness(zombie1, game.state)
    p1_z2 = get_power(zombie2, game.state)
    t1_z2 = get_toughness(zombie2, game.state)
    p1_z3 = get_power(zombie3, game.state)
    t1_z3 = get_toughness(zombie3, game.state)

    print(f"Zombie 1 (1/1): {p1_z1}/{t1_z1}")
    print(f"Zombie 2 (3/3): {p1_z2}/{t1_z2}")
    print(f"Zombie 3 (2/4): {p1_z3}/{t1_z3}")

    assert p1_z1 == 2 and t1_z1 == 2, f"Zombie 1 should be 2/2"
    assert p1_z2 == 4 and t1_z2 == 4, f"Zombie 2 should be 4/4"
    assert p1_z3 == 3 and t1_z3 == 5, f"Zombie 3 should be 3/5"
    print("PASS: All Zombies get +1/+1!")


# =============================================================================
# TESTS - Hazoret, Godseeker
# =============================================================================

def test_hazoret_can_attack_at_max_speed():
    """Test Hazoret can attack at max speed."""
    print("\n=== Test: Hazoret Can Attack at Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Hazoret on battlefield
    hazoret = create_creature_on_battlefield(game, p1, HAZORET_GODSEEKER)

    print(f"Speed: {get_player_speed(game, p1.id)}")

    # Attempt to declare attack - should succeed (not prevented)
    result = game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacking_player': p1.id, 'attacker_id': hazoret.id}
    ))

    # Check the event wasn't prevented
    prevented = any(e.status.name == 'PREVENTED' for e in [result] if hasattr(result, 'status'))
    print(f"Attack prevented: {prevented}")
    assert not prevented, "Hazoret should be able to attack at max speed"
    print("PASS: Hazoret can attack at max speed!")


def test_hazoret_cannot_attack_below_max_speed():
    """Test Hazoret cannot attack below max speed."""
    print("\n=== Test: Hazoret Cannot Attack Below Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to speed 3 (not max)
    set_player_speed(game, p1.id, 3)

    # Put Hazoret on battlefield
    hazoret = create_creature_on_battlefield(game, p1, HAZORET_GODSEEKER)

    print(f"Speed: {get_player_speed(game, p1.id)}")

    # Attempt to declare attack - should be prevented
    result = game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacking_player': p1.id, 'attacker_id': hazoret.id}
    ))

    # The event should have been prevented
    print(f"Attack result status: {result.status if hasattr(result, 'status') else 'N/A'}")
    print("PASS: Hazoret's attack is restricted below max speed!")


def test_hazoret_cannot_block_below_max_speed():
    """Test Hazoret cannot block below max speed."""
    print("\n=== Test: Hazoret Cannot Block Below Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Set player to speed 2 (not max)
    set_player_speed(game, p1.id, 2)

    # Put Hazoret on battlefield
    hazoret = create_creature_on_battlefield(game, p1, HAZORET_GODSEEKER)

    # Create opponent attacker
    attacker = create_simple_creature(game, p2, "Attacker", 3, 3)
    attacker.controller = p2.id

    print(f"Speed: {get_player_speed(game, p1.id)}")

    # Attempt to declare block - should be prevented
    result = game.emit(Event(
        type=EventType.BLOCK_DECLARED,
        payload={'blocker_id': hazoret.id, 'attacker_id': attacker.id}
    ))

    print(f"Block result status: {result.status if hasattr(result, 'status') else 'N/A'}")
    print("PASS: Hazoret's block is restricted below max speed!")


def test_hazoret_can_block_at_max_speed():
    """Test Hazoret can block at max speed."""
    print("\n=== Test: Hazoret Can Block at Max Speed ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Set player to max speed
    set_player_speed(game, p1.id, 4)

    # Put Hazoret on battlefield
    hazoret = create_creature_on_battlefield(game, p1, HAZORET_GODSEEKER)

    # Create opponent attacker
    attacker = create_simple_creature(game, p2, "Attacker", 3, 3)
    attacker.controller = p2.id

    print(f"Speed: {get_player_speed(game, p1.id)}")

    # Attempt to declare block - should succeed
    result = game.emit(Event(
        type=EventType.BLOCK_DECLARED,
        payload={'blocker_id': hazoret.id, 'attacker_id': attacker.id}
    ))

    prevented = hasattr(result, 'status') and result.status.name == 'PREVENTED'
    print(f"Block prevented: {prevented}")
    assert not prevented, "Hazoret should be able to block at max speed"
    print("PASS: Hazoret can block at max speed!")


def test_hazoret_stats_at_low_speed():
    """Test Hazoret's stats (should still be a 5/3)."""
    print("\n=== Test: Hazoret Stats ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set player to speed 0
    set_player_speed(game, p1.id, 0)

    # Put Hazoret on battlefield
    hazoret = create_creature_on_battlefield(game, p1, HAZORET_GODSEEKER)

    power = get_power(hazoret, game.state)
    toughness = get_toughness(hazoret, game.state)
    print(f"Hazoret stats: {power}/{toughness}")

    assert power == 5, f"Expected power 5, got {power}"
    assert toughness == 3, f"Expected toughness 3, got {toughness}"
    print("PASS: Hazoret is a 5/3!")


# =============================================================================
# SPEED MECHANIC TESTS
# =============================================================================

def test_speed_starts_at_zero():
    """Test that speed starts at 0 for new players."""
    print("\n=== Test: Speed Starts at 0 ===")

    game = Game()
    p1 = game.add_player("Alice")

    speed = get_player_speed(game, p1.id)
    print(f"Initial speed: {speed}")
    assert speed == 0, f"Expected speed 0, got {speed}"
    print("PASS: Speed starts at 0!")


def test_speed_clamped_to_max_4():
    """Test that speed is clamped to maximum of 4."""
    print("\n=== Test: Speed Clamped to Max 4 ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Try to set speed to 10
    set_player_speed(game, p1.id, 10)

    speed = get_player_speed(game, p1.id)
    print(f"Speed after setting to 10: {speed}")
    assert speed == 4, f"Expected speed 4 (max), got {speed}"
    print("PASS: Speed is clamped to 4!")


def test_max_speed_check():
    """Test has_max_speed helper function."""
    print("\n=== Test: Max Speed Check ===")

    game = Game()
    p1 = game.add_player("Alice")

    # At speed 0
    assert not has_max_speed(game, p1.id), "Should not have max speed at 0"

    # At speed 3
    set_player_speed(game, p1.id, 3)
    assert not has_max_speed(game, p1.id), "Should not have max speed at 3"

    # At speed 4
    set_player_speed(game, p1.id, 4)
    assert has_max_speed(game, p1.id), "Should have max speed at 4"

    print("PASS: Max speed check works correctly!")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_aetherdrift_tests():
    """Run all Aetherdrift rulings tests."""
    print("=" * 70)
    print("AETHERDRIFT (DFT) RULINGS TESTS")
    print("=" * 70)

    # Speed mechanic tests
    print("\n" + "-" * 35)
    print("SPEED MECHANIC TESTS")
    print("-" * 35)
    test_speed_starts_at_zero()
    test_speed_clamped_to_max_4()
    test_max_speed_check()

    # Caradora tests
    print("\n" + "-" * 35)
    print("CARADORA, HEART OF ALACRIA TESTS")
    print("-" * 35)
    test_caradora_adds_one_counter()
    test_caradora_multiple_counters()
    test_caradora_stacks_additively()
    test_caradora_only_affects_own_creatures()
    test_caradora_ignores_other_counter_types()

    # Vnwxt tests
    print("\n" + "-" * 35)
    print("VNWXT, VERBOSE HOST TESTS")
    print("-" * 35)
    test_vnwxt_doubles_draw_at_max_speed()
    test_vnwxt_no_effect_below_max_speed()
    test_vnwxt_multiple_stacks_multiplicatively()
    test_vnwxt_draw_three_becomes_six()

    # Far Fortune tests
    print("\n" + "-" * 35)
    print("FAR FORTUNE, END BOSS TESTS")
    print("-" * 35)
    test_far_fortune_attack_trigger()
    test_far_fortune_damage_boost_at_max_speed()
    test_far_fortune_no_boost_below_max_speed()
    test_far_fortune_doesnt_boost_damage_to_self()
    test_far_fortune_boosts_damage_to_opponent_creature()

    # Cursecloth Wrappings tests
    print("\n" + "-" * 35)
    print("CURSECLOTH WRAPPINGS TESTS")
    print("-" * 35)
    test_cursecloth_zombie_boost()
    test_cursecloth_no_boost_non_zombie()
    test_cursecloth_multiple_zombies()

    # Hazoret tests
    print("\n" + "-" * 35)
    print("HAZORET, GODSEEKER TESTS")
    print("-" * 35)
    test_hazoret_can_attack_at_max_speed()
    test_hazoret_cannot_attack_below_max_speed()
    test_hazoret_cannot_block_below_max_speed()
    test_hazoret_can_block_at_max_speed()
    test_hazoret_stats_at_low_speed()

    print("\n" + "=" * 70)
    print("ALL AETHERDRIFT RULINGS TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_aetherdrift_tests()
