# SCP Site Zero: Broken Masquerade Balance Notes

Expansion code: `SZB`

Card count: 180 cards across six 30-card packages.

Mechanics:

- `Brief`: adds briefing tokens for mood shifts and incident play.
- `Blackfile`: adds paperwork to opposing pending dossiers, or audits when no pending dossier exists.
- `Anchor`: binds contained anomalies to active threats through cross-containment.
- `Quarantine`: applies safer moods/protocols to active or revealed anomalies.
- `Overexpose`: trades secrecy/ethics pressure for archive or clearance tempo.
- `Rotation`: refunds a used assignment and refreshes exhausted staff.

Costing model:

SCP red tape was treated as delay, not mana. Zero-red-tape cards were kept to low stats or clock-risk effects. Red tape 1 is the default for efficient staff/procedures. Red tape 2+ is used for compression cards, high-clearance bonuses, and pushed build-arounds. Procedures that generate Archives also carry breach, secrecy, or ethics pressure unless they require a board setup such as Anchor.

## Archetypes

- `site_zero_masquerade`: Blackfile and Overexpose pressure. Wins through public panic or by converting opponent exposure into Archives.
- `site_zero_quarantine`: Brief/Quarantine redaction. Wins by researching safer anomalies and maintaining high secrecy.
- `site_zero_thaumiel`: Anchor grid. Wins by containing anomalies and using contained threats as countermeasures.
- `site_zero_blackfile`: Bureaucratic tempo. Wins by slowing rival dossiers while building Archives through paperwork engines.
- `site_zero_clean_hands`: Ethics audit. Wins by keeping ethics debt low while turning testimony into stable Archives.
- `site_zero_veil_rotation`: Rotation control. Wins by refreshing staff, suppressing hazards, and using risky archive bursts.

## Balance Passes

Target band: 35%-65% deck win rate. Small passes used same-pilot `balanced` runs; pass 9 and pass 10 used three games per matchup.

1. `logs/scp_site_zero_pass1.json`: Initial smoke tournament. Masquerade and Quarantine were too low; Thaumiel, Clean Hands, and Veil Rotation were too high. Found a Rotation bug: it permanently increased assignment slots.
2. `logs/scp_site_zero_pass2.json`: Fixed Rotation to refund a used assignment instead of increasing base slots. Quarantine and Blackfile moved into band; Veil Rotation remained too high and Thaumiel/Clean Hands under-corrected.
3. `logs/scp_site_zero_pass3.json`: Removed Veil Rotation's alternate-win shortcut; added Archive payoff to Anchor and ethics discharge. Four decks moved into band; Clean Hands was too high and Masquerade still low.
4. `logs/scp_site_zero_pass4.json`: Tightened `ethics_audit` to require ethics debt <= 2 and added Archive payoff to counter-raids. Clean Hands moved into band; Veil remained high and Masquerade low.
5. `logs/scp_site_zero_pass5.json`: Added Archive payoff to Masquerade Blackfile procedures and trimmed Veil's free Archive line. Result was noisy; Blackfile and Clean Hands spiked while Masquerade still underperformed.
6. `logs/scp_site_zero_pass6.json`: Added Masquerade research payoff and AI public-panic research priority. Five decks were in band; Masquerade remained low at 20%.
7. `logs/scp_site_zero_pass7.json`: Reduced Masquerade self-hazard and added Brief on some reveals. Masquerade reached 50%; only Thaumiel high and Veil low on a 30-game run.
8. `logs/scp_site_zero_pass8.json`: Restored a risky Veil archive line at breach +1. This over-buffed Veil and left Masquerade low in that sample.
9. `logs/scp_site_zero_pass9.json`: Public panic threshold changed from opposing secrecy <= 5 to <= 6; Veil archive burst set to breach +2. Larger 45-game result was close: Quarantine, Thaumiel, Blackfile in band; Masquerade and Clean Hands one win below band; Veil one win above band.
10. `logs/scp_site_zero_pass10.json`: Tested breach +3 on Veil's archive burst. This overcorrected; final code reverted to pass-9's breach +2 value after the pass.

## Final Candidate Decks

Best current candidates by repeated tournament signal:

- `site_zero_quarantine`: strongest overall ceiling. Pass 9: 60%; pass 10: 73.3%. Watch for redaction snowballing.
- `site_zero_blackfile`: most stable disruptive deck. Pass 6: 60%; pass 9: 60%; pass 10: 46.7%.
- `site_zero_clean_hands`: stable midrange/control shell after ethics-audit tightening. Pass 9: 33.3%; pass 10: 60%, with high sample sensitivity.
- `site_zero_masquerade`: improved from nonfunctional to viable after hazard and AI changes. Pass 7: 50%; pass 9: 33.3%; pass 10: 46.7%.

Decks needing more sampling:

- `site_zero_veil_rotation`: sensitive to one Archive procedure. Final code uses pass-9 breach +2 setting, where it was slightly high at 66.7%.
- `site_zero_thaumiel`: close to band but matchup-polarized; Anchor payoff may need a larger sample before further nerfs.

## Residual Risks

- Tournament samples are still small; 45-game passes showed matchup noise around the 35%-65% thresholds.
- The SCP AI uses deterministic target selection for targetless procedures. Cards that would be modal in paper choose the highest-hazard active anomaly or first pending dossier.
- Public panic and ethics audit are global engine alternate-win changes, not SZB-only changes. Existing GOI/Ethics decks were not fully revalidated after those calibration changes.
- The art manifest has prompts and target paths for all 180 SZB cards, but no generated image assets were created.
