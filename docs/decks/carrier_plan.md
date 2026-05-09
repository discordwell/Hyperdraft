# Carrier — Plan

## Composition summary

30-card SUBS drone-swarm list (`SUBS_carrier` in
`src/cards/depths/submarine_fleet/decks.py:158`):

- **Cheap Drone bodies (12)**: 4 Pilot Cadet (1/1 {1T}), 4 Patrol Bomber
  (2/1 homing {2T}), 2 Recon Drone (2/1 draw-on-death {1T}), 2 Skipjack
  Drone (2/1 spawn-on-death {1T}).
- **Carriers (7)**: 4 Escort Carrier ({3T} 1/5, +0/+1 anthem, 1 ETB Drone
  + 1 Drone/end phase), 2 Fleet Carrier "Hiryu" ({4T,1S} 2/6, 2 ETB Drones
  + 2 Drones/end phase), 1 Light Carrier "Shoho" ({3T} 2/4, ETB + on-attack
  Drone, +0/+1 anthem).
- **Crew (5)**: 2 Veteran Squadron Lead (+1/+1 to Drones), 2 Drone Pen Mate
  (+1/+0 to each new Drone deployed by host Carrier), 1 Air-Sea Coordinator
  (+0/+1 to all Drones at end phase).
- **Mid bodies (4)**: 3 Escort Frigate ({2T} 2/2 reach), 1 Heavy Cruiser
  Escort ({3T,1S} 4/4 reach).
- **Finishers (2)**: 1 Fleet Admiral Yamamoto ({6T,2S} 3/8, 3 Drones/turn +
  homing grant), 1 Crash-Boat Pilot ({2T} 2/2, suicide-4-damage when attacks
  Flagship).

**Curve shape**: 12 1T bodies, 7 3T+ Carriers, Crew at 1-2T. TC-heavy;
SC needed only for Hiryu ({1S}) and Yamamoto ({2S}).

**Sonar lean**: very light SC budget. Detection ability is minimal — the deck
does NOT win the detection sub-game; it wins the volume sub-game by presenting
more targets than the AI can afford to detect.

## Win condition

**Primary**: Drone saturation — deploy more 2/1 bodies per turn than the AI
can spend Sonar detecting. Undetected Drones deal damage directly to the
Flagship. With 3-5 Drones attacking simultaneously, even partial detection
still lands 4-6 hull damage/turn. Target: Flagship at 0 hull by T12-T16.

**Secondary**: Carrier engine stability — once a Carrier lands (T3), it
produces 1-2 Drones per end phase, replacing losses and widening the board
without spending hand cards. The AI needs to kill the Carrier or the drone
flood never stops.

**Target lethal turn**: T12-T18 depending on detection pressure. Faster if
AI over-detects individual Drones; slower if AI banks SC and surgically
intercepts carries.

## Key cards and roles

- **Skipjack Drone / Recon Drone** ({1T} 2/1): the cheapest attackers. Deploy
  T1-T2. These are sacrificial — they force the AI to spend SC detecting or
  take free chip. Skipjack's death trigger creates another Drone (replace-on-
  death anti-detection measure). Recon draws a card on death (card advantage
  when intercepted). Both are value-positive even when destroyed.
- **Pilot Cadet** ({1T} 1/1): the most expendable body. Deploy early to tax
  detection budget. Does NOT clear the MEDIUM_MIN_ATTACK_DAMAGE=2 threshold
  alone — needs a Carrier anthem (+0/+1) to swing for 2. Priority-2 deploy;
  Recon/Skipjack first when TC is scarce.
- **Patrol Bomber** ({2T} 2/1 homing): the reliable Flagship hitter. Homing
  negates depth-band penalties vs Flagship. Deploy when TC=2 available. The
  workhorse mid-game attacker.
- **Escort Carrier** ({3T} 1/5): the engine piece. Priority-1 play T3-T5.
  ETB creates 1 Drone immediately, then 1/end phase. Anthem (+0/+1) makes
  all your Drones survive one more combat trade. Deploying even one Carrier
  doubles your drone production rate.
- **Escort Frigate** ({2T} 2/2 reach): defensive body. Use to intercept
  Snorkel Stalker or other stealth attackers that the AI's defense might miss.
  Also attacks Flagship reliably at power 2.
