"""FBN — Lich Phylactery Vaults archetype (30 cards).

Euclid-class undeath recursion. Captured liches store consciousness in
phylacteries that resist memory-holing. Core mechanic: **Phylactery Audit X**
— when a card is memory-holed it returns for X ethics_debt. Mnestic personnel
see past the memory-hole misdirection and protect the recursion engine.

Alt-win route: ``phylactery_chain`` (4 successful Phylactery Audits in a game).
Secondary alt-win bridge: ``mnestic_saturation`` (4 Mnestic personnel on
battlefield + breach = 0) — piggybacked from MNR via the Mandate.

Composition: 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

Lich-flavour naming draws on: Liliana (lich form), Mikaeus the Unhallowed,
Endrek Sahr, Atraxa (planeswalker-lich pattern), Korlash Heir to Blackblade,
Lim-Dûl the Necromancer, Phage the Untouchable, Sedris the Traitor King,
Volrath the Shapestealer, Crovax the Cursed.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import (
    CardDefinition,
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)

from .helpers import (
    _fbn_card,
    _mnestic_personnel,
    _phylactery_audit,
    _with_fbn_metadata,
)


_ARCHETYPE = "lich_phylactery"


# ---------------------------------------------------------------------------
# Shared local helpers
# ---------------------------------------------------------------------------


def _site_event(obj: GameObject, event_type: EventType, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(
        type=event_type,
        payload=payload,
        source=obj.id,
        controller=obj.controller,
    )


def _opp(state: GameState, player_id: str) -> str | None:
    return scp._first_opposing_player(state, player_id)


def _count_forgotten(state: GameState, player_id: str) -> int:
    """Count cards in the player's scp_forgotten zone."""
    return len(list(getattr(state, "scp_forgotten", {}).get(player_id, [])))


def _has_friendly_mnestic(state: GameState, controller: str) -> bool:
    """True iff the controller has at least one active Mnestic personnel."""
    return scp.has_mnestic(state, controller)


def _count_phylactery_audits_fired(state: GameState, player_id: str) -> int:
    """Read how many Phylactery Audits have fired for this player this game.

    The engine increments ``state.scp_sites[player_id]["phylactery_audits"]``
    each time a ``SCP_PHYLACTERY_AUDIT_OFFER`` is accepted. We read that
    counter here for alt-win checks and procedure effects.
    """
    return int(scp.site(state, player_id).get("phylactery_audits", 0))


# ---------------------------------------------------------------------------
# Bespoke on-reveal / effect functions
# ---------------------------------------------------------------------------

# --- Mikaeus: when returned from scp_forgotten, opposing breach +1 ---

def _mikaeus_audit_return(obj: GameObject, state: GameState) -> list[Event]:
    """Fired by the engine when Mikaeus returns via Phylactery Audit.

    Hooks the ``SCP_PHYLACTERY_AUDIT_OFFER`` acceptance path: the engine
    calls ``card.scp_on_audit_return(obj, state)`` if present.
    """
    opp_id = _opp(state, obj.controller)
    if opp_id is not None:
        scp.site(state, opp_id)["breach"] = (
            scp.site(state, opp_id).get("breach", 0) + 1
        )
    return [_site_event(
        obj,
        EventType.SCP_BREACH_TICK,
        amount=1,
        reason="mikaeus_lich_resurrection_surge",
        target=opp_id,
    )]


# --- Necropotence Specimen: when audit cost is paid, draw 1 paperwork ---

def _necropotence_audit_return(obj: GameObject, state: GameState) -> list[Event]:
    """When Necropotence returns via Phylactery Audit, grant 1 briefing token.

    The engine calls ``card.scp_on_audit_return`` if present after
    accepting an audit offer. Briefing +1 models the "drawing a card" effect
    of the MTG Necropotence.
    """
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [_site_event(
        obj,
        EventType.SCP_INCIDENT_RESOLVED,
        reason="necropotence_audit_draw",
        briefing=s["briefing"],
    )]


# ---------------------------------------------------------------------------
# Procedure effect factories
# ---------------------------------------------------------------------------


