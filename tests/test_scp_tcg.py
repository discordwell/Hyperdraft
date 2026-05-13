import asyncio
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

from src.engine.game import Game
from src.engine.types import CardType, EventType, ZoneType
from src.engine import scp
from src.cards.scp import SCP_CARDS, SCP_STARTER_DECKS


def _setup():
    game = Game(mode="scp")
    p1 = game.add_player("Site-01")
    p2 = game.add_player("Site-02")
    game.setup_scp_player(p1, [])
    game.setup_scp_player(p2, [])
    return game, p1, p2


def _hand_card(game, player, name):
    card_def = SCP_CARDS[name]
    return game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_scp_card_pool_has_distinct_types_and_starter_decks():
    assert len(SCP_CARDS) >= 680
    types = {
        card_type
        for card in SCP_CARDS.values()
        for card_type in card.characteristics.types
    }
    assert {
        CardType.SCP_ANOMALY,
        CardType.SCP_PERSONNEL,
        CardType.SCP_FACILITY,
        CardType.SCP_PROCEDURE,
        CardType.SCP_MANDATE,
    }.issubset(types)
    expansion_codes = {getattr(card, "scp_expansion_code", None) for card in SCP_CARDS.values()}
    assert {"CORE", "ACW", "KBO", "GOI", "ETH", "OAR", "SZB"}.issubset(expansion_codes)
    assert all(getattr(card, "scp_art_prompt", "") for card in SCP_CARDS.values())
    assert any(card.rarity == "mythic" and "Hero" in card.characteristics.subtypes for card in SCP_CARDS.values())
    assert all(len(factory()) == 25 for factory in SCP_STARTER_DECKS.values())
    assert len(SCP_STARTER_DECKS) >= 14


def test_site_zero_expansion_has_mechanics_and_candidate_decks():
    site_zero = [card for card in SCP_CARDS.values() if getattr(card, "scp_expansion_code", None) == "SZB"]

    assert len(site_zero) == 180
    assert {
        "broken_masquerade",
        "mnestic_quarantine",
        "thaumiel_grid",
        "blackfile_bureau",
        "clean_hands",
        "veil_rotation",
    }.issubset({getattr(card, "scp_archetype", None) for card in site_zero})
    keywords = {keyword for card in site_zero for keyword in getattr(card, "scp_keywords", [])}
    assert {"Anchor", "Blackfile", "Brief", "Overexpose", "Quarantine", "Rotation"}.issubset(keywords)
    for deck_id in [
        "site_zero_masquerade",
        "site_zero_quarantine",
        "site_zero_thaumiel",
        "site_zero_blackfile",
        "site_zero_clean_hands",
        "site_zero_veil_rotation",
    ]:
        deck = SCP_STARTER_DECKS[deck_id]()
        assert len(deck) == 25
        assert all(getattr(card, "scp_expansion_code", None) == "SZB" for card in deck)


def test_site_zero_redaction_lock_is_registered_legal_and_mixed():
    from src.server.services.game_registry import get_deck_rules

    deck = SCP_STARTER_DECKS["site_zero_redaction_lock"]()
    rules = get_deck_rules("scp")
    names = [card.name for card in deck]
    counts = Counter(names)
    expansion_codes = {getattr(card, "scp_expansion_code", None) for card in deck}

    assert len(deck) == rules.min_main
    assert all(count <= rules.max_copies for count in counts.values())
    assert {"CORE", "SZB"}.issubset(expansion_codes)
    assert "There Is No Antimemetics Division" in names
    assert "SZB Quiet Recital Protocol" in names


def test_create_match_scp_sets_up_sites_and_starter_decks():
    from src.server.models import CreateMatchRequest
    from src.server.routes.match import create_match
    from src.server.session import session_manager

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="scp",
                player_deck_id="veil_control",
                ai_deck_id="keter_risk",
                ai_difficulty="medium",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None
        assert session.game.state.game_mode == "scp"
        assert len(session.player_ids) == 2
        for pid in session.player_ids:
            assert pid in session.game.state.scp_sites
            library = session.game.state.zones[f"library_{pid}"]
            assert len(library.objects) == 25
        state = session.get_client_state(response.player_id)
        assert state.game_mode == "scp"
        assert response.player_id in state.scp_sites

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_open_dossier_uses_paperwork_queue_before_activation():
    game, p1, _p2 = _setup()
    facility = _hand_card(game, p1, "Site-19 Intake Wing")

    ok, message, events = scp.open_dossier(game, p1.id, facility.id)

    assert ok, message
    assert facility.zone == ZoneType.BATTLEFIELD
    assert facility.state.scp_status == "pending"
    assert facility.state.scp_paperwork == 1
    assert facility.id not in game.state.scp_facilities[p1.id]
    assert any(event.type == EventType.SCP_OPEN_DOSSIER for event in events)

    tick_events = scp.process_paperwork(game, p1.id)

    assert facility.state.scp_status == "active"
    assert facility.state.scp_paperwork == 0
    assert facility.id in game.state.scp_facilities[p1.id]
    assert any(event.type == EventType.SCP_ACTIVATE_DOSSIER for event in tick_events)


def test_fast_track_bypasses_paperwork_by_spending_secrecy():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")

    ok, message, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)

    assert ok, message
    assert anomaly.state.scp_status == "active"
    assert anomaly.id in game.state.scp_anomalies[p1.id]
    assert scp.site(game.state, p1.id)["secrecy"] == 8
    assert any(event.type == EventType.SCP_FAST_TRACK for event in events)


def test_research_test_uses_assigned_personnel_and_gains_archive():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    junior = _hand_card(game, p1, "Junior Researcher")
    intern = _hand_card(game, p1, "Sleep-Deprived Intern")

    assert scp.open_dossier(game, p1.id, anomaly.id)[0]
    assert scp.open_dossier(game, p1.id, junior.id)[0]
    assert scp.open_dossier(game, p1.id, intern.id)[0]

    ok, message, events = scp.run_test(game, p1.id, anomaly.id, [junior.id, intern.id])

    assert ok, message
    # Moth in the Camera now wires a research_bounty on-test hook (+1 archive on top
    # of the engine's base +1), so a successful test yields 2 archives.
    assert scp.site(game.state, p1.id)["archives"] == 2
    assert junior.state.scp_exhausted is True
    # Sleep-Deprived Intern has a scp_on_assign quirk: on the FIRST assignment
    # per turn the intern is NOT marked exhausted (the engine exhausts them
    # via _staff_total, and the on-assign hook toggles the flag back). The
    # quirk is wired by src/cards/scp/mechanics/personnel_quirks.py.
    assert intern.state.scp_exhausted is False
    assert any(event.type == EventType.SCP_TEST_RUN and event.payload["success"] for event in events)


def test_containment_moves_anomaly_out_of_breach_pool():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Paperclip Colony")
    specialist = _hand_card(game, p1, "Containment Specialist")

    assert scp.open_dossier(game, p1.id, anomaly.id)[0]
    assert scp.open_dossier(game, p1.id, specialist.id, fast_track=True)[0]

    ok, message, events = scp.contain_anomaly(game, p1.id, anomaly.id, [specialist.id])

    assert ok, message
    assert anomaly.state.scp_status == "contained"
    assert anomaly.id not in game.state.scp_anomalies[p1.id]
    assert anomaly.id in game.state.scp_contained[p1.id]
    assert scp.site(game.state, p1.id)["archives"] == 2
    assert any(event.type == EventType.SCP_CONTAINED for event in events)


def test_suppression_reduces_next_breach_tick_only():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    janitor = _hand_card(game, p1, "Janitor Who Knows Too Much")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, janitor.id, fast_track=True)[0]
    assert scp.suppress_anomaly(game, p1.id, anomaly.id, [janitor.id])[0]

    scp.breach_tick(game, p1.id)
    assert scp.site(game.state, p1.id)["breach"] == 0

    scp.breach_tick(game, p1.id)
    assert scp.site(game.state, p1.id)["breach"] == 2


def test_protect_mandate_turns_full_suppression_into_archive():
    game, p1, _p2 = _setup()
    mandate = _hand_card(game, p1, "Protect Mandate")
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    janitor = _hand_card(game, p1, "Janitor Who Knows Too Much")

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, janitor.id, fast_track=True)[0]

    ok, message, events = scp.suppress_anomaly(game, p1.id, anomaly.id, [janitor.id])

    assert ok, message
    assert anomaly.state.scp_status == "contained"
    assert anomaly.id not in game.state.scp_anomalies[p1.id]
    assert anomaly.id in game.state.scp_contained[p1.id]
    assert scp.site(game.state, p1.id)["archives"] == 2
    assert any(event.type == EventType.SCP_CONTAINED for event in events)
    assert any(event.type == EventType.SCP_ARCHIVE_GAINED for event in events)
    scp.breach_tick(game, p1.id)
    assert scp.site(game.state, p1.id)["breach"] == 0


def test_archives_win_and_breach_loses():
    game, p1, p2 = _setup()

    scp.gain_archives(game, p1.id, 7)
    assert p2.has_lost

    game2, q1, _q2 = _setup()
    scp.site(game2.state, q1.id)["breach"] = scp.BREACH_LIMIT
    events = game2.check_state_based_actions()

    assert q1.has_lost
    assert any(event.type == EventType.SCP_SITE_LOST for event in events)


def test_procedure_resolves_and_moves_to_graveyard():
    game, p1, _p2 = _setup()
    scp.site(game.state, p1.id)["breach"] = 5
    proc = _hand_card(game, p1, "Emergency Lockdown")

    ok, message, events = scp.open_dossier(game, p1.id, proc.id, fast_track=True)

    assert ok, message
    assert scp.site(game.state, p1.id)["breach"] == 2
    assert proc.zone == ZoneType.GRAVEYARD
    assert any(event.type == EventType.SCP_ACTIVATE_DOSSIER for event in events)


def test_scp_turn_driver_ticks_paperwork_draws_and_applies_breach():
    game, p1, p2 = _setup()
    anomaly = _hand_card(game, p1, "Recursive Hallway")
    assert scp.open_dossier(game, p1.id, anomaly.id)[0]
    game.turn_manager.set_turn_order([p1.id, p2.id])

    events = asyncio.run(game.turn_manager.run_turn(p1.id))

    assert anomaly.state.scp_status == "active"
    assert scp.site(game.state, p1.id)["breach"] == 1
    assert any(event.type == EventType.SCP_PAPERWORK_TICK for event in events)
    assert any(event.type == EventType.SCP_BREACH_TICK for event in events)


def test_mandate_bonus_affects_assignment_checks():
    game, p1, _p2 = _setup()
    mandate = _hand_card(game, p1, "Contain Mandate")
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    junior = _hand_card(game, p1, "Junior Researcher")

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, anomaly.id)[0]
    assert scp.open_dossier(game, p1.id, junior.id)[0]

    assert scp.run_test(game, p1.id, anomaly.id, [junior.id])[0]
    # Moth in the Camera has a research_bounty on-test payoff (+1 extra archive).
    assert scp.site(game.state, p1.id)["archives"] == 2


