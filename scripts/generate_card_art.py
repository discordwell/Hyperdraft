#!/usr/bin/env python3
"""
Card Art Generator - Slay the Spire style sketchy art

Fetches card art from Scryfall and transforms it to a hand-drawn sketch style,
or generates original art for custom sets.
"""

import os
import sys
import json
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO

import torch
from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline

# Use MPS on Apple Silicon, CUDA on NVIDIA, CPU as fallback
# Note: MPS requires float32 to avoid NaN issues
if torch.backends.mps.is_available():
    DEVICE = "mps"
    DTYPE = torch.float32  # float16 causes NaN on MPS
elif torch.cuda.is_available():
    DEVICE = "cuda"
    DTYPE = torch.float16
else:
    DEVICE = "cpu"
    DTYPE = torch.float32

print(f"Using device: {DEVICE}")

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
ART_BASE = PROJECT_DIR / "assets" / "card_art"
MTG_ART_DIR = ART_BASE / "mtg"
CUSTOM_ART_DIR = ART_BASE / "custom"
CACHE_DIR = ART_BASE / ".cache"

# Create directories
for d in [MTG_ART_DIR, CUSTOM_ART_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Base style prompts
BASE_SKETCH_STYLE = "hand-drawn sketch, limited color palette, indie game art style, rough brushstrokes, concept art, Slay the Spire style"
NEGATIVE_PROMPT = "photorealistic, 3d render, photograph, high detail, smooth, polished, digital art"

# Model - using SD 1.5 for speed, can upgrade to SDXL later
MODEL_ID = "runwayml/stable-diffusion-v1-5"

# =============================================================================
# SET THEMES - Consistent style per set
# =============================================================================

# MTG Sets - capture the aesthetic/setting of each set
MTG_SET_THEMES = {
    # 2023-2024 Standard sets
    "woe": {"name": "Wilds of Eldraine", "style": "dark fairy tale, Brothers Grimm, enchanted forest, storybook illustration", "palette": "deep greens, purples, gold accents"},
    "lci": {"name": "Lost Caverns of Ixalan", "style": "Mesoamerican temples, underground caverns, dinosaurs, ancient ruins", "palette": "warm earth tones, jade green, gold"},
    "mkm": {"name": "Murders at Karlov Manor", "style": "noir detective, gothic mansion, Ravnica cityscape, mystery", "palette": "muted grays, deep reds, gaslight amber"},
    "otj": {"name": "Outlaws of Thunder Junction", "style": "weird west, desert frontier, outlaws, cacti, steam-tech", "palette": "dusty oranges, turquoise, leather brown"},
    "blb": {"name": "Bloomburrow", "style": "cozy woodland, anthropomorphic animals, cottagecore, tiny adventurers", "palette": "warm pastels, forest greens, sunset orange"},
    "dsk": {"name": "Duskmourn", "style": "80s horror, haunted house, survival horror, VHS aesthetic", "palette": "neon pink, deep shadows, sickly green"},
    "fdn": {"name": "Foundations", "style": "classic fantasy, iconic magic, timeless", "palette": "rich primaries, classic fantasy colors"},

    # Universes Beyond
    "fin": {"name": "Final Fantasy", "style": "JRPG, crystals, chocobos, moogles, epic fantasy", "palette": "vibrant blues, crystalline, dramatic lighting"},
    "spm": {"name": "Spider-Man", "style": "comic book, New York cityscape, web-slinging, Marvel", "palette": "red and blue, urban grays, dynamic action"},
    "tla": {"name": "Avatar TLA", "style": "anime, elemental bending, Asian-inspired, four nations", "palette": "elemental colors - red fire, blue water, green earth, orange air"},
}

# Custom/Fan-made Sets - original themed art
CUSTOM_SET_THEMES = {
    "star_wars": {"style": "space opera, lightsabers, droids, starships", "palette": "deep space blues, saber glows, imperial gray"},
    "lord_of_the_rings": {"style": "high fantasy, Middle-earth, epic quest", "palette": "earthy browns, elven silver, volcanic red"},
    "studio_ghibli": {"style": "Miyazaki watercolor, whimsical, nature spirits, flying machines", "palette": "soft pastels, sky blue, forest green"},
    "pokemon_horizons": {"style": "creature collection, evolution, Pokemon trainer", "palette": "bright and cheerful, type-based colors"},
    "naruto": {"style": "ninja anime, jutsu, hidden villages, Shonen action", "palette": "orange energy, leaf green, sharingan red"},
    "dragon_ball": {"style": "martial arts anime, ki energy, transformations, Shonen power", "palette": "golden aura, orange gi, energy blue"},
    "harry_potter": {"style": "British wizarding, Hogwarts castle, magical creatures", "palette": "house colors, candlelit warmth, magical purple"},
    "marvel_avengers": {"style": "superhero comic, team dynamics, cosmic threats", "palette": "primary hero colors, cosmic purple"},
    "one_piece": {"style": "pirate adventure, devil fruits, Grand Line seas", "palette": "ocean blue, straw hat gold, vibrant crew colors"},
    "attack_on_titan": {"style": "dark military fantasy, titans, walled cities, ODM gear", "palette": "muted military, blood red, stone gray"},
    "demon_slayer": {"style": "Taisho-era Japan, breathing techniques, demon hunting", "palette": "checkered patterns, flame orange, water blue"},
    "jujutsu_kaisen": {"style": "cursed energy, modern Tokyo, sorcerers vs curses", "palette": "dark purple cursed energy, school uniform blue"},
    "my_hero_academia": {"style": "superhero academy, quirks, hero costumes", "palette": "UA blue, heroic primaries, villain purple"},
    "legend_of_zelda": {"style": "Hyrule adventure, dungeons, Master Sword, Triforce", "palette": "Hylian green, golden Triforce, royal blue"},
    "temporal_horizons": {"style": "time magic, temporal rifts, past and future colliding", "palette": "temporal gold, void purple, reality fractures"},
    "lorwyn_custom": {"style": "Celtic fairy tale, tribal creatures, idyllic then dark", "palette": "autumn gold, twilight purple, fae green"},
}

def get_set_style(set_code: str = None, custom_set: str = None) -> tuple[str, str]:
    """Get style prompt and color palette for a set."""
    if set_code and set_code.lower() in MTG_SET_THEMES:
        theme = MTG_SET_THEMES[set_code.lower()]
        return theme["style"], theme["palette"]
    elif custom_set and custom_set.lower() in CUSTOM_SET_THEMES:
        theme = CUSTOM_SET_THEMES[custom_set.lower()]
        return theme["style"], theme["palette"]
    else:
        return "fantasy card game art", "rich fantasy colors"

_img2img_pipe = None
_txt2img_pipe = None


def get_img2img_pipeline():
    """Lazy-load img2img pipeline."""
    global _img2img_pipe
    if _img2img_pipe is None:
        print("Loading img2img model (first run will download ~4GB)...")
        _img2img_pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=DTYPE,
            safety_checker=None,  # Disable for speed
            requires_safety_checker=False,
        )
        _img2img_pipe.to(DEVICE)
        # Optimization for Apple Silicon
        if DEVICE == "mps":
            _img2img_pipe.enable_attention_slicing()
    return _img2img_pipe


