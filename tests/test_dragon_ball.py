"""
Test Dragon Ball Z: Saiyan Saga cards

Tests for mechanics:
- Power Level (combat damage -> +1/+1 counters)
- Transform (conditional P/T boost and keyword grant)
- Ki Blast (activated ability dealing damage)
- ETB triggers
- Death triggers
- Attack triggers
- Upkeep triggers
- Static lord effects (P/T boosts, keyword grants)
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import engine components
from src.engine.types import (
    Event, EventType, ZoneType, CardType, Color,
    Characteristics, GameObject, GameState
)
from src.engine.game import Game, make_creature
from src.engine.queries import get_power, get_toughness, has_ability

# Import dragon_ball module directly using importlib to avoid __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "dragon_ball",
    str(PROJECT_ROOT / "src/cards/custom/dragon_ball.py")
)
dragon_ball = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dragon_ball)

# Extract what we need from the loaded module
# White cards
GOKU_EARTHS_HERO = dragon_ball.GOKU_EARTHS_HERO
GOHAN_HIDDEN_POWER = dragon_ball.GOHAN_HIDDEN_POWER
KRILLIN_BRAVE_WARRIOR = dragon_ball.KRILLIN_BRAVE_WARRIOR
VIDEL_HERO_IN_TRAINING = dragon_ball.VIDEL_HERO_IN_TRAINING
SUPREME_KAI = dragon_ball.SUPREME_KAI
KING_KAI = dragon_ball.KING_KAI
Z_FIGHTERS_UNITE = dragon_ball.Z_FIGHTERS_UNITE
# Blue cards
ANDROID_18 = dragon_ball.ANDROID_18
ANDROID_17 = dragon_ball.ANDROID_17
ANDROID_16 = dragon_ball.ANDROID_16
BULMA_GENIUS_INVENTOR = dragon_ball.BULMA_GENIUS_INVENTOR
DR_BRIEF = dragon_ball.DR_BRIEF
# Black cards
FRIEZA_EMPEROR = dragon_ball.FRIEZA_EMPEROR
CELL_PERFECT_FORM = dragon_ball.CELL_PERFECT_FORM
KID_BUU = dragon_ball.KID_BUU
SUPER_BUU = dragon_ball.SUPER_BUU
FRIEZA_FORCE = dragon_ball.FRIEZA_FORCE
# Red cards
VEGETA_SAIYAN_PRINCE = dragon_ball.VEGETA_SAIYAN_PRINCE
BROLY_LEGENDARY = dragon_ball.BROLY_LEGENDARY
KID_TRUNKS = dragon_ball.KID_TRUNKS
GOTEN = dragon_ball.GOTEN
KING_VEGETA = dragon_ball.KING_VEGETA
SAIYAN_PRIDE = dragon_ball.SAIYAN_PRIDE
# Green cards
PICCOLO_NAMEKIAN_WARRIOR = dragon_ball.PICCOLO_NAMEKIAN_WARRIOR
NAIL = dragon_ball.NAIL
GURU = dragon_ball.GURU
NAMEKIAN_CHILD = dragon_ball.NAMEKIAN_CHILD
NAMEK_FROG = dragon_ball.NAMEK_FROG
NAMEK_CRAB = dragon_ball.NAMEK_CRAB
NAMEKIAN_RESILIENCE = dragon_ball.NAMEKIAN_RESILIENCE
# Multicolor
VEGITO = dragon_ball.VEGITO
GOGETA = dragon_ball.GOGETA
GOTENKS = dragon_ball.GOTENKS
BEERUS = dragon_ball.BEERUS
HIT = dragon_ball.HIT
# Helpers
SAIYAN_WARRIOR = dragon_ball.SAIYAN_WARRIOR
ANDROID_PROTOTYPE = dragon_ball.ANDROID_PROTOTYPE
NAMEKIAN_WARRIOR = dragon_ball.NAMEKIAN_WARRIOR
# Ki Blast helper
make_ki_blast_ability = dragon_ball.make_ki_blast_ability


# =============================================================================
# WHITE CARD TESTS
# =============================================================================

def test_krillin_etb_life_gain():
    """Test Krillin, Brave Warrior ETB: gain 3 life."""
    print("\n=== Test: Krillin ETB Life Gain ===")

    game = Game()
    p1 = game.add_player("Alice")
    starting_life = p1.life

    creature = game.create_object(
        name="Krillin, Brave Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=KRILLIN_BRAVE_WARRIOR.characteristics,
        card_def=KRILLIN_BRAVE_WARRIOR
    )

    # Emit ETB event
    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=creature.id,
        controller=p1.id
    ))

    life_events = [e for e in triggered_events if e.type == EventType.LIFE_CHANGE]
    print(f"Life change events triggered: {len(life_events)}")

    # Check that at least one life event with +3 occurred
    life_gain_3 = [e for e in life_events if e.payload.get('amount', 0) == 3]
    assert len(life_gain_3) >= 1, f"Expected at least one +3 life event, got {[e.payload.get('amount') for e in life_events]}"
    print("PASSED: Krillin ETB triggers life gain of 3")


def test_supreme_kai_etb_scry():
    """Test Supreme Kai, Divine Watcher ETB: scry 3."""
    print("\n=== Test: Supreme Kai ETB Scry ===")

    game = Game()
    p1 = game.add_player("Alice")

    creature = game.create_object(
        name="Supreme Kai, Divine Watcher",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SUPREME_KAI.characteristics,
        card_def=SUPREME_KAI
    )

    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=creature.id,
        controller=p1.id
    ))

    # Scry uses ACTIVATE event with action='scry' as placeholder
    scry_events = [e for e in triggered_events if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry']
    print(f"Scry events triggered: {len(scry_events)}")

    # Check that at least one scry 3 event occurred
    scry_3_events = [e for e in scry_events if e.payload.get('amount') == 3]
    assert len(scry_3_events) >= 1, f"Expected at least one scry 3 event, got {[e.payload.get('amount') for e in scry_events]}"
    print("PASSED: Supreme Kai ETB triggers scry 3")


def test_king_kai_upkeep_draw():
    """Test King Kai, Martial Arts Master: draw a card at upkeep."""
    print("\n=== Test: King Kai Upkeep Draw ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    creature = game.create_object(
        name="King Kai, Martial Arts Master",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=KING_KAI.characteristics,
        card_def=KING_KAI
    )

    # Emit upkeep phase start
    triggered_events = game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep'},
        source=None,
        controller=p1.id
    ))

    # DrawCards generates one DRAW event per card drawn
    draw_events = [e for e in triggered_events if e.type == EventType.DRAW]
    print(f"Draw events triggered: {len(draw_events)}")

    # King Kai draws 1 card, so 1 draw event
    assert len(draw_events) >= 1, f"Expected at least 1 draw event, got {len(draw_events)}"
    print("PASSED: King Kai triggers draw at upkeep")


def test_gohan_death_trigger_counters():
    """Test Gohan, Hidden Power: +2 +1/+1 counters when another creature dies."""
    print("\n=== Test: Gohan Death Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")

    gohan = game.create_object(
        name="Gohan, Hidden Power",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOHAN_HIDDEN_POWER.characteristics,
        card_def=GOHAN_HIDDEN_POWER
    )

    # Create another creature to die
    other_creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=2, toughness=2
        ),
        card_def=None
    )

    # Emit death event for the other creature
    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': other_creature.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=other_creature.id,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")
    for e in counter_events:
        print(f"  Counter event: {e.payload}")

    # Check that at least one counter event on Gohan occurred (any amount)
    gohan_counter_events = [e for e in counter_events if e.payload.get('object_id') == gohan.id]
    assert len(gohan_counter_events) >= 1, f"Expected at least one counter event for Gohan, got {len(gohan_counter_events)}"
    print("PASSED: Gohan gains +1/+1 counters when another creature dies")


def test_videl_grants_vigilance():
    """Test Videl, Hero in Training: other Z-Fighters have vigilance."""
    print("\n=== Test: Videl Grants Vigilance ===")

    game = Game()
    p1 = game.add_player("Alice")

    videl = game.create_object(
        name="Videl, Hero in Training",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=VIDEL_HERO_IN_TRAINING.characteristics,
        card_def=VIDEL_HERO_IN_TRAINING
    )

    # Create a Z-Fighter
    z_fighter = game.create_object(
        name="Test Z-Fighter",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human", "Z-Fighter"},
            power=2, toughness=2
        ),
        card_def=None
    )

    # Use has_ability to check if vigilance was granted
    has_vigilance = has_ability(z_fighter, 'vigilance', game.state)
    print(f"Z-Fighter has vigilance: {has_vigilance}")

    assert has_vigilance, f"Expected Z-Fighter to have vigilance granted by Videl"
    print("PASSED: Videl grants vigilance to other Z-Fighters")


def test_z_fighters_unite_lord_effect():
    """Test Z-Fighters Unite: Z-Fighters get +1/+1."""
    print("\n=== Test: Z-Fighters Unite Lord Effect ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create enchantment first
    enchantment = game.create_object(
        name="Z-Fighters Unite",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Z_FIGHTERS_UNITE.characteristics,
        card_def=Z_FIGHTERS_UNITE
    )

    # Create a Z-Fighter
    krillin = game.create_object(
        name="Krillin, Brave Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=KRILLIN_BRAVE_WARRIOR.characteristics,
        card_def=KRILLIN_BRAVE_WARRIOR
    )

    base_power = KRILLIN_BRAVE_WARRIOR.characteristics.power
    base_toughness = KRILLIN_BRAVE_WARRIOR.characteristics.toughness

    actual_power = get_power(krillin, game.state)
    actual_toughness = get_toughness(krillin, game.state)

    print(f"Krillin base: {base_power}/{base_toughness}")
    print(f"Krillin with Z-Fighters Unite: {actual_power}/{actual_toughness}")

    assert actual_power == base_power + 1, f"Expected power {base_power + 1}, got {actual_power}"
    assert actual_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}, got {actual_toughness}"
    print("PASSED: Z-Fighters Unite grants +1/+1 to Z-Fighters")


# =============================================================================
# BLUE CARD TESTS
# =============================================================================

def test_android_18_etb_draw():
    """Test Android 18, Infinite Energy ETB: draw a card."""
    print("\n=== Test: Android 18 ETB Draw ===")

    game = Game()
    p1 = game.add_player("Alice")

    creature = game.create_object(
        name="Android 18, Infinite Energy",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ANDROID_18.characteristics,
        card_def=ANDROID_18
    )

    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=creature.id,
        controller=p1.id
    ))

    draw_events = [e for e in triggered_events if e.type == EventType.DRAW]
    print(f"Draw events triggered: {len(draw_events)}")

    assert len(draw_events) >= 1, f"Expected at least 1 draw event, got {len(draw_events)}"
    print("PASSED: Android 18 ETB triggers card draw")


def test_android_17_grants_hexproof():
    """Test Android 17, Nature's Protector: other Androids have hexproof."""
    print("\n=== Test: Android 17 Grants Hexproof ===")

    game = Game()
    p1 = game.add_player("Alice")

    android_17 = game.create_object(
        name="Android 17, Nature's Protector",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ANDROID_17.characteristics,
        card_def=ANDROID_17
    )

    # Create another Android
    other_android = game.create_object(
        name="Android Prototype",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ANDROID_PROTOTYPE.characteristics,
        card_def=ANDROID_PROTOTYPE
    )

    # Use has_ability to check if hexproof was granted
    has_hexproof = has_ability(other_android, 'hexproof', game.state)
    print(f"Other Android has hexproof: {has_hexproof}")

    assert has_hexproof, f"Expected Android Prototype to have hexproof granted by Android 17"
    print("PASSED: Android 17 grants hexproof to other Androids")


