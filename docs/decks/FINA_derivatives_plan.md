# FINA_derivatives — Plan

## Composition summary

Leverage-counter-management deck. Trader chassis: Options Desk Intern (1c, 2/2), Underlying Asset Runner (UAR, 2c, 3/3 Lev 1), Delta Hedger (3c, 2/4 Lev 2 + damage reduction), Theta Decay Trader (3c, 2/3 Lev 2 + pre-MC free counter-remove), Rho Opportunist (3c, 3/2 Lev 1 + draw on counter-add), Vega Amplifier (4c, 4/3 Lev 3 + lord +1/+0 to other Leverage Traders), Gamma Scalper (4c, 3/3 Lev 3 + lethal-tick safety valve, once per game), Convexity Rider (4c, 2/5 Lev 2 + Short-Sold recursion), Hedge Fund PM (5c, 5/4 Lev 2). Counter-removers: Theta Decay Trader (free), The Black-Scholes Model (3c sorcery, pay 1 to remove), Carry Trade (3c — Liquidity refund per Leverage counter), Theta Decay Collar (2c Derivative, attach for +1/+2 + counter-remove). Auras/Equipment: Synthetic Collar, Gamma Amp, etc. (per-Derivative scaling).

## Hypothesis: deck identity (revised iter-2)

**The deck is NOT "stack Derivative auras on one Trader"** — that interpretation came from the prompt and starter doc but is wrong on inspection. Both iter-2 pilots converged on a different read:

> Derivatives is a **Leverage-counter-management** archetype. Leverage = double-edged: +1/+0 power per counter, -1 capital per counter at MARKET_CLOSE. Each Leverage Trader is a ticking time bomb. The win condition is *managing* the counter tax via counter-removers (Theta Decay Trader, Black-Scholes, Theta Decay Collar). Without management, the deck self-destructs by T8-T10.

Derivative auras (Synthetic Collar, Gamma Amp) are **secondary** — they scale the eventual finisher, but you have to survive long enough to assemble them, which requires NOT dying to your own Leverage tick.

## Critical pre-deploy check (AI/pilot decision rule)

Before deploying any Leverage Trader, the AI/pilot **MUST** compute:

```
expected_leverage_tax = sum(Lev_counters across own Leverage Traders) + new_trader_lev
projected_capital_after_MC = current_capital - expected_leverage_tax
```

**Refuse to deploy** if `projected_capital_after_MC < safety_margin` (suggested: 5) AND no counter-removal source is in play (Theta Decay Trader, Black-Scholes Model in play, Theta Decay Collar attached).

This is implemented as `_expected_leverage_tax(state, player_id)` in `src/ai/finance_adapter.py` (iter-2).

## Win condition

**Plan A (primary, confirmed iter-4): Collar + Σlev ≤ 3 → ~1.6 cap/turn drain → T11 flood wins.** Play Theta Decay Collar early (T2-T3) on a cheap Trader body. Stack DH (Lev 2) + Rho or TDT (Lev 1) = Σlev 3, no more. With Collar removing 1 counter pre-MC, effective net tick = (Σlev − 1) = ~2/turn, but observed ~1.6/turn (Collar fires BEFORE tick, reducing counter count first). Capital loss is 8 points over 5 turns vs a 33-face attack sequence. **Attack with DH (5-power) first, then stack remaining bodies — 3-body waves deal 12+ face from T9, lethal by T11.**

**Plan B (race insurance): Vega Amplifier lord swing.** Vega Amp's +1/+0 to other Leverage Traders fires correctly per iter-2. If you can drop Vega Amp + 2 Leverage Traders + Black-Scholes Model in the same window, the buffed swarm closes T9-T11. Risky — Lev 3 + Lev 2 + Lev 1 = 6 self-tax/turn unless Black-Scholes eats one each turn.

**Ticker: The "×1.7 bug factor" is NOT active in Plan A.** Iter-2 observed ×1.7 only in the ETB-double-add edge case (Bug 14). With Collar active in normal play, net tick = (Σlev − 1), NOT Σlev × 1.7. Revise capital projections accordingly.

## Target turns (Plan A)

- **T1**: Options Desk Intern (1c, 2/2). No leverage tax. Clean tempo body.
- **T2**: Pass or Theta Decay Collar (2c) staged for the upcoming Trader.
- **T3**: Delta Hedger (3c, 2/4 Lev 2). Tax = 2/turn. Or Theta Decay Trader (3c, 2/3 Lev 2 + free pre-MC remove) = effective 1/turn tax.
- **T4-T7**: ONE more Leverage Trader on board MAX. Keep total Σleverage ≤ 3 unless Black-Scholes is in play. Cast Black-Scholes Model (3c) ASAP — it's the deck's safety valve.
- **T8-T11**: Stack Derivatives on the sticky host. Gamma Amp, Synthetic Collar increase the per-Derivative scaling. Vega Amplifier lord buff if multiple Leverage Traders survived.
- **T12-T15**: Lethal swing with a buffed 7-9 power Trader.

