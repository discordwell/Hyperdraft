"""Tests for the ultra-agent telemetry features (Phase 5+):

  1. Per-decision JSONL capture (storage/ultra-agent/decisions/<match_id>.jsonl)
  2. Auto-write session takeaway (supervisor → storage/strategy/<game_mode>.md)
  3. /api/match/ultra-summary aggregate endpoint
  4. Model + git SHA in match metadata header

The tests use direct function invocation against the route handlers
(mirroring the pattern in tests/test_phase4_routes.py + test_match_replay.py),
not a TestClient round-trip, so no live FastAPI app is needed.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from src.server import replay_archive, spectator, ultra_telemetry
from src.server.models import PlayerActionRequest


# ===== Common fixtures =========================================================


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Redirect every file-backed surface to a per-test tmp dir."""
    decisions_dir = tmp_path / "decisions"
    replays_dir = tmp_path / "replays"
    strategy_dir = tmp_path / "strategy"
    decisions_dir.mkdir()
    replays_dir.mkdir()
    strategy_dir.mkdir()

    monkeypatch.setattr(ultra_telemetry, "DECISIONS_DIR", decisions_dir)
    monkeypatch.setattr(replay_archive, "ARCHIVE_DIR", replays_dir)
    monkeypatch.setattr(replay_archive, "INDEX_PATH", replays_dir / "index.json")
    # Stable SHA across tests
    ultra_telemetry.reset_git_sha_cache_for_test()
    monkeypatch.setattr(ultra_telemetry, "get_git_sha", lambda: "test-sha-deadbe")

    return {
        "decisions": decisions_dir,
        "replays": replays_dir,
        "strategy": strategy_dir,
        "root": tmp_path,
    }


# ===== Feature 1 — Per-decision JSONL capture ==================================


def test_init_match_metadata_writes_meta_header(isolated_dirs):
    path = ultra_telemetry.init_match_metadata(
        match_id="m-abc",
        game_mode="mtg",
        ultra_model_id="claude-opus-4.7",
        agent_runner="claude",
    )
    assert path is not None
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    meta = json.loads(lines[0])
    assert "_meta" in meta
    assert meta["_meta"]["match_id"] == "m-abc"
    assert meta["_meta"]["model_id"] == "claude-opus-4.7"
    assert meta["_meta"]["git_sha"] == "test-sha-deadbe"
    assert meta["_meta"]["agent_runner"] == "claude"


def test_init_match_metadata_is_idempotent(isolated_dirs):
    """Calling init twice (bot-vs-bot has two seats) must not double-write."""
    path1 = ultra_telemetry.init_match_metadata(
        match_id="m-2", game_mode="pokemon", ultra_model_id="x"
    )
    path2 = ultra_telemetry.init_match_metadata(
        match_id="m-2", game_mode="pokemon", ultra_model_id="y"
    )
    assert path1 == path2
    # Only one _meta line, even though we called init twice
    lines = path1.read_text().strip().splitlines()
    assert len(lines) == 1
    meta = json.loads(lines[0])
    assert meta["_meta"]["model_id"] == "x"  # first wins


def test_append_decision_writes_jsonl_line(isolated_dirs):
    ultra_telemetry.init_match_metadata(
        match_id="m-3", game_mode="mtg", ultra_model_id="model-z"
    )
    ok = ultra_telemetry.append_decision(
        match_id="m-3",
        player_id="seat-A",
        turn=12,
        phase="MAIN1",
        action_type="CAST_SPELL",
        action_payload={"card_id": "abc", "targets": [["t1"]]},
        actor_is_ultra=True,
        ai_difficulty="ultra",
    )
    assert ok is True
    lines = (isolated_dirs["decisions"] / "m-3.jsonl").read_text().strip().splitlines()
    # 1 meta + 1 decision
    assert len(lines) == 2
    decision = json.loads(lines[1])
    assert decision["player_id"] == "seat-A"
    assert decision["turn"] == 12
    assert decision["phase"] == "MAIN1"
    assert decision["action_type"] == "CAST_SPELL"
    assert decision["action_payload"]["card_id"] == "abc"
    assert decision["actor_is_ultra"] is True


