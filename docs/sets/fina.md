# FINA — Finance TCG Set 1 (Quant & IB)

## 1. Set Identity

**Set code:** `FINA` · **Set label:** `fina` · **Set module:** `fina`

FINA is the Finance TCG's inaugural set, built around three interlocking systems: the **Leverage** cost engine (borrow power now, pay Capital Reserve at Market Close), the **Dark Pool** timing trap (instant-speed deferred Orders that resolve on the opponent's Trading Session), and the **Derivatives Desk** staging area (Derivatives sit ready until an entering Trader claims them). Every archetype answers the risk/reward question differently: High-Frequency burns fast with Alpha Strike Traders and disposable tempo; Derivatives grinds out value by stacking Leverage counters and using Short Selling to reset and double them; Quant controls with Arbitrage Liquidity generation and passive Asset engines; Dark Arbitrage combo-assembles one giant leveraged Trader behind a wall of Dark Pool traps. The PS1 polygon aesthetic makes every card feel like a Bloomberg terminal FMV sequence — expensive flat-shaded geometry, jewel-tone panels, gold-foil rares rendered as floating triangles.

---

## 2. Mechanics (4 Named Mechanics)

### LEVERAGE N

**Rules text:** This Trader enters with N Leverage counters on it. It gets +1/+0 for each Leverage counter on it. At the start of your Market Close, pay 1 Capital Reserve per Leverage counter or remove all Leverage counters from it.

**Rationale:** Leverage is the central IB concept of borrowing capital to amplify returns with corresponding amplified risk. A Trader with Leverage 3 is a 2/3 that threatens like a 5/3 but drains 3 Capital Reserve per turn if you can't service the debt.

**Implementation note:** Leverage counters stored in `obj.state.counters["leverage"]`. The global `_register_leverage_tick` interceptor in `finance.py` fires on `PHASE_START(market_close)` and emits `LIFE_CHANGE(amount=-leverage_count)`. Card-level: ETB trigger adds counters via `COUNTER_ADDED` events; no additional per-card system interceptor needed.

---

### ARBITRAGE N

**Rules text:** When this card enters the Trading Floor, if you control more Traders than your opponent, gain N Liquidity this turn.

**Rationale:** Arbitrage extracts profit from position differentials — here, having more Traders is the price discrepancy; Arbitrage converts board lead into Liquidity acceleration.

**Implementation note:** ETB trigger via `make_etb_trigger`. Effect function counts `FIN_TRADER` objects on the battlefield for each player and if controller leads, emits a turn-data adjustment to `player.mana_crystals_available += N`.

---

### DARK POOL (keyword on Orders)

**Rules text:** When you play this Order with Dark Pool, instead of resolving immediately, place it face-down in the Dark Pool zone. It triggers at the start of your opponent's next Trading Session.

**Rationale:** Dark Pools are private off-exchange venues where block orders hide until execution — the card goes "off-book" and fires at a moment the opponent cannot respond to.

**Implementation note:** The global `_register_dark_pool_trigger` system interceptor in `finance.py` handles the full cycle. At card level, Dark Pool Orders register a `FIN_MARKET_EVENT` filter interceptor as their actual effect.

---

### SHORT SELLING

**Rules text:** Exile target Trader you control. At the start of your next Pre-Market, return it to the Trading Floor with two +1/+1 counters on it.

**Rationale:** Short selling exiles a position temporarily and returns it doubled — protects from removal, resets damage, and returns with permanent +1/+1 counters.

**Implementation note:** Strategy/Order emits `ZONE_CHANGE` to `EXILE` for target Trader and registers a one-shot `PHASE_START(pre_market)` interceptor that fires next turn to emit `ZONE_CHANGE` back to `BATTLEFIELD` plus two `COUNTER_ADDED` events for "+1/+1" counters.

---

### ALPHA STRIKE (keyword on Traders)

**Rules text:** When this Trader attacks alone (no other Traders you control are attacking), it gets +3/+0 until Market Close.

**Rationale:** Alpha means excess return above the benchmark — going alone and outperforming. Creates interesting declare-attackers decisions: wide board for distributed damage, or one Alpha Striker for a devastating single hit.

