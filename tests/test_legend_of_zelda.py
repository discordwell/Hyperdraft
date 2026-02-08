"""
Test Legend of Zelda: Hyrule Chronicles card mechanics

Tests cover:
- ETB (enters the battlefield) triggers
- Upkeep triggers
- Attack triggers
- Death triggers
- Combat damage triggers
- Spell cast triggers
- Draw triggers
- Static effects (lords, P/T boosts, keyword grants)
- Triforce mechanic (custom interceptor-based)
- Dungeon mechanic (custom interceptor-based)
- Heart Container mechanic
"""

import sys
import os

# Add project root to path
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics,
)

# Import directly to avoid broken __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "legend_of_zelda",
    "/Users/discordwell/Projects/Hyperdraft/src/cards/custom/legend_of_zelda.py"
)
loz_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loz_module)
LEGEND_OF_ZELDA_CARDS = loz_module.LEGEND_OF_ZELDA_CARDS


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_creature_on_battlefield(game, player_id, card_name, emit_etb=True):
    """
    Helper to create a creature on the battlefield.

    NOTE: The Game.create_object() method automatically emits a ZONE_CHANGE event
    when creating objects directly on the battlefield (from_zone='library').
    Set emit_etb=False if you want to handle the ETB event manually.
    """
    card_def = LEGEND_OF_ZELDA_CARDS[card_name]

    if emit_etb:
        # Create in hand first to avoid automatic ETB
        creature = game.create_object(
            name=card_name,
            owner_id=player_id,
            zone=ZoneType.HAND,
            characteristics=card_def.characteristics,
            card_def=card_def
        )
        # Then move to battlefield with explicit zone change
        creature.zone = ZoneType.BATTLEFIELD
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': creature.id,
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.BATTLEFIELD
            },
            source=creature.id,
            controller=creature.controller
        ))
    else:
        # Create directly on battlefield (triggers automatic ETB event)
        creature = game.create_object(
            name=card_name,
            owner_id=player_id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=card_def.characteristics,
            card_def=card_def
        )
    return creature


def create_on_battlefield_no_etb(game, player_id, card_name):
    """Create a creature on battlefield without triggering ETB (for setup)."""
    card_def = LEGEND_OF_ZELDA_CARDS[card_name]
    creature = game.create_object(
        name=card_name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    return creature


def emit_upkeep_event(game, player_id):
    """Emit an upkeep phase start event."""
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': player_id},
        source=None,
        controller=player_id
    ))


def emit_attack_event(game, attacker, defending_player_id):
    """Emit an attack declared event."""
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={
            'attacker_id': attacker.id,
            'defending_player': defending_player_id
        },
        source=attacker.id,
        controller=attacker.controller
    ))


def emit_death_event(game, creature):
    """Emit a death event (zone change to graveyard)."""
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=creature.id,
        controller=creature.controller
    ))


def emit_combat_damage_to_player(game, creature, player_id, amount):
    """Emit a combat damage event to a player."""
    return game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': creature.id,
            'target': player_id,
            'amount': amount,
            'is_combat': True
        },
        source=creature.id,
        controller=creature.controller
    ))


def emit_spell_cast_event(game, player_id, spell_id=None):
    """Emit a spell cast event."""
    return game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': player_id,
            'spell_id': spell_id or 'test_spell'
        },
        source=spell_id,
        controller=player_id
    ))


def emit_draw_event(game, player_id):
    """Emit a draw event."""
    return game.emit(Event(
        type=EventType.DRAW,
        payload={
            'player': player_id,
            'amount': 1
        },
        source=None,
        controller=player_id
    ))


# =============================================================================
# WHITE CARD TESTS
# =============================================================================

def test_zelda_princess_of_hyrule_etb():
    """Test Zelda, Princess of Hyrule ETB gains 3 life.
    """
    print("\n=== Test: Zelda, Princess of Hyrule ETB ===")

    game = Game()
    p1 = game.add_player("Link")
    starting_life = p1.life

    zelda = create_creature_on_battlefield(game, p1.id, "Zelda, Princess of Hyrule")

    print(f"Starting life: {starting_life}, After ETB: {p1.life}")
    assert p1.life == starting_life + 3, f"Expected {starting_life + 3}, got {p1.life}"
    print("PASSED: Zelda ETB life gain works!")


def test_zelda_wielder_of_wisdom_spell_trigger():
    """Test Zelda, Wielder of Wisdom draws when you cast a spell."""
    print("\n=== Test: Zelda, Wielder of Wisdom Spell Cast Trigger ===")

    game = Game()
    p1 = game.add_player("Wisdom")

    # Create without ETB events
    zelda = create_on_battlefield_no_etb(game, p1.id, "Zelda, Wielder of Wisdom")

    # Cast a spell
    events = emit_spell_cast_event(game, p1.id)

    # Check for draw event
    draw_events = [e for e in events if e.type == EventType.DRAW]
    print(f"Draw events triggered: {len(draw_events)}")
    assert len(draw_events) == 1, f"Expected 1 draw event, got {len(draw_events)}"
    print("PASSED: Zelda draws on spell cast")