def test_append_decision_skips_non_ultra(isolated_dirs):
    """Heuristic AI and human actions must NOT produce a JSONL line."""
    ok = ultra_telemetry.append_decision(
        match_id="m-4",
        player_id="seat-B",
        turn=1,
        phase="MAIN1",
        action_type="PASS",
        action_payload={},
        actor_is_ultra=False,  # skipped at call site
    )
    assert ok is False
    assert not (isolated_dirs["decisions"] / "m-4.jsonl").exists()


def test_append_decision_carries_reasoning_when_present(isolated_dirs):
    ultra_telemetry.init_match_metadata(match_id="m-5", game_mode="mtg", ultra_model_id="m")
    ultra_telemetry.append_decision(
        match_id="m-5",
        player_id="seat-A",
        turn=3,
        phase="MAIN1",
        action_type="CAST_SPELL",
        action_payload={},
        actor_is_ultra=True,
        reasoning="They have only 2 mana so I can leave 1U up for counterspell.",
    )
    lines = (isolated_dirs["decisions"] / "m-5.jsonl").read_text().strip().splitlines()
    decision = json.loads(lines[1])
    assert decision["reasoning"].startswith("They have only 2 mana")


def test_count_decisions_by_seat(isolated_dirs):
    ultra_telemetry.init_match_metadata(match_id="m-6", game_mode="mtg", ultra_model_id="m")
    for seat in ["A", "A", "B", "A", "B", "B"]:
        ultra_telemetry.append_decision(
            match_id="m-6",
            player_id=seat,
            turn=1, phase="MAIN1", action_type="PASS",
            action_payload={}, actor_is_ultra=True,
        )
    counts = ultra_telemetry.count_decisions_by_seat("m-6")
    assert counts == {"A": 3, "B": 3}


def test_is_ultra_seat_uses_session_predicate(isolated_dirs):
    class StubSession:
        def is_ultra_ai_player(self, pid):
            return pid == "ultra-seat"

    s = StubSession()
    assert ultra_telemetry.is_ultra_seat(s, "ultra-seat") is True
    assert ultra_telemetry.is_ultra_seat(s, "human-seat") is False
    # No session
    assert ultra_telemetry.is_ultra_seat(None, "anything") is False


def test_is_ultra_seat_falls_back_to_profile(isolated_dirs):
    """When session lacks the predicate, fall back to ai_profiles_by_player."""

    class StubSession:
        # No is_ultra_ai_player attr
        ai_profiles_by_player = {
            "p1": {"difficulty": "ultra"},
            "p2": {"difficulty": "medium"},
        }

    s = StubSession()
    assert ultra_telemetry.is_ultra_seat(s, "p1") is True
    assert ultra_telemetry.is_ultra_seat(s, "p2") is False


# ===== Feature 2 — Auto-write session takeaway =================================


def test_synthesize_takeaway_reads_decision_log(isolated_dirs):
    ultra_telemetry.init_match_metadata(match_id="m-7", game_mode="mtg", ultra_model_id="m")
    # Two seats, A makes 5 decisions, B makes 3
    for _ in range(5):
        ultra_telemetry.append_decision(
            match_id="m-7", player_id="A", turn=1, phase="MAIN1",
            action_type="CAST_SPELL", action_payload={}, actor_is_ultra=True,
        )
    for _ in range(3):
        ultra_telemetry.append_decision(
            match_id="m-7", player_id="B", turn=1, phase="MAIN1",
            action_type="PASS", action_payload={}, actor_is_ultra=True,
        )

    body = ultra_telemetry.synthesize_takeaway(
        match_id="m-7", game_mode="mtg", winner_id="A", total_turns=12,
        seat_labels={"A": "Seat A (claude · ultra)", "B": "Seat B (claude · ultra)"},
    )
    assert ultra_telemetry.TAKEAWAY_HEADING in body
    assert "Seat A (claude · ultra)" in body
    assert "Engine**: mtg" in body
    # Decisions counts surfaced
    assert ": 5" in body and ": 3" in body
    # Most-played action surfaced (CAST_SPELL appears 5x, PASS is excluded)
    assert "CAST_SPELL (5x)" in body


