"""
Phase 5b — Agent O shock-land framework + 10 card wirings.

Covers ``make_shockland_setup(life_cost=2)`` and its 10 consumers:
- EOE: BREEDING_POOL, GODLESS_SHRINE, SACRED_FOUNDRY, STOMPING_GROUND,
       WATERY_GRAVE
- ECL: BLOOD_CRYPT, HALLOWED_FOUNTAIN, OVERGROWN_TOMB, STEAM_VENTS,
       TEMPLE_GARDEN

The framework wires an ETB-trigger interceptor that opens a PendingChoice
(``choice_type='shockland'``) owned by the land's controller. The choice's
handler emits ``LIFE_CHANGE -2`` (pay) or ``TAP`` on the land (decline).
AI players auto-resolve the choice inline against the heuristic
``life > life_cost + 3``; humans see the pending choice.

The mana ability is intentionally NOT wired by the framework — it falls out
of the land's basic-land subtypes via ``ManaSystem._get_land_mana_production``.
Each per-card smoke test asserts that mana production works as printed.
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    GameObject, ObjectState, new_id,
)
from src.engine.priority import PlayerAction, ActionType
from src.engine.mana import ManaSystem, ManaType

from src.cards import edge_of_eternities as eoe
from src.cards import lorwyn_eclipsed as ecl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.start_game()
    return game, p1, p2


def _spawn_in_hand(game, player_id, card_def):
    obj = GameObject(
        id=new_id(),
        name=card_def.name,
        owner=player_id,
        controller=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        state=ObjectState(),
        card_def=card_def,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    game.state.zones[f'hand_{player_id}'].objects.append(obj.id)
    return obj


async def _play_land(game, player_id, obj_id):
    action = PlayerAction(type=ActionType.PLAY_LAND, player_id=player_id, card_id=obj_id)
    events = await game.priority_system._handle_play_land(action)
    for e in events:
        game.pipeline.emit(e)
    return events


# ---------------------------------------------------------------------------
# 1. Core framework behavior: ETB opens PendingChoice for a human controller
# ---------------------------------------------------------------------------


def test_shockland_etb_emits_pay_choice():
    """Playing a shockland under a human controller should leave a
    PendingChoice on the state, owned by that player, with options=[True, False].
    """
    print("\n=== Test: shockland ETB emits pay/decline PendingChoice ===")

    async def go():
        game, p1, _ = _new_game()
        # No set_ai_player → p1 is treated as human; the framework leaves the
        # choice pending instead of auto-resolving.
        obj = _spawn_in_hand(game, p1.id, eoe.BREEDING_POOL)
        await _play_land(game, p1.id, obj.id)
        pc = game.state.pending_choice
        assert pc is not None, "expected pending shockland choice for human"
        assert pc.player == p1.id, (
            f"choice should be owned by controller {p1.id}, got {pc.player}"
        )
        assert pc.choice_type == "shockland", pc.choice_type
        assert pc.options == [True, False], pc.options
        on_bf = game.state.objects[obj.id]
        assert on_bf.zone == ZoneType.BATTLEFIELD
        # Before the choice is submitted, the land is on the battlefield
        # untapped (default; tap is applied only on decline).
        assert on_bf.state.tapped is False
        # Life is unchanged until the player commits.
        assert p1.life == 20

    asyncio.run(go())
    print("  PASS: PendingChoice for shockland opens with [True, False] options")


def test_shockland_pay_life_keeps_untapped_costs_2_life():
    """Submit 'pay' (True) → controller loses 2 life, land stays untapped."""
    print("\n=== Test: submit 'pay' costs 2 life and keeps land untapped ===")

    async def go():
        game, p1, _ = _new_game()
        starting_life = p1.life
        obj = _spawn_in_hand(game, p1.id, ecl.HALLOWED_FOUNTAIN)
        await _play_land(game, p1.id, obj.id)
        pc = game.state.pending_choice
        assert pc is not None
        ok, msg, events = game.submit_choice(pc.id, p1.id, [True])
        assert ok, msg
        # LIFE_CHANGE should have been emitted via the handler.
        life_evts = [
            e for e in events
            if e.type == EventType.LIFE_CHANGE
            and e.payload.get('player') == p1.id
            and e.payload.get('amount') == -2
        ]
        assert life_evts, (
            f"expected LIFE_CHANGE -2 for {p1.id}; got events "
            f"{[(e.type.name, e.payload) for e in events]}"
        )
        assert p1.life == starting_life - 2, p1.life
        on_bf = game.state.objects[obj.id]
        assert on_bf.state.tapped is False, "pay → untapped"
        assert game.state.pending_choice is None

    asyncio.run(go())
    print("  PASS: pay submission costs 2 life and leaves Hallowed Fountain untapped")


def test_shockland_decline_taps_land_no_life_change():
    """Submit 'decline' (False) → TAP event on the land, no life change."""
    print("\n=== Test: submit 'decline' taps land, no life change ===")

    async def go():
        game, p1, _ = _new_game()
        starting_life = p1.life
        obj = _spawn_in_hand(game, p1.id, eoe.STOMPING_GROUND)
        await _play_land(game, p1.id, obj.id)
        pc = game.state.pending_choice
        assert pc is not None
        ok, msg, events = game.submit_choice(pc.id, p1.id, [False])
        assert ok, msg
        # No LIFE_CHANGE for our player.
        life_evts = [
            e for e in events
            if e.type == EventType.LIFE_CHANGE
            and e.payload.get('player') == p1.id
        ]
        assert not life_evts, (
            f"decline must not change life; got "
            f"{[(e.type.name, e.payload) for e in events]}"
        )
        assert p1.life == starting_life
        # A TAP event must be present (the framework emits TAP on decline).
        tap_evts = [
            e for e in events
            if e.type == EventType.TAP and e.payload.get('object_id') == obj.id
        ]
        assert tap_evts, (
            f"expected TAP event on the land; got "
            f"{[(e.type.name, e.payload) for e in events]}"
        )
        on_bf = game.state.objects[obj.id]
        assert on_bf.state.tapped is True, "decline → tapped"
        assert game.state.pending_choice is None

    asyncio.run(go())
    print("  PASS: decline submission taps Stomping Ground without losing life")


# ---------------------------------------------------------------------------
# 2. AI heuristic: pay when comfortable, decline when low life
# ---------------------------------------------------------------------------


def test_shockland_ai_heuristic_pays_when_high_life():
    """AI controller at default life (20) auto-resolves to 'pay'."""
    print("\n=== Test: AI heuristic pays at high life ===")

    async def go():
        game, p1, _ = _new_game()
        game.priority_system.set_ai_player(p1.id)
        starting_life = p1.life
        obj = _spawn_in_hand(game, p1.id, eoe.GODLESS_SHRINE)
        await _play_land(game, p1.id, obj.id)
        # AI auto-resolves inline → choice cleared, life reduced, untapped.
        assert game.state.pending_choice is None
        assert p1.life == starting_life - 2
        assert game.state.objects[obj.id].state.tapped is False

    asyncio.run(go())
    print("  PASS: AI at life=20 pays 2 life and Godless Shrine enters untapped")


def test_shockland_ai_heuristic_declines_when_low_life():
    """AI controller at life=3 auto-resolves to 'decline' (cost+3 floor)."""
    print("\n=== Test: AI heuristic declines at low life ===")

    async def go():
        game, p1, _ = _new_game()
        game.priority_system.set_ai_player(p1.id)
        p1.life = 3  # below cost+3 = 5 → decline
        starting_life = p1.life
        obj = _spawn_in_hand(game, p1.id, ecl.OVERGROWN_TOMB)
        await _play_land(game, p1.id, obj.id)
        assert game.state.pending_choice is None
        assert p1.life == starting_life, (
            f"low-life AI should not pay; got life={p1.life}"
        )
        assert game.state.objects[obj.id].state.tapped is True, (
            "low-life AI should decline → tapped"
        )

    asyncio.run(go())
    print("  PASS: AI at life=3 declines and Overgrown Tomb enters tapped")


# ---------------------------------------------------------------------------
# 3. Per-card smoke tests: confirm the mana ability survives the rewrite
# ---------------------------------------------------------------------------


# Map of card_def → expected mana colors produced. The mana ability is derived
# from the basic-land subtypes by ManaSystem; we assert both subtypes survive
# the wiring and that ``_get_land_mana_production`` returns both colors.
_SHOCKLAND_MANA_TABLE: list[tuple[str, object, set[ManaType], set[str]]] = [
    ("Breeding Pool", eoe.BREEDING_POOL,
     {ManaType.GREEN, ManaType.BLUE}, {"Forest", "Island"}),
    ("Godless Shrine", eoe.GODLESS_SHRINE,
     {ManaType.WHITE, ManaType.BLACK}, {"Plains", "Swamp"}),
    ("Sacred Foundry", eoe.SACRED_FOUNDRY,
     {ManaType.RED, ManaType.WHITE}, {"Mountain", "Plains"}),
    ("Stomping Ground", eoe.STOMPING_GROUND,
     {ManaType.RED, ManaType.GREEN}, {"Mountain", "Forest"}),
    ("Watery Grave", eoe.WATERY_GRAVE,
     {ManaType.BLUE, ManaType.BLACK}, {"Island", "Swamp"}),
    ("Blood Crypt", ecl.BLOOD_CRYPT,
     {ManaType.BLACK, ManaType.RED}, {"Mountain", "Swamp"}),
    ("Hallowed Fountain", ecl.HALLOWED_FOUNTAIN,
     {ManaType.WHITE, ManaType.BLUE}, {"Plains", "Island"}),
    ("Overgrown Tomb", ecl.OVERGROWN_TOMB,
     {ManaType.BLACK, ManaType.GREEN}, {"Swamp", "Forest"}),
    ("Steam Vents", ecl.STEAM_VENTS,
     {ManaType.BLUE, ManaType.RED}, {"Island", "Mountain"}),
    ("Temple Garden", ecl.TEMPLE_GARDEN,
     {ManaType.GREEN, ManaType.WHITE}, {"Forest", "Plains"}),
]


def _smoke_test_factory(name, card_def, expected_colors, expected_subtypes):
    """Per-card test: subtypes intact, framework wired, mana derives correctly."""
    def runner():
        print(f"\n=== Test: {name} mana ability still wired ===")
        # 1. Subtypes are still on the CardDefinition (no accidental loss).
        actual_subtypes = set(card_def.characteristics.subtypes)
        assert actual_subtypes == expected_subtypes, (
            f"{name} subtypes drifted: expected {expected_subtypes}, "
            f"got {actual_subtypes}"
        )
        # 2. setup_interceptors is wired (not None / not bare stub).
        assert card_def.setup_interceptors is not None, (
            f"{name} should have setup_interceptors wired"
        )

        async def go():
            game, p1, _ = _new_game()
            game.priority_system.set_ai_player(p1.id)
            # Float at full life so AI pays and the land enters untapped,
            # making the mana ability legally activatable this same turn.
            obj = _spawn_in_hand(game, p1.id, card_def)
            await _play_land(game, p1.id, obj.id)
            on_bf = game.state.objects[obj.id]
            assert on_bf.state.tapped is False, (
                f"{name} should enter untapped at high life"
            )

            # 3. ManaSystem derives the right colors from the subtypes.
            colors = set(game.mana_system._get_land_mana_production(on_bf))
            assert colors == expected_colors, (
                f"{name}: expected mana {expected_colors}, got {colors}"
            )

            # 4. The untapped land registers as a mana source for its controller.
            sources = game.mana_system.get_untapped_lands(p1.id)
            land_source = next((s for s in sources if s.land_id == obj.id), None)
            assert land_source is not None, (
                f"{name} should appear as an untapped mana source"
            )
            assert set(land_source.produces) == expected_colors, (
                f"{name} source produces {land_source.produces}, "
                f"expected {expected_colors}"
            )

        asyncio.run(go())
        print(f"  PASS: {name} produces {sorted(c.name for c in expected_colors)}")

    runner.__name__ = f"test_{name.lower().replace(' ', '_')}_mana_still_wired"
    runner.__doc__ = (
        f"Per-card smoke test for {name}: confirms the mana ability "
        f"(derived from basic-land subtypes) is intact after wiring "
        f"make_shockland_setup."
    )
    return runner


# Generate one test function per shockland and register at module scope so the
# main runner below can iterate over them.
_PER_CARD_TESTS = []
for _name, _card_def, _colors, _subs in _SHOCKLAND_MANA_TABLE:
    _t = _smoke_test_factory(_name, _card_def, _colors, _subs)
    globals()[_t.__name__] = _t
    _PER_CARD_TESTS.append(_t)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    tests = [
        test_shockland_etb_emits_pay_choice,
        test_shockland_pay_life_keeps_untapped_costs_2_life,
        test_shockland_decline_taps_land_no_life_change,
        test_shockland_ai_heuristic_pays_when_high_life,
        test_shockland_ai_heuristic_declines_when_low_life,
    ] + list(_PER_CARD_TESTS)

    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")

    print(f"\nRan {len(tests)} tests. {len(tests) - len(failed)} passed, "
          f"{len(failed)} failed.")
    if failed:
        for name, err in failed:
            print(f"  - {name}: {err}")
        sys.exit(1)
    sys.exit(0)