**Implementation note:** `make_attack_trigger` on `ATTACK_DECLARED`. Effect function counts attacking `FIN_TRADER` objects controlled by the same player at trigger time. If count == 1, emit `PT_MODIFICATION(power_mod=+3, duration="end_of_turn")`.

---

## 3. Archetypes (4)

### Archetype 1: HIGH-FREQUENCY (FINA_high_frequency)

**Strategy:** Deploy a swarm of cheap Alpha Strike Traders turns 1–3, protect with Dark Pool Orders, swing alone for 5–7 damage. Never be forced to block; always attack.

**Key cards:** Flash Crash Bot, Front-Running Algo, Dark Pool Flash Order, HFT Feed Colocation, Quote Stuffing Burst, Momentum Ignition

**Loop:** Deploy cheap Alpha Strike Traders → Dark Pool Orders clear blockers → Alpha Strike alone for lethal.

---

### Archetype 2: DERIVATIVES (FINA_derivatives)

**Strategy:** Stack Leverage counters on powerful Traders; use Short Selling to reset and double +1/+1 counters. Derivatives Desk accelerates tempo. Win mid-game when opponents can't trade favorably into a Leverage-pumped Trader.

**Key cards:** Delta Hedger, Gamma Scalper, Short Squeeze, Theta Decay Collar, Vega Spike, The Black-Scholes Model

**Loop:** Play Leverage Trader → pump with Vega Spike → Short Sell to reset damage and gain +1/+1 counters → repeat for a dominant permanent threat.

---

### Archetype 3: QUANT (FINA_quant)

**Strategy:** Generate overwhelming Liquidity advantage through Arbitrage triggers and passive Assets. High-defense/low-aggression Traders survive long enough for Arbitrage to fire. Win by grinding out card advantage and outvaluing the opponent.

**Key cards:** Risk Manager, Quant Lab, Portfolio Diversifier, Correlation Matrix, Systematic Alpha Engine, Monopoly Position

**Loop:** Establish board majority → fire Arbitrage each turn for bonus Liquidity → use surplus for control cards → deck/outvalue opponent.

---

### Archetype 4: DARK ARBITRAGE (FINA_dark_arbitrage)

**Strategy:** Spend turns 1–4 staging Dark Pool Orders defensively, suppressing the opponent's board. Deploy one enormous Leverage + Arbitrage Trader turn 5–6. Arbitrage refuels; Alpha Strike closes the game.

**Key cards:** Dark Pool Aggressor, Off-Exchange Position, Block Trade Sweep, Liquidity Event, Principal Trading Desk, Dark Venue Console

**Loop:** Stage Dark Pool Orders → protect with them → resolve Dark Pool Aggressor → Arbitrage 2 refuels → Alpha Strike alone for lethal.

---

## 4. Card List (150 Cards)

Deck label codes: **HF** = FINA_high_frequency, **DV** = FINA_derivatives, **QT** = FINA_quant, **DA** = FINA_dark_arbitrage, **N** = Neutral.

---

### HIGH-FREQUENCY — 37 cards