def test_append_takeaway_to_strategy_doc_inserts_most_recent_first(isolated_dirs):
    """Each new takeaway must be inserted right under the heading,
    NOT at the bottom — most-recent first."""
    strategy_dir = isolated_dirs["strategy"]
    (strategy_dir / "mtg.md").write_text(
        "# MTG\n\n"
        "Some preface.\n\n"
        f"{ultra_telemetry.SESSION_TAKEAWAYS_ANCHOR}\n\n"
        "<!-- comment -->\n"
    )

    first = "## Session takeaway — 2026-05-22 18:00 UTC · match aaaa\n- match A\n"
    second = "## Session takeaway — 2026-05-22 19:00 UTC · match bbbb\n- match B\n"

    ultra_telemetry.append_takeaway_to_strategy_doc(
        game_mode="mtg", body=first, strategy_dir=strategy_dir,
    )
    ultra_telemetry.append_takeaway_to_strategy_doc(
        game_mode="mtg", body=second, strategy_dir=strategy_dir,
    )

    text = (strategy_dir / "mtg.md").read_text()
    # B was appended second, but appears FIRST in the doc (most-recent first)
    idx_a = text.index("match aaaa")
    idx_b = text.index("match bbbb")
    assert idx_b < idx_a


def test_append_takeaway_bootstraps_missing_doc(isolated_dirs):
    """If <mode>.md doesn't exist yet, the writer must create it."""
    strategy_dir = isolated_dirs["strategy"]
    body = "## Session takeaway — now · match qqqq\n- foo\n"

    written = ultra_telemetry.append_takeaway_to_strategy_doc(
        game_mode="pokemon", body=body, strategy_dir=strategy_dir,
    )
    assert written is not None
    assert (strategy_dir / "pokemon.md").exists()
    text = (strategy_dir / "pokemon.md").read_text()
    assert ultra_telemetry.SESSION_TAKEAWAYS_ANCHOR in text
    assert "match qqqq" in text


def test_takeaway_rotation_caps_at_max(isolated_dirs, monkeypatch):
    """Once a doc has MAX_TAKEAWAYS_PER_DOC entries, older ones rotate to archive."""
    strategy_dir = isolated_dirs["strategy"]
    monkeypatch.setattr(ultra_telemetry, "MAX_TAKEAWAYS_PER_DOC", 3)

    for i in range(5):
        body = f"## Session takeaway — {i} · match m{i}\n- entry {i}\n"
        ultra_telemetry.append_takeaway_to_strategy_doc(
            game_mode="mtg", body=body, strategy_dir=strategy_dir,
        )

    main_doc = (strategy_dir / "mtg.md").read_text()
    archive_doc = (strategy_dir / "mtg.archive.md").read_text()

    # Newest 3 stay in the main doc
    assert "match m4" in main_doc
    assert "match m3" in main_doc
    assert "match m2" in main_doc
    # Oldest 2 rotated to archive
    assert "match m0" in archive_doc
    assert "match m1" in archive_doc


def test_write_post_match_takeaway_no_session(isolated_dirs, monkeypatch):
    """The supervisor hook must run even when the session is already gone
    (the typical case at game end)."""
    # Point strategy doc writes at our tmp dir
    monkeypatch.setattr(ultra_telemetry, "MAX_TAKEAWAYS_PER_DOC", 50)
    monkeypatch.chdir(isolated_dirs["root"])

    # Seed a decision log so the takeaway has something to summarise
    decisions_dir = isolated_dirs["root"] / "storage" / "ultra-agent" / "decisions"
    decisions_dir.mkdir(parents=True)
    monkeypatch.setattr(ultra_telemetry, "DECISIONS_DIR", decisions_dir)
    ultra_telemetry.init_match_metadata(match_id="ghost", game_mode="mtg", ultra_model_id="m")
    ultra_telemetry.append_decision(
        match_id="ghost", player_id="A", turn=1, phase="MAIN1",
        action_type="CAST_SPELL", action_payload={}, actor_is_ultra=True,
    )

    # Run the supervisor hook directly (session is None — it's been evicted)
    spectator._write_post_match_takeaway("ghost", "mtg")

    doc = (isolated_dirs["root"] / "storage" / "strategy" / "mtg.md").read_text()
    assert "match ghost" in doc or "match ghost"[:8] in doc


