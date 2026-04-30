#!/usr/bin/env python3
"""
Custom Set Tournament

Auto-builds decks for every custom MTG set in src/cards/custom/, runs
round-robin AI-vs-AI games, captures per-card stats, and emits a tier
report for finding dead/strong/broken cards and weak set archetypes.

Usage:
    python scripts/play/custom_set_tournament.py                     # full tournament
    python scripts/play/custom_set_tournament.py --smoke             # 2 sets only
    python scripts/play/custom_set_tournament.py --games 10          # 10 games per pair
    python scripts/play/custom_set_tournament.py --sets LRW,TMH,NRT  # specific sets
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.engine import (  # noqa: E402
    Game,
    GameState,
    Event,
    EventType,
    ZoneType,
    CardType,
    ActionType,
    PlayerAction,
    Color,
)
from src.engine.mana import ManaCost  # noqa: E402
from src.ai import AIEngine  # noqa: E402
from src.ai.strategies import (  # noqa: E402
    AggroStrategy,
    MidrangeStrategy,
    ControlStrategy,
)
from src.cards.custom import CUSTOM_SETS  # noqa: E402
from src.cards.custom.lorwyn_custom import LORWYN_CUSTOM_CARDS  # noqa: E402


# ----------------------------------------------------------------------
# Deck building
# ----------------------------------------------------------------------

BASIC_LAND_BY_COLOR: dict[Color, Any] = {
    Color.WHITE: LORWYN_CUSTOM_CARDS.get("Plains"),
    Color.BLUE: LORWYN_CUSTOM_CARDS.get("Island"),
    Color.BLACK: LORWYN_CUSTOM_CARDS.get("Swamp"),
    Color.RED: LORWYN_CUSTOM_CARDS.get("Mountain"),
    Color.GREEN: LORWYN_CUSTOM_CARDS.get("Forest"),
}


def get_cmc(card_def) -> int:
    """Compute mana value of a card definition. Returns 0 if no mana cost."""
    if not getattr(card_def, "mana_cost", None):
        return 0
    try:
        return ManaCost.parse(card_def.mana_cost).mana_value
    except Exception:
        return 0


def card_colors(card_def) -> set[Color]:
    return set(card_def.characteristics.colors or set())


def card_types(card_def) -> set[CardType]:
    return set(card_def.characteristics.types or set())


def primary_color(cards_dict) -> Color:
    """Most common single color across the set; ignores artifacts/lands."""
    counts: dict[Color, float] = defaultdict(float)
    for cd in cards_dict.values():
        if CardType.LAND in card_types(cd):
            continue
        cs = card_colors(cd)
        if not cs:
            continue
        weight = 1.0 / len(cs)
        for c in cs:
            counts[c] += weight
    if not counts:
        return Color.GREEN
    return max(counts, key=counts.get)


def build_set_deck(domain: str, cards_dict) -> tuple[list, dict]:
    """
    Build a 60-card deck from a custom set.

    Strategy: pick mono-primary-color creatures + 1-2 colorless artifacts
    + a few primary-color spells, sorted with creature preference and
    a CMC-3 sweet spot. 24 basic lands of the primary color.

    Falls back to LORWYN basic lands when the set lacks them.
    """
    primary = primary_color(cards_dict)

    # Candidate spells (non-land cards that include primary color or are colorless)
    spells: list = []
    for name, cd in cards_dict.items():
        if CardType.LAND in card_types(cd):
            continue
        cs = card_colors(cd)
        if cs and primary not in cs:
            continue
        if len(cs) > 2:
            continue
        spells.append(cd)

    # Quality score: lower is better
    def quality(cd) -> float:
        is_creature = CardType.CREATURE in card_types(cd)
        cmc = get_cmc(cd)
        cs = card_colors(cd)
        score = 0.0
        score -= 5.0 if is_creature else 0.0
        score += abs(cmc - 3)  # CMC-3 sweet spot
        score += 0.0 if (cs == {primary} or not cs) else 1.5
        # Prefer cards with interceptors (they actually do something)
        if getattr(cd, "setup_interceptors", None):
            score -= 0.5
        return score

    spells.sort(key=quality)

    # Build to 36 spells, max 4 copies each
    deck: list = []
    seen: dict[str, int] = defaultdict(int)
    for cd in spells:
        if len(deck) >= 36:
            break
        if seen[cd.name] >= 4:
            continue
        copies = 2 if CardType.CREATURE in card_types(cd) else 1
        for _ in range(copies):
            if len(deck) >= 36 or seen[cd.name] >= 4:
                break
            deck.append(cd)
            seen[cd.name] += 1

    # If we still didn't fill 36, repeat best cards
    if len(deck) < 36 and spells:
        idx = 0
        guard = 0
        while len(deck) < 36 and guard < 500:
            cd = spells[idx % len(spells)]
            if seen[cd.name] < 4:
                deck.append(cd)
                seen[cd.name] += 1
            idx += 1
            guard += 1

    # Pick basic land: prefer set's own, fallback to Lorwyn
    set_basic = None
    target_subtype = {
        Color.WHITE: "Plains",
        Color.BLUE: "Island",
        Color.BLACK: "Swamp",
        Color.RED: "Mountain",
        Color.GREEN: "Forest",
    }.get(primary, "Forest")
    for cd in cards_dict.values():
        if CardType.LAND in card_types(cd) and target_subtype in (cd.characteristics.subtypes or set()):
            set_basic = cd
            break
    basic_land = set_basic or BASIC_LAND_BY_COLOR.get(primary) or LORWYN_CUSTOM_CARDS.get("Forest")

    deck.extend([basic_land] * 24)

    info = {
        "domain": domain,
        "primary_color": primary.name,
        "size": len(deck),
        "spell_count": sum(1 for c in deck if CardType.LAND not in card_types(c)),
        "land_count": sum(1 for c in deck if CardType.LAND in card_types(c)),
        "unique_spells": len({c.name for c in deck if CardType.LAND not in card_types(c)}),
        "basic_land": basic_land.name if basic_land else None,
    }
    return deck[:60], info


# ----------------------------------------------------------------------
# Game runner
# ----------------------------------------------------------------------


@dataclass
class GameResult:
    p1_domain: str
    p2_domain: str
    winner_domain: Optional[str]   # None = draw / unfinished
    turns: int
    p1_life: int
    p2_life: int
    p1_lost: bool
    p2_lost: bool
    duration_s: float
    error: Optional[str] = None
    # Per-card stats keyed by "DOMAIN::CardName"
    card_stats: dict[str, dict[str, float]] = field(default_factory=dict)


def _card_ref(domain: str, card_def) -> str:
    return f"{domain}::{card_def.name}"


def _walk_event_log(state: GameState) -> list[Event]:
    return list(getattr(state, "event_log", []) or [])


def _collect_card_stats(
    game: Game,
    p1_id: str,
    p2_id: str,
    p1_domain: str,
    p2_domain: str,
    deck1: list,
    deck2: list,
    winner_id: Optional[str],
) -> dict[str, dict[str, float]]:
    """
    Walk event log + final state to compute per-card stats.

    Tracks: appeared (in deck), drawn, cast, dmg_dealt, kills, deaths,
    triggers_fired, in_play_at_end, on_winning_side.
    """
    state = game.state
    stats: dict[str, dict[str, float]] = defaultdict(lambda: {
        "deck_copies": 0,
        "drawn": 0,
        "cast": 0,
        "dmg_dealt": 0.0,
        "kills": 0,
        "deaths": 0,
        "triggers_fired": 0,
        "in_play_at_end": 0,
        "on_winning_side": 0,
    })

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
        domain = p1_domain if owner == p1_id else p2_domain if owner == p2_id else None
        if domain is None:
            return None
        return _card_ref(domain, cd), domain

    # Seed deck copies
    for cd in deck1:
        stats[_card_ref(p1_domain, cd)]["deck_copies"] += 1
    for cd in deck2:
        stats[_card_ref(p2_domain, cd)]["deck_copies"] += 1

    # Walk event log
    for ev in _walk_event_log(state):
        et = ev.type if hasattr(ev, "type") else None
        payload = ev.payload if hasattr(ev, "payload") else {}
        source_id = getattr(ev, "source", None) or payload.get("source")

        if et == EventType.ZONE_CHANGE:
            obj_id = payload.get("object_id") or payload.get("card_id")
            from_zone = payload.get("from_zone")
            to_zone = payload.get("to_zone")
            ref = _name_for(obj_id)
            if ref and to_zone == ZoneType.HAND and from_zone == ZoneType.LIBRARY:
                stats[ref[0]]["drawn"] += 1
            if ref and to_zone == ZoneType.BATTLEFIELD and from_zone in (ZoneType.HAND, ZoneType.STACK):
                # Lands shouldn't count as casts; still record as cast for play frequency
                stats[ref[0]]["cast"] += 1
            if ref and from_zone == ZoneType.BATTLEFIELD and to_zone == ZoneType.GRAVEYARD:
                stats[ref[0]]["deaths"] += 1
        elif et == EventType.DAMAGE:
            amount = payload.get("amount", 0) or 0
            ref = _name_for(source_id)
            if ref:
                stats[ref[0]]["dmg_dealt"] += amount
        elif et == EventType.OBJECT_DESTROYED:
            target_id = payload.get("object_id") or payload.get("target")
            ref_t = _name_for(target_id)
            if ref_t:
                stats[ref_t[0]]["deaths"] += 1
            ref_s = _name_for(source_id)
            if ref_s and ref_s[0] != (ref_t[0] if ref_t else None):
                stats[ref_s[0]]["kills"] += 1
        elif et == EventType.ENTER_BATTLEFIELD:
            obj_id = payload.get("object_id") or payload.get("card_id")
            ref = _name_for(obj_id)
            if ref:
                stats[ref[0]]["triggers_fired"] += 1
        elif et in (EventType.SPELL_CAST, EventType.CAST):
            obj_id = payload.get("object_id") or payload.get("card_id") or source_id
            ref = _name_for(obj_id)
            if ref:
                stats[ref[0]]["cast"] += 1

    # Final battlefield state
    bf = state.zones.get("battlefield")
    if bf:
        for obj_id in bf.objects:
            obj = state.objects.get(obj_id)
            if not obj or not getattr(obj, "card_def", None):
                continue
            owner = obj.owner
            domain = p1_domain if owner == p1_id else p2_domain if owner == p2_id else None
            if domain is None:
                continue
            ref = _card_ref(domain, obj.card_def)
            stats[ref]["in_play_at_end"] += 1
            if winner_id and owner == winner_id:
                stats[ref]["on_winning_side"] += 1

    return dict(stats)


async def play_one_game(
    deck1: list,
    deck2: list,
    ai1: AIEngine,
    ai2: AIEngine,
    p1_domain: str,
    p2_domain: str,
    max_turns: int = 25,
    per_turn_timeout_s: float = 1.5,
) -> GameResult:
    """Run one MTG AI-vs-AI game and return per-card stats + outcome."""
    start = time.perf_counter()

    try:
        game = Game()  # MTG default
        p1 = game.add_player("P1")
        p2 = game.add_player("P2")

        for cd in deck1:
            game.add_card_to_library(p1.id, cd)
        for cd in deck2:
            game.add_card_to_library(p2.id, cd)

        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        game.set_ai_player(p1.id)
        game.set_ai_player(p2.id)

        ais: dict[str, AIEngine] = {p1.id: ai1, p2.id: ai2}

        async def get_ai_action(player_id, state, legal_actions):
            ai = ais[player_id]
            try:
                return ai.get_action(player_id, state, legal_actions)
            except Exception:
                return PlayerAction(type=ActionType.PASS, player_id=player_id)

        def attack_handler(attacker_id, legal_attackers):
            try:
                return ais[attacker_id].get_attack_declarations(
                    attacker_id, game.state, legal_attackers
                )
            except Exception:
                return []

        def block_handler(blocker_id, attacks, legal_blockers):
            try:
                return ais[blocker_id].get_block_declarations(
                    blocker_id, game.state, attacks, legal_blockers
                )
            except Exception:
                return []

        game.set_ai_action_handler(get_ai_action)
        game.set_attack_handler(attack_handler)
        game.set_block_handler(block_handler)
        game.set_mulligan_handler(lambda pid, hand, count: True)  # always keep

        await asyncio.wait_for(game.start_game(), timeout=10.0)

        turn_count = 0
        timed_out = False
        wall_deadline = time.perf_counter() + 7.0  # absolute cap per game
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
        winner_domain = (
            p1_domain if winner_id == p1.id
            else p2_domain if winner_id == p2.id
            else None
        )

        card_stats = _collect_card_stats(
            game, p1.id, p2.id, p1_domain, p2_domain, deck1, deck2, winner_id
        )

        duration = time.perf_counter() - start
        return GameResult(
            p1_domain=p1_domain,
            p2_domain=p2_domain,
            winner_domain=winner_domain,
            turns=turn_count,
            p1_life=game.state.players[p1.id].life,
            p2_life=game.state.players[p2.id].life,
            p1_lost=game.state.players[p1.id].has_lost,
            p2_lost=game.state.players[p2.id].has_lost,
            duration_s=duration,
            card_stats=card_stats,
            error="timeout" if timed_out else None,
        )
    except Exception as exc:
        return GameResult(
            p1_domain=p1_domain,
            p2_domain=p2_domain,
            winner_domain=None,
            turns=0,
            p1_life=20,
            p2_life=20,
            p1_lost=False,
            p2_lost=False,
            duration_s=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:1500]}",
            card_stats={},
        )


# ----------------------------------------------------------------------
# Tournament orchestration
# ----------------------------------------------------------------------


def make_ai(strategy_name: str = "midrange", difficulty: str = "hard") -> AIEngine:
    if strategy_name == "aggro":
        return AIEngine(strategy=AggroStrategy(), difficulty=difficulty)
    if strategy_name == "control":
        return AIEngine(strategy=ControlStrategy(), difficulty=difficulty)
    return AIEngine(strategy=MidrangeStrategy(), difficulty=difficulty)


class _HardTimeoutError(Exception):
    pass


def _worker_run_game(args) -> dict:
    """Run one game in a subprocess. Args: (p1_domain, p2_domain, max_turns, difficulty, hard_timeout_s)."""
    import signal

    p1_dom, p2_dom, max_turns, difficulty, hard_timeout_s = args

    # SIGALRM raises an exception, caught here. If the exception can't
    # propagate (deep CPU loop swallows it), the next signal.alarm
    # iteration will try again. With shorter intervals, eventually one fires.
    def _alarm_handler(signum, frame):
        raise _HardTimeoutError(f"hard timeout on {p1_dom} vs {p2_dom}")

    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, hard_timeout_s)

    try:
        deck1, _ = build_set_deck(p1_dom, CUSTOM_SETS[p1_dom])
        deck2, _ = build_set_deck(p2_dom, CUSTOM_SETS[p2_dom])
        ai1 = make_ai("midrange", difficulty)
        ai2 = make_ai("midrange", difficulty)
        result = asyncio.run(
            play_one_game(deck1, deck2, ai1, ai2, p1_dom, p2_dom, max_turns=max_turns)
        )
        return result.__dict__
    except _HardTimeoutError as e:
        return {
            "p1_domain": p1_dom, "p2_domain": p2_dom, "winner_domain": None,
            "turns": 0, "p1_life": 20, "p2_life": 20,
            "p1_lost": False, "p2_lost": False, "duration_s": hard_timeout_s,
            "error": "hard_timeout",
            "card_stats": {},
        }
    except Exception as e:
        return {
            "p1_domain": p1_dom, "p2_domain": p2_dom, "winner_domain": None,
            "turns": 0, "p1_life": 20, "p2_life": 20,
            "p1_lost": False, "p2_lost": False, "duration_s": 0,
            "error": f"{type(e).__name__}: {e}",
            "card_stats": {},
        }
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def run_tournament_parallel(
    domains: list[str],
    games_per_pair: int = 3,
    max_turns: int = 20,
    difficulty: str = "hard",
    workers: int = 4,
    verbose: bool = True,
) -> dict[str, Any]:
    """Round-robin with ProcessPool parallelism."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from concurrent.futures.process import BrokenProcessPool

    deck_info: dict[str, dict] = {}
    for d in domains:
        _, info = build_set_deck(d, CUSTOM_SETS[d])
        deck_info[d] = info

    if verbose:
        print("\n=== Decks ===", flush=True)
        for d, info in deck_info.items():
            print(f"  {d:5s}  primary={info['primary_color']:6s}  "
                  f"unique={info['unique_spells']:3d}  "
                  f"spells={info['spell_count']:3d}  "
                  f"lands={info['land_count']:3d}", flush=True)

    pairings: list[tuple[str, str]] = []
    for i, a in enumerate(domains):
        for b in domains[i + 1:]:
            pairings.append((a, b))

    # Build work list: each game is one task. Alternate p1/p2.
    HARD_TIMEOUT_S = 8.0  # SIGALRM wall cap per game
    tasks: list[tuple] = []
    for a, b in pairings:
        for g in range(games_per_pair):
            p1, p2 = (a, b) if g % 2 == 0 else (b, a)
            tasks.append((p1, p2, max_turns, difficulty, HARD_TIMEOUT_S))

    total_games = len(tasks)
    started = time.perf_counter()
    results: list[dict] = []
    completed = 0

    if verbose:
        print(f"\nDispatching {total_games} games to {workers} workers...", flush=True)

    with ProcessPoolExecutor(max_workers=workers, max_tasks_per_child=50) as pool:
        futures = [pool.submit(_worker_run_game, t) for t in tasks]
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except Exception as e:
                r = {
                    "p1_domain": "?", "p2_domain": "?", "winner_domain": None,
                    "turns": 0, "p1_life": 20, "p2_life": 20,
                    "p1_lost": False, "p2_lost": False, "duration_s": 0,
                    "error": f"worker exception: {e}", "card_stats": {},
                }
            results.append(r)
            completed += 1
            if verbose and (completed % 10 == 0 or completed == total_games):
                elapsed = time.perf_counter() - started
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (total_games - completed) / rate if rate > 0 else 0
                err_count = sum(1 for x in results if x.get("error"))
                tos = sum(1 for x in results if x.get("error") == "hard_timeout")
                print(f"  [{completed}/{total_games}] {rate:.1f} g/s, "
                      f"err={err_count} (tmo={tos}), ETA {eta:.0f}s", flush=True)

    elapsed = time.perf_counter() - started

    return {
        "domains": domains,
        "games_per_pair": games_per_pair,
        "max_turns": max_turns,
        "difficulty": difficulty,
        "workers": workers,
        "deck_info": deck_info,
        "elapsed_s": elapsed,
        "results": results,
    }


