# Yu-Gi-Oh! Spice Loop - 2026-05-10

YGO worker pass following the Hyperdraft spice-pass workflow, adapted to the
local Yu-Gi-Oh! engine and harnesses. Logs are under
`logs/ygo_spice_loop_20260510/`.

## Scope

- Pilot/custom focus: optimized YGO decks plus Beyond Kamigawa.
- Additional coverage: starter and classic YGO decks in the final variant loop.
- LLM-vs-LLM substitute: local two-pilot variant tournament via
  `scripts/play/variant_tournament.py --engine yugioh`.
- Balance substitute: static quality reports plus Beyond Kamigawa wet tests.

## Code And Deck Actions

- Added YGO support to `variant_tournament.py`, including starter/classic,
  optimized, and Beyond Kamigawa deck resolution.
- Added Beyond Kamigawa strategy hints so the YGO AI can use archetype-specific
  summon and set priorities.
- Fixed YGO optimized draw effects to use `library_<player>` zones.
- Fixed YGO spell activation target forwarding and lifecycle movement for
  Normal, Quick-Play, Continuous, Equip, and Field spells.
- Routed YGO action events through the event pipeline so YGO interceptors can
  react.
- Resolved YGO flip effects on flip summon and battle flip.
- Fixed AI Tribute Summons by supplying `tribute_ids`.
- Added hard-AI heuristics for custom-set draw, bounce, removal, burn, Equip,
  Field, and Continuous spells.
- Added simple proactive Trap activation for modeled set traps.
- Tuned Kamigawa Ninja and Moonfolk decklists toward engine-visible
  interaction and draw.
- Updated the Kamigawa wet-test harness to use strategy-aware per-seat YGO AI
  adapters and raised mirror-imbalance detection to 10 completed mirror games.

## Final 10 Iterations

Each iteration ran:

1. Optimized YGO deck quality report with `--fail-on-flags`.
2. Kamigawa static balance report with `--fail-on-flags`.
3. YGO variant tournament across starter, classic, optimized, and Kamigawa decks.
4. Beyond Kamigawa quick wet test.

| Iter | Design/deck pass | Tournament result | Balance result |
|---:|---|---|---|
| 1 | Static quality + Kamigawa balance pass; no flags | top `control` 67.7%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 2 | Static quality + Kamigawa balance pass; no flags | top `control` 63.1%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 3 | Static quality + Kamigawa balance pass; no flags | top `deck_strategy` 55.4%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 4 | Static quality + Kamigawa balance pass; no flags | top `aggro` 63.1%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 5 | Static quality + Kamigawa balance pass; no flags | top `deck_strategy` 56.9%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 6 | Static quality + Kamigawa balance pass; no flags | top `burn` 64.6%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 7 | Static quality + Kamigawa balance pass; no flags | top `deck_strategy` 61.5%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 8 | Static quality + Kamigawa balance pass; no flags | top `burn` 58.5%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |
| 9 | Static quality + Kamigawa balance pass; no flags | top `deck_strategy` 60.0%; 195 games, 0 errors, 1 draw | 0 wet anomalies; 0 static flags |
| 10 | Static quality + Kamigawa balance pass; no flags | top `control` 58.5%; 195 games, 0 errors, 0 draws | 0 wet anomalies; 0 static flags |

Final aggregate:

- Final loop size: 1,950 YGO variant games, 1 draw, 0 errors.
- Final quick wet-test aggregate: 150 Kamigawa games, 1 draw, 0 anomalies.
- Average variant win rates: control 57.1%, deck_strategy 55.1%, burn 52.3%,
  aggro 51.7%, balanced 44.5%, random 39.2%.
- Kamigawa quick wet aggregate: Spirit Dragons 68.3%, Samurai 53.3%,
  Modified 46.7%, Ninja 43.3%, Moonfolk 36.7%.

## Verification

- `python -m pytest tests/test_yugioh_strategy_iteration.py tests/test_beyond_kamigawa_balance.py -q`
- `python scripts/play/yugioh_deck_quality_report.py --fail-on-flags`
- `python scripts/play/kamigawa_balance_report.py --fail-on-flags`
- Final 10-loop logs: `logs/ygo_spice_loop_20260510/final_iterations_summary.json`

## Residual Risks

- The tournament is a local heuristic substitute, not a true automated
  LLM-vs-LLM harness.
- The final quick wet aggregate still shows Spirit Dragons high and Moonfolk
  low. The larger post-tune 10-game wet sample was milder, but these archetypes
  should get a larger seeded sample before heavier card changes.
- YGO trap timing remains simplified: proactive trap activation is modeled, but
  full chain-window response play is still not implemented.
