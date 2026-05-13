# SCP Polish Punchlist — iter 1 @ 2026-05-13

## Loop status
- **Iterations completed**: 1/3 (skipped 2+3 due to harness mismatch; see report)
- **P0 interceptor verification**: 100/100 pass (100%)
- **P5a tournament**: 84 games, 82 finished, 2 draws, **0 errors**

## Balance findings

| Deck | Wins / Games | Winrate | Flag |
|---|---|---|---|
| keter_risk | 17/21 | 81.0% | **too strong** |
| veil_control | 15/21 | 71.4% | **too strong** |
| oneiric_archives | 13/21 | 61.9% | watch |
| antimemetic_cold_war | 12/21 | 57.1% | watch |
| secure_contain_research | 9/21 | 42.9% | watch |
| goi_frontline | 9/21 | 42.9% | watch |
| keter_blackout | 4/21 | 19.0% | **too weak** |
| ethics_reckoning | 3/21 | 14.3% | **too weak** |

67-point winrate spread across 8 decks. Every deck is outside the target band — none are in the 45-55% range.

## Win-condition distribution

| Reason | Count | Notes |
|---|---|---|
| opponent_breach | 45 | dominant — aggressive breach pressure |
| archives | 21 | Thaumiel-style accumulation |
| veil_lockdown | 7 | secrecy victory |
| opponent_exposure | 4 | secrecy-attack victory |
| alternate_or_state_based | 2 | mandate alt-wins |
| draw_or_timeout | 2 | rare |
| opponent_ethics | 2 | ethics-debt collapse |
| public_panic | 1 | GOI alt-win |

**Average game length: 14.1 turns** — fast format. Slower archetypes don't have time to express identity.

## Pool coverage

- 179/680 cards (26.3%) appear across the 8 starter decks tested
- The other 74% are wired but untouched by this tournament. They may shine in tuned decks built by `/build-decks`, or they may be dead weight.

## Recommended actions (ranked by leverage)

### Priority 1 — fix the breach economy
keter_risk + veil_control + oneiric_archives all win primarily through `opponent_breach`. The new W1+W5 wiring made `_hostile_reveal` more common (was sparse `index % 9` in the generator; now every-2nd KBO + every GOI odd-index + ETH ethics-debt). Suggested tuning:
- Lower default `_hostile_reveal` amounts from 1-2 down to 0-1 for templated cards
- Increase `BREACH_LIMIT` from current value (check `src/engine/scp.py`)
- OR add a "first breach per turn is free" buffer to slow the slope

### Priority 2 — buff slower archetypes
- **ethics_reckoning** (14% winrate): the W1-baked "ethics_debt +1 on reveal" makes the archetype's own anomalies *cost it secrecy/runway*. Reduce baked ethics-debt cost OR make ethics_debt convert to clearance more efficiently.
- **keter_blackout** (19% winrate): expensive late-game payoff, but format ends turn 14. Speed up its containment payoffs OR slow the format.

### Priority 3 — investigate winrate ceiling
- keter_risk at 81% suggests the new contained-state auras (W2) + on_reveal mood seeding (W1) compound too well on its specific card list (MTF Doorbreaker + Oracle Mold + Borrowed Moon). Audit specific synergies.

## P0 watchlist (zero-play cards, in-deck-but-never-impactful)

Cannot determine from this tournament alone — would need `--log-interceptor-fires` telemetry which `scp_tournament.py` doesn't yet support. Adding that flag is a candidate for follow-up tooling work.

## Loop stages not run (and why)

- **P1** (deckbuilder) — `scp_tournament.py` doesn't accept JSON deck files. Would need `--decks-file` flag added.
- **P1.5** (variant tournament) — `scripts/play/variant_tournament.py` registry doesn't include SCP.
- **P2** (ultra-loop) — depends on P1's deck candidates.
- **P3** (frontend polish) — already done this session.
- **P4** (P0 re-verification) — redundant; P0 was clean and nothing card-side changed.
- **P5d** (plan-vs-reality drift) — no fresh `/ultra-loop` plans to compare against.

## Artifacts
- `tests/test_scp_interceptors.py` (new, 56KB, 100 tests)
- `logs/scp_polish_wet_iter1.json` (84 outcomes)
