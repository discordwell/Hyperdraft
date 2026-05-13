# Veil Control Deck Plan

## Core Identity
- **Mandate**: Protect Mandate (alt-win `veil_lockdown` = 3 archives + 0 breach).
- **Bonus**: +1 to all suppression checks.
- **Win conditions**:
  1. **Primary alt-win**: 3 Archives at 0 breach.
  2. **Fallback**: 7 Archives or opp Site collapse (breach 10+, secrecy 0).

## Deck Composition (25 cards)
- **Personnel** (8): Field Agent x2 (suppress 2, jack of all), Ethics Liaison (sup 2),
  Memetics Analyst (res 2 sup 1), Janitor Who Knows Too Much (sup 3, contain 1),
  Sleep-Deprived Intern (res/sup), Junior Researcher (res 1), D-Class (utility).
- **Facilities** (4): Redaction Office (research+sup +1), Amnestic Pharmacy (+1 sup),
  Reality Anchor Array (+2 sup, tape 2), Cafeteria 3AM (sup/contain, tape 0).
- **Anomalies** (5): Red Room Static (hz 2 cur 4), Door Sideways (hz 2 cur 2),
  Patient Zero Yesterday (hz 3 cur 5), Hostile Nursery Rhyme (hz 2 cur 5),
  Antimemetic Orchard (hz 2 cur 5), The Helpful Knife (hz 2 cur 3).
- **Procedures** (7): Class-A Amnestic Broadcast (sec +3), Witness Relocation
  (sec +2), Null Room Calibration (breach -2), Red-Team the Veil (breach -2),
  GOI Raid Tip-Off, Incident Report Rewrite (sec +1).
- **Mandate**: Protect Mandate.

## Game Plan

### T1-T2 (Setup)
- Multi-open: bank personnel + facilities (low tape) on T1.
- Open Protect Mandate ASAP (T1-T2).
- Avoid revealing anomalies that trigger breach without contain/suppress online.

### T3-T6 (Stabilize Suppression Engine)
- Bring Reality Anchor Array online (suppress +2 stack).
- Begin opening low-hazard anomalies SEALED (deploy as memory-hole fodder or controlled).
- Per-mandate text: "Fully suppressed anomalies become contained Archives." Suppress
  builds archives directly without breach pressure.

### T7+ (Lockdown)
- Push toward 3 Archives via fully-suppressed anomalies.
- Drop active haz to 0 via Null Room + Red-Team-Veil.
- Trigger alt-win once breach is 0 and archives ≥ 3.

## Threats from GOI Frontline
- `public_panic` alt-win: opp needs 4 archives + my secrecy ≤ 6.
- Starting secrecy 10. **Hard floor: secrecy ≥ 7 always**.
- Avoid Class-A Amnestic if ethics already loaded; secrecy gains are gold.
- Opp will run GOI Raid Tip-Off cards: may slash my secrecy → counter with
  Witness Relocation / Incident Report Rewrite.

## Specific Heuristic Rules
1. **Suppression > Contain > Research priority** for staffing (Protect Mandate gives sup +1, Redaction/Pharmacy/Array stack).
2. **0 breach is sacred**: if active haz sum > 0 at EOT, suppress/null-room before scoring.
3. Memory-hole only if archive surplus AND alt-win blocked (rarely; veil_lockdown only needs 3).
4. Open anomalies SEALED first turn, reveal only when suppression online (sup ≥ hazard).
5. Resolve incidents (hostility_spike = -1 breach + briefing) immediately.
6. Mood-shift to docile for any haz>1 anomaly to reduce passive breach.

## Iteration 3 log (2026-05-12 — vs GOI Frontline LLM pilot)

**Outcome**: WIN T8 via `veil_lockdown` alt-win. Final: secrecy 9 /
breach 0 / archives 4 (target 3). Opp ended at 0 archives, 0 anomalies on
field, no Mandate opened.

**Engine truth confirmed (and doc corrected)**
- **Suppress-to-contain pays 2 archives per conversion**, not 1
  (`scp.py:531`: `gain_archives(... 2 ...)`). veil_lockdown's 3-archive
  threshold is therefore reachable in **2 successful suppressions**.
- **Reveal does NOT tick hazard.** Empirically: revealing Helpful Knife
  (T4) and fast-tracking Red Room Static (T8) both left breach at 0.
  Engine confirmation: `_activate_dossier` in `scp.py:172` emits
  `SCP_ANOMALY_REVEALED` but does NOT call `breach_tick`; breach only
  ticks once per turn at EOT (`scp_turn.py:80`). The strategy doc
  previously claimed on-reveal hazard ticks — that has been corrected.
- **Suppress target = `max(hazard, containment)`** (`scp.py:_effective_*`
  helpers). Helpful Knife (haz 2 cont 2) → target 2. Red Room Static
  (haz 2 cont 2) → target 2. Both clear with Janitor (sup 3) +
  Mandate (+1) = sup 4.

**Winning loop (replicable)**
1. **T1-T2 multi-open**: bank Mandate + Janitor + Field Agent + a
   facility + a procedure. Seal one low-hazard anomaly (haz≤2,
   cont≤3).
2. **T3-T4**: reveal sealed anomaly when staff are ready. Suppress
   immediately = +2 archives, +1 contained, breach unchanged.
3. **T5-T7**: open + suppress a second anomaly (fast-track if needed —
   surplus secrecy is cheap when opp has 0 archives). 2 suppress-to-
   contain conversions = 4 archives ≥ threshold 3.
4. **Win at end-of-turn** once archives ≥ 3 and breach == 0.

**Notes for heuristic AI tuning**
- "veil" preset (`breach_danger=3`, `anomaly_staff_threshold=2`) already
  prioritizes suppress correctly via the veil_lockdown branch in `plan()`
  at `scp_adapter.py:486`. The branch fires when `suppress_power >=
  redaction_target`, which is correct for max(haz, cont).
- Possible refinement: raise `anomaly_staff_threshold` from 2 to 3 for
  the "veil" preset. Iter 3 evidence: opening anomalies *sealed* first,
  then waiting for full suppress staff, is the optimal play. Raising the
  threshold biases against premature anomaly opens.
- **Do not memory-hole**: veil_lockdown's path is suppress-to-contain,
  not redaction-bridge. Each archive is worth keeping.

**Matchup verdict**: VC 67% / GOI 24% baseline reproduces. GOI's
multi-axis public_panic alt-win combined with the raid pool's lack of
+archive procedures means VC's suppress-to-contain pipeline almost
always finishes first. The iter 1/2 "underperformer rescuable by LLM"
narrative does NOT apply here — GOI's gap is structural.

