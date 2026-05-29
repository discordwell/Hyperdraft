"""Beyond Kamigawa per-card firing trace.

Runs AI-vs-AI BK games on a chosen archetype matchup and reports, per BK card,
whether its setup_interceptors actually fired in play. The primary failure mode
this harness catches: a card that registers an interceptor but never receives
a matching event (the YGO ignition-effect gap pre-fix).

Usage:
    python -m scripts.play.bk_event_trace --p1 samurai --p2 samurai --games 5
    python -m scripts.play.bk_event_trace --p1 modified --p2 ninja --games 5 \
        --max-turns 30 --out-dir logs/bk_event_trace

Output:
    - logs/bk_event_trace/<p1>_vs_<p2>_summary.json
    - stdout: per-card firing counts, total ignition-effect activations,
      and a list of "Bottom 10" historically-dead cards with whether they
      fired this run.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Audit-identified "Bottom 10" BK ignition cards historically observed dead.
# When the new YGO_ACTIVATE_MONSTER_EFFECT surface is wired, these should
# fire at least once across a 5-game trace.
BOTTOM_10_TARGETS = [
    "Eight-and-a-Half-Tails",
    "Boseiju Mechanical Bridgekeeper",
    "Eiganjo Free-Rider",
    "Mukotai Ambusher",
    "Reckoner Bankbuster",
    "Kira",
    "Kitsune Diviner",
    "Konda's Banner-Bearer",
    "Asari Captain",
    "General Fumiko",
]


def _resolve_decks(p1: str, p2: str):
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        from src.cards.yugioh.beyond.kamigawa import (
            ARCHETYPE_DECK_BUILDERS, kamigawa_strategy, build_kamigawa_deck,
        )
    if p1 not in ARCHETYPE_DECK_BUILDERS or p2 not in ARCHETYPE_DECK_BUILDERS:
        raise SystemExit(
            f"Unknown deck. Known: {sorted(ARCHETYPE_DECK_BUILDERS)}")
    return build_kamigawa_deck(p1), build_kamigawa_deck(p2), kamigawa_strategy


class _DispatchYugiohAI:
    def __init__(self, adapters):
        self.adapters = adapters
    def get_main_phase_action(self, pid, state, ts):
        return self.adapters[pid].get_main_phase_action(pid, state, ts)
    def get_battle_action(self, pid, state, ts):
        return self.adapters[pid].get_battle_action(pid, state, ts)
    def should_enter_battle(self, pid, state):
        return self.adapters[pid].should_enter_battle(pid, state)


async def _run_one_traced_game(p1: str, p2: str, max_turns: int):
    """Run one AI-vs-AI game; capture all events.

    Returns ``(event_log, summary)``. Each event_log entry is a dict with
    ``type``, ``payload`` (filtered), ``source``, ``card_name``.
    """
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        from src.engine.game import Game
        from src.ai.yugioh_adapter import YugiohAIAdapter
    (main_a, extra_a), (main_b, extra_b), strat_fn = _resolve_decks(p1, p2)
    game = Game(mode="yugioh")
    pa = game.add_player(f"A-{p1}")
    pb = game.add_player(f"B-{p2}")
    game.setup_yugioh_player(pa, main_a, extra_a)
    game.setup_yugioh_player(pb, main_b, extra_b)
    ai_a = YugiohAIAdapter(difficulty="hard")
    ai_b = YugiohAIAdapter(difficulty="hard")
    ai_a.strategy = strat_fn(p1)
    ai_b.strategy = strat_fn(p2)
    game.turn_manager.set_ai_handler(_DispatchYugiohAI({pa.id: ai_a, pb.id: ai_b}))
    game.turn_manager.ai_players.add(pa.id)
    game.turn_manager.ai_players.add(pb.id)

    captured: list[dict] = []
    pipeline = getattr(game, "pipeline", None)
    original_emit = None
    if pipeline and hasattr(pipeline, "emit"):
        original_emit = pipeline.emit
        def trace_emit(event):
            try:
                payload = {}
                for k, v in (event.payload or {}).items():
                    if isinstance(v, (int, float, str, bool)) or v is None:
                        payload[k] = v
                    elif isinstance(v, list):
                        payload[k] = [str(x) if not isinstance(
                            x, (int, float, str, bool)) else x for x in v]
                    else:
                        payload[k] = str(v)
                captured.append({
                    "type": event.type.name,
                    "payload": payload,
                    "source": str(event.source) if event.source else None,
                    "card_name": payload.get("card_name"),
                })
            except Exception:
                pass
            return original_emit(event)
        pipeline.emit = trace_emit

    await game.turn_manager.setup_game()
    turns = 0
    for _ in range(max_turns):
        if game.is_game_over():
            break
        await game.turn_manager.run_turn()
        turns += 1
    if original_emit:
        pipeline.emit = original_emit
    winner = None
    if pa.has_lost and not pb.has_lost:
        winner = "B"
    elif pb.has_lost and not pa.has_lost:
        winner = "A"
    return captured, {
        "turns": turns,
        "p1_lp": pa.lp,
        "p2_lp": pb.lp,
        "winner": winner or "incomplete",
        "completed": game.is_game_over(),
    }


def _classify_event_owner(ev: dict) -> str | None:
    """Pick a representative card name for the event, if any."""
    pl = ev.get("payload") or {}
    return (pl.get("card_name") or ev.get("card_name") or pl.get("card")
            or pl.get("source"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1", default="samurai")
    parser.add_argument("--p2", default="samurai")
    parser.add_argument("--games", type=int, default=5)
    parser.add_argument("--max-turns", type=int, default=25)
    parser.add_argument("--out-dir", default="logs/bk_event_trace")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    all_events: list[dict] = []
    summaries = []
    start = time.perf_counter()
    for i in range(args.games):
        events, summary = asyncio.run(_run_one_traced_game(
            args.p1, args.p2, max_turns=args.max_turns))
        summaries.append(summary)
        all_events.extend(events)
        log_path = out / f"{args.p1}_vs_{args.p2}_g{i+1}.txt"
        with log_path.open("w") as f:
            f.write(f"# Game {i+1}: {args.p1} vs {args.p2}\n# {summary}\n\n")
            for ev in events:
                if ev["type"].startswith("YGO_"):
                    f.write(
                        f"{ev['type']:35s} src={ev.get('source')} "
                        f"payload={json.dumps(ev.get('payload') or {}, default=str)}\n"
                    )
        print(f"[game {i+1}/{args.games}] turns={summary['turns']:2d}  "
              f"winner={summary['winner']:12s}  log: {log_path}")

    elapsed = time.perf_counter() - start

    # Aggregate by event type.
    type_counts = Counter(ev["type"] for ev in all_events)

    # Aggregate ignition activations by card name.
    ignition_events = [ev for ev in all_events
                       if ev["type"] == "YGO_ACTIVATE_MONSTER_EFFECT"]
    ignition_cards = Counter(
        ev.get("payload", {}).get("card_name") for ev in ignition_events
        if ev.get("payload", {}).get("card_name"))
    distinct_ignition_cards = sorted(ignition_cards)

    # Card-level firing: any event whose card_name matches our target list.
    card_fire_counts: Counter[str] = Counter()
    for ev in all_events:
        owner = _classify_event_owner(ev)
        if owner:
            card_fire_counts[owner] += 1

    # Bottom-10 status.
    bottom10_status = {}
    for name in BOTTOM_10_TARGETS:
        # Count events that mention the card by any of these channels.
        n = card_fire_counts.get(name, 0)
        # Also count ignition events with this exact card name.
        n_ign = ignition_cards.get(name, 0)
        bottom10_status[name] = {
            "any_events": n,
            "ignition_events": n_ign,
            "fired_at_least_once": (n > 0 or n_ign > 0),
        }

    fired_bottom10 = sum(1 for v in bottom10_status.values()
                        if v["fired_at_least_once"])

    print(f"\n=== BK Event Trace summary: "
          f"{args.p1} vs {args.p2}, {args.games} games, "
          f"{elapsed:.1f}s ===")
    print(f"Winner counts: {Counter(s['winner'] for s in summaries)}")
    avg_turns = sum(s["turns"] for s in summaries) / max(1, len(summaries))
    print(f"Avg turns: {avg_turns:.1f}")
    print(f"Total events captured: {len(all_events)}")
    print(f"\nYGO_ACTIVATE_MONSTER_EFFECT activations: {len(ignition_events)}")
    print(f"Distinct cards firing ignition: {len(distinct_ignition_cards)}")
    if distinct_ignition_cards:
        print("  Cards: " + ", ".join(distinct_ignition_cards[:20]))

    print(f"\nBottom-10 firing status: {fired_bottom10}/10 fired")
    for name, info in bottom10_status.items():
        flag = "[FIRED]" if info["fired_at_least_once"] else "[dead] "
        print(f"  {flag} {name:36s} "
              f"events={info['any_events']:3d} ign={info['ignition_events']:3d}")

    # JSON summary.
    report_path = out / f"{args.p1}_vs_{args.p2}_summary.json"
    report_path.write_text(json.dumps({
        "matchup": f"{args.p1}_vs_{args.p2}",
        "games": args.games,
        "max_turns": args.max_turns,
        "elapsed_s": elapsed,
        "game_summaries": summaries,
        "total_events": len(all_events),
        "ignition_total": len(ignition_events),
        "ignition_distinct_cards": distinct_ignition_cards,
        "ignition_card_counts": dict(ignition_cards),
        "bottom10_status": bottom10_status,
        "top_event_types": dict(type_counts.most_common(30)),
    }, indent=2))
    print(f"\nWrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
