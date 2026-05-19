"""
Tests for the impulse-draw permission consumer (Gap 1).

Background
----------
The ``EXILE_TOP_PLAY`` / ``IMPULSE_DRAW`` library handlers in
``src/engine/pipeline/handlers/library.py`` write two attributes on the
exiled object's state:

    obj.state._playable_from_exile_by             # player_id allowed to cast
    obj.state._playable_from_exile_through_turn   # inclusive turn-number cap

Until this consumer landed there was no code path reading those flags, so
every "exile top of library, may play this turn" card (Master Kohga,
Ghirahim Demon Lord, Boba Fett HoH, Temporal Bridge, ...) was a silent
no-op at the play-permission level.

These tests verify that the consumer wired into ``cast_permission.py`` and
``priority.py`` correctly surfaces the cast action for owner==caster
impulse, cross-controller impulse (Boba Fett's pattern), and properly
respects the turn-window cap.
"""
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, ZoneType, CardType, Color,
    Event, EventType,
    make_instant, make_creature, make_land,
    PlayerAction, ActionType,
)
from src.engine.cast_permission import (
    is_castable_from_zone,
    query_cast_permission,
)


def _make_simple_instant(name: str = "Plain Instant", cost: str = "{1}{U}"):
    def noop_resolve(targets, state):
        return []
    return make_instant(
        name=name,
        mana_cost=cost,
        colors={Color.BLUE},
        text="Do nothing.",
        resolve=noop_resolve,
    )


def _setup_game_with_two_players(islands_for_p1: int = 4):
    from src.engine.turn import Phase
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    if game.turn_manager is not None:
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(islands_for_p1):
        game.create_object(
            name="Island", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics, card_def=island_def,
        )
    return game, p1, p2


def test_exile_top_play_flags_allow_cast():
    """Flags written by EXILE_TOP_PLAY should make is_castable_from_zone return True."""
    game, p1, _ = _setup_game_with_two_players()
    spell = _make_simple_instant()
    exile_card = game.create_object(
        name=spell.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=spell.characteristics, card_def=spell,
    )
    game.state.zones['exile'].objects.append(exile_card.id)

    # Before flags: not castable.
    assert not is_castable_from_zone(exile_card.id, ZoneType.EXILE, game.state)

    # Simulate the EXILE_TOP_PLAY handler having written the flags.
    exile_card.state._playable_from_exile_by = p1.id
    exile_card.state._playable_from_exile_through_turn = game.state.turn_number

    assert is_castable_from_zone(exile_card.id, ZoneType.EXILE, game.state)
    payload = query_cast_permission(
        exile_card.id, ZoneType.EXILE, p1.id, game.state,
    )
    assert payload.get("allowed") is True


def test_exile_top_play_flags_expire_with_turn_window():
    """``_playable_from_exile_through_turn`` past today => no permission."""
    game, p1, _ = _setup_game_with_two_players()
    spell = _make_simple_instant()
    exile_card = game.create_object(
        name=spell.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=spell.characteristics, card_def=spell,
    )
    game.state.zones['exile'].objects.append(exile_card.id)

    # Window expired last turn.
    exile_card.state._playable_from_exile_by = p1.id
    exile_card.state._playable_from_exile_through_turn = game.state.turn_number - 1

    assert not is_castable_from_zone(exile_card.id, ZoneType.EXILE, game.state)


def test_exile_top_play_flags_only_for_named_caster():
    """Flags address a specific player; nobody else gets to cast."""
    game, p1, p2 = _setup_game_with_two_players()
    spell = _make_simple_instant()
    exile_card = game.create_object(
        name=spell.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=spell.characteristics, card_def=spell,
    )
    game.state.zones['exile'].objects.append(exile_card.id)

    exile_card.state._playable_from_exile_by = p1.id
    exile_card.state._playable_from_exile_through_turn = game.state.turn_number

    p1_payload = query_cast_permission(
        exile_card.id, ZoneType.EXILE, p1.id, game.state,
    )
    p2_payload = query_cast_permission(
        exile_card.id, ZoneType.EXILE, p2.id, game.state,
    )
    assert p1_payload.get("allowed") is True
    assert p2_payload.get("allowed") is False


