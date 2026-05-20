"""Auto-repair: spawn ``claude`` inside the container to diagnose engine crashes.

The session handler calls :func:`capture_and_kick` from its top-level exception
handler. That writes a small failure context (traceback, match state snapshot,
trigger reason) into ``storage/repair/<session_id>/`` and spawns ``claude -p``
as an asyncio subprocess. Per-match dedup: only one active claude per match at
a time.

:func:`cadence_loop` is a long-running asyncio task registered in the lifespan
of ``src/server/main.py``. It resumes any active repair sessions every 5
minutes via ``claude --resume`` until each writes a ``STATUS`` file
(``DONE`` / ``NEED_HUMAN``) or the wall-time limit is hit.

Verification (test-first): claude must drop a new pytest file at
``tests/auto_repair/<session>.py`` that reproduces the crash, plus the patch
that makes it pass. ``_verify_fix`` runs that test; a failing run flips the
status to ``REJECTED`` and resumes claude with the diff captured as
``verification_failures`` in ``context.json``.

The host-side watcher (``scripts/ops/repair_patch_watcher.sh``) picks up
``STATUS=DONE`` directories, filters the in-container git diff against
``ALLOWED_PATHS``, and pushes a ``auto-repair/<session_id>`` branch with a
draft PR. The container never touches GitHub.

Kill switch: set ``REPAIR_ENABLED=false`` to skip new kicks and resumes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

REPAIR_ROOT = Path("storage/repair")
PROMPT_PATH = Path(__file__).parent / "repair_prompt.md"

MAX_REPAIR_WALL_SECONDS = int(os.environ.get("REPAIR_MAX_WALL_SECONDS", "18000"))
RESUME_INTERVAL_SECONDS = int(os.environ.get("REPAIR_RESUME_INTERVAL_SECONDS", "300"))
PER_TURN_TIMEOUT_SECONDS = int(os.environ.get("REPAIR_PER_TURN_TIMEOUT_SECONDS", "900"))
VERIFY_TIMEOUT_SECONDS = int(os.environ.get("REPAIR_VERIFY_TIMEOUT_SECONDS", "90"))
STREAM_LINE_LIMIT = 10 * 1024 * 1024
ARTIFACT_TTL_SECONDS = int(
    os.environ.get("REPAIR_ARTIFACT_TTL_SECONDS", str(7 * 86400))
)
CLEANUP_INTERVAL_SECONDS = int(
    os.environ.get("REPAIR_CLEANUP_INTERVAL_SECONDS", "3600")
)

ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

# Tools we trust claude to invoke without further confirmation. The host-side
# patch watcher independently enforces ALLOWED_PATHS on the resulting diff so
# even if claude writes outside its sandbox, the changes don't reach GitHub.

_active: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()
_inflight_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> None:
    _inflight_tasks.add(task)
    task.add_done_callback(_inflight_tasks.discard)


def is_enabled() -> bool:
    """Auto-repair defaults OFF. Production opts in via REPAIR_ENABLED=true."""
    return os.environ.get("REPAIR_ENABLED", "").lower() in ("true", "1", "yes")


def active_repairs_snapshot() -> dict[str, dict[str, Any]]:
    """Read-only snapshot for diagnostics."""
    return {k: dict(v) for k, v in _active.items()}


async def capture_and_kick(
    match_id: str,
    *,
    game_mode: str,
    traceback_text: str,
    game_state_snapshot: dict[str, Any] | None = None,
    trigger: str = "exception",
    extra_context: dict[str, Any] | None = None,
) -> bool:
    """Write failure context and (if not deduped) spawn ``claude -p``.

    ``trigger`` is one of ``exception``, ``ai_none_returned``, ``turn_timeout``.
    Per-match dedup: if a claude is already active for this match, this folds
    in and returns False.
    """
    if not is_enabled():
        log.info(
            "capture_and_kick skipped: REPAIR_ENABLED not truthy "
            "(match=%s trigger=%s)", match_id, trigger,
        )
        return False

    log.info(
        "capture_and_kick starting match=%s game_mode=%s trigger=%s",
        match_id, game_mode, trigger,
    )

    try:
        out_dir = REPAIR_ROOT / match_id
        out_dir.mkdir(parents=True, exist_ok=True)

        context_obj: dict[str, Any] = {
            "match_id": match_id,
            "game_mode": game_mode,
            "trigger": trigger,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "traceback": traceback_text,
        }
        if extra_context:
            context_obj.update(extra_context)
        (out_dir / "context.json").write_text(json.dumps(context_obj, indent=2))

        if game_state_snapshot is not None:
            try:
                (out_dir / "state_snapshot.json").write_text(
                    json.dumps(game_state_snapshot, indent=2, default=str)
                )
            except Exception as e:  # noqa: BLE001
                log.warning("could not serialize state snapshot: %s", e)
    except Exception as cap_err:  # noqa: BLE001
        log.warning("auto-repair context capture failed: %s", cap_err)

    return await _kick(match_id, game_mode)


async def _kick(match_id: str, game_mode: str) -> bool:
    async with _lock:
        if match_id in _active:
            log.info(
                "auto-repair already active for match=%s; folding new failure",
                match_id,
            )
            return False
        _active[match_id] = {
            "game_mode": game_mode,
            "claude_session_id": None,
            "started_at": time.time(),
            "last_turn_at": time.time(),
            "turns": 0,
        }

    _track_task(asyncio.create_task(_run_first_turn(match_id, game_mode)))
    return True


async def _run_first_turn(match_id: str, game_mode: str) -> None:
    if not PROMPT_PATH.exists():
        log.warning("repair prompt missing at %s; cannot run repair", PROMPT_PATH)
        async with _lock:
            _active.pop(match_id, None)
        return
    prompt_template = PROMPT_PATH.read_text()
    prompt = (
        f"{prompt_template}\n\n---\n\n"
        f"MATCH_ID: {match_id}\nGAME_MODE: {game_mode}\n\n"
        "Begin work."
    )
    try:
        result = await _run_claude(
            prompt,
            resume_session_id=None,
            match_id=match_id,
            turn_number=1,
        )
        async with _lock:
            if match_id in _active:
                _active[match_id]["claude_session_id"] = result.get("session_id")
                _active[match_id]["last_turn_at"] = time.time()
                _active[match_id]["turns"] = 1
    except Exception as e:  # noqa: BLE001
        log.exception("auto-repair first turn for match=%s failed: %s", match_id, e)

    try:
        done = await _check_done(match_id)
    except Exception as e:  # noqa: BLE001
        log.warning("_check_done after first turn raised: %s", e)
        done = False

    if not done:
        async with _lock:
            info = _active.get(match_id)
            if info is not None and not info.get("claude_session_id"):
                log.warning(
                    "first turn ended without claude_session_id and no terminal "
                    "STATUS — popping match=%s",
                    match_id,
                )
                _active.pop(match_id, None)


async def _run_claude(
    prompt: str,
    *,
    resume_session_id: str | None,
    match_id: str,
    turn_number: int,
) -> dict[str, Any]:
    """Spawn ``claude -p`` in stream-json mode and persist per-turn transcripts."""
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--allowedTools",
        *ALLOWED_TOOLS,
    ]
    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])

    turn_dir = REPAIR_ROOT / match_id / "turns" / f"{turn_number:03d}"
    turn_dir.mkdir(parents=True, exist_ok=True)
    stream_path = turn_dir / "stream.jsonl"
    started_at = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at))

    log.info(
        "claude turn starting match=%s turn=%d resume=%s prompt_bytes=%d "
        "timeout=%ds turn_dir=%s",
        match_id, turn_number, resume_session_id or "<none>",
        len(prompt), PER_TURN_TIMEOUT_SECONDS, turn_dir,
    )

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=STREAM_LINE_LIMIT,
    )

    final_result: dict[str, Any] | None = None
    fallback_session_id: str | None = None

    async def _read_stdout() -> None:
        nonlocal final_result, fallback_session_id
        assert proc.stdout is not None
        try:
            stream_file = stream_path.open("ab")
        except Exception as e:  # noqa: BLE001
            log.warning("could not open stream.jsonl for write: %s", e)
            stream_file = None
        try:
            while True:
                try:
                    line = await proc.stdout.readline()
                except ValueError as e:
                    log.warning("stream readline exceeded limit, skipping: %s", e)
                    try:
                        await proc.stdout.read(STREAM_LINE_LIMIT)
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                if not line:
                    return
                if stream_file is not None:
                    try:
                        stream_file.write(line)
                        stream_file.flush()
                    except Exception:  # noqa: BLE001
                        pass
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                evt_type = event.get("type")
                if (
                    evt_type == "system"
                    and event.get("subtype") == "init"
                    and event.get("session_id")
                ):
                    fallback_session_id = event["session_id"]
                elif evt_type == "result":
                    final_result = event
        finally:
            if stream_file is not None:
                try:
                    stream_file.close()
                except Exception:  # noqa: BLE001
                    pass

    read_task = asyncio.create_task(_read_stdout())
    timed_out = False
    try:
        try:
            await asyncio.wait_for(proc.wait(), timeout=PER_TURN_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
        await read_task
    except asyncio.CancelledError:
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        read_task.cancel()
        await _write_turn_meta(
            turn_dir, cmd, prompt, resume_session_id, match_id,
            turn_number, started_iso, started_at, b"",
            exit_code=proc.returncode, final_result=None,
            fallback_session_id=fallback_session_id, note="cancelled",
        )
        raise

    stderr_bytes = b""
    if proc.stderr is not None:
        try:
            stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
    try:
        (turn_dir / "stderr.txt").write_bytes(stderr_bytes)
    except Exception as e:  # noqa: BLE001
        log.warning("could not write turn stderr: %s", e)

    await _write_turn_meta(
        turn_dir, cmd, prompt, resume_session_id, match_id,
        turn_number, started_iso, started_at, stderr_bytes,
        exit_code=proc.returncode, final_result=final_result,
        fallback_session_id=fallback_session_id,
        note="timeout" if timed_out else None,
    )

    if timed_out:
        raise RuntimeError(
            f"claude subprocess exceeded {PER_TURN_TIMEOUT_SECONDS}s"
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude exited {proc.returncode}: {stderr_bytes.decode()[:500]}"
        )

    if final_result is not None:
        return final_result
    return {"session_id": fallback_session_id, "result": ""}


async def _write_turn_meta(
    turn_dir: Path,
    cmd: list[str],
    prompt: str,
    resume_session_id: str | None,
    match_id: str,
    turn_number: int,
    started_iso: str,
    started_at: float,
    stderr_bytes: bytes,
    exit_code: int | None,
    final_result: dict[str, Any] | None,
    fallback_session_id: str | None,
    note: str | None = None,
) -> None:
    ended_at = time.time()
    ended_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended_at))
    duration_ms = int((ended_at - started_at) * 1000)
    meta: dict[str, Any] = {
        "turn": turn_number,
        "match_id": match_id,
        "resume_session_id": resume_session_id,
        "prompt_size_bytes": len(prompt),
        "prompt_preview": prompt[:500],
        "command_argv_preview": cmd[:3] + ["<prompt elided>"] + cmd[3:][:8],
        "started_at": started_iso,
        "ended_at": ended_iso,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "stderr_bytes": len(stderr_bytes),
        "stderr_preview": stderr_bytes.decode(errors="replace")[:500],
        "note": note,
        "fallback_session_id": fallback_session_id,
    }
    if final_result:
        denials = final_result.get("permission_denials") or []
        meta.update({
            "claude_session_id": final_result.get("session_id"),
            "num_turns": final_result.get("num_turns"),
            "cost_usd": float(final_result.get("total_cost_usd") or 0.0),
            "duration_api_ms": final_result.get("duration_api_ms"),
            "stop_reason": final_result.get("stop_reason"),
            "is_error": final_result.get("is_error"),
            "result_preview": (final_result.get("result") or "")[:500],
            "permission_denials_count": len(denials),
        })

    try:
        (turn_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    except Exception as e:  # noqa: BLE001
        log.warning("could not write turn meta to %s: %s", turn_dir, e)

    log.info(
        "claude turn done match=%s turn=%d exit=%s duration=%dms "
        "cost=$%.4f stop=%s note=%s result=%r",
        match_id, turn_number, exit_code, duration_ms,
        meta.get("cost_usd", 0.0), meta.get("stop_reason"), note or "ok",
        (meta.get("result_preview") or "")[:120],
    )


async def _verify_fix(match_id: str) -> tuple[bool, str | None]:
    """Verify a claude-claimed fix actually passes its repro test.

    Two checks:
      1. ``tests/auto_repair/<match_id>.py`` exists (claude wrote a test).
      2. ``pytest tests/auto_repair/<match_id>.py`` passes.

    Returns ``(passed, reason)``. On pass, ``reason`` is None.
    """
    repro_test = Path("tests") / "auto_repair" / f"{match_id}.py"
    if not repro_test.exists():
        return (
            False,
            f"no repro test at {repro_test} — claude declared DONE but did not "
            "write the required pytest file under tests/auto_repair/",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-m", "pytest",
            str(repro_test), "-x", "--tb=short",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd="/app" if Path("/app").exists() else None,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=VERIFY_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False, f"pytest verifier exceeded {VERIFY_TIMEOUT_SECONDS}s"
    except FileNotFoundError as e:
        return False, f"verifier could not find pytest: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"verifier setup failed: {type(e).__name__}: {e}"

    out = stdout_bytes.decode("utf-8", "replace")
    if proc.returncode == 0:
        log.info(
            "verify PASSED match=%s test=%s", match_id, repro_test,
        )
        return True, None
    return (
        False,
        f"pytest exited {proc.returncode}. Last 800 bytes of output:\n{out[-800:]}",
    )


async def _on_verification_failed(
    match_id: str, reason: str, rejected_status_body: str
) -> None:
    """Move STATUS aside and record the rejection in context.json."""
    log.warning("verification REJECTED match=%s reason=%s", match_id, reason)
    out_dir = REPAIR_ROOT / match_id
    try:
        rejected_path = out_dir / f"STATUS_REJECTED_turn{int(time.time())}"
        (out_dir / "STATUS").rename(rejected_path)
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("could not move rejected STATUS aside: %s", e)
        try:
            (out_dir / "STATUS").unlink()
        except Exception:  # noqa: BLE001
            pass

    ctx_path = out_dir / "context.json"
    try:
        ctx_obj = json.loads(ctx_path.read_text())
    except Exception:  # noqa: BLE001
        ctx_obj = {}
    history = ctx_obj.get("verification_failures") or []
    history.append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": reason,
        "rejected_status_first_line": (
            rejected_status_body.split("\n", 1)[0][:240]
        ),
    })
    ctx_obj["verification_failures"] = history
    try:
        ctx_path.write_text(json.dumps(ctx_obj, indent=2))
    except Exception as e:  # noqa: BLE001
        log.warning("could not append verification failure to context: %s", e)


async def _check_done(match_id: str) -> bool:
    """If STATUS exists and verifier passes, mark the repair complete."""
    status_file = REPAIR_ROOT / match_id / "STATUS"
    if not status_file.exists():
        return False
    body = status_file.read_text()
    first_line = body.split("\n", 1)[0].strip()
    normalized = first_line.lstrip("#`* ").upper()
    if not (normalized.startswith("DONE") or normalized.startswith("NEED_HUMAN")):
        return False

    verdict = "DONE" if normalized.startswith("DONE") else "NEED_HUMAN"

    if verdict == "DONE":
        log.info(
            "verifying DONE claim match=%s first_line=%r",
            match_id, first_line[:200],
        )
        passed, reason = await _verify_fix(match_id)
        if not passed:
            await _on_verification_failed(match_id, reason or "?", body)
            return False  # keep active; cadence will resume claude

    async with _lock:
        _active.pop(match_id, None)
    log.info(
        "STATUS complete match=%s verdict=%s body_bytes=%d",
        match_id, verdict, len(body),
    )
    log.info("STATUS body match=%s:\n%s", match_id, body[:4000])
    return True


async def cadence_loop() -> None:
    """Long-running background task. Resumes active repairs every N seconds
    and garbage-collects aged artifacts."""
    log.info(
        "auto-repair cadence loop starting (interval=%ds, max wall=%ds, "
        "artifact ttl=%ds)",
        RESUME_INTERVAL_SECONDS, MAX_REPAIR_WALL_SECONDS, ARTIFACT_TTL_SECONDS,
    )
    try:
        cleanup_old_artifacts()
    except Exception as e:  # noqa: BLE001
        log.warning("startup artifact cleanup raised: %s", e)
    last_cleanup = time.time()
    while True:
        try:
            await asyncio.sleep(RESUME_INTERVAL_SECONDS)
            if not is_enabled():
                continue
            await _cadence_tick()
            if time.time() - last_cleanup > CLEANUP_INTERVAL_SECONDS:
                try:
                    cleanup_old_artifacts()
                except Exception as e:  # noqa: BLE001
                    log.warning("periodic artifact cleanup raised: %s", e)
                last_cleanup = time.time()
        except asyncio.CancelledError:
            return
        except Exception as e:  # noqa: BLE001
            log.exception("auto-repair cadence tick crashed: %s", e)


def cleanup_old_artifacts() -> None:
    """Prune storage/repair/<match>/ whose mtime is older than the TTL."""
    cutoff = time.time() - ARTIFACT_TTL_SECONDS
    active_ids = set(_active.keys())
    pruned = 0
    kept_active = 0
    if not REPAIR_ROOT.exists():
        return
    for entry in REPAIR_ROOT.iterdir():
        try:
            if entry.is_dir() and entry.name in active_ids:
                kept_active += 1
                continue
            if entry.stat().st_mtime >= cutoff:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            pruned += 1
        except Exception as e:  # noqa: BLE001
            log.warning("artifact cleanup: failed to prune %s: %s", entry, e)
    if pruned or kept_active:
        log.info(
            "artifact cleanup: pruned=%d kept_active=%d ttl=%ds",
            pruned, kept_active, ARTIFACT_TTL_SECONDS,
        )


async def _cadence_tick() -> None:
    async with _lock:
        snapshot = dict(_active)
    for match_id, info in snapshot.items():
        if await _check_done(match_id):
            continue
        if time.time() - info["started_at"] > MAX_REPAIR_WALL_SECONDS:
            await _timeout_repair(match_id)
            continue
        await _resume_one(match_id, info["claude_session_id"])


async def _resume_one(match_id: str, claude_session_id: str | None) -> None:
    if not claude_session_id:
        log.warning(
            "no claude session id recorded for match=%s repair; skipping resume",
            match_id,
        )
        return
    resume_prompt = (
        "Continue. **Re-read context.json first** — it may have a "
        "`verification_failures` array appended since your last turn. "
        "Each entry has the pytest output that proved a previous STATUS=DONE "
        "was wrong; use it as the real signal for what's still broken. "
        "The original `traceback` field may be a downstream symptom. "
        "Status check: what have you found? What's next? "
        "If you've truly finished, write a fresh STATUS file."
    )
    async with _lock:
        next_turn = (
            (_active[match_id]["turns"] + 1) if match_id in _active else 0
        )
    try:
        result = await _run_claude(
            resume_prompt,
            resume_session_id=claude_session_id,
            match_id=match_id,
            turn_number=next_turn,
        )
        async with _lock:
            if match_id in _active:
                _active[match_id]["last_turn_at"] = time.time()
                _active[match_id]["turns"] += 1
                turns = _active[match_id]["turns"]
            else:
                turns = -1
        log.info(
            "auto-repair resume turn %d for match=%s: %s",
            turns, match_id, (result.get("result") or "")[:240],
        )
        await _check_done(match_id)
    except Exception as e:  # noqa: BLE001
        log.exception("auto-repair resume for match=%s failed: %s", match_id, e)


async def _timeout_repair(match_id: str) -> None:
    log.warning(
        "auto-repair timeout (>%ds) for match=%s",
        MAX_REPAIR_WALL_SECONDS, match_id,
    )
    try:
        status_file = REPAIR_ROOT / match_id / "STATUS"
        if not status_file.exists():
            status_file.write_text(
                f"NEED_HUMAN: auto-repair exceeded "
                f"{MAX_REPAIR_WALL_SECONDS}s wall time\n"
            )
    except Exception as e:  # noqa: BLE001
        log.warning("failed to write timeout STATUS: %s", e)
    async with _lock:
        _active.pop(match_id, None)


async def shutdown() -> None:
    """Cancel any in-flight repair turns. Called from main.py lifespan teardown."""
    if _inflight_tasks:
        log.info(
            "auto-repair shutdown: cancelling %d in-flight task(s)",
            len(_inflight_tasks),
        )
        for task in list(_inflight_tasks):
            task.cancel()
        await asyncio.gather(*_inflight_tasks, return_exceptions=True)
