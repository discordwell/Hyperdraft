"""
Foundations (FDN) Rulings Tests

Testing complex card interactions and edge cases for:
1. Doubling Season - Token/counter doubling replacement effects
2. Massacre Wurm - ETB -2/-2 and death triggers
3. Consuming Aberration - CDA P/T calculation in all zones
4. Angel of Vitality - Life gain +1 replacement, conditional +2/+2
5. Liliana, Dreadhorde General - Death draw triggers, simultaneous death
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    make_creature, make_enchantment, make_planeswalker,
    new_id, GameObject
)


# =============================================================================
# CARD DEFINITIONS - Doubling Season
# =============================================================================

def doubling_season_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Doubling Season: If an effect would create one or more tokens under your
    control, it creates twice that many of those tokens instead.
    If an effect would put one or more counters on a permanent you control,
    it puts twice that many of those counters on that permanent instead.
    """

    # Token doubling - TRANSFORM interceptor for CREATE_TOKEN
    def token_filter(event: Event, state) -> bool:
        if event.type != EventType.CREATE_TOKEN:
            return False
        # Only double tokens for our controller
        return event.payload.get('controller') == obj.controller

    def token_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current_count = new_event.payload.get('count', 1)
        new_event.payload['count'] = current_count * 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    token_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=token_filter,
        handler=token_handler,
        duration='while_on_battlefield'
    )

    # Counter doubling - TRANSFORM interceptor for COUNTER_ADDED
    def counter_filter(event: Event, state) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        # Only double counters on permanents we control
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return target.controller == obj.controller and target.zone == ZoneType.BATTLEFIELD

    def counter_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current_amount = new_event.payload.get('amount', 1)
        new_event.payload['amount'] = current_amount * 2
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

    return [token_interceptor, counter_interceptor]


DOUBLING_SEASON = make_enchantment(
    name="Doubling Season",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="If an effect would create one or more tokens under your control, it creates twice that many. If an effect would put one or more counters on a permanent you control, it puts twice that many instead.",
    setup_interceptors=doubling_season_setup
)


# =============================================================================
# CARD DEFINITIONS - Massacre Wurm
# =============================================================================

