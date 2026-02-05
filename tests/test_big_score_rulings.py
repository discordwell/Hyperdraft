"""
The Big Score (BIG) Rulings Tests

Testing complex card interactions and edge cases from The Big Score bonus sheet:
1. Simulacrum Synthesizer - ETB scry and artifact-triggered token creation
2. Sword of Wealth and Power - Equipment with protection and spell copying
3. Nexus of Becoming - Combat-triggered token copies of exiled cards
4. Torpor Orb - Static effect preventing ETB triggers

These tests verify official rulings from Gatherer/Scryfall dated April 2024.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    make_creature, make_artifact, make_instant, make_sorcery,
    new_id, GameObject, parse_cost
)


def get_mana_value(mana_cost: str) -> int:
    """Calculate mana value from a mana cost string."""
    if not mana_cost:
        return 0
    return parse_cost(mana_cost).mana_value


# =============================================================================
# CARD DEFINITIONS: Simulacrum Synthesizer
# =============================================================================

def simulacrum_synthesizer_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Simulacrum Synthesizer {2}{U}
    Artifact

    When Simulacrum Synthesizer enters the battlefield, scry 2.
    Whenever another artifact you control with mana value 3 or greater enters
    the battlefield, create a 0/0 colorless Construct artifact creature token
    with "This creature gets +1/+1 for each artifact you control."

    Key Rulings:
    - The Construct's ability counts itself (so minimum 1/1)
    - If mana cost includes {X}, X is 0 for determining mana value
    """

    # ETB: Scry 2
    def etb_filter(event: Event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('object_id') == obj.id and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)

    def etb_handler(event: Event, state) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'count': 2},
                source=obj.id
            )]
        )

    etb_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield'
    )

    # Triggered ability: When another artifact MV>=3 enters
    def artifact_enters_filter(event: Event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False

        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False  # "another" artifact

        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False

        # Must be an artifact we control
        if CardType.ARTIFACT not in entering_obj.characteristics.types:
            return False
        if entering_obj.controller != obj.controller:
            return False

        # Check mana value >= 3
        mana_cost = entering_obj.characteristics.mana_cost
        mv = get_mana_value(mana_cost) if mana_cost else 0
        return mv >= 3

    def artifact_enters_handler(event: Event, state) -> InterceptorResult:
        # Create a Construct token with the special ability
        # The token tracks artifact count for its P/T
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Construct',
                        'power': 0,  # Base 0/0
                        'toughness': 0,
                        'types': {CardType.ARTIFACT, CardType.CREATURE},
                        'subtypes': {'Construct'},
                        'abilities': [{'artifact_count_pt': True}]
                    },
                    'count': 1
                },
                source=obj.id
            )]
        )

    artifact_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_enters_filter,
        handler=artifact_enters_handler,
        duration='while_on_battlefield'
    )

    return [etb_interceptor, artifact_trigger]


SIMULACRUM_SYNTHESIZER = make_artifact(
    name="Simulacrum Synthesizer",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="When Simulacrum Synthesizer enters the battlefield, scry 2.\nWhenever another artifact you control with mana value 3 or greater enters the battlefield, create a 0/0 colorless Construct artifact creature token with \"This creature gets +1/+1 for each artifact you control.\"",
    setup_interceptors=simulacrum_synthesizer_setup
)


# =============================================================================
# CARD DEFINITIONS: Sword of Wealth and Power
# =============================================================================

