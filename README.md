# Hyperdraft

AI-powered deckbuilder that creates unique card game metas with dynamically generated rules and cards.

## Overview

Hyperdraft uses AI to generate entirely new card game mechanics and metas based on randomized properties:
- Resource systems (mana, energy, action points, etc.)
- Removal prevalence and types
- Combat resolution mechanics
- Win conditions
- Card archetypes and synergies

## Features (Planned)

- **Meta Generation**: Create unique game rules and mechanics
- **Card Generation**: AI generates balanced card sets for each meta
- **Playtesting**: Automated testing to ensure balance
- **Web Interface**: Play generated games in browser
- **Claude Code Integration**: Scripts to generate and test new metas

## Status

🚧 **Project in development** - Repository created for Claude Code Web development.

## Tech Stack (Planned)

- Backend: Python (meta generation, game logic)
- AI: Claude API (card/rule generation)
- Frontend: React/TypeScript
- Testing: Automated playtesting engine
- Database: PostgreSQL (storing metas, cards, games)

## Example Meta Properties

```json
{
  "resource_system": "escalating_mana",
  "removal_prevalence": "low",
  "combat_type": "simultaneous",
  "win_condition": "deck_depletion",
  "special_mechanics": ["echo", "cascade", "morph"]
}
```

## License

MIT

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)