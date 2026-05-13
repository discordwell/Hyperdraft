"""MNR-on-SZB callback cards.

16 bridge cards that hybridize MNR's Redact verb (and Mnestic tag) with the
Site Zero: Broken Masquerade keyword library: Brief, Blackfile, Anchor,
Quarantine, Overexpose, Rotation, and GOI counter-raid. Layout::

- 10 procedures whose effect_fn fires a Redact + an SZB-verb step (the
  hybrid premise of the sub-set).
- 6 personnel — 4 Mnestic, 2 Bystander. Two carry ``scp_on_assign`` hooks
  that call the SZB verbs (Brief, Anchor return-from-forgotten); one
  carries an ``scp_aura`` so MNR's Mnestic tag interacts with SZB Agent /
  Memetics subtypes; one carries a Mnestic Wake activated ability.

Card-design contract:

- All cards keep the ``MNR`` prefix so the global SCP_CARDS filter by
  ``scp_expansion_code == "MNR"`` still matches.
- ``effect_fn`` signatures match ``_activate_dossier``'s ``(obj, state)`` /
  ``(obj, state, game)`` dispatcher.
- The sample ``MNR Antimemetic Audit`` is preserved verbatim.
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

from .helpers import _mnestic_wake_ability, _mnr_card, _redact


# ---------------------------------------------------------------------------
# Local helpers — small wrappers around scp.* engine calls that the callbacks
# below share. Each helper is short enough to inline, but pulling them out
# keeps the procedure effect_fns readable + makes "what does Redact+Brief
# look like" greppable for downstream card agents.
# ---------------------------------------------------------------------------


def _opponent(state: GameState, controller: str) -> str | None:
    return next(
        (
            pid
            for pid, player in state.players.items()
            if pid != controller and not getattr(player, "has_lost", False)
        ),
        None,
    )


def _highest_pending_dossier(state: GameState, controller: str) -> GameObject | None:
    """Return the highest-paperwork pending dossier owned by ``controller``.

    Used by Blackfile-style hybrids to pick a single deterministic misfile
    target. Ties broken by oldest object_id (insertion order).
    """
    best: GameObject | None = None
    for cand in state.objects.values():
        if cand.controller != controller:
            continue
        if cand.state.scp_status != "pending":
            continue
        if best is None or cand.state.scp_paperwork > best.state.scp_paperwork:
            best = cand
    return best


def _brief_n(obj: GameObject, state: GameState, n: int) -> Event:
    """Brief N: add ``n`` to briefing, emit ``SCP_INCIDENT_RESOLVED``."""
    s = scp.site(state, obj.controller)
    s["briefing"] += n
    return Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={"player": obj.controller, "reason": "brief", "briefing": s["briefing"]},
        source=obj.id,
        controller=obj.controller,
    )


def _maybe_redact(obj: GameObject, state: GameState, game, n: int) -> list[Event]:
    """Redact N if ``game`` is present (engine path); empty list in bare tests."""
    if game is None or n <= 0:
        return []
    return scp.redact_opposing(game, obj.controller, n, source=obj.id)


# ---------------------------------------------------------------------------
# Sample card — preserved verbatim. Card-design agents: do NOT edit this
# entry, only append below.
# ---------------------------------------------------------------------------


def _redact_and_blackfile(obj: GameObject, state: GameState, game=None) -> list[Event]:
    actual_game = game if game is not None else getattr(state, "_game", None)
    if actual_game is None:
        return []
    # Redact 1 first.
    events = scp.redact_opposing(actual_game, obj.controller, 1, source=obj.id)
    # Then a deterministic Blackfile-1: misfile the first opposing pending
    # dossier we find (matches the SZB Blackfile sample's iteration order).
    opponent = next(
        (
            pid for pid, player in state.players.items()
            if pid != obj.controller and not getattr(player, "has_lost", False)
        ),
        None,
    )
    if opponent is None:
        return events
    for cand in state.objects.values():
        if cand.controller != opponent:
            continue
        if cand.state.scp_status != "pending":
            continue
        ok, _msg, mis_events = scp.misfile_dossier(
            actual_game, obj.controller, cand.id, amount=1, source=obj.id,
        )
        if ok:
            events.extend(mis_events)
            break
    return events


_ANTIMEMETIC_AUDIT = _mnr_card(
    "MNR Antimemetic Audit",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Redaction", "Audit"},
    text="Redact 1 and Blackfile 1: each opponent discards a card; add paperwork to one opposing pending dossier.",
    effect=_redact_and_blackfile,
    rarity="uncommon",
    archetype="redaction_press",
    keywords={"Blackfile", "Redact"},
)


# ---------------------------------------------------------------------------
# Procedures (10) — hybrid Redact + SZB-verb chains.
# ---------------------------------------------------------------------------


# 1. Mnestic Quarantine — Redact 1 + set opposing anomaly mood to "cryptic".
def _mnestic_quarantine(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Redact 1, then shift one opposing active anomaly to ``cryptic``.

    Mood shift uses the engine's ``apply_protocol`` path when ``game`` is
    available (so the event log gets ``SCP_PROTOCOL_APPLIED``); falls back
    to a direct state mutation in bare-test contexts. Targets the highest-
    hazard opposing active anomaly (no PendingChoice — this card prints as
    a one-shot procedure not a target-prompt spell, in keeping with the
    SZB ``_quarantine_procedure`` simplifying convention).
    """
    actual_game = game if game is not None else getattr(state, "_game", None)
    events = _maybe_redact(obj, state, actual_game, 1)
    opp_id = _opponent(state, obj.controller)
    if opp_id is None:
        return events
    candidates = [
        state.objects[aid]
        for aid in state.scp_anomalies.get(opp_id, [])
        if aid in state.objects
        and state.objects[aid].state.scp_status == "active"
        and state.objects[aid].zone == ZoneType.BATTLEFIELD
    ]
    if not candidates:
        return events
    target = max(candidates, key=lambda a: int(getattr(a.card_def, "scp_hazard", 0) or 0))
    target.state.scp_mood = "cryptic"
    events.append(Event(
        type=EventType.SCP_MOOD_SHIFT,
        payload={"object_id": target.id, "to": "cryptic", "reason": "mnestic_quarantine"},
        source=obj.id,
        controller=obj.controller,
    ))
    return events


