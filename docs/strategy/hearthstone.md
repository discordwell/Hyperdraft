# Hearthstone — Strategy Doc

Persistent strategic memory for the Hearthstone engine + Riftclash /
Stormrift / Frierenrift variants. A fresh Claude instance piloting HS
reads this BEFORE every game.

The doc is paired with `src/ai/hearthstone_adapter.py` and per-class
heuristic biases — when an LLM-piloted match reveals a blind spot,
patch BOTH this doc and the adapter so the lesson persists in the
heuristic too.

## How to update this file at end of game

Append a `## Session takeaway — <UTC date>` section at the bottom:
- **Class + variant**: e.g. "Pyromancer · Riftclash"
- **Opponent**: class + opening curve
- **Result**: win/loss + turn
- **One mechanical lesson** for next time
- **One engine gap** (if any), tagged `gap:` for the punchlist

## Format principles

(Empty until evidence accumulates.)

## Per-variant + per-class playbook

(Empty.)

## Known engine gaps

(Empty.)

---

## Session takeaways

<!-- Most-recent entry first. -->
