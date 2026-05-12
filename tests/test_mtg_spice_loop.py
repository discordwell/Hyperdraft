from pathlib import Path

from scripts.play import mtg_spice_loop
from scripts.play.capability_test import _load_synergy_registry, build_synergy_deck
from scripts.play.custom_set_tournament import build_set_deck
from src.cards.custom import CUSTOM_SETS


def test_summarize_deckbuilding_pass_forces_focal_and_partners():
    cards = CUSTOM_SETS["PKH"]
    registry = _load_synergy_registry("PKH")
    focal = "Pikachu, Thunder Champion"
    partners = registry[focal]
    baseline, _ = build_set_deck("PKH", cards)
    synergy = build_synergy_deck(focal, partners, cards)

    summary = mtg_spice_loop.summarize_deckbuilding_pass(
        set_code="PKH",
        focal=focal,
        partners=partners,
        baseline_deck=baseline,
        synergy_deck=synergy,
    )

    assert summary["synergy_focal_copies"] == 4
    assert summary["partners_in_synergy_deck"] >= 2
    assert summary["spell_count"] == 36
    assert summary["land_count"] == 24
    assert focal in summary["top_additions_vs_baseline"]


def test_balance_classification_flags_low_cast_rate_before_card_tuning():
    action = mtg_spice_loop.classify_balance_action(
        capability={
            "errors": 0,
            "capability_score": 0.0,
            "focal_cast_per_game": 0.0,
        },
        tournament={
            "results": [],
            "synergy_match_winrate": 0.5,
        },
        deckbuilding={
            "synergy_focal_copies": 4,
            "functional_nonland_ratio": 0.8,
        },
    )

    assert action["action"] == "lower_cost_or_add_mana_support"


def test_run_loop_writes_iteration_logs_with_mocked_games(tmp_path: Path, monkeypatch):
    def fake_capability(**kwargs):
        return {
            "focal": kwargs["focal_name"],
            "set": kwargs["set_code"],
            "games_run": kwargs["games"],
            "wins": 1,
            "losses": 0,
            "draws": 0,
            "errors": 0,
            "synergy_deck_winrate": 1.0,
            "focal_cast_per_copy": 0.25,
            "focal_cast_per_game": 1.0,
            "focal_win_rate_in_play": 1.0,
            "focal_is_permanent": True,
            "capability_score": 1.0,
            "focal_dmg_per_game": 0.0,
            "focal_kills_per_game": 0.0,
            "passed_threshold": True,
            "elapsed_s": 0.0,
            "synergy_partners_used": list(kwargs["synergy_partners"]),
            "synergy_partners_missing": [],
        }

    def fake_tournament(**kwargs):
        focal = kwargs["focal"]
        return {
            "domains": ["PKH_syn", "PKH_baseline"],
            "games_per_pair": kwargs["games"],
            "max_turns": kwargs["max_turns"],
            "difficulty": kwargs["difficulty"],
            "pilot_map": {"PKH_syn": "aggro", "PKH_baseline": "midrange"},
            "substitution": "test substitute",
            "results": [],
            "aggregate": {"set_summary": {}, "matchup": {}, "card_scores": {}},
            "report": f"report for {focal}",
            "synergy_label": "PKH_syn",
            "baseline_label": "PKH_baseline",
            "synergy_match_winrate": 0.5,
        }

    def fake_mirror(**kwargs):
        out_path = kwargs["out_path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('{"schema_version":"test"}\n', encoding="utf-8")
        return {
            "schema_version": "hyperdraft.mtg_spice_loop.mirror.v1",
            "mode": "deterministic_fallback",
            "live_subagents_used": False,
            "fallback_actions": kwargs["max_actions"],
            "actions": kwargs["max_actions"],
            "invalid_actions": 0,
            "engine_errors": 0,
            "transcript_path": str(out_path),
            "summary": {},
            "note": "test mirror",
        }

    monkeypatch.setattr(mtg_spice_loop, "run_capability_test", fake_capability)
    monkeypatch.setattr(mtg_spice_loop, "run_two_pilot_substitute", fake_tournament)
    monkeypatch.setattr(mtg_spice_loop, "run_mirror_validation", fake_mirror)

    out_dir = tmp_path / "mtg_spice_loop_test"
    mirror_dir = tmp_path / "mtg_codex_test"
    summary = mtg_spice_loop.run_loop(
        set_code="PKH",
        iterations=2,
        capability_games=1,
        tournament_games=1,
        max_turns=4,
        difficulty="hard",
        seed=7,
        out_dir=out_dir,
        mirror_dir=mirror_dir,
        focals=["Pikachu, Thunder Champion", "Hyper Beam"],
        mirror_actions=2,
        skip_llm_check=True,
    )

    assert summary["schema_version"] == "hyperdraft.mtg_spice_loop.v2"
    assert len(summary["iterations"]) == 2
    assert summary["iterations"][0]["mirror"]["actions"] == 2
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    assert any(path.name.startswith("iteration_01") for path in mirror_dir.iterdir())
    assert any(path.name.startswith("iteration_01") for path in out_dir.iterdir())
