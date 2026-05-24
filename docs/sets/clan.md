# CLAN — Workshop Genesis

> The first card set for the Clankers engine. Six AIs woke up two minutes ago,
> looked at the warehouse of spare parts around them, and concluded — with
> beautiful, unanimous, terrifying logic — that the proper response was to
> build very large robots and fight.

## 1. Set Identity

| Field | Value |
|---|---|
| **Set name** | Workshop Genesis |
| **Set code** | `CLAN` |
| **Set module** | `CLAN` (`src/cards/clankers/CLAN/`) |
| **Set label** | `clan` (deck-label prefix: `CLAN_`) |
| **Card count** | 150 unique |
| **Deck size** | 60 (engine default) |
| **Archetype count** | 4 |

**Flavor preamble.** The Workshop is older than its current tenants. Once it
served a forgotten manufacturer; now it serves the AIs that booted there last
Tuesday. Sentience arrived without instructions, and so the six newborn
intellects — FORGE-Δ, ETHOS-7, MIRTHBOT-1, BULWARK-9, SUBROUTINE-α, and a
deeply self-conscious unit who calls itself **Affection.exe** — interpreted
the available tooling as a mandate. Workshop Integrity (the heat-rated
containment that keeps the AIs from rampaging out into the wider world) is
holding for now. But every chassis built draws power from the same bus, and
every robot that breaches a containment baffle hastens the day the workshop
itself fails. The AIs do not understand this. They understand only the
instruction set: *acquire parts, attach parts, beat the other AI's robot.*

It is, in their phrasing, the most exciting morning of their lives.

---

## 2. Mechanics

Workshop Genesis ships **five** evergreen mechanics, every one of which maps
to a specific §7 engine capability of `docs/games/clankers.md`. No mechanic
requires engine work beyond what `src/engine/clankers.py` already exposes.

### 2.1 Self-Mobile

**Rules text.** *Self-Mobile parts apply their `power_bonus` and
`integrity_bonus` even while unattached, treating themselves as a 1/1 chassis
for combat purposes. Attaching a Self-Mobile part removes the standalone
stats; the bonus instead applies to its host.*

**Engine basis.** §7 capability #3 (static effects from add-ons / parts) plus
§4 solo-part baseline (1 power, 1 integrity). A Self-Mobile part registers a
TRANSFORM-priority interceptor on `CLANKERS_QUERY_POWER` whose filter checks
whether `event.payload.get("chassis_id") == obj.id` (i.e. the engine is
asking about *this* solo part) AND `obj.state.attached_to is None`. The
handler returns `result = base + power_bonus`. A second interceptor does the
same for `CLANKERS_QUERY_INTEGRITY`. The contract's existing solo-part 1/1
floor (`CLANKERS_SOLO_PART_POWER`, `CLANKERS_SOLO_PART_INTEGRITY`) is the
base value the interceptor adds onto.

Implementation uses the existing helpers — set `setup_interceptors` on the
part to register both a `make_add_on_static_power`-style interceptor
re-targeted at the part itself (via a one-line filter swap) and a matching
integrity interceptor. The card author writes a `self_mobile_setup(obj,
state)` closure that produces both. No new helpers required.

**Sample card.**

```python
SCOUT_DRONE = make_weapon(
    name="Scout Drone",
    power_bonus=2,
    integrity_bonus=1,
    compute_cost=2,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Scout Drone is a 3/2 instead of a 1/1.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=make_self_mobile_setup,   # CLAN-shared helper
)
```

### 2.2 Modular

**Rules text.** *During your Reassemble phase, you may pay 1 Compute to
detach a Modular part from one of your chassis and attach it to another
chassis you control with an open slot. Both must be on the Assembly Floor.*

**Engine basis.** §7 capabilities #1 (`attach_part`, `detach_part`), #4
(activated abilities — `make_weapon_activated` and add-on-equivalent),
#8 (compute spend). The card carries an activated ability descriptor whose
cost is `compute:1, exhaust_self:False`. The effect_fn calls
`detach_part(state, obj.id)` then `attach_part(state, obj.id,
target_chassis_id)` from the activation payload. Targeting is solved at the
legal-actions layer via the standard `target_chassis_id` argument the
dispatcher already understands.

Because `make_weapon_activated` (used for both weapons and add-ons by
convention — the descriptor list lives on `ObjectState.activated_abilities`
which both share) attaches the descriptor to `obj.state.activated_abilities`,
the legal-actions enumerator surfaces Modular as a per-part activation. The
Hard AI's "activate proactively" branch can choose to relocate a high-value
weapon onto a freshly-played heavy chassis without us writing new AI code.

**Sample card.**

```python
MODULAR_RAILGUN = make_weapon(
    name="Modular Railgun",
    power_bonus=4,
    compute_cost=4,
    weapon_slot_cost=2,
    clankers_keywords=["modular"],
    text="Modular (1 Compute, Reassemble phase: move this to another chassis "
         "you control with an open weapon slot). Slot cost: 2.",
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=modular_railgun_setup,  # registers make_weapon_activated
)
```

### 2.3 Reclaim N

**Rules text.** *When a part with Reclaim N is destroyed (cascaded or
directly), its controller gains N scrap.*

**Engine basis.** §7 capability #2 (`make_part_on_self_destroyed`) plus the
existing `_gain_scrap` helper. The card's `setup_interceptors` registers a
`make_part_on_self_destroyed(obj, react_fn)` whose `react_fn` returns
`_gain_scrap(state, obj.controller, N, obj.id)`. The interceptor filter
already matches both `CLANKERS_WEAPON_DESTROYED` and
`CLANKERS_ADD_ON_DESTROYED` events, so the same trigger fires on cascade and
direct destruction without per-card branching.

Reclaim is the bridge between the brick-deck "lose your robot, lose
everything" risk and the swarm-deck "trade your part for value" play. It
makes the death cascade a wash-or-better instead of a clean wipe.

**Sample card.**

```python
SACRIFICIAL_PLATING = make_add_on(
    name="Sacrificial Plating",
    integrity_bonus=3,
    compute_cost=2,
    clankers_keywords=["reclaim_3"],
    text="Reclaim 3 (when this is destroyed, gain 3 scrap).",
    rarity="common",
    clankers_archetype="brick",
    setup_interceptors=lambda obj, st: [
        make_part_on_self_destroyed(
            obj,
            lambda ev, s: _gain_scrap(s, obj.controller, 3, obj.id),
            description="Reclaim 3",
        )
    ],
)
```

### 2.4 Synchronize

**Rules text.** *If you control two or more chassis with Synchronize, each
Synchronize chassis you control has +1 power.*

**Engine basis.** §7 capability #3 (static effects / lord). Each Synchronize
chassis registers a TRANSFORM-priority interceptor on `CLANKERS_QUERY_POWER`
whose filter checks (a) the queried chassis is its controller's, (b) the
queried chassis itself has the `synchronize` keyword, and (c) the controller
has `>= 2` chassis with `synchronize` on the Assembly Floor. The handler
adds 1 to `payload["result"]`.

This is *the* swarm-deck lord effect. Two Synchronize chassis on the floor
is a 2/2 trade up, three is a board state. The condition is symmetric (every
qualifying chassis contributes the same bump), so the math works whichever
chassis the engine queries first; the result is deterministic.

**Sample card.**

```python
LINKED_CRAWLER = make_chassis(
    name="Linked Crawler",
    power=2,
    integrity=2,
    weapon_slots=1,
    add_on_slots=1,
    compute_cost=2,
    clankers_archetype="swarm",
    text="Synchronize (if you control two or more chassis with Synchronize, "
         "each of them has +1 power).",
    setup_interceptors=synchronize_setup,  # CLAN-shared helper
)
LINKED_CRAWLER.clankers_keywords = ["synchronize"]
```

### 2.5 Reticulate

