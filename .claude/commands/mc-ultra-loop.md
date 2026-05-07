---
description: Self-improvement loop for MC ultra AI. LLM pilot plays N games vs heuristic AI, coach updates strategy doc + bias presets + per-deck plan after each game.
argument-hint: [--iterations N] [--ai-bias passive_econ] [--my-deck raider] [--ai-deck raider] [--decks-file PATH]
---

# /mc-ultra-loop — LLM-piloted ultra AI training loop

The "ultra" difficulty in Minecraft TCG is *not* a heuristic — it's an
LLM pilot that plays the format with full strategic reasoning, persists
its learnings to `docs/strategy/minecraft.md`, and patches the heuristic
AI's blind spots in `src/ai/minecraft_adapter.py` along the way.

This command runs the full self-improvement loop:

> pilot game → coach review → update strategy doc + heuristic preset → repeat

## Arguments

User invoked with: `$ARGUMENTS`

Defaults:
- `--iterations 3` — number of pilot/coach rounds. Each round = 1 game + 1 coach pass.
- `--ai-bias passive_econ` — the heuristic preset the pilot plays against.
- `--my-deck raider` — pilot's deck (starter name, OR a name in `--decks-file`).
- `--ai-deck raider` — opponent's deck.
- `--decks-file` (optional) — JSON file with custom decks (e.g. `logs/mc_decks_v1.json`). Required if `--my-deck` or `--ai-deck` is not a starter.

## Workflow

For each iteration:

### 1. Spawn pilot subagent

Use `Agent` tool with `subagent_type=general-purpose`. Brief:

> You are the MC ultra pilot — an LLM that plays Minecraft TCG with
> full strategic reasoning. You're playing P1 against an AI opponent
> running `<ai-bias>` preset on the `<ai-deck>` deck.
>
> **Read first** (in this order — these are persistent memory across
> sessions; lean on them):
> 1. `docs/strategy/minecraft.md` — general format strategy. The
>    accumulated wisdom from prior games regardless of deck. Internalize.
> 2. `docs/decks/<my_deck>_plan.md` — strategy specific to YOUR deck.
>    What this deck wants to do (win condition, target turn, key cards,
>    mulligan policy). **If this file does not exist**, you write it
>    BEFORE playing — read the deck composition from
>    `src/cards/minecraft/alpha.py` (for starter decks: BUILDER_NAMES /
>    MINER_NAMES / RAIDER_NAMES) or from the `--decks-file` JSON, then
>    write `docs/decks/<my_deck>_plan.md` following the template in
>    `docs/decks/README.md`. Use the Write tool. The plan is a
>    *hypothesis* — first draft is fine; the coach refines it after
>    the game.
> 3. `src/ai/minecraft_adapter.py` (just `MC_BIAS_PRESETS["<ai-bias>"]`
>    and `_DEFAULTS`) — know what the opponent is biased toward.
>
> **Then play one game** using the wet-test harness:
>
> ```
> # Start (add --decks-file if either deck is custom)
> PYTHONPATH=. python scripts/play/mc_wet_test.py start \\
>     --my-deck <my-deck> --ai-deck <ai-deck> --ai-bias <ai-bias> \\
>     [--decks-file <path-from-args>]
>
> # Inspect state
> PYTHONPATH=. python scripts/play/mc_wet_test.py state
>
> # Take actions (any combination, any order):
> PYTHONPATH=. python scripts/play/mc_wet_test.py mine <biome_idx>
> PYTHONPATH=. python scripts/play/mc_wet_test.py worker_mine <worker_id_prefix> <biome_idx>
> PYTHONPATH=. python scripts/play/mc_wet_test.py play "<card name>" [cell_x] [cell_y] [--target-id <id>]
> PYTHONPATH=. python scripts/play/mc_wet_test.py attack <attacker_prefix>:<col> [<another>:<col> ...]
> PYTHONPATH=. python scripts/play/mc_wet_test.py avatar_attack <col>
>
> # End your turn (also runs AI turn):
> PYTHONPATH=. python scripts/play/mc_wet_test.py end_turn
>
> # When game over:
> PYTHONPATH=. python scripts/play/mc_wet_test.py result
> PYTHONPATH=. python scripts/play/mc_wet_test.py history > /tmp/mc_pilot_log.txt
> ```
>
> Play strategically — apply the strategy doc, watch for AI mistakes,
> exploit the documented heuristic weaknesses, take notes on anything
> NEW you observe (the AI did something unexpected, a card combo
> worked surprisingly well, the opening hand was bad, etc.).
>
> **After the game ends**, write a single Markdown file at
> `/tmp/mc_pilot_report.md` with this structure:
>
> ```markdown
> # MC Pilot Report — iteration <N>
>
> ## Outcome
> <won|lost|draw> in <T> turns. Final HP: ME=<x> AI=<y>.
>
> ## My deck / opponent
> Pilot: <my-deck>. Opponent: <ai-deck> running <ai-bias>.
>
> ## Game log
> <turn-by-turn summary, 5-10 bullet points; what I played, what AI played, key swings>
>
> ## What worked
> <2-3 specific tactical or strategic insights — what carried this game>
>
> ## What didn't / what I'd do differently
> <2-3 things — bad opening, missed combo, etc.>
>
> ## NEW observations about the AI
> <only NEW ones — things not already in docs/strategy/minecraft.md
>  "Known heuristic-AI weaknesses" section. e.g. "AI played Bone Meal
>  on a tapped non-Worker, wasting it" or "AI never used its avatar
>  attack despite having a weapon for 4 turns">
>
> ## Suggested updates
> ### To docs/strategy/minecraft.md
> <bullet points of what to add/change>
>
> ### To src/ai/minecraft_adapter.py (MC_BIAS_PRESETS["<ai-bias>"])
> <specific weight changes that would have plugged the holes I exploited>
> ```
>
> Be concrete. Don't list general principles already in the doc; only
> list NEW ones. If you lost, focus on what you'd do differently. If
> you won decisively, focus on what AI weaknesses you exploited (so
> coach can patch them).

