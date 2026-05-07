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
  damage to the Flagship when it attacks (ignores depth modifier). Spend it
  as a finisher on the "almost lethal" turn. Do NOT trade it into interceptors.
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
1. **Ignore Listening Post early**. 2/1 Drones attacking into a 0/3 wall is
   a losing trade (Drone dies, LP lives). Instead send Drones at the Flagship
   undetected while LP sits idle. LP can only intercept one attacker per swing
   — send 4 and it can at most clog one.
2. **Prioritize killing Snorkel Stalker** if the AI deploys it (their carry is
   4 dmg/turn). Use Escort Frigate (reach) to intercept Snorkel Stalker before
   it accumulates chip. If it's at PERISCOPE and you have reach, intercept it.
   One Snorkel Stalker kill is worth 12-16 hull damage saved over the game.
3. **Hit the Flagship, not the walls**. Width (5-6 attackers) forces the AI to
   spend SC detecting. At 2 SC/turn budget, detecting all your Drones is
   impossible — some will land. Saturate detection before it matters.
4. **Veteran Squadron Lead ASAP**. +1/+1 on Drones elevates 2/1 → 3/2.
   3-power attackers beat Listening Post (0/3) cleanly and KO most Stalker
   Subs. This is the deck's built-in answer to SH's 0-power chump wall.
5. **Deploy Crash-Boat Pilot on lethal turn**. When Flagship is at <4 hull,
   attack with Crash-Boat and get the automatic +4 ignoring depth modifiers.
   Combine with regular drone swarm for the closing alpha.
6. **Race SH's Snorkel clock**. SH needs T3-T10 to land 25 hull damage at
   4/turn. Carrier needs T1-T3 cheap bodies eating detection budget, Carrier
   Engine T3-T5 doubling production. If Carrier is landing 6-8 chip/turn by
   T5-T8, SH can't bank SC and has to spend it detecting — breaking their
   grind plan.

## Style: aggressive drone-swarm

This deck plays greedy body deployment:
- **Every turn, deploy the best affordable body.** Never skip a deploy turn
  unless TC=0.
- **Width over power.** 5 x 2/1 attackers > 2 x 4/2 attackers in the
  detection-cost game. Each Drone taxes 1 SC to detect; the AI has a fixed
  SC budget.
- **No bank turns** (unlike Wolfpack). The deck's top-end cards are Carriers
  at {3T} — achievable quickly without banking. Fleet Carrier "Hiryu" at {4T}
  is the exception; can bank 1 turn for it if Escort Carrier is missing.
- **Carrier placement priority**: Escort Carrier on T3 if TC allows; skip a
  cheap body that turn only if it means landing the Carrier.

## Cumulative-damage patch awareness (iter-6 mission)

The detection patch (`MEDIUM_RECENT_DAMAGE_TRIGGER=6`) causes the AI to
escalate detection when its Flagship has lost ≥6 hull in 3 turns. Track:
- If AI starts spending SC=3-5 to detect individual 2/1 Drones (power 2,
  depth modifier = 1 from SURFACE→PERISCOPE → 1 effective damage), that's
  over-detection. A 2/1 Drone at SURFACE deals max(1, 2-1) = 1 damage.
  Spending SC=1 to detect it is break-even; spending SC=2 is value-negative.
- Width exploits this: if AI is burning SC=5/turn detecting 5 Drones at 1
  damage each = 5 SC to stop 5 damage. Once Carrier anthem is online (Drones
  become 2/2+), each undetected Drone is now dealing 1-2 damage, but the
  detection cost is the same. The ratio tips further in our favor.

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
