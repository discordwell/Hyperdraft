"""
Smoke test for the depths engine — Stage 1 deliverable.

Asserts:
  1. AI-vs-AI game completes within 60 turns (no infinite loop / crash)
  2. Both AIs make at least one non-no-op decision
  3. Some win condition fires (it doesn't end in a 60-turn timeout
     with no winner)

Uses a minimal 8-vessel placeholder card pool — no real card set is
required. Stage 4 of the /new-game pipeline will produce the actual
first-set cards.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                  # noqa: E402
    CardDefinition, Characteristics, CardType, ZoneType,
)
from src.engine.game import Game                                # noqa: E402
from src.engine.depths import (                                 # noqa: E402
    DepthBand, FLAGSHIP_HULL,
    setup_depths_player, get_flagship, is_vessel,
)
from src.engine.depths_turn import DepthsTurnManager            # noqa: E402
from src.ai.depths_adapter import DepthsAIAdapter               # noqa: E402


MAX_TURNS = 60


# =============================================================================
# Minimal placeholder card pool
# =============================================================================

def _make_flagship_def(name: str = "Test Flagship") -> CardDefinition:
    """A Flagship — DEPTHS_VESSEL with hull=25, locked at PERISCOPE."""
    chars = Characteristics(
        types={CardType.DEPTHS_VESSEL},
        subtypes={"Flagship"},
        power=0,
        toughness=FLAGSHIP_HULL,
    )
    cd = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        text="Flagship. Cannot dive. If sunk, you lose.",
    )
    cd.depths_flagship = True
    cd.depths_starting_depth = DepthBand.PERISCOPE
    return cd


def _make_vessel(name: str, *, power: int, hull: int, cost: str = "{1T}") -> CardDefinition:
    """A vanilla Vessel — DEPTHS_VESSEL, cheap, no special rules."""
    chars = Characteristics(
        types={CardType.DEPTHS_VESSEL},
        subtypes={"Submarine"},
        power=power,
        toughness=hull,
    )
    cd = CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text="Vanilla submarine.",
    )
    return cd


def _build_test_deck(label: str, size: int = 30) -> list[CardDefinition]:
    """A 30-card deck of cheap vanilla Vessels for both sides."""
    pool = [
        _make_vessel(f"{label} Coastal Sub",  power=2, hull=2, cost="{1T}"),
        _make_vessel(f"{label} Patrol Boat",  power=1, hull=3, cost="{1T}"),
        _make_vessel(f"{label} Hunter-Killer", power=3, hull=2, cost="{2T}"),
        _make_vessel(f"{label} Type-VII",     power=3, hull=3, cost="{3T}"),
        _make_vessel(f"{label} Destroyer",    power=4, hull=4, cost="{4T}"),
        _make_vessel(f"{label} Submersible",  power=2, hull=4, cost="{2T}"),
    ]
    deck: list[CardDefinition] = []
    i = 0
    while len(deck) < size:
        deck.append(pool[i % len(pool)])
        i += 1
    return deck


# =============================================================================
# Decision tracker
# =============================================================================

class DecisionTracker:
    """Wraps a DepthsAIAdapter to record whether it ever made a non-no-op
    decision (i.e. anything other than ``Done``/empty list/0 spend)."""

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
            spent = sum(detections.values()) if isinstance(detections, dict) else len(detections)
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
        # Default: discard the first `count` cards in hand
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


def _is_done(action) -> bool:
    """Heuristic: action is a no-op / 'done with phase' signal."""
    if action is None:
        return True
    if isinstance(action, dict):
        return action.get("action_type", "").endswith("_END_MANEUVER") or \
               action.get("action_type", "").endswith("_END_REGROUP")
    cls_name = type(action).__name__
    return cls_name in ("Done", "NoOp")


# Agent 4 (AI adapter) returns dataclass instances; Agent 3 (turn manager)
# expects dicts with `action_type` key. Convert at the boundary.
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


def _action_to_dict(action, end_action_type: str = "DEPTHS_END_MANEUVER"):
    """Convert AI's dataclass action → turn-manager's dict format."""
    if action is None:
        return None
    if isinstance(action, dict):
        return action
    cls_name = type(action).__name__
    if cls_name == "Done":
        return {"action_type": end_action_type}
    spec = _AI_DATACLASS_TO_DICT.get(cls_name)
    if not spec:
        # Unknown action — treat as Done so the loop terminates rather than crash
        return {"action_type": end_action_type}
    action_type, fields = spec
    out = {"action_type": action_type}
    for field in fields:
        if hasattr(action, field):
            out[field] = getattr(action, field)
    # Some dict consumers prefer "card_id" / "target_id" semantics for attach
    if cls_name in ("AttachCrew", "AttachWeapon"):
        out["card_id"] = out.pop("crew_id" if cls_name == "AttachCrew" else "weapon_id")
        out["target_id"] = out.pop("vessel_id")
    return out


# =============================================================================
# The smoke test
# =============================================================================

async def _run_one_game() -> dict:
    """Run a single AI-vs-AI depths game. Return a result dict."""
    game = Game(mode="depths")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    flagship_def = _make_flagship_def()
    deck1 = _build_test_deck("A")
    deck2 = _build_test_deck("B")

    # Use the turn manager as the orchestrator (it calls setup_depths_player)
    tm = DepthsTurnManager(game.state)
    game.turn_manager = tm

    p1_ai = DecisionTracker(DepthsAIAdapter(difficulty="medium"), "P1")
    p2_ai = DecisionTracker(DepthsAIAdapter(difficulty="medium"), "P2")

    # Setup: install per-player AI handlers + register AI players. The
    # turn manager dispatches each AI decision to the handler registered
    # for that player (falling back to the default-registered shared
    # handler if no per-player override is set).
    tm.set_ai_handler(p1_ai, player_id=p1.id)
    tm.set_ai_handler(p2_ai, player_id=p2.id)
    if hasattr(tm, "set_ai_player"):
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)

    await tm.setup_game(game, deck1, deck2, flagship_def, flagship_def)

    # Verify both flagships exist
    fs1 = get_flagship(p1.id, game.state)
    fs2 = get_flagship(p2.id, game.state)
    assert fs1 is not None, "P1 flagship missing after setup"
    assert fs2 is not None, "P2 flagship missing after setup"

    # Run turns until game over or MAX_TURNS
    turns_run = 0
    error = None
    try:
        for _ in range(MAX_TURNS):
            if game.is_game_over():
                break
            active_id = p1.id if turns_run % 2 == 0 else p2.id
            await tm.run_turn(active_id)
            turns_run += 1
    except Exception as exc:
        import traceback
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}"

    p1_decisions = p1_ai.made_any_decision
    p2_decisions = p2_ai.made_any_decision
    game_over = game.is_game_over()
    return {
        "turns": turns_run,
        "completed": game_over,
        "p1_made_decision": p1_decisions,
        "p2_made_decision": p2_decisions,
        "error": error,
        "p1_actions": p1_ai.actions_taken,
        "p2_actions": p2_ai.actions_taken,
        "p1_attacks": p1_ai.attacks_declared,
        "p2_attacks": p2_ai.attacks_declared,
    }


def test_depths_ai_vs_ai_completes():
    result = asyncio.run(_run_one_game())
    print(f"\n=== depths smoke result ===")
    for k, v in result.items():
        if k != "error":
            print(f"  {k}: {v}")
    if result["error"]:
        print(f"  error: {result['error']}")

    assert result["error"] is None, f"Game crashed: {result['error']}"
    assert result["turns"] <= MAX_TURNS, \
        f"Game exceeded {MAX_TURNS} turns ({result['turns']})"
    assert result["completed"], \
        f"Game did not finish within {MAX_TURNS} turns (no win condition fired)"


def test_depths_ai_makes_decisions():
    """Both AIs must make at least one non-no-op decision in a game."""
    result = asyncio.run(_run_one_game())
    assert result["error"] is None, f"Game crashed: {result['error']}"
    assert result["p1_made_decision"], (
        f"P1 made zero non-no-op decisions in {result['turns']} turns "
        f"(actions={result['p1_actions']} attacks={result['p1_attacks']})"
    )
    assert result["p2_made_decision"], (
        f"P2 made zero non-no-op decisions in {result['turns']} turns "
        f"(actions={result['p2_actions']} attacks={result['p2_attacks']})"
    )


if __name__ == "__main__":
    print("=" * 60)
    print("DEPTHS ENGINE SMOKE TEST")
    print("=" * 60)
    test_depths_ai_vs_ai_completes()
    test_depths_ai_makes_decisions()
    print("\nOK — all depths smoke tests passed.")