### 2. Spawn coach subagent

After pilot finishes, use `Agent` tool again with `subagent_type=general-purpose`. Brief:

> You are the MC ultra coach. The pilot just played a game and wrote
> a report. Your job is to apply the report's suggestions to:
>   1. `docs/strategy/minecraft.md` — format-level lessons (true regardless of deck).
>   2. `docs/decks/<my_deck>_plan.md` — deck-specific lessons. Append
>      a new entry to "Iteration log" with date, opponent, outcome, and
>      a one-line lesson. Refine sections (mulligan policy, play
>      priorities, key cards, anticipated weaknesses) if the game
>      contradicted them.
>   3. `src/ai/minecraft_adapter.py` — patch the bias preset that lost.
>
> **Read first**:
> 1. `/tmp/mc_pilot_report.md` (the pilot's findings)
> 2. `docs/strategy/minecraft.md` (current format-level state)
> 3. `docs/decks/<my_deck>_plan.md` (current deck plan)
> 4. `src/ai/minecraft_adapter.py` (preset definitions)
>
> **Then apply updates with the `Edit` tool**:
>
> - For the **strategy doc** (format-level): only add format-true
>   lessons (e.g., "Hostile mobs +1 ATK at Night" — applies to all
>   decks). Add a new dated entry to the changelog at the bottom. If a
>   "Known heuristic-AI weaknesses" section item is newly relevant,
>   refine it. **Do NOT add deck-specific tactics here** — those go in
>   the deck plan.
> - For the **deck plan** (`docs/decks/<my_deck>_plan.md`): append an
>   "Iteration log" entry with date, opponent, outcome, one-line lesson.
>   If the game revealed the win condition was misstated, the mulligan
>   rules were wrong, or a "Key card" turned out to be a trap — refine
>   those sections. The pilot's "What didn't / what you'd do
>   differently" section is the goldmine for deck-plan updates.
> - For the **bias preset**: bump weights that would have prevented
>   the pilot's exploits. Be conservative — single-digit weight changes,
>   not wholesale rewrites. If a weakness needs a NEW knob (e.g. "Bed
>   priority weight"), add the field to `_DEFAULTS` first, then use it.
>
> **Constraints**:
> - Don't break existing tests. Run `PYTHONPATH=. python -m pytest
>   tests/test_minecraft_tcg.py -q` after edits to verify.
> - Don't modify ALL presets — only the one the pilot beat (`<ai-bias>`).
> - Output a brief summary of changes you made (file + section + nature
>   of edit). Don't repeat the full diff.

### 3. Save iteration outputs

After each iteration, save:
- `logs/mc_ultra_pilot_iter<N>.md` (copy of pilot report)
- `logs/mc_ultra_coach_iter<N>.txt` (coach's summary)

### 4. After all iterations: progression report

After all `--iterations` rounds, summarize:

- **Win/loss progression**: did the pilot win more often as iterations
  passed? (If the AI is improving from coach patches, late wins should
  be harder than early wins.)
- **Strategy doc growth**: new bullets added per iteration.
- **Heuristic preset evolution**: which weights were bumped, by how much.
- **Quality check**: did the pilot's reports actually surface NEW
  insights, or did they re-litigate things already documented? (If the
  same insight comes up 3x, the strategy doc isn't working — flag it.)

## Notes

- This is interactive. The user runs it once and watches the loop.
- Each iteration takes ~5-10 minutes (pilot game + coach + tests).
- 3 iterations = ~30 minutes runtime.
- The pilot can lose. That's fine — losing reveals AI strengths and
  drives coach updates that benefit the heuristic side.
- If the pilot wins all N games, increase difficulty: switch `--ai-bias`
  to `wall_grinder` or `workers` and re-run.
- The strategy doc + bias preset are committed to git after the loop
  finishes (one commit, message summarizing the progression).
