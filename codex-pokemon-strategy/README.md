# Codex Pokemon Strategy

This folder holds Codex-side Pokemon TCG strategy experiments and stable
comparison artifacts. Scratch runs belong under `scratch/` so generated
match data does not look like source deletion.

## Current Focus

The first pass targets execution/deck-function strategy rather than a broad
engine rewrite:

- Play setup Items before bench/evolution/energy decisions for Codex profiles.
- Keep the public Pokemon difficulties as `easy`, `medium`, `hard`, and
  `ultra`, with Codex improvements promoted into the extra-hard `ultra`
  profile.
- Make shared trainer-suite cards actually support deck setup, especially Rare
  Candy and search/draw Trainers.
- Measure same-deck mirrors across Beyond Ravnica guild decks with alternating
  play/draw seating.

## Harness

Run a focused comparison without the full test suite:

```bash
python codex-pokemon-strategy/compare_pokemon_strategies.py \
  --decks azorius,boros,dimir,golgari,gruul,izzet,orzhov,rakdos,selesnya,simic \
  --seeds 20260502,20260503,20260504,20260505,20260506,20260507,20260508,20260509 \
  --max-turns 60 \
  --out codex-pokemon-strategy/pokemon_strategy_results.json
```

The harness compares `ultra` against the main `medium` baseline and also runs
Ultra-vs-Ultra mirrors as stability checks.

Current verification target: compare `ultra` against `medium` across 160
alternating same-deck games, with no errors and no mirror timeouts. The stable
summary is saved as `pokemon_strategy_summary.json`.
