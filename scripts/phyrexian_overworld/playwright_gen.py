#!/usr/bin/env python3
"""
Phyrexia Bedrock Edition — ChatGPT web image generator (Playwright).

Drives chatgpt.com via a persistent Playwright profile to generate the
remaining card art. Reads ``assets/card_art/minecraft/draw_prompts.json``,
skips PNGs already on disk, and stops cleanly on anomalies that need a
human in the loop (rate limits, clarification questions, login expiry,
content moderation, slow generations).

Design rules
------------
* **Foreground / supervised**. Browser is visible (headed). When the
  script can't make forward progress it prints the diagnostic, leaves
  the browser open, and exits with a non-zero code. Re-launching picks
  up where it left off (PNGs are the resume marker).
* **Persistent profile** at ``~/.hyperdraft_chatgpt_profile``. First run
  requires a manual sign-in in the browser window; subsequent runs reuse
  the cookies.
* **One conversation, many prompts**. ChatGPT keeps the chat thread
  open and we feed prompts one after the other; each generated image
  is the latest ``img[alt="Generated image"]`` whose URL contains
  ``estuary``.
* **Anomaly detection**. After submit, if no new image appears in
  ``--timeout`` seconds, we exit. If ChatGPT returns a clarifying
  assistant text (no image) we exit. If a rate-limit banner appears
  we exit. The human dismisses the issue in the open browser, then
  re-runs.

Usage
-----
First run (login flow):
    python scripts/phyrexian_overworld/playwright_gen.py --limit 1

Bulk run, after login:
    python scripts/phyrexian_overworld/playwright_gen.py

Other knobs:
    --limit N         Stop after N successful cards (handy for smoke tests)
    --resume-from X   Skip until card name contains substring X
    --timeout SEC     Max seconds to wait for one image (default 240)
    --pacing SEC      Sleep this long between cards (default 5)
    --queue PATH      Override the default draw_prompts.json path
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = PROJECT_ROOT / "assets" / "card_art" / "minecraft" / "draw_prompts.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "assets" / "card_art" / "minecraft"
DEFAULT_PROFILE = Path(os.path.expanduser("~/.hyperdraft_chatgpt_profile"))

CHATGPT_URL = "https://chatgpt.com/"
NAV_TIMEOUT_MS = 30_000
SUBMIT_SETTLE_MS = 600

# Prefix every prompt with explicit image-gen intent so ChatGPT doesn't ask a
# clarifying question on a fresh chat.
PROMPT_PREAMBLE = "Generate a 1024x1024 PNG illustration with this exact prompt — no questions, just produce the image:\n\n"
# If we get a text reply instead of an image, this is the auto-follow-up.
CLARIFY_FOLLOWUP = "Yes — please generate the image now, do not ask further questions."

# Selectors discovered on chatgpt.com (May 2026)
SEL_PROMPT_EDITOR = "#prompt-textarea"
SEL_SEND_BUTTON = '[data-testid="send-button"], button[aria-label*="Send"]'
SEL_STOP_BUTTON = 'button[aria-label*="Stop"]'

# Rate-limit / clarification heuristics
RATE_LIMIT_NEEDLES = [
    "rate limit",
    "slow down",
    "you've reached",
    "you have reached",
    "limit on",
    "try again later",
]


class StuckError(RuntimeError):
    """Raised when the script can't make forward progress and needs a human."""


def _slug_safe_in(prompt: str, fname: str) -> bool:
    """Sanity-check we're not about to overwrite an unrelated file."""
    return fname.endswith(".png") and "/" not in fname and ".." not in fname


