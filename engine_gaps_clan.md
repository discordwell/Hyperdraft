# CLAN — Engine gaps for Stage 4.7

Punch list of engine-side primitives the CLAN set needs that don't yet exist
(or are wired but no-op). Written by the post-parallel reconciliation agent
after merging the four archetype outputs (FORGE / ETHOS / MIRTH / BULWARK).

Each entry: gap name → affected cards → expected primitive → severity.

Severity legend:
- **silent**  — card registers an interceptor that filters but never fires
  (no crash, just no effect)
- **partial** — card works in some code paths but not others
- **hard**    — would raise / crash if reached

---

## 1. Activated abilities have no dispatcher — **RESOLVED**

**Affected**: 10 cards across FORGE/ETHOS/BULWARK use
`make_weapon_activated(...)` (Salvager-7, Modular Railgun, Recoil Mount,
Apex Coilgun, Reactor Shell, Memory Buffer, Stunner Arm, Workshop Wrench,
Coolant Cradle, Auxiliary Bench).

**Resolution**:
- `src/engine/clankers.py` ships `activate_ability(state, player_id,
  source_obj_id, *, ability_index=0, targets=None) -> list[Event]`. It
  validates ownership, pays the declared compute cost (routed through
  `_spend_compute` so cost-reduction TRANSFORMs apply) and optional
  `exhaust_self`, then invokes the descriptor's `effect_fn` with a
  synthetic `CLANKERS_ACTIVATE` event. Returns
  `[CLANKERS_ACTIVATE marker, *cost_events, *effect_events]`. Returns
  `[]` (no mutation) on insufficient cost, controller mismatch, already-
  tapped source when `exhaust_self=True`, or bad ability_index.
- `src/engine/types.py` adds `EventType.CLANKERS_ACTIVATE`.
- `src/engine/clankers_turn.py::_dispatch_activate` routes the contract
  §1 `{"action": "activate_ability", ...}` shape through the new
  function (the `hasattr` guard is gone).
- `src/ai/clankers_adapter.py` adds `_enumerate_activatable_abilities`
  which walks chassis + attached parts + solo parts + structures and
  yields affordable `(source_obj_id, ability_index, cost_spec, descriptor)`
  tuples. Medium tier fires only lethal-finisher activations
  (`_medium_lethal_activation`); hard tier scores all candidates (lethal,
  defensive lockouts, value plays at <=2 compute) and folds them into
  `_hard_assemble_action`'s scoring loop. The hard early-return on empty
  hand is gated so an in-play activation can still happen with an empty
  hand.
- Tests: `tests/test_clankers_activated_abilities.py` (13 cases) covers
  cost-payment + state mutation for 3 representative cards, the four
  negative paths (insufficient compute, already-tapped, wrong controller,
  bad index), turn-manager routing, AI enumeration, and the lethal-
  finisher pick under medium + hard tiers.

**Severity**: silent — now functional.

---

## 2. Armor-skip marker / event distinction (silent, low priority)

**Affected**: Carbon-Steel Drudge (FORGE) — its printed text reads
"This is unaffected by armor-skip effects from Transients you don't
control." The card setup is currently empty (just a chassis with
`# TODO: armor-skip immunity`).

**State today**: No card in CLAN actually has the "armor-skip" effect, so
the immunity is currently vacuous. If/when an armor-skip Transient is
introduced (e.g. "Damage from this Transient ignores armor"), the engine
needs an event that armor interceptors can filter on:

```python
# In DAMAGE / CLANKERS_COMBAT_DAMAGE payloads:
"armor_skip": True   # or
"armor_skip_source": "transient"
```

Carbon-Steel's setup_interceptors would register a TRANSFORM on the
DAMAGE event filtered by `armor_skip == True AND source_card_def is
CLANKERS_TRANSIENT AND source.controller != obj.controller`, removing
the flag.

**Severity**: silent + currently vacuous. Card still functions as a 2/6
tank. Re-implement when an actual armor-skip Transient ships (likely
late Stage 4 or Stage 5).

---

## 3. Death attribution for non-chassis kills (silent, partial)

**State today**: `clankers_combat.py` correctly populates
`kill_credited_to` on `CLANKERS_CHASSIS_DESTROYED`. **Salvage Cleaver
works today** (its TODO was stale and has been removed in this pass).

**Future gap**: weapons/add-ons destroyed by other weapons/add-ons (not
yet a thing in CLAN, but plausible) don't carry attribution. If a Stage
4.7+ card reads "when your host kills a weapon" we'll need
`kill_credited_to` on `CLANKERS_WEAPON_DESTROYED` and
`CLANKERS_ADD_ON_DESTROYED` too. The combat manager already populates
these for combat-damage kills (lines 576, 602 of `clankers_combat.py`);
just death_cascade doesn't.

**Severity**: silent. No CLAN card currently relies on this; flag for
future-set scoping.

---

## 4. CLANKERS_HAND_REFILL_QUERY interceptor support (silent)

**State today**: `emit_refill_query` in `clankers.py` already calls
`_dispatch_interceptors` against the query event. Cards CAN register
TRANSFORM interceptors that mutate `payload['target_hand_size']` (e.g.
"refill to 8 instead of 7"). But:

- No CLAN card currently uses this. (Some cards like FORGE bookkeepers
  do not lean on hand-size payoffs.)
