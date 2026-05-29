"""Gate tests for SCP "choosy" cards — activated + modal abilities.

Phase 0 of the verb-redesign foundation. These prove the primitive pipeline
end-to-end: cost grammar -> registration -> dispatch (scp.activate_ability) ->
legal-action surfacing -> AI fires/skips. If these pass, card work is unblocked.

Run under HYPERDRAFT_STRICT=1 so card-side errors in effect_fns surface.
"""

import asyncio

import pytest

from src.engine.game import Game
from src.engine.types import CardType, EventType, ZoneType
from src.engine import scp
from src.engine.scp_costs import SCPCost, SCPValueHint
from src.engine.scp_abilities import SCPMode, make_scp_activated_ability
from src.engine.scp_legal_actions import legal_scp_actions


def _setup():
    game = Game(mode="scp")
    p1 = game.add_player("Site-01")
    p2 = game.add_player("Site-02")
    game.setup_scp_player(p1, [])
    game.setup_scp_player(p2, [])
    return game, p1, p2


def _battlefield_personnel(game, player, name="Test Operative"):
    card_def = scp.make_scp_card(name, CardType.SCP_PERSONNEL, text="", skills={"contain": 1})
    obj = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.controller = player.id
    obj.state.scp_status = "active"
    return obj


def _activate_actions(game, player_id):
    return [a for a in legal_scp_actions(game, player_id) if a["type"] == "SCP_ACTIVATE_ABILITY"]


# --------------------------------------------------------------------------- #
# Dispatch: cost paid + effect resolves + activation event emitted
# --------------------------------------------------------------------------- #


def test_activate_ability_pays_cost_and_resolves_effect():
    game, p1, p2 = _setup()
    obj = _battlefield_personnel(game, p1)
    site = scp.site(game.state, p1.id)
    site["briefing"] = 1
    site["breach"] = 5

    def effect(o, state):
        s = scp.site(state, o.controller)
        s["breach"] = max(0, s["breach"] - 1)
        return []

    make_scp_activated_ability(
        obj, cost=SCPCost(briefing=1), description="Reduce breach by 1",
        effect_fn=effect, value_hint=SCPValueHint(breach=-1),
    )

    ok, msg, events = scp.activate_ability(game, p1.id, obj.id, 0)
    assert ok, msg
    assert scp.site(game.state, p1.id)["briefing"] == 0, "cost not paid"
    assert scp.site(game.state, p1.id)["breach"] == 4, "effect did not resolve"
    assert any(e.type == EventType.SCP_ABILITY_ACTIVATED for e in events)


def test_activate_ability_rejects_when_unaffordable():
    game, p1, p2 = _setup()
    obj = _battlefield_personnel(game, p1)
    scp.site(game.state, p1.id)["briefing"] = 0
    make_scp_activated_ability(
        obj, cost=SCPCost(briefing=1), description="Reduce breach by 1",
        effect_fn=lambda o, s: [], value_hint=SCPValueHint(breach=-1),
    )
    ok, _msg, events = scp.activate_ability(game, p1.id, obj.id, 0)
    assert not ok
    assert events == []


# --------------------------------------------------------------------------- #
# Legal-action surfacing
# --------------------------------------------------------------------------- #


def test_legal_action_appears_only_when_affordable():
    game, p1, p2 = _setup()
    obj = _battlefield_personnel(game, p1)
    make_scp_activated_ability(
        obj, cost=SCPCost(briefing=1), description="Reduce breach by 1",
        effect_fn=lambda o, s: [], value_hint=SCPValueHint(breach=-1),
    )
    scp.site(game.state, p1.id)["briefing"] = 0
    assert _activate_actions(game, p1.id) == []
    scp.site(game.state, p1.id)["briefing"] = 1
    acts = _activate_actions(game, p1.id)
    assert len(acts) == 1
    assert acts[0]["payload"]["source_id"] == obj.id


# --------------------------------------------------------------------------- #
# Modal "choose one" — one action per mode; chosen mode resolves
# --------------------------------------------------------------------------- #


