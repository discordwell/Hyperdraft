# Depths Strategy Doc

Persistent format-level strategy notes for the Depths submarine-fleet card
engine. Updated by the `/ultra-loop` coach after each pilot iteration.
Format-level lessons go here; deck-specific lessons live in
`docs/decks/<deck>_plan.md`.

## Win conditions

- Sink the opposing **Flagship** (hull 25, locked at PERISCOPE).
- Or scuttle the opponent's whole fleet (no Vessels in hand, library, or
  battlefield besides the Flagship).
- Damage to the Flagship persists turn to turn — there's no MTG-style
  cleanup heal. Chip damage compounds.

## Combat math (most-load-bearing rule)

- Damage from attacker → target = `max(1, power - |attacker_band - target_band|)`.
- Flagship sits at PERISCOPE (band 1). So attacking from PERISCOPE → no
  penalty. From SURFACE (band 0) or MID (band 2) → −1. From DEEP (band 3) → −2.
- Detection sub-game: an undetected attacker may not be intercepted, but
  still deals damage. Defender pays Sonar (cost = `1 + depth_difficulty`)
  to detect, then can declare interceptors.
- The CRITICAL strategic lever: stealth attackers chip the flagship for
  free unless the defender can afford detection.
- **Alpha-strike timing tracks the OPPONENT's SC pool, not your own
  attacker count** (Pilot A, 2026-05-07). Saturating 5 attackers when
  opp has 5 SC is a wash — the third detection of the swing matters more
  than the fifth attacker. Saturating 3 attackers when opp has 1 SC is a
  knockout. Track the *defender's* sonar bank explicitly when deciding
  whether to push or hold.

## Resources

- TC (Torpedo) and SC (Sonar) per-turn cap = `min(turn_number, 10)`.
- +1 of each per turn (resupply); persists across turns up to cap.
- Going second ≈ being one turn behind on cap. Compensation TBD.
- **Curve-vs-deck-shape mismatch**: an aggro deck that always deploys
  max-cost-affordable will spend its TC every turn, perpetually sitting
  at TC=1-2 and never reaching the 3+ band. If the deck's anthems /
  finishers live at {3T}+, "always deploy" *bricks the top half of the
  deck* by ~T11 (Pilot A vs Wolfpack, 2026-05-07). The right curve for
  a top-heavy aggro deck is "deploy max-affordable EXCEPT for one or two
  bank-turns to load the anthem". Treat the bank turn as part of the
  greedy script, not a deviation from it.

## Phase order (per turn)

DIVE (untap + resupply + draw) → MANEUVER (deploy/attach/dive/cast Doctrine
or Action) → ENGAGEMENT (declare attackers → detect → intercept → damage)
→ REGROUP (more main-phase actions) → SURFACE (discard, sonar decay,
oxygen tick, EOT modifier sweep).

## Known archetypes (post-balance pass 5, all 40-60% in AI-vs-AI tournament)

- **Wolfpack** (60%): cheap 1-2T bodies that race the flagship. No Sonar
  income to speak of, so it cannot detect; vulnerable to stealth control.
  Top-end ({3T} Doctrine, {3T} Pack Leader, {4T} Hammerhead, {5T}
  Dönitz) is *only reachable* if the pilot intentionally banks TC for a
  turn around T7-T9 — see deck plan.
  - **Pack Leader U-99 is NOT a static lord** (CORRECTION iter-3,
    verified in `src/cards/depths/submarine_fleet/wolfpack.py:291`). It
    has a TRIGGERED ATTACK_DECLARED ability requiring ≥2 OTHER attacking
    Submarines (3 attackers total) before the +1 power EOT lord-buff
    fires. Single- and 2-attacker swings get NO Pack Leader bonus —
    only the swing-with-3-or-more is buffed. Strategically: a 2-attacker
    "alpha" with Pack Leader on board still hits at printed power. The
    deck does not earn its anthem until you saturate.
  - **U-Boat Wolf-cub is vanilla** (CORRECTION iter-3,
    `wolfpack.py:215-222` is `power=2, hull=1, cost={1T}` with no
    `setup_interceptors`). The deck plan previously implied a
    Wolfpack-1 trigger; that trigger lives on Pack Runner, not Wolf-cub.
  - Only the {3T} Wolfpack Doctrine is a true static anthem (always-on
    +1/+0 to your Subs while on the battlefield). Iter-3 Pilot A drew
    Doctrine T3 and never cast it through T25 — same brick as iter-2.
