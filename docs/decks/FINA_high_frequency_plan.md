# FINA_high_frequency — Plan

## Composition summary

Aggressive tempo deck built around Alpha Strike chip damage. 2-cost Trader chassis (Spoofing Algo, Front-Running Algo, Retail Flow Chaser, Flash Crash Bot, Fill-or-Kill Executor) — most are 2/1 or 3/1 with the Alpha Strike keyword. Support: Direct Market Access (ASSET, +4/+0 static to Alpha Strikers — see strategy doc contested question), Speed Amplifier (DERIVATIVE, +2/+0 auto-attach), Tick Data Archive (ASSET, draw on solo-attack), Momentum Ignition / Low-Latency Strike (Orders), Quote Stuffing Burst (STRATEGY).

## Win condition

**Plan A (primary): Solo Alpha Strike chip race.** Land a 2/1 attacker T1-T2, swing solo for +3 alpha = 4-5 face per turn through T9. Drop opponent to 12-15 capital before they stabilise. Close with a buffed solo-swing finisher (FCE + DMA + Speed Amp = 6-7 power solo).

**Plan B (race insurance): Quote Stuffing Burst alpha.** Hold QSB for the swing where +3/+0 + alpha-grant chains an 8+ power hit through any blocker.

## Target turns (Plan A — solo chip race)

- **T1**: Retail Flow Chaser (1/1 Alpha Strike) deploy.
- **T2**: Spoofing Algo (2/1 Alpha Strike) deploy. Don't attack with both — solo-attack RFC for +3 alpha = 4 face damage. Engine bug: only the FIRST declared attacker gets the alpha buff in multi-attack. Always solo-attack with HF.
- **T3-T9**: Solo-attack one Trader per turn for 4-5 face. Drop a 2nd Trader as backup. Target opponent at 18-20 capital by T9.
- **T10-T15**: Quant typically deploys 4-tough wall + PCD lord here. Hold QSB or DMA for a buffed swing that breaks through. Block defensively with FCB / Bandwidth Predator (3-toughness bodies) to kill PCD when it attacks.
- **T15-T20**: Closing window. If you've kept opponent under 16 capital and have FCE + DMA on board, swing for 6-7 power solo for lethal range.

## Mulligan policy

- **Auto-keep**: any 2-cost Alpha Strike Trader (Spoofing, FRA, RFC, FCB, FCE) + 1 other 2-3 cost Trader. Sets up the T1-T2 chip plan.
- **Auto-keep (good)**: 1-cost RFC + 2-cost Alpha Striker + Direct Market Access. DMA T3 = +4/+0 static (per Pilot B's observation; see strategy doc contested question).
- **Salvage**: hand with 2-3 Traders but no DMA / no QSB. Plan B (chip-only) is viable but expect to lose to a stabilised Quant.
- **Auto-mull**: 0 cards costing ≤2.

## Play priorities (order)

1. **Always deploy a 2-cost Alpha Strike Trader on T2 if available.** Tempo > value.
2. **NEVER multi-attack with Alpha Strike Traders.** Solo-attack only — only the first declared gets +3 alpha. Multi-attack = lose the alpha buff on every other attacker. Wait one more turn to deploy the second attacker if needed.
3. **Hold Direct Market Access** until you have a 2-3 power Trader on board to multiply (the static +4/+0 amplifies any Alpha Striker).
4. **Don't auto-cast Liquidity Provision** at full mana — only cast when chaining a 4+ cost play same turn or when current mana < max - 2.
5. **Don't auto-cast Speed Amplifier on a 2/1 Trader** if it's likely to trade in 1 turn — Speed Amp orphans on the attached Trader's death (engine bug, see strategy doc). Prefer to attach to a 3+ tough body (Bandwidth Predator, Fill-or-Kill Executor).
6. **Hold Quote Stuffing Burst** for the turn an Alpha Striker is set up to solo-swing for lethal-range damage.
7. **Block PCD with cheap chumps when Quant attacks.** Killing PCD removes the +0/+1 lord; Quant's wall folds without it.

## Anticipated weaknesses

- **Quant's 4-tough wall + PCD lord (iter-1, P=Lost).** Once Quant has 3+ Traders + PCD on board, HF's 1-2 toughness Alpha Strikers can't break through cleanly. The chip-window closes hard around T10-T12.
- **Hand starvation late game.** From T15 onward HF draws 1 card per turn. Tick Data Archive's "attacked-alone last turn" trigger doesn't fire (engine bug — see strategy doc); without that draw, HF runs out of cards by T20.
- **Speed Amplifier orphans** when its attached Trader trades. Wastes 2 mana for the rest of the game (engine bug).
- **Direct Market Access alpha upgrade is currently unwired** (engine bug, contested between pilots — likely the static +4/+0 fires but the alpha-bonus-upgrade-to-+4 flag is dead). DMA's value is currently capped by the static-power-buff path only.

## Iteration log

- **2026-05-08 (iter-1)**: vs FINA_quant (LLM Pilot B, double-pilot mode). **Lost** in 28 turns; final P1=0 P2=16. Pilot A self-graded the play as decent given the wall — chipped 12 capital off Quant by T9 (Spoofing solo, FRA solo, FCE solo) but couldn't break the 4-tough wall + PCD lord post-T10. Hand starved by T15.
  Key new findings:
  - **Solo Alpha Strike pressure dropped opp from 30 → 18 in 9 turns** with mostly favorable trades — strong opening.
  - **Multi-attacker alpha bug confirmed**: T7 swing with Spoofing + FRA only buffed Spoofing (+3 alpha); FRA stayed at 2 power (lost alone-status). Total dmg ~7 vs solo would be 5 — concentrated solo damage is harder to chump efficiently.
  - **Tick Data Archive useless**: solo-attacked multiple times, never drew the bonus card. Asset is dead until engine fix.
  - **Speed Amplifier dead from T9**: Speed Amp attached to FRA, FRA died, Amp orphaned on dead ID for the rest of the game.
  - **Late-game blocks killed PCD twice (T16, T22)** with FCB — only way HF made a dent in Quant's late game. Without these two PCD kills, HF would have died T20 instead of T28.
  - **Mulligan policy refined**: hand had RFC + Spoofing + FRA + FCE + Speed Amp + DMA + Tick Data Archive + Bandwidth Predator. Good shape on paper; in practice the late-game ASSETs (DMA, Tick Data) didn't carry their weight.
  - **Open question for iter-2**: would HF win if it side-boarded MORE 2-cost Alpha Strikers and CUT the Tick Data Archive + 1 Speed Amp? Untested. Mass-tempo HF should be tried.