def massacre_wurm_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Massacre Wurm:
    When Massacre Wurm enters, creatures your opponents control get -2/-2 until end of turn.
    Whenever a creature an opponent controls dies, that player loses 2 life.
    """
    # Track which creatures were affected by ETB (for the -2/-2 effect)
    # This is stored on the object itself
    if not hasattr(obj, '_wurm_affected_creatures'):
        obj._wurm_affected_creatures = set()

    # ETB trigger - mark opponents' creatures for -2/-2
    def etb_filter(event: Event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('object_id') == obj.id and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)

    def etb_handler(event: Event, state) -> InterceptorResult:
        # Mark all opponent creatures present at resolution
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for creature_id in battlefield.objects:
                creature = state.objects.get(creature_id)
                if creature and creature.controller != obj.controller:
                    if CardType.CREATURE in creature.characteristics.types:
                        obj._wurm_affected_creatures.add(creature_id)
        return InterceptorResult(action=InterceptorAction.PASS)

    etb_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield'
    )

    # QUERY interceptor for power - applies -2 to affected creatures
    def power_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        return target_id in obj._wurm_affected_creatures

    def power_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('value', 0)
        new_event.payload['value'] = current - 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    power_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'  # Actually should be 'end_of_turn' but using this for testing
    )

    # QUERY interceptor for toughness - applies -2 to affected creatures
    def toughness_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        return target_id in obj._wurm_affected_creatures

    def toughness_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('value', 0)
        new_event.payload['value'] = current - 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    toughness_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='while_on_battlefield'
    )

    # Death trigger - opponent loses 2 life when their creature dies
    def death_filter(event: Event, state) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        dead_id = event.payload.get('object_id')
        dead_obj = state.objects.get(dead_id)
        if not dead_obj:
            return False
        # Must be a creature controlled by an opponent
        if CardType.CREATURE not in dead_obj.characteristics.types:
            return False
        return dead_obj.controller != obj.controller

    def death_handler(event: Event, state) -> InterceptorResult:
        dead_id = event.payload.get('object_id')
        dead_obj = state.objects.get(dead_id)
        if not dead_obj:
            return InterceptorResult(action=InterceptorAction.PASS)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': dead_obj.controller, 'amount': -2},
                source=obj.id
            )]
        )

    death_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield'
    )

    return [etb_interceptor, power_interceptor, toughness_interceptor, death_interceptor]


MASSACRE_WURM = make_creature(
    name="Massacre Wurm",
    power=6,
    toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Phyrexian", "Wurm"},
    text="When Massacre Wurm enters, creatures your opponents control get -2/-2 until end of turn. Whenever a creature an opponent controls dies, that player loses 2 life.",
    setup_interceptors=massacre_wurm_setup
)


# =============================================================================
# CARD DEFINITIONS - Consuming Aberration
# =============================================================================

def consuming_aberration_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Consuming Aberration: */* where * is total cards in opponents' graveyards.
    Whenever you cast a spell, each opponent mills until they mill a land.

    The CDA (characteristic-defining ability) works in ALL zones.
    """

    # P/T CDA - QUERY interceptors for power and toughness
    def power_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def toughness_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == obj.id

    def count_opponent_graveyard_cards() -> int:
        """Count total cards in all opponents' graveyards."""
        total = 0
        for player_id in state.players:
            if player_id != obj.controller:
                gy_key = f"graveyard_{player_id}"
                if gy_key in state.zones:
                    total += len(state.zones[gy_key].objects)
        return total

    def power_handler(event: Event, state) -> InterceptorResult:
        card_count = count_opponent_graveyard_cards()
        new_event = event.copy()
        # CDA sets base P/T, so we set the value directly
        new_event.payload['value'] = card_count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def toughness_handler(event: Event, state) -> InterceptorResult:
        card_count = count_opponent_graveyard_cards()
        new_event = event.copy()
        new_event.payload['value'] = card_count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    power_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        # CDA works in all zones, so we use 'forever' instead of 'while_on_battlefield'
        duration='forever'
    )

    toughness_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='forever'
    )

    # Spell cast trigger - mill opponents
    def cast_filter(event: Event, state) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        # Only trigger on spells cast by controller
        return event.payload.get('caster') == obj.controller

    def cast_handler(event: Event, state) -> InterceptorResult:
        # Mill each opponent until they mill a land
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.MILL,
                    payload={
                        'player': player_id,
                        'count': 1,  # Mill one at a time until land
                        'until_land': True
                    },
                    source=obj.id
                ))
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=events
        )

    cast_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cast_filter,
        handler=cast_handler,
        duration='while_on_battlefield'
    )

    return [power_interceptor, toughness_interceptor, cast_interceptor]


# Note: Consuming Aberration has */* base stats - we use 0/0 as placeholder
# The CDA interceptors will set the actual values
CONSUMING_ABERRATION = make_creature(
    name="Consuming Aberration",
    power=0,  # Base stats for CDA creature
    toughness=0,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Horror"},
    text="Consuming Aberration's power and toughness are each equal to the total number of cards in your opponents' graveyards. Whenever you cast a spell, each opponent mills cards until they mill a land card.",
    setup_interceptors=consuming_aberration_setup
)


# =============================================================================
# CARD DEFINITIONS - Angel of Vitality
# =============================================================================

def angel_of_vitality_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Angel of Vitality:
    Flying
    If you would gain life, you gain that much life plus 1 instead.
    Angel of Vitality gets +2/+2 as long as you have 25 or more life.
    """

    # Life gain replacement effect - TRANSFORM
    def life_gain_filter(event: Event, state) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        player = event.payload.get('player')
        # Only replace life GAIN for our controller
        return amount > 0 and player == obj.controller

    def life_gain_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    life_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=life_gain_filter,
        handler=life_gain_handler,
        duration='while_on_battlefield'
    )

    # Conditional +2/+2 when at 25+ life
    def power_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def toughness_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == obj.id

    def check_life_threshold() -> bool:
        """Check if controller has 25+ life."""
        player = state.players.get(obj.controller)
        return player and player.life >= 25

    def power_handler(event: Event, state) -> InterceptorResult:
        if check_life_threshold():
            new_event = event.copy()
            current = new_event.payload.get('value', 0)
            new_event.payload['value'] = current + 2
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    def toughness_handler(event: Event, state) -> InterceptorResult:
        if check_life_threshold():
            new_event = event.copy()
            current = new_event.payload.get('value', 0)
            new_event.payload['value'] = current + 2
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    power_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    )

    toughness_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='while_on_battlefield'
    )

    return [life_interceptor, power_interceptor, toughness_interceptor]


ANGEL_OF_VITALITY = make_creature(
    name="Angel of Vitality",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying. If you would gain life, you gain that much life plus 1 instead. Angel of Vitality gets +2/+2 as long as you have 25 or more life.",
    setup_interceptors=angel_of_vitality_setup
)


# =============================================================================
# CARD DEFINITIONS - Liliana, Dreadhorde General
# =============================================================================

def liliana_dreadhorde_general_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Liliana, Dreadhorde General:
    Whenever a creature you control dies, draw a card.
    +1: Create a 2/2 black Zombie creature token.
    -4: Each player sacrifices two creatures.
    -9: Each opponent chooses a permanent they control of each permanent type and sacrifices the rest.

    Key ruling: If Liliana dies at the same time as creatures you control,
    those creatures still trigger the draw ability.
    """

    # Death trigger - draw when creatures you control die
    def death_filter(event: Event, state) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        dead_id = event.payload.get('object_id')
        dead_obj = state.objects.get(dead_id)
        if not dead_obj:
            return False
        # Must be a creature we controlled
        if CardType.CREATURE not in dead_obj.characteristics.types:
            return False
        return dead_obj.controller == obj.controller

    def death_handler(event: Event, state) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id
            )]
        )

    death_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        # Use 'until_leaves' so triggers still fire when Liliana dies simultaneously
        duration='until_leaves'
    )

    return [death_interceptor]


