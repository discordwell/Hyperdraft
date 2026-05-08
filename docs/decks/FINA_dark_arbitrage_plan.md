# FINA_dark_arbitrage — Plan

## Status: ENGINE-BROKEN (iter-3) — Combo identity dead, deck wins on midrange goodstuff

In iter-3 (vs Quant), Pilot B deployed a full curve of Trader bodies and won at T20 via a goodstuff midrange Trader chain. **However, every Dark Pool Order resolved straight to graveyard without staging** — engine bug 15 (`_play_card_action` lacks the `_dark_pool` branch). All 6 DP Orders are completely non-functional, Hidden Accumulator's +1/+1 buff never fires, and the cantrip combo plan is structurally impossible. The deck won despite its theme, not because of it. **Until bug 15 is fixed, this archetype is decorative.**

## What functions vs what is dead (iter-3, both pilots agree)

| Card | Status | Why |
|------|--------|-----|
| Hidden Accumulator | **DEAD** | Filter listens for DP play but no DP ever stages. Vanilla 2/2. |
| Hidden Aggression | **DEAD** | DP staging unwired (bug 15). Order goes to GY. setup_interceptors never runs (Orders never enter battlefield). |
| Block Trade Sweep | **DEAD** | Same as HA. Never staged → no destroy effect. |
| Off-Exchange Position | **DEAD** | Same as HA. Engine bug 13 (iter-2) confirmed: silent no-op cast. |
| Iceberg Order | **DEAD** | DP rider non-functional; cantrip portion unconfirmed (likely bug-7 affected). |
| Crossed Market | **DEAD** | DP staging unwired. |
| Lit-Market Decoy | **HALF-DEAD** | Cast event fires, but DRAW silently doesn't draw (iter-1 bug 7). Free-DP rider sets a flag DP staging never reads. |
| Dark Inventory Position | **HALF-DEAD** | ETB SEARCH_LIBRARY → PendingChoice. Filter `dark_pool_order` unrecognised → tutor offers entire library. Two-pilot harness has no `choose` command, so PendingChoice stalls (bug 20). Body is 2/3 ETB-tutor — strong if tutor worked. |
| Off-Exchange Operative | **PARTIAL** | Body OK (3/3 cost 3). Arb 1 may fire. Lev 1 power query uses `InterceptorPriority.TRANSFORM` instead of `QUERY` (bug 19) → power buff doesn't apply (3 power not 4). Self-tax via leverage tick still applies. |
| Off-Exchange Finisher | **FUNCTIONAL (bug-helped)** | 5c, 3/4 with `_make_alpha_strike_plus4` helper. Alpha+4 fires solo OR multi-attack (bug 18 — first-declared keeps the +4 buff regardless of attacker count). 7 power Alpha-strike is the deck's TRUE finisher. |
| Institutional Block Trader | **FUNCTIONAL** | 5c, 3/4 Lev 2 Arb 1 +2 mana ETB. ETB ramp gives a chained play same turn — major tempo card, untested in iter-1/iter-2, validated iter-3. |
| Dark Flow Engine | **UNTESTED** | DP cost reduction; useless until staging works. |

## Composition summary (intended)

Combo/tempo hybrid built around the Dark Pool mechanic and instant-speed disruption. Trader chassis: Off-Exchange Operative (3c, 3/3 Lev 1 Arb 1), Dark Inventory Position (2c, 2/3 ETB-tutors a DP Order), Block Trade Sweep (combo finisher), Hidden Accumulator (combo enabler). Orders: Off-Exchange Position (DP -3/-0 to highest-power), Lit-Market Decoy (cantrip + free DP grant rider), Iceberg Order (cantrip), Hidden Aggression (+2/+0 — text says +4/+0, code says +2/+0, see strategy doc bug 12). Structure/Asset: Dark Flow Engine (DFE, cost reduction for DP Orders).

## Tentative hypothesis: deck identity

**Plan A (theorized): Dark Pool combo finisher.** Stage DP Orders via Lit-Market Decoy / Iceberg Order cantrip chain, trigger Hidden Accumulator twice for a T5-T6 4/4 swing. Block Trade Sweep closes mid-game. Win condition: combo damage burst around T8-T10.