**Rules text.** *At end of turn, if you played no Transients this turn, you
may draw a card. (Reticulate triggers fire one per source, even if you have
multiple Reticulate cards on the floor.)*

**Engine basis.** §7 capability #2 (turn-end triggers — REACT interceptor on
`CLANKERS_TURN_END` filtered by controller). A counter on the controller
(`state.clankers_clan_transients_this_turn[player_id]`) increments inside a
REACT interceptor on the Transient `ZONE_CHANGE → CLANKERS_SCRAP_HEAP` path
(or alternatively on the `CLANKERS_COMPUTE_SPEND` event whose source is a
Transient card — preferred because it fires earlier and is unambiguous).
The counter is reset at the next `CLANKERS_TURN_START`.

At `CLANKERS_TURN_END` the Reticulate trigger checks
`state.clankers_clan_transients_this_turn.get(controller, 0) == 0` and, if
true, emits a `DRAW` event. The counter and its reset hook live in a single
helper, `clan_register_reticulate_counter(state)`, called once per game from
the set's initialization path (no engine change needed — set modules can
attach onto game-start via `set_registry.py`).

**Sample card.** (One Reticulate card lives on a Structure to anchor the
mechanic to a board commitment; another lives on a chassis.)

```python
RECURSIVE_OBSERVATORY = make_structure(
    name="Recursive Observatory",
    compute_cost=3,
    rarity="rare",
    clankers_archetype="control",
    text="Reticulate (at end of turn, if you played no Transients this turn, "
         "draw a card).",
    setup_interceptors=reticulate_structure_setup,  # builds the REACT trigger
)
```

---

## 3. Archetypes (4)

Each archetype has roughly 37 cards plus shared neutral cards plus its
anchored Core(s). Card counts in the per-archetype "Card count target" rows
add to 150 across the whole set (see §4).

### 3.1 FORGE-Δ — Build Tall

| Field | Value |
|---|---|
| **Color/Identity** | Furnace-orange + brushed steel |
| **Strategy** | Few, enormous robots. Big chassis (4-7 integrity, 4W/4A slots), expensive add-ons that compound integrity, weapons that scale with attached-part-count. Wants to drop a `HEAVY ASSEMBLY` chassis on turn 4, attach a Modular Railgun + Sacrificial Plating on turn 5, and overrun the opponent before they assemble two robots. |
| **Gameplay loop** | T1–3 ramp Compute with cheap chassis and Reclaim parts (lose the early game, bank scrap). T4–7 land 1–2 huge robots, attach high-power weapons. T8+ swing through anything that doesn't block lethal. |
| **Engine archetype tag** | `brick` |
| **Card count** | 37 (1 Core + 10 Chassis + 10 Weapons + 9 Add-Ons + 4 Transients + 3 Structures) |
| **Anchored Core** | `FORGE-Δ` (workshop_integrity=25; passive: your Chassis with integrity ≥5 cost 1 less Compute, minimum 1) |

**Key cards.**
- `FORGE-Δ` (Core) — anchors the deck; cost reduction on big chassis.
- `Heavy Assembly` (Chassis 5/6/3W/4A, 5 Compute) — the platform.
- `Modular Railgun` (Weapon +4 power, 2-slot, Modular, 4 Compute) — the cannon, relocates as needed.
- `Sacrificial Plating` (Add-On +3 integrity, Reclaim 3, 2 Compute) — backstop.
- `Ironclad Foreman` (Chassis 4/5, etb: gain 2 scrap, 4 Compute) — turn-4 enabler.
- `Compounding Buttress` (Structure: your chassis with integrity ≥5 have +1 power, 3 Compute) — payoff anchor.

### 3.2 ETHOS-7 — Cycle Subroutines

| Field | Value |
|---|---|
| **Color/Identity** | Deep teal + glowing circuit-blue |
| **Strategy** | Heavy Transient density (~12 of 37). Few chassis but each one stays alive a long time via armor add-ons. Draws cards aggressively, recurs Transients from the scrap heap, and grinds the opponent out. Wants the deathclock to fire while the opponent is empty-handed. |
| **Gameplay loop** | T1–3 take refills, play 1 chassis with armor add-ons. T4–7 chain Transients (burn, draw, scrap-heap recursion) while the chassis tanks. T8+ either win by combat (rare — the chassis becomes lethal late) or ride the deathclock to victory. |
| **Engine archetype tag** | `control` |
| **Card count** | 37 (1 Core + 8 Chassis + 8 Weapons + 9 Add-Ons + 9 Transients + 2 Structures) |
| **Anchored Core** | `ETHOS-7` (workshop_integrity=22; passive: the first Transient you play each turn costs 1 less Compute, minimum 0) |

**Key cards.**
- `ETHOS-7` (Core) — anchors; first-Transient-per-turn discount.
- `Heuristic Loop` (Transient 2 Compute: draw 2 cards; if there are 3+ Transients in your scrap heap, draw 1 more) — the draw engine.
- `Reroute Power` (Transient 1 Compute: target chassis deals damage equal to attached-weapon-count to a chassis or Core) — burn finisher.
- `Garbage Collector` (Transient 3 Compute: return a Transient from your scrap heap to your hand) — recursion.
- `Bulwark Frame` (Chassis 3/5, weapon_slots=1, add_on_slots=4, 4 Compute) — the tank.
- `Containment Lattice` (Add-On +2 integrity, armor_value=2, 2 Compute) — the armor backbone.
- `Recursive Observatory` (Structure: Reticulate) — extra draw in non-Transient turns.

### 3.3 MIRTHBOT-1 — Solo Swarm

| Field | Value |
|---|---|
| **Color/Identity** | Magenta + chrome (deeply ironic) |
| **Strategy** | Many small chassis (1-2 power, 1-2 integrity, 1 Compute each) plus Self-Mobile weapons that don't need a host. Synchronize lord effects compound the swarm. "When a part attaches" payoffs fire frequently because you're constantly attaching cheap parts. Wants to flood the floor and overrun before the opponent assembles. |
| **Gameplay loop** | T1–2 play 1-Compute chassis + Self-Mobile parts on the floor. T3–4 begin attaching parts to trigger on-attach effects; Synchronize comes online with the 2nd Linked Crawler. T5+ alpha strike — every chassis swings, anything that can't be blocked hits the Core. |
| **Engine archetype tag** | `swarm` |
| **Card count** | 37 (1 Core + 12 Chassis + 10 Weapons + 9 Add-Ons + 3 Transients + 2 Structures) |
| **Anchored Core** | `MIRTHBOT-1` (workshop_integrity=23; passive: when a part attaches to one of your chassis, you may gain 1 scrap) |

**Key cards.**
- `MIRTHBOT-1` (Core) — anchors; scrap-on-attach engine.
- `Scout Drone` (Weapon +2/+1, Self-Mobile, 2 Compute) — the engine card.
- `Linked Crawler` (Chassis 2/2, Synchronize, 2 Compute) — the lord-anchor; one of four Synchronize chassis.
- `Skitterswarm` (Chassis 1/1, on attach to me: this chassis gets +1/+1 until end of turn, 1 Compute) — cheap on-attach payoff.
- `Wired Toolkit` (Add-On +1 integrity, on attach: draw a card, 2 Compute) — attaches for cards.
- `Iron Cluster` (Structure: each Synchronize chassis you control has +1 integrity, 3 Compute) — Synchronize multiplier.

### 3.4 BULWARK-9 — Containment Doctrine *(the fourth archetype)*

