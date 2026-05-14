# /ultra-loop quarantine workflow

The `/ultra-loop` skill spawns an LLM pilot, a coach, and a heuristic
encoder. The encoder converts the pilot's observations into adapter
code changes. If the pilot's game was *contaminated* — harness errors,
mode collapse, partial play, state-file race conditions — the encoder
can still produce plausible-looking "bug fixes" that silently land in
real code.

This document defines what counts as contamination, how the workflow
catches it, and how to triage quarantined claims.

## Motivating case — BRV v2-iter3c

During the BRV ultra-loop v2 session (commit `3540b21d`):

| Iter | Mode | Winner | Turns | Notes |
|---|---|---|---|---|
| v2-1 | double | Boros | 31 | Clean |
| v2-2 | double | Dimir | 17 | Clean |
| v2-3a | double | abort | 2 | **State file corrupted by parallel write race** |
| v2-3b | double-retry | abort | 4 | **Same race; pilots stuck polling** |
| v2-3c | **single** | Dimir | 11 | **Pilot played both seats sub-optimally** |

The progression report EXPLICITLY flagged v2-3c as contaminated. The
encoder's `-100` hard-block claims for **Switch** and **Potion** in
`src/ai/pokemon/trainers.py` were still applied — silencing two
working cards. The workarounds stayed until commit `7a982116` removed
them after a reproducer (`tests/test_brv_gap_v3.py`) confirmed both
cards work correctly end-to-end through `_play_trainer`.

The quarantine workflow makes that failure mode impossible: contaminated
iters' coach/encoder outputs land in `quarantine/` rather than being
applied, and a reproducer is required before any quarantined claim can
become code.

## What counts as contamination

The detector lives in `scripts/play/ultra_loop_quarantine.py` and
checks six signal classes:

| Signal | Trigger | Why it matters |
|---|---|---|
| **pilot_self_report** | Pilot wrote `CONTAMINATED`, `STATE FILE CORRUPTED`, `STALE PACKET`, `PARALLEL WRITE RACE`, `PLAYED BOTH SEATS`, `ABORT`, etc. | Pilot is the closest witness — if it says "something was off," believe it. |
| **harness_error** | `EOFError`, `UnpicklingError`, `ran out of input`, `pickle data was truncated`, refused active-player checks in the harness log, pilot report, or coach output. | The game state the pilot was reading was inconsistent. Any conclusion based on it is suspect. |
| **partial_completion** | `turns_played < expected_min_turns` (default 5). | A 2-turn game didn't reach key decision points. The pilot can't have learned anything about the matchup. |
| **mode_collapse** | Requested mode differs from actual mode (e.g. user asked for `double`, loop fell back to `single`). | In single mode the pilot effectively plays both seats. Cross-check disappears, and the "opponent's" actions are filtered through the same model — no independent signal. |
| **missing_pilot_report** | Double mode but only one pilot report exists. | One pilot crashed; the surviving one either filled in or the orchestrator dropped to a heuristic. Either way, double-mode synthesis is impossible. |
| **orchestrator** | Free-form signals passed in by the loop runner (watchdog kill, timeout, manual flag). | Catch-all for things the static detector can't see. |

All six are union'd into the iteration's `signals` list. Any non-empty
list flags the iter as contaminated.

## Workflow

```
                    /ultra-loop iteration N
                              │
                              ▼
         ┌──────── pilot(s) play, write report ────────┐
         │                                              │
         │  pilot writes CONTAMINATED markers if any   │
         │                                              │
         └────────────────────┬────────────────────────┘
                              │
                              ▼
                detect_contamination(artifacts)
                              │
            ┌─────────────────┴─────────────────┐
            ▼                                   ▼
        CLEAN                              CONTAMINATED
            │                                   │
            │                                   │
   apply_iteration                      quarantine_iteration
            │                                   │
   coach + encoder apply        write to logs/<run>/quarantine/iterN/
   to real source files                        │
            │                                   │
            ▼                                   ▼
   logs/<run>/iterN_*.txt           manifest.json (status="quarantined")
                                                │
                                                ▼
                                     /quarantine-review
                                                │
                              ┌─────────────────┴─────────────────┐
                              ▼                                   ▼
                  draft reproducer test                  obvious false alarm
                              │                                   │
                              ▼                                   │
                  test passes (claim real)                        │
                              │                                   │
                              ▼                                   ▼
                      mark_verified                       mark_dismissed
                              │                                   │
                              ▼                                   │
              spawn coach + encoder apply                         │
              for this iter — edits land in code                  │
                                                                  │
                                                                  ▼
                                              reproducer committed as
                                              regression (locks in correct
                                              behavior so future loops
                                              can't repeat the mistake)
```

