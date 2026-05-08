"""Finance TCG core helpers.

Implements the FinanceModeAdapter, liquidity (mana-crystal) management,
Dark Pool zone helpers, Derivatives Desk helpers, structure-count helpers,
and the four system interceptor registrations described in docs/games/finance.md.

Parallel agents are writing:
  - src/engine/finance_combat.py  (FinanceCombatManager, overflow, SBAs)
  - src/engine/finance_turn.py    (FinanceTurnManager, 5-phase run_turn)
  - src/ai/finance_adapter.py     (FinanceAIAdapter, 3 difficulty tiers)
Those modules must NOT be edited here.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    ZoneType,
    new_id,
)

# ---------------------------------------------------------------------------
# Optional sibling imports — wrapped so this module loads even when the
# parallel-agent files don't exist yet (same pattern as depths_adapter.py).
# ---------------------------------------------------------------------------

_HAS_FINANCE_COMBAT = False
try:
    import importlib as _il
    _il.util.find_spec("src.engine.finance_combat")  # noqa: E501 — probe only
    _HAS_FINANCE_COMBAT = True
except Exception:
    pass

_HAS_FINANCE_TURN = False
try:
    _il.util.find_spec("src.engine.finance_turn")
    _HAS_FINANCE_TURN = True
except Exception:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIQUIDITY_MAX = 10
STARTING_CAPITAL = 30
MAX_STRUCTURES = 3
MAX_DERIV_DESK = 3


# =============================================================================
# Player / state initialisation
# =============================================================================

def ensure_finance_state(state: GameState, player_id: str) -> None:
    """Mirror of minecraft.py's ensure_player_state.

    Idempotently initialises the per-player and shared turn_data keys used
    by the Finance engine.  Safe to call multiple times.
    """
    state.turn_data.setdefault("finance_deriv_desk_" + player_id, [])
    state.turn_data.setdefault("finance_structure_count_" + player_id, 0)
    # Dark Pool is shared (singleton) — only set the key once, regardless of
    # which player triggers the initialisation.
    state.turn_data.setdefault("finance_dark_pool", None)


def setup_finance_player(game, player: Player) -> None:
    """Initialise a Player for a Finance game.

    Should be called by FinanceModeAdapter.on_game_start for every player.
    """
    player.life = STARTING_CAPITAL
    player.max_life = STARTING_CAPITAL
    player.has_lost = False
    player.fatigue_damage = 0
    # Liquidity starts at 0; first reset_liquidity_for_turn call gives 1.
    player.mana_crystals = 0
    player.mana_crystals_available = 0
    ensure_finance_state(game.state, player.id)


# =============================================================================
# Liquidity (mana-crystal style resource)
# =============================================================================

def reset_liquidity_for_turn(state: GameState, player_id: str) -> None:
    """Called at the start of Pre-Market.

    Increments the player's Liquidity maximum by 1 (capped at LIQUIDITY_MAX),
    then refills available Liquidity to the new maximum.
    """
    ensure_finance_state(state, player_id)
    player = state.players.get(player_id)
    if not player:
        return
    player.mana_crystals = min(LIQUIDITY_MAX, player.mana_crystals + 1)
    player.mana_crystals_available = player.mana_crystals


# =============================================================================
# Dark Pool helpers  (shared singleton zone stored in turn_data)
# =============================================================================

def get_dark_pool(state: GameState) -> Optional[str]:
    """Return the object ID currently in the Dark Pool, or None."""
    return state.turn_data.get("finance_dark_pool")


def set_dark_pool(state: GameState, obj_id: Optional[str]) -> None:
    """Place obj_id in the Dark Pool, or clear it (obj_id=None)."""
    state.turn_data["finance_dark_pool"] = obj_id


# =============================================================================
# Derivatives Desk helpers  (per-player staging list in turn_data)
# =============================================================================

def get_deriv_desk(state: GameState, player_id: str) -> list[str]:
    """Return the Derivatives Desk object-ID list for player_id."""
    ensure_finance_state(state, player_id)
    return state.turn_data["finance_deriv_desk_" + player_id]


def add_to_deriv_desk(state: GameState, player_id: str, obj_id: str) -> None:
    """Stage a Derivative on the player's Derivatives Desk.

    Raises ValueError if the desk is already at capacity (MAX_DERIV_DESK).
    """
    desk = get_deriv_desk(state, player_id)
    if len(desk) >= MAX_DERIV_DESK:
        raise ValueError(
            f"Derivatives Desk for {player_id} is full ({MAX_DERIV_DESK} max)."
        )
    desk.append(obj_id)


def remove_from_deriv_desk(state: GameState, player_id: str, obj_id: str) -> None:
    """Remove a Derivative from the player's Derivatives Desk (no-op if absent)."""
    desk = get_deriv_desk(state, player_id)
    try:
        desk.remove(obj_id)
    except ValueError:
        pass


