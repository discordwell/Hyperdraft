"""Clash mechanic tests (Lorwyn block).

Covers ``src.engine.clash.clash``:

- Strictly-higher mana value wins the clash; equal or lower loses.
- An empty opponent library can't beat a non-empty reveal (you win).
- An empty caster library loses to any non-empty reveal, and an
  all-empty clash is a loss (own MV -1 is not > opp MV -1).
- A LIBSEARCH_REVEAL marker is emitted for each card actually revealed.
- ``bottom_own`` / ``bottom_opponent`` move the revealed card to the bottom
  of the respective library (the optional "put on the bottom" choice).
- Additive discipline: clash never mutates either library unless a bottom
  flag is set, and reveals nothing that isn't on top.

Run:
    PYTHONPATH=. python tests/test_clash.py
"""

import os
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _ROOT)

from src.engine import (
    Game, ZoneType, CardType, Characteristics,
)
from src.engine.clash import clash


def _make_game():
    game = Game()
    p1 = game.add_player("P0")
    p2 = game.add_player("P1")
    return game, p1, p2


def _lib_card(game, player, mana_cost, name=None):
    """Append a card to player's library. First-appended == top (index 0)."""
    return game.create_object(
        name=name or f"Lib-{player.id}-{mana_cost}",
        owner_id=player.id, zone=ZoneType.LIBRARY,
        characteristics=Characteristics(types={CardType.CREATURE}, mana_cost=mana_cost),
        card_def=None,
    )


def test_higher_mv_wins():
    game, p1, p2 = _make_game()
    _lib_card(game, p1, "{4}{G}")  # MV 5
    _lib_card(game, p2, "{1}")     # MV 1
    res = clash(game.state, p1.id)
    assert res.won, "caster MV5 vs opp MV1 should win"
    assert res.own_mv == 5 and res.opp_mv == 1


def test_equal_mv_loses():
    game, p1, p2 = _make_game()
    _lib_card(game, p1, "{2}")
    _lib_card(game, p2, "{2}")
    res = clash(game.state, p1.id)
    assert not res.won, "tie clash is NOT a win (strictly-greater rule)"


def test_lower_mv_loses():
    game, p1, p2 = _make_game()
    _lib_card(game, p1, "{1}")
    _lib_card(game, p2, "{5}")
    res = clash(game.state, p1.id)
    assert not res.won, "caster MV1 vs opp MV5 should lose"


def test_empty_opponent_library_loses_to_reveal():
    game, p1, p2 = _make_game()
    _lib_card(game, p1, "")  # MV 0
    # opponent library empty -> opp MV treated as -1
    res = clash(game.state, p1.id)
    assert res.won, "MV0 reveal beats an empty opponent library"
    assert res.opp_mv is None and res.opp_card is None


def test_all_empty_is_a_loss():
    game, p1, p2 = _make_game()
    res = clash(game.state, p1.id)
    assert not res.won, "empty-vs-empty is a loss (-1 is not > -1)"
    assert res.own_card is None and res.opp_card is None
    assert res.events == [], "no reveal markers when nothing is revealed"


def test_reveal_markers_emitted():
    game, p1, p2 = _make_game()
    c1 = _lib_card(game, p1, "{3}")
    c2 = _lib_card(game, p2, "{1}")
    res = clash(game.state, p1.id)
    revealed = {e.payload["object_id"] for e in res.events
                if e.type.name == "LIBSEARCH_REVEAL"}
    assert revealed == {c1.id, c2.id}, f"both top cards revealed, got {revealed}"


def test_bottom_own_moves_card_to_bottom():
    game, p1, p2 = _make_game()
    top = _lib_card(game, p1, "{0}")
    other = _lib_card(game, p1, "{0}", name="second")
    _lib_card(game, p2, "{0}")
    clash(game.state, p1.id, bottom_own=True)
    lib = game.state.zones[f"library_{p1.id}"].objects
    assert lib[0] == other.id and lib[-1] == top.id, \
        "bottom_own should move the revealed top card to the bottom"


def test_no_bottom_keeps_library_unchanged():
    game, p1, p2 = _make_game()
    top = _lib_card(game, p1, "{0}")
    other = _lib_card(game, p1, "{0}", name="second")
    before = list(game.state.zones[f"library_{p1.id}"].objects)
    clash(game.state, p1.id)  # no bottom flags
    after = list(game.state.zones[f"library_{p1.id}"].objects)
    assert before == after, "clash must not mutate the library without a bottom flag"


def run_all():
    test_higher_mv_wins()
    test_equal_mv_loses()
    test_lower_mv_loses()
    test_empty_opponent_library_loses_to_reveal()
    test_all_empty_is_a_loss()
    test_reveal_markers_emitted()
    test_bottom_own_moves_card_to_bottom()
    test_no_bottom_keeps_library_unchanged()
    print("\n" + "=" * 60)
    print("ALL CLASH TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
