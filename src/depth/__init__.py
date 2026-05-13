"""
Depth heuristic for Hyperdraft TCG cards.

Replaces the typography-based `card_depth()` formula (word count + clauses +
keyword set-membership) with a five-axis mechanical-depth rubric plus a
code-level AST fingerprint that detects literal reskins.

Entry points:
    src.depth.report.score_set(engine, set_code) -> SetReport
    src.depth.report.score_card(card_def, profile) -> CardReport

See `/Users/discordwell/.claude/plans/async-moseying-bear.md` for the design.
"""

from .ast_fingerprint import FeatureBag, extract_features_from_callable
from .axis_scorer import AxisScores, CardScore, score_card, score_features
from .engine_profiles import EngineProfile, get_profile, list_profiles

__all__ = [
    "FeatureBag",
    "extract_features_from_callable",
    "AxisScores",
    "CardScore",
    "score_card",
    "score_features",
    "EngineProfile",
    "get_profile",
    "list_profiles",
]
