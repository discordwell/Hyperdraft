"""
Depths-engine tournament adapter for the /new-set balance loop.

Round-robins AI-vs-AI games across a list of deck labels (each label maps
to a builder in `src.cards.depths.submarine_fleet.decks.SUBS_STARTER_DECKS`)
and emits the canonical
`{set_summary, matchup, card_scores}` shape that
`scripts/new_set/balance_loop.py` and `scripts/new_set/coverage.py`
consume.

Card-ref keys are `<DECK_LABEL>::<Card Name>` (no engine-side domain
lookup; the deck label IS the domain — `domain_matches_set("SUBS",
"SUBS_wolfpack")` already returns True via the prefix match in
`coverage.domain_matches_set`).

CLI:
    python -m scripts.new_set._adapters.depths_tournament_adapter \\
        --decks SUBS_wolfpack,SUBS_silent_hunter,SUBS_carrier,SUBS_deep_strike \\
        --games 5 \\
        --max-turns 60 \\
        --out logs/balance_subs_round_1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                  # noqa: E402
    CardDefinition, Event, EventType, ZoneType,
)
from src.engine.game import Game                                # noqa: E402
from src.engine.depths import (                                 # noqa: E402
    get_flagship,
)
from src.engine.depths_turn import DepthsTurnManager            # noqa: E402
from src.ai.depths_adapter import DepthsAIAdapter               # noqa: E402

from src.cards.depths.submarine_fleet.decks import (            # noqa: E402
    SUBS_STARTER_DECKS, make_subs_flagship,
)


# =============================================================================
# Decision tracker (reused / inlined from tests/test_depths_smoke.py)
# =============================================================================
# Agent 4 (AI adapter) returns dataclass instances; Agent 3 (turn manager)
# expects dicts with `action_type` key. Convert at the boundary or every
# AI action becomes a silent no-op and the game stalls until max_turns.
_AI_DATACLASS_TO_DICT = {
    "DeployVessel":     ("DEPTHS_DEPLOY_VESSEL",   ("card_id",)),
    "Dive":             ("DEPTHS_DIVE",            ("vessel_id",)),
    "SurfaceVessel":    ("DEPTHS_SURFACE_VESSEL",  ("vessel_id",)),
    "LayMine":          ("DEPTHS_LAY_MINE",        ("card_id", "depth_band")),
    "AttachCrew":       ("DEPTHS_ATTACH",          ("crew_id", "vessel_id")),
    "AttachWeapon":     ("DEPTHS_ATTACH",          ("weapon_id", "vessel_id")),
    "CastAction":       ("DEPTHS_CAST_SPELL",      ("card_id", "target")),
    "ActivateAbility":  ("DEPTHS_ACTIVATE_ABILITY", ("vessel_id", "ability_idx", "target")),
}


def _is_done(action) -> bool:
    if action is None:
        return True
    if isinstance(action, dict):
        at = action.get("action_type", "")
        return at.endswith("_END_MANEUVER") or at.endswith("_END_REGROUP")
    return type(action).__name__ in ("Done", "NoOp")


def _action_to_dict(action, end_action_type: str = "DEPTHS_END_MANEUVER"):
    if action is None:
        return None
    if isinstance(action, dict):
        return action
    cls_name = type(action).__name__
    if cls_name == "Done":
        return {"action_type": end_action_type}
    spec = _AI_DATACLASS_TO_DICT.get(cls_name)
    if not spec:
        return {"action_type": end_action_type}
    action_type, fields = spec
    out: dict[str, Any] = {"action_type": action_type}
    for field in fields:
        if hasattr(action, field):
            out[field] = getattr(action, field)
    if cls_name in ("AttachCrew", "AttachWeapon"):
        out["card_id"] = out.pop(
            "crew_id" if cls_name == "AttachCrew" else "weapon_id"
        )
        out["target_id"] = out.pop("vessel_id")
    return out


class DecisionTracker:
    """Wraps a DepthsAIAdapter and converts dataclass actions → dict at the
    boundary. Also records whether the AI ever made a non-no-op decision so
    the runner can detect stuck games."""

    def __init__(self, inner: DepthsAIAdapter, label: str):
        self.inner = inner
        self.label = label
        self.actions_taken = 0
        self.attacks_declared = 0
        self.detections_made = 0
        self.intercepts_made = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def choose_maneuver_action(self, state, player_id):
        action = self.inner.choose_maneuver_action(state, player_id)
        if action is not None and not _is_done(action):
            self.actions_taken += 1
        return _action_to_dict(action, "DEPTHS_END_MANEUVER")

    async def choose_regroup_action(self, state, player_id):
        action = self.inner.choose_maneuver_action(state, player_id)
        if action is not None and not _is_done(action):
            self.actions_taken += 1
        return _action_to_dict(action, "DEPTHS_END_REGROUP")

    def choose_attackers(self, state, player_id):
        attackers = self.inner.choose_attackers(state, player_id)
        if attackers:
            self.attacks_declared += len(attackers)
        return attackers

    def choose_detections(self, state, defender_id, attackers):
        detections = self.inner.choose_detections(state, defender_id, attackers)
        if detections:
            spent = (
                sum(detections.values()) if isinstance(detections, dict)
                else len(detections)
            )
            if spent > 0:
                self.detections_made += 1
        return detections

    def choose_interceptors(self, state, defender_id, detected_attackers):
        ints = self.inner.choose_interceptors(state, defender_id, detected_attackers)
        if ints:
            self.intercepts_made += len(ints)
        return ints

    async def choose_discards(self, state, player_id, count):
        if hasattr(self.inner, "choose_discards"):
            r = self.inner.choose_discards(state, player_id, count)
            if asyncio.iscoroutine(r):
                r = await r
            return r
        hand = state.zones.get(f"hand_{player_id}")
        if not hand:
            return []
        return list(hand.objects)[:count]

    def mulligan_decision(self, state, player_id, hand=None):
        if hasattr(self.inner, "mulligan_decision"):
            return self.inner.mulligan_decision(state, player_id, hand)
        return True

    @property
    def made_any_decision(self) -> bool:
        return (self.actions_taken
                + self.attacks_declared
                + self.detections_made
                + self.intercepts_made) > 0


# =============================================================================
# Per-card stat collection
# =============================================================================

def _card_ref(label: str, card_def: CardDefinition) -> str:
    """Canonical key the balance loop / coverage tools consume."""
    return f"{label}::{card_def.name}"


def _zone_type(state, value: Any) -> ZoneType | None:
    if isinstance(value, ZoneType):
        return value
    if isinstance(value, str):
        zone = state.zones.get(value)
        if zone:
            return zone.type
        try:
            return ZoneType[value.upper()]
        except Exception:
            return None
    return None


def _collect_card_stats(
    game: Game,
    p1_id: str,
    p2_id: str,
    p1_label: str,
    p2_label: str,
    deck1: list[CardDefinition],
    deck2: list[CardDefinition],
    winner_id: str | None,
) -> dict[str, dict[str, float]]:
    """Walk event log + final battlefield to compute per-card stats keyed
    `<DECK_LABEL>::<Card Name>`.

    Mirrors the four fields that `balance_loop.py` and `coverage.py` consume:
      - deck_copies        (seeded from the deck list)
      - cast               (HAND→BATTLEFIELD or HAND→STACK ZONE_CHANGEs)
      - in_play_at_end     (final battlefield scan)
      - on_winning_side    (in_play_at_end where owner == winner)

    Plus a few advisory counters (drawn, dmg_dealt, deaths, triggers_fired,
    in_*_at_end) so the JSON closely tracks the upstream
    `custom_set_tournament` shape — `aggregate()` in balance_loop relies on
    `cast`, `deck_copies`, `in_play_at_end`, `on_winning_side` for its
    derived metrics, and the rest is useful debug data.
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
    cast_seen: set[str] = set()
    drawn_seen: set[str] = set()
    death_seen: set[str] = set()

    def _label_for(owner_id: str | None) -> str | None:
        if owner_id == p1_id:
            return p1_label
        if owner_id == p2_id:
            return p2_label
        return None

    def _ref_for(obj_id: str | None) -> str | None:
        if not obj_id:
            return None
        obj = state.objects.get(obj_id)
        if not obj:
            return None
        cd = getattr(obj, "card_def", None)
        if not cd:
            return None
        label = _label_for(obj.owner)
        if label is None:
            return None
        return _card_ref(label, cd)

    # 1. Seed deck_copies from the deck lists.
    for cd in deck1:
        stats[_card_ref(p1_label, cd)]["deck_copies"] += 1
    for cd in deck2:
        stats[_card_ref(p2_label, cd)]["deck_copies"] += 1

    # 2. Walk the event log.
    for ev in list(getattr(state, "event_log", []) or []):
        et = getattr(ev, "type", None)
        payload = getattr(ev, "payload", {}) or {}
        source_id = getattr(ev, "source", None) or payload.get("source")

        if et == EventType.ZONE_CHANGE:
            obj_id = payload.get("object_id") or payload.get("card_id")
            from_zone = (_zone_type(state, payload.get("from_zone_type"))
                         or _zone_type(state, payload.get("from_zone")))
            to_zone = (_zone_type(state, payload.get("to_zone_type"))
                       or _zone_type(state, payload.get("to_zone")))
            ref = _ref_for(obj_id)
            if not ref:
                continue
            # Library → Hand: drawn
            if from_zone == ZoneType.LIBRARY and to_zone == ZoneType.HAND:
                if obj_id and obj_id not in drawn_seen:
                    drawn_seen.add(obj_id)
                    stats[ref]["drawn"] += 1
            # Hand → Battlefield (deploy_vessel / direct play): cast
            # Hand → Stack (cast_spell on instants/actions): cast
            if from_zone == ZoneType.HAND and to_zone in (
                ZoneType.BATTLEFIELD, ZoneType.STACK
            ):
                if obj_id and obj_id not in cast_seen:
                    cast_seen.add(obj_id)
                    stats[ref]["cast"] += 1
            # Battlefield → Graveyard: death
            if from_zone == ZoneType.BATTLEFIELD and to_zone == ZoneType.GRAVEYARD:
                if obj_id and obj_id not in death_seen:
                    death_seen.add(obj_id)
                    stats[ref]["deaths"] += 1

        elif et == EventType.SPELL_CAST:
            # Some Depths code paths (cast_spell) emit SPELL_CAST directly
            # alongside the ZONE_CHANGE; dedupe via cast_seen.
            obj_id = payload.get("object_id") or payload.get("card_id") or source_id
            ref = _ref_for(obj_id)
            if ref and obj_id and obj_id not in cast_seen:
                cast_seen.add(obj_id)
                stats[ref]["cast"] += 1

        elif et == EventType.DAMAGE:
            ref = _ref_for(source_id)
            if ref:
                amount = payload.get("amount", 0) or 0
                stats[ref]["dmg_dealt"] += float(amount)

        elif et == EventType.OBJECT_DESTROYED:
            target_id = payload.get("object_id") or payload.get("target")
            ref_t = _ref_for(target_id)
            if ref_t and target_id and target_id not in death_seen:
                death_seen.add(target_id)
                stats[ref_t]["deaths"] += 1
            ref_s = _ref_for(source_id)
            if ref_s and ref_s != ref_t:
                stats[ref_s]["kills"] += 1

        elif et == EventType.ENTER_BATTLEFIELD:
            obj_id = payload.get("object_id") or payload.get("card_id")
            ref = _ref_for(obj_id)
            if ref:
                stats[ref]["triggers_fired"] += 1

    # 3. Final battlefield + on-winning-side scan.
    for obj_id, obj in state.objects.items():
        if not obj or not getattr(obj, "card_def", None):
            continue
        if getattr(obj, "is_token", False):
            continue
        label = _label_for(obj.owner)
        if label is None:
            continue
        ref = _card_ref(label, obj.card_def)
        if obj.zone == ZoneType.BATTLEFIELD:
            stats[ref]["in_play_at_end"] += 1
            if winner_id and obj.owner == winner_id:
                stats[ref]["on_winning_side"] += 1

    return dict(stats)