_MNESTIC_QUARANTINE = _mnr_card(
    "MNR Mnestic Quarantine",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    subtypes={"Redaction", "Quarantine"},
    text=(
        "Redact 1. Quarantine: an opposing active anomaly's mood becomes "
        "cryptic. Lock it behind glass; let the glass do the lying."
    ),
    effect=_mnestic_quarantine,
    rarity="uncommon",
    archetype="redaction_press",
    keywords={"Quarantine", "Redact"},
)


# 2. Backchannel Brief — Redact 1 + Brief 1.
def _backchannel_brief(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Redact 1, then add 1 briefing token. The director makes a call."""
    actual_game = game if game is not None else getattr(state, "_game", None)
    events = _maybe_redact(obj, state, actual_game, 1)
    events.append(_brief_n(obj, state, 1))
    return events


_BACKCHANNEL_BRIEF = _mnr_card(
    "MNR Backchannel Brief",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Redaction", "Brief"},
    text="Redact 1. Brief 1. The director makes a call nobody remembers.",
    effect=_backchannel_brief,
    rarity="common",
    archetype="redaction_press",
    keywords={"Brief", "Redact"},
)


# 3. Anchor Reset — reset forget counters on all your anomalies (no Redact).
def _anchor_reset(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Reset ``scp_forget_counters`` to 0 on every anomaly the controller has.

    Pairs cleanly with SZB Anchor decks (which hold contained anomalies long
    enough to want the counters scrubbed) AND with MNR antimeme decks (which
    are racing the antimeme clock). Briefing +1 because the act of reviewing
    each dossier is its own briefing event.
    """
    reset_count = 0
    events: list[Event] = []
    for anomaly_id in list(state.scp_anomalies.get(obj.controller, [])) + list(state.scp_contained.get(obj.controller, [])):
        anomaly = state.objects.get(anomaly_id)
        if anomaly is None or anomaly.zone != ZoneType.BATTLEFIELD:
            continue
        prior = int(getattr(anomaly.state, "scp_forget_counters", 0) or 0)
        if prior > 0:
            anomaly.state.scp_forget_counters = 0
            reset_count += 1
            events.append(Event(
                type=EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": obj.controller,
                    "object_id": anomaly.id,
                    "reason": "anchor_reset",
                    "forget_counters_before": prior,
                },
                source=obj.id,
                controller=obj.controller,
            ))
    events.append(_brief_n(obj, state, 1))
    return events


