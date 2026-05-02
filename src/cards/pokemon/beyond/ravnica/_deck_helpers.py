"""Shared deck-construction helpers for Beyond Ravnica guild decks.

The "modern competitive" trainer suite — modeled on the search/draw density
of real Scarlet & Violet-era decks. Without this density the AI's evolution
chains never come online and games end at turn 7-8 (vs 10-12 for proper
games), suppressing prize-trade dynamics.
"""

from __future__ import annotations


def standard_trainer_suite():
    """Return the 22-card sv_starter trainer suite shared by every guild deck.

    Composition:
      Search:    4 Nest Ball, 3 Ultra Ball, 2 Rare Candy
      Mobility:  2 Switch
      Utility:   1 Potion, 1 Super Rod
      Draw:      4 Professor's Research, 1 Judge
      Disrupt:   2 Iono
      Gust:      2 Boss's Orders
    """
    from src.cards.pokemon.sv_starter import (
        NEST_BALL, ULTRA_BALL, RARE_CANDY, SWITCH, POTION, SUPER_ROD,
        PROFESSOR_RESEARCH, IONO, BOSS_ORDERS, JUDGE,
    )
    deck = []
    deck.extend([NEST_BALL] * 4)
    deck.extend([ULTRA_BALL] * 3)
    deck.extend([RARE_CANDY] * 2)
    deck.extend([SWITCH] * 2)
    deck.extend([POTION] * 1)
    deck.extend([SUPER_ROD] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 4)
    deck.extend([IONO] * 2)
    deck.extend([BOSS_ORDERS] * 2)
    deck.extend([JUDGE] * 1)
    return deck