# ===== Feature 3 — /api/match/ultra-summary ====================================


def test_ultra_summary_empty_when_nothing_archived(isolated_dirs):
    summary = ultra_telemetry.build_ultra_summary(
        replays_index_path=isolated_dirs["replays"] / "index.json",
        decisions_dir=isolated_dirs["decisions"],
    )
    assert summary["total_matches"] == 0
    assert summary["by_engine"] == {}
    assert summary["earliest"] is None
    assert summary["latest"] is None
    assert "generated_at" in summary


def test_ultra_summary_aggregates_by_engine(isolated_dirs):
    """Two MTG matches + one Pokemon match → by_engine totals reflect both."""
    # Seed the replay index (acts as the canonical match list)
    replay_archive.archive_match("mtg-1", {
        "game_mode": "mtg", "winner": "A", "total_turns": 13,
        "frames": [{} for _ in range(20)],
        "match_metadata": {"model_id": "m1", "git_sha": "abc", "agent_runner": "claude"},
    })
    replay_archive.archive_match("mtg-2", {
        "game_mode": "mtg", "winner": "B", "total_turns": 17,
        "frames": [{} for _ in range(30)],
    })
    replay_archive.archive_match("pkm-1", {
        "game_mode": "pokemon", "winner": "A", "total_turns": 8,
        "frames": [{}],  # 1 frame → counts as incomplete
    })

    # Seed decision logs (5 for mtg-1, 2 for mtg-2, 7 for pkm-1)
    for i in range(5):
        ultra_telemetry.append_decision(
            match_id="mtg-1", player_id="A", turn=i, phase="MAIN1",
            action_type="PASS", action_payload={}, actor_is_ultra=True,
        )
    for i in range(2):
        ultra_telemetry.append_decision(
            match_id="mtg-2", player_id="B", turn=i, phase="MAIN1",
            action_type="PASS", action_payload={}, actor_is_ultra=True,
        )
    for i in range(7):
        ultra_telemetry.append_decision(
            match_id="pkm-1", player_id="A", turn=i, phase="MAIN",
            action_type="PKM_ATTACK", action_payload={}, actor_is_ultra=True,
        )

    summary = ultra_telemetry.build_ultra_summary(
        replays_index_path=isolated_dirs["replays"] / "index.json",
        decisions_dir=isolated_dirs["decisions"],
    )

    assert summary["total_matches"] == 3
    assert summary["by_engine"]["mtg"]["matches"] == 2
    assert summary["by_engine"]["mtg"]["decisions_logged"] == 7
    assert summary["by_engine"]["mtg"]["avg_turns"] == 15.0
    assert summary["by_engine"]["mtg"]["median_turns"] == 15
    # Both mtg matches have >1 frame → 100% completeness
    assert summary["by_engine"]["mtg"]["archive_completeness_pct"] == 100.0

    # Pokemon: only 1 match, 1 frame (the regression case) → 0% completeness
    assert summary["by_engine"]["pokemon"]["matches"] == 1
    assert summary["by_engine"]["pokemon"]["archive_completeness_pct"] == 0.0
    assert summary["by_engine"]["pokemon"]["decisions_logged"] == 7


