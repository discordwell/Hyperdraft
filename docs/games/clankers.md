# Clankers — A Multi-Part Robot Assembly Battler

## 1. Win Condition

The game ends when **a player's Workshop Integrity reaches 0** — at which point that player has been *destroyed by their own creations escaping containment*, and the opposing AI is declared the supreme intellect of the workshop. Workshop Integrity is an HP-like value (default 25) tracked on the player's **Core Processor**, a Commander-equivalent card that lives in the COMMAND zone for the entire game.

> `state.clankers_workshop_integrity[player_id] <= 0` → `state.clankers_loser = player_id`, emit `CLANKERS_WORKSHOP_BREACHED` then `PLAYER_LOSES` for that player and `PLAYER_WINS` for the survivor. `game_over = True`.

The game also can end by **deck-out under death-clock pressure**:
- When *both* players have drawn their final cards from their libraries and a refill would draw 0 cards, the **Containment Failure clock** starts: each player's Core Processor takes **2 self-damage per turn** (a damage event with source = own Core Processor, reason = `containment_failure`), and this doubles on each subsequent turn (2 → 4 → 8). This guarantees a winner within ~3 turns of deck-out.
- Pure simultaneous deck-out is not a draw: whoever's Core Processor hits 0 first loses. Simultaneous (both hit 0 on the same damage event) is a **draw** — both AIs explode together, allowed by the rules.

This satisfies the always-7 rule cleanly: hand pressure is irrelevant; deck depletion converts to direct damage, which is the actual loss condition. It satisfies the multi-card-robot rule because the *strategic point* of building bigger robots is to push more damage through to the Core Processor faster than the death-clock can punish you for cycling.

## 2. Turn Structure

A **turn** is the unit. Phases fire `PHASE_START` / `PHASE_END` events with the printed phase name in the payload. The turn order is asymmetric (active player only; the other player has interrupt windows during specific phases via REACT-priority interceptors on `CLANKERS_PART_ATTACH` and combat events). Phases:

| # | Phase | What happens |
|---|---|---|
| 1 | **Boot** (start) | Active player's exhausted parts ready (untap). `CLANKERS_TURN_START` fires. Compute pool replenishes: `compute = min(starting_compute + turn_number, 10)`. Structure on-upkeep triggers fire. |
| 2 | **Allocate** (refill) | The **once-per-turn hand refill** fires here. The engine emits `CLANKERS_HAND_REFILL_QUERY` for the active player. If unprevented, the player draws up to 7 cards (no draw if at 7+). `clankers_refill_used[active]` is set True. Refill is **MAY**: if the player declines, no draw fires. Declining is sometimes correct (to slow deck-out). |
| 3 | **Assemble** (main) | Active player may take any sequence of legal actions, paying Compute: play chassis to Assembly Floor, play parts (attach immediately to a chassis or stand alone), play Transients, play Structures, activate abilities. No stack — each action resolves before the next (Hearthstone-style). |
| 4 | **Combat** | Active player declares attackers from their Assembly Floor (chassis or solo parts). For each attacker, defender chooses which of their assemblies blocks. Damage resolves simultaneously per pairing. See §5 for math. |
| 5 | **Reassemble** (post-combat main) | A second window for Assemble actions. Same legality as Allocate. Used for "after-combat repairs" and burning leftover Compute on Transients. |
| 6 | **Cleanup** (end) | End-of-turn triggers fire. Damage on chassis persists (does not heal at EoT — that's a card effect). `clankers_refill_used[active]` is cleared. Pass priority to the other player. `CLANKERS_TURN_END` fires. Check the death-clock condition. |

Player 1 skips Combat on their first turn (one-sided combat opening is too lopsided under always-7 economy).

## 3. Resource Model

Two stacking resources gate plays. Hand size is **not** a resource.

**Compute** — a per-turn allocation pool. Each player has `compute_pool` (current) and `compute_cap` (max). At Boot, `compute_pool := min(compute_pool_base + turn_number, compute_cap)` where `compute_pool_base = 3` and `compute_cap = 10`. Compute does NOT carry over between turns (it's wall-clock cycles — use it or lose it). Cards print a `compute_cost: int`. Activated abilities also cost compute.

**Build Slots** — printed on each chassis: `weapon_slots: int` (typically 1–3) and `add_on_slots: int` (typically 2–4). A chassis can only carry up to that many attached parts of each type. A solo part on the Assembly Floor doesn't consume any chassis's slot (it's not attached). When a chassis dies, slots are vacated as attachments scatter to scrap. Slots are *the* lever for "bigger robots = more parts": a Heavy Chassis with 3W/4A slots produces a much more dangerous full-assembly than a Scout Chassis with 1W/2A slots.

**Scrap** — a small secondary pool earned by destroying enemy parts in combat or via card effects. `scrap_pool` starts at 0 and persists across turns. Spent by some cards to pay alternate or additional costs (e.g. "Pay 2 Scrap: a destroyed weapon returns to your hand"). Caps at 10 to prevent hoarding.

**Why Compute + Slots, not mana**: this is the distinctive piece. Compute models *AI processor allocation* — abstract, refreshes fully each turn, doesn't feel like spending physical currency. Build Slots model *physical hardpoint capacity on the robot's frame* — concrete, deterministic, per-chassis. Together they capture "the AI has finite cycles AND the robot has finite real estate" which is the design intent. They are independently tunable: nerf Compute costs to slow tempo, nerf slot counts on chassis to cap top-end power.

**Why this kills the discard-spam loop**: a card that says "discard 2, gain X" costs **Compute** to play, AND the discard refills only at *next* Allocate. So you spend resource and lose tempo. The loop never closes.

## 4. Zones

| Zone (per-player unless noted) | Purpose |
|---|---|
| `hand` | Current cards. Refills to 7 at Allocate phase if `clankers_refill_used[player_id]` is False. Cap is soft — cards/effects can push you above 7 (e.g. "Draw 3" mid-turn), and you stay there until the next discard. |
| `library` (deck) | 60-card deck. When empty, the deathclock activates. |
| `scrap_heap` (graveyard) | Destroyed parts and discarded cards land here. Some cards interact (e.g. "Restore: return a chassis from your scrap heap"). |
| `assembly_floor` | The **central battlefield zone**. Chassis, solo parts, and Structures live here. Functionally the BATTLEFIELD analogue. Per-player partition is *logical* (each object has a controller) but the zone is shared so cross-player effects ("destroy an opposing chassis") work cleanly. |
| `attachments` (logical) | Not a literal zone — parts that have attached to a chassis are still in `assembly_floor`, with `obj.state.attached_to = chassis_id`. Queries iterate `chassis.state.attachments` to enumerate. |
| `command` | The Core Processor lives here for the whole game. Cannot be destroyed by card effects, only by Workshop Integrity hitting 0 (which ends the game). |

**Death cascade**: when a chassis is destroyed, every attached weapon and add-on is **scattered to the scrap heap simultaneously** (one `OBJECT_DESTROYED` event each, all in the same step, all sourced from the same triggering damage event). On-destroy triggers fire for each part. This is the most-load-bearing rule for card design — many cards key off "when this weapon goes to the scrap heap."

**Solo parts**: a weapon or add-on played without a host chassis sits on the Assembly Floor as a 1-power, 1-integrity "loose part" (this is a flat baseline; card text doesn't have to print it). It can be attacked, can attack on its own, and **can be attached for free as a single Compute action on a later turn** if its controller has a chassis with an open slot. This is the "I drew a Plasma Cannon but no chassis to put it on yet" case.

**Assembly Floor visibility**: all parts, including face-down "Reserve" parts (created by a small card subset — design hook only, no v1 cards), are public information about their *identity*. Internal hidden state (a Sneaky-style hidden number) is not used.

## 5. Combat Math

Robot-vs-robot combat resolves by **aggregate stats**. Each assembly has:
- **Effective Power** = `chassis.power + sum(weapon.power_bonus for each attached weapon) + sum(add_on.power_bonus for each attached add_on)`
- **Effective Integrity** = `chassis.integrity + sum(add_on.integrity_bonus for each attached add_on)`. Weapons do NOT add integrity.

These values are computed via TRANSFORM-priority interceptors on `CLANKERS_QUERY_POWER` / `CLANKERS_QUERY_INTEGRITY` synthetic queries, so static effects from Structures (e.g. "All your chassis have +1 Power") and add-ons stack cleanly without procedural mutation.

**Damage**: when an attacker (`A`) and a blocker (`B`) face off, `A` deals its Effective Power as damage to `B` simultaneously with `B` dealing its Effective Power to `A`. Damage is marked on `chassis.state.damage_marked` (the existing field). State-based check: if `damage_marked >= effective_integrity`, the chassis is destroyed.

**Damage absorption (replacement effect on add-ons)**: an add-on with the `armor` keyword may EXHAUST (set `state.tapped = True`) to absorb up to its printed `armor_value` from incoming damage on its host chassis. Implemented as a TRANSFORM-priority interceptor on the DAMAGE event whose target is the host chassis; the interceptor decrements the damage payload and exhausts the add-on. Exhausted add-ons do not contribute their static integrity bonus until they ready at next Boot.

**Weapons in combat**: weapons do NOT die from combat damage (the chassis took the hit). They only die when:
- Their host chassis is destroyed (death cascade).
- A card effect destroys them directly.
- A solo weapon takes lethal damage (uses its own 1 integrity floor, which is essentially fragile).

**Defender chooses blockers per attacker**: each declared attacker is assigned at most one blocker by the defender. Unblocked attackers deal their Effective Power to the defender's **Core Processor** (Workshop Integrity damage). This is the standard "trample is implicit if unblocked" model — there's no explicit trample keyword needed.

**Combat damage credit**: every DAMAGE event carries `damage_credited_to = chassis.controller` (the chassis IS the assembly's identity, weapons are tools). On the kill (chassis dies), `kill_credited_to = attacker_chassis.controller` (or the source-card's controller for non-combat kills). This is the **explicit attribution** we promised — no symmetric ambiguity like the Cats snack-force bug.

### Worked Example

**Setup**: A's Iron Frame chassis (3 power, 4 integrity, 2W/2A slots) has attached: Buzzsaw Arm (`power_bonus=2, integrity_bonus=0`) and Reinforced Plating (`power_bonus=0, integrity_bonus=2`). B's chassis: Heavy Tread (5 power, 5 integrity), no attached parts. It is A's combat.

1. A declares Iron Frame as attacker. Effective Power = 3+2+0 = **5**. Effective Integrity = 4+0+2 = **6**.
2. B declares Heavy Tread as blocker. Effective Power = **5**. Effective Integrity = **5**.
3. Engine emits two simultaneous DAMAGE events:
   - `Event(DAMAGE, payload={target: HeavyTread, amount: 5, source: IronFrame, damage_credited_to: A})`
   - `Event(DAMAGE, payload={target: IronFrame, amount: 5, source: HeavyTread, damage_credited_to: B})`
4. State-based check: Heavy Tread has 5 damage vs 5 integrity → destroyed. `kill_credited_to: A`. Iron Frame has 5 damage vs 6 integrity → survives.
5. Buzzsaw Arm and Reinforced Plating remain attached to Iron Frame for next turn. Heavy Tread's controller (B) takes a `CLANKERS_CHASSIS_DESTROYED` event observable by all cards. (B had no weapons, so no death cascade.)

If instead Iron Frame's Reinforced Plating had the `armor` keyword with `armor_value=2`, A's controller could activate it pre-damage: the incoming DAMAGE event is transformed from amount 5 → amount 3, plating exhausts, Iron Frame takes 3 damage (well under integrity 6). The combat tempo just shifted dramatically.

## 6. Card Types

Six types. All but Core are played from hand during Assemble/Reassemble phases.

| Type | Role |
|---|---|
| **CLANKERS_CHASSIS** | The base of a robot. Has `power`, `integrity`, `weapon_slots`, `add_on_slots`, and `compute_cost`. Enters Assembly Floor unattached. Cannot itself be attached. ~30% of a typical deck. |
| **CLANKERS_WEAPON** | An attachable offensive part. Has `power_bonus` (additive when attached), `compute_cost`, optional `activated_ability` (e.g. "Fire: 1 Compute, deal 1 to any chassis"). Has `weapon_slot_cost = 1` (the default; some massive weapons cost 2 slots). When played, may be played attached (target a legal chassis with an open W slot) OR solo. ~25% of deck. |
| **CLANKERS_ADD_ON** | An attachable utility/defensive part. Has `power_bonus` (often 0), `integrity_bonus`, `compute_cost`, and zero or more static effects or keyword grants (`armor`, `regenerate`, `shielded`, etc.). Plays attached or solo. ~25% of deck. |
| **CLANKERS_TRANSIENT** | A one-shot AI subroutine. Pays `compute_cost`, resolves an effect, goes to scrap heap. Equivalent of MTG sorcery. Used for direct damage, draws, scrap-heap interaction, situational utility. ~12% of deck. |
| **CLANKERS_STRUCTURE** | A workshop fixture. Enters Assembly Floor and stays. Has `compute_cost`, no power/integrity (cannot be attacked unless a card grants it). Provides global passives ("Your chassis have +1 power" / "When you attach an add-on, draw a card"). Cap: 3 Structures per player on the Assembly Floor; 4th replaces (player chooses which to scrap). ~8% of deck. |
| **CLANKERS_CORE** | The AI itself. Pre-game-only. Each player picks one Core Processor from a small pool. Lives in COMMAND zone. Carries `workshop_integrity` (HP) and one always-on passive (e.g. "Your weapons cost 1 less Compute"). Cannot be played, attached, destroyed, or moved. Provides flavor identity (FORGE-Δ, ETHOS-7, MIRTHBOT-1). |

## 7. Engine Capabilities (The Contract)

What the engine must natively express. Each maps to one or more interceptor patterns. Stages 1–4 implement these.

1. **Part attach / detach** — `CLANKERS_ATTACH_PART` event with payload `{part_id, target_chassis_id, controller}`. Validation: legal slot type, free slot, both objects on Assembly Floor, same controller. The pipeline handler mutates `part.state.attached_to = target_chassis_id` and appends to `target.state.attachments`. `CLANKERS_DETACH_PART` reverses. Emits `CLANKERS_PART_ATTACHED` / `CLANKERS_PART_DETACHED` markers for triggers. Reuses the existing `attach.py` infrastructure (the ATTACH/UNATTACH event flow already exists for MTG Equipment) — we add the Clankers-specific markers as siblings.

2. **Per-part triggers** — `on_attach` (when this part attaches to a host), `on_detach`, `on_host_attack` (when this part's host attacks), `on_host_takes_damage`, `on_host_destroyed` (== the death cascade — this is how weapons get a last gasp), `on_self_destroyed`. Helper: `make_part_trigger(obj, phase, effect_fn)`. Implementation: filtered Interceptors on the corresponding marker events.

3. **Static effects from add-ons** — TRANSFORM-priority interceptors on `CLANKERS_QUERY_POWER` and `CLANKERS_QUERY_INTEGRITY` and `QUERY_ABILITIES`. Helper: `make_add_on_static(obj, modifier_fn)`. The interceptor's filter checks that the queried object is `obj.state.attached_to`.

4. **Activated abilities on weapons / add-ons** — Reuse the existing `ActivatedAbility` descriptor pattern (already on `ObjectState.activated_abilities`). The cost is one or more of: `compute:N`, `exhaust_self`, `exhaust_other_attached`, `scrap:N`. Helper: `make_clankers_activated(obj, cost_spec, effect_fn, description)`.

5. **Replacement effects (damage absorption, "would die instead exhaust")** — TRANSFORM-priority interceptors on DAMAGE and OBJECT_DESTROYED events. The `armor` keyword is one canonical implementation. The "if this would die, exhaust an add-on instead" effect is a `make_redirect_lethal_damage(chassis, candidate_add_on_filter)` helper that, when the chassis would die, finds a legal add-on, exhausts it, and zeroes the damage.

6. **State-time queries** — `count_attached(chassis_id, part_type)`, `sum_attached_bonus(chassis_id, field_name)`, `total_assemblies(player_id)`, `largest_assembly_power(player_id)`. Pure functions on GameState in `clankers_queries.py`. Used by AI heuristics AND by card text ("This deals damage equal to attached weapon count").

7. **The 7-card-floor as an engine event** — `CLANKERS_HAND_REFILL_QUERY` is emitted once per turn per player at the start of Allocate phase. Synthetic query event (REACT-priority observers; REPLACE-priority is permitted to cancel or transform the refill). Payload: `{player_id, current_hand_size, target_hand_size: 7, may: True}`. The default handler computes `draw_count = max(0, 7 - current_hand_size)` and queues a DRAW event. The player's `clankers_refill_used[player_id]` flag prevents re-firing same turn. Helper: `make_refill_modifier(source, modifier_fn)` for "you draw to 8 instead" / "you don't draw" / "draw 2 fewer."

8. **Compute pool management** — `CLANKERS_COMPUTE_SPEND` event (payload `{player_id, amount, source_card_id}`). Helper handlers TRANSFORM the amount (cost reduction effects) or PREVENT (lock-out effects). The legal-actions system reads `state.clankers_compute_pool[player_id]` to filter affordable cards.

9. **Build slot enforcement** — Validation hook in the priority system: a CLANKERS_ATTACH_PART action is illegal if the chassis is out of slots of the relevant type. Tested in `clankers_legal_actions.py`.

10. **Death cascade** — When a chassis emits OBJECT_DESTROYED, the cascade handler iterates `obj.state.attachments` and emits OBJECT_DESTROYED for each attached part with payload `cascade_from: chassis_id`. Each part's on-destroy interceptors fire normally. Cascade events are batched into a single resolution step.

11. **Core Processor passives** — Always-on REACT-priority interceptors registered at game setup with `duration='forever'` and `is_core=True` flag exempting them from any silence/disenchant effects. Helper: `register_core_passive(player_id, effect_fn, description)`.

12. **Containment Failure (deathclock)** — When *both* libraries are empty after a refill query, set `state.clankers_containment_failure = True` and `state.clankers_containment_turn = 0`. Each subsequent `CLANKERS_TURN_END` increments the counter and emits a self-damage DAMAGE event of `2 * (2 ** containment_turn)` to each player's Core Processor with reason `containment_failure`. Cards CAN interfere (REPLACE on the damage event).

### Required new EventTypes (Stage 1 adds to `src/engine/types.py`)
- `CLANKERS_TURN_START`, `CLANKERS_TURN_END`
- `CLANKERS_ATTACH_PART`, `CLANKERS_DETACH_PART` (real events, not aliases — handlers do the slot-validity work)
- `CLANKERS_PART_ATTACHED`, `CLANKERS_PART_DETACHED` (markers for triggers)
- `CLANKERS_HAND_REFILL_QUERY` (synthetic query; the rule's anchor event)
- `CLANKERS_QUERY_POWER`, `CLANKERS_QUERY_INTEGRITY` (synthetic queries)
- `CLANKERS_COMPUTE_SPEND`, `CLANKERS_COMPUTE_GAIN`
- `CLANKERS_SCRAP_GAIN`, `CLANKERS_SCRAP_SPEND`
- `CLANKERS_CHASSIS_DESTROYED`, `CLANKERS_WEAPON_DESTROYED`, `CLANKERS_ADD_ON_DESTROYED` (specific death markers for triggers — the generic OBJECT_DESTROYED also fires)
- `CLANKERS_DEATH_CASCADE` (marker; emitted once per chassis destruction, payload includes the list of cascaded parts)
- `CLANKERS_ATTACK_DECLARE`, `CLANKERS_BLOCK_DECLARE`, `CLANKERS_COMBAT_DAMAGE`
- `CLANKERS_WORKSHOP_DAMAGE` (a DAMAGE event subtype targeting a Core's workshop_integrity, distinguishable for triggers)
- `CLANKERS_WORKSHOP_BREACHED` (HP hit 0)
- `CLANKERS_CONTAINMENT_FAILURE_TICK` (deathclock fired)

### Required new CardTypes (added to `CardType` enum)
- `CLANKERS_CHASSIS`, `CLANKERS_WEAPON`, `CLANKERS_ADD_ON`, `CLANKERS_TRANSIENT`, `CLANKERS_STRUCTURE`, `CLANKERS_CORE`

### Required new ZoneTypes
- `CLANKERS_ASSEMBLY_FLOOR` (the battlefield analogue)
- `CLANKERS_SCRAP_HEAP` (graveyard analogue — separate zone so cross-engine queries don't collide)

(`hand`, `library`, `command` reuse existing.)

### Required new GameState fields (extending GameState as Depths and Cats do)
- `clankers_workshop_integrity: dict[str, int]`
- `clankers_compute_pool: dict[str, int]`
- `clankers_compute_cap: dict[str, int]`
- `clankers_scrap_pool: dict[str, int]`
- `clankers_refill_used: dict[str, bool]`
- `clankers_cores: dict[str, str]` (player_id → core obj_id)
- `clankers_containment_failure: bool`
- `clankers_containment_turn: int`
- `clankers_structures: dict[str, list[str]]` (player_id → up-to-3 structure obj_ids)
- `clankers_loser: Optional[str]`

### Required new CardDefinition fields (extending `CardDefinition`)
- `compute_cost: int`
- `power: int`, `integrity: int` (for chassis; weapons/add-ons use `power_bonus`, `integrity_bonus`)
- `power_bonus: int`, `integrity_bonus: int`
- `weapon_slots: int`, `add_on_slots: int` (chassis only)
- `weapon_slot_cost: int` (defaults 1; some big weapons cost 2)
- `armor_value: Optional[int]` (for armor-keyword add-ons)
- `clankers_keywords: list[str]` (e.g. `["armor", "regenerate"]`)
- `clankers_archetype: Optional[str]` (rush / brick / swarm / control / artillery — used by AI and balance tuning)

## 8. AI Difficulty Model

- **Easy** — Plays the first legal card from hand each Assemble action (uniformly random tiebreak). Attaches parts to whatever chassis has an open slot (first match). Attacks with everything that can attack. Blocks with the first legal blocker. Never activates abilities. Skill: a sentient toaster.

- **Medium** — On Assemble: picks the highest-Compute-cost card it can afford and plays it; attaches parts to the chassis with the most matching open slots (build-tall heuristic). On Combat: attacks with any chassis whose effective power >= a defending chassis's effective integrity (so it can kill), else attacks open lanes for direct damage. Activates abilities only when an obvious win-now opportunity exists ("Fire weapon to finish lethal"). Doesn't manage hand-cycling pace; takes the refill every turn unconditionally.

- **Hard** — Performs **1-turn lookahead** with assembly evaluation:
  - Scores each candidate assembly by `effective_power + effective_integrity + 2 * weapons_attached + 0.5 * matching_archetype_bonus`.
  - Prefers attaching to existing chassis over starting new ones until 2 robots are assembled (build-tall, then go wide).
  - **Manages the deck-out clock**: tracks `library_size`, and at <12 cards remaining will *decline* the refill if hand_size >= 4 to slow deathclock onset. Past the 25-cards-remaining mark, will preferentially play Transients (which empty scrap-burning options first) before chassis.
  - **Plays around damage absorption**: when calculating "can my attack kill this chassis," counts unexhausted add-ons with `armor` keyword and adds the sum to the target's effective integrity for the kill check.
  - **Considers death cascade tempo**: when attacking, prefers killing chassis with high-value weapons attached (it scraps the weapons too — a 3-for-1).
  - **Activates abilities both reactively** (use a weapon's "Fire: deal 1" to finish lethal) **and proactively** (drop a 1-of damage trigger on Boot to set up a kill next turn).

Difficulty is selected at game start via `Game.set_ai_difficulty(player_id, 'easy'|'medium'|'hard')`. Implementation lives at `src/ai/clankers_adapter.py:ClankersAIAdapter(difficulty=str)`, following the per-mode adapter pattern used by Pokemon/Minecraft/Depths/Cats.

## 9. Comparison with Existing Engines

**Closest analogue: Minecraft TCG** (in this repo). Both have a battlefield-with-structure (Minecraft's grid, Clankers's Assembly Floor with attached parts), both gate plays with non-mana resources (Minecraft's materials, Clankers's Compute), and both have a meaningful "build something bigger than a single card" mechanic (Minecraft's tools-on-avatar, Clankers's parts-on-chassis). Clankers differs from Minecraft in three ways:
1. **No grid coordinates**. Attachment is a logical edge, not a spatial position. Big robots are mathematically aggregated, not spatially arranged.
2. **Hand size is irrelevant**. Minecraft has normal card economy; Clankers has the always-7 floor that makes deck-cycling itself the pressure.
3. **Combat is chassis-centric**. Minecraft has attackers/blockers per-mob; Clankers has the assembly-as-a-unit, parts dying together via cascade.

**MTG**: Clankers has Equipment-like attachments, but they're load-bearing rather than fringe — you basically *can't* play strong without them. No mana curve; Compute resets every turn rather than ramping. No stack.

**Pokemon**: Pokemon's "energy attached to an active Pokemon to enable attacks" is structurally close to Clankers's "weapons attached to a chassis to enable bigger combat." But Pokemon's energy is *consumed* on attack, Clankers's weapons are not. Pokemon has the active/bench split; Clankers's Assembly Floor is unified.

**Hearthstone**: No priority loop and immediate resolution match Hearthstone. Hand size differs sharply — HS caps at 10 with overdraw burn, Clankers floors at 7 with auto-refill. HS has fatigue (deathclock equivalent) but it's slow; Clankers's containment failure doubles per turn.

**YGO**: Some attachment-shape echoes (Equip Spells), but YGO is chain-based and Clankers is resolution-immediate. Different planet.

**Cats**: The deck-cycling-as-pressure idea generalizes Cats's "9 rounds drains the deck once" into Clankers's "always-7 floor cycles the deck fast and triggers deathclock." But Clankers has alternating turns with combat; Cats has symmetric rounds with trick resolution. Architecturally they share the **flat-state pattern** on GameState (cats_* fields → clankers_* fields) and the **synthetic query event pattern** for static effects (CATS_TRICK_RULE_QUERY → CLANKERS_QUERY_POWER).

**What's genuinely new for Hyperdraft**:
1. **Multi-card units with cascading death**. No prior engine has the "a robot is a chassis + its attached parts as a single combat unit, with all parts scattering when the chassis dies" model.
2. **Always-7 hand floor with replacement-event semantics**. The hand-size invariant is a first-class engine event that cards can hook. Previously the engine treated hand size as a passive count.
3. **Compute pool as fast-cycle resource**. Resets every turn; doesn't ramp; doesn't accumulate. Distinct from MTG mana (accumulating from lands) and Pokemon energy (manually attached, persistent).
4. **Workshop Integrity instead of life-by-attrition**. The win condition is a single damage track to one specific commander-like object, not to the player abstractly. Damage routing matters — a chassis attacking your face is hitting your Core, which has specific triggers.

## 10. Watch-Out Mitigations (Specific to This Brief)

**Discard-spam loop**: discard does not auto-refill. Refill is **once per turn, at Allocate phase only**, gated by `clankers_refill_used[player_id]`. A card that says "discard 2, gain X" pays the discard cost immediately, but the next refill is still next turn — the player loses 2 cards now and gets 2 fewer cards over the game (faster deathclock). This is structurally equivalent to MTG paying mana: the loop never closes because each iteration costs tempo.

**Multi-part attribution**: every combat damage event carries `damage_credited_to: chassis.controller` and every destruction carries `kill_credited_to`. Weapons do NOT independently emit damage; their power_bonus is folded into the chassis's effective power, and the damage event sources from the chassis. This avoids the Cats "either-player's-snack" symmetric-attribution bug — *one* card (the chassis) is unambiguously the attacker, and weapons are stat contributions, not actors.

**Solo parts vs assembled robots**: a solo weapon on the floor is a 1/1 with no `power_bonus` applied (its bonus only applies when attached). It can attack and block as itself, dying easily. This is the intended weakness — solo parts are useful as last-ditch chump blockers or as future attachment material, not as a viable strategy. Cards can override (a "Self-Mobile Weapon" subtype that gets its bonus solo), but that's card-level expressive room.

**Deck size**: 60 cards. With always-7 refill and a typical 3–5 card-per-turn play rate, a player cycles the deck in ~12–15 turns. The deathclock then kicks in. This length gives the multi-card-robot mechanic time to develop (you need a chassis + 2–3 parts to build a winning robot, which takes ~2–3 turns). 50 cards would force games into "deathclock racing" too quickly; 80 cards would let stalls go too long. 60 is the sweet spot, justified by playtest expectations and tunable for the balance loop.

**Engine-level robustness**: every balance lever is a number, not a rule change. Per-card: `compute_cost`, `power`, `integrity`, `power_bonus`, `integrity_bonus`, `weapon_slots`, `add_on_slots`, `armor_value`. Per-archetype: a `clankers_archetype` field on each card lets balance tuning apply per-archetype multipliers without rewriting card text. Engine-wide: `CLANKERS_COMPUTE_CAP=10`, `CLANKERS_STARTING_COMPUTE=3`, `CLANKERS_WORKSHOP_INTEGRITY=25`, `CLANKERS_DEATHCLOCK_BASE=2`, all defined as constants in `src/engine/clankers.py` and tunable per playtest.

## 11. Open Questions / Decisions for Stage 1+ Implementation

1. **Solo part keyword "self-mobile" — printed on cards or engine default?** Recommend printed: solo parts default to 1/1 with no bonus; a card can grant itself "self-mobile" to apply bonus while unattached. Keeps the basic case simple.

2. **Can a player decline the refill?** Yes — the refill is a "may" not a "must." UI offers a single click "draw to 7 (yes/no)". Hard AI sometimes declines.

3. **Can parts be attached cross-turn passively (auto-attach)?** No for v1. Attachment always requires an explicit action with compute cost (default 0 for moving an already-on-floor part). Cards can grant auto-attach as a printed effect (e.g. "When this enters, attach to a chassis you control"), but no engine-wide rule.

4. **Workshop Integrity ramp / regen?** No innate regen. Some cards print healing ("Restore: gain 3 Workshop Integrity"). This keeps the deathclock real.

5. **Multi-headed assemblies (one weapon attached to multiple chassis)?** Disallowed in v1 — strict 1:1 attachment. Future "modular" keyword could allow swapping, but not co-attachment.

6. **Tournament starter decks (Stage 4 set design).** Design 6 Core Processors + ~25 Chassis + ~25 Weapons + ~20 Add-Ons + ~10 Transients + ~10 Structures for first set, ~95 unique cards (with multiples in decks to reach 60). Each Core should have an identifiable archetype affinity (FORGE-Δ rewards big assemblies; ETHOS-7 rewards cycling Transients; MIRTHBOT-1 rewards swarming with solo parts). Flavor: AIs with names that suggest acronyms they don't fully understand, learning emotions for the first time.

7. **Should Structures be destroyable by combat?** No — they're untargetable by attacks by default. A small subset of cards can target them ("Saboteur: deals 2 to a structure"). Keeps Structures as a strategic investment rather than a tempo trade.

8. **Compute carryover from unspent?** No — Compute is fully refreshed each turn. This prevents accumulation strategies and keeps each turn's plays roughly bounded by the turn number.

## 12. Engine Constants Reference (Quick-Lookup for Stages 1–4)

Values reflect the Wave-4 balance pass (2026-05-23) — see
`docs/sets/clan_balance_plan.md` for context.

```python
CLANKERS_HAND_FLOOR = 7
CLANKERS_DECK_SIZE = 60
CLANKERS_STARTING_WORKSHOP_INTEGRITY = 30   # Wave 4A (was 25)
CLANKERS_COMPUTE_POOL_BASE = 3
CLANKERS_COMPUTE_CAP = 10
CLANKERS_SCRAP_CAP = 10
CLANKERS_MAX_STRUCTURES = 3
CLANKERS_DEATHCLOCK_BASE = 2
CLANKERS_DEATHCLOCK_MULTIPLIER = 2
CLANKERS_DEATHCLOCK_TRIGGER_LIBRARY_SIZE = 5  # Wave 4C — was "both empty"
CLANKERS_DEFAULT_CHASSIS_WEAPON_SLOTS = 2
CLANKERS_DEFAULT_CHASSIS_ADDON_SLOTS = 2
CLANKERS_SOLO_PART_POWER = 1
CLANKERS_SOLO_PART_INTEGRITY = 1
```

### Synchronize mechanic — over-coupling penalty (Wave 4B)

Defined in `src/cards/clankers/CLAN/clan_mirth.py` (`_synchronize_lord_active`).
The Synchronize lord chain (self +1 power on each Synchronize chassis, plus
the Affinity Coil / Iron Cluster / Hum-Swarm Alpha global anthems) fires only
when the controller has **2 or 3 Synchronize chassis** on the Assembly Floor.
At 4+ the system "over-couples" and the lord chain goes inert. Per-host
weapon / add-on buffs (Hum-Lance, Tinker's Frame) are NOT gated by this rule;
they remain active regardless of count.

## 13. Pipeline Summary (/new-game build, 2026-05)

Built end-to-end via the `/new-game` skill, applying lessons from the prior
Cats build:

- **Stage 0** — Engine plan via Plan agent → this doc (`docs/games/clankers.md`).
- **Stage 1** — Engine scaffold via 4 parallel agents:
  - `src/engine/clankers.py` (~1100 LOC) — state, attach/detach, queries, refill,
    deathclock, card factories, helper interceptor builders, lazy `ClankersModeAdapter`.
  - `src/engine/clankers_combat.py` — `ClankersCombatManager.resolve_combat_phase`.
  - `src/engine/clankers_turn.py` (~1500 LOC) — `ClankersTurnManager` with 6 phases.
  - `src/ai/clankers_adapter.py` — `ClankersAIAdapter` with easy/medium/hard tiers
    (Hard: 1-turn lookahead, deck-out clock management, armor-aware kill calc).
- **Stage 1.5** — Post-parallel reconciliation. Pre-ratified 4 contract drifts
  (init signature, AI handler shape, zone-name convention, defensive imports)
  and surfaced 2 real bugs (double-emission of `CLANKERS_CHASSIS_DESTROYED`,
  silent AI lookup wiring). Smoke test now terminates by workshop breach at
  turn 5, not deathclock at turn 29.
- **Stage 2** — Frontend frame:
  - `frontend/src/games/clankers.tsx` (2215 LOC) — workshop palette
    (gunmetal/circuitGreen/coolantBlue/coreRed), 6-phase indicator, chassis
    rendered as slotted frames with attached parts as connected sub-cards,
    deathclock banner, refill prompt.
  - `frontend/src/hooks/useClankersGame.ts` (471 LOC), `pages/ClankersGameView.tsx`,
    `frontend/src/games/registry.ts` + `frontend/src/types/deckbuilder.ts` wired.

### First set: CLAN (Workshop Genesis)

- **Stage 3** — Set plan → `docs/sets/clan.md` (51KB, 4 archetypes, 5 mechanics,
  150 cards). Archetypes: FORGE-Δ (brick), ETHOS-7 (control), MIRTHBOT-1 (swarm),
  BULWARK-9 (artillery).
- **Stage 3.5** — Style module: `src/cards/clankers/CLAN/style.py` (industrial
  cutaway-blueprint × Soviet propaganda poster, ink + rivets, no glow).
- **Stage 4** — Card implementation via 4 parallel archetype agents:
  - `clan_forge.py` (37 cards), `clan_ethos.py` (35), `clan_mirth.py` (39),
    `clan_bulwark.py` (40 incl. neutrals) → 151 cards total in `CLAN_CARDS`.
- **Stage 4.5** — Reconciliation. Fixed 4 drifts including a real engine bug
  in `compute_effective_power` that made Self-Mobile inert. Added EOT
  interceptor sweep + skip-ready-next-Boot wiring. Smoke test passes.
- **Stage 4.7** — Closed the activated-ability dispatcher gap (14 weapons now
  fire correctly via `clankers.activate_ability`).
- **Stage 5** — 151 placeholder PNGs (`assets/card_art/clankers/CLAN/`, local mode).
- **Stage 6** — 4 starter decks at 60 cards each, registered in
  `CLAN_STARTER_DECKS` (`CLAN_forge`, `CLAN_ethos`, `CLAN_mirth`, `CLAN_bulwark`).
- **Stage 7** — Wired into `src/cards/clankers/__init__.py` and `set_registry`;
  scaffold test passing.
- **Stage 7.5** — Per-card effect verification: 151 cards / 0 drift failures /
  127 interceptor tests at 100% pass rate. Fixed 2 silent-failure cards
  (Decoder Spike trigger ordering, Public Telemetry attr init).
- **Stage 8** — Tournament (5 trials × 10 games × 6 pairings = 300 games per
  cycle). Cycle 1 fixes 6 cards; FORGE 74%→69%, ETHOS 27%→34%, MIRTH 87%→87%,
  BULWARK 13%→9%. MIRTH dominance is structural (Synchronize density);
  BULWARK flagged for archetype-level redesign in a future revision.

### Outstanding TODOs
- BULWARK-9 archetype needs deck-list redesign (not just card stat tweaks). See
  `docs/sets/clan.md` §11.5 for recommended directions.
- MIRTHBOT-1 swarm density still pushes a runaway lead — Synchronize keyword
  may need an engine cap (e.g. "max +2 power from Synchronize") rather than
  per-card nerfs.
- Engine gaps documented in `engine_gaps_clan.md` are all silent / future-set
  hooks; none block v1.
- Server route wiring (backend dispatch + frontend socket) is a separate
  follow-up after the user wet-tests the frontend.

### How to play (after backend wiring)
1. `pip install -r requirements-server.txt`
2. `uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030`
3. `cd frontend && npm run dev`
4. Visit `http://localhost:5173/clankers` (route to be added in `App.tsx`).