def run_tournament_sequential(
    domains: list[str],
    games_per_pair: int = 5,
    max_turns: int = 14,
    difficulty: str = "hard",
    hard_timeout_s: float = 8.0,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Sequential round-robin — single process with SIGALRM hard timeout.
    No multiprocessing. Each game wrapped in signal.alarm so CPU-bound
    hangs are bounded.
    """
    import signal

    decks: dict[str, list] = {}
    deck_info: dict[str, dict] = {}
    for d in domains:
        deck, info = build_set_deck(d, CUSTOM_SETS[d])
        decks[d] = deck
        deck_info[d] = info

    if verbose:
        print(f"\n=== Decks: {len(domains)} sets ===", flush=True)

    pairings: list[tuple[str, str]] = []
    for i, a in enumerate(domains):
        for b in domains[i + 1:]:
            pairings.append((a, b))

    tasks: list[tuple] = []
    for a, b in pairings:
        for g in range(games_per_pair):
            p1, p2 = (a, b) if g % 2 == 0 else (b, a)
            tasks.append((p1, p2))

    total = len(tasks)
    started = time.perf_counter()
    results: list[dict] = []

    class _HardTimeout(Exception):
        pass

    def _alarm(signum, frame):
        raise _HardTimeout()

    signal.signal(signal.SIGALRM, _alarm)

    for i, (p1, p2) in enumerate(tasks):
        signal.setitimer(signal.ITIMER_REAL, hard_timeout_s)
        ai1 = make_ai("midrange", difficulty)
        ai2 = make_ai("midrange", difficulty)
        try:
            result = asyncio.run(
                play_one_game(decks[p1], decks[p2], ai1, ai2, p1, p2, max_turns=max_turns)
            )
            results.append(result.__dict__)
        except _HardTimeout:
            results.append({
                "p1_domain": p1, "p2_domain": p2,
                "winner_domain": None, "turns": 0,
                "p1_life": 20, "p2_life": 20,
                "p1_lost": False, "p2_lost": False,
                "duration_s": hard_timeout_s,
                "error": "hard_timeout", "card_stats": {},
            })
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()[:1500]
            results.append({
                "p1_domain": p1, "p2_domain": p2,
                "winner_domain": None, "turns": 0,
                "p1_life": 20, "p2_life": 20,
                "p1_lost": False, "p2_lost": False,
                "duration_s": 0,
                "error": f"{type(e).__name__}: {str(e)[:100]}\n{tb}",
                "card_stats": {},
            })
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

        if verbose and ((i + 1) % 20 == 0 or i + 1 == total):
            elapsed = time.perf_counter() - started
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            err_count = sum(1 for r in results if r.get("error"))
            tos = sum(1 for r in results if r.get("error") == "hard_timeout")
            print(f"  [{i+1}/{total}] {rate:.1f} g/s, "
                  f"err={err_count} (tmo={tos}), ETA {eta:.0f}s", flush=True)

    return {
        "domains": domains,
        "games_per_pair": games_per_pair,
        "max_turns": max_turns,
        "difficulty": difficulty,
        "deck_info": deck_info,
        "elapsed_s": time.perf_counter() - started,
        "results": results,
    }


async def run_tournament(*args, **kwargs):
    """Compat wrapper — delegates to sequential."""
    return run_tournament_sequential(*args, **kwargs)


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------


def aggregate(results_dict: dict[str, Any]) -> dict[str, Any]:
    """Compute set winrate matrix + per-card aggregate stats."""
    domains = results_dict["domains"]
    raw_results = results_dict["results"]

    set_record: dict[str, dict[str, int]] = defaultdict(
        lambda: {"wins": 0, "losses": 0, "draws": 0, "errors": 0}
    )
    matchup: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"wins_a": 0, "wins_b": 0, "draws": 0}
    )

    card_agg: dict[str, dict[str, float]] = defaultdict(lambda: {
        "games": 0,
        "deck_copies": 0,
        "drawn": 0,
        "cast": 0,
        "dmg_dealt": 0.0,
        "kills": 0,
        "deaths": 0,
        "triggers_fired": 0,
        "in_play_at_end": 0,
        "on_winning_side": 0,
    })

    for r in raw_results:
        if r.get("error"):
            set_record[r["p1_domain"]]["errors"] += 1
            set_record[r["p2_domain"]]["errors"] += 1
            continue
        winner = r["winner_domain"]
        a, b = r["p1_domain"], r["p2_domain"]

        # Normalize matchup key (alphabetical)
        ka, kb = sorted([a, b])
        m = matchup[(ka, kb)]
        if winner is None:
            m["draws"] += 1
            set_record[a]["draws"] += 1
            set_record[b]["draws"] += 1
        elif winner == a:
            set_record[a]["wins"] += 1
            set_record[b]["losses"] += 1
            if a == ka:
                m["wins_a"] += 1
            else:
                m["wins_b"] += 1
        else:
            set_record[b]["wins"] += 1
            set_record[a]["losses"] += 1
            if b == ka:
                m["wins_a"] += 1
            else:
                m["wins_b"] += 1

        # Card stats — count games this card "appeared" in (deck-side games)
        for ref, cs in (r.get("card_stats") or {}).items():
            agg = card_agg[ref]
            agg["games"] += 1
            for k, v in cs.items():
                if k in agg:
                    agg[k] += v

    # Per-set winrate
    set_summary = {}
    for d in domains:
        rec = set_record[d]
        gp = rec["wins"] + rec["losses"] + rec["draws"]
        wr = (rec["wins"] / gp) if gp else 0.0
        set_summary[d] = {**rec, "games_played": gp, "winrate": round(wr, 3)}

    # Card scores: per-card "value" — cast frequency + on-winning-side rate
    card_scores: dict[str, dict[str, float]] = {}
    for ref, agg in card_agg.items():
        games = max(agg["games"], 1)
        cast_per_game = agg["cast"] / games
        copies_per_game = agg["deck_copies"] / games
        # Cast rate = casts / (copies present across games this card was deck-included)
        cast_per_copy = (agg["cast"] / agg["deck_copies"]) if agg["deck_copies"] else 0.0
        win_rate_when_in_play = (
            agg["on_winning_side"] / agg["in_play_at_end"]
            if agg["in_play_at_end"] > 0 else 0.0
        )
        card_scores[ref] = {
            **agg,
            "cast_per_game": round(cast_per_game, 3),
            "copies_per_game": round(copies_per_game, 3),
            "cast_per_copy": round(cast_per_copy, 3),
            "win_rate_in_play": round(win_rate_when_in_play, 3),
        }

    return {
        "set_summary": set_summary,
        "matchup": {f"{a} vs {b}": v for (a, b), v in matchup.items()},
        "card_scores": card_scores,
    }


def render_tier_report(agg: dict[str, Any]) -> str:
    """Human-readable tier report."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("CUSTOM SET TOURNAMENT — TIER REPORT")
    lines.append("=" * 70)

    # Set ranking
    lines.append("\n## Set Winrate Ranking")
    ranked = sorted(agg["set_summary"].items(), key=lambda kv: kv[1]["winrate"], reverse=True)
    lines.append(f"{'Set':6s}  {'WR':>6s}  {'W':>3s}  {'L':>3s}  {'D':>3s}  {'Err':>3s}")
    for d, rec in ranked:
        lines.append(
            f"{d:6s}  {rec['winrate']*100:5.1f}%  "
            f"{rec['wins']:3d}  {rec['losses']:3d}  {rec['draws']:3d}  {rec['errors']:3d}"
        )

    # Per-set card breakdown
    lines.append("\n## Card Tiers Per Set")
    by_set: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for ref, score in agg["card_scores"].items():
        domain = ref.split("::", 1)[0]
        by_set[domain].append((ref.split("::", 1)[1], score))

    BASIC_LAND_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
    for d in sorted(by_set.keys()):
        cards = by_set[d]
        # Drop basic lands (they enter via PLAY_LAND, not always logged as cast)
        cards = [c for c in cards if c[0] not in BASIC_LAND_NAMES]
        cards.sort(key=lambda kv: (-kv[1]["cast_per_copy"], kv[0]))

        # Bucket by cast_per_copy (fraction of deck copies that ever got cast)
        dead = [c for c in cards if c[1]["cast_per_copy"] < 0.05 and c[1]["deck_copies"] >= 2]
        weak = [c for c in cards if 0.05 <= c[1]["cast_per_copy"] < 0.30]
        ok = [c for c in cards if 0.30 <= c[1]["cast_per_copy"] < 0.70]
        strong = [c for c in cards if c[1]["cast_per_copy"] >= 0.70]

        # Within "strong", bucket "broken" — high winrate when in play, frequent appearance
        broken = [c for c in strong if c[1]["win_rate_in_play"] > 0.70 and c[1]["in_play_at_end"] >= 4]

        lines.append(f"\n### {d}  ({len(cards)} unique cards in deck)")
        lines.append(f"  dead:    {len(dead):3d}")
        lines.append(f"  weak:    {len(weak):3d}")
        lines.append(f"  ok:      {len(ok):3d}")
        lines.append(f"  strong:  {len(strong):3d}  (of which broken: {len(broken)})")

        if dead:
            lines.append("  dead cards (cast/copy <0.05, ≥2 copies in deck):")
            for name, s in dead[:10]:
                lines.append(
                    f"    - {name}  copies={int(s['deck_copies'])}  "
                    f"cast={int(s['cast'])}  c/copy={s['cast_per_copy']:.2f}"
                )

        if broken:
            lines.append("  broken candidates (winrate-in-play >70%, ≥4 endgame appearances):")
            for name, s in broken[:5]:
                lines.append(
                    f"    + {name}  c/copy={s['cast_per_copy']:.2f}  "
                    f"wr-in-play={s['win_rate_in_play']*100:.0f}%  "
                    f"dmg={int(s['dmg_dealt'])}  kills={int(s['kills'])}"
                )

        # Top performers (highest cast rate)
        top = [c for c in cards if c[1]["deck_copies"] >= 2][:5]
        if top:
            lines.append("  top by cast rate:")
            for name, s in top:
                lines.append(
                    f"    > {name}  c/copy={s['cast_per_copy']:.2f}  "
                    f"dmg={int(s['dmg_dealt'])}  kills={int(s['kills'])}  "
                    f"deaths={int(s['deaths'])}"
                )

    # Matchup matrix
    lines.append("\n## Matchup Matrix (a-vs-b: a wins / b wins / draws)")
    for k, v in sorted(agg["matchup"].items()):
        lines.append(f"  {k}: {v['wins_a']} / {v['wins_b']} / {v['draws']}")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="2 sets only (LRW vs TMH)")
    parser.add_argument("--games", type=int, default=3, help="games per pair")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--difficulty", default="hard")
    parser.add_argument("--sets", type=str, default=None,
                        help="comma-separated domain codes; default = all")
    parser.add_argument("--out", type=str, default="logs/tournament_results.json")
    parser.add_argument("--report", type=str, default="logs/tournament_report.txt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--sequential", action="store_true",
                        help="run sequentially (no multiprocessing)")
    args = parser.parse_args()

    random.seed(args.seed)

    if args.smoke:
        domains = ["LRW", "TMH"]
    elif args.sets:
        domains = [s.strip() for s in args.sets.split(",") if s.strip()]
    else:
        domains = list(CUSTOM_SETS.keys())

    out_path = REPO_ROOT / args.out
    report_path = REPO_ROOT / args.report
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_pairs = len(domains) * (len(domains) - 1) // 2
    total_games = n_pairs * args.games
    print(f"Tournament: {len(domains)} sets, {n_pairs} pairs, "
          f"{args.games} games/pair = {total_games} games. "
          f"max_turns={args.max_turns}, difficulty={args.difficulty}, "
          f"workers={1 if args.sequential else args.workers}", flush=True)

    try:
        if args.sequential:
            results = run_tournament_sequential(
                domains, args.games, args.max_turns, args.difficulty, verbose=True,
            )
        else:
            results = run_tournament_parallel(
                domains, args.games, args.max_turns, args.difficulty,
                workers=args.workers, verbose=True,
            )
    except KeyboardInterrupt:
        print("\nInterrupted — saving partial data...", flush=True)
        results = {"domains": domains, "games_per_pair": args.games,
                   "max_turns": args.max_turns, "difficulty": args.difficulty,
                   "deck_info": {}, "elapsed_s": 0, "results": []}

    # Aggregate + render
    agg = aggregate(results)
    report = render_tier_report(agg)

    with open(out_path, "w") as f:
        json.dump({**results, "aggregate": agg}, f, indent=2, default=str)

    with open(report_path, "w") as f:
        f.write(report)

    print(report)
    print(f"\nRaw results -> {out_path}")
    print(f"Tier report -> {report_path}")
    print(f"Total wall time: {results['elapsed_s']:.0f}s "
          f"({results['elapsed_s']/total_games:.2f}s/game)", flush=True)


if __name__ == "__main__":
    main()
