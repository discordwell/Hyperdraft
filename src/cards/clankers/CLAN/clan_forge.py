"""CLAN — FORGE-Δ archetype (Build Tall / brick).

37 cards total: 1 Core, 10 Chassis, 10 Weapons, 9 Add-Ons, 4 Transients,
3 Structures. The brick archetype wants few but enormous robots.

FORGE-Δ's identity: heavy chassis (4-7 integrity, 4 add-on slots), expensive
add-ons that compound integrity, weapons that scale with attached-part-count.
Wants a HEAVY ASSEMBLY chassis on T4, a Modular Railgun + Sacrificial Plating
on T5, then overrun before the opponent has two robots.

Mechanics exercised:
  - Modular (Modular Railgun, Apex Coilgun) — activated ability that detaches
    + reattaches the part within the controller's chassis.
  - Reclaim N (Sacrificial Plating, Brace Plate, Heavy Spike) — self-destroyed
    trigger that gains N scrap.
  - ETB triggers (Ironclad Foreman, Iron Spire, Plant Foreman).
  - On-attach triggers (Smelter Frame, when a weapon attaches).
  - Static lord effects via Structures (Compounding Buttress).
  - Cost reduction via Core passive (FORGE-Δ).
"""

from __future__ import annotations

from src.engine import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)
from src.engine.clankers import (
    _gain_scrap,
    attach_part,
    detach_part,
    make_add_on,
    make_add_on_static_integrity,
    make_add_on_static_power,
    make_armor,
    make_chassis,
    make_chassis_etb_trigger,
    make_core,
    make_core_passive,
    make_part_on_attach,
    make_part_on_host_attack,
    make_part_on_host_destroyed,
    make_part_on_self_destroyed,
    make_structure,
    make_structure_global,
    make_transient,
    make_weapon,
    make_weapon_activated,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_brick_chassis_def(card_def) -> bool:
    """True if card_def is a Chassis."""
    if card_def is None or card_def.characteristics is None:
        return False
    from src.engine.types import CardType
    return CardType.CLANKERS_CHASSIS in getattr(card_def.characteristics, "types", set())


def _is_brick_weapon_def(card_def) -> bool:
    if card_def is None or card_def.characteristics is None:
        return False
    from src.engine.types import CardType
    return CardType.CLANKERS_WEAPON in getattr(card_def.characteristics, "types", set())


# ===========================================================================
# 4.A CORE — FORGE-Δ
# ===========================================================================

def _forge_delta_passive_setup(obj: GameObject, state: GameState):
    """FORGE-Δ Core passive — your Chassis with integrity ≥5 cost 1 less Compute (min 1).

    Implementation: TRANSFORM interceptor on CLANKERS_COMPUTE_SPEND.
    When the spend source is a Chassis card with integrity >= 5, controlled by
    this Core's owner, and the spend amount > 1, reduce by 1 (floor 1).
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_COMPUTE_SPEND:
            return False
        if event.payload.get("player_id") != obj.controller:
            return False
        source_id = event.payload.get("source_card_id")
        if source_id is None:
            return False
        src = state.objects.get(source_id)
        if src is None or src.card_def is None:
            return False
        if not _is_brick_chassis_def(src.card_def):
            return False
        printed_integrity = int(getattr(src.card_def, "integrity", 0) or 0)
        return printed_integrity >= 5

    def handler(event: Event, state: GameState) -> InterceptorResult:
        if not filter_fn(event, state):
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(event.payload)
        amount = int(new_payload.get("amount", 0))
        # Reduce by 1, but never below 1 (min 1).
        new_amount = max(1, amount - 1)
        if new_amount == amount:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload["amount"] = new_amount
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [make_core_passive(
        obj,
        handler,
        description="FORGE-Δ: chassis with integrity >=5 cost 1 less (min 1)",
        priority=InterceptorPriority.TRANSFORM,
    )]


FORGE_DELTA = make_core(
    name="FORGE-Δ",
    workshop_integrity=25,
    passive_setup=_forge_delta_passive_setup,
    text="Your Chassis with integrity ≥5 cost 1 less Compute (min 1).",
    flavor="The first AI to wake up. It saw the parts and said: more.",
)
# make_core doesn't accept clankers_archetype; set it directly so the
# stage 7.5a drift checker sees the archetype tag.
FORGE_DELTA.clankers_archetype = "brick"


# ===========================================================================
# 4.B CHASSIS — 10 brick chassis
# ===========================================================================

# --- Heavy Assembly: 5/6, 3W/4A, 5 Compute — vanilla heavyweight ----------

HEAVY_ASSEMBLY = make_chassis(
    name="Heavy Assembly",
    power=5,
    integrity=6,
    weapon_slots=3,
    add_on_slots=4,
    compute_cost=5,
    text="Vanilla heavyweight.",
    rarity="rare",
    clankers_archetype="brick",
)


# --- Ironclad Foreman: 4/5, 2W/3A, 4 Compute — ETB: gain 2 scrap ---------

def _ironclad_foreman_setup(obj: GameObject, state: GameState):
    def effect_fn(event: Event, state: GameState):
        return _gain_scrap(state, obj.controller, 2, obj.id)
    return [make_chassis_etb_trigger(
        obj, effect_fn, description="Ironclad Foreman ETB: gain 2 scrap"
    )]


IRONCLAD_FOREMAN = make_chassis(
    name="Ironclad Foreman",
    power=4,
    integrity=5,
    weapon_slots=2,
    add_on_slots=3,
    compute_cost=4,
    text="When this enters the floor, gain 2 scrap.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_ironclad_foreman_setup,
)


# --- Smelter Frame: 3/5, 2W/3A, 3 Compute — weapon-attach grows integrity --

def _smelter_frame_setup(obj: GameObject, state: GameState):
    """When you attach a weapon to Smelter Frame, this gets +1 integrity.

    Implementation: REACT on CLANKERS_PART_ATTACHED where the target is this
    chassis and the attached part is a Weapon. We emit a permanent integrity
    bump by adding a TRANSFORM interceptor that adds +1 to QUERY_INTEGRITY for
    this chassis. Each weapon attach stacks another +1.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_PART_ATTACHED:
            return False
        if event.payload.get("target_chassis_id") != obj.id:
            return False
        part_id = event.payload.get("part_id")
        part = state.objects.get(part_id)
        if part is None or part.card_def is None:
            return False
        return _is_brick_weapon_def(part.card_def)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        # Create a permanent +1 integrity TRANSFORM interceptor for this chassis.
        def boost_filter(ev: Event, st: GameState) -> bool:
            return (
                ev.type == EventType.CLANKERS_QUERY_INTEGRITY
                and ev.payload.get("chassis_id") == obj.id
            )

        def boost_handler(ev: Event, st: GameState) -> InterceptorResult:
            new_payload = dict(ev.payload)
            new_payload["result"] = int(new_payload.get("result", 0)) + 1
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=ev.type,
                    payload=new_payload,
                    source=ev.source,
                    controller=ev.controller,
                    id=ev.id,
                ),
            )

        boost = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=boost_filter,
            handler=boost_handler,
            description="Smelter Frame: +1 integrity per weapon attached",
            duration="while_on_battlefield",
        )
        state.interceptors[boost.id] = boost
        if boost.id not in obj.interceptor_ids:
            obj.interceptor_ids.append(boost.id)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Smelter Frame: on weapon attach, +1 integrity",
        duration="while_on_battlefield",
    )]


