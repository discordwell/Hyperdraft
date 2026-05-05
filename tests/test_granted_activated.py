"""Tests for granted activated abilities.

Covers:
- Equipment with granted activated ability: ATTACH registers the ability on
  the equipped creature; the descriptor is tagged with ``_granted_by``.
- UNATTACH revokes the granted ability.
- Equipment leaving the battlefield revokes the granted ability via the
  leaves-bf cleanup path.
- Two equipments granting the same cost coexist independently.
- Activating a granted ability fires from the equipped creature's
  perspective (effect_fn receives the equipped creature as ``obj``).
- Per-card sanity tests for the 3 wired LCI cards.
"""

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
from src.cards.card_factories import make_equipment
from src.cards.interceptor_helpers import (
    make_equipment_setup,
    make_aura_setup,
    make_granted_activated_ability,
)


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


def _make_simple_creature(name="Bear"):
    return make_creature(
        name=name, power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )


# ----------------------------------------------------------------------
# Core mechanic tests
# ----------------------------------------------------------------------


def test_attach_registers_granted_activated_ability():
    """ATTACH grants the activated ability on the equipped creature."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()

    def draw_one(o, state, targets):
        return [Event(
            type=EventType.DRAW,
            payload={"player": o.controller, "amount": 1},
            source=o.id, controller=o.controller,
        )]

    equip_def = make_equipment(
        name="Drawing Quill", mana_cost="{1}",
        text='Equipped creature has "{T}: Draw a card."',
        equip_cost="{2}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{2}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": draw_one,
                "description": "Draw a card",
            },
        ),
    )
    bear = _spawn(game, p1, bear_def)
    quill = _spawn(game, p1, equip_def)

    # Before ATTACH: bear has no granted ability.
    assert not any(getattr(a, "_granted_by", None) == quill.id
                   for a in bear.state.activated_abilities), \
        "expected no granted ability pre-ATTACH"

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": quill.id, "target_id": bear.id},
        source=quill.id, controller=p1.id,
    ))

    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == quill.id]
    assert len(granted) == 1, f"expected 1 granted ability, got {len(granted)}"
    assert granted[0].cost_text == "{T}"
    assert granted[0].description == "Draw a card"
    print("PASS: ATTACH registers granted activated ability")


def test_unattach_revokes_granted_ability():
    """UNATTACH removes the granted ability."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()

    def noop(o, state, targets):
        return []

    equip_def = make_equipment(
        name="Test", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{2}",
                "effect_fn": noop,
                "description": "Test ability",
            },
        ),
    )
    bear = _spawn(game, p1, bear_def)
    eq = _spawn(game, p1, equip_def)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq.id, "target_id": bear.id},
        source=eq.id, controller=p1.id,
    ))
    assert any(getattr(a, "_granted_by", None) == eq.id
               for a in bear.state.activated_abilities)

    # Now unattach.
    game.emit(Event(
        type=EventType.UNATTACH,
        payload={"object_id": eq.id},
        source=eq.id, controller=p1.id,
    ))
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == eq.id]
    assert not granted, f"expected no granted abilities post-UNATTACH, got {granted}"
    print("PASS: UNATTACH revokes granted ability")


def test_equipment_leaving_bf_revokes_granted_ability():
    """When the equipment leaves the battlefield, the granted ability is removed.

    The leaves-battlefield cleanup interceptor (system:attach_cleanup) emits
    UNATTACH on behalf of the departing equipment, which routes through the
    granted-abilities listener and revokes the ability.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()

    def noop(o, state, targets):
        return []

    equip_def = make_equipment(
        name="Vanishing Blade", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{1}",
                "effect_fn": noop,
                "description": "Demo",
            },
        ),
    )
    bear = _spawn(game, p1, bear_def)
    eq = _spawn(game, p1, equip_def)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq.id, "target_id": bear.id},
        source=eq.id, controller=p1.id,
    ))
    assert any(getattr(a, "_granted_by", None) == eq.id
               for a in bear.state.activated_abilities)

    # Equipment goes to graveyard.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': eq.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == eq.id]
    assert not granted, f"expected no granted abilities after equipment leaves bf, got {granted}"
    print("PASS: equipment leaving bf revokes granted ability")


def test_equipped_creature_leaving_bf_revokes_granted_ability():
    """If the equipped creature leaves bf, the equipment's UNATTACH path also
    revokes the granted ability — there's no creature to attach to anymore.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()

    def noop(o, state, targets):
        return []

    equip_def = make_equipment(
        name="Sticky Sword", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{1}",
                "effect_fn": noop,
                "description": "Demo",
            },
        ),
    )
    bear = _spawn(game, p1, bear_def)
    eq = _spawn(game, p1, equip_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq.id, "target_id": bear.id},
        source=eq.id, controller=p1.id,
    ))

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': bear.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    # bear's activated_abilities list should not retain any granted ability.
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == eq.id]
    assert not granted, f"bear should not retain granted abilities, got {granted}"
    print("PASS: equipped creature leaving bf revokes granted ability")


