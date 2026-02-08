"""
Game Session Management

Manages active game sessions, player connections, and game state.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from uuid import uuid4
import time

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

    # AI engine (lazy initialized)
    _ai_engine: Optional[Any] = None
    ai_difficulty: str = "medium"

    def __post_init__(self):
        """Set up game callbacks."""
        self.game.set_human_action_handler(self._get_human_action)
        self.game.set_ai_action_handler(self._get_ai_action)
        self.game.set_attack_handler(self._get_attacks)
        self.game.set_block_handler(self._get_blocks)
        self.game.set_mulligan_handler(self._get_mulligan_decision)
        # Set up action processed callback for synchronization
        self.game.priority_system.on_action_processed = self._on_action_processed

    def _on_action_processed(self):
        """Called when an action is fully processed by the game loop."""
        if self._action_processed_event:
            self._action_processed_event.set()

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
        for card_def in card_defs:
            self.game.add_card_to_library(player_id, card_def)
        self.game.shuffle_library(player_id)

    async def start_game(self) -> None:
        """Start the game."""
        if self.is_started:
            return

        self.is_started = True
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
                library_size=self.game.get_library_size(pid)
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
            waiting_for_choice=waiting_for_choice_data
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

    def _get_ai_action(
        self,
        player_id: str,
        state: GameState,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Handler for AI player actions."""
        # First, check if there's a pending choice for the AI
        pending_choice = self.game.get_pending_choice()
        if pending_choice and pending_choice.player == player_id:
            # AI needs to make a choice, not take an action
            self._handle_ai_choice(player_id, pending_choice, state)
            # Return pass - the choice handling will advance the game
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        # Try to import AI engine (assume it exists)
        try:
            from src.ai import AIEngine
            ai = self._get_or_create_ai_engine()
            return ai.get_action(player_id, state, legal_actions)
        except ImportError:
            # AI not available - use simple fallback
            return self._simple_ai_action(player_id, legal_actions)

    def _get_or_create_ai_engine(self) -> 'AIEngine':
        """Get or create the AI engine for this session."""
        if self._ai_engine is None:
            from src.ai import AIEngine
            if self.ai_difficulty == "ultra":
                self._ai_engine = AIEngine.create_ultra_bot()
            else:
                self._ai_engine = AIEngine(difficulty=self.ai_difficulty)
        return self._ai_engine

    def _handle_ai_choice(
        self,
        player_id: str,
        pending_choice,
        state: GameState
    ) -> None:
        """Have the AI make a pending choice."""
        try:
            from src.ai import AIEngine
            ai = self._get_or_create_ai_engine()

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
            owner=obj.owner
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
        ai_difficulty: str = "medium"
    ) -> GameSession:
        """Create a new game session."""
        async with self._lock:
            session_id = generate_id()
            game = Game()

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
