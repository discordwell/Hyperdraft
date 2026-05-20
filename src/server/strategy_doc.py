"""Strategy-doc bootstrap + reader.

The ultra-agent reads ``storage/strategy/<game_mode>.md`` (writable, in the
named volume so updates survive image rebuilds) and falls back to
``docs/strategy/<game_mode>.md`` (the shipped baseline, read-only image
layer). This module seeds the writable copies from the baseline on
lifespan startup — first deploy populates the volume; subsequent deploys
preserve whatever the LLM pilots have written.

The pairing with the launcher (scripts/launch_ultra_agent.sh) is:

  1. launcher exports STRATEGY_DOC=storage/strategy/<mode>.md if present
     else docs/strategy/<mode>.md
  2. launcher exports SCRATCHPAD=storage/ultra-agent/notes/<MATCH_ID>__<AI_PLAYER_ID>.md
     (created empty if missing)
  3. claude reads both at session start, writes scratchpad turn-by-turn,
     appends "Session takeaway" to STRATEGY_DOC at game end.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Path layout — relative paths so the same code works in /app (container)
# and the dev checkout.
BASELINE_DIR = Path("docs/strategy")
WRITABLE_DIR = Path("storage/strategy")
NOTES_DIR = Path("storage/ultra-agent/notes")

# The 8 game modes that ship strategy docs.
KNOWN_MODES = ("mtg", "hearthstone", "pokemon", "yugioh", "minecraft", "finance", "depths", "scp")


def bootstrap() -> None:
    """Seed storage/strategy/<mode>.md from docs/strategy/<mode>.md if missing.

    Safe to call on every lifespan startup: existing writable copies are
    untouched, so LLM-pilot edits accumulated across previous matches
    are preserved.
    """
    WRITABLE_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_DIR.exists():
        log.info("strategy-doc bootstrap: no %s directory; nothing to seed", BASELINE_DIR)
        return

    seeded = 0
    skipped = 0
    for mode in KNOWN_MODES:
        baseline = BASELINE_DIR / f"{mode}.md"
        writable = WRITABLE_DIR / f"{mode}.md"
        if writable.exists():
            skipped += 1
            continue
        if not baseline.exists():
            # Mode without a shipped strategy doc — create a minimal stub
            # so the launcher's STRATEGY_DOC=... path always resolves.
            writable.write_text(
                f"# {mode.capitalize()} — Strategy Doc\n\n"
                f"This file accumulates session takeaways from LLM-piloted matches.\n\n"
                f"## Session takeaways\n\n"
                f"<!-- Most-recent entry first; written by the ultra-agent at game end. -->\n"
            )
            seeded += 1
            continue
        try:
            shutil.copy2(baseline, writable)
            seeded += 1
        except Exception as e:  # noqa: BLE001
            log.warning("strategy-doc bootstrap: failed to seed %s: %s", writable, e)

    if seeded:
        log.info(
            "strategy-doc bootstrap: seeded=%d skipped=%d (preserved existing)",
            seeded, skipped,
        )


def read_strategy(mode: str) -> str | None:
    """Return the current persistent strategy doc for a mode, or None if absent."""
    writable = WRITABLE_DIR / f"{mode}.md"
    if writable.exists():
        try:
            return writable.read_text()
        except OSError as e:
            log.warning("could not read %s: %s", writable, e)
    baseline = BASELINE_DIR / f"{mode}.md"
    if baseline.exists():
        try:
            return baseline.read_text()
        except OSError as e:
            log.warning("could not read %s: %s", baseline, e)
    return None
