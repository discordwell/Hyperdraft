# Hearthstone AI Integration Status

## Current State

### ✓ Working - Core Hearthstone Mechanics
- [x] Mana crystals (auto-gain, refill each turn)
- [x] Hero setup (heroes, hero powers)
- [x] Combat damage to heroes (with armor absorption)
- [x] Minion death at 0 health
- [x] Divine Shield
- [x] Freeze mechanics
- [x] Taunt enforcement
- [x] Overdraw/card burn
- [x] Fatigue damage
- [x] Game end on player death
- [x] Weapon durability

### ✓ Working - AI Framework
- AIEngine with difficulty levels (easy/medium/hard/ultra)
- Strategy system (Aggro, Control, Midrange)
- Board evaluation
- Heuristics for card/play evaluation

### ⚠️  Problem - AI Integration

**The current AI is MTG-specific and won't work for Hearthstone without changes.**

#### Why It Won't Work:

1. **Priority System Dependency**
   - MTG AI works through priority rounds (pass/play loop)
   - Hearthstone is turn-based - active player acts until ending turn
   - No opponent responses during your turn

2. **Combat Model**
   - MTG: Declare attackers → Declare blockers → Damage
   - Hearthstone: Direct attacks with target selection
   - AI needs to choose: "Attack hero or this minion?"

3. **Action Selection**
   - MTG AI evaluates legal actions from priority system
   - Hearthstone needs different action model:
     - Play minions
     - Cast spells
     - Use hero power
     - Attack with minions
     - End turn

## What's Needed for Hearthstone AI

### Option 1: Adapt Existing AI (Recommended)

Create a Hearthstone-specific action selector that plugs into the existing AIEngine:

```python
class HearthstoneAIAdapter:
    """Adapts AIEngine for Hearthstone gameplay."""

    def __init__(self, ai_engine: AIEngine):
        self.ai_engine = ai_engine

    async def take_turn(self, player_id: str, state: GameState) -> list[Event]:
        """
        Execute a full Hearthstone turn for AI.

        1. Evaluate board state
        2. Play cards from hand (prioritize mana curve)
        3. Use hero power if beneficial
        4. Attack with minions (face vs trade decision)
        5. End turn
        """
        events = []

        # Play phase
        while self._should_play_card(state, player_id):
            card_to_play = self._choose_card_to_play(state, player_id)
            if card_to_play:
                events.extend(await self._play_card(card_to_play, state))
            else:
                break

        # Hero power phase
        if self._should_use_hero_power(state, player_id):
            events.extend(await self._use_hero_power(state, player_id))

        # Attack phase
        attackers = self._get_available_attackers(state, player_id)
        for attacker in attackers:
            target = self._choose_attack_target(attacker, state, player_id)
            if target:
                events.extend(await self._attack(attacker, target, state))

        return events

    def _choose_attack_target(self, attacker_id: str, state: GameState, player_id: str) -> str:
        """
        Choose attack target using strategy.

        Decision tree:
        1. Must attack Taunt if present
        2. Trade if:
           - Favorable trade (kill without dying)
           - Control/Midrange strategy
        3. Go face if:
           - Aggro strategy
           - No favorable trades
           - Can lethal
        """
        # Use existing BoardEvaluator and strategy system
        # ...
```

### Option 2: Use HearthstoneTurnManager Directly

The HearthstoneTurnManager already handles turn structure. We just need AI to make decisions at key points:

```python
# In HearthstoneTurnManager._run_main_phase()

async def _run_main_phase(self) -> list[Event]:
    """Main phase - player can take actions."""
    events = []

    active_player_id = self.hs_turn_state.active_player_id

    # If AI player, let AI take actions
    if self._is_ai_player(active_player_id):
        ai_actions = await self._get_ai_actions(active_player_id)
        events.extend(ai_actions)
    else:
        # Human player - wait for manual actions
        pass

    return events
```

## Recommended Implementation

### Step 1: Create HearthstoneAIAdapter

File: `src/ai/hearthstone_adapter.py`

- Reuses existing AIEngine, BoardEvaluator, Strategies
- Translates Hearthstone game state to evaluation format
- Makes Hearthstone-specific decisions

### Step 2: Integrate with HearthstoneTurnManager

Modify `hearthstone_turn.py`:
- Call AI adapter during main phase
- Pass control to AI for attack declarations
- AI signals "end turn" when done

### Step 3: Update Session Manager

Modify `session.py`:
- Set up HearthstoneAIAdapter for AI players in Hearthstone mode
- Keep existing AIEngine for MTG mode

## Testing Plan

1. **Easy AI** - Should play random valid actions
2. **Medium AI** - Should follow mana curve, make basic trades
3. **Hard AI** - Should optimize trades, plan ahead
4. **Ultra AI** - Should use LLM for complex decisions

## Current Blockers

### ❌ AI Integration Missing
The `/bot-game` endpoint sets up heroes and decks, but doesn't configure AI action handlers for Hearthstone mode.

**Fix needed in** `src/server/session.py`:

```python
async def start_game(self):
    """Start the game."""
    if not self.is_started:
        # ... existing setup ...

        # Setup AI handlers based on game mode
        if self.game.state.game_mode == "hearthstone":
            # Use Hearthstone AI adapter
            from src.ai.hearthstone_adapter import HearthstoneAIAdapter
            ai_adapter = HearthstoneAIAdapter(self.ai_engine)
            # Set as action handler
            self.game.set_hearthstone_ai_handler(ai_adapter)
        else:
            # Use existing MTG AI handlers
            self.game.set_ai_action_handler(self._get_ai_action)
```

## Summary

**Status**: Hearthstone mechanics work ✓, but AI can't play Hearthstone yet ❌

**What's needed**:
1. Create `HearthstoneAIAdapter` class (reuses existing AI logic)
2. Integrate adapter with `HearthstoneTurnManager`
3. Update session manager to use adapter for HS games

**Estimated effort**: 4-6 hours
- 2 hours: Build adapter
- 2 hours: Integrate with turn manager
- 1-2 hours: Test and tune

**Alternative**: For immediate testing, could add random action selector as placeholder AI.
