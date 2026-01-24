# Hyperdraft Arena: Full-Stack Architecture Plan

## Executive Summary

This document outlines the architecture for transforming Hyperdraft into a full Arena-style MTG game with:
- **Human vs Bot** gameplay
- **Bot vs Bot** simulation/spectator mode
- **Web-based frontend** with card rendering and game visualization
- **Python backend** leveraging the existing event-driven engine

---

## Current State Assessment

### What Exists ✅
```
src/engine/
├── types.py      # Core types: Event, Interceptor, GameObject, GameState
├── pipeline.py   # Event processing with TRANSFORM/PREVENT/REACT phases
├── queries.py    # Continuous effects via QUERY interceptors
└── game.py       # Game manager, SBA checking, card builder helpers

src/cards/
├── lorwyn_eclipsed.py   # Example set (being populated by other agent)
├── avatar_tla.py        # Custom set
├── spider_man.py        # Custom set
└── edge_of_eternities.py # Custom set
```

### What's Missing ❌
1. **Turn/Phase Manager** - Full turn structure with proper phase transitions
2. **Priority System** - Player priority passing, response windows
3. **Stack Resolution** - LIFO stack with priority between each resolution
4. **Combat System** - Attack/block declaration, damage assignment
5. **Mana/Cost System** - Cost parsing, mana payment, mana abilities
6. **Targeting System** - Legal target validation, target selection
7. **AI/Bot Player** - Decision-making for bot gameplay
8. **Frontend** - Game visualization, interaction UI
9. **API Layer** - WebSocket/REST for client-server communication
10. **Game Session Management** - Match creation, game state persistence

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React/TypeScript)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Game Board  │  │  Hand View   │  │  Stack View  │  │  Phase/Turn  │    │
│  │  Component   │  │  Component   │  │  Component   │  │   Display    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Card Renderer│  │ Action Menu  │  │ Target Picker│  │ Combat UI    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
├─────────────────────────────────────────────────────────────────────────────┤
│                        WebSocket Connection (Socket.IO)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                              BACKEND (Python/FastAPI)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          API Layer                                    │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │    │
│  │  │  Game WS   │  │  Match API │  │  Deck API  │  │  Card API  │    │    │
│  │  │  Handler   │  │   (REST)   │  │   (REST)   │  │   (REST)   │    │    │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       Game Session Manager                            │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                     │    │
│  │  │  Session   │  │   Action   │  │   State    │                     │    │
│  │  │   Store    │  │ Dispatcher │  │ Serializer │                     │    │
│  │  └────────────┘  └────────────┘  └────────────┘                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Game Engine Core                              │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │    │
│  │  │   Turn    │ │  Priority │ │   Stack   │ │  Combat   │           │    │
│  │  │  Manager  │ │  System   │ │  Manager  │ │  Manager  │           │    │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘           │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │    │
│  │  │   Mana    │ │ Targeting │ │    AI     │ │   Event   │           │    │
│  │  │  System   │ │  System   │ │   Engine  │ │  Pipeline │ (exists)  │    │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Engine Completion

### 1.1 Turn Manager (`src/engine/turn.py`)

```python
# Turn structure with proper phase/step management

class Phase(Enum):
    BEGINNING = auto()
    PRECOMBAT_MAIN = auto()
    COMBAT = auto()
    POSTCOMBAT_MAIN = auto()
    ENDING = auto()

class Step(Enum):
    # Beginning
    UNTAP = auto()
    UPKEEP = auto()
    DRAW = auto()
    # Combat
    BEGINNING_OF_COMBAT = auto()
    DECLARE_ATTACKERS = auto()
    DECLARE_BLOCKERS = auto()
    COMBAT_DAMAGE = auto()  # May have first strike sub-step
    END_OF_COMBAT = auto()
    # Ending
    END = auto()
    CLEANUP = auto()

class TurnManager:
    """Manages turn structure and phase transitions."""

    def __init__(self, game: Game):
        self.game = game
        self.phase = Phase.BEGINNING
        self.step = Step.UNTAP
        self.turn_number = 0
        self.active_player_id: str = None
        self.extra_turns: list[str] = []  # Player IDs with extra turns

    async def run_turn(self, player_id: str):
        """Execute a complete turn for a player."""
        self.active_player_id = player_id
        self.turn_number += 1

        await self._emit_turn_start()

        # Beginning Phase
        await self._run_beginning_phase()

        # Pre-combat Main Phase
        await self._run_main_phase()

        # Combat Phase (optional - player may skip)
        if await self._player_wants_combat():
            await self._run_combat_phase()

        # Post-combat Main Phase
        await self._run_main_phase()

        # Ending Phase
        await self._run_ending_phase()

        await self._emit_turn_end()

    async def _run_beginning_phase(self):
        """Untap, Upkeep, Draw."""
        self.phase = Phase.BEGINNING

        # Untap Step (no priority)
        self.step = Step.UNTAP
        await self._untap_permanents()

        # Upkeep Step
        self.step = Step.UPKEEP
        await self._emit_step_triggers()
        await self.game.priority_system.run_priority_loop()

        # Draw Step
        self.step = Step.DRAW
        await self._draw_card()
        await self._emit_step_triggers()
        await self.game.priority_system.run_priority_loop()
```