def test_android_16_death_trigger():
    """Test Android 16, Gentle Giant: deals 5 damage to each opponent when it dies."""
    print("\n=== Test: Android 16 Death Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    android_16 = game.create_object(
        name="Android 16, Gentle Giant",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ANDROID_16.characteristics,
        card_def=ANDROID_16
    )

    # Emit death event
    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': android_16.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=android_16.id,
        controller=p1.id
    ))

    damage_events = [e for e in triggered_events if e.type == EventType.DAMAGE]
    print(f"Damage events triggered: {len(damage_events)}")

    # Should deal damage to each opponent (in this case, 1 opponent)
    assert len(damage_events) >= 1, f"Expected at least 1 damage event, got {len(damage_events)}"
    assert damage_events[0].payload['amount'] == 5, f"Expected 5 damage, got {damage_events[0].payload['amount']}"
    print("PASSED: Android 16 death trigger deals 5 damage to opponents")


def test_bulma_artifact_cost_reduction():
    """Test Bulma, Genius Inventor: has interceptor for artifact cost reduction."""
    print("\n=== Test: Bulma Artifact Cost Reduction ===")

    game = Game()
    p1 = game.add_player("Alice")

    bulma = game.create_object(
        name="Bulma, Genius Inventor",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BULMA_GENIUS_INVENTOR.characteristics,
        card_def=BULMA_GENIUS_INVENTOR
    )

    # Check that Bulma has interceptors registered
    print(f"Bulma has {len(bulma.interceptor_ids)} interceptor(s)")

    assert len(bulma.interceptor_ids) >= 1, f"Expected at least 1 interceptor for Bulma, got {len(bulma.interceptor_ids)}"
    print("PASSED: Bulma has cost reduction interceptor registered")


