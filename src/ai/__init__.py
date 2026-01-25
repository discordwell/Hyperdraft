"""
Hyperdraft AI System

A modular AI system for playing MTG-style games.
Supports multiple strategies (aggro, control, midrange) and difficulty levels.
"""

from .engine import AIEngine
from .evaluator import BoardEvaluator
from .heuristics import Heuristics
from .reactive import ReactiveEvaluator, ReactiveContext, StackThreatAssessment, CombatCreatureInfo
from .strategies import AIStrategy, AggroStrategy, ControlStrategy, MidrangeStrategy

__all__ = [
    'AIEngine',
    'BoardEvaluator',
    'Heuristics',
    'ReactiveEvaluator',
    'ReactiveContext',
    'StackThreatAssessment',
    'CombatCreatureInfo',
    'AIStrategy',
    'AggroStrategy',
    'ControlStrategy',
    'MidrangeStrategy',
]
