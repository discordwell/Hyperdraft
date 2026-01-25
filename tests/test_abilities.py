"""
Tests for the Ability System

Validates that:
1. Abilities correctly generate rules text
2. Abilities correctly generate interceptors
3. Generated interceptors behave correctly
4. Backward compatibility with existing cards
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    # Core types
    Game, GameObject, GameState, CardDefinition, Characteristics,
    Event, EventType, ZoneType, CardType, Color,
    Interceptor, InterceptorPriority,
    new_id,
    # Card builders
    make_creature, make_enchantment,
    # Ability system
    TriggeredAbility, StaticAbility, KeywordAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, DealsDamageTrigger,
    UpkeepTrigger, LifeGainTrigger,
    GainLife, LoseLife, DrawCards, CompositeEffect, AddCounters,
    PTBoost, KeywordGrant,
    SelfTarget, AnotherCreature, AnotherCreatureYouControl, CreatureWithSubtype,
    CreaturesYouControlFilter, OtherCreaturesYouControlFilter, CreaturesWithSubtypeFilter,
)


# =============================================================================
# Test Cards Using Ability System
# =============================================================================

# Simple ETB - Gain Life
HEALER_OF_THE_GLADE = make_creature(
    name="Healer of the Glade",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(3)
        )
    ]
)

# Soul Warden equivalent - triggers on other creatures
SOUL_WARDEN_V2 = make_creature(
    name="Soul Warden",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(target=AnotherCreature()),
            effect=GainLife(1)
        )
    ]
)

# Glorious Anthem equivalent - lord effect
GLORIOUS_ANTHEM_V2 = make_enchantment(
    name="Glorious Anthem",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesYouControlFilter()
        )
    ]
)

# Lord with tribal filter
ELVISH_ARCHDRUID = make_creature(
    name="Elvish Archdruid",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Elf", include_self=False)
        )
    ]
)

# Flying creature with ETB
MULLDRIFTER = make_creature(
    name="Mulldrifter",
    power=2, toughness=2,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    abilities=[
        KeywordAbility("Flying"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(2)
        )
    ]
)

# Composite effect
INSPIRING_OVERSEER = make_creature(
    name="Inspiring Overseer",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    abilities=[
        KeywordAbility("Flying"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CompositeEffect([GainLife(1), DrawCards(1)])
        )
    ]
)

# Combat damage trigger
THIEVING_MAGPIE = make_creature(
    name="Thieving Magpie",
    power=1, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    abilities=[
        KeywordAbility("Flying"),
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=DrawCards(1)
        )
    ]
)


# =============================================================================
# Text Generation Tests
# =============================================================================

def test_etb_trigger_text():
    """Test ETB trigger text generation."""
    print("Testing ETB trigger text generation...")

    # Self ETB
    assert "enters the battlefield" in HEALER_OF_THE_GLADE.text.lower()
    assert "gain 3 life" in HEALER_OF_THE_GLADE.text.lower()
    print(f"  Healer of the Glade: {HEALER_OF_THE_GLADE.text}")

    # Other creature ETB
    assert "another creature" in SOUL_WARDEN_V2.text.lower()
    assert "enters the battlefield" in SOUL_WARDEN_V2.text.lower()
    assert "gain 1 life" in SOUL_WARDEN_V2.text.lower()
    print(f"  Soul Warden: {SOUL_WARDEN_V2.text}")

    print("  PASSED")


def test_static_ability_text():
    """Test static ability text generation."""
    print("Testing static ability text generation...")

    # Anthem effect
    assert "creatures you control" in GLORIOUS_ANTHEM_V2.text.lower()
    assert "+1/+1" in GLORIOUS_ANTHEM_V2.text
    print(f"  Glorious Anthem: {GLORIOUS_ANTHEM_V2.text}")

    # Tribal lord
    assert "elf" in ELVISH_ARCHDRUID.text.lower()
    assert "+1/+1" in ELVISH_ARCHDRUID.text
    print(f"  Elvish Archdruid: {ELVISH_ARCHDRUID.text}")

    print("  PASSED")


def test_keyword_ability_text():
    """Test keyword ability text generation."""
    print("Testing keyword ability text generation...")

    # Flying + ETB
    assert "Flying" in MULLDRIFTER.text
    assert "draw" in MULLDRIFTER.text.lower()
    print(f"  Mulldrifter: {MULLDRIFTER.text}")

    print("  PASSED")


def test_composite_effect_text():
    """Test composite effect text generation."""
    print("Testing composite effect text generation...")

    # Gain life AND draw
    text_lower = INSPIRING_OVERSEER.text.lower()
    assert "gain 1 life" in text_lower
    assert "draw" in text_lower
    assert "and" in text_lower
    print(f"  Inspiring Overseer: {INSPIRING_OVERSEER.text}")

    print("  PASSED")


def test_damage_trigger_text():
    """Test damage trigger text generation."""
    print("Testing damage trigger text generation...")

    text_lower = THIEVING_MAGPIE.text.lower()
    assert "deals" in text_lower
    assert "combat" in text_lower
    assert "damage" in text_lower
    assert "player" in text_lower
    print(f"  Thieving Magpie: {THIEVING_MAGPIE.text}")

    print("  PASSED")


# =============================================================================
# Interceptor Generation Tests
# =============================================================================

def test_etb_interceptor_generation():
    """Test that ETB triggers generate correct interceptors."""
    print("Testing ETB interceptor generation...")

    game = Game()
    player = game.add_player("Player 1")
    p1 = player.id

    # Create a healer
    healer = game.create_object(
        name="Healer of the Glade",
        owner_id=p1,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HEALER_OF_THE_GLADE.characteristics,
        card_def=HEALER_OF_THE_GLADE
    )

    # Generate interceptors
    interceptors = HEALER_OF_THE_GLADE.setup_interceptors(healer, game.state)

    assert len(interceptors) == 1, f"Expected 1 interceptor, got {len(interceptors)}"
    assert interceptors[0].priority == InterceptorPriority.REACT

    print(f"  Generated {len(interceptors)} interceptor(s)")
    print("  PASSED")


def test_static_pt_boost_interceptor():
    """Test that static P/T boost generates correct interceptors."""
    print("Testing static P/T boost interceptor generation...")

    game = Game()
    player = game.add_player("Player 1")
    p1 = player.id

    # Create anthem
    anthem = game.create_object(
        name="Glorious Anthem",
        owner_id=p1,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GLORIOUS_ANTHEM_V2.characteristics,
        card_def=GLORIOUS_ANTHEM_V2
    )

    # Generate interceptors
    interceptors = GLORIOUS_ANTHEM_V2.setup_interceptors(anthem, game.state)

    # Should have 2 interceptors: one for power, one for toughness
    assert len(interceptors) == 2, f"Expected 2 interceptors, got {len(interceptors)}"
    assert all(i.priority == InterceptorPriority.QUERY for i in interceptors)

    print(f"  Generated {len(interceptors)} interceptor(s)")
    print("  PASSED")


def test_keyword_with_trigger_interceptors():
    """Test that keywords + triggers generate correct interceptors."""
    print("Testing keyword + trigger interceptor generation...")

    game = Game()
    player = game.add_player("Player 1")
    p1 = player.id

    # Create mulldrifter
    mulldrifter = game.create_object(
        name="Mulldrifter",
        owner_id=p1,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MULLDRIFTER.characteristics,
        card_def=MULLDRIFTER
    )

    # Generate interceptors
    interceptors = MULLDRIFTER.setup_interceptors(mulldrifter, game.state)

    # Should have 1 interceptor for ETB (Flying doesn't need interceptor)
    assert len(interceptors) >= 1, f"Expected at least 1 interceptor, got {len(interceptors)}"

    print(f"  Generated {len(interceptors)} interceptor(s)")
    print("  PASSED")


# =============================================================================
# Backward Compatibility Tests
# =============================================================================

def test_backward_compatibility():
    """Test that cards without abilities still work."""
    print("Testing backward compatibility...")

    # Create a card the old way
    def old_style_setup(obj, state):
        return []

    OLD_STYLE_CARD = make_creature(
        name="Old Style Creature",
        power=2, toughness=2,
        mana_cost="{1}{G}",
        colors={Color.GREEN},
        text="This card uses the old setup_interceptors pattern.",
        setup_interceptors=old_style_setup
    )

    # Should still have the manually provided text
    assert OLD_STYLE_CARD.text == "This card uses the old setup_interceptors pattern."
    assert OLD_STYLE_CARD.setup_interceptors == old_style_setup

    print(f"  Old style card text: {OLD_STYLE_CARD.text}")
    print("  PASSED")


def test_mixed_abilities_and_setup():
    """Test that abilities + custom setup can coexist."""
    print("Testing mixed abilities and custom setup...")

    def custom_setup(obj, state):
        return []

    # If both abilities AND setup_interceptors are provided,
    # the manual setup_interceptors should take precedence
    MIXED_CARD = make_creature(
        name="Mixed Card",
        power=1, toughness=1,
        mana_cost="{W}",
        colors={Color.WHITE},
        abilities=[
            TriggeredAbility(
                trigger=ETBTrigger(),
                effect=GainLife(1)
            )
        ],
        text="Custom text takes precedence.",
        setup_interceptors=custom_setup
    )

    # Custom text and setup should be preserved
    assert MIXED_CARD.text == "Custom text takes precedence."
    assert MIXED_CARD.setup_interceptors == custom_setup

    print(f"  Mixed card text: {MIXED_CARD.text}")
    print("  PASSED")


# =============================================================================
# Integration Tests
# =============================================================================

def test_soul_warden_trigger_fires():
    """Test that Soul Warden's trigger actually fires on creature ETB."""
    print("Testing Soul Warden trigger fires correctly...")

    game = Game()
    player = game.add_player("Player 1")
    p1 = player.id
    starting_life = game.state.players[p1].life

    # Create Soul Warden - create_object automatically registers interceptors
    warden = game.create_object(
        name="Soul Warden",
        owner_id=p1,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN_V2.characteristics,
        card_def=SOUL_WARDEN_V2
    )

    # Verify interceptor was registered
    assert len(warden.interceptor_ids) == 1, f"Expected 1 interceptor, got {len(warden.interceptor_ids)}"

    # Create another creature (should trigger Soul Warden)
    other = game.create_object(
        name="Grizzly Bears",
        owner_id=p1,
        zone=ZoneType.HAND,  # Start in hand
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=2, toughness=2
        ),
        card_def=None
    )

    # Emit zone change event (hand -> battlefield)
    etb_event = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': other.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=other.id,
        controller=p1
    )

    # Process the event
    triggered_events = game.emit(etb_event)

    # Check if life gain event was triggered
    life_events = [e for e in triggered_events if e.type == EventType.LIFE_CHANGE]

    assert len(life_events) == 1, f"Expected 1 life change event, got {len(life_events)}"
    assert life_events[0].payload['amount'] == 1

    print(f"  Triggered {len(triggered_events)} event(s)")
    print(f"  Life change event: +{life_events[0].payload['amount']}")
    print("  PASSED")