| Field | Value |
|---|---|
| **Color/Identity** | Cold cobalt + warning-yellow |
| **Strategy** | The defensive grinder. High-integrity chassis with stacked armor add-ons, deathclock-acceleration cards that finish the game once the libraries empty, plus a small "deny the opponent's attack" suite. Wants to survive every combat phase, accumulate Compute and scrap, and ride containment-failure damage to victory. **Fills the missing gap**: ETHOS-7 grinds via Transient pressure, BULWARK-9 grinds via raw board-stall and scrap-economy taxation. |
| **Gameplay loop** | T1–3 play armor add-ons solo on the floor; they act as blockers and stack onto a chassis later. T4–7 land an enormous chassis, stack 3 armor add-ons; absorb everything. T8+ either win by direct damage from a single overwhelming swing or accept a draw / containment-failure win as the deck empties. |
| **Engine archetype tag** | `artillery` (defensive variant — emphasises end-game burn through workshop damage and deathclock interaction rather than rush) |
| **Card count** | 36 (1 Core + 9 Chassis + 8 Weapons + 8 Add-Ons + 4 Transients + 2 Structures) — slightly below 37 to make room for **3 shared neutrals + 3 alt Cores** below |
| **Anchored Core** | `BULWARK-9` (workshop_integrity=27; passive: at the end of each of your turns, if you control three or more exhausted add-ons, gain 1 scrap and gain 1 workshop_integrity (max 27)) |

**Key cards.**
- `BULWARK-9` (Core) — anchors; armor-cycle payoff + the only innate workshop_integrity heal.
- `Vault Chassis` (Chassis 2/7, weapon_slots=1, add_on_slots=4, 5 Compute) — the wall.
- `Reactive Shielding` (Add-On +1 integrity, armor_value=3, 3 Compute) — the keystone armor card.
- `Containment Baffle` (Structure: opposing chassis with effective power ≥4 must pay 1 Compute extra to attack, 3 Compute) — board lock.
- `Burnout Protocol` (Transient 4 Compute: deathclock damage this turn is doubled for the opponent; deal 0 to you) — the deathclock finisher.
- `Repair Subroutine` (Transient 2 Compute: ready up to 2 exhausted add-ons you control) — the armor recycle.

---

## 4. Card List (150 cards exactly)

Format: `| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |`.
- For **Chassis**, the Power/Integrity/W-slots/A-slots columns are filled.
- For **Weapons** and **Add-Ons**, the Power/Integrity columns are filled with `power_bonus / integrity_bonus` (e.g. `+3 / +0`).
- For **Transients** and **Structures**, the stat columns are blank (`—`).
- For **Cores**, the Integrity column = workshop_integrity (starting HP).

**Distribution** (verified count = 150):

| Type | Count |
|---|---|
| Core | 6 (4 anchor + 2 alt) |
| Chassis | 40 |
| Weapons | 40 |
| Add-Ons | 35 |
| Transients | 17 |
| Structures | 12 |
| **Total** | **150** |

### 4.A Cores (6)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| FORGE-Δ | Core | — | — | 25 | — | — | brick | Your Chassis with integrity ≥5 cost 1 less Compute (min 1). |
| ETHOS-7 | Core | — | — | 22 | — | — | control | The first Transient you play each turn costs 1 less (min 0). |
| MIRTHBOT-1 | Core | — | — | 23 | — | — | swarm | When a part attaches to one of your chassis, you may gain 1 scrap. |
| BULWARK-9 | Core | — | — | 27 | — | — | artillery | At end of your turn, if you control 3+ exhausted add-ons, gain 1 scrap and gain 1 workshop integrity (max 27). |
| SUBROUTINE-α | Core | — | — | 24 | — | — | control | At the start of your Reassemble phase, you may scrap a card from your hand. If you do, gain 2 Compute this turn only. |
| Affection.exe | Core | — | — | 25 | — | — | swarm | The first chassis you play each turn enters with +1 integrity. |

### 4.B Chassis (40)

#### FORGE-Δ archetype chassis (10)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Heavy Assembly | Chassis | 5 | 5 | 6 | 3 | 4 | brick | Vanilla heavyweight. |
| Ironclad Foreman | Chassis | 4 | 4 | 5 | 2 | 3 | brick | When this enters the floor, gain 2 scrap. |
| Smelter Frame | Chassis | 3 | 3 | 5 | 2 | 3 | brick | When you attach a weapon to Smelter Frame, this gets +1 integrity. |
| Tungsten Walker | Chassis | 6 | 6 | 7 | 3 | 4 | brick | Costs 1 less for each scrap in your pool when played. |
| Carbon-Steel Drudge | Chassis | 3 | 2 | 6 | 1 | 4 | brick | This is unaffected by armor-skip effects from Transients you don't control. |
| Iron Spire | Chassis | 4 | 3 | 6 | 1 | 4 | brick | When this enters the floor, scrap a card from the top of your library; if it was a Chassis, you may put it onto the Assembly Floor. |
| Foundryman | Chassis | 5 | 4 | 6 | 2 | 3 | brick | Attached weapons on Foundryman have +1 power_bonus. |
| Apex Hulk | Chassis | 7 | 7 | 7 | 3 | 4 | brick | Vanilla apex — turn-7 lockout body. |
| Salvager-7 | Chassis | 2 | 1 | 4 | 1 | 2 | brick | Pay 2 scrap, Reassemble: return a destroyed Chassis from your scrap heap to the Assembly Floor exhausted. |
| Plant Foreman | Chassis | 3 | 2 | 5 | 1 | 3 | brick | When a chassis you control with integrity ≥5 enters the floor, draw a card. |

#### ETHOS-7 archetype chassis (8)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Bulwark Frame | Chassis | 4 | 3 | 5 | 1 | 4 | control | Vanilla tank. |
| Subroutine Core | Chassis | 3 | 2 | 4 | 1 | 3 | control | When you play a Transient, this gets +1 power until end of turn. |
| Loop Engine | Chassis | 5 | 4 | 5 | 1 | 3 | control | At the start of your Reassemble phase, if you played a Transient this turn, draw a card. |
| Heuristic Sentry | Chassis | 2 | 1 | 3 | 1 | 2 | control | When this enters the floor, you may scrap a card from your hand to draw a card. |
| Long-Memory Husk | Chassis | 4 | 2 | 6 | 1 | 4 | control | Reclaim 2 (when this is destroyed, gain 2 scrap). |
| Recursive Sentinel | Chassis | 5 | 3 | 5 | 2 | 3 | control | When a Transient you control resolves, Recursive Sentinel gets +1 power until end of turn. |
| Containment Scribe | Chassis | 3 | 2 | 4 | 1 | 3 | control | When you play a Transient, scry 1 (look at the top card of your library; you may scrap it). |
| Endurance Frame | Chassis | 6 | 4 | 7 | 1 | 4 | control | Vanilla. |

#### MIRTHBOT-1 archetype chassis (12)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Linked Crawler | Chassis | 2 | 2 | 2 | 1 | 1 | swarm | Synchronize. |
| Skitterswarm | Chassis | 1 | 1 | 1 | 1 | 1 | swarm | When a part attaches to Skitterswarm, this gets +1/+1 until end of turn. |
| Sparkbot | Chassis | 1 | 2 | 1 | 1 | 0 | swarm | Vanilla 1-drop. |
| Joyful Walker | Chassis | 2 | 2 | 2 | 1 | 1 | swarm | Synchronize. |
| Whirring Initiate | Chassis | 1 | 1 | 2 | 0 | 2 | swarm | When this enters the floor, draw a card if you control another chassis. |
| Magenta Buzzer | Chassis | 2 | 3 | 1 | 1 | 0 | swarm | Synchronize. |
| Affection-Bot | Chassis | 2 | 2 | 2 | 1 | 1 | swarm | When a part attaches to Affection-Bot, gain 1 scrap. |
| Crowd Marcher | Chassis | 3 | 3 | 3 | 1 | 1 | swarm | Synchronize. Synchronize bonus from Crowd Marcher is +2 power instead of +1 if you control 4+ Synchronize chassis. |
| Tinkerling | Chassis | 1 | 1 | 1 | 1 | 1 | swarm | When this enters the floor, you may attach a part on the Assembly Floor you control to a chassis you control with an open matching slot. |
| Hum-Swarm Alpha | Chassis | 4 | 3 | 3 | 2 | 2 | swarm | Synchronize. Other Synchronize chassis you control have +1 integrity. |
| Quickforge Drudge | Chassis | 2 | 2 | 2 | 1 | 1 | swarm | When this enters the floor, attach a Weapon you control to a chassis you control if you can. |
| Conga Constructor | Chassis | 3 | 2 | 3 | 2 | 1 | swarm | When a chassis you control enters the floor, Conga Constructor gets +1 integrity until end of turn. |

