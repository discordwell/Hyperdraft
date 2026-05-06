---
description: Build a complete new card set in an existing engine (cards + art + decks + tests + balance loop).
argument-hint: <engine> <theme> [--cards 150]
---

# /new-set — pipeline for a new card set in an existing engine

You are about to drive a multi-stage pipeline that produces a fully tested
card set. **This is compute-intensive and may take 1–3 hours of wall time.**
Stages 4 and 8 spawn parallel subagents and run multi-game tournaments.

## Arguments

The user invoked this with: `$ARGUMENTS`

Parse them as:

- **`engine`** (required): one of `mtg-custom`, `minecraft`, `pokemon`, `yugioh`, `hearthstone`. Determines:
  - Where cards live (`src/cards/<engine>/<set>/` or `src/cards/custom/<set>.py` for `mtg-custom`).
  - Which engine modules to use for AI-vs-AI testing.
  - Which `__init__.py` / `set_registry.py` `wire_set.py` edits.
- **`theme`** (required): free-form, e.g. `"deep-sea pirates"`, `"haunted carnival"`. Drives mechanics + art style.
- **`--cards N`** (optional, default 150): target card count. Range 120–200.
- **`--max-cycles N`** (optional, default 10): balance-loop revision cap.
- **`--games-per-pairing N`** (optional, default 50): tournament games per archetype matchup.

If the user did not supply enough args (no engine or no theme), STOP and ask before starting.

## Pre-flight (do this BEFORE creating any tasks)

Before kicking off 1–3 hours of compute, do this validation pass:

1. **Validate engine.** Must be one of: `mtg-custom`, `minecraft`, `pokemon`, `yugioh`, `hearthstone`. If the user typed something else, suggest the closest match and stop.

2. **Decide set code + set label.** Pick a 3–4 letter uppercase code (e.g. `PIRT` for "deep-sea pirates"). The set code IS the set label — it's used as the registry key, the tournament `_card_ref` domain prefix, and the smoke-test `<set_label>` argument. Avoid collisions: read `src/cards/set_registry.py` first to make sure the code isn't taken.

3. **Decide file layout** based on engine:
   - `mtg-custom` → single file `src/cards/custom/<set_module>.py` (matches existing pattern: `lorwyn_custom.py`, `temporal_horizons.py`, etc.). Card archetypes are organized by section comments in one module, not separate files. Stage 4 still spawns parallel agents — they coordinate by section/line ranges in the same file via merge-friendly edits.
   - All other engines → directory `src/cards/<engine>/<set_module>/` with one file per archetype (matches minecraft: `alpha.py`, `phyrexia.py`, `horror.py`) plus an aggregating `__init__.py`. Stage 4 agents own one file each — no merge concerns.

4. **Deck-label naming convention** (LOAD-BEARING — `balance_loop.py` and `coverage.py` filter on this):

   When stage 6 builds the starter decks and stage 8 runs the tournament, **every deck label MUST start with `<SET_CODE>_`**. Examples for set code `PIRT`:
   - ✓ `PIRT_aggro`, `PIRT_control`, `PIRT_combo`, `PIRT_midrange`
   - ✗ `aggro_pirate`, `pirate_aggro`, `pirates_aggro` — these do not match the set filter and the analyzer will report empty `card_scores` → loop fails fast with an explicit error.

   The tournament's `card_scores` keys are `<DECK_LABEL>::<Card Name>`, and `domain_matches_set` accepts either an exact set-code match (single mirror pool) or `<SET>_*` prefix (per-archetype pools). Deviating from this convention makes the entire balance loop blind to the set's data.

4. **Confirm with user.** Print a 4-line summary: engine / theme / set code / card count / max cycles / estimated wall time, and ask **"OK to start?"** before creating any tasks. Estimated wall time:
   - 150 cards × manual ChatGPT art (~30s/card) ≈ 75 min just for stage 5
   - 50 games × C(archetypes, 2) pairings × 10 cycles ≈ 1–2 hours for stage 8
   - Plus 30–60 min for planning + impl + revision
   - **Total: 3–5 hours typical** (longer if balance does not converge early)

Only after the user confirms do you proceed to stage 3 below.

## How to drive this pipeline

You are the **orchestrator**. Your job is to:

1. Use `TaskCreate` to add tasks for each stage below.
2. Mark each task `in_progress` when starting it and `completed` when done.
3. Spawn subagents (`Agent` tool) for stages that need them, **in parallel** when their work is independent.
4. Use the helper scripts in `scripts/new_set/` for non-LLM work.
5. After every stage, check the artifact actually exists before continuing.