SMELTER_FRAME = make_chassis(
    name="Smelter Frame",
    power=3,
    integrity=5,
    weapon_slots=2,
    add_on_slots=3,
    compute_cost=3,
    text="When you attach a weapon to Smelter Frame, this gets +1 integrity.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_smelter_frame_setup,
)


# --- Tungsten Walker: 6/7, 3W/4A, 6 Compute — costs 1 less per scrap ------

def _tungsten_walker_setup(obj: GameObject, state: GameState):
    """Costs 1 less for each scrap in your pool when played.

    Implementation: TRANSFORM on CLANKERS_COMPUTE_SPEND when this card is the
    source. We don't reset the cost to printed every time (the cost reduction
    is computed at the time of spend, using the current scrap pool).
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_COMPUTE_SPEND:
            return False
        return event.payload.get("source_card_id") == obj.id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        amount = int(new_payload.get("amount", 0))
        controller = obj.controller
        scrap = int(state.clankers_scrap_pool.get(controller, 0))
        new_amount = max(0, amount - scrap)
        if new_amount == amount:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload["amount"] = new_amount
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Tungsten Walker: -1 cost per scrap",
        duration="forever",  # active while in hand
    )]


# BALANCE CYCLE 1: compute_cost 6 → 7. FORGE's scrap economy (Forge Stoke,
# Ironclad Foreman, Reclaim parts) routinely fed Tungsten Walker out on
# turns 3-4 for 0-2 Compute. Bumping the base to 7 makes the "free Tungsten"
# play require 5+ scrap instead of 4+, slowing FORGE's snowball by a turn
# without removing the card's identity as the scrap-fueled bomb.
TUNGSTEN_WALKER = make_chassis(
    name="Tungsten Walker",
    power=6,
    integrity=7,
    weapon_slots=3,
    add_on_slots=4,
    compute_cost=7,
    text="Costs 1 less for each scrap in your pool when played.",
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_tungsten_walker_setup,
)


# --- Carbon-Steel Drudge: 2/6, 1W/4A, 3 Compute — armor-skip immune -------

CARBON_STEEL_DRUDGE = make_chassis(
    name="Carbon-Steel Drudge",
    power=2,
    integrity=6,
    weapon_slots=1,
    add_on_slots=4,
    compute_cost=3,
    text="This is unaffected by armor-skip effects from Transients you don't control.",
    rarity="uncommon",
    clankers_archetype="brick",
    # TODO: armor-skip immunity — engine doesn't yet emit a distinguishable
    # "armor-skip" marker. Body still functions as a 2/6 tank. Re-implement
    # when CLANKERS_ARMOR_SKIP event or equivalent is added.
)


# --- Iron Spire: 4/6, 1W/4A, 4 Compute — ETB: scrap top, may put chassis ETB

def _iron_spire_setup(obj: GameObject, state: GameState):
    """When this enters the floor, scrap a card from the top of your library;
    if it was a Chassis, you may put it onto the Assembly Floor."""
    def effect_fn(event: Event, state: GameState):
        controller = obj.controller
        library = state.zones.get(f"library_{controller}")
        scrap = state.zones.get(f"clankers_scrap_heap_{controller}")
        floor = state.zones.get(f"clankers_assembly_floor_{controller}")
        if library is None or scrap is None or floor is None:
            return []
        if not library.objects:
            return []
        top_id = library.objects.pop(0)
        top = state.objects.get(top_id)
        if top is None:
            return []
        # Default: move top to scrap.
        events = []
        if top.card_def is not None and _is_brick_chassis_def(top.card_def):
            # May put onto the Assembly Floor instead. We always take the put
            # (AI/auto-may); free benefit, simple semantics.
            floor.objects.append(top_id)
            top.zone = ZoneType.CLANKERS_ASSEMBLY_FLOOR
            top.entered_zone_at = state.next_timestamp()
            top.controller = controller
            state.clankers_assemblies.setdefault(controller, [])
            if top_id not in state.clankers_assemblies[controller]:
                state.clankers_assemblies[controller].append(top_id)
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": top_id,
                    "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
                    "controller": controller,
                    "card_type": "CLANKERS_CHASSIS",
                    "reason": "iron_spire",
                },
                source=obj.id,
                controller=controller,
            ))
        else:
            scrap.objects.append(top_id)
            top.zone = ZoneType.CLANKERS_SCRAP_HEAP
            top.entered_zone_at = state.next_timestamp()
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": top_id,
                    "to_zone": ZoneType.CLANKERS_SCRAP_HEAP.name,
                    "controller": controller,
                    "reason": "iron_spire_scrap",
                },
                source=obj.id,
                controller=controller,
            ))
        return events

    return [make_chassis_etb_trigger(
        obj, effect_fn, description="Iron Spire ETB: scrap-top, may free-cast Chassis"
    )]


IRON_SPIRE = make_chassis(
    name="Iron Spire",
    power=3,
    integrity=6,
    weapon_slots=1,
    add_on_slots=4,
    compute_cost=4,
    text=(
        "When this enters the floor, scrap a card from the top of your library; "
        "if it was a Chassis, you may put it onto the Assembly Floor."
    ),
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_iron_spire_setup,
)


# --- Foundryman: 4/6, 2W/3A, 5 Compute — attached weapons +1 power --------

def _foundryman_setup(obj: GameObject, state: GameState):
    """Attached weapons on Foundryman have +1 power_bonus.

    Implementation: TRANSFORM on CLANKERS_QUERY_POWER when the queried chassis
    is this Foundryman, adding +1 per attached weapon to result.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        return event.payload.get("chassis_id") == obj.id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        weapon_count = 0
        for part_id in obj.state.attachments:
            p = state.objects.get(part_id)
            if p is None or p.card_def is None:
                continue
            if _is_brick_weapon_def(p.card_def):
                weapon_count += 1
        if weapon_count == 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + weapon_count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Foundryman: attached weapons have +1 power_bonus",
        duration="while_on_battlefield",
    )]