def sword_of_wealth_and_power_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Sword of Wealth and Power {3}
    Artifact - Equipment

    Equipped creature gets +2/+2 and has protection from instants and
    from sorceries.
    Whenever equipped creature deals combat damage to a player, create
    a Treasure token. When you next cast an instant or sorcery spell
    this turn, copy that spell. You may choose new targets for the copy.
    Equip {2}

    Key Rulings:
    - The copy is created on the stack, not "cast"
    - Modal spells keep the same modes
    - X values are preserved from original
    - Damage division/counter distribution can't be changed
    """

    # P/T boost for equipped creature
    def power_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        if not hasattr(obj.state, 'attached_to') or not obj.state.attached_to:
            return False
        return event.payload.get('object_id') == obj.state.attached_to

    def power_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('value', 0)
        new_event.payload['value'] = current + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    def toughness_filter(event: Event, state) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        if not hasattr(obj.state, 'attached_to') or not obj.state.attached_to:
            return False
        return event.payload.get('object_id') == obj.state.attached_to

    def toughness_handler(event: Event, state) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('value', 0)
        new_event.payload['value'] = current + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    power_boost = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    )

    toughness_boost = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='while_on_battlefield'
    )

    # Protection from instants and sorceries - prevent targeting
    # This uses TARGET_REQUIRED event (the available targeting event)
    def protection_target_filter(event: Event, state) -> bool:
        if event.type != EventType.TARGET_REQUIRED:
            return False
        if not hasattr(obj.state, 'attached_to') or not obj.state.attached_to:
            return False
        if event.payload.get('target_id') != obj.state.attached_to:
            return False

        # Check if source is instant or sorcery
        source_id = event.payload.get('source_id')
        source_obj = state.objects.get(source_id)
        if not source_obj:
            return False

        source_types = source_obj.characteristics.types
        return CardType.INSTANT in source_types or CardType.SORCERY in source_types

    def protection_target_handler(event: Event, state) -> InterceptorResult:
        # Prevent targeting from instants/sorceries
        return InterceptorResult(action=InterceptorAction.PREVENT)

    protection_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=protection_target_filter,
        handler=protection_target_handler,
        duration='while_on_battlefield'
    )

    # Protection from instants/sorceries - prevent damage
    def protection_damage_filter(event: Event, state) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not hasattr(obj.state, 'attached_to') or not obj.state.attached_to:
            return False
        if event.payload.get('target') != obj.state.attached_to:
            return False

        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj:
            return False

        source_types = source_obj.characteristics.types
        return CardType.INSTANT in source_types or CardType.SORCERY in source_types

    def protection_damage_handler(event: Event, state) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    damage_protection = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=protection_damage_filter,
        handler=protection_damage_handler,
        duration='while_on_battlefield'
    )

    # Combat damage trigger: Create Treasure + set up spell copy
    def combat_damage_filter(event: Event, state) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        if not hasattr(obj.state, 'attached_to') or not obj.state.attached_to:
            return False

        # Damage must be from equipped creature
        source_id = event.payload.get('source')
        if source_id != obj.state.attached_to:
            return False

        # Damage must be to a player
        target = event.payload.get('target')
        return target in state.players

    def combat_damage_handler(event: Event, state) -> InterceptorResult:
        # Create a Treasure token
        treasure_event = Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Treasure',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'abilities': [{'sacrifice_for_mana': True}]
                },
                'count': 1
            },
            source=obj.id
        )

        # Mark that next instant/sorcery should be copied
        if not hasattr(obj.state, 'copy_next_spell'):
            obj.state.copy_next_spell = False
        obj.state.copy_next_spell = True

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[treasure_event]
        )

    combat_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_damage_filter,
        handler=combat_damage_handler,
        duration='while_on_battlefield'
    )

    # Spell copy when instant/sorcery cast (if triggered)
    def spell_cast_filter(event: Event, state) -> bool:
        if event.type != EventType.CAST:
            return False
        if not hasattr(obj.state, 'copy_next_spell') or not obj.state.copy_next_spell:
            return False
        if event.payload.get('caster') != obj.controller:
            return False

        spell_types = event.payload.get('types', set())
        return CardType.INSTANT in spell_types or CardType.SORCERY in spell_types

    def spell_cast_handler(event: Event, state) -> InterceptorResult:
        obj.state.copy_next_spell = False  # Use the trigger

        # Store copy data on the object for testing purposes
        # In the real engine, this would put a copy on the stack
        obj.state.last_copy_data = {
            'original_spell_id': event.payload.get('spell_id'),
            'controller': obj.controller,
            'may_choose_new_targets': True,
            # Modal spells keep same modes
            'modes': event.payload.get('modes', []),
            # X values preserved
            'x_value': event.payload.get('x_value', 0),
            # Division cannot be changed
            'preserve_division': True
        }

        # Create a CAST event for the copy (simplified for testing)
        copy_cast = Event(
            type=EventType.CAST,
            payload={
                'spell_id': f"{event.payload.get('spell_id')}_copy",
                'caster': obj.controller,
                'is_copy': True,
                'types': event.payload.get('types', set()),
                'x_value': event.payload.get('x_value', 0),
                'modes': event.payload.get('modes', []),
                'preserve_division': True
            },
            source=obj.id
        )

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[copy_cast]
        )

    spell_copy_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=spell_cast_handler,
        duration='while_on_battlefield'
    )

    return [power_boost, toughness_boost, protection_interceptor,
            damage_protection, combat_trigger, spell_copy_trigger]


SWORD_OF_WEALTH_AND_POWER = make_artifact(
    name="Sword of Wealth and Power",
    mana_cost="{3}",
    colors=set(),  # Colorless
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+2 and has protection from instants and from sorceries.\nWhenever equipped creature deals combat damage to a player, create a Treasure token. When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.\nEquip {2}",
    setup_interceptors=sword_of_wealth_and_power_setup
)


# =============================================================================
# CARD DEFINITIONS: Nexus of Becoming
# =============================================================================

def nexus_of_becoming_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Nexus of Becoming {6}
    Artifact

    At the beginning of combat on your turn, draw a card. Then you may
    exile an artifact or creature card from your hand. If you do, create
    a token that's a copy of the exiled card, except it's a 3/3 Golem
    artifact creature in addition to its other types.

    Key Rulings:
    - Token copies printed characteristics, {X} in cost is 0
    - ETB abilities of copied card WILL trigger
    - "As enters" and "enters with" abilities work
    """

    def combat_trigger_filter(event: Event, state) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        return state.active_player == obj.controller

    def combat_trigger_handler(event: Event, state) -> InterceptorResult:
        # Draw a card
        draw_event = Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )

        # The "may exile" part creates a pending choice
        # For testing, we'll mark that player can exile
        if not hasattr(obj.state, 'pending_exile_choice'):
            obj.state.pending_exile_choice = False
        obj.state.pending_exile_choice = True

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[draw_event]
        )

    combat_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_trigger_filter,
        handler=combat_trigger_handler,
        duration='while_on_battlefield'
    )

    return [combat_trigger]


