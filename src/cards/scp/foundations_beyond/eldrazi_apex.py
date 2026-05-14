"""Eldrazi Apex (FBN) — Apollyon void incursion sub-set.

30 cards for the `eldrazi_apex` archetype of Foundations Beyond.
Theme: The SCP Foundation has classified the Eldrazi titans and their brood as
Apollyon-class void entities. The deck sacrifices its own dossiers (cheap
scion/spawn anomalies) to fuel Annihilation Wave breaches on its three apex
anomalies, pushing opposing breach toward 12 to trigger public_panic.

Composition (30 total):
- 14 Anomalies (3 mythic apex, 5 uncommon brood/support, 4 common fodder,
  2 rare escalation tier)
- 6 Personnel (2 rare, 2 uncommon, 2 common)
- 5 Procedures (1 mythic, 2 rare, 1 uncommon, 1 common)
- 4 Facilities (2 rare, 2 uncommon)
- 1 Mandate (mythic)

Alt-win condition: `opposing_breach >= 12` (Mandate FBN-AVI: Apollyon Vector
Inhibition). The engine's standard `public_panic` loss fires at breach 10;
this mandate's win-check fires at 12 so the Eldrazi deck can accelerate past
normal breach thresholds.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import (
    _annihilation_wave,
    _brief,
    _fbn_card,
    _with_fbn_metadata,
)

_ARCH = "eldrazi_apex"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ea_card(
    name: str,
    card_type: CardType,
    **kwargs,
) -> CardDefinition:
    """Thin wrapper: create a card, stamp FBN metadata, pin the archetype."""
    art_prompt = kwargs.pop("art_prompt", None)
    card = scp.make_scp_card(name, card_type, **kwargs)
    return _with_fbn_metadata(
        card,
        archetype=_ARCH,
        art_prompt=art_prompt or (
            f"Original SCP-inspired trading card art for {name}: "
            "a non-Euclidean Eldrazi entity inside a Foundation maximum-containment "
            "cell — black-concrete brutalist architecture, redacted/stamped dossiers "
            "overlaid, void-geometry distortions in the background, Annihilator-scale "
            "horror at a bureaucratic remove, colorless palette with ochre sodium-arc "
            "accent light, no text, no logos, no card frames, high-detail digital painting."
        ),
    )


# ---------------------------------------------------------------------------
# 14 ANOMALIES
# ---------------------------------------------------------------------------

# ── Mythic apex trio (Ulamog, Kozilek, Emrakul) ───────────────────────────


# 1. SCP-FBN-2271: Apollyon-Class Void Eater (Ulamog)
# Rules text: Annihilation Wave 2.
_VOID_EATER = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2271: Apollyon-Class Void Eater (Ulamog)",
        CardType.SCP_ANOMALY,
        containment=6,
        curiosity=3,
        hazard=4,
        red_tape=2,
        clearance=0,
        subtypes={"Eldrazi", "Titan", "Apollyon"},
        text=(
            "Annihilation Wave 2. On breach, redact 2 opposing dossiers "
            "and opposing breach +2. "
            "He did not arrive. He was always here."
        ),
        rarity="mythic",
    ),
    n=2,
)


# 2. SCP-FBN-2272: Apollyon-Class Hedron-Tilt (Kozilek)
# Rules text: Annihilation Wave 2. Brief 1 on reveal.
def _kozilek_reveal(obj, state):
    """On reveal, Brief 1 (briefing +1)."""
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hedron_tilt_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_HEDRON_TILT = _brief(
    _annihilation_wave(
        _ea_card(
            "SCP-FBN-2272: Apollyon-Class Hedron-Tilt (Kozilek)",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=4,
            hazard=4,
            red_tape=2,
            clearance=0,
            subtypes={"Eldrazi", "Titan", "Apollyon"},
            text=(
                "Annihilation Wave 2. Brief 1 on reveal. "
                "The geometry of the containment wing has not stabilized. "
                "O5 has been informed."
            ),
            rarity="mythic",
        ),
        n=2,
    ),
    n=1,
)
_HEDRON_TILT.scp_on_reveal = _kozilek_reveal


# 3. SCP-FBN-2273: Apollyon-Class Reality-Eater (Emrakul)
# Rules text: Annihilation Wave 3. On contain, opposing breach +2 anyway.
def _emrakul_contain(obj, state):
    """Even when contained, opposing breach climbs +2 (reality reasserts)."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp:
        s_opp = scp.site(state, opp)
        s_opp["breach"] = s_opp.get("breach", 0) + 2
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "emrakul_contain_bleed",
            "opp_breach": scp.site(state, opp).get("breach", 0) if opp else 0,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_REALITY_EATER = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2273: Apollyon-Class Reality-Eater (Emrakul)",
        CardType.SCP_ANOMALY,
        containment=7,
        curiosity=3,
        hazard=5,
        red_tape=2,
        clearance=0,
        subtypes={"Eldrazi", "Titan", "Apollyon"},
        text=(
            "Annihilation Wave 3. On contain, opposing breach +2 anyway. "
            "Containment integrity: holding. "
            "Site exposure projections: classified."
        ),
        rarity="mythic",
    ),
    n=3,
)
_REALITY_EATER.scp_on_contain = _emrakul_contain


