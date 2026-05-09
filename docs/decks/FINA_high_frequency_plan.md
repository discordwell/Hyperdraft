# FINA_high_frequency — Plan

## Composition summary

Aggressive tempo deck built around Alpha Strike chip damage. 2-cost Trader chassis (Spoofing Algo, Front-Running Algo, Retail Flow Chaser, Flash Crash Bot, Fill-or-Kill Executor) — most are 2/1 or 3/1 with the Alpha Strike keyword. Support: Direct Market Access (ASSET, +4/+0 static to Alpha Strikers — see strategy doc contested question), Speed Amplifier (DERIVATIVE, +2/+0 auto-attach), Tick Data Archive (ASSET, draw on solo-attack), Momentum Ignition / Low-Latency Strike (Orders), Quote Stuffing Burst (STRATEGY).

## Win condition

**Plan A (primary, iter-6 confirmed): Board flood + DMA spike.** Deploy a Trader every turn (no exceptions) → save DMA → on the DMA deploy turn, multi-attack with ALL bodies, declaring best Alpha Striker FIRST. T9 setup with 4 bodies + DMA delivers 9+ face. With opponent at ≤12 capital at T9 spike, game closes T11. **DMA spike applies in multi-attack — it is not solo-only.**

**Plan B (solo chip race, pre-Bug-23-fix legacy): Solo Alpha Strike chip race.** Land a 2/1 attacker T1-T2, swing solo for +3 alpha = 4-5 face per turn through T9. Drop opponent to 12-15 capital before they stabilise. Close with a buffed solo-swing finisher (FCE + DMA + Speed Amp = 6-7 power solo). Still valid as fallback if multi-attack path is unavailable.

**Plan C (race insurance): Quote Stuffing Burst alpha.** Hold QSB for the swing where +3/+0 + alpha-grant chains an 8+ power hit through any blocker.

## Target turns (Plan A — board flood + DMA spike)

- **T1**: Retail Flow Chaser (1/1 Alpha Strike) deploy.
- **T2**: Spoofing Algo (2/1 Alpha Strike) deploy. Solo-attack RFC for +3 alpha = 4 face. **Engine bug 2 note**: only the FIRST declared attacker gets the alpha buff in multi-attack — exploit this by always declaring your best Alpha Striker first.
- **T3-T8**: Deploy one Trader PER TURN without exception. Solo-attack highest-alpha Trader each turn for 4-5 face. No spells — non-Trader cards are dead weight in the mirror. Target: 4 active Traders by T8.
- **T9 (spike turn)**: Deploy DMA (3 mana). Multi-attack with ALL bodies — declare best Alpha Striker (FCB/FCE) FIRST. DMA's +4/+0 fires on the first-declared attacker. 4 bodies at T9 = 9+ face if unblocked. Reduces opponent from ~15→6 or better.
- **T10-T11**: Deploy any remaining Traders. Multi-attack for lethal. Game should close by T11.

## Mulligan policy

