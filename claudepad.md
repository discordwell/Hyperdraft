# Claudepad - Session Memory

## Session Summaries

### 2026-02-05T14:XX:XX UTC - Payload Key Bugs and Handler Flexibility

**Fixed 8 bugs:**

1. **ObjectState.get() Bug** (`lorwyn_custom.py:6784`)
   - Bug: `obj.state.get('exiled_card_id')` - ObjectState is a dataclass, not dict
   - Fix: Changed to `getattr(obj.state, 'exiled_card_id', None)`

2. **DRAW Event payload 'player_id'** (`temporal_horizons.py`)
   - Bug: 4 cards used `player_id` instead of `player`
   - Lines: 1451, 1457, 1463, 1608
   - Fix: Changed to `'player': obj.controller`

3. **DAMAGE Event payload keys** (`temporal_horizons.py:1514`)
   - Bug: Used `target_id` and `source_id` instead of `target` and `source`
   - Fix: Changed to correct payload keys

4. **SCRY Event payload keys** (`temporal_horizons.py:1471`)
   - Bug: Used `player_id` and `amount` instead of `player` and `count`
   - Fix: Changed to `'player': obj.controller, 'count': 1`

5. **LIFE_LOSS EventType** (`temporal_horizons.py:1477`)
   - Bug: Used `LIFE_LOSS` with `player_id` key
   - Fix: Changed to `LIFE_CHANGE` with negative amount and `player` key

6. **SCRY Handler inflexible** (`pipeline.py:665`)
   - Bug: Many cards used `amount` but handler only accepted `count`
   - Fix: Handler now accepts both `count` and `amount` keys

7. **MILL Handler inflexible** (`pipeline.py:735`)
   - Bug: Cards used `amount` but handler only accepted `count`
   - Fix: Handler now accepts both `count` and `amount` keys

**All tests pass:** 33 (4 Lorwyn, 20 degenerate, 11 layer nightmare)

**Verified working:**
- All 19 custom card modules import successfully
- Interceptors fire correctly (ETB triggers, counters)
- Basic game setup and zone movement works

---

### 2026-02-05T12:XX:XX UTC - PT_MODIFICATION and EventType Bug Fixes

**Fixed multiple bugs:**

1. **PT_MODIFICATION Implementation** (`types.py`, `pipeline.py`, `queries.py`, `turn.py`)
   - Added `PT_MODIFICATION` event type for temporary P/T boosts (until end of turn)
   - Added `_handle_pt_modification()` handler in pipeline.py
   - Updated `get_power()` and `get_toughness()` to apply `obj.state.pt_modifiers`
   - Added cleanup in turn.py's `_do_cleanup_step()` to remove end-of-turn modifiers
   - Tests: `test_pt_modification_until_eot`, `test_pt_modification_with_counters`

2. **Boggart Prankster Attack Trigger** (`lorwyn_custom.py:1786`)
   - Bug: Stub returned empty list instead of actual PT modification
   - Fix: Now emits PT_MODIFICATION event for +1/+0 to attacking Goblin

3. **DEAL_DAMAGE EventType Doesn't Exist** (`temporal_horizons.py`)
   - Bug: 3 cards used non-existent `EventType.DEAL_DAMAGE`
   - Fix: Changed to `EventType.DAMAGE` with proper payload (target, amount, is_combat)
   - Affected: Echo of Rage, Echo Dragon, Rift Spark

4. **37 Missing EventTypes** (`types.py`)
   - Bug: Many cards used undefined EventTypes (DESTROY, COUNTER, COPY_SPELL, etc.)
   - Fix: Added 40+ new EventTypes to cover card-used events
   - Includes: DESTROY, COUNTER, RETURN_TO_HAND, TAP_TARGET, EXTRA_TURN, PHASE_OUT, etc.

5. **Attribute Access Bugs** (`studio_ghibli.py`, `penultimate_avatar.py`, `lorwyn_custom.py`)
   - `.counters` -> `.state.counters` (9 instances across 2 files)
   - `.tapped` -> `.state.tapped` (1 instance in lorwyn_custom.py)
   - `.attached_to` -> `.state.attached_to` (1 instance)
   - `ObjectState.ATTACKING` -> `state.tapped` (2 instances in studio_ghibli.py)