_ANCHOR_RESET = _mnr_card(
    "MNR Anchor Reset",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    subtypes={"Anchor", "Antimemetic"},
    text=(
        "Reset forget counters on every anomaly you control. Brief 1. "
        "Re-read the file. The file insists this is the first reading."
    ),
    effect=_anchor_reset,
    rarity="rare",
    archetype="mnestic_reset",
    keywords={"Anchor", "Brief"},
)


# 4. Overexposure Probe — secrecy -2, ethics -1 (refund), Redact 1.
def _overexposure_probe(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Overexpose-style: trade secrecy for archives + redact a card."""
    actual_game = game if game is not None else getattr(state, "_game", None)
    s = scp.site(state, obj.controller)
    s["secrecy"] -= 2
    s["ethics_debt"] = max(0, s["ethics_debt"] - 1)
    events: list[Event] = [Event(
        type=EventType.SCP_AUDIT,
        payload={
            "actor": obj.id,
            "target": obj.controller,
            "exposure": 2,
            "reason": "overexposure_probe",
            "secrecy": s["secrecy"],
            "ethics_debt": s["ethics_debt"],
        },
        source=obj.id,
        controller=obj.controller,
    )]
    events.extend(_maybe_redact(obj, state, actual_game, 1))
    return events


_OVEREXPOSURE_PROBE = _mnr_card(
    "MNR Overexposure Probe",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Overexpose", "Redaction"},
    text=(
        "Overexpose: secrecy -2, ethics debt -1. Redact 1. Trade the cover "
        "story for a clean memory."
    ),
    effect=_overexposure_probe,
    rarity="uncommon",
    archetype="mnestic_reset",
    keywords={"Overexpose", "Redact"},
)


# 5. Rotation Drill — refresh one exhausted staff + Brief 1.
def _rotation_drill(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Mirror SZB ``_rotation_procedure``: refund slot, refresh one staff."""
    s = scp.site(state, obj.controller)
    s["briefing"] += 1
    if s["assignments_used"] > 0:
        s["assignments_used"] -= 1
    refreshed = 0
    for staff_id in list(state.scp_personnel.get(obj.controller, [])):
        staff = state.objects.get(staff_id)
        if staff and staff.state.scp_exhausted:
            staff.state.scp_exhausted = False
            refreshed += 1
            break
    return [Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": obj.controller,
            "reason": "rotation_drill",
            "refreshed": refreshed,
            "assignments_used": s["assignments_used"],
            "briefing": s["briefing"],
        },
        source=obj.id,
        controller=obj.controller,
    )]


_ROTATION_DRILL = _mnr_card(
    "MNR Rotation Drill",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Rotation", "Brief"},
    text=(
        "Rotation 1. Brief 1. Send the swing shift home. Bring the night "
        "shift in. Hand them the same coffee."
    ),
    effect=_rotation_drill,
    rarity="common",
    archetype="mnestic_reset",
    keywords={"Rotation", "Brief"},
)


