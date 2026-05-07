---
description: Run the polish-pass loop N times on an existing engine. Each pass interceptor-verifies, runs the deckbuilder, discovers the meta, tunes the AI, polishes the frontend, wet-tests, checks drift, and writes a punchlist. Pass N artifacts feed pass N+1.
argument-hint: [N=1] [--game NAME] [--polish-pilot-games 5] [--polish-num-decks 4] [--skip-stage P0,P3,...]
---

# /ng-plus — N polish passes on an existing engine

The "post-generation loop." Where `/new-game` produces a working
engine, `/ng-plus` polishes it: interceptor verification, deck
construction, meta discovery, AI tuning, frontend polish, wet
testing — repeated N times, with each pass's artifacts feeding the
next.

`/ng-plus` does **not** run `/new-game`. Use `/new-game` first to
create the engine; then `/ng-plus N` to polish.

`/ng-plus 7` = up to 7 polish passes back-to-back. Convergence-aware:
stops early when an iteration shows P0 = 100%, no plan drift > 30%,
and a clean punchlist. Once converged, more iterations are
measurement noise.

Fire-and-forget contract: never calls `AskUserQuestion`, never blocks
on user input. Same as `/new-game`. The user can interrupt at any
time.

## Arguments

User invoked with: `$ARGUMENTS`

Positional:
- `N` (default 1) — number of polish passes. Clamped to [1, 20].

Optional flags:
- `--game NAME` — engine to polish. If absent, inferred from repo
  state (see "Game inference").
- `--polish-pilot-games N` (default 5) — pilot games per `/ultra-loop`
  call.
- `--polish-num-decks N` (default 4) — decks the LLM deckbuilder
  designs in P1.
- `--skip-stage P0,...` — skip named stages this run. Valid:
  `P0`, `P1`, `P1.5`, `P2`, `P2a`, `P2b`, `P3`, `P4`, `P5`, `P5a`,
  `P5b`, `P5c`, `P5d`. Skips apply to **every** iteration; per-iter
  skips aren't supported (use a smaller N if you want to interleave).

## Pre-flight

### Argument parsing

Treat the first whitespace-delimited token of `$ARGUMENTS` as the
positional `N` if and only if it parses cleanly as an integer ≥ 1.
Otherwise N defaults to 1 and the token is treated as a flag value.
Examples:

- `/ng-plus`             → N=1, no flags
- `/ng-plus 7`           → N=7, no flags
- `/ng-plus 3 --game minecraft` → N=3, `--game minecraft`
- `/ng-plus --game minecraft`   → N=1, `--game minecraft`

If `N > 20`, clamp to 20 and warn (anything more is almost certainly
a typo and would burn 40+ hours of agent time).

### Game inference (when `--game` is omitted)

Same heuristic as `/ultra-loop`:

1. Run `git status --short` and `git log -5 --name-only`. Tally how
   many modified/recent files match `src/cards/<X>/`,
   `src/engine/<X>*.py`, `src/ai/<X>_adapter.py`,
   `frontend/src/games/<X>.tsx`, or `docs/strategy/<X>.md` for each
   candidate `<X>`.
2. If a single game has ≥3 matches AND dominates runners-up 3:1, pick it.
3. Else: list `src/cards/*/__init__.py`. If only one engine directory
   exists, use it.
4. Else: halt with "Could not infer --game. Candidates: <list>. Pass
   --game explicitly."

Print the inferred game in the discovery block.

### Engine sanity check

Confirm the engine actually exists. Required files:

- `src/cards/<game>/` directory has at least one set module
- `src/ai/<game>_adapter.py` exists
- A wet-test harness at one of (preference order):
  - `scripts/play/<game>_wet_test.py`
  - `scripts/play/<game>_play.py`
  - `scripts/play/play_<game>.py`
- A starter-deck registry: `<UPPER>_STARTER_DECKS` in
  `src/cards/<game>/__init__.py`

If any required artifact is missing, halt with:

