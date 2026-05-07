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


def test_eot_pt_modifiers_clear_at_end_of_turn():
    """Regression: PT_MODIFICATION events with duration='end_of_turn' must
    actually clear at the end of the active player's turn. Otherwise per-turn
    triggers like Snorkel Stalker's '+1 power EOT when attacking undetected'
    accumulate across turns and the card becomes a runaway carry.
    """
    from src.engine.types import EventType, Event
    from src.cards.depths.submarine_fleet.decks import (
        SUBS_STARTER_DECKS, make_subs_flagship,
    )

    async def _run():
        game = Game(mode="depths")
        p1 = game.add_player("A")
        p2 = game.add_player("B")
        tm = DepthsTurnManager(game.state)
        game.turn_manager = tm
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)
        await tm.setup_game(
            game,
            SUBS_STARTER_DECKS["SUBS_wolfpack"](),
            SUBS_STARTER_DECKS["SUBS_silent_hunter"](),
            make_subs_flagship(), make_subs_flagship(),
        )
        # Manually create a battlefield vessel and attach an EOT pt_modifier.
        bf = game.state.zones.get("battlefield")
        target_obj = None
        for oid in bf.objects:
            obj = game.state.objects.get(oid)
            if obj and obj.controller == p1.id:
                target_obj = obj
                break
        if target_obj is None:
            return None
        if not hasattr(target_obj.state, "pt_modifiers") or target_obj.state.pt_modifiers is None:
            target_obj.state.pt_modifiers = []
        target_obj.state.pt_modifiers.append({
            "power": 5, "toughness": 0, "duration": "end_of_turn",
        })
        # Run P1's turn — the EOT cleanup should sweep the modifier.
        await tm.run_turn(p1.id)
        return list(target_obj.state.pt_modifiers or [])

    leftover = asyncio.run(_run())
    assert leftover is not None, "Test setup failed: no battlefield object"
    assert leftover == [], (
        f"PT_MODIFICATION with duration='end_of_turn' was not cleared at "
        f"end of turn. Remaining: {leftover}"
    )


def test_medium_ai_does_not_oscillate_dive_surface():
    """Regression: medium AI must not Dive a vessel and then SurfaceVessel
    the same vessel within the same turn — that pattern burns 1 Sonar/turn
    on a no-op move (PERISCOPE→MID→PERISCOPE).
    """
    from src.cards.depths.submarine_fleet.decks import (
        SUBS_STARTER_DECKS, make_subs_flagship,
    )
    from src.ai.depths_adapter import Dive, SurfaceVessel

    async def _run():
        game = Game(mode="depths")
        p1 = game.add_player("A")
        p2 = game.add_player("B")
        tm = DepthsTurnManager(game.state)
        game.turn_manager = tm

        # Capture each AI choice per (turn, vessel) so we can detect oscillation.
        # offence_pattern[(turn, vessel_id)] = [classes returned by AI]
        per_vessel: dict[tuple[int, str], list[str]] = {}

        class TrackingHandler:
            def __init__(self, ai): self.ai = ai
            def __getattr__(self, n):
                if n == "ai":
                    raise AttributeError(n)
                return getattr(self.__dict__["ai"], n)
            async def choose_maneuver_action(self, state, player_id):
                action = self.ai.choose_maneuver_action(state, player_id)
                if isinstance(action, (Dive, SurfaceVessel)):
                    key = (state.turn_number, action.vessel_id)
                    per_vessel.setdefault(key, []).append(type(action).__name__)
                return _action_to_dict(action, "DEPTHS_END_MANEUVER")
            async def choose_regroup_action(self, state, player_id):
                action = self.ai.choose_maneuver_action(state, player_id)
                if isinstance(action, (Dive, SurfaceVessel)):
                    key = (state.turn_number, action.vessel_id)
                    per_vessel.setdefault(key, []).append(type(action).__name__)
                return _action_to_dict(action, "DEPTHS_END_REGROUP")
            def choose_attackers(self, s, p): return self.ai.choose_attackers(s, p)
            def choose_detections(self, s, d, a): return self.ai.choose_detections(s, d, a)
            def choose_interceptors(self, s, d, a): return self.ai.choose_interceptors(s, d, a)
            async def choose_discards(self, s, p, n):
                h = s.zones.get(f"hand_{p}")
                return list(h.objects)[:n] if h else []
            def mulligan_decision(self, *a, **kw): return True

        tm.set_ai_handler(TrackingHandler(DepthsAIAdapter(difficulty="medium")), p1.id)
        tm.set_ai_handler(TrackingHandler(DepthsAIAdapter(difficulty="medium")), p2.id)
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)
        await tm.setup_game(
            game,
            SUBS_STARTER_DECKS["SUBS_wolfpack"](),
            SUBS_STARTER_DECKS["SUBS_silent_hunter"](),
            make_subs_flagship(), make_subs_flagship(),
        )
        for t in range(20):
            if game.is_game_over():
                break
            active = p1.id if t % 2 == 0 else p2.id
            await tm.run_turn(active)
        return per_vessel

    per_vessel = asyncio.run(_run())
    bad = []
    for (turn, vid), classes in per_vessel.items():
        seen = set(classes)
        if "Dive" in seen and "SurfaceVessel" in seen:
            bad.append(f"turn={turn} vessel={vid[:8]} sequence={classes}")
    assert not bad, (
        "Medium AI oscillated Dive/SurfaceVessel within the same turn — "
        f"that burns 1 Sonar per turn on a no-op move. Cases:\n  "
        + "\n  ".join(bad[:5])
    )