def test_sealed_dossier_has_no_hazard_until_revealed():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")

    ok, message, events = scp.open_dossier(game, p1.id, anomaly.id, sealed=True)
    assert ok, message
    assert anomaly.state.scp_status == "sealed"
    assert anomaly.id not in game.state.scp_anomalies[p1.id]
    assert any(event.type == EventType.SCP_SEAL_DOSSIER for event in events)

    scp.breach_tick(game, p1.id)
    assert scp.site(game.state, p1.id)["breach"] == 0

    ok, message, events = scp.reveal_dossier(game, p1.id, anomaly.id)
    assert ok, message
    assert anomaly.state.scp_status == "active"
    assert anomaly.id in game.state.scp_anomalies[p1.id]
    assert any(event.type == EventType.SCP_REVEAL_DOSSIER for event in events)


def test_cross_site_audit_and_misfile_pressure_opponent_without_combat():
    game, p1, p2 = _setup()
    pending = _hand_card(game, p2, "Keter Annex")
    assert scp.open_dossier(game, p2.id, pending.id)[0]

    events = scp.force_audit(game, p1.id, p2.id, intensity=2)
    assert scp.site(game.state, p2.id)["secrecy"] == 7
    assert any(event.type == EventType.SCP_AUDIT for event in events)

    ok, message, _events = scp.misfile_dossier(game, p1.id, pending.id, amount=2)
    assert ok, message
    assert pending.state.scp_paperwork == 5


def test_site_zero_blackfile_protocol_misfiles_opposing_pending_dossier():
    game, p1, p2 = _setup()
    pending = _hand_card(game, p2, "SZB Press Conference Wing")
    protocol = _hand_card(game, p1, "SZB Press Conference Protocol")

    assert scp.open_dossier(game, p2.id, pending.id)[0]
    before = pending.state.scp_paperwork
    ok, message, events = scp.open_dossier(game, p1.id, protocol.id, fast_track=True)

    assert ok, message
    assert pending.state.scp_paperwork == before + 2
    assert protocol.zone == ZoneType.GRAVEYARD
    assert any(event.type == EventType.SCP_AUDIT for event in events)


def test_site_zero_quarantine_reveal_sets_mood_protocol_and_briefing():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "SZB White Pill Ward Anomaly")

    ok, message, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)

    assert ok, message
    assert anomaly.state.scp_status == "active"
    assert anomaly.state.scp_mood == "docile"
    assert "no_eye_contact" in anomaly.state.scp_protocols
    assert scp.site(game.state, p1.id)["briefing"] == 1
    assert any(event.type == EventType.SCP_MOOD_SHIFT for event in events)


def test_site_zero_anchor_binds_contained_anomaly_to_active_threat():
    game, p1, _p2 = _setup()
    source = _hand_card(game, p1, "SZB Paired Vault Anomaly")
    target = _hand_card(game, p1, "SZB Counter-God Anomaly")
    handler = _hand_card(game, p1, "SZB Silver Lattice Handler")

    assert scp.open_dossier(game, p1.id, source.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, target.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, handler.id, fast_track=True)[0]
    source.state.scp_status = "contained"
    if source.id in game.state.scp_anomalies[p1.id]:
        game.state.scp_anomalies[p1.id].remove(source.id)
    game.state.scp_contained[p1.id].append(source.id)

    protocol = _hand_card(game, p1, "SZB Silver Lattice Protocol")
    ok, message, events = scp.open_dossier(game, p1.id, protocol.id, fast_track=True)

    assert ok, message
    assert target.state.scp_bound_to == source.id
    assert any(event.type == EventType.SCP_CROSS_CONTAINMENT for event in events)


def test_site_zero_rotation_refreshes_staff_and_adds_assignment_slot():
    game, p1, _p2 = _setup()
    staff = _hand_card(game, p1, "SZB Night Desk Handler")
    protocol = _hand_card(game, p1, "SZB Night Desk Protocol")
    assert scp.open_dossier(game, p1.id, staff.id, fast_track=True)[0]
    staff.state.scp_exhausted = True
    scp.site(game.state, p1.id)["assignments_used"] = 1

    ok, message, events = scp.open_dossier(game, p1.id, protocol.id, fast_track=True)

    assert ok, message
    assert staff.state.scp_exhausted is False
    assert scp.site(game.state, p1.id)["assignment_slots"] == 2
    assert scp.site(game.state, p1.id)["assignments_used"] == 0
    assert any(event.type == EventType.SCP_INCIDENT_RESOLVED for event in events)


def test_ethics_debt_can_be_spent_but_still_has_a_loss_ceiling():
    game, p1, _p2 = _setup()
    scp.site(game.state, p1.id)["ethics_debt"] = 3

    ok, message, events = scp.spend_ethics(game, p1.id, 2, mode="buy_clearance")

    assert ok, message
    assert scp.site(game.state, p1.id)["clearance"] == 4
    assert scp.site(game.state, p1.id)["ethics_debt"] == 1
    assert any(event.type == EventType.SCP_ETHICS_SPENT for event in events)

    scp.site(game.state, p1.id)["ethics_debt"] = scp.ETHICS_LIMIT
    game.check_state_based_actions()
    assert p1.has_lost


def test_scp_native_alternate_redaction_win_uses_printed_threshold():
    game, p1, p2 = _setup()
    mandate = _hand_card(game, p1, "There Is No Antimemetics Division")
    scp.site(game.state, p1.id)["clearance"] = 3

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["archives"] = 3
    scp.site(game.state, p1.id)["secrecy"] = 8
    scp.site(game.state, p1.id)["breach"] = 9

    events = scp.check_scp_victory(game)

    assert not p2.has_lost
    assert not any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "total_redaction" for event in events)

    scp.site(game.state, p1.id)["secrecy"] = 12

    events = scp.check_scp_victory(game)

    assert p2.has_lost
    assert any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "total_redaction" for event in events)


def test_site_zero_redaction_mandate_requires_printed_breach_ceiling():
    card_def = SCP_CARDS["SZB Directive 1: White Pill Ward"]

    assert "breach 3 or less" in card_def.text
    assert card_def.scp_redaction_win == {"archives": 3, "secrecy": 12, "max_breach": 3}
    assert not scp.redaction_alt_win_met(card_def, {"archives": 3, "secrecy": 12, "breach": 9})
    assert scp.redaction_alt_win_met(card_def, {"archives": 3, "secrecy": 12, "breach": 3})


def test_site_zero_redaction_victory_honors_printed_breach_ceiling():
    game, p1, p2 = _setup()
    mandate = _hand_card(game, p1, "SZB Directive 1: White Pill Ward")
    scp.site(game.state, p1.id)["clearance"] = 3

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["archives"] = 3
    scp.site(game.state, p1.id)["secrecy"] = 12
    scp.site(game.state, p1.id)["breach"] = 9

    events = scp.check_scp_victory(game)
    assert not p2.has_lost
    assert not any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "total_redaction" for event in events)

    scp.site(game.state, p1.id)["breach"] = 3
    events = scp.check_scp_victory(game)

    assert p2.has_lost
    assert any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "total_redaction" for event in events)


def test_scp_native_alternate_veil_lockdown_win():
    game, p1, p2 = _setup()
    mandate = _hand_card(game, p1, "Protect Mandate")

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["archives"] = 3
    scp.site(game.state, p1.id)["secrecy"] = 7
    scp.site(game.state, p1.id)["breach"] = 0

    events = scp.check_scp_victory(game)

    assert p2.has_lost
    assert any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "veil_lockdown" for event in events)


def test_scp_native_alternate_ethics_audit_win():
    game, p1, p2 = _setup()
    mandate = _hand_card(game, p1, "ETH Mandate 1: Mercy Ledger")

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["archives"] = 4
    scp.site(game.state, p1.id)["secrecy"] = 8
    scp.site(game.state, p1.id)["ethics_debt"] = 3

    events = scp.check_scp_victory(game)
    assert not p2.has_lost
    assert not any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "ethics_audit" for event in events)

    scp.site(game.state, p1.id)["ethics_debt"] = 2

    events = scp.check_scp_victory(game)

    assert p2.has_lost
    assert any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "ethics_audit" for event in events)


def test_scp_native_alternate_public_panic_win():
    game, p1, p2 = _setup()
    mandate = _hand_card(game, p1, "GOI Mandate 1: Serpent Consulate")

    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["archives"] = 4
    scp.site(game.state, p2.id)["secrecy"] = 6

    events = scp.check_scp_victory(game)

    assert p2.has_lost
    assert any(event.type == EventType.PLAYER_LOSES and event.payload["reason"] == "public_panic" for event in events)


def test_failed_sealed_fast_track_does_not_spend_secrecy():
    game, p1, _p2 = _setup()
    facility = _hand_card(game, p1, "Site-19 Intake Wing")

    ok, message, events = scp.open_dossier(game, p1.id, facility.id, fast_track=True, sealed=True)

    assert not ok
    assert message == "Only anomalies can be sealed"
    assert events == []
    assert scp.site(game.state, p1.id)["secrecy"] == 10
    assert facility.zone == ZoneType.HAND


def test_audit_pressure_increases_against_dangerous_boards():
    game, p1, p2 = _setup()
    pending = _hand_card(game, p2, "Keter Annex")
    anomaly = _hand_card(game, p2, "Moth in the Camera")
    assert scp.open_dossier(game, p2.id, pending.id)[0]
    assert scp.open_dossier(game, p2.id, anomaly.id)[0]

    scp.force_audit(game, p1.id, p2.id, intensity=1)

    # intensity 1 + one pending dossier + one active anomaly = 3 exposure.
    assert scp.site(game.state, p2.id)["secrecy"] == 7


def test_mood_shift_rewrites_anomaly_difficulty():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    junior = _hand_card(game, p1, "Junior Researcher")
    # Use Field Agent (Agent subtype) — outside the Scientist aura on Junior so
    # the mood shift still flips the test outcome after personnel-synergy auras.
    agent = _hand_card(game, p1, "Field Agent")
    assert scp.open_dossier(game, p1.id, anomaly.id)[0]
    assert scp.open_dossier(game, p1.id, junior.id)[0]
    assert scp.open_dossier(game, p1.id, agent.id)[0]
    ok, message, _events = scp.shift_mood(game, p1.id, anomaly.id, "cryptic")
    assert not ok
    assert message == "Mood shift requires a briefing token"
    scp.site(game.state, p1.id)["briefing"] = 1
    assert scp.shift_mood(game, p1.id, anomaly.id, "cryptic")[0]

    ok, message, _events = scp.run_test(game, p1.id, anomaly.id, [junior.id, agent.id])

    assert ok, message
    assert scp.site(game.state, p1.id)["archives"] == 0
    assert scp.site(game.state, p1.id)["breach"] > 0