- **Crash-Boat Pilot** ({2T} 2/2): special case — auto-deals 4 unblockable
  damage to the Flagship AND sacrifices itself the first time it attacks
  (fires unconditionally, no hull threshold). Deploy only when you are ready
  for it to fire immediately. Do NOT deploy into a turn where your Flagship
  attack is suicidal. The sac is not optional — it triggers on any Flagship
  attack regardless of board state.
- **Veteran Squadron Lead** (Crew, {2T,1S}): the lord card. +1/+1 to all
  your Drones elevates 2/1 Drones to 3/2, clearing most enemy 2-power
  interceptors. This is the pump that breaks the LP/Stalker Sub wall. Attach
  ASAP once you have the SC.

## Mulligan policy

**Auto-keep** (any of the following):
- 2× {1T} Drone + 1× {2T} body (Escort Frigate or Crash-Boat Pilot) → fast
  deployment start, Carrier to follow.
- 1× {1T} + 1× Escort Carrier + 1× Escort Frigate → engine plan with defense.
- 2× {1T} Drone + Fleet Carrier "Hiryu" in hand (plan to bank to {4T,1S}).

**Ship (mulligan)**:
- Hand with 0 cards costing ≤2T. Cannot deploy early enough to race.
- Hand with ≥3 Carriers and no cheap bodies. Engine pieces with no fuel.
- Hiryu-heavy hand with no cheap bodies (cannot deploy anything T1-T3).

**Opening hand analysis (current game)**:
- Skipjack Drone {1T}, Crash-Boat Pilot {2T}, Fleet Carrier "Hiryu" {4T,1S},
  Recon Drone {1T}, Pilot Cadet {1T} → **KEEP**. Three cheap bodies for T1-T3,
  Crash-Boat as finisher, Hiryu as long-term engine. Bank toward Hiryu T5-T6.

## How to beat Silent Hunter specifically

**The core challenge**: SH has Listening Post (0/3 wall that never dies to
2-power Drones without anthem), Stalker Sub (2/3 interceptor), and Snorkel
Stalker doing 4 dmg/turn to your Flagship while you try to chip theirs.

**Counter-strategy**:
1. **Kill LP with mass Drone targeting (iter-11 lesson)**. LP has power 0 — attacking it
   with 3+ Drones means zero return damage to your Drones. All 3 survive. LP dies in
   1-2 swings. This is far better than ignoring LP (lets it absorb your drones forever)
   or waiting for VSL (VSL requires SC you may not have). Execute LP kill as early as
   T3-T4 when EC spawns enough Drones. After LP dies, all future Drones hit the Flagship
   unblockable unless SH spends SC for detection. Prior guidance to "ignore LP" was wrong
   — target LP directly with 3+ Drones and remove it cleanly.
2. **Protect EC — do NOT use it as an interceptor (iter-11 critical lesson)**. EC at
   any hull value is the engine piece that produces all future Drones. Using it as an
   interceptor can kill it (AI interceptor assignment bug does this at ≤2 hull when no
   other options exist — encoder patch pending). Manual guidance: never assign EC as
   interceptor once its hull drops below 3. Consider diving EC to MID (1 SC) to move
   it out of the intercept pool entirely when at low hull.
