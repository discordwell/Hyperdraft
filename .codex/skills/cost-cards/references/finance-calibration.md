# Finance Calibration

Engine-specific cost values for the Finance TCG. Use alongside `cost-heuristics.md` (the engine-agnostic core) when pricing a Finance card.

## Engine snapshot

- **Resource**: Liquidity. Same ramp as Hearthstone mana (start 1, cap 10, +1 per turn).
- **Speed**: Limited instant-speed interaction. Orders are the only "instant"-shape cards; ~half are conditional or Dark Pool. Most plays resolve at sorcery speed in your own Trading Session.
- **Combat math**: Damage to Trader persists until heal/destroy (HS-style), unlike MTG where damage clears at end of turn. Toughness premium therefore includes "damage carries over" durability.
- **Win condition**: Reduce opponent's Capital Reserve (life total) from 30 to 0. Alt-win: Monopoly Position 20+ Portfolio Value counters.
- **Card types**: Trader (creature), Order (instant), Strategy (sorcery), Asset (passive enchantment), Structure (artifact-shape), Derivative (equipment/aura attach).

## Vanilla curve — Trader stats

Follows HS curve (`P+T = 2*cost + 1`, toughness-skewed) since Finance is no-instant-removal-mid-turn.

| Cost | Square baseline | Pushed (with text) | Examples in set |
|---|---|---|---|
| 1 | 1/2 or 2/1 (P+T=3) | 1/1 with strong text or Alpha Strike | Flash Crash Bot {1} 2/1 Alpha Strike, Statistical Arb Clerk {1} 1/2 Arb 1 |
| 2 | 2/3 or 3/2 (P+T=5) | 2/2 with text + minor mechanic | Front-Running Algo {2} 2/1 Alpha Strike + draw, Risk Manager {2} 1/4 Arb 1 |
| 3 | 3/4 or 4/3 (P+T=7) | 3/3 with mechanic + text | Pairs Trader {3} 2/3 Arb 2 + bonus, Delta Hedger {3} 2/4 Lev 2 + dmg-reduce |
| 4 | 4/5 (P+T=9) | 4/3 with multiple mechanics | Vega Amplifier {4} 4/3 Lev 3 + lord, Smart Beta Strategist {4} 3/4 Arb 1 + draw |
| 5 | 5/6 (P+T=11) | 5/4 with payoff | Hedge Fund PM {5} 4/4 Lev 2 + Derivatives sweeper |
| 6 | 6/7 (P+T=13) | 6/5 finisher | OTC Behemoth {6} 5/5 Lev 3 + Arb 2 + asymmetric prison |
| 7 | 7/8 (P+T=15) | 7/5 with pushed | Internalized Flow Monster {7} 6/5 Lev 4 + Arb 3 + Alpha Strike + ETB sweeper |

Audit observation: most existing Finance Traders sit *below* the HS curve at their cost tier, because the named mechanics carry the rest of the value. That's correct — see mechanic premiums below.

## Mechanic premiums

These are Finance-specific keywords. Each adds value to a Trader; the math says each is worth roughly the listed mana.

### LEVERAGE N — `+1 power per counter, +N drain per Market Close`

| N | Effective stat boost | Drain cost (per turn after it lands) | Net premium |
|---|---|---|---|
| 1 | +1/+0 | 1 Capital Reserve / turn | +0.5 mana |
| 2 | +2/+0 | 2 / turn | +1 mana |
| 3 | +3/+0 | 3 / turn | +1.5 mana |
| 4 | +4/+0 | 4 / turn | +2 mana |

The drain cost is real — opponent dies in 30 turns un-pressured, so 4 drain/turn is a quarter of your clock. Cards that mitigate the drain (Theta Decay, Synthetic Long) reduce the cost premium. Cards that pump *more* off Leverage counters (Vega Amplifier, Risk-Parity Quant) add +0.5–1 mana per scaling.

