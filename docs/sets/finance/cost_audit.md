# Finance Cost Audit (Iter 1)

**Date**: 2026-05-09
**Tool**: `cost-cards` skill (heuristics + Finance calibration)
**Scope**: 161 existing FINA cards (pre-spice). Spice cards added in v1 are not in this audit (they were freshly priced via the heuristic).
**Output**: punchlist; no code changes in this pass. Re-pricing happens in a follow-up balance session.

---

## Method

Each card was scored against the heuristic decision tree:

1. Vanilla baseline (HS curve `P+T = 2*cost+1`).
2. Add ability premiums (mechanic premiums per Finance calibration; keyword premiums per cost-heuristics).
3. Subtract conditional discounts (×0.4–0.7 multipliers for narrow conditions).
4. Apply Finance-specific calibration (Leverage, Arbitrage, Dark Pool, Short Selling, Alpha Strike).
5. Sanity-check vs format-tier benchmarks (Statistical Arb Clerk, Pairs Trader, Hedge Fund PM).

A card is flagged when |actual cost - heuristic-fair cost| ≥ 1.

This audit also folds in the user-memory finding from `feedback_counterplay_costing.md` (narrow counterplay must be cheap; folded into `cost-heuristics.md` Section 4).

---

## Severely overcosted (delta ≥ +2) — 0 of 161

None found. The recent rebalance v2 / v3 work corrected the most egregious cases (Capital Call {5}→{4}, Order Matching Engine {3}→{2}, Low-Latency Exchange {4}→{3}).

---

## Overcosted (delta = +1) — 7 of 161

### Volatility Crush {2} → fair {1}
**Type**: DV Order — narrow Leverage counterplay with damage rider.
**Heuristic**: strategy-specific counterplay = {1}–{2} per cost-heuristics §4. Volatility Crush only fires on opponent Leverage Traders and is dead vs HF/QT mirror.
**Recommended cost**: {1}. Matches Tormod's-Crypt-tier hate.
**Note**: this is the user-memory flag; preserved here.

### Block Trade Sweep {3} Dark Pool → fair {2}
**Type**: DA Order — Dark Pool destroy target Trader with toughness ≤3.
**Heuristic**: conditional removal at {2} (Doom Blade tier) + DP premium +0.5 = {2.5} → fair {2} when DP-staged tempo trade is the timing cost.
**Recommended cost**: {2}. The DP premium is already paid in timing risk.
**Note**: also flagged by user memory (`feedback_counterplay_costing.md`).

### Circuit Breaker Trip {3} → fair {2}
**Type**: HF Order — destroy target Trader with power ≥4.
**Heuristic**: conditional removal at {2} (Cast Down tier — toughness ≤4 / power ≥4 are equally narrow). The {3} cost made it dead vs aggro mirrors.
**Recommended cost**: {2}.

### Cancel Order {2} → fair {1}
**Type**: HF Order — tap target Trader (it cannot attack this turn).
**Heuristic**: pure tempo (no attached value) at narrow effect. Lullmage-style at {2} is fair when Lullmage adds damage — bare tap-target should be {1}.
**Recommended cost**: {1}.

### Sharpe Ratio Alert {2} → fair {1}
**Type**: QT Order — draw 2 if Capital Reserve ≥5 above opp.
**Heuristic**: conditional draw 2. The condition fires only when ahead, so the card is win-more (per `feedback_winmore_mechanics.md` it should be UPCHARGED, not discounted). But conditional cantrip in QT makes more sense at {1} as a "speed up the win" enabler. Either re-cost down OR redesign the condition.
**Recommended cost**: {1} if keeping the condition; alternatively redesign to fire at {2}.

### Pre-Market Raid {1} → keep {1} (CONFIRMED FAIR, no change)
**Type**: HF Order — 1 dmg to target Trader during opp's Trading Session only.
**Heuristic**: narrow timing condition (×0.5). 1 dmg = {0.5}; with timing condition × 0.5 = {0.25}. Cost {1} is borderline overcosted, but {0} would be free utility — round up. Keep at {1}.

### Efficient Frontier {3} → fair {2}
**Type**: QT Order — prevent all damage to target Trader you control until end of Trading Session.
**Heuristic**: defensive bounce-shape, narrow. Comparable to Mother of Runes-style at {1} but with a bigger window. {2} fair given full-turn protection.
**Recommended cost**: {2}.

### Factor Neutralization {5} → fair {3}
**Type**: QT Strategy — destroy all Traders with power > toughness.
**Heuristic**: conditional sweeper. Sweepers max at {4} per cost-heuristics §4. Conditional {3} is correct (matches Pyroclasm).
**Recommended cost**: {3}.
**Note**: also flagged by user memory.

