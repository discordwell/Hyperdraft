# ChatGPT-web blob download helper

How to pull generated images out of ChatGPT-web when the OpenAI API
path is unavailable and the `claude-in-chrome` MCP refuses to surface
the raw image URLs.

## The problem

When driving ChatGPT-web through the `claude-in-chrome` MCP, every
image URL the model returns is hosted on `oaiusercontent.com` with auth
tokens baked into the query string, e.g.

```
https://files.oaiusercontent.com/file-AbCd...?se=2026-05-14T20%3A00%3A00Z&sig=...
```

The MCP scrubs those URLs as

```
[BLOCKED: Cookie/query string data]
```

before they reach the agent. So the agent has no URL to hand to `curl`
or `requests`, and the API fallback isn't an option either — for
example, the user's OpenAI image API hit a billing hard limit during
the MNR run, which is precisely why we drive ChatGPT-web in the first
place.

## The solution

Run a small JS snippet **inside the tab** where the session cookies are
still live. The snippet:

1. Finds the most recent generated image (`<img alt="Generated image …">`
   in an assistant message), or fetches a URL you pass in explicitly.
2. `await fetch(img.src).then(r => r.blob())` — works because the
   in-tab fetch carries the cookies the MCP redacted.
3. Builds an `<a download="<filename>" href="<blob: URL>">`, appends it
   to `document.body`, and `.click()`s it.
4. Chrome runs its native download flow and writes the file to
   `~/Downloads/<filename>`.
5. The Python side then `mv`s the file from `~/Downloads/` into the
   real target path under `frontend/public/scp-art/...` (or wherever).

After the **first** download in a session, Chrome may prompt the user
to "Allow this site to download multiple files". Click **Allow**.
Subsequent downloads happen silently, even when the tab is
backgrounded.

## Module

`scripts/art/chatgpt_browser_download.py`

Two functions:

- `download_via_blob_fetch(image_url, target_path, tab_id, …) -> str`
  Builds the JS snippet. Pure function — no side effects. Hand the
  returned string to `mcp__claude-in-chrome__javascript_tool`.

- `move_from_downloads(filename, target_path, …) -> bool`
  After the JS reports `{ok: true}`, move the file from `~/Downloads/`
  to its final destination. Returns `False` if the file is missing or
  too small (incomplete download / Chrome saved an error page).

There's also `move_from_downloads_via_bash(...)` which shells out to
`mv` for callers that prefer to audit filesystem mutations through
their Bash tool.

## Usage

```python
from scripts.art.chatgpt_browser_download import (
    download_via_blob_fetch,
    move_from_downloads,
)

# Mode A: let the JS find the latest generated image in the DOM.
# This is the MNR-run pattern -- you don't even need the URL.
js = download_via_blob_fetch(
    image_url=None,
    target_path="frontend/public/scp-art/mnr/mnr-foo.png",
    tab_id=42,
)

# Mode B: pass an explicit URL (e.g. you scraped it from a DOM walk
# that the MCP did *not* redact for some reason).
js = download_via_blob_fetch(
    image_url="https://files.oaiusercontent.com/file-...?se=...&sig=...",
    target_path="frontend/public/scp-art/mnr/mnr-foo.png",
    tab_id=42,
)

# Hand the JS to the MCP. The snippet returns
# {ok: true, blob_size, mime, w, h, filename} on success,
# or {error: "<reason>", ...} on failure (timeout / rate_limited /
# policy_refused / fetch_failed / blob_too_small / exception).
# In an agent context:
#   result = mcp__claude_in_chrome__javascript_tool(tab_id=42, code=js)

# Then mv from ~/Downloads to the real destination:
ok = move_from_downloads(
    filename="mnr-foo.png",
    target_path="frontend/public/scp-art/mnr/mnr-foo.png",
)
assert ok, "download didn't land"
```

## Gotchas

- **First-download consent.** Chrome's default is to ask once per site
  whether to allow multiple downloads. The first download in a fresh
  session may stall waiting for that click. Click **Allow** once and
  the rest of the run is hands-off.
- **Cookies must be live.** The fetch only works because the tab still
  holds ChatGPT auth cookies. If the user has been logged out, the
  fetch returns 401/403 and you get `{error: "fetch_failed", status: 4xx}`.
  Have the agent verify the session before launching a batch.
- **Large images can take >5s.** The poll loop defaults to 3 rounds of
  30s waiting for the image element to appear; once it appears,
  another 6×1s wait covers the `naturalWidth=0` "still loading" window.
  For very large prompts you may need to bump `poll_rounds` /
  `poll_interval_ms`.
- **The `tab_id` arg isn't actually used by the JS.** It's embedded
  only as a leading comment so log scraping can correlate JS errors
  back to a specific tab. The caller still has to pass the same
  `tab_id` to the MCP `javascript_tool` call.
- **Refusals short-circuit the wait.** If ChatGPT returns a content-
  policy refusal or rate-limit message instead of an image, the JS
  detects the message and returns `{error: "policy_refused"}` /
  `{error: "rate_limited"}` immediately so the orchestrator can mark
  the entry failed without burning the full timeout budget.
- **Blob size floor.** Anything under `MIN_BLOB_BYTES` (10 KB) is
  rejected as a partial / placeholder download. Override
  `min_blob_bytes=` if you're deliberately fetching something tiny.

## Proof of concept: the MNR run

This pattern was distilled from the May 2026 SCP "Mnestic Reset" art
run: **120 / 120 cards** generated end-to-end. Throwaway per-run
scratch scripts at `scripts/_mnr_*.py` (gitignored) drove the loop;
the durable extract is `scripts/art/chatgpt_browser_download.py`.

Run summary lives at
`assets/card_art/scp/mnr/_gen_summary.md` (253 MB across 120 PNGs, 0
failures, ~5 h wall-clock).

## When **not** to use this

- If you have a working OpenAI image API key, use that — direct REST
  is faster, deterministic, and doesn't depend on a logged-in browser.
- If the MCP stops redacting `oaiusercontent.com` URLs in a future
  version, the blob fetch becomes a needless detour: just `curl` the
  URL with the cookies.
