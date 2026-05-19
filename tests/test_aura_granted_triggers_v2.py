"""Helper 5 round 2 — three new trigger shapes on
``make_aura_setup(granted_triggered_abilities=...)``.

Gaps closed 2026-05-18:

1. ``trigger_on="death"`` — fires when the enchanted creature dies.
   Synchronous fire from ``_cleanup_handler`` BEFORE the Aura's
   granted-trigger stash is revoked (parallel to the activated-ability
   revocation timing fix).
2. ``trigger_on="enchanted_controller_upkeep"`` — fires at the beginning
   of the enchanted creature's *current* controller's upkeep. Re-reads
   ``attached_to.controller`` per fire so post-control-change auras
   target the right player.
3. PendingChoice from death triggers — uses the existing
   ``create_target_creature_choice`` helper; the death trigger fires
   during REACT before interceptor cleanup, so the dying creature's
   characteristics are still intact at PendingChoice opening time.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, Color, CardType,
    make_creature, make_enchantment, get_power,
)
from src.cards.interceptor_helpers import (
    make_aura_setup, make_death_trigger, create_target_creature_choice,
)


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
        name=name, power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Human"},
    )


# ---------------------------------------------------------------------------
# Gap 1 — Aura "enchanted creature dies" trigger
# ---------------------------------------------------------------------------


def test_aura_death_trigger_fires_when_enchanted_creature_dies():
    """When the enchanted creature dies, the Aura's death spec fires and
    its events appear in the event log (here: each opp loses 2 life)."""
    game, p1, p2 = _new_game()

    def death_effect(target_obj, event, state):
        # target_obj is the dying creature; iterate opponents from there.
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': pid, 'amount': -2, 'source': 'aura'},
                source=None,
            )
            for pid in state.players if pid != target_obj.controller
        ]

    aura_def = make_enchantment(
        name="Dark Spirits Blessing",
        mana_cost="{1}{B}",
        text="Enchanted creature dies → each opp loses 2 life.",
        subtypes={"Aura"},
        setup_interceptors=make_aura_setup(
            granted_triggered_abilities={
                "trigger_on": "death",
                "effect_fn": death_effect,
                "description": "Death: each opp loses 2 life",
            },
        ),
    )

    target = _put_card(game, p1, _plain_creature())
    aura = _put_card(game, p1, aura_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))

    death_specs = getattr(aura.state, "_aura_death_specs", None)
    assert death_specs and len(death_specs) == 1, (
        f"Expected death spec stashed on Aura state; got {death_specs}"
    )

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DESTROY,
        payload={'object_id': target.id, 'reason': 'test_destroy'},
        source=None,
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -2
    ]
    assert drains, (
        f"Expected -2 LIFE_CHANGE on p2 from Aura death trigger; "
        f"recent={[e.type.name for e in new[-15:]]}"
    )


def test_aura_death_trigger_does_not_fire_when_aura_leaves_directly():
    """If the Aura itself is bounced/exiled (target creature stays alive),
    the death spec should NOT fire."""
    game, p1, p2 = _new_game()
    fired = {"count": 0}

    def death_effect(target_obj, event, state):
        fired["count"] += 1
        return []

    aura_def = make_enchantment(
        name="Dark Spirits Blessing",
        mana_cost="{1}{B}",
        text="Death trigger",
        subtypes={"Aura"},
        setup_interceptors=make_aura_setup(
            granted_triggered_abilities={
                "trigger_on": "death",
                "effect_fn": death_effect,
            },
        ),
    )

    target = _put_card(game, p1, _plain_creature())
    aura = _put_card(game, p1, aura_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))

    # Bounce the Aura directly (zone_change to hand).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': aura.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'hand_{p1.id}',
            'to_zone_type': ZoneType.HAND,
        },
        source=aura.id,
    ))

    assert fired["count"] == 0, (
        f"Aura bounce should NOT fire death trigger; got {fired['count']}"
    )
    # Target should still be on the battlefield.
    assert target.zone == ZoneType.BATTLEFIELD


def test_aura_death_trigger_sees_dying_creatures_characteristics():
    """The death spec's effect_fn receives the dying creature with its
    characteristics still readable (power, controller, subtypes)."""
    game, p1, p2 = _new_game()
    captured = {}

    def death_effect(target_obj, event, state):
        captured['power'] = target_obj.characteristics.power
        captured['controller'] = target_obj.controller
        captured['subtypes'] = set(target_obj.characteristics.subtypes)
        return []

    aura_def = make_enchantment(
        name="Cursed Charm",
        mana_cost="{B}",
        text="Death trigger",
        subtypes={"Aura"},
        setup_interceptors=make_aura_setup(
            granted_triggered_abilities={
                "trigger_on": "death",
                "effect_fn": death_effect,
            },
        ),
    )

    big_def = make_creature(
        name="Champion", power=4, toughness=3, mana_cost="{2}{G}",
        colors={Color.GREEN}, subtypes={"Warrior", "Hero"},
    )
    target = _put_card(game, p1, big_def)
    aura = _put_card(game, p1, aura_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))

    game.emit(Event(
        type=EventType.DESTROY,
        payload={'object_id': target.id, 'reason': 'test'},
        source=None,
    ))

    assert captured.get('power') == 4
    assert captured.get('controller') == p1.id
    assert 'Warrior' in (captured.get('subtypes') or set())


# ---------------------------------------------------------------------------
# Gap 2 — Aura enchanted-controller upkeep trigger
# ---------------------------------------------------------------------------


def test_aura_upkeep_trigger_fires_on_enchanted_controllers_upkeep():
    """Trigger fires at the start of the enchanted creature's controller's
    upkeep — NOT the Aura's controller's upkeep."""
    game, p1, p2 = _new_game()

    def upkeep_effect(target_obj, event, state):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target_obj.controller, 'amount': -1,
                     'source': 'aura_upkeep'},
            source=None,
        )]

    aura_def = make_enchantment(
        name="Majin Mark",
        mana_cost="{B}",
        text="At enchanted creature's controller's upkeep, that player loses 1 life.",
        subtypes={"Aura"},
        setup_interceptors=make_aura_setup(
            granted_triggered_abilities={
                "trigger_on": "enchanted_controller_upkeep",
                "effect_fn": upkeep_effect,
            },
        ),
    )

    # p1 owns/controls the Aura; p2 owns/controls the target creature.
    target = _put_card(game, p2, _plain_creature(name="Bob's Creature"))
    aura = _put_card(game, p1, aura_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))

    # p2's upkeep should drain p2.
    before = len(game.state.event_log)
    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert drains, (
        f"Expected p2 (enchanted's controller) drain on their upkeep; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_aura_upkeep_trigger_skips_non_enchanted_controllers_upkeep():
    """On the Aura controller's upkeep (when they don't also control the
    target), the trigger should NOT fire — gated on enchanted's controller."""
    game, p1, p2 = _new_game()

    def upkeep_effect(target_obj, event, state):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target_obj.controller, 'amount': -1,
                     'source': 'aura'},
            source=None,
        )]

    aura_def = make_enchantment(
        name="Majin Mark", mana_cost="{B}", text="upkeep trigger",
        subtypes={"Aura"},
        setup_interceptors=make_aura_setup(
            granted_triggered_abilities={
                "trigger_on": "enchanted_controller_upkeep",
                "effect_fn": upkeep_effect,
            },
        ),
    )
    target = _put_card(game, p2, _plain_creature())
    aura = _put_card(game, p1, aura_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))

    # p1's upkeep — should NOT fire (p1 is the Aura controller, not the
    # enchanted's controller).
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('source') == 'aura'
    ]
    assert not drains, (
        f"Aura controller's upkeep should NOT fire; got {len(drains)}"
    )