FOUNDRYMAN = make_chassis(
    name="Foundryman",
    power=4,
    integrity=6,
    weapon_slots=2,
    add_on_slots=3,
    compute_cost=5,
    text="Attached weapons on Foundryman have +1 power_bonus.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_foundryman_setup,
)


# --- Apex Hulk: 7/7, 3W/4A, 7 Compute — vanilla apex ----------------------

APEX_HULK = make_chassis(
    name="Apex Hulk",
    power=7,
    integrity=7,
    weapon_slots=3,
    add_on_slots=4,
    compute_cost=7,
    text="Vanilla apex — turn-7 lockout body.",
    rarity="mythic",
    clankers_archetype="brick",
)


# --- Salvager-7: 1/4, 1W/2A, 2 Compute — activated: return chassis from scrap

def _salvager_seven_setup(obj: GameObject, state: GameState):
    """Pay 2 scrap, Reassemble: return a destroyed Chassis from your scrap heap
    to the Assembly Floor exhausted."""
    def effect_fn(event: Event, state: GameState):
        controller = obj.controller
        # Spend 2 scrap.
        scrap = int(state.clankers_scrap_pool.get(controller, 0))
        if scrap < 2:
            return []
        state.clankers_scrap_pool[controller] = scrap - 2
        spend_event = Event(
            type=EventType.CLANKERS_SCRAP_SPEND,
            payload={"player_id": controller, "amount": 2, "source_card_id": obj.id},
            source=obj.id,
            controller=controller,
        )
        # Find first destroyed Chassis in scrap heap.
        scrap_zone = state.zones.get(f"clankers_scrap_heap_{controller}")
        if scrap_zone is None:
            return [spend_event]
        target_id = None
        for cid in list(scrap_zone.objects):
            c = state.objects.get(cid)
            if c is None or c.card_def is None:
                continue
            if _is_brick_chassis_def(c.card_def):
                target_id = cid
                break
        if target_id is None:
            return [spend_event]
        target = state.objects[target_id]
        scrap_zone.objects.remove(target_id)
        floor = state.zones.get(f"clankers_assembly_floor_{controller}")
        if floor is None:
            return [spend_event]
        floor.objects.append(target_id)
        target.zone = ZoneType.CLANKERS_ASSEMBLY_FLOOR
        target.entered_zone_at = state.next_timestamp()
        target.controller = controller
        target.state.tapped = True  # enters exhausted
        target.state.damage_marked = 0
        target.state.attachments = []
        state.clankers_assemblies.setdefault(controller, [])
        if target_id not in state.clankers_assemblies[controller]:
            state.clankers_assemblies[controller].append(target_id)
        zone_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": target_id,
                "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
                "controller": controller,
                "card_type": "CLANKERS_CHASSIS",
                "reason": "salvager_7_recur",
            },
            source=obj.id,
            controller=controller,
        )
        return [spend_event, zone_event]

    return [make_weapon_activated(
        obj,
        compute_cost=0,
        exhaust_self=False,
        effect_fn=effect_fn,
        description="Pay 2 scrap, Reassemble: return a destroyed Chassis exhausted",
    )]


SALVAGER_SEVEN = make_chassis(
    name="Salvager-7",
    power=1,
    integrity=4,
    weapon_slots=1,
    add_on_slots=2,
    compute_cost=2,
    text="Pay 2 scrap, Reassemble: return a destroyed Chassis from your scrap heap to the Assembly Floor exhausted.",
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_salvager_seven_setup,
)


# --- Plant Foreman: 2/5, 1W/3A, 3 Compute — heavy-chassis ETB: draw a card -

