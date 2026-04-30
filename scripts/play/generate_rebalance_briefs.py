#!/usr/bin/env python3
"""
Generate per-set rebalance briefs from a tournament JSON.

Each brief is a structured markdown block ready to feed to a rebalance
agent. It contains:
  - Set winrate vs each opponent
  - Top dead cards (cast/copy < 0.05)
  - Weak cards (cast/copy 0.05–0.30)
  - Broken cards (winrate-in-play > 70%)
  - High performers (cast/copy ≥ 0.7) for context
  - Caveats about mono-color deck construction

Usage:
    python scripts/play/generate_rebalance_briefs.py logs/tournament_v1.json \\
        --out-dir logs/briefs/
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


SET_FILE_PATHS = {
    "TLAC": "src/cards/custom/penultimate_avatar.py",
    "SPMC": "src/cards/custom/man_of_pider.py",
    "FINC": "src/cards/custom/princess_catholicon.py",
    "TMH":  "src/cards/custom/temporal_horizons.py",
    "LRW":  "src/cards/custom/lorwyn_custom.py",
    "SWR":  "src/cards/custom/star_wars.py",
    "DMS":  "src/cards/custom/demon_slayer.py",
    "OPC":  "src/cards/custom/one_piece.py",
    "PKH":  "src/cards/custom/pokemon_horizons.py",
    "ZLD":  "src/cards/custom/legend_of_zelda.py",
    "GHB":  "src/cards/custom/studio_ghibli.py",
    "MHA":  "src/cards/custom/my_hero_academia.py",
    "LTR":  "src/cards/custom/lord_of_the_rings.py",
    "JJK":  "src/cards/custom/jujutsu_kaisen.py",
    "AOT":  "src/cards/custom/attack_on_titan.py",
    "HPW":  "src/cards/custom/harry_potter.py",
    "MVL":  "src/cards/custom/marvel_avengers.py",
    "NRT":  "src/cards/custom/naruto.py",
    "DBZ":  "src/cards/custom/dragon_ball.py",
}

BASIC_LAND_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


def build_brief(domain: str, agg: dict, deck_info: dict) -> str:
    set_summary = agg["set_summary"].get(domain, {})
    winrate = set_summary.get("winrate", 0.0) * 100
    record = f"{set_summary.get('wins', 0)}W-{set_summary.get('losses', 0)}L-{set_summary.get('draws', 0)}D"

    # Per-opponent winrate (from matchup matrix)
    opp_records: list[tuple[str, str]] = []
    for k, v in agg["matchup"].items():
        a, b = k.split(" vs ")
        if a == domain:
            opp_records.append((b, f"{v['wins_a']}W-{v['wins_b']}L-{v['draws']}D"))
        elif b == domain:
            opp_records.append((a, f"{v['wins_b']}W-{v['wins_a']}L-{v['draws']}D"))

    # Sort by wins descending
    def _wins(rec: str) -> int:
        return int(rec.split("W")[0])
    opp_records.sort(key=lambda x: -_wins(x[1]))

    # Per-card data for this set
    cards = []
    for ref, score in agg["card_scores"].items():
        if not ref.startswith(f"{domain}::"):
            continue
        name = ref.split("::", 1)[1]
        if name in BASIC_LAND_NAMES:
            continue
        cards.append((name, score))

    # Tier buckets
    dead = [c for c in cards if c[1]["cast_per_copy"] < 0.05 and c[1]["deck_copies"] >= 2]
    weak = [c for c in cards if 0.05 <= c[1]["cast_per_copy"] < 0.30]
    ok = [c for c in cards if 0.30 <= c[1]["cast_per_copy"] < 0.70]
    strong = [c for c in cards if c[1]["cast_per_copy"] >= 0.70]
    broken = [
        c for c in strong
        if c[1]["win_rate_in_play"] > 0.70 and c[1]["in_play_at_end"] >= 4
    ]

    # Sort each bucket
    dead.sort(key=lambda kv: -kv[1]["deck_copies"])
    weak.sort(key=lambda kv: kv[1]["cast_per_copy"])
    strong.sort(key=lambda kv: -kv[1]["dmg_dealt"])
    broken.sort(key=lambda kv: -kv[1]["win_rate_in_play"])

    info = deck_info.get(domain, {})
    primary = info.get("primary_color", "?")
    file_path = SET_FILE_PATHS.get(domain, f"src/cards/custom/{domain.lower()}.py")

    lines: list[str] = []
    lines.append(f"# Rebalance Brief — {domain}")
    lines.append("")
    lines.append(f"**File:** `{file_path}`")
    lines.append(f"**Tournament winrate:** {winrate:.1f}% ({record})")
    lines.append(f"**Test deck primary color:** {primary}")
    lines.append("")
    lines.append("## Per-opponent record")
    lines.append("")
    for opp, rec in opp_records:
        lines.append(f"- vs {opp}: {rec}")
    lines.append("")

    if broken:
        lines.append(f"## Broken outliers ({len(broken)} cards) — consider toning down")
        lines.append("")
        lines.append("Cards that win >70% of games where they remain on the battlefield:")
        lines.append("")
        for name, s in broken[:10]:
            lines.append(
                f"- **{name}**  cast/copy={s['cast_per_copy']:.2f}  "
                f"wr-in-play={s['win_rate_in_play']*100:.0f}%  "
                f"dmg_dealt={int(s['dmg_dealt'])}  kills={int(s['kills'])}  "
                f"deaths={int(s['deaths'])}"
            )
        lines.append("")

    if dead:
        lines.append(f"## Dead cards ({len(dead)} cards) — never get cast")
        lines.append("")
        lines.append(
            "Cards in the test deck where fewer than 5% of copies were cast across "
            "all games. These may be too expensive, too narrow, or have unworkable "
            f"interceptors. **Caveat:** the test deck was mono-{primary} so multi-color "
            "cards may show as dead due to mana base, not design weakness."
        )
        lines.append("")
        for name, s in dead[:20]:
            lines.append(
                f"- **{name}**  copies_in_test={int(s['deck_copies'])}  "
                f"cast={int(s['cast'])}  drawn={int(s['drawn'])}"
            )
        lines.append("")

    if weak:
        lines.append(f"## Weak cards ({len(weak)} cards) — rarely cast")
        lines.append("")
        for name, s in weak[:15]:
            lines.append(
                f"- **{name}**  cast/copy={s['cast_per_copy']:.2f}  "
                f"dmg={int(s['dmg_dealt'])}  in_play_end={int(s['in_play_at_end'])}"
            )
        lines.append("")

    if strong:
        lines.append(f"## Strong performers ({len(strong)} cards) — for design reference")
        lines.append("")
        for name, s in strong[:10]:
            lines.append(
                f"- **{name}**  cast/copy={s['cast_per_copy']:.2f}  "
                f"wr-in-play={s['win_rate_in_play']*100:.0f}%  "
                f"dmg={int(s['dmg_dealt'])}  kills={int(s['kills'])}"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Rebalance Goals")
    lines.append("")
    lines.append(
        f"This set won {winrate:.0f}% of its tournament games. "
        + ("It's overpowered — tone down outliers, possibly raise costs of broken cards." if winrate > 60 else
           "It's underpowered — buff weak cards, fix dead cards, sharpen archetypes." if winrate < 35 else
           "It's near average — focus on dead cards (improving floor) and broken outliers (raising ceiling).")
    )
    lines.append("")
    lines.append("**Constraints:**")
    lines.append("- Edit ONLY the file at the path above. Don't add new cards. Don't rename cards.")
    lines.append("- Keep set theme/flavor intact. The set's mechanics (Power Level, Transform, etc.) should remain.")
    lines.append("- Tweak mana costs, P/T values, interceptor effects, or text. Prefer minimal mechanical changes.")
    lines.append("- For dead cards with mono-color cost issues, consider lowering CMC or mono-color-fying.")
    lines.append("- For broken outliers, raise cost OR weaken the trigger condition.")
    lines.append("- Aim to revise 8–15 cards total (don't churn the whole set).")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tournament_json", help="path to tournament_*.json")
    parser.add_argument("--out-dir", default="logs/briefs", help="brief output dir")
    parser.add_argument("--min-deck-copies", type=int, default=2)
    args = parser.parse_args()

    tournament_path = Path(args.tournament_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(tournament_path) as f:
        data = json.load(f)

    if "aggregate" not in data:
        print("ERROR: tournament JSON has no 'aggregate' section. Did the tournament finish?")
        sys.exit(1)

    agg = data["aggregate"]
    deck_info = data.get("deck_info", {})
    domains = data.get("domains", list(agg["set_summary"].keys()))

    for domain in domains:
        brief = build_brief(domain, agg, deck_info)
        out_path = out_dir / f"{domain}_brief.md"
        with open(out_path, "w") as f:
            f.write(brief)
        print(f"  wrote {out_path}")

    print(f"\nGenerated {len(domains)} briefs in {out_dir}/")


if __name__ == "__main__":
    main()
