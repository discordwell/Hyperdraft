---
description: Walk through quarantined /ultra-loop iterations and apply (or dismiss) their claims one at a time. Prompts for a reproducer test before any encoder-suggested edit lands in real code.
argument-hint: [--game <name>] [--log-dir <path>] [--iter <N>]
---

# /quarantine-review — triage contaminated ultra-loop iterations

The `/ultra-loop` skill writes contaminated iterations' coach/encoder
outputs to a `quarantine/` sub-directory of the loop's log dir, NOT
into real source files. This skill walks through those quarantined
claims one at a time and decides what to do with each.

The canonical motivating case: BRV v2-iter3c. A state-file race
truncated the pickle mid-game, the pilot mis-attributed the resulting
"card consumed, no effect" reads to engine bugs in Switch and Potion,
and the encoder applied `-100` hard-block scorers to `trainers.py`.
Those workarounds silenced two working cards until they were retracted
in commit 7a982116 (along with a reproducer test in
`tests/test_brv_gap_v3.py`). Under this skill they would have been
caught before any code change landed.

## Arguments

User invoked with: `$ARGUMENTS`

- `--game <name>` — restrict to a specific game's loop logs.
- `--log-dir <path>` — review only the manifests under this loop log.
  Defaults to scanning all of `logs/`.
- `--iter <N>` — jump straight to a specific iteration's manifest.

## Workflow

### 1. Discover quarantined manifests

Run the discovery helper:

```bash
python -c '
from pathlib import Path
from scripts.play import ultra_loop_quarantine as q
manifests = q.discover_quarantined_across_logs(Path("logs"))
for m in manifests:
    print(f"{m[\"log_dir\"]}  iter={m[\"iteration\"]}  status={m[\"status\"]}  signals={m[\"signals\"]}")
'
```

If `--log-dir` was given, use `q.list_quarantined(Path("<log-dir>"))`
instead and iterate only those.

For each manifest with `status == "quarantined"` print a one-line
summary so the user can pick which to triage first.

### 2. For each quarantined manifest, present the claim

Read the manifest plus the bundled artefacts:

```
logs/<run>/quarantine/iter<N>/
  manifest.json         <- signals, reasons, status
  pilot_A.txt           <- pilot report
  pilot_B.txt           <- if double mode
  coach.txt             <- coach's would-be edits
  encoder.txt           <- encoder's would-be edits
  harness_log.txt       <- if captured
```

Show the user:

- The signals + reasons that triggered the quarantine.
- The specific claims the encoder wanted to apply (parse `encoder.txt`).
- The pilot evidence behind each claim (the relevant turn(s) from
  `pilot_A.txt` / `pilot_B.txt`).

### 3. Reproduce the claim before applying

For each claim, ask the user one of three options:

#### Option A — write a reproducer test

This is the default and strongly preferred. If the claim says "card X
is broken when Y happens," the reproducer is a unit test that:

1. Sets up the minimal game state Y.
2. Plays card X.
3. Asserts the expected effect either DID happen (claim is false) or
   DID NOT happen (claim is true).

Spawn a small `general-purpose` agent to draft the reproducer:

> The /ultra-loop iter <N> quarantine manifest at
> `<manifest_path>` flags a claim that <claim text>. Read the pilot's
> evidence in `<pilot_A.txt>` (and `<pilot_B.txt>` if present) and
> draft a minimal pytest reproducer in `tests/test_<game>_quarantine_iter<N>.py`.
>
> The test should construct the minimum game state needed to exercise
> the claim and assert the engine's actual behavior. Do NOT consult the
> encoder's proposed fix — write the test against the engine's real
> public API, treating the claim as a hypothesis.
>
> Run the test. Report which assertion fired and what it concluded.

If the reproducer test passes (i.e. the engine behaves as the pilot
expected — the claim is real), the user should:

```python
from pathlib import Path
from scripts.play import ultra_loop_quarantine as q
q.mark_verified(
    Path("<log-dir>"),
    iteration=<N>,
    reproducer_test="tests/test_<game>_quarantine_iter<N>.py::test_<name>",
    notes="<one-line summary>",
)
```

…and THEN spawn the coach + encoder apply step the same way `/ultra-loop`
would have if the iter had been clean. Their changes now land in real
source files, backed by a regression test.

If the reproducer test FAILS to reproduce the claim (i.e. the engine
behaves correctly, the pilot was wrong — the BRV v2-iter3c case),
dismiss the claim:

```python
from pathlib import Path
from scripts.play import ultra_loop_quarantine as q
q.mark_dismissed(
    Path("<log-dir>"),
    iteration=<N>,
    notes="reproducer in tests/test_<game>_quarantine_iter<N>.py confirms <X> works correctly",
)
```

Commit the reproducer anyway — it documents the false alarm and
locks in the correct behavior so a future loop can't make the same
mistake.

#### Option B — dismiss as false alarm

If after re-reading the pilot's evidence and the engine code the claim
is obviously bogus (e.g. mis-read of a packet, pilot confusion), call
`mark_dismissed` directly with a notes explanation. No reproducer
required — but writing one is still recommended if the engine is
under active development.

#### Option C — defer

If the claim is genuinely interesting but the user doesn't have time
right now, leave the status as `quarantined` and move on. The next
`/quarantine-review` run will pick it back up.

### 4. Retroactive quarantine (post-hoc discovery)

If contamination is discovered AFTER a loop already applied its claims
(the BRV v2-iter3c case), the user can backfill the quarantine
manifest so this skill can drive triage:

```python
from pathlib import Path
from scripts.play import ultra_loop_quarantine as q
q.retroactive_quarantine(
    Path("logs/<run>"),
    iteration=<N>,
    reasons=[
        "single-mode used in a double-mode loop (mode collapse)",
        "state-file race truncated pickle (stale packet on T4)",
    ],
    coach_output=open("logs/<run>/iter<N>_coach.txt").read(),
    encoder_output=open("logs/<run>/iter<N>_encoder.txt").read(),
)
```

The reviewer is then responsible for reverting any code changes that
came from the now-quarantined iter, BEFORE running through the
reproducer step. The retroactive helper only moves artefacts; it does
not unwind committed code.

### 5. Final summary

After the reviewer has walked every quarantined manifest, print:

```
Triaged <N> quarantined iterations:
  verified:   <M>   (claims applied, backed by reproducers)
  dismissed:  <K>   (false alarms; reproducers committed as regressions)
  deferred:   <D>   (left as quarantined for a future pass)
```

If `verified > 0`, remind the user to commit the corresponding code
changes from the encoder's now-applied claim list. If `dismissed > 0`,
remind them to commit the reproducer tests that nailed down the
correct behavior.

## Notes

- Interactive command. User watches and confirms each apply/dismiss.
- This skill does NOT auto-apply anything that wasn't already explicitly
  marked `verified`. Every edit requires a passing reproducer test or
  an explicit `mark_dismissed` decision.
- The quarantine module
  (`scripts/play/ultra_loop_quarantine.py`) is engine-agnostic — it
  operates on the loop's own JSON manifests. So this skill works for
  every game `/ultra-loop` supports.
- For background on the workflow and the BRV v2-iter3c case study, see
  `docs/methodology/quarantine.md`.
