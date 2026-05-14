#!/usr/bin/env python3
"""Engine-agnostic ChatGPT-web art runner.

Single command that drives the whole imagegen loop for any Hyperdraft
set. Wraps ``scripts/phyrexian_overworld/playwright_gen.py`` — adds the
``--engine`` + ``--set`` convention so you don't have to remember the
queue / served-PNG paths.

## What it does

1. Reads ``assets/card_art/<engine>/<set>/draw_prompts.json`` (written
   by ``scripts/new_set/art_harness.py --mode manual``).
2. Skips entries whose served PNG already exists in
   ``frontend/public/<engine>-art/<set>/``.
3. Launches a headed Chrome via Playwright with a persistent profile at
   ``~/.hyperdraft_chatgpt_profile``. First run prompts you to sign in;
   subsequent runs reuse the cookies.
4. For each remaining card: pastes the prompt, waits for ChatGPT to
   generate, downloads the PNG straight into the served dir.
5. Resume-safe — Ctrl-C any time, re-run, picks up where it left off.

## Example

    # FBN (this set):
    python -m scripts.new_set.art_chatgpt_runner --engine scp --set foundations_beyond

    # MNR (the previous SCP expansion):
    python -m scripts.new_set.art_chatgpt_runner --engine scp --set mnr

    # Smoke-test the loop with 2 cards before committing 5 hours:
    python -m scripts.new_set.art_chatgpt_runner --engine scp --set foundations_beyond --limit 2

    # Custom paths if your set doesn't follow the convention:
    python -m scripts.new_set.art_chatgpt_runner --engine pokemon --set sv_starter \\
        --queue-dir /custom/queue --served-dir /custom/served

## Prerequisites

- ``pip install playwright && playwright install chromium``
- ChatGPT Plus account (image gen quota)
- For first run: the script opens Chrome, points at chatgpt.com, and
  waits for you to sign in. After that, the persistent profile keeps
  the session forever (until ChatGPT logs you out server-side).

## Cross-set resume

Each set has its own queue dir + served dir, so switching engines /
sets never disturbs the other set's progress. Mid-run interrupts are
fine — the served PNG is the on-disk resume marker; if it's on disk,
the next launch skips it.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _queue_dir(engine: str, set_slug: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "assets" / "card_art" / engine / set_slug


def _served_dir(engine: str, set_slug: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "frontend" / "public" / f"{engine}-art" / set_slug


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", required=True, help="engine slug (scp / pokemon / mtg-custom / ...)")
    ap.add_argument("--set", dest="set_slug", required=True, help="set slug (foundations_beyond / mnr / sv_starter / ...)")
    ap.add_argument("--queue-dir", help="override; default assets/card_art/<engine>/<set>/")
    ap.add_argument("--served-dir", help="override; default frontend/public/<engine>-art/<set>/")
    ap.add_argument("--profile", help="Playwright profile dir; default ~/.hyperdraft_chatgpt_profile")
    ap.add_argument("--limit", type=int, default=0, help="stop after N successful cards (smoke test)")
    ap.add_argument("--headless", action="store_true", help="run Chrome headless (NOT recommended for first login)")
    ap.add_argument("--timeout", type=int, default=240, help="max seconds per image")
    ap.add_argument("--pacing", type=float, default=5.0, help="seconds to sleep between cards")
    ap.add_argument("--resume-from", default="", help="skip until filename contains this substring")
    args = ap.parse_args()

    queue_dir = _queue_dir(args.engine, args.set_slug, args.queue_dir)
    served_dir = _served_dir(args.engine, args.set_slug, args.served_dir)
    queue_path = queue_dir / "draw_prompts.json"

    if not queue_path.exists():
        print(
            f"[runner] queue not found: {queue_path}\n"
            f"[runner] hint: run art_harness --mode manual first:\n"
            f"  python -m scripts.new_set.art_harness \\\n"
            f"    --style src.cards.{args.engine}.{args.set_slug}.style \\\n"
            f"    --cards src.cards.{args.engine}.{args.set_slug}:<SET>_CARDS \\\n"
            f"    --out-dir {queue_dir} \\\n"
            f"    --mode manual",
            file=sys.stderr,
        )
        return 1

    served_dir.mkdir(parents=True, exist_ok=True)
    print(f"[runner] engine={args.engine} set={args.set_slug}")
    print(f"[runner] queue:  {queue_path}")
    print(f"[runner] served: {served_dir}")

    # Translate to playwright_gen's flag set and call its async main.
    fake_argv = [
        "playwright_gen.py",
        "--queue", str(queue_path),
        "--out-dir", str(served_dir),
        "--timeout", str(args.timeout),
        "--pacing", str(args.pacing),
    ]
    if args.limit:
        fake_argv += ["--limit", str(args.limit)]
    if args.headless:
        fake_argv += ["--headless"]
    if args.resume_from:
        fake_argv += ["--resume-from", args.resume_from]
    if args.profile:
        fake_argv += ["--profile", args.profile]

    sys.argv = fake_argv
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "phyrexian_overworld"))
    import playwright_gen  # noqa: E402 — late import after argv rewrite

    return asyncio.run(playwright_gen.amain())


if __name__ == "__main__":
    sys.exit(main())
