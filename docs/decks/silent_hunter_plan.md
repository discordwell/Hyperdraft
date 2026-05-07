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

(Inferred — no Pilot B report.)

- **Auto-keep**: Listening Post + 1× {1T} unit + 1× {2T} interceptor
  (Stalker Sub or Probe). Sets up the wall + grind plan immediately.
- **Auto-keep (good)**: Listening Post + 2× cheap detection bodies.
- **Salvage**: Hand with no Listening Post but 2× early stealth bodies
  + Snorkel Stalker in the back. Race-as-control plan.
- **Auto-mull**: 0 cards costing ≤2T.

## Play priorities (order)

(Inferred from Pilot B's observed lines, Pilot A's narrative.)

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
- **Top-heavy aggro that BANKS into anthems** beats this deck — the
  deck assumes greedy aggro will brick its own top-end. If the
  opposing pilot disciplines the bank turn, the saturation swing comes
  online fully buffed and shreds the interceptor wall. (See contested
  question in `docs/strategy/depths.md`: "Greedy vs bank-and-hold for
  top-heavy aggro decks".)
- **Sonar Jammer currently dead** (engine bug). Effective deck size
  temporarily 28.
- **Combo decks (Deep Strike) outlast Silent Hunter on absolute
  resource accumulation.** Untested vs the new Pilot B line; a slow
  deck mirror likely turns on Snorkel Stalker reach vs Deep Strike's
  finisher count.

## Iteration log

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
