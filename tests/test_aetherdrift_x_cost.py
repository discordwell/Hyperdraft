"""Tests for the three Aetherdrift X-cost Exhaust cards (W8 wiring).

Cards covered:
  - Mindspring Merfolk: Exhaust — {X}{U}{U}, {T}: Draw X cards.
  - Boommobile: Exhaust — {X}{2}{R}: Boommobile deals X damage to any target.
  - Sita Varma, Masked Racer: Exhaust — {X}{G}{G}{U}: Sita Varma's base
    power and toughness become X/X until end of turn.

Each test:
  1. Spawns the card on the battlefield and clears summoning sickness.
  2. Gives the controller enough mana for the chosen X.
  3. Activates the Exhaust ability via the priority system with x_value set.
  4. Resolves the resulting stack item to fire the effect events.
  5. Asserts the effect (cards drawn / damage dealt / P/T modified) and that
     the once-per-game flag is now set.
"""

import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    Characteristics, get_power, get_toughness,
)
from src.engine.mana import ManaType
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.targeting import Target


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _setup_game_for_player(p_id, game):
    """Configure turn_state so ``p_id`` has priority on their main phase."""
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN


def _spawn_on_battlefield(game, player, card_def):
    """Spawn a card_def's GameObject onto the battlefield via ZONE_CHANGE."""
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


def _give_player_mana(player, mana_system, *, generic=0, red=0, green=0,
                      white=0, blue=0, black=0):
    """Manually populate the mana pool for a player."""
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


def _add_dummy_library(game, player, count, name_prefix="Card"):
    """Stock the player's library so DRAW has cards to find."""
    for i in range(count):
        game.create_object(
            name=f"{name_prefix} {i+1}",
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.INSTANT}),
        )


def _create_simple_creature(game, player, name, power, toughness, subtypes=None):
    """Create a vanilla creature on the battlefield (target practice)."""
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
            subtypes=subtypes or set(),
        ),
    )


# ---------------------------------------------------------------------------
# Mindspring Merfolk: Exhaust — {X}{U}{U}, {T}: Draw X cards.
# ---------------------------------------------------------------------------