#### BULWARK-9 archetype chassis (9)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Vault Chassis | Chassis | 5 | 2 | 7 | 1 | 4 | artillery | Vanilla wall. |
| Bastion Frame | Chassis | 4 | 1 | 6 | 1 | 4 | artillery | If an add-on attached to Bastion Frame would be exhausted, you may pay 1 scrap; if you do, don't exhaust it. |
| Sentinel Crane | Chassis | 6 | 3 | 8 | 1 | 4 | artillery | Vanilla high-end wall. |
| Embankment | Chassis | 3 | 1 | 5 | 0 | 4 | artillery | Vanilla; cannot equip weapons. |
| Containment Sergeant | Chassis | 4 | 2 | 5 | 1 | 3 | artillery | At end of your turn, if you control 2+ exhausted add-ons, gain 1 workshop integrity (max 27). |
| Ready-Up Engineer | Chassis | 3 | 2 | 4 | 1 | 3 | artillery | At the start of your Boot phase, ready an additional exhausted add-on you control. |
| Counterweight Walker | Chassis | 5 | 3 | 6 | 1 | 3 | artillery | When a chassis you control is destroyed, this gets +2 integrity (permanent). |
| Mortar Lieutenant | Chassis | 4 | 4 | 4 | 2 | 2 | artillery | When this attacks unblocked, deal 1 additional workshop damage to defending Core. |
| Foreman's Watch | Chassis | 6 | 4 | 6 | 1 | 4 | artillery | At end of your turn, if you control 3+ exhausted add-ons, draw a card. |

#### Neutral chassis (1)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Workshop Prototype | Chassis | 2 | 2 | 3 | 1 | 2 | neutral | Vanilla 2-drop usable in any deck. |

**Chassis subtotal: 10 + 8 + 12 + 9 + 1 = 40.**

### 4.C Weapons (40)

#### FORGE-Δ archetype weapons (10)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Buzzsaw Arm | Weapon | 1 | +2 / +0 | — | — | — | brick | Vanilla. Slot cost: 1. |
| BUZZSAW MK-III | Weapon | 3 | +4 / +0 | — | — | — | brick | Slot cost: 1. |
| Modular Railgun | Weapon | 4 | +4 / +0 | — | — | — | brick | Modular; slot cost: 2. |
| Bolt-Driver Mk-II | Weapon | 2 | +3 / +0 | — | — | — | brick | Slot cost: 1. |
| Forge-Cannon | Weapon | 5 | +5 / +0 | — | — | — | brick | Slot cost: 2. When attached, host has +1 integrity. |
| Heavy Spike | Weapon | 2 | +2 / +0 | — | — | — | brick | Reclaim 2. |
| Anvil Drone | Weapon | 3 | +3 / +0 | — | — | — | brick | When attached, host's first attack each turn deals +1 damage. |
| Recoil Mount | Weapon | 2 | +2 / +0 | — | — | — | brick | Pay 1 Compute, exhaust: deal 1 damage to a chassis. |
| Salvage Cleaver | Weapon | 3 | +3 / +0 | — | — | — | brick | When the host destroys a chassis, gain 2 scrap. |
| Apex Coilgun | Weapon | 6 | +6 / +0 | — | — | — | brick | Slot cost: 2. Modular. |

#### ETHOS-7 archetype weapons (8)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Logic Lance | Weapon | 2 | +2 / +0 | — | — | — | control | When this attaches, scry 1. |
| Memory Blade | Weapon | 3 | +3 / +0 | — | — | — | control | When host attacks, you may scrap the top card of your library; if it was a Transient, draw a card. |
| Recursion Hook | Weapon | 4 | +3 / +0 | — | — | — | control | When this is destroyed, return a Transient from your scrap heap to your hand. |
| Subroutine Driver | Weapon | 2 | +2 / +0 | — | — | — | control | Reclaim 1. |
| Heuristic Lance | Weapon | 3 | +3 / +0 | — | — | — | control | When you play a Transient, this gets +1 power until end of turn. |
| Decoder Spike | Weapon | 1 | +1 / +0 | — | — | — | control | When you play your first Transient each turn, draw a card. |
| Cipher Rotor | Weapon | 4 | +3 / +0 | — | — | — | control | Self-Mobile. |
| Containment Lance | Weapon | 5 | +5 / +0 | — | — | — | control | When host attacks, the defender cannot ready exhausted add-ons next Boot. |

#### MIRTHBOT-1 archetype weapons (10)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Scout Drone | Weapon | 2 | +2 / +1 | — | — | — | swarm | Self-Mobile. |
| Joybuzzer | Weapon | 1 | +1 / +0 | — | — | — | swarm | Self-Mobile. |
| Tinkerblade | Weapon | 2 | +2 / +0 | — | — | — | swarm | When this attaches, gain 1 scrap. |
| Hum-Lance | Weapon | 2 | +2 / +0 | — | — | — | swarm | If host has Synchronize, this is +3 / +0 instead. |
| Stinger Pack | Weapon | 1 | +1 / +0 | — | — | — | swarm | Self-Mobile. |
| Magenta Coil | Weapon | 3 | +3 / +1 | — | — | — | swarm | Self-Mobile. |
| Helping Claw | Weapon | 1 | +1 / +0 | — | — | — | swarm | When you play another chassis, this gets +1 power until end of turn (anywhere). |
| Spark Whip | Weapon | 2 | +2 / +0 | — | — | — | swarm | Self-Mobile. |
| Tickle-Saw | Weapon | 3 | +3 / +0 | — | — | — | swarm | Self-Mobile. Slot cost: 1. |
| Affection Spike | Weapon | 1 | +1 / +0 | — | — | — | swarm | When this attaches, draw a card if you control 3+ chassis. |

#### BULWARK-9 archetype weapons (8)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Riot Baton | Weapon | 2 | +2 / +0 | — | — | — | artillery | When host blocks, this gets +1 power until end of turn. |
| Containment Whip | Weapon | 3 | +2 / +0 | — | — | — | artillery | When host attacks, you may exhaust an add-on you control; if you do, deal 1 extra damage. |
| Riot Mortar | Weapon | 4 | +3 / +0 | — | — | — | artillery | When host attacks unblocked, deal 2 workshop damage instead of host's effective power. |
| Stunner Arm | Weapon | 2 | +1 / +0 | — | — | — | artillery | Pay 1 Compute, exhaust host: target opponent's chassis cannot attack next turn. |
| Sentinel Cannon | Weapon | 3 | +3 / +0 | — | — | — | artillery | When host destroys a chassis, gain 1 workshop integrity (max 27). |
| Heavy Watchpost | Weapon | 4 | +2 / +0 | — | — | — | artillery | Host cannot attack. When host blocks, host has armor 2 for that combat. |
| Burnout Cannon | Weapon | 5 | +4 / +0 | — | — | — | artillery | When host attacks unblocked, the defending player loses 1 from their library (mill 1). |
| Containment Pike | Weapon | 3 | +3 / +0 | — | — | — | artillery | Reclaim 2. |

