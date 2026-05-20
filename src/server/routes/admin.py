"""Admin-only routes (Phase 4.3): on-demand training runs.

POST /api/admin/train spawns ``claude -p '/ultra-loop ...'`` inside the
container against a hardlinked copy of /app so the training run is
isolated from the live production tree. Outputs are tarballed and the
host-side patch watcher picks them up for human review (no auto-merge).

Auth: requires ``X-Admin-Auth`` header matching ``HYPERDRAFT_ADMIN_SECRET``.
If the env var is unset, the endpoint refuses ALL requests — the secret
must be configured before training is usable.

The training run is bounded by the TRAINING_SEMAPHORE (Phase 2.3) so a
single mis-fired button-press can't fork 20 concurrent claude subprocesses.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..concurrency import training_semaphore, _get_training_sem

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

TRAINING_ROOT = Path("storage/training")
APP_ROOT = Path("/app") if Path("/app").exists() else Path.cwd()

VALID_GAMES = {"mtg", "hearthstone", "pokemon", "yugioh", "minecraft", "finance", "depths", "scp"}
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("TRAINING_TIMEOUT_SECONDS", "10800"))  # 3h

# In-memory registry: run_id -> {"proc": Popen, "started_at": ts, "tar_path": Path | None}.
_active_runs: dict[str, dict] = {}


def _require_admin(request: Request) -> None:
    """Gate the endpoint on HYPERDRAFT_ADMIN_SECRET + X-Admin-Auth header."""
    expected = os.environ.get("HYPERDRAFT_ADMIN_SECRET", "").strip()
    if not expected:
        # Refuse-all when secret isn't configured — avoids accidental exposure.
        raise HTTPException(status_code=404, detail="Not found")
    provided = request.headers.get("x-admin-auth", "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/train")
async def start_training(
    request: Request,
    game: str,
    iterations: int = 1,
) -> dict:
    """Spawn a Claude training run against a hardlinked /app copy."""
    _require_admin(request)

    if game not in VALID_GAMES:
        raise HTTPException(status_code=400, detail=f"Unknown game: {game}")
    if iterations < 1 or iterations > 50:
        raise HTTPException(status_code=400, detail="iterations must be 1..50")

    # Refuse to start a new run if the training semaphore is already at cap.
    # We do not BLOCK the HTTP route — caps are an operator safety, so a 429
    # is more useful than a hung request when the cap is hit. The acquired
    # slot is released by ``_await_and_tarball`` when the subprocess exits.
    sem = _get_training_sem()
    if sem.locked():
        raise HTTPException(
            status_code=429,
            detail=f"Training capacity at cap ({sem._value} slot(s)); retry after a run completes.",
        )
    await sem.acquire()

    # Sub-second uniqueness via random suffix; two POSTs in the same second
    # used to share a run_id, with the second's shutil.rmtree corrupting the
    # first run's workdir mid-claude-edit.
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
    run_dir = TRAINING_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Hardlink /app into the run dir so claude can edit without touching live code.
    # ``cp -al`` is the cheapest way: hardlinks for regular files, recurses dirs.
    work_root = run_dir / "app"
    if work_root.exists():
        shutil.rmtree(work_root, ignore_errors=True)
    work_root.mkdir(parents=True, exist_ok=True)
    try:
        # ``cp -al`` is GNU-specific; container has GNU coreutils.
        subprocess.run(
            ["cp", "-al", str(APP_ROOT) + "/.", str(work_root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        sem.release()  # Don't leak the slot on staging failure.
        log.error("cp -al failed for training run=%s: %s",
                  run_id, e.stderr.decode("utf-8", "replace")[:500])
        raise HTTPException(status_code=500, detail="failed to stage training workdir")

    log_path = run_dir / "log"
    prompt = f"/ultra-loop --game={game} --iterations={iterations}"

    # Don't await — fire-and-forget the subprocess. Status endpoint reads
    # progress from the log file + the _active_runs registry.
    log_fh = open(log_path, "ab")
    proc = subprocess.Popen(
        ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"],
        cwd=str(work_root),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    _active_runs[run_id] = {
        "proc": proc,
        "started_at": time.time(),
        "game": game,
        "iterations": iterations,
        "log_path": str(log_path),
        "work_root": str(work_root),
        "tar_path": None,
    }

    # Reap + tarball on exit so the host watcher can pick up the artifacts.
    asyncio.create_task(_await_and_tarball(run_id))

    log.info("training run=%s started game=%s iterations=%d pid=%d cwd=%s",
             run_id, game, iterations, proc.pid, work_root)
    return {"run_id": run_id, "status": "running", "game": game, "iterations": iterations}


@router.get("/train/{run_id}/status")
async def get_training_status(run_id: str, request: Request) -> dict:
    """Report whether a training run is still active and where its log lives."""
    _require_admin(request)
    info = _active_runs.get(run_id)
    if info is None:
        # Could be a completed run whose entry was reaped. Check tarball presence.
        tar_path = TRAINING_ROOT / f"{run_id}.tar.gz"
        if tar_path.exists():
            return {"run_id": run_id, "status": "completed", "tar_path": str(tar_path)}
        raise HTTPException(status_code=404, detail="Unknown training run")
    proc = info["proc"]
    state = "running" if proc.poll() is None else f"exited_{proc.returncode}"
    return {
        "run_id": run_id,
        "status": state,
        "game": info["game"],
        "iterations": info["iterations"],
        "started_at": info["started_at"],
        "log_path": info["log_path"],
        "tar_path": info.get("tar_path"),
    }


async def _await_and_tarball(run_id: str) -> None:
    """Wait for the training subprocess to exit, then tarball the outputs."""
    info = _active_runs.get(run_id)
    if info is None:
        return
    proc = info["proc"]
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, proc.wait)
    finally:
        run_dir = TRAINING_ROOT / run_id
        tar_path = TRAINING_ROOT / f"{run_id}.tar.gz"
        try:
            subprocess.run(
                ["tar", "-czf", str(tar_path), "-C", str(TRAINING_ROOT), run_id],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            info["tar_path"] = str(tar_path)
            log.info("training run=%s tarball at %s", run_id, tar_path)
        except subprocess.CalledProcessError as e:
            log.warning("training run=%s tar failed: %s",
                        run_id, e.stderr.decode("utf-8", "replace")[:500])
        finally:
            # Always release the semaphore slot, even if tar failed.
            try:
                _get_training_sem().release()
            except Exception:
                pass
