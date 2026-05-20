# Phase 1 Retrospective — Cats engine scaffold

**Phase scope:** Design doc + engine scaffold (4 modules) + reconciliation + frontend frame + smoke tests.
**Outcome:** 11/11 smoke tests pass. Engine + AI + frontend integrate cleanly. Commit `d90b3890`.

## What went well
1. **Plan agent → design doc**: produced 11-section design with concrete win condition, explicit engine-capability contract, and worked example. Set up the parallel scaffold agents to succeed because they had a single shared source of truth.
2. **Parallel scaffold (3 of 4 succeeded)**: cats_combat, cats_turn, cats_adapter each shipped ~580–1361 LOC with internal smoke-test validation. Their inter-module dependency was managed via defensive try/except imports.
3. **Smoke test catches drift fast**: 11 targeted assertions covering full-game flow, scoring edge cases, AI return-type discipline, and tiebreaker. Ran in 0.4s.
4. **Frontend agent picked up the irreverent voice naturally**: cream/butterscotch palette, "knocked over" instead of "tapped", "cards in paw" instead of "hand size". Build clean.

## What went wrong
1. **Agent 1 (cats.py core) socket-closed after 4206s** — the most critical of the 4 parallel agents dropped right before writing the actual file. types.py and __init__.py were saved; cats.py was not. Orchestrator (me) had to write it directly.
2. **3 type-signature mismatches in my manual cats.py**:
   - `ZoneType.COMMAND_ZONE` doesn't exist (it's `ZoneType.COMMAND`)
   - `Characteristics(name=...)` — Characteristics has no name field
   - `empty_library_loses_game()` — wrong hook name (real one is `handle_empty_library_draw`)
   Each one only surfaced when I ran the full import check. The 4-line type-check command found all of them in seconds, but only after I wrote the bugs in.
3. **Circular import**: `cats.py → mode_adapter.py → cats.py` for the adapter class. Fixed by mimicking the depths pattern (lazy builder function). Took 2 minutes to diagnose because the registry imports happen at module load.

## What I'd do differently
1. **Don't keep Agent 1 running 70min in parallel with the others.** When the most complex module is owned by one agent and the other 3 depend on it, run Agent 1 first, then fan out 2–4 once Agent 1 has shipped. The "4 parallel" template is wrong for this shape of work.
2. **Validate Characteristics field set up-front.** A 5-line `python -c "from ...types import Characteristics; print(Characteristics.__init__.__doc__)"` would have caught the `name=` mistake before I made it in 5 helper functions.
3. **Run a tiny "type-check probe" between scaffolding and smoke test.** A bare `python -c "from src.engine.cats import *; print('ok')"` against each invariant (zone enum, attribute names) would catch drift before the smoke test layer.

## Skills observations (early notes for the 5-phase self-analysis)
- **new-game skill spec was good**: "fire-and-forget, never block" was honored even when Agent 1 dropped — I picked up the failed shard and continued.
- **The Stage 1.5 reconciliation contract was load-bearing**: identified and queued the right drift questions (action contract, method-name contract, combat-manager init, EventType coverage). Should make this explicit in skill docs.
- **Parallel-agent failure recovery is missing from new-game**: when 1 of 4 agents drops, the orchestrator is on its own. Worth adding a small "if any agent dropped, here's the recovery template" section.

## Files added (Phase 1)
13 files, 6163 insertions. See commit `d90b3890`.

## Next phase
Phase 2: test-interceptors. First set doesn't exist yet, so this will run against the cards we'll generate. Defer until after first-set generation.

**Adjusted plan:** Skip Phase 2 in original order. Run Phase 3 (build-decks) next to seed a card pool, then Phase 2 against those cards, then continue.

Actually — both Phase 2 and Phase 3 need cards to exist. The new-game pipeline's Stage 3-9 was supposed to delegate to /new-set, which generates the first set. Run /new-set first as Phase 2 (replacing the original Phase 2 task).