# =============================================================================
# Structure count helpers
# =============================================================================

def get_structure_count(state: GameState, player_id: str) -> int:
    """Return the number of Structures the player currently has on the Trading Floor."""
    ensure_finance_state(state, player_id)
    return int(state.turn_data.get("finance_structure_count_" + player_id, 0))


def inc_structure_count(state: GameState, player_id: str) -> None:
    """Increment the player's Structure count, capped at MAX_STRUCTURES."""
    ensure_finance_state(state, player_id)
    key = "finance_structure_count_" + player_id
    state.turn_data[key] = min(MAX_STRUCTURES, state.turn_data[key] + 1)


def dec_structure_count(state: GameState, player_id: str) -> None:
    """Decrement the player's Structure count, floored at 0."""
    ensure_finance_state(state, player_id)
    key = "finance_structure_count_" + player_id
    state.turn_data[key] = max(0, state.turn_data[key] - 1)


# =============================================================================
# System interceptor registrations
# =============================================================================

def _register_dark_pool_trigger(game) -> None:
    """REACT on PHASE_START(trading_session) for the active player.

    If a Dark Pool Order card is staged, emit FIN_MARKET_EVENT and clear
    the slot.  The card's own interceptor handles the actual effect.
    """

    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return (
            event.payload.get("phase") == "trading_session"
            and get_dark_pool(state) is not None
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        dark_pool_id = get_dark_pool(state)
        if not dark_pool_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        set_dark_pool(state, None)
        trigger = Event(
            type=EventType.FIN_MARKET_EVENT,
            payload={"obj_id": dark_pool_id},
            source=dark_pool_id,
            controller=event.payload.get("player"),
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[trigger],
        )

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="FIN_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="forever",
    ))


def _register_leverage_tick(game) -> None:
    """REACT on PHASE_START(market_close).

    For each battlefield object with leverage counters owned by the active
    player, emit a LIFE_CHANGE (negative) representing the leverage cost.
    Also emits a FIN_LEVERAGE_TICK marker for telemetry.
    """

    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "market_close"
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        active_player = event.payload.get("player")
        if not active_player:
            return InterceptorResult(action=InterceptorAction.PASS)

        new_events: list[Event] = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)

        for oid in list(battlefield.objects):
            obj = state.objects.get(oid)
            if not obj or obj.controller != active_player:
                continue
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            leverage = int(obj.state.counters.get("leverage", 0) or 0)
            if leverage <= 0:
                continue
            # Telemetry marker
            new_events.append(Event(
                type=EventType.FIN_LEVERAGE_TICK,
                payload={"object_id": oid, "leverage": leverage, "player": active_player},
                source=oid,
                controller=active_player,
            ))
            # Actual Capital Reserve damage
            new_events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": active_player, "amount": -leverage},
                source=oid,
                controller=active_player,
            ))

        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="FIN_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="forever",
    ))