| Name | Type | Cost | P/T | Archetype | Rules Text |
|------|------|------|-----|-----------|-----------|
| Flash Crash Bot | Trader | {1} | 2/1 | HF | Alpha Strike. When this enters, gain 1 Liquidity this turn. |
| Retail Flow Chaser | Trader | {1} | 1/1 | HF | Alpha Strike. |
| Spoofing Algo | Trader | {2} | 2/1 | HF | Alpha Strike. When this attacks alone, opponent cannot play Orders until Market Close. |
| Front-Running Algo | Trader | {2} | 2/1 | HF | Alpha Strike. When this deals unblocked damage to Capital Reserve, draw a card. |
| Tape Painter | Trader | {2} | 1/2 | HF | Alpha Strike. When this attacks alone, gain 1 Liquidity this turn. |
| Colocation Server | Trader | {2} | 2/2 | HF | Alpha Strike. Summoning sickness does not apply to this Trader. |
| Latency Arbitrageur | Trader | {3} | 3/1 | HF | Alpha Strike. When this attacks alone and deals unblocked damage, it deals 1 additional damage. |
| Momentum Igniter | Trader | {3} | 3/2 | HF | Alpha Strike. When this enters, each other Trader you control gains Alpha Strike until Market Close. |
| Order Router | Trader | {3} | 2/3 | HF | Alpha Strike. When this blocks, draw a card. |
| Fill-or-Kill Executor | Trader | {3} | 3/2 | HF | Alpha Strike. When this attacks alone and is not blocked, gain 2 Liquidity this turn. |
| Speed Advantage Desk | Trader | {4} | 4/2 | HF | Alpha Strike. Leverage 1. When this attacks alone, +3/+0 applies before Leverage bonus. |
| Bandwidth Predator | Trader | {4} | 3/3 | HF | Alpha Strike. When this deals damage to a Trader, that Trader does not untap next Pre-Market. |
| Microwave Relay | Trader | {4} | 4/3 | HF | Alpha Strike. When this enters, if you have no other Traders, gain 2 Liquidity this turn. |
| Nanosecond Assassin | Trader | {5} | 5/3 | HF | Alpha Strike. Leverage 2. Alpha Strike bonus is +4/+0 for this Trader. |
| Dark Pool Flash Order | Order | {1} | — | HF | Dark Pool. When this triggers, deal 2 damage to target Trader. |
| Sub-Penny Intercept | Order | {1} | — | HF | Target attacking Trader gets -2/-0 until end of Trading Session. |
| Pre-Market Raid | Order | {1} | — | HF | During opponent's Trading Session only: deal 1 damage to target Trader. |
| Execution Glitch | Order | {2} | — | HF | Counter target Order. |
| Spoofed Bid | Order | {2} | — | HF | Dark Pool. When this triggers, target Trader gets -3/-0 until Market Close. |
| Cancel Order | Order | {2} | — | HF | Target Trader cannot attack this turn. |
| Quote Stuffing Burst | Order | {2} | — | HF | Target Trader you control gets +3/+0 and Alpha Strike until Market Close. |
| Circuit Breaker Trip | Order | {3} | — | HF | Destroy target Trader with Aggression 4 or greater. |
| Regulatory Halt | Order | {3} | — | HF | Dark Pool. When this triggers, tap target Trader (it cannot attack this turn). |
| Low-Latency Strike | Strategy | {2} | — | HF | Each of your Traders with Alpha Strike may attack this turn even if they have summoning sickness. |
| Momentum Ignition | Strategy | {3} | — | HF | Each of your Traders attacks this turn if able. Traders with Alpha Strike get +2/+0 until Market Close. |
| Flash Crash Event | Strategy | {3} | — | HF | Destroy all Traders with Defense Rating 2 or less. |
| Pump-and-Dump | Strategy | {4} | — | HF | Target Trader you control gets +4/+0 until Market Close. Then place 2 Leverage counters on it. |
| Acceleration Protocol | Strategy | {4} | — | HF | Your Traders get +2/+0 until Market Close. Each Trader with Alpha Strike gets +1/+0 additionally. |
| HFT Feed Colocation | Asset | {2} | — | HF | Static: your Traders with Alpha Strike get +1/+0. |
| Tick Data Archive | Asset | {2} | — | HF | At the start of your Pre-Market, if any of your Traders attacked alone last turn, draw a card. |
| Speed Co-location Hub | Asset | {3} | — | HF | At the start of your Trading Session, you may have one Trader lose summoning sickness this turn. |
| Direct Market Access | Asset | {3} | — | HF | Static: your Alpha Strike bonus is +4/+0 instead of +3/+0. |
| High-Speed Network | Asset | {4} | — | HF | Activated: {2}, tap — give target Trader Alpha Strike until Market Close. |
| Order Matching Engine | Structure | {3} | — | HF | Tap: target Trader you control gets +2/+0 until Market Close. |
| Low-Latency Exchange | Structure | {4} | — | HF | At the start of your Trading Session, each of your Traders with Alpha Strike gets +1/+0 until Market Close. |
| Ticker Tape Derivative | Derivative | {2} | — | HF | Attach to a Trader: it gains Alpha Strike. |
| Speed Amplifier | Derivative | {2} | — | HF | Attach to a Trader: it gets +2/+0. When it attacks alone, draw a card. |

