"""Depths engine card pool — set 1: SUBS (submarine fleet)."""

from .submarine_fleet import SUBS_CARDS

# Aggregate of all depths-engine cards (currently just SUBS).
DEPTHS_CARDS: dict = {**SUBS_CARDS}

__all__ = ["DEPTHS_CARDS", "SUBS_CARDS"]
