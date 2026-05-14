"""Phyrexian Strain (FBN) — Keter biomechanical assimilation sub-set.

30 cards for the `phyrexian_strain` archetype of Foundations Beyond.
Theme: The SCP Foundation has classified the Phyrexian Praetors and their
oil-seeded brood as Keter-class biomechanical contagion entities. The deck
weaponises *compleation* — a slow-burn counter system that steals opposing
Personnel at 3 counters — and fortifies its own Mnestic researchers as anchors
that resist the cognitive-rewrite component of the strain.

Composition (30 total):
- 13 Anomalies (3 mythic Praetors, 2 rare escalation, 5 uncommon support,
  3 common carrier/spawn)
- 7 Personnel (2 rare Mnestic leads, 3 uncommon specialists, 2 common agents)
- 4 Facilities (2 rare, 1 uncommon, 1 common)
- 5 Procedures (2 rare, 2 uncommon, 1 rare audit)
- 1 Mandate (mythic, alt-win compleation_overrun)

Alt-win condition: `compleation_overrun` — when 3+ opposing Personnel have
been compleated (control-swapped) by you this game, you win at the end of
your next turn. Registered via `card.scp_alt_win = "compleation_overrun"`.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import (
    _brief,
    _compleation,
    _fbn_card,
    _mnestic_personnel,
    _with_fbn_metadata,
)

_ARCH = "phyrexian_strain"

# ---------------------------------------------------------------------------
# Internal factory helper
# ---------------------------------------------------------------------------


def _ps_card(
    name: str,
    card_type: CardType,
    **kwargs,
) -> CardDefinition:
    """Create a card, stamp FBN metadata, pin the phyrexian_strain archetype."""
    art_prompt = kwargs.pop("art_prompt", None)
    card = scp.make_scp_card(name, card_type, **kwargs)
    return _with_fbn_metadata(
        card,
        archetype=_ARCH,
        art_prompt=art_prompt or (
            f"Original SCP-inspired trading card art for {name}: "
            "a Phyrexian Praetor or oil-contaminated entity inside a Foundation "
            "maximum-containment cell — sterile concrete architecture under sodium-arc "
            "light, Phyrexian oil sheen and biomechanical tendrils visible, redacted "
            "dossiers and biohazard overlays, dread-bureaucratic tone, no text, no logos, "
            "no card frames, high-detail digital painting."
        ),
    )


# ---------------------------------------------------------------------------
# 13 ANOMALIES
# ---------------------------------------------------------------------------

# ── Mythic Praetor trio ──────────────────────────────────────────────────


# C001. SCP-FBN-1140: Yawgmoth-Pattern Strain
# Rules text: Compleation Vector 2. When this Anomaly breaches, place 1
# compleation counter on each opposing Personnel.
def _yawgmoth_breach(obj, state):
    """On breach, place 1 compleation counter on every opposing personnel."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    events = []
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    for pid in list(opp_personnel):
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue  # Mnestic personnel are immune
        counters = s_opp.get(f"compleation_{pid}", 0) + 1
        s_opp[f"compleation_{pid}"] = counters
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "yawgmoth_breach_compleation",
                "target_personnel": pid,
                "compleation_counters": counters,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_C001 = _compleation(
    _ps_card(
        "SCP-FBN-1140: Yawgmoth-Pattern Strain",
        CardType.SCP_ANOMALY,
        containment=5,
        curiosity=4,
        hazard=4,
        red_tape=2,
        clearance=0,
        subtypes={"Phyrexian", "Praetor", "Keter"},
        text=(
            "Compleation Vector 2. When this Anomaly breaches, place 1 "
            "compleation counter on each opposing Personnel. "
            "He did not invade. He was already in the water supply."
        ),
        rarity="mythic",
    ),
    n=2,
)
_C001.scp_on_breach = _yawgmoth_breach


