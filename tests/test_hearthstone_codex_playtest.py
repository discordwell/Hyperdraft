import asyncio
import json
import subprocess
import sys

from scripts.play.hearthstone_codex_match import (
    apply_action_id,
    apply_player_json,
    current_packet,
    initialize_referee,
    parse_player_json,
    run_fallback_match,
)
from src.engine.hearthstone_legal_actions import (
    legal_hearthstone_actions,
    validate_hearthstone_action,
    visible_hearthstone_packet,
)
from src.engine.types import Characteristics, ZoneType


def _referee():
    return asyncio.run(
        initialize_referee(
            p1_deck="stormrift_pyromancer",
            p2_deck="stormrift_cryomancer",
            seed=123,
        )
    )


def test_hearthstone_codex_packet_hides_opponent_hand_and_library_names():
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

    packet = asyncio.run(current_packet(referee))
    raw = json.dumps(packet)

    assert packet["seat"] in {"P1", "P2"}
    assert "OPPONENT SECRET DO NOT LEAK" not in raw
    assert "OPPONENT LIBRARY SECRET DO NOT LEAK" not in raw
    assert "hand_count" in packet["opponent"]
    assert "library_count" in packet["opponent"]
    assert "hand" not in packet["opponent"]


def test_hearthstone_codex_legal_actions_validate_and_apply():
    referee = _referee()
    p1 = referee.player_ids[0]
    asyncio.run(current_packet(referee))
    actions = legal_hearthstone_actions(referee.game, p1)

    assert actions
    assert actions[-1]["type"] == "HS_END_TURN"
    assert validate_hearthstone_action(referee.game, p1, actions[0]["id"])["ok"]
    assert not validate_hearthstone_action(referee.game, p1, "missing")["ok"]

    action = next((a for a in actions if a["type"] != "HS_END_TURN"), actions[-1])
    entry = asyncio.run(apply_action_id(referee, action["id"], rationale="test", source="live_codex"))

    assert entry["validation"] is True
    assert entry["source"] == "live_codex"
    assert entry["action"]["type"] == action["type"]


def test_hearthstone_codex_invalid_player_json_has_fallback_path():
    referee = _referee()
    packet = asyncio.run(current_packet(referee))

    action_id, rationale, error = parse_player_json("not json", packet["legal_actions"])
    assert action_id is None
    assert error and "Invalid JSON" in error

    action_id, rationale, error = parse_player_json('{"action_id":"missing","rationale":"x"}', packet["legal_actions"])
    assert action_id == "missing"
    assert error and "Illegal action_id" in error

    entry = asyncio.run(apply_player_json(referee, "not json"))
    assert entry["source"] == "deterministic_fallback"
    assert entry["fallback_reason"]
    assert entry["validation"] is True


def test_hearthstone_codex_fallback_match_is_deterministic():
    left = asyncio.run(
        run_fallback_match(
            p1_deck="stormrift_pyromancer",
            p2_deck="stormrift_cryomancer",
            seed=999,
            max_actions=8,
        )
    )
    right = asyncio.run(
        run_fallback_match(
            p1_deck="stormrift_pyromancer",
            p2_deck="stormrift_cryomancer",
            seed=999,
            max_actions=8,
        )
    )

    left_actions = [(entry["deck"], entry["selected_action_id"], entry["action"]["label"]) for entry in left.transcript]
    right_actions = [(entry["deck"], entry["selected_action_id"], entry["action"]["label"]) for entry in right.transcript]
    assert left_actions == right_actions
    assert len(left.transcript) == 8


def test_hearthstone_codex_smoke_script_writes_transcript(tmp_path):
    out = tmp_path / "hearthstone_codex_smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.play.hearthstone_codex_match",
            "smoke",
            "--p1-deck",
            "stormrift_pyromancer",
            "--p2-deck",
            "stormrift_cryomancer",
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
    assert report["schema_version"] == "hyperdraft.hearthstone_codex_match.v1"
    assert len(report["transcript"]) == 4
    assert report["decision_counts"]["deterministic_fallback"] == 4
    assert "summary" in result.stdout
