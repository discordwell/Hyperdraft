# Yu-Gi-Oh! — Strategy Doc

Persistent strategic memory for the YGO engine in Hyperdraft (Goat
Control era + Dragon Beatdown + classic archetypes). A fresh Claude
instance piloting the format reads this BEFORE every game and consults
it during play.

The doc is paired with `src/ai/yugioh_adapter.py` and the per-deck
heuristic profiles. When an LLM-piloted match reveals a blind spot,
patch BOTH this doc and the adapter.

## How to update this file at end of game

Append a `## Session takeaway — <UTC date>` section at the bottom:
- **Deck I piloted**
- **Opponent deck**
- **Result**: win/loss + LP at end
- **One mechanical lesson** — phases, chain links, set-trap timing
- **One engine gap** if any, tagged `gap:`

## Format principles

(Empty until evidence accumulates.)

## Per-archetype playbook

(Empty.)

## Known engine gaps

(Empty.)

---

## Session takeaways

<!-- Most-recent entry first. -->
