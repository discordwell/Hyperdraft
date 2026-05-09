---
description: Generate an aesthetic PDF rulebook for any Hyperdraft game engine. Orchestrates parallel research, validates rules against code, captures frontend screenshots, and compiles a styled PDF.
argument-hint: <game> [--out-dir docs/rulebooks]
---

# /rulebook — PDF rulebook generator

Generates a professionally styled, human-readable PDF rulebook for a specified Hyperdraft game engine.

## Arguments

The user invoked this with: `$ARGUMENTS`

- **`game`** (required): one of `mtg`, `hearthstone` / `hs`, `pokemon`, `yugioh` / `ygo`, `minecraft` / `mc`, `depths`, `finance`.
- **`--out-dir`** (optional, default `docs/rulebooks`): where to write the output files.

If `game` is missing, list the options and ask once. Otherwise never block on user input — pick reasonable defaults and proceed.

## Pre-flight

Resolve the game alias to canonical name and key file paths. Then announce and proceed:

```
=== /rulebook pre-flight ===
game:     <game>
out-dir:  <out_dir>
==> starting stage 1...
```

### Game → file map

| Game | Turn manager | Card module(s) | Docs |
|------|-------------|----------------|------|
| mtg | src/engine/turn.py | src/cards/ | docs/, CLAUDE.md |
| hearthstone | src/engine/hearthstone_turn.py | src/cards/hearthstone/ | CLAUDE.md §HS |
| pokemon | src/engine/pokemon_turn.py, src/engine/pokemon_*.py | src/cards/pokemon/ | CLAUDE.md §Pokemon |
| yugioh | src/engine/yugioh_turn.py, src/engine/yugioh_*.py | src/cards/yugioh/ | CLAUDE.md §YGO |
| minecraft | src/engine/minecraft_turn.py, src/engine/minecraft.py | src/cards/minecraft/ | docs/strategy/minecraft.md |
| depths | src/ai/depths_adapter.py, scripts/new_set/_adapters/depths_tournament_adapter.py | docs/sets/SUBS.md | docs/strategy/depths.md, docs/sets/SUBS.md |
| finance | src/engine/finance_turn.py, src/engine/finance.py | src/server/modes/finance.py | — |

### Visual theme per game

| Game | Primary bg | Accent | Font family | Flavor label |
|------|-----------|--------|-------------|--------------|
| mtg | #F5E6C8 | #4A235A | Cinzel + Crimson Text | Arcane Grimoire |
| hearthstone | #3B2008 | #FFD700 | Playfair Display + Lato | Tavern Ledger |
| pokemon | #CC0000 | #3B4CCA | Nunito + Nunito Sans | Trainer's Handbook |
| yugioh | #0A0A0A | #C9A84C | UnifrakturMaguntia + Crimson Text | Duelist's Tome |
| minecraft | #2D2D2D | #5D9E3A | VT323 + Share Tech Mono | Crafter's Manual |
| depths | #030E1A | #00FF41 | Orbitron + Share Tech Mono | Naval Operations Brief |
| finance | #FAFAFA | #1B5E20 | Merriweather + Source Sans Pro | Investment Prospectus |

All fonts are available via Google Fonts CDN.

---

## Stage 1 — Parallel research (three agents simultaneously)

Create tasks, then spawn all three in a **single message** with three Agent tool calls.

### Agent A: Documentation reader

> **Task**: Read all documentation for the **`<game>`** engine in the Hyperdraft project.
>
> **Files to read** (start with these, expand if you find cross-references):
> - Any `docs/strategy/<game>.md` or similar path
> - Any `docs/sets/` files for this game's card sets
> - Relevant sections of `CLAUDE.md` and `MEMORY.md` (project root and ~/.claude/)
> - Any `ARCHITECTURE.md` that describes this game
> - Any deck plan files in `docs/decks/` mentioning this game
>
> **Output** — structured markdown under these exact headers:
> - `## Overview` — what is this game, how many players, what's unique about it
> - `## Turn Structure (documented)` — phases in order, what happens in each
> - `## Win Conditions (documented)` — how does the game end
> - `## Resource System (documented)` — mana / energy / LP / whatever
> - `## Card Types (documented)` — what types exist, what rules govern each
> - `## Special Mechanics (documented)` — any named mechanics, keywords
> - `## Known Gaps` — any TODOs, "not yet implemented", or "coming soon" mentioned in docs

### Agent B: Code archaeologist

> **Task**: Read the source code for the **`<game>`** engine to extract the ACTUAL rules as implemented.
>
> **Files to read**: turn manager at `<turn_manager_path>`, card module at `<card_module_path>`, plus any related files (combat, chain, zones, AI adapter, win condition checks). Also read `src/engine/game.py` and `src/server/session.py` for engine-level rules.
>
> **Extract and structure**:
> 1. **Turn phases** — read `run_turn()` or equivalent. List each phase in execution order, what actions are legal, and what automatic effects fire.
> 2. **Win conditions** — find `check_win_conditions()`, `is_game_over()`, or equivalent. What triggers a win/loss?
> 3. **Zones** — list all zone names and their roles. How do cards move between zones?
> 4. **Resource system** — how is mana/energy/LP tracked and consumed? Any limits?
> 5. **Card types** — list all CardType enum values and the rules governing each.
> 6. **Special mechanics** — any game-unique mechanics implemented in code (detect/reveal in Depths, chain resolution in YGO, evolution in Pokemon, etc.).
> 7. **Starting state** — hand size, starting life, any special setup.
>
> **Output** — structured markdown under: `## Turn Phases (code)`, `## Win Conditions (code)`, `## Zones`, `## Resource System (code)`, `## Card Types (code)`, `## Special Mechanics (code)`, `## Starting State`.