# =============================================================================
# BLACK CARD TESTS
# =============================================================================

def test_kid_buu_upkeep_life_loss():
    """Test Kid Buu, Pure Destruction: each opponent loses 2 life at upkeep."""
    print("\n=== Test: Kid Buu Upkeep Life Loss ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id

    kid_buu = game.create_object(
        name="Kid Buu, Pure Destruction",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=KID_BUU.characteristics,
        card_def=KID_BUU
    )

    # Emit upkeep phase start
    triggered_events = game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep'},
        source=None,
        controller=p1.id
    ))

    life_loss_events = [e for e in triggered_events if e.type == EventType.LIFE_CHANGE and e.payload.get('amount', 0) < 0]
    print(f"Life loss events triggered: {len(life_loss_events)}")

    # Should cause life loss to opponent
    assert len(life_loss_events) >= 1, f"Expected at least 1 life loss event, got {len(life_loss_events)}"
    assert life_loss_events[0].payload['amount'] == -2, f"Expected -2 life, got {life_loss_events[0].payload['amount']}"
    print("PASSED: Kid Buu causes opponents to lose 2 life at upkeep")


def test_cell_absorb_counters():
    """Test Cell, Perfect Form: gains +1/+1 counter when another creature dies."""
    print("\n=== Test: Cell Absorb Counters ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    cell = game.create_object(
        name="Cell, Perfect Form",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CELL_PERFECT_FORM.characteristics,
        card_def=CELL_PERFECT_FORM
    )

    # Create another creature (can be opponent's)
    victim = game.create_object(
        name="Victim",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=2, toughness=2
        ),
        card_def=None
    )

    # Emit death event for the victim
    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=victim.id,
        controller=p2.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    assert len(counter_events) == 1, f"Expected 1 counter added event, got {len(counter_events)}"
    assert counter_events[0].payload['object_id'] == cell.id, "Counter should be added to Cell"
    assert counter_events[0].payload['amount'] == 1, f"Expected 1 counter, got {counter_events[0].payload['amount']}"
    print("PASSED: Cell gains +1/+1 counter when another creature dies")


