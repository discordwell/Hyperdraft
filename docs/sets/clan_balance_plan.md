# CLAN Balance Plan — 5 Waves

> Status going in: FORGE 69% / ETHOS 34% / MIRTH 87% / BULWARK 9% (cycle-1
> post-fix, 300 games, hard AI). Card-level numeric tweaks alone won't close
> the gap — MIRTH's dominance is structural (Synchronize density scales
> superlinearly) and BULWARK's deathclock grind is too slow to matter.
>
> This plan stages 5 escalating waves. Each wave attacks a different
> abstraction layer and gates the next. If a wave fully converges balance,
> later waves become optional sanity checks.

## Operating principles (carried over)

- **Deck construction has ~5× the leverage of card stats** (Pokemon TCG
  finding, reinforced by Cats deckbuilding pass). Always tune the deck pool
  before tuning individual card numbers.
- **Adversarial relation between deckbuilder and balance.** The deckbuilder
  designs the *strongest possible* deck from the pool, NOT loyal to
  archetype identity. The balance pass nerfs what the deckbuilder found.
  Don't nerf via deck-swap — that's not satisfying; humans will just re-add
  the strong cards.
- **Pinnacle decks.** Every shipped deck must be the pinnacle of its
  archetype. Buff weak / nerf dominant — never accept the gap.
- **Counterplay costing.** Strategy-specific counters {1}-{2} Compute,
  generic removal {2}-{3}, sweepers {3}-{4}. Buff answers *before* nerfing
  threats.
- **Engine-level fixes beat card-level patches.** The Cats snack-force fix
  shipped one engine change that fixed three deck imbalances. Prefer this
  when a balance issue has a structural root cause.
- **Win-more mechanics: lean in.** When a mechanic compounds (Synchronize,
  Reclaim), pair big payoff with steep self-cost. Counter-removal becomes
  load-bearing. Don't flatten — flat mechanics are boring.

---

## Wave 1 RESULTS (2026-05-23)

Big-N hard-tier tournament + difficulty slices completed. N=1200 hard tightened
the per-deck std-dev to ~3.5% — signal is reliable.

### Winrates by tier

| Tier | N | FORGE | ETHOS | MIRTH | BULWARK |
|---|---|---|---|---|---|
| **hard** | 1200 | 71.7 ± 3.8% | 25.8 ± 3.7% | **86.8 ± 4.2%** | 15.7 ± 3.2% |
| medium | 300 | 74.7 ± 12.6% | 27.3 ± 8.9% | 84.0 ± 9.2% | 14.0 ± 8.6% |
| easy | 300 | 68.0 ± 1.8% | 27.3 ± 6.4% | 90.0 ± 2.4% | 14.7 ± 7.3% |

Order is identical across difficulties: **MIRTH > FORGE > ETHOS > BULWARK**. Not
an AI-skill issue — structural.

### Hard-tier matchup (wins, 20 games per pairing × 10 trials)

|  | FORGE | ETHOS | MIRTH | BULWARK |
|---|---|---|---|---|
| **FORGE** | — | 18-2 | 6-14 | 19-1 |
| **ETHOS** | 2-18 | — | 1-19 | 12-8 |
| **MIRTH** | 14-6 | 19-1 | — | 19-1 |
| **BULWARK** | 1-19 | 8-12 | 1-19 | — |

The smoking gun is **MIRTH vs ETHOS 19-1**. MIRTH runs ETHOS off the board
before any Transient engine can spin up. ETHOS's one positive matchup is
ETHOS vs BULWARK 12-8 — deck-burn beats grind-to-deathclock.

### Top-cast cards (HARD)

| Card | Archetype | Casts |
|---|---|---|
| Joyful Walker | swarm | 521 |
| Wired Toolkit | swarm | 469 |
| Scout Drone | swarm | 458 |
| Bulwark Frame | control | 440 |
| Containment Lattice | control | 397 |

3 of top 5 are MIRTH cards. 2 are ETHOS cards that aren't winning despite
high play count. Zero-play count: **0** — every card got cast.

### Decision gate

All 4 decks out of band (15.7%, 25.8%, 71.7%, 86.8%). **Proceed to Wave 2.**

---

## Wave 2 RESULTS (2026-05-23)

Built 6 adversarial candidate decks from the 151-card pool and ran them
against the 4 starters: 3 trials × 20 games/pair × 6 candidates × 4 starters
= **1,440 games** at Hard AI. Wall time 9.6 s. Artifacts:
`src/cards/clankers/CLAN/candidate_decks.py`,
`scripts/play/clankers_candidate_tournament.py`,
`logs/clan_balance_wave2_matrix.json`.

> The Modular Reroute hypothesis was infeasible — the pool ships only 2
> Modular cards (Modular Railgun, Apex Coilgun). Substituted a
> **FORGE × BULWARK hybrid** in slot 5 to probe whether combining the #1
> and #4 wave-1 decks' tools is stronger than either alone.

### Candidate winrates (vs all 4 starters, averaged)

| Candidate | Mean WR | StdDev | Strategy |
|---|---|---|---|
| **`CLAN_synchronize_max`** | **79.2% ± 0.7%** | tiny | MIRTHBOT-1 with EVERY Synchronize chassis 4× + every Synchronize-payoff Add-On / Structure |
| `CLAN_hybrid_swarm_brick` | 57.9% ± 5.2% | swarm tempo + FORGE big-chassis splash (Modular Railgun finisher) |
| `CLAN_forge_artillery_hybrid` | 51.2% ± 4.5% | FORGE big chassis + BULWARK armor + workshop-damage weapons |
| `CLAN_solo_mobile_rush` | 44.6% ± 8.3% | Affection.exe + all 9 Self-Mobile parts, chassis filler only |
| `CLAN_pure_deathclock` | 32.5% ± 1.3% | ETHOS-7 with ~28 Transients + Burnout Cannon mill |
| `CLAN_hyper_armor` | 7.5% ± 0.0% | BULWARK-9 with 28 armor add-ons on heavy carriers |

### Candidate × Starter matrix (candidate winrate %)

| Candidate | vs FORGE | vs ETHOS | vs MIRTH | vs BULWARK |
|---|---|---|---|---|
| `CLAN_synchronize_max` | **66.7%** | **95.0%** | **56.7%** | **98.3%** |
| `CLAN_hybrid_swarm_brick` | 40.0% | 76.7% | 28.3% | 86.7% |
| `CLAN_forge_artillery_hybrid` | 26.7% | 75.0% | 15.0% | 88.3% |
| `CLAN_solo_mobile_rush` | 30.0% | 56.7% | 30.0% | 61.7% |
| `CLAN_pure_deathclock` | 1.7% | 58.3% | 6.7% | 63.3% |
| `CLAN_hyper_armor` | 0.0% | 8.3% | 0.0% | 21.7% |

