"""Site Zero: Broken Masquerade expansion for SCP Containment TCG.

This set is intentionally callback-heavy. The printed mechanics below are SCP
mode shorthand for operations the engine already simulates:

- Brief N: add briefing tokens for mood shifts and incident play.
- Blackfile N: add paperwork to rival pending dossiers, auditing if none exist.
- Anchor: turn contained anomalies into cross-containment countermeasures.
- Quarantine: reveal anomalies in safer moods/protocols instead of raw hazard.
- Overexpose: trade secrecy or ethics pressure for archives/clearance tempo.
- Rotation: refresh staff or assignment slots for burst turns.

Some cards use deterministic "best available" targets because SCP procedures do
not currently prompt for modal or target choices. The approximation is kept
near each helper and favors the board state the AI can already evaluate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.engine.types import CardDefinition, CardType, Event, EventType, GameObject, GameState, ZoneType
from src.engine import scp


EXPANSION = "Site Zero: Broken Masquerade"
EXPANSION_CODE = "SZB"


def _site_event(event_type, obj: GameObject, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(type=event_type, payload=payload, source=obj.id, controller=obj.controller)


def _opponent(state: GameState, player_id: str) -> str | None:
    return next((pid for pid, player in state.players.items() if pid != player_id and not player.has_lost), None)


def _active_anomalies(state: GameState, player_id: str) -> list[GameObject]:
    return [
        state.objects[aid]
        for aid in state.scp_anomalies.get(player_id, [])
        if aid in state.objects and state.objects[aid].zone == ZoneType.BATTLEFIELD and state.objects[aid].state.scp_status == "active"
    ]


def _contained_anomalies(state: GameState, player_id: str) -> list[GameObject]:
    return [
        state.objects[aid]
        for aid in state.scp_contained.get(player_id, [])
        if aid in state.objects and state.objects[aid].zone == ZoneType.BATTLEFIELD and state.objects[aid].state.scp_status == "contained"
    ]


def _pending_dossiers(state: GameState, player_id: str) -> list[GameObject]:
    return [
        obj for obj in state.objects.values()
        if obj.controller == player_id and obj.zone == ZoneType.BATTLEFIELD and obj.state.scp_status == "pending"
    ]


def _with_metadata(
    card: CardDefinition,
    *,
    archetype: str,
    keywords: set[str],
    art_prompt: str | None = None,
) -> CardDefinition:
    card.scp_expansion = EXPANSION
    card.scp_expansion_code = EXPANSION_CODE
    card.scp_archetype = archetype
    card.scp_keywords = sorted(keywords)
    card.scp_art_prompt = art_prompt or (
        f"Original SCP-inspired trading card art for {card.name} from Site Zero: Broken Masquerade. "
        f"Classified containment facility under public crisis, clear focal subject, no text or logos."
    )
    return card


def _make_card(
    name: str,
    card_type: CardType,
    *,
    archetype: str,
    keywords: set[str],
    text: str,
    subtypes: set[str],
    red_tape: int = 0,
    clearance: int = 0,
    containment: int = 0,
    curiosity: int = 0,
    hazard: int = 0,
    skills: dict[str, int] | None = None,
    bonus: dict[str, int] | None = None,
    rarity: str | None = None,
    on_reveal=None,
    on_contain=None,
    on_test=None,
    effect=None,
) -> CardDefinition:
    return _with_metadata(
        scp.make_scp_card(
            name,
            card_type,
            red_tape=red_tape,
            clearance=clearance,
            containment=containment,
            curiosity=curiosity,
            hazard=hazard,
            skills=skills,
            bonus=bonus,
            subtypes=subtypes,
            text=text,
            rarity=rarity,
            on_reveal=on_reveal,
            on_contain=on_contain,
            on_test=on_test,
            effect=effect,
        ),
        archetype=archetype,
        keywords=keywords,
    )


def _brief(amount: int):
    def hook(obj: GameObject, state: GameState) -> list[Event]:
        site = scp.site(state, obj.controller)
        site["briefing"] += amount
        return [_site_event(EventType.SCP_INCIDENT_RESOLVED, obj, reason="brief", briefing=site["briefing"])]

    return hook


def _quarantine(mood: str, protocol: str, briefing: int = 0):
    def hook(obj: GameObject, state: GameState) -> list[Event]:
        obj.state.scp_mood = mood
        if protocol not in obj.state.scp_protocols:
            obj.state.scp_protocols.append(protocol)
        site = scp.site(state, obj.controller)
        site["briefing"] += briefing
        return [_site_event(EventType.SCP_MOOD_SHIFT, obj, to=mood, protocol=protocol, briefing=site["briefing"])]

    return hook


def _redaction_test(obj: GameObject, state: GameState) -> list[Event]:
    site = scp.site(state, obj.controller)
    site["secrecy"] += 1
    site["briefing"] += 1
    return [_site_event(EventType.SCP_ARCHIVE_GAINED, obj, reason="redaction_test", secrecy=site["secrecy"], briefing=site["briefing"])]


def _ethics_test(obj: GameObject, state: GameState) -> list[Event]:
    site = scp.site(state, obj.controller)
    if site["ethics_debt"] > 0:
        site["ethics_debt"] = max(0, site["ethics_debt"] - 1)
        site["secrecy"] += 1
    else:
        site["briefing"] += 1
    return [_site_event(EventType.SCP_ETHICS_SPENT, obj, mode="testimony", ethics_debt=site["ethics_debt"])]


def _archive_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    site = scp.site(state, obj.controller)
    site["breach"] = max(0, site["breach"] - 1)
    site["briefing"] += 1
    return [_site_event(EventType.SCP_CONTAINED, obj, reason="clean_containment", breach=site["breach"])]


def _anchor_resolve(anchor_id: str, target_id: str, controller: str, state: GameState) -> list[Event]:
    """Bind the chosen active anomaly to the anchoring contained one + bleed off 1 breach."""
    target = state.objects.get(target_id)
    anchor = state.objects.get(anchor_id)
    if target is None or anchor is None:
        return []
    target.state.scp_bound_to = anchor_id
    site = scp.site(state, controller)
    site["breach"] = max(0, site["breach"] - 1)
    return [Event(
        type=EventType.SCP_CROSS_CONTAINMENT,
        payload={"player": controller, "contained_id": anchor_id, "active_id": target_id},
        source=anchor_id,
        controller=controller,
    )]


def _anchor_on_contain(obj: GameObject, state: GameState) -> list[Event]:
    """First demo of the cross-engine PendingChoice primitive in SCP.

    When the Anchor procedure contains an anomaly, the controlling player
    chooses which active anomaly to bind it to (was: auto-pick the
    highest-hazard active anomaly). For AI players, the heuristic is
    preserved via ``heuristic_pick``, so existing AI behavior doesn't
    change. Humans now get a real choice.
    """
    active = [candidate for candidate in _active_anomalies(state, obj.controller) if candidate.id != obj.id]
    if not active:
        return _archive_on_contain(obj, state)

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    options = [
        {
            "id": a.id,
            "label": getattr(a.card_def, "name", a.id),
            "description": f"Hazard {getattr(a.card_def, 'scp_hazard', 0)} · Mood {a.state.scp_mood or 'neutral'}",
        }
        for a in active
    ]
    best = max(active, key=lambda a: int(getattr(a.card_def, "scp_hazard", 0) or 0))

    def _resolve_handler(choice, selected, st):
        target_id = selected[0] if selected else best.id
        # Tolerate raw or {id: ...} selection shapes.
        if isinstance(target_id, dict):
            target_id = target_id.get("id", best.id)
        return _anchor_resolve(obj.id, target_id, obj.controller, st)

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=obj.controller,
        prompt="Bind which active anomaly to this containment?",
        options=options,
        source_id=obj.id,
        min_choices=1,
        max_choices=1,
        handler=_resolve_handler,
        heuristic_pick=[best.id],
    )


def _resolve_blackfile(
    actor_id: str,
    target_id: str,
    opponent_id: str,
    amount: int,
    archive: bool,
    source_id: str,
    game,
) -> list[Event]:
    """Apply a misfile to ``target_id``, audit the opponent, optionally gain archives."""
    _ok, _message, events = scp.misfile_dossier(game, actor_id, target_id, amount=amount, source=source_id)
    events.extend(scp.force_audit(game, actor_id, opponent_id, intensity=1, source=source_id))
    if archive:
        events.extend(scp.gain_archives(game, actor_id, 1, source=source_id))
    return events


def _blackfile_procedure(amount: int = 2, *, archive: bool = False):
    """Blackfile NN procedure: player chooses which opponent pending dossier to misfile.

    Migrated to PendingChoice — was deterministic ``pending[0]``. AI preserves
    the original behavior via ``heuristic_pick``. Humans get a real prompt.
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        opponent = _opponent(state, obj.controller)
        if game is None or not opponent:
            return []
        pending = _pending_dossiers(state, opponent)
        if not pending:
            events = scp.force_audit(game, obj.controller, opponent, intensity=amount, source=obj.id)
            if archive:
                events.extend(scp.gain_archives(game, obj.controller, 1, source=obj.id))
            return events

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        best = pending[0]
        options = [
            {
                "id": p.id,
                "label": getattr(p.card_def, "name", p.id) if p.card_def else p.id,
                "description": f"Paperwork {p.state.scp_paperwork}",
            }
            for p in pending
        ]

        def _resolve_handler(choice, selected, st):
            target_id = selected[0] if selected else best.id
            if isinstance(target_id, dict):
                target_id = target_id.get("id", best.id)
            return _resolve_blackfile(
                obj.controller, target_id, opponent, amount, archive, obj.id, game,
            )

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=obj.controller,
            prompt=f"Choose an opposing pending dossier to misfile (+{amount} paperwork)",
            options=options,
            source_id=obj.id,
            min_choices=1,
            max_choices=1,
            handler=_resolve_handler,
            heuristic_pick=[best.id],
        )

    return effect


