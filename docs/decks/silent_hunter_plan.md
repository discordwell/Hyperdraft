# silent_hunter — Plan

## Composition summary

30-card SUBS stealth-control list (`SUBS_silent_hunter` in
`src/cards/depths/submarine_fleet/decks.py:100`):

- **1-cost (6)**: 4 Periscope Recon, 2 Listening Post (0/3 wall — the
  format-defining 0-power chump interceptor).
- **2-cost (10)**: 4 Stalker Sub (interceptor body), 3 Bottom-Crawler
  Probe (DEEP-band stealth), 3 U-Class Stalker.
- **3-cost (6)**: 3 Diesel Whisper (2/3 mid-band attacker), 3 Snorkel
  Stalker (the carry; +1 power EOT when attacking undetected, hull 1
  post-nerf).
- **Mid + actions (8)**: 2 Wolf at the Door, 2 Type-XXI Phantom (mid-
  late stealth attacker), 2 Iron Discipline (doctrine), 2 Sonar Jammer
  (action — currently broken via cast_effect_fn engine gap).

**Curve shape**: 16/30 in the 1-2 cost band, 6 at 3-cost, 4 mid-late
finishers. More balanced than Wolfpack — has a real mid-game.

**Sonar / Torpedo lean**: even split with slight Sonar lean. Has
detection income; can punish stealth and intercept reliably.

## Win condition

**Plan A (PROMOTED iter-4): Aggressive race.** Open Listening Post T1
as the wall, deploy Snorkel Stalker T2 for 4-dmg/turn chip starting T3,
add cheap stealth bodies (Periscope Recon, Stalker Sub, U-Class Stalker)
to set up 3-4 attacker swings by T7-T9. Hold control pieces (Iron
Discipline, Sonar Jammer) as insurance — they often go uncast in the
race line and that's fine. Target lethal T15-T18. Iter-4 evidence:
Pilot B (P2) won 20-0 in 17 turns vs bank-discipline Wolfpack with this
exact line.

**Plan B (DEMOTED iter-4): Grind.** Out-detect and out-intercept while
slowly chipping with stealth attackers from DEEP/MID. Realistic target
lethal T20-T35. Pilot B iter-1 won this way (T38). Use this plan only
when (a) the opener lacks Snorkel Stalker AND a cheap stealth body,
OR (b) the opp is a combo deck that out-grinds (Deep Strike).

## Target turns (Plan A — aggressive race, iter-4 promoted)

- **T1**: Listening Post deploy. Sets the wall the opp must answer.
- **T2**: Snorkel Stalker deploy at PERISCOPE. Auto-keeper enabler.
- **T3**: Snorkel Stalker swings undetected → 4 dmg to Flagship
  (3 power + 1 attack-undetected pump, no depth penalty since both at
  PERISCOPE). 25 → 21.
- **T4-T6**: Add Periscope Recon + Stalker Sub. Continue Snorkel chip
  for 4 dmg/turn. Bottom-Crawler Probe to DEEP if you have the SC for
  the dive (rarely; usually skip). Flagship 21 → 13 by T6.
- **T7-T9**: 3-attacker swing. Snorkel + Periscope + Probe all
  unintercepted (target's heuristic defense at this hull level may
  finally engage post-iter-5 cumulative-damage patch — see strategy
  doc). 6 dmg if uncontested. Flagship 13 → 7.
- **T11-T13**: 4-attacker swing. Add U-Class Stalker. Force opp into
  pure defense; Sat Strike / Pack Leader-anthem alpha never lands.
  Flagship 7 → 0 by T13-T17.
- **T15-T17**: Closing alpha. Trade attackers if needed; the opp's
  remaining hull is usually 0-3 by here.

## Target turns (Plan B — grind, iter-1 fallback)

- **T1-T7**: Build board. Deploy Listening Post for the 0/3 wall.
  Periscope Recon for the cheap stealth body. **Bank Sonar income** —
  do not spend SC on speculative detections.