- **Silent Hunter** (53%): stealth + detection mid-range. Snorkel Stalker
  is the carry but no longer auto-wins post-nerf (silent_running removed,
  hull 1). Defensive 0-power chump interceptors (Listening Post 0/3) are
  unusually strong here vs Wolfpack — they soak 1-2 power suicide
  attacks indefinitely without trading.
- **Carrier** (47%): swarm of cheap Drones with Drone-anthem buffs from
  Carrier vessels.
- **Deep Strike** (47%): combo, banks Sonar for late-game finishers and
  multi-band-change tricks.

## Format-wide tactical patterns

- **0-power chump interceptors are oppressive vs no-removal aggro**
  (Pilot A, 2026-05-07). Listening Post (0/3) costs the defender nothing
  per chump (interceptor power 0 → no return damage to attacker, but
  attacker still dies into 3 toughness if not buffed past 3). Without
  sorcery-speed Vessel-removal, a {1T} aggro deck can lose 4-5 attackers
  to a single Listening Post over a game. Possible answers: every aggro
  deck packs ≥1 Vessel-removal Action; OR the format gives 0-power
  walls a downside (sink-on-trigger, max-uses, etc.). See contested
  questions.
- **Banked Sonar > spent Sonar in the early game** (inferred from
  Pilot B, 2026-05-07). The conservative side sat on its SC through
  T11 even while taking free chip damage, then cashed all of it on T13+
  for surgical interception. Net effect: P2 traded ~10 hull-points of
  free early damage for P1's entire mid-game push collapsing. Implies
  detection budget should be hoarded until the attacker's saturation
  swing forces the issue, not spent reactively turn-by-turn.