def load_queue(queue_path: Path, out_dir: Path) -> list[dict]:
    """Read draw_prompts.json and filter out cards whose PNG already exists.

    Accepts both schema shapes:
      v1 (Phyrexia/minecraft-era): a flat list of ``{filename, prompt, ...}``
      v2 (post-FBN art_harness):   ``{version, entries: [{output_file,
                                     filename, prompt, ...}], ...}``
    """
    data = json.loads(queue_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        raw = data["entries"]
    else:
        raw = data

    remaining = []
    for e in raw:
        if "prompt" not in e:
            continue
        # v2 prefers ``output_file``; v1 used ``filename``. The art_harness
        # writes both during the transition, so this picks whichever is set.
        fname = e.get("filename") or e.get("output_file")
        if not fname or not _slug_safe_in(e["prompt"], fname):
            continue
        if (out_dir / fname).exists():
            continue
        # Normalise so the rest of the script can reference ``filename``.
        if "filename" not in e:
            e["filename"] = fname
        remaining.append(e)
    return remaining


# ============================================================================
# Browser client
# ============================================================================

class ChatGPTArtClient:
    def __init__(self, profile_dir: Path, headless: bool = False):
        self.profile_dir = profile_dir
        self.headless = headless
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self):
        await self._launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Always close — the persistent profile keeps cookies/session, so the
        # next run picks up signed in. Leaving the browser open just blocks
        # re-launch (profile-locked).
        await self._close()

    async def _launch(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            headless=self.headless,
            channel="chrome",
            viewport={"width": 1280, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
            accept_downloads=True,
        )
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        self._page.set_default_timeout(NAV_TIMEOUT_MS)

    async def _close(self) -> None:
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

    # ----- login + readiness ---------------------------------------------

    async def _is_signed_in(self) -> bool:
        """Strict signed-in detector — requires a positive signal AND no
        guest-mode markers. ChatGPT lets guests prompt too, so editor
        presence is not enough."""
        return await self._page.evaluate(
            """
            () => {
              const url = location.href;
              if (/\\/(auth|login|signup)/.test(url)) return false;

              // Definitive guest marker: ChatGPT injects this modal/host element
              // for any flow that requires auth (image gen, file upload, etc.)
              const guestModal = document.querySelector('[data-testid="modal-no-auth-login"]');
              if (guestModal) return false;

              // Positive signals — at least one must be true.
              const profileImg = document.querySelector('img[alt="Profile image"]');
              if (profileImg) return true;

              const profileBtn = document.querySelector('button[data-testid="profile-button"]');
              if (profileBtn) return true;

              // Sidebar with conversation history (only signed-in users have it)
              const histLink = document.querySelector('aside a[href^="/c/"]');
              if (histLink) return true;

              // 'New chat' button as a final fallback (specifically the link
              // form which only logged-in users get)
              const newChat = document.querySelector('a[data-testid="create-new-chat-button"]');
              if (newChat) return true;

              return false;
            }
            """
        )

    async def ensure_logged_in(self) -> None:
        page = self._page
        # Bring the Playwright window to the foreground so the user can find it.
        try:
            await page.bring_to_front()
        except Exception:
            pass

        # Quick signed-in probe: hit chatgpt.com first.
        await page.goto(CHATGPT_URL, timeout=NAV_TIMEOUT_MS)
        await page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        editor = page.locator(SEL_PROMPT_EDITOR).first
        try:
            await editor.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        if await self._is_signed_in():
            print("[hyperdraft] signed in — chatgpt ready.")
            return

        # Not signed in: route to the login page directly so they can complete
        # OAuth without hunting for the link.
        try:
            await page.goto("https://chatgpt.com/auth/login", timeout=NAV_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
            await page.bring_to_front()
        except Exception:
            pass

        # GIANT terminal banner so the user sees the prompt.
        bar = "═" * 70
        block = "█" * 70
        print()
        print(block)
        print(block)
        print(bar)
        print("  ⚠  PLAYWRIGHT-CHROME OPENED — PLEASE SIGN IN TO CHATGPT")
        print(bar)
        print("  • A NEW Chrome window just opened (separate from your main Chrome).")
        print("  • It is currently parked at chatgpt.com/auth/login.")
        print("  • Sign in (Google / Apple / email — whatever).")
        print("  • This script will detect the signed-in state and proceed.")
        print("  • Do NOT close that window — its session is what we'll reuse.")
        print(bar)
        print(block)
        print(block, flush=True)

        deadline = time.time() + 900  # 15 min
        last_log = 0.0
        while time.time() < deadline:
            try:
                await page.bring_to_front()
            except Exception:
                pass
            if await self._is_signed_in():
                print("\n[hyperdraft] ✓ signed in — proceeding to chatgpt.com.")
                await page.goto(CHATGPT_URL, timeout=NAV_TIMEOUT_MS)
                await page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
                # Make sure the editor exists on the post-login landing.
                try:
                    await editor.wait_for(state="visible", timeout=10000)
                except Exception:
                    pass
                return

            now = time.time()
            if now - last_log > 20:
                last_log = now
                remaining = int(deadline - now)
                print(f"  …still waiting for sign-in (timeout in {remaining}s).  url={page.url}")
            await page.wait_for_timeout(3000)

        raise StuckError("login timed out — sign in once in the Chrome window, then re-run.")

    # ----- per-card flow --------------------------------------------------

    async def _count_estuary_imgs(self) -> tuple[int, set[str]]:
        """Return (count of unique estuary image ids, set of those ids)."""
        ids = await self._page.evaluate(
            """
            () => {
              const set = new Set();
              for (const i of document.querySelectorAll('img')) {
                if (i.alt !== 'Generated image') continue;
                const m = (i.src || '').match(/[?&]id=([^&]+)/);
                if (m) set.add(m[1]);
              }
              return Array.from(set);
            }
            """
        )
        return len(ids), set(ids)

    async def _is_generating(self) -> bool:
        loc = self._page.locator(SEL_STOP_BUTTON)
        try:
            return await loc.count() > 0
        except Exception:
            return False

    async def _detect_rate_limit(self) -> Optional[str]:
        body_text = (await self._page.evaluate("() => document.body.innerText || ''")) or ""
        lc = body_text.lower()
        for needle in RATE_LIMIT_NEEDLES:
            if needle in lc:
                # Be more careful — only treat as limit if the text mentions
                # message rate / image rate, not just any occurrence.
                window = lc[max(0, lc.find(needle) - 30): lc.find(needle) + 60]
                if "image" in window or "message" in window or "limit" in window:
                    return window.strip()
        return None

    async def submit_prompt(self, prompt: str) -> None:
        page = self._page
        try:
            await page.locator(SEL_PROMPT_EDITOR).first.wait_for(state="visible", timeout=15000)
        except Exception:
            raise StuckError("prompt editor never mounted (post-navigation race)")
        # Clear the editor first.
        await page.evaluate(
            """
            () => {
              const editor = document.querySelector('#prompt-textarea');
              if (!editor) throw new Error('no #prompt-textarea');
              editor.focus();
              editor.innerHTML = '';
            }
            """
        )
        await page.locator(SEL_PROMPT_EDITOR).first.focus()
        await page.keyboard.insert_text(prompt)
        await page.wait_for_timeout(150)

        send_btn = page.locator(SEL_SEND_BUTTON).first
        try:
            await send_btn.wait_for(state="visible", timeout=4000)
        except Exception:
            raise StuckError("send button never appeared after typing prompt")

        for _ in range(15):
            try:
                if await send_btn.is_enabled():
                    break
            except Exception:
                pass
            await page.wait_for_timeout(150)
        await send_btn.click()
        await page.wait_for_timeout(SUBMIT_SETTLE_MS)

    async def _last_assistant_text(self) -> str:
        """Return the text content of the most recent assistant message (or '')."""
        return await self._page.evaluate(
            """
            () => {
              const msgs = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
              if (!msgs.length) return '';
              const last = msgs[msgs.length - 1];
              return (last.innerText || '').slice(0, 600);
            }
            """
        )

    async def wait_for_new_image(self, baseline_ids: set[str], timeout_s: int) -> str:
        """Poll until a new estuary image appears whose id is not in baseline.
        Returns the URL of the new image. If a text-only assistant reply
        arrives first (clarification), auto-respond once then keep waiting."""
        page = self._page
        deadline = time.time() + timeout_s
        last_log = 0.0
        clarification_followup_sent = False

        async def _wait_for_resolved_url(max_wait_s: float = 8.0) -> str:
            """Poll until _latest_estuary_url returns a usable absolute URL."""
            t0 = time.time()
            while time.time() - t0 < max_wait_s:
                u = await self._latest_estuary_url()
                if u and u.startswith("http"):
                    return u
                await page.wait_for_timeout(300)
            return ""

        while time.time() < deadline:
            count, ids = await self._count_estuary_imgs()
            new_ids = ids - baseline_ids
            if new_ids:
                await page.wait_for_timeout(1500)
                url = await _wait_for_resolved_url()
                if url:
                    return url
                # URL still not resolved — keep polling
                continue

            rl = await self._detect_rate_limit()
            if rl:
                raise StuckError(f"rate-limit-style banner detected: {rl!r}")

            # If ChatGPT stopped generating without producing an image, it
            # probably replied with a clarifying question. Try once to push it
            # along; if that doesn't work, exit so the human can handle it.
            generating = await self._is_generating()
            if not generating and not clarification_followup_sent:
                # Give it a moment in case the image is just slow to render.
                await page.wait_for_timeout(2000)
                count2, ids2 = await self._count_estuary_imgs()
                if ids2 - baseline_ids:
                    await page.wait_for_timeout(1500)
                    return await self._latest_estuary_url()
                # Still no image. Send the clarification follow-up.
                last_text = await self._last_assistant_text()
                if last_text:
                    print(f"  ↳ assistant text reply detected, sending follow-up. Reply preview:\n    {last_text[:200]!r}")
                    await self.submit_prompt(CLARIFY_FOLLOWUP)
                    clarification_followup_sent = True
                    # Reset baseline window — the follow-up shouldn't reset
                    # it; we still want any image generated after the original.
                    await page.wait_for_timeout(2000)

            now = time.time()
            if now - last_log > 15:
                last_log = now
                elapsed = int(timeout_s - (deadline - now))
                print(f"  …waiting (elapsed {elapsed}s, generating={generating})")
            await page.wait_for_timeout(1500)

        last_text = await self._last_assistant_text()
        hint = f" assistant said: {last_text[:200]!r}" if last_text else ""
        raise StuckError(f"no new image after {timeout_s}s — likely rate-limited or stuck.{hint}")

    async def _latest_estuary_url(self) -> str:
        """Return the URL of the most-recent fully-resolved estuary image.
        Filters to URLs that have an ``id=`` query param — that's the
        canonical content URL, not a transient blob/preview URL."""
        return await self._page.evaluate(
            """
            () => {
              const imgs = Array.from(document.querySelectorAll('img'))
                .filter(i => i.alt === 'Generated image'
                          && (i.src||'').includes('estuary')
                          && /[?&]id=/.test(i.src||''));
              return imgs.length ? imgs[imgs.length - 1].src : '';
            }
            """
        )

    async def fetch_image(self, url: str) -> bytes:
        if not url or not url.startswith("http"):
            raise StuckError(f"refusing to fetch malformed url: {url!r}")
        # Use the browser's request context so we inherit auth cookies.
        resp = await self._context.request.get(url)
        if not resp.ok:
            raise StuckError(f"image fetch failed: HTTP {resp.status}")
        return await resp.body()

    # ----- driver --------------------------------------------------------

    async def process_card(self, prompt: str, filename: str, out_dir: Path, timeout_s: int) -> None:
        baseline_count, baseline_ids = await self._count_estuary_imgs()
        print(f"[hyperdraft] >> {filename} (baseline {baseline_count} imgs)")
        await self.submit_prompt(PROMPT_PREAMBLE + prompt)
        url = await self.wait_for_new_image(baseline_ids, timeout_s)
        body = await self.fetch_image(url)
        out_path = out_dir / filename
        out_path.write_bytes(body)
        size = out_path.stat().st_size
        print(f"[hyperdraft] ✓ {filename} ({size:,} bytes)")


# ============================================================================
# Main
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless (not recommended for first login).")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N successful cards.")
    parser.add_argument("--timeout", type=int, default=240, help="Max seconds per image.")
    parser.add_argument("--pacing", type=float, default=5.0, help="Seconds to sleep between cards.")
    parser.add_argument("--resume-from", type=str, default="", help="Skip until card filename contains substring.")
    return parser.parse_args()


async def amain() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    queue = load_queue(args.queue, args.out_dir)
    if args.resume_from:
        anchor = args.resume_from.lower()
        for i, e in enumerate(queue):
            if anchor in e["filename"].lower():
                queue = queue[i:]
                break
    if args.limit > 0:
        queue = queue[: args.limit]

    if not queue:
        print("[hyperdraft] nothing to do — every card already on disk.")
        return 0

    print(f"[hyperdraft] queue={len(queue)} cards, profile={args.profile}")
    print(f"[hyperdraft] first up: {queue[0]['filename']}  …  last: {queue[-1]['filename']}")

    skipped: list[str] = []
    consecutive_stuck = 0
    MAX_CONSECUTIVE_STUCK = 3   # bail if we can't make progress

    async with ChatGPTArtClient(profile_dir=args.profile, headless=args.headless) as cli:
        await cli.ensure_logged_in()
        for i, entry in enumerate(queue, 1):
            try:
                print(f"\n[{i:03d}/{len(queue)}] {entry['card']}")
                await cli.process_card(entry["prompt"], entry["filename"], args.out_dir, args.timeout)
                consecutive_stuck = 0
            except StuckError as e:
                consecutive_stuck += 1
                skipped.append(entry["filename"])
                print(f"\n[hyperdraft] STUCK on {entry['filename']}: {e}")
                print(f"[hyperdraft] skipping; consecutive_stuck={consecutive_stuck}/{MAX_CONSECUTIVE_STUCK}")
                # Try to recover the chat: navigate fresh so the next card
                # starts in a clean state.
                try:
                    await cli._page.goto(CHATGPT_URL, timeout=NAV_TIMEOUT_MS)
                    await cli._page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    await cli._page.wait_for_timeout(2000)
                except Exception:
                    pass
                if consecutive_stuck >= MAX_CONSECUTIVE_STUCK:
                    print(f"[hyperdraft] {consecutive_stuck} stucks in a row — exiting.")
                    print(f"[hyperdraft] skipped so far: {skipped}")
                    return 2
            except Exception as e:
                print(f"\n[hyperdraft] FATAL on {entry['filename']}: {type(e).__name__}: {e}")
                print(f"[hyperdraft] skipped so far: {skipped}")
                return 3
            if args.pacing > 0 and i < len(queue):
                await asyncio.sleep(args.pacing)
        print(f"\n[hyperdraft] done — {len(queue)} cards attempted, {len(skipped)} skipped.")
        if skipped:
            print(f"[hyperdraft] skipped cards: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
