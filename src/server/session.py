"""
Game Session Management

Manages active game sessions, player connections, and game state.
"""

import asyncio
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
    PendingChoiceData, PendingChoiceWaitingData
)

logger = logging.getLogger(__name__)


def generate_id() -> str:
    """Generate a short unique ID."""
    return str(uuid4())[:8]


@dataclass
class GameSession:
    """
    Manages a single game session.

    Wraps the engine Game class and provides:
    - Player socket tracking
    - State serialization for clients
    - Action handling with validation
    - Replay recording
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
        self.deck_card_defs_by_player.setdefault(player_id, []).extend(card_defs)
        for card_def in card_defs:
            self.game.add_card_to_library(player_id, card_def)
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
        """Start the game."""
        if self.is_started:
            return

        self.is_started = True

        # Setup AI handlers based on game mode
        if self.game.state.game_mode == "hearthstone":
            # Setup Hearthstone AI adapter
            from src.ai.hearthstone_adapter import HearthstoneAIAdapter

            # Default difficulty from first AI profile (or 'medium')
            if self.ai_profiles_by_player:
                first_profile = next(iter(self.ai_profiles_by_player.values()))
                difficulty = first_profile.get('difficulty', 'medium')
            else:
                difficulty = 'medium'

            ai_adapter = HearthstoneAIAdapter(difficulty=difficulty)

            # Set per-player difficulty overrides for bot-vs-bot
            for pid, profile in self.ai_profiles_by_player.items():
                player_diff = profile.get('difficulty', difficulty)
                ai_adapter.player_difficulties[pid] = player_diff

            self.game.set_hearthstone_ai_handler(ai_adapter)
        else:
            # MTG mode - prepare AI layers before the first priority decision
            await self._prepare_ai_layers()

        await self.game.start_game()

        # Record initial state
        self._record_frame(action=None)

    async def run_until_human_input(self) -> None:
        """Run the game until human input is needed or game ends."""
        try:
            while not self.is_finished:
                # Check for pending choices that AI needs to handle
                await self._process_ai_pending_choices()

                # Run one priority cycle
                await self.game.turn_manager.run_turn()

                # Check for AI choices again after the turn
                await self._process_ai_pending_choices()

                # Check if game is over
                if self.game.is_game_over():
                    self.is_finished = True
                    self.winner_id = self.game.get_winner()
                    break

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

            # Check if the choice is for an AI player
            if pending_choice.player not in self.human_players:
                # It's an AI player - make the choice
                self._handle_ai_choice(
                    pending_choice.player,
                    pending_choice,
                    self.game.state
                )
                # Small delay to prevent tight loops
                await asyncio.sleep(0.01)
            else:
                # Human player needs to make choice - stop processing
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
                hero_power_id=player.hero_power_id
            )

        # Get battlefield
        battlefield = []
        for obj in self.game.get_battlefield():
            battlefield.append(self._serialize_permanent(obj))

        # Get stack
        stack = []
        for item in self.game.stack.get_items():
            stack.append(self._serialize_stack_item(item))

        # Get hand (only for requesting player)
        hand = []
        if player_id:
            for obj in self.game.get_hand(player_id):
                hand.append(self._serialize_card(obj))

        # Get graveyards
        graveyards = {}
        for pid in game_state.players:
            graveyards[pid] = [
                self._serialize_card(obj)
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
                # This player needs to make the choice
                pending_choice_data = PendingChoiceData(
                    id=pending_choice.id,
                    choice_type=pending_choice.choice_type,
                    player=pending_choice.player,
                    prompt=pending_choice.prompt,
                    options=pending_choice.options,
                    source_id=pending_choice.source_id,
                    min_choices=pending_choice.min_choices,
                    max_choices=pending_choice.max_choices
                )
            else:
                # Another player is making a choice
                waiting_for_choice_data = PendingChoiceWaitingData(
                    waiting_for=pending_choice.player,
                    choice_type=pending_choice.choice_type
                )

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
            hand=hand,
            graveyard=graveyards,
            legal_actions=legal_actions,
            combat=combat,
            is_game_over=self.is_finished,
            winner=self.winner_id,
            pending_choice=pending_choice_data,
            waiting_for_choice=waiting_for_choice_data,
            game_mode=game_state.game_mode,
            max_hand_size=game_state.max_hand_size
        )

    async def handle_action(self, request: PlayerActionRequest) -> tuple[bool, str]:
        """
        Handle a player action request.

        Returns (success, message).
        """
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

    def _get_or_create_ai_engine(self, player_id: str) -> 'AIEngine':
        """Get or create the AI engine for a specific player."""
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

        from src.ai.llm import LLMConfig, OpenAIProvider, AnthropicProvider, OllamaProvider

        config = LLMConfig()

        if brain == "openai":
            provider = OpenAIProvider(
                api_key=config.openai_key,
                model=model or config.openai_model,
                timeout=config.timeout,
            )
        elif brain == "anthropic":
            provider = AnthropicProvider(
                api_key=config.anthropic_key,
                model=model or config.anthropic_model,
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
    ) -> bool:
        """
        Handler for mulligan decisions.

        Uses smart logic: keep hands with 2-5 lands for aggro, 2-4 for control.
        Returns True to keep, False to mulligan.
        """
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

    def _serialize_permanent(self, obj) -> CardData:
        """Serialize a permanent for the client."""
        from src.engine.queries import get_power, get_toughness, is_creature

        return CardData(
            id=obj.id,
            name=obj.name,
            domain=getattr(obj.card_def, "domain", None) if getattr(obj, "card_def", None) else "TOKEN",
            mana_cost=obj.characteristics.mana_cost,
            types=[t.name for t in obj.characteristics.types],
            subtypes=list(obj.characteristics.subtypes),
            power=get_power(obj, self.game.state) if is_creature(obj, self.game.state) else None,
            toughness=get_toughness(obj, self.game.state) if is_creature(obj, self.game.state) else None,
            text=obj.card_def.text if obj.card_def else "",
            tapped=obj.state.tapped,
            counters=dict(obj.state.counters),
            damage=obj.state.damage,
            controller=obj.controller,
            owner=obj.owner,
            divine_shield=obj.state.divine_shield,
            stealth=obj.state.stealth,
            windfury=obj.state.windfury,
            frozen=obj.state.frozen,
            summoning_sickness=obj.state.summoning_sickness,
            attacks_this_turn=obj.state.attacks_this_turn
        )

    def _serialize_card(self, obj) -> CardData:
        """Serialize a card for the client."""
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
            owner=obj.owner
        )

    def _serialize_stack_item(self, item) -> StackItemData:
        """Serialize a stack item for the client."""
        source = self.game.state.objects.get(item.source_id)
        return StackItemData(
            id=item.id,
            type=item.type.name,
            source_id=item.source_id,
            source_name=source.name if source else "Unknown",
            controller=item.controller_id
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
