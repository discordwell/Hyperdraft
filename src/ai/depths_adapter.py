"""
Depths AI Adapter — DepthsAIAdapter

Heuristic AI for the submarine-fleet engine. Three difficulty tiers
(``easy`` / ``medium`` / ``hard``) share a single legal-move generator
and differ only in selection policy. See ``docs/games/depths.md`` §8 for
the design statement.

The adapter is intentionally **stateless** between calls — every method
reads the current ``GameState`` and returns a fresh decision. The turn
manager (``src/engine/depths_turn.py``) calls one method per phase:

  * ``mulligan_decision(state, player_id, hand) -> bool``
  * ``choose_maneuver_action(state, player_id) -> ManeuverAction``
        (loop until ``Done`` for both Maneuver and Regroup phases)
  * ``choose_attackers(state, player_id) -> list[AttackerSpec]``
  * ``choose_detections(state, defender_id, attackers) -> dict[str,int]``
  * ``choose_interceptors(state, defender_id, detected) -> list[BlockerSpec]``

Imports from sibling depths modules are wrapped in ``try/except`` so
this file remains importable while the other three parallel agents are
still landing their changes — the adapter falls back to inline
definitions where possible. When the real symbols arrive they take
precedence and the inline shims become dead code.

No LLM hooks, no MCTS, no neural eval. Matches the readability of
``src/ai/hearthstone_adapter.py`` and ``src/ai/minecraft_adapter.py``.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from src.engine.types import CardType, GameState, ZoneType

if TYPE_CHECKING:
    from src.engine.types import GameObject, Player


# =============================================================================
# Imports from depths.* sibling modules (with safe fallbacks)
# =============================================================================
#
# The other three Stage-1 agents own ``depths.py``, ``depths_combat.py``,
# and ``depths_turn.py``. We import their canonical helpers if they exist
# and define minimal local stand-ins otherwise so this file is always
# importable. Fallbacks rely only on public ``GameObject.state`` fields
# (``depth_band``, ``detected``) that ``types.py`` already declares, so
# the contract with the rest of the engine is preserved either way.
# =============================================================================

try:  # depths.py — DepthBand enum and convenience queries
    from src.engine.depths import (  # type: ignore[import-not-found]
        DepthBand,
        cap_for_turn,
        is_vessel,
        vessels_at_depth as _depths_vessels_at_depth,
        get_flagship as _depths_get_flagship,
        depth_difference,
    )
    # Adapt depths.py signatures to the AI's (state-first) convention.
    def get_flagship(state: GameState, player_id: str):  # type: ignore[no-redef]
        return _depths_get_flagship(player_id, state)

    def vessels_at_depth(state: GameState, player_id: str, band: 'DepthBand'):  # type: ignore[no-redef]
        return _depths_vessels_at_depth(player_id, band, state)

    _HAS_DEPTHS_MODULE = True
except Exception:  # pragma: no cover — exercised only during parallel scaffold
    _HAS_DEPTHS_MODULE = False

    class DepthBand(Enum):  # type: ignore[no-redef]
        SURFACE = 0
        PERISCOPE = 1
        MID = 2
        DEEP = 3
        CRUSH = 4

    def cap_for_turn(turn: int) -> int:  # type: ignore[no-redef]
        return min(max(int(turn), 1), 10)

    def is_vessel(obj: 'GameObject') -> bool:  # type: ignore[no-redef]
        return obj is not None and CardType.DEPTHS_VESSEL in obj.characteristics.types

    def get_flagship(state: GameState, player_id: str) -> Optional['GameObject']:  # type: ignore[no-redef]
        player = state.players.get(player_id)
        if player and getattr(player, "flagship_id", None):
            return state.objects.get(player.flagship_id)
        # Fallback: scan battlefield for a Flagship-subtype Vessel
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return None
        for oid in battlefield.objects:
            obj = state.objects.get(oid)
            if obj and obj.controller == player_id and is_vessel(obj):
                if "Flagship" in obj.characteristics.subtypes:
                    return obj
        return None

    def vessels_at_depth(state: GameState, player_id: str, band: 'DepthBand') -> list['GameObject']:  # type: ignore[no-redef]
        out: list['GameObject'] = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return out
        for oid in battlefield.objects:
            obj = state.objects.get(oid)
            if obj and obj.controller == player_id and is_vessel(obj):
                if obj.state.depth_band == band:
                    out.append(obj)
        return out

    def depth_difference(a: 'DepthBand', b: 'DepthBand') -> int:  # type: ignore[no-redef]
        try:
            return abs(int(a.value) - int(b.value))
        except Exception:
            return 0


try:  # depths_combat.py — AttackerSpec/BlockerSpec and target/cost helpers
    from src.engine.depths_combat import (  # type: ignore[import-not-found]
        AttackerSpec,
        BlockerSpec,
        legal_targets_for as _combat_legal_targets_for,
        detection_cost as _combat_detection_cost,
        is_detected,
    )
    # Adapt combat module signatures to the AI's (state-first) convention.
    def legal_targets_for(state: GameState, attacker: 'GameObject'):  # type: ignore[no-redef]
        return _combat_legal_targets_for(attacker, state)

    def detection_cost(state: GameState, attacker: 'GameObject') -> int:  # type: ignore[no-redef]
        return _combat_detection_cost(attacker, state)

    _HAS_COMBAT_MODULE = True
except Exception:  # pragma: no cover — exercised only during parallel scaffold
    _HAS_COMBAT_MODULE = False

    @dataclass
    class AttackerSpec:  # type: ignore[no-redef]
        """One declared attacker: source vessel id + target id + firing band."""
        attacker_id: str
        target_id: str
        firing_band: 'DepthBand'

    @dataclass
    class BlockerSpec:  # type: ignore[no-redef]
        """One interceptor assignment: defender vessel intercepts one attacker."""
        blocker_id: str
        attacker_id: str

    def legal_targets_for(  # type: ignore[no-redef]
        state: GameState, attacker: 'GameObject'
    ) -> list[str]:
        """Targets opponent's Flagship and any opposing Vessel (no print rules)."""
        opp = _other_player(state, attacker.controller)
        if opp is None:
            return []
        targets: list[str] = []
        flagship = get_flagship(state, opp)
        if flagship is not None:
            targets.append(flagship.id)
        battlefield = state.zones.get("battlefield")
        if battlefield:
            for oid in battlefield.objects:
                obj = state.objects.get(oid)
                if obj and obj.controller == opp and is_vessel(obj) and obj.id != getattr(flagship, "id", None):
                    targets.append(obj.id)
        return targets

    def detection_cost(state: GameState, attacker: 'GameObject') -> int:  # type: ignore[no-redef]
        """Sonar to detect: 1 + depth_difficulty (0 at SURFACE, +2 at DEEP/CRUSH)."""
        band = attacker.state.depth_band
        if band is None:
            return 1
        try:
            diff = max(0, int(band.value) - int(DepthBand.SURFACE.value))
        except Exception:
            diff = 0
        # Silent Running keyword: +1 to detection cost.
        if "silent_running" in attacker.characteristics.keywords:
            diff += 1
        return 1 + diff

    def is_detected(obj: 'GameObject') -> bool:  # type: ignore[no-redef]
        return bool(getattr(obj.state, "detected", False))


