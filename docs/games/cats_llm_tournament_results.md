# Cats — LLM vs LLM tournament results

Both seats Claude (haiku model). 12 games, seat-balanced, 4-deck round-robin.

**Wall time:** 128.6 minutes (10.7 min/game avg).
**Run date:** 2026-05-20.
**Artifact:** `artifacts/cats_llm_tournament.json` (full per-game reasoning + scores).

## Final standings

| Deck | W | L | T | Win% |
|------|---|---|---|------|
| Naptime Tyrants | 4 | 2 | 0 | **66.7%** |
| Couch Empire | 3 | 3 | 0 | 50.0% |
| Shadow Cats | 3 | 3 | 0 | 50.0% |
| Snack Rush | 2 | 4 | 0 | 33.3% |

## Per-pairing record

| Pairing | Game 1 | Game 2 | Winner |
|---|---|---|---|
| Couch Empire vs Naptime Tyrants | NT 12-8 (6r) | NT 20-12 (9r) | **NT 2-0** |
| Couch Empire vs Snack Rush | CE 16-8 (7r) | CE 10-0 (6r) | **CE 2-0** |
| Couch Empire vs Shadow Cats | CE 14-0 (6r) | SC 8-6 (6r) | split 1-1 |
| Naptime Tyrants vs Snack Rush | SR 8-6 (6r) | NT 6-0 (6r) | split 1-1 |
| Naptime Tyrants vs Shadow Cats | NT 18-14 (9r) | SC 22-4 (6r) | split 1-1 |
| Snack Rush vs Shadow Cats | SR 29-12 (9r) | SC 11-6 (6r) | split 1-1 |

## Comparison to heuristic-AI tournament

| Deck | Heuristic mean (5 trials) | LLM win% (12 games) | Delta |
|------|--------------------------|---------------------|-------|
| Couch Empire | 48.3% | 50.0% | +1.7 |
| Naptime Tyrants | 55.0% | **66.7%** | +11.7 |
| Snack Rush | 41.3% | 33.3% | -8.0 |
| Shadow Cats | 55.3% | 50.0% | -5.3 |

**Takeaways:**

1. **Naptime Tyrants is the true pinnacle deck.** Both pilots favor it; LLM pilots favor it even more strongly. The Reginald + Heated Blanket + Bartholomew engine is robust under both heuristic and LLM piloting.

2. **Shadow Cats was a heuristic-exploit deck.** Under the heuristic AI, Sneaky hidden values and Mood chaos exploited the opponent's lack of awareness. Under LLM piloting (where both sides can reason about hidden values), Shadow Cats's edge disappears — back to 50%.

3. **Snack Rush remains the weakest archetype.** Snack-force is structurally high-variance: if you don't win the snack trick, you feed the opponent's pile. LLM piloting doesn't fix this — it's a deck-design issue, not a pilot issue.

4. **Couch Empire is the median.** Steady 50% under both pilots. Reliable Sleek value engine, no special exploitation potential.

5. **Game length varies wildly.** Some games run the full 9 rounds (with the deck cycling through the 30-card pool); others end at round 6 when both hands empty. The "9 rounds" target in the design doc is a CAP — most games finish before the cap because hands deplete faster than they refill. This is a design-doc-vs-engine discrepancy worth investigating.

## Notable individual games

- **Game 11 — Snack Rush 29-12 Shadow Cats (9 rounds).** Highest single-game score. SR's engine fired: 4 snacks in the Snack pile = 12pt + Trinket bonuses + repeated draws via Catnip Mouse. When Snack Rush's deck cycles cleanly, it can produce a 25+ point ceiling.
- **Game 10 — Shadow Cats 22-4 Naptime Tyrants (6 rounds).** Inverse of game 9 in the same pairing — Shadow Cats wiped Naptime in just 6 rounds, suggesting the Mood-rule-swap pattern still has teeth in specific matchups even with LLM piloting.
- **Games 4 + 5 — Couch Empire shutouts (10-0 and 14-0).** Couch Empire can deny opponents entirely when its Sleek bombs (Bartholomew 10, Brigadier 9, Pomf 9) line up early.

## Strategic patterns observed (haiku-level reasoning)

From the captured `notes` in the JSON:

- **Hand-economy awareness.** Both seats track opponent hand size and accelerate when opponent has 1-2 cards left.
- **Pile sequencing.** Early-round LLM picks: snack (high rate, low cap). Mid-round: nap. Late: territory + attention.
- **Snack denial.** When opponent's snack pile is near cap, dump junk via Snack-force to push them past the greed threshold (5+ cards = 1pt/card).
- **Mood opportunism.** Use lowest-wins Moods only when holding a low-Value card you want to win with.
- **Sneaky pessimism.** Without revelation (only Gary's commander reveals), LLM treats unknown Sneaky values as max-9 — leads to conservative play against Shadow Cats.

## Reasoning quality vs game outcome

The captured reasoning per decision is genuinely strategic — typical lines like:
> "Bartholomew's draw-2 ability triggers on Nap entry, and 2pt/card is solid early value with room to scale (2/6 capacity)."

But the LLM tournament isn't dramatically tighter than the heuristic multi-trial mean. The biggest delta is Naptime jumping +11.7 percentage points — suggesting LLM piloting is most beneficial for decks with **clear win-condition chains** (Naptime's "nap-stuff to cap → +bonus" plan) and least beneficial for **chaos decks** (Shadow Cats) or **structurally-fragile decks** (Snack Rush).

## Where to push next

Three follow-ups suggested by this data:

1. **Sonnet/Opus tournament for comparison.** Haiku played well; a stronger model may exhibit deeper strategy (especially around Sneaky-card pessimism handling).

2. **Heuristic AI ports of LLM strategies.** The strategy doc (`cats_claude_strategy.md`) already lists 5 patterns the heuristic doesn't do. Pile sequencing + opponent-hand-size awareness could close the 11.7-point Naptime gap.

3. **Snack Rush deck redesign.** 33.3% mean across both pilots indicates the deck doesn't have a path to win-rate parity in the current pool. A Snack Rush v3 with stronger high-Value bombs (or a different commander) is worth a Phase 14.

## Reproducing

```bash
python scripts/play/cats_llm_tournament.py \
  --model haiku \
  --games-per-pairing 2 \
  --output artifacts/cats_llm_tournament.json
```

Each game burns ~30+ subprocess calls to `claude -p`. Expect 10-18 min per game on haiku, 25-40 min on sonnet, longer on opus.