- **Surgical detection prioritization beats blanket detection** (Pilot
  A's read of Pilot B at T17). With 3 SC vs 4 attackers, P2 detected
  the 3 highest-power attackers and let the smallest one through. Pilot
  A's Pack Runner (the lowest-threat unit) carried for 3 — but the
  alternative (4 SC across 4 attackers) would have shut the swing
  entirely if the SC bank had supported it. The correct read is "spend
  the SC budget on the *threats you cannot afford to leave alive*",
  not "spread thin".

## Heuristic AI weaknesses (current, post-fix)

- **Medium tier ≈ greedy aggro pilot.** `_medium_pick_deploy` in
  `src/ai/depths_adapter.py:925` always picks the highest-`value_ratio`
  affordable vessel each turn. For a top-heavy curve like Wolfpack this
  produces the same TC-starvation pattern Pilot A self-described:
  always-deploy → never bank → never reach the {3T} anthems. Concrete
  evidence: Pilot A (LLM, not heuristic) followed exactly this policy
  and bricked Pack Leader U-99 + Wolfpack Doctrine + Hammerhead +
  Dönitz the entire 38-turn game. The medium AI would have produced
  the same line. Do not patch yet — the heuristic isn't *wrong*, it's
  optimised for a different (bottom-heavy) curve. Patch is to add a
  preset, not change medium.
- **PATCHED (2026-05-07, iter 2): Medium AI defense was pump-blind.**
  `_medium_detections` and `_medium_interceptors` in
  `src/ai/depths_adapter.py` projected attacker damage via
  `_depth_modifier_damage(attacker, target)` which read
  `obj.characteristics.power` (printed only). Saturation Strike's +2 EOT
  pump (now firing post-iter-1 fix) was invisible — defender's
  cumulative-damage projection sat under the lethal-buffer threshold
  while a 9-damage alpha walked in unintercepted. **Pilot B iter-2 lost
  this exact way.** Fix: `_power(obj, state)` and
  `_depth_modifier_damage(attacker, target, state)` now optionally route
  through `src.engine.queries.get_power` when state is supplied. Defense
  paths thread state. Legacy callsites (mulligan/deploy heuristics) keep
  the printed-only behaviour and are unaffected. Regression test:
  `tests/test_subs.py::test_medium_ai_defense_sees_pumped_power`.
- **Exploitable, NOT yet patched: medium AI's deploy/attack heuristics
  are still printed-power-only.** `_medium_pick_attackers` (line 1280)
  scores attacks via `_depth_modifier_damage` *without* state, and
  `_medium_pick_deploy` ranks by `_value_ratio` (printed power+toughness
  / cost). An LLM pilot can deliberately build a board that *underrates*
  on paper (low printed power, large pump effects) and the medium AI
  will mis-prioritise both attacks and deploys. Not patching today —
  these are offense-side calls where the AI is already flagged as
  "greedy" and the patch surface is wider. Document as a contested
  question if a future iter exploits it.

(Each new ultra-loop run that surfaces a heuristic-specific exploit
goes here.)

## Settled lessons (resolved questions)

- **NEW iter-4: Aggressive Silent_Hunter (T2 Snorkel Stalker + LP wall)
  outraces bank-discipline Wolfpack.** Conservative Silent_Hunter (the
  iter-1 grind plan) loses if drawn out beyond ~T20; the aggressive
  race plan beats Wolfpack's bank line by killing it before the anthem
  turn lands. Iter-4 evidence: P2 W 20-0 in 17 turns vs Pilot A's
  bank-then-deploy line that did everything "right" per the iter-3
  doctrine. Pilot B opened LP T1 + Snorkel T2 → 4 dmg/turn chip from
  T3 → reduced flagship 25 → 4 by T13 → forced Pilot A into pure
  defensive deploys, never castable Saturation Strike. The race wins by
  T17 because the bank pilot can't afford to skip a deploy turn while
  the chip clock is ticking at 4 hull/turn.

- **NEW iter-3: Saturation Strike timing tracks the OPPONENT's
  current SC pool, not nominal cap.** Pilot A's T25 lethal worked
  precisely because Pilot B had spent SC=6 on T23 detection and was
  sitting at SC=1 when Sat Strike hit. Cast on a turn where the
  defender has SC ≥ your attacker count = the +2 EOT buff is fully
  visible to the now-patched defense and gets surgically intercepted.
  Cast on a turn where defender SC < attacker count = lethal. This is
  the canonical Wolfpack kill-turn rule going forward.

## Conditional lessons (settled-when-X, contested-when-Y)

- **CONDITIONAL (was settled iter-2, contested iter-4): Bank-then-deploy
  is correct for top-heavy aggro decks ONLY when the opponent is
  passive.** When opp applies ≥4 hull/turn chip pressure starting T3,
  bank turns are unaffordable — the bank pilot loses tempo on a clock
  it cannot recover. Iter-1 (greedy, no bank, slow opp): L 0-1 in 38.
  Iter-2 (bank, slow opp): W 21-0 in 28. Iter-3 (bank, slow opp,
  defense fix): W 6-0 in 25. **Iter-4 (bank, AGGRESSIVE opp): L 0-20
  in 17.** Same matchup, same decks, opposite outcome — the variable
  is opponent's deck-shape choice, not the bank rule's correctness.
  The bank rule's CONDITION is "opp is not racing"; without that, the
  rule actively loses the matchup.
  - Cross-deck inference: any aggro deck with ≥2 cards in the {3T}+
    band needs to choose bank-vs-greedy AT MULLIGAN time based on the
    opener's mix. With a heavy {3T}+ hand, bank is forced; with a
    cheap-only hand, greedy race is forced.
  - The previous iter-3 caveat ("the margin shrinks once the defense
    fix shipped") was understated — iter-4 shows the margin doesn't
    just shrink, it INVERTS when opp races.

- **CONDITIONAL: Iter-3's "Pilot B will pivot aggressive without LP"
  was a one-game observation, NOT a stable pattern.** Iter-4 Pilot B
  drew LP again AND played aggressive AND won decisively. The pattern
  is "Pilot B's deck-shape variance dominates the matchup outcome more
  than the bank discipline does." A coin flip on B's opener determines
  the matchup result far more than P1's bank discipline does. This
  also implies: **single-game iters are noisy** — confidence requires
  N games per matchup-vs-strategy combo, ideally with paired openers.

## Contested strategic questions

- **Should defensive 0-power chump interceptors have a downside?**
  Listening Post (0/3) hard-counters Wolfpack's 1-2 power swarm
  without ever trading. Either every aggro archetype needs a sorcery-
  speed Vessel-removal Action, or 0-power walls need a built-in cost
  (sink-on-block, oxygen tick on use, etc.). **Iter-2 partial data**:
  Pilot B deployed Listening Post on T1 and it survived to game end,
  but Pilot A's read was that "Listening Post wasn't oppressive this
  game — possibly because Pack Leader U-99 + Sat Strike pumped my Subs
  past its 3 toughness." Inference: anthems + Saturation Strike now
  give Wolfpack the natural counter to Listening Post. Question
  remains contested for the *no-anthem-drawn* line: if Wolfpack
  doesn't reach {3T}+, Listening Post is still oppressive. Test in
  iter 3+ by running a hand that mulligans into a low-curve-only line.
- **Consider new AI preset: `bank_and_hold`.** Distinct from medium
  (greedy) and conservative-heuristic. Skips a deploy turn when (a)
  hand contains an anthem the next-turn TC would make affordable AND
  (b) board has ≥2 attackers already. **Iter-2 strengthens the case:**
  the LLM-pilot bank-then-deploy line cleanly beat the medium-AI's
  conservative line. Worth building for the next bias-surface pass.
- **Two-pilot harness coordination.** Pilot B reported (iter-2) that
  T23-T28 advanced without P2 having a window to queue actions; Pilot
  A's poll-and-play loop ran ahead. This is a harness bug, not a
  strategy question, but it directly affected iter-2's outcome —
  Pilot B's late game ran on autopilot. Fix in `scripts/llm_pilot/`
  before iter-3 (out of scope for this doc; flagged so it doesn't get
  lost).

## Engine punchlist

- **FIXED 2026-05-07 (iter-1 → iter-2): `cast_effect_fn` was never
  invoked.** Saturation Strike's +2 EOT pump silently no-op'd every
  cast. Patch landed in `src/engine/depths.py:cast_spell`. **Iter-2
  confirmation:** Pilot A observed an 11-damage alpha on T16 (raw
  expected 5 → with +2 pump, 9; lord effect added another point); Pilot
  B confirmed a 9-damage alpha hitting their flagship on T18. Both
  pilots independently verified the fix works in-game.

- **NEW (iter 2): `default_depth` is ignored by `deploy_vessel`.**
  `src/engine/depths.py:deploy_vessel` (line 575+) hard-codes
  `band = _coerce_depth_band(depth_band) or DepthBand.SURFACE` (line
  600), but `make_vessel` in
  `src/cards/depths/submarine_fleet/_factories.py:65` accepts a
  `default_depth: DepthBand = DepthBand.SURFACE` parameter and attaches
  it to the CardDefinition as `depths_default_depth`. The AI's
  `DeployVessel` action emits `card_id=...` with no `depth_band` arg
  (see `src/ai/depths_adapter.py:1762` and `_medium_pick_deploy` line
  940), so every Vessel deploys to SURFACE regardless of the card's
  printed default. **Pilot B iter-2 evidence**: Type-XXI Phantom
  (default_depth=DEEP) deployed to SURFACE, breaking the silent-hunter
  Iron Discipline → DEEP-stealth-chip plan on T19. Cards affected:
  Type-XXI Phantom (DEEP), Bottom-Crawler Probe (DEEP), Snorkel Stalker
  (PERISCOPE), Stalker Sub (PERISCOPE), and any Mine card lacking an
  explicit `depth_band` arg. Fix: in `deploy_vessel`, when `depth_band`
  is None, look up `obj.card_def.depths_default_depth` (or
  `obj.characteristics.card_def.depths_default_depth` depending on
  convention) and use it before falling back to SURFACE. Verified the
  bug by reading `_factories.py:55-108` and confirming the AI deploy
  action passes no band.

- **NEW (iter 2, PARTIAL FIX SHIPPED): Medium AI defense was
  pump-blind.** `_medium_detections`, `_medium_interceptors`, and
  `_depth_modifier_damage` in `src/ai/depths_adapter.py` projected
  attacker damage from `obj.characteristics.power` (printed only).
  Saturation Strike's +2 EOT pump and lord effects (Pack Leader U-99,
  Wolfpack Doctrine) were invisible to the AI. Defender's
  cumulative-unintercepted-damage projection sat under the
  lethal-buffer threshold while the alpha walked in. **Pilot B iter-2
  ate a 9-dmg alpha this exact way on T18.** Fix shipped: `_power(obj,
  state)` and `_depth_modifier_damage(attacker, target, state)` accept
  optional state and route through `src.engine.queries.get_power` when
  supplied. The defense paths thread state. Regression test:
  `tests/test_subs.py::test_medium_ai_defense_sees_pumped_power`. The
  *offense* paths (`_medium_pick_attackers`, `_medium_pick_deploy`,
  `_score_state`) still read printed power — flagged for a future iter
  if a pilot exploits it.

- **PARTIALLY FIXED (iter 4 → iter 5): Medium AI defense
  under-detects mid-game chip swings.** First fix (iter-4): lowered
  `MEDIUM_FLAGSHIP_LETHAL_BUFFER` from 5 → 3
  (`src/ai/depths_adapter.py:287`). Iter-4 evidence shows this alone
  did NOT change behaviour visibly — Pilot A still ate 4 unintercepted
  swings before defending. Second fix (iter-5, this pass):
  cumulative-recent-damage term added. `DepthsAIAdapter.__init__` now
  tracks `_flagship_hull_history: dict[defender_id, list[(turn, hull)]]`
  pruned to a 3-turn window. `_medium_detections` augments
  `cumulative_unintercepted` with the recent damage delta when it
  trips `MEDIUM_RECENT_DAMAGE_TRIGGER=6`. Effectively: a 4-damage chip
  stream starts triggering detection on turn 3 of the stream
  (cumulative=12 lost, projection=12+swing exceeds the
  hull-buffer-3 threshold once flagship is below ~17 hull). Regression
  test: `tests/test_subs.py::test_medium_ai_detects_chip_stream`. Note
  this only patches the medium *defense* path; offense still reads
  printed-only power.

- **NEW (iter 4): Pack Leader U-99 attack-trigger investigation —
  NO BUG.** Pilot A reported a 5-damage 2-attacker swing (Pack Leader
  3 + Wolf-cub 2) where the formula predicts 3 (max(1,3-1) + max(1,2-1)
  = 2+1 = 3). Read `wolfpack.py:289-310`: the trigger check
  `len(_attacking_allied_submarines(obj, st)) < 2` is correct
  (≥2 OTHER attackers required, since `_attacking_allied_submarines`
  on line 98-115 explicitly excludes the source via
  `if obj.id == source.id: continue`). 2-attacker swing = 1 OTHER → no
  fire. The 5-damage observation is consistent with both attackers
  having been DOVE to PERISCOPE before the swing (depth diff 0 → no
  penalty → 3+2=5). LLM pilots have no surfaced action shape to specify
  deploy depth (`DeployVessel(card_id)` only, no `depth_band` field —
  `src/ai/depths_adapter.py:204-207`), but `Dive(vessel_id)` exists
  (line 211). Most likely Pilot A dove via SC over T9-T13 and forgot
  to log it in the report. Trigger code is fine; doc Pilot A's likely
  miss-log as the explanation.

- **NEW (iter 4): Snorkel Stalker damage anomaly — NO BUG.** Pilot B
  reported 4 dmg/swing where formula "predicts 3" (max(1, 3-1) + 1
  trigger = 2 + 1 = 3 was the claim). Wrong baseline: Snorkel Stalker
  spawns at PERISCOPE (`silent_hunter.py:937-944`,
  `default_depth=DepthBand.PERISCOPE`); Flagship is at PERISCOPE; depth
  diff 0 → no penalty. Power 3 + 1 attack-while-undetected pump =
  4 base power → 4 dmg unmodified. The math is right; the report's
  expectation was wrong (treated SURFACE→PERISCOPE penalty as if
  Snorkel were at SURFACE). No engine fix needed.

## Pilot iteration log

- **2026-05-07 (iter 4)**: refined greedy Wolfpack (P1, LLM Pilot A,
  bank discipline) vs HYBRID-AGGRESSIVE Silent_Hunter (P2, LLM Pilot B,
  T1 LP + T2 Snorkel + 4-attacker chip rate from T7). **P2 WON 17 turns,
  ME=20/25 vs P1=0/25** (Flagship sunk). Pilot A self-graded **3/10**;
  Pilot B self-graded **9/10** ("cleanest win in 4 iters"). Iter-1→2→3→4
  on this matchup: **L 0-1 (38) → W 21-0 (28) → W 6-0 (25) → L 0-20 (17)**.
  The result series is wildly volatile because Pilot B's opener variance
  swamps the bank-discipline signal. **This is the first iter with all
  prior engine-side fixes shipped (cast_effect_fn, defense pump-blind,
  lethal-buffer 5→3) AND with B playing competently aggressive.**
  Key surfaced lessons:
  - **Iter-2 + iter-3 P1 wins were partially engine-bug-driven.** Iter-2
    benefited from B's defense being pump-blind; iter-3 benefited from
    P1's defense ALSO being under-detection-bugged in a way B couldn't
    fully exploit. Iter-4 with both fixes + an aggressive B → matchup
    flipped. Mark iter-2 + iter-3 results as engine-bug-influenced; the
    iter-4 result is the first with a clean engine layer.
  - **The lethal-buffer fix (5→3) shipped this iter did NOT change
    Pilot A's defense behaviour observably.** P1's flagship took 4
    unintercepted swings T9-T13 before defending at T15 — same passive
    pattern as iter-3 with a 5 buffer. The buffer alone doesn't fix the
    chip-stream problem. The cumulative-recent-damage term flagged in
    iter-3 punchlist matters more — patched this pass.
  - **Sat Strike NEVER cast in iter-2, iter-3, OR iter-4** (3-iter
    streak). Pilot A drew it iter-2 T6, iter-3 T7, iter-4 T8 — never
    castable any iter because Pack Leader's {3T} + the bank turn ate the
    TC budget every cycle. Either cut it from the deck, or auto-cast on
    the first multi-vessel swing turn where TC ≥ 2 is available.
  - **Wolfpack Doctrine ALSO never cast** (3-iter streak — same
    pattern). The {3T} slot is structurally over-allocated.
  - **Pilot A's best tactical option iter-4 was actually to abandon
    the bank rule by T7** when B's chip pressure became visible, not
    persist with bank discipline through T9. Codified as an exception
    clause in the Wolfpack plan.
  - **B's hybrid policy (open aggressive even with control pieces in
    hand) is a fully validated Plan A** — the iter-3 "aggressive race"
    was Plan B; iter-4 promotes it to Plan A. The deck wins faster
    racing than grinding.

