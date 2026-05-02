# Pokemon Strategy Notes

## Research Inputs

- The official Pokemon TCG rulebook gives the baseline construction constraints:
  60 cards exactly, a four-copy limit except basic Energy, at least one Basic
  Pokemon, one or two Energy types as a starting point, enough Energy to cast
  attacks, and Trainers such as Ultra Ball as consistency tools.
  Source: https://assets.pokemon.com/assets/cms2/pdf/trading-card-game/rulebook/sm6_rulebook_en.pdf
- Pokemon's own strategy writing emphasizes that attaching Energy and playing a
  Supporter almost every turn is critical, and that draw Pokemon help attackers
  keep functioning.
  Source: https://www.pokemon.com/us/strategy/quick-on-the-draw
- JustInBasil's deckbuilding guide is useful for current competitive structure:
  consistency/setup cards are distinct from raw draw, a typical modern Energy
  baseline can be much lower than starter rulebook counts, and Rare Candy is a
  major speed tool for Stage 2 decks.
  Source: https://www.justinbasil.com/guide/crafting-your-deck

## Claude/Baseline Blind Spots

- Search/setup Items were played after basics, evolution, and Energy. Nest Ball,
  Ultra Ball, and Rare Candy therefore could not improve the current turn's board
  or attachment target.
- Rare Candy was present in the shared guild trainer suite but had no resolve
  function, so the AI could score it positively and discard it without evolving.
- Trainer resolution happened while the Trainer was still in hand. Draw and
  shuffle effects could accidentally include the resolving card, which made
  card-flow telemetry and strategy comparisons unreliable.
- Attack scoring overvalued raw damage. It did not distinguish useful damage
  from overkill or penalize Energy-discard attacks unless the card used an
  explicit `discard_cost` field.

## Codex Strategy Shape

- `ultra` is the deterministic extra-hard Pokemon profile, with extra
  resource-conservation, setup-consistency, and attack-pressure flags.
- Codex/Ultra profiles cash setup/search Items before hand-reset Supporters,
  rebuild context, then choose basics, evolutions, and Energy attachment from
  the updated board.
- Codex attack scoring values prize-taking and useful damage, but discounts
  wasteful overkill and non-lethal Energy-discard attacks.
- Codex pressure scoring now means meaningful damage, not merely any legal
  attack: Energy attachments prioritize attacks that come online this turn,
  but 20-damage basics do not override real attacker development.
- Codex can skip attacks that are strategically negative because they draw into
  deck-out, and late deck-thinning Trainers are hard-discounted.
- Codex basic-benching scoring rewards early board filling and utility Pokemon,
  while reducing late low-impact bench clutter.

## Latest Promotion

- Promoted the broad setup/search Item pass after correcting duplicated draw and
  search side effects in the Ravnica Pokemon card scripts.
- Public Pokemon difficulties remain `easy`, `medium`, `hard`, and `ultra`; the
  improved profile is promoted into the extra-hard `ultra` setting while
  `medium` remains the mid-level baseline.
- On the 160-game corrected-simulation matrix, promoted `ultra` beat `medium`
  `118-42`, with `+56` prize margin, `+226` attacks, `+604` damage counters,
  `+30` knockouts, no errors, and no Ultra mirror timeouts.
- Variant checks rejected opening Active selection and narrower setup filters:
  they either reduced win rate or converted wins into low-pressure deck-out
  races with worse damage/knockout margins.