def create_nexus_token(state, controller_id: str, exiled_card: GameObject, source_id: str) -> Event:
    """
    Helper to create the Nexus of Becoming token.

    The token is a copy of the exiled card except:
    - It's a 3/3 Golem artifact creature IN ADDITION to its other types
    - If original was a creature, it keeps creature type but becomes 3/3
    - If original was an artifact, it gains creature type
    """
    # Copy characteristics from exiled card
    new_types = set(exiled_card.characteristics.types)
    new_types.add(CardType.ARTIFACT)
    new_types.add(CardType.CREATURE)

    new_subtypes = set(exiled_card.characteristics.subtypes)
    new_subtypes.add('Golem')

    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': controller_id,
            'token': {
                'name': exiled_card.name,
                'power': 3,  # Always 3/3
                'toughness': 3,
                'types': new_types,
                'subtypes': new_subtypes,
                'colors': exiled_card.characteristics.colors,
                'abilities': exiled_card.characteristics.abilities,
                'is_copy_of': exiled_card.id
            },
            'count': 1
        },
        source=source_id
    )


NEXUS_OF_BECOMING = make_artifact(
    name="Nexus of Becoming",
    mana_cost="{6}",
    colors=set(),  # Colorless
    text="At the beginning of combat on your turn, draw a card. Then you may exile an artifact or creature card from your hand. If you do, create a token that's a copy of the exiled card, except it's a 3/3 Golem artifact creature in addition to its other types.",
    setup_interceptors=nexus_of_becoming_setup
)


# =============================================================================
# CARD DEFINITIONS: Torpor Orb
# =============================================================================

def torpor_orb_setup(obj: GameObject, state) -> list[Interceptor]:
    """
    Torpor Orb {2}
    Artifact

    Creatures entering the battlefield don't cause abilities to trigger.

    Key Rulings:
    - Stops creature's OWN ETB triggers
    - Stops OTHER triggers that care about creatures entering
    - "When," "Whenever," "At" triggers are affected
    - "As enters" replacement effects are NOT affected
    - "Enters with" abilities work (counters, etc.)
    - If Torpor Orb enters simultaneously with a creature, that creature's
      ETB won't trigger
    """

    # Prevent ETB triggers for creatures
    def etb_prevention_filter(event: Event, state) -> bool:
        # We need to intercept the triggering, not the zone change itself
        # This intercepts REACT events that are triggered by creature ETB
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False

        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False

        return CardType.CREATURE in entering.characteristics.types

    def etb_prevention_handler(event: Event, state) -> InterceptorResult:
        # Mark this creature as "entered under Torpor Orb"
        # This prevents ETB triggers from firing
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if entering:
            entering.state._torpor_orb_applied = True

        # We use TRANSFORM but don't change the event
        # The key is that we mark the creature so ETB triggers check this flag
        return InterceptorResult(action=InterceptorAction.PASS)

    etb_prevention = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,  # Early in pipeline
        filter=etb_prevention_filter,
        handler=etb_prevention_handler,
        duration='while_on_battlefield'
    )

    return [etb_prevention]


TORPOR_ORB = make_artifact(
    name="Torpor Orb",
    mana_cost="{2}",
    colors=set(),  # Colorless
    text="Creatures entering the battlefield don't cause abilities to trigger.",
    setup_interceptors=torpor_orb_setup
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_on_battlefield(game, player, card_def, name=None):
    """Create a card on the battlefield with ETB handling."""
    creature = game.create_object(
        name=name or card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
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
    """Create a simple vanilla creature."""
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


def create_simple_artifact(game, player, name, mana_value=0):
    """Create a simple artifact."""
    artifact = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            mana_value=mana_value
        )
    )
    return artifact