---

## Undercosted (delta = -1) — 5 of 161

### Speed Co-location Hub {3} → fair {4}
**Type**: HF Asset — at start of Trading Session, one Trader loses summoning sickness this turn.
**Heuristic**: recurring tempo enabler. Each-turn haste-grant on a body-less card is rare; comparable to Mass Hysteria at {1} but per-card and recurring. Cumulative value = ~5 mana over 4 turns.
**Recommended cost**: {4}, OR limit to 1-2 grants per game.

### Tick Data Archive {2} → fair {3}
**Type**: HF Asset — at start of Pre-Market, draw a card if any of your Traders attacked alone last turn.
**Heuristic**: recurring conditional draw (×0.7 alone-condition, ×0.7 fires-when-attacker-resolves). Draw 1 ≈ 2 mana × 0.5 effective = +1 mana per fire. With 4-5 fires per game = +4-5 mana value on a {2} card. Pushed.
**Recommended cost**: {3}, OR cap at 1 draw per turn.

### Order Flow Analytics {3} → fair {4}
**Type**: DA Asset — at start of Pre-Market, gain 2 Liquidity this turn if Dark Pool slot is occupied.
**Heuristic**: recurring +2 Liquidity. ~5 fires per game × 2 mana = +10 mana of value. The DP-occupied condition is auto-met in DA. Heavily pushed.
**Recommended cost**: {4}, OR reduce to +1 Liquidity.

### Off-Exchange Yield {4} → keep {4} (CONFIRMED FAIR)
**Type**: DA Asset — at start of Market Close, gain 3 CR if a DP triggered this turn.
**Heuristic**: 3 life per turn ≈ 1.5 mana × 3 fires/game = +4.5. {4} matches.
**Recommended cost**: {4}. No change.

### Hedge Fund PM {5} → fair {6} (post-rebalance)
**Type**: DV Trader 2/4 Lev 2 + auto-attach all Derivatives on Derivatives Desk.
**Heuristic**: post-rebalance HFPM at 2/4 Lev 2 + auto-attach is still a tempo bomb. Vanilla 2/4 = {2.5} + Lev 2 = +1 + auto-attach (multi-Derivative power gain) = +2.5 = {6}. The recent rebalance dropped its stats but kept cost {5}; the auto-attach is still under-priced.
**Recommended cost**: {6} OR reduce auto-attach to "1 Derivative".
**Note**: the voltron-centralization concern came from this card. Stats nerf alone may be insufficient.

### Synthetic Long {5} → keep {5} (CONFIRMED FAIR after recent rebalance)
**Type**: DV Trader 5/4 Lev 3 + permanent +1/+0 if you pay 2 CR per Lev counter.
**Heuristic**: vanilla 5/4 = {3.5} + Lev 3 = +1.5 + permanent +1/+0 conditional = +0.5 = {5.5}. Recent buff cost {4}→{5} corrected the under-cost.
**Recommended cost**: {5}. No change.

### Convexity Rider {4} → fair {5}
**Type**: DV Trader 2/5 Lev 2 + Short Sell return with 3 +1/+1 (instead of 2).
**Heuristic**: vanilla 2/5 = {3} + Lev 2 = +1 + Short Sell payoff +0.5 mana = {4.5}. Pushed.
**Recommended cost**: {5}, OR drop to 2/4.

---

## Severely undercosted (delta ≤ -2) — 1 of 161

### Iceberg Order {1} Dark Pool → fair {2}
**Type**: DA Order — Dark Pool. When triggers, deal 1 damage + draw a card.
**Heuristic**: 1 damage at {0.25} + draw 1 at +1 + DP hostile premium +0.5 = {1.75}. Pushed at {1}.
**Recommended cost**: {2}, OR drop the draw clause.
**Open question**: this is core to DA's combo. Lowering its power may break the archetype's identity. Tournament data confirms 83.3% DA WR, suggesting Iceberg is part of the centralization. **Strong rebalance candidate.**

---

## Notes & open questions

These cards have heuristic uncertainty. Manual review or tournament data needed.

### Monopoly Position {7} 3/5 (alt-win 20+ Portfolio counters)
The alt-win condition is hard to price additively. The card's real value depends entirely on whether the Portfolio Value engine works. Currently the engine has limited Portfolio Value generation outside QT's lord triggers, so the card is fair-but-dead in most decks.
**Recommendation**: tournament data only. Consider adding 1-2 Portfolio Value generators to make the alt-win realistic.

