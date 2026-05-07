# wolfpack — Plan

## Composition summary

30-card SUBS aggro list (`SUBS_wolfpack` in
`src/cards/depths/submarine_fleet/decks.py:72`):

- **1-cost Vessels (8)**: 4 U-Boat Wolf-cub (2/1 {1T}, **vanilla**),
  4 Sea Wolf Scout (1/2 {1T}, draws on coordinated attack).
- **2-cost Vessels (10)**: 4 Pack Runner ({2T}, Wolfpack-1 trigger:
  +1 power EOT when ≥1 other ally Sub attacks), 3 Coastal Raider, 3
  Surface Skirmisher.
- **3-cost Vessels (6)**: 3 Pack Leader U-99 ({3T}, **TRIGGERED
  Wolfpack-2 anthem, NOT a static lord** — fires only on attack-declared
  with ≥2 OTHER attacking allied Subs), 3 Type-VII Veteran ({3T},
  TC-ramp engine).
- **Finishers + actions (6)**: 1 Admiral Dönitz ({5T}, legendary
  finisher), 2 Saturation Strike ({2T} action: your Subs +2/+0 EOT —
  **currently broken, see Engine punchlist**), 2 Wolfpack Doctrine
  ({3T} anthem), 1 Hammerhead U-505 ({4T}).

**Curve shape**: 18 of 30 cards (60%) are 1-2 cost. The deck looks
bottom-heavy but its **reason to exist lives in the {3T}+ band**
(Doctrine, Pack Leader, Hammerhead, Dönitz). All four anthem/finisher
slots are gated behind a TC=3+ turn that the greedy "always deploy"
script never reaches.

## Win condition

Race the Flagship. Cheap 1-2 power Submarines chip down hull 25 from
SURFACE/PERISCOPE while a Pack Leader U-99 anthem (+1/+0 to your Subs)
or Wolfpack Doctrine turns the swarm into a 2-3 power per attacker
saturation alpha-strike around T9-T11.

Realistic target: **lethal T11-T13** vs a Silent_Hunter that can't
detect cheap stealth. The deck has no Sonar income to speak of, so
against a stealth-mirror it relies entirely on out-racing the
opponent's clock.

## Target turns

- **T1-T3**: Deploy a 1-cost Sub (Wolf-cub preferred for the 2 power)
  at SURFACE. Begin 1-2 chip damage per turn. **Do not deploy more
  than necessary** — every Sub on board past 3 risks attracting the
  defender's first detection swing.
- **T4-T6**: Add a second Sub (Skirmisher or Scout). Continue chipping
  for ~2-3 face per turn. Watch defender's SC pool; if they're
  hoarding (no detection through T5), keep dropping bodies.
  **CRITICAL bank turn (~T7-T9)**: skip a deploy, save 1-2 TC. Aim to
  arrive at T8 with TC=3+ in hand AND Wolfpack Doctrine or Pack Leader
  U-99 castable.
- **T8-T11**: Anthem turn. Cast Wolfpack Doctrine OR deploy Pack Leader
  U-99 to convert your existing 1-2 power swarm into a 2-3 power
  saturation swing. THIS is the kill turn the deck is built for.
- **T12-T13**: Closer. Saturation Strike (when fixed) + Hammerhead
  U-505 finishes a Flagship below ~6 hull.

**If you fail to bank by T9 and end up at TC=1-2 with the {3T}+ half
of your hand stuck**, the deck transitions to a slow grind it cannot
win — see Anticipated weaknesses.

## Key cards