# =============================================================================
# Maneuver action descriptors
# =============================================================================
#
# These are the action verbs the turn manager (Agent 3) consumes when it
# loops the AI through Maneuver / Regroup. We define them here rather
# than in ``depths_turn.py`` because they're intrinsic to the AI's
# decision representation; the turn manager just unpacks them. If Agent
# 3 prefers a different shape, the dataclasses are tiny and easy to
# adapt — only the ``ManeuverAction`` union is part of the public API.
# =============================================================================

@dataclass
class DeployVessel:
    """Play a Vessel from hand (engine pays cost, defaults band to SURFACE)."""
    card_id: str


@dataclass
class Dive:
    """Move a Vessel one band deeper (costs 1 Sonar Charge per design §4)."""
    vessel_id: str


@dataclass
class SurfaceVessel:
    """Move a Vessel one band shallower (free per design §4)."""
    vessel_id: str


@dataclass
class LayMine:
    """Place a Mine card from hand at a chosen depth band."""
    card_id: str
    depth_band: DepthBand


@dataclass
class AttachCrew:
    """Attach a Crew card from hand onto a friendly Vessel."""
    crew_id: str
    vessel_id: str


@dataclass
class AttachWeapon:
    """Attach a Weapon card from hand onto a friendly Vessel."""
    weapon_id: str
    vessel_id: str


@dataclass
class CastAction:
    """Play an Action (INSTANT-typed) card. Engine resolves the spell."""
    card_id: str
    target: Optional[str] = None


@dataclass
class ActivateAbility:
    """Activate an indexed ability on a permanent (Vessel / Weapon / Crew)."""
    vessel_id: str
    ability_idx: int
    target: Optional[str] = None


@dataclass
class Done:
    """No more actions this maneuver phase. Turn manager moves on."""
    pass


# Sum type the turn manager pattern-matches on.
ManeuverAction = Any  # one of the dataclasses above


# =============================================================================
# Heuristic constants (cite design doc §8)
# =============================================================================

# §8 Easy: deploy if board has fewer than this many friendly Vessels.
EASY_VESSEL_FLOOR = 3

# §8 Medium: deployment is preferred when (power + hull) / cost > 1.5.
MEDIUM_DEPLOY_VALUE_RATIO = 1.5

# §8 Medium: dive Vessels with power >= 3 toward DEEP for stealth.
MEDIUM_DIVE_POWER_THRESHOLD = 3

# §8 Medium: Flagship "lethal buffer" — detect attackers whose
# unintercepted damage would push Flagship below this much hull headroom.
MEDIUM_FLAGSHIP_LETHAL_BUFFER = 5

# §8 Medium: minimum expected damage to Flagship before AI will swing.
MEDIUM_MIN_ATTACK_DAMAGE = 2

# §8 Hard: top-K candidate sequences scored via 1-turn lookahead.
HARD_LOOKAHEAD_TOP_K = 5

# §8 Hard: weighted value function weights.
HARD_W_FLAGSHIP = 0.6
HARD_W_BOARD = 0.3
HARD_W_CHARGE = 0.1


# =============================================================================
# Helpers
# =============================================================================

def _other_player(state: GameState, player_id: str) -> Optional[str]:
    return next((pid for pid in state.players if pid != player_id), None)


def _hand_zone(state: GameState, player_id: str) -> Optional[Any]:
    return state.zones.get(f"hand_{player_id}")


def _battlefield(state: GameState) -> Optional[Any]:
    return state.zones.get("battlefield")


def _hand_cards(state: GameState, player_id: str) -> list['GameObject']:
    zone = _hand_zone(state, player_id)
    if not zone:
        return []
    out: list['GameObject'] = []
    for oid in zone.objects:
        obj = state.objects.get(oid)
        if obj is not None:
            out.append(obj)
    return out


def _own_vessels(state: GameState, player_id: str) -> list['GameObject']:
    bf = _battlefield(state)
    if not bf:
        return []
    return [
        obj for oid in bf.objects
        if (obj := state.objects.get(oid)) is not None
        and obj.controller == player_id
        and is_vessel(obj)
    ]


def _opp_vessels(state: GameState, player_id: str) -> list['GameObject']:
    opp = _other_player(state, player_id)
    if opp is None:
        return []
    return _own_vessels(state, opp)


def _opp_mines(state: GameState, player_id: str) -> list['GameObject']:
    opp = _other_player(state, player_id)
    if opp is None:
        return []
    bf = _battlefield(state)
    if not bf:
        return []
    return [
        obj for oid in bf.objects
        if (obj := state.objects.get(oid)) is not None
        and obj.controller == opp
        and CardType.DEPTHS_MINE in obj.characteristics.types
    ]