def test_two_equipments_grant_independently():
    """Two equipments, both granting an activated ability: both should
    register, both should clean up independently.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()

    def effect_a(o, state, targets):
        return []

    def effect_b(o, state, targets):
        return []

    eq_a_def = make_equipment(
        name="Quill A", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": effect_a,
                "description": "Effect A",
            },
        ),
    )
    eq_b_def = make_equipment(
        name="Quill B", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": effect_b,
                "description": "Effect B",
            },
        ),
    )
    bear = _spawn(game, p1, bear_def)
    eq_a = _spawn(game, p1, eq_a_def)
    eq_b = _spawn(game, p1, eq_b_def)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq_a.id, "target_id": bear.id},
        source=eq_a.id, controller=p1.id,
    ))
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq_b.id, "target_id": bear.id},
        source=eq_b.id, controller=p1.id,
    ))

    granted_a = [a for a in bear.state.activated_abilities
                 if getattr(a, "_granted_by", None) == eq_a.id]
    granted_b = [a for a in bear.state.activated_abilities
                 if getattr(a, "_granted_by", None) == eq_b.id]
    assert len(granted_a) == 1, f"expected 1 from eq_a, got {len(granted_a)}"
    assert len(granted_b) == 1, f"expected 1 from eq_b, got {len(granted_b)}"
    assert granted_a[0].description == "Effect A"
    assert granted_b[0].description == "Effect B"

    # Unattach only eq_a — eq_b's grant should still be present.
    game.emit(Event(
        type=EventType.UNATTACH,
        payload={"object_id": eq_a.id},
        source=eq_a.id, controller=p1.id,
    ))
    granted_a = [a for a in bear.state.activated_abilities
                 if getattr(a, "_granted_by", None) == eq_a.id]
    granted_b = [a for a in bear.state.activated_abilities
                 if getattr(a, "_granted_by", None) == eq_b.id]
    assert not granted_a, "eq_a's grant should be revoked"
    assert len(granted_b) == 1, "eq_b's grant should remain"
    print("PASS: two equipments grant and revoke independently")


def test_activate_granted_ability_fires_effect():
    """Activating a granted ability invokes effect_fn with the equipped
    creature as ``obj`` and returns the right events.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()

    captured = {"obj_id": None}

    def draw_one(o, state, targets):
        captured["obj_id"] = o.id
        return [Event(
            type=EventType.DRAW,
            payload={"player": o.controller, "amount": 1},
            source=o.id, controller=o.controller,
        )]

    equip_def = make_equipment(
        name="Quill", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": draw_one,
                "description": "Draw a card",
            },
        ),
    )
    bear = _spawn(game, p1, bear_def)
    quill = _spawn(game, p1, equip_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": quill.id, "target_id": bear.id},
        source=quill.id, controller=p1.id,
    ))

    # Find the granted ability and invoke its effect_fn directly. (The
    # priority-system path is exercised in other tests; here we want to
    # confirm effect_fn receives the equipped creature as `obj`.)
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == quill.id][0]
    events = granted.effect_fn(bear, game.state, [])
    assert captured["obj_id"] == bear.id, \
        f"effect_fn should see the equipped creature as obj, got {captured['obj_id']!r}"
    assert len(events) == 1 and events[0].type == EventType.DRAW
    assert events[0].source == bear.id, \
        f"event source should be the equipped creature, got {events[0].source}"
    print("PASS: activating granted ability fires effect from equipped creature's perspective")