def _phylactery_activation_protocol_effect():
    """Pay X ethics, return any Phylactery-Audit card from scp_forgotten.

    X is the audit cost of the chosen card. AI heuristic: cheapest audit
    cost card first. Increments ``phylactery_audits`` counter.
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        forgotten_zone = getattr(state, "scp_forgotten", {})
        forgotten = list(forgotten_zone.get(obj.controller, []))
        # Filter to cards that have Phylactery Audit
        candidates: list[GameObject] = []
        for fid in forgotten:
            fan = state.objects.get(fid)
            if fan is None:
                continue
            audit_cost = int(getattr(fan.card_def, "scp_phylactery_audit", 0) or 0)
            if audit_cost >= 1:
                candidates.append(fan)
        if not candidates:
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="phylactery_activation_whiff",
            )]
        # Cheapest first for AI
        target = min(candidates, key=lambda a: int(getattr(a.card_def, "scp_phylactery_audit", 0) or 0))
        audit_cost = int(getattr(target.card_def, "scp_phylactery_audit", 0))
        s = scp.site(state, obj.controller)
        current_debt = s.get("ethics_debt", 0)
        if current_debt + audit_cost > 8:
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="phylactery_activation_over_ethics_cap",
            )]
        s["ethics_debt"] = current_debt + audit_cost
        # Move card from forgotten back to dossier queue (anomalies pending)
        if obj.controller in forgotten_zone:
            items = list(forgotten_zone[obj.controller])
            if target.id in items:
                items.remove(target.id)
            forgotten_zone[obj.controller] = type(forgotten_zone[obj.controller])(items)
        # Put it back into pending anomalies
        target.state.scp_status = "pending"
        anomalies = state.scp_anomalies.setdefault(obj.controller, [])
        if target.id not in anomalies:
            anomalies.append(target.id)
        # Bump audit counter
        s["phylactery_audits"] = s.get("phylactery_audits", 0) + 1
        # Fire on_audit_return if present
        extra: list[Event] = []
        on_return = getattr(target.card_def, "scp_on_audit_return", None)
        if callable(on_return):
            extra = on_return(target, state) or []
        return [_site_event(
            obj,
            EventType.SCP_ANOMALY_REVEALED,
            reason="phylactery_activation_protocol",
            object_id=target.id,
            audit_cost=audit_cost,
            phylactery_audits=s["phylactery_audits"],
        )] + extra
    return effect


def _mnestic_necromancy_audit_effect():
    """Grant Mnestic + Phylactery Audit 1 to all your personnel until end of turn.

    Sets a transient flag ``scp_mnestic_necromancy_active`` on each personnel
    object. The engine already checks ``scp_mnestic_gained`` for Mnestic;
    the PA-1 grant is tracked via ``scp_phylactery_audit_temp = 1`` — when a
    temporary-PA card is memory-holed the engine reads ``scp_phylactery_audit``
    first, then checks ``scp_phylactery_audit_temp`` as a fallback.
    End-of-turn cleanup: the SCP turn manager clears ``scp_mnestic_necromancy_active``
    and ``scp_phylactery_audit_temp`` at turn end (honoured via the engine's
    ``end_of_turn_temp_flag_cleanup`` pass).
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        granted = 0
        for pid in list(state.scp_personnel.get(obj.controller, [])):
            person = state.objects.get(pid)
            if not person or person.zone != ZoneType.BATTLEFIELD:
                continue
            if person.state.scp_status != "active":
                continue
            person.state.scp_mnestic_gained = True
            person.state.scp_mnestic_necromancy_active = True
            person.state.scp_phylactery_audit_temp = 1
            granted += 1
        return [_site_event(
            obj,
            EventType.SCP_MNESTIC_ACTIVE,
            reason="mnestic_necromancy_audit",
            granted_count=granted,
        )]
    return effect


