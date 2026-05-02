"""
Structured tracing for MTG AI decisions.

The recorder is intentionally small and dependency-free so tests, scripts, and
AI-vs-AI harnesses can opt in without changing the public game engine surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from pathlib import Path
from typing import Any, Optional


SCHEMA_VERSION = "hyperdraft.ai.decision.v1"


def _jsonable(value: Any) -> Any:
    """Convert common engine values into JSON-serializable primitives."""
    if isinstance(value, Enum):
        return value.name
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "id") and hasattr(value, "name"):
        return {"id": getattr(value, "id", None), "name": getattr(value, "name", None)}
    return value


@dataclass
class DecisionTraceEvent:
    """Machine-readable record for one AI decision point."""

    decision_type: str
    player_id: str
    turn: int = 0
    phase: str = ""
    duration_ms: float = 0.0
    legal_count: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    selected: dict[str, Any] = field(default_factory=dict)
    selected_targets: list[Any] = field(default_factory=list)
    board: dict[str, Any] = field(default_factory=dict)
    ultra: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable({
            "schema_version": SCHEMA_VERSION,
            "decision_type": self.decision_type,
            "player_id": self.player_id,
            "turn": self.turn,
            "phase": self.phase,
            "duration_ms": round(self.duration_ms, 3),
            "legal_count": self.legal_count,
            "candidates": self.candidates,
            "selected": self.selected,
            "selected_targets": self.selected_targets,
            "board": self.board,
            "ultra": self.ultra,
            "metadata": self.metadata,
            "timestamp_ns": self.timestamp_ns,
        })


class AITraceRecorder:
    """
    Collects AI decision traces and optionally mirrors them to JSONL.

    `events` are retained in memory for tests and local summaries. Long-running
    benchmark jobs should pass `jsonl_path` and call `clear()` between suites if
    they do not need all events resident.
    """

    def __init__(self, jsonl_path: Optional[str | Path] = None):
        self.jsonl_path = Path(jsonl_path) if jsonl_path else None
        self.events: list[dict[str, Any]] = []
        if self.jsonl_path:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            self.jsonl_path.write_text("")

    def record(self, event: DecisionTraceEvent | dict[str, Any]) -> dict[str, Any]:
        data = event.to_dict() if isinstance(event, DecisionTraceEvent) else _jsonable(event)
        data.setdefault("schema_version", SCHEMA_VERSION)
        self.events.append(data)
        if self.jsonl_path:
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(data, sort_keys=True) + "\n")
        return data

    def clear(self) -> None:
        self.events.clear()
        if self.jsonl_path:
            self.jsonl_path.write_text("")

    def summary(self) -> dict[str, Any]:
        durations = [float(e.get("duration_ms", 0.0) or 0.0) for e in self.events]
        sorted_durations = sorted(durations)
        p95 = 0.0
        if sorted_durations:
            idx = min(len(sorted_durations) - 1, int(len(sorted_durations) * 0.95))
            p95 = sorted_durations[idx]

        action_mix: dict[str, int] = {}
        fallback_count = 0
        cache_hits = 0
        cache_misses = 0
        missed_lethal = 0
        bad_trades = 0
        target_checks = 0
        target_hits = 0

        for event in self.events:
            selected = event.get("selected") or {}
            action_type = str(selected.get("action_type") or event.get("decision_type") or "unknown")
            action_mix[action_type] = action_mix.get(action_type, 0) + 1

            ultra = event.get("ultra") or {}
            if ultra.get("fallback_used"):
                fallback_count += 1
            if ultra.get("cache_hit"):
                cache_hits += 1
            if ultra.get("cache_miss"):
                cache_misses += 1

            metadata = event.get("metadata") or {}
            missed_lethal += int(bool(metadata.get("missed_lethal")))
            bad_trades += int(bool(metadata.get("bad_trade")))
            if "target_correct" in metadata:
                target_checks += 1
                target_hits += int(bool(metadata.get("target_correct")))

        return {
            "schema_version": "hyperdraft.ai.benchmark_summary.v1",
            "decision_count": len(self.events),
            "avg_decision_ms": round(sum(durations) / len(durations), 3) if durations else 0.0,
            "p95_decision_ms": round(p95, 3),
            "action_mix": action_mix,
            "missed_lethal_count": missed_lethal,
            "bad_trade_count": bad_trades,
            "target_accuracy": round(target_hits / target_checks, 3) if target_checks else None,
            "fallback_rate": round(fallback_count / len(self.events), 3) if self.events else 0.0,
            "cache_hit_rate": round(cache_hits / (cache_hits + cache_misses), 3)
            if (cache_hits + cache_misses) else 0.0,
        }

    def write_summary(self, path: str | Path) -> dict[str, Any]:
        summary = self.summary()
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary


def board_trace_summary(state: Any, player_id: str, analysis: Any = None) -> dict[str, Any]:
    """Return a compact board summary for trace payloads."""
    player = getattr(state, "players", {}).get(player_id)
    opponent_id = None
    for pid in getattr(state, "players", {}):
        if pid != player_id:
            opponent_id = pid
            break
    opponent = getattr(state, "players", {}).get(opponent_id) if opponent_id else None

    data = {
        "player_life": getattr(player, "life", None),
        "opponent_id": opponent_id,
        "opponent_life": getattr(opponent, "life", None),
    }
    if analysis is not None:
        data.update({
            "life_score": getattr(analysis, "life_score", 0.0),
            "board_score": getattr(analysis, "board_score", 0.0),
            "card_advantage": getattr(analysis, "card_advantage", 0.0),
            "mana_advantage": getattr(analysis, "mana_advantage", 0.0),
            "threat_score": getattr(analysis, "threat_score", 0.0),
            "blocker_score": getattr(analysis, "blocker_score", 0.0),
            "evasion_pressure": getattr(analysis, "evasion_pressure", 0.0),
            "crack_back_risk": getattr(analysis, "crack_back_risk", 0.0),
            "permanent_score": getattr(analysis, "permanent_score", 0.0),
            "total_score": getattr(analysis, "total_score", 0.0),
            "role": getattr(analysis, "role", ""),
        })
    return data
