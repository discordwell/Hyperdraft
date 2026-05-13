"""Post-construction mechanic appliers for the SCP card pool.

Each module under this package exposes ``apply_<mechanic>(cards)`` that walks
the card dict and mutates relevant entries. The five planned modules:

- ``reveal_identity`` — wires ``scp_on_reveal`` for bare anomalies (mood
  seeding, sealed defaults, public-leak, paperwork interference).
- ``contained_auras`` — wires ``scp_contained_bonus`` for selected anomalies.
- ``test_dividends`` — wires ``scp_on_test`` / ``scp_on_test_fail`` for
  research-flavored anomalies.
- ``personnel_synergy`` — wires ``scp_aura`` for skill-stick personnel.
- ``expansion_defaults`` — adjusts the templated ``_build_expansion_cards``
  output (touches generator post-hoc rather than at build time).

Each module owns exactly one attribute family, so they are merge-safe to
develop in parallel worktrees.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.types import CardDefinition


def apply_all_mechanics(cards: "dict[str, CardDefinition]") -> None:
    """Called once after ``SCP_CARDS`` is built. Mechanic modules register here."""
    from .contained_auras import apply_contained_auras
    from .test_dividends import apply_test_dividends

    apply_contained_auras(cards)
    apply_test_dividends(cards)
