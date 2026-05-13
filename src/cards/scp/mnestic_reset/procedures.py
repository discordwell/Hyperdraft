"""MNR procedure sub-set.

Mnestic Reset's offensive toolkit. Six themes interlock:

  1. Redact-heavy (10) — opponent discards + retroactive event tags. Cheap
     RT 0 single-Redact to expensive RT 3 multi-Redact + bonus.
  2. Antimeme-control (6) — reset ``scp_forget_counters`` on one or all of
     your anomalies. "We remember the threat."
  3. Mnestic-recovery (4) — pop an anomaly out of ``state.scp_forgotten``
     back into ``state.scp_anomalies``. Premium, gated on Mnestic presence.
  4. Archive engine (4) — secrecy / archive / breach manipulation,
     MNR-themed (uses the engine's standard ``adjust_site`` /
     ``gain_archives``).
  5. Bystander-themed (4) — cheap RT 0 procedures with Bystander
     personnel synergy. (Bystander is a subtype tag introduced in MNR
     personnel; this checks active personnel subtypes at resolve time.)
  6. Cognitive sweepers (4) — punish opposing antimemetic plays. Add
     forget counters to opposing anomalies (or to one big one), or block
     resets for a turn.

Composition: 32 procedures total. KEEPS the sample ``MNR Memory Triage``
from the seed scaffold.
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

from .helpers import _mnr_card, _redact


# ---------------------------------------------------------------------------
# Local helpers — custom effect_fns shared across multiple procedures.
# ---------------------------------------------------------------------------


def _opponent_id(state: GameState, player_id: str):
    """Return the first non-eliminated opponent, or None."""
    for pid, player in state.players.items():
        if pid == player_id:
            continue
        if getattr(player, "has_lost", False):
            continue
        return pid
    return None


def _site_event(obj: GameObject, event_type: EventType, **payload) -> Event:
    """Shorthand: build an Event with this card as the source/controller."""
    payload.setdefault("player", obj.controller)
    return Event(
        type=event_type,
        payload=payload,
        source=obj.id,
        controller=obj.controller,
    )


def _has_active_subtype(state: GameState, player_id: str, subtype: str) -> bool:
    """True if ``player_id`` has at least one active personnel with ``subtype``."""
    for sid in list(state.scp_personnel.get(player_id, [])):
        s = state.objects.get(sid)
        if not s or s.zone != ZoneType.BATTLEFIELD:
            continue
        if s.state.scp_status != "active":
            continue
        if not s.card_def:
            continue
        subtypes = getattr(s.card_def.characteristics, "subtypes", set()) or set()
        if subtype in subtypes:
            return True
    return False


def _count_active_subtype(state: GameState, player_id: str, subtype: str) -> int:
    """Count active personnel with ``subtype``."""
    total = 0
    for sid in list(state.scp_personnel.get(player_id, [])):
        s = state.objects.get(sid)
        if not s or s.zone != ZoneType.BATTLEFIELD:
            continue
        if s.state.scp_status != "active":
            continue
        if not s.card_def:
            continue
        subtypes = getattr(s.card_def.characteristics, "subtypes", set()) or set()
        if subtype in subtypes:
            total += 1
    return total


def _reset_forget_counters(state: GameState, player_id: str, limit: int | None = None) -> int:
    """Zero out ``scp_forget_counters`` on (at most ``limit``) anomalies.

    Acts on both active and contained anomalies. Returns the count reset.
    If ``limit`` is None, resets all. Picks the highest counter first
    (most-decayed anomaly is the most valuable to refresh).
    """
    candidates: list[tuple[int, GameObject]] = []
    pool: list[str] = []
    pool.extend(list(state.scp_anomalies.get(player_id, [])))
    pool.extend(list(state.scp_contained.get(player_id, [])))
    for aid in pool:
        an = state.objects.get(aid)
        if not an or an.zone != ZoneType.BATTLEFIELD:
            continue
        counter = int(getattr(an.state, "scp_forget_counters", 0) or 0)
        if counter > 0:
            candidates.append((counter, an))
    # Highest counters first (most urgent to reset).
    candidates.sort(key=lambda c: -c[0])
    if limit is not None:
        candidates = candidates[:limit]
    for _, an in candidates:
        an.state.scp_forget_counters = 0
    return len(candidates)


def _bump_opposing_antimeme_counters(
    state: GameState, player_id: str, amount: int = 1, limit: int | None = None,
) -> list[GameObject]:
    """Add ``amount`` to ``scp_forget_counters`` on opposing antimeme anomalies.

    Picks the LOWEST current counter first (so the bump is most likely to
    advance multiple anomalies toward their forget threshold). If ``limit``
    is None, hits all qualifying anomalies.
    """
    opp_id = _opponent_id(state, player_id)
    if opp_id is None:
        return []
    bumped: list[GameObject] = []
    pool: list[str] = []
    pool.extend(list(state.scp_anomalies.get(opp_id, [])))
    pool.extend(list(state.scp_contained.get(opp_id, [])))
    candidates: list[GameObject] = []
    for aid in pool:
        an = state.objects.get(aid)
        if not an or an.zone != ZoneType.BATTLEFIELD:
            continue
        threshold = int(getattr(an.card_def, "scp_antimeme", 0) or 0)
        if threshold <= 0:
            continue
        candidates.append(an)
    # Lowest current counter first.
    candidates.sort(key=lambda a: int(getattr(a.state, "scp_forget_counters", 0) or 0))
    if limit is not None:
        candidates = candidates[:limit]
    for an in candidates:
        prior = int(getattr(an.state, "scp_forget_counters", 0) or 0)
        an.state.scp_forget_counters = prior + amount
        bumped.append(an)
    return bumped


def _recover_forgotten(state: GameState, player_id: str, limit: int = 1) -> list[GameObject]:
    """Move up to ``limit`` anomalies from ``scp_forgotten`` back to ``scp_anomalies``.

    Requires a Mnestic personnel on board (the case files only resurface
    when somebody can remember). Returns the recovered anomaly objects.
    Sets ``scp_status = "active"`` and resets forget counters to 0.
    """
    if limit <= 0:
        return []
    if not scp.has_mnestic(state, player_id):
        return []
    forgotten = state.scp_forgotten.get(player_id, [])
    if not forgotten:
        return []
    recovered: list[GameObject] = []
    # Take from the tail (most-recently forgotten first — feels right
    # narratively, and matches list.pop() semantics).
    while forgotten and len(recovered) < limit:
        aid = forgotten.pop()
        an = state.objects.get(aid)
        if an is None:
            continue
        an.state.scp_status = "active"
        an.state.scp_forget_counters = 0
        active = state.scp_anomalies.setdefault(player_id, [])
        if an.id not in active:
            active.append(an.id)
        recovered.append(an)
    return recovered


# ---------------------------------------------------------------------------
# Effect builders (returned by factories so each card is a fresh closure).
# ---------------------------------------------------------------------------


def _redact_plus_secrecy(redact_n: int, secrecy_delta: int):
    """Redact N + adjust secrecy. Common Redact pattern."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        actual_game = game if game is not None else getattr(state, "_game", None)
        if actual_game is not None:
            events.extend(scp.redact_opposing(actual_game, obj.controller, redact_n, source=obj.id))
        if secrecy_delta:
            scp.site(state, obj.controller)["secrecy"] += secrecy_delta
            events.append(_site_event(
                obj,
                EventType.SCP_BREACH_TICK,
                amount=0,
                reason="redact_plus_secrecy",
                secrecy=scp.site(state, obj.controller)["secrecy"],
            ))
        return events
    return effect


