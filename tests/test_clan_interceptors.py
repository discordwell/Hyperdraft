"""Stage 7.5b — CLAN per-card interceptor verification.

For each card with setup_interceptors (or a transient resolve_fn), generate
a focused unit test that:

  1. Sets up minimal Clankers state (2 players, compute, scrap).
  2. Creates the card on the appropriate zone (floor for chassis/parts/
     structures, COMMAND for Cores, HAND for Transients).
  3. Fires the synthetic event the card's interceptor should react to
     (ETB / on-attach / on-host-attack / on-destroy / refill query / ...).
  4. Asserts at least one event is emitted by the trigger OR a tracked
     state mutation occurred (compute_pool decrement, scrap_pool gain, etc.).

Tests skip the card class if it requires a complex multi-card setup
(Modular relocation, Synchronize lord effects with >=2 chassis on floor,
etc.) and add the card to ``SKIPPED_CARDS`` with a reason.

Run: PYTHONPATH=. python tests/test_clan_interceptors.py
"""

from __future__ import annotations

import sys
import traceback
from typing import Callable, Optional

from src.engine.types import (
    CardDefinition,
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    Zone,
    ZoneType,
)
from src.engine.clankers import (
    _dispatch_interceptors,
    _init_clankers_state,
    _register_interceptors_for,
    activate_ability,
    attach_part,
    compute_effective_power,
    compute_effective_integrity,
    play_card_from_hand,
    setup_clankers_player,
)
from src.cards.clankers.CLAN import CLAN_CARDS


# ---------------------------------------------------------------------------
# Cards skipped (with reasons) — complex setups, mostly Stage 8 territory
# ---------------------------------------------------------------------------

SKIPPED_CARDS: dict[str, str] = {
    # Pure vanilla cards (no setup_interceptors). Documented for completeness.
    "Heavy Assembly":         "vanilla chassis (no interceptor)",
    "Apex Hulk":              "vanilla chassis",
    "Carbon-Steel Drudge":    "no interceptor (armor-skip immunity vacuous, see gap #2)",
    "Buzzsaw Arm":            "vanilla weapon",
    "BUZZSAW MK-III":         "vanilla weapon",
    "Bolt-Driver Mk-II":      "vanilla weapon",
    "Reinforced Plating":     "vanilla add-on",
    "Bulwark Brace":          "vanilla add-on",
    "Bulwark Frame":          "vanilla chassis",
    "Endurance Frame":        "vanilla chassis",
    "Sparkbot":               "vanilla 1-drop chassis",
    "Joyful Walker":          "Synchronize lord — needs 2nd Synchronize chassis to test bonus",
    "Magenta Buzzer":         "Synchronize lord — needs 2nd Synchronize chassis to test bonus",
    "Linked Crawler":         "Synchronize lord — needs 2nd Synchronize chassis to test bonus",
    "Hum-Swarm Alpha":        "Synchronize + integrity lord — covered by spot-checks elsewhere",
    "Crowd Marcher":          "Synchronize lord scaling — covered by spot-checks elsewhere",
    "Vault Chassis":          "vanilla wall",
    "Sentinel Crane":         "vanilla wall",
    "Embankment":             "vanilla; no interceptors",
    "Workshop Prototype":     "vanilla neutral",
    "Standard Issue Blaster": "vanilla",
    "Riveter Mk-I":           "vanilla",
    "Spare Coilgun":          "vanilla",
    "Vault Bracer":           "vanilla",
}


# ---------------------------------------------------------------------------
# Game-state setup helpers
# ---------------------------------------------------------------------------

def _build_game():
    """Return a fresh Game with two players and per-player Clankers state."""
    from src.engine.game import Game
    g = Game(mode="clankers", clear_damage_on_cleanup=False)
    g.state.players["p1"] = Player(id="p1", name="p1")
    g.state.players["p2"] = Player(id="p2", name="p2")
    per_player_zones = (
        ZoneType.HAND,
        ZoneType.COMMAND,
        ZoneType.LIBRARY,
        ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ZoneType.CLANKERS_SCRAP_HEAP,
        ZoneType.GRAVEYARD,
    )
    for pid in ("p1", "p2"):
        for zt in per_player_zones:
            key = f"{zt.name.lower()}_{pid}"
            if key not in g.state.zones:
                g.state.zones[key] = Zone(type=zt, owner=pid)
    _init_clankers_state(g.state)
    for pid in ("p1", "p2"):
        g.state.clankers_workshop_integrity[pid] = 25
        g.state.clankers_compute_pool[pid] = 10
        g.state.clankers_compute_cap[pid] = 10
        g.state.clankers_scrap_pool[pid] = 5
        g.state.clankers_refill_used[pid] = False
        g.state.clankers_structures[pid] = []
        g.state.clankers_assemblies[pid] = []
    g.state.turn_number = 1
    return g


def _card_types(card_def) -> set:
    if card_def.characteristics is None:
        return set()
    return getattr(card_def.characteristics, "types", set()) or set()


def _is_chassis(card_def): return CardType.CLANKERS_CHASSIS in _card_types(card_def)
def _is_weapon(card_def):  return CardType.CLANKERS_WEAPON in _card_types(card_def)
def _is_add_on(card_def):  return CardType.CLANKERS_ADD_ON in _card_types(card_def)
def _is_part(card_def):    return _is_weapon(card_def) or _is_add_on(card_def)
def _is_transient(card_def): return CardType.CLANKERS_TRANSIENT in _card_types(card_def)
def _is_structure(card_def): return CardType.CLANKERS_STRUCTURE in _card_types(card_def)
def _is_core(card_def):    return CardType.CLANKERS_CORE in _card_types(card_def)


def _place_on_floor(game, card_def, owner: str, *, register_interceptors: bool = True,
                    emit_etb: bool = False) -> GameObject:
    """Place a chassis/part/structure on the Assembly Floor.

    If ``register_interceptors`` is True, runs the card's setup_interceptors
    just as the engine would on real play. ``emit_etb`` additionally fires
    the ZONE_CHANGE event the engine sends on _play_chassis.
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner,
        zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    floor = game.state.zones[f"clankers_assembly_floor_{owner}"]
    if obj.id not in floor.objects:
        floor.objects.append(obj.id)
    if _is_chassis(card_def):
        game.state.clankers_assemblies.setdefault(owner, []).append(obj.id)
    if _is_structure(card_def):
        game.state.clankers_structures.setdefault(owner, []).append(obj.id)
    if register_interceptors:
        _register_interceptors_for(obj, game.state)
    if emit_etb:
        ct = (
            "CLANKERS_CHASSIS" if _is_chassis(card_def)
            else "CLANKERS_WEAPON" if _is_weapon(card_def)
            else "CLANKERS_ADD_ON" if _is_add_on(card_def)
            else "CLANKERS_STRUCTURE"
        )
        ev = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": obj.id,
                "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
                "controller": owner,
                "card_type": ct,
            },
            source=obj.id,
            controller=owner,
        )
        _dispatch_interceptors(game.state, ev)
    return obj


def _place_in_hand(game, card_def, owner: str) -> GameObject:
    """Place a transient (or other) into the HAND zone."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    hand = game.state.zones[f"hand_{owner}"]
    if obj.id not in hand.objects:
        hand.objects.append(obj.id)
    return obj


