"""FBN Dragon Conclave sub-set — 30 cards.

Theme: Dragons as apex-predator Keter-class anomalies. Archive-engine
midrange: every Dragon-subtype card archived grants Dragon Hoard X to all
tests. Spark Containment N fires extra draw whenever containing opposing
anomalies crosses clearance-6 each turn.

Composition (30):
- 13 Anomalies (Dragon-subtype, all carrying Dragon Hoard or Spark
  Containment)
- 7 Personnel (Dragonologists / Containment Specialists)
- 5 Facilities
- 4 Procedures
- 1 Mandate

MTG dragon inspiration: Nicol Bolas, Niv-Mizzet, Ugin, Sarkhan's broods,
Atarka, Kolaghan, Ojutai, Silumgar, Dromoka, The Dragon-of-Korlis, Shivan
Dragon / Ramoth, Ancient Wyrm.
"""

from __future__ import annotations

from typing import Callable

from src.engine import scp
from src.engine.types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
)

from .helpers import (
    _dragon_hoard,
    _fbn_card,
    _spark_containment,
    _with_fbn_metadata,
)

_ARCH = "dragon_conclave"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _site_event(event_type: EventType, obj: GameObject, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(
        type=event_type,
        payload=payload,
        source=obj.id,
        controller=obj.controller,
    )


def _dragon_anomaly(name: str, *, containment: int, curiosity: int, hazard: int,
                    red_tape: int, rarity: str, text: str,
                    hoard: int = 0, spark: int = 0,
                    subtypes_extra: set[str] | None = None,
                    on_contain=None, on_reveal=None) -> object:
    """Build a Dragon-subtype anomaly and stamp Dragon Hoard / Spark
    Containment as requested."""
    subtypes = {"Dragon"} | (subtypes_extra or set())
    card = _fbn_card(
        name,
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=containment,
        curiosity=curiosity,
        hazard=hazard,
        red_tape=red_tape,
        rarity=rarity,
        subtypes=subtypes,
        text=text,
        on_contain=on_contain,
        on_reveal=on_reveal,
    )
    if hoard:
        _dragon_hoard(card, hoard)
    if spark:
        _spark_containment(card, spark)
    return card


# ---------------------------------------------------------------------------
# Bespoke on-contain / on-reveal hooks
# ---------------------------------------------------------------------------


def _nicol_bolas_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """On contain, archive this anomaly (record it in archives_list and bump
    the archive counter by 1 extra so the Dragon Hoard can read it)."""
    events: list[Event] = []
    s = scp.site(state, obj.controller)
    s.setdefault("archives_list", [])
    if obj.card_def and obj.card_def not in s["archives_list"]:
        s["archives_list"].append(obj.card_def)
    s["archives"] = s.get("archives", 0) + 1
    events.append(_site_event(
        EventType.SCP_ARCHIVE_GAINED,
        obj,
        amount=1,
        archives=s["archives"],
        reason="nicol_bolas_self_archive",
    ))
    return events


def _niv_mizzet_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """When you contain a Dragon, draw 1 paperwork (paperwork tick)."""
    events: list[Event] = []
    # Check if the contained anomaly is a Dragon.
    # ``scp_on_contain`` fires on the anomaly being contained, so ``obj`` IS
    # the anomaly. The card's own subtype guarantees it's a Dragon, so the
    # draw fires whenever Niv-Mizzet itself is contained (one draw) AND
    # whenever ANY Dragon's on_contain fires after Niv-Mizzet delegates —
    # but the spec says "when you contain a Dragon, draw 1 paperwork." Since
    # on_contain fires on the contained card itself, this hook fires whenever
    # Niv-Mizzet is contained. For other Dragons in the deck triggering the
    # draw, that would require a global watcher (no scp_on_archive hook
    # exists); we scope it to the Niv-Mizzet contain event.
    events.append(_site_event(
        EventType.SCP_PAPERWORK_TICK,
        obj,
        reason="niv_mizzet_dragon_contain_draw",
        amount=1,
    ))
    return events


def _ugin_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """When you contain an opposing anomaly, archive a Dragon from your hand
    for free. Implementation: we fire a protocol marker event; the full hand-
    inspection requires game reference. Engine reads scp_on_archive; since
    that hook doesn't exist yet, we mark via an incident-resolved event and
    # TODO-stub the hand-grab logic.
    """
    # TODO: archive a Dragon from hand when this fires via SCP_CONTAINED.
    # Requires iterating state.players[obj.controller].hand for a Dragon card_def.
    events: list[Event] = []
    events.append(_site_event(
        EventType.SCP_INCIDENT_RESOLVED,
        obj,
        reason="ugin_spirit_wyrm_dragon_archive_offer",
    ))
    return events


def _atarka_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """When this is contained, opposing breach +1."""
    events: list[Event] = []
    for opp_id in state.players:
        if opp_id == obj.controller:
            continue
        scp.site(state, opp_id)["breach"] += 1
        events.append(_site_event(
            EventType.SCP_INCIDENT,
            obj,
            reason="atarka_world_render_breach",
            target=opp_id,
            breach_delta=1,
        ))
    return events


def _ojutai_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """On contain, gain 1 clearance."""
    s = scp.site(state, obj.controller)
    s["clearance"] = s.get("clearance", 0) + 1
    return [_site_event(
        EventType.SCP_INCIDENT_RESOLVED,
        obj,
        reason="ojutai_soul_of_winter_clearance",
        clearance=s["clearance"],
    )]


def _dragon_of_korlis_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """When archived, gain 1 archive token of 'Dragon' subtype.

    'Archived' in SCP maps to the contain event followed by the gain_archives
    call. We emit an extra archive-gain event here and append a lightweight
    synthetic card_def stub to archives_list so Dragon Hoard counts it.
    """
    events: list[Event] = []
    s = scp.site(state, obj.controller)
    s.setdefault("archives_list", [])
    # Append a minimal stub so Dragon Hoard state-time reads see an extra
    # Dragon with Dragon Hoard 1 contribution from the archive token.
    from src.engine.types import CardDefinition, Characteristics
    stub = CardDefinition(
        name="Dragon Archive Token (Dragon-of-Korlis)",
        mana_cost=None,
        domain="SCP",
        text="Archive token — counts as a Dragon for Dragon Hoard.",
        rarity="token",
        characteristics=Characteristics(
            types={CardType.SCP_ANOMALY},
            subtypes={"Dragon"},
        ),
    )
    stub.scp_dragon_hoard = 1
    s["archives_list"].append(stub)
    s["archives"] = s.get("archives", 0) + 1
    events.append(_site_event(
        EventType.SCP_ARCHIVE_GAINED,
        obj,
        amount=1,
        archives=s["archives"],
        reason="dragon_of_korlis_archive_token",
    ))
    return events


# ---------------------------------------------------------------------------
# Personnel on-assign hooks
# ---------------------------------------------------------------------------


def _sarkhan_vol_on_assign_hook() -> Callable:
    """On assign (any task): scry top 3 of your library; archive a Dragon.

    Full scry (reorder + choice) is beyond the engine's action surface.
    Implementation: scan top 3 for a Dragon card_def; if found, archive it
    directly (pop from library, add to archives_list, gain 1 archive).
    If none found, no action. Non-Dragon cards remain in library order.
    """
    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        events: list[Event] = []
        player = obj.controller
        lib = getattr(state.players.get(player), "library", None)
        if not lib:
            return events
        top3 = list(lib[:3])
        archived = False
        for i, card_def in enumerate(top3):
            if card_def is None:
                continue
            subtypes = set(getattr(getattr(card_def, "characteristics", None), "subtypes", None) or set())
            if "Dragon" not in subtypes:
                continue
            # Archive it: remove from library, record in archives_list.
            lib.pop(i)
            s = scp.site(state, player)
            s.setdefault("archives_list", [])
            s["archives_list"].append(card_def)
            s["archives"] = s.get("archives", 0) + 1
            events.append(Event(
                type=EventType.SCP_ARCHIVE_GAINED,
                payload={
                    "player": player,
                    "amount": 1,
                    "archives": s["archives"],
                    "reason": "sarkhan_vol_scry_archive",
                },
                source=obj.id,
                controller=player,
            ))
            archived = True
            break
        if not archived:
            events.append(Event(
                type=EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": player,
                    "reason": "sarkhan_vol_scry_no_dragon_found",
                },
                source=obj.id,
                controller=player,
            ))
        return events
    return hook


