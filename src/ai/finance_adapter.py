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
    # Iter-4 single pilot (HF mirror): board flooding wins over capital accumulation;
    # bumped board_weight 0.3→0.4, capital_weight 0.5→0.4 to reflect empirical result.
    capital_weight: float = 0.4
    board_weight: float = 0.4
    liquidity_weight: float = 0.2

    # Hard combat: minimum V-delta improvement required to commit attackers.
    # Iter-6 single pilot (P2a iter-3): nudged 0.0→0.05 so AI waits for a
    # meaningful attack window (≥2 unblocked attackers OR DMA in play) before
    # committing — avoids trickling 1-body attacks into chump-trades early.
    attack_threshold: float = 0.05

    # Medium: Capital Reserve threshold below which AI holds Orders defensively
    # in the Dark Pool rather than playing them immediately (§8 Medium).
    hold_order_threshold: int = 10

    # Response window — how aggressively to spend a counterspell/removal Order
    # when the opponent casts something. Higher = more eager to interrupt.
    # Range roughly 0.0 (never) to 1.0 (always if you can pay).
    counterspell_eagerness: float = 0.6
    # Cap on how deep we'll repush during a single priority loop. Prevents
    # AIs that have multiple cheap counters from chaining infinitely.
    response_depth_cap: int = 2


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


# Counterspells are only useful as responses to opponent spells. The default
# `choose_play_action` heuristic doesn't model "save for later" — it just
# picks the highest-scoring affordable card every action loop, which would
# burn IRE/Glitch/Regime on the active player's own turn for no effect.
# We exclude these cards from regular play; they're only cast via
# choose_response_action.
_RESPONSE_ONLY_CARD_NAMES = frozenset({
    "Information Ratio Enforcer",
    "Regime Change Detection",
    "Execution Glitch",
})


def _is_response_only(obj: "GameObject") -> bool:
    return _card_name(obj) in _RESPONSE_ONLY_CARD_NAMES


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


def _affordable_traders_in_hand(state: GameState, player_id: str) -> list["GameObject"]:
    """Return Traders in hand that the player can afford right now.

    Iter-7 (P2a iter-5) body-priority encoder: used by _hard_play_action to
    detect when an affordable Trader exists so we can prioritise it over
    non-Trader plays when trailing on board count.
    """
    hand = _hand_cards(state, player_id)
    return [c for c in hand if _is_trader(c) and _can_afford(state, player_id, c.id)]


def _find_opponent_lord(state: GameState, player_id: str) -> Optional["GameObject"]:
    """Return the opponent's lord Trader (grants +0/+N to all allies), or None.

    Iter-7 (P2a iter-5) lord-killing encoder: a 'lord' grants a static +0/+N
    buff to all friendly Traders (e.g., Portfolio Construction Desk +0/+1).
    Heuristic detection: opponent Trader whose card text contains '+0/+' and
    references 'other' Traders or 'each'/'all' Traders — covers lord patterns
    in the current Finance pool.
    """
    opp_traders = _opp_traders(state, player_id)
    for obj in opp_traders:
        try:
            text = str(
                getattr(obj.characteristics, "text", None)
                or getattr(obj, "text", None)
                or ""
            )
            # Lord pattern: grants a bonus to "other" friendly Traders.
            if "other" in text and "+0/+" in text:
                return obj
            # Also match "each Trader you control" / "all" wording variants.
            if "+0/+" in text and ("each" in text or "all" in text):
                return obj
        except (AttributeError, TypeError):
            continue
    return None


def _highest_power_own_trader(state: GameState, player_id: str) -> Optional["GameObject"]:
    """Return the highest-power own Trader on the battlefield; None if board is empty.

    Iter-4 single pilot (Bug 22): QSB auto-targeted first Trader in list (RFC 1/1)
    rather than highest-power Trader (FCE 3/2), wasting the alpha grant on the
    weakest body. Use this helper to select the correct QSB/buff target.
    """
    traders = _own_traders(state, player_id)
    if not traders:
        return None
    return max(traders, key=_power)


def _has_ttd_attached(obj: "GameObject", state: GameState) -> bool:
    """True if a Ticker Tape Derivative is attached to this Trader.

    P2b iter-3: FCB+TTD is the strongest combo body in the HF deck.
    Once TTD is attached, FCB becomes a 5-power Alpha Striker that must
    be answered every turn.  Use this to identify the combo piece so it
    can receive highest-attack-priority and be protected from discard.
    """
    bf = state.zones.get("battlefield")
    if bf is None:
        return False
    for oid in bf.objects:
        deriv = state.objects.get(oid)
        if deriv is None:
            continue
        if _card_name(deriv) != "Ticker Tape Derivative":
            continue
        attached_to = getattr(getattr(deriv, "state", None), "attached_to", None)
        if attached_to == obj.id:
            return True
    return False


def _find_ttd_combo_body(state: GameState, player_id: str) -> Optional["GameObject"]:
    """Return the own Trader that has TTD attached and native Alpha Strike, or None.

    P2b iter-3: FCB+TTD (post Bug-30 fix: 5-power) is the kill engine.
    When this body is live, it should be the first declared attacker and
    the last candidate for discard.
    """
    for obj in _own_traders(state, player_id):
        if _has_alpha_strike(obj) and _has_ttd_attached(obj, state):
            return obj
    return None


def _has_dma_on_board(state: GameState, player_id: str) -> bool:
    """True if Direct Market Access is currently in play for this player.

    Iter-4 single pilot (Bug 21): DMA's +4/+0 is an ETB spike, not a persistent
    static. The bonus only applies on the turn DMA enters. After that turn it
    reverts. Tracking whether DMA is fresh (deployed this turn) requires turn_data,
    but the conservative heuristic is: if DMA is on board AND we have a high-power
    Alpha Striker, treat this turn's attack as DMA-enhanced.
    """
    bf = _battlefield(state)
    if not bf:
        return False
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.controller == player_id and _card_name(obj) == "Direct Market Access":
            return True
    return False


def _dma_played_this_turn(state: GameState, player_id: str) -> bool:
    """True if Direct Market Access was deployed on the current turn.

    Iter-4 single pilot (Bug 21): DMA's +4/+0 is a 1-turn ETB spike.
    Checks turn_data flag set when DMA enters the battlefield this turn.
    Falls back to False if turn_data is absent (safe default).
    """
    try:
        turn_data = getattr(state, "turn_data", {}) or {}
        return bool(turn_data.get(f"fin_dma_entered_{player_id}", False))
    except (AttributeError, TypeError):
        return False