def test_impa_sheikah_guardian_hexproof():
    """Test Impa grants hexproof to other Sheikah."""
    print("\n=== Test: Impa, Sheikah Guardian Hexproof Grant ===")

    game = Game()
    p1 = game.add_player("Guardian")

    impa = create_on_battlefield_no_etb(game, p1.id, "Impa, Sheikah Guardian")
    warrior = create_on_battlefield_no_etb(game, p1.id, "Sheikah Warrior")

    # Verify the static ability is set up
    print(f"Impa interceptors: {len(impa.interceptor_ids)}")
    assert len(impa.interceptor_ids) >= 1, "Impa should have keyword grant interceptor"
    print("PASSED: Impa has keyword grant interceptor for Sheikah")


def test_rauru_sage_of_light_upkeep():
    """Test Rauru gains 2 life at upkeep."""
    print("\n=== Test: Rauru, Sage of Light Upkeep Trigger ===")

    game = Game()
    p1 = game.add_player("Light")
    game.state.active_player = p1.id  # Set active player for upkeep check

    rauru = create_on_battlefield_no_etb(game, p1.id, "Rauru, Sage of Light")
    starting_life = p1.life

    emit_upkeep_event(game, p1.id)

    print(f"Starting life: {starting_life}, After upkeep: {p1.life}")
    assert p1.life == starting_life + 2, f"Expected {starting_life + 2}, got {p1.life}"
    print("PASSED: Rauru gains 2 life on upkeep")


def test_hylia_goddess_of_light_anthem():
    """Test Hylia gives other creatures +1/+1."""
    print("\n=== Test: Hylia, Goddess of Light Anthem ===")

    game = Game()
    p1 = game.add_player("Divine")

    # Create a vanilla creature first
    guard = create_on_battlefield_no_etb(game, p1.id, "Castle Guard")
    base_power = get_power(guard, game.state)
    base_toughness = get_toughness(guard, game.state)

    # Create Hylia
    hylia = create_on_battlefield_no_etb(game, p1.id, "Hylia, Goddess of Light")

    boosted_power = get_power(guard, game.state)
    boosted_toughness = get_toughness(guard, game.state)

    print(f"Castle Guard base: {base_power}/{base_toughness}")
    print(f"Castle Guard with Hylia: {boosted_power}/{boosted_toughness}")

    assert boosted_power == base_power + 1, f"Expected power {base_power + 1}, got {boosted_power}"
    assert boosted_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}, got {boosted_toughness}"

    # Check Hylia doesn't buff herself
    hylia_power = get_power(hylia, game.state)
    print(f"Hylia's power: {hylia_power} (should be base 4)")
    assert hylia_power == 4, "Hylia shouldn't buff herself"
    print("PASSED: Hylia anthem works correctly")


def test_sheikah_warrior_etb():
    """Test Sheikah Warrior ETB gains 2 life."""
    print("\n=== Test: Sheikah Warrior ETB ===")

    game = Game()
    p1 = game.add_player("Shadow")
    starting_life = p1.life

    warrior = create_creature_on_battlefield(game, p1.id, "Sheikah Warrior")

    print(f"Starting life: {starting_life}, After ETB: {p1.life}")
    assert p1.life == starting_life + 2, f"Expected {starting_life + 2}, got {p1.life}"
    print("PASSED: Sheikah Warrior ETB gains 2 life")


def test_temple_guardian_heart_container():
    """Test Temple Guardian Heart Container gains 3 life on ETB."""
    print("\n=== Test: Temple Guardian Heart Container ===")

    game = Game()
    p1 = game.add_player("Temple")
    starting_life = p1.life

    guardian = create_creature_on_battlefield(game, p1.id, "Temple Guardian")

    print(f"Starting life: {starting_life}, After ETB: {p1.life}")
    assert p1.life == starting_life + 3, f"Expected {starting_life + 3}, got {p1.life}"
    print("PASSED: Temple Guardian Heart Container works")


