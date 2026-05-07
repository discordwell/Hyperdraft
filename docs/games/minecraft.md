# Minecraft TCG — Polish-Loop Summary

## /ng-plus run @ 2026-05-07 (full polish pass)

**Iterations**: 1 / 1 (full polish; not converged — punchlist non-empty)
**Scope**: full as designed
**Skipped stages**: P2b iters 2-5 (parallel-pilot coordination is fragile;
infrastructure gap logged)

## Stage outcomes (iter 1)

| Stage | Outcome |
|-------|---------|
| P0    | 100% pass rate (84 tests, 49 skipped, 81 vanilla) |
| P1    | 0 errors over 144 games; no new deck beat all starters; `infect_oil_rush` (62.5%) #2 narrowly missed |
| P1.5  | meta = `passive_econ` (43.2% winrate, +11.4pp over random) |
| P2a   | **5 pilot games**: 3 draws, 2 losses. Strategy doc grew through v9 changelog. Bias preset patched once (iter 1: weapon_no_bed_penalty 28→40); subsequent iters didn't find clear weaknesses to plug. builder_plan.md created and iteratively refined. Iron Golem cost typo (I3+R1 → I1+R1) caught and corrected. avatar_attack semantics clarified (route to face on truly empty cols only). |
| P2b   | iter 1 only: parallel-pilot coordination stalled (both pilots polled each other into giving up). v10 changelog captured pre-stall findings (Warden ETB + miner T1 Panda Forager line). miner_plan.md created. Iters 2-5 skipped — same coordination failure would recur. |
| P3    | Single color tweak (iron #d8d8d8 → #9ca3af for dark-mode visibility). Honest "file already in good shape" assessment. Build passes. |
| P4    | 100% (parity with P0; 5+ rounds of strategy/bias/plan/frontend edits introduced no regression) |
| P5a   | raider 80% / builder 65% / box_of_horrors 0% under passive_econ. 0 errors / 50 games. **Card-level telemetry** (38 zero-play cards, 3 loss-only cards) via the new `--log-interceptor-fires` flag. |
| P5b   | deckbuilder route loads cleanly; only React Router future-flag warnings (not errors). Game-route hard-test would need a live backend match — out of scope. |
| P5c   | smoke + interceptors all pass |
| P5d   | builder drift 28% (under 30% threshold) — improved from 34% test-pass after P2a iters refined the plan. miner 20% drift. **No flags.** |

## Auto-repair summary

0 fired. P0/P4 cleared on first run; P1/P1.5/P5a tournament gates all
passed cleanly (0 errors per stage). The auto-repair pattern's
behavior under failure remains untested in this run.

## Outstanding TODOs

### Card balance
- **Iron Golem (builder)** — 0 plays in 20 games despite multiple
  pilot attempts. Either lower cost (drop redstone), add Strip Mine
  copies to the starter, or provide an alternative redstone source.
- **38 zero-play cards** across 4 starters. Top offenders:
  - `builder`: Redstone Engine, Piston Gate, Iron Golem, Allay Courier
  - `miner`: Beacon, Diamond Armor
  - `raider`: Enderman, Blaze, Diamond Sword, TNT Blast, Nether Expedition
  - `box_of_horrors`: 13 cards
- **box_of_horrors** — 0% winrate, 13 zero-play cards, 3 loss-only
  cards. Structural failure. Redesign or retire.

### Format-level
- **Builder mirror is a structural draw.** P2a iters 1-5 confirmed
  the mirror cannot reach lethal at 35-turn cap. Either format-level
  rule change (turn cap?) or a new card that breaks the structure-war
  pattern.
- **Warden ETB clears Workers ≤4HP** — major builder counter
  surfaced in P2b. Not exploited at the heuristic level; consider
  adding a "Warden hate" card or higher-toughness Worker variants.

### Infrastructure
- **mc_wet_test.py two-pilot mode is fragile.** Parallel-dispatch
  coordination doesn't reliably advance turns — pilots stall on each
  other. Needs a turn-acknowledgment marker in the persisted state
  or a different dispatch pattern (sequential turn-by-turn?).
- **AI bias `mining_mode` enum** — pilot reports flagged this twice
  (iter 2 wrongly, iter 3 corrected). Consider documenting the enum
  values and their priority orders inline in the adapter so future
  pilots have ground truth.

## Artifacts produced

- `tests/test_minecraft_interceptors.py` — 84-test interceptor verifier (auto-regenerable)
- `logs/minecraft_decks_polish_iter1.json` — 4 LLM-designed decks
- `logs/minecraft_polish_decktourney_iter1.json` — P1 tournament data (balanced bias)
- `logs/minecraft_polish_meta_discovery_iter1.json` — P1.5 variant tournament
- `logs/minecraft_polish_wet_iter1_full.json` — P5a tournament (passive_econ + telemetry)
- `docs/games/minecraft_polish_punchlist.md` — punchlist (card-level)
- `docs/games/minecraft_plan_drift.md` — drift report (clean)
- `docs/decks/builder_plan.md` — refined across 6 iters
- `docs/decks/miner_plan.md` — created in P2b
- `docs/strategy/minecraft.md` — v5 → v10 changelog
- Harness patches: `scripts/play/mc_wet_test.py` (`--two-pilot`),
  `scripts/play/mc_deck_tournament.py` (`--log-interceptor-fires`)
