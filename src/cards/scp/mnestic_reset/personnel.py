"""MNR personnel sub-set.

Two pools live here:

* **Mnestic personnel** (12) — combat-ready bodies tagged
  ``scp_mnestic = True``. They hold antimemetic anomalies in place and
  shield the controller from Cognitive Hazard. Higher red tape (1-3) is
  the deck's tempo tax: Mnestic is *expensive*. Several carry a
  ``scp_aura`` that buffs other Mnestic / subtype-matching teammates.

* **Bystander personnel** (12) — cheap (RT 0-1), fragile sponges. They
  fill out the early-turn assignment grid, drain first under Cognitive
  Hazard's lowest-red-tape autopick, and a subset carry the **Mnestic
  Wake** activated ability (pay 1 ethics, exhaust, gain Mnestic
  permanently). 4 Bystanders carry Wake; another 4 carry
  ``scp_on_assign`` quirks that pay off only when a Mnestic teammate is
  online.

The sample ``MNR Marion Wheeler`` retains its position as the first card
because ``tests/test_scp_tcg.py::test_mnr_card_pool_smoke`` looks it up
by name.
"""

from __future__ import annotations

from typing import Callable

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

from .helpers import _mnestic_personnel, _mnestic_wake_ability, _mnr_card


# ---------------------------------------------------------------------------
# Sample Mnestic personnel — kept first for the smoke test fixture.
# ---------------------------------------------------------------------------


_MARION_WHEELER = _mnestic_personnel(
    "MNR Marion Wheeler",
    skills={"research": 2, "suppress": 1},
    red_tape=2,
    subtypes={"Antimemetics", "Hero"},
    text=(
        "Mnestic. While Marion Wheeler is active, antimemetic anomalies you "
        "control do not gain forget counters and your hand is shielded from "
        "Cognitive Hazard."
    ),
    rarity="rare",
    archetype="mnestic_core",
)


# ---------------------------------------------------------------------------
# Helpers for Bystander on_assign hooks. Self-contained so this module
# does not import from sibling mechanics/personnel_quirks.py.
# ---------------------------------------------------------------------------


def _site_event(event_type: EventType, obj: GameObject, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(
        type=event_type,
        payload=payload,
        source=obj.id,
        controller=obj.controller,
    )


def _has_friendly_mnestic_teammate(
    state: GameState, controller: str, self_obj: GameObject
) -> bool:
    """True iff a Mnestic personnel other than ``self_obj`` is active.

    Reads both the printed ``scp_mnestic`` card_def attribute AND the
    per-object ``scp_mnestic_gained`` flag (set by Mnestic Wake), so the
    check tracks the same "is Mnestic" semantics as ``scp.has_mnestic``
    but excludes the Bystander itself (Bystanders are not Mnestic; this
    check matters only when one wakes up, in which case the self
    exclusion still avoids double-counting).
    """
    for pid in list(state.scp_personnel.get(controller, [])):
        person = state.objects.get(pid)
        if not person or person.id == self_obj.id:
            continue
        if person.zone != ZoneType.BATTLEFIELD or person.state.scp_status != "active":
            continue
        if bool(getattr(person.card_def, "scp_mnestic", False)):
            return True
        if bool(getattr(person.state, "scp_mnestic_gained", False)):
            return True
    return False


def _co_assigned_mnestic(
    state: GameState, controller: str, self_obj: GameObject
) -> bool:
    """True iff another friendly Mnestic personnel is exhausted THIS test.

    ``_staff_total`` marks every co-assigned staff exhausted before
    ``_fire_on_assign`` runs, so iterating exhausted teammates lets a
    Bystander hook detect "I was used alongside a Mnestic teammate."
    """
    for pid in list(state.scp_personnel.get(controller, [])):
        person = state.objects.get(pid)
        if not person or person.id == self_obj.id:
            continue
        if person.zone != ZoneType.BATTLEFIELD or person.state.scp_status != "active":
            continue
        if not person.state.scp_exhausted:
            continue
        if bool(getattr(person.card_def, "scp_mnestic", False)):
            return True
        if bool(getattr(person.state, "scp_mnestic_gained", False)):
            return True
    return False


def _d_class_no_recall_hook() -> Callable:
    """Research assignment with a Mnestic teammate online: briefing +1.

    The D-Class shrug-and-forget is useful only when somebody else
    remembers what happened. Caps at briefing's natural state — no
    overflow handling.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "research":
            return []
        if not _has_friendly_mnestic_teammate(state, obj.controller, obj):
            return []
        s = scp.site(state, obj.controller)
        s["briefing"] += 1
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="d_class_no_recall_brief",
            briefing=s["briefing"],
            action=action,
        )]

    return hook


def _untrained_observer_hook() -> Callable:
    """Suppress assignment with Mnestic teammate online: secrecy +1.

    A naive observer told what to say by a Mnestic handler covers the
    public story better than a panicked one. No Mnestic = no benefit.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "suppress":
            return []
        if not _has_friendly_mnestic_teammate(state, obj.controller, obj):
            return []
        s = scp.site(state, obj.controller)
        s["secrecy"] += 1
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="untrained_observer_brief",
            secrecy=s["secrecy"],
            action=action,
        )]

    return hook


