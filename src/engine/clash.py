"""Clash mechanic (Lorwyn block).

Clash is a one-shot library-peek minigame used by several Lorwyn spells:

    "Clash with an opponent. [If you win, <effect>.]"

Rules text (CR 701.x, paraphrased):
  - You and a chosen opponent each reveal the top card of your library.
  - Each player may then put their revealed card on the bottom of their
    library (or leave it on top).
  - You "win the clash" if your revealed card's mana value is strictly
    greater than the opponent's revealed card's mana value.

This module is a small, additive helper. It does **not** add a new event
type or pipeline stage: clash resolves inline during a spell's resolve()
and returns ``(won, reveal_events)`` so the calling card can gate its
secondary effect on the boolean and emit the reveal markers for
public-information triggers.

Public API
----------
- ``clash(state, caster_id, opponent_id=None, *, bottom_own=False,
          bottom_opponent=False) -> ClashResult``

``ClashResult`` is a small dataclass exposing:
  - ``won``           : did the caster win the clash?
  - ``own_mv`` / ``opp_mv`` : revealed mana values (None if a library was empty)
  - ``own_card`` / ``opp_card`` : revealed object IDs (None if empty)
  - ``events``        : LIBSEARCH_REVEAL markers for each revealed card

An empty library reveals nothing (mana value treated as None). Per the
comprehensive rules, a missing reveal can't beat anything, so a player who
reveals no card is treated as mana value -1 for the comparison (they lose
ties and any non-empty reveal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .types import Event, EventType, GameState, ZoneType
from .mana import _card_mana_value


@dataclass
class ClashResult:
    won: bool = False
    own_mv: Optional[int] = None
    opp_mv: Optional[int] = None
    own_card: Optional[str] = None
    opp_card: Optional[str] = None
    events: list = field(default_factory=list)


def _top_card_id(state: GameState, player_id: str) -> Optional[str]:
    """Top of a player's library (index 0 by engine convention), or None."""
    lib = state.zones.get(f"library_{player_id}")
    if not lib or not lib.objects:
        return None
    return lib.objects[0]


def _pick_opponent(state: GameState, caster_id: str) -> Optional[str]:
    for pid in state.players:
        if pid != caster_id:
            return pid
    return None


def clash(
    state: GameState,
    caster_id: str,
    opponent_id: Optional[str] = None,
    *,
    bottom_own: bool = False,
    bottom_opponent: bool = False,
) -> ClashResult:
    """Perform a clash and report whether ``caster_id`` won.

    Args:
        state: live game state.
        caster_id: the player who initiated the clash.
        opponent_id: the opponent to clash with. Defaults to the first other
            player in turn order.
        bottom_own: if True, put the caster's revealed card on the bottom of
            their library (default: leave on top).
        bottom_opponent: if True, put the opponent's revealed card on the
            bottom of their library (default: leave on top).

    Returns a ``ClashResult`` (see module docstring).
    """
    if opponent_id is None:
        opponent_id = _pick_opponent(state, caster_id)

    own_id = _top_card_id(state, caster_id)
    opp_id = _top_card_id(state, opponent_id) if opponent_id else None

    result = ClashResult(own_card=own_id, opp_card=opp_id)

    # Reveal markers for public-information triggers.
    for pid, cid in ((caster_id, own_id), (opponent_id, opp_id)):
        if cid is not None and pid is not None:
            obj = state.objects.get(cid)
            result.events.append(Event(
                type=EventType.LIBSEARCH_REVEAL,
                payload={
                    "player": pid,
                    "object_id": cid,
                    "source_id": caster_id,
                    "destination": "clash",
                    "reason": "clash",
                },
                source=caster_id,
            ))
            # record mana value
            mv = _card_mana_value(obj) if obj is not None else None
            if pid == caster_id:
                result.own_mv = mv
            else:
                result.opp_mv = mv

    # Strictly-greater comparison; an empty reveal counts as -1 (loses ties
    # and any non-empty reveal, can't beat an empty one).
    own_cmp = result.own_mv if result.own_mv is not None else -1
    opp_cmp = result.opp_mv if result.opp_mv is not None else -1
    result.won = own_cmp > opp_cmp

    # Optional "put on the bottom of your library".
    if bottom_own and own_id is not None:
        _bottom(state, caster_id, own_id)
    if bottom_opponent and opp_id is not None and opponent_id is not None:
        _bottom(state, opponent_id, opp_id)

    return result


def _bottom(state: GameState, player_id: str, card_id: str) -> None:
    lib = state.zones.get(f"library_{player_id}")
    if not lib or card_id not in lib.objects:
        return
    lib.objects.remove(card_id)
    lib.objects.append(card_id)