def _parse_charge_cost(card: 'GameObject') -> tuple[int, int]:
    """
    Return ``(torpedo, sonar)`` charges required to play this card.

    Costs print as e.g. ``{2T, 1S}`` per design §3. Cost lives on
    ``characteristics.mana_cost`` (reused for symbol parsing). When the
    string can't be parsed (e.g. a hybrid ``{X(T/S)}``), we fall back
    to a generic-1 estimate so the AI doesn't deadlock.
    """
    raw = card.characteristics.mana_cost or ""
    if not raw:
        return (0, 0)
    tc = 0
    sc = 0
    # Strip braces/whitespace and split on commas: ``{2T, 1S}`` -> ['2T', '1S']
    cleaned = raw.replace("{", "").replace("}", "").replace(" ", "")
    if not cleaned:
        return (0, 0)
    for token in cleaned.split(","):
        if not token:
            continue
        # Hybrid {X(T/S)} — treat as 1 of each as a defensive estimate.
        if "/" in token or "(" in token:
            tc += 1
            sc += 1
            continue
        # Trailing T or S indicates pool; leading digits are the amount.
        amount = 0
        i = 0
        while i < len(token) and token[i].isdigit():
            amount = amount * 10 + int(token[i])
            i += 1
        if amount == 0:
            amount = 1
        rest = token[i:].upper()
        if "T" in rest:
            tc += amount
        if "S" in rest:
            sc += amount
        if not rest:
            # Generic — bill against torpedo as the offensive default.
            tc += amount
    return (tc, sc)


def _can_afford(player: 'Player', tc: int, sc: int) -> bool:
    return int(getattr(player, "tc", 0)) >= tc and int(getattr(player, "sc", 0)) >= sc


def _power(obj: 'GameObject') -> int:
    return int(obj.characteristics.power or 0)


def _hull(obj: 'GameObject') -> int:
    """Effective hull (toughness - damage). Negative is clamped to 0."""
    base = obj.characteristics.toughness
    if base is None:
        return 0
    remaining = int(base) - int(getattr(obj.state, "damage", 0))
    return max(0, remaining)


def _cost_total(card: 'GameObject') -> int:
    tc, sc = _parse_charge_cost(card)
    return max(1, tc + sc)


def _value_ratio(card: 'GameObject') -> float:
    """``(power + hull) / cost`` per §8 Medium deployment heuristic."""
    cost = _cost_total(card)
    pt = (card.characteristics.power or 0) + (card.characteristics.toughness or 0)
    return float(pt) / float(cost)


def _depth_modifier_damage(attacker: 'GameObject', target: 'GameObject') -> int:
    """
    Damage after the depth-band modifier (§5: −1 per band of separation,
    min 1). ``homing`` keyword ignores the modifier.
    """
    base = _power(attacker)
    if "homing" in attacker.characteristics.keywords:
        return base
    a_band = attacker.state.depth_band
    t_band = target.state.depth_band
    if a_band is None or t_band is None:
        return base
    sep = depth_difference(a_band, t_band)
    return max(1, base - int(sep))


def _is_ready_to_attack(obj: 'GameObject') -> bool:
    state = obj.state
    if getattr(state, "tapped", False):
        return False
    if getattr(state, "summoning_sickness", False):
        return False
    if "Flagship" in obj.characteristics.subtypes:
        return False
    return True


def _flagship_buffer(state: GameState, player_id: str) -> int:
    """Remaining hull headroom on the Flagship (used by Medium detection)."""
    fs = get_flagship(state, player_id)
    if fs is None:
        return 0
    return _hull(fs)


# =============================================================================
# DepthsAIAdapter
# =============================================================================

