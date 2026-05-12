import asyncio
import json
import subprocess
import sys

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import ZoneType
from src.engine.yugioh_legal_actions import (
    legal_yugioh_actions,
    validate_yugioh_action,
)
from scripts.play.yugioh_codex_match import (
    apply_action_id,
    current_packet,
    initialize_referee,
    parse_player_json,
    run_fallback_match,
)


def _referee():
    return asyncio.run(initialize_referee(
        p1_deck="chain_burn",
        p2_deck="kamigawa:ninja",
        seed=123,
    ))


def test_yugioh_codex_packet_hides_opponent_hand_library_and_set_cards():
    referee = _referee()
    seat = referee.player_ids[referee.active_index]
    opponent = next(pid for pid in referee.player_ids if pid != seat)
    secret_spell = make_ygo_spell("OPPONENT SECRET DO NOT LEAK")
    secret_set = make_ygo_trap("OPPONENT SET SECRET DO NOT LEAK")
    secret_monster = make_ygo_monster("OPPONENT MONSTER SECRET DO NOT LEAK", 100, 100)

    referee.game.create_object(
        name=secret_spell.name,
        owner_id=opponent,
        zone=ZoneType.HAND,
        characteristics=secret_spell.characteristics,
        card_def=secret_spell,
    )
    set_obj = referee.game.create_object(
        name=secret_set.name,
        owner_id=opponent,
        zone=ZoneType.SPELL_TRAP_ZONE,
        characteristics=secret_set.characteristics,
        card_def=secret_set,
    )
    set_obj.state.face_down = True
    facedown = referee.game.create_object(
        name=secret_monster.name,
        owner_id=opponent,
        zone=ZoneType.MONSTER_ZONE,
        characteristics=secret_monster.characteristics,
        card_def=secret_monster,
    )
    facedown.state.face_down = True
    facedown.state.ygo_position = "face_down_def"

    packet = current_packet(referee)
    raw = json.dumps(packet)

    assert packet["seat"] == seat
    assert "OPPONENT SECRET DO NOT LEAK" not in raw
    assert "OPPONENT SET SECRET DO NOT LEAK" not in raw
    assert "OPPONENT MONSTER SECRET DO NOT LEAK" not in raw
    assert "hand_count" in packet["opponent"]
    assert "library_count" in packet["opponent"]
    assert "hand" not in packet["opponent"]
    assert "Set Spell/Trap" in raw
    assert "Face-down Monster" in raw


def test_yugioh_codex_legal_actions_validate_and_apply():
    referee = _referee()
    player_id = referee.player_ids[referee.active_index]
    current_packet(referee)
    actions = legal_yugioh_actions(referee.game, player_id)

    assert actions
    assert actions[-1]["type"] == "YGO_END_TURN"
    assert validate_yugioh_action(referee.game, player_id, actions[0]["id"])["ok"]
    assert not validate_yugioh_action(referee.game, player_id, "missing")["ok"]

    action = next((a for a in actions if a["type"] != "YGO_END_TURN"), actions[-1])
    entry = asyncio.run(apply_action_id(referee, action["id"], rationale="test"))

    assert entry["validation"] is True
    assert entry["engine_ok"] is True
    assert entry["action"]["type"] == action["type"]


def test_yugioh_codex_invalid_player_json_has_fallback_path():
    referee = _referee()
    packet = current_packet(referee)

    action_id, rationale, error = parse_player_json("not json", packet["legal_actions"])
    assert action_id is None
    assert error and "Invalid JSON" in error

    action_id, rationale, error = parse_player_json('{"action_id":"missing","rationale":"x"}', packet["legal_actions"])
    assert action_id == "missing"
    assert error and "Illegal action_id" in error


def test_yugioh_codex_fallback_match_is_deterministic():
    left = asyncio.run(run_fallback_match(
        p1_deck="chain_burn",
        p2_deck="kamigawa:ninja",
        seed=999,
        max_actions=8,
    ))
    right = asyncio.run(run_fallback_match(
        p1_deck="chain_burn",
        p2_deck="kamigawa:ninja",
        seed=999,
        max_actions=8,
    ))

    left_actions = [(entry["deck"], entry["selected_action_id"], entry["action"]["label"]) for entry in left.transcript]
    right_actions = [(entry["deck"], entry["selected_action_id"], entry["action"]["label"]) for entry in right.transcript]
    assert left_actions == right_actions
    assert len(left.transcript) == 8


def test_yugioh_codex_smoke_script_writes_transcript(tmp_path):
    out = tmp_path / "yugioh_codex_smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.play.yugioh_codex_match",
            "smoke",
            "--p1-deck",
            "chain_burn",
            "--p2-deck",
            "kamigawa:ninja",
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
    assert report["schema_version"] == "hyperdraft.yugioh_codex_match.v1"
    assert len(report["transcript"]) == 4
    assert "summary" in result.stdout
