"""
FINA Starter Decks — four 40-card decks, one per archetype.

Archetypes:
  FINA_high_frequency  — aggro: cheap Alpha Strike Traders + Dark Pool tempo
  FINA_derivatives     — midrange: Leverage counters + Short Selling + Derivatives
  FINA_quant           — control: Arbitrage Liquidity engine + passive Assets
  FINA_dark_arbitrage  — combo: Dark Pool trap wall → giant Leverage/Arbitrage finisher
"""

from src.engine.types import CardDefinition


# =============================================================================
# HIGH-FREQUENCY — Aggro (40 cards)
# =============================================================================
# Loop: deploy cheap Alpha Strike Traders T1-3 → Dark Pool Orders clear blockers
#       → swing alone for +3/+0 or +4/+0 lethal.
# Curve: heavy at {1}-{2}, a few {3} payoffs, light top-end.

def build_high_frequency_deck() -> list[CardDefinition]:
    from src.cards.finance.fina import FINA_CARDS

    def c(name: str, n: int = 1) -> list[CardDefinition]:
        return [FINA_CARDS[name]] * n

    deck: list[CardDefinition] = []

    # --- {1} Traders (8) ---     8
    deck += c("Flash Crash Bot", 4)        # 2/1 Alpha Strike + ETB gain 1 Liq
    deck += c("Retail Flow Chaser", 4)     # 1/1 Alpha Strike vanilla

    # --- {2} Traders (6) ---     14
    deck += c("Spoofing Algo", 3)          # 2/1 Alpha Strike + locks out Orders
    deck += c("Front-Running Algo", 3)     # 2/1 Alpha Strike + draw on face damage

    # --- {3} Traders (4) ---     18
    deck += c("Latency Arbitrageur", 2)    # 3/1 Alpha Strike + bonus damage
    deck += c("Fill-or-Kill Executor", 2)  # 3/2 Alpha Strike + gain 2 Liq unblocked

    # --- {4} Trader (2) ---      20
    deck += c("Bandwidth Predator", 2)     # 3/3 Alpha Strike + freeze blocker

    # --- {1} Orders (4) ---      24
    deck += c("Dark Pool Flash Order", 4)  # DP: deal 2 to target Trader

    # --- {2} Orders (4) ---      28
    deck += c("Quote Stuffing Burst", 2)   # +3/+0 + Alpha Strike grant
    deck += c("Sub-Penny Intercept", 2)    # -2/-0 to attacking Trader

    # --- {2} Assets (4) ---      32
    deck += c("HFT Feed Colocation", 2)    # static +1/+0 to Alpha Strike Traders
    deck += c("Tick Data Archive", 2)      # pre-market draw if attacked alone

    # --- {2} Strategies (2) ---  34
    deck += c("Low-Latency Strike", 2)     # remove sickness from all Alpha Strikers

    # --- {3} Strategies (2) ---  36
    deck += c("Momentum Ignition", 2)      # mass attack + +2/+0 all Alpha Strike

    # --- {3} Asset (1) ---       37
    deck += c("Direct Market Access", 1)   # static: Alpha Strike bonus → +4/+0

    # --- {2} Derivatives (3) ---  40
    deck += c("Ticker Tape Derivative", 2) # attach: grant Alpha Strike
    deck += c("Speed Amplifier", 1)        # attach: +2/+0 + draw on solo attack

    assert len(deck) == 40, f"HF deck: {len(deck)}"
    return deck


# =============================================================================
# DERIVATIVES — Midrange (40 cards)
# =============================================================================
# Loop: play Leverage Traders → pump with Vega Spike/Gamma Hedge → Short Sell
#       to reset damage and return with +1/+1 counters → repeat for dominant threat.
# Curve: 1-drop enabler, 2-3 drop Leverage core, 4-5 finishers.