def test_anthem_boosts_creatures():
    """Test that Glorious Anthem boosts creature power/toughness."""
    print("Testing Glorious Anthem boosts creatures...")

    from src.engine import get_power, get_toughness

    game = Game()
    player = game.add_player("Player 1")
    p1 = player.id

    # Create a 2/2 creature
    bear = game.create_object(
        name="Grizzly Bears",
        owner_id=p1,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Bear"},
            power=2, toughness=2
        ),
        card_def=None
    )

    # Check base power/toughness
    base_power = get_power(bear, game.state)
    base_toughness = get_toughness(bear, game.state)
    assert base_power == 2
    assert base_toughness == 2

    # Create Glorious Anthem - create_object automatically registers interceptors
    anthem = game.create_object(
        name="Glorious Anthem",
        owner_id=p1,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GLORIOUS_ANTHEM_V2.characteristics,
        card_def=GLORIOUS_ANTHEM_V2
    )

    # Verify interceptors were registered (power + toughness = 2)
    assert len(anthem.interceptor_ids) == 2, f"Expected 2 interceptors, got {len(anthem.interceptor_ids)}"

    # Check boosted power/toughness
    boosted_power = get_power(bear, game.state)
    boosted_toughness = get_toughness(bear, game.state)

    print(f"  Bear before anthem: 2/2")
    print(f"  Bear after anthem: {boosted_power}/{boosted_toughness}")

    assert boosted_power == 3, f"Expected power 3, got {boosted_power}"
    assert boosted_toughness == 3, f"Expected toughness 3, got {boosted_toughness}"

    print("  PASSED")


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    print("=" * 60)
    print("ABILITY SYSTEM TESTS")
    print("=" * 60)
    print()

    # Text generation tests
    print("TEXT GENERATION TESTS")
    print("-" * 40)
    test_etb_trigger_text()
    test_static_ability_text()
    test_keyword_ability_text()
    test_composite_effect_text()
    test_damage_trigger_text()
    print()

    # Interceptor generation tests
    print("INTERCEPTOR GENERATION TESTS")
    print("-" * 40)
    test_etb_interceptor_generation()
    test_static_pt_boost_interceptor()
    test_keyword_with_trigger_interceptors()
    print()

    # Backward compatibility tests
    print("BACKWARD COMPATIBILITY TESTS")
    print("-" * 40)
    test_backward_compatibility()
    test_mixed_abilities_and_setup()
    print()

    # Integration tests
    print("INTEGRATION TESTS")
    print("-" * 40)
    test_soul_warden_trigger_fires()
    test_anthem_boosts_creatures()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
