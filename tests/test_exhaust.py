"""Tests for the Exhaust mechanic (once-per-game activated ability).

Exhaust is an Aetherdrift / Avatar: TLA mechanic. Each Exhaust ability
on a permanent can be activated at most once — ever. The ability is
tracked per-permanent (per ``GameObject``), not per card name, so two
copies of the same card each have their own state.

Covers:
- Exhaust ability surfaces in legal actions before first activation
- After activation, it's removed from legal actions for that permanent
- Two copies of the same card maintain independent exhaust state
- Engine API: ``ActivatedAbility.once_per_game`` and the
  ``make_exhaust_ability`` helper.
- A real wired card (Skystreak Engineer from Aetherdrift) round-trips
  through the priority system.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, Color,
    make_creature,
)
from src.engine.activated import detect_exhaust
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_exhaust_ability


def _setup_game_for_player(p_id, game):
    """Set up turn_state so the player has priority on their own main phase."""
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


def _give_player_mana(player, mana_system, generic=0, red=0, green=0,
                      white=0, blue=0, black=0):
    from src.engine.mana import ManaType
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(green):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)
    for _ in range(white):
        mana_system.produce_mana(player.id, ManaType.WHITE, 1)
    for _ in range(blue):
        mana_system.produce_mana(player.id, ManaType.BLUE, 1)
    for _ in range(black):
        mana_system.produce_mana(player.id, ManaType.BLACK, 1)


def _make_pump_exhaust_card(name="Test Exhaust"):
    """Helper: build a creature with an Exhaust — {1}: +1/+1 counter ability."""

    def setup(obj, state):
        def _effect(o, st, targets):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id, controller=o.controller,
            )]
        make_exhaust_ability(
            obj, cost="{1}", effect_fn=_effect,
            description="{1}: Put a +1/+1 counter on this creature.",
        )
        return []

    return make_creature(
        name=name,
        power=2, toughness=2, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text=f"Exhaust — {{1}}: Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
        setup_interceptors=setup,
    )


# ---------------------------------------------------------------------------
# Engine-level tests
# ---------------------------------------------------------------------------


def test_detect_exhaust_recognizes_text():
    """detect_exhaust catches the standard reminder phrasing and the Exhaust prefix."""
    yes = [
        "Exhaust — {2}{R}: Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
        "Flying\nExhaust — {1}: Draw a card.",
        "Foo bar (Activate each exhaust ability only once.)",
    ]
    no = [
        "",
        "Vigilance",
        "{T}: Add {R}.",
        "Activate this ability only once each turn.",  # Once-per-turn != exhaust
    ]
    for t in yes:
        assert detect_exhaust(t), f"expected Exhaust detected in: {t!r}"
    for t in no:
        assert not detect_exhaust(t), f"did not expect Exhaust in: {t!r}"
    print("PASS: detect_exhaust recognizes Exhaust text")


def test_exhaust_surfaces_then_disappears_after_activation():
    """The ability is legal before, gone after."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_pump_exhaust_card("Lone Exhauster")
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=2)

        # Legal before activation.
        before = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in before if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert matches, f"expected Exhaust ability in legal actions, got: {[a.description for a in before]}"

        # Activate.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), "first activation should succeed"

        # Confirm the descriptor recorded the use.
        ability = obj.state.activated_abilities[0]
        assert ability.once_per_game is True, "ability should be marked once-per-game"
        assert ability.once_per_game_used is True, "once_per_game_used should be set"
        assert ability.total_activations == 1

        # No longer legal — even on the same turn.
        after = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in after if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not matches, "Exhaust ability should be hidden after first activation"

        # Re-attempting should also fail through the dispatch path.
        _give_player_mana(p1, game.mana_system, generic=2)
        replay = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in replay), \
            "second activation must be rejected by can_pay_activation"

        # And it's still gone on a future turn.
        game.turn_manager.turn_state.turn_number += 5
        game.state.turn_number += 5
        future = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in future if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not matches, "Exhaust ability should be hidden across turns"
        print("PASS: exhaust ability surfaces, activates once, never returns")

    asyncio.get_event_loop().run_until_complete(_run())