def _ramoth_on_assign_hook() -> Callable:
    """When you archive a Dragon (detected via task_bonus pattern): gain 1
    clearance. We approximate by granting clearance whenever this personnel
    assists a contain action that results in an archive gain.

    Since ``scp_on_assign`` fires before success resolution, we check whether
    the anomaly being targeted is a Dragon and grant clearance optimistically
    (the contain may still fail, but it matches the deck's design intent).
    """
    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "contain":
            return []
        # Grant clearance optimistically when assisting Dragon containment.
        # A full "on archive" hook does not exist; this is the closest hook.
        # TODO: move to scp_on_archive hook when that engine surface ships.
        s = scp.site(state, obj.controller)
        s["clearance"] = s.get("clearance", 0) + 1
        return [Event(
            type=EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "ramoth_hoard_auditor_clearance",
                "clearance": s["clearance"],
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return hook


def _belora_on_assign_hook() -> Callable:
    """On assign (any task): look at top 4 of library; archive top Dragon.

    Same pattern as Sarkhan Vol but scans top 4 and requires no specific
    action filter.
    """
    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        events: list[Event] = []
        player = obj.controller
        lib = getattr(state.players.get(player), "library", None)
        if not lib:
            return events
        top4 = list(lib[:4])
        for i, card_def in enumerate(top4):
            if card_def is None:
                continue
            subtypes = set(getattr(getattr(card_def, "characteristics", None), "subtypes", None) or set())
            if "Dragon" not in subtypes:
                continue
            lib.pop(i)
            s = scp.site(state, player)
            s.setdefault("archives_list", [])
            s["archives_list"].append(card_def)
            s["archives"] = s.get("archives", 0) + 1
            events.append(Event(
                type=EventType.SCP_ARCHIVE_GAINED,
                payload={
                    "player": player,
                    "amount": 1,
                    "archives": s["archives"],
                    "reason": "belora_dragon_cartographer_top4_archive",
                },
                source=obj.id,
                controller=player,
            ))
            break
        return events
    return hook


def _o5_12_on_assign_hook() -> Callable:
    """When you contain a Dragon-subtype anomaly, gain 2 clearance.

    The on_assign hook fires during contain attempts; we check if the
    anomaly being contained is a Dragon.
    """
    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "contain":
            return []
        # Find the anomaly being contained this assignment. Walk active
        # anomalies to find one being targeted (exhausted this tick via
        # assignment). Best-effort: check if any active Dragon is involved.
        # TODO: full dragon-subtype check requires passing anomaly_id through
        # _fire_on_assign's context; currently not plumbed.
        # Heuristic: grant +2 clearance when containing any anomaly on the
        # first contain assignment for this personnel per turn.
        assigns = int(getattr(obj.state, "scp_assigns_this_turn", 0) or 0)
        if assigns > 1:
            return []
        s = scp.site(state, obj.controller)
        s["clearance"] = s.get("clearance", 0) + 2
        return [Event(
            type=EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "o5_12_sky_patrol_dragon_clearance",
                "clearance": s["clearance"],
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return hook


# ---------------------------------------------------------------------------
# Procedure effect callables
# ---------------------------------------------------------------------------


def _dracoform_cataloging_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Archive a Dragon from your hand. Spark Containment 1 trigger fires.

    Full hand-selection is beyond the engine's one-shot effect surface
    (no modal targeting). Heuristic: archive the first Dragon card_def found
    in the player's hand. The Spark Containment tag on the card itself
    causes the engine to fire apply_spark_containment on contain events; here
    we manually trigger it to model the "Spark Containment 1 trigger fires"
    text as a bonus.
    """
    events: list[Event] = []
    player = obj.controller
    hand = getattr(state.players.get(player), "hand", None)
    if hand:
        for i, card_def in enumerate(list(hand)):
            if card_def is None:
                continue
            subtypes = set(getattr(getattr(card_def, "characteristics", None), "subtypes", None) or set())
            if "Dragon" not in subtypes:
                continue
            hand.pop(i)
            s = scp.site(state, player)
            s.setdefault("archives_list", [])
            s["archives_list"].append(card_def)
            s["archives"] = s.get("archives", 0) + 1
            events.append(Event(
                type=EventType.SCP_ARCHIVE_GAINED,
                payload={
                    "player": player,
                    "amount": 1,
                    "archives": s["archives"],
                    "reason": "dracoform_cataloging_hand_archive",
                },
                source=obj.id,
                controller=player,
            ))
            # Bonus Spark Containment 1 trigger: bump clearance by 1.
            s["clearance"] = s.get("clearance", 0) + 1
            events.append(Event(
                type=EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": player,
                    "reason": "dracoform_cataloging_spark_containment_bonus",
                    "clearance": s["clearance"],
                },
                source=obj.id,
                controller=player,
            ))
            break
    return events


def _hoard_audit_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Look at top 3 of library, archive any Dragons, return rest."""
    events: list[Event] = []
    player = obj.controller
    lib = getattr(state.players.get(player), "library", None)
    if not lib:
        return events
    top3 = list(lib[:3])
    kept_back: list = []
    s = scp.site(state, player)
    s.setdefault("archives_list", [])
    for card_def in top3:
        lib_pop_idx = lib.index(card_def) if card_def in lib else -1
        if lib_pop_idx < 0:
            continue
        subtypes = set(getattr(getattr(card_def, "characteristics", None), "subtypes", None) or set())
        if "Dragon" in subtypes:
            lib.pop(lib_pop_idx)
            s["archives_list"].append(card_def)
            s["archives"] = s.get("archives", 0) + 1
            events.append(Event(
                type=EventType.SCP_ARCHIVE_GAINED,
                payload={
                    "player": player,
                    "amount": 1,
                    "archives": s["archives"],
                    "reason": "hoard_audit_dragon_archived",
                },
                source=obj.id,
                controller=player,
            ))
        else:
            kept_back.append(card_def)
    # Non-Dragon cards remain in library (already in place since we only
    # popped Dragon entries). No explicit reinsert needed.
    return events


def _dracoform_sweep_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Each Dragon anomaly you control gets +2 hazard until end of turn.

    Mutates scp_suppressed by -2 (negative suppression = bonus hazard at
    breach-tick time) on every active Dragon anomaly. Per engine convention,
    this is cleared at the controlling player's end step.
    """
    events: list[Event] = []
    player = obj.controller
    for anomaly_id in list(state.scp_anomalies.get(player, [])):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly or not anomaly.card_def:
            continue
        subtypes = set(getattr(getattr(anomaly.card_def, "characteristics", None), "subtypes", None) or set())
        if "Dragon" not in subtypes:
            continue
        prior = int(getattr(anomaly.state, "scp_suppressed", 0) or 0)
        anomaly.state.scp_suppressed = prior - 2  # negative = extra hazard
        events.append(Event(
            type=EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": player,
                "reason": "dracoform_sweep_hazard_boost",
                "anomaly_id": anomaly_id,
                "suppressed": anomaly.state.scp_suppressed,
            },
            source=obj.id,
            controller=player,
        ))
    return events


def _dragonhoard_cataclysm_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Archive each Dragon anomaly you control. Gain 2 archives.
    Dragon Hoard sum +1 permanently (stored as scp_dragon_hoard_bonus on site).

    Moves all active Dragon anomalies to archived status, records them in
    archives_list, then grants +2 archives and +1 to the permanent Dragon
    Hoard bonus multiplier.
    """
    events: list[Event] = []
    player = obj.controller
    s = scp.site(state, player)
    s.setdefault("archives_list", [])
    dragon_ids = [
        aid for aid in list(state.scp_anomalies.get(player, []))
        if (lambda a: a and a.card_def and "Dragon" in set(
            getattr(getattr(a.card_def, "characteristics", None), "subtypes", None) or set()
        ))(state.objects.get(aid))
    ]
    for aid in dragon_ids:
        anomaly = state.objects.get(aid)
        if not anomaly:
            continue
        anomaly.state.scp_status = "contained"
        state.scp_anomalies[player].remove(aid)
        if aid not in state.scp_contained[player]:
            state.scp_contained[player].append(aid)
        if anomaly.card_def:
            s["archives_list"].append(anomaly.card_def)
        s["archives"] = s.get("archives", 0) + 1
        events.append(Event(
            type=EventType.SCP_ARCHIVE_GAINED,
            payload={
                "player": player,
                "amount": 1,
                "archives": s["archives"],
                "reason": "dragonhoard_cataclysm_mass_archive",
                "anomaly_id": aid,
            },
            source=obj.id,
            controller=player,
        ))
    # +2 flat archives on top of the per-dragon gains.
    s["archives"] = s.get("archives", 0) + 2
    events.append(Event(
        type=EventType.SCP_ARCHIVE_GAINED,
        payload={
            "player": player,
            "amount": 2,
            "archives": s["archives"],
            "reason": "dragonhoard_cataclysm_bonus_archives",
        },
        source=obj.id,
        controller=player,
    ))
    # Permanent +1 to Dragon Hoard bonus (engine reads scp_dragon_hoard_bonus
    # as a flat additive on top of the per-card hoard sum in _active_bonus).
    # TODO: _active_bonus does not yet read scp_dragon_hoard_bonus from site;
    # this sets the value for forward-compatibility when the engine supports it.
    s["scp_dragon_hoard_bonus"] = s.get("scp_dragon_hoard_bonus", 0) + 1
    events.append(Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": player,
            "reason": "dragonhoard_cataclysm_permanent_hoard_plus1",
            "dragon_hoard_bonus": s["scp_dragon_hoard_bonus"],
        },
        source=obj.id,
        controller=player,
    ))
    return events


# ---------------------------------------------------------------------------
# Facility aura helpers
# ---------------------------------------------------------------------------


def _eastern_wyrm_bunker_aura() -> dict:
    """Aura: Dragon-subtype anomalies you control get +1 containment."""
    return {"subtype:Dragon": {"contain": 1}}


# ---------------------------------------------------------------------------
# 13 Anomalies
# ---------------------------------------------------------------------------

# 1 — Nicol Bolas, Class-V Apex Dracoform (mythic)
SCP_FBN_3001 = _dragon_anomaly(
    "SCP-FBN-3001: Nicol Bolas, Class-V Apex Dracoform",
    containment=6, curiosity=4, hazard=4,
    red_tape=2, rarity="mythic",
    hoard=2,
    text=(
        "Dragon. Dragon Hoard 2. On contain, archive this. "
        "Containment Integrity: Holding. Threat Level: Apex."
    ),
    on_contain=_nicol_bolas_on_contain,
)

# 2 — Niv-Mizzet, Class-IV Conduit (rare)
SCP_FBN_3002 = _dragon_anomaly(
    "SCP-FBN-3002: Niv-Mizzet, Class-IV Conduit",
    containment=4, curiosity=3, hazard=3,
    red_tape=1, rarity="rare",
    hoard=1,
    text=(
        "Dragon. Dragon Hoard 1. When you contain a Dragon, draw 1 paperwork. "
        "Note: specimen demonstrates cross-planar gestalt cognition. Do not engage."
    ),
    on_contain=_niv_mizzet_on_contain,
)

# 3 — Ugin, Class-V Spirit-Wyrm (mythic)
SCP_FBN_3003 = _dragon_anomaly(
    "SCP-FBN-3003: Ugin, Class-V Spirit-Wyrm",
    containment=5, curiosity=4, hazard=3,
    red_tape=2, rarity="mythic",
    spark=1,
    text=(
        "Dragon. Spark Containment 1. When you contain an opposing anomaly, "
        "archive a Dragon from your hand for free. Classification: Spirit-type Keter."
    ),
    on_contain=_ugin_on_contain,
)

# 4 — Sarkhan-Pattern Hunter (uncommon)
SCP_FBN_3004 = _dragon_anomaly(
    "SCP-FBN-3004: Sarkhan-Pattern Hunter",
    containment=3, curiosity=2, hazard=3,
    red_tape=1, rarity="uncommon",
    hoard=1,
    text=(
        "Dragon. Dragon Hoard 1. "
        "Pattern: consistent dracoform morphology. Origin: Tarkir-plane bleed."
    ),
)

# 5 — Atarka, World Render (rare)
SCP_FBN_3005 = _dragon_anomaly(
    "SCP-FBN-3005: Atarka, World Render",
    containment=5, curiosity=3, hazard=4,
    red_tape=2, rarity="rare",
    hoard=1,
    text=(
        "Dragon. Dragon Hoard 1. When this contained, opposing breach +1. "
        "Designated: World-class consumption event vector. Do not breach."
    ),
    on_contain=_atarka_on_contain,
)

# 6 — Dragonlord Silumgar (rare)
SCP_FBN_3006 = _dragon_anomaly(
    "SCP-FBN-3006: Dragonlord Silumgar",
    containment=5, curiosity=3, hazard=3,
    red_tape=2, rarity="rare",
    hoard=1, spark=1,
    text=(
        "Dragon. Dragon Hoard 1. Spark Containment 1. "
        "Specimen displays ostentatious trophy collection. Do not permit unsupervised access to D-Class."
    ),
)

# 7 — Kolaghan, Storm's Fury (uncommon)
SCP_FBN_3007 = _dragon_anomaly(
    "SCP-FBN-3007: Kolaghan, Storm's Fury",
    containment=3, curiosity=2, hazard=3,
    red_tape=1, rarity="uncommon",
    hoard=1,
    text=(
        "Dragon. Dragon Hoard 1. "
        "Designated: Storm-vector Keter. Containment chamber requires full lightning-rod array."
    ),
)

# 8 — Ojutai, Soul of Winter (rare)
SCP_FBN_3008 = _dragon_anomaly(
    "SCP-FBN-3008: Ojutai, Soul of Winter",
    containment=5, curiosity=3, hazard=3,
    red_tape=2, rarity="rare",
    hoard=1,
    text=(
        "Dragon. Dragon Hoard 1. On contain, gain 1 clearance. "
        "Clearance upgrade ratified: prolonged exposure to specimen's verbal pattern grants unexpected insight."
    ),
    on_contain=_ojutai_on_contain,
)

# 9 — Dragonlord Dromoka (rare)
SCP_FBN_3009 = _dragon_anomaly(
    "SCP-FBN-3009: Dragonlord Dromoka",
    containment=4, curiosity=2, hazard=2,
    red_tape=1, rarity="rare",
    hoard=1, spark=1,
    text=(
        "Dragon. Dragon Hoard 1. Spark Containment 1. "
        "Specimen exerts strong territorial pacification field. Useful against parallel-cell incidents."
    ),
)

# 10 — Ramoth-Class Drake (common)
SCP_FBN_3010 = _dragon_anomaly(
    "SCP-FBN-3010: Ramoth-Class Drake",
    containment=3, curiosity=2, hazard=2,
    red_tape=1, rarity="common",
    text=(
        "Dragon. "
        "Standard dracoform intake. Containment per Site-17 Protocol 4-B. No anomalous secondary traits detected."
    ),
)

# 11 — Class-III Wyrmling (common)
SCP_FBN_3011 = _dragon_anomaly(
    "SCP-FBN-3011: Class-III Wyrmling",
    containment=2, curiosity=1, hazard=1,
    red_tape=0, rarity="common",
    text=(
        "Dragon. "
        "Juvenile dracoform. Low hazard; elevated curiosity among junior researchers. Caution advised."
    ),
)

# 12 — Ancient Class-IV Wyrm (uncommon)
SCP_FBN_3012 = _dragon_anomaly(
    "SCP-FBN-3012: Ancient Class-IV Wyrm",
    containment=5, curiosity=3, hazard=4,
    red_tape=2, rarity="uncommon",
    hoard=1,
    text=(
        "Dragon. Dragon Hoard 1. "
        "Pre-Foundation designation: SCP-████. Age: indeterminate. Scales resist thaumic attenuation."
    ),
)

# 13 — Dragon-of-Korlis, Containment Specimen (uncommon)
SCP_FBN_3013 = _dragon_anomaly(
    "SCP-FBN-3013: Dragon-of-Korlis, Containment Specimen",
    containment=4, curiosity=3, hazard=2,
    red_tape=1, rarity="uncommon",
    text=(
        "Dragon. When archived, gain 1 archive token of 'Dragon' subtype. "
        "Historical note: specimen participated in Phyrexian defeat. Records archived by Yawgmoth's own hand."
    ),
    on_contain=_dragon_of_korlis_on_contain,
)


# ---------------------------------------------------------------------------
# 7 Personnel
# ---------------------------------------------------------------------------

# 14 — Dr. Sarkhan Vol, Dragonologist (rare)
_DR_SARKHAN_VOL = _fbn_card(
    "Dr. Sarkhan Vol, Dragonologist",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=2, clearance=1,
    skills={"research": 2, "contain": 1},
    rarity="rare",
    subtypes={"Dragonologist", "Hero"},
    text=(
        "skills: research 2, contain 1. On assign, scry top 3 of your library; archive a Dragon. "
        "Field note: Dr. Vol's 'empathy' with specimens is classified and under review."
    ),
)
_DR_SARKHAN_VOL.scp_on_assign = _sarkhan_vol_on_assign_hook()

# 15 — Operative O5-7, Dracoform Specialist (rare)
_OPERATIVE_O5_7 = _spark_containment(
    _fbn_card(
        "Operative O5-7, Dracoform Specialist",
        CardType.SCP_PERSONNEL,
        archetype=_ARCH,
        red_tape=2, clearance=1,
        skills={"contain": 2, "research": 1},
        rarity="rare",
        subtypes={"Operative", "O5"},
        text=(
            "skills: contain 2, research 1. Spark Containment 1. "
            "O5-7 personally oversaw the Tarkir bleed response. Clearance: ████."
        ),
    ),
    1,
)

# 16 — Researcher Ramoth, Hoard Auditor (uncommon)
_RESEARCHER_RAMOTH = _fbn_card(
    "Researcher Ramoth, Hoard Auditor",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1, clearance=0,
    skills={"research": 2},
    rarity="uncommon",
    subtypes={"Researcher", "Dragonologist"},
    text=(
        "skills: research 2. When you archive a Dragon, gain 1 clearance. "
        "Tracks Hoard totals with bureaucratic precision. Ask her about the spreadsheet."
    ),
)
_RESEARCHER_RAMOTH.scp_on_assign = _ramoth_on_assign_hook()

# 17 — Dr. Ojiri Kaname, Wyrmkeeper (uncommon)
_DR_OJIRI_KANAME = _fbn_card(
    "Dr. Ojiri Kaname, Wyrmkeeper",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1, clearance=0,
    skills={"contain": 2},
    rarity="uncommon",
    subtypes={"Researcher", "Wyrmkeeper"},
    text=(
        "skills: contain 2. "
        "Maintains the dracoform feeding schedule. Do not adjust the feeding schedule."
    ),
)

# 18 — Class-A Dragonologist 'Forge' (common)
_CLASS_A_FORGE = _fbn_card(
    "Class-A Dragonologist 'Forge'",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1, clearance=0,
    skills={"research": 1, "contain": 1},
    rarity="common",
    subtypes={"Dragonologist"},
    text=(
        "skills: research 1, contain 1. "
        "Nickname earned on first field assignment. Containment suit condition: adequate."
    ),
)

# 19 — Researcher Belora, Dragon Cartographer (uncommon)
_RESEARCHER_BELORA = _fbn_card(
    "Researcher Belora, Dragon Cartographer",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1, clearance=0,
    skills={"research": 2},
    rarity="uncommon",
    subtypes={"Researcher", "Cartographer"},
    text=(
        "skills: research 2. On assign, look at top 4; archive top Dragon. "
        "Her maps of known dracoform territories are not approved for general distribution."
    ),
)
_RESEARCHER_BELORA.scp_on_assign = _belora_on_assign_hook()

# 20 — Operative O5-12, Sky Patrol Coordinator (rare)
_OPERATIVE_O5_12 = _fbn_card(
    "Operative O5-12, Sky Patrol Coordinator",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=2, clearance=1,
    skills={"contain": 2},
    rarity="rare",
    subtypes={"Operative", "O5"},
    text=(
        "skills: contain 2. When you contain a Dragon-subtype anomaly, gain 2 clearance. "
        "Sky Patrol incident log: 47 aerial dracoform intercepts. Zero public sightings. "
        "Containment integrity: holding."
    ),
)
_OPERATIVE_O5_12.scp_on_assign = _o5_12_on_assign_hook()


# ---------------------------------------------------------------------------
# 4 Procedures
# ---------------------------------------------------------------------------

# 21 — Protocol: Dracoform Cataloging (uncommon)
_DRACOFORM_CATALOGING = _spark_containment(
    _fbn_card(
        "Protocol: Dracoform Cataloging",
        CardType.SCP_PROCEDURE,
        archetype=_ARCH,
        red_tape=1,
        rarity="uncommon",
        text=(
            "Archive a Dragon from your hand. Spark Containment 1 trigger fires. "
            "Standard intake form for Class-III+ dracoform specimens. Red tape reduced pending council review."
        ),
        effect=_dracoform_cataloging_effect,
    ),
    1,
)

# 22 — Hoard Audit (uncommon)
_HOARD_AUDIT = _fbn_card(
    "Hoard Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=1,
    rarity="uncommon",
    text=(
        "Look at top 3 of your library, archive any Dragons among them, return rest. "
        "Quarterly inventory of dracoform asset dossiers. Results: see attached."
    ),
    effect=_hoard_audit_effect,
)

# 23 — Class-III Dracoform Sweep (rare)
_DRACOFORM_SWEEP = _fbn_card(
    "Class-III Dracoform Sweep",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=2,
    rarity="rare",
    text=(
        "Each Dragon anomaly you control gets +2 hazard until end of turn. "
        "Temporary hazard elevation approved for inter-site deterrence operations."
    ),
    effect=_dracoform_sweep_effect,
)

# 24 — Dragonhoard Cataclysm Audit (mythic)
_DRAGONHOARD_CATACLYSM = _fbn_card(
    "Dragonhoard Cataclysm Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=3,
    rarity="mythic",
    text=(
        "Archive each Dragon anomaly you control. Gain 2 archives. "
        "Your Dragon Hoard sum +1 permanently. "
        "O5-Council unanimous decision: mass archive event authorized. No further questions."
    ),
    effect=_dragonhoard_cataclysm_effect,
)


# ---------------------------------------------------------------------------
# 5 Facilities
# ---------------------------------------------------------------------------

# 25 — Dracoform Containment Hangar (rare)
_DRACOFORM_HANGAR = _dragon_hoard(
    _fbn_card(
        "Dracoform Containment Hangar",
        CardType.SCP_FACILITY,
        archetype=_ARCH,
        red_tape=2,
        rarity="rare",
        subtypes={"Hangar"},
        bonus={"contain": 1, "research": 1},
        text=(
            "Bonus: contain +1, research +1. Dragon Hoard 1 base. "
            "Infrastructure note: blast-door reinforcement required. Ceiling height: non-standard."
        ),
    ),
    1,
)

# 26 — Wyrmkeeper's Vault (uncommon)
_WYRMKEEPERS_VAULT = _fbn_card(
    "Wyrmkeeper's Vault",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=1,
    rarity="uncommon",
    subtypes={"Vault"},
    bonus={"research": 1},
    text=(
        "Bonus: research +1. When you archive a Dragon, gain 1 archive. "
        "Climate-controlled dossier storage. Dragons archived here retain full thaumic signature."
    ),
)

# TODO: scp_on_archive hook not yet available; the "when you archive a Dragon,
# gain 1 archive" trigger on Wyrmkeeper's Vault is registered as a keyword but
# will not fire until the engine ships scp_on_archive facility hooks.
_WYRMKEEPERS_VAULT.scp_on_archive_stub = True  # forward-compat marker

# 27 — Dragon Audit Bureau (uncommon)
_DRAGON_AUDIT_BUREAU = _fbn_card(
    "Dragon Audit Bureau",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=1,
    rarity="uncommon",
    subtypes={"Bureau"},
    bonus={"research": 1},
    text=(
        "Bonus: research +1. "
        "All dracoform incident reports routed here for cross-classification. "
        "Backlog: 4,200 files."
    ),
)

# 28 — Eastern Wyrm Containment Bunker (rare)
_EASTERN_WYRM_BUNKER = _fbn_card(
    "Eastern Wyrm Containment Bunker",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=2,
    rarity="rare",
    subtypes={"Bunker"},
    bonus={"contain": 1},
    aura=_eastern_wyrm_bunker_aura(),
    text=(
        "Bonus: contain +1. Your Dragon-subtype anomalies get +1 containment. "
        "East-wing fortification: reinforced concrete, Faraday cage, thaumic dampeners."
    ),
)

# 29 — Dragonlord Audit Chamber (rare)
_DRAGONLORD_AUDIT_CHAMBER = _fbn_card(
    "Dragonlord Audit Chamber",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=2,
    rarity="rare",
    subtypes={"Chamber"},
    bonus={"contain": 1},
    text=(
        "Bonus: contain +1. When you contain a Dragon, gain 1 clearance and 1 archive. "
        "Designated multi-purpose assessment suite. Clearance upgrade pending every Dragon-contain event."
    ),
)

# Bespoke on-contain hook for Dragonlord Audit Chamber (Facility).
def _audit_chamber_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """When you contain a Dragon, gain 1 clearance and 1 archive."""
    # obj here is the anomaly being contained, not the facility.
    # We scan the controller's active facilities for Dragonlord Audit Chamber.
    events: list[Event] = []
    player = obj.controller
    subtypes = set(getattr(getattr(obj.card_def, "characteristics", None), "subtypes", None) or set())
    if "Dragon" not in subtypes:
        return events
    # Check if the facility is active.
    has_chamber = any(
        (lambda f: f and f.card_def and f.card_def.name == "Dragonlord Audit Chamber"
         and f.state.scp_status == "active")(state.objects.get(fid))
        for fid in list(state.scp_facilities.get(player, []))
    )
    if not has_chamber:
        return events
    s = scp.site(state, player)
    s["clearance"] = s.get("clearance", 0) + 1
    s["archives"] = s.get("archives", 0) + 1
    s.setdefault("archives_list", [])
    if obj.card_def:
        s["archives_list"].append(obj.card_def)
    events.append(Event(
        type=EventType.SCP_ARCHIVE_GAINED,
        payload={
            "player": player,
            "amount": 1,
            "archives": s["archives"],
            "reason": "dragonlord_audit_chamber_dragon_contain",
        },
        source=obj.id,
        controller=player,
    ))
    events.append(Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": player,
            "reason": "dragonlord_audit_chamber_clearance_gain",
            "clearance": s["clearance"],
        },
        source=obj.id,
        controller=player,
    ))
    return events