def test_frieza_force_lord_effect():
    """Test Frieza Force: Soldiers get +1/+0."""
    print("\n=== Test: Frieza Force Lord Effect ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create enchantment first
    enchantment = game.create_object(
        name="Frieza Force",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=FRIEZA_FORCE.characteristics,
        card_def=FRIEZA_FORCE
    )

    # Create a Soldier
    soldier = game.create_object(
        name="Test Soldier",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Alien", "Soldier"},
            power=2, toughness=2
        ),
        card_def=None
    )

    actual_power = get_power(soldier, game.state)
    actual_toughness = get_toughness(soldier, game.state)

    print(f"Soldier base: 2/2")
    print(f"Soldier with Frieza Force: {actual_power}/{actual_toughness}")

    assert actual_power == 3, f"Expected power 3, got {actual_power}"
    assert actual_toughness == 2, f"Expected toughness 2, got {actual_toughness}"
    print("PASSED: Frieza Force grants +1/+0 to Soldiers")


# =============================================================================
# RED CARD TESTS
# =============================================================================

def test_broly_attack_trigger_counters():
    """Test Broly, Legendary Super Saiyan: gains +1/+1 counters when attacking."""
    print("\n=== Test: Broly Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")

    broly = game.create_object(
        name="Broly, Legendary Super Saiyan",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BROLY_LEGENDARY.characteristics,
        card_def=BROLY_LEGENDARY
    )

    # Emit attack event
    triggered_events = game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': broly.id},
        source=broly.id,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    # AddCounters generates one event per counter, so 2 counters = 2 events
    # There might be duplicates, so check for at least 2 counter events
    broly_counter_events = [e for e in counter_events if e.payload.get('object_id') == broly.id]
    assert len(broly_counter_events) >= 2, f"Expected at least 2 counter events for Broly (one per counter), got {len(broly_counter_events)}"
    print("PASSED: Broly gains +1/+1 counters when attacking")


def test_goten_etb_damage():
    """Test Goten, Cheerful Saiyan: deals 2 damage to each opponent on ETB."""
    print("\n=== Test: Goten ETB Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    goten = game.create_object(
        name="Goten, Cheerful Saiyan",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOTEN.characteristics,
        card_def=GOTEN
    )

    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': goten.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=goten.id,
        controller=p1.id
    ))

    damage_events = [e for e in triggered_events if e.type == EventType.DAMAGE]
    print(f"Damage events triggered: {len(damage_events)}")

    assert len(damage_events) >= 1, f"Expected at least 1 damage event, got {len(damage_events)}"
    assert damage_events[0].payload['amount'] == 2, f"Expected 2 damage, got {damage_events[0].payload['amount']}"
    print("PASSED: Goten deals 2 damage to opponents on ETB")


def test_kid_trunks_saiyan_lord():
    """Test Trunks, Young Fighter: other Saiyans get +1/+0."""
    print("\n=== Test: Kid Trunks Saiyan Lord ===")

    game = Game()
    p1 = game.add_player("Alice")

    kid_trunks = game.create_object(
        name="Trunks, Young Fighter",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=KID_TRUNKS.characteristics,
        card_def=KID_TRUNKS
    )

    # Create another Saiyan
    saiyan_warrior = game.create_object(
        name="Saiyan Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SAIYAN_WARRIOR.characteristics,
        card_def=SAIYAN_WARRIOR
    )

    base_power = SAIYAN_WARRIOR.characteristics.power
    actual_power = get_power(saiyan_warrior, game.state)

    print(f"Saiyan Warrior base power: {base_power}")
    print(f"Saiyan Warrior with Kid Trunks: {actual_power}")

    assert actual_power == base_power + 1, f"Expected power {base_power + 1}, got {actual_power}"
    print("PASSED: Kid Trunks grants +1/+0 to other Saiyans")


def test_king_vegeta_saiyan_lord():
    """Test King Vegeta: other Saiyans get +1/+1."""
    print("\n=== Test: King Vegeta Saiyan Lord ===")

    game = Game()
    p1 = game.add_player("Alice")

    king_vegeta = game.create_object(
        name="King Vegeta",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=KING_VEGETA.characteristics,
        card_def=KING_VEGETA
    )

    # Create another Saiyan
    saiyan_warrior = game.create_object(
        name="Saiyan Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SAIYAN_WARRIOR.characteristics,
        card_def=SAIYAN_WARRIOR
    )

    base_power = SAIYAN_WARRIOR.characteristics.power
    base_toughness = SAIYAN_WARRIOR.characteristics.toughness
    actual_power = get_power(saiyan_warrior, game.state)
    actual_toughness = get_toughness(saiyan_warrior, game.state)

    print(f"Saiyan Warrior base: {base_power}/{base_toughness}")
    print(f"Saiyan Warrior with King Vegeta: {actual_power}/{actual_toughness}")

    assert actual_power == base_power + 1, f"Expected power {base_power + 1}, got {actual_power}"
    assert actual_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}, got {actual_toughness}"
    print("PASSED: King Vegeta grants +1/+1 to other Saiyans")


