# Antimemetic Cold War (ACW) — Deck Plan

## Win Condition
- **Primary**: ACW Mandate 1: Blind Library alt-win = **3 archives + secrecy ≥ 12** (cheapest of the alt-wins; lets us cash in earlier than racing to 7 archives).
- **Fallback**: 7 archives (standard) — slower but the deck has plenty of research throughput.

## Target Turn
- Mandate 1 down by turn 2-3, facilities + first specialist by turn 3-4.
- First archive (via Backmask / Blind Library Protocol or research on a low-curiosity anomaly) by turn 4-5.
- Win window: turns 7-10 — alt-win triggers as soon as we hit 3 archives while secrecy still rides at 12+.

## Key Cards
- **ACW Mandate 1: Blind Library** — alt-win enabler + research +1 bonus. Tape 1.
- **ACW Hero - Agent No-Name** (research 3 / suppress 2, tape 1) and **Hero - Archivist Lumen Rye** (research 3 / suppress 2 / contain 1, tape 2).
- **Specialists** (research 2-3, suppress 1) — most are tape 0-1, very castable.
- **Facilities** — research +1 site bonus stack; Backmask City and Blind Library Wings also add suppress.
- **Procedure: Backmask City / Blind Library Protocol** — Archive +1, secrecy +1, breach -1. Direct alt-win lever.
- **Procedure: Cipher Hospital Protocol** — secrecy +2, breach -1 (pure stabilizer for hitting secrecy ≥ 12).
- **Procedure: Absent Jury Protocol** — clearance +1.
- **Anomalies** — Blind Library Anomaly (tape 0) and Cipher Hospital Anomaly (tape 0) are cheapest entry points; we research them for archives if we have staff power; **avoid Backmask/Absent Jury Anomaly (tape 2)** unless we have a clear plan.

## Mulligan Policy
- Keep Mandate 1 in opener every time.
- Want at least one specialist or hero AND at least one facility/protocol in opening 6.
- Toss hands that are anomaly-heavy without staff — anomalies just feed breach without research-ers.

## Sequencing
- **T1**: Open Mandate 1 (tape 1). Keep secrecy ≥ 10. Do not fast-track unless absolutely needed.
- **T2**: Open a tape-0 facility (Backmask City Wing or Absent Jury Wing) — research +1 piles up.
- **T3**: Open a tape-0 specialist (Absent Jury Specialist or Backmask City Specialist with research 2-3).
- **T4+**: Drop another wing/specialist, and start cashing archives via Backmask City / Blind Library Protocol (Archive +1, secrecy +1, breach -1 → this is THE alt-win combo, single card both bumps archives and secrecy).
- Begin pulling anomalies (tape 0 ones first) once we have ≥ research 3 staff power to research them for archives.
- Cipher Hospital Protocol for secrecy padding when we are above 10 but need 12+.

## Matchup: vs Secure Contain Research (SCR)
- SCR runs Junior Researcher, Containment Specialist, Memetics Lab, Redaction Office, Class-A Amnestic Broadcast, etc. It is the **archetypal containment build** — research + contain.
- They will outpace us on traditional archives (they got 76% baseline vs our 9.5%).
- **Key**: do NOT try to out-archive them. Race the alt-win — we just need 3 archives and 12 secrecy.
- They have some auditing (False Flag Cover Story, Incident Report Rewrite) that could drop our secrecy. So we must keep secrecy buffers high — **target 14+** to absorb an audit drop and still threshold 12.
- They are likely to develop personnel + facilities for archive engine. We should avoid drawing breach attention; opening anomalies on our side is risky if we cannot resolve them quickly.
- **Tempo bend**: fast-tracking is OK in turn 1-2 if it lets us land Mandate 1 + a facility on the same turn — secrecy −1 from 10 → 9 is recoverable via Cipher Hospital Protocol or Backmask/Blind Library Protocol (both +1 secrecy).

## Risk Profile
- Anomalies + hazard = breach pressure → we must research/contain promptly. Suppression is fine as breach control even if it doesn't archive.
- Ethics is not our axis — keep ethics_debt at 0. No need to spend ethics for clearance.
- Clearance: we start at 2. Some cards require clearance — keep an Absent Jury Protocol around to push to 3 if needed.

## Heuristic-Exploit Notes
- The opposing AI (per `scp_adapter.py`) will likely run the `containment` or `archivist` pilot. It prioritizes Personnel > Mandate > Facility > anomalies. It will play one dossier per turn. It does NOT consider alt-win shortcuts; it just plays out the long game. Our alt-win shortcut is the lever.
- The AI does not target our Site unless its deck has audit procedures. SCR runs few auditors — so secrecy 12+ is achievable if we stop sliding it down via fast-track.

## Iteration 1 log (2026-05-12 — vs SCR LLM pilot)

**Outcome**: WON T11 via `total_redaction` alt-win (Blind Library — 3 archives + secrecy 12). Final ACW site: secrecy=12 breach=2 archives=4 ethics=0. Final SCR site: secrecy=10 breach=0 archives=2.

**Confirmed plan elements (worked as designed)**
- The redaction alt-win bridge worked end-to-end: bank low-tape engine T1, research own anomaly for cheap archives, finish on a secrecy bump.
- Cipher Hospital Anomaly (haz 1, curi 4) was the dominant archive engine — researched 5 times in the game for 5 archives.
- Mood-shift docile (-1 hazard) zeroed our own anomaly's breach tick after one briefing token.