- **T8-T13**: Detection economy comes online. Spend banked SC
  surgically — detect the highest-power attackers first, let chip
  damage from 1-power Subs through.
- **T13-T20**: Snorkel Stalker comes down for the +1 power EOT
  attacking-undetected line. Type-XXI Phantom deploys to MID/DEEP for
  hard-to-detect chip damage.
- **T20-T35**: Grind. The opponent's deck either cracks or stabilises.

## Key cards

- **Listening Post** (0/3, {1T}) — the format-defining 0-power chump
  interceptor. Costs nothing, soaks 1-2 power attackers indefinitely
  without trading. Against Wolfpack specifically this card alone may
  win the game (Pilot A confirmed at T21 onward — "burned through
  Wolf-cubs/Coastal Raiders/Pack Runner for no flagship damage").
- **Stalker Sub** ({2T}, 2/3) — the workhorse interceptor. Trades up
  into 1-2 power Wolfpack swarm cleanly.
- **Snorkel Stalker** ({3T}, 2/1 hull post-nerf) — the deck's carry.
  +1 power EOT when attacking undetected. Late-game finisher; the
  delayed clock.
- **Diesel Whisper** ({3T}, 2/3 stealth) — mid-band stealth body.
  Hard for aggro decks to detect because they have ~no SC income.
- **Bottom-Crawler Probe** ({2T}) — DEEP-band sit. Detection cost
  for the attacker is `1 + DEEP difficulty` = 4 Sonar, prohibitive
  for any deck without dedicated Sonar income.
- **Sonar Jammer** ({2T} action, currently broken) — would raise
  detection cost. Engine bug: cast_effect_fn never fires. Treat as
  dead 2-cost slot until fixed.
- **Iron Discipline** ({1T} doctrine — exact effect TBD) — global
  enchantment.

## Mulligan policy

- **Auto-keep**: Listening Post + 1× {1T} unit + 1× {2T} interceptor
  (Stalker Sub or Probe). Sets up the wall + grind plan immediately.
- **Auto-keep (good)**: Listening Post + 2× cheap detection bodies.
- **Auto-keep (iter-2 add)**: any hand WITH Iron Discipline AND a
  Type-XXI Phantom in the deck. Iron Discipline → DEEP-stealth chip is
  the primary late-game plan vs aggro decks; without Iron Discipline
  the deck has no answer to a fully-buffed Wolfpack saturation swing.
  Note: until the `default_depth` engine bug is fixed, Phantom must be
  manually dove to DEEP across 3 SC over 3 turns (it spawns at
  SURFACE despite its DEEP default — see strategy doc Engine punchlist).
- **Salvage**: Hand with no Listening Post but 2× early stealth bodies
  + Snorkel Stalker in the back. Race-as-control plan — see Play
  priority #0 (iter-3 add).
- **MULLIGAN HARDER (iter-3 refinement)**: opening hand with NEITHER
  Listening Post NOR Iron Discipline = neither wing of the deck's plan
  is online. Pilot B drew this exact opener iter-3 and was forced to
  improvise an aggressive race; nearly won (lost by 6 hull) but the
  margin was on the wrong side of variance. Recommendation: ship a
  no-LP/no-Iron-Discipline opener UNLESS the hand contains Snorkel
  Stalker AND ≥1 cheap stealth body (in which case keep and switch to
  the aggressive-race plan from T1).
- **Auto-mull**: 0 cards costing ≤2T.

## Play priorities (order)

0. **AGGRESSIVE-RACE PIVOT (iter-3 add) when neither Listening Post
   nor Iron Discipline is in the opener.** Skip the grind plan
   entirely. Deploy Snorkel Stalker by T6-T8, then start 3-attacker
   swings by T14. Sonar Jammer 2x cast (drains 2 SC from opp) gates
   their detection budget. **Iter-3 evidence**: Pilot B did this
   organically and chip-attacked OPP from 25 → 6 in three swings
   (T14/T18/T22) UNINTERCEPTED — P1's heuristic defense had SC=4-9
   the whole time but the lethal-buffer threshold was never crossed.
   Pilot B lost by 6 hull because they ran out of follow-up; with one
   more deploy turn or +2 SC at T22-T24 it would have been a win.
   This is a viable Plan B for the deck, NOT a desperation move.
1. **Listening Post on T1 if available** — sets the wall the
   opponent must remove (and Wolfpack has no removal).
2. **Bank Sonar through T7-T11.** Do NOT spend SC on speculative
   detections. The opponent's chip damage in this window is *cheap to
   absorb* relative to the SC you'd burn detecting it. Pilot B
   followed this line cleanly: through T11 they spent 0 SC even while
   taking ~9 hull damage.
3. **Surgical detection T13+.** Spend banked SC on the *threats you
   cannot afford to leave alive* — the Pack Leaders, Hammerheads,
   buffed Snorkel Stalkers. Let the 1-power Wolf-cubs through.
4. **Stalker Sub on a defender turn** — trade up into 1-2 power swarm.
5. **Snorkel Stalker T13+** for the slow Flagship clock.
6. **Diesel Whisper / Bottom-Crawler Probe at MID/DEEP** for
   undetectable chip damage.
7. **Sonar Jammer** — when fixed, cast on a turn where the opponent
   has a saturation swing teed up.

## Anticipated weaknesses

- **Slow clock.** Snorkel Stalker is the carry. Without it (or at
  hull 1 post-nerf, a single failed interception kills it), the deck
  has no real Flagship-pressure plan. If a fast aggro deck reaches its
  anthems before T15 the deck cannot stabilise in time.
- **CONFIRMED iter-2: Top-heavy aggro that BANKS into anthems beats
  this deck.** Pilot A's iter-2 bank-then-deploy line landed Pack
  Leader U-99 + Saturation Strike for an 11-damage T16 alpha that the
  interceptor wall couldn't stop. The wall absorbs *unbuffed* 1-2
  power chip; once Wolfpack hits +2-3 power per attacker, every
  attacker punches through Listening Post (3 toughness) and Stalker
  Sub (3 hull) in one swing. The matchup is now decisively bad —
  iter-2 result was 25-vs-0 — and only flips back if either (a) the
  pilot intervenes to spend SC on the alpha turn (the medium AI
  defense can't, see Engine punchlist pump-blind bug, partially
  patched iter-2) or (b) the silent_hunter pilot lands Iron Discipline
  AND dives Type-XXI Phantom to DEEP for an unblockable counter-clock.
- **Type-XXI Phantom currently broken in practice (iter-2).** Card
  defines `default_depth=DEEP` but `deploy_vessel` ignores it and
  spawns at SURFACE. Iron Discipline → DEEP-stealth plan requires
  Phantom to be at DEEP for the unblockable bit to fire. Until
  fixed, Phantom is a 5-cost attacker that takes 3 turns of dives
  (3 SC) to reach DEEP — push to T22+ at the earliest. Effective
  deck size with Phantom this slow: ~27 (Phantom marginal, Sonar
  Jammer marginal, 1 Iron Discipline reliable).
- **Sonar Jammer** — engine fix verified iter-2 (cast_effect_fn now
  invoked) but the action's effect_fn body itself may still be a
  stub returning `[]`. Test cast in iter-3 before relying on it.
- **Combo decks (Deep Strike) outlast Silent Hunter on absolute
  resource accumulation.** Untested vs the new Pilot B line; a slow
  deck mirror likely turns on Snorkel Stalker reach vs Deep Strike's
  finisher count.

## Iteration log

- **2026-05-07 (iter-5)**: vs Wolfpack (LLM Pilot A, refined greedy
  + custom-depth deploy flag). **W in 19 turns harness / T10 internal
  lethal**, ME=12/25 vs OPP=0/25 (Flagship sunk). Pilot B self-graded
  **9/10**, "cleanest decisive win in 5 iters". Iter-1→2→3→4→5
  result: W 1-0 (38) → L 0-21 (28) → L 0-6 (25) → **W 20-0 (17) →
  W 12-0 (10/19)** — second consecutive decisive Silent_Hunter win
  on a clean engine, confirming the iter-4 plan promotion.
  Key new findings:
  - **Aggressive race plan now N=2 wins.** Confirms iter-4's plan
    promotion; the matchup-vs-strategy combo is settled at this
    confidence level. Future iters should pivot to other matchups
    rather than re-confirm.
  - **Snorkel Stalker @ PERISCOPE post default_depth fix verified
    structurally strong.** Spawns at PERISCOPE (no SC dive needed),
    hits flagship for 4 dmg unintercepted T3-T7. ~8 SC saved across
    the game vs the iter-4 manual-dive path; this saving directly
    funds the late-game surgical defense via the cumulative-damage
    patch. Compounding win condition.
  - **Cumulative-damage patch fires at T6** (vs iter-4 T15). Pilot A
    (P1) finally detected after 15 dmg taken in 3 turns — that's the
    patch firing exactly as designed. Lost a Snorkel + Periscope to
    interception this iter where iter-4 lost nothing; the matchup is
    *harder* than iter-4 but still decisively won by SH.
  - **Snorkel #2 backup carry deploy** (T6) was a strong play —
    redundancy if Snorkel #1 gets intercepted. New play priority: any
    second Snorkel from hand should auto-deploy on the turn after
    the first one starts taking SC fire.
  - **Dive-to-MID saves no SC vs sonar ≥ 2.** T8 Pilot B dove
    Snorkel #2 to MID (1 SC); P1 still detected (sonar=2 vs MID
    detection cost 3 — but P1 had 2+1=3 available). Net: dive cost
    1 SC for 0 benefit. Rule: only dive to MID when defender SC ≤ 1
    AND deployed Snorkel is the carry; otherwise eat the detection.
  - **Pack Leader U-99 NEVER deployed by Pilot A this iter** (or any
    iter, 0/5 streak). The aggressive race kills Wolfpack before its
    {3T} top-end becomes castable — the matchup is now *structurally*
    inverse to iter-2/iter-3.
  - **Iron Discipline still uncast** (drew Phantom T6, never castable).
    Plan A's race wins so fast that Plan B's Iron Discipline + Phantom
    finisher never materialises. This is fine — confirms control
    pieces are insurance, not requirement.

