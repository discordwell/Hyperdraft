"""Type-overwrite auras: Lignify-style replacements (CR layer 4/5/6/7b).

Covers:
- Aura attaches: target's power/toughness become the aura's base values
- Aura attaches: target's subtypes are exactly the aura's new_subtypes
- Aura attaches: target loses keywords from before attachment
- Aura unattaches (e.g., aura destroyed): target reverts to original
  P/T, subtypes, abilities
- Aura attached + counters added to creature: counters stack on top of
  the new base (CR layer 7c — counters apply after base-set)
- Lord effect targeting the new subtype: the transformed creature gets
  the lord buff
- Per-card test for each wired card (Noggle the Mind + 2 SYNTHETIC)
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
    make_creature, make_enchantment,
    get_power, get_toughness, has_ability,
)
from src.engine.queries import get_subtypes, get_types, get_colors
from src.cards.interceptor_helpers import (
    make_type_overwrite_aura,
    make_static_pt_boost,
    creatures_with_subtype,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


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


def _spawn_aura(game, player, name, target, *, base_power, base_toughness,
                new_subtypes, new_types=None, new_colors=None,
                lose_abilities=True, keep_keywords=None,
                aura_colors=None):
    """Create a type-overwrite aura targeting ``target`` and put it onto BF.

    Mirrors the ``test_aura_setup_attaches_and_boosts`` pattern: build the
    aura object directly (card_def=None at create_object time so setup
    doesn't run prematurely), pre-set ``_aura_target_id``, then emit a
    ZONE_CHANGE to BATTLEFIELD which runs setup_interceptors.
    """
    aura_chars = Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Aura"},
        colors=set(aura_colors or set()),
        mana_cost="{2}{G}",
    )

    def _setup(obj, state):
        inner = make_type_overwrite_aura(
            obj,
            base_power=base_power,
            base_toughness=base_toughness,
            new_subtypes=new_subtypes,
            new_types=new_types,
            new_colors=new_colors,
            lose_abilities=lose_abilities,
            keep_keywords=keep_keywords,
        )
        return inner(obj, state)

    aura_def = CardDefinition(
        name=name,
        mana_cost="{2}{G}",
        characteristics=aura_chars,
        text=f"Enchant creature\n{name}",
        setup_interceptors=_setup,
    )
    aura = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=aura_chars,
        card_def=None,
    )
    aura.card_def = aura_def
    setattr(aura.state, "_aura_target_id", target.id)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': aura.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return aura


# -----------------------------------------------------------------------------
# Core helper tests
# -----------------------------------------------------------------------------


def test_aura_attach_overrides_pt_and_subtypes():
    """A 5/5 Beast with flying becomes a 0/4 Treefolk with no abilities."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    big_def = make_creature(
        name="Pterodactyl", power=5, toughness=5, mana_cost="{3}{G}{G}",
        colors={Color.GREEN}, subtypes={"Beast"},
        text="Flying",
    )
    # Wire flying as a printed ability on the characteristics so has_ability
    # sees it; make_creature stores abilities on CardDefinition rather than
    # injecting into Characteristics.abilities.
    big_def.characteristics.abilities = [{'keyword': 'flying'}]
    big = _spawn(game, p1, big_def)

    # Sanity check.
    assert get_power(big, game.state) == 5
    assert "Beast" in big.characteristics.subtypes
    assert has_ability(big, "flying", game.state), "should have flying before"

    aura = _spawn_aura(
        game, p1, "Lignify", big,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        new_colors={Color.GREEN},
        aura_colors={Color.GREEN},
    )

    # Aura is attached.
    assert aura.state.attached_to == big.id

    # P/T overrides via QUERY_POWER / QUERY_TOUGHNESS.
    assert get_power(big, game.state) == 0, f"expected 0 power, got {get_power(big, game.state)}"
    assert get_toughness(big, game.state) == 4, f"expected 4 toughness, got {get_toughness(big, game.state)}"

    # Subtypes replaced (via QUERY_SUBTYPES *and* dual-write).
    subs = get_subtypes(big, game.state)
    assert subs == {"Treefolk"}, f"expected {{'Treefolk'}}, got {subs}"
    assert big.characteristics.subtypes == {"Treefolk"}, "dual-write should mirror"

    # Direct read of P/T also reflects override (dual-write).
    assert big.characteristics.power == 0
    assert big.characteristics.toughness == 4

    # Keywords stripped.
    assert not has_ability(big, "flying", game.state), "flying should be stripped"
    print("PASS: aura attach overrides P/T and subtypes (Lignify)")


