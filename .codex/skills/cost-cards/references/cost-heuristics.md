# Cost Heuristics — Engine-Agnostic Core

This document is the substantive reference for the `cost-cards` skill. It lists the values, premiums, and discounts used in the 5-step decision tree.

**Reading order**: skim once. When pricing a specific card, jump to the relevant section.

---

## 1. Vanilla baselines

Two engine families. Hyperdraft's MTG-shape engines (real MTG sets, custom MTG sets) follow the MTG curve. HS-shape engines (Finance, Hearthstone, Pokemon TCG with caveats) follow the HS curve.

### MTG vanilla curve — `P + T ≤ 2 * cmc` (with colored-mana premium)

| CMC | Mono color "fair" | Two-color "fair" | Mythic / pushed |
|---|---|---|---|
| 1 | 1/1 (vanilla) or 1/2 / 2/1 with downside | 2/1 (e.g. Goblin Guide-tier) | 1-mana threats with text (Ragavan tier) |
| 2 | 2/2 (Grizzly Bears) | 2/3 / 3/1 (Watchwolf-tier) | 2-power evasion / push to 2/3 with ETB (Snapcaster tier) |
| 3 | 3/3 (Hill Giant) | 3/4 / 4/3 with text | 3-mana planeswalker / haste finisher |
| 4 | 4/4 vanilla | 4/5 / 3/5 with keyword | Sheoldred-tier (4/5 + lifelink + draw payoff) |
| 5 | 5/5 vanilla | 5/6 / 4/6 with keyword | 5-mana flying / mythic legendary |
| 6 | 6/6 vanilla | 6/7 / 7/6 with text | 6-mana finisher with multiple abilities |
| 7+ | 7/7 vanilla | 7/8 with text | scaling fattie with build-around |

The "vanilla test": a creature with no abilities at the listed P/T at the listed cost is *playable but not exciting*. Anything that fails the vanilla test (e.g. 2/2 for {3}) needs to make up the deficit with abilities, conditions, or a downside-as-flavor.

Off-square stats: 1/3 vs 2/2 vs 3/1 at {2} are roughly equivalent in total power-budget; the choice is which combat the card wants to be in. 3/1s die to ping/Bolt; 1/3s wall a Bear; 2/2s trade. Pricing is the same.

### HS vanilla curve — `P + T = 2*cost + 1`, toughness skewed +1

This is the Chillwind Yeti rule: 4-mana 4/5 = 9 stats. Generalizes:

| Cost | Stats (square baseline) | Common splits |
|---|---|---|
| 1 | 1/2 or 2/1 (P+T=3) | 2/1 aggressive, 1/2 walls |
| 2 | 2/3 or 3/2 (P+T=5) | 3/2 aggressive, 2/3 trade |
| 3 | 3/4 or 4/3 (P+T=7) | 3/4 generalist, 4/3 push |
| 4 | 4/5 (P+T=9, Yeti) | the canonical "play and stop" |
| 5 | 5/6 (P+T=11) | 5/6 control, 6/5 push |
| 6 | 6/7 (P+T=13, Boulderfist Ogre) | mid-control finisher |
| 7 | 7/8 (P+T=15) | rare in modern HS |
| 8+ | scales linearly: P+T = 2*cost + 1 | usually paired with abilities |

The HS curve is **higher than MTG** because HS has no instant-speed interaction during the turn. With no instants, the toughness premium for surviving combat is bigger. Finance follows the HS curve because Finance also has limited instant-speed interaction (Orders are the only instant-shape cards, and most are conditional).