- **2026-05-07 (iter-4)**: vs Wolfpack (LLM Pilot A, refined greedy
  + bank discipline). **W in 17 turns**, ME=20/25 vs OPP=0/25 (Flagship
  sunk). Pilot B self-graded **9/10**, "cleanest decisive win in 4
  iters". Iter-1→2→3→4 result: W 1-0 (38) → L 0-21 (28) → L 0-6 (25)
  → **W 20-0 (17)** — first decisive Silent_Hunter win since iter-1.
  Key new findings:
  - **Hybrid policy "open aggressive even with control pieces"
    confirmed correct.** Drew BOTH LP + Iron Discipline + Snorkel —
    used LP only, never cast Iron Discipline (no DEEP vessel to
    anchor it). Aggressive Snorkel deploy T2 → 4 dmg/turn chip from
    T3 → P1 flagship at 4 hull by T13. **Promoted aggressive race
    from Plan B → Plan A** in this plan above.
  - **Snorkel Stalker damage 4/swing investigated — NO BUG.** Pilot
    B reported the 4-dmg observation. Engine math: PERISCOPE
    (default_depth) → PERISCOPE (Flagship) = depth diff 0 → no
    penalty. Power 3 + 1 attack-undetected pump = 4. Reporter's
    expectation of 3 was wrong (assumed SURFACE→PERISCOPE penalty).
    Logged in strategy doc Engine punchlist as resolved.
  - **Pilot A's defense ate 4 unintercepted swings T9-T13** despite
    iter-4 lethal-buffer fix (5→3). Same pattern as iter-3. The
    cumulative-recent-damage patch shipped THIS pass (see strategy
    doc Engine punchlist) should fix this in iter-5.
  - **Listening Post deployed T1 was decisive** — soaked Pilot A's
    2-power Wolf-cubs harmlessly (LP wasn't even attacked the whole
    game). Reaffirms LP as the format-defining 0-power chump
    interceptor.
  - **Mulligan policy**: dream opener (LP + Iron Discipline + Snorkel
    + Jammer + Wolf at the Door) is auto-keep but uses only LP +
    Snorkel; the rest are insurance. Refined mulligan rule above
    notes this opener is auto-keep regardless of Iron Discipline.

