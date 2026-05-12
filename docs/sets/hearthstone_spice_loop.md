# Hearthstone Spice Loop

Date: 2026-05-09

Scope: Hearthstone-owned custom/expansion sets and harnesses: Stormrift, Frierenrift, Riftclash, Hearthstone AI adapter, and Hearthstone play/report scripts.

LLM-vs-LLM status: no automated Hearthstone LLM-vs-LLM harness was available in-repo. The loop used the closest local substitute: `scripts/play/variant_tournament.py --engine hearthstone`, with named aggro/control/midrange/ultra/random pilots across the six custom decks. The `ultra` pilot is still local heuristic play for Hearthstone; it does not call an LLM provider.

## Changes

- Added Hearthstone support to `variant_tournament.py` for Classic and custom decks, including Stormrift/Frierenrift/Riftclash modifiers.
- Added per-player Hearthstone pilot archetypes and a true noisy `random` floor in `HearthstoneAIAdapter`.
- Fixed Hearthstone report scripts so they run from the repo root without external `PYTHONPATH`.
- Added custom-set deck metrics to `hearthstone_deck_report.py`.
- Added Frierenrift support cards:
  - `Aureole Wayfinder`: two-drop shard smoothing, replacing an illegal third `Apprentice Caster`.
  - `Kraft, Roadside Monk`: midgame taunt/armor stabilizer.
- Tuned Stormrift Pyromancer deck curve by replacing one `Inferno Golem` with `Storm Herald`.

## Iterations

| Iteration | Design / Deck / Balance Action | Tournament Result |
| --- | --- | --- |
| 1 | Fixed root-path harness issue, added Hearthstone pilot tournament support, fixed Frieren copy-limit issue with `Aureole Wayfinder`, added aggro pilot face pressure. | Control 66.7%, aggro 62.5%, midrange 62.5%, no errors. |
| 2 | Removed forced midrange from `ultra`; let ultra detect deck archetype. | Midrange 54.2%, aggro/control 50.0%, random 45.8%, no errors. |
| 3 | Added custom deck report, found role flags, tuned Stormrift Pyromancer curve and Frieren midgame support. | Random/easy baseline still overperformed at 70.8%, exposing a bad baseline definition. |
| 4 | Added true noisy `random` Hearthstone difficulty instead of mapping random to easy face-bot. | Control 62.5%, aggro 54.2%, random 50.0%, no errors. |
| 5 | Validation loop with clean custom deck and Stormrift balance reports. | Control 58.3%, aggro/random 50.0%, no errors. |
| 6 | Validation loop. | Midrange 66.7%, control 54.2%, random 33.3%, no errors. |
| 7 | Validation loop. | Control 75.0%, midrange/ultra 58.3%, random 16.7%, no errors. |
| 8 | Validation loop. | Control 70.8%, aggro 58.3%, no errors. |
| 9 | Validation loop. | Aggro 75.0%, random 50.0%, no errors. |
| 10 | Validation loop. | Random 58.3%, ultra 54.2%, no errors. |

Aggregate over iterations 1-10: 600 games, 0 errors, 8 draws. Winner distribution: control 130, aggro 126, midrange 124, random 106, ultra 106. Finish reasons: 382 lethal, 210 life-total timeouts, 8 draws.

## Logs

Primary logs are under `logs/hearthstone_spice_loop_*`.

- `iter01` through `iter10`: numbered tournament JSON/stdout logs.
- `iter03` through `iter10`: custom deck report logs after the custom report path landed.
- `iter01` through `iter10`: Stormrift balance logs where applicable.
- `final_custom_deck_report.json` and `final_stormrift_balance.json`: final clean reports.

## Residual Risks

- The Hearthstone `ultra` pilot remains heuristic-only in this path; it is not a real LLM pilot.
- Slow control shells still create timeout adjudications at `--max-turns 24`, especially Stormrift Cryomancer and Riftclash Cryomancer.
- The variant tournament compares pilots on mirrored deck labels; it is a strong local substitute for pilot quality, not a full deck-vs-deck metagame tournament.

---

# Hearthstone Spice Loop - Codex Mirror Pass

Date: 2026-05-10

Scope: another 10-iteration Hearthstone pass over Stormrift, Frierenrift, Riftclash, Hearthstone deckbuilding reports, Hearthstone variant tournaments, and the new Hearthstone Codex mirror-playtest harness.

Codex mirror status: repository-side harness implemented in the requested shape:

- `src/engine/hearthstone_legal_actions.py`
- `scripts/play/hearthstone_codex_match.py`
- `prompts/ultra_ai/hearthstone_codex_player.md`
- `tests/test_hearthstone_codex_playtest.py`