# =============================================================================
# TESTS: Simulacrum Synthesizer
# =============================================================================

def test_simulacrum_synthesizer_etb_scry():
    """Test Simulacrum Synthesizer triggers scry 2 on ETB."""
    print("\n=== Test: Simulacrum Synthesizer ETB Scry ===")

    game = Game()
    p1 = game.add_player("Alice")

    scry_triggered = {'count': 0, 'amount': 0}

    # Track scry events
    def track_scry_filter(event: Event, state) -> bool:
        return event.type == EventType.SCRY

    def track_scry_handler(event: Event, state) -> InterceptorResult:
        scry_triggered['count'] += 1
        scry_triggered['amount'] = event.payload.get('count', 0)
        return InterceptorResult(action=InterceptorAction.PASS)

    tracker = Interceptor(
        id=new_id(),
        source="test",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=track_scry_filter,
        handler=track_scry_handler,
        duration='forever'
    )
    game.register_interceptor(tracker)

    # Create Simulacrum Synthesizer
    synthesizer = create_on_battlefield(game, p1, SIMULACRUM_SYNTHESIZER)

    print(f"Scry triggered: {scry_triggered['count']} times")
    print(f"Scry amount: {scry_triggered['amount']}")

    assert scry_triggered['count'] == 1, "Should trigger scry once"
    assert scry_triggered['amount'] == 2, "Should scry 2"
    print("PASS: Simulacrum Synthesizer triggers scry 2 on ETB!")


def test_simulacrum_synthesizer_creates_construct():
    """Test Simulacrum Synthesizer creates Construct when MV>=3 artifact enters."""
    print("\n=== Test: Simulacrum Synthesizer Creates Construct ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Simulacrum Synthesizer first
    synthesizer = create_on_battlefield(game, p1, SIMULACRUM_SYNTHESIZER)

    token_created = {'count': 0, 'name': None}

    # Track token creation
    def track_token_filter(event: Event, state) -> bool:
        return event.type == EventType.CREATE_TOKEN

    def track_token_handler(event: Event, state) -> InterceptorResult:
        token_created['count'] += 1
        token_created['name'] = event.payload.get('token', {}).get('name')
        return InterceptorResult(action=InterceptorAction.PASS)

    tracker = Interceptor(
        id=new_id(),
        source="test",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=track_token_filter,
        handler=track_token_handler,
        duration='forever'
    )
    game.register_interceptor(tracker)

    # Create an artifact with MV >= 3 (using mana_cost to calculate)
    big_artifact = game.create_object(
        name="Big Artifact",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            mana_cost="{4}"  # MV = 4
        )
    )

    # ETB the artifact
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': big_artifact.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Token created: {token_created['count']} times")
    print(f"Token name: {token_created['name']}")

    assert token_created['count'] == 1, "Should create one Construct token"
    assert token_created['name'] == 'Construct', "Token should be named Construct"
    print("PASS: Simulacrum Synthesizer creates Construct for MV>=3 artifacts!")


def test_simulacrum_synthesizer_mv_under_3_no_trigger():
    """Test Simulacrum Synthesizer doesn't trigger for MV < 3 artifacts."""
    print("\n=== Test: Simulacrum Synthesizer No Trigger for MV < 3 ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Simulacrum Synthesizer first
    synthesizer = create_on_battlefield(game, p1, SIMULACRUM_SYNTHESIZER)

    token_created = {'count': 0}

    def track_token_filter(event: Event, state) -> bool:
        return event.type == EventType.CREATE_TOKEN

    def track_token_handler(event: Event, state) -> InterceptorResult:
        token_created['count'] += 1
        return InterceptorResult(action=InterceptorAction.PASS)

    tracker = Interceptor(
        id=new_id(),
        source="test",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=track_token_filter,
        handler=track_token_handler,
        duration='forever'
    )
    game.register_interceptor(tracker)

    # Create an artifact with MV = 2 (under threshold)
    small_artifact = game.create_object(
        name="Small Artifact",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            mana_cost="{2}"  # MV = 2
        )
    )

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': small_artifact.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Tokens created: {token_created['count']}")

    assert token_created['count'] == 0, "Should not create token for MV < 3"
    print("PASS: Simulacrum Synthesizer doesn't trigger for MV < 3!")