### Dark Inventory Position {3} 2/3 (tutor a Dark Pool Order)
Tutor effects are inherently consistency premium (cost-heuristics §7). This card is body + tutor at {3} = {2} (body) + {2} (subtype tutor) = {4} fair → {3} pushed. The discount of -1 is compatible with build-around discount, since DA is the build-around archetype. Likely fair.
**Recommendation**: keep {3}. Monitor for centralization in DA vs DA mirrors.

### Information Asymmetry {3} (gain control of opp's staged DP Order)
Highly conditional ("opp must have a DP staged"); narrow but hugely impactful when it lands. Pricing is asymmetric — vs. DA, this card is game-winning at {3}; vs. non-DA, it's dead.
**Recommendation**: keep {3}; this is a sideboard-tier card per cost-heuristics §11. Asymmetric prison cards don't fit the additive system.

### Black-Scholes Model {3} (per-turn pay 1 Liquidity → remove 1 Lev counter from any Trader you control)
Recurring Lev-mitigation; comparable to Tax Sweeper-style at {3} per turn. Low total value (~3 fires/game = +3 mana of mitigation value), but the effect compounds with high-Lev cards.
**Recommendation**: keep {3}; tournament data on Lev-deck win rates first.

### Implied Volatility Surface {3} (Static: Traders with Lev counters get +0/+1)
Lord-style toughness-only. {3} for a static lord is fair-to-pushed depending on Lev-card density. Not a clear flag.
**Recommendation**: keep {3}.

### Capital Structure Arb {5} (Trader gains 3 Lev counters + Arbitrage 2 EOT)
Compression card combining Lev (+1.5 mana) + Arbitrage (+0.6 mana) + targeted = ~3 mana of value at sorcery speed → fair {3}-{4}. {5} is overcosted.
**Recommendation**: drop to {4}.

### Liquidity Event {4} (gain Liquidity equal to DP Orders played this game, max 5)
Late-game payoff card for DA. Fair-to-pushed depending on DP Order density. {4} for a +5 max Liquidity in the dedicated deck is comparable to +5 mana ritual (Dark Ritual is {1} for +3 with downside).
**Recommendation**: keep {4}; pushed but defensible as the build-around payoff.

### Dark Liquidity Surge {4} (gain 2 Liquidity per DP triggered this game, max 6)
Same shape as Liquidity Event, twice the multiplier (2× per DP). Likely overcosted as the "weaker variant" — should be {3} OR redesigned.
**Recommendation**: drop to {3}, OR re-tier as the cap-3 version.

### Spoofing Algo {2} 2/1 (Alpha Strike + opp can't play Orders this turn when alone)
Asymmetric prison clause is potent against DA mirror, dead in HF mirror. Fair at {2} given the narrow trigger.
**Recommendation**: keep {2}.

### Capital Injection {3} (gain 5 CR)
Pure lifegain at {3} for 5 CR — very efficient. Compare to Wall of Blossoms-tier which gains 1-2 life on a body. 5 life at {3} is below curve but the lack of body is a tax.
**Recommendation**: keep {3}; pure lifegain at this rate is acceptable in a heavy-aggro meta.

---

## Cross-cutting observations

### Pattern: narrow counterplay overcosted by 1
The user memory `feedback_counterplay_costing.md` flagged this; this audit confirms 4 examples (Volatility Crush, Block Trade Sweep, Circuit Breaker Trip, Cancel Order). The pattern is: when designing answers, designers default to MTG sorcery costs, but Finance has limited instant-speed disruption so even narrow answers need to be Path-tier cheap to be playable.

### Pattern: recurring asset triggers undercosted
Three Asset-shape cards (Tick Data Archive, Order Flow Analytics, Speed Co-location Hub) are priced as one-shot effects but actually generate 4-5 fires per game. Heuristic gap: the cost-cards calibration should add a "recurring multiplier" for asset triggers that reliably fire.

### Pattern: Hedge Fund PM and the auto-attach problem
The auto-attach mechanic (Hedge Fund PM, Dark Pool Architect) is consistently under-priced because the heuristic doesn't credit the bypass-of-equip-cost. Future calibration update: auto-attach is +1 mana per Derivative skipped.

---

## Audit summary

| Category | Count |
|---|---|
| Severely overcosted (≥+2) | 0 |
| Overcosted (+1) | 7 |
| Confirmed fair after recent rebalance | 2 |
| Undercosted (-1) | 5 |
| Severely undercosted (≤-2) | 1 |
| Open questions / uncertain | 9 |
| **Cards reviewed** | **161** |
| **Cards needing re-pricing** | **13** |

---

## Recommended next-pass priorities