The harness is model-free and exposes `init`, `packet`, `apply`, and `response` commands so a parent Codex orchestrator can pass hidden-info-safe seat packets to player subagents and feed back JSON `action_id` choices. This tool session did not expose a callable subagent/delegation tool; tool discovery only exposed Computer Use. Therefore the validation transcripts below are deterministic fallback mirror smokes, with `decision_counts.live_codex = 0` and `decision_counts.deterministic_fallback = 10` in each transcript.

## Iterations - 2026-05-10

Each iteration ran:

1. Custom-set spice/deck survey via `hearthstone_deck_report.py --custom-only`.
2. Deckbuilding improvement gate via custom deck quality flags.
3. Tournament/balance pass via Hearthstone variant tournament.
4. Codex mirror validation pass via Hearthstone referee transcript.

| Iteration | Spice / Deckbuilding Result | Tournament Signal | Mirror Validation |
| --- | --- | --- | --- |
| 1 | No custom deck quality flags; no Stormrift balance flags. | Aggro 75.0%, control 20.8%; 60 games, 0 errors, 0 draws. | Stormrift Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter01.json` |
| 2 | No custom deck quality flags; no Stormrift balance flags. | Aggro 58.3%, midrange 41.7%; 60 games, 0 errors, 1 draw. | Frieren vs Macht, fallback 10/10: `logs/hearthstone_codex_20260510_iter02.json` |
| 3 | No custom deck quality flags; no Stormrift balance flags. | Aggro 70.8%, midrange 33.3%; 60 games, 0 errors, 1 draw. | Riftclash Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter03.json` |
| 4 | No custom deck quality flags; no Stormrift balance flags. | Aggro 79.2%, random 29.2%; 60 games, 0 errors, 1 draw. | Stormrift Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter04.json` |
| 5 | No custom deck quality flags; no Stormrift balance flags. | Aggro 66.7%, ultra 29.2%; 60 games, 0 errors, 2 draws. | Frieren vs Macht, fallback 10/10: `logs/hearthstone_codex_20260510_iter05.json` |
| 6 | No custom deck quality flags; no Stormrift balance flags. | Ultra 58.3%, random 33.3%; 60 games, 0 errors, 1 draw. | Riftclash Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter06.json` |
| 7 | No custom deck quality flags; no Stormrift balance flags. | Control 58.3%, random 37.5%; 60 games, 0 errors, 2 draws. | Stormrift Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter07.json` |
| 8 | No custom deck quality flags; no Stormrift balance flags. | Aggro 83.3%, control 33.3%; 60 games, 0 errors, 0 draws. | Frieren vs Macht, fallback 10/10: `logs/hearthstone_codex_20260510_iter08.json` |
| 9 | No custom deck quality flags; no Stormrift balance flags. | Control 58.3%, ultra 33.3%; 60 games, 0 errors, 1 draw. | Riftclash Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter09.json` |
| 10 | No custom deck quality flags; no Stormrift balance flags. | Midrange 70.8%, random 20.8%; 60 games, 0 errors, 0 draws. | Stormrift Pyromancer vs Cryomancer, fallback 10/10: `logs/hearthstone_codex_20260510_iter10.json` |

Aggregate tournament result: 600 games, 0 errors, 9 draws. Winner reasons: lethal 386, life-total timeout 205, draw 9.

Aggregate pilot ranking:

| Variant | Wins | Games | Winrate |
| --- | ---: | ---: | ---: |
| Aggro | 159 | 240 | 66.2% |
| Midrange | 123 | 240 | 51.2% |
| Ultra | 114 | 240 | 47.5% |
| Control | 103 | 240 | 42.9% |
| Random | 92 | 240 | 38.3% |

## Logs - 2026-05-10

- Deck reports: `logs/hearthstone_spice_loop_20260510_iterXX_deck_report.json`
- Stormrift balance reports: `logs/hearthstone_spice_loop_20260510_iterXX_stormrift_balance.json`
- Variant tournaments: `logs/hearthstone_spice_loop_20260510_iterXX_variants.json`
- Tournament stdout reports: `logs/hearthstone_spice_loop_20260510_iterXX_variants_stdout.txt`
- Mirror transcripts: `logs/hearthstone_codex_20260510_iterXX.json`
- Mirror stdout summaries: `logs/hearthstone_codex_20260510_iterXX_stdout.txt`

## Residual Risks - 2026-05-10