# 6. Memory-Holed Audit — paperwork sabotage + Redact 1.
def _memory_holed_audit(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Add 2 paperwork to one opposing pending dossier; Redact 1.

    Blackfile-flavored variant — picks the highest-paperwork pending dossier
    rather than the first one we find (so the audit lands on the file that
    was already drifting toward late). Falls back to direct mutation when
    ``game`` is unavailable.
    """
    actual_game = game if game is not None else getattr(state, "_game", None)
    events: list[Event] = []
    opp_id = _opponent(state, obj.controller)
    if opp_id is not None:
        target = _highest_pending_dossier(state, opp_id)
        if target is not None:
            if actual_game is not None:
                ok, _msg, mis_events = scp.misfile_dossier(
                    actual_game, obj.controller, target.id, amount=2, source=obj.id,
                )
                if ok:
                    events.extend(mis_events)
            else:
                target.state.scp_paperwork += 2
                events.append(Event(
                    type=EventType.SCP_PAPERWORK_TICK,
                    payload={
                        "object_id": target.id,
                        "to": target.state.scp_paperwork,
                        "reason": "memory_holed_audit",
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
    events.extend(_maybe_redact(obj, state, actual_game, 1))
    return events


_MEMORY_HOLED_AUDIT = _mnr_card(
    "MNR Memory-Holed Audit",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    subtypes={"Blackfile", "Redaction"},
    text=(
        "Blackfile 2: add 2 paperwork to one opposing pending dossier. "
        "Redact 1. Bury it under more of itself."
    ),
    effect=_memory_holed_audit,
    rarity="uncommon",
    archetype="redaction_press",
    keywords={"Blackfile", "Redact"},
)


# 7. Mnestic Counter-Raid — opposing goi_raid + Redact 1.
def _mnestic_counter_raid(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Trigger ``scp.goi_raid`` against an opponent + Redact 1."""
    actual_game = game if game is not None else getattr(state, "_game", None)
    events: list[Event] = []
    opp_id = _opponent(state, obj.controller)
    if actual_game is not None and opp_id is not None:
        events.extend(scp.goi_raid(
            actual_game, opp_id, faction="MNR Mnestic Strike Team", source=obj.id,
        ))
    events.extend(_maybe_redact(obj, state, actual_game, 1))
    return events


_MNESTIC_COUNTER_RAID = _mnr_card(
    "MNR Mnestic Counter-Raid",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    subtypes={"GOI", "Redaction"},
    text=(
        "Counter-raid an opposing Site. Redact 1. Send the unmarked van. "
        "Send the second unmarked van to forget the first one."
    ),
    effect=_mnestic_counter_raid,
    rarity="uncommon",
    archetype="redaction_press",
    keywords={"GOI", "Redact"},
)


# 8. Brief and Bury — Brief 1 + Redact 1 + Brief 1 chain.
def _brief_and_bury(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Brief 1, Redact 1, Brief 1. The double-brief frames the redaction."""
    actual_game = game if game is not None else getattr(state, "_game", None)
    events: list[Event] = [_brief_n(obj, state, 1)]
    events.extend(_maybe_redact(obj, state, actual_game, 1))
    events.append(_brief_n(obj, state, 1))
    return events


_BRIEF_AND_BURY = _mnr_card(
    "MNR Brief and Bury",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Brief", "Redaction"},
    text=(
        "Brief 1. Redact 1. Brief 1. Tell them, take it back, tell them "
        "the take-back never happened."
    ),
    effect=_brief_and_bury,
    rarity="common",
    archetype="redaction_press",
    keywords={"Brief", "Redact"},
)


# 9. Witness Erasure — exhaust an opposing personnel + Redact 1.
def _witness_erasure(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Exhaust the opposing personnel with the highest research; Redact 1.

    Targets research (rather than contain/suppress) on the theory that the
    canonical use case is removing a researcher from the upcoming research
    phase — research is the task most directly producing archives. Falls
    back to the highest by sum-of-skills if research ties.
    """
    actual_game = game if game is not None else getattr(state, "_game", None)
    events: list[Event] = []
    opp_id = _opponent(state, obj.controller)
    if opp_id is not None:
        candidates: list[GameObject] = []
        for pid in state.scp_personnel.get(opp_id, []):
            staff = state.objects.get(pid)
            if not staff or staff.state.scp_status != "active":
                continue
            if staff.state.scp_exhausted:
                continue
            if staff.zone != ZoneType.BATTLEFIELD:
                continue
            candidates.append(staff)
        if candidates:
            def _score(staff: GameObject) -> tuple[int, int, str]:
                skills = getattr(staff.card_def, "scp_skills", {}) if staff.card_def else {}
                research = int(skills.get("research", 0) or 0)
                total = sum(int(v or 0) for v in skills.values())
                return (research, total, staff.id)

            target = max(candidates, key=_score)
            target.state.scp_exhausted = True
            events.append(Event(
                type=EventType.SCP_INCIDENT_RESOLVED,
                payload={
                    "player": obj.controller,
                    "target": opp_id,
                    "object_id": target.id,
                    "reason": "witness_erasure",
                },
                source=obj.id,
                controller=obj.controller,
            ))
    events.extend(_maybe_redact(obj, state, actual_game, 1))
    return events


_WITNESS_ERASURE = _mnr_card(
    "MNR Witness Erasure",
    CardType.SCP_PROCEDURE,
    red_tape=2,
    subtypes={"Redaction", "Mnemonic"},
    text=(
        "Exhaust the opposing personnel with the highest research. "
        "Redact 1. The most informed witness is the easiest to convince."
    ),
    effect=_witness_erasure,
    rarity="rare",
    archetype="redaction_press",
    keywords={"Redact"},
)


# ---------------------------------------------------------------------------
# Personnel (6) — 4 Mnestic + 2 Bystander.
# ---------------------------------------------------------------------------


# 1. Mnestic Anchor Operative — Mnestic + scp_on_assign returns a forgotten
#    anomaly to active when assigned to contain.
def _anchor_operative_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """On contain assignment: return one forgotten anomaly to active status.

    Reads ``state.scp_forgotten[controller]``; pops the most-recently-
    forgotten anomaly (LIFO — newest forgotten is the most likely to still
    be relevant). Restores ``scp_status = "active"`` and re-inserts into
    ``scp_anomalies``. No event emitted by the hook itself beyond the
    standard ``SCP_INCIDENT_RESOLVED`` marker — the SCP_FORGET log is
    already in event_log, and this functions as a soft undo.
    """
    if action != "contain":
        return []
    forgotten_ids = list(state.scp_forgotten.get(staff.controller, []))
    if not forgotten_ids:
        return []
    target_id = forgotten_ids[-1]
    target = state.objects.get(target_id)
    if target is None or target.zone != ZoneType.BATTLEFIELD:
        return []
    # Restore: drop from forgotten, append to active, flip status.
    state.scp_forgotten[staff.controller].remove(target_id)
    if target_id not in state.scp_anomalies.setdefault(staff.controller, []):
        state.scp_anomalies[staff.controller].append(target_id)
    target.state.scp_status = "active"
    target.state.scp_forget_counters = 0
    return [Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": staff.controller,
            "object_id": target_id,
            "reason": "anchor_operative_recall",
            "task_bonus": 0,
        },
        source=staff.id,
        controller=staff.controller,
    )]