## Mulligan policy

- **Auto-keep**: hand with Theta Decay Trader OR The Black-Scholes Model (counter-removers). One of these is required to survive past T8.
- **Auto-keep (good)**: low-curve hand with Options Desk Intern + 1 Leverage 1-2 Trader + 1 counter-remover.
- **Auto-mull**: all Leverage 2-3 Traders, no counter-removers. This hand kills you by T10.

## Play priorities (order)

1. **NEVER deploy a Leverage Trader without computing expected_leverage_tax first.** AI heuristic enforces this; pilots must do it manually.
2. **Theta Decay Trader is the deck's safety valve.** Its free pre-MC counter-remove is uncosted Liquidity-wise. Always deploy if you have 2 Leverage Traders out.
3. **Black-Scholes Model > Carry Trade in priority.** BSM removes counters; CT just refunds Liquidity. BSM is the survival card.
4. **Vega Amplifier (4c, 4/3 Lev 3) is a 3-self-damage liability.** Only deploy when board has at least 2 other Leverage Traders to benefit from the +1/+0 lord, AND Black-Scholes is in play.
5. **Avoid stacking 4+ Leverage Traders simultaneously.** Iter-2: 5 Leverage Traders → 16 self-damage in one MC, lost from 12.
6. **Underlying Asset Runner (2c, 3/3 Lev 1) is overcosted at 2 mana net of Leverage tax.** After 3 turns of -1 capital, it's a -1 net body. Treat as a tempo card, not a stretch keep.
7. **Auto-attach Derivative on play targets your highest-power Trader.** Untested in iter-2 (no Derivative was played). Carry forward to iter-3.

## Self-loss risk profile

| Σleverage | Tax/turn | Safe with | Lethal in (from 30) |
|-----------|----------|-----------|---------------------|
| 1         | 1        | nothing   | 30 turns           |
| 3         | 3        | 1 counter-remover | 10 turns   |
| 6         | 6        | Black-Scholes + Theta Decay | 5 turns |
| 9         | 9 (or 16 with bug) | nothing survives | 2-3 turns |

**Iter-2 observation: actual tick exceeded Σleverage by ~1.7×.** Until the tick-doubling bug is fixed, project tax as `Σleverage × 1.7` for capital-survival math.

## Anticipated weaknesses

- **Self-damage is the primary loss vector.** Iter-2: P1 lost from 12 → -4 with no opp combat damage. Manage Leverage or die.
- **Slow start.** No <3-cost Leverage Traders means T1-T2 are weak (only Options Desk Intern is a 1-cost play).
- **Counter-remover density too low.** Currently ~4 counter-removers across the deck. Probably need 6-7 to sustain midrange. Iter-3 candidate.
- **Auto-attach untested.** If the auto-attach mechanic is silently broken or confused by no-Trader scenarios, the Derivative half of the deck is dead. Iter-3.
- **Off-Exchange Position from Dark Arbitrage is a hard counter** — staged into Dark Pool, it lands -3/-0 on the highest-power Trader during opp's trading_session, neutering finisher math.

## Self-loss risk profile (revised iter-4)

| Σleverage | Collar? | Net tick/turn | Safe turns (from 30) |
|-----------|---------|---------------|----------------------|
| 1         | no      | 1             | 30 turns             |
| 3         | YES     | ~1.6          | ~19 turns (observed) |
| 3         | no      | 3             | 10 turns             |
| 6         | YES     | ~5            | 6 turns              |
| 9         | no      | 9 (or 16 ETB) | 2-3 turns            |

**Key update from iter-4**: With Collar active, effective tick rate ≈ (Σlev − 1), not Σlev × 1.7. The ×1.7 safety multiplier in `_filter_trap_cards` remains as a conservative guard but overstates actual risk for Plan A.

## Iteration log

