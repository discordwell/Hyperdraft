# Dimir LZ Engine — Match Plan (ultraloop iter1)

## Win Condition

Primary: **Lazav, Dimir Mastermind ex** (Stage 2, 280 HP) — `Shadowstrike`
{P}{P}{D}{D} for 200 dmg + mill 4. Backed by **Mirko Vosk, Mind Drinker**
(Stage 1) `Lost Recall` {P}{D}{C} for 70 + put 1 of opp's top 4 into Lost
Zone (resource denial / LZ-feed combined).

NOTE: Prompt mentions Jarad ex / Cremate / Jarlet — those aren't in the
actual `brv:dimir` deck (it ships Lazav + Mirko + mill-style trainers).
Strategy is **mill + LZ-feed + energy denial** rather than the Jarad
Necrosurge plan. Adapt to deck shipped.

## Target Tempo

- T1-2: Bench Mirklet + Lazlet (both Basics, both Psychic). Attach P.
- T2-3: Evolve to Lazander (Stage 1, 90 HP, `Mimic Cape` for 50 + mill 1).
- T3-4: Evolve Mirklet → Mirko Vosk OR Lazander → Lazav ex. Attach D.
- T4-5: Mirko `Lost Recall` once energy ready (P+D+C). First real attack.
- T5+: Lazav ex on field; swing for 80-200 while burying opp's deck.

## Key Cards

- **Lazlet / Lazander / Lazav ex** — main attacker chain.
- **Mirklet / Mirko Vosk** — secondary chain w/ LZ-feed and mill.
- **Voidmage Apprentice** — 1-cost {P} discard-energy denial. Free in matchup.
- **Dimir Cluestone** — search {P}+{D} to hand. Energy fixer.
- **Dimir Blend Energy** — attach {P}+{D} from deck directly. Tempo spike.
- **Duskmantle, House of Shadow** — passive mill + Confused on Trainer mill.
- **Etrata, the Silencer** — Supporter; opp bottoms 3, riders on type seen.
- **Dimir Interrogation** — yank a Pokemon from opp hand, slow their setup.
- **Tox-Pawpsule** — Poison opp Active, scaling damage counters.

## Mulligan Policy

- Keep with: ≥1 Basic Pokemon AND (≥1 evolution piece OR ≥1 energy fixer).
- Hard keep: any hand with Lazlet/Mirklet + Lazander/Mirko Vosk + energy.

## Decision Priorities

