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
    assert scp.site(game.state, p1.id)["archives"] == 1
    assert junior.state.scp_exhausted is True
    assert intern.state.scp_exhausted is True
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
    assert scp.site(game.state, p1.id)["archives"] == 1


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
    intern = _hand_card(game, p1, "Sleep-Deprived Intern")
    assert scp.open_dossier(game, p1.id, anomaly.id)[0]
    assert scp.open_dossier(game, p1.id, junior.id)[0]
    assert scp.open_dossier(game, p1.id, intern.id)[0]
    ok, message, _events = scp.shift_mood(game, p1.id, anomaly.id, "cryptic")
    assert not ok
    assert message == "Mood shift requires a briefing token"
    scp.site(game.state, p1.id)["briefing"] = 1
    assert scp.shift_mood(game, p1.id, anomaly.id, "cryptic")[0]

    ok, message, _events = scp.run_test(game, p1.id, anomaly.id, [junior.id, intern.id])

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
    analyst.card_def.scp_aura = {"subtype:Memetics": {"research": 1}}

    total, used = scp._staff_total(game.state, p1.id, [analyst.id, junior.id], "research")
    # analyst: skills.research=2 + aura(+1, since it has Memetics) = 3
    # junior:  skills.research=1 + aura(0, no Memetics)         = 1
    assert total == 3 + 1
    assert set(used) == {analyst.id, junior.id}
    # Reset aura so it does not pollute the shared card_def for other tests.
    analyst.card_def.scp_aura = {}


def test_personnel_aura_any_selector_applies_to_all_friendly_staff():
    game, p1, _p2 = _setup()
    analyst = _hand_card(game, p1, "Memetics Analyst")
    junior = _hand_card(game, p1, "Junior Researcher")
    scp.open_dossier(game, p1.id, analyst.id, fast_track=True)
    scp.open_dossier(game, p1.id, junior.id, fast_track=True)
    analyst.card_def.scp_aura = {"any": {"research": 1}}

    total, _used = scp._staff_total(game.state, p1.id, [analyst.id, junior.id], "research")
    # analyst: skills 2 + 1 = 3 ; junior: skills 1 + 1 = 2
    assert total == 3 + 2
    analyst.card_def.scp_aura = {}


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

    Picks any ACW expansion anomaly. After reveal, mood is ``cryptic`` and the
    ``mirror_box`` protocol is on the anomaly. ``scp_seal_default`` is True.
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
    # Reveal hook fires on activation.
    game, p1, _p2 = _setup()
    obj = _hand_card(game, p1, sample_name)
    ok, _msg, _events = scp.open_dossier(game, p1.id, obj.id, fast_track=True)
    assert ok
    assert obj.state.scp_status == "active"
    assert obj.state.scp_mood == "cryptic"
    assert "mirror_box" in obj.state.scp_protocols


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
    # Reveal an even-index GOI anomaly (motif index 0 → "Serpent Consulate").
    name = "GOI Serpent Consulate Anomaly"
    assert name in SCP_CARDS
    secrecy_before = scp.site(game.state, p1.id)["secrecy"]
    obj = _hand_card(game, p1, name)
    ok, _msg, _events = scp.open_dossier(game, p1.id, obj.id, fast_track=True)
    assert ok
    # public_reveal -1 secrecy, plus fast_track on a 0-tape card costs 0,
    # so the only delta to secrecy is the reveal hook itself.
    assert scp.site(game.state, p1.id)["secrecy"] == secrecy_before - 1


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