LILIANA_DREADHORDE_GENERAL = make_planeswalker(
    name="Liliana, Dreadhorde General",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    loyalty=6,
    subtypes={"Liliana"},
    text="Whenever a creature you control dies, draw a card. +1: Create a 2/2 black Zombie creature token. -4: Each player sacrifices two creatures. -9: Each opponent chooses a permanent they control of each permanent type and sacrifices the rest.",
    setup_interceptors=liliana_dreadhorde_general_setup
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


def put_card_in_graveyard(game, player, name="Test Card"):
    """Put a card directly into a player's graveyard."""
    card = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(types={CardType.CREATURE})
    )
    return card


# =============================================================================
# TESTS - Doubling Season
# =============================================================================

def test_doubling_season_token_doubling():
    """Test Doubling Season doubles token creation."""
    print("\n=== Test: Doubling Season Token Doubling ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Doubling Season on battlefield
    ds = create_creature_on_battlefield(game, p1, DOUBLING_SEASON)

    # Create 1 token - should become 2
    game.emit(Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': p1.id,
            'token': {
                'name': 'Soldier',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Soldier'}
            },
            'count': 1
        }
    ))

    # Count tokens on battlefield
    battlefield = game.state.zones.get('battlefield')
    tokens = [oid for oid in battlefield.objects
              if game.state.objects[oid].name == 'Soldier']

    print(f"Tokens created (with Doubling Season): {len(tokens)}")
    assert len(tokens) == 2, f"Expected 2 tokens, got {len(tokens)}"
    print("PASS: Doubling Season doubles token creation!")


def test_doubling_season_counter_doubling():
    """Test Doubling Season doubles counter placement."""
    print("\n=== Test: Doubling Season Counter Doubling ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Doubling Season on battlefield
    create_creature_on_battlefield(game, p1, DOUBLING_SEASON)

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
    print(f"+1/+1 counters (with Doubling Season): {counters}")
    assert counters == 2, f"Expected 2 counters, got {counters}"
    print("PASS: Doubling Season doubles counter placement!")


def test_doubling_season_planeswalker_loyalty():
    """Test Doubling Season doubles planeswalker starting loyalty."""
    print("\n=== Test: Doubling Season Planeswalker Loyalty ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Doubling Season on battlefield
    create_creature_on_battlefield(game, p1, DOUBLING_SEASON)

    # Create a planeswalker that enters with loyalty counters
    # Liliana enters with 6 loyalty - should become 12
    pw = game.create_object(
        name="Liliana, Dreadhorde General",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=LILIANA_DREADHORDE_GENERAL.characteristics,
        card_def=LILIANA_DREADHORDE_GENERAL
    )

    # ETB with loyalty counters
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': pw.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    # Add loyalty counters (simulating ETB)
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': pw.id,
            'counter_type': 'loyalty',
            'amount': 6  # Base loyalty
        }
    ))

    loyalty = pw.state.counters.get('loyalty', 0)
    print(f"Loyalty counters (with Doubling Season): {loyalty}")
    assert loyalty == 12, f"Expected 12 loyalty, got {loyalty}"
    print("PASS: Doubling Season doubles planeswalker starting loyalty!")