**Refinements for next iteration**
- **Multi-dossier T1 is mandatory, not optional.** Open all 5-6 playable dossiers turn 1 if hand permits (Mandate 1 + 2 Wings + 1-2 Specialists + a tape-0 procedure). Paperwork ticks once per YOUR turn — every banked dossier turns into a free activation later.
- **Memory-hole bridge plan**: once archives ≥ 4 and secrecy is 10-11, memory-hole any pending non-active dossier (Mandate 2 or an unfilled Specialist) to trade -1 archive for +1 secrecy. This is the alt-win bridge to 12. NOTE: `memory_hole` does NOT call `check_scp_victory` directly; the win is only declared when the next victory-checking event fires (e.g. the EOT breach_tick). Plan to memory-hole on a turn that ends with at least one anomaly active so the breach_tick fires the victory check.
- **Anomaly priority**: open Cipher Hospital Anomaly or Blind Library Anomaly (tape 0, hazard ≤ 2, curi 3-4) early as research engines. Avoid Backmask/Absent Jury Anomaly (tape 2) unless explicit plan to break through tape.
- **Win window pulled in**: with multi-dossier T1, the win window is T7-T11 rather than T7-T10 in the original plan. T11 is the conservative line; T8-T9 is achievable if Cipher Hospital Protocol draws early for free secrecy.
- **Mulligan refinement**: keep Mandate 1 + 1 tape-0 facility + 1 specialist as the dream opener. Tape-0 Backmask City Protocol is the highest-impact single card (Archive +1, secrecy +1, breach -1).
- **Engine quirk to track**: opening an anomaly triggers an immediate `SCP_BREACH_TICK` on its hazard, not only at EOT. Anomalies cost ~1 breach up front.

## Iteration 2 log (2026-05-12 — vs SCR LLM pilot, different seed)

**Outcome**: WON T14 via **opponent breach overflow** (SCR site hit breach 11 at EOT T14, exceeding loss threshold of 10). ACW alt-win bridge was 1 turn away — T15 plan was research Backmask (arc 3→4) + memory-hole Absent Jury Anomaly (arc 4→3, sec 11→12) for redaction win. Final ACW site: secrecy=10 breach=4 archives=3 ethics=0. Final SCR site: secrecy=12 breach=11 archives=2.

**Reproducibility confirmed**
- Multi-dossier T1 (5 opens) works the same way under a different seed.
- Anomaly-as-engine still works with a higher-hazard draw: **Backmask City Anomaly (haz 3, curi 3) replaced iter 1's Cipher Hospital (haz 1, curi 4)**. With research pool ~15 vs curi 3, the engine fires regardless. Higher haz cost more breach management (briefing + mood-shift docile) but the plan held.
- Mood-shift docile (-1 hazard) is per-turn-effective but **not permanent** — needs re-shifting if the anomaly stays active multiple turns. Briefing economy must keep up.
- Memory-hole `check_scp_victory` engine fix is applied (verified): memory-hole now triggers alt-win immediately, no longer requires a downstream event.

**New tactic: sealed anomaly as memory-hole fodder**
- Drew Absent Jury Anomaly on T11 and opened it `sealed=true`. Sealed anomalies don't paperwork-tick, don't auto-activate, and don't fire on-reveal hazard. They remain a legal `SCP_MEMORY_HOLE` target indefinitely.
- This is the **clean memory-hole bridge** — stockpile fodder without paying activation breach. The planned T15 redaction win was going to memory-hole this sealed Absent Jury for -1 arc / +1 sec to cross the secrecy 12 line.
- Pattern: when you draw a high-haz / high-tape anomaly that you won't research yourself, seal it as a future memory-hole reservoir rather than passing on the dossier entirely.

**New observation: opp breach-overflow self-destruct as alternate win path**
- SCR fast-tracked Oracle Mold (haz 3) T2 with only Ethics Liaison (sup 2) as contain/suppress. They never assembled enough contain throughput. By T14, Oracle Mold haz 3 + Moth haz 1 + paperwork ticks pushed their breach 8 → 11 in one EOT.
- This is a real alternate win path: when an opponent stacks anomalies without contain pieces, watch their breach + active haz_sum. If ≥ 9 at start of their turn, they likely auto-lose at EOT.
- Strategically: a redaction pilot can sometimes win by just **waiting one extra turn** rather than racing to alt-win, if the opponent's breach clock is faster than our archive bridge.

**Hidden value reinforced**
- `hostility_spike` resolution gave +1 brief AND -1 breach (T13) — free tempo, slot-free. Strictly always resolve.
- Sealed anomalies don't burn paperwork ticks, so they're cheaper than banked dossiers.

**Friction noted**
- Pilot B (SCR) stalled twice (T12, T14) — likely LLM rate-limit / context issue. Harness fallback ended their turn cleanly. Pilot A still won, but the asymmetric turn count makes the SCR side under-observed.
- Staff routing is all-or-nothing per task — legal_actions only offers "research/contain/suppress with ALL fresh staff", can't split across slots. Wasted second slot on most turns where research consumed all fresh staff.

**Win window holds**: T13-T15 alt-win, with T14 opp-collapse alternative if SCR over-anomaly-greedy.