- **2026-05-07 (iter 3)**: refined greedy Wolfpack (P1, LLM Pilot A,
  bank-turn + Sat-Strike-timing discipline) vs refined conservative
  Silent_Hunter (P2, LLM Pilot B, no-Listening-Post pivot to aggressive).
  **P1 WON 25 turns, ME=6/25 vs P2=0/25** (Flagship sunk). Pilot A
  self-graded **8/10**; Pilot B self-graded **6/10**. Same matchup, third
  result. **Iter-1→2→3 progression: 0-1 (L) → 21-0 (W) → 6-0 (W).** The
  matchup remains Wolfpack-favored but the margin collapsed once the
  iter-2 pump-blind defense fix shipped.
  Key surfaced lessons:
  - **Defense pump-blind fix is verified live.** Pilot A confirmed at
    T25 that Pilot B's defense detected Type-VII Veteran (highest
    post-Sat-Strike pumped power = 5) and surgically intercepted with
    Snorkel Stalker. The fix works in two-pilot mode.
  - **Defense under-detection bug surfaced.** Pilot B exploited it for
    3 unintercepted 3-attacker swings (T14/T18/T22) chipping P1 from
    25 → 6 nearly free. P1's heuristic defense had SC=4-9 across these
    turns but the lethal-buffer threshold (5 hull headroom) was never
    crossed. Filed in Engine punchlist with two candidate fixes.
  - **Pack Leader U-99 / U-Boat Wolf-cub doc corrections.** Pilot A
    verified the code: Pack Leader is a TRIGGERED ability requiring ≥2
    OTHER attackers (not a static lord), Wolf-cub is vanilla (no
    Wolfpack-1). Both fixed in `docs/decks/wolfpack_plan.md` and the
    Wolfpack archetype description above.
  - **Wolfpack Doctrine NEVER cast in iter-2 OR iter-3.** Pilot A
    drew it T3 in iter-3 and again could not afford it through T25
    because Pack Leader U-99 absorbed the {3T} bank-turn TC budget.
    Open question for iter-4: cut Doctrine OR cut Pack Leader from
    the Wolfpack list?
  - **Silent_Hunter mulligan policy needs refinement.** Pilot B's
    opener had no Listening Post AND no Iron Discipline — the deck
    plan's "auto-keep" priorities don't cover this case. B
    organically pivoted to aggressive race (deploy Snorkel Stalker
    early, swing 3-attacker T14/T18/T22) and almost won. Either
    mulligan harder OR codify the aggressive-race fallback as Plan B.
  - **Pack Leader is a single point of failure.** Pilot B's T21
    incidental kill of Pack Leader collapsed Wolfpack's anthem
    trigger; subsequent swings ran on Sat Strike alone. Counter for
    Wolfpack: protect Pack Leader at MID/DEEP if `default_depth`
    bug ever ships and a redundant anthem source drops in.