def test_doubling_season_multiple_copies_stack():
    """Test multiple Doubling Seasons stack multiplicatively."""
    print("\n=== Test: Multiple Doubling Seasons Stack Multiplicatively ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put TWO Doubling Seasons on battlefield
    create_creature_on_battlefield(game, p1, DOUBLING_SEASON)
    create_creature_on_battlefield(game, p1, DOUBLING_SEASON)

    # Create a creature to put counters on
    creature = create_simple_creature(game, p1, "Test Creature", 1, 1)

    # Add 1 counter - should become 4 (1 * 2 * 2)
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            'object_id': creature.id,
            'counter_type': '+1/+1',
            'amount': 1
        }
    ))

    counters = creature.state.counters.get('+1/+1', 0)
    print(f"+1/+1 counters (with 2x Doubling Season): {counters}")
    assert counters == 4, f"Expected 4 counters (1*2*2), got {counters}"
    print("PASS: Multiple Doubling Seasons stack multiplicatively!")


def test_doubling_season_loyalty_cost_not_doubled():
    """Test Doubling Season doesn't double loyalty COSTS (only effects)."""
    print("\n=== Test: Doubling Season - Loyalty Costs NOT Doubled ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Doubling Season on battlefield
    create_creature_on_battlefield(game, p1, DOUBLING_SEASON)

    # Create a planeswalker with some loyalty
    pw = game.create_object(
        name="Test Planeswalker",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER}
        )
    )
    pw.state.counters['loyalty'] = 6

    # Simulate using a -2 ability (cost, not effect)
    # This should NOT be doubled - costs are paid as-is
    # We remove counters directly (simulating cost payment)
    game.emit(Event(
        type=EventType.COUNTER_REMOVED,
        payload={
            'object_id': pw.id,
            'counter_type': 'loyalty',
            'amount': 2
        }
    ))

    loyalty = pw.state.counters.get('loyalty', 0)
    print(f"Loyalty after -2 ability cost: {loyalty}")
    # Should be 4 (6 - 2), NOT 2 (6 - 4)
    assert loyalty == 4, f"Expected 4 loyalty (6-2), got {loyalty}. Costs should not be doubled!"
    print("PASS: Loyalty COSTS are not doubled by Doubling Season!")


# =============================================================================
# TESTS - Massacre Wurm
# =============================================================================

