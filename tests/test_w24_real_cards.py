"""W24 — real-card wirings for the W19 engine helpers.

W19 added three engine extensions (EXHAUST_RESET +
``reset_exhaust``, ``CostStep`` kind ``exile_from_graveyard``, and
``CostStep`` kind ``sacrifice_named``) and tested them against
synthetic cards in ``tests/test_engine_niche.py``. W24 wires those
helpers to the four real cards that motivated them:

* Aetherdrift — Elvish Refueler: upkeep-time exhaust reset on the
  controller's permanents (v1 model of the printed permission).
* Aetherdrift — Winter, Cursed Rider: Exhaust ability whose mana cost
  is ``{X}{2}{U}{B}, {T}`` and whose effect exiles X artifact cards
  from the controller's graveyard before applying ``-X/-X`` end-of-turn
  to every other nonartifact creature.
* Lost Caverns of Ixalan — Deconstruction Hammer: granted activated
  ability whose printed cost ``{3}, {T}, Sacrifice Deconstruction
  Hammer`` is now parsed end-to-end via the W19 ``sacrifice_named``
  cost-step kind (the W6 effect_fn workaround was removed).

Each test exercises the full engine path (registration via
``setup_interceptors``, cost parsing, additional-cost validation,
and the effect_fn).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, make_artifact,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase


# ---------------------------------------------------------------------------
# Test helpers (mirror tests/test_engine_niche.py)
# ---------------------------------------------------------------------------


def _setup_game_for_player(p_id, game):
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN


def _spawn_on_battlefield(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _give_player_mana(player, mana_system, generic=0, red=0, green=0,
                      white=0, blue=0, black=0):
    from src.engine.mana import ManaType
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(green):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)
    for _ in range(white):
        mana_system.produce_mana(player.id, ManaType.WHITE, 1)
    for _ in range(blue):
        mana_system.produce_mana(player.id, ManaType.BLUE, 1)
    for _ in range(black):
        mana_system.produce_mana(player.id, ManaType.BLACK, 1)


def _stash_in_graveyard(game, player, card_def, count):
    """Create ``count`` GameObjects in the player's graveyard."""
    gy_key = f"graveyard_{player.id}"
    gy = game.state.zones[gy_key]
    out = []
    for _ in range(count):
        stub = game.create_object(
            name=card_def.name,
            owner_id=player.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=card_def.characteristics,
            card_def=None,
        )
        stub.card_def = card_def
        if stub.id not in gy.objects:
            gy.objects.append(stub.id)
        out.append(stub)
    return out


# ---------------------------------------------------------------------------
# (1) Elvish Refueler — upkeep-time exhaust reset
# ---------------------------------------------------------------------------


def test_elvish_refueler_registers_own_exhaust():
    """The card's own '{1}{G}: +1/+1 counter' Exhaust is registered."""
    from src.cards.aetherdrift import ELVISH_REFUELER

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    refueler = _spawn_on_battlefield(game, p1, ELVISH_REFUELER)
    abilities = refueler.state.activated_abilities
    assert len(abilities) >= 1, "Elvish Refueler should register its Exhaust ability"
    # The Exhaust descriptor should be once-per-game with the printed cost.
    ex = next((a for a in abilities if a.is_exhaust), None)
    assert ex is not None, "expected an Exhaust ability"
    assert ex.cost_text == "{1}{G}", f"unexpected cost: {ex.cost_text!r}"
    assert ex.once_per_game is True
    print("PASS: Elvish Refueler registers its own '{1}{G}' Exhaust ability")