def _gain_archives_and_brief(archives: int, briefing: int, *, breach: int = 0, secrecy: int = 0, ethics: int = 0):
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        site = scp.site(state, obj.controller)
        site["briefing"] += briefing
        site["breach"] = max(0, site["breach"] + breach)
        site["secrecy"] += secrecy
        site["ethics_debt"] = max(0, site["ethics_debt"] + ethics)
        if game is not None and archives:
            return scp.gain_archives(game, obj.controller, archives, source=obj.id)
        if archives:
            site["archives"] += archives
            return [_site_event(EventType.SCP_ARCHIVE_GAINED, obj, amount=archives, archives=site["archives"])]
        return [_site_event(EventType.SCP_INCIDENT_RESOLVED, obj, reason="brief", briefing=site["briefing"])]

    return effect


def _resolve_quarantine(
    obj: GameObject, target_id: str, protocol: str, mood: str, state: GameState, game=None,
) -> list[Event]:
    """Apply a protocol/mood to ``target_id``; ``game`` enables the engine path."""
    target = state.objects.get(target_id)
    if target is None:
        return []
    if game is not None:
        ok, _message, events = scp.apply_protocol(game, obj.controller, target.id, protocol, source=obj.id)
        if ok:
            target.state.scp_mood = mood
            events.extend(game.emit(Event(
                type=EventType.SCP_MOOD_SHIFT,
                payload={"object_id": target.id, "to": mood},
                source=obj.id,
                controller=obj.controller,
            )))
            return events
    target.state.scp_mood = mood
    if protocol not in target.state.scp_protocols:
        target.state.scp_protocols.append(protocol)
    return [_site_event(EventType.SCP_PROTOCOL_APPLIED, obj, anomaly_id=target.id, protocol=protocol)]


