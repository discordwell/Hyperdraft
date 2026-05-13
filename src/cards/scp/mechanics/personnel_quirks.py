"""Assignment-time triggers for SCP personnel.

Each entry below sets ``scp_on_assign`` on a personnel card. The hook fires
once per assignment that actually uses the personnel (research / contain /
suppress) — fired BY the engine in ``src/engine/scp._fire_on_assign``,
called from ``run_test``, ``contain_anomaly``, and ``suppress_anomaly`` AFTER
``_staff_total`` has marked used staff exhausted.

Hook signature::

    (personnel_obj, state, action: str) -> list[Event]

``action`` is one of ``"research"``, ``"contain"``, ``"suppress"``.

Hooks may:
  * Mutate site state directly (briefing/secrecy/breach/ethics_debt).
  * Return events whose ``payload["task_bonus"]`` adds to THIS assignment's
    total before success/fail resolution (e.g. Memory Triage Handler adds
    +1 research when another Memetics staff is co-assigned).
  * Toggle ``personnel.state.scp_exhausted = False`` to veto exhaustion
    (Sleep-Deprived Intern's "first assignment per turn is free").

The hooks are stateless w.r.t. card definitions: every in-game copy of the
card reads the same ``card_def.scp_on_assign``, so post-construction
mutation here is the canonical pattern (mirrors ``personnel_synergy.py``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from src.engine import scp
from src.engine.types import Event, EventType, GameObject, GameState, ZoneType

if TYPE_CHECKING:
    from src.engine.types import CardDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _site_event(event_type: EventType, obj: GameObject, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(type=event_type, payload=payload, source=obj.id, controller=obj.controller)


def _co_assigned_with_subtype(state: GameState, controller: str, self_obj: GameObject, subtype: str) -> bool:
    """True iff another friendly personnel exhausted THIS turn carries ``subtype``.

    Used by "+X to this test if a teammate of subtype Y was also assigned"
    handlers. Because ``_staff_total`` exhausts the whole staff list before
    on_assign hooks fire, every co-assignee for the current action is already
    marked exhausted by the time this lookup runs.
    """
    for pid in list(state.scp_personnel.get(controller, [])):
        person = state.objects.get(pid)
        if not person or person.id == self_obj.id:
            continue
        if person.zone != ZoneType.BATTLEFIELD:
            continue
        if not person.state.scp_exhausted:
            continue
        subtypes = set(person.characteristics.subtypes or set()) if person.characteristics else set()
        if subtype in subtypes:
            return True
    return False


def _has_sealed_anomaly(state: GameState, controller: str) -> bool:
    """True iff ``controller`` has at least one sealed-status anomaly on the battlefield."""
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return False
    for obj_id in list(battlefield.objects):
        obj = state.objects.get(obj_id)
        if not obj or obj.controller != controller:
            continue
        if obj.state.scp_status == "sealed":
            return True
    return False


# ---------------------------------------------------------------------------
# CORE personnel quirks
# ---------------------------------------------------------------------------


def _janitor_who_knows_too_much():
    """When assigned to suppression, lower breach by 1 (alarms hushed early).

    Flavor: "stops alarms before anyone notices." Mechanically a +1 to the
    Site's hidden breach counter is too punishing on every fire; instead we
    SHAVE one point off the current breach when the Janitor is dispatched
    to suppress. Caps at zero — never seeds negative breach.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "suppress":
            return []
        s = scp.site(state, obj.controller)
        before = s["breach"]
        s["breach"] = max(0, before - 1)
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="janitor_hushed_alarm",
            breach_before=before,
            breach=s["breach"],
        )]

    return hook


def _sleep_deprived_intern():
    """First assignment per turn does NOT exhaust the Intern.

    The intern can be re-assigned in the same turn so long as one of their
    earlier slots was their FIRST of the turn. We piggyback on the engine's
    ``scp_assigns_this_turn`` counter, incremented BEFORE the hook runs in
    ``_fire_on_assign``. So this hook reads ``scp_assigns_this_turn == 1``
    to detect the first assignment.

    Subsequent assignments DO exhaust normally (the engine already marked
    the Intern exhausted, so we leave that in place).
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        count = int(getattr(obj.state, "scp_assigns_this_turn", 0) or 0)
        if count != 1:
            return []
        # Veto exhaustion ONLY on the first assignment. The engine has already
        # set scp_exhausted = True (via _staff_total) so we toggle it back.
        obj.state.scp_exhausted = False
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="intern_still_available",
            action=action,
        )]

    return hook


# ---------------------------------------------------------------------------
# SZB Handler quirks
# ---------------------------------------------------------------------------


def _memory_triage_handler():
    """When assigned to research with a co-Memetics staff: +1 research to this test.

    Reads the global personnel index to detect a co-assigned Memetics
    teammate. The bonus is returned as a ``task_bonus`` event payload —
    summed into the test total by the engine's _fire_on_assign helper
    before the success check.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "research":
            return []
        if not _co_assigned_with_subtype(state, obj.controller, obj, "Memetics"):
            return []
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="memory_triage_handoff",
            task_bonus=1,
            action=action,
        )]

    return hook


