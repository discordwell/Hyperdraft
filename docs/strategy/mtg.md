# Magic: The Gathering — Strategy Doc

This file is the persistent strategic memory for the MTG engine in
Hyperdraft (twelve real Standard-era sets plus the custom-MTG family).
A fresh Claude instance piloting the format reads this BEFORE every
game and consults it during play. Update it whenever a game reveals
a non-obvious truth — write down WHAT and WHY, not just WHAT.

The doc is paired with `src/ai/mtg_adapter.py` and the per-deck heuristic
profiles — when you find a blind spot in the heuristic AI, patch both
this doc (so the LLM pilot remembers) AND the adapter (so the heuristic
gets it too).

## How to update this file at end of game

Append a `## Session takeaway — <UTC date>` section at the bottom with:
- **Deck I piloted**: archetype + key spells
- **Opponent deck**: archetype + key threats
- **Result**: win/loss + turn
- **One thing I'd do differently next time**: concrete, mechanical
- **One thing the engine got wrong** (if any): tag with `gap:` for the
  punchlist

Don't rewrite the playbook below — that's the consolidated wisdom across
many games. Only the head of the file gets edited when a takeaway
graduates from "anecdote" to "established principle".

## Format-wide principles

(Empty until the first wave of LLM-piloted matches accumulates evidence.)

## Per-archetype playbook

(Empty until per-archetype experience accumulates.)

## Known engine gaps to work around

(Empty.)

---

## Session takeaways

<!-- Most-recent entry first. -->