def _quarantine_procedure(protocol: str, mood: str):
    """Quarantine procedure: player chooses which active anomaly receives ``protocol``+``mood``.

    Migrated to PendingChoice — was a deterministic max-hazard pick. AI keeps
    the same target via ``heuristic_pick``; humans see a real prompt.
    """
    def effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
        active = _active_anomalies(state, obj.controller)
        if not active:
            scp.site(state, obj.controller)["briefing"] += 1
            return [_site_event(EventType.SCP_INCIDENT_RESOLVED, obj, reason="empty_quarantine")]

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        best = max(active, key=lambda a: int(getattr(a.card_def, "scp_hazard", 0) or 0))
        options = [
            {
                "id": a.id,
                "label": getattr(a.card_def, "name", a.id) if a.card_def else a.id,
                "description": f"Hazard {getattr(a.card_def, 'scp_hazard', 0)} · Mood {a.state.scp_mood or 'neutral'}",
            }
            for a in active
        ]

        def _resolve_handler(choice, selected, st):
            target_id = selected[0] if selected else best.id
            if isinstance(target_id, dict):
                target_id = target_id.get("id", best.id)
            return _resolve_quarantine(obj, target_id, protocol, mood, st, game)

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=obj.controller,
            prompt=f"Quarantine which active anomaly? (apply {protocol}, mood {mood})",
            options=options,
            source_id=obj.id,
            min_choices=1,
            max_choices=1,
            handler=_resolve_handler,
            heuristic_pick=[best.id],
        )

    return effect