def test_aura_unattach_restores_original():
    """When the aura goes to graveyard, the creature reverts."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    big_def = make_creature(
        name="Pterodactyl", power=5, toughness=5, mana_cost="{3}{G}{G}",
        colors={Color.GREEN}, subtypes={"Beast"},
        text="Flying",
    )
    big_def.characteristics.abilities = [{'keyword': 'flying'}]
    big = _spawn(game, p1, big_def)
    aura = _spawn_aura(
        game, p1, "Lignify", big,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        aura_colors={Color.GREEN},
    )

    assert get_power(big, game.state) == 0
    assert big.characteristics.subtypes == {"Treefolk"}

    # Aura goes to graveyard.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': aura.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))

    # Original characteristics restored.
    assert get_power(big, game.state) == 5, f"expected 5 power restored, got {get_power(big, game.state)}"
    assert get_toughness(big, game.state) == 5
    assert "Beast" in big.characteristics.subtypes, "Beast subtype should return"
    assert "Treefolk" not in big.characteristics.subtypes
    assert has_ability(big, "flying", game.state), "flying should return"
    print("PASS: aura unattach restores original characteristics")


def test_counters_stack_on_top_of_new_base():
    """CR layer 7c: counters apply AFTER base-set effects.

    A 0/4 Treefolk with two +1/+1 counters is a 2/6, not 2/2.
    """
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    big_def = make_creature(
        name="Stomper", power=5, toughness=5, mana_cost="{3}{G}{G}",
        colors={Color.GREEN}, subtypes={"Beast"}, text="",
    )
    big = _spawn(game, p1, big_def)

    _spawn_aura(
        game, p1, "Lignify", big,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        aura_colors={Color.GREEN},
    )

    # Add two +1/+1 counters AFTER the aura is attached.
    big.state.counters['+1/+1'] = 2

    assert get_power(big, game.state) == 2, f"expected 0+2=2, got {get_power(big, game.state)}"
    assert get_toughness(big, game.state) == 6, f"expected 4+2=6, got {get_toughness(big, game.state)}"
    print("PASS: counters stack on top of new base (layer 7c)")


def test_lord_buffs_new_subtype():
    """A Treefolk lord buffs the transformed creature.

    The aura turns Bear into a Treefolk. A 'Treefolk creatures get +1/+1'
    static effect should now apply to the transformed creature.
    """
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, bear_def)

    _spawn_aura(
        game, p1, "Lignify", bear,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        aura_colors={Color.GREEN},
    )

    # Sanity: 0/4 now.
    assert get_power(bear, game.state) == 0
    assert "Treefolk" in get_subtypes(bear, game.state)

    # Spawn a Treefolk lord that grants +1/+1 to Treefolk you control.
    # ``other_creatures_with_subtype`` excludes the lord itself; we want to
    # buff every Treefolk we control here so use ``creatures_with_subtype``.
    def lord_setup(obj, state):
        from src.cards.interceptor_helpers import other_creatures_with_subtype
        return make_static_pt_boost(
            obj, power_mod=1, toughness_mod=1,
            affects_filter=other_creatures_with_subtype(obj, "Treefolk"),
        )

    lord_chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Treefolk"},
        colors={Color.GREEN},
        mana_cost="{2}{G}",
        power=2, toughness=2,
        abilities=[],
    )
    lord_def = CardDefinition(
        name="Treefolk Champion",
        mana_cost="{2}{G}",
        characteristics=lord_chars,
        text="Other Treefolk you control get +1/+1.",
        setup_interceptors=lord_setup,
    )
    lord = game.create_object(
        name="Treefolk Champion",
        owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=lord_chars,
        card_def=None,
    )
    lord.card_def = lord_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': lord.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    # Lord buff: 0/4 + 1/+1 = 1/5.
    assert get_power(bear, game.state) == 1, (
        f"expected 1 power (0 base + 1 lord), got {get_power(bear, game.state)}"
    )
    assert get_toughness(bear, game.state) == 5, (
        f"expected 5 toughness (4 base + 1 lord), got {get_toughness(bear, game.state)}"
    )
    print("PASS: lord effect buffs the new subtype")


def test_types_and_colors_overwritten():
    """An artifact creature becomes a creature-only Treefolk; its colors are replaced."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    art_def = make_creature(
        name="Steel Hawk", power=3, toughness=3, mana_cost="{2}",
        colors=set(),
        subtypes={"Bird"}, text="Flying",
    )
    art_def.characteristics.abilities = [{'keyword': 'flying'}]
    # Artifact creature: add ARTIFACT type manually.
    art_def.characteristics.types.add(CardType.ARTIFACT)
    art_def.characteristics.colors = set()
    art = _spawn(game, p1, art_def)

    _spawn_aura(
        game, p1, "Lignify", art,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        new_types=[CardType.CREATURE],
        new_colors={Color.GREEN},
        aura_colors={Color.GREEN},
    )

    types = get_types(art, game.state)
    assert types == {CardType.CREATURE}, f"expected {{CREATURE}}, got {types}"
    colors = get_colors(art, game.state)
    assert colors == {Color.GREEN}, f"expected green, got {colors}"
    assert not has_ability(art, "flying", game.state)
    print("PASS: types and colors overwritten")


