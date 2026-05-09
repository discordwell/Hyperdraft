---
name: cost-cards
description: "Use when designing, auditing, or rebalancing a card's mana cost in a Hyperdraft set — anytime the question is 'how much should this card cost?' Engine-agnostic core (vanilla curve, draw value, removal value, keyword premiums) with per-engine calibration tables (MTG, Finance, etc.). Use as the gate before committing a new card or as the lens for set-wide cost audits."
metadata:
  short-description: Heuristic-driven card costing for Hyperdraft sets
---

# Cost Cards

## Purpose

Cards are mispriced when the designer reaches for them via gut feel rather than against a benchmark. This skill turns "feels about right" into a step-by-step heuristic — vanilla baseline + ability premiums – condition discounts, calibrated to the target engine, sanity-checked against a format-tier benchmark.

Use this skill when the user asks to:
- Cost a new card design before committing it.
- Audit an existing set for cards that are over-priced or under-priced.
- Inform a spice pass with cost-aware reasoning (fold this skill into `spice-pass` when designing pushed cards — it tells you *how* to push, not just *that* you should).
- Re-derive cost during a balance pass without re-inventing the framework each time.

For full derivation, tables, and worked examples, read `references/cost-heuristics.md`. For per-engine calibration tables, read the matching `references/<engine>-calibration.md`.

## Decision Tree

For every card, walk this five-step tree. Stop only when you have a single integer cost (or a half-step you'll round per engine convention).

1. **Vanilla baseline.** Look up the engine's stat-line baseline at the target cost (or work backward: stats → cost). For HS-shaped engines (Finance, Hearthstone), `P + T = 2*cost + 1` with toughness skewed +1 over power. For MTG, vanilla curve is `P + T ≈ 2*cmc` with colored-mana premiums adding +1 P or +1 T.
2. **Add for each upside ability.** Use the ability premium table in `references/cost-heuristics.md`. Common values: +1/+1 stat ≈ 0.5 mana, draw 1 ≈ 2 mana, evasion ≈ 0.5–1 mana on a relevant body, single-target removal ≈ 2–3 mana, sweeper ≈ 4 mana, recurring trigger value ≈ trigger value × expected fires.
3. **Subtract for conditions.** Conditions discount the ability they gate. Common multipliers: "when you do X" ≈ ×0.6 if X happens 50%+ of turns, ×0.4 if rarer; "build-around" ≈ ×0.6 if requires support cards; "narrow counterplay" ≈ ×0.5 if dead vs half the meta. See `references/cost-heuristics.md` for the full table.
4. **Apply engine calibration.** Read the engine's calibration file. For Finance, named mechanics (Leverage, Arbitrage, Dark Pool, Short Selling, Alpha Strike) have specific premiums. For MTG, multi-color costs have specific bonuses.
5. **Sanity-check against format-tier benchmark.** Compare against a known card at this cost in the engine. "Is this card stronger or weaker than `<benchmark>`?" If stronger, the cost should be ≥ benchmark; if weaker, ≤ benchmark. Format-tier benchmarks live in the calibration file.

If steps 1–5 produce a half-mana cost, round to the engine's grain (whole mana for MTG/Finance/HS; specific dual-color for MTG). Document the rounding direction — round up for build-arounds (because they're already discounted), round down for compression cards (because they're already paying for two effects).

## Workflow

### When costing a new card

1. Read the card's intent (rules text + stats) and state effects in normalized form. Write down the stat line + each ability separately.
2. Walk the 5-step decision tree.
3. Compare result to the designer's gut-feel cost. If delta ≥ 1, write down which step contributed the disagreement. The gut-feel cost is sometimes right and the heuristic is wrong (engine-specific factor not yet captured) — record those exceptions back into the calibration file.
4. Cost the card at the heuristic-derived value. Spice-pass cards may push 0.5–1 below the heuristic if they target a build-around pattern (pattern 11 in `spice-pass`) and depend on support to deliver value.

### When auditing an existing set

1. Read each card in the set. Compute heuristic-derived fair cost.
2. Flag every card with `|delta| ≥ 1` mana into a punchlist file at `docs/sets/<set>/cost_audit.md`.
3. Group by severity: severely over (delta ≥ +2), over (+1), under (-1), severely under (-2). Within each group, sort by archetype.
4. Add a "Notes & open questions" section for cards the heuristic doesn't price cleanly (alt-win conditions, designed-as-trash flavor pieces, asymmetric prison effects).
5. **Don't re-price in the audit pass.** The audit is the punchlist; re-pricing happens in a follow-up balance pass. Mixing forward design and backward balance loses the signal.

### When re-balancing after a tournament

1. Read the tournament report. Find the cards with anomalous data (high cast rate + high WR for a card the heuristic said was fair, or low cast rate for a card the heuristic priced cheap).
2. For each anomaly, re-walk the heuristic. Identify which step produced the wrong number — usually a missing keyword premium or under-credited synergy.
3. Update the engine calibration file with the corrected premium / discount. Future cards inherit the correction.
4. Apply the corrected cost to the offending card.

## Common Pitfalls

- **Costing the printed text, not the played effect.** A card that says "draw a card" but only draws when a rare condition fires is not a draw card. Cost the average outcome, not the maximum.
- **Forgetting toughness premium.** In aggressive engines (Hearthstone, Finance HF archetype), toughness ≥ 1 above the curve trades up — that's a real cost premium, not a vanilla stat skew.
- **Treating tribal/build-around discounts as free.** A discount only applies if the support cards exist in the set. A "build-around mythic" without a synergy package is just an over-costed card.
- **Ignoring the format-tier sanity check.** The arithmetic can produce a "fair cost" that's still off-format. If your card costs the same as the format-defining benchmark but does less, you're over-costed regardless of what the math says.
- **Letting flavor override math.** "It's a Wrath, it should cost 4" is right *because* {4} is the math, not because of name recognition. Flavor names are a sanity check on math, not a substitute.

## Outputs

- For new cards: cost decision recorded in the card's docstring or PR description. "Heuristic: vanilla 2/2 ({2}) + draw on combat damage (+1) + Alpha Strike condition discount (-0.5) ≈ {2.5} → round up to {3} per build-around convention."
- For audits: `docs/sets/<set>/cost_audit.md` with the punchlist.
- For calibration learnings: append to the matching `references/<engine>-calibration.md`. Calibration files are living docs.

## Relationship to Other Skills

- **`spice-pass`**: cost-cards is the cost gate inside spice-pass. Spice cards target broken-card patterns; cost-cards prices them so the patterns are *intentionally* pushed, not accidentally so.
- **`implement-mtg-cards`**: cost-cards informs the *cost field*; implement-mtg-cards wires the *behavior*. They're orthogonal: cost-cards doesn't tell you how to wire a trigger, implement-mtg-cards doesn't tell you what cost to wire it at.
- **`build-decks`**: deck-builders use cost as a tempo signal. If cost-cards mis-prices answers, build-decks will under-include them. The counterplay-costing memory (folded into `references/cost-heuristics.md`) was originally a build-decks heuristic.
