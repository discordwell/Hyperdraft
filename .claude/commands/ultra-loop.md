---
description: Engine-agnostic LLM-pilot training loop. Single mode = LLM pilot vs heuristic AI. Double mode = two LLM pilots play each other; coach synthesizes both reports. Updates strategy doc + AI bias presets + heuristic decision logic after each game.
argument-hint: [--game <name>] [--mode single|double] [--iterations N] [--ai-bias NAME] [--my-deck NAME] [--ai-deck NAME] [--decks-file PATH]
---

# /ultra-loop — discovery-driven LLM-pilot training

The "ultra" tier of an engine's AI isn't a heuristic — it's an LLM
playing with full strategic reasoning, persisting learnings to the
strategy doc, and patching the heuristic AI's blind spots along the
way.

Two modes:
- **single** — LLM pilot vs heuristic AI. The pilot exploits the
  heuristic's documented weaknesses; the coach patches them. The
  default mode.
- **double** — two LLM pilots play each other. Higher signal-to-noise
  (no "AI made an obvious blunder" contamination), and the coach gets
  TWO reports — winner's exploits + loser's regrets — to synthesize a
  richer strategy update.

## Arguments

User invoked with: `$ARGUMENTS`

Optional (inferred from repo state if absent — see "Game inference" below):
- `--game <name>` — engine to train. Maps to `src/cards/<name>/`,
  `src/ai/<name>_adapter.py`, `docs/strategy/<name>.md`,
  `scripts/play/<name>_wet_test.py` (or closest equivalent).

Other optional:
- `--mode single|double` (default `single`)
- `--iterations N` (default 3)
- `--ai-bias NAME` (default: discover from adapter; pick one) — the
  heuristic preset used when one or both seats need a heuristic. In
  double mode, only used as a fallback if a pilot fails.
- `--my-deck NAME` (default: first starter)
- `--ai-deck NAME` (default: same as `--my-deck`)
- `--decks-file PATH` — JSON of custom decks (e.g. from `/build-decks`)

## Workflow

### Game inference (when `--game` is omitted)

If `--game <name>` is not provided, infer it from repo state:

1. Run `git status --short`. Tally how many modified/untracked files
   match `src/cards/<X>/`, `src/engine/<X>*.py`, `src/ai/<X>_adapter.py`,
   `frontend/src/games/<X>.tsx`, or `docs/strategy/<X>.md` for each
   candidate `<X>`.
2. If a single game has ≥3 matches AND dominates runners-up ≥3:1, pick it.
3. Else: run `git log -5 --name-only` and apply the same tally to
   recent commits.
4. Else: list `src/cards/*/__init__.py`. If only one engine directory
   exists, use it.
5. Else: halt with "Could not infer --game. Candidates: <list>. Pass
   --game explicitly."

Print the inferred game in the discovery block so it's visible.

### 0. Pre-flight discovery

Before spawning anything, discover engine specifics:

1. Confirm `src/cards/<game>/`, `src/ai/<game>_adapter.py` exist.
2. Find the wet-test harness. Order of preference:
   - `scripts/play/<game>_wet_test.py`
   - `scripts/play/<game>_play.py`
   - `scripts/play/play_<game>.py`
   - Halt and report if none found — the loop needs an interactive
     harness so a subagent can play turn-by-turn.
3. Find the bias-preset registry. Pattern: `<UPPER>_BIAS_PRESETS` dict
   in `src/ai/<game>_adapter.py`. If `--ai-bias` not given, pick a
   non-default preset (the loop's job is to challenge the AI; default
   preset is the easy match).
4. Find `docs/strategy/<game>.md`. Create a stub if absent — the loop
   produces it.
5. Find the deck registry. Same convention as `/build-decks`:
   `<UPPER>_STARTER_DECKS` in `src/cards/<game>/__init__.py`. If
   `--my-deck` not given, pick the first starter.
6. **Mode-specific discovery**:
   - Single: nothing extra.
   - Double: check if the harness supports a "no-AI / both-pilots"
     mode. Look for `--ai-bias none`, `--manual-both`, `--two-pilot`,
     or equivalent flags. If absent, **spawn a small agent to add
     one** before the loop runs (see §0a).

Print a discovery block:

```
=== /ultra-loop pre-flight ===
game:           <game>
mode:           <single|double>
harness:        scripts/play/<...>.py
bias preset:    <ai-bias>  (from <UPPER>_BIAS_PRESETS)
my deck:        <name>     (from <UPPER>_STARTER_DECKS)
ai deck:        <name>
strategy doc:   docs/strategy/<game>.md
iterations:     <N>
==> proceeding...
```

### 0a. (Double mode only) Add two-pilot harness mode if missing

If pre-flight found no two-pilot mode, spawn one Agent (general-purpose).
Brief:

> The wet-test harness at `<harness_path>` doesn't support a
> two-pilot mode (where both seats are externally controlled and
> `end_turn` does NOT auto-run a heuristic AI). Add minimal support:
>
> 1. Add a `--two-pilot` flag to the `start` subcommand. When set,
>    persist `two_pilot=True` in the saved game state.
> 2. In `cmd_end_turn` (or equivalent), if `two_pilot` is set, advance
>    the turn boundary but skip the AI execution block. The next
>    pilot's commands will then operate on the new active player's
>    state.
> 3. Add a `--seat p1|p2` flag to action commands so the second pilot
>    can act on the OFF turn (or have the harness use `state.active_player_id`
>    automatically — pick whichever is simpler).
> 4. Run `<harness_path> start --two-pilot ...` and verify both seats
>    can take actions. Don't add full test coverage — this is plumbing.
>
> Keep the patch under 50 LOC. Mirror the existing argparse pattern.

### 1. Mode dispatch

#### Single mode — for each iteration

##### 1a. Spawn pilot subagent

Use `Agent` tool with `subagent_type=general-purpose`. Brief:

> You are the `<game>` ultra pilot — an LLM that plays with full
> strategic reasoning. You're playing P1 against a heuristic AI
> opponent running the `<ai-bias>` preset on the `<ai-deck>` deck.
>
> **Read first** (these are persistent memory across sessions):
> 1. `docs/strategy/<game>.md` — accumulated wisdom regardless of
>    deck. Internalize.
> 2. `docs/decks/<my-deck>_plan.md` if it exists — deck-specific
>    strategy. If absent, write it before playing: read the deck
>    composition (from `<UPPER>_STARTER_DECKS` or the `--decks-file`
>    JSON) and write a hypothesis covering win condition, target turn,
>    key cards, mulligan policy. The coach refines it after the game.
> 3. `src/ai/<game>_adapter.py` — read `<UPPER>_BIAS_PRESETS["<ai-bias>"]`
>    so you know what the opponent is biased toward.
>
> **Then play one game** using the wet-test harness at
> `<harness_path>`. Discover the action commands by running
> `<harness_path> --help` and reading the source if needed. Typical
> commands: `start`, `state`, `play <card>`, attack/block actions,
> `end_turn`, `history`, `result`.
>
> Play strategically. Apply the strategy doc, watch for AI mistakes,
> exploit documented weaknesses, take notes on anything NEW.
>
> **After the game**, write `/tmp/<game>_pilot_report.md`:
>
> ```markdown
> # <Game> Pilot Report — iteration <N>
>
> ## Outcome
> <won|lost|draw> in <T> turns. Final state: ME=<...> AI=<...>.
>
> ## My deck / opponent
> Pilot: <my-deck>. Opponent: <ai-deck> running <ai-bias>.
>
> ## Game log
> <turn-by-turn 5–10 bullets>
>
> ## What worked / didn't
> <2–3 each>
>
> ## NEW observations about the AI
> <only new ones — not already in the strategy doc>
>
> ## Suggested updates
> ### To docs/strategy/<game>.md
> <bullets>
>
> ### To src/ai/<game>_adapter.py (<UPPER>_BIAS_PRESETS["<ai-bias>"])
> <specific weight changes>
> ```

##### 1b. Spawn coach subagent

> You are the `<game>` ultra coach. The pilot just played and wrote
> `/tmp/<game>_pilot_report.md`. Apply its suggestions:
>
> 1. `docs/strategy/<game>.md` — format-level lessons (true regardless
>    of deck). Add a dated changelog entry.
> 2. `docs/decks/<my-deck>_plan.md` — append iteration log; refine
>    sections if game contradicted them.
> 3. `src/ai/<game>_adapter.py` — patch the bias preset that lost. Be
>    conservative (single-digit weight changes to `<UPPER>_BIAS_PRESETS`
>    weights only — do NOT touch decision logic methods).
>
> Run the engine's tests after edits to verify nothing broke. Output
> a brief change summary; don't repeat full diffs.

