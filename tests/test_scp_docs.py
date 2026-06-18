"""Doc-truth guard for the canonical SCP ruleset (`docs/design/scp_rules.md`).

§8 ("Card-type taxonomy & example cards") silently rotted once: written as a Phase-1 sketch
and never reconciled with the shipped pool, it listed real cards with *wrong* effects
(Worldspine Wurm "Total Breach +2" vs the real +5, Memetic Archive "reveals hand" vs the real
"expose", Reality Bender / Emergency Lockdown with effects that were never built) **and** ~6
phantom cards that never existed (Skeleton Key, Field Medic, Mole, EMP Charge, Forged
Credentials, Smash & Grab). The numeric sections (§9 decks, §10 numbers) stayed current, so the
drift hid in plain sight inside a section most lines of which were correct.

This test pins every card named in §8 to a real `CardDefinition` and re-derives the stat lines
from code, so the canonical doc cannot drift from the engine again. It is the doc analogue of
the repo's other anti-rot gates (test_scp_cards = effect gate, test_scp_selfplay = fire gate).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.cards.scp import foundation as F, insurgency as I
from src.engine.types import CardType

RULES_PATH = Path(__file__).resolve().parents[1] / "docs" / "design" / "scp_rules.md"

ALL_CARDS = list(F.FOUNDATION_CARDS) + list(I.INSURGENCY_CARDS)


def _section8() -> str:
    text = RULES_PATH.read_text(encoding="utf-8")
    # §8 runs from its header to the start of the next top-level (## N.) section.
    m = re.search(r"^## 8\. .*?(?=^## \d+\.)", text, re.S | re.M)
    assert m, "could not locate §8 in scp_rules.md"
    return m.group(0)


def _bullets() -> list[tuple[str, str]]:
    """Every example-card bullet in §8, as (card_name, rest_of_line).

    Card names are the first emphasised ``*...*`` span on a line that starts with ``- ``; this
    tolerates a leading qualifier (none today, but e.g. ``- Foundation *Name*``).
    """
    out = []
    for line in _section8().splitlines():
        if not line.lstrip().startswith("- "):
            continue
        m = re.search(r"\*([^*]+)\*\s*(.*)$", line)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _find_card(friendly_name: str):
    """Resolve a doc's friendly name to a shipped card. Anomalies carry an ``SCP-####`` prefix,
    so match on an exact name or a name *suffix*; others match exactly. Returns None if absent."""
    name = re.sub(r"\s*\(.*?\)\s*$", "", friendly_name).strip()  # drop a trailing "(TRAP)" etc.
    for cd in ALL_CARDS:
        if cd.name == name or cd.name.endswith(" " + name):
            return cd
    return None


def _kind(cd) -> CardType | None:
    return getattr(cd, "scp_kind", None)


def test_section8_has_example_bullets():
    # Guard the parser itself: if §8 is restructured into something this test can't read, fail
    # loudly rather than vacuously pass (a silent zero-bullet match would hide all drift).
    bullets = _bullets()
    assert len(bullets) >= 30, f"§8 parsed to only {len(bullets)} card bullets — parser/section drift?"


def test_every_card_named_in_section8_is_real():
    """Catches phantom cards and renames: each *Name* in §8 must exist in the shipped pool."""
    missing = [name for name, _rest in _bullets() if _find_card(name) is None]
    assert not missing, (
        "§8 names cards that are not in the shipped SCP pool (phantoms or stale renames): "
        f"{missing}"
    )


def test_section8_anomaly_and_layer_statlines_match_code():
    """The first ``N/M`` token on each anomaly/layer bullet is its real Threshold/Value (anomaly)
    or strength/rez (layer). This is the check that would have caught the Worldspine "+2" bug's
    cousins — a stat line that reads plausibly but disagrees with the engine."""
    mismatches = []
    for name, rest in _bullets():
        cd = _find_card(name)
        if cd is None:
            continue  # existence is asserted by its own test
        nm = re.search(r"\b(\d+)/(\d+)\b", rest)
        if not nm:
            continue
        a, b = int(nm.group(1)), int(nm.group(2))
        if _kind(cd) == CardType.SCP_ANOMALY:
            real = (int(getattr(cd, "scp_threshold", 0)), int(getattr(cd, "scp_value", 0)))
            if (a, b) != real:
                mismatches.append(f"{name}: doc says {a}/{b}, code is {real[0]}/{real[1]} (Threshold/Value)")
        elif _kind(cd) == CardType.SCP_LAYER:
            real = (int(getattr(cd, "scp_strength", 0)), int(getattr(cd, "scp_rez", 0)))
            if (a, b) != real:
                mismatches.append(f"{name}: doc says {a}/{b}, code is {real[0]}/{real[1]} (strength/rez)")
    assert not mismatches, "§8 stat lines disagree with the code:\n  " + "\n  ".join(mismatches)


def test_section8_breach_on_free_claims_match_code():
    """A bullet that promises "Total Breach +N" on free must match the card's breach_on_free
    override (this is the exact line that was wrong: Worldspine said +2, the engine does +5)."""
    mismatches = []
    for name, rest in _bullets():
        cd = _find_card(name)
        if cd is None or _kind(cd) != CardType.SCP_ANOMALY:
            continue
        m = re.search(r"on-free:\s*Total Breach \+(\d+)", rest)
        if not m:
            continue
        claimed = int(m.group(1))
        real = getattr(cd, "scp_breach_on_free", None)
        # breach_on_free=None means "freeing adds the anomaly's Value" — so the doc's number must
        # equal the explicit override when set, or the Value when not.
        expected = int(real) if real is not None else int(getattr(cd, "scp_value", 0))
        if claimed != expected:
            mismatches.append(f"{name}: doc says on-free +{claimed}, code yields +{expected}")
    assert not mismatches, "§8 on-free breach claims disagree with the code:\n  " + "\n  ".join(mismatches)


def test_section8_operative_power_matches_code():
    """Each operative bullet's "power N" is its real base break power."""
    mismatches = []
    for name, rest in _bullets():
        cd = _find_card(name)
        if cd is None or _kind(cd) != CardType.SCP_OPERATIVE:
            continue
        m = re.search(r"power (\d+)", rest)
        if not m:
            continue
        if int(m.group(1)) != int(getattr(cd, "scp_power", 0)):
            mismatches.append(f"{name}: doc says power {m.group(1)}, code is {getattr(cd, 'scp_power', 0)}")
    assert not mismatches, "§8 operative power disagrees with the code:\n  " + "\n  ".join(mismatches)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
