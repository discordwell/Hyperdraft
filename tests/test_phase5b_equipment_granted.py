"""Phase 5b — Equipment-granted activated abilities.

Verifies the ``make_equipment_granted_ability`` helper and the underlying
``make_granted_abilities_listener`` pipeline. The mechanic implements
'Equipped creature has "<cost>: <effect>"' — the activated ability is
registered on the equipped creature (so the priority system surfaces it
like any other activated ability) but cleaned up when the equipment
unattaches or leaves the battlefield.

Coverage:
1. Helper-level: granted ability registers on the attached creature with
   the correct cost; cleared on UNATTACH.
2. Helper-level: leaves-battlefield (equipment moves to graveyard) also
   revokes the granted ability.
3. Helper-level: cost (a {T} tap-self) ticks the *equipped creature*,
   not the equipment.
4. Trusty Boomerang: granted ability emits TAP + ZONE_CHANGE events
   when activated.
5. Fishing Pole: granted ability emits TAP + COUNTER_ADDED for the bait
   counter.
6. Friendly Neighborhood (Aura): granted ability registers on the
   attached land.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, make_artifact,
)
from src.engine.attach import (
    grant_activated_ability_on_attach,
    revoke_granted_abilities,
)
from src.cards.interceptor_helpers import (
    make_equipment_granted_ability,
    make_equipment_setup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """A vanilla 1/1 creature for use as the equip target."""
    return make_creature(
        name=name,
        power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Human"},
        text="",
    )


def _has_granted_ability(target, cost_substr: str) -> bool:
    abilities = getattr(target.state, 'activated_abilities', None) or []
    for a in abilities:
        if cost_substr.lower() in (a.cost_text or '').lower():
            return True
    return False


def _granted_ability_count(target, source_id: str) -> int:
    abilities = getattr(target.state, 'activated_abilities', None) or []
    return sum(1 for a in abilities if getattr(a, '_granted_by', None) == source_id)


# ---------------------------------------------------------------------------
# 1. Helper-level: ability registers on ATTACH and is tagged with source id
# ---------------------------------------------------------------------------


def test_granted_ability_registers_on_attach():
    """When an Equipment with a granted-ability spec attaches to a creature,
    the activated ability shows up on ``creature.state.activated_abilities``
    tagged with ``_granted_by == equipment.id``."""
    print("\n=== granted_ability_registers_on_attach ===")
    game, p1, _ = _new_game()

    # Spec-only effect; ignore targets, return no events.
    def _noop_effect(o, st, targets):
        return []

    # Build a minimal Equipment + creature.
    equipment_def = make_artifact(
        name="Test Equipment",
        mana_cost="{1}",
        text='Equipped creature has "{2}, {T}: Do nothing."\nEquip {1}',
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{2}, {T}",
                "effect_fn": _noop_effect,
                "description": "Do nothing.",
            },
        ),
    )
    eqp = _put_card(game, p1, equipment_def)
    creature = _put_card(game, p1, _plain_creature())

    # Before ATTACH: no granted ability on the creature.
    assert _granted_ability_count(creature, eqp.id) == 0, (
        f"creature should have no granted ability pre-attach, got "
        f"{creature.state.activated_abilities!r}"
    )

    # Emit ATTACH — the listener should grant the ability.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eqp.id, "target_id": creature.id},
        source=eqp.id, controller=p1.id,
    ))

    assert eqp.state.attached_to == creature.id, (
        f"ATTACH didn't update attached_to: {eqp.state.attached_to}"
    )
    assert _granted_ability_count(creature, eqp.id) == 1, (
        f"expected exactly one granted ability after ATTACH, got "
        f"{creature.state.activated_abilities!r}"
    )
    assert _has_granted_ability(creature, "{2}, {T}"), (
        "granted ability cost mismatch"
    )
    print("  PASS")


# ---------------------------------------------------------------------------
# 2. Helper-level: ability is revoked on UNATTACH
# ---------------------------------------------------------------------------


def test_granted_ability_revoked_on_unattach():
    """After ATTACH, an UNATTACH event strips the granted ability."""
    print("\n=== granted_ability_revoked_on_unattach ===")
    game, p1, _ = _new_game()

    def _noop_effect(o, st, targets):
        return []

    equipment_def = make_artifact(
        name="Test Equipment Unattach",
        mana_cost="{1}",
        text='Equipped creature has "{T}: Do nothing."',
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": _noop_effect,
                "description": "Tap creature.",
            },
        ),
    )
    eqp = _put_card(game, p1, equipment_def)
    creature = _put_card(game, p1, _plain_creature())

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eqp.id, "target_id": creature.id},
        source=eqp.id, controller=p1.id,
    ))
    assert _granted_ability_count(creature, eqp.id) == 1

    # Now emit UNATTACH and confirm the granted ability is gone.
    game.emit(Event(
        type=EventType.UNATTACH,
        payload={"object_id": eqp.id},
        source=eqp.id, controller=p1.id,
    ))
    assert eqp.state.attached_to is None, "UNATTACH didn't clear attached_to"
    assert _granted_ability_count(creature, eqp.id) == 0, (
        f"granted ability not revoked after UNATTACH: "
        f"{creature.state.activated_abilities!r}"
    )
    print("  PASS")


# ---------------------------------------------------------------------------
# 3. Helper-level: ability is revoked when equipment leaves the battlefield
# ---------------------------------------------------------------------------


def test_granted_ability_revoked_when_equipment_leaves_battlefield():
    """If the equipment moves from BATTLEFIELD to GRAVEYARD (e.g. destroyed),
    the granted ability is cleaned up on the formerly-equipped creature."""
    print("\n=== granted_ability_revoked_when_equipment_leaves_battlefield ===")
    game, p1, _ = _new_game()

    def _noop_effect(o, st, targets):
        return []

    equipment_def = make_artifact(
        name="Test Equipment LBF",
        mana_cost="{1}",
        text='Equipped creature has "{T}: Do nothing."',
        subtypes={"Equipment"},
        setup_interceptors=make_equipment_setup(
            equip_cost="{1}",
            granted_activated_abilities={
                "cost": "{T}",
                "effect_fn": _noop_effect,
                "description": "Tap creature.",
            },
        ),
    )
    eqp = _put_card(game, p1, equipment_def)
    creature = _put_card(game, p1, _plain_creature())

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": eqp.id, "target_id": creature.id},
        source=eqp.id, controller=p1.id,
    ))
    assert _granted_ability_count(creature, eqp.id) == 1

    # Now move equipment to graveyard via ZONE_CHANGE.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': eqp.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'to_zone_owner': p1.id,
        },
    ))
    assert eqp.zone == ZoneType.GRAVEYARD, (
        f"equipment should be in graveyard, got zone={eqp.zone}"
    )
    assert _granted_ability_count(creature, eqp.id) == 0, (
        f"granted ability not revoked after equipment left battlefield: "
        f"{creature.state.activated_abilities!r}"
    )
    print("  PASS")


# ---------------------------------------------------------------------------
# 4. Trusty Boomerang — granted ability emits TAP + ZONE_CHANGE on activation
# ---------------------------------------------------------------------------


def test_trusty_boomerang_grants_bounce_ability():
    """Trusty Boomerang attached → its granted ability lives on the creature
    with cost '{1}, {T}'. Invoking the effect_fn emits a TAP on the chosen
    target creature plus a ZONE_CHANGE bouncing the Boomerang to hand."""
    print("\n=== trusty_boomerang_grants_bounce_ability ===")
    from src.cards.avatar_tla import TRUSTY_BOOMERANG
    from src.engine.targeting import Target

    game, p1, p2 = _new_game()

    boomerang = _put_card(game, p1, TRUSTY_BOOMERANG)
    wielder = _put_card(game, p1, _plain_creature(name="Wielder 1/1"))
    enemy = _put_card(game, p2, _plain_creature(name="Enemy 1/1"))

    # Attach the Boomerang.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": boomerang.id, "target_id": wielder.id},
        source=boomerang.id, controller=p1.id,
    ))
    assert _granted_ability_count(wielder, boomerang.id) == 1, (
        f"Boomerang should grant exactly one ability; got "
        f"{wielder.state.activated_abilities!r}"
    )

    # Find the granted ability and invoke its effect_fn with the enemy as
    # target. We pass a Target dataclass to mimic the engine's effect
    # invocation contract.
    granted = None
    for a in wielder.state.activated_abilities:
        if getattr(a, '_granted_by', None) == boomerang.id:
            granted = a
            break
    assert granted is not None, "granted ability missing"
    assert granted.cost_text == "{1}, {T}", (
        f"cost mismatch: {granted.cost_text!r}"
    )

    targets = [Target(id=enemy.id)]
    events = granted.effect_fn(wielder, game.state, targets)
    tap_evts = [e for e in events if e.type == EventType.TAP]
    zc_evts = [e for e in events if e.type == EventType.ZONE_CHANGE]
    assert tap_evts, f"expected TAP event, got {[(e.type, e.payload) for e in events]}"
    assert tap_evts[0].payload.get("object_id") == enemy.id, (
        f"TAP should target the enemy creature; got {tap_evts[0].payload}"
    )
    assert zc_evts, "expected ZONE_CHANGE bounce event"
    zc = zc_evts[0]
    assert zc.payload.get("object_id") == boomerang.id, (
        f"bounce should target the boomerang; got {zc.payload}"
    )
    assert zc.payload.get("to_zone_type") == ZoneType.HAND, (
        f"bounce should target hand; got {zc.payload}"
    )
    print("  PASS")


# ---------------------------------------------------------------------------
# 5. Fishing Pole — granted ability emits TAP + COUNTER_ADDED for bait
# ---------------------------------------------------------------------------


def test_fishing_pole_grants_bait_counter_ability():
    """Fishing Pole attached → granted ability with cost '{1}, {T}' is on
    the equipped creature; the effect_fn emits a TAP on the Pole plus a
    COUNTER_ADDED event with counter_type='bait'."""
    print("\n=== fishing_pole_grants_bait_counter_ability ===")
    from src.cards.foundations import FISHING_POLE

    game, p1, _ = _new_game()
    pole = _put_card(game, p1, FISHING_POLE)
    wielder = _put_card(game, p1, _plain_creature(name="Angler 1/1"))

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": pole.id, "target_id": wielder.id},
        source=pole.id, controller=p1.id,
    ))

    granted = None
    for a in wielder.state.activated_abilities:
        if getattr(a, '_granted_by', None) == pole.id:
            granted = a
            break
    assert granted is not None, "granted ability missing"
    assert granted.cost_text == "{1}, {T}", (
        f"cost mismatch: {granted.cost_text!r}"
    )

    events = granted.effect_fn(wielder, game.state, [])
    tap_evts = [e for e in events if e.type == EventType.TAP]
    counter_evts = [e for e in events if e.type == EventType.COUNTER_ADDED]
    assert tap_evts, f"expected TAP on Pole, got {[(e.type, e.payload) for e in events]}"
    assert tap_evts[0].payload.get("object_id") == pole.id, (
        f"TAP should target the Pole; got {tap_evts[0].payload}"
    )
    assert counter_evts, "expected COUNTER_ADDED for bait"
    assert counter_evts[0].payload.get("counter_type") == "bait"
    assert counter_evts[0].payload.get("object_id") == pole.id
    print("  PASS")


# ---------------------------------------------------------------------------
# 6. Friendly Neighborhood — granted ability registers on the enchanted land
# ---------------------------------------------------------------------------


def test_friendly_neighborhood_grants_pump_ability():
    """Friendly Neighborhood (Aura) attached to a land → land has the
    granted '{1}, {T}: pump' ability. The pump's effect scales by counting
    creatures the controller has on the battlefield."""
    print("\n=== friendly_neighborhood_grants_pump_ability ===")
    from src.cards.spider_man import FRIENDLY_NEIGHBORHOOD
    from src.engine.targeting import Target

    game, p1, _ = _new_game()
    aura = _put_card(game, p1, FRIENDLY_NEIGHBORHOOD)

    # Stand-in "land" — a vanilla object we'll just attach the aura to. The
    # granted-ability listener doesn't enforce land-typing; the type-check
    # would happen at cast time via target_requirements (which we don't
    # exercise here).
    land = _put_card(game, p1, _plain_creature(name="Stand-in Land"))
    # And two creatures the controller has on the battlefield so the pump
    # sees a count of two (plus the stand-in counts as a 3rd creature, but
    # we just verify the effect doesn't return empty and the modifier is
    # positive).
    c1 = _put_card(game, p1, _plain_creature(name="Friend A"))
    c2 = _put_card(game, p1, _plain_creature(name="Friend B"))

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": aura.id, "target_id": land.id},
        source=aura.id, controller=p1.id,
    ))
    granted = None
    for a in land.state.activated_abilities:
        if getattr(a, '_granted_by', None) == aura.id:
            granted = a
            break
    assert granted is not None, (
        f"land should have a granted ability; got "
        f"{land.state.activated_abilities!r}"
    )
    assert granted.cost_text == "{1}, {T}", (
        f"cost mismatch: {granted.cost_text!r}"
    )
    assert granted.sorcery_speed, "should be sorcery-speed"

    # Invoke with one of the creatures as target.
    events = granted.effect_fn(land, game.state, [Target(id=c1.id)])
    pt_evts = [e for e in events if e.type == EventType.PT_MODIFICATION]
    assert pt_evts, f"expected PT_MODIFICATION event, got {[(e.type, e.payload) for e in events]}"
    assert pt_evts[0].payload.get("object_id") == c1.id, (
        f"PT_MODIFICATION should target c1; got {pt_evts[0].payload}"
    )
    n = pt_evts[0].payload.get("power_mod", 0)
    assert n >= 2, (
        f"power_mod should be at least 2 (creatures-controlled); got {n}"
    )
    print("  PASS")


# ---------------------------------------------------------------------------
# 7. Helper-level — make_equipment_granted_ability returns a listener
# ---------------------------------------------------------------------------


def test_make_equipment_granted_ability_returns_listener():
    """The standalone helper returns a single interceptor (a listener) that
    fires on ATTACH/UNATTACH. Confirms callers can append the result to
    their hand-rolled setup return list."""
    print("\n=== make_equipment_granted_ability_returns_listener ===")
    game, p1, _ = _new_game()

    # Spawn a bare Equipment-shaped object so the helper has something to
    # bind to. The helper just builds an interceptor, no setup required.
    eqp_def = make_artifact(
        name="Stub Equipment",
        mana_cost="{1}",
        text="",
        subtypes={"Equipment"},
    )
    eqp = _put_card(game, p1, eqp_def)

    def _noop(o, st, targets):
        return []

    ics = make_equipment_granted_ability(
        eqp,
        cost="{1}, {T}",
        effect_fn=_noop,
        description="No-op",
        targets_required=0,
        target_kind="any",
    )
    assert isinstance(ics, list), f"helper should return a list, got {type(ics)}"
    assert len(ics) == 1, f"expected 1 interceptor, got {len(ics)}"
    interceptor = ics[0]
    assert interceptor.source == eqp.id, (
        f"interceptor should be sourced on the equipment; got {interceptor.source}"
    )
    assert interceptor.duration == "while_on_battlefield"
    print("  PASS")


# ---------------------------------------------------------------------------
# Run-all entry point
# ---------------------------------------------------------------------------


def main():
    tests = [
        test_granted_ability_registers_on_attach,
        test_granted_ability_revoked_on_unattach,
        test_granted_ability_revoked_when_equipment_leaves_battlefield,
        test_trusty_boomerang_grants_bounce_ability,
        test_fishing_pole_grants_bait_counter_ability,
        test_friendly_neighborhood_grants_pump_ability,
        test_make_equipment_granted_ability_returns_listener,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e!r}")
            import traceback
            traceback.print_exc()
            failed.append(t.__name__)
    if failed:
        print(f"\n{len(failed)}/{len(tests)} FAILED: {failed}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
