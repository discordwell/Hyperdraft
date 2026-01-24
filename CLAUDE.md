# Hyperdraft

AI-powered deckbuilder with an event-driven MTG rules engine.

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
| Set | Cards | With Interceptors |
|-----|-------|-------------------|
| Lorwyn Eclipsed | 408 | 202 |
| Avatar TLA | 286 | 151 |
| Spider-Man | 198 | 103 |
| Edge of Eternities | 276 | 113 |

## Running Tests
```bash
python tests/test_lorwyn.py
python tests/test_layer_nightmares.py
python tests/test_degenerate.py
```

## Running the Server
```bash
pip install -r requirements-server.txt
uvicorn src.server.main:app --reload
```

## Running the Frontend
```bash
cd frontend
npm install
npm run dev
```
