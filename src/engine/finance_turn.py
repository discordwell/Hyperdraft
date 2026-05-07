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

ACTION_END_PHASE      = "FIN_END_PHASE"
ACTION_END_TURN       = "FIN_END_TURN"
ACTION_PLAY_CARD      = "FIN_PLAY_CARD_ACTION"
ACTION_ACTIVATE       = "FIN_ACTIVATE_ABILITY"
ACTION_DISCARD        = "FIN_DISCARD"

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
        self.finance_combat_manager = None  # set after construction

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
        - Emit PHASE_START  (fires 'Monopoly Position' alternate-win check,
          leverage-income interceptors, etc.)
        - Untap all Traders belonging to player_id
        - Reset Liquidity pool for the turn
        - Clear summoning sickness on player's Traders
        - Emit PHASE_END
        """
        events: list[Event] = []
        events.extend(self._emit_phase("pre_market", "start", player_id))

        # Handle Short Sell returns: derivatives.py stores
        # state.turn_data["short_sell_return_{obj_id}"] = True when a Trader is exiled
        # via Short Selling.  Return it here with two +1/+1 counters.
        for key in list(self.state.turn_data.keys()):
            if key.startswith("short_sell_return_"):
                obj_id = key.replace("short_sell_return_", "")
                obj = self.state.objects.get(obj_id)
                if obj and obj.zone == ZoneType.EXILE and obj.owner == player_id:
                    # Determine counter count (default 2; Convexity Rider may set 3)
                    bonus_key = f"short_sell_bonus_counters_{obj_id}"
                    counter_count = int(self.state.turn_data.pop(bonus_key, 2))
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
                    # Apply +1/+1 counters directly (fallback if COUNTER_ADDED
                    # is not yet processed for FIN objects)
                    returned_obj = self.state.objects.get(obj_id)
                    if returned_obj:
                        returned_obj.state.counters["+1/+1"] = (
                            returned_obj.state.counters.get("+1/+1", 0) + counter_count
                        )
                        returned_obj.characteristics.power = (
                            (returned_obj.characteristics.power or 0) + counter_count
                        )
                        returned_obj.characteristics.toughness = (
                            (returned_obj.characteristics.toughness or 0) + counter_count
                        )
                    for _ in range(counter_count):
                        counter_evt = Event(
                            type=EventType.COUNTER_ADDED,
                            payload={
                                "object_id": obj_id,
                                "counter_type": "+1/+1",
                                "amount": 1,
                            },
                        )
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

        # Reset Liquidity pool (grow by 1, refill to new max, cap 10).
        reset_liquidity_for_turn(self.state, player_id)

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
        attackers: list[str] = []
        if self._is_ai_player(player_id):
            ai = self._get_ai(player_id)
            if ai is not None:
                result = self._call_ai(ai, "choose_attackers", self.state, player_id)
                attackers = await self._maybe_await(result) or []
        elif self.human_action_handler is not None:
            action = await self.human_action_handler(player_id, self.state)
            if action and action.get("action_type") == "FIN_DECLARE_ATTACKERS":
                attackers = list(action.get("attackers", []))

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
            if action and action.get("action_type") == "FIN_DECLARE_BLOCKERS":
                blocks = dict(action.get("blocks", {}))

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

        # Liquidity check.
        if player.mana_crystals_available < cost:
            return events

        # Deduct Liquidity.
        player.mana_crystals_available -= cost

        # Emit FIN_PLAY_CARD marker event.
        fin_et = getattr(EventType, "FIN_PLAY_CARD", None) or EventType.ZONE_CHANGE
        play_event = Event(
            type=fin_et,
            payload={
                "card_id": card_id,
                "player": player_id,
                "cost": cost,
                "targets": list(targets),
            },
            source=card_id,
        )
        if (pl := self._emit_pipeline):
            pl.emit(play_event)
        events.append(play_event)

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
            # Execute card effect before moving to graveyard.
            card_def = getattr(obj, "card_def", None)
            if card_def is not None:
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

            grv_ev = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": card_id,
                    "from_zone": f"hand_{player_id}",
                    "from_zone_type": ZoneType.HAND,
                    "to_zone": f"graveyard_{player_id}",
                    "to_zone_type": ZoneType.GRAVEYARD,
                },
                source=card_id,
            )
            if (pl := self._emit_pipeline):
                pl.emit(grv_ev)
            events.append(grv_ev)

        # Track cards played this turn.
        if hasattr(player, "cards_played_this_turn"):
            player.cards_played_this_turn += 1

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
        # Clear per-turn scratchpad.
        if hasattr(self.state, "turn_data"):
            self.state.turn_data.clear()
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