### 1.2 Priority System (`src/engine/priority.py`)

```python
class PrioritySystem:
    """Handles priority passing and action windows."""

    def __init__(self, game: Game):
        self.game = game
        self.priority_player: str = None
        self.passed_players: set[str] = set()

    async def run_priority_loop(self):
        """
        Main priority loop:
        1. Active player gets priority
        2. Players can act or pass
        3. When all pass with empty stack, proceed
        4. When all pass with stack items, resolve top
        """
        self.passed_players.clear()
        self.priority_player = self.game.turn_manager.active_player_id

        while True:
            # Check SBAs before granting priority
            await self._check_state_based_actions()
            await self._put_triggers_on_stack()

            # Get player action
            action = await self._get_player_action(self.priority_player)

            if action.type == ActionType.PASS:
                self.passed_players.add(self.priority_player)

                if self._all_players_passed():
                    if self.game.stack.is_empty():
                        return  # Phase/step ends
                    else:
                        await self._resolve_top_of_stack()
                        self.passed_players.clear()
                        self.priority_player = self.game.turn_manager.active_player_id
                        continue
            else:
                # Player took an action
                self.passed_players.clear()
                await self._execute_action(action)
                # Player retains priority after acting (rule 116.3c)
                continue

            self.priority_player = self._next_player()

    async def _get_player_action(self, player_id: str) -> PlayerAction:
        """Get action from human or AI player."""
        player = self.game.get_player(player_id)

        if player.is_ai:
            return await self.game.ai_engine.get_action(player_id, self.game.state)
        else:
            # Wait for human input via WebSocket
            return await self.game.session.wait_for_player_action(player_id)
```

### 1.3 Stack Manager (`src/engine/stack.py`)

```python
@dataclass
class StackItem:
    """An item on the stack (spell or ability)."""
    id: str
    type: Literal['spell', 'ability']
    source_id: str           # Card/permanent that created this
    controller_id: str
    targets: list[Target]
    resolve_fn: Callable     # What happens on resolution
    timestamp: int

class StackManager:
    """LIFO stack for spells and abilities."""

    def __init__(self, game: Game):
        self.game = game
        self.items: list[StackItem] = []

    def push(self, item: StackItem):
        """Add item to top of stack."""
        item.timestamp = self.game.state.next_timestamp()
        self.items.append(item)

        # Emit stack event for frontend
        self.game.emit_ui_event('stack_push', {
            'item_id': item.id,
            'source': item.source_id,
            'controller': item.controller_id
        })

    async def resolve_top(self):
        """Resolve the top item of the stack."""
        if not self.items:
            return

        item = self.items.pop()

        # Check if all targets are still legal
        legal_targets = [t for t in item.targets if self._is_target_legal(t, item)]

        if item.targets and not legal_targets:
            # All targets illegal - spell/ability is countered
            if item.type == 'spell':
                await self._move_to_graveyard(item.source_id)
            return

        # Resolve with legal targets
        await item.resolve_fn(legal_targets, self.game.state)

        # If spell, move card to appropriate zone
        if item.type == 'spell':
            card = self.game.state.objects[item.source_id]
            if CardType.CREATURE in card.characteristics.types or \
               CardType.ARTIFACT in card.characteristics.types or \
               CardType.ENCHANTMENT in card.characteristics.types or \
               CardType.PLANESWALKER in card.characteristics.types:
                await self._enter_battlefield(item.source_id)
            else:
                await self._move_to_graveyard(item.source_id)
```

### 1.4 Combat Manager (`src/engine/combat.py`)

```python
@dataclass
class AttackDeclaration:
    attacker_id: str
    defending_player_id: str  # Or planeswalker ID

@dataclass
class BlockDeclaration:
    blocker_id: str
    blocking_attacker_id: str

class CombatManager:
    """Handles combat phase mechanics."""

    def __init__(self, game: Game):
        self.game = game
        self.attackers: list[AttackDeclaration] = []
        self.blockers: list[BlockDeclaration] = []
        self.damage_assignments: dict[str, list[tuple[str, int]]] = {}

    async def run_combat_phase(self):
        """Execute full combat phase."""
        # Beginning of Combat
        await self.game.turn_manager.set_step(Step.BEGINNING_OF_COMBAT)
        await self.game.priority_system.run_priority_loop()

        # Declare Attackers
        await self.game.turn_manager.set_step(Step.DECLARE_ATTACKERS)
        self.attackers = await self._get_attack_declarations()

        if not self.attackers:
            # No attackers - skip rest of combat
            return

        await self._tap_attackers()
        await self._emit_attack_triggers()
        await self.game.priority_system.run_priority_loop()

        # Declare Blockers
        await self.game.turn_manager.set_step(Step.DECLARE_BLOCKERS)
        self.blockers = await self._get_block_declarations()
        await self._emit_block_triggers()
        await self.game.priority_system.run_priority_loop()

        # Combat Damage
        await self._run_combat_damage()

        # End of Combat
        await self.game.turn_manager.set_step(Step.END_OF_COMBAT)
        await self._clear_combat_state()
        await self.game.priority_system.run_priority_loop()

    async def _run_combat_damage(self):
        """Handle combat damage step (with first strike split if needed)."""
        first_strikers = self._get_first_strikers()
        regular = self._get_regular_combatants()

        # First strike damage (if any)
        if first_strikers:
            await self.game.turn_manager.set_step(Step.COMBAT_DAMAGE)
            await self._assign_and_deal_damage(first_strikers)
            await self.game.priority_system.run_priority_loop()

        # Regular damage
        if regular:
            await self.game.turn_manager.set_step(Step.COMBAT_DAMAGE)
            await self._assign_and_deal_damage(regular)
            await self.game.priority_system.run_priority_loop()
```

