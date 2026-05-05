"""Pokemon deckbuilding quality checks."""

import json
import subprocess
import sys

import pytest

from src.cards.pokemon.deck_builder import (
    SV_STARTER_DECK_BUILDERS,
    build_sv_starter_deck,
    list_sv_starter_decks,
)
from src.cards.pokemon.deck_quality import analyze_pokemon_deck_quality, analyze_sv_starter_decks


def test_sv_starter_decks_have_clean_quality_metrics():
    summaries = analyze_sv_starter_decks()

    assert set(summaries) == {"fire", "water"}
    for deck_name, summary in summaries.items():
        assert summary["size"] == 60, deck_name
        assert summary["pokemon_count"] >= 12, deck_name
        assert summary["basic_count"] >= 8, deck_name
        assert 12 <= summary["energy_count"] <= 24, deck_name
        assert summary["trainer_count"] >= 16, deck_name
        assert summary["search_count"] >= 4, deck_name
        assert summary["draw_count"] >= 4, deck_name
        assert summary["rare_candy_count"] >= 1, deck_name
        assert summary["copy_violations"] == [], deck_name
        assert summary["quality_flags"] == [], deck_name
        assert summary["role_quality_flags"] == [], deck_name


def test_sv_starter_deck_roles_have_switch_and_gust_tools():
    summaries = analyze_sv_starter_decks()

    for summary in summaries.values():
        assert summary["role"] == "starter"
        assert summary["switch_count"] >= 2
        assert summary["gust_count"] >= 1
        assert summary["supporter_count"] >= 6


def test_pokemon_deck_quality_report_writes_json_artifact(tmp_path):
    out_path = tmp_path / "pokemon_deck_quality.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/play/pokemon_deck_quality_report.py",
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
    assert file_report["format"] == "pokemon_deck_quality"
    assert file_report["quality_gate"]["passed"] is True
    assert sorted(file_report["decks"]) == ["fire", "water"]


def test_validated_sv_starter_deckbuilder_serves_all_decks():
    assert list_sv_starter_decks() == sorted(SV_STARTER_DECK_BUILDERS)

    for deck_name in list_sv_starter_decks():
        deck, strategy = build_sv_starter_deck(deck_name)
        summary = analyze_pokemon_deck_quality(deck, role=strategy["role"])
        assert len(deck) == 60
        assert strategy["deck"] == deck_name
        assert strategy["role"] == "starter"
        assert not summary["quality_flags"]
        assert deck is not build_sv_starter_deck(deck_name, enforce_quality=False)[0]


def test_validated_sv_starter_deckbuilder_rejects_unknown_decks():
    with pytest.raises(ValueError, match="Unknown Pokemon starter deck"):
        build_sv_starter_deck("not_a_deck")