def _briefing_room_listener_hook() -> Callable:
    """Research assignment co-assigned with Mnestic teammate: task_bonus +1.

    The Listener pulls extra value when a Mnestic handler walks them
    through what they're looking at during the test itself.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "research":
            return []
        if not _co_assigned_mnestic(state, obj.controller, obj):
            return []
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="briefing_room_listener_handoff",
            task_bonus=1,
            action=action,
        )]

    return hook


def _walked_out_intern_hook() -> Callable:
    """Research assignment while any friendly Mnestic personnel is active: +1 research.

    Differs from the Briefing-Room Listener in that the Mnestic teammate
    does NOT have to be co-assigned — the Intern just needs one to be
    online. Cheaper trigger, tighter window (research-only).
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "research":
            return []
        if not _has_friendly_mnestic_teammate(state, obj.controller, obj):
            return []
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="walked_out_intern_assist",
            task_bonus=1,
            action=action,
        )]

    return hook


# ---------------------------------------------------------------------------
# Mnestic personnel (11 more, totaling 12 including Marion Wheeler).
# ---------------------------------------------------------------------------


_MNESTIC_PERSONNEL: list[CardDefinition] = [
    _mnestic_personnel(
        "MNR Director, Antimemetics Division",
        skills={"research": 3, "contain": 1},
        red_tape=3,
        subtypes={"Director", "Antimemetics"},
        text=(
            "Mnestic. The Division remembers because she insists. Every "
            "friendly personnel gets +1 research while the Director is active."
        ),
        rarity="rare",
        archetype="mnestic_core",
        aura={"any": {"research": 1}},
    ),
    _mnestic_personnel(
        "MNR Mnemonic Surgeon",
        skills={"research": 3},
        red_tape=2,
        subtypes={"Scientist", "Medical"},
        text=(
            "Mnestic. Treats memory like surgery: precise, sterile, and "
            "billed by the hour. Pure research engine."
        ),
        archetype="antimemetic_decay",
    ),
    _mnestic_personnel(
        "MNR Class-A Inoculated Agent",
        skills={"contain": 2, "suppress": 2, "research": 1},
        red_tape=2,
        subtypes={"Agent", "Security"},
        text=(
            "Mnestic. Class-A dosing buys broad-spectrum tasking — useful "
            "anywhere the file room screams. Other Agent personnel get +1 "
            "suppress while the Inoculated Agent is active."
        ),
        archetype="redaction_press",
        aura={"subtype:Agent": {"suppress": 1}},
    ),
    _mnestic_personnel(
        "MNR Mnestic-Coated Operative",
        skills={"contain": 3, "suppress": 1},
        red_tape=2,
        subtypes={"Security", "MTF"},
        text=(
            "Mnestic. Frontline containment in armor laminated with "
            "amnestic countermeasures. Other Security personnel get +1 "
            "contain while the Operative is active."
        ),
        archetype="mnestic_core",
        aura={"subtype:Security": {"contain": 1}},
    ),
    _mnestic_personnel(
        "MNR Memory Pattern Analyst",
        skills={"research": 3, "suppress": 1},
        red_tape=2,
        subtypes={"Scientist", "Memetics"},
        text=(
            "Mnestic. Reads the shape of what nobody else can read. "
            "Other Mnestic personnel get +1 research."
        ),
        archetype="antimemetic_decay",
        aura={"subtype:Mnestic": {"research": 1}},
    ),
    _mnestic_personnel(
        "MNR Inoculated Recordkeeper",
        skills={"research": 2, "suppress": 1},
        red_tape=2,
        subtypes={"Archivist", "Staff"},
        text=(
            "Mnestic. Writes down what the files refuse to. Other Mnestic "
            "personnel get +1 research."
        ),
        archetype="mnestic_core",
        aura={"subtype:Mnestic": {"research": 1}},
    ),
    _mnestic_personnel(
        "MNR Antimemetic Tactician",
        skills={"contain": 2, "research": 2, "suppress": 1},
        red_tape=2,
        subtypes={"Agent", "Security"},
        text=(
            "Mnestic. Plans around what the enemy will forget about us "
            "before they're done forgetting it."
        ),
        archetype="redaction_press",
    ),
    _mnestic_personnel(
        "MNR Bystander Coordinator",
        skills={"research": 1, "suppress": 2},
        red_tape=2,
        subtypes={"Staff", "Liaison"},
        text=(
            "Mnestic. Manages the people who can't be told what they're "
            "managing. Bystander personnel get +1 research while the "
            "Coordinator is active."
        ),
        archetype="mnestic_wake",
        aura={"subtype:Bystander": {"research": 1}},
    ),
    _mnestic_personnel(
        "MNR Mnestic Cathedral Curator",
        skills={"research": 2, "contain": 2},
        red_tape=3,
        subtypes={"Archivist", "Occult"},
        text=(
            "Mnestic. The Cathedral remembers what the Site forgets. "
            "Every friendly personnel gets +1 suppress."
        ),
        rarity="rare",
        archetype="redaction_press",
        aura={"any": {"suppress": 1}},
    ),
    _mnestic_personnel(
        "MNR Forgotten Bureau Liaison",
        skills={"research": 2, "suppress": 1},
        red_tape=1,
        subtypes={"Agent", "Liaison"},
        text=(
            "Mnestic. Speaks for the wing that does not appear on the org "
            "chart. Other Mnestic personnel get +1 suppress."
        ),
        archetype="redaction_press",
        aura={"subtype:Mnestic": {"suppress": 1}},
    ),
    _mnestic_personnel(
        "MNR Black-Box Archivist",
        skills={"research": 3, "contain": 1},
        red_tape=3,
        subtypes={"Archivist", "Staff"},
        text=(
            "Mnestic. The black box is full of nothing, and she has read "
            "all of it. Other Archivist personnel get +1 research."
        ),
        rarity="rare",
        archetype="mnestic_core",
        aura={"subtype:Archivist": {"research": 1}},
    ),
]


