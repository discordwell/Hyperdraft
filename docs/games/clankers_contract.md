# Clankers Stage-1 Implementation Contract

The 4 parallel scaffold agents (engine, combat, turn, AI) all read this file. **Treat every signature and dict shape here as immutable**; if you need to deviate, leave a `# CONTRACT-DEVIATION:` comment and the Stage 1.5 reconciliation agent will adjudicate.

Design source: `docs/games/clankers.md`.

---

## 1. Action contract — what the AI returns

All AI decisions to the turn manager use **dicts**, not dataclasses.

```python
choose_assemble_action(state, player_id) -> Optional[dict]
```

Returns one of these dict shapes (or `None` / `{"action": "pass"}` to end the Assemble phase):

```python
{"action": "play_chassis",     "card_obj_id": str, "compute_cost": int}
{"action": "play_weapon",      "card_obj_id": str, "compute_cost": int, "target_chassis_id": Optional[str]}  # None = play solo
{"action": "play_add_on",      "card_obj_id": str, "compute_cost": int, "target_chassis_id": Optional[str]}
{"action": "play_transient",   "card_obj_id": str, "compute_cost": int, "targets": list[str]}
{"action": "play_structure",   "card_obj_id": str, "compute_cost": int}
{"action": "attach_floor_part","part_obj_id": str, "target_chassis_id": str}                                  # part already on floor, compute_cost = 0
{"action": "activate_ability", "source_obj_id": str, "ability_index": int, "targets": list[str]}
{"action": "pass"}
```

Other AI methods:
```python
choose_attackers(state, player_id) -> list[str]
    # list of chassis OR solo-part obj_ids controlled by player_id

choose_blockers(state, player_id, attackers: list[str]) -> dict[str, str]
    # {attacker_id: blocker_id}; missing keys = attacker unblocked

choose_refill(state, player_id) -> bool
    # True = take Allocate-phase refill; False = decline

mulligan_decision(state, player_id, num_kept: int) -> bool
    # True = mulligan (Vancouver-style); False = keep

choose_target(state, source_id: str, candidates: list[str], requirement: dict) -> Optional[str]
    # Mid-resolution target selection. requirement has 'kind' ('chassis'/'part'/'player') and 'reason'.
    # Returns None for 'may' decline or no legal target.
```

---

## 2. Combat manager contract

```python
class ClankersCombatManager:
    def __init__(self, game):  # game has .state, .clankers_ai_handlers
        self.game = game
        self.state = game.state

    def resolve_combat_phase(self, attacker_player_id: str) -> list[Event]:
        # 1. Call game.clankers_ai_handlers[attacker_player_id].choose_attackers(state, attacker_player_id)
        # 2. For each attacker, emit CLANKERS_ATTACK_DECLARE
        # 3. Call game.clankers_ai_handlers[defender_id].choose_blockers(state, defender_id, attackers)
        # 4. For each pairing, emit CLANKERS_BLOCK_DECLARE
        # 5. For each (attacker, blocker) pair:
        #    - Compute attacker effective power via clankers.compute_effective_power
        #    - Compute blocker effective power same way
        #    - Emit two simultaneous CLANKERS_COMBAT_DAMAGE events
        # 6. For each unblocked attacker, emit CLANKERS_WORKSHOP_DAMAGE on defender's Core
        # 7. SBA: any chassis with damage_marked >= effective_integrity gets destroyed → cascade
        # 8. Return list of emitted events
```

---

## 3. Turn manager contract