def test_two_copies_have_independent_exhaust_state():
    """Per-permanent, not per-card-name. Activating one copy doesn't lock the other."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_pump_exhaust_card("Twinned Exhauster")
        obj_a = _spawn_on_battlefield(game, p1, card)
        obj_b = _spawn_on_battlefield(game, p1, card)
        obj_a.state.summoning_sickness = False
        obj_b.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=4)

        # Both copies should expose their Exhaust ability.
        actions = game.priority_system.get_legal_actions(p1.id)
        a_match = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj_a.id]
        b_match = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj_b.id]
        assert a_match and b_match, "both copies should expose their Exhaust ability"

        # Activate copy A only.
        action_a = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj_a.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action_a)
        assert any(e.type == EventType.ACTIVATE for e in events), "copy A should activate"

        # Copy A locked, copy B still legal.
        post = game.priority_system.get_legal_actions(p1.id)
        a_locked = [a for a in post if a.ability_id == "activated:0" and a.source_id == obj_a.id]
        b_open = [a for a in post if a.ability_id == "activated:0" and a.source_id == obj_b.id]
        assert not a_locked, "copy A should be locked"
        assert b_open, "copy B should remain legal"

        # Independent descriptor state.
        ab_a = obj_a.state.activated_abilities[0]
        ab_b = obj_b.state.activated_abilities[0]
        assert ab_a is not ab_b, "each permanent must own its own ActivatedAbility instance"
        assert ab_a.once_per_game_used is True
        assert ab_b.once_per_game_used is False
        print("PASS: two copies of the same card have independent exhaust state")

    asyncio.get_event_loop().run_until_complete(_run())


def test_make_exhaust_ability_sets_once_per_game_flag():
    """The helper produces a descriptor with once_per_game=True and a clear description."""
    game = Game()
    p1 = game.add_player("Alice")
    _setup_game_for_player(p1.id, game)

    card = _make_pump_exhaust_card("Inspectable")
    obj = _spawn_on_battlefield(game, p1, card)

    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    ab = abilities[0]
    assert ab.once_per_game is True, "make_exhaust_ability must set once_per_game"
    assert ab.once_per_turn is False, "Exhaust does not imply once-per-turn"
    assert ab.description.lower().startswith("exhaust"), \
        f"description should be prefixed with 'Exhaust —', got {ab.description!r}"
    print("PASS: make_exhaust_ability sets once_per_game flag and Exhaust prefix")


# ---------------------------------------------------------------------------
# Wired-card smoke tests
# ---------------------------------------------------------------------------


def test_wired_skystreak_engineer_exhaust():
    """Aetherdrift Skystreak Engineer: Exhaust — {4}{U}: 2 +1/+1 counters."""
    async def _run():
        from src.cards.aetherdrift import SKYSTREAK_ENGINEER

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, SKYSTREAK_ENGINEER)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=4, blue=1)

        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert matches, "Skystreak Engineer should expose its Exhaust ability"

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), "activation should succeed"

        # Resolve the stack item to confirm two +1/+1 counters are emitted.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        ctr_events = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert ctr_events, f"expected COUNTER_ADDED, got {[e.type for e in resolved]}"
        assert ctr_events[0].payload['amount'] == 2, "should add two +1/+1 counters"
        assert ctr_events[0].payload['counter_type'] == '+1/+1'

        # And it's locked for the rest of the game.
        post = game.priority_system.get_legal_actions(p1.id)
        post_match = [a for a in post if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not post_match, "Skystreak Engineer's Exhaust must be locked after activation"
        print("PASS: wired Skystreak Engineer Exhaust round-trips and locks")

    asyncio.get_event_loop().run_until_complete(_run())


def test_wired_aetherdrift_cards_register_exhaust_abilities():
    """Sanity check: the seven wired Aetherdrift cards each register one Exhaust ability."""
    from src.cards import aetherdrift

    cards = [
        aetherdrift.KEEN_BUCCANEER,
        aetherdrift.SKYSTREAK_ENGINEER,
        aetherdrift.PACESETTER_PARAGON,
        aetherdrift.PROWCATCHER_SPECIALIST,
        aetherdrift.HAZARD_OF_THE_DUNES,
        aetherdrift.STAMPEDING_SCURRYFOOT,
        aetherdrift.CAMERA_LAUNCHER,
    ]
    for card in cards:
        assert card.setup_interceptors is not None, f"{card.name}: setup_interceptors not wired"

    # Spawn each one and check the Exhaust ability registered with once_per_game.
    for card in cards:
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)
        obj = _spawn_on_battlefield(game, p1, card)
        ab_list = obj.state.activated_abilities or []
        exhaust_abs = [a for a in ab_list if a.once_per_game]
        assert exhaust_abs, f"{card.name}: expected an Exhaust ability registered"
        assert len(exhaust_abs) == 1, \
            f"{card.name}: expected exactly one Exhaust ability, got {len(exhaust_abs)}"
    print(f"PASS: {len(cards)} wired Aetherdrift Exhaust cards register correctly")


# ---------------------------------------------------------------------------
# Group A — newly-wired Aetherdrift Exhaust cards (W4)
# ---------------------------------------------------------------------------


def test_riverchurn_monument_each_opp_mills():
    """Each opponent mills cards equal to their own graveyard size.

    Setup:
      - opp1 graveyard size 0
      - opp2 graveyard size 3
    After activation: one MILL event for opp2 with amount=3, none for opp1.
    """
    async def _run():
        from src.cards.aetherdrift import RIVERCHURN_MONUMENT, KEEN_BUCCANEER

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")     # gy size 0
        p3 = game.add_player("Carol")   # gy size 3
        _setup_game_for_player(p1.id, game)

        # Stash three cards in Carol's graveyard so the mill amount is 3.
        gy_key = f"graveyard_{p3.id}"
        gy = game.state.zones.get(gy_key)
        assert gy is not None, "expected a graveyard zone for player 3"
        # Reuse a small card_def to populate the graveyard with 3 GameObjects.
        for _ in range(3):
            stub = game.create_object(
                name="Filler",
                owner_id=p3.id,
                zone=ZoneType.GRAVEYARD,
                characteristics=KEEN_BUCCANEER.characteristics,
                card_def=None,
            )
            stub.card_def = KEEN_BUCCANEER
            # The create_object helper places objects in state but doesn't
            # always push them into the zone's list — do it explicitly.
            if stub.id not in gy.objects:
                gy.objects.append(stub.id)
        assert len(gy.objects) == 3, f"expected 3 cards in p3 graveyard, got {len(gy.objects)}"

        obj = _spawn_on_battlefield(game, p1, RIVERCHURN_MONUMENT)
        # Treat the artifact as ready to tap for the cost. Exhaust uses the
        # once-per-game gate, not summoning sickness.
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=2, blue=2)

        # The activated ability index should be 0 for the lone Exhaust.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "Riverchurn Monument's Exhaust should activate"

        # Resolve the stack item to capture the MILL events.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        mill_events = [e for e in resolved if e.type == EventType.MILL]
        # Only opp2 (Carol, gy=3) should produce a mill event.
        assert len(mill_events) == 1, f"expected 1 mill event, got {len(mill_events)}: {mill_events}"
        ev = mill_events[0]
        assert ev.payload['player'] == p3.id
        assert ev.payload['amount'] == 3

        # Once-per-game lock fires.
        ab = obj.state.activated_abilities[0]
        assert ab.once_per_game is True
        assert ab.once_per_game_used is True
        print("PASS: Riverchurn Monument mills each opponent by their own GY size, locks after one use")

    asyncio.get_event_loop().run_until_complete(_run())


def test_greasewrench_goblin_zero_discard_skips_draw():
    """With zero cards in hand, the {2}{R} Exhaust still fires but emits no draw."""
    async def _run():
        from src.cards.aetherdrift import GREASEWRENCH_GOBLIN

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, GREASEWRENCH_GOBLIN)
        obj.state.summoning_sickness = False
        # Empty hand — make sure no leftover hand objects.
        hand = game.state.zones.get(f"hand_{p1.id}")
        if hand:
            hand.objects.clear()

        _give_player_mana(p1, game.mana_system, generic=2, red=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        # With no cards in hand, no PendingChoice opens; only the +1/+1 counter rider fires.
        ctr = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        draws = [e for e in resolved if e.type == EventType.DRAW]
        assert ctr, "expected the +1/+1 counter rider"
        assert ctr[0].payload['amount'] == 1
        assert ctr[0].payload['counter_type'] == '+1/+1'
        assert not draws, "no draw should be emitted when hand is empty"

        # Locked.
        ab = obj.state.activated_abilities[0]
        assert ab.once_per_game_used is True
        print("PASS: Greasewrench Goblin with empty hand emits +1/+1 only, locks after one use")

    asyncio.get_event_loop().run_until_complete(_run())


def test_skyserpent_seeker_search_emits_search_library_event():
    """The {4} Exhaust should emit a SEARCH_LIBRARY event for 2 lands ETB tapped,
    plus the +1/+1 counter rider."""
    async def _run():
        from src.cards.aetherdrift import SKYSERPENT_SEEKER

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, SKYSERPENT_SEEKER)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=4)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        searches = [e for e in resolved if e.type == EventType.SEARCH_LIBRARY]
        ctrs = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert searches, f"expected a SEARCH_LIBRARY event, got {[e.type for e in resolved]}"
        ev = searches[0]
        assert ev.payload['amount'] == 2
        assert ev.payload.get('tapped') is True
        assert ev.payload.get('destination') == 'battlefield'
        assert ctrs and ctrs[0].payload['amount'] == 1
        # Locked.
        assert obj.state.activated_abilities[0].once_per_game_used is True
        print("PASS: Skyserpent Seeker emits SEARCH_LIBRARY (2 lands tapped) and counter rider")

    asyncio.get_event_loop().run_until_complete(_run())


def test_redshift_no_permanents_in_hand_emits_no_events():
    """When hand has no permanent cards, Redshift's Exhaust resolves to no events
    (no PendingChoice opens). Once-per-game still locks."""
    async def _run():
        from src.cards.aetherdrift import REDSHIFT_ROCKETEER_CHIEF

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, REDSHIFT_ROCKETEER_CHIEF)
        obj.state.summoning_sickness = False
        # Empty hand of permanent cards.
        hand = game.state.zones.get(f"hand_{p1.id}")
        if hand:
            hand.objects.clear()

        _give_player_mana(p1, game.mana_system, generic=10, red=1, green=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        assert resolved == [], f"expected no events with empty hand, got {resolved}"
        # Locked anyway: the once_per_game flag flips on the PAYMENT/use side.
        assert obj.state.activated_abilities[0].once_per_game_used is True
        print("PASS: Redshift with empty hand resolves to no events, still locks once-per-game")

    asyncio.get_event_loop().run_until_complete(_run())


def test_loot_pathfinder_three_exhausts_distinct():
    """Loot has three Exhausts: {G}, {U}, {R} — each should appear independently
    in the activated_abilities list, all marked once_per_game.

    Activate {U} (draw 3): the other two Exhausts remain available; activating
    them all in sequence locks each one separately.
    """
    async def _run():
        from src.cards.aetherdrift import LOOT_THE_PATHFINDER

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, LOOT_THE_PATHFINDER)
        obj.state.summoning_sickness = False

        ab_list = obj.state.activated_abilities or []
        exhausts = [a for a in ab_list if a.once_per_game]
        assert len(exhausts) == 3, f"Loot should register exactly 3 Exhausts, got {len(exhausts)}"
        # All distinct descriptors.
        ids = {id(a) for a in exhausts}
        assert len(ids) == 3, "the three Exhausts should be distinct ActivatedAbility instances"
        descs = [a.description for a in exhausts]
        # Description ordering matches setup: {G} mana, {U} draw, {R} damage.
        assert "{G}" in descs[0] and "Add three mana" in descs[0]
        assert "{U}" in descs[1] and "Draw three cards" in descs[1]
        assert "{R}" in descs[2] and ("damage" in descs[2].lower())

        # Activate Exhaust 1 (G mana).
        _give_player_mana(p1, game.mana_system, green=1)
        action_g = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action_g)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "first Exhaust ({G}) should activate"

        # Verify only the first descriptor is now locked.
        assert obj.state.activated_abilities[0].once_per_game_used is True
        assert obj.state.activated_abilities[1].once_per_game_used is False
        assert obj.state.activated_abilities[2].once_per_game_used is False

        # Each Exhaust on Loot has a {T} cost. Activating the first taps Loot;
        # we manually untap before activating the second to simulate the
        # untap step on the next turn (Exhaust survives across turns).
        obj.state.tapped = False

        # Activate Exhaust 2 (U draw).
        _give_player_mana(p1, game.mana_system, blue=1)
        action_u = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:1",
        )
        events = await game.priority_system._handle_activate_ability(action_u)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "second Exhaust ({U}) should activate"
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        draws = [e for e in resolved if e.type == EventType.DRAW]
        assert draws and draws[0].payload['count'] == 3, \
            f"expected DRAW(3), got {[(e.type, e.payload) for e in resolved]}"

        # Re-attempting either of the locked Exhausts should silently fail —
        # untap first to rule out tap-state as the blocker, isolating the
        # once-per-game gate.
        obj.state.tapped = False
        _give_player_mana(p1, game.mana_system, green=1)
        replay = await game.priority_system._handle_activate_ability(action_g)
        assert not any(e.type == EventType.ACTIVATE for e in replay), \
            "first Exhaust must not re-activate"
        # Third Exhaust still unlocked.
        assert obj.state.activated_abilities[2].once_per_game_used is False
        print("PASS: Loot, the Pathfinder registers 3 distinct Exhausts; each locks independently")

    asyncio.get_event_loop().run_until_complete(_run())


def test_draconautics_engineer_two_exhausts_distinct():
    """Draconautics Engineer has two Exhausts: {R} (haste + counter) and {3}{R}
    (4/4 Dinosaur Dragon token). Both register; activating one leaves the other.
    """
    async def _run():
        from src.cards.aetherdrift import DRACONAUTICS_ENGINEER

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, DRACONAUTICS_ENGINEER)
        obj.state.summoning_sickness = False

        ab_list = obj.state.activated_abilities or []
        exhausts = [a for a in ab_list if a.once_per_game]
        assert len(exhausts) == 2, \
            f"Draconautics should register 2 Exhausts, got {len(exhausts)}"

        # Activate the {R} Exhaust (haste + counter on self). Verify a
        # GRANT_KEYWORD haste event for *another* creature you control fires.
        # First spawn another creature for p1 so haste-grant is observable.
        from src.cards.aetherdrift import KEEN_BUCCANEER
        ally = _spawn_on_battlefield(game, p1, KEEN_BUCCANEER)
        ally.state.summoning_sickness = False

        _give_player_mana(p1, game.mana_system, red=1)
        action_r = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action_r)
        assert any(e.type == EventType.ACTIVATE for e in events)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        haste_events = [
            e for e in resolved
            if e.type == EventType.GRANT_KEYWORD and e.payload.get('keyword') == 'haste'
        ]
        # Should grant haste to ally but not to self ("other creatures").
        haste_target_ids = {e.payload['object_id'] for e in haste_events}
        assert ally.id in haste_target_ids
        assert obj.id not in haste_target_ids
        # +1/+1 counter on self.
        ctrs = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert ctrs and ctrs[0].payload['object_id'] == obj.id

        # First Exhaust locked, second still open.
        assert obj.state.activated_abilities[0].once_per_game_used is True
        assert obj.state.activated_abilities[1].once_per_game_used is False

        # Activate {3}{R}: should produce a Dinosaur Dragon 4/4 with flying token.
        _give_player_mana(p1, game.mana_system, generic=3, red=1)
        action_3r = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:1",
        )
        events = await game.priority_system._handle_activate_ability(action_3r)
        assert any(e.type == EventType.ACTIVATE for e in events)
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        token_events = [
            e for e in resolved
            if e.type == EventType.OBJECT_CREATED
            and e.payload.get('name') == 'Dinosaur Dragon'
        ]
        assert token_events, f"expected a Dinosaur Dragon token, got {[(e.type, e.payload.get('name')) for e in resolved]}"
        ev = token_events[0]
        assert ev.payload['power'] == 4
        assert ev.payload['toughness'] == 4
        assert 'flying' in ev.payload['abilities']
        # Both locked now.
        assert obj.state.activated_abilities[1].once_per_game_used is True
        print("PASS: Draconautics Engineer registers 2 Exhausts; each locks independently with correct effects")

    asyncio.get_event_loop().run_until_complete(_run())


def test_w4_group_a_all_register_exhausts():
    """Sanity sweep: each W4 Group A card registers >=1 Exhaust (some register multiple)."""
    from src.cards import aetherdrift

    expected = [
        (aetherdrift.RIVERCHURN_MONUMENT, 1),
        (aetherdrift.GREASEWRENCH_GOBLIN, 1),
        (aetherdrift.SKYSERPENT_SEEKER, 1),
        (aetherdrift.REDSHIFT_ROCKETEER_CHIEF, 1),
        (aetherdrift.LOOT_THE_PATHFINDER, 3),
        (aetherdrift.DRACONAUTICS_ENGINEER, 2),
    ]
    for card, expected_count in expected:
        assert card.setup_interceptors is not None, f"{card.name}: not wired"
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)
        obj = _spawn_on_battlefield(game, p1, card)
        ab_list = obj.state.activated_abilities or []
        exhausts = [a for a in ab_list if a.once_per_game]
        assert len(exhausts) == expected_count, \
            f"{card.name}: expected {expected_count} Exhausts, got {len(exhausts)}"
    print(f"PASS: W4 Group A — all {len(expected)} cards register the expected Exhaust counts")


if __name__ == "__main__":
    test_detect_exhaust_recognizes_text()
    test_make_exhaust_ability_sets_once_per_game_flag()
    test_exhaust_surfaces_then_disappears_after_activation()
    test_two_copies_have_independent_exhaust_state()
    test_wired_skystreak_engineer_exhaust()
    test_wired_aetherdrift_cards_register_exhaust_abilities()
    # W4 Group A — newly wired Aetherdrift Exhausts.
    test_w4_group_a_all_register_exhausts()
    test_riverchurn_monument_each_opp_mills()
    test_greasewrench_goblin_zero_discard_skips_draw()
    test_skyserpent_seeker_search_emits_search_library_event()
    test_redshift_no_permanents_in_hand_emits_no_events()
    test_loot_pathfinder_three_exhausts_distinct()
    test_draconautics_engineer_two_exhausts_distinct()
    print("\nAll Exhaust tests passed.")