- **Auto-keep**: any 2-cost Alpha Strike Trader (Spoofing, FRA, RFC, FCB, FCE) + 1 other 2-3 cost Trader. Sets up the T1-T2 chip plan.
- **Auto-keep (good)**: 1-cost RFC + 2-cost Alpha Striker + Direct Market Access. DMA T3 = +4/+0 static (per Pilot B's observation; see strategy doc contested question).
- **Salvage**: hand with 2-3 Traders but no DMA / no QSB. Plan B (chip-only) is viable but expect to lose to a stabilised Quant.
- **Auto-mull**: 0 cards costing ≤2.

## Play priorities (order)

1. **Always deploy a Trader every single turn.** No exceptions in the mirror. Tempo > value. Traders only until you have ≥4 active bodies.
2. **In the HF mirror: defer all non-Trader spells** (Spells, ASSETs, DERIVATIVEs) until you have ≥4 Traders. Non-Trader cards are dead weight in the mirror at this game speed. Exception: DMA is the one ASSET worth holding for the T9 spike.
3. **Declare best Alpha Striker FIRST in any multi-attack.** Bug 2/18: only the first-declared attacker gets the alpha buff (count==1 at trigger time). FCB or FCE declared first = 5-9 power spike; rest deal base power. This asymmetry HELPS you when you exploit it correctly.
4. **DMA deploy turn = multi-attack turn.** DMA's +4/+0 is a 1-turn ETB spike (Bug 21). Deploy DMA AND attack with ALL bodies the same turn. Declare best Alpha Striker first to capture +4 within the alpha+3 boost. Do NOT hold DMA for a "future static buff" — it reverts after the deploy turn.
5. **Prefer 2-cost Alpha Strike Traders** over 3-cost non-Alpha-Strike bodies in the mirror curve. Latency Arbitrageur (3-cost 3/1) underperforms two 2-cost 2/1 Alpha Strikers in T3-T5 window.
6. **Don't auto-cast Liquidity Provision** at full mana — only cast when chaining a 4+ cost play same turn or when current mana < max - 2.
7. **Don't auto-cast Speed Amplifier on a 2/1 Trader** if it's likely to trade in 1 turn — Speed Amp orphans on the attached Trader's death (engine bug). Prefer to attach to a 3+ tough body or skip entirely in mirror.
8. **Hold Quote Stuffing Burst** for the turn an Alpha Striker is set up to solo-swing for lethal-range damage.
9. **Block PCD with cheap chumps when Quant attacks.** Killing PCD removes the +0/+1 lord; Quant's wall folds without it.

## Anticipated weaknesses

- **Quant's 4-tough wall + PCD lord (iter-1, P=Lost).** Once Quant has 3+ Traders + PCD on board, HF's 1-2 toughness Alpha Strikers can't break through cleanly. The chip-window closes hard around T10-T12.
- **Hand starvation late game.** From T15 onward HF draws 1 card per turn. Tick Data Archive's "attacked-alone last turn" trigger doesn't fire (engine bug — see strategy doc); without that draw, HF runs out of cards by T20.
- **Speed Amplifier orphans** when its attached Trader trades. Wastes 2 mana for the rest of the game (engine bug).
- **Direct Market Access alpha upgrade is currently unwired** (engine bug, contested between pilots — likely the static +4/+0 fires but the alpha-bonus-upgrade-to-+4 flag is dead). DMA's value is currently capped by the static-power-buff path only.

## Iteration log

- **2026-05-08 (iter-1 v2, post 20-bug-fix batch)**: vs FINA_quant (LLM Pilot B). **Effective Quant win — stalled at T26**; final P1=20, P2=11 (HF leading capital but traderless, Quant has 5 Traders incl. 3/5 Monopoly Position). Predicted finish T30-T32. Key findings:
  - **Hypothesis "HF can stall against Quant" REJECTED.** With walls now actually holding (bug 1 fix) and RM Arb-heal recurring, HF chipped Quant from 30→11 in 23 turns (19% better than v1's 30→18) but ran out of Traders — hand starvation T23+ left HF with only DPFO/LLS/TTD/QSB (all unplayable in zero-Trader hand). HF must close before T20 or grind to defeat.
  - **Bug 1 fix CONFIRMED.** PT 2/3 took 2 dmg and survived T7. RM 1/4 took 2 dmg and survived T19 with Arb-heal.
  - **Bug 9 RM Arbitrage timing FIXED.** Heal applies AFTER damage now. RM survives 2-power blocks repeatedly.
  - **Bug 17 Rebalancing Halt FIXED.** T15 cast on LA during block window — attacker un-declared, P2 took 0 dmg. Defensive ORDER play is now playable.
  - **Bug 8 Quant Signal FIXED.** Hand stayed at 6 (lost QS, gained 1 from top of library).
  - **Bug 5 Speed Amp orphan FIXED.** SA died with FCE host on T11.
  - **Bug 2 Multi-attack alpha STILL solo-only.** Multi-attack with 3-5 attackers on T7/T19/T21 buffed nobody. Continue to declare best Alpha Striker first and accept rest deal base power.
  - **Bug 6 Tick Data Archive STILL broken.** TDA played, multiple solo alpha attacks, never granted bonus draw. Cut TDA from deck.
  - **NEW bug #21**: HFT Feed Colocation +1/+0 NOT firing. Same QUERY priority issue as #19. FRA solo showed 5/1 (2+3 alpha, no +1 HFT). Audit `_hft_feed_colocation_setup` priority.
  - **Strategy implication**: HF needs MORE 1-cost Trader chassis (8-10) to avoid hand starvation past T15. Multi-attack with 4-5 wide is now profitable for face damage even without alpha buff (chumps don't leak any more, but multiple unblocked attackers do the work).
  - Pilot reports: `logs/finance_ultra_iter1v2_pilotA.md`, `logs/finance_ultra_iter1v2_pilotB.md`.

- **2026-05-08 (iter-6 single, P2a iter-3)**: vs FINA_high_frequency heuristic (single-pilot). **WON** T11; ME=10, AI=0. First pilot win. Board flood + DMA spike T9 with Bug 23 fixed. Key findings:
  - **DMA multi-attack spike confirmed.** FCB declared first in 4-body multi-attack: alpha +3 AND DMA +4 = 9/1 FCB. Not solo-only; works in multi-attack when Alpha Striker declared first.
  - **Win condition locked in.** Deploy every turn → save DMA → T9 multi-attack with all bodies (best Alpha first). 4 bodies + DMA + opponent at ~15 = lethal in 2 turns.
  - **Non-Trader spells are zero value in mirror.** Sub-Penny Intercept, Dark Pool Flash Order, Low-Latency Strike, Speed Amplifier, Momentum Ignition: all stayed in hand, none contributed. Deck construction: cut 4-6 non-Trader slots for 2-cost Alpha Strikers.
  - **3-cost non-Alpha-Strike bodies are suboptimal.** Latency Arbitrageur (3/1, cost 3) was awkward vs 2-cost 2/1 Alpha Strikers. Keep curve ≤2 for mirror construction.
  - **AI cluster-deploy left only 2 active blockers at T9.** AI played 2 FCBs T2 then idled → 2 more bodies T8 with SS. By T9 only 2 active blockers. Spread deploy beats cluster deploy in the mirror.
  - **AI bias update**: `attack_threshold` 0.0→0.05 (wait for ≥2 unblocked attackers OR DMA in play before committing).

- **2026-05-08 (iter-5 single, P2a iter-2)**: vs FINA_high_frequency heuristic (single-pilot mode). **Lost** T12; ME=0, AI=~15. Board flood executed well (8 Traders by T11, deploy-every-turn discipline from iter-4 lesson). But multi-attack face output collapsed to ~2 regardless of board size — Bug 23. Key findings:
  - **Bug 23 FIXED (harness-level, not engine).** Sequential `attack <id>` commands overwrote `attackers_declared`; only the last attacker's damage resolved. Post-fix: 2-attacker test dealt 7 face (correct). Multi-attack now reliable.
  - **Solo-alpha was the only effective combat path while Bug 23 was active.** With 7 Traders on board and sequential declarations, still only 2 face landed. Temporary rec from pilot: until bug fixed, single vararg `attack <id1> <id2>...` or solo-alpha only. **Moot now — bug fixed.**
  - **Board flooding is confirmed correct.** 8 Traders by T11 is achievable and correct strategy when multi-attack damage resolves properly.
  - **AI with 1 Trader dealing 5-11 face was normal behavior.** The asymmetry was entirely Bug 23 on the human side, not engine asymmetry.

- **2026-05-08 (iter-4 single, P2a)**: vs FINA_high_frequency heuristic (single-pilot mode). **Lost** T12; Pilot=0, AI=3. Body-count mirror: AI deployed 6 Traders by T10 vs pilot's 3 (FCE + 2×2/1). Pilot dealt 27 total face damage (4+4+6+7+6) and nearly closed but AI's flood pace (6-8 face/turn) outrun pilot's 4-7/turn. Key findings:
  - **HF mirror = body-count race. Flood wins.** 6 bodies > DMA + 3 bodies in damage-per-turn. Deploy priority in mirror: Traders ONLY until ≥4 bodies. Defer all ASSETs/DERIVATIVEs.
  - **DMA is a 1-turn spike, not ongoing static (Bug 21).** FCE=7 on DMA deploy turn (T9), FCE=6 the next turn (T11). Always attack with FCE the same turn DMA is played. The +4 is gone after turn of entry.
  - **QSB applies to wrong Trader (Bug 22).** With RFC+FCE+Spoofing on board, QSB buffed RFC (1/1) instead of FCE (3/2). Do NOT play QSB when multiple Traders are on board until Bug 22 is fixed — result is unpredictable.
  - **AI correct to never block.** 1/1 bodies vs 4-7 power = death + overflow. Racing is optimal for HF mirror.
  - **Draw starvation from non-Trader spells.** Held/drew Speed Amp, Ticker Tape, QSB when Traders were needed. Mirror boards require Trader density.
  - **AI bias updated**: board_weight 0.3→0.4, capital_weight 0.5→0.4.
  - **Encoder patches**: mirror flood mode (opp ≥4 bodies → flood), QSB picks highest-power Trader, DMA same-turn attack heuristic.

- **2026-05-08 (iter-1)**: vs FINA_quant (LLM Pilot B, double-pilot mode). **Lost** in 28 turns; final P1=0 P2=16. Pilot A self-graded the play as decent given the wall — chipped 12 capital off Quant by T9 (Spoofing solo, FRA solo, FCE solo) but couldn't break the 4-tough wall + PCD lord post-T10. Hand starved by T15.
  Key new findings:
  - **Solo Alpha Strike pressure dropped opp from 30 → 18 in 9 turns** with mostly favorable trades — strong opening.
  - **Multi-attacker alpha bug confirmed**: T7 swing with Spoofing + FRA only buffed Spoofing (+3 alpha); FRA stayed at 2 power (lost alone-status). Total dmg ~7 vs solo would be 5 — concentrated solo damage is harder to chump efficiently.
  - **Tick Data Archive useless**: solo-attacked multiple times, never drew the bonus card. Asset is dead until engine fix.
  - **Speed Amplifier dead from T9**: Speed Amp attached to FRA, FRA died, Amp orphaned on dead ID for the rest of the game.
  - **Late-game blocks killed PCD twice (T16, T22)** with FCB — only way HF made a dent in Quant's late game. Without these two PCD kills, HF would have died T20 instead of T28.
  - **Mulligan policy refined**: hand had RFC + Spoofing + FRA + FCE + Speed Amp + DMA + Tick Data Archive + Bandwidth Predator. Good shape on paper; in practice the late-game ASSETs (DMA, Tick Data) didn't carry their weight.
  - **Open question for iter-2**: would HF win if it side-boarded MORE 2-cost Alpha Strikers and CUT the Tick Data Archive + 1 Speed Amp? Untested. Mass-tempo HF should be tried.
