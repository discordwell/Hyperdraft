"""Tests for Marvin, Murderous Mimic dynamic activated-ability mirror.

Marvin's printed text: "Marvin has all activated abilities of creatures you
control that don't have the same name as this creature."

The mirror system lives in src/engine/activated.py:
- AbilityMirror + register_ability_mirror — registry entry.
- get_mirrored_abilities — state-time view used by the legal-action surface.
- find_mirrored_ability — lookup used by _handle_activate_ability.
- cleanup_ability_mirror — pruned by the pipeline when the mimic leaves.

These tests verify:
1. Marvin sees activated abilities of *differently named* creatures.
2. Marvin excludes activated abilities of *identically named* creatures.
3. Tapping Marvin for a mirrored {T}: ability taps Marvin, not the source.
4. With no other creatures, no mirrored abilities surface; no crash.
5. When the source creature leaves the battlefield, the ability disappears.
6. Two Marvins (different names) coexist without infinite recursion.
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
    make_creature,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import (
    make_pump_self_ability,
    make_draw_ability,
)


# ---------------------------------------------------------------------------
# Helpers (mirror the conventions used in test_activated_abilities.py).
# ---------------------------------------------------------------------------


def _setup_game_for_player(p_id, game):
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN


def _spawn_on_battlefield(game, player, card_def):
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


def _give_player_mana(player, mana_system, generic=0, red=0):
    from src.engine.mana import ManaType
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)


def _marvin_card():
    """Build a Marvin-shaped card with the mirror setup wired up.

    We construct via make_creature so the test doesn't depend on
    the real DSK module's load semantics. The setup is identical to
    src/cards/duskmourn.py: marvin_murderous_mimic_setup.
    """
    from src.engine.activated import register_ability_mirror

    def _setup(obj, state):
        def _predicate(mimic, st):
            out = []
            for c in st.objects.values():
                if c.zone != ZoneType.BATTLEFIELD:
                    continue
                if CardType.CREATURE not in c.characteristics.types:
                    continue
                if c.controller != mimic.controller:
                    continue
                if c.id == mimic.id:
                    continue
                if c.name == mimic.name:
                    continue
                out.append(c)
            return out
        register_ability_mirror(obj, _predicate)
        return []

    return make_creature(
        name="Marvin, Murderous Mimic",
        power=2, toughness=2, mana_cost="{2}",
        colors=set(), subtypes={"Toy", "Construct"},
        text=(
            "Marvin has all activated abilities of creatures you control "
            "that don't have the same name as this creature."
        ),
        setup_interceptors=_setup,
    )


def _bookworm_card():
    """A Wizard with ``{T}: Draw a card`` for source-creature reuse."""
    def _setup(obj, state):
        make_draw_ability(obj, "{T}", count=1)
        return []

    return make_creature(
        name="Bookworm",
        power=1, toughness=1, mana_cost="{1}{U}",
        colors={Color.BLUE}, subtypes={"Human", "Wizard"},
        text="{T}: Draw a card.",
        setup_interceptors=_setup,
    )


def _goblin_brawler_card():
    """A Goblin with ``{R}: +1/+0 until end of turn`` — no tap, so mana-only."""
    def _setup(obj, state):
        make_pump_self_ability(
            obj, "{R}", power_mod=1, toughness_mod=0,
            description="+1/+0 until end of turn",
        )
        return []

    return make_creature(
        name="Goblin Brawler",
        power=2, toughness=2, mana_cost="{1}{R}",
        colors={Color.RED}, subtypes={"Goblin"},
        text="{R}: Goblin Brawler gets +1/+0 until end of turn.",
        setup_interceptors=_setup,
    )


def _other_marvin_card():
    """A creature literally named Marvin, Murderous Mimic — to test name exclusion.

    The mirror predicate excludes by name, so even though we wire the same
    setup, this creature's *printed* abilities (there are none on Marvin
    proper) won't be mirrored. We add a draw ability here so we can prove
    the mirror correctly skips identically-named creatures.
    """
    from src.engine.activated import register_ability_mirror

    def _setup(obj, state):
        # A draw ability we DO NOT want mirrored.
        make_draw_ability(obj, "{T}", count=1)
        # Also register a mirror so this Marvin can copy others (used in
        # the two-Marvins recursion-guard test).
        def _predicate(mimic, st):
            out = []
            for c in st.objects.values():
                if c.zone != ZoneType.BATTLEFIELD:
                    continue
                if CardType.CREATURE not in c.characteristics.types:
                    continue
                if c.controller != mimic.controller:
                    continue
                if c.id == mimic.id:
                    continue
                if c.name == mimic.name:
                    continue
                out.append(c)
            return out
        register_ability_mirror(obj, _predicate)
        return []

    return make_creature(
        name="Marvin, Murderous Mimic",
        power=2, toughness=2, mana_cost="{2}",
        colors=set(), subtypes={"Toy", "Construct"},
        text=(
            "Marvin has all activated abilities of creatures you control "
            "that don't have the same name as this creature.\n"
            "{T}: Draw a card."
        ),
        setup_interceptors=_setup,
    )


def _twin_marvin_card():
    """A second "mimic-style" creature with a DIFFERENT name.

    Has the same mirror behaviour as Marvin so we can test that when two
    distinct-name mimics coexist they each mirror the other's *printed*
    abilities only — never the mirror-derived ones.
    """
    from src.engine.activated import register_ability_mirror

    def _setup(obj, state):
        # Printed activated ability — should be visible to a paired Marvin.
        make_pump_self_ability(
            obj, "{G}", power_mod=2, toughness_mod=2,
            description="+2/+2 until end of turn",
        )
        # Mirror set.
        def _predicate(mimic, st):
            out = []
            for c in st.objects.values():
                if c.zone != ZoneType.BATTLEFIELD:
                    continue
                if CardType.CREATURE not in c.characteristics.types:
                    continue
                if c.controller != mimic.controller:
                    continue
                if c.id == mimic.id:
                    continue
                if c.name == mimic.name:
                    continue
                out.append(c)
            return out
        register_ability_mirror(obj, _predicate)
        return []

    return make_creature(
        name="Twin Mimic",
        power=2, toughness=2, mana_cost="{2}",
        colors={Color.GREEN}, subtypes={"Shapeshifter"},
        text=(
            "Twin Mimic has all activated abilities of creatures you "
            "control that don't have the same name as this creature.\n"
            "{G}: Twin Mimic gets +2/+2 until end of turn."
        ),
        setup_interceptors=_setup,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_marvin_sees_abilities_of_differently_named_creatures():
    """With Marvin + a Bookworm ({T}: Draw a card), Marvin shows a mirror
    action whose source is Marvin's id and whose ability_id starts with
    ``mirror:``.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    marvin = _spawn_on_battlefield(game, p1, _marvin_card())
    bookworm = _spawn_on_battlefield(game, p1, _bookworm_card())
    marvin.state.summoning_sickness = False
    bookworm.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    marvin_mirror_actions = [
        a for a in actions
        if a.source_id == marvin.id
        and (a.ability_id or "").startswith("mirror:")
    ]
    assert marvin_mirror_actions, (
        f"expected mirrored ability on Marvin, got "
        f"{[(a.source_id, a.ability_id, a.description) for a in actions]}"
    )
    # The mirror_source should be Bookworm.
    parts = marvin_mirror_actions[0].ability_id.split(":")
    assert parts[1] == bookworm.id, f"mirror source mismatch: {parts}"
    print("PASS: marvin sees abilities of differently named creatures")


