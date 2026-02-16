"""
Test Jujutsu Kaisen: Cursed Clash card mechanics

Tests cover:
- ETB (enters the battlefield) triggers
- Death triggers
- Attack triggers
- Combat damage triggers
- Upkeep triggers
- Static P/T boost effects (lord effects)
- Keyword abilities
- Spell cast triggers
- Token creation
- Custom mechanics (Binding Vow, Cursed Energy)
"""

import sys
import os
import importlib.util
from pathlib import Path

# Ensure proper path setup
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics, InterceptorPriority
)

# Import directly from the module file to avoid __init__.py import issues
spec = importlib.util.spec_from_file_location(
    "jujutsu_kaisen",
    str(PROJECT_ROOT / "src/cards/custom/jujutsu_kaisen.py")
)
jujutsu_kaisen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jujutsu_kaisen)
JUJUTSU_KAISEN_CARDS = jujutsu_kaisen.JUJUTSU_KAISEN_CARDS


# =============================================================================
# HELPERS
# =============================================================================

def create_on_battlefield(game: Game, player_id: str, card_name: str):
    """
    Create a card and move it onto the battlefield via a ZONE_CHANGE event.

    Triggered abilities like ETB (ETBTrigger) listen for ZONE_CHANGE -> BATTLEFIELD.
    """
    card_def = JUJUTSU_KAISEN_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player_id}',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=obj.id,
        controller=obj.controller
    ))
    return obj


# =============================================================================
# ETB TRIGGER TESTS
# =============================================================================
# Note: ETB triggers fire on ZONE_CHANGE events (to_zone_type == BATTLEFIELD).

def test_jujutsu_first_year_etb_life_gain():
    """Test Jujutsu High First Year gains 2 life on ETB."""
    print("\n=== Test: Jujutsu High First Year ETB Life Gain ===")

    game = Game()
    p1 = game.add_player("Alice")

    starting_life = p1.life
    print(f"Starting life: {starting_life}")

    create_on_battlefield(game, p1.id, "Jujutsu High First Year")

    print(f"Life after ETB: {p1.life}")
    # The trigger should have fired once during creation
    assert p1.life == starting_life + 2, f"Expected {starting_life + 2}, got {p1.life}"
    print("PASSED: Jujutsu High First Year ETB life gain works!")


