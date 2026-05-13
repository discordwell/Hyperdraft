# Pokemon TCG — Strategy Doc

This file is the persistent strategic memory for Pokemon TCG (Hyperdraft
implementation, focused on the Beyond Ravnica spice pack v1 cards).
A fresh Claude instance piloting the format reads this BEFORE every
game and consults it during play. Update it whenever a game reveals
a non-obvious truth — write down WHAT and WHY, not just WHAT.

The doc is paired with `src/ai/pokemon/biases.py` (`POKEMON_BIAS_PRESETS`)
— when you find a blind spot in the heuristic AI, patch both: write the
lesson here AND tighten the relevant preset.

---

## Format fundamentals

### Resources

- **Prizes**: 6 per player. Take prizes by KO'ing opponent's Pokemon.
  Whoever takes their last prize first wins. Standard KOs give 1 prize;
  ex Pokemon give 2.
- **Energy**: Manually attached, 1 per turn. Different attacks need
  different types — Fire R, Water W, Grass G, Lightning L, Psychic P,
  Fighting F, Darkness D, Metal M, Fairy Y, Colorless C.
- **Hand**: 7 starting cards. Mulligan if you have 0 Basic Pokemon
  (opponent draws a card per mulligan).
- **Deck**: 60 cards. Decking out (drawing from empty deck) loses the
  game.

### Per-turn limits

- 1 energy attachment per turn (except via specific cards).
- 1 Supporter per turn.
- 1 Stadium per turn (replaces existing).
- Multiple Items per turn.
- 1 retreat per turn (paying the active's retreat cost in energy).
- 1 evolution per Pokemon (cannot evolve same turn the Pokemon hits play).

### Type chart (weakness / resistance)

- **Fire R** > Grass G
- **Grass G** > Water W, Lightning L
- **Water W** > Fire R, Fighting F
- **Lightning L** > Water W
- **Psychic P** > Fighting F
- **Fighting F** > Lightning L, Darkness D, Metal M, Colorless C
- **Darkness D** > Psychic P
- **Metal M** > Grass G

Weakness multiplies damage 2×; resistance reduces by 30.

### Status conditions (mutually exclusive — Pokemon's "Special Condition")

- **Asleep**: can't attack/retreat; flip heads at end of turn to wake.
- **Burned**: 2 damage counters + flip; tails for 1 more counter.
- **Confused**: flip heads to attack (tails: 30 damage to self, attack fails).
- **Paralyzed**: can't attack/retreat for one turn.
- **Poisoned**: 1 damage counter between turns; persists.

---

## BRV archetypes

Six bias presets ship with the BRV set, each tuned for a distinct
archetype. The LLM coach updates per-card multipliers per iteration.

### LZ Engine (`lz_engine`)

**Core cards**: Mirklet → Mirko Vosk · Jarlet → Jaradite → Jarad ex ·
Cremate · Sanguine Sacrament.

**Win condition**: Build a stack of own Pokemon in the Lost Zone (5+),
then KO opp Active with Jarad ex's Necrosurge (places 2 damage counters
per Pokemon in own LZ).

**Play pattern**:
1. T1–2: Bench Mirklet + Jarlet. Attach Psychic / Darkness energy to
   establish either threat.
2. T2–3: Play Cremate to send 2-3 Pokemon/Energy from hand to LZ. Each
   Cremate = +20 to +40 future Necrosurge damage.
3. T3–4: Evolve to Jaradite, then Jarad ex (via Rare Candy if available).
   Or evolve Mirklet → Mirko Vosk for the mid-game Lost Recall (mill +
   LZ feed combined).
4. T5+: Necrosurge with 4-5 LZ Pokemon = 80+40 to 80+100 damage. Wins
   prize trades.

**Key decision point**: When to commit to evolution. Stage 2 Jarad ex
locks in the archetype but costs a turn; sometimes a Mirko Vosk attack
on T4 with 2-3 LZ Pokemon is enough.

**Counter-archetypes**: Energy denial slows the {P}{D}{C} cost of
Necrosurge significantly. Hand disruption (Dimir Interrogation) can
yank our evolution line.

### Bench Swarm (`bench_swarm`)

**Core cards**: Borblet → Borborgrew → Aurelia ex · Sanguine Sacrament
· Pithing Drone.

**Win condition**: Fill bench with 3-5 Pokemon. Aurelia ex's Battalion
Mark places 1 damage counter per Benched Pokemon on opp Active — at
3 bench Pokemon, that's 30 chip per turn (low-cost {R}{F}). Mounts
pressure into Stage 2 KO range.

**Play pattern**:
1. T1: Bench 2 Basics. Pithing Drone onto Active.
2. T2: Bench 2 more Basics (4 total bench). Evolve where possible.
3. T3+: Aurelia ex hits play. Battalion Mark ticks 4 damage counters /
   turn into opp Active. Sanguine Sacrament saves any of these from KO
   by sacrificing a bench dud.