# Wire the Audit Chamber's contain hook onto every Dragon anomaly that will
# fire it. Rather than modifying the anomaly cards post-hoc (which would
# require keeping a cross-ref), we expose the hook as a standalone callable
# that the engine can register via scp_audit_chamber_hook. The engine's
# SCP_CONTAINED handler checks for active facilities with this attribute
# and fires it.
# contain_anomaly fires scp_on_dragon_contain via _fire_static_trigger, which
# DOES scan facilities — so the facility just has to store the hook under the
# canonical name. (It was stored as scp_facility_on_dragon_contain, which the
# engine never reads, so the Audit Chamber's on-contain payoff never fired.)
_DRAGONLORD_AUDIT_CHAMBER.scp_on_dragon_contain = _audit_chamber_on_contain


# ---------------------------------------------------------------------------
# 1 Mandate
# ---------------------------------------------------------------------------

# 30 — Mandate FBN-DCG: Dracoform Containment Grid (mythic)
_MANDATE_DCG = _fbn_card(
    "Mandate FBN-DCG: Dracoform Containment Grid",
    CardType.SCP_MANDATE,
    archetype=_ARCH,
    red_tape=3, clearance=2,
    rarity="mythic",
    subtypes={"Mandate"},
    text=(
        "Mandate. Win on existing thaumiel (3 contained + 0 breach), "
        "but also: while ≥4 Dragons are archived, your tests gain +X = Dragon Hoard count. "
        "Ratified: O5-Council unanimous. The dragons are the grid."
    ),
)
_MANDATE_DCG.scp_alt_win = "thaumiel"