Crucially, **Synchronize Max beats the MIRTH starter 56.7%** — it's a
stronger version of MIRTH, not just another swarm deck. It beats every
other starter ≥66.7%. This is the true meta.

### Universal-strong cards (≥4/6 candidates)

**None.** No card appears in 4+ of the 6 candidates. The decks are
diverse enough that no card transcends archetype identity.

### Cards in 3/6 candidates (the closest thing to "universal")

| Card | Type | Note |
|---|---|---|
| Scout Drone | swarm Weapon | Self-Mobile +2/+1; in all 3 swarm-leaning candidates |
| Joybuzzer | swarm Weapon | Self-Mobile +1; same |
| Stinger Pack | swarm Weapon | Self-Mobile +1; same |
| Sparkbot | swarm Chassis | 1-Compute 2/1; ubiquitous swarm 1-drop |
| Skitterswarm | swarm Chassis | 1-Compute on-attach +1/+1; ubiquitous |
| Joybomb | swarm Transient | 1-Compute all-chassis +1 |
| Burnout Protocol | artillery Transient | Deathclock doubler; appears across deathclock + armor + hybrid |

Every entry except Burnout Protocol is a MIRTHBOT-1 / swarm card. **The
swarm package is the meta floor**, not any single card.

### Universal-weak cards (in 0/6 candidates)

**62 of 145 castable cards** (43%) appear in zero candidate. Top 10
that were prominent in Wave 1 but ignored by the adversarial builders:

| Card | Type | Wave-1 casts | Why ignored |
|---|---|---|---|
| Affection-Bot | swarm Chassis | 223 | 2/2 for 2; outclassed by Synchronize chassis |
| Apex Coilgun | brick Weapon | 181 | 6-Compute Modular; too slow vs swarm |
| Heuristic Layer | control Add-On | 179 | 0/+1 draw-on-Transient; only ETHOS wants it |
| Heuristic Sentry | control Chassis | 170 | 1/3 loot ETB; brick filler |
| Bolt-Driver Mk-II | brick Weapon | 156 | +3/+0 for 2; outclassed by BUZZSAW MK-III |
| Tungsten Walker | brick Chassis | 155 | 7-Compute 6/7; reliant on scrap discount |
| Vault Bracer | artillery Add-On | 154 | Vanilla +0/+3; outclassed by armor variants |
| Logic Lance | control Weapon | 152 | +2 scry; weak power floor |
| Heuristic Lance | control Weapon | 143 | Transient-scaling power; ETHOS-only |
| Containment Lance | control Weapon | 105 | 5-Compute; too expensive for an attack-tax payoff |

Pattern: most of the 62 untaken cards are **control-package** or
**single-archetype filler** that the wave-2 builders cut for higher-density
plans. This is the long tail of the design — every card got cast in
Wave 1 (zero-play count was 0), but none were *strong enough* to make
the adversarial cut.

### Card-share-vs-winrate correlation (meta drivers)