##### 1c. Spawn heuristic encoder subagent

After the coach finishes, spawn a second `general-purpose` Agent. Brief:

> You are the `<game>` heuristic encoder. The LLM pilot played a game
> and wrote `/tmp/<game>_pilot_report.md`. Your job is to read the
> pilot's turn-by-turn log and encode any optimal decision sequences
> into the heuristic AI's decision logic in `src/ai/<game>_adapter.py`.
>
> **Scope**: decision LOGIC only — method bodies, conditionals,
> ordering, thresholds. Do NOT touch `<UPPER>_BIAS_PRESETS` weight
> values (that's the coach's job). Do NOT touch docs.
>
> **Process**:
> 1. Read `/tmp/<game>_pilot_report.md` — focus on the "Game log"
>    and "What worked" sections. Extract decisions of the form
>    "I did X on turn N because Y" — these are encodable rules.
> 2. Read `src/ai/<game>_adapter.py` — understand the existing
>    decision methods (`_best_biome_to_mine`, `_play_affordable_cards`,
>    `take_turn`, etc.). Identify which pilot decisions the current
>    code can't replicate.
> 3. For each gap, write targeted code changes:
>    - Ordering: if the pilot always played card A before card B when
>      both were affordable, encode that priority.
>    - Conditions: if the pilot explored on T1 before playing anything,
>      add a condition that fires explore before mine on early turns.
>    - Thresholds: if the pilot held a card until a condition was met
>      (e.g. "don't play Sculk Catalyst without a defender"), encode
>      that guard.
>    - Sequencing: if the pilot executed a multi-turn chain (explore →
>      Sculk Catalyst → Allay Courier), add lookahead that detects the
>      chain is available and prioritizes it.
> 4. Be surgical — add targeted helper methods or extend existing ones.
>    Don't rewrite the adapter. Each change should have a one-line
>    comment explaining which pilot observation it encodes.
> 5. Run the engine's tests to confirm nothing broke.
>
> Output: list the specific pilot observations you encoded and the
> method/line you changed for each. Note any observations you
> couldn't encode (complex modal choices, opponent-read decisions)
> as "deferred — needs human design."

#### Double mode — for each iteration

##### 1c. Spawn TWO pilots in parallel

Single message, two `Agent` calls. Brief each pilot identically except
for seat assignment + deck:

> You are `<game>` ultra Pilot <A|B> — an LLM playing with full
> strategic reasoning. You control seat <P1|P2> in a two-pilot game.
> Your opponent is ANOTHER LLM playing the OTHER seat. Neither side
> is a heuristic; play your A-game.
>
> Your deck: <my-deck if A, ai-deck if B>. Opponent's deck:
> <the other>.
>
> **Read first**:
> 1. `docs/strategy/<game>.md`
> 2. `docs/decks/<your-deck>_plan.md` (if exists; create if not)
>
> **Coordination**: the harness was started in two-pilot mode with
> `--two-pilot`. Use `<harness_path> state` to see whose turn it is
> before acting. Take your actions on YOUR turn only. After
> `end_turn`, the other pilot will act on its turn — do NOT issue
> commands until `state` shows your seat is active again.
>
> **Polling**: between your turns, run `state` periodically (every
> few seconds, no aggressive busy-waiting — call once, then if it's
> not your turn yet, sleep ~3s and call again, max 10 polls before
> giving up and writing your report).
>
> Play strategically. After the game ends (`result` returns a
> winner), write `/tmp/<game>_pilot_<A|B>_report.md` in the same
> shape as the single-mode pilot report.

The two pilots run **concurrently** but coordinate via the persisted
game state on disk. Important caveats:
- Only ONE pilot acts per turn; the other polls until its turn.
- If both pilots try to act simultaneously, the harness will reject
  the second one (since the active-player check fails). That's fine
  — the rejected pilot polls and tries again next turn.
- A 30-turn game with 5s polling overhead = ~5 minutes max. If both
  pilots stall for 60+ seconds, assume one crashed; the orchestrator
  spawns a fallback heuristic for the silent seat and continues.

##### 1d. Spawn coach subagent (richer, two reports)

