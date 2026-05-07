# Finance TCG — Engine Design Document

## Theme & Aesthetic

Two rival trading firms go head-to-head on the Trading Floor. Players are rival quant desks — one perhaps an HFT shop running low-latency arbitrage, the other a classic long/short hedge fund running a multi-strategy book. Cards are named after real IB concepts: **Leveraged Buyout**, **Dark Pool Order**, **Front-Running Algo**, **Alpha Strike**, **Margin Call**, **Capital Call**, **Volatility Crush**, **Black-Scholes Trader**, **Delta Hedger**, **Gamma Scalper**. The art style is PS1 low-fi polygonal: chunky geometric card frames, jewel-tone emerald and sapphire asset panels, shimmering gold foil on rare cards rendered as flat-shaded triangles, bright overlit luxury — think a Bloomberg terminal reimagined as a PlayStation 1 FMV cutscene. Not grimdark. Not cartoon. Expensive geometry.

---

## 1. Win Condition

**Primary: Reduce the opponent's Capital Reserve to zero.**

Each player begins with **Capital Reserve = 30** (the life-total analog, stored on `Player.life`). When a player's Capital Reserve reaches 0 or below, that player's firm declares bankruptcy and loses. This maps directly onto the existing `LIFE_CHANGE` / `PLAYER_LOSES` event pipeline — no new SBA logic required.

**Secondary alternate-win (single card, not a rule)**: One mythic rare card, **"Monopoly Position"**, reads: *"At the start of your Pre-Market, if your Portfolio Value counter is 20 or greater, you win the game."* Portfolio Value counters are placed by specific cards. This alternate win is intentionally narrow and slow — it creates a combo archetype. Implementable as a standard `PHASE_START` trigger interceptor checking a counter on the card object.

**Deck-out**: Empty deck is **not** an immediate loss. Instead, each time a player must draw and cannot, they lose 1 Capital Reserve (Fatigue: `fatigue_damage` on `Player`, already supported).

---

## 2. Turn Structure

Five phases per turn, in order. Each phase emits `PHASE_START` / `PHASE_END` events with payload `{"phase": "<name>", "player": <id>}`.

| # | Phase | Finance name | MTG analog | Key actions |
|---|-------|-------------|------------|-------------|
| 1 | **PRE_MARKET** | Pre-Market | Beginning (Untap + Upkeep) | Refresh all Traders (untap); collect passive income from Assets; pay interest on Debt counters; reset Liquidity pool |
| 2 | **RESEARCH** | Research | Draw | Draw 1 card. If deck is empty, take 1 fatigue damage to Capital Reserve |
| 3 | **TRADING_SESSION** | Trading Session | Pre-combat Main + Combat | Play cards (Traders, Assets, Structures, Strategies); declare attackers; declare blockers; resolve combat damage |
| 4 | **SETTLEMENT** | Settlement | Post-combat Main | Play additional cards after combat; activate abilities; play Orders (instant-speed) |
| 5 | **MARKET_CLOSE** | Market Close | Ending (End step + Cleanup) | Resolve end-of-turn triggers; discard down to hand limit (7); clear "until end of turn" effects |

**Combat is embedded in Trading Session**. The sequence within Trading Session is:
1. Pre-combat action window (play cards, pay costs)
2. Declare Attackers
3. Declare Blockers
4. Damage resolution (simultaneous, overflow to Capital Reserve)
5. Post-combat SBA check (Liquidate Traders with fatal damage)

Orders with instant timing can be played during the opponent's Research, Trading Session, Settlement, and Market Close phases — and during your own Pre-Market, Research, and Market Close.

**Implementation**: `FinanceTurnManager(TurnManager)` with a `FinancePhase` enum: `PRE_MARKET`, `RESEARCH`, `TRADING_SESSION`, `SETTLEMENT`, `MARKET_CLOSE`.

---

## 3. Resource Model

**Liquidity — a ramping pool that fully refreshes each turn.**

