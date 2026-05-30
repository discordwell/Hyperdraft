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

### SCP support (implemented 2026-05-29)

```
python -m scripts.play.diagnose_card_fire \
  --card "SZB Public Spectacle Suite" \
  --p1 site_zero_masquerade --p2 site_zero_masquerade \
  --games 4 --max-turns 25 --engine scp
```

`_run_scp_diagnostic_game` wraps `_estimate_ability_value`/`_cost_value` to
capture the value math at consideration time, samples hand + battlefield
presence each turn, and counts `SCP_ABILITY_ACTIVATED`. `diagnose_scp` leads
with the ground-truth fire count, then explains a non-fire via the six steps
below. The original "inert bombs" diagnosis (walked by hand) IS this probe:

1. **Drawn** — hand membership across the playtest. SCP twist: games are short
   and breach-dominated (a self-mirror can end in 4-6 turns), so a 1-of
   signature card may never be drawn at all (Apollyon Convergence Array: 0
   hand-instances in 3×50-turn eldrazi games). FAIL → bump deck count, add a
   tutor, or the deck/format is too fast for the payoff (a deck-speed item).
2. **Legal action** — for an activated ability: does `legal_scp_actions` emit
   `SCP_ACTIVATE_ABILITY` (one per modal mode) when the card is on the
   battlefield, un-exhausted, and affordable? For deployment: does the card get
   played from hand via `open_dossier` (works for every SCP card type)?
3. **Scorer positive** — SCP has TWO scorers, check both: deployment is
   `scp_adapter.score()` (a bomb must out-rank generic rank-2 facilities — see
   `_carries_signature_bomb`); activation is `_consider_activated_abilities`,
   which fires iff `_estimate_ability_value(value_hint) − _cost_value(cost) >
   _ability_fire_threshold`. The flat 0.5 `exhaust_self` cost-weight lived here
   (put gain~1.0 facility bombs below the bar).
4. **Precondition met** — `precondition_fn` AND a conditional
   `value_hint`/`custom_value_fn` that returns 0.0 until the condition is met
   (the "win-more cliff": Containment Singularity scored 0 below 2 contained).
   SCP analog of the evolution-prereq step. Credit *progress toward* the
   condition, not only the turn it's crossed.
5. **Cost payable** — `can_pay_scp_cost` (ethics is INVERTED — paying reduces
   debt; `exhaust_self` requires un-exhausted). CRITICAL: facility exhaustion +
   `once_per_turn` counters must reset each turn (`reset_turn_abilities`) or the
   ability is silently once-per-GAME — a fire-path bug that looks like a value
   bug.
6. **Ranked competitively** — deployment: the bomb's `score()` rank vs the rest
   of hand (a 1-of at flat rank 2 loses every deploy race); activation: does its
   value clear the threshold, or does it lose to "do nothing"? (Public Spectacle
   net 0.50, not > 0.50 — missed by epsilon.)

Wrap `scp_adapter.score()`, `_consider_activated_abilities`,
`_estimate_ability_value`, `_cost_value`; sample `legal_scp_actions` membership
and `can_pay_scp_cost`; drive games via the `scp_tournament.run_one_game` wiring.
Until this is coded, the cheap stand-in is to instrument `SCP_ABILITY_ACTIVATED`
in the event log across a tournament (what the re-validation probe did).
