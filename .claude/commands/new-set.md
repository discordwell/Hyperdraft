---
description: Build a complete new card set in an existing engine (cards + art + decks + tests + balance loop). Fire-and-forget — auto-picks defaults and runs without asking.
argument-hint: <engine> <theme> [--code XXXX] [--cards 150] [--max-cycles 10]
---

# /new-set — pipeline for a new card set in an existing engine

You drive a multi-stage pipeline that produces a fully tested card set. **Fire-and-forget mode**: pick reasonable defaults, announce them, run for 1–3 hours without blocking on user input. Stages 4 and 8 spawn parallel subagents and run multi-game tournaments.

## Arguments

The user invoked this with: `$ARGUMENTS`

- **`engine`** (required): one of `mtg-custom`, `minecraft`, `pokemon`, `yugioh`, `hearthstone`, `scp`. Determines:
  - Where cards live (`src/cards/<engine>/<set>/` or `src/cards/custom/<set>.py` for `mtg-custom`).
  - Which engine modules to use for AI-vs-AI testing.
  - Which `__init__.py` / `set_registry.py` `wire_set.py` edits.
- **`theme`** (required): free-form, e.g. `"deep-sea pirates"`, `"haunted carnival"`. Drives mechanics + art style.
- **`--code XXXX`** (optional): override the auto-picked set code (3–4 uppercase letters).
- **`--cards N`** (optional, default 150): target card count. Range 120–200.
- **`--max-cycles N`** (optional, default 10): balance-loop revision cap.
- **`--games-per-pairing N`** (optional, default 50): tournament games per archetype matchup.

If `engine` or `theme` is missing or invalid, ask once. Otherwise **never block on user input** — auto-pick everything else.

## Operating mode: fire-and-forget

**This command does NOT call AskUserQuestion. Ever.** It does not ask "OK to start?", does not ask for clarification mid-pipeline, does not ask for permission to commit. It announces decisions in plain text and proceeds. The user can interrupt at any time by typing a message.

If a stage hits a genuine blocker, pick the documented fallback and log it. Halting and waiting is reserved for cases where every fallback also fails.

## Pre-flight (auto-pick defaults, ANNOUNCE, do NOT ask)

Pick all of the following deterministically. Print one status block, then immediately start stage 3.

| Decision | Auto-pick rule |
|---|---|
| **Engine validation** | Must be one of `mtg-custom`, `minecraft`, `pokemon`, `yugioh`, `hearthstone`, `scp`. If invalid, ask once for correction. |
| **Set code** (`<CODE>`) | If `--code` provided, use it. Else: 3–4 uppercase letters derived from the theme (e.g. `"deep-sea pirates"` → `PIRT`, `"haunted carnival"` → `CARN`). Verify no collision against `src/cards/set_registry.py`'s `SETS` dict. On collision, append digit. |
| **Set module name** | snake_case slug derived from the theme (e.g. `"deep-sea pirates"` → `deep_sea_pirates`). Used as the directory/file name. |
| **File layout** | Determined by engine: `mtg-custom` → single file `src/cards/custom/<set_module>.py`. All others → directory `src/cards/<engine>/<set_module>/` with one file per archetype + aggregating `__init__.py`. |
| **Card count** | `--cards` flag value, default 150. |
| **Cycles cap** | `--max-cycles` flag value, default 10. |

**Deck-label naming convention** (LOAD-BEARING — `balance_loop.py` and `coverage.py` filter on this):

Stage 6 builds starter decks and stage 8 runs the tournament. **Every deck label MUST start with `<SET_CODE>_`.** Examples for `PIRT`:
- ✓ `PIRT_aggro`, `PIRT_control`, `PIRT_combo`, `PIRT_midrange`
- ✗ `aggro_pirate`, `pirate_aggro`, `pirates_aggro` — these don't match the filter and the analyzer reports empty `card_scores` → loop fails fast with an explicit error.

The tournament's `card_scores` keys are `<DECK_LABEL>::<Card Name>`. `domain_matches_set` accepts exact set-code match OR `<SET>_*` prefix. Deviating from the convention makes the balance loop blind to the set's data.

