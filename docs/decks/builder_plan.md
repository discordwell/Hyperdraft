# builder — Plan

## Composition summary

Economy-focused deck built around turn-bonus structures and Worker mining
compounding. Typical counts (vary by build):

- **Workers (~8-10)**: Steve's Helper, Alex's Scout, Villager Mason,
  Panda Forager, Steve's Helper variants. Multiple mining tribes — wood
  and stone yield. High Worker density (~20% of deck) is the deck's
  defining characteristic.
- **Turn-bonus structures (~8)**: Crafting Table (1W, +1W/turn), Furnace
  (2S, +1S/turn), Chest (2W, +1W/turn + draw), Redstone Engine
  (1S+2R, +1R/turn). Stack 2-3 for material dominance by T6-8.
- **Defensive structures (~4)**: Farm Plot, Village Watchtower (5HP,
  W2+S2), Water Bucket Moat (blocks mob lane attacks).
- **Blocks (~4)**: Oak Planks (1W, free-effective), Piston Gate.
  Grid-fortification to protect the economy.
- **Dedicated attackers (~6)**: Wolf Pack (3/2 base, +1/Worker — at 4
  Workers = 7 ATK), Iron Golem (3/4 I1+R1, the finisher), Village Guard
  (2/3, cheap early attacker), Village Reinforcements (sorcery: summon
  Village Guard).
- **Bed (2)**: Mandatory. Back row priority.
- **Utility (~4)**: Explore Map (1W, biome upgrades), Eyes of Ender
  (tutor), Strip Mine (1S → 1I+1R redstone ramp).

**Worker-to-attacker ratio**: heavily Worker-weighted early; dedicated
attackers (non-Workers) are the closer. This is not an aggro deck.

## Win condition

Economy dominance through Worker compounding and turn-bonus structures,
then a single concentrated column one-shot via Wolf Pack (6-7 ATK with
3-4 Workers) + Iron Golem (3 ATK) in one turn through a lightly-defended
column. **Builder does NOT win through attrition or chipping.** The
correct kill vector is accumulating enough ATK in one column to one-shot
through all blocking layers simultaneously.

**Expected lethal turn: T18-25 vs mirror.** Builder mirror is a structure
war — the game cannot reach a conclusion through normal chip damage.
Against aggro decks, lethal can arrive from the opponent side by T10-12
if the builder doesn't establish blocking structures fast enough.

## Target turns