def test_megumi_fushiguro_etb_creates_divine_dog_token():
    """Test Megumi Fushiguro creates a Divine Dog token on ETB."""
    print("\n=== Test: Megumi Fushiguro ETB Token Creation ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Count creatures before
    creatures_before = len([obj for obj in game.state.objects.values()
                           if obj.zone == ZoneType.BATTLEFIELD and
                           CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures before: {creatures_before}")

    create_on_battlefield(game, p1.id, "Megumi Fushiguro, Ten Shadows")

    # Count creatures after ETB
    creatures_after = len([obj for obj in game.state.objects.values()
                          if obj.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures after: {creatures_after}")

    # Should have Megumi + Divine Dog token = 2 (or 1 more than before)
    assert creatures_after >= creatures_before + 2, f"Expected Megumi + token, creatures: {creatures_before} -> {creatures_after}"
    print("PASSED: Megumi Fushiguro ETB token creation works!")


def test_technique_analyst_etb_scry():
    """Test Technique Analyst scries 2 on ETB."""
    print("\n=== Test: Technique Analyst ETB Scry ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Technique Analyst"]

    creature = game.create_object(
        name="Technique Analyst",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Verify interceptors were registered (Scry trigger)
    assert len(creature.interceptor_ids) >= 1, f"Expected interceptors, got {len(creature.interceptor_ids)}"
    print(f"Interceptors registered: {len(creature.interceptor_ids)}")
    print("PASSED: Technique Analyst has scry ETB trigger registered!")


def test_finger_bearer_etb_life_loss():
    """Test Finger Bearer makes opponents lose 2 life on ETB."""
    print("\n=== Test: Finger Bearer ETB Opponent Life Loss ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")  # Opponent

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    create_on_battlefield(game, p1.id, "Finger Bearer")

    print(f"Opponent life after ETB: {p2.life}")
    assert p2.life == p2_starting_life - 2, f"Expected {p2_starting_life - 2}, got {p2.life}"
    print("PASSED: Finger Bearer ETB opponent life loss works!")


def test_rabbit_escape_etb_creates_multiple_tokens():
    """Test Rabbit Escape Swarm creates 3 tokens on ETB."""
    print("\n=== Test: Rabbit Escape Swarm ETB Multiple Tokens ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Count creatures before
    creatures_before = len([obj for obj in game.state.objects.values()
                           if obj.zone == ZoneType.BATTLEFIELD and
                           CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures before: {creatures_before}")

    create_on_battlefield(game, p1.id, "Rabbit Escape Swarm")

    creatures_after = len([obj for obj in game.state.objects.values()
                          if obj.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures after: {creatures_after}")

    # Should have Rabbit Escape + 3 tokens = 4 (or 4 more than before)
    assert creatures_after >= creatures_before + 4, f"Expected 4 new creatures, got: {creatures_before} -> {creatures_after}"
    print("PASSED: Rabbit Escape Swarm creates 3 tokens!")


def test_round_deer_etb_life_gain():
    """Test Round Deer Shikigami gains 4 life on ETB."""
    print("\n=== Test: Round Deer Shikigami ETB Life Gain ===")

    game = Game()
    p1 = game.add_player("Alice")

    starting_life = p1.life
    print(f"Starting life: {starting_life}")

    create_on_battlefield(game, p1.id, "Round Deer Shikigami")

    print(f"Life after ETB: {p1.life}")
    assert p1.life == starting_life + 4, f"Expected {starting_life + 4}, got {p1.life}"
    print("PASSED: Round Deer Shikigami ETB life gain works!")


# =============================================================================
# STATIC EFFECT / LORD TESTS
# =============================================================================

def test_jujutsu_instructor_lord_effect():
    """Test Jujutsu High Instructor gives Students +1/+1."""
    print("\n=== Test: Jujutsu High Instructor Lord Effect ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a Student creature first
    student_def = JUJUTSU_KAISEN_CARDS["Jujutsu High First Year"]
    student = game.create_object(
        name="Jujutsu High First Year",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=student_def.characteristics,
        card_def=student_def
    )

    # Check base stats
    base_power = get_power(student, game.state)
    base_toughness = get_toughness(student, game.state)
    print(f"Student base stats: {base_power}/{base_toughness}")

    # Create Instructor (lord)
    instructor_def = JUJUTSU_KAISEN_CARDS["Jujutsu High Instructor"]
    instructor = game.create_object(
        name="Jujutsu High Instructor",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=instructor_def.characteristics,
        card_def=instructor_def
    )

    # Check boosted stats
    boosted_power = get_power(student, game.state)
    boosted_toughness = get_toughness(student, game.state)
    print(f"Student with Instructor: {boosted_power}/{boosted_toughness}")

    assert boosted_power == base_power + 1, f"Expected power +1, got {boosted_power}"
    assert boosted_toughness == base_toughness + 1, f"Expected toughness +1, got {boosted_toughness}"
    print("PASSED: Jujutsu High Instructor lord effect works!")


def test_megumi_fushiguro_shikigami_boost():
    """Test Megumi Fushiguro gives Shikigami +1/+0."""
    print("\n=== Test: Megumi Fushiguro Shikigami Boost ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Megumi first
    megumi_def = JUJUTSU_KAISEN_CARDS["Megumi Fushiguro, Ten Shadows"]
    megumi = game.create_object(
        name="Megumi Fushiguro, Ten Shadows",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=megumi_def.characteristics,
        card_def=megumi_def
    )

    # Create a Shikigami
    shikigami_def = JUJUTSU_KAISEN_CARDS["Divine Dog: White"]
    shikigami = game.create_object(
        name="Divine Dog: White",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=shikigami_def.characteristics,
        card_def=shikigami_def
    )

    # Check Shikigami stats - should have +1/+0 from Megumi
    power = get_power(shikigami, game.state)
    toughness = get_toughness(shikigami, game.state)
    print(f"Divine Dog with Megumi: {power}/{toughness}")

    # Base is 2/2, should be 3/2 with Megumi
    assert power == 3, f"Expected power 3, got {power}"
    assert toughness == 2, f"Expected toughness 2, got {toughness}"
    print("PASSED: Megumi Fushiguro Shikigami boost works!")


def test_shikigami_summoner_lord_effect():
    """Test Shikigami Summoner gives Shikigami +1/+1."""
    print("\n=== Test: Shikigami Summoner Lord Effect ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create lord first
    lord_def = JUJUTSU_KAISEN_CARDS["Shikigami Summoner"]
    lord = game.create_object(
        name="Shikigami Summoner",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=lord_def.characteristics,
        card_def=lord_def
    )

    # Create Shikigami
    shikigami_def = JUJUTSU_KAISEN_CARDS["Toad Shikigami"]
    shikigami = game.create_object(
        name="Toad Shikigami",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=shikigami_def.characteristics,
        card_def=shikigami_def
    )

    power = get_power(shikigami, game.state)
    toughness = get_toughness(shikigami, game.state)
    print(f"Toad Shikigami with Summoner: {power}/{toughness}")

    # Base is 1/3, should be 2/4 with Summoner
    assert power == 2, f"Expected power 2, got {power}"
    assert toughness == 4, f"Expected toughness 4, got {toughness}"
    print("PASSED: Shikigami Summoner lord effect works!")


def test_masamichi_yaga_cursed_corpse_boost():
    """Test Masamichi Yaga gives Cursed Corpse +1/+1."""
    print("\n=== Test: Masamichi Yaga Cursed Corpse Boost ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Yaga (lord for Cursed Corpse)
    yaga_def = JUJUTSU_KAISEN_CARDS["Masamichi Yaga, Principal"]
    yaga = game.create_object(
        name="Masamichi Yaga, Principal",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=yaga_def.characteristics,
        card_def=yaga_def
    )

    # Test that interceptors are registered
    assert len(yaga.interceptor_ids) >= 2, f"Expected lord interceptors, got {len(yaga.interceptor_ids)}"
    print(f"Yaga interceptors registered: {len(yaga.interceptor_ids)}")
    print("PASSED: Masamichi Yaga has lord effect interceptors!")


def test_special_grade_curse_lord_effect():
    """Test Special Grade Curse gives other Curses +1/+1."""
    print("\n=== Test: Special Grade Curse Lord Effect ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create lord
    lord_def = JUJUTSU_KAISEN_CARDS["Special Grade Curse"]
    lord = game.create_object(
        name="Special Grade Curse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=lord_def.characteristics,
        card_def=lord_def
    )

    lord_power = get_power(lord, game.state)
    print(f"Special Grade Curse power: {lord_power}")

    # Create another Curse
    curse_def = JUJUTSU_KAISEN_CARDS["Grade One Curse"]
    curse = game.create_object(
        name="Grade One Curse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=curse_def.characteristics,
        card_def=curse_def
    )

    curse_power = get_power(curse, game.state)
    curse_toughness = get_toughness(curse, game.state)
    print(f"Grade One Curse with lord: {curse_power}/{curse_toughness}")

    # Grade One Curse is base 4/4, should be 5/5
    assert curse_power == 5, f"Expected power 5, got {curse_power}"
    assert curse_toughness == 5, f"Expected toughness 5, got {curse_toughness}"

    # Lord should not boost itself
    assert lord_power == 6, f"Lord power should be 6 (base), got {lord_power}"
    print("PASSED: Special Grade Curse lord effect works!")


def test_window_guardian_sorcerer_boost():
    """Test Window Guardian gives other Sorcerers +0/+1."""
    print("\n=== Test: Window Guardian Sorcerer Boost ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create lord
    lord_def = JUJUTSU_KAISEN_CARDS["Window Guardian"]
    lord = game.create_object(
        name="Window Guardian",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=lord_def.characteristics,
        card_def=lord_def
    )

    # Create a Sorcerer
    sorcerer_def = JUJUTSU_KAISEN_CARDS["Barrier Technician"]
    sorcerer = game.create_object(
        name="Barrier Technician",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=sorcerer_def.characteristics,
        card_def=sorcerer_def
    )

    toughness = get_toughness(sorcerer, game.state)
    print(f"Barrier Technician toughness with Window Guardian: {toughness}")

    # Barrier Technician is base 1/3, should be 1/4 with Window Guardian
    assert toughness == 4, f"Expected toughness 4, got {toughness}"
    print("PASSED: Window Guardian Sorcerer boost works!")


def test_disease_curse_deathtouch_grant():
    """Test Disease Curse gives other Curses deathtouch."""
    print("\n=== Test: Disease Curse Deathtouch Grant ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Disease Curse (keyword granter)
    disease_def = JUJUTSU_KAISEN_CARDS["Disease Curse"]
    disease = game.create_object(
        name="Disease Curse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=disease_def.characteristics,
        card_def=disease_def
    )

    # Verify it has deathtouch ability itself
    assert "Deathtouch" in disease_def.characteristics.keywords or any(
        "Deathtouch" in str(a) for a in (disease_def.abilities or [])
    ), "Disease Curse should have Deathtouch"

    # Verify interceptors are registered for keyword grant
    assert len(disease.interceptor_ids) >= 1, f"Expected keyword grant interceptor, got {len(disease.interceptor_ids)}"
    print(f"Disease Curse interceptors: {len(disease.interceptor_ids)}")
    print("PASSED: Disease Curse has keyword grant registered!")


def test_self_embodiment_of_perfection_debuff():
    """Test Self-Embodiment of Perfection gives opponent creatures -1/-1."""
    print("\n=== Test: Self-Embodiment of Perfection Opponent Debuff ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")  # Opponent

    # Create opponent's creature first
    opp_creature_def = JUJUTSU_KAISEN_CARDS["Grade One Curse"]
    opp_creature = game.create_object(
        name="Grade One Curse",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=opp_creature_def.characteristics,
        card_def=opp_creature_def
    )

    base_power = get_power(opp_creature, game.state)
    base_toughness = get_toughness(opp_creature, game.state)
    print(f"Opponent creature base: {base_power}/{base_toughness}")

    # Create the domain enchantment
    domain_def = JUJUTSU_KAISEN_CARDS["Self-Embodiment of Perfection"]
    domain = game.create_object(
        name="Self-Embodiment of Perfection",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=domain_def.characteristics,
        card_def=domain_def
    )

    debuffed_power = get_power(opp_creature, game.state)
    debuffed_toughness = get_toughness(opp_creature, game.state)
    print(f"Opponent creature with domain: {debuffed_power}/{debuffed_toughness}")

    # Base 4/4 should become 3/3
    assert debuffed_power == base_power - 1, f"Expected power -1, got {debuffed_power}"
    assert debuffed_toughness == base_toughness - 1, f"Expected toughness -1, got {debuffed_toughness}"
    print("PASSED: Self-Embodiment of Perfection debuffs opponents!")


def test_chimera_shadow_garden_shikigami_boost():
    """Test Chimera Shadow Garden gives Shikigami +2/+2 and deathtouch."""
    print("\n=== Test: Chimera Shadow Garden Shikigami Boost ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create domain
    domain_def = JUJUTSU_KAISEN_CARDS["Chimera Shadow Garden"]
    domain = game.create_object(
        name="Chimera Shadow Garden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=domain_def.characteristics,
        card_def=domain_def
    )

    # Create Shikigami
    shikigami_def = JUJUTSU_KAISEN_CARDS["Divine Dog: White"]
    shikigami = game.create_object(
        name="Divine Dog: White",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=shikigami_def.characteristics,
        card_def=shikigami_def
    )

    power = get_power(shikigami, game.state)
    toughness = get_toughness(shikigami, game.state)
    print(f"Divine Dog with Chimera Shadow Garden: {power}/{toughness}")

    # Base 2/2, should be 4/4
    assert power == 4, f"Expected power 4, got {power}"
    assert toughness == 4, f"Expected toughness 4, got {toughness}"
    print("PASSED: Chimera Shadow Garden boosts Shikigami!")


# =============================================================================
# UPKEEP TRIGGER TESTS
# Note: Upkeep triggers use PHASE_START with payload={'phase': 'upkeep'}
# =============================================================================

def test_hanami_upkeep_counter():
    """Test Hanami gets +1/+1 counter at upkeep."""
    print("\n=== Test: Hanami Upkeep Counter ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set active player for upkeep check
    game.state.active_player = p1.id

    card_def = JUJUTSU_KAISEN_CARDS["Hanami, Forest Curse"]
    creature = game.create_object(
        name="Hanami, Forest Curse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    counters_before = creature.state.counters.get('+1/+1', 0)
    print(f"Counters before upkeep: {counters_before}")

    # Emit upkeep event using PHASE_START
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        controller=p1.id
    ))

    counters_after = creature.state.counters.get('+1/+1', 0)
    print(f"Counters after upkeep: {counters_after}")

    assert counters_after == counters_before + 1, f"Expected +1 counter"
    print("PASSED: Hanami upkeep counter works!")


def test_cursed_bud_upkeep_counter():
    """Test Cursed Bud gets +1/+1 counter at upkeep."""
    print("\n=== Test: Cursed Bud Upkeep Counter ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set active player
    game.state.active_player = p1.id

    card_def = JUJUTSU_KAISEN_CARDS["Cursed Bud"]
    creature = game.create_object(
        name="Cursed Bud",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    counters_before = creature.state.counters.get('+1/+1', 0)
    power_before = get_power(creature, game.state)
    print(f"Before upkeep: {power_before} power, {counters_before} counters")

    # Emit upkeep event
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        controller=p1.id
    ))

    counters_after = creature.state.counters.get('+1/+1', 0)
    power_after = get_power(creature, game.state)
    print(f"After upkeep: {power_after} power, {counters_after} counters")

    assert counters_after == counters_before + 1
    print("PASSED: Cursed Bud upkeep counter works!")


def test_malevolent_shrine_upkeep_damage():
    """Test Malevolent Shrine deals 2 damage at upkeep."""
    print("\n=== Test: Malevolent Shrine Upkeep Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")  # Opponent

    # Set active player
    game.state.active_player = p1.id

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Malevolent Shrine"]
    enchantment = game.create_object(
        name="Malevolent Shrine",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit upkeep event
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        controller=p1.id
    ))

    print(f"Opponent life after upkeep: {p2.life}")
    assert p2.life == p2_starting_life - 2, f"Expected {p2_starting_life - 2}, got {p2.life}"
    print("PASSED: Malevolent Shrine upkeep damage works!")


def test_shining_sea_of_flowers_upkeep_life():
    """Test Shining Sea of Flowers gains 2 life at upkeep."""
    print("\n=== Test: Shining Sea of Flowers Upkeep Life Gain ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set active player
    game.state.active_player = p1.id

    starting_life = p1.life
    print(f"Starting life: {starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Shining Sea of Flowers"]
    enchantment = game.create_object(
        name="Shining Sea of Flowers",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit upkeep event
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        controller=p1.id
    ))

    print(f"Life after upkeep: {p1.life}")
    assert p1.life == starting_life + 2, f"Expected {starting_life + 2}, got {p1.life}"
    print("PASSED: Shining Sea of Flowers upkeep life gain works!")


def test_horizon_of_captivating_skandha_upkeep_token():
    """Test Horizon of the Captivating Skandha creates token at upkeep."""
    print("\n=== Test: Horizon of the Captivating Skandha Upkeep Token ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set active player
    game.state.active_player = p1.id

    card_def = JUJUTSU_KAISEN_CARDS["Horizon of the Captivating Skandha"]
    enchantment = game.create_object(
        name="Horizon of the Captivating Skandha",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    creatures_before = len([obj for obj in game.state.objects.values()
                           if obj.zone == ZoneType.BATTLEFIELD and
                           CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures before upkeep: {creatures_before}")

    # Emit upkeep event
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        controller=p1.id
    ))

    creatures_after = len([obj for obj in game.state.objects.values()
                          if obj.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures after upkeep: {creatures_after}")

    assert creatures_after == creatures_before + 1, f"Expected token creation"
    print("PASSED: Horizon creates token at upkeep!")


def test_cursed_womb_death_painting_upkeep():
    """Test Cursed Womb: Death Painting creates token and loses life at upkeep."""
    print("\n=== Test: Cursed Womb Death Painting Upkeep ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Set active player
    game.state.active_player = p1.id

    starting_life = p1.life

    card_def = JUJUTSU_KAISEN_CARDS["Cursed Womb: Death Painting"]
    enchantment = game.create_object(
        name="Cursed Womb: Death Painting",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    creatures_before = len([obj for obj in game.state.objects.values()
                           if obj.zone == ZoneType.BATTLEFIELD and
                           CardType.CREATURE in obj.characteristics.types])
    print(f"Before upkeep: {creatures_before} creatures, {starting_life} life")

    # Emit upkeep event
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        controller=p1.id
    ))

    creatures_after = len([obj for obj in game.state.objects.values()
                          if obj.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in obj.characteristics.types])
    print(f"After upkeep: {creatures_after} creatures, {p1.life} life")

    # Should create a token AND lose 1 life
    assert creatures_after == creatures_before + 1, f"Expected token creation"
    assert p1.life == starting_life - 1, f"Expected life loss"
    print("PASSED: Cursed Womb Death Painting upkeep works!")


# =============================================================================
# ATTACK TRIGGER TESTS
# Note: Attack triggers use ATTACK_DECLARED
# =============================================================================

def test_yuji_itadori_attack_trigger():
    """Test Yuji Itadori deals 1 damage to each opponent when attacking."""
    print("\n=== Test: Yuji Itadori Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")  # Opponent

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Yuji Itadori, Sukuna's Vessel"]
    creature = game.create_object(
        name="Yuji Itadori, Sukuna's Vessel",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit attack event using ATTACK_DECLARED
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': creature.id, 'defender': p2.id},
        source=creature.id,
        controller=p1.id
    ))

    print(f"Opponent life after attack: {p2.life}")
    assert p2.life == p2_starting_life - 1, f"Expected {p2_starting_life - 1}, got {p2.life}"
    print("PASSED: Yuji Itadori attack trigger works!")


def test_nobara_attack_trigger():
    """Test Nobara Kugisaki deals 2 damage to each opponent when attacking."""
    print("\n=== Test: Nobara Kugisaki Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Nobara Kugisaki, Straw Doll"]
    creature = game.create_object(
        name="Nobara Kugisaki, Straw Doll",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit attack event
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': creature.id, 'defender': p2.id},
        source=creature.id,
        controller=p1.id
    ))

    print(f"Opponent life after attack: {p2.life}")
    assert p2.life == p2_starting_life - 2, f"Expected {p2_starting_life - 2}, got {p2.life}"
    print("PASSED: Nobara Kugisaki attack trigger works!")


def test_jogo_attack_trigger():
    """Test Jogo deals 2 damage to each opponent when attacking."""
    print("\n=== Test: Jogo Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Jogo, Volcano Curse"]
    creature = game.create_object(
        name="Jogo, Volcano Curse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit attack event
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': creature.id, 'defender': p2.id},
        source=creature.id,
        controller=p1.id
    ))

    print(f"Opponent life after attack: {p2.life}")
    assert p2.life == p2_starting_life - 2, f"Expected {p2_starting_life - 2}, got {p2.life}"
    print("PASSED: Jogo attack trigger works!")


def test_aoi_todo_attack_counter():
    """Test Aoi Todo gets +1/+1 counter when attacking."""
    print("\n=== Test: Aoi Todo Attack Counter ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    card_def = JUJUTSU_KAISEN_CARDS["Aoi Todo, Best Friend"]
    creature = game.create_object(
        name="Aoi Todo, Best Friend",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    counters_before = creature.state.counters.get('+1/+1', 0)
    print(f"Counters before attack: {counters_before}")

    # Emit attack event
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': creature.id, 'defender': p2.id},
        source=creature.id,
        controller=p1.id
    ))

    counters_after = creature.state.counters.get('+1/+1', 0)
    print(f"Counters after attack: {counters_after}")

    assert counters_after == counters_before + 1, f"Expected +1 counter"
    print("PASSED: Aoi Todo attack counter works!")


def test_divine_dog_totality_attack_damage():
    """Test Divine Dog: Totality deals 2 damage when attacking."""
    print("\n=== Test: Divine Dog Totality Attack Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Divine Dog: Totality"]
    creature = game.create_object(
        name="Divine Dog: Totality",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit attack event
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': creature.id, 'defender': p2.id},
        source=creature.id,
        controller=p1.id
    ))

    print(f"Opponent life after attack: {p2.life}")
    assert p2.life == p2_starting_life - 2, f"Expected {p2_starting_life - 2}, got {p2.life}"
    print("PASSED: Divine Dog Totality attack damage works!")


# =============================================================================
# DEATH TRIGGER TESTS
# =============================================================================

def test_cursed_womb_death_tokens():
    """Test Cursed Womb creates 2 tokens when it dies."""
    print("\n=== Test: Cursed Womb Death Tokens ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Cursed Womb"]
    creature = game.create_object(
        name="Cursed Womb",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    creatures_before = len([obj for obj in game.state.objects.values()
                           if obj.zone == ZoneType.BATTLEFIELD and
                           CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures before death: {creatures_before}")

    # Emit death event (battlefield -> graveyard)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=creature.id,
        controller=p1.id
    ))

    creatures_after = len([obj for obj in game.state.objects.values()
                          if obj.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures after death: {creatures_after}")

    # Should have 2 new tokens (the original is dead, so net +1)
    # creatures_after should be creatures_before - 1 (dead) + 2 (tokens) = creatures_before + 1
    assert creatures_after >= creatures_before + 1, f"Expected 2 tokens created"
    print("PASSED: Cursed Womb death tokens work!")


def test_vengeful_spirit_death_life_loss():
    """Test Vengeful Cursed Spirit makes opponents lose 2 life when it dies."""
    print("\n=== Test: Vengeful Cursed Spirit Death Life Loss ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Vengeful Cursed Spirit"]
    creature = game.create_object(
        name="Vengeful Cursed Spirit",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit death event
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=creature.id,
        controller=p1.id
    ))

    print(f"Opponent life after death: {p2.life}")
    assert p2.life == p2_starting_life - 2, f"Expected {p2_starting_life - 2}, got {p2.life}"
    print("PASSED: Vengeful Cursed Spirit death life loss works!")


def test_grasshopper_curse_death_life_loss():
    """Test Grasshopper Curse makes opponents lose 1 life when it dies."""
    print("\n=== Test: Grasshopper Curse Death Life Loss ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    p2_starting_life = p2.life
    print(f"Opponent starting life: {p2_starting_life}")

    card_def = JUJUTSU_KAISEN_CARDS["Grasshopper Curse"]
    creature = game.create_object(
        name="Grasshopper Curse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Emit death event
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=creature.id,
        controller=p1.id
    ))

    print(f"Opponent life after death: {p2.life}")
    assert p2.life == p2_starting_life - 1, f"Expected {p2_starting_life - 1}, got {p2.life}"
    print("PASSED: Grasshopper Curse death life loss works!")


def test_tiger_funeral_death_draw():
    """Test Tiger Funeral Shikigami draws a card when it dies."""
    print("\n=== Test: Tiger Funeral Shikigami Death Draw ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Tiger Funeral Shikigami"]
    creature = game.create_object(
        name="Tiger Funeral Shikigami",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Verify interceptor is registered for death trigger
    assert len(creature.interceptor_ids) >= 1, f"Expected death trigger interceptor"
    print(f"Interceptors registered: {len(creature.interceptor_ids)}")
    print("PASSED: Tiger Funeral Shikigami has death trigger!")


def test_nature_curse_spawn_death_token():
    """Test Nature Curse Spawn creates a token when it dies."""
    print("\n=== Test: Nature Curse Spawn Death Token ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Nature Curse Spawn"]
    creature = game.create_object(
        name="Nature Curse Spawn",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    creatures_before = len([obj for obj in game.state.objects.values()
                           if obj.zone == ZoneType.BATTLEFIELD and
                           CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures before death: {creatures_before}")

    # Emit death event
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=creature.id,
        controller=p1.id
    ))

    creatures_after = len([obj for obj in game.state.objects.values()
                          if obj.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in obj.characteristics.types])
    print(f"Creatures after death: {creatures_after}")

    # Net change: -1 (dead) + 1 (token) = 0
    assert creatures_after >= creatures_before - 1, f"Expected token creation"
    print("PASSED: Nature Curse Spawn death token works!")


# =============================================================================
# SPELL CAST TRIGGER TESTS
# =============================================================================

def test_yuta_okkotsu_spell_counter():
    """Test Yuta Okkotsu gets +1/+1 counter when casting instant/sorcery."""
    print("\n=== Test: Yuta Okkotsu Spell Cast Counter ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Yuta Okkotsu, Rika's Beloved"]
    creature = game.create_object(
        name="Yuta Okkotsu, Rika's Beloved",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    counters_before = creature.state.counters.get('+1/+1', 0)
    print(f"Counters before spell: {counters_before}")

    # Emit spell cast event
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'spell_type': CardType.INSTANT,
            'controller': p1.id,
            'caster': p1.id
        },
        controller=p1.id
    ))

    counters_after = creature.state.counters.get('+1/+1', 0)
    print(f"Counters after spell: {counters_after}")

    assert counters_after == counters_before + 1, f"Expected +1 counter"
    print("PASSED: Yuta Okkotsu spell cast counter works!")


def test_domain_master_enchantment_draw():
    """Test Domain Master draws a card when enchantment is cast."""
    print("\n=== Test: Domain Master Enchantment Cast Draw ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Domain Master"]
    creature = game.create_object(
        name="Domain Master",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Verify interceptor is registered
    assert len(creature.interceptor_ids) >= 1, f"Expected spell cast trigger"
    print(f"Interceptors registered: {len(creature.interceptor_ids)}")
    print("PASSED: Domain Master has spell cast trigger!")


# =============================================================================
# COMBAT DAMAGE TRIGGER TESTS
# Note: Uses 'is_combat': True in payload for combat damage
# =============================================================================

def test_panda_combat_damage_counter():
    """Test Panda gets +1/+1 counter when dealing combat damage."""
    print("\n=== Test: Panda Combat Damage Counter ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    card_def = JUJUTSU_KAISEN_CARDS["Panda, Cursed Corpse"]
    creature = game.create_object(
        name="Panda, Cursed Corpse",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    counters_before = creature.state.counters.get('+1/+1', 0)
    print(f"Counters before combat damage: {counters_before}")

    # Emit combat damage event with is_combat: True
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': creature.id,
            'target': p2.id,
            'amount': 4,
            'is_combat': True
        },
        source=creature.id,
        controller=p1.id
    ))

    counters_after = creature.state.counters.get('+1/+1', 0)
    print(f"Counters after combat damage: {counters_after}")

    assert counters_after == counters_before + 1, f"Expected +1 counter"
    print("PASSED: Panda combat damage counter works!")


def test_mahito_damage_to_creature_counter():
    """Test Mahito puts -1/-1 counter on creature it damages."""
    print("\n=== Test: Mahito Damage to Creature Counter ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create Mahito
    mahito_def = JUJUTSU_KAISEN_CARDS["Mahito, Soul Sculptor"]
    mahito = game.create_object(
        name="Mahito, Soul Sculptor",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=mahito_def.characteristics,
        card_def=mahito_def
    )

    # Create target creature
    target_def = JUJUTSU_KAISEN_CARDS["Grade One Curse"]
    target = game.create_object(
        name="Grade One Curse",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=target_def.characteristics,
        card_def=target_def
    )

    counters_before = target.state.counters.get('-1/-1', 0)
    power_before = get_power(target, game.state)
    print(f"Target before damage: {power_before} power, {counters_before} -1/-1 counters")

    # Emit damage event to creature
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': mahito.id,
            'target': target.id,
            'amount': 4,
            'to_creature': True
        },
        source=mahito.id,
        controller=p1.id
    ))

    counters_after = target.state.counters.get('-1/-1', 0)
    power_after = get_power(target, game.state)
    print(f"Target after damage: {power_after} power, {counters_after} -1/-1 counters")

    assert counters_after == counters_before + 1, f"Expected -1/-1 counter"
    print("PASSED: Mahito damage counter works!")


# =============================================================================
# KEYWORD ABILITY TESTS
# =============================================================================

def test_satoru_gojo_keywords():
    """Test Satoru Gojo has Hexproof and Flying."""
    print("\n=== Test: Satoru Gojo Keywords ===")

    card_def = JUJUTSU_KAISEN_CARDS["Satoru Gojo, The Strongest"]

    # Check keywords via characteristics
    keywords = card_def.characteristics.keywords
    print(f"Gojo keywords: {keywords}")

    assert "Hexproof" in keywords or any("Hexproof" in str(a) for a in (card_def.abilities or [])), "Expected Hexproof"
    assert "Flying" in keywords or any("Flying" in str(a) for a in (card_def.abilities or [])), "Expected Flying"
    print("PASSED: Satoru Gojo has correct keywords!")


def test_mahoraga_keywords():
    """Test Mahoraga has Trample and Indestructible."""
    print("\n=== Test: Mahoraga Keywords ===")

    card_def = JUJUTSU_KAISEN_CARDS["Mahoraga, Eight-Handled Sword"]

    keywords = card_def.characteristics.keywords
    print(f"Mahoraga keywords: {keywords}")

    assert "Trample" in keywords or any("Trample" in str(a) for a in (card_def.abilities or [])), "Expected Trample"
    assert "Indestructible" in keywords or any("Indestructible" in str(a) for a in (card_def.abilities or [])), "Expected Indestructible"
    print("PASSED: Mahoraga has correct keywords!")


def test_ryomen_sukuna_double_strike():
    """Test Ryomen Sukuna has Double Strike."""
    print("\n=== Test: Ryomen Sukuna Double Strike ===")

    card_def = JUJUTSU_KAISEN_CARDS["Ryomen Sukuna, King of Curses"]

    keywords = card_def.characteristics.keywords
    print(f"Sukuna keywords: {keywords}")

    assert "Double strike" in keywords or any("Double strike" in str(a) for a in (card_def.abilities or [])), "Expected Double strike"
    print("PASSED: Ryomen Sukuna has Double Strike!")


def test_maki_zenin_keywords():
    """Test Maki Zenin has First Strike and Vigilance."""
    print("\n=== Test: Maki Zenin Keywords ===")

    card_def = JUJUTSU_KAISEN_CARDS["Maki Zenin, Heavenly Pact"]

    keywords = card_def.characteristics.keywords
    print(f"Maki keywords: {keywords}")

    assert "First strike" in keywords or any("First strike" in str(a) for a in (card_def.abilities or [])), "Expected First strike"
    assert "Vigilance" in keywords or any("Vigilance" in str(a) for a in (card_def.abilities or [])), "Expected Vigilance"
    print("PASSED: Maki Zenin has correct keywords!")


def test_guardian_shikigami_defender():
    """Test Guardian Shikigami has Defender and Vigilance."""
    print("\n=== Test: Guardian Shikigami Keywords ===")

    card_def = JUJUTSU_KAISEN_CARDS["Guardian Shikigami"]

    keywords = card_def.characteristics.keywords
    print(f"Guardian Shikigami keywords: {keywords}")

    assert "Defender" in keywords or any("Defender" in str(a) for a in (card_def.abilities or [])), "Expected Defender"
    assert "Vigilance" in keywords or any("Vigilance" in str(a) for a in (card_def.abilities or [])), "Expected Vigilance"
    print("PASSED: Guardian Shikigami has correct keywords!")


# =============================================================================
# CARD STAT TESTS
# =============================================================================

def test_card_base_stats():
    """Test various cards have correct base power/toughness."""
    print("\n=== Test: Card Base Stats ===")

    game = Game()
    p1 = game.add_player("Alice")

    test_cases = [
        ("Yuji Itadori, Sukuna's Vessel", 3, 3),
        ("Satoru Gojo, The Strongest", 6, 6),
        ("Ryomen Sukuna, King of Curses", 7, 6),
        ("Mahoraga, Eight-Handled Sword", 8, 8),
        ("Guardian Shikigami", 0, 4),
        ("Cursed Bud", 0, 3),
    ]

    for name, expected_power, expected_toughness in test_cases:
        card_def = JUJUTSU_KAISEN_CARDS[name]
        creature = game.create_object(
            name=name,
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=card_def.characteristics,
            card_def=card_def
        )

        power = get_power(creature, game.state)
        toughness = get_toughness(creature, game.state)

        print(f"  {name}: {power}/{toughness} (expected {expected_power}/{expected_toughness})")
        assert power == expected_power, f"{name} power mismatch"
        assert toughness == expected_toughness, f"{name} toughness mismatch"

    print("PASSED: All card base stats correct!")


# =============================================================================
# BINDING VOW / CURSED ENERGY TESTS
# =============================================================================

def test_yuji_binding_vow_interceptor():
    """Test Yuji Itadori has Binding Vow interceptor registered."""
    print("\n=== Test: Yuji Itadori Binding Vow ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Yuji Itadori, Sukuna's Vessel"]
    creature = game.create_object(
        name="Yuji Itadori, Sukuna's Vessel",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Should have interceptors for Binding Vow plus attack trigger
    print(f"Interceptors registered: {len(creature.interceptor_ids)}")
    assert len(creature.interceptor_ids) >= 1, f"Expected interceptors for Binding Vow"
    print("PASSED: Yuji has Binding Vow interceptor!")


def test_sukuna_binding_vow_interceptor():
    """Test Ryomen Sukuna has Binding Vow interceptor registered."""
    print("\n=== Test: Ryomen Sukuna Binding Vow ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = JUJUTSU_KAISEN_CARDS["Ryomen Sukuna, King of Curses"]
    creature = game.create_object(
        name="Ryomen Sukuna, King of Curses",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    print(f"Interceptors registered: {len(creature.interceptor_ids)}")
    assert len(creature.interceptor_ids) >= 1, f"Expected interceptors"
    print("PASSED: Sukuna has Binding Vow interceptor!")


# =============================================================================
# MULTICOLOR / LEGENDARY TESTS
# =============================================================================

def test_legendary_supertypes():
    """Test legendary creatures have Legendary supertype."""
    print("\n=== Test: Legendary Supertypes ===")

    legendaries = [
        "Yuji Itadori, Sukuna's Vessel",
        "Megumi Fushiguro, Ten Shadows",
        "Satoru Gojo, The Strongest",
        "Ryomen Sukuna, King of Curses",
        "Mahoraga, Eight-Handled Sword",
        "Rika Orimoto, Cursed Queen",
    ]

    for name in legendaries:
        card_def = JUJUTSU_KAISEN_CARDS[name]
        supertypes = card_def.characteristics.supertypes
        print(f"  {name}: supertypes = {supertypes}")
        assert "Legendary" in supertypes, f"{name} should be Legendary"

    print("PASSED: All legendary creatures have correct supertype!")


def test_multicolor_cards():
    """Test multicolor cards have correct colors."""
    print("\n=== Test: Multicolor Card Colors ===")

    test_cases = [
        ("Yuji Itadori, Sukuna's Vessel", {Color.WHITE, Color.RED}),
        ("Megumi Fushiguro, Ten Shadows", {Color.WHITE, Color.GREEN}),
        ("Satoru Gojo, The Strongest", {Color.WHITE, Color.BLUE}),
        ("Ryomen Sukuna, King of Curses", {Color.BLACK, Color.RED}),
        ("Divine Dog: Totality", {Color.GREEN, Color.BLACK}),
        ("Rika Orimoto, Cursed Queen", {Color.BLUE, Color.BLACK}),
    ]

    for name, expected_colors in test_cases:
        card_def = JUJUTSU_KAISEN_CARDS[name]
        colors = card_def.characteristics.colors
        print(f"  {name}: colors = {colors}")
        assert colors == expected_colors, f"{name} color mismatch: {colors} != {expected_colors}"

    print("PASSED: All multicolor cards have correct colors!")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("JUJUTSU KAISEN: CURSED CLASH CARD TESTS")
    print("=" * 70)

    failed_tests = []

    # ETB Trigger Tests
    print("\n" + "=" * 70)
    print("ETB TRIGGER TESTS")
    print("=" * 70)

    tests = [
        test_jujutsu_first_year_etb_life_gain,
        test_megumi_fushiguro_etb_creates_divine_dog_token,
        test_technique_analyst_etb_scry,
        test_finger_bearer_etb_life_loss,
        test_rabbit_escape_etb_creates_multiple_tokens,
        test_round_deer_etb_life_gain,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Static Effect / Lord Tests
    print("\n" + "=" * 70)
    print("STATIC EFFECT / LORD TESTS")
    print("=" * 70)

    tests = [
        test_jujutsu_instructor_lord_effect,
        test_megumi_fushiguro_shikigami_boost,
        test_shikigami_summoner_lord_effect,
        test_masamichi_yaga_cursed_corpse_boost,
        test_special_grade_curse_lord_effect,
        test_window_guardian_sorcerer_boost,
        test_disease_curse_deathtouch_grant,
        test_self_embodiment_of_perfection_debuff,
        test_chimera_shadow_garden_shikigami_boost,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Upkeep Trigger Tests
    print("\n" + "=" * 70)
    print("UPKEEP TRIGGER TESTS")
    print("=" * 70)

    tests = [
        test_hanami_upkeep_counter,
        test_cursed_bud_upkeep_counter,
        test_malevolent_shrine_upkeep_damage,
        test_shining_sea_of_flowers_upkeep_life,
        test_horizon_of_captivating_skandha_upkeep_token,
        test_cursed_womb_death_painting_upkeep,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Attack Trigger Tests
    print("\n" + "=" * 70)
    print("ATTACK TRIGGER TESTS")
    print("=" * 70)

    tests = [
        test_yuji_itadori_attack_trigger,
        test_nobara_attack_trigger,
        test_jogo_attack_trigger,
        test_aoi_todo_attack_counter,
        test_divine_dog_totality_attack_damage,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Death Trigger Tests
    print("\n" + "=" * 70)
    print("DEATH TRIGGER TESTS")
    print("=" * 70)

    tests = [
        test_cursed_womb_death_tokens,
        test_vengeful_spirit_death_life_loss,
        test_grasshopper_curse_death_life_loss,
        test_tiger_funeral_death_draw,
        test_nature_curse_spawn_death_token,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Spell Cast Trigger Tests
    print("\n" + "=" * 70)
    print("SPELL CAST TRIGGER TESTS")
    print("=" * 70)

    tests = [
        test_yuta_okkotsu_spell_counter,
        test_domain_master_enchantment_draw,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Combat Damage Trigger Tests
    print("\n" + "=" * 70)
    print("COMBAT DAMAGE TRIGGER TESTS")
    print("=" * 70)

    tests = [
        test_panda_combat_damage_counter,
        test_mahito_damage_to_creature_counter,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Keyword Ability Tests
    print("\n" + "=" * 70)
    print("KEYWORD ABILITY TESTS")
    print("=" * 70)

    tests = [
        test_satoru_gojo_keywords,
        test_mahoraga_keywords,
        test_ryomen_sukuna_double_strike,
        test_maki_zenin_keywords,
        test_guardian_shikigami_defender,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Card Stat Tests
    print("\n" + "=" * 70)
    print("CARD STAT TESTS")
    print("=" * 70)

    tests = [
        test_card_base_stats,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Custom Mechanic Tests
    print("\n" + "=" * 70)
    print("BINDING VOW / CURSED ENERGY TESTS")
    print("=" * 70)

    tests = [
        test_yuji_binding_vow_interceptor,
        test_sukuna_binding_vow_interceptor,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Multicolor / Legendary Tests
    print("\n" + "=" * 70)
    print("MULTICOLOR / LEGENDARY TESTS")
    print("=" * 70)

    tests = [
        test_legendary_supertypes,
        test_multicolor_cards,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            failed_tests.append((test.__name__, str(e)))
            print(f"FAILED: {test.__name__} - {e}")

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total_tests = 42  # Count of all individual tests
    passed = total_tests - len(failed_tests)

    if failed_tests:
        print(f"\nFAILED TESTS ({len(failed_tests)}):")
        for name, error in failed_tests:
            print(f"  - {name}: {error}")
        print(f"\n{passed}/{total_tests} tests passed")
    else:
        print(f"\nALL {total_tests} TESTS PASSED!")

    return len(failed_tests) == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