### Agent C: Card inventory

> **Task**: Read all card definitions for the **`<game>`** game in Hyperdraft. Card files are at: `<card_module_path>`.
>
> **Produce**:
> 1. **Card count by type** — e.g. "42 Creatures, 18 Spells, 10 Lands"
> 2. **Full card table** — every card: Name | Type | Cost/Stats | Rules text (one line max). Sort by type then name. If there are >150 cards, include all but flag a "display subset" of the 40 most mechanically interesting.
> 3. **Mechanics catalogue** — distinct named mechanics or keywords found in card text/interceptors, with one example card per mechanic.
> 4. **Starter decks** — list deck names, card counts, and 3-line strategy description for each.
>
> **Output** — structured markdown under: `## Card Counts`, `## Card Table`, `## Mechanics Found`, `## Starter Decks`.

---

## Stage 2 — Consistency check + rules draft

This stage runs **after** all three agents return. Synthesize their output yourself (no additional agents needed).

### 2a. Cross-check docs vs code

Compare Agent A (documented rules) vs Agent B (code-derived rules). For each discrepancy, classify:
- **MINOR** — trivial difference, doesn't affect gameplay description
- **MAJOR** — material rule difference (a phase doc describes that code skips, a win condition that differs)
- **UNDOCUMENTED** — code implements something not mentioned in any doc

Accumulate these into a "Rules Audit" list for the rulebook appendix.

### 2b. Write the full rulebook content

Use engaging, flavor-appropriate prose — not dry technical writing. Write for a player who has never played this game. Structure:

```
1. WELCOME
   - What is <game name>? (2-3 sentences of flavor matching the game's theme)
   - What makes it unique in the Hyperdraft collection?
   - Players, approximate game length, difficulty

2. COMPONENTS
   - Card types and total counts (from Agent C)
   - Starter decks (names and strategic identity)
   - Any tokens, counters, or special components

3. SETUP
   - Shuffle and draw procedure
   - Starting hand size and mulligan rules (if any)
   - Starting life / LP / resources
   - Who goes first

4. HOW TO PLAY — TURN STRUCTURE
   For each phase (from Agent B, verified against Agent A):
   - Phase name + evocative sub-title (e.g. "Main Phase — Lay Your Plans")
   - What the active player may do
   - What automatic effects fire
   - Any timing or priority rules
   Include a "Quick Turn Cheat Sheet" box at the end: one line per phase.

5. CARD TYPES AND PLAY AREA
   - Diagram description of the table layout (label zones left→right, near→far)
   - Each card type: what it is, when it can be played, how it leaves play
   - Any special card zones (graveyard, banish zone, energy pile, etc.)

6. RESOURCES
   - How to gain the resource each turn
   - How to spend it
   - Any limits (hand size cap, resource cap, max per turn)

7. WINNING AND LOSING
   - Primary win condition (exact code-derived rule from Agent B)
   - Any alternative win conditions
   - Any instant-loss triggers

8. SPECIAL MECHANICS
   - One sub-section per named mechanic from Agent C's catalogue
   - Rules text, followed by a concrete example using a named card
   - Any interactions or edge cases

9. CARD GALLERY
   - Full card table from Agent C (or the 40-card display subset for large sets)
   - Organized by type, then alphabetically
   - Each row: Name | Type | Cost/Stats | Rules Text

10. RULES AUDIT (appendix)
    - The discrepancy list from 2a
    - MINOR items in a footnote section
    - MAJOR / UNDOCUMENTED items flagged clearly

11. QUICK REFERENCE (back cover)
    - Turn order cheat sheet
    - Resource reference
    - Common timing Q&A (3-5 entries)
```

---

## Stage 3 — Visual asset generation

Create `docs/rulebooks/assets/` if it doesn't exist.

### 3a. Check and start servers

```bash
# Backend
curl -s http://localhost:8030/health > /dev/null 2>&1 && echo "backend:up" || echo "backend:down"
# Frontend
curl -s http://localhost:5173 > /dev/null 2>&1 && echo "frontend:up" || echo "frontend:down"
```

If backend is down: `cd /Users/discordwell/Projects/HYPERDRAFT && uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030 &` — wait 4s.

If frontend is down: `cd /Users/discordwell/Projects/HYPERDRAFT/frontend && npm run dev &` — wait 6s.

### 3b. Browser screenshots

Load browser tools via ToolSearch (`select:mcp__claude-in-chrome__tabs_context_mcp`) then capture:

1. **Homepage / game selector** → `docs/rulebooks/assets/<game>_home.png`
   - Navigate to `http://localhost:5173`
   - Wait for page load, screenshot

2. **Game board** → `docs/rulebooks/assets/<game>_board.png`
   - Navigate to the game's URL (try `/game?mode=<game>` or `/game`, or the game-specific route)
   - If the game requires setup/deck selection, complete the minimum steps to see the board
   - Screenshot the full board

3. **Deckbuilder** (if it shows this game's cards) → `docs/rulebooks/assets/<game>_deck.png`
   - Navigate to `/deckbuilder`
   - Filter to this game's cards if a filter exists
   - Screenshot

4. **Card detail** → `docs/rulebooks/assets/<game>_card.png`
   - Click on any visible card to open a detail/modal view
   - Screenshot

If any screenshot fails after 2 attempts, skip it and note the gap.

### 3c. Fallback card frames (if screenshots unavailable)

If the game has no frontend view or screenshots all failed, generate procedural card frames using Python:

```python
from PIL import Image, ImageDraw, ImageFont
import base64, os

# For each of the 6 "notable" cards from Agent C's list:
# - Draw a card frame in the game's color scheme
# - Print card name, type line, P/T or stats, rules text (wrapped)
# Save as docs/rulebooks/assets/<game>_card_<N>.png
```

---

## Stage 4 — HTML generation

Write `docs/rulebooks/<game>_rulebook.html` using the game's visual theme.

Requirements:
- Google Fonts loaded via CDN (use the fonts from the theme table)
- Background and accent colors from the theme table
- Print-ready CSS: `@page` with margins, `page-break-before: always` on each major section
- Embedded screenshots as `<img>` tags with file paths (relative to the HTML file) — NOT base64 inline (keeps file size manageable)
- Table of contents with anchor links
- Card gallery in a `<table>` with alternating row colors
- Decorative section dividers (CSS borders, not images)
- Cover page with game title, a tagline, and a screenshot (if available)
- Maximum width 900px, centered, with outer margin for print

The HTML should feel like a real tabletop rulebook — not a README.

---

## Stage 5 — PDF compilation

Try each approach in order. Stop at the first that produces a file > 20 KB.

### Approach A: Chrome headless (preferred on macOS)

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless \
  --disable-gpu \
  --print-to-pdf="docs/rulebooks/<game>_rulebook.pdf" \
  --no-margins \
  --run-all-compositor-stages-before-draw \
  --virtual-time-budget=10000 \
  "file:///Users/discordwell/Projects/HYPERDRAFT/docs/rulebooks/<game>_rulebook.html" \
  2>/dev/null

ls -lh docs/rulebooks/<game>_rulebook.pdf
```

### Approach B: weasyprint

```bash
pip install weasyprint --quiet 2>/dev/null
python3 -c "
from weasyprint import HTML
HTML(filename='docs/rulebooks/<game>_rulebook.html').write_pdf('docs/rulebooks/<game>_rulebook.pdf')
print('weasyprint: done')
"
```

### Approach C: reportlab (programmatic fallback)

```python
pip install reportlab pillow --quiet
# Build a PDF directly from the rules text and screenshots using reportlab's Platypus.
# Multi-column layout for card gallery, full-page screenshots for board image.
# Apply game color scheme to headers, dividers, and table rows.
```

### Approach D: Halt and report

If all three approaches fail, do **not** invent a fourth fallback (the OpenAI API does not return PDF binaries natively, and per-user memory notes that direct API use hits billing limits fast). Instead:

1. Leave the HTML at `docs/rulebooks/<game>_rulebook.html` for the user to open.
2. Tell the user PDF generation failed, list which approaches were tried with their error messages, and ask whether to install missing system deps (libcairo for weasyprint, etc.), open the HTML in a normal browser and Print-to-PDF manually, or skip the PDF entirely for this run.

---

## Stage 6 — Final report

Tell the user:

- **PDF**: `docs/rulebooks/<game>_rulebook.pdf` — PDF approach used (A/B/C/D)
- **HTML source**: `docs/rulebooks/<game>_rulebook.html`
- **Assets**: list which screenshots were captured vs generated as placeholders
- **Card count**: how many cards appear in the gallery
- **Rules audit**: N total discrepancies — X MINOR, Y MAJOR, Z UNDOCUMENTED. If any MAJOR discrepancies exist, name them.
- **Outstanding**: any stages that fell back to a less-preferred method

Do NOT commit. The user will type `commit` when ready.

---

## Orchestrator notes

- Use `TaskCreate` to track each stage. Mark `completed` as soon as the stage finishes.
- Spawn Stage 1 agents in a **single message** — all three tool calls together.
- Stage 2 synthesizes in-context — no additional agents.
- Stage 3 browser work is sequential (tab context → navigate → screenshot).
- Stages 4 and 5 run after Stage 3 finishes.
- If either server fails to start after the start command, proceed without screenshots — generate a screenshot-free HTML and note it in the Stage 6 report.
- For games with >150 cards in the gallery, include all in the HTML table but flag in the intro that "this gallery shows all N cards; for large sets a curated 40-card spotlight appears in the print edition."