- **2026-05-07 (iter-3)**: vs Wolfpack (LLM Pilot A, refined greedy
  + Sat-Strike-timing discipline). **L in 26 turns**, ME=0/25 vs
  OPP=6/25 — close loss by 6 hull. Pilot B self-graded **6/10**,
  characterized as "iter-2 was 0/25, iter-3 was 0/6 — significant
  improvement on the same matchup".
  Key new findings:
  - **Aggressive-race pivot is a viable Plan B.** Opener had no
    Listening Post and no Iron Discipline. Pilot B improvised:
    deployed Snorkel Stalker T10, Sonar Jammer 2x for opp-SC drain,
    and ran 3-attacker offensive swings T14/T18/T22 — ALL THREE
    UNINTERCEPTED — chip-attacking OPP from 25 → 6 nearly free.
    Codified as Play priority #0 above.
  - **Sonar Jammer (proxy `_drain_opponent_charges`) confirmed
    working post-iter-2 fix.** 2 casts = -2 SC for opp, net 0 SC
    cost for me. Genuine tempo tool.
  - **Pack Leader U-99 killed by incidental chip.** Bottom-Crawler
    Probe (1/4) likely chip-killed Pack Leader during a defensive
    intercept around T20-T21. Pilot A lost the anthem source through
    a non-targeted interaction. Counter for Wolfpack: protect Pack
    Leader at MID/DEEP if engine bug allows; for Silent_Hunter, this
    is a free upside — incidental anthem-kills are realistic.
  - **Razor-thin defensive timing during the race.** When all my
    interceptors were tapped from offense T20-T24, P1 swung freely
    for 5-7 dmg/turn. The race plan needs either a 1-turn-faster
    lethal OR a defensive doctrine to bridge.
  - **Mulligan policy gap.** Iter-3 opener had no LP + no Iron
    Discipline. The prior auto-keep heuristic doesn't cover this
    case. Refined above: mulligan harder UNLESS Snorkel + cheap
    stealth body are present (then keep and pivot aggressive from T1).
  - **Pilot A's defense was too passive (filed in strategy doc
    Engine punchlist as defense under-detection bug).** Heuristic
    defense had SC=4-9 across T14/T18/T22 and never intercepted my
    3-attacker swings. The lethal-buffer-only threshold means
    mid-game chip is allowed through indefinitely. This was the
    mechanical reason Pilot B almost won the race.
  - **`pt_modifiers` visibility helped predict but not catch in
    flight.** Pack Leader U-99's anthem fires only on attack-declare
    and clears EOT before my next-turn poll. Useful for predicting
    "P1 has 2 attackers + Pack Leader → anthem will fire next swing"
    but the field stays empty in main phases.