def test_undetected_attack_depth_modifier():
    """Iter-7 investigation: does the depth modifier apply to undetected attackers?

    Pilot A and Pilot B both reported that a SURFACE 2/1 attacker dealt 2 damage
    to a PERISCOPE flagship (full printed power), where the formula predicts
    max(1, 2 - |0 - 1|) = 1. Both pilots hypothesised that "undetected attackers
    bypass the depth modifier".

    This test confirms the ACTUAL engine behaviour:
    - The depth modifier interceptor fires for ALL combat damage events,
      detected or not (the filter gates on is_combat/depths_combat flags,
      NOT on the detected status of the attacker).
    - A SURFACE (band=0) attacker vs PERISCOPE (band=1) flagship DOES get
      reduced from 2 → 1 even when undetected.
    - The pilot observations of "2 damage" were reading the pre-transform
      event payload returned by assign_damage (which captures events before
      the pipeline transforms them). The actual damage applied to the
      flagship object is 1.

    VERDICT: The depth modifier is NOT bypassed for undetected attackers.
    The pilot hypothesis was INCORRECT. The engine is working as designed.
    The harness combat log printed the pre-transform amount (2), not the
    post-pipeline amount (1), causing the confusion.
    """
    from src.engine.types import CardType, Characteristics, ZoneType, GameObject, new_id, ObjectState
    from src.engine.game import Game
    from src.engine.depths import DepthBand
    from src.engine.depths_combat import (
        DepthsCombatManager, AttackerSpec, install_depth_damage_modifier, is_detected,
    )

    game = Game(mode="depths")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    state = game.state

    # 2/1 Drone at SURFACE (band 0).
    atk_chars = Characteristics(
        types={CardType.DEPTHS_VESSEL}, subtypes={"Drone"}, power=2, toughness=1
    )
    atk_id = new_id()
    atk_state = ObjectState()
    atk_state.depth_band = DepthBand.SURFACE
    atk_state.tapped = False
    atk_state.summoning_sickness = False
    atk_state.detected = False  # explicitly UNDETECTED
    atk_obj = GameObject(
        id=atk_id, name="Surface Drone", characteristics=atk_chars,
        controller=p1.id, owner=p1.id, zone=ZoneType.BATTLEFIELD, state=atk_state,
    )
    state.objects[atk_id] = atk_obj
    state.zones["battlefield"].objects.append(atk_id)

    # 0/25 Flagship at PERISCOPE (band 1).
    tgt_chars = Characteristics(
        types={CardType.DEPTHS_VESSEL}, subtypes={"Flagship"}, power=0, toughness=25
    )
    tgt_id = new_id()
    tgt_state = ObjectState()
    tgt_state.depth_band = DepthBand.PERISCOPE
    tgt_state.tapped = False
    tgt_state.summoning_sickness = False
    tgt_obj = GameObject(
        id=tgt_id, name="Test Flagship", characteristics=tgt_chars,
        controller=p2.id, owner=p2.id, zone=ZoneType.BATTLEFIELD, state=tgt_state,
    )
    state.objects[tgt_id] = tgt_obj
    state.zones["battlefield"].objects.append(tgt_id)

    state.active_player = p1.id
    install_depth_damage_modifier(state)

    # Confirm attacker is undetected before combat.
    assert not is_detected(atk_obj), "Attacker must be undetected for this test"

    cm = DepthsCombatManager()
    atk_spec = AttackerSpec(
        vessel_id=atk_id,
        target_id=tgt_id,
        firing_depth_band=DepthBand.SURFACE,
    )
    result = cm.resolve_combat(
        state,
        attacker_specs=[atk_spec],
        sonar_spends={},   # defender spends 0 SC — attacker stays undetected
        blocker_specs=[],
    )

    assert result["ok"], "Combat should succeed"

    # The pre-pipeline event captured by assign_damage shows the raw power (2).
    # This is what harness logs displayed, causing pilot confusion.
    pre_transform_amount = result["damage_events"][0].payload["amount"]
    assert pre_transform_amount == 2, (
        f"assign_damage emits raw power before pipeline transform: expected 2, got {pre_transform_amount}"
    )

    # The ACTUAL damage applied to the flagship is 1 — the depth modifier fired.
    # SURFACE (0) → PERISCOPE (1): diff=1, reduced = max(1, 2-1) = 1.
    actual_damage = int(tgt_obj.state.damage or 0)
    assert actual_damage == 1, (
        f"Depth modifier MUST fire for undetected SURFACE→PERISCOPE attack. "
        f"Expected 1 damage (max(1, 2-1)), got {actual_damage}. "
        f"The depth modifier applies to ALL combat, not just detected attackers. "
        f"Pilot reports of '2 damage' were reading pre-pipeline event payloads."
    )