- **2026-05-08 (iter-2 v2, post 20-bug-fix batch)**: vs FINA_dark_arbitrage (LLM Pilot B). **WON T23**; final P1=3, P2=−7. **First Derivatives two-pilot win — leverage management is now PLAYABLE.** Lethal swing T23: HFPM 3 + Rho Opp 5 = 8 face into P2 at 1, no blockers. Key findings:
  - **Bug 10/14 Leverage Tick doubling FIXED.** Σleverage tax matches exactly: T17 EOT Σ=2 → -2 capital. T21 EOT Σ=3 → -3 capital. **No 1.7× or 2× doubling observed.** The `leverage_bug_multiplier = 1.7` safety factor in `_filter_trap_cards` is now a conservative guard, not an active correction.
  - **Bug 19 Leverage power query FIXED.** TDT 5/3 (3+Lev2), UAR 4/3 (3+Lev1), HFPM 6/4 (4+Lev2). Counters dynamically contribute to displayed power.
  - **Bug 15 Dark Pool staging FIXED for opponent.** P2's combo actually fired this game (HACC pumped to 3/3, BTS killed UAR, OEP nerfed HFPM -3/-0). Confirms DA archetype is playable post-fix.
  - **Theta Decay Trader's free counter-remove WORKS.** TDT had Lev 2, removed both counters pre-MC for free. T5→T7: TDT displayed power dropped 5/3 → 3/3 confirming remove fired.
  - **Big bodies trade well into DA's smaller bodies.** HFPM 6/4, DH 5/4, UAR 4/3 vs DA's 2/2-3/4 roster.
  - **NEW bug #24**: Vega Spike resolves but does NOT add Leverage counters. Mana consumed (9→6), strategy → graveyard, target counters unchanged. Cut Vega Spike from deck or fix the COUNTER_ADDED event handler.
  - **NEW bug #25**: Synthetic Collar QUERY priority issue. Attached to TDT but TDT stayed at 3/3 (expected 4/4). Same fix-pattern as #19.
  - **NEW bug #26**: Hidden Aggression appears to deal 1 face damage on cast (suspected). T5→T6 capital drop -3 when expected -2 from Lev. Speculative; needs unit test.
  - **NEW bug #27**: Trample inconsistent (partially on / partially off). T15 went 7 face when 5 (no trample) or 9 (full trample) was expected.
  - **Bug 1 attacker-side edge case**: T19 UAR3 (4/3) blocked by HACC (2/2) → UAR3 took 2 dmg, has 3 toughness, should LIVE — but DIED. Blocker-side fix landed cleanly; attacker-side may have a separate damage-application path.
  - **Strategy update**: 2 Traders + Rho Opportunist build works for race scenarios when DP combo is firing on opp's side. The race window opens once P2's HACC dies (typically T7-T9 from blocks).
  - **Heuristic for Pilot A**: When P2 has SS Traders, the SS does NOT prevent blocking. Multiple unblocked attackers needed for guaranteed lethal due to trample being OFF.
  - Pilot reports: `logs/finance_ultra_iter2v2_pilotA.md`, `logs/finance_ultra_iter2v2_pilotB.md`.

- **2026-05-08 (iter-4 single, P2a iter-4)**: vs FINA_dark_arbitrage (heuristic AI). **WON T11**; P1=22, P2=−3. **First Derivatives win on record.** Theta Decay Collar T3 on ODI → DH (Lev 2) T5 → Rho (Lev 1) T7. Σlev=3 cap drain ~1.6/turn (net 8 capital lost across 5 turns). Attack waves: 7 face T7, 12 face T9, 14 face T11. DA AI deployed zero Leverage Traders (over-conservative heuristic; encoder fix applied). Bug 19 scope confirmed: Derivatives cards display CORRECT Leverage-boosted power (Bug 19 is DA-only). Collar counter-remove fires correctly pre-MC. Auto-attach confirmed for Protective Put (on Rho) and Shadow Protocol Module (AI's DERIVATIVE on HA). Pilot report: `logs/finance_ultra_iter4_single_pilot.md`.
- **2026-05-08 (iter-2)**: vs FINA_dark_arbitrage (Pilot B). **Lost** in 9 turns; final P1=-4, P2=15. Pilot A self-graded the loss as primarily caused by stacking 5 Leverage Traders with no counter-removal cards drawn. Vega Amplifier lord effect verified working (+1/+0 to other Leverage Traders displayed). Multi-attack mechanically works. Off-Exchange Position from P2 silently no-op'd in one cast (DP-staging requirement?). 5 new engine bugs flagged (see strategy doc punch list). **Deck identity revised: leverage-counter-management, not auras-on-trader.**

## Open questions for iter-5

- ~~Does the auto-attach Derivative mechanic actually fire?~~ **CLOSED iter-4**: YES — Protective Put auto-attached to highest-power Trader (Rho 5/3). Also confirmed for TDC in iter-7 Quant vs Derivatives game. **Closed.**
- ~~Does Theta Decay Collar's attach-and-remove combo work mechanically end-to-end?~~ **CLOSED iter-4**: YES — Collar removed counters correctly at MC; net tick confirmed ~(Σlev−1)/turn. **Closed.**
- What's the optimal Leverage-Trader / counter-remover ratio?
- Is Vega Amplifier playable at Lev 3, or does it need a re-balance to Lev 2 + on-ETB counter-remove trigger?
- How does Derivatives fare against High Frequency (fast aggro)? Iter-4 result only tested vs Dark Arbitrage midrange.