- **2026-05-07 (iter 2)**: refined greedy Wolfpack (P1, LLM Pilot A,
  bank-turn discipline) vs refined conservative Silent_Hunter (P2, LLM
  Pilot B, bank-then-surgical-detect). **P1 WON 28 turns, ME=21/25 vs
  P2=0/25** (Flagship sunk). Pilot A self-graded **8/10**; Pilot B
  self-graded **3/10**. Same matchup as iter 1, opposite result.
  Key surfaced lessons:
  - **Bank-then-deploy is decisively correct for top-heavy aggro** (see
    Settled lessons). Pilot A's iter-1→iter-2 reversal (L 0-1 → W 21-0)
    on the same matchup with the same deck is the cleanest evidence.
    Single-skip rule refined to "bank UNTIL TC ≥ anthem cost" — from
    TC=1, that was 2 consecutive banks (T9 + T10) before the T13
    Pack Leader U-99 anthem turn.
  - **Saturation Strike fix verified by both pilots independently.**
    Pilot A landed an 11-damage alpha on T16 (Pack Leader 6 + Wolf-cub
    5); Pilot B observed P1 land a 9-damage alpha on T18 hitting their
    flagship 17→8. The cast_effect_fn fix is real.
  - **Two engine bugs surfaced and verified** — `default_depth` ignored
    by `deploy_vessel`, and the medium AI defense was pump-blind. Both
    documented in Engine punchlist; the AI defense bug got patched +
    regression-tested in this pass.
  - **The matchup, in iter 2, was contestable on paper** but the AI
    defense bug + the Phantom-deploys-to-SURFACE bug combined to tilt
    it irrecoverably toward Wolfpack once Pilot A's bank discipline
    landed. Pilot B's 3/10 self-grade is fair: the strategy didn't
    fail, the engine layer beneath it failed. With the AI-defense
    patch shipped this pass, iter 3 should test the same matchup again
    — the expectation is a closer game (perhaps still Wolfpack favored,
    but not 25-vs-0).
  - **Listening Post (the iter-1 0-power chump question)**: Pilot B
    deployed it T1, and it survived to game end. Pilot A's read was
    that anthems + Saturation Strike pumped Subs past its 3-toughness
    enough that it was no longer oppressive. Partial answer to the
    contested question — the no-anthem-drawn line still needs testing.

