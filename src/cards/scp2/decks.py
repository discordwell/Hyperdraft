"""SCP: SECURE / CONTAIN / SUBVERT — starter decks (2 archetypes per faction).

Four 40-card pinnacle decks built from the scp2 pool. Each Foundation deck satisfies the
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
becomes the 40-card library. Decks are validated by tests/test_scp2_cards.py.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType
from src.cards.scp2 import foundation as F
from src.cards.scp2 import insurgency as I

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
        if getattr(cd, "scp2_kind", None) == CardType.SCP2_ANOMALY and not getattr(cd, "scp2_trap", False):
            total += int(getattr(cd, "scp2_value", 0) or 0)
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
        # Operations — 6
        (F.EMERGENCY_LOCKDOWN, 2), (F.MANDATORY_AUDIT, 2),
        (F.AMNESTICS, 1), (F.REDACTION_ORDER, 1),
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
        # Operations — 6 (soft-kill payoff)
        (F.REDACTION_ORDER, 2), (F.AMNESTICS, 2),
        (F.EMERGENCY_LOCKDOWN, 1), (F.MANDATORY_AUDIT, 1),
    )


# ===========================================================================
# Insurgency A — "Black Queen Cell" (criminal tempo)
# ===========================================================================
def black_queen_cell() -> list[CardDefinition]:
    # Focused steal-tempo pinnacle: wins purely by liberation (no breach events). Deep breaker
    # suite to crack kill-walls, econ to fund repeated runs, Sabotage to mill the Foundation's
    # containment. The Black Queen Cell identity banks +1 Liberation per free on top.
    return _deck(
        # Operatives — 14 (deep breaker suite, sentry-heavy to beat the kill deck)
        (I.INFILTRATOR, 3), (I.MASTER_INFILTRATOR, 2),
        (I.SABOTEUR, 3), (I.VETERAN_SABOTEUR, 2),
        (I.GHOST, 2), (I.GHOST_IN_THE_MACHINE, 2),
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
# Registries — label → (identity, deck-builder). Both Foundation decks share the
# Site-19 Command identity; both Insurgency decks share Black Queen Cell (one
# identity per faction in v0.1, per rules §11).
# ===========================================================================
SCP2_FOUNDATION_DECKS = {
    "SCP2_site19_containment": (F.SITE_19_COMMAND, site19_containment),
    "SCP2_blackfile_bait": (F.SITE_19_COMMAND, blackfile_bait),
}
SCP2_INSURGENCY_DECKS = {
    "SCP2_black_queen_cell": (I.BLACK_QUEEN_CELL, black_queen_cell),
    "SCP2_containment_breach": (I.BLACK_QUEEN_CELL, containment_breach),
}
SCP2_DECKS = {**SCP2_FOUNDATION_DECKS, **SCP2_INSURGENCY_DECKS}