1. Bench Basics aggressively turn 1-2 (Mirklet, Lazlet, Voidmage, Cutpurse).
2. Always attach energy. P first (cheaper attacks), D after evolutions.
3. Trainer Items: Cluestone/Blend early; Interrogation when opp hand ≥ 3.
4. Tox-Pawpsule: only when opp Active has 0 status (Poison sticks for KO chip).
5. Duskmantle Stadium: play after own Active is bare-board (don't self-confuse).
6. Evolution priority: Lazander > Mirko Vosk (Lazander cheaper to attack with).
7. Don't promote ex before {P}{P}{D}{D} ready — Lazav ex KO'd = 2 prizes.

## Counterplay (vs Boros bench swarm)

- Their bench-counter scaling makes my smaller bench safer than wide.
- Voidmage Apprentice discards their Active energy → slows their evolution.
- Lost Recall can yank their Aurelia ex from deck top 4.
- Tox-Pawpsule punishes their full bench (more poisoned targets = bigger chip).

---

## Iteration log

### iter 1 (2026-05-13) — **WON** (10 turns, `no_pokemon`)

**Deck-contents discovery**: pre-game hypothesis assumed Jarad ex / Cremate (the
`lz_engine` preset's nominal target). The actual `brv:dimir` deck ships
**Lazav ex / Lazander / Lazlet** as the win line plus Mirko Vosk as
secondary. Strategy is **Stage 2 control-tank + mill** via Lazav ex's
Shadowstrike (200 dmg + mill 4 at {P}{P}{D}{D}), not Necrosurge LZ-ramp.

**Updated win condition**: Lazav ex on Active by T6 with 4 energy
({P}{P}{D}{D}). Shadowstrike 1-shots any Boros threat (Aurelia ex 280
HP weakness would be P; Feather 120 dies easy). The mill payload is a
secondary clock — combined with Mimic Cape pings, opp deck shrinks ~1
card per round.

**Updated key cards**:

- **Lazlet / Lazander / Lazav ex** — primary chain. Lazav ex is the
  S2 win condition.
- **Dimir Blend Energy** — T2 P+D attach. Highest-tempo card in deck.
  Effectively a free attach.
- **Mirko Vosk / Mirklet** — secondary chain. Mirko's Lost Recall is
  fine ancillary but Lazav's Shadowstrike wins faster.
- **Dimir Cutpurse / Voidmage Apprentice** — bench fodder, sized to
  survive bench-snipes from Boros.
- **Mimic Cape / Shadowstrike** — mill payload. Don't depend on it but
  count it as a 2nd win path against slow decks.

**What worked**:

- T2 Dimir Blend Energy → Disguise Drip turn-1-of-attacks. Fastest
  clock the deck offers.
- Lazav ex 280 HP wall ate 4 turns of Boros chip for 10 dmg total.
- Shadowstrike T8 KO'd Feather Redeemed, took 1 prize, milled 4 cards.

**What didn't / pitfalls discovered**:

- **Ultra Ball discarded 2 Psychic energies on T2** (heuristic auto-pick
  rated them as discardable; hand had no better targets). Cost a turn
  of attacker tempo. **Hold Ultra Ball until energy is on the field**.
- **Empty bench T2-T6**: only Lazav-line was active. If Boros had been
  faster to KO, Dimir would have lost via `no_pokemon`. **Always bench
  ≥1 Basic before going up the evolution chain.**
- **Ultra Ball heuristic auto-picked Lazav ex** (highest HP) when a
  Basic was needed for bench. Need a "prefer Basic when bench empty"
  decision hook (encoder task, not coach scope).
- **Dimir Interrogation whiff**: opp hand at 3, no Pokemon to yank →
  opp drew a card for free.

**Updated mulligan**: unchanged but emphasize "≥1 Basic + ≥1 evolution
piece OR ≥1 energy fixer". Dimir Blend Energy in opener is a hard keep.

**Updated decision priorities** (delta from pre-game):

1. (NEW) Bench Lazlet AND Mirklet by T2 even if you only attach to one.
   Prevents `no_pokemon` loss while evolving up.
2. Energy attach unchanged: P first, D after evolutions.
3. Ultra Ball: DEPRIORITIZE in early-game. Wait until ≥1 attacker has
   energy attached so the discard cost doesn't crater your curve.
4. Lazav ex on Active by T6 with 4 energy is the kill window.

### iter 2 (2026-05-13) — **LOST** (22 turns, opp Aurelin Practice Lance KO into empty bench → `no_pokemon`)

**Outcome**: 3-3 prizes at end-of-board. Lost because Mirklet was Active with empty bench on T22 — Aurelin's Practice Lance 60 → KO → `no_pokemon`. Pilot took 2 prizes total (Feathlet T3, Reckoner T14 indirectly via Confused-tails self-KO).

**Decisive variance event**: drew **0 Lazlet across 22 turns** from a 4-copy starter — exact mirror of iter 1's Boros 0-Aurelet game. The Lazav ex Stage 2 line was completely dead the entire game; Pilot fell back on Mirklet/Cutpurse chip + Mirko Vosk wall.

**Symmetric finding (cross-iter)**: BRV's two flagship guild builders both ship 4 copies of the key Stage 0 evolver against 3+2 Stage 1+ex chains. With ~5-6 total Basics in 60 cards, drawing 0 of 4 over 20+ turns happens. Same problem in both decks. **Deck construction fix recommended for `make_dimir_deck`**: Lazlet 4 → 5 or 6, mirroring the Boros fix.

**What worked**:

- **Nest Ball T1** — avoided iter-1 empty-bench start. Got Mirklet to bench T1. Direct iter-1 lesson application.
- **Dimir Blend Energy T1** — confirmed iter-1 finding: free P+D attach was the highest-tempo card. Cutpurse online for Pickpocket on T3.
- **Mirko Vosk retreat T5** — traded damaged Cutpurse for Mirko's 120 HP wall. Bought 2 turns of survival.
- **Duskmantle Stadium clutch T13** — opp's top discard from mill was a Trainer → opp Reckoner Confused → confusion-tails self-KO on T14. Single best play of the game; saved 2-3 turns.
- **Pickpocket as engine** — Dimir Cutpurse {D}{C} 30 dmg per turn was the engine while waiting on the dead Lazav line. Got 2 prizes total.

**What didn't / pitfalls**:

- **Lazlet starvation** — Lazav line dead from turn 1 to T22. Same structural problem Boros had with Aurelet in iter 1.
- **Bench-drain spiral** — once Mirko Vosk died T6, Pilot went 5+ turns with 0-1 Basics on field. Ran out of Basics by T21 (Cutpurse, Mirklet, Voidmage all KO'd or in discard, Lazlet never drawn).
- **Iono backfired T11** — coin-flip refresh in low-Basic deck drew 4 cards, 0 Basics. Iono is variance-prone for Dimir; only play when hand is dead AND library is fresh.
- **Rare Candy was a dead card** — never had Lazlet + Lazav ex + Mirklet/Mirko-pair to fire it. Down-weight in this deck.
- **Voidmage Apprentice underused** — benched T7, never had P energy attached, KO'd as a chump. Should have prioritized P attachment to fire Energy Drain vs Boros's R/F curve.

**Updated decision priorities** (delta from iter 1):

1. (NEW) **Lazlet is Plan A** — if Lazlet shows up, prioritize Rare Candy + Lazav line. If it doesn't show up by T5, switch to **Plan B**: Mirklet → Mirko Vosk Lost Recall as the main attacker.
2. (NEW) **Plan C — Cutpurse + Voidmage chip**: when both Stage 2 lines are dead, the Pickpocket {D}{C} 30 + Energy Drain {P}{C} 20+disrupt loop is the fallback. Plays out over 8-10 turns.
3. (NEW) **Iono only when hand is dead AND library has ≥30 cards left**: low-Basic-density decks see Iono as a coin flip — don't blind it.
4. (NEW) **Hold Rare Candy until Lazlet is on field** — playing it without Lazlet in play is a dead card. Strictly conditional.
5. (NEW) **Duskmantle Stadium**: drop when own Active has damage AND opp Active has damage AND opp's likely top deck is a Trainer (high-trainer-density deck like Boros). Don't play when own next-turn attack is the kill — the self-Confusion risk is too high.

### iter 3 (2026-05-13) — **WON** (22 turns, prize race 6-0 via Lazav ex Veiled Whisper chain)

**Outcome**: Dimir took all 6 prizes by T22. Boros drew BOTH Aurelia ex but lost both to Pro Research churn → Aurelia line dead all game. Series final: **Dimir 2-1**.

**Decisive plays**:
- **T12 retreat-and-promote**: retreated chipped Cutpurse into freshly-evolved Lazav ex. Established the 280-HP wall on Active.
- **T12-T22 Veiled Whisper chain**: 5 KOs in 11 turns (Reckoner, Reckoner, Feathlet, Feather Redeemed, Aurelet). Only used Veiled Whisper, never Shadowstrike.
- **T10 Tox-Pawpsule on Reckoner**: poison ticks killed Reckoner without Dimir attacking (50→20 over 2 turns). Boros lacked Switch, forced retreat-or-die.

**New STRATEGIC findings**:

1. **Veiled Whisper > Shadowstrike in the Boros matchup**. Boros's max HP is 280 (Aurelia ex which never hit field) — outside that, everything dies to 80 damage. The 2-energy {P}{D} cost vs 4-energy {P}{P}{D}{D} is a 2-turn tempo gap. **Default attack rule: Veiled Whisper unless Stage 2 ex Active or mill-out finish needed.** Bias preset bumped 1.3→1.6.
2. **Tox-Pawpsule between-turn damage is decisive vs no-Switch decks**. Bias preset added at 1.4× (was implicit 1.0). Best vs Boros's deck which is light on Switch.
3. **Lazav ex 280 HP + no-Boros-Darkness-type = un-KO-able with one Potion heal**. The matchup may be structurally biased toward Dimir if Boros lacks a Darkness exploiter — open question for next pass.

**What didn't / pitfalls**:

- **Starting hand 0 Lazlet** — exact mirror of iter 2's Boros problem. Even with Lazlet bias bumped to 1.6×, the 4-copy floor still allows whiff games. **Deck construction fix still pending**: Lazlet 4→5/6.
- **Pilot coordination race condition** — multiple times pilot-A's apply calls got rerouted to the OPPOSITE player's legal actions (engine bug: action IDs not packet-bound). Engine fix candidate.

**Updated decision priorities** (delta from iter 1+2):

1. (NEW) **Default Lazav ex attack: Veiled Whisper, not Shadowstrike**. Build 2 energy ({P}{D}) and KO 80-HP threats; only build to 4 energy for Aurelia ex KO or mill-out finish.
2. (NEW) **Tox-Pawpsule on opp blocker** when opp lacks Switch — chip damage while you press tempo elsewhere.
3. (NEW) **Retreat-and-promote pattern**: when chipped Active is about to die and a Stage 2 ex is bench-ready with energy, retreat (pay the cost) to swap a sub-50% HP Active for a fresh 280 HP wall. Worth the energy cost.

### v2-iter1 (2026-05-13) — **LOST** (31 turns, prize race 0-6 to Boros)

**Outcome**: Boros took all 6 prizes; Dimir got 2 (Aurelet T4, Feather Redeemed T28). Loss dominated by pilot-coordination race condition (pilot-A executed only 13/51 Dimir actions; pilot-B-fallback played the rest), so strategy validation is partial.

**Decisive variance event**: race condition fixed direction. Where the doc says "promote Lazav ex carefully", pilot-B-fallback promoted Lazav ex BARE (0 energy) on T22 because the legal_actions packet had the option. Three turns of attach-only followed before Lazav could fire — by then Boros's Gideon+Feather chain had already chipped Lazav 280→60.

**MAJOR retraction (cross-checked with Pilot B)**:
- **Iter 3's "Lazav ex un-KO-able with one Potion" was wrong**. Boros's Gideon (20) + Feather Redeemed Recursion (80) stacks 100 dmg/turn cumulatively. KOs 280 HP Lazav ex in 3.5 turns even with one Potion heal. **Update strategy doc**: Lazav ex is NOT an automatic 280-HP wall vs Boros — when Gideon+Feather is online, Dimir needs to either (a) prevent Feather Redeemed from evolving, (b) use Voidmage Energy Drain to disrupt Boros's Fire attachments, or (c) win the prize race elsewhere (Veiled Whisper KOs on Boros bench). Don't trust the wall.

**What worked**:
- Lazlet 4→6 deck fix WORKED (drew 3 Lazlet vs iter 2's 0). Lazav line was reliably available.
- T2 Disguise Drip + Dimir Blend Energy execution went per plan.
- T28 Veiled Whisper KO'd Feather Redeemed (40 HP from chip) — only Dimir KO of the second half.

**What didn't (mostly mis-execution from race condition)**:
- **Lazav ex promoted bare** on T22 (no energy) — required 3 turns of attach-only before fire. By then chip damage had pre-broken the wall.
- **Bench-Lazander pileup** — heuristic kept evolving Lazlet → Lazander on bench (3 Lazanders simultaneously) without promoting any. Energy attached to bench Lazander was wasted unless promoted. **New rule**: don't evolve a 2nd Lazander on bench while Active is non-Lazander.
- **Voidmage Apprentice Energy Drain never fired** — Voidmage benched but never had P attached for the disrupt attack. Vs Boros's Gideon+Feather Fire reliance, Energy Drain would have been disruptive.
- **Mirko Vosk never evolved** (Mirklet lingered on bench). Plan B (Lost Recall) never activated.

**Updated decision priorities (delta from iter 3)**:
1. (NEW) **Don't promote Lazav ex BARE**. Strategic rule: don't promote unless Lazav ex has ≥2 energy attached AND a kill target ≤80 HP within reach. Bare Lazav ex burns 3 turns of attach-only before relevant.
2. (NEW) **Don't pile up Lazanders on bench**. Don't evolve a 2nd Lazander while the 1st isn't promoted. Energy attached to bench Lazander is wasted; redirect to next-priority attacker (Voidmage P attach for Energy Drain).
3. (NEW) **Voidmage Energy Drain is the Boros disruption answer**. With Boros leaning on Fire-attaching to Feather Redeemed every turn, dropping a P on benched Voidmage and draining Boros's Active energy slows the 100-dmg/turn combo by ~1 turn each cycle.
4. (NEW) **Lazav ex 280 HP is NOT a Boros-proof wall**. When Boros has Gideon+Feather online, plan a parallel pressure path (Veiled Whisper bench-snipes via Boss's Orders if available, Tox-Pawpsule chip on opp Active). Do NOT assume Lazav ex sits on Active forever.

### v2-iter2 (2026-05-13) — **WON** (17 turns, prize race 6-0 via Veiled Whisper chain + Shadowstrike finisher)

**Outcome**: Dimir took all 6 prizes. KO order: T5 Feathlet (Veiled Whisper), T7 Aurelet (Veiled Whisper), T9 Aurelin (Veiled Whisper + Tox-Pawpsule poison tick = 90), T13 Feather Redeemed (Shadowstrike 200 + mill 4), T15 Aurelet 10HP (Veiled Whisper), T17 Aurelet 60HP (Veiled Whisper — game).

**Series state**: **1-1** going into v2-iter3.

**Key plays validating v2-iter1 priorities**:
- **T5 Lazav ex same-turn evolve via Lazander energy inheritance**: Lazander had 3P from earlier attaches + 1D from Dimir Blend (free). Ultra-Ball-fetched Lazav ex from deck → evolved Lazander → Lazav ex inherited 3P+1D → Veiled Whisper online same turn for KO of Feathlet. **Best-case Stage 2 ex deploy turn = T5** when energy is on Lazander pre-evolve. Add to plan: **prefer Ultra Ball when Lazander is on field with ≥2 energy AND Lazav ex is in deck** — same-turn evolve gives a free tempo turn.
- **T11 single-Lazlet bench (followed v2-iter1 priority 4)**: had 2 Lazlet in hand, benched only 1. Bench-stacking guard demonstrated by pilot.
- **Voidmage proactive bench T9 (followed priority 2)**: Voidmage came up via Pro Research → benched immediately as Boros answer. Never fired (Boros's Active energy too low to be worth disrupting), but the proactive bench prevented bench-empty exposure.

**What worked (carryover)**:
- Pro Research T9 was the inflection turn (drew Voidmage + 2 Lazlet + Tox-Pawpsule + Nest Ball — full board rebuild from a dead hand).
- Tox-Pawpsule + chip math: T9 Aurelin (90 HP) KO'd by Veiled Whisper 80 + 1 poison counter = exactly 90. **Single poison tick mattered** — Tox-Pawpsule's 1-counter scaling is decisive in tight HP windows.
- Shadowstrike used CORRECTLY this game (1× on T13 to 1-shot Feather Redeemed at 120 HP — fits the v2-iter1 rule "only commit Shadowstrike for actually-1-shotable Stage 2 ex's or 120+ HP non-ex").

**What didn't (mostly engine bugs)**:
- **Shadowstrike apply silently no-op'd on first try** (T13). Had to retry — second apply with same action_id worked. Engine bug; pilot lost ~30sec but no game impact.
- **Mill events mislabeled `PKM_DISCARD_ENERGY`** for Shadowstrike's mill-4. Pilot initially thought Lazav was discarding energy as cost. Cosmetic but confusing — engine fix needed.
- **Boros healed Feather Redeemed 40→120 between T11 and T13**. Pilot didn't have a clear action log to confirm cause. Possible Sanguine Sacrament (60) + Potion (30) chain — except v2-iter2 ALSO confirmed **Potion is broken** (consumed but no heal). So this heal source is genuinely unclear; likely engine bug.
- **Packet perspective glitch on opp turn**: Lazav showed 0 energies in Boros's packet view (still my Pokemon). Reverted to true 5-energy state on next Dimir-perspective packet. Cosmetic.

**Untested this game (no opportunity)**:
- Bare-promotion penalty: Lazav ex never went on bench, so promote-bare path didn't arise.
- Bench-stacking guard at heuristic level: pilot was hands-on the whole game; heuristic AI didn't get to make redundancy decisions.

**Updated decision priorities (delta from v2-iter1)**:
1. (NEW) **Ultra Ball + Stage-2-on-loaded-Stage-1 = same-turn ex deploy**: when a Lazander has ≥2 energy attached AND Lazav ex is in deck, Ultra Ball into Lazav ex + same-turn evolve = full energy carryover, attack-ready immediately. Best-case Stage 2 ex deploy turn = T5.
2. (NEW) **Veiled Whisper > Shadowstrike default re-confirmed**: 4-of-5 KOs this game were Veiled Whisper (2-energy 80 dmg). Shadowstrike only fires when target is 120+ HP non-ex AND can't be 2-shot by Veiled Whisper. Fits the v2-iter1 rule, expanded.
3. (NEW) **Pro Research T9-T10 inflection**: when starting hand goes dead (only Rare Candy + dead trainers, no Lazlet/Mirklet to advance), Pro Research is the panic refresh. Dimir's Plan B (Pro Research → rebuild) actually works here — drew exactly what was needed in iter2.
4. (NEW) **Tox-Pawpsule 1-counter scaling decisive**: when opp Active HP equals (Veiled Whisper 80 + 10), playing Tox-Pawpsule converts a survive into a KO. Look for this exact-90-HP edge case.