def _register_structure_cap_check(game) -> None:
    """TRANSFORM on ZONE_CHANGE → BATTLEFIELD for FIN_STRUCTURE cards.

    Prevents the zone change if the controller already has MAX_STRUCTURES
    Structures on the Trading Floor.  On success, increments the count.

    Also registers a REACT on OBJECT_DESTROYED to decrement the count when
    a Structure leaves the battlefield.
    """

    # --- TRANSFORM: cap enforcement on entry ---
    def _entry_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        to_zone = event.payload.get("to_zone_type")
        if to_zone != ZoneType.BATTLEFIELD:
            return False
        oid = event.payload.get("object_id")
        if not oid:
            return False
        obj = state.objects.get(oid)
        return obj is not None and CardType.FIN_STRUCTURE in obj.characteristics.types

    def _entry_handler(event: Event, state: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        obj = state.objects.get(oid) if oid else None
        if not obj:
            return InterceptorResult(action=InterceptorAction.PASS)
        controller = obj.controller
        if get_structure_count(state, controller) >= MAX_STRUCTURES:
            # Prevent the zone change — Trading Floor is full.
            return InterceptorResult(action=InterceptorAction.PREVENT)
        # Allow entry and track the count.
        inc_structure_count(state, controller)
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="FIN_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.TRANSFORM,
        filter=_entry_filter,
        handler=_entry_handler,
        duration="forever",
    ))

    # --- REACT: decrement on destruction ---
    def _destroy_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        oid = event.payload.get("object_id")
        if not oid:
            return False
        obj = state.objects.get(oid)
        return obj is not None and CardType.FIN_STRUCTURE in obj.characteristics.types

    def _destroy_handler(event: Event, state: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        obj = state.objects.get(oid) if oid else None
        if obj:
            dec_structure_count(state, obj.controller)
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="FIN_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_destroy_filter,
        handler=_destroy_handler,
        duration="forever",
    ))


def _register_derivative_attach_on_etb(game) -> None:
    """REACT on ZONE_CHANGE → BATTLEFIELD for FIN_DERIVATIVE cards.

    When a Derivative lands on the battlefield without being attached to a
    host (i.e. played directly from hand), move it to the controller's
    Derivatives Desk if there is room.  Card effects that attach a Derivative
    directly to a Trader bypass this by setting 'attach_to' in the event
    payload, which suppresses staging.

    The Derivatives Desk is implemented as turn_data lists; the card objects
    themselves stay in the battlefield zone so existing zone queries continue
    to work.  The desk list is a logical overlay used by the turn manager
    and AI to distinguish "attached" vs "staged" Derivatives.
    """

    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        to_zone = event.payload.get("to_zone_type")
        if to_zone != ZoneType.BATTLEFIELD:
            return False
        # Only intercept if not already being attached to a specific host.
        if event.payload.get("attach_to"):
            return False
        oid = event.payload.get("object_id")
        if not oid:
            return False
        obj = state.objects.get(oid)
        return obj is not None and CardType.FIN_DERIVATIVE in obj.characteristics.types

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        obj = state.objects.get(oid) if oid else None
        if not obj:
            return InterceptorResult(action=InterceptorAction.PASS)
        controller = obj.controller
        desk = get_deriv_desk(state, controller)
        if len(desk) < MAX_DERIV_DESK and oid not in desk:
            desk.append(oid)
        # Allow the zone change; the card is on the battlefield and also
        # tracked on the Derivatives Desk until a Trader adopts it.
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="FIN_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="forever",
    ))


# =============================================================================
# Mode adapter
# =============================================================================

