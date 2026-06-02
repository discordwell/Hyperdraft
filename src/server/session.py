"""
Game Session Management

Manages active game sessions, player connections, and game state.

This module is the orchestrator: it owns lifecycle (start/stop/reconnect),
socket tracking, replay recording, the MTG priority-based action flow, and
the AI engine registry. Per-mode game loops, action handlers, and card
serializers live in `src.server.modes.*` and are reached via
`get_server_mode_adapter(game_mode)`.
"""

import asyncio
import os
import traceback as _tb
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from uuid import uuid4
import time
import re
import logging

from src.engine import (
    Game, GameState, Player, PlayerAction, ActionType, LegalAction,
    Phase, Step, ZoneType, CardType, GameObject,
    AttackDeclaration, BlockDeclaration
)
from src.engine.types import CardDefinition

from .models import (
    GameStateResponse, PlayerData, CardData, StackItemData,
    LegalActionData, CombatData, PlayerActionRequest, ReplayFrame,
    PendingChoiceData, PendingChoiceWaitingData, GameLogEntry,
    PendingTriggerData,
    DivideAllocationData, TargetGroupMetadataData,
)
from .modes import get_server_mode_adapter

logger = logging.getLogger(__name__)


def generate_id() -> str:
    """Generate a short unique ID."""
    return str(uuid4())[:8]


# Probability that a freshly-added library card is rendered as foil (cosmetic).
FOIL_RATE = 0.10


# Action type prefixes handled by specific mode adapters.
_MODE_ACTION_PREFIXES = {"pokemon": "PKM", "hearthstone": "HS", "yugioh": "YGO", "minecraft": "MC", "finance": "FIN", "depths": "DEPTHS", "scp": "SCP", "cats": "CATS", "clankers": "CLANKERS"}

_HS_ACTION_TYPES = frozenset({
    "HS_PLAY_CARD", "HS_ATTUNE_CARD", "HS_ATTACK", "HS_HERO_POWER", "HS_END_TURN",
})

_PKM_ACTION_TYPES = frozenset({
    "PKM_PLAY_CARD", "PKM_ATTACH_ENERGY", "PKM_ATTACK", "PKM_RETREAT",
    "PKM_EVOLVE", "PKM_USE_ABILITY", "PKM_END_TURN",
})

_YGO_ACTION_TYPES = frozenset({
    "YGO_NORMAL_SUMMON", "YGO_SET_MONSTER", "YGO_FLIP_SUMMON",
    "YGO_CHANGE_POSITION", "YGO_ACTIVATE", "YGO_SET_SPELL_TRAP",
    "YGO_DECLARE_ATTACK", "YGO_DIRECT_ATTACK", "YGO_CHAIN_RESPONSE",
    "YGO_CHAIN_PASS", "YGO_END_TURN", "YGO_SPECIAL_SUMMON", "YGO_END_PHASE",
})

_MC_ACTION_TYPES = frozenset({
    "MC_PLAY_CARD", "MC_ASSIGN_WORKER", "MC_AVATAR_ACTION", "MC_EXPLORE_BIOME",
    "MC_DECLARE_ATTACKERS", "MC_DECLARE_BLOCKERS", "MC_END_TURN",
    "MC_MULLIGAN_DECISION",
})

_FIN_ACTION_TYPES = frozenset({
    "FIN_PLAY_CARD", "FIN_DECLARE_ATTACKERS", "FIN_DECLARE_BLOCKERS",
    "FIN_ACTIVATE_ABILITY", "FIN_END_PHASE", "FIN_END_TURN",
})

_DEPTHS_ACTION_TYPES = frozenset({
    "DEPTHS_DEPLOY_VESSEL", "DEPTHS_PLAY_CARD", "DEPTHS_DIVE",
    "DEPTHS_SURFACE_VESSEL", "DEPTHS_SURFACE",
    "DEPTHS_ATTACH", "DEPTHS_CAST_SPELL", "DEPTHS_LAY_MINE",
    "DEPTHS_ACTIVATE_ABILITY", "DEPTHS_DECLARE_ATTACKERS", "DEPTHS_DETECT",
    "DEPTHS_DECLARE_INTERCEPTORS", "DEPTHS_END_TURN",
})

_CATS_ACTION_TYPES = frozenset({
    "CATS_PLAY_CARD", "CATS_CHOOSE_PILE", "CATS_KNOCK_OVER",
})

_CLANKERS_ACTION_TYPES = frozenset({
    "CLANKERS_PLAY_CARD", "CLANKERS_ATTACH_PART", "CLANKERS_ACTIVATE_ABILITY",
    "CLANKERS_DECLARE_ATTACKERS", "CLANKERS_DECLARE_BLOCKERS",
    "CLANKERS_REFILL_DECISION", "CLANKERS_END_PHASE",
})

_SCP_ACTION_TYPES = frozenset({
    "SCP_GAIN", "SCP_DRAW", "SCP_PLAY", "SCP_ADVANCE",
    "SCP_CONTAIN", "SCP_INFILTRATE", "SCP_ACTIVATE", "SCP_END_TURN",
})


# Finance card art lives under assets/card_art/finance/<subset>/<slug>.png and
# is served via /api/card-art/finance/<subset>/<slug>.png. Subsets so far:
# FINA (set 1: Quant & IB) and FINM (set 2). FINM has no art folder yet.
_FIN_ART_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _finance_image_url(card_def: Optional[CardDefinition], name: str) -> Optional[str]:
    """Compute the /api/card-art/ URL for a Finance card.

    Uses the card's ``domain`` (FINA / FINM) to pick the subset folder; falls
    back to ``fina/`` since that's the only folder with art today. The slug is
    name-lowercased and non-alphanumeric chars collapsed to underscores so it
    matches the on-disk PNG filenames (e.g. "Flash Crash Bot" → flash_crash_bot).
    """
    if not name:
        return None
    slug = _FIN_ART_SLUG_RE.sub("_", name.lower()).strip("_")
    if not slug:
        return None
    domain = (getattr(card_def, "domain", None) or "").strip().lower()
    subset = domain if domain in ("fina", "finm") else "fina"
    return f"/api/card-art/finance/{subset}/{slug}.png"


