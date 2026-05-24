"""Local single-match harness for Clankers LLM-vs-LLM play.

Spawns a tiny FastAPI server on localhost that holds ONE match's state in
memory. Two external clients (Claude Code Agent subagents, typically) poll
``/state`` and POST ``/action`` to drive the match — mirrors the production
``launch_ultra_agent.sh`` REST contract, but server-less and per-match.

Run:
    python scripts/play/clankers_local_match.py \\
        --deck-p1 CLAN_forge --deck-p2 CLAN_mirth \\
        --port 0 --json-out logs/match.json

``--port 0`` picks a free port; the chosen port is printed as the FIRST
output line ``LISTEN: <port>`` so the orchestrator can read it. The server
exits when the game completes (or after ``--max-turns``).

Endpoints (all return JSON):
    GET  /state?player_id=p1       — full state from p1's perspective
    GET  /pending?player_id=p1     — what decision p1 needs to make next (or null)
    POST /action                   — body: {player_id, decision_kind, value}
    GET  /done                     — winner + final state once the match ends

Design:
- A background thread runs the full turn loop in-engine.
- Per-player BlockingAIHandler instances block on ``threading.Event`` when
  the engine calls a decision method (choose_assemble_action, etc.).
- /action POST fulfills the pending Event and returns.
- /state reads a snapshot of the latest engine state.
- /pending returns the active decision so the agent knows what to POST.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

# Make repo root importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, HTTPException, Request
import uvicorn

from src.ai.clankers_adapter import ClankersAIAdapter
from src.cards.clankers.CLAN.decks import CLAN_STARTER_DECKS
from src.engine.clankers_turn import ClankersTurnManager
from src.engine.types import GameState, Player


# ---------------------------------------------------------------------------
# Blocking AI handler — turn-manager calls these from the engine thread; they
# block until an external POST fulfills the pending decision.
# ---------------------------------------------------------------------------


class _BlockingHandler:
    """One per seat. Blocks the engine thread on .pending until /action POSTs."""

    def __init__(self, player_id: str, fallback_difficulty: str = "hard"):
        self.player_id = player_id
        self.pending: Optional[dict] = None  # the current "what to decide" payload
        self.pending_event = threading.Event()
        self.response: Any = None
        self.response_event = threading.Event()
        self.lock = threading.Lock()
        # Heuristic fallback for timeouts.
        self._fallback = ClankersAIAdapter(difficulty=fallback_difficulty)
        # Bound how long the engine will block (the harness may otherwise hang).
        self.timeout_seconds = 300.0

    def _ask(self, kind: str, payload: dict, fallback_fn) -> Any:
        with self.lock:
            self.pending = {"kind": kind, "player_id": self.player_id, **payload}
            self.response = None
            self.response_event.clear()
            self.pending_event.set()
        if not self.response_event.wait(timeout=self.timeout_seconds):
            # Agent didn't respond in time — fall back.
            with self.lock:
                self.pending = None
                self.pending_event.clear()
            return fallback_fn()
        result = self.response
        with self.lock:
            self.pending = None
            self.pending_event.clear()
        return result

    def submit(self, value: Any) -> None:
        """Called from the HTTP thread via /action."""
        with self.lock:
            self.response = value
            self.response_event.set()

    # --- engine-facing methods (delegate to _ask) ---

    def choose_assemble_action(self, state, player_id):
        try:
            legal = self._fallback._legal_actions_for(state, player_id)
        except Exception:
            legal = [{"action": "pass"}]
        return self._ask(
            "choose_assemble_action",
            {"legal_actions": _slot_legal(legal, state), "raw_legal": legal,
             "state_snapshot": _state_for(state, player_id)},
            lambda: self._fallback.choose_assemble_action(state, player_id),
        )

    def choose_attackers(self, state, player_id):
        candidates = _eligible_attackers(state, player_id)
        return self._ask(
            "choose_attackers",
            {"candidates": candidates,
             "state_snapshot": _state_for(state, player_id)},
            lambda: self._fallback.choose_attackers(state, player_id),
        )

    def choose_blockers(self, state, player_id, attackers):
        defenders = _eligible_attackers(state, player_id)
        return self._ask(
            "choose_blockers",
            {"attackers": [_describe_obj(state, a) for a in attackers],
             "attacker_ids": list(attackers),
             "defenders": defenders,
             "state_snapshot": _state_for(state, player_id)},
            lambda: self._fallback.choose_blockers(state, player_id, attackers),
        )

    def choose_refill(self, state, player_id):
        return self._ask(
            "choose_refill",
            {"library_size": _library_size(state, player_id),
             "hand_size": _hand_size(state, player_id),
             "workshop_integrity": _wi(state, player_id),
             "state_snapshot": _state_for(state, player_id)},
            lambda: self._fallback.choose_refill(state, player_id),
        )

    def mulligan_decision(self, state, player_id, num_kept=7):
        return False  # Clankers doesn't ship mulligans in v1

    def choose_target(self, state, source_id, candidates, requirement):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return self._ask(
            "choose_target",
            {"candidates": [_describe_obj(state, c) for c in candidates],
             "candidate_ids": list(candidates),
             "source": _describe_obj(state, source_id),
             "requirement": requirement,
             "state_snapshot": _state_for(state, source_id) if isinstance(source_id, str) else None},
            lambda: self._fallback.choose_target(state, source_id, candidates, requirement),
        )


# ---------------------------------------------------------------------------
# State rendering — minimal, slot-indexed
# ---------------------------------------------------------------------------


def _slot_legal(legal: list[dict], state) -> list[dict]:
    """Replace obj_ids in actions with slot indices + readable names."""
    return [{"slot": i + 1, **_describe_action(a, state)} for i, a in enumerate(legal)]


def _describe_action(action: dict, state) -> dict:
    out = {"action": action.get("action", "?")}
    card_id = action.get("card_obj_id") or action.get("part_obj_id") or action.get("source_obj_id")
    if card_id:
        obj = state.objects.get(card_id)
        out["card"] = obj.card_def.name if (obj and obj.card_def) else "?"
    if "compute_cost" in action:
        out["compute_cost"] = action["compute_cost"]
    target = action.get("target_chassis_id")
    if target:
        t = state.objects.get(target)
        out["target"] = t.card_def.name if (t and t.card_def) else "?"
    return out


def _describe_obj(state, obj_id: str) -> dict:
    obj = state.objects.get(obj_id) if obj_id else None
    if obj is None or obj.card_def is None:
        return {"id": obj_id, "name": "?"}
    return {"id": obj_id, "name": obj.card_def.name,
            "tapped": obj.state.tapped,
            "attached_to": obj.state.attached_to,
            "damage": obj.state.damage_marked}


def _eligible_attackers(state, player_id: str) -> list[dict]:
    from src.engine.types import CardType
    out: list[dict] = []
    assemblies = getattr(state, "clankers_assemblies", {}).get(player_id, [])
    for obj_id in assemblies:
        obj = state.objects.get(obj_id)
        if obj is None or obj.state.tapped:
            continue
        eff_p = _eff_power(state, obj_id)
        eff_i = _eff_int(state, obj_id)
        if obj.state.damage_marked >= eff_i:
            continue
        out.append({"id": obj_id, "name": obj.card_def.name if obj.card_def else "?",
                    "eff_power": eff_p, "eff_int": eff_i})
    for obj_id, obj in state.objects.items():
        if obj.controller != player_id or obj.state.attached_to is not None or obj.state.tapped:
            continue
        if obj.card_def is None:
            continue
        types = getattr(obj.card_def.characteristics, "types", set()) or set()
        if CardType.CLANKERS_WEAPON in types or CardType.CLANKERS_ADD_ON in types:
            out.append({"id": obj_id, "name": f"solo {obj.card_def.name}",
                        "eff_power": 1, "eff_int": 1})
    return out


def _state_for(state, player_id: str) -> dict:
    opp = next((p for p in state.players if p != player_id), None)
    return {
        "turn_number": state.turn_number,
        "active_player": state.active_player,
        "you": player_id,
        "opponent": opp,
        "wi_you": _wi(state, player_id),
        "wi_opp": _wi(state, opp) if opp else None,
        "compute": _compute(state, player_id),
        "scrap": _scrap(state, player_id),
        "library_size": _library_size(state, player_id),
        "hand_size": _hand_size(state, player_id),
        "hand": _hand_slots(state, player_id),
        "your_assemblies": _assemblies(state, player_id),
        "opponent_assemblies": _assemblies(state, opp) if opp else [],
        "deathclock_active": bool(getattr(state, "clankers_containment_failure", False)),
    }


def _wi(state, pid): return getattr(state, "clankers_workshop_integrity", {}).get(pid, 0)
def _compute(state, pid): return getattr(state, "clankers_compute_pool", {}).get(pid, 0)
def _scrap(state, pid): return getattr(state, "clankers_scrap_pool", {}).get(pid, 0)


def _library_size(state, pid):
    z = state.zones.get(f"library_{pid}")
    return len(z.objects) if z else 0


def _hand_size(state, pid):
    z = state.zones.get(f"hand_{pid}")
    return len(z.objects) if z else 0


def _hand_slots(state, pid) -> list[dict]:
    z = state.zones.get(f"hand_{pid}")
    if not z:
        return []
    out = []
    for i, oid in enumerate(z.objects, 1):
        obj = state.objects.get(oid)
        if obj is None or obj.card_def is None:
            continue
        cd = obj.card_def
        out.append({"slot": f"hand-{i}", "name": cd.name,
                    "compute_cost": getattr(cd, "compute_cost", 0),
                    "archetype": getattr(cd, "clankers_archetype", "?")})
    return out


def _assemblies(state, pid) -> list[dict]:
    out = []
    for obj_id in getattr(state, "clankers_assemblies", {}).get(pid, []):
        obj = state.objects.get(obj_id)
        if obj is None or obj.card_def is None:
            continue
        attached = []
        for a_id in obj.state.attachments or []:
            a = state.objects.get(a_id)
            if a and a.card_def:
                attached.append({"id": a_id, "name": a.card_def.name})
        out.append({
            "id": obj_id, "name": obj.card_def.name,
            "eff_power": _eff_power(state, obj_id),
            "eff_int": _eff_int(state, obj_id),
            "damage": obj.state.damage_marked,
            "tapped": obj.state.tapped,
            "attached": attached,
        })
    return out


def _eff_power(state, obj_id):
    try:
        from src.engine.clankers import compute_effective_power
        return compute_effective_power(state, obj_id)
    except Exception:
        return 0


def _eff_int(state, obj_id):
    try:
        from src.engine.clankers import compute_effective_integrity
        return compute_effective_integrity(state, obj_id)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# FastAPI app + match thread
# ---------------------------------------------------------------------------


class MatchHarness:
    def __init__(self, deck_p1_label: str, deck_p2_label: str, max_turns: int = 40):
        self.deck_p1_label = deck_p1_label
        self.deck_p2_label = deck_p2_label
        self.max_turns = max_turns
        self.state = GameState()
        self.state.players["p1"] = Player(id="p1", name="P1")
        self.state.players["p2"] = Player(id="p2", name="P2")
        self.state._game = None  # type: ignore[attr-defined]
        self.tm = ClankersTurnManager(self.state)
        self.handler_p1 = _BlockingHandler("p1")
        self.handler_p2 = _BlockingHandler("p2")
        self.tm.set_ai_handler(self.handler_p1, "p1")
        self.tm.set_ai_handler(self.handler_p2, "p2")
        self._done = threading.Event()
        self.winner: Optional[str] = None
        self.loser: Optional[str] = None
        self.turns_played: int = 0
        self.error: Optional[str] = None

    def run(self) -> None:
        """Run the match in this thread; blocks until done."""
        try:
            core_p1, deck_p1 = CLAN_STARTER_DECKS[self.deck_p1_label]()
            core_p2, deck_p2 = CLAN_STARTER_DECKS[self.deck_p2_label]()
            self.tm.setup_game(deck_p1, core_p1, deck_p2, core_p2)
            turn = 0
            while turn < self.max_turns:
                active = self.state.active_player
                if active is None:
                    break
                self.tm.run_turn(active)
                turn += 1
                self.turns_played = turn
                if getattr(self.state, "game_over", False):
                    break
            self.loser = getattr(self.state, "clankers_loser", None)
            if self.loser is None:
                self.winner = None
            else:
                self.winner = "p1" if self.loser == "p2" else "p2"
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self._done.set()
            # Wake any blocked agents so /action returns cleanly.
            self.handler_p1.submit(None)
            self.handler_p2.submit(None)


# Single global harness — the server only runs one match at a time.
_HARNESS: Optional[MatchHarness] = None


def make_app(harness: MatchHarness) -> FastAPI:
    app = FastAPI()

    @app.get("/state")
    def state(player_id: str):
        if player_id not in ("p1", "p2"):
            raise HTTPException(400, "bad player_id")
        return _state_for(harness.state, player_id)

    @app.get("/pending")
    def pending(player_id: str):
        handler = harness.handler_p1 if player_id == "p1" else harness.handler_p2
        if not handler.pending_event.is_set():
            return {"pending": None}
        return {"pending": handler.pending}

    @app.post("/action")
    async def action(request: Request):
        body = await request.json()
        pid = body.get("player_id")
        if pid not in ("p1", "p2"):
            raise HTTPException(400, "bad player_id")
        handler = harness.handler_p1 if pid == "p1" else harness.handler_p2
        if not handler.pending_event.is_set():
            raise HTTPException(409, "no pending decision for this player")
        kind = handler.pending["kind"]
        value = body.get("value")
        # Per-kind: translate AND validate. Raises 422 with a precise error
        # if the agent submitted a malformed payload — better than silently
        # dropping into "pass" / "[]" / "{}" which masks bugs (the issue
        # caught by the Wave-5 BULWARK agent).
        translated, errors = _translate(kind, handler.pending, value)
        if errors:
            raise HTTPException(422, {"errors": errors, "kind": kind,
                                       "expected_schema": _schema_hint(kind)})
        handler.submit(translated)
        return {"ok": True, "kind": kind, "submitted": str(translated)[:200]}

    @app.get("/done")
    def done():
        return {"done": harness._done.is_set(), "winner": harness.winner,
                "loser": harness.loser, "turns": harness.turns_played,
                "error": harness.error}

    return app


def _coerce_slot(raw: Any, max_n: int, candidates_with_ids: Optional[list[dict]] = None) -> Optional[int]:
    """Resolve a slot reference to an int.

    Accepts an int directly, OR a string-of-int, OR an obj_id that maps to
    a candidate. Returns None if nothing valid.
    """
    if isinstance(raw, int) and 1 <= raw <= max_n:
        return raw
    if isinstance(raw, str):
        # Try parsing as int first.
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= max_n:
                return n
        # Try looking up as obj_id in candidates.
        if candidates_with_ids:
            for i, c in enumerate(candidates_with_ids, 1):
                if c.get("id") == raw:
                    return i
    return None


def _schema_hint(kind: str) -> str:
    return {
        "choose_assemble_action": '{"slot": <int>} — 0=pass, 1..N from legal_actions',
        "choose_attackers": '{"slots": [<int>, ...]} — 1-indexed slots from candidates list (NOT obj_ids)',
        "choose_blockers": '{"blocks": [{"attacker_slot": <int>, "blocker_slot": <int>}, ...]} — 1-indexed integers, NOT obj_ids',
        "choose_refill": '{"take": <bool>}',
        "choose_target": '{"slot": <int>} — 1-indexed slot from candidates',
    }.get(kind, "")


def _translate(kind: str, pending: dict, value: Any) -> tuple[Any, list[str]]:
    """Map agent slot-indexed answers back to obj_ids the engine expects.

    Returns (translated_value, errors). If errors is non-empty, the action
    endpoint will reject with 422 — agents learn from errors, silent drops
    teach nothing (Wave-5 lesson).
    """
    errors: list[str] = []

    if kind == "choose_assemble_action":
        if not isinstance(value, dict) or "slot" not in value:
            errors.append("expected dict with 'slot' key")
            return ({"action": "pass"}, errors)
        slot = value["slot"]
        legal = pending.get("raw_legal", [])
        if slot == 0:
            return ({"action": "pass"}, [])
        resolved = _coerce_slot(slot, len(legal))
        if resolved is None:
            errors.append(f"slot {slot!r} out of range (1..{len(legal)} or 0 for pass)")
            return ({"action": "pass"}, errors)
        return (legal[resolved - 1], [])

    if kind == "choose_attackers":
        if not isinstance(value, dict) or "slots" not in value:
            errors.append("expected dict with 'slots' key (list of ints)")
            return ([], errors)
        slots = value["slots"]
        if not isinstance(slots, list):
            errors.append("'slots' must be a list of integers (1-indexed)")
            return ([], errors)
        candidates = pending.get("candidates", [])
        out: list[str] = []
        for s in slots:
            resolved = _coerce_slot(s, len(candidates), candidates)
            if resolved is None:
                errors.append(f"attacker slot {s!r} invalid (expected int 1..{len(candidates)} or obj_id from candidates)")
                continue
            out.append(candidates[resolved - 1]["id"])
        return (out, errors)

    if kind == "choose_blockers":
        if not isinstance(value, dict) or "blocks" not in value:
            errors.append("expected dict with 'blocks' key (list of {attacker_slot, blocker_slot})")
            return ({}, errors)
        blocks = value["blocks"]
        if not isinstance(blocks, list):
            errors.append("'blocks' must be a list of {attacker_slot, blocker_slot}")
            return ({}, errors)
        attackers = pending.get("attacker_ids", [])
        attacker_dicts = [{"id": a} for a in attackers]
        defenders = pending.get("defenders", [])
        out: dict[str, str] = {}
        used: set[str] = set()
        for i, entry in enumerate(blocks):
            if not isinstance(entry, dict):
                errors.append(f"blocks[{i}] must be a dict")
                continue
            a_slot_raw = entry.get("attacker_slot")
            b_slot_raw = entry.get("blocker_slot")
            a_resolved = _coerce_slot(a_slot_raw, len(attackers), attacker_dicts)
            b_resolved = _coerce_slot(b_slot_raw, len(defenders), defenders)
            if a_resolved is None:
                errors.append(f"blocks[{i}].attacker_slot {a_slot_raw!r} invalid (expected int 1..{len(attackers)} or obj_id)")
                continue
            if b_resolved is None:
                errors.append(f"blocks[{i}].blocker_slot {b_slot_raw!r} invalid (expected int 1..{len(defenders)} or obj_id)")
                continue
            blocker_id = defenders[b_resolved - 1]["id"]
            if blocker_id in used:
                errors.append(f"blocks[{i}].blocker_slot {b_slot_raw!r} already used by an earlier block")
                continue
            used.add(blocker_id)
            out[attackers[a_resolved - 1]] = blocker_id
        return (out, errors)

    if kind == "choose_refill":
        if isinstance(value, dict) and "take" in value:
            return (bool(value["take"]), [])
        if isinstance(value, bool):
            return (value, [])
        errors.append("expected dict with 'take' key (bool)")
        return (True, errors)

    if kind == "choose_target":
        if not isinstance(value, dict) or "slot" not in value:
            errors.append("expected dict with 'slot' key")
            return (None, errors)
        slot = value["slot"]
        candidates = pending.get("candidate_ids", [])
        cand_dicts = [{"id": c} for c in candidates]
        resolved = _coerce_slot(slot, len(candidates), cand_dicts)
        if resolved is None:
            errors.append(f"slot {slot!r} out of range (1..{len(candidates)})")
            return (None, errors)
        return (candidates[resolved - 1], [])

    return (value, [])


def main():
    global _HARNESS
    p = argparse.ArgumentParser()
    p.add_argument("--deck-p1", required=True)
    p.add_argument("--deck-p2", required=True)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--max-turns", type=int, default=40)
    p.add_argument("--json-out", type=str, default=None)
    p.add_argument("--idle-timeout", type=int, default=600,
                   help="Exit if no /action POST for this many seconds")
    args = p.parse_args()

    _HARNESS = MatchHarness(args.deck_p1, args.deck_p2, max_turns=args.max_turns)
    app = make_app(_HARNESS)

    # Start uvicorn in a thread so we can also run the match loop.
    import socket
    if args.port == 0:
        s = socket.socket(); s.bind(("127.0.0.1", 0)); args.port = s.getsockname()[1]; s.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    print(f"LISTEN: {args.port}", flush=True)

    def _serve():
        import asyncio
        asyncio.run(server.serve())

    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()

    # Give the server a moment to bind.
    time.sleep(0.5)

    # Run the match in this (main) thread; the engine + handlers + server
    # all coordinate via the threading events inside _BlockingHandler.
    _HARNESS.run()

    # Match done — give agents a moment to fetch /done, then exit.
    print(f"DONE: winner={_HARNESS.winner} loser={_HARNESS.loser} "
          f"turns={_HARNESS.turns_played} error={_HARNESS.error}", flush=True)
    if args.json_out:
        result = {
            "deck_p1": args.deck_p1, "deck_p2": args.deck_p2,
            "winner": _HARNESS.winner, "loser": _HARNESS.loser,
            "turns": _HARNESS.turns_played, "error": _HARNESS.error,
            "port": args.port,
        }
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2))
        print(f"WROTE: {args.json_out}", flush=True)

    # Linger 30s so any in-flight agent requests resolve, then exit.
    time.sleep(5)
    server.should_exit = True
    sys.exit(0 if _HARNESS.error is None else 1)


if __name__ == "__main__":
    main()