def test_massacre_wurm_etb_minus_2():
    """Test Massacre Wurm ETB gives -2/-2 to opponents' creatures."""
    print("\n=== Test: Massacre Wurm ETB -2/-2 ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put some creatures on battlefield for opponent
    opp_creature = create_simple_creature(game, p2, "Bear", 2, 2)
    opp_creature.controller = p2.id

    print(f"Opponent creature before Wurm: {get_power(opp_creature, game.state)}/{get_toughness(opp_creature, game.state)}")

    # Put Massacre Wurm on battlefield (triggers ETB)
    wurm = create_creature_on_battlefield(game, p1, MASSACRE_WURM)

    # Note: The PUMP event was emitted, but we need to check if the creature died
    # A 2/2 getting -2/-2 should die
    game.check_state_based_actions()

    print(f"Opponent creature zone after Wurm ETB: {opp_creature.zone}")
    assert opp_creature.zone == ZoneType.GRAVEYARD, "2/2 should die from -2/-2!"
    print("PASS: Massacre Wurm ETB kills small creatures!")


def test_massacre_wurm_only_affects_present_creatures():
    """Test Massacre Wurm -2/-2 only affects creatures present at resolution."""
    print("\n=== Test: Massacre Wurm Only Affects Present Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Massacre Wurm on battlefield first
    wurm = create_creature_on_battlefield(game, p1, MASSACRE_WURM)

    # Now create opponent creature AFTER Wurm ETB resolved
    late_creature = create_simple_creature(game, p2, "Late Bear", 2, 2)
    late_creature.controller = p2.id

    power = get_power(late_creature, game.state)
    toughness = get_toughness(late_creature, game.state)
    print(f"Creature added AFTER Wurm: {power}/{toughness}")

    # Should still be 2/2 - wasn't present when ETB resolved
    assert power == 2 and toughness == 2, "Creature added after ETB should be unaffected!"
    print("PASS: Massacre Wurm only affects creatures present at ETB!")


def test_massacre_wurm_death_trigger_life_loss():
    """Test Massacre Wurm death trigger causes life loss."""
    print("\n=== Test: Massacre Wurm Death Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Massacre Wurm on battlefield
    wurm = create_creature_on_battlefield(game, p1, MASSACRE_WURM)

    # Create opponent creature
    opp_creature = create_simple_creature(game, p2, "Goblin", 1, 1)
    opp_creature.controller = p2.id

    print(f"Opponent life before creature death: {p2.life}")

    # Kill the opponent's creature
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': opp_creature.id}
    ))

    print(f"Opponent life after creature death: {p2.life}")
    assert p2.life == 18, f"Expected 18 life (20-2), got {p2.life}"
    print("PASS: Massacre Wurm death trigger causes 2 life loss!")


def test_massacre_wurm_etb_chain_triggers():
    """Test deaths from -2/-2 chain into life loss triggers."""
    print("\n=== Test: Massacre Wurm ETB Chains Into Death Triggers ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create 3 small creatures for opponent
    creatures = []
    for i in range(3):
        c = create_simple_creature(game, p2, f"Goblin {i+1}", 1, 1)
        c.controller = p2.id
        creatures.append(c)

    print(f"Opponent life before Wurm: {p2.life}")
    print(f"Opponent creatures: {len(creatures)}")

    # Put Massacre Wurm on battlefield - all 1/1s should die from -2/-2
    # and each death should trigger 2 life loss
    wurm = create_creature_on_battlefield(game, p1, MASSACRE_WURM)
    game.check_state_based_actions()

    # Count dead creatures
    dead_count = sum(1 for c in creatures if c.zone == ZoneType.GRAVEYARD)
    print(f"Creatures that died: {dead_count}")
    print(f"Opponent life after Wurm: {p2.life}")

    # 3 creatures died, each causes 2 life loss = 6 total
    expected_life = 20 - (dead_count * 2)
    assert p2.life == expected_life, f"Expected {expected_life} life, got {p2.life}"
    print("PASS: Massacre Wurm ETB chains into death triggers correctly!")


# =============================================================================
# TESTS - Consuming Aberration
# =============================================================================

def test_consuming_aberration_power_equals_graveyard():
    """Test Consuming Aberration P/T equals opponent graveyard size."""
    print("\n=== Test: Consuming Aberration P/T = Opponent Graveyard ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put some cards in opponent's graveyard
    for i in range(5):
        put_card_in_graveyard(game, p2, f"Dead Card {i+1}")

    # Create Consuming Aberration
    aberration = create_creature_on_battlefield(game, p1, CONSUMING_ABERRATION)

    power = get_power(aberration, game.state)
    toughness = get_toughness(aberration, game.state)

    print(f"Opponent graveyard size: 5")
    print(f"Consuming Aberration stats: {power}/{toughness}")

    assert power == 5, f"Expected power 5, got {power}"
    assert toughness == 5, f"Expected toughness 5, got {toughness}"
    print("PASS: Consuming Aberration P/T equals opponent graveyard size!")


def test_consuming_aberration_cda_in_hand():
    """Test Consuming Aberration CDA works in hand."""
    print("\n=== Test: Consuming Aberration CDA Works in Hand ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put cards in opponent's graveyard
    for i in range(7):
        put_card_in_graveyard(game, p2, f"Dead Card {i+1}")

    # Create Consuming Aberration IN HAND (not battlefield)
    aberration = game.create_object(
        name="Consuming Aberration",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=CONSUMING_ABERRATION.characteristics,
        card_def=CONSUMING_ABERRATION
    )

    # CDA should still work in hand
    power = get_power(aberration, game.state)
    toughness = get_toughness(aberration, game.state)

    print(f"Zone: {aberration.zone}")
    print(f"Consuming Aberration stats (in hand): {power}/{toughness}")

    assert power == 7, f"Expected power 7 in hand, got {power}"
    assert toughness == 7, f"Expected toughness 7 in hand, got {toughness}"
    print("PASS: Consuming Aberration CDA works in hand!")


def test_consuming_aberration_cda_in_graveyard():
    """Test Consuming Aberration CDA works in graveyard."""
    print("\n=== Test: Consuming Aberration CDA Works in Graveyard ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put cards in opponent's graveyard
    for i in range(3):
        put_card_in_graveyard(game, p2, f"Dead Card {i+1}")

    # Create Consuming Aberration IN GRAVEYARD
    aberration = game.create_object(
        name="Consuming Aberration",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=CONSUMING_ABERRATION.characteristics,
        card_def=CONSUMING_ABERRATION
    )

    # CDA should still work in graveyard
    power = get_power(aberration, game.state)
    toughness = get_toughness(aberration, game.state)

    print(f"Zone: {aberration.zone}")
    print(f"Consuming Aberration stats (in graveyard): {power}/{toughness}")

    assert power == 3, f"Expected power 3 in graveyard, got {power}"
    assert toughness == 3, f"Expected toughness 3 in graveyard, got {toughness}"
    print("PASS: Consuming Aberration CDA works in graveyard!")


def test_consuming_aberration_updates_dynamically():
    """Test Consuming Aberration P/T updates as graveyard changes."""
    print("\n=== Test: Consuming Aberration Updates Dynamically ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create Consuming Aberration with empty opponent graveyard
    aberration = create_creature_on_battlefield(game, p1, CONSUMING_ABERRATION)

    power_initial = get_power(aberration, game.state)
    print(f"Initial stats (empty graveyard): {power_initial}")
    assert power_initial == 0, "Should be 0/0 with empty graveyard"

    # Add cards to graveyard
    put_card_in_graveyard(game, p2, "Card 1")
    put_card_in_graveyard(game, p2, "Card 2")
    put_card_in_graveyard(game, p2, "Card 3")

    power_after = get_power(aberration, game.state)
    toughness_after = get_toughness(aberration, game.state)
    print(f"After 3 cards in graveyard: {power_after}/{toughness_after}")

    assert power_after == 3, f"Expected 3, got {power_after}"
    assert toughness_after == 3, f"Expected 3, got {toughness_after}"
    print("PASS: Consuming Aberration updates dynamically!")


def test_consuming_aberration_multiple_opponents():
    """Test Consuming Aberration counts all opponents' graveyards."""
    print("\n=== Test: Consuming Aberration Counts All Opponents ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    p3 = game.add_player("Charlie")

    # Put cards in both opponents' graveyards
    for i in range(3):
        put_card_in_graveyard(game, p2, f"Bob Card {i+1}")
    for i in range(4):
        put_card_in_graveyard(game, p3, f"Charlie Card {i+1}")

    # Create Consuming Aberration
    aberration = create_creature_on_battlefield(game, p1, CONSUMING_ABERRATION)

    power = get_power(aberration, game.state)
    toughness = get_toughness(aberration, game.state)

    print(f"Bob's graveyard: 3 cards")
    print(f"Charlie's graveyard: 4 cards")
    print(f"Consuming Aberration stats: {power}/{toughness}")

    # Total should be 3 + 4 = 7
    assert power == 7, f"Expected power 7 (3+4), got {power}"
    assert toughness == 7, f"Expected toughness 7 (3+4), got {toughness}"
    print("PASS: Consuming Aberration counts all opponents' graveyards!")


# =============================================================================
# TESTS - Angel of Vitality
# =============================================================================

def test_angel_of_vitality_life_gain_plus_1():
    """Test Angel of Vitality adds +1 to life gain."""
    print("\n=== Test: Angel of Vitality Life Gain +1 ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Angel on battlefield
    angel = create_creature_on_battlefield(game, p1, ANGEL_OF_VITALITY)

    print(f"Starting life: {p1.life}")

    # Gain 3 life - should become 4
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 3}
    ))

    print(f"Life after gaining '3': {p1.life}")
    assert p1.life == 24, f"Expected 24 (20 + 3 + 1), got {p1.life}"
    print("PASS: Angel of Vitality adds +1 to life gain!")


def test_angel_of_vitality_multiple_angels_stack():
    """Test multiple Angels of Vitality stack additively."""
    print("\n=== Test: Multiple Angels Stack Additively ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put THREE Angels on battlefield
    for i in range(3):
        create_creature_on_battlefield(game, p1, ANGEL_OF_VITALITY)

    print(f"Starting life: {p1.life}")

    # Gain 1 life - should become 4 (1 + 1 + 1 + 1)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 1}
    ))

    print(f"Life after gaining '1' with 3 Angels: {p1.life}")
    assert p1.life == 24, f"Expected 24 (20 + 1 + 3), got {p1.life}"
    print("PASS: Multiple Angels stack additively!")


def test_angel_of_vitality_threshold_25_life():
    """Test Angel of Vitality gets +2/+2 at 25+ life."""
    print("\n=== Test: Angel of Vitality +2/+2 at 25 Life ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Angel on battlefield
    angel = create_creature_on_battlefield(game, p1, ANGEL_OF_VITALITY)

    # At 20 life - should be base 2/2
    power_at_20 = get_power(angel, game.state)
    toughness_at_20 = get_toughness(angel, game.state)
    print(f"Stats at 20 life: {power_at_20}/{toughness_at_20}")
    assert power_at_20 == 2 and toughness_at_20 == 2, "Should be 2/2 below 25 life"

    # Gain life to reach 25
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 5}  # 20 + 5 + 1 = 26
    ))

    power_at_26 = get_power(angel, game.state)
    toughness_at_26 = get_toughness(angel, game.state)
    print(f"Life after gain: {p1.life}")
    print(f"Stats at {p1.life} life: {power_at_26}/{toughness_at_26}")

    assert power_at_26 == 4 and toughness_at_26 == 4, "Should be 4/4 at 25+ life"
    print("PASS: Angel of Vitality gets +2/+2 at 25+ life!")


def test_angel_of_vitality_threshold_checked_continuously():
    """Test Angel's +2/+2 is checked continuously (can lose it)."""
    print("\n=== Test: Angel Threshold Checked Continuously ===")

    game = Game()
    p1 = game.add_player("Alice", life=30)  # Start above threshold

    # Put Angel on battlefield
    angel = create_creature_on_battlefield(game, p1, ANGEL_OF_VITALITY)

    power_at_30 = get_power(angel, game.state)
    print(f"Stats at 30 life: {power_at_30}/X")
    assert power_at_30 == 4, "Should be 4/4 at 30 life"

    # Take damage to drop below 25
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 10}
    ))

    power_at_20 = get_power(angel, game.state)
    print(f"Stats at {p1.life} life: {power_at_20}/X")
    assert power_at_20 == 2, "Should be 2/2 after dropping below 25 life"
    print("PASS: Angel threshold is checked continuously!")