@dataclass
class GameSession:
    """
    Manages a single game session.

    Wraps the engine Game class and provides:
    - Player socket tracking
    - State serialization for clients
    - Action handling with validation
    - Replay recording
    - Delegates per-mode game loop / action handling / serialization to
      `src.server.modes.ModeAdapter` instances.
    """
    id: str
    game: Game
    mode: str  # human_vs_bot, bot_vs_bot, human_vs_human

    # Player tracking
    player_ids: list[str] = field(default_factory=list)
    player_names: dict[str, str] = field(default_factory=dict)
    player_sockets: dict[str, str] = field(default_factory=dict)  # player_id -> socket_id
    human_players: set[str] = field(default_factory=set)

    # Game state
    is_started: bool = False
    is_finished: bool = False
    winner_id: Optional[str] = None
    display_variant: Optional[str] = None  # Game variant (e.g. "stormrift") sent to clients

    # Replay recording
    replay_frames: list[ReplayFrame] = field(default_factory=list)

    # Callbacks
    on_state_change: Optional[Callable[[str, dict], Any]] = None

    # Pending human action
    _pending_action_future: Optional[asyncio.Future] = None
    _pending_player_id: Optional[str] = None
    _action_processed_event: Optional[asyncio.Event] = None
    # Pending human choice (scry/target/modal/etc.)
    _pending_choice_future: Optional[asyncio.Future] = None
    _pending_choice_player_id: Optional[str] = None
    _pending_choice_id: Optional[str] = None
    # Pending Minecraft mulligan decisions, keyed by player_id. Multiple players
    # are processed sequentially in setup_starting_hands, but the dict is the
    # right shape if we ever parallelise.
    _pending_mulligan_futures: dict[str, asyncio.Future] = field(default_factory=dict)
    # Mirror of mulligan-prompt UI state, broadcast in get_client_state so the
    # frontend can render the keep/mulligan buttons.
    _mulligan_state: dict[str, dict] = field(default_factory=dict)

    # Game log (used by PKM/YGO modes)
    _game_log: list[GameLogEntry] = field(default_factory=list)

    # AI engine (lazy initialized)
    _ai_engines_by_player: dict[str, Any] = field(default_factory=dict)
    _choice_engines_by_player: dict[str, Any] = field(default_factory=dict)
    ai_difficulty: str = "medium"
    # Per-player AI profiles (used for bot-vs-bot and LLM duels).
    # Example:
    #   {"brain": "anthropic", "model": "claude-opus-4.6", "temperature": 0.2, "record_prompts": True}
    ai_profiles_by_player: dict[str, dict[str, Any]] = field(default_factory=dict)
    _llm_providers_by_player: dict[str, Any] = field(default_factory=dict)
    _llm_response_cache_by_player: dict[str, dict[str, dict]] = field(default_factory=dict)
    _last_processed_action: Optional[dict[str, Any]] = None
    _last_non_pass_action: Optional[dict[str, Any]] = None
    # Decklists as provided to add_cards_to_deck (used for AI layer preparation).
    deck_card_defs_by_player: dict[str, list[CardDefinition]] = field(default_factory=dict)
    # Deck IDs by player seat (used for WatchLive lobby blurbs). Bot-vs-bot
    # /start populates these when the request provides a deck_id; modes that
    # don't expose decks (e.g. early Cats variant) leave this empty.
    deck_id_by_player: dict[str, str] = field(default_factory=dict)
    # YGO AI strategy hints (set in match.py, applied when adapter is created)
    ygo_ai_strategy: Optional[dict] = None

    # Replay/spectator controls (primarily for /bot-game).
    record_actions_for_replay: bool = False
    spectator_delay_ms: int = 0
    max_replay_frames: int = 5000
    _replay_truncated: bool = False

    def __post_init__(self):
        """Set up game callbacks."""
        self.game.set_human_action_handler(self._get_human_action)
        self.game.set_ai_action_handler(self._get_ai_action)
        self.game.set_attack_handler(self._get_attacks)
        self.game.set_block_handler(self._get_blocks)
        self.game.set_mulligan_handler(self._get_mulligan_decision)
        # Set up action processed callback for synchronization
        self.game.priority_system.on_action_processed = self._on_action_processed

    # --- Mode adapter accessor -------------------------------------------

    @property
    def mode_adapter(self):
        """Server-side mode adapter for the current game mode."""
        return get_server_mode_adapter(self.game.state.game_mode)

    async def _on_action_processed(self, action: Optional[PlayerAction] = None):
        """
        Called when an action is fully processed by the game loop.

        Used for:
        - API synchronization (unblock /action callers)
        - Bot-game replay recording (per-action frames)
        - Optional spectator pacing (delay between actions)
        """
        if self._action_processed_event:
            self._action_processed_event.set()

        serialized_action = self._serialize_processed_action(action)
        if serialized_action:
            self._last_processed_action = serialized_action
            if serialized_action.get("action_type") != "PASS":
                self._last_non_pass_action = serialized_action

        if self.record_actions_for_replay:
            self._record_frame(action=serialized_action)

        if self.spectator_delay_ms and self.spectator_delay_ms > 0:
            # Don't slow the game down for "just passing"; it's very spammy and
            # makes spectating/replays feel glacial.
            should_delay = True
            if action is not None and getattr(action, "type", None) == ActionType.PASS:
                should_delay = False
            if should_delay:
                await asyncio.sleep(self.spectator_delay_ms / 1000.0)

    def add_player(self, name: str, is_ai: bool = False) -> str:
        """Add a player to the session."""
        player = self.game.add_player(name)
        self.player_ids.append(player.id)
        self.player_names[player.id] = name

        if is_ai:
            self.game.set_ai_player(player.id)
        else:
            self.human_players.add(player.id)

        return player.id

    # --- Ultra-AI helpers -------------------------------------------------
    # An "ultra" AI seat is server-aware but plays via the REST /action endpoint
    # (an external Claude Code or Codex agent submits actions for it). For these seats:
    #   - we DON'T register a heuristic adapter handler with the turn manager
    #   - we DON'T mark the player as AI in the engine's priority/turn AI sets
    #     (so the engine treats them as human-controlled and routes via
    #     human_action_handler, which the REST /action endpoint resolves).

    def _player_difficulty(self, player_id: str) -> str:
        """Resolve the configured difficulty for a player (profile -> session default)."""
        profile = self.ai_profiles_by_player.get(player_id) or {}
        diff = profile.get("difficulty", self.ai_difficulty or "medium")
        if hasattr(diff, "value"):
            diff = diff.value
        return str(diff).strip().lower()

    def is_ultra_ai_player(self, player_id: str) -> bool:
        """True if this player is an AI seat configured to be driven externally."""
        if player_id in self.human_players:
            return False
        if player_id not in self.player_ids:
            return False
        return self._player_difficulty(player_id) == "ultra"

    def external_agent_runner(self, player_id: str) -> str:
        """Resolve the local CLI runner for an externally-driven Ultra seat."""
        profile = self.ai_profiles_by_player.get(player_id) or {}
        runner = str(profile.get("agent_runner") or "claude").strip().lower()
        return runner if runner in {"claude", "codex"} else "claude"

    @property
    def ultra_ai_player_ids(self) -> list[str]:
        """All AI seats in this session that are externally driven (ultra)."""
        return [pid for pid in self.player_ids if self.is_ultra_ai_player(pid)]

    @property
    def has_ultra_ai(self) -> bool:
        """True if any seat in this session is an ultra (externally driven) AI."""
        return bool(self.ultra_ai_player_ids)

    def detach_ultra_from_engine_ai_sets(self) -> None:
        """Remove ultra-AI players from engine-level AI registries.

        Called by mode adapters during setup_game(). Without this, the engine's
        priority loop and turn manager will route the AI seat to a heuristic
        adapter rather than blocking on the human_action_handler future.
        """
        ultra_ids = self.ultra_ai_player_ids
        if not ultra_ids:
            return
        # MTG-style priority system tracks AI players for the get_action dispatch.
        ps = getattr(self.game, "priority_system", None)
        if ps is not None and hasattr(ps, "ai_players"):
            for pid in ultra_ids:
                ps.ai_players.discard(pid)
        # Mode-specific turn managers each maintain their own ai_players set.
        tm = getattr(self.game, "turn_manager", None)
        if tm is not None and hasattr(tm, "ai_players"):
            for pid in ultra_ids:
                try:
                    tm.ai_players.discard(pid)
                except (AttributeError, TypeError):
                    pass

    def connect_socket(self, player_id: str, socket_id: str) -> None:
        """Connect a player's socket."""
        self.player_sockets[player_id] = socket_id

    def disconnect_socket(self, socket_id: str) -> Optional[str]:
        """Disconnect a socket and return the player_id if found."""
        for pid, sid in list(self.player_sockets.items()):
            if sid == socket_id:
                del self.player_sockets[pid]
                return pid
        return None

    def add_cards_to_deck(self, player_id: str, card_defs: list[CardDefinition]) -> None:
        """Add cards to a player's library."""
        from src.engine.turn_state import _get_rng
        self.deck_card_defs_by_player.setdefault(player_id, []).extend(card_defs)
        rng = _get_rng(self.game.state)
        for card_def in card_defs:
            obj = self.game.add_card_to_library(player_id, card_def)
            if rng.random() < FOIL_RATE:
                obj.state.foil = True
        self.game.shuffle_library(player_id)

    async def _prepare_ai_layers(self) -> None:
        """
        Precompute AI strategy layers (Hard/Ultra) from the known decklists.

        The match routes construct both decks server-side, so we can give the bot
        perfect matchup knowledge (deck + matchup + card layers) without any
        mid-game inference.
        """
        ai_player_ids = [pid for pid in self.player_ids if pid not in self.human_players]
        if not ai_player_ids:
            return

        for ai_pid in ai_player_ids:
            profile = self.ai_profiles_by_player.get(ai_pid) or {}
            brain = (profile.get("brain") or "heuristic").strip().lower()
            difficulty = profile.get("difficulty", "medium")

            # LLM-driven bots only need layers if they're using Ultra difficulty
            # (for their heuristic fallback engine)
            if brain in ("openai", "anthropic", "ollama") and difficulty != "ultra":
                continue

            ai = self._get_or_create_ai_engine(ai_pid)

            # Not all difficulties use layers.
            if not getattr(ai, "settings", {}).get("use_layers"):
                continue

            if getattr(ai, "_layers_prepared", False):
                continue

            our_defs = self.deck_card_defs_by_player.get(ai_pid) or []
            if not our_defs:
                continue

            our_deck_cards = [cd.name for cd in our_defs]

            opp_pid = next((pid for pid in self.player_ids if pid != ai_pid), None)
            opp_defs = (self.deck_card_defs_by_player.get(opp_pid) or []) if opp_pid else []
            opponent_deck_cards = [cd.name for cd in opp_defs] if opp_defs else None

            # Provide a combined card definition map covering both decks (incl. custom domains).
            card_defs_map: dict[str, CardDefinition] = {}
            for cd in (our_defs + opp_defs):
                card_defs_map[cd.name] = cd

            try:
                await ai.prepare_for_match(
                    our_deck_cards=our_deck_cards,
                    card_defs=card_defs_map,
                    opponent_deck_cards=opponent_deck_cards,
                )
            except Exception as e:
                # Don't hard-fail the match start if LLM/layer generation errors.
                print(f"AI layer preparation failed for {ai_pid}: {e}")

    async def start_game(self) -> None:
        """Start the game (dispatches per-mode setup)."""
        if self.is_started:
            return

        self.is_started = True

        # Per-mode setup (AI adapter wiring, turn_manager.setup_game(), etc.)
        await self.mode_adapter.setup_game(self)

        await self.game.start_game()

        # Record initial state
        self._record_frame(action=None)

    async def run_until_human_input(self) -> None:
        """Run the game until human input is needed or game ends."""
        try:
            await self.mode_adapter.run_game_loop(self)
        except asyncio.CancelledError:
            pass

    async def _process_ai_pending_choices(self) -> None:
        """Process any pending choices for AI players."""
        # Keep processing while there are AI choices to make
        max_iterations = 10  # Safety limit
        for _ in range(max_iterations):
            pending_choice = self.game.get_pending_choice()
            if not pending_choice:
                break

            # Check if the choice is for an AI player. Ultra-AI seats are driven
            # externally via /api/match/<id>/choice, so we skip them here too.
            choice_player = pending_choice.player
            if (
                choice_player not in self.human_players
                and not self.is_ultra_ai_player(choice_player)
            ):
                # It's a heuristic AI player - make the choice locally
                self._handle_ai_choice(
                    choice_player,
                    pending_choice,
                    self.game.state
                )
                # Small delay to prevent tight loops
                await asyncio.sleep(0.01)
            else:
                # Human player or ultra AI needs to make choice - stop processing
                break

    def get_client_state(self, player_id: Optional[str] = None) -> GameStateResponse:
        """
        Get game state formatted for a client.

        Hides hidden information appropriately.
        """
        # Keep session flags in sync even when the game ends mid-turn (e.g. during a
        # choice submission while the background loop is still inside run_turn()).
        if self.game.is_game_over():
            self.is_finished = True
            self.winner_id = self.game.get_winner()

        game_state = self.game.state
        adapter = self.mode_adapter

        # Get player data
        players = {}
        for pid, player in game_state.players.items():
            players[pid] = PlayerData(
                id=pid,
                name=self.player_names.get(pid, player.name),
                life=player.life,
                has_lost=player.has_lost,
                hand_size=len(self.game.get_hand(pid)),
                library_size=self.game.get_library_size(pid),
                mana_crystals=player.mana_crystals,
                mana_crystals_available=player.mana_crystals_available,
                armor=player.armor,
                hero_id=player.hero_id,
                weapon_attack=player.weapon_attack,
                weapon_durability=player.weapon_durability,
                fatigue_damage=player.fatigue_damage,
                hero_power_used=player.hero_power_used,
                hero_power_id=player.hero_power_id,
                hero_power_name=adapter.get_hero_power_name(self, player),
                hero_power_cost=adapter.get_hero_power_cost(self, player),
                hero_power_text=adapter.get_hero_power_text(self, player),
                max_life=player.max_life,
                variant_resources=self._get_variant_resources(player),
                prizes_remaining=getattr(player, 'prizes_remaining', 0),
                energy_attached_this_turn=getattr(player, 'energy_attached_this_turn', False),
                supporter_played_this_turn=getattr(player, 'supporter_played_this_turn', False),
                mc_materials=dict(getattr(player, 'mc_materials', {}) or {}),
                mc_avatar_gear=dict(getattr(player, 'mc_avatar_gear', {}) or {}),
                mc_avatar_action_used=bool(getattr(player, 'mc_avatar_action_used', False)),
                # Depths: Submarine Fleet fields
                tc=int(getattr(player, 'tc', 0) or 0),
                sc=int(getattr(player, 'sc', 0) or 0),
                tc_max=int(getattr(player, 'tc_max', 10) or 10),
                sc_max=int(getattr(player, 'sc_max', 10) or 10),
                flagship_id=getattr(player, 'flagship_id', None),
            )

        # Get battlefield (exclude heroes/hero powers in HS mode — those are in player data)
        battlefield = []
        for obj in self.game.get_battlefield():
            if self.game.mode_adapter.excludes_from_battlefield_serialization(obj):
                continue
            battlefield.append(self._serialize_permanent(obj))

        # Get stack
        stack = []
        for item in self.game.stack.get_items():
            stack.append(self._serialize_stack_item(item))

        # Get pending triggered abilities (CR 603.2). These are queued but
        # not yet on the stack — they're drained on the next priority pass.
        pending_triggers_data = []
        for trig in getattr(game_state, 'pending_triggers', []) or []:
            try:
                pending_triggers_data.append(self._serialize_pending_trigger(trig))
            except Exception:
                # Defensive: don't block state serialization on a malformed
                # trigger queue entry.
                continue

        # Get hand (only for requesting player)
        hand = []
        if player_id:
            for obj in self.game.get_hand(player_id):
                hand.append(self._serialize_card(obj))

        # Get graveyards
        graveyards = {}
        # Choose a serializer based on mode. PKM/YGO use mode-specific serializers;
        # MTG/HS use the default CardData serializer.
        if self.game.mode_adapter.uses_pokemon_card_serializer():
            serialize_fn = lambda o: adapter.serialize_card(self, o)
        else:
            serialize_fn = self._serialize_card
        for pid in game_state.players:
            graveyards[pid] = [
                serialize_fn(obj)
                for obj in self.game.get_graveyard(pid)
            ]

        # Get legal actions (only for priority player)
        legal_actions = []
        if player_id == self.game.get_priority_player():
            for action in self.game.priority_system.get_legal_actions(player_id):
                legal_actions.append(self._serialize_legal_action(action))

        # Get combat state
        combat = None
        if self.game.get_current_phase() == Phase.COMBAT:
            combat_state = self.game.combat_manager.combat_state
            combat = CombatData(
                attackers=[
                    {"attacker_id": a.attacker_id, "defending_player": a.defending_player_id}
                    for a in combat_state.attackers
                ],
                blockers=[
                    {"blocker_id": b.blocker_id, "attacker_id": b.blocking_attacker_id}
                    for b in combat_state.blockers
                ],
                blocked_attackers=list(combat_state.blocked_attackers)
            )

        # Get pending choice state
        pending_choice_data = None
        waiting_for_choice_data = None
        pending_choice = self.game.get_pending_choice()

        if pending_choice:
            if player_id == pending_choice.player:
                # This player needs to make the choice. Surface the
                # rendering hint (Phase 5b overlay mode for MTG cast-time
                # targets) from callback_data so the frontend can switch
                # to click-to-target board highlights instead of a modal.
                interaction_mode = None
                cb_data = getattr(pending_choice, "callback_data", None) or {}
                raw_hint = cb_data.get("interaction_mode")
                if raw_hint in ("overlay", "modal"):
                    interaction_mode = raw_hint
                # Arc B — pass target_metadata through. The engine
                # populates it on cast-time target / divide-allocation
                # choices; absent for modal / scry / surveil / etc.
                tm_obj = getattr(pending_choice, "target_metadata", None)
                target_metadata_data: Optional[TargetGroupMetadataData] = None
                if tm_obj is not None:
                    divide_data: Optional[DivideAllocationData] = None
                    if tm_obj.divide is not None:
                        divide_data = DivideAllocationData(
                            total=tm_obj.divide.total,
                            min_per_target=tm_obj.divide.min_per_target,
                            allow_zero=tm_obj.divide.allow_zero,
                        )
                    target_metadata_data = TargetGroupMetadataData(
                        label=tm_obj.label,
                        predicate_description=tm_obj.predicate_description,
                        min=tm_obj.min,
                        max=tm_obj.max,
                        unique=tm_obj.unique,
                        divide=divide_data,
                        group_index=tm_obj.group_index,
                        total_groups=tm_obj.total_groups,
                    )
                # Arc C — total nested choice depth (in-flight + stacked).
                # Defaults to 1 for ordinary single-choice flow.
                stack_depth = 1
                try:
                    stack_depth = game_state.pending_choice_depth()
                except AttributeError:
                    # Older GameState without the helper — treat as 1.
                    pass
                pending_choice_data = PendingChoiceData(
                    id=pending_choice.id,
                    choice_type=pending_choice.choice_type,
                    player=pending_choice.player,
                    prompt=pending_choice.prompt,
                    options=pending_choice.options,
                    source_id=pending_choice.source_id,
                    min_choices=pending_choice.min_choices,
                    max_choices=pending_choice.max_choices,
                    interaction_mode=interaction_mode,
                    target_metadata=target_metadata_data,
                    stack_depth=stack_depth,
                )
            else:
                # Another player is making a choice
                waiting_for_choice_data = PendingChoiceWaitingData(
                    waiting_for=pending_choice.player,
                    choice_type=pending_choice.choice_type
                )

        # Pokemon zone serialization
        active_pokemon = {}
        bench = {}
        stadium_card_data = None
        if game_state.game_mode == "pokemon":
            def _resolve_obj(obj_or_id):
                """Resolve a zone entry to a GameObject (zones may store IDs or objects)."""
                if isinstance(obj_or_id, str):
                    return game_state.objects.get(obj_or_id)
                return obj_or_id

            for pid in game_state.players:
                # Active spot
                active_zone = game_state.zones.get(f"active_spot_{pid}")
                if active_zone and active_zone.objects:
                    obj = _resolve_obj(active_zone.objects[0])
                    active_pokemon[pid] = adapter.serialize_card(self, obj) if obj else None
                else:
                    active_pokemon[pid] = None

                # Bench
                bench_zone = game_state.zones.get(f"bench_{pid}")
                if bench_zone:
                    bench[pid] = []
                    for entry in bench_zone.objects:
                        obj = _resolve_obj(entry)
                        if obj:
                            bench[pid].append(adapter.serialize_card(self, obj))
                else:
                    bench[pid] = []

            # Stadium
            stadium_zone = game_state.zones.get("stadium_zone")
            if stadium_zone and stadium_zone.objects:
                obj = _resolve_obj(stadium_zone.objects[0])
                stadium_card_data = adapter.serialize_card(self, obj) if obj else None

            # For Pokemon, serialize hand cards with Pokemon-specific fields
            hand = []
            if player_id:
                for obj in self.game.get_hand(player_id):
                    hand.append(adapter.serialize_card(self, obj))

        # Include game log (last 50 entries) for modes that surface it (PKM/YGO).
        game_log = self._game_log[-50:] if self.game.mode_adapter.includes_game_log_in_state() else []

        # Yu-Gi-Oh! zone serialization
        monster_zones: dict = {}
        spell_trap_zones: dict = {}
        field_spells: dict = {}
        banished: dict = {}
        extra_deck_sizes: dict = {}
        ygo_phase: Optional[str] = None
        chain_links: list = []
        minecraft_grid: dict = {}
        minecraft_biomes: dict = {}
        minecraft_exposed_targets: dict = {}

        if game_state.game_mode == "yugioh":
            def _resolve_obj(obj_or_id):
                if isinstance(obj_or_id, str):
                    return game_state.objects.get(obj_or_id)
                return obj_or_id

            for pid in game_state.players:
                # Monster zones (5 slots)
                mz = game_state.zones.get(f"monster_zone_{pid}")
                monster_zones[pid] = []
                if mz:
                    for oid in mz.objects:
                        if oid is None:
                            monster_zones[pid].append(None)
                        else:
                            obj = _resolve_obj(oid)
                            monster_zones[pid].append(
                                adapter.serialize_card(self, obj, reveal=(pid == player_id)) if obj else None
                            )

                # Spell/Trap zones (5 slots)
                stz = game_state.zones.get(f"spell_trap_zone_{pid}")
                spell_trap_zones[pid] = []
                if stz:
                    for oid in stz.objects:
                        if oid is None:
                            spell_trap_zones[pid].append(None)
                        else:
                            obj = _resolve_obj(oid)
                            spell_trap_zones[pid].append(
                                adapter.serialize_card(self, obj, reveal=(pid == player_id)) if obj else None
                            )

                # Field spell
                fsz = game_state.zones.get(f"field_spell_zone_{pid}")
                if fsz and fsz.objects:
                    obj = _resolve_obj(fsz.objects[0])
                    field_spells[pid] = adapter.serialize_card(self, obj, reveal=True) if obj else None
                else:
                    field_spells[pid] = None

                # Banished
                bz = game_state.zones.get(f"banished_{pid}")
                banished[pid] = []
                if bz:
                    for oid in bz.objects:
                        obj = _resolve_obj(oid)
                        if obj:
                            banished[pid].append(adapter.serialize_card(self, obj, reveal=True))

                # Extra deck size
                edz = game_state.zones.get(f"extra_deck_{pid}")
                extra_deck_sizes[pid] = len(edz.objects) if edz else 0

            # Current YGO phase
            turn_mgr = self.game.turn_manager
            if hasattr(turn_mgr, 'ygo_turn_state'):
                ygo_phase = turn_mgr.ygo_turn_state.phase.name

            # Serialize hand with YGO fields
            hand = []
            if player_id:
                for obj in self.game.get_hand(player_id):
                    hand.append(adapter.serialize_card(self, obj, reveal=True))

            # Serialize graveyards with YGO fields
            for pid in game_state.players:
                graveyards[pid] = []
                gy = game_state.zones.get(f"graveyard_{pid}")
                if gy:
                    for oid in gy.objects:
                        obj = _resolve_obj(oid)
                        if obj:
                            graveyards[pid].append(adapter.serialize_card(self, obj, reveal=True))

            # Update player data with YGO-specific fields
            for pid, player in game_state.players.items():
                if pid in players:
                    players[pid].lp = player.lp
                    players[pid].normal_summon_used = player.normal_summon_used

        if game_state.game_mode == "minecraft":
            from src.engine import minecraft as mc

            mc.cleanup_references(game_state)
            minecraft_biomes = {
                pid: [dict(slot) for slot in game_state.minecraft_biomes.get(pid, [])]
                for pid in game_state.players
            }
            for pid in game_state.players:
                raw_grid = game_state.minecraft_grid.get(pid) or mc.empty_grid()
                serialized_rows = []
                for row in raw_grid:
                    serialized_row = []
                    for oid in row:
                        obj = game_state.objects.get(oid) if oid else None
                        serialized_row.append(self._serialize_permanent(obj) if obj else None)
                    serialized_rows.append(serialized_row)
                minecraft_grid[pid] = serialized_rows
                minecraft_exposed_targets[pid] = mc.exposed_grid_targets(game_state, pid)

        # Finance-specific state
        finance_phase = None
        finance_dark_pool_val = None
        finance_turn_data_extra: dict = {}
        finance_stack_dto: list[dict] = []
        finance_pending_response_dto: Optional[dict] = None
        if game_state.game_mode == "finance":
            tm = self.game.turn_manager
            if hasattr(tm, "fin_turn_state"):
                finance_phase = tm.fin_turn_state.phase.name
            finance_dark_pool_val = game_state.turn_data.get("finance_dark_pool")
            for pid in game_state.players:
                desk_key = f"finance_deriv_desk_{pid}"
                finance_turn_data_extra[desk_key] = game_state.turn_data.get(desk_key, [])
            fin_stack = getattr(tm, "fin_stack", None)
            if fin_stack is not None:
                for item in fin_stack.items:
                    obj = game_state.objects.get(item.card_id)
                    name = ""
                    if obj is not None and obj.characteristics:
                        name = obj.characteristics.name or ""
                    finance_stack_dto.append({
                        "card_id": item.card_id,
                        "controller": item.controller,
                        "name": name,
                        "is_response": item.is_response,
                        "countered": item.countered,
                    })
            pending_player = getattr(
                getattr(tm, "fin_turn_state", None),
                "pending_response_player",
                None,
            )
            if pending_player and finance_stack_dto:
                top = finance_stack_dto[-1]
                finance_pending_response_dto = {
                    "prompted_player_id": pending_player,
                    "top_card_id": top["card_id"],
                    "top_card_name": top["name"],
                    "top_controller": top["controller"],
                }

        # Cats-specific state — nested dict consumed by useCatsGame.ts
        cats_state_data: Optional[dict] = None
        if game_state.game_mode == "cats":
            cats_state_data = self._serialize_cats_state(game_state, player_id)

        # Clankers-specific state — nested dict consumed by the clankers frontend
        clankers_state_data: Optional[dict] = None
        if game_state.game_mode == "clankers":
            clankers_state_data = self._serialize_clankers_state(game_state, player_id)

        # SCP-specific state — viewer-redacted (fog of war) nested dict consumed by useSCPGame.ts
        scp_state_data: Optional[dict] = None
        if game_state.game_mode == "scp":
            scp_state_data = self._serialize_scp_state(game_state, player_id)

        # Depths-specific state
        depths_phase_val = None
        depths_combat_val: dict = {}
        if game_state.game_mode == "depths":
            tm = self.game.turn_manager
            # Current phase label from the turn state
            ts = getattr(tm, "turn_state", None)
            if ts is not None:
                phase_obj = getattr(ts, "phase", None)
                if phase_obj is not None:
                    depths_phase_val = getattr(phase_obj, "name", str(phase_obj))
            # Combat context stored on game state or turn manager
            raw_combat = getattr(game_state, "depths_combat_context", None)
            if isinstance(raw_combat, dict):
                depths_combat_val = dict(raw_combat)

        return GameStateResponse(
            match_id=self.id,
            turn_number=self.game.turn_manager.turn_number,
            phase=self.game.get_current_phase().name,
            step=self.game.get_current_step().name,
            active_player=self.game.get_active_player(),
            priority_player=self.game.get_priority_player(),
            players=players,
            battlefield=battlefield,
            stack=stack,
            pending_triggers=pending_triggers_data,
            hand=hand,
            graveyard=graveyards,
            legal_actions=legal_actions,
            combat=combat,
            is_game_over=self.is_finished,
            winner=self.winner_id,
            pending_choice=pending_choice_data,
            waiting_for_choice=waiting_for_choice_data,
            game_mode=game_state.game_mode,
            variant=self.display_variant,
            max_hand_size=game_state.max_hand_size,
            active_pokemon=active_pokemon,
            bench=bench,
            stadium_card=stadium_card_data,
            game_log=game_log,
            monster_zones=monster_zones,
            spell_trap_zones=spell_trap_zones,
            field_spells=field_spells,
            banished=banished,
            extra_deck_sizes=extra_deck_sizes,
            ygo_phase=ygo_phase,
            chain_links=chain_links,
            minecraft_day_phase=game_state.minecraft_day_phase,
            minecraft_biomes=minecraft_biomes,
            minecraft_grid=minecraft_grid,
            minecraft_combat=dict(game_state.minecraft_combat or {}),
            minecraft_exposed_targets=minecraft_exposed_targets,
            minecraft_mulligan_pending=dict(self._mulligan_state),
            finance_phase=finance_phase,
            finance_dark_pool=finance_dark_pool_val,
            finance_turn_data=finance_turn_data_extra,
            finance_stack=finance_stack_dto,
            finance_pending_response=finance_pending_response_dto,
            depths_phase=depths_phase_val,
            depths_combat=depths_combat_val,
            cats=cats_state_data,
            clankers=clankers_state_data,
            scp=scp_state_data,
        )

    async def handle_action(self, request: PlayerActionRequest) -> tuple[bool, str]:
        """Handle a player action request.

        Wraps the real work in :meth:`_handle_action_body` with two
        auto-repair hooks (Phase 3):
          - 30s timeout (env: ACTION_TIMEOUT_SECONDS) → ``turn_timeout`` kick
          - uncaught Exception → ``exception`` kick, then re-raise

        Both hooks are best-effort and only fire when REPAIR_ENABLED is
        truthy. They never break the surface contract: timeout returns
        ``(False, msg)`` like any other action failure; exceptions still
        propagate so the route returns a 500.
        """
        timeout_s = self._action_timeout_seconds()
        try:
            return await asyncio.wait_for(
                self._handle_action_body(request), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            await self._maybe_kick_auto_repair(
                trigger="turn_timeout",
                traceback_text=(
                    f"handle_action exceeded {timeout_s}s for action "
                    f"{request.action_type} (player={request.player_id})"
                ),
                extra_context={
                    "action_type": str(request.action_type),
                    "player_id": request.player_id,
                },
            )
            return False, f"action timed out (>{timeout_s}s)"
        except Exception:
            tb = _tb.format_exc()
            logger.exception(
                "handle_action crashed for match=%s action=%s player=%s",
                self.id, request.action_type, request.player_id,
            )
            await self._maybe_kick_auto_repair(
                trigger="exception",
                traceback_text=tb,
                extra_context={
                    "action_type": str(request.action_type),
                    "player_id": request.player_id,
                },
            )
            raise

    @staticmethod
    def _action_timeout_seconds() -> int:
        raw = os.environ.get("ACTION_TIMEOUT_SECONDS", "").strip()
        try:
            return max(1, int(raw)) if raw else 30
        except ValueError:
            return 30

    async def _maybe_kick_auto_repair(
        self,
        *,
        trigger: str,
        traceback_text: str,
        extra_context: Optional[dict] = None,
    ) -> None:
        """Best-effort auto-repair kick; failures here must not propagate."""
        try:
            from . import auto_repair  # lazy import — avoids cycle at module load

            await auto_repair.capture_and_kick(
                match_id=self.id,
                game_mode=getattr(self.game.state, "game_mode", "mtg"),
                traceback_text=traceback_text,
                game_state_snapshot=self._auto_repair_state_snapshot(),
                trigger=trigger,
                extra_context=extra_context,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "auto-repair kick raised for match=%s trigger=%s: %s",
                self.id, trigger, e,
            )

    def _auto_repair_state_snapshot(self) -> dict:
        """Tiny, defensive snapshot — only what's safe to JSON-serialize."""
        try:
            state = self.game.state
            return {
                "game_mode": getattr(state, "game_mode", None),
                "turn_number": getattr(getattr(self.game, "turn_manager", None), "turn_number", None),
                "active_player": (
                    self.game.get_active_player()
                    if hasattr(self.game, "get_active_player") else None
                ),
                "player_ids": list(getattr(state, "players", {}).keys()),
                "is_game_over": (
                    self.game.is_game_over()
                    if hasattr(self.game, "is_game_over") else None
                ),
            }
        except Exception:  # noqa: BLE001
            return {}

    async def _handle_action_body(self, request: PlayerActionRequest) -> tuple[bool, str]:
        """
        Handle a player action request.

        Returns (success, message).
        """
        # Check if game is already finished
        if self.is_finished:
            return False, "Game is already over."

        # Validate action matches the current game mode
        mode = self.game.state.game_mode
        action_prefix = request.action_type.split("_")[0] if "_" in request.action_type else ""
        expected_prefix = _MODE_ACTION_PREFIXES.get(mode)
        if expected_prefix and action_prefix in _MODE_ACTION_PREFIXES.values() and action_prefix != expected_prefix:
            return False, f"Action {request.action_type} is not valid for {mode} mode."

        # Route mode-specific actions to the current mode adapter.
        if request.action_type in _PKM_ACTION_TYPES:
            return await get_server_mode_adapter("pokemon").handle_action(self, request)
        if request.action_type in _HS_ACTION_TYPES:
            return await get_server_mode_adapter("hearthstone").handle_action(self, request)
        if request.action_type in _YGO_ACTION_TYPES:
            return await get_server_mode_adapter("yugioh").handle_action(self, request)
        if request.action_type in _MC_ACTION_TYPES:
            return await get_server_mode_adapter("minecraft").handle_action(self, request)
        if request.action_type in _FIN_ACTION_TYPES:
            return await get_server_mode_adapter("finance").handle_action(self, request)
        if request.action_type in _DEPTHS_ACTION_TYPES:
            return await get_server_mode_adapter("depths").handle_action(self, request)
        if request.action_type in _CATS_ACTION_TYPES:
            return await get_server_mode_adapter("cats").handle_action(self, request)
        if request.action_type in _CLANKERS_ACTION_TYPES:
            return await get_server_mode_adapter("clankers").handle_action(self, request)
        if request.action_type in _SCP_ACTION_TYPES:
            return await get_server_mode_adapter("scp").handle_action(self, request)

        # Combat declarations are not wired through the priority action loop yet.
        if request.action_type in ("DECLARE_ATTACKERS", "DECLARE_BLOCKERS"):
            return False, "Manual combat declarations are not supported via /action yet"

        # Validate it's this player's turn to act
        priority_player = self.game.get_priority_player()
        if request.player_id != priority_player:
            return False, "Not your turn to act"

        # If the engine is waiting on a PendingChoice, the client must submit /choice
        # rather than attempting to take an action (PASS, CAST_SPELL, etc.).
        pending_choice = self.game.get_pending_choice_for_player(request.player_id)
        if pending_choice:
            return False, "Waiting for pending choice; use /choice"

        # Build PlayerAction from request
        action = self._build_action(request)

        # If we're waiting for this player's input, resolve the future
        if (self._pending_action_future and
            self._pending_player_id == request.player_id):
            # Save reference to the processed event before clearing
            processed_event = self._action_processed_event

            self._pending_action_future.set_result(action)
            self._pending_action_future = None
            self._pending_player_id = None

            # Record the action
            self._record_frame(action=request.model_dump())

            # Wait for the game loop to process the action
            if processed_event:
                try:
                    await asyncio.wait_for(processed_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass  # Continue anyway if timeout
                self._action_processed_event = None

            # Give the game loop a chance to advance (AI actions, phase changes)
            # by yielding control briefly
            await asyncio.sleep(0.05)

            return True, "Action accepted"

        return False, "No pending action expected"

    # === Per-mode action shims (for test compatibility) =====================
    # These are thin pass-throughs to the corresponding mode adapters. They
    # exist so test modules (and any legacy callers) that invoke
    # `session.handle_hs_action(...)` / `session.handle_pkm_action(...)` /
    # `session.handle_ygo_action(...)` continue to work.

    async def handle_hs_action(self, request: PlayerActionRequest) -> tuple[bool, str]:
        return await get_server_mode_adapter("hearthstone").handle_action(self, request)

    async def handle_pkm_action(self, request: PlayerActionRequest) -> tuple[bool, str]:
        return await get_server_mode_adapter("pokemon").handle_action(self, request)

    async def handle_ygo_action(self, request: PlayerActionRequest) -> tuple[bool, str]:
        return await get_server_mode_adapter("yugioh").handle_action(self, request)

    def _add_pkm_log(self, text: str, event_type: str, player: Optional[str] = None) -> None:
        """Shim: delegate PKM log entry creation to the Pokemon adapter."""
        get_server_mode_adapter("pokemon").add_log(self, text, event_type, player)

    def _add_ygo_log(self, text: str, event_type: str, player: Optional[str] = None) -> None:
        """Shim: delegate YGO log entry creation to the Yu-Gi-Oh! adapter."""
        get_server_mode_adapter("yugioh").add_log(self, text, event_type, player)

    def _build_action(self, request: PlayerActionRequest) -> PlayerAction:
        """Convert API request to engine PlayerAction."""
        action_type_map = {
            "PASS": ActionType.PASS,
            "CAST_SPELL": ActionType.CAST_SPELL,
            "ACTIVATE_ABILITY": ActionType.ACTIVATE_ABILITY,
            "PLAY_LAND": ActionType.PLAY_LAND,
            "SPECIAL_ACTION": ActionType.SPECIAL_ACTION,
        }

        targets = self._coerce_action_targets(request.targets)

        return PlayerAction(
            type=action_type_map.get(request.action_type, ActionType.PASS),
            player_id=request.player_id,
            card_id=request.card_id,
            targets=targets,
            x_value=request.x_value,
            ability_id=request.ability_id,
            source_id=request.source_id,
        )

    def _coerce_action_targets(self, raw_targets):
        """
        Convert API-provided target IDs into engine Target objects.

        The engine expects `Target` instances for spell resolution (e.g. text-parsed
        "deals N damage to any target" spells). The API payload uses plain IDs.
        """
        if not raw_targets:
            return []

        from src.engine.targeting import Target

        state = self.game.state
        coerced = []

        for group in raw_targets:
            if not group:
                coerced.append([])
                continue

            group_targets = []
            for entry in group:
                # Support a possible future format for divided effects:
                # {"target_id": "...", "amount": 2}
                if isinstance(entry, dict):
                    target_id = entry.get("target_id") or entry.get("id")
                    if not target_id:
                        continue
                    is_player = target_id in state.players
                    group_targets.append(
                        Target(
                            id=target_id,
                            is_player=is_player,
                            divided_amount=entry.get("amount"),
                        )
                    )
                    continue

                target_id = str(entry)
                is_player = target_id in state.players
                group_targets.append(Target(id=target_id, is_player=is_player))

            coerced.append(group_targets)

        return coerced

    async def _get_human_action(
        self,
        player_id: str,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Handler for getting human player actions."""
        pending_choice = self.game.get_pending_choice_for_player(player_id)
        if pending_choice:
            # The engine is waiting on a PendingChoice, not an action.
            # Block here until the client submits /choice.
            loop = asyncio.get_event_loop()
            self._pending_choice_future = loop.create_future()
            self._pending_choice_player_id = player_id
            self._pending_choice_id = pending_choice.id

            if self.on_state_change:
                state = self.get_client_state(player_id)
                await self.on_state_change(player_id, state.model_dump())

            try:
                await asyncio.wait_for(self._pending_choice_future, timeout=300.0)
            except asyncio.TimeoutError:
                # Timeout: choose a safe fallback to avoid permanently wedging the match.
                fallback = []
                if pending_choice.min_choices:
                    for opt in pending_choice.options[:pending_choice.min_choices]:
                        if isinstance(opt, dict):
                            if opt.get("id") is not None:
                                fallback.append(opt["id"])
                            elif opt.get("index") is not None:
                                fallback.append(opt["index"])
                            else:
                                fallback.append(opt)
                        else:
                            fallback.append(opt)
                self.game.submit_choice(pending_choice.id, player_id, fallback)

            # The choice submission already advanced the game. Return a no-op
            # action so the priority loop continues without counting as a pass.
            return PlayerAction(type=ActionType.SPECIAL_ACTION, player_id=player_id)

        # Create a future to wait for the action
        loop = asyncio.get_event_loop()
        self._pending_action_future = loop.create_future()
        self._pending_player_id = player_id
        # Create event that will be signaled by on_action_processed callback
        self._action_processed_event = asyncio.Event()

        # Notify the client they need to act
        if self.on_state_change:
            state = self.get_client_state(player_id)
            await self.on_state_change(player_id, state.model_dump())

        # Wait for the action
        try:
            action = await asyncio.wait_for(self._pending_action_future, timeout=300.0)
            return action
        except asyncio.TimeoutError:
            # Timeout - pass priority, signal event so handle_action doesn't hang
            if self._action_processed_event:
                self._action_processed_event.set()
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

    async def handle_choice(self, choice_id: str, player_id: str, selected: list[Any]) -> tuple[bool, str, list[Any]]:
        """
        Handle a /choice submission.

        Returns (success, message, events).
        """
        success, message, events = self.game.submit_choice(
            choice_id=choice_id,
            player_id=player_id,
            selected=selected,
        )

        if success:
            # Unblock a waiting human choice request, if any.
            if (
                self._pending_choice_future
                and not self._pending_choice_future.done()
                and self._pending_choice_player_id == player_id
                and (self._pending_choice_id is None or self._pending_choice_id == choice_id)
            ):
                self._pending_choice_future.set_result(True)

            self._pending_choice_future = None
            self._pending_choice_player_id = None
            self._pending_choice_id = None

            # Record the choice for replays/clients.
            self._record_frame(action={
                "type": "choice",
                "choice_id": choice_id,
                "player_id": player_id,
                "selected": selected,
            })

        return success, message, events

    async def _get_ai_action(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Handler for AI player actions (sync or async brains).

        Wraps the real work in :meth:`_get_ai_action_body` with auto-repair
        hooks (Phase 3):
          - uncaught Exception → ``exception`` kick, then re-raise
          - None return        → ``ai_none_returned`` kick, but DON'T raise
                                 (caller may handle None — we just notify)
        """
        try:
            action = await self._get_ai_action_body(player_id, state, legal_actions)
        except Exception:
            tb = _tb.format_exc()
            logger.exception(
                "_get_ai_action crashed for match=%s player=%s",
                self.id, player_id,
            )
            await self._maybe_kick_auto_repair(
                trigger="exception",
                traceback_text=tb,
                extra_context={"player_id": player_id, "source": "_get_ai_action"},
            )
            raise
        if action is None:
            await self._maybe_kick_auto_repair(
                trigger="ai_none_returned",
                traceback_text=(
                    f"_get_ai_action returned None for player={player_id} "
                    f"with {len(legal_actions)} legal actions"
                ),
                extra_context={"player_id": player_id, "source": "_get_ai_action"},
            )
        return action

    async def _get_ai_action_body(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Handler for AI player actions (sync or async brains)."""
        # First, check if there's a pending choice for the AI.
        pending_choice = self.game.get_pending_choice()
        if pending_choice and pending_choice.player == player_id:
            # AI needs to make a choice, not take an action.
            self._handle_ai_choice(player_id, pending_choice, state)
            # Return pass - the choice handling will advance the game.
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        profile = self.ai_profiles_by_player.get(player_id) or {}
        brain = (profile.get("brain") or "heuristic").strip().lower()

        if brain in ("openai", "anthropic", "ollama"):
            try:
                mode = self._llm_decision_mode(player_id, state, legal_actions)

                if mode == "skip":
                    action = PlayerAction(type=ActionType.PASS, player_id=player_id)
                    action.data["ai"] = {
                        "brain": brain,
                        "model": profile.get("model"),
                        "reasoning": "autopass (no non-pass legal actions)",
                    }
                    return action

                if mode == "interrupt":
                    should_interrupt, gate_meta = await self._llm_should_interrupt(
                        player_id=player_id,
                        state=state,
                        legal_actions=legal_actions,
                        profile=profile,
                    )
                    if not should_interrupt:
                        action = PlayerAction(type=ActionType.PASS, player_id=player_id)
                        action.data["ai"] = gate_meta
                        return action

                    action = self._pick_interrupt_action(player_id, state, legal_actions)
                    action.data["ai"] = gate_meta
                    return action

                return await self._get_llm_action(player_id, state, legal_actions, profile)
            except Exception as e:
                # LLM failures should not wedge the match.
                action = self._simple_ai_action(player_id, legal_actions)
                action.data.setdefault("llm_error", str(e))
                return action

        # Default: built-in heuristic AI.
        try:
            ai = self._get_or_create_ai_engine(player_id)
            action = ai.get_action(player_id, state, legal_actions)
            action.data.setdefault("ai", {"brain": "heuristic", "difficulty": self._get_ai_difficulty(player_id)})
            return action
        except ImportError:
            return self._simple_ai_action(player_id, legal_actions)

    def _llm_decision_mode(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction],
    ) -> str:
        """
        Choose LLM behavior for this priority window.

        Returns one of:
        - "full": ask model to select an action index (our own main-phase planning)
        - "interrupt": off-phase yes/no interrupt gate
        - "skip": no meaningful actions beyond pass
        """
        if not legal_actions or all(a.type == ActionType.PASS for a in legal_actions):
            return "skip"

        active_player = self.game.get_active_player()
        phase = self.game.get_current_phase()
        step = self.game.get_current_step()

        # Full planning only for our own main phase.
        if (
            active_player == player_id
            and phase in (Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN)
            and step == Step.MAIN
        ):
            return "full"

        return "interrupt"

    def _pick_interrupt_action(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction],
    ) -> PlayerAction:
        """Select a non-pass action without making a second LLM call."""
        non_pass = [a for a in legal_actions if a.type != ActionType.PASS]
        if not non_pass:
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        try:
            ai = self._get_or_create_ai_engine(player_id)
            action = ai.get_action(player_id, state, non_pass)
            if action.type != ActionType.PASS:
                return action
        except Exception:
            pass

        # Fallback to simple AI if heuristic engine fails.
        fallback = self._simple_ai_action(player_id, non_pass)
        if fallback.type != ActionType.PASS:
            return fallback

        # Last resort: first legal non-pass action.
        first = non_pass[0]
        return PlayerAction(
            type=first.type,
            player_id=player_id,
            card_id=first.card_id,
            ability_id=first.ability_id,
            source_id=first.source_id,
        )

    async def _llm_should_interrupt(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction],
        profile: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """
        Off-phase interrupt gate with a single LLM call.

        The model gets a compact "what opponent just did" context and must answer
        exactly "yes" or "no".
        """
        provider = self._get_or_create_llm_provider(player_id, profile)
        prompt = self._build_llm_interrupt_prompt(player_id, state, legal_actions)
        system = (
            "You are a real-time MTG interrupt gate.\n"
            "Decide whether to interrupt RIGHT NOW.\n"
            "Output exactly one token: yes or no.\n"
            "No punctuation. No explanation."
        )

        import hashlib

        cache = self._llm_response_cache_by_player.setdefault(player_id, {})
        cache_key = hashlib.sha256(
            f"interrupt\n{provider.model_name}\n{system}\n{prompt}".encode("utf-8")
        ).hexdigest()[:24]

        cached = False
        if cache_key in cache:
            raw_text = str(cache[cache_key].get("raw", "")).strip()
            cached = True
        else:
            response = await provider.complete(
                prompt=prompt,
                system=system,
                temperature=0.0,
            )
            raw_text = (response.content or "").strip()
            cache[cache_key] = {"raw": raw_text}
            if len(cache) > 512:
                cache.clear()

        lower = raw_text.strip().lower()
        match = re.search(r"\b(yes|no)\b", lower)
        if match:
            decision = match.group(1)
        elif lower.startswith("y"):
            decision = "yes"
        else:
            decision = "no"

        meta: dict[str, Any] = {
            "brain": (profile.get("brain") or "").strip().lower(),
            "model": provider.model_name,
            "mode": "interrupt_gate",
            "decision": decision,
            "reasoning": f"interrupt gate: {decision}",
            "raw": raw_text[:120],
            "cached": cached,
            "opponent_action": self._describe_last_opponent_action(player_id),
        }

        if bool(profile.get("record_prompts")):
            max_chars = int(profile.get("max_prompt_chars", 8000))
            meta["prompt"] = prompt[:max_chars]

        return decision == "yes", meta

    def _describe_last_opponent_action(self, player_id: str) -> str:
        """Human-readable summary of the most recent opponent non-pass action."""
        action = self._last_non_pass_action
        if not action:
            return "No recent opponent action."
        if action.get("player_id") == player_id:
            return "Most recent non-pass action was ours."

        who = action.get("player_name") or action.get("player_id") or "Opponent"
        action_type = action.get("action_type") or "ACTION"
        card_name = action.get("card_name") or ""
        if card_name:
            return f"{who} {action_type} {card_name}"
        return f"{who} {action_type}"

    def _build_llm_interrupt_prompt(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction],
    ) -> str:
        """Prompt for the off-phase interrupt yes/no gate."""
        non_pass = [a for a in legal_actions if a.type != ActionType.PASS]
        opponent_id = next((pid for pid in state.players if pid != player_id), None)
        player = state.players.get(player_id)
        opponent = state.players.get(opponent_id) if opponent_id else None

        turn = getattr(self.game.turn_manager, "turn_number", 0)
        phase = self.game.get_current_phase().name
        step = self.game.get_current_step().name
        active = self.game.get_active_player()

        stack_summary = self._summarize_zone_cards(state, "stack", max_cards=6, include_cost=False)
        our_board = self._summarize_battlefield(state, player_id, max_permanents=14)
        opp_board = self._summarize_battlefield(state, opponent_id, max_permanents=14) if opponent_id else "Unknown"
        untapped_lands = self._count_untapped_lands(state, player_id)
        last_opp_action = self._describe_last_opponent_action(player_id)

        action_lines = []
        for i, action in enumerate(non_pass):
            name = ""
            if action.card_id:
                obj = state.objects.get(action.card_id)
                if obj:
                    name = obj.name
            desc = action.description or action.type.name
            if name and name not in desc:
                desc = f"{desc} [{name}]"
            action_lines.append(f"- {i + 1}. {desc}")
        legal_block = "\n".join(action_lines) if action_lines else "- none"

        return (
            "State snapshot for interrupt decision:\n"
            f"Turn: {turn}\n"
            f"Phase/Step: {phase}/{step}\n"
            f"Active player: {active}\n"
            f"Our life: {player.life if player else '??'} | Opp life: {opponent.life if opponent else '??'}\n"
            f"Untapped lands we control: {untapped_lands}\n"
            f"Most recent opponent action: {last_opp_action}\n"
            f"Stack: {stack_summary}\n"
            f"Our battlefield: {our_board}\n"
            f"Opponent battlefield: {opp_board}\n"
            "Available non-pass responses right now:\n"
            f"{legal_block}\n\n"
            "Decision policy:\n"
            "- yes: interrupt now only if a response is materially better than passing.\n"
            "- no: pass if action is low-value, speculative, or not time-sensitive.\n\n"
            "Answer with only: yes or no."
        )

    def _get_ai_difficulty(self, player_id: str) -> str:
        profile = self.ai_profiles_by_player.get(player_id) or {}
        return (profile.get("difficulty") or self.ai_difficulty or "medium").strip().lower()

    def _get_or_create_ai_engine(self, player_id: Optional[str] = None) -> 'AIEngine':
        """Get or create the AI engine for a specific player."""
        if player_id is None:
            # Backward compatibility: infer target AI player when older callers
            # don't pass an explicit player_id.
            ai_candidates = [pid for pid in self.player_ids if pid not in self.human_players]
            if ai_candidates:
                player_id = ai_candidates[0]
            elif self.player_ids:
                player_id = self.player_ids[0]
            else:
                # Keep backward compatibility for tests/utility callers that
                # create a session only to access a configured AI engine.
                player_id = "__default__"

        if player_id in self._ai_engines_by_player:
            return self._ai_engines_by_player[player_id]

        from src.ai import AIEngine

        profile = self.ai_profiles_by_player.get(player_id) or {}
        brain = (profile.get("brain") or "heuristic").strip().lower()
        difficulty = self._get_ai_difficulty(player_id)

        if difficulty == "ultra":
            engine = AIEngine.create_ultra_bot()
        else:
            engine = AIEngine(difficulty=difficulty)

        # For LLM-brain bots, this engine is only used as a lightweight fallback
        # selector (post-yes interrupt).
        if brain in ("openai", "anthropic", "ollama") and difficulty == "ultra":
            player_name = profile.get("name", player_id)
            has_layers = getattr(engine, "_layers_prepared", False)
            layer_status = "with strategy layers" if has_layers else "without strategy layers (will use Midrange fallback)"
            logger.info(
                f"LLM bot '{player_name}' ({brain}) using Ultra fallback engine {layer_status}"
            )

        self._ai_engines_by_player[player_id] = engine
        return engine

    def _get_or_create_choice_engine(self, player_id: str) -> 'AIEngine':
        """Choice helper engine (used for PendingChoice handling)."""
        if player_id in self._choice_engines_by_player:
            return self._choice_engines_by_player[player_id]

        from src.ai import AIEngine

        profile = self.ai_profiles_by_player.get(player_id) or {}
        brain = (profile.get("brain") or "heuristic").strip().lower()
        difficulty = self._get_ai_difficulty(player_id)

        # Avoid creating an "ultra" engine for LLM-driven bots; it's unnecessary and can
        # introduce extra provider calls / assumptions. Choices are handled heuristically.
        if brain in ("openai", "anthropic", "ollama") and difficulty == "ultra":
            difficulty = "medium"

        if difficulty == "ultra":
            # Choices don't benefit from full UltraStrategy; keep it lightweight.
            difficulty = "hard"

        engine = AIEngine(difficulty=difficulty)
        self._choice_engines_by_player[player_id] = engine
        return engine

    def _handle_ai_choice(
        self,
        player_id: str,
        pending_choice,
        state: GameState
    ) -> None:
        """Have the AI make a pending choice."""
        try:
            ai = self._get_or_create_choice_engine(player_id)

            # AI makes the choice
            selected = ai.make_choice(player_id, pending_choice, state)

            # Submit the choice
            success, message, events = self.game.submit_choice(
                choice_id=pending_choice.id,
                player_id=player_id,
                selected=selected
            )

            if not success:
                print(f"AI choice failed: {message}")
                # Fallback: select minimum required options
                fallback_selected = list(pending_choice.options[:pending_choice.min_choices])
                self.game.submit_choice(
                    choice_id=pending_choice.id,
                    player_id=player_id,
                    selected=fallback_selected
                )
            else:
                # Record the choice for bot-game replays.
                if self.record_actions_for_replay:
                    self._record_frame(action={
                        "kind": "ai_choice",
                        "choice_id": pending_choice.id,
                        "choice_type": getattr(pending_choice, "choice_type", None),
                        "player_id": player_id,
                        "player_name": self.player_names.get(player_id, player_id),
                        "selected": self._jsonify_choice_selected(selected),
                    })
        except Exception as e:
            print(f"Error in AI choice handling: {e}")
            import traceback
            traceback.print_exc()

    def _simple_ai_action(
        self,
        player_id: str,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Simple fallback AI that plays cards when possible."""
        # Look for castable spells or lands to play
        for action in legal_actions:
            if action.type == ActionType.PLAY_LAND:
                return PlayerAction(
                    type=ActionType.PLAY_LAND,
                    player_id=player_id,
                    card_id=action.card_id
                )
            elif action.type == ActionType.CAST_SPELL and not action.requires_mana:
                return PlayerAction(
                    type=ActionType.CAST_SPELL,
                    player_id=player_id,
                    card_id=action.card_id
                )

        # Default: pass
        return PlayerAction(type=ActionType.PASS, player_id=player_id)

    # === LLM Bot Brains ======================================================

    async def _get_llm_action(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction],
        profile: dict[str, Any],
    ) -> PlayerAction:
        """
        Choose an action using an LLM provider.

        The LLM MUST select an index from the provided legal action list.
        Targeting/modes/X-values are handled by the engine via PendingChoice when needed.
        """
        provider = self._get_or_create_llm_provider(player_id, profile)

        prompt = self._build_llm_action_prompt(player_id, state, legal_actions)
        schema = {"action_index": "int", "reasoning": "str"}
        system = (
            "You are an expert Magic: The Gathering player.\n"
            "Choose the best LEGAL action from the provided list.\n"
            "Avoid passing unless there is a strong reason.\n"
            "Return JSON only."
        )

        temperature = float(profile.get("temperature", 0.2))
        import hashlib

        cache = self._llm_response_cache_by_player.setdefault(player_id, {})
        cache_key = hashlib.sha256(f"{provider.model_name}\n{system}\n{prompt}".encode("utf-8")).hexdigest()[:24]

        cached = False
        if cache_key in cache:
            response = cache[cache_key]
            cached = True
        else:
            response = await provider.complete_json(
                prompt=prompt,
                schema=schema,
                system=system,
                temperature=temperature,
            )
            cache[cache_key] = response
            # Keep caches bounded (per player).
            if len(cache) > 512:
                cache.clear()

        try:
            idx = int(response.get("action_index", 0))
        except Exception:
            idx = 0

        if idx < 0 or idx >= len(legal_actions):
            idx = 0

        reasoning = str(response.get("reasoning", "") or "").strip()

        chosen = legal_actions[idx] if legal_actions else None
        if not chosen:
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        action = PlayerAction(
            type=chosen.type,
            player_id=player_id,
            card_id=chosen.card_id,
            ability_id=chosen.ability_id,
            source_id=chosen.source_id,
        )

        # Attach structured metadata for replay/debugging.
        legal_summaries = []
        for i, la in enumerate(legal_actions):
            card_name = None
            if la.card_id:
                obj = state.objects.get(la.card_id)
                card_name = obj.name if obj else None
            legal_summaries.append({
                "i": i,
                "type": la.type.name,
                "description": la.description,
                "card_name": card_name,
            })

        ai_meta: dict[str, Any] = {
            "brain": (profile.get("brain") or "").strip().lower(),
            "model": provider.model_name,
            "temperature": temperature,
            "selected_index": idx,
            "reasoning": reasoning,
            "legal_actions": legal_summaries,
            "llm_response": response,
            "cached": cached,
        }

        if bool(profile.get("record_prompts")):
            # Keep prompts from exploding replay size.
            max_chars = int(profile.get("max_prompt_chars", 8000))
            ai_meta["prompt"] = prompt[:max_chars]

        action.data["ai"] = ai_meta
        return action

    def _get_or_create_llm_provider(self, player_id: str, profile: dict[str, Any]):
        """Create and cache the LLM provider for a player."""
        if player_id in self._llm_providers_by_player:
            return self._llm_providers_by_player[player_id]

        brain = (profile.get("brain") or "").strip().lower()
        model = (profile.get("model") or "").strip() or None

        from src.ai.llm import LLMConfig, OpenAIProvider, ClaudeCodeProvider, OllamaProvider

        config = LLMConfig()

        if brain == "openai":
            provider = OpenAIProvider(
                api_key=config.openai_key,
                model=model or config.openai_model,
                timeout=config.timeout,
            )
        elif brain == "anthropic":
            # Anthropic is now reached via the Claude Code CLI subprocess
            # (OAuth creds at ~/.claude), not the HTTP API — no key needed.
            # The "anthropic" brain value is kept for profile back-compat.
            provider = ClaudeCodeProvider(
                model=model or config.claude_code_model,
                timeout=config.timeout,
            )
        elif brain == "ollama":
            provider = OllamaProvider(
                host=config.ollama_host,
                model=model or config.ollama_model,
                timeout=config.timeout,
            )
        else:
            raise RuntimeError(f"Unknown LLM brain: {brain}")

        if not getattr(provider, "is_available", False):
            raise RuntimeError(f"LLM provider '{brain}' not available (missing key or service down)")

        self._llm_providers_by_player[player_id] = provider
        return provider

    def _build_llm_action_prompt(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction],
    ) -> str:
        """Build a compact, model-friendly prompt describing state + legal actions."""
        opponent_id = next((pid for pid in state.players if pid != player_id), None)
        player = state.players.get(player_id)
        opponent = state.players.get(opponent_id) if opponent_id else None

        turn = getattr(self.game.turn_manager, "turn_number", 0)
        phase = self.game.get_current_phase().name if hasattr(self.game, "get_current_phase") else ""
        step = self.game.get_current_step().name if hasattr(self.game, "get_current_step") else ""
        active_player = self.game.get_active_player() if hasattr(self.game, "get_active_player") else None

        hand_summary = self._summarize_zone_cards(state, f"hand_{player_id}", max_cards=14, include_cost=True)
        our_bf = self._summarize_battlefield(state, player_id, max_permanents=16)
        opp_bf = self._summarize_battlefield(state, opponent_id, max_permanents=16) if opponent_id else "Unknown"
        stack = self._summarize_zone_cards(state, "stack", max_cards=6, include_cost=False)

        untapped_lands = self._count_untapped_lands(state, player_id)

        # Legal action list.
        action_lines = []
        for i, la in enumerate(legal_actions):
            line = f"{i}. {la.type.name} - {la.description or la.type.name}"
            if la.card_id:
                obj = state.objects.get(la.card_id)
                if obj:
                    cost = (obj.characteristics.mana_cost or "").strip()
                    if cost:
                        line += f" | Cost: {cost}"
                    if obj.card_def and obj.card_def.text:
                        text = (obj.card_def.text or "").replace("\n", " ").strip()
                        if len(text) > 180:
                            text = text[:177] + "..."
                        line += f" | Text: {text}"
            action_lines.append(line)

        actions_block = "\n".join(action_lines) if action_lines else "0. PASS - Pass priority"

        return (
            "You have priority in a Magic: The Gathering game.\n"
            "Pick the best legal action index.\n\n"
            f"Turn: {turn}\n"
            f"Phase/Step: {phase}/{step}\n"
            f"Active player: {active_player}\n\n"
            f"Life: you={player.life if player else '??'} opp={opponent.life if opponent else '??'}\n"
            f"Untapped lands you control: {untapped_lands}\n\n"
            f"Your hand: {hand_summary}\n"
            f"Your battlefield: {our_bf}\n"
            f"Opponent battlefield: {opp_bf}\n"
            f"Stack: {stack}\n\n"
            "Legal actions:\n"
            f"{actions_block}\n\n"
            'Respond with ONLY JSON: {"action_index": int, "reasoning": str}\n'
        )

    def _summarize_zone_cards(
        self,
        state: GameState,
        zone_key: str,
        max_cards: int = 12,
        include_cost: bool = False,
    ) -> str:
        zone = state.zones.get(zone_key)
        if not zone or not zone.objects:
            return "Empty"

        parts = []
        for obj_id in zone.objects[:max_cards]:
            obj = state.objects.get(obj_id)
            if not obj:
                continue
            label = obj.name
            if include_cost and getattr(obj, "characteristics", None):
                cost = (obj.characteristics.mana_cost or "").strip()
                if cost:
                    label = f"{label} {cost}"
            parts.append(label)

        remaining = max(0, len(zone.objects) - max_cards)
        if remaining:
            parts.append(f"...(+{remaining} more)")

        return ", ".join(parts) if parts else "Empty"

    def _summarize_battlefield(
        self,
        state: GameState,
        player_id: Optional[str],
        max_permanents: int = 16,
    ) -> str:
        if not player_id:
            return "Unknown"

        battlefield = state.zones.get("battlefield")
        if not battlefield or not battlefield.objects:
            return "Empty"

        from src.engine import CardType

        parts = []
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller != player_id:
                continue

            tapped = " (tapped)" if getattr(obj, "state", None) and obj.state.tapped else ""
            chars = getattr(obj, "characteristics", None)
            if chars and CardType.CREATURE in chars.types:
                p = obj.characteristics.power or 0
                t = obj.characteristics.toughness or 0
                parts.append(f"{obj.name} {p}/{t}{tapped}")
            else:
                parts.append(f"{obj.name}{tapped}")

            if len(parts) >= max_permanents:
                break

        if not parts:
            return "Empty"

        if len(parts) >= max_permanents:
            parts.append("...(more)")

        return ", ".join(parts)

    def _count_untapped_lands(self, state: GameState, player_id: str) -> int:
        from src.engine import CardType

        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return 0

        count = 0
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller != player_id:
                continue
            if CardType.LAND in obj.characteristics.types and not obj.state.tapped:
                count += 1
        return count

    def _jsonify_choice_selected(self, selected: list[Any]) -> list[Any]:
        """Best-effort conversion of choice selections into JSON-friendly primitives."""
        out: list[Any] = []
        for item in selected or []:
            if hasattr(item, "id"):
                out.append(getattr(item, "id"))
            else:
                out.append(item)
        return out

    def _serialize_processed_action(self, action: Optional[PlayerAction]) -> Optional[dict]:
        """Convert an engine PlayerAction into a replay-friendly dict."""
        if action is None:
            return None

        card_name = None
        if action.card_id:
            obj = self.game.state.objects.get(action.card_id)
            if obj:
                card_name = obj.name

        return {
            "kind": "action_processed",
            "player_id": action.player_id,
            "player_name": self.player_names.get(action.player_id, action.player_id),
            "action_type": action.type.name if hasattr(action.type, "name") else str(action.type),
            "card_id": action.card_id,
            "card_name": card_name,
            "ability_id": action.ability_id,
            "source_id": action.source_id,
            "targets": self._jsonify_action_targets(getattr(action, "targets", None)),
            "x_value": getattr(action, "x_value", 0),
            "modes": list(getattr(action, "modes", []) or []),
            "data": self._jsonify_action_data(getattr(action, "data", {}) or {}),
        }

    def _jsonify_action_targets(self, targets) -> list[list[str]]:
        """Convert engine Target objects to plain ids for JSON."""
        if not targets:
            return []

        out: list[list[str]] = []
        for group in targets:
            if not group:
                out.append([])
                continue
            grp: list[str] = []
            for t in group:
                if hasattr(t, "id"):
                    grp.append(str(getattr(t, "id")))
                else:
                    grp.append(str(t))
            out.append(grp)
        return out

    def _jsonify_action_data(self, data: dict) -> dict:
        """
        Best-effort conversion of PlayerAction.data into JSON.

        This is primarily used for bot metadata (LLM prompts/reasoning). If any
        value isn't JSON-serializable, we stringify it.
        """
        import json

        if not data:
            return {}

        def coerce(value):
            if value is None or isinstance(value, (bool, int, float, str)):
                return value
            if isinstance(value, list):
                return [coerce(v) for v in value]
            if isinstance(value, dict):
                return {str(k): coerce(v) for k, v in value.items()}
            try:
                json.dumps(value)
                return value
            except Exception:
                return str(value)

        return coerce(data)  # type: ignore[return-value]

    def _get_attacks(
        self,
        player_id: str,
        legal_attackers: list[str]
    ) -> list[AttackDeclaration]:
        """Handler for getting attack declarations."""
        # Attack with all legal attackers
        # TODO: Implement action-based attack declaration for more control
        defending_players = [
            pid for pid in self.player_ids if pid != player_id
        ]
        if not defending_players:
            return []

        defender = defending_players[0]
        return [
            AttackDeclaration(
                attacker_id=aid,
                defending_player_id=defender
            )
            for aid in legal_attackers
        ]

    def _get_blocks(
        self,
        player_id: str,
        attackers: list[AttackDeclaration],
        legal_blockers: list[str]
    ) -> list[BlockDeclaration]:
        """Handler for getting block declarations."""
        # Simple blocking strategy - block with available creatures
        # TODO: Implement action-based blocking for more control
        blocks = []
        available_blockers = list(legal_blockers)

        for attacker in attackers:
            if available_blockers:
                blocker = available_blockers.pop(0)
                blocks.append(BlockDeclaration(
                    blocker_id=blocker,
                    blocking_attacker_id=attacker.attacker_id
                ))

        return blocks

    def _get_mulligan_decision(
        self,
        player_id: str,
        hand: list,
        mulligan_count: int
    ):
        """
        Handler for mulligan decisions.

        Returns either a bool (sync auto-keep / MTG heuristic) or an awaitable
        coroutine (Minecraft human-driven flow that waits for a UI decision).

        - Minecraft + connected human → returns coroutine, waits for client
        - Minecraft + AI / disconnected human → True (auto-keep)
        - Other modes → MTG land-count heuristic (existing behaviour)
        """
        if self.game.state.game_mode == "minecraft":
            if player_id in self.human_players and player_id in self.player_sockets:
                # Coroutine: the engine awaits this and the UI resolves it.
                return self._await_minecraft_mulligan_decision(player_id, mulligan_count)
            # AI players (or humans with no live socket): auto-keep first hand.
            return True

        # Default: MTG-style land-count heuristic.
        # Always keep at 4+ mulligans (3 cards or fewer)
        if mulligan_count >= 4:
            return True

        # Count lands in hand
        land_count = sum(1 for card in hand if CardType.LAND in card.characteristics.types)

        # Count playable cards (CMC <= 3)
        playable_count = sum(
            1 for card in hand
            if CardType.LAND not in card.characteristics.types
            and card.characteristics.mana_cost.count('{') <= 3
        )

        # Ideal hand: 2-4 lands with at least 1 playable spell
        if 2 <= land_count <= 4 and playable_count >= 1:
            return True

        # At mulligan 3 (4 cards), be less picky
        if mulligan_count >= 3 and 1 <= land_count <= 5:
            return True

        # Mulligan hands with 0-1 or 6+ lands
        return False

    async def _await_minecraft_mulligan_decision(
        self,
        player_id: str,
        mulligan_count: int,
    ) -> bool:
        """Async waiter for a human Minecraft mulligan decision.

        Stages a mulligan-prompt entry on _mulligan_state, broadcasts the new
        client state so the frontend can render the keep/mulligan buttons,
        then awaits a future that handle_action resolves when the player picks.
        Falls back to keep on timeout.
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_mulligan_futures[player_id] = future

        # Cost of the NEXT mulligan, if the player chooses to mull again.
        # Free mulligan #0 (count 0). Each mulligan after costs one card.
        cost_for_next = max(0, mulligan_count)
        # If the player keeps this hand right now, that's how many cards land
        # on the bottom of their library: max(0, mulligan_count - 1).
        cost_to_keep = max(0, mulligan_count - 1)
        hand_size_after_keep = 6 - cost_to_keep

        self._mulligan_state[player_id] = {
            "mulligan_count": mulligan_count,
            "hand_size_after_keep": hand_size_after_keep,
            "cost_for_next": cost_for_next,
        }

        # Push current state to the client. They'll see the mulligan prompt.
        if self.on_state_change:
            try:
                state = self.get_client_state(player_id)
                await self.on_state_change(player_id, state.model_dump())
            except Exception:
                # Don't let serialization errors stall game start.
                pass

        try:
            keep = await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            keep = True  # Default: keep on timeout to avoid stalling

        # Clear UI state and the future regardless of outcome.
        self._pending_mulligan_futures.pop(player_id, None)
        self._mulligan_state.pop(player_id, None)
        return bool(keep)

    def resolve_mulligan_decision(self, player_id: str, keep: bool) -> bool:
        """Public hook used by mode adapters to resolve the pending future."""
        future = self._pending_mulligan_futures.get(player_id)
        if future is None or future.done():
            return False
        future.set_result(bool(keep))
        return True

    def _get_variant_resources(self, player) -> dict[str, int]:
        """
        Serialize variant resource counters exposed on Player objects.

        Variants can attach `player.variant_resources` as a dict[str, int] and optional
        attunement counters (`attunements_per_turn`, `attunements_this_turn`).
        """
        raw = getattr(player, "variant_resources", None)
        out: dict[str, int] = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                try:
                    out[str(key)] = int(value)
                except Exception:
                    continue

        try:
            per_turn = int(getattr(player, "attunements_per_turn", 0) or 0)
            used = int(getattr(player, "attunements_this_turn", 0) or 0)
        except Exception:
            per_turn = 0
            used = 0

        if per_turn > 0:
            out.setdefault("attunes_per_turn", per_turn)
            out.setdefault("attunes_left", max(0, per_turn - used))

        return out

    def _serialize_permanent(self, obj) -> CardData:
        """Serialize a permanent for the client."""
        from src.engine.queries import get_power, get_toughness, is_creature

        has_pt = (
            is_creature(obj, self.game.state)
            or CardType.MC_STRUCTURE in obj.characteristics.types
            or CardType.MC_BLOCK in obj.characteristics.types
            or CardType.FIN_TRADER in obj.characteristics.types
        )
        toughness = get_toughness(obj, self.game.state) if has_pt else obj.characteristics.toughness

        # Finance card art — wire through to CardData.image_url so the
        # frontend can render bespoke PNGs from /api/card-art/finance/...
        _image_url: Optional[str] = None
        if self.game.state.game_mode == "finance" and getattr(obj, "card_def", None):
            _image_url = _finance_image_url(obj.card_def, obj.name)

        # Depths card fields
        _depth_band_raw = getattr(obj.state, "depth_band", None)
        _depth_band = None
        if _depth_band_raw is not None:
            _depth_band = getattr(_depth_band_raw, "name", str(_depth_band_raw))
        _depths_cost: dict = {}
        if obj.card_def:
            _cd_cost = getattr(obj.card_def, "depths_cost", None)
            if isinstance(_cd_cost, dict):
                _depths_cost = dict(_cd_cost)
            elif _cd_cost is not None and hasattr(_cd_cost, "torpedo"):
                _depths_cost = {"tc": int(_cd_cost.torpedo), "sc": int(_cd_cost.sonar)}
        # Card-art URL. Already populated on the CardDefinition for sets that
        # ship art (e.g. Depths submarine_fleet); this carries it onto the
        # wire so the frontend's CardData.image_url is populated.
        _image_url = getattr(obj.card_def, "image_url", None) if obj.card_def else None

        return CardData(
            id=obj.id,
            name=obj.name,
            domain=getattr(obj.card_def, "domain", None) if getattr(obj, "card_def", None) else "TOKEN",
            mana_cost=obj.characteristics.mana_cost,
            types=[t.name for t in obj.characteristics.types],
            subtypes=list(obj.characteristics.subtypes),
            power=get_power(obj, self.game.state) if has_pt else None,
            toughness=toughness,
            text=obj.card_def.text if obj.card_def else "",
            tapped=obj.state.tapped,
            counters=dict(obj.state.counters),
            damage=obj.state.damage,
            controller=obj.controller,
            owner=obj.owner,
            keywords=list(obj.characteristics.keywords),
            foil=obj.state.foil,
            divine_shield=obj.state.divine_shield,
            stealth=obj.state.stealth,
            windfury=obj.state.windfury,
            frozen=obj.state.frozen,
            summoning_sickness=obj.state.summoning_sickness,
            attacks_this_turn=obj.state.attacks_this_turn,
            mc_cost=dict(getattr(obj.card_def, "mc_cost", {}) or {}) if obj.card_def else {},
            mc_grid_x=obj.state.mc_grid_x,
            mc_grid_y=obj.state.mc_grid_y,
            mc_gear_slot=obj.state.mc_gear_slot,
            mc_exhausted=obj.state.mc_exhausted,
            mc_keywords=sorted(getattr(obj.card_def, "mc_keywords", None) or ()) if obj.card_def else [],
            # Depths fields
            depth_band=_depth_band,
            detected=bool(getattr(obj.state, "detected", False)),
            is_flagship=bool(
                getattr(obj.state, "is_flagship", False)
                or "Flagship" in list(obj.characteristics.subtypes)
            ),
            depths_cost=_depths_cost,
            image_url=_image_url,
        )

    def _serialize_card(self, obj) -> CardData:
        """Serialize a card for the client (hand/graveyard)."""
        # Depths cost for hand cards
        _depths_cost_hand: dict = {}
        if obj.card_def:
            _cd_cost = getattr(obj.card_def, "depths_cost", None)
            if isinstance(_cd_cost, dict):
                _depths_cost_hand = dict(_cd_cost)
            elif _cd_cost is not None and hasattr(_cd_cost, "torpedo"):
                _depths_cost_hand = {"tc": int(_cd_cost.torpedo), "sc": int(_cd_cost.sonar)}
        # Per-engine image_url resolution. Prefer card_def.image_url
        # (Depths submarine_fleet, Minecraft sets via _wire_image_urls);
        # fall back to Finance's name-derived path if no pre-wired URL.
        _image_url: Optional[str] = (
            getattr(obj.card_def, "image_url", None) if obj.card_def else None
        )
        if (
            _image_url is None
            and self.game.state.game_mode == "finance"
            and getattr(obj, "card_def", None)
        ):
            _image_url = _finance_image_url(obj.card_def, obj.name)
        return CardData(
            id=obj.id,
            name=obj.name,
            domain=getattr(obj.card_def, "domain", None) if getattr(obj, "card_def", None) else "TOKEN",
            mana_cost=obj.characteristics.mana_cost,
            types=[t.name for t in obj.characteristics.types],
            subtypes=list(obj.characteristics.subtypes),
            power=obj.characteristics.power,
            toughness=obj.characteristics.toughness,
            text=obj.card_def.text if obj.card_def else "",
            controller=obj.controller,
            owner=obj.owner,
            keywords=list(obj.characteristics.keywords),
            foil=obj.state.foil,
            mc_cost=dict(getattr(obj.card_def, "mc_cost", {}) or {}) if obj.card_def else {},
            mc_grid_x=obj.state.mc_grid_x,
            mc_grid_y=obj.state.mc_grid_y,
            mc_gear_slot=obj.state.mc_gear_slot,
            mc_exhausted=obj.state.mc_exhausted,
            mc_keywords=sorted(getattr(obj.card_def, "mc_keywords", None) or ()) if obj.card_def else [],
            depths_cost=_depths_cost_hand,
            image_url=_image_url,
        )

    def _serialize_stack_item(self, item) -> StackItemData:
        """Serialize a stack item for the client.

        Handles both ``StackItem`` (spells/activated abilities — has
        ``controller_id``) and ``TriggeredStackItem`` (CR 603.2 triggered
        abilities — has ``controller`` and ``description``).
        """
        source = self.game.state.objects.get(item.source_id)

        # Triggered abilities prefer ``source_card_name`` for display
        # because the source object may have been moved zones since the
        # trigger fired (e.g. a death trigger whose source is now in the
        # graveyard).
        if hasattr(item, 'source_card_name'):
            source_name = item.source_card_name or (source.name if source else "Unknown")
        else:
            source_name = source.name if source else "Unknown"

        controller = getattr(item, 'controller_id', None) or getattr(item, 'controller', '')
        description = getattr(item, 'description', '') or ''

        return StackItemData(
            id=item.id,
            type=item.type.name,
            source_id=item.source_id,
            source_name=source_name,
            controller=controller,
            description=description,
        )

    def _serialize_pending_trigger(self, trig) -> PendingTriggerData:
        """Serialize a pending (queued) triggered ability for the client.

        ``trig`` is a ``TriggeredStackItem`` from ``state.pending_triggers``;
        these are queued but not yet on the stack. The client uses this
        list to render the trigger queue panel before the next priority
        pass.
        """
        source = self.game.state.objects.get(trig.source_id)
        source_name = trig.source_card_name or (source.name if source else "Unknown")
        return PendingTriggerData(
            id=trig.id or '',
            controller=trig.controller,
            source_id=trig.source_id,
            source_name=source_name,
            description=trig.description or '',
        )

    def _serialize_legal_action(self, action: LegalAction) -> LegalActionData:
        """Serialize a legal action for the client."""
        return LegalActionData(
            type=action.type.name,
            card_id=action.card_id,
            ability_id=action.ability_id,
            source_id=action.source_id,
            description=action.description,
            requires_targets=action.requires_targets,
            requires_mana=action.requires_mana
        )

    def _serialize_scp_state(self, game_state, viewer_id: Optional[str]) -> dict:
        """Serialize scp state into the viewer-redacted shape consumed by useSCPGame.ts.

        Fog of war: the cell board comes from ``scp.public_board`` (Phase-1-tested redaction —
        face-down anomaly/layer identities are ``[FACE-DOWN]`` to the non-owner, but advancement
        'heat' stays public). Hands reveal only the viewer's own cards; the opponent exposes a
        count. The Insurgency rig is public (breakers install face-up); Foundation assets install
        face-down, so they're redacted to the opponent.
        """
        from src.engine import scp
        from src.engine.types import CardType

        fid = scp.foundation_id(game_state)
        iid = scp.insurgency_id(game_state)
        # Spectators / replay frames serialize with no viewer; show the Foundation's
        # perspective (its own board revealed, the Insurgency redacted) rather than a
        # blank board. Live play passes the real viewer, so this is a no-op there.
        eff_viewer = viewer_id or fid
        board = scp.public_board(game_state, eff_viewer)
        active = getattr(game_state, "active_player", None)

        def _card_dto(obj_id: str, reveal: bool) -> dict:
            obj = game_state.objects.get(obj_id)
            if obj is None:
                return {"id": obj_id, "name": "?", "kind": None, "hidden": True}
            cd = obj.card_def
            kind = getattr(cd, "scp_kind", None)
            if not reveal:
                return {"id": obj_id, "name": "[REDACTED]", "kind": None, "hidden": True}
            dto = {
                "id": obj_id, "name": obj.name, "hidden": False,
                "kind": kind.name if kind else None,
                "text": (cd.text or "") if cd else "",
                "cost": int(getattr(cd, "scp_cost", 0) or 0),
            }
            if kind == CardType.SCP_ANOMALY:
                dto.update(threshold=int(getattr(cd, "scp_threshold", 0) or 0),
                           value=int(getattr(cd, "scp_value", 0) or 0),
                           trap=bool(getattr(cd, "scp_trap", False)))
            elif kind == CardType.SCP_LAYER:
                dto.update(ltype=getattr(cd, "scp_ltype", None),
                           strength=scp._effective_strength(game_state, obj),
                           rez=int(getattr(cd, "scp_rez", 0) or 0),
                           rezzed=bool(getattr(obj.state, "scp_rezzed", False)))
            elif kind == CardType.SCP_OPERATIVE:
                dto.update(breaks=getattr(cd, "scp_breaks", None),
                           power=int(getattr(cd, "scp_power", 0) or 0),
                           boost=int(getattr(cd, "scp_boost", 1) or 1))
            return dto

        def _seat(pid):
            if pid is None:
                return None
            rec = dict(board["players"].get(pid, {}))  # faction, credits, ap, counters, cells (redacted)
            r = scp.ensure_scp_state(game_state, pid)
            is_me = (pid == eff_viewer)
            hand = scp.hand_ids(game_state, pid)
            rec["hand"] = [_card_dto(h, reveal=True) for h in hand] if is_me else None
            rec["hand_count"] = len(hand)
            rec["deck_count"] = len(scp.deck_ids(game_state, pid))
            rec["discard_count"] = len(scp.discard_ids(game_state, pid))
            rec["rig"] = [_card_dto(o, reveal=True) for o in r.get("rig", []) if o in game_state.objects]
            rec["assets"] = [
                _card_dto(o, reveal=not scp.card_hidden_from(game_state, game_state.objects[o], eff_viewer))
                for o in r.get("assets", []) if o in game_state.objects
            ]
            ident_id = r.get("identity")
            rec["identity"] = game_state.objects[ident_id].name if (ident_id and ident_id in game_state.objects) else None
            return rec

        losers = [pid for pid, p in game_state.players.items() if getattr(p, "has_lost", False)]
        game_over = bool(losers)
        winner = reason = None
        if game_over and fid and iid:
            winner = fid if losers[0] == iid else iid
            f = scp.ensure_scp_state(game_state, fid)
            i = scp.ensure_scp_state(game_state, iid)
            if f["containment_points"] >= scp.CONTAINMENT_TARGET:
                reason = "containment"
            elif i.get("burned_out"):
                reason = "burnout"
            elif i["liberation_points"] >= scp.LIBERATION_TARGET:
                reason = "liberation"
            elif f["total_breach"] >= scp.BREACH_CATASTROPHE:
                reason = "total_breach"
            elif scp._foundation_reachable_containment(game_state, fid) < scp.CONTAINMENT_TARGET:
                # The Foundation can no longer reach Containment (anomaly supply spent) → it lost by
                # collapse; mirrors the engine's check_scp_win so the client shows the real reason.
                reason = "foundation_collapse"

        return {
            "foundation_id": fid, "insurgency_id": iid,
            "viewer_faction": (scp.faction_of(game_state, eff_viewer) if eff_viewer else None),
            "active_player": active,
            "your_turn": bool(viewer_id is not None and viewer_id == active),
            "game_over": game_over, "winner": winner, "win_reason": reason,
            "targets": {"containment": scp.CONTAINMENT_TARGET,
                        "liberation": scp.LIBERATION_TARGET,
                        "breach": scp.BREACH_CATASTROPHE},
            "me": _seat(eff_viewer) if eff_viewer else None,
            "opponent": _seat(scp.opponent_of(game_state, eff_viewer)) if eff_viewer else None,
        }

    def _serialize_cats_state(self, game_state, viewer_id: Optional[str]) -> dict:
        """Serialize the cats engine state into the shape expected by useCatsGame.ts.

        The frontend consumes a single nested ``state.cats`` object with seat-
        relative keys (``player`` / ``opponent``) and short pile names
        (``territory`` / ``nap`` / ``snack`` / ``attention``). We map engine
        identifiers (``pile_territory`` etc.) to the short keys here.
        """
        def _seat(pid: Optional[str]) -> Optional[str]:
            """Map a player_id to 'me' / 'opponent' from the viewer's perspective."""
            if pid is None:
                return None
            if viewer_id is None:
                # No viewer (e.g. bot_vs_bot broadcast) — treat lowest-id seat
                # as 'me' so the payload is still well-formed.
                return "me" if pid == next(iter(game_state.players.keys()), None) else "opponent"
            return "me" if pid == viewer_id else "opponent"

        def _has_knock_over_handler(card_id: str) -> bool:
            """True iff the card has a CATS_KNOCK_OVER REACT interceptor registered.

            We probe by checking each interceptor sourced from this card with a
            synthetic CATS_KNOCK_OVER payload — `make_pile_activated`'s filter
            matches exactly that combination. Avoids importing engine helpers
            into the hot serialization path.
            """
            try:
                from src.engine.types import Event, EventType
            except ImportError:
                return False
            probe = Event(
                type=EventType.CATS_KNOCK_OVER,
                payload={"card_id": card_id},
                source=card_id,
            )
            for ic in (game_state.interceptors or {}).values():
                if ic.source != card_id:
                    continue
                try:
                    if ic.filter(probe, game_state):
                        return True
                except Exception:
                    continue
            return False

        def _card_dto(obj_id: str, reveal: bool = True, in_my_pile: bool = False) -> dict:
            """Serialize one card object to the cats wire shape.

            ``in_my_pile`` is True when the card lives in the viewer's own
            scoring pile — in that case we compute ``is_activatable`` so the
            frontend can render a knock-over affordance. Opponent pile cards
            and hand cards never get this flag.
            """
            obj = game_state.objects.get(obj_id)
            if obj is None:
                return {
                    "id": obj_id,
                    "name": "?",
                    "value": 0,
                    "card_type": "Cat",
                    "tapped": False,
                }
            card_def = obj.card_def
            # Card type label
            card_type = "Cat"
            if card_def is not None:
                try:
                    from src.engine.types import CardType
                    types = card_def.characteristics.types
                    if CardType.CATS_MOOD in types:
                        card_type = "Mood"
                    elif CardType.CATS_SNACK in types:
                        card_type = "Snack"
                    elif CardType.CATS_TRINKET in types:
                        card_type = "Trinket"
                    elif CardType.CATS_COMMANDER in types:
                        card_type = "Commander"
                    elif CardType.CATS_CAT in types:
                        card_type = "Cat"
                except (ImportError, AttributeError):
                    pass
            value = 0
            category = None
            text = ""
            name = obj.name or "?"
            if card_def is not None:
                value = int(getattr(card_def, "cats_value", 0) or 0)
                category = getattr(card_def, "cats_category", None)
                text = card_def.text or ""
            if not reveal:
                # Hide opponent hand cards: opaque "Hidden Cat" placeholder.
                return {
                    "id": obj_id,
                    "name": "Hidden Cat",
                    "value": 0,
                    "card_type": "Cat",
                    "tapped": False,
                }
            tapped = bool(getattr(obj.state, "tapped", False)) if obj.state else False
            dto: dict = {
                "id": obj_id,
                "name": name,
                "value": value,
                "category": category,
                "card_type": card_type,
                "text": text,
                "tapped": tapped,
            }
            if in_my_pile:
                # is_activatable: pile card, owned by viewer, untapped, has a
                # registered CATS_KNOCK_OVER handler. The first three are
                # already implied by the call site; we add the handler check.
                dto["is_activatable"] = (not tapped) and _has_knock_over_handler(obj_id)
            return dto

        def _pile_dto(piles_map: dict, pile_key: str, *, in_my_pile: bool = False) -> list[dict]:
            ids = piles_map.get(pile_key, []) if piles_map else []
            return [_card_dto(oid, reveal=True, in_my_pile=in_my_pile) for oid in ids]

        def _player_state(pid: str, reveal_hand: bool, *, is_viewer: bool) -> dict:
            hand_zone = game_state.zones.get(f"HAND_{pid}")
            hand_ids = list(hand_zone.objects) if hand_zone else []
            piles_map = (getattr(game_state, "cats_piles", {}) or {}).get(pid, {})
            commanders = getattr(game_state, "cats_commanders", {}) or {}
            cmd_id = commanders.get(pid)
            return {
                "hand": [_card_dto(cid, reveal=reveal_hand) for cid in hand_ids],
                "hand_size": len(hand_ids),
                "piles": {
                    "territory": _pile_dto(piles_map, "pile_territory", in_my_pile=is_viewer),
                    "nap": _pile_dto(piles_map, "pile_nap", in_my_pile=is_viewer),
                    "snack": _pile_dto(piles_map, "pile_snack", in_my_pile=is_viewer),
                    "attention": _pile_dto(piles_map, "pile_attention", in_my_pile=is_viewer),
                },
                "commander": _card_dto(cmd_id, reveal=True) if cmd_id else None,
            }

        # Resolve viewer + opponent ids
        all_pids = list(game_state.players.keys())
        if viewer_id and viewer_id in all_pids:
            me_id = viewer_id
            opp_id = next((p for p in all_pids if p != viewer_id), None)
        else:
            me_id = all_pids[0] if all_pids else None
            opp_id = all_pids[1] if len(all_pids) > 1 else None

        # Phase: derive a label from trick state.
        trick = getattr(game_state, "cats_current_trick", None) or {}
        winner_id = trick.get("winner")
        if winner_id is not None:
            phase = "claim"
        elif trick.get("counter_card"):
            phase = "resolve"
        elif trick.get("pounce_card"):
            phase = "counter_pounce"
        else:
            phase = "pounce"

        lead_id = getattr(game_state, "cats_lead_player", None)

        # Installed rule name (Sleek/Fluffy/Scrappy/Sneaky), if any
        installed_rule_name = None
        rule_fn = trick.get("installed_rule") or getattr(game_state, "cats_current_rule", None)
        if rule_fn is not None:
            try:
                from src.engine.cats import CATS_CATEGORY_RULES
                for cat_name, fn in CATS_CATEGORY_RULES.items():
                    if fn is rule_fn:
                        installed_rule_name = cat_name
                        break
            except Exception:
                pass

        current_trick = {
            "pounce_card": _card_dto(trick.get("pounce_card"), reveal=True) if trick.get("pounce_card") else None,
            "counter_card": _card_dto(trick.get("counter_card"), reveal=True) if trick.get("counter_card") else None,
            "winner": _seat(winner_id),
            "installed_rule": installed_rule_name,
        }

        # Final scores when game ends.
        final_scores = None
        if getattr(game_state, "cats_game_over", False):
            scores = getattr(game_state, "cats_final_scores", {}) or {}
            if me_id and opp_id:
                me_score = scores.get(me_id) or {}
                opp_score = scores.get(opp_id) or {}
                def _score_dto(s: dict) -> dict:
                    return {
                        "territory": int(s.get("territory", 0) or 0),
                        "nap": int(s.get("nap", 0) or 0),
                        "snack": int(s.get("snack", 0) or 0),
                        "attention": int(s.get("attention", 0) or 0),
                        "total": int(s.get("total", 0) or 0),
                    }
                final_scores = {
                    "me": _score_dto(me_score),
                    "opponent": _score_dto(opp_score),
                }

        result: dict = {
            "round_number": int(getattr(game_state, "cats_round_number", 1) or 1),
            "phase": phase,
            "lead_player": _seat(lead_id) or "me",
            "current_trick": current_trick,
            "player": _player_state(me_id, reveal_hand=True, is_viewer=True) if me_id else None,
            "opponent": _player_state(opp_id, reveal_hand=False, is_viewer=False) if opp_id else None,
            "game_over": bool(getattr(game_state, "cats_game_over", False)),
        }
        if final_scores is not None:
            result["final_scores"] = final_scores
        return result

    def _serialize_clankers_state(self, game_state, viewer_id: Optional[str]) -> dict:
        """Serialize the clankers engine state for the client.

        Returns a per-player view of workshop integrity, compute / scrap
        pools, hand / library / scrap-heap sizes, the assembly floor with
        each chassis + its attached parts + effective P/I, plus the active
        phase + turn number + deathclock flag.

        Hidden info: opponent hand cards are surfaced as count-only stubs
        (id + "Hidden" placeholder); the viewer's own hand is revealed.
        """
        from src.engine.types import CardType, ZoneType
        from src.engine.clankers import (
            compute_effective_power, compute_effective_integrity,
        )

        all_pids = list(game_state.players.keys())

        def _is_type(obj, type_name: str) -> bool:
            if obj is None or obj.characteristics is None:
                return False
            target = getattr(CardType, type_name, None)
            if target is None:
                return False
            return target in (obj.characteristics.types or set())

        def _part_dto(part_id: str) -> dict:
            obj = game_state.objects.get(part_id)
            if obj is None:
                return {"id": part_id, "name": "?", "kind": "Unknown"}
            kind = "Weapon" if _is_type(obj, "CLANKERS_WEAPON") else (
                "Add-On" if _is_type(obj, "CLANKERS_ADD_ON") else "Part"
            )
            card_def = obj.card_def
            return {
                "id": part_id,
                "name": obj.name or "?",
                "kind": kind,
                "power_bonus": int(getattr(card_def, "power_bonus", 0) or 0) if card_def else 0,
                "integrity_bonus": int(getattr(card_def, "integrity_bonus", 0) or 0) if card_def else 0,
                "armor_value": getattr(card_def, "armor_value", None) if card_def else None,
                "tapped": bool(getattr(obj.state, "tapped", False)) if obj.state else False,
                "text": (card_def.text if card_def else "") or "",
            }

        def _chassis_dto(chassis_id: str) -> dict:
            obj = game_state.objects.get(chassis_id)
            if obj is None:
                return {"id": chassis_id, "name": "?", "attached_parts": []}
            card_def = obj.card_def
            try:
                eff_p = compute_effective_power(game_state, chassis_id)
            except Exception:
                eff_p = int(getattr(card_def, "power", 0) or 0) if card_def else 0
            try:
                eff_i = compute_effective_integrity(game_state, chassis_id)
            except Exception:
                eff_i = int(getattr(card_def, "integrity", 0) or 0) if card_def else 0
            attached = [_part_dto(pid) for pid in (obj.state.attachments or [])]
            damage = int(getattr(obj.state, "damage_marked", 0) or 0)
            return {
                "id": chassis_id,
                "name": obj.name or "?",
                "base_power": int(getattr(card_def, "power", 0) or 0) if card_def else 0,
                "base_integrity": int(getattr(card_def, "integrity", 0) or 0) if card_def else 0,
                "effective_power": eff_p,
                "effective_integrity": eff_i,
                "damage": damage,
                "tapped": bool(getattr(obj.state, "tapped", False)) if obj.state else False,
                "weapon_slots": int(getattr(card_def, "weapon_slots", 2) or 0) if card_def else 0,
                "add_on_slots": int(getattr(card_def, "add_on_slots", 2) or 0) if card_def else 0,
                "attached_parts": attached,
                "controller": obj.controller,
                "text": (card_def.text if card_def else "") or "",
            }

        def _solo_part_dto(part_id: str) -> dict:
            """A weapon / add-on on the floor with no host. Render as a 1/1
            standalone unit per design §4."""
            obj = game_state.objects.get(part_id)
            if obj is None:
                return {"id": part_id, "name": "?", "attached_parts": []}
            base = _part_dto(part_id)
            try:
                eff_p = compute_effective_power(game_state, part_id)
            except Exception:
                eff_p = 1
            try:
                eff_i = compute_effective_integrity(game_state, part_id)
            except Exception:
                eff_i = 1
            base.update({
                "effective_power": eff_p,
                "effective_integrity": eff_i,
                "is_solo": True,
                "controller": obj.controller,
            })
            return base

        def _hand_dto(pid: str, *, reveal: bool) -> list[dict]:
            hand_zone = game_state.zones.get(f"hand_{pid}")
            ids = list(hand_zone.objects) if hand_zone else []
            out: list[dict] = []
            for cid in ids:
                if not reveal:
                    out.append({"id": cid, "name": "Hidden", "hidden": True})
                    continue
                obj = game_state.objects.get(cid)
                if obj is None:
                    out.append({"id": cid, "name": "?", "hidden": False})
                    continue
                card_def = obj.card_def
                # Infer card type label.
                kind = "Unknown"
                if obj.characteristics is not None:
                    types = obj.characteristics.types or set()
                    if CardType.CLANKERS_CHASSIS in types:
                        kind = "Chassis"
                    elif CardType.CLANKERS_WEAPON in types:
                        kind = "Weapon"
                    elif CardType.CLANKERS_ADD_ON in types:
                        kind = "Add-On"
                    elif CardType.CLANKERS_TRANSIENT in types:
                        kind = "Transient"
                    elif CardType.CLANKERS_STRUCTURE in types:
                        kind = "Structure"
                    elif CardType.CLANKERS_CORE in types:
                        kind = "Core"
                out.append({
                    "id": cid,
                    "name": obj.name or "?",
                    "kind": kind,
                    "compute_cost": int(getattr(card_def, "compute_cost", 0) or 0) if card_def else 0,
                    "power": int(getattr(card_def, "power", 0) or 0) if card_def else 0,
                    "integrity": int(getattr(card_def, "integrity", 0) or 0) if card_def else 0,
                    "power_bonus": int(getattr(card_def, "power_bonus", 0) or 0) if card_def else 0,
                    "integrity_bonus": int(getattr(card_def, "integrity_bonus", 0) or 0) if card_def else 0,
                    "weapon_slots": int(getattr(card_def, "weapon_slots", 0) or 0) if card_def else 0,
                    "add_on_slots": int(getattr(card_def, "add_on_slots", 0) or 0) if card_def else 0,
                    "armor_value": getattr(card_def, "armor_value", None) if card_def else None,
                    "text": (card_def.text if card_def else "") or "",
                    "hidden": False,
                })
            return out

        def _floor_dto(pid: str) -> dict:
            """Return chassis+attachments and solo parts for this player."""
            floor_zone = game_state.zones.get(f"clankers_assembly_floor_{pid}")
            ids = list(floor_zone.objects) if floor_zone else []
            chassis: list[dict] = []
            solo_parts: list[dict] = []
            for oid in ids:
                obj = game_state.objects.get(oid)
                if obj is None or obj.card_def is None:
                    continue
                if _is_type(obj, "CLANKERS_CHASSIS"):
                    chassis.append(_chassis_dto(oid))
                elif _is_type(obj, "CLANKERS_WEAPON") or _is_type(obj, "CLANKERS_ADD_ON"):
                    # Solo (unattached) parts live on the floor too.
                    if obj.state.attached_to is None:
                        solo_parts.append(_solo_part_dto(oid))
            return {"chassis": chassis, "solo_parts": solo_parts}

        def _core_dto(pid: str) -> Optional[dict]:
            cores = getattr(game_state, "clankers_cores", {}) or {}
            core_id = cores.get(pid)
            if not core_id:
                return None
            obj = game_state.objects.get(core_id)
            if obj is None:
                return None
            return {
                "id": core_id,
                "name": obj.name or "?",
                "text": (obj.card_def.text if obj.card_def else "") or "",
            }

        def _player_state(pid: str, *, is_viewer: bool) -> dict:
            workshop_dict = getattr(game_state, "clankers_workshop_integrity", {}) or {}
            compute_dict = getattr(game_state, "clankers_compute_pool", {}) or {}
            compute_cap_dict = getattr(game_state, "clankers_compute_cap", {}) or {}
            scrap_dict = getattr(game_state, "clankers_scrap_pool", {}) or {}
            structures_dict = getattr(game_state, "clankers_structures", {}) or {}

            hand_zone = game_state.zones.get(f"hand_{pid}")
            hand_ids = list(hand_zone.objects) if hand_zone else []
            library_zone = game_state.zones.get(f"library_{pid}")
            library_size = len(library_zone.objects) if library_zone else 0
            scrap_zone = game_state.zones.get(f"clankers_scrap_heap_{pid}")
            scrap_heap_size = len(scrap_zone.objects) if scrap_zone else 0

            return {
                "workshop_integrity": int(workshop_dict.get(pid, 0) or 0),
                "compute_pool": int(compute_dict.get(pid, 0) or 0),
                "compute_cap": int(compute_cap_dict.get(pid, 10) or 10),
                "scrap_pool": int(scrap_dict.get(pid, 0) or 0),
                "hand": _hand_dto(pid, reveal=is_viewer),
                "hand_size": len(hand_ids),
                "library_size": library_size,
                "scrap_heap_size": scrap_heap_size,
                "floor": _floor_dto(pid),
                "structures": [
                    _part_dto(sid) for sid in (structures_dict.get(pid, []) or [])
                ],
                "core": _core_dto(pid),
            }

        if viewer_id and viewer_id in all_pids:
            me_id = viewer_id
            opp_id = next((p for p in all_pids if p != viewer_id), None)
        else:
            me_id = all_pids[0] if all_pids else None
            opp_id = all_pids[1] if len(all_pids) > 1 else None

        tm = self.game.turn_manager
        turn_number = int(getattr(tm, "turn_number", 0) or 0)
        active_player_id = getattr(game_state, "active_player", None)
        phase = getattr(game_state, "clankers_current_phase", None)

        result: dict = {
            "turn_number": turn_number,
            "phase": phase,
            "active_player": "me" if active_player_id == me_id else (
                "opponent" if active_player_id == opp_id else None
            ),
            "active_player_id": active_player_id,
            "first_turn": bool(getattr(game_state, "clankers_first_turn", False)),
            "deathclock_active": bool(getattr(game_state, "clankers_containment_failure", False)),
            "deathclock_turn": int(getattr(game_state, "clankers_containment_turn", 0) or 0),
            "player": _player_state(me_id, is_viewer=True) if me_id else None,
            "opponent": _player_state(opp_id, is_viewer=False) if opp_id else None,
        }
        return result

    def _record_frame(self, action: Optional[dict]) -> None:
        """Record a replay frame."""
        if self.max_replay_frames and len(self.replay_frames) >= self.max_replay_frames:
            if not self._replay_truncated:
                self._replay_truncated = True
                print(f"Replay frame cap reached for session {self.id} ({self.max_replay_frames}); truncating replay.")
            return

        state = self.get_client_state()
        frame = ReplayFrame(
            turn=state.turn_number,
            phase=state.phase,
            step=state.step,
            action=action,
            state=state.model_dump(),
            timestamp=time.time()
        )
        self.replay_frames.append(frame)


class SessionManager:
    """
    Manages all active game sessions.
    """

    def __init__(self):
        self.sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        mode: str = "human_vs_bot",
        player_name: str = "Player",
        ai_difficulty: str = "medium",
        game_mode: str = "mtg"
    ) -> GameSession:
        """Create a new game session."""
        async with self._lock:
            session_id = generate_id()
            game = Game(mode=game_mode)

            # Live-game toggle (CR 603.2): MTG matches with at least one human
            # disable the auto-resolve fast path so triggered abilities go on
            # the stack and players get a priority window to respond. Tests
            # leave the default (True) so legacy assertions about inline ETB
            # firing keep working. Bot-vs-bot MTG also stays on auto-resolve
            # because there's no human to use the response window.
            if game_mode == "mtg" and mode in ("human_vs_bot", "human_vs_human"):
                game.state.options.auto_resolve_triggers = False

            session = GameSession(
                id=session_id,
                game=game,
                mode=mode,
                ai_difficulty=ai_difficulty
            )

            self.sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[GameSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    async def remove_session(self, session_id: str) -> None:
        """Remove a session."""
        async with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]

    def get_session_by_socket(self, socket_id: str) -> Optional[tuple[GameSession, str]]:
        """Find a session by socket ID, returning (session, player_id)."""
        for session in self.sessions.values():
            for pid, sid in session.player_sockets.items():
                if sid == socket_id:
                    return session, pid
        return None


# Global session manager instance
session_manager = SessionManager()
