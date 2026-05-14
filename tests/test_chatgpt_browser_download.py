"""Tests for scripts.art.chatgpt_browser_download.

Covers JS string generation and the `~/Downloads/` -> target move
helper. The browser-side fetch / `<a download>` click is not covered
here -- that's an MCP-driven integration concern and out of scope.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.art.chatgpt_browser_download import (
    MIN_BLOB_BYTES,
    download_via_blob_fetch,
    move_from_downloads,
)


# ---------------------------------------------------------------------------
# download_via_blob_fetch -- JS string generation
# ---------------------------------------------------------------------------

def test_explicit_url_embedded_in_js():
    """When an image_url is passed, the JS hard-codes that URL and skips
    DOM-search polling (no `findGenerated()` fallback path used)."""
    url = (
        "https://files.oaiusercontent.com/file-AbCdEfGh"
        "?se=2026-05-14T20%3A00%3A00Z&sig=REDACTED"
    )
    js = download_via_blob_fetch(
        image_url=url,
        target_path="frontend/public/scp-art/mnr/mnr-foo.png",
        tab_id=7,
    )
    # Explicit URL is JSON-encoded into the JS literal so quoting / `&`
    # round-trip safely. We assert the substring is present verbatim.
    assert url in js
    # Filename uses only the basename of target_path.
    assert '"mnr-foo.png"' in js
    # tab_id is embedded as a comment for log correlation.
    assert "tab_id=7" in js
    # When explicit_url is set, the JS sets fetch_url=explicit_url and
    # skips the findGenerated poll loop on the success path.
    assert "explicit_url" in js
    # Sanity: the JS performs the blob fetch, creates an <a download>,
    # and clicks it.
    assert "URL.createObjectURL(blob)" in js
    assert "a.download = target_fname" in js
    assert "a.click()" in js


def test_dom_discovery_mode_when_url_is_none():
    """When image_url is None, the JS encodes `null` and relies on the
    DOM-walk + poll loop -- the MNR-run mode."""
    js = download_via_blob_fetch(
        image_url=None,
        target_path="/abs/path/mnr-bar.png",
        tab_id=42,
    )
    assert "const explicit_url = null;" in js
    # DOM discovery: must look for "generated image" alt text and the
    # assistant-message img fallback.
    assert "generated image" in js.lower()
    assert "data-message-author-role=\"assistant\"" in js
    # Filename strips the directory portion.
    assert '"mnr-bar.png"' in js
    assert "/abs/path" not in js


def test_poll_knobs_threaded_through_js():
    """`poll_rounds` and `poll_interval_ms` flow into the JS constants."""
    js = download_via_blob_fetch(
        image_url=None,
        target_path="x.png",
        tab_id=1,
        poll_rounds=5,
        poll_interval_ms=12_000,
        min_blob_bytes=4096,
    )
    assert "const POLL_ROUNDS = 5;" in js
    assert "const POLL_INTERVAL_MS = 12000;" in js
    assert "const MIN_BYTES = 4096;" in js


def test_default_min_bytes_matches_constant():
    """Defaults match the module-level MIN_BLOB_BYTES."""
    js = download_via_blob_fetch(
        image_url=None,
        target_path="x.png",
        tab_id=1,
    )
    assert f"const MIN_BYTES = {MIN_BLOB_BYTES};" in js


def test_filename_with_special_chars_is_json_quoted():
    """Filenames containing quotes / backslashes round-trip safely
    through json.dumps -- the JS won't break on quoting."""
    js = download_via_blob_fetch(
        image_url=None,
        target_path='weird"name.png',
        tab_id=1,
    )
    # json.dumps escapes the inner quote, so the JS literal stays valid.
    assert r'"weird\"name.png"' in js


# ---------------------------------------------------------------------------
# move_from_downloads
# ---------------------------------------------------------------------------

def _write_blob(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG" + b"\x00" * (size - 4))


def test_move_from_downloads_happy_path(tmp_path):
    downloads = tmp_path / "Downloads"
    target = tmp_path / "art" / "out.png"
    _write_blob(downloads / "out.png", MIN_BLOB_BYTES * 2)

    assert not target.exists()
    ok = move_from_downloads(
        filename="out.png",
        target_path=str(target),
        downloads_dir=downloads,
    )
    assert ok is True
    assert target.exists()
    assert target.stat().st_size >= MIN_BLOB_BYTES
    # Source file moved (not copied).
    assert not (downloads / "out.png").exists()


def test_move_from_downloads_missing_source(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    target = tmp_path / "art" / "out.png"

    ok = move_from_downloads(
        filename="never_existed.png",
        target_path=str(target),
        downloads_dir=downloads,
    )
    assert ok is False
    assert not target.exists()


def test_move_from_downloads_rejects_tiny_file(tmp_path):
    """A 1KB file is below MIN_BLOB_BYTES -- probably an error page."""
    downloads = tmp_path / "Downloads"
    target = tmp_path / "art" / "out.png"
    _write_blob(downloads / "tiny.png", 1024)

    ok = move_from_downloads(
        filename="tiny.png",
        target_path=str(target),
        downloads_dir=downloads,
    )
    assert ok is False
    # The source is left in place when we reject it -- the caller can
    # inspect what Chrome actually downloaded.
    assert (downloads / "tiny.png").exists()
    assert not target.exists()


def test_move_creates_parent_directory(tmp_path):
    """Target parent dirs are auto-created."""
    downloads = tmp_path / "Downloads"
    target = tmp_path / "deep" / "nested" / "dirs" / "out.png"
    _write_blob(downloads / "out.png", MIN_BLOB_BYTES * 2)

    ok = move_from_downloads(
        filename="out.png",
        target_path=str(target),
        downloads_dir=downloads,
    )
    assert ok is True
    assert target.exists()