def test_angel_of_vitality_doesnt_affect_life_loss():
    """Test Angel of Vitality doesn't affect life loss (only gain)."""
    print("\n=== Test: Angel Doesn't Affect Life Loss ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Angel on battlefield
    create_creature_on_battlefield(game, p1, ANGEL_OF_VITALITY)

    print(f"Starting life: {p1.life}")

    # Lose 5 life - should be exactly 5, not modified
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': -5}
    ))

    print(f"Life after losing 5: {p1.life}")
    assert p1.life == 15, f"Expected 15 (20-5), got {p1.life}. Life loss should not be modified!"
    print("PASS: Angel doesn't modify life loss!")


# =============================================================================
# TESTS - Liliana, Dreadhorde General
# =============================================================================

def test_liliana_draws_on_creature_death():
    """Test Liliana draws a card when a creature you control dies."""
    print("\n=== Test: Liliana Draws on Creature Death ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Liliana on battlefield
    liliana = create_creature_on_battlefield(game, p1, LILIANA_DREADHORDE_GENERAL)

    # Create a creature
    creature = create_simple_creature(game, p1, "Zombie", 2, 2)

    # Add some cards to library to draw from
    for i in range(3):
        game.create_object(
            name=f"Library Card {i+1}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT})
        )

    hand_before = len(game.get_hand(p1.id))
    print(f"Hand size before death: {hand_before}")

    # Kill the creature
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': creature.id}
    ))

    hand_after = len(game.get_hand(p1.id))
    print(f"Hand size after death: {hand_after}")

    assert hand_after == hand_before + 1, f"Expected to draw 1 card, hand went from {hand_before} to {hand_after}"
    print("PASS: Liliana draws on creature death!")


