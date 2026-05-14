"""SCP Containment TCG card pool.

Original, SCP-inspired containment cards for Hyperdraft. The mode borrows the
public-domain shape of anomalous containment fiction, but card names/text here
are original and do not reproduce SCP article prose.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType, Event, EventType, GameState, GameObject
from src.engine import scp


def _with_metadata(
    card: CardDefinition,
    *,
    expansion: str = "SCP Core",
    expansion_code: str = "CORE",
    archetype: str = "foundation",
    art_prompt: str | None = None,
) -> CardDefinition:
    card.scp_expansion = expansion
    card.scp_expansion_code = expansion_code
    card.scp_archetype = archetype
    card.scp_art_prompt = art_prompt or (
        f"Original SCP-inspired trading card art for {card.name}: cinematic classified-site containment, "
        f"clear focal subject, readable silhouette, no text, no logos, high-detail digital painting."
    )
    return card


def _anomaly(
    name,
    containment,
    curiosity,
    hazard,
    red_tape,
    subtypes,
    text,
    *,
    clearance=0,
    reveal=None,
    rarity=None,
    expansion="SCP Core",
    expansion_code="CORE",
    archetype="foundation",
    art_prompt=None,
    contained_bonus=None,
    aura=None,
    on_test_fail=None,
    seal_default=False,
):
    card = scp.make_scp_card(
        name,
        CardType.SCP_ANOMALY,
        containment=containment,
        curiosity=curiosity,
        hazard=hazard,
        red_tape=red_tape,
        clearance=clearance,
        subtypes=set(subtypes),
        text=text,
        rarity=rarity,
        on_reveal=reveal,
        contained_bonus=contained_bonus,
        aura=aura,
        on_test_fail=on_test_fail,
    )
    # ``scp_seal_default`` is a non-engine hint indicating an anomaly is
    # designed to be opened sealed (face-down) by default. AI / mechanic
    # modules read it; the engine itself ignores it.
    card.scp_seal_default = bool(seal_default)
    return _with_metadata(card, expansion=expansion, expansion_code=expansion_code, archetype=archetype, art_prompt=art_prompt)


def _personnel(
    name,
    skills,
    red_tape,
    subtypes,
    text,
    *,
    clearance=0,
    rarity=None,
    expansion="SCP Core",
    expansion_code="CORE",
    archetype="foundation",
    art_prompt=None,
    aura=None,
):
    card = scp.make_scp_card(
        name,
        CardType.SCP_PERSONNEL,
        skills=skills,
        red_tape=red_tape,
        clearance=clearance,
        subtypes=set(subtypes),
        text=text,
        rarity=rarity,
        aura=aura,
    )
    return _with_metadata(card, expansion=expansion, expansion_code=expansion_code, archetype=archetype, art_prompt=art_prompt)


def _facility(
    name,
    bonus,
    red_tape,
    subtypes,
    text,
    *,
    clearance=0,
    rarity=None,
    expansion="SCP Core",
    expansion_code="CORE",
    archetype="foundation",
    art_prompt=None,
):
    card = scp.make_scp_card(
        name,
        CardType.SCP_FACILITY,
        bonus=bonus,
        red_tape=red_tape,
        clearance=clearance,
        subtypes=set(subtypes),
        text=text,
        rarity=rarity,
    )
    return _with_metadata(card, expansion=expansion, expansion_code=expansion_code, archetype=archetype, art_prompt=art_prompt)


def _procedure(
    name,
    red_tape,
    subtypes,
    text,
    effect,
    *,
    clearance=0,
    rarity=None,
    expansion="SCP Core",
    expansion_code="CORE",
    archetype="foundation",
    art_prompt=None,
):
    card = scp.make_scp_card(
        name,
        CardType.SCP_PROCEDURE,
        red_tape=red_tape,
        clearance=clearance,
        subtypes=set(subtypes),
        text=text,
        rarity=rarity,
        effect=effect,
    )
    return _with_metadata(card, expansion=expansion, expansion_code=expansion_code, archetype=archetype, art_prompt=art_prompt)


def _mandate(
    name,
    red_tape,
    subtypes,
    text,
    *,
    clearance=0,
    bonus=None,
    alt_win=None,
    rarity=None,
    expansion="SCP Core",
    expansion_code="CORE",
    archetype="foundation",
    art_prompt=None,
):
    card = scp.make_scp_card(
        name,
        CardType.SCP_MANDATE,
        red_tape=red_tape,
        clearance=clearance,
        bonus=bonus or {},
        subtypes=set(subtypes),
        text=text,
        rarity=rarity,
    )
    card.scp_alt_win = alt_win
    return _with_metadata(card, expansion=expansion, expansion_code=expansion_code, archetype=archetype, art_prompt=art_prompt)


def _site_event(event_type, obj, **payload):
    payload.setdefault("player", obj.controller)
    return Event(type=event_type, payload=payload, source=obj.id, controller=obj.controller)


def _adjust_site(*, secrecy=0, breach=0, ethics=0, clearance=0):
    def effect(obj: GameObject, state: GameState, game=None):
        s = scp.site(state, obj.controller)
        s["secrecy"] += secrecy
        s["breach"] = max(0, s["breach"] + breach)
        s["ethics_debt"] = max(0, s["ethics_debt"] + ethics)
        s["clearance"] = max(0, s["clearance"] + clearance)
        return [_site_event(EventType.SCP_BREACH_TICK, obj, reason="procedure", breach=s["breach"], secrecy=s["secrecy"])]
    return effect


def _resolve_paperwork_bonfire(
    obj: GameObject, target_id: str, state: GameState, game=None,
) -> list[Event]:
    """Fast-track a single pending dossier (``target_id``) for secrecy -1."""
    candidate = state.objects.get(target_id)
    if candidate is None:
        return []
    s = scp.site(state, obj.controller)
    s["secrecy"] -= 1
    if game is not None:
        events = scp.activate_dossier_now(game, candidate, source=obj.id)
        return events or [_site_event(EventType.SCP_FAST_TRACK, obj, reason="paperwork_bonfire")]
    candidate.state.scp_paperwork = 0
    return [_site_event(EventType.SCP_FAST_TRACK, obj, reason="paperwork_bonfire")]


def _paperwork_bonfire(obj: GameObject, state: GameState, game=None):
    """Paperwork Bonfire: player chooses which of their own pending dossiers to fast-track.

    Migrated to PendingChoice — was first-pending in iteration order. AI
    preserves the same target via ``heuristic_pick``; humans pick.
    """
    pending = [
        candidate for candidate in state.objects.values()
        if candidate.controller == obj.controller and candidate.state.scp_status == "pending"
    ]
    if not pending:
        return []

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    # AI keeps the original first-in-iteration target.
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
        return _resolve_paperwork_bonfire(obj, target_id, st, game)

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=obj.controller,
        prompt="Fast-track which of your pending dossiers? (secrecy -1)",
        options=options,
        source_id=obj.id,
        min_choices=1,
        max_choices=1,
        handler=_resolve_handler,
        heuristic_pick=[best.id],
    )


def _resolve_lure(obj: GameObject, target_id: str, state: GameState) -> list[Event]:
    """Move ``target_id`` from active -> contained for the controller."""
    target = state.objects.get(target_id)
    if target is None:
        return []
    target.state.scp_status = "contained"
    anomaly_list = state.scp_anomalies.get(obj.controller, [])
    if target.id in anomaly_list:
        anomaly_list.remove(target.id)
    contained_list = state.scp_contained.setdefault(obj.controller, [])
    if target.id not in contained_list:
        contained_list.append(target.id)
    return [Event(
        type=EventType.SCP_CONTAINED,
        payload={"player": obj.controller, "anomaly_id": target.id, "reason": "procedure"},
        source=obj.id,
        controller=obj.controller,
    )]


def _lure_into_box(obj: GameObject, state: GameState, game=None):
    """Lure It Into a Box: player chooses which active anomaly to contain.

    Migrated to PendingChoice — was lowest-containment auto-pick. AI keeps
    the original target via ``heuristic_pick``; humans pick.
    """
    if game is None:
        return []
    active = [
        state.objects[aid]
        for aid in state.scp_anomalies.get(obj.controller, [])
        if aid in state.objects and state.objects[aid].state.scp_status == "active"
    ]
    if not active:
        return []

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    best = min(active, key=lambda a: int(getattr(a.card_def, "scp_containment", 0) or 0))
    options = [
        {
            "id": a.id,
            "label": getattr(a.card_def, "name", a.id) if a.card_def else a.id,
            "description": f"Containment {getattr(a.card_def, 'scp_containment', 0)} · Hazard {getattr(a.card_def, 'scp_hazard', 0)}",
        }
        for a in active
    ]

    def _resolve_handler(choice, selected, st):
        target_id = selected[0] if selected else best.id
        if isinstance(target_id, dict):
            target_id = target_id.get("id", best.id)
        return _resolve_lure(obj, target_id, st)

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=obj.controller,
        prompt="Contain which of your active anomalies?",
        options=options,
        source_id=obj.id,
        min_choices=1,
        max_choices=1,
        handler=_resolve_handler,
        heuristic_pick=[best.id],
    )


def _archive_sprint(obj: GameObject, state: GameState, game=None):
    s = scp.site(state, obj.controller)
    s["breach"] += 2
    if game is not None:
        return scp.gain_archives(game, obj.controller, 1, source=obj.id)
    s["archives"] += 1
    return [_site_event(EventType.SCP_ARCHIVE_GAINED, obj, amount=1, archives=s["archives"])]


def _archive_and_cover(obj: GameObject, state: GameState, game=None):
    s = scp.site(state, obj.controller)
    s["secrecy"] += 1
    s["breach"] = max(0, s["breach"] - 1)
    if game is not None:
        return scp.gain_archives(game, obj.controller, 1, source=obj.id)
    s["archives"] += 1
    return [_site_event(EventType.SCP_ARCHIVE_GAINED, obj, amount=1, archives=s["archives"])]


def _ethics_audit_record(obj: GameObject, state: GameState, game=None):
    s = scp.site(state, obj.controller)
    s["breach"] = max(0, s["breach"] - 2)
    s["ethics_debt"] = max(0, s["ethics_debt"] + 1)
    if game is not None:
        return scp.gain_archives(game, obj.controller, 1, source=obj.id)
    s["archives"] += 1
    return [_site_event(EventType.SCP_ARCHIVE_GAINED, obj, amount=1, archives=s["archives"])]


def _opponent(state: GameState, player_id: str):
    return next((pid for pid, player in state.players.items() if pid != player_id and not player.has_lost), None)


def _whistleblower_leak(obj: GameObject, state: GameState, game=None):
    opponent = _opponent(state, obj.controller)
    if game is None or not opponent:
        return []
    return scp.force_audit(game, obj.controller, opponent, intensity=2, source=obj.id)


def _resolve_misfile_audit(
    obj: GameObject, target_id: str, opponent: str, state: GameState, game,
) -> list[Event]:
    """Apply a 2-paperwork misfile to ``target_id`` (opponent pending)."""
    _ok, _message, events = scp.misfile_dossier(game, obj.controller, target_id, amount=2, source=obj.id)
    return events


def _misfile_audit(obj: GameObject, state: GameState, game=None):
    """Misfile Audit: player chooses which opponent pending dossier to misfile.

    Migrated to PendingChoice — was ``pending[0]`` deterministic pick. AI
    preserves the original target via ``heuristic_pick``.
    """
    opponent = _opponent(state, obj.controller)
    if game is None or not opponent:
        return []
    pending = [
        candidate
        for candidate in state.objects.values()
        if candidate.controller == opponent and candidate.state.scp_status == "pending"
    ]
    if not pending:
        return scp.force_audit(game, obj.controller, opponent, intensity=1, source=obj.id)

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
        return _resolve_misfile_audit(obj, target_id, opponent, st, game)

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=obj.controller,
        prompt="Misfile which opposing pending dossier? (+2 paperwork)",
        options=options,
        source_id=obj.id,
        min_choices=1,
        max_choices=1,
        handler=_resolve_handler,
        heuristic_pick=[best.id],
    )


def _weaponize_ethics(obj: GameObject, state: GameState, game=None):
    if game is None:
        return []
    ok, _message, events = scp.spend_ethics(game, obj.controller, 2, mode="buy_clearance", source=obj.id)
    if ok:
        return events
    scp.site(state, obj.controller)["ethics_debt"] += 2
    return [_site_event(EventType.SCP_ETHICS_SPENT, obj, amount=0, mode="debt_seeded")]


def _goi_tip_off(obj: GameObject, state: GameState, game=None):
    opponent = _opponent(state, obj.controller)
    if game is None or not opponent:
        return []
    return scp.goi_raid(game, opponent, faction="Serpent's Hand", source=obj.id)


def _crisis_reframe(obj: GameObject, state: GameState, game=None):
    """Catch-up sweeper: when you're behind on breach, hit both sites; otherwise small relief."""
    s = scp.site(state, obj.controller)
    opp_id = _opponent(state, obj.controller)
    own_breach = s["breach"]
    events = []
    if own_breach >= 6 and opp_id is not None:
        opp = scp.site(state, opp_id)
        opp_delta = min(2, opp["breach"])
        own_delta = min(2, own_breach)
        opp["breach"] -= opp_delta
        s["breach"] -= own_delta
        events.append(_site_event(
            EventType.SCP_BREACH_TICK, obj,
            amount=-own_delta, reason="crisis_reframe_self",
            breach=s["breach"],
        ))
        events.append(Event(
            type=EventType.SCP_BREACH_TICK,
            payload={"player": opp_id, "amount": -opp_delta, "reason": "crisis_reframe_opp", "breach": opp["breach"]},
            source=obj.id, controller=obj.controller,
        ))
    else:
        s["breach"] = max(0, own_breach - 1)
        events.append(_site_event(
            EventType.SCP_BREACH_TICK, obj,
            amount=-1, reason="crisis_reframe_small",
            breach=s["breach"],
        ))
    return events


