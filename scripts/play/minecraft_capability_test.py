"""
Minecraft TCG capability test harness.

Mirrors scripts/play/capability_test.py for the Minecraft engine. Builds a
synergy deck around a focal card, runs N AI-vs-AI games against a baseline
deck, and reports a capability score so build-around redesigns can be
validated before commit.

Differences from the MTG version:
  - No mana / lands. Decks are 50 card-defs (2 of each unique by convention).
  - Cards play directly from HAND -> BATTLEFIELD (mobs, structures, blocks,
    tools) or HAND -> GRAVEYARD (actions). No stack.
  - Game runs `MinecraftTurnManager` + `MinecraftAIAdapter`.
  - `is_permanent` test maps:
        Action -> use deck winrate (one-shots, sorcery-equivalent)
        Mob/Structure/Block/Tool -> use win-rate-when-in-play
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from src.ai.minecraft_adapter import MinecraftAIAdapter
from src.cards.minecraft import MINECRAFT_CARDS, MINECRAFT_STARTER_DECKS
from src.engine.game import Game
from src.engine.types import CardDefinition, CardType, Event, EventType, ZoneType


# ---------------------------------------------------------------------------
# Synergy registry loader
# ---------------------------------------------------------------------------


def _load_synergy_registry() -> dict[str, list[str]]:
    """Hand-curated focal -> partner-list mapping for Minecraft spice cards."""
    try:
        from src.cards.minecraft.synergies import MC_SYNERGY_PACKAGES
        return MC_SYNERGY_PACKAGES
    except ImportError:
        return {}


# ---------------------------------------------------------------------------
# Deck construction
# ---------------------------------------------------------------------------


def build_synergy_deck(
    focal_name: str,
    partner_names: list[str],
    focal_copies: int = 4,
    partner_copies: int = 2,
    target_size: int = 50,
) -> list[CardDefinition]:
    """
    Build a 50-card MC deck: 4x focal + 2x partners + filler from the
    builder/miner/raider pool to round out the curve.
    """
    deck: list[CardDefinition] = []

    if focal_name not in MINECRAFT_CARDS:
        raise ValueError(f"Focal card not found in MINECRAFT_CARDS: {focal_name!r}")
    deck.extend([MINECRAFT_CARDS[focal_name]] * focal_copies)

    for pname in partner_names:
        if pname not in MINECRAFT_CARDS:
            raise ValueError(f"Synergy partner not found: {pname!r}")
        deck.extend([MINECRAFT_CARDS[pname]] * partner_copies)

    # Fill with sane curve cards (cheap workers + 1-mana actions + Bed) so the
    # deck can actually function. Pick from BUILDER_NAMES which is the most
    # generic of the three starter pools.
    from src.cards.minecraft.alpha import BUILDER_NAMES
    filler_pool = [name for name in BUILDER_NAMES
                   if name != focal_name and name not in partner_names]
    deck_size = len(deck)
    i = 0
    while len(deck) < target_size and filler_pool:
        deck.append(MINECRAFT_CARDS[filler_pool[i % len(filler_pool)]])
        i += 1

    return deck[:target_size]


def _baseline_deck(deck_label: str = "raider") -> list[CardDefinition]:
    """Default opposing deck — Raider is the most aggressive, gives a
    workable sparring partner that tries to win."""
    factory = MINECRAFT_STARTER_DECKS.get(deck_label)
    if not factory:
        raise ValueError(f"Unknown baseline deck: {deck_label}")
    return factory()


# ---------------------------------------------------------------------------
# Focal-in-opener: stack one copy of the focal card on top of the library
# before opening hand draw.
# ---------------------------------------------------------------------------


def _make_stack_focal_hook(focal_name: str, copies_to_stack: int = 1, target_seat: str = "p1"):
    def hook(game, p1_id: str, p2_id: str) -> None:
        target_id = p2_id if target_seat == "p2" else p1_id
        library = game.state.zones.get(f"library_{target_id}")
        if not library or not library.objects:
            return
        focal_indices: list[int] = []
        for i, oid in enumerate(library.objects):
            obj = game.state.objects.get(oid)
            if obj and obj.name == focal_name:
                focal_indices.append(i)
                if len(focal_indices) >= copies_to_stack:
                    break
        for slot, src_idx in enumerate(focal_indices):
            if src_idx >= len(library.objects):
                continue
            library.objects.insert(slot, library.objects.pop(src_idx))
    return hook


# ---------------------------------------------------------------------------
# Per-card stat collection (Minecraft-flavored).
# Walks the event log + final state to compute cast / in_play / on_winning.
# ---------------------------------------------------------------------------


def _card_ref(label: str, card_def: CardDefinition) -> str:
    return f"{label}::{card_def.name}"


def _collect_minecraft_card_stats(
    game: Game,
    p1_id: str,
    p2_id: str,
    p1_label: str,
    p2_label: str,
    deck1: list[CardDefinition],
    deck2: list[CardDefinition],
    winner_id: Optional[str],
) -> dict[str, dict[str, float]]:
    state = game.state
    stats: dict[str, dict[str, float]] = defaultdict(lambda: {
        "deck_copies": 0,
        "cast": 0,
        "in_play_at_end": 0,
        "in_graveyard_at_end": 0,
        "on_winning_side": 0,
    })
    cast_object_ids: set[str] = set()

    def _name_for(obj_id: Optional[str]) -> Optional[tuple[str, str]]:
        if not obj_id:
            return None
        obj = state.objects.get(obj_id)
        if not obj:
            return None
        cd = getattr(obj, "card_def", None)
        if not cd:
            return None
        owner = obj.owner
        label = p1_label if owner == p1_id else p2_label if owner == p2_id else None
        if label is None:
            return None
        return _card_ref(label, cd), label

    # Seed deck copies
    for cd in deck1:
        stats[_card_ref(p1_label, cd)]["deck_copies"] += 1
    for cd in deck2:
        stats[_card_ref(p2_label, cd)]["deck_copies"] += 1

    # Walk event log: count casts when card leaves HAND (to BATTLEFIELD or
    # GRAVEYARD — actions resolve directly to graveyard in MC).
    log = getattr(state, "event_log", []) or []
    for ev in log:
        et = getattr(ev, "type", None)
        payload = getattr(ev, "payload", None) or {}
        if et != EventType.ZONE_CHANGE:
            continue
        obj_id = payload.get("object_id")
        if not obj_id or obj_id in cast_object_ids:
            continue
        from_z = payload.get("from_zone_type")
        to_z = payload.get("to_zone_type")
        if from_z == ZoneType.HAND and to_z in (ZoneType.BATTLEFIELD, ZoneType.GRAVEYARD):
            ref = _name_for(obj_id)
            if ref:
                stats[ref[0]]["cast"] += 1
                cast_object_ids.add(obj_id)

    # Final zones
    for obj_id, obj in state.objects.items():
        if not obj or not getattr(obj, "card_def", None):
            continue
        owner = obj.owner
        label = p1_label if owner == p1_id else p2_label if owner == p2_id else None
        if label is None:
            continue
        ref = _card_ref(label, obj.card_def)
        if obj.zone == ZoneType.BATTLEFIELD:
            stats[ref]["in_play_at_end"] += 1
            if winner_id and owner == winner_id:
                stats[ref]["on_winning_side"] += 1
        elif obj.zone == ZoneType.GRAVEYARD:
            stats[ref]["in_graveyard_at_end"] += 1

    return dict(stats)


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------


@dataclass
class MCGameResult:
    p1_label: str
    p2_label: str
    winner_label: Optional[str]
    turns: int
    p1_life: int
    p2_life: int
    duration_s: float
    error: Optional[str] = None
    card_stats: dict[str, dict[str, float]] = field(default_factory=dict)


async def play_one_minecraft_game(
    deck1: list[CardDefinition],
    deck2: list[CardDefinition],
    p1_label: str = "P1",
    p2_label: str = "P2",
    difficulty: str = "medium",
    bias_p1: Any = None,
    bias_p2: Any = None,
    max_turns: int = 25,
    per_turn_timeout_s: float = 3.0,
    wall_deadline_s: float = 30.0,
    pre_start_hook: Optional[Any] = None,
) -> MCGameResult:
    start = time.perf_counter()
    try:
        game = Game(mode="minecraft")
        p1 = game.add_player(p1_label)
        p2 = game.add_player(p2_label)

        # setup_minecraft_player handles avatar HP, materials, biomes, AND
        # creates the library objects from the deck list.
        game.setup_minecraft_player(p1, deck1)
        game.setup_minecraft_player(p2, deck2)

        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        game.set_ai_player(p1.id)
        game.set_ai_player(p2.id)

        # Per-seat AI biases — variant-tournament builds dispatch this
        # so each player can run a different strategy. Forwards both
        # `take_turn` (offense) and `choose_blockers` (defense) so the
        # bias preset's mining/attack/block axes apply to the right seat.
        ai_p1 = MinecraftAIAdapter(difficulty=difficulty, bias=bias_p1)
        ai_p2 = MinecraftAIAdapter(difficulty=difficulty, bias=bias_p2)
        if bias_p1 == bias_p2 or (bias_p1 is None and bias_p2 is None):
            game.turn_manager.set_ai_handler(ai_p1)
        else:
            ai_by_player = {p1.id: ai_p1, p2.id: ai_p2}

            class _DispatchAdapter:
                async def take_turn(self, player_id, state, game_):
                    adapter = ai_by_player.get(player_id) or ai_p1
                    return await adapter.take_turn(player_id, state, game_)

                def choose_blockers(self, state, defender_id, attackers):
                    adapter = ai_by_player.get(defender_id) or ai_p1
                    return adapter.choose_blockers(state, defender_id, attackers)

            game.turn_manager.set_ai_handler(_DispatchAdapter())

        if pre_start_hook is not None:
            pre_start_hook(game, p1.id, p2.id)

        await asyncio.wait_for(game.start_game(), timeout=10.0)

        turn_count = 0
        timed_out = False
        wall_deadline = time.perf_counter() + wall_deadline_s
        while turn_count < max_turns and not game.is_game_over():
            if time.perf_counter() > wall_deadline:
                timed_out = True
                break
            try:
                await asyncio.wait_for(
                    game.turn_manager.run_turn(),
                    timeout=per_turn_timeout_s,
                )
            except asyncio.TimeoutError:
                timed_out = True
                break
            turn_count += 1

        winner_id = game.get_winner() if game.is_game_over() else None
        winner_label = (
            p1_label if winner_id == p1.id
            else p2_label if winner_id == p2.id
            else None
        )

        card_stats = _collect_minecraft_card_stats(
            game, p1.id, p2.id, p1_label, p2_label, deck1, deck2, winner_id,
        )

        return MCGameResult(
            p1_label=p1_label,
            p2_label=p2_label,
            winner_label=winner_label,
            turns=turn_count,
            p1_life=game.state.players[p1.id].life,
            p2_life=game.state.players[p2.id].life,
            duration_s=time.perf_counter() - start,
            card_stats=card_stats,
            error="timeout" if timed_out else None,
        )
    except Exception as exc:
        return MCGameResult(
            p1_label=p1_label,
            p2_label=p2_label,
            winner_label=None,
            turns=0,
            p1_life=20,
            p2_life=20,
            duration_s=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:1500]}",
        )


# ---------------------------------------------------------------------------
# Capability test
# ---------------------------------------------------------------------------


def _is_action_card(focal_name: str) -> bool:
    """Action cards resolve to graveyard immediately — use deck winrate, not
    in-play winrate."""
    cd = MINECRAFT_CARDS.get(focal_name)
    if not cd:
        return False
    return CardType.MC_ACTION in (cd.characteristics.types or set())


def run_capability_test(
    focal_name: str,
    partner_names: Optional[list[str]] = None,
    games: int = 8,
    baseline_deck: str = "raider",
    difficulty: str = "medium",
    max_turns: int = 20,
    focal_in_opener: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run `games` AI-vs-AI matches: synergy deck (built around focal_name) vs
    baseline_deck. Returns per-card metrics + capability score.
    """
    if partner_names is None:
        registry = _load_synergy_registry()
        partner_names = registry.get(focal_name, [])

    synergy_deck = build_synergy_deck(focal_name, partner_names)
    baseline = _baseline_deck(baseline_deck)

    if verbose:
        print(f"\n=== Capability test: {focal_name} ===", flush=True)
        print(f"  synergy partners: {len(partner_names)} cards", flush=True)
        print(f"  baseline: {baseline_deck} ({len(baseline)} cards)", flush=True)
        print(f"  games: {games}, focal-in-opener: {focal_in_opener}", flush=True)

    p1_hook = _make_stack_focal_hook(focal_name, target_seat="p1") if focal_in_opener else None
    p2_hook = _make_stack_focal_hook(focal_name, target_seat="p2") if focal_in_opener else None

    async def _run_all() -> list[MCGameResult]:
        results: list[MCGameResult] = []
        for g in range(games):
            # Alternate seats so first-player advantage cancels.
            if g % 2 == 0:
                d1, d2, l1, l2 = synergy_deck, baseline, "synergy", "baseline"
                run_hook = p1_hook
            else:
                d1, d2, l1, l2 = baseline, synergy_deck, "baseline", "synergy"
                run_hook = p2_hook
            r = await play_one_minecraft_game(
                d1, d2, l1, l2,
                difficulty=difficulty,
                max_turns=max_turns,
                pre_start_hook=run_hook,
            )
            results.append(r)
            if verbose:
                marker = "TIMEOUT" if r.error and "timeout" in r.error.lower() else (
                    "ERR" if r.error else (r.winner_label or "draw"))
                print(f"  game {g+1}: turns={r.turns:3d} winner={marker} "
                      f"p1_life={r.p1_life} p2_life={r.p2_life}",
                      flush=True)
        return results

    results = asyncio.run(_run_all())

    # Aggregate
    synergy_wins = sum(1 for r in results if r.winner_label == "synergy")
    games_finished = sum(1 for r in results if not r.error)
    games_with_winner = sum(1 for r in results if r.winner_label)
    deck_winrate = synergy_wins / games_with_winner if games_with_winner else 0.0
    error_count = sum(1 for r in results if r.error)

    # Focal card metrics across games
    focal_cast = 0
    focal_in_play_at_end = 0
    focal_on_winning_side = 0
    focal_deck_copies_per_game = 0
    for r in results:
        # Find focal in either label
        for ref, st in r.card_stats.items():
            label, name = ref.split("::", 1)
            if name != focal_name or label != "synergy":
                continue
            focal_cast += int(st.get("cast", 0))
            focal_in_play_at_end += int(st.get("in_play_at_end", 0))
            focal_on_winning_side += int(st.get("on_winning_side", 0))
            focal_deck_copies_per_game = max(focal_deck_copies_per_game,
                                             int(st.get("deck_copies", 0)))

    cast_per_game = focal_cast / games if games else 0.0
    win_rate_in_play = (focal_on_winning_side / focal_in_play_at_end) if focal_in_play_at_end else 0.0

    is_action = _is_action_card(focal_name)
    win_correlation = deck_winrate if is_action else win_rate_in_play
    capability_score = cast_per_game * win_correlation

    summary = {
        "focal": focal_name,
        "is_action": is_action,
        "games": games,
        "games_finished": games_finished,
        "errors": error_count,
        "synergy_wins": synergy_wins,
        "deck_winrate": round(deck_winrate, 3),
        "focal_cast_total": focal_cast,
        "cast_per_game": round(cast_per_game, 3),
        "focal_in_play_at_end_total": focal_in_play_at_end,
        "win_rate_in_play": round(win_rate_in_play, 3),
        "win_correlation": round(win_correlation, 3),
        "capability_score": round(capability_score, 3),
        "passes": capability_score >= 0.30,
    }

    if verbose:
        verdict = "PASS" if summary["passes"] else "FAIL"
        print(f"\n  --- {focal_name}: {verdict} ---", flush=True)
        print(f"    cast/game={summary['cast_per_game']}  "
              f"win_corr={summary['win_correlation']} "
              f"({'deck' if is_action else 'in-play'})  "
              f"score={summary['capability_score']}",
              flush=True)
        print(f"    deck_winrate={summary['deck_winrate']}  "
              f"errors={error_count}/{games}",
              flush=True)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Minecraft TCG capability test.")
    parser.add_argument("--card", type=str, help="Focal card name (e.g. 'Warden')")
    parser.add_argument("--all", action="store_true",
                        help="Run all cards in the synergy registry")
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--baseline", type=str, default="raider",
                        choices=list(MINECRAFT_STARTER_DECKS.keys()))
    parser.add_argument("--difficulty", type=str, default="medium")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--no-focal-in-opener", action="store_true",
                        help="Disable opening-hand stacking of the focal card")
    parser.add_argument("--out", type=str, help="Write JSON summary to this path")
    args = parser.parse_args()

    targets: list[str]
    registry = _load_synergy_registry()
    if args.all:
        if not registry:
            print("No synergy registry found at src/cards/minecraft/synergies.py")
            return
        targets = list(registry.keys())
    elif args.card:
        targets = [args.card]
    else:
        parser.error("Must pass --card NAME or --all")
        return

    summaries: list[dict[str, Any]] = []
    for focal in targets:
        try:
            summary = run_capability_test(
                focal,
                games=args.games,
                baseline_deck=args.baseline,
                difficulty=args.difficulty,
                max_turns=args.max_turns,
                focal_in_opener=not args.no_focal_in_opener,
            )
        except Exception as exc:
            print(f"  ERROR running {focal}: {exc}", flush=True)
            summary = {"focal": focal, "error": str(exc), "passes": False}
        summaries.append(summary)

    print("\n" + "=" * 60)
    print("MC CAPABILITY SWEEP SUMMARY")
    print("=" * 60)
    print(f"{'Card':32s}  {'Score':>6s}  {'C/g':>5s}  {'WinCorr':>7s}  Pass")
    print("-" * 60)
    for s in summaries:
        if "error" in s:
            print(f"{s['focal']:32s}  ERROR")
            continue
        print(f"{s['focal']:32s}  {s['capability_score']:>6.2f}  "
              f"{s['cast_per_game']:>5.2f}  {s['win_correlation']:>7.2f}  "
              f"{'YES' if s['passes'] else 'no'}")
    n_pass = sum(1 for s in summaries if s.get("passes"))
    print(f"\n{n_pass}/{len(summaries)} cards PASS (capability >= 0.30)")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(summaries, fh, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    _cli()