def test_mindspring_merfolk_x_cost_draws_x():
    """X=3 against {X}{U}{U}, {T} should consume 3 generic + 2 blue and draw 3.

    Pool: 3 generic + 2 blue = 5. After paying X=3 (3 generic) + UU (2 blue),
    pool is empty and the source is tapped.
    """
    async def _run():
        from src.cards.aetherdrift import MINDSPRING_MERFOLK

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        merfolk = _spawn_on_battlefield(game, p1, MINDSPRING_MERFOLK)
        merfolk.state.summoning_sickness = False
        # Enough cards in library to draw 3 from.
        _add_dummy_library(game, p1, 10)
        # 3 generic + 2 blue = exactly enough for X=3 against {X}{U}{U}.
        _give_player_mana(p1, game.mana_system, generic=3, blue=2)

        hand_before = len(game.get_hand(p1.id))

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=merfolk.id,
            ability_id="activated:0",
            x_value=3,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            f"Mindspring Merfolk activation should succeed; got: {[e.type for e in events]}"

        # Tap cost paid.
        assert merfolk.state.tapped, "Merfolk should be tapped after activation"

        # Mana pool drained.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 0, \
            f"expected empty pool after paying X=3 + UU; got {pool.total()}"

        # Resolve the stack item to actually emit the DRAW event, then process it.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        draw_events = [e for e in resolved if e.type == EventType.DRAW]
        assert draw_events, f"resolve should emit DRAW; got {[e.type for e in resolved]}"
        assert draw_events[0].payload['count'] == 3, \
            f"DRAW count should equal x_value=3; got {draw_events[0].payload}"

        # Drive the DRAW event through the pipeline so the hand actually grows.
        for ev in resolved:
            game.emit(ev)
        hand_after = len(game.get_hand(p1.id))
        cards_drawn = hand_after - hand_before
        assert cards_drawn == 3, f"expected 3 cards drawn, got {cards_drawn}"

        # once_per_game_used should be set after activation.
        ability = merfolk.state.activated_abilities[0]
        assert ability.once_per_game is True
        assert ability.once_per_game_used is True
        print("PASS: Mindspring Merfolk X=3 draws 3 cards, pays 5 mana, locks Exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Boommobile: Exhaust — {X}{2}{R}: Boommobile deals X damage to any target.
# ---------------------------------------------------------------------------


def test_boommobile_x_cost_deals_x_damage_to_target():
    """X=3 should pay 3 generic + 2 generic + 1 red (= 6 total) and deal 3 damage.

    Setup: Boommobile untapped, 5/5 enemy creature, 3 generic + 1 red + 2
    extra generic = 6 mana total. Activate with X=3 targeting enemy creature.
    """
    async def _run():
        from src.cards.aetherdrift import BOOMMOBILE

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        boom = _spawn_on_battlefield(game, p1, BOOMMOBILE)
        boom.state.summoning_sickness = False
        # 5 generic + 1 red = enough for X=3 against {X}{2}{R} (X=3 -> 3 generic
        # for X plus 2 generic for {2} plus 1 red for {R} = 6 mana). We give
        # exactly 5 generic + 1 red so the pool drains to 0.
        _give_player_mana(p1, game.mana_system, generic=5, red=1)

        # Enemy creature to target.
        enemy = _create_simple_creature(game, p2, "Big Enemy", 5, 5)
        enemy.controller = p2.id

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=boom.id,
            ability_id="activated:0",
            x_value=3,
            targets=[[Target(id=enemy.id, is_player=False)]],
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            f"Boommobile activation should succeed; got: {[e.type for e in events]}"

        # Mana drained.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 0, \
            f"expected empty pool after paying X=3 + {{2}}{{R}} = 6 mana; got {pool.total()}"

        # Resolve the stack item and emit the DAMAGE event.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        dmg_events = [e for e in resolved if e.type == EventType.DAMAGE]
        assert dmg_events, f"resolve should emit DAMAGE; got {[e.type for e in resolved]}"
        assert dmg_events[0].payload['amount'] == 3, \
            f"DAMAGE amount should equal x_value=3; got {dmg_events[0].payload}"
        assert dmg_events[0].payload['target'] == enemy.id, \
            f"DAMAGE target should be enemy creature; got {dmg_events[0].payload}"

        # Drive the DAMAGE event through the pipeline so the enemy actually
        # takes damage.
        for ev in resolved:
            game.emit(ev)
        assert enemy.state.damage == 3, \
            f"enemy should have taken 3 damage; got {enemy.state.damage}"

        # once_per_game_used set.
        ability = boom.state.activated_abilities[0]
        assert ability.once_per_game is True
        assert ability.once_per_game_used is True
        print("PASS: Boommobile X=3 deals 3 damage to target, pays 6 mana, locks Exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Sita Varma, Masked Racer: Exhaust — {X}{G}{G}{U}: P/T becomes X/X EOT.
# ---------------------------------------------------------------------------


def test_sita_varma_x_cost_sets_pt_to_x():
    """X=4 should set Sita Varma's P/T to 4/4 until end of turn.

    Sita Varma is printed as 2/3, so the effect emits a PT_MODIFICATION
    delta of (+2, +1) to land at 4/4. With no other modifiers in play,
    the resulting power and toughness should both be 4.
    """
    async def _run():
        from src.cards.aetherdrift import SITA_VARMA_MASKED_RACER

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        sita = _spawn_on_battlefield(game, p1, SITA_VARMA_MASKED_RACER)
        sita.state.summoning_sickness = False
        # 4 generic + 2 green + 1 blue = enough for X=4 against {X}{G}{G}{U}.
        _give_player_mana(p1, game.mana_system, generic=4, green=2, blue=1)

        # Sanity: printed P/T is 2/3, current power/toughness should match
        # before activation (no modifiers yet).
        assert get_power(sita, game.state) == 2
        assert get_toughness(sita, game.state) == 3

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=sita.id,
            ability_id="activated:0",
            x_value=4,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            f"Sita Varma activation should succeed; got: {[e.type for e in events]}"

        # Mana drained.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 0, \
            f"expected empty pool after paying X=4 + {{G}}{{G}}{{U}}; got {pool.total()}"

        # Resolve the stack item and emit the PT_MODIFICATION event.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        pt_events = [e for e in resolved if e.type == EventType.PT_MODIFICATION]
        assert pt_events, f"resolve should emit PT_MODIFICATION; got {[e.type for e in resolved]}"
        # Delta should be (X - printed_p, X - printed_t) = (4-2, 4-3) = (2, 1).
        assert pt_events[0].payload['power_mod'] == 2, \
            f"power_mod should be x_value(4) - printed_power(2) = 2; got {pt_events[0].payload}"
        assert pt_events[0].payload['toughness_mod'] == 1, \
            f"toughness_mod should be x_value(4) - printed_toughness(3) = 1; got {pt_events[0].payload}"
        assert pt_events[0].payload['duration'] == 'end_of_turn'

        # Drive the PT_MODIFICATION event through the pipeline.
        for ev in resolved:
            game.emit(ev)

        # Final P/T should be X/X = 4/4.
        new_p = get_power(sita, game.state)
        new_t = get_toughness(sita, game.state)
        assert new_p == 4, f"expected power 4 (X), got {new_p}"
        assert new_t == 4, f"expected toughness 4 (X), got {new_t}"

        # once_per_game_used set.
        ability = sita.state.activated_abilities[0]
        assert ability.once_per_game is True
        assert ability.once_per_game_used is True
        print("PASS: Sita Varma X=4 sets P/T to 4/4 until EOT, pays 7 mana, locks Exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Smoke test: all three cards register exactly one Exhaust ability with
# has_x_cost=True.
# ---------------------------------------------------------------------------


def test_aetherdrift_x_cost_cards_register_x_exhaust_abilities():
    """Sanity check: each of the 3 wired cards registers a single Exhaust
    ability with has_x_cost=True after spawning on the battlefield."""
    from src.cards.aetherdrift import (
        MINDSPRING_MERFOLK, BOOMMOBILE, SITA_VARMA_MASKED_RACER,
    )

    cards = [MINDSPRING_MERFOLK, BOOMMOBILE, SITA_VARMA_MASKED_RACER]
    for card in cards:
        assert card.setup_interceptors is not None, \
            f"{card.name}: setup_interceptors not wired"

    for card in cards:
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)
        obj = _spawn_on_battlefield(game, p1, card)
        ab_list = obj.state.activated_abilities or []
        x_exhaust = [
            a for a in ab_list
            if getattr(a, 'once_per_game', False) and getattr(a, 'has_x_cost', False)
        ]
        assert len(x_exhaust) == 1, (
            f"{card.name}: expected exactly one X-cost Exhaust ability, "
            f"got {len(x_exhaust)} (abilities={[a.cost_text for a in ab_list]})"
        )
    print(f"PASS: {len(cards)} W8 X-cost Exhaust cards register has_x_cost=True")


if __name__ == "__main__":
    print("=" * 70)
    print("AETHERDRIFT X-COST EXHAUST CARDS (W8)")
    print("=" * 70)
    test_aetherdrift_x_cost_cards_register_x_exhaust_abilities()
    test_mindspring_merfolk_x_cost_draws_x()
    test_boommobile_x_cost_deals_x_damage_to_target()
    test_sita_varma_x_cost_sets_pt_to_x()
    print("=" * 70)
    print("All Aetherdrift X-cost tests passed.")
    print("=" * 70)
