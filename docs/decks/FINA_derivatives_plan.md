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

**Plan A (primary): Counter-managed midrange.** Hold 1-2 Leverage Traders MAX on the field. Use Theta Decay Trader's free pre-MC counter-removal to keep tax at ≤1/turn. Stack Derivatives (Theta Decay Collar, Gamma Amp, Synthetic Collar) on a single sticky 4-toughness host (Delta Hedger 4 toughness with damage reduction is ideal). Win via single-attacker burst from a 7-9 power buffed Trader around T12-T15.

**Plan B (race insurance): Vega Amplifier lord swing.** Vega Amp's +1/+0 to other Leverage Traders fires correctly per iter-2. If you can drop Vega Amp + 2 Leverage Traders + Black-Scholes Model in the same window, the buffed swarm closes T9-T11. Risky — Lev 3 + Lev 2 + Lev 1 = 6 self-tax/turn unless Black-Scholes eats one each turn.

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

## Iteration log

- **2026-05-08 (iter-2)**: vs FINA_dark_arbitrage (Pilot B). **Lost** in 9 turns; final P1=-4, P2=15. Pilot A self-graded the loss as primarily caused by stacking 5 Leverage Traders with no counter-removal cards drawn. Vega Amplifier lord effect verified working (+1/+0 to other Leverage Traders displayed). Multi-attack mechanically works. Off-Exchange Position from P2 silently no-op'd in one cast (DP-staging requirement?). 5 new engine bugs flagged (see strategy doc punch list). **Deck identity revised: leverage-counter-management, not auras-on-trader.**

## Open questions for iter-3

- Does the auto-attach Derivative mechanic actually fire?
- What's the optimal Leverage-Trader / counter-remover ratio?
- Does Theta Decay Collar's attach-and-remove combo work mechanically end-to-end?
- Is Vega Amplifier playable at Lev 3, or does it need a re-balance to Lev 2 + on-ETB counter-remove trigger?