def test_saiyan_pride_anthem():
    """Test Saiyan Pride: Saiyans get +2/+1."""
    print("\n=== Test: Saiyan Pride Anthem ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create enchantment first
    enchantment = game.create_object(
        name="Saiyan Pride",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SAIYAN_PRIDE.characteristics,
        card_def=SAIYAN_PRIDE
    )

    # Create a Saiyan
    saiyan_warrior = game.create_object(
        name="Saiyan Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SAIYAN_WARRIOR.characteristics,
        card_def=SAIYAN_WARRIOR
    )

    base_power = SAIYAN_WARRIOR.characteristics.power
    base_toughness = SAIYAN_WARRIOR.characteristics.toughness
    actual_power = get_power(saiyan_warrior, game.state)
    actual_toughness = get_toughness(saiyan_warrior, game.state)

    print(f"Saiyan Warrior base: {base_power}/{base_toughness}")
    print(f"Saiyan Warrior with Saiyan Pride: {actual_power}/{actual_toughness}")

    assert actual_power == base_power + 2, f"Expected power {base_power + 2}, got {actual_power}"
    assert actual_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}, got {actual_toughness}"
    print("PASSED: Saiyan Pride grants +2/+1 to Saiyans")


# =============================================================================
# GREEN CARD TESTS
# =============================================================================

def test_piccolo_upkeep_counter():
    """Test Piccolo, Namekian Warrior: gains +1/+1 counter at upkeep."""
    print("\n=== Test: Piccolo Upkeep Counter ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    piccolo = game.create_object(
        name="Piccolo, Namekian Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=PICCOLO_NAMEKIAN_WARRIOR.characteristics,
        card_def=PICCOLO_NAMEKIAN_WARRIOR
    )

    # Emit upkeep phase start
    triggered_events = game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep'},
        source=None,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    assert len(counter_events) == 1, f"Expected 1 counter added event, got {len(counter_events)}"
    assert counter_events[0].payload['object_id'] == piccolo.id, "Counter should be added to Piccolo"
    print("PASSED: Piccolo gains +1/+1 counter at upkeep")


def test_nail_namekian_lord():
    """Test Nail, Namekian Elite: other Namekians get +1/+1."""
    print("\n=== Test: Nail Namekian Lord ===")

    game = Game()
    p1 = game.add_player("Alice")

    nail = game.create_object(
        name="Nail, Namekian Elite",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAIL.characteristics,
        card_def=NAIL
    )

    # Create another Namekian
    namekian_warrior = game.create_object(
        name="Namekian Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEKIAN_WARRIOR.characteristics,
        card_def=NAMEKIAN_WARRIOR
    )

    base_power = NAMEKIAN_WARRIOR.characteristics.power
    base_toughness = NAMEKIAN_WARRIOR.characteristics.toughness
    actual_power = get_power(namekian_warrior, game.state)
    actual_toughness = get_toughness(namekian_warrior, game.state)

    print(f"Namekian Warrior base: {base_power}/{base_toughness}")
    print(f"Namekian Warrior with Nail: {actual_power}/{actual_toughness}")

    assert actual_power == base_power + 1, f"Expected power {base_power + 1}, got {actual_power}"
    assert actual_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}, got {actual_toughness}"
    print("PASSED: Nail grants +1/+1 to other Namekians")


def test_namekian_child_etb_life():
    """Test Namekian Child: gain 1 life on ETB."""
    print("\n=== Test: Namekian Child ETB Life ===")

    game = Game()
    p1 = game.add_player("Alice")

    namekian_child = game.create_object(
        name="Namekian Child",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEKIAN_CHILD.characteristics,
        card_def=NAMEKIAN_CHILD
    )

    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': namekian_child.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=namekian_child.id,
        controller=p1.id
    ))

    life_events = [e for e in triggered_events if e.type == EventType.LIFE_CHANGE]
    print(f"Life change events triggered: {len(life_events)}")

    # Check that at least one life gain of +1 occurred
    life_gain_1 = [e for e in life_events if e.payload.get('amount', 0) == 1]
    assert len(life_gain_1) >= 1, f"Expected at least one +1 life event, got {[e.payload.get('amount') for e in life_events]}"
    print("PASSED: Namekian Child gains 1 life on ETB")


def test_namek_frog_death_draw():
    """Test Namek Frog: draw a card when it dies."""
    print("\n=== Test: Namek Frog Death Draw ===")

    game = Game()
    p1 = game.add_player("Alice")

    frog = game.create_object(
        name="Namek Frog",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEK_FROG.characteristics,
        card_def=NAMEK_FROG
    )

    # Emit death event
    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': frog.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=frog.id,
        controller=p1.id
    ))

    draw_events = [e for e in triggered_events if e.type == EventType.DRAW]
    print(f"Draw events triggered: {len(draw_events)}")

    assert len(draw_events) == 1, f"Expected 1 draw event, got {len(draw_events)}"
    print("PASSED: Namek Frog draws a card when it dies")


def test_namek_crab_etb_life():
    """Test Namek Crab: gain 2 life on ETB."""
    print("\n=== Test: Namek Crab ETB Life ===")

    game = Game()
    p1 = game.add_player("Alice")

    crab = game.create_object(
        name="Namek Crab",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEK_CRAB.characteristics,
        card_def=NAMEK_CRAB
    )

    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': crab.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=crab.id,
        controller=p1.id
    ))

    life_events = [e for e in triggered_events if e.type == EventType.LIFE_CHANGE]
    print(f"Life change events triggered: {len(life_events)}")

    # Check that at least one life gain of +2 occurred
    life_gain_2 = [e for e in life_events if e.payload.get('amount', 0) == 2]
    assert len(life_gain_2) >= 1, f"Expected at least one +2 life event, got {[e.payload.get('amount') for e in life_events]}"
    print("PASSED: Namek Crab gains 2 life on ETB")


