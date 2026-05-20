# Cats Engine — 5-Phase Skills Self-Analysis

After: Phase 1 (engine + frame), Phase 2 (60-card set + engine patches), Phase 3 (4 decks + tournament), Phase 4 (polish + P0 fixes), Phase 5 (rulebook PDF).
Commits: `d90b3890`, `7cf7dee0`, `131f438b`, `13137370`, `eb55ea07`.

## Skills that worked

### `new-game` — engine + frame in 1 invocation
- **Strength**: the 4-parallel scaffold pattern produced 1361 LOC (cats_turn.py) + 580 LOC (cats_adapter.py) + 580 LOC (cats_combat.py) in ~70 minutes wall-clock.
- **Strength**: the Stage 1.5 reconciliation contract pre-identified the right drift questions (action contract, method-name contract, EventType coverage). When agents shipped, smoke test caught ZERO drift because the contracts were tight.
- **Weakness**: when 1 of 4 agents drops (Agent 1, cats.py core), there's no documented recovery path. The orchestrator (me) had to write cats.py manually with no template guidance.

### Plan agent for design doc
- Produced 11 sections of crisp design including engine-capability contract.
- Did NOT block on user input. Made every default decision deterministically.
- One downside: agent was in read-only mode so file write fell to me. Not a skill problem.

### TaskCreate tracking
- 11 tasks tracked across 5 phases. Marking in_progress / completed in the same flow as code work kept the progress visible without overhead.

## Skills that needed help

### Agent-spawning resilience
**Problem**: 1 of the 4 stage-1 agents dropped (cats.py owner) after 70 minutes of work — types.py and `__init__.py` were partially written, but the load-bearing module was never created. The agent left no diagnostic trace; my console showed only "socket closed unexpectedly."

**Suggested fix for skills**: add a "checkpoint-and-recover" sub-pattern to multi-agent skills. After each major file write, the agent should call a "checkpoint" tool that summarizes what's done. When an agent dies mid-task, the orchestrator can read the last checkpoint and either resume the same agent (via SendMessage) or pick up the work.

**For now**: I added a Phase 1 retrospective note: "Don't run Agent 1 for 70 min in parallel with the other 3 — gate on Agent 1's completion before spawning 2-4." This pattern would be worth codifying in the skill.

### Engine-card contract drift
**Problem**: the card-author agent (Phase 2) wired 44 cards with `setup_interceptors=...` expecting them to fire on pile entry. But the Phase 1 engine never called `setup_interceptors` for pile-entry. The agent flagged this in its report but didn't fix it. I patched the engine in the same phase.

**Suggested fix for skills**: when a `new-set` or `implement-mtg-cards` agent registers an interceptor, it should also write a tiny integration test that proves the interceptor fires. We have a `test-interceptors` skill that does this for an entire set; running it per-archetype-file during set generation would catch wired-but-dead cards immediately.

### Frontend wet-test in agent context
**Problem**: the Phase 4 agent tried to wet-test the cats frontend via chrome browser automation but couldn't because the cats.tsx component isn't mounted on a route (it only loads via the deckbuilder). The agent surfaced this as P1 but couldn't actually visually verify the page.

**Suggested fix for skills**: the `new-game` skill's Stage 2 (frontend frame) should ALSO add a minimal route mount in App.tsx so the page is visually verifiable. Even mock-data-backed, a route at `/cats-preview` would let wet-tests happen.

## New patterns worth codifying

### Lightweight in-process interceptor dispatcher
The engine pipeline is heavy. For a brand-new engine, a 30-LOC `_dispatch_interceptors(state, event, priorities)` that walks `state.interceptors.values()` and routes TRANSFORM/REACT/REPLACE is enough to bootstrap. This is what cats.py uses, and it covers TRINKET score-mods, MOOD rule-overrides, and on-win triggers without dragging in the full pipeline.

**Suggested fix**: add a `lightweight_dispatcher.py` helper module under `src/engine/` and document the pattern in the engine-author guide.

### Buff-not-nerf balance cycle
Phase 3 deliberately exercised the buff-weak-don't-nerf-strong principle from `feedback_deck_design_pinnacles.md`. When Snack Rush dropped to 30%, the fix was to bomb-upgrade it — which cascaded into Shadow Cats over-correcting. Final balance took 3 iterations.

**Pattern**: when buffing a weak deck cascades, the next iteration should buff the SECOND-weakest, not the now-weak ex-strong one. The "buff don't nerf" rule needs a "and buff the most-deserving, which is whoever's currently lowest" sub-rule.

### Real-card examples in rulebook
The Phase 5 rulebook agent cited actual first-set card names + verbatim text from `commanders.py`/`moods.py`/etc. This made the rulebook feel concrete rather than abstract.

**Pattern for rulebook skill**: always pull card examples from the shipped set, not from the design doc's invented placeholder names. A rulebook that cites cards the player will actually draw is dramatically better than one that cites design-doc fiction.

## Skills updates I'd make (if running this skill again)

1. **`new-game` Stage 1**: Run Agent 1 (engine core) FIRST, then fan out Agents 2-4 once it's shipped. The dependency direction (combat/turn/AI depend on the engine core) makes the 4-parallel pattern wrong.
2. **`new-game` Stage 2**: Add `App.tsx` route mounting to the frontend agent's scope so the page is wet-testable without manual wiring.
3. **`new-set` mid-pipeline**: Run per-archetype test-interceptors after each file lands, not just at the end.
4. **`ng-plus`**: Verbose-mode in tournament infrastructure should be the default in polish passes (caught silent-trigger regressions in 30 seconds).
5. **Add a `rulebook` template**: the cats rulebook build script (`docs/templates/cats_rulebook_build.py`) is a reusable pandoc-free PDF pipeline. Worth lifting into a skill.

## Engine-wide gaps the 5 phases surfaced

These are in the punchlist (`docs/games/cats_punchlist.md`) — the 2 P0s are resolved:
- **P0 (resolved)** trick-resolve REACT routing
- **P0 (resolved)** DRAW/LOOK_AT_HAND processing
- **P1** pile-activated abilities (`make_pile_activated` missing)
- **P1** Trinket attach mechanic (`state.cats_pile_trinkets` is written-by-nobody)
- **P1** Sneaky reveal mechanic (Gary commander emits Pokemon engine event)
- **P1** `/cats` route on frontend
- **P2** Mood-vs-Mood stacking, 3-player support, untap path, AI activation EV

## Counts

- 6 commits
- 13 net new files (engine + cards + tests + docs)
- 24 cats-specific tests passing
- 60 cards across 8 archetype files
- 4 archetype decks balanced + tournament infrastructure
- 17-page rulebook PDF
- 1 punchlist file
- 3 retrospectives

## Next 5 phases (proposed)

- Phase 6: implement P1 punchlist items (pile-activated, Trinket attach, Sneaky reveal)
- Phase 7: re-balance the meta after the P0 fix shifted Shadow Cats to 76.7%
- Phase 8: wire the `/cats` frontend route + a minimal backend integration
- Phase 9: expand the set with a second archetype file (snacks variant or sneaky-themed)
- Phase 10: 2nd self-analysis pass