def _compelling_testimony(obj: GameObject, state: GameState, game=None):
    """Catch-up archive: gain +1 archive when behind on board presence."""
    own_anomalies = len(state.scp_anomalies.get(obj.controller, []))
    own_contained = len(state.scp_contained.get(obj.controller, []))
    opp_id = _opponent(state, obj.controller)
    if opp_id is None:
        return []
    opp_anomalies = len(state.scp_anomalies.get(opp_id, []))
    opp_contained = len(state.scp_contained.get(opp_id, []))
    own_board = own_anomalies + own_contained
    opp_board = opp_anomalies + opp_contained
    if game is not None and own_board <= opp_board:
        return scp.gain_archives(game, obj.controller, 1, source=obj.id)
    # Otherwise small secrecy boost (deck still wants the slot)
    scp.site(state, obj.controller)["secrecy"] += 1
    return [_site_event(
        EventType.SCP_ARCHIVE_GAINED, obj,
        amount=0, reason="testimony_neutral",
        secrecy=scp.site(state, obj.controller)["secrecy"],
    )]


def _hostile_reveal(amount):
    def reveal(obj: GameObject, state: GameState):
        s = scp.site(state, obj.controller)
        s["breach"] += amount
        return [Event(type=EventType.SCP_BREACH_TICK, payload={"player": obj.controller, "amount": amount, "reason": "reveal"}, source=obj.id, controller=obj.controller)]
    return reveal