def _resolve_anchor(
    obj: GameObject, source_id: str, target_id: str, state: GameState, game=None,
) -> list[Event]:
    """Cross-contain ``source_id`` (contained) and ``target_id`` (active)."""
    source = state.objects.get(source_id)
    target = state.objects.get(target_id)
    if source is None or target is None:
        return []
    if game is not None:
        ok, _message, events = scp.cross_contain(game, obj.controller, source.id, target.id, source=obj.id)
        if ok:
            events.extend(scp.gain_archives(game, obj.controller, 1, source=obj.id))
            return events
    target.state.scp_bound_to = source.id
    scp.site(state, obj.controller)["archives"] += 1
    return [_site_event(EventType.SCP_CROSS_CONTAINMENT, obj, contained_id=source.id, active_id=target.id)]


def _anchor_procedure(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Anchor procedure: player chooses which active anomaly to bind.

    The contained "source" is still auto-picked as max-hazard (the obvious
    pick — bind the worst active threat to the best containment shield).
    Migrated to PendingChoice for the TARGET active anomaly. AI preserves
    the original behavior via ``heuristic_pick``.
    """
    contained = _contained_anomalies(state, obj.controller)
    active = _active_anomalies(state, obj.controller)
    if not contained or not active:
        scp.site(state, obj.controller)["breach"] = max(0, scp.site(state, obj.controller)["breach"] - 2)
        return [_site_event(EventType.SCP_BREACH_TICK, obj, reason="anchor_no_pair")]

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    source = max(contained, key=lambda a: int(getattr(a.card_def, "scp_hazard", 0) or 0))
    best_target = max(active, key=lambda a: int(getattr(a.card_def, "scp_hazard", 0) or 0))
    options = [
        {
            "id": a.id,
            "label": getattr(a.card_def, "name", a.id) if a.card_def else a.id,
            "description": f"Hazard {getattr(a.card_def, 'scp_hazard', 0)} · Mood {a.state.scp_mood or 'neutral'}",
        }
        for a in active
    ]

    def _resolve_handler(choice, selected, st):
        target_id = selected[0] if selected else best_target.id
        if isinstance(target_id, dict):
            target_id = target_id.get("id", best_target.id)
        return _resolve_anchor(obj, source.id, target_id, st, game)

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=obj.controller,
        prompt=f"Anchor: bind which active anomaly to {getattr(source.card_def, 'name', source.id)}?",
        options=options,
        source_id=obj.id,
        min_choices=1,
        max_choices=1,
        handler=_resolve_handler,
        heuristic_pick=[best_target.id],
    )


def _rotation_procedure(obj: GameObject, state: GameState, game=None) -> list[Event]:
    site = scp.site(state, obj.controller)
    site["briefing"] += 1
    if site["assignments_used"] > 0:
        site["assignments_used"] -= 1
    refreshed = 0
    for staff_id in list(state.scp_personnel.get(obj.controller, [])):
        staff = state.objects.get(staff_id)
        if staff and staff.state.scp_exhausted:
            staff.state.scp_exhausted = False
            refreshed += 1
            break
    return [_site_event(
        EventType.SCP_INCIDENT_RESOLVED,
        obj,
        reason="rotation",
        refreshed=refreshed,
        assignments_used=site["assignments_used"],
    )]


def _overexpose_procedure(obj: GameObject, state: GameState, game=None) -> list[Event]:
    site = scp.site(state, obj.controller)
    site["secrecy"] -= 2
    site["clearance"] += 1
    if game is not None:
        return scp.gain_archives(game, obj.controller, 1, source=obj.id)
    site["archives"] += 1
    return [_site_event(EventType.SCP_ARCHIVE_GAINED, obj, amount=1, archives=site["archives"])]


def _goi_counterraid(obj: GameObject, state: GameState, game=None) -> list[Event]:
    opponent = _opponent(state, obj.controller)
    if game is None or not opponent:
        return []
    events = scp.goi_raid(game, opponent, faction="Site Zero Counter-Raid", source=obj.id)
    scp.site(state, obj.controller)["briefing"] += 1
    events.extend(scp.gain_archives(game, obj.controller, 1, source=obj.id))
    return events


def _ethics_discharge(obj: GameObject, state: GameState, game=None) -> list[Event]:
    site = scp.site(state, obj.controller)
    if site["ethics_debt"] >= 2 and game is not None:
        ok, _message, events = scp.spend_ethics(game, obj.controller, 2, mode="erase_breach", source=obj.id)
        if ok:
            events.extend(scp.gain_archives(game, obj.controller, 1, source=obj.id))
            return events
    site["ethics_debt"] += 1
    site["breach"] = max(0, site["breach"] - 3)
    return [_site_event(EventType.SCP_ETHICS_SPENT, obj, mode="discharge", ethics_debt=site["ethics_debt"])]


def _mandate_alt_win(archetype: str) -> str | None:
    return {
        "broken_masquerade": "public_panic",
        "thaumiel_grid": "thaumiel",
        "mnestic_quarantine": "redaction",
        "clean_hands": "ethics_audit",
    }.get(archetype)


DIVISIONS: list[dict[str, Any]] = [
    {
        "archetype": "broken_masquerade",
        "task": "suppress",
        "secondary": "research",
        "subtype": "Masquerade",
        "keywords": {"Blackfile", "Overexpose"},
        "motifs": [
            "Press Conference", "Glass Newsroom", "Witness Stampede", "Leaked Siren", "Civic Panic",
            "Camera Choir", "Broadcast Bunker", "Open Records", "Crowd of Doubles", "Broken Curfew",
        ],
    },
    {
        "archetype": "mnestic_quarantine",
        "task": "research",
        "secondary": "suppress",
        "subtype": "Mnestic",
        "keywords": {"Brief", "Quarantine"},
        "motifs": [
            "White Pill Ward", "Sleep Lab", "Quiet Recital", "Blindfold Theater", "Memory Triage",
            "Mnemonic Orchard", "Closed Loop Interview", "Gentle Siren", "REM Debrief", "Soft Lock Cell",
        ],
    },
    {
        "archetype": "thaumiel_grid",
        "task": "contain",
        "secondary": "suppress",
        "subtype": "Thaumiel",
        "keywords": {"Anchor", "Cross-Containment"},
        "motifs": [
            "Silver Lattice", "Paired Vault", "Clockwork Saint", "Friendly Leviathan", "Counter-God",
            "Mercy Engine", "Chain Reactor", "Halo Key", "Borrowed Lock", "Answer Box",
        ],
    },
    {
        "archetype": "blackfile_bureau",
        "task": "research",
        "secondary": "contain",
        "subtype": "Bureaucracy",
        "keywords": {"Blackfile", "Brief"},
        "motifs": [
            "Ink Labyrinth", "Unsigned Order", "File Room Zero", "Carbon Copy Ghost", "Stampede Desk",
            "Deadline Engine", "Archive Trap", "Misfile Saint", "Red String Office", "Paper Guillotine",
        ],
    },
    {
        "archetype": "clean_hands",
        "task": "research",
        "secondary": "contain",
        "subtype": "Ethics",
        "keywords": {"Overexpose", "Brief"},
        "motifs": [
            "Consent Bell", "Mercy Ledger", "Witness Clinic", "Aftercare Vault", "Human Cost",
            "Red Line Board", "Clean Knife", "Volunteer Court", "Debt Hospital", "Pardon Archive",
        ],
    },
    {
        "archetype": "veil_rotation",
        "task": "suppress",
        "secondary": "contain",
        "subtype": "Veil",
        "keywords": {"Rotation", "Quarantine"},
        "motifs": [
            "Night Desk", "Shift Siren", "False Dawn", "Gatehouse Loop", "Amnestic Pantry",
            "Standby Chapel", "Two-Key Elevator", "Low Alarm", "Quiet Motorcade", "Last Coffee",
        ],
    },
]


def _rarity(index: int, *, mandate: bool = False) -> str:
    if mandate and index == 0:
        return "mythic"
    if index in {0, 7}:
        return "rare"
    if index in {2, 5, 8}:
        return "uncommon"
    return "common"


def _anomaly_hook(archetype: str, index: int):
    if archetype == "mnestic_quarantine":
        return _quarantine("docile" if index % 2 == 0 else "cooperative", "no_eye_contact", briefing=1 if index % 3 == 0 else 0), _redaction_test, None
    if archetype == "thaumiel_grid":
        return None, None, _anchor_on_contain
    if archetype == "clean_hands":
        return None, _ethics_test, _archive_on_contain
    if archetype == "veil_rotation":
        return _quarantine("cooperative", "mirror_box", briefing=1 if index % 4 == 0 else 0), None, _archive_on_contain
    if archetype == "blackfile_bureau":
        return None, _redaction_test if index % 2 == 0 else None, None
    if archetype == "broken_masquerade":
        return _brief(1) if index % 3 == 0 else None, _redaction_test if index % 2 == 0 else None, None
    return None, None, None


def _procedure_effect(archetype: str, index: int) -> tuple[str, Callable]:
    if archetype == "broken_masquerade":
        options = [
            ("Blackfile 2. Add paperwork to a rival pending dossier; audit if none exist. Archive +1.", _blackfile_procedure(2, archive=True)),
            ("Overexpose. Archive +1, clearance +1, secrecy -2.", _overexpose_procedure),
            ("Counter-raid an opposing Site and Brief 1.", _goi_counterraid),
            ("Blackfile 3. Heavy paperwork sabotage or audit pressure. Archive +1.", _blackfile_procedure(3, archive=True)),
            ("Archive +1, Brief 1, breach +1.", _gain_archives_and_brief(1, 1, breach=1)),
        ]
    elif archetype == "mnestic_quarantine":
        options = [
            ("Quarantine the highest-hazard active anomaly with no-eye-contact and docile mood.", _quarantine_procedure("no_eye_contact", "docile")),
            ("Brief 2, secrecy +1.", _gain_archives_and_brief(0, 2, secrecy=1)),
            ("Archive +1, Brief 1, breach -1.", _gain_archives_and_brief(1, 1, breach=-1)),
            ("Quarantine an active anomaly with mirror-box and cooperative mood.", _quarantine_procedure("mirror_box", "cooperative")),
            ("Brief 1, secrecy +3, ethics debt +1.", _gain_archives_and_brief(0, 1, secrecy=3, ethics=1)),
        ]
    elif archetype == "thaumiel_grid":
        options = [
            ("Anchor. Bind your best contained anomaly to your highest-hazard active anomaly.", _anchor_procedure),
            ("Containment surge: breach -2, Brief 1.", _gain_archives_and_brief(0, 1, breach=-2)),
            ("Archive +1 if the grid stabilizes; breach +1.", _gain_archives_and_brief(1, 0, breach=1)),
            ("Apply ritual diagram to the highest-hazard active anomaly.", _quarantine_procedure("ritual_diagram", "cryptic")),
            ("Rotation 1. Refund a used assignment and refresh one exhausted staff.", _rotation_procedure),
        ]
    elif archetype == "blackfile_bureau":
        options = [
            ("Blackfile 2 and Brief 1 through a paper trail.", _blackfile_procedure(2)),
            ("Rotation 1. Refund a used assignment and refresh one exhausted staff.", _rotation_procedure),
            ("Archive +1, Brief 1, secrecy +1.", _gain_archives_and_brief(1, 1, secrecy=1)),
            ("Blackfile 1. Light paperwork sabotage or audit.", _blackfile_procedure(1)),
            ("Brief 2, clearance +1.", _gain_archives_and_brief(0, 2)),
        ]
    elif archetype == "clean_hands":
        options = [
            ("Discharge ethics pressure: spend ethics to erase breach or take debt to lower breach.", _ethics_discharge),
            ("Archive +1, ethics debt +1, secrecy +1.", _gain_archives_and_brief(1, 0, secrecy=1, ethics=1)),
            ("Brief 2, breach -2.", _gain_archives_and_brief(0, 2, breach=-2)),
            ("Overexpose testimony. Archive +1, clearance +1, secrecy -2.", _overexpose_procedure),
            ("Breach -3, ethics debt +1.", _gain_archives_and_brief(0, 0, breach=-3, ethics=1)),
        ]
    else:
        options = [
            ("Rotation 1. Refund a used assignment and refresh one exhausted staff.", _rotation_procedure),
            ("Quarantine an active anomaly with feed-it-lies and cooperative mood.", _quarantine_procedure("feed_it_lies", "cooperative")),
            ("Brief 1, secrecy +2.", _gain_archives_and_brief(0, 1, secrecy=2)),
            ("Archive +1, breach +2.", _gain_archives_and_brief(1, 0, breach=2)),
            ("Breach -3, secrecy -1.", _gain_archives_and_brief(0, 0, breach=-3, secrecy=-1)),
        ]
    return options[index % len(options)]


def _build_cards() -> list[CardDefinition]:
    cards: list[CardDefinition] = []
    for division in DIVISIONS:
        archetype = division["archetype"]
        task = division["task"]
        secondary = division["secondary"]
        subtype = division["subtype"]
        keywords = set(division["keywords"])
        motifs = division["motifs"]
        for index, motif in enumerate(motifs):
            reveal, on_test, on_contain = _anomaly_hook(archetype, index)
            if archetype == "broken_masquerade":
                hazard = 1 + (index % 3)
            else:
                hazard = 1 + ((index + (0 if archetype in {"mnestic_quarantine", "veil_rotation"} else 1)) % 4)
            containment = 2 + (index % 5) + (1 if task == "contain" else 0)
            curiosity = 2 + ((index + 2) % 5) + (1 if task == "research" else 0)
            red_tape = min(3, index % 3)
            clearance = 1 if index in {0, 6} else 0
            text = (
                f"{', '.join(sorted(keywords))}. "
                f"Contain {containment}, research {curiosity}, hazard {hazard}; supports {archetype.replace('_', ' ')}."
            )
            cards.append(_make_card(
                f"SZB {motif} Anomaly",
                CardType.SCP_ANOMALY,
                archetype=archetype,
                keywords=keywords,
                containment=containment,
                curiosity=curiosity,
                hazard=hazard,
                red_tape=red_tape,
                clearance=clearance,
                subtypes={subtype, "Site-Zero"},
                text=text,
                rarity=_rarity(index),
                on_reveal=reveal,
                on_test=on_test,
                on_contain=on_contain,
            ))
        for index, motif in enumerate(motifs[:8]):
            primary = 2 + (1 if index in {0, 4} else 0)
            skills = {task: primary, secondary: 1}
            if index in {2, 6}:
                skills["research" if task != "research" else "suppress"] = 1
            cards.append(_make_card(
                f"SZB {motif} Handler",
                CardType.SCP_PERSONNEL,
                archetype=archetype,
                keywords=keywords,
                skills=skills,
                red_tape=index % 2,
                clearance=1 if index == 0 else 0,
                subtypes={subtype, "Handler"},
                text=f"{', '.join(sorted(keywords))} support staff. Skills: {skills}.",
                rarity=_rarity(index),
            ))
        for index, motif in enumerate(motifs[:4]):
            bonus = {task: 1 + (1 if index == 0 else 0)}
            if index % 2 == 0:
                bonus[secondary] = 1
            cards.append(_make_card(
                f"SZB {motif} Wing",
                CardType.SCP_FACILITY,
                archetype=archetype,
                keywords=keywords,
                bonus=bonus,
                red_tape=1 + (index % 2),
                clearance=1 if index == 0 else 0,
                subtypes={subtype, "Site-Zero", "Facility"},
                text=f"Site Zero infrastructure. {task.capitalize()} checks get {bonus.get(task, 0)}; secondary bonuses: {bonus}.",
                rarity="rare" if index == 0 else "uncommon",
            ))
        for index, motif in enumerate(motifs[:5]):
            text, effect = _procedure_effect(archetype, index)
            cards.append(_make_card(
                f"SZB {motif} Protocol",
                CardType.SCP_PROCEDURE,
                archetype=archetype,
                keywords=keywords,
                red_tape=index % 2,
                clearance=1 if index in {1, 3} else 0,
                subtypes={subtype, "Protocol"},
                text=text,
                effect=effect,
                rarity=_rarity(index),
            ))
        for index, motif in enumerate(motifs[:3]):
            focus = task if index != 2 else secondary
            bonus = {focus: 1}
            alt_win = _mandate_alt_win(archetype) if index == 0 else None
            text = f"Site Zero directive for {archetype.replace('_', ' ')}. {focus.capitalize()} checks get +1."
            if alt_win == "public_panic":
                text += " Alternate win: four Archives while an opposing Site has secrecy 6 or less."
            elif alt_win == "thaumiel":
                text += " Alternate win: hold four contained anomalies at zero breach."
            elif alt_win == "redaction":
                text += " Alternate win: three Archives, secrecy 12+, and breach 3 or less."
            elif alt_win == "ethics_audit":
                text += " Alternate win: four Archives and secrecy 8+."
            elif alt_win == "veil_lockdown":
                text += " Alternate win: three Archives and zero breach."
            card = _make_card(
                f"SZB Directive {index + 1}: {motif}",
                CardType.SCP_MANDATE,
                archetype=archetype,
                keywords=keywords,
                bonus=bonus,
                red_tape=1 + (index % 2),
                clearance=1 if index == 0 else 0,
                subtypes={subtype, "Mandate", "Site-Zero"},
                text=text,
                rarity=_rarity(index, mandate=True),
            )
            card.scp_alt_win = alt_win
            if alt_win == "redaction":
                card.scp_redaction_win = {"archives": 3, "secrecy": 12, "max_breach": 3}
            cards.append(card)
    return cards


SITE_ZERO_BROKEN_MASQUERADE_CARDS = _build_cards()
SITE_ZERO_CARDS_BY_NAME = {card.name: card for card in SITE_ZERO_BROKEN_MASQUERADE_CARDS}


def _names(archetype: str, card_type: CardType | None = None, subtype: str | None = None) -> list[str]:
    names = []
    for name, card in SITE_ZERO_CARDS_BY_NAME.items():
        if getattr(card, "scp_archetype", None) != archetype:
            continue
        if card_type and card_type not in card.characteristics.types:
            continue
        if subtype and subtype not in set(card.characteristics.subtypes or set()):
            continue
        names.append(name)
    return sorted(names)


def _deck(archetype: str, *, anomaly_count: int, procedure_count: int) -> list[CardDefinition]:
    names: list[str] = []
    names.extend(_names(archetype, CardType.SCP_MANDATE)[:3])
    names.extend(_names(archetype, CardType.SCP_PERSONNEL)[:7])
    names.extend(_names(archetype, CardType.SCP_FACILITY)[:4])
    names.extend(_names(archetype, CardType.SCP_ANOMALY)[:anomaly_count])
    names.extend(_names(archetype, CardType.SCP_PROCEDURE)[:procedure_count])
    if len(names) < 25:
        raise ValueError(f"Site Zero deck {archetype} only has {len(names)} cards")
    return [SITE_ZERO_CARDS_BY_NAME[name] for name in names[:25]]


def make_site_zero_masquerade_deck() -> list[CardDefinition]:
    return _deck("broken_masquerade", anomaly_count=6, procedure_count=6)


def make_site_zero_quarantine_deck() -> list[CardDefinition]:
    return _deck("mnestic_quarantine", anomaly_count=7, procedure_count=5)


def make_site_zero_thaumiel_deck() -> list[CardDefinition]:
    return _deck("thaumiel_grid", anomaly_count=8, procedure_count=4)


def make_site_zero_blackfile_deck() -> list[CardDefinition]:
    return _deck("blackfile_bureau", anomaly_count=6, procedure_count=6)


def make_site_zero_clean_hands_deck() -> list[CardDefinition]:
    return _deck("clean_hands", anomaly_count=7, procedure_count=5)


def make_site_zero_veil_rotation_deck() -> list[CardDefinition]:
    return _deck("veil_rotation", anomaly_count=6, procedure_count=6)


SITE_ZERO_DECK_FACTORIES = {
    "site_zero_masquerade": make_site_zero_masquerade_deck,
    "site_zero_quarantine": make_site_zero_quarantine_deck,
    "site_zero_thaumiel": make_site_zero_thaumiel_deck,
    "site_zero_blackfile": make_site_zero_blackfile_deck,
    "site_zero_clean_hands": make_site_zero_clean_hands_deck,
    "site_zero_veil_rotation": make_site_zero_veil_rotation_deck,
}


SITE_ZERO_SYNERGY_PACKAGES: dict[str, list[str]] = {
    "SZB Press Conference Protocol": [
        "SZB Glass Newsroom Protocol", "SZB Civic Panic Handler", "SZB Camera Choir Anomaly",
        "SZB Broadcast Bunker Wing", "SZB Directive 1: Press Conference", "SZB Leaked Siren Anomaly",
        "SZB Witness Stampede Handler", "SZB Open Records Anomaly",
    ],
    "SZB Silver Lattice Protocol": [
        "SZB Paired Vault Anomaly", "SZB Clockwork Saint Anomaly", "SZB Silver Lattice Handler",
        "SZB Silver Lattice Wing", "SZB Directive 1: Silver Lattice", "SZB Friendly Leviathan Anomaly",
        "SZB Counter-God Handler", "SZB Answer Box Anomaly",
    ],
    "SZB White Pill Ward Protocol": [
        "SZB Sleep Lab Anomaly", "SZB White Pill Ward Handler", "SZB Quiet Recital Wing",
        "SZB Directive 1: White Pill Ward", "SZB Memory Triage Anomaly", "SZB REM Debrief Handler",
        "SZB Gentle Siren Protocol", "SZB Soft Lock Cell Anomaly",
    ],
    "SZB Night Desk Protocol": [
        "SZB Shift Siren Handler", "SZB False Dawn Wing", "SZB Gatehouse Loop Anomaly",
        "SZB Directive 1: Night Desk", "SZB Amnestic Pantry Protocol", "SZB Standby Chapel Handler",
        "SZB Low Alarm Anomaly", "SZB Last Coffee Anomaly",
    ],
}


__all__ = [
    "EXPANSION",
    "EXPANSION_CODE",
    "SITE_ZERO_BROKEN_MASQUERADE_CARDS",
    "SITE_ZERO_CARDS_BY_NAME",
    "SITE_ZERO_DECK_FACTORIES",
    "SITE_ZERO_SYNERGY_PACKAGES",
    "make_site_zero_masquerade_deck",
    "make_site_zero_quarantine_deck",
    "make_site_zero_thaumiel_deck",
    "make_site_zero_blackfile_deck",
    "make_site_zero_clean_hands_deck",
    "make_site_zero_veil_rotation_deck",
]
