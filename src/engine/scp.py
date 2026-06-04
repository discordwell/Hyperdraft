"""SCP: SECURE / CONTAIN / SUBVERT — asymmetric engine core.

Foundation (the builder) vs Chaos Insurgency (the disruptor), modeled on Netrunner.
See docs/design/scp_rules.md for the full ruleset. This module is the pure-Python
engine: state model, card constructors, the action verbs, the infiltration (run)
resolution, and the symmetric win check. No server/frontend dependencies.

Design invariants worth keeping in mind while reading:
  * There is NO self-inflicted loss. Each faction's win is the other's loss (§7 of the
    spec). ``check_scp_win`` is the single arbiter, run as a state-based action.
  * Installed cards live on the shared ``battlefield`` zone; the board *structure*
    (which cell, which layer stack, the rig) is tracked in ``state.scp_state`` indexes,
    mirroring how scp.py uses ``scp_anomalies`` etc.
  * Per-object scp data (advancement, face-down, rezzed) lives on ``obj.state`` as
    dynamic ``scp_*`` attrs (ObjectState is a plain dataclass, no __slots__).
  * Total Breach is a single shared clock kept on the Foundation's record (its
    containment is what's failing).
"""

from __future__ import annotations

import random
from typing import Any, Callable, Optional

from .types import (
    CardDefinition,
    Characteristics,
    CardType,
    Event,
    EventType,
    GameState,
    GameObject,
    Player,
    Zone,
    ZoneType,
)

# ---------------------------------------------------------------------------
# Constants (initial values — tuned in Phase 4; see spec §10)
# ---------------------------------------------------------------------------
FOUNDATION = "foundation"
INSURGENCY = "insurgency"

AP_PER_TURN = 4             # Phase-4 tuned 3→4: the Foundation's plan is action-heavy
STARTING_CREDITS = 5
GAIN_AMOUNT = 2
DRAW_PER_TURN = 1
MAX_HAND = 5

CONTAINMENT_TARGET = 6      # Foundation primary win (Phase-4 tuned 7→6)
LIBERATION_TARGET = 7       # Insurgency primary win
BREACH_CATASTROPHE = 24     # Insurgency secondary win, "unleash" (10→14→16→24). The 16 era was a
                            # HOLLOW breach axis: the breach deck ran Black Queen and actually won by
                            # *liberation*. Giving it the Sarkic Cult identity (breach events +1) made
                            # breach a real engine — and explosive (~85% vs Foundation at 16). With a
                            # real engine + Foundation counterplay (Containment Sweep) the bar must be
                            # higher: 24 restores ~50/50 (mean Found 52% / 480 games) with breach a
                            # live-but-fair ~1/4 of wins. Re-tune this whenever the breach engine changes.
# How much of a freed anomaly's value (or its breach_on_free override) flows into the shared
# Total Breach clock. 1.0 = full (a freed anomaly's Value is also its Breach). A balance knob
# (Phase 4): freeing already banks Liberation, so the Breach contribution can be < 1.0 to keep
# the Foundation's advance-in-the-open from feeding its own loss-con too hard.
BREACH_FREE_MULTIPLIER = 1.0

LAYER_TYPES = ("barrier", "sentry", "sensor")
CENTRALS = ("hq", "research", "archives")

# Default subroutine per layer type (a card may override via scp_sub).
_DEFAULT_SUB = {"barrier": "end_run", "sentry": "neutralize", "sensor": "expose"}


# ---------------------------------------------------------------------------
# Per-player state model
# ---------------------------------------------------------------------------
def _player_defaults(faction: str) -> dict[str, Any]:
    return {
        "faction": faction,
        "credits": STARTING_CREDITS,
        "ap": 0,
        # win counters
        "containment_points": 0,   # Foundation
        "liberation_points": 0,    # Insurgency
        "total_breach": 0,         # kept on the Foundation record; shared clock
        # Insurgency status
        "exposed": 0,              # tag count
        "burned_out": False,       # flatline flag → Foundation soft-kill win
        # board structure
        "cells": [],               # Foundation: [{"id", "anomaly": obj_id|None, "layers": [obj_id]}]
        "centrals": {c: [] for c in CENTRALS},  # Foundation: layer stacks on HQ/Research/Archives
        "assets": [],              # Foundation: installed asset obj_ids
        "rig": [],                 # Insurgency: installed operative/tool obj_ids
        "next_cell_id": 1,
    }


def ensure_scp_state(state: GameState, player_id: str, faction: Optional[str] = None) -> dict:
    rec = state.scp_state.get(player_id)
    if rec is None:
        rec = _player_defaults(faction or FOUNDATION)
        state.scp_state[player_id] = rec
    if faction:
        rec["faction"] = faction
    for key, value in _player_defaults(rec["faction"]).items():
        rec.setdefault(key, value)
    return rec


def setup_scp_player(game, player: Player, faction: str) -> None:
    """Initialise a player as a Foundation site or an Insurgency cell network."""
    player.life = 0
    player.max_life = 0
    player.has_lost = False
    ensure_scp_state(game.state, player.id, faction)
    # The shared battlefield zone holds installed cards; create it if missing
    # (per-player library/hand/graveyard are made by Game.add_player).
    if "battlefield" not in game.state.zones:
        game.state.zones["battlefield"] = Zone(type=ZoneType.BATTLEFIELD, owner=None)


def rec(state: GameState, player_id: str) -> dict:
    return ensure_scp_state(state, player_id)


def faction_of(state: GameState, player_id: str) -> str:
    return ensure_scp_state(state, player_id)["faction"]


def _player_with_faction(state: GameState, faction: str) -> Optional[str]:
    for pid in state.players:
        if faction_of(state, pid) == faction:
            return pid
    return None


def foundation_id(state: GameState) -> Optional[str]:
    return _player_with_faction(state, FOUNDATION)


def insurgency_id(state: GameState) -> Optional[str]:
    return _player_with_faction(state, INSURGENCY)


def opponent_of(state: GameState, player_id: str) -> Optional[str]:
    for pid in state.players:
        if pid != player_id:
            return pid
    return None


