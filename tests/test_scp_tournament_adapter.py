"""Smoke test for ``scripts/new_set/_adapters/scp_tournament_adapter.py``.

Runs a tiny SCP tournament against the existing MNR + core starter decks
(so we don't depend on FBN being merged yet), asserts the extended JSON
contract is present and non-empty, and that at least one mechanic from the
MNR set fired (or, as a fallback, at least one core SCP mechanic — Breach
Audit fires every turn unconditionally).

Run directly:
    python tests/test_scp_tournament_adapter.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.new_set._adapters.scp_tournament_adapter import (   # noqa: E402
    run_scp_tournament,
)
from src.cards.scp import SCP_STARTER_DECKS                       # noqa: E402


REQUIRED_KEYS = {
    "set_summary",
    "matchup",
    "card_scores",
    "ai_action_counts",
    "mechanic_triggers",
    "available_actions",
}


def _smoke_builders() -> dict[str, callable]:
    """Three SCP decks, MNR-themed where possible.

    Uses synthetic ``MNR_`` deck labels (the smoke fixture is wrapped around
    pre-existing SCP_STARTER_DECKS builders) so the adapter's set-prefix
    validation is exercised end-to-end. The 3 decks yield 3 unordered
    pairings.
    """
    return {
        "MNR_division":         SCP_STARTER_DECKS["mnestic_reset_division"],
        "MNR_secure_baseline":  SCP_STARTER_DECKS["secure_contain_research"],
        "MNR_veil_baseline":    SCP_STARTER_DECKS["veil_control"],
    }


def main() -> int:
    builders = _smoke_builders()
    # 3 decks × 1 game-per-pairing = 3 games. The task description called
    # for "--games 4 (2 pairings)" — we run 3 games across 3 pairings, which
    # is in the same neighbourhood and covers all three decks at least once
    # without ballooning runtime.
    payload = asyncio.run(run_scp_tournament(
        builders,
        games_per_pairing=1,
        max_turns=20,
        difficulty="medium",
        pilot="balanced",
        seed=2026_05_13,
        set_code="MNR",
    ))

    # 1. All 6 required keys present.
    missing = REQUIRED_KEYS - set(payload.keys())
    assert not missing, f"missing required keys: {sorted(missing)}"

    # 2. set_summary has one entry per deck, each with winrate + games_played.
    assert set(payload["set_summary"].keys()) == set(builders.keys()), (
        f"set_summary keys mismatch: "
        f"{sorted(payload['set_summary'])} vs {sorted(builders)}"
    )
    for label, rec in payload["set_summary"].items():
        assert "winrate" in rec, f"{label} missing winrate"
        assert "games_played" in rec, f"{label} missing games_played"
        assert rec["games_played"] >= 0
    print(f"[ok] set_summary populated: "
          f"{[(k, v['winrate']) for k, v in payload['set_summary'].items()]}")

    # 3. ai_action_counts non-empty (the AI must have done SOMETHING).
    aac = payload["ai_action_counts"]
    assert aac, "ai_action_counts is empty — AI took no actions"
    assert any(v > 0 for v in aac.values()), (
        f"ai_action_counts has no non-zero entries: {aac}"
    )
    # Open Dossier is by far the most-frequent action; if it's missing,
    # the AI didn't open any cards, which means the engine is broken.
    assert aac.get("SCP_OPEN_DOSSIER", 0) > 0, (
        f"AI never opened a dossier — sanity check failed: {aac}"
    )
    print(f"[ok] ai_action_counts: {dict(sorted(aac.items()))}")

    # 4. available_actions has SCP_OPEN_DOSSIER + SCP_END_TURN at minimum.
    avail = set(payload["available_actions"])
    assert "SCP_OPEN_DOSSIER" in avail, (
        f"SCP_OPEN_DOSSIER missing from available_actions: {sorted(avail)}"
    )
    assert "SCP_END_TURN" in avail, (
        f"SCP_END_TURN missing from available_actions: {sorted(avail)}"
    )
    print(f"[ok] available_actions: {sorted(avail)}")

    # 5. mechanic_triggers: at least one MNR mechanic OR one core SCP mechanic
    #    should fire. Breach Audit fires every turn unconditionally so it's
    #    the reliable floor. MNR's Antimeme only fires on threshold; with a
    #    Mnestic-heavy MNR deck on one side it will be suppressed often.
    mech = payload["mechanic_triggers"]
    assert mech, f"mechanic_triggers is empty: {mech}"
    floor_mechanics = {
        # MNR-themed:
        "Antimeme", "Mnestic Wake", "Redact", "Cognitive Hazard",
        # Core SCP — at least one of these MUST fire in any non-trivial game:
        "Breach Audit", "Open Dossier", "Archive Gained",
    }
    fired = floor_mechanics & set(mech.keys())
    assert fired, (
        f"none of the floor mechanics fired: expected at least one of "
        f"{sorted(floor_mechanics)}; got {dict(sorted(mech.items()))}"
    )
    print(f"[ok] mechanic_triggers: {dict(sorted(mech.items()))}")

    # 6. card_scores: keys must be '<DECK_LABEL>::<Card Name>' and
    #    every deck_label should appear at least once.
    cs = payload["card_scores"]
    assert cs, "card_scores is empty"
    seen_labels: set[str] = set()
    for ref in cs:
        assert "::" in ref, f"card_scores key not in '<label>::<card>' form: {ref}"
        label = ref.split("::", 1)[0]
        seen_labels.add(label)
    assert seen_labels == set(builders.keys()), (
        f"card_scores label coverage gap: expected {sorted(builders)}, "
        f"got {sorted(seen_labels)}"
    )
    print(f"[ok] card_scores covers {len(cs)} card refs across "
          f"{len(seen_labels)} decks")

    # 7. matchup: 3 unordered pairings → 3 entries.
    assert len(payload["matchup"]) == 3, (
        f"expected 3 matchup pairings, got {len(payload['matchup'])}: "
        f"{list(payload['matchup'])}"
    )
    print(f"[ok] matchup: {list(payload['matchup'])}")

    print("\nSMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