# ---------------------------------------------------------------------------
# Bystanders (12). Cheap, fragile, occasionally surprising.
# ---------------------------------------------------------------------------


def _make_bystander(
    name: str,
    *,
    skills: dict[str, int],
    red_tape: int,
    subtypes: set[str] | None = None,
    text: str,
    archetype: str = "mnestic_wake",
    rarity: str | None = None,
) -> CardDefinition:
    """Construct a Bystander personnel.

    Always tags the card with the ``Bystander`` subtype so the
    Bystander Coordinator's ``"subtype:Bystander"`` aura matches.
    """
    full_subtypes = set(subtypes or set()) | {"Bystander"}
    return _mnr_card(
        name,
        CardType.SCP_PERSONNEL,
        skills=skills,
        red_tape=red_tape,
        subtypes=full_subtypes,
        text=text,
        archetype=archetype,
        rarity=rarity,
        keywords={"Bystander"},
    )


# Plain Bystanders — pure stat lines that get drained first under
# Cognitive Hazard's lowest-RT-first autopick.

_OFFICE_TEMP = _make_bystander(
    "MNR Office Temp",
    skills={"research": 1},
    red_tape=0,
    text="A face in the crowd. Drains first when the file room screams.",
)

_DOCUMENTS_CLERK = _make_bystander(
    "MNR Documents Clerk",
    skills={"research": 1},
    red_tape=0,
    subtypes={"Staff"},
    text="Stamps the dossier she will not remember stamping.",
)