def test_elvish_refueler_upkeep_resets_used_exhausts():
    """Marking the controller's exhausts as used and emitting the upkeep
    PHASE_START should clear them via Elvish Refueler's interceptor."""
    async def _run():
        from src.cards.aetherdrift import ELVISH_REFUELER, HAZARD_OF_THE_DUNES

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        refueler = _spawn_on_battlefield(game, p1, ELVISH_REFUELER)
        # Hazard of the Dunes wires a {6}{G} Exhaust on a real Aetherdrift card.
        hazard = _spawn_on_battlefield(game, p1, HAZARD_OF_THE_DUNES)

        # Mark all of Alice's exhaust descriptors as used.
        for o in (refueler, hazard):
            for a in o.state.activated_abilities:
                if a.is_exhaust:
                    a.once_per_game_used = True
        for o in (refueler, hazard):
            assert any(a.once_per_game_used for a in o.state.activated_abilities)

        # Fire the controller's beginning-of-upkeep trigger by emitting a
        # PHASE_START event — the upkeep trigger filter watches for this.
        game.state.active_player = p1.id
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'upkeep', 'active_player': p1.id},
        ))

        # Both exhaust descriptors should be reset.
        for o in (refueler, hazard):
            for a in o.state.activated_abilities:
                if a.is_exhaust:
                    assert a.once_per_game_used is False, \
                        f"upkeep trigger should have reset {o.name}'s exhaust"
        print("PASS: Elvish Refueler's upkeep reset clears controller's used exhausts")

    asyncio.get_event_loop().run_until_complete(_run())


def test_elvish_refueler_upkeep_does_not_reset_opponent_exhausts():
    """The reset is controller-scoped — opponents' exhausts stay locked."""
    async def _run():
        from src.cards.aetherdrift import ELVISH_REFUELER, HAZARD_OF_THE_DUNES

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        refueler = _spawn_on_battlefield(game, p1, ELVISH_REFUELER)
        # Bob's Hazard of the Dunes (different controller).
        bob_hazard = _spawn_on_battlefield(game, p2, HAZARD_OF_THE_DUNES)

        for o in (refueler, bob_hazard):
            for a in o.state.activated_abilities:
                if a.is_exhaust:
                    a.once_per_game_used = True

        game.state.active_player = p1.id
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'upkeep', 'active_player': p1.id},
        ))

        # Alice's exhaust resets...
        for a in refueler.state.activated_abilities:
            if a.is_exhaust:
                assert a.once_per_game_used is False
        # ...but Bob's stays locked.
        for a in bob_hazard.state.activated_abilities:
            if a.is_exhaust:
                assert a.once_per_game_used is True, \
                    "Bob's Exhaust must remain locked after Alice's upkeep"
        print("PASS: Elvish Refueler's reset is controller-scoped (no opp leakage)")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# (2) Winter, Cursed Rider — X-cost + exile-X-artifacts-from-graveyard
# ---------------------------------------------------------------------------


def test_winter_cursed_rider_registers_x_cost_exhaust():
    """Winter, Cursed Rider's Exhaust descriptor parses {X}{2}{U}{B}, {T}."""
    from src.cards.aetherdrift import WINTER_CURSED_RIDER

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    winter = _spawn_on_battlefield(game, p1, WINTER_CURSED_RIDER)
    abilities = winter.state.activated_abilities
    ex = next((a for a in abilities if a.is_exhaust), None)
    assert ex is not None, "Winter, Cursed Rider should register an Exhaust"
    assert ex.requires_tap is True, "{T} should be parsed"
    assert ex.has_x_cost is True, "X-cost should be detected"
    assert ex.mana_cost is not None
    assert ex.mana_cost.x_count == 1
    assert ex.mana_cost.generic == 2
    assert ex.mana_cost.blue == 1
    assert ex.mana_cost.black == 1
    print("PASS: Winter, Cursed Rider registers {X}{2}{U}{B}, {T} Exhaust ability")


