"""Helper 5 — granted *triggered* abilities on Equipment / Aura attach.

Parallel to ``tests/test_phase5b_equipment_granted.py`` which covers the
activated-ability variant. This test guards
``_make_attached_triggered_ability_listener`` and the new
``granted_triggered_abilities`` parameter on ``make_equipment_setup`` /
``make_aura_setup``.

Coverage:
1. ATTACH installs the granted triggered interceptor; the granted IDs
   are stashed on ``source.state._granted_triggered_ability_ids``.
2. The granted trigger actually fires on the matching event (combat
   damage to player).
3. UNATTACH revokes — the granted Interceptor is popped from
   ``state.interceptors`` and the trigger no longer fires.
4. Equipment leaving the battlefield (ZONE_CHANGE → graveyard) also
   revokes — uses the same in-REACT cleanup path that the activated-
   ability listener uses (so cleanup runs before
   ``_cleanup_departed_interceptors`` strips the listener itself).
5. Re-attaching to a different creature revokes the first grant before
   installing the new one (no zombie triggers on the previous target).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, Color,
    make_creature, make_artifact,
)
from src.cards.interceptor_helpers import make_equipment_setup


def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_card(game, owner, card_def, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _plain_creature(name="Plain 1/1"):
    return make_creature(
        name=name,
        power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Human"},
        text="",
    )


def _life_drain_spec(amount=1):
    """A trigger spec: 'Whenever this creature deals combat damage to a
    player, that player loses N life.' Useful test substrate because the
    DAMAGE event fires through a well-known path."""
    def event_filter(event, state, target_id):
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != target_id:
            return False
        # Player damage only (not creature damage).
        target = event.payload.get('target')
        return target in state.players

    def effect_fn(target_obj, event, state):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={
                'player': event.payload.get('target'),
                'amount': -amount,
                'source': target_obj.id,
            },
            source=target_obj.id,
        )]

    return {
        'event_filter': event_filter,
        'effect_fn': effect_fn,
        'description': f'Combat damage → {amount} life',
    }


def test_attach_installs_granted_trigger():
    game, p1, _ = _new_game()
    sword_def = make_artifact(
        name="Test Sword",
        mana_cost="{2}",
        text="Equipped creature has 'When dealing damage, opp loses 1 life.'",
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            power_mod=1, toughness_mod=0,
            equip_cost="{2}",
            granted_triggered_abilities=_life_drain_spec(amount=1),
        ),
    )
    sword = _put_card(game, p1, sword_def)
    creature = _put_card(game, p1, _plain_creature())

    granted_before = list(getattr(sword.state, "_granted_triggered_ability_ids", []) or [])
    assert granted_before == [], "Before attach, no granted IDs should exist"

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': creature.id},
        source=sword.id,
    ))

    granted_after = list(getattr(sword.state, "_granted_triggered_ability_ids", []) or [])
    assert len(granted_after) == 1, (
        f"Expected 1 granted ID after ATTACH, got {granted_after}"
    )
    assert granted_after[0] in game.state.interceptors, (
        "Granted Interceptor should be registered on state.interceptors"
    )


def test_granted_trigger_actually_fires_on_damage():
    game, p1, p2 = _new_game()
    sword_def = make_artifact(
        name="Test Sword 2",
        mana_cost="{2}",
        text="Equipped creature combat damage → opp loses 1 life",
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            granted_triggered_abilities=_life_drain_spec(amount=2),
        ),
    )
    sword = _put_card(game, p1, sword_def)
    creature = _put_card(game, p1, _plain_creature())
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': creature.id},
        source=sword.id,
    ))

    p2_life_before = p2.life
    # Simulate the creature dealing combat damage to p2.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': creature.id,
            'target': p2.id,
            'amount': 1,
            'combat': True,
        },
        source=creature.id,
    ))
    # The granted trigger should fire a LIFE_CHANGE of -2 on p2.
    drains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -2
    ]
    assert drains, (
        f"Expected granted trigger to fire LIFE_CHANGE -2 on p2; "
        f"p2.life: {p2_life_before} → {p2.life}; "
        f"recent={[e.type.name for e in game.state.event_log[-8:]]}"
    )


def test_unattach_revokes_granted_trigger():
    game, p1, _ = _new_game()
    sword_def = make_artifact(
        name="Test Sword 3",
        mana_cost="{2}",
        text="Combat damage trigger",
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            granted_triggered_abilities=_life_drain_spec(amount=1),
        ),
    )
    sword = _put_card(game, p1, sword_def)
    creature = _put_card(game, p1, _plain_creature())
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': creature.id},
        source=sword.id,
    ))
    granted_ids = list(getattr(sword.state, "_granted_triggered_ability_ids", []) or [])
    assert granted_ids, "Setup: should have granted IDs after attach"

    game.emit(Event(
        type=EventType.UNATTACH,
        payload={'object_id': sword.id, 'target_id': creature.id},
        source=sword.id,
    ))

    for int_id in granted_ids:
        assert int_id not in game.state.interceptors, (
            f"After UNATTACH, granted Interceptor {int_id} should be revoked"
        )
    assert not getattr(sword.state, "_granted_triggered_ability_ids", []), (
        "After UNATTACH, the stashed IDs list should be cleared"
    )


def test_leaves_battlefield_revokes_granted_trigger():
    game, p1, _ = _new_game()
    sword_def = make_artifact(
        name="Test Sword 4",
        mana_cost="{2}",
        text="Granted trigger",
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            granted_triggered_abilities=_life_drain_spec(amount=1),
        ),
    )
    sword = _put_card(game, p1, sword_def)
    creature = _put_card(game, p1, _plain_creature())
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': creature.id},
        source=sword.id,
    ))
    granted_ids = list(getattr(sword.state, "_granted_triggered_ability_ids", []) or [])
    assert granted_ids, "Setup: granted IDs after attach"

    # Equipment leaves the battlefield (destroyed).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': sword.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=sword.id,
    ))

    for int_id in granted_ids:
        assert int_id not in game.state.interceptors, (
            f"After ZONE_CHANGE to graveyard, "
            f"granted Interceptor {int_id} should be revoked"
        )


def test_reattach_revokes_first_then_installs_second():
    game, p1, _ = _new_game()
    sword_def = make_artifact(
        name="Test Sword 5",
        mana_cost="{2}",
        text="Granted trigger",
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            granted_triggered_abilities=_life_drain_spec(amount=1),
        ),
    )
    sword = _put_card(game, p1, sword_def)
    creature_a = _put_card(game, p1, _plain_creature(name="Creature A"))
    creature_b = _put_card(game, p1, _plain_creature(name="Creature B"))

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': creature_a.id},
        source=sword.id,
    ))
    first_ids = list(getattr(sword.state, "_granted_triggered_ability_ids", []) or [])

    # Re-attach to creature_b — should revoke the trigger on creature_a
    # before installing on creature_b.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': creature_b.id},
        source=sword.id,
    ))
    second_ids = list(getattr(sword.state, "_granted_triggered_ability_ids", []) or [])

    # First IDs should be gone from state.interceptors.
    for int_id in first_ids:
        assert int_id not in game.state.interceptors, (
            f"First granted Interceptor {int_id} should have been "
            f"revoked when re-attaching to a different creature"
        )
    # New IDs should be present.
    assert second_ids, "After re-attach, should have new granted IDs"
    assert set(first_ids) & set(second_ids) == set(), (
        "First and second grant IDs should be distinct"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Helper 5 — granted triggered ability on attach")
    print("=" * 60)
    tests = [
        test_attach_installs_granted_trigger,
        test_granted_trigger_actually_fires_on_damage,
        test_unattach_revokes_granted_trigger,
        test_leaves_battlefield_revokes_granted_trigger,
        test_reattach_revokes_first_then_installs_second,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print("=" * 60)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * 60)