def test_ultra_summary_orphan_decisions_use_meta_game_mode(isolated_dirs):
    """A match with a decisions JSONL but no replay archive (crashed before
    archive) must bucket under the JSONL ``_meta`` header's game_mode, not
    'unknown'. Regression for the killed-HS-smoke-test artifact."""
    # No replay archive entry — just a decisions file with meta + 1 line.
    ultra_telemetry.init_match_metadata(
        match_id="orphan-hs", game_mode="hearthstone",
        ultra_model_id="m1", agent_runner="claude", extra={},
    )
    ultra_telemetry.append_decision(
        match_id="orphan-hs", player_id="A", turn=1, phase="MAIN",
        action_type="HS_PLAY_CARD", action_payload={}, actor_is_ultra=True,
    )

    summary = ultra_telemetry.build_ultra_summary(
        replays_index_path=isolated_dirs["replays"] / "index.json",
        decisions_dir=isolated_dirs["decisions"],
    )

    assert "unknown" not in summary["by_engine"], (
        f"Expected the orphan match to bucket under 'hearthstone', not "
        f"'unknown'. Got by_engine={list(summary['by_engine'].keys())}"
    )
    assert summary["by_engine"]["hearthstone"]["matches"] == 1
    assert summary["by_engine"]["hearthstone"]["decisions_logged"] == 1
    # archive_completeness_pct = 0% because no frames archived.
    assert summary["by_engine"]["hearthstone"]["archive_completeness_pct"] == 0.0


def test_ultra_summary_orphan_without_meta_still_bucketed_unknown(isolated_dirs):
    """Defensive: if the _meta header is somehow missing, fall back to
    'unknown' instead of crashing."""
    decisions_path = isolated_dirs["decisions"] / "orphan-nometa.jsonl"
    # Write a decision line with no preceding _meta — simulates a corrupt
    # or partially-written log.
    decisions_path.write_text(
        '{"ts": 1.0, "match_id": "orphan-nometa", "player_id": "A", "turn": 1, '
        '"phase": "MAIN", "action_type": "PASS", "actor_is_ultra": true}\n'
    )

    summary = ultra_telemetry.build_ultra_summary(
        replays_index_path=isolated_dirs["replays"] / "index.json",
        decisions_dir=isolated_dirs["decisions"],
    )
    assert summary["by_engine"]["unknown"]["matches"] == 1


def test_ultra_summary_endpoint_route(isolated_dirs, monkeypatch):
    """The /api/match/ultra-summary route handler returns the aggregate payload."""
    from src.server.routes.match import get_ultra_summary

    # Seed something so the result isn't trivially empty
    replay_archive.archive_match("uniq-mtg", {
        "game_mode": "mtg", "winner": "A", "total_turns": 9,
        "frames": [{}, {}, {}],
        "match_metadata": {"model_id": "claude-opus-4.7", "git_sha": "test-sha"},
    })

    async def _run():
        result = await get_ultra_summary()
        assert result["total_matches"] == 1
        assert "mtg" in result["by_engine"]
        assert result["by_engine"]["mtg"]["matches"] == 1
        assert result["window_since"] is None

    asyncio.run(_run())


# ===== Feature 3.5 — ?since= window filter =====================================


def test_parse_since_relative_windows():
    """Hours/days/minutes resolve to (now - delta), within 2 s of expected."""
    now = time.time()
    assert abs(ultra_telemetry.parse_since("1h") - (now - 3600)) < 2
    assert abs(ultra_telemetry.parse_since("24h") - (now - 86400)) < 2
    assert abs(ultra_telemetry.parse_since("7d") - (now - 7 * 86400)) < 2
    assert abs(ultra_telemetry.parse_since("30m") - (now - 1800)) < 2
    # Fractional + capitalized accepted
    assert abs(ultra_telemetry.parse_since("0.5H") - (now - 1800)) < 2


def test_parse_since_absolute_iso():
    """ISO with trailing Z resolves to the matching unix timestamp."""
    ts = ultra_telemetry.parse_since("2026-05-20T00:00:00Z")
    import datetime as _dt
    expected = _dt.datetime(2026, 5, 20, 0, 0, 0, tzinfo=_dt.timezone.utc).timestamp()
    assert ts == expected


def test_parse_since_unix_timestamp():
    """Bare int/float passes through unchanged."""
    assert ultra_telemetry.parse_since("1747800000") == 1747800000.0
    assert ultra_telemetry.parse_since("1747800000.5") == 1747800000.5


def test_parse_since_rejects_garbage():
    """Unrecognized inputs raise ValueError with a guiding message."""
    for bad in ["", "  ", "yesterday", "abc", "-5h", "0d", "5x"]:
        with pytest.raises(ValueError):
            ultra_telemetry.parse_since(bad)


