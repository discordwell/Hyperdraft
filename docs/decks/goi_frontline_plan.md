# GOI Frontline — Deck Plan

## Win Condition
- **Primary alt-win**: GOI Mandate 1 (Serpent Consulate) — `public_panic` = **4 archives AND opponent secrecy ≤ 6**.
- **Fallback**: 7 archives (standard) — slow.

## Composition (25 cards)
- 2 Mandates: Serpent Consulate (alt-win, tape 1), Broken Auction (tape 2)
- 2 Heroes: Felicity Graves (sup 4 / res 1, tape 1), Captain Crowbar Venn (sup 3 / res 2, tape 2)
- 6 Personnel: All `sup 2 / res 1`. Three are tape 0 (Black Market Reliquary, Counterfeit Oracle, Crowded Safehouse), three are tape 1.
- 4 Facilities (Wings): suppress +1 site bonus. One tape 0 (Black Market Reliquary), three tape 1.
- 4 Anomalies: GOI Borderless Site (haz 1, cur 4, tape 0) — the engine target. GOI Broken Auction (haz 2, cur 5, tape 1). Others haz 3 (avoid revealing).
- 7 Procedures, archetype = raid (NOT GOI Raid Tip-Off — that's a starter-deck card)

### Procedure effects (CRITICAL — derived from `_procedure_profile("raid", motif_index)`)
- **GOI Black Market Reliquary Protocol** (tape 0) — AUDIT opp (force_audit intensity 2): drops opp secrecy by `2 + opp_pending + opp_active_anomalies`. CORE alt-win lever.
- **GOI Counterfeit Oracle Protocol** (tape 0) — AUDIT opp (intensity 2). CORE alt-win lever.
- **GOI Crowded Safehouse Protocol** (tape 0) — AUDIT opp (intensity 2). CORE alt-win lever.
- **GOI Broken Auction Protocol** (tape 1) — misfile_audit: +2 paperwork on opp pending, or audit if none.
- **GOI Glass Insurgency Protocol** (tape 1) — Secrecy +1 / breach -1 (self-stabilize).
- **GOI Borderless Site Protocol** (tape 1) — Secrecy +1 / breach -1.
- **GOI Anomalous Embassy Protocol** (tape 1) — Secrecy +1 / breach -1.

## Key insight: triple audit is the kill button
Force_audit drops opp secrecy by `intensity (2) + opp_pending + opp_active_anomalies`. If opp has 2 pending + 1 active anomaly at the moment of audit, one audit drops their secrecy by 5. With 3 audit procedures, we can crater opp from secrecy 10 → 0 in three plays, much less than 6.

## Mulligan Policy
- Keep Mandate 1 (Serpent Consulate, tape 1) every time.
- Want at least 1 audit procedure (Black Market Reliquary Protocol is tape 0 — auto-include if drawn) and 1 personnel/hero in opener.
- Toss anomaly-heavy hands without staff, and toss high-haz anomalies (≥2) unless we can seal them.

## Sequencing
- **T1 (multi-dossier open)**: Open as many tape 0-1 dossiers as hand permits. Priorities:
  1. Mandate 1 (Serpent Consulate) — tape 1, primary win enabler
  2. Tape-0 facility (Black Market Reliquary Wing) — secrecy bonus engine
  3. Tape-0 specialists (Black Market Reliquary, Counterfeit Oracle, Crowded Safehouse) — sup 2 / res 1
  4. Tape-0 procedures (audit triple) — these are bullets
  5. Tape-0 anomaly (Borderless Site Anomaly, haz 1 cur 4) — research engine
  6. SEAL high-haz anomalies (haz 3) — never reveal, keep as memory-hole fodder or just dead-park
- **T2-T4**: Activate first procedures as their paperwork ticks down. Use research staff to research the Borderless Site Anomaly (cur 4 vs our research ~3-4 + 1 wing bonus) for +1 archive each time. Use audit procedures whenever they paperwork-tick to zero.
- **T5-T8**: Push archives to 4 via research engine + procedures. Push opp secrecy ≤ 6 via audit triple. Win.

## Anomaly priority
- **Borderless Site Anomaly (haz 1, cur 4, tape 0)** = canonical research engine like Cipher Hospital in ACW. OPEN unsealed, research repeatedly for archives.
- **Broken Auction Anomaly (haz 2, cur 5, tape 1)** = research-able if we have ≥5 research pool. Watch breach.
- **Anomalous Embassy / Black Market Reliquary Anomaly (haz 3, tape 2)** = SEAL for memory-hole fodder OR skip entirely. NEVER reveal.

## Matchup: vs Veil Control (VC)
- VC runs Protect Mandate (probably `redaction` or `veil_lockdown` alt-win — both want secrecy high or breach 0).
- VC has Witness Relocation (+sec 2), Null Room Calibration (-breach 2), Red-Team the Veil (-sec 1, -breach 2), Class-A Amnestic Broadcast (+sec 3 / +ethics 1), Incident Report Rewrite (+sec 1). Lots of secrecy stabilization.
- VC ALSO has **GOI Raid Tip-Off** (audits us!) and **Whistleblower Leak**-style audits typically. **We must brace our secrecy** with our +1 sec / -1 breach procedures (3 of them).
- KEY: VC will try to push their own secrecy ≥ 12 and lock archives + 0 breach. Our audit triple counters their high-secrecy plan AND moves us toward public_panic.
- **Watch for VC's redaction win**: if their secrecy hits ≥ 12 and they have ≥ 3 archives, they win — same as ACW iter1/2. Audit early to keep their secrecy ≤ 9.

## Risk Profile
- Anomalies are breach pressure — for raid we only need 1 active anomaly (Borderless Site) as engine.
- Audits cost +ethics_debt on us (intensity 2 → +1 ethics each audit). At 3 audits = +3 ethics. Acceptable; loss at 8+.
- Fast-tracking is fine if it lands a key piece T1 — we have 3 self-secrecy procedures to recover.

## Heuristic-Exploit Notes
- Opposing AI is heuristic baseline (scp_adapter.py) — plays one card per turn, no awareness of alt-win shortcuts.
- VC AI will likely accumulate secrecy passively. Don't let them stockpile.
- Public_panic check fires on any victory-checking event after archives ≥ 4 AND any opp ≤ 6 secrecy. Stack archives in parallel — don't audit too early or opp recovers.

## Win Plan Calendar
- T1: bank Mandate 1 + Black Market Reliquary Wing + tape-0 specialist + tape-0 audit procedure + Borderless Site Anomaly (if drawn) + Crowded Safehouse Wing-equivalent specialist.
- T3-T4: first archive via research on Borderless Site Anomaly.
- T5-T7: archives 2-4 via research repeats + Broken Auction Anomaly research if drawn.
- T7-T9: triple-audit opp to ≤ 6 secrecy (their starting 10 - 6 = need -4 net, accounting for their +sec procedures probably needing -6 to -8). Public_panic fires.

## Iteration 3 log (2026-05-12 — vs VC heuristic AI, seed 3030)

**Outcome**: LOSS T8 — Veil Control won via `veil_lockdown` alt-win (4 archives + 0 breach). Final my site: secrecy 11, breach 0, archives 0. Final opp site: secrecy 9, breach 0, archives 4.

**Draw failure**
- Mandate 1 (Serpent Consulate, public_panic alt-win) **never drew** — library slot 13 of 17. Without alt-win mandate on board, no alt-win path available.
- All 3 audit procedures (Black Market Reliquary, Counterfeit Oracle, Crowded Safehouse Protocols) — **none drew** by T8.

**What worked**
- Multi-dossier T1 (5 opens + 1 seal) was correct. Hand emptied turn 1. Good base for paperwork ticking.
- Sealing the haz-3 Reliquary Anomaly was correct — never paid the reveal hazard cost.
- Fast-tracking the Broken Auction Protocol at T5 was correct in spirit (audit opp) but the 1-secrecy hit + intensity-1 audit didn't move the needle enough to delay opp's win clock.

**Structural problems exposed**
1. **Raid archetype has NO +archive procedures.** All 7 procedures are audit/raid/defensive. Archive generation requires researching own anomalies — but the deck only has 4 anomalies, 3 of which are haz≥2 (dangerous). 
2. **Public_panic is a TWO-CLOCK alt-win** (4 archives AND opp sec ≤ 6). Slower than veil_lockdown's 1-clock (3 archives + 0 breach).
3. **Paperwork tick = 1 per OWN turn**. Tape 2 = 4 calendar turns to activate. Half the deck (Mandate 1, Mandate 2, Hero Crowbar) takes 4+ turns each.
4. **Heuristic VC AI exploits Protect Mandate text**: "Fully suppressed anomalies become contained Archives" — turns suppress-skill into a free archive engine. VC's Janitor (sup 3) + Field Agent (sup 2) generates archives by suppressing opp anomalies (or own).

**Plan revisions for next iter**
- **Win window is T11-T14, not T9-T11.** With draw variance, expecting T9 alt-win is unrealistic for this deck.
- **Mulligan policy must hard-aggressive for Mandate 1.** Toss any opener without Mandate 1 + Black Market Reliquary Protocol (tape 0 audit).
- **Audit timing**: audit BEFORE opp archives reach 2, not after. By the time opp is at arc=2 + sec=12, the audit clock is too slow.
- **Consider deckbuilder change**: duplicate Mandate 1 (Serpent Consulate) — 2 copies improves draw probability from 0.04 to 0.08 per turn.

**Engine quirk noted**
- `process_paperwork` ticks 1 per own-turn-begin. Manual inspection showed Captain Crowbar (tape 2 opened T1) still pending at pw=1 by T7. That's consistent with tick-per-own-turn but means tape ≥ 2 cards take 4+ calendar turns.

**Suggested balance changes**
- GOI Frontline buff: lower public_panic threshold to **3 archives + opp sec ≤ 6** (match redaction/veil_lockdown's archive count).
- OR add an archive-generating procedure to the raid pool — e.g. "Trigger a GOI raid AND gain an archive" or "Audit opp, gain an archive if their sec ≤ 8".
- OR Veil Control nerf: Protect Mandate alt-win → 4 archives + 0 breach (slows veil_lockdown to match others' clocks).

## Iteration 3 follow-up (2026-05-12 — convergent pilot reports)

Pilot A (this deck) and Pilot B (Veil Control opp) converged on a single
narrative: **the GOI loss was structural, not skill-driven**. The iter 1/2
"underperformer can be LLM-rescued" finding does NOT generalize to
GOI Frontline. Key structural weaknesses, in decreasing severity:

1. **Multi-axis alt-win mismatch.** public_panic (4 arc + opp sec ≤ 6) is a
   2-axis threshold that requires both archive stacking AND opp-sec
   disruption. Veil Control's veil_lockdown (3 arc + 0 breach) is 1-axis.
   In a head-to-head clock race, single-axis wins.
2. **Zero +archive procedures in raid pool.** All 4 archives must come
   from researching own anomalies. Deck has only 4 anomalies, 3 of them
   hazard ≥ 2. If the haz-1 Borderless Site Anomaly doesn't draw, the
   archive engine never starts.
3. **Protect Mandate's "fully suppressed → contained Archive" line gives
   VC a free 2-archives-per-suppress engine.** Each Janitor + Field Agent
   suppress = +2 archives at 0 breach. VC needs only 2 such conversions
   to win. This is *the* fastest archive-stacker in the game.
4. **Tape costs front-load the deck.** Mandate 1 (Serpent Consulate) at
   tape 1 takes 2 own-turns to activate; if it doesn't draw T1-T2, the
   alt-win path is unavailable until T5+. Mandate 2 (Broken Auction) at
   tape 2 takes 4 own-turns.

**Balance recommendations (pick one or combine):**
- **Lower public_panic threshold from 4 archives to 3 archives** (still
  requires opp sec ≤ 6 — keeps the disruption axis). Matches
  veil_lockdown's archive count.
- **Add a +archive raid procedure** — e.g. "Raid Calendar Protocol:
  +1 archive, opp sec -1, tape 1". Gives the deck an archive engine
  independent of anomaly draws.
- **Duplicate Mandate 1 (Serpent Consulate) — 2 copies instead of 1.**
  Draw probability per turn jumps from ~0.04 to ~0.08; mulligan-keep odds
  jump from 0.28 to 0.47 on a 7-card opener. Cheapest fix.

**Open question**: is GOI Frontline's underperformance a deckbuilder bug
(suboptimal selection from the raid card pool) or an archetype-level
weakness (raid card pool lacks +archive)? Worth a deckbuilder re-run with
a constraint "include >=1 archive-generating card if available in the
raid pool".