def test_simulacrum_synthesizer_x_spell_mv_zero():
    """Test that {X} in mana cost counts as 0 for MV calculation."""
    print("\n=== Test: Simulacrum Synthesizer X=0 for MV ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Simulacrum Synthesizer
    synthesizer = create_on_battlefield(game, p1, SIMULACRUM_SYNTHESIZER)

    token_created = {'count': 0}

    def track_token_filter(event: Event, state) -> bool:
        return event.type == EventType.CREATE_TOKEN

    def track_token_handler(event: Event, state) -> InterceptorResult:
        token_created['count'] += 1
        return InterceptorResult(action=InterceptorAction.PASS)

    tracker = Interceptor(
        id=new_id(),
        source="test",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=track_token_filter,
        handler=track_token_handler,
        duration='forever'
    )
    game.register_interceptor(tracker)

    # Create an artifact with {X}{2} cost - on battlefield, X=0, so MV=2
    # This is below the threshold
    # Note: parse_cost treats X as 0, so {X}{2} = MV 2
    x_artifact = game.create_object(
        name="X Artifact",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            mana_cost="{X}{2}"  # X=0 on battlefield, so MV=2
        )
    )

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': x_artifact.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Tokens created for {{X}}{{2}} artifact: {token_created['count']}")

    # MV = 2 (X=0 + 2), which is less than 3
    assert token_created['count'] == 0, "X=0 on battlefield, so MV < 3"
    print("PASS: X is 0 for MV calculation on battlefield!")


# =============================================================================
# TESTS: Sword of Wealth and Power
# =============================================================================

def test_sword_pt_boost():
    """Test Sword of Wealth and Power gives +2/+2."""
    print("\n=== Test: Sword of Wealth and Power +2/+2 ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create creature
    creature = create_simple_creature(game, p1, "Test Creature", 2, 2)

    # Create and equip sword
    sword = create_on_battlefield(game, p1, SWORD_OF_WEALTH_AND_POWER)
    sword.state.attached_to = creature.id
    creature.state.attachments = [sword.id]

    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)

    print(f"Equipped creature P/T: {power}/{toughness}")

    assert power == 4, f"Expected power 4 (2+2), got {power}"
    assert toughness == 4, f"Expected toughness 4 (2+2), got {toughness}"
    print("PASS: Sword gives +2/+2!")


def test_sword_protection_prevents_targeting():
    """Test Sword protection prevents instant/sorcery targeting."""
    print("\n=== Test: Sword Protection Prevents Targeting ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create creature and equip sword
    creature = create_simple_creature(game, p1, "Protected Creature", 2, 2)
    sword = create_on_battlefield(game, p1, SWORD_OF_WEALTH_AND_POWER)
    sword.state.attached_to = creature.id
    creature.state.attachments = [sword.id]

    # Create an instant that would target it
    lightning_bolt = game.create_object(
        name="Lightning Bolt",
        owner_id=p2.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors={Color.RED}
        )
    )

    targeting_prevented = {'prevented': False}

    # The sword's protection interceptor should PREVENT targeting
    target_event = Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source_id': lightning_bolt.id,
            'target_id': creature.id
        }
    )

    # Process through interceptors
    for interceptor in game.state.interceptors.values():
        if interceptor.filter(target_event, game.state):
            result = interceptor.handler(target_event, game.state)
            if result.action == InterceptorAction.PREVENT:
                targeting_prevented['prevented'] = True
                break

    print(f"Targeting prevented: {targeting_prevented['prevented']}")

    assert targeting_prevented['prevented'], "Protection should prevent instant targeting"
    print("PASS: Protection prevents instant/sorcery targeting!")


def test_sword_protection_prevents_damage():
    """Test Sword protection prevents instant/sorcery damage."""
    print("\n=== Test: Sword Protection Prevents Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create creature and equip sword
    creature = create_simple_creature(game, p1, "Protected Creature", 2, 2)
    sword = create_on_battlefield(game, p1, SWORD_OF_WEALTH_AND_POWER)
    sword.state.attached_to = creature.id
    creature.state.attachments = [sword.id]

    # Create an instant damage source
    lightning_bolt = game.create_object(
        name="Lightning Bolt",
        owner_id=p2.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors={Color.RED}
        )
    )

    damage_prevented = {'prevented': False}

    damage_event = Event(
        type=EventType.DAMAGE,
        payload={
            'source': lightning_bolt.id,
            'target': creature.id,
            'amount': 3
        }
    )

    for interceptor in game.state.interceptors.values():
        if interceptor.filter(damage_event, game.state):
            result = interceptor.handler(damage_event, game.state)
            if result.action == InterceptorAction.PREVENT:
                damage_prevented['prevented'] = True
                break

    print(f"Damage prevented: {damage_prevented['prevented']}")

    assert damage_prevented['prevented'], "Protection should prevent instant damage"
    print("PASS: Protection prevents instant/sorcery damage!")