- **2026-05-07 (iter-2)**: vs Wolfpack (LLM Pilot A, refined greedy
  with bank-turn discipline). **L in 28 turns**, ME=0/25 vs OPP=21/25.
  Pilot B self-graded **3/10** — the strategy didn't fail; the engine
  layer beneath it did. Bank-then-detect plan executed cleanly through
  T17: spent 0 SC on detection, took ~9 hull of cheap chip, then
  Iron Discipline + Type-XXI Phantom plan was the intended late-game
  pivot.
  Key new findings:
  - **Iron Discipline cast went well** ({3S}); the doctrine's idea is
    sound. Pilot B's intended T17+ pivot was: deploy Type-XXI Phantom
    at DEEP under Iron Discipline → unblockable chip clock against
    Wolfpack's anthems.
  - **Engine bug killed the pivot**: Type-XXI Phantom's
    `default_depth=DEEP` is ignored by `deploy_vessel`; the card
    spawned at SURFACE despite the printed DEEP default. Filed in
    `docs/strategy/depths.md` Engine punchlist. Until fixed, Phantom
    is a slow-clock liability requiring 3 SC of dives.
  - **Engine bug killed the defense**: medium AI defense was
    pump-blind to Saturation Strike's +2 EOT pump. Defender's
    cumulative-damage projection sat under the lethal-buffer
    threshold while a 9-damage alpha walked into the flagship on T18.
    Patched this pass — `_power(obj, state)` and
    `_depth_modifier_damage(..., state)` now route through
    `get_power`. Regression test added.
  - **Listening Post survived to game end** but didn't matter — once
    Wolfpack's pump effects activated, every Sub punched through 3
    toughness in one hit. Listening Post is excellent vs no-anthem
    aggro and irrelevant vs anthem-aggro.
  - **Snorkel Stalker held back too long**. Pilot B held it per the
    iter-1 lesson "T13+ for safe deploy" but never deployed it in
    iter-2 — should have shipped T17 alongside Iron Discipline for
    immediate pressure, regardless of detection risk.
  - **Two-pilot harness coordination bug** — T23-T28 advanced without
    Pilot B having a window to queue actions. Pilot A's poll-and-play
    loop ran ahead. Out of scope for this deck plan; flagged in the
    strategy doc Contested questions for the harness team.