def test_cross_containment_uses_contained_anomaly_as_countermeasure():
    game, p1, _p2 = _setup()
    contained = _hand_card(game, p1, "Paperclip Colony")
    active = _hand_card(game, p1, "The Concrete Saint")
    specialist = _hand_card(game, p1, "Containment Specialist")
    assert scp.open_dossier(game, p1.id, contained.id)[0]
    assert scp.open_dossier(game, p1.id, active.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, specialist.id, fast_track=True)[0]
    assert scp.contain_anomaly(game, p1.id, contained.id, [specialist.id])[0]

    ok, message, events = scp.cross_contain(game, p1.id, contained.id, active.id)

    assert ok, message
    assert active.state.scp_bound_to == contained.id
    assert any(event.type == EventType.SCP_CROSS_CONTAINMENT for event in events)
    scp.breach_tick(game, p1.id)
    assert scp.site(game.state, p1.id)["breach"] == 1
    scp.breach_tick(game, p1.id)
    assert scp.site(game.state, p1.id)["breach"] == 2
    assert active.state.scp_bound_to == contained.id


def test_incident_tick_can_shift_mood_and_memory_hole_redacts_dossiers():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["archives"] = 1
    game.state.turn_number = 1

    events = scp.incident_tick(game, p1.id)
    assert any(event.type == EventType.SCP_INCIDENT for event in events)

    ok, message, events = scp.memory_hole(game, p1.id, anomaly.id)
    assert not ok
    assert message == "Active anomalies cannot be memory-holed safely"

    contained = _hand_card(game, p1, "Paperclip Colony")
    assert scp.open_dossier(game, p1.id, contained.id)[0]
    contained.state.scp_status = "contained"
    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    ok, message, events = scp.memory_hole(game, p1.id, contained.id)
    assert ok, message
    assert contained.zone == ZoneType.EXILE
    assert scp.site(game.state, p1.id)["secrecy"] == secrecy_before + 1
    assert any(event.type == EventType.SCP_MEMORY_HOLE for event in events)


def test_scp_ai_adapter_takes_noncombat_actions():
    from src.ai.scp_adapter import SCPAIAdapter

    game, p1, p2 = _setup()
    for name in ["Moth in the Camera", "Junior Researcher", "Sleep-Deprived Intern"]:
        _hand_card(game, p1, name)
    adapter = SCPAIAdapter()

    events = asyncio.run(adapter.take_turn(p1.id, game.state, game))

    assert events
    assert game.state.scp_anomalies[p1.id] or game.state.scp_personnel[p1.id]


def test_scp_ai_adapter_rejects_unknown_pilot_names():
    from src.ai.scp_adapter import SCPAIAdapter

    with pytest.raises(ValueError, match="Unknown SCP pilot"):
        SCPAIAdapter(pilot="typo_pilot")
    with pytest.raises(ValueError, match="Unknown SCP pilot"):
        SCPAIAdapter("typo_pilot")


def test_scp_tournament_programmatic_paths_reject_unknown_pilots():
    from scripts.play.scp_tournament import run_one_game, run_tournament

    with pytest.raises(ValueError, match="Unknown SCP pilot"):
        asyncio.run(run_one_game(
            "site_zero_redaction_lock",
            "keter_risk",
            seed=1,
            max_turns=1,
            difficulty="medium",
            p1_pilot="typo_pilot",
            p2_pilot="balanced",
        ))

    with pytest.raises(ValueError, match="Unknown SCP pilot"):
        asyncio.run(run_tournament(
            games_per_pair=1,
            max_turns=1,
            difficulty="medium",
            pilots=["balanced", "typo_pilot"],
            cross_pilots=False,
            seed=1,
            decks=["site_zero_redaction_lock", "keter_risk"],
        ))


def test_scp_deckbuilder_registry_and_server_mode_are_registered():
    from src.server.services.game_registry import get_card_pool, get_deck_rules, card_to_data
    from src.server.modes import get_server_mode_adapter

    pool = get_card_pool("scp")
    rules = get_deck_rules("scp")
    data = card_to_data("scp", "The Concrete Saint", pool["The Concrete Saint"])
    szb_data = card_to_data("scp", "SZB Press Conference Anomaly", pool["SZB Press Conference Anomaly"])

    assert "The Concrete Saint" in pool
    assert len(pool) >= 500
    assert rules.min_main == 25
    assert data["extras"]["scp_hazard"] == 2
    assert data["extras"]["scp_expansion_code"] == "CORE"
    assert data["extras"]["scp_art_prompt"]
    assert szb_data["extras"]["scp_keywords"] == ["Blackfile", "Overexpose"]
    assert get_server_mode_adapter("scp").__class__.__name__ == "SCPModeAdapter"


def test_scp_tournament_rejects_single_deck_filters():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.play.scp_tournament",
            "--games",
            "1",
            "--decks",
            "site_zero_redaction_lock",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "At least two SCP deck ids are required after filtering" in result.stderr


def test_scp_tournament_rejects_unknown_pilots():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.play.scp_tournament",
            "--games",
            "1",
            "--decks",
            "site_zero_redaction_lock,keter_risk",
            "--pilots",
            "typo_pilot",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "Unknown SCP pilot name(s): typo_pilot" in result.stderr


def test_sealed_dossier_serialization_hides_identity_and_stats():
    from src.server.session import GameSession

    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    assert scp.open_dossier(game, p1.id, anomaly.id, sealed=True)[0]
    session = GameSession(id="scp-test", game=game, mode="human_vs_human")

    data = session._serialize_permanent(anomaly)

    assert data.name == "Sealed Dossier"
    assert data.text.startswith("Sealed anomaly")
    assert data.scp_hazard == 0
    assert data.scp_containment == 0
    assert data.scp_status == "sealed"
    assert data.scp_public_tags == ["Statue"]


def test_memory_hole_rejects_unopened_cards():
    game, p1, _p2 = _setup()
    card = _hand_card(game, p1, "Paperclip Colony")

    ok, message, _events = scp.memory_hole(game, p1.id, card.id)

    assert not ok
    assert message == "Only opened dossiers can be memory-holed"
    assert card.zone == ZoneType.HAND


def test_memory_hole_triggers_redaction_alt_win():
    game, p1, p2 = _setup()

    # Active redaction mandate (3 archives + 12 secrecy alt-win).
    mandate = _hand_card(game, p1, "There Is No Antimemetics Division")
    scp.site(game.state, p1.id)["clearance"] = 3
    assert scp.open_dossier(game, p1.id, mandate.id, fast_track=True)[0]

    # Pending dossier that can be memory-holed.
    dossier = _hand_card(game, p1, "Paperclip Colony")
    assert scp.open_dossier(game, p1.id, dossier.id, fast_track=True)[0]
    dossier.state.scp_status = "pending"

    # One memory_hole will take us from (4, 11) to (3, 12) -> redaction win.
    scp.site(game.state, p1.id)["archives"] = 4
    scp.site(game.state, p1.id)["secrecy"] = 11
    assert not p2.has_lost

    ok, message, events = scp.memory_hole(game, p1.id, dossier.id)

    assert ok, message
    assert scp.site(game.state, p1.id)["archives"] == 3
    assert scp.site(game.state, p1.id)["secrecy"] == 12
    assert p2.has_lost
    assert game.is_game_over()
    assert any(
        event.type == EventType.PLAYER_LOSES
        and event.payload.get("reason") == "total_redaction"
        and event.payload.get("winner") == p1.id
        for event in events
    )


def test_assignment_slots_limit_actions_until_reset():
    game, p1, _p2 = _setup()
    anomaly1 = _hand_card(game, p1, "Moth in the Camera")
    anomaly2 = _hand_card(game, p1, "Rain Inside the Elevator")
    anomaly3 = _hand_card(game, p1, "Paperclip Colony")
    staff = [
        _hand_card(game, p1, "Junior Researcher"),
        _hand_card(game, p1, "Sleep-Deprived Intern"),
        _hand_card(game, p1, "D-Class Volunteer"),
    ]
    for obj in [anomaly1, anomaly2, anomaly3, *staff]:
        assert scp.open_dossier(game, p1.id, obj.id, fast_track=True)[0]

    assert scp.run_test(game, p1.id, anomaly1.id, [staff[0].id])[0]
    assert scp.run_test(game, p1.id, anomaly2.id, [staff[1].id])[0]
    ok, message, _events = scp.run_test(game, p1.id, anomaly3.id, [staff[2].id])
    assert not ok
    assert message == "No assignment slots remaining"

    scp.reset_assignment_slots(game.state, p1.id)
    ok, _message, _events = scp.run_test(game, p1.id, anomaly3.id, [staff[2].id])
    assert ok


def test_visible_protocol_and_binding_fields_serialize():
    from src.server.session import GameSession

    game, p1, _p2 = _setup()
    contained = _hand_card(game, p1, "Paperclip Colony")
    active = _hand_card(game, p1, "The Concrete Saint")
    specialist = _hand_card(game, p1, "Containment Specialist")
    assert scp.open_dossier(game, p1.id, contained.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, active.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, specialist.id, fast_track=True)[0]
    assert scp.contain_anomaly(game, p1.id, contained.id, [specialist.id])[0]
    assert scp.apply_protocol(game, p1.id, active.id, "mirror_box")[0]
    assert scp.cross_contain(game, p1.id, contained.id, active.id)[0]
    session = GameSession(id="scp-test", game=game, mode="human_vs_human")

    data = session._serialize_permanent(active)

    assert data.scp_bound_to == contained.id
    assert data.scp_protocols == ["mirror_box"]


def test_protocols_can_help_or_contradict_containment():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    specialist = _hand_card(game, p1, "Containment Specialist")
    helper = _hand_card(game, p1, "D-Class Volunteer")
    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, specialist.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, helper.id)[0]

    assert scp.apply_protocol(game, p1.id, anomaly.id, "mirror_box")[0]
    ok, message, _events = scp.contain_anomaly(game, p1.id, anomaly.id, [specialist.id, helper.id])
    assert ok, message
    assert anomaly.state.scp_status == "contained"

    anomaly2 = _hand_card(game, p1, "Door That Opens Sideways")
    assert scp.open_dossier(game, p1.id, anomaly2.id, fast_track=True)[0]
    assert scp.apply_protocol(game, p1.id, anomaly2.id, "no_eye_contact")[0]
    assert scp.apply_protocol(game, p1.id, anomaly2.id, "feed_it_lies")[0]
    assert scp.site(game.state, p1.id)["ethics_debt"] == 1


def test_goi_raid_and_incident_resolution_create_external_pressure():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    assert scp.open_dossier(game, p1.id, anomaly.id)[0]

    events = scp.goi_raid(game, p1.id, faction="Serpent's Hand")

    assert anomaly.state.scp_mood == "agitated"
    assert scp.site(game.state, p1.id)["breach"] == 1
    assert any(event.type == EventType.SCP_GOI_RAID for event in events)

    scp.incident_tick(game, p1.id)
    assert game.state.scp_incidents[p1.id]
    ok, message, events = scp.resolve_incident(game, p1.id, 0)

    assert ok, message
    assert scp.site(game.state, p1.id)["briefing"] == 1
    assert any(event.type == EventType.SCP_INCIDENT_RESOLVED for event in events)


def test_goi_raid_tip_off_card_makes_external_pressure_live():
    game, p1, p2 = _setup()
    target = _hand_card(game, p2, "Moth in the Camera")
    tip = _hand_card(game, p1, "GOI Raid Tip-Off")
    assert scp.open_dossier(game, p2.id, target.id)[0]

    ok, message, events = scp.open_dossier(game, p1.id, tip.id, fast_track=True)

    assert ok, message
    assert tip.zone == ZoneType.GRAVEYARD
    assert target.state.scp_mood == "agitated"
    assert scp.site(game.state, p2.id)["breach"] == 1
    assert any(event.type == EventType.SCP_GOI_RAID for event in events)