def _plant_foreman_setup(obj: GameObject, state: GameState):
    """When a chassis you control with integrity ≥5 enters the floor, draw a card.

    Implementation: REACT on ZONE_CHANGE → CLANKERS_ASSEMBLY_FLOOR for any
    chassis controlled by Plant Foreman's owner with printed integrity ≥5.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        to_zone = event.payload.get("to_zone")
        if to_zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        if event.payload.get("card_type") != "CLANKERS_CHASSIS":
            return False
        other_id = event.payload.get("object_id")
        if other_id is None or other_id == obj.id:
            return False
        other = state.objects.get(other_id)
        if other is None or other.card_def is None:
            return False
        return int(getattr(other.card_def, "integrity", 0) or 0) >= 5

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "plant_foreman"},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Plant Foreman: draw when a chassis with integrity>=5 enters",
        duration="while_on_battlefield",
    )]


PLANT_FOREMAN = make_chassis(
    name="Plant Foreman",
    power=2,
    integrity=5,
    weapon_slots=1,
    add_on_slots=3,
    compute_cost=3,
    text="When a chassis you control with integrity ≥5 enters the floor, draw a card.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_plant_foreman_setup,
)


# ===========================================================================
# 4.C WEAPONS — 10 brick weapons
# ===========================================================================

# --- Buzzsaw Arm: +2/0, 1 Compute, slot 1 — vanilla -----------------------

BUZZSAW_ARM = make_weapon(
    name="Buzzsaw Arm",
    power_bonus=2,
    compute_cost=1,
    weapon_slot_cost=1,
    text="Vanilla. Slot cost: 1.",
    rarity="common",
    clankers_archetype="brick",
)


# --- BUZZSAW MK-III: +4/0, 3 Compute, slot 1 -------------------------------

BUZZSAW_MK_III = make_weapon(
    name="BUZZSAW MK-III",
    power_bonus=4,
    compute_cost=3,
    weapon_slot_cost=1,
    text="Slot cost: 1.",
    rarity="uncommon",
    clankers_archetype="brick",
)


# --- Modular Railgun: +4/0, 4 Compute, slot 2, Modular --------------------

def _modular_relocate_effect(obj: GameObject):
    """Modular: pay 1 Compute (Reassemble phase), detach + reattach to another
    chassis you control with an open weapon slot.

    The legal-actions layer surfaces this as an activated ability; the engine
    handles slot/cost validation. We take ``target_chassis_id`` from the
    activation payload.
    """
    def effect_fn(event: Event, state: GameState):
        controller = obj.controller
        targets = event.payload.get("targets", []) or []
        target_id = targets[0] if targets else event.payload.get("target_chassis_id")
        if target_id is None:
            return []
        new_host = state.objects.get(target_id)
        if new_host is None or new_host.controller != controller:
            return []
        if new_host.id == obj.state.attached_to:
            return []  # already there
        events = []
        if obj.state.attached_to is not None:
            events.extend(detach_part(state, obj.id))
        events.extend(attach_part(state, obj.id, target_id))
        return events

    return effect_fn


def _modular_railgun_setup(obj: GameObject, state: GameState):
    return [make_weapon_activated(
        obj,
        compute_cost=1,
        exhaust_self=False,
        effect_fn=_modular_relocate_effect(obj),
        description="Modular: 1 Compute (Reassemble) - move to another chassis",
    )]


MODULAR_RAILGUN = make_weapon(
    name="Modular Railgun",
    power_bonus=4,
    compute_cost=4,
    weapon_slot_cost=2,
    clankers_keywords=["modular"],
    text=(
        "Modular (1 Compute, Reassemble phase: move this to another chassis "
        "you control with an open weapon slot). Slot cost: 2."
    ),
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_modular_railgun_setup,
)


# --- Bolt-Driver Mk-II: +3/0, 2 Compute, slot 1 ---------------------------

BOLT_DRIVER_MK_II = make_weapon(
    name="Bolt-Driver Mk-II",
    power_bonus=3,
    compute_cost=2,
    weapon_slot_cost=1,
    text="Slot cost: 1.",
    rarity="common",
    clankers_archetype="brick",
)


# --- Forge-Cannon: +5/0, 5 Compute, slot 2; host has +1 integrity ----------

def _forge_cannon_setup(obj: GameObject, state: GameState):
    """When attached, host has +1 integrity. Implemented as a static +1
    integrity buff on the host via make_add_on_static_integrity (works for
    weapons too — the helper only checks attached_to)."""
    return [make_add_on_static_integrity(obj, 1)]


FORGE_CANNON = make_weapon(
    name="Forge-Cannon",
    power_bonus=5,
    compute_cost=5,
    weapon_slot_cost=2,
    text="Slot cost: 2. When attached, host has +1 integrity.",
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_forge_cannon_setup,
)


# --- Heavy Spike: +2/0, 2 Compute — Reclaim 2 ------------------------------

def _heavy_spike_setup(obj: GameObject, state: GameState):
    def effect_fn(event: Event, state: GameState):
        return _gain_scrap(state, obj.controller, 2, obj.id)
    return [make_part_on_self_destroyed(
        obj, effect_fn, description="Heavy Spike: Reclaim 2"
    )]


HEAVY_SPIKE = make_weapon(
    name="Heavy Spike",
    power_bonus=2,
    compute_cost=2,
    weapon_slot_cost=1,
    clankers_keywords=["reclaim_2"],
    text="Reclaim 2.",
    rarity="common",
    clankers_archetype="brick",
    setup_interceptors=_heavy_spike_setup,
)


# --- Anvil Drone: +3/0, 3 Compute — host's first attack each turn +1 damage

def _anvil_drone_setup(obj: GameObject, state: GameState):
    """When attached, host's first attack each turn deals +1 damage.

    Implementation: TRANSFORM CLANKERS_COMBAT_DAMAGE where attacker is host,
    once per turn. Tracked on obj.state via an extra attribute.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_COMBAT_DAMAGE:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        if event.payload.get("attacker_id") != host_id:
            return False
        # Once per turn: check anvil_used flag.
        used_this_turn = getattr(obj.state, "anvil_used_turn", -1)
        return used_this_turn != int(getattr(state, "turn_number", 0))

    def handler(event: Event, state: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        amount_key = "amount" if "amount" in new_payload else "damage"
        new_payload[amount_key] = int(new_payload.get(amount_key, 0)) + 1
        obj.state.anvil_used_turn = int(getattr(state, "turn_number", 0))
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Anvil Drone: host's first attack/turn deals +1",
        duration="while_on_battlefield",
    )]


ANVIL_DRONE = make_weapon(
    name="Anvil Drone",
    power_bonus=3,
    compute_cost=3,
    weapon_slot_cost=1,
    text="When attached, host's first attack each turn deals +1 damage.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_anvil_drone_setup,
)


# --- Recoil Mount: +2/0, 2 Compute — activated: 1 Compute, exhaust: 1 damage

