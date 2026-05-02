"""Internal scoring data structures for staged MTG AI decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import LegalAction


@dataclass
class ActionScoreBreakdown:
    """Named score terms for one legal action."""

    strategy: float = 0.0
    fundamentals: float = 0.0
    reactive: float = 0.0
    x_spell: float = 0.0
    hold_mana_penalty: float = 0.0
    adventure: float = 0.0
    split: float = 0.0
    graveyard_activation: float = 0.0
    target_quality: float = 0.0
    board_delta: float = 0.0
    mana_posture: float = 0.0
    combat_outlook: float = 0.0
    layer: float = 0.0
    risk: float = 0.0
    random_delta: float = 0.0

    def total(self) -> float:
        return (
            self.strategy
            + self.fundamentals
            + self.reactive
            + self.x_spell
            - self.hold_mana_penalty
            + self.adventure
            + self.split
            + self.graveyard_activation
            + self.target_quality
            + self.board_delta
            + self.mana_posture
            + self.combat_outlook
            + self.layer
            + self.risk
            + self.random_delta
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "strategy": round(self.strategy, 4),
            "fundamentals": round(self.fundamentals, 4),
            "reactive": round(self.reactive, 4),
            "x_spell": round(self.x_spell, 4),
            "hold_mana_penalty": round(self.hold_mana_penalty, 4),
            "adventure": round(self.adventure, 4),
            "split": round(self.split, 4),
            "graveyard_activation": round(self.graveyard_activation, 4),
            "target_quality": round(self.target_quality, 4),
            "board_delta": round(self.board_delta, 4),
            "mana_posture": round(self.mana_posture, 4),
            "combat_outlook": round(self.combat_outlook, 4),
            "layer": round(self.layer, 4),
            "risk": round(self.risk, 4),
            "random_delta": round(self.random_delta, 4),
            "total": round(self.total(), 4),
        }


@dataclass
class ActionCandidateScore:
    """A legal action plus staged scoring metadata."""

    action: "LegalAction"
    bucket: str
    breakdown: ActionScoreBreakdown
    target_ids: list[str] = field(default_factory=list)
    kept_for_deep_score: bool = False
    keep_reason: str = ""

    @property
    def final_score(self) -> float:
        return self.breakdown.total()

    def to_trace(self, state: Any, selected: bool = False) -> dict[str, Any]:
        card = state.objects.get(self.action.card_id) if getattr(self.action, "card_id", None) else None
        source = state.objects.get(self.action.source_id) if getattr(self.action, "source_id", None) else None
        return {
            "action_type": self.action.type.name if hasattr(self.action.type, "name") else str(self.action.type),
            "card_id": getattr(self.action, "card_id", None),
            "card_name": getattr(card, "name", None),
            "source_id": getattr(self.action, "source_id", None),
            "source_name": getattr(source, "name", None),
            "ability_id": getattr(self.action, "ability_id", None),
            "bucket": self.bucket,
            "score": round(self.final_score, 4),
            "breakdown": self.breakdown.to_dict(),
            "target_ids": list(self.target_ids),
            "kept_for_deep_score": self.kept_for_deep_score,
            "keep_reason": self.keep_reason,
            "selected": selected,
        }