---

### DERIVATIVES — 37 cards

| Name | Type | Cost | P/T | Archetype | Rules Text |
|------|------|------|-----|-----------|-----------|
| Options Desk Intern | Trader | {1} | 1/2 | DV | When this enters, you may attach a Derivative from your Derivatives Desk to it for free. |
| Underlying Asset Runner | Trader | {2} | 2/2 | DV | Leverage 1. |
| Delta Hedger | Trader | {3} | 2/4 | DV | Leverage 2. When damage is dealt to this Trader, reduce it by 1 (minimum 0). |
| Rho Opportunist | Trader | {3} | 3/2 | DV | Leverage 1. When a Leverage counter is added to this, draw a card. |
| Theta Decay Trader | Trader | {3} | 2/3 | DV | Leverage 2. At the start of your Pre-Market, remove 1 Leverage counter from this (does not cost Capital Reserve). |
| Gamma Scalper | Trader | {4} | 3/3 | DV | Leverage 3. Once per game, if the Market Close drain would reduce your Capital Reserve to 0, remove all Leverage counters instead. |
| Convexity Rider | Trader | {4} | 2/5 | DV | Leverage 2. When this is Short Sold, return with 3 +1/+1 counters instead of 2. |
| Vega Amplifier | Trader | {4} | 4/3 | DV | Leverage 3. When this enters, each other Trader you control with Leverage gets +1/+0 until Market Close. |
| Structured Product Builder | Trader | {4} | 3/4 | DV | Leverage 2. Derivatives attached to this cost {1} less to play. |
| Hedge Fund PM | Trader | {5} | 4/4 | DV | Leverage 2. When this enters, attach all Derivatives from your Derivatives Desk to this Trader. |
| Synthetic Long | Trader | {5} | 5/4 | DV | Leverage 3. At Market Close, you may pay 2 Capital Reserve per counter instead of 1 to keep all Leverage counters; if you do, this gets +1/+0 permanently. |
| Risk-Parity Quant | Trader | {3} | 2/3 | DV | When a +1/+1 counter is placed on this, place an additional +1/+1 counter on it. |
| Leveraged Buyout Specialist | Trader | {6} | 5/5 | DV | Leverage 4. When this enters, gain Liquidity equal to its Leverage count this turn. |
| Exposure Manager | Trader | {2} | 1/3 | DV | Leverage 1. When any Leverage counter is removed from a Trader you control, gain 1 Liquidity. |
| Basis Trade Analyst | Trader | {3} | 3/2 | DV | Leverage 1. When this attacks, you may move 1 Leverage counter from it to another Trader you control. |
| Short Squeeze | Strategy | {2} | — | DV | Short Selling — exile target Trader you control. Return it at the start of your next Pre-Market with two +1/+1 counters. |
| Vega Spike | Strategy | {3} | — | DV | Place 2 Leverage counters on target Trader you control. |
| Volatility Crush | Order | {2} | — | DV | Remove all Leverage counters from target Trader. If opponent's, deal damage equal to counters removed to that Trader. |
| Margin Call | Strategy | {4} | — | DV | Each of your Traders loses all Leverage counters. For each counter removed this way, deal 1 damage to target opponent Trader. |
| Capital Call | Strategy | {5} | — | DV | Search your Book for a Trader with Leverage and put it into your hand. Gain Liquidity equal to its Leverage value this turn. |
| Leveraged Buyout | Strategy | {5} | — | DV | Gain control of target Trader. Place Leverage counters on it equal to its Defense Rating. |
| Gamma Hedge | Order | {2} | — | DV | Target Trader you control gets +1/+1 for each Leverage counter on it until Market Close. |
| Delta Neutral | Order | {3} | — | DV | Target Trader you control loses all Leverage counters. Remove all damage from it. |
| Cover Short | Order | {2} | — | DV | Return an exiled Trader you own to the Trading Floor immediately, with its counters. |
| Carry Trade | Strategy | {3} | — | DV | Gain 1 Liquidity for each Leverage counter across all Traders you control (maximum 5). |
| The Black-Scholes Model | Asset | {3} | — | DV | At the start of your Pre-Market, you may pay 1 Liquidity to remove 1 Leverage counter from any Trader you control. |
| Implied Volatility Surface | Asset | {3} | — | DV | Static: Traders you control with Leverage counters get +0/+1. |
| Greeks Dashboard | Asset | {4} | — | DV | Activated: {2}, tap — add 1 Leverage counter to target Trader you control. |
| Derivatives Desk Console | Structure | {3} | — | DV | At the start of your Pre-Market, if you have at least one Derivative on your Derivatives Desk, draw a card. |
| Risk Waterfall | Structure | {4} | — | DV | At the start of your Market Close, reduce the Capital Reserve cost of Leverage counters on one of your Traders by 1 (minimum 0 per counter). |
| Theta Decay Collar | Derivative | {2} | — | DV | Attach to a Trader: it gets +1/+2 and loses 1 Leverage counter at the end of each Pre-Market. |
| Gamma Amplifier | Derivative | {3} | — | DV | Attach to a Trader: it gets +2/+1. Its Leverage counters cost 0 Capital Reserve at Market Close this turn. |
| Delta Neutral Wrap | Derivative | {2} | — | DV | Attach to a Trader: remove all damage from it and it gets +0/+2. |
| Iron Condor | Derivative | {3} | — | DV | Attach to a Trader: when this Trader is blocked, deal 1 damage to the blocker. |
| Protective Put | Derivative | {2} | — | DV | Attach to a Trader: the first time this Trader would be destroyed, remove this Derivative instead. |
| Covered Call | Derivative | {2} | — | DV | Attach to a Trader: it gets +1/+0 and, when it attacks unblocked, gain 1 Liquidity. |
| Synthetic Collar | Derivative | {3} | — | DV | Attach to a Trader: it gets +1/+1 for each Derivative attached to it (including this one). |

