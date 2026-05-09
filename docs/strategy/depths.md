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
- **CORRECTED (iter-9): depth modifier IS applied to all combat — but a library-
  registration bug caused it to silently skip for SURFACE→PERISCOPE attacks in iters
  6-8.** Root cause: `_damage_modifier_handler` in `src/engine/depths_combat.py` used
  `has_ability(src, "homing", state)` to decide whether to skip the modifier.
  `has_ability()` scans QUERY interceptors from `state.interceptors` WITHOUT zone-gating
  — so Fleet Admiral Yamamoto's "Drones you control have homing" QUERY interceptor
  (registered when Yamamoto was put in the library at game setup) was visible and
  matched all Drones controlled by P1, even Drones Yamamoto never grants homing to
  in actual play. Effect: every P1 Drone was treated as homing → modifier skipped →
  Drones dealt full printed power (2) instead of depth-modified (1) for SURFACE→PERISCOPE.
  **Fix (iter-9)**: `_damage_modifier_handler` now checks
  `"homing" in src.characteristics.keywords` (the printed/battlefield-static value)
  instead of `has_ability()`. Regression confirmed: hull delta is now 1 for an
  undetected non-homing SURFACE→PERISCOPE attacker, and 2 for a printed-homing attacker.
  Unit test added to `tests/test_subs.py`. The iter-7 "RESOLVED" conclusion
  ("harness display artifact") was incorrect — both pilots were observing real engine
  behaviour. Corrected here.
  **Strategic implication**: SURFACE drones deal 1 (not 2) to a PERISCOPE flagship
  when detected. Undetected non-homing drones also deal 1 (after fix). Detection cost
  (1 SC) is now break-even per drone intercepted at this range. Carrier's advantage
  is WIDTH, not undetected full-power hits.
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

- **SC starvation cascade (iter-8)**: spending your entire SC bank in a single
  detection turn leaves you with ~0 SC for 2-3 turns (resupply is 1/turn). A
  5-SC all-in detection turn → 5 free hull from undetected attacks the next turn.
  Budget SC detection: never spend more than 60% of current SC in a single turn
  unless it's the lethal swing. Saving 2 SC for next turn is worth more than the
  marginal detection on the current swing. Example: P1 spent 5 SC T6 detecting
  Snorkel+Recon → SC=0 T7-T9 → 13 free hull from uncontested Recon swarm in 3
  turns. Game-ending cascade.

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

- **PATCHED (2026-05-07, iter 10): `_can_intercept` used wrong band reference.**
  `_can_intercept(blocker, attacker)` in `depths_adapter.py` computed
  `depth_difference(attacker.band, blocker.band)`. For SURFACE attacker vs MID LP:
  `diff(SURFACE=0, MID=2)=2 > DEFAULT_INTERCEPT_RANGE=1` → LP rejected as interceptor.
  But the engine's `can_intercept` (depths_combat.py:381) uses the attacker's TARGET
  band (the PERISCOPE Flagship): `diff(PERISCOPE=1, MID=2)=1 ≤ 1` → LP is legal.
  This was the root cause of LP appearing useless in iters 6-10 — the adapter's
  heuristic refused to assign LP as an interceptor even when it was engine-legal.
  **Fix**: `_can_intercept` accepts an optional `target_band` param; all call sites
  (easy, medium, would-die-to-lethal check) now pass the attack target's depth band.
  LP at MID will now correctly volunteer to intercept SURFACE→PERISCOPE attacks.
  The LP-being-a-wall lesson is now unblocked for iter-11 testing.

(Each new ultra-loop run that surfaces a heuristic-specific exploit
goes here.)

## Settled lessons (resolved questions)

- **CONFIRMED iter-5 (N=2): Aggressive Silent_Hunter (T2 Snorkel
  Stalker + LP wall) outraces bank-discipline Wolfpack on a clean
  engine.** Iter-4 (first clean engine, all bug fixes shipped) was
  P2 W 20-0 in 17 turns. Iter-5 (repeat-confirm on the same matchup,
  same decks, no engine changes) is P2 W 12-0 in **10 turns** — even
  faster. Pilot B's plan: open LP T1 + Snorkel @ PERISCOPE T2 → 4
  dmg/swing T3-T5 (15 dmg in 3 turns) → flagship at hull 10 by T6 →
  cumulative-damage detection patch fires on schedule but P1's defense
  budget can't catch up → flagship sunk T10. Pilot A (P1) was forced
  into the iter-4 "abandon bank if opp races" exception clause; the
  exception itself loses (no anthem ever castable, Pack Leader 0/5
  cast streak across all iters). The bank-then-deploy lesson is now
  a settled-conditional: it WINS if opp is passive (iter-2/iter-3
  evidence — see Conditional lessons below), it LOSES if opp races
  (iter-4 + iter-5).

