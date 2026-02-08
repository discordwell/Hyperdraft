#!/usr/bin/env python3
"""
Precompute "how to play this card" (Layer 1: CardStrategy) for MTG cards.

This is an offline tool that:
- iterates through the local MTG card registry (src.cards.ALL_CARDS)
- optionally fetches extra context (netdeck usage + Scryfall rulings)
- uses an LLM provider to generate CardStrategy JSON
- stores results in ~/.hyperdraft/llm_cache/ via LLMCache

The game engine will automatically use these cached strategies when preparing
layers for a match (AIEngine.prepare_for_match -> LayerGenerator -> LLMCache).

Usage:
  python scripts/precompute_card_strategies.py --limit 50
  python scripts/precompute_card_strategies.py --provider openai --model gpt-4o-mini --workers 8
  python scripts/precompute_card_strategies.py --no-scryfall --no-netdeck-usage
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, ".")

from src.ai.llm.cache import LLMCache
from src.ai.llm.config import LLMConfig, ProviderType
from src.ai.llm.api_provider import get_provider
from src.ai.llm.prompts import (
    CARD_STRATEGY_SYSTEM,
    CARD_STRATEGY_PROMPT,
    CARD_STRATEGY_SCHEMA,
)
from src.ai.layers.types import CardStrategy
from src.ai.research.netdeck_usage import build_netdeck_usage, format_usage_context
from src.ai.research.scryfall import ScryfallClient
from src.cards import ALL_CARDS


def _load_dotenv_if_present(path: Path) -> None:
    """
    Minimal dotenv loader.

    We avoid adding python-dotenv as a hard dependency.
    Only sets env vars that are not already set.
    """
    if not path.exists():
        return

    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k or k in os.environ:
                continue
            os.environ[k] = v
    except Exception:
        return


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _build_prompt(card_def, extra_context: list[str]) -> str:
    prompt = CARD_STRATEGY_PROMPT.format(
        name=card_def.name,
        cost=card_def.characteristics.mana_cost or "N/A",
        type=str(list(card_def.characteristics.types)),
        text=card_def.text or "No text",
        pt=f"{card_def.characteristics.power or '-'}/{card_def.characteristics.toughness or '-'}",
    )

    extra = [s.strip() for s in extra_context if s and s.strip()]
    if not extra:
        return prompt

    joined = "\n".join(f"- {s}" for s in extra)
    return (
        f"{prompt}\n\n"
        "Additional context (from decklists / official rulings):\n"
        f"{joined}"
    )


async def _generate_one(
    name: str,
    provider,
    cache: LLMCache,
    *,
    scryfall: Optional[ScryfallClient],
    netdeck_usage_map,
    netdeck_total: int,
    force: bool,
) -> tuple[str, bool, Optional[str]]:
    """
    Returns: (card_name, did_write, error)
    """
    # Skip if already cached and not forcing.
    if not force:
        existing = cache.get_card_strategy(name)
        if existing:
            return name, False, None

    card_def = ALL_CARDS.get(name)
    if not card_def:
        return name, False, "missing from ALL_CARDS"

    extra_context: list[str] = []

    # Local "web-derived" context from our netdeck corpus.
    if netdeck_usage_map is not None and netdeck_total > 0:
        usage = format_usage_context(name, netdeck_usage_map, netdeck_total)
        if usage:
            extra_context.append(usage)

    # Official rulings via Scryfall (web).
    if scryfall is not None:
        ctx = await asyncio.to_thread(scryfall.get_card_context, name)
        if ctx and ctx.rulings:
            # Keep short: rulings can be long and repetitive.
            for r in ctx.rulings[:5]:
                extra_context.append(f"Official ruling: {r}")

    prompt = _build_prompt(card_def, extra_context)

    try:
        result = await provider.complete_json(
            prompt=prompt,
            schema=CARD_STRATEGY_SCHEMA,
            system=CARD_STRATEGY_SYSTEM,
        )
    except Exception as e:
        return name, False, f"llm_error: {e}"

    # Normalize and clamp.
    strategy = CardStrategy(
        card_name=card_def.name,
        timing=str(result.get("timing", "any") or "any"),
        base_priority=_clamp01(result.get("base_priority", 0.5)),
        role=str(result.get("role", "utility") or "utility"),
        target_priority=list(result.get("target_priority", ["creature"]) or ["creature"]),
        when_to_play=str(result.get("when_to_play", "") or ""),
        when_not_to_play=str(result.get("when_not_to_play", "") or ""),
        targeting_advice=str(result.get("targeting_advice", "") or ""),
    )

    cache.set_card_strategy(card_def.name, strategy.to_dict(), provider.model_name)
    return name, True, None


async def main_async(args) -> int:
    _load_dotenv_if_present(Path(".env"))

    # Configure provider.
    config = LLMConfig()
    if args.provider:
        config.provider = ProviderType(args.provider)
    if args.model:
        # Map model arg to provider-specific model field.
        if config.provider == ProviderType.OPENAI:
            config.openai_model = args.model
        elif config.provider == ProviderType.ANTHROPIC:
            config.anthropic_model = args.model
        elif config.provider == ProviderType.OLLAMA:
            config.ollama_model = args.model

    try:
        provider = get_provider(config)
    except Exception as e:
        print(f"Failed to create LLM provider: {e}", file=sys.stderr)
        return 2

    # Basic dependency check: providers require aiohttp at runtime.
    try:
        import aiohttp  # noqa: F401
    except Exception:
        print("aiohttp is not installed; required for LLM providers. Install: pip install aiohttp", file=sys.stderr)
        return 2

    cache = LLMCache()

    # Optional context sources.
    netdeck_usage_map = None
    netdeck_total = 0
    if not args.no_netdeck_usage:
        try:
            netdeck_usage_map, netdeck_total = build_netdeck_usage()
        except Exception:
            netdeck_usage_map = None
            netdeck_total = 0

    scryfall = None
    if not args.no_scryfall:
        scryfall = ScryfallClient()

    # Build card list.
    names = sorted(ALL_CARDS.keys())
    if args.shuffle:
        rng = random.Random(args.seed)
        rng.shuffle(names)

    if args.offset:
        names = names[args.offset :]
    if args.limit:
        names = names[: args.limit]

    sem = asyncio.Semaphore(args.workers)
    wrote = 0
    skipped = 0
    failed = 0

    async def run_one(nm: str):
        nonlocal wrote, skipped, failed
        async with sem:
            _nm, did_write, err = await _generate_one(
                nm,
                provider,
                cache,
                scryfall=scryfall,
                netdeck_usage_map=netdeck_usage_map,
                netdeck_total=netdeck_total,
                force=args.force,
            )
            if err:
                failed += 1
                if args.verbose:
                    print(f"[fail] {_nm}: {err}")
                return
            if did_write:
                wrote += 1
                if args.verbose:
                    print(f"[ok] {_nm}")
            else:
                skipped += 1
                if args.verbose:
                    print(f"[skip] {_nm}")

    # Process sequentially but allow concurrency via semaphore.
    tasks = [asyncio.create_task(run_one(nm)) for nm in names]
    for i, t in enumerate(asyncio.as_completed(tasks), 1):
        await t
        if args.progress_every and i % args.progress_every == 0:
            print(f"progress: {i}/{len(names)} wrote={wrote} skipped={skipped} failed={failed}")

    print(f"done: total={len(names)} wrote={wrote} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Precompute MTG CardStrategy layer into LLMCache")
    p.add_argument("--provider", choices=["ollama", "openai", "anthropic"], default=None)
    p.add_argument("--model", default=None, help="Provider model name override")
    p.add_argument("--workers", type=int, default=6, help="Concurrent workers (default: 6)")
    p.add_argument("--limit", type=int, default=0, help="Only process first N cards (default: all)")
    p.add_argument("--offset", type=int, default=0, help="Skip first N cards (default: 0)")
    p.add_argument("--shuffle", action="store_true", help="Shuffle card order (helps parallel runs)")
    p.add_argument("--seed", type=int, default=0, help="Shuffle seed (default: 0)")
    p.add_argument("--force", action="store_true", help="Regenerate even if cache hit")
    p.add_argument("--no-scryfall", action="store_true", help="Disable Scryfall rulings fetch")
    p.add_argument("--no-netdeck-usage", action="store_true", help="Disable local netdeck usage context")
    p.add_argument("--progress-every", type=int, default=50, help="Progress log cadence (default: 50)")
    p.add_argument("--verbose", action="store_true", help="Verbose per-card logging")
    args = p.parse_args(argv)

    if args.workers < 1:
        args.workers = 1

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