# ---------------------------------------------------------------------------
# Card constructors
# ---------------------------------------------------------------------------
def _card(name: str, ctype: CardType, text: str = "", **attrs: Any) -> CardDefinition:
    cd = CardDefinition(
        name=name,
        mana_cost=None,
        domain="SCP",
        text=text,
        characteristics=Characteristics(types={ctype}),
    )
    cd.scp_kind = ctype
    for key, value in attrs.items():
        setattr(cd, "scp_" + key, value)
    return cd


def make_anomaly(name: str, threshold: int, value: int, *, trap: bool = False,
                 cost: int = 0, text: str = "", on_contain: Optional[Callable] = None,
                 on_free: Optional[Callable] = None, on_access: Optional[Callable] = None,
                 breach_on_free: Optional[int] = None) -> CardDefinition:
    """Foundation agenda. ``threshold`` advancement to lock; ``value`` points when contained.

    A ``trap`` looks like an anomaly (advanceable, fogged) but punishes on access via
    ``on_access`` (default: deal 2 damage). ``breach_on_free`` overrides how much a freed
    real anomaly adds to Total Breach (defaults to its value).
    """
    return _card(name, CardType.SCP_ANOMALY, text, threshold=threshold, value=value,
                 trap=trap, cost=cost, on_contain=on_contain, on_free=on_free,
                 on_access=on_access, breach_on_free=breach_on_free)


def make_layer(name: str, ltype: str, strength: int, rez: int, *,
               sub: Optional[str] = None, text: str = "") -> CardDefinition:
    """Foundation containment layer (ICE). ``ltype`` in LAYER_TYPES; ``sub`` overrides the
    default subroutine for that type (end_run / neutralize / expose / damage2 / discard)."""
    assert ltype in LAYER_TYPES, f"bad layer type {ltype}"
    return _card(name, CardType.SCP_LAYER, text, ltype=ltype, strength=strength,
                 rez=rez, sub=sub or _DEFAULT_SUB[ltype])


def make_asset(name: str, *, cost: int = 0, text: str = "",
               on_install: Optional[Callable] = None,
               on_turn_start: Optional[Callable] = None,
               ability: Optional[Callable] = None,
               ability_cost: int = 0, ability_ap: int = 1) -> CardDefinition:
    """Foundation persistent. ``ability(game, pid, obj, target)`` is an activated ability
    costing ``ability_ap`` AP + ``ability_cost`` Funding (fired via ``activate_ability``)."""
    return _card(name, CardType.SCP_ASSET, text, cost=cost, on_install=on_install,
                 on_turn_start=on_turn_start, ability=ability,
                 ability_cost=ability_cost, ability_ap=ability_ap)


def make_operation(name: str, *, cost: int = 0, text: str = "",
                   effect: Optional[Callable] = None) -> CardDefinition:
    return _card(name, CardType.SCP_OPERATION, text, cost=cost, effect=effect)


def make_operative(name: str, breaks: str, power: int, *, boost: int = 1,
                   cost: int = 0, text: str = "") -> CardDefinition:
    """Insurgency breaker. Breaks layers of type ``breaks``; ``power`` base, ``boost`` Cells
    per +1 power for the encounter."""
    assert breaks in LAYER_TYPES, f"bad break type {breaks}"
    return _card(name, CardType.SCP_OPERATIVE, text, breaks=breaks, power=power,
                 boost=boost, cost=cost)


def make_tool(name: str, *, cost: int = 0, text: str = "",
              on_install: Optional[Callable] = None,
              ability: Optional[Callable] = None,
              ability_cost: int = 0, ability_ap: int = 1) -> CardDefinition:
    """Insurgency persistent. ``ability(game, pid, obj, target)`` is an activated ability
    costing ``ability_ap`` AP + ``ability_cost`` Cells (fired via ``activate_ability``)."""
    return _card(name, CardType.SCP_TOOL, text, cost=cost, on_install=on_install,
                 ability=ability, ability_cost=ability_cost, ability_ap=ability_ap)


def make_event(name: str, *, cost: int = 0, text: str = "",
               effect: Optional[Callable] = None) -> CardDefinition:
    return _card(name, CardType.SCP_EVENT, text, cost=cost, effect=effect)


def make_identity(name: str, faction: str, *, text: str = "",
                  passive: Optional[Callable] = None) -> CardDefinition:
    return _card(name, CardType.SCP_IDENTITY, text, faction=faction, passive=passive)


# ---------------------------------------------------------------------------
# Zones / movement / draw
# ---------------------------------------------------------------------------
def _zkey(ztype: ZoneType, owner: str) -> str:
    return f"{ztype.name.lower()}_{owner}"


def hand_ids(state: GameState, player_id: str) -> list[str]:
    z = state.zones.get(_zkey(ZoneType.HAND, player_id))
    return list(z.objects) if z else []


def deck_ids(state: GameState, player_id: str) -> list[str]:
    z = state.zones.get(_zkey(ZoneType.LIBRARY, player_id))
    return list(z.objects) if z else []


def discard_ids(state: GameState, player_id: str) -> list[str]:
    z = state.zones.get(_zkey(ZoneType.GRAVEYARD, player_id))
    return list(z.objects) if z else []


def _relocate(game, obj: GameObject, to_zone: ZoneType, *, source: Optional[str] = None) -> list[Event]:
    """Move an object between zones, keeping zone object-lists and obj.zone in sync, and
    emit a ZONE_CHANGE so interceptors/replays observe it."""
    state = game.state
    # remove from current zone list
    from_key = ("battlefield" if obj.zone in (ZoneType.BATTLEFIELD,)
                else _zkey(obj.zone, obj.owner))
    fz = state.zones.get(from_key)
    if fz and obj.id in fz.objects:
        fz.objects.remove(obj.id)
    to_key = "battlefield" if to_zone == ZoneType.BATTLEFIELD else _zkey(to_zone, obj.owner)
    if to_key not in state.zones and to_zone == ZoneType.BATTLEFIELD:
        state.zones[to_key] = Zone(type=ZoneType.BATTLEFIELD, owner=None)
    tz = state.zones.get(to_key)
    obj.zone = to_zone
    if tz and obj.id not in tz.objects:
        tz.objects.append(obj.id)
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={"object_id": obj.id, "to_zone_type": to_zone, "to_zone": to_key},
        source=source or obj.id,
        controller=obj.controller,
    ))


