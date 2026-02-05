# Claudepad - Session Memory

## Session Summaries

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