---

### QUANT — 37 cards

| Name | Type | Cost | P/T | Archetype | Rules Text |
|------|------|------|-----|-----------|-----------|
| Statistical Arb Clerk | Trader | {1} | 1/2 | QT | Arbitrage 1. |
| Factor Model Analyst | Trader | {2} | 1/3 | QT | Arbitrage 1. When Arbitrage triggers, draw a card. |
| Risk Manager | Trader | {2} | 1/4 | QT | Arbitrage 1. When this blocks, remove 1 damage from it after combat. |
| Correlation Trader | Trader | {3} | 2/4 | QT | Arbitrage 1. Static: your other Traders with Defense Rating 3 or greater get +0/+1. |
| Pairs Trader | Trader | {3} | 2/3 | QT | Arbitrage 2. When this enters, if Arbitrage triggers, gain 2 Liquidity this turn. |
| Mean Reversion Bot | Trader | {3} | 1/4 | QT | At the start of your Pre-Market, remove 1 damage from this Trader. |
| Factor Exposure Desk | Trader | {4} | 2/5 | QT | Arbitrage 2. When this enters, if Arbitrage triggers, draw a card. |
| Smart Beta Strategist | Trader | {4} | 3/4 | QT | Arbitrage 1. When this attacks, if your Capital Reserve is higher than opponent's, draw a card. |
| Drawdown Controller | Trader | {4} | 2/5 | QT | When this enters, remove all damage from one Trader you control. |
| Portfolio Construction Desk | Trader | {4} | 3/4 | QT | Arbitrage 2. Your other Traders get +0/+1. |
| Systematic Rebalancer | Trader | {5} | 3/5 | QT | Arbitrage 2. At the start of your Pre-Market, you may move 1 damage counter from one of your Traders to another. |
| Cross-Sectional Alpha Machine | Trader | {5} | 4/5 | QT | Arbitrage 3. When Arbitrage triggers, also gain 1 Liquidity for each Trader you control beyond the opponent count. |
| Machine Learning Optimizer | Trader | {6} | 4/6 | QT | Arbitrage 3. When this enters, draw cards equal to your Arbitrage triggers this game (maximum 4). |
| Monopoly Position | Trader | {7} | 3/5 | QT | Alternate win: at the start of your Pre-Market, if your Portfolio Value counter total is 20 or greater, you win the game. When this enters, place 5 Portfolio Value counters on it. Each other Trader you control with Arbitrage places 1 Portfolio Value counter on this each Pre-Market. |
| Information Ratio Enforcer | Order | {2} | — | QT | Counter target Order or Strategy unless its controller pays {2}. |
| Rebalancing Halt | Order | {2} | — | QT | Target Trader cannot attack this turn. Draw a card. |
| Efficient Frontier | Order | {3} | — | QT | Prevent all damage to target Trader you control until end of Trading Session. |
| Quant Signal | Order | {1} | — | QT | Look at the top 3 cards of your Book. Put one into your hand, the rest on the bottom. |
| Sharpe Ratio Alert | Order | {2} | — | QT | If your Capital Reserve is at least 5 more than your opponent's, draw 2 cards. |
| Regime Change Detection | Order | {3} | — | QT | Counter target Strategy. |
| Liquidity Provision | Order | {2} | — | QT | Gain 3 Liquidity this turn. (Cannot exceed your Liquidity maximum.) |
| Risk-Adjusted Return | Strategy | {3} | — | QT | Gain Liquidity equal to the number of Traders you control beyond your opponent's count (minimum 0, maximum 4). |
| Correlation Matrix | Strategy | {4} | — | QT | Draw cards equal to Traders you control minus opponent's Traders (minimum 0, maximum 4). |
| Information Advantage | Strategy | {3} | — | QT | Draw 2 cards. If you control more Traders than your opponent, draw 3 instead. |
| Factor Neutralization | Strategy | {5} | — | QT | Destroy all Traders with Aggression greater than Defense Rating. |
| Portfolio Stress Test | Strategy | {4} | — | QT | Each player discards down to 3 cards. You draw 2 cards. |
| Portfolio Diversifier | Asset | {2} | — | QT | Your Liquidity maximum is 1 higher than normal (max 11). |
| Sharpe Ratio Monitor | Asset | {2} | — | QT | At the start of your Pre-Market, if you control more Traders than your opponent, gain 1 Liquidity this turn. |
| Backtesting Engine | Asset | {3} | — | QT | Activated: {2}, tap — look at the top 5 cards of your Book; put one into your hand and the rest on the bottom. |
| Systematic Alpha Engine | Asset | {4} | — | QT | At the start of your Pre-Market, if you control more Traders than your opponent, gain 2 Liquidity this turn. |
| Risk Attribution Model | Asset | {3} | — | QT | Static: your Traders with Defense Rating 4 or greater get +0/+1. |
| Live P&L Dashboard | Asset | {4} | — | QT | At the start of your Research phase, draw an additional card if you control more Traders than your opponent. |
| Quant Lab | Structure | {3} | — | QT | At the start of your Pre-Market, if you control more Traders than your opponent, gain 2 Liquidity this turn. |
| Research Server Farm | Structure | {4} | — | QT | At the start of your Research phase, draw an additional card if your Capital Reserve is 10+ above your opponent's. |
| Alpha Capture Platform | Structure | {4} | — | QT | At the start of your Trading Session, your Traders with Arbitrage get +1/+0 until Market Close. |
| Signal Processing Rig | Derivative | {2} | — | QT | Attach to a Trader: it gains Arbitrage 1. When Arbitrage triggers, remove 1 damage from it. |
| Portfolio Insurance Wrap | Derivative | {3} | — | QT | Attach to a Trader: when this Trader would be destroyed, instead remove this Derivative and it survives with 1 Defense Rating remaining. |

