# Minecraft Plan-vs-Reality Drift — iter 1 @ 2026-05-07 (full polish)

## Plans evaluated

`docs/decks/builder_plan.md` was modified across P2a iters 1-5 and
P2b iter 1 (refining target-turn estimates each iter). Other plans
in scope:
- `docs/decks/miner_plan.md` (created in P2b iter 1) — declared
  target turn T15-20.

## Drift table

Tournament data: `logs/minecraft_polish_wet_iter1_full.json` (50 games, passive_econ bias).

| Deck | Predicted (upper bound) | Actual median (wins) | Drift | Action |
|------|-------------------------|----------------------|-------|--------|
| builder | T25 (mirror context) | T18.0 (n=13) | 28% | **OK** (under 30% threshold) |
| miner | T20 (declared) | T16.0 (n=7) | 20% | **OK** |

## Compared to test-pass run

Test-pass iter (deck-only data) flagged builder at 34% drift. After
P2a iters 2-5 refined the builder plan with iteration logs and the
"true kill sequence" framing, declared target ranges align better
with actual win turns. Drift dropped 34% → 28%. **Auto-resolved
through coach iteration.**

## Other observations

- raider's median win turn is T11.5 — much faster than any plan
  declares. raider has no plan file; if one is written next pass,
  declare a T10-15 target.
- compleated_dominion has no plan file. Its median win is T16, range
  T9-T34. Wide spread reflects matchup variance.

## Iters-flagged counter

| Plan | Iters flagged |
|------|---------------|
| builder | 1 (test-pass only; full polish run cleared it) |
| miner | 0 |