def _build_anchor_operative() -> CardDefinition:
    card = _mnr_card(
        "MNR Mnestic Anchor Operative",
        CardType.SCP_PERSONNEL,
        red_tape=3,
        subtypes={"Mnestic", "Security", "Anchor"},
        text=(
            "Mnestic. Suppress 2. When you assign Mnestic Anchor Operative "
            "to contain, return one of your forgotten anomalies to active "
            "status (forget counters reset to 0). The badge was issued "
            "yesterday. Yesterday is exactly when it has always been issued."
        ),
        skills={"suppress": 2},
        rarity="rare",
        archetype="mnestic_core",
    )
    card.scp_mnestic = True
    card.scp_on_assign = _anchor_operative_on_assign
    return card


_ANCHOR_OPERATIVE = _build_anchor_operative()


# 2. SZB Liaison — Mnestic, RT 2, dual stats, no aura.
def _build_szb_liaison() -> CardDefinition:
    card = _mnr_card(
        "MNR SZB Liaison",
        CardType.SCP_PERSONNEL,
        red_tape=2,
        subtypes={"Mnestic", "Bureaucracy"},
        text=(
            "Mnestic. Research 2, suppress 1. Carries the briefing across "
            "the floor without reading it."
        ),
        skills={"research": 2, "suppress": 1},
        rarity="uncommon",
        archetype="mnestic_core",
    )
    card.scp_mnestic = True
    return card


_SZB_LIAISON = _build_szb_liaison()


# 3. Bystander Witness Pool — Bystander, on_assign: Brief 1.
def _bystander_pool_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """Brief 1 on EVERY assignment (research / contain / suppress).

    Bystanders are perpetual: the more often you cite them, the larger the
    crowd becomes. Encoded as briefing +1 per assignment.
    """
    return [_brief_n(staff, state, 1)]


