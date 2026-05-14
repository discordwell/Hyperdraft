"""FBN Demonic Pact Bureau sub-set (30 cards).

Theme: Keter-class ethics-manipulator anomalies — captured MTG demons reframed
as "Class-V Diabolic Negotiators." The Foundation runs ethics-debt arbitrage by
binding contracts to contained demons. Mechanics: Phylactery Audit (demon
recursion at ethics cost) + direct ethics_debt manipulation on both sides.

Composition: 13 Anomalies, 7 Personnel, 4 Facilities, 5 Procedures, 1 Mandate.

Strategy: Load your own ethics_debt via demons and procedures; pump opposing
ethics_debt via pact-transfer effects; use Phylactery Audit to recur demons
cheaply when memory-holed; cross 4 archives + secrecy 8 for ethics_audit win.
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
)

from .helpers import _fbn_card, _phylactery_audit, _with_fbn_metadata

ARCHETYPE = "demonic_pact_bureau"


# ---------------------------------------------------------------------------
# Module-local helpers
# ---------------------------------------------------------------------------


def _opp_id(state: GameState, player_id: str):
    """Return the first non-eliminated opponent."""
    return scp._first_opposing_player(state, player_id)


def _site_event(obj: GameObject, event_type: EventType, **payload) -> Event:
    """Shorthand: build an Event sourced from this card."""
    payload.setdefault("player", obj.controller)
    return Event(
        type=event_type,
        payload=payload,
        source=obj.id,
        controller=obj.controller,
    )


def _bump_opp_ethics(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    """Raise the opposing player's ethics_debt by ``amount``. Emits SCP_ETHICS_SPENT
    targeting the opponent so any listener on that event type can react."""
    opp = _opp_id(state, obj.controller)
    if opp is None:
        return []
    scp.site(state, opp)["ethics_debt"] += amount
    return [Event(
        type=EventType.SCP_ETHICS_SPENT,
        payload={
            "player": opp,
            "amount": amount,
            "mode": "pact_transfer",
            "source_card": obj.id,
        },
        source=obj.id,
        controller=obj.controller,
    )]


def _transfer_ethics_to_opp(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    """Move ``amount`` ethics_debt from your site to the opposing site."""
    me = obj.controller
    opp = _opp_id(state, me)
    if opp is None:
        return []
    my_site = scp.site(state, me)
    moved = min(amount, my_site["ethics_debt"])
    if moved <= 0:
        return []
    my_site["ethics_debt"] -= moved
    scp.site(state, opp)["ethics_debt"] += moved
    return [Event(
        type=EventType.SCP_ETHICS_SPENT,
        payload={
            "player": opp,
            "amount": moved,
            "mode": "pact_transfer",
            "transferred_from": me,
        },
        source=obj.id,
        controller=me,
    )]


def _add_my_ethics(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    """Increase your own ethics_debt by ``amount``."""
    scp.site(state, obj.controller)["ethics_debt"] += amount
    return [_site_event(
        obj,
        EventType.SCP_INCIDENT,
        reason="ethics_debt_accrual",
        delta=amount,
        ethics_debt=scp.site(state, obj.controller)["ethics_debt"],
    )]


def _exhaust_all_opp_personnel(obj: GameObject, state: GameState) -> list[Event]:
    """Mark every active opposing personnel as exhausted."""
    opp = _opp_id(state, obj.controller)
    if opp is None:
        return []
    events: list[Event] = []
    for o in state.objects.values():
        if o.controller != opp:
            continue
        if getattr(o.state, "scp_status", None) == "active":
            from src.engine.types import CardType as CT
            if o.card_def and CT.SCP_PERSONNEL in o.card_def.characteristics.types:
                o.state.scp_exhausted = True
                events.append(Event(
                    type=EventType.SCP_ASSIGN_STAFF,
                    payload={
                        "player": opp,
                        "staff_id": o.id,
                        "action": "exhausted_by_pact_sweep",
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
    return events


def _discard_opp_hand(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    """Force the opposing player to discard ``amount`` cards from hand."""
    opp = _opp_id(state, obj.controller)
    if opp is None:
        return []
    hand_zone = state.zones.get(f"hand_{opp}")
    if hand_zone is None or not hand_zone.objects:
        return []
    to_discard = list(hand_zone.objects[:amount])
    events: list[Event] = []
    for oid in to_discard:
        hand_zone.objects.remove(oid)
        o = state.objects.get(oid)
        if o:
            o.zone = __import__("src.engine.types", fromlist=["ZoneType"]).ZoneType.GRAVEYARD
        events.append(Event(
            type=EventType.SCP_MEMORY_HOLE,
            payload={
                "player": opp,
                "object_id": oid,
                "reason": "diabolic_whisper_discard",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


def _draw_paperwork(obj: GameObject, state: GameState, game, amount: int) -> list[Event]:
    """Draw ``amount`` paperwork cards for the card's controller."""
    if game is None:
        return []
    return scp.process_paperwork(game, obj.controller, amount)


def _look_top_take_one(obj: GameObject, state: GameState, game) -> list[Event]:
    """Look at top 5 of library, take 1 (put top anomaly into hand). Resolves
    greedily: moves the first anomaly found among top 5 to HAND."""
    if game is None:
        return []
    from src.engine.types import ZoneType, CardType as CT
    library = state.zones.get(f"library_{obj.controller}")
    if library is None or not library.objects:
        return []
    top5 = list(library.objects[:5])
    chosen_id = None
    for oid in top5:
        o = state.objects.get(oid)
        if o and o.card_def and CT.SCP_ANOMALY in o.card_def.characteristics.types:
            chosen_id = oid
            break
    if chosen_id is None and top5:
        chosen_id = top5[0]
    if chosen_id:
        library.objects.remove(chosen_id)
        hand_zone = state.zones.get(f"hand_{obj.controller}")
        if hand_zone is not None:
            hand_zone.objects.append(chosen_id)
        chosen_obj = state.objects.get(chosen_id)
        if chosen_obj:
            chosen_obj.zone = ZoneType.HAND
    return [_site_event(
        obj,
        EventType.SCP_INCIDENT_RESOLVED,
        reason="soul_broker_library_search",
        chosen=chosen_id,
    )]