### 1.5 Mana System (`src/engine/mana.py`)

```python
@dataclass
class ManaCost:
    """Parsed mana cost."""
    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0
    colorless: int = 0  # Specifically colorless (C)
    generic: int = 0     # Can be paid with any color

    # Special costs
    phyrexian: dict[Color, int] = field(default_factory=dict)  # Can pay 2 life
    hybrid: list[tuple[Color, Color]] = field(default_factory=list)
    snow: int = 0
    x: int = 0  # Variable cost

    @classmethod
    def parse(cls, cost_string: str) -> 'ManaCost':
        """Parse cost string like '{2}{W}{W}' or '{X}{R}{R}'."""
        cost = cls()
        # ... parsing logic
        return cost

class ManaPool:
    """Player's mana pool with restrictions."""

    def __init__(self):
        self.mana: dict[Color, list[ManaUnit]] = {c: [] for c in Color}

    def add(self, color: Color, amount: int = 1, restrictions: list[str] = None):
        """Add mana to pool."""
        for _ in range(amount):
            self.mana[color].append(ManaUnit(color, restrictions or []))

    def can_pay(self, cost: ManaCost) -> bool:
        """Check if pool can pay a cost."""
        # Create copy of pool for simulation
        sim_pool = self._copy_pool()
        return self._try_pay(cost, sim_pool)

    def pay(self, cost: ManaCost) -> bool:
        """Actually pay a cost (removes mana from pool)."""
        if not self.can_pay(cost):
            return False
        return self._try_pay(cost, self.mana, actually_pay=True)

    def empty(self):
        """Empty the mana pool (happens at end of each step/phase)."""
        for color in self.mana:
            self.mana[color].clear()

class ManaSystem:
    """Handles mana abilities and cost payment."""

    def is_mana_ability(self, ability) -> bool:
        """Check if an ability is a mana ability (doesn't use stack)."""
        return (
            not ability.has_targets() and
            ability.could_produce_mana() and
            not ability.is_loyalty_ability()
        )

    async def activate_mana_ability(self, ability_id: str, player_id: str):
        """Activate a mana ability (immediate, no stack)."""
        # Mana abilities resolve immediately
        ability = self.get_ability(ability_id)
        await ability.resolve()
```

### 1.6 Targeting System (`src/engine/targeting.py`)

```python
@dataclass
class TargetRequirement:
    """Specification for what can be targeted."""
    filter: TargetFilter
    zones: list[ZoneType] = field(default_factory=lambda: [ZoneType.BATTLEFIELD])
    count: int = 1
    count_type: Literal['exactly', 'up_to', 'any_number'] = 'exactly'

@dataclass
class TargetFilter:
    """Filter for legal targets."""
    types: set[CardType] = None
    subtypes: set[str] = None
    controller: Literal['you', 'opponent', 'any'] = 'any'
    characteristics: dict = None  # Custom filters

    def matches(self, obj: GameObject, state: GameState, source_controller: str) -> bool:
        """Check if object matches filter."""
        # ... matching logic

class TargetingSystem:
    """Handles target selection and validation."""

    def get_legal_targets(
        self,
        requirement: TargetRequirement,
        source: GameObject,
        state: GameState
    ) -> list[str]:
        """Get all legal target IDs for a requirement."""
        targets = []

        for zone_type in requirement.zones:
            for obj_id in self._get_zone_objects(zone_type, state):
                obj = state.objects[obj_id]

                if not requirement.filter.matches(obj, state, source.controller):
                    continue

                # Check hexproof
                if self._has_hexproof(obj, state) and obj.controller != source.controller:
                    continue

                # Check shroud
                if self._has_shroud(obj, state):
                    continue

                # Check protection
                if self._has_protection_from(obj, source, state):
                    continue

                targets.append(obj_id)

        return targets

    def is_still_legal(
        self,
        target_id: str,
        requirement: TargetRequirement,
        source: GameObject,
        state: GameState
    ) -> bool:
        """Check if a previously selected target is still legal."""
        return target_id in self.get_legal_targets(requirement, source, state)
```

---

## Phase 2: AI Engine

### 2.1 AI Architecture (`src/ai/`)

```
src/ai/
├── __init__.py
├── engine.py         # Main AI decision engine
├── evaluator.py      # Board state evaluation
├── strategies/
│   ├── __init__.py
│   ├── base.py       # Strategy interface
│   ├── aggro.py      # Aggressive playstyle
│   ├── control.py    # Controlling playstyle
│   ├── midrange.py   # Balanced playstyle
│   └── combo.py      # Combo-seeking
├── mcts.py           # Monte Carlo Tree Search for complex decisions
└── heuristics.py     # Quick decision heuristics
```

### 2.2 AI Engine (`src/ai/engine.py`)

