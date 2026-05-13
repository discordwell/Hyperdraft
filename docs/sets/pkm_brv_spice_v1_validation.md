# BRV Spice Pack v1 — Stage 3 Play Validation

> Companion to `pkm_brv_spice_designs.md` (Stage 1) and the post-pass
> results section in `pkm_brv_depth_audit.md` (Stage 2). This doc captures
> the **play-level** validation — do the new cards actually do something
> interesting when the game runs, not just score well on the rubric?

## Smoke test — engine integrity

`scripts/play/brv_spice_smoke.py` ran 30 heuristic-AI vs heuristic-AI
games (3 games each across 10 circular guild matchups, max 30 turns).

- **0 crashes**
- 24 of 30 games completed within 30 turns (prizes emptied)
- Avg game length ≈ 20 turns
- Total runtime: 0.4s

**Verdict**: the spice cards integrate cleanly. No null derefs, no
infinite loops, no PendingChoice deadlocks.

## Event-trace audit — do cards actually fire?

`scripts/play/brv_spice_event_trace.py` runs N games on a chosen
matchup, monkey-patches the pipeline `emit()`, and counts how often
each spice card's effects actually execute.

### Dimir vs Golgari (5 games, max 40 turns)

| Spice EventType | Emissions |
|---|---|
| PKM_LOST_ZONE | 3 |
| PKM_REVEAL | 4 |
| PKM_REVEAL_HAND | 8 |
| PKM_FORCE_SWITCH | 0 |
| PKM_MOVE_ENERGY | 0 |
| PKM_PRIZE_TAX | 0 |
| PKM_COST_REDUCTION | 0 |

| Card | In deck? | Plays | Effect-fires |
|---|---|---|---|
| Dimir Interrogation | ✓ Dimir | 20 | ~8 reveals = 40% of plays resolve fully |
| Tox-Pawpsule | ✓ Dimir | 16 | poison applied, but PKM_REVEAL_HAND only logged via Dimir Interrog (not Tox) |
| Cremate | ✓ Golgari | 12 | **only 3 LZ moves** — AI plays Cremate with non-Pokemon hand cards 75% of the time |
| Jarad ex (evolution event) | ✓ Golgari | 4 | Evolved 4×; **Lich's Bargain attack never fired** |
| Mirko Vosk Lost Recall | ✓ Dimir | **0** | AI never attacks with Mirko |
| Voidmage Apprentice | ✓ Dimir | **0** | AI never attacks with Voidmage |

### Azorius vs Simic (5 games, max 40 turns)

| Card | In deck? | Plays | Effect-fires |
|---|---|---|---|
| Pithing Drone | ✓ Azorius | 7 | KO trigger never fires (opponent's attacks don't KO the holder's Pokemon enough) |
| Negate the Negation | ✓ Simic | 7 | **0 LZ emissions** — AI plays the card even when opp has no Tools (wasted) |
| Jace, Memory Adept | ✓ Azorius | 3 plays (placed on bench) | **0 attacks** with Jace |
| Niv-Mizzet's Quandary | ✓ Azorius | 0 plays | Never drew or never played |
| Tezzy's Test | — | not in either deck | |

**Total**: 0 PKM_REVEAL_HAND, 0 PKM_LOST_ZONE, 0 PKM_FORCE_SWITCH, 0
PKM_PRIZE_TAX events across 5 games.

## Diagnosis

The spice cards are STRUCTURALLY in the decks but the **heuristic AI
doesn't pilot them well**. Three distinct failure modes:

1. **Build-around Pokemon attacks never fire.** Mirko Vosk (Stage 1
   Psychic), Jace (Basic Psychic), Voidmage Apprentice (Basic Psychic),
   Aurelia ex's Battalion Mark, Obzedat ex's modes — the AI either
   doesn't promote these Pokemon to Active or doesn't choose their
   higher-cost/lower-damage attacks. This is a generic Pokemon-AI gap,
   not specific to the new cards.

2. **Trainer Items play even when conditions aren't met.** Cremate
   plays 12× but only 3 LZ moves resolve (hand mostly Trainers and
   Energy that aren't Pokemon/Energy from the filter perspective —
   actually Energy IS eligible but the AI plays Cremate with empty
   hand). Negate the Negation plays 7× with 0 LZ emissions (no opp
   Tools exist when played). The AI plays Items eagerly without the
   contextual gates the cards assume.

3. **Multi-mode cards default to the safe mode.** Tezzy's Test has 3
   modes with a heuristic mode-picker; only the first mode fires
   when triggered. Obzedat ex's Spectral Decree has 2 modes (KO bench
   or prize tax) — the heuristic picks one but neither was observed
   firing in 5 games (Obzedat never reached Stage 2).

## What this means for the audit