def test_paperwork_bonfire_only_fast_tracks_one_dossier():
    game, p1, _p2 = _setup()
    first = _hand_card(game, p1, "Borrowed Moon")
    second = _hand_card(game, p1, "Antimemetic Orchard")
    bonfire = _hand_card(game, p1, "Paperwork Bonfire")
    assert scp.open_dossier(game, p1.id, first.id)[0]
    assert scp.open_dossier(game, p1.id, second.id)[0]
    assert first.state.scp_status == "pending"
    assert second.state.scp_status == "pending"

    assert scp.open_dossier(game, p1.id, bonfire.id)[0]

    statuses = {first.state.scp_status, second.state.scp_status}
    assert statuses == {"active", "pending"}


def test_resolving_incidents_has_site_effects_beyond_briefing():
    game, p1, _p2 = _setup()
    game.state.scp_incidents[p1.id].append({"name": "paperwork_storm", "turn": 1, "breach": 3})
    scp.site(game.state, p1.id)["secrecy"] = 5

    ok, message, _events = scp.resolve_incident(game, p1.id, 0)

    assert ok, message
    assert scp.site(game.state, p1.id)["briefing"] == 1
    assert scp.site(game.state, p1.id)["secrecy"] == 6


def test_scp_end_turn_action_returns_without_waiting_for_processing_event():
    from src.server.models import ActionType, PlayerActionRequest
    from src.server.modes.scp import SCPModeAdapter
    from src.server.session import GameSession

    game, p1, _p2 = _setup()
    game.turn_manager.turn_state.active_player_id = p1.id
    session = GameSession(id="scp-end-turn-test", game=game, mode="human_vs_human")
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        session._pending_action_future = loop.create_future()
        session._pending_player_id = p1.id
        session._action_processed_event = asyncio.Event()
        request = PlayerActionRequest(action_type=ActionType.SCP_END_TURN, player_id=p1.id)

        started = time.monotonic()
        ok, message = loop.run_until_complete(SCPModeAdapter().handle_action(session, request))
        elapsed = time.monotonic() - started

        assert ok, message
        assert elapsed < 0.5
        assert session._pending_action_future is None
        assert session._pending_player_id is None
        assert session._action_processed_event is None
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ---------------------------------------------------------------------------
# Helper-contract tests for the post-construction mechanic plumbing.
# These lock in the engine API the parallel mechanic agents will rely on.
# ---------------------------------------------------------------------------


def test_public_reveal_helper_drops_secrecy_and_emits_audit():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    # Patch the card_def's reveal hook in place — mechanic modules do this too.
    anomaly.card_def.scp_on_reveal = scp._public_reveal(2)

    ok, _msg, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    assert ok
    assert scp.site(game.state, p1.id)["secrecy"] == 10 - 2  # fast_track on red_tape=0 anomaly is free
    audit_events = [e for e in events if e.type == EventType.SCP_AUDIT and e.payload.get("reason") == "public_reveal"]
    assert audit_events, "expected SCP_AUDIT reason=public_reveal"


def test_seeded_mood_helper_sets_mood_and_protocol():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    anomaly.card_def.scp_on_reveal = scp._seeded_mood("cryptic", protocol="ritual_diagram", briefing=1)

    ok, _msg, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    assert ok
    assert anomaly.state.scp_mood == "cryptic"
    assert "ritual_diagram" in anomaly.state.scp_protocols
    assert scp.site(game.state, p1.id)["briefing"] == 1
    assert any(e.type == EventType.SCP_MOOD_SHIFT for e in events)


def test_tax_own_pending_taxes_only_callers_pending_dossiers():
    game, p1, _p2 = _setup()
    # One pending personnel for p1 with red_tape so it stays pending.
    spec = _hand_card(game, p1, "Containment Specialist")  # red_tape=1
    scp.open_dossier(game, p1.id, spec.id)
    assert spec.state.scp_status == "pending"
    paperwork_before = spec.state.scp_paperwork

    events = scp.tax_own_pending(game.state, p1.id, 2, source=spec.id)
    assert spec.state.scp_paperwork == paperwork_before + 2
    assert events and all(e.type == EventType.SCP_PAPERWORK_TICK for e in events)


def test_contained_bonus_extends_active_bonus_for_tests():
    game, p1, _p2 = _setup()
    # Contain something cheap, then tag its card_def with a contained_bonus.
    anomaly = _hand_card(game, p1, "Paperclip Colony")
    specialist = _hand_card(game, p1, "Containment Specialist")
    scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    scp.open_dossier(game, p1.id, specialist.id, fast_track=True)
    assert scp.contain_anomaly(game, p1.id, anomaly.id, [specialist.id])[0]
    anomaly.card_def.scp_contained_bonus = {"research": 1}

    # Now pretend a second test runs on a different anomaly — the contained
    # bonus should add into _active_bonus.
    assert scp._active_bonus(game.state, p1.id, "research") == 1


def test_personnel_aura_buffs_same_subtype_friendly_staff():
    game, p1, _p2 = _setup()
    # One Memetics personnel (aura source) plus one Scientist (not Memetics).
    analyst = _hand_card(game, p1, "Memetics Analyst")  # subtypes {Scientist, Memetics}
    junior = _hand_card(game, p1, "Junior Researcher")  # subtypes {Scientist}
    scp.open_dossier(game, p1.id, analyst.id, fast_track=True)
    scp.open_dossier(game, p1.id, junior.id, fast_track=True)
    # Wire a memetics-research aura on the Memetics Analyst's card_def.
    # Stash and clear personnel-synergy auras so this helper-contract test
    # observes only the aura under test. Card_defs are shared across copies,
    # so we restore them on the way out.
    saved_analyst = analyst.card_def.scp_aura
    saved_junior = junior.card_def.scp_aura
    analyst.card_def.scp_aura = {"subtype:Memetics": {"research": 1}}
    junior.card_def.scp_aura = {}

    total, used = scp._staff_total(game.state, p1.id, [analyst.id, junior.id], "research")
    # analyst: skills.research=2 + aura(+1, since it has Memetics) = 3
    # junior:  skills.research=1 + aura(0, no Memetics)         = 1
    assert total == 3 + 1
    assert set(used) == {analyst.id, junior.id}
    # Restore so we don't pollute the shared card_def for other tests.
    analyst.card_def.scp_aura = saved_analyst
    junior.card_def.scp_aura = saved_junior


def test_personnel_aura_any_selector_applies_to_all_friendly_staff():
    game, p1, _p2 = _setup()
    analyst = _hand_card(game, p1, "Memetics Analyst")
    junior = _hand_card(game, p1, "Junior Researcher")
    scp.open_dossier(game, p1.id, analyst.id, fast_track=True)
    scp.open_dossier(game, p1.id, junior.id, fast_track=True)
    saved_analyst = analyst.card_def.scp_aura
    saved_junior = junior.card_def.scp_aura
    analyst.card_def.scp_aura = {"any": {"research": 1}}
    junior.card_def.scp_aura = {}

    total, _used = scp._staff_total(game.state, p1.id, [analyst.id, junior.id], "research")
    # analyst: skills 2 + 1 = 3 ; junior: skills 1 + 1 = 2
    assert total == 3 + 2
    analyst.card_def.scp_aura = saved_analyst
    junior.card_def.scp_aura = saved_junior


def test_on_test_fail_hook_fires_on_failure():
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")  # curiosity 2
    scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    fired = []
    anomaly.card_def.scp_on_test_fail = lambda obj, state: (fired.append(obj.id) or [])

    # Run a test with NO staff so it fails (total 0 < curiosity 2).
    ok, _msg, _events = scp.run_test(game, p1.id, anomaly.id, [])
    assert ok
    assert fired == [anomaly.id]


def test_mechanics_package_imports_cleanly():
    from src.cards.scp import mechanics
    assert callable(mechanics.apply_all_mechanics)
    # No-op default doesn't error.
    mechanics.apply_all_mechanics({})


def test_expansion_acw_anomaly_arrives_cryptic_and_sealed_by_default():
    """W5 generator default: every ACW templated anomaly is cryptic + sealed.

    Picks any ACW expansion anomaly. After open, mood is ``cryptic`` and the
    ``mirror_box`` protocol is on the anomaly. The engine now honors
    ``scp_seal_default = True``: the reveal hook fires (mood + protocol seed)
    but the final ``scp_status`` ends ``"sealed"`` rather than ``"active"``.
    """
    acw_anomaly_names = [
        name
        for name, card in SCP_CARDS.items()
        if getattr(card, "scp_expansion_code", None) == "ACW"
        and CardType.SCP_ANOMALY in card.characteristics.types
        and "Anomaly" in name
    ]
    assert acw_anomaly_names, "Expected ACW templated anomalies in expansion pool"
    sample_name = acw_anomaly_names[0]
    sample = SCP_CARDS[sample_name]
    # Generator-baked seal hint.
    assert getattr(sample, "scp_seal_default", False) is True
    # Reveal hook fires on activation, then engine reseals.
    game, p1, _p2 = _setup()
    obj = _hand_card(game, p1, sample_name)
    ok, _msg, _events = scp.open_dossier(game, p1.id, obj.id, fast_track=True)
    assert ok
    assert obj.state.scp_status == "sealed"
    assert obj.state.scp_mood == "cryptic"
    assert "mirror_box" in obj.state.scp_protocols
    # And the anomaly is NOT in the active-anomaly registry.
    assert obj.id not in game.state.scp_anomalies.get(p1.id, [])


def test_expansion_goi_anomaly_reveal_costs_secrecy_or_breach():
    """W5 generator default: GOI anomalies reveal with public_reveal (even index)
    or hostile_reveal (odd index). Either way, the controller pays.
    """
    game, p1, _p2 = _setup()
    goi_anomaly_names = [
        name
        for name, card in SCP_CARDS.items()
        if getattr(card, "scp_expansion_code", None) == "GOI"
        and CardType.SCP_ANOMALY in card.characteristics.types
        and "Anomaly" in name
    ]
    assert goi_anomaly_names
    # After breach-economy tuning, GOI anomalies cost secrecy or breach
    # depending on motif index (1-in-3 are breach hits). Verify both
    # variants exist and at least one cost lands on either axis.
    name = "GOI Serpent Consulate Anomaly"
    assert name in SCP_CARDS
    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    breach_before = scp.site(game.state, p1.id)["breach"]
    obj = _hand_card(game, p1, name)
    ok, _msg, _events = scp.open_dossier(game, p1.id, obj.id, fast_track=True)
    assert ok
    secrecy_after = scp.site(game.state, p1.id)["secrecy"]
    breach_after = scp.site(game.state, p1.id)["breach"]
    # Either the secrecy or the breach axis moved (not both, but one).
    assert (
        secrecy_after == secrecy_before - 1 or breach_after == breach_before + 1
    ), f"GOI anomaly should hit secrecy or breach; got secrecy {secrecy_before}->{secrecy_after}, breach {breach_before}->{breach_after}"