def _modal_obj(game, player):
    obj = _battlefield_personnel(game, player, name="Site Directive")

    def gain_briefing(o, s):
        scp.site(s, o.controller)["briefing"] += 1
        return []

    def cut_breach(o, s):
        site = scp.site(s, o.controller)
        site["breach"] = max(0, site["breach"] - 1)
        return []

    make_scp_activated_ability(
        obj,
        cost=SCPCost(),
        description="Choose one",
        modes=[
            SCPMode("Gain 1 briefing", gain_briefing, ("value",), SCPValueHint(briefing=1)),
            SCPMode("Reduce breach by 1", cut_breach, ("stabilize",), SCPValueHint(breach=-1)),
        ],
    )
    return obj


def test_modal_modes_enumerated_and_dispatch_by_mode():
    game, p1, p2 = _setup()
    obj = _modal_obj(game, p1)
    site = scp.site(game.state, p1.id)
    site["breach"] = 3
    site["briefing"] = 0

    acts = _activate_actions(game, p1.id)
    assert len(acts) == 2, "expected one legal action per mode"
    assert {a["payload"]["mode"] for a in acts} == {0, 1}

    # Activating mode 1 must reduce breach, not add briefing.
    ok, _msg, _events = scp.activate_ability(game, p1.id, obj.id, 0, mode=1)
    assert ok
    assert scp.site(game.state, p1.id)["breach"] == 2
    assert scp.site(game.state, p1.id)["briefing"] == 0

    # With no mode supplied, a modal ability now raises a PendingChoice (the
    # human "choose one" path), rather than rejecting or silently defaulting.
    ok2, _m2, _e2 = scp.activate_ability(game, p1.id, obj.id, 0, mode=None)
    assert ok2
    assert game.state.pending_choice is not None
    assert game.state.pending_choice.choice_type == "modal"


def test_once_per_turn_gating():
    game, p1, p2 = _setup()
    obj = _battlefield_personnel(game, p1)
    make_scp_activated_ability(
        obj, cost=SCPCost(), description="Free tick", once_per_turn=True,
        effect_fn=lambda o, s: [], value_hint=SCPValueHint(briefing=1),
    )
    ok, _m, _e = scp.activate_ability(game, p1.id, obj.id, 0)
    assert ok
    ok2, _m2, _e2 = scp.activate_ability(game, p1.id, obj.id, 0)
    assert not ok2, "once_per_turn ability fired twice"
    assert _activate_actions(game, p1.id) == [], "spent ability still offered"


# --------------------------------------------------------------------------- #
# AI uses the ability (the crux — choosy cards must not be dead in tournaments)
# --------------------------------------------------------------------------- #


def _adapter():
    from src.ai.scp_adapter import SCPAIAdapter
    return SCPAIAdapter(difficulty="medium")


def _index_personnel(game, player, name="Test Operative"):
    obj = _battlefield_personnel(game, player, name=name)
    scp.ensure_scp_state(game.state, player.id)
    game.state.scp_personnel.setdefault(player.id, []).append(obj.id)
    return obj


def test_ai_fires_ability_when_beneficial():
    game, p1, p2 = _setup()
    obj = _index_personnel(game, p1)
    scp.site(game.state, p1.id)["breach"] = 6

    def effect(o, state):
        s = scp.site(state, o.controller)
        s["breach"] = max(0, s["breach"] - 1)
        return []

    make_scp_activated_ability(
        obj, cost=SCPCost(), description="Reduce breach by 1",
        effect_fn=effect, value_hint=SCPValueHint(breach=-1),
    )
    events = _adapter()._consider_activated_abilities(p1.id, game.state, game)
    assert scp.site(game.state, p1.id)["breach"] == 5, "AI did not fire a clearly-good ability"
    assert any(e.type == EventType.SCP_ABILITY_ACTIVATED for e in events)