def draw_cards(game, player_id: str, n: int = 1) -> list[Event]:
    """Move the top ``n`` library cards to hand. Decking out is not an scp loss (the
    spec has no self-inflicted loss); an empty library simply draws nothing."""
    state = game.state
    events: list[Event] = []
    for _ in range(n):
        dz = state.zones.get(_zkey(ZoneType.LIBRARY, player_id))
        if not dz or not dz.objects:
            break
        top = dz.objects[-1]
        obj = state.objects.get(top)
        if obj is None:
            dz.objects.pop()
            continue
        events.extend(_relocate(game, obj, ZoneType.HAND))
        events.append(Event(type=EventType.DRAW, payload={"player": player_id, "object_id": top}))
    return events


def _emit(game, etype: EventType, controller: Optional[str] = None, **payload: Any) -> list[Event]:
    return game.emit(Event(type=etype, payload=payload, source="SCP_SYSTEM", controller=controller))


# ---------------------------------------------------------------------------
# Resource / AP helpers
# ---------------------------------------------------------------------------
def reset_turn_resources(state: GameState, player_id: str) -> None:
    r = ensure_scp_state(state, player_id)
    r["ap"] = AP_PER_TURN


def _spend_ap(r: dict, n: int = 1) -> bool:
    if r["ap"] < n:
        return False
    r["ap"] -= n
    return True


def _spend_credits(r: dict, n: int) -> bool:
    if r["credits"] < n:
        return False
    r["credits"] -= n
    return True


# ---------------------------------------------------------------------------
# Card-effect helpers — the vocabulary card closures call. Each is a thin,
# directly-callable function (no AP/credit gate; the playing verb already paid
# that). They mutate the per-player record and emit the matching event so the
# log/frontend observe the effect. Used by card on_*/effect/ability closures.
# ---------------------------------------------------------------------------
def add_credits(state: GameState, player_id: str, n: int) -> list[Event]:
    ensure_scp_state(state, player_id)["credits"] = max(0, ensure_scp_state(state, player_id)["credits"] + n)
    return []


def add_liberation(state: GameState, player_id: str, n: int) -> list[Event]:
    ensure_scp_state(state, player_id)["liberation_points"] += n
    return []


def add_containment(state: GameState, player_id: str, n: int) -> list[Event]:
    ensure_scp_state(state, player_id)["containment_points"] += n
    return []


def add_breach(game, n: int) -> list[Event]:
    """Raise the shared Total Breach clock (kept on the Foundation record). A breach-doctrine
    Insurgency identity (Sarkic Cult) adds ``breach_event_bonus`` to every breach event — this is
    the only path breach events take, so the bonus lands exactly on Leak/Wetwork/Anonymous Tip."""
    state = game.state
    fid = foundation_id(state)
    if fid is None:
        return []
    iid = insurgency_id(state)
    if iid is not None:
        n += int(ensure_scp_state(state, iid).get("breach_event_bonus", 0))
    fr = ensure_scp_state(state, fid)
    fr["total_breach"] += n
    return _emit(game, EventType.SCP_BREACH, amount=n, total_breach=fr["total_breach"])


def reduce_breach(game, n: int) -> list[Event]:
    """Roll the shared Total Breach clock back down (Foundation counterplay to the breach axis).
    Clamps at 0 — the Foundation re-contains loosed material rather than reversing past 'safe'."""
    state = game.state
    fid = foundation_id(state)
    if fid is None:
        return []
    fr = ensure_scp_state(state, fid)
    before = fr["total_breach"]
    fr["total_breach"] = max(0, before - n)
    return _emit(game, EventType.SCP_BREACH, amount=fr["total_breach"] - before,
                 total_breach=fr["total_breach"])


def expose(game, n: int = 1) -> list[Event]:
    """Tag the Insurgency (enables Foundation soft-kill punishment)."""
    state = game.state
    iid = insurgency_id(state)
    if iid is None:
        return []
    ir = ensure_scp_state(state, iid)
    ir["exposed"] = int(ir.get("exposed", 0)) + n
    return _emit(game, EventType.SCP_EXPOSE, controller=iid, player=iid, amount=n)


def mill(game, player_id: str, n: int) -> list[Event]:
    """Trash the top ``n`` cards of ``player_id``'s deck to discard (Research sabotage)."""
    state = game.state
    events: list[Event] = []
    for _ in range(n):
        dz = state.zones.get(_zkey(ZoneType.LIBRARY, player_id))
        if not dz or not dz.objects:
            break
        top = state.objects.get(dz.objects[-1])
        if top is None:
            dz.objects.pop()
            continue
        events.extend(_relocate(game, top, ZoneType.GRAVEYARD))
    return events


def reinforce(state: GameState, layer_obj: GameObject, n: int) -> list[Event]:
    """Permanently raise a layer's effective strength (Foundation reinforcement tech)."""
    layer_obj.state.scp_strength_mod = int(getattr(layer_obj.state, "scp_strength_mod", 0)) + n
    return []


def trash_a_tool(game) -> list[Event]:
    """Foundation soft-kill: trash one installed Insurgency tool (or operative if no tool)."""
    state = game.state
    iid = insurgency_id(state)
    if iid is None:
        return []
    ir = ensure_scp_state(state, iid)
    for role in ("tool", "operative"):
        for oid in list(ir["rig"]):
            obj = state.objects.get(oid)
            if obj and getattr(obj.state, "scp_role", None) == role:
                ir["rig"].remove(oid)
                return _relocate(game, obj, ZoneType.GRAVEYARD)
    return []