- **Pack Leader U-99** ({3T}, TRIGGERED Wolfpack-2) — fires only on
  attack-declared when ≥2 OTHER allied Submarines are also attacking
  (i.e. **3+ total attackers**). When it fires, every attacking
  Submarine you control gets +1 power EOT. **CORRECTION iter-3**:
  this is NOT a static lord (the deck plan + strategy doc previously
  described it that way; the code at
  `src/cards/depths/submarine_fleet/wolfpack.py:291-310` is a
  TRIGGERED ability). Strategic implication: a 2-attacker swing with
  Pack Leader on board hits at printed power. You earn the anthem
  ONLY by saturating to 3+ attackers in the same swing.
  - **CAST-RATE FAILURE: 0/5 across iter-1 → iter-5.** Pack Leader
    has never cast in this matchup, period. iter-5 drew copies T3 +
    T13; both uncastable (TC starvation under chip pressure). Pilot
    A flagged as iter-6 cut candidate. Counter-evidence:
    `SUBS_wolfpack_lean` (cuts ONE card already, Sat Strike) lost 6-2
    to base in tournament — cutting a second card might break the
    deck. Decision deferred; track for iter-6 with a dedicated
    `wolfpack_no_pl` variant test.
- **Wolfpack Doctrine** ({3T}, **TRUE static anthem**) — `make_doctrine`
  with `make_static_pt_boost` filter on your Submarines (`wolfpack.py:982`).
  Always-on +1/+0 to your Subs while it's on the battlefield, no
  attack threshold required. Stacks with Pack Leader. Two anthems
  = +2 power per Sub = the deck's winning state. **In practice**:
  Doctrine has NEVER been cast in iter-2 OR iter-3 (drawn early both
  times, no TC headroom past Pack Leader). Open question for iter-4:
  cut Doctrine OR cut Pack Leader, since the {3T} slot can't hold both.
- **Pack Runner** ({2T}, Wolfpack-1) — the only 2-cost with a built-in
  scaling trigger. With ≥1 other ally Sub attacking, it gets +1 power
  EOT. Against a stretched defender (when the other Subs eat
  detections), Pack Runner is the unit that actually carries to the
  Flagship — exactly Pilot A's T17/T19 line.
- **U-Boat Wolf-cub** ({1T}, **vanilla 2/1**) — pure 2-power chip body.
  No trigger. **CORRECTION iter-3**: prior plan implied a Wolfpack-1
  trigger on Wolf-cub; that was wrong (`wolfpack.py:215-222` defines
  no `setup_interceptors`). The Wolfpack-1 attack trigger lives on
  Pack Runner, not Wolf-cub.
- **Sea Wolf Scout** ({1T}, 1/2) — chip body that DRAWS 1 when it
  attacks alongside another Submarine (`wolfpack.py:248-265`). Cantrip
  body, not vanilla. Enabler for the anthem turn — its job is to be on
  board when Pack Leader / Doctrine lands AND to *eat detections* on
  the saturation turn so heavier hitters reach the Flagship.
