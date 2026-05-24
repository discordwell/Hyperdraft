# Clankers Strategy Notes

> Persistent strategy doc — seeded into `storage/strategy/` on lifespan startup.
> Read by LLM pilots before each game. Should compress what NOT to do as much
> as what to do.

## Core Loop

A Clankers game has two competing timers:

1. **Workshop Integrity** (your Core's HP, 30 max) — the opponent grinds this with chassis attacks.
2. **Library depletion** (your deck) — once either library hits 5 cards, the Containment Failure deathclock activates and both players take escalating self-damage (2 → 4 → 8).

You win by managing both. Card draw is "free" (hand floor refills to 7) but every card drawn empties your library — converts hand size into deathclock pressure.

## Resource Economics

- **Compute resets every turn** (3 + turn_number, cap 10). Spend it or lose it. Holding cards in hand doesn't accumulate value — they cost the same to play later.
- **Build Slots gate robot size**. A chassis with `2W/2A` slots can never carry more than 4 attached parts. Big robots come from chassis with big slot counts (3W/4A on heavies).
- **Scrap is persistent**. It builds up. Some cards exchange scrap for one-time effects ("Pay 2 Scrap: return destroyed weapon"). Don't hoard past 7-8 — it caps at 10.

## Refill Decisions

The "may" refill at Allocate is THE key strategic choice every turn.

| Library size | Hand size | Recommendation |
|---|---|---|
| > 20 | any | Take. Plenty of cycles left. |
| 12-20 | < 5 | Take. Need plays. |
| 12-20 | ≥ 5 | Maybe skip. You have plays. |
| 6-11 | < 4 | Take. Need plays more than time. |
| 6-11 | ≥ 4 | **Skip**. Buy turns. |
| ≤ 5 | any | **Skip if possible**. Deathclock activates at 5 (either library). |

## Attack/Block Heuristics

**When to attack with a chassis**:
- Effective Power ≥ defender's Effective Integrity (including unexhausted Armor) → you kill it.
- Unblocked path to Core that deals ≥ 4 damage.
- Mirror match where you can trade up (your 3/4 into their 4/3).

**When NOT to attack**:
- Your chassis would die for no kill.
- Their cheap chump can block + survive (e.g. you're a 3/4, they have a 1/3 blocker).

**Blocking**:
- Always block lethal-to-Core threats.
- Block to kill (defender_eff_power ≥ attacker_eff_integrity) if you can survive the return.
- Let chip damage through — 2 damage to your Core is usually less bad than losing a 3/5 chassis.

## Per-Archetype Notes

### Brick (FORGE-Δ)

- Compute curve matters most. Drop a chassis turn 1, 2-cost weapon turn 2, big chassis turn 3-4.
- FORGE-Δ Core: chassis with integrity ≥5 cost -1 Compute. This makes 4-cost 5/5+ chassis play for 3.
- DON'T attach all your weapons to one chassis. Death-cascade is a real risk.

### Control (ETHOS-7)

- ETHOS-7 Core: first Transient each turn costs -1. This is your engine — use it every turn.
- Bulwark Frame (3/6) is your turn-3 wall — survives most early swarm attacks.
- Heuristic Loop scales with Transient density in your scrap heap. Don't dump scrap-recur Transients without thinking.

### Swarm (MIRTHBOT-1)

- Synchronize ACTIVATES at 2 chassis. Until you have 2 Synchronize chassis, your Synchronize cards are vanilla.
- Synchronize over-couples at 4+ chassis (gives 0 bonus). Wide-but-not-too-wide is the sweet spot.
- Affection.exe Core: first chassis each turn enters with +1 integrity. Play chassis FIRST in your turn.
- Self-Mobile parts (Scout Drone, Joybuzzer) attack as 1/1 baseline — only worth it if Self-Mobile applies their bonus.

### Artillery (BULWARK-9)

- Armor stacking is your defense. Reactive Shielding (Armor 2), Bunker Cradle (Armor 1), Containment Lining.
- BULWARK-9 Core: 3+ exhausted add-ons → +1 scrap + 1 WI per turn. Stack armor; let it tick.
- Burnout Cannon mills opponent (-5 cards). Pair with Burnout Protocol to double deathclock damage on opponent.
- Bad vs MIRTH: swarm faster than you stabilize. Mulligan toward Vault Chassis.

## Common Card Patterns

- **Self-Mobile weapons** (Scout Drone, Joybuzzer): play solo for tempo, attach later for permanent buff.
- **Modular parts** (Modular Railgun, Apex Coilgun): can shuffle attachments at end of turn. Use to re-arm an undamaged chassis after a death cascade.
- **Activated weapons** (most FORGE/BULWARK weapons): "1 Compute, exhaust: deal X damage". Save for lethal finisher.
- **Damage Transients** (Reroute Power, Big Swing, Hammer-On, Scrap Salvo): direct damage. Reach to close.
- **Heal Transients** (Patch): full-heal a chassis. Save for "would lethal" situations.

## Deck-out / Deathclock Awareness

- Game length: typically 8-12 turns at hard play.
- Deathclock activates when EITHER library hits 5 cards.
- Once activated: turn 1 = 2 damage, turn 2 = 4, turn 3 = 8.
- If you're at 14 WI and deathclock fires: turn 1 lose to 12, turn 2 to 8, turn 3 to 0. You have ~3 turns.
- If you're racing to deathclock + 0: empty your hand to draw, even if it's cards you don't want to play — every refill takes 7 cards out of library.