def build_derivatives_deck() -> list[CardDefinition]:
    from src.cards.finance.fina import FINA_CARDS

    def c(name: str, n: int = 1) -> list[CardDefinition]:
        return [FINA_CARDS[name]] * n

    deck: list[CardDefinition] = []

    # --- {1} Trader (3) ---      3
    deck += c("Options Desk Intern", 3)            # 1/2 attach free Derivative on ETB

    # --- {2} Traders (6) ---     9
    deck += c("Underlying Asset Runner", 4)        # 2/2 Leverage 1 vanilla body
    deck += c("Exposure Manager", 2)               # 1/3 Leverage 1 + Liq on counter removal

    # --- {3} Traders (6) ---     15
    deck += c("Delta Hedger", 2)                   # 2/4 Leverage 2 damage reduction
    deck += c("Rho Opportunist", 2)                # 3/2 Leverage 1 draw on counter add
    deck += c("Theta Decay Trader", 2)             # 2/3 Leverage 2 free tick removal

    # --- {4} Traders (4) ---     19
    deck += c("Vega Amplifier", 2)                 # 4/3 Leverage 3 +1/+0 to all Leverage
    deck += c("Gamma Scalper", 2)                  # 3/3 Leverage 3 once-per-game bailout

    # --- {5} Trader (1) ---      20
    deck += c("Hedge Fund PM", 1)                  # 4/4 Leverage 2 attach whole Desk

    # --- {2} Strategies (4) ---  24
    deck += c("Short Squeeze", 4)                  # exile then return +2 counters

    # --- {3} Strategies (3) ---  27
    deck += c("Vega Spike", 2)                     # +2 Leverage counters on a Trader
    deck += c("Carry Trade", 1)                    # gain Liq per Leverage counter (max 5)

    # --- {2} Orders (4) ---      31
    deck += c("Gamma Hedge", 2)                    # +1/+1 per Leverage counter until EOT
    deck += c("Cover Short", 2)                    # instant-return exiled Trader

    # --- {3} Assets (2) ---      33
    deck += c("The Black-Scholes Model", 2)        # pre-market: pay 1 Liq remove counter

    # --- {3} Structure (1) ---   34
    deck += c("Derivatives Desk Console", 1)       # pre-market draw if Derivative on Desk

    # --- {2} Derivatives (4) ---  38
    deck += c("Theta Decay Collar", 2)             # attach +1/+2 + free tick remove
    deck += c("Protective Put", 2)                 # attach indestructible-once shield

    # --- {3} Derivatives (2) ---  40
    deck += c("Gamma Amplifier", 1)                # attach +2/+1 + 0-cost tick once
    deck += c("Synthetic Collar", 1)               # attach +1/+1 per Derivative attached

    assert len(deck) == 40, f"DV deck: {len(deck)}"
    return deck


# =============================================================================
# QUANT — Control (40 cards)
# =============================================================================
# Loop: establish board majority → Arbitrage fires each ETB → surplus Liquidity
#       fuels draw engines → out-value opponent; Monopoly Position alternate win.
# Curve: low-cost defensive Traders, mid Assets/Structures, top-end value bombs.

def build_quant_deck() -> list[CardDefinition]:
    from src.cards.finance.fina import FINA_CARDS

    def c(name: str, n: int = 1) -> list[CardDefinition]:
        return [FINA_CARDS[name]] * n

    deck: list[CardDefinition] = []

    # --- {1} Trader (4) ---      4
    deck += c("Statistical Arb Clerk", 4)          # 1/2 Arbitrage 1 cheap blocker

    # --- {2} Traders (6) ---     10
    deck += c("Factor Model Analyst", 2)           # 1/3 Arb 1 + draw on trigger
    deck += c("Risk Manager", 3)                   # 1/4 Arb 1 + self-heal blocker
    deck += c("Market Maker", 1)                   # 2/2 neutral: ETB gain 1 Liq

    # --- {3} Traders (6) ---     16
    deck += c("Pairs Trader", 3)                   # 2/3 Arbitrage 2
    deck += c("Correlation Trader", 2)             # 2/4 Arb 1 + static +0/+1 lord
    deck += c("Mean Reversion Bot", 1)             # 1/4 pre-market self-repair

    # --- {4} Traders (3) ---     19
    deck += c("Portfolio Construction Desk", 2)    # 3/4 Arb 2 + global +0/+1
    deck += c("Drawdown Controller", 1)            # 2/5 ETB remove damage

    # --- {7} Trader (1) ---      20
    deck += c("Monopoly Position", 1)              # 3/5 alternate-win Portfolio counters

    # --- {1} Order (2) ---       22
    deck += c("Quant Signal", 2)                   # look top 3, keep 1

    # --- {2} Orders (5) ---      27
    deck += c("Rebalancing Halt", 2)               # tap + draw a card
    deck += c("Liquidity Provision", 3)            # gain 3 Liquidity this turn

    # --- {2} Assets (4) ---      31
    deck += c("Portfolio Diversifier", 2)          # Liq max +1
    deck += c("Sharpe Ratio Monitor", 2)           # pre-market: gain 1 Liq if leading

    # --- {3} Assets (3) ---      34
    deck += c("Systematic Alpha Engine", 2)        # pre-market: gain 2 Liq if leading
    deck += c("Risk Attribution Model", 1)         # static +0/+1 to 4+ Defense Traders

    # --- {3} Structures (2) ---  36
    deck += c("Quant Lab", 2)                      # pre-market: gain 2 Liq if leading

    # --- {3} Strategy (1) ---    37
    deck += c("Information Advantage", 1)          # draw 2 (or 3 if leading)

    # --- {4} Strategy (1) ---    38
    deck += c("Correlation Matrix", 1)             # draw cards = Trader lead (max 4)

    # --- {2} Derivative (2) ---  40
    deck += c("Signal Processing Rig", 2)          # attach: gain Arbitrage 1 + self-heal

    assert len(deck) == 40, f"QT deck: {len(deck)}"
    return deck