class DepthsAIAdapter:
    """
    Three-tier heuristic adapter — see ``docs/games/depths.md`` §8.

    :param difficulty: ``"easy"``, ``"medium"``, or ``"hard"``
    :param rng: optional ``random.Random`` for deterministic tests
    """

    DIFFICULTIES = ("easy", "medium", "hard")

    def __init__(self, difficulty: str = "medium", rng: Optional[random.Random] = None):
        diff = (difficulty or "medium").lower()
        if diff not in self.DIFFICULTIES:
            diff = "medium"
        self.difficulty = diff
        self.rng = rng or random.Random()

    # ─── Mulligan ──────────────────────────────────────────────────

    def mulligan_decision(self, state: GameState, player_id: str,
                          hand: Optional[list['GameObject']] = None) -> bool:
        """
        Return True to keep the hand, False to mulligan.

        Default heuristic (per the prompt): keep if hand has at least 2
        Vessels and at least one Vessel of cost <= 3. This guarantees a
        2-drop curve play and a follow-up.
        """
        if hand is None:
            hand = _hand_cards(state, player_id)

        vessels = [c for c in hand if c is not None and CardType.DEPTHS_VESSEL in c.characteristics.types]
        if len(vessels) < 2:
            return False
        cheap = any(_cost_total(v) <= 3 for v in vessels)
        return cheap

    # ─── Maneuver loop dispatch ────────────────────────────────────

    def choose_maneuver_action(self, state: GameState, player_id: str) -> ManeuverAction:
        """
        Return one ``ManeuverAction`` to perform. The turn manager calls
        this in a loop until ``Done`` is returned. All three difficulties
        end the loop with ``Done`` once they have nothing useful to do.
        """
        if self.difficulty == "easy":
            return self._easy_maneuver(state, player_id)
        if self.difficulty == "medium":
            return self._medium_maneuver(state, player_id)
        return self._hard_maneuver(state, player_id)

    # ─── Combat dispatch ───────────────────────────────────────────

    def choose_attackers(self, state: GameState, player_id: str) -> list[AttackerSpec]:
        """Pick which Vessels attack this engagement and what they target."""
        if self.difficulty == "easy":
            return self._easy_attackers(state, player_id)
        if self.difficulty == "medium":
            return self._medium_attackers(state, player_id)
        return self._hard_attackers(state, player_id)

    def choose_detections(self, state: GameState, defender_id: str,
                          attackers: list[AttackerSpec]) -> dict[str, int]:
        """
        Decide how much Sonar to spend trying to detect each incoming
        attacker. Returns ``{attacker_id: sonar_spent}``. Spending exactly
        the detection cost detects that attacker; 0 means "don't bother".
        """
        if not attackers:
            return {}
        if self.difficulty == "easy":
            return self._easy_detections(state, defender_id, attackers)
        if self.difficulty == "medium":
            return self._medium_detections(state, defender_id, attackers)
        return self._hard_detections(state, defender_id, attackers)

    def choose_interceptors(self, state: GameState, defender_id: str,
                            detected_attackers: list[AttackerSpec]) -> list[BlockerSpec]:
        """
        Assign 1:1 interceptor blockers. Only detected attackers are
        legal targets (per §5). Returns an empty list if no Vessel
        wants to (or can) intercept.
        """
        if not detected_attackers:
            return []
        if self.difficulty == "easy":
            return self._easy_interceptors(state, defender_id, detected_attackers)
        if self.difficulty == "medium":
            return self._medium_interceptors(state, defender_id, detected_attackers)
        return self._hard_interceptors(state, defender_id, detected_attackers)

    # ==========================================================================
    # EASY tier — random with two safety floors (§8 Easy)
    # ==========================================================================

    def _easy_maneuver(self, state: GameState, player_id: str) -> ManeuverAction:
        player = state.players.get(player_id)
        if player is None:
            return Done()

        own_vessels = _own_vessels(state, player_id)
        hand = _hand_cards(state, player_id)

        # Floor 1 (§8 Easy): always deploy a Vessel if board < 3 friendly
        # Vessels and we can afford one. Pick uniformly at random among
        # affordable Vessels.
        if len(own_vessels) < EASY_VESSEL_FLOOR:
            affordable_vessels = [
                c for c in hand
                if CardType.DEPTHS_VESSEL in c.characteristics.types
                and _can_afford(player, *_parse_charge_cost(c))
            ]
            if affordable_vessels:
                pick = self.rng.choice(affordable_vessels)
                return DeployVessel(card_id=pick.id)

        # All other actions: weighted-random over the legal-action grab bag.
        legal = self._enumerate_legal_actions(state, player_id)
        if not legal:
            return Done()
        # 25% chance to stop early so Easy doesn't drain its hand every
        # turn — keeps the tutorial opponent feeling sloppy on purpose.
        if self.rng.random() < 0.25:
            return Done()
        return self.rng.choice(legal)

    def _easy_attackers(self, state: GameState, player_id: str) -> list[AttackerSpec]:
        opp = _other_player(state, player_id)
        if opp is None:
            return []
        attackers: list[AttackerSpec] = []
        ready = [v for v in _own_vessels(state, player_id) if _is_ready_to_attack(v)]

        for vessel in ready:
            if self.rng.random() < 0.4:
                # Skip ~40% — Easy doesn't always swing.
                continue
            target_ids = legal_targets_for(state, vessel)
            if not target_ids:
                continue
            target_id = self.rng.choice(target_ids)
            target = state.objects.get(target_id)

            # Safety floor 2 (§8 Easy): one-step lookahead — don't attack
            # into a known-lethal interceptor at the same band.
            if target is not None and _would_die_to_lethal_interceptor(
                state, vessel, target, opp
            ):
                continue

            band = vessel.state.depth_band or DepthBand.SURFACE
            attackers.append(AttackerSpec(
                vessel_id=vessel.id,
                target_id=target_id,
                firing_depth_band=band,
            ))
        return attackers

    def _easy_detections(self, state: GameState, defender_id: str,
                         attackers: list[AttackerSpec]) -> dict[str, int]:
        player = state.players.get(defender_id)
        if player is None:
            return {}
        budget = int(getattr(player, "sc", 0))
        out: dict[str, int] = {}
        order = list(attackers)
        self.rng.shuffle(order)
        for spec in order:
            if budget <= 0:
                break
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None or is_detected(attacker):
                continue
            cost = detection_cost(state, attacker)
            # Easy: 50/50 whether to actually spend.
            if self.rng.random() < 0.5 and cost <= budget:
                out[spec.vessel_id] = cost
                budget -= cost
        return out

    def _easy_interceptors(self, state: GameState, defender_id: str,
                           detected: list[AttackerSpec]) -> list[BlockerSpec]:
        ready = [v for v in _own_vessels(state, defender_id) if _is_ready_to_attack(v)]
        if not ready:
            return []
        assignments: list[BlockerSpec] = []
        used: set[str] = set()
        order = list(detected)
        self.rng.shuffle(order)
        for spec in order:
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None:
                continue
            candidates = [
                v for v in ready
                if v.id not in used and _can_intercept(v, attacker)
            ]
            if not candidates:
                continue
            blocker = self.rng.choice(candidates)
            used.add(blocker.id)
            assignments.append(BlockerSpec(interceptor_id=blocker.id, attacker_id=spec.vessel_id))
        return assignments

    # ==========================================================================
    # MEDIUM tier — greedy heuristic, no lookahead (§8 Medium)
    # ==========================================================================

    def _medium_maneuver(self, state: GameState, player_id: str) -> ManeuverAction:
        player = state.players.get(player_id)
        if player is None:
            return Done()

        hand = _hand_cards(state, player_id)
        own_vessels = _own_vessels(state, player_id)

        # 1. Deploy the best-value affordable Vessel (§8: ratio > 1.5).
        deploy = self._medium_pick_deploy(hand, player)
        if deploy is not None:
            return deploy

        # 2. Surface any Vessel sitting on top of an opposing Mine (§8).
        surface = self._medium_pick_surface_off_mine(state, player_id, own_vessels)
        if surface is not None:
            return surface

        # 3. Dive an undetected, beefy Vessel (power >= 3) toward DEEP (§8).
        dive = self._medium_pick_dive(state, player, own_vessels)
        if dive is not None:
            return dive

        # 4. Attach Crew/Weapon to a friendly Vessel if it strictly upgrades.
        attach = self._medium_pick_attach(state, hand, own_vessels, player)
        if attach is not None:
            return attach

        # 5. Lay a mine if we have one and it covers a likely attack lane.
        mine = self._medium_pick_mine(state, hand, player)
        if mine is not None:
            return mine

        # 6. Cast an Action card with a sensible target.
        action = self._medium_pick_action(state, hand, player_id, player)
        if action is not None:
            return action

        return Done()

    def _medium_pick_deploy(self, hand: list['GameObject'], player: 'Player') -> Optional[DeployVessel]:
        candidates: list[tuple[float, 'GameObject']] = []
        for card in hand:
            if CardType.DEPTHS_VESSEL not in card.characteristics.types:
                continue
            if not _can_afford(player, *_parse_charge_cost(card)):
                continue
            ratio = _value_ratio(card)
            # §8 Medium: prefer vessels above the 1.5 threshold.
            if ratio < MEDIUM_DEPLOY_VALUE_RATIO:
                continue
            candidates.append((ratio, card))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return DeployVessel(card_id=candidates[0][1].id)

    def _medium_pick_surface_off_mine(self, state: GameState, player_id: str,
                                      own_vessels: list['GameObject']) -> Optional[SurfaceVessel]:
        """Surface a Vessel out of any band that holds an opposing Mine (§8)."""
        opp_mine_bands = {
            mine.state.depth_band for mine in _opp_mines(state, player_id)
            if mine.state.depth_band is not None
        }
        if not opp_mine_bands:
            return None
        for vessel in own_vessels:
            if vessel.state.depth_band in opp_mine_bands and vessel.state.depth_band != DepthBand.SURFACE:
                # Surfacing is free per §4, so always safe to do.
                if "Flagship" not in vessel.characteristics.subtypes:
                    return SurfaceVessel(vessel_id=vessel.id)
        return None

    def _medium_pick_dive(self, state: GameState, player: 'Player',
                          own_vessels: list['GameObject']) -> Optional[Dive]:
        """Dive an undetected power-3+ Vessel toward DEEP if we can pay 1 Sonar."""
        if int(getattr(player, "sc", 0)) < 1:
            return None
        for vessel in own_vessels:
            if "Flagship" in vessel.characteristics.subtypes:
                continue
            if is_detected(vessel):
                continue
            if _power(vessel) < MEDIUM_DIVE_POWER_THRESHOLD:
                continue
            band = vessel.state.depth_band
            if band is None:
                continue
            try:
                # Already at max depth (DEEP per §4 — CRUSH is implosion).
                if int(band.value) >= int(DepthBand.DEEP.value):
                    continue
            except Exception:
                continue
            return Dive(vessel_id=vessel.id)
        return None

    def _medium_pick_attach(self, state: GameState, hand: list['GameObject'],
                            own_vessels: list['GameObject'],
                            player: 'Player') -> Optional[ManeuverAction]:
        if not own_vessels:
            return None
        best_host = max(own_vessels, key=lambda v: _power(v) + _hull(v))
        if "Flagship" in best_host.characteristics.subtypes:
            # Avoid attaching to the Flagship — it can't move; spread elsewhere.
            non_fs = [v for v in own_vessels if "Flagship" not in v.characteristics.subtypes]
            if non_fs:
                best_host = max(non_fs, key=lambda v: _power(v) + _hull(v))
        for card in hand:
            types = card.characteristics.types
            if CardType.DEPTHS_CREW in types and _can_afford(player, *_parse_charge_cost(card)):
                return AttachCrew(crew_id=card.id, vessel_id=best_host.id)
            if CardType.DEPTHS_WEAPON in types and _can_afford(player, *_parse_charge_cost(card)):
                return AttachWeapon(weapon_id=card.id, vessel_id=best_host.id)
        return None

    def _medium_pick_mine(self, state: GameState, hand: list['GameObject'],
                          player: 'Player') -> Optional[LayMine]:
        for card in hand:
            if CardType.DEPTHS_MINE not in card.characteristics.types:
                continue
            if not _can_afford(player, *_parse_charge_cost(card)):
                continue
            # Drop mines at the band where the opponent has the most Vessels;
            # default to PERISCOPE (the highest-traffic mid-band).
            opp = _other_player(state, card.controller)
            band_counts: dict['DepthBand', int] = {}
            if opp is not None:
                for v in _own_vessels(state, opp):
                    if v.state.depth_band is not None:
                        band_counts[v.state.depth_band] = band_counts.get(v.state.depth_band, 0) + 1
            if band_counts:
                target_band = max(band_counts.items(), key=lambda x: x[1])[0]
            else:
                target_band = DepthBand.PERISCOPE
            return LayMine(card_id=card.id, depth_band=target_band)
        return None

    def _medium_pick_action(self, state: GameState, hand: list['GameObject'],
                            player_id: str, player: 'Player') -> Optional[CastAction]:
        opp = _other_player(state, player_id)
        for card in hand:
            types = card.characteristics.types
            if CardType.INSTANT not in types and CardType.SORCERY not in types:
                continue
            if not _can_afford(player, *_parse_charge_cost(card)):
                continue
            target = None
            if opp is not None:
                # Default target: highest-power opposing Vessel (a removal-friendly pick).
                opp_vs = sorted(_opp_vessels(state, player_id), key=_power, reverse=True)
                if opp_vs:
                    target = opp_vs[0].id
            return CastAction(card_id=card.id, target=target)
        return None

    def _medium_attackers(self, state: GameState, player_id: str) -> list[AttackerSpec]:
        opp = _other_player(state, player_id)
        if opp is None:
            return []
        opp_flagship = get_flagship(state, opp)

        ready = [v for v in _own_vessels(state, player_id) if _is_ready_to_attack(v)]
        attackers: list[AttackerSpec] = []
        for vessel in ready:
            target_ids = legal_targets_for(state, vessel)
            if not target_ids:
                continue

            scored: list[tuple[float, str]] = []
            for tid in target_ids:
                target = state.objects.get(tid)
                if target is None:
                    continue
                dmg = _depth_modifier_damage(vessel, target)
                if target is opp_flagship:
                    # §8 Medium: only swing at Flagship if expected damage >= 2.
                    if dmg >= MEDIUM_MIN_ATTACK_DAMAGE:
                        # Bias toward Flagship when it's hurt (closing the game).
                        urgency = 10.0 - float(_hull(opp_flagship))
                        scored.append((dmg * 2.0 + max(0.0, urgency), tid))
                else:
                    # Trade scoring: prefer to sink high-value enemy Vessels.
                    target_value = _power(target) + _hull(target)
                    if dmg >= _hull(target):
                        scored.append((float(target_value) * 1.5, tid))
                    elif dmg >= MEDIUM_MIN_ATTACK_DAMAGE:
                        scored.append((float(target_value) * 0.5, tid))

            if not scored:
                continue
            scored.sort(reverse=True)
            best_score, best_tid = scored[0]
            if best_score <= 0:
                continue
            band = vessel.state.depth_band or DepthBand.SURFACE
            attackers.append(AttackerSpec(
                vessel_id=vessel.id,
                target_id=best_tid,
                firing_depth_band=band,
            ))
        return attackers

    def _medium_detections(self, state: GameState, defender_id: str,
                           attackers: list[AttackerSpec]) -> dict[str, int]:
        """
        §8 Medium: spend Sonar on attackers whose unintercepted damage
        would push Flagship below ``hull - lethal_buffer``.
        """
        player = state.players.get(defender_id)
        if player is None:
            return {}
        budget = int(getattr(player, "sc", 0))
        flagship_hull = _flagship_buffer(state, defender_id)
        if budget <= 0:
            return {}

        # Sort attackers by danger to Flagship (descending).
        ranked: list[tuple[int, AttackerSpec]] = []
        for spec in attackers:
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None or is_detected(attacker):
                continue
            target = state.objects.get(spec.target_id)
            if target is None:
                continue
            # Only Flagship-bound attackers feed the buffer math; other
            # detections are a luxury at this tier.
            target_is_flagship = "Flagship" in target.characteristics.subtypes
            danger = _depth_modifier_damage(attacker, target) if target_is_flagship else 0
            ranked.append((danger, spec))
        ranked.sort(key=lambda x: x[0], reverse=True)

        out: dict[str, int] = {}
        cumulative_unintercepted = sum(d for d, _ in ranked)
        # If unintercepted damage > flagship_hull - lethal_buffer, start
        # detecting in danger order until the projection falls below.
        while cumulative_unintercepted > max(0, flagship_hull - MEDIUM_FLAGSHIP_LETHAL_BUFFER):
            if not ranked or budget <= 0:
                break
            danger, spec = ranked.pop(0)
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None:
                continue
            cost = detection_cost(state, attacker)
            if cost > budget:
                # Can't afford this one; skip and try the next-most-dangerous.
                continue
            out[spec.vessel_id] = cost
            budget -= cost
            cumulative_unintercepted -= danger
        return out

    def _medium_interceptors(self, state: GameState, defender_id: str,
                             detected: list[AttackerSpec]) -> list[BlockerSpec]:
        ready = [v for v in _own_vessels(state, defender_id) if _is_ready_to_attack(v)]
        if not ready:
            return []
        # Sort attackers by damage threat (descending).
        threats: list[tuple[int, AttackerSpec]] = []
        for spec in detected:
            attacker = state.objects.get(spec.vessel_id)
            target = state.objects.get(spec.target_id)
            if attacker is None or target is None:
                continue
            threats.append((_depth_modifier_damage(attacker, target), spec))
        threats.sort(key=lambda x: x[0], reverse=True)

        assignments: list[BlockerSpec] = []
        used: set[str] = set()
        for _danger, spec in threats:
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None:
                continue
            candidates = [v for v in ready if v.id not in used and _can_intercept(v, attacker)]
            if not candidates:
                continue
            # Prefer interceptors that survive the trade and ideally kill the attacker.
            def block_score(v: 'GameObject') -> tuple[int, int, int]:
                survives = 1 if _power(attacker) < _hull(v) else 0
                kills = 1 if _power(v) >= _hull(attacker) else 0
                # Prefer cheapest hulls when no good option exists.
                value_lost = -(_power(v) + _hull(v)) if not survives else 0
                return (kills + survives, value_lost, _power(v))
            blocker = max(candidates, key=block_score)
            # Don't trade if we lose value AND don't kill (chump only when threatened lethally).
            survives = _power(attacker) < _hull(blocker)
            kills = _power(blocker) >= _hull(attacker)
            if not survives and not kills:
                # Only chump if attacker is heading at the Flagship for >= MIN_ATTACK_DAMAGE.
                target_obj = state.objects.get(spec.target_id)
                if target_obj is None or "Flagship" not in target_obj.characteristics.subtypes:
                    continue
            used.add(blocker.id)
            assignments.append(BlockerSpec(interceptor_id=blocker.id, attacker_id=spec.vessel_id))
        return assignments

    # ==========================================================================
    # HARD tier — lookahead-1 with value heuristics (§8 Hard)
    # ==========================================================================
    #
    # Implementation note: we use ``copy.deepcopy(state)`` for forward
    # simulation, which is the slow-but-correct choice. The score
    # function only depends on:
    #   * own + opponent flagship hull
    #   * own + opponent battlefield Vessels (P+T sum)
    #   * own + opponent (tc + sc) charge totals
    # ...so a faster shallow simulator would only need to track those
    # six numbers. We chose deepcopy because (a) the AI runs once per
    # phase, not per-frame, (b) the shallow simulator would have to
    # duplicate combat math that ``DepthsCombatManager`` owns, and (c)
    # cards routinely emit ETB triggers / static effects whose impact
    # only shows up after the engine's pipeline runs — a shallow sim
    # would systematically underrate triggered-ability cards. If
    # profiling shows deepcopy is the bottleneck we'll fall back to
    # the shallow approximation tracking only the score inputs.
    #
    # The "simulate one turn" step is currently a stub that returns
    # the unmodified state and lets the score function read off the
    # POST-action snapshot. Once Agent 3's turn manager exposes a
    # ``simulate_turn(state, player_id, actions)`` helper we can wire
    # it in here without changing any of the surrounding policy code.
    # ==========================================================================

    def _hard_maneuver(self, state: GameState, player_id: str) -> ManeuverAction:
        legal = self._enumerate_legal_actions(state, player_id)
        if not legal:
            return Done()

        # Score each candidate via greedy expansion (one action) +
        # immediate value-function delta. We don't do full sequence
        # simulation per call because the manager already loops this
        # method until ``Done`` — successive calls naturally chain.
        scored: list[tuple[float, ManeuverAction]] = []
        baseline = self._score_state(state, player_id)
        for action in legal:
            forecast = self._simulate_action(state, player_id, action)
            if forecast is None:
                continue
            delta = self._score_state(forecast, player_id) - baseline
            scored.append((delta, action))

        if not scored:
            return Done()

        scored.sort(key=lambda x: x[0], reverse=True)
        # Take the top-K and weight slightly toward Done if the best
        # candidate doesn't actually improve our position.
        scored = scored[:HARD_LOOKAHEAD_TOP_K]
        best_delta, best_action = scored[0]
        if best_delta <= 0:
            return Done()
        return best_action

    def _hard_attackers(self, state: GameState, player_id: str) -> list[AttackerSpec]:
        # Hard reuses the Medium attacker selector for the first pass —
        # the value function it cares about (§8 weights) lives mostly
        # in the maneuver phase. The saturation-strike heuristic
        # below adds the extra "stealth strike when opponent is sonar-poor"
        # behavior described in §8.
        attackers = self._medium_attackers(state, player_id)

        opp = _other_player(state, player_id)
        if opp is None:
            return attackers
        opp_player = state.players.get(opp)
        opp_sonar = int(getattr(opp_player, "sc", 0)) if opp_player else 0

        # Saturation strike: include any *additional* stealth-keyword
        # Vessels we held back when the opponent's total Sonar budget
        # can't cover detecting all of our attackers.
        already_attacking = {a.vessel_id for a in attackers}
        ready_stealth = [
            v for v in _own_vessels(state, player_id)
            if _is_ready_to_attack(v)
            and v.id not in already_attacking
            and "stealth" in v.characteristics.keywords
        ]
        if ready_stealth:
            opp_flagship = get_flagship(state, opp)
            projected_detect_cost = sum(detection_cost(state, state.objects[a.vessel_id])
                                        for a in attackers if a.vessel_id in state.objects)
            if opp_sonar < projected_detect_cost + 1 and opp_flagship is not None:
                # Opponent can't afford to ping all of us — pile on with stealth.
                for vessel in ready_stealth:
                    band = vessel.state.depth_band or DepthBand.SURFACE
                    attackers.append(AttackerSpec(
                        vessel_id=vessel.id,
                        target_id=opp_flagship.id,
                        firing_depth_band=band,
                    ))
        return attackers

    def _hard_detections(self, state: GameState, defender_id: str,
                         attackers: list[AttackerSpec]) -> dict[str, int]:
        # Hard ranks attackers by *value-function* damage (not just
        # Flagship) and keeps the Medium spend-only-when-buffer-threatened
        # discipline as a floor.
        plan = self._medium_detections(state, defender_id, attackers)

        # If we still have unspent Sonar after the buffer-rule plan,
        # spend it on the highest-EV stealth attackers we can afford.
        player = state.players.get(defender_id)
        if player is None:
            return plan
        spent = sum(plan.values())
        budget = int(getattr(player, "sc", 0)) - spent
        if budget <= 0:
            return plan

        leftovers: list[tuple[float, AttackerSpec, int]] = []
        for spec in attackers:
            if spec.vessel_id in plan:
                continue
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None or is_detected(attacker):
                continue
            cost = detection_cost(state, attacker)
            if cost > budget:
                continue
            target = state.objects.get(spec.target_id)
            if target is None:
                continue
            ev = float(_depth_modifier_damage(attacker, target)) + 0.5 * float(_power(attacker) + _hull(attacker))
            leftovers.append((ev, spec, cost))
        leftovers.sort(key=lambda x: x[0], reverse=True)
        for ev, spec, cost in leftovers:
            if cost > budget:
                continue
            plan[spec.vessel_id] = cost
            budget -= cost
            if budget <= 0:
                break
        return plan

    def _hard_interceptors(self, state: GameState, defender_id: str,
                           detected: list[AttackerSpec]) -> list[BlockerSpec]:
        # The Medium block planner already does kill/survive scoring.
        # Hard would benefit from full lookahead but we intentionally
        # cap simulation depth to keep the AI snappy. Reuse Medium.
        return self._medium_interceptors(state, defender_id, detected)

    # ──────────────────────────────────────────────────────────────────────
    # Hard-tier helpers
    # ──────────────────────────────────────────────────────────────────────

    def _simulate_action(self, state: GameState, player_id: str,
                         action: ManeuverAction) -> Optional[GameState]:
        """
        Forward-simulate ONE maneuver action by deep-copying the state
        and applying a best-effort approximation of the action's effect.

        We don't have the real engine pipeline here — we'd need
        ``depths.py``'s deploy/dive/surface helpers. Until those land,
        we approximate: deploy spends charges + decrements hand;
        dive/surface adjusts depth; charge cost is modeled.

        Returns ``None`` if the action can't be approximated cleanly.
        """
        try:
            forecast = copy.deepcopy(state)
        except Exception:
            return None

        player = forecast.players.get(player_id)
        if player is None:
            return None

        if isinstance(action, Done):
            return forecast

        if isinstance(action, DeployVessel):
            card = forecast.objects.get(action.card_id)
            if card is None:
                return None
            tc, sc = _parse_charge_cost(card)
            player.tc = max(0, int(getattr(player, "tc", 0)) - tc)
            player.sc = max(0, int(getattr(player, "sc", 0)) - sc)
            # Approximate ETB: move the card object to the battlefield zone
            # and tag it with a SURFACE depth band. This lets _score_state
            # see it as friendly board value.
            hand_zone = forecast.zones.get(f"hand_{player_id}")
            bf = forecast.zones.get("battlefield")
            if hand_zone and action.card_id in hand_zone.objects:
                hand_zone.objects.remove(action.card_id)
            if bf is not None:
                bf.objects.append(action.card_id)
            card.zone = ZoneType.BATTLEFIELD
            card.state.depth_band = DepthBand.SURFACE
            return forecast

        if isinstance(action, Dive):
            vessel = forecast.objects.get(action.vessel_id)
            if vessel is None:
                return None
            player.sc = max(0, int(getattr(player, "sc", 0)) - 1)
            band = vessel.state.depth_band
            if band is not None:
                try:
                    next_val = min(int(DepthBand.DEEP.value), int(band.value) + 1)
                    vessel.state.depth_band = DepthBand(next_val)
                except Exception:
                    pass
            return forecast

        if isinstance(action, SurfaceVessel):
            vessel = forecast.objects.get(action.vessel_id)
            if vessel is None:
                return None
            band = vessel.state.depth_band
            if band is not None:
                try:
                    next_val = max(int(DepthBand.SURFACE.value), int(band.value) - 1)
                    vessel.state.depth_band = DepthBand(next_val)
                except Exception:
                    pass
            return forecast

        if isinstance(action, LayMine):
            card = forecast.objects.get(action.card_id)
            if card is None:
                return None
            tc, sc = _parse_charge_cost(card)
            player.tc = max(0, int(getattr(player, "tc", 0)) - tc)
            player.sc = max(0, int(getattr(player, "sc", 0)) - sc)
            hand_zone = forecast.zones.get(f"hand_{player_id}")
            bf = forecast.zones.get("battlefield")
            if hand_zone and action.card_id in hand_zone.objects:
                hand_zone.objects.remove(action.card_id)
            if bf is not None:
                bf.objects.append(action.card_id)
            card.zone = ZoneType.BATTLEFIELD
            card.state.depth_band = action.depth_band
            return forecast

        if isinstance(action, (AttachCrew, AttachWeapon, CastAction, ActivateAbility)):
            # For these we lack reliable inline approximations. Pay the
            # cost so the score function discourages free spending, but
            # don't try to model the effect.
            card_id = getattr(action, "card_id", None) or getattr(action, "crew_id", None) or getattr(action, "weapon_id", None)
            if card_id and (card := forecast.objects.get(card_id)) is not None:
                tc, sc = _parse_charge_cost(card)
                player.tc = max(0, int(getattr(player, "tc", 0)) - tc)
                player.sc = max(0, int(getattr(player, "sc", 0)) - sc)
            return forecast

        return forecast

    def _score_state(self, state: GameState, player_id: str) -> float:
        """
        §8 Hard value function:
          0.6 * flagship_hull_diff
          + 0.3 * board_value_diff
          + 0.1 * charge_economy_diff
        Higher is better for ``player_id``.
        """
        opp = _other_player(state, player_id)
        if opp is None:
            return 0.0

        own_fs = get_flagship(state, player_id)
        opp_fs = get_flagship(state, opp)
        own_hull = _hull(own_fs) if own_fs is not None else 0
        opp_hull = _hull(opp_fs) if opp_fs is not None else 0
        flagship_hull_diff = float(own_hull - opp_hull)

        own_value = sum(_power(v) + _hull(v) for v in _own_vessels(state, player_id))
        opp_value = sum(_power(v) + _hull(v) for v in _own_vessels(state, opp))
        board_value_diff = float(own_value - opp_value)

        own_player = state.players.get(player_id)
        opp_player = state.players.get(opp)
        own_charges = int(getattr(own_player, "tc", 0)) + int(getattr(own_player, "sc", 0)) if own_player else 0
        opp_charges = int(getattr(opp_player, "tc", 0)) + int(getattr(opp_player, "sc", 0)) if opp_player else 0
        charge_economy_diff = float(own_charges - opp_charges)

        return (
            HARD_W_FLAGSHIP * flagship_hull_diff
            + HARD_W_BOARD * board_value_diff
            + HARD_W_CHARGE * charge_economy_diff
        )

    # ==========================================================================
    # Shared legal-move generator
    # ==========================================================================

    def _enumerate_legal_actions(self, state: GameState, player_id: str) -> list[ManeuverAction]:
        """
        Produce every legal maneuver action the AI knows how to evaluate.
        All three difficulties consume this list — they differ in policy.
        """
        player = state.players.get(player_id)
        if player is None:
            return []

        actions: list[ManeuverAction] = []
        hand = _hand_cards(state, player_id)
        own_vessels = _own_vessels(state, player_id)

        for card in hand:
            tc, sc = _parse_charge_cost(card)
            if not _can_afford(player, tc, sc):
                continue
            types = card.characteristics.types
            if CardType.DEPTHS_VESSEL in types:
                actions.append(DeployVessel(card_id=card.id))
            elif CardType.DEPTHS_MINE in types:
                # Default to PERISCOPE — the most-trafficked band per §4.
                actions.append(LayMine(card_id=card.id, depth_band=DepthBand.PERISCOPE))
            elif CardType.DEPTHS_CREW in types and own_vessels:
                for host in own_vessels:
                    actions.append(AttachCrew(crew_id=card.id, vessel_id=host.id))
            elif CardType.DEPTHS_WEAPON in types and own_vessels:
                for host in own_vessels:
                    actions.append(AttachWeapon(weapon_id=card.id, vessel_id=host.id))
            elif CardType.INSTANT in types or CardType.SORCERY in types:
                actions.append(CastAction(card_id=card.id))

        for vessel in own_vessels:
            if "Flagship" in vessel.characteristics.subtypes:
                continue
            band = vessel.state.depth_band
            if band is None:
                continue
            try:
                if int(band.value) < int(DepthBand.DEEP.value) and int(getattr(player, "sc", 0)) >= 1:
                    actions.append(Dive(vessel_id=vessel.id))
                if int(band.value) > int(DepthBand.SURFACE.value):
                    actions.append(SurfaceVessel(vessel_id=vessel.id))
            except Exception:
                continue

            # Activated abilities, if the engine has registered any descriptors.
            for idx, _desc in enumerate(getattr(vessel.state, "activated_abilities", []) or []):
                actions.append(ActivateAbility(vessel_id=vessel.id, ability_idx=idx))

        return actions