def test_ai_skips_ability_when_worthless():
    game, p1, p2 = _setup()
    obj = _index_personnel(game, p1)
    scp.site(game.state, p1.id)["breach"] = 0  # nothing to reduce

    fired = {"v": False}

    def effect(o, state):
        fired["v"] = True
        return []

    make_scp_activated_ability(
        obj, cost=SCPCost(), description="Reduce breach by 1",
        effect_fn=effect, value_hint=SCPValueHint(breach=-1),
    )
    events = _adapter()._consider_activated_abilities(p1.id, game.state, game)
    assert not fired["v"], "AI fired a worthless ability (breach already 0)"
    assert events == []


def test_ai_picks_higher_value_modal_mode():
    game, p1, p2 = _setup()
    obj = _modal_obj(game, p1)  # mode0 = +1 briefing; mode1 = breach -1
    scp.ensure_scp_state(game.state, p1.id)
    game.state.scp_personnel.setdefault(p1.id, []).append(obj.id)
    site = scp.site(game.state, p1.id)
    site["breach"] = 6
    site["briefing"] = 0

    _adapter()._consider_activated_abilities(p1.id, game.state, game)
    # At breach 6, reducing breach (mode 1) outvalues +1 briefing (mode 0).
    assert scp.site(game.state, p1.id)["breach"] == 5
    assert scp.site(game.state, p1.id)["briefing"] == 0


# --------------------------------------------------------------------------- #
# PILOT: real Phyrexian Strain cards exercise the primitives end-to-end
# --------------------------------------------------------------------------- #

from src.cards.scp import SCP_CARDS


def _play(game, player, card_name):
    cd = SCP_CARDS[card_name]
    obj = game.create_object(
        name=cd.name, owner_id=player.id, zone=ZoneType.HAND,
        characteristics=cd.characteristics, card_def=cd,
    )
    scp.open_dossier(game, player.id, obj.id)
    return game.state.objects.get(obj.id)


def _active_anomaly(game, player, card_name):
    cd = SCP_CARDS[card_name]
    obj = game.create_object(
        name=cd.name, owner_id=player.id, zone=ZoneType.BATTLEFIELD,
        characteristics=cd.characteristics, card_def=cd,
    )
    obj.controller = player.id
    obj.state.scp_status = "active"
    scp.ensure_scp_state(game.state, player.id)
    if obj.id not in game.state.scp_anomalies.setdefault(player.id, []):
        game.state.scp_anomalies[player.id].append(obj.id)
    return obj


def test_pilot_o5_3_dead_ability_now_registers_and_fires():
    """Acceptance test: O5-3's previously-dead activated ability registers on
    battlefield entry, is surfaced as a legal action, and removes a compleation
    counter when fired."""
    game, p1, p2 = _setup()
    o5_3 = _play(game, p1, "Operative O5-3, Strain Containment Lead")
    assert getattr(o5_3.state, "activated_abilities", []), "O5-3 ability not registered (dead-code regression)"

    victim = _play(game, p1, 'Class-A Operative "Nailbiter"')
    victim.state.scp_compleation = 2

    acts = _activate_actions(game, p1.id)
    assert any(a["payload"]["source_id"] == o5_3.id for a in acts), "O5-3 ability not offered as a legal action"

    ok, msg, _events = scp.activate_ability(game, p1.id, o5_3.id, 0)
    assert ok, msg
    assert victim.state.scp_compleation == 1, "O5-3 did not remove a compleation counter"


def test_pilot_drei_places_real_compleation_counter():
    """Drei's scry placeholder is replaced by a real effect: on research-assign
    with a CV anomaly online, place a compleation counter on the opponent's
    strongest non-Mnestic Personnel."""
    game, p1, p2 = _setup()
    _active_anomaly(game, p1, "SCP-FBN-1151: Compleation Vector Spawn")
    drei = _play(game, p1, "Researcher Drei, Compleation Cartographer")
    opp = _play(game, p2, "Junior Researcher")  # non-Mnestic
    assert int(getattr(opp.state, "scp_compleation", 0) or 0) == 0

    events = drei.card_def.scp_on_assign(drei, game.state, "research")
    assert int(getattr(opp.state, "scp_compleation", 0) or 0) == 1, "Drei did not place a compleation counter"
    # No longer a scry placeholder.
    assert not any(e.payload.get("reason") == "drei_assign_scry" for e in events)


