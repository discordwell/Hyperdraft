# SCP Deck Optimization: Site Zero Redaction Lock

Final deck id: `site_zero_redaction_lock`

Goal: find the strongest legal 25-card SCP deck using both the older SCP pool and `Site Zero: Broken Masquerade` (`SZB`). SCP deckbuilder rules are 25-40 main deck cards with max 2 copies, so the final list uses a 25-card max-consistency shell.

## Final Decklist

- 2 There Is No Antimemetics Division
- 2 SZB Directive 1: White Pill Ward
- 2 D-Class Volunteer
- 2 Sleep-Deprived Intern
- 2 Memetics Analyst
- 2 SZB White Pill Ward Handler
- 2 SZB Memory Triage Handler
- 2 Memetics Lab
- 2 Redaction Office
- 2 Moth in the Camera
- 2 SZB White Pill Ward Anomaly
- 2 SZB Quiet Recital Protocol
- 1 Emergency Lockdown

## Why This Deck

The best performing shells were all built around fast redaction wins. `There Is No Antimemetics Division` and `SZB Directive 1: White Pill Ward` give redundant redaction mandates. Low-paperwork CORE staff and facilities turn `Moth in the Camera` and `SZB White Pill Ward Anomaly` into repeatable Archive engines, while `SZB Quiet Recital Protocol` adds direct Archive progress and breach relief. `Emergency Lockdown` is the single stabilizer slot for games where breach spikes before redaction closes.

Primary win pattern: resolve a redaction mandate, reach 3 Archives, and keep secrecy at 8+ with breach at 5 or lower. The deck also wins normal Archive games when the mandate is delayed.

## Candidate Results

Baseline registered-deck run: `logs/scp_deck_optimization_baseline.json`

- Best existing decks across 1,092 games: `site_zero_quarantine` 59.6%, `site_zero_veil_rotation` 57.1%, `antimemetic_cold_war` 55.1%, `keter_blackout` 54.5%.
- This made Quarantine/Redaction and Veil/Rotation the initial targets for mixed shells.

Round 1 mixed candidates: `logs/scp_deck_optimization_candidates_round1.json`

- `candidate_quarantine_redaction_lock`: 117-51, 69.6%.
- `candidate_quarantine_veil_hybrid`: 116-52, 69.0%.
- `candidate_veil_rotation_lockdown`: 103-65, 61.3%.
- `candidate_thaumiel_anchor_core`: 98-70, 58.3%.
- `candidate_clean_hands_ethics`: 87-81, 51.8%.
- `candidate_blackfile_public_panic`: 73-95, 43.5%.

Round 2 consistency variants: `logs/scp_deck_optimization_candidates_round2.json`

- `opt_redaction_lock_v2_consistency`: 170-82, 67.5%. Best result.
- `opt_redaction_lock_v1`: 166-86, 65.9%.
- `opt_quarantine_veil_v2`: 162-90, 64.3%.
- `opt_redaction_lock_v3_archive`: 156-96, 61.9%.
- `opt_lockdown_v2`: 141-111, 56.0%.
- `opt_public_panic_v2`: 133-119, 52.8%.

Final registered-field run: `logs/scp_deck_optimization_final.json`

- `site_zero_redaction_lock`: 193-59, 76.6% across all 15 registered SCP decks.
- Next-best registered decks in that run: `keter_blackout` 57.9%, `veil_control` 56.0%, `site_zero_veil_rotation` 55.2%, `site_zero_thaumiel` 54.0%.
- Main win routes across the event were Archives, breach pressure, and total redaction; this deck's matchup matrix was positive into every deck except an even 50.0% split with `keter_blackout`.

## Known Weaknesses

- The deck is tuned for the current heuristic AI. A human opponent may prioritize killing the redaction clock with exposure pressure more aggressively.
- It can still lose to fast Archive starts before the redaction mandate appears.
- It has only one true breach panic button, so repeated high-hazard starts can punish weak opening hands.
- It is intentionally above the balance band because this was an optimization task, not a fairness pass.