def test_exile_top_play_handler_writes_flags_and_surfaces_legal_cast():
    """End-to-end: emit EXILE_TOP_PLAY, the handler writes the flags, and the
    next legal-actions surface includes the exiled card as a castable spell."""
    game, p1, _ = _setup_game_with_two_players()
    spell = _make_simple_instant("Impulse Target", cost="{1}{U}")
    top_card = game.create_object(
        name=spell.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=spell.characteristics, card_def=spell,
    )
    lib = game.state.zones[f"library_{p1.id}"]
    if top_card.id not in lib.objects:
        lib.objects.insert(0, top_card.id)

    # Fire the EXILE_TOP_PLAY event through the pipeline to exercise the
    # full handler chain.
    game.emit(Event(
        type=EventType.EXILE_TOP_PLAY,
        payload={
            'player': p1.id,
            'caster': p1.id,
            'amount': 1,
            'until': 'end_of_turn',
        },
    ))

    # Card should now be in the exile zone with the flags set.
    assert top_card.zone == ZoneType.EXILE
    assert getattr(top_card.state, '_playable_from_exile_by', None) == p1.id
    expires = getattr(top_card.state, '_playable_from_exile_through_turn', None)
    assert expires == game.state.turn_number

    # ``is_castable_from_zone`` (player-aware via query_cast_permission) sees it.
    payload = query_cast_permission(
        top_card.id, ZoneType.EXILE, p1.id, game.state,
    )
    assert payload.get("allowed") is True

    # And the cast surfaces in legal actions.
    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(
        a.type == ActionType.CAST_SPELL and a.card_id == top_card.id
        for a in legal
    )


def test_exile_top_play_actually_casts():
    """Cast handler should accept an exiled card with the impulse flags set
    and put it on the stack."""
    game, p1, _ = _setup_game_with_two_players()
    spell = _make_simple_instant()
    exile_card = game.create_object(
        name=spell.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=spell.characteristics, card_def=spell,
    )
    game.state.zones['exile'].objects.append(exile_card.id)
    exile_card.state._playable_from_exile_by = p1.id
    exile_card.state._playable_from_exile_through_turn = game.state.turn_number

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=exile_card.id,
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert exile_card.zone == ZoneType.STACK


def test_cross_controller_impulse_legal_actions():
    """Boba Fett pattern: exile from opp's library, you may play. The exiled
    card's owner is the opponent, but ``_playable_from_exile_by`` names the
    casting player. legal_actions should surface a cast for the named caster."""
    game, p1, p2 = _setup_game_with_two_players()
    spell = _make_simple_instant()
    # Owned by p2 (the opponent whose library was raided).
    exile_card = game.create_object(
        name=spell.name, owner_id=p2.id, zone=ZoneType.EXILE,
        characteristics=spell.characteristics, card_def=spell,
    )
    game.state.zones['exile'].objects.append(exile_card.id)
    # p1 is the caster.
    exile_card.state._playable_from_exile_by = p1.id
    exile_card.state._playable_from_exile_through_turn = game.state.turn_number

    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(
        a.type == ActionType.CAST_SPELL and a.card_id == exile_card.id
        for a in legal
    ), "Cross-controller impulse cast not surfaced in legal_actions"


def test_no_flags_means_no_permission():
    """Regression: an exiled card without the flags should NOT be castable."""
    game, p1, _ = _setup_game_with_two_players()
    spell = _make_simple_instant()
    exile_card = game.create_object(
        name=spell.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=spell.characteristics, card_def=spell,
    )
    game.state.zones['exile'].objects.append(exile_card.id)

    assert not is_castable_from_zone(exile_card.id, ZoneType.EXILE, game.state)
    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(
        a.type == ActionType.CAST_SPELL and a.card_id == exile_card.id
        for a in legal
    )


if __name__ == "__main__":
    test_exile_top_play_flags_allow_cast()
    test_exile_top_play_flags_expire_with_turn_window()
    test_exile_top_play_flags_only_for_named_caster()
    test_exile_top_play_handler_writes_flags_and_surfaces_legal_cast()
    test_exile_top_play_actually_casts()
    test_cross_controller_impulse_legal_actions()
    test_no_flags_means_no_permission()
    print("All exile-play permission tests passed.")