- **NEW iter-3: Saturation Strike timing tracks the OPPONENT's
  current SC pool, not nominal cap.** Pilot A's T25 lethal worked
  precisely because Pilot B had spent SC=6 on T23 detection and was
  sitting at SC=1 when Sat Strike hit. Cast on a turn where the
  defender has SC ≥ your attacker count = the +2 EOT buff is fully
  visible to the now-patched defense and gets surgically intercepted.
  Cast on a turn where defender SC < attacker count = lethal. This is
  the canonical Wolfpack kill-turn rule going forward.

## Conditional lessons (settled-when-X, contested-when-Y)

- **SETTLED-CONDITIONAL (iter-5 N=2 confirm): Bank-then-deploy is
  correct for top-heavy aggro decks ONLY when the opponent is
  passive.** When opp applies ≥4 hull/turn chip pressure starting T3,
  bank turns are unaffordable — the bank pilot loses tempo on a clock
  it cannot recover. Re-classified iter-4: result series under bug-
  influence: iter-1 (cost prop bug, greedy P1): L 0-1 in 38. Iter-2
  (cast_effect_fn fix shipped, defense pump-blind, bank P1): W 21-0
  in 28. Iter-3 (defense pump-aware, lethal-buffer wrong, bank P1):
  W 6-0 in 25. **Iter-4 (FIRST CLEAN engine, bank P1, aggressive P2):
  L 0-20 in 17.** **Iter-5 (clean engine repeat-confirm, bank P1,
  aggressive P2): L 0-12 in 10.** Engine layer is now stable across
  N=2; the matchup outcome is structural. Bank-then-deploy WINS if
  opp is passive; LOSES decisively if opp is aggressive. The bank
  rule's correctness is conditional on the opener-mix-vs-opp-tempo
  check, not on engine state.
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
  - **Iter-5 partial update**: Pilot B drew LP T1 + Snorkel T2 again.
    The "LP-and-race" opener appears to be the modal outcome of B's
    mulligan policy. If true, the variance is smaller than iter-4
    feared — the policy IS stable, the deck is just genuinely strong
    here. Future iters should test the no-LP/no-Snorkel B opener
    explicitly (force-mulligan harness) to settle this.

## Settled lessons (resolved questions)

- **CONFIRMED iter-11 (N=1 clean game): LP+Snorkel opener beats Carrier EC swarm.**
  SH won 2/25 hull remaining in 23 turns with LP at MID correctly intercepting (adapter
  fix confirmed working). The iter-10 question "Does LP+Snorkel race beat Carrier before
  VSL comes online?" is now answered: YES, SH wins if Snorkel lands by T4 and LP
  intercepts 1-2 drones/swing. Carrier's VSL must land by T7 with EC alive to contest
  this. N=1, so treat as provisional — a second clean game is warranted.

- **CONFIRMED iter-11: EC kill is a higher-priority target than Flagship chip when EC ≤2 hull.**
  Killing EC at 1 hull froze P1's drone engine for 12 turns. The engine kill was worth more
  hull-equivalent value than any 12 turns of direct Flagship chip would have been.

- **CONFIRMED iter-11: LP is detection-gated (REACTIVE), not static.**
  SC income (~1/turn) is the binding constraint on LP's usefulness, not its band position.
  Against 3 drones, LP can at most intercept 1/turn (costs 1 SC to detect). Any more
  requires banked SC. "LP absorbs 3 drone hits" requires 3 separate SC-funded detections.

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
  Pilot B's late game ran on autopilot. **FIXED iter-10**: `--seat` is
  now required in two-pilot mode; the harness refuses and prints an error
  if omitted. This prevents P1's agent from accidentally advancing P2's
  turn blank.

- **RESOLVED iter-11: Does LP+Snorkel opener race beat Carrier before VSL comes online?**
  YES — confirmed N=1 clean game (iter-11). SH won 2/25 hull with LP at MID intercepting
  (adapter fix active, harness clean). Snorkel landed T4 (delayed from ideal T2 due to draw
  variance), LP intercepted 1-2 drones/turn when SC was available. Carrier reached 2 hull
  before losing — margin is thin but the result is clear. VSL must land by T7 AND EC must
  survive for Carrier to contest this line. Reclassified to Settled once N=2.

