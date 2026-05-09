# silent_hunter — Plan

## Composition summary

30-card SUBS stealth-control list (`SUBS_silent_hunter` in
`src/cards/depths/submarine_fleet/decks.py:100`):

- **1-cost (6)**: 4 Periscope Recon ({1T}), 2 Listening Post (0/3 wall —
  the format-defining 0-power chump interceptor; costs {1S} NOT {1T} —
  iter-8 correction).
- **2-cost (10)**: 4 Stalker Sub ({2T}, interceptor body), 3 Bottom-Crawler
  Probe ({2S}, DEEP-band stealth), 3 U-Class Stalker ({2T,1S}).
- **2-cost (confirmed iter-8)**: 3 Snorkel Stalker ({2T} NOT {3T} —
  iter-8 correction; deploy T2 not T3; the carry, +1 power EOT when
  attacking undetected, hull 1 post-nerf).
- **3-cost (3)**: 3 Diesel Whisper ({2T,1S}, 2/3 mid-band attacker).
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

- **Listening Post** (0/3, {1S} — SONAR not Torpedo; iter-8 correction) —
  the format-defining 0-power chump interceptor. Costs 1 Sonar (not TC),
  so it can be deployed on T1 without consuming any Torpedo Charge. Against
  Wolfpack specifically this card alone may win the game (Pilot A confirmed
  at T21 onward — "burned through Wolf-cubs/Coastal Raiders/Pack Runner for
  no flagship damage").
- **Stalker Sub** ({2T}, 2/3) — the workhorse interceptor. Trades up
  into 1-2 power Wolfpack swarm cleanly.
- **Snorkel Stalker** ({2T} — iter-8 correction; was listed as {3T}) —
  the deck's carry. 3/1 hull (3 base + 1 undetected-attack pump, hull 1
  post-nerf). Deployable T2, one turn earlier than previously planned.
  +1 power EOT when attacking undetected. The primary Flagship clock.
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

## Iter-11 key lessons

**EC kill is the highest-value play after landing combat damage on EC**:
When Snorkel combat damage (or any intercept exchange) reduces EC to ≤2 hull,
redirect an attacker to finish it immediately. Do not chip the Flagship instead.
EC kill freezes the drone engine permanently — worth more than any 2 Flagship hull.
Confirmed iter-11: EC kill on T11 froze P1 at 3 Drones for turns 11-23.

**LP gate — SC banking for burst interception**:
LP only intercepts when SC is spent to detect the attacker first. SC income is ~1/turn.
With 3 Drones attacking simultaneously, LP can intercept at most 1/turn. To guarantee
LP fires during critical early turns (T4-T5), bank SC in T1-T3 (spend 0 SC on other
detections). Arriving at T4 with SC=3-4 lets LP intercept 3-4 Drone attacks in burst
while Snorkel chips the Flagship uncontested.

**Patrol Bomber must be killed immediately (homing priority)**:
Patrol Bomber (2/1 homing) bypasses depth modifier. Every turn PB is alive costs 2
effective hull. Use cheapest available vessel attack (Periscope Recon 1/2 trades into
PB 2/1 favorably — PB's power 2 at SURFACE→PERISCOPE = max(1,2-1)=1 vs Recon's hull 2,
Recon survives). Priority: detect+kill PB the turn after it deploys.

**Width closing alpha beats partial interception**:
Iter-11 closing alpha: 6 attackers, P1 intercepted Snorkel with Escort Frigate (best
response). Remaining 5 attackers dealt 7 damage to 4-hull Flagship. Build wide — even
losing your best attacker to interception, enough width closes the game.

**Fallback when Snorkel not in opener**:
T1 LP → T2 Stalker Sub → T3 start attacking. Probe to DEEP for SC-drain pressure. Clock
is 2/turn instead of 4/turn, but the attrition plan (kill EC, reduce drone count, build
width) still wins vs Carrier. Target lethal T20-T25 without Snorkel opener. Do not hold
Wolf at the Door hoping to play it — with constant TC pressure it is rarely affordable
during the race. Treat Wolf as insurance, not a plan.