# C002. SCP-FBN-1141: Atraxa, Praetors' Conduit
# Rules text: Compleation Vector 1. On reveal, place 1 compleation counter on
# each opposing Personnel.
def _atraxa_reveal(obj, state):
    """On reveal, place 1 compleation counter on each opposing personnel."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    events = []
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    for pid in list(opp_personnel):
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue
        counters = s_opp.get(f"compleation_{pid}", 0) + 1
        s_opp[f"compleation_{pid}"] = counters
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "atraxa_reveal_compleation",
                "target_personnel": pid,
                "compleation_counters": counters,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_C002 = _compleation(
    _ps_card(
        "SCP-FBN-1141: Atraxa, Praetors' Conduit",
        CardType.SCP_ANOMALY,
        containment=6,
        curiosity=4,
        hazard=3,
        red_tape=2,
        clearance=0,
        subtypes={"Phyrexian", "Praetor", "Keter"},
        text=(
            "Compleation Vector 1. On reveal, place 1 compleation counter on "
            "each opposing Personnel. "
            "She spreads not by violence but by touch. "
            "She has touched everything."
        ),
        rarity="mythic",
    ),
    n=1,
)
_C002.scp_on_reveal = _atraxa_reveal


# C003. SCP-FBN-1145: Elesh Norn, Mother of Machines
# Rules text: Compleation Vector 1. Your other Compleation Vector anomalies
# get +1 to Compleation Vector.
def _elesh_norn_etb(obj, state):
    """On entering play, boost all other Compleation Vector anomalies by +1 N."""
    s_me = scp.site(state, obj.controller)
    active_anomalies = s_me.get("active_anomalies", [])
    boosted = []
    for aid in list(active_anomalies):
        anom_obj = state.objects.get(aid)
        if anom_obj is None or anom_obj.id == obj.id:
            continue
        card_def = getattr(anom_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_compleation_vector", 0) >= 1:
            # Increment the runtime compleation vector attribute
            current = getattr(anom_obj, "scp_compleation_vector_bonus", 0)
            anom_obj.scp_compleation_vector_bonus = current + 1
            boosted.append(aid)
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "elesh_norn_cv_boost",
            "boosted_anomalies": boosted,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C003 = _compleation(
    _ps_card(
        "SCP-FBN-1145: Elesh Norn, Mother of Machines",
        CardType.SCP_ANOMALY,
        containment=6,
        curiosity=3,
        hazard=3,
        red_tape=2,
        clearance=0,
        subtypes={"Phyrexian", "Praetor", "Keter"},
        text=(
            "Compleation Vector 1. Your other Compleation Vector anomalies "
            "get +1 to Compleation Vector. "
            "She does not command. She completes."
        ),
        rarity="mythic",
    ),
    n=1,
)
_C003.scp_on_reveal = _elesh_norn_etb


# ── Rare Praetor anomalies ─────────────────────────────────────────────────


# C004. SCP-FBN-1142: Sheoldred, Whispering Strain
# Rules text: Compleation Vector 1. When an opposing Personnel becomes
# compleated, draw 1 paperwork.
def _sheoldred_compleat_draw(obj, state, compleated_id=None):
    """When an opposing Personnel is compleated, draw 1 paperwork."""
    return [scp.Event(
        type=scp.EventType.SCP_PAPERWORK_TICK,
        payload={
            "player": obj.controller,
            "reason": "sheoldred_compleat_draw",
            "count": 1,
            "compleated_personnel": compleated_id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C004 = _compleation(
    _ps_card(
        "SCP-FBN-1142: Sheoldred, Whispering Strain",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=3,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Phyrexian", "Praetor"},
        text=(
            "Compleation Vector 1. When an opposing Personnel becomes compleated, "
            "draw 1 paperwork. "
            "Every personnel file added to the roster is a whisper answered."
        ),
        rarity="rare",
    ),
    n=1,
)
_C004.scp_on_opponent_compleated = _sheoldred_compleat_draw


# C005. SCP-FBN-1143: Vorinclex, Bio-Engineer Specimen
# Rules text: Compleation Vector 2. Compleation counters tick at 2× rate on
# opposing personnel with skill 3+.
_C005 = _compleation(
    _ps_card(
        "SCP-FBN-1143: Vorinclex, Bio-Engineer Specimen",
        CardType.SCP_ANOMALY,
        containment=5,
        curiosity=3,
        hazard=4,
        red_tape=2,
        clearance=0,
        subtypes={"Phyrexian", "Praetor"},
        text=(
            "Compleation Vector 2. Compleation counters tick at 2× rate on "
            "opposing personnel with skill 3+. "
            "It targets the strong first. "
            "The strong become the strain."
        ),
        rarity="rare",
    ),
    n=2,
)
# Engine reads scp_compleation_double_on_skill_threshold to apply double-rate
# ticking for high-skill opposing personnel.
_C005.scp_compleation_double_on_skill_threshold = 3


# C006. SCP-FBN-1144: Jin-Gitaxias, Cognitive Vector
# Rules text: Compleation Vector 1. When a Personnel is compleated, opposing
# player discards 1 paperwork.
def _jin_gitaxias_compleat_discard(obj, state, compleated_id=None):
    """When any Personnel is compleated, opposing player discards 1 paperwork."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    s_opp = scp.site(state, opp)
    hand = s_opp.get("hand", [])
    if not hand:
        return []
    # Discard top paperwork (heuristic: last card)
    discarded = hand.pop()
    s_opp["hand"] = hand
    s_opp.setdefault("discard", []).append(discarded)
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "jin_gitaxias_discard",
            "target_player": opp,
            "discarded": discarded,
            "compleated_personnel": compleated_id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C006 = _compleation(
    _ps_card(
        "SCP-FBN-1144: Jin-Gitaxias, Cognitive Vector",
        CardType.SCP_ANOMALY,
        containment=5,
        curiosity=5,
        hazard=2,
        red_tape=2,
        clearance=0,
        subtypes={"Phyrexian", "Praetor"},
        text=(
            "Compleation Vector 1. When a Personnel is compleated, opposing "
            "player discards 1 paperwork. "
            "The cognitive rewrite is thorough. "
            "Their filing system is now his."
        ),
        rarity="rare",
    ),
    n=1,
)
_C006.scp_on_opponent_compleated = _jin_gitaxias_compleat_discard