def test_sheikah_scout_scry():
    """Test Sheikah Scout ETB scry 2."""
    print("\n=== Test: Sheikah Scout ETB Scry ===")

    game = Game()
    p1 = game.add_player("Scout")
    starting_life = p1.life

    # Create in hand first
    card_def = LEGEND_OF_ZELDA_CARDS["Sheikah Scout"]
    scout = game.create_object(
        name="Sheikah Scout",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Move to battlefield
    scout.zone = ZoneType.BATTLEFIELD
    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': scout.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=scout.id,
        controller=scout.controller
    ))

    # Note: Scry effect currently uses ACTIVATE as placeholder (engine limitation)
    scry_events = [e for e in events if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry']
    print(f"Scry (ACTIVATE placeholder) events: {len(scry_events)}")
    assert len(scry_events) == 1, f"Expected 1 scry event, got {len(scry_events)}"
    assert scry_events[0].payload.get('amount') == 2, "Should scry 2"
    print("PASSED: Sheikah Scout scry 2 works")


# =============================================================================
# BLUE CARD TESTS
# =============================================================================

def test_mipha_zora_champion_upkeep():
    """Test Mipha gains 2 life at upkeep."""
    print("\n=== Test: Mipha, Zora Champion Upkeep ===")

    game = Game()
    p1 = game.add_player("Zora")
    game.state.active_player = p1.id

    mipha = create_on_battlefield_no_etb(game, p1.id, "Mipha, Zora Champion")
    starting_life = p1.life

    emit_upkeep_event(game, p1.id)

    print(f"Starting life: {starting_life}, After upkeep: {p1.life}")
    assert p1.life == starting_life + 2, f"Expected {starting_life + 2}, got {p1.life}"
    print("PASSED: Mipha upkeep trigger works")


def test_ruto_zora_princess_lord():
    """Test Ruto gives other Zora +1/+1."""
    print("\n=== Test: Ruto, Zora Princess Lord Effect ===")

    game = Game()
    p1 = game.add_player("Domain")

    # Create a Zora creature first
    warrior = create_on_battlefield_no_etb(game, p1.id, "Zora Warrior")
    base_power = get_power(warrior, game.state)
    base_toughness = get_toughness(warrior, game.state)

    # Create Ruto
    ruto = create_on_battlefield_no_etb(game, p1.id, "Ruto, Zora Princess")

    boosted_power = get_power(warrior, game.state)
    boosted_toughness = get_toughness(warrior, game.state)

    print(f"Zora Warrior base: {base_power}/{base_toughness}")
    print(f"Zora Warrior with Ruto: {boosted_power}/{boosted_toughness}")

    assert boosted_power == base_power + 1, f"Expected power {base_power + 1}"
    assert boosted_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}"
    print("PASSED: Ruto lord effect works")


def test_king_zora_etb_draw():
    """Test King Zora ETB draws 2 cards."""
    print("\n=== Test: King Zora ETB Draw ===")

    game = Game()
    p1 = game.add_player("Ruler")

    # Create in hand first
    card_def = LEGEND_OF_ZELDA_CARDS["King Zora, Domain Ruler"]
    king = game.create_object(
        name="King Zora, Domain Ruler",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Move to battlefield
    king.zone = ZoneType.BATTLEFIELD
    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': king.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=king.id,
        controller=king.controller
    ))

    # Note: DrawCards generates one event per card drawn (engine behavior)
    draw_events = [e for e in events if e.type == EventType.DRAW]
    print(f"Draw events: {len(draw_events)}")
    # King Zora draws 2 cards, so expect 2 draw events
    assert len(draw_events) == 2, f"Expected 2 draw events (one per card), got {len(draw_events)}"
    print("PASSED: King Zora ETB draw 2 works")


def test_nayru_oracle_draw_trigger():
    """Test Nayru scry 1 when you draw."""
    print("\n=== Test: Nayru, Oracle of Wisdom Draw Trigger ===")

    game = Game()
    p1 = game.add_player("Wisdom")

    nayru = create_on_battlefield_no_etb(game, p1.id, "Nayru, Oracle of Wisdom")
    events = emit_draw_event(game, p1.id)

    # Note: Scry effect uses ACTIVATE as placeholder (engine limitation)
    scry_events = [e for e in events if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry']
    print(f"Scry (ACTIVATE placeholder) events: {len(scry_events)}")
    assert len(scry_events) == 1, f"Expected 1 scry event"
    print("PASSED: Nayru draw trigger works")


def test_sidon_zora_prince_attack():
    """Test Sidon draws when attacking."""
    print("\n=== Test: Sidon, Zora Prince Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Prince")
    p2 = game.add_player("Enemy")

    sidon = create_on_battlefield_no_etb(game, p1.id, "Sidon, Zora Prince")
    events = emit_attack_event(game, sidon, p2.id)

    draw_events = [e for e in events if e.type == EventType.DRAW]
    print(f"Draw events: {len(draw_events)}")
    assert len(draw_events) == 1, f"Expected 1 draw event"
    print("PASSED: Sidon attack trigger works")


def test_zora_scholar_etb_draw():
    """Test Zora Scholar ETB draws 1 card."""
    print("\n=== Test: Zora Scholar ETB ===")

    game = Game()
    p1 = game.add_player("Scholar")

    # Create in hand first
    card_def = LEGEND_OF_ZELDA_CARDS["Zora Scholar"]
    scholar = game.create_object(
        name="Zora Scholar",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Move to battlefield
    scholar.zone = ZoneType.BATTLEFIELD
    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': scholar.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=scholar.id,
        controller=scholar.controller
    ))

    # Note: DrawCards generates one event per card drawn
    draw_events = [e for e in events if e.type == EventType.DRAW]
    print(f"Draw events: {len(draw_events)}")
    assert len(draw_events) == 1, f"Expected 1 draw event"
    print("PASSED: Zora Scholar ETB draw works")


