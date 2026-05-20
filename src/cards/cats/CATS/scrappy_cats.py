"""CATS — Scrappy-category Cats (7 cards).

Scrappy cats install the Scrappy rule when played as Pounce: LOWEST Value
wins. The scrappy cat wins by being the underdog. Effects often reward
losing tricks or playing junk cards.

Capabilities exercised: trick-time triggers (on_lose), pile-time triggers
(on_enter_pile), and vanilla cards.
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
# Scrappy 1: Gary Junior — vanilla low (scrappy bait)
# ---------------------------------------------------------------------------

GARY_JUNIOR = make_cat_card(
    name="Gary Junior",
    value=1,
    category="Scrappy",
    text="Gary's son. Gary's eye. (Different eye.)",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Scrappy 2: The Alley Phantom — on-lose draw
# ---------------------------------------------------------------------------

def alley_phantom_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "alley_phantom_skulk"},
                source=obj.id,
            )
        ]
    return [_on_lose_trigger(obj, react)]


THE_ALLEY_PHANTOM = make_cat_card(
    name="The Alley Phantom",
    value=2,
    category="Scrappy",
    text="When the Phantom loses a trick, draw a card. She prefers the shadows anyway.",
    rarity="uncommon",
    setup_interceptors=alley_phantom_setup,
)


# ---------------------------------------------------------------------------
# Scrappy 3: One-Tooth Eduardo — vanilla mid
# ---------------------------------------------------------------------------

ONE_TOOTH_EDUARDO = make_cat_card(
    name="One-Tooth Eduardo",
    value=4,
    category="Scrappy",
    text="Eduardo has one tooth. It's enough. It's plenty.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Scrappy 4: Princess Mayhem the Fourth — on-win, snack-pile bonus
# (Naming chain: I (origin lost), II (also lost), III is Commander, IV plays.)
# ---------------------------------------------------------------------------

def mayhem_iv_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "mayhem_iv_chaos"},
                source=obj.id,
            )
        ]
    return [_on_win_trigger(obj, react)]


PRINCESS_MAYHEM_THE_FOURTH = make_cat_card(
    name="Princess Mayhem the Fourth",
    value=3,
    category="Scrappy",
    text="When Princess Mayhem the Fourth wins a trick, draw a card. The Mayhem dynasty endures.",
    rarity="rare",
    setup_interceptors=mayhem_iv_setup,
)


# ---------------------------------------------------------------------------
# Scrappy 5: The Yowling Stranger — vanilla high (scrappy bomb if rule flips)
# ---------------------------------------------------------------------------

THE_YOWLING_STRANGER = make_cat_card(
    name="The Yowling Stranger",
    value=8,
    category="Scrappy",
    text="No one knows this cat. Everyone knows this cat. The neighborhood weeps at 4 a.m.",
    rarity="uncommon",
)


# ---------------------------------------------------------------------------
# Scrappy 6: The Bedraggled Earl — on-enter-snack draw (snack synergy)
# ---------------------------------------------------------------------------

def bedraggled_earl_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "bedraggled_earl_snack"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_snack", react)]


THE_BEDRAGGLED_EARL = make_cat_card(
    name="The Bedraggled Earl",
    value=5,
    category="Scrappy",
    text="When the Earl enters your Snack pile, draw a card. Title intact. Dignity, less so.",
    rarity="rare",
    setup_interceptors=bedraggled_earl_setup,
)


# ---------------------------------------------------------------------------
# Scrappy 7: Maximum Carnage — top of curve, on-win and on-lose both fire
# ---------------------------------------------------------------------------

def maximum_carnage_setup(obj: GameObject, state: GameState):
    def react_win(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": obj.controller, "amount": 1, "reason": "maximum_carnage_win"},
                source=obj.id,
            )
        ]

    def react_lose(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "maximum_carnage_lose"},
                source=obj.id,
            )
        ]

    return [
        _on_win_trigger(obj, react_win),
        _on_lose_trigger(obj, react_lose),
    ]


MAXIMUM_CARNAGE = make_cat_card(
    name="Maximum Carnage",
    value=10,
    category="Scrappy",
    text="Win: +1 score. Lose: draw a card. Either way, the curtains are ruined.",
    rarity="mythic",
    setup_interceptors=maximum_carnage_setup,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

SCRAPPY_CATS = [
    GARY_JUNIOR,
    THE_ALLEY_PHANTOM,
    ONE_TOOTH_EDUARDO,
    PRINCESS_MAYHEM_THE_FOURTH,
    THE_YOWLING_STRANGER,
    THE_BEDRAGGLED_EARL,
    MAXIMUM_CARNAGE,
]
