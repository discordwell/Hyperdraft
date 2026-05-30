# HYPERDRAFT

AI-powered TCG playground on an event-driven rules engine.

> Brand mark, pitch, audience, and design philosophy live in
> [`docs/design/brand.md`](docs/design/brand.md). Read that before
> writing user-visible copy.

## Claude Preferences

- When spawning >5 agents in a single command, ask user if they want to use `model: "sonnet"` instead of opus to reduce cost/latency.
- When following a skill and a turn uncovers bugs, gaps, or errors, instead of moving on to the next step first fix those bugs then move on.
- When a new subsystem lands (not every commit), review it with a **parallel multi-reviewer `/code-review`** — split the diff by area (engine / AI / cards / server+frontend / tests) with one reviewer per area, and give one reviewer an *independent root-cause investigation* of the riskiest claim rather than a checklist pass. A single-pass review missed the SCP inert-bomb class for ~9 commits; the 4-way split re-derived the root cause and found the turn-reset bug. Run it when a subsystem lands, not only at "major revision" boundaries.
- A card/ability is not "done" when its effect is correct — it's done when the AI actually **fires it in self-play**. `/test-interceptors` is the effect gate; `/card-fire-debug` is the fire gate. "Scores well in review" / "has a value_hint" / "tournament in-band" are not fire gates (see the SCP inert-bomb retrospective).

## Concurrent worktree safety

This repo runs many parallel worktree-agents under `/semaphore`. The parent session does `git reset --hard HEAD` after merge waves, which silently wipes uncommitted work in the **main checkout** (not in agent worktrees).

Two safety nets are wired up:

- `scripts/safety/wip_autobackup.sh` — background daemon that snapshots tracked + untracked changes to `refs/wip/auto/<branch>/<ts>` every 60 s. Auto-started by the `SessionStart` hook in `.claude/settings.json` (singleton per repo).
- `scripts/safety/git-reset-guarded.sh` — opt-in safer reset that snapshots to `refs/wip/manual/<branch>/<ts>` before running `git reset --hard`. Use this in any script / parent workflow that does a discretionary hard-reset.

Recovery after a suspected reset wipe: `git for-each-ref refs/wip/ --sort=-creatordate | head` then `git checkout <ref> -- .`. Full details in `docs/safety/git_reset_defense.md`.

## Worktree sparse-checkout (disk space)

Tracked binary art (`assets/card_art/`, `frontend/public/scp-art/`) is ~2.7GB. Each worktree materializes its own copy, so 18 concurrent worktrees costs ~50GB of disk.

**If you start work inside a `.claude/worktrees/agent-*/` directory, run this before any task work:**

```bash
git sparse-checkout init --cone
git sparse-checkout set src tests frontend/src frontend/public/sounds scripts docs data prompts art-runs codex-pokemon-strategy
```

This drops the worktree from ~2.9GB to ~150MB. Skip only if your task explicitly involves card art or SCP art — in that case re-include with `git sparse-checkout add assets/card_art` (or `frontend/public/scp-art`).

If `git status` shows files missing that you need, the include list above is incomplete for your task — add the dir and continue.

## Card art via Git LFS

Tracked binary art (`assets/card_art/**`, `frontend/public/scp-art/**`) lives in **Git LFS on Cloudflare R2**, fronted by a small giftless server on Fly.io (`infra/giftless/`). The `.git` pack holds pointer files; the actual PNGs are fetched from R2 at clone time. Anonymous reads, JWT-gated writes.

**Fresh clone**: one-time `git lfs install` per machine, then `git clone …` smudges art automatically — no auth required for reads.

**Pushing new art** (rare; most changes touch only code): mint a fresh 2 h JWT with

```bash
./infra/giftless/scripts/issue-token.sh --install discordwell/Hyperdraft
```

Re-run whenever a token expires. The script installs credentials at both URL and host scope, so subsequent `git push` / `git lfs pull` Just Work.

**Symptom → cause**:
- Working-tree art files look like ~130 B of `version https://git-lfs…` text → run `git lfs pull` here.
- `git lfs pull` or `clone` spins forever and trace shows repeated `HTTP 401` against `hyperdraft-lfs.fly.dev` → cached JWT is expired; re-run `issue-token.sh --install`. An expired credential traps git-lfs in a tight `credential fill` → 401 → `credential reject` loop instead of falling through to anon reads.

Full ops + cost model + failure modes: `infra/giftless/README.md`. One-time migration record: `docs/safety/lfs_migration_runbook.md`.

## Architecture

**Core Philosophy**: Everything is an Event, everything else is an Interceptor.

### Event Pipeline
```
Event → TRANSFORM → PREVENT → RESOLVE → REACT
```

### Key Directories
- `src/engine/` - Core rules engine (events, interceptors, combat, mana, stack)
- `src/cards/` - Card definitions and interceptor implementations
- `src/ai/` - AI strategies (aggro, control, midrange)
- `src/server/` - FastAPI game server
- `frontend/` - React + TypeScript game client
- `tests/` - Test suites

## Implementing Cards

See `.claude/skills/implement-mtg-cards.md` for the complete guide.

### Quick Reference

```python
# Setup function pattern
def card_name_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 3},
                      source=obj.id)]
    return [make_etb_trigger(obj, effect_fn)]

# Card definition
CARD_NAME = make_creature(
    name="Card Name",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="When Card Name enters, you gain 3 life.",
    setup_interceptors=card_name_setup
)
```

### Available Helpers (interceptor_helpers.py)