# =============================================================================
# One AI-vs-AI game
# =============================================================================

async def _run_one_game(
    label_a: str,
    label_b: str,
    deck_a: list[CardDefinition],
    deck_b: list[CardDefinition],
    max_turns: int,
) -> dict[str, Any]:
    """Run a single Depths AI-vs-AI match. Returns a result dict."""
    started = time.perf_counter()
    game = Game(mode="depths")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    flagship_def = make_subs_flagship()

    tm = DepthsTurnManager(game.state)
    game.turn_manager = tm

    p1_ai = DecisionTracker(DepthsAIAdapter(difficulty="medium"), label_a)
    p2_ai = DecisionTracker(DepthsAIAdapter(difficulty="medium"), label_b)

    tm.set_ai_handler(p1_ai, player_id=p1.id)
    tm.set_ai_handler(p2_ai, player_id=p2.id)
    if hasattr(tm, "set_ai_player"):
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)

    error: str | None = None
    turns_run = 0
    try:
        await tm.setup_game(game, deck_a, deck_b, flagship_def, flagship_def)
        # Smoke test asserts both flagships exist. Do the same — if not, the
        # game is unrunnable.
        if get_flagship(p1.id, game.state) is None:
            raise RuntimeError("P1 flagship missing after setup")
        if get_flagship(p2.id, game.state) is None:
            raise RuntimeError("P2 flagship missing after setup")

        for _ in range(max_turns):
            if game.is_game_over():
                break
            active_id = p1.id if turns_run % 2 == 0 else p2.id
            await tm.run_turn(active_id)
            turns_run += 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1200:]}"

    completed = False
    winner_id: str | None = None
    winner_label: str | None = None
    try:
        completed = game.is_game_over()
        if completed:
            winner_id = game.get_winner()
            if winner_id == p1.id:
                winner_label = label_a
            elif winner_id == p2.id:
                winner_label = label_b
    except Exception:
        pass

    card_stats: dict[str, dict[str, float]] = {}
    if error is None:
        try:
            card_stats = _collect_card_stats(
                game, p1.id, p2.id, label_a, label_b,
                deck_a, deck_b, winner_id,
            )
        except Exception as exc:
            # Don't lose the game just because stats blew up.
            error = (error or "") + (
                f"; card_stats failed: {type(exc).__name__}: {exc}"
            )

    return {
        "p1_label": label_a,
        "p2_label": label_b,
        "winner_label": winner_label,
        "winner_id": winner_id,
        "completed": completed,
        "turns": turns_run,
        "p1_made_decision": p1_ai.made_any_decision,
        "p2_made_decision": p2_ai.made_any_decision,
        "p1_actions": p1_ai.actions_taken,
        "p2_actions": p2_ai.actions_taken,
        "p1_attacks": p1_ai.attacks_declared,
        "p2_attacks": p2_ai.attacks_declared,
        "duration_s": round(time.perf_counter() - started, 3),
        "error": error,
        "card_stats": card_stats,
    }


