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


# Spice-pack v1 card names. Markers are NOT hand-maintained here — they're
# read off ``card_def.fire_markers`` at runtime (auto-derived by the
# make_pokemon / make_trainer_* factories). To add or remove a spice card
# from the trace, just edit this list.
SPICE_CARD_NAMES: tuple[str, ...] = (
    "Mirko Vosk, Mind Drinker",
    "Voidmage Apprentice",
    "Dimir Interrogation",
    "Tox-Pawpsule",
    "Aurelia, the Warleader ex",
    "Niv-Mizzet's Quandary",
    "Jace, Memory Adept",
    "Pithing Drone",
    "Tezzy's Test",
    "Obzedat, Ghost Council ex",
    "Sanguine Sacrament",
    "Cremate",
    "Jarad, Golgari Lich Lord ex",
    "Negate the Negation",
)


def _load_spice_fire_markers() -> dict[str, frozenset[str]]:
    """Walk the BRV registry and read ``fire_markers`` off each spice card.

    Replaces the prior hand-maintained ``SPICE_FIRE_MARKERS`` dict — markers
    are now auto-derived at card-construction time by the make_* factories,
    so adding a new spice card with a new attack-name never silently drifts.

    Raises:
        RuntimeError if a card listed in ``SPICE_CARD_NAMES`` isn't in the
        registry (the trace would silently 0-fire it otherwise).
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    out: dict[str, frozenset[str]] = {}
    missing: list[str] = []
    for name in SPICE_CARD_NAMES:
        card_def = BEYOND_RAVNICA_CARDS.get(name)
        if card_def is None:
            missing.append(name)
            continue
        out[name] = frozenset(card_def.fire_markers)
    if missing:
        raise RuntimeError(
            f"Spice cards listed in SPICE_CARD_NAMES but not in the BRV "
            f"registry: {missing}. Either add them to the correct guild's "
            f"registry or remove them from SPICE_CARD_NAMES."
        )
    return out


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


def _event_payload_str(event: dict) -> str:
    return json.dumps(event.get("payload") or {}, sort_keys=True, default=str)


def _did_card_fire(
    event_log: list[dict],
    markers: frozenset[str],
) -> tuple[bool, int, list[str]]:
    """Return (fired_at_least_once, count, example_payload_strings).

    Matches the same substring-in-payload-or-source logic used before the
    refactor so per-card firing counts remain behaviour-preserving.
    """
    examples: list[str] = []
    count = 0
    for ev in event_log:
        payload_str = _event_payload_str(ev)
        source_str = str(ev.get("source") or "")
        for marker in markers:
            if marker in payload_str or marker in source_str:
                count += 1
                if len(examples) < 2:
                    examples.append(f"{ev['type']}: {payload_str[:200]}")
                break
    return count > 0, count, examples


def _preflight_marker_check() -> None:
    """Self-check that the event-trace can detect a known-firing card.

    Spins up a tiny one-Charmander Pokemon game, runs one Ember attack,
    captures the event log and asserts ``Charmander.fire_markers`` are
    detected as fired by the same matching logic the spice trace uses.
    If this fails we raise loudly so the operator doesn't read off a
    bogus "0 firings" headline from a downstream broken pipeline /
    wrongly-routed payload.
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.engine.types import EventType, ZoneType
        from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    expected_attack = "Ember"
    if expected_attack not in CHARMANDER.fire_markers:
        raise RuntimeError(
            f"Preflight: Charmander.fire_markers={sorted(CHARMANDER.fire_markers)} "
            f"is missing {expected_attack!r} — the make_pokemon auto-"
            f"derivation is broken (attack names should be auto-included)."
        )

    g = Game(mode="pokemon")
    p1 = g.add_player("preflight-p1")
    p2 = g.add_player("preflight-p2")
    # Minimal field: each side gets a Charmander + 1 fire energy attached so
    # Ember is legal. No supporters/items, no decks needed for an attack.
    a = g.create_object(
        name=CHARMANDER.name, owner_id=p1.id, zone=ZoneType.ACTIVE_SPOT,
        characteristics=CHARMANDER.characteristics, card_def=CHARMANDER,
    )
    b = g.create_object(
        name=CHARMANDER.name, owner_id=p2.id, zone=ZoneType.ACTIVE_SPOT,
        characteristics=CHARMANDER.characteristics, card_def=CHARMANDER,
    )
    e = g.create_object(
        name="Fire Energy", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
    )
    a.state.attached_energy.append(e.id)
    g.state.active_player = p1.id

    captured: list[dict] = []
    pipeline = getattr(g, "pipeline", None)
    original_emit = None
    if pipeline and hasattr(pipeline, "emit"):
        original_emit = pipeline.emit

        def trace_emit(event):
            try:
                captured.append({
                    "type": event.type.name,
                    "payload": {
                        k: (str(v) if not isinstance(v, (int, float, str, bool, list, type(None))) else v)
                        for k, v in (event.payload or {}).items()
                    },
                    "source": str(event.source) if event.source else None,
                })
            except Exception:
                pass
            return original_emit(event)

        pipeline.emit = trace_emit

    try:
        # Attack by index 0 = Charmander's first attack ('Ember'). The
        # combat manager's declare_attack emits a PKM_ATTACK_DECLARE event
        # whose payload contains ``attack_name='Ember'`` — exactly the
        # marker form the spice trace's matcher looks for.
        g.combat_manager.declare_attack(a.id, 0)
    finally:
        if original_emit:
            pipeline.emit = original_emit

    fired, count, _ = _did_card_fire(captured, CHARMANDER.fire_markers)
    if not fired:
        raise RuntimeError(
            f"Preflight marker check FAILED: expected to detect "
            f"{expected_attack!r} as fired after Charmander attacks, but "
            f"the matcher returned 0 firings. Either the event-trace's "
            f"emit-hook isn't capturing events, or the matching logic is "
            f"broken. Aborting before reporting bogus '0 firings' for "
            f"spice cards. Captured {len(captured)} events; "
            f"types={[ev['type'] for ev in captured]}"
        )