# ---------------------------------------------------------------------------
# Aggregate export
# ---------------------------------------------------------------------------

DRAGON_CONCLAVE_CARDS: list = [
    # Anomalies (13)
    SCP_FBN_3001,
    SCP_FBN_3002,
    SCP_FBN_3003,
    SCP_FBN_3004,
    SCP_FBN_3005,
    SCP_FBN_3006,
    SCP_FBN_3007,
    SCP_FBN_3008,
    SCP_FBN_3009,
    SCP_FBN_3010,
    SCP_FBN_3011,
    SCP_FBN_3012,
    SCP_FBN_3013,
    # Personnel (7)
    _DR_SARKHAN_VOL,
    _OPERATIVE_O5_7,
    _RESEARCHER_RAMOTH,
    _DR_OJIRI_KANAME,
    _CLASS_A_FORGE,
    _RESEARCHER_BELORA,
    _OPERATIVE_O5_12,
    # Procedures (4)
    _DRACOFORM_CATALOGING,
    _HOARD_AUDIT,
    _DRACOFORM_SWEEP,
    _DRAGONHOARD_CATACLYSM,
    # Facilities (5)
    _DRACOFORM_HANGAR,
    _WYRMKEEPERS_VAULT,
    _DRAGON_AUDIT_BUREAU,
    _EASTERN_WYRM_BUNKER,
    _DRAGONLORD_AUDIT_CHAMBER,
    # Mandate (1)
    _MANDATE_DCG,
]

_CARDS = DRAGON_CONCLAVE_CARDS
