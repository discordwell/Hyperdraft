# Finance TCG — Polish Punchlist (iter 1)
_Generated: 2026-05-09 | /ng-plus --game finance_

---

## P0 — Interceptors
- **Pass rate: 48/48 (100%)** — 15 intentionally skipped (engine gaps, not regressions)
- Zero failures; zero errors.

## P5c — Smoke Tests
- `test_finance_interceptors.py`: **48/48 PASS**
- `test_finance_smoke.py`: **PASS** — 13-turn game, both AIs played cards and declared attackers

---

## P5b — Wet-Test Bug Fixed

### BUG (Fixed): Attack declaration available during SETTLEMENT
- **Root cause**: `selectableMyTraders` in `finance.tsx` was enabled whenever
  `isMyTurn && !isCombatBlockStep`, including SETTLEMENT phase. But
  `_run_combat()` reads `attackers_declared` BEFORE Settlement starts and
  `fin_turn_state.attackers_declared` resets to `[]` at each turn start —
  so any attackers declared in SETTLEMENT were silently discarded.
- **Fix**: Added `inTradingSession` guard (`currentPhase === 'TRADING_SESSION'`)
  so attacker selection UI only appears during TRADING SESSION.
- **Verified**: Combat damage now resolves correctly (Codex Ultra: 30 → 25).

---

## P5d — Plan Drift (Tournament: 4 games/matchup)

| Deck | Winrate | Avg Turns | Plan Target | Drift |
|------|---------|-----------|-------------|-------|
| FINA_dark_arbitrage | **83.3%** | ~19 | T8–T10 combo | HIGH — Dark Pool combo engine-broken (bug 15); wins via goodstuff midrange instead |
| FINA_derivatives | 66.7% | ~18 | Mid-range control | Moderate — performing above par |
| FINA_quant | 33.3% | ~21 | Control/wall | On-plan as control; walls hold but not enough win condition |
| FINA_high_frequency | 16.7% | ~20 | Close T11 | HIGH — plan says T11 close; actual average ~20 turns |

### Key drift findings
1. **HF closes too slowly**: plan targets T11 lethal with 4 Traders + DMA spike; actual
   games average ~20 turns. HF hand starves T20+ without Traders. Deck needs either
   more card draw or a secondary win condition before T20.
2. **Dark Arbitrage identity mismatch**: deck is designed as a Dark Pool combo deck
   but engine bug 15 (`_play_card_action` lacks `_dark_pool` branch) means all DP
   Orders go to GY without staging. Hidden Accumulator / Stealth Position Builder
   effects never fire. Deck wins by accident via wide cheap-body midrange. This is a
   **known blocker** — tracked as engine bug 15 in the strategy doc.
3. **Meta is DA-dominant**: at 83.3%, Dark Arbitrage is overcentralized. If bug 15
   were fixed (enabling actual combo play), DA could become even stronger or shift to
   fragile — needs retest post-fix.

---

## P3 — Visual Polish (Applied, build passes)

All visual enhancements verified in browser:
- ✅ Ticker tape scrolling (12 market items, 60s CSS animation)
- ✅ CRT scanline overlay rendering
- ✅ Segmented capital reserve bars (10 blocks × 3HP)
- ✅ Phase pulse animation on TRADING SESSION / SETTLEMENT labels
- ✅ Market Feed live indicator (green dot)
- ✅ Zero console errors

---

## Open Issues / Watchlist

| Priority | Issue | Location |
|----------|-------|----------|
| P1 | Dark Pool combo completely broken — DP Orders never stage | `finance_turn.py` `_play_card_action` missing `_dark_pool` branch (bug 15) |
| P2 | Alpha Strike power buff: first-declared attacker gets disproportionate power boost (bug 18) | `finance_combat.py` multi-attacker power calculation |
| P2 | Block-window race condition: blocks sometimes ignored when game advances past block window (bug 23) | `finance_turn.py` block collection timing |
| P3 | FINA_high_frequency hand starvation post-T20 — no draw engine | Deck design; add 2× Compulsive Research or cantrip |
| P4 | Dark Arbitrage metagame dominance (83.3%) likely driven by wide cheap bodies, not design intent | Rebalance when bug 15 fixed |

---

## Ultra Loop Summary (P2)

- **5 iterations single + 5 double** completed
- Strategy doc updated with: Alpha Strike ordering, Liquidity pool timing, block-window exploit, DA midrange fallback line
- Bias preset `aggressive` patched: +3 Trader-deploy weight, -2 hold-order weight
- Heuristic encoder added: early-turn deploy priority, DMA declare-first ordering

---

## Convergence

- P0: 100% ✅
- P4 regression: none ✅  
- P5d drift flags: 2 HIGH (HF timing, DA identity) — structural issues, not regressions
- Punchlist: 5 open items, all pre-existing engine gaps
- **Verdict: CONVERGED for visual/UX layer. Engine gaps (bug 15, 18, 23) tracked separately.**
