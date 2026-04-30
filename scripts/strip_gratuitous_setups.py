"""Strip `setup_interceptors=foo_setup` from cards classified as
`strip_activated` in the worksheet.

These cards have only activated abilities — the engine handles activation
through the cast pipeline, not setup_interceptors. The bare-`return []`
setup function adds nothing and misleads readers into thinking the card
has a wired effect.

We DON'T delete the function definition itself — it's harmless dead code
and removing it would inflate the diff. The unreferenced `def foo_setup`
will be picked up by future cleanup if anyone cares.
"""
from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
WORKSHEET = ROOT / "noop_cleanup_worksheet.json"


def strip_setup_line(file_lines: list[str], card_lineno: int, card_end_lineno: int,
                     fn_name: str) -> bool:
    """Look in [card_lineno, card_end_lineno] for the `setup_interceptors=fn_name,`
    line and remove it. Return True if removed.
    """
    target = f"setup_interceptors={fn_name},"
    target_no_comma = f"setup_interceptors={fn_name}"
    for i in range(card_lineno - 1, card_end_lineno):
        if i >= len(file_lines):
            break
        line = file_lines[i]
        # The line should be roughly: "    setup_interceptors=fn_name,"
        if target in line or target_no_comma in line.strip():
            # Sanity: confirm it's just this kwarg, not part of something else
            stripped = line.strip()
            if stripped.startswith("setup_interceptors=") and (
                stripped == target or stripped == target_no_comma
            ):
                del file_lines[i]
                return True
    return False


def main() -> None:
    rows = json.loads(WORKSHEET.read_text())
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["disposition"] == "strip_activated":
            by_file[r["set"]].append(r)

    total_stripped = 0
    skipped: list[str] = []
    for fname, cards in by_file.items():
        path = CARDS_DIR / fname
        lines = path.read_text().split("\n")
        # Sort by card_lineno DESCENDING so earlier-line indices stay valid
        # after deletions further down the file.
        cards.sort(key=lambda r: r["card_lineno"], reverse=True)
        stripped_in_file = 0
        for r in cards:
            if strip_setup_line(lines, r["card_lineno"], r["card_end_lineno"], r["fn"]):
                stripped_in_file += 1
            else:
                skipped.append(f"{fname}::{r['fn']} on card {r['card_var']} L{r['card_lineno']}")
        path.write_text("\n".join(lines))
        total_stripped += stripped_in_file
        print(f"{fname:<35} stripped {stripped_in_file}/{len(cards)}")

    print(f"\nTotal stripped: {total_stripped}")
    if skipped:
        print(f"\nSkipped ({len(skipped)}):")
        for s in skipped[:10]:
            print(f"  {s}")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more")


if __name__ == "__main__":
    main()
