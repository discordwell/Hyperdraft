"""CATS — Sneaky-category Cats (7 cards).

Sneaky cats install the Sneaky rule when played as Pounce: comparison is by
each card's HIDDEN ``sneaky_value`` field. Published Value is a bluff. The
mind game is: opponent doesn't know who actually wins until resolution.

Capabilities exercised: trick-time triggers, pile-time triggers, vanilla.
The sneaky_value is set per-card via make_cat_card's sneaky_value=N kwarg
and intentionally diverges from public Value to create the bluff.
"""

from __future__ import annotations

from src.engine import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    new_id,
)
from src.engine.cats import make_cat_card

from .sleek_cats import _on_win_trigger, _on_lose_trigger, _on_enter_pile_trigger


# ---------------------------------------------------------------------------
# Sneaky 1: Whispertoes — looks low, plays high
# ---------------------------------------------------------------------------

def whispertoes_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "whispertoes_smug"},
                source=obj.id,
            )
        ]
    return [_on_win_trigger(obj, react)]


WHISPERTOES = make_cat_card(
    name="Whispertoes",
    value=2,
    category="Sneaky",
    text="Looks like nothing. Bites like everything. Draw when wins a trick.",
    rarity="rare",
    setup_interceptors=whispertoes_setup,
    sneaky_value=9,
)


# ---------------------------------------------------------------------------
# Sneaky 2: The Shadow Loaf — vanilla low public, high private
# ---------------------------------------------------------------------------

THE_SHADOW_LOAF = make_cat_card(
    name="The Shadow Loaf",
    value=1,
    category="Sneaky",
    text="A loaf in the dark. Best not stepped on.",
    rarity="uncommon",
    sneaky_value=8,
)


# ---------------------------------------------------------------------------
# Sneaky 3: Midnight Pancake — vanilla
# ---------------------------------------------------------------------------

MIDNIGHT_PANCAKE = make_cat_card(
    name="Midnight Pancake",
    value=4,
    category="Sneaky",
    text="The hours between 1am and 4am belong to Pancake. Bring offerings.",
    rarity="common",
    sneaky_value=5,
)


# ---------------------------------------------------------------------------
# Sneaky 4: Madam Inkblot — high public, low private (the trap)
# ---------------------------------------------------------------------------

def madam_inkblot_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "inkblot_consolation"},
                source=obj.id,
            )
        ]
    return [_on_lose_trigger(obj, react)]


# Nerf: draw on lose reduced from 2 -> 1 (deckbuilding-pass flagged her as the
# single strongest card in the pool — positive in BOTH win and lose paths).
MADAM_INKBLOT = make_cat_card(
    name="Madam Inkblot",
    value=7,
    category="Sneaky",
    text="Looks fearsome. Is not. When she loses a trick, draw a card. Sacrifices were made.",
    rarity="rare",
    setup_interceptors=madam_inkblot_setup,
    sneaky_value=2,
)


# ---------------------------------------------------------------------------
# Sneaky 5: Knives — vanilla mid
# ---------------------------------------------------------------------------

KNIVES = make_cat_card(
    name="Knives",
    value=5,
    category="Sneaky",
    text="Yes, the name fits. No, do not pet her.",
    rarity="common",
    sneaky_value=6,
)


# ---------------------------------------------------------------------------
# Sneaky 6: The Penumbra Twin — sneaky high
# ---------------------------------------------------------------------------

def penumbra_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "penumbra_slipshadow"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_nap", react)]


THE_PENUMBRA_TWIN = make_cat_card(
    name="The Penumbra Twin",
    value=6,
    category="Sneaky",
    text="When this enters your Nap pile, draw a card. She sleeps in both worlds.",
    rarity="uncommon",
    setup_interceptors=penumbra_setup,
    sneaky_value=7,
)


# ---------------------------------------------------------------------------
# Sneaky 7: The Unobserved — top of the sneaky curve. Vanilla bomb.
# ---------------------------------------------------------------------------

THE_UNOBSERVED = make_cat_card(
    name="The Unobserved",
    value=9,
    category="Sneaky",
    text="By the time you see this cat, this cat has already won.",
    rarity="mythic",
    sneaky_value=10,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

SNEAKY_CATS = [
    WHISPERTOES,
    THE_SHADOW_LOAF,
    MIDNIGHT_PANCAKE,
    MADAM_INKBLOT,
    KNIVES,
    THE_PENUMBRA_TWIN,
    THE_UNOBSERVED,
]
