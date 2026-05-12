import asyncio
import json
import subprocess
import sys

from src.engine.game import make_creature, make_land
from src.engine.types import Characteristics, Color, ZoneType
from src.engine.mtg_legal_actions import legal_mtg_actions, validate_mtg_action
from scripts.play.mtg_codex_match import (
    apply_action_id,
    current_packet,
    initialize_referee_from_decks,
    parse_player_json,
    run_fallback_match_from_decks,
)


def _test_deck(prefix: str):
    mountain = make_land(name=f"{prefix} Mountain", subtypes={"Mountain"}, supertypes={"Basic"})
    scout = make_creature(
        name=f"{prefix} Ember Scout",
        power=2,
        toughness=1,
        mana_cost="{R}",
        colors={Color.RED},
        subtypes={"Human", "Scout"},
    )
    brute = make_creature(
        name=f"{prefix} Hill Brute",
        power=3,
        toughness=3,
        mana_cost="{2}{R}",
        colors={Color.RED},
        subtypes={"Giant"},
    )
    return [mountain] * 28 + [scout] * 20 + [brute] * 12


def _referee():
    return asyncio.run(initialize_referee_from_decks(
        p1_deck=_test_deck("P1"),
        p2_deck=_test_deck("P2"),
        p1_deck_id="test:p1",
        p2_deck_id="test:p2",
        seed=123,
    ))


def test_mtg_codex_packet_hides_opponent_hand_and_library_contents():
    referee = _referee()
    p1, p2 = referee.player_ids
    referee.game.create_object(
        name="OPPONENT SECRET DO NOT LEAK",
        owner_id=p2,
        zone=ZoneType.HAND,
        characteristics=Characteristics(),
    )
    referee.game.create_object(
        name="OPPONENT LIBRARY SECRET DO NOT LEAK",
        owner_id=p2,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(),
    )

    packet = current_packet(referee)
    raw = json.dumps(packet)

    assert packet["seat"] == p1
    assert "OPPONENT SECRET DO NOT LEAK" not in raw
    assert "OPPONENT LIBRARY SECRET DO NOT LEAK" not in raw
    assert "hand_count" in packet["opponent"]
    assert "library_count" in packet["opponent"]
    assert "hand" not in packet["opponent"]


def test_mtg_codex_legal_actions_validate_and_apply():
    referee = _referee()
    p1 = referee.player_ids[0]
    current_packet(referee)
    actions = legal_mtg_actions(referee.game, p1)

    assert actions
    assert actions[0]["type"] == "MTG_PASS"
    assert validate_mtg_action(referee.game, p1, actions[0]["id"])["ok"]
    assert not validate_mtg_action(referee.game, p1, "missing")["ok"]

    action = next((a for a in actions if a["type"] != "MTG_PASS"), actions[0])
    entry = asyncio.run(apply_action_id(referee, action["id"], rationale="test"))

    assert entry["validation"] is True
    assert entry["engine_ok"] is True
    assert entry["action"]["type"] == action["type"]


def test_mtg_codex_invalid_player_json_and_action_use_fallback_path():
    referee = _referee()
    packet = current_packet(referee)

    action_id, rationale, error = parse_player_json("not json", packet["legal_actions"])
    assert action_id is None
    assert error and "Invalid JSON" in error

    action_id, rationale, error = parse_player_json('{"action_id":"missing","rationale":"x"}', packet["legal_actions"])
    assert action_id == "missing"
    assert error and "Illegal action_id" in error

    entry = asyncio.run(apply_action_id(referee, "missing", rationale="bad", source="test"))
    assert entry["validation"] is False
    assert entry["fallback_action_id"]
    assert entry["action"]["type"] == "MTG_PASS"


def test_mtg_codex_fallback_match_is_deterministic():
    left = asyncio.run(run_fallback_match_from_decks(
        p1_deck=_test_deck("P1"),
        p2_deck=_test_deck("P2"),
        p1_deck_id="test:p1",
        p2_deck_id="test:p2",
        seed=999,
        max_actions=8,
    ))
    right = asyncio.run(run_fallback_match_from_decks(
        p1_deck=_test_deck("P1"),
        p2_deck=_test_deck("P2"),
        p1_deck_id="test:p1",
        p2_deck_id="test:p2",
        seed=999,
        max_actions=8,
    ))

    left_actions = [(entry["deck"], entry["selected_action_id"], entry["action"]["label"]) for entry in left.transcript]
    right_actions = [(entry["deck"], entry["selected_action_id"], entry["action"]["label"]) for entry in right.transcript]
    assert left_actions == right_actions
    assert len(left.transcript) == 8


def test_mtg_codex_smoke_script_writes_transcript(tmp_path):
    out = tmp_path / "mtg_codex_smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.play.mtg_codex_match",
            "smoke",
            "--set",
            "PKH",
            "--focal",
            "Pikachu, Thunder Champion",
            "--seed",
            "321",
            "--max-actions",
            "4",
            "--out",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    assert out.exists()
    report = json.loads(out.read_text())
    assert report["schema_version"] == "hyperdraft.mtg_codex_match.v1"
    assert len(report["transcript"]) == 4
    assert report["live_subagents_used"] is False
    assert "summary" in result.stdout
