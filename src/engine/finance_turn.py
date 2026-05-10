"""
Finance Turn Manager
=====================

Five-phase turn structure for the Finance TCG:

    PRE_MARKET     — Untap Traders, reset Liquidity, collect passive income,
                     clear summoning sickness
    RESEARCH       — Draw 1 card (or take fatigue damage if deck empty)
    TRADING_SESSION— Pre-combat action loop; declare attackers; declare
                     blockers; resolve combat damage
    SETTLEMENT     — Post-combat action loop (play cards, activate abilities)
    MARKET_CLOSE   — End-step triggers; discard to 7; clear EOT effects;
                     Leverage-counter cost tick; check win condition

Every phase emits ``PHASE_START`` / ``PHASE_END`` events with payload
``{"phase": "<name>", "player": <id>}`` so card triggers can hook them.

Orders (FIN_ORDER) can be played at instant speed during the opponent's
Research, Trading Session, Settlement, and Market Close phases, and during
your own Pre-Market, Research, and Market Close phases.

Imports from finance.py and finance_combat.py are wrapped in try/except so
this file can be loaded in parallel with those sibling modules.

Primary pattern: HearthstoneTurnManager (hearthstone_turn.py).
Secondary pattern: DepthsTurnManager (depths_turn.py).
"""

from __future__ import annotations

import inspect
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional, TYPE_CHECKING

from .turn import TurnManager, Phase, Step
from .types import (
    Event,
    EventType,
    GameState,
    ZoneType,
)

if TYPE_CHECKING:  # pragma: no cover
    from .pipeline import EventPipeline


# =============================================================================
# Guarded imports from peer modules
# =============================================================================

try:
    from .finance import reset_liquidity_for_turn, ensure_finance_state  # type: ignore
    _HAS_FINANCE_MODULE = True
except ImportError:
    _HAS_FINANCE_MODULE = False

    def reset_liquidity_for_turn(state, player_id):  # type: ignore[misc]
        """Fallback: grow mana_crystals by 1 (cap 10) and refill available."""
        player = state.players.get(player_id)
        if player is None:
            return
        if player.mana_crystals < 10:
            player.mana_crystals += 1
        player.mana_crystals_available = player.mana_crystals

    def ensure_finance_state(state):  # type: ignore[misc]
        pass


try:
    from .finance_combat import FinanceCombatManager  # type: ignore
    _HAS_COMBAT_MODULE = True
except ImportError:
    _HAS_COMBAT_MODULE = False
    FinanceCombatManager = None  # type: ignore[assignment,misc]


# =============================================================================
# Action-type sentinels
# =============================================================================

ACTION_END_PHASE          = "FIN_END_PHASE"
ACTION_END_TURN           = "FIN_END_TURN"
ACTION_PLAY_CARD          = "FIN_PLAY_CARD_ACTION"
ACTION_ACTIVATE           = "FIN_ACTIVATE_ABILITY"
ACTION_DISCARD            = "FIN_DISCARD"
ACTION_DECLARE_ATTACKERS  = "FIN_DECLARE_ATTACKERS"
ACTION_DECLARE_BLOCKERS   = "FIN_DECLARE_BLOCKERS"
ACTION_PLAY_RESPONSE      = "FIN_PLAY_RESPONSE"
ACTION_PASS_RESPONSE      = "FIN_PASS_RESPONSE"

# Safety cap: action loops exit after this many iterations regardless.
_ACTION_LOOP_CAP = 200

# Default hand limit (design doc: 7).
_DEFAULT_HAND_LIMIT = 7


# =============================================================================
# FinancePhase enum
# =============================================================================

class FinancePhase(Enum):
    PRE_MARKET      = auto()
    RESEARCH        = auto()
    TRADING_SESSION = auto()
    SETTLEMENT      = auto()
    MARKET_CLOSE    = auto()


# =============================================================================
# FinanceTurnState dataclass
# =============================================================================

@dataclass
class FinanceTurnState:
    turn_number: int = 0
    active_player_id: Optional[str] = None
    phase: FinancePhase = FinancePhase.PRE_MARKET
    combat_blocks: dict[str, str] = field(default_factory=dict)  # attacker_id -> blocker_id
    attackers_declared: list[str] = field(default_factory=list)
    # Set while ``_poll_response`` is awaiting a player's response to the
    # top of the FinanceStack. Cleared when the priority window closes.
    pending_response_player: Optional[str] = None


# =============================================================================
# FinanceTurnManager
# =============================================================================