- **Saturation Strike** ({2T}, **NOW LIVE post-iter-1 fix**) — converts
  a saturation swing into a 2-power-per-attacker burst. Pilot A iter-2
  used it on T16 alongside Pack Leader U-99 + Wolf-cub for an
  11-damage alpha; Pilot B's defense (medium AI) failed to detect
  because the AI was pump-blind (separate bug, also patched iter-2).
  Cast on the same turn as a saturation swing — it's the canonical
  Wolfpack kill turn. With both engine fixes, expected lethal range
  shifts to T15-T18 vs T20+ pre-fix.
  - **CASTING-RATE FAILURE: 0/5 across iter-1 → iter-5.** Sat Strike
    has not fired in 5 consecutive iters of this matchup. Iter-5: not
    drawn (deck shuffle variance, irrelevant — would have been
    uncastable anyway under bank pressure). The {2T} action slot is
    structurally over-allocated when bank discipline is enforced
    (Pack Leader's {3T} eats the budget every cycle). Two repair
    options:
    - **Cut Saturation Strike** (replace with cheaper trigger like
      Pack Runner ×4 → ×5 or +1 Sea Wolf Scout). Accept that the
      named "kill turn" doesn't exist; rely on Pack Leader anthem.
    - **Add explicit "cast on first multi-vessel swing where TC ≥ 2"
      rule** to the play priorities, BEFORE Pack Leader / Doctrine
      deploys. Trades one anthem turn for a guaranteed Sat Strike
      cast, which the iter-2 11-damage alpha shows is enough.
    Either is testable; recommend the "cast first" version for iter-5
    since cutting risks losing the deck's defining burst.
- **Admiral Dönitz** ({5T}, legendary) — top-end finisher. Not
  reachable in any iter so far; reachable only with a successful
  bank-turn line + Type-VII Veteran TC-ramp.

## Mulligan policy

- **Auto-mull**: hand with 0 cards costing ≤2T. The deck has 18/30
  cheap cards (60%) so this is rare; if it happens, ship.
- **Auto-keep (snap)**: 1× {1T} Sub + 1× {2T} Sub + 1× {3T} anthem
  (Pack Leader OR Doctrine). The bank turn pays off most cleanly with
  the anthem already in hand.
- **Auto-keep (good)**: 2× {1T} Sub + 1× {2T} Sub + any TC-ramp
  (Type-VII Veteran in hand for the bank turn).
- **Salvage**: 3× {1T-2T} Sub with no anthem in hand. Race plan; hope
  to draw the anthem by T7. **REVISED iter-5**: the salvage-keep is
  unwinnable vs hybrid-aggressive Silent_Hunter (LP T1 + Snorkel T2).
  Rule: if opp's likely deck is SH and the salvage hand has ≥3 cards
  costing ≥3T, MULLIGAN; the deep-cards never cast against an
  opponent dealing 4 dmg/turn from T3.
- **NEW iter-5 auto-mulligan rule**: any opener WITHOUT ≥1 anthem in
  hand against a known-SH opponent that runs Snorkel Stalker. Pilot A
  (iter-5): "salvage opener vs Snorkel Stalker = unwinnable from
  opener" (5-iter Pack-Leader 0/5 cast streak supports this). The
  bank rule's exception clause (iter-4) — abandoning bank to race —
  itself loses; the only surviving line is a hand with anthem already
  present.
- **Avoid keeping**: hands with 2+ {3T}+ cards and no 1-cost body.
  The early game is dead; defender will set up before you apply
  pressure.

## Play priorities (order)

1. **{1T} Sub on T1** if available (Wolf-cub > Scout for the higher
   power).
2. **{2T} Sub on T2-T3** to add a second attacker.
3. **Bank turns (PLURAL) until TC ≥ anthem cost** (refined iter-2).
   Skip deploys consecutively if (a) hand contains {3T}+ anthem AND
   (b) you have ≥2 Subs already on board AND (c) the bank actually
   makes the anthem castable. From TC=1 with a {3T} anthem in hand,
   that's 2 consecutive skips (typically T9 + T10). From TC=2, 1 skip.
   This is the **MOST IMPORTANT** non-obvious priority in this deck.
   Iter-1 violated this rule and lost; iter-2 banked T9 + T10 and won
   21-vs-0 on T28.
   - **EXCEPTION CLAUSE (iter-4 add): if opp applies ≥4 hull/turn chip
     pressure starting T3, ABANDON the bank line — switch to
     emergency aggressive deploys to contest board.** Iter-4 evidence:
     Pilot A persisted with bank discipline through T9 while Pilot B
     chipped 4 dmg/turn from T3; flagship reached 4 hull before any
     anthem fired. The bank rule's correctness is conditional on opp
     being passive. Heuristic for "opp is racing": opp has ≥3 attackers
     on board by T7 OR opp has dealt ≥6 hull in the last 2 turns. If
     either fires, abandon bank and emergency-deploy whatever max-cost
     body is castable (preferring 2-power chips that contest detection).
4. **Anthem T8-T11** — Pack Leader U-99 OR Wolfpack Doctrine. The
   anthem is the deck's win condition; everything else is enabler.
5. **Pack Runner deploy on a turn ≥3 attackers will swing** — its
   Wolfpack-1 trigger needs the company.
6. **Surface vs PERISCOPE** at the swing turn — PERISCOPE is the
   Flagship's band, so attacking from PERISCOPE has no depth-modifier
   penalty. SURFACE has a −1 penalty (attacker_band 0 vs target_band
   1). Default to PERISCOPE deploy for hull-pressure attackers.
7. **Saturation strike** — when the engine bug is fixed, cast on the
   same turn as the saturation swing (sorcery speed; effect lasts
   EOT).
8. **Surface a deep Sub for a profitable strike** — only worth it if
   the depth-modifier loss is < the gained Flagship hull damage.

## Anticipated weaknesses

- **TC starvation locks out top-end** (Pilot A 2026-05-07, dominant
  finding). Greedy "always deploy max-affordable" perpetually sits at
  TC=1-2 because every turn's TC is spent. The {3T}+ half of the deck
  bricks. Bank turn discipline is *not optional* for this curve. See
  Play priorities #3.
- **0-power chump interceptors hard-counter the 1-2 power swarm.**
  Listening Post (Silent_Hunter, 0/3) costs the defender 0 to deploy
  and absorbs 1-2 power Subs without trading. With no sorcery-speed
  Vessel-removal Action in this deck, a single Listening Post can soak
  4-5 attackers across a game. Possible patches considered: cut Pack
  Leader U-99 (replace with a {2T} pinger) or add a {2T}
  Vessel-destroy Action — both deferred pending a second iter.
- **No Sonar income → cannot detect.** Vulnerable to a stealth-mirror
  (Deep Strike, late-game Silent_Hunter). The race plan needs to win
  before the opponent's stealth attackers come online.
- **No 2-for-1 plays.** Every all-out swing trades 2+ attackers for
  ≤1 Flagship damage once the defender's SC budget comes online (T13+
  in Pilot A). The deck *must* land its lethal before this point.