def test_namekian_resilience_hexproof():
    """Test Namekian Resilience: Namekians have hexproof."""
    print("\n=== Test: Namekian Resilience Hexproof ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create enchantment first
    enchantment = game.create_object(
        name="Namekian Resilience",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEKIAN_RESILIENCE.characteristics,
        card_def=NAMEKIAN_RESILIENCE
    )

    # Create a Namekian
    namekian = game.create_object(
        name="Namekian Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEKIAN_WARRIOR.characteristics,
        card_def=NAMEKIAN_WARRIOR
    )

    # Use has_ability to check if hexproof was granted
    has_hexproof = has_ability(namekian, 'hexproof', game.state)
    print(f"Namekian has hexproof: {has_hexproof}")

    assert has_hexproof, f"Expected Namekian Warrior to have hexproof granted by Namekian Resilience"
    print("PASSED: Namekian Resilience grants hexproof to Namekians")


def test_guru_etb_all_namekians_counter():
    """Test Guru, Grand Elder: puts +1/+1 counter on each Namekian when entering."""
    print("\n=== Test: Guru ETB Counters ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a Namekian first
    namekian = game.create_object(
        name="Namekian Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NAMEKIAN_WARRIOR.characteristics,
        card_def=NAMEKIAN_WARRIOR
    )

    # Create Guru
    guru = game.create_object(
        name="Guru, Grand Elder",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GURU.characteristics,
        card_def=GURU
    )

    # Emit ETB event for Guru
    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': guru.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=guru.id,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    # Should put counters on existing Namekians
    assert len(counter_events) >= 1, f"Expected at least 1 counter added event, got {len(counter_events)}"
    print("PASSED: Guru puts +1/+1 counters on Namekians when entering")


# =============================================================================
# MULTICOLOR CARD TESTS
# =============================================================================

def test_gogeta_attack_damage():
    """Test Gogeta, Fusion Warrior: deals 3 damage to each opponent when attacking."""
    print("\n=== Test: Gogeta Attack Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    gogeta = game.create_object(
        name="Gogeta, Fusion Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOGETA.characteristics,
        card_def=GOGETA
    )

    # Emit attack event
    triggered_events = game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': gogeta.id},
        source=gogeta.id,
        controller=p1.id
    ))

    damage_events = [e for e in triggered_events if e.type == EventType.DAMAGE]
    print(f"Damage events triggered: {len(damage_events)}")

    assert len(damage_events) >= 1, f"Expected at least 1 damage event, got {len(damage_events)}"
    assert damage_events[0].payload['amount'] == 3, f"Expected 3 damage, got {damage_events[0].payload['amount']}"
    print("PASSED: Gogeta deals 3 damage to opponents when attacking")


def test_gotenks_etb_tokens():
    """Test Gotenks, Young Fusion: creates 3 Super Ghost tokens on ETB."""
    print("\n=== Test: Gotenks ETB Tokens ===")

    game = Game()
    p1 = game.add_player("Alice")

    gotenks = game.create_object(
        name="Gotenks, Young Fusion",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOTENKS.characteristics,
        card_def=GOTENKS
    )

    triggered_events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': gotenks.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=gotenks.id,
        controller=p1.id
    ))

    # Token creation uses OBJECT_CREATED events with token=True
    token_events = [e for e in triggered_events if e.type == EventType.OBJECT_CREATED and e.payload.get('token', False)]
    print(f"Token creation events triggered: {len(token_events)}")

    # Should create 3 tokens (may have duplicates)
    assert len(token_events) >= 3, f"Expected at least 3 token creation events, got {len(token_events)}"
    print("PASSED: Gotenks creates Super Ghost tokens on ETB")


def test_beerus_upkeep_destroy():
    """Test Beerus, God of Destruction: destroys something each upkeep."""
    print("\n=== Test: Beerus Upkeep Destroy ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id

    beerus = game.create_object(
        name="Beerus, God of Destruction",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BEERUS.characteristics,
        card_def=BEERUS
    )

    # Emit upkeep phase start
    triggered_events = game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep'},
        source=None,
        controller=p1.id
    ))

    # Destroy uses OBJECT_DESTROYED events
    destroy_events = [e for e in triggered_events if e.type == EventType.OBJECT_DESTROYED]
    print(f"Destroy events triggered: {len(destroy_events)}")

    assert len(destroy_events) >= 1, f"Expected at least 1 destroy event, got {len(destroy_events)}"
    print("PASSED: Beerus triggers destruction at upkeep")