**Save context**: when subagents return, capture only the actionable summary (paths produced, flags raised). Don't paste back card lists or stack traces unless something failed.

## Repository conventions you must follow

Read these once at start so subagents can be briefed accurately:

- `CLAUDE.md` — top-level project conventions, set list, helper inventory.
- `.claude/skills/implement-mtg-cards.md` — the canonical card-implementation pattern (interceptors, helpers, test recipe). Cite this in every stage-4 subagent prompt.
- `.claude/skills/spice-pass.md` — overlaps with stage 8's revision agent; if it covers the engine you're working in, reuse its prompt.
- `src/cards/minecraft/` — exemplar of the per-engine "split into archetype files" layout you should mirror (`alpha.py` / `phyrexia.py` / `horror.py` + aggregating `__init__.py`).
- `scripts/play/custom_set_tournament.py` — the MTG-engine tournament runner whose JSON output `scripts/new_set/balance_loop.py` consumes. Other engines have their own runners under `scripts/play/` and `scripts/stress/` — check there first.

## Stages

### Stage 3 — Set plan
*(Stages 0–2 are `/new-game` only. This command starts at 3.)*

Spawn one Plan agent. Brief:

> Design a card set for the **`<engine>`** engine themed `<theme>`. Output a markdown design doc at `docs/sets/<set_label>.md` containing:
> - 3–5 mechanics (named, with one-paragraph rules text each, plus rationale for why it fits the theme)
> - 4 archetypes (one per faction/color/element of the engine) — each with strategy summary, key cards, and a one-line gameplay loop
> - A card list of exactly **N** cards (where N is the `--cards` value, default 150) distributed across archetypes. Each row: `name | type | cost/resources | P/T-or-analog | archetype | one-line rules text`
> - Per-set art style preamble (the equivalent of phyrexian's `STYLE_HEADLINE` + `CATEGORY_FLAVORS`) — concrete enough that a single visual style is dictated. Cover at least these categories: creature/mob, spell/action, structure/artifact, weapon/equipment, boss/legend.
> - Set code (3-4 letters uppercase) and set label.
>
> Read `CLAUDE.md` and the existing sets under `src/cards/<engine>/` to ensure mechanics interlock with engine capabilities. Reject mechanics that need engine work the engine doesn't already support.

After it returns, verify `docs/sets/<set_label>.md` exists, set code is established, and N matches `--cards`.

### Stage 3.5 — Style module

The art harness consumes a Python style module. Extract the style preamble from the design doc and write it to:
- `src/cards/<engine>/<set_module>/style.py` for split-file engines
- `src/cards/custom/<set_module>_style.py` for `mtg-custom`

The module must define:
- `STYLE_HEADLINE: str` — the lead paragraph applied to every prompt
- `CATEGORY_FLAVORS: dict[str, str]` — per-category second-paragraph blurb

`categorize(card) -> str` is optional. The default categorizer maps `CardType.CREATURE → "creature"`, `INSTANT/SORCERY → "spell"`, `ARTIFACT → "artifact"`, `ENCHANTMENT → "enchantment"`, `LAND → "land"`, `PLANESWALKER → "planeswalker"`, falling back to `"object"`.

**Override `categorize` when the engine has custom CardType enums.** Specifically:
- `minecraft`: handle `CardType.MC_MOB`, `MC_TOOL`, `MC_STRUCTURE`, `MC_BLOCK`, `MC_ACTION` (see `scripts/phyrexian_overworld/generate_card_art.py:111-142` for the exemplar `_category` function).
- `pokemon`: handle `CardType.POKEMON`, `TRAINER`, `ENERGY` (or whatever the pokemon module uses).
- `yugioh`: handle monster / spell / trap distinctions.
- `hearthstone`: minion / spell / weapon / hero are usually fine via the default mapping but verify against `src/cards/hearthstone/`.

Write the style module directly via the Write tool — it's small (~50–80 lines) and doesn't need a subagent.

### Stage 4 — Card implementation (parallel)

For each archetype in the design doc, spawn one Agent (general-purpose). Run **all archetype agents in parallel** (single message, multiple `Agent` tool calls).

Brief each agent:

> Implement the cards in archetype **`<archetype>`** from `docs/sets/<set_label>.md`.
>
> Output to `src/cards/<engine>/<set>/<archetype_slug>.py` (or `src/cards/custom/<set>_<archetype>.py` for `mtg-custom`). Export a dict named `<ARCHETYPE>_CARDS = {…}` keyed by card name → CardDefinition.
>
> Follow the patterns in `.claude/skills/implement-mtg-cards.md`. Use only helpers that already exist in `src/cards/interceptor_helpers.py` (or the engine's equivalent). Do not edit any file outside your archetype's own module.
>
> Stay strictly within your archetype's card list — do not implement any card claimed by another archetype. The orchestrator is running you in parallel with sibling agents on other archetypes.
>
> When done, write a one-line summary: `<archetype> archetype: K cards implemented; M used X helper, N used Y helper`.

After all agents return, write the aggregating `src/cards/<engine>/<set>/__init__.py` that imports each archetype dict and merges them into a single `<SET>_CARDS` dict. Also import any deck builders the agents wrote.

### Stage 5 — Card art

This stage has two sub-steps:

#### Per-engine import paths (use these in commands below)

| Engine        | Cards module path                              | Style module path                                |
|---------------|------------------------------------------------|--------------------------------------------------|
| `mtg-custom`  | `src.cards.custom.<set_module>`                | `src.cards.custom.<set_module>_style`            |
| `minecraft`   | `src.cards.minecraft.<set_module>`             | `src.cards.minecraft.<set_module>.style`         |
| `pokemon`     | `src.cards.pokemon.<set_module>`               | `src.cards.pokemon.<set_module>.style`           |
| `yugioh`      | `src.cards.yugioh.<set_module>`                | `src.cards.yugioh.<set_module>.style`            |
| `hearthstone` | `src.cards.hearthstone.<set_module>`           | `src.cards.hearthstone.<set_module>.style`       |

(`mtg-custom` is single-file, so its style is a sibling `<set_module>_style.py` rather than a submodule. All others use the directory-with-submodules layout from stage Pre-flight.)

#### 5a. Write the prompt pack

Substitute the cards / style paths from the table above:

```bash
python -m scripts.new_set.art_harness \
    --style <STYLE_MODULE_PATH> \
    --cards <CARDS_MODULE_PATH>:<SET>_CARDS \
    --out-dir assets/card_art/<set_module> \
    --mode manual
```
This writes `assets/card_art/<set>/draw_prompts.json` — a JSON list of `{card, filename, prompt}` for every card.

#### 5b. Browser-automate ChatGPT to generate images
Spawn one Agent (general-purpose) with the **claude-in-chrome MCP tools loaded** (see `ToolSearch` for `mcp__claude-in-chrome__*`). Brief it:

> Drive ChatGPT (https://chatgpt.com) to generate an image for every entry in `assets/card_art/<set>/draw_prompts.json`.
>
> For each entry: open a fresh ChatGPT conversation in a new tab, paste the `prompt` field, wait for the image to render, save the resulting PNG to `assets/card_art/<set>/<filename>` at 1024×1024 (resize / center-crop if needed).
>
> Verify the user's ChatGPT session is logged in by calling `mcp__claude-in-chrome__tabs_context_mcp` first. If not, halt with instructions for the user.
>
> Report any cards that failed to generate. The pipeline can re-run this stage to fill gaps — the harness in --mode manual already skips entries whose PNG exists.

If the agent reports gaps, re-run 5a (it will only re-emit prompts for missing PNGs) and re-spawn 5b. Cap at 3 rounds before flagging the gaps and continuing.

### Stage 6 — Starter decks

Spawn one Agent. Brief:

> Build 2–4 starter decks for `<set_label>`, one per archetype from the design doc. Each deck should be 30–60 cards depending on the engine's convention. Use cards from `<set>_CARDS` only, plus any required basic resources (lands / energy) the engine needs.
>
> Output: deck builder functions in `src/cards/<engine>/<set>/decks.py` (or wherever the engine puts its starter decks). Each function returns a `list[CardDefinition]`. Register them in the engine's starter-decks dict if it has one.
>
> Decks must be playable — each archetype's gameplay loop from the design doc should be expressible by the deck.

### Stage 7 — Wire + smoke test

Run the wire_set helpers via Bash:

```bash
# For mtg-custom:
python -m scripts.new_set.wire_set register-mtg \
    --code <CODE> --name "<Set Name>" --module <set_module> \
    --registry-var <SET>_CARDS --custom

# For non-MTG engines:
python -m scripts.new_set.wire_set register-engine \
    --engine <engine> --module <set> --registry-var <SET>_CARDS

# Always (use the cards module path from the table in stage 5):
python -m scripts.new_set.wire_set scaffold-test \
    --set-label <SET> --import-path <CARDS_MODULE_PATH> \
    --registry-var <SET>_CARDS \
    --decks "<archetype1>:<builder1>,<archetype2>:<builder2>"
```

Then run the smoke test:
```bash
python tests/test_<set>.py
```

If it fails, fix the root cause (don't loosen the assertions). Common failures: a card definition missing `setup_interceptors` for a card with substantive rules text → fix the card, not the test.

### Stage 8 — Balance loop (up to `--max-cycles`, default 10)

**Tournament runner per engine** (run from `<repo_root>`):

| Engine        | Runner                                                   | Emits target JSON shape? |
|---------------|----------------------------------------------------------|--------------------------|
| `mtg-custom`  | `scripts/play/custom_set_tournament.py`                  | YES — direct input to `balance_loop.py` |
| `minecraft`   | `scripts/play/custom_set_tournament.py` with `--decks` for the new set's archetypes | YES — same script, different decks |
| `pokemon`     | `scripts/stress/stress_test_pokemon.py`                  | NO — write a small adapter (10–20 lines) emitting `{set_summary, card_scores}` from its anomaly-format output |
| `yugioh`      | `scripts/wet/wet_test_ygo_bvb.py` (or build a tournament wrapper) | NO — write adapter |
| `hearthstone` | `scripts/stress/stress_test_hearthstone.py`              | NO — write adapter |

For engines without a native tournament runner emitting the right JSON, place the adapter at `scripts/new_set/_adapters/<engine>_tournament_adapter.py`. It should:
1. Run N games via the engine's existing AI-vs-AI driver
2. Track per-card cast/in_play/winning_side via the engine's event log (mirror `_collect_card_stats` in `custom_set_tournament.py`)
3. Emit `{set_summary, matchup, card_scores}` to the same output path
**Do not modify `balance_loop.py`** — it is engine-agnostic by design.

Pseudocode:

```
for cycle in 1..max_cycles:
    1. Run engine-specific tournament with the new set's archetype decks.
       Output: logs/balance_<set>_round_<cycle>.json
       (See the table above for the right runner per engine.)

    2. Run coverage analyzer:
       python -m scripts.new_set.coverage \
           --tournament logs/balance_<set>_round_<cycle>.json \
           --set <SET_LABEL> \
           --card-list /tmp/<set>_cardlist.txt \
           --out logs/coverage_<set>_round_<cycle>.json

    3. If coverage report shows zero-play cards, run a force-include
       round (build a deck per zero-play card via
       scripts.new_set.coverage.build_force_include_spec, run K games
       each, merge results into the tournament JSON before metrics).

    4. Run balance analyzer:
       python -m scripts.new_set.balance_loop \
           --tournament <merged_json> --set <SET_LABEL> \
           --archetypes <a1>,<a2>,<a3> --cycle <cycle> \
           --max-cycles <max_cycles> \
           --out logs/balance_<set>_flags_<cycle>.json
       Exit 0 = converged, exit 2 = revisions needed.

    5. If converged → done, break.

    6. Else: spawn one Agent (general-purpose). Brief it with the flags
       JSON. Instruct it to revise flagged cards (cost ±, P/T ±, text
       simplification) in the appropriate archetype module file. Append
       a changelog entry to docs/sets/<set>.md describing each change
       and its rationale.

    7. After agent returns, re-run smoke test (stage 7's pytest); fix
       failures before proceeding to next cycle.
```

### Stage 9 — Final report

Append a "Pipeline summary" section to `docs/sets/<set>.md` containing:
- Final card count and archetype distribution
- Mechanic list (final, after revisions)
- Balance trajectory: per-cycle archetype winrates and number of cards revised
- Coverage final: % of cards with cast ≥ 1
- Outstanding flags (low-sample cards, archetypes still outside band, never-in-deck)
- Pointers to all artifacts (cards module, decks, art dir, smoke test, design doc)

Also write a short status message to the user summarizing what shipped.

## Notes for the orchestrator

- **Don't run /new-game's stages 0–2.** This command assumes the engine already exists. If the user clearly meant a new engine, suggest `/new-game` instead.
- **Card-art stage cost**: ChatGPT-driven art for 150 cards is slow but free relative to the OpenAI API (which hits hard billing limits per user's saved memory). Don't fall back to `--mode api` without confirming with the user.
- **Tournament throughput**: for non-MTG engines, the per-engine stress-test script under `scripts/stress/` may emit a different JSON shape than `custom_set_tournament.py`. If so, write a small adapter that converts to the `{set_summary, matchup, card_scores}` shape before feeding `balance_loop.py`. Don't modify `balance_loop.py` itself — it is engine-agnostic by design.
- **Each stage commits**: after each stage completes successfully, suggest committing what was produced. The user generally says "commit" → push remote (per their global CLAUDE.md). Confirm before pushing.