# =============================================================================
# DARK ARBITRAGE — Combo (40 cards)
# =============================================================================
# Loop: turns 1-4 stage Dark Pool Orders defensively → suppress board → T5
#       drop Dark Pool Aggressor or OTC Behemoth → Arbitrage refuels →
#       Alpha Strike alone for lethal with Hidden Aggression boost.
# Curve: {1}-{2} Dark Pool setup, {3}-{4} board presence, {5}-{6} finishers.

def build_dark_arbitrage_deck() -> list[CardDefinition]:
    from src.cards.finance.fina import FINA_CARDS

    def c(name: str, n: int = 1) -> list[CardDefinition]:
        return [FINA_CARDS[name]] * n

    deck: list[CardDefinition] = []

    # --- {2} Traders (8) ---     8
    deck += c("Hidden Accumulator", 4)             # 2/2 +1/+1 whenever DP played
    deck += c("Dark Inventory Position", 4)        # 2/3 ETB tutor a DP Order

    # --- {3} Traders (4) ---     12
    deck += c("Stealth Position Builder", 2)       # 2/4 draw when DP triggers
    deck += c("Off-Exchange Operative", 2)         # 3/3 Leverage 1 Arbitrage 1

    # --- {4} Traders (4) ---     16
    deck += c("Institutional Block Trader", 2)     # 3/4 Leverage 2 Arb 1 + 2 Liq ETB
    deck += c("Dark Pool Architect", 2)            # 4/4 Leverage 2 Arb 2 + free DP play

    # --- {5} Traders (3) ---     19
    deck += c("Dark Pool Aggressor", 2)            # 4/4 Leverage 3 Arb 2 Alpha Strike
    deck += c("Off-Exchange Finisher", 1)          # 5/4 Leverage 2 Arb 2 +4/+0 Alpha

    # --- {6} Trader (1) ---      20
    deck += c("OTC Behemoth", 1)                   # 5/5 Leverage 3 Arb 2 + lock Orders

    # --- {1} Orders (4) ---      24
    deck += c("Iceberg Order", 2)                  # DP: deal 1 + draw
    deck += c("Lit-Market Decoy", 2)               # draw + free DP play this turn

    # --- {2} Orders (8) ---      32
    deck += c("Off-Exchange Position", 2)          # DP: -3/-0 to target Trader
    deck += c("Crossed Market", 2)                 # DP: target Trader can't block
    deck += c("Hidden Aggression", 2)              # DP: +4/+0 to friendly Trader
    deck += c("Payment for Order Flow", 2)         # DP: gain 3 Liquidity

    # --- {3} Orders (2) ---      34
    deck += c("Block Trade Sweep", 2)              # DP: destroy ≤3 Defense Trader

    # --- {3} Assets (2) ---      36
    deck += c("Dark Flow Engine", 2)               # static DP Orders cost {1} less

    # --- {4} Structures (2) ---  38
    deck += c("Principal Trading Desk", 1)         # pre-market draw if DP slot empty
    deck += c("Dark Venue Console", 1)             # pay {1} to trigger staged DP now

    # --- {4} Strategy (1) ---    39
    deck += c("Liquidity Event", 1)                # gain Liq = # DP played (max 5)

    # --- {2} Derivative (1) ---  40
    deck += c("Shadow Protocol Module", 1)         # attach: DP staged cost {1} less

    assert len(deck) == 40, f"DA deck: {len(deck)}"
    return deck


# =============================================================================
# Deck registry — keys MUST start with FINA_ for the balance loop filter
# =============================================================================

FINA_STARTER_DECKS: dict[str, object] = {
    "FINA_high_frequency": build_high_frequency_deck,
    "FINA_derivatives": build_derivatives_deck,
    "FINA_quant": build_quant_deck,
    "FINA_dark_arbitrage": build_dark_arbitrage_deck,
}


# =============================================================================
# Module-level validation
# =============================================================================

if __name__ == "__main__":
    for name, builder in FINA_STARTER_DECKS.items():
        deck = builder()
        assert len(deck) == 40, f"{name} deck has {len(deck)} cards, expected 40"
    print(f"All FINA starter decks validated ({len(FINA_STARTER_DECKS)} decks, 40 cards each)")
