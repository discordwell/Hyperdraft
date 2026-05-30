# Fae but Mid — Constructed Strategy Guide

*Custom fae-tribal set (`src/cards/custom/fae_but_mid.py`, 412 cards). This doc
covers the first **designed** metagame for the set: six pinnacle archetype decks,
one per tribal pillar. Before these existed, the set was only ever played with
auto-greedy decklists, so most of its tribal payoffs never actually got cast.*

Decks are registered in `src/decks/standard_decks.py` (`STANDARD_DECKS`) under the
ids `fbm_faerie_tempo`, `fbm_elf_ramp`, `fbm_kithkin_wide`, `fbm_merfolk_tempo`,
`fbm_goblin_aggro`, `fbm_changeling_5c`. Tournament them with:

```bash
python scripts/play/deck_tournament.py \
  --decks faerie:standard:fbm_faerie_tempo elf:standard:fbm_elf_ramp \
          kithkin:standard:fbm_kithkin_wide merfolk:standard:fbm_merfolk_tempo \
          goblin:standard:fbm_goblin_aggro changeling:standard:fbm_changeling_5c \
  --games 5 --out logs/fbm_tournament.json --report logs/fbm_tournament_report.txt
```

## The Mana Base Constraint (read first)

The set ships **5 basics**, **5 shocklands** — Blood Crypt (BR), Hallowed Fountain
(WU), Overgrown Tomb (BG), Steam Vents (UR), Temple Garden (GW) — plus **Eclipsed
Realms** (tribal any-color) and **Evolving Wilds**. There are **no duals for the
enemy/off-allied pairs** (no WB, RW, RG, GU, GW... wait — GW *is* Temple Garden;
the missing pairs are WB, RW, RG, UB-as-dual, UG). This is the single biggest
deckbuilding constraint in the format:

- **UB Faeries**, **WU Merfolk**, **RB Goblins**, **GW Elves/Kithkin** all have a
  matching shock and live comfortably on two colors.
- **Five-color** decks *must* lean on any-color mana dorks (Bloom Tender, Great
  Forest Druid, Firdoch Core, Elvish Harbinger) + Eclipsed Realms + Evolving
  Wilds; the shocks only cover allied/one wedge pair each.

Every deck below respects this: two-color decks run their shock + Evolving Wilds;
the five-color deck runs the whole fixing suite and a higher land count.

## Deck-Construction Principles for this Set

1. **Pick a tribe with a *working* lord.** Several anthem creatures in the file are
   not wired (their static buff does nothing): **Thoughtweft Lieutenant**,
   **Warren Torchmaster**, plus **Nova Chaser / Thoughtseize / Springleaf Drum /
   Devoted Druid / Vendilion Clique** are bare. Build around the lords that *fire*:
   Imperious Perfect, Scion of Oona, Incandescent Soulstoke, High Perfect Morcant,
   Mistmeadow Council, Champion of the Clachan, Gaddock Teeg, Silvergill Mentor,
   and the hybrid Lieges.
2. **Token engines beat single bodies.** Bitterblossom, Spectral Procession,
   Hunting Triad, Clachan Festival, Kithkeeper, Grub, Imperious Perfect, and Oona
   all manufacture a board the lords then pump. The set rewards *width*.
3. **Sacrifice = reach.** Goblins (Sting-Slinger, Murderous Redcap, Hovel Hurler,
   Boggart Cursecrafter, Grub) turn a stalled board into direct damage; this is
   how the aggro decks beat a wall.
4. **Tap-matters is a real axis.** Merrow Commerce untaps your team every end
   step, so Merfolk "whenever this becomes tapped / {T}:" abilities fire on the
   opponent's turn too. Adept Watershaper makes tapped attackers indestructible.
5. **Changelings are universal keys.** A Changeling is *every* creature type, so a
   single shapeshifter turns on every tribal lord and every Aurora payoff at once
   — but it does **not** make off-color Lieges trigger (Lieges care about *color*,
   not type). Fix to all five colors, then the Lieges come online too.

---

## 1. FBM Faerie Tempo (UB) — `fbm_faerie_tempo`

**Hypothesis:** A small evasive clock + flash countermagic that *scales with your
own board* is the most resilient tempo deck in the format, because Spellstutter
Sprite and Mistbind Clique convert board presence into free counters.

**Key cards:** Bitterblossom, Spellstutter Sprite, Scion of Oona (lord + shroud),
Mistbind Clique (champion → tap all their lands = a Time Walk), Oona, Glen Elendra
Archmage, Cryptic Command, Sower of Temptation.

**Game plan:** Bitterblossom or a one-drop flyer on turn 1–2, hold up Spellstutter
for their first real spell, then deploy Scion of Oona to make the whole air force
bigger and shroud-protected. Mistbind Clique flashed in on their end step taps
their lands and swings the tempo race. Oona closes from the air and floods tokens.

**Mulligan:** Keep a hand with a 1–2 land + an early flyer *or* Bitterblossom, plus
at least one piece of interaction. Ship hands with no early play or all top-end.
You are the beatdown against control, the control against aggro — read the matchup.

## 2. FBM Elf Ramp (GW) — `fbm_elf_ramp`

**Hypothesis:** Elves have the best mana dorks *and* the best token engine, so they
can both ramp into a bomb and go wide — the lords (Imperious Perfect, High Perfect
Morcant, Wilt-Leaf Liege) make the swarm lethal either way.