**Bottom-Crawler Probe as vessel-killer**:
Probe (1/4 DEEP) can redirect from Flagship to kill individual Drones (1 damage exactly
kills 1-hull Drone; Probe takes 1 back, remains at 3 hull). Reducing drone count by 1/turn
is worth more than 1 Flagship chip/turn in the endgame when the opponent's board is wide.

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
2. **Bank Sonar for burst detection at LP's critical window (T4-T5)**. Against Carrier,
   spend 0 SC on T1-T3 even if taking chip damage. Arrive at T4-T5 with SC=3-4 banked.
   Use banked SC to fund LP interceptions during the turns before EC comes online (T4 is
   EC's earliest landing). LP-with-banked-SC absorbs 3-4 Drone attacks in burst; after
   EC lands and spawns Drones, the volume will exceed your bank. Pivot to surgical
   detection (priority #3 below) after EC lands.
   Against Wolfpack (slower clock): bank through T7-T11 as before — the opponent's chip
   damage is cheap to absorb relative to the SC you'd burn detecting it.
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

- **2026-05-07 (iter-8)**: vs Carrier (LLM Pilot A, EC-by-T4 directive). **W in 17
  turns**, ME=18/25 vs OPP=0/25 (Flagship sunk). Pilot B self-graded **9/10**,
  "first clean Silent_Hunter victory vs Carrier archetype in the matchup series".
  Turn order: P2 (SH) went first.
  Key new findings:
  - **LP at SURFACE (T1) + Snorkel at PERISCOPE (T2) = decisive opener vs Carrier.**
    LP intercepted SURFACE Drones throughout; Snorkel dealt 4 dmg/turn T3-T5 (12 dmg
    before EC landed). Flagship sunk in 17 turns at 18/25 hull remaining.
  - **COST CORRECTIONS confirmed in-game (iter-8)**:
    - Listening Post costs {1S} (Sonar), NOT {1T} (Torpedo). LP can be deployed on T1
      without consuming any Torpedo Charge — LP + a TC vessel is possible in the same turn.
    - Snorkel Stalker costs {2T} (Torpedo), NOT {3T}. One tier cheaper than planned;
      accessible T2 (one turn earlier than the T2-T3 window in older plans).
  - **SC starvation cascade (critical pattern)**: P1 spent all 5 SC on T6 detecting
    Snorkel + Recon. This left P1 at SC=0 for T7-T9. All 3 turns were completely free
    hits: 3+5+5=13 undetected damage. SH's endgame was 3 turns of free uncontested attacks.
    This cascade is repeatable: LP+Snorkel T1/T2 forces P1 into early detection spending;
    Recon swarm (SR keyword, 3 SC to detect each) exploits the bankruptcy.
  - **Periscope Recon as late-game carry**: treated as "cheap early body" in older plans.
    With SR keyword (3 SC detection cost each), Recons are effectively undetectable when
    P1 SC is depleted. 3× Recon on the board = 9 SC detection tax. The endgame archetype
    for SH vs Carrier is: Snorkel early clock → LP wall → Recon swarm as bankruptcy closer.
  - **AI interceptor bug (Carrier sacrificed)**: P1's heuristic assigned Escort Carrier
    (5-hull engine piece) as interceptor for Snorkel on T6 instead of a Drone (1-hull
    expendable). This burned the Carrier to 1 hull; SH killed it T7 for free. Fix shipped
    in this coach pass (iter-8): Carriers now deprioritized in `_medium_interceptors`.
  - **Carrier drone token bug (crippled P1)**: All EC drone tokens spawned at UNKNOWN
    band and dealt 0 damage despite attacking. The engine piece was structurally non-
    functional. Fix shipped: `_handle_object_created` in zone.py now reads `depth_band`
    from the payload and applies it to the new object's state.
  - **Turn order advantage noted**: SH went first (P2 in game turn order but first to
    act). 1-turn head start on board building may have contributed to the decisive margin.

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

### Iter 9 (2026-05-07) — vs Carrier (LLM Pilot A), both engine fixes applied
**Won**. Engine bugs fixed this pass; first clean result since iter-8.

Key findings:
- **LP draw variance (critical pattern)**: Iters 8 AND 9 both failed to get LP in the
  opening hand in at least one run. The LP-less-opener risk is a recurring structural
  problem. **Recommendation for iter-10**: use a seeded hand or harness `--force-hand`
  flag to guarantee LP in at least one test. Two consecutive natural draws without LP
  is insufficient sample size to evaluate the LP-present matchup.
- **Homing bug fix benefits SH**: SURFACE Drones now deal 1 damage each (not 2) when
  undetected. SH's Flagship absorbs drone swarms at half the previous rate. P2 banked
  SC=9+ without needing to spend any SC on detection — the corrected damage rate is low
  enough that detection can be entirely deferred.
- **No-interceptors detection guard fix helps P1 not P2**: the `_medium_detections`
  guard fix was a P1 AI improvement (Carrier's heuristic AI now detects even when no
  interceptors are ready, if lethal threat is projected). Does not directly affect SH
  game plan.
- **SC banking confirmed dominant**: P2 banked 9+ SC without spending any. The corrected
  1-damage drone rate means SH does NOT need to invest SC in early detection vs Carrier
  swarms. The SC saved funds late-game surgical interception of the Carrier engine itself.

**Iter-10 recommendation**: run a 3-game mini-tournament (best-of-3) with seeded LP in P2
opener for at least 2 of the 3 games, to isolate Carrier matchup quality from LP draw
variance.

### Iter 6 (2026-05-07) — vs Carrier (LLM Pilot A), P2 mostly heuristic
**Lost** in T17, ME=0/25, OPP=25/25. Harness pickle race condition degraded
P2 to heuristic autopilot after T2 (concurrent writes from both pilots).
One action executed: Listening Post deployed on T2.

Calibration findings (from P2's T2 window + heuristic behavior observed):
- **Bank-until-T8 is WRONG vs Carrier**: Carrier builds a 4-drone board by T5.
  4 × 2/1 drones = 4-5 hull/swing. 12 free turns of chip = certain loss.
  SH vs Carrier: detection investment must begin T5, not T11.
- ~~**LP band placement is load-bearing**: Heuristic deployed LP at MID. SURFACE
  attackers targeting PERISCOPE flagship cannot be intercepted by a MID vessel
  (band coverage rule). LP must be at SURFACE or PERISCOPE for SURFACE attackers.~~
  **RETRACTED (iter-10)**: LP at MID IS within intercept range of the PERISCOPE
  flagship (depth_difference(PERISCOPE, MID)=1 ≤ DEFAULT_INTERCEPT_RANGE=1). The
  AI heuristic was not assigning LP as an interceptor due to an adapter bug in
  `_can_intercept`, now fixed. LP at MID (its default) is correct placement.
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

### Iter 11 (2026-05-09) — vs Carrier (LLM Pilot A), first clean LP-active game
**Won** in 23 turns, ME=2/25, OPP=0/25. First clean LP-active game with all fixes active.

Key findings:
- **Snorkel not in opener — fallback plan worked**: Snorkel appeared T7 via draw. Clock delayed 4
  turns. Despite the delay, the attrition plan (LP wall + kill EC + build width) won. Confirmed:
  the fallback plan is viable. Target lethal is T20-T25 without Snorkel opener.
- **EC kill was the game-deciding play**: Redirected Stalker Sub at T11 to finish EC (at 1 hull
  from Snorkel T9 combat damage). EC killed. P1 frozen at 3 Drones for the rest of the game.
  Flagship chipping would have been worth ~2 hull; EC kill was worth ~12 hull-equivalent in
  Drones P1 never spawned. This is the highest-value target when EC is at ≤2 hull.
- **LP did intercept (adapter fix confirmed)**: LP hull went 3→1 over 2 interceptions (T4-T14
  window). However, the binding constraint was SC: with SC income ~1/turn and 3 Drones attacking,
  LP only fired when detection was funded. LP is reactive, not passive. 13 turns elapsed before
  P2's detection threshold triggered reliably. LP provided exactly 2 confirmed intercepts before dying.
- **Killing Patrol Bomber immediately was correct**: Periscope Recon killed PB on T17 before it
  fired. PB (homing 2/1) would have dealt 2 hull/turn for the rest of the game — a total of
  ~4-6 hull saved for the cost of 1 Recon hull. Any time PB deploys, kill it before your next turn.
- **Width alpha closed the game despite losing Snorkel**: Closing alpha with 6 attackers; P1
  intercepted Snorkel with Escort Frigate (both died). Remaining 5 attackers dealt 7 damage to
  4-hull Flagship. Build wide — partial interception cannot stop width at game end.
- **Wolf at the Door never cast**: Constant TC pressure meant Wolf (3T,1S) was unaffordable
  throughout the race. Confirmed: treat Wolf as insurance, not a plan component.
- **Defense AI EC-as-interceptor bug helped P2**: The AI assigned EC (at 1 hull) as interceptor
  for Stalker Sub, killing it. This is a bug the encoder will fix — do not rely on it in future
  games. Instead, plan for P1's EC to survive and target it with a vessel attack.

### Iter 10 (2026-05-07) — vs Carrier (LLM Pilot A), harness blank-turn bug corrupted data
**Lost** in 20 turns, ME=0/25, OPP=21/25. **Data is not clean** — turns 5, 7, 9, 11, 13, 17
ran blank due to the `--seat` two-pilot coordination bug (now fixed). P2 took only ~4 meaningful
turns. The LP+Snorkel opener test never materialized — Snorkel Stalker was never deployed.

**LP band analysis — CORRECTED (overrides iter-6/8/A claims)**:
- LP's `default_depth=MID` is correct by design. LP at MID IS within intercept range of the
  PERISCOPE Flagship: `depth_difference(PERISCOPE=1, MID=2)=1 <= DEFAULT_INTERCEPT_RANGE=1`.
  LP at MID CAN legally intercept SURFACE→PERISCOPE attacks.
- Prior iter-6 claim "LP at MID is a complete defensive blank vs SURFACE attackers" was wrong.
  The observed blanking was caused by an adapter bug: `_can_intercept` in depths_adapter.py used
  `depth_difference(attacker.band, blocker.band)` (diff SURFACE/MID=2 > 1 → rejected) instead of
  the engine rule `depth_difference(target.band, blocker.band)` (diff PERISCOPE/MID=1 ≤ 1 → legal).
- **Fix shipped iter-10**: `_can_intercept` now accepts `target_band` and all callers pass the
  attack target's depth band. LP at MID will correctly intercept SURFACE→PERISCOPE attacks.
- **Strategic implication**: LP at MID absorbs ~3 drone hits before dying (hull=3). Deploy LP T1-T2,
  let it act as the wall. No need to manually surface it to PERISCOPE (that was wrong guidance).

**Wolf at the Door confirmed strong T6-T8 deploy**:
- DEEP homing (power 3, effective at full vs PERISCOPE despite depth) + hull=4 makes it resilient.
  P2's final dead-cat-bounce included Wolf contributing meaningful hits. Elevate Wolf's priority in
  the deployment order when Snorkel is not in hand by T4.

**Iter-10 suggested opening with LP**:
- T1: LP ({1S}) — deploys at MID (correct, within PERISCOPE intercept range). No TC cost.
- T2: Snorkel Stalker ({2T}) at PERISCOPE. Flagship clock starts T3 (4 dmg/turn).
- T3-T5: LP absorbs 1-2 SURFACE drones/swing (now that adapter bug is fixed). Snorkel chips.
- T6-T7: If VSL appears on Carrier side, escalate SC detection immediately (VSL = 2 dmg/drone).

**Phantom as T9 emergency play**:
- Type-XXI Phantom (5/4, {4T,2S}, DEEP, homing+SR): deals 5 homing damage/turn from DEEP.
  When P1 SC < 5, Phantom is effectively undetectable. In games where LP opener is not drawn,
  deploy Phantom T9-T11 as the primary clock alternative. Do not hold it as theoretical late-game.

**Iter-11 plan**: this will be the first clean LP opener test with (a) harness fix active,
(b) LP intercept adapter fix active, (c) seeded LP in P2 opener. Critical matchup data pending.

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