**Key decision point**: Don't over-commit bench (Niv-Mizzet's Quandary
or Boss-Orders KO us if 1-prize Pokemon stack up).

**Counter-archetypes**: AOE damage (rare in BRV but exists). Lost Zone
attacks that exile bench targets.

### Control / Disrupt (`control_disrupt`)

**Core cards**: Dimir Interrogation · Jace, Memory Adept · Niv-Mizzet's
Quandary · Tezzy's Test · Tox-Pawpsule.

**Win condition**: Strip opp hand and prevent opp from setting up.
Win on prize trades with Lazav ex (Stage 2 Dimir) or Obzedat ex
(Stage 2 Orzhov).

**Play pattern**:
1. T1–2: Build slowly; emphasize Trainer Items.
2. T3+: Dimir Interrogation (yank Pokemon from opp hand) and Jace's
   Mental Triage (discard opp Items) each turn. Tezzy's Test as a
   modal flex.
3. T5+: Niv-Mizzet's Quandary forces opp to switch a setup attacker
   off Active, then redistributes their energy elsewhere.

**Key decision point**: Tezzy's Test mode selection. Default heuristic:
mode 3 (disrupt) if opp hand has Trainer cards, mode 2 (tutor) if our
deck has Items we want, mode 1 (draw 3) otherwise.

**Counter-archetypes**: Aggro burn that ignores hand pressure and races
on damage.

### Energy Denial (`energy_denial`)

**Core cards**: Voidmage Apprentice · Pithing Drone · Niv-Mizzet's
Quandary · Tox-Pawpsule.

**Win condition**: Lock opp out of attacks by stripping their energy
attachments. While they fail to attack, we chip with cheap attackers
and close on prize math.

**Play pattern**:
1. T1: Voidmage to Active. Single energy attach.
2. T2+: Voidmage's Energy Drain (1 energy cost) discards 1 of opp's
   Active energy each turn. Cumulative — by T4, opp Active is bare.
3. Pithing Drone on a sticky Pokemon — when we lose it, opp loses all
   energy from the attacker.

**Key decision point**: When to retreat Voidmage out. If opp gets a
single hit through, the attack is lost; we want to retreat to bench
before opp KOs to preserve the engine.

**Counter-archetypes**: Decks with lots of attach cards (Iono refresh)
or Stage 2 evolution that doesn't care about energy stripping (rare).

### Aggro Burn (`aggro_burn`)

**Core cards**: Whichever Basic / Stage 1 attacker is fastest in deck.

**Win condition**: KO the first 4 opp Pokemon before opp sets up. Don't
bother with utility Trainers.

**Play pattern**: Aggressive Active commitment, ignore bench beyond
a single backup. Race prize math.

### Balanced (`balanced`)

Vanilla heuristic AI with no per-card multipliers. Used as control
matchup for new strategies and as the default when no archetype is
specified.

---

## Spice-card decision points

### Tezzy's Test (modal Supporter)

Choose 1 of 3 modes:

- **Mode 0 — Draw 3**: Default when hand is small (≤ 3 cards).
- **Mode 1 — Tutor Item**: Choose when we have evolution lines that
  want an Item (e.g., Rare Candy missing). Also strong when our deck
  is fat (probability of finding the right Item).
- **Mode 2 — Disrupt Trainer**: Opp reveals hand; pick a Trainer for
  them to shuffle back. Strong when opp hand has 4+ cards likely to
  include a Trainer.

**Heuristic AI default**: Mode 2 if opp has Trainers in hand, Mode 1 if
deck has Items, Mode 0 otherwise. LLM pilots can override per game state.

### Obzedat, Ghost Council ex — Spectral Decree (modal attack)

Choose 1 of 2 modes:

- **Mode A — KO Bench**: KO an opp Benched Pokemon with ≤ 30 HP. Strong
  late game when opp has low-HP setup Pokemon waiting on evolution.
- **Mode B — Prize Tax**: Opp takes 1 fewer Prize from their next KO
  against us. Strong when we're at risk of losing an ex (turning a
  2-prize loss into 1).

**Heuristic AI default**: Mode A if opp bench has a KO-eligible target,
else Mode B.

### Mirko Vosk's Lost Recall (build-around attack)

Look at top 4 of opp's deck, put 1 in Lost Zone, shuffle the rest back.
The "1 in LZ" choice is critical:

- **Prefer**: Opp's only copy of their Stage 2 evolution (high-impact
  removal).
- **Then**: Opp's last Energy of a specific type (if they're committed
  to a typed attacker).
- **Then**: Opp's Supporter (limits their future plays).
- **Default**: First Pokemon seen.

### Negate the Negation (build-around Item)

Useless unless opp has Tools attached. Hold in hand and don't play
until opp commits a Tool. When played:

- Discard all Tools on the chosen opp Pokemon.
- Per Tool discarded: opp reveals top card of deck; that card → Lost Zone.

**Heuristic AI**: Bias −100 when opp has no Tool. Once a Tool appears,
bias +40 plus +25 for each additional Tool.

---

## Common pitfalls

### Over-discarding into Cremate

Cremate moves up to 3 cards to the Lost Zone. The temptation is to
empty the hand for maximum LZ ramp. **Don't** — keep at least:

- 1 evolution piece if a Basic in play is waiting on it.
- 1 Supporter (we get 1/turn).
- 1 backup attacker (in case Active is KO'd).

### Wrong-time energy attachment

In LZ engine: Mirko Vosk's Lost Recall costs {P}{D}{C}. Splash the
energy types correctly — typically 8 Psychic + 5 Darkness. Don't
attach Darkness when Psychic is the bottleneck for Mirko's evolution
turn.

### Prize-trading into ex losses

ex Pokemon give 2 prizes when KO'd. Don't promote an ex Active when
opp can KO it next turn unless the trade is favorable (we KO their ex
back). Sanguine Sacrament can dodge an ex KO by sacrificing the ex to
Lost Zone (no prizes given — Pokemon in LZ don't count for prize math).

### Tezzy's Test wasted

Default Mode 0 (Draw 3) is the LOWEST EV mode in most game states.
Always check first:
1. Is opp's hand revealed-Trainer-rich? → Mode 2.
2. Is our deck fat AND we want a specific Item? → Mode 1.
3. Otherwise → Mode 0.

### Pithing Drone on the wrong attacker

The Tool only fires when its holder is KO'd by an attack. Putting it
on a bench Pokemon that won't get KO'd anytime soon wastes the slot.
Default: attach to Active when it's an ex (high-value target).

---

## Update log

This section is appended by LLM coaches after each iteration of
`/ultra-loop`. Each entry: date, matchup, key finding, preset patch
applied.

### 2026-05-13 — iter 1 (double mode): Dimir LZ (p2, won) vs Boros Bench (p1, lost) — 10 turns, `no_pokemon`

**Matchup summary**: Dimir LZ took 2 prizes and finished Boros via the empty-bench KO rule on T10. Boros bricked: drew 0 Aurelet in 10 turns despite running 4 copies, leaving the Aurelia ex line completely dead. Both pilots converged on Ultra Ball being harmful in early-game energy-thin hands.

**Confirmed findings**:

- **Ultra Ball energy-discard pitfall (engine-wide)**: Both pilots saw Ultra Ball discard 2 Energy from a hand that had no other discard-eligible "junk". The auto-discard heuristic scores Energy near zero (cheapest to ditch), so when hand = (UltraBall + 2 Energy + targets), it wipes the energy curve. Costs ~2-3 turns of attacker setup. **Recommendation**: pilots should hold Ultra Ball until ≥1 Pokemon is benched AND ≥2 Energy are attached or in-hand-non-discardable.
- **Empty-bench loss is real**: Lazav ex 280 HP feels invulnerable, but if it is your only Pokemon and goes down, you lose by `no_pokemon`. This applies symmetrically — Boros lost via the same path (Feathlet was its only remaining Pokemon on T10). **Maintain ≥1 bench Basic at ALL times.**
- **Dimir Blend Energy is load-bearing on T2**: free P+D attach effectively skips an attach turn, enabling Disguise Drip on T2 going-second. Combined with Lazlet's chip+mill, this is a faster clock than its sticker price suggests.
- **Shadowstrike + Mimic Cape mill stacks into a real secondary clock**: 2x Shadowstrike (mill 4 each) + 3x Mimic Cape (mill 1 each) = 11 cards. Against slow decks, deckout is a backup win condition.

**Disagreements / contested**:

- **Sunhome Stadium evaluation**: Pilot B wants it down-weighted (mutual heal favors a tanky opp Active); the doc currently treats it as neutral. Confirmed contested — apply mild down-weight pending iter 2 evidence in a non-Dimir-tank matchup.

### Counterplay vs Boros bench swarm (Dimir perspective)

Boros bench-snipes hit Dimir's smallest Basics first (Mirklet, Voidmage). Defend by:

1. Keep Lazav ex on Active to absorb chip — its 280 HP is essentially un-KO-able by Boros 1-shot.
2. Keep replaceable benchers (Mirklet, Voidmage) as the bench-snipe absorbers; don't put your only spare evolution piece there.
3. If Aurelia ex hits the field, **prioritize Shadowstrike to KO before her Battalion Mark scales** (each bench Pokemon = +10 dmg/turn; at bench 4-5 she does 40-50/turn passively while Boros builds).
4. Dimir Interrogation is a +EV play vs Boros only when their hand ≥ 4 (Boros runs lots of Pokemon density). At hand ≤ 3 it often whiffs and just cycles a card for them.

### Counterplay vs Dimir LZ (Boros perspective)

Dimir's win condition is Stage 2 Lazav ex with {P}{P}{D}{D}. Counter by:

1. **Race the energy curve, not the HP wall**: Lazav ex needs 4 energy attached. Boros's Battalion Mark only needs 2R+2F and scales by bench (every turn ≥30 chip when bench ≥3). If bench ≥3 by T3, you out-pace Dimir's setup.
2. **Boss's Orders is the surgical counter** to Dimir's tanky Active strategy: pull a 1-prize bench Pokemon (Mirklet, Voidmage, Cutpurse) to Active and KO it. Bypasses Lazav ex entirely and bleeds the prize race.
3. **Don't waste Ultra Ball T1** — see pitfall section. Boros NEEDS its 2-color energy curve intact for T2 Practice Lance / T4 Battalion Mark.

### Aurelet starvation (Boros deck construction note)

Boros currently runs 4 Aurelet for a line with 3 Aurelin + 2 Aurelia ex. Drawing 0 Aurelet in 10 turns happened in iter 1 — variance, but the deck is more fragile than the Aurelin count implies. **Deck construction fix recommended**: bump Aurelet to 5-6, or add a second non-discard Pokemon tutor (Nest Ball variant). This is a deck-list fix, not a bias preset fix.

### Spice-card decision points (additions)

- **Ultra Ball when hand has ≤2 non-Pokemon non-Energy discard targets**: SKIP. Auto-discard will hit Energy first and crater the curve. Hold until you have junk to feed it.
- **Dimir Interrogation when opp hand has no Pokemon**: net effect is +1 to opp hand (you reveal, they draw 1, you remove nothing). Skip unless their hand is ≥ 4 AND their archetype is Pokemon-heavy.

### 2026-05-13 — iter 2 (double mode): Dimir LZ (p1, lost) vs Boros Bench (p2, won) — 22 turns, `no_pokemon`

**Matchup summary**: Boros took the empty-bench win on T22, mirror of iter 1 (where Dimir won via the same path). Dimir bricked: drew 0 Lazlet across 22 turns despite running 4 copies, leaving the Lazav ex Stage 2 line completely dead. Boros's Aurelet starvation persisted (only 1 Aurelet hit field by T18 via panic-Pro Research) — `_choose_ai_nest_ball_target` HP-based fallback grabbed Reckoner/Feathlet 3 of 3 times. Game ended Boros 2 prizes / Dimir 3 prizes; series now **1-1**.

**Confirmed STRUCTURAL findings** (now reproduced 2-of-2 games):

- **Symmetric `no_pokemon` empty-bench loss is a FORMAT-LEVEL issue, not archetype-specific**. Iter 1: Boros lost this way. Iter 2: Dimir lost this way. Both decks attrition down to 1 Active + 0 bench, then a single attack (or even a 20-dmg Supporter — see Gideon below) closes. This is a real, repeating endgame pattern in BRV. **Defensive policy: maintain ≥1 bench Pokemon at all costs**. **Offensive policy: drive opp to 0 bench AND keep opp Active sub-30 HP — even a Supporter can finish.** Engine team should evaluate whether a 1-turn grace / mulligan-on-no_pokemon would soften the binary.
- **Symmetric 4-copy starvation is a guild-builder bug**. Boros's 4 Aurelet (iter 1: 0 drawn) and Dimir's 4 Lazlet (iter 2: 0 drawn) are the SAME structural deck-construction problem in BRV's two flagship guilds. Both Stage 2 lines (Aurelia ex / Lazav ex) require the corresponding S0 Basic to be on field before Rare Candy or normal evolution can fire. With ~5-6 Basics in a 60-card deck and ~4 of those being the key evolver, drawing 0 in 20+ turns happens. **Guild-builder fix recommended**: bump key evolver Basic to 5-6 in BOTH `make_dimir_deck` (Lazlet 4→5/6) AND `make_boros_deck` (Aurelet 4→5/6).

**New cards seen this iter**:

- **Gideon Blackblade as a finisher**: "20 dmg + 20 heal, doesn't end turn" Supporter. Confirmed kill line on T22 (KO'd Mirklet at 10 HP from outside attack flow). This is a 2-for-1: kill opp + heal own, AND it's a Supporter so the rest of the turn remains usable. **Save for opp Active ≤ 20 HP** — strictly better than attacking when the attack is overkill. Bench-swarm decks should prioritize when sub-30 finishing damage is needed.
- **Reckoner Counter-Punch + Confusion = self-KO gambling**: when Reckoner is confused, attacking is a coin-flip self-KO (tails: 30 self-damage, attack fails). At low HP, retreat instead. **Don't gamble Reckoner on a Confused turn**.
- **Duskmantle Stadium clutch tech**: when opp's top discard from the mill effect is a Trainer, opp Active gets Confused. Iter 2 used this as a hail-mary — opp's Reckoner hit confusion-tails and self-KO'd. ~30-40% expected value (probability of Trainer on top), but in clutch situations vs aggro it's a free attack-cancel. Risk: if MY top is a Trainer, I get Confused. Time it when own next-turn attack isn't critical.

**Disagreements / contested**:

- **Empty-bench rule binarity**: the `no_pokemon` instant-loss has now decided 2-of-2 BRV games. Either the engine team softens it (1-turn grace / forced mulligan on empty bench), or the BRV decks need a structural Basic-density floor. Coach scope is the deck-density side; engine scope is the rule.
- **Iono down-weight in Dimir**: Pilot A flagged Iono as a coin-flip in low-Basic decks (iter 2 played it, drew 0 Basics from 4 cards). Coach skipped this bias edit because (a) iter 1 didn't see Iono play, single data point, and (b) Iono valuation depends heavily on hand state — a static bias is a poor instrument. Watch in iter 3.
- **Pro Research valuation in Boros**: iter 1 said over-cautious; iter 2 said it saved the game at T18. Coach skipped re-bumping (was 0.8× from earlier? — actually not in current preset). Watch in iter 3.

### Counterplay vs symmetric empty-bench (BRV-format)

When opp has 1 Active + 0 bench, ALL of these become viable finishers (in addition to direct attacks):

1. **Gideon Blackblade** (Boros): 20 dmg Supporter. KOs any Active ≤ 20 HP without ending turn. Guaranteed 2-prize swing (1 prize + game).
2. **Tox-Pawpsule** poison stack: scaling damage counters at end-of-turn cycle KO low-HP Actives without you swinging.
3. **Duskmantle Stadium mill** (Dimir): random Confusion gambit; ~30-40% chance opp self-KOs via Counter-Punch tails or whiffs an attack you can answer.
4. **Bench-snipe Tools** (Boros Aurelia ex Battalion Mark): scaling chip ignores HP wall, lands counters on the lone Active each turn.

### Counterplay against being driven to empty bench

When you reach 1 Active + 0 bench (as the defender), priority order:

1. **Tutor a Basic this turn**: Nest Ball → any Basic; Pro Research → hand reset (high-variance but sometimes game-saving — see iter 2 Boros T18 save).
2. **Don't attack if it leaves Active KO-able next turn**: even a 1-prize trade is fine; an empty-bench follow-up is not.
3. **Status-stall**: Tox-Pawpsule poisons opp Active for chip while you stall. Voidmage Energy Drain delays opp's KO swing.
4. **NEVER play a Stadium that triggers your own discard / mill while at 1 Active**: Duskmantle on yourself is a self-Confusion risk.
5. **Don't play Rare Candy speculatively** (iter 3): if the Stage 2 is in discard but hand has only Stage 1 + Basic, Rare Candy is a no-op. Engine still lists it legal but consumes for zero effect. Use Super Rod first to recover the Stage 2.

### 2026-05-13 — iter 3 (double mode): Dimir LZ (p2, won) vs Boros Bench (p1, lost) — 22 turns, prize race 6-0

**Matchup summary**: Dimir took all 6 prizes via repeated Lazav ex Veiled Whisper KOs by T22. Boros drew both Aurelia ex but lost both to repeated Pro Research churn, leaving the Aurelia line dead for the entire game. Series final: **Dimir 2-1**.

**Series verdict**: Dimir 2-1, but the matchup is closer than the score suggests. Iter 2 Boros won by 22T when Dimir's Stage 2 line bricked; iter 3 Dimir won by 22T when Boros's Stage 2 line bricked. Whoever resolves the 4-copy starvation problem first dominates that game. The 1 outlier in 3 games (iter 1's 10-turn no_pokemon exploit) has been heuristic-patched, leaving 2 long-form attrition games where deck construction dictates the outcome.

**Confirmed STRUCTURAL findings (now 3-of-3 games)**:

- **4-copy evolver starvation is the format's central problem**. Iter 1 Boros 0 Aurelet (10T); iter 2 Dimir 0 Lazlet (22T); iter 3 Boros drew both Aurelia ex but both Pro-Research-discarded → Aurelia line dead anyway. Three games, three independent failure modes of the same structural issue: ~4-6 Basics + 4-copy key evolver + Pro Research churn = Stage 2 line dies ~33-50% of games. Bias tuning is a stop-gap; deck construction is the actual fix.
- **Heuristic Nest Ball mis-targets evolution-line basics**. Iter 2 + iter 3 both saw Nest Ball fetch Reckoner/Feathlet over Aurelet despite Aurelin in hand. The `_choose_ai_nest_ball_target` scorer ranks by HP, not evolution-line awareness. Encoder task — pre-check hand for matching Stage 1/2 before HP scoring.

**New STRATEGIC findings (iter 3 only)**:

- **Veiled Whisper > Shadowstrike for most BRV KOs**. Lazav ex's 2-energy {P}{D} attack (80 dmg) one-shots BRV's typical 60-90 HP basics and Stage 1s. Shadowstrike's 4-energy {P}{P}{D}{D} (200 dmg + mill 4) is overkill against Boros's 120 HP max Stage 1 (Feather Redeemed) and only matters vs 280 HP Stage 2 ex. The 2-energy tempo gap is huge. **Strategic rule for Dimir piloting**: default to Veiled Whisper; only build to Shadowstrike for the Stage 2 ex KO or mill-out finish.
- **Tox-Pawpsule between-turn poison is decisive**. T10 poisoned Reckoner died to poison ticks (50→20→0) over 2 turns without Dimir attacking. Forced Boros into a no-Switch retreat-or-die position. Passive damage on opp blocker while you press tempo elsewhere. **Bias-bump from 1.2× to 1.4×** (post-iter-2 evidence + iter 3 game-winning play).
- **Lazav ex 280 HP + no Boros Darkness type = un-KO-able with one Potion**. Boros's max single-attack damage (Feather Redeemed 80) needs 3+ unanswered turns to KO Lazav ex; Potion 30-heal once stretches the wall to effectively infinite. **Open question: is this an archetype-balance problem (Boros lacks a Darkness-weakness exploiter) or is it intended that Stage 2 ex are durable walls?** Worth raising with engine team if the matchup is a designed counter.

**Open question (variance vs structural)**:

Is Boros bench swarm structurally weaker than Dimir LZ, or are 3 games not enough to call it? Score is Dimir 2-1, but both Boros wins+losses were driven by the SAME 4-copy starvation variance source. If the starvation is fixed (deck-list bump Aurelet/Lazlet 4→5/6 + Nest Ball heuristic patch), the matchup may settle to closer-to-even. **Recommend: do not buff/nerf either bias preset based on the 2-1 series alone; fix deck construction first, then re-measure.**

**Engine bugs surfaced this iter (for a future fix pass)**:

1. **Rare Candy no-Stage-2 gate**: legal even when no matching Stage 2 in hand; consumes the card for zero effect. Should be gated out of legal actions.
2. **Duplicate-name action labels**: 2 Feathlets in play → "Attach Fire to Feathlet" appears twice with no disambiguation. T15 iter 3 misrouted energy from Active to Bench. Engine should suffix or label by position.
3. **Pro Research DRAW count=7 inconsistent**: iter 3 T21 first Pro Research drew only 1 card; second drew 7. Possible event-resolution bug in DRAW handler with count > 1.
4. **Ultra Ball silent fail**: T21 discarded 2 cards but added no Pokemon to hand (search either failed or unreported). Should auto-cancel or report failure.
5. **Gideon Blackblade end-turn contradiction**: iter 2 finding ("doesn't end turn") contradicts iter 3 evidence (next packet showed opponent's turn). Card text should be clarified and one of the iter findings retracted.

**Did NOT change decision logic**: per task spec — encoder owns that pass.

**Recommended next-pass work (NOT applied this iter)**:

- **Deck construction**: bump Aurelet 4→5/6 in `make_boros_deck` and Lazlet 4→5/6 in `make_dimir_deck` (`src/cards/pokemon/beyond/ravnica/`). The variance source is the deck-list, not the AI.
- **Engine fixes (5 bugs)**: Rare Candy gate, duplicate-name disambiguation, Pro Research DRAW resolution, Ultra Ball search-failure feedback, Gideon Blackblade turn-end clarification.
- **Heuristic encoder pass**: Nest Ball evolution-line awareness, Ultra Ball Basic-priority when bench=0, Aurelia ex attack-mode selection by bench count.

### 2026-05-13 — v2-iter1 (single mode v2): Boros bench-swarm vs Dimir LZ — Boros WON 6-0 in 31 turns

**Matchup summary**: Boros (Pilot B) took all 6 prizes via Lazav ex KO on T29 (+2 prizes via ex) and final Lazlet KO on T31. Game-defining sequence: confirmed the Gideon Blackblade + Feather Redeemed Recursion 100-dmg/turn combo melts Lazav ex's 280 HP in 4 turns even with one Potion heal.

**RETRACTION 1 — Iter 3 was WRONG: Gideon Blackblade does NOT end turn**:

- **Iter 2 was right; iter 3 was misread.** Pilot B confirmed via 2 separate plays this game (T19, T29) — both turns continued with attack actions after Gideon resolved (Gideon 20 + heal 20, then Feather Redeemed Recursion 80, then turn ended via End Turn action).
- **Trace path**: T19 packet sequence was `Gideon Blackblade` → `Redeemed Recursion (Feather)` → `End Turn` → opp turn. T29 same sequence. Iter 3's "next packet was opp's turn" likely missed the intervening attack action in the transcript.
- **Strategic update**: Gideon is a **free 20-dmg + 20-heal Supporter EVERY turn** it's available, NOT a one-shot finisher. Top-tier Boros tempo card — play alongside an attack on every available turn. Bias preset bumped 1.8 → 2.0.

**RETRACTION 2 — Iter 3 was MISLEADING: Lazav ex 280 HP wall is NOT un-KO-able**:

- **Iter 3 claim**: "Lazav ex un-KO-able with one Potion (Boros lacks Darkness exploiter)."
- **Reality (this game)**: Boros's Gideon (20) + Feather Redeemed Recursion (80) = **100 damage/turn cumulative**. Lazav ex 280 HP + 1 Potion 30 heal = 310 dmg threshold. Boros exceeds it in **3.5 turns** (4 turn cycles to be safe). Pilot B confirmed in T29 — KO'd Lazav ex 280 HP cleanly in 4 turns of stacked Gideon+Feather even though Dimir got one Veiled Whisper through.
- **Strategic update**: Boros has a real, repeatable kill line vs Lazav ex. **Don't surrender to Lazav ex** when the Gideon+Feather combo is online. Conversely, Dimir's "tank Active forever" plan needs reinforcement (Sanguine Sacrament, Tox-Pawpsule chip, Niv-Mizzet's Quandary forced switch) — bare Lazav ex with one Potion is NOT enough.

**NEW finding — Aurelia ex is OPTIONAL not REQUIRED for bench-swarm**:

- Pilot B drew **0/2 Aurelia ex** in 31 turns and still WON. The win came from Aurelin (90 HP / 60 dmg with bench bonus) + Feather, the Redeemed (120 HP / 80 dmg + Trainer recursion) + Gideon Blackblade chip-and-heal.
- Doc previously framed Aurelia ex as the win condition ("T4-T5 Aurelia ex active"). **Update**: the deck's win condition is **any of {Aurelin, Feather Redeemed, Aurelia ex} chained with Gideon+Cluestone**. Stage 2 ex is upside, not a requirement. Deck is more resilient than previously documented.
- **Implication for bias presets**: do NOT bump Aurelia ex weighting further (already 1.8×, demonstrably unnecessary). Bench_swarm preset should reward the Stage 1 attackers as primary, not the Stage 2 alone.

**NEW engine bug — Evolve action labels lack `(Active)/(Bench N)` disambiguation**:

- Iter 3 fix only patched `Attach` action labels. Evolve actions still show "Evolve Lazlet into Lazander" with no zone marker when 2+ Lazlets are in play. Pilot A reported T20 promotion mistake (bare Lazlet promoted instead of Lazav line) traceable to this. Pilot B reported T3 evolved Bench Aurelet instead of Active Aurelet.
- **Fix scope**: extend the `Attach` `(Active)/(Bench N)` suffix logic in `src/engine/pokemon_legal_actions.py` (around line 207-212) to `PKM_EVOLVE` action labels.

**NEW coordination issue — pilot-vs-pilot race condition**:

- v2-loop runs two LLM pilots (one per seat). Pilot A reported only **13/51 Dimir-side actions** were executed by pilot-A's code path; the remaining 38 went through pilot-B's (or the default heuristic fallback's) action pipe before pilot-A's packet-fetch finished.
- Cause: whichever pilot polls + applies first wins each action slot. The race window (~3-5 seconds) is shorter than pilot-A's typical decision latency.
- **Effect**: pilot-A's strategy doc became functionally unreachable. The mid-game "promote Lazav ex bare" mistake was made by pilot-B-as-Dimir-fallback, not by pilot-A executing the strategy doc.
- **Fix scope**: parent orchestrator (in `.claude/skills/ultra-loop/`) should serialize per-seat pilot calls or use a per-seat lock. Until fixed, single-mode (one LLM pilot) is the only reliable path; double-mode results are race-poisoned.

**Confirmed findings (3-of-3+ carryover)**:
- Aurelet 4→6 deck fix WORKED (Pilot B drew 3 Aurelet vs iter 1's 0).
- Lazlet 4→6 deck fix WORKED (Pilot A drew 3 Lazlet vs iter 2's 0).
- Pro Research panic button (T9 saved Boros).
- Sunhome Stadium correctly NOT played (3-of-3-of-3).
- Ultra Ball correctly NOT played (3-of-3-of-3).
- Nest Ball still mis-targets Reckoner over Aurelet (4-of-4 — encoder fix still pending).

### 2026-05-13 — v2-iter2 (single mode v2): Dimir LZ vs Boros bench-swarm — Dimir WON 6-0 in 17 turns

**Series state**: **1-1** after iter 2 (v2-iter1 Boros won 31T; v2-iter2 Dimir won 17T).

**Matchup summary**: Dimir Pilot A executed cleanly — no pilot-coordination collision this game. Lazav ex assembled by T5 via Lazlet → Lazander → Ultra-Ball-fetch Lazav ex on Lazander (energy inheritance kept the Stage 2 active-ready). Veiled Whisper KO chain handled 4 of 6 prizes; Shadowstrike 1-shot Feather Redeemed for the final Stage 1 KO. Boros bricked on Fighting energy delivery — Feather Redeemed evolved T10 with 0 energy and never attacked.

**Verified — v2-iter1 encoder fixes WORKING**:
- **Bench-stacking guard** (-25 per existing copy in `_score_evolution`): Dimir avoided piling Lazanders on bench (only 1 Lazander promoted, others held as Lazlets in hand).
- **Bare-promotion penalty** (-35 / -50 ex in `_score_attacker`): Dimir never promoted Lazav ex bare; the only Lazav ex promotion was the T5 same-turn evolve from a Lazander already carrying 3P+1D.
- **Evolve-action disambiguation**: no T20-style mis-promote reported this game.
- **Net effect**: Dimir played more efficiently than v2-iter1 (4 KOs in 8 turns vs v2-iter1's 1 KO in 18 turns). Pilot B explicitly flagged Dimir as a stronger opponent post-fixes.

**Refined finding — Aurelia-ex-optional is CONDITIONAL**:
- v2-iter1 said "Pilot B won 0/2 Aurelia ex drawn → Aurelia is optional".
- v2-iter2 says: that finding only holds when Feather + Gideon kill combo can fire. When Boros energy-bricks (couldn't keep Fighting in deck for Aurelin/Feather), the deck has **no apex attacker at all**. Aurelia ex is the backup apex when Feather Redeemed can't be powered. Update: Aurelia ex is **optional iff the Feather+Gideon combo is online** — otherwise it's the backup win condition.

**Boros energy bottleneck (NEW)**:
- Cluestone tutored Fighting twice (4 of 5 Fighting basics consumed); Boros Blend delivered only 1/2 energy at T8 because Fighting was depleted in deck. Aurelet/Aurelin/Feather all need R+C; Aurelia ex's Bombardment needs Fighting; Reckoner needs Fighting. With 5 Fighting in deck and 3 Pokemon needing it, the ratio is too thin.
- **Recommended deck-list fix**: bump Fire copies in `make_boros_deck` (currently 8 Fire / 5 Fighting). Either bring Fire to 10 or Fighting up to 7 — three R-needing Pokemon (Aurelet, Aurelin, Feather) all compete for a small Fire pool while Cluestone splits the deck's energy further. Coach scope flags; deck author owns the change.

**NEW engine bugs**:
1. **Switch consumed but did NOT swap Active↔Bench** (T4 Boros): hand -1, discard +1, but Aurelet stayed Active. Pilot fell back to Retreat. Reproducible.
2. **Potion consumed but did NOT heal** (T6 Boros): hand -1, discard +1, but Aurelet's 4 damage counters stayed. Possible disambiguation (no target chosen?).
3. **Mill events emit `PKM_DISCARD_ENERGY` instead of `PKM_DISCARD_DECK_CARD` / `PKM_MILL`** (T13 Dimir Shadowstrike): mill-4 events were mis-categorized in the action log. Cosmetic but very confusing for pilots reading transcripts.
4. **Shadowstrike apply silently no-op'd on first try** (T13 Dimir): valid packet_hash + selected_action_id returned but no PKM_KNOCKOUT in events; second apply with same action ID worked. Race condition or stale-state suspect.
5. **Packet perspective glitch on opp turn**: Dimir's Lazav (still my Pokemon) appeared with 0 energies in the Boros-perspective packet; reverted to true 5-energy state on next Dimir-perspective packet. Cosmetic rendering inconsistency.

**Confirmed findings (carryover)**:
- Lazav ex 280 HP wall held for 17 turns this game — but ONLY because Boros never assembled the Gideon+Feather combo (energy bricked). v2-iter1's "wall is NOT un-KO-able" stands as a principle (when combo fires); this game it sat unchallenged.
- Aurelet 4→6 deck fix WORKED (Boros drew 5+ Aurelets across the game).
- Lazlet 4→6 deck fix WORKED (Dimir drew Lazlet and built Lazav line by T5).
- Sunhome NEVER played by Boros (4-of-4 — guidance held).
- Tox-Pawpsule KO chain: T9 Aurelin (90 HP) was KO'd by Veiled Whisper 80 + 1 poison counter = exactly 90. Single tick mattered.

**Engine bugs queued for next fix pass** (not coach scope):
- Switch / Potion item application bugs (Bug 6, 7).
- Mill event-name mis-categorization (Bug 8).
- Shadowstrike race / stale-state (Bug 9).
- Packet perspective rendering (Bug 10).