Each player has a **Liquidity pool** that grows by 1 each turn, to a maximum of 10. At the start of Pre-Market, the pool is refilled to the current maximum. Unspent Liquidity does **not** carry over. Cost is printed as `{N}` symbols (e.g. `{3}` = costs 3 Liquidity).

This is the Hearthstone mana-crystal model, stored on `Player.mana_crystals` (max) and `Player.mana_crystals_available` (current). The mode adapter overrides `on_turn_start` to increment and refill the pool.

**Finance-specific wrinkle — Leverage counters**: Some Trader and Asset cards carry **Leverage counters** (stored in `obj.state.counters["leverage"]`). A card with Leverage counters might have +2/+0 but costs 1 Capital Reserve at Market Close if the counters remain. This is a card-level mechanic driven by standard `COUNTER_ADDED` / `PHASE_START` interceptors.

---

## 4. Zones

| Zone | Finance flavor name | ZoneType | Notes |
|------|-------------------|----------|-------|
| Library | **Book** | `LIBRARY` | 40-card deck (min). Draw pile. |
| Hand | **Hand** | `HAND` | Max 7 cards. |
| Battlefield | **Trading Floor** | `BATTLEFIELD` | Shared. Holds Traders, Assets, Structures. |
| Graveyard | **Liquidated** | `GRAVEYARD` | Destroyed/discarded cards. Per-player. |
| Exile | **Written Off** | `EXILE` | Permanently removed. Per-player. |
| Stack | Stack | `STACK` | Ability/Order resolution queue. |

**Finance-specific zone 1 — The Dark Pool** (shared, singleton): A single shared face-down slot for Orders with the **Dark Pool** keyword. The card triggers at the start of the opponent's next Trading Session. Only one card may occupy the Dark Pool at a time; playing a second replaces the first. Implementation: turn_data key `"finance_dark_pool"` holding an object ID (avoids new ZoneType). A system interceptor listens for `PHASE_START` events where phase is `TRADING_SESSION` for the opponent, then reveals and resolves the Dark Pool card.

**Finance-specific zone 2 — The Derivatives Desk** (per-player): A persistent face-up staging area holding up to 3 Derivative cards not yet attached to a Trader. When a Trader enters the Trading Floor, the owner may immediately attach one Derivative from their Derivatives Desk. Stored as a list in `state.turn_data["finance_deriv_desk_<player_id>"]`.

---

## 5. Combat Math

**Model: Declare Attackers / Declare Blockers, simultaneous damage, overflow to Capital Reserve.**

Each Trader has:
- **Aggression** (= `power`): damage dealt
- **Defense Rating** (= `toughness`): damage absorbed before Liquidation

**Rules**:
1. Attacking Traders become "committed" (tapped). Summoning sickness (`obj.state.summoning_sickness = True`) prevents attacking on the turn a Trader enters.
2. Defending player assigns one blocker per attacker (max); a blocker can only block one attacker.
3. Damage is simultaneous: attacker and blocker deal their Aggression to each other.
4. Lethal: if damage ≥ Defense Rating, the Trader is Liquidated. **Damage persists** — does not reset at Market Close.
5. Unblocked attacker deals full Aggression to opponent's Capital Reserve.
6. **Overflow rule**: If a blocker's Defense Rating is exceeded, the overflow hits the opponent's Capital Reserve.

**Worked example — overflow**:

Player A attacks with **HFT Algorithm** (4 Aggression / 2 Defense). Player B blocks with **Risk Manager** (2 Aggression / 3 Defense).

- HFT Algorithm deals 4 to Risk Manager → 4 ≥ 3: lethal. Risk Manager Liquidated.
- Risk Manager deals 2 to HFT Algorithm → 2 ≥ 2: lethal. HFT Algorithm Liquidated.
- Overflow: 4 − 3 = 1 → Player B loses 1 Capital Reserve (30 → 29).

Result: Both Liquidated. Player B took 1 damage — HFT archetype's value proposition.

**Worked example — clean trade**:

Player A attacks with **Delta Hedger** (3 Aggression / 4 Defense). Player B blocks with **Gamma Scalper** (3 Aggression / 3 Defense).