## How a real claim flows

### Clean case
1. Iter N runs to natural end. Pilot reports T=20+ turns, no contamination markers, no harness errors.
2. `detect_contamination` returns `contaminated=False`.
3. `apply_iteration` writes `logs/<run>/iterN_coach.txt` + `logs/<run>/iterN_encoder.txt`.
4. The coach and encoder apply steps run as usual — edits land in
   `docs/strategy/<game>.md`, `src/ai/<game>_adapter.py`, etc.

### Contaminated case (under this workflow)
1. Iter N runs but hits a state-file race. Pilot writes `STALE PACKET` and `PARALLEL WRITE RACE` in its report.
2. `detect_contamination` flags `pilot_self_report` + `harness_error`. `contaminated=True`.
3. `quarantine_iteration` writes the coach/encoder outputs to
   `logs/<run>/quarantine/iterN/{coach.txt, encoder.txt, pilot_A.txt, ...}`
   plus a `manifest.json` with `status="quarantined"`.
4. The loop's end-of-run summary mentions iter N is in quarantine and
   prompts the user to run `/quarantine-review`.
5. The user runs `/quarantine-review`. For each claim:
   - Read the claim and the pilot's evidence.
   - Spawn a small agent to write a minimal reproducer test.
   - If the test PASSES (claim is real): `mark_verified(reproducer_test=...)` and apply the encoder's edits with a regression test backing them.
   - If the test FAILS (claim is bogus — BRV v2-iter3c): `mark_dismissed(...)` and commit the reproducer anyway to lock in correct behavior.

## How to retroactively quarantine

If contamination is discovered AFTER a loop already applied its
claims (i.e. the BRV v2-iter3c scenario as it actually happened):

```python
from pathlib import Path
from scripts.play import ultra_loop_quarantine as q

q.retroactive_quarantine(
    Path("logs/ultra_loop_brv_v2"),
    iteration=3,
    reasons=[
        "single-mode used in a double-mode loop (mode collapse)",
        "state-file race truncated pickle (stale packet on T4)",
    ],
    coach_output=open("logs/ultra_loop_brv_v2/iter03_coach.txt").read(),
    encoder_output=open("logs/ultra_loop_brv_v2/iter03_encoder.txt").read(),
)
```

This writes the manifest as if the loop had quarantined the iter at
the time. The reviewer then:
1. **Reverts** any code changes that came from the iter. (For BRV
   v2-iter3c, that meant removing the `-100` scorers from
   `trainers.py` — already done in commit `7a982116`.)
2. Runs `/quarantine-review` to walk through the claims with
   reproducers, just like a regular quarantine triage.

## How to mark a claim as a false alarm

If after reproducing you've confirmed the engine is correct and the
claim is bogus, dismiss it:

```python
from pathlib import Path
from scripts.play import ultra_loop_quarantine as q

q.mark_dismissed(
    Path("logs/ultra_loop_brv_v2"),
    iteration=3,
    notes=(
        "tests/test_brv_gap_v3.py confirms Switch swaps Active/Bench "
        "correctly via _switch_resolve, and Potion heals 3 damage "
        "counters correctly. Original 'engine bug' was a stale-packet "
        "read from the state-file race condition."
    ),
)
```

The encoder's edits do NOT get applied. The manifest stays in
`quarantine/` as a record. The reproducer test is committed regardless —
it locks in the correct behavior so a future loop can't make the same
mistake.

## How to manually quarantine in advance

If you can already predict a session will be contaminated (e.g. you
know the harness has a race condition that hasn't been fixed yet),
pass an extra signal when constructing `IterationArtifacts`:

```python
art = q.IterationArtifacts(
    iteration=3,
    mode="single",
    requested_mode="double",
    pilot_reports={"A": pilot_report},
    coach_output=coach,
    encoder_output=encoder,
    turns_played=11,
    extra_signals=["harness race condition known to corrupt state — see issue #42"],
)
```

The `orchestrator` signal will fire and the iter will go straight to
quarantine.

## Why this is conservative on purpose

The cost of a false-positive quarantine (clean iter goes to
`quarantine/` and needs a one-line `mark_verified` to release) is a
few minutes of review time. The cost of a false-negative (contaminated
iter's bogus claims silently land in real code) is multiple commits to
unwind — and possibly a regression that doesn't surface for weeks.

Lean toward over-flagging. The reviewer can always run a 30-second
reproducer to validate or dismiss. The encoder can't.
