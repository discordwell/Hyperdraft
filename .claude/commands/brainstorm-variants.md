---
description: Brainstorm new AI bias presets for any engine via subagent, then evaluate them in the variant tournament. Discovery-mode strategy search.
argument-hint: [--game <name>] [--num-variants N] [--games N] [--out PATH]
---

# /brainstorm-variants — discovery-driven AI strategy search

Spawn a subagent that designs new bias presets for the named game's
heuristic AI, then run the variant tournament to see which beat the
existing benchmarks. Engine-agnostic and schema-discovery driven —
the subagent learns the legal preset schema from the engine's AI
adapter rather than carrying a hardcoded list of knobs.

## Arguments

User invoked with: `$ARGUMENTS`

- `--game <name>` (optional — see "Game inference" below if omitted)
- `--num-variants N` (default 6) — how many new presets to design.
- `--games N` (default 4) — games per pair per deck in the tournament.
- `--out PATH` (default `logs/<game>_brainstorm_<timestamp>.json`).

### Game inference (when `--game` is omitted)

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

## Workflow

### 0. Pre-flight discovery

Before spawning the subagent:

1. Confirm `src/ai/<game>_adapter.py` exists. Halt if not.
2. Find the bias-preset registry. Pattern: `<UPPER>_BIAS_PRESETS` dict
   in the adapter file. If absent, halt: "Engine `<game>` has no
   `*_BIAS_PRESETS` registry — variant tournament needs presets to
   compare against."
3. Find the `_DEFAULTS` (or equivalent) dict that defines every legal
   knob and its default. The subagent will read this to learn the
   schema.
4. Locate the most recent variant-tournament log under `logs/` matching
   `<game>` — gives the subagent prior winrates so its hypotheses are
   informed by the meta. Optional; absence is fine.
5. Confirm `scripts/play/variant_tournament.py` accepts `--engine
   <game>`. Run `python scripts/play/variant_tournament.py --help` and
   check the `--engine` choices. If `<game>` isn't in the list, halt:
   "variant_tournament.py doesn't have an entry for `<game>`. Add an
   `ENGINES[<game>] = ...` config block before brainstorming."

Print:

```
=== /brainstorm-variants pre-flight ===
game:           <game>  (inferred or supplied)
adapter:        src/ai/<game>_adapter.py
preset registry: <UPPER>_BIAS_PRESETS  (existing: name1, name2, ...)
schema source:  <UPPER>_DEFAULTS  (or ad-hoc — note location)
recent log:     logs/<game>_*.json  (or "none")
==> spawning brainstorm subagent...
```

### 1. Spawn brainstorm subagent

Use `Agent` tool with `subagent_type=general-purpose`. Brief:

