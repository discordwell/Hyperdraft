#!/usr/bin/env python3
"""
Fetch Pokemon card data from pokemontcg.io API and generate Python card definitions.

Usage:
    python scripts/fetch_pokemon_set.py sv6pt5 shrouded_fable "Shrouded Fable"
    python scripts/fetch_pokemon_set.py sv1 scarlet_violet "Scarlet & Violet"
    python scripts/fetch_pokemon_set.py sv6pt5 shrouded_fable "Shrouded Fable" --update
    python scripts/fetch_pokemon_set.py sv6pt5 shrouded_fable "Shrouded Fable" --dry-run

Standard-Legal SV Sets:
    sv1     Scarlet & Violet
    sv2     Paldea Evolved
    sv3     Obsidian Flames
    sv3pt5  151
    sv4     Paradox Rift
    sv4pt5  Paldean Fates
    sv5     Temporal Forces
    sv6     Twilight Masquerade
    sv6pt5  Shrouded Fable
    sv7     Stellar Crown
    sv8     Surging Sparks
    sv8pt5  Prismatic Evolutions
    sv9     Journey Together
"""

import sys
import os
import json
import time
import re
import argparse
import urllib.request
import urllib.error
from typing import Optional, List

# =============================================================================
# CONFIGURATION
# =============================================================================

API_BASE = "https://api.pokemontcg.io/v2"
REQUEST_DELAY = 0.2  # Rate limit: ~30 req/min without API key
MAX_RETRIES = 3
RETRY_DELAY = 2.0

POKEMON_TYPE_MAP = {
    "Grass": "G",
    "Fire": "R",
    "Water": "W",
    "Lightning": "L",
    "Psychic": "P",
    "Fighting": "F",
    "Darkness": "D",
    "Metal": "M",
    "Dragon": "N",
    "Colorless": "C",
    "Fairy": "P",  # Fairy merged into Psychic in SV era
}

# =============================================================================
# API FUNCTIONS
# =============================================================================

def fetch_json(url: str, retries: int = MAX_RETRIES) -> dict:
    """Fetch JSON from URL with rate limiting and retries."""
    time.sleep(REQUEST_DELAY)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Hyperdraft/1.0',
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
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


def fetch_all_cards(set_id: str) -> List[dict]:
    """Fetch all cards from a set, handling pagination."""
    cards = []
    page = 1
    page_size = 250

    while True:
        url = f"{API_BASE}/cards?q=set.id:{set_id}&pageSize={page_size}&page={page}"
        print(f"  Page {page}: fetching...")
        try:
            data = fetch_json(url)
            batch = data.get('data', [])
            cards.extend(batch)
            total = data.get('totalCount', 0)
            print(f"    Got {len(batch)} cards (total: {len(cards)}/{total})")
            if len(cards) >= total:
                break
            page += 1
        except ValueError as e:
            if "Not found" in str(e) and not cards:
                raise ValueError(f"Set '{set_id}' not found on pokemontcg.io")
            break

    return cards


# =============================================================================
# PARSING FUNCTIONS
# =============================================================================

def sanitize_name(name: str) -> str:
    """Convert card name to Python variable name."""
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    name = re.sub(r"\s+", "_", name.strip().upper())
    return name


def parse_energy_cost(cost: list) -> str:
    """Parse attack energy cost into our format."""
    if not cost:
        return "[]"

    counts = {}
    for energy in cost:
        mapped = POKEMON_TYPE_MAP.get(energy, "C")
        counts[mapped] = counts.get(mapped, 0) + 1

    parts = []
    for etype, count in sorted(counts.items()):
        parts.append(f'{{"type": "{etype}", "count": {count}}}')
    return "[" + ", ".join(parts) + "]"


def parse_attack(attack: dict) -> str:
    """Parse a single attack into Python dict literal."""
    name = attack.get('name', 'Attack').replace('"', '\\"')
    cost = parse_energy_cost(attack.get('cost', []))
    damage_str = attack.get('damage', '0')
    # Parse damage: may be "30", "20+", "30x", etc.
    damage_num = re.sub(r'[^0-9]', '', str(damage_str)) or '0'
    text = (attack.get('text', '') or '').replace('"', '\\"').replace('\n', ' ')

    return f'{{"name": "{name}", "cost": {cost}, "damage": {damage_num}, "text": "{text}"}}'


def parse_weakness(weaknesses: list) -> tuple[Optional[str], str]:
    """Parse weakness list. Returns (type_code, modifier)."""
    if not weaknesses:
        return None, "x2"
    w = weaknesses[0]
    wtype = POKEMON_TYPE_MAP.get(w.get('type', ''), None)
    modifier = w.get('value', 'x2') or 'x2'
    return wtype, modifier


def parse_resistance(resistances: list) -> tuple[Optional[str], int]:
    """Parse resistance list. Returns (type_code, modifier)."""
    if not resistances:
        return None, -30
    r = resistances[0]
    rtype = POKEMON_TYPE_MAP.get(r.get('type', ''), None)
    modifier_str = r.get('value', '-30') or '-30'
    modifier = int(re.sub(r'[^0-9-]', '', modifier_str) or '-30')
    return rtype, modifier


