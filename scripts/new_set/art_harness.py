"""
art_harness — generalized prompt-pack writer for the /new-set pipeline.

Generalization of `scripts/phyrexian_overworld/generate_card_art.py`.
Same three modes (manual / api / local), same output shape (PNGs +
draw_prompts.json + _gen_log.json), but parameterized over a per-set
*style config* so the pipeline can drive it for any engine + any
aesthetic.

Default mode is `manual`, which writes a `draw_prompts.json` for the
claude-in-chrome browser-automation agent in stage 5 to consume —
matching the user's stated workflow ("the part going to the ChatGPT
web interface").

Per-set style config
--------------------
A Python module whose top-level defines:

    STYLE_HEADLINE: str
        Lead paragraph describing visual style. Concatenated as the first
        portion of every prompt.

    CATEGORY_FLAVORS: dict[str, str]
        Map from category key → second-paragraph flavor describing how
        cards in that category should look.

    categorize(card) -> str   (optional)
        Returns one of the keys in CATEGORY_FLAVORS. If absent, a default
        categorizer is used that maps CardType.CREATURE → "creature",
        CardType.INSTANT/SORCERY → "spell", etc.

Cards source
------------
Either a Python module dict via ``--cards <module>:<var>``, or one or more
JSON files via ``--cards-json <path>`` (repeatable). The JSON path is the
escape hatch for engines whose card data isn't in the hyperdraft Python
tree — PIP30, for example, holds its cards in Unity StreamingAssets/*.json.

CLI:
    python -m scripts.new_set.art_harness \\
        --style src.cards.minecraft.style \\
        --cards src.cards.minecraft:MINECRAFT_CARDS \\
        --out-dir assets/card_art/minecraft \\
        --mode manual

    # PIP30 (JSON-driven, localized via en.json):
    python -m scripts.new_set.art_harness \\
        --style src.cards.pip30.style \\
        --cards-json /path/to/PIP30/Assets/StreamingAssets/cards/starter_deck.json \\
        --cards-json-name-key nameKey \\
        --cards-json-text-key descriptionKey \\
        --cards-json-text-lookup /path/to/PIP30/Assets/StreamingAssets/text/en.json \\
        --out-dir /path/to/PIP30/Assets/StreamingAssets/card_art \\
        --mode manual
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import io
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Pillow + requests are only needed in api/local modes. We import them
# lazily so manual mode runs in a minimal environment.

DEFAULT_MODEL = "chatgpt-image-latest"
DEFAULT_DRAW_MODEL = "gpt-5"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_PROVIDER = "auto"


# =============================================================================
# Style config loader
# =============================================================================

@dataclass
class StyleConfig:
    style_headline: str
    category_flavors: dict[str, str]
    categorize: Callable[[Any], str]


def _default_categorize(card: Any) -> str:
    """Fallback categorizer using src.engine.types.CardType."""
    try:
        from src.engine.types import CardType
    except Exception:
        return "object"
    chars = getattr(card, "characteristics", None)
    if not chars:
        return "object"
    types = getattr(chars, "types", set()) or set()
    if CardType.CREATURE in types:
        return "creature"
    if CardType.INSTANT in types or CardType.SORCERY in types:
        return "spell"
    if CardType.ARTIFACT in types:
        return "artifact"
    if CardType.ENCHANTMENT in types:
        return "enchantment"
    if CardType.LAND in types:
        return "land"
    if CardType.PLANESWALKER in types:
        return "planeswalker"
    return "object"


def load_style(style_module_path: str) -> StyleConfig:
    """Import a style module and pull STYLE_HEADLINE / CATEGORY_FLAVORS /
    categorize from it."""
    mod = importlib.import_module(style_module_path)
    style_headline = getattr(mod, "STYLE_HEADLINE", None)
    if not isinstance(style_headline, str) or not style_headline.strip():
        raise ValueError(
            f"{style_module_path}: STYLE_HEADLINE must be a non-empty str."
        )
    category_flavors = getattr(mod, "CATEGORY_FLAVORS", None)
    if not isinstance(category_flavors, dict):
        raise ValueError(
            f"{style_module_path}: CATEGORY_FLAVORS must be a dict[str,str]."
        )
    categorize = getattr(mod, "categorize", None)
    if not callable(categorize):
        categorize = _default_categorize
    return StyleConfig(
        style_headline=style_headline.strip(),
        category_flavors=dict(category_flavors),
        categorize=categorize,
    )


# =============================================================================
# Card source loader
# =============================================================================

def load_cards(cards_arg: str) -> dict[str, Any]:
    """`<module>:<var>` → that module's `<var>` (a card dict)."""
    if ":" not in cards_arg:
        raise ValueError(f"--cards must be 'module:var', got {cards_arg!r}")
    module_path, var_name = cards_arg.split(":", 1)
    mod = importlib.import_module(module_path)
    obj = getattr(mod, var_name, None)
    if not isinstance(obj, dict):
        raise ValueError(
            f"{module_path}:{var_name} is not a dict; got {type(obj).__name__}"
        )
    return obj


