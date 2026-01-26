#!/usr/bin/env python3
"""
Fetch card data from Scryfall and generate/update Python card definitions.

PRODUCTION-READY: Preserves existing interceptors when updating card data.

Usage:
    # Fresh fetch (creates new file, warns if exists)
    python scripts/fetch_scryfall_set.py blb bloomburrow "Bloomburrow"

    # Update existing file (preserves interceptors)
    python scripts/fetch_scryfall_set.py blb bloomburrow "Bloomburrow" --update

    # Force overwrite (destroys interceptors!)
    python scripts/fetch_scryfall_set.py blb bloomburrow "Bloomburrow" --force

    # Dry run (show what would change)
    python scripts/fetch_scryfall_set.py blb bloomburrow "Bloomburrow" --dry-run

Handles all MTG card layouts:
- normal: Standard single-faced cards
- adventure: Cards with Adventure spell (e.g., Bonecrusher Giant // Stomp)
- transform: Double-faced cards that transform (e.g., Delver of Secrets)
- modal_dfc: Modal double-faced cards (e.g., Kazandu Mammoth // Kazandu Valley)
- split: Split cards AND Room cards (e.g., Fire // Ice, Dazzling Theater // Prop Room)
- flip: Flip cards (e.g., Nezumi Shortfang)
- meld: Meld cards (e.g., Bruna, the Fading Light)
- saga, class, case: Enchantment subtypes
- leveler: Level Up cards
- prototype: Prototype cards (e.g., Phyrexian Fleshgorger)
"""

import sys
import os
import json
import time
import re
import argparse
import urllib.request
import urllib.error
from typing import Optional, Dict, Set, Tuple, List
from pathlib import Path


# =============================================================================
# CONFIGURATION
# =============================================================================

SCRYFALL_API = "https://api.scryfall.com"
REQUEST_DELAY = 0.1  # Scryfall asks for 50-100ms between requests
MAX_RETRIES = 3
RETRY_DELAY = 1.0

COLOR_MAP = {
    'W': 'Color.WHITE',
    'U': 'Color.BLUE',
    'B': 'Color.BLACK',
    'R': 'Color.RED',
    'G': 'Color.GREEN',
}

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


# =============================================================================
# API FUNCTIONS
# =============================================================================

