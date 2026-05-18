# Custom Set Depth Baseline (v2 rubric) — 2026-05-18

First sweep of the v2 mechanical-depth heuristic across every set in
`src/cards/custom/`. The audit was previously unreachable because
`scripts/play/custom_set_depth_report.py` only registered 5 set profiles;
this run extends the registry to all 19 custom sets and provides the
headline numbers that should drive prioritization of the next spice
passes.

Raw JSON: `logs/custom_set_depth_baseline_2026-05-18.json`.

## Health gates (v2 rubric)

A set is considered healthy when all four pass:

- `median_depth ≥ 2`
- `axis_diversity ≥ 0.08`
- `code_diversity ≥ 0.40`
- `thin_ratio ≤ 0.90`

## Headline numbers — worst → best

| Set | Cards | Median | Mean | Axis div | Code div | Thin % | Wired % | Gates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **mtg_zld** Legend of Zelda | 207 | 0 | 0.05 | 0.019 | 0.128 | 100.0 | 18.8 | **0/4** |
| **mtg_pkh** Pokemon Horizons | 249 | 0 | 0.11 | 0.028 | 0.045 | 98.4 | 97.6 | **0/4** |
| mtg_hpw Harry Potter | 194 | 0 | 0.13 | 0.041 | 0.857 | 100.0 | 14.4 | 1/4 |
| mtg_finc Final Fantasy | 275 | 0 | 0.22 | 0.040 | 0.808 | 99.3 | 18.9 | 1/4 |
| mtg_dbz Dragon Ball | 225 | 0 | 0.24 | 0.058 | 0.795 | 99.1 | 19.6 | 1/4 |
| mtg_ltr Lord of the Rings | 187 | 0 | 0.26 | 0.043 | 0.633 | 97.9 | 26.2 | 1/4 |
| mtg_mvl Marvel Avengers | 187 | 0 | 0.29 | 0.043 | 0.750 | 99.5 | 27.8 | 1/4 |
| mtg_opc One Piece | 296 | 0 | 0.33 | 0.047 | 0.733 | 97.6 | 20.3 | 1/4 |
| mtg_dms Demon Slayer | 251 | 0 | 0.43 | 0.032 | 0.784 | 98.0 | 20.3 | 1/4 |
| mtg_jjk Jujutsu Kaisen | 222 | 0 | 0.43 | 0.041 | 0.634 | 96.4 | 41.9 | 1/4 |
| mtg_mha My Hero Academia | 255 | 0 | 0.46 | 0.035 | 0.636 | 95.3 | 38.8 | 1/4 |
| mtg_swr Star Wars | 289 | 0 | 0.46 | 0.048 | 0.840 | 97.6 | 26.0 | 1/4 |
| mtg_tmh Temporal Horizons | 276 | 0 | 0.46 | 0.054 | 0.752 | 98.2 | 39.5 | 1/4 |
| mtg_nrt Naruto | 222 | 0 | 0.51 | 0.036 | 0.787 | 95.5 | 33.8 | 1/4 |
| mtg_spmc Spider-Man | 209 | 0 | 0.52 | 0.072 | 0.651 | 98.1 | 52.2 | 1/4 |
| mtg_aot Attack on Titan | 254 | 0 | 0.54 | 0.047 | 0.472 | 96.9 | 56.7 | 1/4 |
| mtg_tlac Avatar TLA | 286 | 0 | 0.69 | 0.056 | 0.611 | 94.8 | 52.1 | 1/4 |
| mtg_lrw Lorwyn Custom | 408 | 0 | 0.72 | 0.039 | 0.528 | 96.1 | 34.8 | 1/4 |
| mtg_ghb Studio Ghibli | 195 | 0 | 0.58 | 0.082 | 0.912 | 94.9 | 34.9 | 2/4 |
| **modern_mtg** Bloomburrow (benchmark) | 280 | 2 | 1.61 | 0.089 | 0.774 | 88.9 | 80.7 | **4/4** |

**Every custom MTG set fails the depth gates.** Only `mtg_ghb` passes 2/4
(thanks to higher code diversity); the rest pass 0–1/4. The benchmark
(Bloomburrow) passes all four.

## Highest-leverage targets

### `mtg_zld` — 34-card reskin cluster of unwired vanilla cards

The single largest reskin cluster across all custom sets. 34 cards share
the empty-callable fingerprint:

> Daruk Goron Champion, Darunia Goron Chief, Din Oracle of Power,
> Divine Beast Vah Medoh/Naboris/Rudania, …

These are flavorful legendaries with no engine wiring. A spice pass here
could (a) wire 6–10 of them with distinct mechanics, and (b) add 8–12
new format-defining picks (Triforce of Power/Wisdom/Courage, Master
Sword, Champion transformations).

ZLD has the worst mean (0.05), lowest axis diversity (0.019), and lowest
code diversity (0.128) of any custom set — the methodology will land
maximum measurable impact here.

### `mtg_pkh` — 233-card reskin cluster despite 97.6% wired

PKH already received a spice pass (v1→v2 documented in `spice-pass.md`),
but the underlying set still scores median 0. **233 of 249 cards share
one code fingerprint** — they're mostly identical etb_damage / draw / ramp
shells with different flavor. The earlier spice pass added 8 build-around
mythics; this audit shows the bulk of the set is still a single template.

This is the same problem documented in `docs/sets/pkm_brv_depth_audit.md`
for Pokemon BRV. PKH needs a *bulk re-wiring pass* (similar to the
spice-pass methodology but applied to the reskin cluster, not just
top-of-curve cards). That work pattern doesn't yet exist as a named skill.

### `mtg_hpw` — vanilla volume (only 14.4% wired)

194 cards, 85% unwired. Different from PKH — there's no reskin cluster,
just a sea of stat-line-only creatures and one-line vanilla spells. The
classical spice-pass shape (add 15 format-defining picks) applies
cleanly.

## Methodology gap surfaced by this audit

**Reskin-cluster cleanup is not a documented skill.** `spice-pass.md`
covers adding format-defining cards (15-pick shape). `engine_gaps.md`
covers "this card can't be wired yet because engine X is missing." Neither
addresses **the case PKH and BRV both exhibit**: the set is *wired* but
*one-template*. A future skill update should formalize this as a third
methodology, perhaps "reskin-break pass."

## Recommended pilot

**`mtg_zld` (Legend of Zelda)**. Combines:

- Worst depth metrics across the catalog (0/4 gates, 0.05 mean).
- Largest single-fingerprint cluster (34 unwired vanilla flavorful
  cards) — a concrete punchlist for "what to wire."
- Flavor that suits the broken-on-purpose spice ethos
  (transformations, Triforce shards, Master Sword, Divine Beasts).
- Bounded scope at 207 cards — small enough to land in one phase, large
  enough to exercise the full methodology.

Pilot deliverables:
1. 12–15 spice picks (Plan agent, mirroring the Star Wars pilot shape).
2. Wire 6–10 of the 34 Divine Beast / Champion cluster with distinct
   mechanics.
3. Capability tests on every build-around pick.
4. Tournament validation against the existing custom-set tournament
   harness.
5. Notes on every skill friction point → feed back into `spice-pass.md`.