def get_txt2img_pipeline():
    """Lazy-load txt2img pipeline."""
    global _txt2img_pipe
    if _txt2img_pipe is None:
        print("Loading txt2img model...")
        _txt2img_pipe = StableDiffusionPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=DTYPE,
            safety_checker=None,
            requires_safety_checker=False,
        )
        _txt2img_pipe.to(DEVICE)
        if DEVICE == "mps":
            _txt2img_pipe.enable_attention_slicing()
    return _txt2img_pipe


def fetch_scryfall_art(card_name: str, set_code: str = None, retries: int = 3) -> Image.Image | None:
    """Fetch card art from Scryfall API with retries."""
    import time as time_module

    url = f"https://api.scryfall.com/cards/named?fuzzy={requests.utils.quote(card_name)}"
    if set_code:
        url += f"&set={set_code}"

    for attempt in range(retries):
        try:
            # Rate limit: Scryfall asks for 50-100ms between requests
            time_module.sleep(0.1)

            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Get art crop URL
            art_url = data.get("image_uris", {}).get("art_crop")
            if not art_url:
                # Try card_faces for double-faced cards
                faces = data.get("card_faces", [])
                if faces:
                    art_url = faces[0].get("image_uris", {}).get("art_crop")

            if not art_url:
                return None

            # Fetch the image
            img_resp = requests.get(art_url, timeout=30)
            img_resp.raise_for_status()
            return Image.open(BytesIO(img_resp.content)).convert("RGB")

        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time_module.sleep(1)  # Wait before retry
                continue
            return None
        except Exception as e:
            return None

    return None