def test_expansion_eth_specialist_carries_secondary_task_aura():
    """W5 generator default: ETH Specialist's aura buffs the secondary task
    (``contain`` for the Ethics archetype) on friendly Ethics-subtype staff.
    """
    eth_spec_names = [
        name
        for name, card in SCP_CARDS.items()
        if getattr(card, "scp_expansion_code", None) == "ETH"
        and CardType.SCP_PERSONNEL in card.characteristics.types
        and "Specialist" in name
    ]
    assert eth_spec_names
    sample = SCP_CARDS[eth_spec_names[0]]
    # The Ethics archetype's secondary task is "contain".
    assert sample.scp_aura == {"subtype:Ethics": {"contain": 1}}
    # And the aura actually fires in _staff_total against an Ethics-tagged
    # friendly. We use a second ETH specialist as the target so we know it
    # carries the Ethics subtype.
    game, p1, _p2 = _setup()
    source = _hand_card(game, p1, sample.name)
    target_name = next(n for n in eth_spec_names if n != sample.name)
    target = _hand_card(game, p1, target_name)
    scp.open_dossier(game, p1.id, source.id, fast_track=True)
    scp.open_dossier(game, p1.id, target.id, fast_track=True)
    target_skills = SCP_CARDS[target_name].scp_skills
    # Both staff have subtype Ethics and both carry the aura, so both auras
    # apply to both staff: each staff's contribution is
    # base_contain + (n_auras x +1). With two ETH specialists this is
    # (skills.contain + 2) per staff. The total is the sum across both.
    per_staff = sample.scp_skills.get("contain", 0) + 2
    expected_contain = per_staff + (target_skills.get("contain", 0) + 2)
    total, _used = scp._staff_total(
        game.state, p1.id, [source.id, target.id], "contain"
    )
    assert total == expected_contain


# ---------------------------------------------------------------------------
# W2 — Contained-state auras
# ---------------------------------------------------------------------------

def _open_active(game, player, name):
    """Open a dossier and bypass any paperwork via fast_track for test setup."""
    obj = _hand_card(game, player, name)
    scp.open_dossier(game, player.id, obj.id, fast_track=True)
    return obj


def _contain_anomaly_for_test(game, player, name):
    """Helper: place an anomaly into the contained zone via a fresh staff body.

    Uses an MTF Doorbreaker so the contain check is reliably big enough; the
    anomaly's intrinsic containment difficulty may exceed Containment
    Specialist's contribution, but Doorbreaker + bonuses should clear most
    CORE anomalies. For anomalies whose containment is too high, we set
    scp_status directly — these tests are about the bonus, not the check.
    """
    anomaly = _hand_card(game, player, name)
    scp.open_dossier(game, player.id, anomaly.id, fast_track=True)
    # Move into contained zone directly. This mirrors what the engine does
    # on a successful contain_anomaly() call but skips the staff check so the
    # test stays focused on the contained-bonus aura.
    anomaly.state.scp_status = "contained"
    if anomaly.id in game.state.scp_anomalies[player.id]:
        game.state.scp_anomalies[player.id].remove(anomaly.id)
    if anomaly.id not in game.state.scp_contained[player.id]:
        game.state.scp_contained[player.id].append(anomaly.id)
    return anomaly


def test_w2_contained_auras_wired_on_assigned_cards():
    """Every name in CONTAINED_BONUSES exists in SCP_CARDS and has the attr set."""
    from src.cards.scp.mechanics.contained_auras import CONTAINED_BONUSES
    for name, expected in CONTAINED_BONUSES.items():
        assert name in SCP_CARDS, f"Missing card from pool: {name}"
        card = SCP_CARDS[name]
        actual = getattr(card, "scp_contained_bonus", None)
        assert actual == expected, f"{name}: expected {expected}, got {actual}"
        # Text edit should mention the aura.
        assert "While contained," in (card.text or ""), (
            f"{name} text was not updated with contained-state mention: {card.text!r}"
        )


def test_w2_oracle_mold_research_aura_applies_while_contained():
    """Oracle Mold gives research +1 to the Site's totals while contained."""
    game, p1, _p2 = _setup()
    # Baseline: empty site, no bonus.
    assert scp._active_bonus(game.state, p1.id, "research") == 0
    _contain_anomaly_for_test(game, p1, "Oracle Mold")
    # The aura is research +1.
    assert scp._active_bonus(game.state, p1.id, "research") == 1
    # Other tasks unaffected.
    assert scp._active_bonus(game.state, p1.id, "contain") == 0
    assert scp._active_bonus(game.state, p1.id, "suppress") == 0


def test_w2_unlicensed_heaven_multi_task_aura_stacks_across_tasks():
    """Unlicensed Heaven contributes research +2 AND contain +1 at the same time."""
    game, p1, _p2 = _setup()
    _contain_anomaly_for_test(game, p1, "Unlicensed Heaven")
    assert scp._active_bonus(game.state, p1.id, "research") == 2
    assert scp._active_bonus(game.state, p1.id, "contain") == 1
    assert scp._active_bonus(game.state, p1.id, "suppress") == 0


def test_w2_contained_aura_only_applies_in_contained_zone():
    """An Oracle Mold that is merely active (not contained) gives no bonus."""
    game, p1, _p2 = _setup()
    # Open Oracle Mold as ACTIVE (default open path), do not contain it.
    _open_active(game, p1, "Oracle Mold")
    # Still active, still in the breach pool — contained-bonus must not fire.
    assert scp._active_bonus(game.state, p1.id, "research") == 0


def test_w2_contained_aura_feeds_staff_total_for_research():
    """The contained aura adds into ``_staff_total``, which is what run_test/contain/suppress consume.

    We assert on ``_staff_total`` directly rather than the full ``run_test``
    pipeline because the Moth-in-the-Camera and Paperclip-Colony card_defs are
    mutated by other tests in this file (they patch on_reveal / on_test_fail
    / contained_bonus on shared card_def instances). The aura calculation
    itself is what matters here.
    """
    game, p1, _p2 = _setup()
    # Baseline: Junior Researcher (research 1) + W4 self-aura from his own
    # "subtype:Scientist" aura = 2. Capture the baseline rather than hard-code
    # it so this test stays robust if other auras land later.
    junior = _open_active(game, p1, "Junior Researcher")
    baseline_total, _ = scp._staff_total(game.state, p1.id, [junior.id], "research")
    junior.state.scp_exhausted = False

    # Now contain Oracle Mold; the +1 research aura should lift the total.
    _contain_anomaly_for_test(game, p1, "Oracle Mold")
    boosted_total, _ = scp._staff_total(game.state, p1.id, [junior.id], "research")
    assert boosted_total == baseline_total + 1, (
        f"Oracle Mold contained-aura should add +1 to research staff total "
        f"(baseline {baseline_total}, boosted {boosted_total})."
    )


# ---------------------------------------------------------------------------
# W3 — Test Dividends: on-test payoffs & failure penalties.
# ---------------------------------------------------------------------------


def test_test_dividends_success_payoff_changes_site_state():
    """Successful research on a wired anomaly applies the success payoff."""
    game, p1, _p2 = _setup()
    # Singing Vending Machine: research_bounty → +1 extra archive on success.
    # curiosity=4, but we'll stack staff so the test passes.
    anomaly = _hand_card(game, p1, "Singing Vending Machine")
    o5 = _hand_card(game, p1, "O5 Auditor")  # research:3, clearance handled by site setup
    scp.site(game.state, p1.id)["clearance"] = 3  # ensure O5 can be played
    intern = _hand_card(game, p1, "Sleep-Deprived Intern")  # research:1
    junior = _hand_card(game, p1, "Junior Researcher")  # research:1

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, o5.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, intern.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, junior.id, fast_track=True)[0]

    # Verify the on-test hook is wired by the mechanic applier.
    assert callable(getattr(anomaly.card_def, "scp_on_test", None))

    archives_before = scp.site(game.state, p1.id)["archives"]
    ok, _msg, events = scp.run_test(game, p1.id, anomaly.id, [o5.id, intern.id, junior.id])
    assert ok
    archives_after = scp.site(game.state, p1.id)["archives"]
    # Engine base +1 archive + research_bounty +1 = +2 total.
    assert archives_after - archives_before == 2
    assert any(
        event.type == EventType.SCP_ARCHIVE_GAINED
        and event.payload.get("reason") == "research_bounty"
        for event in events
    )


def _strip_reveal_state(anomaly, game=None):
    """Clear mood + protocols on an anomaly so test-time math is base curiosity/hazard.

    W1's on_reveal hooks seed mood and protocols that shift curiosity/hazard
    via MOOD_MODS / PROTOCOL_MODS. These W3 tests assert raw-stat math; reset
    after reveal so the assertions still reflect the on_test mechanic itself.

    If ``game`` is provided and the anomaly opened into a sealed state (because
    its card_def has ``scp_seal_default = True``), this helper also forces the
    anomaly back into the active registry so tests of OTHER mechanics
    (research, contain, etc.) can keep operating on it.
    """
    anomaly.state.scp_mood = None
    anomaly.state.scp_protocols = []
    if game is not None and anomaly.state.scp_status == "sealed":
        anomaly.state.scp_status = "active"
        anomalies = game.state.scp_anomalies.setdefault(anomaly.controller, [])
        if anomaly.id not in anomalies:
            anomalies.append(anomaly.id)


def test_test_dividends_failure_penalty_fires():
    """Failed research on an anomaly with a wired fail-hook applies the penalty."""
    game, p1, _p2 = _setup()
    # Hostile Nursery Rhyme: curiosity=5, fail-hook = breach_punish(+1).
    anomaly = _hand_card(game, p1, "Hostile Nursery Rhyme")
    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    _strip_reveal_state(anomaly)

    # Verify the fail-hook is wired by the mechanic applier.
    assert callable(getattr(anomaly.card_def, "scp_on_test_fail", None))

    breach_before = scp.site(game.state, p1.id)["breach"]
    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    # Run a test with NO staff -> total 0 < curiosity 5 -> failure.
    ok, _msg, events = scp.run_test(game, p1.id, anomaly.id, [])
    assert ok
    breach_after = scp.site(game.state, p1.id)["breach"]
    secrecy_after = scp.site(game.state, p1.id)["secrecy"]
    # Engine baseline failure: secrecy -1, breach += max(1, hazard - total).
    # Hazard=2, total=0 -> engine breach += 2. Our fail-hook adds +1 more.
    assert secrecy_after == secrecy_before - 1
    assert breach_after == breach_before + 2 + 1  # engine leak + fail-hook punish
    assert any(
        event.type == EventType.SCP_BREACH_TICK
        and event.payload.get("reason") == "research_failure_breach"
        for event in events
    )