def _redact_plus_opp_secrecy_drop(redact_n: int, opp_secrecy_drop: int):
    """Redact N, then drop opponent's secrecy."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        actual_game = game if game is not None else getattr(state, "_game", None)
        if actual_game is not None:
            events.extend(scp.redact_opposing(actual_game, obj.controller, redact_n, source=obj.id))
        opp_id = _opponent_id(state, obj.controller)
        if opp_id is not None and opp_secrecy_drop:
            scp.site(state, opp_id)["secrecy"] -= opp_secrecy_drop
            events.append(Event(
                type=EventType.SCP_AUDIT,
                payload={
                    "actor": obj.controller,
                    "target": opp_id,
                    "intensity": opp_secrecy_drop,
                    "reason": "redact_pressure",
                    "secrecy": scp.site(state, opp_id)["secrecy"],
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return effect


def _redact_plus_misfile(redact_n: int, misfile_amount: int):
    """Redact N, then add paperwork to opponent's pending dossiers."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        actual_game = game if game is not None else getattr(state, "_game", None)
        if actual_game is not None:
            events.extend(scp.redact_opposing(actual_game, obj.controller, redact_n, source=obj.id))
        opp_id = _opponent_id(state, obj.controller)
        if opp_id is not None and misfile_amount > 0:
            for candidate in list(state.objects.values()):
                if candidate.controller != opp_id:
                    continue
                if candidate.zone != ZoneType.BATTLEFIELD:
                    continue
                if candidate.state.scp_status != "pending":
                    continue
                before = candidate.state.scp_paperwork
                candidate.state.scp_paperwork = before + misfile_amount
                events.append(Event(
                    type=EventType.SCP_PAPERWORK_TICK,
                    payload={
                        "object_id": candidate.id,
                        "from": before,
                        "to": candidate.state.scp_paperwork,
                        "reason": "black_bag_job",
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events
    return effect


def _redact_with_self_reset(redact_n: int):
    """Redact N + reset forget counters on all your anomalies."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        actual_game = game if game is not None else getattr(state, "_game", None)
        if actual_game is not None:
            events.extend(scp.redact_opposing(actual_game, obj.controller, redact_n, source=obj.id))
        reset_count = _reset_forget_counters(state, obj.controller, limit=None)
        events.append(_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="counter_strike_reset",
            reset_count=reset_count,
        ))
        return events
    return effect


def _redact_if_opponent_has_mnestic(redact_n: int):
    """Conditional Redact: only fires if opponent controls a Mnestic personnel."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        actual_game = game if game is not None else getattr(state, "_game", None)
        opp_id = _opponent_id(state, obj.controller)
        if opp_id is None or not scp.has_mnestic(state, opp_id):
            # Whiffed — no Mnestic to walk out on.
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="walk_out_no_target",
                redacted=0,
            )]
        if actual_game is None:
            return []
        return scp.redact_opposing(actual_game, obj.controller, redact_n, source=obj.id)
    return effect


def _reset_self_counters(limit: int | None, archive_or_research: dict | None = None):
    """Zero forget counters on (at most ``limit``) of your anomalies.

    Optional extra: ``archive_or_research`` is a dict like ``{"briefing": 1}``
    or ``{"clearance": 1}`` applied directly to the site. (We piggyback on
    the ``briefing`` and ``clearance`` fields rather than inventing new
    state.)
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        reset_count = _reset_forget_counters(state, obj.controller, limit=limit)
        events.append(_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="remembrance",
            reset_count=reset_count,
            scope="all" if limit is None else f"up_to_{limit}",
        ))
        if archive_or_research:
            s = scp.site(state, obj.controller)
            for key, delta in archive_or_research.items():
                if key in s:
                    s[key] = max(0, s[key] + delta)
                    events.append(_site_event(
                        obj,
                        EventType.SCP_BREACH_TICK,
                        amount=0,
                        reason="remembrance_bonus",
                        bonus_key=key,
                        bonus_value=s[key],
                    ))
        return events
    return effect


def _reset_one_plus_briefing():
    """Reset 1 anomaly's counter + gain a briefing token."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        reset_count = _reset_forget_counters(state, obj.controller, limit=1)
        s = scp.site(state, obj.controller)
        s["briefing"] += 1
        events.append(_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="pattern_recognition",
            reset_count=reset_count,
            briefing=s["briefing"],
        ))
        return events
    return effect


