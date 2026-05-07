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

(No exploited patterns observed by an LLM pilot beyond the above. Each
new ultra-loop run that surfaces a heuristic-specific exploit goes here.)

## Contested strategic questions

- **Greedy vs bank-and-hold for top-heavy aggro decks.** Pilot A's
  greedy line (always deploy max-affordable) lost from a 1-hull
  position because the {3T}+ half of the deck was bricked by T11. The
  alternative — skip a deploy turn around T7-T9 to bank TC for
  Wolfpack Doctrine — is untested but plausibly the right policy for
  this curve. Open question: at what curve-shape threshold should an
  aggro pilot switch from "always deploy" to "bank for anthem"? The
  Wolfpack-specific answer goes in the deck plan; the format-level
  answer needs cross-deck data.
- **Should defensive 0-power chump interceptors have a downside?**
  Listening Post (0/3) hard-counters Wolfpack's 1-2 power swarm
  without ever trading. Either every aggro archetype needs a sorcery-
  speed Vessel-removal Action, or 0-power walls need a built-in cost
  (sink-on-block, oxygen tick on use, etc.). Picking one shapes the
  format's mid-game.
- **Consider new AI preset: `bank_and_hold`.** Distinct from medium
  (greedy) and conservative-heuristic. Skips a deploy turn when (a)
  hand contains an anthem the next-turn TC would make affordable AND
  (b) board has ≥2 attackers already. Would require a new preset entry
  in the bias surface; not yet evidenced enough to commit to building.

## Engine punchlist

- **`cast_effect_fn` is never invoked** — Action cards' bodies don't
  run. `src/engine/depths.py:cast_spell` (line 782) emits SPELL_CAST
  and routes the card to graveyard but does not call
  `card.cast_effect_fn`. So Saturation Strike's `+2 power EOT` to all
  Submarines is a silent no-op every cast — the PT_MODIFICATION events
  are never emitted, so `obj.state.pt_modifiers` stays empty, so
  `get_power` returns the printed value, so combat damage uses the
  unbuffed amount. Pilot A confirmed in-game at T33: cast Saturation
  Strike + Sea Wolf Scout swing → damage event amount=1 instead of
  expected 3. This is *not* Saturation-Strike-specific; it affects
  every Action in the codebase that uses `cast_effect_fn` (carrier.py
  line 42 docstring already flags this gap; ~25 cards across all four
  archetype files are affected). Fix: in `cast_spell`, after the
  SPELL_CAST emit, look up `card.cast_effect_fn` (the
  `CardDefinition` is reachable via `obj.characteristics.card_def` or
  `obj.card_def` depending on engine convention), invoke it with
  `(obj, state)`, and emit each returned Event through `game.emit`.
  Not fixed here — flagged for engine repair.

## Pilot iteration log

- **2026-05-07**: greedy Wolfpack (P1, LLM Pilot A) vs conservative
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