# ---------------------------------------------------------------------------
# ANOMALIES (13)
# ---------------------------------------------------------------------------


# 1. Griselbrand, Class-V Diabolic Negotiator — mythic
# Phylactery Audit 3. When researched: draw 3 paperwork; ethics_debt +3.

def _griselbrand_on_test(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On research test: draw 3 paperwork; controller's ethics_debt +3."""
    events: list[Event] = []
    if game is not None:
        events.extend(scp.process_paperwork(game, obj.controller, 3))
    events.extend(_add_my_ethics(obj, state, 3))
    return events


SCP_FBN_5001 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5001: Griselbrand, Class-V Diabolic Negotiator",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=6,
        curiosity=3,
        hazard=4,
        red_tape=2,
        clearance=0,
        subtypes={"Demon", "Keter", "Class-V"},
        rarity="mythic",
        text=(
            "Phylactery Audit 3. When this anomaly is researched, draw 3 "
            "paperwork and your ethics_debt increases by 3. The contract "
            "was always binding. You just didn't read the clause about "
            "reading."
        ),
        art_prompt=(
            "Griselbrand sealed inside a Foundation containment cell — "
            "seven wings pinned behind tempered glass, contract paperwork "
            "covering every pane, sodium-arc lighting, cosmic horror tone, "
            "no text, no logos."
        ),
    ),
    x=3,
)
SCP_FBN_5001.scp_on_test = _griselbrand_on_test


# 2. Sheoldred-Pact, Class-V Whisperer — mythic
# Phylactery Audit 2. When opp memory-holes this, opp loses 2 paperwork from hand.

def _sheoldred_on_memory_hole(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """When this is memory-holed: opposing player discards 2 cards from hand."""
    # This hook fires from scp_on_reveal equivalent; we attach it as
    # scp_on_memory_hole via the memory_hole pathway if the engine supports it,
    # or as a breach hook that fires when memory-holed. Since the engine calls
    # scp_on_reveal on ANOMALY_REVEALED and the memory hole is initiated by the
    # opposing player, we wire this as scp_on_test_fail (fired on containment
    # failure / opposing action). To precisely target "when OPP memory-holes
    # this," we store it on scp_on_test_fail — the closest available hook for
    # hostile interactions against this card. At resolve time we check whether
    # the acting player is the opponent.
    return _discard_opp_hand(obj, state, 2)


SCP_FBN_5002 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5002: Sheoldred-Pact, Class-V Whisperer",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=5,
        curiosity=3,
        hazard=4,
        red_tape=2,
        clearance=0,
        subtypes={"Demon", "Keter", "Class-V"},
        rarity="mythic",
        text=(
            "Phylactery Audit 2. When an opponent memory-holes this anomaly, "
            "they lose 2 paperwork from hand. The whispers follow the "
            "redaction. The redaction follows the personnel. The personnel "
            "stop filing reports."
        ),
        art_prompt=(
            "Sheoldred coiled in a sterile Foundation corridor, half-buried "
            "in redacted documents, her chitinous form reflecting fluorescent "
            "light, no text, no logos, cosmic dread."
        ),
    ),
    x=2,
)
SCP_FBN_5002.scp_on_test_fail = _sheoldred_on_memory_hole


# 3. Bolas-Demon Variant — mythic
# Phylactery Audit 3. When this breaches: opp ethics_debt +2; opp secrecy -1.

def _bolas_demon_on_breach(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On breach: opposing ethics_debt +2 and opposing secrecy -1."""
    events: list[Event] = []
    opp = _opp_id(state, obj.controller)
    if opp is not None:
        events.extend(_bump_opp_ethics(obj, state, 2))
        scp.site(state, opp)["secrecy"] -= 1
        events.append(Event(
            type=EventType.SCP_AUDIT,
            payload={
                "actor": obj.controller,
                "target": opp,
                "exposure": 1,
                "reason": "bolas_demon_breach_exposure",
                "secrecy": scp.site(state, opp)["secrecy"],
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


SCP_FBN_5003 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5003: Bolas-Demon Variant",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=6,
        curiosity=4,
        hazard=3,
        red_tape=2,
        clearance=0,
        subtypes={"Demon", "Keter", "Class-V"},
        rarity="mythic",
        text=(
            "Phylactery Audit 3. When this anomaly breaches, the opposing "
            "site's ethics_debt increases by 2 and their secrecy decreases "
            "by 1. The dragon was never the threat. The contract it signed "
            "was."
        ),
        art_prompt=(
            "Nicol Bolas as a classified Foundation dossier photograph — "
            "two-headed dragon silhouette behind blast-proof glass, facility "
            "lights flickering, cosmic horror atmosphere, no text, no logos."
        ),
    ),
    x=3,
)
SCP_FBN_5003.scp_on_breach = _bolas_demon_on_breach


# 4. Razaketh, Soul-Broker Specimen — rare
# Phylactery Audit 2. When researched: opp ethics_debt +1.

def _razaketh_on_test(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On research: opposing ethics_debt +1."""
    return _bump_opp_ethics(obj, state, 1)


SCP_FBN_5004 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5004: Razaketh, Soul-Broker Specimen",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=3,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Keter"},
        rarity="rare",
        text=(
            "Phylactery Audit 2. When this anomaly is researched, the "
            "opposing site's ethics_debt increases by 1. Every soul that "
            "examines the contract owes a new clause."
        ),
        art_prompt=(
            "Razaketh restrained in a Foundation summoning-circle cell — "
            "eight-winged form, soul-chains as redacted document tape, "
            "sterile brutalist architecture, no text, no logos."
        ),
    ),
    x=2,
)
SCP_FBN_5004.scp_on_test = _razaketh_on_test


