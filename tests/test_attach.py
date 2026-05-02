"""Phase 3: tests for the equipment / aura attach mechanic.

Covers:
- ATTACH event sets attached_to + appends to host's attachments list
- ATTACH from one host to another emits a follow-up UNATTACH
- UNATTACH clears attached_to and removes from host's attachments
- Equipment static P/T boost flows through QUERY_POWER + QUERY_TOUGHNESS
- Equipment keyword grant flows through QUERY_ABILITIES (has_keyword)
- Equip activated ability: sorcery-speed, emits ATTACH on activation
- Leaves-battlefield cleanup unattaches an equipment when the host dies
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
    make_creature, get_power, get_toughness, has_ability,
)
from src.cards.card_factories import make_equipment
from src.cards.interceptor_helpers import (
    make_equipment_setup,
    make_aura_setup,
    attach_aura_to_target,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase


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


def test_attach_event_sets_state():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    equip = make_equipment(
        name="Belt", mana_cost="{1}", text="Equipped creature gets +1/+1.\nEquip {2}",
        equip_cost="{2}",
        setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{2}"),
    )
    bear = _spawn(game, p1, creature)
    belt = _spawn(game, p1, equip)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": belt.id, "target_id": bear.id},
        source=belt.id, controller=p1.id,
    ))

    assert belt.state.attached_to == bear.id, f"expected attached_to={bear.id}, got {belt.state.attached_to}"
    assert belt.id in bear.state.attachments, f"expected {belt.id} in attachments, got {bear.state.attachments}"
    print("PASS: attach event sets state")


def test_attach_to_new_host_emits_unattach():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    equip_def = make_equipment(
        name="Belt", mana_cost="{1}", text="Equip {2}", equip_cost="{2}",
        setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{2}"),
    )
    bear1 = _spawn(game, p1, creature_def)
    bear2 = _spawn(game, p1, creature_def)
    belt = _spawn(game, p1, equip_def)

    # Attach to bear1.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": belt.id, "target_id": bear1.id},
        source=belt.id, controller=p1.id,
    ))
    assert belt.state.attached_to == bear1.id
    # Re-attach to bear2 — bear1 should no longer have belt in attachments.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": belt.id, "target_id": bear2.id},
        source=belt.id, controller=p1.id,
    ))
    assert belt.state.attached_to == bear2.id
    assert belt.id in bear2.state.attachments
    assert belt.id not in bear1.state.attachments, f"belt should be off bear1: {bear1.state.attachments}"
    print("PASS: attach to new host emits unattach")


def test_pt_boost_flows_through_query_power():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    equip_def = make_equipment(
        name="Belt", mana_cost="{1}", text="Equipped creature gets +1/+1.\nEquip {2}",
        equip_cost="{2}",
        setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{2}"),
    )
    bear = _spawn(game, p1, creature_def)
    belt = _spawn(game, p1, equip_def)

    # Before attach: 2/2.
    assert get_power(bear, game.state) == 2, f"unboosted power: {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 2

    # Attach.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": belt.id, "target_id": bear.id},
        source=belt.id, controller=p1.id,
    ))

    # After attach: 3/3.
    assert get_power(bear, game.state) == 3, f"boosted power should be 3, got {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 3, f"boosted toughness should be 3, got {get_toughness(bear, game.state)}"
    print("PASS: P/T boost flows through QUERY_POWER")


def test_keyword_grant_flows_through_query_abilities():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    equip_def = make_equipment(
        name="Wing", mana_cost="{1}", text="Equipped creature has flying.\nEquip {1}",
        equip_cost="{1}",
        setup_interceptors=make_equipment_setup(keywords=["flying"], equip_cost="{1}"),
    )
    bear = _spawn(game, p1, creature_def)
    wing = _spawn(game, p1, equip_def)

    # Before attach: no flying.
    assert not has_ability(bear, "flying", game.state), "unattached creature should not fly"

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": wing.id, "target_id": bear.id},
        source=wing.id, controller=p1.id,
    ))

    assert has_ability(bear, "flying", game.state), "attached creature should fly"
    print("PASS: keyword grant flows through QUERY_ABILITIES")


def test_equip_ability_is_sorcery_speed():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Bob's turn — equip should not be activatable.
    game.turn_manager.turn_state.active_player_id = p2.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    equip_def = make_equipment(
        name="Belt", mana_cost="{1}", text="Equip {2}", equip_cost="{2}",
        setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{2}"),
    )
    bear = _spawn(game, p1, creature_def)
    belt = _spawn(game, p1, equip_def)
    belt.state.summoning_sickness = False

    # Provide mana.
    from src.engine.mana import ManaType
    for _ in range(2):
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 1)

    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.source_id == belt.id and a.ability_id and a.ability_id.startswith("activated:")]
    assert not matches, f"sorcery-speed equip should not appear on opponent's turn, got: {[a.description for a in matches]}"
    print("PASS: equip ability is sorcery-speed")


def test_equip_ability_emits_attach():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        creature_def = make_creature(
            name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
            colors={Color.GREEN}, subtypes={"Bear"}, text="",
        )
        equip_def = make_equipment(
            name="Belt", mana_cost="{1}", text="Equip {2}", equip_cost="{2}",
            setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{2}"),
        )
        bear = _spawn(game, p1, creature_def)
        belt = _spawn(game, p1, equip_def)
        belt.state.summoning_sickness = False

        from src.engine.mana import ManaType
        for _ in range(2):
            game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 1)

        # Pre-select target via action.targets.
        from src.engine.targeting import Target
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=belt.id,
            ability_id="activated:0",
            targets=[[Target(id=bear.id)]],
        )
        events = await game.priority_system._handle_activate_ability(action)
        # Stack item should resolve to ATTACH.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        types = [e.type for e in resolved]
        assert EventType.ATTACH in types, f"expected ATTACH from resolve, got {types}"
        print("PASS: equip ability emits ATTACH on resolve")

    asyncio.get_event_loop().run_until_complete(_run())


def test_leaves_battlefield_unattaches():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    equip_def = make_equipment(
        name="Belt", mana_cost="{1}", text="Equip {2}", equip_cost="{2}",
        setup_interceptors=make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{2}"),
    )
    bear = _spawn(game, p1, creature_def)
    belt = _spawn(game, p1, equip_def)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={"object_id": belt.id, "target_id": bear.id},
        source=belt.id, controller=p1.id,
    ))
    assert belt.state.attached_to == bear.id
    assert belt.id in bear.state.attachments

    # Bear leaves the battlefield (destroyed).
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

    assert belt.state.attached_to is None, f"belt should be detached, got {belt.state.attached_to}"
    print("PASS: leaves-battlefield unattaches")


def test_aura_setup_attaches_and_boosts():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    creature_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, creature_def)

    # Build an aura object directly. We pre-set _aura_target_id before
    # the setup runs; this mirrors the resolve flow that decides target.
    from src.engine.types import Characteristics
    aura_chars = Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Aura"},
        colors={Color.WHITE},
        mana_cost="{1}{W}",
    )
    from src.engine import CardDefinition
    aura_def = CardDefinition(
        name="Holy Strength",
        mana_cost="{1}{W}",
        characteristics=aura_chars,
        text="Enchant creature\nEnchanted creature gets +1/+2.",
        setup_interceptors=make_aura_setup(power_mod=1, toughness_mod=2),
    )

    aura = game.create_object(
        name="Holy Strength",
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

    assert aura.state.attached_to == bear.id, f"aura should be attached to bear, got {aura.state.attached_to}"
    assert get_power(bear, game.state) == 3, f"bear should be 3 power, got {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 4, f"bear should be 4 toughness, got {get_toughness(bear, game.state)}"
    print("PASS: aura setup attaches and boosts")


if __name__ == "__main__":
    test_attach_event_sets_state()
    test_attach_to_new_host_emits_unattach()
    test_pt_boost_flows_through_query_power()
    test_keyword_grant_flows_through_query_abilities()
    test_equip_ability_is_sorcery_speed()
    test_equip_ability_emits_attach()
    test_leaves_battlefield_unattaches()
    test_aura_setup_attaches_and_boosts()
    print("\nAll Phase 3 tests passed!")
