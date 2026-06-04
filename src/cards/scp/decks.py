"""SCP: SECURE / CONTAIN / SUBVERT — starter decks (2 archetypes per faction).

Four 40-card pinnacle decks built from the scp pool. Each Foundation deck satisfies the
anomaly-density rule (≥ 18 Containment points of *real* anomalies — traps don't count, per
spec §2), so it can always draw a win-con. Two archetypes per side keeps the Phase-4
balance matrix honest:

  Foundation A — "Site-19 Containment"  : glacier build; dense anomalies, tall walls,
                                          Funding engine. Out-defends the run.
  Foundation B — "Black-File Bait"      : trap/kill; decoys + Sentry walls + expose/trash.
                                          Pursues the soft-kill (burnout) axis.
  Insurgency A — "Black Queen Cell"     : criminal tempo; cheap breakers + econ, steals
                                          anomalies efficiently for Liberation.
  Insurgency B — "Containment Breach"   : breach-rush; floods the shared Total Breach clock
                                          (Leak/Wetwork + freeing) for the secondary win.

Each deck is (identity, list[CardDefinition]); the identity is installed at setup, the list
becomes the 40-card library. Decks are validated by tests/test_scp_cards.py.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType
from src.cards.scp import foundation as F
from src.cards.scp import insurgency as I

DECK_SIZE = 40
MIN_ANOMALY_DENSITY = 18  # spec §2: ≥18 Containment points of real anomalies per Foundation deck


def _deck(*pairs: tuple[CardDefinition, int]) -> list[CardDefinition]:
    """Expand (card, count) pairs into a flat deck list. Sharing a CardDefinition across
    copies is safe — per-object state lives on the GameObject, not the template."""
    out: list[CardDefinition] = []
    for card, count in pairs:
        out.extend([card] * count)
    return out


def anomaly_density(deck: list[CardDefinition]) -> int:
    """Sum of Value across non-trap anomalies — the deck's guaranteed containment ceiling."""
    total = 0
    for cd in deck:
        if getattr(cd, "scp_kind", None) == CardType.SCP_ANOMALY and not getattr(cd, "scp_trap", False):
            total += int(getattr(cd, "scp_value", 0) or 0)
    return total


# ===========================================================================
# Foundation A — "Site-19 Containment" (glacier build)
# ===========================================================================
def site19_containment() -> list[CardDefinition]:
    return _deck(
        # Anomalies — 12 cards, 22 Containment points
        (F.SENTIENT_LOCKBOX, 2), (F.SEALED_VAULT, 2),
        (F.ANOMALOUS_SPECIMEN, 3), (F.EUCLID_SUBJECT, 2), (F.REALITY_BENDER, 1),
        (F.CONTAINMENT_LEVIATHAN, 1), (F.WORLDSPINE_WURM, 1),
        # Layers — 16 cards (tall walls)
        (F.BLAST_DOOR, 4), (F.REINFORCED_BULKHEAD, 2), (F.CONTAINMENT_FIELD, 2),
        (F.RESPONSE_TEAM, 3), (F.KILL_ON_SIGHT, 1),
        (F.SURVEILLANCE_GRID, 3), (F.AMNESTIC_MIST, 1),
        # Assets — 6 (Funding engine)
        (F.CONTAINMENT_BUDGET, 3), (F.BLACK_SITE_FUNDING, 1),
        (F.SITE_DIRECTOR, 1), (F.MOBILE_TASK_FORCE, 1),
        # Operations — 6 (Containment Sweep ×2 is the answer to the breach clock)
        (F.EMERGENCY_LOCKDOWN, 1), (F.MANDATORY_AUDIT, 2),
        (F.CONTAINMENT_SWEEP, 2), (F.REDACTION_ORDER, 1),
    )


# ===========================================================================
# Foundation B — "Black-File Bait" (trap / soft-kill)
# ===========================================================================
def blackfile_bait() -> list[CardDefinition]:
    return _deck(
        # Anomalies — 14 cards: 10 real (19 pts) + 4 traps
        (F.SENTIENT_LOCKBOX, 2), (F.ANOMALOUS_SPECIMEN, 3),
        (F.EUCLID_SUBJECT, 2), (F.MEMETIC_ARCHIVE, 2), (F.KETER_HORROR, 1),
        (F.RELIQUARY_OF_BAD_IDEAS, 2), (F.CEREBRAL_RELAY, 1), (F.HONEYPOT_CELL, 1),
        # Layers — 14 cards (Sentry-heavy kill walls + tag sensors)
        (F.RESPONSE_TEAM, 3), (F.KILL_ON_SIGHT, 2), (F.SNIPER_NEST, 2),
        (F.SURVEILLANCE_GRID, 3), (F.TRIPWIRE, 2), (F.BLAST_DOOR, 2),
        # Assets — 6
        (F.CONTAINMENT_BUDGET, 2), (F.BLACK_SITE_FUNDING, 2),
        (F.MOBILE_TASK_FORCE, 1), (F.SITE_DIRECTOR, 1),
        # Operations — 6 (soft-kill payoff: tag with Redaction, burst with Interrogation; Audit for
        # card flow; Containment Sweep ×1 so the bait deck isn't helpless against the breach clock)
        (F.REDACTION_ORDER, 2), (F.MANDATORY_AUDIT, 1),
        (F.ENHANCED_INTERROGATION, 2), (F.CONTAINMENT_SWEEP, 1),
    )


