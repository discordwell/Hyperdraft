#!/usr/bin/env python3
"""Engine-agnostic JS-payload emitter for ChatGPT-web card-art batches.

This is the generalization of ``scripts/_mnr_make_js.py``. It reads an
entry from the queue's ``draw_prompts.json`` and prints the JavaScript
snippet that:

    send      — inserts the prompt into ChatGPT's composer and clicks Send
    download  — waits for the generated image and triggers a blob download

The JS itself is engine-agnostic — it talks to chatgpt.com's DOM, not to
the engine's card data. Only the input path needed parameterizing.

## Example

    python -m scripts.new_set.art_chatgpt_js send \\
        --engine scp --set fbn --id phyrexian_strain__scp_fbn_1138

    python -m scripts.new_set.art_chatgpt_js download \\
        --engine scp --set fbn --id phyrexian_strain__scp_fbn_1138
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _queue_dir(engine: str, set_slug: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "assets" / "card_art" / engine / set_slug


def load_entry(queue_dir: Path, eid: str) -> dict:
    queue_path = queue_dir / "draw_prompts.json"
    if not queue_path.exists():
        raise SystemExit(f"queue not found: {queue_path}")
    with open(queue_path) as f:
        d = json.load(f)
    for e in d["entries"]:
        if e["id"] == eid:
            return e
    raise SystemExit(f"no entry {eid} in {queue_path}")


def cmd_send(entry: dict) -> None:
    prompt_js = json.dumps(entry["prompt"])
    print(
        f"""
(async () => {{
  const prompt = {prompt_js};
  const composer = document.querySelector('#prompt-textarea');
  if (!composer) return {{error: 'no_composer'}};
  composer.focus();
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(composer);
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('delete', false, null);
  const inserted = document.execCommand('insertText', false, prompt);
  if (!inserted) return {{error: 'insertText_failed'}};
  await new Promise(r => setTimeout(r, 250));
  if (composer.innerText.length < prompt.length * 0.95) {{
    return {{error: 'text_too_short', got: composer.innerText.length, want: prompt.length}};
  }}
  const sendBtn = document.querySelector('[data-testid="send-button"]') || document.querySelector('button[aria-label*="Send" i]');
  if (!sendBtn) return {{error: 'no_send_button'}};
  if (sendBtn.disabled) return {{error: 'send_disabled'}};
  sendBtn.click();
  return {{ok: true, sent_chars: prompt.length, t: Date.now()}};
}})()
""".strip()
    )


def cmd_download(entry: dict, upload_url: str | None) -> None:
    fname = entry["output_file"]
    fname_js = json.dumps(fname)
    upload_js = json.dumps(upload_url) if upload_url else "null"
    print(
        f"""
(async () => {{
  const target_fname = {fname_js};
  const upload_base = {upload_js};
  const findGenerated = () => {{
    const all = Array.from(document.querySelectorAll('img'));
    const gen = all.filter(i => (i.alt || '').toLowerCase().startsWith('generated image'));
    if (gen.length) return gen[gen.length-1];
    const ai = Array.from(document.querySelectorAll('[data-message-author-role="assistant"] img'));
    if (ai.length) return ai[ai.length-1];
    return null;
  }};
  const bodyHasIssue = () => {{
    const txt = (document.body.innerText || '').toLowerCase();
    if (/try again later|rate limit|429|too many requests/.test(txt)) return 'rate_limited';
    if (/content policy|policy violation|can'?t generate|unable to generate|i can'?t help|i cannot help/.test(txt)) return 'policy_refused';
    return null;
  }};
  let img = findGenerated();
  for (let i = 0; i < 3 && !img; i++) {{
    await new Promise(r => setTimeout(r, 30000));
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
  try {{
    const resp = await fetch(img.src);
    if (!resp.ok) return {{error: 'fetch_failed', status: resp.status}};
    const blob = await resp.blob();
    if (blob.size < 10240) return {{error: 'blob_too_small', size: blob.size}};
    if (upload_base) {{
      const up = await fetch(upload_base + '?filename=' + encodeURIComponent(target_fname), {{
        method: 'POST',
        headers: {{'Content-Type': blob.type || 'image/png'}},
        body: blob,
      }});
      const upj = await up.json().catch(() => ({{}}));
      if (!up.ok) return {{error: 'upload_failed', status: up.status, server: upj}};
      return {{ok: true, blob_size: blob.size, mime: blob.type, w: img.naturalWidth, h: img.naturalHeight, filename: target_fname, uploaded: true, server: upj}};
    }} else {{
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = target_fname;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {{ URL.revokeObjectURL(url); a.remove(); }}, 5000);
      return {{ok: true, blob_size: blob.size, mime: blob.type, w: img.naturalWidth, h: img.naturalHeight, filename: target_fname, uploaded: false}};
    }}
  }} catch (e) {{
    return {{error: 'exception', msg: e.message}};
  }}
}})()
""".strip()
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--engine", required=True)
    p.add_argument("--set", dest="set_slug", required=True)
    p.add_argument("--id", dest="entry_id", required=True)
    p.add_argument("--queue-dir", help="override the queue directory")
    p.add_argument(
        "--upload-url",
        default="http://127.0.0.1:17800/upload",
        help="POST endpoint for the download JS to push the PNG to "
        "(set to empty string '' to use blob-download fallback)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("send")
    sub.add_parser("download")

    args = p.parse_args()
    qdir = _queue_dir(args.engine, args.set_slug, args.queue_dir)
    entry = load_entry(qdir, args.entry_id)
    if args.cmd == "send":
        cmd_send(entry)
    elif args.cmd == "download":
        upload = args.upload_url or None
        cmd_download(entry, upload)


if __name__ == "__main__":
    main()