```python
class AIEngine:
    """Main AI decision-making engine."""

    def __init__(self, strategy: AIStrategy = None):
        self.strategy = strategy or MidrangeStrategy()
        self.evaluator = BoardEvaluator()
        self.mcts = MCTSEngine()

    async def get_action(
        self,
        player_id: str,
        state: GameState
    ) -> PlayerAction:
        """Decide what action to take."""
        legal_actions = self._get_legal_actions(player_id, state)

        if not legal_actions:
            return PlayerAction(type=ActionType.PASS)

        # Use strategy to evaluate actions
        scored_actions = []
        for action in legal_actions:
            score = self.strategy.evaluate_action(action, state, self.evaluator)
            scored_actions.append((action, score))

        # Sort by score and pick best
        scored_actions.sort(key=lambda x: x[1], reverse=True)
        best_action, best_score = scored_actions[0]

        # If close call, use MCTS for deeper analysis
        if len(scored_actions) > 1:
            second_score = scored_actions[1][1]
            if abs(best_score - second_score) < 0.1:
                best_action = await self.mcts.analyze(
                    state, [a for a, _ in scored_actions[:5]]
                )

        return best_action

    async def get_mulligan_decision(
        self,
        hand: list[GameObject],
        mulligan_count: int
    ) -> Literal['keep', 'mulligan']:
        """Decide whether to mulligan."""
        score = self._evaluate_hand(hand)
        threshold = 0.6 - (mulligan_count * 0.1)  # Lower threshold for more mulligans
        return 'keep' if score >= threshold else 'mulligan'

    async def get_attack_declarations(
        self,
        state: GameState,
        player_id: str
    ) -> list[AttackDeclaration]:
        """Decide which creatures to attack with."""
        return self.strategy.plan_attacks(state, player_id, self.evaluator)

    async def get_block_declarations(
        self,
        state: GameState,
        player_id: str,
        attackers: list[AttackDeclaration]
    ) -> list[BlockDeclaration]:
        """Decide how to block."""
        return self.strategy.plan_blocks(state, player_id, attackers, self.evaluator)

    async def choose_targets(
        self,
        ability,
        legal_targets: list[str],
        state: GameState
    ) -> list[str]:
        """Choose targets for a spell/ability."""
        return self.strategy.choose_targets(ability, legal_targets, state, self.evaluator)

class BoardEvaluator:
    """Evaluates game state for AI decision making."""

    def evaluate(self, state: GameState, player_id: str) -> float:
        """
        Evaluate board state from player's perspective.
        Returns value from -1.0 (losing) to 1.0 (winning).
        """
        score = 0.0

        # Life totals
        my_life = state.players[player_id].life
        opp_life = self._get_opponent_life(state, player_id)
        score += (my_life - opp_life) * 0.02

        # Board presence
        my_power = self._total_power(state, player_id)
        opp_power = self._total_power(state, self._get_opponent_id(state, player_id))
        score += (my_power - opp_power) * 0.05

        # Card advantage
        my_cards = self._count_cards(state, player_id)
        opp_cards = self._count_cards(state, self._get_opponent_id(state, player_id))
        score += (my_cards - opp_cards) * 0.08

        # Mana advantage
        my_mana = self._count_mana_sources(state, player_id)
        opp_mana = self._count_mana_sources(state, self._get_opponent_id(state, player_id))
        score += (my_mana - opp_mana) * 0.03

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, score))
```

### 2.3 MCTS for Complex Decisions (`src/ai/mcts.py`)

```python
class MCTSEngine:
    """Monte Carlo Tree Search for deep decision analysis."""

    def __init__(self, simulations: int = 1000, max_depth: int = 10):
        self.simulations = simulations
        self.max_depth = max_depth

    async def analyze(
        self,
        state: GameState,
        candidate_actions: list[PlayerAction]
    ) -> PlayerAction:
        """Use MCTS to find best action among candidates."""
        root = MCTSNode(state, None)

        for _ in range(self.simulations):
            # Selection
            node = self._select(root)

            # Expansion
            if not node.is_terminal:
                node = self._expand(node, candidate_actions)

            # Simulation
            reward = await self._simulate(node)

            # Backpropagation
            self._backpropagate(node, reward)

        # Return best action
        best_child = max(root.children, key=lambda c: c.visits)
        return best_child.action

    async def _simulate(self, node: MCTSNode) -> float:
        """Simulate game from node using random/heuristic play."""
        sim_state = node.state.copy()
        depth = 0

        while depth < self.max_depth and not self._is_game_over(sim_state):
            # Use fast heuristics for simulation
            action = self._quick_heuristic_action(sim_state)
            sim_state = self._apply_action(sim_state, action)
            depth += 1

        return self._evaluate_terminal(sim_state, node.player_id)
```

---

## Phase 3: API Layer

### 3.1 FastAPI Server (`src/server/main.py`)

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import socketio

app = FastAPI(title="Hyperdraft Arena API")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO for real-time game communication
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio, app)

# REST endpoints
@app.post("/api/match/create")
async def create_match(config: MatchConfig):
    """Create a new match."""
    session = GameSession.create(config)
    return {"match_id": session.id}