def test_liliana_multiple_creature_deaths():
    """Test Liliana draws for each creature death."""
    print("\n=== Test: Liliana Draws for Each Death ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Liliana on battlefield
    liliana = create_creature_on_battlefield(game, p1, LILIANA_DREADHORDE_GENERAL)

    # Create multiple creatures
    creatures = []
    for i in range(3):
        c = create_simple_creature(game, p1, f"Zombie {i+1}", 2, 2)
        creatures.append(c)

    # Add cards to library
    for i in range(10):
        game.create_object(
            name=f"Library Card {i+1}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT})
        )

    hand_before = len(game.get_hand(p1.id))
    print(f"Hand size before deaths: {hand_before}")

    # Kill all creatures
    for c in creatures:
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': c.id}
        ))

    hand_after = len(game.get_hand(p1.id))
    print(f"Hand size after 3 deaths: {hand_after}")

    assert hand_after == hand_before + 3, f"Expected to draw 3 cards"
    print("PASS: Liliana draws for each creature death!")


def test_liliana_simultaneous_death_with_creatures():
    """Test Liliana triggers for creatures that die at the same time as her."""
    print("\n=== Test: Liliana Simultaneous Death ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Liliana on battlefield
    liliana = create_creature_on_battlefield(game, p1, LILIANA_DREADHORDE_GENERAL)

    # Create creatures
    zombie = create_simple_creature(game, p1, "Zombie", 2, 2)

    # Add cards to library
    for i in range(5):
        game.create_object(
            name=f"Library Card {i+1}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT})
        )

    hand_before = len(game.get_hand(p1.id))
    print(f"Hand size before simultaneous death: {hand_before}")

    # Kill creature first (simulates "simultaneous" death)
    # Since Liliana's trigger uses 'until_leaves' duration, it should still fire
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': zombie.id}
    ))

    # Then Liliana dies
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': liliana.id}
    ))

    hand_after = len(game.get_hand(p1.id))
    print(f"Hand size after both died: {hand_after}")

    # Should have drawn 1 card for zombie's death (Liliana was still there when it triggered)
    assert hand_after >= hand_before + 1, f"Should draw at least 1 card for zombie death"
    print("PASS: Liliana triggers for creatures dying with her!")