# ── Uncommon support anomalies ─────────────────────────────────────────────


# C007. SCP-FBN-1138: The Compleated Liaison
# Rules text: Compleation Vector 1.
_C007 = _compleation(
    _ps_card(
        "SCP-FBN-1138: The Compleated Liaison",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=3,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Phyrexian", "Humanoid"},
        text=(
            "Compleation Vector 1. "
            "Personnel report it is cooperative. "
            "Personnel did not define cooperative the same way before exposure."
        ),
        rarity="uncommon",
    ),
    n=1,
)


# C008. SCP-FBN-1146: Urabrask, Combustion Vector
# Rules text: Compleation Vector 1. When this anomaly breaches, opposing
# personnel with skill ≤2 become compleated immediately.
def _urabrask_breach(obj, state):
    """On breach, immediately compleat opposing personnel with skill ≤2."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    events = []
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    for pid in list(opp_personnel):
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue
        # Check total skill
        skills = getattr(card_def, "skills", {}) if card_def else {}
        total_skill = sum(skills.values()) if skills else 0
        if total_skill <= 2:
            # Immediately compleat: set counters to 3
            s_opp[f"compleation_{pid}"] = 3
            events.append(scp.Event(
                type=scp.EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": obj.controller,
                    "reason": "urabrask_breach_instant_compleat",
                    "target_personnel": pid,
                    "compleation_counters": 3,
                },
                source=obj.id,
                controller=obj.controller,
            ))
    return events


_C008 = _compleation(
    _ps_card(
        "SCP-FBN-1146: Urabrask, Combustion Vector",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=4,
        red_tape=1,
        clearance=0,
        subtypes={"Phyrexian", "Praetor"},
        text=(
            "Compleation Vector 1. When this anomaly breaches, opposing "
            "personnel with skill ≤2 become compleated immediately. "
            "The forge operates without mercy or pause."
        ),
        rarity="uncommon",
    ),
    n=1,
)
_C008.scp_on_breach = _urabrask_breach


# C009. SCP-FBN-1147: Skithiryx-Class Vector Carrier
# Rules text: Compleation Vector 1. When a Personnel becomes compleated, gain
# 1 Brief.
def _skithiryx_compleat_brief(obj, state, compleated_id=None):
    """When any Personnel is compleated, gain 1 Brief (briefing +1)."""
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "skithiryx_compleat_brief",
            "briefing": s["briefing"],
            "compleated_personnel": compleated_id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C009 = _brief(
    _compleation(
        _ps_card(
            "SCP-FBN-1147: Skithiryx-Class Vector Carrier",
            CardType.SCP_ANOMALY,
            containment=3,
            curiosity=3,
            hazard=3,
            red_tape=1,
            clearance=0,
            subtypes={"Phyrexian", "Dragon", "Carrier"},
            text=(
                "Compleation Vector 1. When a Personnel becomes compleated, "
                "gain 1 Brief. "
                "The dragon does not breathe fire. "
                "It breathes paperwork-grade biohazard."
            ),
            rarity="uncommon",
        ),
        n=1,
    ),
    n=1,
)
_C009.scp_on_opponent_compleated = _skithiryx_compleat_brief


# C010. SCP-FBN-1148: The Phyresis Engine
# Rules text: Compleation Vector 1. Compleation counters do not decay between
# turns.
_C010 = _compleation(
    _ps_card(
        "SCP-FBN-1148: The Phyresis Engine",
        CardType.SCP_ANOMALY,
        containment=4,
        curiosity=4,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Phyrexian", "Artifact", "Engine"},
        text=(
            "Compleation Vector 1. Compleation counters do not decay between turns. "
            "Patience. The oil does not evaporate."
        ),
        rarity="uncommon",
    ),
    n=1,
)
# Engine reads scp_compleation_no_decay to suppress end-of-turn counter removal.
_C010.scp_compleation_no_decay = True


# C011. SCP-FBN-1149: Memnarch-Pattern Aberration
# Rules text: Compleation Vector 1. On contain, gain 1 archive.
def _memnarch_contain(obj, state):
    """On contain, gain 1 archive."""
    return [scp.Event(
        type=scp.EventType.SCP_ARCHIVE_GAINED,
        payload={
            "player": obj.controller,
            "amount": 1,
            "archives": 1,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C011 = _compleation(
    _ps_card(
        "SCP-FBN-1149: Memnarch-Pattern Aberration",
        CardType.SCP_ANOMALY,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Phyrexian", "Artifact", "Aberration"},
        text=(
            "Compleation Vector 1. On contain, gain 1 archive. "
            "Containment is merely a different kind of assimilation."
        ),
        rarity="uncommon",
    ),
    n=1,
)
_C011.scp_on_contain = _memnarch_contain


# ── Common carrier anomalies ──────────────────────────────────────────────


# C012. SCP-FBN-1150: Phyrexian Negator
# Rules text: When you compleat an opposing Personnel, suppress this Anomaly's
# next breach.
def _negator_compleat_suppress(obj, state, compleated_id=None):
    """When you compleat an opposing Personnel, suppress this anomaly's next breach."""
    # Set a one-shot suppress flag on the object itself
    obj.scp_suppress_next_breach = True
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "negator_suppress_next_breach",
            "anomaly_id": obj.id,
            "compleated_personnel": compleated_id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C012 = _ps_card(
    "SCP-FBN-1150: Phyrexian Negator",
    CardType.SCP_ANOMALY,
    containment=2,
    curiosity=2,
    hazard=2,
    red_tape=0,
    clearance=0,
    subtypes={"Phyrexian", "Negator"},
    text=(
        "When you compleat an opposing Personnel, suppress this Anomaly's next breach. "
        "Negotiation was never on the table. "
        "We put it on the table. It removed the table."
    ),
    rarity="common",
)
_C012.scp_on_you_compleated = _negator_compleat_suppress