def _mnestic_dust_cloud():
    """Reset 1 + secrecy -1 (cheap, sketchy)."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        reset_count = _reset_forget_counters(state, obj.controller, limit=1)
        s = scp.site(state, obj.controller)
        s["secrecy"] -= 1
        events.append(_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="dust_cloud",
            reset_count=reset_count,
            secrecy=s["secrecy"],
        ))
        return events
    return effect


def _recover_n(n: int):
    """Pull ``n`` anomalies out of scp_forgotten if a Mnestic personnel is active."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        recovered = _recover_forgotten(state, obj.controller, limit=n)
        if not recovered:
            # Whiffed (no Mnestic OR no forgotten).
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="recovery_failed",
                recovered=0,
            )]
        events: list[Event] = []
        for an in recovered:
            events.append(Event(
                type=EventType.SCP_ANOMALY_REVEALED,
                payload={
                    "player": obj.controller,
                    "object_id": an.id,
                    "reason": "mnestic_recovery",
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return effect


def _recover_plus_bonus(n: int, *, secrecy: int = 0, briefing: int = 0):
    """Recover ``n`` + side effect (secrecy delta and/or briefing)."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        events: list[Event] = []
        recovered = _recover_forgotten(state, obj.controller, limit=n)
        for an in recovered:
            events.append(Event(
                type=EventType.SCP_ANOMALY_REVEALED,
                payload={
                    "player": obj.controller,
                    "object_id": an.id,
                    "reason": "mnestic_recovery_plus",
                },
                source=obj.id,
                controller=obj.controller,
            ))
        s = scp.site(state, obj.controller)
        if secrecy:
            s["secrecy"] += secrecy
        if briefing:
            s["briefing"] += briefing
        events.append(_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="recovery_bonus",
            recovered=len(recovered),
            secrecy=s["secrecy"],
            briefing=s["briefing"],
        ))
        return events
    return effect


def _adjust_site(*, secrecy: int = 0, breach: int = 0, ethics: int = 0, clearance: int = 0):
    """Plain site-clock manipulation. Matches the CORE ``_adjust_site``."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["secrecy"] += secrecy
        s["breach"] = max(0, s["breach"] + breach)
        s["ethics_debt"] = max(0, s["ethics_debt"] + ethics)
        s["clearance"] = max(0, s["clearance"] + clearance)
        return [_site_event(
            obj,
            EventType.SCP_BREACH_TICK,
            amount=0,
            reason="mnr_adjust_site",
            breach=s["breach"],
            secrecy=s["secrecy"],
        )]
    return effect


def _briefing_update():
    """Gain a briefing token."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["briefing"] += 1
        return [_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="briefing_update",
            briefing=s["briefing"],
        )]
    return effect


def _archive_and_breach():
    """Gain 1 archive, +1 breach (the price of indexing)."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["breach"] += 1
        if game is not None:
            return scp.gain_archives(game, obj.controller, 1, source=obj.id)
        s["archives"] += 1
        return [_site_event(
            obj,
            EventType.SCP_ARCHIVE_GAINED,
            amount=1,
            reason="antimemetic_brief_box",
            archives=s["archives"],
        )]
    return effect


def _bystander_briefing():
    """Briefing +1 only if a Bystander is active."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        if not _has_active_subtype(state, obj.controller, "Bystander"):
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="office_memo_whiff",
                briefing_gained=0,
            )]
        s = scp.site(state, obj.controller)
        s["briefing"] += 1
        return [_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="office_memo",
            briefing=s["briefing"],
        )]
    return effect


def _bystander_roll_call():
    """Briefing +2 if 2+ Bystanders active, else +1 if any."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        count = _count_active_subtype(state, obj.controller, "Bystander")
        s = scp.site(state, obj.controller)
        gained = 2 if count >= 2 else (1 if count >= 1 else 0)
        s["briefing"] += gained
        return [_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="roll_call",
            bystanders=count,
            briefing_gained=gained,
        )]
    return effect


def _bystander_exhaust_for_secrecy():
    """Exhaust the first un-exhausted Bystander for secrecy +1."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        target = None
        for sid in list(state.scp_personnel.get(obj.controller, [])):
            staff = state.objects.get(sid)
            if not staff or staff.zone != ZoneType.BATTLEFIELD:
                continue
            if staff.state.scp_status != "active":
                continue
            if staff.state.scp_exhausted:
                continue
            if not staff.card_def:
                continue
            subtypes = getattr(staff.card_def.characteristics, "subtypes", set()) or set()
            if "Bystander" in subtypes:
                target = staff
                break
        if target is None:
            return [_site_event(
                obj,
                EventType.SCP_INCIDENT_RESOLVED,
                reason="untrained_assignment_whiff",
            )]
        target.state.scp_exhausted = True
        s = scp.site(state, obj.controller)
        s["secrecy"] += 1
        return [_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="untrained_assignment",
            exhausted=target.id,
            secrecy=s["secrecy"],
        )]
    return effect


def _bystander_headcount():
    """Archive +1 (gain_archives) if Bystander active, else secrecy +1."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        if _has_active_subtype(state, obj.controller, "Bystander"):
            if game is not None:
                return scp.gain_archives(game, obj.controller, 1, source=obj.id)
            scp.site(state, obj.controller)["archives"] += 1
            return [_site_event(
                obj,
                EventType.SCP_ARCHIVE_GAINED,
                amount=1,
                reason="headcount_audit",
                archives=scp.site(state, obj.controller)["archives"],
            )]
        s = scp.site(state, obj.controller)
        s["secrecy"] += 1
        return [_site_event(
            obj,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="headcount_no_bystander",
            secrecy=s["secrecy"],
        )]
    return effect


def _bump_all_opposing_antimeme():
    """+1 forget counter on every opposing antimeme anomaly."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        bumped = _bump_opposing_antimeme_counters(state, obj.controller, amount=1, limit=None)
        return [_site_event(
            obj,
            EventType.SCP_COG_HAZARD_TICK,
            reason="class_b_drill",
            bumped=len(bumped),
            bumped_ids=[a.id for a in bumped],
        )]
    return effect


def _bump_single_opposing(amount: int):
    """+``amount`` forget counter on one opposing antimeme anomaly (lowest first)."""
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        bumped = _bump_opposing_antimeme_counters(state, obj.controller, amount=amount, limit=1)
        return [_site_event(
            obj,
            EventType.SCP_COG_HAZARD_TICK,
            reason="cognitive_cleanse",
            bumped=len(bumped),
            amount=amount,
            bumped_ids=[a.id for a in bumped],
        )]
    return effect


def _pattern_disruption():
    """+1 on one opposing antimeme + plant a marker that opp can't reset this turn.

    The marker is a soft state flag (``mnr_no_reset_this_turn``) on the
    opponent's site dict. Future MNR resets can read it; the engine
    itself ignores it. The pragmatic effect is still the +1 bump.
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        bumped = _bump_opposing_antimeme_counters(state, obj.controller, amount=1, limit=1)
        opp_id = _opponent_id(state, obj.controller)
        if opp_id is not None:
            scp.site(state, opp_id)["mnr_no_reset_this_turn"] = True
        return [_site_event(
            obj,
            EventType.SCP_COG_HAZARD_TICK,
            reason="pattern_disruption",
            bumped=len(bumped),
            target=opp_id,
        )]
    return effect


def _antimemetic_defense_brief():
    """+1 forget counter on opponent's most-recently-revealed antimeme anomaly.

    "Defense brief" thematically: we pre-charge the paperwork so the
    next antimeme reveal is already advanced. Implementation targets the
    most-recently added id to scp_anomalies (= last reveal).
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        opp_id = _opponent_id(state, obj.controller)
        if opp_id is None:
            return [_site_event(obj, EventType.SCP_COG_HAZARD_TICK, reason="defense_brief_no_opp")]
        # Walk opponent's anomalies newest-first.
        anom_list = list(state.scp_anomalies.get(opp_id, []))
        target = None
        for aid in reversed(anom_list):
            an = state.objects.get(aid)
            if not an or an.zone != ZoneType.BATTLEFIELD:
                continue
            threshold = int(getattr(an.card_def, "scp_antimeme", 0) or 0)
            if threshold > 0:
                target = an
                break
        if target is None:
            return [_site_event(
                obj,
                EventType.SCP_COG_HAZARD_TICK,
                reason="defense_brief_no_antimeme",
            )]
        prior = int(getattr(target.state, "scp_forget_counters", 0) or 0)
        target.state.scp_forget_counters = prior + 1
        return [_site_event(
            obj,
            EventType.SCP_COG_HAZARD_TICK,
            reason="defense_brief",
            target=target.id,
            counter=target.state.scp_forget_counters,
        )]
    return effect


# ---------------------------------------------------------------------------
# Procedure list
# ---------------------------------------------------------------------------


# Keep the seed card — it's referenced by tests/test_scp_tcg.py.
_MEMORY_TRIAGE = _mnr_card(
    "MNR Memory Triage",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Redaction", "Mnemonic"},
    text="Redact 1: each opponent discards a card.",
    effect=_redact(1),
    rarity="common",
    archetype="redaction_press",
)


PROCEDURES: list[CardDefinition] = [
    _MEMORY_TRIAGE,
    # ------------------------------------------------------------------
    # Redact-heavy (10)
    # ------------------------------------------------------------------
    _mnr_card(
        "MNR Memo Disposal",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Redaction"},
        text="Redact 1. (Opponent discards 1; recent events affecting them tagged redacted.)",
        effect=_redact(1),
        rarity="common",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Class-A Inoculation Dose",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Redaction", "Amnestic"},
        text="Redact 1 and your Site gains secrecy +1.",
        effect=_redact_plus_secrecy(1, 1),
        rarity="common",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Selective Forgetting",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Redaction", "Memetics"},
        text="Redact 2. (A surgical strike on opposing memory.)",
        effect=_redact(2),
        rarity="uncommon",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Operative Erasure",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Redaction", "Cover"},
        text="Redact 2 and opposing Site loses 1 secrecy.",
        effect=_redact_plus_opp_secrecy_drop(2, 1),
        rarity="uncommon",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Conference Redaction",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=1,
        subtypes={"Redaction", "Bureaucracy"},
        text="Redact 3.",
        effect=_redact(3),
        rarity="rare",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Black-Bag Job",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Redaction", "Operative"},
        text="Redact 1 and add 2 paperwork to each of the opposing pending dossiers.",
        effect=_redact_plus_misfile(1, 2),
        rarity="uncommon",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Records Burn",
        CardType.SCP_PROCEDURE,
        red_tape=3,
        subtypes={"Redaction", "Archive"},
        text="Redact 3 and your Site gains secrecy +2.",
        effect=_redact_plus_secrecy(3, 2),
        rarity="rare",
        archetype="redaction_press",
    ),
    _mnr_card(
        "MNR Mnestic Counter-Strike",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Redaction", "Mnestic"},
        text="Redact 1 and reset forget counters on all your anomalies. (We strike, we remember.)",
        effect=_redact_with_self_reset(1),
        rarity="uncommon",
        archetype="mnestic_core",
    ),
    _mnr_card(
        "MNR Walk-Out Order",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Redaction", "Operative"},
        text="If any opposing personnel is Mnestic, Redact 1. Otherwise this procedure does nothing.",
        effect=_redact_if_opponent_has_mnestic(1),
        rarity="common",
        archetype="redaction_press",
    ),
    # ------------------------------------------------------------------
    # Antimeme-control (6)
    # ------------------------------------------------------------------
    _mnr_card(
        "MNR Pattern Recognition Drill",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Mnemonic", "Training"},
        text="Reset forget counters on one of your active anomalies.",
        effect=_reset_self_counters(limit=1),
        rarity="common",
        archetype="mnestic_core",
    ),
    _mnr_card(
        "MNR Antimemetic Tracker",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Mnemonic", "Research"},
        text="Reset forget counters on one of your anomalies and gain a briefing token.",
        effect=_reset_one_plus_briefing(),
        rarity="uncommon",
        archetype="mnestic_core",
    ),
    _mnr_card(
        "MNR Mass Remembrance",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=1,
        subtypes={"Mnemonic", "Mnestic"},
        text="Reset forget counters on all your active anomalies. (We remember now.)",
        effect=_reset_self_counters(limit=None),
        rarity="rare",
        archetype="mnestic_core",
    ),
    _mnr_card(
        "MNR Inoculation Wave",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=1,
        subtypes={"Mnestic", "Amnestic"},
        text="Reset forget counters on all your anomalies; gain a briefing token.",
        effect=_reset_self_counters(limit=None, archive_or_research={"briefing": 1}),
        rarity="rare",
        archetype="mnestic_core",
    ),
    _mnr_card(
        "MNR Mnestic Dust Cloud",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Mnemonic", "Cover"},
        text="Reset forget counters on one of your anomalies; your Site loses 1 secrecy.",
        effect=_mnestic_dust_cloud(),
        rarity="common",
        archetype="mnestic_core",
    ),
    _mnr_card(
        "MNR Standard Protocol Refresh",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Mnemonic", "Bureaucracy"},
        text="Reset forget counters on one of your anomalies.",
        effect=_reset_self_counters(limit=1),
        rarity="common",
        archetype="mnestic_core",
    ),
    # ------------------------------------------------------------------
    # Mnestic-recovery (4) — pop forgotten back to active
    # ------------------------------------------------------------------
    _mnr_card(
        "MNR Found Files",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Recovery", "Archive"},
        text="If a Mnestic personnel is active, return one of your forgotten anomalies to play active.",
        effect=_recover_n(1),
        rarity="rare",
        archetype="mnestic_wake",
    ),
    _mnr_card(
        "MNR Reconstruction Project",
        CardType.SCP_PROCEDURE,
        red_tape=3,
        clearance=1,
        subtypes={"Recovery", "Archive", "Mnestic"},
        text="If a Mnestic personnel is active, return 2 of your forgotten anomalies to play active; your Site loses 1 secrecy.",
        effect=_recover_plus_bonus(2, secrecy=-1, briefing=0),
        rarity="rare",
        archetype="mnestic_wake",
    ),
    _mnr_card(
        "MNR Director's Memo",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=1,
        subtypes={"Recovery", "Mandate"},
        text="If a Mnestic personnel is active, return one of your forgotten anomalies and gain a briefing token.",
        effect=_recover_plus_bonus(1, secrecy=0, briefing=1),
        rarity="rare",
        archetype="mnestic_wake",
    ),
    _mnr_card(
        "MNR Cold Trail Reopened",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Recovery", "Investigation"},
        text="If a Mnestic personnel is active, return one of your forgotten anomalies to play active.",
        effect=_recover_n(1),
        rarity="uncommon",
        archetype="mnestic_wake",
    ),
    # ------------------------------------------------------------------
    # Archive engine (4) — site-clock manipulation
    # ------------------------------------------------------------------
    _mnr_card(
        "MNR Cold Storage Open",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Archive", "Security"},
        text="Secrecy +2.",
        effect=_adjust_site(secrecy=2),
        rarity="common",
        archetype="mnestic_reset",
    ),
    _mnr_card(
        "MNR Briefing Update",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Briefing"},
        text="Gain a briefing token.",
        effect=_briefing_update(),
        rarity="common",
        archetype="mnestic_reset",
    ),
    _mnr_card(
        "MNR Inoculation Schedule",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Ethics", "Medical"},
        text="Ethics debt -1.",
        effect=_adjust_site(ethics=-1),
        rarity="common",
        archetype="mnestic_reset",
    ),
    _mnr_card(
        "MNR Antimemetic Brief Box",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Archive", "Research"},
        text="Gain 1 archive; breach +1.",
        effect=_archive_and_breach(),
        rarity="uncommon",
        archetype="mnestic_reset",
    ),
    # ------------------------------------------------------------------
    # Bystander-themed (4)
    # ------------------------------------------------------------------
    _mnr_card(
        "MNR Office Memo",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Bureaucracy"},
        text="If a Bystander personnel is active, gain a briefing token.",
        effect=_bystander_briefing(),
        rarity="common",
        archetype="bystander_synergy",
    ),
    _mnr_card(
        "MNR Department Roll Call",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Bureaucracy"},
        text="Gain a briefing token; gain another if 2+ Bystander personnel are active.",
        effect=_bystander_roll_call(),
        rarity="common",
        archetype="bystander_synergy",
    ),
    _mnr_card(
        "MNR Untrained Assignment",
        CardType.SCP_PROCEDURE,
        red_tape=0,
        subtypes={"Cover"},
        text="Exhaust one of your active Bystander personnel: secrecy +1.",
        effect=_bystander_exhaust_for_secrecy(),
        rarity="common",
        archetype="bystander_synergy",
    ),
    _mnr_card(
        "MNR Headcount Audit",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Audit", "Bureaucracy"},
        text="If a Bystander personnel is active, gain 1 archive; otherwise secrecy +1.",
        effect=_bystander_headcount(),
        rarity="uncommon",
        archetype="bystander_synergy",
    ),
    # ------------------------------------------------------------------
    # Cognitive sweepers (4) — punish opposing antimemetic plays
    # ------------------------------------------------------------------
    _mnr_card(
        "MNR Class-B Inoculation Drill",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        subtypes={"Memetics", "Training"},
        text="Every opposing antimemetic anomaly gains a forget counter immediately.",
        effect=_bump_all_opposing_antimeme(),
        rarity="rare",
        archetype="antimeme_decay",
    ),
    _mnr_card(
        "MNR Cognitive Cleanse",
        CardType.SCP_PROCEDURE,
        red_tape=2,
        clearance=1,
        subtypes={"Memetics", "Counter"},
        text="One opposing antimemetic anomaly gains 2 forget counters.",
        effect=_bump_single_opposing(2),
        rarity="rare",
        archetype="antimeme_decay",
    ),
    _mnr_card(
        "MNR Pattern Disruption",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Memetics", "Counter"},
        text="One opposing antimemetic anomaly gains a forget counter; opponent's Site is flagged 'no reset this turn'.",
        effect=_pattern_disruption(),
        rarity="uncommon",
        archetype="antimeme_decay",
    ),
    _mnr_card(
        "MNR Antimemetic Defense Brief",
        CardType.SCP_PROCEDURE,
        red_tape=1,
        subtypes={"Memetics", "Briefing"},
        text="Opponent's most-recently-revealed antimemetic anomaly gains a forget counter.",
        effect=_antimemetic_defense_brief(),
        rarity="uncommon",
        archetype="antimeme_decay",
    ),
]