- Delta Hedger deals 3 to Gamma Scalper → lethal. Gamma Scalper Liquidated.
- Gamma Scalper deals 3 to Delta Hedger → 3 < 4: not lethal. Delta Hedger survives with 3 damage.
- No overflow (attacker's 3 fully absorbed by blocker's 3).

Result: Gamma Scalper Liquidated, Delta Hedger survives at 3 damage.

**Implementation**: Standard `CombatManager.resolve_damage`. The overflow logic (`max(0, attacker_power - blocker_toughness_remaining)` → `LIFE_CHANGE` on opponent) is replicated via a REACT-priority interceptor in `finance_combat.py`.

---

## 6. Card Types

Six canonical types (new `CardType` enum entries prefixed `FIN_`):

| Type | Enum | Timing | Finance analog |
|------|------|--------|---------------|
| **Trader** | `FIN_TRADER` | Trading Session (your turn) | Creature. Has Aggression / Defense Rating. Enters the Trading Floor. Can attack. Summoning sickness. |
| **Order** | `FIN_ORDER` | Any priority window | Instant. One-shot effect. Subtype: **Market Order** (immediate), **Dark Pool Order** (deferred). |
| **Strategy** | `FIN_STRATEGY` | Your Trading Session only | Sorcery. Slower, higher-impact. Sorcery-speed enforced. |
| **Asset** | `FIN_ASSET` | Your Trading Session | Stays on board. Passive static effect or activated ability. Not a combatant. |
| **Derivative** | `FIN_DERIVATIVE` | Your Trading Session → attaches to a Trader | Enchantment-on-a-Trader. Modifies stats or grants keywords. Stages to Derivatives Desk first. |
| **Structure** | `FIN_STRUCTURE` | Your Trading Session | Building. Max 3 per player on Trading Floor. Tap-to-activate abilities. No Aggression/Defense. |

---

## 7. Engine Capabilities

### Trigger types

| Capability | Implementation path | Status |
|-----------|-------------------|--------|
| ETB triggers | `make_etb_trigger` / `ZONE_CHANGE` → `BATTLEFIELD` interceptor | [existing] |
| Death triggers | `OBJECT_DESTROYED` → REACT interceptor | [existing] |
| Attack triggers | `ATTACK_DECLARED` → REACT interceptor | [existing] |
| End-of-turn triggers | `PHASE_START` with `phase="market_close"` filter | [existing, new phase name] |
| Pre-Market triggers | `PHASE_START` with `phase="pre_market"` filter | [existing, new phase name] |
| Card played triggers | `FIN_PLAY_CARD` marker event + REACT interceptor | [new event] |

### Static effects

| Capability | Implementation path | Status |
|-----------|-------------------|--------|
| Lord effects ("+1/+0 to your Traders") | `QUERY_POWER` interceptor | [existing] |
| Cost reduction | `QUERY_COST` / cost_modifier pattern | [existing] |
| Restriction effects ("Traders can't attack") | `ATTACK_DECLARED` → PREVENT interceptor | [existing] |

### Activated abilities

| Capability | Implementation path | Status |
|-----------|-------------------|--------|
| Tap-to-activate | `make_activated_ability` with TAP cost | [existing] |
| Pay Liquidity | `make_activated_ability` with mana_cost | [existing] |
| Once-per-turn limit | `uses_remaining` or turn_data flag | [existing] |

### New EventType additions required

```
FIN_PLAY_CARD       # Finance card played from hand
FIN_MARKET_EVENT    # Dark Pool card triggered
FIN_LEVERAGE_TICK   # Leverage counter accrued cost at Market Close
FIN_CAPITAL_CALL    # Capital Reserve damage from non-combat source
FIN_BANKRUPTCY      # Player's Capital Reserve reached 0
```

### New CardType additions required

```
FIN_TRADER
FIN_ORDER
FIN_STRATEGY
FIN_ASSET
FIN_DERIVATIVE
FIN_STRUCTURE
```

