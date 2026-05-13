# Boros (BRV) — Deck Plan

Pilot: LLM ultra-loop iter 1. Seat p1 (606d5c4d). Going first. Opp: Dimir LZ engine.

## Deck composition

- **Aurelia line**: 4 Aurelet (Basic, 60 HP, Tiny Smite R 20 + draw if bench),
  3 Aurelin (Stage 1, 90 HP, Practice Lance RC 50 +10 if bench),
  2 Aurelia, the Warleader ex (Stage 2, 280 HP, Legion's Charge RC 80 + Battalion Mark RRFF 0 — each
  benched Pokemon does 10 to opp Active).
- **Feather line**: 3 Feathlet (70 HP, Halo Bash RC 30), 2 Feather, the Redeemed (Stage 1, 120 HP, Redeemed
  Recursion RC 80 + recover top Trainer from discard to hand).
- **Standalone**: 2 Boros Reckoner (Basic, 80 HP, Counter-Punch RC 60 + 2 counters to self).
- **Guild trainers**: 2 Sunhome Stadium (heal 10 to both actives + ping opp if bench ≥ 2),
  2 Gideon Blackblade (Supporter — 20 to opp Active + heal 20 to own),
  3 Boros Cluestone (Item — tutor 1 R energy + 1 F energy),
  2 Boros Blend Energy (special energy R or F).
- **Standard trainer suite**: 22 cards (Rare Candy, Iono refresh, Switch, etc. via `standard_trainer_suite()`).
- **Energy**: 8 Fire + 5 Fighting.

## Win condition

Stage 2 Aurelia ex (turn 4-5) with bench ≥ 3 Pokemon. Battalion Mark places +30-40 damage counters
per turn (1 counter per bench Pokemon). With Sunhome Stadium pinging +10 when bench ≥ 2, and Gideon
Blackblade adding +20 burst, we 2-shot opp's actives. Late game we also have Razia/Wojek/Aurelin
Practice Lance for value damage. 6 prizes through 1 ex KO (2) + standard KOs.

## Target turn

T4-T5 to have Aurelia ex active. Path:
- T1: Bench 2 Basics (Aurelet + maybe Feathlet/Reckoner), attach R energy to Aurelet active.
- T2: Bench more (target 3-4), evolve Aurelet → Aurelin, attach R energy.
- T3: Evolve to Aurelia ex via Rare Candy OR keep Aurelin attacker; attach F. Boros Cluestone for ramp.
- T4: Battalion Mark with 3+ bench = 30+ counters, plus Sunhome ping = potential 40+/turn.
- T5: Finish with Legion's Charge (80) + accumulated counters; close prize race.

## Key cards / priorities

1. **Aurelet → Aurelin → Aurelia ex** — primary win condition. Aurelia ex is 2-prize but tank-heavy
   (280 HP) and pressures opp Stage 2 KO range.
2. **Boros Cluestone** — early energy tutor; play first turn possible to get RR/FF in hand.
3. **Sunhome Stadium** — drop T2-3 to start chip pings AND heal our active.
4. **Gideon Blackblade** — Supporter; +20 dmg/turn AND heal 20. Use over Iono unless we need refresh.
5. **Bench wide** — aim for 4-5 by T3. Feathlet/Aurelet/Reckoner all viable utility benchers.
6. **Pivot threat**: Boros Reckoner Counter-Punch is fine secondary attacker (60 dmg, RC cost).

## Mulligan policy

- Keep with ≥ 2 Basics in hand. Ideal: Aurelet + something else (Feathlet, Reckoner, Tajic).
- Mulligan only on zero Basics (forced).
- Bonus: Boros Cluestone + Aurelet line = great keep (energy tutor + evolution).

## Threats from Dimir LZ

- **Mirko Vosk's Lost Recall** — they mill our top 4 (Lost Zone 1). Don't depend on a single Aurelia
  ex copy; we run 2. If they LR our second Aurelia, fall back on Feather + Aurelin chip plan.
- **Jarad ex Necrosurge** — scales with their LZ count (2 counters per Pokemon in their LZ). At
  5 LZ Pokemon = 100 damage. Our 280 HP Aurelia ex eats that twice. Use Sanguine Sacrament if needed.
