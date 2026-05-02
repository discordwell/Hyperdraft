#!/usr/bin/env python3
"""
Beyond Kamigawa — card-art generator.

For each Beyond Kamigawa card:
  1. Pick the best YGO style reference from the library at
     ``assets/card_art/beyond/kamigawa/refs/_manifest.json`` by matching
     (Race, Attribute, Level-band).
  2. Build a prompt that fuses MTG-Kamigawa flavor (the card's name and
     text) with the YGO art style of the reference.
  3. Call the OpenAI Responses API with ``image_generation`` tool, passing
     the local reference image as ``input_image`` so the generator
     stylistically anchors to the reference.
  4. Save the rendered PNG to
     ``assets/card_art/beyond/kamigawa/<card_slug>.png``.

Modes (mirrors ``scripts/generate_riftclash_art.py``):
  - api     — generate via OpenAI (default)
  - manual  — emit a prompt-pack JSON for manual paste-into-ChatGPT use
  - local   — deterministic procedural fallback (offline)

Usage::

    python scripts/beyond_kamigawa/generate_card_art.py --limit 5         # smoke
    python scripts/beyond_kamigawa/generate_card_art.py --force --limit 1 # regen 1
    python scripts/beyond_kamigawa/generate_card_art.py                   # full set
    python scripts/beyond_kamigawa/generate_card_art.py --mode manual     # JSON pack
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cards.yugioh.beyond.kamigawa import BEYOND_KAMIGAWA_CARDS
from src.engine.types import CardType


REFS_DIR = PROJECT_ROOT / "assets" / "card_art" / "beyond" / "kamigawa" / "refs"
REFS_MANIFEST = REFS_DIR / "_manifest.json"
OUT_DIR = PROJECT_ROOT / "assets" / "card_art" / "beyond" / "kamigawa"
PROMPT_PACK_PATH = OUT_DIR / "draw_prompts.json"

DEFAULT_MODEL = "chatgpt-image-latest"
DEFAULT_DRAW_MODEL = "gpt-5"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_PROVIDER = "auto"


# =============================================================================
# Config / dotenv
# =============================================================================

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass
class OpenAiImageConfig:
    api_key: str
    model: str
    draw_model: str
    provider: str
    size: str
    quality: str
    timeout_s: float


# =============================================================================
# Reference-library lookup
# =============================================================================

@dataclass
class RefMatch:
    """The chosen YGO reference for a Beyond Kamigawa card."""
    key: str
    ygo_name: str
    local_path: Path
    description: str


def _level_band(level: int | None) -> str:
    if level is None:
        return "any"
    if level <= 2:
        return "1_2"
    if level <= 4:
        return "3_4"
    if level <= 6:
        return "5_6"
    if level <= 8:
        return "7_8"
    return "9_plus"


def _load_refs_index() -> tuple[list[dict], dict[str, dict]]:
    """Load the refs manifest and return (entries, by_key)."""
    if not REFS_MANIFEST.exists():
        raise RuntimeError(
            f"Reference manifest not found at {REFS_MANIFEST}. "
            "Run scripts/beyond_kamigawa/fetch_ygo_refs.py first."
        )
    data = json.loads(REFS_MANIFEST.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    by_key = {e["key"]: e for e in entries if "key" in e}
    return entries, by_key


# Mapping of YGO Race (the API's "race" field on monster cards) to a list of
# library key prefixes, in priority order. Beyond Kamigawa only uses these
# Races (read off the source files); anything else falls back to ``warrior``.
_RACE_TO_PREFIX = {
    "Warrior": ["warrior"],
    "Beast-Warrior": ["beastwarrior", "warrior", "beast"],
    "Beast": ["beast", "beastwarrior"],
    "Spellcaster": ["spellcaster"],
    "Dragon": ["dragon"],
    "Machine": ["machine"],
    "Wing Beast": ["wingbeast"],            # YGO actually calls this "Winged Beast"
    "Winged Beast": ["wingbeast"],
    "Fiend": ["fiend"],
    "Fairy": ["fairy"],
    "Plant": ["plant"],
    "Rock": ["rock"],
    "Reptile": ["reptile"],
    "Pyro": ["pyro"],
    "Insect": ["insect"],
    "Sea Serpent": ["dragon", "wingbeast"],  # Lean on dragon/wingbeast palettes
    "Aqua": ["spellcaster", "wingbeast"],
    "Cyberse": ["machine"],
    "Divine-Beast": ["dragon"],
}


def _card_race(card) -> str | None:
    """Pull the YGO Race from a CardDefinition's subtypes set.

    Beyond Kamigawa encodes archetype membership in the same subtypes set
    (e.g. ``{"Warrior", "Samurai"}``). We strip the archetype tags to find
    the engine-level Race.
    """
    if not card.characteristics:
        return None
    subs = set(card.characteristics.subtypes or set())
    archetype_tags = {"Samurai", "Ninja", "Spirit", "Moonfolk", "Modified"}
    racy = subs - archetype_tags
    if not racy:
        return None
    # Prefer specific over generic
    priority = ["Dragon", "Spellcaster", "Machine", "Warrior", "Beast-Warrior",
                "Beast", "Wing Beast", "Winged Beast", "Fiend", "Fairy",
                "Plant", "Rock", "Reptile", "Pyro", "Insect", "Cyberse",
                "Sea Serpent", "Aqua", "Divine-Beast"]
    for p in priority:
        if p in racy:
            return p
    # Fallback: any remaining subtype string
    return next(iter(racy))


def pick_reference(card, by_key: dict[str, dict]) -> RefMatch:
    """Choose the best YGO reference for a Beyond Kamigawa card.

    Match priority:
      1. Card-frame (Spell/Trap/ExtraDeck) matches override Race-based picks.
      2. ``{race_prefix}_{attr}_lv{band}``  — exact match.
      3. ``{race_prefix}_{attr}_*``         — same race+attr, any level.
      4. ``{race_prefix}_*``                — same race only.
      5. Default fallback ``warrior_light_lv7_8``.
    """
    types = card.characteristics.types if card.characteristics else set()

    # --- Spell / Trap / Extra-Deck overrides ---
    if CardType.YGO_SPELL in types:
        spell_type = (getattr(card, "ygo_spell_type", "") or "Normal").lower()
        spell_keys = {
            "normal": "spell_normal",
            "quick-play": "spell_quickplay",
            "quickplay": "spell_quickplay",
            "continuous": "spell_continuous",
            "equip": "spell_equip",
            "field": "spell_field",
            "ritual": "spell_ritual",
        }
        candidate = spell_keys.get(spell_type, "spell_normal")
        if candidate in by_key:
            ref = by_key[candidate]
            return RefMatch(candidate, ref.get("ygo_name", ""),
                            REFS_DIR / f"{candidate}.jpg",
                            ref.get("description", ""))

    if CardType.YGO_TRAP in types:
        trap_type = (getattr(card, "ygo_trap_type", "") or "Normal").lower()
        trap_keys = {
            "normal": "trap_normal",
            "continuous": "trap_continuous",
            "counter": "trap_counter",
        }
        candidate = trap_keys.get(trap_type, "trap_normal")
        if candidate in by_key:
            ref = by_key[candidate]
            return RefMatch(candidate, ref.get("ygo_name", ""),
                            REFS_DIR / f"{candidate}.jpg",
                            ref.get("description", ""))

    # Extra Deck monster types take precedence over Race-based lookup
    monster_type = (getattr(card, "ygo_monster_type", "") or "").lower()
    if monster_type == "synchro":
        race = _card_race(card)
        candidate = "synchro_dragon_lv8" if race == "Dragon" else "synchro_warrior_lv5"
        if candidate in by_key:
            ref = by_key[candidate]
            return RefMatch(candidate, ref.get("ygo_name", ""),
                            REFS_DIR / f"{candidate}.jpg",
                            ref.get("description", ""))
    if monster_type == "xyz" and "xyz_warrior_rank4" in by_key:
        ref = by_key["xyz_warrior_rank4"]
        return RefMatch("xyz_warrior_rank4", ref.get("ygo_name", ""),
                        REFS_DIR / "xyz_warrior_rank4.jpg", ref.get("description", ""))
    if monster_type == "fusion" and "fusion_dragon_high" in by_key:
        ref = by_key["fusion_dragon_high"]
        return RefMatch("fusion_dragon_high", ref.get("ygo_name", ""),
                        REFS_DIR / "fusion_dragon_high.jpg", ref.get("description", ""))
    if monster_type == "link" and "link_warrior" in by_key:
        ref = by_key["link_warrior"]
        return RefMatch("link_warrior", ref.get("ygo_name", ""),
                        REFS_DIR / "link_warrior.jpg", ref.get("description", ""))
    if monster_type == "pendulum" and "pendulum_dragon" in by_key:
        ref = by_key["pendulum_dragon"]
        return RefMatch("pendulum_dragon", ref.get("ygo_name", ""),
                        REFS_DIR / "pendulum_dragon.jpg", ref.get("description", ""))

    # --- Main-deck monsters: match by (race, attribute, level_band) ---
    race = _card_race(card)
    attr = (getattr(card, "attribute", "") or "").lower()
    level = getattr(card, "level", None)
    band = _level_band(level)

    prefixes = _RACE_TO_PREFIX.get(race or "", ["warrior"])

    # Try keys in order of specificity
    for prefix in prefixes:
        if attr:
            # Exact: prefix_attr_lvBAND
            for variant in (f"{prefix}_{attr}_lv{band}", f"{prefix}_{attr}_lv{band[:1]}"):
                if variant in by_key:
                    ref = by_key[variant]
                    return RefMatch(variant, ref.get("ygo_name", ""),
                                    REFS_DIR / f"{variant}.jpg",
                                    ref.get("description", ""))
            # Same prefix+attr, any level — search by prefix
            for k in by_key:
                if k.startswith(f"{prefix}_{attr}_"):
                    ref = by_key[k]
                    return RefMatch(k, ref.get("ygo_name", ""),
                                    REFS_DIR / f"{k}.jpg",
                                    ref.get("description", ""))
        # Same prefix, any attribute
        for k in by_key:
            if k.startswith(f"{prefix}_"):
                ref = by_key[k]
                return RefMatch(k, ref.get("ygo_name", ""),
                                REFS_DIR / f"{k}.jpg",
                                ref.get("description", ""))

    # Universal fallback
    fallback = "warrior_light_lv7_8"
    if fallback in by_key:
        ref = by_key[fallback]
        return RefMatch(fallback, ref.get("ygo_name", ""),
                        REFS_DIR / f"{fallback}.jpg",
                        ref.get("description", ""))
    raise RuntimeError(f"No reference available for card {card.name}")


# =============================================================================
# Prompt building
# =============================================================================

# Locked style headline — the conceit is that Konami designers ripped MTG.
STYLE_HEADLINE = (
    "Yu-Gi-Oh! Trading Card Game illustration in the modern Konami "
    "house style: glossy ink-and-paint finish, dramatic chiaroscuro "
    "lighting with rim-light, sharp pen-line outlines, exaggerated "
    "anime-influenced proportions, dynamic action pose, intricate "
    "armor and ornament detail. Single subject dominates a 1:1 "
    "square frame. NO text, NO logos, NO card frame, NO borders, "
    "NO ATK/DEF numbers — illustration only."
)


def _archetype_of(card) -> str:
    if not card.characteristics:
        return ""
    subs = card.characteristics.subtypes or set()
    for tag in ("Samurai", "Ninja", "Spirit", "Moonfolk", "Modified"):
        if tag in subs:
            return tag
    return ""


def _archetype_flavor(archetype: str) -> str:
    """One-sentence flavor tag the prompt prepends so each archetype's art
    has a distinctive shared aesthetic (Kamigawa block + Neon Dynasty)."""
    return {
        "Samurai": (
            "Kamigawa-plane noble samurai aesthetic — feudal-Japan armor, "
            "katana, sashimono banner, cherry-blossom petals, Eiganjo "
            "castle silhouettes, white-and-gold imperial palette."
        ),
        "Ninja": (
            "Kamigawa-plane shadow-ninja aesthetic — black silk wrappings, "
            "kunai/shuriken, mist and moonlight, cobalt-blue and indigo "
            "palette, stealthy crouched poses."
        ),
        "Spirit": (
            "Kamigawa-plane kami-spirit aesthetic — translucent paper "
            "ribbons, paper-lantern glow, shrine torii silhouettes, "
            "floating divine sigils, ethereal pastel palette."
        ),
        "Moonfolk": (
            "Kamigawa-plane Soratami moonfolk aesthetic — pale-skinned "
            "winged sages, robes of cloud-silk, drifting cherry petals, "
            "moonlit indigo-and-silver palette."
        ),
        "Modified": (
            "Neon-Dynasty cyber-Kamigawa aesthetic — chrome armor with "
            "kanji-glyph etching, holographic ofuda paper-charms, neon-"
            "magenta and electric-cyan accents, cyberpunk Japan palette."
        ),
    }.get(archetype, "")


def build_prompt(card) -> str:
    arche = _archetype_of(card)
    arche_line = _archetype_flavor(arche)
    flavor_text = " ".join((card.text or "").split()).strip()
    parts = [
        STYLE_HEADLINE,
        f"Card name: {card.name}.",
    ]
    if arche_line:
        parts.append(arche_line)
    if flavor_text:
        # Truncate text — long rules text adds noise to the visual prompt
        if len(flavor_text) > 240:
            flavor_text = flavor_text[:237] + "..."
        parts.append(f"Card flavor / behavior cue: {flavor_text}")
    parts.append(
        "Match the OVERALL visual style, palette intensity, and "
        "composition energy of the attached reference image; "
        "the SUBJECT must be different — depict the named character "
        "above, not the reference's character."
    )
    return " ".join(parts)


# =============================================================================
# OpenAI calls
# =============================================================================

def fetch_binary_from_url(url: str, timeout_s: float) -> bytes:
    response = requests.get(url, timeout=timeout_s)
    response.raise_for_status()
    return response.content


def maybe_base64_to_bytes(value: Any) -> bytes | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return base64.b64decode(stripped, validate=False)
    except Exception:
        return None


def extract_image_bytes_from_payload(payload: Any, timeout_s: float) -> bytes:
    if not isinstance(payload, (dict, list)):
        raise RuntimeError("OpenAI response payload was empty")

    queue: list[Any] = [payload]
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            for key in ("b64_json", "image_base64", "result"):
                data = maybe_base64_to_bytes(node.get(key))
                if data:
                    return data
            url = node.get("url")
            if not isinstance(url, str):
                url = node.get("image_url")
            if isinstance(url, str) and (url.startswith("https://") or url.startswith("http://")):
                return fetch_binary_from_url(url, timeout_s=timeout_s)
            for key in ("data", "output", "content", "images"):
                child = node.get(key)
                if isinstance(child, list):
                    queue.extend(child)
                elif isinstance(child, dict):
                    queue.append(child)
        elif isinstance(node, list):
            queue.extend(node)

    raise RuntimeError("OpenAI response had no image payload")


def _ref_as_data_url(ref_path: Path) -> str:
    raw = ref_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def generate_via_responses(prompt: str, ref_path: Path, cfg: OpenAiImageConfig) -> bytes:
    """Use the Responses API with image_generation tool, attaching the
    YGO reference image as multimodal input.
    """
    data_url = _ref_as_data_url(ref_path)
    payload = {
        "model": cfg.draw_model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        "tools": [
            {
                "type": "image_generation",
                "size": cfg.size,
                "quality": cfg.quality,
                "background": "opaque",
                "output_format": "png",
            }
        ],
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=cfg.timeout_s,
    )
    if not response.ok:
        raise RuntimeError(f"Responses API failed ({response.status_code}): {response.text[:240]}")
    return extract_image_bytes_from_payload(response.json(), timeout_s=cfg.timeout_s)


def generate_via_images(prompt: str, ref_path: Path, cfg: OpenAiImageConfig) -> bytes:
    """Fallback: prompt-only generation via the images endpoint.

    The /v1/images/generations endpoint doesn't accept a reference image.
    For style continuity, we encode the reference's filename role into
    the prompt text instead. (Lower fidelity than Responses API.)
    """
    payload = {
        "model": cfg.model,
        "prompt": prompt + " [Note: style anchor was provided as an attached reference image in the source request; carry the same color palette, ink-line weight, and dynamic-pose energy.]",
        "size": cfg.size,
        "quality": cfg.quality,
        "output_format": "png",
        "background": "opaque",
    }
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=cfg.timeout_s,
    )
    if not response.ok:
        raise RuntimeError(f"Images API failed ({response.status_code}): {response.text[:240]}")
    return extract_image_bytes_from_payload(response.json(), timeout_s=cfg.timeout_s)


def generate_image(prompt: str, ref_path: Path, cfg: OpenAiImageConfig) -> bytes:
    provider = cfg.provider.lower()
    providers = ["responses", "images"] if provider == "auto" else [provider]
    last_err: Exception | None = None
    for current in providers:
        try:
            if current == "responses":
                return generate_via_responses(prompt, ref_path, cfg)
            return generate_via_images(prompt, ref_path, cfg)
        except Exception as exc:
            last_err = exc
            if len(providers) > 1:
                print(f"  provider {current} failed: {exc}; trying next")
    if last_err:
        raise last_err
    raise RuntimeError("Generation failed with no provider error")


# =============================================================================
# Local fallback (deterministic; for offline testing)
# =============================================================================

def make_local_fallback_art(card_name: str, archetype: str) -> Image.Image:
    width, height = 1024, 1024
    seed = int(hashlib.sha256(card_name.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    palette = {
        "Samurai":  ((96, 24, 24), (220, 180, 80), (255, 240, 200)),
        "Ninja":    ((10, 12, 40), (60, 80, 140), (200, 220, 255)),
        "Spirit":   ((180, 200, 240), (240, 230, 255), (140, 220, 255)),
        "Moonfolk": ((30, 40, 80), (150, 170, 220), (220, 230, 255)),
        "Modified": ((30, 10, 50), (180, 30, 200), (60, 240, 240)),
    }.get(archetype, ((40, 40, 60), (110, 90, 180), (220, 200, 255)))
    c1, c2, accent = palette
    img = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(height):
        t = y / max(1, height - 1)
        color = (int(c1[0] * (1 - t) + c2[0] * t),
                 int(c1[1] * (1 - t) + c2[1] * t),
                 int(c1[2] * (1 - t) + c2[2] * t))
        draw.line([(0, y), (width, y)], fill=color)
    for _ in range(36):
        x1 = rng.randint(-160, width - 60)
        y1 = rng.randint(-160, height - 60)
        x2 = x1 + rng.randint(120, 380)
        y2 = y1 + rng.randint(80, 320)
        alpha = rng.randint(20, 90)
        tint = (min(255, accent[0] + rng.randint(-24, 24)),
                min(255, accent[1] + rng.randint(-24, 24)),
                min(255, accent[2] + rng.randint(-24, 24)),
                alpha)
        draw.ellipse((x1, y1, x2, y2), fill=tint)
    img = img.filter(ImageFilter.GaussianBlur(radius=2.0))
    return img


# =============================================================================
# Output
# =============================================================================

def to_filename(name: str) -> str:
    return (
        name.lower()
        .replace("'", "")
        .replace(",", "")
        .replace(":", "")
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
        .strip("_")
    )


def render_square(image_bytes: bytes, side: int = 1024) -> Image.Image:
    with Image.open(io.BytesIO(image_bytes)) as src:
        src = src.convert("RGB")
        return ImageOps.fit(src, (side, side), method=Image.Resampling.LANCZOS)


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True, compress_level=3)


# =============================================================================
# Driver
# =============================================================================

def collect_cards():
    """Sorted list of (name, card_def) — every BK card."""
    return sorted(BEYOND_KAMIGAWA_CARDS.items(), key=lambda kv: kv[0])


def run_api_mode(specs, by_key, force, cfg, retries, sleep_s, limit):
    generated, skipped, failed = 0, 0, 0
    log: list[dict] = []
    for i, (name, card) in enumerate(specs, 1):
        if 0 < limit < i:
            break
        out_path = OUT_DIR / f"{to_filename(name)}.png"
        if out_path.exists() and not force:
            skipped += 1
            print(f"[{i:03d}/{len(specs)}] SKIP (cached) {out_path.name}")
            continue
        try:
            ref = pick_reference(card, by_key)
        except Exception as exc:
            failed += 1
            print(f"[{i:03d}/{len(specs)}] FAIL ref-pick {name}: {exc}")
            continue
        prompt = build_prompt(card)
        attempt_results = []
        success = False
        for attempt in range(1, retries + 1):
            try:
                print(f"[{i:03d}/{len(specs)}] GEN  {out_path.name}  ref={ref.key}  (attempt {attempt}/{retries})")
                raw = generate_image(prompt, ref.local_path, cfg)
                rendered = render_square(raw, side=1024)
                save_png(rendered, out_path)
                generated += 1
                success = True
                attempt_results.append("ok")
                break
            except Exception as exc:
                wait = min(20.0, 1.8 * attempt)
                print(f"        FAIL: {exc}")
                attempt_results.append(str(exc)[:120])
                if attempt < retries:
                    print(f"        retry in {wait:.1f}s")
                    time.sleep(wait)
        log.append({
            "card": name,
            "ref": ref.key,
            "out": str(out_path.relative_to(PROJECT_ROOT)),
            "attempts": attempt_results,
            "success": success,
        })
        if not success:
            failed += 1
        if sleep_s > 0:
            time.sleep(sleep_s)
    # Append-style log
    log_path = OUT_DIR / "_gen_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.extend(log)
    log_path.write_text(json.dumps(existing, indent=2) + "\n")
    return generated, skipped, failed


def run_local_mode(specs, force, limit):
    generated, skipped, failed = 0, 0, 0
    for i, (name, card) in enumerate(specs, 1):
        if 0 < limit < i:
            break
        out_path = OUT_DIR / f"{to_filename(name)}.png"
        if out_path.exists() and not force:
            skipped += 1
            continue
        try:
            archetype = _archetype_of(card)
            art = make_local_fallback_art(name, archetype)
            save_png(art, out_path)
            generated += 1
            print(f"[{i:03d}] LOCAL {out_path.name}")
        except Exception as exc:
            failed += 1
            print(f"[{i:03d}] FAIL  {name}: {exc}")
    return generated, skipped, failed


def run_manual_mode(specs, by_key, force, limit, image_size, quality):
    entries = []
    for i, (name, card) in enumerate(specs, 1):
        if 0 < limit < i:
            break
        out_path = OUT_DIR / f"{to_filename(name)}.png"
        if out_path.exists() and not force:
            continue
        try:
            ref = pick_reference(card, by_key)
        except Exception:
            continue
        prompt = build_prompt(card)
        entries.append({
            "card_name": name,
            "ref_key": ref.key,
            "ref_local_path": str(ref.local_path.relative_to(PROJECT_ROOT)),
            "prompt": prompt,
            "output_file": out_path.name,
            "image_options": {
                "size": image_size,
                "quality": quality,
                "output_format": "png",
                "background": "opaque",
            },
        })
    pack = {
        "version": 1,
        "variant": "beyond_kamigawa",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entry_count": len(entries),
        "entries": entries,
    }
    PROMPT_PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_PACK_PATH.write_text(json.dumps(pack, indent=2) + "\n")
    print(f"Wrote {len(entries)} prompt entries to {PROMPT_PACK_PATH}")


def parse_args():
    parser = argparse.ArgumentParser(description="Beyond Kamigawa card-art generator.")
    parser.add_argument("--mode", choices=("api", "manual", "local"), default="api")
    parser.add_argument("--provider", choices=("auto", "responses", "images"),
                        default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--draw-model", default=DEFAULT_DRAW_MODEL)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", default=DEFAULT_QUALITY)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--archetype", default="",
                        help="Only generate cards belonging to this archetype "
                             "(samurai, ninja, spirit_dragons, moonfolk, modified)")
    return parser.parse_args()


def filter_by_archetype(specs, archetype: str):
    if not archetype:
        return specs
    archetype_tag = {
        "samurai": "Samurai",
        "ninja": "Ninja",
        "spirit_dragons": "Spirit",
        "spirit": "Spirit",
        "moonfolk": "Moonfolk",
        "modified": "Modified",
    }.get(archetype.lower())
    if not archetype_tag:
        return specs
    out = []
    for name, card in specs:
        subs = card.characteristics.subtypes if card.characteristics else set()
        if archetype_tag in (subs or set()):
            out.append((name, card))
    return out


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Beyond Kamigawa card-art generator")
    print(f"  Mode    : {args.mode}")
    print(f"  Output  : {OUT_DIR.relative_to(PROJECT_ROOT)}")

    _entries, by_key = _load_refs_index()
    print(f"  Refs    : {len(by_key)} library keys")

    specs = collect_cards()
    if args.archetype:
        specs = filter_by_archetype(specs, args.archetype)
        print(f"  Archetype filter: {args.archetype} -> {len(specs)} cards")
    print(f"  Cards   : {len(specs)} (limit={args.limit or 'none'})")
    print()

    if args.mode == "manual":
        run_manual_mode(specs, by_key, args.force, args.limit, args.size, args.quality)
        return 0

    if args.mode == "local":
        g, s, f = run_local_mode(specs, args.force, args.limit)
        print(f"local: generated={g} skipped={s} failed={f}")
        return 0

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for --mode api (set in .env)")
    cfg = OpenAiImageConfig(
        api_key=api_key,
        model=args.model,
        draw_model=args.draw_model,
        provider=args.provider,
        size=args.size,
        quality=args.quality,
        timeout_s=max(10.0, args.timeout),
    )
    g, s, f = run_api_mode(specs, by_key, args.force, cfg,
                           retries=max(1, args.retries),
                           sleep_s=max(0.0, args.sleep),
                           limit=args.limit)
    print(f"api: generated={g} skipped={s} failed={f}")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
