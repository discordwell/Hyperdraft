# Hyperdraft

An AI-powered multi-TCG playground built on an event-driven rules engine. Hyperdraft supports **Magic: The Gathering**, **Hearthstone**, **Pokemon TCG**, and **Yu-Gi-Oh!** through a single shared engine, with AI opponents, a React/TypeScript client, and thousands of playable cards.

## Overview

Hyperdraft started as an MTG rules engine and has since grown into a cross-format sandbox for theorycrafting, AI playtesting, and novel mechanic exploration. Every game action — playing a card, attacking, activating an ability, resolving a trigger — flows through the same event pipeline, and each game mode layers its own rules and turn structure on top.

## Quick Start

### Backend (Python)

```bash
pip install -r requirements-server.txt
uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030
```

The server runs on port **8030** (see `~/Projects/PORTS.md`). Note the ASGI app is `socket_app` (Socket.IO wrapped), not `app`.

### Frontend (React + TypeScript)

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

The main test suite runs under pytest:

```bash
pytest tests/
```

Several test scripts are designed to be run directly instead (e.g. the Pokemon and Yu-Gi-Oh! suites):

```bash
python tests/test_pokemon.py
python tests/test_yugioh.py
python tests/test_lorwyn.py
```

There is also a wet-test harness that exercises all four game modes through the live API:

```bash
python scripts/wet/wet_test.py
```

Stress tests (AI-vs-AI anomaly detection) live under `scripts/stress/` — e.g. `stress_test_hearthstone.py`, `stress_test_pokemon.py`.

## Architecture

**Core Philosophy**: Everything is an Event, everything else is an Interceptor.

```
Event -> TRANSFORM -> PREVENT -> RESOLVE -> REACT
```

Events travel through a four-stage pipeline. Interceptors can rewrite an event (TRANSFORM), cancel it (PREVENT), produce its effects (RESOLVE), or spawn follow-up events in reaction (REACT). Triggered abilities, replacement effects, static modifiers, and state-based actions are all expressed as interceptors — there is no special case.

The same pipeline backs every game mode; mode-specific turn managers (`PokemonTurnManager`, `YugiohTurnManager`, etc.) sit on top and orchestrate phase flow.

For deeper design docs see `docs/hyperdraft-architecture.md`, `docs/mtg-rules-engine-spec.md`, and the arena planning notes under `docs/`.

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `src/engine/` | Core rules engine (events, interceptors, combat, mana, stack, mode turn managers) |
| `src/cards/` | Card definitions per game/set (MTG real sets, `custom/`, `hearthstone/`, `pokemon/`, `yugioh/`) |
| `src/ai/` | AI strategies and per-mode adapters (aggro, control, midrange, Ultra LLM, Pokemon/Yu-Gi-Oh! adapters) |
| `src/server/` | FastAPI + Socket.IO game server |
| `src/decks/` | Pre-built decks, including tournament netdecks |
| `frontend/` | React + TypeScript client with unified drag-and-drop across modes |
| `tests/` | Test suites (pytest + direct-run scripts) |
| `docs/` | Architecture and spec documents |

## Game Modes

### Magic: The Gathering

The oldest and most complete mode. Full priority + stack, combat (first strike, trample, blockers), mana with color requirements, targeting with legality checks, modal spells, scry/surveil, and replacement effects. Four AI difficulties (easy / medium / hard / ultra), with Ultra optionally driven by a local LLM.

### Hearthstone

Board-based combat with mana crystals, battlecries, deathrattles, taunt, and dynamic-cost cards. Uses the same interceptor model (battlecries as setup functions returning events, auras as interceptors). AI has lethal awareness and an Ultra tier.

### Pokemon TCG

Bench + active zones, energy attachment, weakness/resistance, status conditions (5 conditions with mutual exclusivity and checkup resolution), prize cards, and evolution. AI is a planning opponent with multi-turn energy commitment, trainer-specific scoring for 12 named trainers, lethal detection, and prize-aware strategy.

### Yu-Gi-Oh!

Monster / spell / trap zones, normal and tribute summons, flip summons, position changes, and chain resolution. ~51 unique cards with working spell/trap/flip effects implemented (Pot of Greed, Raigeki, Heavy Storm, Torrential Tribute, Bottomless Trap Hole, etc.), 4 competitive decks (Goat Control, Monarch Control, Chain Burn, Dragon Beatdown), and an AI with per-deck strategy tables.

All four modes share a unified drag-and-drop UX in the frontend (hand -> play, attackers, energy attachment, zone placement) with click-based interactions preserved as a fallback.

## Card Sets

### Real MTG sets (from Scryfall API)

Located in `src/cards/`. Accurate card data, no interceptors (used for drafting and deck context).

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

Regenerate a set from Scryfall with:

```bash
python scripts/fetch_scryfall_set.py <set_code> <module_name> "<Set Name>"
```

### Custom sets (with interceptors)

Located in `src/cards/custom/`. ~4,400 fan-made cards wired up with working interceptors — used heavily by the test suite.

| Set | Cards | Notes |
|-----|-------|-------|
| Lorwyn Custom | 408 | Has interceptors, used by tests |
| Temporal Horizons | 276 | Has interceptors |
| + 16 crossover sets | ~3,700 | Star Wars, anime, games, etc. |

### Other game modes

Hearthstone, Pokemon TCG, and Yu-Gi-Oh! card definitions live under `src/cards/hearthstone/`, `src/cards/pokemon/`, and `src/cards/yugioh/` respectively, each with working interceptors / battlecries / effects for the implemented cards.

## Implementing Cards

The setup-function + interceptor pattern:

```python
def card_name_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 3},
                      source=obj.id)]
    return [make_etb_trigger(obj, effect_fn)]

CARD_NAME = make_creature(
    name="Card Name",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="When Card Name enters, you gain 3 life.",
    setup_interceptors=card_name_setup,
)
```

Common helpers in `src/cards/interceptor_helpers.py`:

| Helper | Purpose |
|--------|---------|
| `make_etb_trigger` | Enter-the-battlefield triggers |
| `make_death_trigger` | Dies triggers |
| `make_attack_trigger` | When attacks |
| `make_damage_trigger` | When deals damage |
| `make_static_pt_boost` | Lord effects (+X/+Y) |
| `make_keyword_grant` | Grant keywords |
| `make_upkeep_trigger` | Upkeep triggers |
| `make_spell_cast_trigger` | Spell cast triggers |

See `.claude/skills/implement-mtg-cards.md` for the full MTG card guide. HS / PKM / YGO card patterns are captured in `CLAUDE.md`.

## API Endpoints

Selected REST + Socket.IO endpoints (see `src/server/` for the full surface):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Liveness check |
| `/match/create` | POST | Create a new game (all modes) |
| `/match/{id}/start` | POST | Start the game |
| `/match/{id}/state` | GET | Get current game state |
| `/match/{id}/action` | POST | Submit a player action |
| `/match/{id}/choice` | POST | Submit a pending choice |
| `/match/decks` | GET | List MTG decks |
| `/match/ygo-decks` | GET | List Yu-Gi-Oh! decks (starter + optimized) |

## Ultra AI (optional)

For LLM-guided MTG / HS decisions, install Ollama and pull a small model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
```

## Development

Contributor and agent-specific guidance — coding style, card-implementation patterns, testing conventions, and the session-memory convention (`claudepad.md`) — lives in `CLAUDE.md` at the repo root.

Deployment is handled by `deploy.sh` (rsync + systemd on an OVH VPS behind Caddy). The production service is `hyperdraft.discordwell.com`.

## License

MIT