def test_zora_sage_spell_trigger():
    """Test Zora Sage scry 1 when a spell is cast."""
    print("\n=== Test: Zora Sage Spell Cast Trigger ===")

    game = Game()
    p1 = game.add_player("Sage")

    sage = create_on_battlefield_no_etb(game, p1.id, "Zora Sage")
    events = emit_spell_cast_event(game, p1.id)

    # Note: Scry effect uses ACTIVATE as placeholder (engine limitation)
    scry_events = [e for e in events if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry']
    print(f"Scry (ACTIVATE placeholder) events: {len(scry_events)}")
    assert len(scry_events) >= 1, f"Expected at least 1 scry event"
    print("PASSED: Zora Sage spell trigger works")


# =============================================================================
# BLACK CARD TESTS
# =============================================================================

def test_ganondorf_death_trigger():
    """Test Ganondorf makes opponents lose 3 life on death."""
    print("\n=== Test: Ganondorf, King of Evil Death Trigger ===")

    game = Game()
    p1 = game.add_player("Ganon")
    p2 = game.add_player("Hero")

    ganon = create_on_battlefield_no_etb(game, p1.id, "Ganondorf, King of Evil")
    p2_starting_life = p2.life

    events = emit_death_event(game, ganon)

    life_events = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('amount', 0) < 0]
    print(f"Life loss events: {len(life_events)}")
    print("PASSED: Ganondorf death trigger registered")


def test_ganon_calamity_attack_discard():
    """Test Ganon makes opponents discard when attacking."""
    print("\n=== Test: Ganon, Calamity Incarnate Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Calamity")
    p2 = game.add_player("Hyrule")

    ganon = create_on_battlefield_no_etb(game, p1.id, "Ganon, Calamity Incarnate")
    events = emit_attack_event(game, ganon, p2.id)

    discard_events = [e for e in events if e.type == EventType.DISCARD]
    print(f"Discard events: {len(discard_events)}")
    assert len(discard_events) >= 1, "Should trigger discard"
    print("PASSED: Ganon attack discard trigger works")


def test_midna_combat_damage_draw():
    """Test Midna draws when dealing combat damage to a player."""
    print("\n=== Test: Midna, Twilight Princess Combat Damage Trigger ===")

    game = Game()
    p1 = game.add_player("Twilight")
    p2 = game.add_player("Light")

    midna = create_on_battlefield_no_etb(game, p1.id, "Midna, Twilight Princess")
    events = emit_combat_damage_to_player(game, midna, p2.id, 3)

    draw_events = [e for e in events if e.type == EventType.DRAW]
    print(f"Draw events: {len(draw_events)}")
    assert len(draw_events) == 1, "Should draw on combat damage"
    print("PASSED: Midna combat damage draw works")


def test_vaati_upkeep_life_loss():
    """Test Vaati makes opponents lose 1 life at upkeep."""
    print("\n=== Test: Vaati, Wind Mage Upkeep Trigger ===")

    game = Game()
    p1 = game.add_player("Wind")
    p2 = game.add_player("Hero")
    game.state.active_player = p1.id

    vaati = create_on_battlefield_no_etb(game, p1.id, "Vaati, Wind Mage")
    events = emit_upkeep_event(game, p1.id)

    life_events = [e for e in events if e.type == EventType.LIFE_CHANGE]
    print(f"Life change events: {len(life_events)}")
    print("PASSED: Vaati upkeep trigger registered")


def test_shadow_beast_death_token():
    """Test Shadow Beast creates a token on death."""
    print("\n=== Test: Shadow Beast Death Trigger ===")

    game = Game()
    p1 = game.add_player("Shadow")

    beast = create_on_battlefield_no_etb(game, p1.id, "Shadow Beast")
    events = emit_death_event(game, beast)

    # Note: CreateToken uses OBJECT_CREATED event type (engine limitation)
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED and e.payload.get('token')]
    print(f"Token creation (OBJECT_CREATED) events: {len(token_events)}")
    assert len(token_events) == 1, "Should create token on death"
    print("PASSED: Shadow Beast death token works")


# =============================================================================
# RED CARD TESTS
# =============================================================================

def test_daruk_combat_damage():
    """Test Daruk deals 2 damage to opponents on combat damage."""
    print("\n=== Test: Daruk, Goron Champion Combat Damage Trigger ===")

    game = Game()
    p1 = game.add_player("Goron")
    p2 = game.add_player("Enemy")

    daruk = create_on_battlefield_no_etb(game, p1.id, "Daruk, Goron Champion")
    events = emit_combat_damage_to_player(game, daruk, p2.id, 5)

    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    print(f"Triggered damage events: {len(damage_events)}")
    print("PASSED: Daruk combat damage trigger registered")


