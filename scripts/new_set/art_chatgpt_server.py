#!/usr/bin/env python3
"""Engine-agnostic HTTP receiver for browser-uploaded card-art PNGs.

This is the generalization of ``scripts/_mnr_upload_server.py``. Same
behavior, but parameterized by ``--engine`` + ``--set`` so the same
binary serves every set. Listens on ``127.0.0.1:<port>`` (default
17800) and accepts::

    POST /upload?filename=foo.png  Content-Type: image/png  body: PNG bytes

Writes to the served-PNG directory (default
``frontend/public/<engine>-art/<set>/``).

Minimal CORS so browser fetches from the ``chatgpt.com`` origin work.

## Example

    python -m scripts.new_set.art_chatgpt_server --engine scp --set fbn

    # Custom port + output:
    python -m scripts.new_set.art_chatgpt_server \\
        --engine pokemon --set sv_starter --port 17801 \\
        --output-dir frontend/public/pokemon-art/sv_starter
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_BYTES = 50_000_000


def _output_dir(engine: str, set_slug: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "frontend" / "public" / f"{engine}-art" / set_slug


def make_handler(out_dir: Path, role_label: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "role": role_label}).encode())

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            fname = (qs.get("filename") or [""])[0]
            if not fname or not SAFE.match(fname):
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"bad filename"}')
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BYTES:
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"bad length"}')
                return
            data = self.rfile.read(length)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / fname
            out.write_bytes(data)
            size = out.stat().st_size
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"ok": True, "size": size, "path": str(out)}).encode()
            )

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write(f"[{role_label}] " + (fmt % args) + "\n")

    return Handler


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--engine", required=True)
    p.add_argument("--set", dest="set_slug", required=True)
    p.add_argument("--output-dir", help="override the served-PNG directory")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=17800)
    args = p.parse_args()

    out_dir = _output_dir(args.engine, args.set_slug, args.output_dir)
    role_label = f"{args.engine}-{args.set_slug}-upload"
    handler_cls = make_handler(out_dir, role_label)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    sys.stderr.write(
        f"[{role_label}] listening on http://{args.host}:{args.port} "
        f"-> {out_dir}\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
