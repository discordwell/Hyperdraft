#!/usr/bin/env python3
"""
Phyrexian Overworld — Minecraft TCG card-art generator.

Generates blocky voxel + Phyrexian dark-fantasy illustrations for every card
in src.cards.minecraft (alpha + Phyrexia Bedrock Edition + Box of Horrors). Skips the
reference-image pipeline used by the kamigawa generator — Minecraft's
aesthetic is the *style anchor*, not a reference frame.

Modes:
  - api     — generate via OpenAI (default)
  - manual  — write prompt-pack JSON for paste-into-ChatGPT use
  - local   — deterministic procedural placeholders (offline)

Usage::

    python scripts/phyrexian_overworld/generate_card_art.py --limit 5
    python scripts/phyrexian_overworld/generate_card_art.py --force --only "Herobrine"
    python scripts/phyrexian_overworld/generate_card_art.py --mode manual
    python scripts/phyrexian_overworld/generate_card_art.py --set phyrexia        # only Phyrexia Bedrock Edition
    python scripts/phyrexian_overworld/generate_card_art.py --set all             # alpha + phyrexia
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

from src.cards.minecraft import MINECRAFT_CARDS, PHYREXIA_CARDS, ALPHA_CARDS, HORROR_CARDS
from src.engine.types import CardType


OUT_DIR = PROJECT_ROOT / "assets" / "card_art" / "minecraft"
PROMPT_PACK_PATH = OUT_DIR / "draw_prompts.json"
GEN_LOG_PATH = OUT_DIR / "_gen_log.json"

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
# Prompt building — Minecraft voxel + Phyrexian dark fantasy
# =============================================================================

STYLE_HEADLINE = (
    "Minecraft voxel art crashed into Phyrexian dark fantasy: blocky 1m³ "
    "cube geometry, low-poly cubist subject framed by a single gnarled "
    "cobblestone vignette. Soft ambient occlusion. Color palette: "
    "obsidian black, oil-slick iridescence, oxidized copper, sickly "
    "green ichor, Phyrexian crimson, polished steel highlights. Dim "
    "torchlit village ruin in the background, bedrock ground tiles, "
    "drips of glistening oil pooling. Single subject dominates a 1:1 "
    "square frame, cinematic 3/4 angle. Heavy chiaroscuro, rim-light "
    "in crimson. Matte finish, NOT photoreal. "
    "NO text, NO logos, NO card frame, NO borders, NO HP/ATK numbers — "
    "illustration only."
)


def _category(card) -> str:
    """Top-level visual category for prompt scaffolding."""
    if not card.characteristics:
        return "object"
    types = card.characteristics.types
    subs = card.characteristics.subtypes or set()
    if "Boss" in subs and "Praetor" in subs:
        return "praetor"
    if "Boss" in subs:
        return "boss"
    if CardType.MC_MOB in types:
        if "Compleated" in subs:
            return "compleated_mob"
        if "Hostile" in subs:
            return "hostile"
        if "Worker" in subs:
            return "worker"
        return "mob"
    if CardType.MC_STRUCTURE in types:
        return "structure"
    if CardType.MC_BLOCK in types:
        return "block"
    if CardType.MC_TOOL in types:
        slot = getattr(card, "mc_tool_slot", "") or ""
        if slot == "weapon":
            return "weapon"
        if slot == "armor":
            return "armor"
        return "tool"
    if CardType.MC_ACTION in types:
        return "action"
    return "object"


def _category_flavor(category: str) -> str:
    return {
        "praetor": (
            "PRAETOR — towering legendary Phyrexian overlord, ornate metal "
            "regalia, obsidian throne backdrop, distorted halo of oil-smoke. "
            "Imposing centered composition; the figure looms over a dim "
            "voxel village skyline."
        ),
        "boss": (
            "BOSS-tier legendary entity — massive scale relative to the "
            "blocky world, wreathed in shadow and crimson light, bedrock "
            "and obsidian rubble at its feet."
        ),
        "compleated_mob": (
            "COMPLEATED MOB — flesh-machine fusion. The familiar Minecraft "
            "creature has been corrupted: organic surfaces replaced with "
            "polished steel plating, exposed black-oil tendons, glowing "
            "crimson eye-pixels, blocky Phyrexian augments grafted on."
        ),
        "hostile": (
            "Hostile mob — aggressive blocky creature, glowing red eye "
            "pixels, dark smoky aura, in a torchlit voxel village ruin."
        ),
        "worker": (
            "Worker villager — humble blocky figure with mining tools and "
            "hauling pack, but cast in dark Phyrexian shadow, oil-stained "
            "robes, suggesting fragile humanity besieged."
        ),
        "mob": (
            "Stylized blocky creature in a Phyrexian-corrupted Minecraft "
            "village, voxel anatomy."
        ),
        "structure": (
            "Voxel structure built from blocky cubes — Phyrexian-corrupted "
            "Minecraft architecture: oil-slicked stone, copper-etched runes, "
            "dim torchlight from sickly green torches."
        ),
        "block": (
            "Single defensive block — chunky cube wall or trap, weathered "
            "and oil-stained, decorative voxel detailing."
        ),
        "weapon": (
            "Phyrexian weapon — voxel sword/bow with jagged metal segments, "
            "oil dripping from edges, crimson glow along blade runes. "
            "Floating against a dark background, hero pose."
        ),
        "armor": (
            "Phyrexian armor piece — chunky voxel plate with bone-and-metal "
            "fusion, glowing seams of oil-light, displayed on a stand "
            "before a dim village forge."
        ),
        "tool": (
            "Phyrexian tool — pickaxe / utility item, voxel construction, "
            "oil-darkened metal, faint glowing inscriptions."
        ),
        "action": (
            "Action card scene — a moment of dark Phyrexian magic in a "
            "blocky Minecraft village: a glistening-oil ritual circle, "
            "crimson lightning, voxel debris hurled into the air."
        ),
    }.get(category, "Voxel artifact in a Phyrexian-corrupted Minecraft setting.")


def build_prompt(card) -> str:
    category = _category(card)
    cat_line = _category_flavor(category)
    flavor_text = " ".join((card.text or "").split()).strip()
    parts = [STYLE_HEADLINE, f"Card name: {card.name}.", cat_line]
    if flavor_text:
        if len(flavor_text) > 240:
            flavor_text = flavor_text[:237] + "..."
        parts.append(f"Card flavor / behavior cue: {flavor_text}")
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


def generate_via_responses(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    payload = {
        "model": cfg.draw_model,
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]}
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
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=cfg.timeout_s,
    )
    if not response.ok:
        raise RuntimeError(f"Responses API failed ({response.status_code}): {response.text[:240]}")
    return extract_image_bytes_from_payload(response.json(), timeout_s=cfg.timeout_s)


def generate_via_images(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    payload = {
        "model": cfg.model,
        "prompt": prompt,
        "size": cfg.size,
        "quality": cfg.quality,
        "output_format": "png",
        "background": "opaque",
    }
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=cfg.timeout_s,
    )
    if not response.ok:
        raise RuntimeError(f"Images API failed ({response.status_code}): {response.text[:240]}")
    return extract_image_bytes_from_payload(response.json(), timeout_s=cfg.timeout_s)


def generate_image(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    provider = cfg.provider.lower()
    providers = ["responses", "images"] if provider == "auto" else [provider]
    last_err: Exception | None = None
    for current in providers:
        try:
            if current == "responses":
                return generate_via_responses(prompt, cfg)
            return generate_via_images(prompt, cfg)
        except Exception as exc:
            last_err = exc
            if len(providers) > 1:
                print(f"  provider {current} failed: {exc}; trying next")
    if last_err:
        raise last_err
    raise RuntimeError("Generation failed with no provider error")


# =============================================================================
# Local fallback
# =============================================================================

def make_local_fallback_art(card_name: str, category: str) -> Image.Image:
    width, height = 1024, 1024
    seed = int(hashlib.sha256(card_name.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    palette = {
        "praetor":           ((20, 8, 14), (96, 16, 32),  (240, 200, 90)),
        "boss":              ((10, 10, 14), (80, 14, 30),  (220, 80, 60)),
        "compleated_mob":    ((14, 12, 16), (60, 30, 70),  (220, 40, 80)),
        "hostile":           ((18, 14, 18), (60, 60, 30),  (220, 200, 60)),
        "worker":            ((30, 28, 24), (90, 80, 60),  (200, 180, 140)),
        "mob":               ((22, 20, 26), (80, 60, 110), (200, 200, 220)),
        "structure":         ((26, 24, 22), (90, 80, 60),  (180, 160, 100)),
        "block":             ((30, 30, 32), (60, 60, 64),  (160, 160, 168)),
        "weapon":            ((20, 16, 20), (90, 30, 30),  (240, 220, 200)),
        "armor":             ((24, 22, 24), (70, 60, 80),  (200, 200, 220)),
        "tool":              ((28, 26, 24), (90, 70, 50),  (220, 200, 160)),
        "action":            ((10, 6, 14),  (80, 14, 60),  (240, 60, 90)),
    }.get(category, ((30, 30, 30), (90, 90, 90), (200, 200, 200)))
    c1, c2, accent = palette
    img = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(height):
        t = y / max(1, height - 1)
        color = (int(c1[0] * (1 - t) + c2[0] * t),
                 int(c1[1] * (1 - t) + c2[1] * t),
                 int(c1[2] * (1 - t) + c2[2] * t))
        draw.line([(0, y), (width, y)], fill=color)
    # Voxel-ish chunky blocks scattered.
    for _ in range(60):
        size = rng.choice([64, 96, 128, 192])
        x1 = rng.randint(-32, width - size + 32)
        y1 = rng.randint(-32, height - size + 32)
        alpha = rng.randint(60, 160)
        tint = (
            min(255, max(0, accent[0] + rng.randint(-30, 30))),
            min(255, max(0, accent[1] + rng.randint(-30, 30))),
            min(255, max(0, accent[2] + rng.randint(-30, 30))),
            alpha,
        )
        draw.rectangle((x1, y1, x1 + size, y1 + size), fill=tint, outline=(0, 0, 0, 200), width=2)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.0))
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
        .replace(".", "")
        .replace("!", "")
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

def collect_cards(set_filter: str):
    if set_filter == "alpha":
        source = ALPHA_CARDS
    elif set_filter == "phyrexia":
        source = PHYREXIA_CARDS
    elif set_filter == "horror":
        source = HORROR_CARDS
    else:
        source = MINECRAFT_CARDS
    return sorted(source.items(), key=lambda kv: kv[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Minecraft TCG card art")
    parser.add_argument("--mode", choices=["api", "manual", "local"], default="api")
    parser.add_argument("--set", dest="set_filter", choices=["alpha", "phyrexia", "horror", "all"], default="all")
    parser.add_argument("--force", action="store_true", help="Regenerate existing files")
    parser.add_argument("--limit", type=int, default=0, help="Generate at most N cards")
    parser.add_argument("--only", default="", help="Substring match on card name")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", default=DEFAULT_QUALITY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--draw-model", default=DEFAULT_DRAW_MODEL)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["auto", "responses", "images"])
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def filter_specs(specs, only: str, limit: int):
    if only:
        needle = only.lower()
        specs = [s for s in specs if needle in s[0].lower()]
    if limit > 0:
        specs = specs[:limit]
    return specs


def run_api_mode(specs, force, cfg, retries, sleep_s):
    generated, skipped, failed = 0, 0, 0
    log: list[dict] = []
    total = len(specs)
    for i, (name, card) in enumerate(specs, 1):
        out_path = OUT_DIR / f"{to_filename(name)}.png"
        if out_path.exists() and not force:
            skipped += 1
            print(f"[{i:03d}/{total}] SKIP (cached) {out_path.name}")
            continue
        prompt = build_prompt(card)
        success = False
        attempt_results: list[str] = []
        for attempt in range(1, retries + 1):
            try:
                print(f"[{i:03d}/{total}] GEN  {out_path.name}  (attempt {attempt}/{retries})")
                raw = generate_image(prompt, cfg)
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
            "out": str(out_path.relative_to(PROJECT_ROOT)),
            "attempts": attempt_results,
            "success": success,
        })
        if not success:
            failed += 1
        if sleep_s > 0:
            time.sleep(sleep_s)
    GEN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEN_LOG_PATH.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return generated, skipped, failed


def run_manual_mode(specs, force: bool = False):
    """Dump a paste-into-ChatGPT prompt pack JSON. Skips cards that already
    have a PNG on disk so the output only lists what's still missing."""
    pack = []
    skipped = 0
    for name, card in specs:
        filename = f"{to_filename(name)}.png"
        if (OUT_DIR / filename).exists() and not force:
            skipped += 1
            continue
        pack.append({
            "card": name,
            "filename": filename,
            "prompt": build_prompt(card),
        })
    PROMPT_PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_PACK_PATH.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    print(f"Wrote prompt pack with {len(pack)} entries to {PROMPT_PACK_PATH.relative_to(PROJECT_ROOT)}")
    if skipped:
        print(f"Skipped {skipped} cards already cached on disk (pass --force to include them).")


def run_local_mode(specs, force):
    generated = 0
    for name, card in specs:
        out_path = OUT_DIR / f"{to_filename(name)}.png"
        if out_path.exists() and not force:
            continue
        category = _category(card)
        img = make_local_fallback_art(name, category)
        save_png(img, out_path)
        generated += 1
        print(f"WROTE {out_path.name}")
    print(f"Local fallback: generated {generated} placeholders.")


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    specs = collect_cards(args.set_filter)
    specs = filter_specs(specs, args.only, args.limit)
    print(f"Targeting {len(specs)} cards (set={args.set_filter})")

    if args.mode == "manual":
        run_manual_mode(specs, force=args.force)
        return

    if args.mode == "local":
        run_local_mode(specs, args.force)
        return

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY not set — falling back to local placeholders")
        run_local_mode(specs, args.force)
        return

    cfg = OpenAiImageConfig(
        api_key=api_key,
        model=args.model,
        draw_model=args.draw_model,
        provider=args.provider,
        size=args.size,
        quality=args.quality,
        timeout_s=args.timeout,
    )
    generated, skipped, failed = run_api_mode(specs, args.force, cfg, args.retries, args.sleep)
    print(f"Done. generated={generated} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