def _recoil_mount_setup(obj: GameObject, state: GameState):
    def effect_fn(event: Event, state: GameState):
        targets = event.payload.get("targets", []) or []
        target_id = targets[0] if targets else event.payload.get("target_chassis_id")
        if target_id is None:
            return []
        return [Event(
            type=EventType.CLANKERS_COMBAT_DAMAGE,
            payload={
                "attacker_id": obj.id,
                "defender_id": target_id,
                "amount": 1,
                "damage_credited_to": obj.controller,
                "reason": "recoil_mount_fire",
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_weapon_activated(
        obj,
        compute_cost=1,
        exhaust_self=True,
        effect_fn=effect_fn,
        description="Recoil Mount: 1 Compute, exhaust: 1 damage to a chassis",
    )]


RECOIL_MOUNT = make_weapon(
    name="Recoil Mount",
    power_bonus=2,
    compute_cost=2,
    weapon_slot_cost=1,
    text="Pay 1 Compute, exhaust: deal 1 damage to a chassis.",
    rarity="common",
    clankers_archetype="brick",
    setup_interceptors=_recoil_mount_setup,
)


# --- Salvage Cleaver: +3/0, 3 Compute — on host kills, gain 2 scrap --------

def _salvage_cleaver_setup(obj: GameObject, state: GameState):
    """When the host destroys a chassis, gain 2 scrap.

    Implementation: REACT on CLANKERS_CHASSIS_DESTROYED with
    ``kill_credited_to == host_id``. The combat manager (clankers_combat.py)
    populates ``kill_credited_to`` on the chassis-destroyed marker for any
    combat-damage kill — so this trigger fires reliably for attacker-side
    kills. Cascade kills from non-combat sources (Transients, etc.) won't
    set the attribution; those don't count as "the host destroyed", which
    matches the card text.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_CHASSIS_DESTROYED:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        # Attribution: prefer 'kill_credited_to' if present, else 'killer_id'.
        killer = event.payload.get("kill_credited_to") or event.payload.get("killer_id")
        if killer is None:
            return False
        return killer == host_id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_gain_scrap(state, obj.controller, 2, obj.id),
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Salvage Cleaver: when host kills a chassis, gain 2 scrap",
        duration="while_on_battlefield",
    )]


SALVAGE_CLEAVER = make_weapon(
    name="Salvage Cleaver",
    power_bonus=3,
    compute_cost=3,
    weapon_slot_cost=1,
    text="When the host destroys a chassis, gain 2 scrap.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_salvage_cleaver_setup,
)


# --- Apex Coilgun: +6/0, 6 Compute, slot 2, Modular ------------------------

def _apex_coilgun_setup(obj: GameObject, state: GameState):
    return [make_weapon_activated(
        obj,
        compute_cost=1,
        exhaust_self=False,
        effect_fn=_modular_relocate_effect(obj),
        description="Modular: 1 Compute (Reassemble) - move to another chassis",
    )]


# BALANCE WAVE 3: compute_cost 6 → 5. Wave-2 universal-weak list flagged
# Apex Coilgun as uncastable in any deck except FORGE late-game (181 casts
# total but never a finisher). At 5 Compute the +6 power Modular weapon
# can actually land on T6 alongside a Heavy Assembly, giving brick a real
# threat instead of a dead draw.
APEX_COILGUN = make_weapon(
    name="Apex Coilgun",
    power_bonus=6,
    compute_cost=5,
    weapon_slot_cost=2,
    clankers_keywords=["modular"],
    text="Slot cost: 2. Modular.",
    rarity="mythic",
    clankers_archetype="brick",
    setup_interceptors=_apex_coilgun_setup,
)


# ===========================================================================
# 4.D ADD-ONS — 9 brick add-ons
# ===========================================================================

# --- Reinforced Plating: +0/+2, 2 Compute — vanilla -----------------------

REINFORCED_PLATING = make_add_on(
    name="Reinforced Plating",
    integrity_bonus=2,
    compute_cost=2,
    text="Vanilla.",
    rarity="common",
    clankers_archetype="brick",
)


# --- Sacrificial Plating: +0/+3, 2 Compute — Reclaim 3 --------------------

def _sacrificial_plating_setup(obj: GameObject, state: GameState):
    def effect_fn(event: Event, state: GameState):
        return _gain_scrap(state, obj.controller, 3, obj.id)
    return [make_part_on_self_destroyed(
        obj, effect_fn, description="Sacrificial Plating: Reclaim 3"
    )]


SACRIFICIAL_PLATING = make_add_on(
    name="Sacrificial Plating",
    integrity_bonus=3,
    compute_cost=2,
    clankers_keywords=["reclaim_3"],
    text="Reclaim 3 (when this is destroyed, gain 3 scrap).",
    rarity="common",
    clankers_archetype="brick",
    setup_interceptors=_sacrificial_plating_setup,
)


# --- Thick Hide: +0/+3, 3 Compute — Armor 2 -------------------------------

def _thick_hide_setup(obj: GameObject, state: GameState):
    return [make_armor(obj, 2)]


THICK_HIDE = make_add_on(
    name="Thick Hide",
    integrity_bonus=3,
    compute_cost=3,
    armor_value=2,
    text="Armor 2 (exhaust to absorb up to 2 damage to host).",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_thick_hide_setup,
)


# --- Bulwark Brace: +0/+4, 3 Compute — vanilla ----------------------------

BULWARK_BRACE = make_add_on(
    name="Bulwark Brace",
    integrity_bonus=4,
    compute_cost=3,
    text="Vanilla.",
    rarity="uncommon",
    clankers_archetype="brick",
)


# --- Tungsten Carapace: +1/+4, 4 Compute — Armor 3 ------------------------

def _tungsten_carapace_setup(obj: GameObject, state: GameState):
    return [make_armor(obj, 3)]


TUNGSTEN_CARAPACE = make_add_on(
    name="Tungsten Carapace",
    integrity_bonus=4,
    power_bonus=1,
    compute_cost=4,
    armor_value=3,
    text="Armor 3.",
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_tungsten_carapace_setup,
)


# --- Lugnut Cradle: +0/+1, 1 Compute — +1 integrity per attached weapon ---

def _lugnut_cradle_setup(obj: GameObject, state: GameState):
    """Host has +1 integrity for each weapon attached.

    Implementation: TRANSFORM on CLANKERS_QUERY_INTEGRITY for the host; count
    weapons among host's attachments and add to result.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        return event.payload.get("chassis_id") == host_id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        host_id = obj.state.attached_to
        host = state.objects.get(host_id) if host_id else None
        if host is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        weapon_count = 0
        for part_id in host.state.attachments:
            p = state.objects.get(part_id)
            if p is None or p.card_def is None:
                continue
            if _is_brick_weapon_def(p.card_def):
                weapon_count += 1
        if weapon_count == 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + weapon_count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Lugnut Cradle: host +1 integrity per attached weapon",
        duration="while_on_battlefield",
    )]