# ── Rare escalation anomalies ─────────────────────────────────────────────


# 4. SCP-FBN-2280: Eldrazi Conscription Pattern
# Rules text: Annihilation Wave 1. When this anomaly breaches, opposing
# personnel become exhausted.
def _conscription_breach(obj, state):
    """On breach, exhaust all opposing personnel (they cannot act next turn)."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    # TODO: engine primitive for mass-exhaust opposing personnel not yet
    # implemented — emit an SCP_INCIDENT_RESOLVED info event as a placeholder.
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "conscription_exhaustion",
            "target_player": opp,
            "effect": "exhaust_all_personnel",
        },
        source=obj.id,
        controller=obj.controller,
    )]


_CONSCRIPTION_PATTERN = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2280: Eldrazi Conscription Pattern",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=2,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Eldrazi", "Memetic"},
        text=(
            "Annihilation Wave 1. When this anomaly breaches, opposing "
            "personnel become exhausted. "
            "The anomaly does not fight. It drafts."
        ),
        rarity="rare",
    ),
    n=1,
)
_CONSCRIPTION_PATTERN.scp_on_breach = _conscription_breach


# 5. SCP-FBN-2281: Hedron-Caged Titan
# Rules text: Annihilation Wave 2. On reveal, hazard +1 per pending dossier
# you control.
def _hedron_caged_reveal(obj, state):
    """On reveal, hazard +1 per pending dossier the controller has active."""
    s = scp.site(state, obj.controller)
    pending_count = len(s.get("pending_dossiers", []))
    if pending_count > 0:
        current_hazard = getattr(obj, "scp_hazard", obj.characteristics.get("hazard", 0))
        obj.scp_hazard = current_hazard + pending_count
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hedron_titan_reveal_boost",
            "pending_count": pending_count,
            "new_hazard": getattr(obj, "scp_hazard", 0),
        },
        source=obj.id,
        controller=obj.controller,
    )]


_HEDRON_CAGED_TITAN = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2281: Hedron-Caged Titan",
        CardType.SCP_ANOMALY,
        containment=6,
        curiosity=3,
        hazard=3,
        red_tape=2,
        clearance=0,
        subtypes={"Eldrazi", "Titan"},
        text=(
            "Annihilation Wave 2. On reveal, hazard +1 per pending dossier "
            "you control. The hedrons slow it. The hedrons are also on fire."
        ),
        rarity="rare",
    ),
    n=2,
)
_HEDRON_CAGED_TITAN.scp_on_reveal = _hedron_caged_reveal


# ── Uncommon brood anomalies ──────────────────────────────────────────────


# 6. SCP-FBN-2276: Void Drone, Apollyon-Adjacent
# Rules text: Annihilation Wave 1.
_VOID_DRONE = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2276: Void Drone, Apollyon-Adjacent",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Eldrazi", "Drone"},
        text=(
            "Annihilation Wave 1. "
            "It doesn't look at you. It doesn't look at anything. "
            "The radar shows three dozen more."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# 7. SCP-FBN-2277: Hedron Network Fragment
# Rules text: When you sacrifice an Eldrazi anomaly, gain 1 Brief.
def _hedron_fragment_sac(obj, state, sacrificed_obj=None):
    """When you sacrifice an Eldrazi anomaly, briefing +1."""
    if sacrificed_obj is not None:
        sac_subtypes = set(getattr(
            sacrificed_obj, "subtypes",
            getattr(getattr(sacrificed_obj, "characteristics", None), "subtypes", set()),
        ) or set())
        if "Eldrazi" not in sac_subtypes:
            return []
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hedron_fragment_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_HEDRON_FRAGMENT = _ea_card(
    "SCP-FBN-2277: Hedron Network Fragment",
    CardType.SCP_ANOMALY,
    containment=2,
    curiosity=2,
    hazard=2,
    red_tape=1,
    clearance=0,
    subtypes={"Eldrazi", "Object"},
    text=(
        "When you sacrifice an Eldrazi anomaly, gain 1 Brief. "
        "The geometry implies a larger structure. The larger structure "
        "implies a larger absence."
    ),
    rarity="uncommon",
)
# TODO: engine hook for SCP_SACRIFICE filtered to Eldrazi subtypes not yet
# formally implemented — attaching to scp_on_sacrifice as convention placeholder.
_HEDRON_FRAGMENT.scp_on_sacrifice = _hedron_fragment_sac


# 8. SCP-FBN-2278: Brood Tyrant Specimen
# Rules text: Annihilation Wave 1.
_BROOD_TYRANT = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2278: Brood Tyrant Specimen",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Eldrazi", "Brood"},
        text=(
            "Annihilation Wave 1. "
            "It controls the smaller anomalies by proximity. "
            "The smaller anomalies do not appear to know this."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# 9. SCP-FBN-2279: Void Eel
# Rules text: Annihilation Wave 1.
_VOID_EEL = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2279: Void Eel",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Eldrazi", "Serpentine"},
        text=(
            "Annihilation Wave 1. "
            "Depth: inapplicable. "
            "Behavior when fed: inapplicable. "
            "Behavior when not fed: see attached incident log."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# 10. SCP-FBN-2282: Void Aberration
# Rules text: Annihilation Wave 1.
_VOID_ABERRATION = _annihilation_wave(
    _ea_card(
        "SCP-FBN-2282: Void Aberration",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=1,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Eldrazi", "Aberration"},
        text=(
            "Annihilation Wave 1. "
            "Classification: impossible. "
            "Containment: provisional. "
            "Exposure risk: catastrophic."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# ── Common fodder anomalies ───────────────────────────────────────────────


# 11. SCP-FBN-2274: Apollyon Vector Spawn
# Rules text: Sacrificial fodder. When this is memory-holed, gain 1 Brief.
def _vector_spawn_memoryholes(obj, state):
    """When memory-holed, briefing +1."""
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "vector_spawn_memory_hole_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_VECTOR_SPAWN = _ea_card(
    "SCP-FBN-2274: Apollyon Vector Spawn",
    CardType.SCP_ANOMALY,
    containment=1,
    curiosity=1,
    hazard=1,
    red_tape=0,
    clearance=0,
    subtypes={"Eldrazi", "Spawn"},
    text=(
        "When this is memory-holed, gain 1 Brief. "
        "Sub-object of SCP-FBN-2271. "
        "Docile when isolated. Docile is not safe."
    ),
    rarity="common",
)
_VECTOR_SPAWN.scp_on_memory_hole = _vector_spawn_memoryholes


# 12. SCP-FBN-2275: Eldrazi Scion Pattern
# Rules text: Sacrificial fodder. When this is memory-holed, your next
# Apollyon-class Anomaly costs -1 red_tape.
def _scion_pattern_memoryholes(obj, state):
    """When memory-holed, the next Apollyon-class anomaly costs -1 red_tape."""
    s = scp.site(state, obj.controller)
    # Accumulate discount token (engine reads scp_apollyon_cost_reduction at
    # red_tape calculation time and decrements by 1 per pending discount).
    # TODO: engine read of scp_apollyon_cost_reduction not yet wired in the
    # paperwork queue cost calculator — this sets the flag; engine side pending.
    s["scp_apollyon_cost_reduction"] = s.get("scp_apollyon_cost_reduction", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "scion_pattern_cost_reduction",
            "apollyon_discount_pending": s["scp_apollyon_cost_reduction"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_SCION_PATTERN = _ea_card(
    "SCP-FBN-2275: Eldrazi Scion Pattern",
    CardType.SCP_ANOMALY,
    containment=2,
    curiosity=1,
    hazard=1,
    red_tape=0,
    clearance=0,
    subtypes={"Eldrazi", "Scion"},
    text=(
        "When this is memory-holed, your next Apollyon-class Anomaly "
        "costs -1 red_tape. "
        "Residual mana crystallisation. "
        "Recommend accelerated disposal."
    ),
    rarity="common",
)
_SCION_PATTERN.scp_on_memory_hole = _scion_pattern_memoryholes


# 13. SCP-FBN-2283: Apollyon-Adjacent Ingress
# Rules text: Sacrificial fodder. When sacrificed, opposing breach +1.
def _ingress_sac(obj, state):
    """When sacrificed, opposing breach +1."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp:
        s_opp = scp.site(state, opp)
        s_opp["breach"] = s_opp.get("breach", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ingress_sac_breach",
            "target_player": opp,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_APOLLYON_INGRESS = _ea_card(
    "SCP-FBN-2283: Apollyon-Adjacent Ingress",
    CardType.SCP_ANOMALY,
    containment=2,
    curiosity=1,
    hazard=2,
    red_tape=0,
    clearance=0,
    subtypes={"Eldrazi", "Portal"},
    text=(
        "When sacrificed, opposing breach +1. "
        "We sealed it. Something on the other side unsealed it. "
        "We sealed it again."
    ),
    rarity="common",
)
_APOLLYON_INGRESS.scp_on_sacrifice = _ingress_sac


# 14. SCP-FBN-2284: Reality-Hole Fragment
# Rules text: When you sacrifice this, draw 1 paperwork.
def _reality_hole_sac(obj, state):
    """When sacrificed, draw 1 paperwork card."""
    # TODO: engine direct-draw-from-sacrifice hook not yet implemented;
    # emit SCP_PAPERWORK_TICK as the closest existing primitive.
    return [scp.Event(
        type=scp.EventType.SCP_PAPERWORK_TICK,
        payload={
            "player": obj.controller,
            "reason": "reality_hole_sac_draw",
            "count": 1,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_REALITY_HOLE = _ea_card(
    "SCP-FBN-2284: Reality-Hole Fragment",
    CardType.SCP_ANOMALY,
    containment=2,
    curiosity=2,
    hazard=2,
    red_tape=1,
    clearance=0,
    subtypes={"Eldrazi", "Spatial"},
    text=(
        "When you sacrifice this, draw 1 paperwork. "
        "Stable. Stable-adjacent. "
        "The paperwork regarding it is also stable-adjacent."
    ),
    rarity="common",
)
_REALITY_HOLE.scp_on_sacrifice = _reality_hole_sac


# ---------------------------------------------------------------------------
# 6 PERSONNEL
# ---------------------------------------------------------------------------


# 15. Researcher Drake-Ulamog Pact Interpreter
# Rules text: skills: research 2. When you sacrifice an anomaly, gain 1 Brief.
def _drake_sac_brief(obj, state, sacrificed_obj=None):
    """When you sacrifice any anomaly, briefing +1."""
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "drake_sac_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_RESEARCHER_DRAKE = _ea_card(
    "Researcher Drake-Ulamog Pact Interpreter",
    CardType.SCP_PERSONNEL,
    red_tape=1,
    clearance=0,
    skills={"research": 2},
    subtypes={"Researcher"},
    text=(
        "skills: research 2. "
        "When you sacrifice an anomaly, gain 1 Brief. "
        "Voluntary exposure agreement on file. "
        "Amendment 12: still alive."
    ),
    rarity="uncommon",
)
# TODO: engine hook for SCP_SACRIFICE for personnel passive triggers not yet
# formally wired — attaching to scp_on_sacrifice as convention placeholder.
_RESEARCHER_DRAKE.scp_on_sacrifice = _drake_sac_brief


# 16. Operative Kozilek-Liaison "Cipher"
# Rules text: skills: research 2, contain 1. Your Annihilation Wave triggers
# add +1 to the wave's N.
_OPERATIVE_CIPHER = _ea_card(
    "Operative Kozilek-Liaison \"Cipher\"",
    CardType.SCP_PERSONNEL,
    red_tape=2,
    clearance=1,
    skills={"research": 2, "contain": 1},
    subtypes={"Operative"},
    text=(
        "skills: research 2, contain 1. "
        "Your Annihilation Wave triggers add +1 to the wave's N. "
        "She has read the full void geometry. "
        "She is still reading it."
    ),
    rarity="rare",
)
# TODO: engine-side Annihilation Wave N augmentation via personnel passive
# not yet implemented — scp_annihilation_wave_bonus flag to be read at
# breach-tick resolution time.
_OPERATIVE_CIPHER.scp_annihilation_wave_bonus = 1


# 17. Class-A Emrakul Containment Specialist
# Rules text: skills: contain 2, research 1. On assign, opposing breach +1.
def _emrakul_specialist_assign(obj, state, action=None):
    """On assign, opposing breach +1 — working with Emrakul is never cost-free."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp:
        s_opp = scp.site(state, opp)
        s_opp["breach"] = s_opp.get("breach", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "emrakul_specialist_assign_breach",
            "target_player": opp,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_EMRAKUL_SPECIALIST = _ea_card(
    "Class-A Emrakul Containment Specialist",
    CardType.SCP_PERSONNEL,
    red_tape=2,
    clearance=1,
    skills={"contain": 2, "research": 1},
    subtypes={"Class-A", "Specialist"},
    text=(
        "skills: contain 2, research 1. "
        "On assign, opposing breach +1. "
        "She knows where the holes in reality are. "
        "She made three of them."
    ),
    rarity="rare",
)
_EMRAKUL_SPECIALIST.scp_on_assign = _emrakul_specialist_assign


# 18. Dr. Hedron Calibrator
# Rules text: skills: research 2. When an Apollyon-class anomaly enters play,
# gain 1 Brief.
def _hedron_calibrator_etb(obj, state, entering_obj=None):
    """When an Apollyon-class anomaly enters play, briefing +1."""
    if entering_obj is not None:
        etb_subtypes = set(getattr(
            entering_obj, "subtypes",
            getattr(getattr(entering_obj, "characteristics", None), "subtypes", set()),
        ) or set())
        if "Apollyon" not in etb_subtypes:
            return []
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hedron_calibrator_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_DR_HEDRON_CALIBRATOR = _ea_card(
    "Dr. Hedron Calibrator",
    CardType.SCP_PERSONNEL,
    red_tape=1,
    clearance=0,
    skills={"research": 2},
    subtypes={"Researcher", "Specialist"},
    text=(
        "skills: research 2. "
        "When an Apollyon-class anomaly enters play, gain 1 Brief. "
        "The calibrations are always slightly off. "
        "She prefers it that way."
    ),
    rarity="uncommon",
)
# TODO: engine hook for SCP_OPEN_DOSSIER filtered to Apollyon subtype for
# personnel passive triggers — attaching to scp_on_anomaly_enter as
# convention placeholder.
_DR_HEDRON_CALIBRATOR.scp_on_anomaly_enter = _hedron_calibrator_etb


# 19. Researcher Voider "Drone Five"
# Rules text: skills: contain 1. When sacrificed, opposing breach +1.
def _drone_five_sac(obj, state):
    """When sacrificed, opposing breach +1."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp:
        s_opp = scp.site(state, opp)
        s_opp["breach"] = s_opp.get("breach", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "drone_five_sac_breach",
            "target_player": opp,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_RESEARCHER_DRONE_FIVE = _ea_card(
    "Researcher Voider \"Drone Five\"",
    CardType.SCP_PERSONNEL,
    red_tape=0,
    clearance=0,
    skills={"contain": 1},
    subtypes={"Researcher"},
    text=(
        "skills: contain 1. "
        "When sacrificed, opposing breach +1. "
        "Volunteers were requested. "
        "Drone Five was not a volunteer."
    ),
    rarity="common",
)
_RESEARCHER_DRONE_FIVE.scp_on_sacrifice = _drone_five_sac


# 20. Class-A Operative "Hollowing"
# Rules text: skills: research 1. When you sacrifice an anomaly, this
# personnel ready (refresh).
def _hollowing_sac_ready(obj, state, sacrificed_obj=None):
    """When you sacrifice any anomaly, this personnel becomes ready."""
    # TODO: engine personnel-ready/refresh primitive not yet implemented as
    # a direct event — emitting SCP_INCIDENT_RESOLVED with reason "ready" as
    # placeholder; engine should interpret this to clear exhaustion on obj.id.
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hollowing_ready",
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_OPERATIVE_HOLLOWING = _ea_card(
    "Class-A Operative \"Hollowing\"",
    CardType.SCP_PERSONNEL,
    red_tape=1,
    clearance=0,
    skills={"research": 1},
    subtypes={"Class-A", "Operative"},
    text=(
        "skills: research 1. "
        "When you sacrifice an anomaly, this personnel ready. "
        "She returns from every encounter. "
        "Less, each time."
    ),
    rarity="common",
)
_OPERATIVE_HOLLOWING.scp_on_sacrifice = _hollowing_sac_ready


# ---------------------------------------------------------------------------
# 5 PROCEDURES
# ---------------------------------------------------------------------------


# 21. Protocol: Hedron Network Activation
# Rules text: Sacrifice up to 3 of your pending Anomalies. Gain 1 Brief per
# sacrifice. Your active Annihilation Wave anomalies get +1 to their wave's N
# until end of turn.
def _hedron_activation_play(obj, state):
    """Sac up to 3 pending anomalies; 1 Brief each; AW anomalies get +1 N EOT."""
    s = scp.site(state, obj.controller)
    pending = list(s.get("pending_dossiers", []))
    # Heuristic: sacrifice up to 3 cheapest pending anomalies (by red_tape).
    eligible = []
    for did in pending:
        dossier_obj = state.objects.get(did)
        if dossier_obj is None:
            continue
        card = getattr(dossier_obj, "card_def", None)
        if card and CardType.SCP_ANOMALY in getattr(card, "types", [card.card_type]):
            eligible.append(dossier_obj)
    eligible.sort(key=lambda o: getattr(getattr(o, "card_def", None), "red_tape", 99))
    to_sac = eligible[:3]
    events = []
    for sac_obj in to_sac:
        s["briefing"] = s.get("briefing", 0) + 1
        # TODO: engine SCP_SACRIFICE event not yet fully plumbed for procedures;
        # mark the dossier as sacrificed via memory-hole proxy.
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "hedron_activation_sac",
                "sacrificed": sac_obj.id,
                "briefing": s["briefing"],
            },
            source=obj.id,
            controller=obj.controller,
        ))
    # TODO: +1 Annihilation Wave N until EOT requires a transient state
    # modifier on all active AW anomalies — setting a site-level flag that
    # breach-tick reads this turn.
    s["scp_annihilation_wave_bonus_eot"] = s.get("scp_annihilation_wave_bonus_eot", 0) + 1
    return events


_PROTOCOL_HEDRON_ACTIVATION = _brief(
    _ea_card(
        "Protocol: Hedron Network Activation",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=0,
        subtypes={"Protocol"},
        text=(
            "Sacrifice up to 3 of your pending Anomalies. Gain 1 Brief per "
            "sacrifice. Your active Annihilation Wave anomalies get +1 to "
            "their wave's N until end of turn. "
            "Signed. Countersigned. Witnessed. The witness is gone."
        ),
        rarity="rare",
    ),
    n=1,
)
_PROTOCOL_HEDRON_ACTIVATION.scp_on_play = _hedron_activation_play


# 22. Void Bombardment
# Rules text: Redact 3 opposing dossiers. Your breach +2.
def _void_bombardment_play(obj, state):
    """Redact 3 opposing dossiers; your own breach +2."""
    opp = scp._first_opposing_player(state, obj.controller)
    s_me = scp.site(state, obj.controller)
    s_me["breach"] = s_me.get("breach", 0) + 2
    events = [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "void_bombardment_self_breach",
            "breach": s_me["breach"],
        },
        source=obj.id,
        controller=obj.controller,
    )]
    if opp:
        for _ in range(3):
            # TODO: scp.misfile_dossier helper may not be importable at card
            # module level — using SCP_INCIDENT_RESOLVED info event with
            # reason="force_redact" as placeholder; engine resolves on key.
            events.append(scp.Event(
                type=scp.EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": obj.controller,
                    "reason": "force_redact",
                    "target_player": opp,
                    "count": 1,
                },
                source=obj.id,
                controller=obj.controller,
            ))
    return events


