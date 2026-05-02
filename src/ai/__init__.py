"""
Hyperdraft AI System

A modular AI system for playing MTG-style games.
Supports multiple strategies (aggro, control, midrange, ultra) and difficulty levels.

Strategy Layers:
- Hard AI uses programmatic layer scoring
- Ultra AI uses LLM-guided decisions with full layer context
"""

from .engine import AIEngine
from .evaluator import BoardEvaluator
from .heuristics import Heuristics
from .benchmark import AIBenchmarkRun
from .tracing import AITraceRecorder, DecisionTraceEvent
from .reactive import ReactiveEvaluator, ReactiveContext, StackThreatAssessment, CombatCreatureInfo
from .strategies import AIStrategy, AggroStrategy, ControlStrategy, MidrangeStrategy, UltraStrategy

# LLM and Layers modules available for advanced usage
from . import llm
from . import layers

__all__ = [
    # Core
    'AIEngine',
    'BoardEvaluator',
    'Heuristics',
    'AIBenchmarkRun',
    'AITraceRecorder',
    'DecisionTraceEvent',
    # Reactive
    'ReactiveEvaluator',
    'ReactiveContext',
    'StackThreatAssessment',
    'CombatCreatureInfo',
    # Strategies
    'AIStrategy',
    'AggroStrategy',
    'ControlStrategy',
    'MidrangeStrategy',
    'UltraStrategy',
    # Submodules
    'llm',
    'layers',
]
