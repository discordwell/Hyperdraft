"""SCP event-trace harness — answers "do cards in the rebalanced archetypes
actually fire in heuristic AI play?".

Mirrors scripts/play/brv_spice_event_trace.py but adapted for the SCP engine.
SCP differs from Pokemon in two ways:
  1. SCP_* events go through ``game.emit -> pipeline.emit`` (same hook works).
  2. ``event.source`` is an ``obj.id``, not a card name. We build an
     ``obj_id -> card_name`` registry by walking ``state.objects`` at the end
     of each game so a marker-string match works.

Usage:
    python -m scripts.play.scp_archetype_event_trace \\
        --archetype antimemetic_cold_war --opponent goi_frontline --games 5

Per-card output: how often each card's id appeared as the ``source`` of
ANY pipeline event during the game. A 0 means "the AI either never opened
the dossier or the card sat in hand the whole game" — i.e. dead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ai.scp_adapter import SCPAIAdapter
from src.cards.scp import (
    SCP_STARTER_DECKS,
    ANTIMEMETIC_COLD_WAR_NAMES,
    ETHICS_RECKONING_NAMES,
    MNESTIC_RESET_DIVISION_NAMES,
)
from src.engine.game import Game


ARCHETYPE_NAMES = {
    "antimemetic_cold_war": ANTIMEMETIC_COLD_WAR_NAMES,
    "ethics_reckoning": ETHICS_RECKONING_NAMES,
    "mnestic_reset_division": MNESTIC_RESET_DIVISION_NAMES,
}


class _DispatchSCPAIAdapter:
    def __init__(self, adapters):
        self.adapters = adapters

    async def take_turn(self, player_id, state, game):
        return await self.adapters[player_id].take_turn(player_id, state, game)


async def _run_one_traced_game(p1_deck_name, p2_deck_name, max_turns, seed):
    game = Game(mode="scp")
    p1 = game.add_player(f"P1-{p1_deck_name}")
    p2 = game.add_player(f"P2-{p2_deck_name}")
    game.setup_scp_player(p1, SCP_STARTER_DECKS[p1_deck_name]())
    game.setup_scp_player(p2, SCP_STARTER_DECKS[p2_deck_name]())
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)
    game.turn_manager.set_ai_handler(_DispatchSCPAIAdapter({
        p1.id: SCPAIAdapter(difficulty="medium", pilot="balanced"),
        p2.id: SCPAIAdapter(difficulty="medium", pilot="balanced"),
    }))

    captured = []
    pipeline = getattr(game, "pipeline", None)
    original_emit = pipeline.emit if pipeline else None

    def trace_emit(event):
        try:
            payload = {}
            for k, v in (event.payload or {}).items():
                payload[k] = v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
            captured.append({
                "type": event.type.name,
                "payload": payload,
                "source": str(event.source) if event.source else None,
                "controller": getattr(event, "controller", None),
            })
        except Exception:
            pass
        return original_emit(event)

    if pipeline:
        pipeline.emit = trace_emit

    await game.start_game()
    for _ in range(max_turns * 2):
        if game.is_game_over():
            break
        await game.run_turn()

    if pipeline and original_emit:
        pipeline.emit = original_emit

    # Build obj_id -> card_name registry from the FINAL state (includes
    # objects that were opened then moved to graveyard/forgotten).
    id_to_name = {}
    id_to_controller = {}
    for obj_id, obj in game.state.objects.items():
        if obj.card_def is not None:
            id_to_name[obj_id] = obj.card_def.name
            id_to_controller[obj_id] = obj.controller

    # Mine win-reason from the last PLAYER_LOSES event we captured (the
    # alt-win declarator stamps the reason into the payload). Lets us
    # distinguish memory_hole / ethics_audit / archives_completed wins.
    win_reasons: list[str] = []
    for ev in captured:
        if ev.get("type") == "PLAYER_LOSES":
            reason = (ev.get("payload") or {}).get("reason")
            if reason:
                win_reasons.append(str(reason))
    win_reason = win_reasons[-1] if win_reasons else None

    # MNR forgotten count (memory_hole alt-win input).
    total_forgotten = sum(len(game.state.scp_forgotten.get(pid, [])) for pid in game.state.players)

    winner_id = game.get_winner()
    summary = {
        "p1_deck": p1_deck_name,
        "p2_deck": p2_deck_name,
        "winner": p1_deck_name if winner_id == p1.id else (p2_deck_name if winner_id == p2.id else "incomplete"),
        "win_reason": win_reason,
        "turns": int(game.turn_manager.turn_number),
        "p1_site": dict(game.state.scp_sites.get(p1.id, {})),
        "p2_site": dict(game.state.scp_sites.get(p2.id, {})),
        "total_forgotten": total_forgotten,
        "p1_id": p1.id,
        "p2_id": p2.id,
    }
    return captured, summary, id_to_name, id_to_controller


def _firing_counts(events, id_to_name, target_card_names, target_player_id, id_to_controller):
    """For each card name in target_card_names, count how many pipeline events
    had source==obj_id for an obj whose card_def.name matched AND whose
    controller was target_player_id (so a card name shared between archetypes
    doesn't get cross-counted)."""
    per_card = Counter()
    per_card_event_types = defaultdict(Counter)
    target_set = set(target_card_names)
    for ev in events:
        src = ev.get("source")
        if not src:
            continue
        name = id_to_name.get(src)
        if not name or name not in target_set:
            continue
        if id_to_controller.get(src) != target_player_id:
            continue
        per_card[name] += 1
        per_card_event_types[name][ev["type"]] += 1
    return per_card, per_card_event_types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archetype", required=True, choices=list(ARCHETYPE_NAMES.keys()))
    parser.add_argument("--opponent", default="secure_contain_research",
                        help="Deck the archetype plays against. Defaults to SCR (the SCP CORE starter).")
    parser.add_argument("--games", type=int, default=5)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default="logs/scp_archetype_trace")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    target_names = ARCHETYPE_NAMES[args.archetype]
    # We test the archetype as p1. Unique card list (dedupe doubles).
    unique_target_names = list(dict.fromkeys(target_names))

    all_summaries = []
    aggregated_counts = Counter()
    aggregated_event_types = defaultdict(Counter)
    games_card_appeared_in = Counter()  # at-least-once-this-game per card

    start = time.perf_counter()
    for i in range(args.games):
        events, summary, id_to_name, id_to_controller = asyncio.run(
            _run_one_traced_game(args.archetype, args.opponent, args.max_turns, args.seed + i)
        )
        per_card, per_event_type = _firing_counts(
            events, id_to_name, target_names, summary["p1_id"], id_to_controller
        )
        for name, n in per_card.items():
            aggregated_counts[name] += n
            if n > 0:
                games_card_appeared_in[name] += 1
            for t, k in per_event_type[name].items():
                aggregated_event_types[name][t] += k
        all_summaries.append({**summary, "per_card_firings": dict(per_card)})

        reason_str = f" reason={summary.get('win_reason') or '-'}"
        print(f"[game {i+1}/{args.games}] {args.archetype} vs {args.opponent}: "
              f"turns={summary['turns']:2d} winner={summary['winner']}{reason_str} "
              f"site={summary['p1_site']}")

    elapsed = time.perf_counter() - start

    # Per-card report.
    print(f"\n=== Firing trace: {args.archetype} vs {args.opponent} "
          f"({args.games} games, {elapsed:.1f}s) ===")
    wins = sum(1 for s in all_summaries if s["winner"] == args.archetype)
    print(f"Win rate (this script, small sample): {wins}/{args.games}")
    reason_counts = Counter(s.get("win_reason") for s in all_summaries if s.get("win_reason"))
    if reason_counts:
        print("Win reasons across all games (incl. opponent losses):")
        for r, c in reason_counts.most_common():
            print(f"   - {r}: {c}")
    print()
    print(f"{'Card':45s} {'Total':>6s} {'Games':>6s} {'AvgPerGame':>10s}  Notable event types")
    print("-" * 120)
    for name in unique_target_names:
        total = aggregated_counts[name]
        games_present = games_card_appeared_in[name]
        avg = total / args.games
        # Top 3 event types this card emitted.
        top_types = aggregated_event_types[name].most_common(3)
        types_str = ", ".join(f"{t}={k}" for t, k in top_types) if top_types else "—"
        flag = " " if total > 0 else "*DEAD*"
        print(f"{flag} {name:43s} {total:>6d} {games_present:>3d}/{args.games:<3d}{avg:>10.2f}  {types_str}")

    # Bucket counts.
    dead_cards = [n for n in unique_target_names if aggregated_counts[n] == 0]
    light_cards = [n for n in unique_target_names if 0 < aggregated_counts[n] < args.games]
    active_cards = [n for n in unique_target_names if aggregated_counts[n] >= args.games]
    print(f"\nDead (0 firings across {args.games} games):       {len(dead_cards)}/{len(unique_target_names)}")
    for n in dead_cards:
        print(f"   - {n}")
    print(f"Light (<1 firing/game avg):                       {len(light_cards)}/{len(unique_target_names)}")
    for n in light_cards:
        print(f"   - {n} ({aggregated_counts[n]} total)")
    print(f"Active (>=1 firing/game avg):                     {len(active_cards)}/{len(unique_target_names)}")

    # JSON dump.
    out_path = out / f"{args.archetype}_vs_{args.opponent}.json"
    out_path.write_text(json.dumps({
        "archetype": args.archetype,
        "opponent": args.opponent,
        "games": args.games,
        "max_turns": args.max_turns,
        "elapsed_s": elapsed,
        "wins": wins,
        "per_card": {
            name: {
                "total_firings": aggregated_counts[name],
                "games_present": games_card_appeared_in[name],
                "event_types": dict(aggregated_event_types[name]),
            } for name in unique_target_names
        },
        "summaries": all_summaries,
    }, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