# =============================================================================
# Internal combat helpers (free functions — used by Easy + Medium policies)
# =============================================================================

def _can_intercept(blocker: 'GameObject', attacker: 'GameObject') -> bool:
    """Reach <= 1 band by default; ``reach`` keyword bumps it to 2 (§7 keywords)."""
    a = attacker.state.depth_band
    b = blocker.state.depth_band
    if a is None or b is None:
        return False
    sep = depth_difference(a, b)
    max_reach = 2 if "reach" in blocker.characteristics.keywords else 1
    return sep <= max_reach


def _would_die_to_lethal_interceptor(state: GameState, attacker: 'GameObject',
                                     target: 'GameObject', defender_id: str) -> bool:
    """
    §8 Easy floor 2: refuse to attack into a known-lethal interceptor
    that we don't kill back. We approximate "known" as "any opposing
    Vessel within reach of the target's depth band that has lethal
    power and survives the trade".
    """
    target_band = target.state.depth_band
    if target_band is None:
        return False
    for v in _own_vessels(state, defender_id):
        if v.id == target.id:
            continue
        if not _can_intercept(v, attacker):
            continue
        if _power(v) >= _hull(attacker) and _power(attacker) < _hull(v):
            return True
    return False


__all__ = [
    "DepthsAIAdapter",
    "ManeuverAction",
    "DeployVessel",
    "Dive",
    "SurfaceVessel",
    "LayMine",
    "AttachCrew",
    "AttachWeapon",
    "CastAction",
    "ActivateAbility",
    "Done",
    "AttackerSpec",
    "BlockerSpec",
    "DepthBand",
]