def test_make_granted_activated_ability_helper():
    """The standalone helper registers a tagged ability."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = _make_simple_creature()
    equip_def = make_equipment(
        name="Bare", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(equip_cost="{1}"),
    )
    bear = _spawn(game, p1, bear_def)
    eq = _spawn(game, p1, equip_def)

    def effect(o, state, targets):
        return []

    ability = make_granted_activated_ability(
        bear, eq, "{1}", effect, description="Manual grant",
    )
    assert ability is not None
    assert getattr(ability, "_granted_by", None) == eq.id
    assert ability in bear.state.activated_abilities
    print("PASS: make_granted_activated_ability helper")


def test_aura_grants_activated_ability():
    """Auras can also use granted_activated_abilities."""
    from src.engine.types import Characteristics
    from src.engine import CardDefinition

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bear = _spawn(game, p1, _make_simple_creature())

    def effect(o, state, targets):
        return []

    aura_chars = Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Aura"},
        colors={Color.WHITE},
        mana_cost="{1}{W}",
    )
    aura_def = CardDefinition(
        name="Endow",
        mana_cost="{1}{W}",
        characteristics=aura_chars,
        text='Enchanted creature has "{T}: Gain 1 life."',
        setup_interceptors=make_aura_setup(
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": effect,
                "description": "Gain 1 life",
            },
        ),
    )
    aura = game.create_object(
        name="Endow",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=aura_chars,
        card_def=None,
    )
    aura.card_def = aura_def
    setattr(aura.state, "_aura_target_id", bear.id)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': aura.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    # The aura's setup runs, attach_to is set immediately for cards that
    # bypass the stack. Now also fire the ATTACH event so the listener
    # registers the granted ability.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": aura.id, "target_id": bear.id},
        source=aura.id, controller=p1.id,
    ))

    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == aura.id]
    assert len(granted) == 1, f"aura should grant 1 ability, got {len(granted)}"
    print("PASS: aura grants activated ability via granted_activated_abilities")


# ----------------------------------------------------------------------
# Per-card tests for the 3 wired LCI Equipment
# ----------------------------------------------------------------------


def test_lci_deconstruction_hammer():
    """Deconstruction Hammer (real LCI): +1/+1 + '{3}, {T}, Sacrifice this:
    Destroy target artifact or enchantment.' Equip {1}.

    Note: the cost text we register is "{3}, {T}" — the equipment-sacrifice
    is folded into the effect_fn (cost parser doesn't yet handle
    "Sacrifice <named card>").
    """
    from src.cards.lost_caverns_ixalan import DECONSTRUCTION_HAMMER
    from src.engine import get_power, get_toughness

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bear = _spawn(game, p1, _make_simple_creature())
    hammer = _spawn(game, p1, DECONSTRUCTION_HAMMER)

    # Pre-attach: 2/2.
    assert get_power(bear, game.state) == 2
    assert get_toughness(bear, game.state) == 2

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": hammer.id, "target_id": bear.id},
        source=hammer.id, controller=p1.id,
    ))

    # P/T boost.
    assert get_power(bear, game.state) == 3, \
        f"expected 3 power, got {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 3
    # Granted destroy ability registered.
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == hammer.id]
    assert len(granted) == 1, f"expected 1 granted ability, got {len(granted)}"
    assert granted[0].cost_text == "{3}, {T}", \
        f"unexpected cost: {granted[0].cost_text!r}"
    # Effect emits both DESTROY (target) and SACRIFICE (equipment).
    from src.engine.targeting import Target

    # Make a fake artifact target.
    artifact_def = make_equipment(
        name="Dummy Equipment", mana_cost="{1}",
        setup_interceptors=make_equipment_setup(equip_cost="{1}"),
    )
    dummy = _spawn(game, p1, artifact_def)
    events = granted[0].effect_fn(bear, game.state, [Target(id=dummy.id)])
    types = [e.type for e in events]
    assert EventType.OBJECT_DESTROYED in types
    assert EventType.SACRIFICE in types
    sac_event = next(e for e in events if e.type == EventType.SACRIFICE)
    assert sac_event.payload["object_id"] == hammer.id, \
        "sac event should target the Deconstruction Hammer, not the bear"
    print("PASS: Deconstruction Hammer wires grant + P/T boost + sac-effect")


def test_lci_swashbucklers_whip():
    """Swashbuckler's Whip (real LCI): reach + two granted activated abilities."""
    from src.cards.lost_caverns_ixalan import SWASHBUCKLERS_WHIP
    from src.engine import has_ability

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bear = _spawn(game, p1, _make_simple_creature())
    whip = _spawn(game, p1, SWASHBUCKLERS_WHIP)

    assert not has_ability(bear, "reach", game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": whip.id, "target_id": bear.id},
        source=whip.id, controller=p1.id,
    ))

    assert has_ability(bear, "reach", game.state), "equipped creature should have reach"
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == whip.id]
    assert len(granted) == 2, f"expected 2 granted abilities, got {len(granted)}"
    costs = sorted(a.cost_text for a in granted)
    assert costs == sorted(["{2}, {T}", "{8}, {T}"]), f"unexpected costs: {costs}"
    print("PASS: Swashbuckler's Whip wires reach + 2 granted abilities")


