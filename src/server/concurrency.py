"""Per-feature concurrency bounds for the Hyperdraft server.

Three independent classes of work spawn ``claude`` subprocesses inside the
container, and each has its own concurrency budget so a runaway ultra match
can't starve the auto-repair daemon (or vice versa). The semaphores are
created lazily on first ``acquire()`` so they bind to whatever event loop
is running at that point — asyncio refuses to bind a Semaphore to a loop
at module-import time under uvicorn's lifespan model.

Defaults can be overridden via env vars:

    HYPERDRAFT_ULTRA_MAX   default 3  (includes 1 soft-reservation for spectator)
    HYPERDRAFT_REPAIR_MAX  default 1
    HYPERDRAFT_TRAIN_MAX   default 1

Usage:

    from src.server.concurrency import ultra_agent_semaphore
    async with ultra_agent_semaphore():
        proc = subprocess.Popen([...])
        ...
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional


def _read_cap(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


_ultra_sem: Optional[asyncio.Semaphore] = None
_repair_sem: Optional[asyncio.Semaphore] = None
_training_sem: Optional[asyncio.Semaphore] = None


def _get_ultra_sem() -> asyncio.Semaphore:
    global _ultra_sem
    if _ultra_sem is None:
        _ultra_sem = asyncio.Semaphore(_read_cap("HYPERDRAFT_ULTRA_MAX", 3))
    return _ultra_sem


def _get_repair_sem() -> asyncio.Semaphore:
    global _repair_sem
    if _repair_sem is None:
        _repair_sem = asyncio.Semaphore(_read_cap("HYPERDRAFT_REPAIR_MAX", 1))
    return _repair_sem


def _get_training_sem() -> asyncio.Semaphore:
    global _training_sem
    if _training_sem is None:
        _training_sem = asyncio.Semaphore(_read_cap("HYPERDRAFT_TRAIN_MAX", 1))
    return _training_sem


@asynccontextmanager
async def ultra_agent_semaphore() -> AsyncIterator[None]:
    """Bound concurrent ultra-agent subprocess spawns (human-vs-bot + spectator)."""
    sem = _get_ultra_sem()
    async with sem:
        yield


@asynccontextmanager
async def auto_repair_semaphore() -> AsyncIterator[None]:
    """Bound concurrent auto-repair sessions (engine-crash claude invocations)."""
    sem = _get_repair_sem()
    async with sem:
        yield


@asynccontextmanager
async def training_semaphore() -> AsyncIterator[None]:
    """Bound concurrent /ultra-loop training runs from the admin endpoint."""
    sem = _get_training_sem()
    async with sem:
        yield


def reset_for_testing() -> None:
    """Test hook: drop the cached semaphores so the next acquire re-reads env."""
    global _ultra_sem, _repair_sem, _training_sem
    _ultra_sem = None
    _repair_sem = None
    _training_sem = None
