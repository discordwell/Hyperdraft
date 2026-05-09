"""
FinanceStack — bounded MTG-style priority stack for FINA spells.

Only Orders and Strategies push to the stack; permanents (Traders,
Derivatives, Assets, Structures) bypass it and resolve immediately.
Counterspells (Information Ratio Enforcer, Execution Glitch, Regime
Change Detection) call ``mark_countered`` on the targeted stack item;
when the resolver pops a countered item, it skips the resolve_fn and
sends the card straight to the graveyard.

The stack is owned by FinanceTurnManager (``self.fin_stack``) and
mirrored on GameState (``state.fin_stack``) so card resolve_fns can
reach it without holding a turn-manager reference.

Resolution semantics:
- LIFO: items pop top-down
- A countered item still moves to the graveyard, but its effect_fn
  is skipped and a FIN_CARD_COUNTERED event is emitted instead of
  FIN_CARD_RESOLVED.
- The stack is always empty at turn boundaries (every cast resolves
  within one priority loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class FinanceStackItem:
    """A single cast on the FINA stack."""

    card_id: str
    controller: str
    targets: list[list[str]] = field(default_factory=list)
    resolve_fn: Optional[Callable[[Any, Any], list[Any]]] = None
    is_response: bool = False
    countered: bool = False
    cost_paid: int = 0


@dataclass
class FinanceStack:
    """LIFO stack of FinanceStackItems."""

    items: list[FinanceStackItem] = field(default_factory=list)

    def push(self, item: FinanceStackItem) -> None:
        self.items.append(item)

    def pop(self) -> Optional[FinanceStackItem]:
        if not self.items:
            return None
        return self.items.pop()

    def peek(self) -> Optional[FinanceStackItem]:
        if not self.items:
            return None
        return self.items[-1]

    def find(self, card_id: str) -> Optional[FinanceStackItem]:
        for item in self.items:
            if item.card_id == card_id:
                return item
        return None

    def mark_countered(self, card_id: str) -> bool:
        """Mark the named stack item countered. Returns True if found."""
        item = self.find(card_id)
        if item is None:
            return False
        item.countered = True
        return True

    def is_empty(self) -> bool:
        return not self.items

    def depth(self) -> int:
        return len(self.items)

    def clear(self) -> None:
        self.items.clear()
