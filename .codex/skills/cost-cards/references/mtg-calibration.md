# MTG Calibration

Engine-specific cost values for the 12 real MTG sets in Hyperdraft (`src/cards/<set>/`) and the ~19 custom MTG-style sets (`src/cards/custom/<set>/`).

The MTG engine is the *source* of most cost-heuristics values, so this file is short — it mostly lists format-tier benchmarks and color-pie premiums.

## Engine snapshot

- **Resource**: mana, colored. Cost strings like `{1}{W}{B}`.
- **Speed**: instants and abilities work at any time. Removal is reactive. This is what makes MTG's vanilla curve *lower* than HS's: a 4-mana 4/5 in MTG is a *bomb*, not a Yeti.
- **Combat math**: damage clears at end of turn. Toughness premium reflects combat-survival, not damage-persistence.
- **Card types**: creatures, instants, sorceries, enchantments, artifacts, equipment, lands, planeswalkers, sagas, battles, kindreds.

## Vanilla curve

See `cost-heuristics.md` Section 1. Reproduced for quick scan:

| CMC | Mono "fair" | Two-color "fair" | Mythic / pushed |
|---|---|---|---|
| 1 | 1/1 | 2/1 | 1-mana threats with text |
| 2 | 2/2 (Grizzly Bears) | 2/3 / 3/1 | Pushed 2-drops |
| 3 | 3/3 (Hill Giant) | 3/4 / 4/3 | 3-mana planeswalker / haste finisher |
| 4 | 4/4 | 4/5 / 3/5 | Sheoldred-tier |
| 5 | 5/5 | 5/6 / 4/6 | Mythic flyer |
| 6 | 6/6 | 6/7 | Format-defining finisher |
| 7+ | 7/7+ | 7/8+ | Build-around fattie |

## Colored mana premium

Adding a color (going from `{2}` to `{1}{R}` to `{R}{R}`) packs more value into the same CMC. Roughly:

| Cost shape | Shape value | Notes |
|---|---|---|
| `{N}` (all generic) | baseline | Colorless restriction; usually artifacts. |
| `{N}{C}` (one color) | +0.25 mana of value | Most cards. |
| `{N}{C}{C}` (double-pip) | +0.5 mana of value | Stronger color expression. |
| `{C}{D}` (two-color hybrid) | +0.5 mana of value | Either-color flexibility. |
| `{C}{D}{E}` (three-color) | +1 mana of value | Multicolor restriction is deck-construction tax + payoff. |

In other words: a 2-mana 2/2 should be 2/2; a `{R}{R}` 2/2 should be 2/3 or include text; a `{R/G}{R/G}` (hybrid) 2/2 should include flexible text.

## Format-tier benchmarks

These are the cards every MTG designer should know. They define the "fair" cost at each tier and serve as the gut-check.

### 1-mana benchmarks

- **Lightning Bolt** ({R}): 3 dmg anywhere. The floor for damage-as-removal.
- **Path to Exile** ({W}): destroy any creature with downside. The floor for unconditional removal.
- **Swords to Plowshares** ({W}): same as Path with life downside. Equivalent.
- **Brainstorm** ({U}): draw 3 / put 2 back. Library-sculpting; "draws 1 net" but the sculpting is the value.
- **Ponder / Preordain** ({U}): scry/cantrip. Library smoothing.
- **Unsummon** ({U}): bounce a permanent. The floor for tempo plays.
- **Ragavan, Nimble Pilferer** ({R}): 2/1 dash + treasure on damage + steal-cards. The most pushed 1-drop in modern Magic.

### 2-mana benchmarks

- **Counterspell** ({U}{U}): counter any spell. The fair counter.
- **Snapcaster Mage** ({1}{U}): 2/1 flash + flashback grant. Pushed; format-defining.
- **Tarmogoyf** ({1}{G}): 2/2+ scaling fattie. Pushed; format-defining.
- **Fatal Push** ({B}): conditional removal (CMC ≤ 2 or revolt). Pushed; common in modern.
- **Thoughtseize** ({B}): hand disruption with life cost. The fair discard.
- **Inquisition of Kozilek** ({B}): cmc-2-or-less hand disruption. Slightly weaker than Thoughtseize; same cost.
- **Lightning Helix** ({R}{W}): 3 dmg + 3 life. Double-color Bolt with lifegain.
- **Stoneforge Mystic** ({1}{W}): equipment tutor + auto-equip. Pushed; banned in most formats.

### 3-mana benchmarks

- **Murder** ({1}{B}{B}): unconditional kill. The fair removal.
- **Liliana of the Veil** ({1}{B}{B}): planeswalker, generic edict. Modern-tier 3-drop benchmark.
- **Anger of the Gods** ({1}{R}{R}): 4 dmg sweeper with exile. Pushed sweeper.
- **Fact or Fiction** ({3}{U}): split-pile draw. Pushed card-advantage.
- **Goblin Rabblemaster** ({1}{R}{R}): 2/2 with token + lord on attack. Pushed aggressive 3-drop.
- **Reflector Mage** ({1}{W}{U}): bounce + delay. Pushed tempo.