# ===========================================================================
# Insurgency A — "Black Queen Cell" (criminal tempo)
# ===========================================================================
def black_queen_cell() -> list[CardDefinition]:
    # Focused steal-tempo pinnacle: wins purely by liberation (no breach events). Deep breaker
    # suite to crack kill-walls, econ to fund repeated runs, Sabotage to mill the Foundation's
    # containment. The Black Queen Cell identity banks +1 Liberation per free on top.
    return _deck(
        # Operatives — 14 (deep breaker suite, Sentry-heavy to survive the kill deck's neutralize
        # walls; Veteran Saboteur is the load-bearing anti-Sentry tech — power 3, boost 1 — while a
        # Ghost trims out since smart-break now eats Sensor tags rather than paying to break them)
        (I.INFILTRATOR, 3), (I.MASTER_INFILTRATOR, 2),
        (I.SABOTEUR, 3), (I.VETERAN_SABOTEUR, 3),
        (I.GHOST, 2), (I.GHOST_IN_THE_MACHINE, 1),
        # Tools — 9 (econ to fund the runs)
        (I.BLACK_BUDGET, 3), (I.STOLEN_CREDENTIALS, 3), (I.SAFEHOUSE, 3),
        # Events — 17: econ/draw/mill core + a small breach REACH package (3) so a kill deck
        # that walls us out of stealing can't grind the game to a stall.
        (I.BLACK_MARKET, 4), (I.COORDINATED_STRIKE, 2), (I.EXTRACTION, 3),
        (I.DATA_HEIST, 3), (I.SABOTAGE, 2),
        (I.LEAK_TO_THE_PRESS, 2), (I.WETWORK, 1),
    )


# ===========================================================================
# Insurgency B — "Containment Breach" (breach-rush)
# ===========================================================================
def containment_breach() -> list[CardDefinition]:
    return _deck(
        # Operatives — 10 (enough to break in; freeing feeds breach)
        (I.INFILTRATOR, 3), (I.MASTER_INFILTRATOR, 2),
        (I.SABOTEUR, 2), (I.VETERAN_SABOTEUR, 1), (I.GHOST, 2),
        # Tools — 8 (econ to afford the rush)
        (I.BLACK_BUDGET, 3), (I.STOLEN_CREDENTIALS, 3), (I.SAFEHOUSE, 2),
        # Events — 22 (breach-heavy)
        (I.LEAK_TO_THE_PRESS, 3), (I.WETWORK, 3), (I.ANONYMOUS_TIP, 3),
        (I.BLACK_MARKET, 3), (I.COORDINATED_STRIKE, 2),
        (I.EXTRACTION, 3), (I.SABOTAGE, 3), (I.DATA_HEIST, 2),
    )


# ===========================================================================
# Insurgency C — "Black Lodge" (denial / mill → Foundation collapse)
# ===========================================================================
def black_lodge_cell() -> list[CardDefinition]:
    # The third Insurgency archetype: doesn't race liberation or breach — it DESTROYS the
    # Foundation's containment supply (mill their deck, free what's on the board) until they can no
    # longer reach Containment 6 and lose by *collapse* (engine check_scp_win). The Black Lodge Cell
    # identity trashes +1 per mill. A small breach package keeps it from being walled into a stall.
    return _deck(
        # Operatives — 10 (enough to free on-board anomalies + crack the occasional wall)
        (I.INFILTRATOR, 3), (I.MASTER_INFILTRATOR, 2),
        (I.SABOTEUR, 2), (I.VETERAN_SABOTEUR, 1), (I.GHOST, 2),
        # Tools — 8 (econ to fund mill events + runs)
        (I.BLACK_BUDGET, 3), (I.STOLEN_CREDENTIALS, 3), (I.SAFEHOUSE, 2),
        # Events — 22: heavy mill core (Sabotage/Data Heist) + draw/econ + a 5-card breach reach
        (I.SABOTAGE, 4), (I.DATA_HEIST, 3),
        (I.EXTRACTION, 4), (I.BLACK_MARKET, 4), (I.COORDINATED_STRIKE, 2),
        (I.LEAK_TO_THE_PRESS, 2), (I.ANONYMOUS_TIP, 2), (I.WETWORK, 1),
    )


# ===========================================================================
# Registries — label → (identity, deck-builder). Each archetype now runs its OWN
# win-condition-aligned identity: the glacier build keeps Site-19 Command (card
# flow); the bait/kill deck takes Overseer Council (soft-kill damage +1 vs an
# exposed Insurgency); the steal deck keeps Black Queen Cell (+1 Liberation/free);
# the breach-rush deck takes Sarkic Cult (breach events +1) instead of borrowing
# Black Queen's liberation engine it never used.
# ===========================================================================
SCP_FOUNDATION_DECKS = {
    "SCP_site19_containment": (F.SITE_19_COMMAND, site19_containment),
    "SCP_blackfile_bait": (F.OVERSEER_COUNCIL, blackfile_bait),
}
SCP_INSURGENCY_DECKS = {
    "SCP_black_queen_cell": (I.BLACK_QUEEN_CELL, black_queen_cell),
    "SCP_containment_breach": (I.SARKIC_CULT, containment_breach),
    "SCP_black_lodge_cell": (I.BLACK_LODGE_CELL, black_lodge_cell),
}
SCP_DECKS = {**SCP_FOUNDATION_DECKS, **SCP_INSURGENCY_DECKS}