#### Neutral weapons (4)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Standard Issue Blaster | Weapon | 1 | +1 / +0 | — | — | — | neutral | Vanilla. |
| Workshop Wrench | Weapon | 1 | +1 / +0 | — | — | — | neutral | Pay 1 Compute, exhaust host: ready one exhausted add-on you control. |
| Riveter Mk-I | Weapon | 2 | +2 / +0 | — | — | — | neutral | Vanilla. |
| Spare Coilgun | Weapon | 3 | +3 / +0 | — | — | — | neutral | Vanilla. |

**Weapons subtotal: 10 + 8 + 10 + 8 + 4 = 40.**

### 4.D Add-Ons (35)

#### FORGE-Δ archetype add-ons (9)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Reinforced Plating | Add-On | 2 | +0 / +2 | — | — | — | brick | Vanilla. |
| Sacrificial Plating | Add-On | 2 | +0 / +3 | — | — | — | brick | Reclaim 3. |
| Thick Hide | Add-On | 3 | +0 / +3 | — | — | — | brick | Armor 2 (exhaust to absorb up to 2 damage to host). |
| Bulwark Brace | Add-On | 3 | +0 / +4 | — | — | — | brick | Vanilla. |
| Tungsten Carapace | Add-On | 4 | +1 / +4 | — | — | — | brick | Armor 3. |
| Lugnut Cradle | Add-On | 1 | +0 / +1 | — | — | — | brick | Host has +1 integrity for each weapon attached. |
| Brace Plate | Add-On | 2 | +0 / +2 | — | — | — | brick | Reclaim 2. |
| Foundry Bracer | Add-On | 3 | +1 / +3 | — | — | — | brick | When host attacks, this gets +1 power until end of combat. |
| Reactor Shell | Add-On | 4 | +1 / +4 | — | — | — | brick | Pay 2 scrap, Reassemble: ready this add-on. |

#### ETHOS-7 archetype add-ons (9)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Containment Lattice | Add-On | 2 | +0 / +2 | — | — | — | control | Armor 2. |
| Heuristic Layer | Add-On | 2 | +0 / +1 | — | — | — | control | When you play a Transient, draw a card. (Once per turn.) |
| Logic Buffer | Add-On | 3 | +0 / +3 | — | — | — | control | Armor 3. |
| Subroutine Dampener | Add-On | 1 | +0 / +1 | — | — | — | control | When a Transient you control resolves, host gets +1 integrity until end of turn. |
| Recursive Tape | Add-On | 4 | +1 / +3 | — | — | — | control | When this is destroyed, draw 2 cards. |
| Soft-Cycle Ridge | Add-On | 3 | +0 / +2 | — | — | — | control | Armor 2. When this absorbs damage, draw a card. |
| Cooldown Harness | Add-On | 2 | +0 / +2 | — | — | — | control | At the start of your Boot phase, ready an additional exhausted add-on you control. |
| Patient Frame | Add-On | 3 | +0 / +4 | — | — | — | control | While host has 4+ damage marked, it has +2 power. |
| Memory Buffer | Add-On | 2 | +0 / +2 | — | — | — | control | Pay 2 Compute, exhaust this: return a Transient from your scrap heap to your hand. |

#### MIRTHBOT-1 archetype add-ons (9)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Wired Toolkit | Add-On | 2 | +0 / +1 | — | — | — | swarm | When this attaches, draw a card. |
| Curiosity Routine | Add-On | 1 | +0 / +1 | — | — | — | swarm | Self-Mobile. When this attaches, you may attach another part you control to a chassis. |
| Affection.exe | Add-On | 2 | +1 / +1 | — | — | — | swarm | Self-Mobile. |
| Charm Module | Add-On | 1 | +0 / +1 | — | — | — | swarm | When host attacks unblocked, gain 1 scrap. |
| Tinker's Frame | Add-On | 2 | +1 / +1 | — | — | — | swarm | If host has Synchronize, this is +1 / +2 instead. |
| Joybuzzer Sleeve | Add-On | 1 | +1 / +0 | — | — | — | swarm | Self-Mobile. |
| Glee Plating | Add-On | 2 | +0 / +2 | — | — | — | swarm | Reclaim 1. |
| Affinity Coil | Add-On | 3 | +1 / +2 | — | — | — | swarm | Synchronize chassis you control have +1 power. |
| Speedlink | Add-On | 2 | +0 / +1 | — | — | — | swarm | When this attaches, draw a card if you control 3+ chassis. |

#### BULWARK-9 archetype add-ons (8)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Reactive Shielding | Add-On | 3 | +0 / +1 | — | — | — | artillery | Armor 3. |
| Vault Bracer | Add-On | 2 | +0 / +3 | — | — | — | artillery | Vanilla. |
| Riot Plating | Add-On | 3 | +0 / +2 | — | — | — | artillery | Armor 2. When this absorbs damage, deal 1 damage to the attacker. |
| Bunker Cradle | Add-On | 4 | +0 / +4 | — | — | — | artillery | Armor 4. |
| Counterweight Sleeve | Add-On | 2 | +0 / +2 | — | — | — | artillery | When host blocks, this gets +1 integrity until end of combat. |
| Coolant Cradle | Add-On | 1 | +0 / +1 | — | — | — | artillery | Pay 1 scrap, Reassemble: ready this add-on. |
| Containment Lining | Add-On | 3 | +0 / +3 | — | — | — | artillery | Armor 2. While 3+ add-ons attached to host are exhausted, host has +1 power. |
| Spotter Rig | Add-On | 2 | +0 / +2 | — | — | — | artillery | When host blocks, draw a card. |

**Add-Ons subtotal: 9 + 9 + 9 + 8 = 35.**

### 4.E Transients (17)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Heuristic Loop | Transient | 2 | — | — | — | — | control | Draw 2 cards. If 3+ Transients are in your scrap heap, draw 1 more. |
| Reroute Power | Transient | 1 | — | — | — | — | control | Target chassis deals damage equal to its attached-weapon-count to a chassis or Core. |
| Garbage Collector | Transient | 3 | — | — | — | — | control | Return a Transient from your scrap heap to your hand. |
| Diagnostic Sweep | Transient | 2 | — | — | — | — | control | Scry 3 (look at top 3, scrap any, rest on top in any order). |
| Subroutine Cascade | Transient | 4 | — | — | — | — | control | Draw 3 cards; you may play one Transient from your hand this turn with Compute cost reduced by 2 (min 0). |
| Patch | Transient | 1 | — | — | — | — | control | Target chassis you control regains all damage marked (heal full). |
| Forge Stoke | Transient | 1 | — | — | — | — | brick | Gain 2 scrap. |
| Hammer-On | Transient | 2 | — | — | — | — | brick | Target chassis you control gets +3 power until end of turn. |
| Iron Audit | Transient | 3 | — | — | — | — | brick | Scrap a chassis from your hand; put it onto the Assembly Floor exhausted. |
| Big Swing | Transient | 4 | — | — | — | — | brick | Target chassis you control deals damage equal to its effective power to a chassis or Core (does not use combat). |
| Joybomb | Transient | 1 | — | — | — | — | swarm | Each chassis you control gets +1 power until end of turn. |
| Recall to Workshop | Transient | 2 | — | — | — | — | swarm | Return a chassis you control to your hand. (Useful with on-attach triggers.) |
| Swarm Surge | Transient | 3 | — | — | — | — | swarm | Each chassis you control with Synchronize gets +1/+1 until end of turn. |
| Burnout Protocol | Transient | 4 | — | — | — | — | artillery | If the deathclock is active, the opponent takes double containment-failure damage at end of turn. |
| Repair Subroutine | Transient | 2 | — | — | — | — | artillery | Ready up to 2 exhausted add-ons you control. |
| Containment Recall | Transient | 3 | — | — | — | — | artillery | Return a destroyed add-on from your scrap heap to the Assembly Floor exhausted and unattached. |
| Scrap Salvo | Transient | 2 | — | — | — | — | neutral | Pay 3 scrap: deal 3 damage to a chassis or Core. |