def fetch_json(url: str, retries: int = MAX_RETRIES) -> dict:
    """Fetch JSON from URL with rate limiting and retries."""
    time.sleep(REQUEST_DELAY)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Hyperdraft/1.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                wait_time = RETRY_DELAY * (attempt + 1) * 2
                print(f"  Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            elif e.code == 404:
                raise ValueError(f"Not found: {url}")
            else:
                if attempt < retries - 1:
                    print(f"  HTTP {e.code}, retrying...")
                    time.sleep(RETRY_DELAY)
                else:
                    raise
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Error: {e}, retrying...")
                time.sleep(RETRY_DELAY)
            else:
                raise

    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def fetch_all_cards(set_code: str) -> List[dict]:
    """Fetch all cards from a set, handling pagination."""
    cards = []
    url = f"{SCRYFALL_API}/cards/search?q=set:{set_code}&unique=cards&order=set"

    page = 1
    while url:
        print(f"  Page {page}: {url[:70]}...")
        try:
            data = fetch_json(url)
            cards.extend(data.get('data', []))
            url = data.get('next_page')
            page += 1
        except ValueError as e:
            if "Not found" in str(e) and not cards:
                raise ValueError(f"Set '{set_code}' not found on Scryfall")
            break

    return cards


# =============================================================================
# PARSING FUNCTIONS
# =============================================================================

def sanitize_name(name: str) -> str:
    """Convert card name to Python variable name."""
    # Handle split cards - use first part
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
    return "{" + ", ".join(sorted(mapped)) + "}"


def parse_mana_cost(mana_cost: Optional[str]) -> str:
    """Clean mana cost string."""
    if not mana_cost:
        return '""'
    return f'"{mana_cost}"'


def parse_types(type_line: str) -> Tuple[Set[str], Set[str], Set[str]]:
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
            if subtype not in ('/', '//', 'Creature', 'Instant', 'Sorcery',
                              'Enchantment', 'Artifact', 'Land', 'Planeswalker'):
                subtypes.add(subtype)

    return supertypes, types, subtypes


def get_front_face(card: dict) -> dict:
    """Extract front face data from multi-faced cards."""
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
    """Get combined oracle text for multi-faced cards."""
    layout = card.get('layout', 'normal')
    faces = card.get('card_faces', [])

    if not faces or len(faces) < 2:
        return card.get('oracle_text', '')

    if layout == 'adventure':
        # Adventure cards: Main card text + Adventure spell
        main_text = faces[0].get('oracle_text', '')
        adv_name = faces[1].get('name', 'Adventure')
        adv_cost = faces[1].get('mana_cost', '')
        adv_type_line = faces[1].get('type_line', '')
        # Extract Adventure subtype (Instant/Sorcery)
        adv_spell_type = 'Instant' if 'Instant' in adv_type_line else 'Sorcery'
        adv_text = faces[1].get('oracle_text', '').split('(Then exile')[0].strip()
        return f"{main_text}\n// Adventure — {adv_name} {adv_cost} ({adv_spell_type})\n{adv_text}"

    elif layout == 'transform':
        # Transform cards: Front face text + back face info
        front_text = faces[0].get('oracle_text', '')
        back_name = faces[1].get('name', '')
        back_text = faces[1].get('oracle_text', '')
        back_pt = ""
        if 'power' in faces[1] and 'toughness' in faces[1]:
            back_pt = f" ({faces[1]['power']}/{faces[1]['toughness']})"
        return f"{front_text}\n// Transforms into: {back_name}{back_pt}\n{back_text}"

    elif layout == 'modal_dfc':
        # Modal DFCs: Front + back as separate modes
        front_text = faces[0].get('oracle_text', '')
        back_name = faces[1].get('name', '')
        back_type = faces[1].get('type_line', '')
        back_text = faces[1].get('oracle_text', '')
        back_pt = ""
        if 'power' in faces[1] and 'toughness' in faces[1]:
            back_pt = f" ({faces[1]['power']}/{faces[1]['toughness']})"
        return f"{front_text}\n// Back face: {back_name}{back_pt} — {back_type}\n{back_text}"

    elif layout == 'split':
        # Split cards: Both halves (includes Room cards)
        left_name = faces[0].get('name', '')
        left_cost = faces[0].get('mana_cost', '')
        left_type = faces[0].get('type_line', '')
        left_text = faces[0].get('oracle_text', '').split('(You may cast')[0].strip()
        right_name = faces[1].get('name', '')
        right_cost = faces[1].get('mana_cost', '')
        right_text = faces[1].get('oracle_text', '').split('(You may cast')[0].strip()

        # Check if it's a Room card
        if 'Room' in left_type:
            return f"{left_name} {left_cost}:\n{left_text}\n//\n{right_name} {right_cost}:\n{right_text}"
        else:
            return f"{left_name} {left_cost}: {left_text}\n//\n{right_name} {right_cost}: {right_text}"

    elif layout == 'flip':
        # Flip cards: Normal + flipped version
        normal_text = faces[0].get('oracle_text', '')
        flip_name = faces[1].get('name', '')
        flip_type = faces[1].get('type_line', '')
        flip_text = faces[1].get('oracle_text', '')
        flip_pt = ""
        if 'power' in faces[1] and 'toughness' in faces[1]:
            flip_pt = f" {faces[1]['power']}/{faces[1]['toughness']}"
        return f"{normal_text}\n// Flips into: {flip_name} — {flip_type}{flip_pt}\n{flip_text}"

    # Default: use root oracle_text or first face
    if 'oracle_text' in card:
        return card['oracle_text']
    return faces[0].get('oracle_text', '')


def escape_text(text: Optional[str]) -> str:
    """Escape oracle text for Python string."""
    if not text:
        return '""'
    # Escape backslashes and quotes
    text = text.replace('\\', '\\\\').replace('"', '\\"')
    # Replace newlines
    text = text.replace('\n', '\\n')
    return f'"{text}"'


# =============================================================================
# EXISTING FILE PARSING
# =============================================================================

def extract_interceptors(file_path: str) -> Dict[str, str]:
    """
    Extract existing interceptor setup functions from a card file.
    Returns dict mapping card variable name to its setup function name.
    """
    if not os.path.exists(file_path):
        return {}

    interceptors = {}
    setup_functions = {}

    with open(file_path, 'r') as f:
        content = f.read()

    # Find all setup function definitions
    # Pattern: def card_name_setup(obj: GameObject, state: GameState)
    setup_pattern = re.compile(
        r'^def\s+(\w+_setup)\s*\([^)]*\)\s*(?:->.*?)?\s*:\s*\n((?:[ \t]+.+\n)*)',
        re.MULTILINE
    )

    for match in setup_pattern.finditer(content):
        func_name = match.group(1)
        func_body = match.group(0)
        setup_functions[func_name] = func_body

    # Find card definitions that reference setup functions
    # We need a different approach since card defs span multiple lines with many ')'
    # Split content into card definition blocks and check each for setup_interceptors

    # Pattern to find card variable definitions
    card_def_pattern = re.compile(
        r'^([A-Z][A-Z0-9_]*)\s*=\s*make_\w+\(',
        re.MULTILINE
    )

    for match in card_def_pattern.finditer(content):
        var_name = match.group(1)
        start_pos = match.start()

        # Find the closing paren of this card definition
        # Count parens from the opening '(' after make_xxx
        paren_start = content.find('(', match.end() - 1)
        paren_depth = 1
        pos = paren_start + 1

        while pos < len(content) and paren_depth > 0:
            char = content[pos]
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            pos += 1

        card_def = content[start_pos:pos]

        # Check for setup_interceptors in this card definition
        setup_match = re.search(r'setup_interceptors\s*=\s*(\w+)', card_def)
        if setup_match:
            setup_name = setup_match.group(1)
            if setup_name in setup_functions:
                interceptors[var_name] = {
                    'setup_name': setup_name,
                    'setup_code': setup_functions[setup_name]
                }

    return interceptors


def extract_imports_and_helpers(file_path: str) -> Tuple[str, str]:
    """Extract custom imports and helper functions from existing file."""
    if not os.path.exists(file_path):
        return "", ""

    with open(file_path, 'r') as f:
        content = f.read()

    # Find imports from interceptor_helpers
    helper_import_match = re.search(
        r'from src\.cards\.interceptor_helpers import \([^)]+\)',
        content,
        re.DOTALL
    )
    helper_imports = helper_import_match.group(0) if helper_import_match else ""

    return helper_imports, ""


# =============================================================================
# CODE GENERATION
# =============================================================================

def generate_card_code(card: dict, var_name: str, existing_setup: Optional[str] = None) -> str:
    """Generate card definition code."""
    layout = card.get('layout', 'normal')

    # Get combined text for multi-faced cards
    combined_text = get_combined_text(card) if layout in MULTI_FACE_LAYOUTS else None

    # Get front face for type checking
    face = get_front_face(card)
    type_line = face.get('type_line', card.get('type_line', '')).lower()

    # Handle split type lines
    if ' // ' in type_line:
        type_line = type_line.split(' // ')[0]

    # Extract card attributes
    name = face.get('name', card['name']).split(' // ')[0]
    mana_cost = parse_mana_cost(face.get('mana_cost', card.get('mana_cost')))
    colors = parse_colors(face.get('colors', card.get('colors', [])))
    supertypes, types, subtypes = parse_types(face.get('type_line', card.get('type_line', '')))
    rarity = card.get('rarity', 'common')  # Extract rarity from Scryfall data

    if combined_text is not None:
        text = escape_text(combined_text)
    else:
        text = escape_text(face.get('oracle_text', card.get('oracle_text', '')))

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else "set()"
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    # Determine card type and generate appropriate code
    if 'creature' in type_line:
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

        if 'artifact' in type_line:
            func = 'make_artifact_creature'
        elif 'enchantment' in type_line:
            func = 'make_enchantment_creature'
        else:
            func = 'make_creature'

        lines = [
            f'{var_name} = {func}(',
            f'    name="{name}",',
            f'    power={power}, toughness={toughness},',
            f'    mana_cost={mana_cost},',
            f'    colors={colors},',
            f'    subtypes={subtypes_str},',
        ]
        if supertypes_str:
            lines.append(f'    supertypes={supertypes_str},')
        lines.append(f'    text={text},')
        lines.append(f'    rarity="{rarity}",')
        if existing_setup:
            lines.append(f'    setup_interceptors={existing_setup}')
        lines.append(')')

    elif 'planeswalker' in type_line:
        loyalty = face.get('loyalty', card.get('loyalty', '0'))
        try:
            loyalty = int(loyalty)
        except:
            loyalty = 0

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
        lines.append(f'    rarity="{rarity}",')
        if existing_setup:
            lines.append(f'    setup_interceptors={existing_setup}')
        lines.append(')')

    elif 'instant' in type_line:
        subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
        lines = [
            f'{var_name} = make_instant(',
            f'    name="{name}",',
            f'    mana_cost={mana_cost},',
            f'    colors={colors},',
            f'    text={text},',
            f'    rarity="{rarity}",',
        ]
        if subtypes_str:
            lines.append(f'    subtypes={subtypes_str},')
        if supertypes_str:
            lines.append(f'    supertypes={supertypes_str},')
        lines.append(')')

    elif 'sorcery' in type_line:
        subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
        lines = [
            f'{var_name} = make_sorcery(',
            f'    name="{name}",',
            f'    mana_cost={mana_cost},',
            f'    colors={colors},',
            f'    text={text},',
            f'    rarity="{rarity}",',
        ]
        if subtypes_str:
            lines.append(f'    subtypes={subtypes_str},')
        if supertypes_str:
            lines.append(f'    supertypes={supertypes_str},')
        lines.append(')')

    elif 'enchantment' in type_line:
        subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
        lines = [
            f'{var_name} = make_enchantment(',
            f'    name="{name}",',
            f'    mana_cost={mana_cost},',
            f'    colors={colors},',
            f'    text={text},',
            f'    rarity="{rarity}",',
        ]
        if subtypes_str:
            lines.append(f'    subtypes={subtypes_str},')
        if supertypes_str:
            lines.append(f'    supertypes={supertypes_str},')
        if existing_setup:
            lines.append(f'    setup_interceptors={existing_setup}')
        lines.append(')')

    elif 'artifact' in type_line:
        subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
        lines = [
            f'{var_name} = make_artifact(',
            f'    name="{name}",',
            f'    mana_cost={mana_cost},',
            f'    text={text},',
            f'    rarity="{rarity}",',
        ]
        if subtypes_str:
            lines.append(f'    subtypes={subtypes_str},')
        if supertypes_str:
            lines.append(f'    supertypes={supertypes_str},')
        if existing_setup:
            lines.append(f'    setup_interceptors={existing_setup}')
        lines.append(')')

    elif 'land' in type_line:
        subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
        lines = [
            f'{var_name} = make_land(',
            f'    name="{name}",',
            f'    text={text},',
            f'    rarity="{rarity}",',
        ]
        if subtypes_str:
            lines.append(f'    subtypes={subtypes_str},')
        if supertypes_str:
            lines.append(f'    supertypes={supertypes_str},')
        if existing_setup:
            lines.append(f'    setup_interceptors={existing_setup}')
        lines.append(')')

    else:
        return None

    return '\n'.join(lines)


def generate_file(set_code: str, module_name: str, set_name: str,
                  cards: List[dict], existing_interceptors: Dict[str, dict],
                  helper_imports: str) -> str:
    """Generate complete Python file for a card set."""

    # Collect all setup functions that we need to preserve
    setup_functions_code = []
    for var_name, info in existing_interceptors.items():
        setup_functions_code.append(info['setup_code'])

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
'''

    # Add interceptor helper imports if they exist
    if helper_imports:
        header += f"\n{helper_imports}\n"
    elif existing_interceptors:
        # Default imports if we have interceptors but no explicit imports
        header += '''
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger, make_damage_trigger,
    make_static_pt_boost, make_keyword_grant, make_upkeep_trigger,
    make_life_gain_trigger, make_draw_trigger,
    other_creatures_you_control, creatures_you_control, other_creatures_with_subtype
)
'''

    header += '''

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_instant(name: str, mana_cost: str, colors: set, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create instant card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        resolve=resolve
    )


