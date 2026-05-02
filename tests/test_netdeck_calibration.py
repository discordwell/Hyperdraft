#!/usr/bin/env python3
"""
Smoke test for scripts/play/netdeck_calibration.py.

Mocks the W2 (`build_heuristic_deck`) and W4 (`run_deck_tournament`)
dependencies so this test runs without those worktrees being merged.
Verifies:

  - JSON shape has expected top-level keys (date, git_sha, args,
    per_archetype, per_matchup).
  - Markdown report file is written and contains the load-bearing
    "## Notes" section.
  - One JSONL line is appended to the history file per run.

Per spec:
  - Calibration is a PROGRESS METRIC, not a pass-bar. The test asserts
    only structural correctness, never specific winrates.
  - Skips gracefully if NETDECKS does not contain an Aggro entry.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _has_aggro_netdeck() -> bool:
    """Return True iff at least one netdeck has archetype=='Aggro'."""
    try:
        from src.decks.netdecks import NETDECKS
        return any(d.archetype == "Aggro" for d in NETDECKS.values())
    except Exception:
        return False


def _make_fake_deck(name: str = "fake", archetype: str = "Aggro"):
    """Construct a minimal Deck stand-in for the hybrid build."""
    from src.decks.deck import Deck, DeckEntry
    return Deck(
        name=name,
        archetype=archetype,
        colors=["R"],
        description=f"Fake hybrid for {archetype}",
        mainboard=[DeckEntry("Mountain", 60)],
        sideboard=[],
    )


def _make_fake_tournament_results(deck_pool: dict, games_per_pair: int = 1, **_kwargs):
    """
    Synthetic tournament result mirroring the W4 output shape.

    Strategy: hybrid_<arch> wins half the games it plays, loses the
    other half — gives non-trivial W/L/D counts so aggregation paths
    are exercised. Labels in the output use `p1_label`/`winner_label`
    (the post-rename W4 shape) — the production code also tolerates
    `p1_domain`/`winner_domain` so either is fine.
    """
    labels = list(deck_pool.keys())
    results = []
    # Round-robin over distinct pairs
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            for g in range(games_per_pair):
                p1, p2 = (a, b) if g % 2 == 0 else (b, a)
                # Deterministic: alternate winner so we get a mix of W/L
                winner = p1 if g % 2 == 0 else p2
                results.append({
                    "p1_label": p1,
                    "p2_label": p2,
                    "p1_domain": p1,    # back-compat key
                    "p2_domain": p2,
                    "winner_label": winner,
                    "winner_domain": winner,
                    "turns": 5,
                    "p1_life": 0 if winner == p2 else 20,
                    "p2_life": 0 if winner == p1 else 20,
                    "duration_s": 0.1,
                    "card_stats": {},
                })
    return {
        "domains": labels,
        "labels": labels,
        "games_per_pair": games_per_pair,
        "max_turns": 14,
        "difficulty": "hard",
        "deck_info": {lab: {"size": 60} for lab in labels},
        "elapsed_s": 0.5,
        "results": results,
    }


@unittest.skipUnless(
    _has_aggro_netdeck(),
    "NETDECKS does not contain an Aggro archetype — skipping calibration smoke",
)
class TestNetdeckCalibration(unittest.TestCase):
    def setUp(self):
        # Ensure scripts/play/netdeck_calibration is importable
        from scripts.play import netdeck_calibration as nc
        self.nc = nc

    def test_smoke_json_shape_and_history(self):
        """Run main() with mocks and verify outputs."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out_json = tmp_path / "calib.json"
            out_md = tmp_path / "calib.md"
            history = tmp_path / "history.jsonl"

            # Patch the lazy-imported dependencies inside the calibration module.
            # The functions are imported *inside* the runner functions, so we
            # patch them at their import sites.
            with patch(
                "src.decks.heuristics.builder.build_heuristic_deck",
                side_effect=lambda **kw: _make_fake_deck(
                    name=kw.get("name", "Hybrid"),
                    archetype=kw.get("archetype", "Aggro"),
                ),
                create=True,
            ), patch(
                "scripts.play.custom_set_tournament.run_deck_tournament",
                side_effect=_make_fake_tournament_results,
                create=True,
            ):
                rc = self.nc.main([
                    "--games", "1",
                    "--archetypes", "Aggro",
                    "--top-n", "1",
                    "--out", str(out_json),
                    "--md", str(out_md),
                    "--history", str(history),
                ])

            # Calibration is informational; main() should always return 0.
            self.assertEqual(rc, 0)

            # JSON file exists and has the expected shape
            self.assertTrue(out_json.exists(), f"missing {out_json}")
            data = json.loads(out_json.read_text())
            for key in ("date", "git_sha", "args", "per_archetype", "per_matchup"):
                self.assertIn(key, data, f"missing key {key!r} in JSON output")

            # args block sanity
            self.assertEqual(data["args"]["games"], 1)
            self.assertEqual(data["args"]["top_n"], 1)
            self.assertIn("Aggro", data["args"]["archetypes"])

            # per_archetype sanity
            self.assertIn("Aggro", data["per_archetype"])
            aggro = data["per_archetype"]["Aggro"]
            self.assertIn("hybrid_label", aggro)
            self.assertIn("same_archetype", aggro)
            self.assertIn("cross_archetype", aggro)
            self.assertIn("same_archetype_winrate", aggro)
            self.assertIsInstance(aggro["same_archetype"], list)
            # With top-n=1 and at least one Aggro netdeck, we expect 1 row.
            self.assertEqual(
                len(aggro["same_archetype"]), 1,
                "expected exactly one same-archetype matchup (top-n=1)",
            )

            # Markdown file exists and contains the Notes section
            self.assertTrue(out_md.exists(), f"missing {out_md}")
            md = out_md.read_text()
            self.assertIn("## Notes", md, "markdown must include '## Notes' framing")
            self.assertIn(
                "informational", md.lower(),
                "Notes section should explain calibration is informational",
            )
            self.assertIn("# Hybrid Builder Calibration", md)

            # History JSONL file appended to (one line)
            self.assertTrue(history.exists(), f"missing {history}")
            lines = [ln for ln in history.read_text().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1, "expected one history line per run")
            entry = json.loads(lines[0])
            for key in ("date", "git_sha", "per_archetype_winrate", "args"):
                self.assertIn(key, entry, f"missing key {key!r} in history entry")
            self.assertIn("Aggro", entry["per_archetype_winrate"])

    def test_history_is_append_only(self):
        """Two runs should produce two JSONL lines (append-only)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = tmp_path / "history.jsonl"

            def _run_once(idx: int):
                out_json = tmp_path / f"calib_{idx}.json"
                out_md = tmp_path / f"calib_{idx}.md"
                with patch(
                    "src.decks.heuristics.builder.build_heuristic_deck",
                    side_effect=lambda **kw: _make_fake_deck(
                        name=kw.get("name", "Hybrid"),
                        archetype=kw.get("archetype", "Aggro"),
                    ),
                    create=True,
                ), patch(
                    "scripts.play.custom_set_tournament.run_deck_tournament",
                    side_effect=_make_fake_tournament_results,
                    create=True,
                ):
                    return self.nc.main([
                        "--games", "1",
                        "--archetypes", "Aggro",
                        "--top-n", "1",
                        "--out", str(out_json),
                        "--md", str(out_md),
                        "--history", str(history),
                    ])

            self.assertEqual(_run_once(1), 0)
            self.assertEqual(_run_once(2), 0)

            lines = [ln for ln in history.read_text().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2, "history should append, not overwrite")
            for ln in lines:
                json.loads(ln)  # each line is valid JSON


if __name__ == "__main__":
    unittest.main()
