# FINX Voltron Premium Deck Tech

## Pick

Final deck: `FINX_voltron_premium`

This is a FINA Hedge Fund PM Derivatives shell with a small FINM splash:
`All-In Control Premium` replaces weaker FINA Derivative flex slots as the
cleanest two-mana power attachment. The deck's main plan is to build a large
Derivative-backed Trader, then use Hedge Fund PM to mass-attach and close before
FINM value decks can turn repeated Coupon/Hedge triggers into inevitability.

## Decklist

- 4 Hedge Fund PM
- 4 Structured Product Builder
- 4 Underlying Asset Runner
- 3 Protective Put
- 2 Theta Decay Trader
- 2 Synthetic Collar
- 2 Theta Decay Collar
- 2 Gamma Amplifier
- 2 Iron Condor
- 2 All-In Control Premium
- 2 Position Audit
- 2 Forced Liquidation
- 2 The Black-Scholes Model
- 2 Liquidity Provision
- 1 Delta Hedger
- 1 Delta Neutral Wrap
- 1 Cover Short
- 1 Derivatives Desk Console
- 1 Short Squeeze

## Candidate Results

| Run | Field | Best relevant result |
| --- | --- | --- |
| `logs/finance_finm_opt_pass1.json` | broad first-pass hybrids + top starters, 1 game/pair | `FINX_voltron_credit_coupon` led hybrids at 75.0%; pure FINM All-In/Risk were ahead. |
| `logs/finance_finm_opt_pass2.json` | narrowed splashes + top starters, 2 games/pair | `FINX_voltron_premium` led at 85.0%. |
| `logs/finance_finm_opt_pass3.json` | broad finalists, 4 games/pair | `FINX_voltron_premium` led at 66.7% over 48 games. |
| `logs/finance_finm_opt_finals.json` | short-list finals, 10 games/pair | `FINX_risk_bomb_plus` led the narrow anti-meta table at 62.0%; `FINX_voltron_premium` was 54.0%. |
| `logs/finance_finm_opt_pass4.json` | broad finalists, 8 games/pair | `FINX_voltron_premium` led at 66.7% over 96 games. |

Pass 4 matchup notes for `FINX_voltron_premium`: 75.0% vs `FINX_risk_bomb_plus`,
62.5% vs FINM All-In, 62.5% vs FINM Risk, 62.5% vs FINM Treasury, 75.0% vs
FINM Credit, 87.5% vs FINA Dark Arbitrage, and 50.0% vs `FINX_big_lever_coupon`.

## Card Choices

- `Hedge Fund PM` is still the strongest FINA payoff because it converts the
Derivative desk into immediate battlefield power.
- `Structured Product Builder`, `Underlying Asset Runner`, and `Theta Decay
Trader` provide the best early bodies while keeping leverage tax manageable.
- `All-In Control Premium` is the FINM upgrade: it is a cheap +2/+0 attachment
that improves the clock without increasing leverage exposure.
- `Protective Put`, `Theta Decay Collar`, `Gamma Amplifier`, `Synthetic Collar`,
and `Iron Condor` keep the voltron threat large enough to force bad blocks.
- `Position Audit` and `Forced Liquidation` hedge against opposing attachment
or single-threat mirrors.

## Weaknesses

- FINM Treasury and Hedge can still beat it when they establish enough high
toughness Coupon/Hedge bodies before the PM turn.
- `FINX_big_lever_coupon` split the pass-4 matchup 50.0%, so the deck is not
strictly dominant against every FINA leverage shell.
- The results are medium-AI tournament results. Hard-AI and human play may value
draw, removal, and attachment timing differently.
