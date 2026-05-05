"""Beyond Ravnica Pokemon custom-set balance checks."""

import json
import subprocess
import sys
from collections import defaultdict

import pytest

from scripts.beyond.wet_test.round_robin import build_round_robin_report
from src.cards.pokemon.beyond.ravnica import (
    GUILD_DECK_BUILDERS,
    build_all_ravnica_guild_decks,
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
        assert profile["trainer_count"] >= 30, guild
        assert profile["trainer_to_energy_ratio"] >= 2.0, guild
        assert profile["supporter_count"] >= 8, guild
        assert profile["item_count"] >= 12, guild
        assert profile["primary_energy_count"] >= 7, guild
        assert profile["energy_alignment_score"] >= 7, guild
        assert profile["energy_type_counts"], guild
        assert profile["pokemon_type_counts"], guild
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
        "primary_energy_count": 8,
        "energy_alignment_score": 8,
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
        "primary_energy_count": 8,
        "energy_alignment_score": 8,
        "consistency_score": 50,
        "pressure_score": 20,
        "stadium_count": 2,
    })
    assert "low_energy_alignment" in ravnica_balance_flags("azorius", {
        "size": 60,
        "copy_violations": [],
        "pokemon_count": 16,
        "basic_count": 9,
        "energy_count": 13,
        "supporter_count": 10,
        "item_count": 16,
        "primary_energy_count": 8,
        "energy_alignment_score": 3,
        "consistency_score": 50,
        "pressure_score": 45,
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
    assert file_report["summary"]["guild_count"] == 10
    assert file_report["summary"]["flagged_guild_count"] == 0
    assert file_report["summary"]["min_energy_alignment_score"] >= 7
    assert file_report["summary"]["consistency_score_spread"] >= 0
    assert file_report["summary"]["pressure_score_spread"] >= 0
    assert len(file_report["guilds"]) == 10


def test_ravnica_balance_report_can_focus_one_guild():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/play/ravnica_balance_report.py",
            "--guild",
            "izzet",
            "--fail-on-flags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert set(report["guilds"]) == {"izzet"}
    assert report["summary"]["guild_count"] == 1
    assert report["guilds"]["izzet"]["primary_energy_count"] >= 7


def test_validated_ravnica_deckbuilder_serves_all_guilds():
    assert list_ravnica_guild_decks() == sorted(GUILD_DECK_BUILDERS)

    for guild in list_ravnica_guild_decks():
        deck, strategy = build_ravnica_guild_deck(guild)
        profile = ravnica_guild_profile(guild, deck)
        assert len(deck) == 60
        assert strategy["guild"] == guild
        assert not profile["balance_flags"]
        assert deck is not build_ravnica_guild_deck(guild, enforce_balance=False)[0]

    all_decks = build_all_ravnica_guild_decks()
    assert sorted(all_decks) == list_ravnica_guild_decks()
    assert all(len(deck) == 60 for deck, _strategy in all_decks.values())


def test_validated_ravnica_deckbuilder_rejects_unknown_guilds():
    with pytest.raises(ValueError, match="Unknown Beyond Ravnica guild"):
        build_ravnica_guild_deck("not_a_guild")


def test_ravnica_round_robin_report_summarizes_anomalies():
    wins = defaultdict(int, {"izzet": 1})
    losses = defaultdict(int, {"azorius": 1})
    draws = defaultdict(int)
    timeouts = defaultdict(int)
    crashes = defaultdict(int)

    report = build_round_robin_report(
        ["azorius", "izzet"],
        wins,
        losses,
        draws,
        timeouts,
        crashes,
        ["azorius vs izzet: timeout @ turn 80"],
        [12, 80],
        1.25,
        2,
    )

    assert report["format"] == "pokemon_beyond_ravnica_round_robin"
    assert report["quality_gate"]["passed"] is False
    assert report["quality_gate"]["anomaly_count"] == 1
    assert report["standings"]["izzet"]["win_rate"] == 1.0
