---
description: /new-game followed by an extensive polish pass — interceptor verification, deckbuilder pass, AI tuning, frontend polish, and wet testing. Fire-and-forget. Use this instead of /new-game when you want a tournament-ready engine, not just a working one.
argument-hint: <theme> [--engine NAME] [--code XXXX] [--cards 150] [--max-cycles 10] [--polish-pilot-games 5] [--skip-stage P0,P3,...]
---

# /new-game-plus — /new-game + polish pass

`/new-game` produces a working engine. `/new-game-plus` produces a
polished one — interceptors verified, decks designed beyond the
hand-rolled starters, AI tuned via pilot games, frontend visually
polished, and wet-tested in a real browser before declaring done.

The polish pass adds ~2–4 hours after `/new-game`'s 4–12. Total
runtime: 6–16h, fully unattended. Same fire-and-forget contract — never
calls `AskUserQuestion`, never blocks on user input.

## Arguments

User invoked with: `$ARGUMENTS`

Required:
- `theme` — same as `/new-game`. Free-form.

Forwarded to `/new-game`:
- `--engine NAME`, `--code XXXX`, `--cards N`, `--max-cycles N`,
  `--games-per-pairing N`.

Polish-pass-specific:
- `--polish-pilot-games N` (default 5) — number of AI-vs-AI games to
  run during the AI tuning stage (P2).
- `--polish-num-decks N` (default 4) — decks the LLM deckbuilder
  designs in P1.
- `--skip-stage P0,P1,...` — skip named polish stages. Valid values:
  `P0`, `P1`, `P1.5`, `P2`, `P2a`, `P2b`, `P3`, `P4`, `P5`, `P5a`,
  `P5b`, `P5c`, `P5d`. Use sparingly; the order is intentional
  (front-loaded QA catches engine breakage before downstream tuning
  runs on a bad foundation; punchlist + drift checks at the end feed
  the next pass).

## Stage 0 — Run /new-game

Read `.claude/commands/new-game.md` and execute every stage exactly as
written, forwarding all `/new-game`-relevant flags. Do not modify
`/new-game`'s pre-flight, stage list, or final report. When `/new-game`
finishes (its stage 9), capture:

- `<engine>` — the engine name picked at pre-flight
- `<set_code>` — the first set code
- `<theme>` — passed through

Print:

```
=== /new-game-plus: /new-game complete ===
engine:    <engine>
first set: <set_code>
==> starting polish pass...
```

Then create polish-pass tasks via `TaskCreate` (one per stage) and
proceed.

## Polish pass

Stages run in order. Each produces concrete artifacts; the final
report aggregates.

### P0 — Interceptor verification (LOAD-BEARING)

**Why first**: catches the depths case (interceptor wired, effect_fn
returns `[]`) before the deckbuilder and AI tuner waste hours
producing "the deck is bad" results that are really "the engine is
broken." This is the single highest-leverage stage in polish.

**Pre-flight (feed-forward from prior polish passes)**: if
`docs/games/<engine>_polish_punchlist.md` exists from a prior polish
pass, read it. The "Zero-play cards" and "Loss-only cards" sections
list cards the previous pass flagged as broken or dead weight. Any
card mentioned there gets added to a watchlist for THIS run:

- If P0's interceptor test now passes that card cleanly → note in
  the final report under "Resolved from prior polish": the card
  was redesigned between passes.
- If P0 still fails the card → it's a known issue; flag in the final
  report under "Persistent dead weight" with iteration count
  (track how many polish passes have failed to fix it).

This avoids rediscovering the same dead-weight cards cold in every
pass.

Invoke `/test-interceptors --game <engine> --set <set_code>`. Read
`.claude/commands/test-interceptors.md` and follow it.

**Gate**: if pass rate <70%, halt the polish pass before P1 and write a
diagnosis report at `docs/games/<engine>_polish_blocker.md` listing the
top failure categories. The user wakes up to "engine has N broken
interceptors, here's the punch list" rather than "polish pass spent 3
hours producing nonsense." Print:

```
=== POLISH PASS HALTED at P0 ===
pass rate: X%  (threshold: 70%)
see: docs/games/<engine>_polish_blocker.md
```

If pass rate ≥70%, continue. Even 70–90% should produce a "watchlist"
section in the final report flagging the failed cards.

### P1 — Generalized deckbuilder