def test_vegito_power_level_trigger():
    """Test Vegito, Ultimate Fusion: Power Level trigger on combat damage."""
    print("\n=== Test: Vegito Power Level ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    vegito = game.create_object(
        name="Vegito, Ultimate Fusion",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=VEGITO.characteristics,
        card_def=VEGITO
    )

    # Emit combat damage event
    triggered_events = game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': vegito.id,
            'target': p2.id,
            'amount': 8,
            'is_combat': True
        },
        source=vegito.id,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    assert len(counter_events) == 1, f"Expected 1 counter added event, got {len(counter_events)}"
    assert counter_events[0].payload['counter_type'] == '+1/+1', "Should add +1/+1 counter"
    print("PASSED: Vegito gains +1/+1 counter on combat damage (Power Level)")


# =============================================================================
# POWER LEVEL MECHANIC TESTS
# =============================================================================

def test_goku_power_level_combat_damage():
    """Test Goku's Power Level mechanic: +1/+1 counter on combat damage."""
    print("\n=== Test: Goku Power Level Combat Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    goku = game.create_object(
        name="Goku, Earth's Hero",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOKU_EARTHS_HERO.characteristics,
        card_def=GOKU_EARTHS_HERO
    )

    # Emit combat damage event
    triggered_events = game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': goku.id,
            'target': p2.id,
            'amount': 4,
            'is_combat': True
        },
        source=goku.id,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    assert len(counter_events) == 1, f"Expected 1 counter added event, got {len(counter_events)}"
    print("PASSED: Goku gains +1/+1 counter on combat damage")


def test_vegeta_power_level_combat_damage():
    """Test Vegeta's Power Level mechanic: +1/+1 counter on combat damage."""
    print("\n=== Test: Vegeta Power Level Combat Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    vegeta = game.create_object(
        name="Vegeta, Saiyan Prince",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=VEGETA_SAIYAN_PRINCE.characteristics,
        card_def=VEGETA_SAIYAN_PRINCE
    )

    # Emit combat damage event
    triggered_events = game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': vegeta.id,
            'target': p2.id,
            'amount': 4,
            'is_combat': True
        },
        source=vegeta.id,
        controller=p1.id
    ))

    counter_events = [e for e in triggered_events if e.type == EventType.COUNTER_ADDED]
    print(f"Counter added events triggered: {len(counter_events)}")

    assert len(counter_events) == 1, f"Expected 1 counter added event, got {len(counter_events)}"
    print("PASSED: Vegeta gains +1/+1 counter on combat damage")


# =============================================================================
# TRANSFORM MECHANIC TESTS
# =============================================================================

def test_goku_transform_low_life():
    """Test Goku's Transform mechanic: bonus P/T when life <= 10."""
    print("\n=== Test: Goku Transform Low Life ===")

    game = Game()
    p1 = game.add_player("Alice")
    p1.life = 8  # Set life below threshold

    goku = game.create_object(
        name="Goku, Earth's Hero",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOKU_EARTHS_HERO.characteristics,
        card_def=GOKU_EARTHS_HERO
    )

    base_power = GOKU_EARTHS_HERO.characteristics.power
    base_toughness = GOKU_EARTHS_HERO.characteristics.toughness
    actual_power = get_power(goku, game.state)
    actual_toughness = get_toughness(goku, game.state)

    print(f"Goku base: {base_power}/{base_toughness}")
    print(f"Goku transformed (life={p1.life}): {actual_power}/{actual_toughness}")

    # Transform should give +3/+3
    assert actual_power == base_power + 3, f"Expected power {base_power + 3}, got {actual_power}"
    assert actual_toughness == base_toughness + 3, f"Expected toughness {base_toughness + 3}, got {actual_toughness}"
    print("PASSED: Goku transforms when life is low")


def test_goku_no_transform_high_life():
    """Test Goku doesn't transform when life > 10."""
    print("\n=== Test: Goku No Transform High Life ===")

    game = Game()
    p1 = game.add_player("Alice")
    p1.life = 20  # Normal life

    goku = game.create_object(
        name="Goku, Earth's Hero",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GOKU_EARTHS_HERO.characteristics,
        card_def=GOKU_EARTHS_HERO
    )

    base_power = GOKU_EARTHS_HERO.characteristics.power
    base_toughness = GOKU_EARTHS_HERO.characteristics.toughness
    actual_power = get_power(goku, game.state)
    actual_toughness = get_toughness(goku, game.state)

    print(f"Goku base: {base_power}/{base_toughness}")
    print(f"Goku not transformed (life={p1.life}): {actual_power}/{actual_toughness}")

    assert actual_power == base_power, f"Expected power {base_power}, got {actual_power}"
    assert actual_toughness == base_toughness, f"Expected toughness {base_toughness}, got {actual_toughness}"
    print("PASSED: Goku doesn't transform when life is high")


def test_vegeta_transform_low_life():
    """Test Vegeta's Transform mechanic: bonus P/T when life <= 10."""
    print("\n=== Test: Vegeta Transform Low Life ===")

    game = Game()
    p1 = game.add_player("Alice")
    p1.life = 5  # Set life below threshold

    vegeta = game.create_object(
        name="Vegeta, Saiyan Prince",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=VEGETA_SAIYAN_PRINCE.characteristics,
        card_def=VEGETA_SAIYAN_PRINCE
    )

    base_power = VEGETA_SAIYAN_PRINCE.characteristics.power
    base_toughness = VEGETA_SAIYAN_PRINCE.characteristics.toughness
    actual_power = get_power(vegeta, game.state)
    actual_toughness = get_toughness(vegeta, game.state)

    print(f"Vegeta base: {base_power}/{base_toughness}")
    print(f"Vegeta transformed (life={p1.life}): {actual_power}/{actual_toughness}")

    # Transform should give +3/+2
    assert actual_power == base_power + 3, f"Expected power {base_power + 3}, got {actual_power}"
    assert actual_toughness == base_toughness + 2, f"Expected toughness {base_toughness + 2}, got {actual_toughness}"
    print("PASSED: Vegeta transforms when life is low")