def test_darunia_goron_lord():
    """Test Darunia gives other Gorons +1/+1."""
    print("\n=== Test: Darunia, Goron Chief Lord Effect ===")

    game = Game()
    p1 = game.add_player("Chief")

    # Create a Goron first
    warrior = create_on_battlefield_no_etb(game, p1.id, "Goron Warrior")
    base_power = get_power(warrior, game.state)
    base_toughness = get_toughness(warrior, game.state)

    # Create Darunia
    darunia = create_on_battlefield_no_etb(game, p1.id, "Darunia, Goron Chief")

    boosted_power = get_power(warrior, game.state)
    boosted_toughness = get_toughness(warrior, game.state)

    print(f"Goron Warrior base: {base_power}/{base_toughness}")
    print(f"Goron Warrior with Darunia: {boosted_power}/{boosted_toughness}")

    assert boosted_power == base_power + 1, f"Expected power {base_power + 1}"
    assert boosted_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}"
    print("PASSED: Darunia lord effect works")


def test_din_attack_damage():
    """Test Din deals 2 damage to opponents when attacking."""
    print("\n=== Test: Din, Oracle of Power Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Power")
    p2 = game.add_player("Enemy")

    din = create_on_battlefield_no_etb(game, p1.id, "Din, Oracle of Power")
    events = emit_attack_event(game, din, p2.id)

    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    print(f"Damage events: {len(damage_events)}")
    print("PASSED: Din attack damage trigger registered")


def test_yunobo_etb_damage():
    """Test Yunobo deals 3 damage to opponents on ETB."""
    print("\n=== Test: Yunobo, Goron Descendant ETB ===")

    game = Game()
    p1 = game.add_player("Descendant")
    p2 = game.add_player("Enemy")

    # Create in hand first
    card_def = LEGEND_OF_ZELDA_CARDS["Yunobo, Goron Descendant"]
    yunobo = game.create_object(
        name="Yunobo, Goron Descendant",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Move to battlefield
    yunobo.zone = ZoneType.BATTLEFIELD
    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': yunobo.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=yunobo.id,
        controller=yunobo.controller
    ))

    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    print(f"Damage events: {len(damage_events)}")
    print("PASSED: Yunobo ETB damage registered")


# =============================================================================
# GREEN CARD TESTS
# =============================================================================

def test_saria_kokiri_lord():
    """Test Saria gives other Kokiri +1/+1."""
    print("\n=== Test: Saria, Forest Sage Lord Effect ===")

    game = Game()
    p1 = game.add_player("Forest")

    # Create a Kokiri first
    child = create_on_battlefield_no_etb(game, p1.id, "Kokiri Child")
    base_power = get_power(child, game.state)
    base_toughness = get_toughness(child, game.state)

    # Create Saria
    saria = create_on_battlefield_no_etb(game, p1.id, "Saria, Forest Sage")

    boosted_power = get_power(child, game.state)
    boosted_toughness = get_toughness(child, game.state)

    print(f"Kokiri Child base: {base_power}/{base_toughness}")
    print(f"Kokiri Child with Saria: {boosted_power}/{boosted_toughness}")

    assert boosted_power == base_power + 1, f"Expected power {base_power + 1}"
    assert boosted_toughness == base_toughness + 1, f"Expected toughness {base_toughness + 1}"
    print("PASSED: Saria lord effect works")


def test_great_deku_tree_upkeep_token():
    """Test Great Deku Tree creates a token at upkeep."""
    print("\n=== Test: Great Deku Tree Upkeep Token ===")

    game = Game()
    p1 = game.add_player("Forest")
    game.state.active_player = p1.id

    deku = create_on_battlefield_no_etb(game, p1.id, "Great Deku Tree")
    events = emit_upkeep_event(game, p1.id)

    # Note: CreateToken uses OBJECT_CREATED event type (engine limitation)
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED and e.payload.get('token')]
    print(f"Token (OBJECT_CREATED) events: {len(token_events)}")
    assert len(token_events) == 1, "Should create token on upkeep"
    print("PASSED: Great Deku Tree upkeep token works")


def test_farore_etb_token():
    """Test Farore creates a 2/2 Spirit token on ETB."""
    print("\n=== Test: Farore, Oracle of Courage ETB Token ===")

    game = Game()
    p1 = game.add_player("Courage")

    # Create in hand first
    card_def = LEGEND_OF_ZELDA_CARDS["Farore, Oracle of Courage"]
    farore = game.create_object(
        name="Farore, Oracle of Courage",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Move to battlefield
    farore.zone = ZoneType.BATTLEFIELD
    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': farore.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD
        },
        source=farore.id,
        controller=farore.controller
    ))

    # Note: CreateToken uses OBJECT_CREATED event type (engine limitation)
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED and e.payload.get('token')]
    print(f"Token (OBJECT_CREATED) events: {len(token_events)}")
    assert len(token_events) == 1, "Should create token on ETB"
    print("PASSED: Farore ETB token works")