Invoke `/build-decks --game <engine> --num-decks <polish-num-decks>
--bias balanced --games 4`. Read `.claude/commands/build-decks.md` and
follow it.

The starters from `/new-game` are the benchmark pool. Winners (decks
that beat all starters, or beat the field on overall winrate) get
their JSON spec saved at `logs/<engine>_decks_polish_v1.json` for
later registration into `<ENGINE>_STARTER_DECKS`.

After the tournament, if any new deck beat all starters, register it
as an additional starter:

1. Read the JSON spec.
2. Edit `src/cards/<engine>/<set_module>/decks.py` (or wherever
   `<ENGINE>_STARTER_DECKS` lives) to add a factory function for the
   winning deck.
3. Add a one-line note to `docs/strategy/<engine>.md` (creating it if
   absent) explaining the new deck's hypothesis.

If no new deck beat all starters, do NOT register anything — the
existing starters are already locally optimal. Note the negative
result in the final report.

**Tournament error gate** (applies to every tournament invocation in
this polish pass — P1, P1.5, P5a): after the tournament finishes,
parse `aggregated.totals` from the output JSON. If
`errors / games > 0.05`, **halt the polish pass** and write
`docs/games/<engine>_polish_blocker.md` with:
- the error rate observed
- a sample traceback (first error's `error` field)
- which stage detected it (P1 / P1.5 / P5a)
- suggested next step (likely a real engine bug — investigate the
  reported file/line, not the AI tuning).

Two recent engine bugs in the Minecraft TCG (`auto_block` bypass and a
`GameObject` in `block_map`) were each invisible to interceptor tests
(P0/P4) but produced 10.8% tournament errors at scale. This gate
catches that class of bug.

### P1.5 — Meta discovery (variant tournament)

**Why before P2**: `/ultra-loop` patches a specific bias preset. Without
knowing which preset is the format meta, the patch targets whichever
preset was passed (often a default or the author's first guess). A
brief variant tournament identifies the meta empirically, so P2's AI
tuning compounds toward the actual strongest play instead of an
arbitrary one.

Procedure:

1. Check the variant tournament harness:
   - `scripts/play/variant_tournament.py` exists.
   - The engine appears in its `ENGINES` registry.
   - The engine has ≥3 bias presets in `<UPPER>_BIAS_PRESETS`.

   If any of those is false, **skip** P1.5 with a logged note:
   `"<engine> has no variant tournament support; P2 falls back to default preset"`.
   Print the note and continue.

2. Run:

   ```
   PYTHONPATH=. python scripts/play/variant_tournament.py \\
       --engine <engine> --games 4 --max-turns 35 \\
       --out logs/<engine>_polish_meta_discovery.json
   ```

3. **Tournament error gate** (see P1 for the shared procedure):
   parse `aggregated.totals.errors / .games`. If > 5%, HALT.

4. Read `aggregated.ranking[0]` from the JSON. That's the meta
   preset. Capture its name as `<meta-preset>` for the rest of the
   polish pass.

5. Print the discovery:

   ```
   === P1.5: meta preset discovered ===
   winner:  <meta-preset>  (<winrate>%, <wins>/<games>)
   margin vs random:  <delta>pp
   margin vs worst:   <delta>pp
   ```

6. If the margin vs `random` (if present in the preset registry) is
   <5pp, the variant tournament didn't surface meaningful strategic
   difference yet. Note in the final report: "Variant axes don't
   express enough strategic content; P2 may produce shallow patches."
   Continue anyway.

Output: `<meta-preset>` is consumed by P2.

### P2 — AI tuning via /ultra-loop (single + double)

P2 runs `/ultra-loop` twice back-to-back: first single mode, then
double. Single mode patches the heuristic AI's blind spots from a
skilled-pilot perspective. Double mode then has two skilled pilots
play each other, surfacing strategic questions neither single-mode
exploitation nor heuristic-vs-heuristic tournaments can reach.

**Use `<meta-preset>` from P1.5 as the `--ai-bias`** in both sub-stages.
If P1.5 was skipped (engine has no variant tournament support),
`/ultra-loop` falls back to its own preset discovery (the first
non-default preset).

#### P2a — Single ultra loop

Read `.claude/commands/ultra-loop.md` and invoke it as:

```
/ultra-loop --game <engine> --mode single \\
    --ai-bias <meta-preset> \\
    --iterations <polish-pilot-games> \\
    --my-deck <first_starter> --ai-deck <first_starter>
```

`<first_starter>` = first key in `<ENGINE>_STARTER_DECKS` (or the
polished winner from P1 if one was registered). Drop `--ai-bias` if
P1.5 was skipped.

The loop handles strategy-doc creation/update, deck-plan persistence,
and bias-preset patches. When it returns, capture the iteration count
and any preset-weight deltas for the final report.

#### P2b — Double ultra loop

Same skill, double mode:

```
/ultra-loop --game <engine> --mode double \\
    --ai-bias <meta-preset> \\
    --iterations <polish-pilot-games> \\
    --my-deck <first_starter> --ai-deck <second_starter>
```

`<second_starter>` = a different starter from the same registry. If
only one starter exists (very brand-new engine), pass the same deck on
both sides — the LLM pilots' strategic divergence still produces
signal, just less than a deck-mismatch matchup.

If P2a's run modified the harness to support two-pilot mode (by
adding `--two-pilot`), P2b reuses that. If not, P2b's pre-flight
(§0a in `ultra-loop.md`) adds it.

#### Post-P2 watchlist

If P0's interceptor verification flagged cards as failing, the ultra
loops should now confirm whether those cards ever appear in real play
— the pilots will (or won't) reach for them. Note any cards that
*neither* pilot ever plays in the final report; those are zero-play
cards that the deckbuilder + AI tuning can't redeem and should be
considered for redesign.

### P3 — Frontend polish

The frontend frame from `/new-game`'s stage 2 is functional but not
visually distinguished. P3 takes a real visual-design pass.

Invoke the `frontend-design` skill via the Skill tool. Brief it with:

> Polish the `<engine>` game frontend at
> `frontend/src/games/<engine>.tsx`. The current implementation is a
> functional MVP — readable but generic. Take a real visual-design
> pass appropriate to the theme `<theme>`.
>
> Constraints:
>   - Don't change game logic; visual layer only.
>   - Reuse the project's existing styling vocabulary (read sibling
>     game components in `frontend/src/games/` to see the design
>     language). Don't introduce a new design system.
>   - Read `frontend/src/games/minecraft.tsx` and one other engine for
>     the level of polish to match.
>
> After: run `cd frontend && npm run build` to confirm the build still
> passes. If it fails, fix root causes.

If `frontend-design` is not available, skip P3 with a logged note —
don't fail polish for an unavailable skill.

### P4 — Interceptor verification (re-run)

Re-invoke `/test-interceptors --game <engine> --set <set_code>` to
verify nothing P1–P3 broke. The deckbuilder and AI tuner shouldn't
have changed card defs, but if P2's adapter patches inadvertently
broke a card path, this catches it.

If pass rate dropped vs P0, halt and report — something downstream
broke the engine. If it stayed flat or improved, continue.

### P5 — Wet test

Three sub-tests. All run; report aggregates.

**P5a — AI vs AI tournament with telemetry**

```
PYTHONPATH=. python scripts/play/<engine>_deck_tournament.py \\
    --decks <all_starters_inc_polished_winner> \\
    --bias <meta-preset> --games 5 --max-turns 35 \\
    --log-interceptor-fires \\
    --out logs/<engine>_polish_wet.json
```

Use `<meta-preset>` from P1.5 (or `balanced` if P1.5 was skipped).

If the tournament script doesn't support `--log-interceptor-fires`,
spawn a small agent to add it (read `mc_deck_tournament.py` for the
pattern — wrap the game loop with an event listener that counts
interceptor invocations per card). The telemetry catches cards that
*never fire* in real play — different signal from P0/P4 (which fire
the trigger artificially).

**P5a-1 — Tournament error gate** (same procedure as P1/P1.5):

Parse `aggregated.totals.errors / .games`. If > 5%, **halt the polish
pass** and write `docs/games/<engine>_polish_blocker.md`. By P5a, the
ultra-loop has applied AI tuning; an error rate spike here likely
means a tuning patch broke something (re-check P2's bias edits).

**P5a-2 — Polish punchlist** (feed-forward to future passes):

Parse the tournament JSON (and the per-card telemetry from
`--log-interceptor-fires` if available) to identify:

- **Zero-play cards**: present in ≥1 deck but never entered the
  battlefield in any game. Their interceptor never fired in real
  play (P0 fired it artificially; P5a confirms it never fires
  through normal gameplay).
- **Loss-only cards**: appeared in ≥3 games, controller's deck never
  won any of those games. Either the card actively loses, or the
  decks featuring it are uncompetitive.
- **Cast-but-no-impact cards**: appeared and entered play, but never
  contributed measurable progress (no kills, no damage attributed,
  no triggered effects). Limp filler.

Write `docs/games/<engine>_polish_punchlist.md`:

```markdown
# <Engine> Polish Punchlist — <ISO date>

## Zero-play cards (in deck, never entered play)
| Card | Decks featuring it | Action |
|------|-------------------|--------|
| <name> | <list>            | Redesign or remove |

## Loss-only cards (appeared, controller always lost)
| Card | Appearances | Action |
|------|-------------|--------|
| <name> | <count>     | Investigate / redesign |

## Cast-but-no-impact cards (in play, no measurable effect)
| Card | Plays | Action |
|------|-------|--------|
| <name> | <count> | Audit effect_fn or AI play priority |

## Recommendations for next polish pass
- ...
```

Future polish passes and `/new-set` invocations should READ this file
to inform redesign priorities. P0 of the *next* polish pass also
reads this file (see P0's pre-flight). The pattern: each polish pass
leaves a punchlist that the next pass starts from, instead of
rediscovering the same dead weight cold.

**P5b — Browser wet test**

Use the browser automation tools (`mcp__claude-in-chrome__*`) to:
1. Start the dev server: `cd frontend && npm run dev` (background).
2. Navigate to `http://localhost:5173/<engine>` (or the route
   registered in `frontend/src/games/registry.ts`).
3. Click through one full AI-vs-AI game (or human-vs-AI if the
   frontend supports it). Screenshot 3–5 key moments.
4. Read browser console (`mcp__claude-in-chrome__read_console_messages`)
   filtered for errors. Any uncaught exception is a wet-test failure.

Per CLAUDE.md: this is a "hard wet test" — try to break the happy
path. End turn out of order, click cards in wrong zones, see what
happens. Note any UX brittleness.

Stop the dev server when done.

**P5c — Smoke run-through of generated tests**

```
PYTHONPATH=. python tests/test_<engine>_smoke.py
PYTHONPATH=. python tests/test_<engine>_interceptors.py
```

Both should pass. Any failure is a regression.

**P5d — Plan-vs-reality drift check**

`/ultra-loop` produces deck plans at `docs/decks/<deck>_plan.md`. Each
plan has a "Target turns" section claiming a lethal turn estimate
(e.g. "T10-12 lethal"). If a plan's estimate is wildly off the actual
P5a tournament outcomes, the plan is misleading the next pilot — every
future iteration of `/ultra-loop` will read the wrong target and
either underplan (kills come slower than expected → pilot panics
mid-game) or overplan (kills come faster than expected → pilot wastes
turns on infrastructure).

Procedure:

1. List all `docs/decks/<deck>_plan.md` files modified during this
   polish pass (P2's `/ultra-loop` writes them). If none exist, skip
   P5d with a note.

2. For each plan, parse its "Target turns" section. Extract the
   declared lethal turn — look for the latest "T<N>" or "T<N>-<M>"
   pattern in the section (e.g. "T10-12" → use 11 as midpoint, or
   12 as upper bound; pick the upper bound for conservatism).

3. From `logs/<engine>_polish_wet.json` (P5a output), compute the
   median turn count for games where this deck WON. Specifically:

   ```python
   wins = [o["turns"] for o in outcomes
           if o["winner_deck"] == <deck_name>]
   actual_median = statistics.median(wins) if wins else None
   ```

   If `wins` < 3 games, the deck didn't win enough to compare —
   skip with a note ("insufficient data: <count> wins").

4. Compute drift: `|actual_median - predicted| / predicted`. Flag
   plans with **drift > 30%** as misleading.

5. Write `docs/games/<engine>_plan_drift.md`:

   ```markdown
   # <Engine> Plan-vs-Reality Drift — <ISO date>

   Polish-pass post-check. Compares each deck plan's predicted lethal
   turn against the median turn count from P5a tournament wins.

   ## Drift summary

   | Deck | Predicted | Actual median | Drift | Action |
   |------|-----------|---------------|-------|--------|
   | <deck> | T<N>     | T<M>          | ±X%   | <Rewrite | OK> |

   ## Recommended rewrites

   For each flagged plan:
   - Plan file: `docs/decks/<deck>_plan.md`
   - Section to rewrite: "Target turns"
   - Suggested replacement: `T<actual_lower>-<actual_upper>` based on
     the empirical 25th–75th percentile of winning game lengths.

   The next `/ultra-loop` invocation reads these plans; rewriting
   them keeps the next pilot from inheriting wrong predictions.
   ```

6. If any drift > 30%, the final report's "Outstanding TODOs" section
   lists the affected plans for human attention. Don't auto-rewrite
   plans here — drift detection is observation, not correction;
   correction happens in the next `/ultra-loop` run when the coach
   has fresh game data plus this report.

### Final report

Append a "Polish pass" section to `docs/games/<engine>.md`:

- **P0 pass rate**: X% (Y/Z cards). If <100%, link to the failure
  list. Also note any cards from the prior polish punchlist that this
  pass resolved or persist.
- **P1 deckbuilder**: did any new deck beat all starters? List
  winners. Tournament error rate (must be ≤5% to have continued).
- **P1.5 meta discovery**: discovered meta preset name + winrate. If
  skipped, note why. Also note margin vs `random` baseline (small
  margin = bias surface needs more axes).
- **P2 AI tuning**: summary of strategy doc additions; list of bias
  patches applied to `<engine>_adapter.py`. Note which preset was
  patched (should be `<meta-preset>` from P1.5).
- **P3 frontend**: brief note on what changed; link to a screenshot
  if P5b captured one.
- **P4 pass rate**: X% (delta vs P0).
- **P5a tournament**: top 3 decks by winrate. Tournament error rate.
  Punchlist counts: zero-play cards, loss-only cards, no-impact cards.
- **P5b browser**: pass / fail; note any UX issues.
- **P5c smoke**: pass / fail.
- **P5d plan drift**: list of deck plans flagged with drift > 30%.
  Each is a TODO for the next `/ultra-loop` invocation.
- **Outstanding TODOs**: aggregate from all stages, including:
  - Plans flagged by P5d.
  - Cards on the persistent-dead-weight list (failed P0 multiple
    polish passes in a row).
  - Punchlist redesign candidates (zero-play, loss-only, no-impact).

**Artifacts produced this pass** (paths for the next pass to consume):

- `logs/<engine>_polish_meta_discovery.json` — variant tournament JSON
- `logs/<engine>_polish_wet.json` — P5a tournament JSON
- `docs/games/<engine>_polish_punchlist.md` — feeds P0 of next pass
- `docs/games/<engine>_plan_drift.md` — feeds next `/ultra-loop`'s coach
- `docs/games/<engine>_polish_blocker.md` — only present if a gate
  halted this pass; pass start of next pass should check & resolve

Then a tight status message:

```
=== /new-game-plus complete ===
engine:    <engine>
runtime:   <total>h
P0 / P4:   X% / Y% interceptor pass rate
new decks: <list of polished winners>
ready:     <yes if all gates passed, else "see polish report">
```

## Notes for the orchestrator

- **Skipped stages**: if `--skip-stage` is passed, drop the listed
  stages but keep the order intact for surviving stages. Skipping P0
  is allowed but loud — print a warning.
- **No mid-pipeline commits**, same as `/new-game`. The user types
  `commit` themselves at the end.
- **Failure handling**: hard halts (write `<engine>_polish_blocker.md`,
  do not continue):
  - **P0** with pass rate <70% (engine broken).
  - **Tournament error gate** (>5% errors) at P1, P1.5, or P5a.
    Engine has runtime instability; downstream tuning would compound
    on a broken foundation.
  - **P4** if pass rate dropped vs P0 (a P1–P3 stage broke a card).

  All other stages soft-fail — they log the failure and continue, so
  the user always gets *some* polish even if one stage misbehaves.
  P5d (drift check) is observation-only; never halts.
- **Tooling absences are not failures**: if `frontend-design` isn't
  available, skip P3 and log it. If browser automation isn't set up,
  skip P5b and log it. The pipeline keeps going.
- **Stage independence**: P0–P5 don't share state beyond the on-disk
  artifacts of `/new-game`'s stage 9. Each stage reads what it needs
  and writes its own outputs. This makes individual stages
  re-runnable: if P3 fails, you can rerun just that stage manually
  without redoing P0–P2.
