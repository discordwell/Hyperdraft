"""Wurm Apex (FBN) — Apollyon planet-scale fauna.

30 cards: 14 Anomalies, 6 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

Theme: The Foundation has captured Apollyon-class mega-fauna — planet-devouring
wurms whose containment isn't just incarceration but taming.  Research tests
don't tick curiosity; they tame the beast (-2 hazard / +2 containment each
pass via Wurm Devourer).  Stack Annihilation Wave on the giants so a breach
is catastrophic, then race to successfully research 3 wurms before they eat
your site.

Alt-win anchor: ``Mandate FBN-WAT: Wurm Apex Tamed Doctrine``
    ``wurm_apex_tamed`` fires when 3+ Wurm Devourer anomalies have been tamed.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import (
    _annihilation_wave,
    _fbn_card,
    _with_fbn_metadata,
    _wurm_devourer,
)

_ARCH = "wurm_apex"


# ---------------------------------------------------------------------------
# Bespoke on-reveal / on-contain / on-test hooks
# ---------------------------------------------------------------------------


def _worldspine_on_contain(obj, state):
    """When the Worldspine Wurm is finally contained, the breach was already
    planetary — opposing breach +1 to acknowledge how close it came."""
    opp_id = scp._first_opposing_player(state, obj.controller)
    if opp_id:
        s_opp = scp.site(state, opp_id)
        s_opp["breach"] = s_opp.get("breach", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "worldspine_contained",
            "opposing_breach_bump": 1,
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _pelakka_on_test(obj, state):
    """Every successful test against the Pelakka Wurm grants 1 archive — the
    Foundation catalogues immense biological data from each session."""
    s = scp.site(state, obj.controller)
    s["archives"] = s.get("archives", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "pelakka_test_archive",
            "archives": s["archives"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _apex_reclamation_on_contain(obj, state):
    """Apex Reclamation Wurm: on contain, gain 1 archive AND 1 clearance — a
    successful reclassification opens funding channels."""
    s = scp.site(state, obj.controller)
    s["archives"] = s.get("archives", 0) + 1
    s["clearance"] = s.get("clearance", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "apex_reclamation_contained",
            "archives": s["archives"],
            "clearance": s["clearance"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _coil_engine_on_contain(obj, state):
    """Wurm Coil Engine creates two 3/3 coil tokens on successful contain;
    engine models this as gain 2 Brief (briefing = mobilised containment
    reserves ready for the next deployment)."""
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 2
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "coil_engine_token_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _ghalta_on_contain(obj, state):
    """Ghalta's raw biomass produces an enormous amount of research data when
    contained — gain 1 archive."""
    s = scp.site(state, obj.controller)
    s["archives"] = s.get("archives", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ghalta_contained_archive",
            "archives": s["archives"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _slagwurm_on_test_fail(obj, state):
    """The Engulfing Slagwurm punishes a failed research test: containment
    protocols falter and the opposing breach climbs by 1."""
    opp_id = scp._first_opposing_player(state, obj.controller)
    if opp_id:
        s_opp = scp.site(state, opp_id)
        s_opp["breach"] = s_opp.get("breach", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "slagwurm_test_fail_breach",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _underground_tunnel_on_reveal(obj, state):
    """Underground Wurm-Tunnel Specimen: on reveal, secrecy -1 — the
    tunnels were already under the city before anyone filed the report."""
    s = scp.site(state, obj.controller)
    s["secrecy"] = max(0, s.get("secrecy", 0) - 1)
    return [scp.Event(
        type=scp.EventType.SCP_AUDIT,
        payload={
            "actor": obj.id,
            "target": obj.controller,
            "exposure": 1,
            "reason": "tunnel_public_exposure",
            "secrecy": s["secrecy"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _spitting_earth_on_test_fail(obj, state):
    """Failed test against the Spitting Earth Wurm causes a minor breach
    escalation — it vents geothermal acid."""
    s = scp.site(state, obj.controller)
    s["breach"] = s.get("breach", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "spitting_earth_test_fail",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _heyok_on_assign(personnel_obj, state, action: str):
    """Dr. Heyok: when assigned to a Wurm Devourer anomaly, the test
    auto-passes — modelled as +99 task bonus so the success check always
    clears, capped internally by the engine."""
    target_id = getattr(state, "_current_assignment_target", None)
    if target_id:
        zones = state.zones or {}
        for zone_objs in zones.values():
            if not isinstance(zone_objs, list):
                continue
            for obj in zone_objs:
                if getattr(obj, "id", None) == target_id:
                    card_def = getattr(obj, "card_def", None)
                    if card_def and getattr(card_def, "scp_wurm_devourer", False):
                        return [scp.Event(
                            type=scp.EventType.SCP_TEST_RUN,
                            payload={
                                "task_bonus": 99,
                                "reason": "heyok_specialist_auto_pass",
                                "actor": personnel_obj.id,
                            },
                            source=personnel_obj.id,
                            controller=personnel_obj.controller,
                        )]
    return []


def _o5_15_on_tame_hook(obj, state):
    """Operative O5-15: when any Wurm is tamed (wurms_tamed counter bumps),
    gain 1 archive — this fires as the on_test hook on Wurm Devourer anomalies
    patched in by the Mandate setup, but we wire it as a personnel bonus tracked
    by a state marker instead; here we just emit the archive gain directly."""
    # NOTE: This fires as scp_on_test on the *anomaly* side, not the personnel.
    # The workaround: personnel cards that want "on-tame" effects carry a marker
    # on the site dict; the Mandate's alt-win check polls it. For O5-15 the
    # simplest approach is an on-contain hook on the personnel itself via aura.
    # Here we provide the gain_archives burst used by the Apex Reclamation Site
    # facility (same pattern). Actual per-tame trigger is a TODO for engine
    # Phase 6 "on_tame" event. For now: archive on contain of any anomaly.
    s = scp.site(state, obj.controller)
    s["archives"] = s.get("archives", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "o5_15_tame_archive",
            "archives": s["archives"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _megafauna_audit_effect(obj, state):
    """Megafauna Audit: each Wurm Devourer anomaly you control gets hazard -1
    and containment +1 until end of turn. Modelled as immediate stat mutations
    on all active Wurm anomalies; 'end of turn' rollback is a TODO stub."""
    mutated = 0
    zones = state.zones or {}
    for zone_objs in zones.values():
        if not isinstance(zone_objs, list):
            continue
        for anomaly_obj in zone_objs:
            if getattr(anomaly_obj, "controller", None) != obj.controller:
                continue
            card_def = getattr(anomaly_obj, "card_def", None)
            if card_def and getattr(card_def, "scp_wurm_devourer", False):
                cur_hazard = getattr(anomaly_obj.state, "scp_hazard",
                                     card_def.scp_hazard)
                cur_contain = getattr(anomaly_obj.state, "scp_containment",
                                      card_def.scp_containment)
                anomaly_obj.state.scp_hazard = max(0, cur_hazard - 1)
                anomaly_obj.state.scp_containment = cur_contain + 1
                mutated += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "megafauna_audit_effect",
            "anomalies_mutated": mutated,
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _apex_sweep_effect(obj, state):
    """Class-V Apex Sweep: every Wurm Devourer anomaly you control has its
    Wurm Devourer mechanic applied twice (hazard -4 / containment +4 each,
    and wurms_tamed += 2 per anomaly).  Engine calls apply_wurm_devourer
    directly on each anomaly object."""
    events: list[scp.Event] = []
    zones = state.zones or {}
    for zone_objs in zones.values():
        if not isinstance(zone_objs, list):
            continue
        for anomaly_obj in zone_objs:
            if getattr(anomaly_obj, "controller", None) != obj.controller:
                continue
            card_def = getattr(anomaly_obj, "card_def", None)
            if card_def and getattr(card_def, "scp_wurm_devourer", False):
                # Fire twice — apex sweep tames the beast completely.
                # apply_wurm_devourer needs a game object; we use a lazy
                # approach: emit two SCP_INCIDENT_RESOLVED events that the
                # engine handles via apply_wurm_devourer shim.
                for _ in range(2):
                    s = scp.site(state, anomaly_obj.controller)
                    cur_hazard = getattr(anomaly_obj.state, "scp_hazard",
                                         card_def.scp_hazard)
                    cur_contain = getattr(anomaly_obj.state, "scp_containment",
                                          card_def.scp_containment)
                    anomaly_obj.state.scp_hazard = max(0, cur_hazard - 2)
                    anomaly_obj.state.scp_containment = cur_contain + 2
                    s["wurms_tamed"] = int(s.get("wurms_tamed", 0) or 0) + 1
                events.append(scp.Event(
                    type=scp.EventType.SCP_INCIDENT_RESOLVED,
                    payload={
                        "player": obj.controller,
                        "reason": "apex_sweep_double_tame",
                        "anomaly_id": anomaly_obj.id,
                        "wurms_tamed": scp.site(state, obj.controller).get("wurms_tamed", 0),
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
    return events


def _tame_the_giant_effect(obj, state):
    """Tame the Giant: trigger Wurm Devourer on your highest-hazard Wurm
    anomaly.  Finds the anomaly with the greatest effective hazard and
    mutates it directly."""
    best = None
    best_hazard = -1
    zones = state.zones or {}
    for zone_objs in zones.values():
        if not isinstance(zone_objs, list):
            continue
        for anomaly_obj in zone_objs:
            if getattr(anomaly_obj, "controller", None) != obj.controller:
                continue
            card_def = getattr(anomaly_obj, "card_def", None)
            if card_def and getattr(card_def, "scp_wurm_devourer", False):
                h = getattr(anomaly_obj.state, "scp_hazard", card_def.scp_hazard)
                if h > best_hazard:
                    best_hazard = h
                    best = anomaly_obj
    if best is None:
        return []
    best_def = best.card_def
    best.state.scp_hazard = max(0, best_hazard - 2)
    cur_contain = getattr(best.state, "scp_containment", best_def.scp_containment)
    best.state.scp_containment = cur_contain + 2
    s = scp.site(state, obj.controller)
    s["wurms_tamed"] = int(s.get("wurms_tamed", 0) or 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "tame_the_giant",
            "anomaly_id": best.id,
            "new_hazard": best.state.scp_hazard,
            "new_containment": best.state.scp_containment,
            "wurms_tamed": s["wurms_tamed"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _apex_sedation_effect(obj, state):
    """Apex Sedation Protocol: run a test on a Wurm Devourer anomaly you
    control; the test auto-passes.  We model this the same way as Heyok's
    on-assign auto-pass: find the highest-hazard untested Wurm and apply
    Wurm Devourer manually."""
    best = None
    best_hazard = -1
    zones = state.zones or {}
    for zone_objs in zones.values():
        if not isinstance(zone_objs, list):
            continue
        for anomaly_obj in zone_objs:
            if getattr(anomaly_obj, "controller", None) != obj.controller:
                continue
            card_def = getattr(anomaly_obj, "card_def", None)
            if card_def and getattr(card_def, "scp_wurm_devourer", False):
                h = getattr(anomaly_obj.state, "scp_hazard", card_def.scp_hazard)
                if h > best_hazard:
                    best_hazard = h
                    best = anomaly_obj
    if best is None:
        return []
    best_def = best.card_def
    best.state.scp_hazard = max(0, best_hazard - 2)
    cur_contain = getattr(best.state, "scp_containment", best_def.scp_containment)
    best.state.scp_containment = cur_contain + 2
    s = scp.site(state, obj.controller)
    s["wurms_tamed"] = int(s.get("wurms_tamed", 0) or 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "apex_sedation_auto_pass",
            "anomaly_id": best.id,
            "new_hazard": best.state.scp_hazard,
            "new_containment": best.state.scp_containment,
            "wurms_tamed": s["wurms_tamed"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _apex_habitat_audit_effect(obj, state):
    """Apex Habitat Audit: gain 1 clearance per tamed Wurm anomaly you
    control.  'Tamed' = current hazard < printed hazard (Wurm Devourer
    has fired at least once)."""
    tamed_count = 0
    zones = state.zones or {}
    for zone_objs in zones.values():
        if not isinstance(zone_objs, list):
            continue
        for anomaly_obj in zone_objs:
            if getattr(anomaly_obj, "controller", None) != obj.controller:
                continue
            card_def = getattr(anomaly_obj, "card_def", None)
            if not card_def or not getattr(card_def, "scp_wurm_devourer", False):
                continue
            cur_hazard = getattr(anomaly_obj.state, "scp_hazard",
                                  card_def.scp_hazard)
            if cur_hazard < card_def.scp_hazard:
                tamed_count += 1
    if tamed_count == 0:
        return []
    s = scp.site(state, obj.controller)
    s["clearance"] = s.get("clearance", 0) + tamed_count
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "apex_habitat_audit",
            "clearance_gained": tamed_count,
            "clearance": s["clearance"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _apex_reclamation_site_on_tame(obj, state):
    """Apex Reclamation Site: when a Wurm is tamed, gain 1 archive.
    Wired as on_contain on the facility; actual 'on-tame' event is a
    Phase-6 TODO.  For now fires on contain as the nearest proxy."""
    s = scp.site(state, obj.controller)
    s["archives"] = s.get("archives", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "apex_reclamation_site_archive",
            "archives": s["archives"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


# ---------------------------------------------------------------------------
# 14 Anomalies
# ---------------------------------------------------------------------------


# 1. SCP-FBN-9001 — Worldspine Wurm (mythic, Wurm Devourer + Annihilation Wave 2)
_WORLDSPINE_WURM = _annihilation_wave(
    _wurm_devourer(
        _fbn_card(
            "SCP-FBN-9001: Worldspine Wurm, Class-V Apollyon Fauna",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=7,
            curiosity=3,
            hazard=6,
            red_tape=2,
            subtypes={"Wurm", "Apollyon"},
            text=(
                "Wurm Devourer. Annihilation Wave 2. "
                "When contained, opposing breach +1 — even captured, it nearly "
                "ended everything. 15 kilometres from nose to tail. The hangar "
                "was not designed with this in mind."
            ),
            rarity="mythic",
            on_contain=_worldspine_on_contain,
        )
    ),
    n=2,
)


# 2. SCP-FBN-9002 — Pelakka Wurm (mythic, Wurm Devourer; test on success = archive)
_PELAKKA_WURM = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9002: Pelakka Wurm, Class-IV Apollyon Fauna",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=6,
        curiosity=3,
        hazard=5,
        red_tape=2,
        subtypes={"Wurm", "Apollyon"},
        text=(
            "Wurm Devourer. "
            "On each successful research test, gain 1 archive — the lifelink "
            "analogue maps to biological data harvested during each taming session. "
            "The Pelakka feeds. The Foundation catalogues. Both are satisfied."
        ),
        rarity="mythic",
        on_test=_pelakka_on_test,
    )
)


# 3. SCP-FBN-9003 — Engulfing Slagwurm (rare, Wurm Devourer + Annihilation Wave 1)
_ENGULFING_SLAGWURM = _annihilation_wave(
    _wurm_devourer(
        _fbn_card(
            "SCP-FBN-9003: Engulfing Slagwurm, Class-IV Containment",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=5,
            curiosity=3,
            hazard=5,
            red_tape=2,
            subtypes={"Wurm", "Apollyon"},
            text=(
                "Wurm Devourer. Annihilation Wave 1. "
                "On failed research test, opposing breach +1 — whatever the "
                "Slagwurm swallows does not return. A failed session means "
                "losing the researcher entirely."
            ),
            rarity="rare",
            on_test_fail=_slagwurm_on_test_fail,
        )
    ),
    n=1,
)


# 4. SCP-FBN-9004 — Penumbra Wurm (rare, Wurm Devourer)
_PENUMBRA_WURM = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9004: Penumbra Wurm, Class-III Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=4,
        curiosity=2,
        hazard=4,
        red_tape=1,
        subtypes={"Wurm", "Keter"},
        text=(
            "Wurm Devourer. "
            "The shadow is larger than the wurm. Containment of the penumbra — "
            "the zone of gravitational distortion trailing the specimen — requires "
            "a secondary perimeter seven times the size of the primary."
        ),
        rarity="rare",
    )
)


# 5. SCP-FBN-9005 — Hellkite-Specimen (rare, Wurm Devourer + Annihilation Wave 1)
_HELLKITE_SPECIMEN = _annihilation_wave(
    _wurm_devourer(
        _fbn_card(
            "SCP-FBN-9005: Hellkite-Specimen, Class-IV",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=5,
            curiosity=3,
            hazard=4,
            red_tape=2,
            subtypes={"Wurm", "Apollyon"},
            text=(
                "Wurm Devourer. Annihilation Wave 1. "
                "Classification note: 'Hellkite' is a research-team colloquialism. "
                "The specimen is not a dragon. It has not been confirmed to breathe "
                "fire. Fourteen confirmed instances of fire. Classification: pending."
            ),
            rarity="rare",
        )
    ),
    n=1,
)


# 6. SCP-FBN-9006 — Ghalta, Primal Hunger Specimen (rare, Wurm Devourer)
_GHALTA = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9006: Ghalta, Primal Hunger Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=4,
        curiosity=2,
        hazard=4,
        red_tape=1,
        subtypes={"Wurm", "Keter"},
        text=(
            "Wurm Devourer. "
            "On contain, gain 1 archive — biomass alone constitutes a publishable "
            "monograph. 80,000 tonnes of primal hunger, successfully reclassified "
            "from Apollyon to Keter. The paperwork took six weeks."
        ),
        rarity="rare",
        on_contain=_ghalta_on_contain,
    )
)


# 7. SCP-FBN-9007 — Yargle, Vile Containment Subject (uncommon, Wurm Devourer)
_YARGLE = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9007: Yargle, Vile Containment Subject",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=4,
        red_tape=1,
        subtypes={"Wurm", "Keter", "Frog"},
        text=(
            "Wurm Devourer. "
            "Notes: the 'frog' classification was added by the original MTG data "
            "export. The Foundation does not recognise it as a separate subtype. "
            "It is 9 feet of hostile amphibian. It is also 9 feet of hostile wurm. "
            "Containment protocols apply for both simultaneously."
        ),
        rarity="uncommon",
    )
)


# 8. SCP-FBN-9008 — Class-III Wurmling (common, Wurm Devourer)
_CLASS_III_WURMLING = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9008: Class-III Wurmling",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=2,
        curiosity=1,
        hazard=2,
        red_tape=0,
        subtypes={"Wurm", "Keter"},
        text=(
            "Wurm Devourer. "
            "Juvenile specimen. Containment is straightforward at this stage. "
            "Growth projections are less straightforward. The report filed under "
            "FBN-9008-A (Projected Mass at Maturity) has been redacted."
        ),
        rarity="common",
    )
)


# 9. SCP-FBN-9009 — Wurm Coil Engine (uncommon, Wurm Devourer)
_WURM_COIL_ENGINE = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9009: Wurm Coil Engine, Class-IV Forge-Wurm",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=4,
        curiosity=2,
        hazard=3,
        red_tape=1,
        subtypes={"Wurm", "Keter", "Construct"},
        text=(
            "Wurm Devourer. "
            "On contain, Brief 2 — the Coil Engine's contained segments remain "
            "biologically active and produce viable secondary specimens. "
            "Classification: Euclid (per coil segment). Euclid × 3 is classified "
            "under the Keter escalation protocol."
        ),
        rarity="uncommon",
        on_contain=_coil_engine_on_contain,
    )
)


# 10. SCP-FBN-9010 — Class-V Apex Wurm (mythic, Wurm Devourer + Annihilation Wave 2)
_CLASS_V_APEX_WURM = _annihilation_wave(
    _wurm_devourer(
        _fbn_card(
            "SCP-FBN-9010: Class-V Apex Wurm",
            CardType.SCP_ANOMALY,
            archetype=_ARCH,
            containment=6,
            curiosity=3,
            hazard=5,
            red_tape=2,
            subtypes={"Wurm", "Apollyon"},
            text=(
                "Wurm Devourer. Annihilation Wave 2. "
                "The designation 'Apex' is accurate. There is nothing above it "
                "in the local food chain. There is no local food chain. The Apex "
                "Wurm is the food chain. Containment integrity: marginal."
            ),
            rarity="mythic",
        )
    ),
    n=2,
)


# 11. SCP-FBN-9011 — Cradle Wurm Specimen (uncommon, Wurm Devourer)
_CRADLE_WURM = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9011: Cradle Wurm Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=4,
        red_tape=1,
        subtypes={"Wurm", "Keter"},
        text=(
            "Wurm Devourer. "
            "Designate as 'Cradle' based on initial survey showing eggs nested "
            "within the lower jaw musculature. Subsequent survey: 47 eggs. "
            "Addendum: 47 breaches in the secondary perimeter, all consistent "
            "with hatchling emergence."
        ),
        rarity="uncommon",
    )
)


# 12. SCP-FBN-9012 — Spitting Earth Wurm (uncommon, Wurm Devourer)
_SPITTING_EARTH_WURM = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9012: Spitting Earth Wurm",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=3,
        curiosity=2,
        hazard=3,
        red_tape=1,
        subtypes={"Wurm", "Keter"},
        text=(
            "Wurm Devourer. "
            "On failed research test, your breach +1 — the specimen's acid-earth "
            "discharge is projectile at range. Researchers operating within 800m "
            "of the enclosure are required to carry Standard Dissolution Protocol "
            "Form SCP-FBN-9012-H (Emergency Solvent Authorization)."
        ),
        rarity="uncommon",
        on_test_fail=_spitting_earth_on_test_fail,
    )
)


# 13. SCP-FBN-9013 — Underground Wurm-Tunnel Specimen (common, Wurm Devourer)
_UNDERGROUND_TUNNEL = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9013: Underground Wurm-Tunnel Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=2,
        curiosity=1,
        hazard=2,
        red_tape=0,
        subtypes={"Wurm", "Euclid"},
        text=(
            "Wurm Devourer. "
            "On reveal, secrecy -1 — the tunnels predated the facility by "
            "approximately six centuries. Several are bus-route width. "
            "The city council has been asking questions."
        ),
        rarity="common",
        on_reveal=_underground_tunnel_on_reveal,
    )
)


# 14. SCP-FBN-9014 — Apex Reclamation Wurm (rare, Wurm Devourer; on contain = archive + clearance)
_APEX_RECLAMATION_WURM = _wurm_devourer(
    _fbn_card(
        "SCP-FBN-9014: Apex Reclamation Wurm",
        CardType.SCP_ANOMALY,
        archetype=_ARCH,
        containment=5,
        curiosity=3,
        hazard=5,
        red_tape=2,
        subtypes={"Wurm", "Apollyon"},
        text=(
            "Wurm Devourer. "
            "On contain, gain 1 archive and gain 1 clearance — the Reclamation "
            "Wurm's successful reclassification unlocks upper-tier funding. "
            "The O5 Council sent a congratulatory memo. Nobody is sure what "
            "the memo is congratulating, specifically."
        ),
        rarity="rare",
        on_contain=_apex_reclamation_on_contain,
    )
)


# ---------------------------------------------------------------------------
# 6 Personnel
# ---------------------------------------------------------------------------


# 15. Dr. Heyok, Megafauna Specialist (rare, research 2 / contain 1 + auto-pass on Wurm)
_DR_HEYOK = _fbn_card(
    "Dr. Heyok, Megafauna Specialist",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=2,
    clearance=1,
    subtypes={"Researcher", "Specialist"},
    text=(
        "skills: research 2, contain 1. "
        "On assign to a Wurm Devourer anomaly, auto-pass the test — "
        "Heyok has been working with mega-fauna containment since before "
        "the Foundation had a Megafauna Classification Committee. "
        "He wrote the committee's charter."
    ),
    rarity="rare",
    skills={"research": 2, "contain": 1},
    on_reveal=None,
)
_DR_HEYOK.scp_on_assign = _heyok_on_assign


# 16. Researcher Kram, Megafauna Veterinarian (uncommon, research 2)
_RESEARCHER_KRAM = _fbn_card(
    "Researcher Kram, Megafauna Veterinarian",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1,
    clearance=0,
    subtypes={"Researcher"},
    text=(
        "skills: research 2. "
        "Kram approaches each wurm with the same methodical calm she brought "
        "to bovine TB screening in a former life. The main difference, she notes, "
        "is that the wurms are aware of the screening."
    ),
    rarity="uncommon",
    skills={"research": 2},
)


# 17. Operative O5-15, Apex Asset Coordinator (rare, contain 2; on-tame = archive)
_O5_15 = _fbn_card(
    "Operative O5-15, Apex Asset Coordinator",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=2,
    clearance=1,
    subtypes={"Operative", "O5-Council"},
    text=(
        "skills: contain 2. "
        "When a Wurm anomaly is tamed (Wurm Devourer fires), gain 1 archive. "
        "[TODO: engine Phase-6 on_tame event for per-taming trigger; "
        "currently fires on contain as proxy.]"
    ),
    rarity="rare",
    skills={"contain": 2},
)
# Wire on_contain as proxy until engine Phase-6 on_tame event exists.
_O5_15.scp_on_contain = _o5_15_on_tame_hook


# 18. Class-A Megafauna Specialist (uncommon, research 1 / contain 1)
_CLASS_A_MEGAFAUNA = _fbn_card(
    "Class-A Megafauna Specialist",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1,
    clearance=0,
    subtypes={"Operative", "Specialist"},
    text=(
        "skills: research 1, contain 1. "
        "Class-A clearance for megafauna operations. 'Class-A' here does not "
        "mean excellent; it means you have signed the disclaimer and are cleared "
        "to enter the outer perimeter without an escort."
    ),
    rarity="uncommon",
    skills={"research": 1, "contain": 1},
)


# 19. Researcher "Tamer" (uncommon, research 2)
_RESEARCHER_TAMER = _fbn_card(
    "Researcher \"Tamer\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=1,
    clearance=0,
    subtypes={"Researcher"},
    text=(
        "skills: research 2. "
        "Callsign awarded after surviving three unsupervised sessions with "
        "SCP-FBN-9001. Preferred approach: very long pole, very short session, "
        "very immediate exit. Has published twelve papers on wurm behavioural "
        "conditioning. Has not yet lost a limb. (Touch wood.)"
    ),
    rarity="uncommon",
    skills={"research": 2},
)


# 20. Operative "Wurmtongue" (common, contain 1)
_OPERATIVE_WURMTONGUE = _fbn_card(
    "Operative \"Wurmtongue\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCH,
    red_tape=0,
    clearance=0,
    subtypes={"Operative"},
    text=(
        "skills: contain 1. "
        "Callsign is a reference to J.R.R. Tolkien, not to any anomalous "
        "lingual properties. The operative's tongue is baseline human. "
        "They have simply been told not to provoke anything and have "
        "taken the advice more seriously than most."
    ),
    rarity="common",
    skills={"contain": 1},
)


# ---------------------------------------------------------------------------
# 5 Procedures
# ---------------------------------------------------------------------------


# 21. Apex Sedation Protocol (rare, auto-pass on highest-hazard Wurm Devourer)
_APEX_SEDATION = _fbn_card(
    "Apex Sedation Protocol",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Protocol"},
    text=(
        "Run a test on your highest-hazard Wurm Devourer anomaly. "
        "The test auto-passes (Wurm Devourer fires). "
        "The sedative was developed by combining six Schedule-I compounds "
        "and one substance whose legal status is 'pending classification'. "
        "It works exactly once per specimen per week."
    ),
    rarity="rare",
    effect=_apex_sedation_effect,
)


# 22. Tame the Giant (uncommon, trigger Wurm Devourer on highest-hazard wurm)
_TAME_THE_GIANT = _fbn_card(
    "Tame the Giant",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Protocol"},
    text=(
        "Trigger Wurm Devourer on your highest-hazard Wurm anomaly — "
        "the taming fires (-2 hazard / +2 containment). "
        "There is no manual for this. There are seventeen drafts of a manual, "
        "each cancelling the previous. The field operatives have read none of them."
    ),
    rarity="uncommon",
    effect=_tame_the_giant_effect,
)


# 23. Megafauna Audit (rare, each Wurm Devourer anomaly: hazard -1 / containment +1)
_MEGAFAUNA_AUDIT = _fbn_card(
    "Megafauna Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Audit"},
    text=(
        "Each Wurm Devourer anomaly you control has hazard -1 and "
        "containment +1 until end of turn. "
        "Full site-wide audit of containment integrity for all mega-fauna "
        "specimens. Cross-referencing 847 open action items. "
        "Closing 3. Re-opening 11."
    ),
    rarity="rare",
    effect=_megafauna_audit_effect,
)


# 24. Class-V Apex Sweep (mythic, all Wurm Devourer anomalies tamed twice)
_CLASS_V_APEX_SWEEP = _fbn_card(
    "Class-V Apex Sweep",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=3,
    subtypes={"Protocol"},
    text=(
        "Each Wurm Devourer anomaly you control becomes tamed: "
        "Wurm Devourer fires twice on each (hazard -4 / containment +4 each, "
        "wurms_tamed +2 per anomaly). "
        "Full mobilisation of the Megafauna Division. All sedation reserves "
        "consumed. The wurms are, briefly, cooperative. The report will note "
        "that 'briefly' covered a 14-minute window."
    ),
    rarity="mythic",
    effect=_apex_sweep_effect,
)


# 25. Apex Habitat Audit (uncommon, gain 1 clearance per tamed wurm)
_APEX_HABITAT_AUDIT = _fbn_card(
    "Apex Habitat Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Audit"},
    text=(
        "Gain 1 clearance per tamed Wurm anomaly you control — "
        "successful reclassifications from Apollyon are noted by the "
        "O5 Council and translate directly into expanded site authority. "
        "A tamed wurm is a contained asset. An asset justifies clearance."
    ),
    rarity="uncommon",
    effect=_apex_habitat_audit_effect,
)


# ---------------------------------------------------------------------------
# 4 Facilities
# ---------------------------------------------------------------------------


# 26. Apex Megafauna Habitat (rare, contain +1, research +1, Wurm hazard +1 in facility)
_APEX_MEGAFAUNA_HABITAT = _fbn_card(
    "Apex Megafauna Habitat",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Habitat", "Containment"},
    text=(
        "Bonus: contain +1, research +1. "
        "Your Wurm anomalies' hazard +1 while in this facility — "
        "a purpose-built enclosure designed to keep the specimens at peak "
        "biological activity for research purposes. The hazard increase is "
        "considered 'scientifically desirable'. The insurance underwriters "
        "have been informed."
    ),
    rarity="rare",
    bonus={"contain": 1, "research": 1},
    aura={"subtype:Wurm": {"hazard_mod": 1}},
)


# 27. Containment Pit Vault (uncommon, contain +1)
_CONTAINMENT_PIT_VAULT = _fbn_card(
    "Containment Pit Vault",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Vault", "Containment"},
    text=(
        "Bonus: contain +1. "
        "Originally a disused industrial quarry. Retrofitted with "
        "containment-grade reinforcement and a lid. The lid is the "
        "most expensive lid the Foundation has ever commissioned."
    ),
    rarity="uncommon",
    bonus={"contain": 1},
)


# 28. Megafauna Audit Bureau (uncommon, research +1)
_MEGAFAUNA_AUDIT_BUREAU = _fbn_card(
    "Megafauna Audit Bureau",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=1,
    subtypes={"Bureau", "Administrative"},
    text=(
        "Bonus: research +1. "
        "The Bureau was established to process the paperwork generated "
        "by the Megafauna Division. The Bureau generates more paperwork "
        "than the Megafauna Division. An oversight committee was formed "
        "to audit the Bureau. It has not yet filed its first report."
    ),
    rarity="uncommon",
    bonus={"research": 1},
)


# 29. Apex Reclamation Site (rare, research +1; when Wurm tamed gain 1 archive)
_APEX_RECLAMATION_SITE = _fbn_card(
    "Apex Reclamation Site",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    red_tape=2,
    subtypes={"Site", "Containment"},
    text=(
        "Bonus: research +1. "
        "When a Wurm is tamed (Wurm Devourer fires), gain 1 archive. "
        "[TODO: engine Phase-6 on_tame event; currently proxied via on_contain.] "
        "The Reclamation Site is where successful taming projects are "
        "reclassified. The archive room is the only part of the site that "
        "smells like fresh paper rather than whatever the Apex Wurms emit."
    ),
    rarity="rare",
    bonus={"research": 1},
)
_APEX_RECLAMATION_SITE.scp_on_contain = _apex_reclamation_site_on_tame


# 29b. Apex Pacification Reactor (mythic signature bomb — activated taming engine)
def _apex_pacification_best_wurm(state, controller):
    """Your highest-effective-hazard active Wurm Devourer anomaly (or None)."""
    best, best_haz = None, -1
    for aid in state.scp_anomalies.get(controller, []):
        a = state.objects.get(aid)
        if (a is not None and a.state.scp_status == "active"
                and getattr(a.card_def, "scp_wurm_devourer", False)):
            h = int(getattr(a.state, "scp_hazard", getattr(a.card_def, "scp_hazard", 0)) or 0)
            if h > best_haz:
                best, best_haz = a, h
    return best, best_haz


def _apex_pacification_effect(obj, state):
    game = getattr(state, "_game", None)
    best, best_haz = _apex_pacification_best_wurm(state, obj.controller)
    if best is None:
        return []
    new_haz = max(0, best_haz - 3)
    best.state.scp_hazard = new_haz  # permanent; now honored by _effective_hazard
    cur_contain = getattr(best.state, "scp_containment", best.card_def.scp_containment)
    best.state.scp_containment = cur_contain + 2
    s = scp.site(state, obj.controller)
    s["wurms_tamed"] = int(s.get("wurms_tamed", 0) or 0) + 1
    events = [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller, "reason": "apex_pacification",
            "anomaly_id": best.id, "new_hazard": new_haz,
            "wurms_tamed": s["wurms_tamed"],
        },
        source=obj.id, controller=obj.controller,
    )]
    if new_haz == 0 and game is not None:
        events.extend(scp.gain_archives(game, obj.controller, 1, source=obj.id))
    return events


def _apex_pacification_value(obj, state, _mode):
    # Fire when there's a high-hazard Wurm Devourer to pacify — each point of
    # hazard removed is ~1 breach/turn avoided, and each tame advances the
    # 3-tamed alt-win. 0 when no wurm is on board (nothing to tame, no waste).
    best, best_haz = _apex_pacification_best_wurm(state, obj.controller)
    if best is None or best_haz <= 0:
        return 0.0
    tamed = int(scp.site(state, obj.controller).get("wurms_tamed", 0) or 0)
    return min(best_haz, 3) * 0.6 + (0.8 if tamed >= 2 else 0.3)


def _apex_pacification_setup(obj, state):
    from src.engine.scp_abilities import make_scp_activated_ability
    from src.engine.scp_costs import SCPCost, SCPValueHint
    make_scp_activated_ability(
        obj,
        cost=SCPCost(exhaust_self=True),
        description=("Hard-tame your highest-hazard Wurm Devourer: hazard -3 + "
                     "containment +2 + a tamed wurm; +1 archive if fully pacified"),
        effect_fn=_apex_pacification_effect,
        value_hint=SCPValueHint(custom_value_fn=_apex_pacification_value),
    )
    return []


_APEX_PACIFICATION_REACTOR = _fbn_card(
    "SCP-FBN-9099: Apex Pacification Reactor",
    CardType.SCP_FACILITY,
    archetype=_ARCH,
    keywords={"Pacify"},
    red_tape=2,
    clearance=1,
    subtypes={"Reactor", "Containment", "Megafauna"},
    text=(
        "Exhaust: hard-tame your highest-hazard Wurm Devourer anomaly — its "
        "hazard -3 (permanently) and containment +2, and it counts as a tamed "
        "wurm. If its hazard reaches 0, gain 1 archive. "
        "The reactor does not sedate the specimen. It convinces the specimen "
        "that being contained was its own idea."
    ),
    rarity="mythic",
)
_APEX_PACIFICATION_REACTOR.setup_interceptors = _apex_pacification_setup


# ---------------------------------------------------------------------------
# 1 Mandate (alt-win anchor)
# ---------------------------------------------------------------------------


# 30. Mandate FBN-WAT: Wurm Apex Tamed Doctrine (mythic, alt-win wurm_apex_tamed)
_MANDATE_WAT = _fbn_card(
    "Mandate FBN-WAT: Wurm Apex Tamed Doctrine",
    CardType.SCP_MANDATE,
    archetype=_ARCH,
    red_tape=3,
    clearance=2,
    subtypes={"Mandate", "Apollyon"},
    text=(
        "Mandate. Alt-win wurm_apex_tamed: when 3+ Wurm Devourer anomalies "
        "have been tamed by you (wurms_tamed >= 3), you win at end of your "
        "next turn. "
        "O5 DIRECTIVE FBN-WAT: The successful taming and reclassification of "
        "three or more Apollyon-class mega-fauna constitutes a paradigm shift "
        "in Foundation operational doctrine. The entities are assets. "
        "The Foundation does not release assets."
    ),
    rarity="mythic",
)
_MANDATE_WAT.scp_alt_win = "wurm_apex_tamed"


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------


WURM_APEX_CARDS: list[CardDefinition] = [
    # 14 Anomalies
    _WORLDSPINE_WURM,
    _PELAKKA_WURM,
    _ENGULFING_SLAGWURM,
    _PENUMBRA_WURM,
    _HELLKITE_SPECIMEN,
    _GHALTA,
    _YARGLE,
    _CLASS_III_WURMLING,
    _WURM_COIL_ENGINE,
    _CLASS_V_APEX_WURM,
    _CRADLE_WURM,
    _SPITTING_EARTH_WURM,
    _UNDERGROUND_TUNNEL,
    _APEX_RECLAMATION_WURM,
    # 6 Personnel
    _DR_HEYOK,
    _RESEARCHER_KRAM,
    _O5_15,
    _CLASS_A_MEGAFAUNA,
    _RESEARCHER_TAMER,
    _OPERATIVE_WURMTONGUE,
    # 5 Procedures
    _APEX_SEDATION,
    _TAME_THE_GIANT,
    _MEGAFAUNA_AUDIT,
    _CLASS_V_APEX_SWEEP,
    _APEX_HABITAT_AUDIT,
    # 4 Facilities
    _APEX_MEGAFAUNA_HABITAT,
    _CONTAINMENT_PIT_VAULT,
    _MEGAFAUNA_AUDIT_BUREAU,
    _APEX_RECLAMATION_SITE,
    _APEX_PACIFICATION_REACTOR,
    # 1 Mandate
    _MANDATE_WAT,
]

_CARDS = WURM_APEX_CARDS
