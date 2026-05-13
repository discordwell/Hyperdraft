"""MNR-on-SZB callback cards.

These are bridge cards that mix MNR verbs with Site Zero: Broken Masquerade
keywords (Blackfile, Brief, Anchor, etc.). Card-design agents: populate
``CALLBACKS`` with ~16 hybrids.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import (
    CardDefinition,
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
)

from .helpers import _mnr_card, _redact


# Sample card: hybrid procedure that fires Redact 1 followed by a 1-paperwork
# misfile against an opposing pending dossier (the SZB "Blackfile 1" pattern).
# Card-design agents replace / extend this list.
def _redact_and_blackfile(obj: GameObject, state: GameState, game=None) -> list[Event]:
    actual_game = game if game is not None else getattr(state, "_game", None)
    if actual_game is None:
        return []
    # Redact 1 first.
    events = scp.redact_opposing(actual_game, obj.controller, 1, source=obj.id)
    # Then a deterministic Blackfile-1: misfile the first opposing pending
    # dossier we find (matches the SZB Blackfile sample's iteration order).
    opponent = next(
        (
            pid for pid, player in state.players.items()
            if pid != obj.controller and not getattr(player, "has_lost", False)
        ),
        None,
    )
    if opponent is None:
        return events
    for cand in state.objects.values():
        if cand.controller != opponent:
            continue
        if cand.state.scp_status != "pending":
            continue
        ok, _msg, mis_events = scp.misfile_dossier(
            actual_game, obj.controller, cand.id, amount=1, source=obj.id,
        )
        if ok:
            events.extend(mis_events)
            break
    return events


_ANTIMEMETIC_AUDIT = _mnr_card(
    "MNR Antimemetic Audit",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Redaction", "Audit"},
    text="Redact 1 and Blackfile 1: each opponent discards a card; add paperwork to one opposing pending dossier.",
    effect=_redact_and_blackfile,
    rarity="uncommon",
    archetype="redaction_press",
    keywords={"Blackfile", "Redact"},
)


CALLBACKS: list[CardDefinition] = [
    _ANTIMEMETIC_AUDIT,
]
