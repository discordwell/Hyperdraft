import argparse

import pytest

from src.cards.minecraft import MINECRAFT_CARDS
from src.engine.game import Game


def test_mc_wet_test_start_establishes_active_turn(tmp_path, monkeypatch, capsys):
    pytest.importorskip("dill")
    from scripts.play import mc_wet_test

    monkeypatch.setattr(mc_wet_test, "STATE_PATH", str(tmp_path / "mc_wet_test_state.pkl"))
    args = argparse.Namespace(
        my_deck="builder",
        ai_deck="raider",
        ai_bias="passive_econ",
        decks_file=None,
        two_pilot=False,
    )

    mc_wet_test.cmd_start(args)
    payload = mc_wet_test._load()
    output = capsys.readouterr().out

    assert payload["game"].state.active_player in {payload["p1_id"], payload["p2_id"]}
    assert payload["game"].state.turn_number >= 1
    assert payload["history"]
    assert "Turn 0" not in output
    assert "active=None" not in output


def test_mc_wet_test_two_pilot_end_turn_keeps_p2_manual(tmp_path, monkeypatch, capsys):
    pytest.importorskip("dill")
    from scripts.play import mc_wet_test

    class ExplodingAI:
        async def take_turn(self, *_args, **_kwargs):
            raise AssertionError("two-pilot P2 must not run AI")

    monkeypatch.setattr(mc_wet_test, "STATE_PATH", str(tmp_path / "mc_wet_test_state.pkl"))
    args = argparse.Namespace(
        my_deck="builder",
        ai_deck="raider",
        ai_bias="passive_econ",
        decks_file=None,
        two_pilot=True,
    )

    mc_wet_test.cmd_start(args)
    payload = mc_wet_test._load()
    game = payload["game"]
    p2_id = payload["p2_id"]
    assert p2_id not in game.turn_manager.ai_players

    # Simulate an older/regressed saved two-pilot state where P2 was still
    # registered as AI. end_turn must clear that before opening P2's turn.
    game.turn_manager.set_ai_player(p2_id)
    game.turn_manager.set_ai_handler(ExplodingAI())
    mc_wet_test._save(payload)

    mc_wet_test.cmd_end_turn(argparse.Namespace())
    payload = mc_wet_test._load()
    output = capsys.readouterr().out

    assert payload["game"].state.active_player == p2_id
    assert p2_id not in payload["game"].turn_manager.ai_players
    assert not any(actor == "AI" and action == "took turn" for _, actor, action in payload["history"])
    assert "YOUR turn — seat=P2" in output


def test_mc_wet_test_one_pilot_end_turn_still_runs_ai(tmp_path, monkeypatch, capsys):
    pytest.importorskip("dill")
    from scripts.play import mc_wet_test

    monkeypatch.setattr(mc_wet_test, "STATE_PATH", str(tmp_path / "mc_wet_test_state.pkl"))
    args = argparse.Namespace(
        my_deck="builder",
        ai_deck="raider",
        ai_bias="passive_econ",
        decks_file=None,
        two_pilot=False,
    )

    mc_wet_test.cmd_start(args)
    payload = mc_wet_test._load()
    assert payload["p2_id"] in payload["game"].turn_manager.ai_players

    mc_wet_test.cmd_end_turn(argparse.Namespace())
    payload = mc_wet_test._load()
    capsys.readouterr()

    assert any(actor == "AI" and action == "took turn" for _, actor, action in payload["history"])
    assert any(actor == "ME" and action == "begin of turn (auto)" for _, actor, action in payload["history"])


def test_capability_focal_in_opener_hook_can_target_p2_seat():
    from scripts.play.minecraft_capability_test import _make_stack_focal_hook

    game = Game(mode="minecraft")
    p1 = game.add_player("baseline")
    p2 = game.add_player("synergy")
    game.setup_minecraft_player(
        p1,
        [MINECRAFT_CARDS["Bed"], MINECRAFT_CARDS["Crafting Table"], MINECRAFT_CARDS["Furnace"]],
    )
    game.setup_minecraft_player(
        p2,
        [MINECRAFT_CARDS["Bed"], MINECRAFT_CARDS["Crafting Table"], MINECRAFT_CARDS["Breeze"]],
    )

    hook = _make_stack_focal_hook("Breeze", target_seat="p2")
    hook(game, p1.id, p2.id)

    p1_top = game.state.zones[f"library_{p1.id}"].objects[0]
    p2_top = game.state.zones[f"library_{p2.id}"].objects[0]
    assert game.state.objects[p1_top].name == "Bed"
    assert game.state.objects[p2_top].name == "Breeze"