@app.get("/api/match/{match_id}/state")
async def get_match_state(match_id: str):
    """Get current game state."""
    session = SessionManager.get(match_id)
    return session.get_client_state()

@app.get("/api/cards")
async def list_cards(set_code: str = None):
    """List available cards."""
    return CardDatabase.list_cards(set_code=set_code)

@app.get("/api/cards/{card_id}")
async def get_card(card_id: str):
    """Get card details."""
    return CardDatabase.get_card(card_id)

# WebSocket for game events
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def join_match(sid, data):
    """Join a match room."""
    match_id = data['match_id']
    player_id = data['player_id']

    session = SessionManager.get(match_id)
    session.connect_player(player_id, sid)

    await sio.enter_room(sid, match_id)
    await sio.emit('game_state', session.get_client_state(), room=sid)

@sio.event
async def player_action(sid, data):
    """Handle player action."""
    match_id = data['match_id']
    action = PlayerAction.from_dict(data['action'])

    session = SessionManager.get(match_id)
    result = await session.handle_action(action)

    # Broadcast state update to all players
    await sio.emit('game_update', result, room=match_id)

@sio.event
async def spectate(sid, data):
    """Join as spectator."""
    match_id = data['match_id']
    await sio.enter_room(sid, match_id)
```

### 3.2 Game Session (`src/server/session.py`)

```python
@dataclass
class MatchConfig:
    mode: Literal['human_vs_bot', 'bot_vs_bot', 'human_vs_human']
    player1_deck: list[str]  # Card IDs
    player2_deck: list[str]
    ai_difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    spectator_mode: bool = False

class GameSession:
    """Manages a single game session."""

    def __init__(self, config: MatchConfig):
        self.id = new_id()
        self.config = config
        self.game = Game()
        self.player_sockets: dict[str, str] = {}  # player_id -> socket_id
        self.action_queue: asyncio.Queue = asyncio.Queue()
        self.state_history: list[dict] = []

    @classmethod
    def create(cls, config: MatchConfig) -> 'GameSession':
        """Create and initialize a new game session."""
        session = cls(config)
        session._setup_game()
        return session

    def _setup_game(self):
        """Initialize game with players and decks."""
        # Add players
        p1 = self.game.add_player("Player 1")
        p2 = self.game.add_player("Player 2" if self.config.mode == 'human_vs_human' else "Bot")

        # Mark AI player
        if self.config.mode in ['human_vs_bot', 'bot_vs_bot']:
            p2.is_ai = True
            if self.config.mode == 'bot_vs_bot':
                p1.is_ai = True

        # Load decks
        self._load_deck(p1.id, self.config.player1_deck)
        self._load_deck(p2.id, self.config.player2_deck)

        # Shuffle and draw starting hands
        self._shuffle_libraries()
        self._draw_starting_hands()

    def get_client_state(self, player_id: str = None) -> dict:
        """
        Get game state for client.
        Hides hidden information appropriately.
        """
        return {
            'turn': self.game.turn_manager.turn_number,
            'phase': self.game.turn_manager.phase.name,
            'step': self.game.turn_manager.step.name,
            'active_player': self.game.turn_manager.active_player_id,
            'priority_player': self.game.priority_system.priority_player,
            'players': self._serialize_players(player_id),
            'battlefield': self._serialize_battlefield(),
            'stack': self._serialize_stack(),
            'hand': self._serialize_hand(player_id) if player_id else None,
            'graveyard': self._serialize_graveyards(),
            'legal_actions': self._get_legal_actions(player_id) if player_id else [],
        }

    async def handle_action(self, action: PlayerAction) -> dict:
        """Process a player action and return state update."""
        # Validate action
        if not self._is_action_legal(action):
            return {'error': 'Illegal action'}

        # Execute action
        events = await self.game.execute_action(action)

        # Save state for replay
        self.state_history.append(self.get_client_state())

        # Return events and new state
        return {
            'events': [e.to_dict() for e in events],
            'state': self.get_client_state()
        }

    async def run_bot_vs_bot(self):
        """Run an automated bot vs bot game."""
        while not self.game.is_over():
            # Get current player
            current_player = self.game.priority_system.priority_player

            # AI makes decision
            action = await self.game.ai_engine.get_action(
                current_player,
                self.game.state
            )

            # Execute action
            result = await self.handle_action(action)

            # Emit state to spectators
            await self._emit_to_spectators('game_update', result)

            # Small delay for spectator viewing
            await asyncio.sleep(0.5)

class SessionManager:
    """Manages all active game sessions."""
    _sessions: dict[str, GameSession] = {}

    @classmethod
    def create(cls, config: MatchConfig) -> GameSession:
        session = GameSession.create(config)
        cls._sessions[session.id] = session
        return session

    @classmethod
    def get(cls, session_id: str) -> GameSession:
        return cls._sessions.get(session_id)
