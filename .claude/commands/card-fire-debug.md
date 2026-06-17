---
description: Auto-diagnose "why doesn't this card fire under heuristic AI?" Walks the 6-step decision tree once-walked manually for the BRV gap-closure (Voidmage, Mirko, Aurelia, Pithing, Negate, Jarad) and reports which step fails with a suggested patch. Engine-agnostic by design (Pokemon today, others later).
argument-hint: --card "<Card Name>" [--p1 <deck>] [--p2 <deck>] [--p1-bias <preset>] [--p2-bias <preset>] [--games N] [--max-turns N]
---

# /card-fire-debug — why doesn't this card fire?

When a heuristic AI scores a card well in design review but the card never
actually fires in playtests, six possible failure modes account for ~all
real-world cases. This skill walks all six in one shot and reports the
specific blocker plus a suggested patch.

This applies equally to **activated / modal abilities**, not just whole cards —
"the AI never activates this ability" is the same six-step tree (drawn →
deployed → ability offered as a legal action → value-scored above its fire
threshold → precondition met → cost payable → out-competes the turn's other
plays). The SCP verb-redesign "inert bombs" (2026-05-29) were exactly this:
6 signature abilities that passed every *effect* gate (`/test-interceptors`
green — the effect fired correctly when invoked) yet fired ~never in real games,
because nothing checked the *fire* path. **`/test-interceptors` answers "does the
effect happen when triggered?"; this skill answers "does the AI ever trigger it?"
— run both.** That class of bug stayed invisible for ~9 commits because this
diagnostic was Pokemon-only and the recipe never called for it. **SCP support
has since been added** (see "Engine support" / "SCP support" below).

There is a third failure one rung below this skill: the AI fires the ability
correctly, but the win-condition **mechanism** it feeds is an orphaned engine hook
with no production caller, so the payoff counter never moves and the archetype is
unwinnable by its own plan (the SCP wurm/rift/leyline/spark substrate bugs,
2026-05-29). If `/card-fire-debug` reports an ability *does* fire yet the deck still
never executes its game plan, audit the mechanism for a dead caller — see the
"dead-caller audit" in `/test-interceptors`. Effect → mechanism → fire: a card is
only done when all three pass.

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
- `--engine` (`pokemon` | `scp`) — engine to use. Auto-inferred from the `--p1`
  deck name when omitted (an SCP deck → `scp`); set it explicitly to be sure.
- `--difficulty` (SCP only) — `easy` | `medium` | `hard` (default `medium`; the
  Pokemon-centric default `balanced` is normalized to `medium` for SCP).

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

**Pokemon and SCP** are supported. The engine is inferred from the `--p1` deck
name (an SCP deck → SCP engine), or set it explicitly with `--engine scp`.
Adding a further engine means:

1. Plug in the engine's legal-action / play discovery (mirror
   `_run_pokemon_diagnostic_game`'s use of `legal_pokemon_actions`, or the SCP
   probe's battlefield + event-log sampling).
2. Wrap the AI adapter's scorer methods (look for the engine's
   `<engine>_adapter.py::_score_*` / value-estimator methods).
3. Map "card type → eligibility precondition" for Step 2.

The decision tree itself (Step 1 through Step 6) is engine-agnostic —
only the per-engine probe needs to be added.

### SCP support

```
python scripts/play/diagnose_card_fire.py \
  --card "SCP-0863 Anomalous Specimen" \
  --p1 SCP_site19_containment --p2 SCP_black_queen_cell \
  --games 5 --max-turns 80 --engine scp
```

SCP is the **asymmetric** Foundation-vs-Chaos-Insurgency engine (`src/engine/scp.py`),
not the old symmetric "SCP-1" — so it has no activated-ability *scorer* to instrument.
"Fire" here is simpler and stricter: **the heuristic AI actually plays the card in
self-play** (CLAUDE.md's level-3 / AI-dead gate). The probe is asymmetry-aware:

- Pass **one Foundation deck and one Insurgency deck** to `--p1`/`--p2` in either order
  (the probe orders them; two same-faction decks is a hard error). Deck names are keys of
  `src.cards.scp.decks.SCP_FOUNDATION_DECKS` / `SCP_INSURGENCY_DECKS`.
- `--difficulty` is `easy` / `medium` / `hard` (the script-wide default `balanced` is
  normalized to `medium`).

`_run_scp_diagnostic_game` runs the real `scp.setup_scp_game` + `SCPAIAdapter` self-play
(the same wiring as `tests/test_scp_selfplay.py`, the canonical SCP fire gate), then
attributes plays by matching the `object_id` in `SCP_INSTALL` / `SCP_ACTIVATE` events back
to the card name — exact per-card attribution, since `play_card` emits `SCP_INSTALL` for
every kind (anomaly/layer/asset/tool/operative/operation/event). `diagnose_scp` walks a
short tree:

0. **In a deck** — counted against the `--p1`/`--p2` builders.
1. **Drawn** — hand membership across the games (a play implies it was drawn). SCP games
   can close fast, so a 1-of payoff may stay undrawn — bump copies or `--games`/`--max-turns`.
2. **Played by the AI** (`SCP_INSTALL`) — the fire for every card. A drawn-but-never-played
   card is a **level-3 (AI-dead)** gap: the effect may be correct but no decision path in
   `src/ai/scp_adapter.py` picks it. Look at `_foundation_action` (anomalies / layers / ops /
   assets) or `_insurgency_action` (breakers / events / operatives) for a branch that
   recognises and affords the card.
3. **Activated** (`SCP_ACTIVATE`) — only for assets/tools that carry an `scp_ability`. Played
   but never activated → `WARN`: check that the adapter calls `scp.activate_ability` for that
   effect class, that `scp_ability_ap` / `scp_ability_cost` are affordable while it is
   installed, and that the activation precondition is ever met (e.g. Site Director's draw fires
   only on a thin Foundation hand — a real but narrow window, ~1 fire / 48-game matrix).

This is the FIRE gate only. A card the AI *plays* whose `effect_fn` returns `[]` is a
**level-1 (effect-dead)** bug — that is `/test-interceptors` (and `tests/test_scp_cards.py`),
not this tool. A correct effect wired to a win-condition hook with no engine caller is
**level-2 (mechanism-dead)** — grep the `apply_*` / `_fire_*` hooks for a real caller.

The regression guard for this whole path is `tests/test_scp_card_fire.py` (pytest-collected,
so the live-engine wiring can't silently rot the way it did when the symmetric engine was
deleted on 2026-05-31 and the probe kept importing `src.engine.scp_abilities`).