def _build_bystander_witness_pool() -> CardDefinition:
    card = _mnr_card(
        "MNR Bystander Witness Pool",
        CardType.SCP_PERSONNEL,
        red_tape=1,
        subtypes={"Bystander", "Civilian"},
        text=(
            "Research 1, suppress 1. When you assign Bystander Witness "
            "Pool, Brief 1. Twenty witnesses. Twenty-one stories. None of "
            "them agree."
        ),
        skills={"research": 1, "suppress": 1},
        rarity="common",
        archetype="mnestic_reset",
    )
    card.scp_on_assign = _bystander_pool_on_assign
    return card


_BYSTANDER_WITNESS_POOL = _build_bystander_witness_pool()


# 4. Mnemonic Field Agent — Mnestic + Agent subtype, suppress 2 + Agent aura.
def _build_mnemonic_field_agent() -> CardDefinition:
    card = _mnr_card(
        "MNR Mnemonic Field Agent",
        CardType.SCP_PERSONNEL,
        red_tape=2,
        subtypes={"Mnestic", "Agent"},
        text=(
            "Mnestic. Suppress 2. Other Agent personnel get +1 suppress. "
            "He carries two notebooks. The second one notes what the "
            "first one forgot."
        ),
        skills={"suppress": 2},
        rarity="rare",
        archetype="mnestic_core",
        aura={"subtype:Agent": {"suppress": 1}},
    )
    card.scp_mnestic = True
    return card


_MNEMONIC_FIELD_AGENT = _build_mnemonic_field_agent()


# 5. Cleanup Crew Lead — Mnestic + Security, contain 2.
def _build_cleanup_crew_lead() -> CardDefinition:
    card = _mnr_card(
        "MNR Cleanup Crew Lead",
        CardType.SCP_PERSONNEL,
        red_tape=1,
        subtypes={"Mnestic", "Security"},
        text=(
            "Mnestic. Contain 2. He has been on the cleanup crew for "
            "longer than the cleanup crew has existed."
        ),
        skills={"contain": 2},
        rarity="uncommon",
        archetype="mnestic_core",
    )
    card.scp_mnestic = True
    return card


_CLEANUP_CREW_LEAD = _build_cleanup_crew_lead()


# 6. Inoculated D-Class — Bystander, flexible 1/1/1, Mnestic Wake.
def _inoculated_d_class_setup(obj: GameObject, state: GameState):
    """Register Mnestic Wake on the D-Class.

    Mnestic Wake is a once-per-game exhaust ability that pays 1 ethics_debt
    to permanently gain Mnestic — flexible bridge card for any deck willing
    to seed ethics on this body and convert it into a Mnestic-tagged
    researcher. Matches helpers._mnestic_wake_ability.
    """
    return [_mnestic_wake_ability(obj, state, ethics_cost=1)]


def _build_inoculated_d_class() -> CardDefinition:
    card = _mnr_card(
        "MNR Inoculated D-Class",
        CardType.SCP_PERSONNEL,
        red_tape=0,
        subtypes={"Bystander", "D-Class"},
        text=(
            "Research 1, contain 1, suppress 1. Mnestic Wake: exhaust, pay "
            "1 ethics debt. Gains Mnestic permanently. Cheap, flexible, "
            "and statistically guaranteed to live through this."
        ),
        skills={"research": 1, "contain": 1, "suppress": 1},
        rarity="common",
        archetype="mnestic_reset",
    )
    card.setup_interceptors = _inoculated_d_class_setup
    return card


_INOCULATED_D_CLASS = _build_inoculated_d_class()


# ---------------------------------------------------------------------------
# Final assembly. 10 procedures + 6 personnel = 16 callbacks.
# ---------------------------------------------------------------------------


CALLBACKS: list[CardDefinition] = [
    # Procedures (10)
    _ANTIMEMETIC_AUDIT,
    _MNESTIC_QUARANTINE,
    _BACKCHANNEL_BRIEF,
    _ANCHOR_RESET,
    _OVEREXPOSURE_PROBE,
    _ROTATION_DRILL,
    _MEMORY_HOLED_AUDIT,
    _MNESTIC_COUNTER_RAID,
    _BRIEF_AND_BURY,
    _WITNESS_ERASURE,
    # Personnel (6)
    _ANCHOR_OPERATIVE,
    _SZB_LIAISON,
    _BYSTANDER_WITNESS_POOL,
    _MNEMONIC_FIELD_AGENT,
    _CLEANUP_CREW_LEAD,
    _INOCULATED_D_CLASS,
]