def _press_conference_handler():
    """When assigned to suppression: -1 secrecy, +2 suppress to this test (going public).

    The price of staging a press conference: you trade exposure for raw
    suppression power. Suppression is otherwise weakly task-leveraged
    (no built-in archive reward), so a +2 is in-line with mandate auras.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "suppress":
            return []
        s = scp.site(state, obj.controller)
        s["secrecy"] -= 1
        return [_site_event(
            EventType.SCP_AUDIT,
            obj,
            reason="press_conference_handoff",
            task_bonus=2,
            exposure=1,
            secrecy=s["secrecy"],
        )]

    return hook


def _witness_stampede_handler():
    """When assigned to containment: scrub the target anomaly's mood back to None.

    Witness stampede = "everyone's running, the anomaly's signal vanishes
    under the noise." Resetting mood removes any mood-driven hazard /
    containment / curiosity penalty for the rest of this turn (until the
    next mood-shift event). Returns no task_bonus — pure debuff utility.

    Looks up the most recently-opened active anomaly for the controller
    because containment hooks don't see the target via the personnel slot.
    We pick the FIRST active anomaly the controller owns (deterministic).
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "contain":
            return []
        anomalies = list(state.scp_anomalies.get(obj.controller, []))
        if not anomalies:
            return []
        for aid in anomalies:
            anomaly = state.objects.get(aid)
            if not anomaly:
                continue
            if anomaly.zone != ZoneType.BATTLEFIELD or anomaly.state.scp_status != "active":
                continue
            if anomaly.state.scp_mood is None:
                continue
            prior = anomaly.state.scp_mood
            anomaly.state.scp_mood = None
            return [_site_event(
                EventType.SCP_MOOD_SHIFT,
                obj,
                anomaly_id=anomaly.id,
                reason="witness_stampede_scrub",
                **{"from": prior, "to": None},
            )]
        return []

    return hook


def _white_pill_ward_handler():
    """When assigned to research: erase one point of ethics_debt (white-pill triage).

    A small, repeatable ethics-cleanup payoff. Caps at zero. No task_bonus.
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "research":
            return []
        s = scp.site(state, obj.controller)
        if s["ethics_debt"] <= 0:
            return []
        before = s["ethics_debt"]
        s["ethics_debt"] = max(0, before - 1)
        return [_site_event(
            EventType.SCP_ETHICS_SPENT,
            obj,
            reason="white_pill_triage",
            mode="ethics_relief",
            ethics_debt=s["ethics_debt"],
            ethics_debt_before=before,
        )]

    return hook


def _mnemonic_orchard_handler():
    """When assigned to research with at least one sealed anomaly on the battlefield: briefing +1.

    Sealed anomalies in the Mnestic playbook are the orchard you're tending.
    Working a sealed anomaly while assigning the Orchard Handler grants a
    briefing token (the engine's mood-shift currency).
    """

    def hook(obj: GameObject, state: GameState, action: str) -> list[Event]:
        if action != "research":
            return []
        if not _has_sealed_anomaly(state, obj.controller):
            return []
        s = scp.site(state, obj.controller)
        s["briefing"] += 1
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="mnemonic_orchard_brief",
            briefing=s["briefing"],
        )]

    return hook


# ---------------------------------------------------------------------------
# Wiring table
# ---------------------------------------------------------------------------


# (name, factory, text) — text replaces the card's printed flavor.
_QUIRKS: tuple[tuple[str, Callable[[], Callable], str], ...] = (
    # CORE personnel.
    (
        "Janitor Who Knows Too Much",
        _janitor_who_knows_too_much,
        # NOTE: personnel_synergy.py already sets a "Staff +1 suppress" aura
        # text for the Janitor; we APPEND the on-assign clause so both
        # appliers cooperate.
        " On assignment to suppress: breach -1 (alarms hushed before anyone notices).",
    ),
    (
        "Sleep-Deprived Intern",
        _sleep_deprived_intern,
        "Research 1, suppress 1. On the FIRST assignment per turn the Intern is NOT exhausted (somehow always available).",
    ),
    # SZB Handlers.
    (
        "SZB Memory Triage Handler",
        _memory_triage_handler,
        # Memory Triage's stat line is research-leaning per the SZB
        # generator; we APPEND the on-assign clause to the existing text.
        " On assignment to research with a co-assigned Memetics staff: +1 research to this test.",
    ),
    (
        "SZB Press Conference Handler",
        _press_conference_handler,
        " On assignment to suppress: secrecy -1, +2 suppress to this test (the price of going public).",
    ),
    (
        "SZB Witness Stampede Handler",
        _witness_stampede_handler,
        " On assignment to contain: reset the highest-priority active anomaly's mood to None.",
    ),
    (
        "SZB White Pill Ward Handler",
        _white_pill_ward_handler,
        " On assignment to research: ethics debt -1 (white-pill triage clears one point).",
    ),
    (
        "SZB Mnemonic Orchard Handler",
        _mnemonic_orchard_handler,
        " On assignment to research while you have a sealed anomaly: briefing +1.",
    ),
)


def apply_personnel_quirks(cards: "dict[str, CardDefinition]") -> None:
    """Wire ``scp_on_assign`` (and rules-text) on selected personnel.

    Mutates the card pool in place. Idempotent — re-running rebinds the
    same hook factory output and re-appends/re-overwrites the same text
    clause. Safe to call once after the SCP card pool is constructed.

    Ordering: ``personnel_synergy`` runs FIRST in ``apply_all_mechanics``
    so its scp_aura clause is already in the card text. For cards that
    share text with personnel_synergy (Janitor, SZB Memory Triage Handler),
    we APPEND a new sentence instead of overwriting.
    """
    for name, factory, text in _QUIRKS:
        card = cards.get(name)
        if card is None:
            continue
        card.scp_on_assign = factory()
        existing = card.text or ""
        # Idempotency: skip if our clause is already present.
        if text.strip() and text.strip() in existing:
            continue
        # If the text starts with a leading space, treat it as an append
        # clause to whatever personnel_synergy already wrote. Otherwise
        # it's a full replacement.
        if text.startswith(" "):
            card.text = f"{existing.rstrip()}{text}" if existing.strip() else text.lstrip()
        else:
            card.text = text
