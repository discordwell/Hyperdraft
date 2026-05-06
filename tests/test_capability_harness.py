"""
Tests for the per-card capability test harness.

Validates:
- The PKH synergy registry has no typos (every partner exists in PKH).
- `build_synergy_deck` produces a 60-card deck containing the focal.
- `run_capability_test` runs end-to-end and returns a metrics dict.

The single-game smoke is the slowest test here (~25s wall cap). Skipped
in default pytest runs by setting `SKIP_CAPABILITY_SMOKE=1` in env.
"""

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cards.custom import CUSTOM_SETS
from src.cards.custom.pokemon_horizons_synergies import PKH_SYNERGY_PACKAGES
from src.engine.types import CardType
from scripts.play.capability_test import (
    build_synergy_deck,
    run_capability_test,
    _load_synergy_registry,
)


def _is_land(cd):
    return CardType.LAND in (cd.characteristics.types or set())


def test_synergy_registry_is_loadable():
    """The PKH registry resolves through `_load_synergy_registry`."""
    print("\n=== synergy registry: load ===")
    reg = _load_synergy_registry("PKH")
    assert isinstance(reg, dict)
    assert len(reg) >= 8, f"PKH registry should have ≥8 spice entries; got {len(reg)}"
    print(f"  Loaded {len(reg)} synergy packages for PKH")


def test_pkh_synergy_partners_all_exist():
    """Every named partner must be in the PKH card pool — catches typos."""
    print("\n=== synergy registry: partner sanity ===")
    pkh = CUSTOM_SETS["PKH"]
    missing: list[tuple[str, str]] = []
    for focal, partners in PKH_SYNERGY_PACKAGES.items():
        if focal not in pkh:
            missing.append((focal, "<focal missing>"))
            continue
        for p in partners:
            if p not in pkh:
                missing.append((focal, p))
    assert not missing, f"Missing partners (focal, partner): {missing[:5]}"
    print(f"  All {sum(len(v) for v in PKH_SYNERGY_PACKAGES.values())} partner refs resolve")


def test_build_synergy_deck_60_cards_contains_focal():
    """A built synergy deck is 60 cards and includes 4 copies of the focal."""
    print("\n=== build_synergy_deck: shape ===")
    pkh = CUSTOM_SETS["PKH"]
    focal = "Pikachu, Thunder Champion"
    partners = PKH_SYNERGY_PACKAGES[focal]
    deck = build_synergy_deck(focal, partners, pkh)

    assert len(deck) == 60, f"Deck should be 60 cards; got {len(deck)}"
    focal_count = sum(1 for c in deck if c.name == focal)
    assert focal_count == 4, f"Should have 4 copies of focal; got {focal_count}"

    spell_count = sum(1 for c in deck if not _is_land(c))
    land_count = sum(1 for c in deck if _is_land(c))
    assert spell_count == 36, f"36 spells expected; got {spell_count}"
    assert land_count == 24, f"24 lands expected; got {land_count}"
    print(f"  {focal}: 4× focal + {spell_count - 4} other spells + {land_count} lands")


def test_build_synergy_deck_uses_partners():
    """At least 2 unique synergy partners should appear in the deck."""
    print("\n=== build_synergy_deck: partners present ===")
    pkh = CUSTOM_SETS["PKH"]
    focal = "Master Ball"
    partners = PKH_SYNERGY_PACKAGES[focal]
    deck = build_synergy_deck(focal, partners, pkh)
    deck_names = {c.name for c in deck if not _is_land(c)}
    partner_names_in_deck = deck_names & set(partners)
    assert len(partner_names_in_deck) >= 2, (
        f"Synergy deck should include ≥2 partners; got {len(partner_names_in_deck)}: "
        f"{partner_names_in_deck}"
    )
    print(f"  {focal}: {len(partner_names_in_deck)} unique partners in deck")


def test_build_synergy_deck_no_offcolor_filler():
    """Filler cards should be mono-primary-color (matching the build_set_deck contract)."""
    print("\n=== build_synergy_deck: color coherent ===")
    from scripts.play.custom_set_tournament import primary_color
    from src.engine.mana import ManaCost

    pkh = CUSTOM_SETS["PKH"]
    primary = primary_color(pkh)
    focal = "Hyper Beam"
    partners = PKH_SYNERGY_PACKAGES[focal]
    deck = build_synergy_deck(focal, partners, pkh)

    offcolor: list[str] = []
    for cd in deck:
        if _is_land(cd):
            continue
        cost = cd.characteristics.mana_cost or ""
        try:
            cc = ManaCost.parse(cost).colors
        except Exception:
            cc = set()
        # Synergy partners are allowed to be mono-primary; the filler
        # path enforces that, so the whole deck should be mono-primary.
        if cc - {primary}:
            offcolor.append((cd.name, [c.name for c in cc]))
    assert not offcolor, (
        f"Synergy deck shouldn't have off-primary spells (focal+partners "
        f"are all mono-primary in PKH): {offcolor[:3]}"
    )
    print(f"  All non-land cards mono-{primary.name[0]}")


@unittest.skipIf(
    os.environ.get("SKIP_CAPABILITY_SMOKE") == "1",
    "Capability smoke test is slow (~25s); set SKIP_CAPABILITY_SMOKE=1 to skip"
)
def test_capability_smoke_one_game():
    """End-to-end: run 1 game with Pikachu's synergy deck vs PKH baseline."""
    print("\n=== capability_test: smoke (1 game) ===")
    pkh = CUSTOM_SETS["PKH"]
    focal = "Pikachu, Thunder Champion"
    partners = PKH_SYNERGY_PACKAGES[focal]
    report = run_capability_test(
        focal_name=focal,
        synergy_partners=partners,
        set_cards=pkh,
        set_code="PKH",
        games=1,
        max_turns=14,
        per_turn_timeout_s=4.0,
        wall_deadline_s=25.0,
    )
    assert report["games_run"] == 1
    assert report["focal"] == focal
    assert "capability_score" in report
    assert "synergy_deck_winrate" in report
    # The 1-game sample isn't expected to pass any threshold, but the
    # report must exist and the metrics must be computed.
    assert isinstance(report["capability_score"], (int, float))
    print(
        f"  Smoke complete in {report['elapsed_s']:.0f}s — "
        f"capability_score={report['capability_score']:.2f}, "
        f"winrate={report['synergy_deck_winrate']*100:.0f}%"
    )


if __name__ == "__main__":
    test_synergy_registry_is_loadable()
    test_pkh_synergy_partners_all_exist()
    test_build_synergy_deck_60_cards_contains_focal()
    test_build_synergy_deck_uses_partners()
    test_build_synergy_deck_no_offcolor_filler()
    if os.environ.get("SKIP_CAPABILITY_SMOKE") != "1":
        test_capability_smoke_one_game()
    print("\nALL CAPABILITY-HARNESS TESTS PASSED!")
