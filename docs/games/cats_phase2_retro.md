# Phase 2 + Phase 3 Retrospective — First set + tournament

## Phase 2 — 60-card CATS set + engine patches

**Scope:** Generate first card set (60 cards across 8 files) + patch the 3 engine gaps that prevented interceptors from firing.
**Outcome:** 44/60 cards wired (73%), 14/14 tests pass. Engine now dispatches CATS_QUERY_PILE_SCORE and CATS_TRICK_RULE_QUERY via a lightweight in-process dispatcher; setup_interceptors runs on pile entry.
**Commit:** `7cf7dee0`

### What went well
1. **Single-agent execution for the first set was faster than parallel scaffolding.** 60 cards landed in 1 agent-hour with consistent naming + style across 8 files. Parallel would have produced 8 different voices.
2. **Set author flagged 3 real engine gaps proactively.** Card author didn't try to fake the effects — listed engine-shape gaps in the report. That made the patches surgical (~50 LOC in cats.py).
3. **The 3 engine-patch tests cover the exact mechanism each patch enables.** Phase 1 smoke didn't test interceptors firing; Phase 2 tests do. Will keep Phase 3+ honest about engine drift.

### What went wrong
1. **The card-author agent skipped some effects-that-needed-engine-support** rather than asking for the hook. Of the 16 "vanilla" cards, ~4 wanted a "draw" or "peek" event the engine doesn't have. These are tracked silently — no TODO file emerged. Future skill: require agents to write engine-gap TODOs to a known file.
2. **The agent used `setup_interceptors` to register effects even though Phase 1 engine didn't call it on pile entry.** The cards looked wired but weren't firing. Caught by the agent's own report ("works under TurnManager but not the smoke driver") — so not a blocker, but a sign the engine→cards contract needs tightening.

## Phase 3 — 4 archetype decks + tournament

**Scope:** Design 4 mechanically distinct decks, run round-robin, balance until all decks are in 35-60% range.
**Outcome:** 6/6 deck tests pass, tournament runs in <1s, balance verified across 5 trials (mean win rates 42.7-57.3%).
**Commit:** TBD (this commit).

### What went well
1. **Iterative buff-not-nerf strategy worked.** First tournament had Snack Rush at 30%. Buffing it with bombs → too strong (60%). Compensating buff to Shadow Cats → over-corrected (66.7%). Final: trim Shadow Cats bombs, add Hair Tie to losers → all 4 in range. The "buff weak, don't nerf strong" principle from [[feedback_deck_design_pinnacles]] held even when buffing one deck cascaded.
2. **Tournament is fast (~0.4s for 60 games).** Means we can do balance loops without burning wall-clock. Future phases can run 100-game tournaments per balance pass cheaply.
3. **Deck composition is genuinely mechanically distinct.** Snack Rush has 11 snacks (vs 0 in Shadow Cats); Shadow Cats has 8 moods (vs 3 in Couch Empire). Each commander reinforces the archetype.

### What went wrong
1. **`new_id()` uses uuid4 — non-deterministic.** Even with `rng_seed` set, card IDs vary, so AI tie-breakers via sorted-by-id produce ±10% variance run-to-run. Not a blocker, just means single tournaments aren't authoritative; need multi-trial means.
2. **Hard AI tiebreak isn't strategy-aware.** Currently sorts card IDs alphabetically. A real "hard AI" would weight by trick-win probability + pile-cap pressure. Won't matter until decks get tighter than the current 15% spread.

## Cross-phase observations

- **The engine's interceptor-dispatch is minimal but works.** A 30-line `_dispatch_interceptors` covers TRANSFORM/REACT/REPLACE for the events I care about. Full pipeline integration can wait until either (a) the cats TurnManager wires through `pipeline.dispatch_event` or (b) we hit a scenario where the in-process dispatcher is insufficient.
- **The "real game" definition is now met.** 60 cards, 4 decks, 4 commanders, AI vs AI plays a balanced tournament under 1 second. That's a complete game. The remaining phases (rulebook, polish, frontend wet test) are quality-of-life.

## Next phases
- Phase 4: ng-plus polish loop (scaled to this small set — focus on AI tuning + frontend wet test)
- Phase 5: rulebook PDF generation
- Then: self-analysis pass on skills