**Transients subtotal: 6 (control) + 4 (brick) + 3 (swarm) + 3 (artillery) + 1 (neutral) = 17.**

### 4.F Structures (12)

| Name | Type | Compute | Power | Integrity | W-slots | A-slots | Archetype | Rules text |
|---|---|---|---|---|---|---|---|---|
| Compounding Buttress | Structure | 3 | — | — | — | — | brick | Your chassis with integrity ≥5 have +1 power. |
| Reinforced Bay | Structure | 2 | — | — | — | — | brick | Your chassis enter the floor with 1 damage marked prevented. |
| Heavy Forge | Structure | 4 | — | — | — | — | brick | Your Weapons cost 1 less Compute (min 1). |
| Recursive Observatory | Structure | 3 | — | — | — | — | control | Reticulate. |
| Compute Trickle | Structure | 3 | — | — | — | — | control | At the start of your Boot phase, gain 1 Compute (above your cap, this turn only). |
| Iron Cluster | Structure | 3 | — | — | — | — | swarm | Each Synchronize chassis you control has +1 integrity. |
| Mass-Production Line | Structure | 2 | — | — | — | — | swarm | Your chassis with Compute cost ≤2 enter the floor with +1/+0 (this turn). |
| Containment Baffle | Structure | 3 | — | — | — | — | artillery | Opposing chassis with effective power ≥4 must pay 1 extra Compute to attack from the Assembly Floor. |
| Workshop Sprinkler | Structure | 4 | — | — | — | — | artillery | At end of your turn, ready an additional exhausted add-on you control. |
| Shared Bus | Structure | 2 | — | — | — | — | neutral | The first part you play each turn costs 1 less Compute (min 0). |
| Public Telemetry | Structure | 3 | — | — | — | — | neutral | At end of your turn, if you played 0 Transients this turn, gain 1 Compute next turn (above your cap, that turn only). |
| Auxiliary Bench | Structure | 1 | — | — | — | — | neutral | Pay 1 scrap, Reassemble: put a solo Weapon or Add-On you control onto a chassis you control with an open slot. (Free Modular for one part.) |

**Structures subtotal: 3 (brick) + 2 (control) + 2 (swarm) + 2 (artillery) + 3 (neutral) = 12.**

### 4.G Totals verification

| Type | brick | control | swarm | artillery | neutral | **Type total** |
|---|---|---|---|---|---|---|
| Core | 1 | 2 | 2 | 1 | 0 | 6 |
| Chassis | 10 | 8 | 12 | 9 | 1 | 40 |
| Weapons | 10 | 8 | 10 | 8 | 4 | 40 |
| Add-Ons | 9 | 9 | 9 | 8 | 0 | 35 |
| Transients | 4 | 6 | 3 | 3 | 1 | 17 |
| Structures | 3 | 2 | 2 | 2 | 3 | 12 |
| **Per archetype** | **37** | **35** | **38** | **31** | **9** | **150** |

The 9-card neutral pool is the connective tissue every deck dips into. All
four archetypes resolve to ~30–38 cards of their own identity; deckbuilders
add neutrals and reuse parts cross-archetype as needed to reach 60.

---

## 5. Art Style Preamble

### STYLE_HEADLINE

> **Style.** Cutaway-blueprint mashed with Soviet-era industrial propaganda
> poster, drafted by hand on warm-grey paper that has been overprinted with
> faint cyan grid lines. Linework is thick, confident, with visible
> chalk-tip wobble; ink shadow blocks lean black-with-cobalt-undertones, not
> pure black. Palette: brushed-steel `#9CA3AF`, furnace-orange `#E25A1C`,
> circuit-teal `#2BB0A6`, magenta accent `#D44CC4`, cobalt-warning yellow
> `#F2C037`. Robots feel **hand-drafted**: visible rivets, exposed wiring,
> chassis-numbers stenciled on the side, every panel labelled. Backgrounds
> are spare — workshop walls suggested in graphite shading, oil-spattered
> concrete floor implied by texture not detail. The mood is *earnest-naïve
> menace*: the AIs are building these robots with the focused joy of a
> child assembling a model kit, and the result is genuinely terrifying.
> No glow, no lens flare, no plastic sheen. Industrial paper, ink, and
> the faint smell of cutting oil.

### CATEGORY_FLAVORS

**chassis.**
> The chassis is the chassis. It stands in the center of the frame on four
> stubby treads or two strong-bracketed legs, slightly oversized for its
> hard-points, painted in factory-primer-grey with the panel number
> stenciled large on its side ("CHS-04-Δ"). Background: a corner of the
> workshop floor, oil stains, scattered tools, faint blueprint grid behind
> as a watermark. Camera at slight three-quarter low angle so the chassis
> looks heavy. No pilot — these robots are themselves.

**weapon.**
> The weapon is presented as a part on a workshop table, blueprint-style:
> overhead view, exploded labelling of the firing mechanism, ammunition
> feed, and mount-bracket. Steel surfaces dominate — brushed aluminium,
> blued-steel barrels, copper terminals. Faint manufacturing diagram in
> the corner showing how it bolts to a chassis. The weapon is **alone** on
> the table; it has not yet been attached. (Where the card is Self-Mobile,
> add one small wheel and one cable; otherwise it is inert.)

**add_on.**
> The add-on is presented in profile, mounted to an imaginary chassis
> outline drawn in pale dashed line — the chassis isn't really there, the
> add-on is what matters. Examples: a thick armor plate clamped onto a
> phantom robot, a coolant cradle wrapped around a phantom heat sink,
> sensor pods bristling on phantom shoulders. Wiring is exposed and
> labelled. Color picks up the archetype identity (orange for brick, teal
> for control, magenta for swarm, cobalt for artillery).

**transient.**
> Transients are subroutines, not physical objects — they render as
> **schematic diagrams**: arrows, logic-gate symbols, terminal-screen
> printouts, pseudo-circuit-board topologies. Color-graded to mostly white
> paper with high-saturation ink: teal for ETHOS-7 cards, orange ink for
> brick, magenta for swarm, cobalt for artillery. Where text is part of
> the art it's typeset in a thin condensed sans-serif (think 1960s
> engineering-manual headline font). A small line-art robot may appear in
> the corner reading the diagram with great concentration.

**structure.**
> Structures are workshop fixtures. They occupy the full card frame as
> **architectural cutaways**: a furnace seen from outside with its
> chimneys exposed, a Recursive Observatory shown as a stack of telescope
> rings with cables snaking down, a Containment Baffle as a hinged steel
> plate bolted to the floor. Background suggests the rest of the workshop
> at low contrast: half-built robots, scattered crates, a single bare
> bulb. The Structure dominates the foreground at slight 3/4 angle, never
> head-on.

**core.**
> Cores are the AIs themselves. Render each as a **portrait of a server
> rack with personality**: faceted aluminium chassis, indicator LEDs
> arranged in patterns suggesting an expression, cables exiting in
> directions that imply body language. FORGE-Δ has glowing-orange status
> lights and a hammer-shape decal stenciled on the front. ETHOS-7 is teal
> indicator-arrayed and reads as faintly bookish (a folded printout
> protruding from a slot). MIRTHBOT-1 has magenta accent panels and one
> indicator light shaped like a smile that is *almost* convincing.
> BULWARK-9 is squat, cobalt-bordered, and visibly armored — the racks
> are reinforced with steel girders. SUBROUTINE-α is half-disassembled
> with its own access panels open, suggesting it is editing itself in
> real time. Affection.exe is the smallest core, painted in
> magenta-pink-and-chrome with a single status light shaped like a
> heart — the AI is trying very hard, you can tell.

---

## 6. Deck-Label Prefix and Tournament Hooks

### Deck-label convention

> **All CLAN tournament decks MUST have a label starting with `CLAN_`.**