```

---

## Phase 4: Frontend (React/TypeScript)

### 4.1 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── game/
│   │   │   ├── GameBoard.tsx        # Main game board layout
│   │   │   ├── Battlefield.tsx      # Battlefield zones
│   │   │   ├── HandView.tsx         # Player's hand
│   │   │   ├── StackView.tsx        # The stack visualization
│   │   │   ├── PhaseIndicator.tsx   # Turn/phase/step display
│   │   │   ├── PlayerInfo.tsx       # Life, mana, etc.
│   │   │   └── GraveyardView.tsx    # Graveyard browser
│   │   ├── cards/
│   │   │   ├── Card.tsx             # Card component
│   │   │   ├── CardFrame.tsx        # Card frame rendering
│   │   │   ├── CardArt.tsx          # Art display
│   │   │   └── CardTooltip.tsx      # Hover tooltip
│   │   ├── actions/
│   │   │   ├── ActionMenu.tsx       # Available actions
│   │   │   ├── TargetPicker.tsx     # Target selection UI
│   │   │   ├── ManaPayment.tsx      # Mana payment modal
│   │   │   └── CombatUI.tsx         # Attack/block UI
│   │   └── ui/
│   │       ├── Button.tsx
│   │       ├── Modal.tsx
│   │       └── Tooltip.tsx
│   ├── hooks/
│   │   ├── useGame.ts               # Main game state hook
│   │   ├── useSocket.ts             # WebSocket connection
│   │   ├── useAnimation.ts          # Card animations
│   │   └── useTargeting.ts          # Target selection state
│   ├── stores/
│   │   └── gameStore.ts             # Zustand game state
│   ├── types/
│   │   ├── game.ts                  # Game types
│   │   ├── cards.ts                 # Card types
│   │   └── actions.ts               # Action types
│   ├── services/
│   │   ├── api.ts                   # REST API client
│   │   └── socket.ts                # Socket.IO client
│   └── utils/
│       ├── cardRenderer.ts          # Card image generation
│       └── animations.ts            # Animation helpers
├── public/
│   └── assets/
│       ├── frames/                  # Card frame images
│       ├── icons/                   # Mana symbols, etc.
│       └── sounds/                  # Game sounds
└── package.json
```

### 4.2 Main Game Component

```tsx
// src/components/game/GameBoard.tsx
import { useGame } from '@/hooks/useGame';
import { Battlefield } from './Battlefield';
import { HandView } from './HandView';
import { StackView } from './StackView';
import { PhaseIndicator } from './PhaseIndicator';
import { PlayerInfo } from './PlayerInfo';
import { ActionMenu } from '../actions/ActionMenu';
import { TargetPicker } from '../actions/TargetPicker';

export function GameBoard() {
  const {
    state,
    myPlayerId,
    legalActions,
    selectedTargets,
    isTargeting,
    phase,
    step,
    activePlayer,
    priorityPlayer,
    sendAction,
    selectTarget,
    cancelTargeting,
  } = useGame();

  const hasPriority = priorityPlayer === myPlayerId;

  return (
    <div className="game-board">
      {/* Opponent Area */}
      <div className="opponent-area">
        <PlayerInfo player={state.players.opponent} />
        <Battlefield
          permanents={state.battlefield.opponent}
          isOpponent
        />
      </div>

      {/* Center Area */}
      <div className="center-area">
        <PhaseIndicator
          phase={phase}
          step={step}
          activePlayer={activePlayer}
        />
        <StackView items={state.stack} />
      </div>

      {/* Player Area */}
      <div className="player-area">
        <Battlefield
          permanents={state.battlefield.mine}
          onPermanentClick={(id) => isTargeting && selectTarget(id)}
        />
        <HandView
          cards={state.hand}
          playable={hasPriority ? legalActions.playableCards : []}
          onCardClick={(card) => hasPriority && sendAction({ type: 'play', cardId: card.id })}
        />
        <PlayerInfo player={state.players.me} />
      </div>

      {/* Action UI */}
      {hasPriority && (
        <ActionMenu
          actions={legalActions}
          onAction={sendAction}
        />
      )}

      {/* Target Selection Overlay */}
      {isTargeting && (
        <TargetPicker
          requirement={state.targetingRequirement}
          selected={selectedTargets}
          onSelect={selectTarget}
          onConfirm={() => sendAction({ type: 'targets', targets: selectedTargets })}
          onCancel={cancelTargeting}
        />
      )}
    </div>
  );
}
```

### 4.3 Card Component

