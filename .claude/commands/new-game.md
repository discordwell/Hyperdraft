---
description: Build a complete new game engine + frame + first card set, fully tested. Fire-and-forget — auto-picks defaults and runs without asking.
argument-hint: <theme> [--engine NAME] [--code XXXX] [--cards 150] [--max-cycles 10]
---

# /new-game — pipeline for a new game engine + first set

You drive a multi-stage pipeline that produces a new game (rules engine + AI adapter + frontend frame) and a first card set ready to play. **Fire-and-forget mode**: pick reasonable defaults, announce them, run for 4–12 hours without blocking on user input.

## Arguments

The user invoked this with: `$ARGUMENTS`

- **`theme`** (required, free-form): drives mechanics, aesthetic, and engine philosophy. e.g. `"submarine fleet"`, `"haunted carnival"`, `"trains and steam"`.
- **`--engine NAME`** (optional): override the auto-picked engine name (snake_case).
- **`--code XXXX`** (optional): override the auto-picked first-set code (3–4 uppercase letters).
- **`--cards N`** (optional, default 150): target card count for the first set.
- **`--max-cycles N`** (optional, default 10): balance-loop revision cap.
- **`--games-per-pairing N`** (optional, default 50): tournament games per archetype matchup.

If `theme` is missing, ask once for it. Otherwise **never block on user input** — auto-pick everything else.

## Operating mode: fire-and-forget

**This command does NOT call AskUserQuestion. Ever.** It does not ask "OK to start?", does not ask for clarification mid-pipeline, does not ask for permission to commit. It announces decisions in plain text and proceeds. The user can interrupt at any time by typing a message — the orchestrator notices the interruption on its next thinking step.

If a stage hits a genuine blocker (e.g. ChatGPT not logged in for stage 5), the orchestrator picks the documented fallback (e.g. `--mode local` placeholder art) and logs that it did so. Halting and waiting is reserved for cases where every fallback also fails.

Use `TaskCreate` to track every stage. Mark `in_progress` when starting and `completed` when done. Spawn subagents in parallel where independent.

## Pre-flight (auto-pick defaults, ANNOUNCE, do NOT ask)

Pick all of the following deterministically. Print one 5-line status block, then immediately start stage 0.

| Decision | Auto-pick rule |
|---|---|
| **Engine name** (`<engine>`) | If `--engine` provided, use it. Else: take the first noun in the theme, lowercase, snake_case (drop articles, common adjectives). e.g. `"submarine fleet"` → `submarine`; `"haunted carnival"` → `carnival`; `"trains and steam"` → `trains`. If the theme is too abstract for a clean noun, take a 1-word evocative descriptor. |
| **Set code** (`<CODE>`) | If `--code` provided, use it. Else: first 4 letters of the engine name, uppercased. Verify no collision against `src/cards/set_registry.py`'s `SETS` dict. On collision, append digit (e.g. `SUBM` → `SUB2`). |
| **File layout** | New engines always use the split-file layout: `src/cards/<engine>/<set_module>/<archetype>.py` per archetype + aggregating `__init__.py`. (`mtg-custom` is the only single-file engine, and `/new-game` never targets it.) |
| **Card count** | `--cards` flag value, default 150. |
| **Cycles cap** | `--max-cycles` flag value, default 10. |
| **Subagent model** | All Opus by default. The user's CLAUDE.md notes Sonnet is acceptable for >5-parallel runs but defaults to Opus for quality. |

Engine name is reused as paths:
- `src/engine/<engine>.py`, `<engine>_combat.py`, `<engine>_turn.py`
- `src/ai/<engine>_adapter.py`
- `src/cards/<engine>/`
- `frontend/src/games/<engine>.tsx`
- `frontend/src/hooks/use<Engine>Game.ts` (PascalCase for the hook name)
- `assets/card_art/<engine>/`
- `mode="<engine>"` in `Game()` constructor

Status announcement format (one block, no questions, no waiting):
```
=== /new-game pre-flight ===
theme:       <theme>
engine:      <engine>
first set:   <CODE>
cards:       <N>
max cycles:  <K>
estimated:   4–12h, fully unattended
==> starting stage 0...
```

Then create tasks and begin.

## Stages

### Stage 0 — Engine plan

Spawn one Plan agent. Brief:

> Design a brand-new card-game engine themed `<theme>`. Output a markdown design doc at `docs/games/<engine>.md` containing:
>
> 1. **Win condition**: how a player wins/loses. Be concrete (life total, deck-out, objective control, etc.).
> 2. **Turn structure**: phases in order, what each phase allows. Default to MTG-style (untap → upkeep → draw → main → combat → main → end) or a deliberate departure with rationale.
> 3. **Resource model**: how players pay for cards. (Mana? Energy attachment? Material accumulation? Per-turn currency? Multi-resource?)
> 4. **Zones**: hand, library/deck, battlefield/board, graveyard/discard, exile/banished, plus any engine-specific zones (e.g. minecraft's "column" combat lanes, pokemon's "active" / "bench").
> 5. **Combat math**: damage flow, attack/block model, special combat rules (overflow? lanes? simultaneous?). If non-MTG, give a worked example showing a turn of combat resolving step-by-step.
> 6. **Card types**: the canonical card-type taxonomy (creature/spell/structure/etc.).
> 7. **Engine capabilities**: what kinds of effects the engine must natively support so cards can express interesting rules. (ETB triggers? Static effects? Activated abilities? Replacement effects? Stack? List explicitly.)
> 8. **AI difficulty model**: how the AI's "easy / medium / hard" levels differ behaviorally.
> 9. **Comparison with existing engines**: 3–5 lines on how this differs from MTG / Pokemon / YGO / Hearthstone / Minecraft engines already in the repo, and which one it most resembles.
>
> Read `src/engine/__init__.py`, `src/engine/types.py`, and one existing per-engine module (e.g. `src/engine/minecraft.py`) to understand engine-shape conventions before designing.

After it returns, verify `docs/games/<engine>.md` exists and the win condition is unambiguous.

### Stage 1 — Engine scaffold (parallel)

Spawn **four agents in parallel** (single message, multiple `Agent` tool calls):

#### Agent 1 — `src/engine/<engine>.py`
Brief:
> Implement the core game-state module for the `<engine>` engine following `docs/games/<engine>.md`. Patterns to mirror from `src/engine/minecraft.py`:
> - Define `<Engine>State` extending GameState if needed, or extend the existing `GameState` with engine-specific fields.
> - Implement zone setup, draw, basic mulligan if applicable.
> - Provide a `setup_<engine>_player(game, player, deck)` entry point.
> - Define a `<Engine>ModeAdapter(GameModeAdapter)` subclass in this file (or import + register one in `src/engine/mode_adapter.py`) that overrides only the hooks where this engine's behavior differs from MTG defaults.
>
> Do not implement combat or turn structure here — those go in their own modules (Agents 2 and 3 are working on them in parallel; do not edit those files).

#### Agent 2 — `src/engine/<engine>_combat.py`
Brief:
> Implement combat for the `<engine>` engine following `docs/games/<engine>.md`. Patterns to mirror from `src/engine/minecraft_combat.py` (column-based) and `src/engine/combat.py` (MTG attacker/blocker). Provide a `<Engine>CombatManager` class with at minimum: `declare_attackers`, `declare_blockers`, `assign_damage`, `resolve_combat`. Export the manager + any helper enums/dataclasses.
>
> Do not edit `<engine>.py` or `<engine>_turn.py`.

#### Agent 3 — `src/engine/<engine>_turn.py`
Brief:
> Implement the turn manager for the `<engine>` engine following `docs/games/<engine>.md`. Patterns to mirror from `src/engine/minecraft_turn.py` and `src/engine/hearthstone_turn.py`. Provide a `<Engine>TurnManager(TurnManager)` class with `setup_game`, `run_turn`, and per-phase helpers. Wire it to call into the combat manager (`<engine>_combat`) at the appropriate phase.
>
> Do not edit `<engine>.py` or `<engine>_combat.py`.