After both pilots finish, spawn the coach. Brief:

> You are the `<game>` ultra coach. TWO LLM pilots just played each
> other and each wrote a report:
>   - `/tmp/<game>_pilot_A_report.md` — Pilot A's perspective.
>   - `/tmp/<game>_pilot_B_report.md` — Pilot B's perspective.
>
> Synthesize both:
>
> 1. **Cross-check**: where do the two pilots agree on what was
>    decisive? Where do they disagree? Disagreements are the most
>    interesting signal — both pilots are skilled, so a disagreement
>    means the strategic question is genuinely open.
> 2. **Update `docs/strategy/<game>.md`**: add format-level lessons
>    that BOTH reports support, OR explicitly call out a "contested
>    question" if the reports disagreed (e.g. "Pilot A thinks aggro
>    wins the matchup; Pilot B thinks control wins. Untested
>    hypothesis — needs more games").
> 3. **Update both deck plans**
>    (`docs/decks/<my-deck>_plan.md`, `docs/decks/<ai-deck>_plan.md`)
>    with iteration-log entries reflecting what each side learned.
> 4. **Heuristic patches**: in double mode, neither side was a
>    heuristic, so DON'T patch `<UPPER>_BIAS_PRESETS` blindly.
>    Instead, identify which existing preset would have produced the
>    losing pilot's actions, and patch THAT one. (E.g. if Pilot B
>    played greedily and lost, the `greedy` or `tempo` preset is
>    closer to that style — patch it.) If no preset matches the
>    losing pilot's style, that's a discovery — flag it as "consider
>    new preset: <name>" in the strategy doc.
>
> Run the engine's tests after edits. Output a brief change summary.

##### 1e. Spawn heuristic encoder subagent (double mode)

After the double-mode coach finishes, spawn a heuristic encoder with
the same brief as §1c but sourcing from BOTH pilot reports:

> Read `/tmp/<game>_pilot_A_report.md` AND
> `/tmp/<game>_pilot_B_report.md`. Extract decision sequences from
> the WINNER's game log — those are the plays the heuristic should
> learn. Also note any decisions where BOTH pilots agreed (strong
> signal regardless of outcome). Apply the same encoding process as
> §1c: surgical code changes to decision logic, no weight edits, tests
> after.

### 2. Save iteration outputs

After each iteration:
- `logs/<game>_ultra_iter<N>_pilot<A|B>.md` — copy of pilot report(s)
- `logs/<game>_ultra_iter<N>_coach.txt` — coach's summary
- `logs/<game>_ultra_iter<N>_encoder.txt` — heuristic encoder's change list

### 3. Final progression report

After all iterations:

- **Win/loss progression** (single: did pilot win more as iterations
  went? double: did the matchup converge or stay split?)
- **Strategy doc growth**: new bullets per iteration
- **Bias preset evolution**: which weights bumped
- **Quality check**: did pilot reports surface NEW insights, or
  re-litigate things already documented? (Same insight appearing 3x =
  strategy doc isn't capturing it well — flag.)
- **Encoder quality**: which pilot observations were encodable vs
  deferred? A high deferred rate means the adapter needs structural
  changes before weight tuning can help.
- **Mode-specific addendum**:
  - Single: list of heuristic exploits the coach patched AND the
    decision-logic changes the encoder added.
  - Double: list of contested strategic questions still open after N
    iterations — these are candidates for `/build-decks` to test or
    for a longer-running double-loop session.

## Notes

- Interactive command. User watches.
- Single mode: ~7–12 min per iteration (pilot + coach + encoder). 3 iterations = ~35 min.
- Double mode: ~12–18 min per iteration (two pilots + coach + encoder). 3 iterations = ~50 min.
- The pilot can lose. Single: that's fine, drives coach updates.
  Double: that's the *point* — coach learns from both perspectives.
- If a single-mode pilot wins all N games, escalate `--ai-bias` to a
  harder preset and re-run.
- If a double-mode matchup is 6-0 in N=6 iterations, the decks are
  mismatched, not the pilots — re-run with `--my-deck` and `--ai-deck`
  swapped, OR pick different decks.
- Strategy doc + bias presets are committed after the loop finishes
  (one commit, message summarizing the progression).
- This skill is invoked by `/new-game-plus` P2 in both modes
  back-to-back.