```tsx
// src/components/cards/Card.tsx
import { useState } from 'react';
import { motion } from 'framer-motion';
import { CardData } from '@/types/cards';
import { CardTooltip } from './CardTooltip';

interface CardProps {
  card: CardData;
  size?: 'small' | 'medium' | 'large';
  tapped?: boolean;
  highlighted?: boolean;
  onClick?: () => void;
  draggable?: boolean;
}

export function Card({
  card,
  size = 'medium',
  tapped = false,
  highlighted = false,
  onClick,
  draggable = false,
}: CardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const sizeClasses = {
    small: 'w-16 h-22',
    medium: 'w-24 h-34',
    large: 'w-48 h-68',
  };

  return (
    <motion.div
      className={`
        card
        ${sizeClasses[size]}
        ${tapped ? 'rotate-90' : ''}
        ${highlighted ? 'ring-2 ring-yellow-400' : ''}
        cursor-pointer
        relative
      `}
      whileHover={{ scale: 1.05, y: -10 }}
      onClick={onClick}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      draggable={draggable}
      layout
    >
      {/* Card Frame */}
      <div className="card-frame absolute inset-0 rounded-lg overflow-hidden">
        <img
          src={getFrameImage(card.colors)}
          alt=""
          className="w-full h-full"
        />
      </div>

      {/* Card Art */}
      <div className="card-art absolute top-[10%] left-[8%] right-[8%] h-[35%]">
        <img
          src={card.artUrl || '/assets/placeholder-art.png'}
          alt={card.name}
          className="w-full h-full object-cover rounded"
        />
      </div>

      {/* Card Name */}
      <div className="card-name absolute top-[2%] left-[5%] right-[15%] text-xs font-bold">
        {card.name}
      </div>

      {/* Mana Cost */}
      <div className="mana-cost absolute top-[2%] right-[5%] flex gap-0.5">
        {renderManaCost(card.manaCost)}
      </div>

      {/* Type Line */}
      <div className="type-line absolute top-[47%] left-[5%] right-[5%] text-xs">
        {card.typeLine}
      </div>

      {/* Rules Text */}
      <div className="rules-text absolute top-[52%] left-[5%] right-[5%] bottom-[18%] text-xs overflow-hidden">
        {card.text}
      </div>

      {/* P/T Box (if creature) */}
      {card.power !== undefined && (
        <div className="pt-box absolute bottom-[3%] right-[5%] bg-black text-white px-2 py-1 rounded text-sm font-bold">
          {card.power}/{card.toughness}
        </div>
      )}

      {/* Counters */}
      {card.counters && Object.entries(card.counters).map(([type, count]) => (
        <div key={type} className="counter absolute bottom-[15%] left-[5%]">
          <span className="bg-green-500 text-white rounded-full px-2 py-1 text-xs">
            {count > 0 ? '+' : ''}{count}
          </span>
        </div>
      ))}

      {/* Tooltip */}
      {showTooltip && <CardTooltip card={card} />}
    </motion.div>
  );
}
```

### 4.4 WebSocket Hook

```tsx
// src/hooks/useGame.ts
import { useEffect, useCallback } from 'react';
import { create } from 'zustand';
import { io, Socket } from 'socket.io-client';
import { GameState, PlayerAction, LegalActions } from '@/types/game';

interface GameStore {
  socket: Socket | null;
  matchId: string | null;
  playerId: string | null;
  state: GameState | null;
  legalActions: LegalActions | null;
  isTargeting: boolean;
  selectedTargets: string[];

  connect: (matchId: string, playerId: string) => void;
  disconnect: () => void;
  sendAction: (action: PlayerAction) => void;
  selectTarget: (targetId: string) => void;
  clearTargets: () => void;
}

export const useGameStore = create<GameStore>((set, get) => ({
  socket: null,
  matchId: null,
  playerId: null,
  state: null,
  legalActions: null,
  isTargeting: false,
  selectedTargets: [],

  connect: (matchId, playerId) => {
    const socket = io('http://localhost:8000');

    socket.on('connect', () => {
      socket.emit('join_match', { match_id: matchId, player_id: playerId });
    });

    socket.on('game_state', (state: GameState) => {
      set({ state, legalActions: state.legal_actions });
    });

    socket.on('game_update', (update) => {
      set({
        state: update.state,
        legalActions: update.state.legal_actions,
      });
    });

    socket.on('targeting_required', (requirement) => {
      set({ isTargeting: true });
    });

    set({ socket, matchId, playerId });
  },

  disconnect: () => {
    const { socket } = get();
    socket?.disconnect();
    set({ socket: null, matchId: null, playerId: null, state: null });
  },

  sendAction: (action) => {
    const { socket, matchId } = get();
    socket?.emit('player_action', { match_id: matchId, action });
    set({ isTargeting: false, selectedTargets: [] });
  },

  selectTarget: (targetId) => {
    const { selectedTargets } = get();
    if (selectedTargets.includes(targetId)) {
      set({ selectedTargets: selectedTargets.filter(id => id !== targetId) });
    } else {
      set({ selectedTargets: [...selectedTargets, targetId] });
    }
  },

  clearTargets: () => set({ selectedTargets: [], isTargeting: false }),
}));

// Hook wrapper for components
export function useGame() {
  const store = useGameStore();

  const hasPriority = store.state?.priority_player === store.playerId;

  return {
    ...store,
    hasPriority,
    phase: store.state?.phase,
    step: store.state?.step,
    activePlayer: store.state?.active_player,
    priorityPlayer: store.state?.priority_player,
  };
}
```

---

## Phase 5: Bot vs Bot Spectator Mode

### 5.1 Spectator Page

```tsx
// src/pages/SpectatorView.tsx
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { GameBoard } from '@/components/game/GameBoard';
import { EventLog } from '@/components/game/EventLog';
import { useSpectator } from '@/hooks/useSpectator';

export function SpectatorView() {
  const { matchId } = useParams();
  const {
    state,
    events,
    isLive,
    playbackSpeed,
    setPlaybackSpeed,
    pause,
    resume,
  } = useSpectator(matchId);

  if (!state) return <div>Loading...</div>;

  return (
    <div className="spectator-view">
      {/* Game Board (read-only) */}
      <GameBoard
        state={state}
        spectatorMode
      />

      {/* Event Log */}
      <div className="event-log-panel">
        <EventLog events={events} />
      </div>

      {/* Playback Controls */}
      <div className="playback-controls">
        <button onClick={pause}>⏸</button>
        <button onClick={resume}>▶</button>
        <select
          value={playbackSpeed}
          onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
        >
          <option value={0.5}>0.5x</option>
          <option value={1}>1x</option>
          <option value={2}>2x</option>
          <option value={4}>4x</option>
        </select>
      </div>
    </div>
  );
}
```

