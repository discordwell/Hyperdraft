"""
Regression guard for ``scp_on_*`` orphan trigger slots.

Cards in ``src/cards/scp/`` can declare ``scp_on_<name>`` callable hooks on
their ``CardDefinition``. The engine only fires a subset of those hooks —
the rest are dead-letter declarations. When a card author adds a new
``scp_on_<name>`` declaration assuming the engine will pick it up, the
result is a silent no-op: the test plays, the card "fires" (sets the
attribute) but nothing happens at runtime.

This test does two things:

1. Pins the current set of *orphan* slots — slots declared by at least one
   card but never read by ``src/engine/scp*.py``. The list is grandfathered
   from the 2026-05-14 audit. A new orphan declaration (a slot in
   ``src/cards/scp/`` that the engine never reads) fails the test.

2. Asserts that the engine still reads every slot the test expects it to.
   A future engine refactor that drops, say, ``scp_on_reveal`` would fail
   the test even before the cards visibly break.

The audit script that produced these baselines is
``scripts/audit_scp_orphan_triggers.py``. Run it with ``--json`` to refresh
the grandfather lists in this file when intentionally rebalancing.

Run::

    python -m pytest tests/test_scp_orphan_triggers.py -q
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


SLOT_PATTERN = re.compile(r"scp_on_[a-z_]+")

REPO_ROOT = Path(__file__).resolve().parent.parent
CARD_DIR = REPO_ROOT / "src" / "cards" / "scp"
ENGINE_DIR = REPO_ROOT / "src" / "engine"


# Slots the engine MUST continue to read. Removing a wired slot here is
# a deliberate engine deprecation — update this list AND the cards in the
# same commit.
EXPECTED_WIRED_SLOTS = frozenset({
    "scp_on_assign",
    "scp_on_contain",
    "scp_on_reveal",
    "scp_on_test",
    "scp_on_test_fail",
})


# Slots that are *currently* orphaned — declared by at least one card but
# never read by the engine. Captured at 2026-05-14 (audit run: 17 orphans,
# 60+ declarations across the orphan set). New orphans cannot be added
# without updating this allow-list — that forces the card author to either
# (a) wire the slot in the engine or (b) remove the orphan declaration.
#
# The recommended close-out for each orphan slot is one of:
#  * "wire in engine"  — the trigger semantics are real and 3+ cards use it
#  * "remove from card" — the trigger was speculative; rewrite via existing
#                         wired slots or via scp_effect
GRANDFATHERED_ORPHAN_SLOTS = frozenset({
    "scp_on_activate",              # 1 decl
    "scp_on_annihilation_wave_fire", # 2 decl
    "scp_on_anomaly_enter",          # 3 decl
    "scp_on_any_compleated",         # 1 decl
    "scp_on_archive",                # 5 decl
    "scp_on_archive_stub",           # 1 decl
    "scp_on_audit_return",           # 6 decl
    "scp_on_breach",                 # 6 decl
    "scp_on_dragon_contain",         # 2 decl
    "scp_on_memory_hole",            # 3 decl
    "scp_on_open_dossier",           # 2 decl
    "scp_on_opponent_compleated",    # 3 decl
    "scp_on_play",                   # 10 decl — highest-value rewire target
    "scp_on_rift_play",              # 1 decl
    "scp_on_sacrifice",              # 11 decl — highest-volume orphan
    "scp_on_turn_end",               # 3 decl
    "scp_on_you_compleated",         # 3 decl
})


# ---------------------------------------------------------------------------
# Scan helpers — duplicated from scripts/audit_scp_orphan_triggers.py so
# this test stays runnable without importing a script.
# ---------------------------------------------------------------------------


def _scan_card_slots() -> set[str]:
    slots: set[str] = set()
    for path in CARD_DIR.rglob("*.py"):
        text = path.read_text()
        for match in SLOT_PATTERN.finditer(text):
            slots.add(match.group(0))
    return slots


def _scan_engine_slots() -> set[str]:
    slots: set[str] = set()
    for path in ENGINE_DIR.glob("scp*.py"):
        text = path.read_text()
        for match in SLOT_PATTERN.finditer(text):
            slots.add(match.group(0))
    return slots


def _scan_card_files_per_slot() -> dict[str, set[str]]:
    file_map: dict[str, set[str]] = defaultdict(set)
    for path in CARD_DIR.rglob("*.py"):
        text = path.read_text()
        for match in SLOT_PATTERN.finditer(text):
            file_map[match.group(0)].add(str(path.relative_to(REPO_ROOT)))
    return file_map


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_engine_continues_reading_every_expected_wired_slot():
    """A future engine refactor that drops a wired slot must update both
    EXPECTED_WIRED_SLOTS AND the cards that use it, in the same commit.
    Failing here means the engine no longer reads one of the slots we
    promised to fire — cards will silently no-op."""
    engine_slots = _scan_engine_slots()
    missing = EXPECTED_WIRED_SLOTS - engine_slots
    assert not missing, (
        f"Engine no longer reads expected slot(s): {sorted(missing)}\n"
        f"  If this is intentional, remove from EXPECTED_WIRED_SLOTS AND "
        f"audit the cards under src/cards/scp/ that declare it."
    )


def test_no_new_orphan_slots_have_been_introduced():
    """A new ``scp_on_<name>`` declaration must be matched by an engine read.

    If you add ``scp_on_play_new`` to a card and the engine doesn't read it,
    this test fails — push you to either wire the slot in the engine or
    rewrite the card via an existing wired slot. Grandfathered orphans
    stay grandfathered until the next intentional refactor pass.
    """
    card_slots = _scan_card_slots()
    engine_slots = _scan_engine_slots()
    actual_orphans = card_slots - engine_slots

    new_orphans = actual_orphans - GRANDFATHERED_ORPHAN_SLOTS
    files_per_slot = _scan_card_files_per_slot()
    diagnostic = "\n".join(
        f"  {slot}: declared in {sorted(files_per_slot[slot])}"
        for slot in sorted(new_orphans)
    )
    assert not new_orphans, (
        f"New orphan scp_on_* slot(s) detected — engine has no reader:\n"
        f"{diagnostic}\n"
        f"  Either wire the slot under src/engine/scp*.py or rewrite the "
        f"card via an existing wired slot. To intentionally grandfather a "
        f"slot, add it to GRANDFATHERED_ORPHAN_SLOTS with a # decl-count "
        f"comment."
    )


def test_grandfathered_orphan_list_does_not_drift_above_baseline():
    """The reverse direction: every grandfathered orphan must still be
    declared by at least one card. If a card author cleans up an orphan
    declaration, the grandfather entry must come out too — otherwise the
    allow-list rots and could mask a future re-introduction of the slot."""
    card_slots = _scan_card_slots()
    stale = GRANDFATHERED_ORPHAN_SLOTS - card_slots
    assert not stale, (
        f"Grandfathered orphan slot(s) no longer declared by any card: "
        f"{sorted(stale)}\n"
        f"  Remove from GRANDFATHERED_ORPHAN_SLOTS in this test. "
        f"(Cleaning up an orphan slot is a *good* outcome — this test "
        f"makes sure the cleanup ripples here too.)"
    )


def test_audit_script_runs_and_classifies_consistently():
    """The audit script and this test must agree on which slots are wired
    vs. orphan — they share the same logic, but a future refactor could
    drift them apart."""
    import subprocess
    import sys
    import json

    script = REPO_ROOT / "scripts" / "audit_scp_orphan_triggers.py"
    result = subprocess.run(
        [sys.executable, str(script), "--json"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    audit_wired = {row["slot"] for row in payload["wired"]}
    audit_orphans = {row["slot"] for row in payload["orphans"]}

    card_slots = _scan_card_slots()
    engine_slots = _scan_engine_slots()
    expected_wired = card_slots & engine_slots
    expected_orphans = card_slots - engine_slots

    assert audit_wired == expected_wired, (
        f"Audit-script wired slots {audit_wired} != test scan {expected_wired}"
    )
    assert audit_orphans == expected_orphans, (
        f"Audit-script orphan slots {audit_orphans} != test scan {expected_orphans}"
    )
