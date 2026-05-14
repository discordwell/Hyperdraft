"""Browser-side blob download helper for ChatGPT-web art runs.

Problem
-------
When driving ChatGPT-web through the ``claude-in-chrome`` MCP, the MCP
redacts ``oaiusercontent.com`` image URLs as
``"[BLOCKED: Cookie/query string data]"`` because those URLs carry auth
tokens in the query string. That means the agent cannot read the URL out
of the page and pipe it to ``curl`` / ``requests`` -- the URL is opaque
to Python-side tooling.

Solution
--------
Run a small JS snippet *inside the tab* (where session cookies are still
valid). The snippet:

1. Locates the freshly-generated image (or fetches the explicit URL you
   pass in).
2. ``await fetch(img.src).then(r => r.blob())`` -- this works because
   the tab retains the auth cookies the MCP can't see.
3. Constructs an ``<a download="<filename>" href="<blob: URL>">`` element
   and ``.click()``s it.
4. Chrome's native download flow drops the file into ``~/Downloads/``.
5. A subsequent ``mv ~/Downloads/<filename> <target_path>`` (see
   :func:`move_from_downloads`) puts it where the caller wants it.

After the **first** download in a session, Chrome may prompt the user to
allow multiple downloads from this site. Click "Allow". Subsequent
downloads happen silently, even with the tab backgrounded.

Proof of concept
----------------
This pattern drove the MNR (SCP "Mnestic Reset") art run in May 2026:
120/120 cards downloaded without manual intervention after the initial
consent click. The throwaway driver scripts live at
``scripts/_mnr_*.py`` (gitignored as per-run scratch).

Usage
-----
::

    from scripts.art.chatgpt_browser_download import (
        download_via_blob_fetch,
        move_from_downloads,
    )

    # Either: discover the latest "Generated image" in the DOM
    js = download_via_blob_fetch(
        image_url=None,
        target_path="frontend/public/scp-art/mnr/mnr-foo.png",
        tab_id=42,
    )

    # Or: fetch a specific (MCP-redacted) URL the caller already knows
    js = download_via_blob_fetch(
        image_url="https://oaiusercontent.com/file-abc?se=...&sig=...",
        target_path="frontend/public/scp-art/mnr/mnr-foo.png",
        tab_id=42,
    )

    # Hand `js` to the claude-in-chrome MCP:
    #   mcp__claude-in-chrome__javascript_tool(tab_id=42, code=js)
    # The JS returns {ok: true, blob_size: <bytes>, ...} on success.

    # Then move from ~/Downloads to the real destination:
    move_from_downloads("mnr-foo.png",
                        "frontend/public/scp-art/mnr/mnr-foo.png")
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Minimum byte size for a generated PNG to count as "real" art.
# Smaller responses are usually placeholder/transparent images that
# slipped through before the real one finished rendering.
MIN_BLOB_BYTES = 10_240

# How long the JS polls for the generated image to appear (3 x 30s).
_DEFAULT_POLL_ROUNDS = 3
_DEFAULT_POLL_INTERVAL_MS = 30_000


def _resolve_downloads_dir() -> Path:
    """Return Chrome's default Downloads directory for this user."""
    return Path(os.path.expanduser("~/Downloads"))