def test_test_dividends_cognitive_load_exhausts_extra_researcher():
    """Cognitive-load cards (Mirror, Patient Zero, Red Room) drain one more researcher on success."""
    game, p1, _p2 = _setup()
    # The Mirror That Interviews You: curiosity=4, cognitive_load + research_bounty.
    anomaly = _hand_card(game, p1, "The Mirror That Interviews You")
    # Two researchers used for the test (must beat curiosity 4)...
    o5 = _hand_card(game, p1, "O5 Auditor")  # research:3
    scp.site(game.state, p1.id)["clearance"] = 3
    intern = _hand_card(game, p1, "Sleep-Deprived Intern")  # research:1
    # ...plus a THIRD bystander who is not assigned to the test but is on the
    # battlefield, active, and unexhausted. Cognitive load should drain them.
    bystander = _hand_card(game, p1, "Junior Researcher")  # research:1

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    # Mirror has scp_seal_default=True; helper passes game to also unseal.
    _strip_reveal_state(anomaly, game)
    assert scp.open_dossier(game, p1.id, o5.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, intern.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, bystander.id, fast_track=True)[0]

    assert bystander.state.scp_exhausted is False

    ok, _msg, events = scp.run_test(game, p1.id, anomaly.id, [o5.id, intern.id])
    assert ok

    # The cognitive-load hook drains exactly ONE active researcher. With
    # the Sleep-Deprived Intern's first-assignment-free quirk, the intern
    # is un-exhausted after _staff_total and remains a candidate (lowest
    # research, tied with the bystander). Iteration order makes the intern
    # the cognitive-load victim; the bystander stays unexhausted.
    assert o5.state.scp_exhausted is True
    assert intern.state.scp_exhausted is True  # re-exhausted by cognitive_load
    assert bystander.state.scp_exhausted is False
    assert any(
        event.type == EventType.SCP_ASSIGN_STAFF
        and event.payload.get("reason") == "cognitive_load"
        for event in events
    )


def test_test_dividends_cognitive_load_safe_when_no_bystander_available():
    """Cognitive-load hook degrades gracefully when no extra researcher exists."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Mirror That Interviews You")
    o5 = _hand_card(game, p1, "O5 Auditor")
    scp.site(game.state, p1.id)["clearance"] = 3
    intern = _hand_card(game, p1, "Sleep-Deprived Intern")
    # No third bystander on the battlefield this time.

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    # Mirror has scp_seal_default=True; helper passes game to also unseal.
    _strip_reveal_state(anomaly, game)
    assert scp.open_dossier(game, p1.id, o5.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, intern.id, fast_track=True)[0]

    archives_before = scp.site(game.state, p1.id)["archives"]
    ok, _msg, _events = scp.run_test(game, p1.id, anomaly.id, [o5.id, intern.id])
    assert ok
    # Both staff still get exhausted by the test, payoff (+2 archives) still fires.
    assert scp.site(game.state, p1.id)["archives"] - archives_before == 2


def test_test_dividends_applier_is_idempotent():
    """Running apply_test_dividends repeatedly is safe."""
    from src.cards.scp import SCP_CARDS
    from src.cards.scp.mechanics.test_dividends import apply_test_dividends

    moth = SCP_CARDS["Moth in the Camera"]
    original_text = moth.text
    original_hook = moth.scp_on_test
    assert callable(original_hook)

    apply_test_dividends(SCP_CARDS)
    apply_test_dividends(SCP_CARDS)

    # Text is unchanged, hook is still a callable. (The factory creates new
    # closures each call, so identity may change — only behavioural identity
    # matters, and that is covered by the other tests.)
    assert moth.text == original_text
    assert callable(moth.scp_on_test)


# ---------------------------------------------------------------------------
# W4 personnel-synergy aura tests (lord effects on CORE staff + heroes).
# ---------------------------------------------------------------------------


def test_personnel_synergy_memetics_analyst_buffs_another_memetics():
    """Memetics Analyst's aura should buff a teammate Memetics personnel's research."""
    game, p1, _p2 = _setup()
    # Two copies of Memetics Analyst so both are friendly Memetics personnel.
    analyst = _hand_card(game, p1, "Memetics Analyst")
    teammate = _hand_card(game, p1, "Memetics Analyst")
    assert scp.open_dossier(game, p1.id, analyst.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, teammate.id, fast_track=True)[0]

    # Aura on Memetics Analyst's card_def is wired by apply_personnel_synergy
    # — confirm it exists and yields +1 research for Memetics targets.
    assert SCP_CARDS["Memetics Analyst"].scp_aura.get("subtype:Memetics") == {"research": 1}

    total, used = scp._staff_total(game.state, p1.id, [analyst.id, teammate.id], "research")
    # Both analysts are aura sources AND both are aura targets. Each analyst
    # contributes its own aura, both selectors of which match its target's
    # subtypes (Memetics+Scientist). Per analyst the +1 fires twice (Memetics
    # +1 and Scientist +1) and there are TWO sources, so each analyst nets
    # base 2 + (1+1 from itself) + (1+1 from the teammate) = 6.
    assert total == 12
    assert set(used) == {analyst.id, teammate.id}


def test_personnel_synergy_o5_auditor_any_buffs_all_friendly():
    """O5 Auditor's "any" aura should buff every friendly personnel's research."""
    game, p1, _p2 = _setup()
    auditor = _hand_card(game, p1, "O5 Auditor")
    junior = _hand_card(game, p1, "Junior Researcher")
    # O5 Auditor has clearance 2, so we need 2 clearance to play it.
    scp.site(game.state, p1.id)["clearance"] = 3
    assert scp.open_dossier(game, p1.id, auditor.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, junior.id, fast_track=True)[0]

    assert SCP_CARDS["O5 Auditor"].scp_aura.get("any") == {"research": 1}

    total, used = scp._staff_total(game.state, p1.id, [auditor.id, junior.id], "research")
    # auditor (O5): research 3 + auditor "any" +1 = 4 (junior's Scientist aura
    #   does not apply — auditor is not a Scientist).
    # junior (Scientist): research 1 + auditor "any" +1 + junior self Scientist +1 = 3.
    assert total == 7
    assert set(used) == {auditor.id, junior.id}


def test_personnel_synergy_aura_does_not_buff_opponent_personnel():
    """The aura is friendly-only — opponent personnel must not receive a friendly's buff."""
    game, p1, p2 = _setup()
    # p1 has two Memetics Analysts — they'd compound to (2+2)+(2+2) = 8 in a
    # friendly call. p2 has one. We assert that p2's solo total is unaffected
    # by p1's two analysts.
    a1 = _hand_card(game, p1, "Memetics Analyst")
    a2 = _hand_card(game, p1, "Memetics Analyst")
    assert scp.open_dossier(game, p1.id, a1.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, a2.id, fast_track=True)[0]

    opp_analyst = _hand_card(game, p2, "Memetics Analyst")
    assert scp.open_dossier(game, p2.id, opp_analyst.id, fast_track=True)[0]

    # p2's total is computed from p2's own analyst's aura ONLY: research 2 +
    # self-Memetics +1 + self-Scientist +1 = 4. If p1's aura sources leaked
    # across to p2, the total would be 4 + 2 + 2 = 8. We assert 4.
    total_opp, used_opp = scp._staff_total(game.state, p2.id, [opp_analyst.id], "research")
    assert total_opp == 4
    assert used_opp == [opp_analyst.id]

    # And p1's analysts must NOT be buffed by p2's analyst either.
    total_friend, _used = scp._staff_total(game.state, p1.id, [a1.id, a2.id], "research")
    # Two p1 analysts, two aura sources (both p1). Each analyst gets:
    # base 2 + self-aura(+1 +1) + teammate-aura(+1 +1) = 6. Two of them = 12.
    assert total_friend == 12


def test_personnel_synergy_aura_source_buffs_itself_on_matching_subtype():
    """When the aura source's own subtypes match its selector, it counts itself."""
    game, p1, _p2 = _setup()
    # Memetics Analyst has subtypes {Scientist, Memetics}; its aura selectors
    # include subtype:Memetics, so it must self-buff +1 research.
    analyst = _hand_card(game, p1, "Memetics Analyst")
    assert scp.open_dossier(game, p1.id, analyst.id, fast_track=True)[0]

    total, used = scp._staff_total(game.state, p1.id, [analyst.id], "research")
    # base research 2 + memetics aura +1 + scientist aura +1 = 4
    assert total == 4
    assert used == [analyst.id]


def test_personnel_synergy_text_describes_aura_for_assigned_cards():
    """Card text should describe the lord effect, not just flavor."""
    # CORE pick.
    junior_text = SCP_CARDS["Junior Researcher"].text
    assert "Scientist" in junior_text and "research" in junior_text.lower()

    # CORE "any" pick.
    auditor_text = SCP_CARDS["O5 Auditor"].text
    assert "friendly" in auditor_text.lower() or "every" in auditor_text.lower()

    # Expansion hero pick — should mention the archetype subtype.
    director_text = SCP_CARDS["ACW Hero - Director Ana Vale"].text
    assert "Antimemetic" in director_text


def test_personnel_synergy_expansion_hero_auras_match_archetype_subtype():
    """All 5 expansions: each hero's aura keys on the expansion's signature subtype."""
    expected = {
        "ACW": ("subtype:Antimemetic", {"research": 1}),
        "KBO": ("subtype:Keter", {"contain": 1}),
        "GOI": ("subtype:GOI", {"suppress": 1}),
        "ETH": ("subtype:Ethics", {"research": 1}),
        "OAR": ("subtype:Dream", {"research": 1}),
    }
    heroes_seen = 0
    for code, (selector, delta) in expected.items():
        for name, card in SCP_CARDS.items():
            if not name.startswith(f"{code} Hero - "):
                continue
            aura = getattr(card, "scp_aura", None) or {}
            assert aura.get(selector) == delta, (
                f"{name}: expected aura[{selector}]={delta}, got {aura}"
            )
            heroes_seen += 1
    assert heroes_seen >= 30  # 5 expansions x 6+ heroes


# ---------------------------------------------------------------------------
# Reveal-identity wiring (W1) — assert one CORE and one expansion card fire
# their reveal hooks end-to-end through open_dossier.
# ---------------------------------------------------------------------------


