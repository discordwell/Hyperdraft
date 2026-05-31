"""
Regeneration shield tests (CR 701.16).

Covers ``src.engine.replacements.make_regeneration_shield`` and the
``make_regenerate_ability`` activated-ability wrapper:

- A regen shield replaces the next destroy: the creature SURVIVES (stays on
  the battlefield), is tapped, all marked damage is removed, it leaves combat,
  and the shield is consumed (one-shot).
- A second destroy the same turn kills the creature (shield was single-use).
- Lethal combat damage routed through the SBA is regenerated too (and the SBA
  does not immediately re-destroy it, because damage is cleared).
- Regeneration does NOT replace a sacrifice (CR: it only replaces "destroy").
- Additive discipline: a creature with NO shield dies normally — base
  destroy behavior is unchanged for everything else.

Run:
    PYTHONPATH=. python tests/test_regenerate.py
"""

import os
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.engine.replacements import make_regeneration_shield


def _make_game(players=1):
    game = Game()
    out = []
    for i in range(players):
        out.append(game.add_player(f"P{i}"))
    return game, out


def _creature(game, player, name="Regen Target", power=3, toughness=3):
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=power, toughness=toughness
        ),
    )


def _on_battlefield(game, obj):
    return (
        obj.zone == ZoneType.BATTLEFIELD
        and obj.id in game.state.zones['battlefield'].objects
    )


# =============================================================================
# Core shield behavior
# =============================================================================

def test_shield_replaces_destroy_creature_survives():
    print("\n=== Test: regen shield replaces a destroy (survives) ===")
    game, (p,) = _make_game()
    c = _creature(game, p)
    # Simulate combat + damage so we can confirm the shield clears both.
    c.state.attacking = True
    c.state.damage = 2
    c.state.damage_marked = 2

    shield = make_regeneration_shield(c, game.state)
    assert shield.id in game.state.interceptors
    assert shield.id in c.interceptor_ids

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': c.id, 'reason': 'destroy'}))

    assert _on_battlefield(game, c), "regenerated creature must stay on the battlefield"
    assert c.state.tapped, "regenerated creature must be tapped"
    assert c.state.damage == 0, "regen must remove all marked damage"
    assert c.state.damage_marked == 0, "regen must clear damage_marked"
    assert not c.state.attacking, "regen must remove the creature from combat"
    # Shield is one-shot: consumed after firing once.
    assert shield.id not in game.state.interceptors, "shield must be consumed after one use"
    # A REGENERATE marker event was logged.
    assert any(e.type == EventType.REGENERATE and e.payload.get('object_id') == c.id
               for e in game.state.event_log), "a REGENERATE marker must be logged"
    print("✓ shield replaced the destroy; creature tapped, healed, out of combat, shield consumed")


def test_shield_is_one_shot_second_destroy_kills():
    print("\n=== Test: regen shield is one-shot (second destroy kills) ===")
    game, (p,) = _make_game()
    c = _creature(game, p)
    make_regeneration_shield(c, game.state)

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': c.id, 'reason': 'destroy'}))
    assert _on_battlefield(game, c), "first destroy should be regenerated"

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': c.id, 'reason': 'destroy'}))
    assert not _on_battlefield(game, c), "second destroy must kill (shield was one-shot)"
    assert c.zone == ZoneType.GRAVEYARD, f"expected GRAVEYARD, got {c.zone}"
    print("✓ second destroy killed the creature after the shield was spent")


def test_shield_regenerates_lethal_combat_damage_via_sba():
    print("\n=== Test: regen shield catches lethal damage via SBA ===")
    game, (p,) = _make_game()
    c = _creature(game, p, toughness=3)
    c.state.attacking = True
    c.state.damage = 5  # lethal
    make_regeneration_shield(c, game.state)

    events = game.check_state_based_actions()
    assert _on_battlefield(game, c), "lethal-damage destroy should be regenerated"
    assert c.state.tapped, "regenerated creature must be tapped"
    assert c.state.damage == 0, "regen must clear lethal damage so the SBA can't re-destroy"
    assert not c.state.attacking, "regen must remove from combat"
    assert any(e.type == EventType.REGENERATE for e in events), "SBA destroy should be regenerated"
    print("✓ lethal combat damage regenerated; SBA did not re-destroy")


def test_shield_does_not_replace_sacrifice():
    print("\n=== Test: regen shield does NOT replace a sacrifice ===")
    game, (p,) = _make_game()
    c = _creature(game, p)
    make_regeneration_shield(c, game.state)

    # An OBJECT_DESTROYED with reason 'sacrifice' must fall through the shield.
    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': c.id, 'reason': 'sacrifice'}))
    assert not _on_battlefield(game, c), "regeneration must not stop a sacrifice"
    assert c.zone == ZoneType.GRAVEYARD, f"expected GRAVEYARD, got {c.zone}"
    print("✓ sacrifice killed through the regen shield (correct: regen replaces destroy only)")


def test_no_shield_creature_dies_normally():
    print("\n=== Test: additive discipline — no shield, normal death ===")
    game, (p,) = _make_game()
    c = _creature(game, p)
    # No shield installed.
    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': c.id, 'reason': 'destroy'}))
    assert not _on_battlefield(game, c), "an un-shielded creature must die normally"
    assert c.zone == ZoneType.GRAVEYARD, f"expected GRAVEYARD, got {c.zone}"
    assert not c.state.tapped, "no shield should fire, so no spurious tap"
    print("✓ un-shielded creature dies normally (base behavior unchanged)")


def run_all():
    print("=" * 60)
    print("REGENERATION SHIELD TESTS")
    print("=" * 60)
    test_shield_replaces_destroy_creature_survives()
    test_shield_is_one_shot_second_destroy_kills()
    test_shield_regenerates_lethal_combat_damage_via_sba()
    test_shield_does_not_replace_sacrifice()
    test_no_shield_creature_dies_normally()
    print("\n" + "=" * 60)
    print("ALL REGENERATION TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