# =============================================================================
# Tournament aggregation → canonical {set_summary, matchup, card_scores}
# =============================================================================

def _aggregate(
    deck_labels: list[str],
    raw_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Mirror `scripts/play/custom_set_tournament.py::aggregate` shape."""
    set_record: dict[str, dict[str, int]] = {
        d: {"wins": 0, "losses": 0, "draws": 0, "errors": 0}
        for d in deck_labels
    }
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
        a, b = r["p1_label"], r["p2_label"]
        if a not in set_record:
            set_record[a] = {"wins": 0, "losses": 0, "draws": 0, "errors": 0}
        if b not in set_record:
            set_record[b] = {"wins": 0, "losses": 0, "draws": 0, "errors": 0}

        if r.get("error"):
            set_record[a]["errors"] += 1
            set_record[b]["errors"] += 1
            continue

        ka, kb = sorted([a, b])
        m = matchup[(ka, kb)]
        winner = r.get("winner_label")
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
        elif winner == b:
            set_record[b]["wins"] += 1
            set_record[a]["losses"] += 1
            if b == ka:
                m["wins_a"] += 1
            else:
                m["wins_b"] += 1
        else:
            # Defensive: unknown winner label → draw.
            m["draws"] += 1
            set_record[a]["draws"] += 1
            set_record[b]["draws"] += 1

        # Per-card stats accumulate across games this card appeared in.
        for ref, cs in (r.get("card_stats") or {}).items():
            agg = card_agg[ref]
            agg["games"] += 1
            for k, v in cs.items():
                if k in agg:
                    agg[k] += v

    # Per-deck winrate.
    set_summary: dict[str, dict[str, Any]] = {}
    for d in deck_labels:
        rec = set_record[d]
        gp = rec["wins"] + rec["losses"] + rec["draws"]
        wr = (rec["wins"] / gp) if gp else 0.0
        set_summary[d] = {**rec, "games_played": gp, "winrate": round(wr, 3)}

    # Per-card derived metrics.
    card_scores: dict[str, dict[str, float]] = {}
    for ref, agg in card_agg.items():
        games = max(int(agg["games"]), 1)
        cast_per_game = agg["cast"] / games
        copies_per_game = agg["deck_copies"] / games
        cast_per_copy = (
            (agg["cast"] / agg["deck_copies"]) if agg["deck_copies"] else 0.0
        )
        win_rate_in_play = (
            (agg["on_winning_side"] / agg["in_play_at_end"])
            if agg["in_play_at_end"] > 0 else 0.0
        )
        card_scores[ref] = {
            **agg,
            "cast_per_game": round(cast_per_game, 3),
            "copies_per_game": round(copies_per_game, 3),
            "cast_per_copy": round(cast_per_copy, 3),
            "win_rate_in_play": round(win_rate_in_play, 3),
        }

    return {
        "set_summary": set_summary,
        "matchup": {f"{a} vs {b}": v for (a, b), v in matchup.items()},
        "card_scores": card_scores,
    }


# =============================================================================
# Public API: run the round-robin
# =============================================================================

async def run_depths_tournament(
    deck_labels: list[str],
    games_per_pairing: int = 5,
    max_turns: int = 60,
) -> dict[str, Any]:
    """Round-robin AI-vs-AI tournament for the depths engine.

    For each unordered pair (A, B) in `deck_labels`, runs `games_per_pairing`
    games and produces a JSON dict with the canonical shape:
      {
        "set_summary": {<deck_label>: {wins, losses, draws, errors,
                                       games_played, winrate}, ...},
        "matchup":     {"A vs B": {wins_a, wins_b, draws}, ...},
        "card_scores": {"<deck_label>::<card name>": {...}, ...},
      }
    """
    # Validate deck builders up front so a typo doesn't waste a partial round.
    builders: dict[str, Any] = {}
    for label in deck_labels:
        builder = SUBS_STARTER_DECKS.get(label)
        if builder is None:
            raise KeyError(
                f"unknown deck label {label!r}; "
                f"known labels: {sorted(SUBS_STARTER_DECKS)}"
            )
        builders[label] = builder

    started = time.perf_counter()
    raw_results: list[dict[str, Any]] = []
    pairings = list(combinations(deck_labels, 2))

    print(f"[depths-tournament] {len(deck_labels)} decks, "
          f"{len(pairings)} pairings × {games_per_pairing} games "
          f"= {len(pairings) * games_per_pairing} games total")

    for label_a, label_b in pairings:
        wins_a = wins_b = draws = errors = 0
        pair_started = time.perf_counter()
        for game_idx in range(games_per_pairing):
            # Fresh deck list per game (builders return fresh CardDefinition
            # references — though card_def itself is shared, the *list*
            # belongs to this game).
            deck_a = builders[label_a]()
            deck_b = builders[label_b]()
            result = await _run_one_game(
                label_a, label_b, deck_a, deck_b, max_turns,
            )
            raw_results.append(result)
            if result.get("error"):
                errors += 1
            elif result.get("winner_label") == label_a:
                wins_a += 1
            elif result.get("winner_label") == label_b:
                wins_b += 1
            else:
                draws += 1
        pair_elapsed = time.perf_counter() - pair_started
        print(f"  {label_a:>22s} vs {label_b:<22s}  "
              f"a={wins_a} b={wins_b} draw={draws} err={errors}  "
              f"({pair_elapsed:.1f}s)")

    aggregated = _aggregate(deck_labels, raw_results)

    # Top-level metadata for traceability.
    aggregated["meta"] = {
        "engine": "depths",
        "deck_labels": list(deck_labels),
        "games_per_pairing": games_per_pairing,
        "max_turns": max_turns,
        "pairings": len(pairings),
        "total_games": len(raw_results),
        "errored_games": sum(1 for r in raw_results if r.get("error")),
        "completed_games": sum(1 for r in raw_results if r.get("completed")),
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    aggregated["raw_results"] = [
        # Drop card_stats from raw to keep the JSON tractable (it's
        # already aggregated into card_scores).
        {k: v for k, v in r.items() if k != "card_stats"}
        for r in raw_results
    ]
    return aggregated


# =============================================================================
# CLI
# =============================================================================

def _parse_decks(s: str) -> list[str]:
    return [tok.strip() for tok in s.split(",") if tok.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--decks", required=True,
        help="Comma-separated deck labels "
             "(e.g. SUBS_wolfpack,SUBS_silent_hunter,...).",
    )
    ap.add_argument("--games", type=int, default=5,
                    help="Games per unordered pairing (default 5).")
    ap.add_argument("--max-turns", type=int, default=60,
                    help="Hard cap on turns per game.")
    ap.add_argument("--out", type=Path, required=True,
                    help="Write tournament JSON here.")
    args = ap.parse_args()

    deck_labels = _parse_decks(args.decks)
    if not deck_labels:
        print("ERROR: --decks is empty", file=sys.stderr)
        return 2

    payload = asyncio.run(run_depths_tournament(
        deck_labels,
        games_per_pairing=args.games,
        max_turns=args.max_turns,
    ))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    print(f"wrote {args.out}")
    print(f"set_summary: {json.dumps(payload['set_summary'], indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
