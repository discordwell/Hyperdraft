"""Beyond Ravnica Pokemon custom-set balance checks."""

import json
import subprocess
import sys

import pytest

from src.cards.pokemon.beyond.ravnica import (
    GUILD_DECK_BUILDERS,
    build_ravnica_guild_deck,
    list_ravnica_guild_decks,
    ravnica_balance_flags,
    ravnica_balance_summary,
)
from src.cards.pokemon.beyond.ravnica.balance import ravnica_guild_profile


def test_ravnica_balance_summary_tracks_all_guilds():
    summary = ravnica_balance_summary()

    assert set(summary) == {
        "azorius", "boros", "dimir", "golgari", "gruul",
        "izzet", "orzhov", "rakdos", "selesnya", "simic",
    }
    for guild, profile in summary.items():
        assert profile["size"] == 60, guild
        assert profile["pokemon_count"] == 16, guild
        assert profile["basic_count"] >= 8, guild
        assert 10 <= profile["energy_count"] <= 18, guild
        assert profile["supporter_count"] >= 8, guild
        assert profile["item_count"] >= 12, guild
        assert profile["copy_violations"] == [], guild
        assert profile["balance_flags"] == [], guild


def test_ravnica_balance_scores_remain_in_expected_band():
    summary = ravnica_balance_summary()

    for profile in summary.values():
        assert profile["consistency_score"] >= 45
        assert profile["pressure_score"] >= 40
        assert profile["stadium_count"] <= 3


def test_ravnica_balance_flags_detect_bad_profiles():
    assert "too_few_basics" in ravnica_balance_flags("izzet", {
        "size": 60,
        "copy_violations": [],
        "pokemon_count": 16,
        "basic_count": 4,
        "energy_count": 13,
        "supporter_count": 10,
        "item_count": 16,
        "consistency_score": 50,
        "pressure_score": 45,
        "stadium_count": 2,
    })
    assert "low_pressure_score" in ravnica_balance_flags("azorius", {
        "size": 60,
        "copy_violations": [],
        "pokemon_count": 16,
        "basic_count": 9,
        "energy_count": 13,
        "supporter_count": 10,
        "item_count": 16,
        "consistency_score": 50,
        "pressure_score": 20,
        "stadium_count": 2,
    })


def test_ravnica_balance_report_writes_json_artifact(tmp_path):
    out_path = tmp_path / "ravnica_balance.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/play/ravnica_balance_report.py",
            "--out",
            str(out_path),
            "--fail-on-flags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_report = json.loads(result.stdout)
    file_report = json.loads(out_path.read_text())
    assert stdout_report == file_report
    assert file_report["format"] == "pokemon_beyond_ravnica_balance"
    assert file_report["quality_gate"]["passed"] is True
    assert len(file_report["guilds"]) == 10


def test_validated_ravnica_deckbuilder_serves_all_guilds():
    assert list_ravnica_guild_decks() == sorted(GUILD_DECK_BUILDERS)

    for guild in list_ravnica_guild_decks():
        deck, strategy = build_ravnica_guild_deck(guild)
        profile = ravnica_guild_profile(guild, deck)
        assert len(deck) == 60
        assert strategy["guild"] == guild
        assert not profile["balance_flags"]
        assert deck is not build_ravnica_guild_deck(guild, enforce_balance=False)[0]


def test_validated_ravnica_deckbuilder_rejects_unknown_guilds():
    with pytest.raises(ValueError, match="Unknown Beyond Ravnica guild"):
        build_ravnica_guild_deck("not_a_guild")
