"""
Interactive Depths wet-test harness — LLM-pilot vs heuristic AI.

Pattern mirrors scripts/play/mc_wet_test.py:
- Game state is pickled to /tmp/depths_wet_test_state.pkl between commands
- LLM queues actions via plan-* commands, then `play-turn` executes one full
  turn cycle (my actions → my engagement → AI's full turn).

Usage:
    PYTHONPATH=. python scripts/play/depths_wet_test.py start \\
        --my-deck wolfpack --ai-deck silent_hunter --difficulty medium

    PYTHONPATH=. python scripts/play/depths_wet_test.py state

    # Build up a plan:
    python scripts/play/depths_wet_test.py plan-deploy "Sea Wolf Scout"
    python scripts/play/depths_wet_test.py plan-deploy "Pack Runner"
    python scripts/play/depths_wet_test.py plan-dive <vessel_id_prefix>
    python scripts/play/depths_wet_test.py plan-attack <vessel_prefix:target_prefix> ...
    python scripts/play/depths_wet_test.py plan-attack <vessel_prefix:flagship>
    python scripts/play/depths_wet_test.py plan-show
    python scripts/play/depths_wet_test.py play-turn

    # Inspect afterwards:
    python scripts/play/depths_wet_test.py state
    python scripts/play/depths_wet_test.py history

    # Game over:
    python scripts/play/depths_wet_test.py result

Available decks: wolfpack, silent_hunter, carrier, deep_strike
Difficulty: easy, medium, hard
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import dill as pickle  # noqa: E402

STATE_PATH = "/tmp/depths_wet_test_state.pkl"


def _save(payload: dict[str, Any]) -> None:
    with open(STATE_PATH, "wb") as fh:
        pickle.dump(payload, fh)


def _load() -> dict[str, Any]:
    with open(STATE_PATH, "rb") as fh:
        return pickle.load(fh)


# =============================================================================
# PlannedHandler — yields queued actions to the turn manager
# =============================================================================

class PlannedHandler:
    """A handler that pulls actions from pre-queued lists.

    The harness queues maneuver/regroup actions and attacker specs ahead of
    time; the turn manager calls choose_*() and gets one action at a time.
    Defensive falls back to Done() / [] when queues are empty so the phase
    closes out normally.
    """

    def __init__(self):
        # Each is consumed FIFO; harness commands append to these.
        self.maneuver_q: list[dict] = []   # action dicts (already in turn-mgr format)
        self.regroup_q: list[dict] = []
        self.attackers_spec: list[Any] = []  # AttackerSpec instances
        # For passive defense: the AI handler picks the smart detect/intercept
        # choices. We delegate to it for those.
        self.defense_ai = None
        # Telemetry — populated by play-turn so the LLM can see what happened.
        self.execution_log: list[str] = []

    def _label(self, action: dict, state) -> str:
        a_type = action.get("action_type", "?")
        if a_type == "DEPTHS_DEPLOY_VESSEL":
            obj = state.objects.get(action.get("card_id"))
            return f"deploy {obj.name if obj else action.get('card_id', '?')}"
        if a_type == "DEPTHS_DIVE":
            obj = state.objects.get(action.get("vessel_id"))
            return f"dive {obj.name if obj else action.get('vessel_id', '?')}"
        if a_type == "DEPTHS_SURFACE_VESSEL":
            obj = state.objects.get(action.get("vessel_id"))
            return f"surface {obj.name if obj else action.get('vessel_id', '?')}"
        if a_type == "DEPTHS_LAY_MINE":
            obj = state.objects.get(action.get("card_id"))
            return f"lay mine {obj.name if obj else action.get('card_id', '?')}"
        if a_type == "DEPTHS_ATTACH":
            att = state.objects.get(action.get("card_id") or action.get("attachment_id"))
            tgt = state.objects.get(action.get("target_id"))
            return f"attach {att.name if att else '?'} → {tgt.name if tgt else '?'}"
        if a_type == "DEPTHS_CAST_SPELL":
            obj = state.objects.get(action.get("card_id"))
            return f"cast {obj.name if obj else action.get('card_id', '?')}"
        if a_type == "DEPTHS_ACTIVATE_ABILITY":
            obj = state.objects.get(action.get("source_id"))
            return f"activate ability of {obj.name if obj else '?'}"
        return a_type

    async def choose_maneuver_action(self, state, player_id):
        if self.maneuver_q:
            action = self.maneuver_q.pop(0)
            self.execution_log.append(f"MANEUVER: {self._label(action, state)}")
            return action
        return {"action_type": "DEPTHS_END_MANEUVER"}

    async def choose_regroup_action(self, state, player_id):
        if self.regroup_q:
            action = self.regroup_q.pop(0)
            self.execution_log.append(f"REGROUP: {self._label(action, state)}")
            return action
        return {"action_type": "DEPTHS_END_REGROUP"}

    def choose_attackers(self, state, player_id):
        return list(self.attackers_spec)

    def choose_detections(self, state, defender_id, attackers):
        # As the active player we don't get called here — but if AI attacks
        # us, this defender hook IS called. Delegate to a real AI for sensible
        # defensive play. Returns dict {attacker_id: sonar_spend}.
        if self.defense_ai is not None:
            return self.defense_ai.choose_detections(state, defender_id, attackers)
        return {}

    def choose_interceptors(self, state, defender_id, detected_attackers):
        if self.defense_ai is not None:
            return self.defense_ai.choose_interceptors(
                state, defender_id, detected_attackers
            )
        return []

    async def choose_discards(self, state, player_id, count):
        hand = state.zones.get(f"hand_{player_id}")
        return list(hand.objects)[:count] if hand else []

    def mulligan_decision(self, state, player_id, hand=None):
        return True


class AIDictAdapter:
    """Wrap a DepthsAIAdapter so its choose_*_action returns dicts (the
    format the turn manager expects), not dataclass instances."""

    def __init__(self, ai):
        self.ai = ai

    def __getattr__(self, name):
        # Guard against recursion when unpickling (self.ai not yet set).
        if name.startswith("__") or name == "ai":
            raise AttributeError(name)
        return getattr(self.__dict__["ai"], name)

    async def choose_maneuver_action(self, state, player_id):
        from tests.test_depths_smoke import _action_to_dict
        action = self.ai.choose_maneuver_action(state, player_id)
        return _action_to_dict(action, "DEPTHS_END_MANEUVER")

    async def choose_regroup_action(self, state, player_id):
        from tests.test_depths_smoke import _action_to_dict
        # AI adapter doesn't distinguish phases — reuse maneuver pick.
        action = self.ai.choose_maneuver_action(state, player_id)
        return _action_to_dict(action, "DEPTHS_END_REGROUP")

    def choose_attackers(self, state, player_id):
        return self.ai.choose_attackers(state, player_id)

    def choose_detections(self, state, defender_id, attackers):
        return self.ai.choose_detections(state, defender_id, attackers)

    def choose_interceptors(self, state, defender_id, detected_attackers):
        return self.ai.choose_interceptors(state, defender_id, detected_attackers)

    async def choose_discards(self, state, player_id, count):
        hand = state.zones.get(f"hand_{player_id}")
        return list(hand.objects)[:count] if hand else []

    def mulligan_decision(self, state, player_id, hand=None):
        return True


# =============================================================================
# State printer
# =============================================================================

def _print_state(payload: dict[str, Any]) -> None:
    from src.engine.types import ZoneType
    from src.engine.depths import DepthBand, get_flagship, is_vessel, is_mine

    game = payload["game"]
    state = game.state
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    p1 = state.players[p1_id]
    p2 = state.players[p2_id]

    print("=" * 72)
    print(f"Turn {getattr(state, 'turn_number', '?')}  active={state.active_player!r}")
    print("=" * 72)

    if game.is_game_over():
        if getattr(p1, "has_lost", False) and getattr(p2, "has_lost", False):
            print(">>> GAME OVER — DRAW (both fleets scuttled).")
        elif getattr(p1, "has_lost", False):
            print(">>> GAME OVER — AI (P2) WON.")
        elif getattr(p2, "has_lost", False):
            print(">>> GAME OVER — ME (P1) WON.")
        else:
            print(">>> GAME OVER — winner unclear.")
        return

    def _band_label(b):
        return b.name if b is not None else "?"

    def _player_block(label, p, pid):
        flag = get_flagship(pid, state)
        if flag is not None:
            base = flag.characteristics.toughness or 0
            dmg = flag.state.damage or 0
            hull = max(0, base - dmg)
            flag_str = f"{hull}/{base} @ {_band_label(flag.state.depth_band)}"
        else:
            flag_str = "(no flagship!)"
        print(f"\n[{label}]  TC={getattr(p, 'tc', '?')}  SC={getattr(p, 'sc', '?')}  Flagship: {flag_str}")

        # Vessels (non-flagship), grouped by depth band
        bands: dict[Any, list[str]] = {b: [] for b in DepthBand}
        bands["?"] = []
        bf = state.zones.get("battlefield")
        if bf:
            for oid in bf.objects:
                obj = state.objects.get(oid)
                if not obj or obj.controller != pid or obj.zone != ZoneType.BATTLEFIELD:
                    continue
                if not is_vessel(obj):
                    continue
                if "Flagship" in obj.characteristics.subtypes:
                    continue
                power = obj.characteristics.power or 0
                hull = obj.characteristics.toughness or 0
                dmg = obj.state.damage or 0
                tap = "T" if getattr(obj.state, "tapped", False) else " "
                ss = "S" if getattr(obj.state, "summoning_sickness", False) else " "
                det = "D" if getattr(obj.state, "detected", False) else " "
                band = obj.state.depth_band
                key = band if band is not None else "?"
                bands.setdefault(key, []).append(
                    f"    [{oid[:8]}] {obj.name:<26} {power}/{hull-dmg}({hull}) {tap}{ss}{det}"
                )
        printed_any = False
        for b in (DepthBand.SURFACE, DepthBand.PERISCOPE, DepthBand.MID, DepthBand.DEEP, DepthBand.CRUSH, "?"):
            if bands.get(b):
                lbl = b.name if hasattr(b, "name") else "UNKNOWN"
                print(f"  {lbl}:")
                for line in bands[b]:
                    print(line)
                printed_any = True
        if not printed_any:
            print("  (no vessels on battlefield)")

        # Mines
        mines = []
        if bf:
            for oid in bf.objects:
                obj = state.objects.get(oid)
                if obj and obj.controller == pid and is_mine(obj):
                    mines.append(f"    [{oid[:8]}] {obj.name} @ {_band_label(obj.state.depth_band)}")
        if mines:
            print("  MINES:")
            for line in mines:
                print(line)

    _player_block("ME (P1)", p1, p1_id)
    _player_block("AI (P2)", p2, p2_id)

    # My hand
    print(f"\n[MY HAND]  ({len(state.zones.get(f'hand_{p1_id}').objects) if state.zones.get(f'hand_{p1_id}') else 0} cards)")
    hand = state.zones.get(f"hand_{p1_id}")
    if hand:
        for oid in hand.objects:
            obj = state.objects.get(oid)
            if not obj or not obj.card_def:
                continue
            cd = obj.card_def
            cost = getattr(cd, "mana_cost", "") or ""
            types = obj.characteristics.types
            type_aliases = {
                "DEPTHS_VESSEL": "VESSEL",
                "DEPTHS_CREW": "CREW",
                "DEPTHS_WEAPON": "WEAPON",
                "DEPTHS_MINE": "MINE",
                "INSTANT": "ACTION",       # SUBS Action cards reuse INSTANT
                "ENCHANTMENT": "DOCTRINE",  # SUBS Doctrines reuse ENCHANTMENT
            }
            tnames = sorted(type_aliases.get(t.name, t.name) for t in types if t.name in type_aliases) or ["?"]
            tlabel = "/".join(tnames)
            pt = ""
            if getattr(obj.characteristics, "power", None) is not None:
                pt = f" {obj.characteristics.power}/{obj.characteristics.toughness}"
            print(f"  [{oid[:8]}] {tlabel:<10} {obj.name:<28}{pt:<8} cost={cost}")

    # Library / graveyard sizes
    lib = state.zones.get(f"library_{p1_id}")
    gy = state.zones.get(f"graveyard_{p1_id}")
    print(f"\n[ZONES]  library={len(lib.objects) if lib else 0}  graveyard={len(gy.objects) if gy else 0}")

    # Pending plan
    handler = payload.get("handler")
    if handler:
        n_man = len(handler.maneuver_q)
        n_reg = len(handler.regroup_q)
        n_atk = len(handler.attackers_spec)
        if n_man + n_reg + n_atk:
            print(f"\n[PLAN QUEUED]  maneuver={n_man}  regroup={n_reg}  attackers={n_atk}")
            print("  (call plan-show to inspect; play-turn to execute)")


# =============================================================================
# Lookup helpers
# =============================================================================

def _find_in_hand(state, p1_id: str, name_or_prefix: str):
    hand = state.zones.get(f"hand_{p1_id}")
    if not hand:
        return None
    nlow = name_or_prefix.lower()
    for oid in hand.objects:
        obj = state.objects.get(oid)
        if not obj:
            continue
        if obj.id.startswith(name_or_prefix) or obj.name.lower() == nlow:
            return obj
    # Fuzzy: substring on name
    for oid in hand.objects:
        obj = state.objects.get(oid)
        if obj and nlow in obj.name.lower():
            return obj
    return None


def _find_on_battlefield(state, p1_id: Optional[str], name_or_prefix: str):
    """Resolve to an object on the battlefield. p1_id=None to allow either side."""
    bf = state.zones.get("battlefield")
    if not bf:
        return None
    nlow = name_or_prefix.lower()
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if not obj:
            continue
        if p1_id and obj.controller != p1_id:
            continue
        if obj.id.startswith(name_or_prefix) or obj.name.lower() == nlow:
            return obj
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if not obj:
            continue
        if p1_id and obj.controller != p1_id:
            continue
        if nlow in obj.name.lower():
            return obj
    return None


# =============================================================================
# Commands
# =============================================================================

def cmd_start(args) -> None:
    from src.engine.game import Game
    from src.engine.depths_turn import DepthsTurnManager
    from src.ai.depths_adapter import DepthsAIAdapter
    from src.cards.depths.submarine_fleet.decks import (
        SUBS_STARTER_DECKS, make_subs_flagship,
    )

    deck1_key = f"SUBS_{args.my_deck}"
    deck2_key = f"SUBS_{args.ai_deck}"
    if deck1_key not in SUBS_STARTER_DECKS or deck2_key not in SUBS_STARTER_DECKS:
        avail = sorted(k.replace("SUBS_", "") for k in SUBS_STARTER_DECKS)
        sys.exit(f"Unknown deck. Available: {', '.join(avail)}")

    deck1 = SUBS_STARTER_DECKS[deck1_key]()
    deck2 = SUBS_STARTER_DECKS[deck2_key]()
    flag = make_subs_flagship()

    game = Game(mode="depths")
    p1 = game.add_player("ME")
    p2 = game.add_player("AI")

    tm = DepthsTurnManager(game.state)
    game.turn_manager = tm

    handler = PlannedHandler()
    handler.defense_ai = DepthsAIAdapter(difficulty=args.difficulty)
    ai_handler = AIDictAdapter(DepthsAIAdapter(difficulty=args.difficulty))

    tm.set_ai_handler(handler, p1.id)
    tm.set_ai_handler(ai_handler, p2.id)
    # Both must be marked as AI-controlled so the action-loop runs for both
    # players; our handler still keeps P1 under harness control because it
    # only emits actions the harness queues.
    tm.set_ai_player(p1.id)
    tm.set_ai_player(p2.id)

    asyncio.run(tm.setup_game(game, deck1, deck2, flag, flag))

    payload = {
        "game": game,
        "p1_id": p1.id,
        "p2_id": p2.id,
        "handler": handler,
        "ai_handler": ai_handler,
        "history": [],  # list of (turn, actor, str)
        "args": {
            "my_deck": args.my_deck,
            "ai_deck": args.ai_deck,
            "difficulty": args.difficulty,
        },
    }

    # If AI is on the play, run their first turn before handing control to ME.
    # The setup leaves current_player_index at 0; check turn_order.
    first = tm.turn_order[tm.current_player_index] if tm.turn_order else p1.id
    if first == p2.id:
        print("AI is on the play — running their first turn.")
        asyncio.run(tm.run_turn(p2.id))
        payload["history"].append((game.state.turn_number, "AI", "first turn"))

    _save(payload)
    print(f"Started: ME={p1.id[:8]} (deck={args.my_deck}) "
          f"vs AI={p2.id[:8]} (deck={args.ai_deck}, difficulty={args.difficulty})")
    print()
    _print_state(payload)


def cmd_state(args) -> None:
    payload = _load()
    _print_state(payload)


def cmd_plan_deploy(args) -> None:
    payload = _load()
    obj = _find_in_hand(payload["game"].state, payload["p1_id"], args.card)
    if not obj:
        print(f"Not in hand: {args.card!r}")
        return
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_DEPLOY_VESSEL",
        "card_id": obj.id,
    })
    _save(payload)
    print(f"+ DEPLOY {obj.name} [{obj.id[:8]}]")


def cmd_plan_dive(args) -> None:
    payload = _load()
    obj = _find_on_battlefield(payload["game"].state, payload["p1_id"], args.vessel)
    if not obj:
        print(f"Not on battlefield: {args.vessel!r}")
        return
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_DIVE",
        "vessel_id": obj.id,
    })
    _save(payload)
    print(f"+ DIVE {obj.name} [{obj.id[:8]}] (cost: 1 Sonar)")


def cmd_plan_surface(args) -> None:
    payload = _load()
    obj = _find_on_battlefield(payload["game"].state, payload["p1_id"], args.vessel)
    if not obj:
        print(f"Not on battlefield: {args.vessel!r}")
        return
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_SURFACE_VESSEL",
        "vessel_id": obj.id,
    })
    _save(payload)
    print(f"+ SURFACE {obj.name} [{obj.id[:8]}] (free)")


def cmd_plan_attach(args) -> None:
    payload = _load()
    state = payload["game"].state
    p1_id = payload["p1_id"]
    att = _find_in_hand(state, p1_id, args.attachment)
    if not att:
        print(f"Attachment not in hand: {args.attachment!r}")
        return
    target = _find_on_battlefield(state, p1_id, args.target)
    if not target:
        print(f"Target not on battlefield: {args.target!r}")
        return
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_ATTACH",
        "card_id": att.id,
        "target_id": target.id,
    })
    _save(payload)
    print(f"+ ATTACH {att.name} → {target.name}")


def cmd_plan_mine(args) -> None:
    from src.engine.depths import DepthBand
    payload = _load()
    obj = _find_in_hand(payload["game"].state, payload["p1_id"], args.card)
    if not obj:
        print(f"Not in hand: {args.card!r}")
        return
    band = None
    if args.depth:
        try:
            band = DepthBand[args.depth.upper()]
        except KeyError:
            print(f"Bad depth {args.depth!r}. Use one of: SURFACE/PERISCOPE/MID/DEEP/CRUSH")
            return
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_LAY_MINE",
        "card_id": obj.id,
        "depth_band": band,
    })
    _save(payload)
    print(f"+ LAY MINE {obj.name} @ {band.name if band else 'PERISCOPE (default)'}")


def cmd_plan_cast(args) -> None:
    payload = _load()
    state = payload["game"].state
    p1_id = payload["p1_id"]
    obj = _find_in_hand(state, p1_id, args.card)
    if not obj:
        print(f"Not in hand: {args.card!r}")
        return
    targets = []
    if args.target:
        # Allow "flagship" as a special token for the opponent's flagship.
        if args.target.lower() == "flagship":
            from src.engine.depths import get_flagship
            flag = get_flagship(payload["p2_id"], state)
            if flag:
                targets.append(flag.id)
        else:
            tobj = _find_on_battlefield(state, None, args.target)
            if tobj:
                targets.append(tobj.id)
            else:
                print(f"Target not found: {args.target!r}")
                return
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_CAST_SPELL",
        "card_id": obj.id,
        "targets": targets,
        "modes": [],
    })
    _save(payload)
    print(f"+ CAST {obj.name}{' targeting ' + args.target if args.target else ''}")


def cmd_plan_ability(args) -> None:
    payload = _load()
    obj = _find_on_battlefield(payload["game"].state, payload["p1_id"], args.source)
    if not obj:
        print(f"Source not on battlefield: {args.source!r}")
        return
    targets = []
    if args.target:
        tobj = _find_on_battlefield(payload["game"].state, None, args.target)
        if tobj:
            targets.append(tobj.id)
    payload["handler"].maneuver_q.append({
        "action_type": "DEPTHS_ACTIVATE_ABILITY",
        "source_id": obj.id,
        "ability_index": args.idx,
        "targets": targets,
    })
    _save(payload)
    print(f"+ ACTIVATE ability[{args.idx}] of {obj.name}")


def cmd_plan_attack(args) -> None:
    from src.ai.depths_adapter import AttackerSpec
    from src.engine.depths import get_flagship, DepthBand
    payload = _load()
    state = payload["game"].state
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    for spec in args.specs:
        if ":" not in spec:
            print(f"Bad spec {spec!r} — expected vessel_prefix:target_prefix (use 'flagship' for opponent's flagship)")
            continue
        vstr, tstr = spec.split(":", 1)
        vobj = _find_on_battlefield(state, p1_id, vstr)
        if not vobj:
            print(f"  attacker {vstr!r} not found on my battlefield")
            continue
        if tstr.lower() == "flagship":
            tobj = get_flagship(p2_id, state)
            if not tobj:
                print("  opponent has no flagship?")
                continue
        else:
            tobj = _find_on_battlefield(state, p2_id, tstr)
            if not tobj:
                print(f"  target {tstr!r} not found on opponent's battlefield")
                continue
        firing_band = vobj.state.depth_band or DepthBand.SURFACE
        payload["handler"].attackers_spec.append(AttackerSpec(
            vessel_id=vobj.id,
            target_id=tobj.id,
            firing_depth_band=firing_band,
        ))
        print(f"+ ATTACK {vobj.name}({firing_band.name}) → {tobj.name}")
    _save(payload)


def cmd_plan_show(args) -> None:
    payload = _load()
    h = payload["handler"]
    print(f"=== Planned actions ===")
    if not (h.maneuver_q or h.regroup_q or h.attackers_spec):
        print("  (empty)")
        return
    if h.maneuver_q:
        print("MANEUVER:")
        for i, a in enumerate(h.maneuver_q):
            print(f"  {i+1}. {a}")
    if h.attackers_spec:
        print("ATTACKERS:")
        for i, a in enumerate(h.attackers_spec):
            print(f"  {i+1}. {a}")
    if h.regroup_q:
        print("REGROUP:")
        for i, a in enumerate(h.regroup_q):
            print(f"  {i+1}. {a}")


def cmd_plan_clear(args) -> None:
    payload = _load()
    payload["handler"].maneuver_q.clear()
    payload["handler"].regroup_q.clear()
    payload["handler"].attackers_spec.clear()
    _save(payload)
    print("Plan cleared.")


def _format_combat_events(events: list, state) -> list[str]:
    """Scan a list of Events and produce human-readable combat-log lines.
    Covers attack declarations, detection ping/fail, damage, sinks, mines."""
    from src.engine.types import EventType

    def _name(oid):
        if not oid:
            return "?"
        o = state.objects.get(oid)
        return o.name if o else oid[:8]

    lines: list[str] = []
    for ev in events or []:
        try:
            t = ev.type
            p = ev.payload or {}
        except AttributeError:
            continue

        if t == EventType.ATTACK_DECLARED and p.get("is_depths"):
            band = p.get("firing_depth_band")
            band_label = band.name if band is not None and hasattr(band, "name") else "?"
            lines.append(f"ATTACK {_name(p.get('attacker_id'))}({band_label}) → {_name(p.get('target_id'))}")
        elif t == EventType.DEPTHS_DETECT:
            # depths_combat.py emits payload key 'cost_paid'.
            spent = p.get("cost_paid", p.get("sonar_spent", p.get("cost", "?")))
            lines.append(f"DETECT {_name(p.get('attacker_id'))} (sonar {spent})")
        elif t == EventType.DEPTHS_DETECTION_FAIL:
            lines.append(f"DETECT-FAIL {_name(p.get('attacker_id'))}")
        elif t == EventType.DEPTHS_MINE_TRIGGER:
            lines.append(
                f"MINE {_name(p.get('mine_id'))} → "
                f"{_name(p.get('triggering_vessel_id') or p.get('object_id'))}"
            )
        elif t == EventType.DAMAGE:
            tgt = p.get("target") or p.get("target_id")
            src = ev.source or p.get("source") or p.get("source_id")
            amt = p.get("amount") or p.get("damage")
            if amt is None or tgt is None:
                continue
            lines.append(f"DMG {_name(src)} → {_name(tgt)} for {amt}")
        elif t == EventType.OBJECT_DESTROYED:
            reason = p.get("reason") or "destroyed"
            lines.append(f"SUNK {_name(p.get('object_id'))} ({reason})")
    return lines


def cmd_play_turn(args) -> None:
    """Execute MY turn (drains the queue), then run AI's full turn."""
    payload = _load()
    game = payload["game"]
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]
    h = payload["handler"]
    if game.is_game_over():
        print("Game already over.")
        _print_state(payload)
        return

    n_man = len(h.maneuver_q)
    n_atk = len(h.attackers_spec)
    h.execution_log.clear()

    # Wrap execute_action so we report each action's success/fail.
    tm = game.turn_manager
    orig_execute = tm.execute_action
    me_actions: list[str] = []
    ai_actions: list[str] = []

    async def _wrapped(player_id, action):
        ok, msg, evs = await orig_execute(player_id, action)
        label = h._label(action, game.state)
        bucket = me_actions if player_id == p1_id else ai_actions
        bucket.append(f"{'OK' if ok else 'NO'} {label}{f' [{msg}]' if msg and not ok else ''}")
        return ok, msg, evs
    tm.execute_action = _wrapped

    # Capture pipeline events (combat math goes through game.emit, not the
    # return value of run_turn). We re-wrap before each phase so events_me
    # and events_ai stay separated.
    captured_events: list = []
    orig_emit = game.emit

    def _emit_wrapped(event):
        captured_events.append(event)
        return orig_emit(event)
    game.emit = _emit_wrapped

    # Run MY turn — handler will pop from the queue.
    print(f"--- Running MY turn ({n_man} maneuver actions + {n_atk} attackers) ---")
    try:
        asyncio.run(game.turn_manager.run_turn(p1_id))
    except Exception as exc:
        import traceback
        print(f"!! ERROR during my turn: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        tm.execute_action = orig_execute
        game.emit = orig_emit
        _save(payload)
        return
    for line in me_actions:
        print(f"  ME: {line}")
    me_events = list(captured_events)
    captured_events.clear()
    for line in _format_combat_events(me_events, game.state):
        print(f"  combat: {line}")
    if h.attackers_spec:
        h.attackers_spec.clear()
    payload["history"].append((game.state.turn_number, "ME", f"played {n_man} actions, {n_atk} attacks"))

    if game.is_game_over():
        _save(payload)
        _print_state(payload)
        return

    # Sanity: warn if the queue had leftovers (player tried more than the
    # phase could absorb — likely a planning error).
    leftover = []
    if h.maneuver_q:
        leftover.append(f"{len(h.maneuver_q)} maneuver")
    if h.regroup_q:
        leftover.append(f"{len(h.regroup_q)} regroup")
    if h.attackers_spec:
        leftover.append(f"{len(h.attackers_spec)} attacker(s)")
    if leftover:
        print(f"!! WARNING: leftover queued actions not played: {', '.join(leftover)}")
        h.maneuver_q.clear()
        h.regroup_q.clear()
        h.attackers_spec.clear()

    # Run AI's turn.
    print(f"--- Running AI turn ---")
    try:
        asyncio.run(game.turn_manager.run_turn(p2_id))
    except Exception as exc:
        import traceback
        print(f"!! ERROR during AI turn: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        tm.execute_action = orig_execute
        game.emit = orig_emit
        _save(payload)
        return
    for line in ai_actions:
        print(f"  AI: {line}")
    ai_events = list(captured_events)
    captured_events.clear()
    for line in _format_combat_events(ai_events, game.state):
        print(f"  combat: {line}")
    payload["history"].append((game.state.turn_number, "AI", "took turn"))
    tm.execute_action = orig_execute  # un-monkey-patch before we pickle
    game.emit = orig_emit

    _save(payload)
    _print_state(payload)


def cmd_history(args) -> None:
    payload = _load()
    print("=== History ===")
    for turn, actor, action in payload["history"][-30:]:
        print(f"  turn {turn}  {actor:<3}  {action}")


def cmd_result(args) -> None:
    payload = _load()
    game = payload["game"]
    state = game.state
    p1 = state.players[payload["p1_id"]]
    p2 = state.players[payload["p2_id"]]
    if not game.is_game_over():
        print("Game still in progress.")
        return
    if getattr(p1, "has_lost", False) and getattr(p2, "has_lost", False):
        print("DRAW")
    elif getattr(p1, "has_lost", False):
        print("AI WON")
    elif getattr(p2, "has_lost", False):
        print("ME WON")
    else:
        print("(unclear)")


def cmd_legal(args) -> None:
    """Cheat sheet: what can I do right now?"""
    payload = _load()
    state = payload["game"].state
    p1_id = payload["p1_id"]
    p1 = state.players[p1_id]
    print(f"TC={p1.tc}  SC={p1.sc}")
    print()
    print("HAND (cards I can deploy/cast/lay/attach):")
    hand = state.zones.get(f"hand_{p1_id}")
    if hand:
        for oid in hand.objects:
            obj = state.objects.get(oid)
            if obj and obj.card_def:
                cost = getattr(obj.card_def, "mana_cost", "") or ""
                print(f"  [{oid[:8]}] {obj.name:<28} cost={cost}")
    print()
    print("MY VESSELS (can dive/surface/attack):")
    bf = state.zones.get("battlefield")
    if bf:
        from src.engine.depths import is_vessel
        for oid in bf.objects:
            obj = state.objects.get(oid)
            if obj and obj.controller == p1_id and is_vessel(obj):
                if "Flagship" in obj.characteristics.subtypes:
                    continue
                tap = " (tapped)" if getattr(obj.state, "tapped", False) else ""
                ss = " (SS)" if getattr(obj.state, "summoning_sickness", False) else ""
                band = obj.state.depth_band.name if obj.state.depth_band else "?"
                print(f"  [{oid[:8]}] {obj.name:<28} P/H={obj.characteristics.power}/{obj.characteristics.toughness} @ {band}{tap}{ss}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start"); p.add_argument("--my-deck", default="wolfpack")
    p.add_argument("--ai-deck", default="silent_hunter")
    p.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    p.set_defaults(fn=cmd_start)

    sub.add_parser("state").set_defaults(fn=cmd_state)
    sub.add_parser("legal").set_defaults(fn=cmd_legal)

    p = sub.add_parser("plan-deploy"); p.add_argument("card"); p.set_defaults(fn=cmd_plan_deploy)
    p = sub.add_parser("plan-dive"); p.add_argument("vessel"); p.set_defaults(fn=cmd_plan_dive)
    p = sub.add_parser("plan-surface"); p.add_argument("vessel"); p.set_defaults(fn=cmd_plan_surface)
    p = sub.add_parser("plan-attach"); p.add_argument("attachment"); p.add_argument("target"); p.set_defaults(fn=cmd_plan_attach)
    p = sub.add_parser("plan-mine"); p.add_argument("card"); p.add_argument("depth", nargs="?"); p.set_defaults(fn=cmd_plan_mine)
    p = sub.add_parser("plan-cast"); p.add_argument("card"); p.add_argument("target", nargs="?"); p.set_defaults(fn=cmd_plan_cast)
    p = sub.add_parser("plan-ability"); p.add_argument("source"); p.add_argument("--idx", type=int, default=0); p.add_argument("--target"); p.set_defaults(fn=cmd_plan_ability)
    p = sub.add_parser("plan-attack"); p.add_argument("specs", nargs="+", help="vessel_prefix:target_prefix (or :flagship)"); p.set_defaults(fn=cmd_plan_attack)
    sub.add_parser("plan-show").set_defaults(fn=cmd_plan_show)
    sub.add_parser("plan-clear").set_defaults(fn=cmd_plan_clear)

    sub.add_parser("play-turn").set_defaults(fn=cmd_play_turn)
    sub.add_parser("history").set_defaults(fn=cmd_history)
    sub.add_parser("result").set_defaults(fn=cmd_result)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
