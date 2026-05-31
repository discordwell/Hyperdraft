"""Balance-regression guard for scp2 (Phase 4).

run_tournament is deterministic (fixed per-game seeds), so this is stable, not flaky. It
guards the Phase-4 result — a healthy Foundation/Insurgency split with all win paths live —
against future AI/card/constant changes silently re-breaking balance (the 0%/100% bug this
phase fixed). When you intentionally rebalance, update the band here to match.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp2_balance.py -q
"""

import pytest

from scripts.play.scp2_tournament import run_tournament, summarize

GAMES_PER_PAIRING = 12  # 4 pairings → 48 games; deterministic seeds


@pytest.fixture(scope="module")
def summary():
    return summarize(run_tournament(games=GAMES_PER_PAIRING))


def test_no_stalls_and_every_game_has_a_winner(summary):
    assert summary["stalls"] == 0, "some games never resolved (AI can't close)"
    decided = summary["faction"].get("Foundation", 0) + summary["faction"].get("Insurgency", 0)
    assert decided == summary["games"], f"undecided games: {summary['faction']}"


def test_neither_faction_dominates(summary):
    f = summary["foundation_winrate"]
    assert 35.0 <= f <= 65.0, (
        f"faction balance regressed: Foundation {f}% / Insurgency {summary['insurgency_winrate']}% "
        f"(reasons={summary['reasons']})")


def test_both_win_axes_are_reachable(summary):
    reasons = summary["reasons"]
    assert reasons.get("containment", 0) > 0, "Foundation never wins by containment"
    insurgency_wins = reasons.get("liberation", 0) + reasons.get("total_breach", 0)
    assert insurgency_wins > 0, "Insurgency never wins by liberation or breach"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
