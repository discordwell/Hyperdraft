---
description: LLM-driven deckbuilder for any game engine. Subagent discovers card pool + conventions for the named game, designs K candidate decks, tournament evaluates them against starters, winners get reported.
argument-hint: [--game <name>] [--num-decks N] [--bias balanced] [--games N] [--out PATH]
---

# /build-decks — discovery-driven deck construction

Generalization of the original `mc-build-decks` skill. The deck *is* the
strategy as much as the AI bias is — hand-rolled starters tend to be
suboptimal, and an LLM with the full card pool in front of it can
hypothesize archetypes the human builders missed.

This skill is **engine-agnostic**. It expects the target game to follow
the standard HYPERDRAFT layout (cards under `src/cards/<game>/`, an AI
adapter, a per-game tournament harness). The subagent discovers the
specific dict names and conventions itself rather than reading a
registry — naming is not uniform across games (`MINECRAFT_CARDS` vs
`ALL_YGO_CARDS` vs `ALL_CARDS` for HS) so registry maintenance would rot
fast.

## Arguments

User invoked with: `$ARGUMENTS`

Optional (inferred from repo state if absent — see "Game inference" below):
- `--game <name>` — the engine name (matches the `src/cards/<name>/`
  package). e.g. `minecraft`, `pokemon`, `yugioh`, `hearthstone`,
  `submarine`.

Other optional:
- `--num-decks 4` — how many new decks to design.
- `--bias balanced` — AI bias used by both seats during evaluation.
  Pass-through to the tournament script. If the engine has no bias
  system (e.g. Pokemon difficulty levels), the tournament script will
  ignore or remap it.
- `--games 3` — games per deck pair in the tournament.
- `--out logs/<game>_decks_<timestamp>.json` — deck spec path.

## Workflow

### Game inference (when `--game` is omitted)

If `--game <name>` is not provided, infer it from repo state:

1. Run `git status --short`. Tally how many modified/untracked files
   match `src/cards/<X>/`, `src/engine/<X>*.py`, `src/ai/<X>_adapter.py`,
   `frontend/src/games/<X>.tsx`, or `docs/strategy/<X>.md` for each
   candidate `<X>`.
2. If a single game has ≥3 matches AND dominates runners-up ≥3:1, pick it.
3. Else: run `git log -5 --name-only` and apply the same tally to
   recent commits.
4. Else: list `src/cards/*/__init__.py`. If only one engine directory
   exists, use it.
5. Else: halt with "Could not infer --game. Candidates: <list>. Pass
   --game explicitly."

Print the inferred game in the discovery block so it's visible.

### 0. Pre-flight discovery

**Before** spawning the subagent, run discovery yourself (cheap and lets
you fail fast on a bad `--game` value):

1. Confirm `src/cards/<game>/` exists. If not, halt: "Game `<game>` has
   no card package."
2. Skim `src/cards/<game>/__init__.py` to find:
   - The unified card-pool dict name. Common patterns:
     `<GAME>_CARDS`, `ALL_<GAME>_CARDS`, `ALL_CARDS`, or a manually
     merged dict like `MINECRAFT_CARDS = {**ALPHA, **HORROR}`.
   - The starter-deck registry. Common pattern: `<GAME>_STARTER_DECKS`
     or `STARTER_DECKS`. Each entry usually maps name → factory or
     name → list[CardDefinition].
3. Look for a tournament harness:
   - First choice: `scripts/play/<game>_deck_tournament.py`
   - Fallback: `scripts/play/deck_tournament.py` (generic MTG one)
   - If neither exists, halt: "No deck tournament harness for `<game>`.
     Build one or hand-pass to a different evaluator."
4. Look for a strategy doc at `docs/strategy/<game>.md`. Optional —
   absence is fine for a brand-new game; the subagent will still have
   the card pool.
5. Determine deck size by reading an existing starter (e.g.
   `MINECRAFT_STARTER_DECKS["builder"]()` returns 50 cards). Pass this
   to the subagent so it doesn't guess.

Print a one-block summary of what you found:

```
=== /build-decks pre-flight ===
game:           <game>
card pool:      <module>.<DICT_NAME>  (<N> cards)
starters:       <name1>, <name2>, ...  (deck size = <N>)
strategy doc:   docs/strategy/<game>.md  (or "none")
tournament:     scripts/play/<game>_deck_tournament.py
==> spawning deckbuilder subagent...
```

### 1. Spawn deckbuilder subagent

Use `Agent` tool with `subagent_type=general-purpose`. Brief:

> You are the deckbuilder for the `<game>` engine. Design K=N new decks
> (N from the user's --num-decks flag, default 4). Each deck is exactly
> `<DECK_SIZE>` cards (the size used by existing starters).
>
> **Read first**:
>   - The strategy doc at `docs/strategy/<game>.md` if it exists. Pay
>     attention to mulligan rules and any "known weaknesses" sections.
>   - The card pool. The unified dict is named `<DICT_NAME>` and lives
>     in `src/cards/<game>/__init__.py`. Read enough of the card-source
>     files to understand the pool — costs, stats, effect categories.
>   - The existing starter decks (registered as `<STARTER_DICT_NAME>`).
>     Your designs should differ meaningfully from the starters; the
>     point is to *test alternative hypotheses*, not iterate on what's
>     already there.
>   - Any pilot or tournament logs under `logs/` matching `<game>` —
>     past results are deck-construction evidence.
>
> Card-count convention: most engines run N copies of fewer unique
> names. Verify by inspecting an existing starter, then follow the same
> convention unless you have a reason not to (e.g. "this archetype
> wants 4-of's instead of 2-of's because it really needs the density").
>
> Design diverse decks, each with a clear hypothesis. Do not invent a
> universal template — the right archetypes depend on the engine.
> Examples that translate across most engines:
>   - **engine_archetype**: load up on the engine's defining mechanic
>     (workers / energy attachment / tribal). Tests "is this mechanic
>     undertuned in the starters?"
>   - **early_aggro**: cheapest threats, no late game. Tests "kill
>     before opponent ramps."
>   - **stall_to_lategame**: defensive plays + recovery + bombs. Tests
>     "can the engine even support control?"
>   - **synergy_pile**: pick one card with a strong "matters" trigger
>     and stuff its enablers. Tests build-around viability.
>
> For each deck, output:
>   - **name** (snake_case, unique)
>   - **rationale** (one sentence — what hypothesis this tests)
>   - **cards** (list of `<DECK_SIZE>` card names, with duplicates for
>     multi-copies)
>
> Output format: write a single JSON file at the path given by --out
> (or `logs/<game>_decks_<timestamp>.json` if not specified) with
> shape:
>
> ```json
> {
>   "version": 1,
>   "game": "<game>",
>   "generated_by": "claude-code-subagent",
>   "decks": {
>     "<name1>": {
>       "rationale": "...",
>       "cards": ["Card Name 1", "Card Name 2", ...]
>     }
>   }
> }
> ```
>
> **Validate before saving**: each `cards` array must have exactly
> `<DECK_SIZE>` entries; every name must appear as a key in
> `<DICT_NAME>`. Failures here are silent disasters at tournament time.
>
> Use the `Write` tool to save the JSON. Then print a short summary
> listing each deck name, rationale, and key card counts (e.g.
> "worker_engine: 12 Workers, 4 Explore Map"). Don't repeat the full
> JSON.

### 2. Run the deck tournament

Invoke the tournament harness discovered in pre-flight. Most harnesses
follow the same CLI shape (modeled on `mc_deck_tournament.py`):

```
PYTHONPATH=. python scripts/play/<game>_deck_tournament.py \\
    --decks-file <PATH_FROM_STEP_1> \\
    --decks <new_deck_names>,<starter1>,<starter2>,... \\
    --bias <bias> \\
    --games <games> \\
    --max-turns 35 \\
    --out logs/<game>_deck_tourney_<timestamp>.json
```

Always include the existing starters as benchmarks. If the game has no
starters yet (brand-new engine), warn that the tournament will be
"new decks vs each other" only — winners are *relative*, not absolute.

If the harness's flags differ (e.g. uses `--difficulty` instead of
`--bias`), adapt — the discovery in pre-flight should have surfaced
the actual flag set. If unsure, run `python scripts/play/<game>_deck_tournament.py --help`.

### 3. Report findings

Summarize the result in tight markdown:

1. **Top 3 decks** with winrates. Mark which are new vs starter.
2. **Did any new deck beat all starters?** That's a real construction win.
3. **Did any new deck fail to beat ALL starters?** That hypothesis is rejected.
4. **Surprising matchups** — e.g. did `worker_engine` lose to `early_aggro`?
   That tells you something the starter-pair tests didn't.
5. **Suggested next iteration**: which winning deck deserves more copies/
   tuning, which losing one is dead.

### 4. Optional: Update strategy doc

If a deck-construction insight is genuinely new (e.g. "12 Workers is
the sweet spot, 16 is too many"), append a "Deck construction" section
to `docs/strategy/<game>.md` (creating the file if absent). Don't dump
tournament results — extract principles. Use the Edit tool.

## Notes

- Interactive command. User watches the loop.
- Total expected runtime: ~5–10 minutes for 4 decks × 4 starters × 3
  games, plus subagent design time.
- Tournament uses the SAME AI bias on both seats — pure deck-quality
  signal, not deck-AI synergy. Re-run with different `--bias` values to
  test deck-AI fit.
- Sample size of 3 games per pair is noisy. Bump `--games` for tighter
  signal once you find a candidate worth pressure-testing.
- This skill is intentionally invoked by other skills — `/new-game-plus`
  calls it as part of the polish pass. When invoked from a parent, the
  parent supplies `--game` directly so no discovery ambiguity.