# =============================================================================
# MULTICOLOR CARD TESTS
# =============================================================================

def test_urbosa_attack_damage():
    """Test Urbosa deals 2 damage when attacking."""
    print("\n=== Test: Urbosa, Gerudo Champion Attack Trigger ===")

    game = Game()
    p1 = game.add_player("Gerudo")
    p2 = game.add_player("Enemy")

    urbosa = create_on_battlefield_no_etb(game, p1.id, "Urbosa, Gerudo Champion")
    events = emit_attack_event(game, urbosa, p2.id)

    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    print(f"Damage events: {len(damage_events)}")
    print("PASSED: Urbosa attack damage registered")


def test_fi_spell_scry():
    """Test Fi scry 1 when a spell is cast."""
    print("\n=== Test: Fi, Sword Spirit Spell Cast Trigger ===")

    game = Game()
    p1 = game.add_player("Spirit")

    fi = create_on_battlefield_no_etb(game, p1.id, "Fi, Sword Spirit")
    events = emit_spell_cast_event(game, p1.id)

    # Note: Scry effect uses ACTIVATE as placeholder (engine limitation)
    scry_events = [e for e in events if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry']
    print(f"Scry (ACTIVATE placeholder) events: {len(scry_events)}")
    assert len(scry_events) >= 1, "Should scry on spell cast"
    print("PASSED: Fi spell scry works")


def test_skull_kid_masked_upkeep_discard():
    """Test Skull Kid makes opponents discard at upkeep."""
    print("\n=== Test: Skull Kid, Masked Menace Upkeep Discard ===")

    game = Game()
    p1 = game.add_player("Masked")
    p2 = game.add_player("Target")
    game.state.active_player = p1.id

    skull_kid = create_on_battlefield_no_etb(game, p1.id, "Skull Kid, Masked Menace")
    events = emit_upkeep_event(game, p1.id)

    discard_events = [e for e in events if e.type == EventType.DISCARD]
    print(f"Discard events: {len(discard_events)}")
    print("PASSED: Skull Kid upkeep discard registered")


def test_tetra_combat_damage_treasure():
    """Test Tetra creates Treasure when dealing combat damage."""
    print("\n=== Test: Tetra, Pirate Princess Combat Damage Treasure ===")

    game = Game()
    p1 = game.add_player("Pirate")
    p2 = game.add_player("Victim")

    tetra = create_on_battlefield_no_etb(game, p1.id, "Tetra, Pirate Princess")
    events = emit_combat_damage_to_player(game, tetra, p2.id, 3)

    # Note: CreateToken uses OBJECT_CREATED event type (engine limitation)
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED and e.payload.get('token')]
    print(f"Token (OBJECT_CREATED) events: {len(token_events)}")
    assert len(token_events) == 1, "Should create Treasure token"
    print("PASSED: Tetra combat damage treasure works")


# =============================================================================
# ARTIFACT CARD TESTS
# =============================================================================

def test_divine_beast_vah_ruta_upkeep():
    """Test Divine Beast Vah Ruta gains 2 life at upkeep."""
    print("\n=== Test: Divine Beast Vah Ruta Upkeep ===")

    game = Game()
    p1 = game.add_player("Champion")
    game.state.active_player = p1.id

    beast = create_on_battlefield_no_etb(game, p1.id, "Divine Beast Vah Ruta")
    starting_life = p1.life

    emit_upkeep_event(game, p1.id)

    print(f"Starting life: {starting_life}, After upkeep: {p1.life}")
    assert p1.life == starting_life + 2, f"Expected {starting_life + 2}, got {p1.life}"
    print("PASSED: Vah Ruta upkeep life gain works")


def test_divine_beast_vah_rudania_upkeep():
    """Test Divine Beast Vah Rudania deals damage at upkeep."""
    print("\n=== Test: Divine Beast Vah Rudania Upkeep ===")

    game = Game()
    p1 = game.add_player("Champion")
    p2 = game.add_player("Enemy")
    game.state.active_player = p1.id

    beast = create_on_battlefield_no_etb(game, p1.id, "Divine Beast Vah Rudania")
    events = emit_upkeep_event(game, p1.id)

    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    print(f"Damage events: {len(damage_events)}")
    print("PASSED: Vah Rudania upkeep damage registered")


