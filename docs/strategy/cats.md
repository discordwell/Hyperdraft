# Cats Strategy Doc

Persistent format-level wisdom for the Cats engine — 9-round trick-taking +
pile-building game. Updated by the ultra-agent after each LLM-piloted match.

## Win conditions

- **Highest total score across territory + nap + snack piles** at the end of
  round 9 (or earlier if both hands empty after a refill cycle).
- Tiebreaker: more cards in the **attention pile**. Further tie: draw.
- Each pile scores differently:
  - **Territory**: 1pt / card, +2 per attached Trinket, **+5 bonus if ≥6 cards**.
  - **Nap**: 2pt / card, **capped at 12pt total**.
  - **Snack**: 3pt / card while pile <5 cards, drops to **1pt / card at 5+**.

## Format-level principles (the 5 patterns)

1. **Pile sequencing over time.** Early rounds: Snack pile is the best
   per-card rate (3pt). Stuff it FIRST, but stop at 4 cards to avoid the
   greed cliff. Mid rounds: shift to Nap (2pt/card, max 12pt → 6 cards
   gets you the cap). Late rounds: dump into Territory for 1pt/card +
   Trinket and ≥6-card bonuses.

2. **Snack denial.** Filling your own Snack pile shuts opponent off from
   the snack-force play. When opponent's Snack is at 3/5, dumping a junk
   Snack to force them past the greed threshold (5+ cards = 1pt/card) is
   a swing of 8+ points.

3. **Effect-driven play.** Cards have pile-entry triggers (draw on nap,
   peek-hand on territory, +1 to a played value, etc.). The cards' `text`
   field matters more than `value` once you're 3+ rounds in. Bias pile
   choice toward the pile that triggers the entering card's effect.

4. **Hand-size pressure.** Both hands deplete each round. When opponent
   has 1-2 cards left, they're about to refill from library — exploit the
   tempo gap by pushing for trick wins NOW. Conversely, when YOU have 1-2
   cards left, conserve high-value cards for tricks you can guarantee.

5. **Sneaky pessimism.** Sneaky cards' value is hidden (a `sneaky_value`
   1-10 on the card def, only the engine sees it). Without revelation,
   treat opponent Sneakies as max-9. Gary the One-Eyed Tabby (Shadow Cats
   commander) flips this for his side — but he doesn't help against
   Sneakies the opponent plays.

## Per-deck plans

### Couch Empire (Karen the Dignified Calico)

- **Plan**: Territory control. Stack Territory pile to ≥6 for the +5 bonus,
  then layer 3 trinkets (Karen lets you have 3, not 2). Sleek cats Mister
  Whiskers (7) and Magnificent Bartholomew (10) dominate Sleek default rule.
- **Pile sequencing**: Round 1-2 push for Snack early (small pile bonus),
  rounds 3-5 fill Nap, rounds 6-9 stuff Territory.
- **Key cards**: Bartholomew (Sleek 10), Mister Whiskers (Sleek 7 + peek),
  Heated Blanket trinket (+1 score per nap card), Yarn Ball + Window Perch
  trinkets (Territory boosts).
- **Trick rule preference**: Sleek (highest wins) — you have the high cats.

### Naptime Tyrants (Sir Reginald Loafington)

- **Plan**: Nap stuffing. Reginald lifts the Nap cap from 6→8 cards;
  Heated Blanket adds +1 per nap card. Stack 7+ cards in Nap with score
  modifiers and you hit 20+ Nap points alone.
- **Key cards**: Magnificent Bartholomew (draw-2 on Nap entry — engine
  fire), Sir Reginald (commander, Nap cap +2), Heated Blanket trinket,
  Sunbeam trinket (+2 score per nap-card while attached).
- **Trick rule preference**: Fluffy (you hold mid-high Fluffies) or default
  Sleek when leading high-value cats.
- **Note**: The most-tested LLM win deck (66.7% in tournament) — the
  Reginald+Heated Blanket+Bartholomew engine is robust under any pilot.

### Snack Rush (Princess Mayhem the Third)

- **Plan**: All 8 Snacks + Cardboard Box. Force every trick into Snack via
  Snack-force; Princess Mayhem adds +1 per snack-card while pile <5.