- Live Codex player validation did not run in this tool session because no subagent/delegation tool was exposed. The harness is ready for parent-orchestrated live decisions through hidden-info-safe packet/apply commands.
- Aggro pilots remain slightly above the normal strong-but-plausible band at 66.2% aggregate winrate. This is a metagame pressure signal, not a harness failure; no late tuning was applied without another validation run.
- Timeout adjudication remains meaningful at 205/600 games, so slow control shells still need higher-turn validation before major balance conclusions.

---

# Hearthstone NG+ Depth Pass - Stormrift/Frieren

Date: 2026-05-11

Scope: Stormrift card texture pass with Frierenrift survey/validation. Frierenrift already had concurrent local support-card edits (`Aureole Wayfinder`, `Kraft, Roadside Monk`), so this pass left that file untouched and concentrated implementation risk in `stormrift.py`.

Mirror status: no live model decisions were needed. No OpenAI API, SDK, key, or model shell calls were used.

## Stormrift Upgrades

Implemented 10 current-engine upgrades, mostly converting empty-text or keyword-only filler into battlecry/deathrattle/interceptor texture:

- `Pyroclasm Adept`: spell-sequence battlecry payoff.
- `Inferno Golem`: Rift Storm self-damage payoff trigger.
- `Void Sprite`: armor plus damaged-minion freeze deathrattle.
- `Glacial Sentinel`: Armor-gated freeze battlecry.
- `Frozen Revenant`: damaged-minion freeze/armor deathrattle.
- `Rift Guardian`: damaged end-step armor engine.
- `Storm Herald`: next-spell damage boost battlecry.
- `Rift Imp`: storm/feedback deathrattle split token payoff.
- `Rift Champion`: damaged-friendly-minion buff or draw battlecry.
- `Rift Behemoth`: Elemental fortify plus damaged-enemy freeze deathrattle.

Cost note: stats/costs were preserved where the new text is conditional or storm-dependent. This keeps Hearthstone curve playability intact while making the cards care about spells, Armor, damaged minions, Rift Storm, and Arcane Feedback.

## Metrics

Stormrift texture metric:

| Metric | Before | After |
| --- | ---: | ---: |
| Cards measured | 48 | 48 |
| Thin cards | 12 | 2 |
| Complex-text cards | 32 | 42 |
| Average text words | 8.46 | 11.12 |

Remaining intentionally simple cards: `Rift Spark Elemental`, `Nexus Guardian`.

Stormrift balance report after pass: both factions retain empty `balance_flags`.

## Validation

- `python -m pytest tests/test_hearthstone_depth.py -q` - 5 passed
- `python -m pytest tests/test_stormrift.py -q` - 21 passed
- `python -m pytest tests/test_stormrift_balance.py -q` - 8 passed
- `python -m pytest tests/test_hearthstone_deck_quality.py -q` - 8 passed
- `python -m pytest tests/test_frierenrift_legendaries.py -q` - 23 passed
- `python scripts/play/stormrift_balance_report.py` - no Stormrift balance flags

## Coordination

No `COORDINATION_REQUEST` was required for this iteration. Live Codex mirror decisions remain available through the existing parent-orchestrated harness if a future pass wants qualitative model play.

---

# Hearthstone NG+ Depth Pass 2 - Custom Thin-Card Lift

Date: 2026-05-11

Scope: Hearthstone custom cards only: Stormrift shared chassis, Frierenrift shard cards, and Riftclash freeze-control spells. No OpenAI API, SDK, key, model, or live subagent/player calls were used.

## Cards Lifted

Lifted 36 formerly thin cards to the depth gate:

- Stormrift/shared chassis: `Rift Spark Elemental`, `Kindling Imp`, `Singe`, `Storm Acolyte`, `Rift Bolt`, `Rift Firehound`, `Pyroclasm Drake`, `Searing Rift`, `Inferno Wave`, `Pyroclasm`, `Rift Walker`, `Frost Wisp`, `Void Seer`, `Abyssal Lurker`, `Voidcrystal Golem`, `Blizzard Golem`, `Void Anchor`, `Rift Sight`, `Void Barrier`, `Void Drain`, `Nexus Guardian`.
- Frierenrift: `Apprentice Caster`, `Stark, Vanguard Guardian`, `Flight Magic Circle`, `Grimoire Archive`, `Fern's Follow-Up`, `Journey to Aureole`, `Supplicant Adept`, `Macht's Gold Guard`, `Demon Suppression`, `El Dorado Collapse`, `Qual's Venom Lance`, `Severing Guillotine`, `Fearsome Battalion`.
- Riftclash: `Ice Shackle`, `Glacial Insight`.

