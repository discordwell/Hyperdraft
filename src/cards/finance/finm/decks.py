"""FINM starter decks for Market Meltdown.

Each deck is 40 cards and exercises one of the expansion's mechanics. These
are tournament seed decks, not final solved lists.
"""

from __future__ import annotations

from src.engine.types import CardDefinition


def _cards(names: list[tuple[str, int]]) -> list[CardDefinition]:
    from src.cards.finance.finm import FINM_CARDS

    deck: list[CardDefinition] = []
    for name, count in names:
        deck.extend([FINM_CARDS[name]] * count)
    assert len(deck) == 40, f"FINM deck has {len(deck)} cards"
    return deck


def build_credit_covenant_deck() -> list[CardDefinition]:
    return _cards([
        ("Covenant Analyst", 4), ("Covenant Associate", 4), ("Covenant Specialist", 3),
        ("Covenant Director", 3), ("Covenant Partner", 2), ("Covenant Architect", 2),
        ("Covenant Standstill", 3), ("Covenant Rescue Facility", 2), ("Covenant Debtor-in-Possession Loan", 2),
        ("Covenant Cramdown", 1), ("Covenant Indenture Archive", 2), ("Covenant Collateral Trustee", 2),
        ("Covenant Seniority Ladder", 2), ("Covenant Priming Lien", 3),
        ("Covenant Make-Whole Warrant", 2), ("Covenant Lien Search", 3),
    ])


def build_treasury_coupon_deck() -> list[CardDefinition]:
    return _cards([
        ("Coupon Analyst", 2), ("Coupon Associate", 3), ("Coupon Specialist", 3),
        ("Coupon Director", 3), ("Coupon Partner", 2), ("Coupon Architect", 2),
        ("Coupon Treasury Bill", 3), ("Coupon Cash Sweep", 3), ("Coupon Bond Ladder", 2),
        ("Coupon Repo Window", 2), ("Coupon Reserve Drain", 2), ("Coupon Bill Vault", 3),
        ("Coupon Funding Desk", 2), ("Coupon Carry Warehouse", 3), ("Coupon Duration Sleeve", 3),
        ("Coupon Central Bank Swap Line", 1), ("Coupon Treasury Futures Pit", 1),
    ])


def build_risk_hedge_deck() -> list[CardDefinition]:
    return _cards([
        ("Hedge Analyst", 2), ("Hedge Associate", 3), ("Hedge Specialist", 3),
        ("Hedge Director", 3), ("Hedge Partner", 2), ("Hedge Architect", 2),
        ("Hedge Stop Loss", 3), ("Hedge Variance Cap", 2), ("Hedge Tail Event Map", 2),
        ("Hedge VaR Breach", 2), ("Hedge Stress Scenario", 2), ("Hedge Risk Dashboard", 2),
        ("Hedge Control Room", 2), ("Hedge Put Spread", 2), ("Hedge Tail Hedge Sleeve", 2),
        ("Hedge Capital Buffer", 2), ("Hedge Catastrophe Bond", 2),
        ("Hedge Limit Check", 2),
    ])


def build_activist_all_in_deck() -> list[CardDefinition]:
    return _cards([
        ("All-In Analyst", 1), ("All-In Associate", 2), ("All-In Specialist", 3),
        ("All-In Director", 3), ("All-In Partner", 2), ("All-In Architect", 2),
        ("All-In Tender Offer", 2), ("All-In Proxy Fight", 1), ("All-In Board Seat", 2),
        ("All-In Hostile Bid", 1), ("All-In Dawn Raid", 1), ("All-In Proxy Advisor", 2),
        ("All-In War Room", 1), ("All-In Voting Trust", 2), ("All-In Control Premium", 2), ("All-In Schedule 13D", 3),
        ("All-In White Knight Search", 3), ("All-In Settlement Agreement", 3),
        ("All-In Poison Pill Wrap", 2), ("All-In Control Bloc", 2),
    ])


def build_distressed_restructure_deck() -> list[CardDefinition]:
    return _cards([
        ("Restructure Analyst", 2), ("Restructure Associate", 3), ("Restructure Specialist", 3),
        ("Restructure Director", 3), ("Restructure Partner", 2), ("Restructure Architect", 2),
        ("Restructure Fire Sale", 3), ("Restructure Asset Strip", 2), ("Restructure Debtor Rollup", 2),
        ("Restructure Liquidation Trust", 1), ("Restructure Workout Desk", 1),
        ("Restructure Claims Register", 2), ("Restructure Auction Block", 2),
        ("Restructure Claims Warrant", 3), ("Restructure Claim Diligence", 3),
        ("Restructure Plan Sponsor", 3), ("Restructure Fulcrum Security", 2),
        ("Restructure Bankruptcy Courtroom", 1),
    ])


def build_ma_buyback_deck() -> list[CardDefinition]:
    return _cards([
        ("Buyback Analyst", 2), ("Buyback Associate", 3), ("Buyback Specialist", 3),
        ("Buyback Director", 3), ("Buyback Partner", 2), ("Buyback Architect", 2),
        ("Buyback Term Sheet", 3), ("Buyback Fairness Opinion", 2), ("Buyback Merger Model", 2),
        ("Buyback Synergy Capture", 1), ("Buyback Breakup Fee", 2), ("Buyback Data Room", 2),
        ("Buyback Integration Office", 2), ("Buyback Earnout Clause", 2), ("Buyback Due Diligence", 2),
        ("Buyback Closing Dinner", 3), ("Buyback Board Approval Room", 2),
        ("Buyback Roll-Up Platform", 2),
    ])


FINM_STARTER_DECKS = {
    "FINM_credit_covenant": build_credit_covenant_deck,
    "FINM_treasury_coupon": build_treasury_coupon_deck,
    "FINM_risk_hedge": build_risk_hedge_deck,
    "FINM_activist_all_in": build_activist_all_in_deck,
    "FINM_distressed_restructure": build_distressed_restructure_deck,
    "FINM_ma_buyback": build_ma_buyback_deck,
}


__all__ = [
    "FINM_STARTER_DECKS",
    "build_credit_covenant_deck",
    "build_treasury_coupon_deck",
    "build_risk_hedge_deck",
    "build_activist_all_in_deck",
    "build_distressed_restructure_deck",
    "build_ma_buyback_deck",
]
