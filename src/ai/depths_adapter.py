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
# Lowered from 5 → 3 in iter-4 (2026-05-07) per coach finding: under-detection
# of mid-game chip swings (Pilot B's 3-attacker swings T14/T18/T22 in iter-3
# all uncontested with P1 at 4-9 SC because cumulative damage didn't reach
# the lethal threshold).
MEDIUM_FLAGSHIP_LETHAL_BUFFER = 3

# §8 Medium: cumulative-damage detection escalation (iter-5 patch).
# Track damage taken in the last N turns; if total exceeds the threshold,
# add it to the lethal-buffer projection so the AI starts intercepting
# *streams* of chip damage, not just single lethal-projecting swings.
MEDIUM_RECENT_DAMAGE_WINDOW = 3
# Iter-6 lowered 6→4: drone swarms deal 4-5 hull/attack-turn; the 6-hull trigger
# never fired even with 4 uncontested 2/1-drone swings (each 4-5 chip, always <6).
MEDIUM_RECENT_DAMAGE_TRIGGER = 4  # 4+ hull lost in last 3 turns starts the escalation
# When chip-stream is detected, force-detect this many top attackers regardless of
# lethal projection (stops the AI from sitting idle while a swarm bleeds it out).
MEDIUM_CHIP_FORCE_DETECT = 2

# §8 Medium: minimum expected damage to Flagship before AI will swing.
MEDIUM_MIN_ATTACK_DAMAGE = 2

# §8 Hard: top-K candidate sequences scored via 1-turn lookahead.
HARD_LOOKAHEAD_TOP_K = 5

# §8 Hard: weighted value function weights.
HARD_W_FLAGSHIP = 0.6
HARD_W_BOARD = 0.3
HARD_W_CHARGE = 0.1

# Maneuver self-cap — the turn manager already enforces _ACTION_LOOP_CAP=200,
# but a tighter per-turn ceiling keeps the AI from monopolising compute on
# pathological boards (e.g. a Vessel with a {1S} ability and 10 SC). 30 is
# generous enough for any realistic combo turn yet bounded.
MAX_ACTIONS_PER_PHASE = 30


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


def _parse_charge_cost_str(raw: Optional[str]) -> Optional[tuple[int, int]]:
    """Parse a printed cost string like ``{2T, 1S}`` to ``(tc, sc)``.

    Mirrors ``_parse_charge_cost`` (which takes a card object) but accepts a
    raw string — used by the activated-ability picker. Returns None if the
    string is empty / unparseable; ``(0, 0)`` for free costs.
    """
    if raw is None:
        return None
    cleaned = str(raw).replace("{", "").replace("}", "").replace(" ", "")
    if not cleaned:
        return (0, 0)
    tc = 0
    sc = 0
    for token in cleaned.split(","):
        if not token:
            continue
        if "/" in token or "(" in token:
            tc += 1
            sc += 1
            continue
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
            tc += amount
    return (tc, sc)


def _power(obj: 'GameObject', state: Optional[GameState] = None) -> int:
    """Effective power. When ``state`` is supplied, applies runtime
    modifiers (PT_MODIFICATION events from ``cast_effect_fn`` actions
    like Saturation Strike, +1/+1 counters, lord auras, etc.) by routing
    through ``src.engine.queries.get_power``. When ``state`` is omitted,
    returns the printed value — preserves the legacy behaviour for
    callsites that don't care about pumps (mulligan / deploy heuristics).
    """
    if state is not None:
        try:
            from src.engine.queries import get_power as _query_get_power
            return int(_query_get_power(obj, state))
        except Exception:
            pass
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


def _depth_modifier_damage(attacker: 'GameObject', target: 'GameObject',
                           state: Optional[GameState] = None) -> int:
    """
    Damage after the depth-band modifier (§5: −1 per band of separation,
    min 1). ``homing`` keyword ignores the modifier.

    When ``state`` is supplied, projects the EFFECTIVE power including
    runtime PT modifiers (e.g. Saturation Strike's +2 EOT pump). The AI
    defense path (``_medium_detections`` / ``_medium_interceptors``)
    threads state through so a pumped attacker isn't undercounted as the
    printed value. Iter 2 lesson: without this, defender stays asleep
    while a 9-damage alpha lands unintercepted.
    """
    base = _power(attacker, state)
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


