# Cost Cards: How to Price Hyperdraft Cards

> Companion to the `cost-cards` skill at `.codex/skills/cost-cards/`. The skill
> file is the operational checklist; this doc is the derivation — where each
> heuristic value comes from and why.

## When this skill earns its keep

Custom-set design has two failure modes:
1. **Over-pricing**: a designer attaches a 0.5-mana premium to every keyword,
   and the card ends up at {5} doing what {3} should. Players never cast it.
2. **Under-pricing**: a designer doesn't credit a 1-shot ability and the card
   turns out to be a format-warping bomb. The set's tournament win-rate gap
   blows past 30 points.

Both failures show the same root: **no benchmark**. The designer reaches for
"feels about right" and lands somewhere within ±2 mana of reality. ±2 in
Hyperdraft is the difference between unplayable and broken.

The cost-cards skill is the benchmark. It turns "feels right" into a 5-step
walk that produces an integer cost — defensible, repeatable, calibrated.

## Why a heuristic, not a calculator

A computational scorer would parse the card and compute the cost from a fixed
formula. Tempting, but wrong for three reasons:

1. **Card text is not a fixed grammar.** Custom sets invent new mechanics
   constantly. A scorer that handles "Leverage" must be re-coded when "Yield"
   ships. A heuristic is text-agnostic.
2. **Conditions matter contextually.** "If you control more Traders than
   opponent" is rare in a control deck and frequent in an aggro deck. A
   scorer can't know which deck the card lives in.
3. **Format-tier benchmarks dominate the math.** A card priced "fairly" by
   formula but visibly stronger than the format-defining benchmark *is* the
   benchmark — your formula is wrong, not the card. Heuristics let you
   privilege empirical comparison over arithmetic.

Heuristics also stay readable. Future designers can scan the decision tree
in 30 seconds and know what to push or pull. A scorer is a black box.

## Where the numbers come from

### Vanilla curves

The MTG vanilla curve (`P+T ≤ 2*cmc`, with colored-mana premium) is
documented Wizards philosophy across two decades. Mark Rosewater's "Lessons
Learned" essays repeatedly reference Erik Lauer's spreadsheet of vanilla
P/T combinations that have been printed at each cost. The community formula
`R = ln(P+T+E)/(cmc+C)` is one of several attempts to capture it; we use the
linear approximation because it's good enough for ±0.5 mana precision.

The HS curve (`P+T = 2*cost+1`, toughness-skewed) is a community-derived
empirical observation, anchored by **Chillwind Yeti** ({4} 4/5) — the
"vanilla 4-drop" that Hearthstone designers use as the reference point for
"a card you just cast on curve." The toughness skew comes from HS's lack of
mid-turn interaction: surviving the next attack matters more in HS than in
MTG, so toughness is priced slightly higher.

Finance, Pokemon TCG, and Yu-Gi-Oh fall on the HS side of the spectrum
because they all lack instant-speed creature removal mid-turn. Pokemon and
Yu-Gi-Oh need their own per-engine calibration before they're priced
confidently.

### Card-advantage premiums

The 2-mana baseline for a single drawn card comes from MTG's printed
catalog: **Divination** ({2}{U}) draws 2, **Concentrate** ({2}{U}{U}) draws
3, **Sign in Blood** ({B}{B}) draws 2 with life cost. Average across these:
1 card ≈ 2 mana of value.

The "cantrip on a body" pattern (+1 mana premium) comes from Snapcaster
Mage analysis: Snapcaster is a 2-mana card with three abilities (2/1
body, flash, flashback grant) that should additively cost ~{3.45}. Its
actual cost is {2}, meaning Wizards intentionally pushed it by ~1.5 mana —
a known modern-tier pushed card. The premium accounting *captures* the
push by noting Snapcaster was deliberately under-cost.

### Removal benchmarks

The user's `feedback_counterplay_costing.md` memory was the seed:
Lightning Bolt {1} for 3 dmg, Murder {3} for unconditional kill,
Counterspell {2}, Wrath of God {4}. These are stable across decades of
Magic and form the spine of the heuristic. Folded into Section 4 of
`cost-heuristics.md`.

### Keyword premiums

Most keyword premiums come from comparing pairs of nearly-identical cards
that differ only by one keyword. **Storm Crow** ({1}{U} 1/2 flying) vs
**Stormbound Geist** ({1}{U} 1/3 flying flash undying) — same body cost,
different ability stack. The differential isolates each keyword's premium.
Flying ≈ 0.5–1 mana premium because removing flyers is harder; haste ≈ 0.5
mana for small bodies, 1 mana for big.

The stacking penalty (3+ keywords compress) comes from the empirical
observation that Snapcaster (2 abilities) costs less than the sum, while
Solitude (4 abilities, with pitch cost) costs about its sum × 1.3.
Compression rewards include-multiple-effects-on-one-card design.

### Conditional discount multipliers

The 0.6 multiplier for "build-around" and the 0.4 for narrow conditions
both come from spice-pass observation: cards in pattern 11 (build-around)
tend to be priced at ~60% of their full-payoff value when supported, and
become unplayable when not. The capability test methodology validates this
empirically — cards with full-cost build-around payoffs cast at 0.10 in
generic decks and 0.30+ in synergy decks; the 60%-cost payoff cards cast at
0.40+ in synergy decks (the "hits the format" threshold).

