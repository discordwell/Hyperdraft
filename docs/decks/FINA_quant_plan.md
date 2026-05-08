# FINA_quant — Plan

## Composition summary

Value/grindy control deck built around the Arbitrage keyword. Trader chassis: Statistical Arb Clerk (1/2 Arb 1), Correlation Trader (2/4 Arb 1 wall), Risk Manager (1/4 Arb 1 wall), Factor Model Analyst (1/3 Arb 1 + draw), Pairs Trader (2/3 Arb 2), Portfolio Construction Desk (3/4 Arb 2 + lord +0/+1), Systematic Alpha Engine (Arb 2 mid), Mean Reversion Bot (mid). Support: Liquidity Provision (mana), Correlation Matrix (draw — currently broken), Quant Lab (structure), Quant Signal (look-at-top — currently broken).

## Win condition

**Plan A (primary): Wall-then-swarm.** Survive T1-T9 (~8-12 face damage absorbed) by deploying 4-tough Arbitrage walls (Risk Manager, Pairs Trader, Correlation Trader). Build trader-count parity by T8-T10 — Pairs Trader's Arb 2 + PCD lord gives a +Liquidity cascade that lets you double-deploy in one turn. Once trader-count > opponent's by 2+, attack with multi-Trader swarms that opponent can't fully block. Close T20-T30 by trample-overflow chip damage.

## Target turns (Plan A — wall-then-swarm)

- **T1-T2**: Stat Arb Clerk (1/2) deploys for the early body. Block solo Alpha Strikers if necessary — expect to leak 2-3 face per chump.
- **T3-T7**: Correlation Trader T3 (2/4 wall — main early-game blocker), Risk Manager T4 (1/4), Factor Model Analyst T5 (1/3 + draw on Arb). Take Alpha Strike chip damage as cost-of-business. P2 should sit at 18-22 capital by T7.
- **T8-T10**: Pairs Trader T8 (2/3 Arb 2 fires +4 Liquidity → enables PCD same turn). PCD T9-T10 (3/4 + lord). This turn is the snowball turn — you go from 2-3 Traders to 4-5 in two turns.
- **T11-T15**: Multi-attacker swarm starts. With 3+ attackers vs opponent's 0-2 blockers, force unblockable damage by spreading the threat. Trample overflow does meaningful work even when chumps absorb individual attackers.
- **T15-T20**: Sustained multi-attack. Each PCD on the board adds +0/+1 to all Quant Traders — a 1/2 Clerk becomes 1/3, a 2/3 Pairs Trader becomes 2/4. Opponent's removal answers (rare in HF) get diluted.
- **T20-T30**: Close. By here HF is hand-starved. 3-attacker swings deal 6-9 face per turn. Lethal lands T26-T30.

## Mulligan policy

- **Auto-keep**: any 4-tough Trader (Correlation Trader, Risk Manager, Pairs Trader) + 1 cheap blocker (Stat Arb Clerk, FMA). Sets up survival window.
- **Auto-keep (good)**: hand with TWO Arbitrage Traders and a low curve. Trigger cascade by T8 = win path.
- **Salvage**: hand with PCD but no early walls. Risky — expect to take 12+ face damage before PCD lands T6-T7.
- **Auto-mull**: 0 cards costing ≤3. Quant cannot survive turns 1-5 without on-curve walls.

## Play priorities (order)

1. **Always deploy a 4-tough wall on T3 if available.** Trample overflow makes 2-tough chumps cost 2-3 face per block. 4-tough bodies absorb a 5-power Alpha swing for only 1 overflow.
2. **NEVER cast Liquidity Provision at full mana.** It gains 0 — both pilots burned 2 mana on this in iter-1. Only cast when current available < max - 2 OR when chaining a 4+ cost play same turn after a generic spend.
3. **Cast Pairs Trader T8 to enable PCD T8 same turn.** Arb 2 trigger fires +4 Liquidity. This is the snowball turn — getting it 1 turn earlier or later swings the matchup heavily.
4. **PROTECT PCD.** It's the linchpin — opponent killing it once (HF blocked it twice in iter-1) sets you back 4-5 turns of board pressure. Hold PCD as a wall, NOT an attacker, until you have a 4th body.
5. **Multi-attack when attackers > opponent blockers.** Once you have 3+ Traders vs HF's 0-1, swing all legal attackers — you force unblockable damage by trader-count asymmetry.
6. **Block Alpha Strikers selectively.** Only block when blocker's toughness > attacker's buffed power (so the blocker survives). Otherwise eat the chip — Quant has more bodies in the long run.
7. **Block when face damage would drop you below 8 capital.** Trample overflow is real but even 2 face leaked beats 5 face unblocked.
8. **Don't cast Correlation Matrix until engine bug is fixed** (it draws 0 cards instead of 3 — see strategy doc).