---

### DARK ARBITRAGE — 36 cards

| Name | Type | Cost | P/T | Archetype | Rules Text |
|------|------|------|-----|-----------|-----------|
| Hidden Accumulator | Trader | {2} | 2/2 | DA | When you play a Dark Pool Order, this Trader gets +1/+1 until Market Close. |
| Stealth Position Builder | Trader | {3} | 2/4 | DA | When a Dark Pool Order you staged triggers, draw a card. |
| Off-Exchange Operative | Trader | {3} | 3/3 | DA | Leverage 1. Arbitrage 1. |
| Dark Flow Aggregator | Trader | {3} | 3/2 | DA | When this enters, place a Dark Pool Order from your hand into the Dark Pool zone (bypassing cost). |
| Institutional Block Trader | Trader | {4} | 3/4 | DA | Leverage 2. Arbitrage 1. When this enters, gain 2 Liquidity this turn. |
| Principal Crossings Desk | Trader | {4} | 4/4 | DA | Leverage 2. When this attacks, if the Dark Pool slot is occupied, this gets +2/+0 until Market Close. |
| Dark Pool Architect | Trader | {5} | 4/4 | DA | Leverage 2. Arbitrage 2. When this enters, you may play a Dark Pool Order from your hand at no cost. |
| Dark Pool Aggressor | Trader | {5} | 4/4 | DA | Leverage 3. Arbitrage 2. Alpha Strike. |
| OTC Behemoth | Trader | {6} | 5/5 | DA | Leverage 3. Arbitrage 2. When this attacks alone, opponent cannot play Orders this turn. |
| Internalized Flow Monster | Trader | {7} | 6/5 | DA | Leverage 4. Arbitrage 3. Alpha Strike. When this enters, trigger all Dark Pool Orders currently staged. |
| Shadow Accumulation Desk | Trader | {4} | 3/4 | DA | Arbitrage 2. When this enters, look at opponent's hand. |
| Dark Inventory Position | Trader | {3} | 2/3 | DA | When this enters, search your Book for a Dark Pool Order and put it into your hand. |
| Crossing Network Pilot | Trader | {4} | 4/3 | DA | Leverage 2. When this attacks, deal 1 damage to target Trader regardless of blocking. |
| Off-Exchange Finisher | Trader | {5} | 5/4 | DA | Leverage 2. Arbitrage 2. Alpha Strike bonus is +4/+0 for this Trader. |
| Iceberg Order | Order | {1} | — | DA | Dark Pool. When this triggers, deal 1 damage to target Trader and draw a card. |
| Off-Exchange Position | Order | {2} | — | DA | Dark Pool. When this triggers, target Trader gets -3/-0 until Market Close. |
| Block Trade Sweep | Order | {3} | — | DA | Dark Pool. When this triggers, destroy target Trader with Defense Rating 3 or less. |
| Crossed Market | Order | {2} | — | DA | Dark Pool. When this triggers, target Trader cannot block this turn. |
| Hidden Aggression | Order | {2} | — | DA | Dark Pool. When this triggers, target Trader you control gets +4/+0 until Market Close. |
| Lit-Market Decoy | Order | {1} | — | DA | Draw a card. You may play a Dark Pool Order from your hand this turn without paying its cost. |
| Internalization Order | Order | {3} | — | DA | Dark Pool. When this triggers, deal 3 damage to target Trader. |
| Payment for Order Flow | Order | {2} | — | DA | Dark Pool. When this triggers, gain 3 Liquidity this turn. |
| Pre-Positioned Strike | Order | {3} | — | DA | Dark Pool. When this triggers, deal 2 damage to target player's Capital Reserve directly. |
| Liquidity Event | Strategy | {4} | — | DA | Gain Liquidity equal to the number of Dark Pool Orders you have played this game (maximum 5). |
| Information Asymmetry | Strategy | {3} | — | DA | Gain control of the opponent's currently staged Dark Pool Order. |
| Dark Liquidity Surge | Strategy | {4} | — | DA | Gain 2 Liquidity for each Dark Pool Order that has triggered this game (maximum 6). |
| Capital Structure Arb | Strategy | {5} | — | DA | Place 3 Leverage counters on target Trader you control. It also gets Arbitrage 2 until Market Close. |
| Spoofing Campaign | Strategy | {3} | — | DA | Destroy all Traders with Aggression 2 or less. |
| Principal Trading Desk | Structure | {4} | — | DA | At the start of your Pre-Market, if the Dark Pool slot is empty, draw a card. |
| Dark Venue Console | Structure | {4} | — | DA | At the start of your Trading Session, you may pay {1} to trigger the staged Dark Pool Order immediately. |
| Dark Flow Engine | Asset | {3} | — | DA | Static: Dark Pool Orders you control cost {1} less to stage. |
| Order Flow Analytics | Asset | {3} | — | DA | At the start of your Pre-Market, if the Dark Pool slot is occupied, gain 2 Liquidity this turn. |
| Off-Exchange Yield | Asset | {4} | — | DA | At the start of your Market Close, if a Dark Pool Order triggered this turn, gain 3 Capital Reserve. |
| Rho Leverage Amplifier | Derivative | {3} | — | DA | Attach to a Trader: it gets +1/+1 for each Dark Pool Order that has triggered this game (maximum +4/+4). |
| Shadow Protocol Module | Derivative | {2} | — | DA | Attach to a Trader: Dark Pool Orders you stage while this Trader is on the field cost {1} less. |
| Off-Exchange Boost Rig | Derivative | {3} | — | DA | Attach to a Trader: when a Dark Pool Order triggers, this Trader gets +2/+0 until Market Close. |