def _opp_trader_count(state: GameState, player_id: str) -> int:
    """Count opponent's Traders currently on the battlefield."""
    return len(_opp_traders(state, player_id))


# =============================================================================
# Anti-voltron helpers (rebalance v2, 2026-05-09)
# =============================================================================
#
# After the card-level voltron rebalance (HFPM {5}→{7}, 4/4→2/4, mass-attach
# cap=2) the heuristic AI still loses to voltron at 78.7% because it does not
# prioritise the new answer cards (Margin Squeeze {2}, Position Audit {3},
# Forced Unwinding {3}, Liquidation Cascade {4}).  The helpers below let
# `_hard_play_action` and `_filter_trap_cards` detect voltron-shaped threats
# and queue the right answer instead of greedy-deploying Traders.
# =============================================================================

# Names recognised by the anti-voltron heuristics.  Other "answer" cards in
# the format (Block Trade Sweep, Forced Liquidation, etc.) are NOT included
# because they are unconditional removal — the heuristic value function
# already prefers them when an opp Trader is the right size.  These cards
# are *conditional on Derivative-shaped opponents* and otherwise look like
# bad plays to the lookahead, so they need explicit handling.
_ANTI_VOLTRON_CARD_NAMES = frozenset({
    "Margin Squeeze",
    "Position Audit",
    "Forced Unwinding",
    "Liquidation Cascade",
})


def _is_derivative(obj: "GameObject") -> bool:
    """True if this object has the FIN_DERIVATIVE CardType."""
    if FIN_DERIVATIVE is None:
        return False
    try:
        return FIN_DERIVATIVE in obj.characteristics.types
    except (AttributeError, TypeError):
        return False


def _count_opponent_attached_derivatives(
    state: GameState, my_player_id: str
) -> int:
    """Count Derivatives attached to a Trader controlled by my opponent.

    "Attached" means the Derivative has its ``state.attached_to`` pointing at
    a Trader on the battlefield controlled by the opponent.  Derivatives that
    are merely staged on the opponent's Derivatives Desk (no host yet) are
    not counted.
    """
    opp_id = _other_player(state, my_player_id)
    if opp_id is None:
        return 0
    # Build the set of opponent Trader ids on the battlefield.
    opp_trader_ids: set[str] = set()
    bf = _battlefield(state)
    if bf is None:
        return 0
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.controller == opp_id and _is_trader(obj):
            opp_trader_ids.add(oid)
    if not opp_trader_ids:
        return 0
    count = 0
    for obj in state.objects.values():
        if not _is_derivative(obj):
            continue
        host_id = getattr(getattr(obj, "state", None), "attached_to", None)
        if host_id in opp_trader_ids:
            count += 1
    return count


def _count_opponent_desk_derivatives(
    state: GameState, my_player_id: str
) -> int:
    """Count Derivatives currently staged on opponent's Derivatives Desk."""
    opp_id = _other_player(state, my_player_id)
    if opp_id is None:
        return 0
    try:
        from src.engine.finance import get_deriv_desk
        desk = get_deriv_desk(state, opp_id)
        return len(desk)
    except Exception:
        return 0


def _count_opponent_total_derivatives(
    state: GameState, my_player_id: str
) -> int:
    """Total Derivatives owned by opponent: attached to host + on Desk."""
    return (
        _count_opponent_attached_derivatives(state, my_player_id)
        + _count_opponent_desk_derivatives(state, my_player_id)
    )


def _find_voltron_host(
    state: GameState, my_player_id: str, *, min_attached: int = 1
) -> Optional["GameObject"]:
    """Return the opponent's Trader with the most attached Derivatives.

    Returns None if no opponent Trader has ``min_attached`` or more
    Derivatives attached.  Used by the anti-voltron Margin Squeeze branch to
    select the highest-EV target.
    """
    opp_traders = _opp_traders(state, my_player_id)
    if not opp_traders:
        return None
    # Count attached Derivatives per opp Trader.
    counts: list[tuple[int, "GameObject"]] = []
    for trader in opp_traders:
        cnt = 0
        for obj in state.objects.values():
            if not _is_derivative(obj):
                continue
            if getattr(getattr(obj, "state", None), "attached_to", None) == trader.id:
                cnt += 1
        if cnt >= min_attached:
            counts.append((cnt, trader))
    if not counts:
        return None
    # Highest count wins; ties broken by highest power (Hedge Fund PM-style
    # threats first).
    counts.sort(key=lambda t: (t[0], _power(t[1])), reverse=True)
    return counts[0][1]


def _hand_has_card_named(
    state: GameState, player_id: str, name: str
) -> Optional["GameObject"]:
    """Return the first card in hand with the given name, or None."""
    for obj in _hand_cards(state, player_id):
        if _card_name(obj) == name:
            return obj
    return None


def _opponent_has_voltron_threats(
    state: GameState, my_player_id: str
) -> bool:
    """True if opponent's board looks like an active voltron threat.

    Triggers when:
      - any opp Trader has ≥2 attached Derivatives, OR
      - opp has ≥4 total Derivatives (attached + Desk), OR
      - ≥2 opp Traders each have ≥1 attached Derivative.
    """
    if _count_opponent_attached_derivatives(state, my_player_id) >= 2:
        host = _find_voltron_host(state, my_player_id, min_attached=2)
        if host is not None:
            return True
    if _count_opponent_total_derivatives(state, my_player_id) >= 4:
        return True
    # Multi-trader Derivative spread (e.g. opp has 2 hosts each holding 1).
    opp_traders = _opp_traders(state, my_player_id)
    multi_host = 0
    for trader in opp_traders:
        for obj in state.objects.values():
            if not _is_derivative(obj):
                continue
            if getattr(getattr(obj, "state", None), "attached_to", None) == trader.id:
                multi_host += 1
                break
    return multi_host >= 2


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