### 4-mana benchmarks

- **Wrath of God** ({2}{W}{W}): destroy all creatures, no regen. The fair sweeper.
- **Damnation** ({2}{B}{B}): same as Wrath in black. Equivalent.
- **Sheoldred, the Apocalypse** ({2}{B}{B}): 4/5 + draw-loss-life trigger + lifelink. Modern Standard "must-answer" 4-drop.
- **Solitude** ({3}{W}, can pitch for {W}): exile creature. Pitch elemental — pushed, format-defining.
- **Fable of the Mirror-Breaker** ({2}{R}): saga that compresses 3 modes. Pushed; format-defining.

### 5-mana benchmarks

- **Mind Twist** ({X}{B}{B}): unbounded discard. Banned for being too efficient.
- **Bonfire of the Damned** ({X}{X}{R}): X dmg sweeper with miracle. Pushed.
- **Cryptic Command** ({1}{U}{U}{U}): 4-mode. Format-defining.

### 6-mana benchmarks

- **Plague Wind** ({7}{B}): destroy all opp's creatures. Asymmetric Wrath.
- **Eldrazi Conscription** ({8}): aura granting +10/+10 + annihilator. Win-condition aura.
- **Karn Liberated** ({7}): planeswalker, exiles permanents. Format-defining 7-mana.

### 7+ mana benchmarks

- **Emrakul, the Aeons Torn** ({15}): if the game has lasted this long, you win.
- **Storm Crow** ({1}{U}): the joke benchmark. (Vanilla 1/2 flying. Strictly worse than Wind Drake.)

## Color pie & premium-color value

| Color | What it pays premium for |
|---|---|
| White | Removal (Path, Swords), sweepers (Wrath), defensive value, fliers, lifegain |
| Blue | Counters, draw, bounce, tempo |
| Black | Single-target removal (Murder, Path-shape), card draw with cost (Sign in Blood), discard, recursion |
| Red | Damage, haste, treasure tokens, ramp via rituals, fast aggro |
| Green | Mana acceleration (ramp), big creatures, fight effects, +1/+1 counters |

A monocolor card priced at `{N}{X}` should match the color's strengths. A red sweeper costs more than a black sweeper costs more than a white sweeper of equivalent power — because each color is "best" at different effects. Use the format-tier benchmark to pick the right cost.

## Multicolor / hybrid premiums

- **2-color allied** (UW, BR, etc.): no premium beyond `{1}{C}{D}` shape. Standard.
- **2-color enemy** (UR, BW, etc.): often slightly pushed historically. No formal premium.
- **3-color** ({C}{D}{E}): pushed by ~0.5 mana of value over single-color equivalents. Players are paying a deck-construction tax.
- **Hybrid mana** ({C/D}): no premium — the flexibility is the deck-construction value, paid in slots.
- **Phyrexian mana** ({C/P} = pay {C} or 2 life): treat as a half-cost; cards like Mental Misstep pay 0 mana but 2 life, and were broken.

## Common audit patterns in Hyperdraft real-MTG sets

When applying this calibration to existing real-MTG sets (FDN, WOE, LCI, MKM, OTJ, BLB, DSK, EOE, ECL, SPM, TLA, FIN), the cards are pre-priced by Wizards. The calibration here is for *new* custom MTG-style cards (in `src/cards/custom/<set>/`).

Common patterns to flag:
1. **Fan-set creatures with stat lines that exceed Wizards' modern curve**: a 5/5 for {3} in green (Doubling Season-tier) is wrong.
2. **Custom keywords that lack a premium**: if you've added a new keyword (e.g. "Volcanic" = "haste + first strike"), price it like the union of its components, not as a free upgrade.
3. **Crossover sets with "balanced" tribal lords at {2}**: lords are worth +0.5–1 mana each. A {2} lord is pushed; a {3} lord is fair.

## Open calibration questions for MTG

These need data:
1. **Tribal payoff cards in mono-color**: Lord of Atlantis at {1}{U} for 2/2 + double-lord is pushed but in a narrow tribe. Fair only if Merfolk has 8+ supporting cards.
2. **Saga cost in custom sets**: Sagas pack 3 abilities into one card cost; the average per-ability cost is lower than the standalone effect. Need to recalibrate after Hyperdraft saga support stabilizes.
3. **Equipment with auto-attach**: Stoneforge-style tutors pre-empt the equip cost. Should be priced higher than equipment + tutor would suggest.

## How to update

Same process as Finance calibration. Add data points to relevant sections, update rules, reference back to the trigger event.