- **T1-2**: Bed if in hand (back row, col 1 preferred). First Worker
  (Steve's Helper or Panda Forager). If Chest in hand, play Chest T1
  for turn-bonus draw. Mine Forest for wood day-bonus.
- **T3-5**: Deploy 2-3 turn-bonus structures (Crafting Table + Furnace
  priority). Second Worker. Begin biome upgrades (Explore Map).
  Strip Mine to unlock redstone — Iron Golem needs I1+R1 (verified).
- **T5-6**: If Strip Mine drawn, PLAY IT IMMEDIATELY (S1 → I1+R1). This
  single card enables Iron Golem (costs I1+R1 — verified). Deploy Iron
  Golem (3/4) as an early 3/4 attacker once Strip Mine yields the R1.
  Iron Golem on T5-6 with 2 Workers already down is the ideal curve.
- **T6-10**: Third Worker if not yet down (base mob value ~22, no big
  bonus). Farm Plot + Village Watchtower for grid fortification.
  Water Bucket Moat in col 0 and col 1 to block mob lane attacks.
  Wolf Pack goes down here — with 3 Workers = 6 ATK.
- **T10+**: Kill turn: Iron Golem + Wolf Pack + avatar attack in one Night
  turn. Sequence: (1) Wolf Pack clears the mid-row structure in target
  column; (2) avatar Iron Sword (4 ATK) attacks through the now-vacated
  column for direct face damage; (3) Iron Golem (3 ATK) attacks a
  second column. Combined 3+4+6+ ATK across 2 columns per Night.
- **No clean clock**: against another builder, there is no guaranteed
  lethal turn. The deck wins only when: (a) opponent misses Bed
  entirely, (b) you can one-shot through a thin column, or (c)
  opponent's econ never scaled and your Wolf Pack dominates by T20.

## Key cards

- **Wolf Pack** — primary attacker. 3/2 base, +1/Worker. With 4 Workers
  on board = 7 ATK. This is the deck's finisher in the late game.
  **Do NOT use Wolf Pack as a chump-blocker.** It's the deck's only
  scalable attacker; losing it to a trade collapses the win condition.
- **Iron Golem** — true finisher. 3/4 body, costs 1I+1R. Verified from
  `src/cards/minecraft/alpha.py`: `_cost(iron=1, redstone=1)`. Much cheaper
  than previously documented (doc had 3I+1R — that was wrong). A single
  Strip Mine (S1 → I1+R1) immediately enables Iron Golem deployment. This
  means Iron Golem is a T5 card with one Strip Mine, not a late-game T12+
  play. Priority: draw Strip Mine by T4-6 via Chest draw or Eyes of Ender,
  then deploy Iron Golem as an early 3/4 threat on T5-7.
- **Crafting Table / Chest / Furnace** — turn-bonus structures. Stack 2-3
  for material compounding. Priority: play all of these before deploying
  blockers or attackers if the board is safe.
- **Village Watchtower** — 5 HP defensive structure. High-value target
  for the AI in mirror (it rebuilds it too). In builder mirror, focus
  on not losing your own Watchtower rather than attacking theirs.
- **Explore Map** — mandatory compounding. 1W for permanent +1 biome
  yield. Play on every available turn while any biome is upgradable.
- **Bed** — mandatory. Back row. Two copies in deck means ~14% T1 chance;
  expect one by T4-5. Do not equip weapons before Bed is down.

## Mulligan policy

- **Auto-mull**: No Bed AND no Worker AND no turn-bonus structure. The
  deck cannot function without at least one of these in the opening.
- **Auto-keep**: Bed + Worker + any turn-bonus structure. This is the
  ideal opener — economy online immediately.
- **Auto-keep (good)**: 2× Worker OR Worker + Crafting Table + Chest.
  The economy starts compounding immediately.
- **Salvage (Worker-less)**: Bed + Chest + Explore Map is salvageable —
  the turn-bonus draw from Chest finds Workers while Explore Map ramps.
- **Avoid**: Hands heavy on Wolf Pack + Iron Golem without Workers or
  structures. Dedicated attackers are dead weight until the economy is online.

## Play priorities (order)

1. **Bed if in hand and wood available** (T1-2). Without a Bed, one
   bad combat step is instant loss. Back row, col 1 preferred.
2. **First Worker** — the deck's entire economy rests on Workers mining
   while the avatar does something else.
3. **Turn-bonus structures** — Crafting Table, Furnace, Chest. Stack until
   3 are down; after that, their EV drops vs deploying threats.
4. **Explore Map** (whenever a biome is upgradable). 1W for permanent
   ramp is the highest-EV action in the format.
5. **Additional Workers** (up to 3 on the field) — after 3, the base mob
   value (~22) competes against defensive and offensive options.
6. **Defensive structures / Blocks** — Village Watchtower, Water Bucket
   Moat. Fortify grid once the economy is stable; Water Moat in front
   row blocks mob lanes.
7. **Wolf Pack** once 3+ Workers are on board (≥6 ATK). This is the
   only attacker worth swinging with in mirror — don't swing earlier.
8. **Strip Mine / redstone** — unlock Iron Golem pathway. Cast before
   any 2-cost stone spend if redstone is not yet in hand.
9. **Iron Golem** on the kill turn. Confirm the target column is clear
   enough for a combined Wolf Pack + Iron Golem + avatar swing to
   one-shot all layers in a single turn.
10. **Do NOT mine with Workers on attack turns.** If Wolf Pack or Iron
    Golem is swinging this turn, keep all non-Worker mobs untapped.
    Mine ONLY with Workers; let the avatar attack.
11. **Do NOT clear a front structure unless you can capitalize immediately.**
    Clearing any y=2 structure when the AI has no Bed active triggers
    reactive Bed placement in that exact slot within 1 turn (iter-4
    confirmed). If you clear a front structure, you MUST have the ATK
    to kill or bypass the resulting Bed in the same Night turn — or you've
    handed the AI respawn protection in its weakest column. Prefer to
    concentrate ALL attacking power (Wolf Pack + Iron Golem + avatar)
    in one swing to bypass this trap rather than softening across turns.

## Anticipated weaknesses

- **Builder mirror draws run past T36 (effective cap ~T21-25 play-turns).**
  Avatar HP damage through normal combat is essentially impossible when both
  players field 3-deep columns. The game can only conclude via Bed-miss,
  burst finisher, or cap. Iter-1: 36-turn draw, 0 direct HP damage. Iter-2:
  ran to state T42 (T21 play-turns) with neither player near lethal despite
  a weapon-aggro line — only 6 direct HP dealt via a temporary col-2 window.

- **Workers cannot attack after mining.** Using Villager Mason or Panda
  Forager for mining taps them; they cannot attack that turn. Piloting
  error: declaring Workers as attackers after they've mined produces zero
  attacks and wastes the turn. Maintain a strict Worker-mines / attacker-
  attacks separation.

- **No reliable answer to the AI's contested-lane cycling.** The AI
  refills col 2 with Oak Planks (free) or Iron Door every turn after a
  clear. Chasing the same lane across 3+ turns is a losing investment.
  Solve by stacking ATK for a one-turn clear, not a grinding campaign.

- **Slow to deploy dedicated attackers.** Wolf Pack + Iron Golem are T10+
  plays. In the meantime, the AI's board pressure can reach avatar HP
  if Bed isn't down and Water Moats aren't placed. Vulnerable to
  surprise aggro by opponent during turns 4-9.

- **No flexible removal.** TNT Blast (if included) is the only hard
  answer to a big mob. Against AI running bosses (Warden 7/8, Wither
  4/4) the builder deck has no clean answer — race through econ to
  outpace HP pressure.

- **Econ lead doesn't translate to kill potential without Wolf Pack.**
  W17+S28+I17 by T30 (observed: iter-1) is useless without a plan
  to one-shot through blocking layers. Material overflow must convert
  into a board win; accumulate attackers, not more structures.

- **Clearing a front structure can BACKFIRE — reactive Bed placement.**
  Iter-4 confirmed: when the pilot cleared the AI's col 1 front structure
  (Cobblestone Wall, T32), the AI immediately placed a Bed in that exact
  slot the next turn (T34). The AI's `bed_search_bonus=40` fires whenever
  no Bed is on board AND a y=2 front slot is empty — using the contested
  column as the highest-priority Bed slot. This means clearing a front
  structure grants the AI respawn protection where it had only a defensive
  wall before. Do NOT clear front structures unless you can capitalize in
  the same turn (one-shot through remaining layers) or the clear is part
  of the confirmed kill sequence. Grinding a lane open turn-by-turn hands
  the AI a free Bed.

- **avatar_attack cannot chain through multiple structures.** Damage does
  NOT propagate past the first structure. Each avatar_attack resolves on
  the single frontmost structure in the column; excess damage is lost.
  A 3-deep column requires 4 Night turns for the avatar alone to reach
  face (front → mid → back → avatar). Planning any weapon-attack line
  that requires the avatar to "plow through" 2+ structures in fewer
  turns is mechanically impossible. The avatar needs mob partners to
  clear adjacent layers while the avatar handles a different row.

- **Warden ETB clears Workers ≤4HP — get Iron Golem out before opponent plays Warden.**
  Warden (7/8, I4+R2+D1) on entry deals 4 damage to ALL enemy mobs. In
  builder vs builder this is a non-issue (neither deck runs Warden). In
  builder vs miner, it is a game-defining threat: Steve's Helper (1/2),
  Alex's Scout (2/1), Village Guard (2/3), Wolf Pack (3/2 base), and
  Panda Forager (2/3) all die instantly to the 4-damage ETB. Only Iron
  Golem (3/4) survives. If the miner pilots Warden with a full builder
  Worker board already deployed, the builder loses its entire mob army
  in one card. Counter-line: deploy Iron Golem (I1+R1 via Strip Mine)
  BEFORE the opponent can play Warden (miner's Warden costs I4+R2+D1 —
  realistically T12+ for the miner). Do NOT flood Workers beyond what
  Iron Golem can anchor. Against miner, treat Iron Golem as a defensive
  Warden-survival anchor, not just the kill-sequence finisher.

## Iteration log

- 2026-05-07: builder mirror vs passive_econ — Draw in 36 turns. Builder
  mirror is a structure war; neither player dealt direct HP damage in 36
  turns. Workers mine XOR attack — dedicated attacker mobs essential.
- 2026-05-07 (iter 2): builder mirror vs passive_econ — Draw at T21
  play-turns. Differentiated by going weapon-aggro (Bow + Iron Sword) vs
  iter 1's pure econ. Dealt 6 direct HP to AI (first ever in builder
  mirror). Key findings: col 2 Bow window is ~4 Night turns; respawn
  strips weapon+armor both; Wolf Pack reaches 11 ATK with 8 Workers (not
  7 as previously assumed); Strip Mine is mandatory-2×; `passive_econ`
  doesn't mine iron aggressively despite huge stone surplus.