**Rule**: Leverage N costs (N × 0.5) mana on top of the vanilla baseline. If the card has a mitigation rider ("does not cost CR if X"), reduce premium by 0.5.

### ARBITRAGE N — `if you lead in Trader count, gain N Liquidity this turn`

| N | Liquidity gained / turn (when leading) | Net premium |
|---|---|---|
| 1 | +1 | +0.5 mana |
| 2 | +2 | +1 mana |
| 3 | +3 | +1.5 mana |

Discount × 0.6 because the condition (lead in Trader count) only fires when you're already ahead. So Arbitrage 1 ≈ +0.3 mana net, Arbitrage 2 ≈ +0.6 mana net, Arbitrage 3 ≈ +0.9 mana net.

**Rule**: Arbitrage N is worth (N × 0.3) mana in expectation. Cards that *also* trigger off Arbitrage (Factor Model Analyst's draw, Pairs Trader's bonus Liquidity) stack the discounted value — don't double-discount the sub-trigger.

### DARK POOL — `play Order face-down, triggers on opp's next Trading Session`

This is hard to price by addition. Compare to MTG flash + counter-protection: a Dark Pool Order is a *staged* counter-attack, hidden from opp, fires when they don't expect it. Premium varies by the Order's effect:

- Damage / removal Dark Pool: premium ≈ +0.5 mana over the same effect at sorcery speed (because timing trap).
- Pump / "self-buff" Dark Pool: premium ≈ +1 mana (the surprise-attack value is huge in HF).
- Liquidity / draw Dark Pool: premium ≈ +0.25 mana (the timing matters less).

**Rule**: Dark Pool premium is +0.5 mana for hostile Orders, +0.25 for value Orders.

Dark Pool Orders also incur a *deck-construction* tax: opp can play around if they know you have Dark Pool fans. So Dark Pool's effective value drops in long games. Don't push Dark Pool finisher costs based on the surprise factor alone.

### SHORT SELLING — `exile target Trader you control, return next turn with 2 +1/+1 counters`

This is the Finance "blink" mechanic with a tempo cost (skip a turn of the Trader being on board) and a permanent value gain (+1/+1 counters stick).

