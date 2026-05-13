"""MNR mandate sub-set.

8 mandates across three archetypes:

- **Memory Hole** (3 cards) — alt-win wired to ``memory_hole`` (3 opposing
  forgotten + secrecy 10+). Different bonus tasks differentiate the build
  the mandate is steering.
- **Mnestic Saturation** (3 cards) — alt-win wired to ``mnestic_saturation``
  (5 active+unexhausted Mnestic personnel AND archives >= 4). Card-side
  payoff is biased toward personnel-heavy decks.
- **Public Inquiry** (2 cards) — alt-win wired to ``public_panic``
  (archives >= 4 AND any opponent at secrecy <= 6). Standard SZB Masquerade
  shell with Mnestic-flavored text.

All mandates use ``_mnr_card`` so MNR metadata + art prompts stamp without
extra ceremony.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType

from .helpers import _mnr_card


# ---------------------------------------------------------------------------
# Memory Hole (3) — alt_win="memory_hole"
# ---------------------------------------------------------------------------


def _build_memory_hole_mandate() -> CardDefinition:
    """Sample card preserved verbatim — referenced by tests/test_scp_tcg.py."""
    card = _mnr_card(
        "MNR Mandate 1: Memory Hole",
        CardType.SCP_MANDATE,
        red_tape=1,
        subtypes={"Mandate", "Antimemetic"},
        text=(
            "Mandate. If 3 or more opposing anomalies are forgotten and your "
            "secrecy is 10 or greater, you win the game."
        ),
        rarity="mythic",
        archetype="mnestic_reset",
    )
    card.scp_alt_win = "memory_hole"
    return card


_MEMORY_HOLE_MANDATE = _build_memory_hole_mandate()


# Total Erasure — bigger research engine while you chase Memory Hole.
def _build_total_erasure() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 2: Total Erasure",
        CardType.SCP_MANDATE,
        red_tape=2,
        subtypes={"Mandate", "Antimemetic"},
        text=(
            "Mandate. Research +1. If 3 or more opposing anomalies are "
            "forgotten and your secrecy is 10 or greater, you win the game. "
            "Erase the record. Erase the records of the erasure."
        ),
        rarity="rare",
        archetype="mnestic_reset",
        bonus={"research": 1},
    )
    card.scp_alt_win = "memory_hole"
    return card


_TOTAL_ERASURE = _build_total_erasure()


# Selective Forgetting — suppression-leaning Memory Hole shell.
def _build_selective_forgetting() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 3: Selective Forgetting",
        CardType.SCP_MANDATE,
        red_tape=2,
        subtypes={"Mandate", "Antimemetic"},
        text=(
            "Mandate. Suppress +1. If 3 or more opposing anomalies are "
            "forgotten and your secrecy is 10 or greater, you win the game. "
            "What you don't remember can't testify against you."
        ),
        rarity="rare",
        archetype="mnestic_reset",
        bonus={"suppress": 1},
    )
    card.scp_alt_win = "memory_hole"
    return card


_SELECTIVE_FORGETTING = _build_selective_forgetting()


# ---------------------------------------------------------------------------
# Mnestic Saturation (3) — alt_win="mnestic_saturation"
# ---------------------------------------------------------------------------


# Mnestic Saturation flagship — research bonus encourages Mnestic researchers.
def _build_mnestic_saturation() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 4: Mnestic Saturation",
        CardType.SCP_MANDATE,
        red_tape=2,
        clearance=1,
        subtypes={"Mandate", "Mnestic"},
        text=(
            "Mandate. Research +1. If you control 5 or more active "
            "unexhausted Mnestic personnel and have 4 or more archives, "
            "you win the game. The signal beneath the static is the staff."
        ),
        rarity="mythic",
        archetype="mnestic_reset",
        bonus={"research": 1},
    )
    card.scp_alt_win = "mnestic_saturation"
    return card


_MNESTIC_SATURATION = _build_mnestic_saturation()


# Inoculation Mandate — containment-leaning Mnestic Saturation.
def _build_inoculation_mandate() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 5: Inoculation Mandate",
        CardType.SCP_MANDATE,
        red_tape=2,
        subtypes={"Mandate", "Mnestic"},
        text=(
            "Mandate. Contain +1. If you control 5 or more active "
            "unexhausted Mnestic personnel and have 4 or more archives, "
            "you win the game. Everyone above clearance 1 gets the pill."
        ),
        rarity="rare",
        archetype="mnestic_reset",
        bonus={"contain": 1},
    )
    card.scp_alt_win = "mnestic_saturation"
    return card


_INOCULATION_MANDATE = _build_inoculation_mandate()


# Memory Reform — suppression-leaning Mnestic Saturation; cheaper RT.
def _build_memory_reform() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 6: Memory Reform",
        CardType.SCP_MANDATE,
        red_tape=2,
        subtypes={"Mandate", "Mnestic"},
        text=(
            "Mandate. Suppress +1. If you control 5 or more active "
            "unexhausted Mnestic personnel and have 4 or more archives, "
            "you win the game. Quietly restore what was quietly removed."
        ),
        rarity="rare",
        archetype="mnestic_reset",
        bonus={"suppress": 1},
    )
    card.scp_alt_win = "mnestic_saturation"
    return card


_MEMORY_REFORM = _build_memory_reform()


# ---------------------------------------------------------------------------
# Public Inquiry (2) — alt_win="public_panic"
# ---------------------------------------------------------------------------


# Public Disclosure — research-leaning Public Inquiry.
def _build_public_disclosure() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 7: Public Disclosure",
        CardType.SCP_MANDATE,
        red_tape=1,
        subtypes={"Mandate", "Masquerade"},
        text=(
            "Mandate. Research +1. If you have 4 or more archives and an "
            "opponent's secrecy is 6 or lower, you win the game. The "
            "newsroom got hold of three pages they were not supposed to."
        ),
        rarity="rare",
        archetype="mnestic_reset",
        bonus={"research": 1},
    )
    card.scp_alt_win = "public_panic"
    return card


_PUBLIC_DISCLOSURE = _build_public_disclosure()


# Cold-Open Inquiry — suppression-leaning Public Inquiry.
def _build_cold_open_inquiry() -> CardDefinition:
    card = _mnr_card(
        "MNR Mandate 8: Cold-Open Inquiry",
        CardType.SCP_MANDATE,
        red_tape=1,
        subtypes={"Mandate", "Masquerade"},
        text=(
            "Mandate. Suppress +1. If you have 4 or more archives and an "
            "opponent's secrecy is 6 or lower, you win the game. Start "
            "with the cover-up; everyone will infer the rest."
        ),
        rarity="rare",
        archetype="mnestic_reset",
        bonus={"suppress": 1},
    )
    card.scp_alt_win = "public_panic"
    return card


_COLD_OPEN_INQUIRY = _build_cold_open_inquiry()


# ---------------------------------------------------------------------------
# Final assembly. Card-design agents: 3 Memory Hole + 3 Mnestic Saturation
# + 2 Public Inquiry = 8 mandates.
# ---------------------------------------------------------------------------


MANDATES: list[CardDefinition] = [
    _MEMORY_HOLE_MANDATE,
    _TOTAL_ERASURE,
    _SELECTIVE_FORGETTING,
    _MNESTIC_SATURATION,
    _INOCULATION_MANDATE,
    _MEMORY_REFORM,
    _PUBLIC_DISCLOSURE,
    _COLD_OPEN_INQUIRY,
]