### 5.2 Bot vs Bot API

```python
# src/server/routes/bot_game.py
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

router = APIRouter(prefix="/api/bot-game")

class BotGameConfig(BaseModel):
    deck1: list[str]
    deck2: list[str]
    ai1_difficulty: str = "medium"
    ai2_difficulty: str = "hard"
    delay_ms: int = 500  # Delay between moves for spectating

@router.post("/start")
async def start_bot_game(config: BotGameConfig, background_tasks: BackgroundTasks):
    """Start a new bot vs bot game."""
    session = SessionManager.create(MatchConfig(
        mode='bot_vs_bot',
        player1_deck=config.deck1,
        player2_deck=config.deck2,
    ))

    # Run game in background
    background_tasks.add_task(session.run_bot_vs_bot)

    return {
        "match_id": session.id,
        "spectate_url": f"/spectate/{session.id}"
    }

@router.get("/{match_id}/replay")
async def get_replay(match_id: str):
    """Get full game replay data."""
    session = SessionManager.get(match_id)
    return {
        "states": session.state_history,
        "events": [e.to_dict() for e in session.game.state.event_log]
    }
```

---

## Implementation Phases

### Phase 1: Core Engine (2-3 weeks)
1. Turn Manager with full phase/step structure
2. Priority System with response windows
3. Stack Manager with LIFO resolution
4. Combat Manager with attack/block flow
5. Mana System with cost parsing and payment
6. Targeting System with legal target computation

### Phase 2: AI Engine (2-3 weeks)
1. Board evaluator for state assessment
2. Basic strategy implementations (aggro, control, midrange)
3. Mulligan decision logic
4. Combat decision logic (attack/block)
5. Target selection heuristics
6. MCTS for complex decisions (optional)

### Phase 3: API Layer (1-2 weeks)
1. FastAPI server setup
2. Socket.IO integration for real-time updates
3. Game session management
4. State serialization with hidden info handling
5. Action validation and execution

### Phase 4: Frontend (3-4 weeks)
1. React project setup with TypeScript
2. Card component with frame rendering
3. Game board layout
4. Hand/battlefield/stack visualization
5. Action menu and targeting UI
6. Combat UI (attack/block declarations)
7. Animations (card movement, damage, etc.)
8. Sound effects

### Phase 5: Bot vs Bot Mode (1 week)
1. Automated game loop
2. Spectator WebSocket connection
3. Playback controls
4. Game replay system

---

## File Structure Summary

```
Hyperdraft/
├── src/
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── types.py         # (exists) Core types
│   │   ├── pipeline.py      # (exists) Event pipeline
│   │   ├── queries.py       # (exists) Query system
│   │   ├── game.py          # (exists) Game manager
│   │   ├── turn.py          # NEW: Turn/phase manager
│   │   ├── priority.py      # NEW: Priority system
│   │   ├── stack.py         # NEW: Stack manager
│   │   ├── combat.py        # NEW: Combat manager
│   │   ├── mana.py          # NEW: Mana system
│   │   └── targeting.py     # NEW: Targeting system
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── engine.py        # NEW: AI decision engine
│   │   ├── evaluator.py     # NEW: Board evaluation
│   │   ├── strategies/      # NEW: AI strategies
│   │   └── mcts.py          # NEW: MCTS engine
│   ├── server/
│   │   ├── __init__.py
│   │   ├── main.py          # NEW: FastAPI server
│   │   ├── session.py       # NEW: Game session manager
│   │   └── routes/          # NEW: API routes
│   └── cards/
│       └── ...              # (exists) Card definitions
├── frontend/
│   ├── src/
│   │   ├── components/      # NEW: React components
│   │   ├── hooks/           # NEW: React hooks
│   │   ├── stores/          # NEW: State management
│   │   └── services/        # NEW: API clients
│   └── package.json
├── tests/
│   └── ...                  # (exists) + NEW tests
└── docs/
    └── ...                  # (exists)
```

---

## Tech Stack Summary

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Backend** | Python 3.11+ | Existing engine, AI/ML ecosystem |
| **Web Framework** | FastAPI | Async, fast, great OpenAPI support |
| **WebSocket** | Socket.IO | Reliable real-time communication |
| **Frontend** | React 18 + TypeScript | Component model, type safety |
| **State Management** | Zustand | Simple, performant |
| **Animation** | Framer Motion | Declarative animations |
| **Styling** | Tailwind CSS | Rapid UI development |
| **Build** | Vite | Fast development builds |

---

## Next Steps

1. **Review this plan** - Confirm architecture decisions
2. **Set up frontend project** - React/TypeScript scaffolding
3. **Implement Turn Manager** - Complete turn structure
4. **Implement Priority System** - Response windows
5. **Build basic AI** - Simple decision-making
6. **Create API layer** - Connect frontend to backend
7. **Build game UI** - Card rendering, board layout
8. **Add bot vs bot mode** - Spectator functionality
