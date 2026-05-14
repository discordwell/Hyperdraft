#!/usr/bin/env python3
"""Engine-agnostic queue manager for the ChatGPT-web card-art batch loop.

This is the generalization of ``scripts/_mnr_image_helper.py``. Same
subcommands, same JSON shapes, but parameterized by ``--engine`` +
``--set`` so the same tool works for any Hyperdraft set (SCP / Pokemon /
MTG-custom / depths / ...).

## Path convention

By default, the queue + status live at::

    assets/card_art/<engine>/<set>/draw_prompts.json     # written by art_harness --mode manual
    assets/card_art/<engine>/<set>/_gen_status.json      # this script's bookkeeping
    assets/card_art/<engine>/<set>/_gen_log.json         # final run log (after `finalize`)
    assets/card_art/<engine>/<set>/_gen_summary.md       # human-readable summary

and the *served* PNGs (downloaded from ChatGPT) land at::

    frontend/public/<engine>-art/<set>/<output_file>.png

Override either via ``--queue-dir`` / ``--output-dir`` if your set ships
elsewhere (Unity StreamingAssets, etc.).

## Subcommands

    next                 print JSON of next pending entry (or {"done": true})
    mark-done <ID>       mark an entry completed
    mark-fail <ID> <REASON>   mark an entry failed
    stats                print stats JSON
    prompt <ID>          print the raw prompt for an entry
    finalize <STARTED_AT>     write _gen_log.json and _gen_summary.md

## Example

    # FBN (this set):
    python -m scripts.new_set.art_chatgpt_queue --engine scp --set fbn next

    # MNR (the prior set — see scripts/_mnr_image_helper.py for the
    # one-line backwards-compat shim):
    python -m scripts.new_set.art_chatgpt_queue --engine scp --set mnr stats
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIN_BYTES = 10240


def _queue_dir(engine: str, set_slug: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "assets" / "card_art" / engine / set_slug


def _output_dir(engine: str, set_slug: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "frontend" / "public" / f"{engine}-art" / set_slug


class QueueIO:
    def __init__(self, queue_dir: Path, output_dir: Path):
        self.queue_dir = queue_dir
        self.output_dir = output_dir
        self.queue_path = queue_dir / "draw_prompts.json"
        self.status_path = queue_dir / "_gen_status.json"
        self.log_path = queue_dir / "_gen_log.json"
        self.summary_path = queue_dir / "_gen_summary.md"

    def load_queue(self) -> dict[str, Any]:
        if not self.queue_path.exists():
            raise SystemExit(
                f"queue not found: {self.queue_path}\n"
                f"hint: run `python -m scripts.new_set.art_harness "
                f"--mode manual --out-dir {self.queue_dir} ...` first."
            )
        with open(self.queue_path) as f:
            return json.load(f)

    def load_status(self) -> dict[str, Any]:
        if self.status_path.exists():
            with open(self.status_path) as f:
                return json.load(f)
        return {"completed": [], "failed": []}

    def save_status(self, s: dict[str, Any]) -> None:
        tmp = self.status_path.with_suffix(".tmp")
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, self.status_path)


def cmd_next(io: QueueIO) -> None:
    q = io.load_queue()
    s = io.load_status()
    completed = set(s["completed"])
    failed_ids = {e["id"] for e in s["failed"]}
    for entry in q["entries"]:
        if entry["id"] in completed or entry["id"] in failed_ids:
            continue
        out = io.output_dir / entry["output_file"]
        if out.exists() and out.stat().st_size > MIN_BYTES:
            # Auto-mark as completed when file is present + nontrivial
            s["completed"].append(entry["id"])
            io.save_status(s)
            completed.add(entry["id"])
            continue
        remaining = sum(
            1
            for e in q["entries"]
            if e["id"] not in completed
            and e["id"] not in failed_ids
            and not (io.output_dir / e["output_file"]).exists()
        )
        print(
            json.dumps(
                {
                    "done": False,
                    "id": entry["id"],
                    "card_name": entry["card_name"],
                    "output_file": entry["output_file"],
                    "prompt": entry["prompt"],
                    "out_path": str(out),
                    "remaining": remaining,
                }
            )
        )
        return
    print(json.dumps({"done": True}))


def cmd_mark_done(io: QueueIO, eid: str) -> None:
    s = io.load_status()
    if eid not in s["completed"]:
        s["completed"].append(eid)
    io.save_status(s)
    print(json.dumps({"ok": True, "completed_count": len(s["completed"])}))


def cmd_mark_fail(io: QueueIO, eid: str, reason: str) -> None:
    s = io.load_status()
    s["failed"] = [e for e in s["failed"] if e["id"] != eid]
    s["failed"].append(
        {"id": eid, "reason": reason, "at": datetime.now(timezone.utc).isoformat()}
    )
    io.save_status(s)
    print(json.dumps({"ok": True, "failed_count": len(s["failed"])}))


def cmd_stats(io: QueueIO) -> None:
    s = io.load_status()
    q = io.load_queue()
    completed = set(s["completed"])
    failed_ids = {e["id"] for e in s["failed"]}
    total = len(q["entries"])
    done_files = 0
    total_bytes = 0
    for entry in q["entries"]:
        out = io.output_dir / entry["output_file"]
        if out.exists():
            done_files += 1
            total_bytes += out.stat().st_size
    pending = total - len(completed) - len(failed_ids)
    print(
        json.dumps(
            {
                "total": total,
                "completed_in_status": len(completed),
                "failed_in_status": len(failed_ids),
                "on_disk": done_files,
                "pending": pending,
                "total_disk_kb": round(total_bytes / 1024, 1),
            }
        )
    )


def cmd_prompt(io: QueueIO, eid: str) -> None:
    q = io.load_queue()
    for entry in q["entries"]:
        if entry["id"] == eid:
            sys.stdout.write(entry["prompt"])
            return
    sys.stderr.write(f"No entry {eid}\n")
    sys.exit(1)


def cmd_finalize(io: QueueIO, started_at: str, engine: str, set_slug: str) -> None:
    s = io.load_status()
    q = io.load_queue()
    total = len(q["entries"])
    completed = s["completed"]
    failed = s["failed"]
    total_bytes = 0
    sample: list[str] = []
    for entry in q["entries"]:
        out = io.output_dir / entry["output_file"]
        if out.exists() and out.stat().st_size > MIN_BYTES:
            total_bytes += out.stat().st_size
            if len(sample) < 3:
                sample.append(entry["output_file"])
    now = datetime.now(timezone.utc).isoformat()
    log = {
        "engine": engine,
        "set": set_slug,
        "started_at": started_at,
        "ended_at": now,
        "total_entries": total,
        "completed": len(completed),
        "failed": len(failed),
        "failed_entries": failed,
        "total_disk_kb": round(total_bytes / 1024, 1),
    }
    with open(io.log_path, "w") as f:
        json.dump(log, f, indent=2)

    md = [
        f"# {engine.upper()} / {set_slug.upper()} Card Art Generation Log",
        "",
        f"- Started: {started_at}",
        f"- Ended: {now}",
        f"- Total entries: {total}",
        f"- Completed: **{len(completed)}**",
        f"- Failed: **{len(failed)}**",
        f"- Total disk: **{round(total_bytes/1024/1024, 2)} MB** "
        f"({round(total_bytes/1024,1)} KB)",
        "",
        "## Sample completed files",
        "",
    ]
    served_rel = io.output_dir.relative_to(PROJECT_ROOT) if io.output_dir.is_relative_to(PROJECT_ROOT) else io.output_dir
    for s_ in sample:
        md.append(f"- `{served_rel}/{s_}`")
    if failed:
        md.append("")
        md.append("## Failures")
        md.append("")
        reasons = Counter(e.get("reason", "unknown") for e in failed)
        for r, c in reasons.most_common():
            md.append(f"- **{r}**: {c}")
        md.append("")
        md.append("### Detailed list")
        md.append("")
        for f_ in failed:
            md.append(f"- `{f_['id']}` -> {f_.get('reason','?')}")
    with open(io.summary_path, "w") as f:
        f.write("\n".join(md) + "\n")
    print(
        json.dumps(
            {
                "completed": len(completed),
                "failed": len(failed),
                "kb": round(total_bytes / 1024, 1),
            }
        )
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--engine", required=True, help="engine slug (scp / pokemon / mtg-custom / ...)")
    p.add_argument("--set", dest="set_slug", required=True, help="set slug (fbn / mnr / sv_starter / ...)")
    p.add_argument("--queue-dir", help="override path to the queue directory")
    p.add_argument("--output-dir", help="override path to the served-PNG directory")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("next")
    md = sub.add_parser("mark-done"); md.add_argument("entry_id")
    # legacy alias to keep backwards-compat one-liners short
    md2 = sub.add_parser("mark_done"); md2.add_argument("entry_id")
    mf = sub.add_parser("mark-fail"); mf.add_argument("entry_id"); mf.add_argument("reason", nargs="?", default="unknown")
    mf2 = sub.add_parser("mark_fail"); mf2.add_argument("entry_id"); mf2.add_argument("reason", nargs="?", default="unknown")
    sub.add_parser("stats")
    pr = sub.add_parser("prompt"); pr.add_argument("entry_id")
    fn = sub.add_parser("finalize"); fn.add_argument("started_at", nargs="?", default="")

    args = p.parse_args()
    io = QueueIO(
        queue_dir=_queue_dir(args.engine, args.set_slug, args.queue_dir),
        output_dir=_output_dir(args.engine, args.set_slug, args.output_dir),
    )
    cmd = args.cmd.replace("_", "-")
    if cmd == "next":
        cmd_next(io)
    elif cmd == "mark-done":
        cmd_mark_done(io, args.entry_id)
    elif cmd == "mark-fail":
        cmd_mark_fail(io, args.entry_id, args.reason)
    elif cmd == "stats":
        cmd_stats(io)
    elif cmd == "prompt":
        cmd_prompt(io, args.entry_id)
    elif cmd == "finalize":
        started = args.started_at or datetime.now(timezone.utc).isoformat()
        cmd_finalize(io, started, args.engine, args.set_slug)
    else:
        p.error(f"unknown subcommand: {cmd}")


if __name__ == "__main__":
    main()