**Plan B (theorized): Disruption tempo.** Stage Off-Exchange Position into Dark Pool to nerf opp's finisher (the -3/-0 lands during opp's trading_session window — useful for blocking math). Survive on chump-blocks from Off-Exchange Operative (Arb 1 healing).

Neither plan was tested in iter-2.

## What was observed in iter-2

- **Off-Exchange Position fired correctly when staged into Dark Pool.** Pilot B confirmed: -3/-0 landed on Vega Amplifier (highest-power) during P1's trading_session on T9. The DP system wiring works for at least one Order.
- **Off-Exchange Position silent no-op when cast WITHOUT a DP slot.** Pilot A cast it at full cost (no DP staged); -3/-0 did not apply. Either silent prerequisite or pipeline drop. Engine bug 13.
- **Lit-Market Decoy** fired DRAW + free-DP-grant on T4 (landed in GY post-resolve), but Pilot B's hand-size accounting could not confirm whether the DRAW actually drew (same bug class as iter-1 #7).
- **Off-Exchange Operative** used as a chump-block on T7 — Arb 1 healing + Leverage 1 power buff made the 3v3 trade with UAR neutral on body but positive on tempo. **NOTE: OEO has Leverage 1 — Dark Arbitrage pilots also self-damage.** Either reduce OEO's Leverage to 0 or warn pilots.

## Critical structural problems

1. **Dark Arbitrage is structurally dead on T1-T2.** No 1-cost Trader, no 1-cost Asset, no useful 1-cost Order without a DP follow-up. The deck wants to cantrip-chain but lacks the on-curve fuel.
2. **Dark Inventory Position (2c, 2/3, ETB-tutors a DP Order) is the deck's missing T2.** Pilot B drew zero copies in 9 turns. Either weight its draw probability higher (4-of) or top-of-library bias the opening hand.
3. **Combo finishers never come together.** Lit-Market Decoy + Iceberg Order + Hidden Aggression should be a T2-T4 cantrip chain that triggers Hidden Accumulator twice for a T5 4/4 swing. None of those cards appeared together. Mulligan or draw-engine support is needed to make this consistent.

## Tentative win condition

**Plan A (untested, ENGINE-BROKEN): Dark Pool cantrip combo.** T1-T4: cantrip chain (Lit-Market Decoy → Iceberg Order → Dark Inventory Position) accumulates DP Orders + draws. T5-T6: Hidden Accumulator + 2 staged DP Orders triggers a 4/4 swing. T7-T9: Block Trade Sweep closes. **DEAD until bug 15 fixed — no DP Order ever stages.**

**Plan B (iter-3 validated, current): Wide-board midrange goodstuff Trader chain.** Deploy 2-3 cost Trader bodies aggressively (DIP 2/3 → HACC 2/2 → OEO 3/3 → SPB 2/4 → IBT 3/4+ramp → OEF 3/4+Alpha+4). Win condition: trader-count race + multi-attack with OEF declared FIRST (bug 18 lets first-declared keep the +4 alpha buff). **Killing opp's PCD/lord is mandatory** — Quant's whole curve depends on it. This is the deck's REAL identity in the current engine.

## Mulligan policy (tentative)

- **Auto-keep**: hand with Dark Inventory Position (2c, ETB-tutor) + Lit-Market Decoy. Sets up the cantrip chain.
- **Auto-keep (good)**: hand with Hidden Accumulator + 2 cantrips. Combo enabler.
- **Auto-mull**: 0 cards costing ≤2. T1-T2 are dead with this deck and recovery is hard.

## Play priorities (iter-3 updated)

