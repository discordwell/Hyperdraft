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

    # A modal ability with no mode supplied is rejected (not silently defaulted).
    ok2, _m2, _e2 = scp.activate_ability(game, p1.id, obj.id, 0, mode=None)
    assert not ok2


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