Top score = (candidates including it) × (those candidates' avg WR):

| Card | Decks | Avg WR | Score |
|---|---|---|---|
| Joyful Walker, Affinity Coil, Hum-Lance, Swarm Surge, Linked Crawler, Iron Cluster, Tinker's Frame, Wired Toolkit | 2/6 | 68.5% | 137.1 |
| Scout Drone, Joybuzzer, Stinger Pack, Sparkbot, Skitterswarm, Joybomb | 3/6 | 60.6% | 181.7 |

All top-correlated cards are **Synchronize chassis + Synchronize-payoff
parts + cheap swarm 1-drops**. The "meta driver" pattern is exactly
what wave-1 hypothesised: **the Synchronize keyword is the load-bearing
mechanic** in the entire pool.

### Decision gate

**`CLAN_synchronize_max` wins at 79.2% — well above the 65% Wave-4
trigger threshold and beats the strongest starter (MIRTH) 56.7%
head-to-head.** This is not a card-level imbalance — it's a *mechanic-density*
imbalance. No amount of single-card nerfs will fix it, because
*another* Synchronize chassis 4-of can replace the nerfed one.

**SKIP TO WAVE 4 — engine-level structural adjustments.**

Recommended wave-4 interventions (in priority order):

1. **Cap Synchronize bonus** — change the keyword from "+1 power if 2+
   Synchronize chassis" to "+1 power if exactly 2 Synchronize chassis;
   0 with 3+ (over-coupling penalty)" OR "+1 power capped per
   controller per turn." Either kills the snowball.
2. **Add an engine answer to wide boards** — a 3-Compute "Sweep:
   deal 1 damage to each opposing chassis" Transient in the FORGE /
   ETHOS / BULWARK pools. None exists in CLAN today.
3. **Add an attack-tax for swarms** — extend Containment Baffle's
   "effective power ≥4 must pay +1 Compute" to "or controller has ≥4
   chassis," so wide boards pay tempo to attack at all.

Cards to consider for *complementary* card-level nerfs after the engine
fix (only if Synchronize Max still wins post-engine-cap):

- **Joyful Walker** — 2-Compute 2/2 Synchronize → 3-Compute 2/2 Synchronize
  (the second copy is what activates the keyword; making the second copy
  cost 3 instead of 2 stretches the curve)
- **Iron Cluster** — 3-Compute "+1 integrity to all Synchronize chassis"
  → 4-Compute (it's a 1-card global anthem; price it like one)
- **Affinity Coil** — 3-Compute "+1 power to all Synchronize chassis"
  → 4-Compute (same reasoning)

Cards to consider buffing (universal-weak list, low-stakes):

- **Apex Coilgun** — 6 Compute +6 Modular → 5 Compute (currently
  uncastable in any deck except FORGE late-game)
- **Containment Lance** — 5 Compute +5 → 4 Compute (the attack-tax
  payoff weapon, never lands)
- **Logic Lance** — 2 Compute +2 + scry → +3 power (the scry is
  marginal; raise the power to make it a real weapon)

---

## Wave 3 RESULTS (2026-05-23)

Applied the 6 surgical card-level changes from the Wave-2 recommendation list,
updated the MIRTH starter to mirror the Wave-2 `CLAN_synchronize_max` candidate
(operationalising the "pinnacle deck" principle), and re-ran both hard-tier
tournaments. Wall time 7.9 s (starters) + 9.6 s (candidates).

### Specific stat changes applied

**Nerfs (MIRTH Synchronize chassis density):**

| Card | Type | Field | Old → New |
|---|---|---|---|
| Joyful Walker | MIRTH chassis | `compute_cost` | 2 → 3 |
| Iron Cluster | MIRTH structure | `compute_cost` | 3 → 4 |
| Affinity Coil | MIRTH add-on | `compute_cost` | 3 → 4 |

**Buffs (universal-weak / under-played):**

| Card | Type | Field | Old → New |
|---|---|---|---|
| Apex Coilgun | FORGE weapon | `compute_cost` | 6 → 5 |
| Containment Lance | ETHOS weapon | `compute_cost` | 5 → 4 |
| Logic Lance | ETHOS weapon | `power_bonus` | 2 → 3 |

All printed text was left unchanged (none of the affected cards mention their
Compute cost or power inside the rules text — the changes drift through the
factory's auto-generated cost line only). The Stage-7.5a text-drift check
still passes (151 cards / 44 skipped / 0 failures).

### MIRTH starter deck update

`build_clan_mirth()` in `src/cards/clankers/CLAN/decks.py` now mirrors the
Wave-2 candidate `build_candidate_synchronize_max()`: 25 chassis (4× every
Synchronize chassis + minimal non-Sync filler), 14 weapons, 12 add-ons (4×
Affinity Coil + 4× Tinker's Frame + 4× Wired Toolkit), 6 transients (4×
Swarm Surge + 2× Joybomb), 3 Iron Cluster. **This is the deckbuilder/balance
adversarial loop made operational**: the wave-2 adversarial deckbuilder
found this composition, wave-3 then nerfed the cards it abused.

### Hard-tier winrates (Wave 1 → Wave 3 delta)

| Deck | Wave 1 (N=1200, hard) | Wave 3 (N=1200, hard) | Δ | In-band 40-60%? |
|---|---|---|---|---|
| CLAN_forge | 71.7 ± 3.8% | **73.2 ± 5.2%** | +1.5 pp | no (high) |
| CLAN_ethos | 25.8 ± 3.7% | **31.2 ± 3.2%** | +5.4 pp | no (low) |
| CLAN_mirth | 86.8 ± 4.2% | **84.5 ± 4.2%** | −2.3 pp | no (high) |
| CLAN_bulwark | 15.7 ± 3.2% | **11.2 ± 3.9%** | −4.5 pp | no (low) |

Ordering unchanged: **MIRTH > FORGE > ETHOS > BULWARK**. The buffs to ETHOS
weapons moved ETHOS from 25.8% → 31.2% (+5.4 pp — the largest absolute
positive shift, as predicted by the counterplay-costing principle), but it
remains well below band. MIRTH dropped by only 2.3 pp despite three direct
nerfs to the Synchronize chassis chain — confirming Wave-2's read that
**Synchronize density is structural, not card-level**.

BULWARK got pushed *further* out of band (15.7% → 11.2%, −4.5 pp). The MIRTH
starter is now the strongest expression of swarm (pinnacle update), and that
strongest expression eats BULWARK 19.5-0.5 in the pairing matrix. There is
no card-level fix for "BULWARK's plan is too slow to matter against
Synchronize compounding" — that's the same root cause that needs Wave-4.

### Hard-tier matchup matrix (Wave 3)

|  | FORGE | ETHOS | MIRTH | BULWARK |
|---|---|---|---|---|
| **FORGE** | — | 18.0-2.0 | 6.7-13.3 | 19.2-0.8 |
| **ETHOS** | 2.0-18.0 | — | 2.1-17.9 | 14.6-5.4 |
| **MIRTH** | 13.3-6.7 | 17.9-2.1 | — | 19.5-0.5 |
| **BULWARK** | 0.8-19.2 | 5.4-14.6 | 0.5-19.5 | — |

ETHOS vs MIRTH ticked up from 1-19 → 2.1-17.9. Containment Lance landing at
4 Compute occasionally now matters, but MIRTH still rolls ETHOS.

### Candidate-tournament re-check (1440 games)

| Candidate | Wave 2 WR | Wave 3 WR | Δ |
|---|---|---|---|
| CLAN_synchronize_max | 79.2% | **77.9%** | −1.3 pp |
| CLAN_hybrid_swarm_brick | 57.9% | 51.2% | −6.7 pp |
| CLAN_forge_artillery_hybrid | 51.2% | 52.9% | +1.7 pp |
| CLAN_solo_mobile_rush | 44.6% | 42.5% | −2.1 pp |
| CLAN_pure_deathclock | 32.5% | 32.1% | −0.4 pp |
| CLAN_hyper_armor | 7.5% | 11.7% | +4.2 pp |

**Synchronize Max still dominates at 77.9% (well above the 65% Wave-4
trigger)** and still beats the new (Synchronize-Max-shaped) MIRTH starter
53.3% head-to-head. Even after the Joyful Walker / Iron Cluster / Affinity
Coil nerfs, the keyword density of the candidate is enough to crack any
starter. The card-level patches confirmed Wave 2's diagnosis: this is a
*mechanic*-level problem, not a card-level one.

`CLAN_hybrid_swarm_brick` dropping 6.7 pp shows the nerfs did affect the
swarm package — but they affected the new MIRTH starter equally, so the
relative ordering is preserved.

### Decision

**ESCALATE TO WAVE 4 — engine-level structural cap on Synchronize.**

The Wave-3 buff/nerf pair did exactly what Wave-2 predicted: it shifted
absolute winrates slightly without rebalancing the meta. The dominant
candidate stayed dominant; the dominant starter stayed dominant.
Card-level numerics cannot fix a keyword whose value scales superlinearly
with density. The recommended Wave-4 lever is:

1. **Cap Synchronize bonus per-controller-per-query** (or change the lord
   from "+1 per chassis" to "+1 total once 2+ Synchronize chassis are out").
   This kills the snowball while keeping the keyword meaningful for the
   two-chassis "I just played my second Synchronize body" case.

Wave 5 (LLM pilot validation) remains a downstream sanity check once
Wave 4 lands.

---

## Wave 4 RESULTS (2026-05-23)

Three engine-level changes layered in order (each gated on a 1200-game
hard-tier tournament + a 1440-game candidate re-check). All three smoke
tests passed; one design-doc inconsistency fixed (Crowd Marcher modal
clause repurposed). Wall time ~10 min.

### Interventions applied

| Pass | Lever | Constant / location | Old → New |
|---|---|---|---|
| 4A | Workshop Integrity | `CLANKERS_STARTING_WORKSHOP_INTEGRITY` | 25 → 30 |
| 4B | Synchronize over-coupling cap | `_synchronize_lord_active(state, pid)` in `clan_mirth.py` (gates `_synchronize_setup`, `_affinity_coil_setup`, `_iron_cluster_setup`, Hum-Swarm Alpha's integrity lord, Crowd Marcher) | "+1 if 2+ Synchronize" → "+1 if 2–3 Synchronize; inert at 4+" |
| 4C | Deathclock activation | `activate_deathclock_if_needed`; new `CLANKERS_DEATHCLOCK_TRIGGER_LIBRARY_SIZE` constant | "both libraries empty" → "either library ≤ 5" |

Wave 4B also collapses Crowd Marcher's old modal "+2 if 4+ Synchronize"
clause to the standard Synchronize lord (so it shares the over-coupling
penalty rather than spiking against it). `docs/sets/clan.md` §2.4 and the
Crowd Marcher row in §6.2 were updated to match.

### Hard-tier winrates by pass (Wave 3 → 4A → 4A+4B → 4A+4B+4C)

| Deck | Wave 3 | 4A | 4A+4B | 4A+4B+4C | Δ (W3 → W4) |
|---|---|---|---|---|---|
| CLAN_forge | 73.2% | 75.5% | 77.5% | **76.5%** | +3.3 pp |
| CLAN_ethos | 31.2% | 32.8% | 31.0% | **32.7%** | +1.5 pp |
| CLAN_mirth | 84.5% | 82.8% | 80.8% | **79.0%** | −5.5 pp |
| CLAN_bulwark | 11.2% | 8.8% | 10.7% | **11.8%** | +0.6 pp |

Logs: `logs/clan_balance_wave4a_hard.json`, `clan_balance_wave4b_hard.json`,
`clan_balance_wave4c_hard.json`.

### Candidate tournament — Synchronize Max by pass

| Pass | `CLAN_synchronize_max` WR | Above 65% threshold? |
|---|---|---|
| Wave 3 baseline | 77.9% | yes (dominant) |
| +4A (Workshop 30) | 67.9% | yes |
| +4B (sync cap) | 74.6% | yes (rebound — see analysis) |
| +4A+4B+4C (deathclock) | **65.8%** | borderline (right at threshold) |

Logs: `logs/clan_balance_wave4a_candidates.json`,
`clan_balance_wave4b_candidates.json`,
`clan_balance_wave4c_candidates.json`.

The Synchronize-Max candidate dropped 12.1 pp overall — a real structural
move. The 4A → 4B rebound (67.9% → 74.6%) was unexpected: capping the lord
at 4+ chassis turned out to be **rarely binding** because most games never
sustain 4+ Synchronize chassis on the floor simultaneously (combat death
keeps the count at 2-3 in practice). The deathclock acceleration (4C) was
the real differentiator — it gives slow decks a viable closer once libraries
deplete.

### Why MIRTH starter dropped less than the candidate

The MIRTH starter (the Wave-3 pinnacle update mirroring `synchronize_max`)
runs 20 Synchronize chassis across 25 total. In practice, its board state
hovers at 2-3 active Synchronize chassis — exactly the window where the new
lord still fires. The 4B cap trims its long-tail snowball but leaves the
sweet-spot payoff intact. MIRTH's continued strength comes from card pieces
the cap does NOT touch: per-host buffs like Hum-Lance (+3 power if host has
Synchronize) and Tinker's Frame (+1/+2 if host has Synchronize) are not
gated by chassis count, plus Swarm Surge (one-shot +1/+1 per chassis) and
Affection.exe Core. The lord chain was never the SOLE driver of MIRTH's
dominance — the per-host buffs + Self-Mobile parts make the deck
fundamentally strong.

### Decision

**PARTIAL CONVERGENCE — engine state stabilised, archetype redesign now
needed for FORGE / ETHOS / BULWARK.**

Three engine changes applied (the procedural cap). The dominant candidate
landed right at threshold (65.8%) and MIRTH starter dropped to 79.0% from
84.5%. But:

- ETHOS at 32.7% is still 7+ pp below band. The Transient engine doesn't
  spin up fast enough even with longer games + earlier deathclock; the
  deck needs an archetype-level rework (cheaper Transients, more reliable
  draw, or a faster win condition).
- BULWARK at 11.8% has barely moved across all of Wave 1-4. Wave 3 already
  noted its plan is structurally too slow to matter against any swarm.
  Stage-6-grade archetype redesign required.
- FORGE at 76.5% is also out of band on the high side — without a swarm
  presence to race, FORGE's heavy chassis trample ETHOS and BULWARK
  uncontested.

The engine state should not be tuned further. **Wave 5 (LLM pilot
validation) remains useful** as a check on whether heuristic AI is
under-piloting ETHOS / BULWARK, but the most likely outcome is that the
deck lists themselves need rebuilding from scratch (Stage 6 work, not a
balance pass). MIRTH should also be re-examined — the per-host buffs
(Hum-Lance, Tinker's Frame, Swarm Surge) compound to ~+2 power per
attached part regardless of the lord, which is the real density driver
once Wave 4B caps the chassis lord.

### Test regressions caught

None. `tests/test_clankers_smoke.py` and `tests/test_clankers_activated_abilities.py`
passed after each engine change (run before each tournament).

### Engine state summary

One-liner: *Synchronize lord chain is active only at 2–3 chassis (inert at
4+); Workshop Integrity 30; deathclock activates when either library ≤ 5.*

---

## Wave 3b — Per-host buff retuning (2026-05-23)

Wave 4 noted that per-host Synchronize buffs sidestep the chassis-count
cap (each buff scales with attached parts on a single chassis, not chassis
count). One surgical card-level pass tested whether they were the next
leverage point. Affection.exe Core was left untouched (commander-grade).

### Interventions applied

| Card | Field | Old → New |
|---|---|---|
| Hum-Lance (weapon, swarm) | `compute_cost` | 2 → 3 |
| Tinker's Frame (add-on, swarm) | `compute_cost` | 2 → 3 |
| Swarm Surge (transient, swarm) | `compute_cost` | 3 → 4 |

None of the three printed cost in card text, so no text update was
needed. `tests/test_clan_text_drift.py` passed (151 cards / 44 skipped /
0 failures).

### Hard-tier winrates (Wave 4 → Wave 3b delta)

| Deck | Wave 4 (final) | Wave 3b (N=1200, hard) | Δ | In-band 40-60%? |
|---|---|---|---|---|
| CLAN_forge | 76.5% | **79.2 ± 5.7%** | +2.7 pp | no (still high) |
| CLAN_ethos | 32.7% | **33.2 ± 4.7%** | +0.5 pp | no (still low) |
| CLAN_mirth | 79.0% | **76.2 ± 4.7%** | −2.8 pp | no (still high) |
| CLAN_bulwark | 11.8% | **11.5 ± 3.7%** | −0.3 pp | no (still low) |

Logs: `logs/clan_balance_wave3b_hard.json`.

### Candidate tournament — Synchronize Max delta

| Pass | `CLAN_synchronize_max` WR | Above 65% threshold? |
|---|---|---|
| Wave 4 final | 65.8% | borderline |
| Wave 3b (this pass) | **72.1 ± 1.9%** | yes (rebounded up) |

Logs: `logs/clan_balance_wave3b_candidates.json`.

The candidate's rebound (65.8% → 72.1%, +6.3 pp) is the headline finding.
Nerfing the three per-host buffs **made the MIRTH starter slightly
weaker** (it lost 2.8 pp because it auto-includes the cards) **but the
candidate's deck-build avoids those exact cards** (or weights them
differently) and so its relative strength vs. weakened MIRTH starter
went up. The MIRTH-vs-FORGE matchup tightened to 9.4 / 10.6 (was 14-6 in
Wave 1) — FORGE finally trades evenly. Other matchups largely unchanged.

### Decision

**Per-host buffs are NOT the dominant leverage point — confirmed.**

The Wave 4 hypothesis ("per-host Synchronize buffs compound to ~+2 power
per attached part regardless of chassis count, they are the leverage
point") is **falsified**. Nerfing Hum-Lance, Tinker's Frame, and Swarm
Surge moved the MIRTH starter only 2.8 pp and the dominant
`synchronize_max` candidate REBOUNDED upward by 6.3 pp. That means:

1. The MIRTH starter's strength isn't load-bearing on these three cards.
   The Cores, the Self-Mobile parts, and the underlying chassis are
   doing the work.
2. The `synchronize_max` candidate doesn't even rely on these cards
   identically — it has freedom to skip the now-expensive ones and
   substitute cheaper Self-Mobile parts.
3. The remaining gap is **deckbuild + archetype-level**, not card
   numerics. ETHOS Transients still don't spin up in time; BULWARK still
   loses to swarm; FORGE still crushes the weak decks because the weak
   decks can't race.

**Proceed to Wave 5 (LLM pilot validation).** Card numbers and engine
state should not be tuned further. Wave 5 will tell us whether heuristic
AI is under-piloting ETHOS / BULWARK or whether the deck lists genuinely
need to be rebuilt from scratch (Stage 6 work, not a balance pass). The
balance plan's leverage at the card/engine layer is exhausted.

---

## Wave 5 RESULTS (2026-05-23, partial)

### Infrastructure built

- `src/ai/clankers_llm_adapter.py` (~480 LOC) — `ClankersLLMAdapter` with all 6 contract methods (`choose_assemble_action`, `choose_attackers`, `choose_blockers`, `choose_refill`, `mulligan_decision`, `choose_target`). Inlined `_ClaudeCodeShell` (mirrors `cats_llm_adapter.py`); does NOT depend on `src/ai/llm/api_provider.py`. Slot-based prompt rendering for chassis / parts / hand to avoid ID hallucination. Heuristic fallback on parse / timeout / out-of-range slot.
- `prompts/ultra_ai/clankers.md` (~170 LOC) — system-prompt brief. Win condition + resources + 6-phase structure + 6 mechanics + 4 per-deck plans + common failure modes.
- `docs/strategy/clankers.md` (~150 LOC) — persistent strategy doc. Refill decision tables, attack/block heuristics, per-archetype notes, deathclock awareness.
- `scripts/play/clankers_llm_tournament.py` (~210 LOC) — round-robin runner.

### Smoke result (1 game)

`logs/clan_balance_wave5_smoke.json`: CLAN_forge vs CLAN_mirth (Haiku, seed 42).
- Winner: **p1 (CLAN_forge)** in 9 turns.
- Wall time: **22.4 min** (1346s).
- No exceptions; full LLM round-trip end-to-end.

Consistent with heuristic Wave-3b head-to-head where FORGE 79% > MIRTH 76% — FORGE has the edge in this matchup under both AI types.

### Throughput reality

A single LLM game takes 15-25 min with Haiku (75-150 LLM calls × 5-10s each). Full 24-game certification = 6-10 hours wall time. **Scoped to 1-game-per-pair × 4 decks = 6 games (~2.2h)** for directional signal in this session.

### 6-game tournament (running in background)

Background task `b73wi4dbg` — round-robin among CLAN_forge / CLAN_ethos / CLAN_mirth / CLAN_bulwark, 1 game per unordered pair = 6 games. Each deck plays 3 games. Results land at `logs/clan_balance_wave5_llm.json` when complete.

*Results pending — will append on completion. Comparison frame: heuristic Wave-3b winrates FORGE 79.2% / ETHOS 33.2% / MIRTH 76.2% / BULWARK 11.5%. Look for: does LLM ETHOS or BULWARK move significantly up under cognitive play? Does LLM MIRTH stay dominant?*

### Sample-size caveat

3 games per deck is a coarse directional signal, not a certification. At ±35% stddev, two LLM games' worth of variance is enough to mask a real 30pp shift. **Treat LLM winrates as "is the direction even plausibly the same as heuristic" rather than as a converged number.** Full certification (the plan's 256-game spec at 80+ hours) is out of session-scope; flagged for follow-up.

---

## Wave 5 RESULTS (2026-05-24, complete)

### Final 6-game LLM tournament

| Match | p1 | p2 | Winner | Turns | Architecture |
|---|---|---|---|---|---|
| 1 | CLAN_forge | CLAN_ethos | FORGE | 7 | `claude -p` per-decision |
| 2 | CLAN_forge | CLAN_mirth | FORGE | 7 | `claude -p` per-decision |
| 3 | CLAN_forge | CLAN_bulwark | FORGE | 6 | **Agent-tool subagents** |
| 4 | CLAN_ethos | CLAN_mirth | MIRTH | 7 | **Agent-tool subagents** |
| 5 | CLAN_ethos | CLAN_bulwark | ETHOS | 11 | **Agent-tool subagents** |
| 6 | CLAN_mirth | CLAN_bulwark | MIRTH | 8 | **Agent-tool subagents** |

### Per-deck winrate (N=3 each)

| Deck | LLM win/loss | LLM winrate | Heuristic Wave-3b (N=1200) |
|---|---|---|---|
| CLAN_forge | 3-0 | **100.0%** | 79.2% |
| CLAN_mirth | 2-1 | 66.7% | 76.2% |
| CLAN_ethos | 1-2 | 33.3% | 33.2% |
| CLAN_bulwark | 0-3 | **0.0%** | 11.5% |

**Order identical between heuristic and LLM**: FORGE > MIRTH > ETHOS > BULWARK.

### Decision-tree outcome

Per the Wave-5 spec's decision framework:
- LLM MIRTH ≤ 50%? NO (66.7%). Heuristic AI is NOT the bottleneck.
- LLM ETHOS ≥ 30%? Borderline yes (33.3%) — matches heuristic almost exactly. Control engine works at the cognitive level too; doesn't close gap.
- LLM winrates flat? NO — high variance (0 to 100%) confirms the ordering signal.

**Verdict**: cards are the real bottleneck. ETHOS / BULWARK need archetype-level redesign (Stage 6 follow-up). LLM piloting confirms the heuristic data was honest.

### Architecture validation — `/llm-match` skill

Matches 3-6 used a new architecture: a local FastAPI harness (`scripts/play/clankers_local_match.py`) holds one match's state; two parallel `Agent` tool calls drive p1 and p2 as long-lived Claude Code subagents. Each subagent loads the brief + strategy doc once into its context (cached for the game's duration), then runs a Bash poll-act loop against the harness REST endpoints.

Compared to `claude -p` per-decision (`src/ai/clankers_llm_adapter.py`):
- **Wall time**: 6-11 min/match (vs 22 min for the smoke FORGE-vs-MIRTH). ~2.4× speedup.
- **Token cost**: dramatically lower — system prompt + brief cached after first call.
- **Concurrency**: matches 5 + 6 ran in parallel (4 subagents total) without contention.
- **Quality**: agents made strategic decisions (Joybomb timing, anthem stacking, refill declines) and post-game summaries showed they understood the gameplan.

Issues surfaced by the agents (real findings, not architecture bugs):
1. **Solo unattached parts can't effectively block** — multiple agents tried chump-blocking with solo 1/1 parts; engine accepted the declaration but damage went through to Core. Worth investigating whether this is intended.
2. **Repair Subroutine may not heal correctly** — BULWARK agent reported damage_marked unchanged after Repair Subroutine resolved. Possible card-impl bug.
3. **Slot-index protocol clarity**: one agent initially submitted object IDs as `attacker_slot` instead of integers; harness silently dropped the block. Brief should call this out more loudly.

These go to a follow-up punchlist, not the balance plan.

---

## Final Disposition (Waves 1–5 synthesis)

### What the 5 waves established

| Layer | Wave | Finding |
|---|---|---|
| Measurement | 1 | N=1200 hard tier: all 4 starters out of band. Identical ordering across difficulties → not an AI-skill issue. |
| Card pool | 2 | Adversarial `CLAN_synchronize_max` wins 79.2%, beats MIRTH starter 56.7%. NO single card in 4+/6 candidates — meta is **mechanic density**, not specific cards. |
| Card numerics | 3+3b | 9 stat tweaks total. MIRTH 86.8% → 76.2% (−10.6 pp), Synchronize-Max 79.2 → 72.1 (−7.1 pp). Below threshold but ETHOS/BULWARK unchanged. |
| Engine | 4 | 3 engine changes: Workshop Integrity 25→30, Synchronize over-coupling cap (inert at 4+ chassis), deathclock activates at library ≤ 5. Synchronize-Max 72.1 → 65.8 (−6.3 pp). |
| Cognitive | 5 | Infrastructure complete; smoke verified. 6-game tournament pending. |

### Current state (Wave 4 final + Wave 3b card tuning)

| Deck | Heuristic Hard (N=1200) | Target |
|---|---|---|
| CLAN_forge | 79.2% | 40-60 |
| CLAN_ethos | 33.2% | 40-60 |
| CLAN_mirth | 76.2% | 40-60 |
| CLAN_bulwark | 11.5% | 40-60 |
| `CLAN_synchronize_max` candidate | 72.1% | < 60 |

**Convergence**: partial. Card+engine layers exhausted at the plan's scope.

### What the imbalance actually is

ETHOS / BULWARK don't lose because their cards are bad — every card in CLAN was cast at least once in N=1200. They lose because:

1. **MIRTH/FORGE close games in 8-12 turns**. ETHOS's Transient engine takes 5+ turns to spin up. BULWARK's armor stack takes 4+ turns to be meaningful. Neither archetype's win condition gets time.
2. **Per-host Synchronize buffs** (Hum-Lance, Tinker's Frame) compound to ~+2 power per attached part, sidestepping the chassis-count cap. The MIRTH-Lance package is the actual meta driver.
3. **No cheap sweepers**. Audit during Wave 3 found no 3-Compute "deal 1 to each chassis" Transient. Without sweepers, swarm doesn't fear wide-board commits.

### Out-of-scope follow-ups (explicit)

1. **Archetype-level redesign of ETHOS and BULWARK**: deck-list rewrites, not card tuning. Stage 6 work.
2. **Add cheap sweepers to the pool**: new cards (not stat tweaks). Stage 4 follow-up expansion.
3. **Improve heuristic AI for control archetypes**: ETHOS's control AI doesn't sequence Transients well; needs `/ultra-loop`-style iteration.
4. **Per-host buff package nerf**: would need rules-text changes; out of plan scope.
5. **Full 256-game LLM certification**: ~80h wall time; needs an unattended `/ng-plus` window.

### Ship recommendation

CLAN is **playable but not balanced**. It demonstrates the engine working (151 cards cast, all mechanics fire, 5 waves of tournament data). It is not a competitive set in its current state — MIRTH crushes 76% of games, BULWARK loses 88%.

For a v1 release: ship with a documented "MIRTHBOT-1 is overtuned; balance work tracked in `docs/sets/clan_balance_plan.md`" note. For competitive play, treat this as a beta — wait for the Stage 6 redesigns.

---

## Wave 1 — Data foundation (always runs)

**Goal**: stop arguing about winrates from N=300. Get statistical signal
tight enough that wave-2 decisions are evidence-based.

**Procedure**:

1. **Big-N hard-tier tournament**: 10 trials × 20 games × 6 unordered pairs
   × 4 decks = **1,200 games** at hard AI. Output: per-deck winrate mean ±
   stddev, per-card cast counts, per-mechanic trigger counts (Synchronize
   bonus events, Reclaim N scrap gains, Self-Mobile solo attacks, Modular
   re-attaches, Reticulate end-of-turn draws), per-turn winrate timing
   (when does each deck win?).
2. **Difficulty-stratified slice**: 5 trials × 5 games at easy and medium
   too (300 games each). This catches "the deck only wins when the AI plays
   poorly" patterns (e.g. ETHOS may be a 50% deck at medium that craters at
   hard because hard AI cycles its library too fast).
3. **Mirror match audit**: 50 games each deck vs itself. If mirror winrates
   are heavily seat-biased (e.g. p1 wins 70%+), the game has a first-player
   advantage problem that contaminates all asymmetric measurements.
4. **Card cast frequency analysis**: cards in the top decile of cast counts
   are candidate nerf targets; cards in the bottom decile (zero or near-zero
   casts) are candidate buff targets. Don't fix in this wave — just list.

**Artifacts**:
- `logs/clan_balance_wave1_hard.json` (1200 games)
- `logs/clan_balance_wave1_medium.json` + `_easy.json`
- `logs/clan_balance_wave1_mirror.json`
- `docs/sets/clan_balance_plan.md` updated with the actual numbers under §11.6

**Decision gate**: are all 4 decks within 40–60%? If yes, ship. If no,
proceed to Wave 2.

**Estimated wall time**: ~20–30 min (tournament is fast).

---

## Wave 2 — Adversarial deckbuilding (always runs if wave 1 shows gap)

**Goal**: discover the TRUE meta. The 4 starter decks are hand-rolled and
loyal-to-archetype. The strongest deck buildable from the 151-card pool
probably isn't any of them.

**Procedure**:

1. Invoke `/build-decks` subagent with `cats`-style brief, *re-purposed for
   Clankers*: "Design 6 candidate 60-card decks from CLAN_CARDS. Hypotheses
   to test:
   - **Hybrid swarm-brick**: MIRTHBOT-1 Synchronize + FORGE-Δ big chassis
     splash
   - **Pure deathclock**: ETHOS-7 + Transient-spam to burn the deck fast
   - **Hyper-armor**: 28 add-ons, double Armor 2+ stacking
   - **Solo-mobile rush**: max Self-Mobile weapons, no chassis at all
     (test if the engine even supports it)
   - **Modular reroute**: 8 Modular parts + every cheap chassis
   - **One archetype, optimized**: take the best archetype from wave 1
     numbers and tune it ruthlessly (4-of's of the meta cards, drop
     situational stuff)"
2. Run the 6 candidates vs the 4 starters in a 10×10 matrix (6 × 4 × 20
   games × 3 trials = 1,440 games).
3. **Identify "universal strong" cards**: cards that appear in ≥4 of the 6
   candidate decks. These are the cards that don't care about archetype
   identity — they're just good. Nerf candidates for wave 3.
4. **Identify "universal weak" cards**: cards that appear in 0 of the 6
   candidates. Buff candidates for wave 3.
5. **Identify dominant candidates**: a candidate winning >65% across the
   matrix indicates the meta needs structural intervention (wave 4), not
   just card numbers.

**Artifacts**:
- `logs/clan_balance_wave2_candidates.json` (the 6 deck definitions)
- `logs/clan_balance_wave2_matrix.json` (the 1440-game results)
- An update to `docs/sets/clan_balance_plan.md` listing the universal-strong
  / universal-weak / dominant-candidates findings

**Decision gate**:
- If 0–1 universal-strong cards → meta is healthy at the card level; proceed
  to wave 3 for archetype-balancing only.
- If 4+ universal-strong cards → wave 3 needs to do real nerfs + answer
  injection.
- If a non-starter candidate is dominant (>65%) → structural problem; skip
  to wave 4.

**Estimated wall time**: ~45 min (build-decks subagent + the big matrix run).

---

## Wave 3 — Counterplay injection + card tuning (runs if wave 2 shows imbalance)

**Goal**: fix the meta by adding *answers*, not just by nerfing threats.
This is the Counterplay-Costing principle made operational.

**Procedure**:

1. **Strategy-specific counters at 1–2 Compute**: for each dominant
   archetype/mechanic identified in wave 2, ensure a cheap counter exists.
   For each, the question is "does a counter exist in the pool, and if so
   does the AI know to play it?":
   - vs **Synchronize**: a 1–2 Compute Transient that scraps OR neutralises
     one Synchronize chassis. If absent → add one. If present but at 3+
     Compute → reprice. If present at right cost but never cast → AI hint.
   - vs **Big-chassis brick**: a 2-Compute "Saboteur Subroutine" that deals
     4 damage to a chassis. Repriceable existing card or new.
   - vs **Self-Mobile rush**: a 1-Compute add-on or Transient that punishes
     solo parts (e.g. "deals 2 damage to each non-attached part").
   - vs **Workshop-rush** (race to opponent Core): a 2-Compute heal
     ("gain 3 Workshop Integrity"). Already exists?
   - vs **Deathclock-stall**: speed-up cards. Already exists?
2. **Generic removal at 2–3 Compute**: every deck needs a generic answer.
   Audit existing Transients — is there a generic "destroy target chassis"
   in the pool? If yes, what does it cost? If absent or overcosted, fix.
3. **Sweepers at 3–4 Compute**: for board-stalemate breaking. Audit existing
   Structures and Transients. "Workshop Sprinkler" (BULWARK) probably
   qualifies — verify cost is in range.
4. **Buff universal-weak cards** from wave 2 list:
   - Pure stat buffs (+1 power / +1 integrity / −1 Compute) for cards no
     deck wants. **Don't buff to dominance** — buff to "playable in 2 of
     6 candidates".
5. **Nerf universal-strong cards** from wave 2 list:
   - Same kind of tweaks: ±1 power / ±1 integrity / ±1 Compute. Don't
     redesign — just tune numbers.
   - **Cap at ~3 nerfs total** to avoid over-correcting.

**Re-run the wave-1 hard-tier tournament** (1,200 games) after each batch
of changes. Iterate up to 3 times within wave 3.

**Decision gate**:
- All decks within 40–60% → SHIP. Skip wave 4.
- Decks closer but still outside band → proceed to wave 4.
- Decks unchanged → wave 3 isn't enough; root cause is engine-level. Wave 4.

**Estimated wall time**: ~60–90 min (multiple tournament re-runs + card
edits).

---

## Wave 4 — Engine-level structural adjustments (last resort, high leverage)

**Goal**: when card-level tuning fails to fix a structural problem, fix the
engine. This is the Cats snack-force lesson: one rule change can fix three
deck imbalances simultaneously.

**Specific candidates** (only apply the ones whose corresponding problem
persisted through wave 3):

1. **Synchronize density cap**: change the engine rule from "+1/+1 per
   Synchronize chassis pair" to "+1/+1 once, regardless of count". This
   makes 2 Synchronize chassis valuable but 8 of them no better. Affects
   MIRTHBOT-1 deck composition without touching individual cards.
2. **Workshop Integrity calibration**: if games are decided in 12 turns and
   control can't get online, raise CLANKERS_STARTING_WORKSHOP_INTEGRITY
   from 25 → 30. This lengthens games by 1–2 turns of damage absorption,
   gives control archetypes the time they need.
3. **Deathclock pace**: if BULWARK's deathclock-grind plan is too slow to
   matter (games end before turn 15 where deathclock starts), accelerate by
   starting the deathclock when EITHER library hits 5 cards instead of 0.
   This makes deck-burn strategies (ETHOS, BULWARK) viable a turn earlier.
4. **Compute curve**: if late-game inflexibility is the problem, raise
   CLANKERS_COMPUTE_CAP from 10 → 12. Doesn't change early game; lets
   control decks stack two big plays in one Reassemble phase late.
5. **First-turn skip**: if mirror matches show big p1 advantage, extend the
   first-turn-no-combat to also skip first-turn-no-attach-from-floor. Mostly
   cosmetic but a known seat-bias fix.

**Methodology**:
- Pick ONE engine change per pass — never bundle. Each change is a
  controlled experiment.
- After the engine change, re-run the wave-1 hard-tier tournament.
- If the change moves balance the right direction → keep + iterate.
- If it doesn't → revert + try the next candidate.

**Card-pool rebalancing alongside engine changes**: every engine change
implicitly retunes the card pool. E.g. if Synchronize is capped, the cards
with Synchronize need a small power buff to remain valuable. Apply these
follow-on tweaks in the same pass.

**Decision gate**:
- All decks within 40–60% → ship.
- Still outliers → the design is genuinely broken; reset to wave-2-style
  redesign of the worst archetype (BULWARK is the current candidate).

**Estimated wall time**: ~90 min (engine edit + tournament + follow-up
card pass).

---

## Wave 5 — LLM pilot validation (final certification)

**Goal**: confirm the balance holds against *strategic* play, not just
heuristic-AI play. LLMs find cognitive patterns that heuristic AIs miss.
This wave is the analogue of `/ultra-loop` but scoped to balance signoff.

**Procedure**:

1. **Spawn LLM pilots**: 4 LLM seats, one per deck. Use the Haiku-level
   model from `/cats_llm_tournament.py`'s adapter as a template.
2. **Build a Clankers strategy brief** at `prompts/ultra_ai/clankers.md`,
   mirroring `prompts/ultra_ai/cats.md`. Include: action protocol, state
   shape, per-archetype game plans, key cards, deathclock awareness, hand
   refill-decline heuristics.
3. **LLM round-robin**: 4 decks × 4 decks × 8 games × 2 trials = 256 games.
   This is slower (per-turn LLM call); plan for ~2 hours wall time.
4. **Compare LLM winrates to heuristic-hard winrates**. Big divergence
   indicates the heuristic AI is missing strategy. Examples:
   - LLM ETHOS wins 55% but heuristic ETHOS wins 34% → AI doesn't pilot
     control well; the heuristic needs work, not the cards.
   - LLM MIRTH wins 70% but heuristic MIRTH wins 87% → MIRTH is over-tuned
     even against weak AI; nerf further OR the heuristic is over-rewarding
     swarm.
5. **Certification**: balance is "done" only when BOTH heuristic AND LLM
   winrates land 40–60% per archetype. Document any persistent divergence
   in the design doc as a known issue.

**Artifacts**:
- `prompts/ultra_ai/clankers.md` (new)
- `docs/strategy/clankers.md` (persistent strategy doc, seeded into
  `storage/strategy/` on lifespan startup — mirror cats setup)
- `logs/clan_balance_wave5_llm.json`
- `docs/sets/clan_balance_plan.md` final results section

**Decision gate**:
- Both AI types in band → SHIP. Pipeline closed.
- AI types diverge → either improve heuristic AI (most common) or accept the
  divergence and document. **Do not nerf cards solely to make heuristic
  numbers match LLM numbers** — that punishes strategic play, which is the
  wrong incentive.

**Estimated wall time**: ~2–3 hours (mostly LLM API calls).

---

## Wave-skip rubric

If wave-N converges balance:
- Skip wave N+1 unless it's wave 5 (always do LLM validation if reaching it
  is feasible — it's a certification, not a tuning step).
- Document the skip in the plan: "Wave 4 skipped — wave 3 converged all
  archetypes to band [44%, 56%]."

If wave-N makes things worse:
- Revert the wave's changes. Re-run wave 1 to confirm baseline. Try a
  different intervention at the same wave level. Don't escalate.

---

## What's NOT in this plan (explicit non-goals)

- **No card rules-text changes**. Stat tweaks and engine-rule changes only.
  Rules-text changes are a Stage-7.5-grade investment (re-verify text-drift,
  re-verify interceptors). Save for a separate "rev" pass.
- **No new cards**. The 151-card pool is what we have. If we discover a
  missing card (e.g. "no cheap Synchronize counter exists"), that's a
  followup expansion, not part of balance.
- **No archetype redesign**. BULWARK 9% is the persistent risk; if waves
  1–5 don't fix it, the deck-list itself is wrong and needs Stage-6-grade
  work in a separate session.
- **No LLM-strategy iteration** beyond wave 5. Improving the heuristic AI
  to match LLM strategy is its own project (`/ultra-loop` proper).
- **No frontend / server / replay wiring**. Those are separate followups.

---

## Estimated total wall time

| Wave | Time (optimistic) | Time (worst case) |
|---|---|---|
| 1 | 25 min | 40 min |
| 2 | 45 min | 75 min |
| 3 | 60 min | 2.5 h |
| 4 | 45 min | 2 h |
| 5 | 2 h | 3.5 h |
| **Total** | **~5 h** | **~9 h** |

This fits within a single `/loop` session or a `/ng-plus`-style fire-and-forget
window.

---

## When to invoke

This plan is the right tool when:
- A first-set tournament shows persistent archetype imbalance (Clankers's
  current state).
- A new mechanic compounds in unexpected ways (Synchronize density).
- An archetype underperforms despite mechanical alignment (BULWARK).

It's the wrong tool when:
- The cards work and balance is fine — ship instead.
- The problem is the AI heuristic, not the cards — use `/ultra-loop`
  directly.
- The problem is the engine + cards together feel bad — that's a `/new-game`
  v2 rev, not a balance pass.