```
=== /ng-plus: engine not ready ===
missing: <list>
==> run /new-game first to create the engine, then re-run /ng-plus.
```

### Discovery block

Print before starting:

```
═══════════════════════════════════════════════
/ng-plus pre-flight
═══════════════════════════════════════════════
game:           <game>
iterations:     <N>  (clamped: yes|no)
harness:        scripts/play/<...>.py
strategy doc:   docs/strategy/<game>.md  (exists|will create)
prior punchlist:  docs/games/<game>_polish_punchlist.md  (yes|absent)
prior drift:    docs/games/<game>_plan_drift.md  (yes|absent)
prior blocker:  docs/games/<game>_polish_blocker.md  (yes|absent — RESOLVE FIRST if yes)
skip stages:    <list or "none">
==> starting polish loop...
```

If a prior `<game>_polish_blocker.md` exists from a previous halt,
**do NOT proceed**. Halt and print:

```
=== /ng-plus: prior pass halted ===
unresolved blocker: docs/games/<game>_polish_blocker.md
==> read the file, fix the underlying issue, delete the file, then re-run /ng-plus.
```

This avoids running 7 polish passes against a known-broken engine.

## Polish loop

For `iter` in 1..N (subject to convergence auto-stop, §"Convergence"):

Print a delimiter:

```
══════════════════════════════════════════════════
ITERATION <iter> / <N>
══════════════════════════════════════════════════
```

Run all stages P0–P5 below in order. Each iteration's outputs are
saved with the iter index in their JSON log filenames
(`logs/<game>_polish_*_iter<iter>.json`). The top-level markdown
status files (`docs/games/<game>_polish_punchlist.md`,
`docs/games/<game>_plan_drift.md`) reflect *current state* and are
overwritten each iteration. After P5, run convergence check; if all
predicates pass, break early.

### P0 — Interceptor verification (LOAD-BEARING)

**Why first**: catches the depths case (interceptor wired, effect_fn
returns `[]`) before the deckbuilder and AI tuner waste hours
producing "the deck is bad" results that are really "the engine is
broken." This is the single highest-leverage stage in polish.

**Feed-forward from prior iteration / prior pass**: if
`docs/games/<game>_polish_punchlist.md` exists (from this loop's
prior iteration, or from a prior `/ng-plus` invocation), read it. The
"Zero-play cards" and "Loss-only cards" sections list cards the
previous pass flagged as broken or dead weight. Track:

- **Resolved**: a previously-failed card now passes P0. Note in this
  iter's report under "Resolved from prior iter."
- **Persistent**: a previously-failed card still fails P0. Increment
  its "iters-failed" counter. Cards that fail across multiple polish
  iterations get escalated to "Persistent dead weight" in the final
  loop report — they almost certainly need redesign rather than
  tuning.

Invoke `/test-interceptors --game <game> --set <set_code>`. Read
`.claude/commands/test-interceptors.md` and follow it.

`<set_code>` = the first set in `src/cards/<game>/`. If the engine
has multiple sets, run P0 against each (one invocation per set,
aggregate the pass rate).

**Gate**: if pass rate < 70%, halt the polish loop before P1. Write
`docs/games/<game>_polish_blocker.md` with:
- iter index that detected
- pass rate
- top failure categories (with card examples)
- suggested next step

Print:

```
=== POLISH LOOP HALTED at P0 (iter <iter>) ===
pass rate: X%  (threshold: 70%)
see: docs/games/<game>_polish_blocker.md
```

Even 70–90% should produce a "watchlist" entry in this iter's report.

### P1 — Generalized deckbuilder

Invoke `/build-decks --game <game> --num-decks <polish-num-decks>
--bias balanced --games 4`. Read `.claude/commands/build-decks.md`
and follow it.

The starters are the benchmark pool. Winners (decks that beat all
starters, or beat the field on overall winrate) get their JSON spec
saved at `logs/<game>_decks_polish_iter<iter>.json` for later
registration into `<UPPER>_STARTER_DECKS`.