def _lich_chain_audit_effect():
    """If 3+ cards in scp_forgotten, gain 1 archive and pay 1 ethics_debt."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        if _count_forgotten(state, obj.controller) < 3:
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="lich_chain_audit_whiff",
                forgotten=_count_forgotten(state, obj.controller),
            )]
        s = scp.site(state, obj.controller)
        s["ethics_debt"] = s.get("ethics_debt", 0) + 1
        s["archives"] = s.get("archives", 0) + 1
        events: list[Event] = [_site_event(
            obj,
            EventType.SCP_ARCHIVE_GAINED,
            reason="lich_chain_audit",
            amount=1,
            archives=s["archives"],
            ethics_debt=s["ethics_debt"],
        )]
        if game is not None:
            events = scp.gain_archives(game, obj.controller, 1, source=obj.id) + events[1:]
        return events
    return effect


def _class_v_phylactery_resurrection_effect():
    """Return up to 2 Phylactery-Audit cards from scp_forgotten. Pay total X+1 ethics.

    X = sum of audit costs of returned cards. The +1 is the premium for
    a mass resurrection. Increments ``phylactery_audits`` for each card.
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        forgotten_zone = getattr(state, "scp_forgotten", {})
        forgotten = list(forgotten_zone.get(obj.controller, []))
        candidates: list[tuple[GameObject, int]] = []
        for fid in forgotten:
            fan = state.objects.get(fid)
            if fan is None:
                continue
            audit_cost = int(getattr(fan.card_def, "scp_phylactery_audit", 0) or 0)
            if audit_cost >= 1:
                candidates.append((fan, audit_cost))
        if not candidates:
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="class_v_resurrection_whiff",
            )]
        # Pick up to 2 cheapest
        candidates.sort(key=lambda x: x[1])
        chosen = candidates[:2]
        total_cost = sum(c for _, c in chosen) + 1  # +1 premium
        s = scp.site(state, obj.controller)
        if s.get("ethics_debt", 0) + total_cost > 8:
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="class_v_resurrection_over_cap",
                total_cost=total_cost,
            )]
        s["ethics_debt"] = s.get("ethics_debt", 0) + total_cost
        events: list[Event] = []
        for target, audit_cost in chosen:
            # Remove from forgotten
            if obj.controller in forgotten_zone:
                items = list(forgotten_zone[obj.controller])
                if target.id in items:
                    items.remove(target.id)
                forgotten_zone[obj.controller] = type(forgotten_zone[obj.controller])(items)
            target.state.scp_status = "pending"
            anomalies = state.scp_anomalies.setdefault(obj.controller, [])
            if target.id not in anomalies:
                anomalies.append(target.id)
            s["phylactery_audits"] = s.get("phylactery_audits", 0) + 1
            on_return = getattr(target.card_def, "scp_on_audit_return", None)
            if callable(on_return):
                events.extend(on_return(target, state) or [])
            events.append(_site_event(
                obj,
                EventType.SCP_ANOMALY_REVEALED,
                reason="class_v_phylactery_resurrection",
                object_id=target.id,
                audit_cost=audit_cost,
            ))
        return events
    return effect