**Key cards:** Heritage Druid + Bloom Tender + Elvish Harbinger (ramp/fix),
Imperious Perfect (lord + token factory), Rhys the Redeemed (token doubler),
Champions of the Perfect (draw engine bomb), Jagged-Scar Archers & Moon-Vigil
Adherents (P/T = your board), Hunting Triad / Gilt-Leaf Ambush (token spells).

**Game plan:** Dork on 1, lord/Harbinger on 2–3, then snowball: every Elf that
enters makes Imperious Perfect's tokens count for more, Jagged-Scar grows with the
team, and Rhys + a token spell doubles the board in one turn. Bloom Tender fixes
the white splash for Morcant and Rhys.

**Mulligan:** Want a dork or a two-drop lord + green source. A hand of only payoffs
with no acceleration is a mulligan; a hand of only dorks with no payoff is a keep
on the play, a marginal keep on the draw.

## 3. FBM Kithkin Go-Wide (GW) — `fbm_kithkin_wide`

**Hypothesis:** Kithkin have the lowest creature curve in the set plus multiple
token-makers and stacking anthems, so they out-flood every other aggro deck and
punish removal with go-wide redundancy.

**Key cards:** Kinsbaile Aspirant (grows per Kithkin), Kithkeeper / Brigid /
Cloudgoat Ranger / Spectral Procession / Clachan Festival (tokens), Mistmeadow
Council + Gaddock Teeg + Champion of the Clachan (anthems), Kinbinding (mass pump),
Catharsis (reset that refills *your* side with tokens).

**Game plan:** Curve out one-drops into token-makers, stack two anthems, alpha
strike. Against sweepers, Catharsis is a symmetric wipe that hands *you* the bigger
post-board (one token per creature destroyed) and Goldmeadow Nomad / Kinsbaile
Borderguard rebuild from the yard.

**Mulligan:** Keep almost any two-lander with multiple creatures — the deck floods
naturally. Ship no-land and no-creature hands only.

## 4. FBM Merfolk Tempo (WU) — `fbm_merfolk_tempo`

**Hypothesis:** Merrow Commerce breaks the symmetry of tap-abilities: you untap
every end step, so your tap-down Merfolk and `{T}` value engines fire on *both*
turns while the opponent stays locked down.

**Key cards:** Merrow Commerce (untap engine), Silvergill Adept + Merrow Skyswimmer
(card advantage), Wanderwine Distracter / Wanderbrine Trapper / Tributary Vaulter /
Champions of the Shoal (tap-down + stun), Sygg River Guide (protection), bounce
(Swat Away, Run Away Together) + Spell Snare.

**Game plan:** Establish a Merfolk or two, resolve Merrow Commerce, then tap their
blockers/attackers down every turn while chipping in the air and refilling with
Silvergill. Thoughtweft Gambit is a one-sided Falter that ends games.

**Mulligan:** Want an early Merfolk + Silvergill Adept or a tap-down piece, with WU
sources. The deck is light on raw power, so a slow no-pressure hand loses the
tempo race — mulligan it.

## 5. FBM Goblin Aggro (RB) — `fbm_goblin_aggro`

**Hypothesis:** Goblins have the lowest curve *and* the most "sacrifice for damage"
outlets, so they win the race outright and still have reach to push the last 6–8
through a clogged board.

**Key cards:** Sting-Slinger / Murderous Redcap / Hovel Hurler / Boggart
Cursecrafter (bodies that become burn), Grub Storied Matriarch (drains on every
Goblin death), Elder/Sourbread Auntie (tokens + pump), Wort the Raidmother
(conspire doubles your burn), Tarfire / Lash Out / Lasting Tarfire / Fodder Launch.

**Game plan:** One-drop, two-drop, attack; when the ground stalls, sacrifice the
team to the face. Murderous Redcap's persist means it does 4 across two lives;
Grub turns every chump into 2 life-swing. Wort makes your removal hit twice.

**Mulligan:** Keep aggressive two-landers with a one-drop and reach/burn. The deck
is resilient to flood (sac outlets convert excess), so lean toward keeping.

## 6. FBM Five-Tribe Changeling (WUBRG) — `fbm_changeling_5c`

**Hypothesis:** Changelings are every tribe at once, so they switch on *every* lord
and Aurora payoff simultaneously — a goodstuff pile where each threat is a
multi-tribe payoff, glued together by the format's deepest fixing.

**Key cards:** Mirror Entity / Chameleon Colossus / Omni-Changeling / Changeling
Wayfinder (universal bodies), the Lieges (Wilt-Leaf, Ashenmoor, Boartusk — each
pumps two colors), Reaper King (Scarecrow lord; Mirror Entity makes everything a
Scarecrow), Horde of Notions + Faewild Convocation + The Aurora Cycle (5-color
payoffs), Bloom Tender / Great Forest Druid / Firdoch Core (any-color ramp).

**Game plan:** Survive early on dorks and spot removal (Crib Swap, Unmake), fix to
five colors, then deploy undercosted lords that all see your changelings as their
tribe. Mirror Entity is the finisher — `{X}:` makes the whole board X/X with every
type, which also turns on Reaper King's destroy trigger en masse.

**Mulligan:** This deck's keeps are about *mana*. Want 3+ lands or 2 lands + a dork,
with access to two+ colors. A greedy no-fixing hand is an automatic mulligan even
with great spells.

---

## Winrate Matrix (round-robin, 5 games/pair)

*(filled in from `logs/fbm_tournament.json` after the tournament run)*

<!-- MATRIX_PLACEHOLDER -->

## Tier Read & Balance Notes

<!-- TIER_PLACEHOLDER -->

## Did previously-dead cards come alive?

<!-- DEADCARD_PLACEHOLDER -->