def _find_items_list(data: Any, items_key: str | None) -> list[dict]:
    """Locate the list-of-dicts that holds card entries in a parsed JSON
    document. If ``items_key`` is given, take that key verbatim. Otherwise
    require *exactly one* top-level value to be a non-empty list of dicts —
    raising if zero or multiple match, so a JSON file that happens to put a
    ``metadata`` array before the real card list can't mis-load silently."""
    if items_key:
        if not isinstance(data, dict) or items_key not in data:
            raise ValueError(f"--cards-json-items-key {items_key!r} not present at top level")
        items = data[items_key]
        if not isinstance(items, list):
            raise ValueError(f"key {items_key!r} is {type(items).__name__}, not list")
        return [x for x in items if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        candidates = [
            (k, v) for k, v in data.items()
            if isinstance(v, list) and v and isinstance(v[0], dict)
        ]
        if len(candidates) == 1:
            return [x for x in candidates[0][1] if isinstance(x, dict)]
        if len(candidates) > 1:
            keys = ", ".join(k for k, _ in candidates)
            raise ValueError(
                f"multiple list-of-dicts candidates ({keys}); pass "
                f"--cards-json-items-key to disambiguate"
            )
    raise ValueError("no list-of-dicts found; pass --cards-json-items-key to disambiguate")


def _first_str_value(entry: dict, candidates: list[str]) -> str:
    """Return the first non-empty string value from ``entry`` matching one of
    the ``candidates`` keys. Used so a single harness invocation can absorb
    multiple JSON schemas — e.g. PIP30 cards use ``nameKey`` while challenges
    in the same set use ``titleKey``."""
    for key in candidates:
        v = entry.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def load_cards_json(
    paths: list[Path],
    *,
    name_key: str = "name",
    text_key: str = "text",
    text_lookup_path: Path | None = None,
    items_key: str | None = None,
) -> dict[str, Any]:
    """Load card entries from one or more JSON files and return them as a
    ``dict[name, SimpleNamespace]`` matching what ``load_cards`` produces.

    ``name_key`` and ``text_key`` may each be a comma-separated list of
    candidate field names. The loader tries them in order on each entry and
    uses the first non-empty string. This lets one harness invocation cover
    heterogeneous JSON shapes — e.g. PIP30's
    ``--cards-json-name-key nameKey,titleKey`` works for both cards
    (``nameKey``) and coding challenges (``titleKey``).

    All non-name/text fields are preserved as attributes on the resulting
    namespace so a per-set style config's ``categorize()`` can read them
    (e.g. ``card.family``, ``card.codeText``).

    If ``text_lookup_path`` is set, raw name/text values are treated as
    translation keys and resolved through that JSON dict. Missing keys
    fall back to the raw key string — better to surface a weird name than
    silently drop the entry.

    Duplicate names across files are not merged: later entries overwrite
    earlier ones, mirroring how ``load_cards`` would return a single dict.
    """
    name_candidates = [s.strip() for s in name_key.split(",") if s.strip()]
    text_candidates = [s.strip() for s in text_key.split(",") if s.strip()]
    if not name_candidates:
        raise ValueError("name_key must contain at least one field")

    lookup: dict[str, str] = {}
    if text_lookup_path is not None:
        loaded = json.loads(Path(text_lookup_path).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{text_lookup_path}: expected a JSON object of key→string")
        lookup = {k: v for k, v in loaded.items() if isinstance(v, str)}

    result: dict[str, Any] = {}
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = _find_items_list(data, items_key)
        for entry in items:
            raw_name = _first_str_value(entry, name_candidates)
            if not raw_name:
                continue
            name = lookup.get(raw_name, raw_name) if lookup else raw_name
            raw_text = _first_str_value(entry, text_candidates) if text_candidates else ""
            text = (lookup.get(raw_text, raw_text) if lookup else raw_text) if raw_text else ""
            ns_fields = dict(entry)
            ns_fields["name"] = name
            ns_fields["text"] = text
            result[name] = SimpleNamespace(**ns_fields)
    return result


# =============================================================================
# Prompt building
# =============================================================================

def build_prompt(card: Any, style: StyleConfig) -> str:
    category = style.categorize(card)
    cat_line = style.category_flavors.get(
        category,
        style.category_flavors.get("object", ""),
    )
    text = (getattr(card, "text", "") or "").strip()
    text = " ".join(text.split())
    parts = [style.style_headline, f"Card name: {card.name}.", cat_line]
    if text:
        if len(text) > 240:
            text = text[:237] + "..."
        parts.append(f"Card flavor / behavior cue: {text}")
    return " ".join(p for p in parts if p)


def to_filename(name: str) -> str:
    return (
        name.lower()
        .replace("'", "")
        .replace('"', "")
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


# =============================================================================
# Mode implementations
# =============================================================================

def run_manual_mode(
    cards: dict[str, Any],
    style: StyleConfig,
    out_dir: Path,
    *,
    force: bool,
) -> Path:
    """Write `draw_prompts.json` listing every card without an existing
    PNG. Skips PNG-cached cards unless force=True. Returns the path of
    the prompt-pack JSON.

    This is the input the claude-in-chrome browser-automation agent
    consumes in stage 5 of the /new-set pipeline.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pack: list[dict[str, str]] = []
    skipped = 0
    for name, card in sorted(cards.items()):
        filename = f"{to_filename(name)}.png"
        if (out_dir / filename).exists() and not force:
            skipped += 1
            continue
        pack.append({
            "card": name,
            "filename": filename,
            "prompt": build_prompt(card, style),
        })
    prompt_path = out_dir / "draw_prompts.json"
    prompt_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    print(
        f"manual mode: wrote {len(pack)} prompts to "
        f"{prompt_path.relative_to(PROJECT_ROOT)}; skipped {skipped} cached."
    )
    return prompt_path


def run_local_mode(
    cards: dict[str, Any],
    style: StyleConfig,
    out_dir: Path,
    *,
    force: bool,
) -> int:
    """Procedural placeholder — deterministic per-card art useful for
    offline tests so the engine has something to render."""
    from PIL import Image, ImageDraw, ImageFilter      # noqa: F401

    out_dir.mkdir(parents=True, exist_ok=True)
    generated = 0
    palette_keys = list(style.category_flavors.keys()) or ["object"]

    for name, card in sorted(cards.items()):
        out = out_dir / f"{to_filename(name)}.png"
        if out.exists() and not force:
            continue
        seed = int(hashlib.sha256(name.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        cat = style.categorize(card)
        if cat not in palette_keys:
            cat = palette_keys[0]
        img = _make_placeholder(rng, cat, palette_keys)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, format="PNG", optimize=True, compress_level=3)
        generated += 1
    print(f"local mode: generated {generated} placeholders in "
          f"{out_dir.relative_to(PROJECT_ROOT)}")
    return generated


def _make_placeholder(rng: random.Random, category: str, all_categories: list[str]):
    """Deterministic abstract placeholder per category — pure Pillow."""
    from PIL import Image, ImageDraw, ImageFilter
    width = height = 1024
    # Hash category name → color triplet so each category has a distinct hue.
    h = int(hashlib.sha256(category.encode()).hexdigest()[:8], 16)
    base = ((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF)
    img = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(80):
        size = rng.choice([64, 96, 128, 192])
        x1 = rng.randint(-32, width - size + 32)
        y1 = rng.randint(-32, height - size + 32)
        alpha = rng.randint(60, 160)
        tint = (
            (base[0] + rng.randint(-40, 40)) & 0xFF,
            (base[1] + rng.randint(-40, 40)) & 0xFF,
            (base[2] + rng.randint(-40, 40)) & 0xFF,
            alpha,
        )
        draw.rectangle((x1, y1, x1 + size, y1 + size), fill=tint, outline=(0, 0, 0, 200), width=2)
    return img.filter(ImageFilter.GaussianBlur(radius=1.0))


# ---------------------------------------------------------------------------
# api mode — preserved as fallback per user note about hard billing limit.
# ---------------------------------------------------------------------------

@dataclass
class OpenAiImageConfig:
    api_key: str
    model: str
    draw_model: str
    provider: str
    size: str
    quality: str
    timeout_s: float


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        os.environ.setdefault(k, v)


def _maybe_b64(value: Any) -> bytes | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return base64.b64decode(value.strip(), validate=False)
    except Exception:
        return None


def _extract_image_bytes(payload: Any, timeout_s: float) -> bytes:
    import requests
    if not isinstance(payload, (dict, list)):
        raise RuntimeError("OpenAI response payload was empty")
    queue: list[Any] = [payload]
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            for k in ("b64_json", "image_base64", "result"):
                data = _maybe_b64(node.get(k))
                if data:
                    return data
            url = node.get("url") or node.get("image_url")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                r = requests.get(url, timeout=timeout_s)
                r.raise_for_status()
                return r.content
            for k in ("data", "output", "content", "images"):
                child = node.get(k)
                if isinstance(child, list):
                    queue.extend(child)
                elif isinstance(child, dict):
                    queue.append(child)
        elif isinstance(node, list):
            queue.extend(node)
    raise RuntimeError("OpenAI response had no image payload")


def _generate_via_responses(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    import requests
    payload = {
        "model": cfg.draw_model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "tools": [{
            "type": "image_generation",
            "size": cfg.size,
            "quality": cfg.quality,
            "background": "opaque",
            "output_format": "png",
        }],
    }
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=cfg.timeout_s,
    )
    if not r.ok:
        raise RuntimeError(f"Responses API failed ({r.status_code}): {r.text[:240]}")
    return _extract_image_bytes(r.json(), timeout_s=cfg.timeout_s)


def _generate_via_images(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    import requests
    payload = {
        "model": cfg.model,
        "prompt": prompt,
        "size": cfg.size,
        "quality": cfg.quality,
        "output_format": "png",
        "background": "opaque",
    }
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=cfg.timeout_s,
    )
    if not r.ok:
        raise RuntimeError(f"Images API failed ({r.status_code}): {r.text[:240]}")
    return _extract_image_bytes(r.json(), timeout_s=cfg.timeout_s)


def _generate_image(prompt: str, cfg: OpenAiImageConfig) -> bytes:
    provider = cfg.provider.lower()
    providers = ["responses", "images"] if provider == "auto" else [provider]
    last_err: Exception | None = None
    for current in providers:
        try:
            if current == "responses":
                return _generate_via_responses(prompt, cfg)
            return _generate_via_images(prompt, cfg)
        except Exception as exc:
            last_err = exc
            if len(providers) > 1:
                print(f"  provider {current} failed: {exc}; trying next")
    if last_err:
        raise last_err
    raise RuntimeError("Generation failed with no provider error")


def run_api_mode(
    cards: dict[str, Any],
    style: StyleConfig,
    out_dir: Path,
    cfg: OpenAiImageConfig,
    *,
    force: bool,
    retries: int,
    sleep_s: float,
) -> tuple[int, int, int]:
    """API mode — preserved per user note. Hits OpenAI billing limit on
    bulk runs; default pipeline mode is `manual` for that reason."""
    from PIL import Image, ImageOps

    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "_gen_log.json"
    log: list[dict] = []
    generated = skipped = failed = 0
    items = sorted(cards.items())
    total = len(items)
    for i, (name, card) in enumerate(items, 1):
        out_path = out_dir / f"{to_filename(name)}.png"
        if out_path.exists() and not force:
            skipped += 1
            print(f"[{i:03d}/{total}] SKIP {out_path.name}")
            continue
        prompt = build_prompt(card, style)
        attempts: list[str] = []
        success = False
        for attempt in range(1, retries + 1):
            try:
                print(f"[{i:03d}/{total}] GEN  {out_path.name} (attempt {attempt}/{retries})")
                raw = _generate_image(prompt, cfg)
                with Image.open(io.BytesIO(raw)) as src:
                    src = src.convert("RGB")
                    img = ImageOps.fit(src, (1024, 1024), method=Image.Resampling.LANCZOS)
                img.save(out_path, format="PNG", optimize=True, compress_level=3)
                generated += 1
                success = True
                attempts.append("ok")
                break
            except Exception as exc:
                wait = min(20.0, 1.8 * attempt)
                print(f"        FAIL: {exc}")
                attempts.append(str(exc)[:120])
                if attempt < retries:
                    time.sleep(wait)
        log.append({
            "card": name,
            "out": str(out_path.relative_to(PROJECT_ROOT)),
            "attempts": attempts,
            "success": success,
        })
        if not success:
            failed += 1
        if sleep_s > 0:
            time.sleep(sleep_s)
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return generated, skipped, failed


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--style", required=True,
                    help="Python module path to a style config module "
                         "(must define STYLE_HEADLINE + CATEGORY_FLAVORS).")
    ap.add_argument("--cards", default=None,
                    help="`module:var` source for the card dict, e.g. "
                         "src.cards.minecraft:MINECRAFT_CARDS. "
                         "Mutually exclusive with --cards-json.")
    ap.add_argument("--cards-json", action="append", default=[], type=Path,
                    metavar="PATH",
                    help="JSON file with card entries. Repeatable; later files "
                         "merge into the same set. Use for engines whose card "
                         "data lives outside the Python tree (e.g. PIP30's "
                         "StreamingAssets/*.json).")
    ap.add_argument("--cards-json-name-key", default="name", metavar="KEYS",
                    help="Field(s) on each JSON entry to use as the card name. "
                         "Comma-separated to try multiple in order — e.g. "
                         "'nameKey,titleKey' to absorb PIP30 cards (nameKey) "
                         "and challenges (titleKey) in one invocation. "
                         "Default 'name'.")
    ap.add_argument("--cards-json-text-key", default="text", metavar="KEYS",
                    help="Field(s) on each JSON entry to use as card text. "
                         "Comma-separated like --cards-json-name-key. "
                         "Default 'text'. PIP30: 'descriptionKey,promptKey'.")
    ap.add_argument("--cards-json-text-lookup", default=None, type=Path,
                    metavar="PATH",
                    help="Optional translation dict (key→string JSON). When set, "
                         "name/text values are looked up here — e.g. PIP30's "
                         "Assets/StreamingAssets/text/en.json.")
    ap.add_argument("--cards-json-items-key", default=None, metavar="KEY",
                    help="If a JSON file's items aren't at the first list-of-dicts "
                         "top-level key, pass the key explicitly.")
    ap.add_argument("--out-dir", required=True, type=Path,
                    help="Output directory for PNGs and draw_prompts.json.")
    ap.add_argument("--mode", choices=["manual", "api", "local"], default="manual",
                    help="Default `manual` — writes draw_prompts.json for "
                         "the browser-automation agent in stage 5.")
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if a PNG exists already.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap to N cards for testing.")
    ap.add_argument("--only", default="",
                    help="Substring match on card name.")
    # api-mode-only knobs
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--size", default=DEFAULT_SIZE)
    ap.add_argument("--quality", default=DEFAULT_QUALITY)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--draw-model", default=DEFAULT_DRAW_MODEL)
    ap.add_argument("--provider", default=DEFAULT_PROVIDER,
                    choices=["auto", "responses", "images"])
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    _load_dotenv(PROJECT_ROOT / ".env")

    style = load_style(args.style)

    if args.cards and args.cards_json:
        ap.error("--cards and --cards-json are mutually exclusive")
    if not args.cards and not args.cards_json:
        ap.error("one of --cards or --cards-json is required")
    if args.cards:
        cards = load_cards(args.cards)
        cards_src = args.cards
    else:
        cards = load_cards_json(
            args.cards_json,
            name_key=args.cards_json_name_key,
            text_key=args.cards_json_text_key,
            text_lookup_path=args.cards_json_text_lookup,
            items_key=args.cards_json_items_key,
        )
        cards_src = ",".join(str(p) for p in args.cards_json)

    if args.only:
        needle = args.only.lower()
        cards = {n: c for n, c in cards.items() if needle in n.lower()}
    if args.limit > 0:
        cards = dict(list(sorted(cards.items()))[:args.limit])

    print(f"Targeting {len(cards)} cards from {cards_src}")

    if args.mode == "manual":
        run_manual_mode(cards, style, args.out_dir, force=args.force)
        return 0

    if args.mode == "local":
        run_local_mode(cards, style, args.out_dir, force=args.force)
        return 0

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY not set — falling back to local placeholders.")
        run_local_mode(cards, style, args.out_dir, force=args.force)
        return 0

    cfg = OpenAiImageConfig(
        api_key=api_key,
        model=args.model,
        draw_model=args.draw_model,
        provider=args.provider,
        size=args.size,
        quality=args.quality,
        timeout_s=args.timeout,
    )
    g, s, f = run_api_mode(
        cards, style, args.out_dir, cfg,
        force=args.force, retries=args.retries, sleep_s=args.sleep,
    )
    print(f"api mode: generated={g} skipped={s} failed={f}")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