- If a Stage-4.7 set wants "refill 2 extra cards", the helper API is
  there but unused; we should add a `make_refill_modifier(amount=+N)`
  helper to `clankers.py` so card authors don't roll their own.

**Severity**: cosmetic. Functional today via raw `Interceptor` plumbing
but no ergonomic helper.

---

## 5. Structure cap (CLANKERS_MAX_STRUCTURES = 3) — choose-which-to-scrap (silent / cosmetic)

**State today**: `_play_structure` in `clankers.py` FIFO-evicts the
oldest structure when the 4th comes down. The contract specifies "player
chooses which to scrap". Currently no CLAN card cares which one is
evicted, but a Stage-4.7 set might (e.g. a Structure with an end-step
trigger you want to keep alive).

**Expected**: thread `choose_structure_to_scrap` into the AI adapter +
the turn manager's action loop. Stage 4.7 can add the choice point
without breaking existing cards.

**Severity**: silent. Current FIFO is "fine" but not strictly correct.

---

## 6. Solo-part TRANSFORM interceptors — fixed in this pass

**Was**: `compute_effective_power` / `compute_effective_integrity`
short-circuited to `CLANKERS_SOLO_PART_POWER` / `..._INTEGRITY` for
non-chassis parts, never dispatching `CLANKERS_QUERY_POWER` /
`..._QUERY_INTEGRITY`. The MIRTH agent's Self-Mobile interceptors
registered correctly but never fired.

**Now**: solo parts also dispatch interceptors with the solo baseline
as `base_value`. Self-Mobile bonuses + any future static-on-solo-part
interceptor work correctly. **No action needed for Stage 4.7** — listed
here for posterity / regression-test scoping.

---

## 7. End-of-turn interceptor sweep — fixed in this pass

**Was**: `_phase_cleanup` in `clankers_turn.py` did not remove
`duration='end_of_turn'` interceptors from `state.interceptors`. MIRTH's
temp-buff helpers worked around it by snapshotting the turn number in
their filter, but interceptors accumulated indefinitely (memory leak in
long games).

**Now**: `_phase_cleanup` sweeps `state.interceptors` for
`duration='end_of_turn'` entries and evicts them (plus removes from
source-object `interceptor_ids` lists). The snapshot-filter pattern in
MIRTH still works defensively — it just no longer needs to.

---

## 8. Skip-ready-next-Boot flag — fixed in this pass

**Was**: Containment Lance (ETHOS) set
`state.clankers_clan_ethos_skip_ready_next_boot[defender] = True` but
`_phase_boot` ignored the flag.

**Now**: `_phase_boot` reads the per-player flag before the untap loop,
skips untap if set, and consumes the flag (one-shot). The lockout lasts
exactly one Boot per Containment Lance trigger as designed.

---

## 9. `make_part_on_self_destroyed` payload key drift — fixed in this pass

**Was**: helper filtered only on `event.payload.get("part_id")`. The
combat manager's direct-destroy path emits `CLANKERS_WEAPON_DESTROYED`
/ `CLANKERS_ADD_ON_DESTROYED` with `object_id` (not `part_id`).
Cards using the helper (Heavy Spike, Subroutine Driver, Recursive Tape,
…) would only fire on death-cascade kills, not on combat-damage kills.

**Now**: filter accepts either key. ~8 cards across FORGE/ETHOS/MIRTH/BULWARK
that use the helper now fire correctly under both destruction paths.

---

## 10. ETHOS Decoder Spike counter ordering — fixed in this pass

**Was**: `decoder_spike_setup` filtered on
`state.clankers_clan_ethos_transients_this_turn[controller] == 0` to detect
"first Transient this turn". But the ETHOS global counter hook
(`install_ethos_counter_hooks`) is registered FIRST in dispatch order (it's
installed by the `_wrap_with_hook` wrapper before any per-card setup runs).
By the time Decoder Spike's REACT interceptor checks the counter, the
global hook has already incremented it to `1` — so the `== 0` check is
always false and the card never fires.

**Now**: Decoder Spike's filter checks `counter == 1` (transition 0→1, "first
Transient this turn after the global increment"). Verified by
`tests/test_clan_interceptors.py::_run_transient_react_test`.

**Severity**: silent (card wired, interceptor never fired). Surfaced by
Stage 7.5b interceptor verification — the gate's purpose.

---

## 11. Public Telemetry uninitialised-attr crash — fixed in this pass

**Was**: `_public_telemetry_setup` did
`st.public_telemetry_transients[obj.controller] = 0` inside the turn-end
REACT handler without first ensuring `public_telemetry_transients` was set
as a state attribute. If no Transient had been played that turn, the
`track_ic` REACT never fired, the attribute was never created, and the
assignment AttributeErrored. The error was silently swallowed by the
exception handler in `_on_turn_end_trigger`, so the +1 Compute pending
queue never accumulated.

**Now**: both `end_react` and `start_react` defensively
`if not hasattr(st, "..."): st.<attr> = {}` before reading/writing.

**Severity**: silent (card wired, effect crashed silently). Surfaced by
Stage 7.5b.

---

## Out-of-scope: design-doc dual naming for "Affection.exe"

The design doc has both a Core and an Add-On named "Affection.exe". Dict
keys can't collide, so the Add-On is keyed `"Affection.exe Add-On"` in
the registry while its printed `name` remains "Affection.exe" (matches
design doc § 521). This is **not** a gap — flagging here in case
downstream tooling (e.g. card-name search) needs to be aware that
printed-name lookups can return either card.