def test_winter_cursed_rider_effect_exiles_artifacts_and_pumps_down():
    """Calling effect_fn directly with x_value=2 exiles 2 artifacts and emits
    -2/-2 to nonartifact creatures."""
    from src.cards.aetherdrift import WINTER_CURSED_RIDER

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    winter = _spawn_on_battlefield(game, p1, WINTER_CURSED_RIDER)

    # Stash artifact cards in Alice's graveyard.
    artifact_def = make_artifact(
        name="Junk Artifact", mana_cost="{1}", text="",
    )
    creature_def = make_creature(
        name="Stray Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    arts = _stash_in_graveyard(game, p1, artifact_def, 3)
    # And one creature card in the GY (NOT artifact — should be skipped).
    _stash_in_graveyard(game, p1, creature_def, 1)

    # Spawn an artifact creature and a nonartifact creature on battlefield —
    # the artifact one must NOT receive -X/-X.
    cleric_def = make_creature(
        name="Plain Cleric", power=3, toughness=3, mana_cost="{1}{W}",
        colors={Color.WHITE}, subtypes={"Cleric"}, text="",
    )
    artcre_def = make_creature(
        name="Walking Artifact", power=4, toughness=4,
        mana_cost="{4}", colors=set(), subtypes={"Construct"}, text="",
    )
    # Make the Walking Artifact actually have ARTIFACT type (some card factories
    # place CardType differently — set the types directly to be safe).
    cleric = _spawn_on_battlefield(game, p2, cleric_def)
    artcre = _spawn_on_battlefield(game, p2, artcre_def)
    artcre.characteristics.types.add(CardType.ARTIFACT)

    # Find the Exhaust descriptor on Winter and call effect_fn directly with x=2.
    ex = next(a for a in winter.state.activated_abilities if a.is_exhaust)
    events = ex.effect_fn(winter, game.state, [], x_value=2)
    types = [e.type for e in events]

    # 2 EXILE events for 2 artifact cards from GY.
    exile_events = [e for e in events if e.type == EventType.EXILE]
    assert len(exile_events) == 2, \
        f"expected 2 EXILE events, got {len(exile_events)}"
    exiled_ids = {e.payload['object_id'] for e in exile_events}
    artifact_ids = {a.id for a in arts}
    assert exiled_ids.issubset(artifact_ids), \
        f"exiled ids {exiled_ids} should be subset of artifact ids in GY"

    # PT_MODIFICATION for the nonartifact creature (Plain Cleric) but not the
    # artifact creature (Walking Artifact). Also should not target Winter itself.
    pt_events = [e for e in events if e.type == EventType.PT_MODIFICATION]
    affected_ids = {e.payload['object_id'] for e in pt_events}
    assert cleric.id in affected_ids, \
        "nonartifact Cleric should receive -X/-X"
    assert artcre.id not in affected_ids, \
        "artifact creature should NOT receive -X/-X"
    assert winter.id not in affected_ids, \
        "Winter itself should be excluded ('each OTHER nonartifact creature')"
    # And every PT_MODIFICATION should have power_mod=-2, toughness_mod=-2.
    for e in pt_events:
        assert e.payload['power_mod'] == -2
        assert e.payload['toughness_mod'] == -2
        assert e.payload['duration'] == 'end_of_turn'
    print("PASS: Winter, Cursed Rider exiles X artifacts and -X/-X's nonartifacts only")


def test_winter_cursed_rider_x_zero_is_noop():
    """With x=0, no exile events and no PT modifications fire."""
    from src.cards.aetherdrift import WINTER_CURSED_RIDER

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    winter = _spawn_on_battlefield(game, p1, WINTER_CURSED_RIDER)
    cleric_def = make_creature(
        name="Plain Cleric", power=3, toughness=3, mana_cost="{1}{W}",
        colors={Color.WHITE}, subtypes={"Cleric"}, text="",
    )
    _spawn_on_battlefield(game, p2, cleric_def)

    ex = next(a for a in winter.state.activated_abilities if a.is_exhaust)
    events = ex.effect_fn(winter, game.state, [], x_value=0)
    assert events == [], f"x=0 should be a no-op, got {events}"
    print("PASS: Winter, Cursed Rider with X=0 is a no-op")


# ---------------------------------------------------------------------------
# (3) Deconstruction Hammer — sacrifice_named cost step end-to-end
# ---------------------------------------------------------------------------


def test_deconstruction_hammer_cost_uses_sacrifice_named_step():
    """The granted ability's cost text exposes a sacrifice_named CostStep."""
    from src.cards.lost_caverns_ixalan import DECONSTRUCTION_HAMMER

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn_on_battlefield(game, p1, bear_def)
    hammer = _spawn_on_battlefield(game, p1, DECONSTRUCTION_HAMMER)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": hammer.id, "target_id": bear.id},
        source=hammer.id, controller=p1.id,
    ))

    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == hammer.id]
    assert len(granted) == 1, f"expected 1 granted ability, got {len(granted)}"
    g = granted[0]
    # Cost text is the full printed cost.
    assert g.cost_text == "{3}, {T}, Sacrifice Deconstruction Hammer", \
        f"unexpected cost text: {g.cost_text!r}"
    # Mana parsed.
    assert g.mana_cost is not None and g.mana_cost.generic == 3
    # Tap parsed.
    assert g.requires_tap is True
    # The sacrifice_named step lands in the additional cost plan.
    plan = g.additional_cost_plan
    assert plan is not None, "additional cost plan should exist"
    assert len(plan) == 1
    step = plan[0]
    assert step.kind == "sacrifice_named", \
        f"expected sacrifice_named, got {step.kind}"
    assert step.name_match == "deconstruction hammer"
    # And critically: sac_self should be False — the sacrifice is the
    # *equipment*, not the creature carrying the ability.
    assert g.sac_self is False, \
        "granted ability should not be flagged as self-sacrifice"
    print("PASS: Deconstruction Hammer's cost parses to a sacrifice_named CostStep")