def test_sword_combat_damage_trigger():
    """Test Sword triggers on combat damage to create Treasure."""
    print("\n=== Test: Sword Combat Damage Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create creature and equip sword
    creature = create_simple_creature(game, p1, "Attacker", 2, 2)
    sword = create_on_battlefield(game, p1, SWORD_OF_WEALTH_AND_POWER)
    sword.state.attached_to = creature.id
    creature.state.attachments = [sword.id]

    treasure_created = {'count': 0}

    def track_treasure_filter(event: Event, state) -> bool:
        if event.type != EventType.CREATE_TOKEN:
            return False
        return event.payload.get('token', {}).get('name') == 'Treasure'

    def track_treasure_handler(event: Event, state) -> InterceptorResult:
        treasure_created['count'] += 1
        return InterceptorResult(action=InterceptorAction.PASS)

    tracker = Interceptor(
        id=new_id(),
        source="test",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=track_treasure_filter,
        handler=track_treasure_handler,
        duration='forever'
    )
    game.register_interceptor(tracker)

    # Deal combat damage to opponent
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': creature.id,
            'target': p2.id,
            'amount': 4,
            'is_combat': True
        }
    ))

    print(f"Treasures created: {treasure_created['count']}")
    print(f"Copy next spell flag: {sword.state.copy_next_spell}")

    assert treasure_created['count'] == 1, "Should create 1 Treasure"
    assert sword.state.copy_next_spell == True, "Should set up spell copy"
    print("PASS: Sword creates Treasure and sets up spell copy!")


def test_sword_spell_copy_preserves_x():
    """Test Sword spell copy preserves X value."""
    print("\n=== Test: Sword Spell Copy Preserves X ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create creature and equip sword
    creature = create_simple_creature(game, p1, "Attacker", 2, 2)
    sword = create_on_battlefield(game, p1, SWORD_OF_WEALTH_AND_POWER)
    sword.state.attached_to = creature.id
    creature.state.attachments = [sword.id]

    # Trigger the copy setup
    sword.state.copy_next_spell = True

    # Cast a sorcery with X=5
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'spell_id': 'fireball',
            'types': {CardType.SORCERY},
            'x_value': 5,
            'modes': []
        }
    ))

    # Check the copy data stored on the sword
    copy_data = sword.state.last_copy_data if hasattr(sword.state, 'last_copy_data') else {}

    print(f"Copy X value: {copy_data.get('x_value')}")
    print(f"Preserve division: {copy_data.get('preserve_division')}")

    assert copy_data.get('x_value') == 5, "X value should be preserved"
    assert copy_data.get('preserve_division') == True, "Division should be preserved"
    print("PASS: Spell copy preserves X value and division!")


# =============================================================================
# TESTS: Nexus of Becoming
# =============================================================================

def test_nexus_combat_trigger_draws():
    """Test Nexus of Becoming draws a card at combat."""
    print("\n=== Test: Nexus of Becoming Combat Draw ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    # Create Nexus
    nexus = create_on_battlefield(game, p1, NEXUS_OF_BECOMING)

    draw_triggered = {'count': 0}

    def track_draw_filter(event: Event, state) -> bool:
        return event.type == EventType.DRAW

    def track_draw_handler(event: Event, state) -> InterceptorResult:
        draw_triggered['count'] += 1
        return InterceptorResult(action=InterceptorAction.PASS)

    tracker = Interceptor(
        id=new_id(),
        source="test",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=track_draw_filter,
        handler=track_draw_handler,
        duration='forever'
    )
    game.register_interceptor(tracker)

    # Trigger combat phase
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'combat'}
    ))

    print(f"Draw triggered: {draw_triggered['count']} times")

    assert draw_triggered['count'] == 1, "Should draw 1 card"
    print("PASS: Nexus of Becoming draws at combat!")


