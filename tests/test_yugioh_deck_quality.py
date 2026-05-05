"""Yu-Gi-Oh! deckbuilding quality checks."""

import json
import subprocess
import sys

from src.cards.yugioh.deck_quality import analyze_all_ygo_optimized_decks
from src.cards.yugioh.ygo_optimized import YGO_OPTIMIZED_DECKS


def test_all_optimized_ygo_decks_have_clean_quality_metrics():
    summaries = analyze_all_ygo_optimized_decks()

    assert set(summaries) == set(YGO_OPTIMIZED_DECKS)
    for deck_name, summary in summaries.items():
        assert summary["size"] == 40, deck_name
        assert summary["monster_count"] >= 10, deck_name
        assert summary["low_level_monster_count"] >= 8, deck_name
        assert summary["removal_count"] >= 5, deck_name
        assert summary["missing_summon_priority"] == [], deck_name
        assert summary["missing_set_priority"] == [], deck_name
        assert summary["copy_violations"] == [], deck_name
        assert summary["quality_flags"] == [], deck_name
        assert summary["role_quality_flags"] == [], deck_name


def test_ygo_role_metrics_cover_optimized_archetypes():
    summaries = analyze_all_ygo_optimized_decks()

    goat = summaries["goat_control"]
    assert goat["role"] == "Control"
    assert goat["draw_count"] >= 3
    assert goat["removal_count"] >= 10

    monarch = summaries["monarch_control"]
    assert monarch["role"] == "Tribute Control"
    assert monarch["tribute_monster_count"] >= 8
    assert monarch["tribute_fodder_count"] >= 8

    burn = summaries["chain_burn"]
    assert burn["role"] == "Burn / Stall"
    assert burn["burn_count"] >= 8
    assert burn["stall_count"] >= 3
    assert burn["monster_count"] <= 16
    assert burn["set_priority_count"] >= 4

    dragon = summaries["dragon_beatdown"]
    assert dragon["role"] == "Beatdown / Aggro"
    assert dragon["dragon_count"] >= 14
    assert dragon["pressure_monster_count"] >= 10
    assert dragon["summon_priority_count"] >= 5


def test_ygo_deck_quality_report_outputs_json_without_flags():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/play/yugioh_deck_quality_report.py",
            "--fail-on-flags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert set(report) == set(YGO_OPTIMIZED_DECKS)
    assert all(not summary["quality_flags"] for summary in report.values())
    assert all(not summary["role_quality_flags"] for summary in report.values())
