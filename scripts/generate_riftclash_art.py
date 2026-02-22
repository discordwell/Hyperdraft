#!/usr/bin/env python3
"""
Riftclash card-art pipeline (ported from the Dwellhome mall image flow).

Modes:
  - api: generate PNG art with OpenAI (`responses` provider first, then `images`)
  - manual: emit a prompt queue JSON for manual ChatGPT draw/import workflows
  - local: deterministic local fallback art (offline)

Outputs:
  assets/card_art/custom/riftclash/<card_name_snake_case>.png
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from src.cards.hearthstone.riftclash import RIFTCLASH_DECKS
from src.engine.types import CardDefinition, CardType


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "assets" / "card_art" / "custom" / "riftclash"
PROMPT_PACK_PATH = OUT_DIR / "draw_prompts.json"

DEFAULT_MODEL = "chatgpt-image-latest"
DEFAULT_DRAW_MODEL = "gpt-5"
DEFAULT_SIZE = "1536x1024"
DEFAULT_QUALITY = "high"
DEFAULT_PROVIDER = "auto"


@dataclass
class CardArtSpec:
    card: CardDefinition
    factions: set[str]


@dataclass
class OpenAiImageConfig:
    api_key: str
    model: str
    draw_model: str
    provider: str
    size: str
    quality: str
    style: str
    timeout_s: float


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
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def to_filename(name: str) -> str:
    return (
        name.lower()
        .replace("'", "")
        .replace(",", "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
        .strip("_")
    )


def slugify(name: str) -> str:
    out = []
    last_dash = False
    for ch in name.lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    slug = "".join(out).strip("-")
    return slug or "card"


def prompt_hash(prompt: str) -> str:
    normalized = " ".join(prompt.split()).strip().lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def classify_theme(name: str) -> str:
    lower = name.lower()
    cold_tokens = (
        "frost",
        "ice",
        "cryo",
        "void",
        "glacial",
        "whiteout",
        "blizzard",
        "absolute",
        "frozen",
    )
    return "cold" if any(token in lower for token in cold_tokens) else "warm"


def palette(theme: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    if theme == "cold":
        return (34, 55, 102), (72, 189, 224), (191, 240, 255)
    return (89, 29, 22), (224, 104, 43), (255, 198, 126)


def draw_gradient(draw: ImageDraw.ImageDraw, size: tuple[int, int], c1: tuple[int, int, int], c2: tuple[int, int, int]) -> None:
    width, height = size
    for y in range(height):
        t = y / max(1, height - 1)
        color = (
            int(c1[0] * (1 - t) + c2[0] * t),
            int(c1[1] * (1 - t) + c2[1] * t),
            int(c1[2] * (1 - t) + c2[2] * t),
        )
        draw.line([(0, y), (width, y)], fill=color, width=1)


def make_local_fallback_art(card_name: str) -> Image.Image:
    width, height = 1024, 640
    seed = int(hashlib.sha256(card_name.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    theme = classify_theme(card_name)
    c1, c2, accent = palette(theme)

    img = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(img, "RGBA")
    draw_gradient(draw, (width, height), c1, c2)

    for _ in range(30):
        x1 = rng.randint(-140, width - 60)
        y1 = rng.randint(-120, height - 50)
        x2 = x1 + rng.randint(120, 380)
        y2 = y1 + rng.randint(70, 280)
        alpha = rng.randint(20, 80)
        tint = (
            min(255, accent[0] + rng.randint(-24, 24)),
            min(255, accent[1] + rng.randint(-24, 24)),
            min(255, accent[2] + rng.randint(-24, 24)),
            alpha,
        )
        draw.ellipse((x1, y1, x2, y2), fill=tint)

    for _ in range(20):
        x = rng.randint(20, width - 20)
        y = rng.randint(10, height - 10)
        dx = rng.randint(-260, 260)
        dy = rng.randint(-170, 170)
        line_alpha = rng.randint(70, 150)
        draw.line(
            [(x, y), (x + dx, y + dy)],
            fill=(accent[0], accent[1], accent[2], line_alpha),
            width=rng.randint(2, 7),
        )

    img = img.filter(ImageFilter.GaussianBlur(radius=2.0))
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vg_draw = ImageDraw.Draw(vignette, "RGBA")
    for i in range(50):
        alpha = int((i / 50) * 7)
        vg_draw.rectangle((i, i, width - i, height - i), outline=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), vignette).convert("RGB")


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
        data = base64.b64decode(stripped, validate=False)
    except Exception:
        return None
    return data if data else None


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


def generate_openai_image_via_images(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    payload: dict[str, Any] = {
        "model": cfg.model,
        "prompt": prompt,
        "size": cfg.size,
        "quality": cfg.quality,
        "output_format": "png",
        "background": "opaque",
    }
    if cfg.style:
        payload["style"] = cfg.style

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
        raise RuntimeError(f"OpenAI images generation failed ({response.status_code}): {response.text[:180]}")
    return extract_image_bytes_from_payload(response.json(), timeout_s=cfg.timeout_s)


def generate_openai_image_via_responses(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    tool: dict[str, Any] = {
        "type": "image_generation",
        "size": cfg.size,
        "quality": cfg.quality,
        "background": "opaque",
        "output_format": "png",
    }
    if cfg.style:
        tool["style"] = cfg.style

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg.draw_model,
            "input": prompt,
            "tools": [tool],
        },
        timeout=cfg.timeout_s,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI responses image generation failed ({response.status_code}): {response.text[:180]}")
    return extract_image_bytes_from_payload(response.json(), timeout_s=cfg.timeout_s)


def generate_openai_image(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    provider = cfg.provider.lower()
    if provider not in {"auto", "responses", "images"}:
        provider = "auto"

    providers = ["responses", "images"] if provider == "auto" else [provider]
    last_error: Exception | None = None
    for current in providers:
        try:
            if current == "responses":
                return generate_openai_image_via_responses(prompt, cfg)
            return generate_openai_image_via_images(prompt, cfg)
        except Exception as exc:
            last_error = exc
            if len(providers) > 1:
                print(f"[riftclash-art] provider {current} failed; trying next: {exc}")
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI image generation failed with no provider error")


def card_type_string(card: CardDefinition) -> str:
    types = card.characteristics.types
    if CardType.MINION in types:
        return "minion"
    if CardType.SPELL in types:
        return "spell"
    if CardType.HERO in types:
        return "hero"
    if CardType.HERO_POWER in types:
        return "hero power"
    return "card"


def joined(values: set[str]) -> str:
    if not values:
        return ""
    return ", ".join(sorted(values))


def card_faction_style(factions: set[str]) -> str:
    if factions == {"Pyromancer"}:
        return (
            "Focus on aggressive fire magic, volcanic shards, embers, molten fractures, "
            "and a warm red-orange-gold palette."
        )
    if factions == {"Cryomancer"}:
        return (
            "Focus on precise ice and void-frost magic, frozen shards, glacial haze, "
            "and a cold cyan-blue-silver palette."
        )
    return (
        "Show the elemental rift tension between fire and ice, with colliding warm and cold magic motifs."
    )


def build_card_prompt(spec: CardArtSpec) -> str:
    card = spec.card
    ctype = card_type_string(card)
    subtypes = joined(card.characteristics.subtypes)
    text = " ".join((card.text or "").split()).strip()
    mana_cost = (card.mana_cost or "").strip()
    power = card.characteristics.power
    toughness = card.characteristics.toughness

    details = [
        "High-end fantasy card illustration for the game Riftclash.",
        f"Card name: {card.name}.",
        f"Card role: {ctype}.",
        f"Faction: {joined(spec.factions)}.",
    ]

    if mana_cost:
        details.append(f"Mana cost impression: {mana_cost}.")
    if subtypes:
        details.append(f"Subtype cues: {subtypes}.")
    if power is not None and toughness is not None:
        details.append(f"Power and vitality cues: {power}/{toughness}.")
    if text:
        details.append(f"Ability inspiration: {text}.")

    details.extend(
        [
            card_faction_style(spec.factions),
            "One clear focal subject, cinematic composition, dramatic spell effects, dynamic motion.",
            "Painterly concept-art finish, rich texture, strong silhouette, high detail.",
            "Landscape composition suitable for a wide card-art crop.",
            "No text, no letters, no symbols, no logos, no card frame, no watermark.",
        ]
    )
    return " ".join(details)


def render_for_card_aspect(image_bytes: bytes, width: int = 1024, height: int = 640) -> Image.Image:
    with Image.open(io.BytesIO(image_bytes)) as source:
        source = source.convert("RGB")
        target_ratio = width / height
        src_ratio = source.width / source.height

        if abs(src_ratio - target_ratio) > 1e-3:
            if src_ratio > target_ratio:
                new_width = int(source.height * target_ratio)
                left = max(0, (source.width - new_width) // 2)
                source = source.crop((left, 0, left + new_width, source.height))
            else:
                new_height = int(source.width / target_ratio)
                top = max(0, (source.height - new_height) // 2)
                source = source.crop((0, top, source.width, top + new_height))

        fitted = ImageOps.fit(source, (width, height), method=Image.Resampling.LANCZOS)
        return fitted


def collect_card_specs() -> list[CardArtSpec]:
    by_name: dict[str, CardArtSpec] = {}
    for faction, deck in RIFTCLASH_DECKS.items():
        for card in deck:
            existing = by_name.get(card.name)
            if existing is None:
                by_name[card.name] = CardArtSpec(card=card, factions={faction})
            else:
                existing.factions.add(faction)
    return [by_name[name] for name in sorted(by_name.keys())]


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True, compress_level=3)


def build_prompt_pack(specs: list[CardArtSpec], image_size: str, quality: str, force: bool) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for spec in specs:
        filename = f"{to_filename(spec.card.name)}.png"
        output_path = OUT_DIR / filename
        if output_path.exists() and not force:
            continue

        prompt = build_card_prompt(spec)
        entries.append(
            {
                "id": f"riftclash-{slugify(spec.card.name)}",
                "kind": "card-art",
                "card_name": spec.card.name,
                "faction": joined(spec.factions),
                "prompt": prompt,
                "prompt_hash": prompt_hash(prompt),
                "output_file": filename,
                "target_public_path": f"/api/card-art/custom/riftclash/{filename}",
                "image_options": {
                    "size": image_size,
                    "quality": quality,
                    "output_format": "png",
                    "background": "opaque",
                },
            }
        )

    return {
        "version": 1,
        "variant": "riftclash",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entry_count": len(entries),
        "entries": entries,
    }


def run_local_mode(specs: list[CardArtSpec], force: bool) -> tuple[int, int, int]:
    generated = 0
    skipped = 0
    failed = 0
    for spec in specs:
        output_path = OUT_DIR / f"{to_filename(spec.card.name)}.png"
        if output_path.exists() and not force:
            skipped += 1
            continue
        try:
            art = make_local_fallback_art(spec.card.name)
            save_png(art, output_path)
            generated += 1
            print(f"[local] generated {output_path.name}")
        except Exception as exc:
            failed += 1
            print(f"[local] failed {spec.card.name}: {exc}")
    return generated, skipped, failed


def run_api_mode(specs: list[CardArtSpec], force: bool, cfg: OpenAiImageConfig, retries: int, sleep_s: float) -> tuple[int, int, int]:
    generated = 0
    skipped = 0
    failed = 0

    for spec in specs:
        output_path = OUT_DIR / f"{to_filename(spec.card.name)}.png"
        if output_path.exists() and not force:
            skipped += 1
            continue

        prompt = build_card_prompt(spec)
        success = False

        for attempt in range(1, retries + 1):
            try:
                print(f"[api] generating {output_path.name} (attempt {attempt}/{retries})")
                raw = generate_openai_image(prompt, cfg)
                rendered = render_for_card_aspect(raw, width=1024, height=640)
                save_png(rendered, output_path)
                generated += 1
                success = True
                break
            except Exception as exc:
                wait_s = min(20.0, 1.8 * attempt)
                print(f"[api] failed {spec.card.name}: {exc}")
                if attempt < retries:
                    print(f"[api] retrying in {wait_s:.1f}s")
                    time.sleep(wait_s)

        if not success:
            failed += 1
        if sleep_s > 0:
            time.sleep(sleep_s)

    return generated, skipped, failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate high-quality Riftclash card art.")
    parser.add_argument(
        "--mode",
        choices=("api", "manual", "local"),
        default=(os.getenv("MALL_IMAGE_MODE") or "manual").lower(),
        help="Generation mode. Defaults to MALL_IMAGE_MODE or manual.",
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "responses", "images"),
        default=(os.getenv("MALL_IMAGE_PROVIDER") or DEFAULT_PROVIDER).lower(),
        help="OpenAI provider mode for API generation.",
    )
    parser.add_argument("--model", default=os.getenv("MALL_IMAGE_MODEL") or DEFAULT_MODEL, help="OpenAI images model.")
    parser.add_argument(
        "--draw-model",
        default=os.getenv("MALL_DRAW_MODEL") or DEFAULT_DRAW_MODEL,
        help="OpenAI responses model used with image_generation tool.",
    )
    parser.add_argument("--size", default=os.getenv("MALL_IMAGE_SIZE") or DEFAULT_SIZE, help="Requested image size.")
    parser.add_argument("--quality", default=os.getenv("MALL_IMAGE_QUALITY") or DEFAULT_QUALITY, help="Image quality.")
    parser.add_argument("--style", default=os.getenv("MALL_IMAGE_STYLE") or "", help="Optional style hint.")
    parser.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout seconds per generation call.")
    parser.add_argument("--retries", type=int, default=3, help="Retry count per card in API mode.")
    parser.add_argument("--sleep", type=float, default=0.4, help="Delay between cards in API mode.")
    parser.add_argument("--force", action="store_true", help="Regenerate images even if files already exist.")
    parser.add_argument("--limit", type=int, default=0, help="Generate only first N unique cards.")
    parser.add_argument(
        "--prompt-pack",
        default=str(PROMPT_PACK_PATH),
        help="Output path for manual prompt queue JSON.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    specs = collect_card_specs()
    if args.limit > 0:
        specs = specs[: args.limit]

    if args.mode == "manual":
        payload = build_prompt_pack(specs, image_size=args.size, quality=args.quality, force=args.force)
        pack_path = Path(args.prompt_pack)
        pack_path.parent.mkdir(parents=True, exist_ok=True)
        pack_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
        print(f"[manual] wrote {payload['entry_count']} prompt entries to {pack_path}")
        return

    if args.mode == "local":
        generated, skipped, failed = run_local_mode(specs, force=args.force)
        print(f"[local] complete: generated={generated}, skipped={skipped}, failed={failed}, dir={OUT_DIR}")
        return

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --mode api (set env or .env).")

    cfg = OpenAiImageConfig(
        api_key=api_key,
        model=args.model,
        draw_model=args.draw_model,
        provider=args.provider,
        size=args.size,
        quality=args.quality,
        style=args.style,
        timeout_s=max(10.0, args.timeout),
    )
    generated, skipped, failed = run_api_mode(
        specs,
        force=args.force,
        cfg=cfg,
        retries=max(1, args.retries),
        sleep_s=max(0.0, args.sleep),
    )
    print(f"[api] complete: generated={generated}, skipped={skipped}, failed={failed}, dir={OUT_DIR}")


if __name__ == "__main__":
    main()
