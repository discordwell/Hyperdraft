#!/usr/bin/env python3
"""
Fetch card data from Scryfall and generate Python card definitions.

Usage:
    python scripts/fetch_scryfall_set.py blb bloomburrow "Bloomburrow"
    python scripts/fetch_scryfall_set.py eoe edge_of_eternities "Edge of Eternities"
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
            subtypes.add(subtype)

    return supertypes, types, subtypes


def escape_text(text: Optional[str]) -> str:
    """Escape oracle text for Python string."""
    if not text:
        return '""'
    # Escape backslashes and quotes
    text = text.replace('\\', '\\\\').replace('"', '\\"')
    # Replace newlines
    text = text.replace('\n', '\\n')
    return f'"{text}"'


def generate_creature(card: dict, var_name: str) -> str:
    """Generate creature card definition."""
    name = card['name'].split(' // ')[0]
    mana_cost = parse_mana_cost(card.get('mana_cost'))
    colors = parse_colors(card.get('colors', []))
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text'))
    power = card.get('power', '0')
    toughness = card.get('toughness', '0')

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


def generate_instant_or_sorcery(card: dict, var_name: str, card_type: str) -> str:
    """Generate instant or sorcery card definition."""
    name = card['name'].split(' // ')[0]
    mana_cost = parse_mana_cost(card.get('mana_cost'))
    colors = parse_colors(card.get('colors', []))
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text'))

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


def generate_enchantment(card: dict, var_name: str) -> str:
    """Generate enchantment card definition."""
    name = card['name'].split(' // ')[0]
    mana_cost = parse_mana_cost(card.get('mana_cost'))
    colors = parse_colors(card.get('colors', []))
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text'))

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


def generate_artifact(card: dict, var_name: str) -> str:
    """Generate artifact card definition."""
    name = card['name'].split(' // ')[0]
    mana_cost = parse_mana_cost(card.get('mana_cost'))
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text'))

    subtypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(subtypes)) + "}" if subtypes else None
    supertypes_str = "{" + ", ".join(f'"{s}"' for s in sorted(supertypes)) + "}" if supertypes else None

    # Check if it's also a creature
    if 'creature' in types:
        return generate_artifact_creature(card, var_name)

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


def generate_artifact_creature(card: dict, var_name: str) -> str:
    """Generate artifact creature card definition."""
    name = card['name'].split(' // ')[0]
    mana_cost = parse_mana_cost(card.get('mana_cost'))
    colors = parse_colors(card.get('colors', []))
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text'))
    power = card.get('power', '0')
    toughness = card.get('toughness', '0')

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


def generate_land(card: dict, var_name: str) -> str:
    """Generate land card definition."""
    name = card['name'].split(' // ')[0]
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text', ''))

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


def generate_planeswalker(card: dict, var_name: str) -> str:
    """Generate planeswalker card definition."""
    name = card['name'].split(' // ')[0]
    mana_cost = parse_mana_cost(card.get('mana_cost'))
    colors = parse_colors(card.get('colors', []))
    supertypes, types, subtypes = parse_types(card.get('type_line', ''))
    text = escape_text(card.get('oracle_text'))
    loyalty = card.get('loyalty', '0')

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
    layout = card.get('layout', '')
    if layout in ('token', 'emblem', 'art_series', 'double_faced_token'):
        return None

    # Skip cards without names
    name = card.get('name')
    if not name:
        return None

    var_name = sanitize_name(name)
    if not var_name:
        return None

    type_line = card.get('type_line', '').lower()

    # Determine primary type
    if 'creature' in type_line:
        if 'artifact' in type_line:
            code = generate_artifact_creature(card, var_name)
        else:
            code = generate_creature(card, var_name)
    elif 'instant' in type_line:
        code = generate_instant_or_sorcery(card, var_name, 'instant')
    elif 'sorcery' in type_line:
        code = generate_instant_or_sorcery(card, var_name, 'sorcery')
    elif 'enchantment' in type_line:
        code = generate_enchantment(card, var_name)
    elif 'artifact' in type_line:
        code = generate_artifact(card, var_name)
    elif 'land' in type_line:
        code = generate_land(card, var_name)
    elif 'planeswalker' in type_line:
        code = generate_planeswalker(card, var_name)
    else:
        # Unknown type, skip
        return None

    return var_name, code, name.split(' // ')[0]


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