# C013. SCP-FBN-1151: Compleation Vector Spawn
# Rules text: Compleation Vector 1.
_C013 = _compleation(
    _ps_card(
        "SCP-FBN-1151: Compleation Vector Spawn",
        CardType.SCP_ANOMALY,
        containment=2,
        curiosity=2,
        hazard=1,
        red_tape=0,
        clearance=0,
        subtypes={"Phyrexian", "Spawn"},
        text=(
            "Compleation Vector 1. "
            "Sub-object of SCP-FBN-1140. "
            "Inert when isolated. "
            "Inert is not contained."
        ),
        rarity="common",
    ),
    n=1,
)


# ---------------------------------------------------------------------------
# 7 PERSONNEL
# ---------------------------------------------------------------------------


# C014. Dr. Kassandra Volkov, Mnestic Quarantine Lead
# Rules text: Mnestic. skills: contain 2, research 1. When an opposing
# Compleation Vector anomaly enters play, gain 1 Brief.
def _volkov_cv_etb(obj, state, entering_obj=None):
    """When an opposing Compleation Vector anomaly enters play, gain 1 Brief."""
    if entering_obj is not None:
        card_def = getattr(entering_obj, "card_def", None)
        entering_controller = getattr(entering_obj, "controller", None)
        if entering_controller == obj.controller:
            return []  # Must be opposing
        cv = getattr(card_def, "scp_compleation_vector", 0) if card_def else 0
        if cv < 1:
            return []
    s = scp.site(state, obj.controller)
    s["briefing"] = s.get("briefing", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "volkov_cv_etb_brief",
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C014 = _mnestic_personnel(
    _ps_card(
        "Dr. Kassandra Volkov, Mnestic Quarantine Lead",
        CardType.SCP_PERSONNEL,
        red_tape=2,
        clearance=1,
        skills={"contain": 2, "research": 1},
        subtypes={"Researcher", "Specialist", "Mnestic"},
        text=(
            "Mnestic. skills: contain 2, research 1. "
            "When an opposing Compleation Vector anomaly enters play, gain 1 Brief. "
            "She has read every strain profile. None of them frightened her. "
            "The last one came close."
        ),
        rarity="rare",
    )
)
_C014.scp_on_anomaly_enter = _volkov_cv_etb


# C015. Researcher Aramis, Vector Specialist
# Rules text: skills: research 2. When you compleat an opposing Personnel,
# place 1 extra compleation counter on another opposing personnel.
def _aramis_compleat_spread(obj, state, compleated_id=None):
    """When you compleat an opposing Personnel, place 1 extra counter on another."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    candidates = []
    for pid in list(opp_personnel):
        if pid == compleated_id:
            continue
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue
        candidates.append(pid)
    if not candidates:
        return []
    # Target highest-skill candidate (heuristic)
    def _skill_total(pid):
        o = state.objects.get(pid)
        cd = getattr(o, "card_def", None) if o else None
        skills = getattr(cd, "skills", {}) if cd else {}
        return sum(skills.values()) if skills else 0

    target = max(candidates, key=_skill_total)
    counters = s_opp.get(f"compleation_{target}", 0) + 1
    s_opp[f"compleation_{target}"] = counters
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "aramis_spread_compleation",
            "target_personnel": target,
            "compleation_counters": counters,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C015 = _ps_card(
    "Researcher Aramis, Vector Specialist",
    CardType.SCP_PERSONNEL,
    red_tape=1,
    clearance=0,
    skills={"research": 2},
    subtypes={"Researcher"},
    text=(
        "skills: research 2. When you compleat an opposing Personnel, place "
        "1 extra compleation counter on another opposing personnel. "
        "She maps transmission vectors. "
        "She has mapped herself into all of them."
    ),
    rarity="uncommon",
)
_C015.scp_on_you_compleated = _aramis_compleat_spread


# C016. Dr. Linna Halle, Phyresis Containment
# Rules text: Mnestic. skills: contain 2. Compleation counters on this
# personnel cannot increase.
_C016 = _mnestic_personnel(
    _ps_card(
        "Dr. Linna Halle, Phyresis Containment",
        CardType.SCP_PERSONNEL,
        red_tape=1,
        clearance=0,
        skills={"contain": 2},
        subtypes={"Researcher", "Specialist", "Mnestic"},
        text=(
            "Mnestic. skills: contain 2. "
            "Compleation counters on this personnel cannot increase. "
            "She takes the inoculation quarterly. "
            "She has since forgotten what quarterly means."
        ),
        rarity="uncommon",
    )
)
# Engine reads scp_compleation_immune to prevent counter increments on this object.
_C016.scp_compleation_immune = True


# C017. Operative O5-3, Strain Containment Lead
# Rules text: Mnestic. skills: contain 1, research 2. Once per turn, remove 1
# compleation counter from any of your Personnel.
def _o5_3_remove_counter(obj, state, target_id=None):
    """Once per turn, remove 1 compleation counter from a friendly personnel."""
    s = scp.site(state, obj.controller)
    # Track once-per-turn
    if s.get("o5_3_used_this_turn", False):
        return []
    s["o5_3_used_this_turn"] = True
    # Find a friendly personnel with the highest compleation counters
    my_personnel = s.get("personnel", [])
    best_pid = None
    best_count = 0
    for pid in my_personnel:
        cnt = s.get(f"compleation_{pid}", 0)
        if cnt > best_count:
            best_count = cnt
            best_pid = pid
    if best_pid is None or best_count == 0:
        return []
    s[f"compleation_{best_pid}"] = best_count - 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "o5_3_remove_compleation",
            "target_personnel": best_pid,
            "compleation_counters": best_count - 1,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C017 = _mnestic_personnel(
    _ps_card(
        "Operative O5-3, Strain Containment Lead",
        CardType.SCP_PERSONNEL,
        red_tape=2,
        clearance=1,
        skills={"contain": 1, "research": 2},
        subtypes={"Operative", "O5-Council", "Mnestic"},
        text=(
            "Mnestic. skills: contain 1, research 2. "
            "Once per turn, remove 1 compleation counter from any of your Personnel. "
            "He reviews the counter logs each morning. "
            "He has begun reviewing them twice."
        ),
        rarity="rare",
    )
)
_C017.scp_on_activate = _o5_3_remove_counter


# C018. Researcher Drei, Compleation Cartographer
# Rules text: skills: research 1. On assign, scry top 2 of your library.
def _drei_assign(obj, state, task: str) -> list:
    """On assign, scry top 2 of the controller's library."""
    # TODO: engine library-scry primitive not yet a first-class procedure event;
    # emitting SCP_INCIDENT_RESOLVED with reason="scry_2" as placeholder.
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "drei_assign_scry",
            "scry_depth": 2,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C018 = _ps_card(
    "Researcher Drei, Compleation Cartographer",
    CardType.SCP_PERSONNEL,
    red_tape=1,
    clearance=0,
    skills={"research": 1},
    subtypes={"Researcher"},
    text=(
        "skills: research 1. On assign, scry top 2 of your library. "
        "He makes maps of things that should not be mapped. "
        "The maps are accurate."
    ),
    rarity="common",
)
_C018.scp_on_assign = _drei_assign


# C019. Class-A Operative "Nailbiter"
# Rules text: skills: contain 1. Mnestic.
_C019 = _mnestic_personnel(
    _ps_card(
        "Class-A Operative \"Nailbiter\"",
        CardType.SCP_PERSONNEL,
        red_tape=0,
        clearance=0,
        skills={"contain": 1},
        subtypes={"Class-A", "Operative", "Mnestic"},
        text=(
            "skills: contain 1. Mnestic. "
            "She has survived six Class-IV breaches. "
            "She remembers all of them. "
            "That is the problem."
        ),
        rarity="common",
    )
)


# C020. Dr. Volker Tiede, Praetor Specialist
# Rules text: skills: research 2, contain 1. When you compleat an opposing
# Personnel, gain 1 clearance.
def _tiede_compleat_clearance(obj, state, compleated_id=None):
    """When you compleat an opposing Personnel, gain 1 clearance."""
    s = scp.site(state, obj.controller)
    s["clearance"] = s.get("clearance", 0) + 1
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "tiede_compleat_clearance",
            "clearance": s["clearance"],
            "compleated_personnel": compleated_id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C020 = _ps_card(
    "Dr. Volker Tiede, Praetor Specialist",
    CardType.SCP_PERSONNEL,
    red_tape=2,
    clearance=1,
    skills={"research": 2, "contain": 1},
    subtypes={"Researcher", "Specialist"},
    text=(
        "skills: research 2, contain 1. When you compleat an opposing Personnel, "
        "gain 1 clearance. "
        "Every compleation event is, technically, a successful containment. "
        "He noted this in his report."
    ),
    rarity="uncommon",
)
_C020.scp_on_you_compleated = _tiede_compleat_clearance


# ---------------------------------------------------------------------------
# 5 PROCEDURES
# ---------------------------------------------------------------------------


# C021. Class-A Mnestic Inoculation, Pattern: Yawgmoth-Resistant
# Rules text: Grant Mnestic to up to 2 of your Personnel until end of turn.
# Remove all compleation counters from those personnel.
def _mnestic_inoculation_play(obj, state):
    """Grant Mnestic to up to 2 personnel; remove all compleation counters."""
    s = scp.site(state, obj.controller)
    my_personnel = s.get("personnel", [])
    # Prioritise personnel with the most compleation counters (they need it most)
    candidates = sorted(
        [p for p in my_personnel if state.objects.get(p) is not None],
        key=lambda pid: s.get(f"compleation_{pid}", 0),
        reverse=True,
    )
    targets = candidates[:2]
    events = []
    for pid in targets:
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        # Grant Mnestic for the turn
        pers_obj.scp_mnestic_until_eot = True
        # Remove all compleation counters
        removed = s.get(f"compleation_{pid}", 0)
        s[f"compleation_{pid}"] = 0
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "mnestic_inoculation",
                "target_personnel": pid,
                "counters_removed": removed,
                "mnestic_granted_until_eot": True,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_C021 = _mnestic_personnel(
    _ps_card(
        "Class-A Mnestic Inoculation, Pattern: Yawgmoth-Resistant",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=0,
        subtypes={"Protocol", "Inoculation"},
        text=(
            "Grant Mnestic to up to 2 of your Personnel until end of turn. "
            "Remove all compleation counters from those personnel. "
            "Effective for 24 hours. Re-administer before exposure."
        ),
        rarity="rare",
    )
)
_C021.scp_on_play = _mnestic_inoculation_play


# C022. Containment Breach Reversal: Phyresis Quarantine
# Rules text: Remove 2 compleation counters from target Personnel you control.
def _phyresis_quarantine_play(obj, state):
    """Remove 2 compleation counters from the friendly personnel with the most."""
    s = scp.site(state, obj.controller)
    my_personnel = s.get("personnel", [])
    # Target the personnel with the most compleation counters
    best_pid = None
    best_count = 0
    for pid in my_personnel:
        cnt = s.get(f"compleation_{pid}", 0)
        if cnt > best_count:
            best_count = cnt
            best_pid = pid
    if best_pid is None:
        return []
    new_count = max(0, best_count - 2)
    s[f"compleation_{best_pid}"] = new_count
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "phyresis_quarantine",
            "target_personnel": best_pid,
            "counters_removed": best_count - new_count,
            "compleation_counters": new_count,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C022 = _ps_card(
    "Containment Breach Reversal: Phyresis Quarantine",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    clearance=0,
    subtypes={"Protocol", "Quarantine"},
    text=(
        "Remove 2 compleation counters from target Personnel you control. "
        "The oil does not come out. "
        "The paperwork says it does."
    ),
    rarity="uncommon",
)
_C022.scp_on_play = _phyresis_quarantine_play


# C023. Praetor Pact Audit
# Rules text: Compleat target opposing Personnel with the highest skill.
# (Counter goes immediately to 3.)
def _praetor_pact_audit_play(obj, state):
    """Immediately compleat the opposing personnel with the highest total skill."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    candidates = []
    for pid in list(opp_personnel):
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue
        skills = getattr(card_def, "skills", {}) if card_def else {}
        total_skill = sum(skills.values()) if skills else 0
        candidates.append((pid, total_skill))
    if not candidates:
        return []
    # Pick highest skill
    target_pid, _ = max(candidates, key=lambda x: x[1])
    s_opp[f"compleation_{target_pid}"] = 3
    return [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "praetor_pact_audit_compleat",
            "target_player": opp,
            "target_personnel": target_pid,
            "compleation_counters": 3,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C023 = _ps_card(
    "Praetor Pact Audit",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    clearance=0,
    subtypes={"Audit", "Protocol"},
    text=(
        "Compleat target opposing Personnel with the highest skill. "
        "(Counter goes immediately to 3.) "
        "The audit was unanimous. "
        "The auditor was already compleated."
    ),
    rarity="rare",
)
_C023.scp_on_play = _praetor_pact_audit_play


# C024. Vector Saturation Sweep
# Rules text: Place 1 compleation counter on each opposing Personnel.
def _vector_saturation_play(obj, state):
    """Place 1 compleation counter on each opposing personnel."""
    opp = scp._first_opposing_player(state, obj.controller)
    if opp is None:
        return []
    events = []
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    for pid in list(opp_personnel):
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue
        counters = s_opp.get(f"compleation_{pid}", 0) + 1
        s_opp[f"compleation_{pid}"] = counters
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "vector_saturation_sweep",
                "target_player": opp,
                "target_personnel": pid,
                "compleation_counters": counters,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_C024 = _ps_card(
    "Vector Saturation Sweep",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    clearance=0,
    subtypes={"Protocol", "Sweep"},
    text=(
        "Place 1 compleation counter on each opposing Personnel. "
        "Not targeted. "
        "The oil does not target. It saturates."
    ),
    rarity="uncommon",
)
_C024.scp_on_play = _vector_saturation_play


# C025. Class-IV Compleation Audit
# Rules text: Place 2 compleation counters on each opposing Personnel. Pay 1
# ethics_debt.
def _class_iv_audit_play(obj, state):
    """Place 2 compleation counters on each opposing personnel; pay 1 ethics_debt."""
    s_me = scp.site(state, obj.controller)
    # Pay 1 ethics_debt
    s_me["ethics_debt"] = s_me.get("ethics_debt", 0) + 1
    opp = scp._first_opposing_player(state, obj.controller)
    events = [scp.Event(
        type=scp.EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "class_iv_audit_ethics_debt",
            "ethics_debt": s_me["ethics_debt"],
        },
        source=obj.id,
        controller=obj.controller,
    )]
    if opp is None:
        return events
    s_opp = scp.site(state, opp)
    opp_personnel = s_opp.get("personnel", [])
    for pid in list(opp_personnel):
        pers_obj = state.objects.get(pid)
        if pers_obj is None:
            continue
        card_def = getattr(pers_obj, "card_def", None)
        if card_def and getattr(card_def, "scp_mnestic", False):
            continue
        counters = s_opp.get(f"compleation_{pid}", 0) + 2
        s_opp[f"compleation_{pid}"] = counters
        events.append(scp.Event(
            type=scp.EventType.SCP_INCIDENT_RESOLVED,
            payload={
                "player": obj.controller,
                "reason": "class_iv_audit_compleation",
                "target_player": opp,
                "target_personnel": pid,
                "compleation_counters": counters,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


_C025 = _ps_card(
    "Class-IV Compleation Audit",
    CardType.SCP_PROCEDURE,
    red_tape=3,
    clearance=0,
    subtypes={"Audit", "Protocol"},
    text=(
        "Place 2 compleation counters on each opposing Personnel. Pay 1 ethics_debt. "
        "Approved under emergency charter. "
        "Ethics board review: pending. "
        "Ethics board: also pending."
    ),
    rarity="rare",
)
_C025.scp_on_play = _class_iv_audit_play


# ---------------------------------------------------------------------------
# 4 FACILITIES
# ---------------------------------------------------------------------------


# C026. Sector-9 Compleation Quarantine Facility
# Rules text: Bonus: contain +1. Your Compleation Vector anomalies get +1
# Compleation Vector.
_C026 = _ps_card(
    "Sector-9 Compleation Quarantine Facility",
    CardType.SCP_FACILITY,
    red_tape=2,
    clearance=0,
    subtypes={"Containment Site", "Sector-9"},
    text=(
        "Bonus: contain +1. "
        "Your Compleation Vector anomalies get +1 Compleation Vector. "
        "Sector 9 was not built for this. "
        "It was repurposed. "
        "Several floors are still missing."
    ),
    rarity="rare",
)
_C026.scp_facility_bonus = {"contain": 1}
# Engine reads scp_compleation_vector_facility_bonus on active facilities
# to boost all friendly CV anomalies' effective N.
_C026.scp_compleation_vector_facility_bonus = 1


# C027. Atraxa Specimen Containment Cell
# Rules text: Bonus: research +1. Your Compleation anomalies have hazard +1
# while in this facility.
_C027 = _ps_card(
    "Atraxa Specimen Containment Cell",
    CardType.SCP_FACILITY,
    red_tape=1,
    clearance=0,
    subtypes={"Containment Site", "Specimen Cell"},
    text=(
        "Bonus: research +1. "
        "Your Compleation anomalies have hazard +1 while in this facility. "
        "Cell integrity: holding. "
        "Specimen cooperation status: alarming."
    ),
    rarity="uncommon",
)
_C027.scp_facility_bonus = {"research": 1}
# Engine reads scp_compleation_hazard_bonus for facility hazard-aura on CV anomalies.
_C027.scp_compleation_hazard_bonus = 1


# C028. Vivisection Suite Vega-9
# Rules text: Bonus: research +1.
_C028 = _ps_card(
    "Vivisection Suite Vega-9",
    CardType.SCP_FACILITY,
    red_tape=1,
    clearance=0,
    subtypes={"Laboratory", "Vivisection Suite"},
    text=(
        "Bonus: research +1. "
        "The suite is sterile. "
        "The subjects are not."
    ),
    rarity="common",
)
_C028.scp_facility_bonus = {"research": 1}


# C029. Oil Reclamation Tank Gamma
# Rules text: Bonus: contain +1, research +1. When a Personnel becomes
# compleated, gain 1 archive.
def _oil_tank_compleat_archive(obj, state, compleated_id=None):
    """When any Personnel is compleated, gain 1 archive."""
    return [scp.Event(
        type=scp.EventType.SCP_ARCHIVE_GAINED,
        payload={
            "player": obj.controller,
            "amount": 1,
            "archives": 1,
        },
        source=obj.id,
        controller=obj.controller,
    )]


_C029 = _ps_card(
    "Oil Reclamation Tank Gamma",
    CardType.SCP_FACILITY,
    red_tape=2,
    clearance=0,
    subtypes={"Laboratory", "Reclamation Tank"},
    text=(
        "Bonus: contain +1, research +1. "
        "When a Personnel becomes compleated, gain 1 archive. "
        "The oil is a resource. "
        "This is the sentence that got the researcher compleated."
    ),
    rarity="rare",
)
_C029.scp_facility_bonus = {"contain": 1, "research": 1}
# Passive facility trigger: when any personnel anywhere is compleated, gain 1 archive.
_C029.scp_on_any_compleated = _oil_tank_compleat_archive


# ---------------------------------------------------------------------------
# 1 MANDATE
# ---------------------------------------------------------------------------


# C030. Mandate FBN-PCV: Compleation Containment Protocol
# Rules text: Mandate. Alt-win `compleation_overrun`: when 3+ opposing Personnel
# have been compleated by you this game, you win at end of your next turn.
def _mandate_pcv_check(obj, state):
    """Win condition: fire when compleation_overrun is achieved (3+ swaps)."""
    s = scp.site(state, obj.controller)
    compleated_count = s.get("compleation_overrun_count", 0)
    if compleated_count >= 3:
        opp = scp._first_opposing_player(state, obj.controller)
        return [scp.Event(
            type=scp.EventType.SCP_WIN_CONDITION,
            payload={
                "winner": obj.controller,
                "reason": "compleation_overrun",
                "loser": opp,
                "compleated_count": compleated_count,
                "alt_win_id": "compleation_overrun",
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return []


_C030 = _ps_card(
    "Mandate FBN-PCV: Compleation Containment Protocol",
    CardType.SCP_MANDATE,
    red_tape=3,
    clearance=2,
    subtypes={"Mandate"},
    text=(
        "Mandate. Alt-win `compleation_overrun`: when 3+ opposing Personnel "
        "have been compleated by you this game, you win at end of your next turn. "
        "O5 ratification: unanimous. "
        "The ratification was unanimous because everyone present was already ours."
    ),
    rarity="mythic",
)
_C030.scp_alt_win = "compleation_overrun"
_C030.scp_alt_win_id = "compleation_overrun"
_C030.scp_alt_win_threshold = 3
_C030.scp_alt_win_metric = "compleation_overrun_count"
# Engine per-turn alt-win poll for mandates.
_C030.scp_on_turn_end = _mandate_pcv_check


# ---------------------------------------------------------------------------
# Aggregate export
# ---------------------------------------------------------------------------


PHYREXIAN_STRAIN_CARDS: list[CardDefinition] = [
    # Anomalies — mythic Praetor trio
    _C001,   # 1  SCP-FBN-1140 Yawgmoth-Pattern Strain
    _C002,   # 2  SCP-FBN-1141 Atraxa, Praetors' Conduit
    _C003,   # 3  SCP-FBN-1145 Elesh Norn, Mother of Machines
    # Anomalies — rare
    _C004,   # 4  SCP-FBN-1142 Sheoldred, Whispering Strain
    _C005,   # 5  SCP-FBN-1143 Vorinclex, Bio-Engineer Specimen
    _C006,   # 6  SCP-FBN-1144 Jin-Gitaxias, Cognitive Vector
    # Anomalies — uncommon
    _C007,   # 7  SCP-FBN-1138 The Compleated Liaison
    _C008,   # 8  SCP-FBN-1146 Urabrask, Combustion Vector
    _C009,   # 9  SCP-FBN-1147 Skithiryx-Class Vector Carrier
    _C010,   # 10 SCP-FBN-1148 The Phyresis Engine
    _C011,   # 11 SCP-FBN-1149 Memnarch-Pattern Aberration
    # Anomalies — common
    _C012,   # 12 SCP-FBN-1150 Phyrexian Negator
    _C013,   # 13 SCP-FBN-1151 Compleation Vector Spawn
    # Personnel — rare
    _C014,   # 14 Dr. Kassandra Volkov, Mnestic Quarantine Lead
    _C017,   # 15 Operative O5-3, Strain Containment Lead
    # Personnel — uncommon
    _C015,   # 16 Researcher Aramis, Vector Specialist
    _C016,   # 17 Dr. Linna Halle, Phyresis Containment
    _C020,   # 18 Dr. Volker Tiede, Praetor Specialist
    # Personnel — common
    _C018,   # 19 Researcher Drei, Compleation Cartographer
    _C019,   # 20 Class-A Operative "Nailbiter"
    # Procedures — rare
    _C021,   # 21 Class-A Mnestic Inoculation, Pattern: Yawgmoth-Resistant
    _C023,   # 22 Praetor Pact Audit
    _C025,   # 23 Class-IV Compleation Audit
    # Procedures — uncommon
    _C022,   # 24 Containment Breach Reversal: Phyresis Quarantine
    _C024,   # 25 Vector Saturation Sweep
    # Facilities — rare
    _C026,   # 26 Sector-9 Compleation Quarantine Facility
    _C029,   # 27 Oil Reclamation Tank Gamma
    # Facilities — uncommon / common
    _C027,   # 28 Atraxa Specimen Containment Cell
    _C028,   # 29 Vivisection Suite Vega-9
    # Mandate
    _C030,   # 30 Mandate FBN-PCV: Compleation Containment Protocol
]

_CARDS = PHYREXIAN_STRAIN_CARDS