def test_deconstruction_hammer_activation_blocks_when_unattached_after_sac():
    """Removing the attached Deconstruction Hammer makes the cost unpayable."""
    async def _run():
        from src.cards.lost_caverns_ixalan import DECONSTRUCTION_HAMMER
        from src.engine.activated import can_pay_activation

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        bear_def = make_creature(
            name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
            colors={Color.GREEN}, subtypes={"Bear"}, text="",
        )
        bear = _spawn_on_battlefield(game, p1, bear_def)
        hammer = _spawn_on_battlefield(game, p1, DECONSTRUCTION_HAMMER)
        bear.state.summoning_sickness = False

        game.emit(Event(
            type=EventType.ATTACH,
            payload={"object_id": hammer.id, "target_id": bear.id},
            source=hammer.id, controller=p1.id,
        ))

        granted = [a for a in bear.state.activated_abilities
                   if getattr(a, "_granted_by", None) == hammer.id]
        assert len(granted) == 1
        g = granted[0]

        # Give Alice 3 mana so the only blocker would be the named-card sac.
        _give_player_mana(p1, game.mana_system, generic=3)
        ok = can_pay_activation(
            g, bear, game.state, p1.id,
            mana_system=game.mana_system,
            is_active_player=True, is_main_phase=True, stack_empty=True,
        )
        assert ok is True, "should be payable while Hammer is on the battlefield"

        # Move the Hammer off the battlefield (e.g. to graveyard).
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': hammer.id,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.GRAVEYARD,
            },
        ))

        # Note: when the equipment leaves play, the granted ability is also
        # revoked. The check we want here is that the cost-validation logic
        # itself catches the missing named card. Re-attach a clean copy with
        # the same setup to a different creature, then move that hammer
        # to graveyard and check.
        bear2 = _spawn_on_battlefield(game, p1, bear_def)
        hammer2 = _spawn_on_battlefield(game, p1, DECONSTRUCTION_HAMMER)
        bear2.state.summoning_sickness = False
        game.emit(Event(
            type=EventType.ATTACH,
            payload={"object_id": hammer2.id, "target_id": bear2.id},
            source=hammer2.id, controller=p1.id,
        ))
        granted2 = [a for a in bear2.state.activated_abilities
                    if getattr(a, "_granted_by", None) == hammer2.id]
        g2 = granted2[0]

        # Now move hammer2 to a non-battlefield zone via direct mutation
        # to simulate "the equipment is gone" before the activation. We do
        # this by changing its zone field — the granted ability cleanup
        # would normally also strip g2 from bear2 on zone change, so we
        # confirm the cost validation catches the missing named card
        # independently by directly poking the zone.
        # NOTE: we must keep g2 alive, so we move via direct field set.
        hammer2.zone = ZoneType.EXILE
        # Remove it from the battlefield zone list.
        bf_objects = game.state.zones["battlefield"].objects
        if hammer2.id in bf_objects:
            bf_objects.remove(hammer2.id)

        _give_player_mana(p1, game.mana_system, generic=3)
        ok2 = can_pay_activation(
            g2, bear2, game.state, p1.id,
            mana_system=game.mana_system,
            is_active_player=True, is_main_phase=True, stack_empty=True,
        )
        assert ok2 is False, \
            "cost should be unpayable when Deconstruction Hammer is not on battlefield"
        print("PASS: Deconstruction Hammer cost blocks when no named card on battlefield")

    asyncio.get_event_loop().run_until_complete(_run())