- **Niv-Mizzet's Quandary** — forces switch + redistributes energy. Plan: keep at least 1 backup
  attacker on bench with energy attached so a forced switch doesn't waste a turn.
- **Cremate** — opp self-mills; not our problem directly.

## Counterplay timing

- If opp commits to Stage 2 Jarad, race with Battalion Mark (we ignore their LZ count; we deal
  fixed bench-scaling damage that they can't outscale on a single turn).
- Don't over-extend bench beyond 4-5; Niv-Mizzet can punish.

## Notes during play

Will update with observed iter 1 results.

---

## Iteration log

### iter 1 (2026-05-13) — **LOST** (10 turns, opp `Shadowstrike` KO into empty bench)

**Outcome**: 5-5 prizes at game end. Lost because Feathlet was Active
with empty bench on T10 — opp's Lazav ex KO'd it → `no_pokemon` loss.

**Decisive variance event**: drew **0 Aurelet across 10 turns** from a
4-copy starter. Without Aurelet, the entire Aurelia line (3 Aurelin +
2 Aurelia ex + Rare Candy) was dead cards. Mulligan-able opener but
the opener already had Feathlet as a Basic so no forced mulligan.

**Deck construction findings — fix recommended**:

- **Aurelet count is too low** for a 9-Basic deck with 5 dud Basics
  (Feathlet x3 + Reckoner x2). Recommended bump: **4 → 5 or 6
  Aurelet** in `make_boros_deck` in
  `src/cards/pokemon/beyond/ravnica/boros.py`. This is a
  deck-construction fix, NOT a bias preset fix.
- Consider adding **Tajic, Legion's Edge** (already in card pool) as
  3rd Basic family — 70 HP Fighting basic with status-clear.
- Consider adding **Sanguine Sacrament** (mentioned in strategy doc
  but not in current deck) to dodge KO on damaged Stage 1s.

**What worked**:

- **Boss's Orders + Redeemed Recursion** (T7) — pulled Dimir Cutpurse
  (80 HP) Active, KO'd with 80 dmg, took 1 prize. Bypassed Lazav ex
  tank entirely. **This is documented as the surgical sub-strategy
  going forward.**
- **Super Rod** recovery kept the Aurelia line theoretically alive
  even after Professor's Research burns.
- **Feather, the Redeemed** confirmed as legitimate secondary win
  condition (120 HP, RC 80 + Trainer recursion).

**What didn't**:

- **Ultra Ball T1 cost 2 Fighting Energy** — same engine-wide pitfall
  Pilot A also hit. Hand had no junk so the heuristic discarded
  energy. 4-turn delay before any 2-energy attacker.
- **Professor's Research played twice** — first time recovered, second
  time burned the 2nd Aurelia ex + 2 Aurelin lines. Should hold the
  2nd P-Research unless bench is secured.
- **Sunhome Stadium mutual-heal** favored Dimir (Lazav ex was tank;
  Boros couldn't KO past 280 HP). Down-weight Sunhome in this matchup.
- **Lazav ex Shadowstrike**: no answer in deck. No Pithing Drone, no
  energy denial.

**Updated mulligan**: HARD-MULLIGAN any opener that has Feathlet/
Reckoner as the only Basic AND no Aurelet. Even if it's legal, the
Aurelia line is dead without Aurelet draws.

**Updated decision priorities** (delta from pre-game):

1. (NEW) **Skip Ultra Ball T1 unless hand has ≥2 energy AND target
   in deck** — discard cost eats your curve.
2. (NEW) **Boss's Orders + Redeemed Recursion is a documented kill
   line** for tanky-Active matchups. Always look for the 1-prize
   bench KO when opp has a 280 HP ex on Active.
3. (NEW) **Sunhome Stadium** — play only if my Active is damaged AND
   opp Active is sub-50% HP. Otherwise mutual heal helps opp's tank.
4. Bench priority: 4-5 by T3 unchanged.
5. Aurelia line: target T4-T5 unchanged but mulligan policy is now
   stricter.

### iter 2 (2026-05-13) — **WON** (22 turns, Gideon Blackblade KO into empty bench → `no_pokemon`)

**Outcome**: Boros 2 prizes left, Dimir 3 prizes left. Won by playing **Gideon Blackblade** (Supporter, 20 dmg + 20 heal, doesn't end turn) on opp's lone Mirklet at 10 HP — KO triggered `no_pokemon` (Dimir empty bench). Full reversal of iter 1: this time the empty-bench rule worked FOR Boros instead of against it.

**Symmetric finding (cross-iter)**: Aurelet starvation persisted **even with 3 Nest Balls played**. All 3 Nest Balls fetched non-Aurelet (2 Reckoner + 1 Feathlet) because `_choose_ai_nest_ball_target` (sv_starter.py:71) uses HP-based scoring, and Reckoner 80 HP > Feathlet 70 HP > Aurelet 60 HP. **The Nest Ball heuristic compounds the 4-copy starvation** — even when tutoring is available, the wrong target gets pulled. This is an engine-level mis-targeting, not a coach-fixable issue. Pilot was saved at T18 by panic-Pro Research that drew 2 Aurelet + Aurelin.

Cross-team mirror: iter 2 Dimir hit the SAME structural starvation with Lazlet (0 drawn in 22 turns from 4 copies). Both BRV guild builders need to dig harder for the key evolver.

**New cards confirmed kill-line**:

- **Gideon Blackblade as a finisher**: 20 dmg + 20 self-heal, doesn't end turn (Supporter). Perfect when opp Active ≤ 20 HP. Effectively a kill spell + free Potion. **Save for finishing low-HP opp Actives**, not chip damage. Win condition T22.
- **Boros Blend Energy + retreat combo**: when stuck with wrong-energy Pokemon, retreating to a fresh Basic + Boros Blend Energy attaching R+F is a 1-turn ramp recovery. Saved Pilot T18 when Feathlet was wrong-typed for the kill.
- **Pro Research as panic button**: -EV swing in normal play, but at T18 with bench=0 and Feathlet at 10 HP, drawing 2 Aurelet from Pro Research saved the game from imminent `no_pokemon` loss. Lesson: dead hand + risk of empty-bench = play it; live hand = preserve.

**What didn't / pitfalls**:

- **Nest Ball mis-targeting** — 3-of-3 fetched Reckoner/Feathlet over Aurelet. Engine patch needed (heuristic should detect Stage 1/2 in hand and prioritize the matching Basic). Documented as encoder-task.
- **Ultra Ball penalty too soft** — T18 Ultra Ball with bench=0 still pulled Aurelia ex over Aurelet. Math: 280 HP - 200 penalty + 100 ex + 50 stage-2 = 230 > Aurelet 60. The `need_basic_for_bench` -200 penalty needs a bump (encoder task).
- **Confused Reckoner Counter-Punch** — flipped tails, self-KO'd. ~50% chance to lose attacker for free. Should retreat instead of attacking when confused.
- **Aurelin orphans** — 2 Aurelin sat dead in hand for 10+ turns waiting on Aurelet. Reinforces 4-copy starvation finding.

**Updated decision priorities** (delta from iter 1):

1. (NEW) **Gideon Blackblade is a kill-spell finisher**, not chip. Hold for opp Active ≤ 20 HP (always KOs, doesn't end turn).
2. (NEW) **Boros Blend Energy + retreat** is a 1-turn ramp combo. Use when wrong-typed Active is the only attacker — retreat to fresh Basic, Blend gives R+F immediately, attack same turn.
3. (NEW) **Pro Research is a panic button at empty-bench risk**. Otherwise preserve. Iter 1 said "burn risk", iter 2 said "saved game" — both true; depends on hand state.
4. (NEW) **Don't gamble Confused Reckoner Counter-Punch** — retreat, don't attack. 50% self-KO is worse than burning 2 energy on retreat.
5. (NEW) **Drive Dimir to empty bench via bench-snipe (Battalion Mark) + Boss's Orders combo**. Then Gideon Blackblade or any 20+ dmg attack closes via `no_pokemon`. This is now the documented win line vs Dimir.

### iter 3 (2026-05-13) — **LOST** (22 turns, prize race 0-6 — Dimir Lazav ex Veiled Whisper chain)

**Outcome**: Boros took 0 prizes; Dimir took all 6 via repeated Veiled Whisper KOs by T22. Series final: **Dimir 2-1**.

**Decisive variance event**: drew BOTH Aurelia ex copies (T5 + T6) but lost both to repeated Pro Research churn (T7 + T9 panic-discards). Aurelin (Stage 1) also pitched. **Aurelia line was dead the entire game** — Ultra Ball T17 pulled Feather, the Redeemed instead (heuristic still mis-targets). Mirror failure of iter 1's 0-Aurelet game but via DIFFERENT mechanism (draw fine; Pro Research burned the line).

**New pitfall — Lazav ex 280 HP wall is un-KO-able vs Boros**:

- Boros's max single-attack damage: 80 (Feather Redeemed Redeemed Recursion).
- Lazav ex HP: 280. KO requires 3+ unanswered turns.
- Add one Potion heal (30 HP): Boros mathematically cannot KO Lazav ex inside the prize race window.
- Boros has no Darkness type → no weakness exploit.
- **Verdict**: Lazav ex on Active is a hard-to-beat finish for Boros. The win line vs Dimir requires either (a) preventing Lazav ex from getting to Active, OR (b) winning the prize race via Battalion Mark + bench-snipe BEFORE Lazav ex stabilizes (~T10-12). If Lazav ex hits Active with full HP, Boros likely loses.

**What worked (despite the loss)**:

- **Feather, the Redeemed T17 via Ultra Ball** — secondary win condition lived briefly, 120 HP tank chipped Lazav ex for 80. Without Feather, T17 was an instant loss.
- **Pro Research panic T7** — saved from immediate no_pokemon loss (bench=1, Feathlet at 10 HP). Drew bench refills.
- **Boros Blend Energy T1** — confirmed iter 2 finding: free R+F attach for Halo Bash T3. Best tempo card in deck.

**New engine bugs surfaced this game** (encoder/engine pass needed):

1. **Rare Candy no-op with no Stage 2 in hand** — T13 played Rare Candy after Pro Research discarded all Aurelia ex. Card consumed, no effect. Engine bug: legal_pokemon_actions should pre-check hand for matching Stage 2.
2. **Duplicate-name action labels misroute energy** — T15 attached Fire to wrong Feathlet (Active vs Bench, same display label). Engine should disambiguate.
3. **Pro Research DRAW count=7 inconsistent** — T21 first Pro Research drew 1 card; second drew 7. Possible DRAW event handler bug with count > 1.
4. **Ultra Ball silent fail** — T21 discarded 2 cards but added 0 Pokemon. Engine should auto-cancel or report.
5. **Gideon Blackblade end-turn contradiction** — iter 2 said "doesn't end turn"; iter 3 evidence shows next packet was opp's turn after both Gideon plays. Card text + engine behavior need to be reconciled.

**Updated decision priorities** (delta from iter 1+2):

1. (NEW) **Rare Candy is conditional, not auto-play**. Always inventory hand for the Stage 2 piece BEFORE playing. If discard contains the Stage 2 but hand doesn't, Super Rod first.
2. (NEW) **Pro Research consumes the Supporter slot — plan one turn ahead**. If you panic-PR to dig for Aurelet, you CANNOT also play Boss's Orders that turn. The kill line is delayed by one turn at best.
3. (NEW) **Lazav ex on Active is a 5+ turn problem**. Don't try to KO it head-on. Use Battalion Mark + bench-snipe to race the prize game OR Boss's Orders to grab benched 1-prize Pokemon. Boss's Orders is the surgical answer (iter 1 finding confirmed).
4. (NEW) **Aurelia ex draws are precious — protect the line from Pro Research**. If Aurelia ex is in hand and you don't have a way to evolve this turn, DO NOT play Pro Research (it'll pitch the win condition). Hold for Super Rod recovery.