def test_pilot_o5_7_signature_bomb_harvests_archives():
    """O5-7 converts compleation setup into archives (the win axis)."""
    game, p1, p2 = _setup()
    o5_7 = _play(game, p1, "Operative O5-7, Strain Harvester")
    opp = _play(game, p2, "Junior Researcher")
    opp.state.scp_compleation = 2  # near-compleated

    before = scp.site(game.state, p1.id)["archives"]
    ok, msg, _events = scp.activate_ability(game, p1.id, o5_7.id, 0)
    assert ok, msg
    assert scp.site(game.state, p1.id)["archives"] == before + 1, "O5-7 did not harvest an archive"


def test_pilot_phyrexian_strain_deck_is_30_and_includes_bomb():
    from src.cards.scp import SCP_STARTER_DECKS
    deck = SCP_STARTER_DECKS["FBN_phyrexian_strain"]()
    assert len(deck) == 30
    names = {c.name for c in deck}
    assert "Operative O5-7, Strain Harvester" in names
    assert "Operative O5-3, Strain Containment Lead" in names


# --------------------------------------------------------------------------- #
# Modal HUMAN path: activate (no mode) -> PendingChoice -> submit -> resolve
# --------------------------------------------------------------------------- #


def test_modal_no_mode_creates_pending_choice():
    game, p1, p2 = _setup()
    obj = _modal_obj(game, p1)
    scp.site(game.state, p1.id)["breach"] = 3
    ok, msg, _events = scp.activate_ability(game, p1.id, obj.id, 0, mode=None)
    assert ok, msg
    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "modal"
    assert pc.player == p1.id
    assert len(pc.options) == 2
    # Nothing resolved yet — cost unpaid, no mode effect applied.
    assert scp.site(game.state, p1.id)["breach"] == 3


def test_modal_pending_choice_resolves_chosen_mode():
    game, p1, p2 = _setup()
    obj = _modal_obj(game, p1)
    scp.site(game.state, p1.id)["breach"] = 3
    scp.activate_ability(game, p1.id, obj.id, 0, mode=None)
    pc = game.state.pending_choice
    ok, msg, _ev = game.submit_choice(pc.id, p1.id, [1])  # mode 1 = breach -1
    assert ok, msg
    assert game.state.pending_choice is None
    assert scp.site(game.state, p1.id)["breach"] == 2


def test_modal_submit_accepts_option_dict_form():
    game, p1, p2 = _setup()
    obj = _modal_obj(game, p1)
    scp.site(game.state, p1.id)["briefing"] = 0
    scp.activate_ability(game, p1.id, obj.id, 0, mode=None)
    pc = game.state.pending_choice
    ok, _m, _e = game.submit_choice(pc.id, p1.id, [{"index": 0}])  # mode 0 = +1 briefing
    assert ok
    assert scp.site(game.state, p1.id)["briefing"] == 1


def test_serialize_scp_abilities_shape():
    from src.engine.scp_abilities import serialize_scp_abilities
    game, p1, p2 = _setup()
    obj = _modal_obj(game, p1)
    abilities = serialize_scp_abilities(obj, game.state)
    assert len(abilities) == 1
    a = abilities[0]
    assert a["index"] == 0 and a["is_modal"] is True and a["affordable"] is True
    assert [m["label"] for m in a["modes"]] == ["Gain 1 briefing", "Reduce breach by 1"]