class FinanceModeAdapter:
    """Game-mode adapter for Finance TCG.

    Plugs into the engine's mode_adapter registry so the server, session,
    and pipeline can call hooks without knowing Finance-specific logic.
    """

    mode: str = "finance"

    # --- Serialization flags (used by session.py) ---------------------------

    def excludes_from_battlefield_serialization(self, obj) -> bool:
        return False

    def uses_pokemon_card_serializer(self) -> bool:
        return False

    # -----------------------------------------------------------------------
    # GameModeAdapter protocol — only override what differs from MTG defaults
    # -----------------------------------------------------------------------

    def hand_size_limit(self, player, state):
        return 7

    def overdraw_burns(self, state):
        return False

    def max_minions_on_board(self, controller_id, state):
        return None  # No explicit board-size cap for Finance (Structures capped separately)

    def default_max_hand_size(self):
        return 7

    def create_mana_system(self, state):
        return None  # Liquidity is handled entirely in reset_liquidity_for_turn

    def life_cap(self, player, state):
        return int(getattr(player, "max_life", None) or STARTING_CAPITAL)

    def create_combat_manager(self, state):
        try:
            from .finance_combat import FinanceCombatManager
            return FinanceCombatManager(state)
        except ImportError:
            # finance_combat.py not yet written — fall back to None so the
            # turn manager can handle combat inline.
            return None

    def create_turn_manager(self, state):
        try:
            from .finance_turn import FinanceTurnManager
            return FinanceTurnManager(state)
        except ImportError:
            return None

    async def setup_starting_hands(self, game, player_ids):
        for player_id in player_ids:
            game.draw_cards(player_id, 5)
        return True

    def skips_turn_order_setup(self):
        return False

    def delegates_start_to_session(self):
        return False

    def shuffle_turn_order(self, player_ids):
        return player_ids

    def includes_game_log_in_state(self):
        return True

    def extra_player_zone_types(self):
        return []

    def extra_shared_zone_types(self):
        return []

    def handles_hero_damage(self):
        return False

    def apply_hero_damage(self, hero, player, amount, state):
        return None

    def sync_hero_damage_with_life(self, player, hero, state):
        return None

    def handle_empty_library_draw(self, player, state):
        """Empty library during Research phase — apply escalating fatigue damage."""
        player.fatigue_damage = getattr(player, "fatigue_damage", 0) + 1
        player.life = max(0, player.life - player.fatigue_damage)
        if player.life <= 0:
            player.has_lost = True
        return []

    def on_leave_battlefield_to_hidden(self, obj, from_zone_type, to_zone_type, state):
        return None

    def on_weapon_destroyed(self, obj, event, state):
        return None

    # -----------------------------------------------------------------------
    # Finance-specific lifecycle hooks
    # -----------------------------------------------------------------------

    def on_game_start(self, game) -> None:
        """Initialise every player and register system interceptors."""
        for pid in game.state.turn_order:
            player = game.state.players.get(pid)
            if player:
                setup_finance_player(game, player)
        self.register_system_interceptors(game)

    def on_turn_start(self, game, player_id: str) -> None:
        """Called by the engine at the start of each player's turn.

        Increments and refills the Liquidity pool (mana-crystal ramp).
        """
        reset_liquidity_for_turn(game.state, player_id)

    def register_ai_player(self, game, player_id: str) -> None:
        try:
            from src.ai.finance_adapter import FinanceAIAdapter
            adapter = FinanceAIAdapter(difficulty="medium")
            if hasattr(game, "finance_turn_manager") and game.finance_turn_manager:
                game.finance_turn_manager.set_ai_handler(player_id, adapter)
            elif hasattr(game, "turn_manager") and hasattr(game.turn_manager, "set_ai_player"):
                game.turn_manager.set_ai_player(player_id)
        except ImportError:
            # FinanceAIAdapter not yet available — silently defer.
            pass

    def register_system_interceptors(self, game) -> None:
        """Register the four Finance system interceptors on game start."""
        _register_dark_pool_trigger(game)
        _register_leverage_tick(game)
        _register_structure_cap_check(game)
        _register_derivative_attach_on_etb(game)

    # -----------------------------------------------------------------------
    # Damage / loss hooks (standard MTG-style defaults are fine for Finance)
    # -----------------------------------------------------------------------

    def apply_player_damage(self, player, amount, state):
        """Reduce Capital Reserve.  No armor in Finance (base behaviour)."""
        player.life -= max(0, amount)
        return 0

    def post_creature_damage_destroy_check(self, obj, event, state):
        """Finance Traders are liquidated when damage >= Defense Rating (toughness)."""
        from .queries import get_toughness
        if CardType.FIN_TRADER not in obj.characteristics.types:
            return []
        toughness = get_toughness(obj, state)
        if toughness is not None and obj.state.damage >= toughness:
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": obj.id, "reason": "finance_liquidated"},
                source=event.source,
                controller=event.controller,
            )]
        return []