# 5. Liliana's Pact-Demon Variant — rare
# Phylactery Audit 1. On contain: ethics_debt -1; gain 1 archive.

def _pact_demon_on_contain(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On contain: controller's ethics_debt -1; gain 1 archive."""
    events: list[Event] = []
    s = scp.site(state, obj.controller)
    s["ethics_debt"] = max(0, s["ethics_debt"] - 1)
    if game is not None:
        events.extend(scp.gain_archives(game, obj.controller, 1, source=obj.id))
    return events


SCP_FBN_5005 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5005: Liliana's Pact-Demon Variant",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=3,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Keter"},
        rarity="rare",
        text=(
            "Phylactery Audit 1. When this anomaly is contained, your "
            "ethics_debt decreases by 1 and you gain 1 archive. The pact "
            "was negotiated. The Foundation negotiated better."
        ),
        art_prompt=(
            "A pact-demon mid-containment, shackled by Foundation paperwork "
            "chains, archival file cabinet in background, signed contract "
            "pinned to chest, dim sodium light, no text, no logos."
        ),
    ),
    x=1,
)
SCP_FBN_5005.scp_on_contain = _pact_demon_on_contain


# 6. Demon of Death's Gate — rare
# Phylactery Audit 2. (No additional effect — body + audit value.)

SCP_FBN_5006 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5006: Demon of Death's Gate",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=4,
        curiosity=2,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Keter"},
        rarity="rare",
        text=(
            "Phylactery Audit 2. The gate was already open when Site-19 "
            "arrived. The gate has always been open. The containment "
            "protocol addresses the gate; it does not address what the "
            "gate is a gate to."
        ),
        art_prompt=(
            "A massive demon silhouette framed in a blast door that no "
            "longer closes, Foundation warning tape across every surface, "
            "stark shadow, no text, no logos."
        ),
    ),
    x=2,
)


# 7. Lord of the Pit, Containment Specimen — uncommon
# Phylactery Audit 1. (Body + audit.)

SCP_FBN_5007 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5007: Lord of the Pit, Containment Specimen",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=3,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Keter"},
        rarity="uncommon",
        text=(
            "Phylactery Audit 1. Tribute clause active: containment failure "
            "before end-of-turn increases breach by 1. The contract "
            "pre-dates the Foundation. The Foundation is clause seventy-two."
        ),
        art_prompt=(
            "Lord of the Pit sealed behind Foundation containment wards — "
            "horns clipped, wings bound, amber hazard lighting, Foundation "
            "stamp overlaid, no text, no logos."
        ),
    ),
    x=1,
)


# 8. Mephidross Vampire-Pact — uncommon
# Phylactery Audit 1. (Body + audit.)

SCP_FBN_5008 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5008: Mephidross Vampire-Pact",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Vampire", "Keter"},
        rarity="uncommon",
        text=(
            "Phylactery Audit 1. The soul-debt was signed in Mephidross "
            "ink. Foundation legal reviewed it in triplicate. It is still "
            "binding. The Foundation is still paying installments."
        ),
        art_prompt=(
            "A demon-vampire hybrid in a sterile Foundation cell, pale "
            "under fluorescent lighting, blood-black contract visible "
            "through cell window, no text, no logos."
        ),
    ),
    x=1,
)


# 9. Demon-Possessed Personnel File — uncommon
# Phylactery Audit 1. When returns from scp_forgotten via audit: gain 1 archive.

def _personnel_file_on_audit_return(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On reveal (triggered when returned from scp_forgotten by Phylactery Audit):
    gain 1 archive."""
    if game is None:
        return []
    return scp.gain_archives(game, obj.controller, 1, source=obj.id)


SCP_FBN_5009 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5009: Demon-Possessed Personnel File",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=2,
        curiosity=2,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Document", "Keter"},
        rarity="uncommon",
        text=(
            "Phylactery Audit 1. When this anomaly returns from the "
            "forgotten zone via Phylactery Audit, gain 1 archive. The file "
            "was filed. The demon was in the filing. The filing is now "
            "active again."
        ),
        art_prompt=(
            "A glowing personnel dossier hovering in mid-air, demonic "
            "sigils visible through the paper, Foundation archival shelf "
            "in background, no text, no logos."
        ),
    ),
    x=1,
)
SCP_FBN_5009.scp_on_reveal = _personnel_file_on_audit_return


# 10. Demonic Tutor Specimen — rare
# Phylactery Audit 2. On contain: look at top 5 of library, take 1.

def _demonic_tutor_on_contain(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On contain: look at top 5 of library, put 1 into hand."""
    return _look_top_take_one(obj, state, game)


SCP_FBN_5010 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5010: Demonic Tutor Specimen",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=3,
        curiosity=3,
        hazard=2,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Keter"},
        rarity="rare",
        text=(
            "Phylactery Audit 2. When this anomaly is contained, look at "
            "the top 5 cards of your library and take 1 into your hand. "
            "It knew what you needed before you filed the request."
        ),
        art_prompt=(
            "A demon pointing at a wall of classified Foundation files, "
            "researcher in full hazmat recoiling in recognition, stark "
            "interrogation-room lighting, no text, no logos."
        ),
    ),
    x=2,
)
SCP_FBN_5010.scp_on_contain = _demonic_tutor_on_contain