def test_execute_action_dispatches_noop_and_ability():
    # The turn-loop dispatcher accepts SCP_NOOP (continue) and SCP_ACTIVATE_ABILITY.
    game, p1, p2 = _setup()
    game.state._game = game  # ensure back-ref for the turn manager path
    tm = game.turn_manager

    async def _drive():
        obj = _battlefield_personnel(game, p1)
        make_scp_activated_ability(
            obj, cost=SCPCost(), description="Free tick", once_per_turn=True,
            effect_fn=lambda o, s: [], value_hint=SCPValueHint(briefing=1),
        )
        ok_noop, _m, _e = await tm.execute_action(p1.id, {"action_type": "SCP_NOOP"})
        ok_act, _m2, _e2 = await tm.execute_action(
            p1.id, {"action_type": "SCP_ACTIVATE_ABILITY", "source_id": obj.id, "ability_index": 0}
        )
        return ok_noop, ok_act

    import asyncio as _aio
    ok_noop, ok_act = _aio.run(_drive())
    assert ok_noop and ok_act


# --------------------------------------------------------------------------- #
# Wave A: Eldrazi Apex — de-stubbed Hedron Audit (was a scry placeholder)
# --------------------------------------------------------------------------- #


def test_hedron_audit_destubbed_to_real_effect():
    game, p1, p2 = _setup()
    cd = SCP_CARDS["Hedron Audit"]
    obj = game.create_object(
        name=cd.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=cd.characteristics, card_def=cd,
    )
    breach0 = scp.site(game.state, p2.id)["breach"]
    brief0 = scp.site(game.state, p1.id)["briefing"]
    ok, _m, events = scp.open_dossier(game, p1.id, obj.id, fast_track=True)
    assert ok
    assert scp.site(game.state, p2.id)["breach"] == breach0 + 1, "opp breach not raised"
    assert scp.site(game.state, p1.id)["briefing"] == brief0 + 1, "briefing not gained"
    # No longer the scry placeholder.
    assert not any(e.payload.get("reason") == "scry_3_put_eldrazi_top" for e in events)


# --------------------------------------------------------------------------- #
# Wave A #1: Eldrazi Apex — bug fixes + Apollyon Convergence bomb
# --------------------------------------------------------------------------- #


def _bf_obj(game, player, card_name, status="active"):
    cd = SCP_CARDS[card_name]
    obj = game.create_object(
        name=cd.name, owner_id=player.id, zone=ZoneType.BATTLEFIELD,
        characteristics=cd.characteristics, card_def=cd,
    )
    obj.controller = player.id
    obj.state.scp_status = status
    return obj


def test_conscription_breach_exhausts_opposing_personnel():
    from src.cards.scp.foundations_beyond.eldrazi_apex import _conscription_breach
    game, p1, p2 = _setup()
    opp = _play(game, p2, "Junior Researcher")
    assert not opp.state.scp_exhausted
    src = _bf_obj(game, p1, "SCP-FBN-2280: Eldrazi Conscription Pattern")
    _conscription_breach(src, game.state)
    assert opp.state.scp_exhausted, "conscription did not exhaust opposing personnel"


def test_hedron_caged_reveal_boosts_hazard_via_suppressed():
    from src.cards.scp.foundations_beyond.eldrazi_apex import _hedron_caged_reveal
    game, p1, p2 = _setup()
    pend = _bf_obj(game, p1, "Junior Researcher", status="pending")  # a pending dossier
    titan = _bf_obj(game, p1, "SCP-FBN-2281: Hedron-Caged Titan")
    s0 = int(getattr(titan.state, "scp_suppressed", 0) or 0)
    _hedron_caged_reveal(titan, game.state)
    assert titan.state.scp_suppressed == s0 - 1, "hedron titan did not add hazard (1 pending -> -1 suppressed)"


def test_apollyon_convergence_bomb_fires_aw_and_self_breach():
    game, p1, p2 = _setup()
    aw = _bf_obj(game, p1, "SCP-FBN-2271: Apollyon-Class Void Eater (Ulamog)")  # AW 2
    scp.ensure_scp_state(game.state, p1.id)
    game.state.scp_anomalies.setdefault(p1.id, []).append(aw.id)
    fac = _bf_obj(game, p1, "Apollyon Convergence Array")
    game.state.scp_facilities.setdefault(p1.id, []).append(fac.id)
    assert getattr(fac.state, "activated_abilities", []), "convergence ability not registered"

    my_b0 = scp.site(game.state, p1.id)["breach"]
    opp_b0 = scp.site(game.state, p2.id)["breach"]
    ok, msg, _ev = scp.activate_ability(game, p1.id, fac.id, 0)
    assert ok, msg
    assert scp.site(game.state, p1.id)["breach"] == my_b0 + 2, "self-breach cost not applied"
    assert scp.site(game.state, p2.id)["breach"] > opp_b0, "Annihilation Wave did not fire on activation"