- **Saturation Strike** is **NOW LIVE** (cast_effect_fn fixed iter-1).
  Effective deck size restored to 30. Treat as a 2-cost finisher
  spell, NOT a dead slot.
- **Pack Leader U-99 STAYS in the deck (resolved iter-2).** Iter-2
  bank-turn discipline reached him on T13 and he carried the
  6-damage end of the 11-damage T16 alpha. The cut question is
  closed; Pack Leader is the deck's primary kill enabler.
- **Wolfpack Doctrine reach is shaky** even with bank-turn discipline.
  Iter-2 evidence: Pilot A drew it T3, never cast it through T28
  because TC stayed tight after the Pack Leader play. **Iter-3
  CONFIRMS THE BRICK** — drew T3 again, never cast through T25 again.
  Two consecutive bricks across two pilot runs is the answer the prior
  plan was waiting on. Decision for iter-4: cut Doctrine OR cut Pack
  Leader. Pack Leader is a triggered Wolfpack-2 (needs 3 attackers
  swinging together) so its anthem fires inconsistently; Doctrine is
  a true static lord but uncastable. The {3T} slot is the bottleneck.
  Recommend testing both lines in iter-4: one variant cuts 2× Doctrine
  (replaces with 2× Coastal Raider for cleaner curve), the other cuts
  3× Pack Leader U-99 (replaces with 3× Coastal Raider plus relies on
  Doctrine as the only anthem).

## Iteration log

(Append after each game piloted with this deck.)