def _effective_strength(state: GameState, layer: GameObject) -> int:
    """A layer's strength after reinforcement modifiers (read at break-check time)."""
    base = int(getattr(layer.card_def, "scp_strength", 0) or 0)
    mod = int(getattr(layer.state, "scp_strength_mod", 0) or 0)
    return max(0, base + mod)


# ---------------------------------------------------------------------------
# Shared verbs
# ---------------------------------------------------------------------------
def gain_credits(game, player_id: str) -> tuple[bool, str, list[Event]]:
    r = ensure_scp_state(game.state, player_id)
    if not _spend_ap(r):
        return False, "No actions left", []
    r["credits"] += GAIN_AMOUNT
    return True, "", []


def draw_action(game, player_id: str) -> tuple[bool, str, list[Event]]:
    r = ensure_scp_state(game.state, player_id)
    if not _spend_ap(r):
        return False, "No actions left", []
    return True, "", draw_cards(game, player_id, 1)


def play_card(game, player_id: str, card_id: str, *, cell_id: Optional[int] = None,
              target: Optional[tuple] = None) -> tuple[bool, str, list[Event]]:
    """Spend 1 AP + the card's credit cost to install a card or resolve a one-shot."""
    state = game.state
    r = ensure_scp_state(state, player_id)
    obj = state.objects.get(card_id)
    if not obj or obj.owner != player_id or obj.zone != ZoneType.HAND:
        return False, "Card not in hand", []
    cd = obj.card_def
    kind = getattr(cd, "scp_kind", None)
    cost = int(getattr(cd, "scp_cost", 0) or 0)
    if r["ap"] < 1:
        return False, "No actions left", []
    if r["credits"] < cost:
        return False, "Insufficient credits", []
    r["ap"] -= 1
    r["credits"] -= cost
    events: list[Event] = []

    if kind == CardType.SCP_ANOMALY:
        events.extend(_install_anomaly(game, player_id, obj, cell_id))
    elif kind == CardType.SCP_LAYER:
        events.extend(_install_layer(game, player_id, obj, target, cell_id))
    elif kind in (CardType.SCP_ASSET, CardType.SCP_TOOL, CardType.SCP_OPERATIVE):
        events.extend(_install_persistent(game, player_id, obj, kind))
    elif kind in (CardType.SCP_OPERATION, CardType.SCP_EVENT):
        effect = getattr(cd, "scp_effect", None)
        if callable(effect):
            events.extend(effect(game, player_id) or [])
        events.extend(_relocate(game, obj, ZoneType.GRAVEYARD))
    else:
        return False, f"Cannot play card of kind {kind}", []

    events = _emit(game, EventType.SCP_INSTALL, controller=player_id,
                   player=player_id, object_id=card_id,
                   kind=(kind.name if kind else None)) + events
    events.extend(check_scp_win(game))
    return True, "", events


def _new_cell(r: dict) -> dict:
    cell = {"id": r["next_cell_id"], "anomaly": None, "layers": []}
    r["next_cell_id"] += 1
    r["cells"].append(cell)
    return cell


def _find_cell(r: dict, cell_id: Optional[int]) -> Optional[dict]:
    if cell_id is None:
        return None
    for cell in r["cells"]:
        if cell["id"] == cell_id:
            return cell
    return None


def _install_anomaly(game, player_id: str, obj: GameObject, cell_id: Optional[int]) -> list[Event]:
    r = ensure_scp_state(game.state, player_id)
    cell = _find_cell(r, cell_id)
    if cell is None or cell["anomaly"] is not None:
        cell = _new_cell(r)
    cell["anomaly"] = obj.id
    obj.state.scp_role = "anomaly"
    obj.state.scp_facedown = True
    obj.state.scp_advancement = 0
    obj.state.scp_cell = cell["id"]
    obj.state.scp_status = "advancing"
    return _relocate(game, obj, ZoneType.BATTLEFIELD)


def _install_layer(game, player_id: str, obj: GameObject, target: Optional[tuple],
                   cell_id: Optional[int]) -> list[Event]:
    r = ensure_scp_state(game.state, player_id)
    obj.state.scp_role = "layer"
    obj.state.scp_facedown = True
    obj.state.scp_rezzed = False
    # target = ("central", name) installs on a central; otherwise onto a cell
    if target and target[0] == "central" and target[1] in CENTRALS:
        r["centrals"][target[1]].append(obj.id)
        obj.state.scp_guard = ("central", target[1])
    else:
        cid = cell_id if cell_id is not None else (target[1] if target and target[0] == "cell" else None)
        cell = _find_cell(r, cid) or (r["cells"][-1] if r["cells"] else _new_cell(r))
        cell["layers"].append(obj.id)
        obj.state.scp_guard = ("cell", cell["id"])
    return _relocate(game, obj, ZoneType.BATTLEFIELD)


def _install_persistent(game, player_id: str, obj: GameObject, kind: CardType) -> list[Event]:
    r = ensure_scp_state(game.state, player_id)
    obj.state.scp_role = {CardType.SCP_ASSET: "asset", CardType.SCP_TOOL: "tool",
                           CardType.SCP_OPERATIVE: "operative"}[kind]
    obj.state.scp_facedown = (kind == CardType.SCP_ASSET)  # Foundation assets install hidden
    (r["assets"] if kind == CardType.SCP_ASSET else r["rig"]).append(obj.id)
    events = _relocate(game, obj, ZoneType.BATTLEFIELD)
    on_install = getattr(obj.card_def, "scp_on_install", None)
    if callable(on_install):
        events.extend(on_install(game, player_id, obj) or [])
    return events


