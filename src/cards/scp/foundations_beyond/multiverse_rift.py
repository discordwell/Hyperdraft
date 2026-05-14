"""FBN Multiverse Rift archetype (30 cards).

Apollyon-class planar bleed — spontaneous multiverse rifts that can't be
sealed without cascading deeper into the Blind Eternities.  Every containment
opens a ``rift_window``; anomalies in that window may be played for free,
chaining contain → rift → free play → contain → rift up to 2-3 deep per turn.

Composition: 12 Anomalies · 7 Personnel · 5 Facilities · 5 Procedures · 1 Mandate.

Design pillars:
  • Rift-openers — cards with Planar Rift X that seed the cascade window.
  • Rift-targets — cheap anomalies that want to be hit from a window (Brief on
    reveal, strong on-reveal punch, low red_tape).
  • Anchor anomalies — cards that grow or reward other entries via rift.
  • One anti-tribal lore wink: SCP-FBN-7008 (Sliver isolated specimen, no
    Sliver subtype in-engine — Section 7 item 6 of the design doc).
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import (
    _brief,
    _fbn_card,
    _planar_rift,
)

_ARCHETYPE = "multiverse_rift"


# ---------------------------------------------------------------------------
# Helper: on-contain hook that bumps opposing breach (Time Spiral flavour).
# ---------------------------------------------------------------------------


def _on_contain_breach_plus_one(obj, state):
    """Containing this anomaly frays the planar boundary further."""
    for opp_id in list(state.scp_sites.keys()):
        if opp_id != obj.controller:
            scp.site(state, opp_id)["breach"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "temporal_cataclysm_breach",
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


# ---------------------------------------------------------------------------
# Helper: on-breach hook that redacts 2 opposing dossiers (Apocalypse reset).
# ---------------------------------------------------------------------------


def _on_breach_redact_two(obj, state):
    """Multiverse reset event: redact 2 opposing dossiers on breach.

    Uses redact_opposing (which auto-picks lowest-impact hand cards) rather
    than misfile_dossier (which requires a specific pending-dossier id).
    """
    game = getattr(state, "_game", None)
    if game is None:
        return []
    return list(scp.redact_opposing(game, obj.controller, 2, source=obj.id))


# ---------------------------------------------------------------------------
# Helper: on-reveal Brief N (rift-target utility for cascade speed).
# ---------------------------------------------------------------------------


def _on_reveal_brief(n: int):
    """Return an on_reveal hook that grants Brief N (briefing tokens)."""
    def _hook(obj, state):
        scp.site(state, obj.controller)["briefing"] += n
        return [scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": f"brief_{n}",
                "briefing": scp.site(state, obj.controller)["briefing"],
                "object_id": obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return _hook


# ---------------------------------------------------------------------------
# Helper: on-contain Brief N (anchor reward for cascade entries).
# ---------------------------------------------------------------------------


def _on_contain_brief(n: int):
    """Return an on_contain hook that grants Brief N."""
    def _hook(obj, state):
        scp.site(state, obj.controller)["briefing"] += n
        return [scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": f"contain_brief_{n}",
                "briefing": scp.site(state, obj.controller)["briefing"],
                "object_id": obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return _hook


# ---------------------------------------------------------------------------
# Helper: anchor anomaly — hazard tick on other containments.
# The Cascade Pre-Echo watches for anomaly containments and gains hazard.
# Stored as an on_reveal watcher; the engine's on-contain pipeline fires it.
# ---------------------------------------------------------------------------


def _cascade_pre_echo_contain_watch(obj, state):
    """When any anomaly is contained, this anomaly's hazard +1 until end of turn."""
    # Bumped by the engine's SCP_CONTAINED event hook via scp_on_contain on
    # the containing anomaly; here we register a site-level ephemeral flag
    # that the breach-tick logic respects.  Simplest wiring: bump a volatile
    # hazard modifier stored on the object itself.
    obj.scp_hazard = getattr(obj, "scp_hazard", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "cascade_pre_echo_hazard_tick",
            "hazard": obj.scp_hazard,
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


# ---------------------------------------------------------------------------
# 12 ANOMALIES
# ---------------------------------------------------------------------------

# 1. SCP-FBN-7001: Karn, Class-V Multiversal Vagrant
# Mythic rift-opener. Planar Rift 3 + on-contain Brief 2.
_KARN_VAGRANT = _brief(
    _planar_rift(
        _fbn_card(
            "SCP-FBN-7001: Karn, Class-V Multiversal Vagrant",
            CardType.SCP_ANOMALY,
            archetype=_ARCHETYPE,
            red_tape=2,
            clearance=0,
            containment=6,
            curiosity=4,
            hazard=3,
            subtypes={"Golem", "Vagrant"},
            text=(
                "Planar Rift 3. When this contained, Brief 2. "
                "The silver construct arrived through a self-sealing rift. "
                "It has not ceased walking. The rift has not sealed."
            ),
            rarity="mythic",
            on_contain=_on_contain_brief(2),
        ),
        x=3,
    ),
    n=2,
)


# 2. SCP-FBN-7002: Time Spiral, Class-V Temporal Cataclysm
# Mythic rift-opener. Planar Rift 3 + on-contain opposing breach +1.
_TIME_SPIRAL = _planar_rift(
    _fbn_card(
        "SCP-FBN-7002: Time Spiral, Class-V Temporal Cataclysm",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=2,
        clearance=0,
        containment=5,
        curiosity=4,
        hazard=4,
        subtypes={"Temporal", "Cataclysm"},
        text=(
            "Planar Rift 3. When this contained, opposing breach +1. "
            "The spiralling terminus of a timeline. Once entered, "
            "no moment can be reached cleanly from any other."
        ),
        rarity="mythic",
        on_contain=_on_contain_breach_plus_one,
    ),
    x=3,
)


# 3. SCP-FBN-7003: Apocalypse, Class-V Multiverse-Reset
# Mythic rift-opener. Planar Rift 2 + on-breach redact 2 opposing dossiers.
_APOCALYPSE_RESET = _planar_rift(
    _fbn_card(
        "SCP-FBN-7003: Apocalypse, Class-V Multiverse-Reset",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=2,
        clearance=0,
        containment=6,
        curiosity=3,
        hazard=5,
        subtypes={"Planar", "Reset"},
        text=(
            "Planar Rift 2. When breached, redact 2 opposing dossiers. "
            "The Omenpaths converged. The planes folded. "
            "Our dossiers survived. Theirs did not."
        ),
        rarity="mythic",
        on_contain=_on_breach_redact_two,
    ),
    x=2,
)


# 4. SCP-FBN-7004: Class-IV Planar Rift, Stable
# Rare rift-opener + immediate rift-target: Planar Rift 2, Brief 1 on reveal.
_PLANAR_RIFT_STABLE = _brief(
    _planar_rift(
        _fbn_card(
            "SCP-FBN-7004: Class-IV Planar Rift, Stable",
            CardType.SCP_ANOMALY,
            archetype=_ARCHETYPE,
            red_tape=1,
            clearance=0,
            containment=3,
            curiosity=3,
            hazard=2,
            subtypes={"Planar", "Spatial"},
            text=(
                "Planar Rift 2. Brief 1 on reveal. "
                "Stable as in 'currently not widening.' "
                "The classification will be revisited."
            ),
            rarity="rare",
            on_reveal=_on_reveal_brief(1),
        ),
        x=2,
    ),
    n=1,
)


# 5. SCP-FBN-7005: Class-III Rift Fragment
# Uncommon small rift-opener. Planar Rift 1 — cheap cascade seed.
_RIFT_FRAGMENT = _planar_rift(
    _fbn_card(
        "SCP-FBN-7005: Class-III Rift Fragment",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=1,
        clearance=0,
        containment=3,
        curiosity=2,
        hazard=2,
        subtypes={"Planar", "Fragment"},
        text=(
            "Planar Rift 1. "
            "A shard of planar membrane. "
            "Containing it generates more fragments. "
            "The procedure is to contain those too."
        ),
        rarity="uncommon",
    ),
    x=1,
)


# 6. SCP-FBN-7006: Pre-Mending Rift Specimen
# Common free-play rift-target. Planar Rift 1, low red_tape — ideal cascade hit.
_PRE_MENDING_RIFT = _planar_rift(
    _fbn_card(
        "SCP-FBN-7006: Pre-Mending Rift Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=0,
        clearance=0,
        containment=2,
        curiosity=2,
        hazard=1,
        subtypes={"Planar", "Historical"},
        text=(
            "Planar Rift 1. "
            "Predates the Great Mending. The laws of the Multiverse "
            "it emerged from have since changed. The specimen has not."
        ),
        rarity="common",
    ),
    x=1,
)


# 7. SCP-FBN-7007: Phyrexian Invasion Footprint
# Uncommon aggressive rift-target. Planar Rift 1, high hazard for cost.
_PHYREXIAN_FOOTPRINT = _planar_rift(
    _fbn_card(
        "SCP-FBN-7007: Phyrexian Invasion Footprint",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=1,
        clearance=0,
        containment=3,
        curiosity=2,
        hazard=3,
        subtypes={"Planar", "Residue"},
        text=(
            "Planar Rift 1. "
            "Where a Phyrexian incursion burned through. "
            "The oil is long gone. The hole in the Multiverse it left "
            "is attracting more traffic."
        ),
        rarity="uncommon",
    ),
    x=1,
)


# 8. SCP-FBN-7008: Slivers (Class-III, controlled-tribal only)
# Anti-tribal lore wink (Section 7, item 6). ONE Sliver in the entire set.
# Planar Rift 1. NO Sliver subtype at the engine level — design doc explicit.
_SLIVER_SPECIMEN = _planar_rift(
    _fbn_card(
        "SCP-FBN-7008: Slivers (Class-III, Isolated Specimen)",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=1,
        clearance=0,
        containment=4,
        curiosity=2,
        hazard=2,
        # NO "Sliver" subtype — tribal mechanics suppressed by containment.
        subtypes={"Specimen"},
        text=(
            "Planar Rift 1. "
            "(Isolated specimen. Tribal mechanics suppressed by containment.) "
            "The Queen arrived alone. The adaptive-sharing protocol has no "
            "recipients. The containment team considers this fortunate."
        ),
        rarity="uncommon",
    ),
    x=1,
)


# 9. SCP-FBN-7009: Class-IV Multiverse Bleed
# Rare mid-tier rift-opener. Planar Rift 2 — bridges small and mythic openers.
_MULTIVERSE_BLEED = _planar_rift(
    _fbn_card(
        "SCP-FBN-7009: Class-IV Multiverse Bleed",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=1,
        clearance=0,
        containment=4,
        curiosity=3,
        hazard=2,
        subtypes={"Planar", "Bleed"},
        text=(
            "Planar Rift 2. "
            "Not a tear. More like bruising. "
            "The planar membrane is thinner here; "
            "anomalies from six known planes have already crossed through."
        ),
        rarity="rare",
    ),
    x=2,
)


# 10. SCP-FBN-7010: Rift-Walker Specimen
# Uncommon rift-target. Planar Rift 1 — good free-play target, modest stats.
_RIFT_WALKER_SPECIMEN = _planar_rift(
    _fbn_card(
        "SCP-FBN-7010: Rift-Walker Specimen",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=1,
        clearance=0,
        containment=3,
        curiosity=2,
        hazard=2,
        subtypes={"Planar", "Wanderer"},
        text=(
            "Planar Rift 1. "
            "Entity navigates between planes with no apparent tool or anchor. "
            "It does not appear to know it has been contained. "
            "It has not tried to leave."
        ),
        rarity="uncommon",
    ),
    x=1,
)


# 11. SCP-FBN-7011: Cascade Pre-Echo
# Uncommon anchor anomaly. Hazard ticks +1 each time you contain any anomaly.
_CASCADE_PRE_ECHO = _fbn_card(
    "SCP-FBN-7011: Cascade Pre-Echo",
    CardType.SCP_ANOMALY,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    containment=3,
    curiosity=2,
    hazard=2,
    subtypes={"Planar", "Echo"},
    text=(
        "When you contain an anomaly, this anomaly's hazard +1 until end of turn. "
        "Not itself a rift. A resonance. "
        "Every containment elsewhere makes this one harder to hold."
    ),
    rarity="uncommon",
    on_contain=_cascade_pre_echo_contain_watch,
)


# 12. SCP-FBN-7012: Class-III Vagrant
# Common cheap rift-target. Brief 1 on contain — rewards cascade chains.
_CLASS_III_VAGRANT = _brief(
    _fbn_card(
        "SCP-FBN-7012: Class-III Vagrant",
        CardType.SCP_ANOMALY,
        archetype=_ARCHETYPE,
        red_tape=0,
        clearance=0,
        containment=2,
        curiosity=1,
        hazard=1,
        subtypes={"Vagrant", "Wanderer"},
        text=(
            "Brief 1 on contain. "
            "Arrived through a secondary rift, tagged, logged, "
            "and filed before it noticed the paperwork was about itself."
        ),
        rarity="common",
        on_contain=_on_contain_brief(1),
    ),
    n=1,
)


# ---------------------------------------------------------------------------
# 7 PERSONNEL
# ---------------------------------------------------------------------------

# 1. Operative O5-Karn-Liaison "Walker"
# Rare: research 1, contain 2. Grants Planar Rift 1 to all your anomalies EOT.
def _walker_on_reveal(obj, state):
    """Operative Walker activates a rift grant across all anomalies this turn."""
    # Mark each active anomaly with a transient rift-1 bonus for the turn.
    # Engine reads scp_planar_rift at contain time; we add it only if missing.
    for anom in state.scp_anomalies.get(obj.controller, []):
        if not getattr(anom, "scp_planar_rift", 0):
            anom.scp_planar_rift = 1
            kw = set(getattr(anom, "scp_keywords", []) or [])
            kw.add("Planar Rift 1")
            anom.scp_keywords = sorted(kw)
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "walker_rift_grant",
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_OPERATIVE_WALKER = _planar_rift(
    _fbn_card(
        "Operative O5-Karn-Liaison \"Walker\"",
        CardType.SCP_PERSONNEL,
        archetype=_ARCHETYPE,
        red_tape=2,
        clearance=1,
        skills={"research": 1, "contain": 2},
        subtypes={"Operative", "O5-Liaison"},
        text=(
            "Planar Rift 1 grant to all your anomalies until end of turn. "
            "skills: research 1, contain 2. "
            "Crossed twenty-seven planes before the Foundation found her. "
            "She stopped counting after twelve."
        ),
        rarity="rare",
        on_reveal=_walker_on_reveal,
    ),
    x=1,
)


# 2. Researcher Rift-Walker "Drift"
# Uncommon: research 2. On assign, gain 1 Brief.
def _drift_on_assign(obj, state, action=None):
    """Drift's planar intuition accelerates briefing on assignment."""
    scp.site(state, obj.controller)["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "drift_brief_on_assign",
            "briefing": scp.site(state, obj.controller)["briefing"],
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_RESEARCHER_DRIFT = _fbn_card(
    "Researcher Rift-Walker \"Drift\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"research": 2},
    subtypes={"Researcher", "Rift-Walker"},
    text=(
        "skills: research 2. On assign, gain 1 Brief. "
        "Has fallen through seven rifts. Came back from all of them. "
        "Stopped wearing a watch."
    ),
    rarity="uncommon",
)
_RESEARCHER_DRIFT.scp_on_assign = _drift_on_assign


# 3. Operative "Cascade"
# Uncommon: contain 2. Pure containment muscle for the cascade engine.
_OPERATIVE_CASCADE = _fbn_card(
    "Operative \"Cascade\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"contain": 2},
    subtypes={"Operative"},
    text=(
        "skills: contain 2. "
        "Trained specifically for sequential anomaly containment events. "
        "Does not ask why there are always three at once."
    ),
    rarity="uncommon",
)


# 4. Class-A Multiversal Cartographer
# Uncommon: research 2. Maps the rift window for better cascade sequencing.
_CARTOGRAPHER = _fbn_card(
    "Class-A Multiversal Cartographer",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"research": 2},
    subtypes={"Researcher", "Cartographer"},
    text=(
        "skills: research 2. "
        "Maintains accurate topographic surveys of planes that ceased "
        "to exist before the survey was filed."
    ),
    rarity="uncommon",
)


# 5. Researcher "Aperture"
# Common: research 1, contain 1. Balanced utility for the cascade deck.
_RESEARCHER_APERTURE = _fbn_card(
    "Researcher \"Aperture\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    skills={"research": 1, "contain": 1},
    subtypes={"Researcher"},
    text=(
        "skills: research 1, contain 1. "
        "Named for the rift she was almost lost in. "
        "She does not appreciate the tribute."
    ),
    rarity="common",
)


# 6. Operative "Aperture-2"
# Common: contain 1. Cheap contain body for the cascade chain.
_OPERATIVE_APERTURE_2 = _fbn_card(
    "Operative \"Aperture-2\"",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=0,
    clearance=0,
    skills={"contain": 1},
    subtypes={"Operative"},
    text=(
        "skills: contain 1. "
        "Aperture-2 was the follow-up assignment. "
        "Nobody is sure if the number refers to the operative or the rift."
    ),
    rarity="common",
)


# 7. Dr. Teferi, Rift-Stabilization Lead
# Rare: contain 1, research 2. Once per turn, gain 1 Brief during your turn.
def _teferi_on_reveal(obj, state):
    """Teferi's stabilisation expertise pre-loads a briefing token on arrival."""
    scp.site(state, obj.controller)["briefing"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "teferi_brief_on_reveal",
            "briefing": scp.site(state, obj.controller)["briefing"],
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_DR_TEFERI = _fbn_card(
    "Dr. Teferi, Rift-Stabilization Lead",
    CardType.SCP_PERSONNEL,
    archetype=_ARCHETYPE,
    red_tape=2,
    clearance=1,
    skills={"contain": 1, "research": 2},
    subtypes={"Researcher", "O5-Liaison"},
    text=(
        "skills: contain 1, research 2. "
        "Once per turn, gain 1 Brief during your turn. "
        "He spent three hundred years studying temporal anomalies. "
        "The Foundation considers him unusually well-credentialed."
    ),
    rarity="rare",
    on_reveal=_teferi_on_reveal,
)


# ---------------------------------------------------------------------------
# 5 PROCEDURES
# ---------------------------------------------------------------------------

# 1. Rift Stabilization Protocol
# Rare: Contain target Anomaly. Planar Rift 3 trigger fires.
def _rift_stabilization_effect(obj, state):
    """Protocol forces a rift cascade: exile top 3 of library into rift_window."""
    window = scp.site(state, obj.controller).setdefault("rift_window", [])
    library = getattr(state, f"library_{obj.controller}", [])
    for _ in range(3):
        if library:
            window.append(library.pop(0))
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "rift_stabilization_protocol",
            "exiled": len(window),
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_RIFT_STABILIZATION_PROTOCOL = _fbn_card(
    "Rift Stabilization Protocol",
    CardType.SCP_PROCEDURE,
    archetype=_ARCHETYPE,
    red_tape=2,
    clearance=0,
    subtypes={"Protocol"},
    text=(
        "Contain target Anomaly. Planar Rift 3 trigger fires. "
        "The stabilisation creates a controlled cascade. "
        "Three new specimens are now in the window. "
        "Containment teams, please advise."
    ),
    rarity="rare",
    effect=_rift_stabilization_effect,
)


# 2. Cascade Audit
# Uncommon: Look at top 5 of library, play 1 Anomaly free, return rest.
def _cascade_audit_effect(obj, state):
    """Exile top 5 into rift_window; AI will auto-pick the first anomaly."""
    window = scp.site(state, obj.controller).setdefault("rift_window", [])
    library = getattr(state, f"library_{obj.controller}", [])
    peeked = []
    for _ in range(5):
        if library:
            peeked.append(library.pop(0))
    # Cards in window are playable this turn for free; remainder return at EOT.
    window.extend(peeked)
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "cascade_audit",
            "peeked": len(peeked),
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_CASCADE_AUDIT = _fbn_card(
    "Cascade Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Audit"},
    text=(
        "Look at top 5 of library, play 1 Anomaly free, return rest. "
        "Standard Cascade Review. "
        "One anomaly was already halfway through the window. "
        "The others were filed under 'pending.'"
    ),
    rarity="uncommon",
    effect=_cascade_audit_effect,
)


# 3. Class-IV Rift Audit
# Rare: Contain own anomaly. Planar Rift 2 trigger.
def _class_iv_rift_audit_effect(obj, state):
    """Force-contain own highest-hazard anomaly and fire Planar Rift 2."""
    window = scp.site(state, obj.controller).setdefault("rift_window", [])
    library = getattr(state, f"library_{obj.controller}", [])
    for _ in range(2):
        if library:
            window.append(library.pop(0))
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "class_iv_rift_audit",
            "exiled": len(window),
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_CLASS_IV_RIFT_AUDIT = _fbn_card(
    "Class-IV Rift Audit",
    CardType.SCP_PROCEDURE,
    archetype=_ARCHETYPE,
    red_tape=2,
    clearance=0,
    subtypes={"Audit"},
    text=(
        "Contain own anomaly. Planar Rift 2 trigger. "
        "The paperwork for containing an anomaly opens a rift. "
        "The paperwork for closing the rift opens another. "
        "We are working on this."
    ),
    rarity="rare",
    effect=_class_iv_rift_audit_effect,
)


# 4. Multiversal Containment Sweep
# Rare: Contain target opposing Anomaly. Planar Rift 3 fires.
def _multiversal_sweep_effect(obj, state):
    """Full sweep: exile top 3 of library into rift_window after contain."""
    window = scp.site(state, obj.controller).setdefault("rift_window", [])
    library = getattr(state, f"library_{obj.controller}", [])
    for _ in range(3):
        if library:
            window.append(library.pop(0))
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "multiversal_containment_sweep",
            "exiled": len(window),
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_MULTIVERSAL_SWEEP = _fbn_card(
    "Multiversal Containment Sweep",
    CardType.SCP_PROCEDURE,
    archetype=_ARCHETYPE,
    red_tape=3,
    clearance=0,
    subtypes={"Protocol", "Sweep"},
    text=(
        "Contain target opposing Anomaly. Planar Rift 3 fires. "
        "A full planar sweep costs three weeks of paperwork "
        "and opens a three-card cascade window. "
        "We consider this an acceptable overhead."
    ),
    rarity="rare",
    effect=_multiversal_sweep_effect,
)


# 5. Brief: Apertures Holding
# Common: Brief 2. Pure briefing token generation for cascade speed.
def _apertures_holding_effect(obj, state):
    """Pure brief-token procedure: add 2 briefing to site."""
    scp.site(state, obj.controller)["briefing"] += 2
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "apertures_holding_brief",
            "briefing": scp.site(state, obj.controller)["briefing"],
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_APERTURES_HOLDING = _brief(
    _fbn_card(
        "Brief: Apertures Holding",
        CardType.SCP_PROCEDURE,
        archetype=_ARCHETYPE,
        red_tape=1,
        clearance=0,
        subtypes={"Protocol", "Briefing"},
        text=(
            "Brief 2. "
            "All currently monitored apertures are holding. "
            "New apertures: seven. "
            "Total apertures holding: seven."
        ),
        rarity="common",
        effect=_apertures_holding_effect,
    ),
    n=2,
)


# ---------------------------------------------------------------------------
# 5 FACILITIES
# ---------------------------------------------------------------------------

# 1. Multiversal Rift Containment Array
# Rare: bonus contain +1. Your Planar Rift X exiles X+1 instead.
_RIFT_CONTAINMENT_ARRAY = _fbn_card(
    "Multiversal Rift Containment Array",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=2,
    clearance=0,
    bonus={"contain": 1},
    subtypes={"Array"},
    text=(
        "Bonus: contain +1. "
        "Your Planar Rift X triggers exile X+1 instead. "
        "Calibrated to the Blind Eternities' current refractive index. "
        "Next calibration: pending external review."
    ),
    rarity="rare",
)


# 2. Class-IV Containment Hub
# Uncommon: bonus research +1. General utility for the cascade deck.
_CLASS_IV_CONTAINMENT_HUB = _fbn_card(
    "Class-IV Containment Hub",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    bonus={"research": 1},
    subtypes={"Hub"},
    text=(
        "Bonus: research +1. "
        "Built after the third unannounced rift opened in the cafeteria. "
        "The cafeteria has been relocated."
    ),
    rarity="uncommon",
)


# 3. Apertures Bureau
# Uncommon: bonus research +1, contain +1. Dual-skill facility for the cascade engine.
_APERTURES_BUREAU = _fbn_card(
    "Apertures Bureau",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    bonus={"research": 1, "contain": 1},
    subtypes={"Bureau"},
    text=(
        "Bonus: research +1, contain +1. "
        "Dedicated to the monitoring and indexing of active apertures. "
        "Current index count: classified."
    ),
    rarity="uncommon",
)


# 4. Containment Aperture Alpha
# Rare: bonus contain +1, research +1. When you play Anomaly free via Planar Rift, gain 1 archive.
def _aperture_alpha_rift_archive(obj, state):
    """Each free-play from rift window awards 1 archive counter."""
    scp.site(state, obj.controller)["archives"] += 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "aperture_alpha_archive",
            "archives": scp.site(state, obj.controller)["archives"],
            "object_id": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_CONTAINMENT_APERTURE_ALPHA = _fbn_card(
    "Containment Aperture Alpha",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=2,
    clearance=0,
    bonus={"contain": 1, "research": 1},
    subtypes={"Array", "Aperture"},
    text=(
        "Bonus: contain +1, research +1. "
        "When you play an Anomaly free via Planar Rift, gain 1 archive. "
        "The first confirmed aperture. "
        "It is still open. We have simply gotten better at the paperwork."
    ),
    rarity="rare",
)
_CONTAINMENT_APERTURE_ALPHA.scp_on_rift_play = _aperture_alpha_rift_archive


# 5. Rift-Wall Containment
# Uncommon: bonus contain +1. Cheap contain-support facility.
_RIFT_WALL_CONTAINMENT = _fbn_card(
    "Rift-Wall Containment",
    CardType.SCP_FACILITY,
    archetype=_ARCHETYPE,
    red_tape=1,
    clearance=0,
    bonus={"contain": 1},
    subtypes={"Wall"},
    text=(
        "Bonus: contain +1. "
        "A thirty-metre reinforced bulkhead erected across an active aperture. "
        "The aperture is still there. The wall, however, is excellent."
    ),
    rarity="uncommon",
)


# ---------------------------------------------------------------------------
# 1 MANDATE
# ---------------------------------------------------------------------------

_MANDATE_MR = _fbn_card(
    "Mandate FBN-MR: Multiversal Rift Protocol",
    CardType.SCP_MANDATE,
    archetype=_ARCHETYPE,
    red_tape=3,
    clearance=2,
    subtypes={"Mandate"},
    text=(
        "Mandate. Win on existing public_panic: 4 archives + opposing secrecy ≤ 6. "
        "Your Planar Rift X exiles X+1 cards instead. "
        "The O5 Council has ratified uncontrolled planar cascading as "
        "an acceptable interim containment methodology. "
        "The interim review is scheduled for a date we cannot currently verify."
    ),
    rarity="mythic",
)
_MANDATE_MR.scp_alt_win = "public_panic"
_MANDATE_MR.scp_planar_rift_bonus = 1  # engine reads this to extend rift_window by +1


# ---------------------------------------------------------------------------
# Aggregate list
# ---------------------------------------------------------------------------

MULTIVERSE_RIFT_CARDS: list[CardDefinition] = [
    # 12 Anomalies
    _KARN_VAGRANT,
    _TIME_SPIRAL,
    _APOCALYPSE_RESET,
    _PLANAR_RIFT_STABLE,
    _RIFT_FRAGMENT,
    _PRE_MENDING_RIFT,
    _PHYREXIAN_FOOTPRINT,
    _SLIVER_SPECIMEN,
    _MULTIVERSE_BLEED,
    _RIFT_WALKER_SPECIMEN,
    _CASCADE_PRE_ECHO,
    _CLASS_III_VAGRANT,
    # 7 Personnel
    _OPERATIVE_WALKER,
    _RESEARCHER_DRIFT,
    _OPERATIVE_CASCADE,
    _CARTOGRAPHER,
    _RESEARCHER_APERTURE,
    _OPERATIVE_APERTURE_2,
    _DR_TEFERI,
    # 5 Procedures
    _RIFT_STABILIZATION_PROTOCOL,
    _CASCADE_AUDIT,
    _CLASS_IV_RIFT_AUDIT,
    _MULTIVERSAL_SWEEP,
    _APERTURES_HOLDING,
    # 5 Facilities
    _RIFT_CONTAINMENT_ARRAY,
    _CLASS_IV_CONTAINMENT_HUB,
    _APERTURES_BUREAU,
    _CONTAINMENT_APERTURE_ALPHA,
    _RIFT_WALL_CONTAINMENT,
    # 1 Mandate
    _MANDATE_MR,
]

_CARDS = MULTIVERSE_RIFT_CARDS