def test_marvin_excludes_abilities_of_same_named_creatures():
    """A second creature literally named "Marvin, Murderous Mimic" has a
    {T}: Draw a card ability. Marvin's mirror MUST skip it (same name).
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    marvin = _spawn_on_battlefield(game, p1, _marvin_card())
    other_marvin = _spawn_on_battlefield(game, p1, _other_marvin_card())
    marvin.state.summoning_sickness = False
    other_marvin.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    marvin_mirror_actions = [
        a for a in actions
        if a.source_id == marvin.id
        and (a.ability_id or "").startswith("mirror:")
    ]
    # No mirrored abilities from the same-named other-Marvin.
    for a in marvin_mirror_actions:
        parts = a.ability_id.split(":")
        assert parts[1] != other_marvin.id, (
            f"Marvin must not mirror the same-named other Marvin: {a.description}"
        )
    # We expect zero mirror actions on marvin in this scenario.
    assert not marvin_mirror_actions, (
        f"expected no mirrored abilities (only same-named source), got "
        f"{[a.description for a in marvin_mirror_actions]}"
    )
    print("PASS: marvin excludes abilities of same-named creatures")


def test_marvin_taps_self_not_source():
    """Activating Marvin's mirrored {T}: Draw via mirror dispatches:
    - emits TAP on Marvin
    - does NOT tap the Bookworm
    """
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        marvin = _spawn_on_battlefield(game, p1, _marvin_card())
        bookworm = _spawn_on_battlefield(game, p1, _bookworm_card())
        marvin.state.summoning_sickness = False
        bookworm.state.summoning_sickness = False

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=marvin.id,
            ability_id=f"mirror:{bookworm.id}:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [(e.type, e.payload.get('object_id')) for e in events]
        # TAP on Marvin must be present.
        marvin_tap = [
            t for t in types
            if t[0] == EventType.TAP and t[1] == marvin.id
        ]
        bookworm_tap = [
            t for t in types
            if t[0] == EventType.TAP and t[1] == bookworm.id
        ]
        assert marvin_tap, f"expected TAP on Marvin, got: {types}"
        assert not bookworm_tap, (
            f"Bookworm must NOT be tapped by Marvin's mirror, got: {types}"
        )
        # Local state — Marvin tapped, Bookworm untapped.
        assert marvin.state.tapped, "Marvin should be marked tapped"
        assert not bookworm.state.tapped, "Bookworm should NOT be tapped"

        # The stack item should resolve to a DRAW event whose player is p1.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        draw_events = [e for e in resolved if e.type == EventType.DRAW]
        assert draw_events, (
            f"expected DRAW from mirror resolve, got "
            f"{[e.type for e in resolved]}"
        )
        assert draw_events[0].payload['player'] == p1.id
        print("PASS: marvin taps self not source (and DRAW fires for Marvin's controller)")

    asyncio.get_event_loop().run_until_complete(_run())


def test_marvin_no_other_creatures_no_mirrored_abilities():
    """Marvin alone — no mirrored actions, no crash."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    marvin = _spawn_on_battlefield(game, p1, _marvin_card())
    marvin.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    marvin_mirror_actions = [
        a for a in actions
        if a.source_id == marvin.id
        and (a.ability_id or "").startswith("mirror:")
    ]
    assert not marvin_mirror_actions, (
        f"alone Marvin should have no mirrored abilities, got "
        f"{[a.description for a in marvin_mirror_actions]}"
    )
    print("PASS: marvin alone has no mirrored abilities (no crash)")


