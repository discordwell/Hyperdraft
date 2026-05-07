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

Grind. Out-detect and out-intercept the opposing aggro deck while
slowly chipping with stealth attackers (Snorkel Stalker, Bottom-Crawler
Probe, Type-XXI Phantom) from DEEP/MID where detection is expensive.
Ground-game slow win.

Realistic target: **lethal T20-T30** — this is genuinely a slow deck.
Pilot B's win at T38 is on-pattern, not anomalously slow. The deck is
allowed to cede early hull damage as long as it lands surgical
interceptions starting T13+.

## Target turns

- **T1-T7**: Build board. Deploy Listening Post for the 0/3 wall.
  Periscope Recon for the cheap stealth body. **Bank Sonar income** —
  do not spend SC on speculative detections.
- **T8-T13**: Detection economy comes online. By now the opponent has
  3-5 attackers on board and is starting saturation swings. Spend
  banked SC surgically — detect the highest-power attackers first,
  let chip damage from 1-power Subs through. Stalker Sub interceptors
  trade up.
- **T13-T20**: Snorkel Stalker comes down for the +1 power EOT
  attacking-undetected line. Type-XXI Phantom deploys to MID/DEEP for
  hard-to-detect chip damage on the opponent's Flagship.
- **T20-T35**: Grind. The opponent's deck either cracks (top-heavy
  aggro that can't reach its anthems) or stabilises and wins on
  finishers. If your deck reaches T25 with the opponent below 10 hull
  and you above 5, you win.

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