## Anticipated weaknesses

- **Direct Market Access (HF static, +4/+0 to Alpha Strikers).** Quant has zero spot removal in the starter. DMA can sit on the board indefinitely as a 3-cost permanent power-buff. If HF lands DMA + 2 Alpha Strikers by T7, Quant cannot stabilise — both pilots flagged this in iter-1.
- **Trample overflow on chump-blocks.** Even chumping a 2/1 Alpha Striker with a 1/2 Clerk leaks 2-3 face. Survival math is tighter than printed values suggest.
- **Risk Manager Arbitrage timing**: heals BEFORE damage assignment per Pilot B (engine bug, see strategy doc). RM as a blocker doesn't actually save itself from a trade.
- **Slow start** — T1-T7 expect to take 8-12 face damage. Capital reserve at T7 is realistically 18-22. Not much margin if HF lands DMA early.

## Iteration log

- **2026-05-08 (iter-3)**: vs FINA_dark_arbitrage (LLM Pilot B). **Lost** in 20 turns; final P1=−1 (dead), P2=10. **Root cause: engine combat bug, not deck flaw.** Engine bug 1 (any-damage-kills) was active for most of the game — every wall (PCD 3/4, MRB 1/4, RM 1/4, FMA 1/3) died to 1-3 damage when blocked, regardless of toughness. Pilot A explicitly noted the deck's identity is structurally invalid until bug 1 is fixed: "the wall deck has no walls — only 1-shot chumps." Mid-game face damage from T5-T11 (P2 30→19) was actually fine; the loss came from the wall plan failing on T11 onwards. **Wall strategy depends on the combat damage bug being fixed.** Iter-3 also surfaced 6 NEW engine bugs (15-20). Quant's open request for a 2-cost spot-removal Order is now triple-confirmed across all 3 iterations — without it, OEF/ICBT/DMA sit unanswered.
  Key new findings:
  - **PCD lord disappears the moment PCD dies** (bug 1 made this trivial). T11 onwards, all walls were 1-tough chumps to ≥2 power attackers.
  - **Quant cannot generate enough trader-count to swarm under bug 1** — every block is a 1-shot suicide, so the trader-count race tilts toward the deck with cheaper bodies.
  - **Liquidity Provision was a permanent trap** — never castable (always at-or-near max). Same observation as iter-1.
  - **Rebalancing Halt at instant speed is useless** (NEW bug 17: tap on already-declared attacker is a no-op for combat). Effective only as a sorcery-speed effect on YOUR turn pre-declare.
  - **Pivot recommendation (Pilot A)**: until bug 1 is fixed, Quant should swap 4-tough walls for 1-2 cost bodies (Stat Arb Clerk x4, Market Maker, FMA) and play swarm-aggro instead.
- **2026-05-08 (iter-1)**: vs FINA_high_frequency (LLM Pilot A, double-pilot mode). **Won** in 28 turns; final P1=0 P2=16. Pilot B self-graded as a tense back-and-forth race that Quant won by trader-count value engine. Net P2 face damage absorbed by blockers ≈ 12-15 across the game.
  Key new findings:
  - **Risk Manager + FMA T8 stabilised**: 2 fresh 4-tough/3-tough bodies after taking 12 face in T1-T7. RM held Alpha Strike pressure for 1 critical turn.
  - **Pairs Trader + PCD T10 (Arbitrage cascade)**: trigger fired +4 Liquidity → enabled deploying 2 cards in one turn. This was the snowball moment.
  - **Multi-attacker swarm T20, T22, T28** forced unblockable damage when HF had 0-1 blockers vs P2's 3 attackers. Lethal closer.
  - **Liquidity Provision misplay T4 + T10 (×2)**: cast at full mana → 0 gain twice. 4 mana wasted across the game.
  - **Correlation Matrix DRAW bug T20**: cast for 4 mana expecting +3 cards, drew 0. Pure tempo loss.
  - **PCD as attacker T22 mistake**: sent PCD into combat where FCB + DMA-buffed +4 power killed it. Should have held PCD as wall.
  - **Mulligan policy validated**: opener had Stat Arb Clerk + Correlation Trader + Risk Manager — correct shape, survived T1-T7.
  - **Open question for iter-2**: would Quant beat HF cleaner if Quant had ONE 2-cost spot-removal Order? Untested. Currently Quant has zero answers to DMA + ASSETs.
