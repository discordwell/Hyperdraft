"""Aggregate Phase 3 per-set orphan reports into a single engine-gap punch list.

Reads .orphan_reports/<set>.json files written by the per-set opus agents.
Emits engine_gaps.md grouped by missing capability and a summary table of
dispositions per set.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / ".orphan_reports"
GAP_OUT = ROOT / "engine_gaps.md"


def main() -> None:
    if not REPORTS.exists():
        print(f"No reports directory at {REPORTS}")
        return

    reports = sorted(REPORTS.glob("*.json"))
    if not reports:
        print("No report JSON files found.")
        return

    per_set_counts: dict[str, Counter] = {}
    gaps: dict[str, list[dict]] = defaultdict(list)
    flagged_total = 0
    skipped_total = 0
    wired_total = 0
    fixed_total = 0
    consolidated_total = 0

    for path in reports:
        data = json.loads(path.read_text())
        set_name = data.get("set", path.stem + ".py")
        results = data.get("results", [])
        counts = Counter(r["disposition"] for r in results)
        per_set_counts[set_name] = counts

        wired_total += counts.get("wired", 0)
        fixed_total += counts.get("fixed", 0)
        consolidated_total += counts.get("consolidated", 0)
        flagged_total += counts.get("flagged", 0)
        skipped_total += counts.get("skipped", 0)

        for r in results:
            if r["disposition"] == "flagged":
                gap = (r.get("engine_gap") or "unspecified").strip()
                gaps[gap].append({
                    "set": set_name,
                    "fn": r.get("fn"),
                    "card_var": r.get("card_var"),
                    "notes": r.get("notes", ""),
                })

    # Build markdown
    lines = ["# MTG Real-Set Orphan Wiring — Engine Gaps", ""]
    lines.append("Aggregated from Phase 3 opus agent reports. Phase 2 (mechanical "
                 "auto-wiring of trivial orphans) added ~140 wirings on top of these "
                 "Phase 3 numbers — see git history of `src/cards/*.py` for the full diff.")
    lines.append("")
    lines.append("## Per-set Phase 3 dispositions")
    lines.append("")
    cats = ["wired", "fixed", "consolidated", "flagged", "skipped"]
    header = "| set | " + " | ".join(cats) + " | total |"
    sep = "|" + "---|" * (len(cats) + 2)
    lines.append(header)
    lines.append(sep)
    for set_name, counts in sorted(per_set_counts.items()):
        total = sum(counts.values())
        row = f"| {set_name} | " + " | ".join(str(counts.get(c, 0)) for c in cats) + f" | {total} |"
        lines.append(row)
    lines.append("")
    lines.append(f"**Totals:** wired={wired_total}, fixed={fixed_total}, "
                 f"consolidated={consolidated_total}, flagged={flagged_total}, skipped={skipped_total}")
    lines.append("")

    # Engine gaps
    if gaps:
        lines.append("## Engine gaps blocking these cards")
        lines.append("")
        lines.append("Grouped by missing capability. Each entry lists the orphan setup function "
                     "and card variable so engine work can be retargeted to unlock them.")
        lines.append("")
        sorted_gaps = sorted(gaps.items(), key=lambda kv: -len(kv[1]))
        for gap_desc, items in sorted_gaps:
            lines.append(f"### {gap_desc} ({len(items)} cards)")
            lines.append("")
            for it in items:
                note = f" — {it['notes']}" if it.get("notes") else ""
                lines.append(f"- `{it['set']}` :: `{it['fn']}` (card `{it['card_var']}`){note}")
            lines.append("")
    else:
        lines.append("## Engine gaps")
        lines.append("")
        lines.append("None reported.")

    GAP_OUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {GAP_OUT}")
    print(f"Totals: wired={wired_total} fixed={fixed_total} "
          f"consolidated={consolidated_total} flagged={flagged_total} skipped={skipped_total}")
    print(f"Distinct engine gaps: {len(gaps)}")


if __name__ == "__main__":
    main()
