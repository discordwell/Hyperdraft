# Minecraft Polish Punchlist — iter 1 @ 2026-05-07 (full polish)

## Tournament data
- Source: `logs/minecraft_polish_wet_iter1_full.json` (50 games, passive_econ bias, all 5 starters)
- 0 tournament errors. 130 distinct (deck, card) entries telemetered.

## Zero-play cards (in deck, never entered play)

38 cards across 4 decks. Top by deck:

### builder (10 zero-play)
| Card | Appearances |
|------|-------------|
| Redstone Engine | 20 |
| Piston Gate | 20 |
| Iron Golem | 20 |
| Allay Courier | 20 |

Notably **Iron Golem** — the P2a pilots repeatedly tried to play this and failed, citing
Strip Mine drought leaving I1+R1 unreachable. Telemetry confirms: 0 plays in 20 games.
The card is supposed to be the builder's mid-game finisher; it's structurally
unreachable at current Strip Mine density.

### miner (5 zero-play)
| Card | Appearances |
|------|-------------|
| Beacon | 20 |
| Diamond Armor | 20 |

### raider (10 zero-play)
| Card | Appearances |
|------|-------------|
| Enderman | 20 |
| Blaze | 20 |
| Diamond Sword | 20 |
| TNT Blast | 20 |
| Nether Expedition | 20 |

### box_of_horrors (13 zero-play)
| Card | Appearances |
|------|-------------|
| Lectern of Whispers | 20 |
| Sculk Catalyst | 20 |
| Eldritch Altar | 20 |
| Soul Sand Trap | 20 |
| (+9 more) | each 20 |

## Loss-only cards (appeared, deck never won)
| Card | Deck | Appearances | Losses |
|------|------|-------------|--------|
| Cursed Bed | box_of_horrors | 20 | 19 |
| Soul Forge | box_of_horrors | 20 | 19 |
| Fog Wall | box_of_horrors | 20 | 19 |

All in box_of_horrors, which has 0% deck winrate — these are loss-correlated by deck failure, not card failure per se.

## Cast-but-no-impact cards
Insufficient data to distinguish from "played but lost" without per-game contribution scoring. Deferred to a future telemetry iteration.

## Recommendations

### Engine / cost balance
- **Iron Golem (builder)** — 0 plays in 20 games is structural failure. Either:
  - Lower the cost to I1 (drop redstone requirement), OR
  - Add more Strip Mine copies to the builder starter (currently appears too sparse), OR
  - Add an alternative redstone source the builder can reach without Strip Mine
- **Beacon, Diamond Armor (miner)** — late-game cards never reached. miner has insufficient ramp to hit them in 35-turn games. Either reduce cost or accept they're for longer formats.
- **box_of_horrors structural failure** — 13 zero-play cards out of 50 means the deck has fundamental curve / consistency problems. Redesign or retire.

### AI heuristic
- The `passive_econ` bias under-prioritizes the unique build paths these cards need. Worth considering a `redstone_priority` enum option for `mining_mode` that explicitly seeks redstone in the early game so Iron Golem becomes reachable.

### Deck registry
- box_of_horrors should be removed or redesigned before the next polish pass. 0% winrate isn't tunable.

## Iters-failed counter

| Card / deck | Iters failed |
|-------------|--------------|
| box_of_horrors (deck) | 1 |
| Iron Golem (builder) | 1 (zero-play structural) |
| Redstone Engine, Piston Gate, Allay Courier (builder) | 1 each |
| Beacon, Diamond Armor (miner) | 1 each |
| Enderman, Blaze, Diamond Sword, TNT Blast, Nether Expedition (raider) | 1 each |
| 13 box_of_horrors cards | 1 each |