```python
class ClankersTurnManager(TurnManager):
    def __init__(self, state):
        # Matches the mode-adapter factory convention used by every peer
        # engine (cats, depths, minecraft, hearthstone). Read the Game
        # back-ref via state._game when the AI handler is needed.
        super().__init__(state)
        self.combat_manager = None  # built lazily in setup_game once
                                    # state._game is wired by _connect_subsystems
        # state.game_mode is set to "clankers" by setup_game

    def setup_game(
        self,
        deck_a: list[CardDefinition], core_a: CardDefinition,
        deck_b: list[CardDefinition], core_b: CardDefinition,
    ) -> None:
        # 1. Shuffle each deck with state.rng_seed (if set) or random.
        # 2. Deal 7 to each player (CLANKERS_HAND_FLOOR initial hand).
        # 3. Place each Core as a GameObject in zone ZoneType.COMMAND.
        #    Register core's passive setup via card_def.clankers_core_passive_setup.
        # 4. Initialize all state.clankers_* fields.
        # 5. Set state.active_player to a random / coin-flip choice.
        # 6. Emit GAME_START.
        # 7. Player 1 skips Combat on their first turn (set state.clankers_first_turn = True).

    def run_turn(self, player_id: str) -> list[Event]:
        # Runs all 6 phases sequentially, returning all events emitted.
        events = []
        events += self._phase_boot(player_id)
        events += self._phase_allocate(player_id)
        events += self._phase_assemble(player_id)
        events += self._phase_combat(player_id)
        events += self._phase_reassemble(player_id)
        events += self._phase_cleanup(player_id)
        return events

    # Phase helpers (private):
    _phase_boot(player_id)
    _phase_allocate(player_id)
    _phase_assemble(player_id)
    _phase_combat(player_id)         # delegates to self.combat_manager.resolve_combat_phase
    _phase_reassemble(player_id)
    _phase_cleanup(player_id)
```

---

## 4. Engine module contract (clankers.py public API)

### Constants (defined at module top)
```python
CLANKERS_HAND_FLOOR = 7
CLANKERS_DECK_SIZE = 60
CLANKERS_STARTING_WORKSHOP_INTEGRITY = 25
CLANKERS_COMPUTE_POOL_BASE = 3
CLANKERS_COMPUTE_CAP = 10
CLANKERS_SCRAP_CAP = 10
CLANKERS_MAX_STRUCTURES = 3
CLANKERS_DEATHCLOCK_BASE = 2
CLANKERS_DEATHCLOCK_MULTIPLIER = 2
CLANKERS_DEFAULT_CHASSIS_WEAPON_SLOTS = 2
CLANKERS_DEFAULT_CHASSIS_ADDON_SLOTS = 2
CLANKERS_SOLO_PART_POWER = 1
CLANKERS_SOLO_PART_INTEGRITY = 1
```

### State (attached to GameState via setattr — cats pattern)
```python
state.clankers_workshop_integrity: dict[str, int]
state.clankers_compute_pool: dict[str, int]
state.clankers_compute_cap: dict[str, int]
state.clankers_scrap_pool: dict[str, int]
state.clankers_refill_used: dict[str, bool]
state.clankers_cores: dict[str, str]          # player_id -> core obj_id
state.clankers_containment_failure: bool
state.clankers_containment_turn: int
state.clankers_structures: dict[str, list[str]]  # player_id -> structure obj_ids (max 3)
state.clankers_assemblies: dict[str, list[str]]  # player_id -> chassis obj_ids on floor
state.clankers_loser: Optional[str]
state.clankers_first_turn: bool   # True on player 1's turn 1; skips combat phase
state.clankers_first_player: str  # the player who acts first; combat is skipped iff
                                  # active_player == clankers_first_player AND
                                  # clankers_first_turn is True AND turn_number == 1
```

### Zone-key convention

Per-player zones (HAND, LIBRARY, COMMAND, CLANKERS_SCRAP_HEAP, CLANKERS_ASSEMBLY_FLOOR) are
keyed with **lowercase**: `f"{zone_type.name.lower()}_{player_id}"`. This matches
`game.py`'s `_create_player_zones` and the convention used by every peer engine
(`depths.py`, `minecraft.py`). Example: `state.zones["hand_p1"]`,
`state.zones["clankers_assembly_floor_p1"]`.