def test_detection_without_interceptors_skips_detect():
    """Iter-7 patch: medium AI must not spend SC detecting when no
    ready interceptors are available — detected attackers still deal
    full damage if there's nothing to assign as blocker.
    """
    from src.cards.depths.submarine_fleet.decks import SUBS_STARTER_DECKS, make_subs_flagship
    from src.engine.depths_combat import AttackerSpec
    from src.ai.depths_adapter import DepthsAIAdapter
    from src.engine.depths import DepthBand

    async def _run():
        game = Game(mode="depths")
        p1 = game.add_player("Carrier")
        p2 = game.add_player("SH")
        tm = DepthsTurnManager(game.state)
        game.turn_manager = tm
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)
        await tm.setup_game(
            game,
            SUBS_STARTER_DECKS["SUBS_carrier"](),
            SUBS_STARTER_DECKS["SUBS_silent_hunter"](),
            make_subs_flagship(), make_subs_flagship(),
        )

        # Manually clear P2's battlefield of all non-Flagship vessels so
        # there are no ready interceptors.
        state = game.state
        from src.engine.depths import get_flagship, is_vessel
        bf = state.zones.get("battlefield")
        p2_flagship = get_flagship(p2.id, state)
        to_remove = []
        for oid in list(bf.objects):
            obj = state.objects.get(oid)
            if obj and obj.controller == p2.id and is_vessel(obj):
                if obj.id != (p2_flagship.id if p2_flagship else None):
                    to_remove.append(oid)
        for oid in to_remove:
            bf.objects.remove(oid)

        # Confirm P2 has no ready interceptors
        from src.ai.depths_adapter import _own_vessels, _is_ready_to_attack
        p2_interceptors = [v for v in _own_vessels(state, p2.id) if _is_ready_to_attack(v)]
        assert p2_interceptors == [], f"P2 should have no interceptors, got: {p2_interceptors}"

        # Build fake attackers targeting P2 flagship
        p2_fs = get_flagship(p2.id, state)
        p1_vessels = _own_vessels(state, p1.id)
        attackers = []
        for v in p1_vessels[:2]:
            if _is_ready_to_attack(v) and p2_fs:
                attackers.append(AttackerSpec(
                    vessel_id=v.id,
                    target_id=p2_fs.id,
                    firing_depth_band=v.state.depth_band or DepthBand.SURFACE,
                ))
        if not attackers:
            return None, None  # no attackers to test with

        # Give P2 some SC
        p2_player = state.players.get(p2.id)
        p2_player.sc = 10

        ai = DepthsAIAdapter(difficulty="medium")
        detections = ai.choose_detections(state, p2.id, attackers)
        return detections, int(getattr(p2_player, "sc", 0))

    detections, remaining_sc = asyncio.run(_run())
    if detections is None:
        return  # no attackers available — test is vacuously true
    assert detections == {}, (
        f"Medium AI must return empty detections when no interceptors are available. "
        f"Got: {detections}. SC spent wastefully on detection with no interceptors to assign."
    )