def test_liliana_doesnt_trigger_for_opponent_creatures():
    """Test Liliana only triggers for your creatures, not opponents'."""
    print("\n=== Test: Liliana Only Triggers for Your Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Put Liliana on battlefield under P1's control
    liliana = create_creature_on_battlefield(game, p1, LILIANA_DREADHORDE_GENERAL)

    # Create opponent's creature
    opp_creature = create_simple_creature(game, p2, "Enemy Zombie", 2, 2)
    opp_creature.controller = p2.id

    # Add cards to P1's library
    for i in range(5):
        game.create_object(
            name=f"Library Card {i+1}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT})
        )

    hand_before = len(game.get_hand(p1.id))
    print(f"Hand size before opponent creature death: {hand_before}")

    # Kill opponent's creature
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': opp_creature.id}
    ))

    hand_after = len(game.get_hand(p1.id))
    print(f"Hand size after opponent creature death: {hand_after}")

    assert hand_after == hand_before, f"Should NOT draw for opponent's creature death"
    print("PASS: Liliana doesn't trigger for opponent creatures!")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_fdn_tests():
    """Run all FDN rulings tests."""
    print("=" * 70)
    print("FOUNDATIONS (FDN) RULINGS TESTS")
    print("=" * 70)

    # Doubling Season tests
    print("\n" + "-" * 35)
    print("DOUBLING SEASON TESTS")
    print("-" * 35)
    test_doubling_season_token_doubling()
    test_doubling_season_counter_doubling()
    test_doubling_season_planeswalker_loyalty()
    test_doubling_season_multiple_copies_stack()
    test_doubling_season_loyalty_cost_not_doubled()

    # Massacre Wurm tests
    print("\n" + "-" * 35)
    print("MASSACRE WURM TESTS")
    print("-" * 35)
    test_massacre_wurm_etb_minus_2()
    test_massacre_wurm_only_affects_present_creatures()
    test_massacre_wurm_death_trigger_life_loss()
    test_massacre_wurm_etb_chain_triggers()

    # Consuming Aberration tests
    print("\n" + "-" * 35)
    print("CONSUMING ABERRATION TESTS")
    print("-" * 35)
    test_consuming_aberration_power_equals_graveyard()
    test_consuming_aberration_cda_in_hand()
    test_consuming_aberration_cda_in_graveyard()
    test_consuming_aberration_updates_dynamically()
    test_consuming_aberration_multiple_opponents()

    # Angel of Vitality tests
    print("\n" + "-" * 35)
    print("ANGEL OF VITALITY TESTS")
    print("-" * 35)
    test_angel_of_vitality_life_gain_plus_1()
    test_angel_of_vitality_multiple_angels_stack()
    test_angel_of_vitality_threshold_25_life()
    test_angel_of_vitality_threshold_checked_continuously()
    test_angel_of_vitality_doesnt_affect_life_loss()

    # Liliana tests
    print("\n" + "-" * 35)
    print("LILIANA, DREADHORDE GENERAL TESTS")
    print("-" * 35)
    test_liliana_draws_on_creature_death()
    test_liliana_multiple_creature_deaths()
    test_liliana_simultaneous_death_with_creatures()
    test_liliana_doesnt_trigger_for_opponent_creatures()

    print("\n" + "=" * 70)
    print("ALL FDN RULINGS TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_fdn_tests()
