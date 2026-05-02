"""Sweep 1: dynamic P/T boost framework tests.

Covers:
- make_dynamic_pt_boost reflects state changes (Forest count etc.)
- make_attached_dynamic_pt_boost honors attached_to (Blanchwood Armor pattern)
- Boost recomputes on each query
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics, get_power, get_toughness,
)
from src.cards.interceptor_helpers import (
    make_dynamic_pt_boost,
    make_attached_dynamic_pt_boost,
    count_permanents_with_subtype,
    count_cards_in_hand,
    count_cards_in_graveyard,
)


def _spawn(game, player, card_def, zone=ZoneType.BATTLEFIELD):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    if zone == ZoneType.BATTLEFIELD:
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


def test_dynamic_self_boost_by_forest_count():
    """An aura-style card whose owner gets +1/+1 for each Forest they control."""
    from src.engine import make_creature, make_land

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    forest_def = make_land(name="Forest", text="", subtypes={"Forest"})

    # The bear's setup attaches a self-boost: +1/+1 per Forest you control.
    def bear_setup(obj, state):
        def mod_fn(source, target, st):
            n = count_permanents_with_subtype(source.controller, "Forest", st)
            return (n, n)
        def affects_self(target, st):
            return target.id == obj.id
        return make_dynamic_pt_boost(obj, mod_fn, affects_self)

    bear_def = CardDefinition(
        name="Forest Bear", mana_cost="{1}{G}",
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Bear"},
            colors={Color.GREEN}, power=2, toughness=2, mana_cost="{1}{G}",
        ),
        text="This creature gets +1/+1 for each Forest you control.",
        setup_interceptors=bear_setup,
    )

    bear = _spawn(game, p1, bear_def)
    # No forests — base 2/2.
    assert get_power(bear, game.state) == 2
    assert get_toughness(bear, game.state) == 2

    # Spawn 3 forests.
    for _ in range(3):
        _spawn(game, p1, forest_def)

    # Now 2+3 = 5 power/toughness.
    assert get_power(bear, game.state) == 5, f"expected 5 power, got {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 5, f"expected 5 toughness, got {get_toughness(bear, game.state)}"

    # Spawn 2 more — should now be 2+5 = 7.
    for _ in range(2):
        _spawn(game, p1, forest_def)
    assert get_power(bear, game.state) == 7, f"expected 7 power after more forests, got {get_power(bear, game.state)}"
    print("PASS: dynamic self-boost reflects Forest count")


def test_attached_dynamic_pt_boost_for_aura():
    """Blanchwood Armor pattern: aura grants +1/+1 to attached creature for each Forest."""
    from src.engine import make_creature, make_land

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    forest_def = make_land(name="Forest", text="", subtypes={"Forest"})
    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )

    def aura_setup(obj, state):
        def mod_fn(source, target, st):
            n = count_permanents_with_subtype(source.controller, "Forest", st)
            return (n, n)
        return make_attached_dynamic_pt_boost(obj, mod_fn)

    aura_chars = Characteristics(
        types={CardType.ENCHANTMENT}, subtypes={"Aura"},
        colors={Color.GREEN}, mana_cost="{2}{G}",
    )
    aura_def = CardDefinition(
        name="Blanchwood Armor", mana_cost="{2}{G}",
        characteristics=aura_chars,
        text="Enchant creature\nEnchanted creature gets +1/+1 for each Forest you control.",
        setup_interceptors=aura_setup,
    )

    bear = _spawn(game, p1, bear_def)
    aura = _spawn(game, p1, aura_def)
    # Forests.
    for _ in range(4):
        _spawn(game, p1, forest_def)

    # Before attach, aura's boost doesn't apply.
    assert get_power(bear, game.state) == 2
    # Attach.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': bear.id},
        source=aura.id, controller=p1.id,
    ))
    # Now bear should be 2+4 = 6/6.
    assert get_power(bear, game.state) == 6, f"expected 6 power, got {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 6
    print("PASS: attached dynamic pt boost for aura")


def test_count_cards_in_hand_dynamic():
    """Hand-size dynamic stat: a creature gets +1/+0 for each card in your hand."""
    from src.engine import make_creature

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    def setup(obj, state):
        def mod_fn(source, target, st):
            n = count_cards_in_hand(source.controller, st)
            return (n, 0)
        return make_dynamic_pt_boost(obj, mod_fn, lambda t, s: t.id == obj.id)

    card_def = CardDefinition(
        name="Hand Watcher", mana_cost="{2}{U}",
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Wizard"},
            colors={Color.BLUE}, power=1, toughness=4, mana_cost="{2}{U}",
        ),
        text="This creature gets +1/+0 for each card in your hand.",
        setup_interceptors=setup,
    )

    obj = _spawn(game, p1, card_def)

    # Empty hand: 1/4.
    hand = game.state.zones.get(f'hand_{p1.id}')
    if hand:
        for cid in list(hand.objects):
            hand.objects.remove(cid)
    assert get_power(obj, game.state) == 1, f"empty-hand power should be 1, got {get_power(obj, game.state)}"

    # Add 3 placeholder cards to hand.
    for _ in range(3):
        from src.engine import make_creature as mk
        c = mk(name="X", power=1, toughness=1, mana_cost="{1}", colors=set(), subtypes={"Human"}, text="")
        _spawn(game, p1, c, zone=ZoneType.HAND)
    assert get_power(obj, game.state) == 4, f"3-card hand power should be 4, got {get_power(obj, game.state)}"
    print("PASS: count_cards_in_hand dynamic")


if __name__ == "__main__":
    test_dynamic_self_boost_by_forest_count()
    test_attached_dynamic_pt_boost_for_aura()
    test_count_cards_in_hand_dynamic()
    print("\nAll dynamic-PT tests passed!")