- **Key cards**: Princess Mayhem commander, Catnip Mouse (Snack with
  draw-on-entry), Tuna Can (Snack force).
- **Critical**: STOP at 4 Snack cards. Crossing 5 turns 4×3=12pt into
  5×1=5pt — a 7-point swing INTO the opponent's column. Use Cardboard Box
  +1 score boost on the 4th card to lock in 13+ points.
- **Trick rule preference**: Sleek default. Snacks usually have low value
  (1-2), so you win on the Snack-force not the value comparison.
- **Note**: Weakest archetype (33% in LLM tournament). Plays high-variance —
  if you don't win the snack-trick, you feed the opponent's pile. Plan
  conservative: only force snack when you're certain to win.

### Shadow Cats (Gary the One-Eyed Tabby)

- **Plan**: All 7 Sneakies + heavy Moods. Sneaky cards' hidden values
  decide the trick under Sneaky rule; Moods can swap the rule mid-round
  (e.g. install Scrappy when holding low cats).
- **Key cards**: Madam Inkblot (Sneaky 3 printed / 10 hidden — bluff),
  Whispertoes (Sneaky 9 printed / 1 hidden — reverse-bluff), 3 a.m.
  Zoomies Mood ("lowest wins this round"), Aggressive Loafing Mood.
- **Trick rule preference**: Sneaky (your team sees their own hidden
  values; Gary sees opponent's via PKM_REVEAL — note this event currently
  emits a wrong-engine name; see engine gaps).
- **Mood use**: Drop Moods as Counter when you're losing a value comparison.

### Greg's Diary (Greg)

- **Plan**: Greg's commander effect TBD — read state.cats_commanders for
  payload. Treat as midrange until the LLM tournament gives us a 10+ game
  sample. Provisional pile sequencing: same as Naptime (mid-rounds Nap,
  late Territory).

### Naptime Denial (Gary)

- **Plan**: Anti-Naptime control deck (Gary as commander). Use junk Snacks
  to force opponent's wins into Snack-overflow, denying Nap stacking.
  Conservative card commitment — bait the opponent into Snack greed cliff.

## Known engine gaps

From `docs/games/cats_punchlist.md`:

- **P1 — Pile-tap activations not yet wired by any card.** The
  `make_pile_activated` helper exists and `CATS_KNOCK_OVER` is dispatched,
  but no card in the 60-card pool uses it. AI will not have activations
  to make until cards adopt the pattern.
- **P1 — Sneaky reveal half-wired.** Gary's commander emits
  `EventType.PKM_REVEAL` (wrong engine namespace) instead of a
  `CATS_REVEAL`. The reveal-info is captured but not consumed by the AI
  decision path yet.
- **P2 — Mood-vs-Mood stacking is order-dependent.** When both players
  play Moods in the same trick, whichever interceptor registered later
  wins (currently the Counter-pounce side by accident, which matches the
  design intent — but the engine doesn't enforce it explicitly).
- **P2 — 3+ player support claimed but never tested.** Engine loops
  `state.players` but trick payload assumes 2-player slots
  (`pounce_card` / `counter_card`).
- **Note**: Many games end at round 6 instead of round 9 because both
  hands empty (5-card hand × 2 plays/round = depletion in 3 rounds, then
  one refill cycle from a 30-card deck minus 6 played gives ~12 left,
  another 3 rounds, etc.). The "9 rounds" target is a CAP, not a target.

## Card-balance notes (from deckbuilding pass)

- **Bartholomew** (Sleek 10, draw-2 on Nap entry) is the strongest single
  card in the pool. Naptime decks should keep, every other deck should
  prefer to deny.
- **Princess Mayhem** is structurally weak as commander — the +1/snack
  bonus pays off only when piloted with discipline; the heuristic AI does
  not yet know to stop at 4 snack cards.
- **Trinkets** are tempo investments: playing one consumes the round's
  card without contributing to the trick (so you lose that trick). Only
  play Trinkets when winning the trick is unaffordable anyway (junk hand)
  OR the Trinket's score boost > 1 trick win in expected points.

## Session takeaways

<!-- Most-recent entry first; written by the ultra-agent at game end. -->
