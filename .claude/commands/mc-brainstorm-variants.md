---
description: Brainstorm new MC AI bias presets via subagent, then evaluate them in the variant tournament. Discovery-mode strategy search.
argument-hint: [--num-variants N] [--games N] [--out PATH]
---

# /mc-brainstorm-variants — subagent-driven strategy search for Minecraft

The user wants to discover new AI strategies for the Minecraft TCG that
beat (or complement) the existing presets. You orchestrate a subagent
that designs new bias presets, then run the variant tournament to
empirically evaluate them.

## Arguments

User invoked with: `$ARGUMENTS`

Defaults if unspecified:
- `--num-variants 6` — how many new presets to brainstorm.
- `--games 4` — games per pair per deck in the evaluation tournament.
- `--out logs/mc_brainstorm_TIMESTAMP.json` — variant file path.

## Workflow

### Step 1 — Spawn brainstorm subagent

Use the `Agent` tool with `subagent_type=general-purpose`. The agent is
a strategy designer with access to the codebase. Brief it like a
colleague who hasn't seen this conversation:

> You're designing AI bias presets for the Minecraft TCG variant
> tournament. Each preset is a dict that overrides the default AI's
> scoring weights and selection modes for card-picking, mining,
> attacking, and blocking.
>
> Read these files to learn the schema:
>   - `src/ai/minecraft_adapter.py` — `_DEFAULTS` (every knob and its
>     default), `_ATTACK_PRIORITY_TABLES`, `MC_BIAS_PRESETS` (existing
>     presets you should NOT duplicate).
>   - `logs/mc_variants_expanded.json` — most recent tournament with
>     12 variants. Read the `aggregated.ranking` to see what's
>     winning and losing.
>
> Design **N** new bias presets (N from the user's --num-variants flag,
> default 6) that:
>
>   1. Each express a coherent strategic hypothesis (NOT random weight
>      tweaks — pick a strategy and tune the weights to it).
>   2. Differ meaningfully from `passive_econ`, `wall_grinder`,
>      `workers`, `balanced` (the current top variants).
>   3. Have a one-sentence rationale explaining the hypothesis.
>
> Strategy ideas to consider (don't be limited to these):
>   - Anti-meta: counter `passive_econ` (chump-block stalling). What
>     punishes a player who chump-blocks everything? Aerial mobs that
>     can't be ground-blocked? Direct face-damage through actions?
>   - Hybrids: mix two existing axes (e.g. ramp's economy + wall_grinder's
>     attack pattern, or workers' early game + iron_rush's late closer).
>   - Off-axis: try strategies on knobs we haven't varied much. Block
>     mode "chump_anything" only appears in passive_econ. Block mode
>     "never" only appears in iron_rush/avatar_burn. What about a
>     defensive-pivot strategy?
>   - Card-axis specialists: a "tools-and-weapons" deck that prioritizes
>     equipping the avatar (high mc_attack tools) over deploying mobs.
>     A "structure-stack" that piles turn-bonus structures.
>
> Output format: write a single JSON file with this shape:
>
> ```json
> {
>   "version": 1,
>   "generated_by": "claude-code-subagent",
>   "rationale_summary": "<2-3 sentences on the overall design space>",
>   "variants": {
>     "<name1>": {
>       "rationale": "<one sentence>",
>       "preset": {
>         "selection_mode": "weighted|random|largest",
>         "worker_bonus_under_3": <int>,
>         "worker_bonus_first": <int>,
>         "turnbonus_struct_bonus": <int>,
>         "explore_map_bonus": <int>,
>         "strip_mine_bonus": <int>,
>         "find_diamonds_bonus": <int>,
>         "chop_trees_bonus": <int>,
>         "untap_worker_bonus": <int>,
>         "nether_expedition_bonus": <int>,
>         "tutor_bonus": <int>,
>         "draw_bonus": <int>,
>         "early_big_mob_penalty": <int>,
>         "late_big_mob_bonus": <int>,
>         "mining_mode": "premium_first|wood_first|iron_first|redstone_first|diamond_first|random",
>         "mine_wood_first_when_pending": <bool>,
>         "attack_priority": "bed_first|avatar_first|structure_first|block_first|random",
>         "block_mode": "auto|never|chump_anything"
>       }
>     },
>     ...
>   }
> }
> ```
>
> Save the file to the path the orchestrator specified (`--out` value
> or `logs/mc_brainstorm_<timestamp>.json`). Use the `Write` tool.
>
> Then print a short summary listing each variant name and rationale.
> Don't repeat the full JSON in your response — just confirm the path
> you wrote to.

### Step 2 — Validate the JSON

Read the saved file. For each variant, confirm:
- It has both `rationale` and `preset` keys.
- The `preset` dict's `selection_mode`, `mining_mode`, `attack_priority`,
  `block_mode` values are in the legal sets.
- Every numeric weight is an integer.

If validation fails, ask the subagent to fix it (one retry max).

### Step 3 — Run the variant tournament

```
PYTHONPATH=. python scripts/play/variant_tournament.py \
    --engine minecraft \
    --variants-file <PATH_FROM_STEP_1> \
    --variants <new_names>,balanced,passive_econ,wall_grinder,workers,random,fully_random \
    --games <user --games or 4> \
    --max-turns 35 \
    --out logs/mc_brainstorm_tournament_<timestamp>.json
```

Include the brainstormed variant names alongside benchmarks
(`balanced`, `passive_econ`, `wall_grinder`, `workers`, `random`,
`fully_random`). The user wants to see if any new variant beats the
current top (`passive_econ` at 42.4%), AND whether any beats `random`
by less than 5pts (which would mean the variant isn't expressing real
strategic content).

### Step 4 — Report findings

After the tournament finishes, summarize:

1. **Top 3 ranking** with winrates and rationales. Mark new vs benchmark.
2. **Did anyone beat `passive_econ` (42.4% baseline)?** If yes, that's a
   real format discovery.
3. **Did any new variant fail to beat `random` by 5+ points?** Those
   are weak strategies — the subagent's hypothesis didn't express
   real strategic difference. Note them.
4. **One "interesting matchup"** — a head-to-head pair where the result
   was unexpected (e.g. anti_passive beats passive_econ but loses to
   random — what does that mean?).
5. **Suggested next iteration**: which winning variant deserves further
   investment (lean weights harder, design more cards) and which
   losing variants suggest a dead end.

Output a tight markdown summary, not a JSON dump.

## Notes

- This is not fire-and-forget. The user runs it interactively and
  reads the brainstorm + report.
- The subagent should NOT modify the `MC_BIAS_PRESETS` dict directly —
  output JSON only. The tournament loads the JSON via `--variants-file`.
- If the tournament errors out (engine bug surfaced), report the error
  but don't try to fix it on this turn — the brainstormer's mistake.
- Total expected runtime: ~5-15 minutes (1 min subagent + variant
  tournament time scales with variant count).
