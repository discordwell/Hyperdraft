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
    """Called once after ``SCP_CARDS`` is built. Mechanic modules register here.

    Order matters for text composition: reveal-identity sets baseline rules
    text first, then test_dividends and contained_auras append their clauses.
    Personnel synergy edits a disjoint family (personnel cards only) so its
    order is independent.
    """
    from .contained_auras import apply_contained_auras
    from .personnel_quirks import apply_personnel_quirks
    from .personnel_synergy import apply_personnel_synergy
    from .reveal_identity import apply_reveal_identity
    from .test_dividends import apply_test_dividends

    apply_reveal_identity(cards)
    apply_test_dividends(cards)
    apply_contained_auras(cards)
    apply_personnel_synergy(cards)
    # personnel_quirks runs AFTER personnel_synergy so its text-append clauses
    # land on top of synergy's aura sentences (Janitor / Memory Triage share).
    apply_personnel_quirks(cards)