def parse_retreat_cost(retreat: list) -> int:
    """Parse retreat cost (list of energy types)."""
    return len(retreat) if retreat else 0


def escape_text(text: str) -> str:
    """Escape text for Python string."""
    if not text:
        return '""'
    text = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return f'"{text}"'


# =============================================================================
# CODE GENERATION
# =============================================================================

def generate_pokemon_card(card: dict, var_name: str) -> Optional[str]:
    """Generate code for a Pokemon card."""
    supertype = card.get('supertype', '')
    subtypes = card.get('subtypes', [])
    name = card.get('name', 'Unknown').replace('"', '\\"')
    rarity = (card.get('rarity', 'Common') or 'Common').lower()

    if supertype == 'Pokémon':
        return _generate_pokemon(card, var_name, name, rarity)
    elif supertype == 'Trainer':
        return _generate_trainer(card, var_name, name, subtypes, rarity)
    elif supertype == 'Energy':
        return _generate_energy(card, var_name, name, subtypes, rarity)
    return None


def _generate_pokemon(card: dict, var_name: str, name: str, rarity: str) -> str:
    """Generate a Pokemon card definition."""
    hp = int(card.get('hp', 0) or 0)
    types = card.get('types', ['Colorless'])
    pokemon_type = POKEMON_TYPE_MAP.get(types[0], 'C') if types else 'C'
    subtypes = card.get('subtypes', [])

    # Determine evolution stage
    evolution_stage = "Basic"
    evolves_from = None
    if "Stage 1" in subtypes:
        evolution_stage = "Stage 1"
    elif "Stage 2" in subtypes:
        evolution_stage = "Stage 2"
    if card.get('evolvesFrom'):
        evolves_from = card['evolvesFrom'].replace('"', '\\"')

    # Is ex?
    is_ex = any(r.get('type') == 'Pokémon ex' for r in card.get('rules', []))
    if ' ex' in name.lower():
        is_ex = True

    # Attacks
    attacks = card.get('attacks', [])
    attack_strs = [parse_attack(a) for a in attacks]
    attacks_code = "[\n        " + ",\n        ".join(attack_strs) + ",\n    ]" if attack_strs else "[]"

    # Abilities
    abilities = card.get('abilities', [])
    ability_code = "None"
    if abilities:
        ab = abilities[0]
        ab_name = (ab.get('name', '') or '').replace('"', '\\"')
        ab_text = (ab.get('text', '') or '').replace('"', '\\"').replace('\n', ' ')
        ab_type = ab.get('type', 'Ability')
        ability_code = f'{{"name": "{ab_name}", "text": "{ab_text}", "ability_type": "{ab_type}"}}'

    # Weakness/Resistance/Retreat
    w_type, w_mod = parse_weakness(card.get('weaknesses', []))
    r_type, r_mod = parse_resistance(card.get('resistances', []))
    retreat = parse_retreat_cost(card.get('retreatCost', []))

    # Build rules text from attacks + abilities
    rules_text = []
    for ab in abilities:
        rules_text.append(f"[{ab.get('type', 'Ability')}] {ab.get('name', '')}: {ab.get('text', '')}")
    for atk in attacks:
        dmg = atk.get('damage', '')
        txt = atk.get('text', '')
        rules_text.append(f"{atk.get('name', '')}: {dmg} {txt}".strip())
    text = escape_text(' | '.join(rules_text))

    lines = [
        f'{var_name} = make_pokemon(',
        f'    name="{name}",',
        f'    hp={hp},',
        f'    pokemon_type="{pokemon_type}",',
        f'    evolution_stage="{evolution_stage}",',
    ]
    if evolves_from:
        lines.append(f'    evolves_from="{evolves_from}",')
    lines.append(f'    attacks={attacks_code},')
    if ability_code != "None":
        lines.append(f'    ability={ability_code},')
    if w_type:
        lines.append(f'    weakness_type="{w_type}",')
    if r_type:
        lines.append(f'    resistance_type="{r_type}",')
        lines.append(f'    resistance_modifier={r_mod},')
    lines.append(f'    retreat_cost={retreat},')
    if is_ex:
        lines.append(f'    is_ex=True,')
    lines.append(f'    text={text},')
    lines.append(f'    rarity="{rarity}",')
    lines.append(')')

    return '\n'.join(lines)


def _generate_trainer(card: dict, var_name: str, name: str, subtypes: list, rarity: str) -> str:
    """Generate a Trainer card definition."""
    text = escape_text(' '.join(card.get('rules', []) + [card.get('text', '') or '']))

    if 'Supporter' in subtypes:
        return f'{var_name} = make_trainer_supporter(\n    name="{name}",\n    text={text},\n    rarity="{rarity}",\n)'
    elif 'Stadium' in subtypes:
        return f'{var_name} = make_trainer_stadium(\n    name="{name}",\n    text={text},\n    rarity="{rarity}",\n)'
    elif 'Pokémon Tool' in subtypes:
        return f'{var_name} = make_pokemon_tool(\n    name="{name}",\n    text={text},\n    rarity="{rarity}",\n)'
    else:
        # Default to Item
        return f'{var_name} = make_trainer_item(\n    name="{name}",\n    text={text},\n    rarity="{rarity}",\n)'