def test_aura_upkeep_revoked_on_unattach():
    """UNATTACH should revoke the upkeep interceptor."""
    game, p1, p2 = _new_game()

    def upkeep_effect(target_obj, event, state):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target_obj.controller, 'amount': -1,
                     'source': 'aura'},
            source=None,
        )]

    aura_def = make_enchantment(
        name="Majin Mark", mana_cost="{B}", text="upkeep trigger",
        subtypes={"Aura"},
        setup_interceptors=make_aura_setup(
            granted_triggered_abilities={
                "trigger_on": "enchanted_controller_upkeep",
                "effect_fn": upkeep_effect,
            },
        ),
    )
    target = _put_card(game, p2, _plain_creature())
    aura = _put_card(game, p1, aura_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))
    granted_ids = list(getattr(aura.state, "_granted_triggered_ability_ids", []) or [])
    assert granted_ids, "Should have stashed the upkeep interceptor id"

    game.emit(Event(
        type=EventType.UNATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))

    # After UNATTACH, granted IDs should be cleared.
    cleared = getattr(aura.state, "_granted_triggered_ability_ids", None)
    assert not cleared, f"Granted IDs should be cleared after unattach; got {cleared}"
    for int_id in granted_ids:
        assert int_id not in game.state.interceptors, (
            f"Interceptor {int_id} should be revoked"
        )


