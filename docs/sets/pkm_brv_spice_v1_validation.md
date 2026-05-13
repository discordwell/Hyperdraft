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

# Event trace for a specific matchup
python -m scripts.play.brv_spice_event_trace --p1 dimir --p2 golgari --games 5

# Refresh the depth audit (should still show 9 spicy / 5 build-around)
python -m src.depth.report --set BRV --summary-only

# Tests
python -m pytest tests/test_depth_rubric.py tests/test_brv_spice_v1.py -q
```
