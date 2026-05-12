# Yu-Gi-Oh! Codex Mirror / Spice Round 2 - 2026-05-10

Follow-up YGO worker pass using the Codex Mirror Playtest and spice-pass
workflows. Logs are under `logs/ygo_spice_loop_20260510_round2/` and
`logs/ygo_codex_round2/`.

## Harness

- Added deterministic YGO legal-action packets in
  `src/engine/yugioh_legal_actions.py`.
- Added model-free referee CLI in `scripts/play/yugioh_codex_match.py` with
  `init`, `packet`, `apply`, and `smoke` commands.
- Added strict JSON-only player prompt at
  `prompts/ultra_ai/yugioh_codex_player.md`.
- Added hidden-information, validation/apply, invalid-output, deterministic
  fallback, and transcript-write tests in `tests/test_yugioh_codex_playtest.py`.

No OpenAI API calls, SDK calls, API keys, or model-service shell calls were
added. This session did not expose a callable Codex subagent/task API, so the
10 automated mirror validations used the deterministic fallback path. Live vs
fallback count: `0 live / 10 fallback`.

## Ten Iterations

Each iteration ran a Kamigawa custom-set balance pass, optimized YGO deck
quality pass, compact YGO variant tournament, quick Kamigawa wet balance pass,
then a YGO Codex mirror validation transcript.

| Iter | Target | Variant top | Errors/draws | Wet anomalies | Mirror transcript |
|---:|---|---|---|---|---|
| 1 | burn tempo vs ninja removal | burn 75.0% | 0/0 | 0 | `logs/ygo_codex_round2/iter01_chain_burn_vs_kamigawa_ninja.json` |
| 2 | big pressure vs bounce control | burn 75.0% | 0/0 | 0 | `logs/ygo_codex_round2/iter02_dragon_beatdown_vs_kamigawa_moonfolk.json` |
| 3 | dragons vs low-win control | deck_strategy 91.7% | 0/0 | 0 | `logs/ygo_codex_round2/iter03_kamigawa_spirit_dragons_vs_kamigawa_moonfolk.json` |
| 4 | tribute control vs swarm | deck_strategy 66.7% | 0/0 | 0 | `logs/ygo_codex_round2/iter04_monarch_control_vs_kamigawa_samurai.json` |
| 5 | classic control vs equipment | deck_strategy 66.7% | 0/1 | 0 | `logs/ygo_codex_round2/iter05_goat_control_vs_kamigawa_modified.json` |
| 6 | burn/stall vs raw pressure | deck_strategy 58.3% | 0/0 | 0 | `logs/ygo_codex_round2/iter06_chain_burn_vs_dragon_beatdown.json` |
| 7 | tempo vs equipment board | control 66.7% | 0/0 | 0 | `logs/ygo_codex_round2/iter07_kamigawa_ninja_vs_kamigawa_modified.json` |
| 8 | dragon inevitability vs burn | deck_strategy 50.0% | 0/0 | 0 | `logs/ygo_codex_round2/iter08_kamigawa_spirit_dragons_vs_chain_burn.json` |
| 9 | control mirror with bounce/draw | control 75.0% | 0/0 | 0 | `logs/ygo_codex_round2/iter09_goat_control_vs_kamigawa_moonfolk.json` |
| 10 | large monsters vs curve pressure | aggro 66.7% | 0/0 | 0 | `logs/ygo_codex_round2/iter10_dragon_beatdown_vs_kamigawa_samurai.json` |

Aggregate summary:

- Deck quality flags: none.
- Kamigawa static balance flags: none.
- Variant tournament volume: 240 games, 0 errors, 1 draw.
- Quick Kamigawa wet checks: 50 games, 0 anomalies.
- Codex mirror validation: 10 fallback transcripts, 100 validated referee
  actions.

## Residual Risks

- Live Codex player subagent validation is still unrun in this session because
  no callable subagent mechanism was available.
- The mirror harness is intentionally phase/action based and does not implement
  full YGO chain-window response timing.
- The compact tournament is enough for smoke/balance drift checks, not for a
  final metagame claim.
