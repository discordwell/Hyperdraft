# Secure / Contain / Research — Deck Plan

## Identity
The flagship "containment + archives" archetype. Open personnel/facilities first so
each subsequent anomaly slots into a research/contain test on the same turn it appears.
The deck is balanced across research and contain; suppression is a safety valve.

## Win Condition
Primary: drive `archives` to 7 via Research tests on revealed anomalies. Each contained
anomaly counts as an archive in the primary clock too, so containment doubles as scoring.
Alternate (Secure Mandate, alt_win = "thaumiel"): hold **4 contained anomalies at zero
breach**. This is the natural secondary line if a heavy-hazard anomaly forces containment
over research.

## Target Turn
Win by ~T8-10. Memetics Lab + Junior Researcher = research 2 on a Junior Researcher,
enough to clear most anomaly curiosities (1-3) the deck holds, especially with Observation
Theatre (+1 research +1 contain) stacked.

## Key Cards
- **Personnel (8):** Junior Researcher x2, Containment Specialist, D-Class Volunteer x2,
  Field Agent, Ethics Liaison, Sleep-Deprived Intern.
- **Facilities (4):** Site-19 Intake Wing (+1 contain), Memetics Lab (+1 research),
  Observation Theatre (+1 research/+1 contain), Redaction Office (+1 research/+1 suppress).
- **Anomalies (7):** Moth in the Camera (1 cont/2 curi/1 haz) — cheapest archive ever,
  Recursive Hallway (3/3/1), Patient Zero (4/5/3), Mirror That Interviews You (3/4/2),
  Red Room Static (4/4/2), Hostile Nursery Rhyme (3/5/2), Oracle Mold (5/3/3).
- **Procedures (5):** Class-A Amnestic Broadcast (+3 secrecy / +1 ethics),
  Emergency Lockdown (-3 breach), False Flag Cover Story (+2 secrecy / -1 breach),
  Friendly Fire Evacuation (-1 breach / +1 ethics), Incident Report Rewrite (+1 secrecy).
- **Mandate:** Secure Mandate (+1 contain, alt_win = thaumiel).

## Mulligan Policy
Keep any hand with **personnel + facility** ideally including Memetics Lab or Junior
Researcher. Drop heavy anomalies (Patient Zero, Oracle Mold, Hostile Nursery Rhyme) unless
backed by Field Agent/Containment Specialist. Always keep one breach answer (Emergency
Lockdown / Friendly Fire / False Flag) when an anomaly with Hazard >=2 is in hand.

## Sequencing — Generic
1. **Turn 1-2:** Open a Memetics Lab or Site-19 Intake Wing first when affordable.
   Open Junior Researcher / D-Class as second body. Skip anomalies until staff is on board.
2. **Turn 3-4:** Open Moth in the Camera or Recursive Hallway as a soft anomaly when you
   have at least 1 research-capable staff. **SEAL** heavy anomalies on entry if breach
   risk is high; **REVEAL** only when you can immediately research or contain.
3. **Turn 4-7:** Cycle the engine — open one card per turn, run research/contain tests.
   Use Friendly Fire / Lockdown / False Flag as breach hits 4-5. Class-A Amnestic if
   secrecy drops below 5 (ACW audit pressure).
4. **End-game:** With 4+ research bonus on the table, blast Patient Zero/Oracle Mold for
   3 archives each via research, OR contain them for the Secure Mandate alt-win.

## Matchup Notes vs antimemetic_cold_war
- ACW = redaction archetype. Plan is to audit our secrecy via Whistleblower Leak,
  Bureaucratic Labyrinth, GOI Tip-Off, and Antimemetic Anomalies with curi 4-7.
- **Key threats:**
  - **Audit pressure on secrecy.** ACW tries to drop our secrecy and trigger penalties.
    Counterplay: stack secrecy-positive procedures (Class-A Amnestic / False Flag / Incident
    Report Rewrite) and keep secrecy >=6 buffer.
  - **Cold-war breach drift.** ACW's anomalies have hazard 1-3; their breach pressure is
    moderate but steady. Emergency Lockdown timing matters.