# ---------------------------------------------------------------------------
# Gap 3 — PendingChoice from death triggers (verifies the existing
# create_target_creature_choice helper works from a death trigger's effect_fn)
# ---------------------------------------------------------------------------


def test_death_trigger_can_open_pending_choice_via_helper():
    """A death trigger's effect_fn can call create_target_creature_choice
    to open a PendingChoice for target creature. The dying creature is
    in graveyard but its characteristics are still intact during REACT."""
    game, p1, p2 = _new_game()

    def dying_setup(obj, state):
        def death_effect(event, st):
            dying_power = get_power(obj, st)
            def filter_fn(t, s):
                return t.controller != obj.controller

            def mill_effect(target, st):
                return [Event(
                    type=EventType.MILL,
                    payload={'player': target.controller, 'amount': dying_power},
                    source=obj.id,
                )]

            create_target_creature_choice(
                st, obj.controller, obj.id,
                filter_fn=filter_fn,
                effect_fn=mill_effect,
                prompt="Pick a creature to mill its controller",
            )
            return []
        return [make_death_trigger(obj, death_effect)]

    saiyan_def = make_creature(
        name="Super Saiyan Aura Bearer",
        power=4, toughness=4, mana_cost="{2}{R}{R}",
        colors={Color.RED}, subtypes={"Warrior"},
        setup_interceptors=dying_setup,
    )
    bait_def = _plain_creature(name="Sacrificial Bait")
    saiyan = _put_card(game, p1, saiyan_def)
    bait = _put_card(game, p2, bait_def)

    game.emit(Event(
        type=EventType.DESTROY,
        payload={'object_id': saiyan.id, 'reason': 'test'},
        source=None,
    ))

    choice = game.state.pending_choice
    assert choice is not None, "Death trigger should have opened a PendingChoice"
    assert choice.choice_type == "target"
    assert bait.id in choice.options, (
        f"Expected bait in choice options; got {choice.options}"
    )
    assert choice.player == p1.id

    # Resolve the choice — pick the bait.
    before = len(game.state.event_log)
    ok, msg, follow = game.submit_choice(choice.id, p1.id, [bait.id])
    assert ok, f"submit_choice failed: {msg}"
    new = game.state.event_log[before:]
    mills = [
        e for e in new
        if e.type == EventType.MILL
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == 4
    ]
    assert mills, (
        f"Expected MILL 4 on p2 from saiyan's death trigger; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


if __name__ == "__main__":
    print("=" * 70)
    print("Aura granted triggers v2 — death + enchanted-controller-upkeep")
    print("=" * 70)
    tests = [
        test_aura_death_trigger_fires_when_enchanted_creature_dies,
        test_aura_death_trigger_does_not_fire_when_aura_leaves_directly,
        test_aura_death_trigger_sees_dying_creatures_characteristics,
        test_aura_upkeep_trigger_fires_on_enchanted_controllers_upkeep,
        test_aura_upkeep_trigger_skips_non_enchanted_controllers_upkeep,
        test_aura_upkeep_revoked_on_unattach,
        test_death_trigger_can_open_pending_choice_via_helper,
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
    print("=" * 70)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * 70)