async def _run_one_traced_game(
    p1_deck_name: str, p2_deck_name: str, max_turns: int,
    p1_bias: str = "balanced", p2_bias: str = "balanced",
) -> tuple[list[dict], dict]:
    """Run one game, capture all PKM_* events, return (event_log, summary).

    ``p1_bias`` / ``p2_bias`` select a ``POKEMON_BIAS_PRESETS`` archetype
    per player (Phase 3 addition). Both default to ``balanced``.
    """
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
    ai = PokemonAIAdapter(difficulty="medium", bias=p1_bias)
    ai.player_difficulties[p1.id] = "medium"
    ai.player_difficulties[p2.id] = "medium"
    ai.set_player_bias(p1.id, p1_bias)
    ai.set_player_bias(p2.id, p2_bias)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1", default="dimir")
    parser.add_argument("--p2", default="golgari")
    parser.add_argument("--p1-bias", default="balanced",
                        help="POKEMON_BIAS_PRESETS key for p1 (Phase 3 addition)")
    parser.add_argument("--p2-bias", default="balanced",
                        help="POKEMON_BIAS_PRESETS key for p2")
    parser.add_argument("--games", type=int, default=5)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--out-dir", default="logs/brv_spice_trace")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Preflight: fail loud if the event-trace's matching logic can't even
    # detect a known-firing card (Charmander Scratch). Catches breakage
    # in the emit-hook / matching code BEFORE we report bogus "0 firings".
    _preflight_marker_check()
    print("[preflight] event-trace matcher healthy (Charmander 'Ember' detected)")

    spice_fire_markers = _load_spice_fire_markers()

    all_events: list[dict] = []
    summaries: list[dict] = []
    start = time.perf_counter()
    for i in range(args.games):
        events, summary = asyncio.run(_run_one_traced_game(
            args.p1, args.p2, max_turns=args.max_turns,
            p1_bias=args.p1_bias, p2_bias=args.p2_bias,
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
    for card_name, markers in spice_fire_markers.items():
        fired, count, examples = _did_card_fire(all_events, markers)
        card_firings[card_name] = {
            "fired_at_least_once": fired,
            "fire_count": count,
            "example_payloads": examples,
            "markers": sorted(markers),
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