---

### NEUTRAL — 3 cards

| Name | Type | Cost | P/T | Archetype | Rules Text |
|------|------|------|-----|-----------|-----------|
| Market Maker | Trader | {2} | 2/2 | N | When this enters, gain 1 Liquidity this turn. |
| Capital Injection | Strategy | {3} | — | N | Gain 5 Capital Reserve. |
| Book Building | Order | {2} | — | N | Draw 2 cards. Discard 1 card. |

---

**Total: 37 + 37 + 37 + 36 + 3 = 150 cards ✓**

---

## 5. Art Style Preamble

**STYLE_HEADLINE:** All FINA card art uses a PS1-era low-polygon aesthetic: chunky flat-shaded triangular geometry, hard jewel-tone fill colors with no texture mapping, visible polygon seams treated as design features. The overall feel is a Bloomberg terminal reimagined as a PlayStation 1 FMV cutscene — expensive geometry, over-lit luxury interiors, angular silhouettes that read as authoritative and dangerous. No gradients. No soft shadows. All depth is achieved through polygon count reduction, not shading. Gold foil rares are rendered as fields of gold flat-shaded triangles catching an overlit point source.

**CATEGORY_FLAVORS:**

- **trader:** Humanoid figures built from 150–400 polygons. Power Traders (Leverage 3+) have larger, more angular silhouettes. All Traders wear high-contrast business attire (charcoal polygon suit, sapphire polygon tie, gold polygon cufflinks) against a jewel-tone background (emerald green for standard, deep sapphire for rare, gold-panel for mythic). Background: flat-shaded open-plan trading floor with overlit fluorescent geometry.
- **order:** Abstract polygon compositions — geometric objects mid-transformation. Market Orders: sharp angular bursts of flat triangles. Dark Pool Orders: face-down polygon slabs with a single jewel-tone polygon glow at one edge.
- **strategy:** Wider scene — a boardroom of polygon figures or a trading floor viewed from above as a polygon grid. Deep emerald and gunmetal with gold accent triangles on rares.
- **asset:** Floating architectural or technological objects — a polygon server rack, flat-shaded monitor array, geometric golden vault door. Permanent and weighty; warm overlit background.
- **derivative:** Flat-polygon attachment frameworks — a shield, collar brace, or angular frame floating against a dark gradient-free background with small angular connective geometry radiating outward.
- **structure:** Large-polygon architectural pieces — trading floor terminal cluster, angular glass-and-steel polygon building facade, server room polygon landscape. Structural blues and cold greys, gold polygon outlines at corners for rares.

**Color palette:**
- background_primary: `#0B1A2E` (deep navy)
- background_secondary: `#0D2B1A` (jewel emerald)
- gold_foil: `#C8A84B`
- polygon_highlight: `#E8F4F8`
- leverage_counter: `#C8A84B` (gold)
- dark_pool_glow: `#3D1A7A` (dark purple)
- arbitrage_glow: `#1A7A3D` (emerald)
- cost_liquidity: `#4AB8E8` (cyan)
- capital_reserve: `#E84A4A` (red)

---

## 6. Set Code and Label Confirmation

```
Set code:   FINA
Set label:  fina
Set module: fina
```

**Deck labels (must start with FINA_):**
- `FINA_high_frequency`
- `FINA_derivatives`
- `FINA_quant`
- `FINA_dark_arbitrage`

---

## Pipeline Summary (appended post-build)

*To be filled by Stage 9.*