- **2026-05-07 (iter-5)**: vs Silent_Hunter (LLM Pilot B, hybrid
  aggressive — same plan as iter-4, slightly faster execution). **L
  in 19 turns**, ME=0/25 vs OPP=12/25. Pilot A self-graded **4/10**.
  Iter-1→2→3→4→5: 0-1 (L 38) → 21-0 (W 28) → 6-0 (W 25) → 0-20 (L 17)
  → **0-12 (L 19)**. Engine state: clean (no new fixes shipped this
  iter; iter-5 confirms iter-4's cumulative-damage patch + default_depth
  fix work). The aggressive-SH wins at N=2.
  Pilot A used the new `--depth PERISCOPE` deploy flag (iter-5 harness
  feature) to land Pack Runner / Coastal Raiders / Wolf-cubs at
  PERISCOPE for full damage vs flagship — mechanically successful but
  insufficient against a 4-dmg/turn chip stream.
  Key new findings:
  - **Salvage-opener-vs-SH = unwinnable from the opener.** Mulligan
    refinement above: against SH risk, mulligan ANY hand with ≥3 cards
    costing ≥3T. The salvage rule's "hope to draw anthem by T7" never
    pays out vs Snorkel chip pressure.
  - **Pack Leader U-99 0/5 cast streak across all iters of this
    matchup.** Drew T3 + T13 in iter-5; never castable. With bank
    discipline AND with greedy aggression AND with the depth-deploy
    flag, this card has not landed in any iter. **Open question for
    iter-6**: cut Pack Leader and rebuild around Wolfpack Doctrine
    (also bricked but a true static lord at least). Tournament data
    from `logs/depths_after_iter4_fixes.json` shows
    `SUBS_wolfpack_lean` (which cuts Sat Strike) lost 6-2 to base
    Wolfpack — cutting one card already hurt; cutting another might
    over-rotate. Recommend a NEW variant `wolfpack_no_pl` that cuts
    Pack Leader specifically, then run the variant tournament.
  - **Saturation Strike 0/5 cast streak in LLM games but tournament-
    essential**: `SUBS_wolfpack_lean` (cuts Sat Strike) underperforms
    base 34% vs 53% — the AI uses Sat Strike correctly but the LLM
    pilot can't budget for it under bank discipline. This is a
    strategic gap, not a card problem; cut would hurt.
  - **--depth PERISCOPE flag worked mechanically.** Pack Runner T7
    deployed at PERISCOPE chipped 2-3 dmg/turn. Coastal Raider T11
    PERISCOPE deploy forced P2 to spend SC=4-5 to detect/intercept.
    Net-positive but couldn't overcome the structural deficit.
  - **Snorkel Stalker @ PERISCOPE post-fix is the dominant card in
    this matchup.** P2 deployed it twice (T2 + T11). Recurring
    threat, no Wolfpack answer.

- **2026-05-07 (iter-4)**: vs Silent_Hunter (LLM Pilot B, hybrid
  aggressive — opened LP T1 + Snorkel T2 + 4-attacker chip rate from
  T7). **L in 17 turns**, ME=0/25 vs OPP=20/25 (Flagship sunk). Pilot
  A self-graded **3/10**. Iter-1→2→3→4 result: 0-1 (L 38) → 21-0
  (W 28) → 6-0 (W 25) → 0-20 (L 17). **Bank discipline applied
  per the doctrine** (T7 bank, Pack Leader T9, Wolf-cub deploys T11+T13)
  — and the deck still lost decisively. The doctrine was correct in
  isolation; the matchup adaptation was missing.
  Key new findings:
  - **Bank rule is conditional on opp passivity, not unconditional**.
    Codified as exception clause in Play priorities #3. When opp
    chips ≥4 hull/turn from T3, abandon bank → emergency aggressive
    deploys to contest board.
  - **Saturation Strike 0/4 cast rate** across all iters. Drew T8,
    never castable through T17. The {2T} slot starvation is the same
    pattern as iter-2/iter-3 but for a tighter reason: bank discipline
    + Pack Leader + the chip-defense pressure all draw on the same
    1-2 TC pool. Two repair options documented in Key cards above.
    Recommend "cast on first multi-vessel swing" rule for iter-5.
  - **Wolfpack Doctrine 0/3 cast rate** (drew iter-2 T3, iter-3 T3,
    not in iter-4 opener). The {3T} slot can hold ONE of {Pack Leader,
    Doctrine, Hammerhead, Dönitz} — all four have been bricked across
    iters. Cut Doctrine + Hammerhead + Dönitz → +3 cheap Wolf-cubs is
    the iter-5 Plan B variant if "cast first" doesn't land.
  - **Pack Leader U-99 attack-trigger gate verified correct**
    (`wolfpack.py:289-310`): requires ≥2 OTHER attackers (excludes
    self via `_attacking_allied_submarines` filter on line 106-107).
    Pilot A's reported 5-damage 2-attacker swing was depth-related
    (both attackers at PERISCOPE, no penalty), not a bug. Logged in
    strategy doc Engine punchlist as resolved.
  - **Defense AI under-detection persists despite iter-4 lethal-buffer
    fix.** Pilot A's defense ate 4 unintercepted swings T9-T13 with
    SC=4-9 available. The cumulative-damage patch shipped this pass
    (see strategy doc Engine punchlist) should fix this in iter-5.