- **NEW iter-11 (OPEN): Can Carrier win if VSL lands T7 and EC is protected?**
  Not yet tested. The iter-11 game saw EC die T11 to AI interceptor assignment (EC at 1 hull
  used as blocker for Stalker Sub — adapter bug, see Engine punchlist). With EC surviving and
  VSL at T7, P1's projected output doubles: 3 drones × 2 effective = 6 hull/turn vs SH's
  6-7/turn. The race may be close enough to flip. Iter-12 should force Carrier to: (a) never
  use EC as interceptor regardless of board state, (b) attach VSL T7. Compare hull totals to
  iter-11 to isolate EC survival value.

- **NEW iter-11 (OPEN): Can P2 deliberately drain P1 SC via Recon-bait targeting?**
  P2's Periscope Recon (SR keyword, detection cost 3 SC) was the direct cause of P1's T17
  SC bankruptcy. If SH can force P1 to detect Recon (via vessel-to-vessel targeting threats),
  the SC cascade fires automatically. Iter-12 should test whether this bait pattern is
  reproducible across different opener mixes.

- **NEW iter-5: Are post-fix balance numbers signs of over-correction?**
  Tournament data after all iter-1→4 engine fixes
  (`logs/depths_after_iter4_fixes.json`): Silent_Hunter 87.5%, Wolfpack
  53%, Carrier 22%, Deep_Strike 53%, Wolfpack_lean 34%. **Two specific
  candidates for over-correction**:
  - `MEDIUM_FLAGSHIP_LETHAL_BUFFER=3` (lowered from 5 in iter-4): a
    Carrier swarm of 4-5 attackers each dealing 1-2 dmg trips the buffer
    on every chip swing, getting shut down by single-detection
    interception. Carrier dropped 47% → 22% post-patch — too aggressive?
    Test: raise back to 4 and re-run tournament.
  - `default_depth` honoring buff: Snorkel Stalker now spawns at
    PERISCOPE = no penalty vs flagship + 1 attack-undetected pump = 4
    dmg/turn structurally guaranteed from T3 onward. Combined with the
    cumulative-damage patch firing late (T6 in iter-5, after 15 dmg
    already taken), the defender starts behind. SH winrate jumped to
    87.5%. Question: should Snorkel Stalker's printed power drop from
    3 to 2 to reflect its new always-at-PERISCOPE structural advantage?
  - **Combined hypothesis**: the cumulative-damage patch + lethal-buffer-3
    + default_depth honoring all stacked together. Each was an iter-N
    fix to a specific bug; the *combined effect* may have shifted the
    metagame more than any single fix would predict in isolation.
    Test: revert one at a time and re-run the 32-game tournament; pick
    the combo that lands all archetypes in 40-60%.

- **NEW iter-5: Is the matchup re-confirm (5 iters on the same matchup)
  duplicative or useful?** Iter-5 was a single-game re-confirm of
  iter-4's structural finding. The marginal value was: (a) confirmed
  the cumulative-damage patch fires earlier (T6 iter-5 vs T15 iter-4)
  with no game-breaking side effects; (b) confirmed Snorkel-at-PERISCOPE
  is structurally strong post default_depth fix; (c) noted Pack Leader
  0/5 cast streak. Cost: 1 LLM-pilot pair-game. The iter is *useful*
  but only marginally. Recommendation: pivot iter-6 to a different
  matchup (Carrier-vs-Wolfpack, or SH-vs-Deep-Strike) to cover unknown
  ground rather than re-confirming this one. See `iter-6 plan` below
  if added.

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

- **NEW iter-5 engine-tuning question (NOT patched this iter): the
  cumulative-damage patch may be over-corrected on Carrier-style
  swarms.** Tournament data (`logs/depths_after_iter4_fixes.json`)
  shows Carrier dropped 47% → 22% post-patch; iter-5 Pilot B observed
  P1 over-defending at T11 (burning SC=4-5 to kill a 3-power Coastal
  Raider when 0-cost LP could have chumped it). Easily tunable knobs:
  raise `MEDIUM_RECENT_DAMAGE_TRIGGER` from 6 → 8 (less sensitive to
  early chip), or raise `MEDIUM_RECENT_DAMAGE_WINDOW` from 3 → 4
  (smoother). Or revert `MEDIUM_FLAGSHIP_LETHAL_BUFFER` from 3 → 4
  (Carrier swarm shutdown buffer). DO NOT patch this iter — the
  iter-4/5 SH-vs-Wolfpack matchup is the cleanest evidence we have
  that the patches work; touching them risks losing that. Defer to
  iter-6 with explicit before/after tournament data.

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