def test_marvin_handles_creature_leaving_battlefield():
    """When the source creature is destroyed, Marvin's mirror set shrinks."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    marvin = _spawn_on_battlefield(game, p1, _marvin_card())
    bookworm = _spawn_on_battlefield(game, p1, _bookworm_card())
    marvin.state.summoning_sickness = False
    bookworm.state.summoning_sickness = False

    # Before destruction: mirror sees Bookworm's ability.
    actions = game.priority_system.get_legal_actions(p1.id)
    pre = [
        a for a in actions
        if a.source_id == marvin.id
        and (a.ability_id or "").startswith("mirror:")
    ]
    assert pre, f"expected mirrored ability before bookworm leaves, got {actions}"

    # Move Bookworm to graveyard via a ZONE_CHANGE event.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': bookworm.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    assert bookworm.zone == ZoneType.GRAVEYARD, (
        f"bookworm should have moved to graveyard, zone={bookworm.zone}"
    )

    actions = game.priority_system.get_legal_actions(p1.id)
    post = [
        a for a in actions
        if a.source_id == marvin.id
        and (a.ability_id or "").startswith("mirror:")
    ]
    assert not post, (
        f"after bookworm leaves, marvin should have no mirrored abilities, got "
        f"{[a.description for a in post]}"
    )
    print("PASS: marvin's mirror correctly shrinks when source leaves battlefield")


def test_marvin_handles_two_marvins():
    """Two distinctly-named mimics (Marvin + Twin Mimic) coexist.

    Each mirrors the other's *printed* abilities (Twin Mimic's "{G}: +2/+2"
    is printed; Marvin proper has none in this test setup), NOT the
    mirror-derived ones. Concretely:
    - Marvin should see Twin Mimic's printed {G}: +2/+2.
    - Marvin must NOT see Twin Mimic's *mirror-derived* views (or this
      becomes an A->B->A->... loop).
    - Twin Mimic should see Marvin's printed activated abilities (which
      Marvin has none here, so Twin Mimic surfaces no mirrors).
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    marvin = _spawn_on_battlefield(game, p1, _marvin_card())
    twin = _spawn_on_battlefield(game, p1, _twin_marvin_card())
    marvin.state.summoning_sickness = False
    twin.state.summoning_sickness = False

    # Twin Mimic's printed ability costs {G}. Marvin's mirror inherits the
    # cost; without green mana the legal-action surface (correctly) hides
    # it. We supply 1 green so the mirror surfaces in actions.
    from src.engine.mana import ManaType
    game.mana_system.produce_mana(p1.id, ManaType.GREEN, 1)

    actions = game.priority_system.get_legal_actions(p1.id)
    # Marvin should mirror Twin Mimic's printed {G}: +2/+2 ability.
    marvin_mirror = [
        a for a in actions
        if a.source_id == marvin.id
        and (a.ability_id or "").startswith(f"mirror:{twin.id}:")
    ]
    assert marvin_mirror, (
        f"Marvin should mirror Twin Mimic's printed {{G}}: ability, got "
        f"{[(a.source_id, a.ability_id, a.description) for a in actions]}"
    )
    # Twin Mimic should NOT mirror Marvin's *mirror-derived* abilities back.
    # Marvin's printed activated_abilities list is empty (only mirror reg),
    # so Twin Mimic should have zero mirror actions sourced from Marvin.
    twin_mirror = [
        a for a in actions
        if a.source_id == twin.id
        and (a.ability_id or "").startswith(f"mirror:{marvin.id}:")
    ]
    assert not twin_mirror, (
        f"Twin Mimic must not mirror Marvin's mirror-derived abilities, got "
        f"{[a.description for a in twin_mirror]}"
    )

    # Cross-check the get_mirrored_abilities API directly — Marvin's view
    # must contain exactly Twin Mimic's printed abilities (1 ability), and
    # all of them must be marked is_mirror_derived=True.
    from src.engine.activated import get_mirrored_abilities
    marvin_views = get_mirrored_abilities(marvin, game.state)
    assert len(marvin_views) == 1, (
        f"expected Marvin to view 1 mirrored ability (Twin Mimic's +2/+2), "
        f"got {len(marvin_views)}: "
        f"{[(v.cost_text, v.description) for v in marvin_views]}"
    )
    assert all(getattr(v, 'is_mirror_derived', False) for v in marvin_views), (
        "all mirrored views must carry is_mirror_derived=True"
    )
    # And Twin Mimic's view set is empty — Marvin has no printed activated
    # abilities to mirror.
    twin_views = get_mirrored_abilities(twin, game.state)
    assert twin_views == [], (
        f"Twin Mimic should see no mirrored abilities (Marvin has no printed "
        f"activated abilities), got "
        f"{[(v.cost_text, v.description) for v in twin_views]}"
    )
    print("PASS: two marvins coexist without infinite recursion")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    test_marvin_sees_abilities_of_differently_named_creatures()
    test_marvin_excludes_abilities_of_same_named_creatures()
    test_marvin_taps_self_not_source()
    test_marvin_no_other_creatures_no_mirrored_abilities()
    test_marvin_handles_creature_leaving_battlefield()
    test_marvin_handles_two_marvins()
    print("\nAll Marvin mirror tests passed.")
