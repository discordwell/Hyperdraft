"""FBN Leyline Anomaly archetype — 30-card sub-module.

Composition: 14 Anomalies / 6 Personnel / 4 Facilities / 5 Procedures / 1 Mandate.

Theme: Ambient mana hazards — wild leyline interference treated as Keter-class
environmental anomalies. Every opposing spell (procedure/facility/mandate) pumps
your active anomalies via Leyline Saturation N; paired with Annihilation Wave the
opponent is spell-locked in the late game.

MTG reference names: Marit Lage, Dark Depths, Field of the Dead, Glacial Chasm,
Maze of Ith, Mishra's Workshop, Bazaar of Baghdad, Tabernacle at Pendrell Vale,
Wasteland, Eldrazi Temple, Strip Mine, Cabal Coffers, Lake of the Dead.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardType

from .helpers import (
    _annihilation_wave,
    _brief,
    _fbn_card,
    _leyline_saturation,
    _with_fbn_metadata,
)

_ARCH = "leyline_anomaly"

# ---------------------------------------------------------------------------
# Bespoke on_reveal / on_contain / scp_effect hooks
# ---------------------------------------------------------------------------


def _marit_lage_reveal(obj, state):
    """SCP-FBN-6001 enters in a sealed, dormant state — breach clock pre-loaded."""
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "marit_lage_dormant_reveal",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _dark_depths_on_breach(obj, state):
    """SCP-FBN-6002: on breach, transforms into a Marit Lage-state hazard 5 ambient.

    The engine cannot hot-swap card_defs; we model the transformation by
    forcing scp_hazard to 5 and setting a flavour marker on the object state.
    This is a TODO stub for full mechanical transform support.
    """
    # TODO: full card-transform (hot-swap card_def) not yet supported by engine.
    # For now, spike hazard to 5 and tag the state so AI/frontend know.
    obj.state.scp_hazard = 5
    obj.state.scp_transformed = "marit_lage_state"
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "dark_depths_transformation",
            "hazard": 5,
            "note": "Marit Lage state — containment integrity: holding.",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _maze_of_ith_on_contain(obj, state):
    """SCP-FBN-6005: on contain, the opposing player's first personnel this turn
    becomes exhausted (spatial distortion impedes operational response).
    """
    events = []
    for opp_id in [pid for pid in state.players if pid != obj.controller]:
        opp_personnel = list(state.scp_personnel.get(opp_id, []))
        for pid_key in opp_personnel[:1]:  # first personnel only
            p_obj = state.objects.get(pid_key)
            if p_obj and not getattr(p_obj.state, "scp_exhausted", False):
                p_obj.state.scp_exhausted = True
                events.append(scp.Event(
                    type=scp.EventType.SCP_INCIDENT_RESOLVED,
                    payload={
                        "player": opp_id,
                        "reason": "maze_of_ith_spatial_lock",
                        "object_id": pid_key,
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
                break
    return events


def _mishra_workshop_reveal(obj, state):
    """SCP-FBN-6006: on reveal, gain 1 Brief — the Thaumic Forge primes the
    paperwork queue immediately upon containment filing.
    """
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "mishras_workshop_forge_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _tabernacle_reveal(obj, state):
    """SCP-FBN-6008: on reveal, tag the anomaly state so that opposing personnel
    upkeep costs +1 paperwork per turn while this anomaly is active.

    The actual enforcement is a TODO stub — it requires a per-upkeep procedure
    cost hook not yet wired in the engine. We set the marker here.
    """
    # TODO: per-upkeep personnel surcharge requires engine upkeep hook.
    obj.state.scp_tabernacle_active = True
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "tabernacle_upkeep_tax_armed",
            "note": "Opposing personnel upkeep +1 paperwork while active.",
        },
        source=obj.id,
        controller=obj.controller,
    )]


# ---------------------------------------------------------------------------
# Bespoke on-open-dossier hooks wired to personnel scp_on_assign
# ---------------------------------------------------------------------------


def _yeats_on_open_dossier(personnel_obj, state, action: str):
    """Dr. Aaron Yeats: when any opposing procedure resolves (which routes through
    scp_on_assign-style hooks called at assignment), gain 1 Brief.

    Actually wired as scp_on_assign — fires on any assignment involving this
    personnel. We gate on `action` context flag for 'research' to approximate
    the 'opp resolves procedure' window within available hook surface.

    TODO: wire to SCP_OPEN_DOSSIER interceptor for precise opposing-procedure trigger.
    """
    # TODO: full "when opp resolves procedure" requires SCP_OPEN_DOSSIER interceptor.
    s = scp.site(state, personnel_obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": personnel_obj.controller,
            "reason": "yeats_ley_network_brief",
            "briefing": s["briefing"],
        },
        source=personnel_obj.id,
        controller=personnel_obj.controller,
    )]


def _lin_on_assign(personnel_obj, state, action: str):
    """Researcher Lin: when a Leyline anomaly gains bonus hazard, draw 1 paperwork.

    The scp_leyline_saturation engine path directly mutates scp_suppressed without
    a hook-able event per-anomaly. We model this as a draw on every assignment
    involving Lin, as an approximation of the 'saturation fires' trigger window.

    TODO: emit per-anomaly SCP_LEYLINE_SATURATED event for precise draw trigger.
    """
    # TODO: precise trigger requires per-anomaly SCP_LEYLINE_SATURATED event.
    return scp.process_paperwork(None, personnel_obj.controller, amount=1) if False else []


def _conduit_cutter_on_assign(personnel_obj, state, action: str):
    """Operative 'Conduit-Cutter': once per turn, suppress opposing leyline.

    Modelled as a once-per-turn scp_suppressed bump of +1 on a random opposing
    Leyline anomaly when this operative is assigned.
    """
    used_key = "conduit_cutter_suppressed_this_turn"
    s = scp.site(state, personnel_obj.controller)
    if s.get(used_key):
        return []
    s[used_key] = True
    events = []
    for opp_id in [pid for pid in state.players if pid != personnel_obj.controller]:
        for anomaly_id in list(state.scp_anomalies.get(opp_id, [])):
            anomaly = state.objects.get(anomaly_id)
            if not anomaly:
                continue
            if not getattr(anomaly.card_def, "scp_leyline_saturation", 0):
                continue
            prior = int(getattr(anomaly.state, "scp_suppressed", 0) or 0)
            anomaly.state.scp_suppressed = prior + 1
            events.append(scp.Event(
                type=scp.EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": opp_id,
                    "reason": "conduit_cutter_suppress",
                    "object_id": anomaly_id,
                },
                source=personnel_obj.id,
                controller=personnel_obj.controller,
            ))
            break  # one suppression per activation
    return events


# ---------------------------------------------------------------------------
# Bespoke procedure / facility effects
# ---------------------------------------------------------------------------


def _ambient_saturation_sweep_effect(obj, state, game=None):
    """Ambient Saturation Sweep: your Leyline Saturation anomalies get a one-shot
    +2 bonus hazard boost on the next opposing procedure (modelled as an immediate
    scp_suppressed -= 2 on all active Leyline anomalies you control).
    """
    events = []
    for anomaly_id in list(state.scp_anomalies.get(obj.controller, [])):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly:
            continue
        if anomaly.state.scp_status != "active":
            continue
        if not getattr(anomaly.card_def, "scp_leyline_saturation", 0):
            continue
        prior = int(getattr(anomaly.state, "scp_suppressed", 0) or 0)
        anomaly.state.scp_suppressed = prior - 2
    events.append(scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ambient_saturation_sweep",
            "note": "All active Leyline anomalies: scp_suppressed -2 (bonus hazard +2).",
        },
        source=obj.id,
        controller=obj.controller,
    ))
    return events


def _bottleneck_spell_lane_effect(obj, state, game=None):
    """Bottleneck the Spell-Lane: redact 1 opposing dossier. Their next procedure
    costs +1 paperwork.
    """
    events = []
    for opp_id in [pid for pid in state.players if pid != obj.controller]:
        if game is not None:
            opp_hand = list(state.zones.get(f"hand_{opp_id}", type("Z", (), {"objects": []})()).objects)
            if opp_hand:
                ok, msg, ev = scp.misfile_dossier(game, obj.controller, opp_hand[0], amount=1, source=obj.id)
                events.extend(ev)
        # Tag opposing site for the +1 cost modifier (TODO: cost modifier hook).
        s_opp = scp.site(state, opp_id)
        s_opp["bottleneck_procedure_tax"] = s_opp.get("bottleneck_procedure_tax", 0) + 1
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": opp_id,
                "reason": "bottleneck_spell_lane",
                "note": "Next opposing procedure: +1 paperwork.",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


def _containment_sweep_ley_audit_effect(obj, state, game=None):
    """Containment Sweep: Ley Network Audit — each opposing personnel becomes
    exhausted at next opposing upkeep.
    """
    events = []
    for opp_id in [pid for pid in state.players if pid != obj.controller]:
        for personnel_id in list(state.scp_personnel.get(opp_id, [])):
            p_obj = state.objects.get(personnel_id)
            if p_obj:
                p_obj.state.scp_exhausted = True
                events.append(scp.Event(
                    type=scp.EventType.SCP_INCIDENT_RESOLVED,
                    payload={
                        "player": opp_id,
                        "reason": "ley_network_audit_exhaustion",
                        "object_id": personnel_id,
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
    return events


def _class_v_saturation_lockdown_effect(obj, state, game=None):
    """Class-V Saturation Lockdown: until end of turn, opposing player cannot
    resolve procedures except by paying ethics_debt 2 per.

    TODO: per-procedure ethics_debt gate requires SCP_OPEN_DOSSIER interceptor.
    Modelled now as tagging opposing site with the lockdown flag.
    """
    # TODO: real procedure gate requires SCP_OPEN_DOSSIER interceptor cost check.
    events = []
    for opp_id in [pid for pid in state.players if pid != obj.controller]:
        s_opp = scp.site(state, opp_id)
        s_opp["saturation_lockdown_this_turn"] = True
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": opp_id,
                "reason": "class_v_saturation_lockdown",
                "note": "Opposing procedures locked — ethics_debt 2 per resolution required.",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


def _ambient_hazard_audit_effect(obj, state, game=None):
    """Ambient Hazard Audit: your active Leyline anomalies +1 hazard until end
    of turn (modelled as scp_suppressed -= 1).
    """
    events = []
    for anomaly_id in list(state.scp_anomalies.get(obj.controller, [])):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly:
            continue
        if anomaly.state.scp_status != "active":
            continue
        if not getattr(anomaly.card_def, "scp_leyline_saturation", 0):
            continue
        prior = int(getattr(anomaly.state, "scp_suppressed", 0) or 0)
        anomaly.state.scp_suppressed = prior - 1
    events.append(scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ambient_hazard_audit",
            "note": "All active Leyline anomalies: +1 hazard until end of turn.",
        },
        source=obj.id,
        controller=obj.controller,
    ))
    return events


def _leyline_containment_grid_reveal(obj, state):
    """Leyline Containment Grid facility: on reveal, tag site so that Leyline
    Saturation N triggers grant N+1 hazard instead of N.

    TODO: the N+1 amplification requires per-saturation event modifier. Tagging
    the site flag for future engine plumbing.
    """
    # TODO: N+1 amplification requires engine-side Leyline Saturation modifier hook.
    s = scp.site(state, obj.controller)
    s["leyline_grid_active"] = True
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "leyline_containment_grid_online",
            "note": "Leyline Saturation N triggers grant N+1 hazard (grid amplification).",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _saturation_reactor_on_reveal(obj, state):
    """Saturation Reactor Core: on reveal, arm the opposing-procedure-clearance
    gain hook by tagging the site flag. Actual per-open-dossier +1 clearance
    is a TODO stub pending SCP_OPEN_DOSSIER interceptor support.
    """
    # TODO: per-open-dossier clearance gain requires SCP_OPEN_DOSSIER interceptor.
    s = scp.site(state, obj.controller)
    s["saturation_reactor_active"] = True
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "saturation_reactor_armed",
            "note": "When opposing procedure resolves, gain 1 clearance (hook TODO).",
        },
        source=obj.id,
        controller=obj.controller,
    )]


# ---------------------------------------------------------------------------
# 14 Anomalies
# ---------------------------------------------------------------------------

# 1. SCP-FBN-6001: Marit Lage, Dormant Class-V Ambient
# Leyline Saturation 2 + Annihilation Wave 2 — apex mythic.
_MARIT_LAGE = _leyline_saturation(
    _annihilation_wave(
        _fbn_card(
            "SCP-FBN-6001: Marit Lage, Dormant Class-V Ambient",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=6,
            curiosity=3,
            hazard=5,
            red_tape=2,
            subtypes={"Leyline", "Avatar"},
            text=(
                "Leyline Saturation 2. Annihilation Wave 2. "
                "Containment integrity: holding. The lake does not move. "
                "The lake is never the same depth twice. Field report: "
                "do not approach from the north shore."
            ),
            rarity="mythic",
            on_reveal=_marit_lage_reveal,
            art_prompt=(
                "SCP Foundation containment file art: enormous black lake surface "
                "under sodium-arc industrial lighting in a cavernous concrete "
                "containment hangar — no visible shore on three sides, "
                "Foundation hazard tape, redacted depth markers, "
                "dim chromatic shimmer at the water's edge, dread-bureaucratic tone."
            ),
        ),
        n=2,
    ),
    n=2,
)


# 2. SCP-FBN-6002: Dark Depths Containment Specimen
# Leyline Saturation 1. On breach, transforms into Marit Lage-state hazard 5.
_DARK_DEPTHS = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6002: Dark Depths Containment Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=6,
        curiosity=3,
        hazard=1,
        red_tape=2,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 1. When breached, becomes a Marit Lage-state "
            "hazard 5 ambient. Ice-core samples: inconclusive. Depth: "
            "unmeasurable. Recommended containment: do not drain."
        ),
        rarity="rare",
        art_prompt=(
            "SCP Foundation containment file art: a sealed industrial access hatch "
            "set in a concrete floor labelled 'DARK DEPTHS SPECIMEN — DEPTH UNKNOWN', "
            "faint blue-black shimmer through the frosted porthole, "
            "Foundation documentation stamps, warning tape, dread tone."
        ),
    ),
    n=1,
)
_DARK_DEPTHS.scp_on_breach = _dark_depths_on_breach


# 3. SCP-FBN-6003: Field of the Dead, Class-IV Necrotic Site
# Leyline Saturation 2.
_FIELD_OF_DEAD = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6003: Field of the Dead, Class-IV Necrotic Site",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=5,
        curiosity=3,
        hazard=3,
        red_tape=2,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 2. The field produces anomalous ambulatory "
            "constructs at a rate proportional to adjacent cleared land area. "
            "Site perimeter fence: seventh replacement."
        ),
        rarity="rare",
        art_prompt=(
            "SCP Foundation containment file art: aerial Foundation surveillance "
            "photograph of a featureless earth field enclosed by chain-link fence "
            "with hazard lighting, shadowed humanoid shapes barely visible in the "
            "grey soil, redacted field notes pinned to the photo, dread tone."
        ),
    ),
    n=2,
)


# 4. SCP-FBN-6004: Glacial Chasm, Class-III Stasis Zone
# Leyline Saturation 1.
_GLACIAL_CHASM = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6004: Glacial Chasm, Class-III Stasis Zone",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=4,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 1. The crevasse maintains a localised temporal "
            "stasis field. Nothing that enters the 30-metre boundary has been "
            "observed to decompose. Duration of current containment: 14 years."
        ),
        rarity="uncommon",
        art_prompt=(
            "SCP Foundation containment file art: a deep blue-white glacial crevasse "
            "inside a climate-controlled containment bay, Foundation measurement "
            "equipment at the edge, frost on the camera lens, hazard tape, "
            "sterile clinical lighting, dread-bureaucratic tone."
        ),
    ),
    n=1,
)


# 5. SCP-FBN-6005: Maze of Ith, Class-III Spatial Distortion
# Leyline Saturation 1. On contain, opposing personnel exhausted.
_MAZE_OF_ITH = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6005: Maze of Ith, Class-III Spatial Distortion",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=4,
        curiosity=3,
        hazard=2,
        red_tape=1,
        subtypes={"Leyline", "Spatial"},
        text=(
            "Leyline Saturation 1. On contain, exhausted opposing personnel. "
            "The hedge maze is 4 metres by 4 metres. The hedge maze has taken "
            "eleven people. Nine returned. The other two are still in transit."
        ),
        rarity="uncommon",
        on_contain=_maze_of_ith_on_contain,
        art_prompt=(
            "SCP Foundation containment file art: a geometrically impossible hedge "
            "maze inside a standard containment chamber, Foundation grid-overlay "
            "survey lines painted on the concrete floor, overhead sodium light, "
            "researcher silhouette disappearing into an impossible perspective, "
            "dread tone."
        ),
    ),
    n=1,
)


# 6. SCP-FBN-6006: Mishra's Workshop, Class-III Thaumic Forge
# Leyline Saturation 1. When opposing procedure resolves, gain 1 Brief.
# Brief is modelled as scp_on_reveal brief-grant here; the opposing-proc
# trigger is a bespoke scp_on_open_dossier stub (TODO: interceptor).
_MISHRAS_WORKSHOP = _leyline_saturation(
    _brief(
        _fbn_card(
            "SCP-FBN-6006: Mishra's Workshop, Class-III Thaumic Forge",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=4,
            curiosity=3,
            hazard=2,
            red_tape=1,
            subtypes={"Leyline", "Thaumic", "Artefact"},
            text=(
                "Leyline Saturation 1. Brief 1 on reveal. When an opposing "
                "procedure resolves, gain 1 Brief. The forge requires no operator. "
                "The forge has never been off. The output is not recorded."
            ),
            rarity="rare",
            on_reveal=_mishra_workshop_reveal,
            art_prompt=(
                "SCP Foundation containment file art: an industrial blast furnace "
                "inside a containment hangar casting blue-white thaumic light, "
                "no visible workers, Foundation instrument panels glowing amber, "
                "slag that pulses like a heartbeat, dread-bureaucratic tone."
            ),
        ),
        n=1,
    ),
    n=1,
)
# TODO: bespoke interceptor — when opposing SCP_OPEN_DOSSIER fires (procedure type),
# gain 1 Brief for the controller of this anomaly.
_MISHRAS_WORKSHOP.scp_on_open_dossier = None  # stub; see TODO above


# 7. SCP-FBN-6007: Bazaar of Baghdad Specimen
# Leyline Saturation 1.
_BAZAAR_BAGHDAD = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6007: Bazaar of Baghdad Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Leyline", "Spatial"},
        text=(
            "Leyline Saturation 1. The stall accepts every currency and none of "
            "them. The goods are always worth exactly what the buyer cannot afford "
            "to lose. No vendor has been identified. Surveillance coverage: 0%."
        ),
        rarity="uncommon",
        art_prompt=(
            "SCP Foundation containment file art: a sealed underground chamber "
            "containing a market stall covered in heterogeneous goods, Foundation "
            "biohazard tape around the perimeter, items that cast no shadows, "
            "overhead sodium arc light, dread tone."
        ),
    ),
    n=1,
)


# 8. SCP-FBN-6008: Tabernacle at Pendrell Vale
# Leyline Saturation 1. Opposing personnel cost +1 paperwork at upkeep (TODO stub).
_TABERNACLE = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6008: Tabernacle at Pendrell Vale",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=3,
        red_tape=1,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 1. Opposing personnel cost +1 paperwork at upkeep. "
            "The structure identifies itself as a place of rest. Personnel assigned "
            "to it file their own termination paperwork. Classification: ongoing."
        ),
        rarity="rare",
        on_reveal=_tabernacle_reveal,
        art_prompt=(
            "SCP Foundation containment file art: a single stone building on "
            "a Foundation-cordoned woodland clearing, redacted survey markers, "
            "Foundation researchers in hazmat suits at a distance, sodium flood "
            "lights illuminating the structure, dread bureaucratic tone."
        ),
    ),
    n=1,
)
# TODO: per-upkeep opposing personnel paperwork tax requires upkeep hook.


# 9. SCP-FBN-6009: Wasteland, Class-III Disruption
# Leyline Saturation 1.
_WASTELAND = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6009: Wasteland, Class-III Disruption",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=2,
        curiosity=2,
        hazard=2,
        red_tape=0,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 1. The containment perimeter is a circle of "
            "zero plant life 3.2 km in diameter. Geological surveys find no "
            "cause. Nothing grows back. Nothing has ever grown back."
        ),
        rarity="common",
        art_prompt=(
            "SCP Foundation containment file art: aerial photograph of a perfect "
            "circle of grey dead earth surrounded by green farmland, Foundation "
            "hazard markers at cardinal points, redacted report overlay, dread tone."
        ),
    ),
    n=1,
)


# 10. SCP-FBN-6010: Eldrazi Temple, Cross-Class Vector
# Leyline Saturation 1 + Annihilation Wave 1.
_ELDRAZI_TEMPLE = _leyline_saturation(
    _annihilation_wave(
        _fbn_card(
            "SCP-FBN-6010: Eldrazi Temple, Cross-Class Vector",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=3,
            curiosity=2,
            hazard=2,
            red_tape=1,
            subtypes={"Leyline", "Thaumic"},
            text=(
                "Leyline Saturation 1. Annihilation Wave 1. The temple serves no "
                "god that has been named. The temple is nonetheless fully occupied. "
                "Observation note: worshippers do not appear to have arrived."
            ),
            rarity="rare",
            art_prompt=(
                "SCP Foundation containment file art: vast stone temple interior "
                "under Foundation containment scaffolding, non-Euclidean archways "
                "visible through the containment structure, dim Eldrazi geometry, "
                "redacted Foundation survey, dread-bureaucratic tone."
            ),
        ),
        n=1,
    ),
    n=1,
)


# 11. SCP-FBN-6011: Strip Mine Specimen
# Leyline Saturation 1.
_STRIP_MINE = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6011: Strip Mine Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=2,
        curiosity=1,
        hazard=2,
        red_tape=0,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 1. The pit is 400 metres deep. The geological "
            "strata are inverted. Samples from depth 400m predate the formation "
            "of the surrounding crust by 1.2 billion years."
        ),
        rarity="common",
        art_prompt=(
            "SCP Foundation containment file art: open-pit mine cordoned by "
            "Foundation barriers at night, Foundation drill equipment at impossible "
            "depths, strata labels with redacted dates, overhead hazard lighting, "
            "dread tone."
        ),
    ),
    n=1,
)


# 12. SCP-FBN-6012: Cabal Coffers, Class-IV Necrotic Geometry
# Leyline Saturation 1.
_CABAL_COFFERS = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6012: Cabal Coffers, Class-IV Necrotic Geometry",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Leyline", "Thaumic", "Geographic"},
        text=(
            "Leyline Saturation 1. The vault contains nothing. The vault is full. "
            "Containment note: do not attempt inventory. Previous inventory "
            "attempts: 4. Investigators recovered: 0."
        ),
        rarity="uncommon",
        art_prompt=(
            "SCP Foundation containment file art: a sealed bank vault door "
            "in a brutalist Foundation containment basement, pale necrotic light "
            "seeping from the vault seam, four redacted incident logs pinned to "
            "the wall, dread bureaucratic tone."
        ),
    ),
    n=1,
)


# 13. SCP-FBN-6013: Lake of the Dead
# Leyline Saturation 1.
_LAKE_OF_DEAD = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-6013: Lake of the Dead",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Leyline", "Geographic"},
        text=(
            "Leyline Saturation 1. Water temperature: -47°C. Sample analysis: "
            "inconclusive. Fauna survey: inconclusive. Dive team status: "
            "pending return. Days elapsed: 612."
        ),
        rarity="uncommon",
        art_prompt=(
            "SCP Foundation containment file art: a black underground lake in a "
            "containment cavern, Foundation inflatable perimeter barriers, "
            "diving equipment abandoned on the stone shore, sodium emergency "
            "lighting, cold mist, dread tone."
        ),
    ),
    n=1,
)


# 14. SCP-FBN-6014: Class-IV Ley Network Knot
# Leyline Saturation 3 + Annihilation Wave 1 — heavy rare.
_LEY_NETWORK_KNOT = _leyline_saturation(
    _annihilation_wave(
        _fbn_card(
            "SCP-FBN-6014: Class-IV Ley Network Knot",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=5,
            curiosity=3,
            hazard=4,
            red_tape=2,
            subtypes={"Leyline", "Thaumic"},
            text=(
                "Leyline Saturation 3. Annihilation Wave 1. A nexus of "
                "intersecting ley-line interference mapped across eleven "
                "continents and two ocean floors. The knot appears stationary. "
                "The ley lines appear stationary. The damage is not stationary."
            ),
            rarity="rare",
            art_prompt=(
                "SCP Foundation containment file art: a world-map overlaid with "
                "glowing ley-line network intersecting at a pulsing nexus, "
                "Foundation satellite imaging equipment, redacted geographic data, "
                "cosmic-horror chromatic aberration at the nexus point, dread tone."
            ),
        ),
        n=1,
    ),
    n=3,
)


# ---------------------------------------------------------------------------
# 6 Personnel
# ---------------------------------------------------------------------------

# 15. Researcher Cartographer "Map"
_CARTOGRAPHER_MAP = _fbn_card(
    "Researcher Cartographer \"Map\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1,
    skills={"contain": 1, "research": 1},
    subtypes={"Researcher", "Leyline Cartographer"},
    text=(
        "Leyline cartographer. Baseline contain 1, research 1. She calls herself "
        "Map because the other cartographers have names for everything and she "
        "has maps for everything, and these are not the same thing."
    ),
    rarity="common",
    art_prompt=(
        "SCP Foundation personnel file photo: a young Foundation researcher "
        "holding a rolled ley-line map over a lightbox in a sparse concrete "
        "office, redacted name tag, Foundation ID lanyard, dread-bureaucratic "
        "tone, no supernatural elements visible."
    ),
)


# 16. Dr. Aaron Yeats, Ley Network Specialist
# When opp resolves procedure, gain 1 Brief — bespoke scp_on_assign hook.
_DR_YEATS = _fbn_card(
    "Dr. Aaron Yeats, Ley Network Specialist",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=2,
    clearance=1,
    skills={"contain": 2, "research": 1},
    subtypes={"Doctor", "Ley Network Specialist"},
    text=(
        "Contain 2, Research 1. When an opposing procedure resolves, gain 1 Brief. "
        "Yeats has written the foundational text on leyline cartography three times. "
        "Each edition is longer. Each edition contradicts the last."
    ),
    rarity="rare",
    art_prompt=(
        "SCP Foundation personnel file photo: a middle-aged Foundation specialist "
        "with thick-rimmed glasses surrounded by ley-line survey printouts in a "
        "cluttered office, redacted name badge, stacks of bound reports, dread tone."
    ),
)
_DR_YEATS.scp_on_assign = _yeats_on_open_dossier
# TODO: bespoke interceptor — precisely when opposing SCP_OPEN_DOSSIER (procedure),
# not on any assignment; update when SCP_OPEN_DOSSIER interceptor surface is wired.


# 17. Operative "Bottleneck"
_OPERATIVE_BOTTLENECK = _fbn_card(
    "Operative \"Bottleneck\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1,
    skills={"contain": 2},
    subtypes={"Operative"},
    text=(
        "Contain 2. Bottleneck is not her operational name. Bottleneck is what "
        "the ley lines do around her. She has learned to stand in them on purpose."
    ),
    rarity="uncommon",
    art_prompt=(
        "SCP Foundation personnel file photo: a Foundation operative in tactical "
        "gear at the centre of faint shimmering ley-line interference visible as "
        "heat distortion, concrete corridor, amber emergency lighting, dread tone."
    ),
)


# 18. Researcher Lin, Ambient Hazard Surveyor
# When active Leyline anomaly gains bonus hazard, draw 1 paperwork — bespoke TODO.
_RESEARCHER_LIN = _fbn_card(
    "Researcher Lin, Ambient Hazard Surveyor",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1,
    skills={"research": 2},
    subtypes={"Researcher", "Leyline Cartographer"},
    text=(
        "Research 2. When your active Leyline anomaly gets bonus hazard, draw "
        "1 paperwork. Lin measures the hazard the way weather stations measure "
        "pressure — passively, continuously, with a detachment she has "
        "spent three years cultivating."
    ),
    rarity="uncommon",
    art_prompt=(
        "SCP Foundation personnel file photo: a Foundation researcher in a "
        "monitoring room walled with hazard-level readouts, stylus in hand, "
        "calm expression, amber status lights, redacted name badge, dread tone."
    ),
)
_RESEARCHER_LIN.scp_on_assign = _lin_on_assign
# TODO: bespoke SCP_LEYLINE_SATURATED event + interceptor for precise trigger.


# 19. Class-A Operative "Survey"
_OPERATIVE_SURVEY = _fbn_card(
    "Class-A Operative \"Survey\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=0,
    skills={"research": 1},
    subtypes={"Operative"},
    text=(
        "Research 1. Survey does surveys. Survey has always done surveys. "
        "The surveys are filed. The surveys are correct. The surveys disagree "
        "with each other."
    ),
    rarity="common",
    art_prompt=(
        "SCP Foundation personnel file photo: a junior Foundation operative "
        "with a clipboard on a grey concrete site exterior, measuring tape "
        "and hazard markers visible, redacted name, no supernatural elements."
    ),
)


# 20. Operative "Conduit-Cutter"
# Once per turn, suppress opposing leyline — bespoke scp_on_assign hook.
_CONDUIT_CUTTER = _fbn_card(
    "Operative \"Conduit-Cutter\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=2,
    clearance=1,
    skills={"contain": 2, "research": 1},
    subtypes={"Operative"},
    text=(
        "Contain 2, Research 1. Once per turn, suppress opposing leyline. "
        "The conduit-cutter protocol has a 78% operational success rate. "
        "The remaining 22% is what the clearance is for."
    ),
    rarity="rare",
    art_prompt=(
        "SCP Foundation personnel file photo: a senior Foundation operative "
        "in reinforced containment gear holding a pulsing ley-line disruptor "
        "device, concrete site interior, dramatic Foundation emergency lighting, "
        "dread-bureaucratic tone."
    ),
)
_CONDUIT_CUTTER.scp_on_assign = _conduit_cutter_on_assign


# ---------------------------------------------------------------------------
# 5 Procedures
# ---------------------------------------------------------------------------

# 21. Ambient Saturation Sweep
_AMBIENT_SATURATION_SWEEP = _fbn_card(
    "Ambient Saturation Sweep",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Procedure"},
    text=(
        "Your Leyline Saturation anomalies trigger Leyline Saturation 2 "
        "on the next opposing procedure (one-shot boost): scp_suppressed -2 "
        "on all active Leyline anomalies immediately. "
        "Protocol designation: sweep-class ambient recalibration. Duration: "
        "until opposition acts."
    ),
    rarity="uncommon",
    effect=_ambient_saturation_sweep_effect,
    art_prompt=(
        "SCP Foundation procedure document art: a circular ley-line interference "
        "diagram printed on official Foundation letterhead, concentric hazard rings "
        "in red ink, a wax-sealed O5 approval stamp, sodium light overhead, "
        "dread-bureaucratic tone."
    ),
)


# 22. Bottleneck the Spell-Lane
_BOTTLENECK_SPELL_LANE = _fbn_card(
    "Bottleneck the Spell-Lane",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Procedure"},
    text=(
        "Redact 1 opposing dossier. Their next procedure costs +1 paperwork. "
        "Interdiction memo issued under O5 authority. Non-compliance is "
        "treated as a Class-B information hazard event."
    ),
    rarity="uncommon",
    effect=_bottleneck_spell_lane_effect,
    art_prompt=(
        "SCP Foundation procedure document art: a Foundation interdiction memo "
        "stamped BOTTLENECK in red across the top, redacted procedure titles on "
        "a list below, a single red line drawn through one dossier entry, "
        "concrete desk under harsh light, dread tone."
    ),
)


# 23. Containment Sweep: Ley Network Audit
_CONTAINMENT_SWEEP_LEY_AUDIT = _fbn_card(
    "Containment Sweep: Ley Network Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Procedure"},
    text=(
        "Each opposing personnel becomes exhausted at next opposing upkeep. "
        "Ley Network Audit Directive FBN-6A. All non-essential personnel are "
        "to stand down pending full leyline recalibration. Duration: indefinite."
    ),
    rarity="rare",
    effect=_containment_sweep_ley_audit_effect,
    art_prompt=(
        "SCP Foundation procedure document art: an official exhaustion order "
        "posted on a site bulletin board, Foundation ID cards of twelve personnel "
        "pinned beneath it, red STAND DOWN stamps, fluorescent office lighting, "
        "dread bureaucratic tone."
    ),
)


# 24. Class-V Saturation Lockdown
_CLASS_V_SATURATION_LOCKDOWN = _fbn_card(
    "Class-V Saturation Lockdown",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=3,
    subtypes={"Procedure"},
    text=(
        "Until end of turn, opposing player cannot resolve procedures except "
        "by paying ethics_debt 2 per. O5-Council emergency directive. "
        "The ley lines are considered hostile infrastructure. All opposing "
        "protocol activity is suspended pending clearance review."
    ),
    rarity="mythic",
    effect=_class_v_saturation_lockdown_effect,
    art_prompt=(
        "SCP Foundation procedure document art: an emergency O5 directive on "
        "heavy cream paper with five wax seals, SATURATION LOCKDOWN in red "
        "block capitals at the top, ethics_debt surcharge tables printed in "
        "fine legal text, dread bureaucratic tone."
    ),
)


# 25. Ambient Hazard Audit
_AMBIENT_HAZARD_AUDIT = _fbn_card(
    "Ambient Hazard Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Procedure"},
    text=(
        "Your active Leyline anomalies +1 hazard until end of turn. "
        "Hazard audit classification: permissive. Containment rating temporarily "
        "revised upward. Do not mention this in the public-facing report."
    ),
    rarity="common",
    effect=_ambient_hazard_audit_effect,
    art_prompt=(
        "SCP Foundation procedure document art: a one-page hazard audit form "
        "with all containment ratings circled and marked +1 in red ink, "
        "AMBIENT HAZARD AUDIT stamp, concrete desk, dim office lighting, "
        "dread tone."
    ),
)


# ---------------------------------------------------------------------------
# 4 Facilities
# ---------------------------------------------------------------------------

# 26. Leyline Containment Grid
# Bonus: contain +1, research +1. Leyline Saturation N triggers grant N+1 (TODO stub).
_LEYLINE_CONTAINMENT_GRID = _fbn_card(
    "Leyline Containment Grid",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Facility"},
    bonus={"contain": 1, "research": 1},
    text=(
        "Bonus: contain +1, research +1. Your Leyline Saturation N triggers "
        "grant N+1 hazard instead. The grid was built to contain the leylines. "
        "The grid has made the leylines stronger. Both facts are in the same "
        "report. Neither fact is in the summary."
    ),
    rarity="rare",
    on_reveal=_leyline_containment_grid_reveal,
    art_prompt=(
        "SCP Foundation facility blueprint art: technical schematic of a "
        "massive electromagnetic grid structure set into a containment site "
        "floor plan, ley-line interference readouts at panel stations, "
        "Foundation engineering stamps, dread-bureaucratic tone."
    ),
)
# TODO: N+1 amplifier requires engine-side Leyline Saturation modifier hook.


# 27. Ley-Survey Bureau
# Bonus: research +1.
_LEY_SURVEY_BUREAU = _fbn_card(
    "Ley-Survey Bureau",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Facility"},
    bonus={"research": 1},
    text=(
        "Bonus: research +1. Room 7-C is listed as a storage room on every "
        "floor plan since 1973. Room 7-C has been the Survey Bureau since 1973. "
        "The discrepancy has been noted."
    ),
    rarity="uncommon",
    art_prompt=(
        "SCP Foundation facility art: a compact survey bureau crammed with "
        "ley-line printouts and wall-mounted maps, Foundation researchers at "
        "terminals, amber overhead lighting, redacted room designation placard, "
        "dread bureaucratic tone."
    ),
)


# 28. Ambient Containment Site Delta-7
# Bonus: contain +1.
_AMBIENT_CONTAINMENT_SITE_DELTA7 = _fbn_card(
    "Ambient Containment Site Delta-7",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Facility", "Site"},
    bonus={"contain": 1},
    text=(
        "Bonus: contain +1. Site Delta-7 is designed specifically for ambient "
        "thaumic hazards with no fixed physical address. Containment philosophy: "
        "if you cannot contain the source, contain the interference pattern."
    ),
    rarity="uncommon",
    art_prompt=(
        "SCP Foundation facility art: an exterior shot of a featureless "
        "Foundation containment building in a cleared field at night, "
        "Foundation signage SITE DELTA-7, sodium perimeter lights, "
        "faint ley-line shimmer in the sky above, dread tone."
    ),
)


# 29. Saturation Reactor Core
# Bonus: research +1. When opposing procedure resolves, gain 1 clearance (TODO stub).
_SATURATION_REACTOR_CORE = _fbn_card(
    "Saturation Reactor Core",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Facility"},
    bonus={"research": 1},
    text=(
        "Bonus: research +1. When an opposing procedure resolves, gain 1 clearance. "
        "The reactor does not generate power. The reactor generates clearance. "
        "Engineering division: declined to elaborate."
    ),
    rarity="rare",
    on_reveal=_saturation_reactor_on_reveal,
    art_prompt=(
        "SCP Foundation facility art: interior of a reactor chamber with "
        "ley-line interference visible as shimmering arcs between containment "
        "rods, Foundation instrument panels, hazard suits on hooks at the door, "
        "sodium arc lighting, dread tone."
    ),
)
# TODO: per-SCP_OPEN_DOSSIER (opposing procedure) clearance gain interceptor.


# ---------------------------------------------------------------------------
# 1 Mandate
# ---------------------------------------------------------------------------

# 30. Mandate FBN-LS: Ley Lockdown Doctrine
_MANDATE_LEY_LOCKDOWN = _fbn_card(
    "Mandate FBN-LS: Ley Lockdown Doctrine",
    CardType.SCP_MANDATE,
    archetype=_ARCH,
    red_tape=3,
    clearance=2,
    subtypes={"Mandate"},
    text=(
        "Mandate. Win on existing 'public_panic' condition: 4 archives + "
        "opposing secrecy ≤ 6. Your Leyline anomalies' hazard caps raised by +1. "
        "O5-Council Mandate FBN-LS. The ley lockdown doctrine ratifies ambient "
        "saturation as a legitimate containment accelerant. Breach is policy."
    ),
    rarity="mythic",
    art_prompt=(
        "SCP Foundation mandate document art: a formal O5-Council mandate printed "
        "on heavy stock with the Foundation seal, LEY LOCKDOWN DOCTRINE in "
        "capitals, five council member signatures (all redacted), a wax seal "
        "cracking under ley-line interference visible in the paper itself, "
        "dread-bureaucratic cosmic tone."
    ),
)
_MANDATE_LEY_LOCKDOWN.scp_alt_win = "public_panic"
_MANDATE_LEY_LOCKDOWN.scp_alt_win_conditions = {
    "archives_min": 4,
    "opposing_secrecy_max": 6,
}
# Hazard cap +1 for Leyline anomalies is a TODO stub pending engine cap-modifier hook.
# TODO: engine hazard-cap modifier for cards tagged scp_leyline_saturation.


# ---------------------------------------------------------------------------
# Aggregate + module export alias
# ---------------------------------------------------------------------------

LEYLINE_ANOMALY_CARDS: list = [
    # 14 Anomalies
    _MARIT_LAGE,
    _DARK_DEPTHS,
    _FIELD_OF_DEAD,
    _GLACIAL_CHASM,
    _MAZE_OF_ITH,
    _MISHRAS_WORKSHOP,
    _BAZAAR_BAGHDAD,
    _TABERNACLE,
    _WASTELAND,
    _ELDRAZI_TEMPLE,
    _STRIP_MINE,
    _CABAL_COFFERS,
    _LAKE_OF_DEAD,
    _LEY_NETWORK_KNOT,
    # 6 Personnel
    _CARTOGRAPHER_MAP,
    _DR_YEATS,
    _OPERATIVE_BOTTLENECK,
    _RESEARCHER_LIN,
    _OPERATIVE_SURVEY,
    _CONDUIT_CUTTER,
    # 5 Procedures
    _AMBIENT_SATURATION_SWEEP,
    _BOTTLENECK_SPELL_LANE,
    _CONTAINMENT_SWEEP_LEY_AUDIT,
    _CLASS_V_SATURATION_LOCKDOWN,
    _AMBIENT_HAZARD_AUDIT,
    # 4 Facilities
    _LEYLINE_CONTAINMENT_GRID,
    _LEY_SURVEY_BUREAU,
    _AMBIENT_CONTAINMENT_SITE_DELTA7,
    _SATURATION_REACTOR_CORE,
    # 1 Mandate
    _MANDATE_LEY_LOCKDOWN,
]

_CARDS = LEYLINE_ANOMALY_CARDS