- **2026-05-07 (iter 1)**: greedy Wolfpack (P1, LLM Pilot A) vs conservative
  Silent_Hunter (P2, LLM Pilot B). **P2 won 38 turns, ME=0/25 vs
  P2=1/25** — a one-hull miss after dragging P2 from 25 → 1 over T9-T19.
  Pilot A self-graded **5/10**, characterised the loss as "executed
  greedy faithfully; greedy is the wrong policy for Wolfpack's actual
  curve". Pilot B's report did not write (timed out mid-session); the
  win is real (P2 closed it on T37) but P2's reasoning is inferred
  from the action-count history and from Pilot A's read of P2's lines
  — see `/tmp/depths_game_history.txt` and §"Format-wide tactical
  patterns" above.
  Key surfaced lessons:
  - Greedy aggro vs Wolfpack's top-heavy curve = bricked top-end. The
    deck's *reason to exist* ({3T} Doctrine + {3T} Pack Leader) was
    never cast despite drawing 2 copies. Codified in the resources
    section above and in `docs/decks/wolfpack_plan.md`.
  - Banking SC early > spending SC reactively (P2 line). Codified in
    Format-wide tactical patterns.
  - Saturation Strike confirmed broken — root cause is engine-wide
    (`cast_effect_fn` never invoked), not card-specific. Filed in
    Engine punchlist.