# --------------------------------------------------------------------------- #
# Wave A #2: MNR — Retrograde Erasure modal bomb + Mnestic Wake migration
# --------------------------------------------------------------------------- #


def test_mnr_retrograde_erasure_redact_mode():
    game, p1, p2 = _setup()
    fac = _bf_obj(game, p1, "MNR Retrograde Erasure Suite")
    game.state.scp_facilities.setdefault(p1.id, []).append(fac.id)
    assert getattr(fac.state, "activated_abilities", []), "Retrograde Erasure ability not registered"
    cd = SCP_CARDS["Junior Researcher"]
    game.create_object(name=cd.name, owner_id=p2.id, zone=ZoneType.HAND,
                       characteristics=cd.characteristics, card_def=cd)
    hand0 = len(game.state.zones[f"hand_{p2.id}"].objects)
    ok, msg, _ev = scp.activate_ability(game, p1.id, fac.id, 0, mode=1)  # Redact 2
    assert ok, msg
    assert len(game.state.zones[f"hand_{p2.id}"].objects) < hand0, "Redact mode did not discard opp"


def test_mnr_retrograde_erasure_reinforce_mode():
    game, p1, p2 = _setup()
    fac = _bf_obj(game, p1, "MNR Retrograde Erasure Suite")
    game.state.scp_facilities.setdefault(p1.id, []).append(fac.id)
    antimeme = next(c for c in SCP_CARDS.values() if int(getattr(c, "scp_antimeme", 0) or 0) >= 1)
    an = game.create_object(name=antimeme.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                            characteristics=antimeme.characteristics, card_def=antimeme)
    an.controller = p1.id
    an.state.scp_status = "active"
    an.state.scp_forget_counters = 2
    scp.ensure_scp_state(game.state, p1.id)
    game.state.scp_anomalies.setdefault(p1.id, []).append(an.id)
    ok, _m, _e = scp.activate_ability(game, p1.id, fac.id, 0, mode=0)  # Reinforce
    assert ok
    assert an.state.scp_forget_counters == 0, "Reinforce did not reset forget counters"


def test_mnestic_wake_migration_fires_and_pays_ethics():
    from src.cards.scp.mnestic_reset.helpers import _mnestic_wake_ability
    from src.engine.scp_abilities import is_scp_ability
    game, p1, p2 = _setup()
    cd = scp.make_scp_card("Test Bystander", CardType.SCP_PERSONNEL, text="", skills={"contain": 1})
    obj = game.create_object(name=cd.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                             characteristics=cd.characteristics, card_def=cd)
    obj.controller = p1.id
    obj.state.scp_status = "active"
    ability = _mnestic_wake_ability(obj, game.state, ethics_cost=1)
    assert is_scp_ability(ability), "Mnestic Wake is no longer an SCP ability after migration"
    scp.site(game.state, p1.id)["ethics_debt"] = 1
    ok, _m, _e = scp.activate_ability(game, p1.id, obj.id, ability.ability_index)
    assert ok
    assert obj.state.scp_mnestic_gained is True, "Mnestic Wake did not grant Mnestic"
    assert scp.site(game.state, p1.id)["ethics_debt"] == 0, "Mnestic Wake did not pay ethics"


def test_mnr_deck_includes_retrograde_erasure():
    from src.cards.scp import SCP_STARTER_DECKS
    deck = SCP_STARTER_DECKS["mnestic_reset_division"]()
    assert len(deck) == 25
    assert "MNR Retrograde Erasure Suite" in {c.name for c in deck}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