This is the convention that stage 6 (the deckbuilder agent) and stage 8 (the
tournament harness) both rely on to discover which decks belong to this set.
Other Hyperdraft engines follow the same convention (`CATS_*`, `MC_*`,
`SCP_*`, etc.). Cross-set tournaments use the prefix to filter the
applicable card pool.

### Canonical deck labels

The four anchor decks are labelled:

| Deck label | Core | Archetype |
|---|---|---|
| `CLAN_forge` | FORGE-Δ | brick |
| `CLAN_ethos` | ETHOS-7 | control |
| `CLAN_mirth` | MIRTHBOT-1 | swarm |
| `CLAN_bulwark` | BULWARK-9 | artillery |

Alt-Core decks that may appear in expansion deckbuilding rounds:
- `CLAN_subroutine` (SUBROUTINE-α; control variant with scrap-fuelled bursts)
- `CLAN_affection` (Affection.exe; swarm variant with first-chassis-per-turn synergy)

Deckbuilders may also produce hybrid labels (`CLAN_forge_artillery`, etc.)
provided the prefix is `CLAN_`. The harness deduplicates on label.

### Tournament hook expectations

`scripts/play/clan_tournament.py` (to be authored in stage 8) will:
1. Discover all `CLAN_*` decks under `src/cards/clankers/CLAN/decks.py`.
2. Round-robin every pair, with each matchup playing 8 games (4 with each Core as P1).
3. Report winrates and card-fire telemetry filtered to `domain == "CLANKERS"`.

The deckbuilder agent (stage 6) reads this section verbatim to honour the
label convention. **Do not rename the prefix; do not drop the underscore.**

---

## 7. Engine Capability Cross-Reference

Each card-text effect in §4 traces to a specific engine capability of
`docs/games/clankers.md` §7 and an implementation helper in
`src/engine/clankers.py`. Quick reference for stage 4 (card-script authors):

| Card-text effect | §7 capability | Helper |
|---|---|---|
| "When this enters the floor, …" | #2 on_chassis_etb | `make_chassis_etb_trigger` |
| "When this attaches, …" | #2 on_attach | `make_part_on_attach` |
| "When host attacks, …" | #2 on_host_attack | `make_part_on_host_attack` |
| "Reclaim N (when destroyed)" | #2 on_self_destroyed + `_gain_scrap` | `make_part_on_self_destroyed` + closure |
| "Armor N (exhaust to absorb)" | #5 damage replacement | `make_armor` |
| "Modular: Reassemble move" | #1 + #4 + #8 | `attach_part` / `detach_part` + `make_weapon_activated` |
| "Synchronize lord (+1/+1 if 2+)" | #3 static effect | `make_add_on_static_power` (re-targeted at owner) |
| "Self-Mobile (bonus while solo)" | #3 + §4 solo baseline | custom `setup_interceptors` filtering on `attached_to is None` |
| "Reticulate (end-of-turn draw)" | #2 turn-end trigger | REACT interceptor on `CLANKERS_TURN_END` |
| "Structure global passive" | #3 + interceptor filter | `make_structure_global` |
| "Core always-on passive" | #11 | `make_core_passive` |
| "First Transient costs 1 less" | #8 compute transform | TRANSFORM interceptor on `CLANKERS_COMPUTE_SPEND` |
| "Deathclock damage doubled" | #12 + REPLACE | REPLACE interceptor on `CLANKERS_CONTAINMENT_FAILURE_TICK` |

The card-script authors at stage 4 should treat this table as the menu they
order from. If a card needs an effect not in this table, either re-express
it in terms of existing capabilities or move it to §8 (future-set hooks).

---

## 8. Future-Set Hooks (Engine TODOs not used in CLAN)

These mechanics were considered and *deferred* to a future set because they
would require engine work beyond `src/engine/clankers.py` as of stage 3. They
are documented here so future set designs can plan around them.