class FinanceTurnManager(TurnManager):
    """
    Drives the five-phase Finance TCG turn loop.

    Constructor sets up AI-handler and combat-manager slots. After
    construction, wire the combat manager::

        turn_mgr.finance_combat_manager = FinanceCombatManager(state)

    and register AI handlers::

        turn_mgr.set_ai_handler(player_id, adapter)
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, state: GameState):
        super().__init__(state)
        self.fin_turn_state = FinanceTurnState()
        self.finance_ai_handlers: dict[str, Any] = {}
        self.ai_players: set[str] = set()
        self.human_action_handler = None   # async fn(player_id, state) -> action_dict
        self.action_log_handler = None     # sync fn(player_id, action_type, obj_or_payload)
        self.finance_combat_manager = None  # set after construction

        # MTG-style priority stack for FINA spells. Only Orders/Strategies push;
        # permanents bypass. Mirrored on state so card resolve_fns can reach it.
        from .finance_stack import FinanceStack
        self.fin_stack = FinanceStack()
        state.fin_stack = self.fin_stack

    # ------------------------------------------------------------------
    # AI handler registration
    # ------------------------------------------------------------------

    def set_ai_handler(self, player_id: str, adapter) -> None:
        """Register an AI adapter for the given player."""
        self.finance_ai_handlers[player_id] = adapter
        self.ai_players.add(player_id)

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled (without registering an adapter)."""
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: Optional[str]) -> bool:
        return bool(player_id and player_id in self.ai_players)

    def _get_ai(self, player_id: str):
        return self.finance_ai_handlers.get(player_id)

    # ------------------------------------------------------------------
    # Pipeline accessor (mirrors DepthsTurnManager._emit_pipeline)
    # ------------------------------------------------------------------

    @property
    def _emit_pipeline(self):
        if self.pipeline is not None:
            return self.pipeline
        return getattr(self.state, "_pipeline", None)

    # ------------------------------------------------------------------
    # Main turn driver
    # ------------------------------------------------------------------

    async def run_turn(self, player_id: str = None) -> list[Event]:
        """Run a complete Finance turn for player_id (or next in order)."""
        events: list[Event] = []

        # Determine active player.
        if player_id:
            self.fin_turn_state.active_player_id = player_id
            self.state.active_player = player_id
            if player_id in self.turn_order:
                self.current_player_index = self.turn_order.index(player_id)
        else:
            self.fin_turn_state.active_player_id = self.turn_order[self.current_player_index]
            self.state.active_player = self.fin_turn_state.active_player_id

        pid = self.fin_turn_state.active_player_id
        self.fin_turn_state.turn_number += 1
        self.state.turn_number = self.fin_turn_state.turn_number
        # Keep base TurnState in sync for interceptors that read it.
        self.turn_state.turn_number = self.fin_turn_state.turn_number

        # Reset per-turn combat tracking.
        self.fin_turn_state.attackers_declared = []
        self.fin_turn_state.combat_blocks = {}

        events.extend(await self._emit_turn_start())

        # Phase 1: PRE_MARKET
        self.fin_turn_state.phase = FinancePhase.PRE_MARKET
        events.extend(await self._run_pre_market(pid))
        if self._is_game_over():
            return events

        # Phase 2: RESEARCH
        self.fin_turn_state.phase = FinancePhase.RESEARCH
        events.extend(await self._run_research(pid))
        if self._is_game_over():
            return events

        # Phase 3: TRADING SESSION
        self.fin_turn_state.phase = FinancePhase.TRADING_SESSION
        events.extend(await self._run_trading_session(pid))
        if self._is_game_over():
            return events

        # Phase 4: SETTLEMENT
        self.fin_turn_state.phase = FinancePhase.SETTLEMENT
        events.extend(await self._run_settlement(pid))
        if self._is_game_over():
            return events

        # Phase 5: MARKET CLOSE
        self.fin_turn_state.phase = FinancePhase.MARKET_CLOSE
        events.extend(await self._run_market_close(pid))

        events.extend(await self._emit_turn_end())
        self._advance_turn()
        return events

    # ------------------------------------------------------------------
    # Phase 1: PRE_MARKET
    # ------------------------------------------------------------------

    async def _run_pre_market(self, player_id: str) -> list[Event]:
        """
        PRE_MARKET:
        - Reset Liquidity pool for the turn
        - Emit PHASE_START  (fires 'Monopoly Position' alternate-win check,
          leverage-income interceptors, etc.)
        - Untap all Traders belonging to player_id
        - Clear summoning sickness on player's Traders
        - Emit PHASE_END
        """
        events: list[Event] = []

        # Refill before start-of-Pre-Market triggers so passive income granted
        # by Assets/Structures is not overwritten by the turn refill.
        reset_liquidity_for_turn(self.state, player_id)

        events.extend(self._emit_phase("pre_market", "start", player_id))

        # Handle Short Sell returns: derivatives.py stores
        # state.turn_data["short_sell_return_{obj_id}"] = True when a Trader is exiled
        # via Short Selling.  Return it here with two +1/+1 counters.
        for key in list(self.state.turn_data.keys()):
            if key.startswith("short_sell_return_"):
                obj_id = key.replace("short_sell_return_", "")
                obj = self.state.objects.get(obj_id)
                if obj and obj.zone == ZoneType.EXILE and obj.owner == player_id:
                    # Determine counter count (default 1; Convexity Rider may set 2)
                    bonus_key = f"short_sell_bonus_counters_{obj_id}"
                    counter_count = int(self.state.turn_data.pop(bonus_key, 1))
                    del self.state.turn_data[key]
                    # Return to battlefield
                    return_evt = Event(
                        type=EventType.ZONE_CHANGE,
                        payload={
                            "object_id": obj_id,
                            "from_zone": "exile",
                            "to_zone": "battlefield",
                            "reason": "short_sell_return",
                        },
                    )
                    if self._emit_pipeline:
                        self._emit_pipeline.emit(return_evt)
                    events.append(return_evt)
                    # Apply +1/+1 counters via pipeline so _handle_counter_added
                    # updates state.counters — get_power() adds counters on top of
                    # characteristics.power, so we must NOT touch characteristics
                    # here or the Trader gets double the boost (bug #19).
                    counter_evt = Event(
                        type=EventType.COUNTER_ADDED,
                        payload={
                            "object_id": obj_id,
                            "counter_type": "+1/+1",
                            "amount": counter_count,
                        },
                    )
                    if self._emit_pipeline:
                        self._emit_pipeline.emit(counter_evt)
                    events.append(counter_evt)
                else:
                    # Object not found or not in exile; clear the stale marker
                    del self.state.turn_data[key]
                    self.state.turn_data.pop(f"short_sell_bonus_counters_{obj_id}", None)

        # Untap all Traders (and other tapped permanents) controlled by player.
        battlefield = self.state.zones.get("battlefield")
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj is None or obj.controller != player_id:
                    continue
                if not getattr(obj.state, "tapped", False):
                    continue
                untap = Event(
                    type=EventType.UNTAP,
                    payload={"object_id": obj_id},
                )
                if (pl := self._emit_pipeline):
                    pl.emit(untap)
                events.append(untap)

        # Clear summoning sickness so Traders that survived from last turn
        # can now attack. Newly played Traders receive summoning_sickness=True
        # on ETB and lose it here on the owner's *next* Pre-Market.
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj is None or obj.controller != player_id:
                    continue
                if hasattr(obj.state, "summoning_sickness"):
                    obj.state.summoning_sickness = False
                # Also reset per-turn attack counter.
                if hasattr(obj.state, "attacks_this_turn"):
                    obj.state.attacks_this_turn = 0

        # If the combat manager is available, ask it to handle its own
        # summoning-sickness bookkeeping (belt-and-braces).
        if self.finance_combat_manager and hasattr(
            self.finance_combat_manager, "clear_summoning_sickness"
        ):
            try:
                self.finance_combat_manager.clear_summoning_sickness(player_id)
            except Exception:
                pass

        events.extend(self._emit_phase("pre_market", "end", player_id))
        return events

    # ------------------------------------------------------------------
    # Phase 2: RESEARCH
    # ------------------------------------------------------------------

    async def _run_research(self, player_id: str) -> list[Event]:
        """
        RESEARCH:
        - Emit PHASE_START
        - Draw 1 card. If library is empty, take 1 fatigue damage.
        - Emit PHASE_END
        """
        events: list[Event] = []
        events.extend(self._emit_phase("research", "start", player_id))

        library = self._get_library(player_id)
        if library:
            events.extend(await self._draw_card(player_id))
        else:
            player = self.state.players.get(player_id)
            if player is not None:
                player.fatigue_damage = getattr(player, "fatigue_damage", 0) + 1
                events.extend(
                    await self._emit_fatigue(player_id, player.fatigue_damage)
                )

        self._check_game_over()
        events.extend(self._emit_phase("research", "end", player_id))
        return events

    # ------------------------------------------------------------------
    # Phase 3: TRADING SESSION
    # ------------------------------------------------------------------

    async def _run_trading_session(self, player_id: str) -> list[Event]:
        """
        TRADING SESSION:
        - Emit PHASE_START
        - Pre-combat action window (play cards, activate abilities)
        - Declare Attackers
        - Declare Blockers (opponent)
        - Resolve combat damage
        - Post-combat SBA check
        - Emit PHASE_END
        """
        events: list[Event] = []
        events.extend(self._emit_phase("trading_session", "start", player_id))

        # Pre-combat action loop.
        events.extend(await self._action_loop(player_id))
        if self._is_game_over():
            events.extend(self._emit_phase("trading_session", "end", player_id))
            return events

        # Combat sub-phase.
        events.extend(await self._run_combat(player_id))

        self._check_game_over()
        events.extend(self._emit_phase("trading_session", "end", player_id))
        return events

    async def _run_combat(self, player_id: str) -> list[Event]:
        """Declare attackers → declare blockers → resolve damage."""
        events: list[Event] = []
        opponent_id = self._get_opponent(player_id)
        if opponent_id is None:
            return events

        combat_mgr = self.finance_combat_manager
        if combat_mgr is None:
            # finance_combat.py not yet available — skip gracefully.
            return events

        # Declare attackers.
        # Human attackers are declared within the TRADING_SESSION action loop via
        # FIN_DECLARE_ATTACKERS; we don't prompt again here so FIN_END_TURN cleanly
        # advances to SETTLEMENT in one step.
        attackers: list[str] = list(self.fin_turn_state.attackers_declared)
        if self._is_ai_player(player_id):
            ai = self._get_ai(player_id)
            if ai is not None:
                result = self._call_ai(ai, "choose_attackers", self.state, player_id)
                attackers = await self._maybe_await(result) or []

        self.fin_turn_state.attackers_declared = list(attackers)

        decl_events = await self._invoke_combat(
            combat_mgr, "declare_attackers", player_id, attackers
        )
        events.extend(decl_events)
        self._check_game_over()
        if self._is_game_over():
            return events

        if not attackers:
            # No attackers — skip blocker declaration and damage.
            return events

        # Declare blockers (opponent).
        blocks: dict[str, str] = {}
        if self._is_ai_player(opponent_id):
            ai = self._get_ai(opponent_id)
            if ai is not None:
                result = self._call_ai(
                    ai, "choose_blockers", self.state, opponent_id, attackers
                )
                blocks = await self._maybe_await(result) or {}
        elif self.human_action_handler is not None:
            action = await self.human_action_handler(opponent_id, self.state)
            atype = action.get("action_type", "") if action else ""
            if atype == ACTION_DECLARE_BLOCKERS:
                blocks = dict(action.get("blocks", {}))
            # FIN_END_TURN or any other action = pass (no blocks)

        self.fin_turn_state.combat_blocks = dict(blocks)

        block_events = await self._invoke_combat(
            combat_mgr, "declare_blockers", opponent_id, blocks
        )
        events.extend(block_events)
        self._check_game_over()
        if self._is_game_over():
            return events

        # Resolve combat damage.
        dmg_events = await self._invoke_combat(
            combat_mgr,
            "resolve_combat_damage",
            attackers,
            blocks,
            opponent_id,
        )
        events.extend(dmg_events)

        # Post-combat SBA: liquidate Traders with fatal damage.
        self._check_game_over()

        return events

    # ------------------------------------------------------------------
    # Phase 4: SETTLEMENT
    # ------------------------------------------------------------------

    async def _run_settlement(self, player_id: str) -> list[Event]:
        """
        SETTLEMENT:
        - Emit PHASE_START
        - Post-combat action loop (same structure as pre-combat)
        - Emit PHASE_END
        """
        events: list[Event] = []
        events.extend(self._emit_phase("settlement", "start", player_id))

        events.extend(await self._action_loop(player_id))

        self._check_game_over()
        events.extend(self._emit_phase("settlement", "end", player_id))
        return events

    # ------------------------------------------------------------------
    # Phase 5: MARKET CLOSE
    # ------------------------------------------------------------------

    async def _run_market_close(self, player_id: str) -> list[Event]:
        """
        MARKET CLOSE:
        - Emit PHASE_START (fires Leverage-tick and end-step trigger interceptors)
        - Discard down to hand limit (7)
        - Clear "until end of turn" PT modifiers, abilities, and interceptors
        - Check win condition (Capital Reserve ≤ 0)
        - Emit PHASE_END
        """
        events: list[Event] = []
        # PHASE_START fires leverage-tick and any "at the beginning of
        # your Market Close" interceptors registered by cards in finance.py.
        events.extend(self._emit_phase("market_close", "start", player_id))

        # Discard to hand limit.
        hand = self._get_hand(player_id)
        while len(hand) > _DEFAULT_HAND_LIMIT:
            discard_id = self._choose_discard(player_id, hand)
            if discard_id is None:
                break
            events.extend(await self._discard_card(player_id, discard_id))
            hand = self._get_hand(player_id)

        # Clear end-of-turn PT modifiers on battlefield objects.
        self._sweep_eot_modifiers()

        # Final win-condition check.
        self._check_game_over()

        events.extend(self._emit_phase("market_close", "end", player_id))
        return events

    # ------------------------------------------------------------------
    # Action loop (pre-combat / post-combat)
    # ------------------------------------------------------------------

    async def _action_loop(self, player_id: str) -> list[Event]:
        """Drive AI / human play actions until the player passes."""
        events: list[Event] = []
        is_ai = self._is_ai_player(player_id)
        ai = self._get_ai(player_id)

        for _ in range(_ACTION_LOOP_CAP):
            if self._is_game_over():
                break

            if is_ai and ai is not None:
                result = self._call_ai(ai, "choose_play_action", self.state, player_id)
                action = await self._maybe_await(result)
            elif self.human_action_handler is not None:
                action = await self.human_action_handler(player_id, self.state)
            else:
                break

            if action is None:
                break

            action_type = action.get("type") or action.get("action_type", "")
            if action_type in ("end_phase", "end_turn", ACTION_END_PHASE, ACTION_END_TURN):
                break

            if action_type in ("play_card", ACTION_PLAY_CARD):
                card_id = action.get("card_id")
                targets = action.get("targets", [])
                if card_id:
                    play_events = await self._play_card_action(
                        player_id, card_id, targets
                    )
                    events.extend(play_events)

            elif action_type in ("activate_ability", ACTION_ACTIVATE):
                source_id = action.get("source_id")
                ability_index = action.get("ability_index", 0)
                targets = action.get("targets", [])
                events.extend(
                    await self._activate_ability(player_id, source_id, ability_index, targets)
                )

            elif action_type == ACTION_DECLARE_ATTACKERS:
                # Human declares which traders attack; stored for _run_combat to consume.
                raw = action.get("attackers", [])
                self.fin_turn_state.attackers_declared = [
                    a["attacker_id"] if isinstance(a, dict) else str(a) for a in raw
                ]

            # SBA check after each action.
            self._check_game_over()
            if self._is_game_over():
                break

        return events

    # ------------------------------------------------------------------
    # Card play
    # ------------------------------------------------------------------

    async def _play_card_action(
        self,
        player_id: str,
        card_id: str,
        targets: list,
    ) -> list[Event]:
        """Validate cost, emit FIN_PLAY_CARD, deduct Liquidity, resolve effect."""
        import re as _re
        events: list[Event] = []

        obj = self.state.objects.get(card_id)
        if obj is None:
            return events

        player = self.state.players.get(player_id)
        if player is None:
            return events

        if not self._card_is_in_player_hand(player_id, card_id):
            return events

        # Compute mana cost (simple numeric extraction — finance uses {N}).
        cost = 0
        if obj.characteristics and obj.characteristics.mana_cost:
            nums = _re.findall(r'\{(\d+)\}', obj.characteristics.mana_cost)
            cost = sum(int(n) for n in nums)

        # Dynamic cost override.
        if (
            getattr(obj, "card_def", None) is not None
            and hasattr(obj.card_def, "dynamic_cost")
            and obj.card_def.dynamic_cost
        ):
            try:
                cost = obj.card_def.dynamic_cost(obj, self.state)
            except Exception:
                pass

        # Cost modifiers (discount effects).
        for mod in getattr(player, "cost_modifiers", []):
            if mod.get("amount"):
                cost = max(0, cost + mod["amount"])

        # bug #28: apply registered QUERY_COST cost-reduction interceptors
        # (e.g. Dark Flow Engine "Dark Pool Orders cost {1} less"). Without this
        # call, those interceptors are registered but never consulted.
        try:
            from .cost_query import get_effective_mana_cost as _gemc
            from .mana import ManaCost as _ManaCost
            base = _ManaCost(generic=cost)
            reduced = _gemc(obj, player_id, self.state, base_cost=base)
            cost = max(0, reduced.generic)
        except Exception:
            pass

        # Liquidity check.
        if player.mana_crystals_available < cost:
            return events

        # bug #13: Off-Exchange Position (and other DP-consumer cards) must
        # refuse to cast when no Dark Pool slot is populated. Check prerequisite
        # via card_def._dark_pool_consumer flag OR explicit cast_prerequisite hook.
        cd_pre = getattr(obj, "card_def", None)
        if cd_pre is not None:
            consumer = getattr(cd_pre, "_dark_pool_consumer", False)
            prereq_fn = getattr(cd_pre, "cast_prerequisite", None)
            if consumer:
                from .finance import get_dark_pool as _get_dp
                if _get_dp(self.state) is None:
                    # Refuse to cast — no DP slot populated. Caller sees no events.
                    return events
            if callable(prereq_fn):
                try:
                    if not prereq_fn(obj, self.state):
                        return events
                except Exception:
                    pass

        # Deduct Liquidity.
        player.mana_crystals_available -= cost

        # Emit FIN_PLAY_CARD marker event.
        # bug #15 (secondary): include both "player" and "controller" keys so
        # card-level filters (Hidden Accumulator) reading "controller" match.
        fin_et = getattr(EventType, "FIN_PLAY_CARD", None) or EventType.ZONE_CHANGE
        play_event = Event(
            type=fin_et,
            payload={
                "card_id": card_id,
                "object_id": card_id,
                "player": player_id,
                "controller": player_id,
                "cost": cost,
                "targets": list(targets),
            },
            source=card_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(play_event)
        events.append(play_event)

        # Notify external observers (e.g. server market feed) when an AI
        # plays a card, so the human player can see it in the log.
        if self._is_ai_player(player_id) and self.action_log_handler is not None:
            try:
                self.action_log_handler(player_id, "play_card", obj)
            except Exception:
                pass

        # Move card to battlefield (for Traders / Assets / Structures) or
        # graveyard (for Orders / Strategies) via ZONE_CHANGE.
        from .types import CardType
        fin_trader    = getattr(CardType, "FIN_TRADER",    None)
        fin_order     = getattr(CardType, "FIN_ORDER",     None)
        fin_strategy  = getattr(CardType, "FIN_STRATEGY",  None)
        fin_asset     = getattr(CardType, "FIN_ASSET",     None)
        fin_structure = getattr(CardType, "FIN_STRUCTURE", None)
        fin_deriv     = getattr(CardType, "FIN_DERIVATIVE", None)

        card_types = (
            obj.characteristics.types if obj.characteristics else set()
        )

        # Permanents → Trading Floor (battlefield).
        is_permanent = any(
            t in card_types
            for t in (fin_trader, fin_asset, fin_structure, fin_deriv)
            if t is not None
        )
        # One-shots → Liquidated (graveyard).
        is_oneshot = any(
            t in card_types
            for t in (fin_order, fin_strategy)
            if t is not None
        )

        if is_permanent:
            zone_ev = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": card_id,
                    "from_zone": f"hand_{player_id}",
                    "from_zone_type": ZoneType.HAND,
                    "to_zone": "battlefield",
                    "to_zone_type": ZoneType.BATTLEFIELD,
                },
                source=card_id,
            )
            if (pl := self._emit_pipeline):
                pl.emit(zone_ev)
            events.append(zone_ev)
            # Mark summoning sickness on Traders.
            re_obj = self.state.objects.get(card_id)
            if re_obj and fin_trader and fin_trader in card_types:
                if hasattr(re_obj.state, "summoning_sickness"):
                    re_obj.state.summoning_sickness = True

            # Auto-attach logic: wire the ATTACH event so stat interceptors fire.
            if fin_deriv and fin_deriv in card_types:
                # A Derivative just ETB'd — attach it to the best Trader.
                events.extend(
                    await self._attach_derivative_to_trader(card_id, player_id)
                )
            elif fin_trader and fin_trader in card_types:
                # A Trader just ETB'd — attach any staged Derivatives from desk.
                events.extend(
                    await self._attach_desk_derivatives_to_trader(card_id, player_id)
                )

        elif is_oneshot:
            # bug #15: route Dark Pool Orders to the DP slot via set_dark_pool
            # instead of straight-to-graveyard. The card object stays alive in
            # ZoneType.EXILE as a hidden staging zone (mirrors Dark Flow Aggregator).
            card_def = getattr(obj, "card_def", None)
            is_dp = bool(card_def and getattr(card_def, "_dark_pool", False))
            if is_dp:
                from .finance import get_dark_pool, set_dark_pool

                # If DP slot occupied, the new card overwrites the old (last-in wins).
                # Move the displaced order to graveyard so it doesn't leak.
                existing = get_dark_pool(self.state)
                if existing is not None:
                    old = self.state.objects.get(existing)
                    if old is not None:
                        old.zone = ZoneType.GRAVEYARD
                        gz = self.state.zones.get(f"graveyard_{old.controller}")
                        if gz is not None and existing not in gz.objects:
                            gz.objects.append(existing)
                    set_dark_pool(self.state, None)

                # Move the staged card out of hand into hidden staging (EXILE proxy).
                hand_zone = self.state.zones.get(f"hand_{player_id}")
                if hand_zone and card_id in hand_zone.objects:
                    hand_zone.objects.remove(card_id)
                obj.zone = ZoneType.EXILE
                set_dark_pool(self.state, card_id)
                # Track DP play count (used by Liquidity Event etc.)
                key = f"fin_dp_played_{player_id}"
                self.state.turn_data[key] = self.state.turn_data.get(key, 0) + 1
                # Run setup_interceptors NOW so dark_pool_setup registers the
                # card-level FIN_MARKET_EVENT REACT trigger before the next
                # PHASE_START(trading_session) fires the system interceptor.
                if card_def and getattr(card_def, "setup_interceptors", None):
                    try:
                        ics = card_def.setup_interceptors(obj, self.state)
                        if ics:
                            game = getattr(self, "game", None)
                            for ic in ics:
                                obj.interceptor_ids.append(ic.id)
                                if game is not None and hasattr(game, "register_interceptor"):
                                    game.register_interceptor(ic)
                                elif (pl := self._emit_pipeline) is not None:
                                    # Fallback: register via pipeline's interceptor list.
                                    if hasattr(pl, "register_interceptor"):
                                        pl.register_interceptor(ic)
                                    elif hasattr(pl, "interceptors"):
                                        pl.interceptors.append(ic)
                    except Exception:
                        pass
                # No graveyard event for staged DP Orders — they leave the slot
                # only when the system interceptor fires FIN_MARKET_EVENT.
            else:
                # Non-DP Orders/Strategies push onto the FinanceStack and
                # the opponent gets a priority window before resolution.
                # The resolve_fn / ZONE_CHANGE-to-graveyard path runs in
                # ``_resolve_stack_top``.
                from .finance_stack import FinanceStackItem

                # Move card out of hand into a "casting" zone (still
                # battlefield-adjacent — Dark Pool already does this with
                # EXILE; we use the same approach for stack residency).
                hand_zone = self.state.zones.get(f"hand_{player_id}")
                if hand_zone and card_id in hand_zone.objects:
                    hand_zone.objects.remove(card_id)

                stack_item = FinanceStackItem(
                    card_id=card_id,
                    controller=player_id,
                    targets=list(targets),
                    resolve_fn=getattr(card_def, "resolve", None) if card_def else None,
                    is_response=False,
                    cost_paid=cost,
                )
                self.fin_stack.push(stack_item)

                # FIN_CARD_CAST signals the frontend to play "order placed".
                cast_ev = Event(
                    type=EventType.FIN_CARD_CAST,
                    payload={
                        "card_id": card_id,
                        "controller": player_id,
                        "is_response": False,
                        "stack_depth": self.fin_stack.depth(),
                    },
                    source=card_id,
                    controller=player_id,
                )
                if (pl := self._emit_pipeline):
                    pl.emit(cast_ev)
                events.append(cast_ev)
                if self.action_log_handler is not None:
                    try:
                        self.action_log_handler(player_id, "fin_card_cast", obj)
                    except Exception:
                        pass

                # Run the priority loop — opponent may push responses.
                opponent_id = self._get_opponent(player_id)
                if opponent_id:
                    events.extend(await self._run_priority_loop(opponent_id))

                # Resolve the stack LIFO until empty.
                events.extend(await self._resolve_stack())

        # Track cards played this turn.
        if hasattr(player, "cards_played_this_turn"):
            player.cards_played_this_turn += 1

        self._check_game_over()
        return events

    # ------------------------------------------------------------------
    # Stack: priority loop + LIFO resolve
    # ------------------------------------------------------------------

    async def _run_priority_loop(self, start_player_id: str) -> list[Event]:
        """Alternate priority between players until both pass.

        On each pass we ask `start_player_id` whether they want to play a
        responding Order. If yes, we cast it onto the stack and switch
        priority to the opponent. If they pass, we exit the loop.

        Strategies cannot be played as responses — only Orders. Per the
        plan: "if response.card not Order: break". This is enforced in
        ``_poll_response`` (the AI is asked to pick an Order; humans are
        UI-gated).
        """
        events: list[Event] = []
        current = start_player_id
        # Bound the loop to keep tournaments terminating even if an AI
        # bugs into infinite repush.
        for _ in range(_ACTION_LOOP_CAP):
            response = await self._poll_response(current)
            if response is None:
                break
            atype = response.get("action_type") or response.get("type", "")
            if atype in (ACTION_PASS_RESPONSE, "pass", "FIN_PASS"):
                break
            if atype not in (ACTION_PLAY_RESPONSE, "play_response"):
                # Anything other than play_response is treated as pass.
                break
            card_id = response.get("card_id")
            targets = response.get("targets", [])
            if not card_id:
                break
            cast_events = await self._cast_response_to_stack(
                current, card_id, targets
            )
            if not cast_events:
                # Cast failed (cost, illegal target, not an Order, etc.) —
                # treat as a pass so we don't loop forever.
                break
            events.extend(cast_events)
            current = self._get_opponent(current) or current
        return events

    async def _poll_response(self, player_id: str) -> Optional[dict]:
        """Ask `player_id` whether they want to respond to the top of stack.

        Returns the action dict, or None to pass. AI players decide
        synchronously via ``choose_response_action``; humans round-trip
        via ``human_action_handler``.
        """
        if self.fin_stack.is_empty():
            return None
        if self._is_ai_player(player_id):
            ai = self._get_ai(player_id)
            if ai is None or not hasattr(ai, "choose_response_action"):
                return None
            top = self.fin_stack.peek()
            try:
                result = ai.choose_response_action(self.state, player_id, top)
            except Exception:
                return None
            return await self._maybe_await(result)
        if self.human_action_handler is not None:
            self.fin_turn_state.pending_response_player = player_id
            try:
                action = await self.human_action_handler(player_id, self.state)
            except Exception:
                return None
            finally:
                self.fin_turn_state.pending_response_player = None
            if action is None:
                return None
            atype = action.get("action_type") or action.get("type", "")
            # Only response-flavored actions are honored; anything else
            # (e.g. play_card, end_turn) is treated as a pass at this
            # priority window.
            if atype in (
                ACTION_PLAY_RESPONSE,
                ACTION_PASS_RESPONSE,
                "play_response",
                "pass",
                "FIN_PASS",
            ):
                return action
            return None
        return None

    async def _cast_response_to_stack(
        self,
        player_id: str,
        card_id: str,
        targets: list,
    ) -> list[Event]:
        """Cast a responding Order onto the stack. Mirrors the cost-pay
        and FIN_PLAY_CARD emission of ``_play_card_action`` for spells."""
        import re as _re
        from .finance_stack import FinanceStackItem
        from .types import CardType

        events: list[Event] = []
        obj = self.state.objects.get(card_id)
        if obj is None:
            return events
        player = self.state.players.get(player_id)
        if player is None:
            return events

        if not self._card_is_in_player_hand(player_id, card_id):
            return events

        # Only Orders can be played as responses.
        fin_order = getattr(CardType, "FIN_ORDER", None)
        if fin_order is None:
            return events
        card_types = obj.characteristics.types if obj.characteristics else set()
        if fin_order not in card_types:
            return events

        # Compute cost (same path as _play_card_action).
        cost = 0
        if obj.characteristics and obj.characteristics.mana_cost:
            nums = _re.findall(r'\{(\d+)\}', obj.characteristics.mana_cost)
            cost = sum(int(n) for n in nums)
        if (
            getattr(obj, "card_def", None) is not None
            and hasattr(obj.card_def, "dynamic_cost")
            and obj.card_def.dynamic_cost
        ):
            try:
                cost = obj.card_def.dynamic_cost(obj, self.state)
            except Exception:
                pass
        for mod in getattr(player, "cost_modifiers", []):
            if mod.get("amount"):
                cost = max(0, cost + mod["amount"])
        if player.mana_crystals_available < cost:
            return events

        card_def = getattr(obj, "card_def", None)
        # Dark Pool Orders cannot be played as responses (they stage,
        # they don't resolve). Skip for now — stack semantics don't fit.
        if card_def and getattr(card_def, "_dark_pool", False):
            return events

        # Pay the cost and remove from hand.
        player.mana_crystals_available -= cost
        hand_zone = self.state.zones.get(f"hand_{player_id}")
        if hand_zone and card_id in hand_zone.objects:
            hand_zone.objects.remove(card_id)

        # Emit FIN_PLAY_CARD marker (existing card filters expect this).
        play_event = Event(
            type=EventType.FIN_PLAY_CARD,
            payload={
                "card_id": card_id,
                "object_id": card_id,
                "player": player_id,
                "controller": player_id,
                "cost": cost,
                "targets": list(targets),
            },
            source=card_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(play_event)
        events.append(play_event)

        if self._is_ai_player(player_id) and self.action_log_handler is not None:
            try:
                self.action_log_handler(player_id, "play_response", obj)
            except Exception:
                pass

        # Push onto the stack.
        stack_item = FinanceStackItem(
            card_id=card_id,
            controller=player_id,
            targets=list(targets),
            resolve_fn=getattr(card_def, "resolve", None) if card_def else None,
            is_response=True,
            cost_paid=cost,
        )
        self.fin_stack.push(stack_item)

        cast_ev = Event(
            type=EventType.FIN_CARD_CAST,
            payload={
                "card_id": card_id,
                "controller": player_id,
                "is_response": True,
                "stack_depth": self.fin_stack.depth(),
            },
            source=card_id,
            controller=player_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(cast_ev)
        events.append(cast_ev)
        if self.action_log_handler is not None:
            try:
                self.action_log_handler(player_id, "fin_card_cast", obj)
            except Exception:
                pass

        if hasattr(player, "cards_played_this_turn"):
            player.cards_played_this_turn += 1

        return events

    async def _resolve_stack(self) -> list[Event]:
        """Pop and resolve all stack items LIFO. Countered items skip
        the resolve_fn but still go to the graveyard with a
        FIN_CARD_COUNTERED event."""
        events: list[Event] = []
        # Bound to prevent runaway infinite resolution.
        for _ in range(_ACTION_LOOP_CAP):
            item = self.fin_stack.pop()
            if item is None:
                break
            events.extend(self._resolve_stack_item(item))
        return events

    def _resolve_stack_item(self, item) -> list[Event]:
        """Resolve a single stack item. Mirrors the inner block of the
        old ``_play_card_action`` is_oneshot path."""
        events: list[Event] = []
        card_id = item.card_id
        player_id = item.controller
        targets = list(item.targets)

        obj = self.state.objects.get(card_id)
        card_def = getattr(obj, "card_def", None) if obj else None

        if item.countered:
            counter_ev = Event(
                type=EventType.FIN_CARD_COUNTERED,
                payload={
                    "card_id": card_id,
                    "controller": player_id,
                },
                source=card_id,
                controller=player_id,
            )
            if (pl := self._emit_pipeline):
                pl.emit(counter_ev)
            events.append(counter_ev)
            if self.action_log_handler is not None:
                try:
                    self.action_log_handler(player_id, "fin_card_countered", obj)
                except Exception:
                    pass
        else:
            # Run effect via resolve_fn (FINA convention) or legacy
            # spell_effect/cast_effect/effect for compatibility.
            resolve_fn = item.resolve_fn or (
                getattr(card_def, "resolve", None) if card_def else None
            )
            if callable(resolve_fn):
                try:
                    if (pl := self._emit_pipeline):
                        pl.sba_deferred = True
                    target_id = None
                    if targets:
                        first = targets[0]
                        if isinstance(first, list) and first:
                            target_id = first[0]
                        elif isinstance(first, str):
                            target_id = first
                    resolve_event = Event(
                        type=EventType.FIN_PLAY_CARD,
                        payload={
                            "controller": player_id,
                            "source_id": card_id,
                            "target_id": target_id,
                            "targets": list(targets),
                        },
                        source=card_id,
                        controller=player_id,
                    )
                    effect_events = resolve_fn(resolve_event, self.state) or []
                    for ev in effect_events:
                        if (pl := self._emit_pipeline):
                            pl.emit(ev)
                        events.append(ev)
                except Exception:
                    pass
                finally:
                    if (pl := self._emit_pipeline):
                        pl.sba_deferred = False
            elif card_def is not None:
                for attr in ("spell_effect", "cast_effect", "effect"):
                    fn = getattr(card_def, attr, None)
                    if callable(fn):
                        try:
                            if (pl := self._emit_pipeline):
                                pl.sba_deferred = True
                            effect_events = fn(obj, self.state, targets)
                            for ev in effect_events:
                                if (pl := self._emit_pipeline):
                                    pl.emit(ev)
                                events.append(ev)
                        except Exception:
                            pass
                        finally:
                            if (pl := self._emit_pipeline):
                                pl.sba_deferred = False
                        break

            resolved_ev = Event(
                type=EventType.FIN_CARD_RESOLVED,
                payload={
                    "card_id": card_id,
                    "controller": player_id,
                },
                source=card_id,
                controller=player_id,
            )
            if (pl := self._emit_pipeline):
                pl.emit(resolved_ev)
            events.append(resolved_ev)
            if self.action_log_handler is not None:
                try:
                    self.action_log_handler(player_id, "fin_card_resolved", obj)
                except Exception:
                    pass

        # Move card to graveyard regardless of countered state.
        grv_ev = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": card_id,
                # The card is no longer in hand by this point — it was
                # removed when it went onto the stack. We still emit the
                # ZONE_CHANGE so the pipeline runs cleanup interceptors.
                "from_zone": "stack",
                "from_zone_type": ZoneType.STACK if hasattr(ZoneType, "STACK") else ZoneType.HAND,
                "to_zone": f"graveyard_{player_id}",
                "to_zone_type": ZoneType.GRAVEYARD,
            },
            source=card_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(grv_ev)
        events.append(grv_ev)

        self._check_game_over()
        return events

    # ------------------------------------------------------------------
    # Derivative attachment helpers
    # ------------------------------------------------------------------

    async def _attach_derivative_to_trader(
        self, derivative_id: str, player_id: str
    ) -> list[Event]:
        """After a Derivative enters the battlefield, auto-attach to the best
        available Trader (highest power, no summoning sickness).

        Emits a proper ATTACH event so ``_handle_attach`` in attach.py writes
        ``source.state.attached_to = target_id`` and the Derivative's
        QUERY_POWER / QUERY_TOUGHNESS interceptors become live.
        """
        from .types import CardType

        fin_trader = getattr(CardType, "FIN_TRADER", None)
        if fin_trader is None:
            return []

        bf = self.state.zones.get("battlefield")
        if not bf:
            return []

        # Skip if the derivative is already attached.
        deriv_obj = self.state.objects.get(derivative_id)
        if deriv_obj and getattr(deriv_obj.state, "attached_to", None):
            return []

        best_trader = None
        best_power = -1
        for oid in bf.objects:
            obj = self.state.objects.get(oid)
            if obj is None:
                continue
            if obj.controller != player_id:
                continue
            if fin_trader not in obj.characteristics.types:
                continue
            # Prefer active (non-summoning-sick) Traders; still allow sick ones
            # as a fallback — the Derivative grants stats regardless.
            p = obj.characteristics.power or 0
            if p > best_power:
                best_power = p
                best_trader = obj

        if best_trader is None:
            return []

        # Remove from staging desk; once attached the desk no longer tracks it.
        try:
            from .finance import remove_from_deriv_desk
            remove_from_deriv_desk(self.state, player_id, derivative_id)
        except ImportError:
            pass

        attach_event = Event(
            type=EventType.ATTACH,
            payload={
                "object_id": derivative_id,
                "target_id": best_trader.id,
            },
            source=derivative_id,
            controller=player_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(attach_event)
        return [attach_event]

    async def _attach_desk_derivatives_to_trader(
        self, trader_id: str, player_id: str
    ) -> list[Event]:
        """After a Trader enters the battlefield, attach any staged Derivatives
        from the player's Derivatives Desk to it.

        Emits one ATTACH event per Derivative and removes each from the desk.
        """
        try:
            from .finance import get_deriv_desk, remove_from_deriv_desk
        except ImportError:
            return []

        desk = get_deriv_desk(self.state, player_id)
        events: list[Event] = []
        for deriv_id in list(desk):
            deriv_obj = self.state.objects.get(deriv_id)
            if deriv_obj is None:
                continue
            # Only attach un-attached Derivatives.
            if getattr(deriv_obj.state, "attached_to", None):
                continue
            remove_from_deriv_desk(self.state, player_id, deriv_id)
            attach_event = Event(
                type=EventType.ATTACH,
                payload={
                    "object_id": deriv_id,
                    "target_id": trader_id,
                },
                source=deriv_id,
                controller=player_id,
            )
            if (pl := self._emit_pipeline):
                pl.emit(attach_event)
            events.append(attach_event)

        return events

    # ------------------------------------------------------------------
    # Activated abilities
    # ------------------------------------------------------------------

    async def _activate_ability(
        self,
        player_id: str,
        source_id: Optional[str],
        ability_index: int,
        targets: list,
    ) -> list[Event]:
        """Dispatch an activated ability on source_id to the engine."""
        events: list[Event] = []
        if source_id is None:
            return events

        obj = self.state.objects.get(source_id)
        if obj is None:
            return events

        # Delegate to finance.py's activate_ability if available.
        if _HAS_FINANCE_MODULE:
            try:
                from .finance import activate_ability as _fin_activate  # type: ignore
                result = _fin_activate(
                    self.state, player_id, source_id,
                    ability_index=ability_index, targets=targets
                )
                if isinstance(result, list):
                    for ev in result:
                        if (pl := self._emit_pipeline):
                            pl.emit(ev)
                        events.append(ev)
            except Exception:
                pass

        return events

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------

    def _sweep_eot_modifiers(self) -> None:
        """Remove PT modifiers, temporary abilities, and interceptors whose
        duration is end-of-turn. Mirrors the equivalent sweep in turn.py
        and depths_turn.py."""
        eot_aliases = {
            "end_of_turn", "until_end_of_turn", "until_eot", "eot",
            "next_end_step", "end_of_this_turn", "this_turn",
        }

        battlefield = self.state.zones.get("battlefield")
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj is None:
                    continue
                # Clear PT modifiers.
                if hasattr(obj.state, "pt_modifiers") and obj.state.pt_modifiers:
                    obj.state.pt_modifiers = [
                        m for m in obj.state.pt_modifiers
                        if str(m.get("duration", "")).strip().lower().replace(" ", "_")
                        not in eot_aliases
                    ]
                # Clear temporary ability grants.
                if obj.characteristics and obj.characteristics.abilities:
                    obj.characteristics.abilities = [
                        a for a in obj.characteristics.abilities
                        if not (
                            isinstance(a, dict)
                            and a.get("_temporary") is True
                            and a.get("_duration") == "end_of_turn"
                        )
                    ]
                # Revert end-of-turn control changes.
                if hasattr(obj.state, "_restore_controller_eot"):
                    obj.controller = getattr(obj.state, "_restore_controller_eot")
                    delattr(obj.state, "_restore_controller_eot")

        # Sweep duration='end_of_turn' interceptors from state.interceptors.
        to_remove = [
            iid for iid, ic in self.state.interceptors.items()
            if isinstance(getattr(ic, "duration", None), str)
            and ic.duration.strip().lower().replace(" ", "_") in eot_aliases
        ]
        for iid in to_remove:
            ic = self.state.interceptors.pop(iid, None)
            if ic is not None:
                src = self.state.objects.get(getattr(ic, "source", None))
                if src is not None and iid in src.interceptor_ids:
                    src.interceptor_ids.remove(iid)

        # Clear 'this_turn' cost modifiers.
        for player in self.state.players.values():
            mods = getattr(player, "cost_modifiers", None)
            if mods is not None:
                player.cost_modifiers = [
                    m for m in mods if m.get("duration") != "this_turn"
                ]

    # ------------------------------------------------------------------
    # Game-over / SBA
    # ------------------------------------------------------------------

    def _is_game_over(self) -> bool:
        """True if any player has_lost."""
        game = getattr(self.state, "_game", None)
        if game is not None and hasattr(game, "is_game_over"):
            try:
                return bool(game.is_game_over())
            except Exception:
                pass
        alive = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive) <= 1

    def _check_game_over(self) -> None:
        """Set has_lost on any player whose Capital Reserve reached 0, and
        emit PLAYER_LOSES + FIN_BANKRUPTCY events."""
        fin_bankrupt = getattr(EventType, "FIN_BANKRUPTCY", None)

        for player in list(self.state.players.values()):
            if player.has_lost:
                continue
            if player.life <= 0:
                player.has_lost = True

                lose_ev = Event(
                    type=EventType.PLAYER_LOSES,
                    payload={"player": player.id, "reason": "bankruptcy"},
                )
                if (pl := self._emit_pipeline):
                    pl.emit(lose_ev)

                if fin_bankrupt is not None:
                    bankrupt_ev = Event(
                        type=fin_bankrupt,
                        payload={"player": player.id},
                    )
                    if (pl := self._emit_pipeline):
                        pl.emit(bankrupt_ev)

    # ------------------------------------------------------------------
    # Turn-pointer advancement
    # ------------------------------------------------------------------

    def _advance_turn(self) -> None:
        """Advance current_player_index to the next player in turn order."""
        if self.turn_order:
            self.current_player_index = (
                (self.current_player_index + 1) % len(self.turn_order)
            )

    # ------------------------------------------------------------------
    # Zone helpers
    # ------------------------------------------------------------------

    def _get_library(self, player_id: str) -> list[str]:
        """Return list of object IDs in player's library (deck)."""
        zone = self.state.zones.get(f"library_{player_id}")
        if zone is None:
            return []
        return list(zone.objects)

    def _get_hand(self, player_id: str) -> list[str]:
        """Return list of object IDs in player's hand."""
        zone = self.state.zones.get(f"hand_{player_id}")
        if zone is None:
            return []
        return list(zone.objects)

    def _card_is_in_player_hand(self, player_id: str, card_id: str) -> bool:
        """Return True only for cards owned/controlled by player_id in their hand."""
        obj = self.state.objects.get(card_id)
        if obj is None:
            return False
        if obj.owner != player_id or obj.controller != player_id:
            return False
        if obj.zone != ZoneType.HAND:
            return False
        return card_id in self._get_hand(player_id)

    def _get_opponent(self, player_id: str) -> Optional[str]:
        """Return the other player's ID."""
        for pid in self.turn_order:
            if pid != player_id:
                return pid
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return None

    # ------------------------------------------------------------------
    # Card movement events
    # ------------------------------------------------------------------

    async def _draw_card(self, player_id: str) -> list[Event]:
        """Emit DRAW event; the pipeline's DRAW handler moves the card."""
        draw_ev = Event(
            type=EventType.DRAW,
            payload={"player": player_id, "count": 1},
        )
        if (pl := self._emit_pipeline):
            pl.emit(draw_ev)
        return [draw_ev]

    async def _discard_card(self, player_id: str, card_id: str) -> list[Event]:
        """Move card_id from hand to graveyard via ZONE_CHANGE (discard)."""
        events: list[Event] = []

        discard_ev = Event(
            type=EventType.DISCARD,
            payload={"player": player_id, "card_id": card_id},
            source=card_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(discard_ev)
        events.append(discard_ev)

        zone_ev = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": card_id,
                "from_zone": f"hand_{player_id}",
                "from_zone_type": ZoneType.HAND,
                "to_zone": f"graveyard_{player_id}",
                "to_zone_type": ZoneType.GRAVEYARD,
                "reason": "discard_hand_limit",
            },
            source=card_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(zone_ev)
        events.append(zone_ev)

        return events

    async def _emit_fatigue(self, player_id: str, amount: int) -> list[Event]:
        """Emit FATIGUE_DAMAGE + a LIFE_CHANGE to apply damage."""
        events: list[Event] = []

        fat_et = getattr(EventType, "FATIGUE_DAMAGE", EventType.LIFE_CHANGE)
        fatigue_ev = Event(
            type=fat_et,
            payload={"player": player_id, "amount": amount},
        )
        if (pl := self._emit_pipeline):
            pl.emit(fatigue_ev)
        events.append(fatigue_ev)

        # Apply Capital Reserve damage.
        life_ev = Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": player_id, "amount": -amount},
        )
        if (pl := self._emit_pipeline):
            pl.emit(life_ev)
        events.append(life_ev)

        return events

    # ------------------------------------------------------------------
    # Discard choice
    # ------------------------------------------------------------------

    def _choose_discard(self, player_id: str, hand: list[str]) -> Optional[str]:
        """Pick a card to discard. AI: lowest-cost card. Human: prompt."""
        if not hand:
            return None

        if self._is_ai_player(player_id):
            ai = self._get_ai(player_id)
            if ai is not None:
                result = self._call_ai(ai, "choose_discard", self.state, player_id, hand)
                if result is not None:
                    # choose_discard may be sync; return immediately.
                    return result if isinstance(result, str) else None
            # Fallback: discard last card in hand (least recent draw).
            return hand[-1]

        # Human: for now fall back to last card; the session layer will
        # override this with a proper prompt when human_action_handler is set.
        if self.human_action_handler is not None:
            # Cannot await here; session code should pre-drain discards before
            # calling run_turn. Fallback to random.
            return random.choice(hand)
        return hand[-1]

    # ------------------------------------------------------------------
    # Turn-start / turn-end events
    # These override the base TurnManager helpers so they use
    # fin_turn_state rather than the MTG turn_state.
    # ------------------------------------------------------------------

    async def _emit_turn_start(self) -> list[Event]:
        ev = Event(
            type=EventType.TURN_START,
            payload={
                "player": self.fin_turn_state.active_player_id,
                "turn_number": self.fin_turn_state.turn_number,
            },
        )
        if (pl := self._emit_pipeline):
            pl.emit(ev)
        return [ev]

    async def _emit_turn_end(self) -> list[Event]:
        ev = Event(
            type=EventType.TURN_END,
            payload={
                "player": self.fin_turn_state.active_player_id,
                "turn_number": self.fin_turn_state.turn_number,
            },
        )
        if (pl := self._emit_pipeline):
            pl.emit(ev)
        # Clear per-turn scratchpad, but keep Finance-persistent keys
        # (Derivatives Desk staging, Dark Pool, structure counts) which
        # are conceptually part of the board state, not per-turn flags.
        #
        # Bug #6 fix: also preserve ``fin_alpha_struck_alone_<player>`` so
        # Tick Data Archive's "attacked alone last turn" pre-market trigger
        # can read the flag on the controller's NEXT turn. The lifecycle is:
        #   - turn N (P1's turn): P1 alpha-strikes solo → flag set True.
        #   - turn N _emit_turn_end: WITHOUT this fix the flag was wiped.
        #   - turn N+1 (P2's turn) _emit_turn_end: also wipes anything new.
        #   - turn N+2 (P1's turn) pre_market: TDA reads flag → draws card,
        #     then flips flag to False (consumed). Without the preservation,
        #     TDA only ever saw a stale-or-absent flag and never fired.
        if hasattr(self.state, "turn_data"):
            persistent = {
                k: v for k, v in self.state.turn_data.items()
                if k.startswith("finance_deriv_desk_")
                or k.startswith("finance_structure_count_")
                or k == "finance_dark_pool"
                or k.startswith("fin_alpha_struck_alone_")
                # Bug #31: ``fin_dp_played_<player>`` tracks game-wide Dark Pool
                # Order play count for cards like Liquidity Event whose payoff
                # scales with total DPs cast over the entire game (not per-turn).
                # Without preservation, the counter resets every turn and
                # Liquidity Event always saw 0 (or just THIS turn's plays).
                or k.startswith("fin_dp_played_")
                # FINM Buyback text is cumulative: "Each Nth Order or Strategy
                # you cast..." The per-card count must not reset at turn end.
                or k.startswith("finm_buyback_count_")
            }
            self.state.turn_data.clear()
            self.state.turn_data.update(persistent)
        return [ev]

    # ------------------------------------------------------------------
    # Phase-event helper
    # ------------------------------------------------------------------

    def _emit_phase(self, phase: str, kind: str, player_id: str) -> list[Event]:
        """Emit PHASE_START or PHASE_END and return [event]."""
        ev_type = EventType.PHASE_START if kind == "start" else EventType.PHASE_END
        ev = Event(
            type=ev_type,
            payload={"phase": phase, "player": player_id},
        )
        if (pl := self._emit_pipeline):
            pl.emit(ev)
        return [ev]

    # ------------------------------------------------------------------
    # AI / combat utility helpers
    # ------------------------------------------------------------------

    def _call_ai(self, handler, method_name: str, *args):
        """Look up handler.method_name and call it. Returns result or None."""
        if handler is None:
            return None
        method = getattr(handler, method_name, None)
        if method is None:
            return None
        try:
            return method(*args)
        except TypeError:
            try:
                return method(args[0], args[1]) if len(args) >= 2 else method(*args)
            except Exception:
                return None

    @staticmethod
    async def _maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def _invoke_combat(self, mgr, method_name: str, *args) -> list[Event]:
        """Call a method on the combat manager and return its event list.

        Handles both sync and async combat-manager methods.
        """
        method = getattr(mgr, method_name, None)
        if method is None:
            return []
        try:
            result = method(*args)
        except TypeError:
            try:
                result = method(args[0]) if args else method()
            except Exception:
                return []
        if inspect.isawaitable(result):
            try:
                result = await result
            except Exception:
                return []
        if isinstance(result, list):
            return result
        if isinstance(result, tuple) and len(result) == 3:
            return result[2] if isinstance(result[2], list) else []
        return []

    # ------------------------------------------------------------------
    # MTG-compat overrides (no-ops for Finance)
    # ------------------------------------------------------------------

    async def _run_beginning_phase(self) -> list[Event]:
        return []

    async def _run_main_phase(self, *_, **__) -> list[Event]:
        return []

    async def _run_combat_phase(self) -> list[Event]:
        return []

    async def _run_ending_phase(self) -> list[Event]:
        return []

    # ------------------------------------------------------------------
    # Properties for client compatibility
    # ------------------------------------------------------------------

    @property
    def turn_number(self) -> int:
        return self.fin_turn_state.turn_number

    @property
    def active_player(self) -> Optional[str]:
        return self.fin_turn_state.active_player_id

    @property
    def phase(self) -> Phase:
        """Map FinancePhase to MTG Phase for client compatibility."""
        _map = {
            FinancePhase.PRE_MARKET:      Phase.BEGINNING,
            FinancePhase.RESEARCH:        Phase.BEGINNING,
            FinancePhase.TRADING_SESSION: Phase.PRECOMBAT_MAIN,
            FinancePhase.SETTLEMENT:      Phase.POSTCOMBAT_MAIN,
            FinancePhase.MARKET_CLOSE:    Phase.ENDING,
        }
        return _map.get(self.fin_turn_state.phase, Phase.PRECOMBAT_MAIN)

    @property
    def step(self) -> Step:
        """Map FinancePhase to Step for client compatibility."""
        _map = {
            FinancePhase.PRE_MARKET:      Step.UNTAP,
            FinancePhase.RESEARCH:        Step.DRAW,
            FinancePhase.TRADING_SESSION: Step.MAIN,
            FinancePhase.SETTLEMENT:      Step.MAIN,
            FinancePhase.MARKET_CLOSE:    Step.END_STEP,
        }
        return _map.get(self.fin_turn_state.phase, Step.MAIN)