_VOID_BOMBARDMENT = _ea_card(
    "Void Bombardment",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    clearance=0,
    subtypes={"Strike"},
    text=(
        "Redact 3 opposing dossiers. Your breach +2. "
        "Anti-materiel. Anti-memetic. Anti-everything. "
        "The report writes: collateral documented."
    ),
    rarity="rare",
)
_VOID_BOMBARDMENT.scp_on_play = _void_bombardment_play


# 23. Apollyon Vector Sacrifice
# Rules text: Sacrifice 1 of your anomalies. Gain 2 Brief.
def _vector_sacrifice_play(obj, state):
    """Sac 1 anomaly (cheapest heuristic), gain 2 Brief."""
    s = scp.site(state, obj.controller)
    pending = list(s.get("pending_dossiers", []))
    eligible = []
    for did in pending:
        dossier_obj = state.objects.get(did)
        if dossier_obj is None:
            continue
        card = getattr(dossier_obj, "card_def", None)
        if card and CardType.SCP_ANOMALY in getattr(card, "types", [card.card_type]):
            eligible.append(dossier_obj)
    eligible.sort(key=lambda o: getattr(getattr(o, "card_def", None), "red_tape", 99))
    events = []
    if eligible:
        sac_obj = eligible[0]
        s["briefing"] = s.get("briefing", 0) + 2
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "vector_sacrifice_sac",
                "sacrificed": sac_obj.id,
                "briefing": s["briefing"],
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_APOLLYON_VECTOR_SACRIFICE = _brief(
    _ea_card(
        "Apollyon Vector Sacrifice",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        clearance=0,
        subtypes={"Protocol"},
        text=(
            "Sacrifice 1 of your anomalies. Gain 2 Brief. "
            "What is a scion except an offering?"
        ),
        rarity="uncommon",
    ),
    n=2,
)
_APOLLYON_VECTOR_SACRIFICE.scp_on_play = _vector_sacrifice_play


