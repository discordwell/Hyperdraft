from pathlib import Path

from scripts.play import pokemon_spice_loop
from src.cards.pokemon.beyond.ravnica import (
    BRV_SYNERGY_PACKAGES,
    brv_synergy_package_errors,
    list_ravnica_guild_decks,
)


def test_pokemon_spice_loop_plans_cover_all_brv_guilds_and_focals():
    planned_guilds = {plan["guild"] for plan in pokemon_spice_loop.ITERATION_PLANS}
    planned_focals = {plan["focal"] for plan in pokemon_spice_loop.ITERATION_PLANS}

    assert planned_guilds == set(list_ravnica_guild_decks())
    assert planned_focals == set(BRV_SYNERGY_PACKAGES)
    assert brv_synergy_package_errors() == []


def test_summarize_brv_deckbuilding_pass_tracks_partner_coverage():
    summary = pokemon_spice_loop.summarize_brv_deckbuilding_pass(
        "izzet",
        "Niv-Mizzet, Parun ex",
    )

    assert summary["focal_copies"] == 2
    assert summary["partners_present"] >= 8
    assert "Crackling Drake" in summary["missing_partners"]
    assert summary["profile"]["balance_flags"] == []
    assert summary["action"] == "hold_current_deck_shape"


def test_pokemon_spice_loop_writes_iteration_logs_with_mocked_games(tmp_path: Path, monkeypatch):
    async def fake_variant_pass(**kwargs):
        pokemon_spice_loop.write_json(kwargs["out_path"], {"fake": "variant"})
        kwargs["report_path"].write_text("fake report\n", encoding="utf-8")
        return {
            "path": str(kwargs["out_path"]),
            "report_path": str(kwargs["report_path"]),
            "totals": {"games": 1, "draws": 0, "errors": 0, "winner_reasons": {"max_turns": 1}},
            "ranking": [{"variant": kwargs["variants"][0], "winrate": 1.0, "wins": 1, "games": 1}],
        }

    async def fake_mirror_pass(**kwargs):
        pokemon_spice_loop.write_json(kwargs["out_path"], {"fake": "mirror"})
        return {
            "path": str(kwargs["out_path"]),
            "mode": "deterministic_fallback_smoke",
            "actions": kwargs["max_actions"],
            "validation_failure_count": 0,
            "summary": {"game_over": False},
        }

    monkeypatch.setattr(pokemon_spice_loop, "_run_variant_pass", fake_variant_pass)
    monkeypatch.setattr(pokemon_spice_loop, "_run_mirror_pass", fake_mirror_pass)

    out_dir = tmp_path / "pokemon_spice_loop_test"
    summary = pokemon_spice_loop.run_loop(
        iterations=1,
        seed=7,
        out_dir=out_dir,
        variants=["hard", "ultra"],
        tournament_games=1,
        max_turns=2,
        mirror_max_actions=3,
    )

    assert summary["schema_version"] == "hyperdraft.pokemon_spice_loop.v1"
    assert len(summary["iterations"]) == 1
    assert summary["live_subagent_validation_count"] == 0
    assert summary["fallback_validation_count"] == 1
    assert summary["mirror_execution_mode"] == "deterministic_fallback_smoke"
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    assert any(path.name.startswith("iteration_01_izzet") for path in out_dir.iterdir())