_MAILROOM_JUNIOR = _make_bystander(
    "MNR Mailroom Junior",
    skills={"contain": 1},
    red_tape=0,
    subtypes={"Staff"},
    text="Hands over the envelope. Forgets the hand.",
)

_HALLWAY_RUNNER = _make_bystander(
    "MNR Hallway Runner",
    skills={"suppress": 1},
    red_tape=0,
    subtypes={"Staff"},
    text="Carries the rumor, not the warning.",
)


# Bystanders with Mnestic Wake — pay 1 ethics_debt + exhaust to gain
# Mnestic permanently. The Wake transforms a fragile sponge into the
# anchor that holds the antimeme deck together.


def _conference_attendee_setup(obj: GameObject, state: GameState):
    _mnestic_wake_ability(
        obj,
        state,
        ethics_cost=1,
        description="Mnestic Wake: Pay 1 ethics debt, exhaust. Gain Mnestic. The Conference Attendee remembers what was discussed in the room.",
    )
    return []


_CONFERENCE_ATTENDEE = _make_bystander(
    "MNR Conference Attendee",
    skills={"research": 1, "suppress": 1},
    red_tape=1,
    subtypes={"Staff"},
    text=(
        "Until activated, just another body in the room. Mnestic Wake: "
        "pay 1 ethics debt, exhaust. Gain Mnestic permanently."
    ),
)
_CONFERENCE_ATTENDEE.setup_interceptors = _conference_attendee_setup


def _witness_12b_setup(obj: GameObject, state: GameState):
    _mnestic_wake_ability(
        obj,
        state,
        ethics_cost=1,
        description="Mnestic Wake: Pay 1 ethics debt, exhaust. Gain Mnestic. The Witness in 12-B remembers what room 12-B contained.",
    )
    return []


_WITNESS_12B = _make_bystander(
    "MNR Witness in 12-B",
    skills={"research": 1},
    red_tape=1,
    subtypes={"Civilian"},
    text=(
        "A subject of incident 12-B. Mnestic Wake: pay 1 ethics debt, "
        "exhaust. Gain Mnestic permanently."
    ),
)
_WITNESS_12B.setup_interceptors = _witness_12b_setup


def _department_newcomer_setup(obj: GameObject, state: GameState):
    _mnestic_wake_ability(
        obj,
        state,
        ethics_cost=1,
        description="Mnestic Wake: Pay 1 ethics debt, exhaust. Gain Mnestic. The Newcomer asks the question nobody asked.",
    )
    return []


_DEPARTMENT_NEWCOMER = _make_bystander(
    "MNR Department Newcomer",
    skills={"research": 1, "contain": 1},
    red_tape=1,
    subtypes={"Staff"},
    text=(
        "Has not yet learned what is forbidden to remember. Mnestic "
        "Wake: pay 1 ethics debt, exhaust. Gain Mnestic permanently."
    ),
)
_DEPARTMENT_NEWCOMER.setup_interceptors = _department_newcomer_setup