# 24. Hedron Audit
# Rules text: Look at top 3 of your library. Put 1 Eldrazi anomaly on top,
# rest shuffled.
def _hedron_audit_play(obj, state):
    """Scry 3; put 1 Eldrazi anomaly on top, shuffle rest."""
    # TODO: engine library scry + conditional top-sort not yet implemented
    # as a procedure callback primitive — emitting SCP_INCIDENT_RESOLVED with
    # reason="scry_3_put_eldrazi_top" as placeholder; engine resolves on key.
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "scry_3_put_eldrazi_top",
            "scry_depth": 3,
            "filter_subtype": "Eldrazi",
        },
        source=obj.id,
        controller=obj.controller,
    )]


_HEDRON_AUDIT = _ea_card(
    "Hedron Audit",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    clearance=0,
    subtypes={"Audit"},
    text=(
        "Look at top 3 of your library. Put 1 Eldrazi anomaly on top, rest shuffled. "
        "The hedrons are filing themselves. "
        "We are reviewing the hedrons' filing."
    ),
    rarity="common",
)
_HEDRON_AUDIT.scp_on_play = _hedron_audit_play


# 25. Class-V Reality-Tilt Audit
# Rules text: Opposing breach +3. Your breach +2. Brief 2.
def _reality_tilt_play(obj, state):
    """Opposing breach +3. Your breach +2. Brief 2."""
    s_me = scp.site(state, obj.controller)
    opp = scp._first_opposing_player(state, obj.controller)
    s_me["breach"] = s_me.get("breach", 0) + 2
    s_me["briefing"] = s_me.get("briefing", 0) + 2
    events = [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "reality_tilt_self",
            "breach": s_me["breach"],
            "briefing": s_me["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]
    if opp:
        s_opp = scp.site(state, opp)
        s_opp["breach"] = s_opp.get("breach", 0) + 3
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "reality_tilt_opp_breach",
                "target_player": opp,
                "breach": s_opp["breach"],
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_CLASS_V_REALITY_TILT = _brief(
    _ea_card(
        "Class-V Reality-Tilt Audit",
        CardType.SCP_PROCEDURE,
        red_tape=3,
        clearance=0,
        subtypes={"Audit", "Protocol"},
        text=(
            "Opposing breach +3. Your breach +2. Brief 2. "
            "Approved by the O5 Council. "
            "Seven abstained. "
            "Reality tilted anyway."
        ),
        rarity="mythic",
    ),
    n=2,
)
_CLASS_V_REALITY_TILT.scp_on_play = _reality_tilt_play


# ---------------------------------------------------------------------------
# 4 FACILITIES
# ---------------------------------------------------------------------------


# 26. Containment Site Ash-of-Zendikar
# Rules text: Bonus: research +1. Your Eldrazi anomalies get +1 hazard while
# in this facility.
_SITE_ASH_OF_ZENDIKAR = _ea_card(
    "Containment Site Ash-of-Zendikar",
    CardType.SCP_FACILITY,
    red_tape=2,
    clearance=0,
    subtypes={"Containment Site"},
    text=(
        "Bonus: research +1. Your Eldrazi anomalies get +1 hazard. "
        "Built on reclaimed void-substrate. "
        "The walls absorb the screaming. "
        "Containment integrity: nominal."
    ),
    rarity="rare",
)
# Passive: research bonus handled by engine's facility bonus system.
# TODO: +1 hazard to Eldrazi anomalies while this facility is active — requires
# engine facility aura hook filtering on Eldrazi subtype; flag set below.
_SITE_ASH_OF_ZENDIKAR.scp_facility_bonus = {"research": 1}
_SITE_ASH_OF_ZENDIKAR.scp_eldrazi_hazard_bonus = 1


# 27. Hedron Network Containment Grid
# Rules text: Bonus: contain +1. When you sacrifice an anomaly, gain 1 archive.
def _hedron_grid_sac(obj, state, sacrificed_obj=None):
    """When you sacrifice an anomaly, gain 1 archive."""
    s = scp.site(state, obj.controller)
    archives = s.get("archives", [])
    # TODO: engine archive-gain from sacrifice event not yet wired for
    # facility passives — emit SCP_INCIDENT_RESOLVED with reason="archive_gain".
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hedron_grid_archive_gain",
            "archives_count": len(archives),
        },
        source=obj.id,
        controller=obj.controller,
    )]