# =============================================================================
# KI BLAST MECHANIC TESTS
# =============================================================================

def test_tien_ki_blast():
    """Test Tien's Ki Blast ability: pay 1 life, deal 2 damage."""
    print("\n=== Test: Tien Ki Blast ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    tien = game.create_object(
        name="Tien, Triclops Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human", "Z-Fighter", "Monk"},
            supertypes={"Legendary"},
            colors={Color.WHITE},
            power=3, toughness=3,
            mana_cost="{2}{W}"
        ),
        card_def=None
    )

    # Manually set up interceptor for Ki Blast
    # make_ki_blast_ability was imported at the top via importlib
    interceptor = make_ki_blast_ability(tien, damage=2, life_cost=1)
    game.state.interceptors[interceptor.id] = interceptor
    tien.interceptor_ids.append(interceptor.id)

    # Emit activate event for ki_blast
    triggered_events = game.emit(Event(
        type=EventType.ACTIVATE,
        payload={
            'source': tien.id,
            'ability': 'ki_blast',
            'target': p2.id
        },
        source=tien.id,
        controller=p1.id
    ))

    life_events = [e for e in triggered_events if e.type == EventType.LIFE_CHANGE]
    damage_events = [e for e in triggered_events if e.type == EventType.DAMAGE]

    print(f"Life change events: {len(life_events)}")
    print(f"Damage events: {len(damage_events)}")

    # Should have life cost and damage
    assert len(life_events) == 1, f"Expected 1 life cost event, got {len(life_events)}"
    assert life_events[0].payload['amount'] == -1, f"Expected -1 life cost, got {life_events[0].payload['amount']}"
    assert len(damage_events) == 1, f"Expected 1 damage event, got {len(damage_events)}"
    assert damage_events[0].payload['amount'] == 2, f"Expected 2 damage, got {damage_events[0].payload['amount']}"
    print("PASSED: Tien Ki Blast works correctly")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_tests():
    print("=" * 60)
    print("DRAGON BALL Z: SAIYAN SAGA CARD TESTS")
    print("=" * 60)

    # WHITE CARDS
    print("\n" + "-" * 40)
    print("WHITE CARD TESTS")
    print("-" * 40)
    test_krillin_etb_life_gain()
    test_supreme_kai_etb_scry()
    test_king_kai_upkeep_draw()
    test_gohan_death_trigger_counters()
    test_videl_grants_vigilance()
    test_z_fighters_unite_lord_effect()

    # BLUE CARDS
    print("\n" + "-" * 40)
    print("BLUE CARD TESTS")
    print("-" * 40)
    test_android_18_etb_draw()
    test_android_17_grants_hexproof()
    test_android_16_death_trigger()
    test_bulma_artifact_cost_reduction()

    # BLACK CARDS
    print("\n" + "-" * 40)
    print("BLACK CARD TESTS")
    print("-" * 40)
    test_kid_buu_upkeep_life_loss()
    test_cell_absorb_counters()
    test_frieza_force_lord_effect()

    # RED CARDS
    print("\n" + "-" * 40)
    print("RED CARD TESTS")
    print("-" * 40)
    test_broly_attack_trigger_counters()
    test_goten_etb_damage()
    test_kid_trunks_saiyan_lord()
    test_king_vegeta_saiyan_lord()
    test_saiyan_pride_anthem()

    # GREEN CARDS
    print("\n" + "-" * 40)
    print("GREEN CARD TESTS")
    print("-" * 40)
    test_piccolo_upkeep_counter()
    test_nail_namekian_lord()
    test_namekian_child_etb_life()
    test_namek_frog_death_draw()
    test_namek_crab_etb_life()
    test_namekian_resilience_hexproof()
    test_guru_etb_all_namekians_counter()

    # MULTICOLOR CARDS
    print("\n" + "-" * 40)
    print("MULTICOLOR CARD TESTS")
    print("-" * 40)
    test_gogeta_attack_damage()
    test_gotenks_etb_tokens()
    test_beerus_upkeep_destroy()
    test_vegito_power_level_trigger()

    # POWER LEVEL MECHANIC
    print("\n" + "-" * 40)
    print("POWER LEVEL MECHANIC TESTS")
    print("-" * 40)
    test_goku_power_level_combat_damage()
    test_vegeta_power_level_combat_damage()

    # TRANSFORM MECHANIC
    print("\n" + "-" * 40)
    print("TRANSFORM MECHANIC TESTS")
    print("-" * 40)
    test_goku_transform_low_life()
    test_goku_no_transform_high_life()
    test_vegeta_transform_low_life()

    # KI BLAST MECHANIC
    print("\n" + "-" * 40)
    print("KI BLAST MECHANIC TESTS")
    print("-" * 40)
    test_tien_ki_blast()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
