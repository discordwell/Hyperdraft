# Hyperdraft Architecture

This document orients a new contributor to the overall shape of Hyperdraft. It is intentionally high-level; for card-implementation mechanics see [`CLAUDE.md`](./CLAUDE.md) and the deeper design notes in [`docs/hyperdraft-architecture.md`](./docs/hyperdraft-architecture.md).

## A. System Overview

Hyperdraft is a four-mode digital TCG platform supporting Magic: The Gathering, Hearthstone, Pokemon TCG, and Yu-Gi-Oh!. The backend is a Python rules engine paired with a FastAPI + Socket.IO server (`src/server/main.py`, port 8030). The frontend is a React + TypeScript + Vite client (`frontend/`). All four game modes share one event-driven engine core but specialize it via mode-specific turn managers, combat managers, and resource systems.

## B. Core Philosophy

> "Everything is an Event. Everything else is an Interceptor on that event."

Every state change in the game — a creature dying, a card being drawn, a player gaining life — is emitted as an `Event` through the `EventPipeline` (`src/engine/pipeline.py`). Cards, keywords, replacement effects, static auras, and even state-based actions are expressed as `Interceptor`s that watch the stream and intervene.

### Pipeline phases

Each event flows through `EventPipeline._process_single` (pipeline.py:56) in this order:

1. **TRANSFORM** — interceptors can rewrite the event (e.g. "damage doubled," "if you would draw, draw two instead"). Runs in timestamp order.
2. **PREVENT** — interceptors can cancel the event (e.g. Divine Shield, "prevent all damage"). May emit side-effect events such as `DIVINE_SHIELD_BREAK`.
3. **RESOLVE** — the event actually mutates state (`_resolve_event`). Produces follow-on events (e.g. `ZONE_CHANGE` producing an `ETB` arrival).
4. **REACT** — triggered abilities fire here (ETBs, death triggers, "whenever you cast..."). These queue new events onto the same emit loop.
5. **CLEANUP** — `_cleanup_departed_interceptors` removes `while_on_battlefield` interceptors for objects that just left the battlefield.

**REACT runs before CLEANUP on purpose.** Death triggers need the dying object's interceptors to still be alive when they fire. Only the timestamp of an interceptor registration determines fire order — there is no layer system. The pipeline guards against runaway chains via `max_iterations` (default 1000).

## C. Directory Map

| Path | Purpose |
|---|---|
| `src/engine/` | The rules engine: events, interceptors, pipeline, turn managers, combat, mana/energy, stack, priority, targeting, queries. |
| `src/cards/` | Card catalog. Real MTG sets from Scryfall at top level; fan-made interceptor-bearing sets under `custom/`; mode-specific catalogs under `hearthstone/`, `pokemon/`, `yugioh/`. |
| `src/cards/interceptor_helpers.py` | The card-building DSL (`make_etb_trigger`, `make_static_pt_boost`, etc.). |
| `src/cards/ability_bundles.py` | Reusable trigger + effect bundles (e.g. ETB token, death deal-damage) composed from interceptor helpers. |
| `src/cards/text_render.py` | Rules-text rendering used alongside the bundle helpers. |
| `src/ai/` | AI decision-making. Shared `engine.py`/`evaluator.py`/`heuristics.py` plus MTG `strategies/` and per-mode adapters. |
| `src/server/` | FastAPI + Socket.IO server. `main.py` is the ASGI entry; `session.py` is the per-game orchestrator; `routes/` exposes REST endpoints; `services/` holds cross-cutting helpers. |
| `frontend/` | React + TypeScript + Vite + Tailwind client. `src/components/game/` holds per-mode boards; `src/stores/` holds Zustand stores; `src/hooks/` holds reusable game-state hooks. |
| `tests/` | Python test suites. Run directly with `python tests/<file>.py` (non-MTG suites do not use pytest). |
| `scripts/` | Utility scripts — Scryfall importer, Pokemon TCG importer, YGOProDeck art fetcher, stress tests. |
| `data/` | Cached card data (Scryfall JSON, images, generated card registries). |
| `docs/` | Design notes — architecture drafts, per-feature plans. |

## D. The Event Pipeline in Practice

### Key event types

Defined in `src/engine/types.py:EventType`. The most common:

- `ZONE_CHANGE` — any movement between LIBRARY, HAND, BATTLEFIELD, GRAVEYARD, EXILE, STACK, COMMAND. Carries `object_id`, `from_zone`, `to_zone`.
- `DAMAGE` — `target` (object_id or player_id), `amount`, optional `source`, `is_combat`.
- `LIFE_CHANGE` — `player`, `amount` (negative = loss).
- `DRAW` — `player`, `amount` (preferred) or `count` (legacy).
- `PT_MODIFICATION` — `object_id`, `power_mod`, `toughness_mod`, `duration`.
- `OBJECT_DESTROYED` — `object_id`. Key for Hearthstone deathrattles.
- `CAST` / `SPELL_CAST` — spell-cast triggers.
- `ADD_TO_HAND` — Hearthstone-specific; payload expects `card_def`.
- Hearthstone extras: `WEAPON_EQUIP`, `DIVINE_SHIELD_BREAK`, `FREEZE_TARGET`, `SILENCE_TARGET`, `ARMOR_GAIN`, `FATIGUE_DAMAGE`.
- Query events: `QUERY_POWER`, `QUERY_TOUGHNESS`, `QUERY_TYPES`, `QUERY_COST` — interceptors on these modify *reads*, taking the place of MTG's layer system.

### Registering interceptors

Cards expose a `setup_interceptors(obj, state) -> list[Interceptor]` callback in their `CardDefinition`. The pipeline's `_handle_zone_change` runs this callback when an object enters BATTLEFIELD (or COMMAND). `create_object()` in `game.py` also runs it, but only for battlefield/command zones — a guard added to avoid registering interceptors for cards sitting in libraries.

Most interceptors use `duration='while_on_battlefield'`. These are auto-removed when their source leaves the battlefield (CLEANUP phase). Use `'until_leaves'` when the interceptor must survive one final event (to fire a death trigger) before removal. See `src/cards/interceptor_helpers.py` for the helper library and `CLAUDE.md` for the card-authoring quick reference.

## E. Per-Mode Architecture

### MTG (full engine)

MTG exercises every subsystem. `src/engine/turn.py:TurnManager` walks Beginning → Pre-combat Main → Combat → Post-combat Main → Ending with full MTG step granularity. `src/engine/stack.py` holds the spell/ability stack; `src/engine/priority.py` passes priority between players; `src/engine/combat.py` handles declarers/blockers/damage. State-based actions live in `game.py:_check_state_based_actions`. Power/toughness, types, and controller are all read through `QUERY_*` interceptors in `src/engine/queries.py`.

AI strategies: `src/ai/strategies/{aggro,control,midrange,ultra}.py`, dispatched via `src/ai/engine.py` and scored by `evaluator.py`.

### Hearthstone

`src/engine/hearthstone_turn.py:HearthstoneTurnManager` collapses MTG's structure to Draw → Main → End — no priority, no stack, no combat phase. `hearthstone_mana.py` tracks auto-refilling mana crystals and overload. `hearthstone_combat.py` handles minion-on-minion and hero attacks.

Hearthstone leans heavily on interceptors for buffs, auras, and keywords. Battlecries run immediately (invoked as the `battlecry=` callback on `make_minion`). Deathrattles register as REACT interceptors filtering on `OBJECT_DESTROYED`. Silence, transform, freeze, and divine shield are implemented as dedicated events (`SILENCE_TARGET`, `TRANSFORM`, `FREEZE_TARGET`, `DIVINE_SHIELD_BREAK`) with pipeline handlers. Dynamic costs (Sea Giant, Molten Giant) are computed by assigning `card_def.dynamic_cost` to a function that runs before cost modifiers in `_get_mana_cost`.

### Pokemon TCG

`src/engine/pokemon_turn.py:PokemonTurnManager` runs Draw → Main → Attack → Checkup. `PokemonEnergySystem` (`pokemon_energy.py`) validates attach costs; `PokemonCombatManager` (`pokemon_combat.py`) applies weakness/resistance and KO resolution; `PokemonStatusSystem` (`pokemon_status.py`) handles Poison, Burn, Sleep, Paralysis, Confusion with mutual exclusivity.

**Architectural note**: Pokemon's turn manager manipulates zones directly instead of emitting `ZONE_CHANGE` events through the pipeline. Zones store object IDs as strings (not `GameObject` references) and the session layer uses a `_resolve_obj` helper. `check_win_conditions` sets `has_lost=True` on the loser for compatibility with `game.is_game_over()`. This is known technical debt — see Section H.

AI: `src/ai/pokemon_adapter.py:PokemonAIAdapter(difficulty=str)` — planning-style AI with per-turn `TurnContext`, energy commitment plans, trainer scorer registry, and lethal detection.

### Yu-Gi-Oh!

`src/engine/yugioh_turn.py:YugiohTurnManager` runs Draw → Standby → Main 1 → Battle → Main 2 → End. First turn's Battle Phase is skipped. `yugioh_combat.py` does ATK/DEF calculation; `yugioh_summon.py` handles Normal/Tribute/Flip summon rules; `yugioh_spells.py` resolves spell effects.