_HEDRON_NETWORK_GRID = _ea_card(
    "Hedron Network Containment Grid",
    CardType.SCP_FACILITY,
    red_tape=1,
    clearance=0,
    subtypes={"Containment Site"},
    text=(
        "Bonus: contain +1. When you sacrifice an anomaly, gain 1 archive. "
        "Every stone is a filing cabinet. "
        "Every filing cabinet is a prayer."
    ),
    rarity="uncommon",
)
_HEDRON_NETWORK_GRID.scp_facility_bonus = {"contain": 1}
# TODO: engine facility passive for scp_on_sacrifice not yet hooked;
# attaching as convention placeholder.
_HEDRON_NETWORK_GRID.scp_on_sacrifice = _hedron_grid_sac


# 28. Void Approach Vector Suppression Site
# Rules text: Bonus: research +1. When Annihilation Wave fires, gain 1 archive.
def _void_suppression_aw_fire(obj, state, wave_n=None):
    """When Annihilation Wave fires from any of our anomalies, gain 1 archive."""
    # TODO: engine SCP_BREACH_TICK / Annihilation Wave fire event hook for
    # facility passive triggers not yet wired — emit SCP_INCIDENT_RESOLVED
    # with reason="aw_archive_gain" as placeholder.
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "aw_archive_gain",
            "wave_n": wave_n,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_VOID_SUPPRESSION_SITE = _ea_card(
    "Void Approach Vector Suppression Site",
    CardType.SCP_FACILITY,
    red_tape=2,
    clearance=0,
    subtypes={"Suppression Site"},
    text=(
        "Bonus: research +1. When Annihilation Wave fires, gain 1 archive. "
        "The wave is contained. "
        "The paperwork about the wave is not."
    ),
    rarity="rare",
)
_VOID_SUPPRESSION_SITE.scp_facility_bonus = {"research": 1}
# TODO: hook scp_on_annihilation_wave_fire for facility passive.
_VOID_SUPPRESSION_SITE.scp_on_annihilation_wave_fire = _void_suppression_aw_fire