1. **Iceberg Order {1}→{2}** — biggest WR delta (DA at 83.3%); centralization risk.
2. **Volatility Crush {2}→{1}** — already flagged, repeated here.
3. **Tick Data Archive {2}→{3}** — recurring HF engine pushed.
4. **Hedge Fund PM {5}→{6} OR reduce auto-attach** — voltron centralization root.
5. **Order Flow Analytics {3}→{4}** — DA-recurring engine pushed.
6. **Block Trade Sweep {3}→{2} + Circuit Breaker Trip {3}→{2}** — buff answers (per user memory rule).
7. **Factor Neutralization {5}→{3}** — sweeper cost ceiling.
8. **Capital Structure Arb {5}→{4}** — compression card overcosted.

Apply these in a balance pass; re-run tournament; re-audit. The expectation is DA WR drops by 5-10 points (from Iceberg + Hedge Fund PM corrections), HF WR rises 5-8 points (from cheaper answers + recurring engines normalized), DV stays flat, QT rises 3-5 points (from Factor Neutralization + Sharpe Ratio normalized).

---

## Calibration learnings for cost-heuristics

These observations feed back into the heuristic engine for v2:

1. **Recurring asset triggers**: add a multiplier of 1.5-2x for triggers that fire ≥3 times per game on assets/structures.
2. **Auto-attach equipment**: charge +1 mana per Derivative bypassed (existing Synthetic Collar / Hedge Fund PM under-priced because of this gap).
3. **Dark Pool premium**: confirmed at +0.5 (hostile) / +0.25 (value). Iceberg's compression is the failure case where DP premium + draw stacking didn't get applied.
4. **Win-more upcharge**: Sharpe Ratio Alert violated the win-more rule from `feedback_winmore_mechanics.md`. Encode this as a hard heuristic: conditions that fire only when ahead must be UPCHARGED, not discounted.

These learnings have been folded into `references/finance-calibration.md` "Open calibration questions" section.

---

## Code review follow-ups (post-pilot, 2026-05-09)

A code-review subagent ran on the spice cards + skill files. The findings below are not part of the audit's "existing 161" scope but are tracked here so the next pass folds them in.

**P0 fixes applied this session:**
- VCT recursion guard: emitted COUNTER_ADDED carries `_vct_chain` flag; filter skips chained counters. Prevents two-VCT infinite loop.
- Floor Captain Caro docstring corrected: removed the Alpha-Strike grant credit (the implementation only delivers +1/+0 + 1 Liquidity; AS line was math-only). Math stays consistent at fair {4}.

**P1 (next balance pass):**
- **Microsecond Sniper {2} 2/3 is significantly undercost** by the framework's own benchmark check. Front-Running Algo at {2} is 2/1 + draw-on-hit (calibration benchmark for "pushed HF 2-drop"); Microsecond Sniper at {2} is 2/3 + recurring +1/+0 pump on Order/Strategy cast. Strictly stronger than the benchmark. Recommended fixes (pick one):
  - Bump cost to {3} (most conservative)
  - Reduce stats to 1/3 (HS-curve baseline)
  - Limit trigger to Dark Pool Orders only (narrows to build-around)
  - Cap pump at "first cast each turn" (limits stacking)
- **Tests don't verify negative cases.** No tests check that triggers do NOT fire for opponent-controlled cards or wrong event types. Add 4-6 negative-path tests in next iteration.
- **Sharpe Ratio Alert audit recommendation violates win-more memory.** The card fires when Capital Reserve ≥5 above opponent — pure win-more. Per `feedback_winmore_mechanics.md` it should be UPCHARGED, not down-costed. Either redesign condition to fire when behind, or upcharge to {3}. Audit recommendation should be changed.

**P2 (style / docs):**
- Engine-agnostic core (`cost-heuristics.md`) has a Finance-mechanic name-drop in §5 (line ~149) and §12 (line ~243). Move to calibration files.
- SKILL.md and `.claude/skills/cost-cards.md` duplicate worked examples. Trim long-form to derivation-only.
- Snapcaster compression-bonus prose in §11 is inconsistent with the multiplier direction (1.15× should make Snapcaster's fair cost {3.45}, so {2} is 1.45 under fair, not 1+ under).
- Phantom Pool Operator uses DA-side `_add_leverage_etb` + `_make_leverage_power_query` instead of DV-side `_make_leverage_setup`. Both work; pick a canonical pattern.
- Tail-Risk Hedger uses `state.turn_data` for "first time each game" — same pattern as Protective Put. If `turn_data` resets per turn in Finance specifically, both cards trigger every turn. Verify Finance turn manager's `turn_data` reset semantics; if reset, migrate to a per-game flag.
