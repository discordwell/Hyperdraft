"""Tests for the strategy-doc bootstrap (src/server/strategy_doc.py).

The bootstrap is a one-shot lifespan-startup task that seeds writable
copies of the strategy docs from the shipped baseline. It must:
  - create storage/strategy/<mode>.md for each KNOWN_MODES entry if missing
  - leave existing writable copies UNTOUCHED so LLM-pilot edits persist
  - create the storage/ultra-agent/notes/ directory for per-match scratchpads
  - fall back to a stub when a mode has no shipped baseline
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.server import strategy_doc


@pytest.fixture
def isolated_workdir(tmp_path, monkeypatch):
    """Redirect BASELINE_DIR + WRITABLE_DIR + NOTES_DIR into a tmp tree."""
    baseline = tmp_path / "docs" / "strategy"
    writable = tmp_path / "storage" / "strategy"
    notes = tmp_path / "storage" / "ultra-agent" / "notes"
    baseline.mkdir(parents=True)
    monkeypatch.setattr(strategy_doc, "BASELINE_DIR", baseline)
    monkeypatch.setattr(strategy_doc, "WRITABLE_DIR", writable)
    monkeypatch.setattr(strategy_doc, "NOTES_DIR", notes)
    return tmp_path, baseline, writable, notes


def test_bootstrap_seeds_from_baseline(isolated_workdir):
    _, baseline, writable, notes = isolated_workdir
    (baseline / "mtg.md").write_text("# MTG baseline content")

    strategy_doc.bootstrap()

    assert (writable / "mtg.md").read_text() == "# MTG baseline content"
    assert notes.exists()


def test_bootstrap_preserves_existing_writable(isolated_workdir):
    """A writable copy from a prior session must not be overwritten."""
    _, baseline, writable, _ = isolated_workdir
    writable.mkdir(parents=True, exist_ok=True)
    (writable / "pokemon.md").write_text("# session takeaway from yesterday")
    (baseline / "pokemon.md").write_text("# pristine baseline")

    strategy_doc.bootstrap()

    assert (writable / "pokemon.md").read_text() == "# session takeaway from yesterday"


def test_bootstrap_creates_stubs_for_modes_without_baseline(isolated_workdir):
    """If a KNOWN_MODES entry has no docs/strategy/<mode>.md, write a stub
    so the launcher's STRATEGY_DOC=... path always resolves."""
    _, _baseline, writable, _ = isolated_workdir
    # Leave baseline dir empty

    strategy_doc.bootstrap()

    for mode in strategy_doc.KNOWN_MODES:
        stub = writable / f"{mode}.md"
        assert stub.exists(), f"missing stub for {mode}"
        body = stub.read_text()
        assert mode in body.lower() or "strategy doc" in body.lower()
        assert "Session takeaways" in body


def test_read_strategy_prefers_writable(isolated_workdir):
    _, baseline, writable, _ = isolated_workdir
    (baseline / "scp.md").write_text("# baseline")
    writable.mkdir(parents=True)
    (writable / "scp.md").write_text("# updated by claude")

    assert strategy_doc.read_strategy("scp") == "# updated by claude"


def test_read_strategy_falls_back_to_baseline(isolated_workdir):
    _, baseline, _, _ = isolated_workdir
    (baseline / "depths.md").write_text("# only baseline")

    assert strategy_doc.read_strategy("depths") == "# only baseline"


def test_read_strategy_returns_none_when_absent(isolated_workdir):
    assert strategy_doc.read_strategy("nonexistent") is None