#### Agent 4 — `src/ai/<engine>_adapter.py`
Brief:
> Implement an AI adapter for the `<engine>` engine following `docs/games/<engine>.md`'s AI difficulty model. Patterns to mirror from `src/ai/hearthstone_adapter.py` and `src/ai/minecraft_adapter.py`. Provide a `<Engine>AIAdapter(difficulty: str)` class with the methods the engine's turn manager will call (typically: `choose_action`, `choose_attackers`, `choose_blockers`, `mulligan_decision`).
>
> The implementation should be heuristic at this stage — no LLM hookups. The "hard" tier should make non-trivial value judgements (don't just attack with everything).
>
> Do not edit any engine file directly; if you need a hook the engine doesn't expose yet, comment a `# TODO: needs <hook> from engine` line and skip it.

After all four return, write a smoke test that runs an AI-vs-AI game with placeholder cards (a minimal CardDefinition pool of 6–10 vanilla cards) and asserts:
1. The game completes within 60 turns.
2. Both AIs make at least one non-no-op decision.
3. Some win condition fires (it doesn't end in a 60-turn timeout).

Write this to `tests/test_<engine>_smoke.py`. Run it. **Do not fix it inline — pass it to stage 1.5.**

### Stage 1.5 — Post-parallel reconciliation (LOAD-BEARING)

The 4 parallel agents in stage 1 each wrote one module without seeing each other's code. The depths run discovered the canonical drift case: AI agent returned dataclass actions, turn manager expected dicts. Stage 1's smoke test caught it; without this stage, that's the agent's job under emergency-fix conditions, which is more expensive than catching it deliberately.

Spawn one Agent (general-purpose). Brief:

> You are the post-parallel reconciliation agent for a freshly built game engine. The 4 parallel agents in stage 1 each wrote one of: `src/engine/<engine>.py`, `src/engine/<engine>_combat.py`, `src/engine/<engine>_turn.py`, `src/ai/<engine>_adapter.py`. None of them saw the others' final code; the smoke test at `tests/test_<engine>_smoke.py` may be failing. Your job: find and fix the contract drift that caused the failure (or proactively fix near-misses if the test passes by luck).
>
> Specifically check:
> 1. **Action contract** — does the AI return the same shape the turn manager dispatches on? (Common drift: dataclass vs dict.)
> 2. **Method-name contract** — does the turn manager call AI methods that the AI actually implements? (Compare `tm.depths_ai_handler.choose_X` vs the AI's actual method names.)
> 3. **Combat manager init signature** — does the turn manager construct the combat manager with the same args the combat module expects?
> 4. **Engine-state field references** — combat / turn / AI all read fields from `state.players[id].<field>` and `obj.state.<field>`. Verify the field names actually exist where Agent 1 declared them.
> 5. **EventType enum coverage** — every event the combat / turn / AI files emit exists in `src/engine/types.py` (Agent 1's responsibility) AND has a handler somewhere.
> 6. **AI-handler dispatch by player_id** — does `set_ai_handler` accept a `player_id=` kwarg? Are different per-player handlers actually consulted?
>
> Goal: get `tests/test_<engine>_smoke.py` passing without weakening assertions. The fix may be on any of the 4 files (or on the smoke test if it made wrong assumptions about an agent's API). Write a brief reconciliation report listing the drifts found and how each was fixed.

After this agent returns, re-run the smoke test. If it still fails, that's a real engine problem (not contract drift) — let the same agent take a second pass at the failing assertion.

This stage is short (~15 minutes) but high-leverage — every drift caught here saves an hour of debugging in the set-side stages 7–8 where the failure would surface as zero-play cards in coverage analysis.

### Stage 2 — Frame (frontend)

Spawn one Agent. Brief:

> Build the React frontend frame for the `<engine>` engine. Output:
>
> - `frontend/src/games/<engine>.tsx` — the main game-board component. Mirror `frontend/src/games/minecraft.tsx` for layout patterns. Render: each player's resources, zones, card area, and any engine-specific UI elements from `docs/games/<engine>.md`. Use the existing styling vocabulary from sibling game components (don't introduce new design systems).
> - `frontend/src/hooks/use<Engine>Game.ts` — the data hook that wraps the game-state socket connection. Mirror `frontend/src/hooks/useMinecraftGame.ts`.
> - Update `frontend/src/games/registry.ts` to include the new engine.
>
> Style: read `CLAUDE.md` and the `frontend-design` skill if it's available. Aesthetic should reflect the theme `<theme>`.
>
> Do not start the dev server; the user will wet-test it manually after the pipeline finishes.

After it returns, run `cd frontend && npm run build` to confirm the build passes. If it fails, fix root causes (likely typecheck errors in the new component).

### Stages 3–9 — Delegate to /new-set

The new engine is now ready. Delegate the rest of the pipeline to `/new-set`'s logic. Read `.claude/commands/new-set.md` and follow stages 3–9 from there, with these substitutions:

- `engine` arg → the new engine name from pre-flight
- `theme` arg → the same theme passed to `/new-game`
- `--cards N` → forwarded
- `--max-cycles N` → forwarded
- `--games-per-pairing N` → forwarded

The set label / set code chosen by the stage-3 planner should be the **first set** of this engine — typically `<ENGINE>` or `<ENGINE>1` or a flavorful one-word code from the theme.

## Final report

After /new-set's stage 9 completes, append a "Pipeline summary" section to `docs/games/<engine>.md` with:

- Engine module paths
- AI adapter location + difficulty model summary
- Frontend frame location
- First-set artifacts (delegated to /new-set's report — link to `docs/sets/<set>.md`)
- One-line "how to play": the user-facing command/route to actually run a game
- Outstanding TODOs in the engine (any `# TODO:` comments left by Agent 4, etc.)

Then a short status message to the user.

## Notes for the orchestrator

- **Engine ↔ set boundary**: keep stage 1 strictly engine-shape and stage 4 strictly card-shape. If a card needs a hook the engine doesn't expose, the right move is to ADD the hook to the engine (a small targeted edit) rather than weaken the card. But don't speculate — only add hooks driven by concrete card needs.
- **Stage-2 wet test**: skipped per project convention. The user will wet-test the frontend after the pipeline. Do NOT prompt them to do so — the final report mentions it once and moves on.
- **No mid-pipeline commits.** Stages produce on-disk artifacts only. The orchestrator does not call `git commit` or prompt the user to commit anywhere in stages 0–9. The final report (stage 9) lists everything that changed and a single "ready to commit" line; the user types `commit` themselves when they're back at the keyboard.
- **No mid-pipeline AskUserQuestion.** If a stage-internal decision arises (planner produces something edge-case, smoke test reveals a bug), the orchestrator picks the documented default and logs the decision in the design doc / stage report. Do not block.