def _ethics_reveal(amount: int = 1):
    """Return an ``on_reveal`` hook that seeds ethics debt by ``amount``.

    Used for ETH archetype anomalies so revealing the dossier itself
    starts the ethics clock. Mirrors ``_hostile_reveal`` shape.
    """
    def reveal(obj: GameObject, state: GameState):
        s = scp.site(state, obj.controller)
        s["ethics_debt"] = max(0, s["ethics_debt"] + amount)
        return [Event(
            type=EventType.SCP_BREACH_TICK,
            payload={
                "player": obj.controller,
                "amount": 0,
                "reason": "ethics_reveal",
                "ethics_debt": s["ethics_debt"],
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return reveal


def _format_bonus_dict(bonus: dict) -> str:
    """Format a ``{task: amount}`` bonus dict as humans-readable card text.

    Single key: ``"research +1"``. Multi-key: ``"research +1, contain +1"``.
    Empty dict: ``"none"``. Keys are surfaced verbatim (lowercase task names).
    """
    if not bonus:
        return "none"
    parts = []
    for key, value in sorted(bonus.items()):
        try:
            value_int = int(value or 0)
        except (TypeError, ValueError):
            value_int = 0
        sign = "+" if value_int >= 0 else ""
        parts.append(f"{key} {sign}{value_int}")
    return ", ".join(parts)


PERSONNEL = [
    _personnel("Junior Researcher", {"research": 1}, 0, {"Scientist"}, "Cheap research body. Low nerve, no containment value."),
    _personnel("Containment Specialist", {"contain": 2, "suppress": 1}, 1, {"Security"}, "Reliable containment staff for mid-risk anomalies."),
    _personnel("MTF Doorbreaker", {"contain": 3, "suppress": 1}, 2, {"MTF", "Security"}, "Heavy response team. Excellent at forced containment."),
    _personnel("Memetics Analyst", {"research": 2, "suppress": 1}, 1, {"Scientist", "Memetics"}, "Researches hostile information without immediately collapsing."),
    _personnel("Ethics Liaison", {"research": 1, "suppress": 2}, 1, {"Ethics"}, "Keeps procedures from becoming the real anomaly."),
    _personnel("D-Class Volunteer", {"contain": 1, "research": 1, "suppress": 1}, 0, {"D-Class"}, "Flexible disposable labor with no paperwork."),
    _personnel("O5 Auditor", {"research": 3, "contain": 1}, 3, {"O5"}, "High-clearance archive engine.", clearance=2),
    _personnel("Field Agent", {"contain": 1, "research": 1, "suppress": 2}, 1, {"Agent"}, "Best at keeping the public story coherent."),
    _personnel("Thaumic Consultant", {"research": 2, "contain": 2}, 2, {"Occult"}, "Answers problems that should not have equations."),
    _personnel("Night Shift Archivist", {"research": 3}, 2, {"Archivist"}, "Turns messy incident notes into Archives."),
    _personnel("Sleep-Deprived Intern", {"research": 1, "suppress": 1}, 0, {"Scientist"}, "Somehow always available."),
    _personnel("Janitor Who Knows Too Much", {"contain": 1, "suppress": 3}, 1, {"Staff"}, "Oddly good at stopping alarms before anyone notices."),
]


FACILITIES = [
    _facility("Site-19 Intake Wing", {"contain": 1}, 1, {"Site"}, "Containment attempts get +1."),
    _facility("Memetics Lab", {"research": 1}, 1, {"Lab"}, "Research tests get +1."),
    _facility("Reality Anchor Array", {"suppress": 2}, 2, {"Array"}, "Suppression actions get +2."),
    _facility("Amnestic Pharmacy", {"suppress": 1}, 1, {"Medical"}, "Suppression actions get +1."),
    _facility("Deepwell Archive", {"research": 2}, 3, {"Archive"}, "Research tests get +2.", clearance=1),
    _facility("Scranton Lattice", {"contain": 1, "suppress": 1}, 2, {"Array"}, "Containment and suppression get +1."),
    _facility("Redaction Office", {"research": 1, "suppress": 1}, 1, {"Office"}, "Research and suppression get +1."),
    _facility("Ethics Committee Desk", {"suppress": 1}, 1, {"Ethics"}, "Suppression gets +1 and ethics decks get a stable anchor."),
    _facility("Observation Theatre", {"research": 1, "contain": 1}, 2, {"Lab"}, "Research and containment get +1."),
    _facility("Keter Annex", {"contain": 2}, 3, {"Site"}, "Containment gets +2.", clearance=1),
    _facility("Black Vault", {"research": 1}, 2, {"Archive"}, "Research gets +1. Its presence justifies higher-clearance cards."),
    _facility("Cafeteria at 3 AM", {"suppress": 1, "contain": 1}, 0, {"Staff"}, "A low-paperwork morale engine."),
]


ANOMALIES = [
    _anomaly("The Concrete Saint", 4, 2, 2, 2, {"Statue"}, "Easy to study, dangerous to ignore."),
    _anomaly("Recursive Hallway", 3, 3, 1, 1, {"Space"}, "Loops paperwork as well as people."),
    _anomaly("Singing Vending Machine", 2, 4, 1, 1, {"Object"}, "High research payoff, low containment difficulty."),
    _anomaly("Door That Opens Sideways", 3, 2, 2, 1, {"Door", "Space"}, "Containment is mostly deciding where the room is."),
    _anomaly("Oracle Mold", 5, 3, 3, 2, {"Biological"}, "Predicts which staff member will make the mistake."),
    _anomaly("Rain Inside the Elevator", 2, 2, 1, 0, {"Weather"}, "A gentle anomaly unless ignored."),
    _anomaly("Hostile Nursery Rhyme", 3, 5, 2, 2, {"Memetic"}, "Excellent archives, bad dreams."),
    _anomaly("Borrowed Moon", 6, 4, 3, 3, {"Celestial"}, "A large containment ask with a rich research profile.", clearance=1),
    _anomaly("Basement Ocean", 5, 4, 2, 2, {"Space", "Aquatic"}, "The tide table is classified."),
    _anomaly("Polite Apocalypse", 7, 5, 4, 4, {"Keter"}, "On reveal, breach +2.", clearance=2, reveal=_hostile_reveal(2)),
    _anomaly("Paperclip Colony", 2, 3, 1, 0, {"Swarm", "Object"}, "Cheap to contain but multiplies in reports."),
    _anomaly("Red Room Static", 4, 4, 2, 2, {"Signal", "Memetic"}, "Every recording edits itself."),
    _anomaly("Patient Zero of Yesterday", 4, 5, 3, 3, {"Temporal", "Biological"}, "Research asks why the outbreak already happened."),
    _anomaly("Clockwork Saint", 6, 3, 2, 2, {"Machine"}, "Hard shell, clean containment reward."),
    _anomaly("The Mirror That Interviews You", 3, 4, 2, 1, {"Cognitive"}, "It knows which questions to ask."),
    _anomaly("Antimemetic Orchard", 5, 5, 2, 3, {"Antimemetic"}, "Hard to remember, very worth archiving."),
    _anomaly("Containment Door Zero", 3, 3, 3, 1, {"Door"}, "Nobody agrees which side is inside."),
    _anomaly("The Helpful Knife", 2, 3, 2, 0, {"Object"}, "Always volunteers. That is the problem."),
    _anomaly("Unlicensed Heaven", 7, 5, 4, 4, {"Divine"}, "High-risk alternate cosmology.", clearance=2),
    _anomaly("Moth in the Camera", 1, 2, 1, 0, {"Tiny", "Signal"}, "Starter anomaly for research-focused decks."),
]


PROCEDURES = [
    _procedure("Class-A Amnestic Broadcast", 1, {"Amnestic"}, "Secrecy +3, ethics debt +1.", _adjust_site(secrecy=3, ethics=1)),
    _procedure("Emergency Lockdown", 1, {"Security"}, "Breach -3.", _adjust_site(breach=-3)),
    _procedure("Black Budget Requisition", 1, {"Funding"}, "Clearance +1, ethics debt +1.", _adjust_site(clearance=1, ethics=1)),
    _procedure("Cross-Test Proposal", 2, {"Research"}, "Archive +1, breach +2.", _archive_sprint, clearance=1),
    _procedure("Controlled Breach Drill", 0, {"Training"}, "Breach +1, clearance +1.", _adjust_site(breach=1, clearance=1)),
    _procedure("False Flag Cover Story", 1, {"Cover"}, "Secrecy +2, breach -1.", _adjust_site(secrecy=2, breach=-1)),
    _procedure("Ethics Waiver", 0, {"Ethics"}, "Clearance +2, ethics debt +2.", _adjust_site(clearance=2, ethics=2)),
    _procedure("Mnestic Wake-Up", 1, {"Memetics"}, "Secrecy -1, clearance +1.", _adjust_site(secrecy=-1, clearance=1)),
    _procedure("Paperwork Bonfire", 0, {"Bureaucracy"}, "Fast-track one pending dossier, secrecy -1.", _paperwork_bonfire),
    _procedure("O5 Midnight Directive", 3, {"O5"}, "Clearance +2, secrecy -2.", _adjust_site(clearance=2, secrecy=-2), clearance=2),
    _procedure("Witness Relocation", 1, {"Cover"}, "Secrecy +2.", _adjust_site(secrecy=2)),
    _procedure("Null Room Calibration", 1, {"Array"}, "Breach -2.", _adjust_site(breach=-2)),
    _procedure("Archive Sprint", 1, {"Research"}, "Archive +1, breach +2.", _archive_sprint),
    _procedure("Incident Report Rewrite", 0, {"Bureaucracy"}, "Secrecy +1.", _adjust_site(secrecy=1)),
    _procedure("Lure It Into a Box", 2, {"Containment"}, "Contain your lowest-containment active anomaly.", _lure_into_box),
    _procedure("Red-Team the Veil", 1, {"Training"}, "Secrecy -1, breach -2.", _adjust_site(secrecy=-1, breach=-2)),
    _procedure("Last Door Protocol", 2, {"Security"}, "Breach -4, secrecy -2.", _adjust_site(breach=-4, secrecy=-2), clearance=1),
    _procedure("Friendly Fire Evacuation", 1, {"Security"}, "Breach -1, ethics debt +1.", _adjust_site(breach=-1, ethics=1)),
    _procedure("Whistleblower Leak", 1, {"Audit"}, "Audit the opposing Site for exposure pressure.", _whistleblower_leak),
    _procedure("Bureaucratic Labyrinth", 1, {"Bureaucracy"}, "Add paperwork to an opposing pending dossier; audit if none exist.", _misfile_audit),
    _procedure("Weaponize Ethics Debt", 0, {"Ethics"}, "Spend 2 ethics debt for clearance, or seed 2 debt if you have none.", _weaponize_ethics),
    _procedure("GOI Raid Tip-Off", 1, {"GOI", "Raid"}, "Trigger a GOI raid against the opposing Site.", _goi_tip_off),
    _procedure("Crisis Reframe", 0, {"Security", "Comeback"}, "If your breach is 6+, both Sites' breach -2; otherwise your breach -1.", _crisis_reframe),
    _procedure("Compelling Testimony", 1, {"Audit", "Comeback"}, "If you have no more active+contained anomalies than opponent, gain +1 archive; otherwise secrecy +1.", _compelling_testimony),
]


MANDATES = [
    _mandate("Secure Mandate", 1, {"Mandate"}, "Containment-focused Site directive. Alternate win: hold three contained anomalies at zero breach.", bonus={"contain": 1}, alt_win="thaumiel"),
    _mandate("Contain Mandate", 1, {"Mandate"}, "Research-focused Site directive.", bonus={"research": 1}),
    _mandate(
        "Protect Mandate",
        1,
        {"Mandate"},
        "Suppression-focused Site directive. Fully suppressed anomalies become contained Archives. Alternate win: three Archives and zero breach.",
        bonus={"suppress": 1},
        alt_win="veil_lockdown",
    ),
    _mandate("There Is No Antimemetics Division", 2, {"Mandate", "Antimemetic"}, "Alternate win: reach three Archives and secrecy 12+.", clearance=2, bonus={"research": 2}, alt_win="redaction"),
]


SCP_EXPANSIONS = [
    {
        "name": "Antimemetic Cold War",
        "code": "ACW",
        "archetype": "redaction",
        "task": "research",
        "secondary": "suppress",
        "alt_win": "redaction",
        "subtype": "Antimemetic",
        "motifs": [
            "Blind Library", "Forgotten Embassy", "Null Choir", "Paperless Witness", "Vanishing Orchard", "Mnemonic Siege",
            "Unwritten Treaty", "Static Pilgrim", "Backmask City", "Cipher Hospital", "Redacted Noon", "Ghost Ledger",
            "Negative Portrait", "White Noise Saint", "Absent Jury", "Hollow Survey", "Memory Quarantine", "Dead Language",
        ],
        "heroes": [
            "Director Ana Vale", "Dr. Kovacs of the Blank Wing", "Agent No-Name", "Archivist Lumen Rye",
            "Professor Hester Quill", "O5-Null", "Mara Voss, Mnestic Surgeon", "Captain Erasure Bell",
        ],
    },
    {
        "name": "Keter Blackout",
        "code": "KBO",
        "archetype": "blackout",
        "task": "contain",
        "secondary": "suppress",
        "alt_win": "thaumiel",
        "subtype": "Keter",
        "motifs": [
            "Sunless Reactor", "Ashen Giant", "Mercy Guillotine", "Broken Halo", "Red Siren", "Iron Nursery",
            "Twelve-Minute God", "Containment Furnace", "Wild Crown", "Nightquake Engine", "Coffin Star", "Burning Elevator",
            "Last Shepherd", "Cathedral Breach", "Blackout Leviathan", "Crisis Glass", "Dead Switch", "Stormward Gate",
        ],
        "heroes": [
            "Commander Slate Rook", "Dr. Mira Lock", "O5-Blackout", "Captain Ferro Kane",
            "Warden Vela Cross", "Chief Sato Lastdoor", "Ada Pike, Breach Marshal", "Rook Team Helix",
        ],
    },
    {
        "name": "GOI Frontline",
        "code": "GOI",
        "archetype": "raid",
        "task": "suppress",
        "secondary": "research",
        "alt_win": "public_panic",
        "subtype": "GOI",
        "motifs": [
            "Serpent Consulate", "Broken Auction", "Black Market Reliquary", "Glass Insurgency", "Parahuman Picket",
            "Smuggled Eden", "Counterfeit Oracle", "Public Leak Cell", "Warehouse Gospel", "Static Broadcast",
            "Crowded Safehouse", "Anomalous Embassy", "Hostile Benefactor", "Litigation Cult", "Witness Riot",
            "Borderless Site", "Raid Calendar", "Quiet Defector",
        ],
        "heroes": [
            "Agent Felicity Graves", "Marshal Rane Cross", "Serpent Speaker Ilya", "The Defector in Blue",
            "Quartermaster Hex", "Dr. Sel Orison", "O5-Interdiction", "Captain Crowbar Venn",
        ],
    },
    {
        "name": "Ethics Reckoning",
        "code": "ETH",
        "archetype": "ethics",
        "task": "research",
        "secondary": "contain",
        "alt_win": "ethics_audit",
        "subtype": "Ethics",
        "motifs": [
            "Mercy Ledger", "Confession Engine", "Borrowed Body", "Clean-Room Tribunal", "Kind Knife", "Witness Garden",
            "Aftercare Ward", "Debt Chapel", "Humane Blacksite", "Consent Simulator", "Red Line Codex", "Volunteer Bell",
            "Burden Archive", "Patient Sun", "Audit Cathedral", "Moral Injury", "White Budget", "Merciful Lock",
        ],
        "heroes": [
            "Chairwoman Inez Salt", "Dr. Gideon Vale", "O5-Conscience", "Nurse Patel of Ward Zero",
            "Mediator June Frost", "D-0001, Volunteer King", "Auditor Sol Mercer", "Sister Redline",
        ],
    },
    {
        "name": "Oneiric Archives",
        "code": "OAR",
        "archetype": "oneiric",
        "task": "research",
        "secondary": "suppress",
        "alt_win": "veil_lockdown",
        "subtype": "Dream",
        "motifs": [
            "Sleeping Observatory", "Lucid Whale", "Moonlit Ward", "Somnambulist Court", "Dream Cartographer",
            "Nightmare Orchard", "Velvet Alarm", "Glass Pillow", "Hypnagogic Door", "Waking Labyrinth",
            "REM Cathedral", "Drowsing Archive", "Murmur Lake", "Imaginary Elevator", "Somatic Star",
            "Nap Protocol", "Dream-Static Choir", "Unremembered Morning",
        ],
        "heroes": [
            "Dr. Somna Reed", "Agent Lucid Marr", "O5-Dreaming", "The Sleepless Child",
            "Archivist Yarrow Night", "Captain Nora REM", "Professor Glass Pillow", "Warden Hypnos Vale",
        ],
    },
]


def _expansion_art_prompt(expansion: dict, kind: str, name: str, motif: str) -> str:
    return (
        f"Original SCP-inspired TCG illustration for {name}, {kind} from {expansion['name']}. "
        f"Subject: {motif.lower()} inside a classified containment facility. "
        f"High-contrast cinematic lighting, practical horror, readable foreground silhouette, no text, no watermark."
    )


def _procedure_profile(archetype: str, index: int):
    if archetype == "redaction":
        profiles = [
            ("Archive +1, secrecy +1, breach -1.", _archive_and_cover, {"Research", "Cover"}),
            ("Secrecy +2, breach -1.", _adjust_site(secrecy=2, breach=-1), {"Cover"}),
            ("Clearance +1.", _adjust_site(clearance=1), {"Mnestic"}),
            ("Audit the opposing Site for exposure pressure.", _whistleblower_leak, {"Audit"}),
        ]
    elif archetype == "blackout":
        profiles = [
            ("Breach -4, secrecy -2.", _adjust_site(breach=-4, secrecy=-2), {"Security"}),
            ("Fast-track one pending dossier, secrecy -1.", _paperwork_bonfire, {"Bureaucracy"}),
            ("Contain your lowest-containment active anomaly.", _lure_into_box, {"Containment"}),
            ("Breach +1, clearance +1.", _adjust_site(breach=1, clearance=1), {"Training"}),
        ]
    elif archetype == "raid":
        profiles = [
            ("Trigger a GOI raid against the opposing Site.", _goi_tip_off, {"GOI", "Raid"}),
            ("Add paperwork to an opposing pending dossier; audit if none exist.", _misfile_audit, {"Bureaucracy"}),
            ("Audit the opposing Site for exposure pressure.", _whistleblower_leak, {"Audit"}),
            ("Secrecy +1, breach -1.", _adjust_site(secrecy=1, breach=-1), {"Cover"}),
        ]
    elif archetype == "ethics":
        profiles = [
            ("Breach -3, ethics debt +1.", _adjust_site(breach=-3, ethics=1), {"Ethics"}),
            ("Spend 2 ethics debt for clearance, or seed 2 debt if you have none.", _weaponize_ethics, {"Ethics"}),
            ("Secrecy +3, ethics debt +1.", _adjust_site(secrecy=3, ethics=1), {"Amnestic"}),
            ("Archive +1, breach -2, ethics debt +1.", _ethics_audit_record, {"Research", "Ethics"}),
        ]
    elif archetype == "oneiric":
        profiles = [
            ("Secrecy +3, breach -1.", _adjust_site(secrecy=3, breach=-1), {"Dream", "Cover"}),
            ("Archive +1, secrecy +1, breach -1.", _archive_and_cover, {"Dream", "Research"}),
            ("Breach -3.", _adjust_site(breach=-3), {"Dream", "Array"}),
            ("Secrecy +2.", _adjust_site(secrecy=2), {"Dream", "Cover"}),
        ]
    else:
        profiles = [
            ("Secrecy -1, breach -2.", _adjust_site(secrecy=-1, breach=-2), {"Training"}),
            ("Secrecy +2.", _adjust_site(secrecy=2), {"Cover"}),
            ("Breach -2.", _adjust_site(breach=-2), {"Array"}),
            ("Archive +1, breach +2.", _archive_sprint, {"Research"}),
        ]
    return profiles[index % len(profiles)]


def _rarity(index: int, *, hero: bool = False) -> str:
    if hero:
        return "mythic"
    if index % 17 == 0:
        return "mythic"
    if index % 7 == 0:
        return "rare"
    if index % 3 == 0:
        return "uncommon"
    return "common"


def _anomaly_defaults(archetype: str, index: int):
    """Return ``(reveal_hook, seal_default, reveal_label)`` for a templated anomaly.

    Per-archetype defaults baked here so every templated anomaly carries a
    flavorful on-reveal hook instead of arriving inert. ``reveal_label`` is a
    short, human-readable phrase appended to card text so the printed effect
    matches the wired hook.

    Behaviour by archetype (all anomalies, not just the sparse ``index % 9``
    gate the previous generator used):
      - ``redaction``  → ``_seeded_mood("cryptic", protocol="mirror_box")`` +
                          ``seal_default=True`` (ACW thrives sealed).
      - ``blackout``   → ``_hostile_reveal(1)`` every 2nd anomaly,
                          ``_seeded_mood("agitated")`` for the rest.
      - ``raid``       → ``_public_reveal(1)`` every 2nd anomaly,
                          ``_hostile_reveal(1)`` for the rest.
      - ``ethics``     → ``_ethics_reveal(1)`` for every anomaly.
      - ``oneiric``    → ``_seeded_mood("cooperative",
                          protocol="no_eye_contact")`` for every anomaly.
    """
    if archetype == "redaction":
        return (
            scp._seeded_mood("cryptic", protocol="mirror_box"),
            True,
            "On reveal: mood becomes cryptic, mirror_box protocol applied; opens sealed by default.",
        )
    if archetype == "blackout":
        if index % 4 == 0:
            return (
                _hostile_reveal(1),
                False,
                "On reveal: breach +1.",
            )
        return (
            scp._seeded_mood("agitated"),
            False,
            "On reveal: mood becomes agitated (+hazard, +containment).",
        )
    if archetype == "raid":
        if index % 3 == 0:
            return (
                _hostile_reveal(1),
                False,
                "On reveal: breach +1.",
            )
        return (
            scp._public_reveal(1),
            False,
            "On reveal: secrecy -1 from public leak.",
        )
    if archetype == "ethics":
        if index % 3 == 0:
            return (
                _ethics_reveal(1),
                False,
                "On reveal: ethics debt +1.",
            )
        return (
            scp._seeded_mood("docile"),
            False,
            "On reveal: mood becomes docile (-hazard, -containment, -curiosity).",
        )
    if archetype == "oneiric":
        return (
            scp._seeded_mood("cooperative", protocol="no_eye_contact"),
            False,
            "On reveal: mood becomes cooperative, no_eye_contact protocol applied.",
        )
    # Fallback preserves the original sparse-gate behaviour.
    if index % 9 == 0:
        return (
            _hostile_reveal(1),
            False,
            "On reveal: breach +1.",
        )
    return (None, False, None)


def _build_expansion_cards() -> list[CardDefinition]:
    cards: list[CardDefinition] = []
    for expansion in SCP_EXPANSIONS:
        code = expansion["code"]
        task = expansion["task"]
        secondary = expansion["secondary"]
        archetype = expansion["archetype"]
        subtype = expansion["subtype"]
        for index, motif in enumerate(expansion["motifs"]):
            rarity = _rarity(index)
            clearance = 1 if index % 6 == 0 else 0
            reveal, seal_default, reveal_label = _anomaly_defaults(archetype, index)
            hazard = 1 + ((index + 1) % 4)
            if archetype in {"redaction", "raid", "oneiric"}:
                hazard = 1 + (index % 3)
            anomaly_text = (
                f"{motif} rewards {task} plans but punishes Sites that ignore its {secondary} pressure."
            )
            if reveal_label:
                anomaly_text = f"{anomaly_text} {reveal_label}"
            cards.append(_anomaly(
                f"{code} {motif} Anomaly",
                2 + (index % 5) + (1 if task == "contain" else 0),
                2 + ((index + 2) % 5) + (1 if task == "research" else 0),
                hazard,
                min(2, index % 3),
                {subtype, "Anomaly"},
                anomaly_text,
                clearance=clearance,
                reveal=reveal,
                rarity=rarity,
                expansion=expansion["name"],
                expansion_code=code,
                archetype=archetype,
                art_prompt=_expansion_art_prompt(expansion, "anomaly", f"{code} {motif} Anomaly", motif),
                seal_default=seal_default,
            ))
            skill_total = 2 + (1 if index % 4 == 0 else 0)
            # Specialists get a SECONDARY-task aura keyed on their archetype's
            # signature subtype. Heroes keep the primary-task aura (set below)
            # so specialist and hero auras stack rather than collide.
            specialist_aura = {f"subtype:{subtype}": {secondary: 1}}
            cards.append(_personnel(
                f"{code} {motif} Specialist",
                {task: skill_total, secondary: 1},
                index % 2,
                {subtype, "Specialist"},
                (
                    f"Build-around support for {archetype} decks: {task} {skill_total}, {secondary} 1. "
                    f"Aura: friendly {subtype} personnel get {secondary} +1."
                ),
                clearance=clearance if index % 8 == 0 else 0,
                rarity=rarity,
                expansion=expansion["name"],
                expansion_code=code,
                archetype=archetype,
                art_prompt=_expansion_art_prompt(expansion, "personnel", f"{code} {motif} Specialist", motif),
                aura=specialist_aura,
            ))
            facility_bonus = {task: 1 + (1 if index % 6 == 0 else 0)}
            if index % 4 == 0:
                facility_bonus[secondary] = 1
            cards.append(_facility(
                f"{code} {motif} Wing",
                facility_bonus,
                index % 2,
                {subtype, "Facility"},
                f"{motif} anchors {archetype} decks. Site bonuses: {_format_bonus_dict(facility_bonus)}.",
                clearance=clearance,
                rarity=rarity,
                expansion=expansion["name"],
                expansion_code=code,
                archetype=archetype,
                art_prompt=_expansion_art_prompt(expansion, "facility", f"{code} {motif} Wing", motif),
            ))
            text, effect, proc_subtypes = _procedure_profile(archetype, index)
            cards.append(_procedure(
                f"{code} {motif} Protocol",
                index % 2,
                {subtype, *proc_subtypes},
                text,
                effect,
                clearance=clearance if index % 5 == 0 else 0,
                rarity=rarity,
                expansion=expansion["name"],
                expansion_code=code,
                archetype=archetype,
                art_prompt=_expansion_art_prompt(expansion, "procedure", f"{code} {motif} Protocol", motif),
            ))
        for index in range(6):
            focus = task if index % 2 == 0 else secondary
            alt = expansion["alt_win"] if index == 0 else None
            text = f"{expansion['name']} directive for {archetype} decks. {focus.capitalize()} checks get +1."
            if alt == "redaction":
                text += " Alternate win: reach three Archives and secrecy 12+, or three Archives while secrecy is high and breach is controlled."
            elif alt == "thaumiel":
                text += " Alternate win: hold four contained anomalies at zero breach."
            elif alt == "veil_lockdown":
                text += " Alternate win: three Archives and zero breach."
            elif alt == "ethics_audit":
                text += " Alternate win: four Archives and secrecy 8+."
            elif alt == "public_panic":
                text += " Alternate win: four Archives while an opposing Site has secrecy 6 or less."
            cards.append(_mandate(
                f"{code} Mandate {index + 1}: {expansion['motifs'][index]}",
                1 + (index % 2),
                {subtype, "Mandate"},
                text,
                bonus={focus: 1},
                alt_win=alt,
                rarity="rare" if index else "mythic",
                expansion=expansion["name"],
                expansion_code=code,
                archetype=archetype,
                art_prompt=_expansion_art_prompt(expansion, "mandate", f"{code} Mandate {index + 1}", expansion["motifs"][index]),
            ))
        # Heroes carry a primary-task aura matching their archetype subtype.
        # W4 may override these with the same payload — assignment is
        # idempotent so this is a safe future-proof default.
        hero_aura = {f"subtype:{subtype}": {task: 1}}
        for index, hero in enumerate(expansion["heroes"]):
            primary = 3 + (1 if index % 4 == 0 else 0)
            skills = {task: primary, secondary: 2}
            if index % 3 == 0:
                skills["research" if task != "research" else "contain"] = 1
            cards.append(_personnel(
                f"{code} Hero - {hero}",
                skills,
                1 + (index % 2),
                {subtype, "Hero", "Legend"},
                (
                    f"Rare hero combo piece for {archetype}: compressed skills "
                    f"({_format_bonus_dict(skills)}) on one high-clearance body. "
                    f"Aura: friendly {subtype} personnel get {task} +1."
                ),
                clearance=1 + (1 if index % 4 == 0 else 0),
                rarity=_rarity(index, hero=True),
                expansion=expansion["name"],
                expansion_code=code,
                archetype=archetype,
                art_prompt=_expansion_art_prompt(expansion, "hero card", f"{code} Hero - {hero}", hero),
                aura=hero_aura,
            ))
    return cards


EXPANSION_CARDS = _build_expansion_cards()

from .site_zero_broken_masquerade import (  # noqa: E402
    SITE_ZERO_BROKEN_MASQUERADE_CARDS,
    SITE_ZERO_DECK_FACTORIES,
    SITE_ZERO_SYNERGY_PACKAGES,
    make_site_zero_blackfile_deck,
    make_site_zero_clean_hands_deck,
    make_site_zero_masquerade_deck,
    make_site_zero_quarantine_deck,
    make_site_zero_thaumiel_deck,
    make_site_zero_veil_rotation_deck,
)

# Mnestic Reset (MNR) — the antimemetic-themed expansion. Currently only the
# scaffold + 6 smoke-test cards; card-design agents extend MNR_CARDS via the
# sub-module lists in src/cards/scp/mnestic_reset/.
from .mnestic_reset import MNR_CARDS  # noqa: E402


SCP_CARDS: dict[str, CardDefinition] = {
    card.name: card
    for card in [
        *PERSONNEL,
        *FACILITIES,
        *ANOMALIES,
        *PROCEDURES,
        *MANDATES,
        *EXPANSION_CARDS,
        *SITE_ZERO_BROKEN_MASQUERADE_CARDS,
        *MNR_CARDS.values(),
    ]
}

# Post-construction mechanic appliers mutate SCP_CARDS in place to wire up
# attributes like scp_on_reveal / scp_contained_bonus / scp_aura. Each module
# under src/cards/scp/mechanics/ owns one attribute family — see the package
# docstring for the per-worktree split.
from .mechanics import apply_all_mechanics  # noqa: E402
apply_all_mechanics(SCP_CARDS)


SECURE_CONTAIN_RESEARCH_NAMES = [
    "Junior Researcher", "Junior Researcher", "Containment Specialist", "D-Class Volunteer",
    "Field Agent", "Ethics Liaison", "Sleep-Deprived Intern", "D-Class Volunteer",
    "Site-19 Intake Wing", "Memetics Lab", "Observation Theatre", "Redaction Office",
    "Moth in the Camera", "Red Room Static", "Patient Zero of Yesterday", "Recursive Hallway",
    "The Mirror That Interviews You", "Hostile Nursery Rhyme", "Oracle Mold",
    "Class-A Amnestic Broadcast", "Emergency Lockdown", "False Flag Cover Story",
    "Friendly Fire Evacuation", "Incident Report Rewrite", "Secure Mandate",
]


KETER_RISK_NAMES = [
    # Nerfed: 2x MTF Doorbreaker -> 1x, freed slot for Ethics Liaison (less Security density)
    "MTF Doorbreaker", "Ethics Liaison", "Containment Specialist", "Field Agent",
    "Thaumic Consultant", "Janitor Who Knows Too Much", "O5 Auditor", "D-Class Volunteer",
    "Reality Anchor Array", "Keter Annex", "Scranton Lattice", "Black Vault",
    "The Concrete Saint", "Oracle Mold", "Borrowed Moon", "Clockwork Saint",
    "Containment Door Zero", "Paperclip Colony", "Basement Ocean",
    "Black Budget Requisition", "Archive Sprint", "Last Door Protocol",
    "Lure It Into a Box", "Paperwork Bonfire", "Contain Mandate",
]


VEIL_CONTROL_NAMES = [
    # Nerfed: 2x Field Agent -> 1x, freed slot for second Junior Researcher (less Agent density)
    "Field Agent", "Junior Researcher", "Ethics Liaison", "Memetics Analyst",
    "Janitor Who Knows Too Much", "Sleep-Deprived Intern", "Junior Researcher", "D-Class Volunteer",
    "Redaction Office", "Amnestic Pharmacy", "Reality Anchor Array", "Cafeteria at 3 AM",
    "Red Room Static", "Door That Opens Sideways", "Patient Zero of Yesterday",
    "Hostile Nursery Rhyme", "Antimemetic Orchard", "The Helpful Knife",
    "Class-A Amnestic Broadcast", "Witness Relocation", "Null Room Calibration",
    "Red-Team the Veil", "GOI Raid Tip-Off", "Incident Report Rewrite", "Protect Mandate",
]


SITE_ZERO_REDACTION_LOCK_NAMES = [
    "There Is No Antimemetics Division", "There Is No Antimemetics Division",
    "SZB Directive 1: White Pill Ward", "SZB Directive 1: White Pill Ward",
    "D-Class Volunteer", "D-Class Volunteer",
    "Sleep-Deprived Intern", "Sleep-Deprived Intern",
    "Memetics Analyst", "Memetics Analyst",
    "SZB White Pill Ward Handler", "SZB White Pill Ward Handler",
    "SZB Memory Triage Handler", "SZB Memory Triage Handler",
    "Memetics Lab", "Memetics Lab",
    "Redaction Office", "Redaction Office",
    "Moth in the Camera", "Moth in the Camera",
    "SZB White Pill Ward Anomaly", "SZB White Pill Ward Anomaly",
    "SZB Quiet Recital Protocol", "SZB Quiet Recital Protocol",
    "Emergency Lockdown",
]


def _names_by(
    *,
    expansion_code: str | None = None,
    archetype: str | None = None,
    card_type: CardType | None = None,
    subtype: str | None = None,
    exclude_subtype: str | None = None,
) -> list[str]:
    names: list[str] = []
    for name, card in SCP_CARDS.items():
        if expansion_code and getattr(card, "scp_expansion_code", None) != expansion_code:
            continue
        if archetype and getattr(card, "scp_archetype", None) != archetype:
            continue
        if card_type and card_type not in card.characteristics.types:
            continue
        subtypes = set(card.characteristics.subtypes or set())
        if subtype and subtype not in subtypes:
            continue
        if exclude_subtype and exclude_subtype in subtypes:
            continue
        names.append(name)
    return sorted(names)


def _expanded_deck(expansion_code: str, archetype: str) -> list[CardDefinition]:
    names: list[str] = []
    if archetype == "raid":
        counts = {"mandates": 2, "heroes": 2, "personnel": 6, "facilities": 4, "anomalies": 4, "procedures": 7}
    elif archetype == "redaction":
        counts = {"mandates": 2, "heroes": 2, "personnel": 7, "facilities": 6, "anomalies": 4, "procedures": 4}
    else:
        counts = {"mandates": 2, "heroes": 2, "personnel": 6, "facilities": 5, "anomalies": 7, "procedures": 5}
    names.extend(_names_by(expansion_code=expansion_code, archetype=archetype, card_type=CardType.SCP_MANDATE)[:counts["mandates"]])
    names.extend(_names_by(expansion_code=expansion_code, archetype=archetype, card_type=CardType.SCP_PERSONNEL, subtype="Hero")[:counts["heroes"]])
    names.extend(_names_by(expansion_code=expansion_code, archetype=archetype, card_type=CardType.SCP_PERSONNEL, exclude_subtype="Hero")[:counts["personnel"]])
    names.extend(_names_by(expansion_code=expansion_code, archetype=archetype, card_type=CardType.SCP_FACILITY)[:counts["facilities"]])
    names.extend(_names_by(expansion_code=expansion_code, archetype=archetype, card_type=CardType.SCP_ANOMALY)[:counts["anomalies"]])
    names.extend(_names_by(expansion_code=expansion_code, archetype=archetype, card_type=CardType.SCP_PROCEDURE)[:counts["procedures"]])
    if len(names) < 25:
        raise ValueError(f"Expanded SCP deck {expansion_code}/{archetype} only has {len(names)} cards")
    return [SCP_CARDS[name] for name in names[:25]]


def make_secure_contain_research_deck():
    return [SCP_CARDS[name] for name in SECURE_CONTAIN_RESEARCH_NAMES]


def make_keter_risk_deck():
    return [SCP_CARDS[name] for name in KETER_RISK_NAMES]


def make_veil_control_deck():
    return [SCP_CARDS[name] for name in VEIL_CONTROL_NAMES]


def make_site_zero_redaction_lock_deck():
    return [SCP_CARDS[name] for name in SITE_ZERO_REDACTION_LOCK_NAMES]


ANTIMEMETIC_COLD_WAR_NAMES = [
    # Targeted nerf: previous build hybridized the SZB White Pill Ward
    # cluster too aggressively and clocked ~70-82% winrate, cloning
    # site_zero_redaction_lock's dominance. We drop the SZB White Pill
    # Ward Anomaly (the high-impact contained-bonus piece) and replace
    # with CORE Antimemetic Orchard (still on-theme, no SZB stack), and
    # we shave 1 SZB Quiet Recital Protocol back to a CORE breach
    # sweeper so the deck's procedure suite carries less SZB density.
    # Personnel (8) — unchanged
    "Memetics Analyst", "Memetics Analyst",
    "D-Class Volunteer", "D-Class Volunteer",
    "ACW Hero - Director Ana Vale",
    "SZB White Pill Ward Handler",
    "Sleep-Deprived Intern",
    "Junior Researcher",
    # Facilities (4): unchanged
    "Memetics Lab", "Memetics Lab",
    "Redaction Office", "Black Vault",
    # Anomalies (4): swap SZB White Pill Ward Anomaly -> CORE Antimemetic
    # Orchard (loses the SZB contained-bonus stack)
    "Moth in the Camera", "Moth in the Camera",
    "Antimemetic Orchard",
    "ACW Forgotten Embassy Anomaly",
    # Procedures (7): drop 1x SZB Quiet Recital -> CORE Null Room
    # Calibration (still breach relief, weaker payoff)
    "Class-A Amnestic Broadcast", "Class-A Amnestic Broadcast",
    "Witness Relocation", "Null Room Calibration",
    "Null Room Calibration",
    "Crisis Reframe", "Compelling Testimony",
    # Mandates (2): unchanged
    "There Is No Antimemetics Division",
    "SZB Directive 1: White Pill Ward",
]


def make_antimemetic_cold_war_deck():
    return [SCP_CARDS[name] for name in ANTIMEMETIC_COLD_WAR_NAMES]


KETER_BLACKOUT_NAMES = [
    # Rebuilt around the SZB Thaumiel grid (Halo Key, Mercy Engine, Friendly
    # Leviathan, Clockwork Saint, Paired Vault) — all have contained_bonus
    # from W2/agent(b) wiring. Heavy use of SZB Handler personnel with
    # on_assign hooks. Pairs with the now-lowered thaumiel alt-win (3 contained).
    # Personnel (8)
    "Containment Specialist", "Containment Specialist",
    "MTF Doorbreaker", "O5 Auditor",
    "KBO Hero - Captain Ferro Kane",
    "SZB Halo Key Handler", "SZB Halo Key Handler",
    "SZB Mercy Engine Handler",
    # Facilities (4): mix of CORE security + SZB Thaumiel facilities
    "Keter Annex", "Scranton Lattice",
    "SZB Friendly Leviathan Wing", "SZB Paired Vault Wing",
    # Anomalies (5): SZB Thaumiel grid + KBO native — all contained_bonus payoff
    "KBO Last Shepherd Anomaly",
    "SZB Halo Key Anomaly", "SZB Mercy Engine Anomaly",
    "SZB Friendly Leviathan Anomaly", "SZB Clockwork Saint Anomaly",
    # Procedures (5): sweepers + comeback reach
    "Lure It Into a Box", "Last Door Protocol", "Emergency Lockdown",
    "Crisis Reframe", "Compelling Testimony",
    # Mandates (3): two thaumiel routes + research support
    "Secure Mandate", "Contain Mandate", "KBO Mandate 1: Sunless Reactor",
]


def make_keter_blackout_deck():
    return [SCP_CARDS[name] for name in KETER_BLACKOUT_NAMES]


GOI_FRONTLINE_NAMES = [
    # Personnel (9): CORE staples + 2 GOI heroes for the suppress aura
    "D-Class Volunteer", "D-Class Volunteer",
    "Field Agent", "Field Agent",
    "Memetics Analyst", "O5 Auditor", "Sleep-Deprived Intern",
    "GOI Hero - Agent Felicity Graves", "GOI Hero - Captain Crowbar Venn",
    # Facilities (4): research + suppress engines
    "Redaction Office", "Redaction Office",
    "Amnestic Pharmacy", "GOI Broken Auction Wing",
    # Anomalies (3): high-curio for archive payoff + GOI public-leak flavor
    "GOI Anomalous Embassy Anomaly", "GOI Broken Auction Anomaly", "GOI Borderless Site Anomaly",
    # Procedures (7): secrecy-attack + opponent-audit + raid
    "GOI Raid Tip-Off", "GOI Raid Tip-Off",
    "Class-A Amnestic Broadcast",
    "Witness Relocation", "Whistleblower Leak",
    "Bureaucratic Labyrinth", "Cross-Test Proposal",
    # Mandates (2): GOI public_panic alt-win + research bonus
    "GOI Mandate 1: Serpent Consulate", "Contain Mandate",
]


def make_goi_frontline_deck():
    return [SCP_CARDS[name] for name in GOI_FRONTLINE_NAMES]


ETHICS_RECKONING_NAMES = [
    # Rebuilt to actually target the ethics_audit alt-win (4 Archives +
    # secrecy 8+). The previous build used "There Is No Antimemetics
    # Division" (alt_win=redaction: 3 Archives + secrecy 12+), which is
    # 4 secrecy harder and unrelated to ETH's ethics-debt motif. We now
    # use ETH Mandate 1: Mercy Ledger (alt_win=ethics_audit) and load
    # ETH-tribal procedures that push the secrecy/archive numbers
    # without painting "Memetics Analyst" tax.
    #
    # We also borrow MNR's Bystander pivot (Conference Attendee) — a
    # RT-0 research body that can Mnestic Wake by paying 1 ethics debt,
    # which ETH naturally produces.
    # Personnel (8): subtype-aura anchors + ETH-Specialist research engine
    "Ethics Liaison", "Ethics Liaison",
    "D-Class Volunteer",
    "MNR Conference Attendee",
    "O5 Auditor",
    "ETH Hero - Chairwoman Inez Salt", "ETH Hero - Dr. Gideon Vale",
    "ETH Burden Archive Specialist",
    # Facilities (4): ethics anchor + research engines
    "Ethics Committee Desk", "Ethics Committee Desk",
    "Memetics Lab", "Deepwell Archive",
    # Anomalies (5): contained-bonus payoffs + on-test rewards
    "ETH Audit Cathedral Anomaly", "ETH Patient Sun Anomaly",
    "ETH Confession Engine Anomaly", "ETH Burden Archive Anomaly",
    "ETH Mercy Ledger Anomaly",
    # Procedures (6): conversion engine + ETH-tribal secrecy/archive
    # pushers + comeback. Audit Cathedral Protocol (secrecy +3) is the
    # critical piece that lets the deck reach the 8 secrecy threshold.
    "Weaponize Ethics Debt",
    "ETH Audit Cathedral Protocol",
    "ETH Clean-Room Tribunal Protocol",
    "Witness Relocation",
    "Crisis Reframe", "Compelling Testimony",
    # Mandates (2): real ethics_audit alt-win + suppress aura
    "ETH Mandate 1: Mercy Ledger",
    "Protect Mandate",
]


def make_ethics_reckoning_deck():
    return [SCP_CARDS[name] for name in ETHICS_RECKONING_NAMES]


def make_oneiric_archives_deck():
    # Reverted from CORE-staple rebuild — OAR's archetype identity is
    # expansion-only (cooperative mood + Dream subtype auras), so the
    # generated _expanded_deck variant outperforms a CORE-anchored hand-tune
    # by ~19pts in 168-game tournament. Documented for future passes.
    return _expanded_deck("OAR", "oneiric")


MNESTIC_RESET_DIVISION_NAMES = [
    # Personnel (8): 6 Mnestic anchors + 2 Bystanders that can Mnestic Wake
    # to scale toward the Mnestic Saturation alt-win (5 active Mnestic + 4 archives).
    "MNR Forgotten Bureau Liaison", "MNR Forgotten Bureau Liaison",
    "MNR Memory Pattern Analyst", "MNR Mnemonic Surgeon",
    "MNR Class-A Inoculated Agent", "MNR Mnestic-Coated Operative",
    "MNR Conference Attendee", "MNR D-Class (No Recall)",
    # Facilities (4)
    "MNR Mnestic Ward", "MNR Antimemetic Quarantine Lab",
    "MNR Pre-Amnestic Records", "MNR Cognitive Anchor Array",
    # Anomalies (5)
    "MNR Memory Reef", "MNR Personnel Drift", "MNR Missing Floor",
    "MNR Soft Erasure", "MNR The Director's Note",
    # Procedures (6): one Redact, secrecy generation for Memory Hole,
    # cognitive sweeper to force opposing forgets, plus recovery tools.
    "MNR Memory Triage",
    "MNR Class-A Inoculation Dose",
    "MNR Mass Remembrance",
    "MNR Found Files",
    "MNR Cold Storage Open",
    "MNR Class-B Inoculation Drill",
    # Mandates (2): both MNR alt-win paths simultaneously
    "MNR Mandate 4: Mnestic Saturation",
    "MNR Mandate 1: Memory Hole",
]


def make_mnestic_reset_division_deck():
    return [SCP_CARDS[name] for name in MNESTIC_RESET_DIVISION_NAMES]


SCP_STARTER_DECKS = {
    "secure_contain_research": make_secure_contain_research_deck,
    "keter_risk": make_keter_risk_deck,
    "veil_control": make_veil_control_deck,
    "site_zero_redaction_lock": make_site_zero_redaction_lock_deck,
    "antimemetic_cold_war": make_antimemetic_cold_war_deck,
    "keter_blackout": make_keter_blackout_deck,
    "goi_frontline": make_goi_frontline_deck,
    "ethics_reckoning": make_ethics_reckoning_deck,
    "oneiric_archives": make_oneiric_archives_deck,
    "mnestic_reset_division": make_mnestic_reset_division_deck,
    **SITE_ZERO_DECK_FACTORIES,
}


__all__ = [
    "SCP_CARDS",
    "SCP_STARTER_DECKS",
    "make_secure_contain_research_deck",
    "make_keter_risk_deck",
    "make_veil_control_deck",
    "make_site_zero_redaction_lock_deck",
    "make_antimemetic_cold_war_deck",
    "make_keter_blackout_deck",
    "make_goi_frontline_deck",
    "make_ethics_reckoning_deck",
    "make_oneiric_archives_deck",
    "SITE_ZERO_SYNERGY_PACKAGES",
    "make_site_zero_masquerade_deck",
    "make_site_zero_quarantine_deck",
    "make_site_zero_thaumiel_deck",
    "make_site_zero_blackfile_deck",
    "make_site_zero_clean_hands_deck",
    "make_site_zero_veil_rotation_deck",
]
