#!/usr/bin/env python3
"""
Fetch card data from Scryfall and generate Python card definitions.

Usage:
    python scripts/fetch_scryfall_set.py blb bloomburrow "Bloomburrow"
    python scripts/fetch_scryfall_set.py eoe edge_of_eternities "Edge of Eternities"

Handles all MTG card layouts:
- normal: Standard single-faced cards
- adventure: Cards with Adventure spell (e.g., Bonecrusher Giant // Stomp)
- transform: Double-faced cards that transform (e.g., Delver of Secrets)
- modal_dfc: Modal double-faced cards (e.g., Kazandu Mammoth // Kazandu Valley)
- split: Split cards (e.g., Fire // Ice)
- flip: Flip cards (e.g., Nezumi Shortfang)
- meld: Meld cards (e.g., Bruna, the Fading Light)
- saga, class, case: Enchantment subtypes
- leveler: Level Up cards
- prototype: Prototype cards (e.g., Phyrexian Fleshgorger)
"""

import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Optional

# Scryfall API base
SCRYFALL_API = "https://api.scryfall.com"

# Color mapping
COLOR_MAP = {
    'W': 'Color.WHITE',
    'U': 'Color.BLUE',
    'B': 'Color.BLACK',
    'R': 'Color.RED',
    'G': 'Color.GREEN',
}

# Card type mapping
TYPE_MAP = {
    'creature': 'CardType.CREATURE',
    'instant': 'CardType.INSTANT',
    'sorcery': 'CardType.SORCERY',
    'enchantment': 'CardType.ENCHANTMENT',
    'artifact': 'CardType.ARTIFACT',
    'land': 'CardType.LAND',
    'planeswalker': 'CardType.PLANESWALKER',
    'battle': 'CardType.BATTLE',
}

# Layouts that use card_faces array
MULTI_FACE_LAYOUTS = {
    'adventure', 'transform', 'modal_dfc', 'split', 'flip',
    'reversible_card', 'meld'
}

# Layouts to skip entirely
SKIP_LAYOUTS = {
    'token', 'emblem', 'art_series', 'double_faced_token',
    'planar', 'scheme', 'vanguard', 'augment', 'host'
}