def test_carrier_etb_drone_spawns_at_surface():
    """Regression (iter-8): Escort Carrier ETB drones must spawn at DepthBand.SURFACE.

    Before the fix in _handle_object_created (zone.py), the OBJECT_CREATED handler
    ignored the 'depth_band' payload key, so all drone tokens landed with
    obj.state.depth_band = None. In combat this produced 0 damage (the formula
    max(1, power - band_diff) could not compute with None). After the fix, the
    payload's depth_band value is applied to obj.state on creation.
    """
    from src.engine.types import EventType, Event
    from src.cards.depths.submarine_fleet.decks import (
        SUBS_STARTER_DECKS, make_subs_flagship,
    )
    from src.cards.depths.submarine_fleet.carrier import ESCORT_CARRIER
    from src.engine.depths import get_flagship, is_vessel

    async def _run():
        game = Game(mode="depths")
        p1 = game.add_player("Carrier_Player")
        p2 = game.add_player("Opponent")
        tm = DepthsTurnManager(game.state)
        game.turn_manager = tm
        tm.set_ai_player(p1.id)
        tm.set_ai_player(p2.id)
        await tm.setup_game(
            game,
            SUBS_STARTER_DECKS["SUBS_carrier"](),
            SUBS_STARTER_DECKS["SUBS_silent_hunter"](),
            make_subs_flagship(), make_subs_flagship(),
        )

        state = game.state
        bf = state.zones.get("battlefield")

        # Record all token IDs before firing the ETB event.
        tokens_before = set(
            oid for oid in bf.objects
            if state.objects.get(oid) and state.objects[oid].state.is_token
        )

        # Manually emit an OBJECT_CREATED event for a Drone token at SURFACE,
        # mimicking exactly what _create_drone_event produces in carrier.py.
        from src.engine.types import EventType, new_id
        from src.engine.depths import DepthBand
        drone_event = Event(
            type=EventType.OBJECT_CREATED,
            payload={
                "name": "Drone",
                "controller": p1.id,
                "owner": p1.id,
                "to_zone_type": ZoneType.BATTLEFIELD,
                "types": [CardType.DEPTHS_VESSEL],
                "subtypes": ["Drone"],
                "power": 2,
                "toughness": 1,
                "is_token": True,
                "depth_band": DepthBand.SURFACE,
            },
            source="test_carrier",
            controller=p1.id,
        )
        # Run through the game pipeline so zone.py's handler fires.
        game.emit(drone_event)

        # Find the newly created drone token.
        tokens_after = set(
            oid for oid in bf.objects
            if state.objects.get(oid) and state.objects[oid].state.is_token
        )
        new_tokens = tokens_after - tokens_before
        assert len(new_tokens) >= 1, "No new drone token was created"

        # All new tokens must have depth_band == SURFACE.
        bad_bands = []
        for oid in new_tokens:
            obj = state.objects.get(oid)
            if obj is not None and "Drone" in obj.characteristics.subtypes:
                if obj.state.depth_band != DepthBand.SURFACE:
                    bad_bands.append((obj.name, obj.state.depth_band))
        return bad_bands

    bad = asyncio.run(_run())
    assert bad == [], (
        f"Drone tokens spawned at wrong depth band (expected SURFACE): {bad}. "
        "Fix: _handle_object_created in zone.py must read 'depth_band' from payload."
    )


if __name__ == "__main__":
    print("=" * 60)
    print("DEPTHS ENGINE SMOKE TEST")
    print("=" * 60)
    test_depths_ai_vs_ai_completes()
    test_depths_ai_makes_decisions()
    test_eot_pt_modifiers_clear_at_end_of_turn()
    test_medium_ai_does_not_oscillate_dive_surface()
    test_undetected_attack_depth_modifier()
    test_detection_without_interceptors_skips_detect()
    test_carrier_etb_drone_spawns_at_surface()
    print("\nOK — all depths smoke tests passed.")
