# Cats — deckbuilding pass results

`/build-decks` invocation against the 4 starter decks. Subagent designed 4 new
candidates; 8-deck heuristic-AI tournament evaluated them (5 trials × 7 pairings
per deck × 10 games = 350 games per deck-pair).

## Final standings (5-trial means)

| Deck | Mean | Min | Max | Verdict |
|------|------|-----|-----|---------|
| **Naptime Denial** 🆕 | **65.7%** | 52.9 | 82.9 | dominant — likely needs a nerf |
| Naptime Tyrants | 59.4% | 52.9 | 67.1 | OK |
| **Snack Rush v3** 🆕 | **57.9%** | 48.6 | 67.1 | upgrade — beats original by +12.2 |
| Shadow Cats | 54.3% | 46.4 | 61.4 | OK |
| Couch Empire | 51.7% | 45.7 | 60.0 | OK |
| **Greg's Diary** 🆕 | **50.1%** | 44.3 | 57.1 | OK — hypothesis confirmed |
| Snack Rush | 45.7% | 35.0 | 58.6 | OK in 8-deck field (was 41.3% in 4-deck) |
| **Fluffinbottom Attention** 🆕 | **15.1%** | 5.7 | 19.3 | **hypothesis rejected** |

## Did any new deck beat ALL starters?

**Naptime Denial (65.7%)** beat 3 of 4 starters (Couch Empire, Snack Rush, Shadow Cats — not Naptime itself). Snack Rush v3 (57.9%) beat 3 of 4 starters too. No deck swept all 4, but the deckbuilder did improve the meta.

## Did any new deck fail to beat any starter?

**Fluffinbottom Attention.** Lost to all 7 other decks. The hypothesis ("max attention pile, win on Fluffinbottom's +5 bonus") is rejected — turns out:
- Without winning trick scoring, the player's attention bonus is irrelevant
- "All 10 Moods + low-value baits" can't win enough tricks under default Sleek rule
- The +5 from Lord Fluffinbottom only fires when your attention pile has the most cards, but you also need scoring-pile points to be competitive
- Net: single-vector deck in a multi-vector engine doesn't work

## Surprising matchups

1. **Naptime Denial vs Naptime Tyrants**: the deck specifically designed to deny Naptime didn't actually win the matchup — Naptime is its 1 loss out of 4 starters. Hidden-value Sneaky wins against Naptime less reliably than against value-based decks.
2. **Snack Rush v3 lost to Naptime Tyrants** specifically — v3 still loses to nap-stuffing. Bomb chain wins individual tricks but Naptime's pile economy scores higher.
3. **Greg's Diary at exactly 50.1%** — Greg's commander ability (swap a hand card with deck top, once per game) is genuinely worth ~1% of win rate. Tiny effect, fair design.

## Insights into card balance (flagged by deckbuilder)

1. **Madam Inkblot is the strongest single card.** 7 public + draw 2 on lose = positive in both win and lose paths. Appears in 3 of 8 decks.
2. **Maximum Carnage is second strongest.** 10 Scrappy, win = +1 score, lose = draw — no downside. Every deck wants her.
3. **The Whole Roast Chicken is the strongest snack.** V3 + draw 2 on entry.
4. **Sunbeam + Heated Blanket stack on Nap is degenerate.** +14 score from Trinkets alone when stacked. This is why Naptime Tyrants is reliably top-tier.
5. **The Dignified Sulk** has a card-text vs implementation mismatch: text says "fewer pile cards wins" but implementation uses `fewer_hand_wins`. Worth a P2 fix.
6. **Toby the Tubster / Tabitha / Gary Junior** are pure value-1/2 vanilla baits. Only useful under lowest-wins Moods.

## Suggested next iteration

1. **Nerf Naptime Denial.** 65.7% mean is too high.
2. **Keep Snack Rush v3** as canonical Snack archetype (+12.2% over original).
3. **Keep Greg's Diary.** Solid 50.1% — exactly where midrange should land.
4. **Drop Fluffinbottom Attention.** Rejected hypothesis. The Attention-pile bonus may need engine-side rework.
5. **Fix Sunbeam + Heated Blanket stack.**
6. **Fix Dignified Sulk text-vs-impl mismatch.**

## Reproducing

```bash
python scripts/play/cats_tournament.py --trials 5
```