def sketchify_image(
    image: Image.Image,
    prompt_addition: str = "",
    set_code: str = None,
    strength: float = 0.65,
    guidance_scale: float = 7.5,
    seed: int = None,
) -> Image.Image:
    """Transform an image to sketchy Slay the Spire style with set-consistent theming."""
    pipe = get_img2img_pipeline()

    # Resize to model-friendly dimensions
    width, height = image.size
    # SD 1.5 works best with 512x512, scale proportionally
    max_dim = 512
    if width > height:
        new_width = max_dim
        new_height = int(height * max_dim / width)
    else:
        new_height = max_dim
        new_width = int(width * max_dim / height)

    # Round to multiple of 8
    new_width = (new_width // 8) * 8
    new_height = (new_height // 8) * 8

    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Build prompt with set theme
    set_style, set_palette = get_set_style(set_code=set_code)
    prompt_parts = [BASE_SKETCH_STYLE, set_style, f"color palette: {set_palette}"]
    if prompt_addition:
        prompt_parts.append(prompt_addition)
    prompt = ", ".join(prompt_parts)

    # Use consistent seed per set for style consistency
    generator = None
    if seed is not None:
        generator = torch.Generator(device=DEVICE).manual_seed(seed)

    result = pipe(
        prompt=prompt,
        image=image,
        strength=strength,
        guidance_scale=guidance_scale,
        negative_prompt=NEGATIVE_PROMPT,
        num_inference_steps=30,
        generator=generator,
    ).images[0]

    return result


def generate_art(
    prompt: str,
    custom_set: str = None,
    width: int = 512,
    height: int = 384,
    guidance_scale: float = 7.5,
    seed: int = None,
) -> Image.Image:
    """Generate original art from text prompt with set-consistent theming."""
    pipe = get_txt2img_pipeline()

    # Build prompt with set theme
    set_style, set_palette = get_set_style(custom_set=custom_set)
    full_prompt = f"{BASE_SKETCH_STYLE}, {set_style}, color palette: {set_palette}, {prompt}"

    # Use consistent seed per set for style consistency
    generator = None
    if seed is not None:
        generator = torch.Generator(device=DEVICE).manual_seed(seed)

    result = pipe(
        prompt=full_prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=width,
        height=height,
        guidance_scale=guidance_scale,
        num_inference_steps=30,
        generator=generator,
    ).images[0]

    return result


def get_set_seed(set_code: str) -> int:
    """Generate a consistent seed from set code for reproducible style."""
    # Hash the set code to get a consistent seed
    return hash(set_code.lower()) % (2**32)


def sanitize_filename(name: str) -> str:
    """Convert card name to safe filename."""
    return name.replace(" ", "_").replace("'", "").replace(",", "").replace(":", "").replace("/", "_").lower()


def process_mtg_card(card_name: str, set_code: str, strength: float = 0.55) -> Path | None:
    """Fetch MTG card art and sketchify it with set-consistent style."""
    # Output in mtg/set_code/card_name.png
    set_dir = MTG_ART_DIR / set_code.lower()
    set_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(card_name)
    output_path = set_dir / f"{safe_name}.png"

    if output_path.exists():
        return output_path  # Silent skip for bulk

    # Fetch original art
    original = fetch_scryfall_art(card_name, set_code)
    if not original:
        return None

    # Get set-based seed for consistency
    seed = get_set_seed(set_code)

    # Sketchify with set theme
    sketched = sketchify_image(
        original,
        prompt_addition=f"fantasy card art, {card_name}",
        set_code=set_code,
        strength=strength,
        seed=seed,
    )

    # Save
    sketched.save(output_path)
    return output_path


def process_custom_card(
    card_name: str,
    card_type: str,
    colors: list[str],
    custom_set: str,
) -> Path | None:
    """Generate original art for custom card with set-consistent style."""
    # Output in custom/set_name/card_name.png
    set_dir = CUSTOM_ART_DIR / custom_set.lower()
    set_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(card_name)
    output_path = set_dir / f"{safe_name}.png"

    if output_path.exists():
        return output_path  # Silent skip for bulk

    # Build prompt from card properties
    color_desc = ", ".join(colors) if colors else "colorless"
    prompt = f"{card_name}, {card_type}, {color_desc} magic, fantasy art"

    # Get set-based seed for consistency
    seed = get_set_seed(custom_set)

    art = generate_art(prompt, custom_set=custom_set, seed=seed)
    art.save(output_path)
    return output_path


# =============================================================================
# BULK PROCESSING
# =============================================================================

# Map Python module names to Scryfall set codes
MODULE_TO_SET_CODE = {
    "wilds_of_eldraine": "woe",
    "lost_caverns_ixalan": "lci",
    "murders_karlov_manor": "mkm",
    "outlaws_thunder_junction": "otj",
    "bloomburrow": "blb",
    "duskmourn": "dsk",
    "foundations": "fdn",
    "edge_of_eternities": "mh3",  # Modern Horizons 3
    "lorwyn_eclipsed": "lrw",     # Original Lorwyn
    "spider_man": "spm",          # Universes Beyond
    "avatar_tla": "atla",         # Universes Beyond
    "final_fantasy": "ff",        # Universes Beyond (approximate)
}


def extract_card_names(filepath: Path) -> list[tuple[str, str, list[str]]]:
    """
    Extract card names, types, and colors from a card set Python file.
    Returns list of (name, type, colors) tuples.
    """
    import re

    cards = []
    content = filepath.read_text()

    # Match card definitions: CARD_NAME = make_type(name="Card Name", ...)
    pattern = r'(\w+)\s*=\s*make_(\w+)\(\s*name="([^"]+)"'

    for match in re.finditer(pattern, content):
        var_name, card_type, card_name = match.groups()

        # Extract colors if present
        # Look for colors={Color.X, Color.Y} after this definition
        start = match.end()
        end = content.find(')', start) + 200  # Look ahead
        snippet = content[start:end] if end > start else ""

        colors = []
        color_match = re.search(r'colors=\{([^}]+)\}', snippet)
        if color_match:
            color_str = color_match.group(1)
            for c in ['WHITE', 'BLUE', 'BLACK', 'RED', 'GREEN']:
                if c in color_str:
                    colors.append(c.lower())

        cards.append((card_name, card_type, colors))

    return cards


def bulk_process_mtg_set(module_name: str, limit: int = None) -> dict:
    """Process all cards from an MTG set."""
    set_code = MODULE_TO_SET_CODE.get(module_name)
    if not set_code:
        print(f"Unknown set: {module_name}, skipping")
        return {"processed": 0, "failed": 0, "skipped": 0}

    filepath = PROJECT_DIR / "src" / "cards" / f"{module_name}.py"
    if not filepath.exists():
        print(f"File not found: {filepath}")
        return {"processed": 0, "failed": 0, "skipped": 0}

    cards = extract_card_names(filepath)
    if limit:
        cards = cards[:limit]

    stats = {"processed": 0, "failed": 0, "skipped": 0}

    print(f"\n{'='*60}")
    print(f"Processing MTG set: {module_name} ({set_code.upper()}) - {len(cards)} cards")
    print(f"{'='*60}")

    for i, (name, card_type, colors) in enumerate(cards):
        # Check if already exists
        set_dir = MTG_ART_DIR / set_code.lower()
        safe_name = sanitize_filename(name)
        if (set_dir / f"{safe_name}.png").exists():
            stats["skipped"] += 1
            continue

        print(f"[{i+1}/{len(cards)}] {name}...", end=" ", flush=True)
        try:
            path = process_mtg_card(name, set_code)
            if path:
                print("✓")
                stats["processed"] += 1
            else:
                print("✗ (no art)")
                stats["failed"] += 1
        except Exception as e:
            print(f"✗ ({e})")
            stats["failed"] += 1

    print(f"\nCompleted: {stats['processed']} processed, {stats['skipped']} skipped, {stats['failed']} failed")
    return stats


def bulk_process_custom_set(module_name: str, limit: int = None) -> dict:
    """Process all cards from a custom set."""
    filepath = PROJECT_DIR / "src" / "cards" / "custom" / f"{module_name}.py"
    if not filepath.exists():
        print(f"File not found: {filepath}")
        return {"processed": 0, "failed": 0, "skipped": 0}

    cards = extract_card_names(filepath)
    if limit:
        cards = cards[:limit]

    stats = {"processed": 0, "failed": 0, "skipped": 0}

    print(f"\n{'='*60}")
    print(f"Processing custom set: {module_name} - {len(cards)} cards")
    print(f"{'='*60}")

    for i, (name, card_type, colors) in enumerate(cards):
        # Check if already exists
        set_dir = CUSTOM_ART_DIR / module_name.lower()
        safe_name = sanitize_filename(name)
        if (set_dir / f"{safe_name}.png").exists():
            stats["skipped"] += 1
            continue

        print(f"[{i+1}/{len(cards)}] {name}...", end=" ", flush=True)
        try:
            path = process_custom_card(name, card_type, colors, module_name)
            if path:
                print("✓")
                stats["processed"] += 1
            else:
                print("✗")
                stats["failed"] += 1
        except Exception as e:
            print(f"✗ ({e})")
            stats["failed"] += 1

    print(f"\nCompleted: {stats['processed']} processed, {stats['skipped']} skipped, {stats['failed']} failed")
    return stats


def bulk_process_all(mtg: bool = True, custom: bool = True, limit_per_set: int = None):
    """Process all card sets."""
    total_stats = {"processed": 0, "failed": 0, "skipped": 0}

    if mtg:
        print("\n" + "="*70)
        print("PROCESSING MTG SETS")
        print("="*70)
        for module_name in MODULE_TO_SET_CODE.keys():
            stats = bulk_process_mtg_set(module_name, limit=limit_per_set)
            for k in total_stats:
                total_stats[k] += stats[k]

    if custom:
        print("\n" + "="*70)
        print("PROCESSING CUSTOM SETS")
        print("="*70)
        custom_dir = PROJECT_DIR / "src" / "cards" / "custom"
        for filepath in sorted(custom_dir.glob("*.py")):
            if filepath.name.startswith("__"):
                continue
            module_name = filepath.stem
            stats = bulk_process_custom_set(module_name, limit=limit_per_set)
            for k in total_stats:
                total_stats[k] += stats[k]

    print("\n" + "="*70)
    print("BULK PROCESSING COMPLETE")
    print(f"Total: {total_stats['processed']} processed, {total_stats['skipped']} skipped, {total_stats['failed']} failed")
    print("="*70)


def demo():
    """Run a quick demo with set-themed cards."""
    print("=" * 60)
    print("Card Art Generator Demo - Set Theming")
    print("=" * 60)

    # Test MTG cards from different sets to show style variation
    mtg_test_cards = [
        ("Mosswood Dreadknight", "woe"),   # Wilds of Eldraine - dark fairy tale
        ("Huatli, Poet of Unity", "lci"),  # Lost Caverns - Mesoamerican
        ("Kellan, Daring Traveler", "mkm"), # Karlov Manor - noir detective
        ("Valgavoth, Terror Eater", "dsk"),  # Duskmourn - 80s horror
    ]

    print("\n--- MTG Cards with Set Themes ---")
    for card_name, set_code in mtg_test_cards:
        theme = MTG_SET_THEMES.get(set_code, {})
        print(f"\n  Set: {theme.get('name', set_code.upper())}")
        print(f"  Style: {theme.get('style', 'default')[:50]}...")
        path = process_mtg_card(card_name, set_code, strength=0.55)
        if path:
            print(f"  ✓ {card_name} -> {path.name}")

    # Test custom cards from themed sets
    custom_test_cards = [
        ("Darth Vader", "Creature", ["black"], "star_wars"),
        ("Totoro", "Creature", ["green"], "studio_ghibli"),
        ("Pikachu", "Creature", ["yellow"], "pokemon_horizons"),
    ]

    print("\n--- Custom Cards with Set Themes ---")
    for card_name, card_type, colors, custom_set in custom_test_cards:
        theme = CUSTOM_SET_THEMES.get(custom_set, {})
        print(f"\n  Set: {custom_set}")
        print(f"  Style: {theme.get('style', 'default')[:50]}...")
        path = process_custom_card(card_name, card_type, colors, custom_set)
        if path:
            print(f"  ✓ {card_name} -> {path.name}")

    print("\n" + "=" * 60)
    print(f"Generated art saved to: {ART_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate card art for Hyperdraft")
    parser.add_argument("--demo", action="store_true", help="Run quick demo")
    parser.add_argument("--bulk", action="store_true", help="Process all cards")
    parser.add_argument("--mtg-only", action="store_true", help="Only process MTG sets")
    parser.add_argument("--custom-only", action="store_true", help="Only process custom sets")
    parser.add_argument("--set", type=str, help="Process specific set (e.g., bloomburrow, star_wars)")
    parser.add_argument("--limit", type=int, help="Limit cards per set (for testing)")
    parser.add_argument("--card", type=str, help="Process single card by name")

    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.bulk:
        mtg = not args.custom_only
        custom = not args.mtg_only
        bulk_process_all(mtg=mtg, custom=custom, limit_per_set=args.limit)
    elif args.set:
        # Check if it's MTG or custom
        if args.set in MODULE_TO_SET_CODE:
            bulk_process_mtg_set(args.set, limit=args.limit)
        else:
            bulk_process_custom_set(args.set, limit=args.limit)
    elif args.card:
        process_mtg_card(args.card, None)
    else:
        parser.print_help()
