---
description: LLM-driven deckbuilder for Minecraft TCG. Subagent designs K candidate decks given the strategy doc + card pool, tournament evaluates them against starters, winners get registered.
argument-hint: [--num-decks N] [--bias balanced] [--games N] [--out PATH]
---

# /mc-build-decks — subagent-driven deck construction

The deck IS the strategy as much as the AI bias is. The current MC starters
(builder, miner, raider) are hand-curated and probably suboptimal. This
command spawns a deckbuilder subagent that designs new decks in light of
the strategy doc + card pool, then the deck tournament evaluates them.

## Arguments

User invoked with: `$ARGUMENTS`

Defaults:
- `--num-decks 4` — how many new decks to design.
- `--bias balanced` — AI bias used by both seats during evaluation.
- `--games 3` — games per deck pair in the tournament.
- `--out logs/mc_decks_<timestamp>.json` — deck spec path.

## Workflow

### 1. Spawn deckbuilder subagent

Use `Agent` tool with `subagent_type=general-purpose`. Brief:

> You are the MC deckbuilder. Design K=N new 50-card decks (N from the
> user's --num-decks flag, default 4) for the Minecraft TCG.
>
> **Read first**:
>   - `docs/strategy/minecraft.md` — current strategic understanding.
>     Pay attention to "Mulligan rules" (what makes a hand non-functional)
>     and "Known heuristic-AI weaknesses" (what to exploit/defend against).
>   - `src/cards/minecraft/alpha.py` — the full card pool. Every card you
>     can use is defined in `_cards = [...]` near the bottom. Each card
>     has a name, cost, stats, and on_play/on_attack/on_block effects.
>     Note the existing starter decks (BUILDER_NAMES, MINER_NAMES,
>     RAIDER_NAMES) — your decks should differ meaningfully from them.
>   - `logs/mc_ultra_pilot_iter1.md` and `logs/mc_ultra_pilot_iter2.md`
>     — recent game reports. The pilot's losses (notably to the Raider
>     no-Workers / no-Strip-Mine opening) are deck-construction
>     evidence, not just play evidence.
>
> Each deck is 50 cards. The convention so far is 2 copies of 25 unique
> names, but you can break this — e.g. 4 copies of Steve's Helper if
> Workers really do want max density. Just verify each card name exists
> in MINECRAFT_CARDS (you can grep alpha.py for the names).
>
> Design diverse decks, each with a clear hypothesis. Examples (don't
> just copy these — invent your own):
>   - **worker_engine**: 12+ Workers, 4 Strip Mines, 4 Explore Maps, 2x
>     Iron Golem (worker-payoff), 2x Wither (hostile-payoff). Tests "load
>     up on workers, ramp into bombs."
>   - **structure_stack**: 4x Crafting Table, 4x Furnace, 4x Chest, 4x
>     Redstone Engine + Beacon. Tests "pile turn-bonus structures."
>   - **early_aggro_v2**: 8x cheap hostiles, 4x Iron Sword, no big mobs.
>     Tests "kill them before they ramp."
>   - **block_kingdom**: 4x Cobblestone Wall, 4x Oak Planks, 4x TNT Trap
>     + Ravager + recovery. Tests "stall to lategame."
>
> For each deck, output:
>   - **name** (snake_case)
>   - **rationale** (one sentence — what hypothesis this tests)
>   - **cards** (list of 50 card names, with duplicates for multi-copies)
>
> Output format: write a single JSON file at the path given by --out
> (or `logs/mc_decks_<timestamp>.json` if not specified) with shape:
>
> ```json
> {
>   "version": 1,
>   "generated_by": "claude-code-subagent",
>   "decks": {
>     "<name1>": {
>       "rationale": "...",
>       "cards": ["Card Name 1", "Card Name 2", ..., "Card Name 50"]
>     },
>     ...
>   }
> }
> ```
>
> **Validate before saving**: each `cards` array must have exactly 50
> entries; every name must appear as a key in
> `MINECRAFT_CARDS = {**ALPHA_CARDS, **PHYREXIA_CARDS, **HORROR_CARDS}`
> (most of your picks should come from alpha.py since the others mix
> from Phyrexia/Horror sets — both are available but stick to alpha for
> baseline tests).
>
> Use the `Write` tool to save the JSON. Then print a short summary
> listing each deck name, rationale, and key card counts (e.g.
> "worker_engine: 12 Workers, 4 Explore Map, 4 Strip Mine"). Don't
> repeat the full JSON.

### 2. Run the deck tournament

```
PYTHONPATH=. python scripts/play/mc_deck_tournament.py \\
    --decks-file <PATH_FROM_STEP_1> \\
    --decks <new_deck_names>,builder,miner,raider \\
    --bias <bias> \\
    --games <games> \\
    --max-turns 35 \\
    --out logs/mc_deck_tourney_<timestamp>.json
```

Always include the 3 starter decks as benchmarks.

### 3. Report findings

Summarize the result in tight markdown:

1. **Top 3 decks** with winrates. Mark which are new vs starter.
2. **Did any new deck beat all 3 starters?** That's a real construction win.
3. **Did any new deck fail to beat ALL of the starters?** That hypothesis
   is rejected.
4. **Surprising matchups** — e.g. did `worker_engine` lose to `early_aggro_v2`?
   That tells you Workers don't matter as much as draw speed.
5. **Suggested next iteration**: which winning deck deserves more copies/
   tuning, which losing one is dead.

### 4. Optional: Update strategy doc

If a deck construction insight is genuinely new (e.g. "12 Workers is the
sweet spot, 16 Workers is too many"), append a "Deck construction"
section to `docs/strategy/minecraft.md`. Don't just dump the tournament
results there — extract principles. Use the Edit tool.

## Notes

- Interactive command. User watches the loop.
- Total expected runtime: ~5-10 minutes for 4 decks × 4 starters × 3
  games = ~84 games, plus subagent design time.
- The tournament uses the SAME AI bias on both seats — so the test is
  pure deck construction quality, not deck-AI synergy. To test deck-AI
  fit, run multiple times with different `--bias` values.
- Sample size of 3 games per pair is noisy. Bump --games for tighter
  signal once you find a candidate worth pressure-testing.