# ---------------------------------------------------------------------------
# Crew / Weapon / Mine / ActivateAbility helpers
# ---------------------------------------------------------------------------

def _is_unattached_vessel(vessel: 'GameObject') -> bool:
    """A Vessel is "un-attached" when it has no Crew/Weapon attached to it."""
    attachments = getattr(vessel.state, "attachments", None) or []
    return len(attachments) == 0


def _is_engaged(vessel: 'GameObject') -> bool:
    """Engaged = currently taking damage or about to attack (proxy: tapped or
    has hull damage). Used for Crew-attach prioritisation per the design doc:
    'prefer attaching to a Vessel that's currently engaged'."""
    if int(getattr(vessel.state, "damage", 0)) > 0:
        return True
    # Vessels declared as attackers get tapped during the engagement step.
    if getattr(vessel.state, "tapped", False):
        return True
    return False


def _has_attachable_host(state: GameState, player_id: str) -> bool:
    """Player controls at least one non-Flagship Vessel."""
    for v in _own_vessels(state, player_id):
        if "Flagship" not in v.characteristics.subtypes:
            return True
    return False


def _own_mines(state: GameState, player_id: str) -> list['GameObject']:
    """Mines on the battlefield controlled by ``player_id``."""
    bf = _battlefield(state)
    if not bf:
        return []
    return [
        obj for oid in bf.objects
        if (obj := state.objects.get(oid)) is not None
        and obj.controller == player_id
        and CardType.DEPTHS_MINE in obj.characteristics.types
    ]


def _ability_can_activate(ability, vessel: 'GameObject', state: GameState) -> bool:
    """True if this activated ability can be activated this turn.

    Honours ``once_per_turn`` (via ``last_activation_turn`` on the ability or
    a ``activations_this_turn`` counter) and ``once_per_game`` exhaust.
    """
    if ability is None:
        return False
    # Once-per-game / Exhaust guard.
    if getattr(ability, "once_per_game", False) or getattr(ability, "is_exhaust", False):
        if int(getattr(ability, "activations_this_turn", 0)) > 0:
            return False
    # Once-per-turn guard: compare against state.turn_number.
    if getattr(ability, "once_per_turn", False):
        last = getattr(ability, "last_activation_turn", -1)
        try:
            if int(last) == int(getattr(state, "turn_number", 0)):
                return False
        except Exception:
            pass
    # own-turn-only guard (applies to most depths abilities).
    if getattr(ability, "own_turn_only", False):
        active_pid = getattr(state, "active_player_id", None)
        if active_pid and active_pid != vessel.controller:
            return False
    # Pre-condition (rare on depths cards).
    pre = getattr(ability, "precondition_fn", None)
    if callable(pre):
        try:
            if not pre(vessel, state):
                return False
        except Exception:
            return False
    return True


def _ability_cost(ability) -> Optional[str]:
    """Return the cost string for an activated ability — handles both the dict
    descriptor shape (legacy) and the ``ActivatedAbility`` dataclass shape."""
    if ability is None:
        return None
    if isinstance(ability, dict):
        return ability.get("cost") or ability.get("cost_text")
    return getattr(ability, "cost_text", None) or getattr(ability, "cost", None)


def _ability_emits_damage(ability) -> bool:
    """Heuristic: True if the ability's description mentions damage / 'deal X'.
    The effect_fn signature doesn't expose a clean 'this is removal' flag, so
    we sniff the text. Used to bias the Medium activation picker."""
    if ability is None:
        return False
    desc = ""
    if isinstance(ability, dict):
        desc = str(ability.get("description") or ability.get("text") or "")
    else:
        desc = str(getattr(ability, "description", "") or "")
    desc = desc.lower()
    return any(tok in desc for tok in ("deal", "damage", "destroy", "kill"))