6. **DAMAGE Events with target: None** (`demon_slayer.py`)
   - Fixed 3 cards: Flame Breathing Student, Kaigaku, Kyojuro Rengoku
   - Now properly target opponent

7. **DRAW Handler Payload Bug** (`pipeline.py`)
   - Handler expected 'count' but 97 cards used 'amount'
   - Fixed handler to accept both, defaulting to 'amount'

8. **Test Coverage**
   - Added `test_replacement_effect_exile_instead_of_die` for TRANSFORM interceptors

**Tests:** 33 passing (4 Lorwyn, 20 degenerate, 11 layer nightmare)

---

### 2026-02-05T10:XX:XX UTC - Lord Effect Bug Fix and AI Test Script

**Fixed 1 bug:**
1. **Lord Effects Active from Library** (`lorwyn_custom.py`, `interceptor_helpers.py`)
   - Bug: `make_static_pt_boost` didn't check if source was on battlefield
   - Cause: Interceptors registered at card creation time, filter only checked target not source
   - Fix: Added zone check `if not source or source.zone != ZoneType.BATTLEFIELD: return False`
   - Commit: `3cc9c45`

**Created AI vs AI test script** (`tests/test_ai_games.py`):
- Builds tribal decks (Kithkin, Merfolk, Goblin, Elf) from Lorwyn Custom cards
- Runs games with AggroStrategy, ControlStrategy, MidrangeStrategy AIs
- Validates mana system, spell casting, land playing, combat phases

**Key technical learnings:**
- Zone movement requires updating both `obj.zone` AND zone objects lists
- TurnManager has its own `turn_state`, not shared with GameState
- ManaSystem's `can_cast()` checks untapped lands on battlefield (zone objects list)
- Priority system correctly filters uncastable spells by mana availability

---

### 2026-02-05T08:XX:XX UTC - Manual AI Testing and Import Fix
**Conducted manual AI vs AI game testing:**

- Set up proper turn management for Game class (must set `turn_state.active_player_id`, `phase`, `lands_played_this_turn`, etc.)
- Discovered `_execute_action` is async - use direct Event emission for synchronous testing
- Tracked summoning sickness separately from engine's `entered_zone_at` timestamp system
- Ran 5 successful games with combat, blocking, creature deaths, and life total changes

**Fixed 1 bug:**
1. **Missing import in lorwyn_custom.py**
   - Bug: `make_end_step_trigger` used but not imported at module level
   - Fix: Added to top-level imports, removed redundant local import in `merrow_commerce_setup`
   - Commit: `eef6ce0`

**Testing observations:**
- Game mechanics work correctly: land playing, mana generation, creature casting, combat damage
- ETB triggers (like Rooftop Percher's lifelink) fire correctly
- Blocking and combat math resolves properly
- State-based actions (creature death from damage) work

---

## Key Findings

### Event Pipeline Architecture
- Events flow: TRANSFORM → PREVENT → RESOLVE → REACT
- Interceptors register with cards via `setup_interceptors` callback
- `while_on_battlefield` duration interceptors are cleaned up when leaving battlefield
- ETB triggers fire in REACT phase after ZONE_CHANGE resolves

### Event Payload Conventions
- DAMAGE: `target` (player_id or object_id), `amount`, `source` (optional), `is_combat` (optional)
- DRAW: `player` (not player_id), `amount` (preferred) or `count` (legacy)
- LIFE_CHANGE: `player` (not player_id), `amount` (positive for gain, negative for loss)
- SCRY: `player`, `count` (number of cards)

### Known Card Limitations
- `mono_red_aggro` deck includes `Accelerated Striker` which costs {R}{G} (Gruul) - wrong for mono-red
- Custom cards from Temporal Horizons set power the standard decks
- Cards with `target: 'choose'` or `target: 'creature'` are stubs needing targeting system

### AI Strategies
- AggroStrategy: Plays creatures early, attacks aggressively
- ControlStrategy: Holds up mana, uses removal, blocks when needed
- MidrangeStrategy: Balance of aggression and defense

### Zone Movement Requirements
When moving objects between zones manually (not through events):
1. Remove object ID from source zone's `objects` list
2. Add object ID to destination zone's `objects` list
3. Update `obj.zone` attribute
4. ManaSystem checks `battlefield.objects` list, not just `obj.zone`