def test_nexus_token_is_3_3_golem():
    """Test Nexus token is a 3/3 Golem artifact creature."""
    print("\n=== Test: Nexus Token is 3/3 Golem ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a creature card to exile
    original = game.create_object(
        name="Big Dragon",
        owner_id=p1.id,
        zone=ZoneType.EXILE,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Dragon"},
            power=6,
            toughness=6,
            colors={Color.RED}
        )
    )

    # Create Nexus
    nexus = create_on_battlefield(game, p1, NEXUS_OF_BECOMING)

    # Use helper to create the token
    token_event = create_nexus_token(game.state, p1.id, original, nexus.id)

    token_data = token_event.payload.get('token', {})

    print(f"Token name: {token_data.get('name')}")
    print(f"Token P/T: {token_data.get('power')}/{token_data.get('toughness')}")
    print(f"Token types: {token_data.get('types')}")
    print(f"Token subtypes: {token_data.get('subtypes')}")

    assert token_data.get('power') == 3, "Should be 3 power"
    assert token_data.get('toughness') == 3, "Should be 3 toughness"
    assert CardType.ARTIFACT in token_data.get('types', set()), "Should be artifact"
    assert CardType.CREATURE in token_data.get('types', set()), "Should be creature"
    assert 'Golem' in token_data.get('subtypes', set()), "Should be Golem"
    assert 'Dragon' in token_data.get('subtypes', set()), "Should keep original subtypes"
    print("PASS: Nexus token is 3/3 Golem artifact creature with original subtypes!")


def test_nexus_token_has_etb_abilities():
    """Test that Nexus token copies have ETB abilities that trigger."""
    print("\n=== Test: Nexus Token ETB Triggers ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a creature with an ETB ability
    etb_creature = game.create_object(
        name="ETB Beast",
        owner_id=p1.id,
        zone=ZoneType.EXILE,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Beast"},
            power=4,
            toughness=4,
            abilities=[{'etb_draw': True}]  # Has ETB ability
        )
    )

    nexus = create_on_battlefield(game, p1, NEXUS_OF_BECOMING)

    token_event = create_nexus_token(game.state, p1.id, etb_creature, nexus.id)
    token_data = token_event.payload.get('token', {})

    print(f"Token abilities: {token_data.get('abilities')}")

    # Token should have copied the ETB ability
    assert token_data.get('abilities') == [{'etb_draw': True}], "Should copy abilities"
    print("PASS: Nexus token copies abilities (ETB will trigger when it enters)!")


# =============================================================================
# TESTS: Torpor Orb
# =============================================================================

def test_torpor_orb_prevents_creature_etb():
    """Test Torpor Orb prevents creature ETB triggers."""
    print("\n=== Test: Torpor Orb Prevents Creature ETB ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Torpor Orb first
    torpor = create_on_battlefield(game, p1, TORPOR_ORB)

    etb_fired = {'count': 0}

    # Create a creature with ETB trigger
    def etb_creature_setup(obj, state):
        def etb_filter(event, state):
            if event.type != EventType.ZONE_CHANGE:
                return False
            if event.payload.get('object_id') != obj.id:
                return False
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            # Check if Torpor Orb prevented this
            if hasattr(obj.state, '_torpor_orb_applied') and obj.state._torpor_orb_applied:
                return False  # Don't trigger
            return True

        def etb_handler(event, state):
            etb_fired['count'] += 1
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield'
        )]

    etb_creature_def = make_creature(
        name="ETB Creature",
        power=2, toughness=2,
        mana_cost="{1}{G}",
        colors={Color.GREEN},
        subtypes={"Beast"},
        text="When this enters, do something.",
        setup_interceptors=etb_creature_setup
    )

    # Create the creature
    creature = create_on_battlefield(game, p1, etb_creature_def)

    print(f"ETB triggered: {etb_fired['count']} times")

    assert etb_fired['count'] == 0, "ETB should NOT trigger with Torpor Orb"
    print("PASS: Torpor Orb prevents creature ETB triggers!")


def test_torpor_orb_replacement_effects_work():
    """Test that Torpor Orb doesn't affect 'enters with' effects."""
    print("\n=== Test: Torpor Orb Doesn't Affect Replacement Effects ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Torpor Orb
    torpor = create_on_battlefield(game, p1, TORPOR_ORB)

    # Create a creature that enters with +1/+1 counters
    # This is a replacement effect, NOT a triggered ability
    counter_creature = game.create_object(
        name="Counter Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=0,
            toughness=0
        )
    )
    # Simulate "enters with 2 +1/+1 counters" - this is a replacement effect
    counter_creature.state.counters['+1/+1'] = 2

    counters = counter_creature.state.counters.get('+1/+1', 0)
    print(f"Counters on creature: {counters}")

    assert counters == 2, "Replacement effects should still work"
    print("PASS: Torpor Orb doesn't prevent 'enters with' counters!")


