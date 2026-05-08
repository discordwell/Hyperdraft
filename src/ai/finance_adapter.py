"""
Finance AI Adapter — FinanceAIAdapter

Heuristic AI for the Finance TCG engine. Three difficulty tiers
(``easy`` / ``medium`` / ``hard``) share a single legal-move generator
and differ only in selection policy. See ``docs/games/finance.md`` §8
for the design statement.

The adapter is intentionally **stateless** between calls — every method
reads the current ``GameState`` and returns a fresh decision. The turn
manager (``src/engine/finance_turn.py``) calls one method per phase:

  * ``mulligan_decision(state, player_id, hand) -> bool``
  * ``choose_play_action(state, player_id) -> dict | None``
        (loop until ``{"type": "end_phase"}`` is returned)
  * ``choose_attackers(state, player_id) -> list[str]``
  * ``choose_blockers(state, attacker_ids, player_id) -> dict[str, str]``
  * ``choose_discard(state, player_id, hand) -> str``

Imports from sibling Finance modules are wrapped in ``try/except`` so
this file remains importable while the other three parallel agents are
still landing their changes — the adapter falls back to inline
definitions where possible.

No LLM hooks, no MCTS, no neural eval. Matches the docstring and
structural style of ``src/ai/depths_adapter.py``.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from src.engine.types import GameState, ZoneType

if TYPE_CHECKING:
    from src.engine.types import GameObject, Player


# =============================================================================
# Imports from Finance CardType symbols (with safe fallbacks)
# =============================================================================
#
# Agent 1 owns types.py and adds FIN_* CardType members. Import them here with
# a graceful fallback so this file compiles even if Agent 1 hasn't landed yet.
# Once the real symbols exist they take precedence; the fallback sentinels
# become dead code.
# =============================================================================

try:
    from src.engine.types import CardType
    FIN_TRADER = CardType.FIN_TRADER
    FIN_ORDER = CardType.FIN_ORDER
    FIN_STRATEGY = CardType.FIN_STRATEGY
    FIN_ASSET = CardType.FIN_ASSET
    FIN_DERIVATIVE = CardType.FIN_DERIVATIVE
    FIN_STRUCTURE = CardType.FIN_STRUCTURE
    _HAS_FIN_TYPES = True
except AttributeError:  # pragma: no cover — exercised only during parallel scaffold
    FIN_TRADER = None      # TODO: needs FIN_TRADER from types.py (Agent 1)
    FIN_ORDER = None
    FIN_STRATEGY = None
    FIN_ASSET = None
    FIN_DERIVATIVE = None
    FIN_STRUCTURE = None
    _HAS_FIN_TYPES = False


# =============================================================================
# FinanceAIBias — tunable weights for variant/tournament loop
# =============================================================================

@dataclass
class FinanceAIBias:
    """
    Tunable weight dataclass for ``FinanceAIAdapter``.

    All weights are exposed as public fields so the variant tournament
    loop can sweep over them without subclassing. The defaults reproduce
    the §8 Hard-tier value function exactly.
    """
    # V(state) = capital_weight * cap_diff
    #          + board_weight   * board_diff
    #          + liquidity_weight * liq_diff
    capital_weight: float = 0.5
    board_weight: float = 0.3
    liquidity_weight: float = 0.2

    # Hard combat: minimum V-delta improvement required to commit attackers
    attack_threshold: float = 0.0

    # Medium: Capital Reserve threshold below which AI holds Orders defensively
    # in the Dark Pool rather than playing them immediately (§8 Medium).
    hold_order_threshold: int = 10


# =============================================================================
# Internal free helpers (shared by all tiers)
# =============================================================================

def _hand_zone(state: GameState, player_id: str) -> Optional[Any]:
    """Return the hand zone for ``player_id``; tries ``hand_<pid>`` first."""
    return state.zones.get(f"hand_{player_id}") or state.zones.get("hand")


def _battlefield(state: GameState) -> Optional[Any]:
    return state.zones.get("battlefield")


def _hand_cards(state: GameState, player_id: str) -> list["GameObject"]:
    zone = _hand_zone(state, player_id)
    if not zone:
        return []
    out: list["GameObject"] = []
    for oid in zone.objects:
        obj = state.objects.get(oid)
        if obj is not None:
            out.append(obj)
    return out


def _is_trader(obj: "GameObject") -> bool:
    """True if ``obj`` has the FIN_TRADER CardType."""
    if FIN_TRADER is None:
        return False
    try:
        return FIN_TRADER in obj.characteristics.types
    except (AttributeError, TypeError):
        return False


def _is_order(obj: "GameObject") -> bool:
    if FIN_ORDER is None:
        return False
    try:
        return FIN_ORDER in obj.characteristics.types
    except (AttributeError, TypeError):
        return False


def _has_alpha_strike(obj: "GameObject") -> bool:
    """True if the card's text mentions Alpha Strike (heuristic, no engine tag).

    Iter-1: only the first declared attacker gets the +3 alpha bonus
    (engine bug — see ``docs/strategy/finance.md``). The HF heuristic
    uses this to refuse multi-attack with Alpha Strikers.
    """
    try:
        text = (getattr(obj.characteristics, "text", None) or
                getattr(obj, "text", None) or "")
        return "Alpha Strike" in str(text)
    except (AttributeError, TypeError):
        return False


def _card_name(obj: "GameObject") -> str:
    """Best-effort card name lookup for name-based heuristics."""
    try:
        return str(getattr(obj.characteristics, "name", None) or
                   getattr(obj, "name", "") or "")
    except (AttributeError, TypeError):
        return ""


def _mana_cost(obj: "GameObject") -> int:
    """Return the numeric Liquidity cost for a card object."""
    raw = getattr(obj.characteristics, "mana_cost_value", None)
    if raw is not None:
        try:
            return max(0, int(raw))
        except (ValueError, TypeError):
            pass
    # Fallback: parse "{N}" from mana_cost string (Hearthstone pattern).
    mana_str = getattr(obj.characteristics, "mana_cost", None) or ""
    import re
    nums = re.findall(r"\{(\d+)\}", str(mana_str))
    if nums:
        return max(0, sum(int(n) for n in nums))
    return 0


def _can_afford(state: GameState, player_id: str, card_id: str) -> bool:
    """True if the player has enough Liquidity to play this card."""
    player = state.players.get(player_id)
    if not player:
        return False
    obj = state.objects.get(card_id)
    if not obj:
        return False
    cost = _mana_cost(obj)
    available = int(getattr(player, "mana_crystals_available", 0) or 0)
    return available >= cost


def _own_traders(state: GameState, player_id: str) -> list["GameObject"]:
    bf = _battlefield(state)
    if not bf:
        return []
    return [
        obj for oid in bf.objects
        if (obj := state.objects.get(oid)) is not None
        and obj.controller == player_id
        and _is_trader(obj)
    ]


def _opp_traders(state: GameState, player_id: str) -> list["GameObject"]:
    opp = _other_player(state, player_id)
    if opp is None:
        return []
    return _own_traders(state, opp)


def _other_player(state: GameState, player_id: str) -> Optional[str]:
    return next((pid for pid in state.players if pid != player_id), None)


def _power(obj: "GameObject") -> int:
    return int(obj.characteristics.power or 0)


def _toughness(obj: "GameObject") -> int:
    return int(obj.characteristics.toughness or 0)


def _remaining_defense(obj: "GameObject") -> int:
    """Defense Rating minus accumulated damage (≥ 0)."""
    base = _toughness(obj)
    dmg = int(getattr(obj.state, "damage", 0) or 0)
    return max(0, base - dmg)


def _card_total_value(obj: "GameObject") -> float:
    """Flat value heuristic: cost + power + toughness (for discard ordering)."""
    return float(_mana_cost(obj) + _power(obj) + _toughness(obj))


def _trader_score(obj: "GameObject") -> float:
    """§8 Medium: (Aggression + Defense Rating) / cost, used for play ordering."""
    cost = max(1, _mana_cost(obj))
    return float(_power(obj) + _toughness(obj)) / float(cost)


def _legal_attackers(state: GameState, player_id: str) -> list["GameObject"]:
    """Traders that may legally attack: untapped, no summoning sickness."""
    traders = _own_traders(state, player_id)
    result = []
    for obj in traders:
        if getattr(obj.state, "tapped", False):
            continue
        if getattr(obj.state, "summoning_sickness", False):
            continue
        result.append(obj)
    return result


# =============================================================================
# Iter-2 patch: Leverage tax projection (Derivatives self-loss prevention)
# =============================================================================
#
# Iter-2 lesson (Pilot A loss vs Dark Arbitrage): stacking 4+ Leverage Traders
# without a counter-removal source on board is a guaranteed loss in 2-3 turns.
# Σleverage damage fires at controller's MARKET_CLOSE. Pilot A went 12 → -4
# in one MC with 5 Leverage Traders deployed (predicted 9 tick, observed 16 —
# tick-doubling bug suspected, see strategy doc bug #10).
#
# This helper sums Leverage counters across the player's Traders and projects
# the next MC tick. Used by _filter_trap_cards / _hard_play_action to refuse
# to deploy a new Leverage Trader if doing so would be lethal-range.
# =============================================================================

# Card names that REMOVE Leverage counters (deck-wide safety valves).
# When any of these is on board (or attached), tick projection can be eased.
_LEVERAGE_COUNTER_REMOVERS = frozenset({
    "Theta Decay Trader",          # pre-MC free remove from self
    "The Black-Scholes Model",     # pay-1 trigger, removes from any
    "Theta Decay Collar",          # attach Derivative, removes counters
    "Gamma Scalper",               # once-per-game lethal-tick safety valve
})


def _leverage_count(obj: "GameObject") -> int:
    """Return the number of Leverage counters on this object (0 if none)."""
    try:
        counters = getattr(obj.state, "counters", {}) or {}
        return int(counters.get("leverage", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def _has_leverage_remover(state: GameState, player_id: str) -> bool:
    """True if at least one Leverage-counter-removal source is in play for this player."""
    bf = _battlefield(state)
    if not bf:
        return False
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.controller != player_id:
            continue
        if _card_name(obj) in _LEVERAGE_COUNTER_REMOVERS:
            return True
    return False


def _expected_leverage_tax(state: GameState, player_id: str) -> int:
    """Sum of Leverage counters across player's own Traders.

    This projects the controller's next MARKET_CLOSE tick damage assuming
    no counter removal occurs. Iter-2 observation: actual tick exceeded
    Σleverage by ~1.7× — a known engine bug. Callers that need a
    safety-margin projection should multiply by ~1.7 until the bug is fixed.
    """
    total = 0
    for obj in _own_traders(state, player_id):
        total += _leverage_count(obj)
    return total


def _is_dark_pool_order(obj: "GameObject") -> bool:
    """Iter-3: True if the card has the `_dark_pool` flag set on its card_def.

    Engine bug 15 (`_play_card_action` lacks `_dark_pool` branch): all DP
    Orders resolve straight to GY without staging into the Dark Pool slot.
    Their `dark_effect_fn` never registers. Until the staging path is
    wired, casting a DP Order is a strict tempo loss — the card disappears
    for zero effect at full mana cost. The Hard tier filter uses this
    helper to refuse DP Orders.
    """
    try:
        cd = getattr(obj, "card_def", None) or getattr(obj.characteristics, "card_def", None)
        return bool(getattr(cd, "_dark_pool", False))
    except (AttributeError, TypeError):
        return False


def _card_text_leverage_n(obj: "GameObject") -> int:
    """Best-effort: detect Leverage N from card text. Returns 0 if not a Leverage Trader."""
    try:
        text = (getattr(obj.characteristics, "text", None) or
                getattr(obj, "text", None) or "")
        text_str = str(text)
        if "Leverage" not in text_str:
            return 0
        import re
        m = re.search(r"Leverage\s+(\d+)", text_str)
        if m:
            return int(m.group(1))
        return 0
    except (AttributeError, TypeError, ValueError):
        return 0


def _board_value(state: GameState, player_id: str) -> float:
    """Sum of (Aggression + Defense Rating) for all Traders on the Trading Floor."""
    total = 0.0
    for obj in _own_traders(state, player_id):
        total += float(_power(obj) + _toughness(obj))
    return total


def _eval_state(state: GameState, player_id: str, bias: FinanceAIBias) -> float:
    """
    §8 Hard value function:
      bias.capital_weight   * capital_reserve_diff
    + bias.board_weight     * board_value_diff
    + bias.liquidity_weight * liquidity_economy_diff
    Higher is better for ``player_id``.
    """
    opp = _other_player(state, player_id)
    player = state.players.get(player_id)
    opponent = state.players.get(opp) if opp else None
    if not player or not opponent:
        return 0.0

    cap_diff = (float(player.life) - float(opponent.life)) / 30.0
    board_diff = (_board_value(state, player_id) - _board_value(state, opp)) / 20.0
    liq_diff = (
        float(getattr(player, "mana_crystals_available", 0) or 0)
        - float(getattr(opponent, "mana_crystals_available", 0) or 0)
    ) / 10.0

    return (
        bias.capital_weight * cap_diff
        + bias.board_weight * board_diff
        + bias.liquidity_weight * liq_diff
    )


# =============================================================================
# FinanceAIAdapter
# =============================================================================

class FinanceAIAdapter:
    """
    Three-tier heuristic adapter — see ``docs/games/finance.md`` §8.

    :param difficulty: ``"easy"``, ``"medium"``, or ``"hard"``
    :param bias: ``FinanceAIBias`` instance for variant/tournament tuning
    :param rng: optional ``random.Random`` for deterministic tests
    """

    DIFFICULTIES = ("easy", "medium", "hard")

    def __init__(
        self,
        difficulty: str = "medium",
        bias: Optional[FinanceAIBias] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        diff = (difficulty or "medium").lower()
        if diff not in self.DIFFICULTIES:
            diff = "medium"
        self.difficulty = diff
        self.bias = bias or FinanceAIBias()
        self.rng = rng or random.Random()

    # ─── Mulligan ──────────────────────────────────────────────────────────

    def mulligan_decision(
        self,
        state: GameState,
        player_id: str,
        hand: Optional[list[str]] = None,
    ) -> bool:
        """
        Return True to keep the opening hand, False to mulligan.

        - Easy: always keep.
        - Medium: keep if hand has ≥ 1 card with cost ≤ 2 (playable on turn 2).
        - Hard: keep if hand has a playable curve — cards at costs 1, 2, 3 or
          any two distinct costs ≤ 3.
        """
        # Resolve hand to GameObjects if we were given IDs.
        objs: list["GameObject"] = []
        if hand is None:
            objs = _hand_cards(state, player_id)
        else:
            for item in hand:
                if isinstance(item, str):
                    obj = state.objects.get(item)
                    if obj is not None:
                        objs.append(obj)
                else:
                    objs.append(item)  # already a GameObject

        if self.difficulty == "easy":
            return True

        costs = [_mana_cost(c) for c in objs]

        if self.difficulty == "medium":
            return any(c <= 2 for c in costs)

        # Hard: keep if the hand contains a playable curve.
        # "Playable curve" = two distinct costs among {1, 2, 3}.
        low_costs = set(c for c in costs if c <= 3)
        return len(low_costs) >= 2

    # ─── Play action (called in a loop by turn manager) ────────────────────

    def choose_play_action(
        self,
        state: GameState,
        player_id: str,
    ) -> Optional[dict]:
        """
        Return one play action or ``{"type": "end_phase"}``.

        The turn manager calls this in a loop until ``end_phase`` is returned.
        Each call returns at most ONE card to play (or end_phase / None).

        Return shape:
          ``{"type": "play_card", "card_id": <str>, "targets": [<str>, ...]}``
          or
          ``{"type": "end_phase"}``
        """
        if self.difficulty == "easy":
            return self._easy_play_action(state, player_id)
        if self.difficulty == "medium":
            return self._medium_play_action(state, player_id)
        return self._hard_play_action(state, player_id)

    # ─── Attacker selection ────────────────────────────────────────────────

    def choose_attackers(
        self,
        state: GameState,
        player_id: str,
    ) -> list[str]:
        """
        Return a list of Trader object IDs to declare as attackers.

        - Easy: all legal attackers.
        - Medium: attack with Trader X only if its Aggression exceeds the
          minimum opposing blocker's Defense Rating, or if unblocked damage
          would be lethal to the opponent's Capital Reserve.
        - Hard: enumerate attack subsets, simulate optimal opponent blocking,
          pick subset maximising expected V delta using ``_eval_state``.
        """
        if self.difficulty == "easy":
            return self._easy_attackers(state, player_id)
        if self.difficulty == "medium":
            return self._medium_attackers(state, player_id)
        return self._hard_attackers(state, player_id)

    # ─── Blocker selection ─────────────────────────────────────────────────

    def choose_blockers(
        self,
        state: GameState,
        attacker_ids: list[str],
        player_id: str,
    ) -> dict[str, str]:
        """
        Return ``{attacker_id: blocker_id}`` blocking assignments.

        - Easy: random legal assignments.
        - Medium: minimise total damage taken; prefer the smallest Trader
          whose Defense Rating > attacker's Aggression (survival priority).
        - Hard: try all legal assignments, pick the one minimising V loss
          for the defending player.
        """
        if not attacker_ids:
            return {}
        if self.difficulty == "easy":
            return self._easy_blockers(state, attacker_ids, player_id)
        if self.difficulty == "medium":
            return self._medium_blockers(state, attacker_ids, player_id)
        return self._hard_blockers(state, attacker_ids, player_id)

    # ─── Discard ───────────────────────────────────────────────────────────

    def choose_discard(
        self,
        state: GameState,
        player_id: str,
        hand: list[str],
    ) -> str:
        """
        Return the card ID to discard (Market Close hand-size trim).

        All tiers: discard the lowest-value card by ``_card_total_value``
        (cost + power + toughness for Traders; cost alone for other types).
        """
        objs: list[tuple[float, str]] = []
        for item in hand:
            cid = item if isinstance(item, str) else item.id
            obj = state.objects.get(cid)
            if obj is None:
                continue
            if _is_trader(obj):
                val = _card_total_value(obj)
            else:
                val = float(_mana_cost(obj))
            objs.append((val, cid))
        if not objs:
            return hand[0] if hand else ""
        objs.sort(key=lambda x: x[0])
        return objs[0][1]

    # ==========================================================================
    # EASY tier — random legal plays, attack with everything
    # ==========================================================================

    def _easy_play_action(self, state: GameState, player_id: str) -> dict:
        """Random affordable card from hand; if none, end phase."""
        hand = _hand_cards(state, player_id)
        affordable = [c for c in hand if _can_afford(state, player_id, c.id)]
        if not affordable:
            return {"type": "end_phase"}
        pick = self.rng.choice(affordable)
        return {"type": "play_card", "card_id": pick.id, "targets": []}

    def _easy_attackers(self, state: GameState, player_id: str) -> list[str]:
        """Attack with every legal attacker (§8 Easy)."""
        return [obj.id for obj in _legal_attackers(state, player_id)]

    def _easy_blockers(
        self,
        state: GameState,
        attacker_ids: list[str],
        player_id: str,
    ) -> dict[str, str]:
        """Random one-to-one blocking assignments from available Traders."""
        available = [
            obj for obj in _own_traders(state, player_id)
            if not getattr(obj.state, "tapped", False)
            and obj.id not in attacker_ids  # friendly can't block own attacker
        ]
        self.rng.shuffle(available)
        assignments: dict[str, str] = {}
        used: set[str] = set()
        for atk_id in attacker_ids:
            for blocker in available:
                if blocker.id not in used:
                    assignments[atk_id] = blocker.id
                    used.add(blocker.id)
                    break
        return assignments

    # ==========================================================================
    # MEDIUM tier — greedy heuristic, no lookahead (§8 Medium)
    # ==========================================================================

    def _medium_play_action(self, state: GameState, player_id: str) -> dict:
        """
        Score cards by (Aggression + Defense Rating) / cost for Traders;
        flat cost score for other types. Play highest-scoring affordable card.
        If none playable, return end_phase.

        §8 Medium: place an Order in the Dark Pool rather than playing it
        immediately when the opponent's Capital Reserve ≤ ``hold_order_threshold``.
        """
        player = state.players.get(player_id)
        if not player:
            return {"type": "end_phase"}

        opp_id = _other_player(state, player_id)
        opp = state.players.get(opp_id) if opp_id else None
        opp_capital = float(getattr(opp, "life", 30)) if opp else 30.0

        hand = _hand_cards(state, player_id)
        candidates: list[tuple[float, "GameObject"]] = []

        for card in hand:
            if not _can_afford(state, player_id, card.id):
                continue
            if _is_trader(card):
                score = _trader_score(card)
            elif _is_order(card):
                # §8 Medium: hold Orders for Dark Pool when opp is low.
                if opp_capital <= float(self.bias.hold_order_threshold):
                    continue  # Don't play immediately — let turn mgr use dark pool
                score = float(_mana_cost(card))
            else:
                score = float(_mana_cost(card))
            candidates.append((score, card))

        if not candidates:
            return {"type": "end_phase"}

        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        return {"type": "play_card", "card_id": best.id, "targets": []}

    def _medium_attackers(self, state: GameState, player_id: str) -> list[str]:
        """
        Attack with Trader X only when profitable (§8 Medium):
          - X.Aggression > minimum opposing blocker's remaining Defense, OR
          - unblocked damage would be lethal to opponent's Capital Reserve.
        """
        opp_id = _other_player(state, player_id)
        opp = state.players.get(opp_id) if opp_id else None
        opp_capital = float(getattr(opp, "life", 30)) if opp else 30.0
        opp_traders = _opp_traders(state, player_id)

        # Minimum toughness on any opposing Trader still standing (∞ if none).
        min_opp_defense = (
            min(_remaining_defense(t) for t in opp_traders)
            if opp_traders
            else float("inf")
        )
        # Total unblocked damage if ALL legal attackers swing — used for lethal check.
        legal = _legal_attackers(state, player_id)
        attackers: list[str] = []

        for obj in legal:
            atk_power = _power(obj)
            # Would kill at least the smallest defender or threatens lethal.
            if atk_power > min_opp_defense:
                attackers.append(obj.id)
            elif atk_power >= opp_capital:
                attackers.append(obj.id)

        # Always swing if lethal is available even if above criteria missed it.
        if not attackers:
            total_dmg = sum(_power(obj) for obj in legal)
            if total_dmg >= opp_capital:
                attackers = [obj.id for obj in legal]

        return attackers

    def _medium_blockers(
        self,
        state: GameState,
        attacker_ids: list[str],
        player_id: str,
    ) -> dict[str, str]:
        """
        Assign blockers to minimise total damage taken (§8 Medium).

        Prefer the smallest Trader (by Defense Rating) that survives the
        trade (Defense Rating > attacker's Aggression). Fall back to any
        available blocker when no blocker survives.

        Iter-1 patch (FINA double-pilot, Quant pilot lesson):
        - When unblocked damage would drop us ≤ 8 capital, ALSO chump-
          block remaining attackers with the smallest available body to
          reduce face leakage. Trample overflow leaks 1-3 face per
          chump but that beats 5+ face unblocked.
        """
        available = [
            obj for obj in _own_traders(state, player_id)
            if not getattr(obj.state, "tapped", False)
            and obj.id not in attacker_ids
        ]
        assignments: dict[str, str] = {}
        used: set[str] = set()

        # Compute mandatory-block-mode: are we facing lethal-range damage?
        player = state.players.get(player_id)
        cur_life = int(getattr(player, "life", 30)) if player else 30
        unblocked_dmg = sum(
            _power(state.objects[aid]) for aid in attacker_ids
            if aid in state.objects
        )
        mandatory_block = (
            unblocked_dmg >= cur_life
            or cur_life - unblocked_dmg <= 8
        )

        # Sort attackers by Aggression descending (block the biggest threats first).
        sorted_atks = sorted(
            attacker_ids,
            key=lambda aid: _power(state.objects[aid]) if aid in state.objects else 0,
            reverse=True,
        )

        for atk_id in sorted_atks:
            atk_obj = state.objects.get(atk_id)
            if atk_obj is None:
                continue
            atk_power = _power(atk_obj)

            # Prefer smallest-defense blocker that survives.
            survivors = [
                b for b in available
                if b.id not in used and _remaining_defense(b) > atk_power
            ]
            if survivors:
                # Pick the one with the smallest remaining defense (least waste).
                blocker = min(survivors, key=_remaining_defense)
            elif mandatory_block:
                # No survivor but we're at lethal-range — chump with cheapest.
                remaining = [b for b in available if b.id not in used]
                if not remaining:
                    continue
                blocker = min(remaining, key=lambda b: _power(b) + _toughness(b))
            else:
                # No survivor and life is fine — only commit a blocker if
                # the trade kills attacker AND blocker has positive value.
                # Pilot B iter-1: chumping a 2/1 with a 1/2 leaks 2 face;
                # eat the chip when life > 8.
                continue

            assignments[atk_id] = blocker.id
            used.add(blocker.id)

        return assignments

    # ==========================================================================
    # HARD tier — 1-ply lookahead with FinanceAIBias value function (§8 Hard)
    # ==========================================================================
    #
    # The "simulate one action" step deep-copies state and approximates the
    # cost-payment + zone transition for a single play_card action. This is
    # the same pattern used in ``depths_adapter._simulate_action``.
    #
    # AI-EXTENSION TODO: ``copy.deepcopy(state)`` will hit RecursionError once
    # a back-reference to ``Game`` is added to ``GameState``. Fix identically to
    # the Depths adapter: add ``__deepcopy__`` to ``GameState`` or build a
    # shallow score-input simulator tracking only {life, board, mana} per player.
    # ==========================================================================

    def _hard_play_action(self, state: GameState, player_id: str) -> dict:
        """
        Generate all affordable cards, simulate V delta for each,
        return the play that maximises _eval_state delta.

        The turn manager calls this in a loop; each call returns ONE card.
        Returning end_phase when nothing improves V stops the loop.

        Iter-1 patches (FINA double-pilot game; both pilots flagged):
        - Filter out Liquidity Provision when at full mana (gains 0).
        - Filter out Speed Amplifier when no 3+ tough Trader exists
          on board (engine bug: orphans on attached Trader's death).
        - Filter out Tick Data Archive (engine bug: trigger flag never
          set; asset is currently dead).
        """
        hand = _hand_cards(state, player_id)
        affordable = [c for c in hand if _can_afford(state, player_id, c.id)]
        if not affordable:
            return {"type": "end_phase"}

        # Surgical name-based filters for known dead/trap cards.
        affordable = self._filter_trap_cards(state, player_id, affordable)
        if not affordable:
            return {"type": "end_phase"}

        baseline = _eval_state(state, player_id, self.bias)
        best_delta = self.bias.attack_threshold  # must beat this to act
        best_card: Optional["GameObject"] = None

        for card in affordable:
            forecast = self._simulate_play_card(state, player_id, card.id)
            if forecast is None:
                continue
            delta = _eval_state(forecast, player_id, self.bias) - baseline
            if delta > best_delta:
                best_delta = delta
                best_card = card

        if best_card is None:
            return {"type": "end_phase"}
        return {"type": "play_card", "card_id": best_card.id, "targets": []}

    def _filter_trap_cards(
        self,
        state: GameState,
        player_id: str,
        cards: list["GameObject"],
    ) -> list["GameObject"]:
        """Hide known-bad / engine-bugged plays from the hard tier.

        Iter-1 lessons (`docs/strategy/finance.md`):
        - Liquidity Provision at full mana = 0-gain trap.
        - Speed Amplifier with no 3+ tough Trader on board = orphan risk.
        - Tick Data Archive = currently dead (trigger flag never set).

        Iter-2 lessons:
        - Leverage Trader self-tax: refuse to deploy a new Leverage Trader
          if the projected MC tick would drop us below safety margin AND
          no counter-removal source is in play. Iter-2: P1 lost 12 → -4
          in one MC with 5 Leverage Traders and no Black-Scholes / Theta
          Decay Trader / Theta Decay Collar on board.

        Returns the filtered list; if everything would be filtered, returns
        the original list (better to play SOMETHING than end_phase).
        """
        player = state.players.get(player_id)
        if not player:
            return cards
        avail = int(getattr(player, "mana_crystals_available", 0) or 0)
        max_mana = int(getattr(player, "mana_crystals_max", avail) or avail)

        # Are there any 3+ tough Traders on our side? (Speed Amp anchor check)
        own_traders = _own_traders(state, player_id)
        has_sticky_anchor = any(_toughness(t) >= 3 for t in own_traders)

        # Iter-2: leverage-tax projection.
        # Project the next MC tick assuming the suspected ×1.7 doubling bug.
        # If the bug gets fixed, the multiplier should drop back to 1.0.
        cur_capital = int(getattr(player, "life", 30) or 30)
        current_lev_total = _expected_leverage_tax(state, player_id)
        has_remover = _has_leverage_remover(state, player_id)
        # Safety margin: refuse to deploy a Leverage Trader if projected
        # tick would drop us at or below this threshold without a remover.
        leverage_safety_margin = 5
        leverage_bug_multiplier = 1.7  # iter-2 observed: tick is ~1.7× Σleverage

        kept: list["GameObject"] = []
        for card in cards:
            name = _card_name(card)
            if name == "Liquidity Provision":
                # Trap at full mana: gains 3 up to current max → 0 net.
                # Only cast when there's headroom OR we're chaining a 4+ play.
                hand = _hand_cards(state, player_id)
                expensive = [
                    c for c in hand
                    if c.id != card.id and _mana_cost(c) >= 4
                    and _can_afford(state, player_id, c.id) is False
                    and avail + 3 >= _mana_cost(c)
                ]
                # Iter-3 (Pilot A): tighten threshold from max-2 to max-1.
                # Even at max-1, +3 caps at max → effective gain is 1 mana
                # for 2 mana spent, still a net loss with no chain target.
                if avail >= max_mana - 1 and not expensive:
                    continue  # skip — would gain ≤1 net, no chain target either
            elif name == "Speed Amplifier":
                # Engine bug: orphans on attached Trader's death.
                # Only deploy when we have a 3+ tough anchor.
                if not has_sticky_anchor:
                    continue
            elif name == "Tick Data Archive":
                # Engine bug: alpha-struck-alone flag never set; trigger
                # never fires. Card is currently dead weight.
                continue
            elif name == "Rebalancing Halt":
                # Iter-3 engine bug 17: TAP on already-declared attacker is
                # a no-op for combat resolution. RH is only useful as a
                # sorcery-speed effect on YOUR turn pre-declare (which the
                # current adapter has no phase-aware path for). At instant
                # speed during opp's combat it does nothing. Skip until
                # the engine fix lands or until phase-aware activation is
                # added to the adapter.
                continue
            elif name == "Off-Exchange Position":
                # Iter-3 engine bug 13/15: silent no-op without DP slot,
                # AND DP staging itself is unwired (`_play_card_action`
                # lacks `_dark_pool` branch). Casting OEP is strictly a
                # mana sink. Skip until staging is wired.
                continue
            elif _is_dark_pool_order(card):
                # Iter-3 engine bug 15: Dark Pool staging unwired.
                # All DP-tagged Orders resolve to GY without staging,
                # their `dark_effect_fn` never registers. Casting is a
                # strict tempo loss. Skip every DP Order until the
                # staging path is wired in finance_turn._play_card_action.
                # Note: this is deck-agnostic — Dark Arbitrage pilots get
                # the most savings, but any deck holding a DP card benefits.
                continue
            else:
                # Iter-2 leverage-tax filter: skip a new Leverage Trader if
                # deploying it would produce a lethal-range MC tick projection
                # and we have no counter-removal source on board.
                #
                # Theta Decay Trader is itself a remover, so playing it always
                # passes (it manages its own counter via pre-MC trigger).
                if name not in _LEVERAGE_COUNTER_REMOVERS and _is_trader(card):
                    new_lev = _card_text_leverage_n(card)
                    if new_lev > 0:
                        projected_total = current_lev_total + new_lev
                        projected_tax = projected_total * leverage_bug_multiplier
                        projected_capital = cur_capital - projected_tax
                        if (
                            projected_capital <= leverage_safety_margin
                            and not has_remover
                        ):
                            # Refuse to deploy — would self-kill in 1-2 MCs.
                            continue
            kept.append(card)

        return kept if kept else cards

    def _hard_attackers(self, state: GameState, player_id: str) -> list[str]:
        """
        Enumerate non-empty subsets of legal attackers (up to size 6 for
        tractability), simulate optimal opponent blocking for each subset,
        and pick the subset maximising V delta (§8 Hard).

        Iter-1 patches (FINA double-pilot, both pilots agreed):
        - **Solo Alpha Strike rule (HF lesson)**: only the first declared
          attacker gets the +3 alpha bonus (engine bug). When the only
          legal attackers are Alpha Strikers, send ONE attacker not all.
          Prefer the highest-power Alpha Striker for solo attack.
        - **Swarm rule (Quant lesson)**: when our attacker count exceeds
          the opponent's potential blocker count by 2+, send everyone —
          asymmetric trader count forces unblockable damage. Only applies
          when no Alpha Strikers (or alpha is irrelevant due to non-AS
          mix).
        """
        legal = _legal_attackers(state, player_id)
        if not legal:
            return []

        # Heuristic preflight: if all legal attackers are Alpha Strikers,
        # solo-attack with the highest-power one. This avoids the multi-
        # attack bug where only the first declared keeps alpha buff.
        as_attackers = [t for t in legal if _has_alpha_strike(t)]
        if as_attackers and len(as_attackers) == len(legal):
            best = max(as_attackers, key=_power)
            # Still verify the solo swing improves V (don't suicide into
            # a wall just because we have an alpha attacker).
            baseline = _eval_state(state, player_id, self.bias)
            forecast = self._simulate_attack_resolution(
                state, player_id, [best.id]
            )
            if forecast is not None:
                delta = _eval_state(forecast, player_id, self.bias) - baseline
                if delta > self.bias.attack_threshold:
                    return [best.id]
            # Fall through to subset search if solo doesn't beat threshold.

        # Swarm rule: if we have 2+ more attackers than opponent has
        # potential blockers, the asymmetry forces unblockable damage.
        # Send everyone (subset search would also find this but cheaper
        # to short-circuit).
        opp_id = _other_player(state, player_id)
        if opp_id is not None:
            opp_blockers = [
                t for t in _own_traders(state, opp_id)
                if not getattr(t.state, "tapped", False)
            ]
            if len(legal) >= len(opp_blockers) + 2 and not as_attackers:
                # Verify swarm improves V before committing.
                all_ids = [t.id for t in legal]
                baseline = _eval_state(state, player_id, self.bias)
                forecast = self._simulate_attack_resolution(
                    state, player_id, all_ids
                )
                if forecast is not None:
                    delta = (
                        _eval_state(forecast, player_id, self.bias)
                        - baseline
                    )
                    if delta > self.bias.attack_threshold:
                        return all_ids

        baseline = _eval_state(state, player_id, self.bias)
        best_delta = self.bias.attack_threshold
        best_subset: list[str] = []

        # Cap at 6 attackers to keep subset count manageable (2^6=64).
        candidates = legal[:6]
        n = len(candidates)

        for mask in range(1, 1 << n):
            subset = [candidates[i].id for i in range(n) if mask & (1 << i)]
            # Skip multi-Alpha-Strike subsets (only one alpha buff fires).
            subset_objs = [state.objects.get(sid) for sid in subset]
            as_count = sum(
                1 for o in subset_objs
                if o is not None and _has_alpha_strike(o)
            )
            if as_count >= 2:
                continue  # multi-AS attack wastes alpha on all but one
            forecast = self._simulate_attack_resolution(state, player_id, subset)
            if forecast is None:
                continue
            delta = _eval_state(forecast, player_id, self.bias) - baseline
            if delta > best_delta:
                best_delta = delta
                best_subset = subset

        return best_subset

    def _hard_blockers(
        self,
        state: GameState,
        attacker_ids: list[str],
        player_id: str,
    ) -> dict[str, str]:
        """
        Try all legal blocking assignments (brute-force), pick the one
        minimising V loss for the defending player (§8 Hard).
        Falls back gracefully to Medium if deepcopy fails.

        Iter-1 patch (Quant pilot lesson):
        - **Mandatory-block override**: when total unblocked damage would
          drop our Capital Reserve below 25% (or to 0), block everything
          we can — even if the brute-force search prefers to take face.
          Trample overflow is real but face leakage > 5 is worse than
          1-2 leaked through chump-blocks.
        - **Empty assignment is allowed**: if every assignment loses V
          worse than taking face, return ``{}`` (no blocks) — the prior
          fallback to ``_medium_blockers`` could force suicide chumps.
        """
        available = [
            obj for obj in _own_traders(state, player_id)
            if not getattr(obj.state, "tapped", False)
            and obj.id not in attacker_ids
        ]
        if not available:
            return {}

        # Mandatory-block check: if unblocked damage is lethal-range,
        # commit every blocker we have. Computed against current life.
        player = state.players.get(player_id)
        cur_life = int(getattr(player, "life", 30)) if player else 30
        unblocked_dmg = sum(
            _power(obj) for aid in attacker_ids
            if (obj := state.objects.get(aid)) is not None
        )
        # 25% reserve = 7.5 of 30. Round to 8 (HF chip threshold).
        force_block = (
            unblocked_dmg >= cur_life
            or cur_life - unblocked_dmg <= 8
        )

        # Collect all valid (attacker_id → blocker_id) assignment dicts
        # via a greedy permutation search (cap at 120 permutations = 5!).
        import itertools
        attacker_objs = [state.objects.get(aid) for aid in attacker_ids if state.objects.get(aid)]
        blocker_ids = [b.id for b in available]

        baseline = _eval_state(state, player_id, self.bias)
        best_loss = float("inf")
        best_assignment: dict[str, str] = {}

        # Limit permutation search to first 5 blockers × 5 attackers.
        for perm in itertools.islice(
            itertools.permutations(blocker_ids[:5]), 120
        ):
            assignment: dict[str, str] = {}
            for i, atk_obj in enumerate(attacker_objs[:5]):
                if i < len(perm):
                    assignment[atk_obj.id] = perm[i]
            forecast = self._simulate_blocking(state, player_id, assignment)
            if forecast is None:
                continue
            v_after = _eval_state(forecast, player_id, self.bias)
            loss = baseline - v_after
            if loss < best_loss:
                best_loss = loss
                best_assignment = assignment

        # If we'd otherwise leak ≥ 25% capital reserve, force a block:
        # delegate to medium (which assigns smallest-survivor blockers
        # to biggest threats first).
        if force_block and not best_assignment:
            return self._medium_blockers(state, attacker_ids, player_id)
        if not best_assignment:
            return self._medium_blockers(state, attacker_ids, player_id)
        return best_assignment

    # ──────────────────────────────────────────────────────────────────────
    # Hard-tier simulation helpers
    # ──────────────────────────────────────────────────────────────────────

    def _simulate_play_card(
        self,
        state: GameState,
        player_id: str,
        card_id: str,
    ) -> Optional[GameState]:
        """
        Deep-copy state, pay cost, move card to battlefield (Trader) or
        graveyard (Order/Strategy), return forecasted state.

        Returns None if deepcopy fails (back-reference recursion guard).
        """
        try:
            forecast = copy.deepcopy(state)
        except Exception:
            return None

        player = forecast.players.get(player_id)
        if player is None:
            return None

        card = forecast.objects.get(card_id)
        if card is None:
            return None

        cost = _mana_cost(card)
        available = int(getattr(player, "mana_crystals_available", 0) or 0)
        if available < cost:
            return None

        player.mana_crystals_available = max(0, available - cost)

        # Move card: Traders → battlefield; others → graveyard (single-use).
        hand_zone = forecast.zones.get(f"hand_{player_id}") or forecast.zones.get("hand")
        bf = forecast.zones.get("battlefield")

        if hand_zone and card_id in hand_zone.objects:
            hand_zone.objects.remove(card_id)

        if _is_trader(card) and bf is not None:
            bf.objects.append(card_id)
            card.zone = ZoneType.BATTLEFIELD
        else:
            gy_key = f"graveyard_{player_id}"
            gy = forecast.zones.get(gy_key) or forecast.zones.get("graveyard")
            if gy is not None:
                gy.objects.append(card_id)
            card.zone = ZoneType.GRAVEYARD

        return forecast

    def _simulate_attack_resolution(
        self,
        state: GameState,
        attacker_player_id: str,
        attacker_ids: list[str],
    ) -> Optional[GameState]:
        """
        Shallow-simulate combat for a given set of attackers. Uses the
        Medium blocking logic on the opposing side to produce a plausible
        opponent blocking response, then resolves simultaneous damage.
        Returns None on deepcopy failure.
        """
        try:
            forecast = copy.deepcopy(state)
        except Exception:
            return None

        opp_id = _other_player(forecast, attacker_player_id)
        if opp_id is None:
            return forecast

        # Simulate opponent's Medium-tier blocking response.
        opp_blocks = self._medium_blockers(forecast, attacker_ids, opp_id)

        self._apply_damage_step(forecast, attacker_ids, opp_blocks, attacker_player_id)
        return forecast

    def _simulate_blocking(
        self,
        state: GameState,
        defender_id: str,
        assignment: dict[str, str],
    ) -> Optional[GameState]:
        """
        Simulate a specific blocking assignment from the defender's perspective.
        Returns a forecasted state after combat damage resolves.
        """
        try:
            forecast = copy.deepcopy(state)
        except Exception:
            return None

        attacker_player_id = _other_player(forecast, defender_id)
        if attacker_player_id is None:
            return forecast

        attacker_ids = list(assignment.keys())
        self._apply_damage_step(forecast, attacker_ids, assignment, attacker_player_id)
        return forecast

    def _apply_damage_step(
        self,
        state: GameState,
        attacker_ids: list[str],
        blocks: dict[str, str],
        attacker_player_id: str,
    ) -> None:
        """
        In-place simultaneous damage approximation (§5 Finance combat math).

        For each attacker:
          - If blocked: attacker deals Aggression to blocker; blocker deals
            Defense to attacker. If lethal, mark damage on obj.state.damage.
          - If unblocked: deal attacker's Aggression to opponent's Capital Reserve.

        This is an approximation — it does not fire events or run overflow
        interceptors. It's sufficient for the 1-ply lookahead score comparison.
        """
        opp_id = _other_player(state, attacker_player_id)
        opp_player = state.players.get(opp_id) if opp_id else None

        for atk_id in attacker_ids:
            atk_obj = state.objects.get(atk_id)
            if atk_obj is None:
                continue
            atk_power = _power(atk_obj)

            blocker_id = blocks.get(atk_id)
            if blocker_id:
                blk_obj = state.objects.get(blocker_id)
                if blk_obj is None:
                    # Unblocked fallthrough.
                    if opp_player:
                        opp_player.life = max(0, opp_player.life - atk_power)
                    continue
                blk_power = _power(blk_obj)
                blk_defense = _remaining_defense(blk_obj)

                # Apply damage to attacker.
                new_atk_dmg = int(getattr(atk_obj.state, "damage", 0)) + blk_power
                atk_obj.state.damage = new_atk_dmg

                # Apply damage to blocker + overflow to Capital Reserve.
                new_blk_dmg = int(getattr(blk_obj.state, "damage", 0)) + atk_power
                blk_obj.state.damage = new_blk_dmg
                overflow = max(0, atk_power - blk_defense)
                if overflow > 0 and opp_player:
                    opp_player.life = max(0, opp_player.life - overflow)
            else:
                # Unblocked — deal full Aggression to opponent's Capital Reserve.
                if opp_player:
                    opp_player.life = max(0, opp_player.life - atk_power)

    # ──────────────────────────────────────────────────────────────────────
    # Internal legal-move helpers (documented in spec; exposed for testing)
    # ──────────────────────────────────────────────────────────────────────

    def _legal_hand(self, state: GameState, player_id: str) -> list[str]:
        """Return IDs of all cards currently in the player's hand zone."""
        player = state.players.get(player_id)
        if not player:
            return []
        hand_zone = (
            state.zones.get(f"hand_{player_id}") or state.zones.get("hand")
        )
        if not hand_zone:
            return []
        return list(hand_zone.objects)

    def _can_afford(self, state: GameState, player_id: str, card_id: str) -> bool:
        """Public wrapper over module-level ``_can_afford`` (for external callers)."""
        return _can_afford(state, player_id, card_id)

    def _legal_attackers(self, state: GameState, player_id: str) -> list[str]:
        """IDs of Traders that can legally attack (on battlefield, untapped, no sickness)."""
        return [obj.id for obj in _legal_attackers(state, player_id)]

    def _is_trader(self, obj: "GameObject") -> bool:
        """True if ``obj`` carries the FIN_TRADER CardType."""
        return _is_trader(obj)

    def _get_card_value(self, state: GameState, card_id: str) -> float:
        """(power + toughness) / max(cost, 1) — efficiency score for Traders."""
        obj = state.objects.get(card_id)
        if not obj:
            return 0.0
        return _trader_score(obj)

    def _board_value(self, state: GameState, player_id: str) -> float:
        """Sum of (Aggression + Defense Rating) for all friendly Traders on floor."""
        return _board_value(state, player_id)

    def _eval_state(self, state: GameState, player_id: str) -> float:
        """Board-value heuristic for hard-tier lookahead (uses ``self.bias``)."""
        return _eval_state(state, player_id, self.bias)

    def _get_opponent(self, state: GameState, player_id: str) -> str:
        return _other_player(state, player_id) or ""

    def _expected_leverage_tax(
        self,
        state: GameState,
        player_id: str,
    ) -> int:
        """Iter-2: sum of Leverage counters across player's Traders.

        Projects the next MARKET_CLOSE tick assuming no counter removal.
        See module-level ``_expected_leverage_tax`` for details and the
        suspected tick-doubling engine bug warning.
        """
        return _expected_leverage_tax(state, player_id)

    def _has_leverage_remover(
        self,
        state: GameState,
        player_id: str,
    ) -> bool:
        """Iter-2: True if player has a Leverage-counter-removal source on board."""
        return _has_leverage_remover(state, player_id)


# =============================================================================
# Public re-exports
# =============================================================================

__all__ = [
    "FinanceAIAdapter",
    "FinanceAIBias",
]