> You're designing AI bias presets for the `<game>` engine's variant
> tournament. Each preset is a dict that overrides the default AI's
> scoring weights and selection modes.
>
> Read these files to learn the schema:
>   - `src/ai/<game>_adapter.py` — the `<UPPER>_DEFAULTS` dict (every
>     knob and its default value), the `<UPPER>_BIAS_PRESETS` dict
>     (existing presets — DO NOT duplicate), and any priority tables
>     or enum-typed fields.
>   - `<MOST_RECENT_LOG_PATH>` if it exists — read the
>     `aggregated.ranking` to see what's currently winning and losing.
>     If absent, you have less information about the meta but more
>     freedom; design more diverse hypotheses to compensate.
>
> Design **N** new bias presets (N from --num-variants, default 6) that:
>
>   1. Each express a coherent strategic hypothesis (NOT random weight
>      tweaks — pick a strategy and tune the weights to match it).
>   2. Differ meaningfully from existing presets.
>   3. Have a one-sentence rationale explaining the hypothesis.
>
> Generic strategy axes worth exploring (instantiate per the engine's
> mechanics — e.g. "ramp" might mean "mana acceleration" in MTG, "draw
> energy fast" in Pokemon, "stack workers" in Minecraft):
>
>   - **Anti-meta**: counter the current top preset. What
>     punishes its dominant strategy?
>   - **Hybrids**: mix two existing axes.
>   - **Off-axis**: try strategies on knobs that haven't been varied
>     much — read the existing presets to see which fields are always
>     set the same way, then deliberately deviate.
>   - **Archetype specialists**: a preset that doubles down on one
>     card-type or one win condition (tools-only, structures-only,
>     swarm-only, etc.).
>
> Output format: write a single JSON file at `<OUT_PATH>` with this
> shape:
>
> ```json
> {
>   "version": 1,
>   "game": "<game>",
>   "generated_by": "claude-code-subagent",
>   "rationale_summary": "<2-3 sentences on the design space you explored>",
>   "variants": {
>     "<name1>": {
>       "rationale": "<one sentence>",
>       "preset": { /* every key from <UPPER>_DEFAULTS, with explicit values */ }
>     },
>     ...
>   }
> }
> ```
>
> The `preset` dict must include EVERY key from `<UPPER>_DEFAULTS`
> (the tournament merges over defaults but explicit values are
> easier to audit). Validate before saving:
>   - All enum-typed values (e.g. `selection_mode`, `mining_mode`,
>     `attack_priority`, `block_mode`) are in their legal sets — read
>     the adapter to find them.
>   - Every numeric weight is the right type (int vs float).
>   - Every key from `<UPPER>_DEFAULTS` is present.
>
> Save with `Write`. Then print a short summary listing each variant
> name and rationale. Don't repeat the JSON.

### 2. Validate the saved JSON

Read the file. For each variant, confirm:
- `rationale` and `preset` keys present.
- Every `<UPPER>_DEFAULTS` key appears in the preset.
- Enum-valued fields are in their legal sets (compare against the
  adapter source).

If validation fails, ask the subagent to fix it (one retry max). On
second failure, halt — broken JSON would silently corrupt the
tournament.

### 3. Run the variant tournament

```
PYTHONPATH=. python scripts/play/variant_tournament.py \\
    --engine <game> \\
    --variants-file <OUT_PATH> \\
    --variants <new_names>,<all_existing_preset_names> \\
    --games <games> \\
    --max-turns 35 \\
    --out logs/<game>_brainstorm_tournament_<timestamp>.json
```

Always include ALL existing presets as benchmarks (read them from
`<UPPER>_BIAS_PRESETS`'s keys), plus `random` / `fully_random` if the
engine defines them. The user wants to see whether new variants beat
the meta AND whether they meaningfully differ from random play (a
variant that doesn't beat random by ≥5pts isn't expressing real
strategic content).

### 4. Report findings

Tight markdown:

1. **Top 3 ranking** with winrates and rationales. Mark new vs benchmark.
2. **Did anyone beat the previous-best preset?** That's a real meta
   discovery.
3. **Did any new variant fail to beat `random` by 5+ points?** Those
   are weak strategies — flag the failing hypothesis.
4. **One "interesting matchup"** — head-to-head pair where the result
   was unexpected.
5. **Suggested next iteration**: which winning variant deserves
   investment, which losing ones are dead.

## Notes

- Interactive command. User runs it and reads the report.
- Subagent does NOT modify `<UPPER>_BIAS_PRESETS` directly — output
  JSON only. The tournament loads via `--variants-file`. If a winning
  variant deserves promotion, the user (or a follow-up command) edits
  the adapter to register it.
- If the tournament errors out, report the error but don't fix it on
  this turn — that's likely the brainstormer's mistake (illegal value)
  or an engine bug surfaced under unusual weights, both of which
  deserve a separate investigation.
- Total runtime: ~5–15 minutes (1 min subagent + tournament time
  scales with variant count).
- This skill is sometimes invoked from `/new-game-plus` as part of an
  extended polish pass when the user wants to widen the AI strategy
  search beyond a single LLM-pilot training loop.