def _ability_is_utility_draw(ability) -> bool:
    if ability is None:
        return False
    desc = ""
    if isinstance(ability, dict):
        desc = str(ability.get("description") or ability.get("text") or "")
    else:
        desc = str(getattr(ability, "description", "") or "")
    desc = desc.lower()
    return any(tok in desc for tok in ("draw", "untap", "gain", "scry"))


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
        # Per-turn action counter — keyed by (player_id, turn_number, phase_label).
        # The maneuver loop calls this adapter once per action; we self-cap at
        # MAX_ACTIONS_PER_PHASE per (player, turn) so a degenerate vessel + cheap
        # ability combo can't drag a single turn out indefinitely. Phase changes
        # are detected via state.turn_number changes (a new turn resets).
        self._action_counter: dict[tuple[str, int], int] = {}
        # iter-5 cumulative-damage tracker: {defender_id: [(turn, hull_remaining), ...]}.
        # Updated on each _medium_detections call. Entries past the window are pruned.
        self._flagship_hull_history: dict[str, list[tuple[int, int]]] = {}

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

    # ─── Per-turn action self-cap ──────────────────────────────────

    def _note_action_call(self, state: GameState, player_id: str) -> bool:
        """Increment this turn's action counter and return False once the cap
        is reached. Returning False causes the maneuver pipeline to short-
        circuit to ``Done()`` so the turn manager can move on. Resets when
        ``state.turn_number`` changes.
        """
        turn = int(getattr(state, "turn_number", 0) or 0)
        key = (player_id, turn)
        # Garbage-collect older counters so the dict doesn't grow forever.
        stale = [k for k in self._action_counter if k[1] < turn - 1]
        for k in stale:
            self._action_counter.pop(k, None)
        count = self._action_counter.get(key, 0) + 1
        self._action_counter[key] = count
        return count <= MAX_ACTIONS_PER_PHASE

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
        if not self._note_action_call(state, player_id):
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

        # Per-call action cap: prevents pathological loops where a cheap
        # repeating activation drains the AI's budget. The turn manager has
        # _ACTION_LOOP_CAP=200 as a hard floor; we self-limit at MAX_ACTIONS_PER_PHASE.
        if not self._note_action_call(state, player_id):
            return Done()

        hand = _hand_cards(state, player_id)
        own_vessels = _own_vessels(state, player_id)

        # 1. Deploy the best-value affordable Vessel (§8: ratio > 1.5).
        deploy = self._medium_pick_deploy(hand, player)
        if deploy is not None:
            return deploy

        # 1b. Cast a Doctrine (persistent global enchantment) — earlier is
        #     better since the effect compounds across remaining turns.
        doctrine = self._medium_pick_doctrine(state, hand, player_id, player)
        if doctrine is not None:
            return doctrine

        # 2. Lay a Mine — best done early so it's actively defending. Highest
        #    impact when the opponent has surface vessels (PERISCOPE) or is
        #    mid-board (MID).
        mine = self._medium_pick_mine(state, hand, player_id, player)
        if mine is not None:
            return mine

        # 3. Attach Crew/Weapon to a friendly Vessel that benefits.
        attach = self._medium_pick_attach(state, hand, own_vessels, player)
        if attach is not None:
            return attach

        # 4. Surface a Vessel under threat OR for a profitable strike (§8).
        surface = self._medium_pick_surface(state, player_id, own_vessels)
        if surface is not None:
            return surface

        # 5. Dive an undetected, beefy Vessel (power >= 3) toward DEEP (§8).
        dive = self._medium_pick_dive(state, player, own_vessels)
        if dive is not None:
            return dive

        # 6. Activate a payable ability (damage > untap/draw > other).
        activate = self._medium_pick_activate(state, player_id, own_vessels)
        if activate is not None:
            return activate

        # 7. Cast an Action card with a sensible target.
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

    def _medium_pick_surface(self, state: GameState, player_id: str,
                             own_vessels: list['GameObject']) -> Optional[SurfaceVessel]:
        """Surface for one of two reasons (§8):

        (a) Escape: a Vessel sits at a depth band that holds an opposing Mine.
        (b) Profitable strike: the Vessel is below SURFACE, has power that
            (after the depth-modifier penalty) would deal more damage to the
            opposing Flagship from a shallower band than its current band.

        Vessels with the ``bottom_crawler`` keyword are explicitly skipped —
        they WANT to be deep (per the design doc keyword definition).
        """
        # (a) Escape from opposing Mines (free move, always safe).
        opp_mine_bands = {
            mine.state.depth_band for mine in _opp_mines(state, player_id)
            if mine.state.depth_band is not None
        }
        if opp_mine_bands:
            for vessel in own_vessels:
                if "Flagship" in vessel.characteristics.subtypes:
                    continue
                if "bottom_crawler" in vessel.characteristics.keywords:
                    continue
                band = vessel.state.depth_band
                if band in opp_mine_bands and band != DepthBand.SURFACE:
                    return SurfaceVessel(vessel_id=vessel.id)

        # (b) Profitable surface→strike sequence. We surface ONLY if:
        #   - the vessel is currently at MID/DEEP/CRUSH (not PERISCOPE — the
        #     Flagship sits there, so the depth penalty against Flagship is 0
        #     from PERISCOPE already).
        #   - shallower band yields strictly more depth-modifier damage to
        #     the opposing Flagship.
        opp = _other_player(state, player_id)
        opp_flagship = get_flagship(state, opp) if opp else None
        if opp_flagship is None:
            return None
        flagship_band = opp_flagship.state.depth_band or DepthBand.PERISCOPE
        for vessel in own_vessels:
            if "Flagship" in vessel.characteristics.subtypes:
                continue
            if "bottom_crawler" in vessel.characteristics.keywords:
                continue
            if "homing" in vessel.characteristics.keywords:
                # Homing ignores the depth penalty — surfacing buys nothing.
                continue
            band = vessel.state.depth_band
            if band is None or band == DepthBand.SURFACE:
                continue
            try:
                if int(band.value) <= int(DepthBand.PERISCOPE.value):
                    continue
            except Exception:
                continue
            # Compare current vs one-band-shallower expected damage.
            current_dmg = max(1, _power(vessel) - depth_difference(band, flagship_band))
            shallower_band = DepthBand(int(band.value) - 1)
            new_dmg = max(1, _power(vessel) - depth_difference(shallower_band, flagship_band))
            # Require at least one extra damage AND the vessel must be
            # tactically useful (not a blocker we want to keep deep).
            if new_dmg > current_dmg and _power(vessel) >= 2 and _is_ready_to_attack(vessel):
                return SurfaceVessel(vessel_id=vessel.id)
        return None

    def _medium_pick_dive(self, state: GameState, player: 'Player',
                          own_vessels: list['GameObject']) -> Optional[Dive]:
        """Dive an undetected Vessel for stealth — but only when it actually helps.

        Diving past the opposing Flagship's depth costs the vessel 1 attack
        damage per band of separation (depth-modifier rule §5) without any
        compensating stealth benefit, since detection cost flattens at MID.
        Without this guard, the picker dives PERISCOPE→MID and the surface
        picker promptly surfaces back, burning 1 Sonar/turn forever.
        """
        if int(getattr(player, "sc", 0)) < 1:
            return None
        # Optimal attack depth = opposing flagship's band (default PERISCOPE).
        opp = _other_player(state, getattr(player, "id", None))
        opp_flag = get_flagship(state, opp) if opp else None
        flagship_band = (
            opp_flag.state.depth_band if (opp_flag and opp_flag.state.depth_band)
            else DepthBand.PERISCOPE
        )
        flagship_v = int(flagship_band.value)
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
                # Don't dive past the flagship band — losing attack damage
                # for no stealth gain. (Detection cost flattens MID==PERISCOPE.)
                if int(band.value) >= flagship_v:
                    continue
            except Exception:
                continue
            return Dive(vessel_id=vessel.id)
        return None

    def _medium_pick_attach(self, state: GameState, hand: list['GameObject'],
                            own_vessels: list['GameObject'],
                            player: 'Player') -> Optional[ManeuverAction]:
        """Attach a Crew/Weapon from hand to the best un-attached host.

        Heuristic (per ai-extension prompt):
          - Skip if the player has no non-Flagship Vessel.
          - Prefer un-attached Vessels (don't double-stack a single host).
          - For Crew with a power_mod or toughness_mod, prefer engaged
            Vessels (taking damage or already attacking) so the boost
            actually matters this turn.
          - Always pick the highest-power un-attached host as a fallback.
          - Skip if cost can't be paid.
        """
        # Find affordable Crew / Weapon cards in hand.
        affordable_crew: list['GameObject'] = []
        affordable_weapons: list['GameObject'] = []
        for card in hand:
            types = card.characteristics.types
            if not _can_afford(player, *_parse_charge_cost(card)):
                continue
            if CardType.DEPTHS_CREW in types:
                affordable_crew.append(card)
            elif CardType.DEPTHS_WEAPON in types:
                affordable_weapons.append(card)
        if not affordable_crew and not affordable_weapons:
            return None

        # Identify candidate hosts (non-Flagship Vessels).
        non_fs = [v for v in own_vessels if "Flagship" not in v.characteristics.subtypes]
        if not non_fs:
            return None

        un_attached = [v for v in non_fs if _is_unattached_vessel(v)]
        host_pool = un_attached or non_fs  # fall back to attached hosts only if all are taken

        # Generic best-power host.
        best_host = max(host_pool, key=lambda v: (_power(v), _hull(v)))

        # For each Crew with stat boosts, prefer an engaged host.
        if affordable_crew:
            engaged = [v for v in host_pool if _is_engaged(v)]
            for crew in affordable_crew:
                # Crew with stat boosts → prefer engaged. Helper detection:
                # a setup function whose card_def text mentions +/- pump.
                cd = getattr(crew, "card_def", None)
                text = ""
                if cd is not None:
                    text = (cd.text or "").lower()
                wants_engaged = any(tok in text for tok in ("+1/", "+2/", "/+1", "/+2", "first strike", "haste"))
                target_host = (
                    max(engaged, key=lambda v: (_power(v), _hull(v)))
                    if (wants_engaged and engaged) else best_host
                )
                return AttachCrew(crew_id=crew.id, vessel_id=target_host.id)

        # Weapons: pick the highest-power un-attached host.
        if affordable_weapons:
            return AttachWeapon(weapon_id=affordable_weapons[0].id, vessel_id=best_host.id)
        return None

    def _medium_pick_mine(self, state: GameState, hand: list['GameObject'],
                          player_id: str, player: 'Player') -> Optional[LayMine]:
        """Lay a Mine where the most opposing Vessels currently sit (or are
        likely to dive to). Defaults per ai-extension prompt:

          - PERISCOPE if the opponent has surface vessels (they'll dive
            through PERISCOPE first).
          - MID otherwise.
          - Cards may carry a ``depths_default_depth`` attribute on
            CardDefinition — honour that as a final fallback.
        """
        opp = _other_player(state, player_id)
        opp_vessels = _opp_vessels(state, player_id) if opp else []

        # Compute opponent vessel distribution by band.
        band_counts: dict['DepthBand', int] = {}
        for v in opp_vessels:
            if v.state.depth_band is not None:
                band_counts[v.state.depth_band] = band_counts.get(v.state.depth_band, 0) + 1

        # Choose the band where opp currently has the most Vessels.
        target_band: Optional['DepthBand'] = None
        if band_counts:
            target_band = max(band_counts.items(), key=lambda x: x[1])[0]
        elif any(v.state.depth_band == DepthBand.SURFACE for v in opp_vessels):
            # Opp has surface vessels → they'll likely dive through PERISCOPE.
            target_band = DepthBand.PERISCOPE
        else:
            # No useful information; default to MID per the prompt.
            target_band = DepthBand.MID

        for card in hand:
            if CardType.DEPTHS_MINE not in card.characteristics.types:
                continue
            if not _can_afford(player, *_parse_charge_cost(card)):
                continue
            # Honour the card's printed default depth as a cheaper fallback
            # when our heuristic is uninformative (no opp vessels visible).
            if not band_counts and not opp_vessels:
                card_default = getattr(getattr(card, "card_def", None),
                                       "depths_default_depth", None)
                if card_default is not None:
                    target_band = card_default
            return LayMine(card_id=card.id, depth_band=target_band)
        return None

    def _medium_pick_activate(self, state: GameState, player_id: str,
                              own_vessels: list['GameObject']) -> Optional[ActivateAbility]:
        """Activate a payable activated ability on a controlled permanent.

        Priority (per ai-extension prompt):
          1. Damage abilities — target the lowest-hull opposing Vessel.
          2. Untap / draw / utility — for tempo.
          3. Other — only if cheap.

        Skips abilities that can't pay their cost, are once-per-turn already
        spent, or are once-per-game and already activated.
        """
        player = state.players.get(player_id)
        if player is None:
            return None

        # Also include Doctrine permanents (controlled enchantments with
        # activated abilities) — Battery Reroute lives there, not on a Vessel.
        bf = _battlefield(state)
        candidates: list['GameObject'] = list(own_vessels)
        if bf is not None:
            for oid in bf.objects:
                obj = state.objects.get(oid)
                if obj is None or obj.controller != player_id or obj in own_vessels:
                    continue
                if getattr(obj.state, "activated_abilities", None):
                    candidates.append(obj)

        # AI-EXTENSION TODO (engine bug):
        # ``src.engine.depths.activate_ability`` reads ``ability.cost`` and
        # ``ability.effect`` but the ``ActivatedAbility`` dataclass uses
        # ``cost_text`` / ``effect_fn``. Until that handler is fixed,
        # activations succeed but pay no charge cost and run no effect. The
        # AI still picks them so the action surface is exercised; once the
        # engine bug is fixed nothing here needs to change.

        # Score every legal activation; pick the highest-scoring.
        best: Optional[tuple[float, ActivateAbility]] = None
        opp = _other_player(state, player_id)
        opp_vessels_sorted = (
            sorted(_opp_vessels(state, player_id), key=lambda v: _hull(v))
            if opp else []
        )
        opp_flagship = get_flagship(state, opp) if opp else None

        for src in candidates:
            abilities = getattr(src.state, "activated_abilities", None) or []
            for idx, ability in enumerate(abilities):
                if not _ability_can_activate(ability, src, state):
                    continue
                cost = _ability_cost(ability)
                if cost:
                    cs = _parse_charge_cost_str(cost)
                    if cs is None or not _can_afford(player, *cs):
                        continue

                target_id: Optional[str] = None
                score = 0.0
                if _ability_emits_damage(ability):
                    # Target the lowest-hull opposing Vessel; if none, Flagship.
                    pool = [v for v in opp_vessels_sorted if _hull(v) > 0]
                    if pool:
                        target_id = pool[0].id
                    elif opp_flagship is not None:
                        target_id = opp_flagship.id
                    score = 3.0  # damage > everything else
                elif _ability_is_utility_draw(ability):
                    score = 2.0
                else:
                    score = 1.0
                if best is None or score > best[0]:
                    best = (score, ActivateAbility(
                        vessel_id=src.id,
                        ability_idx=idx,
                        target=target_id,
                    ))
        return best[1] if best else None

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

    def _medium_pick_doctrine(self, state: GameState, hand: list['GameObject'],
                              player_id: str, player: 'Player') -> Optional[CastAction]:
        """Cast a Doctrine (ENCHANTMENT-typed persistent effect) if affordable.

        Doctrines route through the same DEPTHS_CAST_SPELL action as Actions
        (cast_spell handles all three of INSTANT / SORCERY / ENCHANTMENT and
        moves enchantments to BATTLEFIELD). The previous picker filtered out
        ENCHANTMENT, so the AI never deployed any anthem-style Doctrines like
        Wolfpack Doctrine or Iron Discipline.
        """
        for card in hand:
            types = card.characteristics.types
            if CardType.ENCHANTMENT not in types:
                continue
            # Skip non-Doctrine enchantments if any sneak in (defensive).
            if "Doctrine" not in card.characteristics.subtypes:
                continue
            if not _can_afford(player, *_parse_charge_cost(card)):
                continue
            return CastAction(card_id=card.id, target=None)
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

    def _recent_damage_taken(self, defender_id: str) -> int:
        """How much hull was lost across the tracked window (iter-5 patch).

        Returns 0 if we don't yet have two history points to compare.
        """
        history = self._flagship_hull_history.get(defender_id) or []
        if len(history) < 2:
            return 0
        # Loss = oldest_hull - newest_hull (positive means we took damage).
        oldest_hull = history[0][1]
        newest_hull = history[-1][1]
        return max(0, int(oldest_hull) - int(newest_hull))

    def _medium_detections(self, state: GameState, defender_id: str,
                           attackers: list[AttackerSpec]) -> dict[str, int]:
        """
        §8 Medium: spend Sonar on attackers whose unintercepted damage
        would push Flagship below ``hull - lethal_buffer``.

        Iter-5 patch (cumulative-damage escalation): also escalates when
        the defender has taken ``MEDIUM_RECENT_DAMAGE_TRIGGER`` or more
        hull damage in the last ``MEDIUM_RECENT_DAMAGE_WINDOW`` turns.
        Without this, a 4-damage-per-turn chip stream stays below the
        single-swing lethal projection and goes uncontested forever
        (Pilot B iter-3 + iter-4 evidence).
        """
        player = state.players.get(defender_id)
        if player is None:
            return {}
        budget = int(getattr(player, "sc", 0))
        flagship_hull = _flagship_buffer(state, defender_id)
        if budget <= 0:
            return {}

        # Update the per-defender hull history (iter-5 cumulative tracking).
        turn = int(getattr(state, "turn_number", 0) or 0)
        history = self._flagship_hull_history.setdefault(defender_id, [])
        if not history or history[-1][0] != turn:
            history.append((turn, flagship_hull))
            # Prune entries older than the window.
            cutoff = turn - MEDIUM_RECENT_DAMAGE_WINDOW
            self._flagship_hull_history[defender_id] = [
                (t, h) for (t, h) in history if t >= cutoff
            ]
        recent_damage = self._recent_damage_taken(defender_id)

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
            # Pass state so PT_MODIFICATION pumps (Saturation Strike, anthems)
            # are reflected in the danger projection. Iter-2 fix.
            danger = _depth_modifier_damage(attacker, target, state) if target_is_flagship else 0
            ranked.append((danger, spec))
        ranked.sort(key=lambda x: x[0], reverse=True)

        out: dict[str, int] = {}
        cumulative_unintercepted = sum(d for d, _ in ranked)
        chip_stream = recent_damage >= MEDIUM_RECENT_DAMAGE_TRIGGER
        # iter-5: when recent damage trips the threshold, project the chip
        # stream forward and add the recent damage to this cumulative projection.
        if chip_stream:
            cumulative_unintercepted += recent_damage
        # iter-6 chip-stream force-detect: low-power drone swarms (each 1-2 dmg)
        # have per-attacker danger too low to trip the lethal-buffer threshold
        # even with recent_damage added (e.g. 4 drones × 1 = 4, plus recent=4 →
        # cumulative=8 vs flagship_hull-3=22 → loop never fires). When a chip
        # stream is confirmed, force-detect the top MEDIUM_CHIP_FORCE_DETECT
        # undetected attackers BEFORE the lethal-projection loop so the AI slows
        # the bleed without waiting for a near-death projection.
        if chip_stream and ranked and budget > 0:
            force_n = min(MEDIUM_CHIP_FORCE_DETECT, len(ranked))
            for _ in range(force_n):
                if not ranked or budget <= 0:
                    break
                danger, spec = ranked[0]
                attacker = state.objects.get(spec.vessel_id)
                if attacker is None:
                    ranked.pop(0)
                    continue
                cost = detection_cost(state, attacker)
                if cost <= budget:
                    out[spec.vessel_id] = cost
                    budget -= cost
                    cumulative_unintercepted -= danger
                ranked.pop(0)
        # If unintercepted damage > flagship_hull - lethal_buffer, continue
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
            # Pass state — runtime pumps must be reflected in interceptor triage.
            threats.append((_depth_modifier_damage(attacker, target, state), spec))
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
            # Pass state on attacker reads so PT pumps register; blocker stats
            # are our own so printed power is fine for relative ordering.
            attacker_pwr = _power(attacker, state)
            def block_score(v: 'GameObject') -> tuple[int, int, int]:
                survives = 1 if attacker_pwr < _hull(v) else 0
                kills = 1 if _power(v) >= _hull(attacker) else 0
                # Prefer cheapest hulls when no good option exists.
                value_lost = -(_power(v) + _hull(v)) if not survives else 0
                return (kills + survives, value_lost, _power(v))
            blocker = max(candidates, key=block_score)
            # Don't trade if we lose value AND don't kill (chump only when threatened lethally).
            survives = attacker_pwr < _hull(blocker)
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
        if not self._note_action_call(state, player_id):
            return Done()
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
            # Heuristic prior: actions whose effect the simulator can't model
            # (Attach / LayMine / ActivateAbility / CastAction) get a small
            # positive bonus so they aren't always dominated by Done. The
            # simulator only sees the cost paid (negative delta), so without
            # a prior these actions are never picked. AI-EXTENSION TODO:
            # remove this prior once _simulate_action models attach P/T grant
            # and ability effects properly.
            prior = 0.0
            if isinstance(action, (AttachCrew, AttachWeapon)):
                prior = 1.5  # roughly 1 board-value point + epsilon
            elif isinstance(action, LayMine):
                prior = 1.0  # mines aren't on our side of the board, but they soak
            elif isinstance(action, ActivateAbility):
                prior = 1.2  # most depths abilities are tempo positive
            elif isinstance(action, CastAction):
                prior = 0.8
            elif isinstance(action, SurfaceVessel):
                prior = 0.3  # free move; let the value function decide
            scored.append((delta + prior, action))

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

        AI-EXTENSION TODO (engine bug, NOT in scope for this fix):
          ``GameState`` carries a back-reference to ``Game`` via
          ``state._game``, and ``Game.state`` points back to the same
          GameState. ``copy.deepcopy(state)`` therefore hits
          ``RecursionError: maximum recursion depth exceeded`` once a
          turn manager is wired in. This silently disables the Hard
          tier's lookahead in actual play — the catch below converts
          the recursion into ``None``, which forces ``_hard_maneuver``
          to fall through to ``Done``. Fix: either snip ``state._game``
          out of the deepcopy via a ``__deepcopy__`` override on
          ``GameState`` (cleanest), or build a shallow simulator that
          tracks just the score inputs (flagship hull / board value /
          charge totals) without copying the full state graph.
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
        # Non-Flagship hosts only — engine-side ``attach`` runs cost checks
        # but Flagship-attach is generally non-productive (Flagship can't
        # surface/dive, and equipment like Crush Capacitor wants a mover).
        non_fs_hosts = [v for v in own_vessels if "Flagship" not in v.characteristics.subtypes]
        un_attached_hosts = [v for v in non_fs_hosts if _is_unattached_vessel(v)]

        for card in hand:
            tc, sc = _parse_charge_cost(card)
            if not _can_afford(player, tc, sc):
                continue
            types = card.characteristics.types
            if CardType.DEPTHS_VESSEL in types:
                actions.append(DeployVessel(card_id=card.id))
            elif CardType.DEPTHS_MINE in types:
                # Honour the mine's printed default_depth, fall back to PERISCOPE.
                cd = getattr(card, "card_def", None)
                default = getattr(cd, "depths_default_depth", None) if cd else None
                actions.append(LayMine(card_id=card.id,
                                       depth_band=default or DepthBand.PERISCOPE))
            elif CardType.DEPTHS_CREW in types and non_fs_hosts:
                for host in (un_attached_hosts or non_fs_hosts):
                    actions.append(AttachCrew(crew_id=card.id, vessel_id=host.id))
            elif CardType.DEPTHS_WEAPON in types and non_fs_hosts:
                for host in (un_attached_hosts or non_fs_hosts):
                    actions.append(AttachWeapon(weapon_id=card.id, vessel_id=host.id))
            elif CardType.INSTANT in types or CardType.SORCERY in types:
                actions.append(CastAction(card_id=card.id))

        for vessel in own_vessels:
            if "Flagship" not in vessel.characteristics.subtypes:
                band = vessel.state.depth_band
                if band is not None:
                    try:
                        if int(band.value) < int(DepthBand.DEEP.value) and int(getattr(player, "sc", 0)) >= 1:
                            actions.append(Dive(vessel_id=vessel.id))
                        if int(band.value) > int(DepthBand.SURFACE.value):
                            actions.append(SurfaceVessel(vessel_id=vessel.id))
                    except Exception:
                        pass

        # Activated abilities — scan ALL controlled battlefield permanents
        # (Vessels AND Doctrines like Battery Reroute). Skip abilities the
        # player can't legally activate this turn (cost / once-per / pre).
        bf = _battlefield(state)
        scanned: set[str] = set()
        scan_pool = list(own_vessels)
        if bf is not None:
            for oid in bf.objects:
                if oid in scanned:
                    continue
                obj = state.objects.get(oid)
                if obj is None or obj.controller != player_id:
                    continue
                if obj not in scan_pool:
                    scan_pool.append(obj)
                scanned.add(oid)
        for src in scan_pool:
            abilities = getattr(src.state, "activated_abilities", None) or []
            for idx, ability in enumerate(abilities):
                if not _ability_can_activate(ability, src, state):
                    continue
                cost = _ability_cost(ability)
                if cost:
                    parsed = _parse_charge_cost_str(cost)
                    if parsed is None or not _can_afford(player, *parsed):
                        continue
                actions.append(ActivateAbility(vessel_id=src.id, ability_idx=idx))

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