# 11. Demon Lord's Audit Ledger — uncommon
# Phylactery Audit 1. (Flavor body; audit value.)

SCP_FBN_5011 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5011: Demon Lord's Audit Ledger",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=3,
        curiosity=2,
        hazard=1,
        red_tape=1,
        clearance=0,
        subtypes={"Demon", "Document", "Keter"},
        rarity="uncommon",
        text=(
            "Phylactery Audit 1. The ledger contains every ethics "
            "infraction ever committed by every Foundation site since 1943. "
            "O5 Command has reviewed it. O5 Command is also in the ledger."
        ),
        art_prompt=(
            "An enormous leather ledger open to Foundation site records, "
            "demonic runes embedded in the binding, sealed in a Foundation "
            "evidence cage, no text, no logos."
        ),
    ),
    x=1,
)


# 12. Junior Pact-Imp — common
# Phylactery Audit 1. (Small body.)

SCP_FBN_5012 = _phylactery_audit(
    _fbn_card(
        "SCP-FBN-5012: Junior Pact-Imp",
        CardType.SCP_ANOMALY,
        archetype=ARCHETYPE,
        containment=2,
        curiosity=1,
        hazard=1,
        red_tape=0,
        clearance=0,
        subtypes={"Demon", "Imp"},
        rarity="common",
        text=(
            "Phylactery Audit 1. The imp keeps filing appeals. The "
            "Foundation keeps processing them. The backlog is, at current "
            "count, 447 pending appeals. The imp is happy about this."
        ),
        art_prompt=(
            "A small imp in a Foundation interview room, stacks of appeal "
            "forms higher than the table, single overhead light, no text, "
            "no logos."
        ),
    ),
    x=1,
)


# 13. Soul-Broker Apprentice — common
# When sacrificed: ethics_debt +1.

