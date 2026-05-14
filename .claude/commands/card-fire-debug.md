---
description: Auto-diagnose "why doesn't this card fire under heuristic AI?" Walks the 6-step decision tree once-walked manually for the BRV gap-closure (Voidmage, Mirko, Aurelia, Pithing, Negate, Jarad) and reports which step fails with a suggested patch. Engine-agnostic by design (Pokemon today, others later).
argument-hint: --card "<Card Name>" [--p1 <deck>] [--p2 <deck>] [--p1-bias <preset>] [--p2-bias <preset>] [--games N] [--max-turns N]
---

# /card-fire-debug — why doesn't this card fire?

When a heuristic AI scores a card well in design review but the card never
actually fires in playtests, six possible failure modes account for ~all
real-world cases. This skill walks all six in one shot and reports the
specific blocker plus a suggested patch.

The decision tree (six steps):

1. **Drawn at least once** — across the playtest, is the card in any hand?
   If not, the deck doesn't have enough copies / search trainers / luck.
2. **Appears in legal_pokemon_actions** — when in hand AND its type-specific
   precondition is met, is the card emitted as a legal action? (POKEMON_TOOL
   class bug.)
3. **Scorer returns positive** — when scored by its appropriate scorer
   (`_score_trainer` / `_score_basic_play` / `_score_evolution` /
   `_score_attacker`), is the result > 0? (-100 workaround class bug.)
4. **Evolution prerequisite in play** — for evolution cards, is the base
   ever in play with `turns_in_play >= 1`? (Mirklet/Mirko class bug.)
5. **Required energy attached when Active** — for attackers, are the
   energies for the cheapest attack ever attached to the card while it's
   Active? (Energy plan bias missing.)
6. **Ranked competitively at action selection** — when the card has a
   legal action, does its score beat or match alternatives of the same
   action type? If not, it's drowned by competing plays each turn.

The orchestrator script is
`scripts/play/diagnose_card_fire.py`. It instruments the heuristic AI by
wrapping `_score_trainer`, `_score_attacker`, `_score_basic_play`,
`_score_evolution` for the duration of N games, sampling per-turn
telemetry (hand membership, legal-action presence, energy state,
action-selection rivalry), then projects the captured data onto the
6-step decision tree.

## Usage

```
python -m scripts.play.diagnose_card_fire \
  --card "Voidmage Apprentice" \
  --p1 dimir --p2 golgari \
  --p1-bias lz_engine --p2-bias lz_engine \
  --games 5 --max-turns 40
```

Arguments:

- `--card` (required) — exact `name` field of the card definition.
- `--p1`, `--p2` — deck builder names (default `dimir` / `golgari`).
  For Pokemon, these are `azorius`, `boros`, `dimir`, `golgari`, `gruul`,
  `izzet`, `orzhov`, `rakdos`, `selesnya`, `simic`. (Or whatever your
  engine's deck builders are.)
- `--p1-bias`, `--p2-bias` — bias presets (default `lz_engine`). See
  `src/ai/pokemon/biases.py::POKEMON_BIAS_PRESETS`.
- `--games` (default 5) — how many games to sample. More games = lower
  variance but slower.
- `--max-turns` (default 40) — turn cap per game.
- `--engine` (default `pokemon`) — engine to use. Reserved for future
  cross-engine support.

## Output

```
============================================================
  Voidmage Apprentice — DIAGNOSIS
============================================================
  matchup: dimir(lz_engine) vs golgari(lz_engine)
  games:   5 (max 40 turns each)
  elapsed: 0.2s
  deck presence: P1=2, P2=0

  [PASS] Step 1: drawn into hand at least once
         in hand on 11 player-turns across 5 games
  [PASS] Step 2: appears in legal_pokemon_actions when eligible
         appears on 1/1 turns where it was eligible
  [PASS] Step 3: scorer produces a usable score
         basic_play scorer returns max=18.0, avg=18.0, min=18.0 (5 invocations)
  [PASS] Step 5: required energy attached while Active
         Active 29 turns; 28 of those had cost paid
  [PASS] Step 6: ranked competitively at action selection
         ranked below alternatives on 0 turns; actually played 0x,
         was Active on 29 turns, attacked 15x

OVERALL: PASS

SUGGESTED PATCH:
  No patch needed; card fires under heuristic AI.
============================================================
```

If a step fails, the patch suggests the specific source location to look at:

- Step 1 FAIL → bump deck count / add a finder trainer (Nest Ball, etc.).
- Step 2 FAIL → audit `src/engine/pokemon_legal_actions.py` for the
  card's `CardType`.
- Step 3 FAIL → grep for the card's name in
  `src/ai/pokemon/scoring.py` and `src/ai/pokemon/biases.py` for a
  hardcoded `-100` workaround.
- Step 4 FAIL → bias preset's `choose_setup_active` is letting the
  evolution prerequisite lose the opener race.
- Step 5 FAIL → `_score_energy_attachment` and the bias preset's
  energy_priority weights.
- Step 6 FAIL → add a card-name bias entry in `biases.py` or bump the
  card's score in `scoring.py`.

## When to run

- During `/new-set` or `/new-game` polish passes, when a card scores
  well in design review but the wet-test never shows it firing.
- After a tuning change, to verify the card's full path through the
  pipeline still works.
- When closing an "X cards scored well but plays mid" gap (BRV-style).

## Tests

`tests/test_card_fire_debug.py` covers:

1. Voidmage Apprentice in dimir vs golgari + lz_engine biases — should
   PASS at every step after BRV gap-closure.
2. A deliberately broken scorer (monkey-patched to return -100) — Step 3
   must catch it.
3. A card not in any deck under test — Step 0 must catch it.

Run: `python tests/test_card_fire_debug.py`

## Engine support

Currently Pokemon only. Adding a new engine means:

1. Plug in the engine's legal-action discovery (mirror
   `_run_pokemon_diagnostic_game`'s use of `legal_pokemon_actions`).
2. Wrap the AI adapter's scorer methods (look for the engine's
   `<engine>_adapter.py::_score_*` methods).
3. Map "card type → eligibility precondition" for Step 2 (Pokemon's
   bench < 5 for Basics, `supporter_played_this_turn` for Supporters, etc.).

The decision tree itself (Step 1 through Step 6) is engine-agnostic —
only the per-engine probe needs to be added.