def _reluctant_subject_setup(obj: GameObject, state: GameState):
    _mnestic_wake_ability(
        obj,
        state,
        ethics_cost=1,
        description="Mnestic Wake: Pay 1 ethics debt, exhaust. Gain Mnestic. The Reluctant Subject refuses to be told what to forget.",
    )
    return []


_RELUCTANT_SUBJECT = _make_bystander(
    "MNR Reluctant Subject",
    skills={"suppress": 2},
    red_tape=1,
    subtypes={"Civilian"},
    text=(
        "Pulled in for testing; uncooperative. Mnestic Wake: pay 1 "
        "ethics debt, exhaust. Gain Mnestic permanently."
    ),
)
_RELUCTANT_SUBJECT.setup_interceptors = _reluctant_subject_setup


# Bystanders with on_assign quirks — modest, conditional bonuses that
# only fire when a Mnestic teammate is online. Pre-Wake, they're vanilla.

_D_CLASS_NO_RECALL = _make_bystander(
    "MNR D-Class (No Recall)",
    skills={"contain": 1, "research": 1},
    red_tape=0,
    subtypes={"D-Class"},
    text=(
        "Tasked. Inoculated. Allowed to forget. On assignment to "
        "research while you control a Mnestic personnel: briefing +1."
    ),
)
_D_CLASS_NO_RECALL.scp_on_assign = _d_class_no_recall_hook()


_UNTRAINED_OBSERVER = _make_bystander(
    "MNR Untrained Observer",
    skills={"research": 1},
    red_tape=0,
    subtypes={"Civilian"},
    text=(
        "Doesn't know what they saw. On assignment to suppress while "
        "you control a Mnestic personnel: secrecy +1 (briefed by the "
        "Mnestic handler before going on record)."
    ),
)
_UNTRAINED_OBSERVER.scp_on_assign = _untrained_observer_hook()


_BRIEFING_ROOM_LISTENER = _make_bystander(
    "MNR Briefing-Room Listener",
    skills={"research": 2},
    red_tape=1,
    subtypes={"Staff"},
    text=(
        "Listens like the recording isn't running. On assignment to "
        "research co-assigned with a Mnestic teammate: +1 research to "
        "this test."
    ),
)
_BRIEFING_ROOM_LISTENER.scp_on_assign = _briefing_room_listener_hook()


_WALKED_OUT_INTERN = _make_bystander(
    "MNR Walked-Out Intern",
    skills={"research": 1, "suppress": 1},
    red_tape=0,
    subtypes={"Staff"},
    text=(
        "Quit. Came back. Quit again. On assignment to research while "
        "you control a Mnestic personnel: +1 research to this test."
    ),
)
_WALKED_OUT_INTERN.scp_on_assign = _walked_out_intern_hook()


_BYSTANDERS: list[CardDefinition] = [
    _OFFICE_TEMP,
    _DOCUMENTS_CLERK,
    _MAILROOM_JUNIOR,
    _HALLWAY_RUNNER,
    _CONFERENCE_ATTENDEE,
    _WITNESS_12B,
    _DEPARTMENT_NEWCOMER,
    _RELUCTANT_SUBJECT,
    _D_CLASS_NO_RECALL,
    _UNTRAINED_OBSERVER,
    _BRIEFING_ROOM_LISTENER,
    _WALKED_OUT_INTERN,
]


# ---------------------------------------------------------------------------
# Final export. Marion Wheeler is first (smoke test fixture); then 11
# more Mnestic personnel, then 12 Bystanders, for a total of 24.
# ---------------------------------------------------------------------------


PERSONNEL: list[CardDefinition] = [
    _MARION_WHEELER,
    *_MNESTIC_PERSONNEL,
    *_BYSTANDERS,
]
