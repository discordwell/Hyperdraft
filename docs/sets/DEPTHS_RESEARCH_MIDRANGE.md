# DEPTHS Research Midrange

Second-stage mixed Depths optimization result using the full SUBS + ABYS pool.

## Final Deck

Registered label: `DEPTHS_research_midrange`

| Count | Card | Set | Role |
|---:|---|---|---|
| 4 | Sample Drone | ABYS | Cheap homing pressure |
| 4 | Probe Scribe | ABYS | Scan plus draw velocity |
| 4 | Archive Submersible | ABYS | Main homing closer |
| 4 | Bathymetry Intern | ABYS | Early hull and SC growth |
| 4 | Echo Graduate | ABYS | Silent-running stabilizer |
| 4 | Black Smoker | ABYS | High-hull Vent/pressure body |
| 3 | U-Boat Wolf-cub | SUBS | One-charge attacker |
| 3 | Surface Skirmisher | SUBS | Torpedo-side pressure |

## Candidate Results

All probes used the Depths medium AI with `max_turns=60`.

| Candidate | Main idea | Probe result |
|---|---|---:|
| `OPT_research_pack` | Stock ABYS Research core plus SUBS aggro | 28-2 in probe 1; 50-9-1 in probe 2 |
| `OPT_homing_aggro` | Sample Drone, Patrol Bomber, Archive, Convoy finishers | 23-6-1 in probe 1 |
| `OPT_carrier_research` | SUBS Carrier drone shell plus ABYS Research | 16-14 in probe 1 |
| `OPT_thermal_wolfpack` | SUBS Wolfpack curve plus ABYS Thermals and Archive | 24-6 in probe 1; 46-14 in probe 2 |
| `OPT_convoy_research` | Convoy formation bodies plus Research closers | 21-9 in probe 1 |
| `OPT_salvage_research` | Salvage attrition plus Research closers | 23-7 in probe 1 |
| `OPT_research_dense` | Denser cheap Research with more 5-of counts | 31-27-2 in probe 2 |
| `OPT_research_archive6` | Six Archive Submersibles | 42-16-2 in probe 2 |
| `OPT_archive_salvage` | Archive plus Wreck Lantern/Patchplate Rover | 41-18-1 in probe 2 |
| `OPT_research_midrange` | Research core plus Black Smoker and SUBS pressure | 49-8-3 in probe 2; 81-14-5 in finals |

Finals pod (`logs/depths_optimized_finals.json`) ran 550 games across the top five candidates, best stock ABYS decks, and best SUBS decks. `DEPTHS_research_midrange` led the pod at 81.0% win rate, with no engine errors. It went 10-0 against stock `ABYS_research`, 10-0 against stock `ABYS_convoy`, 10-0 against `ABYS_leviathans`, 10-0 against `SUBS_silent_hunter`, and 10-0 against `SUBS_wolfpack`.

Registered-label validation (`logs/depths_registered_final.json`) ran the committed `DEPTHS_research_midrange` factory against every SUBS and ABYS starter at three games per pairing. The deck finished 31-1-1, 93.9% win rate, with zero errors.

## Card Choice Notes

The strongest pattern was not pure aggro or pure Research. The medium AI rewards high `(power + hull) / cost` bodies, but it also needs enough two-damage attackers to close games. `Probe Scribe`, `Bathymetry Intern`, and `Echo Graduate` keep the deck stable and charge-rich while `Sample Drone`, `Archive Submersible`, `U-Boat Wolf-cub`, and `Surface Skirmisher` convert those turns into flagship damage. `Black Smoker` outperformed the higher-top-end package because it is castable, has enough hull to survive, and gives the deck a strong sonar-cost body without clogging on expensive legends.

Known weakness: finals still showed close mirrors against other optimized Archive shells. The result is strongest against the registered starter field and current medium AI; a future hard-AI or human-piloted metagame may value different combat tricks and late-game legends.