def make_sorcery(name: str, mana_cost: str, colors: set, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_enchantment_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                              subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create enchantment creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", rarity: str = None, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create land card definitions."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, loyalty: int,
                      subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    base_supertypes = supertypes or set()
    loyalty_text = f"[Loyalty: {loyalty}] " + text if text else f"[Loyalty: {loyalty}]"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes or set(),
            supertypes=base_supertypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=loyalty_text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )

'''

    # Add preserved setup functions
    if setup_functions_code:
        header += '''
# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS (Preserved from previous version)
# =============================================================================

'''
        header += '\n\n'.join(setup_functions_code)
        header += '\n'

    header += '''
# =============================================================================
# CARD DEFINITIONS
# =============================================================================

'''

    card_defs = []
    registry_entries = []
    seen_vars = set()
    stats = {'total': 0, 'with_interceptors': 0, 'skipped': 0}

    for card in cards:
        layout = card.get('layout', 'normal')
        if layout in SKIP_LAYOUTS:
            stats['skipped'] += 1
            continue

        name = card.get('name')
        if not name:
            stats['skipped'] += 1
            continue

        var_name = sanitize_name(name)
        if not var_name:
            stats['skipped'] += 1
            continue

        # Handle duplicate variable names
        original_var = var_name
        counter = 2
        while var_name in seen_vars:
            var_name = f"{original_var}_{counter}"
            counter += 1
        seen_vars.add(var_name)

        # Check if this card has an existing interceptor
        existing_setup = None
        if original_var in existing_interceptors:
            existing_setup = existing_interceptors[original_var]['setup_name']
            stats['with_interceptors'] += 1
        elif var_name in existing_interceptors:
            existing_setup = existing_interceptors[var_name]['setup_name']
            stats['with_interceptors'] += 1

        code = generate_card_code(card, var_name, existing_setup)
        if code:
            card_defs.append(code)
            display_name = get_front_face(card).get('name', name).split(' // ')[0]
            registry_entries.append(f'    "{display_name}": {var_name},')
            stats['total'] += 1

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

    return header + '\n\n'.join(card_defs) + footer, stats


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Fetch MTG card data from Scryfall and generate Python definitions.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s blb bloomburrow "Bloomburrow"           # Fresh fetch
  %(prog)s blb bloomburrow "Bloomburrow" --update  # Preserve interceptors
  %(prog)s blb bloomburrow "Bloomburrow" --dry-run # Preview changes
        '''
    )
    parser.add_argument('set_code', help='Scryfall set code (e.g., blb, dsk)')
    parser.add_argument('module_name', help='Python module name (e.g., bloomburrow)')
    parser.add_argument('set_name', help='Display name (e.g., "Bloomburrow")')
    parser.add_argument('--update', '-u', action='store_true',
                       help='Update existing file, preserving interceptors')
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force overwrite (destroys existing interceptors!)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                       help='Show what would be done without writing')
    parser.add_argument('--output', '-o', help='Output path (default: src/cards/<module_name>.py)')

    args = parser.parse_args()

    output_path = args.output or f"src/cards/{args.module_name}.py"

    # Check if file exists
    file_exists = os.path.exists(output_path)

    if file_exists and not args.update and not args.force and not args.dry_run:
        print(f"ERROR: {output_path} already exists!")
        print("Use --update to preserve interceptors, --force to overwrite, or --dry-run to preview")
        sys.exit(1)

    # Extract existing interceptors if updating
    existing_interceptors = {}
    helper_imports = ""
    if file_exists and (args.update or args.dry_run):
        print(f"Reading existing file: {output_path}")
        existing_interceptors = extract_interceptors(output_path)
        helper_imports, _ = extract_imports_and_helpers(output_path)
        print(f"  Found {len(existing_interceptors)} existing interceptors to preserve")

    # Fetch cards from Scryfall
    print(f"Fetching {args.set_name} ({args.set_code}) from Scryfall...")
    try:
        cards = fetch_all_cards(args.set_code)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    print(f"Found {len(cards)} cards")

    # Generate file content
    print("Generating Python file...")
    content, stats = generate_file(
        args.set_code, args.module_name, args.set_name,
        cards, existing_interceptors, helper_imports
    )

    print(f"\nStats:")
    print(f"  Total cards: {stats['total']}")
    print(f"  With interceptors: {stats['with_interceptors']}")
    print(f"  Skipped (tokens/emblems): {stats['skipped']}")

    if args.dry_run:
        print(f"\nDry run - would write {len(content)} bytes to {output_path}")
        print("First 500 chars of output:")
        print("-" * 40)
        print(content[:500])
        print("-" * 40)
    else:
        with open(output_path, 'w') as f:
            f.write(content)
        print(f"\nWritten to {output_path}")

        if args.update:
            print(f"Preserved {stats['with_interceptors']} interceptors")


if __name__ == "__main__":
    main()