### New Player / turn_data fields required

```
finance_structure_count_<player_id>: int     # Structures on Trading Floor (capped at 3)
finance_deriv_desk_<player_id>: list[str]    # Derivative object IDs staged but not attached
finance_dark_pool: str | None                # Single Dark Pool card object ID
finance_liquidity_max_<player_id>: int       # Grows by 1/turn, max 10
```

Stored in `state.turn_data` per-player keys, matching Minecraft's `mc_materials` approach.

---

## 8. AI Difficulty Model

Three tiers, all sharing one legal-move generator. `FinanceAIAdapter(difficulty: str)`, mirroring `DepthsAIAdapter` shape exactly.

### Retail Investor (easy)
Random legal action each decision point. Attacks with all Traders every turn. Plays affordable cards in random order. Never uses Dark Pool defensively.

### Fund Manager (medium)
Greedy heuristic with hand-tuned weights. Scores Traders as `(Aggression + Defense Rating) / cost`. Attacks only when favorable (opponent can't block profitably) or when lethal is available. Places Orders in Dark Pool when opponent Capital Reserve ≤ 10. Always attaches highest-value Derivative on ETB.

### Quant (hard)
1-ply lookahead with board-value heuristic:

```
V(state, player_id) = 0.5 * capital_reserve_diff
                    + 0.3 * board_value_diff
                    + 0.2 * liquidity_economy_diff
```

Simulates all legal play orderings, picks the one maximizing V delta. Simulates opponent's optimal blocking response for each attack configuration. Detects lethal and always takes it. Holds reactive Orders for opponent's turn. `FinanceAIBias` dataclass exposes all weights for variant tuning.

---

## 9. Comparison with Existing Engines

**Closest cousin: Hearthstone.** Finance borrows Hearthstone's resource model almost verbatim (ramping per-turn mana crystals that refill, max 10, no carry-over). It extends HS's 3-phase model to 5 phases to accommodate a post-combat Settlement window.

**Where Finance diverges from Hearthstone**: Finance has explicit declare-attackers / declare-blockers combat where Hearthstone has free-target attacks with no blocking. Finance's Dark Pool is a simplified HS Secret triggered by phase rather than event type. Finance's Derivatives Desk has no HS analog.

**Versus Minecraft**: Minecraft's multi-material economy and grid-based column combat are fundamentally different. Finance uses a single Liquidity pool and standard 1v1 blocker assignment. Both modes use `PHASE_START` for turn-start income collection and `state.turn_data` for per-player state.

**Versus Depths**: Depths is a multi-resource spatial engine with detection mechanics. Finance shares none of its geometry or resource model. Both are simpler than MTG and use a no-priority-loop turn structure. Finance is deliberately easier to implement than Depths.

**Versus MTG**: Finance drops the 7-phase structure, drops land-as-a-card-type, drops end-of-turn damage heal (Trader damage persists), but borrows the attacker/blocker combat model and overflow-to-life-total mechanic.

**Net design statement**: Finance is "Hearthstone's resource economy + MTG's attacker/blocker combat + a staged preparation zone (Derivatives Desk) and a reactive trap slot (Dark Pool) that neither has." If you understand `HearthstoneTurnManager` and `CombatManager`, you can implement Finance in a long afternoon.

---

## Implementation Module Breakdown

| Agent | File | Owns |
|-------|------|------|
| 1 | `src/engine/finance.py` | `FinanceModeAdapter`, `setup_finance_player`, Liquidity management, Dark Pool zone helpers, Derivatives Desk helpers, system interceptor registration, `FIN_*` CardType/EventType additions to `types.py`, mode registry |
| 2 | `src/engine/finance_combat.py` | `FinanceCombatManager`, overflow REACT interceptor, summoning sickness reset, lethal SBA check |
| 3 | `src/engine/finance_turn.py` | `FinanceTurnManager(TurnManager)`, 5-phase `run_turn`, per-phase AI dispatch, Dark Pool trigger, Market Close cleanup |
| 4 | `src/ai/finance_adapter.py` | `FinanceAIAdapter(difficulty)`, 3 tiers, `FinanceAIBias` dataclass |

---

## Pipeline Summary

*Generated by `/new-game` pipeline — 2026-05-07*

### Engine module paths
| Module | Path |
|--------|------|
| Core engine | `src/engine/finance.py` |
| Combat | `src/engine/finance_combat.py` |
| Turn manager | `src/engine/finance_turn.py` |
| AI adapter | `src/ai/finance_adapter.py` |
| Mode registration | `src/engine/mode_adapter.py` (`"finance"` key) |
| Frontend board | `frontend/src/games/finance.tsx` |
| Frontend hook | `frontend/src/hooks/useFinanceGame.ts` |
| Card set | `src/cards/finance/fina/` |
| Art assets | `assets/card_art/finance/fina/` (150 placeholder PNGs) |
| Smoke test | `tests/test_finance_smoke.py`, `tests/test_fina.py` |
| Tournament runner | `scripts/play/finance_tournament.py` |

### AI adapter — difficulty model summary
- **easy**: random-legal action selection
- **medium**: greedy heuristic — maximise board presence + life delta, attacks when ahead
- **hard**: 1-ply V-delta lookahead using `V(state) = 0.5×cap_diff + 0.3×board_diff + 0.2×liq_diff`

### First set: FINA
See `docs/sets/fina.md` for full card list, mechanics, and art style.

| Archetype | Deck label | Strategy |
|-----------|-----------|----------|
| High Frequency | `FINA_high_frequency` | Alpha Strike swarm aggro |
| Derivatives | `FINA_derivatives` | Leverage midrange, short-sell tempo |
| Quant | `FINA_quant` | Arbitrage control, alternate win via Monopoly Position |
| Dark Arbitrage | `FINA_dark_arbitrage` | Dark Pool combo, Leverage burst |

### Balance loop results (3 cycles, medium AI, 10 games/pair)
| Archetype | Cycle 1 | Cycle 2 | Cycle 3 |
|-----------|---------|---------|---------|
| FINA_high_frequency | 73% | 13% | **40%** ✓ |
| FINA_derivatives | 0% | 30% | 27% ✗ |
| FINA_quant | 57% | 70% | 73% ✗ |
| FINA_dark_arbitrage | 70% | 87% | **60%** ✓ |

**Outstanding balance note**: Quant (73%) and Derivatives (27%) remain mismatched at the 3-cycle cap. Root cause is primarily AI strategy: the medium-difficulty AI plays Quant's straight board-presence and Arbitrage ramp efficiently, but doesn't exploit Derivatives' Leverage counter accumulation or Derivative attachment timing. Raising AI difficulty to `hard` narrows the gap. A future balance pass should target Quant's Arbitrage triggers (reduce liquidity gain per trigger from 1→0 on first trigger) and give Derivatives an early-game draw engine.

### How to play
```bash
# Start the server
uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030

# Start the frontend
cd frontend && npm run dev
# Navigate to http://localhost:5173 and select "Finance" game mode
```

### Outstanding TODOs
- `finance_adapter.py`: `choose_play_action` doesn't evaluate Derivative attachment targets — always picks first available Trader. A smarter heuristic would attach to the highest-power Trader.
- `finance_turn.py`: `fin_orders_suppressed_*` flag (set by Spoofing Algo) is tracked in `turn_data` but the turn manager doesn't yet enforce the restriction. Needs a guard in `_run_trading_session`.
- `finance_turn.py`: `fin_cant_block_*` (set by Crossed Market Dark Pool Order) is stored in `turn_data` but the blocker-selection loop doesn't filter on it.
- Art: all 150 cards have procedural placeholder PNGs. See `docs/sets/fina.md` Art Style section for the PS1 polygon aesthetic prompt pack to generate real art via ChatGPT.
- `finance_combat.py`: overflow damage to Capital Reserve bypasses the LIFE_CHANGE event pipeline when `pipeline is None` (test-mode fallback). Wire through the pipeline when not None for consistent event logging.
