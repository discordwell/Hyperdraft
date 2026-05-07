# wolfpack — Plan

## Composition summary

30-card SUBS aggro list (`SUBS_wolfpack` in
`src/cards/depths/submarine_fleet/decks.py:72`):

- **1-cost Vessels (8)**: 4 U-Boat Wolf-cub (2/1 {1T}), 4 Sea Wolf Scout
  (1/2 {1T} or similar — chip-damage body).
- **2-cost Vessels (10)**: 4 Pack Runner ({2T}, Wolfpack-1 trigger:
  +1 power EOT when ≥1 other ally Sub attacks), 3 Coastal Raider, 3
  Surface Skirmisher.
- **3-cost Vessels (6)**: 3 Pack Leader U-99 ({3T}, lord), 3 Type-VII
  Veteran ({3T}, TC-ramp engine).
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

- **Pack Leader U-99** ({3T}, lord) — the per-card EV anchor. Once on
  board, every other Sub gets +1 power, which is the difference
  between "1 power chip blocked by Listening Post forever" and "2
  power chip that punches through 0/3 walls in two hits".
- **Wolfpack Doctrine** ({3T}, anthem) — same +1 power but persistent
  global enchantment, AND it stacks with Pack Leader. Two anthems
  = +2 power per Sub = the deck's winning state.
- **Pack Runner** ({2T}, Wolfpack-1) — the only 2-cost with a built-in
  scaling trigger. With ≥1 other ally Sub attacking, it gets +1 power
  EOT. Against a stretched defender (when the other Subs eat
  detections), Pack Runner is the unit that actually carries to the
  Flagship — exactly Pilot A's T17/T19 line.
- **Sea Wolf Scout / U-Boat Wolf-cub** ({1T}) — enabler bodies. Their
  job is to be on board when the anthem lands and to *eat detections*
  on the saturation turn so the heavier hitters reach the Flagship.
- **Saturation Strike** ({2T}, currently broken) — would convert any
  saturation swing into a 2-power-per-attacker burst. **Engine bug**:
  cast_effect_fn never invoked, so the +2 power EOT modifier is never
  emitted, so combat damage uses unbuffed power. Filed in
  `docs/strategy/depths.md` Engine punchlist. Until fixed, treat as a
  dead 2-cost slot.
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
  to draw the anthem by T7.
- **Avoid keeping**: hands with 2+ {3T}+ cards and no 1-cost body.
  The early game is dead; defender will set up before you apply
  pressure.

## Play priorities (order)

1. **{1T} Sub on T1** if available (Wolf-cub > Scout for the higher
   power).
2. **{2T} Sub on T2-T3** to add a second attacker.
3. **Bank turn around T7-T9** — skip a deploy if (a) hand contains
   {3T}+ anthem AND (b) you have ≥2 Subs already on board AND (c)
   skipping leaves you at TC=3+ next turn for the anthem cost.
   This is the **MOST IMPORTANT** non-obvious priority in this deck.
   Pilot A's loss came from violating this rule.
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
- **Saturation Strike currently dead** (engine bug). Treats as a dead
  2-cost slot until cast_effect_fn dispatch is wired. Effective deck
  size temporarily 28.
- **Pack Leader U-99 may be a cut candidate.** {3T} legendary +1/+0
  lord is good when reached but rarely reached. Pilot A's iter-1
  suggested replacement with a {2T} body or {1T,1S} pinger. Defer the
  cut decision to iter-2 (with the bank-turn line tested first — if
  bank-turn fixes the reach problem, Pack Leader stays).

## Iteration log

(Append after each game piloted with this deck.)

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