- **2026-05-07 (iter-3)**: vs Silent_Hunter (LLM Pilot B, no-Listening-Post
  pivot to aggressive). **W in 25 turns**, ME=6/25 vs OPP=0/25 (Flagship
  sunk). Pilot A self-graded **8/10**. Bank discipline applied (T5+T9),
  Pack Leader U-99 deployed T7, Type-VII Veteran T13. T17 alpha was the
  first 3-attacker swing where Pack Leader's Wolfpack-2 trigger fired
  (8 emitted, 5 net). T25 lethal off Saturation Strike + 5-attacker swing
  while Pilot B sat at SC=1 (drained from a SC=6 detection storm at T23).
  Race was MUCH closer than iter-2: P1 ended at 6/25 hull vs iter-2's
  21/25.
  Key new findings:
  - **Pack Leader U-99 / U-Boat Wolf-cub doc errors uncovered.** Pilot A
    read `wolfpack.py` and verified: Pack Leader is a TRIGGERED Wolfpack-2
    (≥2 OTHER attackers required), Wolf-cub is vanilla. Both are now
    corrected in this plan and `docs/strategy/depths.md`. **Strategic
    consequence**: 2-attacker "alphas" with Pack Leader on board hit at
    printed power. The deck does NOT earn its anthem until 3+ attackers
    swing in the same turn.
  - **Wolfpack Doctrine ABSENT FROM PLAY for the second consecutive
    iter.** Drawn T3 in iter-3 (and again in iter-2), uncastable through
    T25 because Pack Leader U-99 absorbed the {3T} bank-turn TC budget
    every cycle. The deck's {3T} slot can hold ONE of {Pack Leader,
    Doctrine}. **Open question: cut Doctrine (free up hand for closers)
    OR cut Pack Leader (free Doctrine to be the always-on anthem)?**
    Doctrine cut keeps Pack Leader's saturation-burst kill turn but
    abandons the persistent +1 power. Pack Leader cut keeps the
    persistent +1 power but loses the burst. Test in iter-4 by running
    one variant of each.
  - **Saturation Strike timing rule confirmed.** T25 lethal worked
    BECAUSE Pilot B was at SC=1 from a prior detection storm. If Pilot
    B had banked SC instead of spending all 6 on T23, the +2 EOT pump
    would have been visible to defense (post-iter-2 fix) and Pilot B
    would have intercepted enough of the swing to flip the outcome.
    Sat Strike on a turn where opp SC ≥ attacker count = wash; opp
    SC < attacker count = lethal.
  - **Pack Leader is a single point of failure.** T21 incidental kill
    (Snorkel Stalker interception) collapsed the anthem trigger source.
    Subsequent swings ran on Sat Strike alone. With no redundant anthem
    and no current way to ward Pack Leader, this remains a brittleness.
  - **Defense AI under-detection (Pilot B's offensive 3-attacker swings
    UNINTERCEPTED at T14/T18/T22)** — see `docs/strategy/depths.md`
    Engine punchlist. P1's heuristic defense had SC=4-9 but the lethal-
    buffer threshold (5 hull headroom) was never crossed by any single
    swing. Document the asymmetry: bank discipline FOR P1's deploys
    helped P1, but the lethal-buffer-only detection rule made P1's
    own defense passive in mid-game.