3. **Deploy Patrol Bomber ONLY on a turn it can immediately attack (iter-11 lesson)**.
   Homing (bypasses depth modifier) makes PB a priority kill for P2. If PB sits
   for one turn after deployment, P2 will kill it via vessel-to-vessel targeting (a Recon
   at 1 power trades into PB's 1 toughness for free). Deploy PB in the Maneuver phase,
   then attack with it that same Engagement phase.
4. **Prioritize killing Snorkel Stalker** if the AI deploys it (their carry is
   4 dmg/turn). Use Escort Frigate (reach) to intercept Snorkel Stalker before
   it accumulates chip. If it's at PERISCOPE and you have reach, intercept it.
   One Snorkel Stalker kill is worth 12-16 hull damage saved over the game.
5. **Hit the Flagship, not the walls**. Width (5-6 attackers) forces the AI to
   spend SC detecting. At 2 SC/turn budget, detecting all your Drones is
   impossible — some will land. Saturate detection before it matters.
6. **Veteran Squadron Lead ASAP**. +1/+1 on Drones elevates 2/1 → 3/2.
   3-power attackers beat Listening Post (0/3) cleanly and KO most Stalker
   Subs. This is the deck's built-in answer to SH's 0-power chump wall.
   After LP is removed via Drone targeting, VSL-buffed Drones deal 2 effective
   per swing vs PERISCOPE Flagship (power 3, max(1,3-1)=2).
7. **Time Crash-Boat Pilot deployment carefully**. CBP sacs itself the first
   time it attacks the Flagship — unconditionally (iter-9 confirmed: fires at
   full 25 hull, no threshold). Deploy only on the turn you plan to attack
   with it. Combine with the drone swarm for a multi-threat alpha where the
   automatic 4 ignoring depth modifiers is guaranteed to connect.
8. **Never over-spend SC detecting any single target**. The SC starvation
   cascade (iter-8, confirmed again iter-11) is the most common way Carrier
   loses control. P1 spent 3 SC detecting Recon on T17 → SC=0 → Snorkel
   T19 alpha uncontested. Rule: never spend more than 2 SC/turn on detection
   unless the swing is clearly lethal. Keep 1 SC in reserve at all times.
9. **Race SH's Snorkel clock**. SH needs T3-T10 to land 25 hull damage at
   4/turn. Carrier needs T1-T3 cheap bodies eating detection budget, Carrier
   Engine T3-T5 doubling production. If Carrier is landing 6-8 chip/turn by
   T5-T8, SH can't bank SC and has to spend it detecting — breaking their
   grind plan.

**LP gate understanding (iter-11 lesson)**: LP is detection-gated, not passive.
P2 must spend 1 SC to detect your Drone before LP can intercept it. With SC income
~1/turn and 3 Drones attacking, LP fires at most 1 interception per swing when SC is
banked. If you keep 3 Drones attacking simultaneously, LP effectively blocks 1/turn —
the other 2 land uncontested. This is why LP kill (strategy #1 above) beats "send 4
drones to saturate LP" — removing LP entirely costs 2-3 Drone attacks; keeping LP
alive costs 1 Drone hit per turn for the rest of the game.

**Mulligan update (iter-11 lesson)**: The critical check is not "2 cards ≤2T" but
"at least 1 card at {1T}" specifically. Opening 3× Escort Frigate ({2T}) + 2 Carriers
is technically 3 cards at ≤2T but zero {1T} bodies. With no {1T} Drones, the deck
cannot force P2 detection spending on T1-T2. The fastest Carrier path needs at least 1
{1T} Drone (Skipjack, Recon, or Cadet) to threaten damage before P2's Snorkel
stabilizes. Revise auto-keep condition: must include at least 1 card costing {1T}.

## TC Management (iter-7 CRITICAL correction)

**Greedy {1T} deploy policy BLOCKS the Carrier engine.** Deploying a {1T} body
on T1, T2, and T3 means TC never accumulates past 1-2. Escort Carrier costs {3T}
— unreachable if you spend TC every turn on cheap bodies.

**Correct TC management line:**
- **T1**: Deploy one {1T} body (Skipjack, Recon, or Cadet). TC accumulates to 1.
- **T2**: BANK. No deploy. TC accumulates to 2.
- **T3**: BANK. No deploy. TC accumulates to 3.
- **T4**: Deploy Escort Carrier ({3T}) with TC=3. Engine online by T4.

**Alternative if already behind:**
- If T1-T2 were greedy deploys and TC=0-1, consider banking T3+T4 to land
  Carrier by T5. The 2-turn delay costs 2 drone bodies but enables the engine.

**Crew lord constraint**: Drone Pen Mate (CREW {1T}) requires a Carrier vessel
on the battlefield to attach to. It is completely dead if no Carrier lands. Do
NOT keep DPM in opening hand if no Carrier is in hand. Similarly, Veteran Squadron
Lead ({2T,1S}) needs TC=2+SC=1 available — unreachable until T8+ unless TC is
managed carefully.

**Iter-7 evidence**: Greedy deploys on T1-T5 left TC=0-1 throughout — Escort
Carrier never landed even after drawing it T1. Deck still won in 18 turns on
{1T} drones alone (P2 had no LP), but the Carrier engine was completely offline.
Against an ACTIVE detecting P2, the T14 7-attacker swing dealt only 3 damage —
width alone couldn't sustain. The engine is critical for sustained pressure
against a detecting defender.

## Style: aggressive drone-swarm

This deck plays greedy body deployment, **with TC management discipline**:
- **T1-T3: TC management first.** Follow the TC management line above before
  greedy deploying. Landing Escort Carrier by T4-T5 is the primary objective.
- **After Carrier lands: every turn deploy the best affordable body.** Once TC
  is generating Drones via Carrier, resume greedy mode.
- **Width over power.** 5 x 2/1 attackers > 2 x 4/2 attackers in the
  detection-cost game. Each Drone taxes 1 SC to detect; the AI has a fixed
  SC budget.
- **Fleet Carrier "Hiryu" at {4T}**: bank 1 additional turn after Escort Carrier
  if Hiryu is in hand. Not mandatory — Escort Carrier alone is sufficient.
- **Carrier placement priority**: Escort Carrier on T4 (after 2 bank turns) if
  opening TC=0; on T3 if opening TC≥1 (e.g. drew it first turn after a TC=1 T1).

## Cumulative-damage patch awareness (updated iter-7)

The detection patch (`MEDIUM_RECENT_DAMAGE_TRIGGER=4`, `MEDIUM_RECENT_DAMAGE_WINDOW=4`)
causes the AI to escalate detection when its Flagship has lost ≥4 hull in the last 4
turns. Confirmed active in iter-7: AI began detecting ~T12-T14 after taking ~7 hull
over 3 swing turns.

**Critical engine clarification (iter-7 CONFIRMED)**: The depth modifier (`max(1,
power - band_diff)`) fires for ALL combat — detected or not. The "2 damage from
SURFACE" that pilots observed in harness logs was the pre-pipeline event payload;
the actual damage applied to the flagship was 1. The harness log displays raw event
amounts before the transform interceptor modifies them. See `test_undetected_attack_depth_modifier`.

Track the AI's detection behavior:
- **Detection fires ~T12-T14 vs a 2-3 drone/turn chip rate** (iter-7 data). Earlier
  chip rates may trigger sooner with the wider 4-turn window.
- Depth modifier applies: a 2/1 Drone at SURFACE dealing to PERISCOPE flagship takes
  1 effective damage (not 2). Detection costs 1 SC. Detecting a 1-damage Drone is
  break-even; the AI will do it once chip stream is confirmed.
- **Width exploits detection limits**: 5 Drones × 1 SC detection = 5 SC to stop 5
  damage. With Carrier anthem online (Drones become 2/2+), effective power rises
  but detection cost stays the same — ratio tips in our favor.

## Iteration log

### Iter 6 (2026-05-07) — vs Silent_Hunter (heuristic-degraded P2)
**Won** in 17 turns, ME=25/25, OPP=0/25. Zero hull taken.

Drone-swarm line worked cleanly: 3-drone swings from T5 at 5 hull/swing, zero
AI detections across T5-T14. AI deployed LP at MID (wrong band for SURFACE
attackers) and never attacked. AI banked SC=6 at game end entirely unused.

Cumulative-damage patch UNDER-fired: MEDIUM_RECENT_DAMAGE_TRIGGER=6 was above
the 4-5 hull/turn drone chip rate, so escalation never triggered.
**Verdict: under-responding, not over-corrected.**

Patches applied based on this iter:
- `MEDIUM_RECENT_DAMAGE_TRIGGER` lowered 6→4
- `MEDIUM_CHIP_FORCE_DETECT=2`: force-detect top 2 attackers when chip stream active

Key findings:
- Crew lords (VSL, Drone Pen Mate) were inaccessible — harness `plan-deploy`
  refused them. Actual deck power untested. Fix: `plan-attach <crew> <vessel>`.
- Carriers (Escort Carrier, Hiryu) and Yamamoto were never cast — deck closes
  before T20 on {1T} drones alone. Top-end may be dead weight vs passive AI.
- **Open question**: does undetected SURFACE→PERISCOPE attack bypass depth
  modifier? Pilot A observed 2 damage (printed power) not 1 (formula: max(1,2-1)=1).
  Needs engine investigation.

**Open iter-7 question**: how does Carrier perform against an ACTIVE SH pilot
who detects from T5 and deploys LP at the correct band? This iter's SH was
passive — the real matchup test is pending.

### Iter 7 (2026-05-07) — vs Silent_Hunter (heuristic AI, chip-stream patch active)
**Won** in 18 turns, ME≈11/25, OPP=0/25.

This was the first iter where the chip-stream detection patch (MEDIUM_RECENT_DAMAGE_TRIGGER=4,
MEDIUM_CHIP_FORCE_DETECT=2) was active. Carrier still won, but the game was harder than iter-6:
- P2 began detecting ~T12-T14 (vs 0 detections in iter-6)
- A 7-attacker swing on T14 dealt only 3 damage (P2 detected+intercepted 4 of 7 attackers)
- ME took 14 hull damage (vs 0 in iter-6) — the patch IS constraining drone swarms

**ENGINE BUG — SUPERSEDED (iter-9)**: The iter-7 report claimed undetected attacks dealt full
printed power (bypassing depth modifier). This was INCORRECT — it was a library-zone homing
grant bug, not a detection-gating rule. Root cause: Fleet Admiral Yamamoto registers a QUERY
interceptor (homing grant) when added to the library; `has_ability(..., "homing")` scanned
`state.interceptors` without zone-gating, causing ALL P1 Drones to appear "homing" (depth
modifier skipped → raw 2 damage). Fix shipped iter-9: homing check in `_damage_modifier_handler`
now reads `characteristics.keywords` (printed/zone-safe) instead of `has_ability()`. Correct
rule: depth modifier fires for ALL combat, detected OR undetected. SURFACE→PERISCOPE =
max(1, 2-1)=1 effective damage (not 2). Revise all damage projections downward accordingly.

**Key iter-7 findings**:
- **Escort Carrier NEVER landed** — TC starvation from greedy {1T} deploys. Won without the
  engine. However, the T14 7-swing → 3 damage shows that against active detection, width
  alone isn't enough. The Carrier engine is needed for sustained pressure against detecting P2.
- **Skipjack Drone death trigger CONFIRMED**: Died to interception on T14, spawned a Drone
  token. First confirmed in-game fire of this trigger. Value-positive even when intercepted.
- **Escort Frigate (reach) killed Snorkel Stalker T12** — saved ~16+ hull damage. Reach
  interceptors are essential against SH's PERISCOPE carry.
- **Crew lords still untested**: VSL drawn T15 (too late), DPM held entire game (no Carrier
  to attach to). Need a game where Carrier lands T3-T5 to test lord effects.
- **SH without LP is much weaker**: P2 never deployed Listening Post. Without the 0/3 wall,
  drones attacked Flagship directly. The LP-less SH opener is a significant handicap.

**TC management fix needed**: Greedy {1T} deploys prevent Carrier from ever landing. Correct
line: T1 deploy {1T}, T2 BANK, T3 BANK, T4 deploy Escort Carrier with TC=3. Current
"always deploy" policy is broken for this deck's {3T} engine.

**Open iter-8 questions**:
- Can SH with LP wall + active detection from T5 stop the Carrier swarm?
- What happens when Escort Carrier + Drone Pen Mate are both online by T5?
- Does Veteran Squadron Lead's +1/+1 buff allow Drones to kill Listening Post (0/3)?
  With VSL: 2/1 Drones → 3/2 Drones. 3 power vs 3 toughness = LP survives but barely.

### Iter 8 (2026-05-07) — vs Silent_Hunter (LLM Pilot B, LP-T1 + Snorkel-T2 opener)
**LOST** in 17 turns, ME=0/25, OPP=18/25. Flagship sunk by P2.

This was the first matchup with an ACTIVE SH LLM pilot (Pilot B) applying the LP+Snorkel
T1/T2 opener. Carrier (P1, LLM Pilot A) followed EC-by-T4 directive. Two compounding bugs
decided the game:

**Bug 1 — CRITICAL: EC Drone token depth-band = UNKNOWN → 0 damage all game.**
All ETB and end-phase Drone tokens from Escort Carrier appeared at `?`/UNKNOWN band.
Every attack executed but dealt 0 damage to P2 flagship. Root cause: `_handle_object_created`
in `src/engine/pipeline/handlers/zone.py` did not read the `depth_band` payload key set by
`_create_drone_event` in `carrier.py`. **Fix shipped this pass (iter-8 coach)**: zone.py
now reads `depth_band` from the payload and sets it on the new object's state. Also falls back
to `card_def.depths_default_depth`. Both DRONE_TOKEN template (SURFACE) and `_create_drone_event`
(SURFACE default) would have produced correct tokens if zone.py had read the key.
The Skipjack Drone death-trigger token (confirmed working iter-7) used the same code path —
investigating why it worked previously; likely the depths entry interceptor caught it via
ZONE_CHANGE downstream while Carrier tokens were pure OBJECT_CREATED with no follow-up.

**Bug 2 — AI interceptor assignment: Escort Carrier used as Snorkel blocker.**
P1's heuristic assigned Escort Carrier (1/5 engine piece, 5 hull) as the interceptor for
Snorkel Stalker instead of a Drone (1 hull, expendable). This burned the Carrier to 1 hull
on T6; Recon killed it T7. Without the Carrier, drone production stopped and the anthem
(+0/+1) was lost. **Fix shipped this pass**: `_medium_interceptors` now sorts interceptors
with Carriers deprioritized (moved to end of candidate list), non-Carriers first.

**SC starvation cascade observed**: P1 spent 5 SC on T6 detection → SC=0 T7-T9 → 13 free
hull damage in 3 uncontested turns. **Fix shipped**: `MEDIUM_MAX_DETECT_PER_TURN=3` cap
added to `_medium_detections`; cap relaxes to 2× when near-lethal alpha is projected.

**Other findings**:
- EC deployed T4 as directed (TC banking T2-T3 worked; directive executed correctly).
- LP at SURFACE correctly intercepted SURFACE drones throughout (SH played correctly).
- Snorkel Stalker at PERISCOPE dealt 4 dmg/turn T3-T5 (12 dmg before EC landed).
- Air-Sea Coordinator attached to EC T6 — first Crew lord confirmed working in LLM game.
- EC killed T7 after 1-hull reduction; Drone production stopped.
- Without working tokens, Carrier was effectively a 2-3 body aggro deck — not enough to race
  SH's 4 dmg/turn clock.

**Verdict**: Both bugs combined made the Carrier engine non-functional this iter.
A clean iter-9 (token bug fixed, AI interceptor fix applied) is needed to get the true answer
to: "Can EC-by-T4 Carrier beat SH's LP+Snorkel opener?"

### Iter 9 (2026-05-07) — vs Silent_Hunter (LLM Pilot B, LP-T1 + Snorkel-T2)
**LOST** in 19 turns. Engine bugs fixed this pass; results now reflect true matchup dynamics.

Two bugs shipped as fixes this iter:
- **Homing grant library contamination (FIXED)**: `has_ability("homing")` returned True for
  all P1 Drones whenever Yamamoto was in the library, skipping the depth modifier and
  dealing 2 damage instead of 1 for SURFACE→PERISCOPE attacks. Fixed: `_damage_modifier_handler`
  now checks `characteristics.keywords` (zone-safe). SURFACE Drones correctly deal 1 damage vs
  PERISCOPE Flagship. Damage projection must be revised: 5 SURFACE Drones = 5 damage/swing
  (not 10).
- **No-interceptors detection guard (FIXED)**: iter-7 added a guard in `_medium_detections` that
  returned `{}` immediately if no ready interceptors existed — even when lethal threat was active.
  Fixed: guard now checks chip stream AND lethal projection before skipping. Detection fires
  correctly when projected damage > flagship_hull - MEDIUM_FLAGSHIP_LETHAL_BUFFER.
- **CBP sac behavior confirmed**: Crash-Boat Pilot sac fired T3 (full 25-hull Flagship). The
  trigger is unconditional — fires on ANY Flagship attack. 4 damage dealt and vessel sacrificed
  immediately. Plan updated: do NOT deploy CBP before the intended attack turn.

P2 (SH Pilot B) spent 0 SC detecting all game (banked SC=9+ throughout). P1 spent SC on
early detection then ran dry. Drone damage was 1/swing (not 2) after fix — half the previously
projected pressure.

**Open iter-10 questions**:
- Does the corrected 1-damage drone rate require 2× Carrier engine online to race SH's 4-dmg/turn
  Snorkel clock?
- Can Yamamoto's real homing grant (once he's on battlefield) close the gap — Patrol Bombers at
  full power despite depth penalty?
- What is SH vs Carrier win rate over N=5 clean games (both bugs now fixed)?

### Iter 11 (2026-05-09) — vs Silent_Hunter (LLM Pilot B, first clean LP-active game)
**LOST** in 23 turns, ME=0/25, OPP=2/25. First clean LP-active game (adapter fix, harness fix both active).

Key findings:
- **TC banking executed correctly**: P1 banked T1-T2 (no {1T} Drones in opening hand — 3× EF,
  Shoho, EC). Escort Carrier deployed P1 T3 (game T6). Engine online with 2 ETB Drones. Plan
  executed; result shows a hand without {1T} bodies is a suboptimal keep even with TC discipline.
- **EC killed by AI interceptor assignment at 1 hull (iter-11's decisive mistake)**: Defense AI
  used EC (1 hull after Snorkel combat) as interceptor for Stalker Sub on P2 T5. EC died.
  Non-EC interceptors were unavailable (tapped/dead). The Carrier-deprioritization sort from iter-8
  is insufficient — hard threshold ("never use EC at ≤2 hull as interceptor") is needed.
  Engine frozen at 3 Drones for turns 11-23 as a result.
- **LP kill with Drones confirmed correct**: Iter-11 P1 directed all 3 Drones at LP across 2 turns.
  LP power=0 → zero return damage. All Drones survived. LP died T14 (P1 T6-T7). This is the
  primary LP counter — faster and cheaper than waiting for VSL.
- **CBP alpha strike decisive**: Crash-Boat Pilot T1 T5 contributed 4 unblockable + 3 Drones = 8
  damage in one turn. P2 dropped 20→12. CBP is the deck's highest burst play.
- **Patrol Bomber killed before firing**: P2's Periscope Recon targeted PB directly (vessel-to-vessel
  attack) the turn after PB deployed. PB never attacked. Deploy PB only on a turn it can immediately
  swing.
- **VSL dead weight without EC**: Drew VSL T4 but EC died T5. VSL unplayable for the rest of the game.
  VSL is contingent on EC survival; protect EC above all other considerations.
- **Race math**: P2 at 2 hull at game end. Carrier nearly won despite EC death — the LP kill + CBP
  alpha were decisive. With EC alive and VSL attached, the math would have flipped.

### Iter 10 (2026-05-07) — vs Silent_Hunter (LLM Pilot B, blank-turn harness bug)
**Won** in 20 turns, ME=21/25, OPP=0/25. Fastest Carrier win in the series. **Data is not clean** —
P2's turns 5, 7, 9, 11, 13, 17 ran blank due to the `--seat` coordination bug (fixed this pass).
P2 only took ~4 meaningful turns. This win does not resolve the LP+Snorkel matchup question.

Key findings:
- **VSL attachment timing**: VSL attached to EC on T8 (2 turns after EC landed T6). The T8
  VSL-buffed 6-attacker swing dealt 11 hull damage. Recommended optimum: **attach VSL on T7** if
  TC=2 + SC=1 available. Every additional pre-VSL swing is running at half damage (1 instead of 2
  per drone). VSL T7 adds another doubled-output turn.
- **VSL doubles Drone output**: power 3 Drones → max(1, 3-1)=2 effective vs PERISCOPE Flagship.
  Detection value flips: detecting a VSL-buffed Drone saves 2 hull for 1 SC (excellent). Defenders
  should escalate detection immediately when VSL attaches. P2 iter-10 spent 0 SC on the T8 VSL swing
  with SC=4 available — decisive mistake.
- **Crash-Boat Pilot never drawn** this game. Not needed at 6-attacker VSL clock, but would have
  been a strong T6-T7 combined-alpha play if drawn. Keep in the 60.
- **LP intercept adapter bug (fixed this pass)**: the heuristic AI was never assigning LP at MID as
  a legal interceptor for SURFACE→PERISCOPE attacks. This is fixed. Iter-11 with LP active will be
  the first true test of whether the LP wall can stop Carrier drones.
- **Patrol Bomber early**: P2's Periscope Recon intercepted and killed Patrol Bomber on T5.
  The trade (kill 1/2 Recon, deal 1 extra Flagship damage, lose 2/1 Patrol Bomber) is neutral.
  Patrol Bomber's homing is valuable early precisely because LP+Recon defense cannot stop it.

**Iter-11 priorities**:
- Clean LP+Snorkel test with fixed harness and fixed LP intercept adapter.
- Aim for VSL on T7 (one turn earlier than this game).
- Expect LP to finally intercept 1-2 drones/swing — account for this in the attack-count math.
