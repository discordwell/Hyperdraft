# Claude plays Cats — strategy notes from live games

A live game on 2026-05-20 (haiku model, seed=7, Couch Empire vs Naptime
Tyrants, LLM as p1 vs heuristic medium as p2). Game ended round 6 with hands
empty. **LLM won 24-0**, never lost a trick.

This document captures the strategic patterns Claude exhibited so future
versions of the heuristic AI can mimic them.

## Reasoning the LLM produced (verbatim)

**Round 1 — Counter-pounce (LLM is follower-who-plays-second, sees opponent's pounce first)**
> Play Magnificent Bartholomew (Value 10) to win the trick over Sergeant Snuggles
> (Value 8), place in Nap pile for +2 card draw and 2 points to establish early
> momentum.

Strategic observations:
- Identifies the value comparison (10 > 8)
- Recognizes Bartholomew's pile-entry effect (+2 card draw when entering Nap)
- Frames it as "establish early momentum"

**Round 1 — Pile choice**
> Bartholomew's draw-2 ability triggers on Nap entry, and 2pt/card is solid
> early value with room to scale (2/6 capacity).

- Cites the card's pile-specific synergy (Bartholomew + Nap)
- Cites the pile cap (6) and current fill state (2/6)

**Round 2 — Pounce**
> Mister Whiskers (7) likely wins under Sleek rule, providing peek information
> on opponent's hand; I'll claim territory to diversify from my nap lead
> before opponent establishes early advantages.

- Plans for the Sleek default rule
- Values information advantage (Mister Whiskers' peek effect)
- Notes pile diversification ("from my nap lead")

**Round 2 — Pile choice (changed mind from "territory" to "snack")**
> Snack pays 3pt/card (highest rate), capped at 5 cards total—claim into it
> early with strong cards before it fills, then build nap/territory with
> weaker cards later.

- Quotes the per-pile scoring rate (3pt > 2pt > 1pt)
- Plans pile sequencing: high-value cards into snack early (under cap), then
  spread weaker cards later

**Round 3 — Pile choice**
> Snack is highest-value target at 3pts/card (6pts total) and nearly fills
> the 5/5 limit, defensively capping opponent's greedy snacking upside.

- "Defensively capping opponent's greedy snacking upside" — recognizes that
  the snack pile is shared territory; filling your own snack pile limits
  opponent's snack-force value

**Round 4 — Counter-pounce**
> Duchess Velvet's value 6 likely wins under Sleek, and the card draw is
> critical when opponent has only 2 cards remaining.

- Tracks opponent's hand size
- Plans for the resource exhaustion phase

**Round 5 — Pile choice (after a timeout fallback for card choice)**
> Adding these 2 cards to nap scores 4 points and maxes the pile at 12/12;
> snack's 5th card only scores 1pt due to greedy penalty breaking, and
> territory is too inefficient for a weak trick.

- Computes exact pile-score deltas
- Recognizes the snack greed penalty threshold (5+ cards = 1pt/card)
- Picks the optimal pile via expected-value comparison across all 3 options

## Patterns the LLM exhibits that the heuristic AI doesn't

1. **Pile diversification over time** — early game: stuff snack (high rate
   under cap). Mid game: shift to nap. Late game: dump weak cards into
   territory. The heuristic AI always picks "highest-current-value pile"
   without sequencing.

2. **Opponent-pile-cap denial** — filling your own snack pile fast prevents
   opponent from getting easy snack-force value. The heuristic AI doesn't
   reason about denying opponent.

3. **Information-value-of-effects** — Mister Whiskers' peek effect is rated
   strategically valuable even when the +1 value differential is small.
   Heuristic AI only values raw stats.

4. **Hand-size depletion awareness** — opponent has 2 cards left → push for
   wins now because opponent will soon be drawing. Heuristic AI plays each
   round as if hands are infinite.

5. **Pile-cap edge-case math** — knowing that the snack 5th card scores
   1pt instead of 3pt is critical for pile-target choice on round 4-5.
   The heuristic AI doesn't compute the threshold.

## Where the LLM struggled

- **Timeout on round 5 card choice** — fell back to heuristic. 60s timeout
  for `claude -p` is occasionally hit when the state is dense. Could be
  mitigated by:
  - Pre-warming the model (currently every call cold-starts)
  - Reducing the state-rendering verbosity
  - Increasing timeout to 90s

- **Sneaky cards not in this demo** — Couch Empire vs Naptime Tyrants don't
  feature Sneakies, so the LLM didn't have to reason about hidden values.
  Future demo with Shadow Cats deck would expose this.

## Suggested heuristic AI improvements (Phase 14+ candidates)

1. **Pile-sequencing logic** — `_hard_choose_pile` currently picks
   highest-scoring non-full pile. Should bias toward snack EARLY (rounds
   1-3) and away from snack LATE (rounds 7-9) when the cap risks the
   greed penalty.

2. **Opponent hand size tracking** — `_hard_choose_card` should up-weight
   "win this trick now" when opponent has 1-2 cards left.

3. **Effect-driven pile preference** — if the chosen card has a pile-
   entry effect (e.g. Bartholomew's draw-on-nap), bias toward that
   pile. Currently no consideration.

4. **Pile-cap denial heuristic** — when opponent's snack pile is 3/5,
   prefer winning + dumping a snack into your snack to deny their
   approach to cap.

## Demo invocation

```bash
python scripts/play/cats_llm_demo.py --model haiku --seed 7
# Optional flags: --p1-deck "Snack Rush", --p2-deck "Shadow Cats",
# --model sonnet, --p2-difficulty hard
```

Each round burns ~30s of wall time (subprocess spawn + LLM latency). A
full 9-round game = 4-5 minutes. Quota cost: 30+ `claude -p` calls per
game.

## Files

- `src/ai/cats_llm_adapter.py` — the adapter (slot-based state rendering)
- `scripts/play/cats_llm_demo.py` — single-game demo runner
- `tests/test_cats_llm.py` — 7 unit tests with mocked provider

## Summary verdict

**"Claude is pretty good at Cats"** — verified. Haiku model beat the
heuristic medium 24-0 across 6 rounds. The strategic reasoning is
explainable in 1-2 sentence English per decision. Even with 1 round
timing out and falling back, the LLM dominated the game.

Next: integrate this strategy doc into a future heuristic-AI refresh,
or set up a Sonnet/Opus rerun where the LLM plays each deck against the
others to build a strategy matrix.
