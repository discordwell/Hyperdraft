"""Sweep 11: subtype-add via aura/equipment attach.

Auras / Equipment can grant subtypes to the attached creature. The helpers
mutate ``target.characteristics.subtypes`` directly on ATTACH and revert
on UNATTACH (no QUERY_SUBTYPES yet — the engine reads subtypes directly).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics,
    make_creature,
)
from src.cards.card_factories import make_equipment
from src.cards.interceptor_helpers import (
    make_equipment_setup,
    make_aura_setup,
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


def test_equipment_grants_subtype_on_attach():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    eq_def = make_equipment(
        name="Shaman Tome", mana_cost="{2}",
        text="Equipped creature is a Shaman in addition to its other types.\nEquip {1}",
        equip_cost="{1}",
        setup_interceptors=make_equipment_setup(
            subtypes_to_add={"Shaman"},
            equip_cost="{1}",
        ),
    )

    bear = _spawn(game, p1, creature_def)
    eq = _spawn(game, p1, eq_def)

    assert "Shaman" not in bear.characteristics.subtypes

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': eq.id, 'target_id': bear.id},
        source=eq.id, controller=p1.id,
    ))
    assert "Shaman" in bear.characteristics.subtypes, "Shaman subtype should be added"
    assert "Bear" in bear.characteristics.subtypes, "original Bear should be preserved"

    # Detach — Shaman should be removed.
    game.emit(Event(
        type=EventType.UNATTACH,
        payload={'object_id': eq.id},
        source=eq.id, controller=p1.id,
    ))
    assert "Shaman" not in bear.characteristics.subtypes, "Shaman should be removed on unattach"
    assert "Bear" in bear.characteristics.subtypes
    print("PASS: equipment grants subtype on attach, removes on unattach")


def test_aura_grants_subtype_on_etb_with_target():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, creature_def)

    # Aura with subtypes_to_add — preset target before ETB.
    aura_chars = Characteristics(
        types={CardType.ENCHANTMENT}, subtypes={"Aura"},
        colors={Color.WHITE}, mana_cost="{1}{W}",
    )
    aura_def = CardDefinition(
        name="Angelic Destiny", mana_cost="{1}{W}",
        characteristics=aura_chars,
        text="Enchant creature\nEnchanted creature gets +4/+4 and is an Angel.",
        setup_interceptors=make_aura_setup(
            power_mod=4, toughness_mod=4,
            subtypes_to_add={"Angel"},
        ),
    )
    aura = game.create_object(
        name=aura_def.name, owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=aura_chars, card_def=None,
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

    assert "Angel" in bear.characteristics.subtypes, "aura should add Angel subtype"
    print("PASS: aura grants subtype on ETB with preset target")


if __name__ == "__main__":
    test_equipment_grants_subtype_on_attach()
    test_aura_grants_subtype_on_etb_with_target()
    print("\nAll attach-subtype tests passed!")