- 2026-05-07 (iter 3): builder mirror vs passive_econ — Draw at T36 (18
  play-turns). Planned Iron Golem via Strip Mine x2; Strip Mine never
  drawn in 18 turns. Fell back to Iron Sword + Wolf Pack line. Dealt 8
  direct HP (20→12, best so far). Key findings: (1) Iron Golem card shows
  cost I1+R1 in hand (not I3+R1 as documented — verify card def);
  (2) `passive_econ` mines iron at normal Cave rates with 5 Workers (iter-2
  "ignores iron" claim is run-specific, not confirmed); (3) Wolf Pack +
  avatar double-attack sequencing confirmed (Wolf Pack clears mid-row
  structure, avatar goes to face in same turn); (4) col-2 window timing
  is NOT fixed at T12-T20 — appeared T24-T28 in this run; (5) Strip Mine
  sparsity (~2/30) makes Iron Golem plan unreliable without a draw engine
  to find it early.
- 2026-05-07 (iter 4): builder mirror vs passive_econ — LOSS at T39.
  AI wins at 20 HP, pilot at 1 HP (no Bed). First loss in builder loop.
  Root causes: Worker drought (first Worker T12), no Strip Mine drawn,
  Water Bucket Moats sealed all mob attacks from T8, AI Wolf Pack reached
  11 ATK (8 Workers). Key findings: (1) avatar_attack does NOT propagate
  past the first structure — no overkill carry; each layer requires a full
  separate Night turn hit; (2) clearing a front structure when AI has no
  Bed triggers REACTIVE BED PLACEMENT in that exact slot the next turn —
  clearing can BACKFIRE; (3) Water Bucket Moat blocks mob lane attacks only,
  NOT avatar weapon attacks; (4) "true kill sequence" is Iron Golem (3 ATK)
  + Wolf Pack (≥4 Workers = 7 ATK) + avatar Iron Sword (4 ATK) attacking
  simultaneously in one Night turn (11+ ATK minimum), requires Strip Mine
  by T6; (5) AI's Bed was successfully destroyed T36 (Wolf Pack chump-block
  + Iron Sword exact-kill) but a Village Watchtower replaced it T38 — kill
  window after Bed destruction is 1 turn only. No preset changes (pilot
  loss = no confirmed weakness to patch).
