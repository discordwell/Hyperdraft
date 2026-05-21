"""Integration tests for the Pipeline-the-Game REST routes.

Uses FastAPI's TestClient against the live app instance from
`src/server/main.py`. Each test exercises one observable endpoint
behavior; together they cover the full play loop without spinning up
uvicorn.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python tests/test_pipeline_server.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from src.server.main import app


client = TestClient(app)


def test_start_returns_match_id_and_player_id():
    r = client.post("/api/pipeline/start", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["match_id"].startswith("HD-")
    assert len(data["match_id"]) == 7  # HD-XXXX
    assert data["player_id"] == "player_a"
    snap = data["snapshot"]
    assert snap["phase"] == "slot"
    assert snap["tricks"] == {"player_a": 0, "player_b": 0}
    assert len(snap["hands"]["player_a"]) == 8
    print("✓ /pipeline/start returns HD-XXXX match + opening hands of 8")


def test_play_then_resolve_advances_state():
    r = client.post("/api/pipeline/start", json={"rng_seed": 42})
    assert r.status_code == 200
    data = r.json()
    match_id = data["match_id"]
    hand = data["snapshot"]["hands"]["player_a"]
    # Find a RESOLVE card (manager guarantees the AI plays one too).
    resolve_card = next((c for c in hand if c["stage"] == "RESOLVE"), None)
    assert resolve_card is not None, "starting hand should include a RESOLVE card"
    play = client.post(
        f"/api/pipeline/{match_id}/play",
        json={"player_id": "player_a", "card_id": resolve_card["id"]},
    )
    assert play.status_code == 200, play.text
    body = play.json()
    assert body["trick_resolved"] is True
    assert body["resolution"] is not None
    assert body["resolution"]["winner"] in {"player_a", "player_b", None}
    # After resolve, slots cleared + new event drawn
    snap = body["snapshot"]
    if snap["phase"] != "won":
        assert all(v is None for v in snap["slots"]["player_a"].values()), (
            "player_a slots should be cleared after trick resolves"
        )
    print(f"✓ /pipeline/{{id}}/play resolves a trick (winner={body['resolution']['winner']})")


def test_get_state_returns_current_snapshot():
    r = client.post("/api/pipeline/start", json={"rng_seed": 7})
    match_id = r.json()["match_id"]
    g = client.get(f"/api/pipeline/{match_id}")
    assert g.status_code == 200
    assert g.json()["match_id"] == match_id
    print("✓ GET /pipeline/{id} returns the live snapshot")


def test_unknown_match_returns_404():
    g = client.get("/api/pipeline/HD-XXXX")
    assert g.status_code == 404
    print("✓ unknown match id → 404")


def test_reshuffle_resets_match():
    r = client.post("/api/pipeline/start", json={"rng_seed": 1})
    match_id = r.json()["match_id"]
    # Burn through several tricks.
    for _ in range(3):
        snap = client.get(f"/api/pipeline/{match_id}").json()
        if snap["phase"] == "won":
            break
        hand = snap["hands"]["player_a"]
        card = next((c for c in hand if c["stage"] == "RESOLVE"), hand[0])
        client.post(
            f"/api/pipeline/{match_id}/play",
            json={"player_id": "player_a", "card_id": card["id"]},
        )
    re = client.post(f"/api/pipeline/{match_id}/reshuffle")
    assert re.status_code == 200
    fresh = re.json()
    assert fresh["match_id"] == match_id
    assert fresh["snapshot"]["tricks"] == {"player_a": 0, "player_b": 0}
    assert fresh["snapshot"]["turn"] == 0
    print("✓ /pipeline/{id}/reshuffle resets tricks/turn but keeps match_id")


def test_invalid_card_id_returns_400():
    r = client.post("/api/pipeline/start", json={"rng_seed": 99})
    match_id = r.json()["match_id"]
    bad = client.post(
        f"/api/pipeline/{match_id}/play",
        json={"player_id": "player_a", "card_id": "not-a-real-card"},
    )
    assert bad.status_code == 400
    print("✓ unknown card id → 400")


def main():
    test_start_returns_match_id_and_player_id()
    test_play_then_resolve_advances_state()
    test_get_state_returns_current_snapshot()
    test_unknown_match_returns_404()
    test_reshuffle_resets_match()
    test_invalid_card_id_returns_400()
    print("\nALL pipeline-server tests passed.")


if __name__ == "__main__":
    main()
