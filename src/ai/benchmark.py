"""Small fixed-seed benchmark wrapper for MTG AI traces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import random
from typing import Optional

from .tracing import AITraceRecorder


@dataclass
class AIBenchmarkRun:
    """Owns trace artifacts for one deterministic AI benchmark run."""

    name: str
    seed: int
    recorder: AITraceRecorder
    summary_path: Optional[Path] = None

    @classmethod
    def create(
        cls,
        name: str,
        seed: int,
        output_dir: str | Path,
        jsonl_name: str = "decisions.jsonl",
        summary_name: str = "summary.json",
    ) -> "AIBenchmarkRun":
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        random.seed(seed)
        return cls(
            name=name,
            seed=seed,
            recorder=AITraceRecorder(out / jsonl_name),
            summary_path=out / summary_name,
        )

    def attach(self, ai_engine) -> None:
        ai_engine.set_trace_recorder(self.recorder)

    def finish(self) -> dict:
        summary = self.recorder.summary()
        summary.update({
            "benchmark_name": self.name,
            "seed": self.seed,
        })
        if self.summary_path:
            self.summary_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return summary