def test_deconstruction_hammer_effect_fn_only_emits_destroy():
    """After the W19 refactor, effect_fn returns ONLY the destroy event."""
    from src.cards.lost_caverns_ixalan import DECONSTRUCTION_HAMMER
    from src.engine.targeting import Target

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn_on_battlefield(game, p1, bear_def)
    hammer = _spawn_on_battlefield(game, p1, DECONSTRUCTION_HAMMER)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": hammer.id, "target_id": bear.id},
        source=hammer.id, controller=p1.id,
    ))

    # Make a target artifact.
    junk_def = make_artifact(name="Junk", mana_cost="{1}", text="")
    junk = _spawn_on_battlefield(game, p1, junk_def)

    g = next(a for a in bear.state.activated_abilities
             if getattr(a, "_granted_by", None) == hammer.id)
    events = g.effect_fn(bear, game.state, [Target(id=junk.id)])
    types = [e.type for e in events]
    assert EventType.OBJECT_DESTROYED in types, \
        "effect_fn must emit OBJECT_DESTROYED for the target"
    assert EventType.SACRIFICE not in types, \
        "SACRIFICE is now paid by pay_activation_cost, not effect_fn"
    # Only one event total: the destroy.
    assert len(events) == 1, f"expected exactly 1 event, got {len(events)}: {types}"
    print("PASS: Deconstruction Hammer effect_fn emits only OBJECT_DESTROYED post-W19")


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


def main():
    tests = [
        # (1) Elvish Refueler
        test_elvish_refueler_registers_own_exhaust,
        test_elvish_refueler_upkeep_resets_used_exhausts,
        test_elvish_refueler_upkeep_does_not_reset_opponent_exhausts,
        # (2) Winter, Cursed Rider
        test_winter_cursed_rider_registers_x_cost_exhaust,
        test_winter_cursed_rider_effect_exiles_artifacts_and_pumps_down,
        test_winter_cursed_rider_x_zero_is_noop,
        # (3) Deconstruction Hammer
        test_deconstruction_hammer_cost_uses_sacrifice_named_step,
        test_deconstruction_hammer_activation_blocks_when_unattached_after_sac,
        test_deconstruction_hammer_effect_fn_only_emits_destroy,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, e))
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, e))
            print(f"ERROR: {t.__name__}: {e!r}")

    if failed:
        print(f"\n{len(failed)} test(s) failed.")
        sys.exit(1)
    print(f"\nAll {len(tests)} W24 real-card tests passed.")


if __name__ == "__main__":
    main()
