# Claudepad - Session Memory

## Session Summaries

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
   - `ObjectState.ATTACKING` -> `state.tapped` (2 instances in studio_ghibli.py)

6. **Test Coverage**
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

### 2026-02-05T05:XX:XX UTC - Bug Fixes for Layer System and Land Playing
**Fixed 2 critical bugs:**

1. **Double Interceptor Registration on ETB** (`pipeline.py:316`)
   - Bug: Interceptors were registered twice when objects entered battlefield
   - Cause: `create_object()` registered interceptors immediately, then `_handle_zone_change()` registered them again on ZONE_CHANGE event
   - Fix: Added check `and not obj.interceptor_ids` to prevent re-registration
   - Impact: Fixed `test_counter_shenanigans` (Burdened Stoneback getting 4 counters instead of 2) and `test_anthem_plus_counters`

2. **Land Playing Broken** (`priority.py:502`)
   - Bug: Lands weren't moving to battlefield when played
   - Cause: `_handle_play_land()` used string `'BATTLEFIELD'` instead of `ZoneType.BATTLEFIELD` enum
   - Fix: Changed to `ZoneType.BATTLEFIELD` and added missing import
   - Impact: AI can now play lands and produce mana, enabling spell casting

**Tests verified:**
- All degenerate tests pass
- All Lorwyn tests pass
- All layer nightmare tests pass
- AI game runs correctly (lands, spells, attacks, blocks, combat damage)

---

## Key Findings

### Event Pipeline Architecture
- Events flow: TRANSFORM → PREVENT → RESOLVE → REACT
- Interceptors register with cards via `setup_interceptors` callback
- `while_on_battlefield` duration interceptors are cleaned up when leaving battlefield
- ETB triggers fire in REACT phase after ZONE_CHANGE resolves

### Known Card Limitations
- `mono_red_aggro` deck includes `Accelerated Striker` which costs {R}{G} (Gruul) - wrong for mono-red
- Custom cards from Temporal Horizons set power the standard decks

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