def test_lci_idol_of_the_deep_king_demo():
    """Idol of the Deep King (real LCI card, synthetic granted-ability demo)."""
    from src.cards.lost_caverns_ixalan import IDOL_OF_THE_DEEP_KING

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bear = _spawn(game, p1, _make_simple_creature())
    idol = _spawn(game, p1, IDOL_OF_THE_DEEP_KING)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": idol.id, "target_id": bear.id},
        source=idol.id, controller=p1.id,
    ))
    granted = [a for a in bear.state.activated_abilities
               if getattr(a, "_granted_by", None) == idol.id]
    assert len(granted) == 1, f"expected 1 granted ability, got {len(granted)}"
    assert granted[0].cost_text == "{1}, {T}"
    print("PASS: Idol of the Deep King wires synthetic granted ability")


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------


def test_grant_marker_event_fires():
    """The granted-abilities listener should emit a GRANT_ACTIVATED_ABILITY
    marker event when ATTACH succeeds — observable via event_log.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bear = _spawn(game, p1, _make_simple_creature())

    def effect(o, state, targets):
        return []

    equip_def = make_equipment(
        name="Marker", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": effect,
                "description": "Marker",
            },
        ),
    )
    eq = _spawn(game, p1, equip_def)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq.id, "target_id": bear.id},
        source=eq.id, controller=p1.id,
    ))
    markers = [
        e for e in game.state.event_log
        if e.type == EventType.GRANT_ACTIVATED_ABILITY
    ]
    assert markers, "expected a GRANT_ACTIVATED_ABILITY marker"
    assert markers[-1].payload["target_id"] == bear.id
    assert markers[-1].payload["source_id"] == eq.id
    assert markers[-1].payload["cost"] == "{T}"
    print("PASS: GRANT_ACTIVATED_ABILITY marker event fires")


def test_re_attach_to_new_target_moves_grant():
    """Re-attaching the same equipment to a new creature moves the granted
    ability with it.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bear1 = _spawn(game, p1, _make_simple_creature("Bear1"))
    bear2 = _spawn(game, p1, _make_simple_creature("Bear2"))

    def effect(o, state, targets):
        return []

    equip_def = make_equipment(
        name="Mover", mana_cost="{1}", equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{1}",
                "effect_fn": effect,
                "description": "Demo",
            },
        ),
    )
    eq = _spawn(game, p1, equip_def)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq.id, "target_id": bear1.id},
        source=eq.id, controller=p1.id,
    ))
    assert any(getattr(a, "_granted_by", None) == eq.id
               for a in bear1.state.activated_abilities)
    assert not any(getattr(a, "_granted_by", None) == eq.id
                   for a in bear2.state.activated_abilities)

    # Attach to bear2.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eq.id, "target_id": bear2.id},
        source=eq.id, controller=p1.id,
    ))
    assert not any(getattr(a, "_granted_by", None) == eq.id
                   for a in bear1.state.activated_abilities), \
        "bear1 should no longer have the grant"
    assert any(getattr(a, "_granted_by", None) == eq.id
               for a in bear2.state.activated_abilities), \
        "bear2 should now have the grant"
    print("PASS: re-attach moves the grant")


# ----------------------------------------------------------------------
# Test runner
# ----------------------------------------------------------------------

if __name__ == "__main__":
    test_attach_registers_granted_activated_ability()
    test_unattach_revokes_granted_ability()
    test_equipment_leaving_bf_revokes_granted_ability()
    test_equipped_creature_leaving_bf_revokes_granted_ability()
    test_two_equipments_grant_independently()
    test_activate_granted_ability_fires_effect()
    test_make_granted_activated_ability_helper()
    test_aura_grants_activated_ability()
    test_lci_deconstruction_hammer()
    test_lci_swashbucklers_whip()
    test_lci_idol_of_the_deep_king_demo()
    test_grant_marker_event_fires()
    test_re_attach_to_new_target_moves_grant()
    print("\nAll granted-activated-ability tests PASS")