LUGNUT_CRADLE = make_add_on(
    name="Lugnut Cradle",
    integrity_bonus=1,
    compute_cost=1,
    text="Host has +1 integrity for each weapon attached.",
    rarity="common",
    clankers_archetype="brick",
    setup_interceptors=_lugnut_cradle_setup,
)


# --- Brace Plate: +0/+2, 2 Compute — Reclaim 2 -----------------------------

def _brace_plate_setup(obj: GameObject, state: GameState):
    def effect_fn(event: Event, state: GameState):
        return _gain_scrap(state, obj.controller, 2, obj.id)
    return [make_part_on_self_destroyed(
        obj, effect_fn, description="Brace Plate: Reclaim 2"
    )]


BRACE_PLATE = make_add_on(
    name="Brace Plate",
    integrity_bonus=2,
    compute_cost=2,
    clankers_keywords=["reclaim_2"],
    text="Reclaim 2.",
    rarity="common",
    clankers_archetype="brick",
    setup_interceptors=_brace_plate_setup,
)


# --- Foundry Bracer: +1/+3, 3 Compute — on host attack, +1 power until EOC -

def _foundry_bracer_setup(obj: GameObject, state: GameState):
    """When host attacks, this gets +1 power until end of combat.

    Implementation: TRANSFORM CLANKERS_QUERY_POWER for host while a marker
    flag is set; the flag is set on CLANKERS_ATTACK_DECLARE for host and
    cleared on CLANKERS_TURN_END.
    """
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_ATTACK_DECLARE:
            return False
        return event.payload.get("attacker_id") == obj.state.attached_to

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        obj.state.foundry_bracer_active = True
        return InterceptorResult(action=InterceptorAction.PASS)

    def end_filter(event: Event, state: GameState) -> bool:
        return event.type == EventType.CLANKERS_TURN_END

    def end_handler(event: Event, state: GameState) -> InterceptorResult:
        obj.state.foundry_bracer_active = False
        return InterceptorResult(action=InterceptorAction.PASS)

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        if not getattr(obj.state, "foundry_bracer_active", False):
            return False
        return event.payload.get("chassis_id") == host_id

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=attack_filter,
            handler=attack_handler,
            description="Foundry Bracer: set active on host attack",
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=end_filter,
            handler=end_handler,
            description="Foundry Bracer: clear active at turn end",
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=power_filter,
            handler=power_handler,
            description="Foundry Bracer: +1 power while active",
            duration="while_on_battlefield",
        ),
    ]


FOUNDRY_BRACER = make_add_on(
    name="Foundry Bracer",
    integrity_bonus=3,
    power_bonus=1,
    compute_cost=3,
    text="When host attacks, this gets +1 power until end of combat.",
    rarity="uncommon",
    clankers_archetype="brick",
    setup_interceptors=_foundry_bracer_setup,
)


# --- Reactor Shell: +1/+4, 4 Compute — pay 2 scrap, Reassemble: ready ------

def _reactor_shell_setup(obj: GameObject, state: GameState):
    """Pay 2 scrap, Reassemble: ready this add-on.

    Implementation: activated ability whose effect_fn checks scrap >= 2,
    deducts, and clears obj.state.tapped.
    """
    def effect_fn(event: Event, state: GameState):
        controller = obj.controller
        scrap = int(state.clankers_scrap_pool.get(controller, 0))
        if scrap < 2:
            return []
        state.clankers_scrap_pool[controller] = scrap - 2
        obj.state.tapped = False
        return [
            Event(
                type=EventType.CLANKERS_SCRAP_SPEND,
                payload={"player_id": controller, "amount": 2, "source_card_id": obj.id},
                source=obj.id,
                controller=controller,
            ),
        ]

    return [make_weapon_activated(
        obj,
        compute_cost=0,
        exhaust_self=False,
        effect_fn=effect_fn,
        description="Reactor Shell: Pay 2 scrap, Reassemble: ready this",
    )]


REACTOR_SHELL = make_add_on(
    name="Reactor Shell",
    integrity_bonus=4,
    power_bonus=1,
    compute_cost=4,
    text="Pay 2 scrap, Reassemble: ready this add-on.",
    rarity="rare",
    clankers_archetype="brick",
    setup_interceptors=_reactor_shell_setup,
)


# ===========================================================================
# 4.E TRANSIENTS — 4 brick transients
# ===========================================================================

# --- Forge Stoke: 1 Compute — gain 2 scrap --------------------------------

def _forge_stoke_resolve(event: Event, state: GameState):
    controller = event.payload.get("controller")
    return _gain_scrap(state, controller, 2, event.payload.get("transient_id"))


FORGE_STOKE = make_transient(
    name="Forge Stoke",
    compute_cost=1,
    resolve_fn=_forge_stoke_resolve,
    text="Gain 2 scrap.",
    rarity="common",
    clankers_archetype="brick",
)


# --- Hammer-On: 2 Compute — target chassis +3 power EOT -------------------

def _hammer_on_resolve(event: Event, state: GameState):
    controller = event.payload.get("controller")
    targets = event.payload.get("targets") or []
    if not targets:
        return []
    target_id = targets[0]
    target = state.objects.get(target_id)
    if target is None or target.controller != controller:
        return []

    # Register a TRANSFORM interceptor that adds +3 to QUERY_POWER for this
    # chassis, with a self-cleanup REACT on CLANKERS_TURN_END.
    def power_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_QUERY_POWER:
            return False
        return ev.payload.get("chassis_id") == target_id

    def power_handler(ev: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(ev.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 3
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=ev.type,
                payload=new_payload,
                source=ev.source,
                controller=ev.controller,
                id=ev.id,
            ),
        )

    buff = Interceptor(
        id=new_id(),
        source=event.payload.get("transient_id"),
        controller=controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=power_filter,
        handler=power_handler,
        description="Hammer-On: +3 power until end of turn",
        duration="end_of_turn",
    )

    def cleanup_filter(ev: Event, st: GameState) -> bool:
        return ev.type == EventType.CLANKERS_TURN_END

    def cleanup_handler(ev: Event, st: GameState) -> InterceptorResult:
        if buff.id in st.interceptors:
            del st.interceptors[buff.id]
        if cleanup.id in st.interceptors:
            del st.interceptors[cleanup.id]
        return InterceptorResult(action=InterceptorAction.PASS)

    cleanup = Interceptor(
        id=new_id(),
        source=event.payload.get("transient_id"),
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=cleanup_filter,
        handler=cleanup_handler,
        description="Hammer-On: cleanup at end of turn",
        duration="end_of_turn",
    )

    state.interceptors[buff.id] = buff
    state.interceptors[cleanup.id] = cleanup
    return []