# 29. Apollyon Ingress Containment Bunker
# Rules text: Bonus: contain +1.
_APOLLYON_BUNKER = _ea_card(
    "Apollyon Ingress Containment Bunker",
    CardType.SCP_FACILITY,
    red_tape=1,
    clearance=0,
    subtypes={"Containment Site"},
    text=(
        "Bonus: contain +1. "
        "Rated for Class-V anomalous incursion. "
        "Rating under review."
    ),
    rarity="uncommon",
)
_APOLLYON_BUNKER.scp_facility_bonus = {"contain": 1}


# ---------------------------------------------------------------------------
# 1 MANDATE
# ---------------------------------------------------------------------------


# 30. Mandate FBN-AVI: Apollyon Vector Inhibition
# Rules text: Mandate. Win when opposing breach ≥ 12 (accelerated public_panic).
def _mandate_avi_check(obj, state):
    """Win condition: check if opposing breach >= 12 each turn."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    s_opp = scp.site(state, opp)
    if s_opp.get("breach", 0) >= 12:
        return [scp.Event(
            type=scp.EventType.SCP_WIN_CONDITION,
            payload={
                "winner": obj.controller,
                "reason": "apollyon_vector_inhibition",
                "loser": opp,
                "opp_breach": s_opp["breach"],
                "alt_win_id": "apollyon_vector_breach_12",
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return []


_MANDATE_AVI = _ea_card(
    "Mandate FBN-AVI: Apollyon Vector Inhibition",
    CardType.SCP_MANDATE,
    red_tape=3,
    clearance=2,
    subtypes={"Mandate"},
    text=(
        "Mandate. Win when opposing breach ≥ 12. "
        "O5 ratification: unanimous. "
        "The public will not be briefed. "
        "The public will not survive being briefed."
    ),
    rarity="mythic",
)
# Engine alt-win contract: `scp_alt_win` is a string key checked by
# `check_scp_victory`. The Eldrazi mandate's flavor is "opposing breach
# >= 12" but the closest existing engine path is `public_panic`
# (archives >= 4 AND any opponent's secrecy <= 6), which fires under
# similar deck states (Annihilation Wave drives both breach up and
# secrecy down). Keeping the bespoke `*_id`/`*_threshold`/`*_metric`
# attributes as analytics-only documentation; the actual win firing
# rides on `scp_alt_win = "public_panic"`.
_MANDATE_AVI.scp_alt_win = "public_panic"
_MANDATE_AVI.scp_alt_win_id = "apollyon_vector_breach_12"
_MANDATE_AVI.scp_alt_win_threshold = 12
_MANDATE_AVI.scp_alt_win_metric = "opposing_breach"
# TODO: engine per-turn alt-win poll hook for mandates not yet implemented
# as a generic hook; attaching to scp_on_turn_end as placeholder.
_MANDATE_AVI.scp_on_turn_end = _mandate_avi_check


# ---------------------------------------------------------------------------
# Aggregate export
# ---------------------------------------------------------------------------


ELDRAZI_APEX_CARDS: list[CardDefinition] = [
    # Anomalies — mythic apex
    _VOID_EATER,            # 1  SCP-FBN-2271 Apollyon-Class Void Eater (Ulamog)
    _HEDRON_TILT,           # 2  SCP-FBN-2272 Apollyon-Class Hedron-Tilt (Kozilek)
    _REALITY_EATER,         # 3  SCP-FBN-2273 Apollyon-Class Reality-Eater (Emrakul)
    # Anomalies — rare
    _CONSCRIPTION_PATTERN,  # 4  SCP-FBN-2280 Eldrazi Conscription Pattern
    _HEDRON_CAGED_TITAN,    # 5  SCP-FBN-2281 Hedron-Caged Titan
    # Anomalies — uncommon
    _VOID_DRONE,            # 6  SCP-FBN-2276 Void Drone, Apollyon-Adjacent
    _HEDRON_FRAGMENT,       # 7  SCP-FBN-2277 Hedron Network Fragment
    _BROOD_TYRANT,          # 8  SCP-FBN-2278 Brood Tyrant Specimen
    _VOID_EEL,              # 9  SCP-FBN-2279 Void Eel
    _VOID_ABERRATION,       # 10 SCP-FBN-2282 Void Aberration
    # Anomalies — common
    _VECTOR_SPAWN,          # 11 SCP-FBN-2274 Apollyon Vector Spawn
    _SCION_PATTERN,         # 12 SCP-FBN-2275 Eldrazi Scion Pattern
    _APOLLYON_INGRESS,      # 13 SCP-FBN-2283 Apollyon-Adjacent Ingress
    _REALITY_HOLE,          # 14 SCP-FBN-2284 Reality-Hole Fragment
    # Personnel
    _RESEARCHER_DRAKE,      # 15 Researcher Drake-Ulamog Pact Interpreter
    _OPERATIVE_CIPHER,      # 16 Operative Kozilek-Liaison "Cipher"
    _EMRAKUL_SPECIALIST,    # 17 Class-A Emrakul Containment Specialist
    _DR_HEDRON_CALIBRATOR,  # 18 Dr. Hedron Calibrator
    _RESEARCHER_DRONE_FIVE, # 19 Researcher Voider "Drone Five"
    _OPERATIVE_HOLLOWING,   # 20 Class-A Operative "Hollowing"
    # Procedures
    _PROTOCOL_HEDRON_ACTIVATION, # 21 Protocol: Hedron Network Activation
    _VOID_BOMBARDMENT,      # 22 Void Bombardment
    _APOLLYON_VECTOR_SACRIFICE,  # 23 Apollyon Vector Sacrifice
    _HEDRON_AUDIT,          # 24 Hedron Audit
    _CLASS_V_REALITY_TILT,  # 25 Class-V Reality-Tilt Audit
    # Facilities
    _SITE_ASH_OF_ZENDIKAR,  # 26 Containment Site Ash-of-Zendikar
    _HEDRON_NETWORK_GRID,   # 27 Hedron Network Containment Grid
    _VOID_SUPPRESSION_SITE, # 28 Void Approach Vector Suppression Site
    _APOLLYON_BUNKER,       # 29 Apollyon Ingress Containment Bunker
    # Mandate
    _MANDATE_AVI,           # 30 Mandate FBN-AVI: Apollyon Vector Inhibition
]

_CARDS = ELDRAZI_APEX_CARDS
