"""
Compose all 150 Beyond Ravnica cards into final SV-style PNGs.

Iterates GUILD_REGISTRIES, slugifies each card name, locates art under
assets/card_art/beyond/ravnica/, and writes the composed card to
assets/card_art/beyond/ravnica/composed/.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.beyond.render_card import render_card  # noqa: E402
from src.cards.pokemon.beyond.ravnica import GUILD_REGISTRIES  # noqa: E402


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[',.]", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def main():
    art_dir = PROJECT_ROOT / "assets" / "card_art" / "beyond" / "ravnica"
    out_dir = art_dir / "composed"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    with_art = 0
    failed = []
    t0 = time.time()

    for guild, registry in sorted(GUILD_REGISTRIES.items()):
        guild_out = out_dir / guild
        guild_out.mkdir(exist_ok=True)
        for name, card_def in registry.items():
            slug = slugify(card_def.name)
            art_path = art_dir / f"{slug}.png"
            art_str = str(art_path) if art_path.exists() else None
            try:
                img = render_card(card_def, art_path=art_str)
                img.save(guild_out / f"{slug}.png")
                total += 1
                if art_str:
                    with_art += 1
            except Exception as ex:
                failed.append((guild, slug, type(ex).__name__, str(ex)))
                print(f"  FAIL {guild}/{slug}: {type(ex).__name__}: {ex}")

    dt = time.time() - t0
    print()
    print(f"Composed: {total}/150  with art: {with_art}  failed: {len(failed)}")
    print(f"Time: {dt:.1f}s")
    print(f"Output: {out_dir}/<guild>/<slug>.png")
    if failed:
        print("\nFailures:")
        for g, s, et, em in failed:
            print(f"  {g}/{s}: {et}: {em}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
