# ABYS - Abyssal Expanse

Depths expansion set 2. `ABYS` adds 180 playable cards under
`src/cards/depths/abyssal_expanse/`, split into six 30-card archetype modules:

- Thermals: Vent-ramp midrange.
- Salvage: attrition and death-value.
- Leviathans: deep pressure threats.
- Convoy: formation attacks and escort swarms.
- Minefield: scan, mines, and detection control.
- Research: scan/draw into homing closers.

## Mechanics

- Vent: triggers when a Vessel dives to DEEP/CRUSH; refunds charges, pumps, or draws.
- Salvage: triggers when a Vessel is sunk; grants charges/cards or leaves a Drone.
- Formation N: attack bonuses when enough friendly Vessels attack together.
- Scan: marks opposing Vessels detected, usually on ETB or action resolution.
- Pressure: static bonus while a Vessel is at DEEP/CRUSH.
- Abyss Drones: 1/1 homing Drone tokens used by Salvage, Convoy, Research, and Carrier-like payoffs.

The Depths engine has no per-card target prompt for these custom effects yet, so Scan and damage effects use deterministic simulation targets: first legal opposing Vessel or lowest-hull opposing Vessel. That limitation is documented in `src/cards/depths/abyssal_expanse/_mechanics.py`.

## Costing Notes

Costs were priced against existing SUBS benchmarks and the `cost-cards` curve:

- 1-cost Vessels stay around 2/1, 1/2, or 0/3 unless their ability is mostly setup.
- 2-cost Vessels can be 2/3 or 3/2 with conditional text.
- Homing adds about one charge unless the body is fragile.
- Repeat engines such as Drone creation, scan every turn, or same-depth lords were moved to 3+ total charges during balance.
- Build-arounds were intentionally pushed by about half a charge, then corrected by tournament results.

## Starter Decks

Registered labels:

- `ABYS_thermals`
- `ABYS_salvage`
- `ABYS_leviathans`
- `ABYS_convoy`
- `ABYS_minefield`
- `ABYS_research`

These are available through the Depths tournament adapter, demo script, and wet-test harness.

## Balance Result

Ten full ABYS round-robin passes were run and written to `logs/depths_abys_pass1.json` through `logs/depths_abys_pass10.json`.

Final validated pass before the last Convoy correction had five decks in/near range and Convoy underperforming:

- Thermals: 60.0%
- Salvage: 60.0%
- Leviathans: 66.7%
- Minefield: 46.7%
- Research: 60.0%
- Convoy: 0.0%

Pass 10 intentionally tested a Convoy rescue patch and overcorrected to 100%. The committed Convoy list has been toned down after that pass, but it needs another tournament sample before treating Convoy as solved.

## Best Current Candidates

- `ABYS_leviathans`: best raw pass 9 win rate among stable lists, but still sensitive to deep-start tuning.
- `ABYS_research`: strong after Archive Submersible became castable; likely a real contender.
- `ABYS_thermals`: playable Vent midrange, with Geyser Runner as the key payoff.
- `ABYS_salvage`: around 60% in pass 9 but can swing with Drone engine tuning.

## Residual Risks

- Convoy final toned-down list is post-pass-10 and needs one more full sample.
- Depths AI still produces high `DEPTHS_SURFACE_VESSEL` counts; this can distort deep archetype results.
- Action-created Drone damage is not always attributed cleanly in card-score output.
- Some equipment-style activated abilities are approximated or left as stat grants because the Depths activation path currently prefers simple dict abilities.