def _play_card_eval_delta(
    state: GameState,
    player_id: str,
    card: "GameObject",
    bias: FinanceAIBias,
) -> Optional[float]:
    """Analytical V-delta for "play this card" — replaces deepcopy lookahead.

    The 1-ply forecast in ``_simulate_play_card`` only mutates three things:
      - player's mana_crystals_available (-= cost)
      - battlefield (+= card iff Trader)
      - graveyard (+= card iff Order/Strategy/Asset/Derivative)

    ``_eval_state`` reads only ``player.life`` (unchanged), ``mana_crystals_
    available`` (decremented), and ``_board_value`` (sum of P+T on owned
    Traders on the battlefield).  Order/Strategy plays are graveyard moves
    that don't affect the eval at all — only the mana cost.

    Returns ``None`` when the card is unaffordable so callers can skip it.
    No allocations, no deepcopy, no interceptor scans.  ~1000× faster than
    the deepcopy-based forecast.
    """
    player = state.players.get(player_id)
    if player is None:
        return None
    cost = _mana_cost(card)
    available = int(getattr(player, "mana_crystals_available", 0) or 0)
    if available < cost:
        return None
    # Liquidity diff drops by cost/10 (opponent's mana unchanged).
    delta = -bias.liquidity_weight * (cost / 10.0)
    # Board value gains (power + toughness) iff the card resolves to BF
    # (i.e. is a Trader; non-Traders go to the graveyard and don't add bv).
    if _is_trader(card):
        delta += bias.board_weight * ((_power(card) + _toughness(card)) / 20.0)
    return delta


def _combat_overflow_to_opp(
    state: GameState,
    attacker_ids: list[str],
    blocks: dict[str, str],
) -> int:
    """Compute the Capital Reserve damage opp would take if combat resolved
    with this attack/block assignment.  Mirrors ``_apply_damage_step``'s
    overflow math without mutating state or running deepcopy.

    For each attacker:
      - Unblocked: overflow += attacker.power
      - Blocked: overflow += max(0, attacker.power - blocker.remaining_defense)
    """
    total = 0
    for atk_id in attacker_ids:
        atk_obj = state.objects.get(atk_id)
        if atk_obj is None:
            continue
        atk_power = _power(atk_obj)
        blocker_id = blocks.get(atk_id)
        if not blocker_id:
            total += atk_power
            continue
        blk_obj = state.objects.get(blocker_id)
        if blk_obj is None:
            total += atk_power  # invalid block id → treat as unblocked
            continue
        total += max(0, atk_power - _remaining_defense(blk_obj))
    return total