Triggers / static effects:
- `make_etb_trigger`, `make_death_trigger`, `make_attack_trigger`,
  `make_damage_trigger`, `make_upkeep_trigger`, `make_end_step_trigger`,
  `make_spell_cast_trigger`, `make_leaves_battlefield_trigger`
- `make_static_pt_boost` — flat lord effect (+X/+Y)
- `make_dynamic_pt_boost` / `make_attached_dynamic_pt_boost` — "+X/+Y per
  Forest" via state-time `mod_fn`
- `make_keyword_grant` — grant keywords statically

Activated abilities (Phase 4):
- `make_activated_ability(obj, cost, effect_fn, ...)` — generic registration
- Specialised wrappers: `make_pump_self_ability`, `make_draw_ability`,
  `make_loot_ability`, `make_life_gain_ability`, `make_damage_ability`,
  `make_destroy_ability`, `make_counter_ability`,
  `make_token_creation_ability`, `make_sac_destroy_ability`

Equipment / Aura attach (Phase 3):
- `make_equipment_setup` and `make_aura_setup` accept
  `power_mod`, `toughness_mod`, `keywords`, `subtypes_to_add`,
  `equip_cost`, `ward_cost`

Set mechanics (Phase 5):
- `suspect_creature(target_id, source_id, controller, state)`
- `collect_evidence(player_id, n, state)` — greedy MV cost
- `was_bargained(state, card_name)` — read the WOE Bargain marker
- `make_room_setup(...)` + `is_door_unlocked(obj, door_name)`

Sweep helpers:
- `becomes_creature(target, state, *, power, toughness, subtypes, keywords)`
- `threaten_creature(target_id, new_controller, source_id)` — gain control + untap + haste EOT
- `grant_death_trigger(target, source, state, effect_fn, *, duration='end_of_turn')`
- `grant_triggered_ability(target, source, state, *, event_filter, effect_fn, duration, one_shot=False)`
- `make_cost_reduction(source, *, applies_to, amount, self_only=False)` — spell-cast cost reduction
- `make_ward(source, *, mana_cost=None, life_cost=None, custom_cost=None)` — ward replacement

Counts / queries:
- `count_permanents_with_subtype`, `count_permanents_of_type`,
  `count_cards_in_graveyard`, `count_cards_in_hand`

Pipeline events you may emit directly:
- `EventType.ATTACH` / `UNATTACH` (attach mechanic)
- `EventType.MANIFEST_DREAD` (DSK manifest dread)
- `EventType.UNLOCK_DOOR` (DSK Rooms)
- `EventType.TARGET_CHOSEN` (ward post-target hook)
- `EventType.QUERY_COST` (cost reduction query)

CardDefinition fields beyond setup_interceptors:
- `setup_in_graveyard` — runs when the card enters the GRAVEYARD zone
  (for graveyard-activated abilities)

### Filter Factories
- `other_creatures_you_control(obj)`
- `other_creatures_with_subtype(obj, "Elf")`
- `creatures_you_control(obj)`

## Card Sets

### Real MTG Sets (from Scryfall API)
Located in `src/cards/`. ~3,450 cards with accurate data. **2,486 cards have wired interceptors** across the 12 sets. ~744 instants/sorceries use cast-effect dispatch (no setup_interceptors). ~230 truly vanilla cards (keyword-only or stat-line). Of the wired cards, ~1,146 have real effect implementations (~46%), ~736 register a trigger or static interceptor whose effect_fn is `return []` pending engine support, and ~604 are bare `return []` stubs (cards with replacement effects, sagas, equipment statics, modal/target choices, or mechanic-specific patterns the engine doesn't yet express). See `engine_gaps.md` for the punch list grouped by missing capability.

| Set | Code | Cards |
|-----|------|-------|
| Wilds of Eldraine | WOE | 281 |
| Lost Caverns of Ixalan | LCI | 292 |
| Murders at Karlov Manor | MKM | 279 |
| Outlaws of Thunder Junction | OTJ | 276 |
| Bloomburrow | BLB | 280 |
| Duskmourn | DSK | 277 |
| Foundations | FDN | 517 |
| Edge of Eternities | EOE | 266 |
| Lorwyn Eclipsed | ECL | 273 |
| Spider-Man | SPM | 193 |
| Avatar: TLA | TLA | 286 |
| Final Fantasy | FIN | 313 |

### Custom Sets (Fan-Made with Interceptors)
Located in `src/cards/custom/`. ~4,400 cards with working interceptors for testing.

| Set | Cards | Notes |
|-----|-------|-------|
| Fae but Mid | 408 | Has interceptors, used by tests (was "Lorwyn Custom") |
| Temporal Horizons | 276 | Has interceptors |
| + 16 crossover sets | ~3,700 | Star Wars, anime, games |

### Engine-Native Sets (Non-MTG HYPERDRAFT engines)
Card sets that ship with their own engine module (`src/engine/<game>.py`).

| Set | Code | Cards | Notes |
|-----|------|-------|-------|
| Cats | CATS | 60 | First set; 44 wired (73%); 4 decks |

To regenerate real sets from Scryfall:
```bash
python scripts/fetch_scryfall_set.py <set_code> <module_name> "<Set Name>"
```

## Running Tests
```bash
python tests/test_fae_but_mid.py
python tests/test_layer_nightmares.py
python tests/test_degenerate.py
```

## Running the Server

Port **8030** (see `~/Projects/PORTS.md` for registry).

```bash
pip install -r requirements-server.txt
uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030
```

## Running the Frontend
```bash
cd frontend
npm install
npm run dev
```