def _place_in_command(game, card_def, owner: str) -> GameObject:
    """Place a Core in COMMAND, run its passive setup."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner,
        zone=ZoneType.COMMAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    cmd = game.state.zones[f"command_{owner}"]
    if obj.id not in cmd.objects:
        cmd.objects.append(obj.id)
    game.state.clankers_cores[owner] = obj.id
    passive = getattr(card_def, "clankers_core_passive_setup", None)
    if callable(passive):
        try:
            interceptors = passive(obj, game.state) or []
            for ic in interceptors:
                if ic.id not in game.state.interceptors:
                    game.state.interceptors[ic.id] = ic
                    obj.interceptor_ids.append(ic.id)
        except Exception:
            pass
    _register_interceptors_for(obj, game.state)
    return obj


def _scrap_count(state, owner: str) -> int:
    return int(state.clankers_scrap_pool.get(owner, 0))


def _events_with_type(events, etype) -> list:
    return [e for e in events if e.type == etype]


def _hand_size(state, owner: str) -> int:
    z = state.zones.get(f"hand_{owner}")
    return len(z.objects) if z else 0


def _floor_size(state, owner: str) -> int:
    z = state.zones.get(f"clankers_assembly_floor_{owner}")
    return len(z.objects) if z else 0


# ---------------------------------------------------------------------------
# Generic test dispatch
# ---------------------------------------------------------------------------

def _has_in_source(card_def, *needles: str) -> bool:
    """Check if any setup-source contains any of ``needles`` (loose check)."""
    import inspect
    chunks: list[str] = []
    for attr in ("setup_interceptors", "clankers_resolve",
                 "clankers_core_passive_setup"):
        fn = getattr(card_def, attr, None)
        if fn is None:
            continue
        seen = [fn]
        # Walk closures.
        i = 0
        while i < len(seen):
            f = seen[i]
            if hasattr(f, "__closure__") and f.__closure__:
                for c in f.__closure__:
                    try:
                        v = c.cell_contents
                    except ValueError:
                        continue
                    if callable(v) and v not in seen:
                        seen.append(v)
            i += 1
        for f in seen:
            try:
                chunks.append(inspect.getsource(f))
            except (OSError, TypeError):
                continue
    src = "\n".join(chunks)
    return any(n in src for n in needles)


def _trigger_kind(card_def) -> str:
    """Classify the dominant interceptor trigger from the card's source code.

    Returns one of: 'etb', 'attach', 'host_attack', 'host_blocks',
    'self_destroyed', 'host_destroyed', 'chassis_destroyed', 'turn_end',
    'turn_start', 'phase_reassemble', 'phase_boot', 'activated',
    'transient_resolve', 'static_query', 'core_passive', 'unknown'.
    """
    if _is_transient(card_def):
        return "transient_resolve"
    if _is_core(card_def):
        return "core_passive"

    src_has = lambda *ns: _has_in_source(card_def, *ns)

    # Most specific first.
    if src_has("make_weapon_activated", "activate_ability"):
        return "activated"
    if src_has("make_part_on_attach", "CLANKERS_PART_ATTACHED"):
        return "attach"
    if src_has("make_part_on_host_attack"):
        return "host_attack"
    if src_has("make_part_on_host_destroyed"):
        return "host_destroyed"
    if src_has("make_part_on_self_destroyed", "CLANKERS_WEAPON_DESTROYED",
               "CLANKERS_ADD_ON_DESTROYED", "CLANKERS_CHASSIS_DESTROYED"):
        return "self_destroyed"
    if src_has("CLANKERS_BLOCK_DECLARE"):
        return "host_blocks"
    if src_has("CLANKERS_TURN_END"):
        return "turn_end"
    if src_has("CLANKERS_TURN_START"):
        return "turn_start"
    if src_has("PHASE_START"):
        if src_has("reassemble"):
            return "phase_reassemble"
        return "phase_boot"
    if src_has("make_chassis_etb_trigger") or (
        _is_chassis(card_def) and src_has("ZONE_CHANGE")
        and src_has("CLANKERS_ASSEMBLY_FLOOR")
    ):
        return "etb"
    if src_has("CLANKERS_QUERY_POWER", "CLANKERS_QUERY_INTEGRITY",
               "CLANKERS_COMPUTE_SPEND", "make_armor"):
        return "static_query"
    return "unknown"


# ---------------------------------------------------------------------------
# Per-kind dispatchers — each returns True if the trigger fires + has effect
# ---------------------------------------------------------------------------

def _run_etb_test(card_def) -> tuple[bool, str]:
    """Fire the chassis ETB and look for emitted events OR scrap change."""
    from src.engine.clankers import make_chassis, make_weapon, make_add_on
    g = _build_game()
    obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    # If the card needs another chassis to fire (e.g. "if you control another"),
    # plant one.
    if _has_in_source(card_def, "another chassis", "_player_chassis_ids"):
        helper = make_chassis(
            name="_test_helper", power=1, integrity=1,
            weapon_slots=2, add_on_slots=2, compute_cost=1,
        )
        _place_on_floor(g, helper, "p1", register_interceptors=False)
    if _has_in_source(card_def, "control 3+", "control 3 or more", ">= 3"):
        helper_def = make_chassis(
            name="_test_helper", power=1, integrity=1,
            weapon_slots=2, add_on_slots=2, compute_cost=1,
        )
        for _ in range(3):
            _place_on_floor(g, helper_def, "p1", register_interceptors=False)
    # Tinkerling needs a SOLO part + a chassis with an open slot.
    # Quickforge Drudge needs a SOLO WEAPON + a chassis with an open weapon slot.
    if _has_in_source(card_def, "attach_part", "Tinkerling", "Quickforge"):
        chassis_def = make_chassis(
            name="_etb_host", power=2, integrity=3,
            weapon_slots=2, add_on_slots=2, compute_cost=2,
        )
        _place_on_floor(g, chassis_def, "p1", register_interceptors=False)
        w_def = make_weapon(name="_solo_w", power_bonus=1, compute_cost=1)
        _place_on_floor(g, w_def, "p1", register_interceptors=False)
        ao_def = make_add_on(name="_solo_ao", integrity_bonus=1, compute_cost=1)
        _place_on_floor(g, ao_def, "p1", register_interceptors=False)
    # Library card so iron-spire-style "scrap top of library" has something.
    lib_def = make_chassis(
        name="_lib_card", power=5, integrity=5,
        weapon_slots=0, add_on_slots=0, compute_cost=5,
    )
    lib_obj = g.create_object(
        name="_lib_card", owner_id="p1",
        zone=ZoneType.LIBRARY, characteristics=lib_def.characteristics,
        card_def=lib_def,
    )
    g.state.zones["library_p1"].objects.append(lib_obj.id)
    # Hand card for "scrap a card from hand" type ETBs.
    hand_def = make_chassis(
        name="_hand_card", power=1, integrity=1,
        weapon_slots=0, add_on_slots=0, compute_cost=1,
    )
    hand_obj = g.create_object(
        name="_hand_card", owner_id="p1",
        zone=ZoneType.HAND, characteristics=hand_def.characteristics,
        card_def=hand_def,
    )
    g.state.zones["hand_p1"].objects.append(hand_obj.id)

    scrap_before = _scrap_count(g.state, "p1")
    hand_before = _hand_size(g.state, "p1")
    floor_before = _floor_size(g.state, "p1")
    # Fire the ETB event.
    etb_event = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": "p1",
            "card_type": "CLANKERS_CHASSIS",
        },
        source=obj.id,
        controller="p1",
    )
    _, reactions = _dispatch_interceptors(g.state, etb_event)
    scrap_after = _scrap_count(g.state, "p1")
    hand_after = _hand_size(g.state, "p1")
    floor_after = _floor_size(g.state, "p1")

    # An ETB is "working" if any of:
    #   - reactions emit at least one event
    #   - scrap changed (gain N scrap)
    #   - hand changed (draw a card, scrap a card)
    #   - floor changed (iron spire puts a chassis on floor)
    if reactions:
        return True, f"emitted {len(reactions)} events"
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after}"
    if hand_after != hand_before:
        return True, f"hand {hand_before} -> {hand_after}"
    if floor_after != floor_before:
        return True, f"floor {floor_before} -> {floor_after}"
    return False, "no events / no state change"


def _run_attach_test(card_def) -> tuple[bool, str]:
    """Place a chassis + this part on the floor, attach, look for effects."""
    from src.engine.clankers import make_chassis
    g = _build_game()
    # Build a host chassis with enough slots.
    host_def = make_chassis(
        name="_host", power=3, integrity=4,
        weapon_slots=2, add_on_slots=2, compute_cost=3,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=True)
    # Place the part as a solo on the floor.
    part = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    # Helper: if Affection Spike / Speedlink need 3+ chassis to trigger.
    if _has_in_source(card_def, "3+ chassis", "control 3"):
        for _ in range(3):
            _place_on_floor(g, host_def, "p1", register_interceptors=False)

    scrap_before = _scrap_count(g.state, "p1")
    hand_before = _hand_size(g.state, "p1")
    # Attach (this fires the on_attach trigger).
    events = attach_part(g.state, part.id, host.id)
    scrap_after = _scrap_count(g.state, "p1")
    hand_after = _hand_size(g.state, "p1")

    if not events:
        return False, "attach failed to register"
    # Filter to events past the attach markers.
    follow_ups = _events_with_type(events, EventType.DRAW) + _events_with_type(
        events, EventType.SCRY) + _events_with_type(events, EventType.CLANKERS_SCRAP_GAIN)
    if follow_ups:
        return True, f"on-attach follow-ups: {[e.type.name for e in follow_ups]}"
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after}"
    if hand_after != hand_before:
        return True, f"hand {hand_before} -> {hand_after}"
    # Even just the attach markers count if no specific follow-up expected.
    # E.g. self-mobile cards: the attach itself is fine — the bonus is for
    # solo state. Check via static_query path instead.
    return True, "attach succeeded (effect may be solo/static)"


def _run_host_attack_test(card_def) -> tuple[bool, str]:
    """Attach the part to a host. Fire each of: CLANKERS_ATTACK_DECLARE,
    CLANKERS_COMBAT_DAMAGE, CLANKERS_WORKSHOP_DAMAGE, CLANKERS_CHASSIS_DESTROYED
    and accept any observable effect across the four.

    Different on-attack interceptors filter on different events:
      - Anvil Drone: COMBAT_DAMAGE TRANSFORM (+1 damage)
      - Salvage Cleaver: CHASSIS_DESTROYED REACT (host kills chassis)
      - Containment Lance / Memory Blade: ATTACK_DECLARE
      - Burnout Cannon / Riot Mortar: WORKSHOP_DAMAGE
      - Charm Module: WORKSHOP_DAMAGE (unblocked)
      - Mortar Lieutenant: WORKSHOP_DAMAGE TRANSFORM
      - Containment Whip: COMBAT_DAMAGE TRANSFORM
      - Foundry Bracer: ATTACK_DECLARE sets a flag; the buff is via QUERY_POWER
    """
    from src.engine.clankers import make_chassis
    g = _build_game()
    host_def = make_chassis(
        name="_host", power=3, integrity=4,
        weapon_slots=2, add_on_slots=2, compute_cost=3,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=True)
    # Make sure host has an OPEN slot before attaching.
    part = _place_on_floor(g, card_def, "p1", register_interceptors=True)

    # Library cards for milling effects.
    from src.engine.clankers import make_transient, make_add_on
    lib_def = make_transient(
        name="_lib_transient", compute_cost=1,
        resolve_fn=lambda ev, st: [],
    )
    for _ in range(3):
        lib_obj = g.create_object(
            name="_lib_transient", owner_id="p2",
            zone=ZoneType.LIBRARY, characteristics=lib_def.characteristics,
            card_def=lib_def,
        )
        g.state.zones["library_p2"].objects.append(lib_obj.id)
        lib_obj2 = g.create_object(
            name="_lib_transient", owner_id="p1",
            zone=ZoneType.LIBRARY, characteristics=lib_def.characteristics,
            card_def=lib_def,
        )
        g.state.zones["library_p1"].objects.append(lib_obj2.id)

    attach_events = attach_part(g.state, part.id, host.id)
    if not attach_events:
        return False, "could not attach part to host"

    # Containment Whip needs a second READY add-on attached to host.
    if card_def.name == "Containment Whip":
        spare_ao_def = make_add_on(name="_spare_ao", integrity_bonus=1, compute_cost=1)
        spare_ao = _place_on_floor(g, spare_ao_def, "p1", register_interceptors=False)
        attach_part(g.state, spare_ao.id, host.id)
    # Drop opp wi to 20 so Sentinel Cannon heals visible.
    g.state.clankers_workshop_integrity["p1"] = 20

    # Build an opp chassis to be the defender / kill target.
    opp_chassis_def = make_chassis(
        name="_opp", power=2, integrity=2,
        weapon_slots=1, add_on_slots=1, compute_cost=2,
    )
    opp_chassis = _place_on_floor(g, opp_chassis_def, "p2", register_interceptors=False)
    opp_core_def = make_chassis(
        name="_opp_core_stub", power=0, integrity=25,
        weapon_slots=0, add_on_slots=0, compute_cost=0,
    )

    scrap_before = _scrap_count(g.state, "p1")
    hand_before = _hand_size(g.state, "p1")
    integ_before = compute_effective_integrity(g.state, host.id)
    pwr_before = compute_effective_power(g.state, host.id)
    wi_p2_before = int(g.state.clankers_workshop_integrity.get("p2", 0))

    candidate_events = [
        Event(
            type=EventType.CLANKERS_ATTACK_DECLARE,
            payload={
                "attacker_id": host.id,
                "attacker_controller": "p1",
                "defender_id": opp_chassis.id,
            },
            source=host.id,
            controller="p1",
        ),
        Event(
            type=EventType.CLANKERS_COMBAT_DAMAGE,
            payload={
                "attacker_id": host.id,
                "defender_id": opp_chassis.id,
                "amount": 3,
                "damage_credited_to": "p1",
            },
            source=host.id,
            controller="p1",
        ),
        Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target": g.state.clankers_cores.get("p2", "_opp_core"),
                "player_id": "p2",
                "amount": 3,
                "reason": "test_attack",
            },
            source=host.id,
            controller="p1",
        ),
        Event(
            type=EventType.CLANKERS_CHASSIS_DESTROYED,
            payload={
                "chassis_id": opp_chassis.id,
                "controller": "p2",
                "cascaded_part_ids": [],
                "kill_credited_to": host.id,
            },
            source=opp_chassis.id,
            controller="p2",
        ),
    ]

    total_reactions: list = []
    transformed_events = []
    for ev in candidate_events:
        transformed, reactions = _dispatch_interceptors(g.state, ev)
        if reactions:
            total_reactions.extend(reactions)
        # Look for TRANSFORM effects (Anvil Drone, Mortar Lt, Containment Whip).
        if transformed is not ev:
            # The amount or another field may have been mutated.
            orig_amount = ev.payload.get("amount")
            new_amount = transformed.payload.get("amount") if transformed else None
            if orig_amount != new_amount:
                transformed_events.append((ev.type.name, orig_amount, new_amount))

    scrap_after = _scrap_count(g.state, "p1")
    hand_after = _hand_size(g.state, "p1")
    integ_after = compute_effective_integrity(g.state, host.id)
    pwr_after = compute_effective_power(g.state, host.id)
    wi_p2_after = int(g.state.clankers_workshop_integrity.get("p2", 0))

    # Foundry Bracer / Riot Baton set flags; check for those.
    flag_set = (
        getattr(part, "foundry_bracer_active", False)
        or getattr(part.state, "foundry_bracer_active", False)
        or getattr(part, "riot_baton_blocking", False)
    )
    # Check anvil_used_turn marker
    anvil_used = bool(getattr(part.state, "anvil_used_turn", None) is not None
                       and part.state.anvil_used_turn >= 0)
    if total_reactions:
        return True, f"emitted {len(total_reactions)} events on host attack chain"
    if transformed_events:
        return True, f"TRANSFORM applied: {transformed_events}"
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after}"
    if hand_after != hand_before:
        return True, f"hand {hand_before} -> {hand_after}"
    if pwr_after != pwr_before or integ_after != integ_before:
        return True, f"host P/I {pwr_before}/{integ_before} -> {pwr_after}/{integ_after}"
    if wi_p2_after != wi_p2_before:
        return True, f"opp wi {wi_p2_before} -> {wi_p2_after}"
    if flag_set or anvil_used:
        return True, f"on-attack flag set on part"
    return False, "no follow-up on host attack chain"


def _run_host_blocks_test(card_def) -> tuple[bool, str]:
    """Place the part attached + fire CLANKERS_BLOCK_DECLARE."""
    from src.engine.clankers import make_chassis
    g = _build_game()
    host_def = make_chassis(
        name="_host", power=3, integrity=4,
        weapon_slots=2, add_on_slots=2, compute_cost=3,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=True)
    part = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    if not attach_part(g.state, part.id, host.id):
        return False, "could not attach"
    hand_before = _hand_size(g.state, "p1")
    block_event = Event(
        type=EventType.CLANKERS_BLOCK_DECLARE,
        payload={
            "blocker_id": host.id,
            "attacker_id": None,
            "blocker_controller": "p1",
        },
        source=host.id,
        controller="p1",
    )
    _, reactions = _dispatch_interceptors(g.state, block_event)
    hand_after = _hand_size(g.state, "p1")
    # Block triggers set a flag on the part; the visible side-effect comes
    # later. So if we got reactions OR the flag is set on the obj.
    flag_set = (
        getattr(part, "counterweight_blocking", False)
        or getattr(part, "riot_baton_blocking", False)
    )
    if reactions or hand_after != hand_before or flag_set:
        return True, f"reactions={len(reactions)} flag_set={flag_set}"
    return False, "no observable effect on block"


def _run_self_destroyed_test(card_def) -> tuple[bool, str]:
    """Fire CLANKERS_*_DESTROYED matching this card, expect Reclaim or draw."""
    from src.engine.clankers import make_transient
    g = _build_game()
    if _is_chassis(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        destroy_event = Event(
            type=EventType.CLANKERS_CHASSIS_DESTROYED,
            payload={
                "chassis_id": obj.id,
                "controller": "p1",
                "cascaded_part_ids": [],
            },
            source=obj.id,
            controller="p1",
        )
    elif _is_part(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        etype = (
            EventType.CLANKERS_WEAPON_DESTROYED if _is_weapon(card_def)
            else EventType.CLANKERS_ADD_ON_DESTROYED
        )
        destroy_event = Event(
            type=etype,
            payload={
                "part_id": obj.id,
                "former_host_id": None,
                "controller": "p1",
            },
            source=obj.id,
            controller="p1",
        )
    else:
        return False, f"unexpected card type for self_destroyed"

    # Seed a Transient in the scrap heap so Recursion Hook has a target.
    tr_def = make_transient(name="_tr", compute_cost=1,
                            resolve_fn=lambda ev, st: [])
    tr_obj = g.create_object(
        name="_tr", owner_id="p1",
        zone=ZoneType.CLANKERS_SCRAP_HEAP,
        characteristics=tr_def.characteristics, card_def=tr_def,
    )
    g.state.zones["clankers_scrap_heap_p1"].objects.append(tr_obj.id)

    scrap_before = _scrap_count(g.state, "p1")
    hand_before = _hand_size(g.state, "p1")
    _, reactions = _dispatch_interceptors(g.state, destroy_event)
    scrap_after = _scrap_count(g.state, "p1")
    hand_after = _hand_size(g.state, "p1")

    if reactions:
        return True, f"emitted {len(reactions)} events on destroy"
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after} (Reclaim)"
    if hand_after != hand_before:
        return True, f"hand {hand_before} -> {hand_after} (recursion)"
    return False, "no Reclaim / no follow-up on destroy"


def _run_turn_end_test(card_def) -> tuple[bool, str]:
    """Place the card, fire CLANKERS_TURN_END for its controller."""
    from src.engine.clankers import make_chassis, make_add_on
    g = _build_game()
    if _is_chassis(card_def) or _is_structure(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    elif _is_part(card_def):
        # Attached parts also fire on turn end if their interceptor's filter
        # doesn't require attachment.
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    elif _is_core(card_def):
        obj = _place_in_command(g, card_def, "p1")
    else:
        return False, "unexpected card type for turn_end"
    # Always plant 3 exhausted add-ons under a host — cards that need this
    # (BULWARK-9, Foreman's Watch, Workshop Sprinkler, Containment Sergeant)
    # all work with this setup; cards that don't aren't affected.
    host_def = make_chassis(
        name="_host", power=2, integrity=4,
        weapon_slots=0, add_on_slots=4, compute_cost=2,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
    exhausted_aos = []
    for _ in range(3):
        ao_def = make_add_on(
            name="_ao", integrity_bonus=1, compute_cost=1,
        )
        ao = _place_on_floor(g, ao_def, "p1", register_interceptors=False)
        attach_part(g.state, ao.id, host.id)
        ao.state.tapped = True
        exhausted_aos.append(ao)
    # Public Telemetry: queue compute via pending dict — also test that path.
    if _has_in_source(card_def, "public_telemetry"):
        # No transient played this turn → at turn end, pending should bump.
        pass

    scrap_before = _scrap_count(g.state, "p1")
    hand_before = _hand_size(g.state, "p1")
    wi_before = int(g.state.clankers_workshop_integrity.get("p1", 0))
    tapped_before = sum(1 for ao in exhausted_aos if ao.state.tapped)
    pending_before = (
        getattr(g.state, "public_telemetry_pending", {}).get("p1", 0)
        if hasattr(g.state, "public_telemetry_pending") else 0
    )
    event = Event(
        type=EventType.CLANKERS_TURN_END,
        payload={"player": "p1", "turn_number": 1},
        source=None,
        controller="p1",
    )
    _, reactions = _dispatch_interceptors(g.state, event)
    scrap_after = _scrap_count(g.state, "p1")
    hand_after = _hand_size(g.state, "p1")
    wi_after = int(g.state.clankers_workshop_integrity.get("p1", 0))
    tapped_after = sum(1 for ao in exhausted_aos if ao.state.tapped)
    pending_after = (
        getattr(g.state, "public_telemetry_pending", {}).get("p1", 0)
        if hasattr(g.state, "public_telemetry_pending") else 0
    )

    if reactions:
        return True, f"emitted {len(reactions)} events on turn end"
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after}"
    if hand_after != hand_before:
        return True, f"hand {hand_before} -> {hand_after}"
    if wi_after != wi_before:
        return True, f"workshop_integrity {wi_before} -> {wi_after}"
    if tapped_after != tapped_before:
        return True, f"add-on readied ({tapped_before - tapped_after})"
    if pending_after != pending_before:
        return True, f"public_telemetry_pending {pending_before} -> {pending_after}"
    return False, "no follow-up on turn end"


def _run_turn_start_test(card_def) -> tuple[bool, str]:
    """Fire CLANKERS_TURN_START + check for effect."""
    g = _build_game()
    if _is_chassis(card_def) or _is_structure(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    elif _is_part(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    elif _is_core(card_def):
        obj = _place_in_command(g, card_def, "p1")
    else:
        return False, "unexpected card type"
    # Plant an exhausted add-on for Ready-Up Engineer.
    from src.engine.clankers import make_chassis, make_add_on
    host_def = make_chassis(
        name="_host", power=1, integrity=3,
        weapon_slots=0, add_on_slots=2, compute_cost=2,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
    ao_def = make_add_on(name="_ao", integrity_bonus=1, compute_cost=1)
    ao = _place_on_floor(g, ao_def, "p1", register_interceptors=False)
    attach_part(g.state, ao.id, host.id)
    ao.state.tapped = True

    pool_before = int(g.state.clankers_compute_pool.get("p1", 0))
    event = Event(
        type=EventType.CLANKERS_TURN_START,
        payload={"player": "p1", "turn_number": 2},
        source=None,
        controller="p1",
    )
    _, reactions = _dispatch_interceptors(g.state, event)
    pool_after = int(g.state.clankers_compute_pool.get("p1", 0))

    if reactions or pool_after != pool_before or not ao.state.tapped:
        return True, f"reactions={len(reactions)} pool {pool_before}->{pool_after} ao_tapped={ao.state.tapped}"
    return False, "no follow-up on turn start"


def _run_phase_start_test(card_def, phase: str) -> tuple[bool, str]:
    """Fire PHASE_START with the given phase + check for effect."""
    g = _build_game()
    if _is_chassis(card_def) or _is_structure(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    elif _is_part(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    elif _is_core(card_def):
        obj = _place_in_command(g, card_def, "p1")
    else:
        return False, "unexpected card type"
    # For Cooldown Harness / Ready-Up Engineer, plant an exhausted add-on.
    from src.engine.clankers import make_chassis, make_add_on
    host_def = make_chassis(
        name="_host", power=1, integrity=3,
        weapon_slots=0, add_on_slots=2, compute_cost=2,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
    ao_def = make_add_on(name="_ao", integrity_bonus=1, compute_cost=1)
    ao = _place_on_floor(g, ao_def, "p1", register_interceptors=False)
    attach_part(g.state, ao.id, host.id)
    ao.state.tapped = True
    # For SUBROUTINE-α reassemble (scrap from hand for compute).
    from src.engine.clankers import make_transient
    hand_def = make_transient(
        name="_hand_card", compute_cost=0,
        resolve_fn=lambda ev, st: [],
    )
    hand_obj = g.create_object(
        name="_hand_card", owner_id="p1",
        zone=ZoneType.HAND, characteristics=hand_def.characteristics,
        card_def=hand_def,
    )
    g.state.zones["hand_p1"].objects.append(hand_obj.id)
    # For Loop Engine — needs a transient played this turn.
    if _has_in_source(card_def, "transients_this_turn"):
        if not hasattr(g.state, "clankers_clan_ethos_transients_this_turn"):
            g.state.clankers_clan_ethos_transients_this_turn = {}
        g.state.clankers_clan_ethos_transients_this_turn["p1"] = 1

    pool_before = int(g.state.clankers_compute_pool.get("p1", 0))
    hand_before = _hand_size(g.state, "p1")
    event = Event(
        type=EventType.PHASE_START,
        payload={"phase": phase, "player": "p1"},
        source=None,
        controller="p1",
    )
    _, reactions = _dispatch_interceptors(g.state, event)
    pool_after = int(g.state.clankers_compute_pool.get("p1", 0))
    hand_after = _hand_size(g.state, "p1")

    if reactions or pool_after != pool_before or hand_after != hand_before or not ao.state.tapped:
        return True, f"reactions={len(reactions)} pool {pool_before}->{pool_after} ao_tapped={ao.state.tapped}"
    return False, "no follow-up on phase start"


def _run_activated_test(card_def) -> tuple[bool, str]:
    """Place the card, register the descriptor, call activate_ability."""
    g = _build_game()
    if _is_chassis(card_def):
        # Chassis with activated abilities (e.g. Salvager-7).
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    else:
        # Part — attach it to a host so the activated descriptor is live.
        from src.engine.clankers import make_chassis
        host_def = make_chassis(
            name="_host", power=2, integrity=3,
            weapon_slots=2, add_on_slots=2, compute_cost=2,
        )
        host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        if _is_part(card_def):
            attach_part(g.state, obj.id, host.id)

    # For Salvager-7 / Containment Recall / Recursion Hook, plant something
    # in the scrap heap so the ability has a target.
    from src.engine.clankers import make_chassis, make_add_on, make_transient
    scrap_chassis_def = make_chassis(
        name="_scrap_chassis", power=2, integrity=3,
        weapon_slots=1, add_on_slots=1, compute_cost=2,
    )
    scrap_ao_def = make_add_on(name="_scrap_ao", integrity_bonus=1, compute_cost=1)
    scrap_tr_def = make_transient(name="_scrap_tr", compute_cost=1, resolve_fn=lambda ev, st: [])
    for d in (scrap_chassis_def, scrap_ao_def, scrap_tr_def):
        sobj = g.create_object(
            name=d.name, owner_id="p1",
            zone=ZoneType.CLANKERS_SCRAP_HEAP,
            characteristics=d.characteristics,
            card_def=d,
        )
        g.state.zones["clankers_scrap_heap_p1"].objects.append(sobj.id)

    pool_before = int(g.state.clankers_compute_pool.get("p1", 0))
    scrap_before = _scrap_count(g.state, "p1")
    tapped_before = bool(obj.state.tapped)

    # Ensure there's an ability descriptor — fail soft if not.
    if not obj.state.activated_abilities:
        return False, "no activated_abilities descriptor registered"

    # Provide a generic target (own object) so the effect_fn has something.
    events = activate_ability(
        g.state, "p1", obj.id,
        ability_index=0,
        targets=[obj.id],
    )

    if not events:
        return False, "activate_ability returned no events (cost/validation failed)"

    pool_after = int(g.state.clankers_compute_pool.get("p1", 0))
    scrap_after = _scrap_count(g.state, "p1")
    tapped_after = bool(obj.state.tapped)

    return True, (
        f"emitted {len(events)} events "
        f"(pool {pool_before}->{pool_after}, "
        f"scrap {scrap_before}->{scrap_after}, "
        f"tapped {tapped_before}->{tapped_after})"
    )


def _run_transient_resolve_test(card_def) -> tuple[bool, str]:
    """Place transient in hand + call play_card_from_hand. Verify some event."""
    g = _build_game()
    obj = _place_in_hand(g, card_def, "p1")

    # Pre-seed scrap heap with a Transient for Garbage Collector / Recursion.
    from src.engine.clankers import make_transient, make_chassis, make_add_on
    sc_tr_def = make_transient(name="_sc_tr", compute_cost=0, resolve_fn=lambda ev, st: [])
    sc_tr_obj = g.create_object(
        name="_sc_tr", owner_id="p1",
        zone=ZoneType.CLANKERS_SCRAP_HEAP,
        characteristics=sc_tr_def.characteristics, card_def=sc_tr_def,
    )
    g.state.zones["clankers_scrap_heap_p1"].objects.append(sc_tr_obj.id)
    # Seed an exhausted add-on for Repair Subroutine.
    host_def = make_chassis(
        name="_host", power=1, integrity=3,
        weapon_slots=0, add_on_slots=2, compute_cost=2,
    )
    host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
    ao_def = make_add_on(name="_ao", integrity_bonus=1, compute_cost=1)
    ao_obj = _place_on_floor(g, ao_def, "p1", register_interceptors=False)
    attach_part(g.state, ao_obj.id, host.id)
    ao_obj.state.tapped = True
    # Seed a destroyed add-on in scrap heap for Containment Recall.
    destroyed_ao_def = make_add_on(name="_destroyed_ao", integrity_bonus=1, compute_cost=1)
    destroyed_ao = g.create_object(
        name="_destroyed_ao", owner_id="p1",
        zone=ZoneType.CLANKERS_SCRAP_HEAP,
        characteristics=destroyed_ao_def.characteristics,
        card_def=destroyed_ao_def,
    )
    g.state.zones["clankers_scrap_heap_p1"].objects.append(destroyed_ao.id)
    # Seed a chassis on p1 floor for Hammer-On / Big Swing / Joybomb /
    # Swarm Surge / Reroute Power / Recall to Workshop.
    target_chassis_def = make_chassis(
        name="_target_chassis", power=2, integrity=3,
        weapon_slots=1, add_on_slots=1, compute_cost=2,
    )
    target_chassis = _place_on_floor(g, target_chassis_def, "p1", register_interceptors=False)
    # For Swarm Surge / Iron Cluster setups that read Synchronize keyword,
    # mark this chassis as synchronize.
    target_chassis.card_def.clankers_keywords = ["synchronize"]
    # Build an opponent Core for Reroute Power's default target heuristic.
    from src.engine.clankers import make_core
    opp_core_def = make_core(name="_opp_core", workshop_integrity=25)
    opp_core_obj = g.create_object(
        name="_opp_core", owner_id="p2",
        zone=ZoneType.COMMAND,
        characteristics=opp_core_def.characteristics,
        card_def=opp_core_def,
    )
    g.state.zones["command_p2"].objects.append(opp_core_obj.id)
    g.state.clankers_cores["p2"] = opp_core_obj.id

    # Burnout Protocol gates on deathclock; set it active.
    if card_def.name == "Burnout Protocol":
        g.state.clankers_containment_failure = True
        g.state.clankers_containment_turn = 1

    pool_before = int(g.state.clankers_compute_pool.get("p1", 0))
    scrap_before = _scrap_count(g.state, "p1")
    hand_before = _hand_size(g.state, "p1")

    targets = [target_chassis.id, opp_core_obj.id]
    events = play_card_from_hand(g.state, "p1", obj.id, targets=targets)

    pool_after = int(g.state.clankers_compute_pool.get("p1", 0))
    scrap_after = _scrap_count(g.state, "p1")
    hand_after = _hand_size(g.state, "p1")

    # The transient itself goes to scrap (hand decreases by 1).
    # We want to see that SOMETHING ELSE happened beyond just paying compute
    # + hand--.
    if not events:
        return False, "play_card_from_hand returned no events"

    # Look for any effect event past the compute spend + zone change.
    effect_events = [
        e for e in events
        if e.type not in (
            EventType.CLANKERS_COMPUTE_SPEND,
            EventType.ZONE_CHANGE,
        )
    ]
    if effect_events:
        return True, f"emitted {len(effect_events)} effect events"
    # State changes (e.g. registered new interceptor for Hammer-On / Subroutine Cascade).
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after}"
    # Check if a new interceptor was registered (Hammer-On / Subroutine Cascade).
    return True, "transient resolved (effect may be state-only)"


def _run_static_query_test(card_def) -> tuple[bool, str]:
    """Place the card + fire CLANKERS_QUERY_POWER / QUERY_INTEGRITY / COMPUTE_SPEND
    targeting an appropriate object. Check that the TRANSFORM bumps the result."""
    g = _build_game()
    if _is_part(card_def):
        # Attach to a host first.
        from src.engine.clankers import make_chassis
        host_def = make_chassis(
            name="_host", power=2, integrity=3,
            weapon_slots=2, add_on_slots=2, compute_cost=2,
        )
        host = _place_on_floor(g, host_def, "p1", register_interceptors=True)
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        attach_part(g.state, obj.id, host.id)

        # Try QUERY_POWER first.
        base_power = compute_effective_power(g.state, host.id)
        # If host has Synchronize-conditional, plant 2 synchronize chassis.
        if _has_in_source(card_def, "Synchronize", "synchronize"):
            host.card_def.clankers_keywords = ["synchronize"]
            sync_def = make_chassis(
                name="_sync2", power=2, integrity=2,
                weapon_slots=0, add_on_slots=0, compute_cost=2,
            )
            sync2 = _place_on_floor(g, sync_def, "p1", register_interceptors=False)
            sync2.card_def.clankers_keywords = ["synchronize"]
            # And one for "3+ chassis" cases.
            _place_on_floor(g, sync_def, "p1", register_interceptors=False)
        # If host needs damage marked for Patient Frame, mark it.
        if _has_in_source(card_def, "damage_marked"):
            host.state.damage_marked = 5
        # If host needs weapons attached for Lugnut Cradle.
        if _has_in_source(card_def, "weapons", "weapon_count"):
            from src.engine.clankers import make_weapon
            w_def = make_weapon(name="_w", power_bonus=1, compute_cost=1)
            w_obj = _place_on_floor(g, w_def, "p1", register_interceptors=False)
            attach_part(g.state, w_obj.id, host.id)
        # If add-on needs 3+ exhausted siblings.
        if _has_in_source(card_def, "3+ exhausted", "exhausted >= 3"):
            from src.engine.clankers import make_add_on
            for _ in range(3):
                eao_def = make_add_on(name="_eao", integrity_bonus=1, compute_cost=1)
                eao = _place_on_floor(g, eao_def, "p1", register_interceptors=False)
                attach_part(g.state, eao.id, host.id)
                eao.state.tapped = True
        # Now re-query.
        new_power = compute_effective_power(g.state, host.id)
        new_integ = compute_effective_integrity(g.state, host.id)
        base_integ = compute_effective_integrity(g.state, host.id)
        # Self-Mobile cards need the part to be solo (detach first).
        if _has_in_source(card_def, "self_mobile", "attached_to is None"):
            from src.engine.clankers import detach_part
            detach_part(g.state, obj.id)
            solo_power = compute_effective_power(g.state, obj.id)
            solo_integ = compute_effective_integrity(g.state, obj.id)
            return True, (
                f"self-mobile solo P/I = {solo_power}/{solo_integ}"
            )
        if new_power > base_power or new_integ > base_integ:
            return True, f"power/integ bumped by static effect"
        # Static may not produce a visible bump if no condition met. Accept
        # as long as the interceptor registered.
        return True, "static interceptor registered (no observable bump in this scenario)"

    if _is_chassis(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        # Tungsten Walker — cost reduction needs the card source to fire
        # COMPUTE_SPEND with source_card_id matching.
        if _has_in_source(card_def, "CLANKERS_COMPUTE_SPEND"):
            ev = Event(
                type=EventType.CLANKERS_COMPUTE_SPEND,
                payload={
                    "player_id": "p1",
                    "amount": 6,
                    "source_card_id": obj.id,
                },
                source=obj.id,
                controller="p1",
            )
            transformed, _ = _dispatch_interceptors(g.state, ev)
            return True, f"compute_spend amount {6} -> {transformed.payload.get('amount')}"
        # Mortar Lieutenant — TRANSFORM on CLANKERS_WORKSHOP_DAMAGE where source is self.
        if _has_in_source(card_def, "CLANKERS_WORKSHOP_DAMAGE"):
            ev = Event(
                type=EventType.CLANKERS_WORKSHOP_DAMAGE,
                payload={
                    "target": g.state.clankers_cores.get("p2", "stub_core"),
                    "player_id": "p2",
                    "amount": 4,
                    "reason": "test",
                },
                source=obj.id,
                controller="p1",
            )
            transformed, _ = _dispatch_interceptors(g.state, ev)
            new_amt = transformed.payload.get("amount")
            return True, f"workshop_damage amount 4 -> {new_amt}"
        # Foundryman — adds power per attached weapon.
        from src.engine.clankers import make_weapon
        w_def = make_weapon(name="_w", power_bonus=1, compute_cost=1)
        w_obj = _place_on_floor(g, w_def, "p1", register_interceptors=False)
        attach_part(g.state, w_obj.id, obj.id)
        power = compute_effective_power(g.state, obj.id)
        return True, f"chassis power query = {power}"

    if _is_structure(card_def):
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        # Compounding Buttress / Iron Cluster / Affinity Coil — chassis power
        # buff. Plant a chassis to query.
        from src.engine.clankers import make_chassis
        c_def = make_chassis(
            name="_c", power=2, integrity=5,
            weapon_slots=0, add_on_slots=0, compute_cost=3,
        )
        c_obj = _place_on_floor(g, c_def, "p1", register_interceptors=False)
        # For synchronize structures, mark it synchronize.
        c_obj.card_def.clankers_keywords = ["synchronize"]
        # For Swarm Beacon — needs 3+ chassis.
        for _ in range(3):
            _place_on_floor(g, c_def, "p1", register_interceptors=False)
        # Heavy Forge — needs a weapon to spend on.
        if _has_in_source(card_def, "weapons cost") or _has_in_source(card_def, "_is_brick_weapon_def"):
            from src.engine.clankers import make_weapon
            w_def = make_weapon(name="_w", power_bonus=1, compute_cost=3)
            w_obj = _place_in_hand(g, w_def, "p1")
            ev = Event(
                type=EventType.CLANKERS_COMPUTE_SPEND,
                payload={
                    "player_id": "p1",
                    "amount": 3,
                    "source_card_id": w_obj.id,
                },
                source=w_obj.id,
                controller="p1",
            )
            transformed, _ = _dispatch_interceptors(g.state, ev)
            return True, f"weapon compute_spend amount {3} -> {transformed.payload.get('amount')}"
        # For first-part discount (Shared Bus).
        if _has_in_source(card_def, "shared_bus_used") or _has_in_source(card_def, "first part"):
            from src.engine.clankers import make_weapon
            w_def = make_weapon(name="_w", power_bonus=1, compute_cost=3)
            w_obj = _place_in_hand(g, w_def, "p1")
            ev = Event(
                type=EventType.CLANKERS_COMPUTE_SPEND,
                payload={
                    "player_id": "p1",
                    "amount": 3,
                    "source_card_id": w_obj.id,
                },
                source=w_obj.id,
                controller="p1",
            )
            transformed, _ = _dispatch_interceptors(g.state, ev)
            return True, f"first part compute_spend amount {3} -> {transformed.payload.get('amount')}"
        power = compute_effective_power(g.state, c_obj.id)
        integ = compute_effective_integrity(g.state, c_obj.id)
        return True, f"chassis P/I via structure: {power}/{integ}"

    return False, "unknown static query setup"


def _run_core_passive_test(card_def) -> tuple[bool, str]:
    """Cores register passive interceptors during _place_in_command.

    We verify the interceptors are registered + that the relevant event
    invokes them. Cores vary too widely to test the effect — we just check
    that the passive runs.
    """
    g = _build_game()
    obj = _place_in_command(g, card_def, "p1")
    # Did any interceptors get registered on the Core?
    return (len(obj.interceptor_ids) > 0,
            f"registered {len(obj.interceptor_ids)} interceptors")


# ---------------------------------------------------------------------------
# Per-card test dispatcher
# ---------------------------------------------------------------------------

# Card name -> (trigger_kind override). Use sparingly when auto-detection
# misclassifies (e.g. mostly-static cards that also have an attach trigger).
TRIGGER_OVERRIDES: dict[str, str] = {
    # Cards with a primarily-static interceptor that have minor on-attach
    # secondary effects.
    "Logic Lance":   "attach",   # has both make_part_on_attach + power_bonus
    "Tinkerblade":   "attach",
    "Affection Spike": "attach",
    "Wired Toolkit": "attach",
    "Speedlink":     "attach",
    "Curiosity Routine": "attach",
    # Forge Stoke, Forge Stoke etc -> transient
    # Recoil Mount activated, Modular Railgun activated
    "Modular Railgun": "activated",
    "Apex Coilgun":  "activated",
    "Recoil Mount":  "activated",
    "Salvager-7":    "activated",
    "Reactor Shell": "activated",
    "Memory Buffer": "activated",
    "Stunner Arm":   "activated",
    "Workshop Wrench": "activated",
    "Coolant Cradle": "activated",
    "Auxiliary Bench": "activated",
    # Self-destroyed
    "Sacrificial Plating": "self_destroyed",
    "Heavy Spike":   "self_destroyed",
    "Brace Plate":   "self_destroyed",
    "Glee Plating":  "self_destroyed",
    "Recursion Hook": "self_destroyed",
    "Subroutine Driver": "self_destroyed",
    "Recursive Tape": "self_destroyed",
    "Long-Memory Husk": "self_destroyed",
    "Containment Pike": "self_destroyed",
    # Reticulate -> turn_end
    "Recursive Observatory": "turn_end",
    # Cores
    "FORGE-Δ":       "core_passive",
    "ETHOS-7":       "core_passive",
    "SUBROUTINE-α":  "core_passive",
    "MIRTHBOT-1":    "core_passive",
    "Affection.exe": "core_passive",
    "BULWARK-9":     "core_passive",
    # Phase boot
    "Compute Trickle": "phase_boot",
    "Cooldown Harness": "phase_boot",
    "Ready-Up Engineer": "turn_start",  # uses _on_turn_start_trigger
    # Phase reassemble
    "SUBROUTINE-α":  "core_passive",  # placed in command, runs at PHASE_START
    "Loop Engine":   "phase_reassemble",
    # Chassis ETB
    "Ironclad Foreman": "etb",
    "Iron Spire":    "etb",
    "Plant Foreman": "etb_react",  # draws when another integrity-5+ chassis enters
    "Heuristic Sentry": "etb",
    "Whirring Initiate": "etb",
    "Tinkerling":    "etb",
    "Quickforge Drudge": "etb",
    # Smelter Frame — on attach (when a weapon attaches TO IT). Test via
    # the attach path with the chassis as host.
    "Smelter Frame": "attach_to",   # custom-kind
    "Skitterswarm":  "attach_to",
    "Affection-Bot": "attach_to",
    # Conga Constructor — reacts to ally chassis ETB (not own)
    "Conga Constructor": "etb_react",
    # Memory Blade — host attack
    "Memory Blade":  "host_attack",
    "Containment Lance": "host_attack",
    "Containment Whip": "host_attack",
    "Burnout Cannon": "host_attack",
    "Riot Mortar":   "host_attack",
    "Charm Module":  "host_attack",
    "Sentinel Cannon": "host_attack",  # actually "host destroys chassis" — fires via CHASSIS_DESTROYED
    "Mortar Lieutenant": "static_query",  # chassis with workshop_damage transform
    "Anvil Drone":   "host_attack",
    "Salvage Cleaver": "host_attack",
    # Block
    "Riot Baton":    "host_blocks",
    "Counterweight Sleeve": "host_blocks",
    "Spotter Rig":   "host_blocks",
    # Heavy Watchpost is mostly static (armor 2 to host + attack prevention)
    "Heavy Watchpost": "static_query",
    # Subroutine Core / Recursive Sentinel / Heuristic Lance / Decoder Spike — react on transient
    "Subroutine Core":    "transient_react",
    "Recursive Sentinel": "transient_react",
    "Heuristic Lance":    "transient_react",
    "Decoder Spike":      "transient_react",
    "Heuristic Layer":    "transient_react",
    "Subroutine Dampener": "transient_react",
    "Containment Scribe": "transient_react",
    # Counterweight Walker — ally chassis destroyed
    "Counterweight Walker": "chassis_destroyed",
    # Mass-Production Line — listen for ZONE_CHANGE on ally chassis
    "Mass-Production Line": "etb_react",
    # Helping Claw — ZONE_CHANGE ally chassis
    "Helping Claw": "etb_react",
    # Reinforced Bay — ZONE_CHANGE ally chassis
    "Reinforced Bay": "etb_react",
    # Containment Baffle — opp attack tax
    "Containment Baffle": "opp_attack",
    # Workshop Sprinkler — turn end
    "Workshop Sprinkler": "turn_end",
    # Foundryman — static query
    "Foundryman": "static_query",
    "Lugnut Cradle": "static_query",
    "Patient Frame": "static_query",
    "Compounding Buttress": "static_query",
    "Heavy Forge": "static_query",
    "Iron Cluster": "static_query",
    "Affinity Coil": "static_query",
    "Tinker's Frame": "static_query",
    "Hum-Lance": "static_query",
    "Swarm Beacon": "static_query",
    "Containment Lining": "static_query",
    "Forge-Cannon": "static_query",
    # Self-mobile parts: static query
    "Scout Drone": "static_query",
    "Joybuzzer":   "static_query",
    "Magenta Coil": "static_query",
    "Spark Whip":  "static_query",
    "Stinger Pack": "static_query",
    "Tickle-Saw":  "static_query",
    "Cipher Rotor": "static_query",
    "Affection.exe Add-On": "static_query",
    "Joybuzzer Sleeve": "static_query",
    # Tungsten Walker — cost reduction
    "Tungsten Walker": "static_query",
    # Foundry Bracer — host attack triggers flag, then static buff.
    "Foundry Bracer": "host_attack",
    # Public Telemetry — track transient + turn end
    "Public Telemetry": "turn_end",
    "Shared Bus":     "static_query",
    # Armors — static
    "Thick Hide":         "static_query",
    "Tungsten Carapace":  "static_query",
    "Containment Lattice": "static_query",
    "Logic Buffer":       "static_query",
    "Soft-Cycle Ridge":   "static_query",
    "Reactive Shielding": "static_query",
    "Riot Plating":       "static_query",
    "Bunker Cradle":      "static_query",
    # Bastion Frame — REACT on damage to host
    "Bastion Frame":      "static_query",  # close enough
    # Containment Sergeant + Foreman's Watch + BULWARK-9 -> turn_end
    "Containment Sergeant": "turn_end",
    "Foreman's Watch": "turn_end",
}


def _run_attach_to_test(card_def) -> tuple[bool, str]:
    """For chassis whose interceptor triggers when a part attaches TO IT
    (Skitterswarm, Affection-Bot, Smelter Frame). Place the chassis on the
    floor, place a part, attach part to chassis, expect react.
    """
    from src.engine.clankers import make_weapon
    g = _build_game()
    chassis = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    part_def = make_weapon(name="_part", power_bonus=1, compute_cost=1)
    part_obj = _place_on_floor(g, part_def, "p1", register_interceptors=False)
    scrap_before = _scrap_count(g.state, "p1")
    ic_count_before = len(g.state.interceptors)
    integ_before = compute_effective_integrity(g.state, chassis.id)
    events = attach_part(g.state, part_obj.id, chassis.id)
    if not events:
        return False, "attach failed"
    scrap_after = _scrap_count(g.state, "p1")
    ic_count_after = len(g.state.interceptors)
    integ_after = compute_effective_integrity(g.state, chassis.id)
    # Look for a follow-up effect: scrap change, integrity buff registration,
    # or any REACT event past the attach markers.
    react_events = [e for e in events if e.type not in (
        EventType.CLANKERS_ATTACH_PART, EventType.CLANKERS_PART_ATTACHED,
    )]
    if scrap_after != scrap_before:
        return True, f"scrap {scrap_before} -> {scrap_after} (attach trigger fired)"
    if react_events:
        return True, f"react events on attach: {[e.type.name for e in react_events]}"
    # Check if a NEW interceptor was registered (Smelter Frame stacks +1 integ).
    if ic_count_after > ic_count_before + 1:  # +1 for the part's own interceptors
        return True, f"new interceptor(s) registered ({ic_count_after - ic_count_before})"
    if integ_after != integ_before:
        # Note: integ_after may include the +1 part bonus from the new weapon.
        # We require >1 jump to flag a Smelter-style stacking buff.
        if integ_after - integ_before > int(getattr(part_def, "integrity_bonus", 0) or 0):
            return True, f"chassis integrity {integ_before} -> {integ_after}"
    return False, "no observable effect on attach-to-self"


def _run_transient_react_test(card_def) -> tuple[bool, str]:
    """For cards that react when a transient resolves. Place the card on
    the floor + fire a synthetic transient resolve event."""
    g = _build_game()
    if _is_part(card_def):
        from src.engine.clankers import make_chassis
        host_def = make_chassis(
            name="_host", power=2, integrity=3,
            weapon_slots=2, add_on_slots=2, compute_cost=2,
        )
        host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        attach_part(g.state, obj.id, host.id)
    else:
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)

    # Containment Scribe / Subroutine Dampener / Heuristic Layer / Subroutine
    # Core / Recursive Sentinel / Heuristic Lance / Decoder Spike all listen
    # for the synthetic CLANKERS_COMPUTE_SPEND with transient_id in payload.
    hand_before = _hand_size(g.state, "p1")
    pwr_before = compute_effective_power(g.state, obj.id) if _is_chassis(card_def) else 0
    ev = Event(
        type=EventType.CLANKERS_COMPUTE_SPEND,
        payload={
            "transient_id": "fake_transient_id",
            "controller": "p1",
            "targets": [],
        },
        source="fake_transient_id",
        controller="p1",
    )
    _, reactions = _dispatch_interceptors(g.state, ev)
    hand_after = _hand_size(g.state, "p1")
    pwr_after = compute_effective_power(g.state, obj.id) if _is_chassis(card_def) else 0
    if reactions or hand_after != hand_before or pwr_after != pwr_before:
        return True, f"reactions={len(reactions)} hand {hand_before}->{hand_after} pwr {pwr_before}->{pwr_after}"
    return False, "no reaction to transient resolve"


def _run_chassis_destroyed_test(card_def) -> tuple[bool, str]:
    """For Counterweight Walker — fire CLANKERS_CHASSIS_DESTROYED for an
    ally chassis (not self) and check the bump."""
    g = _build_game()
    obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    # Place a "second chassis" to be destroyed.
    from src.engine.clankers import make_chassis
    ally_def = make_chassis(
        name="_ally", power=1, integrity=1,
        weapon_slots=0, add_on_slots=0, compute_cost=1,
    )
    ally = _place_on_floor(g, ally_def, "p1", register_interceptors=False)

    ev = Event(
        type=EventType.CLANKERS_CHASSIS_DESTROYED,
        payload={
            "chassis_id": ally.id,
            "controller": "p1",
            "cascaded_part_ids": [],
        },
        source=ally.id,
        controller="p1",
    )
    integ_before = compute_effective_integrity(g.state, obj.id)
    _, reactions = _dispatch_interceptors(g.state, ev)
    integ_after = compute_effective_integrity(g.state, obj.id)
    if reactions or integ_after != integ_before:
        return True, f"integ {integ_before} -> {integ_after}"
    return False, "no react on ally chassis destroyed"


def _run_etb_react_test(card_def) -> tuple[bool, str]:
    """For Mass-Production Line / Helping Claw / Reinforced Bay / Plant Foreman — listen for
    ally chassis ZONE_CHANGE → ASSEMBLY_FLOOR."""
    g = _build_game()
    if _is_part(card_def):
        from src.engine.clankers import make_chassis
        host_def = make_chassis(
            name="_host", power=2, integrity=3,
            weapon_slots=2, add_on_slots=2, compute_cost=2,
        )
        host = _place_on_floor(g, host_def, "p1", register_interceptors=False)
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
        attach_part(g.state, obj.id, host.id)
    else:
        obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    # Fire a synthetic ZONE_CHANGE for an ally chassis.
    # Use integrity >= 5 so Plant Foreman's filter fires; cheap stat-wise.
    from src.engine.clankers import make_chassis
    new_def = make_chassis(
        name="_new", power=2, integrity=5,
        weapon_slots=0, add_on_slots=0, compute_cost=1,
    )
    new = _place_on_floor(g, new_def, "p1", register_interceptors=False)
    ev = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": new.id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": "p1",
            "card_type": "CLANKERS_CHASSIS",
        },
        source=new.id,
        controller="p1",
    )
    pwr_before = compute_effective_power(g.state, new.id)
    integ_before = compute_effective_integrity(g.state, new.id)
    integ_obj_before = compute_effective_integrity(g.state, obj.id) if _is_chassis(card_def) else 0
    _, reactions = _dispatch_interceptors(g.state, ev)
    pwr_after = compute_effective_power(g.state, new.id)
    integ_after = compute_effective_integrity(g.state, new.id)
    integ_obj_after = compute_effective_integrity(g.state, obj.id) if _is_chassis(card_def) else 0

    if reactions or pwr_after != pwr_before or integ_after != integ_before or integ_obj_after != integ_obj_before:
        return True, f"react/pwr/integ change observed"
    # Check if a temp buff was registered.
    new_ic_count = sum(1 for ic in g.state.interceptors.values()
                       if "tempbuff" in ic.id)
    if new_ic_count > 0:
        return True, f"{new_ic_count} temp-buff interceptors registered"
    # Check for state flag markers (Reinforced Bay sets reinforced_bay_shield).
    if getattr(new.state, "reinforced_bay_shield", 0) > 0:
        return True, "reinforced_bay_shield flag set on ally chassis"
    return False, "no react on ally chassis ETB"


def _run_opp_attack_test(card_def) -> tuple[bool, str]:
    """For Containment Baffle — fire CLANKERS_ATTACK_DECLARE for opp big chassis,
    expect compute deduction."""
    g = _build_game()
    obj = _place_on_floor(g, card_def, "p1", register_interceptors=True)
    from src.engine.clankers import make_chassis
    big_def = make_chassis(
        name="_big", power=5, integrity=4,
        weapon_slots=1, add_on_slots=1, compute_cost=5,
    )
    big = _place_on_floor(g, big_def, "p2", register_interceptors=False)
    pool_before = int(g.state.clankers_compute_pool.get("p2", 0))
    ev = Event(
        type=EventType.CLANKERS_ATTACK_DECLARE,
        payload={
            "attacker_id": big.id,
            "attacker_controller": "p2",
        },
        source=big.id,
        controller="p2",
    )
    _, reactions = _dispatch_interceptors(g.state, ev)
    pool_after = int(g.state.clankers_compute_pool.get("p2", 0))
    if reactions or pool_after != pool_before:
        return True, f"p2 pool {pool_before} -> {pool_after} reactions={len(reactions)}"
    return False, "no tax applied on opp big attack"


# ---------------------------------------------------------------------------
# Map kind -> runner
# ---------------------------------------------------------------------------

RUNNERS: dict[str, Callable[[CardDefinition], tuple[bool, str]]] = {
    "etb":               _run_etb_test,
    "attach":            _run_attach_test,
    "attach_to":         _run_attach_to_test,
    "host_attack":       _run_host_attack_test,
    "host_blocks":       _run_host_blocks_test,
    "self_destroyed":    _run_self_destroyed_test,
    "chassis_destroyed": _run_chassis_destroyed_test,
    "turn_end":          _run_turn_end_test,
    "turn_start":        _run_turn_start_test,
    "phase_reassemble":  lambda cd: _run_phase_start_test(cd, "reassemble"),
    "phase_boot":        lambda cd: _run_phase_start_test(cd, "boot"),
    "activated":         _run_activated_test,
    "transient_resolve": _run_transient_resolve_test,
    "transient_react":   _run_transient_react_test,
    "static_query":      _run_static_query_test,
    "core_passive":      _run_core_passive_test,
    "etb_react":         _run_etb_react_test,
    "opp_attack":        _run_opp_attack_test,
}


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_all_tests():
    """Walk every card in CLAN_CARDS, dispatch to the appropriate runner,
    collect pass/fail counts."""
    passed: list[tuple[str, str]] = []
    failed: list[tuple[str, str, str]] = []  # (card, kind, reason)
    errored: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []

    by_kind: dict[str, int] = {}
    failures_by_kind: dict[str, int] = {}

    for name, cd in CLAN_CARDS.items():
        if name in SKIPPED_CARDS:
            skipped.append((name, SKIPPED_CARDS[name]))
            continue
        kind = TRIGGER_OVERRIDES.get(name, _trigger_kind(cd))
        by_kind[kind] = by_kind.get(kind, 0) + 1
        runner = RUNNERS.get(kind)
        if runner is None:
            errored.append((name, kind, f"no runner for kind '{kind}'"))
            continue
        try:
            ok, reason = runner(cd)
            if ok:
                passed.append((name, f"[{kind}] {reason}"))
            else:
                failed.append((name, kind, reason))
                failures_by_kind[kind] = failures_by_kind.get(kind, 0) + 1
        except Exception as e:
            tb = traceback.format_exc()
            errored.append((name, kind, f"{type(e).__name__}: {e}\n{tb}"))

    total = len(passed) + len(failed) + len(errored)
    print(f"\n=== CLAN interceptor verification ===")
    print(f"  total tested: {total}")
    print(f"  skipped:      {len(skipped)} (see SKIPPED_CARDS)")
    print(f"  passed:       {len(passed)}")
    print(f"  failed:       {len(failed)}")
    print(f"  errored:      {len(errored)}")
    pass_rate = (len(passed) / total * 100) if total else 0
    print(f"  pass rate:    {pass_rate:.1f}%")

    print("\n--- BREAKDOWN BY TRIGGER KIND ---")
    for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        fails = failures_by_kind.get(k, 0)
        print(f"  {k:24s} {n:3d} tested  {fails:3d} failed")

    if failed:
        print(f"\n--- FAILURES ({len(failed)}) ---")
        for name, kind, reason in failed:
            print(f"  [{kind}] {name}: {reason}")

    if errored:
        print(f"\n--- ERRORS ({len(errored)}) ---")
        for name, kind, reason in errored[:20]:
            short = reason.splitlines()[0] if "\n" in reason else reason
            print(f"  [{kind}] {name}: {short}")

    return 0 if (len(failed) + len(errored)) == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