- **RESOLVED (iter 7): Depth damage modifier confirmed working for SURFACE→PERISCOPE.**
  Both pilots reported "2 damage" from SURFACE Drone → PERISCOPE Flagship. Investigated
  in iter-7 coach pass. Root cause: `assign_damage()` in `src/engine/depths_combat.py`
  returns pre-pipeline events (raw amount=2); the pipeline transform interceptor reduces
  to 1 AFTER `assign_damage` captures the list. Actual `tgt_obj.state.damage` = 1.
  The harness combat log was printing the pre-transform event payload, not the
  post-transform damage applied. The modifier fires correctly for ALL combat, detected
  or undetected. Unit test `test_undetected_attack_depth_modifier` in
  `tests/test_depths_smoke.py` confirms and documents this. No engine fix needed.

## Pilot iteration log

- **2026-05-07 (iter 5)**: refined greedy + custom-depth Wolfpack (P1,
  LLM Pilot A) vs hybrid-aggressive Silent_Hunter (P2, LLM Pilot B).
  Same matchup, same decks as iter-1→iter-4. **P2 WON 19 turns,
  ME=12/25 vs P1=0/25** (Flagship sunk; harness reported turn 19 EOG,
  Pilot B internal log claims T10 lethal — discrepancy is either
  display lag or end-of-game cleanup turns; the win is real either
  way). Pilot A self-graded **4/10**; Pilot B self-graded **9/10**
  ("cleanest decisive win in 5 iters"). Iter-1→2→3→4→5: **L 0-1 (38)
  → W 21-0 (28) → W 6-0 (25) → L 0-20 (17) → L 0-12 (19)**. Iter-5
  is the second-clean-engine repeat-confirm of iter-4. Both engine
  fixes (cumulative-damage detection escalation; default_depth
  honoring) shipped iter-5 verified live in this run.
  Reframed iter-progression for the matchup:
  - **iter-1**: bug-influenced (cost prop bug).
  - **iter-2**: bug-influenced (cast_effect_fn fixed but defense
    pump-blind bug benefited Wolfpack's anthem alpha).
  - **iter-3**: bug-influenced (defense pump-aware now, but lethal-
    buffer wrong direction; Wolfpack again won marginally).
  - **iter-4**: FIRST CLEAN engine. Wolfpack lost 0-20.
  - **iter-5**: clean-engine repeat-confirm. Wolfpack lost 0-12.
  Conclusion: Wolfpack's iter-2/iter-3 wins were partially engine-bug-
  driven; the iter-4/iter-5 SH wins are the truth at engine equilibrium.
  Key surfaced lessons:
  - **Snorkel Stalker @ PERISCOPE post default_depth fix is
    structurally strong.** Pilot B confirmed the fix lands the spawn
    correctly without any SC dive cost. Saved ~8 SC across the game
    that flowed straight into the bank for surgical interception.
    Compounding effect with the cumulative-damage patch: SH wins by
    chip + has SC headroom for late surgical defense.
  - **Cumulative-damage patch fires correctly.** T6 detection trigger
    (vs iter-4 T15, vs iter-3 never). The patch shifts defender
    activation forward by ~9 turns. This is what was intended; iter-5
    confirms the patch works in practice.
  - **Pack Leader U-99 0/5 cast streak** — across all 5 iters of this
    matchup, with bank discipline AND with greedy aggression, Pack
    Leader has never landed. The {3T} slot is structurally unreachable
    for this deck on this matchup. Pilot A flagged for cut. **Decision
    deferred to iter-6**: tournament data shows the variant cutting
    the OTHER {3T} card (Sat Strike) lost 6-2 to base — cutting one
    card is already net-negative; cutting two might break the deck
    entirely. Mark as iter-6 candidate, do not ship now.
  - **Saturation Strike 0/5 cast in LLM games but tournament-essential.**
    `SUBS_wolfpack_lean` (cuts Sat Strike) is 34% vs base Wolfpack's
    53%. The card helps the heuristic AI (which can find the saturation
    swing) but not the LLM pilot (which can't budget around the bank
    rule). This is a strategic gap — the LLM pilot needs a sub-doctrine
    "cast Sat Strike on the first multi-vessel swing where TC≥2" rule
    that Pilot A has consistently failed to internalise across 5 iters.
  - **Listening Post survived again.** P1 never attacked it; LP exists
    as deterrent. Reaffirms the format-defining 0-power-chump role.
  - **The matchup-vs-strategy combo is now SETTLED at N=2 clean
    iters.** Future iters should pivot to other matchups (Carrier-vs-
    SH, Deep-Strike-vs-Wolfpack) to map the rest of the meta rather
    than re-confirm this one further.

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

- **2026-05-09 (iter 11)**: **Carrier (P1, LLM Pilot A) LOST 0/25 vs Silent_Hunter (P2, LLM Pilot B) WIN 2/25 in 23 turns.**
  First confirmed LP-active, harness-clean game. Both pilots reported consistent observations. Key updates:

  **LP gate behavior — CONFIRMED AND DOCUMENTED**: LP's intercept geometry fix (iter-10) is verified working.
  LP at MID correctly intercepted SURFACE→PERISCOPE Drones when the defense AI spent SC to detect first.
  LP fired 1-2 times total across the game — not because it was mispositioned, but because SC income
  (~1/turn) is the binding constraint. With 3+ drones attacking simultaneously, the AI cannot afford
  detection for every drone every turn, so LP only intercepts when detection is funded. LP is a
  REACTIVE wall (detection-gated), not a STATIC wall (passive auto-block). This resolves the
  iter-10 contested question: LP IS functional, but SC budget management is the true bottleneck.

  **EC kill priority — CONFIRMED HIGH VALUE**: Killing Escort Carrier at 1 hull (after Snorkel
  combat damage on T9) froze P1's drone engine at 3 Drones for the rest of the game (turns 11–23).
  EC at ≤2 hull is now a higher-value kill target than chipping the Flagship. Redirecting one
  attacker to finish EC saves ~6-8 drone bodies that would otherwise spawn.

  **SC starvation cascade — STILL LIVE**: P1 spent 3 SC detecting Periscope Recon on T17,
  leaving SC=0. Snorkel's T19 swing (4 damage) was uncontested. The cascade pattern persists
  even with MEDIUM_MAX_DETECT_PER_TURN=3 in place — the cap only applies to the AI, not to
  LLM pilots who may voluntarily over-spend.

  **Defense AI EC interceptor threshold bug — PERSISTS**: The Carrier-deprioritization sort
  (iter-8) was insufficient. When EC was the ONLY available interceptor (non-Carrier vessels
  tapped or dead), the sort had no effect — EC at 1 hull was still assigned. A hard threshold
  ("never use EC as interceptor if EC.hull ≤ 2") is needed in the encoder, not in BIAS_PRESETS.
  This is the single highest-impact remaining AI logic bug.

  **Patrol Bomber homing threat — CONFIRMED**: P2 killed Patrol Bomber on T17 before it could
  fire. Homing (bypasses depth modifier) makes PB a disproportionate threat. SH must answer it
  immediately. Carrier should deploy PB only on the turn it can attack.

  **Contested question resolved — "Does LP+Snorkel race beat Carrier?"**: YES, confirmed clean
  iter-11 (N=1, LP at MID active, LP intercept fix active). SH won 2/25 hull. Margin is thin —
  P1 reached 2 hull before losing. The matchup leans SH but is not a blowout.

  **New contested question**: "Can Carrier win if VSL lands T7 and EC is protected from
  interceptor assignment?" — not yet tested. Iter-12 should force Carrier to protect EC
  (never assign as interceptor) AND attach VSL T7.

  **Vessel-to-vessel targeting new format lesson**: P2's Periscope Recon (1/2) killed P1's
  Patrol Bomber (2/1) via direct vessel attack, not interception. This kill format is legal
  and tactically decisive — killing key attackers before they fire is the correct play.
  Carrier should assume any newly deployed homing attacker will be targeted next turn.

  **Heuristic constants stable**: no BIAS_PRESET changes this iter. The SC starvation cascade
  is an LLM pilot behavior pattern (not addressable via AI constants alone). The EC threshold
  bug is an encoder fix, not a constant change.

- **2026-05-07 (iter 10)**: Iter-10 entry. **Carrier (P1, LLM Pilot A) WON 21/25 vs 0/25 in 20 turns.
  Silent_Hunter (P2, LLM Pilot B) lost.** Harness blank-turn bug (fixed this pass — `--seat` now required
  in two-pilot mode) corrupted P2's game: turns 5, 7, 9, 11, 13, 17 ran blank. P2 took only ~4 meaningful
  turns. The LP+Snorkel opener test is still unresolved. Carrier win is real; matchup data is
  not clean.

  **Doctrine corrections (two pre-verified facts override iter-6/8/A analysis)**:
  - **LP band geometry — CORRECTED**: `can_intercept` in `depths_combat.py:381` checks
    `depth_difference(target_band, interceptor_band)` where `target_band` is the FLAGSHIP's
    PERISCOPE band. LP at MID: `depth_difference(PERISCOPE=1, MID=2)=1 <= DEFAULT_INTERCEPT_RANGE=1` →
    LP at MID CAN legally intercept SURFACE→PERISCOPE attacks. The iter-6 claim "LP at MID is a
    complete defensive blank vs SURFACE attackers" was wrong. LP's `default_depth=MID` is correct by
    design. **Strike all prior claims that LP must be at SURFACE.**
  - **AI interceptor bug found and fixed**: The adapter's `_can_intercept` (depths_adapter.py) used
    `depth_difference(attacker.band, blocker.band)` — the wrong operand. For SURFACE attacker vs MID LP:
    diff=2 > 1 → LP rejected. But the engine uses `depth_difference(target.band, blocker.band)` =
    `depth_difference(PERISCOPE, MID)=1 ≤ 1` → LP is legal. **This is why the AI never volunteered LP
    as an interceptor in iters 6-10.** Fix shipped: `_can_intercept` now takes an optional `target_band`
    param; all callers in the medium/easy/hard tiers pass the attack target's band. LP at MID will now
    correctly volunteer for SURFACE→PERISCOPE interception.
  - **Harness blank-turn bug (FIXED)**: `play-active-turn` without `--seat` in two-pilot mode ran
    whichever seat was active. P1's agent could advance P2's turn as a blank. Fix: `--seat` is now
    required in two-pilot mode; wrong-seat calls print an error and refuse. In `scripts/play/depths_wet_test.py`.

  **VSL (Veteran Squadron Lead) effect confirmed**:
  - VSL attached to EC on T8 boosted Drone power 2→3. Post-fix depth modifier (SURFACE→PERISCOPE) = 1,
    so effective damage: power-3 Drone = max(1, 3-1) = 2/swing. This doubled per-attacker output.
    Six-attacker swing dealt 11 hull damage (all undetected; P2 spent 0 SC despite having SC=4).
  - **Detection value of VSL-buffed Drones shifts**: detecting a 3-power Drone (2 effective) costs 1 SC
    and saves 2 hull — strongly value-positive for the defender (was break-even at power 2). Once VSL
    attaches, P2 should immediately escalate detection budget. P2 iter-10 failure to detect the T8 swing
    was the decisive mistake.
  - **Recommended VSL timing**: attach T7 (one turn after EC lands T6) not T8. Iter-10 attached T8 —
    T7 VSL would have doubled output one turn earlier.

  **Still open — LP+Snorkel vs Carrier clean test**: P2 never deployed Snorkel Stalker due to
  blank-turn cascade. The question "Can SH race Carrier when LP is active and AI intercepts correctly?"
  is now more urgent: with the LP intercept bug fixed, iter-11 is the first opportunity for a clean
  test. Recommend seeded LP in P2 opener.

  **Heuristic patches (iter-10)**:
  - `_can_intercept` target_band fix described above. This resolves the LP interception bug across all
    difficulty tiers.
  - `MEDIUM_RECENT_DAMAGE_TRIGGER` kept at 4 (VSL data corrupted by blank turns; deferring tightening).

- **2026-05-07 (iter 9)**: Iter-9 entry. **Re-run of Carrier (P1, LLM Pilot A) vs Silent_Hunter
  (P2, LLM Pilot B) with iter-8 fixes applied. P1 WON 11/25 vs 0/25 in 19 turns.**
  Token engine confirmed fully working (all Drone tokens at SURFACE, full damage delivered).
  EC never sacrificed as interceptor (AI fix confirmed). SC starvation cap (MEDIUM_MAX_DETECT_PER_TURN=3)
  not triggered — P2 spent 0 SC detecting across the entire game. LP was NOT in P2's opening hand
  (second consecutive iter without LP). The "no-interceptors" guard from iter-7 over-blocked
  detection: P2 had SC=9+ banked and never spent any despite Snorkel Stalkers dealing 4 dmg/turn.

  **Three fixes shipped this iter**:
  1. **Bug 1 (CRITICAL): No-interceptors guard revised.** The iter-7 guard
     (`_medium_detections` returns {} when no ready interceptors) is now conditional:
     returns {} only when no interceptors AND no chip-stream AND no lethal projection.
     When chip or lethal threat is present, detection proceeds (for reveal value).
  2. **Bug 2 (CRITICAL): Depth modifier was silently skipped.** `_damage_modifier_handler`
     used `has_ability(src, "homing", state)` which scanned all QUERY interceptors
     including library-registered ones (Fleet Admiral Yamamoto's homing grant, active
     from game setup before Yamamoto was ever played). All Carrier Drones appeared
     "homing" → modifier skipped → full printed power (2) applied instead of 1.
     Fix: use `"homing" in src.characteristics.keywords` (zone-safe printed check).
     Regression tests added.
  3. **Bug 3 (DOC only): Crash-Boat Pilot sac is unconditional.** No hull threshold.
     Fires on any Flagship attack. Updated carrier_plan.md.

  **LP absent two consecutive iters**: SH has drawn LP 0/2 iters in this matchup.
  True LP+Snorkel vs Carrier test still pending. Recommend iter-10 seeded hand.

- **2026-05-07 (iter 8)**: Iter-8 entry. **New matchup repeat: Carrier (P1, LLM Pilot A,
  EC-by-T4 directive) vs Silent_Hunter (P2, LLM Pilot B, LP-T1+Snorkel-T2 mandatory).
  P2 WON 18/25 vs 0/25 in 17 turns — first clean SH victory in the Carrier matchup.**
  Two compounding bugs crippled P1's engine:
  - **CRITICAL BUG FIXED**: EC Drone tokens spawn at UNKNOWN band → 0 combat damage.
    `_handle_object_created` in `src/engine/pipeline/handlers/zone.py` did not read
    `depth_band` from the OBJECT_CREATED payload. All Carrier drone tokens (ETB + end-phase)
    landed at depth_band=None; combat formula fell back to 0 damage. Fix: zone.py now reads
    `depth_band` payload key and also falls back to `card_def.depths_default_depth`.
    Regression test `test_carrier_etb_drone_spawns_at_surface` added.
  - **AI INTERCEPTOR BUG FIXED**: Carrier assigned as interceptor for Snorkel Stalker
    instead of an expendable Drone. `_medium_interceptors` now sorts Carriers to the end
    of the candidate list; non-Carriers always assigned first.
  - **SC STARVATION CASCADE DOCUMENTED AND PATCHED**: P1 spent 5 SC detecting on T6 →
    SC=0 T7-T9 → 13 free hull from uncontested Recon swarm. `MEDIUM_MAX_DETECT_PER_TURN=3`
    constant added; detection spending capped per turn (relaxes to 2× cap near lethal).
  - **COST CORRECTIONS**: Listening Post confirmed {1S} (not {1T}); Snorkel Stalker confirmed
    {2T} (not {3T}). Both plan docs updated.
  - **NEW format lesson**: SC starvation cascade added to Format-wide tactical patterns.
  - **Iter-9 plan**: clean retest of Carrier vs SH with token bug fixed and AI fixes applied.
    True answer to "Can EC-by-T4 beat LP+Snorkel?" requires bug-free engine.

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

- **2026-05-07 (iter 5)**: Iter-5 entry added. **Reframed the iter-1→5
  progression**: iter-1/2/3 were each engine-bug-influenced in distinct
  ways; iter-4 was the FIRST CLEAN engine result; iter-5 is the
  N=2 clean-engine repeat-confirm. Aggressive SH > bank Wolfpack now
  CONFIRMED at N=2. Bank-then-deploy reclassified from "settled iter-2"
  → "settled-conditional on opp passivity". **NEW contested questions
  filed**: are post-fix balance numbers (SH 87.5%, Carrier 22%) signs
  of over-correction? Two specific candidates (lethal-buffer 5→3
  possibly too aggressive; Snorkel Stalker @ PERISCOPE possibly too
  strong post default_depth fix). Engine fixes are NOT being reverted
  this iter — flagged for iter-6+ tournament re-run with one fix
  reverted at a time. **Pack Leader U-99 0/5 cast streak documented**
  but cut deferred (Wolfpack_lean variant data shows cutting one card
  already hurt 6-2; cutting two might break the deck).
- **2026-05-07 (iter 6)**: Iter-6 entry added. **New matchup: Carrier (P1) vs
  Silent_Hunter (P2)**. Outcome: Carrier won 25/25 vs 0/25 in 17 turns (zero
  hull taken by P1). P2 was partially degraded to heuristic autopilot due to
  a pickle-file race condition in the two-pilot harness (both pilots writing
  concurrently); result is indicative but not fully clean.

  **Key finding: cumulative-damage patch UNDER-fired vs drone swarms.** Despite
  4-5 hull/swing from T5 onward, the AI (P2) spent 0 SC on detection across 12
  turns. Root cause: MEDIUM_RECENT_DAMAGE_TRIGGER=6 was above the 4-5 hull/turn
  chip rate, so the chip-stream escalation never activated. In addition, even
  when recent_damage was added to cumulative_unintercepted, the lethal-buffer
  threshold (flagship_hull − 3 = 22 from full health) was far too high for a
  4-drone × 1-damage swing to exceed.

  **Patches applied (iter-6)**:
  - `MEDIUM_RECENT_DAMAGE_TRIGGER` lowered 6→4 (catches 4-hull/turn drone swarms).
  - `MEDIUM_CHIP_FORCE_DETECT = 2`: when chip stream is confirmed, force-detect
    the 2 most-dangerous undetected attackers BEFORE the lethal-projection loop.
    This prevents the "sitting idle while chipped to death" failure mode.
  - `plan-deploy` now prints a helpful error when the target card is CREW type,
    directing pilots to `plan-attach <crew_card> <target_vessel>`.
  - New regression test `test_medium_ai_detects_drone_swarm` added.

  **New format-wide lessons**:
  - Bank-SC-until-T8 is the WRONG doctrine vs Carrier swarm. Carrier builds a
    4-drone board by T5 and starts dealing 4+ hull/swing immediately.
    Against swarm archetypes: detection investment must begin T5, not T11.
  - ~~0-power LP deployed at wrong depth band (MID) vs SURFACE attackers is a
    complete defensive blank.~~ **RETRACTED (iter-10)**: LP at MID is within
    DEFAULT_INTERCEPT_RANGE of the PERISCOPE Flagship — it IS a legal interceptor
    for SURFACE→PERISCOPE attacks. The observed blanking in iter-6 was an adapter
    bug (`_can_intercept` used wrong operand), not a geometry rule. Bug fixed iter-10.
  - Crew lord effects (Veteran Squadron Lead, Drone Pen Mate, Air-Sea Coordinator)
    were never tested in LLM pilot games — harness Crew deployment fix pending.

- **2026-05-07 (iter 7, coach pass)**: Coach notes applied post-iter-7.
  **Patches**: (1) `MEDIUM_RECENT_DAMAGE_WINDOW` widened 3→4 to catch faster chip streams.
  (2) `_medium_detections` now skips detection when no ready interceptors are available
  (detection without interceptors = wasted SC, confirmed by T18 Pilot B observation).
  **Resolved**: depth modifier investigation closed — modifier fires correctly for ALL
  combat, detected or not. Harness logs printed pre-pipeline amounts. No engine fix.
  `_flagship_hull_history` pickle persistence confirmed OK (dill serializes instance
  variables correctly; Pilot B's hypothesis was incorrect). Pilot B's late firing was
  due to the 3-turn window being too small, not a reset bug. Tests added:
  `test_undetected_attack_depth_modifier`, `test_detection_without_interceptors_skips_detect`.

- **2026-05-07 (iter 7)**: Iter-7 entry. **Re-run of iter-6 with chip-stream detection patch
  applied (MEDIUM_RECENT_DAMAGE_TRIGGER 6→4, MEDIUM_CHIP_FORCE_DETECT=2). New matchup:
  Carrier (P1, LLM Pilot A) vs Silent_Hunter (P2, heuristic AI). P1 WON in 18 turns,
  ME≈11/25 vs AI=0/25** (Flagship sunk).

  **Chip-stream patch behavior (iter-7 confirmation)**:
  - Detection DID start this iter (~T12-T14 vs 0 detections in iter-6). Patch WORKS.
  - P2 began spending SC after approximately 7 hull damage accumulated over ~3 swing turns.
  - A 7-attacker swing (T14) was reduced from potential 14 damage to only 3 damage through
    detection + interception — the patch is now meaningfully constraining the swarm.
  - First detection: approximately T12-T14 (vs never in iter-6). Improvement confirmed.
  - **Still slow vs fast swarms**: Against 2-3 damage/turn chip rate, detection trigger
    fires ~6-8 turns in, not turn 3-5. Consider MEDIUM_RECENT_DAMAGE_WINDOW 3→4 to
    smooth the signal.

  **CRITICAL engine mechanic discovered (iter-7)**:
  - **Undetected attackers deal FULL printed power, ignoring depth modifier.** Skipjack
    Drone (2/1 SURFACE) consistently dealt 2 damage to the PERISCOPE Flagship when
    undetected — NOT max(1, 2-1)=1. The depth modifier formula applies ONLY to detected
    attackers. See updated Combat math section above. This changes swarm economics:
    SURFACE drones are full-power vs Flagship until detected.

  **LP absent this game**: P2 did not deploy Listening Post (may be deck-draw variance
  or heuristic policy). Without LP, 2-power drones attacked Flagship directly every turn.
  LP's absence was likely decisive for how fast chip damage accumulated.

  **Crew lords still untested**: VSL drawn T15 (too late, TC=1), DPM held entire game
  (no Carrier to attach to). Escort Carrier never deployed due to TC starvation from
  greedy {1T} deploys.

  **Key new format lesson**: Carrier wins on chip WITHOUT its engine if opponent lacks
  LP wall AND detection fires late. But the margin is thin — a 7-swing that only lands
  3 damage (T14) shows active detection nearly neutralizes width advantage. The Carrier
  engine (Escort Carrier + Drone Pen Mate anthem) is essential against a fully-active
  detecting opponent.