1. **Stop staging DP Orders.** Bug 15 sends them to GY for zero effect. Burning 2-3 mana per DP order is a complete tempo loss. Treat ALL DP-tagged Orders as dead until staging is wired. Only cast Lit-Market Decoy if its cantrip portion proves to fire (currently uncertain due to bug 7).
2. **Curve out on Trader bodies.** DIP T3 (2/3 + tutor — manual injection required in two-pilot harness due to bug 20), OEO T3 (3/3 if bug 19 unfixed; 4/3 if fixed), SPB T3 (2/4 — vanilla post-bug-15), IBT T5 (3/4 + ramp ETB), OEF T5 (3/4 + Alpha+4 finisher).
3. **Kill opp's PCD/lord/+stat-anchor on the first opportunity.** Iter-3: blocking PCD with SPB at T11 was the pivot. Quant has no PCD2, so once it dies the entire wall chassis drops 1 toughness.
4. **Multi-attack with OEF declared FIRST.** Alpha-asymmetry bug 18 lets the first-declared alpha-attacker keep its +4 power even with multiple attackers. 7-power Alpha trample is the deck's lethal close.
5. **Off-Exchange Operative chump-block trades are fine.** Arb 1 healing converts a 3v3 into "blocker dies, attacker dies, +1 capital reclaim." (May be partially broken if bug 19 stops the +1 power; verify in iter-4.)
6. **DON'T cast Off-Exchange Position at all** (engine bug 13: silent no-op without DP slot; engine bug 15: never stages anyway).
7. **Defensive posture vs Derivatives.** Iter-2 lesson: doing nothing while opp stacks Leverage is a winning play. The deck self-immolates if it deploys 4+ Leverage Traders without Black-Scholes.

## Anticipated weaknesses

- **Slow / weak T1-T2.** Structural curve gap — no 1-cost play that pulls weight.
- **Combo dependency.** If Hidden Accumulator / Aggression / Block Trade Sweep aren't drawn, the deck has no finisher.
- **OEO Leverage 1 self-tax.** Minor but real — needs management or a re-balance.
- **No spot removal.** Off-Exchange Position is the only PT-modifier; it's not destroy.

## Iteration log

- **2026-05-08 (iter-3)**: vs FINA_quant (Pilot A). **Won** in 20 turns; final P1=−1, P2=10. **Major findings**: Dark Pool combo identity is COMPLETELY DEAD due to engine bug 15 (`_play_card_action` lacks `_dark_pool` branch). All 6 DP Orders resolved to GY without staging; Hidden Accumulator's +1/+1 buff never fired; Stealth Position Builder's draw never fired. The deck won via wide-board midrange Trader chain — 16+ cheap bodies (DIP, HACC, OEO, IBT, OEF) overwhelmed Quant's collapsing wall. Pivotal moment: **T11 PCD-killing block** (DIP×SPB stopped Quant's lord). Once PCD died (Quant has no PCD2), every 2/2+ Trader became a lethal threat. OEF (5c, 3/4 Alpha+4) was the actual finisher — 7-power solo or multi-attack-declared-first (bug 18). 6 NEW engine bugs documented (15-20). **Verdict**: deck is functional as a goodstuff midrange archetype despite its theme being engine-broken.
- **2026-05-08 (iter-2)**: vs FINA_derivatives (Pilot A). **Won** in 9 turns; final P1=-4, P2=15. Win was 100% passive Leverage Tick on P1's own board. P2 deployed 1 Trader (Off-Exchange Operative) and staged 1 Order (Off-Exchange Position into Dark Pool). Combo finishers (Hidden Accumulator, Hidden Aggression, Block Trade Sweep) never drawn. **Deck identity unverified — tag for iter-3.** Two-pilot harness state file-race observed during this game (engine bug 11) — Pilot B's perceived Liquidity desynced from actual state mid-decision.

## Open questions for iter-4 (after engine fixes)

- Does the cantrip combo (Lit-Market Decoy → Iceberg Order → Hidden Accumulator) actually assemble in a game **once bug 15 is fixed**?
- Is Hidden Accumulator too strong post-fix? Chaining 3 DPs in a turn would be +3/+3 = 5/5 for 2 mana.
- Is Off-Exchange Operative balanced once bug 19 (Lev power query) is fixed AND bug 14 (counter double-add) is resolved?
- Does the deck still win once Quant gets the spot-removal Order requested across 3 iterations?
