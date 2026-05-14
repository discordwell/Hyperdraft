"""FBN Spirit Archive sub-set — 30 cards.

Euclid-class incorporeal anomalies: spirits, ghosts, ectoplasmic intrusions
filed in the Foundation's spectral archive. MTG spirit references (Kamigawa,
Geist of Saint Traft, Kira Great Glass-Spinner, Yuriko ninja-spirits, Phantom
Tiger, Higure the Still Wind, Ojutai's spirit-host, Mikokoro, Niko Aris shards,
Kaito Shizuki spectral cuts) recast as Euclid ambient hazards.

Composition: 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

Mechanics:
  Leyline Saturation N  — opposing spell-resolution pumps active spirit hazard
  Phylactery Audit X    — memory-holed spirits return for X ethics (recursion)
  Many anomalies stack both: _leyline_saturation(_phylactery_audit(card, X), N)

Alt-win piggybacked onto existing SZB `public_panic`:
  Mandate FBN-SAS fires when archives >= 4 AND opposing secrecy <= 6 while
  Leyline Saturation anomalies are active — identical engine path to SZB
  public_panic but driven by spirit saturation pressure.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import (
    _fbn_card,
    _phylactery_audit,
    _leyline_saturation,
    _brief,
    _mnestic_personnel,
)

_ARCHETYPE = "spirit_archive"

# ---------------------------------------------------------------------------
# Bespoke on-reveal hooks
# ---------------------------------------------------------------------------


def _geist_on_reveal(obj, state):
    """Geist of Saint Traft: on reveal, Brief 1 + opposing secrecy -1."""
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    for pid in state.players:
        if pid != obj.controller:
            scp.site(state, pid)["secrecy"] -= 1
    return [scp.Event(
        type=scp.EventType.SCP_AUDIT,
        payload={
            "actor": obj.id,
            "target": obj.controller,
            "exposure": 1,
            "reason": "geist_spectral_assault",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _yuriko_on_reveal(obj, state):
    """Yuriko-Pattern Ninja-Spirit: on reveal, redact 1 opposing dossier.

    Reaches the game object via state._game (set by Game._connect_subsystems).
    Uses redact_opposing rather than misfile_dossier — misfile requires a
    specific pending-dossier id, whereas redact auto-picks lowest-impact
    cards from each opponent's hand (Yuriko's intent: card-level disruption).
    """
    game = getattr(state, "_game", None)
    if game is None:
        return []
    events = list(scp.redact_opposing(game, obj.controller, 1, source=obj.id))
    events.append(scp.Event(
        type=scp.EventType.SCP_AUDIT,
        payload={
            "actor": obj.id,
            "target": obj.controller,
            "exposure": 0,
            "reason": "yuriko_redact",
        },
        source=obj.id,
        controller=obj.controller,
    ))
    return events


def _hollis_opp_procedure_reveal(obj, state):
    """Dr. Mira Hollis: when opponent resolves a Procedure, gain 1 Brief.

    This is wired as an on_reveal — the engine fires on_reveal hooks when the
    card enters the site. The Brief-grant on opposing-procedure is expressed
    as a site-level subscription via the `scp_on_reveal` attribute; the
    trigger itself is a TODO for the engine's procedure-open intercept.
    For now we grant Brief 1 immediately on reveal as a simplified proxy.
    """
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "hollis_brief_grant",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _ambient_specter_detention_on_contain(obj, state):
    """Ambient Specter Detention Site: when you contain an opposing Anomaly, Leyline Saturation 1 fires.

    Expressed as an on_contain hook on the facility object. Decrement
    scp_suppressed by 1 on all controller anomalies (matching LS semantics).
    """
    # Leyline Saturation 1 manual trigger: -1 suppression on all active anomalies
    for pid, zone in (getattr(state, "scp_pending", None) or {}).items():
        if pid == obj.controller:
            for a_id in (zone or []):
                a = state.objects.get(a_id)
                if a and hasattr(a, "scp_suppressed"):
                    a.scp_suppressed = getattr(a, "scp_suppressed", 0) - 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ambient_specter_detention_leyline",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _sas_mandate_on_reveal(obj, state):
    """Mandate FBN-SAS: on reveal, immediately check public_panic win condition."""
    s = scp.site(state, obj.controller)
    # Engine already handles `public_panic` in _check_win_conditions; the
    # mandate's scp_alt_win = "public_panic" registration is what causes the
    # engine to start watching. We emit a paperwork tick to nudge the checker.
    return [scp.Event(
        type=scp.EventType.SCP_PAPERWORK_TICK,
        payload={
            "player": obj.controller,
            "reason": "sas_mandate_activated",
            "archives": s.get("archives", 0),
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _spirit_containment_array_on_reveal(obj, state):
    """Spirit Containment Array: on reveal, Brief 1 as activation bonus."""
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    return []


def _spectral_audit_effect(obj, state):
    """Class-IV Spectral Audit procedure: return a Phylactery card from scp_forgotten."""
    # Pull first Phylactery-tagged card from scp_forgotten for the controller.
    forgotten = getattr(state, "scp_forgotten", {})
    queue = forgotten.get(obj.controller, [])
    target_idx = None
    for i, c in enumerate(queue):
        if getattr(c, "scp_phylactery_audit", 0) > 0:
            target_idx = i
            break
    if target_idx is not None:
        card = queue.pop(target_idx)
        # Return to dossier queue (existing paperwork queue convention)
        dossier = getattr(state, "scp_dossier", {})
        dossier.setdefault(obj.controller, []).append(card)
        s = scp.site(state, obj.controller)
        s["ethics_debt"] = min(10, s.get("ethics_debt", 0) + 1)
        return [scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "spectral_audit_recur",
                "card": getattr(card, "name", "unknown"),
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return []


def _ghost_mass_audit_effect(obj, state):
    """Ghost-Mass Audit: until end of turn, LS-N anomalies trigger LS N+1; grant Phylactery Audit 1 to all personnel.

    Simplified: immediately grants +1 to all active anomalies' leyline saturation
    (as a suppression bonus) and grants the Phylactery Audit 1 keyword tag to
    all active personnel objects on the controller's site.
    """
    # Boost leyline saturation by 1 on all active anomalies this turn
    for pid, zone in (getattr(state, "scp_pending", None) or {}).items():
        if pid == obj.controller:
            for a_id in (zone or []):
                a = state.objects.get(a_id)
                if a and getattr(getattr(a, "card_def", None), "scp_leyline_saturation", 0) > 0:
                    a.scp_suppressed = getattr(a, "scp_suppressed", 0) - 1  # bonus hazard
    # Grant Phylactery Audit 1 keyword to all personnel this turn
    for p_id in (getattr(state, "scp_personnel", {}) or {}).get(obj.controller, []):
        p = state.objects.get(p_id)
        if p:
            existing_kw = set(getattr(getattr(p, "card_def", None), "scp_keywords", []) or [])
            existing_kw.add("Phylactery Audit 1")
            if p.card_def:
                p.card_def.scp_keywords = sorted(existing_kw)
                p.card_def.scp_phylactery_audit = max(
                    getattr(p.card_def, "scp_phylactery_audit", 0), 1
                )
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ghost_mass_audit",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _phantom_recall_audit_effect(obj, state):
    """Phantom Recall Audit: grant Phylactery Audit 2 to all personnel until end of turn."""
    for p_id in (getattr(state, "scp_personnel", {}) or {}).get(obj.controller, []):
        p = state.objects.get(p_id)
        if p and p.card_def:
            existing_kw = set(getattr(p.card_def, "scp_keywords", []) or [])
            existing_kw.add("Phylactery Audit 2")
            p.card_def.scp_keywords = sorted(existing_kw)
            p.card_def.scp_phylactery_audit = max(
                getattr(p.card_def, "scp_phylactery_audit", 0), 2
            )
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "phantom_recall_audit",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _ecto_saturation_pulse_effect(obj, state):
    """Ectoplasmic Saturation Pulse: Leyline Saturation 1 trigger + redact 1 opposing dossier."""
    # Manual LS1 trigger: -1 suppression on all active anomalies
    for pid, zone in (getattr(state, "scp_pending", None) or {}).items():
        if pid == obj.controller:
            for a_id in (zone or []):
                a = state.objects.get(a_id)
                if a:
                    a.scp_suppressed = getattr(a, "scp_suppressed", 0) - 1
    # Redact 1 opposing dossier — uses redact_opposing (full hand-discard semantics)
    # rather than misfile_dossier (which targets a specific pending-dossier id).
    events: list = []
    game = getattr(state, "_game", None)
    if game is not None:
        events.extend(scp.redact_opposing(game, obj.controller, 1, source=obj.id))
    return events + [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "ecto_saturation_pulse",
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _spectral_containment_sweep_effect(obj, state):
    """Spectral Containment Sweep: contain target opposing Anomaly + Leyline Saturation 1 trigger."""
    # Target the lowest-containment opposing active anomaly
    best = None
    best_val = 999
    for pid, zone in (getattr(state, "scp_pending", None) or {}).items():
        if pid != obj.controller:
            for a_id in (zone or []):
                a = state.objects.get(a_id)
                if a:
                    val = getattr(getattr(a, "card_def", None), "scp_containment", 0) or 0
                    if val < best_val:
                        best_val = val
                        best = a
    if best:
        scp.contain_anomaly(state, obj.controller, best.id)
    # Leyline Saturation 1 trigger
    for pid, zone in (getattr(state, "scp_pending", None) or {}).items():
        if pid == obj.controller:
            for a_id in (zone or []):
                a = state.objects.get(a_id)
                if a:
                    a.scp_suppressed = getattr(a, "scp_suppressed", 0) - 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "spectral_containment_sweep",
        },
        source=obj.id,
        controller=obj.controller,
    )]


# ---------------------------------------------------------------------------
# 13 Anomalies
# ---------------------------------------------------------------------------

# A001: Geist of Saint Traft, Class-IV Spectral Asset — mythic, dual mechanic
_GEIST = _leyline_saturation(
    _phylactery_audit(
        _fbn_card(
            "SCP-FBN-A001: Geist of Saint Traft, Class-IV Spectral Asset",
            CardType.SCP_ANOMALY,
            archetype=_ARCHETYPE,
            containment=5,
            curiosity=3,
            hazard=3,
            red_tape=2,
            subtypes={"Spectral", "Euclid"},
            text=(
                "Leyline Saturation 2. Phylactery Audit 2. "
                "On reveal, Brief 1; opposing secrecy -1. "
                "A geist that follows no warding. The ward team "
                "requested amnestics. The ward team is still requested."
            ),
            rarity="mythic",
            art_prompt=(
                "SCP Foundation containment dossier photo: a translucent armored knight "
                "hovering in a concrete cell, trailing angel-wing ectoplasm, Foundation "
                "biohazard tape in the foreground, sodium-arc lighting, cosmic horror tone, "
                "no text."
            ),
        ),
        x=2,
    ),
    n=2,
)
_GEIST.scp_on_reveal = _geist_on_reveal


# A002: Kira, Great Glass-Spinner Specimen — rare, dual mechanic
_KIRA = _leyline_saturation(
    _phylactery_audit(
        _fbn_card(
            "SCP-FBN-A002: Kira, Great Glass-Spinner Specimen",
            CardType.SCP_ANOMALY,
            archetype=_ARCHETYPE,
            containment=4,
            curiosity=3,
            hazard=2,
            red_tape=1,
            subtypes={"Spectral", "Euclid"},
            text=(
                "Leyline Saturation 1. Phylactery Audit 1. "
                "The first procedure targeting this anomaly each turn automatically fails — "
                "the glass-spinner refracts the paperwork. "
                "O5-9 memo: 'just stop writing memos about it.'"
            ),
            rarity="rare",
        ),
        x=1,
    ),
    n=1,
)


# A003: Phantasmal Image, Class-III Phantom — uncommon, Phylactery only
_PHANTASMAL_IMAGE = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-A003: Phantasmal Image, Class-III Phantom",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Phylactery Audit 1. "
            "On reveal, this anomaly gains the subtypes of target anomaly in play. "
            "The image believes it is the original. The original has no comment."
        ),
        rarity="uncommon",
    ),
    x=1,
)


# A004: Mikokoro, Center of the Sea Specimen — uncommon, Leyline only
_MIKOKORO = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-A004: Mikokoro, Center of the Sea Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Spectral", "Spatial", "Euclid"},
        text=(
            "Leyline Saturation 1. "
            "On reveal, each player gains 1 Brief (the knowledge bleeds equally). "
            "Containment note: the island is currently in sublevel 7. It was not "
            "moved there. It did not arrive by any observable mechanism."
        ),
        rarity="uncommon",
    ),
    n=1,
)


def _mikokoro_on_reveal(obj, state):
    """Mikokoro: each player gains 1 Brief on reveal."""
    for pid in state.players:
        scp.site(state, pid)["briefing"] += 1
    return []


_MIKOKORO.scp_on_reveal = _mikokoro_on_reveal


# A005: Yuriko-Pattern Ninja-Spirit — rare, Phylactery + redact
_YURIKO = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-A005: Yuriko-Pattern Ninja-Spirit",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Phylactery Audit 1. On reveal, redact 1 opposing dossier. "
            "The shadow came first. The ninja is a secondary phenomenon. "
            "The dossier on the shadow has been redacted three times this week."
        ),
        rarity="rare",
    ),
    x=1,
)
_YURIKO.scp_on_reveal = _yuriko_on_reveal


# A006: Phyrexian Negator, Spirit-Pattern — rare, Phylactery 2
_PHYREXIAN_NEGATOR_SPIRIT = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-A006: Phyrexian Negator, Spirit-Pattern",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=4,
        curiosity=2,
        hazard=3,
        red_tape=1,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Phylactery Audit 2. "
            "When this anomaly breaches, you lose 1 archive (the negation is mutual). "
            "The oil is ectoplasmic, not Phyrexian. The distinction has not mattered."
        ),
        rarity="rare",
    ),
    x=2,
)


def _negator_on_breach(obj, state):
    """Phyrexian Negator Spirit: breach costs the controller 1 archive."""
    s = scp.site(state, obj.controller)
    s["archives"] = max(0, s.get("archives", 0) - 1)
    return []


_PHYREXIAN_NEGATOR_SPIRIT.scp_on_breach = _negator_on_breach


# A007: Class-III Wraith Specimen — common, low-cost Phylactery
_WRAITH_SPECIMEN = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-A007: Class-III Wraith Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=2,
        curiosity=1,
        hazard=1,
        red_tape=0,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Phylactery Audit 1. "
            "The cheapest thing in the archive is also the hardest to permanently file. "
            "Containment note: it came back again. We expected this."
        ),
        rarity="common",
    ),
    x=1,
)


# A008: Class-III Memory-Wraith — uncommon, dual mechanic
_MEMORY_WRAITH = _leyline_saturation(
    _phylactery_audit(
        _fbn_card(
            "SCP-FBN-A008: Class-III Memory-Wraith",
            CardType.SCP_ANOMALY,
            archetype=_ARCHETYPE,
            containment=3,
            curiosity=2,
            hazard=2,
            red_tape=1,
            subtypes={"Spectral", "Euclid"},
            text=(
                "Phylactery Audit 1. Leyline Saturation 1. "
                "When this enters from scp_forgotten, opposing secrecy -1. "
                "It remembers everything you've forgotten. Currently that's three researchers."
            ),
            rarity="uncommon",
        ),
        x=1,
    ),
    n=1,
)


def _memory_wraith_on_reveal(obj, state):
    """Memory-Wraith: if returning from scp_forgotten, opposing secrecy -1."""
    # Proxy: check if it was in scp_forgotten (simplified — just secrecy penalty)
    for pid in state.players:
        if pid != obj.controller:
            scp.site(state, pid)["secrecy"] = max(
                0, scp.site(state, pid)["secrecy"] - 1
            )
    return []


_MEMORY_WRAITH.scp_on_reveal = _memory_wraith_on_reveal


# A009: Spectral Cartographer Anomaly — uncommon, Leyline only (high curiosity)
_SPECTRAL_CARTOGRAPHER_ANOMALY = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-A009: Spectral Cartographer Anomaly",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=3,
        curiosity=3,
        hazard=1,
        red_tape=1,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Leyline Saturation 1. "
            "On reveal, Brief 1. Researchable: gain 1 archive on success. "
            "It maps zones that do not appear on any official floor plan. "
            "The maps are accurate."
        ),
        rarity="uncommon",
    ),
    n=1,
)


def _cartographer_anomaly_on_reveal(obj, state):
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    return []


_SPECTRAL_CARTOGRAPHER_ANOMALY.scp_on_reveal = _cartographer_anomaly_on_reveal


def _cartographer_anomaly_on_test(obj, state):
    """Spectral Cartographer: on test success, gain 1 archive.

    Engine signature: (obj, state) -> list[Event]. The on_test hook only
    fires on success (failure has its own scp_on_test_fail hook), so no
    result branching needed. gain_archives takes game (not state).
    """
    game = getattr(state, "_game", None)
    if game is None:
        return []
    return list(scp.gain_archives(game, obj.controller, 1, source=obj.id))


_SPECTRAL_CARTOGRAPHER_ANOMALY.scp_on_test = _cartographer_anomaly_on_test


# A010: Class-IV Specter-Conduit — rare, dual mechanic (high tier)
_SPECTER_CONDUIT = _leyline_saturation(
    _phylactery_audit(
        _fbn_card(
            "SCP-FBN-A010: Class-IV Specter-Conduit",
            CardType.SCP_ANOMALY,
            archetype=_ARCHETYPE,
            containment=5,
            curiosity=3,
            hazard=3,
            red_tape=2,
            subtypes={"Spectral", "Euclid"},
            text=(
                "Leyline Saturation 2. Phylactery Audit 2. "
                "Other Spectral anomalies you control get hazard +1. "
                "The conduit doesn't breach. It helps everything else breach first."
            ),
            rarity="rare",
        ),
        x=2,
    ),
    n=2,
)


# A011: Ectoplasmic Resonance Pattern — common, Phylactery only
_ECTOPLASMIC_RESONANCE = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-A011: Ectoplasmic Resonance Pattern",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=2,
        curiosity=1,
        hazard=2,
        red_tape=0,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Phylactery Audit 1. "
            "When this anomaly breaches, your next Phylactery Audit costs 0 ethics. "
            "The resonance ensures its own retrieval. The ethics office is aware."
        ),
        rarity="common",
    ),
    x=1,
)


# A012: Wraithform Specimen — uncommon, Leyline only
_WRAITHFORM = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-A012: Wraithform Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Leyline Saturation 1. "
            "Containment tests against this anomaly suffer -1 (the form shifts). "
            "It is translucent on even-numbered days. "
            "The calendar has been edited. Containment note: do not edit the calendar."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# A013: Class-IV Spectral Aggregation — rare, Leyline 2 (no Phylactery), mythic-adjacent
_SPECTRAL_AGGREGATION = _leyline_saturation(
    _fbn_card(
        "SCP-FBN-A013: Class-IV Spectral Aggregation",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        containment=5,
        curiosity=3,
        hazard=3,
        red_tape=2,
        subtypes={"Spectral", "Euclid"},
        text=(
            "Leyline Saturation 2. "
            "When this anomaly enters, all other Spectral anomalies you control get "
            "Leyline Saturation 1 until end of turn. "
            "The archive cross-referenced. The entire shelf is now ambient."
        ),
        rarity="rare",
    ),
    n=2,
)


def _aggregation_on_reveal(obj, state):
    """Spectral Aggregation: grant LS1 to all other Spectral anomalies until end of turn."""
    for pid, zone in (getattr(state, "scp_pending", None) or {}).items():
        if pid == obj.controller:
            for a_id in (zone or []):
                if a_id == obj.id:
                    continue
                a = state.objects.get(a_id)
                if a and "Spectral" in (
                    getattr(getattr(a, "card_def", None), "characteristics", None) and
                    getattr(getattr(a, "card_def", None).characteristics, "subtypes", set()) or set()
                ):
                    a.scp_suppressed = getattr(a, "scp_suppressed", 0) - 1
    return []


_SPECTRAL_AGGREGATION.scp_on_reveal = _aggregation_on_reveal


# ---------------------------------------------------------------------------
# 7 Personnel
# ---------------------------------------------------------------------------

# P01: Dr. Mira Hollis, Spectral Medium — rare, clearance 1
_DR_HOLLIS = _fbn_card(
    "Dr. Mira Hollis, Spectral Medium",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    clearance=1,
    red_tape=2,
    skills={"contain": 2, "research": 1},
    subtypes={"Medium", "Foundation"},
    text=(
        "When an opponent resolves a Procedure, gain 1 Brief. "
        "She doesn't hear the anomalies; she hears what they remember. "
        "Most of the time that's worse."
    ),
    rarity="rare",
)
_DR_HOLLIS.scp_on_reveal = _hollis_opp_procedure_reveal


# P02: Researcher Aleko, Ecto-thaumic Surveyor — uncommon
_RESEARCHER_ALEKO = _fbn_card(
    "Researcher Aleko, Ecto-thaumic Surveyor",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    skills={"research": 2},
    subtypes={"Researcher", "Foundation"},
    text=(
        "skills: research 2. "
        "Aleko's surveys are precise. His field notes are not. "
        "The Foundation has accepted this tradeoff."
    ),
    rarity="uncommon",
)


# P03: Operative "Ghosthand" — uncommon
_GHOSTHAND = _fbn_card(
    "Operative \"Ghosthand\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    skills={"contain": 2},
    subtypes={"Operative", "Foundation"},
    text=(
        "skills: contain 2. "
        "He says the name is ironic. The briefing file says he can phase through walls. "
        "Both statements remain under review."
    ),
    rarity="uncommon",
)


# P04: Class-A Spectral Cartographer — common
_SPECTRAL_CARTOGRAPHER_PERSONNEL = _fbn_card(
    "Class-A Spectral Cartographer",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    skills={"research": 1, "contain": 1},
    subtypes={"Researcher", "Foundation"},
    text=(
        "skills: research 1, contain 1. "
        "Maps floors that don't exist yet. "
        "The Foundation uses them. The floors arrive within two weeks."
    ),
    rarity="common",
)


# P05: Researcher "Veilreader" — uncommon
_VEILREADER = _fbn_card(
    "Researcher \"Veilreader\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    skills={"research": 2},
    subtypes={"Researcher", "Foundation"},
    text=(
        "skills: research 2. "
        "She reads between the spectral discharge readings. "
        "What she reads has not been cleared for general circulation."
    ),
    rarity="uncommon",
)


# P06: Operative "Phantom-Hand" — common, zero red tape
_PHANTOM_HAND = _fbn_card(
    "Operative \"Phantom-Hand\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=0,
    skills={"contain": 1},
    subtypes={"Operative", "Foundation"},
    text=(
        "skills: contain 1. "
        "Assigned to the midnight shift. Not out of punishment. "
        "Out of compatibility."
    ),
    rarity="common",
)


# P07: Dr. Sven, Medium-Containment Lead — rare, Phylactery Audit 1 on personnel
_DR_SVEN = _phylactery_audit(
    _fbn_card(
        "Dr. Sven, Medium-Containment Lead",
        CardType.SCP_PERSONNEL,
        archetype=_ARCHETYPE,
        red_tape=1,
        skills={"research": 1, "contain": 2},
        subtypes={"Medium", "Foundation"},
        text=(
            "Phylactery Audit 1. skills: research 1, contain 2. "
            "When this personnel is memory-holed, Phylactery Audit fires at no ethics cost. "
            "Dr. Sven files incident reports from the scp_forgotten zone. "
            "They are dated correctly."
        ),
        rarity="rare",
    ),
    x=1,
)


# ---------------------------------------------------------------------------
# 5 Procedures
# ---------------------------------------------------------------------------

# Pr01: Ectoplasmic Saturation Pulse — uncommon
_ECTO_SAT_PULSE = _leyline_saturation(
    _fbn_card(
        "Ectoplasmic Saturation Pulse",
        CardType.SCP_PROCEDURE,
        archetype=_ARCHETYPE,
        red_tape=1,
        subtypes={"Protocol", "Spectral"},
        text=(
            "Leyline Saturation 1 trigger. Redact 1 opposing dossier. "
            "The saturation is ambient; it doesn't need a source anomaly. "
            "That's the problem."
        ),
        rarity="uncommon",
        effect=_ecto_saturation_pulse_effect,
    ),
    n=1,
)


# Pr02: Phantom Recall Audit — uncommon
_PHANTOM_RECALL_AUDIT = _fbn_card(
    "Phantom Recall Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCHETYPE,
    red_tape=1,
    subtypes={"Protocol", "Spectral"},
    text=(
        "Grant Phylactery Audit 2 to your personnel until end of turn. "
        "The audit doesn't retrieve memories. It retrieves the _slots_ memories left. "
        "The distinction is under debate."
    ),
    rarity="uncommon",
    effect=_phantom_recall_audit_effect,
)


# Pr03: Spectral Containment Sweep — rare
_SPECTRAL_SWEEP = _leyline_saturation(
    _fbn_card(
        "Spectral Containment Sweep",
        CardType.SCP_PROCEDURE,
        archetype=_ARCHETYPE,
        red_tape=2,
        subtypes={"Protocol", "Spectral"},
        text=(
            "Contain target opposing Anomaly. Leyline Saturation 1 trigger. "
            "The sweep works. The saturation spike is considered acceptable side-effect."
        ),
        rarity="rare",
        effect=_spectral_containment_sweep_effect,
    ),
    n=1,
)


# Pr04: Class-IV Spectral Audit — rare
_CLASS_IV_SPECTRAL_AUDIT = _leyline_saturation(
    _fbn_card(
        "Class-IV Spectral Audit",
        CardType.SCP_PROCEDURE,
        archetype=_ARCHETYPE,
        red_tape=2,
        subtypes={"Audit", "Spectral"},
        text=(
            "Return a Phylactery card from scp_forgotten. Pay 1 ethics. "
            "Leyline Saturation 1 trigger. "
            "The audit certifies the retrieval. It does not certify what comes back."
        ),
        rarity="rare",
        effect=_spectral_audit_effect,
    ),
    n=1,
)


# Pr05: Ghost-Mass Audit — mythic
_GHOST_MASS_AUDIT = _phylactery_audit(
    _fbn_card(
        "Ghost-Mass Audit",
        CardType.SCP_PROCEDURE,
        archetype=_ARCHETYPE,
        red_tape=3,
        subtypes={"Audit", "Spectral"},
        text=(
            "Until end of turn, your Leyline Saturation N anomalies trigger "
            "Leyline Saturation N+1. Phylactery Audit 1 granted to all your personnel. "
            "O5-9 classified the meeting. The meeting occurred in the archive. "
            "The archive is now also classified."
        ),
        rarity="mythic",
        effect=_ghost_mass_audit_effect,
    ),
    x=1,
)


# ---------------------------------------------------------------------------
# 4 Facilities
# ---------------------------------------------------------------------------

# F01: Spirit Containment Array — rare
_SPIRIT_CONTAINMENT_ARRAY = _fbn_card(
    "Spirit Containment Array",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=2,
    bonus={"contain": 1, "research": 1},
    subtypes={"Site", "Spectral"},
    text=(
        "Bonus: contain +1, research +1. "
        "Your Leyline Saturation N triggers grant N+1 hazard instead of N. "
        "The array works by absorbing ambient spectral charge. "
        "It is very full."
    ),
    rarity="rare",
)
_SPIRIT_CONTAINMENT_ARRAY.scp_on_reveal = _spirit_containment_array_on_reveal


# F02: Specter Audit Bureau — uncommon
_SPECTER_AUDIT_BUREAU = _fbn_card(
    "Specter Audit Bureau",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=1,
    bonus={"research": 1},
    subtypes={"Site", "Spectral"},
    text=(
        "Bonus: research +1. "
        "Handles all SCP-class spectral specimen paperwork. "
        "Wait times are currently 6-8 weeks. The ghosts are aware."
    ),
    rarity="uncommon",
)


# F03: Ectoplasmic Containment Chamber — uncommon
_ECTO_CONTAINMENT_CHAMBER = _fbn_card(
    "Ectoplasmic Containment Chamber",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=1,
    bonus={"contain": 1},
    subtypes={"Site", "Spectral"},
    text=(
        "Bonus: contain +1. "
        "The chamber seals ectoplasmic discharge at the source. "
        "The source does not always agree it has been sealed."
    ),
    rarity="uncommon",
)


# F04: Ambient Specter Detention Site — rare, on-contain trigger
_AMBIENT_SPECTER_DETENTION = _fbn_card(
    "Ambient Specter Detention Site",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=2,
    bonus={"contain": 1},
    subtypes={"Site", "Spectral"},
    text=(
        "Bonus: contain +1. "
        "When you contain an opposing Anomaly, Leyline Saturation 1 fires. "
        "The detained specters do not seem to mind. "
        "The detained specters seem to be waiting."
    ),
    rarity="rare",
    on_contain=_ambient_specter_detention_on_contain,
)


# ---------------------------------------------------------------------------
# 1 Mandate
# ---------------------------------------------------------------------------

# M01: Mandate FBN-SAS: Spectral Ambient Saturation Doctrine — mythic
# Piggybacks on the existing `public_panic` alt-win (SZB engine).
_MANDATE_SAS = _leyline_saturation(
    _fbn_card(
        "Mandate FBN-SAS: Spectral Ambient Saturation Doctrine",
        CardType.SCP_MANDATE,
        archetype=_ARCHETYPE,
        red_tape=3,
        clearance=2,
        subtypes={"Mandate", "Spectral"},
        text=(
            "Mandate. Win on existing `public_panic`: 4 archives + opposing secrecy <= 6. "
            "Your Leyline Saturation N triggers grant N+1 hazard while this mandate is active. "
            "The doctrine was ratified. The spirits were not consulted. "
            "This is noted in the minutes as 'acceptable oversight.'"
        ),
        rarity="mythic",
    ),
    n=1,
)
_MANDATE_SAS.scp_alt_win = "public_panic"
_MANDATE_SAS.scp_on_reveal = _sas_mandate_on_reveal


# ---------------------------------------------------------------------------
# Final list assembly
# ---------------------------------------------------------------------------

SPIRIT_ARCHIVE_CARDS: list[CardDefinition] = [
    # 13 Anomalies
    _GEIST,
    _KIRA,
    _PHANTASMAL_IMAGE,
    _MIKOKORO,
    _YURIKO,
    _PHYREXIAN_NEGATOR_SPIRIT,
    _WRAITH_SPECIMEN,
    _MEMORY_WRAITH,
    _SPECTRAL_CARTOGRAPHER_ANOMALY,
    _SPECTER_CONDUIT,
    _ECTOPLASMIC_RESONANCE,
    _WRAITHFORM,
    _SPECTRAL_AGGREGATION,
    # 7 Personnel
    _DR_HOLLIS,
    _RESEARCHER_ALEKO,
    _GHOSTHAND,
    _SPECTRAL_CARTOGRAPHER_PERSONNEL,
    _VEILREADER,
    _PHANTOM_HAND,
    _DR_SVEN,
    # 5 Procedures
    _ECTO_SAT_PULSE,
    _PHANTOM_RECALL_AUDIT,
    _SPECTRAL_SWEEP,
    _CLASS_IV_SPECTRAL_AUDIT,
    _GHOST_MASS_AUDIT,
    # 4 Facilities
    _SPIRIT_CONTAINMENT_ARRAY,
    _SPECTER_AUDIT_BUREAU,
    _ECTO_CONTAINMENT_CHAMBER,
    _AMBIENT_SPECTER_DETENTION,
    # 1 Mandate
    _MANDATE_SAS,
]

_CARDS = SPIRIT_ARCHIVE_CARDS