A card priced "HS-shaped" but with MTG-style instant-speed answers all around it (e.g. Pokemon TCG's instant abilities) needs to drop toward the MTG curve.

### Pokemon / YGO note

These engines have HP/Defense systems that don't map cleanly to the P+T model. The vanilla curve concept still applies — cost vs total stats — but the calibration files for those engines need their own baseline. See `references/<engine>-calibration.md` (TODO for non-piloted engines).

---

## 2. Stat premiums

Once you're above the vanilla curve, each extra stat point costs incremental mana.

| Premium | MTG cost | HS / Finance cost | Notes |
|---|---|---|---|
| +1 power above curve | +0.5 mana | +0.5 mana | Aggressive sets value power slightly more than control sets. |
| +1 toughness above curve | +0.5 mana | +0.5–1 mana | HS values toughness more (no removal mid-turn). |
| Off-square (3/1 vs 2/2) | 0 | 0 | Trade-off only; total stats are the cost. |
| +2 above curve | +1.5 mana | +1.5 mana | Premiums compound slightly. |
| +3+ above curve | full reroll — card is a fatty, restate baseline | | |

**Round numbers**: a card that is "1 stat over curve" is fair to cost +0.5 mana, but in a {1}/{2}/{3} grain engine you can't actually cost 2.5. Round up if the stat is toughness in HS; round down if it's power in MTG (because power sits behind interaction).

---

## 3. Card-advantage premiums

The most-misunderstood pricing axis. Drawing a card is not free; replacing yourself is.

| Effect | Premium | Notes |
|---|---|---|
| Replace-self cantrip ("draw a card" added to a spell) | +1 mana | Snapcaster grants flashback + draws on cast (the spell + the body)— net +1 from replace-self. |
| Pure draw 1 (sorcery) | 2 mana sorcery | Inquisition tier. Ponder/Preordain are 1 mana with library control. |
| Draw 2 (sorcery) | ~3 mana | Divination = 3. Sign in Blood = 2 with life cost. |
| Draw 3 (sorcery) | ~5 mana | Concentrate = 4 with downside; 5 mana for unconditional 3. |
| Draw 4 | ~6 mana | Big finisher tier. |
| Draw N where N > opp's hand or similar conditional | priced like draw 2-3 | The condition rarely caps the value because deck-builders engineer it. |
| Recurring draw 1/turn | priced like the body it's on + 2 mana | Phyrexian Arena tier. Needs some condition (life cost, attacker-based). |
| Loot 1 / discard 1 | +0.5 mana | Faithless Looting = 1 mana. The discard offsets the draw. |
| Scry 1 | +0.5 mana (tacked on) or 1 mana standalone | Library smoothing, not card advantage. |
| Surveil 1 / mill 1 | +0.5 mana | Conditional value — only matters if the GY matters. |

Critical: a card that says "draw a card" but only fires under a narrow condition is *not* a draw card. Apply the condition discount in section 8.

---

## 4. Removal & damage premiums

The user's `feedback_counterplay_costing.md` memory is the foundation. Folded in here.

### Single-target removal (kill 1 creature)

| Effect | Cost | Benchmark |
|---|---|---|
| 3 damage to anything (creature or player) | 1 mana | Lightning Bolt |
| Destroy any creature, no downside | 3 mana | Murder |
| Destroy creature, color/type restriction | 2 mana | Doom Blade |
| Destroy creature, gives opp a downside (basic land, life) | 1 mana | Path to Exile, Swords to Plowshares |
| Destroy creature with stat condition ("toughness ≤ 3") | 2 mana | Cast Down, Eaten Alive |
| Counter target spell | 2 mana | Counterspell |
| Counter target creature spell | 1 mana | Spell Pierce conditional, Stubborn Denial |
| Bounce single permanent | 1 mana | Unsummon |
| Tap target creature (no untap) | 2 mana | Lullmage, conditional |

### Sweepers

| Effect | Cost | Benchmark |
|---|---|---|
| 4 damage to all creatures (kills bears, leaves big stuff) | 3 mana | Anger of the Gods, Pyroclasm |
| Destroy all creatures | 4 mana | Wrath of God, Day of Judgment |
| Destroy all creatures with condition (e.g. cmc ≤ 3) | 3 mana | Toxic Deluge (life cost), Fiery Confluence modal |
| Symmetric sweeper (hurts you too) | 3 mana | Pyroclasm, Anger |
| Asymmetric sweeper ("destroy all opp's") | 5 mana | Sublime Archangel-shape; rare |
| Mass bounce | 4 mana | Cyclonic Rift modal |

### Format-tier modifiers

- If a {2} removal also draws a card or grants a body, +1 mana premium → costs {3}. (See compression / threat-and-answer in spice-pass pattern 4.)
- If a sweeper also creates a permanent or refills your hand, +1 mana → costs {5} (Plague Wind tier).
- If removal is conditional but on a *narrow* condition (only specific archetype), discount per section 8.

---

## 5. Keyword premiums

| Keyword | Premium | Conditions |
|---|---|---|
| Flying | +0.5–1 mana on relevant body | More valuable on attackers (2+ power); cheap on walls. |
| Haste | +0.5 mana for power ≤ 2; +1 mana for power 3+ | Lightning Berserker, Goblin Guide. |
| Vigilance | +0.5 mana | Dual-purpose attacker/blocker. |
| Trample | +0.5 mana on power 4+; +0.25 below | Useless on small bodies. |
| Lifelink | +0.5–1 mana | Scales with power; lifelinkers in race-y formats are pushed. |
| Deathtouch | +1 mana | Punishes blocking; flat premium. |
| First strike | +0.5 mana | Power-side advantage. |
| Double strike | +1.5 mana | ~2x effective power on offense. |
| Hexproof / Ward {N} | +0.5–1 mana | Hexproof is stronger than ward. |
| Reach | +0.25–0.5 mana | Niche; defensive. |
| Menace | +0.25 mana | Mild evasion. |
| Indestructible | +1.5 mana | Powerful; usually conditional on a card. |
| Defender | -1 mana | Downside; wall pricing. |
| Can't block | -0.5 mana | Aggressive downside. |

**Stacking**: keywords are not strictly additive. Flying + first strike + lifelink at {3} is more than the sum of premiums because the package is hard to remove and impossible to race. Apply stacking penalty: 2 stacked keywords = sum * 1.0; 3+ stacked = sum * 1.2 (or call it a pushed card and let `spice-pass` justify).

**Engine-specific keywords**: see `references/<engine>-calibration.md`. Finance has Leverage, Arbitrage, Dark Pool, Short Selling, Alpha Strike — each with its own premium derived from its mechanical impact.

---

## 6. Mana / ramp / cost-reduction premiums

| Effect | Cost | Benchmark |
|---|---|---|
| Generate 1 mana once (Treasure token) | 0.5 mana on a body, 1 mana standalone | Treasure tokens are ubiquitous. |
| Generate 1 mana per turn (recurring) | 2 mana standalone | Llanowar Elves at 1 mana = pushed; Sol Ring at 1 mana = format-defining. |
| Add 2 mana once | 2 mana | Dark Ritual = 1 mana with -2 life cost (narrow). |
| Cost reduction "your X cost {1} less" | 2 mana standalone, 1 mana on a body | Goblin Electromancer = 2 mana 2/2 with cost reduction. |
| Land drop bonus / extra land | 2 mana | Exploration, Burgeoning. |

Mana is anti-fungible: cheap mana acceleration cascades the curve. A {1} accelerator that gets you to {3} on turn 2 is worth more than {1} of mana — it's worth the *tempo gain* of seeing that {3} a turn earlier. This is why Llanowar Elves and Sol Ring are so much better than the math suggests.

---

## 7. Tutoring / consistency premiums

| Effect | Cost | Benchmark |
|---|---|---|
| Tutor any card | 4+ mana | Demonic Tutor at 2 mana = restricted/banned. |
| Tutor specific type (creature, instant) | 3 mana | Worldly Tutor at 1 mana = pushed (top of library, not hand). |
| Tutor specific subtype (Elf, Dragon) | 2 mana | Eladamri's Call ({1}{G}{W}). |
| Tutor with cost cap (Mystic Snake-tier) | 2 mana | Eldritch Evolution. |
| Search for basic land | 2 mana | Cultivate, Rampant Growth. |
| Improvised tutor (e.g. Diabolic Intent w/ sac cost) | 2 mana with cost | Self-sac costs offset. |

Tutors are *consistency*: they let a deck access the right card, every game. Every tutor effect should be priced 1+ mana more than the equivalent draw effect — drawing the named card is strictly better than drawing a random card.

---

## 8. Conditional discounts

Conditions reduce the value of an ability proportional to how often the condition fires. Common discounts:

| Condition | Multiplier | Notes |
|---|---|---|
| "Whenever you do X (X is a thing your deck does each turn)" | ×0.6 | Likely fires 50–80% of turns. |
| "Whenever you do X (X is a build-around)" | ×0.4 | Fires only in the dedicated deck. |
| "If you control more X than opp" | ×0.5 | Tribal-shape; depends on deck. |
| "If your life ≤ 13" | ×0.4 | Niche; mostly aggro mirror. |
| "Once per turn" | ×0.7 | Caps the upside but most abilities only fire once anyway. |
| "Once per game" | ×0.4 | Significant. |
| "If a creature died this turn" | ×0.6 | Fires reliably in midrange. |
| "If a card was cycled this turn" | ×0.4 | Build-around. |

**Worked example**: a card that says "draw a card whenever a Trader deals combat damage to a player" is a recurring-draw-1, gated on "Trader hits face." In a Finance HF deck this happens every turn (×0.7 multiplier), so the draw is worth 1.4 mana. Vanilla 2/2 ({2}) + 1.4 mana ≈ {3.4} → round to {3} pushed or {4} fair.

---

## 9. Build-around discount (pattern 11 from spice-pass)

The hardest one to price. A "build-around" is a card whose payoff is huge in its dedicated deck and trivial elsewhere.

**Discount**: ×0.6 of the *full payoff cost*, only when ≥8 partner cards exist in the set's synergy registry. Without partners, the card is just over-costed.

**Compounding rules**:
- If the build-around payoff is also a *snowball value engine* (pattern 3), don't discount past 0.7. The snowball makes the card oppressive even in average decks.
- If the build-around payoff is *symmetric* (helps both players), discount to 0.5. Glass cannon.
- If the build-around payoff is *uncopyable* (only the named card triggers it, no related cards), discount stays at 0.6. The "unique" tax doesn't change pricing.

**Worked example**: a card whose payoff at full power would cost {6} (e.g., draw 4 cards) but requires "if you have 5+ Dark Pool Orders triggered this game" → ×0.6 → {3.6} → cost at {4} pushed or {3} format-defining if you want it to anchor the archetype.

Reference: `spice-pass.md` discusses pattern 11 testing methodology (capability test, focal-in-opener stacking).

---

## 10. Win-more / compounding-mechanic discount inversion

When an ability *only* matters when you're already winning, it shouldn't be discounted — it should be *upcharged*. The user feedback memory `feedback_winmore_mechanics.md` flagged this.

**Rule**: if a card's payoff scales with a condition that means you're already ahead (e.g. "double the +1/+1 counters on a creature you control"), don't apply the conditional discount in section 8. Instead, treat it as a snowball value engine (pattern 3) and add +0.5–1 mana premium. The card is genuinely card-advantage when it fires; it just doesn't help you stabilize.

This inverts the usual "condition makes it worse" intuition. In a winning position, the card is a finisher; the cost reflects that.

---

## 11. Asymmetric prison (pattern 5) and tempo theft (pattern 9)

These two patterns have prices outside the additive system.

- **Asymmetric prison** ("opp can't play X"): cost is set by *what the prison breaks*. Blood Moon at {3} breaks non-basic-land manabases entirely; Stony Silence at {2} shuts off most artifact-heavy decks. These should be priced 1 cost below where their hated archetype's threats land — because if they're *reactive*, they need to come down before the threat does, or they're useless.
- **Tempo theft** (extra turns, extra combats): no good additive pricing. Time Walk at {1}{U} is banned everywhere; Temporal Manipulation at {3}{U}{U} = 5 mana is the modern fair tier. Extra combat: {3}–{4}. These are inherently broken cards and should rarely appear in custom sets.

For these patterns, **cost by analogy** to known cards in the engine, not by the additive heuristic.

---

## 12. Format-tier benchmark sanity check

After steps 1–11, compare to a known card at the resulting cost in the engine. The benchmark answers "is this card stronger than X at the same cost?"

Live in the calibration files. MTG benchmarks: Lightning Bolt, Snapcaster Mage, Sheoldred, Wrath of God, Counterspell. Finance benchmarks: Statistical Arb Clerk ({1} 1/2 Arbitrage 1), Pairs Trader ({3} 2/3 Arbitrage 2), Hedge Fund PM ({5} 4/4 Leverage 2 + Derivatives sweeper).

If your card is stronger than the benchmark at the same cost, raise cost. If weaker, lower cost. Do not commit a card that is "the heuristic says it's fair, but it's clearly stronger than X."

---

## Stacking the ability premiums

When a card has 3+ abilities, premiums are super-additive: the package is more valuable than the parts. Apply a "compression bonus":

- 2 abilities: sum × 1.0
- 3 abilities: sum × 1.15
- 4 abilities: sum × 1.3
- 5+ abilities: full restate — call it a planeswalker/legendary and price by analogy.

This is why Snapcaster Mage at {1}{U} is so good: 2/1 body ({1}) + flash (+0.5) + flashback grant (+1.5 for the average flashback) = ~{3} before compression. With compression × 1.15 = {3.45}. Snapcaster's actual cost is {2} — an explicitly pushed Modern-tier card. The math says it's 1+ mana under fair, which matches reality.

---

## Half-mana costs and the rounding rule

The heuristic produces fractional costs. Round per engine grain (whole mana for MTG/Finance/HS).

- Round **up** for build-arounds: they're already discounted, and an extra 0.5 cost doesn't kill them in the dedicated deck.
- Round **down** for compression cards (3+ abilities): the package is the value; you don't want to over-charge for something that's already efficient.
- Round **up** for cards with ETB that you don't want flooded: e.g. a {2.5} ETB that's worth re-casting via Snapcaster should round to {3} so it's not a 1-mana-effective effect with flashback.
- Round **down** for cards with snowball mechanics: they generate their own value; don't double-tax with rounding.

Document the rounding direction in the card's design rationale. Future audits will check the rounding decision.

---

## Quick reference: format-tier benchmarks (cards every designer should know)

| Card | Cost | Why benchmark |
|---|---|---|
| Lightning Bolt | 1 | 3-damage flexible removal, the floor for damage |
| Path to Exile | 1 | Best 1-mana unconditional removal (with a downside) |
| Counterspell | 2 | The fair counter; everything cheaper has a condition |
| Murder | 3 | Unconditional kill at fair cost |
| Wrath of God | 4 | Fair sweeper, the ceiling on board reset |
| Grizzly Bears | 2 | The 2/2 floor; everything above this is "real" |
| Snapcaster Mage | 2 | Pushed 2-mana threat; the bar for premium 2-drops |
| Tarmogoyf | 2 | Pushed 2-mana fattie; format-defining |
| Sheoldred | 4 | Modern-Standard "must-answer" 4-drop |
| Ragavan | 1 | The most pushed 1-drop ever printed |
| Liliana of the Veil | 3 | Modern-tier planeswalker baseline |

**For Finance, see `references/finance-calibration.md`.**

---

## Calibration is a living doc

Heuristic values in this doc are derived from MTG and HS empirics. Any time a card audit, tournament, or design exercise reveals a calibration gap, edit the relevant section and reference the data point. The decision tree should be stable; the values are tunable.