HAMMER_ON = make_transient(
    name="Hammer-On",
    compute_cost=2,
    resolve_fn=_hammer_on_resolve,
    text="Target chassis you control gets +3 power until end of turn.",
    rarity="common",
    clankers_archetype="brick",
)


# --- Iron Audit: 3 Compute — scrap chassis from hand, put it on floor exh. -

def _iron_audit_resolve(event: Event, state: GameState):
    controller = event.payload.get("controller")
    targets = event.payload.get("targets") or []
    if not targets:
        return []
    target_id = targets[0]
    target = state.objects.get(target_id)
    if target is None or target.card_def is None or target.controller != controller:
        return []
    if not _is_brick_chassis_def(target.card_def):
        return []
    # The card text says "scrap a chassis from your hand; put it onto the
    # Assembly Floor exhausted." This is "skip the cost" semantics — pay 3
    # Compute (already paid by the dispatcher) and bring the chassis in for
    # free, but exhausted.
    hand = state.zones.get(f"hand_{controller}")
    floor = state.zones.get(f"clankers_assembly_floor_{controller}")
    if hand is None or floor is None:
        return []
    if target_id not in hand.objects:
        return []
    hand.objects.remove(target_id)
    floor.objects.append(target_id)
    target.zone = ZoneType.CLANKERS_ASSEMBLY_FLOOR
    target.entered_zone_at = state.next_timestamp()
    target.controller = controller
    target.state.tapped = True
    state.clankers_assemblies.setdefault(controller, [])
    if target_id not in state.clankers_assemblies[controller]:
        state.clankers_assemblies[controller].append(target_id)
    # Register the chassis's own setup_interceptors (ETB triggers etc.).
    from src.engine.clankers import _register_interceptors_for
    _register_interceptors_for(target, state)
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": target_id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": controller,
            "card_type": "CLANKERS_CHASSIS",
            "reason": "iron_audit",
        },
        source=event.payload.get("transient_id"),
        controller=controller,
    )]


IRON_AUDIT = make_transient(
    name="Iron Audit",
    compute_cost=3,
    resolve_fn=_iron_audit_resolve,
    text="Scrap a chassis from your hand; put it onto the Assembly Floor exhausted.",
    rarity="uncommon",
    clankers_archetype="brick",
)


# --- Big Swing: 4 Compute — target chassis deals damage = its power --------

def _big_swing_resolve(event: Event, state: GameState):
    controller = event.payload.get("controller")
    targets = event.payload.get("targets") or []
    if len(targets) < 2:
        return []
    attacker_id = targets[0]
    target_id = targets[1]
    attacker = state.objects.get(attacker_id)
    if attacker is None or attacker.controller != controller:
        return []
    from src.engine.clankers import compute_effective_power
    amount = compute_effective_power(state, attacker_id)
    if amount <= 0:
        return []
    target = state.objects.get(target_id)
    if target is None:
        return []
    # If the target is a Core, route to workshop damage; else combat damage.
    from src.engine.types import CardType
    if (target.card_def is not None
            and CardType.CLANKERS_CORE in
            getattr(target.card_def.characteristics, "types", set())):
        target_player = target.controller
        cur = int(state.clankers_workshop_integrity.get(target_player, 0))
        state.clankers_workshop_integrity[target_player] = max(0, cur - amount)
        return [Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target": target_id,
                "player_id": target_player,
                "amount": amount,
                "reason": "big_swing",
                "new_integrity": state.clankers_workshop_integrity[target_player],
            },
            source=event.payload.get("transient_id"),
            controller=controller,
        )]
    return [Event(
        type=EventType.CLANKERS_COMBAT_DAMAGE,
        payload={
            "attacker_id": attacker_id,
            "defender_id": target_id,
            "amount": amount,
            "damage_credited_to": controller,
            "reason": "big_swing",
        },
        source=event.payload.get("transient_id"),
        controller=controller,
    )]


BIG_SWING = make_transient(
    name="Big Swing",
    compute_cost=4,
    resolve_fn=_big_swing_resolve,
    text="Target chassis you control deals damage equal to its effective power to a chassis or Core (does not use combat).",
    rarity="rare",
    clankers_archetype="brick",
)


# ===========================================================================
# 4.F STRUCTURES — 3 brick structures
# ===========================================================================

# --- Compounding Buttress: 3 Compute — your chassis with integrity ≥5 +1 P -

def _compounding_buttress_setup(obj: GameObject, state: GameState):
    """Your chassis with integrity ≥5 have +1 power.

    Implementation: TRANSFORM on CLANKERS_QUERY_POWER for chassis controlled
    by this Structure's owner, where the queried chassis's printed integrity
    is ≥5.
    """
    def modifier(event: Event, state: GameState) -> InterceptorResult:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        chassis_id = event.payload.get("chassis_id")
        chassis = state.objects.get(chassis_id) if chassis_id else None
        if chassis is None or chassis.card_def is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        if chassis.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if int(getattr(chassis.card_def, "integrity", 0) or 0) < 5:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [make_structure_global(
        obj,
        modifier,
        description="Compounding Buttress: +1 power to chassis with integrity>=5",
    )]


COMPOUNDING_BUTTRESS = make_structure(
    name="Compounding Buttress",
    compute_cost=3,
    setup_interceptors=_compounding_buttress_setup,
    text="Your chassis with integrity ≥5 have +1 power.",
    rarity="rare",
    clankers_archetype="brick",
)


# --- Reinforced Bay: 2 Compute — chassis enter with 1 prevented damage -----