Status announcement format (one block, no questions, no waiting):
```
=== /new-set pre-flight ===
engine:      <engine>
theme:       <theme>
set code:    <CODE>
set module:  <set_module>
cards:       <N>
max cycles:  <K>
estimated:   1–3h, fully unattended
==> starting stage 3...
```

Then create tasks and begin.

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
- `.claude/skills/spice-pass.md` — overlaps with stage 8's revision agent; if it covers the engine you're working in, reuse its prompt. **Note its FORBIDDEN section**: never auto-generate `_<set>_s<N>_*` / median-lift / thin-bust stubs, never wire effects that don't match printed text, never emit info-pulse events (SCRY/SURVEIL/MILL/LIFE_CHANGE) as depth filler. Depth/quality metrics are diagnostics, not targets.
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

### Stage 4.5 — Post-parallel reconciliation (LOAD-BEARING)

Parallel agents working from the same design doc can still produce subtly incompatible interfaces — the canonical example from the depths run was AI agents returning dataclass actions while the turn manager expected dicts. The original 4 agents couldn't catch this because none of them owned both ends of the contract. This stage exists specifically to find those gaps before they cause silent failures in stages 7–8.

Spawn one Agent (general-purpose). Brief:

> You are the post-parallel reconciliation agent for a freshly built card set. The N parallel archetype agents in stage 4 each wrote one file from `docs/sets/<set_label>.md` without seeing each other's code. Your job: find and fix interface mismatches between their outputs (and between their outputs and the engine).
>
> Specifically check:
> 1. **Card-to-card collisions** — same card name in two files (the design doc shouldn't allow it, but verify).
> 2. **Helper-import drift** — agents importing the same helper with different argument shapes; agents reinventing helpers that already exist in `src/cards/interceptor_helpers.py`.
> 3. **Event payload-key drift** — different agents using different keys for the same conceptual payload (e.g. one uses `target_id`, another uses `target`).
> 4. **Cross-file references** — Card A in archetype X references "your other card B" by name; verify B exists with the expected interface.
> 5. **Smoke test** — write a 30-line probe that imports every card, instantiates each via `game.create_object`, and runs each `setup_interceptors` (if any) without raising. This catches argument-shape errors that pure import doesn't.
> 6. **Engine-side contracts** — every event your cards emit (DEPTHS_DIVE, ATTACH, DAMAGE, etc.) should have a handler in the engine. Cross-reference card emit calls against engine handlers; flag emit-without-handler pairs as `# RECONCILE TODO`.
>
> Output: a brief patch + a list of any contract drifts you couldn't fix unilaterally (those become work for stage 4.7).

This stage is short (~15 minutes of compute) but high-leverage — every issue caught here saves an hour of debugging in stages 7–8.

### Stage 4.7 — Engine-gap closure

The card-impl agents in stage 4 each report `# TODO:` markers when a card needs an engine primitive that doesn't exist (`QUERY_COST`, prevention shields, EOT keyword grants, etc.). Without addressing these, those cards become silent no-ops, which downstream shows up as zero-play cards in the stage 8 coverage check and skews the balance loop into "fixing" cards that aren't actually broken.

Aggregate the `# TODO:` markers from all stage-4 archetype files (grep is fine: `grep -rn "# TODO:" src/cards/<engine>/<set_module>/`). Cluster them by missing engine primitive. Then:

- **If the cluster is small (≤3 cards affected)**: leave the TODOs. Document them in `docs/sets/<set_label>.md` under "known engine gaps". The cards will be zero-play; stage 8's balance loop will report this honestly.
- **If the cluster is large (≥4 cards affected) AND the engine primitive is bounded (≤200 LOC, no architectural change)**: spawn one Agent to add the primitive to the relevant engine module. Brief includes: the missing primitive's expected signature, the cards that need it, the engine file to extend, and a smoke test asserting the primitive works.
- **If the primitive is unbounded** (requires architecture changes — new pipeline phase, new zone, etc.): leave it for a follow-up `/new-game` rev or a manual engineering pass. Document loudly in `docs/sets/<set_label>.md`.

Skip this stage entirely if stage 4 produced fewer than 5 total `# TODO:` markers. The cost-benefit only flips when there's enough downstream noise to warrant the engine work.

### Stage 5 — Card art (placeholder pass — real art is a post-pipeline follow-up)

**Pipeline policy**: stage 5 always runs `art_harness --mode local` to produce procedural placeholder PNGs. The placeholders are deterministic per card name + category and let stages 7 (smoke test) and 8 (balance loop) run with `image_url` wired through the engine. The "real" art (browser-automated ChatGPT generation, or eventually direct OpenAI API calls when the user has budget) is offered as a one-time prompt in stage 9, after the rest of the pipeline finishes.

This keeps fire-and-forget honest: the user gets a complete, testable, playable set without their browser session being a hard prerequisite of the unattended run.

#### Per-engine import paths (use these in commands below)

| Engine        | Cards module path                              | Style module path                                |
|---------------|------------------------------------------------|--------------------------------------------------|
| `mtg-custom`  | `src.cards.custom.<set_module>`                | `src.cards.custom.<set_module>_style`            |
| `minecraft`   | `src.cards.minecraft.<set_module>`             | `src.cards.minecraft.<set_module>.style`         |
| `pokemon`     | `src.cards.pokemon.<set_module>`               | `src.cards.pokemon.<set_module>.style`           |
| `yugioh`      | `src.cards.yugioh.<set_module>`                | `src.cards.yugioh.<set_module>.style`            |
| `hearthstone` | `src.cards.hearthstone.<set_module>`           | `src.cards.hearthstone.<set_module>.style`       |
| `scp`         | `src.cards.scp.<set_module>`                   | `src.cards.scp.<set_module>.style`               |

(`mtg-custom` is single-file, so its style is a sibling `<set_module>_style.py` rather than a submodule. All others use the directory-with-submodules layout from stage Pre-flight.)

#### Run the harness in local mode

Substitute the cards / style paths from the table above (note: `<engine>/` segment matches the engine subdir):

```bash
python -m scripts.new_set.art_harness \
    --style <STYLE_MODULE_PATH> \
    --cards <CARDS_MODULE_PATH>:<SET>_CARDS \
    --out-dir assets/card_art/<engine>/<set_module> \
    --mode local
```

This produces N deterministic placeholder PNGs (procedural color blocks per category). Smoke test + balance loop don't care that they're placeholders — the engine's `image_url` wiring works on existence, not aesthetic quality.

Real art (browser-automated ChatGPT, or eventually direct OpenAI API calls when the user has billing budget) is offered as a one-time prompt in stage 9 — NOT here. Do NOT spawn the browser-automation agent in this stage.

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

### Stage 7.5 — Per-card effect verification (LOAD-BEARING)

The smoke test in Stage 7 only validates that the engine boots and the AI completes a game. It does **not** verify that each card actually does what its text claims. Skipping straight to Stage 8 (tournament / balance) means the loop chases "this deck is bad" results that are really "this card does nothing." The Finance ultra-loop iter 1–3 found 20 distinct bugs that this stage would catch: cards whose `resolve` is never invoked (e.g. Correlation Matrix's `DRAW` was wired through `card_def.resolve` while the engine only checked `cast_effect`), wrong `InterceptorPriority` (leverage power query returned `TRANSFORM`-priority while `get_power` only iterates `QUERY`), text/code drift (Hidden Aggression printed `+4/+0` while code applied `+2/+0`), helper functions with off-by-one (multi-attacker alpha checked `count==1` before all attackers were declared), and oneshot routing gaps (Dark Pool Orders skipped staging entirely and resolved to graveyard).

Two sub-stages. Both gate Stage 8.

#### 7.5a — Card-text / code drift check (cheap, structural)

Spawn one general-purpose agent. Brief:

> For each card in `src/cards/<game>/<set_module>/`, compare the printed `text` field against the code that registers the effect:
>
> 1. Extract numerals from `text` matching common patterns: `\+(\d+)/\+(\d+)` (P/T mods), `draw (\d+|a) cards?`, `deal (\d+) damage`, `gain (\d+) life`, `Arbitrage (\d+)`, `Leverage (\d+)`, etc. Assert the matching code constant equals the parsed value. Mismatches go in the punch list.
> 2. Extract canonical keyword phrases from text (`Alpha Strike`, `Trample`, `Vigilance`, `Arbitrage N`, etc.) and assert each is granted by the card's `keywords=` field or by an interceptor it registers.
> 3. Flag any text clause that names an effect (`draw`, `deal damage`, `destroy`, `create token`) where no code path on that card emits the corresponding `EventType`.
>
> Output a single test file `tests/test_<set>_text_drift.py` containing one assertion per card it could check; print a summary `<N> cards checked, <K> drift failures` and list the failures by name. Cards with effects too complex to parse heuristically go in a `SKIPPED_CARDS` dict at the top with a one-line reason — surface them, don't silently exclude.

Run the generated drift test. **Halt the pipeline if any drift failure is found** — drift is fixable in-place (~5 min per card) and contaminates every downstream stage.

#### 7.5b — Interceptor / effect-firing verification

Invoke the existing `/test-interceptors` skill with `--game <engine> --set <CODE> --fail-on-empty --out tests/test_<set>_interceptors.py`. The skill reads card defs, generates one unit test per card that fires the card's **own canonical trigger** and asserts a **text-matching** `EventType` is emitted, then runs them under strict mode (`HYPERDRAFT_STRICT=1 HYPERDRAFT_STRICT_STACK=1`). Follow that command's methodology exactly — a "deal damage" card must emit DAMAGE, NOT a generic SCRY/SURVEIL/MILL/LIFE_CHANGE info-pulse; "some event fired" is not a pass.

> ⛔ **No slice-N median-lift stubs.** It is FORBIDDEN to make this stage (or
> the Stage 8 depth/quality numbers) pass by auto-generating `_<set>_s<N>_*` /
> "median-lift" / "thin-bust" helpers that wire cards to emit generic info-pulse
> events unrelated to their printed text — and equally forbidden to edit a
> card's text to match a convenient stub. That is the exact pattern that shipped
> ~16 broken sets. Every wired effect must implement the card's actual text. A
> keyword/stat-only card stays vanilla. See `.claude/skills/spice-pass.md`.

**Decision gate**:

| Pass rate | Action |
|---|---|
| ≥ 90% | Proceed to Stage 8 |
| 70%–90% | Spawn a fixer agent on the top 5 failures, re-run once, then proceed if ≥ 70% |
| < 70% | Halt with a report — the engine or card pool needs structural work before tournament cycles waste resources |

The fixer agent gets the failure list and the relevant card source files. Brief: "categorize each failure (empty-effect / wrong-effect / trigger-never-fires / engine-gap), fix what you can in cards, escalate engine gaps to a punch list in `engine_gaps.md`. Re-run `tests/test_<set>_interceptors.py` after edits. Don't loosen assertions to make tests pass."

#### 7.5c — Fire verification: does the AI ever USE the card? (LOAD-BEARING for payoffs)

7.5a and 7.5b verify a card **does the right thing when triggered**. They do NOT verify the AI **ever triggers it**. These are different gates, and the second one has no other coverage: a card that scores well in design review, carries a non-trivial `value_hint`, and leaves the Stage-8 tournament "in-band" can still be completely inert — and a tournament whose marquee cards never fire produces balance numbers for a board they never touched.

This is not hypothetical. The SCP verb-redesign (2026-05-29) shipped 6 signature activated abilities that passed every effect gate (`/test-interceptors` green) yet fired ~never in real games — uncalibrated value-gating put them below the fire threshold, a missing turn-reset made each one silently once-per-game, and a 1-of payoff lost every deploy race. Every per-archetype "tournament in-band" gate validated a board where the marquee mythic was a dead facility. It went unnoticed for ~9 commits because nothing asserted the fire path.

So: for the deck's **signature / payoff / build-around cards** (finishers, engines, activated-ability "bombs" — not vanilla filler), verify they actually FIRE under the AI:

- Run **`/card-fire-debug --card "<name>"`** for each payoff card (or batch). It walks the six-step tree — drawn → deployed/legal → value-scored above threshold → precondition met → cost payable → out-competes the turn's other plays — and names the exact blocker plus a patch location.
- `/card-fire-debug` supports Pokemon and SCP today. If your engine isn't wired in yet, the cheap stand-in is to **instrument the card's play/activation event across a Stage-8 tournament and assert each payoff card fires ≥ 1×** in self-play. A payoff card that fires zero times across the tournament fails this gate.

**The rule (codify it):** "scores well in review", "has a non-trivial `value_hint`", and "the deck is tournament-in-band" are **NOT** fire gates — every one of them is satisfiable while the card is inert. Only a real-loop assertion that the card actually fired counts. Any new autonomous behavior (the AI plays X / activates Y) needs this gate from its first commit, not after N archetypes ship on faith.

#### Why three sub-stages?

- **Drift check (7.5a)** catches text/code mismatches (cheap, deterministic, parser-driven). 5-minute fixes; would have caught Hidden Aggression in 1s.
- **Interceptor verification (7.5b)** catches "wired but does nothing" — the depths trap, where ~30% of generated cards historically register an interceptor whose `effect_fn` returns `[]`. CLAUDE.md notes ~736 of 2,486 wired MTG cards across 12 sets currently fall into this bucket.
- **Fire verification (7.5c)** catches "works, but the AI never uses it" — the inert-payoff trap, invisible to both checks above because the effect IS correct; it just never runs.

Together they close the gap between "smoke test passed" and "the cards actually work *and get played*." Without 7.5a/b, every Stage 8 tournament result is contaminated by silent-failure cards; without 7.5c, the tournament's headline cards may be dead and the balance data is for a board that never existed. And every LLM-pilot iteration in `/ultra-loop` (which `/new-game-plus` invokes downstream) burns hours rediscovering the same bugs through gameplay.

### Stage 8 — Capability-audit + multi-agent fix loop (up to 3 cycles, parallel within each cycle)

**Replaces the old "tournament → balance_loop → revise flagged cards" cycle.** That logic only ever dispatched card-stat revisions, which can't fix the dominant failure modes — AI omissions (the AI never plays Doctrines, never detects, never lays Mines), engine omissions (cards that need primitives the engine doesn't expose), and structural archetype weakness (a 0% deck can't be saved by per-card tweaks). The audit-driven loop diagnoses the actual root cause and dispatches the right specialist agent.

#### Tournament runner per engine

| Engine        | Runner | Notes |
|---|---|---|
| `mtg-custom`  | `scripts/play/custom_set_tournament.py` | Native shape; extend to emit `ai_action_counts` + `mechanic_triggers` if not present |
| `minecraft`   | `scripts/play/custom_set_tournament.py` with depths-style adapter | |
| `pokemon` / `yugioh` / `hearthstone` / new engines | `scripts/new_set/_adapters/<engine>_tournament_adapter.py` (mirror `depths_tournament_adapter.py`) | Must emit the extended JSON contract below |
| `scp`         | `scripts/new_set/_adapters/scp_tournament_adapter.py` | Must emit extended JSON contract |

#### Tournament JSON contract (extended)

```
{
  "set_summary":       { ... },              // existing
  "matchup":           { ... },              // existing
  "card_scores":       { ... },              // existing — keys are <DECK_LABEL>::<Card>
  "ai_action_counts":  { "<ACTION_TYPE>": int, ... },   // NEW — per-action-type tournament total
  "mechanic_triggers": { "<MECHANIC_NAME>": int, ... }, // NEW — named mechanic trigger counts
  "available_actions": [ "<ACTION_TYPE>", ... ],        // NEW — universe of legal actions
  "card_errors":       { "<Card>": "trace excerpt", ... }, // NEW (optional) — cards that crashed
  "engine_todo_clusters": [ ... ]                       // NEW (optional) — clusters from stage 4.7
}
```

The depths adapter at `scripts/new_set/_adapters/depths_tournament_adapter.py` is the reference implementation.

#### Audit loop pseudocode

```
for cycle in 1..3:
    1. Run engine-specific tournament with the set's archetype decks.
       Output: logs/balance_<set>_round_<cycle>.json

    2. Run coverage analyzer (unchanged):
       python -m scripts.new_set.coverage --tournament <json> --set <SET> \
           --card-list /tmp/<set>_cardlist.txt --out logs/coverage_<cycle>.json
       If zero-play cards exist, run a force-include round before metrics.

    3. Run capability audit:
       python -m scripts.new_set.capability_audit \
           --tournament <json> --set <SET> \
           --archetypes <a1>,<a2>,<a3>,<a4> --cycle <cycle> \
           --out logs/audit_<set>_cycle_<cycle>.json
       Exit 0 = no actionable findings (converged). Exit 2 = fixes needed.

    4. If converged → done, break.

    5. Else: parse the findings JSON. Group findings by `fix_dispatch`.
       Dispatch up to N parallel agents IN A SINGLE MESSAGE (one per
       distinct fix_dispatch + scope unit):

         ai_extension       → 1 agent  (consolidates all ai_omission findings)
         engine_extension   → 1 agent per missing primitive
         card_revision      → 1 agent per affected archetype file
         archetype_redesign → 1 agent per flagged archetype
         mechanic_repair    → 1 agent per dead-end mechanic
         card_repair        → 1 agent per crashing card

       Each agent gets the relevant findings' `fix_brief` field as its
       prompt seed PLUS the file scope it's allowed to touch. Run them
       in parallel (single tool-use message with multiple Agent calls).

    6. Regression test pass:
       python tests/test_<engine>_smoke.py
       python tests/test_<set>.py
       If anything broke (engine smoke OR set smoke fails), spawn one
       test-fix agent with the failure output. It must restore green
       without weakening assertions; if it can't, REVERT the cycle's
       changes (git stash) and continue to next cycle with the
       unchanged code, logging the failure in the audit changelog.

    7. Append cycle changelog to docs/sets/<set>.md: cycle number,
       findings dispatched, fixes applied, regression status.

    8. Re-tournament + re-audit on the next cycle iteration.
```

#### Critical guardrails

- **Do NOT modify `balance_loop.py` or `capability_audit.py`** — they are engine-agnostic by design. Adapters and per-engine logic live elsewhere.
- **Anything-goes scope is real.** A cycle's fix can touch `src/engine/`, `src/ai/`, `src/cards/`, the design doc, even types.py. The regression-test pass + revert mechanism is what makes this safe.
- **Parallel within a cycle, sequential across cycles.** This is intentional — within-cycle fixes are usually orthogonal (ai_extension and archetype_redesign don't overlap), but the regression test must validate them together before the next round.
- **Cap at 3 cycles by default.** The audit can churn if fixes uncover new findings; 3 cycles is enough for the dominant problems. Past 3, ship with the residual findings logged in stage 9's report.

### Stage 9 — Final report + art follow-up prompt

#### 9a. Append the pipeline summary

Append a "Pipeline summary" section to `docs/sets/<set>.md` containing:
- Final card count and archetype distribution
- Mechanic list (final, after revisions)
- Balance trajectory: per-cycle archetype winrates and number of cards revised
- Coverage final: % of cards with cast ≥ 1
- Outstanding flags (low-sample cards, archetypes still outside band, never-in-deck)
- Engine TODOs surfaced by stage 4.7 that were left for follow-up
- Pointers to all artifacts (cards module, decks, art dir, smoke test, design doc)

#### 9b. Art follow-up prompt (the ONLY AskUserQuestion in this command)

The pipeline shipped placeholder PNGs (stage 5 ran `--mode local`). Now that the user is presumably back at the keyboard reading the report, ask **once** whether they want to upgrade to real art:

```
AskUserQuestion: "Generate real card art now?"
options:
  - "Browser-automate ChatGPT (free, ~30s/card, needs your Chrome session logged in)"
  - "OpenAI image API (fast but billed — flag this when you have budget)"
  - "Skip — placeholders are fine for now"
```

- If user picks "Browser-automate": spawn the claude-in-chrome agent with the harness in `--mode manual` (writes draw_prompts.json), then drive ChatGPT one card at a time, saving PNGs into `assets/card_art/<engine>/<set_module>/`. Cap at 3 retry rounds for gaps.
- If user picks "API": run `art_harness --mode api` (requires `OPENAI_API_KEY` in env). Honor the user's saved-memory note about hard billing limits — if a 401/429 is hit, halt and report.
- If user picks "Skip" (or doesn't answer within their attention window): done. Placeholder PNGs stay; user can re-run art via `python -m scripts.new_set.art_harness ...` whenever they want.

#### 9c. CI pre-flight + text-vs-events gate (a set is NOT done until this passes)

**Definition of done — both must hold before you signal commit-readiness:**

1. **Strict text-vs-events verification passes.** Every wired card must pass
   the Stage-7.5b `/test-interceptors` run in strict mode
   (`HYPERDRAFT_STRICT=1 HYPERDRAFT_STRICT_STACK=1`) with **text-matching**
   events — a "deal damage" card emitting only `SCRY` is a FAIL, not a pass.
   If you relaxed 7.5b's gate to ship, you are not done. Re-run it here as the
   final gate; do not declare the set done on a green smoke test alone.
2. **Depth/quality was not gamed.** If you ran a depth report
   (`custom_set_depth_report.py`) during balancing, its numbers must come from
   real, text-matching effects — NOT from info-pulse filler. The scorer now
   text-gates the Asymmetry axis, so a stub can't move the median; but also
   confirm by eye that no `_<set>_s<N>_*` / median-lift / thin-bust helpers
   exist in the set module (`grep -rn '_s[0-9]\+_\|median.lift\|thin.bust' src/cards/<engine>/<set_module>/` should return nothing).

Then run `scripts/ci_quick.sh <engine>` from repo root (e.g. `scripts/ci_quick.sh depths`). This catches the recurring CI-redness pattern: untracked source files imported by tracked code, stale TS types, and missing `requirements-server.txt` deps — none of which the per-stage tests notice.

- If it passes, include `ci_quick: <engine> passed` in the final report and proceed to 9d.
- If the untracked-imports check fails, `git add` the flagged files and re-run.
- If a test failure surfaces, fix it (or log it as an Outstanding TODO and report `ci_quick: blocked` instead of `ready to commit`). Do NOT auto-add `.gitignore` entries to silence the check.

#### 9d. Status message to user

A short final message summarizing what shipped, with a single "ready to commit" line (only if 9c passed). The user types `commit` themselves when ready (per their global CLAUDE.md).

## Notes for the orchestrator

- **Don't run /new-game's stages 0–2.** This command assumes the engine already exists. If the user clearly meant a new engine, log a note in the design doc and suggest `/new-game` to them in the final report — but don't block the pipeline asking.
- **Card-art stage cost**: ChatGPT-driven art for 150 cards is slow but free relative to the OpenAI API (which hits hard billing limits per user's saved memory). If browser automation fails (no logged-in ChatGPT session), fall back to `--mode local` (procedural placeholders). Log the fallback in the design doc; the user can re-run stage 5 separately later.
- **Tournament throughput**: for non-MTG engines, the per-engine stress-test script under `scripts/stress/` may emit a different JSON shape than `custom_set_tournament.py`. Write the adapter at `scripts/new_set/_adapters/<engine>_tournament_adapter.py` to convert to the `{set_summary, matchup, card_scores}` shape before feeding `balance_loop.py`. Do NOT modify `balance_loop.py` — engine-agnostic by design.
- **No mid-pipeline commits.** Stages produce on-disk artifacts only. The orchestrator does not call `git commit` or prompt the user to commit anywhere in stages 3–9. The final report (stage 9) lists everything that changed and a single "ready to commit" line; the user types `commit` themselves when they're back at the keyboard.
- **No mid-pipeline AskUserQuestion.** If a stage-internal decision arises (planner produces something edge-case, smoke test reveals a bug, balance loop hits cycle 10 without converging), pick the documented default and log the decision in the design doc. Do not block.