def test_reveal_identity_core_briefing_card_grants_token_on_reveal():
    """The Concrete Saint: on reveal, +1 briefing token (no breach/secrecy delta)."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")

    briefing_before = scp.site(game.state, p1.id)["briefing"]
    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    breach_before = scp.site(game.state, p1.id)["breach"]

    ok, message, _events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)

    assert ok, message
    assert anomaly.state.scp_status == "active"
    assert scp.site(game.state, p1.id)["briefing"] == briefing_before + 1
    # Reveal should be hazard- and secrecy-neutral (matters for baseline tests).
    assert scp.site(game.state, p1.id)["breach"] == breach_before
    # Fast-track costs red_tape=2 secrecy — that is the only secrecy delta.
    assert scp.site(game.state, p1.id)["secrecy"] == secrecy_before - 2


def test_reveal_identity_core_tax_card_only_taxes_other_pending():
    """Recursive Hallway: on reveal, tax other pending dossiers (no-op if none)."""
    game, p1, _p2 = _setup()
    # Pre-stage a pending personnel so the tax has a target.
    spec = _hand_card(game, p1, "Containment Specialist")  # red_tape=1
    assert scp.open_dossier(game, p1.id, spec.id)[0]
    assert spec.state.scp_status == "pending"
    paperwork_before = spec.state.scp_paperwork

    hallway = _hand_card(game, p1, "Recursive Hallway")
    ok, message, events = scp.open_dossier(game, p1.id, hallway.id, fast_track=True)

    assert ok, message
    assert hallway.state.scp_status == "active"
    # Specialist took +1 paperwork from the reveal-time tax.
    assert spec.state.scp_paperwork == paperwork_before + 1
    tax_events = [
        e for e in events
        if e.type == EventType.SCP_PAPERWORK_TICK
        and e.payload.get("reason") == "tax_own_pending"
    ]
    assert tax_events, "expected SCP_PAPERWORK_TICK reason=tax_own_pending"


def test_reveal_identity_kbo_anomaly_seeds_agitated_mood_and_breach():
    """KBO Ashen Giant Anomaly: on reveal, set mood agitated + breach +2."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "KBO Ashen Giant Anomaly")
    breach_before = scp.site(game.state, p1.id)["breach"]

    ok, message, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)

    assert ok, message
    assert anomaly.state.scp_status == "active"
    assert anomaly.state.scp_mood == "agitated"
    assert scp.site(game.state, p1.id)["breach"] == breach_before + 2
    mood_events = [e for e in events if e.type == EventType.SCP_MOOD_SHIFT]
    breach_events = [
        e for e in events
        if e.type == EventType.SCP_BREACH_TICK and e.payload.get("reason") == "reveal"
    ]
    assert mood_events, "expected SCP_MOOD_SHIFT from seeded mood"
    assert breach_events, "expected SCP_BREACH_TICK reason=reveal"


def test_reveal_identity_acw_anomaly_is_sealed_default_and_cryptic_on_reveal():
    """ACW Null Choir Anomaly: scp_seal_default + cryptic mood + mirror_box on reveal."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "ACW Null Choir Anomaly")

    # Card-def level: sealed default flagged for AI consumers.
    assert getattr(anomaly.card_def, "scp_seal_default", False) is True

    # Open sealed, then reveal — the reveal hook fires inside reveal_dossier.
    ok, _msg, _events = scp.open_dossier(game, p1.id, anomaly.id, sealed=True)
    assert ok
    assert anomaly.state.scp_status == "sealed"
    # Mood not yet applied (still sealed).
    assert anomaly.state.scp_mood is None or anomaly.state.scp_mood == ""

    ok, message, events = scp.reveal_dossier(game, p1.id, anomaly.id)
    assert ok, message
    assert anomaly.state.scp_status == "active"
    assert anomaly.state.scp_mood == "cryptic"
    assert "mirror_box" in anomaly.state.scp_protocols
    assert any(e.type == EventType.SCP_MOOD_SHIFT for e in events)


# ---------------------------------------------------------------------------
# Engine-reads-scp_seal_default — open-time auto-seal of cryptic/antimemetic
# anomalies. The flag was set by previous waves on 28 card_defs; this is the
# engine wiring that finally honors it.
# ---------------------------------------------------------------------------


def test_seal_default_anomaly_opens_directly_into_sealed_state():
    """A card with ``scp_seal_default=True`` opens into ``sealed`` status, not
    ``active``. The reveal hook still fires (mood + protocol seeded), an
    ``SCP_SEAL_DOSSIER`` event is emitted, and the dossier is NOT in the
    active-anomaly registry.
    """
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Mirror That Interviews You")
    assert getattr(anomaly.card_def, "scp_seal_default", False) is True

    # Open WITHOUT explicit sealed=True. The engine should auto-seal because
    # the card_def carries the flag.
    ok, _msg, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    assert ok
    # Final state is sealed, not active.
    assert anomaly.state.scp_status == "sealed"
    # Reveal hook fired: cryptic mood + ritual_diagram protocol were seeded.
    assert anomaly.state.scp_mood == "cryptic"
    assert "ritual_diagram" in anomaly.state.scp_protocols
    # Not exposed as an active anomaly (sealed dossiers don't tick hazard).
    assert anomaly.id not in game.state.scp_anomalies.get(p1.id, [])
    # The seal event is emitted with reason="seal_default" so audits can
    # distinguish open-time auto-seal from explicit-sealed opens.
    seal_events = [e for e in events if e.type == EventType.SCP_SEAL_DOSSIER]
    assert seal_events, "expected SCP_SEAL_DOSSIER from auto-seal"
    assert any(e.payload.get("reason") == "seal_default" for e in seal_events)
    # And the SCP_ANOMALY_REVEALED event still fires (so consumers of the
    # reveal stream — AI, scoring, UI — see the dossier expose itself).
    assert any(e.type == EventType.SCP_ANOMALY_REVEALED for e in events)


def test_seal_default_anomaly_can_be_revealed_after_open_to_become_active():
    """After auto-seal at open, the standard ``reveal_dossier`` flow promotes
    the dossier to ``active`` without re-running the on-reveal hook (because
    mood/protocol were already seeded at open time).
    """
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Mirror That Interviews You")
    # Open auto-seals.
    ok, _msg, _ = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    assert ok
    assert anomaly.state.scp_status == "sealed"
    pre_mood = anomaly.state.scp_mood
    pre_protocols = list(anomaly.state.scp_protocols)

    # Now an explicit reveal_dossier should flip status to active without
    # double-seeding (the seeded-mood hook is idempotent on the mood field but
    # would append a duplicate protocol if it fired twice; the test asserts
    # protocols stay a single entry, proving the hook didn't re-fire here.
    # Actually the hook IS implemented idempotently for protocols — see
    # ``_seeded_mood`` — so the test must instead verify status change.)
    ok, _msg, _ = scp.reveal_dossier(game, p1.id, anomaly.id)
    assert ok
    assert anomaly.state.scp_status == "active"
    # The anomaly is now in the active registry.
    assert anomaly.id in game.state.scp_anomalies.get(p1.id, [])
    # Mood / protocols preserved (carried through reveal).
    assert anomaly.state.scp_mood == pre_mood
    assert anomaly.state.scp_protocols == pre_protocols


def test_anomaly_without_seal_default_still_opens_into_active_state():
    """Cards WITHOUT ``scp_seal_default`` open active as before. This is the
    regression guard for the additive change.
    """
    game, p1, _p2 = _setup()
    # The Concrete Saint has no seal_default — it just seeds a briefing token.
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    assert getattr(anomaly.card_def, "scp_seal_default", False) is False

    ok, _msg, events = scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)
    assert ok
    assert anomaly.state.scp_status == "active"
    # And the anomaly IS in the active registry.
    assert anomaly.id in game.state.scp_anomalies.get(p1.id, [])
    # No SCP_SEAL_DOSSIER event when seal_default is absent.
    seal_events = [e for e in events if e.type == EventType.SCP_SEAL_DOSSIER]
    assert not seal_events


def test_seal_default_anomaly_with_red_tape_seals_after_paperwork_clears():
    """Pending → activate via paperwork also honors ``scp_seal_default``.

    Open an anomaly with red_tape > 0 (no fast-track) so it lands pending.
    Tick paperwork; the activation path goes through ``process_paperwork``
    which now re-reads ``scp_seal_default`` and routes through the auto-seal
    branch.
    """
    game, p1, _p2 = _setup()
    # Find an ACW anomaly with red_tape > 0 (any pattern-applied ACW card
    # carries scp_seal_default=True; pick the first with red_tape > 0).
    candidates = [
        (name, card)
        for name, card in SCP_CARDS.items()
        if getattr(card, "scp_expansion_code", None) == "ACW"
        and CardType.SCP_ANOMALY in card.characteristics.types
        and getattr(card, "scp_seal_default", False) is True
        and int(getattr(card, "scp_red_tape", 0) or 0) > 0
    ]
    assert candidates, "expected at least one ACW seal-default anomaly with red_tape > 0"
    name, card = candidates[0]
    anomaly = _hand_card(game, p1, name)
    # Bump clearance so any clearance check passes during open.
    scp.site(game.state, p1.id)["clearance"] = 5

    # Open without fast-track: lands pending, NOT yet auto-sealed.
    ok, _msg, _ = scp.open_dossier(game, p1.id, anomaly.id, fast_track=False)
    assert ok
    assert anomaly.state.scp_status == "pending"
    # Mood not seeded yet (reveal hook fires on activation, not on open).
    assert anomaly.state.scp_mood is None

    # Tick paperwork enough to drain the queue.
    for _ in range(anomaly.state.scp_paperwork + 1):
        scp.process_paperwork(game, p1.id, amount=1)

    # Now the dossier should be sealed (auto-seal applied during activation).
    assert anomaly.state.scp_status == "sealed"
    # Reveal hook fired during the activation step: mood is set.
    assert anomaly.state.scp_mood == "cryptic"
    assert anomaly.id not in game.state.scp_anomalies.get(p1.id, [])


# Agent (c): scp_on_assign hook + personnel quirks
# ---------------------------------------------------------------------------


def test_personnel_quirks_janitor_reduces_breach_on_suppress_assignment():
    """Janitor Who Knows Too Much shaves a point of breach when assigned to suppress."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    janitor = _hand_card(game, p1, "Janitor Who Knows Too Much")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, janitor.id, fast_track=True)[0]

    # Seed breach so the Janitor has something to reduce.
    scp.site(game.state, p1.id)["breach"] = 3
    breach_before = scp.site(game.state, p1.id)["breach"]

    ok, message, events = scp.suppress_anomaly(game, p1.id, anomaly.id, [janitor.id])
    assert ok, message
    assert scp.site(game.state, p1.id)["breach"] == breach_before - 1
    assert any(
        event.type == EventType.SCP_INCIDENT_RESOLVED
        and event.payload.get("reason") == "janitor_hushed_alarm"
        for event in events
    )


def test_personnel_quirks_janitor_breach_floor_is_zero():
    """Janitor's on-assign payoff cannot drive breach below zero."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    janitor = _hand_card(game, p1, "Janitor Who Knows Too Much")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, janitor.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["breach"] = 0

    ok, _msg, _events = scp.suppress_anomaly(game, p1.id, anomaly.id, [janitor.id])
    assert ok
    assert scp.site(game.state, p1.id)["breach"] == 0


def test_personnel_quirks_memory_triage_handler_grants_task_bonus_with_memetics_co_assignment():
    """SZB Memory Triage Handler adds +1 research when a co-Memetics teammate is assigned."""
    game, p1, _p2 = _setup()
    # SZB Memory Triage Anomaly: curiosity for testing. Use a high-curiosity
    # anomaly so the task_bonus matters (research total = handler + memetics
    # analyst + co_assignment_bonus). We test the bonus shows up in the
    # SCP_TEST_RUN payload as "total".
    anomaly = _hand_card(game, p1, "SZB Memory Triage Anomaly")
    handler = _hand_card(game, p1, "SZB Memory Triage Handler")
    analyst = _hand_card(game, p1, "Memetics Analyst")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, handler.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, analyst.id, fast_track=True)[0]

    ok, _msg, events = scp.run_test(game, p1.id, anomaly.id, [handler.id, analyst.id])
    assert ok
    # The hook emits an SCP_INCIDENT_RESOLVED event with task_bonus=1 and
    # reason=memory_triage_handoff.
    assert any(
        event.type == EventType.SCP_INCIDENT_RESOLVED
        and event.payload.get("reason") == "memory_triage_handoff"
        and event.payload.get("task_bonus") == 1
        for event in events
    )


def test_personnel_quirks_press_conference_handler_trades_secrecy_for_suppression():
    """SZB Press Conference Handler grants +2 suppress at the cost of -1 secrecy."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    handler = _hand_card(game, p1, "SZB Press Conference Handler")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, handler.id, fast_track=True)[0]

    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    ok, _msg, events = scp.suppress_anomaly(game, p1.id, anomaly.id, [handler.id])
    assert ok
    assert scp.site(game.state, p1.id)["secrecy"] == secrecy_before - 1
    # The SCP_ASSIGN_STAFF event records the post-bonus suppression total.
    # Handler's suppress skill is 1 (per generator), +2 from task_bonus = 3.
    assign_events = [
        e for e in events if e.type == EventType.SCP_ASSIGN_STAFF
        and e.payload.get("task") == "suppress"
    ]
    assert assign_events
    assert assign_events[0].payload["total"] >= 3