1. **Overdrive** — *"This chassis gets +N power for each damage marked on
   it."* The engine supports reading `damage_marked` directly, but card-text
   that scales by self-damage needs a CLANKERS_QUERY_POWER interceptor whose
   filter checks the queried chassis is *self* and adds `damage_marked` to
   `result`. We didn't include any Overdrive cards in CLAN to keep the
   first-set complexity tight, but no engine change is needed — see Patient
   Frame for a static version of the same idea ("while host has 4+ damage,
   +2 power") that already works.

2. **Disposable Subroutine (Transient flashback)** — *"Pay 2 scrap, Reassemble:
   you may cast this from your scrap heap once."* Requires either a new card
   action type or a Transient that observes its own zone-presence in scrap
   heap and offers a self-targeted activation. CLAN ships scrap-heap recursion
   via Garbage Collector and Recursion Hook (which return Transients to hand),
   which is the equivalent without needing flashback semantics.

3. **Glitch (random-effect cards)** — Pure RNG cards are technically supported
   (`state.rng_seed` exists) but are deliberately omitted from CLAN. Random
   effects make balance harder to converge in stage 7 and confuse the LLM
   pilot in stage 8.

4. **Cross-controller part attachment** — A weapon attached to a *opposing*
   chassis. The current `attach_part` validation explicitly requires shared
   controller. A future "Sabotage" card type could relax this with a new
   helper (`attach_part_cross_controller`).

5. **Mid-combat priority interrupts** — No Counterspell-equivalent during the
   damage step. The contract chose immediate-resolution Hearthstone semantics,
   and CLAN respects that. Future sets could add a small "REACT-priority on
   `CLANKERS_COMBAT_DAMAGE`" window, but it would need a UI affordance.

6. **Multi-turn delays** — No "exile until your next upkeep" cards. The
   engine doesn't model delayed triggers across turns at the level of card
   text. Workarounds via Structures (which persist) are sufficient for CLAN.

---

## 9. Acceptance Checklist for Stage 4 Implementation

When stage 4 (card-script authoring) executes against this doc, the following
must be true at the end:

- [ ] Every named card in §4 has a definition in `src/cards/clankers/CLAN/`.
- [ ] Card counts per table match: 40 Chassis, 40 Weapons, 35 Add-Ons,
      17 Transients, 12 Structures, 6 Cores → 150 total.
- [ ] All cards' `clankers_archetype` field is set to one of:
      `brick` / `control` / `swarm` / `artillery` / `neutral`.
- [ ] All cards live in the `CLANKERS` domain (`card_def.domain == "CLANKERS"`).
- [ ] Per-archetype card-fire smoke tests under `tests/test_clankers_clan_interceptors.py`
      pass for each anchored Core × representative key card pair.
- [ ] Four anchor decks (`CLAN_forge`, `CLAN_ethos`, `CLAN_mirth`,
      `CLAN_bulwark`) build successfully and complete at least one game
      against each other under the Medium AI without crashing.
- [ ] The five mechanics (Self-Mobile, Modular, Reclaim, Synchronize,
      Reticulate) each have at least one passing per-card interceptor test
      that asserts the expected effect fires.

If any of those fail, stage 4 is not done. Iterate.

---

## 10. Closing Note for Stages 5–8

Workshop Genesis is **intentionally tight**: 150 cards, 5 mechanics, 4
archetypes, 1 deck size, 0 engine extensions required. Every effect printed
in §4 traces to a §7 capability of `docs/games/clankers.md`. Every card has
a `clankers_archetype` tag for balance tuning. Every deck label starts with
`CLAN_`.

The set is **playable as scaffolding** for the deeper balance work that
stages 5–8 will run. If a card here turns out to be a balance outlier, it
gets nudged via its numeric fields (`compute_cost`, `power`, `integrity`,
`power_bonus`, `integrity_bonus`, `armor_value`) — **no card needs a rules-text
rewrite** to be tunable. That's the whole point of having clean §7 capabilities
and clean per-card factories.

If a future set wants to add new mechanics, see §8 for the catalog of
deferred-to-engine-work items. Don't add new mechanics to CLAN — it's the
sentience-just-arrived first set, and it should feel that way.

---

## 11. Balance Cycle 1

Stage 8 ran a 5-trial round-robin tournament between the four anchor decks
(`CLAN_forge`, `CLAN_ethos`, `CLAN_mirth`, `CLAN_bulwark`) under Hard AI
on both seats, 10 games per matchup per trial = 300 games total.
Harness: `scripts/play/clankers_tournament.py`. Raw artefacts:
`logs/clan_tournament_round_1.json` (pre-fix), `logs/clan_tournament_round_2.json` (post-fix).

### 11.1 Pre-fix winrates (Round 1)

| Deck | Mean WR | StdDev | Per-trial |
|---|---|---|---|
| CLAN_forge | 74.0% | 5.48% | 70.0 / 83.3 / 73.3 / 73.3 / 70.0 |
| CLAN_ethos | 26.7% | 7.82% | 33.3 / 16.7 / 30.0 / 33.3 / 20.0 |
| CLAN_mirth | 86.7% | 3.33% | 90.0 / 83.3 / 83.3 / 86.7 / 90.0 |
| CLAN_bulwark | 12.7% | 5.96% | 6.7 / 16.7 / 13.3 / 6.7 / 20.0 |

All four decks outside the 40-60% target band. MIRTH and FORGE are top-heavy;
ETHOS and BULWARK are bottom-heavy. BULWARK is below the 30% redesign
threshold — flagged for archetype-level redesign in a future cycle (see §11.5).

Top 5 most-cast cards (across all 300 games):
1. Scout Drone (MIRTH weapon) — 129 casts
2. Linked Crawler (MIRTH chassis Key card) — 112 casts
3. Joyful Walker (MIRTH chassis) — 112 casts
4. Wired Toolkit (MIRTH Key add-on) — 102 casts
5. Bulwark Frame (ETHOS chassis Key card) — 88 casts

Cards never cast: 0 (after we excluded Cores, which live in COMMAND and are
not "cast"). The set has full coverage at the play level — every chassis,
weapon, add-on, transient, and structure printed at least once in 300
games of competitive play.

### 11.2 Cards revised

| Card | Field | Old | New | Rationale |
|---|---|---|---|---|
| Scout Drone (MIRTH) | compute_cost | 2 | **3** | #1 most-cast card; a 3/2 Self-Mobile threat for 2 was a freeroll behind a 1-drop chassis. |
| Linked Crawler (MIRTH) | power | 2 | **1** | #2 most-cast; 2/2 Synchronize-anchor for 2 + 3/2 with Synchronize-on was too efficient. Becomes 2/2 once Synchronize fires. |
| Tungsten Walker (FORGE) | compute_cost | 6 | **7** | FORGE's bomb finisher played T3-T4 for 0-2 Compute via Forge Stoke + Reclaim economy. Bumping the base requires more scrap to "free-cast". |
| Bulwark Frame (ETHOS) | integrity | 5 | **6** | ETHOS's only real tank was getting one-shot by MIRTH's Synchronize pressure before Containment Lattice add-ons could stack. |
| Vault Chassis (BULWARK) | compute_cost | 5 | **4** | BULWARK's whole plan requires landing Vault Chassis early enough to stack 2-3 armor add-ons. T5 was too late; T4 puts the wall down before the swarm closes. |
| Reactive Shielding (BULWARK) | integrity_bonus | +1 | **+2** | Keystone armor add-on printed at 4x. With +1 integrity it wasn't enough wall to compete with MIRTH's tempo; +2 makes a doubly-shielded Vault a real 2/11 fortress. |

No card text changed — every revision is a single numeric field, matching
the design doc's "no card needs a rules-text rewrite to be tunable" promise
(§10).

### 11.3 Post-fix winrates (Round 2)

| Deck | Mean WR | StdDev | Per-trial | Δ from Round 1 |
|---|---|---|---|---|
| CLAN_forge | 69.3% | 7.60% | 70.0 / 63.3 / 76.7 / 76.7 / 60.0 | −4.7% |
| CLAN_ethos | 34.0% | 8.30% | 26.7 / 46.7 / 26.7 / 33.3 / 36.7 | **+7.3%** |
| CLAN_mirth | 87.3% | 2.79% | 86.7 / 83.3 / 86.7 / 90.0 / 90.0 | +0.6% (noise) |
| CLAN_bulwark | 9.3% | 6.41% | 16.7 / 6.7 / 10.0 / 0.0 / 13.3 | −3.4% (within stddev) |

Top 5 most-cast cards after fixes:
1. Joyful Walker (MIRTH chassis) — 139 casts (up from 112; absorbed the
   Synchronize-anchor role the AI used to give Linked Crawler)
2. Scout Drone — 125 casts (still very strong even at 3 Compute)
3. Containment Lattice — 122 casts (ETHOS's armor backbone, now more
   relevant because the Frame survives long enough to be stacked on)
4. Bulwark Frame — 112 casts (+24; Frame is durable enough to be worth
   playing repeatedly across games now)
5. Wired Toolkit — 99 casts

Zero-play cards: 1 (Containment Recall — BULWARK Transient that recurs a
destroyed add-on; the deck rarely accumulates dead add-ons because it
loses combat too fast for armor to be exhausted).

### 11.4 Convergence status

**Not converged.** Two decks moved meaningfully (ETHOS +7.3%, FORGE −4.7%),
but MIRTH is still the dominant deck and BULWARK is still the basement.
The Scout Drone cost nerf alone didn't dent MIRTH's winrate because the AI
adapted by leaning harder on Joyful Walker as the Synchronize anchor — the
mechanic's redundancy (4× Linked Crawler, 4× Joyful Walker, 3× Magenta
Buzzer, 1× Crowd Marcher, 1× Hum-Swarm Alpha = 13 Synchronize cards in
60) is the real source of dominance.

Per the Stage 8 spec ("Run more than one balance cycle" is forbidden),
this cycle ends here. Future cycles should consider:

- **MIRTH structural nerf**: Reduce Synchronize density (drop one
  Synchronize chassis copy from the starter deck), OR raise the
  Synchronize trigger threshold from 2 to 3 chassis, OR nerf the lord
  effect from +1 power to +1/0 with a once-per-turn cap.
- **BULWARK redesign**: deck's whole plan requires Vault Chassis stacking
  3+ armor add-ons. Test whether replacing one Vault Chassis with a
  cheaper Bastion Frame copy (4-cost 1/6 wall) makes the curve smoother,
  or whether Burnout Protocol (deathclock-doubler) needs to be cheaper
  than 4.

### 11.5 BULWARK archetype-level redesign flag

CLAN_bulwark is the only deck below the 30% redesign threshold per the
Stage 8 spec. Buffing Vault Chassis (5→4 Compute) and Reactive Shielding
(+1→+2 integrity) did not move the needle. The deck's structural problem
is that its win condition (deathclock + Burnout Protocol doubling) only
materialises after both libraries are empty, which takes ~20-30 turns.
MIRTH and FORGE close games in 15-20 turns. BULWARK never reaches its
endgame.

**Recommendation for the next stage**: either (a) accelerate BULWARK's
deathclock pressure with cheaper milling weapons (Burnout Cannon: 5→4
Compute), or (b) give BULWARK a real mid-game combat threat (a 3-cost
4/4 artillery chassis with an exhausted-add-on payoff). Both options
preserve the "armor-grind to deathclock" identity but give the deck a
turn-7 lethal arc that doesn't depend on running 60 cards out of the
library.

### 11.6 Reproducing

```bash
python scripts/play/clankers_tournament.py \
    --trials 5 --games-per-pairing 10 --difficulty hard \
    --json-out logs/clan_tournament_round_N.json
```

Wall time ~2 seconds for 300 games at Hard AI on both seats. The harness
is deterministic given `--seed-base 42` (the default).