"""Sweep 12: grant_triggered_ability framework test."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature,
)
from src.cards.interceptor_helpers import grant_triggered_ability


def _spawn(game, player, card_def):
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


def test_granted_attack_trigger_fires():
    """Target creature gains 'Whenever this creature attacks, gain 1 life'."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    source_def = make_creature(
        name="Source", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED}, subtypes={"Wizard"}, text="",
    )
    bear = _spawn(game, p1, bear_def)
    source = _spawn(game, p1, source_def)

    captured = []

    def attacks_filter(event, state, target_id):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        # Match on the attacking creature's id.
        return event.payload.get("attacker_id") == target_id or event.payload.get("creature") == target_id

    def attack_effect(target_obj, event, state):
        captured.append("attacked")
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target_obj.controller, 'amount': 1},
            source=target_obj.id, controller=target_obj.controller,
        )]

    grant_triggered_ability(
        bear, source, game.state,
        event_filter=attacks_filter,
        effect_fn=attack_effect,
        duration='end_of_turn',
    )

    p1_life_before = game.state.players[p1.id].life
    # Fire ATTACK_DECLARED for the bear.
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bear.id},
    ))
    assert captured == ["attacked"], f"expected attack capture, got {captured}"
    p1_life_after = game.state.players[p1.id].life
    assert p1_life_after == p1_life_before + 1, f"expected +1 life, got {p1_life_before} → {p1_life_after}"
    print("PASS: granted attack trigger fires")


def test_granted_damage_trigger_one_shot():
    """One-shot rider: 'When this creature is next dealt damage, draw a card.'"""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=4, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    source_def = make_creature(
        name="Source", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED}, subtypes={"Wizard"}, text="",
    )
    bear = _spawn(game, p1, bear_def)
    source = _spawn(game, p1, source_def)

    captured = []
    def damage_filter(event, state, target_id):
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == target_id or event.payload.get('object_id') == target_id

    def damage_effect(target_obj, event, state):
        captured.append(event.payload.get('amount', 0))
        return []  # No follow-up events.

    grant_triggered_ability(
        bear, source, game.state,
        event_filter=damage_filter,
        effect_fn=damage_effect,
        one_shot=True,
    )

    # Damage 1: should fire.
    game.emit(Event(type=EventType.DAMAGE, payload={'target': bear.id, 'amount': 1}))
    # Damage 2: should NOT fire (one-shot already fired).
    game.emit(Event(type=EventType.DAMAGE, payload={'target': bear.id, 'amount': 2}))

    assert captured == [1], f"expected one fire (amount=1), got {captured}"
    print("PASS: one-shot granted damage trigger fires once")


def test_end_of_turn_sweep_removes_granted_trigger():
    """A `duration='end_of_turn'` granted trigger must be removed at EOT."""
    import asyncio
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    source_def = make_creature(
        name="Source", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED}, subtypes={"Wizard"}, text="",
    )
    bear = _spawn(game, p1, bear_def)
    source = _spawn(game, p1, source_def)

    def filt(event, state, target_id):
        return event.type == EventType.DAMAGE and event.payload.get("target") == target_id
    def effect(target_obj, event, state):
        return []

    grant_triggered_ability(
        bear, source, game.state,
        event_filter=filt, effect_fn=effect,
        duration='end_of_turn', one_shot=False,
    )
    interceptor_count_before = len(game.state.interceptors)

    # Run end-of-turn sweep manually via the turn manager's cleanup step.
    asyncio.run(game.turn_manager._do_cleanup_step())

    interceptor_count_after = len(game.state.interceptors)
    assert interceptor_count_after < interceptor_count_before, \
        f"end_of_turn interceptor not swept; before={interceptor_count_before}, after={interceptor_count_after}"
    print("PASS: end-of-turn sweep removes granted trigger")


if __name__ == "__main__":
    test_granted_attack_trigger_fires()
    test_granted_damage_trigger_one_shot()
    test_end_of_turn_sweep_removes_granted_trigger()
    print("\nAll grant_triggered_ability tests passed!")