def _generate_energy(card: dict, var_name: str, name: str, subtypes: list, rarity: str) -> str:
    """Generate an Energy card definition."""
    if 'Basic' in subtypes:
        # Determine energy type from name
        energy_type = 'C'
        for type_name, code in POKEMON_TYPE_MAP.items():
            if type_name.lower() in name.lower():
                energy_type = code
                break
        return f'{var_name} = make_basic_energy(\n    name="{name}",\n    pokemon_type="{energy_type}",\n)'
    else:
        # Special Energy - treat as Item for now
        text = escape_text(' '.join(card.get('rules', []) + [card.get('text', '') or '']))
        return f'{var_name} = make_trainer_item(\n    name="{name}",\n    text={text},\n    rarity="{rarity}",\n)'


def generate_file(set_id: str, module_name: str, set_name: str, cards: List[dict]) -> tuple[str, dict]:
    """Generate complete Python file for a Pokemon card set."""
    header = f'''"""
{set_name} ({set_id.upper()}) Pokemon TCG Card Definitions

Real card data fetched from pokemontcg.io API.
{len(cards)} cards in set.
"""

from src.engine.game import (
    make_pokemon, make_trainer_item, make_trainer_supporter,
    make_trainer_stadium, make_pokemon_tool, make_basic_energy,
)


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

'''

    card_defs = []
    registry_entries = []
    seen_vars = set()
    stats = {'total': 0, 'pokemon': 0, 'trainer': 0, 'energy': 0, 'skipped': 0}

    for card in cards:
        name = card.get('name', '')
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

        code = generate_pokemon_card(card, var_name)
        if code:
            card_defs.append(code)
            display_name = name
            registry_entries.append(f'    "{display_name}": {var_name},')
            stats['total'] += 1

            supertype = card.get('supertype', '')
            if supertype == 'Pokémon':
                stats['pokemon'] += 1
            elif supertype == 'Trainer':
                stats['trainer'] += 1
            elif supertype == 'Energy':
                stats['energy'] += 1
        else:
            stats['skipped'] += 1

    registry_name = module_name.upper() + "_CARDS"

    footer = f'''

# =============================================================================
# CARD REGISTRY
# =============================================================================

{registry_name} = {{
{chr(10).join(registry_entries)}
}}

print(f"Loaded {{len({registry_name})}} {set_name} Pokemon cards")
'''

    return header + '\n\n'.join(card_defs) + footer, stats


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Fetch Pokemon TCG card data from pokemontcg.io and generate Python definitions.',
    )
    parser.add_argument('set_id', help='pokemontcg.io set ID (e.g., sv6pt5, sv1)')
    parser.add_argument('module_name', help='Python module name (e.g., shrouded_fable)')
    parser.add_argument('set_name', help='Display name (e.g., "Shrouded Fable")')
    parser.add_argument('--update', '-u', action='store_true',
                       help='Update existing file')
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force overwrite')
    parser.add_argument('--dry-run', '-n', action='store_true',
                       help='Show what would be done without writing')
    parser.add_argument('--output', '-o', help='Output path (default: src/cards/pokemon/<module_name>.py)')

    args = parser.parse_args()

    output_path = args.output or f"src/cards/pokemon/{args.module_name}.py"

    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Check if file exists
    file_exists = os.path.exists(output_path)
    if file_exists and not args.update and not args.force and not args.dry_run:
        print(f"ERROR: {output_path} already exists!")
        print("Use --update to update, --force to overwrite, or --dry-run to preview")
        sys.exit(1)

    # Fetch cards
    print(f"Fetching {args.set_name} ({args.set_id}) from pokemontcg.io...")
    try:
        cards = fetch_all_cards(args.set_id)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    print(f"Found {len(cards)} cards")

    # Generate file
    print("Generating Python file...")
    content, stats = generate_file(args.set_id, args.module_name, args.set_name, cards)

    print(f"\nStats:")
    print(f"  Total cards: {stats['total']}")
    print(f"  Pokemon: {stats['pokemon']}")
    print(f"  Trainers: {stats['trainer']}")
    print(f"  Energy: {stats['energy']}")
    print(f"  Skipped: {stats['skipped']}")

    if args.dry_run:
        print(f"\nDry run - would write {len(content)} bytes to {output_path}")
        print("First 800 chars:")
        print("-" * 40)
        print(content[:800])
        print("-" * 40)
    else:
        with open(output_path, 'w') as f:
            f.write(content)
        print(f"\nWritten to {output_path}")


if __name__ == "__main__":
    main()