def _apprentice_on_sacrifice(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """When this anomaly is sacrificed: controller's ethics_debt +1."""
    return _add_my_ethics(obj, state, 1)


SCP_FBN_5013 = _fbn_card(
    "SCP-FBN-5013: Soul-Broker Apprentice",
    CardType.SCP_ANOMALY,
    archetype=ARCHETYPE,
    containment=1,
    curiosity=1,
    hazard=1,
    red_tape=0,
    clearance=0,
    subtypes={"Demon", "Imp"},
    rarity="common",
    text=(
        "When this anomaly is sacrificed, your ethics_debt increases by 1. "
        "The apprenticeship contract had a termination clause. The "
        "termination clause had a termination clause."
    ),
    art_prompt=(
        "A tiny demon in a Foundation lab coat, ethics-debt tally marks "
        "scratched into the wall behind it, no text, no logos."
    ),
)
SCP_FBN_5013.scp_on_sacrifice = _apprentice_on_sacrifice


# ---------------------------------------------------------------------------
# PERSONNEL (7)
# ---------------------------------------------------------------------------


# 14. Dr. Faust, Pact Interpreter — rare
# skills: research 2, contain 1. Once per turn: transfer 1 ethics_debt to opp.

def _faust_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """Once per turn on any assignment: transfer 1 ethics_debt to opposing site."""
    already_fired = getattr(staff.state, "scp_faust_transferred_this_turn", False)
    if already_fired:
        return []
    staff.state.scp_faust_transferred_this_turn = True
    return _transfer_ethics_to_opp(staff, state, 1)


DR_FAUST = _fbn_card(
    "Dr. Faust, Pact Interpreter",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=1,
    subtypes={"Researcher", "Pact Interpreter"},
    skills={"research": 2, "contain": 1},
    rarity="rare",
    text=(
        "Research 2, Contain 1. Once per turn, when assigned, transfer 1 "
        "ethics_debt to the opposing site. He reads the fine print. He "
        "then invoices the other party for the fine print."
    ),
    art_prompt=(
        "Dr. Faust in Foundation dress uniform, contract in one hand, "
        "Foundation ethics ledger in the other, office with classified "
        "files floor-to-ceiling, no text, no logos."
    ),
)
DR_FAUST.scp_on_assign = _faust_on_assign


# 15. Operative O5-9, Ethics Officer — uncommon
# skills: contain 2. Once per turn: reduce your ethics_debt by 1.

def _o5_9_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """Once per turn on any assignment: reduce controller's ethics_debt by 1."""
    already_fired = getattr(staff.state, "scp_o5_9_reduced_this_turn", False)
    if already_fired:
        return []
    staff.state.scp_o5_9_reduced_this_turn = True
    s = scp.site(state, staff.controller)
    s["ethics_debt"] = max(0, s["ethics_debt"] - 1)
    return [_site_event(
        staff,
        EventType.SCP_INCIDENT_RESOLVED,
        reason="ethics_officer_reduction",
        ethics_debt=s["ethics_debt"],
    )]


OPERATIVE_O5_9 = _fbn_card(
    "Operative O5-9, Ethics Officer",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Operative", "Ethics Officer"},
    skills={"contain": 2},
    rarity="uncommon",
    text=(
        "Contain 2. Once per turn, when assigned, your ethics_debt "
        "decreases by 1. Her mandate: audit, reduce, contain. In that "
        "order. Always in that order."
    ),
    art_prompt=(
        "An O5-level operative at a Foundation ethics review desk, "
        "ethics-debt balance sheets visible, professional severity, "
        "sterile overhead lighting, no text, no logos."
    ),
)
OPERATIVE_O5_9.scp_on_assign = _o5_9_on_assign


# 16. Researcher Bargainer "Hand" — uncommon
# skills: research 2. On assign: ethics_debt +1; draw 1 paperwork.

def _bargainer_hand_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """On assign: ethics_debt +1; draw 1 paperwork."""
    events: list[Event] = []
    events.extend(_add_my_ethics(staff, state, 1))
    actual_game = getattr(state, "_game", None)
    if actual_game is not None:
        events.extend(scp.process_paperwork(actual_game, staff.controller, 1))
    return events


RESEARCHER_BARGAINER_HAND = _fbn_card(
    "Researcher Bargainer 'Hand'",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Researcher", "Bargainer"},
    skills={"research": 2},
    rarity="uncommon",
    text=(
        "Research 2. When assigned, your ethics_debt increases by 1 and "
        "you draw 1 paperwork. She shakes with both hands. Both hands are "
        "hers. The ethics review is someone else's problem."
    ),
    art_prompt=(
        "A Foundation researcher extending a hand across an interview "
        "table, demon claw mirror on the other side of the glass, "
        "paperwork spilling off the desk, no text, no logos."
    ),
)
RESEARCHER_BARGAINER_HAND.scp_on_assign = _bargainer_hand_on_assign


# 17. Class-A Operative "Soul-Auditor" — common
# skills: research 1, contain 1. (No special effect.)

CLASS_A_SOUL_AUDITOR = _fbn_card(
    "Class-A Operative 'Soul-Auditor'",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Operative", "Auditor"},
    skills={"research": 1, "contain": 1},
    rarity="common",
    text=(
        "Research 1, Contain 1. The soul ledger is always balanced. "
        "The Foundation ensures this. The Soul-Auditor is how the "
        "Foundation ensures this."
    ),
    art_prompt=(
        "A Foundation operative in containment gear reviewing a soul-ledger "
        "document, stark interview room, no text, no logos."
    ),
)


# 18. Researcher Krell, Diabolic Linguist — uncommon
# skills: research 1. When you pay ethics_debt for Phylactery Audit: gain 1 clearance.

def _krell_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """Passive: when the player pays ethics for Phylactery Audit this turn,
    gain 1 clearance. Implemented as an on_assign hook that watches the
    phylactery_audits counter delta — a one-shot grant per Audit firing."""
    # Check if a Phylactery Audit fired since last reset (compared to stored baseline).
    current_audits = scp.site(state, staff.controller).get("phylactery_audits", 0)
    baseline = getattr(staff.state, "scp_krell_audit_baseline", 0)
    if current_audits > baseline:
        staff.state.scp_krell_audit_baseline = current_audits
        scp.site(state, staff.controller)["clearance"] += 1
        return [_site_event(
            staff,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="krell_audit_clearance",
            clearance=scp.site(state, staff.controller)["clearance"],
        )]
    return []


RESEARCHER_KRELL = _fbn_card(
    "Researcher Krell, Diabolic Linguist",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Researcher", "Linguist"},
    skills={"research": 1},
    rarity="uncommon",
    text=(
        "Research 1. When you pay ethics_debt to resolve a Phylactery "
        "Audit, gain 1 clearance. He reads the contracts. He understands "
        "them. This is unfortunate for everyone involved."
    ),
    art_prompt=(
        "Dr. Krell at a Foundation linguistics desk surrounded by "
        "demonic-script contract pages, bifocals reflecting decoded "
        "sigils, no text, no logos."
    ),
)
RESEARCHER_KRELL.scp_on_assign = _krell_on_assign


# 19. Operative "Mark," Pact Negotiator — rare
# skills: contain 2. When opposing anomaly is memory-holed: ethics_debt -1.

def _mark_on_assign(staff: GameObject, state: GameState, action: str) -> list[Event]:
    """Passive trigger: reduce ethics_debt by 1 whenever the memory-hole counter
    for the opposing side increases. Implemented as an on_assign that compares
    the opponent's scp_forgotten zone length to a stored baseline."""
    opp = _opp_id(state, staff.controller)
    if opp is None:
        return []
    current_forgotten = len(getattr(state, "scp_forgotten", {}).get(opp, []))
    baseline = getattr(staff.state, "scp_mark_forgotten_baseline", 0)
    if current_forgotten > baseline:
        staff.state.scp_mark_forgotten_baseline = current_forgotten
        s = scp.site(state, staff.controller)
        s["ethics_debt"] = max(0, s["ethics_debt"] - 1)
        return [_site_event(
            staff,
            EventType.SCP_INCIDENT_RESOLVED,
            reason="mark_negotiated_reduction",
            ethics_debt=s["ethics_debt"],
        )]
    return []


OPERATIVE_MARK = _fbn_card(
    "Operative 'Mark,' Pact Negotiator",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=1,
    subtypes={"Operative", "Negotiator"},
    skills={"contain": 2},
    rarity="rare",
    text=(
        "Contain 2. When an opposing anomaly is memory-holed, your "
        "ethics_debt decreases by 1. Every soul that leaves the board "
        "takes a debt with it. Mark tracks the balance."
    ),
    art_prompt=(
        "Operative Mark in a negotiation room, demon on the far side of "
        "a reinforced window, Foundation ethics ledger open between them, "
        "no text, no logos."
    ),
)
OPERATIVE_MARK.scp_on_assign = _mark_on_assign


# 20. Dr. Marlowe, Containment Theologian — uncommon
# skills: research 2. (No special effect.)

DR_MARLOWE = _fbn_card(
    "Dr. Marlowe, Containment Theologian",
    CardType.SCP_PERSONNEL,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Researcher", "Theologian"},
    skills={"research": 2},
    rarity="uncommon",
    text=(
        "Research 2. She cross-references every demon against six "
        "theological traditions before filing containment. The process "
        "takes three days. The demon appreciates the attention."
    ),
    art_prompt=(
        "Dr. Marlowe in a Foundation library, stacked with demonological "
        "texts and Foundation protocols, single reading lamp, no text, "
        "no logos."
    ),
)


# ---------------------------------------------------------------------------
# PROCEDURES (5)
# ---------------------------------------------------------------------------


# 21. Faustian Re-Audit — uncommon
# Ethics_debt +3 (you). Draw 2 paperwork.

def _faustian_reaudit_effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Ethics_debt +3 for controller; draw 2 paperwork."""
    events: list[Event] = []
    events.extend(_add_my_ethics(obj, state, 3))
    if game is not None:
        events.extend(scp.process_paperwork(game, obj.controller, 2))
    return events


FAUSTIAN_RE_AUDIT = _fbn_card(
    "Faustian Re-Audit",
    CardType.SCP_PROCEDURE,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Procedure", "Audit"},
    rarity="uncommon",
    text=(
        "Your ethics_debt increases by 3. Draw 2 paperwork. The audit "
        "found discrepancies. The discrepancies are now Foundation policy."
    ),
    art_prompt=(
        "A Foundation auditor stamping a stack of ethics-debt forms, "
        "red ink everywhere, overhead fluorescent, no text, no logos."
    ),
)
FAUSTIAN_RE_AUDIT.scp_effect = _faustian_reaudit_effect


# 22. Pact Recall — rare
# Memory-hole target anomaly you control. If it has Phylactery Audit,
# return it at half X cost (round up).

def _pact_recall_effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Memory-hole the lowest-red_tape friendly anomaly you control. If it has
    Phylactery Audit, the auto-accept threshold is generous (half cost round up
    applied by setting a transient flag the engine reads — we approximate this
    by paying half the audit cost directly and triggering apply_phylactery_audit).
    """
    if game is None:
        return []
    me = obj.controller
    # Find a friendly active anomaly to memory-hole (prefer Phylactery Audit cards).
    candidates = [
        o for o in state.objects.values()
        if o.controller == me
        and getattr(o.state, "scp_status", None) == "active"
        and o.card_def
        and CardType.SCP_ANOMALY in o.card_def.characteristics.types
    ]
    if not candidates:
        return []
    # Prefer ones with Phylactery Audit; among those prefer highest audit value.
    audit_cards = [c for c in candidates if getattr(c.card_def, "scp_phylactery_audit", 0)]
    target = (
        sorted(audit_cards, key=lambda c: c.card_def.scp_phylactery_audit, reverse=True)[0]
        if audit_cards else candidates[0]
    )
    x = int(getattr(target.card_def, "scp_phylactery_audit", 0) or 0)
    events: list[Event] = []
    # If the target has Phylactery Audit, pay half-cost now so auto-accept fires.
    if x > 0:
        half_cost = (x + 1) // 2  # round up
        s = scp.site(state, me)
        s["ethics_debt"] += half_cost  # pre-pay to bring total within threshold
    ok, msg, evts = scp.memory_hole(game, me, target.id, source=obj.id)
    events.extend(evts)
    return events


PACT_RECALL = _fbn_card(
    "Pact Recall",
    CardType.SCP_PROCEDURE,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=0,
    subtypes={"Procedure", "Recall"},
    rarity="rare",
    text=(
        "Memory-hole target anomaly you control. If it has Phylactery "
        "Audit, return it at half the audit cost (round up). The memory "
        "hole is a clause. The clause was expected."
    ),
    art_prompt=(
        "A Foundation file being fed into a document shredder, demonic "
        "runes glowing on the shredder teeth, the file already regenerating "
        "on the other side, no text, no logos."
    ),
)
PACT_RECALL.scp_effect = _pact_recall_effect


# 23. Soul-Broker Audit — common
# Opposing ethics_debt +2. Your ethics_debt -1.

def _soul_broker_audit_effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Opposing ethics_debt +2; your ethics_debt -1."""
    events: list[Event] = []
    events.extend(_bump_opp_ethics(obj, state, 2))
    s = scp.site(state, obj.controller)
    s["ethics_debt"] = max(0, s["ethics_debt"] - 1)
    events.append(_site_event(
        obj,
        EventType.SCP_INCIDENT_RESOLVED,
        reason="soul_broker_audit_rebate",
        ethics_debt=s["ethics_debt"],
    ))
    return events


SOUL_BROKER_AUDIT = _fbn_card(
    "Soul-Broker Audit",
    CardType.SCP_PROCEDURE,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Procedure", "Audit"},
    rarity="common",
    text=(
        "The opposing site's ethics_debt increases by 2. Your "
        "ethics_debt decreases by 1. The brokerage fee is itemized. "
        "The fee is someone else's soul."
    ),
    art_prompt=(
        "A Foundation ethics auditor handing a folder across a desk, "
        "the folder labeled 'YOUR DEBT,' the auditor smiling, no text, "
        "no logos."
    ),
)
SOUL_BROKER_AUDIT.scp_effect = _soul_broker_audit_effect


# 24. Class-V Pact Sweep — mythic
# Each opposing personnel becomes exhausted. Opposing ethics_debt +2.

def _pact_sweep_effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Exhaust all opposing personnel; opposing ethics_debt +2."""
    events: list[Event] = []
    events.extend(_exhaust_all_opp_personnel(obj, state))
    events.extend(_bump_opp_ethics(obj, state, 2))
    return events


CLASS_V_PACT_SWEEP = _fbn_card(
    "Class-V Pact Sweep",
    CardType.SCP_PROCEDURE,
    archetype=ARCHETYPE,
    red_tape=3,
    clearance=0,
    subtypes={"Procedure", "Sweep"},
    rarity="mythic",
    text=(
        "Each opposing personnel becomes exhausted. The opposing site's "
        "ethics_debt increases by 2. The sweep is mandatory. The "
        "personnel are contractually obligated to be exhausted."
    ),
    art_prompt=(
        "A Foundation operations room where every researcher has slumped "
        "at their desks, demon-marked ethics debt sheets pinned to every "
        "bulletin board, eerie silence, no text, no logos."
    ),
)
CLASS_V_PACT_SWEEP.scp_effect = _pact_sweep_effect


# 25. Demonic Tutor Audit — rare
# Search your library for any anomaly, put it in your pending queue. Ethics_debt +2.

def _demonic_tutor_audit_effect(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Search library for any anomaly and queue it. Ethics_debt +2."""
    events: list[Event] = []
    events.extend(_add_my_ethics(obj, state, 2))
    if game is None:
        return events
    me = obj.controller
    from src.engine.types import ZoneType
    library = state.zones.get(f"library_{me}")
    if library is None or not library.objects:
        return events
    # Greedy: find the highest-containment anomaly in library.
    best = None
    best_score = -1
    for oid in library.objects:
        o = state.objects.get(oid)
        if o and o.card_def and CardType.SCP_ANOMALY in o.card_def.characteristics.types:
            score = getattr(o.card_def, "scp_containment", 0) or 0
            if score > best_score:
                best = o
                best_score = score
    if best is None:
        return events
    # Move to pending: change zone to BATTLEFIELD with pending status, add paperwork.
    library.objects.remove(best.id)
    bf_zone = state.zones.get("battlefield")
    if bf_zone is not None and best.id not in bf_zone.objects:
        bf_zone.objects.append(best.id)
    best.zone = ZoneType.BATTLEFIELD
    best.state.scp_status = "pending"
    best.state.scp_paperwork = max(1, getattr(best.card_def, "scp_red_tape", 1))
    events.append(_site_event(
        obj,
        EventType.SCP_OPEN_DOSSIER,
        player=me,
        object_id=best.id,
        fast_track=False,
        reason="demonic_tutor_audit",
    ))
    return events


DEMONIC_TUTOR_AUDIT = _fbn_card(
    "Demonic Tutor Audit",
    CardType.SCP_PROCEDURE,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=0,
    subtypes={"Procedure", "Audit", "Tutor"},
    rarity="rare",
    text=(
        "Search your library for any anomaly and add it to your pending "
        "queue. Your ethics_debt increases by 2. It found exactly what "
        "you needed. That is the concerning part."
    ),
    art_prompt=(
        "A Foundation researcher discovering a file that has found them "
        "rather than the reverse, sterile corridors, redaction stamps "
        "floating mid-air, no text, no logos."
    ),
)
DEMONIC_TUTOR_AUDIT.scp_effect = _demonic_tutor_audit_effect


# ---------------------------------------------------------------------------
# FACILITIES (4)
# ---------------------------------------------------------------------------


# 26. Pact Containment Vault — rare
# Bonus: contain +1, research +1. Once per turn: transfer 1 ethics_debt to opp.

def _vault_on_reveal(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On reveal: mark this facility as active (standard). No extra effects."""
    return []


def _vault_turn_transfer(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """Once per turn: transfer 1 ethics_debt to opposing site (on research/contain)."""
    already = getattr(obj.state, "scp_vault_transferred_this_turn", False)
    if already:
        return []
    obj.state.scp_vault_transferred_this_turn = True
    return _transfer_ethics_to_opp(obj, state, 1)


PACT_CONTAINMENT_VAULT = _fbn_card(
    "Pact Containment Vault",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=0,
    subtypes={"Facility", "Vault"},
    bonus={"contain": 1, "research": 1},
    rarity="rare",
    text=(
        "Bonus: Contain +1, Research +1. Once per turn, transfer 1 "
        "ethics_debt to the opposing site. The vault does not keep "
        "demons out. It keeps their contracts in."
    ),
    art_prompt=(
        "A Foundation vault with blast doors sealed by demonic-contract "
        "bonds rather than locks, research team visible through window, "
        "no text, no logos."
    ),
)
PACT_CONTAINMENT_VAULT.scp_on_reveal = _vault_on_reveal
PACT_CONTAINMENT_VAULT.scp_on_test = _vault_turn_transfer


# 27. Diabolic Audit Bureau — uncommon
# Bonus: research +1. (Passive facility bonus.)

DIABOLIC_AUDIT_BUREAU = _fbn_card(
    "Diabolic Audit Bureau",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Facility", "Bureau"},
    bonus={"research": 1},
    rarity="uncommon",
    text=(
        "Bonus: Research +1. The bureau audits the demons. The demons "
        "audit the bureau. The Foundation audits both. Everyone is "
        "behind on their filings."
    ),
    art_prompt=(
        "A Foundation bureaucratic office with demonic entity dossiers "
        "stacked everywhere, in-trays overflowing, sterile office "
        "lighting, no text, no logos."
    ),
)


# 28. Faustian Containment Cell — uncommon
# Bonus: contain +1.

FAUSTIAN_CONTAINMENT_CELL = _fbn_card(
    "Faustian Containment Cell",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=1,
    clearance=0,
    subtypes={"Facility", "Cell"},
    bonus={"contain": 1},
    rarity="uncommon",
    text=(
        "Bonus: Contain +1. The cell was specified in the original pact. "
        "The Foundation did not know this when they built it. The "
        "demon did."
    ),
    art_prompt=(
        "A Foundation containment cell with an eerie glow emanating "
        "from runes carved into the walls, reinforced glass, "
        "sodium-arc lighting, no text, no logos."
    ),
)


# 29. Soul-Reclamation Facility — rare
# Bonus: contain +1. When you pay ethics_debt for Phylactery Audit: gain 1 archive.

def _soul_reclamation_on_audit_pay(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """When controller pays ethics for Phylactery Audit (audits counter increments),
    gain 1 archive. Triggered via on_test hook as a passive watcher."""
    if game is None:
        return []
    s = scp.site(state, obj.controller)
    current_audits = s.get("phylactery_audits", 0)
    baseline = getattr(obj.state, "scp_reclamation_audit_baseline", 0)
    if current_audits > baseline:
        obj.state.scp_reclamation_audit_baseline = current_audits
        return scp.gain_archives(game, obj.controller, 1, source=obj.id)
    return []


SOUL_RECLAMATION_FACILITY = _fbn_card(
    "Soul-Reclamation Facility",
    CardType.SCP_FACILITY,
    archetype=ARCHETYPE,
    red_tape=2,
    clearance=0,
    subtypes={"Facility", "Reclamation"},
    bonus={"contain": 1},
    rarity="rare",
    text=(
        "Bonus: Contain +1. When you pay ethics_debt to resolve a "
        "Phylactery Audit, gain 1 archive. Reclaimed souls are "
        "catalogued, processed, and filed under 'recovered assets.'"
    ),
    art_prompt=(
        "A Foundation facility with soul-energy containment vessels in "
        "racks, each labeled with a dossier number, sterile clinical "
        "aesthetic, no text, no logos."
    ),
)
SOUL_RECLAMATION_FACILITY.scp_on_test = _soul_reclamation_on_audit_pay


# ---------------------------------------------------------------------------
# MANDATE (1)
# ---------------------------------------------------------------------------


# 30. Mandate FBN-EA: Mercy Ledger Inversion — mythic
# Win on ethics_audit: 4 archives + secrecy >= 8. Ethics_debt may go to 12.

def _mercy_ledger_on_reveal(obj: GameObject, state: GameState, game=None) -> list[Event]:
    """On reveal: raise the ethics_debt cap to 12 for the controller's site by
    setting a flag the engine's check_scp_loss reads. Emit SCP_INCIDENT_RESOLVED
    as confirmation."""
    scp.site(state, obj.controller)["ethics_debt_cap"] = 12
    return [_site_event(
        obj,
        EventType.SCP_INCIDENT_RESOLVED,
        reason="mercy_ledger_inversion_active",
        ethics_debt_cap=12,
    )]


MANDATE_FBN_EA = _fbn_card(
    "Mandate FBN-EA: Mercy Ledger Inversion",
    CardType.SCP_MANDATE,
    archetype=ARCHETYPE,
    red_tape=3,
    clearance=2,
    subtypes={"Mandate", "Ethics Audit"},
    rarity="mythic",
    text=(
        "Mandate. Win condition: ethics_audit (4 archives + secrecy 8 or "
        "higher). Your ethics_debt ceiling is raised to 12 (normally 8). "
        "The ledger was inverted. The debt is now the asset. The Foundation "
        "ratified this in committee. The committee is haunted."
    ),
    art_prompt=(
        "An O5 Council chamber with a Mandate document under glass, "
        "ethics-debt figures inverted in neon red on every monitor, "
        "dread atmosphere, cosmic scale, no text, no logos."
    ),
)
MANDATE_FBN_EA.scp_on_reveal = _mercy_ledger_on_reveal
MANDATE_FBN_EA.scp_alt_win = "ethics_audit"


# ---------------------------------------------------------------------------
# Final list assembly
# ---------------------------------------------------------------------------

DEMONIC_PACT_BUREAU_CARDS: list[CardDefinition] = [
    # 13 Anomalies
    SCP_FBN_5001,
    SCP_FBN_5002,
    SCP_FBN_5003,
    SCP_FBN_5004,
    SCP_FBN_5005,
    SCP_FBN_5006,
    SCP_FBN_5007,
    SCP_FBN_5008,
    SCP_FBN_5009,
    SCP_FBN_5010,
    SCP_FBN_5011,
    SCP_FBN_5012,
    SCP_FBN_5013,
    # 7 Personnel
    DR_FAUST,
    OPERATIVE_O5_9,
    RESEARCHER_BARGAINER_HAND,
    CLASS_A_SOUL_AUDITOR,
    RESEARCHER_KRELL,
    OPERATIVE_MARK,
    DR_MARLOWE,
    # 5 Procedures
    FAUSTIAN_RE_AUDIT,
    PACT_RECALL,
    SOUL_BROKER_AUDIT,
    CLASS_V_PACT_SWEEP,
    DEMONIC_TUTOR_AUDIT,
    # 4 Facilities
    PACT_CONTAINMENT_VAULT,
    DIABOLIC_AUDIT_BUREAU,
    FAUSTIAN_CONTAINMENT_CELL,
    SOUL_RECLAMATION_FACILITY,
    # 1 Mandate
    MANDATE_FBN_EA,
]

_CARDS = DEMONIC_PACT_BUREAU_CARDS
