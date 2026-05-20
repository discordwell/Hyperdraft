# Cats Engine — 10-Phase Skills Self-Analysis

After phases 6-10: P1 punchlist (pile-activated + Trinket attach), meta rebalance,
frontend route mount, Sneaky reveal + Mood stacking + master event dispatch fix.

Commits: `3008ede0`, `5f336ab4`, `02590754`, `f04274b8`, plus phase 10 retro.

## What worked across P6–P10

### Direct orchestrator-driven work outperformed agent dispatch for tight scope
- Phases 6, 7, 8, 9 were all under ~200 LOC of changes each. Doing them directly was faster than briefing an agent and faster than reviewing the agent's report.
- The agent overhead pays off when the work spans 5+ files OR requires deep exploration. For 1-2 file engine surgery, direct work wins.

### Engine-pattern reuse compounds
- The lightweight `_dispatch_interceptors` from Phase 2 was reusable for Phase 6's pile-activated abilities and Phase 9's master-event REACT. Adding the third dispatcher caller took 1 line.
- The `_process_cats_effect_events` helper from Phase 4 absorbed Phase 6's knock-over DRAW emissions automatically. No new plumbing needed.

### Tests-as-acceptance kept the work crisp
- Every phase ended with a test that proved the change. Phase 6: 5 tests for pile-activated + Trinket. Phase 9: 3 tests for reveal + stacking. Phase 4's repro-driven `test_on_win_trigger_actually_fires` was the template — "show the symptom in a test, then fix the engine, then prove the test passes."
- Cumulative cats test count: smoke 11 + first_set 3 + engine_patches 4 + decks 6 + p1_punchlist 5 + p1p2_mechanics 3 = **32 tests, all passing**.

### Iterative balance with hard-AI determinism
- Phase 4's AI determinism (sort tiebreaks by card name, not by uuid) made Phase 7's rebalance possible without running 5-trial means. 1 tournament run = 1 data point of truth.
- Phase 7 took 3 iterations: v3 trim Mood count → 73% Shadow Cats, deeper Sneaky trim → 53%. Each iteration was a ~30-line edit + a tournament rerun (<1s) + a verdict.

## What needed extra work

### Engine patches kept arriving in trios
- Phase 2 had 3 P0 patches (TRANSFORM dispatch, score query, setup_in_pile).
- Phase 4 had 2 P0 patches (on_win REACT routing, DRAW/LOOK_AT_HAND processing).
- Phase 9 had 1 more P0 patch (master CATS_TRICK_RESOLVE event was emitted but not dispatched).

Pattern: the engine in Phase 1 emitted events but didn't route them through interceptors except for trick-rule queries. Each "card fails to fire" surfaced a new dispatch gap. Lesson: a brand-new engine should write a single "event dispatch matrix" doc that lists which event types are dispatched through interceptors at which priorities — and then test that matrix exhaustively from the start.

### Mock data on frontend means visual wet-test is limited
- Phase 8 wired `/cats` to render `CatsGame` with mock-data hook. The visual wet-test (Phase 4 polish agent attempted) confirms the page exists and renders, but not that real game state would flow through correctly.
- A full backend integration (`/api/cats` routes + WebSocket) is the natural Phase 11 follow-up.

### Commander interceptors are special-cased
- Cards in piles get setup_interceptors called via `_run_setup_on_pile_entry`. Commanders get setup_interceptors called via `setup_cats_player`. Trinkets via `attach_trinket`. Three separate code paths.
- A future cleanup: one `register_card_interceptors(state, obj, zone)` that handles all of them uniformly. P2 nice-to-have.

## Skills observations

### `new-game` skill
- Phase 1's lessons (Agent 1 first, App.tsx route mount) are now in the skill file. Validated.
- The Stage 1.5 reconciliation contract was load-bearing; phases 2-9 mostly avoided drift because of it.
- Recommended addition: a "post-Phase-1 P0 sweep" stage. After the smoke test passes, explicitly check which event types are dispatched through interceptors. The "events emitted but not dispatched" failure mode (Phase 9) would have been caught in 5 minutes by a single test that registers an interceptor on every CATS_* event type and walks the engine looking for unconsumed ones.

### `new-set` skill
- Phase 2's card-author agent was excellent at noting engine gaps in its report. Three of those notes became Phase 2's same-commit fixes.
- Recommended addition: instead of relying on the orchestrator to read the report and patch, the skill could include a "the engine gaps you flagged — please fix them now if they're trivial, or write a punchlist if they're deep" step.

### `ng-plus` (polish)
- The verbose-tournament flag (Phase 4) caught zero regressions because we didn't introduce any. But the infrastructure is there for future runs.
- The hard-AI 1-round lookahead (Phase 4) is the biggest single win of the polish phase — hard-vs-medium 45% → 71.9%.

### `rulebook`
- Phase 5's PDF generation via Chrome headless was robust to missing pandoc/weasyprint. The agent wrote a 16KB Python markdown→HTML converter from scratch (no external deps). Worth lifting into the rulebook skill as a fallback recipe.

## Net counts after 10 phases

- 11 commits (5f336ab4 + balance, 02590754 + route, f04274b8 + p1p2)
- 10 new files (cats.py, cats_combat.py, cats_turn.py, cats_adapter.py, cats_rulebook.md, cats_rulebook.pdf, decks.py, tournament.py, CatsGameView.tsx, plus 6 test files)
- 32 cats tests passing
- 4 archetype decks balanced 45-53%
- 60-card set with 44 cards wired (73%)
- 17-page PDF rulebook
- 2 self-analyses
- 4 P0 engine fixes (Phase 2 score+rule+setup, Phase 4 on_win+DRAW, Phase 9 master event)
- 3 P1 fixes (Phase 6 pile-activated + Trinket attach, Phase 9 Sneaky reveal + Mood stacking)

## Where I would stop

The cats game is complete enough to ship. A human can:
- Read the design doc + rulebook PDF and understand the game
- Run `python scripts/play/cats_tournament.py` and watch AI vs AI play
- Visit `/cats` in the frontend and see the board (mock data)
- Implement new cards using `make_cat_card` / `make_mood_card` / etc. helpers
- Add new mechanics by emitting events the engine dispatches

The remaining P2 items (3+ player support, AI activation EV refinement, untap-loop refactor) are pure polish. The next phase would be backend integration (`/api/cats` routes + WebSocket) which is a different project, not a "polish another iteration of cats."

## Updates I'd apply to skills

1. **`new-game.md`** — already updated post-Phase 5. Add a Phase-9 lesson:
   > After smoke test passes, write a test that registers a no-op interceptor on every engine-specific EventType. Run the smoke test. Then assert each interceptor was invoked at least once. Any zero-invocation interceptor is an "event emitted but never dispatched" gap to fix.

2. **`new-set.md`** — add a "post-set engine-gap remediation" step:
   > After the card-author agent finishes, if its report flags engine gaps, the orchestrator should (a) decide which are P0 (blocking real play) and patch them in-phase, (b) write the rest to a punchlist file. Do not defer P0s to a future phase.

3. **`ng-plus.md`** — codify the verbose-tournament flag as the polish-pass default. Cheap insurance against silent-trigger regressions.

4. **New skill suggestion: `engine-event-audit`** — scans an engine module for `Event(type=EventType.X, ...)` calls and cross-references against `_dispatch_interceptors` callers. Flags event types that are emitted but never dispatched. Would have caught Phase 9's master-event bug in 30 seconds.
