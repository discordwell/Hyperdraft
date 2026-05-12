# PKH MTG Spice Loop

Pilot set: Pokemon Horizons (`PKH`).

The loop runner is `scripts/play/mtg_spice_loop.py`. It follows the
spice-pass sequence for compact MTG iterations:

1. Run a capability test for one focal spice card.
2. Build a synergy-aware deck with 4 focal copies, curated partners, filler,
   and 24 lands.
3. Run the two-pilot tournament/balance pass against generic PKH.
4. Run an MTG Codex mirror validation packet through the model-free referee.
5. Classify and record the balance action from capability, deck, match, and
   mirror metrics.

Current mirror note: the model-free referee harness lives in
`scripts/play/mtg_codex_match.py` and `src/engine/mtg_legal_actions.py`. It
supports hidden-info-safe packet/apply orchestration for live Codex player
subagents, but the loop uses deterministic fallback when no callable subagent
interface is available and never calls model APIs or shell model services.

Example:

```bash
python scripts/play/mtg_spice_loop.py \
  --set PKH \
  --iterations 10 \
  --capability-games 1 \
  --tournament-games 1 \
  --mirror-actions 8 \
  --max-turns 12 \
  --out-dir logs/mtg_spice_loop_pkh_r1 \
  --mirror-dir logs/mtg_codex_pkh_r1
```

Outputs:

- `run_config.json` - run settings and LLM availability.
- `iteration_XX_<card>.json` - full design, deckbuilding, tournament, and
  mirror/balance details for an iteration.
- `iteration_XX_<card>.report.txt` - tournament tier report.
- `summary.json` and `summary.md` - compact rollup.
- `logs/mtg_codex_*/*.json` - per-iteration hidden-info packet validation
  transcripts.

The default samples are intentionally small. Treat a single iteration as a
diagnostic signal, not a balance verdict; rerun with more games before changing
card text or costs.

## NG+/Depth Pass - 2026-05-11

Scope: MTG-mode Pokemon Horizons card texture only. No OpenAI API/SDK/key/model
calls were used; no live mirror player decisions were requested.

Survey metric before this pass:

- `total_cards`: 249
- `creatures`: 157
- `wired_cards`: 51
- `wired_creatures`: 48
- `unwired_creatures`: 109
- `high_depth_wired_cards`: 22

The thin-card survey found many iconic non-red cards with rules text but no
`setup_interceptors`, especially ETB legends and combat-damage value creatures.
This pass kept costs unchanged and converted 10 existing cards into deterministic
engine-backed behavior using the current MTG event helpers:

- `Sylveon, Intertwining Pokemon`: lifelink plus combat-damage bounce.
- `Lugia, Diving Pokemon`: flying plus ETB bounce for two highest-impact
  opposing nonland permanents.
- `Suicune, Aurora Pokemon`: hexproof plus combat-damage `SCRY 2` and draw.
- `Articuno, Freeze Pokemon`: flying plus ETB tap for opposing creatures.
- `Kyogre, Sea Basin Pokemon`: ETB returns all other creatures to hand.
- `Gyarados`: flying plus ETB discard from each opponent.
- `Yveltal, Destruction Pokemon`: flying/lifelink plus ETB destroy strongest
  opposing creature.
- `Absol, Disaster Pokemon`: first strike plus opponent-creature-death draw/life
  loss trigger.
- `Celebi, Time Travel Pokemon`: flying plus ETB return from graveyard to hand.
- `Nidoqueen`: ETB +1/+1 counters for the rest of your team.

Cost gate: all 10 cards retained their existing costs. The upgrades mostly make
already-costed printed text real rather than adding new rate breaks. The only
pushed executions are high-mana legends (`Lugia`, `Kyogre`, `Yveltal`) or
support-dependent payoff bodies (`Sylveon`, `Absol`, `Nidoqueen`), which matches
their current curve slots.

Metric after this pass:

- `wired_cards`: 61
- `wired_creatures`: 58
- `unwired_creatures`: 99
- `high_depth_wired_cards`: 30

Focused validation:

```bash
python -m pytest tests/test_pokemon_horizons_depth.py -q
python -m pytest tests/test_pokemon_horizons_spice.py -q
```

Depth gate added in `tests/test_pokemon_horizons_depth.py`: the current
iteration's 10-card batch must stay wired, PKH must have at least 61 wired cards,
and the heuristic high-depth wired count must stay at least 30.

## NG+/Depth Pass 2 - 2026-05-11

Scope: MTG-mode Pokemon Horizons only. No OpenAI API/SDK/key/model calls were
used; no live mirror player decisions were requested. Basic lands were left
unchanged.

Metric before pass 2:

- `avg_score`: 25.95
- `benchmark_ratio`: 0.390
- `thin_pct`: 61.0
- `wired_pct`: 24.1

This pass lifted 40 additional nonland cards with reusable engine-backed
patterns instead of isolated showcase rewrites:

- Static keyword creatures: `Pidgey`, `Rattata`, `Raticate`, `Jolteon`,
  `Arcanine`, `Rapidash`, `Ponyta`, `Mankey`, `Blaziken`, `Infernape`,
  `Victreebel`, `Beedrill`, `Scyther`, `Nidoking`.
- Evolve stages: `Togetic`, `Wartortle`, `Slowpoke`, `Staryu`, `Haunter`,
  `Grimer`, `Houndour`, `Zubat`, `Charmeleon`, `Growlithe`, `Vulpix`,
  `Ivysaur`.
- ETB/death tempo and attrition cards: `Meowth`, `Lapras`, `Dewgong`,
  `Walrein`, `Weezing`, `Koffing`, `Misdreavus`, `Mismagius`, `Houndoom`,
  `Flareon`, `Ninetales`, `Magmar`, `Electabuzz`, `Electivire`.

Reusable helpers added in `pokemon_horizons.py` cover self-keyword grants,
evolve setup, deterministic default targeting for ETB damage, opponent-team
damage, ETB tapping, opponent discard, Treasure death triggers, and death
damage sweepers. The PKH-local `make_evolve_trigger` payload now includes the
engine's current `power`/`toughness` keys so evolve updates stats as well as
names.

Cost gate: all 40 cards retained their existing costs. The pass implements
already-printed text or standard combat keywords, so it increases realized
functionality rather than adding new rate breaks.

Metric after pass 2:

- `avg_score`: 27.23
- `benchmark_ratio`: 0.409
- `thin_pct`: 53.0
- `wired_pct`: 40.2

Depth gate strengthened in `tests/test_pokemon_horizons_depth.py`: pass-1 and
pass-2 card batches must remain wired, PKH must have at least 101 wired cards,
at least 58 report-high-depth wired cards, average depth at least 27.2, thin
percentage no more than 53.1, and wired percentage at least 40.0.

Focused validation:

```bash
python -m pytest tests/test_pokemon_horizons_depth.py -q
python -m pytest tests/test_pokemon_horizons.py tests/test_pokemon_horizons_spice.py tests/test_pokemon_horizons_depth.py -q
python scripts/play/custom_set_depth_report.py --sets mtg_pkh --compact
```

## NG+/Depth Pass 3 - 2026-05-11

Scope: MTG-mode Pokemon Horizons only. No OpenAI API/SDK/key/model calls were
used; no live mirror player decisions or subagents were requested. Basic lands
were left unchanged.

Metric before pass 3:

- `avg_score`: 27.23
- `benchmark_ratio`: 0.409
- `thin_pct`: 53.0
- `wired_pct`: 40.2

This pass lifted 89 additional nonland cards with reusable engine-backed
patterns:

- 49 instants/sorceries gained deterministic `resolve` functions, including
  the Potion/Synthesis/Psychic families, simple pump/burn/bounce/tap spells,
  discard spells, sweepers, and library search spells.
- 19 tools gained setup-backed activated abilities, upkeep/combat triggers, or
  Equipment query effects. Representative patterns include catch artifacts,
  Pokedex loot, Berries, Max Revive, Lucky Egg, Leftovers, Exp. Share, and
  static Equipment buffs.
- 21 remaining thin creatures gained ETB, combat-damage, activated, evolve, or
  damage-reflection hooks. Representative cards include `Blissey`, `Pidgeot`,
  `Miltank`, `Alakazam, Psi Pokemon`, `Vaporeon`, `Magikarp`, `Wobbuffet`,
  `Murkrow`, `Spiritomb`, and `Toxicroak`.

Reusable helpers added in `pokemon_horizons.py` cover robust target
normalization, controller fallback for direct spell-resolution tests, spell
resolve factories for life/draw/scry/pump/tap/bounce/damage/destroy/search,
Equipment and item activated patterns, combat-damage value triggers, and
selected ETB/death/attack patterns.

Cost gate: all lifted cards retained their existing mana costs and creature
stats. The pass converts printed or conservative rider text into engine events
rather than pushing rates.

Metric after pass 3:

- `avg_score`: 30.52
- `benchmark_ratio`: 0.458
- `thin_pct`: 32.5
- `wired_pct`: 56.2
- `wired_or_resolve_cards`: 190
- `setup_cards`: 140
- `resolve_cards`: 50

Depth gate strengthened in `tests/test_pokemon_horizons_depth.py`: the 89-card
pass-3 batch must stay wired/resolved, every pass-3 card must score at least 28,
PKH must have at least 190 wired-or-resolved cards, at least 147
report-high-depth wired/resolved cards, average depth at least 30.5, thin
percentage no more than 32.6, and report wired percentage at least 56.0.

Focused validation:

```bash
python -m pytest tests/test_pokemon_horizons_depth.py -q
python -m pytest tests/test_pokemon_horizons.py tests/test_pokemon_horizons_spice.py tests/test_pokemon_horizons_depth.py -q
python scripts/play/custom_set_depth_report.py --sets mtg_pkh --compact
```
