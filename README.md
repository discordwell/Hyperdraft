# Hyperdraft

An AI-powered card game engine for theorycrafters who want to play games nobody has played before.

## Overview

Hyperdraft is built for the weirdos who enjoy figuring out a game as they go - exploring novel mechanics, discovering emergent strategies, and theorycrafting in uncharted territory.

The engine starts with Magic: The Gathering as its foundation because MTG is one of the most well-defined and robust card game systems ever created. From this base, Hyperdraft expands outward - generating new mechanics, card sets, and entire game systems that can be playtested and explored.

### Current Capabilities

The event-driven rules engine handles:

- **Priority and Stack**: Full priority passing, spell resolution, and stack interactions
- **Combat**: Attack/block declarations, damage assignment, first strike, trample, etc.
- **Mana System**: Color requirements, mana pools, and mana abilities
- **Targeting**: Legal target validation with the full targeting rules
- **Player Choices**: Modal spells, scry, surveil, discard, sacrifice decisions
- **AI Opponents**: Four difficulty levels that can playtest new cards and mechanics

## Architecture

**Core Philosophy**: Everything is an Event, everything else is an Interceptor.

```
Event → TRANSFORM → PREVENT → RESOLVE → REACT
```

Events flow through a pipeline where interceptors can transform, prevent, or react to them. This cleanly models triggered abilities, replacement effects, and state-based actions.

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `src/engine/` | Core rules engine (events, interceptors, combat, mana, stack) |
| `src/cards/` | Card definitions with ~3,450 real MTG cards |
| `src/cards/custom/` | ~4,400 custom cards with working interceptors |
| `src/ai/` | AI strategies (aggro, control, midrange) + LLM integration |
| `src/server/` | FastAPI game server |
| `src/decks/` | Pre-built decks including tournament netdecks |
| `frontend/` | React + TypeScript game client |

## Features

### AI Opponents

Four difficulty levels with distinct behaviors:

| Difficulty | Description |
|------------|-------------|
| **Easy** | Makes suboptimal plays, misses blocks |
| **Medium** | Reasonable plays using strategy evaluation |
| **Hard** | Optimal plays with strategy layers for scoring |
| **Ultra** | LLM-guided decisions with full strategic context |

The AI handles all player choices including targeting, modal spells, scry/surveil, and combat decisions.

### Card Sets

**Real MTG Sets** (from Scryfall API):

| Set | Code | Cards |
|-----|------|-------|
| Wilds of Eldraine | WOE | 281 |
| Lost Caverns of Ixalan | LCI | 292 |
| Murders at Karlov Manor | MKM | 279 |
| Outlaws of Thunder Junction | OTJ | 276 |
| Bloomburrow | BLB | 280 |
| Duskmourn | DSK | 277 |
| Foundations | FDN | 517 |
| Aetherdrift | AER | 276 |
| Tarkir: Dragonstorm | TDR | 277 |

**Custom Sets** with full interceptor implementations for testing.

### Player Choice System

The engine supports interactive choices for:
- **Targeting**: Choose targets for spells and abilities
- **Modal Spells**: Select modes for cards like Cryptic Command
- **Scry/Surveil**: Decide which cards go to bottom/graveyard
- **Discard/Sacrifice**: Pick cards or permanents
- **"You May" Effects**: Accept or decline optional effects

### Frontend

React-based game client with:
- Drag & drop card playing
- Visual card rendering with Scryfall images
- Smart auto-pass for smoother gameplay
- Choice modal for targeting and decisions
- Real-time game state updates

## Quick Start

### Backend

```bash
# Install dependencies
pip install -r requirements-server.txt

# Run the server
uvicorn src.server.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
python tests/test_lorwyn.py
python tests/test_layer_nightmares.py
python tests/test_degenerate.py
```

## Implementing Cards

Cards are defined with a setup function that returns interceptors:

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
    setup_interceptors=card_name_setup
)
```

### Available Helpers

| Helper | Purpose |
|--------|---------|
| `make_etb_trigger` | Enter the battlefield triggers |
| `make_death_trigger` | Dies triggers |
| `make_attack_trigger` | When attacks |
| `make_damage_trigger` | When deals damage |
| `make_static_pt_boost` | Lord effects (+X/+Y) |
| `make_keyword_grant` | Grant keywords |
| `make_upkeep_trigger` | Upkeep triggers |
| `make_spell_cast_trigger` | Spell cast triggers |

See `.claude/skills/implement-mtg-cards.md` for the complete guide.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/match/create` | POST | Create a new game |
| `/match/{id}/start` | POST | Start the game |
| `/match/{id}/state` | GET | Get current game state |
| `/match/{id}/action` | POST | Submit a player action |
| `/match/{id}/choice` | POST | Submit a player choice |
| `/match/decks` | GET | List available decks |

## Ultra AI Setup (Optional)

For LLM-powered AI decisions:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull qwen2.5:3b
```

## Vision

MTG is the starting point, not the destination. The roadmap:

1. **Foundation** (current): Complete MTG rules engine with AI opponents
2. **Card Generation**: AI-generated cards that slot into existing mechanics
3. **Mechanic Generation**: Novel keywords, abilities, and interactions
4. **Meta Generation**: Entirely new game systems with different resource models, win conditions, and combat rules
5. **Discovery Mode**: Drop into a game with unknown rules and figure it out through play

The goal is a sandbox where theorycrafters can explore card game design space that no human has mapped.

## License

MIT