- 2026-05-07 (iter 5): builder mirror vs passive_econ — LOSS at T27.
  AI wins at 20 HP, pilot at 11 HP (no Bed). True kill sequence test.
  Kill sequence never assembled: Strip Mine never drawn in 13 player turns
  (P≈40% miss without draw engine), both Iron Golem copies dead in hand all
  game. First Worker at T16, Wolf Pack at 4 ATK only, died T24. Bed lost
  T20, no replacement. 9 HP attrition in 2 Night turns = lethal.
  Key finding (VERIFIED): Pilot claimed avatar_attack on empty columns
  silently no-ops. CODE INVESTIGATION PROVES THIS WRONG. Engine routes
  empty columns to opponent face correctly (column_target → None → fallback
  to opponent player ID → apply_player_damage → player.life -= amount).
  Live test: P2 HP 20→19 on empty col 0 attack. Pilot's "zero damage"
  observations were structure hits not visible in the log readout — those
  columns had structures at y=0/y=1 not prominent in the display.
  No bias preset changes (consecutive loss, no exploitable weakness found).
- 2026-05-07 (iter 6): builder vs miner — STALL (two-pilot coordination
  failure). Pilot A (builder/P1) reached T1 with 2 Workers + Village
  Watchtower; Pilot B (miner/P2) reached T0 with Panda Forager deployed.
  Neither pilot saw the other's turn advance; both gave up after 10-30+
  polls. No combat, no HP damage, no winner. Key findings: (1) Warden ETB
  clears all builder Workers ≤4HP — Iron Golem is the only survivor;
  builder must have Iron Golem on board before miner plays Warden or the
  entire board collapses. (2) Miner's "Panda Forager before Bed" T0 line
  is more aggressive than standard — leaves miner Bed-less and material-
  zero on T2, but the 2/3 body is a stronger mining anchor. (3) Miner's
  late-game (Warden + Ender Dragon) theoretically outclasses builder's
  finishers in raw power ceiling — the builder must kill before miner
  resolves those cards. Added "Warden ETB" bullet to Anticipated weaknesses.
