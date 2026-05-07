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
        """
        available = [
            obj for obj in _own_traders(state, player_id)
            if not getattr(obj.state, "tapped", False)
            and obj.id not in attacker_ids
        ]
        assignments: dict[str, str] = {}
        used: set[str] = set()

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
            else:
                # No survivor — pick cheapest available to minimise value lost.
                remaining = [b for b in available if b.id not in used]
                if not remaining:
                    continue
                blocker = min(remaining, key=lambda b: _power(b) + _toughness(b))

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
        """
        hand = _hand_cards(state, player_id)
        affordable = [c for c in hand if _can_afford(state, player_id, c.id)]
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

    def _hard_attackers(self, state: GameState, player_id: str) -> list[str]:
        """
        Enumerate non-empty subsets of legal attackers (up to size 6 for
        tractability), simulate optimal opponent blocking for each subset,
        and pick the subset maximising V delta (§8 Hard).
        """
        legal = _legal_attackers(state, player_id)
        if not legal:
            return []

        baseline = _eval_state(state, player_id, self.bias)
        best_delta = self.bias.attack_threshold
        best_subset: list[str] = []

        # Cap at 6 attackers to keep subset count manageable (2^6=64).
        candidates = legal[:6]
        n = len(candidates)

        for mask in range(1, 1 << n):
            subset = [candidates[i].id for i in range(n) if mask & (1 << i)]
            # Simulate optimal opponent blocking against this attack subset.
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
        """
        available = [
            obj for obj in _own_traders(state, player_id)
            if not getattr(obj.state, "tapped", False)
            and obj.id not in attacker_ids
        ]
        if not available:
            return {}

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

        # If brute-force produced nothing useful, fall back to Medium.
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


# =============================================================================
# Public re-exports
# =============================================================================

__all__ = [
    "FinanceAIAdapter",
    "FinanceAIBias",
]