### Public functions
```python
def setup_clankers_player(
    state: GameState,
    player_id: str,
    deck: list[CardDefinition],
    core_card_def: CardDefinition,
) -> None:
    """Initialize all clankers_* state for this player, create Core in COMMAND."""

def play_card_from_hand(state, player_id, card_obj_id, **kwargs) -> list[Event]:
    """Top-level dispatcher: routes by CardType to play_chassis/play_weapon/etc."""

def attach_part(state, part_obj_id, target_chassis_id) -> list[Event]:
    """Validate slot availability, set obj.state.attached_to, emit CLANKERS_PART_ATTACHED."""

def detach_part(state, part_obj_id) -> list[Event]:
    """Reverse of attach_part."""

def compute_effective_power(state, chassis_obj_id) -> int:
    """Emit CLANKERS_QUERY_POWER, sum interceptor transforms onto base value."""

def compute_effective_integrity(state, chassis_obj_id) -> int:
    """Emit CLANKERS_QUERY_INTEGRITY, sum interceptor transforms onto base value."""

def emit_refill_query(state, player_id) -> list[Event]:
    """Allocate-phase entry: emit CLANKERS_HAND_REFILL_QUERY, default handler draws to 7."""

def activate_deathclock_if_needed(state) -> list[Event]:
    """If both libraries empty post-refill, set containment_failure=True. Increment + emit tick if already active."""

def check_workshop_breached(state) -> Optional[str]:
    """Return player_id of any player whose workshop_integrity <= 0, else None."""

def death_cascade(state, chassis_obj_id) -> list[Event]:
    """Move all attached parts to scrap heap and emit CLANKERS_*_DESTROYED markers."""
```

### Card factories
```python
def make_chassis(name, *, power, integrity, weapon_slots=2, add_on_slots=2,
                 compute_cost=2, text="", rarity="common", clankers_archetype=None,
                 setup_interceptors=None) -> CardDefinition

def make_weapon(name, *, power_bonus, compute_cost=1, weapon_slot_cost=1,
                clankers_keywords=None, text="", rarity="common",
                clankers_archetype=None, setup_interceptors=None) -> CardDefinition

def make_add_on(name, *, integrity_bonus=0, power_bonus=0, compute_cost=1,
                armor_value=None, clankers_keywords=None, text="", rarity="common",
                clankers_archetype=None, setup_interceptors=None) -> CardDefinition

def make_transient(name, *, compute_cost, resolve_fn, text="", rarity="common",
                   clankers_archetype=None) -> CardDefinition

def make_structure(name, *, compute_cost=2, setup_interceptors, text="",
                   rarity="rare", clankers_archetype=None) -> CardDefinition

def make_core(name, *, workshop_integrity=25, passive_setup=None,
              text="", flavor="") -> CardDefinition
```

### Helper interceptor builders (for card scripts)
```python
def make_chassis_etb_trigger(obj, effect_fn) -> Interceptor
def make_part_on_attach(obj, effect_fn) -> Interceptor    # fires when this part attaches
def make_part_on_host_attack(obj, effect_fn) -> Interceptor
def make_part_on_host_destroyed(obj, effect_fn) -> Interceptor
def make_part_on_self_destroyed(obj, effect_fn) -> Interceptor
def make_weapon_activated(obj, *, compute_cost=0, exhaust_self=False, effect_fn, description=""):
def make_add_on_static_power(obj, power_mod: int) -> Interceptor
def make_add_on_static_integrity(obj, integrity_mod: int) -> Interceptor
def make_armor(obj, armor_value: int) -> Interceptor       # TRANSFORM on DAMAGE to host
def make_structure_global(obj, modifier_fn) -> Interceptor
def make_core_passive(obj, modifier_fn, description="") -> Interceptor
```

### Mode adapter
```python
class ClankersModeAdapter(GameModeAdapter):
    """Wires Clankers into the global mode-adapter registry.

    Overrides:
    - handle_empty_library_draw: triggers containment_failure, not loss.
    - handle_lethal_damage: routes chassis death to death_cascade.
    - is_storage_zone_extended: declares CLANKERS_SCRAP_HEAP as graveyard analogue.
    """
```

---

## 5. CardDefinition extensions

Clankers stores per-card numbers as **dynamic attrs** on the standard CardDefinition (cats pattern). Card factories do `card_def.compute_cost = N` etc. Readers use `getattr(card_def, "compute_cost", 0)`.

Field reference:
```
card_def.compute_cost: int
card_def.power: int                        # chassis only
card_def.integrity: int                    # chassis only
card_def.power_bonus: int                  # weapons / add-ons
card_def.integrity_bonus: int              # add-ons (and a few weapons)
card_def.weapon_slots: int                 # chassis only
card_def.add_on_slots: int                 # chassis only
card_def.weapon_slot_cost: int             # weapons; defaults 1
card_def.armor_value: Optional[int]        # add-ons with armor keyword
card_def.clankers_keywords: list[str]
card_def.clankers_archetype: Optional[str]
card_def.clankers_resolve: Optional[Callable]  # transient effect (event, state) -> list[Event]
card_def.clankers_core_passive_setup: Optional[Callable]  # core (obj, state) -> list[Interceptor]
```