def _attack_eval_delta(
    state: GameState,
    attacker_player_id: str,
    attacker_ids: list[str],
    bias: FinanceAIBias,
    overflow_fn,
) -> float:
    """Analytical V-delta for "declare these attackers" — replaces deepcopy.

    ``_simulate_attack_resolution`` deep-copies state, picks an opponent
    Medium-tier block assignment, applies damage in place, and returns the
    forecast.  The eval reads only ``player.life`` (unchanged for attacker)
    and ``opp.life`` (decremented by total overflow).  ``_board_value``
    uses printed P/T so combat damage to creatures does not affect it.

    Therefore the delta is exactly:
        delta = -bias.capital_weight * (-overflow) / 30.0
              = bias.capital_weight * overflow / 30.0
    where overflow is the total Capital Reserve damage to the defender,
    clamped to opp.life so we don't reward "overkill" past 0.

    ``overflow_fn(attacker_ids, blocks_dict)`` is the caller-supplied way
    to compute overflow given a block assignment — typically just
    ``_combat_overflow_to_opp`` after running the medium blocker picker.
    """
    opp_id = _other_player(state, attacker_player_id)
    if opp_id is None:
        return 0.0
    opp_player = state.players.get(opp_id)
    if opp_player is None:
        return 0.0
    overflow = overflow_fn()
    # Clamp to current opp life so we don't credit overkill past 0.
    cur_opp_life = int(getattr(opp_player, "life", 0) or 0)
    overflow = min(overflow, max(0, cur_opp_life))
    return bias.capital_weight * (overflow / 30.0)


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

    # ─── Response action (priority window) ─────────────────────────────────

    def choose_response_action(
        self,
        state: GameState,
        player_id: str,
        top_of_stack,
    ) -> Optional[dict]:
        """
        Decide whether to play a responding Order to the top stack item.
        Returns None to pass, or a dict::

            {"action_type": "FIN_PLAY_RESPONSE",
             "card_id": <order_id>,
             "targets": [[<top_card_id>]]}

        Heuristic: counter Strategies aggressively (they're big swings);
        counter Orders only if cheap and we have spare Liquidity; otherwise
        pass. Never burn our last counterspell on a low-value target.
        """
        if top_of_stack is None:
            return None
        # Don't respond to our own casts (priority loop sometimes pings the
        # original caster after their own opponent passes).
        if top_of_stack.controller == player_id:
            return None
        # Cap recursion depth — each response gets one chance, then we're
        # back at the top of stack reading our own response. Stop there.
        stack = getattr(state, "fin_stack", None)
        if stack is not None and stack.depth() > int(self.bias.response_depth_cap):
            return None

        target_obj = state.objects.get(top_of_stack.card_id)
        if target_obj is None:
            return None

        # Identify the targeted card's category — Strategies are higher value
        # to counter than Orders (bigger effect, higher cost).
        target_is_strategy = False
        target_is_order = False
        try:
            from src.engine.types import CardType as _CT
            fin_strategy = getattr(_CT, "FIN_STRATEGY", None)
            fin_order_t = getattr(_CT, "FIN_ORDER", None)
            target_is_strategy = (
                fin_strategy is not None and fin_strategy in target_obj.characteristics.types
            )
            target_is_order = (
                fin_order_t is not None and fin_order_t in target_obj.characteristics.types
            )
        except Exception:
            pass

        # Browse hand for affordable Orders that could counter.
        hand = _hand_cards(state, player_id)
        player = state.players.get(player_id)
        avail = int(getattr(player, "mana_crystals_available", 0) or 0)

        # Priority list: Information Ratio Enforcer > Regime Change (Strategy
        # only) > Execution Glitch (Order only).
        candidates: list[tuple[int, "GameObject"]] = []
        for obj in hand:
            if not _is_order(obj):
                continue
            cost = _mana_cost(obj)
            if cost > avail:
                continue
            name = _card_name(obj)
            if name == "Information Ratio Enforcer":
                # Universal counter — always a candidate.
                candidates.append((1, obj))
            elif name == "Regime Change Detection" and target_is_strategy:
                candidates.append((2, obj))
            elif name == "Execution Glitch" and target_is_order:
                candidates.append((3, obj))

        if not candidates:
            return None

        # Eagerness gate: don't reflexively counter every cheap Order.
        # If the top is just an Order (not a Strategy) and our roll exceeds
        # eagerness, pass — we save the counter for something bigger.
        eagerness = float(self.bias.counterspell_eagerness)
        if not target_is_strategy:
            if self.rng.random() > eagerness:
                return None

        # Pick the most-specific candidate first.
        candidates.sort(key=lambda t: t[0])
        chosen = candidates[0][1]

        return {
            "action_type": "FIN_PLAY_RESPONSE",
            "card_id": chosen.id,
            "targets": [[top_of_stack.card_id]],
        }

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
        # P2b iter-3: protect the FCB+TTD combo body from discard.
        # If a native Alpha Striker with TTD attached is in the hand (unlikely
        # but theoretically possible during harness state reads), never discard it.
        # Implemented by giving the combo body a very high value so it sorts last.
        combo_body = _find_ttd_combo_body(state, player_id)
        combo_body_id = combo_body.id if combo_body is not None else None

        objs: list[tuple[float, str]] = []
        for item in hand:
            cid = item if isinstance(item, str) else item.id
            obj = state.objects.get(cid)
            if obj is None:
                continue
            if cid == combo_body_id:
                # Highest possible value — never discard the combo piece.
                val = 10000.0
            elif _is_trader(obj):
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
        """Random affordable non-response card from hand; if none, end phase."""
        hand = _hand_cards(state, player_id)
        affordable = [
            c for c in hand
            if _can_afford(state, player_id, c.id) and not _is_response_only(c)
        ]
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
            # Counterspells are saved for response windows — never burn them
            # on our own turn (they have no target on the stack here).
            if _is_response_only(card):
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

        Iter-7 (P2a iter-5) patch — body-priority when trailing:
        - When own Trader count < opp Trader count - 1 AND an affordable
          Trader exists in hand, play that Trader immediately before entering
          the lookahead loop. This is a hard heuristic (not a weight): the
          Derivatives AI was deploying BSM/TDC non-Traders when trailing on
          board count (3 vs 4) instead of Traders, losing on body count T13.
        """
        hand = _hand_cards(state, player_id)
        # Filter out counterspells — they're response-only and saved for
        # priority windows (handled by choose_response_action).
        affordable = [
            c for c in hand
            if _can_afford(state, player_id, c.id) and not _is_response_only(c)
        ]
        if not affordable:
            return {"type": "end_phase"}

        # ── Anti-voltron priority (rebalance v2, 2026-05-09) ─────────────────────
        # Voltron-shaped opponents (Derivative-heavy, voltron host with attached
        # buffs) are the dominant deck and the heuristic value function does not
        # capture the EV of stripping a single 8-power host.  Detect voltron
        # threats and queue the right answer card before the lookahead loop
        # has a chance to greedy-deploy a Trader.  Each branch is gated on
        # both the threat detection AND the answer being affordable in hand.
        anti_voltron_action = self._choose_anti_voltron_action(
            state, player_id, affordable
        )
        if anti_voltron_action is not None:
            return anti_voltron_action

        # ── Iter-7 body-priority heuristic (hard condition, runs BEFORE filters) ──
        # When trailing on Trader count by ≥2 AND an affordable Trader is in hand,
        # play the cheapest affordable Trader immediately (skip lookahead overhead).
        # Condition: own_trader_count < opp_trader_count - 1 (trailing by ≥2 Traders).
        # Rationale: each missed Trader deploy when trailing widens the gap; the
        # lookahead value function may still prefer a non-Trader play because ASSET/
        # DERIVATIVE cards have high nominal scores — this overrides that preference.
        own_trader_count = len(_own_traders(state, player_id))
        opp_id_for_body_check = _other_player(state, player_id)
        opp_trader_count_for_body_check = (
            len(_own_traders(state, opp_id_for_body_check))
            if opp_id_for_body_check else 0
        )
        # anti-voltron: in control mode (opp has 2+ Derivative-attached Traders)
        # the body-priority heuristic is wrong — we want to keep removal in hand
        # priced for the next voltron host, not chase Trader parity by deploying
        # a 1/1.  Skip body-priority when control mode applies.
        opp_voltron_hosts = sum(
            1 for trader in _opp_traders(state, player_id)
            if any(
                _is_derivative(o)
                and getattr(getattr(o, "state", None), "attached_to", None) == trader.id
                for o in state.objects.values()
            )
        )
        in_control_mode = opp_voltron_hosts >= 2
        if (
            not in_control_mode
            and own_trader_count < opp_trader_count_for_body_check - 1
        ):
            affordable_traders = _affordable_traders_in_hand(state, player_id)
            if affordable_traders:
                # Play the cheapest affordable Trader to minimise Liquidity waste.
                cheapest_trader = min(affordable_traders, key=_mana_cost)
                return {"type": "play_card", "card_id": cheapest_trader.id, "targets": []}

        # Surgical name-based filters for known dead/trap cards.
        affordable = self._filter_trap_cards(state, player_id, affordable)
        if not affordable:
            return {"type": "end_phase"}

        # Perf (2026-05-09): the 1-ply "play this card" forecast used to
        # ``copy.deepcopy(state)`` per affordable card — ~30ms per call,
        # ~25s on a 60-turn game.  ``_play_card_eval_delta`` computes the
        # exact same V-delta arithmetically with zero allocation.  See
        # docstring for the equivalence proof.
        best_delta = self.bias.attack_threshold  # must beat this to act
        best_card: Optional["GameObject"] = None

        for card in affordable:
            delta = _play_card_eval_delta(state, player_id, card, self.bias)
            if delta is None:
                continue
            if delta > best_delta:
                best_delta = delta
                best_card = card

        if best_card is None:
            return {"type": "end_phase"}

        # Iter-4 single pilot (Bug 22): QSB auto-targeted first Trader in list
        # (RFC 1/1) instead of highest-power Trader (FCE 3/2), wasting the alpha
        # grant. When playing QSB, pass the highest-power own Trader as target.
        targets: list[str] = []
        if _card_name(best_card) == "Quote Stuffing Burst":
            best_trader = _highest_power_own_trader(state, player_id)
            if best_trader is not None:
                targets = [best_trader.id]

        return {"type": "play_card", "card_id": best_card.id, "targets": targets}

    def _choose_anti_voltron_action(
        self,
        state: GameState,
        player_id: str,
        affordable: list["GameObject"],
    ) -> Optional[dict]:
        """Anti-voltron decision branch: cast Margin Squeeze / Position Audit /
        Forced Unwinding / Liquidation Cascade when the opponent's board shape
        warrants it.  Returns ``None`` when no anti-voltron play applies and
        the caller should fall through to the regular lookahead.

        Branch priority (highest EV first):
          1. Margin Squeeze on a 2+ attached host (cheap precise removal {2}).
          2. Position Audit when opp has 4+ total Derivatives (sweeper {3}).
          3. Liquidation Cascade when opp has 4+ Derivatives AND we have own
             Derivatives that would die to Position Audit ({4} asymmetric).
          4. Forced Unwinding pre-burst: opp has 3+ in Desk, T6+, opp has held
             cards (likely HFPM in hand).  Strips Desk pre-emptively.
        """
        # Quick exit: if NONE of our affordable cards are anti-voltron, skip
        # the (cheap but non-zero) detection scans below.
        affordable_names = {_card_name(c) for c in affordable}
        if not (affordable_names & _ANTI_VOLTRON_CARD_NAMES):
            return None

        # ── 1. Margin Squeeze on a 2+ attached host ─────────────────────────
        # anti-voltron: cheap precise removal of a Derivative-stacked Trader.
        # At {2}, Margin Squeeze is the highest-EV play on the spot when a
        # voltron host exists — it strips ALL attached buffs (via Equipment-
        # cleanup interceptor), turning an 8/4 HFPM into a dead investment.
        ms_card = next((c for c in affordable
                        if _card_name(c) == "Margin Squeeze"), None)
        if ms_card is not None:
            host = _find_voltron_host(state, player_id, min_attached=2)
            if host is not None:
                # anti-voltron: lock in target so resolve doesn't auto-pick
                # a different host than the one we evaluated.
                return {
                    "type": "play_card",
                    "card_id": ms_card.id,
                    "targets": [host.id],
                }
            # Don't hold MS if hand has 2+ copies and opponent has voltron-shape.
            ms_in_hand = sum(
                1 for c in _hand_cards(state, player_id)
                if _card_name(c) == "Margin Squeeze"
            )
            if ms_in_hand >= 2 and _opponent_has_voltron_threats(state, player_id):
                # Even at min_attached=1 the card still profits when opp is
                # a voltron deck — fish for a single-attached host.
                soft_host = _find_voltron_host(state, player_id, min_attached=1)
                if soft_host is not None:
                    return {
                        "type": "play_card",
                        "card_id": ms_card.id,
                        "targets": [soft_host.id],
                    }

        # ── 2. Position Audit when opp has 4+ total Derivatives ──────────────
        # anti-voltron: board-clearing tempo swing when opp is Derivative-heavy.
        pa_card = next((c for c in affordable
                        if _card_name(c) == "Position Audit"), None)
        if pa_card is not None:
            opp_total_derivs = _count_opponent_total_derivatives(state, player_id)
            if opp_total_derivs >= 4:
                # anti-voltron: weigh own Derivatives (symmetric loss) before
                # firing.  When we have NO own Derivatives, this is a pure
                # asymmetric blowout; otherwise weigh the loss.
                own_derivs = sum(
                    1 for o in state.objects.values()
                    if _is_derivative(o)
                    and o.controller == player_id
                    and getattr(o, "zone", None) == ZoneType.BATTLEFIELD
                )
                # Fire if opp has 2+ more derivs than us (asymmetric blowout)
                # OR if opp has 4+ and we have 0 (pure asymmetric).
                if own_derivs == 0 or (opp_total_derivs - own_derivs) >= 2:
                    return {
                        "type": "play_card",
                        "card_id": pa_card.id,
                        "targets": [],
                    }

        # ── 3. Liquidation Cascade for opp-attached + own-Derivative case ───
        # anti-voltron: {4} preserves up to 3 of our own (priority avoids them);
        # use when opp has 4+ derivs but we have own and don't want a sweeper.
        lc_card = next((c for c in affordable
                        if _card_name(c) == "Liquidation Cascade"), None)
        if lc_card is not None:
            opp_total_derivs = _count_opponent_total_derivatives(state, player_id)
            if opp_total_derivs >= 3:
                # LC priority targets opp Derivatives first (auto-pick), so
                # firing is always asymmetrically positive when opp has ≥3.
                return {
                    "type": "play_card",
                    "card_id": lc_card.id,
                    "targets": [],
                }

        # ── 4. Forced Unwinding pre-burst counter ────────────────────────────
        # anti-voltron: strip the Desk before HFPM burst.  Trigger conditions:
        #   - opp has 3+ Derivatives in Desk (about to burst-attach), OR
        #   - opp has any attached Derivatives (general detach value).
        #   - turn ≥ 6 AND opp hand size ≥ 3 implies HFPM held back.
        fu_card = next((c for c in affordable
                        if _card_name(c) == "Forced Unwinding"), None)
        if fu_card is not None:
            opp_attached = _count_opponent_attached_derivatives(state, player_id)
            opp_desk = _count_opponent_desk_derivatives(state, player_id)
            # anti-voltron: detach attached Derivatives — kills voltron buffs.
            if opp_attached >= 2:
                return {
                    "type": "play_card",
                    "card_id": fu_card.id,
                    "targets": [],
                }
            # anti-voltron: pre-empt Desk burst when HFPM is likely in hand.
            opp_id = _other_player(state, player_id)
            opp = state.players.get(opp_id) if opp_id else None
            opp_hand = _hand_cards(state, opp_id) if opp_id else []
            turn_no = int(getattr(state, "turn_number", 0) or 0)
            if (
                opp_desk >= 3
                and turn_no >= 6
                and len(opp_hand) >= 3
            ):
                return {
                    "type": "play_card",
                    "card_id": fu_card.id,
                    "targets": [],
                }

        return None

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

        # Iter-6 single pilot (P2a iter-3) — spell filtering in pure aggro mirror:
        # In the HF mirror (opponent has only cheap Alpha Strikers, no blockers >1
        # toughness), non-Trader spells costing ≤3 are dead weight — no targets,
        # no tempo value, no board impact at this game speed. Deprioritize them
        # by excluding non-Trader non-DMA cards when:
        #   (a) opponent is pure aggro (all opp Traders have Alpha Strike text), AND
        #   (b) we have <4 own Traders (still in flood mode), AND
        #   (c) there IS a Trader we can afford (play the Trader instead).
        # DMA is kept (it IS the spike tool). The filter returns the original list
        # if it would eliminate everything (safe fallback).
        opp_traders_list = _opp_traders(state, player_id)
        own_traders_list = _own_traders(state, player_id)
        opp_is_pure_alpha = (
            len(opp_traders_list) > 0
            and all(_has_alpha_strike(t) for t in opp_traders_list)
            and all(_toughness(t) <= 1 for t in opp_traders_list)
        )
        in_flood_mode = len(own_traders_list) < 4
        has_affordable_trader = any(
            _is_trader(c) and _can_afford(state, player_id, c.id) for c in cards
        )
        in_spell_filter_mode = opp_is_pure_alpha and in_flood_mode and has_affordable_trader

        kept: list["GameObject"] = []
        # anti-voltron: detect voltron-shape so we can keep answer cards
        # that the spell-filter would otherwise discard as "no targets".
        opp_has_voltron = _opponent_has_voltron_threats(state, player_id)
        for card in cards:
            name = _card_name(card)
            # Spell filter: skip non-Trader cards in pure-aggro flood mode (keep DMA).
            if (
                in_spell_filter_mode
                and not _is_trader(card)
                and name != "Direct Market Access"
                and name not in _ANTI_VOLTRON_CARD_NAMES  # anti-voltron: exempt
                and _mana_cost(card) <= 3
            ):
                continue
            # anti-voltron: never mark these as traps; they're situational
            # answers that the lookahead value function won't price correctly.
            # When opp is voltron-shaped, the anti-voltron branch already
            # routed before this filter ran; falling through means we're in
            # a non-voltron matchup and the card is just a dead draw, but
            # keeping it (rather than filtering) preserves the AI's option
            # to fire it if the lookahead happens to find positive V (e.g.
            # opp has 1 attached Derivative + a dangerous Trader to remove).
            if name in _ANTI_VOLTRON_CARD_NAMES and not opp_has_voltron:
                # Only keep if the card has a plausible target (Margin Squeeze
                # needs at least 1 attached host, Position Audit/LC need 1+
                # opp Derivatives, Forced Unwinding needs 1+ attached).
                opp_attached = _count_opponent_attached_derivatives(state, player_id)
                opp_total = _count_opponent_total_derivatives(state, player_id)
                if name == "Margin Squeeze" and opp_attached < 1:
                    continue  # no valid target
                if name == "Forced Unwinding" and opp_attached < 1:
                    continue  # nothing to detach
                if name in ("Position Audit", "Liquidation Cascade") and opp_total < 1:
                    continue  # no Derivatives to destroy
                # else: pass through to keep the card playable.
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
            elif name == "Gamma Scalper":
                # P2b iter-3 (Pilot B loss): Gamma Scalper adds Lev 3, which
                # raises Σlev by 3 immediately.  Without counter-removal on
                # board OR in hand, this is an unrecoverable self-destruct.
                # Rule: NEVER play Gamma Scalper unless Theta Decay Trader (TDT)
                # or Theta Decay Collar (TDC) is on board or in hand.
                # The `_has_leverage_remover` check covers board presence.
                # Additionally check hand for TDT/TDC.
                _GS_SAFE_NAMES = {"Theta Decay Trader", "Theta Decay Collar"}
                hand_for_gs = _hand_cards(state, player_id)
                hand_has_remover = any(
                    _card_name(c) in _GS_SAFE_NAMES for c in hand_for_gs
                )
                if not has_remover and not hand_has_remover:
                    continue  # unplayable without safety valve
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
                #
                # Iter-4 patch (P2a iter-4, DA AI flaw):
                # Original threshold (Σlev ≥ 1 → blocked) was too aggressive
                # for Dark Arbitrage: OEF (Lev 2) and IBT (Lev 2) were NEVER
                # deployed because any existing Leverage counter (even from a
                # prior Trader with Lev 1) would push projected_total to ≥ 1
                # and trigger the block. DA's best finisher bodies were
                # effectively locked out all game. Relax to: only block when
                # projected Σlev > 2 AND no counter-remover present. This
                # allows deploying OEF/IBT when Σlev ≤ 2 (safe per iter-4
                # observation: Σlev=2–3 + Theta Decay Collar = ~1.6 cap/turn
                # drain, sustainable for a 10-15 turn game).
                if name not in _LEVERAGE_COUNTER_REMOVERS and _is_trader(card):
                    new_lev = _card_text_leverage_n(card)
                    if new_lev > 0:
                        projected_total = current_lev_total + new_lev
                        projected_tax = projected_total * leverage_bug_multiplier
                        projected_capital = cur_capital - projected_tax
                        # Relaxed guard: allow deploy if projected Σlev ≤ 2
                        # (was: any Σlev increase blocked without remover).
                        if (
                            projected_total > 2
                            and projected_capital <= leverage_safety_margin
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

        Iter-4 single pilot patches (HF mirror):
        - **Mirror flood mode**: when opponent has ≥4 bodies, body count > solo
          quality. Switch to flooding all legal attackers to race by volume,
          even if some attackers lack alpha (iter-4: AI's 6 Traders outpaced
          pilot's DMA + 3 Traders because multi-attack volume > solo alpha in
          absolute damage terms when attacker count is ≥4 vs ≥4).
        - **DMA same-turn attack priority**: DMA's +4/+0 is an ETB spike, not a
          persistent static (Bug 21). When DMA was played this turn, prioritise
          the highest-power Alpha Striker for a solo attack to capture the +4
          before it expires. Don't hold it to "build a static buff" next turn.

        Iter-7 (P2a iter-5) patch — lord-killing priority:
        - When opponent controls a lord Trader (grants +0/+N to all allies),
          rank it highest for attack targeting. Implemented as: before the
          general subset search, check whether any single legal attacker has
          Aggression ≥ lord's remaining Defense (would kill it). If so,
          declare that attacker alone as a kill-the-lord strike (verify it
          passes V threshold). This prevents the AI from directing attacks
          into non-lord bodies while the lord buffs opponent's entire board.

        P2b iter-1 patches (HF wins T10 vs Derivatives, both pilots confirmed):
        - **Leverage kill-shot recognition**: When opponent's Σlev ≥ 3 AND their
          capital ≤ 5, the MARKET_CLOSE leverage tick (~3+/turn) will finish them
          without us needing to all-in. Reduce attack aggression: hold the
          highest-toughness own Trader back as a blocker rather than all-in.
          Avoids losing our best blocker to a wall trade when we can let the tick
          win instead. Pilot A observed this exact scenario at T10: opponent died
          at MC from Σlev=3 tick while at 2 capital — a combat all-in was
          unnecessary and would have been costly.
        - **Never all-in when opponent has 3+ bodies**: Before committing all
          Traders to attack, check _opp_trader_count() >= 3. If true, hold the
          highest-toughness own Trader back as a blocker. Pilot B (P2 Derivatives)
          confirmed: tapping all Traders for T8 attack left zero blockers for T9,
          allowing P1's 5-body all-in to deal full lethal face.
        """
        legal = _legal_attackers(state, player_id)
        if not legal:
            return []

        # ── P2b iter-3: FCB+TTD combo priority ──────────────────────────────────
        # When a native Alpha Striker has TTD attached (post Bug-30 fix: 5-power
        # Alpha Striker), it is the highest-value attack body in the deck.  Always
        # declare it FIRST when attacking — it gets the alpha +3 bonus (count==1 at
        # trigger time) and forces an answer every turn.
        # Note: if the combo body is the ONLY legal attacker, the solo-alpha path
        # below also handles it correctly.  This block handles the multi-body case
        # where we need to ensure the combo body is listed first.
        combo_body = _find_ttd_combo_body(state, player_id)
        if combo_body is not None and combo_body in legal:
            # Build attack list: combo body first, then remaining legal attackers.
            rest_after_combo = [t for t in legal if t.id != combo_body.id]
            # Perf (2026-05-09): analytical delta replaces deepcopy lookahead.
            delta_combo = self._eval_attack_delta(
                state, player_id, [combo_body.id]
            )
            if delta_combo > self.bias.attack_threshold:
                # Declare combo body first; remaining bodies follow.
                return [combo_body.id] + [t.id for t in rest_after_combo]

        # ── P2b iter-1: leverage kill-shot recognition (runs before all-in paths) ──
        # When opponent's Σlev ≥ 3 AND their capital ≤ 5, their MC tick will close
        # the game without risky all-in combat. Hold the highest-toughness Trader back.
        opp_id_for_lev = _other_player(state, player_id)
        if opp_id_for_lev is not None:
            opp_sigma_lev = _expected_leverage_tax(state, opp_id_for_lev)
            opp_capital = int(getattr(
                state.players.get(opp_id_for_lev), "life", 999
            ) or 999)
            if opp_sigma_lev >= 3 and opp_capital <= 5 and len(legal) >= 2:
                # Don't all-in — hold the tankiest own Trader back as blocker.
                anchor = max(legal, key=_toughness)
                legal = [t for t in legal if t.id != anchor.id]
                if not legal:
                    return []   # only 1 legal attacker, skip attack entirely

        # ── P2b iter-1: never all-in when opponent has 3+ bodies ──
        # With 3+ opponent Traders available to block/counter-attack, all-in leaves
        # us open to a lethal response. Keep the highest-toughness own Trader back.
        if _opp_trader_count(state, player_id) >= 3 and len(legal) >= 2:
            anchor_nai = max(legal, key=_toughness)
            legal = [t for t in legal if t.id != anchor_nai.id]
            if not legal:
                return []   # only 1 legal attacker after removal, skip

        # ── Iter-7 lord-killing priority (runs before DMA and mirror checks) ──
        # When opponent has a lord on board, try to kill it: declare the lowest-
        # power legal attacker whose Aggression ≥ lord's remaining Defense as a
        # solo strike. Killing the lord is worth more V than the raw combat math
        # because it removes the toughness buff from every opponent Trader.
        opp_lord = _find_opponent_lord(state, player_id)
        if opp_lord is not None:
            lord_defense = _remaining_defense(opp_lord)
            # Find attackers that can kill the lord (Aggression >= lord Defense).
            lord_killers = [t for t in legal if _power(t) >= lord_defense]
            if lord_killers:
                # Prefer the weakest attacker that can kill it (conserve power).
                kill_attacker = min(lord_killers, key=_power)
                # Perf: analytical delta replaces deepcopy lookahead.
                delta_lord = self._eval_attack_delta(
                    state, player_id, [kill_attacker.id]
                )
                if delta_lord > self.bias.attack_threshold:
                    return [kill_attacker.id]

        # Iter-6 single pilot (P2a iter-3) — DMA multi-attack priority:
        # When DMA is in play AND ≥3 other Traders exist, flood ALL attackers
        # with the best Alpha Striker declared first. DMA's +4/+0 ETB spike
        # fires on whichever attacker has count==1 at trigger time (Bug 2/18
        # alpha-asymmetry) — declaring the best Alpha Striker first captures
        # both +3 alpha AND +4 DMA for a 9/1 body. The remaining bodies deal
        # base power, converting a 4-body wave into 9+ face (confirmed T9 win).
        # Supersedes iter-4 solo-DMA heuristic for the multi-body case.
        if _dma_played_this_turn(state, player_id):
            own_trader_count = len(_own_traders(state, player_id))
            as_attackers_dma = [t for t in legal if _has_alpha_strike(t)]
            if as_attackers_dma and own_trader_count >= 4:
                # 4+ Traders total (≥3 others besides alpha striker): flood attack.
                # Sort: Alpha Strikers first (highest-power first), then non-alpha.
                best_alpha = max(as_attackers_dma, key=_power)
                rest = [t for t in legal if t.id != best_alpha.id]
                return [best_alpha.id] + [t.id for t in rest]
            elif as_attackers_dma:
                # Fewer than 4 bodies: fall back to solo-alpha (iter-4 lesson —
                # solo spike is still better than trickling non-alpha bodies early).
                best_dma = max(as_attackers_dma, key=_power)
                return [best_dma.id]

        # Iter-4 single pilot (HF mirror): when opponent has ≥4 bodies, body
        # count races beat solo-alpha quality. Flood all legal attackers to race
        # by volume — even non-alpha bodies add meaningful damage per turn when
        # the opponent can't block profitably (all their bodies are 2/1 vs our
        # 4-7 power attacks, death + overflow either way).
        opp_body_count = _opp_trader_count(state, player_id)
        if opp_body_count >= 4 and len(legal) >= 2:
            # Verify flooding improves V before committing all attackers.
            all_ids_flood = [t.id for t in legal]
            # Perf: analytical delta replaces deepcopy lookahead.
            delta_flood = self._eval_attack_delta(
                state, player_id, all_ids_flood
            )
            if delta_flood > self.bias.attack_threshold:
                return all_ids_flood

        # Heuristic preflight: if all legal attackers are Alpha Strikers,
        # solo-attack with the highest-power one. This avoids the multi-
        # attack bug where only the first declared keeps alpha buff.
        as_attackers = [t for t in legal if _has_alpha_strike(t)]
        if as_attackers and len(as_attackers) == len(legal):
            best = max(as_attackers, key=_power)
            # Still verify the solo swing improves V (don't suicide into
            # a wall just because we have an alpha attacker).
            # Perf: analytical delta replaces deepcopy lookahead.
            delta = self._eval_attack_delta(state, player_id, [best.id])
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
                # Perf: analytical delta replaces deepcopy lookahead.
                delta = self._eval_attack_delta(state, player_id, all_ids)
                if delta > self.bias.attack_threshold:
                    return all_ids

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
            # Perf: analytical delta replaces deepcopy lookahead.
            delta = self._eval_attack_delta(state, player_id, subset)
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

        Iter-4 patch (P2a iter-4, DA AI flaw):
        - **High-toughness wall pre-assignment**: before the brute-force
          permutation search, scan available blockers for any Trader whose
          remaining Defense Rating ≥ attacker's Aggression. If such a
          "wall" blocker exists against a given attacker, pre-assign it
          immediately. This ensures SPB (2/4) and similar high-toughness
          bodies are not left idle when they can stop damage profitably.
          The pre-assignment is included in the final block map regardless
          of V delta — high-toughness blocks are always profitable when
          the blocker survives the trade.
        """
        available = [
            obj for obj in _own_traders(state, player_id)
            if not getattr(obj.state, "tapped", False)
            and obj.id not in attacker_ids
        ]
        if not available:
            return {}

        # Iter-4: Pre-assign wall blockers (toughness ≥ attacker power).
        # A blocker that survives the trade is ALWAYS worth committing,
        # regardless of what the V-delta search returns — blocking for
        # free (no capital leak) is strictly better than taking the face.
        pre_assignments: dict[str, str] = {}
        pre_used: set[str] = set()
        # Sort attackers descending by power so largest threats get walls first.
        sorted_atk_for_walls = sorted(
            attacker_ids,
            key=lambda aid: _power(state.objects[aid]) if aid in state.objects else 0,
            reverse=True,
        )
        for atk_id in sorted_atk_for_walls:
            atk_obj = state.objects.get(atk_id)
            if atk_obj is None:
                continue
            atk_power = _power(atk_obj)
            # Find cheapest wall that survives (remaining defense > attacker power).
            wall_candidates = [
                b for b in available
                if b.id not in pre_used
                and _remaining_defense(b) > atk_power
            ]
            if wall_candidates:
                # Prefer wall with smallest remaining defense (least waste).
                wall = min(wall_candidates, key=_remaining_defense)
                pre_assignments[atk_id] = wall.id
                pre_used.add(wall.id)

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
        # Exclude blockers already pre-assigned to walls from the permutation search.
        remaining_available = [b for b in available if b.id not in pre_used]
        attacker_objs = [state.objects.get(aid) for aid in attacker_ids if state.objects.get(aid)]
        blocker_ids = [b.id for b in remaining_available]

        # Attackers without a wall pre-assignment need the permutation search.
        unassigned_atk_objs = [
            obj for obj in attacker_objs
            if obj is not None and obj.id not in pre_assignments
        ]

        best_loss = float("inf")
        best_assignment: dict[str, str] = {}

        # Limit permutation search to first 5 remaining blockers × 5 unassigned attackers.
        search_attackers = unassigned_atk_objs[:5]
        for perm in itertools.islice(
            itertools.permutations(blocker_ids[:5]), 120
        ):
            assignment: dict[str, str] = dict(pre_assignments)  # always include walls
            for i, atk_obj in enumerate(search_attackers):
                if i < len(perm):
                    assignment[atk_obj.id] = perm[i]
            # Perf (2026-05-09): analytical loss replaces deepcopy lookahead.
            loss = self._eval_blocking_loss(state, player_id, assignment)
            if loss < best_loss:
                best_loss = loss
                best_assignment = assignment

        # If pre_assignments found wall blockers, always return them
        # even if the permutation search found nothing better.
        if pre_assignments and not best_assignment:
            best_assignment = pre_assignments

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

        DEPRECATED for hot paths.  Internal hard-attacker callers now use
        :meth:`_eval_attack_delta` which returns the V-delta analytically
        without deep-copying state.  This method is preserved for any
        external callers (tests, debugging) that want a forecasted state.
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

    def _eval_attack_delta(
        self,
        state: GameState,
        attacker_player_id: str,
        attacker_ids: list[str],
    ) -> float:
        """Analytical V-delta for "declare these attackers" — no deepcopy.

        Calls ``_medium_blockers`` (which is read-only over state) to
        synthesise the opponent's blocking response, then computes the
        Capital Reserve overflow with :func:`_combat_overflow_to_opp`.

        Equivalent to::

            forecast = _simulate_attack_resolution(state, ...)
            return _eval_state(forecast, ...) - _eval_state(state, ...)

        but ~30× faster on a 5-attacker swing because no state is copied
        and no event pipeline is touched.
        """
        opp_id = _other_player(state, attacker_player_id)
        if opp_id is None:
            return 0.0
        opp_blocks = self._medium_blockers(state, attacker_ids, opp_id)
        return _attack_eval_delta(
            state,
            attacker_player_id,
            attacker_ids,
            self.bias,
            overflow_fn=lambda: _combat_overflow_to_opp(state, attacker_ids, opp_blocks),
        )

    def _eval_blocking_loss(
        self,
        state: GameState,
        defender_id: str,
        assignment: dict[str, str],
    ) -> float:
        """Analytical "loss" for a candidate block assignment — no deepcopy.

        Returns ``baseline - v_after`` for a given block.  Smaller is
        better (less Capital Reserve damage to the defender).  Mirrors
        the math the deepcopy-based ``_simulate_blocking`` produces, in
        constant time per assignment.
        """
        attacker_player_id = _other_player(state, defender_id)
        if attacker_player_id is None:
            return 0.0
        attacker_ids = list(assignment.keys())
        overflow = _combat_overflow_to_opp(state, attacker_ids, assignment)
        defender = state.players.get(defender_id)
        if defender is None:
            return 0.0
        cur_life = int(getattr(defender, "life", 0) or 0)
        overflow = min(overflow, max(0, cur_life))
        # ``loss = baseline - v_after`` where v_after for the defender
        # subtracts ``capital_weight * overflow / 30`` from their share
        # of the cap_diff term.  Defender is the eval target here, so
        # losing life lowers the eval by exactly that.
        return self.bias.capital_weight * (overflow / 30.0)

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