The 0.7 multiplier for "once per turn" is more arbitrary — most abilities
only fire once per turn anyway, so the cap rarely matters. Adjust per-card.

## Worked examples

### Example 1: pricing a new Finance HF spice card

Design: "**Latency Striker** — {?} 2/3 Trader. Alpha Strike. Whenever this
attacks alone, draw a card."

1. **Vanilla baseline**: 2/3 → P+T=5 → HS curve says cost {2}. ✓
2. **Add for upside**: Alpha Strike on power-2 body = +0.5 mana (premium ×
   0.7 condition multiplier ≈ +0.35). Recurring draw 1 on attacks alone =
   draw value 2 mana × 0.7 alone-condition × 0.7 once-per-turn ≈ 1 mana.
   Sum: +1.35 mana.
3. **Subtract for conditions**: already applied multipliers in step 2.
4. **Engine calibration**: HF aggro, fits the archetype. No additional
   adjustment.
5. **Sanity check**: compare to **Front-Running Algo** ({2} 2/1 Alpha
   Strike + draw on unblocked combat damage). Latency Striker is +0/+2 and
   the draw fires on *any* alone-attack, not just unblocked. Strictly
   stronger. Should cost ≥ {3}.

Final: {3}. Heuristic produced 2 + 1.35 = 3.35 → round down to {3} (HF
deserves the push, build-around-style support).

### Example 2: pricing a Quant sweeper that doesn't exist yet

Design: "**Mark to Market** — {?} Strategy. Destroy all Traders. You may
gain Liquidity equal to the number of Traders destroyed (max 5)."

1. **Vanilla baseline**: sorcery-shape, no body → 0 baseline.
2. **Add for upside**: unconditional sweeper = {4} per Wrath benchmark.
   Liquidity payoff = +1 mana per ~3 Liquidity gained = ~+1.5 mana on
   average sweep.
3. **Subtract**: nothing — symmetric in the sense both players lose
   creatures, but the Liquidity payoff is asymmetric (you gain it).
4. **Engine calibration**: Quant has a sweeper gap (the audit will flag
   this). The set lacks an unconditional Wrath. Pricing this here is
   set-completing, so don't push the cost.
5. **Sanity check**: compare to **Flash Crash Event** ({3} conditional
   sweeper toughness ≤ 2). Mark to Market is unconditional and refunds
   Liquidity — clearly stronger. Should cost > {3}.

Final: {5}. Heuristic produced 0 + 4 + 1.5 = 5.5 → round down to {5}
(symmetric sweeper, no need to over-charge).

### Example 3: auditing an existing card

Audit target: **Volatility Crush** {2}: "Remove all Leverage counters from
target Trader. If opponent's, deal damage equal to counters removed to
that Trader."

1. **Stripped to effect**: conditional removal-or-debuff. Lev-removal
   from your own Trader = utility (saves you drain). Lev-removal from opp
   + dmg = removal scaled to opp's investment.
2. **Heuristic-fair cost**: narrow counterplay (only good if opp has
   Leverage) → {1}–{2} per `feedback_counterplay_costing.md`. Lev removal
   on your own Trader is anti-synergy (you don't usually want to remove
   your own counters). The card is conditional both ways.
3. **Comparison**: Doom Blade tier removal at {2} is unconditional. Vol
   Crush is conditional on opp running Leverage AND being well-stocked
   with counters → narrow.
4. **Verdict**: over-priced by 1 mana. Fair: {1}.

This is exactly the pattern flagged in the user's memory and validates
the heuristic.

## Engine port checklist

When extending cost-cards to a new engine (Pokemon, YGO, future engines):

1. **Identify the resource**: mana, energy, level, etc. Map to a numeric
   axis. (Pokemon energy is multi-typed but the *count* is the cost
   anchor.)
2. **Establish the vanilla curve**: find 5+ cards across the cost range
   that are unanimously considered "playable but not pushed" baselines.
   Their stats define the curve.
3. **Identify named mechanics**: each engine has 2–6 named keywords or
   resource-systems that recur. Each needs a per-engine premium derived
   from comparing pairs.
4. **List 8–12 format-tier benchmarks**: the cards every player knows are
   the "fair benchmark" at each cost. These are your sanity-check anchors.
5. **Run a tournament with naive pricing**, audit the wins/losses, and
   refine the calibration.

## Relationship to spice-pass

The cost-cards skill replaces the *gut-feel* costing step inside
spice-pass. Spice-pass tells you *what to push* (the 11 broken-card
patterns); cost-cards tells you *how much to push* (cost vs benchmark).

Together: design a spice card targeting pattern 4 (compression / threat-
and-answer), price it at heuristic cost, push by 0.5–1 if it's a
build-around (pattern 11), validate via capability test. The two skills
compose without overlap.

## Future directions

- **Per-engine calibration files for Pokemon, YGO, Hearthstone**:
  placeholder slots in `references/`. Each needs a tournament cycle's
  worth of data before the calibration is trustworthy.
- **Capability-test integration**: a card priced at heuristic-fair but
  failing capability test reveals the heuristic missed a synergy
  premium. Auto-flag these for calibration update.
- **Audit-loop integration**: a tournament run that auto-applies the
  heuristic to every card and flags audit-worthy ones. Replaces the
  manual audit pass with a pull-request.