def test_personnel_quirks_on_assign_does_not_fire_when_not_assigned():
    """A handler with scp_on_assign should NOT trigger when it's on the
    battlefield but not in the assigned staff list."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "The Concrete Saint")
    janitor = _hand_card(game, p1, "Janitor Who Knows Too Much")
    other = _hand_card(game, p1, "Junior Researcher")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, janitor.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, other.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["breach"] = 4
    breach_before = scp.site(game.state, p1.id)["breach"]

    # Suppress using ONLY the junior researcher — Janitor is present but not used.
    ok, _msg, events = scp.suppress_anomaly(game, p1.id, anomaly.id, [other.id])
    assert ok
    # Breach unchanged — the Janitor's on-assign quirk did not fire.
    assert scp.site(game.state, p1.id)["breach"] == breach_before
    assert not any(
        event.payload.get("reason") == "janitor_hushed_alarm"
        for event in events
    )


def test_personnel_quirks_intern_first_assignment_per_turn_is_free():
    """Sleep-Deprived Intern is NOT exhausted on the first assignment per turn,
    but IS exhausted on the second."""
    game, p1, _p2 = _setup()
    anomaly1 = _hand_card(game, p1, "Moth in the Camera")
    anomaly2 = _hand_card(game, p1, "Rain Inside the Elevator")
    intern = _hand_card(game, p1, "Sleep-Deprived Intern")

    assert scp.open_dossier(game, p1.id, anomaly1.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, anomaly2.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, intern.id, fast_track=True)[0]

    # First assignment: intern stays unexhausted.
    ok, _msg, _events = scp.run_test(game, p1.id, anomaly1.id, [intern.id])
    assert ok
    assert intern.state.scp_exhausted is False
    assert getattr(intern.state, "scp_assigns_this_turn", 0) == 1

    # Second assignment in the same turn: intern is exhausted normally.
    ok, _msg, _events = scp.run_test(game, p1.id, anomaly2.id, [intern.id])
    assert ok
    assert intern.state.scp_exhausted is True
    assert getattr(intern.state, "scp_assigns_this_turn", 0) == 2


def test_personnel_quirks_applier_is_idempotent():
    """Running apply_personnel_quirks repeatedly is safe — hooks and text stable."""
    from src.cards.scp import SCP_CARDS
    from src.cards.scp.mechanics.personnel_quirks import apply_personnel_quirks

    janitor = SCP_CARDS["Janitor Who Knows Too Much"]
    handler = SCP_CARDS["SZB Memory Triage Handler"]
    janitor_text_before = janitor.text
    handler_text_before = handler.text
    janitor_hook_before = janitor.scp_on_assign
    handler_hook_before = handler.scp_on_assign

    # Re-apply twice.
    apply_personnel_quirks(SCP_CARDS)
    apply_personnel_quirks(SCP_CARDS)

    # Text should be unchanged across applications.
    assert janitor.text == janitor_text_before
    assert handler.text == handler_text_before
    # Hooks are still callable.
    assert callable(janitor.scp_on_assign)
    assert callable(handler.scp_on_assign)
    # Text contains our marker clauses.
    assert "alarms hushed" in janitor.text
    assert "co-assigned Memetics" in handler.text


def test_personnel_quirks_white_pill_ward_drops_one_ethics_debt():
    """SZB White Pill Ward Handler on research: ethics debt -1."""
    game, p1, _p2 = _setup()
    anomaly = _hand_card(game, p1, "Moth in the Camera")
    handler = _hand_card(game, p1, "SZB White Pill Ward Handler")

    assert scp.open_dossier(game, p1.id, anomaly.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, handler.id, fast_track=True)[0]
    scp.site(game.state, p1.id)["ethics_debt"] = 3

    ok, _msg, events = scp.run_test(game, p1.id, anomaly.id, [handler.id])
    assert ok
    assert scp.site(game.state, p1.id)["ethics_debt"] == 2
    assert any(
        e.type == EventType.SCP_ETHICS_SPENT
        and e.payload.get("reason") == "white_pill_triage"
        for e in events
    )


# SZB bespoke mechanics (b) — the 18 SZB-bare anomalies wired into the
# Thaumiel-grid / bureaucratic / media / strange idioms.
# ---------------------------------------------------------------------------


def test_szb_thaumiel_contained_aura_buffs_matching_task():
    """Contained SZB Halo Key Anomaly gives +2 containment to the controller.

    Mirrors test_contained_bonus_extends_active_bonus_for_tests but with the
    bespoke wiring instead of an ad-hoc card_def patch — proves apply_szb_bespoke
    set scp_contained_bonus correctly.
    """
    game, p1, _p2 = _setup()
    halo = _hand_card(game, p1, "SZB Halo Key Anomaly")
    specialist = _hand_card(game, p1, "Containment Specialist")
    assert scp.open_dossier(game, p1.id, halo.id, fast_track=True)[0]
    assert scp.open_dossier(game, p1.id, specialist.id, fast_track=True)[0]
    # Halo Key is contain=5; specialist (contain 2) + dummy contain check
    # should fail without a helper, but we just force it into the contained
    # bucket via a direct mutation (mirrors how `_contain_anomaly_for_test`
    # would, but inline so the test stays self-contained).
    halo.state.scp_status = "contained"
    if halo.id in game.state.scp_anomalies[p1.id]:
        game.state.scp_anomalies[p1.id].remove(halo.id)
    if halo.id not in game.state.scp_contained[p1.id]:
        game.state.scp_contained[p1.id].append(halo.id)
    # Now the contained-aura should add +2 to the controller's contain checks.
    assert scp._active_bonus(game.state, p1.id, "contain") == 2
    # And not bleed into other tasks.
    assert scp._active_bonus(game.state, p1.id, "research") == 0
    assert scp._active_bonus(game.state, p1.id, "suppress") == 0


def test_szb_bureaucratic_anomaly_taxes_own_pending_on_reveal():
    """SZB Misfile Saint Anomaly taxes the controller's other pending dossiers."""
    game, p1, _p2 = _setup()
    # Stage a pending personnel so the tax has a target.
    spec = _hand_card(game, p1, "Containment Specialist")  # red_tape=1
    assert scp.open_dossier(game, p1.id, spec.id)[0]
    assert spec.state.scp_status == "pending"
    paperwork_before = spec.state.scp_paperwork

    misfile = _hand_card(game, p1, "SZB Misfile Saint Anomaly")
    ok, message, events = scp.open_dossier(game, p1.id, misfile.id, fast_track=True)
    assert ok, message
    assert misfile.state.scp_status == "active"
    # Specialist took +1 paperwork from the reveal-time tax.
    assert spec.state.scp_paperwork == paperwork_before + 1
    tax_events = [
        e for e in events
        if e.type == EventType.SCP_PAPERWORK_TICK
        and e.payload.get("reason") == "tax_own_pending"
    ]
    assert tax_events, "expected SCP_PAPERWORK_TICK reason=tax_own_pending"


def test_szb_media_anomaly_drops_secrecy_on_reveal():
    """SZB Glass Newsroom Anomaly drops secrecy by 2 on reveal (public_reveal idiom)."""
    game, p1, _p2 = _setup()
    newsroom = _hand_card(game, p1, "SZB Glass Newsroom Anomaly")  # red_tape=1
    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    ok, message, events = scp.open_dossier(game, p1.id, newsroom.id, fast_track=True)
    assert ok, message
    assert newsroom.state.scp_status == "active"
    # secrecy delta = -1 from fast-track (red_tape=1) + -2 from public_reveal = -3.
    assert scp.site(game.state, p1.id)["secrecy"] == secrecy_before - 1 - 2
    audit_events = [
        e for e in events
        if e.type == EventType.SCP_AUDIT
        and e.payload.get("reason") == "public_reveal"
    ]
    assert audit_events, "expected SCP_AUDIT reason=public_reveal"


def test_szb_chain_reactor_scales_with_other_active_anomalies():
    """SZB Chain Reactor Anomaly: breach +1 per OTHER active anomaly on reveal."""
    game, p1, _p2 = _setup()
    # Stage 2 other active anomalies first.
    moth = _hand_card(game, p1, "Moth in the Camera")
    assert scp.open_dossier(game, p1.id, moth.id, fast_track=True)[0]
    rain = _hand_card(game, p1, "Rain Inside the Elevator")
    assert scp.open_dossier(game, p1.id, rain.id, fast_track=True)[0]
    assert moth.state.scp_status == "active"
    assert rain.state.scp_status == "active"

    chain = _hand_card(game, p1, "SZB Chain Reactor Anomaly")  # red_tape=0
    breach_before = scp.site(game.state, p1.id)["breach"]
    ok, message, events = scp.open_dossier(game, p1.id, chain.id, fast_track=True)
    assert ok, message
    # Two other active anomalies => +2 breach.
    assert scp.site(game.state, p1.id)["breach"] == breach_before + 2
    chain_events = [
        e for e in events
        if e.type == EventType.SCP_BREACH_TICK
        and e.payload.get("reason") == "chain_reactor_reveal"
    ]
    assert chain_events, "expected SCP_BREACH_TICK reason=chain_reactor_reveal"


def test_szb_bespoke_applier_is_idempotent():
    """Running apply_szb_bespoke twice produces no double-append in card.text."""
    from src.cards.scp import SCP_CARDS
    from src.cards.scp.mechanics.szb_bespoke import apply_szb_bespoke

    # Capture text after the natural single-apply that happened at import time.
    before = {
        name: SCP_CARDS[name].text
        for name in (
            "SZB Halo Key Anomaly",
            "SZB Misfile Saint Anomaly",
            "SZB Glass Newsroom Anomaly",
            "SZB Chain Reactor Anomaly",
            "SZB Answer Box Anomaly",
        )
    }
    # Re-apply twice — idempotent guards should make the text identical.
    apply_szb_bespoke(SCP_CARDS)
    apply_szb_bespoke(SCP_CARDS)
    for name, original in before.items():
        assert SCP_CARDS[name].text == original, (
            f"{name}: text changed under re-apply. "
            f"before={original!r} after={SCP_CARDS[name].text!r}"
        )
