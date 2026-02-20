# Hyperdraft

AI-powered deckbuilder with an event-driven MTG rules engine.

## Claude Preferences

- When spawning >5 agents in a single command, ask user if they want to use `model: "sonnet"` instead of opus to reduce cost/latency.

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
- `make_etb_trigger` - Enter the battlefield
- `make_death_trigger` - When dies
- `make_attack_trigger` - When attacks
- `make_damage_trigger` - When deals damage
- `make_static_pt_boost` - Lord effects (+X/+Y)
- `make_keyword_grant` - Grant keywords
- `make_upkeep_trigger` - Upkeep triggers
- `make_spell_cast_trigger` - Spell cast triggers

### Filter Factories
- `other_creatures_you_control(obj)`
- `other_creatures_with_subtype(obj, "Elf")`
- `creatures_you_control(obj)`

## Card Sets

### Real MTG Sets (from Scryfall API)
Located in `src/cards/`. ~3,450 cards with accurate data, no interceptors yet.

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
| Lorwyn Custom | 408 | Has interceptors, used by tests |
| Temporal Horizons | 276 | Has interceptors |
| + 16 crossover sets | ~3,700 | Star Wars, anime, games |

To regenerate real sets from Scryfall:
```bash
python scripts/fetch_scryfall_set.py <set_code> <module_name> "<Set Name>"
```

## Running Tests
```bash
python tests/test_lorwyn.py
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