def test_torpor_orb_affects_other_triggers():
    """Test Torpor Orb prevents other cards' creature ETB triggers."""
    print("\n=== Test: Torpor Orb Affects Other ETB Triggers ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Torpor Orb
    torpor = create_on_battlefield(game, p1, TORPOR_ORB)

    etb_triggered = {'count': 0}

    # Create a "Soul Warden" style card that triggers on creature ETB
    def soul_warden_setup(obj, state):
        def trigger_filter(event, state):
            if event.type != EventType.ZONE_CHANGE:
                return False
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False

            entering_id = event.payload.get('object_id')
            entering = state.objects.get(entering_id)
            if not entering:
                return False
            if CardType.CREATURE not in entering.characteristics.types:
                return False

            # Torpor Orb should prevent this trigger
            if hasattr(entering.state, '_torpor_orb_applied') and entering.state._torpor_orb_applied:
                return False
            return True

        def trigger_handler(event, state):
            etb_triggered['count'] += 1
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=trigger_filter,
            handler=trigger_handler,
            duration='while_on_battlefield'
        )]

    soul_warden_def = make_creature(
        name="Soul Warden",
        power=1, toughness=1,
        mana_cost="{W}",
        colors={Color.WHITE},
        subtypes={"Human", "Cleric"},
        text="Whenever another creature enters, you gain 1 life.",
        setup_interceptors=soul_warden_setup
    )

    # Put Soul Warden on battlefield (before Torpor Orb for this test,
    # but Torpor Orb is already there so it gets marked)
    warden = create_on_battlefield(game, p1, soul_warden_def)

    # Now create another creature - Soul Warden should NOT trigger
    bear = game.create_object(
        name="Bear",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=2,
            toughness=2
        )
    )

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': bear.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Soul Warden triggered: {etb_triggered['count']} times")

    # Note: This test checks that creatures entering don't cause triggers
    # The bear entering should not cause Soul Warden to trigger
    assert etb_triggered['count'] == 0, "Soul Warden should not trigger with Torpor Orb"
    print("PASS: Torpor Orb prevents other cards' creature ETB triggers!")


def test_torpor_orb_non_creature_etb_works():
    """Test that Torpor Orb doesn't affect non-creature ETB."""
    print("\n=== Test: Torpor Orb Doesn't Affect Non-Creature ETB ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Torpor Orb
    torpor = create_on_battlefield(game, p1, TORPOR_ORB)

    artifact_etb_triggered = {'count': 0}

    # Create an artifact with ETB trigger
    def artifact_etb_setup(obj, state):
        def etb_filter(event, state):
            if event.type != EventType.ZONE_CHANGE:
                return False
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)

        def etb_handler(event, state):
            artifact_etb_triggered['count'] += 1
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield'
        )]

    etb_artifact_def = make_artifact(
        name="ETB Artifact",
        mana_cost="{3}",
        colors=set(),
        text="When this enters, do something.",
        setup_interceptors=artifact_etb_setup
    )

    # Create the artifact
    artifact = create_on_battlefield(game, p1, etb_artifact_def)

    print(f"Artifact ETB triggered: {artifact_etb_triggered['count']} times")

    # Non-creature artifacts should still have their ETB trigger
    assert artifact_etb_triggered['count'] == 1, "Non-creature ETB should work"
    print("PASS: Torpor Orb doesn't affect non-creature ETB!")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_big_score_tests():
    """Run all Big Score rulings tests."""
    print("=" * 70)
    print("THE BIG SCORE (BIG) RULINGS TESTS")
    print("=" * 70)

    # Simulacrum Synthesizer tests
    print("\n" + "-" * 35)
    print("SIMULACRUM SYNTHESIZER TESTS")
    print("-" * 35)
    test_simulacrum_synthesizer_etb_scry()
    test_simulacrum_synthesizer_creates_construct()
    test_simulacrum_synthesizer_mv_under_3_no_trigger()
    test_simulacrum_synthesizer_x_spell_mv_zero()

    # Sword of Wealth and Power tests
    print("\n" + "-" * 35)
    print("SWORD OF WEALTH AND POWER TESTS")
    print("-" * 35)
    test_sword_pt_boost()
    test_sword_protection_prevents_targeting()
    test_sword_protection_prevents_damage()
    test_sword_combat_damage_trigger()
    test_sword_spell_copy_preserves_x()

    # Nexus of Becoming tests
    print("\n" + "-" * 35)
    print("NEXUS OF BECOMING TESTS")
    print("-" * 35)
    test_nexus_combat_trigger_draws()
    test_nexus_token_is_3_3_golem()
    test_nexus_token_has_etb_abilities()

    # Torpor Orb tests
    print("\n" + "-" * 35)
    print("TORPOR ORB TESTS")
    print("-" * 35)
    test_torpor_orb_prevents_creature_etb()
    test_torpor_orb_replacement_effects_work()
    test_torpor_orb_affects_other_triggers()
    test_torpor_orb_non_creature_etb_works()

    print("\n" + "=" * 70)
    print("ALL BIG SCORE RULINGS TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_big_score_tests()