- **2026-05-07** (iter-1): vs Wolfpack (LLM Pilot A, greedy).
  **W in 38 turns**, OPP=0/25 vs ME=1/25 — a one-hull win after
  surviving Pilot A's T9-T11 chip damage (P2 at 16 hull) and
  Pilot A's T17 saturation swing (P2 at 3 hull). **Pilot B timed
  out mid-session** so the report did not write — what we know is
  inferred from `/tmp/depths_game_history.txt` action counts and
  Pilot A's read of P2's lines.
  Inferred from action counts + opponent narrative:
  - **Sonar bank discipline through T11**: action-count history
    shows P2 played 1 action per turn through T7-T11 (likely
    deploys), then ramped to 1-2 actions per detection turn from
    T13. Combined with Pilot A's note that P2 did not detect through
    T11, the bank-then-spend pattern is well-evidenced.
  - **Surgical detection T17**: spent 3 SC on the 3 highest-power
    attackers, let smallest (Pack Runner) through for 3 face. Correct
    triage given the bank.
  - **Wide-and-slow board build**: by T19 P2 had multiple Stalkers +
    Diesel Whisper + Listening Post out. Each 2/3 body tanked Pilot
    A's 1-2 power suicide attackers cleanly.
  - **Closing pressure T35-T37**: with Pilot A's deck top-heavy and
    bricked, P2 turned to face damage — 4 attacks at T37 closed
    Pilot A from ~7 hull to 0.

  Plan-side observations:
  - The format-wide "bank Sonar early" lesson is a real edge if the
    opposing aggro pilot is greedy. Codified in
    `docs/strategy/depths.md` Format-wide tactical patterns.
  - Listening Post + interceptor wall successfully stalls a swarm
    aggro deck without removal. This is the matchup the deck is
    *built* to win and it did.
  - **Open question for iter-2**: would the same line lose to a
    bank-and-hold Wolfpack pilot that actually casts Doctrine on T8?
    Untested; suspect this is a much harder matchup. See contested
    question in strategy doc.

### Iter 6 (2026-05-07) — vs Carrier (LLM Pilot A), P2 mostly heuristic
**Lost** in T17, ME=0/25, OPP=25/25. Harness pickle race condition degraded
P2 to heuristic autopilot after T2 (concurrent writes from both pilots).
One action executed: Listening Post deployed on T2.