def _memory_hole_counter_audit_effect():
    """When opp memory-holes your anomaly this turn, gain 1 clearance.

    Hooks the ``SCP_MEMORY_HOLE`` event at resolve time. We register an
    end-of-turn watcher: the first time an opponent's memory-hole fires
    against the controller's anomalies, clearance +1 and the watcher
    self-removes. Implemented as a site flag ``mnr_counter_audit_watching``
    so it composes cleanly with other watchers.
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        s = scp.site(state, obj.controller)
        # Set a "watching this turn" flag the engine checks on SCP_MEMORY_HOLE
        s["mnr_counter_audit_watching"] = True
        s["mnr_counter_audit_rewarded"] = False
        return [_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="memory_hole_counter_audit_armed",
        )]
    return effect


# ---------------------------------------------------------------------------
# ANOMALIES (13)
# ---------------------------------------------------------------------------


# 1. Liliana, Class-V Lich-Form — mythic anchor. PA 3 + Mnestic.
_LILIANA_LICH = _mnestic_personnel(  # reuse helper only for Mnestic tag; it's an anomaly
    _phylactery_audit(
        _fbn_card(
            "SCP-FBN-8001: Liliana, Class-V Lich-Form",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=3,
            hazard=4,
            red_tape=2,
            subtypes={"Lich", "Planeswalker", "Euclid"},
            text=(
                "Phylactery Audit 3. Mnestic. The binding failed. What emerged "
                "from the veil wears her face but filed a containment waiver "
                "that self-amended three times before signing. Euclid class. "
                "Containment integrity: holding. Barely."
            ),
            rarity="mythic",
            archetype=_ARCHETYPE,
            art_prompt=(
                "SCP Foundation containment cell, stark sodium arc lighting, "
                "a serene woman in Foundation-gray robes surrounded by floating "
                "chains of dark necromantic runes; redacted site-document "
                "watermarks, deep black and cold gold palette, no text, no logos."
            ),
        ),
        x=3,
    ),
)
# _mnestic_personnel returns a CardDefinition; fix type since it's an anomaly def
_LILIANA_LICH.scp_mnestic = True
_LILIANA_LICH.scp_expansion = "Foundations Beyond"
_LILIANA_LICH.scp_expansion_code = "FBN"
_LILIANA_LICH.scp_archetype = _ARCHETYPE


# 2. Mikaeus the Unhallowed — mythic. PA 2. On audit return, opp breach +1.
_MIKAEUS = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8002: Mikaeus the Unhallowed, Lich Specimen",
        CardType.SCP_ANOMALY,
        containment=5,
        curiosity=3,
        hazard=4,
        red_tape=2,
        subtypes={"Lich", "Cleric", "Euclid"},
        text=(
            "Phylactery Audit 2. When this returns from scp_forgotten, "
            "opposing breach +1. Specimen designation: SCP-FBN-8002. "
            "Class: Euclid. He teaches, and what he teaches is a second "
            "death that doesn't take."
        ),
        rarity="mythic",
        archetype=_ARCHETYPE,
    ),
    x=2,
)
_MIKAEUS.scp_on_audit_return = _mikaeus_audit_return


# 3. Endrek Sahr, Necrotic Engineer — rare. PA 2.
_ENDREK_SAHR = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8003: Endrek Sahr, Necrotic Engineer Specimen",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=3,
        hazard=3,
        red_tape=1,
        subtypes={"Lich", "Wizard", "Euclid"},
        text=(
            "Phylactery Audit 2. The production run is perpetual. "
            "Containment of output entities is ongoing; containment of the "
            "source entity is technically stable. Technically."
        ),
        rarity="rare",
        archetype=_ARCHETYPE,
    ),
    x=2,
)


# 4. Atraxa-Lich Pattern Variant — mythic. PA 3 + Mnestic.
_ATRAXA_LICH = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8004: Atraxa-Lich Pattern Variant",
        CardType.SCP_ANOMALY,
        containment=6,
        curiosity=4,
        hazard=3,
        red_tape=2,
        subtypes={"Lich", "Angel", "Phyrexian", "Euclid"},
        text=(
            "Phylactery Audit 3. Mnestic. The Praetor-pattern persists "
            "across memory-hole cycles. Mnestic designation because "
            "standard amnestic protocols simply don't apply — it "
            "remembers being forgotten and adapts. Class: Euclid."
        ),
        rarity="mythic",
        archetype=_ARCHETYPE,
    ),
    x=3,
)
_ATRAXA_LICH.scp_mnestic = True


# 5. Demonic Animator-Pact Specimen — rare. PA 2.
_DEMONIC_ANIMATOR = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8005: Demonic Animator-Pact Specimen",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=2,
        hazard=3,
        red_tape=1,
        subtypes={"Lich", "Demon", "Euclid"},
        text=(
            "Phylactery Audit 2. Specimen generates thrall-entities on a "
            "22-hour cycle. The pact terms are redacted under Directive "
            "O5-[REDACTED]. Ethics review pending since [DATE REDACTED]."
        ),
        rarity="rare",
        archetype=_ARCHETYPE,
    ),
    x=2,
)


# 6. Class-IV Lich-Vessel — rare. PA 2.
_LICH_VESSEL = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8006: Class-IV Lich-Vessel",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=3,
        hazard=2,
        red_tape=1,
        subtypes={"Lich", "Undead", "Euclid"},
        text=(
            "Phylactery Audit 2. Vessel-class entities maintain "
            "consciousness coherence across successive containment "
            "failures. File the paperwork. The paperwork will be "
            "filed again."
        ),
        rarity="rare",
        archetype=_ARCHETYPE,
    ),
    x=2,
)


# 7. Class-III Phylactery-Bound Wraith — uncommon. PA 1.
_PHYLACTERY_WRAITH = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8007: Class-III Phylactery-Bound Wraith",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Wraith", "Undead", "Euclid"},
        text=(
            "Phylactery Audit 1. The binding object is a standard "
            "commercial jewelry box. We have locked it in three "
            "separate vaults. It is in three separate vaults. "
            "It is also here."
        ),
        rarity="uncommon",
        archetype=_ARCHETYPE,
    ),
    x=1,
)


# 8. Necropotence Specimen — rare. PA 2. On audit return, briefing +1.
_NECROPOTENCE = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8008: Necropotence Specimen",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=3,
        hazard=1,
        red_tape=1,
        subtypes={"Lich", "Artifact", "Euclid"},
        text=(
            "Phylactery Audit 2. When you pay X ethics for this audit, "
            "gain 1 paperwork. The cost of knowing is knowing. "
            "Lim-Dûl pattern. Refer to file SCP-FBN-8008-Addendum-IV."
        ),
        rarity="rare",
        archetype=_ARCHETYPE,
    ),
    x=2,
)
_NECROPOTENCE.scp_on_audit_return = _necropotence_audit_return


# 9. Class-III Reanimator Pattern — uncommon. PA 1.
_REANIMATOR_PATTERN = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8009: Class-III Reanimator Pattern",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Lich", "Wizard", "Euclid"},
        text=(
            "Phylactery Audit 1. Standard reanimation matrix. Sedris "
            "pattern. Containment protocol: limit arcane substrate "
            "availability within 40m. Updated every six hours."
        ),
        rarity="uncommon",
        archetype=_ARCHETYPE,
    ),
    x=1,
)


# 10. Bone-Vessel, Animated — common. PA 1.
_BONE_VESSEL = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8010: Bone-Vessel, Animated",
        CardType.SCP_ANOMALY,
        containment=2,
        curiosity=1,
        hazard=1,
        red_tape=0,
        subtypes={"Skeleton", "Undead", "Euclid"},
        text=(
            "Phylactery Audit 1. Low-complexity osseous animation. "
            "Crovax pattern (degraded). No apparent intelligence. "
            "Continued containment recommended pending pattern "
            "escalation review."
        ),
        rarity="common",
        archetype=_ARCHETYPE,
    ),
    x=1,
)


# 11. Recurring Lich-Fragment — common. PA 1.
_RECURRING_FRAGMENT = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8011: Recurring Lich-Fragment",
        CardType.SCP_ANOMALY,
        containment=2,
        curiosity=2,
        hazard=1,
        red_tape=0,
        subtypes={"Lich", "Undead", "Euclid"},
        text=(
            "Phylactery Audit 1. A shard of a larger pattern. Korlash "
            "fragment, presumed heir-class. Does not recognize "
            "containment as a permanent state. Neither do we."
        ),
        rarity="common",
        archetype=_ARCHETYPE,
    ),
    x=1,
)


# 12. Class-IV Wraith-Network — uncommon. PA 1.
_WRAITH_NETWORK = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8012: Class-IV Wraith-Network",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Wraith", "Network", "Euclid"},
        text=(
            "Phylactery Audit 1. Network exhibits hive-continuity: "
            "fragmenting does not terminate the whole. Volrath-class "
            "distributed persistence. Isolation protocols have been "
            "filed fourteen times. All fourteen are in scp_forgotten."
        ),
        rarity="uncommon",
        archetype=_ARCHETYPE,
    ),
    x=1,
)


# 13. Death's Auditor — uncommon. PA 1. Mnestic.
_DEATHS_AUDITOR = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-8013: Death's Auditor",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Lich", "Auditor", "Euclid"},
        text=(
            "Phylactery Audit 1. Mnestic. It reads every memory-hole "
            "request. It approves them. It keeps a copy. Phage-adjacent "
            "pattern; exact origin indeterminate. The copy is always there "
            "when you look."
        ),
        rarity="uncommon",
        archetype=_ARCHETYPE,
    ),
    x=1,
)
_DEATHS_AUDITOR.scp_mnestic = True


# ---------------------------------------------------------------------------
# PERSONNEL (7)
# ---------------------------------------------------------------------------

# Helper: create a personnel with FBN metadata. Mirrors MNR's _mnestic_personnel
# convention for plain personnel creation.


def _lich_personnel(
    name: str,
    *,
    skills: dict,
    red_tape: int,
    subtypes: set,
    text: str,
    clearance: int = 0,
    rarity: str | None = None,
    aura: dict | None = None,
    mnestic: bool = False,
    phylactery_audit_x: int = 0,
) -> CardDefinition:
    """Create a Lich Phylactery archetype personnel with FBN metadata."""
    full_subtypes = set(subtypes) | {"Necrologist"}
    if mnestic:
        full_subtypes.add("Mnestic")
    card = scp.make_scp_card(
        name,
        CardType.SCP_PERSONNEL,
        skills=skills,
        red_tape=red_tape,
        clearance=clearance,
        subtypes=full_subtypes,
        text=text,
        rarity=rarity,
        aura=aura,
    )
    if mnestic:
        card.scp_mnestic = True
    if phylactery_audit_x >= 1:
        _phylactery_audit(card, phylactery_audit_x)
    return _with_fbn_metadata(card, archetype=_ARCHETYPE)


# 1. Dr. Aliz Volgrim, Mnestic Necrologist — rare, Mnestic, PA 2.
_DR_VOLGRIM = _lich_personnel(
    "Dr. Aliz Volgrim, Mnestic Necrologist",
    skills={"research": 2, "contain": 1},
    red_tape=2,
    clearance=1,
    subtypes={"Scientist", "Director"},
    text=(
        "Mnestic. Phylactery Audit 2 (this personnel). Volgrim remembers "
        "every memory-hole on her watch. So do her files. So does the "
        "duplicate she keeps locked in the secondary vault."
    ),
    rarity="rare",
    mnestic=True,
    phylactery_audit_x=2,
)


# 2. Operative O5-Liliana "Lich-Liaison" — rare, Mnestic, PA 1.
_O5_LILIANA = _lich_personnel(
    'Operative O5-Liliana "Lich-Liaison"',
    skills={"contain": 2},
    red_tape=2,
    clearance=1,
    subtypes={"Operative", "O5"},
    text=(
        "Mnestic. Phylactery Audit 1. Classified as a Thaumiel-adjacent "
        "cooperative asset before the reclassification committee was "
        "reclassified. Current status: active. Current loyalty: "
        "under review."
    ),
    rarity="rare",
    mnestic=True,
    phylactery_audit_x=1,
)


# 3. Researcher "Bonemark" — common, PA 1.
_RESEARCHER_BONEMARK = _lich_personnel(
    'Researcher "Bonemark"',
    skills={"research": 1},
    red_tape=1,
    subtypes={"Researcher"},
    text=(
        "Phylactery Audit 1. The name is not a name; it is a designation "
        "from the debrief report. Whatever was in the containment cell "
        "when Bonemark opened it, we now call Bonemark."
    ),
    rarity="common",
    phylactery_audit_x=1,
)


# 4. Class-A Necromantic Cartographer — uncommon.
_NECROMANTIC_CARTOGRAPHER = _lich_personnel(
    "Class-A Necromantic Cartographer",
    skills={"research": 2},
    red_tape=1,
    subtypes={"Researcher", "Cartographer"},
    text=(
        "Maps the geography of things that recur. Specialization: "
        "cyclic anomaly spatial footprint. Cross-reference with the "
        "Phylactery Audit Bureau for topological continuity."
    ),
    rarity="uncommon",
)


# 5. Researcher "Knell" — uncommon, PA 1.
_RESEARCHER_KNELL = _lich_personnel(
    'Researcher "Knell"',
    skills={"contain": 2},
    red_tape=1,
    subtypes={"Agent", "Security"},
    text=(
        "Phylactery Audit 1. Containment-track operative. Designation "
        "derives from the sound heard at each audit confirmation. "
        "Containment record: exemplary. Memory record: incomplete."
    ),
    rarity="uncommon",
    phylactery_audit_x=1,
)


# 6. Operative "Phylactery-Hand" — common, Mnestic.
_PHYLACTERY_HAND = _lich_personnel(
    'Operative "Phylactery-Hand"',
    skills={"contain": 1},
    red_tape=1,
    subtypes={"Operative", "MTF"},
    text=(
        "Mnestic. Frontline handler for Phylactery-class Euclid entities. "
        "Inoculated. Remembers the previous six memory-holes. Prefers "
        "not to count the ones before that."
    ),
    rarity="common",
    mnestic=True,
)


# 7. Dr. Veska, Containment Theologian — uncommon.
_DR_VESKA = _lich_personnel(
    "Dr. Veska, Containment Theologian",
    skills={"research": 2},
    red_tape=1,
    subtypes={"Scientist", "Theologian"},
    text=(
        "Specializes in the metaphysics of recursive death — the question "
        "of what binds a lich to its phylactery and whether a Foundation "
        "containment cell can substitute. Currently: seems to work."
    ),
    rarity="uncommon",
)


# ---------------------------------------------------------------------------
# FACILITIES (4)
# ---------------------------------------------------------------------------


# 1. Lich Containment Vault — rare. Bonus: contain +1, research +1.
#    Phylactery Audit costs are -1 ethics (min 0).
_LICH_CONTAINMENT_VAULT = _fbn_card(
    "Lich Containment Vault",
    CardType.SCP_FACILITY,
    red_tape=2,
    bonus={"contain": 1, "research": 1},
    subtypes={"Vault", "Containment"},
    text=(
        "Contain +1, research +1. Your Phylactery Audit costs are -1 "
        "ethics_debt (minimum 0). Reinforced with memorial-grade obsidian "
        "and three ethics review waivers."
    ),
    rarity="rare",
    archetype=_ARCHETYPE,
)
# Engine reads scp_phylactery_audit_cost_reduction to apply the -1 at audit time.
_LICH_CONTAINMENT_VAULT.scp_phylactery_audit_cost_reduction = 1


# 2. Phylactery Audit Bureau — uncommon. Bonus: research +1.
_PHYLACTERY_AUDIT_BUREAU = _fbn_card(
    "Phylactery Audit Bureau",
    CardType.SCP_FACILITY,
    red_tape=1,
    bonus={"research": 1},
    subtypes={"Bureau", "Archive"},
    text=(
        "Research +1. The Bureau processes every Phylactery Audit request "
        "in chronological order. The oldest request is from 1987. "
        "Processing continues."
    ),
    rarity="uncommon",
    archetype=_ARCHETYPE,
)


# 3. Necromancer's Containment Chamber — uncommon. Bonus: contain +1.
_NECROMANCER_CHAMBER = _fbn_card(
    "Necromancer's Containment Chamber",
    CardType.SCP_FACILITY,
    red_tape=1,
    bonus={"contain": 1},
    subtypes={"Chamber", "Containment"},
    text=(
        "Contain +1. Purpose-built for entities that have previously "
        "escaped containment via death. The Chamber assumes at least one "
        "prior failure and designs around it."
    ),
    rarity="uncommon",
    archetype=_ARCHETYPE,
)


# 4. Mnestic Necropolis Site — rare. Bonus: contain +1. Personnel are Mnestic.
_MNESTIC_NECROPOLIS = _fbn_card(
    "Mnestic Necropolis Site",
    CardType.SCP_FACILITY,
    red_tape=2,
    bonus={"contain": 1},
    subtypes={"Site", "Mnestic", "Necropolis"},
    text=(
        "Contain +1. Your personnel are Mnestic while this facility is "
        "active. Site designation: MNESTIC-NECROPOLIS. All staff are "
        "dosed on entry. The Site remembers what leaves."
    ),
    rarity="rare",
    archetype=_ARCHETYPE,
)
# Engine reads scp_facility_grants_mnestic to propagate Mnestic to all active personnel.
_MNESTIC_NECROPOLIS.scp_facility_grants_mnestic = True


# ---------------------------------------------------------------------------
# PROCEDURES (5)
# ---------------------------------------------------------------------------


# 1. Phylactery Activation Protocol — rare, PA 2+.
_PHYLACTERY_ACTIVATION = _fbn_card(
    "Phylactery Activation Protocol",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Protocol", "Recovery"},
    text=(
        "Pay X ethics_debt (X = the audit cost of the target card). "
        "Return any Phylactery-Audit card from scp_forgotten to your "
        "dossier queue."
    ),
    rarity="rare",
    archetype=_ARCHETYPE,
    effect=_phylactery_activation_protocol_effect(),
)


# 2. Mnestic Necromancy Audit — uncommon.
_MNESTIC_NECROMANCY_AUDIT = _fbn_card(
    "Mnestic Necromancy Audit",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Audit", "Mnestic"},
    text=(
        "Grant Mnestic + Phylactery Audit 1 to all your personnel until "
        "end of turn. The Mnestic dose is temporary; the memory of the "
        "audit is not."
    ),
    rarity="uncommon",
    archetype=_ARCHETYPE,
    effect=_mnestic_necromancy_audit_effect(),
)


# 3. Lich-Chain Audit — rare.
_LICH_CHAIN_AUDIT = _fbn_card(
    "Lich-Chain Audit",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    subtypes={"Audit", "Bureaucracy"},
    text=(
        "If you have 3 or more cards in scp_forgotten, gain 1 archive "
        "and pay 1 ethics_debt. The forgotten feed the archives; the "
        "archives know this."
    ),
    rarity="rare",
    archetype=_ARCHETYPE,
    effect=_lich_chain_audit_effect(),
)


# 4. Class-V Phylactery Resurrection — mythic.
_CLASS_V_RESURRECTION = _fbn_card(
    "Class-V Phylactery Resurrection",
    CardType.SCP_PROCEDURE,
    red_tape=3,
    subtypes={"Protocol", "Recovery", "Ritual"},
    text=(
        "Return up to 2 Phylactery-Audit cards from scp_forgotten. "
        "Pay total X+1 ethics_debt (X = sum of their audit costs). "
        "Mass resurrection. O5-approval technically not granted but "
        "technically not refused."
    ),
    rarity="mythic",
    archetype=_ARCHETYPE,
    effect=_class_v_phylactery_resurrection_effect(),
)


# 5. Memory-Hole Counter-Audit — uncommon.
_COUNTER_AUDIT = _fbn_card(
    "Memory-Hole Counter-Audit",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Audit", "Counter"},
    text=(
        "When an opponent memory-holes your anomaly this turn, gain "
        "1 clearance. File the counter-audit before they file the "
        "hole."
    ),
    rarity="uncommon",
    archetype=_ARCHETYPE,
    effect=_memory_hole_counter_audit_effect(),
)


# ---------------------------------------------------------------------------
# MANDATE (1)
# ---------------------------------------------------------------------------


def _build_phylactery_chain_mandate() -> CardDefinition:
    """Mandate FBN-PC: Phylactery Chain Doctrine.

    Primary alt-win: ``phylactery_chain`` — when 4+ Phylactery Audits have
    fired this game, the controller wins at end of their next turn.

    Also carries ``scp_alt_win = "mnestic_saturation"`` so the deck can
    piggyback on the MNR mnestic_saturation win condition (4 Mnestic
    personnel on battlefield + breach = 0) as a secondary route.
    """
    card = _fbn_card(
        "Mandate FBN-PC: Phylactery Chain Doctrine",
        CardType.SCP_MANDATE,
        red_tape=3,
        clearance=2,
        subtypes={"Mandate", "Doctrine", "Euclid"},
        text=(
            "Mandate. If 4 or more successful Phylactery Audits have fired "
            "this game, you win at end of your next turn. "
            "(Alt-win bridge: if you control 4+ active Mnestic personnel "
            "and your breach is 0, win condition: mnestic_saturation also "
            "applies.) The doctrine is clear. The lich was never truly "
            "contained. The Foundation is now the phylactery."
        ),
        rarity="mythic",
        archetype=_ARCHETYPE,
    )
    # Primary alt-win for this archetype.
    card.scp_alt_win = "phylactery_chain"
    # Secondary bridge: piggybacks on MNR mnestic_saturation.
    # The engine reads scp_alt_win_secondary to check additional win conditions.
    card.scp_alt_win_secondary = "mnestic_saturation"
    return card


_PHYLACTERY_CHAIN_MANDATE = _build_phylactery_chain_mandate()


# ---------------------------------------------------------------------------
# Final assembly
# ---------------------------------------------------------------------------


LICH_PHYLACTERY_CARDS: list[CardDefinition] = [
    # --- Anomalies (13) ---
    _LILIANA_LICH,
    _MIKAEUS,
    _ENDREK_SAHR,
    _ATRAXA_LICH,
    _DEMONIC_ANIMATOR,
    _LICH_VESSEL,
    _PHYLACTERY_WRAITH,
    _NECROPOTENCE,
    _REANIMATOR_PATTERN,
    _BONE_VESSEL,
    _RECURRING_FRAGMENT,
    _WRAITH_NETWORK,
    _DEATHS_AUDITOR,
    # --- Personnel (7) ---
    _DR_VOLGRIM,
    _O5_LILIANA,
    _RESEARCHER_BONEMARK,
    _NECROMANTIC_CARTOGRAPHER,
    _RESEARCHER_KNELL,
    _PHYLACTERY_HAND,
    _DR_VESKA,
    # --- Facilities (4) ---
    _LICH_CONTAINMENT_VAULT,
    _PHYLACTERY_AUDIT_BUREAU,
    _NECROMANCER_CHAMBER,
    _MNESTIC_NECROPOLIS,
    # --- Procedures (5) ---
    _PHYLACTERY_ACTIVATION,
    _MNESTIC_NECROMANCY_AUDIT,
    _LICH_CHAIN_AUDIT,
    _CLASS_V_RESURRECTION,
    _COUNTER_AUDIT,
    # --- Mandate (1) ---
    _PHYLACTERY_CHAIN_MANDATE,
]

_CARDS = LICH_PHYLACTERY_CARDS