`yugioh_chain.py` is a **parallel stack system** — separate from MTG's `stack.py` — because YGO chain resolution order (LIFO, spell speed tiers) is structurally different enough that sharing would cost more than it saves. This is deliberate.

Zone shapes differ by zone: **slotted** zones (`monster_zone`, `spell_trap_zone`) are fixed-size lists with `None` in empty slots; **list** zones (`hand`, `graveyard`, `banished`) hold no `None`s. Code that mutates zones must respect this distinction. Because `YugiohTurnManager` subclasses `TurnManager`, the active player ID must be synced to both `ygo_turn_state.active_player_id` and the base class `turn_state.active_player_id` — see Section H.

AI: `src/ai/yugioh_adapter.py:YugiohAIAdapter(difficulty=str)` — four tiers, per-deck `AI_STRATEGY` dicts (priorities, summon priority, set priority) for the optimized decks in `ygo_optimized.py`.

## F. AI Layer

- **MTG**: shared `src/ai/engine.py` dispatches to `strategies/`. `evaluator.py` scores board states; `heuristics.py` supplies cheap game-state proxies. Strategies: Aggro, Control, Midrange, Ultra.
- **Hearthstone / Pokemon / Yu-Gi-Oh**: per-mode adapters (`hearthstone_adapter.py`, `pokemon_adapter.py`, `yugioh_adapter.py`), each accepting a `difficulty` string.
- Four difficulty tiers are shared vocabulary across modes: `easy`, `medium`, `hard`, `ultra`.
- Experimental LLM-backed decision-making lives under `src/ai/llm/`; reactive/layered helpers are in `src/ai/reactive.py` and `src/ai/layers/`.

## G. Frontend

- **Stack**: React 18 + TypeScript + Vite, Tailwind CSS for styling, Zustand for state stores, framer-motion for animations.
- **Mode dispatch**: `GameView.tsx` switches on game mode and renders the matching board: `MTGGameBoard`, `HSGameBoard`, `PKMGameBoard`, `YGOGameBoard`. Mode-specific hooks (`usePokemonGame`, etc.) wrap REST + socket transport.
- **Drag-and-drop**: unified across all four modes via `hooks/useDraggable.ts` (source) and `hooks/useDropTarget.ts` (target), backed by the `useDragDrop.ts` Zustand store. `DragHintOverlay.tsx` and per-mode choice popups handle intent disambiguation (e.g. YGO summon vs set). Click-based interactions are preserved everywhere — drag is additive. Safety: a global `dragend`/`blur` listener clears stuck drag state.
- **Transport**: Socket.IO preferred; REST fallback is always available. The Socket connection occasionally reports "Disconnected" behind some proxy configurations; REST keeps games playable through that.

## H. Known Architectural Debt

These are documented here so contributors know what *not* to reach for as a clean example. None are broken — they are all load-bearing — but they bound how far the current design scales.

1. **`game_mode == "..."` string branching** — factory methods in `game.py` and dispatch in `pipeline.py`, `session.py`, etc. switch on a mode string. Adding a fifth mode means auditing every `if mode == "..."` site.
2. **Pokemon and Yu-Gi-Oh bypass the event pipeline for zone movement.** Their turn managers mutate zone lists directly. This means interceptors on `ZONE_CHANGE` cannot observe, transform, or react to most zone transitions in those modes.
3. ~~**Two parallel effect DSLs.**~~ **Resolved.** The declarative `src/engine/abilities/` package has been retired. All card code now goes through the single path: `src/cards/interceptor_helpers.py` + `src/cards/ability_bundles.py` + `src/cards/text_render.py`. `CardDefinition.abilities` remains as a list of keyword-ability dicts (e.g. `[{'keyword': 'taunt'}]`) used by the Hearthstone catalog and legacy keyword-substring assertions; it no longer triggers any auto-generated interceptor logic.
4. **`TurnManager` inheritance forces dual-state syncing.** `PokemonTurnManager` and `YugiohTurnManager` maintain their own `*_turn_state` dataclasses but must also keep the base class's `turn_state.active_player_id` and `turn_state.turn_number` in lockstep, or frontend checks like `isMyTurn` silently break.
5. **`pipeline.py` is 3,200+ lines in one module.** It handles dispatch for every `EventType` across four game modes.
6. **`session.py` is a 2,700+ line god-object.** Per-mode branches for action handling, logging, serialization, and AI orchestration all live side-by-side.

Addressing any of these is out of scope for this document — flagging only.