- Standalone Strategy ({2} Short Squeeze) is fairly priced: target removal-protection + permanent +1/+1 = 2 mana of value.
- Cards that are *priced* as Short Sell payoffs (Convexity Rider's "+3 counters instead of 2") add +0.5 mana to the Trader's cost.

**Rule**: Short Selling on a Strategy/Order is priced like 2-mana removal protection. As a Trader payoff, +0.5 mana premium per counter increment.

### ALPHA STRIKE — `+3/+0 when attacking alone`

| Body size | Solo damage potential | Premium |
|---|---|---|
| 1/1 | 4 dmg if unblocked | +0.5 mana |
| 2/X | 5 dmg | +0.5 mana (already Alpha Strike's home) |
| 3/X | 6 dmg | +1 mana |
| 4+ | 7+ dmg | +1.5 mana (finisher tier) |

Alpha Strike is gated by "attacking alone" — that's a hard condition for a wide aggro deck. Multiplier × 0.7 (ish): you're making a real choice between board-wide attack (multiple small hits) and Alpha Strike (one big hit).

Cards that *upgrade* Alpha Strike (Direct Market Access "+4/+0 instead of +3/+0", Nanosecond Assassin "+4/+0 specific to this") add +0.5 mana per increment.

**Rule**: Alpha Strike on power-2 body is +0.5 mana; on power-3+ body is +1 mana with × 0.7 condition discount. Net: ~+0.4–0.7 mana most cards.

## Card-type baselines (non-Trader)

### Order (instant-speed sorcery)

Same pricing as MTG instants in `cost-heuristics.md` Section 4. Specific Finance benchmarks:

- **Pre-Market Raid** {1}: 1 dmg to Trader, conditional on opp's Trading Session. Discount ×0.5 → 1 mana fair (the condition is roughly "every other turn").
- **Sub-Penny Intercept** {1}: -2/-0 to attacker. Defensive ping, comparable to Lightning Bolt at half power → fair at {1}.
- **Execution Glitch** {2}: counter Order. = Counterspell tier.
- **Cancel Order** {2}: tap target Trader. = Lullmage Mentor tier; arguably should be {1}, see audit.

### Strategy (sorcery)

- **Liquidity Provision** {2}: gain 3 Liquidity this turn. Mana acceleration. Comparable to Dark Ritual at {1}{B} with -2 life cost. Liquidity Provision at {2} for net +1 Liquidity is fair.
- **Information Advantage** {3}: draw 2, draw 3 if leading. Pure draw 2 = {3}, conditional bump to 3 = +0.5 mana → fair at {3}.
- **Flash Crash Event** {3}: destroy all Traders with toughness ≤ 2. Conditional sweeper → fair at {3} (matches Pyroclasm).
- **Factor Neutralization** {5}: destroy all Traders with power > toughness. Conditional sweeper → over-priced, should be {3}–{4}. **Audit flag**.

### Asset (enchantment)

- **HFT Feed Colocation** {2}: lord (+1/+0 to Alpha Strike). Generic 2-mana lord = {2} fair.
- **Tick Data Archive** {2}: draw a card per turn if you Alpha Striked. Recurring conditional draw, ×0.7 multiplier → 1.4 mana of value, plus the body cost (0 for an enchantment) = {1.4} → round up {2}. Fair.
- **Direct Market Access** {3}: replaces all Alpha Strike with +4/+0 (instead of +3/+0). 1 extra power per Alpha Strike trigger, fired ~3 times/game = 3 dmg net = ~{2} of value, but it's a per-trigger upgrade. Fair {3}.

### Structure (artifact)

Same as Asset pricing — they're functionally enchantments in Finance. Specifics:

- **Order Matching Engine** {3}: tap → +2/+0 to Trader. Activated pump = standalone activated ability worth ~{2} on a card. The card slot is 1 mana. Total {3} fair.

### Derivative (attachment)

Equipment-shape. Pricing follows MTG equipment with attach cost:

- **Theta Decay Collar** {2}: +1/+2 + Leverage decay. {2} for +1/+2 net = fair (+3 stats / 2 mana = same vanilla curve).
- **Synthetic Collar** {3}: +1/+1 *per Derivative attached*. Self-scaling, build-around. Discount ×0.6 → fair {3}.
- **Iron Condor** {3}: +0/+0 attach + "deal 1 to blocker." Combat-trick attach, 1 dmg-per-block recurring trigger. ~{2} of value rounded up → fair {3}.
- **Protective Put** {2}: prevent first destruction. Indestructible-once = {2} fair (cheap because one-shot).

## Format-tier Finance benchmarks

When sanity-checking a new Finance card, compare against these. Each is a card we've decided is fairly priced and acts as the "is this card stronger or weaker than X" gate.

| Card | Cost | Effect | Use as benchmark for |
|---|---|---|---|
| **Statistical Arb Clerk** | {1} | 1/2, Arbitrage 1 | 1-mana Quant Arbitrage cards |
| **Flash Crash Bot** | {1} | 2/1 Alpha Strike + 1 Liquidity ETB | 1-mana HF aggressive |
| **Underlying Asset Runner** | {2} | 2/2 Leverage 1 | 2-mana Derivatives baseline |
| **Front-Running Algo** | {2} | 2/1 Alpha Strike + draw on hit | 2-mana HF aggressive with payoff |
| **Pairs Trader** | {3} | 2/3 Arbitrage 2 + Liquidity bonus | 3-mana Quant payoff |
| **Delta Hedger** | {3} | 2/4 Leverage 2 + damage reduction | 3-mana Derivatives midrange |
| **Vega Amplifier** | {4} | 4/3 Leverage 3 + lord | 4-mana Derivatives finisher |
| **Smart Beta Strategist** | {4} | 3/4 Arbitrage 1 + conditional draw | 4-mana Quant value |
| **Hedge Fund PM** | {5} | 4/4 Leverage 2 + auto-attach all Derivatives | 5-mana Derivatives bomb |
| **OTC Behemoth** | {6} | 5/5 Lev 3 + Arb 2 + asymmetric prison on solo attack | 6-mana DA finisher |
| **Internalized Flow Monster** | {7} | 6/5 Lev 4 + Arb 3 + Alpha Strike + ETB Dark Pool sweep | 7-mana DA top-end |

For non-Traders:

| Card | Cost | Effect | Use as benchmark for |
|---|---|---|---|
| **Liquidity Provision** | {2} | +3 Liquidity this turn | 2-mana ramp |
| **Information Advantage** | {3} | Draw 2 / 3 if leading | 3-mana card draw |
| **Flash Crash Event** | {3} | Destroy all Tgh ≤ 2 | 3-mana sweeper |
| **Wrath of God** (does not exist in set yet) | {4} | Destroy all Traders | 4-mana unconditional sweeper — **audit flagged this gap** |
| **Information Ratio Enforcer** | {2} | Counter Order or Strategy unless paid {2} | 2-mana counter |

## Known calibration corrections (from polish punchlists)

- **HFPM 4/4 → 2/4** (May 2026): voltron centralization correction. Original cost {5} 4/4 with auto-attach made the card a finisher AND a tempo gain. Correction: keep cost {5}, lower stats. Audit lesson: when a card hits multiple broken-card patterns, premium stacks; don't trust additive math past 2 patterns.
- **Pairs Trader nerf**: details TBD from polish punchlist. Audit lesson: Arbitrage payoff scales with *quality* of board lead, not just quantity. Sub-trigger effects ("when Arbitrage triggers, X") add value beyond the Arbitrage premium.
- **Mass-attach cost cap-2**: Derivatives Desk no longer auto-attaches more than 2 per turn. Audit lesson: free attaches violate the equipment-attach pricing model. Treat each attach as if it cost the equip cost.
- **Position Audit instant-speed**: a Strategy moved from sorcery to instant. Audit lesson: instant-speed interaction is +0.5–1 mana more valuable than sorcery in Finance specifically (because sorcery answers can be played around in Finance's phase-locked turn structure).

## Open calibration questions

These are flagged for future audits or tournament data:

1. **Monopoly Position alt-win** ({7} 3/5): how much should a 20-counter alt-win cost? Currently priced as a 7-mana mid-stat with the alt-win as an "extra" — but if the build-around package is good, it should be cheaper (build-around discount). Insufficient data.
2. **Dark Pool tutor pricing**: Dark Inventory Position tutors a Dark Pool Order. Tutor for a specific subtype = {2} per cost-heuristics; with the body it's a {3} 2/3 + tutor → fair if the body is on-curve. Likely fair, but Dark Pool tutors might compound the archetype's combo potential.
3. **Toughness-skew pricing in HF**: HF cards trade with everything for 1, then die. Should HF cost premium be lower (because the bodies are disposable)? Maybe; need tournament data.
4. **Cross-archetype cards**: a card that helps two archetypes (e.g. "all Traders with Leverage OR Arbitrage gain X") — does it cost the sum of the two premiums, or the average? Currently treating as average; insufficient data.

## How to update this file

When a tournament or audit reveals a calibration gap:
1. Add the data point to the relevant section.
2. Update the rule (e.g. "Leverage 4 was over-credited; reducing to +1.75 mana from +2").
3. Re-run the audit on cards that depend on the corrected rule.
4. Reference the data point so future audits know where the rule came from.

The format-tier benchmarks should change rarely. The mechanic premiums should update with each tournament cycle.