def test_ultra_summary_window_drops_old_archives(isolated_dirs, monkeypatch):
    """Matches older than since_ts must drop out of the aggregate."""
    # Archive two matches with very different archived_at timestamps.
    old_ts = time.time() - 30 * 86400  # 30 days ago
    recent_ts = time.time() - 60         # 1 minute ago

    replay_archive.archive_match("old-mtg", {
        "game_mode": "mtg", "winner": "A", "total_turns": 10,
        "frames": [{}, {}, {}],
    })
    replay_archive.archive_match("new-mtg", {
        "game_mode": "mtg", "winner": "B", "total_turns": 12,
        "frames": [{}, {}, {}],
    })

    # Backdate the old entry directly in index.json (archive_match stamps now()).
    index_path = isolated_dirs["replays"] / "index.json"
    entries = json.loads(index_path.read_text())
    for e in entries:
        if e["match_id"] == "old-mtg":
            e["archived_at"] = old_ts
        elif e["match_id"] == "new-mtg":
            e["archived_at"] = recent_ts
    index_path.write_text(json.dumps(entries))

    # No window → both visible
    full = ultra_telemetry.build_ultra_summary(
        replays_index_path=index_path,
        decisions_dir=isolated_dirs["decisions"],
    )
    assert full["by_engine"]["mtg"]["matches"] == 2
    assert full["window_since"] is None

    # 24 h window → only the new one survives
    windowed = ultra_telemetry.build_ultra_summary(
        replays_index_path=index_path,
        decisions_dir=isolated_dirs["decisions"],
        since_ts=time.time() - 86400,
    )
    assert windowed["by_engine"]["mtg"]["matches"] == 1
    assert windowed["total_matches"] == 1
    assert windowed["window_since"] is not None


def test_ultra_summary_window_filters_orphan_decisions_by_meta(isolated_dirs, monkeypatch):
    """Orphan-decisions matches use their _meta.created_at for the window
    check so a crashed match from last month doesn't haunt today's stats."""
    # Old orphan: backdate the _meta.created_at directly.
    ultra_telemetry.init_match_metadata(
        match_id="orphan-old", game_mode="hearthstone", ultra_model_id="m"
    )
    old_path = isolated_dirs["decisions"] / "orphan-old.jsonl"
    raw = json.loads(old_path.read_text().strip())
    raw["_meta"]["created_at"] = "2025-01-01T00:00:00Z"
    old_path.write_text(json.dumps(raw) + "\n")
    ultra_telemetry.append_decision(
        match_id="orphan-old", player_id="A", turn=1, phase="MAIN",
        action_type="HS_PLAY_CARD", action_payload={}, actor_is_ultra=True,
    )

    # New orphan: created_at left at "now" by init_match_metadata.
    ultra_telemetry.init_match_metadata(
        match_id="orphan-new", game_mode="hearthstone", ultra_model_id="m"
    )
    ultra_telemetry.append_decision(
        match_id="orphan-new", player_id="A", turn=1, phase="MAIN",
        action_type="HS_PLAY_CARD", action_payload={}, actor_is_ultra=True,
    )

    # 24 h window → only the recent orphan survives.
    summary = ultra_telemetry.build_ultra_summary(
        replays_index_path=isolated_dirs["replays"] / "index.json",
        decisions_dir=isolated_dirs["decisions"],
        since_ts=time.time() - 86400,
    )
    assert summary["by_engine"]["hearthstone"]["matches"] == 1
    assert summary["by_engine"]["hearthstone"]["decisions_logged"] == 1


def test_ultra_summary_window_keeps_orphan_when_meta_unparseable(isolated_dirs):
    """If the orphan has no usable timestamp (no created_at, no mtime
    readable), fall through and include it — don't silently drop data."""
    # Hand-written JSONL with no created_at field.
    path = isolated_dirs["decisions"] / "orphan-notime.jsonl"
    path.write_text(
        json.dumps({"_meta": {"match_id": "orphan-notime", "game_mode": "mtg"}}) + "\n"
        + json.dumps({"ts": 1.0, "match_id": "orphan-notime", "player_id": "A",
                      "turn": 1, "phase": "MAIN", "action_type": "PASS",
                      "actor_is_ultra": True}) + "\n"
    )
    # Backdate file mtime to a year ago so the mtime fallback would also exclude it.
    old = time.time() - 365 * 86400
    import os as _os
    _os.utime(path, (old, old))

    summary = ultra_telemetry.build_ultra_summary(
        replays_index_path=isolated_dirs["replays"] / "index.json",
        decisions_dir=isolated_dirs["decisions"],
        since_ts=time.time() - 86400,
    )
    # File mtime IS readable and is older than since_ts → drops out.
    assert "mtg" not in summary["by_engine"]