Calibration findings (from P2's T2 window + heuristic behavior observed):
- **Bank-until-T8 is WRONG vs Carrier**: Carrier builds a 4-drone board by T5.
  4 × 2/1 drones = 4-5 hull/swing. 12 free turns of chip = certain loss.
  SH vs Carrier: detection investment must begin T5, not T11.
- **LP band placement is load-bearing**: Heuristic deployed LP at MID. SURFACE
  attackers targeting PERISCOPE flagship cannot be intercepted by a MID vessel
  (band coverage rule). LP must be at SURFACE or PERISCOPE for SURFACE attackers.
- **Heuristic SH never attacked**: the heuristic has no attack policy vs a wide
  board without clear interception opportunities. Manual pilots must push
  counter-attacks aggressively when ahead on SC.
- **Detect early vs swarms or lose**: iterating on the "surgical detection"
  lesson — it's correct vs single high-power attackers but wrong vs 4+ 1-power
  drones. Against wide drone boards: spend SC every turn to cut the swarm size,
  accept that you can't fully answer 4+ attackers, and attack aggressively to
  create a race condition where P1's SC bank is also drained.

Open question: can SH's stealth attackers create a race where P1 is forced to
spend SC detecting YOUR vessels while your Listening Post walls chump P1's
drones? Untested — would require a fully LLM-piloted P2 game.

### Iter 7 (2026-05-07) — vs Carrier (LLM Pilot A + Pilot B dual-seat), P2 heuristic AI
**Lost** in 18 turns, ME=0/25, OPP≈11/25. Pilot B controlled both seats in a
single-agent game (harness quirks prevented true two-pilot mode).

Key findings:
- **No Listening Post in opener**: hand draw variance left SH without LP. This
  was decisive — P1's drones attacked the flagship directly every turn with no
  interception. LP's absence is a significant structural disadvantage vs Carrier.
- **Chip-stream detection patch ACTIVE**: detection DID fire this iter (~T12-T14 vs
  0 in iter-6). P2's AI spent SC detecting after ~7 hull accumulated. A 7-attacker
  swing on T14 was reduced from potential 14 damage to 3 damage. Patch works.
- **Detection without interceptors = wasted SC**: on T18, P2 detected all 3 incoming
  attackers but had no interceptors left (both Snorkel Stalkers killed T13-T14). The 3
  detections were pure SC waste — full damage landed anyway. This was the direct
  motivation for the iter-7 patch in `_medium_detections`.
- **Both Snorkel Stalkers died by T14**: Snorkel #1 killed by Escort Frigate (reach)
  intercept T13. Snorkel #2 intercepted T14. After T14 SH had only Periscope Recon +
  Diesel Whisper, dealing 3/turn vs Carrier's 5/turn incoming — unwinnable race.
- **P1 dealt 14 hull to SH flagship** (vs 0 in iter-6) — first SH counter-attack
  success. The Snorkel + Recon alpha at T11 (5 damage) created a brief 18v19 race
  that was genuinely close.
- **Diesel Whisper at MID hit for full power (2)** — depth modifier applied: MID
  (band 2) → PERISCOPE (band 1) diff=1, max(1, 2-1)=1. Wait: harness logged "2
  damage" but actual target damage = 1. This is the same pre-pipeline vs post-pipeline
  logging confusion as the SURFACE drone issue.

**Engine clarification (iter-7)**: Both Pilot A and Pilot B observed "full printed
power" damage and hypothesised undetected attackers bypass depth modifier. CONFIRMED
INCORRECT. The depth modifier fires for all combat. Harness logs print pre-transform
event payloads (raw power). Actual target damage is post-transform (reduced). See
`test_undetected_attack_depth_modifier` in `tests/test_depths_smoke.py`.

**Iter-8 SH vs Carrier plan**:
- LP T1 is MANDATORY. Mulligan if not present (Pilot B's iter-7 opener had no LP —
  recommend hard mulligan on any LP-less hand against Carrier).
- Deploy Snorkel Stalker T2-T3, but protect it from Escort Frigate reach interception
  by diving to MID once Frigate appears (costs 1 SC but avoids the Frigate counter).
- Counter-attack aggressively when ahead on SC — the race at T11-T14 was the closest
  SH has come to beating Carrier; more aggressive offense earlier might close it.