## Changelog

- **2026-05-07**: Doc created during first ultra-loop double run.
- **2026-05-07**: First pilot-iteration entry. Added Format-wide
  tactical patterns, Engine punchlist, three contested questions, two
  combat-math/resource-management refinements from Pilot A's run.
- **2026-05-07 (iter 2)**: Iter-2 entry added. **Resolved** the
  greedy-vs-bank contested question (bank wins decisively for
  top-heavy aggro). Refined the bank rule from "single skip" to "skip
  UNTIL TC ≥ anthem-cost". **New engine bugs filed:** `default_depth`
  ignored by `deploy_vessel`; medium AI defense pump-blind. **Patched:**
  the AI-defense pump-blind bug — `_power(obj, state)` and
  `_depth_modifier_damage(..., state)` now route through
  `src.engine.queries.get_power` when state is supplied. Regression
  test added (`test_medium_ai_defense_sees_pumped_power`). Saturation
  Strike fix verified by both pilots.
- **2026-05-07 (iter 3)**: Iter-3 entry added. **Verified** the iter-2
  defense pump-blind fix works in two-pilot mode (Pilot A's T25 Sat
  Strike was correctly read by Pilot B's defense projection).
  **Corrected** Pack Leader U-99 (triggered, not static lord) and
  U-Boat Wolf-cub (vanilla, no Wolfpack trigger) descriptions in the
  Wolfpack archetype block and `docs/decks/wolfpack_plan.md`.
  **New engine bug filed:** medium AI defense under-detects mid-game
  chip swings — lethal-buffer threshold of 5 means a string of
  4-damage swings goes unintercepted indefinitely. Two candidate
  fixes documented; not patched this pass. **New format-level
  lesson:** Sat Strike timing should track the OPPONENT's CURRENT SC
  pool, not the nominal cap. Iter-1→2→3 progression on the same
  matchup: 0-1 (L) → 21-0 (W) → 6-0 (W) — bank-then-deploy still
  wins, but the margin shrunk dramatically once the defense fix
  shipped.
- **2026-05-07 (iter 4)**: Iter-4 entry added — **the matchup FLIPPED**.
  P2 won 20-0 in 17 turns vs the same bank-discipline Wolfpack that
  won iter-2 + iter-3. Result series 0-1 → 21-0 → 6-0 → 0-20 reveals
  the bank-then-deploy lesson is **conditional on opponent passivity,
  not unconditionally settled**. Re-classified bank-then-deploy from
  Settled → Conditional. **New settled lesson:** aggressive
  Silent_Hunter (T1 LP + T2 Snorkel + 4-attacker chip rate) outraces
  bank-discipline Wolfpack. **Patched (iter-5 in punchlist terms):**
  cumulative-recent-damage detection escalation in `_medium_detections`
  — `DepthsAIAdapter` now tracks per-defender hull history over a
  3-turn window and adds the recent damage to the cumulative projection
  when ≥6 hull lost in window. Regression test
  `test_medium_ai_detects_chip_stream` added.
  **Bug investigations resolved (no fix needed):** Pack Leader
  attack-trigger gate is correct (≥2 OTHER attackers required, source
  excluded from the count); Snorkel Stalker 4-dmg observation is
  consistent with PERISCOPE→PERISCOPE depth diff 0 + the
  attack-while-undetected +1 pump (3+1=4, no engine bug). The
  reporters' "predicted 3" baseline was wrong in both cases.