After the tournament, if any new deck beat all starters, register it
as an additional starter (same procedure as before — edit the
starter-deck factory, add a one-line note to
`docs/strategy/<game>.md`).

If no new deck beat all starters, do NOT register anything — the
existing starters are already locally optimal for this iter. Note the
negative result.

**Tournament error gate** (applies to every tournament invocation in
the loop — P1, P1.5, P5a): after the tournament finishes, parse
`aggregated.totals` from the output JSON. If
`errors / games > 0.05`, **halt the polish loop** and write
`docs/games/<game>_polish_blocker.md` with:
- the error rate observed
- a sample traceback (first error's `error` field)
- which iter + stage detected it (P1 / P1.5 / P5a)
- suggested next step (likely a real engine bug — investigate the
  reported file/line, not the AI tuning).

Two recent engine bugs in the Minecraft TCG (`auto_block` bypass and
a `GameObject` in `block_map`) were each invisible to interceptor
tests (P0/P4) but produced 10.8% tournament errors at scale. This
gate catches that class of bug.

### P1.5 — Meta discovery (variant tournament)

**Why before P2**: `/ultra-loop` patches a specific bias preset.
Without knowing which preset is the format meta, the patch targets
whichever preset was passed (often a default). A brief variant
tournament identifies the meta empirically, so P2's AI tuning
compounds toward the actual strongest play.

Procedure:

1. Check the variant tournament harness:
   - `scripts/play/variant_tournament.py` exists.
   - The engine appears in its `ENGINES` registry.
   - The engine has ≥3 bias presets in `<UPPER>_BIAS_PRESETS`.

   If any of those is false, **skip** P1.5 with a logged note:
   `"<game> has no variant tournament support; P2 falls back to default preset"`.
   Continue.

2. Run:

   ```
   PYTHONPATH=. python scripts/play/variant_tournament.py \\
       --engine <game> --games 4 --max-turns 35 \\
       --out logs/<game>_polish_meta_discovery_iter<iter>.json
   ```

3. **Tournament error gate** (see P1): if errors/games > 5%, HALT.

4. Read `aggregated.ranking[0]` from the JSON. Capture as
   `<meta-preset>` for the rest of *this iteration*.

5. Print:

   ```
   === iter <iter> P1.5: meta preset discovered ===
   winner:  <meta-preset>  (<winrate>%, <wins>/<games>)
   margin vs random:  <delta>pp
   ```

6. If the margin vs `random` is < 5pp, log "Variant axes don't
   express enough strategic content; P2 may produce shallow patches."
   Continue.

### P2 — AI tuning via /ultra-loop (single + double)

Use `<meta-preset>` from P1.5 as the `--ai-bias` in both sub-stages.
If P1.5 was skipped, drop `--ai-bias` and `/ultra-loop` falls back to
its own preset discovery.

#### P2a — Single ultra loop

```
/ultra-loop --game <game> --mode single \\
    --ai-bias <meta-preset> \\
    --iterations <polish-pilot-games> \\
    --my-deck <first_starter> --ai-deck <first_starter>
```

`<first_starter>` = first key in `<UPPER>_STARTER_DECKS` (or the P1
winner if one was registered this iter).

#### P2b — Double ultra loop

```
/ultra-loop --game <game> --mode double \\
    --ai-bias <meta-preset> \\
    --iterations <polish-pilot-games> \\
    --my-deck <first_starter> --ai-deck <second_starter>
```

`<second_starter>` = a different starter; same fallback as before if
only one starter exists.

Capture per-iter outputs:
- Iteration count actually run by `/ultra-loop`
- Bias-preset weight deltas (the coach's patches)
- New strategy-doc bullets added (count and category)

#### Post-P2 watchlist

If P0 flagged any failing cards, the ultra loops should now confirm
whether those cards ever appear in real play — pilots will (or won't)
reach for them. Note any cards *neither* pilot ever plays in this
iter's report.

### P3 — Frontend polish (iter 1 only by default)

Frontend polish is a one-time visual pass; iters 2..N skip it unless
the prior iter reported visual regressions in P5b. Specifically:

- **iter 1**: run P3 always.
- **iter > 1**: skip P3 unless the prior iter's P5b browser test
  reported any uncaught console errors or layout problems. If it did,
  re-run P3 to address them.

When P3 runs, invoke the `frontend-design` skill via the Skill tool.
Brief it with:

> Polish the `<game>` game frontend at
> `frontend/src/games/<game>.tsx`. The current implementation is a
> functional MVP — readable but generic. Take a real visual-design
> pass appropriate to the engine.
>
> Constraints:
>   - Don't change game logic; visual layer only.
>   - Reuse the project's existing styling vocabulary (read sibling
>     game components in `frontend/src/games/` to see the design
>     language). Don't introduce a new design system.
>   - Read `frontend/src/games/minecraft.tsx` and one other engine
>     for the level of polish to match.
>
> After: run `cd frontend && npm run build` to confirm the build
> still passes. If it fails, fix root causes.

If `frontend-design` is not available, skip P3 with a logged note —
don't fail polish for an unavailable skill.

### P4 — Interceptor verification (re-run)

Re-invoke `/test-interceptors --game <game> --set <set_code>` to
verify nothing P1–P3 broke. The deckbuilder and AI tuner shouldn't
have changed card defs, but if P2's adapter patches inadvertently
broke a card path, this catches it.

If pass rate dropped vs P0, halt and report — something downstream
broke the engine. Write
`docs/games/<game>_polish_blocker.md` with the regression details.
If pass rate stayed flat or improved, continue.

### P5 — Wet test

Three sub-tests plus drift check. All run; report aggregates.

**P5a — AI vs AI tournament with telemetry**

```
PYTHONPATH=. python scripts/play/<game>_deck_tournament.py \\
    --decks <all_starters_inc_polished_winner> \\
    --bias <meta-preset> --games 5 --max-turns 35 \\
    --log-interceptor-fires \\
    --out logs/<game>_polish_wet_iter<iter>.json
```

Use `<meta-preset>` from P1.5 (or `balanced` if P1.5 was skipped).

If the tournament script doesn't support `--log-interceptor-fires`,
spawn a small agent to add it (read `mc_deck_tournament.py` for the
pattern). The telemetry catches cards that *never fire* in real play
— different signal from P0/P4 (which fire the trigger artificially).

**P5a-1 — Tournament error gate** (same procedure as P1/P1.5):

Parse `aggregated.totals.errors / .games`. If > 5%, **halt the polish
loop** and write `docs/games/<game>_polish_blocker.md`. By P5a, the
ultra-loop has applied AI tuning; an error rate spike here likely
means a tuning patch broke something.

**P5a-2 — Polish punchlist** (feed-forward to next iteration / next pass):

Parse the tournament JSON (and per-card telemetry from
`--log-interceptor-fires` if available) to identify:

- **Zero-play cards**: present in ≥1 deck but never entered the
  battlefield in any game.
- **Loss-only cards**: appeared in ≥3 games, controller's deck never
  won any of those games.
- **Cast-but-no-impact cards**: appeared and entered play, but never
  contributed measurable progress.

Write/overwrite `docs/games/<game>_polish_punchlist.md`:

```markdown
# <Game> Polish Punchlist — iter <iter> @ <ISO date>

## Zero-play cards (in deck, never entered play)
| Card | Decks featuring it | Iters failed | Action |
|------|-------------------|--------------|--------|
| <name> | <list>            | <count>      | Redesign or remove |

## Loss-only cards (appeared, controller always lost)
| Card | Appearances | Iters failed | Action |
|------|-------------|--------------|--------|
| <name> | <count>     | <count>      | Investigate / redesign |

## Cast-but-no-impact cards
| Card | Plays | Iters failed | Action |
|------|-------|--------------|--------|
| <name> | <count> | <count>    | Audit effect_fn or AI play priority |

## Recommendations
- ...
```

The "Iters failed" column counts how many iterations of this loop
have flagged the card. Cards that persist across all iterations in a
single loop (or across multiple `/ng-plus` invocations) are the
strongest redesign candidates.

**P5b — Browser wet test**

Use the browser automation tools (`mcp__claude-in-chrome__*`) to:

1. Start the dev server: `cd frontend && npm run dev` (background).
2. Navigate to `http://localhost:5173/<game>` (or the route
   registered in `frontend/src/games/registry.ts`).
3. Click through one full AI-vs-AI game (or human-vs-AI if the
   frontend supports it). Screenshot 3–5 key moments.
4. Read browser console
   (`mcp__claude-in-chrome__read_console_messages`) filtered for
   errors. Any uncaught exception is a wet-test failure.

Per CLAUDE.md: this is a "hard wet test" — try to break the happy
path. End turn out of order, click cards in wrong zones, see what
happens. Note any UX brittleness.

Stop the dev server when done.

If browser automation isn't available, skip P5b with a logged note.

**P5c — Smoke run-through of generated tests**

```
PYTHONPATH=. python tests/test_<game>_smoke.py
PYTHONPATH=. python tests/test_<game>_interceptors.py
```

Both should pass. Any failure is a regression.

**P5d — Plan-vs-reality drift check**

`/ultra-loop` produces deck plans at `docs/decks/<deck>_plan.md`.
Each plan has a "Target turns" section claiming a lethal turn
estimate. If a plan's estimate is wildly off the actual outcomes, the
plan misleads the next pilot — every future iteration of
`/ultra-loop` will read the wrong target.

Procedure:

1. List all `docs/decks/<deck>_plan.md` files modified in this iter
   (P2's `/ultra-loop` writes them). Skip if none.

2. For each plan, parse its "Target turns" section. Extract the
   declared lethal turn — look for the latest "T<N>" or "T<N>-<M>"
   pattern; for ranges, use the upper bound.

3. From `logs/<game>_polish_wet_iter<iter>.json` (P5a output),
   compute the median turn count for games where this deck WON:

   ```python
   wins = [o["turns"] for o in outcomes
           if o["winner_deck"] == <deck_name>]
   actual_median = statistics.median(wins) if wins else None
   ```

   If `wins` < 3, skip with a note ("insufficient data: <count> wins").

4. Compute drift: `|actual_median - predicted| / predicted`. Flag
   plans with **drift > 30%**.

5. Write/overwrite `docs/games/<game>_plan_drift.md`:

   ```markdown
   # <Game> Plan-vs-Reality Drift — iter <iter> @ <ISO date>

   | Deck | Predicted | Actual median | Drift | Action |
   |------|-----------|---------------|-------|--------|
   | <deck> | T<N>     | T<M>          | ±X%   | <Rewrite | OK> |

   ## Recommended rewrites
   For each flagged plan: file, section, suggested replacement.
   ```

P5d is observation-only — it never halts. Plans aren't auto-rewritten
here; the next iter's `/ultra-loop` reads the drift report along with
fresh game data and the coach refines plans then.

### Convergence auto-stop

After P5 finishes, evaluate three predicates:

1. **P0 pass rate this iter = 100%** (no failures).
2. **P5d drift flags = 0** (no plans with > 30% drift).
3. **Punchlist clean**: P5a-2 wrote a punchlist with 0 zero-play, 0
   loss-only, 0 no-impact entries.

If all three are true, the polish has converged — running another
iteration would be measurement noise. Print:

```
=== Polish converged at iter <iter> / <N> ===
- P0 pass rate: 100%
- Plan drift flags: 0
- Punchlist findings: 0
==> ending loop early
```

Skip remaining iterations and proceed to the final report.

If any predicate fails, print which ones (so the user can see what's
keeping the loop running):

```
=== iter <iter> / <N>: not yet converged ===
- P0 pass rate: <X>%   (target: 100)
- Plan drift flags: <count>   (target: 0)
- Punchlist findings: <Z+L+I>   (target: 0)
```

Continue to iter+1.

## Final report (aggregated across iterations)

Append a "Polish-loop summary" section to `docs/games/<game>.md`:

- **Iterations completed**: actual / requested. Note early-stop reason
  if applicable.
- **P0 progression**: pass rate per iter (table). Cards resolved
  across the loop. Cards still on the persistent-dead-weight list.
- **P1 deckbuilder progression**: new decks registered per iter.
- **P1.5 meta evolution**: did the meta preset stay the same across
  iters, or shift? A shift suggests AI tuning is moving the format,
  not just the AI.
- **P2 AI tuning**: total bias-preset deltas across iters; total
  strategy-doc bullets added; net change to `<game>_adapter.py`.
- **P3 frontend**: ran in iter 1; re-ran in iter <X> if P5b regressed.
- **P4 progression**: pass rate per iter (delta vs P0).
- **P5a tournament progression**: top decks per iter; tournament error
  rate per iter (must be ≤5% throughout).
- **P5b browser**: pass/fail per iter when run.
- **P5c smoke**: pass/fail per iter.
- **P5d plan drift**: flagged plans per iter; cumulative count of
  plans flagged at least once.
- **Outstanding TODOs**: aggregated from all iters:
  - Plans flagged by P5d in the FINAL iter (still drifting).
  - Cards on the persistent-dead-weight list.
  - Punchlist redesign candidates from the FINAL iter.

**Artifacts produced** (paths for the next `/ng-plus` invocation):

- `logs/<game>_polish_meta_discovery_iter<I>.json` — variant tournament per iter
- `logs/<game>_polish_wet_iter<I>.json` — P5a tournament per iter
- `logs/<game>_decks_polish_iter<I>.json` — deckbuilder JSON per iter
- `docs/games/<game>_polish_punchlist.md` — current punchlist (final iter)
- `docs/games/<game>_plan_drift.md` — current drift report (final iter)
- `docs/games/<game>_polish_blocker.md` — only present if a halt fired

Then a tight status message:

```
=== /ng-plus complete ===
game:        <game>
iterations:  <actual> / <requested>  (early-stop: <yes|no>)
P0 first→last:  X% → Y%  (delta: ±Zpp)
new decks:   <list of registered winners>
plan drift:  <count of plans flagged in final iter>
punchlist:   <count of unique cards flagged in final iter>
ready:       <yes if final iter converged, else "see polish report">
```

## Notes for the orchestrator

- **Skipped stages**: if `--skip-stage` is passed, drop the listed
  stages but keep the order intact for surviving stages. Skips apply
  to **every** iteration. Skipping P0 is allowed but loud — print a
  warning each iter.
- **No mid-loop commits**, same as `/new-game`. The user types
  `commit` themselves at the end. Per-iter artifacts are unstaged
  files in logs/ and docs/games/.
- **Failure handling — hard halts** (write
  `<game>_polish_blocker.md`, do not continue):
  - **P0** with pass rate < 70% in any iter (engine broken).
  - **Tournament error gate** (>5% errors) at P1, P1.5, or P5a in any iter.
  - **P4** if pass rate dropped vs that iter's P0 (P1–P3 broke a card).
  All other stages soft-fail — they log the failure and continue. P5d
  is observation-only; never halts.
- **Tooling absences are not failures**: if `frontend-design` or
  browser automation isn't set up, skip the relevant stage and log
  it. The loop keeps going.
- **Stage independence within an iter**: P0–P5 don't share state
  beyond on-disk artifacts. Individual stages are re-runnable; if P3
  fails, the user can rerun just P3 manually without redoing P0–P2.
- **Cross-iter state**: punchlist, drift report, and bias presets DO
  persist across iters. That's the entire value of running N>1 — each
  iter starts where the last left off. The "Iters failed" counter on
  punchlist entries is the cleanest signal of which cards are
  genuinely broken (multi-iter persistence) vs flaky (one-off).
- **Convergence is the success state.** Burning all N iterations
  without converging is fine but suggests the engine has structural
  issues no amount of tuning will fix — the final report's
  "Outstanding TODOs" list is then the redesign punchlist for human
  attention.