def test_keep_keywords_survive_overwrite():
    """``keep_keywords=['flying']`` lets the new creature keep flying."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, bear_def)

    _spawn_aura(
        game, p1, "Sky Treefolk", bear,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        keep_keywords=["flying"],
        aura_colors={Color.GREEN},
    )

    # has_ability checks both characteristics.abilities (dual-write) AND
    # the QUERY_ABILITIES interceptor's granted list. Either path should
    # surface flying.
    assert has_ability(bear, "flying", game.state), "kept-keyword flying should be active"
    assert get_power(bear, game.state) == 0
    print("PASS: keep_keywords survive the overwrite")


def test_multiple_overlapping_auras_last_wins():
    """Two type-overwrite auras: latest-timestamp wins.

    Both interceptors TRANSFORM the value, applied in timestamp order, so
    the later aura's value sticks for power/toughness/subtypes.
    """
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, bear_def)

    _spawn_aura(
        game, p1, "Lignify", bear,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        aura_colors={Color.GREEN},
    )
    # First aura: 0/4 Treefolk.
    assert get_power(bear, game.state) == 0

    _spawn_aura(
        game, p1, "Song of the Dryads", bear,
        base_power=1, base_toughness=1,
        new_subtypes=["Elf"],
        aura_colors={Color.GREEN},
    )
    # Latest wins: 1/1 Elf.
    assert get_power(bear, game.state) == 1, f"expected latest 1, got {get_power(bear, game.state)}"
    assert get_toughness(bear, game.state) == 1
    subs = get_subtypes(bear, game.state)
    assert subs == {"Elf"}, f"expected {{Elf}}, got {subs}"
    print("PASS: multiple overlapping auras — latest wins")


def test_reattach_to_new_target_moves_override():
    """If the aura re-attaches, the override moves to the new target."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear1 = _spawn(game, p1, bear_def)
    bear2 = _spawn(game, p1, bear_def)

    aura = _spawn_aura(
        game, p1, "Lignify", bear1,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        aura_colors={Color.GREEN},
    )

    assert get_power(bear1, game.state) == 0
    assert get_power(bear2, game.state) == 2

    # Re-attach to bear2.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': bear2.id},
        source=aura.id, controller=p1.id,
    ))

    # bear1 reverts, bear2 takes the override.
    assert get_power(bear1, game.state) == 2, (
        f"bear1 should revert to 2, got {get_power(bear1, game.state)}"
    )
    assert "Bear" in bear1.characteristics.subtypes
    assert "Treefolk" not in bear1.characteristics.subtypes

    assert get_power(bear2, game.state) == 0, (
        f"bear2 should now be 0, got {get_power(bear2, game.state)}"
    )
    assert "Treefolk" in get_subtypes(bear2, game.state)
    print("PASS: re-attach moves the override to the new target")


