"""FBN archetype: Planeswalker Detention (30 cards).

Thaumiel-class multiverse incursions — the Foundation uses captured
spark-bearers as cross-containment assets. Strategy: contain opposing
Anomalies one after another; each containment fires Spark Containment N
for clearance gain. Cross the clearance-6 threshold to extra-draw, which
fuels the next Detention. Win via existing ``thaumiel`` alt-win (3
contained + 0 breach) or through pure tempo.

Composition: 12 Anomalies, 7 Personnel, 5 Facilities, 5 Procedures, 1 Mandate.

Mechanic surface: Spark Containment N (primary), Brief N (splash).
Engine note: loyalty-style abilities are collapsed to a single static
effect per card (scp_on_reveal or scp_on_contain). See per-card comments.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import (
    _brief,
    _fbn_card,
    _spark_containment,
)

ARCHETYPE = "planeswalker_detention"


# ---------------------------------------------------------------------------
# Bespoke interceptor helpers
# ---------------------------------------------------------------------------


def _draw_paperwork(n: int):
    """Return an on_contain hook that draws N paperwork cards for the controller.

    Used by Jace (draw 2) and Karn (gain 2 clearance, handled separately).
    Emits SCP_PAPERWORK_TICK for each draw tick.
    # Loyalty collapsed: chose +1 ability (draw/cycle effect)
    """
    def hook(obj, state):
        events = []
        s = scp.site(state, obj.controller)
        for _ in range(n):
            events.append(scp.Event(
                type=scp.EventType.SCP_PAPERWORK_TICK,
                payload={
                    "player": obj.controller,
                    "source": obj.id,
                    "reason": "spark_draw",
                    "amount": 1,
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return hook


def _reduce_opposing_queue(obj, state):
    """Liliana on_contain: opposing dossier queue -1 (discard top pending dossier).

    # Loyalty collapsed: chose -3 ability (disruptive/removal effect)
    Emits SCP_INCIDENT_RESOLVED with reason="necromantic_purge" so AI
    and analytics can track the disruption.
    """
    events = []
    # Find the opposing player
    opp_id = None
    for pid in state.scp_sites:
        if pid != obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return events

    # Misfile the top dossier from the opposing pending queue
    opp_site = scp.site(state, opp_id)
    pending = opp_site.get("pending_queue") or []
    if pending:
        # Remove the front of the queue (index 0 = next to be opened)
        victim_id = pending[0]
        victim = state.objects.get(victim_id)
        if victim:
            _, _, misfile_events = scp.misfile_dossier(
                # misfile_dossier requires a game object; we pass state's game ref
                state._game if hasattr(state, "_game") else state,
                opp_id,
                victim_id,
                amount=1,
                source=obj.id,
            )
            events.extend(misfile_events)
    events.append(scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "necromantic_purge",
            "target_player": opp_id,
        },
        source=obj.id,
        controller=obj.controller,
    ))
    return events


def _redact_opposing_dossier(obj, state):
    """Chandra on_contain: redact 1 opposing dossier (force_audit intensity 1).

    # Loyalty collapsed: chose -2 ability (direct damage / burn effect)
    """
    opp_id = None
    for pid in state.scp_sites:
        if pid != obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return []

    game = state._game if hasattr(state, "_game") else state
    events = scp.force_audit(game, opp_id, opp_id, intensity=1, source=obj.id)
    events.append(scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ignition_redact",
            "target_player": opp_id,
        },
        source=obj.id,
        controller=obj.controller,
    ))
    return events


def _gain_clearance(n: int):
    """Return an on_contain hook that grants N clearance to the controller.

    # Loyalty collapsed: chose +2 ability (resource gain effect)
    Used by Karn (gain 2 clearance on contain).
    """
    def hook(obj, state):
        s = scp.site(state, obj.controller)
        s["clearance"] += n
        return [scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "artifact_clearance",
                "clearance_gained": n,
                "clearance": s["clearance"],
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return hook


def _gain_turn_priority(obj, state):
    """Teferi on_contain: gain 1 turn-segment of priority (extra procedure slot).

    Implemented as Brief 1 — the briefing token represents the
    priority window the Temporal Adjuster carves out. The engine's
    existing paperwork-cycle interprets briefing as a turn-segment
    of priority for AI purposes.
    # Loyalty collapsed: chose +1 ability (tempo / priority effect)
    """
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "temporal_priority",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _jace_on_assign(personnel_obj, state, action: str):
    """Operative O5-Jace on_assign: look at top 2 of library; archive 1.

    Bespoke assign hook — fires when this personnel is committed to any
    assignment. Implements the "On assign, look at top 2; archive 1" text
    by emitting SCP_ARCHIVE_GAINED for the top card (greedy heuristic:
    always archive the first card found). Remaining card stays on top.
    """
    s = scp.site(state, personnel_obj.controller)
    archives_list = s.get("archives_list") or []
    lib = s.get("library") or []
    if lib:
        top_card = lib[0]
        archives_list.append(top_card)
        s["archives_list"] = archives_list
        s["archive_count"] = len(archives_list)
    return [scp.Event(
        type=scp.EventType.SCP_ARCHIVE_GAINED,
        payload={
            "player": personnel_obj.controller,
            "amount": 1,
            "archives": s.get("archives", 0),
            "reason": "jace_mindwarden",
        },
        source=personnel_obj.id,
        controller=personnel_obj.controller,
    )]


def _teferi_exhaust_on_assign(personnel_obj, state, action: str):
    """Operative O5-Teferi on_assign: once per turn, exhaust 1 opposing personnel.

    Bespoke assign hook. Fires only when the once-per-turn flag is clear.
    Targets the highest-skill opposing personnel (heuristic match to engine
    convention for Compleation Vector).
    # Loyalty collapsed: chose -3 ability (exhaust / temporal stall)
    """
    s = scp.site(state, personnel_obj.controller)
    if s.get("teferi_exhausted_this_turn"):
        return []
    s["teferi_exhausted_this_turn"] = True

    opp_id = None
    for pid in state.scp_sites:
        if pid != personnel_obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return []

    # Find highest-skill opposing personnel and exhaust them
    best_id = None
    best_skill = -1
    for staff_id in list(state.scp_personnel.get(opp_id, [])):
        staff = state.objects.get(staff_id)
        if not staff or staff.state.scp_status != "active":
            continue
        if not staff.card_def:
            continue
        skills = getattr(staff.card_def, "scp_skills", {})
        total = sum(skills.values())
        if total > best_skill:
            best_skill = total
            best_id = staff_id

    if best_id:
        target = state.objects[best_id]
        target.state.scp_status = "exhausted"

    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": personnel_obj.controller,
            "reason": "teferi_slow_hand",
            "target": best_id,
        },
        source=personnel_obj.id,
        controller=personnel_obj.controller,
    )]


def _mandate_upkeep_draw(obj, state):
    """Mandate on_reveal: while >=3 Planeswalker-type anomalies are contained, draw +1 at upkeep.

    Implemented as a briefing bump of 1 on reveal if the condition is met.
    The engine's upkeep paperwork tick reads briefing to determine extra draws.
    # Engine note: upkeep-conditional draw is approximated via briefing bonus
    #   at reveal time. Full per-upkeep re-evaluation is a TODO stub.
    # NERF cycle 2: threshold raised from >=2 to >=3 (mandate draw-engine
    #   fuelled the clearance loop too cheaply at 2 PW contained)
    """
    s = scp.site(state, obj.controller)
    contained = state.scp_contained.get(obj.controller) or []
    pw_count = 0
    for cid in contained:
        c = state.objects.get(cid)
        if not c or not c.card_def:
            continue
        subtypes = getattr(c.card_def.characteristics, "subtypes", set()) or set()
        if "Planeswalker" in subtypes:
            pw_count += 1
    if pw_count >= 3:
        s["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "detention_doctrine_upkeep",
            "planeswalker_contained": pw_count,
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _detention_site_charlie_boost(obj, state):
    """Multiversal Detention Site Charlie on_reveal: upgrade Spark Containment triggers.

    Tags the site so the engine's Spark Containment handler grants N+1
    instead of N clearance. Implemented as a site flag read by the
    spark_containment engine hook.
    """
    s = scp.site(state, obj.controller)
    s["spark_containment_bonus"] = s.get("spark_containment_bonus", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "site_charlie_boost",
            "spark_containment_bonus": s["spark_containment_bonus"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _hub_archive_once_per_turn(obj, state):
    """Planeswalker Containment Hub on_reveal: once per turn archive a contained PW for 1 archive.

    Seeds the site flag; the engine's contained-archive callback reads it.
    # TODO: full once-per-turn gating requires engine upkeep reset for this flag.
    """
    s = scp.site(state, obj.controller)
    s["hub_pw_archive_available"] = True
    return []


def _temporal_stasis_cell_reveal(obj, state):
    """Temporal Stasis Cell on_reveal: once per game, prevent 1 opposing anomaly breach.

    Sets a site flag the engine's breach-tick handler reads. Single-use.
    """
    s = scp.site(state, obj.controller)
    if not s.get("stasis_cell_used"):
        s["stasis_cell_prevent"] = True
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "temporal_stasis_cell",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _spark_audit_effect(obj, state):
    """Spark Audit procedure effect: gain clearance equal to contained anomaly count.

    # Loyalty collapsed: the Spark Audit is the +1 ability collapsed into a procedure.
    """
    s = scp.site(state, obj.controller)
    contained_count = len(state.scp_contained.get(obj.controller) or [])
    s["clearance"] = s.get("clearance", 0) + contained_count
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "spark_audit",
            "clearance_gained": contained_count,
            "clearance": s["clearance"],
            "contained_count": contained_count,
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _planar_detention_protocol_effect(obj, state):
    """Planar Detention Protocol: contain target opposing Anomaly (highest hazard heuristic).

    Spark Containment 2 fires via the engine's SCP_CONTAINED listener after
    the contain attempt resolves. This on_reveal hook performs the targeting
    heuristic and emits the containment attempt event.
    """
    opp_id = None
    for pid in state.scp_sites:
        if pid != obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return []

    # Target highest-hazard opposing active anomaly (engine convention)
    best_id = None
    best_hazard = -1
    for aid in list(state.scp_anomalies.get(opp_id) or []):
        a = state.objects.get(aid)
        if not a or not a.card_def:
            continue
        h = getattr(a.card_def, "scp_hazard", 0) or 0
        if h > best_hazard:
            best_hazard = h
            best_id = aid

    if best_id:
        return [scp.Event(
            type=scp.EventType.SCP_CONTAINMENT_ATTEMPT,
            payload={
                "player": obj.controller,
                "anomaly_id": best_id,
                "source": obj.id,
                "reason": "planar_detention_protocol",
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return []


def _spark_suppression_effect(obj, state):
    """Class-IV Spark Suppression Protocol: suppress target opposing anomaly's next breach.

    Emits SCP_PROTOCOL_APPLIED with reason "spark_suppression"; the engine's
    breach-tick handler checks for this flag and skips the next breach for
    the targeted anomaly.
    """
    opp_id = None
    for pid in state.scp_sites:
        if pid != obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return []

    best_id = None
    best_hazard = -1
    for aid in list(state.scp_anomalies.get(opp_id) or []):
        a = state.objects.get(aid)
        if not a or not a.card_def:
            continue
        h = getattr(a.card_def, "scp_hazard", 0) or 0
        if h > best_hazard:
            best_hazard = h
            best_id = aid

    events = []
    if best_id:
        target_obj = state.objects[best_id]
        target_obj.state.scp_breach_suppressed = True
        events.append(scp.Event(
            type=scp.EventType.SCP_PROTOCOL_APPLIED,
            payload={
                "player": obj.controller,
                "target": best_id,
                "reason": "spark_suppression",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


def _wanderer_recall_effect(obj, state):
    """Wanderer Recall Audit: return target contained Anomaly to pending queue.

    Targets the most-recently-contained anomaly (last in contained list)
    as a sensible heuristic. Moves the anomaly back from scp_contained to
    pending so it can be re-contained for another Spark Containment trigger.
    """
    s = scp.site(state, obj.controller)
    contained = state.scp_contained.get(obj.controller) or []
    if not contained:
        return []

    target_id = contained[-1]
    contained.remove(target_id)
    state.scp_contained[obj.controller] = contained

    pending = s.get("pending_queue") or []
    pending.append(target_id)
    s["pending_queue"] = pending

    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "wanderer_recall",
            "target": target_id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _detention_sweep_effect(obj, state):
    """Multiversal Detention Sweep: contain up to 2 opposing Anomalies (highest hazard each).

    Spark Containment 2 per contained anomaly fires via the engine listener.
    Auto-targets the two highest-hazard opposing anomalies.
    """
    opp_id = None
    for pid in state.scp_sites:
        if pid != obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return []

    candidates = []
    for aid in list(state.scp_anomalies.get(opp_id) or []):
        a = state.objects.get(aid)
        if not a or not a.card_def:
            continue
        h = getattr(a.card_def, "scp_hazard", 0) or 0
        candidates.append((h, aid))
    candidates.sort(reverse=True)
    top2 = [aid for _, aid in candidates[:2]]

    events = []
    for aid in top2:
        events.append(scp.Event(
            type=scp.EventType.SCP_CONTAINMENT_ATTEMPT,
            payload={
                "player": obj.controller,
                "anomaly_id": aid,
                "source": obj.id,
                "reason": "detention_sweep",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


# ---------------------------------------------------------------------------
# 12 Anomalies
# ---------------------------------------------------------------------------

# 1. Jace, Class-III Cognitive Manipulator — draw 2 on contain, Spark Containment 2.
# Loyalty collapsed: chose +1 ability (draw/cycle effect)
SCP_FBN_4001 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4001: Jace, Class-III Cognitive Manipulator",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=5,
        curiosity=4,
        hazard=2,
        red_tape=2,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "When contained, draw 2 paperwork. Spark Containment 2. "
            "Designation: SCP-FBN-4001. Class: Thaumiel. Status: "
            "Contained under Protocol CEREBRAL-LOCK. The specimen "
            "cooperates. The cooperation is annotated."
        ),
        rarity="mythic",
    ),
    n=2,
)
SCP_FBN_4001.scp_on_contain = _draw_paperwork(2)


# 2. Liliana, Class-IV Necromantic Conduit — opposing dossier queue -1 on contain. SC 2.
# Loyalty collapsed: chose -3 ability (disruption / removal effect)
SCP_FBN_4002 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4002: Liliana, Class-IV Necromantic Conduit",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=5,
        curiosity=3,
        hazard=3,
        red_tape=2,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "When contained, opposing dossier queue -1. Spark Containment 2. "
            "Designation: SCP-FBN-4002. Class: Thaumiel. Status: Contained "
            "under Protocol CHAIN-VEIL-SUPPRESSION. She cooperates by "
            "making everyone else not."
        ),
        rarity="mythic",
    ),
    n=2,
)
SCP_FBN_4002.scp_on_contain = _reduce_opposing_queue


# 3. Chandra, Class-III Thaumic Ignition — redact 1 opposing dossier on contain. SC 1.
# Loyalty collapsed: chose -2 ability (burn / redact effect)
SCP_FBN_4003 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4003: Chandra, Class-III Thaumic Ignition",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=3,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "When contained, redact 1 opposing dossier. Spark Containment 1. "
            "Designation: SCP-FBN-4003. Class: Thaumiel. Status: Contained "
            "under Protocol PYRO-BLANKET. The cell walls are fire-rated. "
            "The paperwork is not."
        ),
        rarity="rare",
    ),
    n=1,
)
SCP_FBN_4003.scp_on_contain = _redact_opposing_dossier


# 4. Teferi, Class-IV Temporal Adjuster — gain 1 turn-segment priority on contain. SC 2.
# Loyalty collapsed: chose +1 ability (tempo / priority effect as briefing)
SCP_FBN_4004 = _spark_containment(
    _brief(
        _fbn_card(
            "SCP-FBN-4004: Teferi, Class-IV Temporal Adjuster",
            CardType.SCP_ANOMALY,
            archetype=ARCHETYPE,
            containment=5,
            curiosity=4,
            hazard=1,
            red_tape=2,
            subtypes={"Planeswalker", "Thaumiel"},
            text=(
                "When contained, gain 1 turn-segment of priority (Brief 1). "
                "Spark Containment 2. "
                "Designation: SCP-FBN-4004. Class: Thaumiel. Status: Contained. "
                "The timeline holds. Specimen compliance rate: 98.4%. "
                "The 1.6% is reclassified as a scheduling conflict."
            ),
            rarity="mythic",
        ),
        n=1,
    ),
    n=2,
)
SCP_FBN_4004.scp_on_contain = _gain_turn_priority


# 5. Garruk, Class-III Beastmaster — SC 1. No bespoke hook (stat-line + mechanic only).
SCP_FBN_4005 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4005: Garruk, Class-III Beastmaster",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=3,
        hazard=3,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "Spark Containment 1. "
            "Designation: SCP-FBN-4005. Class: Thaumiel. Status: Contained. "
            "The fauna accompanying the specimen during initial ingress were "
            "catalogued. Not all of them have been located."
        ),
        rarity="rare",
    ),
    n=1,
)


# 6. Sorin, Class-IV Necromantic Patron — SC 2. No bespoke hook.
SCP_FBN_4006 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4006: Sorin, Class-IV Necromantic Patron",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=5,
        curiosity=3,
        hazard=2,
        red_tape=2,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "Spark Containment 2. "
            "Designation: SCP-FBN-4006. Class: Thaumiel. Status: Contained. "
            "The specimen requested a chair. The chair was provided. "
            "The chair is bolted to the floor. This was not explained."
        ),
        rarity="rare",
    ),
    n=2,
)


# 7. Karn, Class-V Artifact Vector — gain 2 clearance on contain. SC 2.
# Loyalty collapsed: chose +2 ability (resource/clearance gain)
SCP_FBN_4007 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4007: Karn, Class-V Artifact Vector",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=6,
        curiosity=4,
        hazard=2,
        red_tape=2,
        subtypes={"Planeswalker", "Thaumiel", "Golem"},
        text=(
            "When contained, gain 2 clearance. Spark Containment 2. "
            "Designation: SCP-FBN-4007. Class: Thaumiel. Status: Contained. "
            "The artifact vector appears to be made of silver. The "
            "silver is not silver. Containment integrity: holding."
        ),
        rarity="rare",
    ),
    n=2,
)
SCP_FBN_4007.scp_on_contain = _gain_clearance(2)


# 8. Tezzeret, Class-III Artifact Manipulator — SC 1. No bespoke hook.
SCP_FBN_4008 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4008: Tezzeret, Class-III Artifact Manipulator",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "Spark Containment 1. "
            "Designation: SCP-FBN-4008. Class: Thaumiel. Status: Contained. "
            "The etherium components were removed during intake. "
            "The spaces where they were remain warm."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# 9. Class-II Aspirant Spark Carrier — generic common. SC 1.
SCP_FBN_4009 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4009: Class-II Aspirant Spark Carrier",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "Spark Containment 1. "
            "Designation: SCP-FBN-4009. Class: Thaumiel. Status: Pending. "
            "Spark ignition event: Class-II (aspirant). "
            "The subject walked through a door that does not exist. "
            "We found them in Sub-Level 9. They do not remember the door."
        ),
        rarity="common",
    ),
    n=1,
)


# 10. Vraska, Class-IV Gorgon-Spark — SC 1. scp_on_test: petrification flavor.
# Loyalty collapsed: chose -3 ability (targeted kill / petrification)
SCP_FBN_4010 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4010: Vraska, Class-IV Gorgon-Spark",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=3,
        hazard=3,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel", "Gorgon"},
        text=(
            "Spark Containment 1. "
            "Designation: SCP-FBN-4010. Class: Thaumiel. Status: Contained. "
            "The intake photographs show the research team at their stations. "
            "The research team is no longer at their stations."
        ),
        rarity="rare",
    ),
    n=1,
)


def _vraska_on_test(obj, state):
    """Vraska on_test: force-audit 1 opposing dossier (petrify heuristic).

    # Loyalty collapsed: chose -3 ability (targeted removal as research hazard)
    When a test is run against Vraska, the gaze-hazard fires a redact on
    the opposing player's most exposed dossier.
    """
    opp_id = None
    for pid in state.scp_sites:
        if pid != obj.controller:
            opp_id = pid
            break
    if opp_id is None:
        return []
    game = state._game if hasattr(state, "_game") else state
    return scp.force_audit(game, opp_id, opp_id, intensity=1, source=obj.id)


SCP_FBN_4010.scp_on_test = _vraska_on_test


# 11. Kaya, Class-IV Spectral Investigator — SC 1. No bespoke hook.
SCP_FBN_4011 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4011: Kaya, Class-IV Spectral Investigator",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=2,
        hazard=1,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "Spark Containment 1. "
            "Designation: SCP-FBN-4011. Class: Thaumiel. Status: Contained. "
            "The specimen is cooperative. The specimen is also partially "
            "non-corporeal. The containment cell has been updated accordingly."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# 12. The Wanderer, Class-IV Multiversal Asset — SC 1. No bespoke hook.
SCP_FBN_4012 = _spark_containment(
    _fbn_card(
        "SCP-FBN-4012: The Wanderer, Class-IV Multiversal Asset",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=3,
        hazard=2,
        red_tape=1,
        subtypes={"Planeswalker", "Thaumiel"},
        text=(
            "Spark Containment 1. "
            "Designation: SCP-FBN-4012. Class: Thaumiel. Status: Contested. "
            "The Wanderer's file has been opened seventeen times. "
            "Each time, the specimen has already left. "
            "Current status: re-contained. Time of re-containment: pending."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# ---------------------------------------------------------------------------
# 7 Personnel
# ---------------------------------------------------------------------------

# 13. Operative O5-Chandra "Hothead"
OPERATIVE_O5_CHANDRA = _spark_containment(
    _fbn_card(
        "Operative O5-Chandra \"Hothead\"",
        CardType.SCP_PERSONNEL,
        archetype=ARCHETYPE,
        red_tape=2,
        clearance=1,
        skills={"research": 1, "contain": 2},
        subtypes={"O5", "Operative"},
        text=(
            "Spark Containment 1. "
            "O5 designation redacted. Field codename: HOTHEAD. "
            "Research rating: provisional. Containment rating: exceptional. "
            "Previous affiliation: [REDACTED PLANAR DESIGNATION]. "
            "Currently an asset. Cooperation rate: high."
        ),
        rarity="rare",
    ),
    n=1,
)


# 14. Operative O5-Jace "Mindwarden"
OPERATIVE_O5_JACE = _fbn_card(
    "Operative O5-Jace \"Mindwarden\"",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=1,
    skills={"research": 2, "contain": 1},
    subtypes={"O5", "Operative"},
    text=(
        "On assign, look at top 2 of library; archive 1. "
        "O5 designation redacted. Field codename: MINDWARDEN. "
        "Memory-read capability rated Class-III. Personnel clearance "
        "reviews are conducted twice before scheduling."
    ),
    rarity="rare",
)
OPERATIVE_O5_JACE.scp_on_assign = _jace_on_assign


# 15. Operative O5-Liliana "Bone-Reader"
# NERF cycle 2: skills contain: 2->1 (0.833 win-rate-in-play; contain skill too efficient)
OPERATIVE_O5_LILIANA = _spark_containment(
    _fbn_card(
        "Operative O5-Liliana \"Bone-Reader\"",
        CardType.SCP_PERSONNEL,
        archetype=ARCHETYPE,
        red_tape=2,
        clearance=1,
        skills={"research": 1, "contain": 1},
        subtypes={"O5", "Operative"},
        text=(
            "Spark Containment 1. "
            "O5 designation redacted. Field codename: BONE-READER. "
            "Necrotic thaumic classification: acceptable for field deployment. "
            "Personnel psych evaluation: not recommended reading."
        ),
        rarity="rare",
    ),
    n=1,
)


# 16. Operative O5-Teferi "Slow-Hand" — once per turn, exhaust opposing personnel.
# Loyalty collapsed: chose -3 ability (exhaust / temporal stall)
# NERF cycle 2: red_tape 2->3 (0.909 win-rate-in-play; exhaust loop too cheap at cost 2)
OPERATIVE_O5_TEFERI = _fbn_card(
    "Operative O5-Teferi \"Slow-Hand\"",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=3,
    clearance=1,
    skills={"research": 2, "contain": 1},
    subtypes={"O5", "Operative"},
    text=(
        "Once per turn, exhaust opposing personnel during their turn. "
        "O5 designation redacted. Field codename: SLOW-HAND. "
        "Temporal adjustment rating: Class-IV. All meetings with "
        "this operative are subject to scheduling anomaly protocols."
    ),
    rarity="mythic",
)
OPERATIVE_O5_TEFERI.scp_on_assign = _teferi_exhaust_on_assign


# 17. Researcher Tibalt, Junior Spark Auditor
RESEARCHER_TIBALT = _fbn_card(
    "Researcher Tibalt, Junior Spark Auditor",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"research": 1, "contain": 1},
    subtypes={"Researcher", "Spark-Adjacent"},
    text=(
        "Researcher, Thaumic Classification. "
        "Tibalt, [SURNAME REDACTED]. Junior auditor, Spark-Bearing Anomalies Desk. "
        "Hire date on file. Last psych review: overdue. "
        "Current assignment status: field deployment authorized (provisional)."
    ),
    rarity="uncommon",
)


# 18. Class-A Operative "Detainee"
# NERF cycle 2: skills contain: 2->1 (0.800 win-rate-in-play; high-cast contain specialist too strong)
CLASS_A_OPERATIVE_DETAINEE = _fbn_card(
    "Class-A Operative \"Detainee\"",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"contain": 1},
    subtypes={"Operative", "Class-A"},
    text=(
        "Contain specialist. "
        "Class-A operative. The file contains a name. The name is not printed "
        "on the badge. The badge is not printed with a name. "
        "Containment efficiency rated: high."
    ),
    rarity="common",
)


# 19. Detention Operative "Caged"
# NERF cycle 2: red_tape 0->1 (0.778 win-rate-in-play; free deploy was too efficient)
DETENTION_OPERATIVE_CAGED = _fbn_card(
    "Detention Operative \"Caged\"",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"contain": 1},
    subtypes={"Operative", "Detention"},
    text=(
        "Contain specialist. "
        "Designation: CAGED. Red-tape cost: minimal. "  # human-requested: was "none — the operative was already here"
        "Clearance: none on record. Containment assignment: permanent and ongoing."
    ),
    rarity="common",
)


# ---------------------------------------------------------------------------
# 5 Procedures
# ---------------------------------------------------------------------------

# 20. Planar Detention Protocol — contain target opposing anomaly. SC 2.
PLANAR_DETENTION_PROTOCOL = _spark_containment(
    _fbn_card(
        "Planar Detention Protocol",
        CardType.SCP_PROCEDURE,
        archetype=ARCHETYPE,
        red_tape=2,
        subtypes={"Protocol", "Thaumiel"},
        text=(
            "Contain target opposing Anomaly. Spark Containment 2. "
            "Authorization level: O5-Council standing order. "
            "Procedure effective date: [REDACTED]. "
            "Current status: ongoing. The Anomaly did not consent. "
            "Consent was not a variable in the protocol design."
        ),
        rarity="rare",
    ),
    n=2,
)
PLANAR_DETENTION_PROTOCOL.scp_effect = _planar_detention_protocol_effect


# 21. Spark Audit — gain clearance equal to contained count.
SPARK_AUDIT = _fbn_card(
    "Spark Audit",
    CardType.SCP_PROCEDURE,
    archetype=ARCHETYPE,
    red_tape=1,
    subtypes={"Audit", "Thaumiel"},
    text=(
        "Gain clearance equal to your contained anomaly count. "
        "Internal audit report. Auditor: [REDACTED]. "
        "Finding: each contained spark is a thaumic battery. "
        "The clearance pool reflects the charge. "
        "Recommendation: contain more."
    ),
    rarity="uncommon",
)
SPARK_AUDIT.scp_effect = _spark_audit_effect


# 22. Class-IV Spark Suppression Protocol — suppress target opp anomaly's next breach. SC 1.
SPARK_SUPPRESSION_PROTOCOL = _spark_containment(
    _fbn_card(
        "Class-IV Spark Suppression Protocol",
        CardType.SCP_PROCEDURE,
        archetype=ARCHETYPE,
        red_tape=2,
        subtypes={"Protocol", "Suppression"},
        text=(
            "Suppress target opposing Anomaly's next breach. Spark Containment 1. "
            "Suppression field: active. Breach window: closed. "
            "Duration: one incident cycle. "
            "The Anomaly is aware of the suppression field. "
            "This has been noted in the file."
        ),
        rarity="rare",
    ),
    n=1,
)
SPARK_SUPPRESSION_PROTOCOL.scp_effect = _spark_suppression_effect


# 23. Wanderer Recall Audit — return target contained Anomaly to pending queue. SC 1.
WANDERER_RECALL_AUDIT = _spark_containment(
    _fbn_card(
        "Wanderer Recall Audit",
        CardType.SCP_PROCEDURE,
        archetype=ARCHETYPE,
        red_tape=1,
        subtypes={"Audit", "Recall"},
        text=(
            "Return target contained Anomaly to your pending queue. Spark Containment 1. "
            "Recall authorization granted. "
            "The Anomaly was re-routed through Containment Processing. "
            "Again. The intake form is the same form. "
            "The Anomaly recognized the form."
        ),
        rarity="uncommon",
    ),
    n=1,
)
WANDERER_RECALL_AUDIT.scp_effect = _wanderer_recall_effect


# 24. Multiversal Detention Sweep — contain up to 2 opposing anomalies. SC 2 per.
MULTIVERSAL_DETENTION_SWEEP = _spark_containment(
    _fbn_card(
        "Multiversal Detention Sweep",
        CardType.SCP_PROCEDURE,
        archetype=ARCHETYPE,
        red_tape=3,
        subtypes={"Protocol", "Sweep", "Thaumiel"},
        text=(
            "Contain up to 2 opposing Anomalies (auto-target highest hazard each). "
            "Spark Containment 2 per contained Anomaly. "
            "Authorization: O5-Council Emergency Protocol 7-THAUMIEL. "
            "Sweep teams deployed. Anomalies contained. "
            "Incident log: attached. Incident count: two."
        ),
        rarity="rare",
    ),
    n=2,
)
MULTIVERSAL_DETENTION_SWEEP.scp_effect = _detention_sweep_effect


# ---------------------------------------------------------------------------
# 5 Facilities
# ---------------------------------------------------------------------------

# 25. Multiversal Detention Site Charlie — Spark Containment grants N+1 clearance.
MULTIVERSAL_DETENTION_SITE_CHARLIE = _fbn_card(
    "Multiversal Detention Site Charlie",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=2,
    bonus={"contain": 1},
    subtypes={"Site", "Detention"},
    text=(
        "Bonus: contain +1. Your Spark Containment N triggers grant N+1 clearance "
        "instead of N. "
        "Site designation: CHARLIE. Classification: Thaumiel-Grade Detention. "
        "Current occupancy: [REDACTED]. Maximum occupancy: classified. "
        "Visitor log: none. The facility does not receive visitors."
    ),
    rarity="rare",
)
MULTIVERSAL_DETENTION_SITE_CHARLIE.scp_on_reveal = _detention_site_charlie_boost


# 26. Spark Audit Bureau — research +1.
SPARK_AUDIT_BUREAU = _fbn_card(
    "Spark Audit Bureau",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=1,
    bonus={"research": 1},
    subtypes={"Bureau", "Audit"},
    text=(
        "Bonus: research +1. "
        "Bureau of Thaumic Spark Classification. "
        "Established under O5 Standing Order [REDACTED]. "
        "Annual audit count: classified. "
        "The Bureau has never found a spark that could not be classified. "
        "The Bureau has found several that should not have been."
    ),
    rarity="uncommon",
)


# 27. Planeswalker Containment Hub — contain +1, research +1; once per turn archive a PW.
PLANESWALKER_CONTAINMENT_HUB = _fbn_card(
    "Planeswalker Containment Hub",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=2,
    bonus={"contain": 1, "research": 1},
    subtypes={"Hub", "Thaumiel"},
    text=(
        "Bonus: contain +1, research +1. Once per turn, archive a contained "
        "Planeswalker-type for 1 archive. "
        "Hub designation: Thaumiel-Class Multiverse Processing. "
        "Intake capacity: classified. "
        "The hub does not advertise its capabilities. "
        "The capabilities do not require advertising."
    ),
    rarity="rare",
)
PLANESWALKER_CONTAINMENT_HUB.scp_on_reveal = _hub_archive_once_per_turn


# 28. Thaumic Containment Grid — contain +1.
THAUMIC_CONTAINMENT_GRID = _fbn_card(
    "Thaumic Containment Grid",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=1,
    bonus={"contain": 1},
    subtypes={"Grid", "Thaumic"},
    text=(
        "Bonus: contain +1. "
        "Grid specification: thaumic-dampening, cross-planar rated, "
        "spark-resistant. Maintenance schedule: continuous. "
        "The grid has never failed. The grid is always on."
    ),
    rarity="uncommon",
)


# 29. Temporal Stasis Cell — research +1; once per game prevent 1 opposing breach.
TEMPORAL_STASIS_CELL = _fbn_card(
    "Temporal Stasis Cell",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=2,
    bonus={"research": 1},
    subtypes={"Cell", "Temporal"},
    text=(
        "Bonus: research +1. Once per game, prevent 1 opposing anomaly breach. "
        "Cell designation: STASIS-7. "
        "Interior time dilation factor: [REDACTED]. "
        "The breach did not occur. The breach is pending. "
        "The cell holds."
    ),
    rarity="rare",
)
TEMPORAL_STASIS_CELL.scp_on_reveal = _temporal_stasis_cell_reveal


# ---------------------------------------------------------------------------
# 1 Mandate
# ---------------------------------------------------------------------------

# 30. Mandate FBN-PD: Planeswalker Detention Doctrine
# Alt-win: thaumiel (3 contained anomalies + 0 breach)
# While >=3 Planeswalker-subtype anomalies contained, draw +1 paperwork at upkeep.
# NERF cycle 2: upkeep-draw threshold raised from >=2 to >=3 (draw-engine fuelled
#   the clearance loop too cheaply; 3 contained PW is a meaningful commitment)
MANDATE_FBN_PD = _spark_containment(
    _fbn_card(
        "Mandate FBN-PD: Planeswalker Detention Doctrine",
        CardType.SCP_MANDATE,
        archetype=ARCHETYPE,
        red_tape=3,
        clearance=2,
        subtypes={"Mandate", "Thaumiel"},
        text=(
            "Mandate. Win on existing thaumiel: 3 contained anomalies + 0 breach. "
            "While >=3 Planeswalker-subtype anomalies are contained, draw +1 "
            "paperwork at upkeep. Spark Containment 2. "
            "MANDATE FBN-PD. Ratified: [REDACTED]. "
            "The multiverse bleeds. The Foundation holds the drain. "
            "This mandate authorizes the drain to hold permanently."
        ),
        rarity="mythic",
    ),
    n=2,
)
MANDATE_FBN_PD.scp_alt_win = "thaumiel"
MANDATE_FBN_PD.scp_on_reveal = _mandate_upkeep_draw


# ---------------------------------------------------------------------------
# Final list assembly
# ---------------------------------------------------------------------------

PLANESWALKER_DETENTION_CARDS: list[CardDefinition] = [
    # 12 Anomalies
    SCP_FBN_4001,
    SCP_FBN_4002,
    SCP_FBN_4003,
    SCP_FBN_4004,
    SCP_FBN_4005,
    SCP_FBN_4006,
    SCP_FBN_4007,
    SCP_FBN_4008,
    SCP_FBN_4009,
    SCP_FBN_4010,
    SCP_FBN_4011,
    SCP_FBN_4012,
    # 7 Personnel
    OPERATIVE_O5_CHANDRA,
    OPERATIVE_O5_JACE,
    OPERATIVE_O5_LILIANA,
    OPERATIVE_O5_TEFERI,
    RESEARCHER_TIBALT,
    CLASS_A_OPERATIVE_DETAINEE,
    DETENTION_OPERATIVE_CAGED,
    # 5 Procedures
    PLANAR_DETENTION_PROTOCOL,
    SPARK_AUDIT,
    SPARK_SUPPRESSION_PROTOCOL,
    WANDERER_RECALL_AUDIT,
    MULTIVERSAL_DETENTION_SWEEP,
    # 5 Facilities
    MULTIVERSAL_DETENTION_SITE_CHARLIE,
    SPARK_AUDIT_BUREAU,
    PLANESWALKER_CONTAINMENT_HUB,
    THAUMIC_CONTAINMENT_GRID,
    TEMPORAL_STASIS_CELL,
    # 1 Mandate
    MANDATE_FBN_PD,
]

_CARDS = PLANESWALKER_DETENTION_CARDS

__all__ = [
    "PLANESWALKER_DETENTION_CARDS",
    "_CARDS",
]