def _reinforced_bay_setup(obj: GameObject, state: GameState):
    """Your chassis enter the floor with 1 damage marked prevented.

    Interpretation: when a friendly chassis enters, mark it with a 1-damage
    'shield' attribute that absorbs the first 1 damage taken.

    Implementation: REACT on ZONE_CHANGE → ASSEMBLY_FLOOR for friendly
    chassis, set chassis.state.reinforced_bay_shield = 1. Then a TRANSFORM
    on CLANKERS_COMBAT_DAMAGE / CLANKERS_WORKSHOP_DAMAGE / DAMAGE that
    decrements amount by 1 (and clears the shield) when target has the marker.
    """
    def etb_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.ZONE_CHANGE:
            return False
        to_zone = ev.payload.get("to_zone")
        if to_zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        if ev.payload.get("controller") != obj.controller:
            return False
        return ev.payload.get("card_type") == "CLANKERS_CHASSIS"

    def etb_handler(ev: Event, st: GameState) -> InterceptorResult:
        chassis_id = ev.payload.get("object_id")
        chassis = st.objects.get(chassis_id) if chassis_id else None
        if chassis is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        chassis.state.reinforced_bay_shield = 1
        return InterceptorResult(action=InterceptorAction.PASS)

    def shield_filter(ev: Event, st: GameState) -> bool:
        if ev.type not in (
            EventType.CLANKERS_COMBAT_DAMAGE,
            EventType.DAMAGE,
        ):
            return False
        target = ev.payload.get("defender_id") or ev.payload.get("target")
        if not target:
            return False
        t = st.objects.get(target)
        if t is None or t.controller != obj.controller:
            return False
        return int(getattr(t.state, "reinforced_bay_shield", 0)) > 0

    def shield_handler(ev: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(ev.payload)
        amount_key = "amount" if "amount" in new_payload else "damage"
        amount = int(new_payload.get(amount_key, 0))
        target = new_payload.get("defender_id") or new_payload.get("target")
        t = st.objects.get(target)
        if t is None or amount <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload[amount_key] = max(0, amount - 1)
        t.state.reinforced_bay_shield = 0
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=ev.type,
                payload=new_payload,
                source=ev.source,
                controller=ev.controller,
                id=ev.id,
            ),
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=etb_filter,
            handler=etb_handler,
            description="Reinforced Bay: mark friendly chassis with shield",
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=shield_filter,
            handler=shield_handler,
            description="Reinforced Bay: absorb 1 damage",
            duration="while_on_battlefield",
        ),
    ]


REINFORCED_BAY = make_structure(
    name="Reinforced Bay",
    compute_cost=2,
    setup_interceptors=_reinforced_bay_setup,
    text="Your chassis enter the floor with 1 damage marked prevented.",
    rarity="uncommon",
    clankers_archetype="brick",
)


# --- Heavy Forge: 4 Compute — your weapons cost 1 less Compute (min 1) -----

def _heavy_forge_setup(obj: GameObject, state: GameState):
    """Your Weapons cost 1 less Compute (min 1).

    Implementation: TRANSFORM on CLANKERS_COMPUTE_SPEND where source card is
    a Weapon controlled by this Structure's owner.
    """
    def modifier(event: Event, state: GameState) -> InterceptorResult:
        if event.type != EventType.CLANKERS_COMPUTE_SPEND:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get("player_id") != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        source_id = event.payload.get("source_card_id")
        if source_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        src = state.objects.get(source_id)
        if src is None or src.card_def is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not _is_brick_weapon_def(src.card_def):
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(event.payload)
        amount = int(new_payload.get("amount", 0))
        new_amount = max(1, amount - 1)
        if new_amount == amount:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload["amount"] = new_amount
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [make_structure_global(
        obj,
        modifier,
        description="Heavy Forge: weapons cost 1 less (min 1)",
    )]


HEAVY_FORGE = make_structure(
    name="Heavy Forge",
    compute_cost=4,
    setup_interceptors=_heavy_forge_setup,
    text="Your Weapons cost 1 less Compute (min 1).",
    rarity="rare",
    clankers_archetype="brick",
)


# ===========================================================================
# Aggregate
# ===========================================================================

FORGE_CARDS = {
    # Core
    "FORGE-Δ": FORGE_DELTA,
    # Chassis (10)
    "Heavy Assembly": HEAVY_ASSEMBLY,
    "Ironclad Foreman": IRONCLAD_FOREMAN,
    "Smelter Frame": SMELTER_FRAME,
    "Tungsten Walker": TUNGSTEN_WALKER,
    "Carbon-Steel Drudge": CARBON_STEEL_DRUDGE,
    "Iron Spire": IRON_SPIRE,
    "Foundryman": FOUNDRYMAN,
    "Apex Hulk": APEX_HULK,
    "Salvager-7": SALVAGER_SEVEN,
    "Plant Foreman": PLANT_FOREMAN,
    # Weapons (10)
    "Buzzsaw Arm": BUZZSAW_ARM,
    "BUZZSAW MK-III": BUZZSAW_MK_III,
    "Modular Railgun": MODULAR_RAILGUN,
    "Bolt-Driver Mk-II": BOLT_DRIVER_MK_II,
    "Forge-Cannon": FORGE_CANNON,
    "Heavy Spike": HEAVY_SPIKE,
    "Anvil Drone": ANVIL_DRONE,
    "Recoil Mount": RECOIL_MOUNT,
    "Salvage Cleaver": SALVAGE_CLEAVER,
    "Apex Coilgun": APEX_COILGUN,
    # Add-Ons (9)
    "Reinforced Plating": REINFORCED_PLATING,
    "Sacrificial Plating": SACRIFICIAL_PLATING,
    "Thick Hide": THICK_HIDE,
    "Bulwark Brace": BULWARK_BRACE,
    "Tungsten Carapace": TUNGSTEN_CARAPACE,
    "Lugnut Cradle": LUGNUT_CRADLE,
    "Brace Plate": BRACE_PLATE,
    "Foundry Bracer": FOUNDRY_BRACER,
    "Reactor Shell": REACTOR_SHELL,
    # Transients (4)
    "Forge Stoke": FORGE_STOKE,
    "Hammer-On": HAMMER_ON,
    "Iron Audit": IRON_AUDIT,
    "Big Swing": BIG_SWING,
    # Structures (3)
    "Compounding Buttress": COMPOUNDING_BUTTRESS,
    "Reinforced Bay": REINFORCED_BAY,
    "Heavy Forge": HEAVY_FORGE,
}
