"""
depths_demo — run one AI-vs-AI Depths game with turn-by-turn narration.

Usage:
    python scripts/play/depths_demo.py
    python scripts/play/depths_demo.py --p1 wolfpack --p2 deep_strike
    python scripts/play/depths_demo.py --p1 DEPTHS_research_midrange --p2 ABYS_research
    python scripts/play/depths_demo.py --max-turns 30 --quiet
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import EventType, ZoneType                      # noqa: E402
from src.engine.game import Game                                      # noqa: E402
from src.engine.depths import (                                       # noqa: E402
    DepthBand, get_flagship, is_vessel,
)
from src.engine.depths_turn import DepthsTurnManager                  # noqa: E402
from src.ai.depths_adapter import DepthsAIAdapter                     # noqa: E402
from src.cards.depths.decks import (                                  # noqa: E402
    DEPTHS_STARTER_DECKS,
    format_depths_deck_labels,
    normalize_depths_deck_label,
)
from src.cards.depths.submarine_fleet.decks import make_subs_flagship  # noqa: E402
from src.cards.depths.abyssal_expanse.decks import make_abys_flagship  # noqa: E402

# Reuse the action-dict converter from the smoke test.
from tests.test_depths_smoke import _action_to_dict, _is_done          # noqa: E402


def _flagship_for_key(key: str):
    return make_abys_flagship() if key.startswith("ABYS_") else make_subs_flagship()


# =============================================================================
# Pretty colors (ANSI; fall back to plain on --no-color)
# =============================================================================

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    YEL = "\033[33m"
    GRN = "\033[32m"
    MAG = "\033[35m"
    GRAY = "\033[90m"


def _disable_color() -> None:
    for name in dir(C):
        if name.isupper():
            setattr(C, name, "")


# =============================================================================
# Narration tracker — observes events and prints a play-by-play
# =============================================================================

class NarratingTracker:
    """Wraps a DepthsAIAdapter; intercepts decisions and prints them."""

    def __init__(self, ai: DepthsAIAdapter, label: str, color: str):
        self.ai = ai
        self.label = label
        self.color = color
        self.actions = 0
        self.attacks = 0
        self.detections = 0

    def __getattr__(self, name):
        return getattr(self.ai, name)

    def _tag(self) -> str:
        return f"{self.color}[{self.label}]{C.RESET}"

    async def choose_maneuver_action(self, state, player_id):
        action = self.ai.choose_maneuver_action(state, player_id)
        self._narrate_action(state, action, "maneuver")
        return _action_to_dict(action, "DEPTHS_END_MANEUVER")

    async def choose_regroup_action(self, state, player_id):
        action = self.ai.choose_maneuver_action(state, player_id)
        self._narrate_action(state, action, "regroup")
        return _action_to_dict(action, "DEPTHS_END_REGROUP")

    def _narrate_action(self, state, action, phase: str) -> None:
        if action is None or _is_done(action):
            return
        self.actions += 1
        cls = type(action).__name__
        if cls == "DeployVessel":
            obj = state.objects.get(getattr(action, "card_id", None))
            nm = obj.name if obj else "(?)"
            cost = getattr(obj.card_def, "mana_cost", "?") if obj else "?"
            print(f"  {self._tag()} {C.GRN}DEPLOY{C.RESET} {nm} {C.DIM}{cost}{C.RESET}")
        elif cls == "Dive":
            obj = state.objects.get(getattr(action, "vessel_id", None))
            nm = obj.name if obj else "(?)"
            band = obj.state.depth_band.name if obj else "?"
            print(f"  {self._tag()} {C.CYAN}DIVE{C.RESET} {nm} {C.DIM}(now at {band}){C.RESET}")
        elif cls == "SurfaceVessel":
            obj = state.objects.get(getattr(action, "vessel_id", None))
            nm = obj.name if obj else "(?)"
            band = obj.state.depth_band.name if obj else "?"
            print(f"  {self._tag()} {C.YEL}SURFACE{C.RESET} {nm} {C.DIM}(now at {band}){C.RESET}")
        elif cls == "LayMine":
            print(f"  {self._tag()} {C.MAG}LAY MINE{C.RESET}")
        elif cls in ("AttachCrew", "AttachWeapon"):
            print(f"  {self._tag()} {C.GRN}ATTACH{C.RESET} ({cls})")
        elif cls == "CastAction":
            obj = state.objects.get(getattr(action, "card_id", None))
            nm = obj.name if obj else "(?)"
            print(f"  {self._tag()} {C.MAG}CAST{C.RESET} {nm}")
        elif cls == "ActivateAbility":
            print(f"  {self._tag()} ACTIVATE")

    def choose_attackers(self, state, player_id):
        attackers = self.ai.choose_attackers(state, player_id)
        if attackers:
            self.attacks += len(attackers)
            for spec in attackers:
                vid = getattr(spec, "vessel_id", None)
                tid = getattr(spec, "target_id", None)
                v = state.objects.get(vid)
                t = state.objects.get(tid)
                vn = v.name if v else "(?)"
                tn = t.name if t else "Flagship?"
                v_band_obj = getattr(getattr(v, "state", None), "depth_band", None) if v else None
                t_band_obj = getattr(getattr(t, "state", None), "depth_band", None) if t else None
                v_band = v_band_obj.name if v_band_obj is not None else "?"
                t_band = t_band_obj.name if t_band_obj is not None else "?"
                print(f"  {self._tag()} {C.RED}ATTACK{C.RESET} {vn}({v_band}) → {tn}({t_band})")
        return attackers

    def choose_detections(self, state, defender_id, attackers):
        detections = self.ai.choose_detections(state, defender_id, attackers)
        if detections:
            spent = sum(detections.values()) if isinstance(detections, dict) else len(detections)
            if spent:
                self.detections += 1
                print(f"  {self._tag()} {C.CYAN}DETECT{C.RESET} (spent {spent} sonar)")
        return detections

    def choose_interceptors(self, state, defender_id, detected_attackers):
        ints = self.ai.choose_interceptors(state, defender_id, detected_attackers)
        if ints:
            for spec in ints:
                iid = getattr(spec, "interceptor_id", None)
                aid = getattr(spec, "attacker_id", None)
                i = state.objects.get(iid)
                a = state.objects.get(aid)
                i_n = i.name if i else "?"
                a_n = a.name if a else "?"
                print(f"  {self._tag()} {C.YEL}INTERCEPT{C.RESET} {i_n} blocks {a_n}")
        return ints

    async def choose_discards(self, state, player_id, count):
        if hasattr(self.ai, "choose_discards"):
            r = self.ai.choose_discards(state, player_id, count)
            if asyncio.iscoroutine(r):
                r = await r
            return r
        hand = state.zones.get(f"hand_{player_id}")
        return list(hand.objects)[:count] if hand else []

    def mulligan_decision(self, state, player_id, hand=None):
        return self.ai.mulligan_decision(state, player_id, hand) \
            if hasattr(self.ai, "mulligan_decision") else True


# =============================================================================
# Board-state snapshot
# =============================================================================

def _flagship_hull(player_id, state) -> tuple[int, int]:
    fs = get_flagship(player_id, state)
    if fs is None:
        return (0, 0)
    base = fs.characteristics.toughness or 0
    dmg = fs.state.damage or 0
    return (max(0, base - dmg), base)


def _board_snapshot(p1, p2, state) -> str:
    h1, max1 = _flagship_hull(p1.id, state)
    h2, max2 = _flagship_hull(p2.id, state)
    v1 = sum(1 for o in state.objects.values()
             if o.controller == p1.id and o.zone == ZoneType.BATTLEFIELD and is_vessel(o))
    v2 = sum(1 for o in state.objects.values()
             if o.controller == p2.id and o.zone == ZoneType.BATTLEFIELD and is_vessel(o))
    return (f"{C.BLUE}{p1.name}{C.RESET} hull {h1}/{max1} · vessels {v1}  "
            f"{C.GRAY}|{C.RESET}  "
            f"{C.RED}{p2.name}{C.RESET} hull {h2}/{max2} · vessels {v2}  "
            f"{C.GRAY}| TC/SC: {p1.tc}/{p1.sc}  vs  {p2.tc}/{p2.sc}{C.RESET}")


# =============================================================================
# Main demo runner
# =============================================================================

async def run_demo(p1_label: str, p2_label: str, max_turns: int, quiet: bool) -> None:
    print(f"{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║  DEPTHS — Submarine Fleet Demo                           ║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║  {C.BLUE}{p1_label:<12}{C.CYAN}  vs  {C.RED}{p2_label:<12}{C.CYAN}                  ║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════════╝{C.RESET}\n")

    p1_deck_key = normalize_depths_deck_label(p1_label)
    p2_deck_key = normalize_depths_deck_label(p2_label)
    if p1_deck_key not in DEPTHS_STARTER_DECKS or p2_deck_key not in DEPTHS_STARTER_DECKS:
        raise SystemExit(f"unknown deck. Available: {format_depths_deck_labels()}")

    deck1 = DEPTHS_STARTER_DECKS[p1_deck_key]()
    deck2 = DEPTHS_STARTER_DECKS[p2_deck_key]()
    p1_flagship = _flagship_for_key(p1_deck_key)
    p2_flagship = _flagship_for_key(p2_deck_key)

    game = Game(mode="depths")
    p1 = game.add_player(p1_label.title())
    p2 = game.add_player(p2_label.title())

    tm = DepthsTurnManager(game.state)
    game.turn_manager = tm

    p1_ai = NarratingTracker(DepthsAIAdapter(difficulty="medium"), p1.name, C.BLUE)
    p2_ai = NarratingTracker(DepthsAIAdapter(difficulty="medium"), p2.name, C.RED)

    tm.set_ai_handler(p1_ai, player_id=p1.id)
    tm.set_ai_handler(p2_ai, player_id=p2.id)
    # Mark both players as AI-controlled so the turn manager actually
    # runs the action loop for them (handler alone isn't enough).
    if hasattr(tm, "set_ai_player"):
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)

    await tm.setup_game(game, deck1, deck2, p1_flagship, p2_flagship)

    print(f"{C.DIM}initial:{C.RESET} {_board_snapshot(p1, p2, game.state)}")
    print()

    turn = 0
    for _ in range(max_turns):
        if game.is_game_over():
            break
        active = p1 if turn % 2 == 0 else p2
        active_color = C.BLUE if active is p1 else C.RED
        print(f"{C.BOLD}{active_color}── Turn {turn + 1}: {active.name} ──{C.RESET}")
        try:
            await tm.run_turn(active.id)
        except Exception as exc:
            print(f"  {C.RED}!! ERROR: {type(exc).__name__}: {exc}{C.RESET}")
            break
        if not quiet:
            print(f"  {C.DIM}↪ {_board_snapshot(p1, p2, game.state)}{C.RESET}")
        print()
        turn += 1

    # ── Endgame ──
    print(f"{C.BOLD}{C.YEL}╔══════════════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.YEL}║  GAME OVER  ({turn} turns)                                   ║{C.RESET}")
    print(f"{C.BOLD}{C.YEL}╚══════════════════════════════════════════════════════════╝{C.RESET}")
    print(_board_snapshot(p1, p2, game.state))

    p1_lost = getattr(p1, "has_lost", False)
    p2_lost = getattr(p2, "has_lost", False)
    if p1_lost and p2_lost:
        print(f"\n{C.YEL}DRAW — both fleets scuttled.{C.RESET}")
    elif p1_lost:
        print(f"\n{C.BOLD}{C.RED}{p2.name} WINS{C.RESET}")
    elif p2_lost:
        print(f"\n{C.BOLD}{C.BLUE}{p1.name} WINS{C.RESET}")
    else:
        print(f"\n{C.YEL}TIMEOUT after {turn} turns — no win condition fired.{C.RESET}")

    print(f"\n{C.DIM}{p1.name}: {p1_ai.actions} actions, {p1_ai.attacks} attacks, {p1_ai.detections} detection bursts{C.RESET}")
    print(f"{C.DIM}{p2.name}: {p2_ai.actions} actions, {p2_ai.attacks} attacks, {p2_ai.detections} detection bursts{C.RESET}")


def main() -> None:
    deck_help = f"Available deck labels: {format_depths_deck_labels()}"
    ap = argparse.ArgumentParser(
        description=__doc__,
        epilog=deck_help,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--p1", default="wolfpack",
                    help=f"P1 deck label. {deck_help}")
    ap.add_argument("--p2", default="silent_hunter",
                    help=f"P2 deck label. {deck_help}")
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--quiet", action="store_true",
                    help="Skip per-turn board snapshots (just actions)")
    ap.add_argument("--no-color", action="store_true",
                    help="Plain output for non-ANSI terminals")
    args = ap.parse_args()
    if args.no_color:
        _disable_color()
    asyncio.run(run_demo(args.p1, args.p2, args.max_turns, args.quiet))


if __name__ == "__main__":
    main()