The depth rubric **correctly identified the cards as spicy/build-around
by STRUCTURE** — they touch the Lost Zone, force opponent decisions,
emit asymmetric events, etc. But the rubric does NOT measure whether
the AI knows how to USE those structures. The "mid" critique the user
flagged at the top of this project was about user-facing play quality,
which has two ingredients:

- **Card design** (structural depth) → ✅ Fixed in Stage 2
- **AI piloting** (situational decisions) → ❌ Still mid for the heuristic AI

This is fixable but is OUT OF SCOPE for the depth heuristic. Either:

- Tune the heuristic AI to recognize the spice patterns (1-2 days of
  Pokemon AI work). Items: "don't play Cremate without ≥1 Pokemon in
  hand", "promote Mirko Vosk over Jarlet when you have ≥2 Pokemon in
  Lost Zone", etc.
- Use LLM pilots (the original `/ultra-loop` skill is built for this).
  LLM pilots played in the test environment would actually attack
  with Mirko Vosk and pick the right Cremate targets.

## Recommended next steps

In priority order:

1. **Pokemon AI heuristic tuning** (highest leverage, smallest scope) —
   patch `src/ai/pokemon_adapter.py` to add 5-10 "spice-card-aware"
   decision rules. This is what `/ng-plus`'s heuristic encoder phase
   would do. Quick win because the same rules help ALL spice cards.

2. **Spice pack v2** — implement the remaining 16 designs from
   `pkm_brv_spice_designs.md`. This further lifts diversity ratios.

3. **Full `/ultra-loop` double-mode session** — once AI heuristic is
   tuned, run 3+ iterations of LLM-pilot Dimir vs Golgari to validate
   the cards create real strategic decisions. The output is the
   strategy doc `docs/decks/<guild>_plan.md` per the pattern in
   `[[feedback_ultraloop_scratchpad]]`.

## How to reproduce

```bash
# Smoke test (30 games, ~0.5s, exit 1 if any crash)
python -m scripts.play.brv_spice_smoke --games-per-matchup 3 --max-turns 30

# Event trace for a specific matchup (Phase 4 — with archetype biases)
python -m scripts.play.brv_spice_event_trace --p1 dimir --p2 golgari \
  --p1-bias lz_engine --p2-bias lz_engine --games 5

# Refresh the depth audit (should still show 9 spicy / 5 build-around)
python -m src.depth.report --set BRV --summary-only

# Tests
python -m pytest tests/test_depth_rubric.py tests/test_brv_spice_v1.py tests/test_brv_spice_v2.py -q
```

---

## Phase 1–4 update (2026-05-13) — closing the "scored well / plays mid" gap

Pre-Phase-1 trace: 4/14 cards firing, modal "Decision Pressure" was
paper (no real choice point), Pithing Drone wasn't a real Tool, and
`pkm_apply_prize_tax` was a silent no-op bug.

### Phase 1 — Engine foundation (commit `a3c5517`)

- `prize_tax` bug fix in `_take_prizes` (`pokemon_combat.py`). Obzedat
  ex's mode B works for the first time.
- Real Pokemon Tool slot — `attach_tool` / `detach_tool` /
  `make_tool_setup` in `_tool_helpers.py`. Pithing Drone rewritten to
  use it; the interceptor's filter gates on
  `tool.state.attached_to`.
- `PendingChoice` migration for `pkm_modal_choice` and the 4 target
  helpers. Pokemon now has the same modal/choice infrastructure MTG
  has (`Game._process_choice` dispatcher hits `callback_data['handler']`
  for `pkm_modal_with_callback`).
- `PokemonAIAdapter.make_choice` + dedicated dispatcher in
  `src/ai/pokemon/choices.py`. AI's modal selection can override the
  card's heuristic_pick — surface for ultra-loop / LLM pilots.

### Phase 2 — AI heuristic tuning (commit `65b6cf1`)

- `TRAINER_SCORERS` extended with 10 spice-Trainer bias functions
  (`brv_spice_scorers.py`). Examples: Negate the Negation −100 with no
  opp Tool / +40 with one; Cremate +35 if hand has 3+ burnable cards;
  Pithing Drone +25 if Active is ex.