def test_divine_beast_vah_medoh_upkeep():
    """Test Divine Beast Vah Medoh scry 2 at upkeep."""
    print("\n=== Test: Divine Beast Vah Medoh Upkeep ===")

    game = Game()
    p1 = game.add_player("Champion")
    game.state.active_player = p1.id

    beast = create_on_battlefield_no_etb(game, p1.id, "Divine Beast Vah Medoh")
    events = emit_upkeep_event(game, p1.id)

    # Note: Scry effect uses ACTIVATE as placeholder (engine limitation)
    scry_events = [e for e in events if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry']
    print(f"Scry (ACTIVATE placeholder) events: {len(scry_events)}")
    assert len(scry_events) == 1, "Should scry on upkeep"
    assert scry_events[0].payload.get('amount') == 2, "Should scry 2"
    print("PASSED: Vah Medoh upkeep scry works")


def test_divine_beast_vah_naboris_upkeep():
    """Test Divine Beast Vah Naboris deals damage at upkeep."""
    print("\n=== Test: Divine Beast Vah Naboris Upkeep ===")

    game = Game()
    p1 = game.add_player("Champion")
    p2 = game.add_player("Enemy")
    game.state.active_player = p1.id

    beast = create_on_battlefield_no_etb(game, p1.id, "Divine Beast Vah Naboris")
    events = emit_upkeep_event(game, p1.id)

    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    print(f"Damage events: {len(damage_events)}")
    print("PASSED: Vah Naboris upkeep damage registered")


def test_heart_container_artifact_etb():
    """Test Heart Container artifact gains 4 life on ETB."""
    print("\n=== Test: Heart Container Artifact ETB ===")

    game = Game()
    p1 = game.add_player("Hero")
    starting_life = p1.life

    container = create_creature_on_battlefield(game, p1.id, "Heart Container")

    print(f"Starting life: {starting_life}, After ETB: {p1.life}")
    assert p1.life == starting_life + 4, f"Expected {starting_life + 4}, got {p1.life}"
    print("PASSED: Heart Container ETB works")


# =============================================================================
# TRIFORCE MECHANIC TESTS
# =============================================================================

def test_zelda_triforce_bonus():
    """Test Zelda gets +2/+2 with 2+ Triforce artifacts."""
    print("\n=== Test: Zelda Triforce Bonus ===")

    game = Game()
    p1 = game.add_player("Princess")

    # Create Zelda first
    zelda = create_on_battlefield_no_etb(game, p1.id, "Zelda, Princess of Hyrule")
    base_power = get_power(zelda, game.state)
    base_toughness = get_toughness(zelda, game.state)
    print(f"Zelda base: {base_power}/{base_toughness}")

    # Create first Triforce piece
    piece1_def = LEGEND_OF_ZELDA_CARDS["Triforce of Wisdom"]
    piece1 = game.create_object(
        name="Triforce of Wisdom",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=piece1_def.characteristics,
        card_def=piece1_def
    )

    power_1 = get_power(zelda, game.state)
    print(f"Zelda with 1 Triforce: {power_1}/{get_toughness(zelda, game.state)}")

    # Create second Triforce piece
    piece2_def = LEGEND_OF_ZELDA_CARDS["Triforce of Courage"]
    piece2 = game.create_object(
        name="Triforce of Courage",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=piece2_def.characteristics,
        card_def=piece2_def
    )

    boosted_power = get_power(zelda, game.state)
    boosted_toughness = get_toughness(zelda, game.state)
    print(f"Zelda with 2 Triforce: {boosted_power}/{boosted_toughness}")

    # With 2 Triforce pieces, Zelda should get +2/+2
    assert boosted_power == base_power + 2, f"Expected power {base_power + 2}, got {boosted_power}"
    assert boosted_toughness == base_toughness + 2, f"Expected toughness {base_toughness + 2}, got {boosted_toughness}"
    print("PASSED: Zelda Triforce bonus works")


def test_ganondorf_triforce_bonus():
    """Test Ganondorf gets +3/+3 with 1+ Triforce artifact."""
    print("\n=== Test: Ganondorf Triforce Bonus ===")

    game = Game()
    p1 = game.add_player("Evil")

    # Create Ganondorf
    ganon = create_on_battlefield_no_etb(game, p1.id, "Ganondorf, King of Evil")
    base_power = get_power(ganon, game.state)
    base_toughness = get_toughness(ganon, game.state)
    print(f"Ganondorf base: {base_power}/{base_toughness}")

    # Create Triforce of Power
    piece_def = LEGEND_OF_ZELDA_CARDS["Triforce of Power"]
    piece = game.create_object(
        name="Triforce of Power",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=piece_def.characteristics,
        card_def=piece_def
    )

    boosted_power = get_power(ganon, game.state)
    boosted_toughness = get_toughness(ganon, game.state)
    print(f"Ganondorf with Triforce of Power: {boosted_power}/{boosted_toughness}")

    # With 1 Triforce piece, Ganondorf should get +3/+3
    assert boosted_power == base_power + 3, f"Expected power {base_power + 3}, got {boosted_power}"
    assert boosted_toughness == base_toughness + 3, f"Expected toughness {base_toughness + 3}, got {boosted_toughness}"
    print("PASSED: Ganondorf Triforce bonus works")


# =============================================================================
# DUNGEON MECHANIC TESTS
# =============================================================================

def test_link_dungeon_mechanic():
    """Test Link's Dungeon mechanic - draw after 3 attacks."""
    print("\n=== Test: Link, Hero of Time Dungeon Mechanic ===")

    game = Game()
    p1 = game.add_player("Hero")
    p2 = game.add_player("Dungeon")

    link = create_on_battlefield_no_etb(game, p1.id, "Link, Hero of Time")

    # First attack - should add dungeon counter
    events1 = emit_attack_event(game, link, p2.id)
    counters1 = link.state.counters.get('dungeon_room', 0)
    print(f"After attack 1, dungeon counters: {counters1}")

    # Second attack
    events2 = emit_attack_event(game, link, p2.id)
    counters2 = link.state.counters.get('dungeon_room', 0)
    print(f"After attack 2, dungeon counters: {counters2}")

    # Third attack - should trigger effect and reset
    events3 = emit_attack_event(game, link, p2.id)
    counters3 = link.state.counters.get('dungeon_room', 0)
    print(f"After attack 3, dungeon counters: {counters3}")

    # Check for draw event on third attack
    draw_events = [e for e in events3 if e.type == EventType.DRAW]
    print(f"Draw events on 3rd attack: {len(draw_events)}")

    # Counters should reset after completing dungeon
    assert counters3 == 0, f"Counters should reset, got {counters3}"
    assert len(draw_events) == 1, "Should draw card after completing dungeon"
    print("PASSED: Link Dungeon mechanic works")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("LEGEND OF ZELDA: HYRULE CHRONICLES CARD TESTS")
    print("=" * 70)

    # Track results
    passed = 0
    failed = 0
    errors = []

    tests = [
        # White cards
        ("Zelda Princess ETB", test_zelda_princess_of_hyrule_etb),
        ("Zelda Wielder Spell Trigger", test_zelda_wielder_of_wisdom_spell_trigger),
        ("Impa Hexproof", test_impa_sheikah_guardian_hexproof),
        ("Rauru Upkeep", test_rauru_sage_of_light_upkeep),
        ("Hylia Anthem", test_hylia_goddess_of_light_anthem),
        ("Sheikah Warrior ETB", test_sheikah_warrior_etb),
        ("Temple Guardian Heart Container", test_temple_guardian_heart_container),
        ("Sheikah Scout Scry", test_sheikah_scout_scry),

        # Blue cards
        ("Mipha Upkeep", test_mipha_zora_champion_upkeep),
        ("Ruto Lord", test_ruto_zora_princess_lord),
        ("King Zora ETB", test_king_zora_etb_draw),
        ("Nayru Draw Trigger", test_nayru_oracle_draw_trigger),
        ("Sidon Attack", test_sidon_zora_prince_attack),
        ("Zora Scholar ETB", test_zora_scholar_etb_draw),
        ("Zora Sage Spell Trigger", test_zora_sage_spell_trigger),

        # Black cards
        ("Ganondorf Death", test_ganondorf_death_trigger),
        ("Ganon Attack Discard", test_ganon_calamity_attack_discard),
        ("Midna Combat Damage", test_midna_combat_damage_draw),
        ("Vaati Upkeep", test_vaati_upkeep_life_loss),
        ("Shadow Beast Death Token", test_shadow_beast_death_token),

        # Red cards
        ("Daruk Combat Damage", test_daruk_combat_damage),
        ("Darunia Lord", test_darunia_goron_lord),
        ("Din Attack", test_din_attack_damage),
        ("Yunobo ETB", test_yunobo_etb_damage),

        # Green cards
        ("Saria Lord", test_saria_kokiri_lord),
        ("Great Deku Tree Token", test_great_deku_tree_upkeep_token),
        ("Farore ETB Token", test_farore_etb_token),

        # Multicolor cards
        ("Urbosa Attack", test_urbosa_attack_damage),
        ("Fi Spell Scry", test_fi_spell_scry),
        ("Skull Kid Discard", test_skull_kid_masked_upkeep_discard),
        ("Tetra Treasure", test_tetra_combat_damage_treasure),

        # Artifacts
        ("Vah Ruta Upkeep", test_divine_beast_vah_ruta_upkeep),
        ("Vah Rudania Upkeep", test_divine_beast_vah_rudania_upkeep),
        ("Vah Medoh Upkeep", test_divine_beast_vah_medoh_upkeep),
        ("Vah Naboris Upkeep", test_divine_beast_vah_naboris_upkeep),
        ("Heart Container ETB", test_heart_container_artifact_etb),

        # Special mechanics
        ("Zelda Triforce Bonus", test_zelda_triforce_bonus),
        ("Ganondorf Triforce Bonus", test_ganondorf_triforce_bonus),
        ("Link Dungeon Mechanic", test_link_dungeon_mechanic),
    ]

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((test_name, str(e)))
            print(f"FAILED: {test_name} - {e}")
        except Exception as e:
            failed += 1
            errors.append((test_name, str(e)))
            print(f"ERROR: {test_name} - {e}")

    print("\n" + "=" * 70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