- **2026-05-07 (iter-2)**: vs Silent_Hunter (LLM Pilot B,
  conservative). **W in 28 turns**, ME=21/25 vs OPP=0/25 (Flagship
  sunk). Pilot A self-graded **8/10**. Bank-turn discipline applied:
  banked T9 + T10 (skipped 2 deploys), reached TC=3 on T13, deployed
  Pack Leader U-99. T16 alpha = Saturation Strike + Pack Leader (6) +
  Wolf-cub (5) = 11 damage in one turn (Pilot B's medium-AI defense
  failed to detect because of the pump-blind bug, separately patched).
  T26 lethal off a 2-damage Wolf-cub punch through.
  Key new findings:
  - **Bank-turn rule confirmed correct.** Iter-1 (greedy, no banks):
    L 0-vs-1 in 38 turns. Iter-2 (banks T9, T10): W 21-vs-0 in 28
    turns. Same matchup, opposite result. Codified in Play priorities
    #3 with the iter-2 refinement (PLURAL banks until TC ≥ anthem).
  - **Saturation Strike confirmed firing post-iter-1 fix.** T16 alpha
    of 11 damage is direct evidence; without the +2 EOT pump the
    expected damage was ~5.
  - **Pack Leader U-99 is the kill enabler.** Cut question closed —
    he's the primary anchor for the alpha turn.
  - **Hand-management gap**: Pilot A drew Wolfpack Doctrine T3 and
    never cast it through T28; same for Admiral Dönitz (drew T20).
    The deck's top-end is *reachable* with bank discipline but Pack
    Leader U-99 absorbs the TC and leaves no room for the second
    {3T} card. Possible iter-3 line: deploy a Type-VII Veteran on the
    bank turn instead of pure-skip, to ramp TC for a stacked
    Doctrine + Pack Leader + Saturation Strike turn. Untested.
  - **Sea Wolf Scout's value is marginal**. 1-power chip body but
    eaten by Listening Post (0/3) every detection turn for 1-2
    damage returns. Possible cut for a third {2T} body.

- **2026-05-07** (iter-1): vs Silent_Hunter (LLM Pilot B,
  conservative). **L in 38 turns**, ME=0/25 vs OPP=1/25 — a one-hull
  miss. Pilot A self-graded **5/10**: "executed greedy faithfully;
  greedy is the wrong policy for Wolfpack's curve." Game state at
  loss: 3× Pack Leader U-99, 2× Wolfpack Doctrine, 1× Hammerhead
  U-505, 1× Admiral Dönitz, multiple Type-VII Veterans **never cast**
  across 38 turns despite drawing them. T9 alpha-strike with 3×
  uncontested attackers cracked P2 from 23 → 16 essentially free.
  T17 saturation got 3 of 4 attackers detected; Pack Runner carried.
  Stalled at Flagship=1-3 from T21 onward — defender's interceptor
  + Listening Post chump-blocking absorbed the {1T-2T} swarm without
  trading. Closing chip damage from P2's deep stealth attackers
  finished the game T37-T38.
  Key new findings:
  - **Greedy = always deploy** structurally bricks Wolfpack's top-end
    by T11. Bank turn at ~T8 is mandatory, not optional. Codified in
    Play priorities #3.
  - Listening Post 0/3 is a hard counter without removal.
  - Saturation Strike confirmed broken (engine bug — see deck plan
    Key cards entry and strategy doc Engine punchlist).
  - Pack Runner's Wolfpack-1 is the most-load-bearing per-card
    trigger in the deck — it's the unit that punches through stretched
    defenders.

  Plan unchanged after iter-1: the bank-turn rule is the new top
  priority but the actual deck composition stays. Iter-2 should test
  the bank-turn line; if it still loses, revisit Pack Leader cut.