- New `ATTACK_SCORERS` registry consulted by `_score_attack` —
  card+attack-name keyed. 8 attack scorers (Mirko Lost Recall,
  Aurelia Battalion Mark, Voidmage Energy Drain, Obzedat Spectral
  Decree, Jarad Necrosurge + Lich's Bargain, Jace Mental Triage).
- New `EVOLUTION_SCORERS` registry — 4 evolution biases that promote
  Mirko Vosk / Jarad ex / Obzedat ex / Aurelia ex when their archetype
  preconditions are met.

### Phase 3 — Bias presets + strategy doc (commit `7745ab8`)

- `POKEMON_BIAS_PRESETS` (6 presets) in `src/ai/pokemon/biases.py` —
  orthogonal to `difficulty`, controls archetype style. `lz_engine`,
  `bench_swarm`, `control_disrupt`, `energy_denial`, `aggro_burn`,
  `balanced`.
- Adapter takes `bias=None` kwarg (additive to existing `difficulty=`);
  `set_player_bias(player_id, bias)` for AI-vs-AI matchups with
  different archetypes per side.
- `docs/strategy/pokemon.md` — 285-line strategy doc with archetypes,
  spice-card decision points, common pitfalls. Read by ultra-loop's LLM
  coach before each game.

### Phase 4 — Validation gauntlet

**Event-trace gate (re-run with archetype biases):**

- Dimir LZ vs Golgari LZ (5 games, both `lz_engine`)
- Azorius control vs Simic LZ (5 games, `control_disrupt` vs `lz_engine`)
- Boros swarm vs Orzhov control (5 games, `bench_swarm` vs `control_disrupt`)
- Izzet control vs Rakdos aggro (5 games, `control_disrupt` vs `aggro_burn`)

**Aggregated results (20 games, 4 matchups):**

| Card | Pre-Phase-1 | Post-Phase-4 |
|---|---|---|
| Voidmage Apprentice | 0 | 1 |
| Dimir Interrogation | 20 | 6 |
| Tox-Pawpsule | 16 | 12 |
| Cremate | 12 | 11 |
| Jarad ex (evolved) | 4 | 10 |
| Niv-Mizzet's Quandary | 0 | **5** |
| Jace, Memory Adept | 0 | **3** |
| Tezzy's Test | 0 | **12** |
| Obzedat ex | 0 | **5** |
| Sanguine Sacrament | 0 | **7** |
| Mirko Vosk | 0 | 0 |
| Aurelia ex | 0 | 0 |
| Pithing Drone | 0 | 0 |
| Negate the Negation | 0 | 0 |

**10/14 spice cards fire ≥1×** in their target matchups (gate met).

**All build-around payoff events fire ≥1×:**

| Event | Emissions | Build-around |
|---|---|---|
| PKM_LOST_ZONE | 15 | Mirko / Cremate / Negate |
| PKM_PRIZE_TAX | 3 | Obzedat ex mode B (fixed in Phase 1c) |
| PKM_FORCE_SWITCH | 2 | Niv-Mizzet's Quandary |
| PKM_MOVE_ENERGY | 1 | Niv-Mizzet's Quandary follow-up |
| PKM_REVEAL_HAND | 6 | Dimir Interrogation / Jace / Tezzy mode 3 |

**4 cards still not firing — diagnosis:**

These all have hard preconditions that heuristic-AI play rarely
satisfies:

- **Mirko Vosk** — needs Mirklet → Mirko evolution (turn ≥3) AND
  3-color energy attached ({P}{D}{C}). 60-card deck with 2 Mirko + 3
  Mirklet rarely hits the right hand within 30 turns. Bias-preset
  evolution scorer +25 × 2.0 multiplier registered; just situational.
- **Aurelia ex** — Stage 2 ex needing 3-stage evolution (Borblet →
  Borborgrew → Aurelia). 60-card decks rarely complete the chain.
- **Pithing Drone** — scorer prefers attaching to an ex Active; Azorius
  decks rarely have an ex Active in early/mid game.
- **Negate the Negation** — hard-gated −100 with no opp Tool. Symmetric:
  opp never plays Pithing Drone (same problem), so Negate sits dead.

These are **board-state preconditions**, not scorer bugs. The next
gauntlet step (LLM pilot games via `/ultra-loop`) is exactly the right
tool — LLM pilots build toward the archetype on purpose rather than
reacting opportunistically.

### Phase 4 — LLM pilot gauntlet (user-invoked)

The remaining Phase 4 steps are user-invoked because `/ultra-loop`
spawns parallel LLM pilot games:

```bash
# Seed LLM pilot game (single iteration to mine strategy notes):
/ultra-loop --game pokemon --mode single --iterations 1 \
  --ai-bias lz_engine --my-deck dimir --ai-deck golgari

# Use the pilot's scratchpad to flesh out docs/strategy/pokemon.md's
# "Update log" section, then:

# Full ultra-loop validation (coach updates presets per iteration):
/ultra-loop --game pokemon --mode double --iterations 3

# Final verification (one more pilot game with post-loop presets):
/ultra-loop --game pokemon --mode single --iterations 1
```

**Acceptance criteria for full Phase 4:**
- All ultra-loop iterations complete without crashes
- Coach updates ≥ 2 preset entries in `biases.py`
- Both archetypes hit ≥ 30% win rate after iter 3
- Final pilot's per-turn rationale references the post-loop presets AND
  uses spice plays the seed pilot wanted but couldn't realize (Mirko's
  Lost Recall, Aurelia ex's Battalion Mark on a full bench, etc.)