def activate_ability(game, player_id: str, card_id: str, *,
                     target: Optional[tuple] = None) -> tuple[bool, str, list[Event]]:
    """Activate an installed asset/tool ability: spend its AP + credit cost, run its closure.

    The card declares ``scp_ability_ap`` (default 1) and ``scp_ability_cost`` (default 0).
    Closure signature: ``ability(game, player_id, obj, target) -> list[Event]``.
    """
    state = game.state
    r = ensure_scp_state(state, player_id)
    obj = state.objects.get(card_id)
    if not obj or obj.controller != player_id or obj.zone != ZoneType.BATTLEFIELD:
        return False, "Not your installed card", []
    ability = getattr(obj.card_def, "scp_ability", None)
    if not callable(ability):
        return False, "No activated ability", []
    ap_cost = int(getattr(obj.card_def, "scp_ability_ap", 1) or 0)
    credit_cost = int(getattr(obj.card_def, "scp_ability_cost", 0) or 0)
    if r["ap"] < ap_cost:
        return False, "No actions left", []
    if r["credits"] < credit_cost:
        return False, "Insufficient credits", []
    r["ap"] -= ap_cost
    r["credits"] -= credit_cost
    events = _emit(game, EventType.SCP_ACTIVATE, controller=player_id,
                   player=player_id, object_id=card_id)
    events.extend(ability(game, player_id, obj, target) or [])
    events.extend(check_scp_win(game))
    return True, "", events


# ---------------------------------------------------------------------------
# Foundation verbs: advance / contain
# ---------------------------------------------------------------------------
def advance(game, player_id: str, anomaly_id: str) -> tuple[bool, str, list[Event]]:
    """Foundation: spend 1 AP + 1 credit to place an advancement token (public)."""
    state = game.state
    r = ensure_scp_state(state, player_id)
    obj = state.objects.get(anomaly_id)
    if not obj or obj.controller != player_id or getattr(obj.state, "scp_role", None) != "anomaly":
        return False, "Not your anomaly", []
    if getattr(obj.state, "scp_status", None) != "advancing":
        return False, "Anomaly is not advanceable", []
    if r["ap"] < 1:
        return False, "No actions left", []
    if r["credits"] < 1:
        return False, "Insufficient credits", []
    r["ap"] -= 1
    r["credits"] -= 1
    obj.state.scp_advancement = int(getattr(obj.state, "scp_advancement", 0)) + 1
    return True, "", _emit(game, EventType.SCP_ADVANCE, controller=player_id,
                           player=player_id, object_id=anomaly_id,
                           advancement=obj.state.scp_advancement)


def contain(game, player_id: str, anomaly_id: str) -> tuple[bool, str, list[Event]]:
    """Foundation: lock an anomaly whose advancement met its threshold → score its value."""
    state = game.state
    r = ensure_scp_state(state, player_id)
    obj = state.objects.get(anomaly_id)
    if not obj or obj.controller != player_id or getattr(obj.state, "scp_role", None) != "anomaly":
        return False, "Not your anomaly", []
    cd = obj.card_def
    threshold = int(getattr(cd, "scp_threshold", 0) or 0)
    if int(getattr(obj.state, "scp_advancement", 0)) < threshold:
        return False, "Not enough advancement to contain", []
    if r["ap"] < 1:
        return False, "No actions left", []
    r["ap"] -= 1
    value = int(getattr(cd, "scp_value", 0) or 0)
    obj.state.scp_status = "contained"
    obj.state.scp_facedown = False
    # remove from its cell's anomaly slot (the cell may keep its layers)
    for cell in r["cells"]:
        if cell.get("anomaly") == anomaly_id:
            cell["anomaly"] = None
    r["containment_points"] += value
    events = _emit(game, EventType.SCP_CONTAIN, controller=player_id,
                   player=player_id, object_id=anomaly_id, value=value,
                   containment_points=r["containment_points"])
    on_contain = getattr(cd, "scp_on_contain", None)
    if callable(on_contain):
        events.extend(on_contain(game, player_id, obj) or [])
    events.extend(check_scp_win(game))
    return True, "", events


# ---------------------------------------------------------------------------
# Insurgency verb: infiltrate (the run) + damage
# ---------------------------------------------------------------------------
def _layer_stack(state: GameState, fid: str, target: tuple) -> list[str]:
    fr = ensure_scp_state(state, fid)
    if target[0] == "central":
        return fr["centrals"].get(target[1], [])
    cell = _find_cell(fr, target[1])
    return cell["layers"] if cell else []