def download_via_blob_fetch(
    image_url: Optional[str],
    target_path: str,
    tab_id: int,
    *,
    min_blob_bytes: int = MIN_BLOB_BYTES,
    poll_rounds: int = _DEFAULT_POLL_ROUNDS,
    poll_interval_ms: int = _DEFAULT_POLL_INTERVAL_MS,
) -> str:
    """Build the JS payload that fetches an image as a blob and triggers a
    native Chrome download to ``~/Downloads/<basename(target_path)>``.

    Parameters
    ----------
    image_url
        If provided, the JS fetches this exact URL. If ``None``, the JS
        scans the DOM for the latest ``<img alt="Generated image ...">``
        emitted by ChatGPT (the MNR-run mode). Passing ``None`` is the
        right call when the URL is redacted by the MCP and only readable
        from inside the tab.
    target_path
        Where the caller intends to land the file. Only the basename is
        used as the download filename -- the actual move from
        ``~/Downloads/`` to ``target_path`` is the caller's job (see
        :func:`move_from_downloads`).
    tab_id
        The MCP tab id this JS will run in. Embedded as a comment in the
        emitted JS so log scraping can correlate JS errors to a tab.
    min_blob_bytes
        Reject blobs smaller than this -- the rendered image probably
        hadn't loaded yet.
    poll_rounds, poll_interval_ms
        Tunes the in-tab wait loop for the generated image to appear.

    Returns
    -------
    str
        A JavaScript snippet, ready to hand to
        ``mcp__claude-in-chrome__javascript_tool``. The snippet resolves
        to an object: ``{ok: true, blob_size, mime, w, h, filename}`` on
        success, or ``{error: "<reason>", ...}`` on failure. Known error
        reasons: ``timeout``, ``rate_limited``, ``policy_refused``,
        ``fetch_failed``, ``blob_too_small``, ``exception``.

    Notes
    -----
    The function is pure: it just emits a string. Nothing fires until
    the caller hands the string to the MCP's ``javascript_tool``.
    """
    filename = Path(target_path).name
    filename_js = json.dumps(filename)
    url_js = json.dumps(image_url) if image_url else "null"
    min_size_js = json.dumps(int(min_blob_bytes))
    rounds_js = json.dumps(int(poll_rounds))
    interval_js = json.dumps(int(poll_interval_ms))

    # Notes on the JS below:
    # * The "find latest generated image" logic mirrors the proven MNR
    #   selector chain: prefer alt-text match, fall back to the last img
    #   inside any assistant message.
    # * bodyHasIssue() short-circuits the wait loop when ChatGPT returns
    #   a refusal / rate-limit message instead of an image, so the
    #   caller can mark the entry failed without burning the full
    #   timeout.
    return f"""
// tab_id={tab_id} -- emitted by scripts/art/chatgpt_browser_download.py
(async () => {{
  const target_fname = {filename_js};
  const explicit_url = {url_js};
  const MIN_BYTES = {min_size_js};
  const POLL_ROUNDS = {rounds_js};
  const POLL_INTERVAL_MS = {interval_js};

  const findGenerated = () => {{
    const all = Array.from(document.querySelectorAll('img'));
    const gen = all.filter(i => (i.alt || '').toLowerCase().startsWith('generated image'));
    if (gen.length) return gen[gen.length - 1];
    const ai = Array.from(document.querySelectorAll('[data-message-author-role="assistant"] img'));
    if (ai.length) return ai[ai.length - 1];
    return null;
  }};

  const bodyHasIssue = () => {{
    const txt = (document.body.innerText || '').toLowerCase();
    if (/try again later|rate limit|429|too many requests/.test(txt)) return 'rate_limited';
    if (/content policy|policy violation|can'?t generate|unable to generate|i can'?t help|i cannot help/.test(txt)) return 'policy_refused';
    return null;
  }};

  let fetch_url = explicit_url;
  let img = null;
  if (!fetch_url) {{
    img = findGenerated();
    for (let i = 0; i < POLL_ROUNDS && !img; i++) {{
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      const issue = bodyHasIssue();
      if (issue) return {{error: issue}};
      img = findGenerated();
    }}
    if (!img) return {{error: 'timeout'}};
    let tries = 0;
    while ((img.naturalWidth === 0 || img.naturalHeight === 0) && tries < 6) {{
      await new Promise(r => setTimeout(r, 1000));
      tries++;
    }}
    fetch_url = img.src;
  }}

  try {{
    const resp = await fetch(fetch_url);
    if (!resp.ok) return {{error: 'fetch_failed', status: resp.status}};
    const blob = await resp.blob();
    if (blob.size < MIN_BYTES) return {{error: 'blob_too_small', size: blob.size}};
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = target_fname;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {{ URL.revokeObjectURL(url); a.remove(); }}, 5000);
    return {{
      ok: true,
      blob_size: blob.size,
      mime: blob.type,
      w: img ? img.naturalWidth : null,
      h: img ? img.naturalHeight : null,
      filename: target_fname
    }};
  }} catch (e) {{
    return {{error: 'exception', msg: e.message}};
  }}
}})()
""".strip()


def move_from_downloads(
    filename: str,
    target_path: str,
    *,
    downloads_dir: Optional[Path] = None,
    min_bytes: int = MIN_BLOB_BYTES,
) -> bool:
    """Move ``~/Downloads/<filename>`` to ``target_path``.

    Returns ``True`` on success, ``False`` if the source isn't present
    or is smaller than ``min_bytes`` (i.e. the download probably hadn't
    finished or Chrome saved an error page instead).

    The target's parent directory is created if missing.
    """
    src = (downloads_dir or _resolve_downloads_dir()) / filename
    if not src.exists():
        return False
    try:
        size = src.stat().st_size
    except OSError:
        return False
    if size < min_bytes:
        return False

    dst = Path(target_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # shutil.move handles cross-filesystem moves (Downloads and the
    # repo may live on different volumes on some setups).
    shutil.move(str(src), str(dst))
    return dst.exists() and dst.stat().st_size >= min_bytes


def move_from_downloads_via_bash(filename: str, target_path: str) -> bool:
    """Same as :func:`move_from_downloads` but shells out to ``mv``.

    Useful when the caller is an agent that prefers Bash calls for
    auditability of filesystem mutations.
    """
    src = _resolve_downloads_dir() / filename
    if not src.exists():
        return False
    dst = Path(target_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["mv", str(src), str(dst)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return dst.exists()


if __name__ == "__main__":
    # Small demo: print the JS the helper would emit for a hypothetical
    # MNR card. Useful for eyeballing the snippet before wiring it into
    # the MCP call.
    example_url = (
        "https://files.oaiusercontent.com/file-AbCdEfGhIjKlMnOp"
        "?se=2026-05-14T20%3A00%3A00Z&sp=r&sv=2024-08-04&sr=b"
        "&sig=REDACTED_SIGNATURE_TOKEN"
    )
    js = download_via_blob_fetch(
        image_url=example_url,
        target_path="frontend/public/scp-art/mnr/mnr-example.png",
        tab_id=42,
    )
    print("# === download_via_blob_fetch sample (explicit URL) ===")
    print(js)
    print()
    print("# === download_via_blob_fetch sample (DOM auto-discovery) ===")
    print(
        download_via_blob_fetch(
            image_url=None,
            target_path="frontend/public/scp-art/mnr/mnr-example.png",
            tab_id=42,
        )
    )