- **Our advantages:**
  - We score archives via Research, which the ACW deck can't easily disrupt mid-test.
  - Containment Specialist (cont 2) + Site-19 (+1) = cont 3 on T2. ACW's anomalies aren't
    designed to defend against our scoring engine; they're designed to harass.
- **Sequencing:**
  - **Don't fast-track.** Secrecy is the lose-clock when audited.
  - Open Memetics Lab + Junior Researcher T1-T2 if drawn. Skip the Moth on T1 if no
    research staff yet.
  - Reveal sealed anomalies the same turn you can test them. Keep red tape pressure low.
  - Burn ethics for clearance only when an O5-tier card lands in hand (rare in SCR but
    a Black Budget on the other deck's pile could matter for them).

## Why the heuristic wins 76%
The SCR heuristic does the basics right: opens facility + personnel, then chains research
tests. ACW counters require precise audit-timing the heuristic can't pull off because the
SCR deck is just **faster to archive** than ACW is to audit secrecy below 0.

## LLM-only edges
1. **Reveal timing.** Sealing on entry then revealing the same turn we test means the
   reveal trigger (when present) fires while we have action economy. Heuristic seals
   sometimes; LLM should plan reveal+test pairing.
2. **Procedure ordering.** When secrecy is shaky, lead with Incident Report Rewrite (free)
   before False Flag / Class-A so we don't waste secrecy-positive procedures on overflow.
3. **Staff routing.** Send Junior Researcher to research (only skill they have). Send
   Containment Specialist to contain (cont 2). Don't waste Field Agent on research when a
   Junior is free.
4. **Don't dump anomalies into hand.** Slow-roll the anomaly opens; only one active anomaly
   at a time unless we have surplus assignment slots.

## Iteration 1 log (2026-05-12 — vs ACW LLM pilot)

**Outcome**: LOST T11 to ACW redaction alt-win (3 archives + secrecy 12). Final SCR site: secrecy=10 breach=0 archives=2 ethics=0. Plan called for a T8-T10 archive win — actual race was over before the engine ramped.

**Identified deckbuilding gap**
- **SCR has NO secrecy-audit cards.** The "Matchup Notes vs antimemetic_cold_war" section above lists Whistleblower Leak / Bureaucratic Labyrinth / GOI Tip-Off as ACW threats, but SCR itself does not run any of those cards. Against a redaction-piloting ACW, SCR has zero disruption against the alt-win path.
- The 76% baseline was measured against the heuristic ACW (which doesn't pursue alt-wins). Vs an LLM-piloted ACW that reliably finds the redaction combo, the matchup is far closer to 50-50 or favoring ACW.

**Recommendations**
- **Tech card swap**: drop a fragile late-game anomaly (Patient Zero of Yesterday is the prime candidate — pp 3 + curi 5 + hazard 3, slow to deploy and won't fire in a sub-T12 game) for ONE secrecy-audit option:
  - Whistleblower Leak / Bureaucratic Labyrinth (opp secrecy -1) — directly disrupts redaction
  - Or a custom "Cross-Examination" procedure
- **Alt-win pivot**: if facing an active redaction Mandate on the opponent's side, switch from primary 7-archive race to **Secure Mandate alt-win** (4 contained anomalies + 0 breach). Containment is faster than research for this matchup — lean into contain over research.
- **Mulligan rule vs known redaction opponent**: aggressively mulligan for any secrecy-debuff procedure (currently SCR has none — deckbuilder TODO).
- **Avoid long-paperwork anomalies in fast matchups**: pp ≥ 2 anomalies (Observation Theatre pp 2, Patient Zero pp 3) cost 4-6 calendar turns before they fire. In a T10-11 game these never activate. Prefer pp 0-1 cards.
- **Multi-open T2 confirmed efficient**: banking 3 facilities/personnel and a free secrecy procedure in turn 2 was the right shape, but T1 should have been the multi-open turn rather than T2.

**Open questions**
- Does SCR's primary 7-archive plan need a turn-budget rewrite to acknowledge the redaction matchup is unwinnable without a tech card? Possibly yes.
- Is the Secure Mandate alt-win (4 contained + 0 breach) actually faster than the redaction path? Containment Specialist (cont 2) + Site-19 (+1) + Observation Theatre (+1) = cont 4 lets us hit 1 contain/turn from T3-T4. Math says T7-T8 win window — competitive if anomaly draws cooperate.

## Iteration 2 log (2026-05-12 — vs ACW LLM pilot, different seed)

**Outcome**: Cap-stopped at T10 (10-min hard cap); trending loss. Final observed: SCR site secrecy=8 breach=6 archives=2 ethics=0 vs ACW secrecy=11 archives=2 breach=0. ACW was 1 archive + 1 secrecy from redaction alt-win at the cap. Pilot B (this side) projected to lose within 1-3 opponent turns.

**CRITICAL STRUCTURAL FINDING — contain-skill concentration is a single point of failure**
- The Secure Mandate alt-win (4 contained + 0 breach) requires reliable contain-skill availability. SCR currently has **only 4 contain-skill sources in 24 cards**: Containment Specialist, Site-19 Intake Wing, Observation Theatre, Redaction Office.
- Pilot B drew **ZERO contain-skill cards across T1-T10**. This makes the Secure Mandate alt-win **mathematically impossible** ~25% of games purely from draw variance.
- This is not bad piloting — it's a deckbuilding gap. The alt-win path is over-concentrated.

**Recommendation: deck redesign**
- Target **at least 7/24 contain-skill cards** (≈ 30% concentration) for statistical reliability of having contain available by T6-T8.
- Candidate adds: a second Containment Specialist, a second Site-19 Intake Wing, OR a new "Heavy Containment Liaison" personnel with contain 2 / pp 1. A tutor-effect ("search your deck for a Containment-skill personnel") would also work.
- Candidate drops: Patient Zero of Yesterday (pp 3, never fires before T12), Oracle Mold (haz 3 / cont 5 / curi 3 — uncontainable without specialist setup; becomes a dead breach-tick generator in unfavorable draws).
- Mulligan rule: aggressively mulligan for at least one contain-skill card; throw any opener with no contain-skill source.

**Secondary finding: re-poll packet between every apply**
- T2 misclick was fatal: pilot meant to seal Moth (action a003 at start-of-turn), but after banking Emergency Lockdown the action list reindexed and a003 became Oracle Mold fast-track. Cost: -2 secrecy and a haz-3 anomaly active T2 that dominated breach for the entire game.
- **Fast-track + lockdown interactions shift action indices**. Re-poll `legal_actions` before submitting EACH new action, even within the same turn.

**Other observations**
- **Mood-shift to docile is per-turn, not permanent.** Oracle Mold needed shifting twice (T4 and T10) — each costs 1 briefing. Briefing economy must scale with the anomaly's longevity, or shift to suppression as the long-term plan.
- **Moth in the Camera as research engine** worked: revealed T8, researched T8 and T10 for +2 archives. Confirms the "anomaly-as-engine" pattern works for SCR too — Moth (curi 2, haz 1) is exactly the right profile.
- **No Secure Mandate drawn** — even if contain-skill had been available, the alt-win flag itself wasn't active. The mandate may need either +1 copy or a "Mandate-tutor" mulligan rule.
- **Multi-open requires pp-0 cards**: SCR's T1 hand (Lockdown / Liaison / Incident Report / Moth / Oracle Mold) only had 1 pp-0 card. Pp-0 distribution is thinner than ACW's, limiting the multi-open advantage.

**Heuristic gap noted (for src/ai/scp_adapter.py)**
- Heuristic doesn't track contain-skill availability. After T3 with 0 contain skill drawn, it should switch from Secure Mandate alt-win mode to primary 7-archive race mode and avoid opening high-haz anomalies. The current heuristic decides based on hazard threshold alone.
- Coach note added (not a weight change yet — see scp_adapter.py top comment).