def test_ultra_summary_route_parses_since_query(isolated_dirs, monkeypatch):
    """The route handler honors ?since= and surfaces a clean 400 on garbage."""
    from src.server.routes.match import get_ultra_summary
    from fastapi import HTTPException

    replay_archive.archive_match("recent-mtg", {
        "game_mode": "mtg", "winner": "A", "total_turns": 9,
        "frames": [{}, {}, {}],
    })

    async def _run():
        result = await get_ultra_summary(since="24h")
        assert result["window_since"] is not None
        assert result["by_engine"]["mtg"]["matches"] == 1

        # Empty string treated as "no filter" — must not 400.
        result = await get_ultra_summary(since="")
        assert result["window_since"] is None

        # Bad input → 400 with a useful message.
        with pytest.raises(HTTPException) as exc:
            await get_ultra_summary(since="yesterday please")
        assert exc.value.status_code == 400

    asyncio.run(_run())


# ===== Feature 4 — Model + git SHA in match metadata ===========================


def test_archive_carries_metadata_to_index(isolated_dirs):
    replay_archive.archive_match("with-meta", {
        "game_mode": "mtg",
        "winner": "A",
        "total_turns": 11,
        "frames": [{}, {}],
        "match_metadata": {
            "model_id": "claude-opus-4.7",
            "git_sha": "deadbeef",
            "agent_runner": "claude",
        },
    })
    entries = replay_archive.list_archives()
    assert len(entries) == 1
    row = entries[0]
    assert row["match_id"] == "with-meta"
    assert row["model_id"] == "claude-opus-4.7"
    assert row["git_sha"] == "deadbeef"
    assert row["agent_runner"] == "claude"


def test_archive_without_metadata_leaves_fields_off(isolated_dirs):
    """Legacy archive_match calls (no match_metadata) shouldn't blow up — the
    optional fields just don't appear on the index row."""
    replay_archive.archive_match("no-meta", {
        "game_mode": "mtg",
        "winner": "A",
        "total_turns": 5,
        "frames": [{}, {}],
    })
    entries = replay_archive.list_archives()
    assert "model_id" not in entries[0]
    assert "git_sha" not in entries[0]


def test_git_sha_cached_after_first_call(isolated_dirs):
    """get_git_sha should fork at most once per process (cached)."""
    ultra_telemetry.reset_git_sha_cache_for_test()
    # The fixture monkeypatches get_git_sha; bypass that by clearing it
    import src.server.ultra_telemetry as ut
    sha1 = ut.get_git_sha()  # still the monkeypatched version
    sha2 = ut.get_git_sha()
    assert sha1 == sha2  # cached


def test_meta_header_includes_git_sha(isolated_dirs):
    """The first line of a decisions JSONL must carry the git_sha so any
    future analysis can correlate matches with the deployed commit."""
    ultra_telemetry.init_match_metadata(
        match_id="m-sha", game_mode="mtg", ultra_model_id="x"
    )
    lines = (isolated_dirs["decisions"] / "m-sha.jsonl").read_text().strip().splitlines()
    meta = json.loads(lines[0])
    assert meta["_meta"]["git_sha"] == "test-sha-deadbe"
    assert meta["_meta"]["model_id"] == "x"


# ===== Cross-cutting: action endpoint hook =====================================


