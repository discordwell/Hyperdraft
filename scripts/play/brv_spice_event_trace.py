"""Run instrumented AI-vs-AI Pokemon games on a chosen matchup, trace every
event emitted by the BRV spice pack v1 cards, and report whether each spice
card actually fired with meaningful payload.

This is the play-validation step of Stage 3 — it answers "do the cards do
something interesting when actually played?" without requiring LLM pilot
orchestration. Maps directly to the user's "not mid" success criterion.

Usage:
    python -m scripts.play.brv_spice_event_trace --p1 dimir --p2 golgari --games 5 --max-turns 40

Output:
    - Per-game event traces written to logs/brv_spice_trace/<p1>_vs_<p2>_<n>.txt
    - Aggregate "did each spice card fire?" report to stdout + JSON
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Card-name → set of event-source strings that uniquely identify the card's
# effect emitting (matches `payload.source` strings in the effect_fns).
SPICE_FIRE_MARKERS: dict[str, set[str]] = {
    "Mirko Vosk, Mind Drinker": {"Mirko"},  # Lost Recall fires PKM_LOST_ZONE + PKM_REVEAL
    "Voidmage Apprentice": {"Voidmage Apprentice"},
    "Dimir Interrogation": {"Dimir Interrogation"},
    "Tox-Pawpsule": {"Tox-Pawpsule"},
    "Aurelia, the Warleader ex": {"Battalion Mark"},
    "Niv-Mizzet's Quandary": {"Niv-Mizzet's Quandary"},
    "Jace, Memory Adept": {"Jace"},
    "Pithing Drone": {"Pithing Drone"},
    "Tezzy's Test": {"Tezzy's Test"},
    "Obzedat, Ghost Council ex": {"Obzedat", "Spectral Decree", "Soul's Tax"},
    "Sanguine Sacrament": {"Sanguine Sacrament"},
    "Cremate": {"Cremate"},
    "Jarad, Golgari Lich Lord ex": {"Jarad", "Necrosurge", "Lich's Bargain"},
    "Negate the Negation": {"Negate the Negation"},
}


# Events the spice pack v1 introduced — we count these as "structurally new"
# emissions regardless of card identity.
SPICE_EVENT_TYPES = {
    "PKM_LOST_ZONE", "PKM_REVEAL_HAND", "PKM_REVEAL", "PKM_FORCE_SWITCH",
    "PKM_MOVE_ENERGY", "PKM_PRIZE_TAX", "PKM_COST_REDUCTION",
}


def _resolve_deck(name: str):
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS
    if name not in GUILD_DECK_BUILDERS:
        raise SystemExit(f"Unknown deck: {name}. Known: {sorted(GUILD_DECK_BUILDERS)}")
    return GUILD_DECK_BUILDERS[name]()


async def _run_one_traced_game(
    p1_deck_name: str, p2_deck_name: str, max_turns: int,
) -> tuple[list[dict], dict]:
    """Run one game, capture all PKM_* events, return (event_log, summary)."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.ai.pokemon_adapter import PokemonAIAdapter
    deck1 = _resolve_deck(p1_deck_name)
    deck2 = _resolve_deck(p2_deck_name)
    game = Game(mode="pokemon")
    p1 = game.add_player(f"P1-{p1_deck_name}")
    p2 = game.add_player(f"P2-{p2_deck_name}")
    game.setup_pokemon_player(p1, deck1)
    game.setup_pokemon_player(p2, deck2)
    ai = PokemonAIAdapter(difficulty="medium")
    ai.player_difficulties[p1.id] = "medium"
    ai.player_difficulties[p2.id] = "medium"
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    # Subscribe to every event by monkey-patching pipeline.emit if available.
    captured: list[dict] = []
    original_emit = None
    pipeline = getattr(game, "pipeline", None)
    if pipeline and hasattr(pipeline, "emit"):
        original_emit = pipeline.emit
        def trace_emit(event):
            try:
                captured.append({
                    "type": event.type.name,
                    "payload": {k: (str(v) if not isinstance(v, (int, float, str, bool, list, type(None))) else v)
                                for k, v in (event.payload or {}).items()},
                    "source": str(event.source) if event.source else None,
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

    summary = {
        "turns": turns,
        "completed": game.is_game_over(),
        "p1_prizes_remaining": p1.prizes_remaining,
        "p2_prizes_remaining": p2.prizes_remaining,
        "winner": (
            p1_deck_name if p2.prizes_remaining == 0
            else p2_deck_name if p1.prizes_remaining == 0
            else "incomplete"
        ),
    }
    return captured, summary


def _event_payload_str(event: dict) -> str:
    return json.dumps(event.get("payload") or {}, sort_keys=True, default=str)


def _did_spice_fire(event_log: list[dict], card_name: str) -> tuple[bool, int, list[str]]:
    """Return (fired_at_least_once, count, example_payload_strings)."""
    markers = SPICE_FIRE_MARKERS.get(card_name, set())
    examples: list[str] = []
    count = 0
    for ev in event_log:
        # Inspect payload string + source for the marker substring.
        payload_str = _event_payload_str(ev)
        source_str = str(ev.get("source") or "")
        for marker in markers:
            if marker in payload_str or marker in source_str:
                count += 1
                if len(examples) < 2:
                    examples.append(f"{ev['type']}: {payload_str[:200]}")
                break
    return count > 0, count, examples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1", default="dimir")
    parser.add_argument("--p2", default="golgari")
    parser.add_argument("--games", type=int, default=5)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--out-dir", default="logs/brv_spice_trace")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    all_events: list[dict] = []
    summaries: list[dict] = []
    start = time.perf_counter()
    for i in range(args.games):
        events, summary = asyncio.run(_run_one_traced_game(
            args.p1, args.p2, max_turns=args.max_turns,
        ))
        summaries.append(summary)
        all_events.extend(events)
        log_path = out / f"{args.p1}_vs_{args.p2}_g{i+1}.txt"
        with log_path.open("w") as f:
            f.write(f"# Game {i+1}: {args.p1} vs {args.p2}\n")
            f.write(f"# {summary}\n\n")
            for ev in events:
                if (
                    ev["type"].startswith("PKM_")
                    or ev["type"] in {"DRAW", "GAME_START"}
                ):
                    f.write(f"{ev['type']:30s} src={ev.get('source')} payload={_event_payload_str(ev)}\n")
        print(f"[game {i+1}/{args.games}] turns={summary['turns']:2d} winner={summary['winner']:12s}  log: {log_path}")

    elapsed = time.perf_counter() - start

    # Aggregate by event type.
    type_counts: Counter[str] = Counter(ev["type"] for ev in all_events)
    spice_event_counts = {t: type_counts[t] for t in SPICE_EVENT_TYPES if t in type_counts}

    # Per-card firing.
    card_firings = {}
    for card_name in SPICE_FIRE_MARKERS:
        fired, count, examples = _did_spice_fire(all_events, card_name)
        card_firings[card_name] = {
            "fired_at_least_once": fired,
            "fire_count": count,
            "example_payloads": examples,
        }

    print(f"\n=== Event-trace summary ({args.p1} vs {args.p2}, {args.games} games, {elapsed:.1f}s) ===")
    print(f"\nWinner counts: {Counter(s['winner'] for s in summaries)}")
    avg_turns = sum(s['turns'] for s in summaries) / max(1, len(summaries))
    print(f"Avg turns: {avg_turns:.1f}")

    print(f"\nSpice-EventType emissions across all games:")
    for t in sorted(SPICE_EVENT_TYPES):
        n = spice_event_counts.get(t, 0)
        flag = "✓" if n > 0 else "✗"
        print(f"  {flag} {t:25s} {n} emissions")

    print(f"\nPer-card firing:")
    fired_count = 0
    for name, info in card_firings.items():
        flag = "✓" if info["fired_at_least_once"] else "✗"
        print(f"  {flag} {name:36s} {info['fire_count']} firings")
        if info["fired_at_least_once"]:
            fired_count += 1
        for ex in info["example_payloads"][:1]:
            print(f"     example: {ex[:120]}")
    print(f"\n{fired_count}/{len(card_firings)} spice cards fired at least once across {args.games} games")

    # Write structured report.
    report_path = out / f"{args.p1}_vs_{args.p2}_summary.json"
    report_path.write_text(json.dumps({
        "matchup": f"{args.p1}_vs_{args.p2}",
        "games": args.games,
        "max_turns": args.max_turns,
        "elapsed_s": elapsed,
        "game_summaries": summaries,
        "spice_event_counts": spice_event_counts,
        "card_firings": card_firings,
    }, indent=2))
    print(f"\nWrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