`card_def.characteristics.types` contains exactly one `CardType.CLANKERS_*` value.

---

## 6. AI handler access

The Game object holds AI adapters indexed by player_id. Per the depths pattern, the
canonical attribute is `clankers_ai_handlers` (plural, namespaced) — peer engines
use `<mode>_ai_handler(s)` to avoid collisions across modes:

```python
game.clankers_ai_handlers                 # dict[str, ClankersAIAdapter]
game.clankers_ai_handlers[player_id].choose_attackers(state, player_id)
```

Turn manager and combat manager both go through this dict. NEVER hold a local
reference to one specific AI — re-fetch each call so per-player swaps work.

The turn manager exposes a registration helper `set_ai_handler(handler, player_id=None)`
that mirrors the depths convention; the AI dict lives on the turn manager (in
`self.clankers_ai_handlers`) and any `game.clankers_ai_handlers` value is honoured
as a secondary lookup so tests can wire either side.

---

## 7. EventType names (already added to types.py)

Use the exact enum members:
```
CLANKERS_TURN_START, CLANKERS_TURN_END
CLANKERS_ATTACH_PART, CLANKERS_DETACH_PART
CLANKERS_PART_ATTACHED, CLANKERS_PART_DETACHED
CLANKERS_HAND_REFILL_QUERY
CLANKERS_QUERY_POWER, CLANKERS_QUERY_INTEGRITY
CLANKERS_COMPUTE_SPEND, CLANKERS_COMPUTE_GAIN
CLANKERS_SCRAP_GAIN, CLANKERS_SCRAP_SPEND
CLANKERS_CHASSIS_DESTROYED, CLANKERS_WEAPON_DESTROYED, CLANKERS_ADD_ON_DESTROYED
CLANKERS_DEATH_CASCADE
CLANKERS_ATTACK_DECLARE, CLANKERS_BLOCK_DECLARE, CLANKERS_COMBAT_DAMAGE
CLANKERS_WORKSHOP_DAMAGE, CLANKERS_WORKSHOP_BREACHED
CLANKERS_CONTAINMENT_FAILURE_TICK
CLANKERS_CORE_PASSIVE
CLANKERS_REFILL_TAKEN, CLANKERS_REFILL_DECLINED
```

CardType enum values: `CLANKERS_CHASSIS, CLANKERS_WEAPON, CLANKERS_ADD_ON, CLANKERS_TRANSIENT, CLANKERS_STRUCTURE, CLANKERS_CORE`.

ZoneType enum values: `CLANKERS_ASSEMBLY_FLOOR, CLANKERS_SCRAP_HEAP`.

(`HAND`, `LIBRARY`, `COMMAND` reuse existing.)

---

## 8. Stage 1 smoke test (what Agent 1 writes)

`tests/test_clankers_smoke.py`:
1. Constructs a minimal 60-card deck per player from ~6 placeholder card defs (2 chassis, 2 weapons, 1 add-on, 1 transient) repeated.
2. Picks 1 placeholder Core per player.
3. Runs ClankersTurnManager.setup_game(...) and ClankersTurnManager.run_turn(player_a_id) for up to 40 turns alternating.
4. Asserts: game completes (some player's workshop_integrity hits 0 OR deathclock fires), both AIs made >0 non-pass actions during Assemble, no exception raised.

The smoke test runs Easy AI vs Easy AI for determinism.

---

## 9. Deviations & open knobs

- If you need an event type not in §7, **add it to types.py and update this file**. Do not silently emit non-enum strings.
- If a contract field name is wrong / missing for your case, leave a `# CONTRACT-DEVIATION:` comment. Stage 1.5 will look for these.
- Cross-file imports: each file imports only from `src.engine.types`, `src.engine.cats` for reference patterns (do NOT import from cats at runtime), and the sibling clankers files. NO circular: combat → clankers OK, clankers → combat NOT OK.