def _can_break(state: GameState, insurgent_id: str, layer: GameObject) -> tuple[bool, int]:
    """Does the Insurgency control a breaker that can crack this layer, and at what Cell cost?"""
    ir = ensure_scp_state(state, insurgent_id)
    ltype = getattr(layer.card_def, "scp_ltype", None)
    strength = _effective_strength(state, layer)
    best: Optional[int] = None
    for oid in ir["rig"]:
        op = state.objects.get(oid)
        if not op or getattr(op.state, "scp_role", None) != "operative":
            continue
        if getattr(op.card_def, "scp_breaks", None) != ltype:
            continue
        power = int(getattr(op.card_def, "scp_power", 0) or 0)
        boost = max(1, int(getattr(op.card_def, "scp_boost", 1) or 1))
        deficit = max(0, strength - power)
        cost = deficit * boost
        if power + (ir["credits"] // boost) >= strength:
            if best is None or cost < best:
                best = cost
    return (best is not None), (best or 0)


def deal_damage(game, insurgent_id: str, n: int) -> list[Event]:
    """Discard ``n`` random cards from the Insurgency's hand. Damage with an empty hand =
    burned out (flatline) → Foundation soft-kill win (resolved by check_scp_win)."""
    state = game.state
    ir = ensure_scp_state(state, insurgent_id)
    # Foundation kill-identity (Overseer Council): punishment bites +1 harder while the Insurgency
    # is exposed (tag-then-burn). Backward-compatible — damage_bonus defaults to 0 otherwise.
    fid = foundation_id(state)
    if fid is not None and int(ir.get("exposed", 0)) > 0:
        n += int(ensure_scp_state(state, fid).get("damage_bonus", 0))
    events: list[Event] = []
    for _ in range(n):
        hand = hand_ids(state, insurgent_id)
        if not hand:
            ir["burned_out"] = True
            break
        victim = state.objects.get(random.choice(hand))
        if victim:
            events.extend(_relocate(game, victim, ZoneType.GRAVEYARD))
    events.extend(_emit(game, EventType.SCP_DAMAGE, controller=insurgent_id,
                        player=insurgent_id, amount=n))
    return events


def _resolve_subroutine(game, insurgent_id: str, layer: GameObject, run: dict) -> list[Event]:
    """Fire an unbroken layer's subroutine. Returns events; sets run['ended'] for end_run."""
    state = game.state
    ir = ensure_scp_state(state, insurgent_id)
    sub = getattr(layer.card_def, "scp_sub", None) or _DEFAULT_SUB.get(
        getattr(layer.card_def, "scp_ltype", ""), "expose")
    events: list[Event] = []
    if sub == "end_run":
        run["ended"] = True
    elif sub == "neutralize":
        # trash one rig operative; if none, 1 damage
        operatives = [oid for oid in ir["rig"]
                      if getattr(state.objects.get(oid), "state", None)
                      and getattr(state.objects[oid].state, "scp_role", None) == "operative"]
        if operatives:
            victim = state.objects[operatives[0]]
            ir["rig"].remove(victim.id)
            events.extend(_relocate(game, victim, ZoneType.GRAVEYARD))
        else:
            events.extend(deal_damage(game, insurgent_id, 1))
    elif sub == "damage2":
        events.extend(deal_damage(game, insurgent_id, 2))
    elif sub == "expose":
        ir["exposed"] = int(ir.get("exposed", 0)) + 1
        events.extend(_emit(game, EventType.SCP_EXPOSE, controller=insurgent_id, player=insurgent_id))
    elif sub == "discard":
        hand = hand_ids(state, insurgent_id)
        if hand:
            victim = state.objects.get(random.choice(hand))
            if victim:
                events.extend(_relocate(game, victim, ZoneType.GRAVEYARD))
    return events


def infiltrate(game, insurgent_id: str, target: tuple, *,
               rez_policy: Optional[Callable] = None,
               break_policy: Optional[Callable] = None) -> tuple[bool, str, list[Event]]:
    """Insurgency run. ``target`` = ("cell", cell_id) or ("central", name).

    rez_policy(foundation_rec, layer) -> bool : Foundation's reactive rez choice (default:
        greedy — rez any affordable, not-yet-rezzed layer).
    break_policy(insurgent_rec, layer, can_break, cost) -> bool : Insurgency's break choice
        (default: break whenever able).
    """
    state = game.state
    ir = ensure_scp_state(state, insurgent_id)
    fid = foundation_id(state)
    if fid is None:
        return False, "No Foundation", []
    fr = ensure_scp_state(state, fid)
    if target[0] not in ("cell", "central"):
        return False, "Bad target", []
    if ir["ap"] < 1:
        return False, "No actions left", []
    ir["ap"] -= 1

    rezzer = rez_policy or (lambda frec, layer: frec["credits"] >= int(getattr(layer.card_def, "scp_rez", 0) or 0))
    breaker = break_policy or (lambda irec, layer, can, cost: can)

    events = _emit(game, EventType.SCP_INFILTRATE, controller=insurgent_id,
                   player=insurgent_id, target=list(target))
    run = {"ended": False}

    for layer_id in list(_layer_stack(state, fid, target)):
        if run["ended"]:
            break
        layer = state.objects.get(layer_id)
        if not layer:
            continue
        rezzed = bool(getattr(layer.state, "scp_rezzed", False))
        if not rezzed and rezzer(fr, layer):
            rez_cost = int(getattr(layer.card_def, "scp_rez", 0) or 0)
            if fr["credits"] >= rez_cost:
                fr["credits"] -= rez_cost
                layer.state.scp_rezzed = True
                layer.state.scp_facedown = False
                rezzed = True
        broken = False
        if rezzed:
            can, cost = _can_break(state, insurgent_id, layer)
            if can and breaker(ir, layer, can, cost):
                ir["credits"] -= cost
                broken = True
            else:
                events.extend(_resolve_subroutine(game, insurgent_id, layer, run))
        events.extend(_emit(game, EventType.SCP_LAYER_ENCOUNTER, controller=insurgent_id,
                            player=insurgent_id, layer_id=layer_id, rezzed=rezzed, broken=broken))

    if not run["ended"]:
        events.extend(_access(game, insurgent_id, target))
    events.extend(check_scp_win(game))
    return True, "", events


def _access(game, insurgent_id: str, target: tuple) -> list[Event]:
    state = game.state
    fid = foundation_id(state)
    events = _emit(game, EventType.SCP_ACCESS, controller=insurgent_id,
                   player=insurgent_id, target=list(target))
    if target[0] == "central":
        return events + _access_central(game, insurgent_id, target[1])
    fr = ensure_scp_state(state, fid)
    cell = _find_cell(fr, target[1])
    if not cell or not cell.get("anomaly"):
        return events  # empty cell — nothing to free
    anomaly = state.objects.get(cell["anomaly"])
    if not anomaly:
        return events
    cd = anomaly.card_def
    if bool(getattr(cd, "scp_trap", False)):
        events.extend(_spring_trap(game, insurgent_id, anomaly))
        cell["anomaly"] = None
        events.extend(_relocate(game, anomaly, ZoneType.GRAVEYARD))
        return events
    events.extend(_free_anomaly(game, insurgent_id, anomaly, cell))
    return events


def _access_central(game, insurgent_id: str, name: str) -> list[Event]:
    """Espionage/sabotage on a central — the Insurgency's disruption surface when no cell is
    worth cracking. Centrals never grant Liberation (no anomaly); their payoff is tempo so the
    run still does *something* when the cells are walled. Deliberately no breach here (that would
    over-feed the breach-rush axis):

      HQ       → trash 1 random card from the Foundation's hand (espionage / hand attrition).
      Research → trash the top 2 of the Foundation's deck (sabotage / mill).
      Archives → the Insurgency draws 1 (intel pulled from the archived files).
    """
    state = game.state
    fid = foundation_id(state)
    events: list[Event] = []
    effect = "none"
    if name == "hq" and fid is not None:
        hand = hand_ids(state, fid)
        if hand:
            victim = state.objects.get(random.choice(hand))
            if victim:
                events.extend(_relocate(game, victim, ZoneType.GRAVEYARD))
                effect = "hand_trash"
    elif name == "research" and fid is not None:
        events.extend(mill(game, fid, 2))
        effect = "mill"
    elif name == "archives":
        events.extend(draw_cards(game, insurgent_id, 1))
        effect = "draw"
    events.extend(_emit(game, EventType.SCP_SABOTAGE, controller=insurgent_id,
                        player=insurgent_id, central=name, effect=effect))
    return events


def _spring_trap(game, insurgent_id: str, anomaly: GameObject) -> list[Event]:
    on_access = getattr(anomaly.card_def, "scp_on_access", None)
    if callable(on_access):
        return on_access(game, insurgent_id, anomaly) or []
    return deal_damage(game, insurgent_id, 2)  # default trap bite


def _free_anomaly(game, insurgent_id: str, anomaly: GameObject, cell: dict) -> list[Event]:
    state = game.state
    fid = foundation_id(state)
    ir = ensure_scp_state(state, insurgent_id)
    fr = ensure_scp_state(state, fid)
    cd = anomaly.card_def
    value = int(getattr(cd, "scp_value", 0) or 0)
    # A steal-engine identity (e.g. Black Queen Cell) banks bonus Liberation per free.
    ir["liberation_points"] += value + int(ir.get("free_bonus_lib", 0))
    breach = getattr(cd, "scp_breach_on_free", None)
    breach = value if breach is None else int(breach)
    breach = int(round(breach * BREACH_FREE_MULTIPLIER))
    fr["total_breach"] += breach
    cell["anomaly"] = None
    events = _emit(game, EventType.SCP_FREE, controller=insurgent_id,
                   player=insurgent_id, object_id=anomaly.id, value=value,
                   liberation_points=ir["liberation_points"])
    events.extend(_emit(game, EventType.SCP_BREACH, controller=insurgent_id,
                        amount=breach, total_breach=fr["total_breach"]))
    on_free = getattr(cd, "scp_on_free", None)
    if callable(on_free):
        events.extend(on_free(game, insurgent_id, anomaly) or [])
    events.extend(_relocate(game, anomaly, ZoneType.GRAVEYARD))
    return events


# ---------------------------------------------------------------------------
# Win check (the single arbiter; run as a state-based action)
# ---------------------------------------------------------------------------
def _declare_win(game, winner: str, loser: str, reason: str) -> list[Event]:
    state = game.state
    if state.players[loser].has_lost:
        return []
    state.players[loser].has_lost = True
    return game.emit(Event(
        type=EventType.SCP_WIN,
        payload={"winner": winner, "loser": loser, "reason": reason},
        source="SCP_SYSTEM", controller=winner,
    )) + game.emit(Event(
        type=EventType.PLAYER_LOSES,
        payload={"player": loser, "reason": reason, "winner": winner},
        source="SCP_SYSTEM", controller=winner,
    ))


def _foundation_reachable_containment(state: GameState, fid: str) -> int:
    """The most Containment the Foundation could still reach: current points plus the Value of every
    anomaly it can still contain — uncontained-and-unfreed, in its library, hand, or installed on a
    cell. Traps (Value 0) add nothing. When this falls below CONTAINMENT_TARGET the Foundation's
    primary win is mathematically dead — the Insurgency has loosed too many anomalies for it to ever
    reach the target."""
    f = ensure_scp_state(state, fid)
    total = f["containment_points"]
    for oid in hand_ids(state, fid) + deck_ids(state, fid):
        obj = state.objects.get(oid)
        if obj is not None and getattr(obj.card_def, "scp_kind", None) == CardType.SCP_ANOMALY:
            total += int(getattr(obj.card_def, "scp_value", 0) or 0)
    for cell in f["cells"]:
        anomaly = state.objects.get(cell.get("anomaly")) if cell.get("anomaly") else None
        if anomaly is not None and getattr(anomaly.state, "scp_status", None) != "contained":
            total += int(getattr(anomaly.card_def, "scp_value", 0) or 0)
    return total


def check_scp_win(game) -> list[Event]:
    state = game.state
    fid = foundation_id(state)
    iid = insurgency_id(state)
    if fid is None or iid is None:
        return []
    if state.players[fid].has_lost or state.players[iid].has_lost:
        return []
    f = ensure_scp_state(state, fid)
    i = ensure_scp_state(state, iid)
    if f["containment_points"] >= CONTAINMENT_TARGET:
        return _declare_win(game, fid, iid, "containment")
    if i.get("burned_out"):
        return _declare_win(game, fid, iid, "burnout")
    if i["liberation_points"] >= LIBERATION_TARGET:
        return _declare_win(game, iid, fid, "liberation")
    if f["total_breach"] >= BREACH_CATASTROPHE:
        return _declare_win(game, iid, fid, "total_breach")
    # Foundation collapse — the decisive resolution of mutual exhaustion (the game has no draw).
    # The Foundation's mandate is Containment; once it can no longer reach the target — its remaining
    # anomaly Value spent by the Insurgency's frees (see _foundation_reachable_containment) — it has
    # failed to contain, and the Insurgency wins by default. This converts the old ~0.4% "ran to the
    # turn cap" stall (a board where neither side can progress — the Foundation out of anomalies, the
    # Insurgency out of targets) into a clean Insurgency win, and fixes the matching human-play hang.
    # Guard: the soft-kill (burnout) needs an *empty* Insurgency hand, so while the Insurgency still
    # holds cards (>=2) the Foundation cannot flatline it this turn and collapse is the true outcome;
    # if the hand is nearly empty we defer, leaving a genuine burnout window to resolve on its own.
    if (_foundation_reachable_containment(state, fid) < CONTAINMENT_TARGET
            and len(hand_ids(state, iid)) >= 2):
        return _declare_win(game, iid, fid, "foundation_collapse")
    return []


# ---------------------------------------------------------------------------
# Fog of war: redaction logic (wired into the per-viewer serializer in Phase 5)
# ---------------------------------------------------------------------------
def card_hidden_from(state: GameState, obj: GameObject, viewer_id: Optional[str]) -> bool:
    """True if ``obj``'s identity must be hidden from ``viewer_id`` (face-down and not theirs).
    The advancement token COUNT stays public even when the identity is hidden."""
    if viewer_id is not None and obj.owner == viewer_id:
        return False
    return bool(getattr(obj.state, "scp_facedown", False))


def public_board(state: GameState, viewer_id: Optional[str]) -> dict:
    """A viewer-specific board snapshot with face-down identities redacted. Used by the
    frontend serializer (Phase 5); kept here so the redaction rule lives with the engine
    and can be unit-tested in Phase 1."""
    out: dict[str, Any] = {"players": {}}
    for pid in state.players:
        r = ensure_scp_state(state, pid)
        rec_out: dict[str, Any] = {
            "faction": r["faction"],
            "credits": r["credits"],
            "ap": r["ap"],
            "containment_points": r["containment_points"],
            "liberation_points": r["liberation_points"],
            "total_breach": r["total_breach"],
            "exposed": r["exposed"],
        }
        cells_out = []
        for cell in r["cells"]:
            anomaly = state.objects.get(cell["anomaly"]) if cell.get("anomaly") else None
            anomaly_view = None
            if anomaly is not None:
                hidden = card_hidden_from(state, anomaly, viewer_id)
                anomaly_view = {
                    "id": anomaly.id,  # opaque object id (not a fog leak — needed to advance/contain)
                    "advancement": int(getattr(anomaly.state, "scp_advancement", 0)),  # public
                    "name": ("[FACE-DOWN]" if hidden else anomaly.name),
                    "hidden": hidden,
                }
            layers_out = []
            for lid in cell["layers"]:
                layer = state.objects.get(lid)
                if not layer:
                    continue
                hidden = card_hidden_from(state, layer, viewer_id)
                layers_out.append({
                    "id": layer.id,
                    "name": ("[FACE-DOWN]" if hidden else layer.name),
                    "rezzed": bool(getattr(layer.state, "scp_rezzed", False)),
                    "hidden": hidden,
                })
            cells_out.append({"id": cell["id"], "anomaly": anomaly_view, "layers": layers_out})
        rec_out["cells"] = cells_out
        # Central-access layer stacks (HQ / Research / Archives) — a defensible board
        # region the Insurgency runs into via the central-infiltrate path. Face-down
        # identities redacted to the non-owner exactly like cell layers.
        centrals_out: dict[str, Any] = {}
        for cname in CENTRALS:
            stack = []
            for lid in r["centrals"].get(cname, []):
                layer = state.objects.get(lid)
                if not layer:
                    continue
                hidden = card_hidden_from(state, layer, viewer_id)
                stack.append({
                    "id": layer.id,
                    "name": ("[FACE-DOWN]" if hidden else layer.name),
                    "rezzed": bool(getattr(layer.state, "scp_rezzed", False)),
                    "hidden": hidden,
                })
            centrals_out[cname] = stack
        rec_out["centrals"] = centrals_out
        out["players"][pid] = rec_out
    return out


# ---------------------------------------------------------------------------
# Turn-manager support + game setup
# ---------------------------------------------------------------------------
def fire_turn_start_assets(game, player_id: str) -> list[Event]:
    """Run start-of-turn hooks on the active player's installed assets."""
    state = game.state
    r = ensure_scp_state(state, player_id)
    events: list[Event] = []
    for oid in list(r["assets"]):
        obj = state.objects.get(oid)
        if not obj:
            continue
        hook = getattr(obj.card_def, "scp_on_turn_start", None)
        if callable(hook):
            events.extend(hook(game, player_id, obj) or [])
    return events


def discard_to_max(game, player_id: str) -> list[Event]:
    """End-of-turn cleanup: discard at random down to MAX_HAND. (AI/human pick which card
    in practice; the engine enforces only the cap.)"""
    state = game.state
    events: list[Event] = []
    limit = int(ensure_scp_state(state, player_id).get("max_hand") or MAX_HAND)
    while len(hand_ids(state, player_id)) > limit:
        victim = state.objects.get(random.choice(hand_ids(state, player_id)))
        if not victim:
            break
        events.extend(_relocate(game, victim, ZoneType.GRAVEYARD))
    return events


def setup_scp_game(game, foundation_player: Player, insurgency_player: Player, *,
                    foundation_deck: list[CardDefinition], insurgency_deck: list[CardDefinition],
                    foundation_identity: Optional[CardDefinition] = None,
                    insurgency_identity: Optional[CardDefinition] = None,
                    shuffle: bool = True, rng: Optional[random.Random] = None,
                    opening_hand: int = 5) -> None:
    """Wire up a full scp game: factions, libraries, identities, opening hands, turn order
    (Foundation first). Decks are lists of CardDefinition (templates)."""
    rng = rng or random
    setup_scp_player(game, foundation_player, FOUNDATION)
    setup_scp_player(game, insurgency_player, INSURGENCY)

    for player, deck, identity in (
        (foundation_player, foundation_deck, foundation_identity),
        (insurgency_player, insurgency_deck, insurgency_identity),
    ):
        cards = list(deck)
        if shuffle:
            rng.shuffle(cards)
        for cd in cards:
            game.create_object(name=cd.name, owner_id=player.id, zone=ZoneType.LIBRARY,
                               characteristics=cd.characteristics, card_def=cd)
        if identity is not None:
            ident = game.create_object(name=identity.name, owner_id=player.id,
                                       zone=ZoneType.BATTLEFIELD,
                                       characteristics=identity.characteristics, card_def=identity)
            ident.state.scp_role = "identity"
            ensure_scp_state(game.state, player.id)["identity"] = ident.id
            # Apply the identity's passive once, at install. It mutates the player record
            # (e.g. starting credits, max_hand) — the engine reads those flags thereafter.
            passive = getattr(identity, "scp_passive", None)
            if callable(passive):
                passive(game, player.id, ident)
        draw_cards(game, player.id, opening_hand)

    tm = game.turn_manager
    if hasattr(tm, "set_turn_order"):
        tm.set_turn_order([foundation_player.id, insurgency_player.id])