def fetch_json(url: str) -> dict:
    """Fetch JSON from URL with rate limiting."""
    time.sleep(0.1)  # Scryfall asks for 50-100ms between requests
    req = urllib.request.Request(url, headers={'User-Agent': 'Hyperdraft/1.0'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


def fetch_all_cards(set_code: str) -> list[dict]:
    """Fetch all cards from a set, handling pagination."""
    cards = []
    url = f"{SCRYFALL_API}/cards/search?q=set:{set_code}&unique=cards&order=set"

    while url:
        print(f"  Fetching: {url[:80]}...")
        data = fetch_json(url)
        cards.extend(data.get('data', []))
        url = data.get('next_page')

    return cards


def sanitize_name(name: str) -> str:
    """Convert card name to Python variable name."""
    # Handle split cards
    name = name.split(' // ')[0]
    # Remove special characters
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    # Convert to UPPER_SNAKE_CASE
    name = re.sub(r"\s+", "_", name.strip().upper())
    return name


def parse_colors(colors: list) -> str:
    """Convert Scryfall colors to our Color set."""
    if not colors:
        return "set()"
    mapped = [COLOR_MAP.get(c, f"'{c}'") for c in colors]
    return "{" + ", ".join(mapped) + "}"


def parse_mana_cost(mana_cost: Optional[str]) -> str:
    """Clean mana cost string."""
    if not mana_cost:
        return '""'
    return f'"{mana_cost}"'


def parse_types(type_line: str) -> tuple[set, set, set]:
    """Parse type line into supertypes, types, subtypes."""
    supertypes = set()
    types = set()
    subtypes = set()

    # Handle split type lines (e.g., "Creature // Land")
    if ' // ' in type_line:
        type_line = type_line.split(' // ')[0]

    # Split on em-dash for subtypes
    parts = type_line.split('—')
    main_types = parts[0].strip().split()

    # Known supertypes
    supertype_words = {'Legendary', 'Basic', 'Snow', 'World'}

    for word in main_types:
        word_lower = word.lower()
        if word in supertype_words:
            supertypes.add(word)
        elif word_lower in TYPE_MAP:
            types.add(word_lower)

    # Subtypes
    if len(parts) > 1:
        for subtype in parts[1].strip().split():
            # Filter out junk from multi-face parsing
            if subtype not in ('/', '//', 'Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Land'):
                subtypes.add(subtype)

    return supertypes, types, subtypes


def get_front_face(card: dict) -> dict:
    """
    Extract front face data from multi-faced cards.
    For single-faced cards, returns the card itself.
    """
    layout = card.get('layout', 'normal')

    if layout not in MULTI_FACE_LAYOUTS:
        return card

    faces = card.get('card_faces', [])
    if not faces:
        return card

    # Return first face with some root-level data preserved
    front = faces[0].copy()

    # Preserve root-level data that applies to the whole card
    if 'colors' not in front and 'colors' in card:
        front['colors'] = card['colors']
    if 'color_identity' not in front and 'color_identity' in card:
        front['color_identity'] = card['color_identity']

    return front


def get_combined_text(card: dict) -> str:
    """
    Get combined oracle text for multi-faced cards.
    Single-faced cards return their oracle_text directly.
    """
    layout = card.get('layout', 'normal')

    if layout == 'adventure':
        # Adventure cards: Main card text + Adventure spell
        faces = card.get('card_faces', [])
        if len(faces) >= 2:
            main_text = faces[0].get('oracle_text', '')
            adv_name = faces[1].get('name', 'Adventure')
            adv_cost = faces[1].get('mana_cost', '')
            adv_type = faces[1].get('type_line', '').split('—')[-1].strip() if '—' in faces[1].get('type_line', '') else 'Adventure'
            adv_text = faces[1].get('oracle_text', '')
            return f"{main_text}\n// Adventure — {adv_name} {adv_cost}\n{adv_text}"
        return card.get('oracle_text', '')

    elif layout == 'transform':
        # Transform cards: Front face text + back face info
        faces = card.get('card_faces', [])
        if len(faces) >= 2:
            front_text = faces[0].get('oracle_text', '')
            back_name = faces[1].get('name', '')
            back_type = faces[1].get('type_line', '')
            back_text = faces[1].get('oracle_text', '')
            back_pt = ""
            if 'power' in faces[1] and 'toughness' in faces[1]:
                back_pt = f" ({faces[1]['power']}/{faces[1]['toughness']})"
            return f"{front_text}\n// Transforms into: {back_name}{back_pt}\n{back_text}"
        return card.get('oracle_text', '')

    elif layout == 'modal_dfc':
        # Modal DFCs: Front + back as separate modes
        faces = card.get('card_faces', [])
        if len(faces) >= 2:
            front_text = faces[0].get('oracle_text', '')
            back_name = faces[1].get('name', '')
            back_type = faces[1].get('type_line', '')
            back_text = faces[1].get('oracle_text', '')
            return f"{front_text}\n// Back face: {back_name} — {back_type}\n{back_text}"
        return card.get('oracle_text', '')

    elif layout == 'split':
        # Split cards: Both halves
        faces = card.get('card_faces', [])
        if len(faces) >= 2:
            left_name = faces[0].get('name', '')
            left_cost = faces[0].get('mana_cost', '')
            left_text = faces[0].get('oracle_text', '')
            right_name = faces[1].get('name', '')
            right_cost = faces[1].get('mana_cost', '')
            right_text = faces[1].get('oracle_text', '')
            return f"{left_name} {left_cost}: {left_text}\n//\n{right_name} {right_cost}: {right_text}"
        return card.get('oracle_text', '')

    elif layout == 'flip':
        # Flip cards: Normal + flipped version
        faces = card.get('card_faces', [])
        if len(faces) >= 2:
            normal_text = faces[0].get('oracle_text', '')
            flip_name = faces[1].get('name', '')
            flip_type = faces[1].get('type_line', '')
            flip_text = faces[1].get('oracle_text', '')
            flip_pt = ""
            if 'power' in faces[1] and 'toughness' in faces[1]:
                flip_pt = f" {faces[1]['power']}/{faces[1]['toughness']}"
            return f"{normal_text}\n// Flips into: {flip_name} — {flip_type}{flip_pt}\n{flip_text}"
        return card.get('oracle_text', '')

    # Default: use root oracle_text or first face
    if 'oracle_text' in card:
        return card['oracle_text']
    faces = card.get('card_faces', [])
    if faces:
        return faces[0].get('oracle_text', '')
    return ''


def escape_text(text: Optional[str]) -> str:
    """Escape oracle text for Python string."""
    if not text:
        return '""'
    # Escape backslashes and quotes
    text = text.replace('\\', '\\\\').replace('"', '\\"')
    # Replace newlines
    text = text.replace('\n', '\\n')
    return f'"{text}"'


def generate_creature(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate creature card definition."""
    # Use front face for multi-faced cards
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    # Use combined text for multi-faced cards
    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    power = face.get('power', card.get('power', '0'))
    toughness = face.get('toughness', card.get('toughness', '0'))

    # Handle */*, X/X type P/T
    try:
        power = int(power)
    except:
        power = 0
    try:
        toughness = int(toughness)
    except:
        toughness = 0

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else "set()"
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    lines = [
        f'{var_name} = make_creature(',
        f'    name="{name}",',
        f'    power={power}, toughness={toughness},',
        f'    mana_cost={mana_cost},',
        f'    colors={colors},',
        f'    subtypes={subtypes_str},',
    ]
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(f'    text={text},')
    lines.append(')')

    return '\n'.join(lines)


def generate_enchantment_creature(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate enchantment creature card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    power = face.get('power', card.get('power', '0'))
    toughness = face.get('toughness', card.get('toughness', '0'))

    try:
        power = int(power)
    except:
        power = 0
    try:
        toughness = int(toughness)
    except:
        toughness = 0

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else "set()"
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    lines = [
        f'{var_name} = make_enchantment_creature(',
        f'    name="{name}",',
        f'    power={power}, toughness={toughness},',
        f'    mana_cost={mana_cost},',
        f'    colors={colors},',
        f'    subtypes={subtypes_str},',
    ]
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(f'    text={text},')
    lines.append(')')

    return '\n'.join(lines)


def generate_instant_or_sorcery(card: dict, var_name: str, card_type: str, combined_text: str = None) -> str:
    """Generate instant or sorcery card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    func_name = 'make_instant' if card_type == 'instant' else 'make_sorcery'

    lines = [
        f'{var_name} = {func_name}(',
        f'    name="{name}",',
        f'    mana_cost={mana_cost},',
        f'    colors={colors},',
        f'    text={text},',
    ]
    if subtypes_str:
        lines.append(f'    subtypes={subtypes_str},')
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(')')

    return '\n'.join(lines)


def generate_enchantment(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate enchantment card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    lines = [
        f'{var_name} = make_enchantment(',
        f'    name="{name}",',
        f'    mana_cost={mana_cost},',
        f'    colors={colors},',
        f'    text={text},',
    ]
    if subtypes_str:
        lines.append(f'    subtypes={subtypes_str},')
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(')')

    return '\n'.join(lines)


def generate_artifact(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate artifact card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    # Check if it's also a creature
    if 'creature' in types:
        return generate_artifact_creature(card, var_name, combined_text)

    lines = [
        f'{var_name} = make_artifact(',
        f'    name="{name}",',
        f'    mana_cost={mana_cost},',
        f'    text={text},',
    ]
    if subtypes_str:
        lines.append(f'    subtypes={subtypes_str},')
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(')')

    return '\n'.join(lines)


def generate_artifact_creature(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate artifact creature card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    power = face.get('power', card.get('power', '0'))
    toughness = face.get('toughness', card.get('toughness', '0'))

    try:
        power = int(power)
    except:
        power = 0
    try:
        toughness = int(toughness)
    except:
        toughness = 0

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else "set()"
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    lines = [
        f'{var_name} = make_artifact_creature(',
        f'    name="{name}",',
        f'    power={power}, toughness={toughness},',
        f'    mana_cost={mana_cost},',
        f'    colors={colors},',
        f'    subtypes={subtypes_str},',
    ]
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(f'    text={text},')
    lines.append(')')

    return '\n'.join(lines)


def generate_land(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate land card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    lines = [
        f'{var_name} = make_land(',
        f'    name="{name}",',
        f'    text={text},',
    ]
    if subtypes_str:
        lines.append(f'    subtypes={subtypes_str},')
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(')')

    return '\n'.join(lines)


def generate_planeswalker(card: dict, var_name: str, combined_text: str = None) -> str:
    """Generate planeswalker card definition."""
    face = get_front_face(card)
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    loyalty = face.get('loyalty', card.get('loyalty', '0'))

    try:
        loyalty = int(loyalty)
    except:
        loyalty = 0

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else "set()"
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    lines = [
        f'{var_name} = make_planeswalker(',
        f'    name="{name}",',
        f'    mana_cost={mana_cost},',
        f'    colors={colors},',
        f'    loyalty={loyalty},',
        f'    subtypes={subtypes_str},',
    ]
    if supertypes_str:
        lines.append(f'    supertypes={supertypes_str},')
    lines.append(f'    text={text},')
    lines.append(')')

    return '\n'.join(lines)


def generate_card(card: dict) -> Optional[tuple[str, str, str]]:
    """Generate card definition. Returns (var_name, code, card_name) or None."""
    # Skip tokens, emblems, etc.
    layout = card.get('layout', 'normal')
    if layout in SKIP_LAYOUTS:
        return None

    # Skip cards without names
    name = card.get('name')
    if not name:
        return None

    var_name = sanitize_name(name)
    if not var_name:
        return None

    # Get combined text for multi-faced cards
    combined_text = get_combined_text(card) if layout in MULTI_FACE_LAYOUTS else None

    # Get front face for type checking on multi-faced cards
    face = get_front_face(card)
    type_line = face.get('type_line', card.get('type_line', '')).lower()

    # Handle split type lines (e.g., "Creature — Human // Land — Forest")
    if ' // ' in type_line:
        type_line = type_line.split(' // ')[0]

    # Determine primary type with proper priority
    if 'creature' in type_line:
        if 'artifact' in type_line:
            code = generate_artifact_creature(card, var_name, combined_text)
        elif 'enchantment' in type_line:
            code = generate_enchantment_creature(card, var_name, combined_text)
        else:
            code = generate_creature(card, var_name, combined_text)
    elif 'instant' in type_line:
        code = generate_instant_or_sorcery(card, var_name, 'instant', combined_text)
    elif 'sorcery' in type_line:
        code = generate_instant_or_sorcery(card, var_name, 'sorcery', combined_text)
    elif 'enchantment' in type_line:
        code = generate_enchantment(card, var_name, combined_text)
    elif 'artifact' in type_line:
        code = generate_artifact(card, var_name, combined_text)
    elif 'land' in type_line:
        code = generate_land(card, var_name, combined_text)
    elif 'planeswalker' in type_line:
        code = generate_planeswalker(card, var_name, combined_text)
    else:
        # Unknown type, skip
        return None

    # Use front face name for registry
    display_name = face.get('name', name).split(' // ')[0]

    return var_name, code, display_name


def generate_file(set_code: str, module_name: str, set_name: str, cards: list[dict]) -> str:
    """Generate complete Python file for a card set."""

    header = f'''"""
{set_name} ({set_code.upper()}) Card Implementations

Real card data fetched from Scryfall API.
{len(cards)} cards in set.
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_instant(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create instant card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={{CardType.INSTANT}},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={{CardType.SORCERY}},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={{CardType.ARTIFACT}},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={{CardType.ARTIFACT, CardType.CREATURE}},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_enchantment_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                              subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create enchantment creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={{CardType.ENCHANTMENT, CardType.CREATURE}},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create land card definitions."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={{CardType.LAND}},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, loyalty: int,
                      subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    base_supertypes = supertypes or set()
    # Note: loyalty is prepended to text since Characteristics doesn't have loyalty field
    loyalty_text = f"[Loyalty: {{loyalty}}] " + text if text else f"[Loyalty: {{loyalty}}]"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={{CardType.PLANESWALKER}},
            subtypes=subtypes or set(),
            supertypes=base_supertypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=loyalty_text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

'''

    card_defs = []
    registry_entries = []
    seen_vars = set()

    for card in cards:
        result = generate_card(card)
        if result:
            var_name, code, card_name = result
            # Handle duplicate variable names
            original_var = var_name
            counter = 2
            while var_name in seen_vars:
                var_name = f"{original_var}_{counter}"
                code = code.replace(f"{original_var} =", f"{var_name} =", 1)
                counter += 1
            seen_vars.add(var_name)
            card_defs.append(code)
            registry_entries.append(f'    "{card_name}": {var_name},')

    registry_name = module_name.upper() + "_CARDS"

    footer = f'''

# =============================================================================
# CARD REGISTRY
# =============================================================================

{registry_name} = {{
{chr(10).join(registry_entries)}
}}

print(f"Loaded {{len({registry_name})}} {set_name} cards")
'''

    return header + '\n\n'.join(card_defs) + footer


def main():
    if len(sys.argv) < 4:
        print("Usage: python fetch_scryfall_set.py <set_code> <module_name> <set_name>")
        print("Example: python fetch_scryfall_set.py blb bloomburrow \"Bloomburrow\"")
        sys.exit(1)

    set_code = sys.argv[1]
    module_name = sys.argv[2]
    set_name = sys.argv[3]

    print(f"Fetching {set_name} ({set_code}) from Scryfall...")
    cards = fetch_all_cards(set_code)
    print(f"Found {len(cards)} cards")

    print("Generating Python file...")
    content = generate_file(set_code, module_name, set_name, cards)

    output_path = f"src/cards/{module_name}.py"
    with open(output_path, 'w') as f:
        f.write(content)

    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