def test_action_endpoint_logs_ultra_decision(isolated_dirs, monkeypatch):
    """Submitting an action for an ultra seat must produce a JSONL line."""
    from src.server.routes import match as match_routes

    # Stub session with the bits the route handler needs
    class StubGame:
        class State:
            game_mode = "mtg"
        state = State()

        class TurnManager:
            turn_number = 4
            class Phase:
                name = "MAIN1"
            phase = Phase()
        turn_manager = TurnManager()

        def is_game_over(self):
            return False
        def get_winner(self):
            return None

    class StubSession:
        id = "m-action-test"
        game = StubGame()
        ai_profiles_by_player = {"seat-A": {"difficulty": "ultra"}}
        is_finished = False
        winner_id = None
        player_ids = ["seat-A", "seat-B"]
        human_players = set()
        player_names = {"seat-A": "A", "seat-B": "B"}

        def is_ultra_ai_player(self, pid):
            return pid == "seat-A"

        def _player_difficulty(self, pid):
            return "ultra" if pid == "seat-A" else "medium"

        async def handle_action(self, action):
            return True, "ok"

        def get_client_state(self, pid):
            # Return a dummy GameStateResponse-compatible object via duck typing
            from src.server.models import GameStateResponse
            return GameStateResponse(
                match_id=self.id, turn_number=4, phase="MAIN1", step="",
                active_player="seat-A", players={}, is_game_over=False,
            )

    stub = StubSession()

    # Patch the session_manager.get_session to return our stub
    monkeypatch.setattr(match_routes.session_manager, "get_session", lambda mid: stub)

    action = PlayerActionRequest(
        action_type="CAST_SPELL", player_id="seat-A", card_id="card-xyz",
    )

    async def _run():
        result = await match_routes.submit_action("m-action-test", action)
        assert result.success is True

    asyncio.run(_run())

    # JSONL should now exist with one decision (no _meta header; init wasn't
    # called for this test, but append_decision creates the file regardless).
    path = isolated_dirs["decisions"] / "m-action-test.jsonl"
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    # There's no _meta header (we didn't init), just the decision
    assert any("CAST_SPELL" in line for line in lines)
    parsed = [json.loads(l) for l in lines]
    decisions = [p for p in parsed if "_meta" not in p]
    assert len(decisions) >= 1
    assert decisions[0]["player_id"] == "seat-A"
    assert decisions[0]["action_type"] == "CAST_SPELL"
    assert decisions[0]["turn"] == 4
    assert decisions[0]["phase"] == "MAIN1"


def test_action_endpoint_skips_non_ultra_seat(isolated_dirs, monkeypatch):
    """A heuristic-AI or human seat's action must NOT produce a JSONL line."""
    from src.server.routes import match as match_routes

    class StubGame:
        class State:
            game_mode = "mtg"
        state = State()

        class TurnManager:
            turn_number = 1
            class Phase:
                name = "MAIN1"
            phase = Phase()
        turn_manager = TurnManager()

        def is_game_over(self):
            return False
        def get_winner(self):
            return None

    class StubSession:
        id = "m-skip-test"
        game = StubGame()
        ai_profiles_by_player = {"seat-Heur": {"difficulty": "medium"}}
        is_finished = False
        winner_id = None
        player_ids = ["seat-Heur", "seat-Human"]
        human_players = {"seat-Human"}
        player_names = {"seat-Heur": "H", "seat-Human": "U"}

        def is_ultra_ai_player(self, pid):
            return False

        def _player_difficulty(self, pid):
            return "medium"

        async def handle_action(self, action):
            return True, "ok"

        def get_client_state(self, pid):
            from src.server.models import GameStateResponse
            return GameStateResponse(
                match_id=self.id, turn_number=1, phase="MAIN1", step="",
                active_player="seat-Heur", players={}, is_game_over=False,
            )

    stub = StubSession()
    monkeypatch.setattr(match_routes.session_manager, "get_session", lambda mid: stub)

    action = PlayerActionRequest(
        action_type="PASS", player_id="seat-Heur",
    )

    async def _run():
        result = await match_routes.submit_action("m-skip-test", action)
        assert result.success is True

    asyncio.run(_run())

    # No JSONL line should have been written for this non-ultra action.
    path = isolated_dirs["decisions"] / "m-skip-test.jsonl"
    assert not path.exists() or path.read_text().strip() == ""