# -----------------------------------------------------------------------------
# Per-card tests
# -----------------------------------------------------------------------------


def test_card_noggle_the_mind():
    """ECL: 'Enchanted creature loses all abilities and is a colorless
    Noggle with base power and toughness 1/1.'"""
    from src.cards.lorwyn_eclipsed import NOGGLE_THE_MIND
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    big_def = make_creature(
        name="Faerie Conclave", power=4, toughness=4, mana_cost="{2}{U}",
        colors={Color.BLUE}, subtypes={"Faerie", "Wizard"},
        text="Flying",
    )
    big_def.characteristics.abilities = [{'keyword': 'flying'}]
    big = _spawn(game, p1, big_def)

    aura = game.create_object(
        name=NOGGLE_THE_MIND.name,
        owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=NOGGLE_THE_MIND.characteristics,
        card_def=None,
    )
    aura.card_def = NOGGLE_THE_MIND
    setattr(aura.state, "_aura_target_id", big.id)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': aura.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    assert aura.state.attached_to == big.id
    assert get_power(big, game.state) == 1
    assert get_toughness(big, game.state) == 1
    assert get_subtypes(big, game.state) == {"Noggle"}
    assert get_colors(big, game.state) == set(), "Noggle is colorless"
    assert not has_ability(big, "flying", game.state)
    print("PASS: NOGGLE_THE_MIND wires correctly")


def test_synthetic_lignify():
    """SYNTHETIC: classic Lignify template — '0/4 Treefolk with no abilities'."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    target_def = make_creature(
        name="Hellrider", power=3, toughness=3, mana_cost="{2}{R}{R}",
        colors={Color.RED}, subtypes={"Devil"},
        text="Haste, trample",
    )
    target_def.characteristics.abilities = [
        {'keyword': 'haste'}, {'keyword': 'trample'}
    ]
    target = _spawn(game, p1, target_def)

    _spawn_aura(
        game, p1, "Lignify (synthetic)", target,
        base_power=0, base_toughness=4,
        new_subtypes=["Treefolk"],
        new_colors={Color.GREEN},
        aura_colors={Color.GREEN},
    )

    assert get_power(target, game.state) == 0
    assert get_toughness(target, game.state) == 4
    assert get_subtypes(target, game.state) == {"Treefolk"}
    assert not has_ability(target, "haste", game.state)
    assert not has_ability(target, "trample", game.state)
    print("PASS: synthetic Lignify behaves as expected")


def test_synthetic_song_of_the_dryads():
    """SYNTHETIC: 'Song of the Dryads' template — '1/1 Elf, no abilities,
    loses all other types and subtypes' (here we keep CREATURE only)."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    target_def = make_creature(
        name="Goblin Soldier", power=2, toughness=1, mana_cost="{R}",
        colors={Color.RED}, subtypes={"Goblin", "Soldier"},
        text="First strike",
    )
    target_def.characteristics.abilities = [{'keyword': 'first_strike'}]
    target = _spawn(game, p1, target_def)

    _spawn_aura(
        game, p1, "Song of the Dryads (synthetic)", target,
        base_power=1, base_toughness=1,
        new_subtypes=["Elf"],
        new_types=[CardType.CREATURE],
        new_colors={Color.GREEN},
        aura_colors={Color.GREEN},
    )

    assert get_power(target, game.state) == 1
    assert get_toughness(target, game.state) == 1
    assert get_subtypes(target, game.state) == {"Elf"}
    assert get_types(target, game.state) == {CardType.CREATURE}
    assert not has_ability(target, "first_strike", game.state)
    print("PASS: synthetic Song of the Dryads behaves as expected")


if __name__ == "__main__":
    test_aura_attach_overrides_pt_and_subtypes()
    test_aura_unattach_restores_original()
    test_counters_stack_on_top_of_new_base()
    test_lord_buffs_new_subtype()
    test_types_and_colors_overwritten()
    test_keep_keywords_survive_overwrite()
    test_multiple_overlapping_auras_last_wins()
    test_reattach_to_new_target_moves_override()
    test_card_noggle_the_mind()
    test_synthetic_lignify()
    test_synthetic_song_of_the_dryads()
    print("\nAll type-overwrite aura tests passed!")