Cost note: effects were kept conditional, defensive, or tied to existing set axes. A few bodies were trimmed while adding text (`Nexus Guardian`, `Stark, Vanguard Guardian`, `Macht's Gold Guard`, `Fearsome Battalion`) to stay closer to the HS curve.

## Metrics

`python scripts/play/custom_set_depth_report.py --sets hearthstone_custom --compact`

| Metric | Before | After |
| --- | ---: | ---: |
| Avg score | 34.18 | 41.27 |
| Benchmark ratio | 0.513 | 0.620 |
| Thin count | 36 | 0 |
| Thin pct | 36.7% | 0.0% |
| Wired pct | 98.0% | 100.0% |

## Validation

- `python -m pytest tests/test_hearthstone_depth.py tests/test_stormrift.py tests/test_stormrift_balance.py tests/test_frierenrift_legendaries.py tests/test_hearthstone_deck_quality.py tests/test_server_hearthstone_match_create.py -q` - 79 passed
- `python scripts/play/stormrift_balance_report.py` - no balance flags
- `python scripts/play/hearthstone_deck_report.py --custom-only` - all six custom decks valid, no quality flags

## Coordination

No `COORDINATION_REQUEST` was required. Live model decisions were not needed for this depth pass.

---

# Hearthstone NG+ Depth Pass 3 - Mid-Score Decision Lift

Date: 2026-05-11

Scope: Hearthstone custom cards only: Stormrift shared chassis, Frierenrift shard cards, and Riftclash tactical spells/minions. No OpenAI API, SDK, key, model, or live subagent/player calls were used.

## Cards Lifted

Lifted 40 mid-score cards in the 28-40 band by adding second-decision riders, conditional branches, persistent synergies, and counterplay/payoff hooks while preserving Hearthstone-style clarity.

- Stormrift/shared chassis: `Ember Channeler`, `Storm Acolyte`, `Rift Firehound`, `Pyroclasm Adept`, `Pyroclasm Drake`, `Rift Berserker`, `Volatilerift Mage`, `Ignis Ascendant`, `Searing Rift`, `Inferno Wave`, `Pyroclasm`, `Chain Lightning`, `Frost Spike`, `Glacial Sentinel`, `Rift Watcher`, `Voidcrystal Golem`, `Blizzard Golem`, `Voidfrost Dragon`, `Rift Sight`, `Void Barrier`, `Glacial Tomb`, `Storm Herald`, `Rift Behemoth`, `Rift Walker`.
- Frierenrift: `Apprentice Caster`, `Aureole Wayfinder`, `Fern, Precise Disciple`, `Kraft, Roadside Monk`, `Fern's Follow-Up`, `Canon of Souls`, `Linie, Perfect Copy`, `Draht, Binding Thread`, `Journey to Aureole`, `Aura Severing Ray`, `Macht's Gold Guard`.
- Riftclash: `Cinder Lance`, `Ember Volley, Unchained`, `Cryo Sentinel`, `Absolute Archivist`, `Glacial Insight`.

## Metrics

`python scripts/play/custom_set_depth_report.py --sets hearthstone_custom --compact`

| Metric | Before PASS 3 | After PASS 3 |
| --- | ---: | ---: |
| Avg score | 41.27 | 50.28 |
| Benchmark ratio | 0.620 | 0.755 |
| Thin pct | 0.0% | 0.0% |
| Wired pct | 100.0% | 100.0% |

## Validation

- `python -m pytest tests/test_hearthstone_depth.py -q` - 15 passed
- `python -m pytest tests/test_stormrift.py tests/test_stormrift_balance.py tests/test_frierenrift_legendaries.py tests/test_hearthstone_deck_quality.py tests/test_server_hearthstone_match_create.py -q` - 68 passed
- `python scripts/play/stormrift_balance_report.py` - Stormrift Pyromancer and Cryomancer both retain empty `balance_flags`
- `python scripts/play/hearthstone_deck_report.py --custom-only` - all six custom decks valid with empty `quality_flags` and `role_quality_flags`
- `python scripts/play/variant_tournament.py --engine hearthstone --variants aggro,control,midrange,ultra,random --decks stormrift_pyromancer,stormrift_cryomancer,frieren,macht,riftclash_pyromancer,riftclash_cryomancer --games 1 --max-turns 24 --seed 511` - 60 games, 0 errors, 0 draws; control 62.5%, aggro/random 54.2%, midrange 45.8%, ultra 33.3%

## Coordination

No `COORDINATION_REQUEST` is required from this pass. The local heuristic tournament still shows `ultra` underperforming on this seed, so a later AI-adapter pass may want to revisit Hearthstone ultra heuristics separately from card depth.
