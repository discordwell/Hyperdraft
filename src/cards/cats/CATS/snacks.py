"""CATS — Snack cards (8 cards).

Snacks have a Value (typically low) and contribute to the trick comparison
normally. If a trick contains a Snack from either player, the winner is
forced to claim into their Snack pile (or attention if Snack is full).

Capabilities exercised: on-enter-pile triggers (capability #2), replacement-
effect-style logic (Snack pile forcing — engine-level, not card-level),
some vanilla snacks.
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
from src.engine.cats import make_snack_card

from .sleek_cats import _on_enter_pile_trigger


# ---------------------------------------------------------------------------
# Snack 1: Catnip Mouse — on-enter-snack: draw
# ---------------------------------------------------------------------------

def catnip_mouse_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "catnip_mouse_high"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_snack", react)]


CATNIP_MOUSE = make_snack_card(
    name="Catnip Mouse",
    value=2,
    text="When Catnip Mouse enters your Snack pile, draw a card. The high is real.",
    rarity="common",
    setup_interceptors=catnip_mouse_setup,
)


# ---------------------------------------------------------------------------
# Snack 2: Tuna Can — vanilla low
# ---------------------------------------------------------------------------

TUNA_CAN = make_snack_card(
    name="Tuna Can",
    value=1,
    text="The can opener is the call to worship. Tuna Can demands snack-pile placement.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Snack 3: The Forbidden Houseplant — on-enter, attention bump
# ---------------------------------------------------------------------------

def forbidden_houseplant_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.CATS_PILE_ACTIVATE,
                payload={
                    "player": obj.controller,
                    "card_id": obj.id,
                    "pile": "pile_attention",
                    "reason": "forbidden_houseplant",
                },
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_snack", react)]


THE_FORBIDDEN_HOUSEPLANT = make_snack_card(
    name="The Forbidden Houseplant",
    value=2,
    text="When this enters your Snack pile, drop a marker on Attention. NO. NOT THAT ONE.",
    rarity="uncommon",
    setup_interceptors=forbidden_houseplant_setup,
)


# ---------------------------------------------------------------------------
# Snack 4: A Single Crumb — vanilla
# ---------------------------------------------------------------------------

A_SINGLE_CRUMB = make_snack_card(
    name="A Single Crumb",
    value=1,
    text="It fell. It is now hers. (His. Theirs. The cat's.)",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Snack 5: The Whole Roast Chicken — value 3, draws 2 on entry
# ---------------------------------------------------------------------------

def roast_chicken_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 2, "reason": "roast_chicken_feast"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_snack", react)]


THE_WHOLE_ROAST_CHICKEN = make_snack_card(
    name="The Whole Roast Chicken",
    value=3,
    text="When this enters your Snack pile, draw 2 cards. This was meant for the family.",
    rarity="rare",
    setup_interceptors=roast_chicken_setup,
)


# ---------------------------------------------------------------------------
# Snack 6: Empty Yogurt Cup — emit a marker on entry
# ---------------------------------------------------------------------------

def yogurt_cup_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        # Marker that opponents' next Snack pile should be smaller
        return [
            Event(
                type=EventType.CATS_PILE_ACTIVATE,
                payload={
                    "player": obj.controller,
                    "card_id": obj.id,
                    "pile": "pile_snack",
                    "reason": "yogurt_cup_lick",
                },
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_snack", react)]


EMPTY_YOGURT_CUP = make_snack_card(
    name="Empty Yogurt Cup",
    value=1,
    text="Head trapped. Cat undeterred. Marker placed on the Snack pile.",
    rarity="uncommon",
    setup_interceptors=yogurt_cup_setup,
)


# ---------------------------------------------------------------------------
# Snack 7: The Disputed Slice of Cheese — vanilla mid
# ---------------------------------------------------------------------------

THE_DISPUTED_SLICE_OF_CHEESE = make_snack_card(
    name="The Disputed Slice of Cheese",
    value=2,
    text="Was on the floor for 0.4 seconds. It is now contested international territory.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Snack 8: That One Thing Off The Counter — top value
# ---------------------------------------------------------------------------

def counter_thing_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": obj.controller, "amount": 2, "reason": "counter_thing_victory"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_snack", react)]


THAT_ONE_THING_OFF_THE_COUNTER = make_snack_card(
    name="That One Thing Off The Counter",
    value=3,
    text="The cat planned this. The cat has been planning this for HOURS. Gain +2 score when claimed.",
    rarity="rare",
    setup_interceptors=counter_thing_setup,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

SNACKS = [
    CATNIP_MOUSE,
    TUNA_CAN,
    THE_FORBIDDEN_HOUSEPLANT,
    A_SINGLE_CRUMB,
    THE_WHOLE_ROAST_CHICKEN,
    EMPTY_YOGURT_CUP,
    THE_DISPUTED_SLICE_OF_CHEESE,
    THAT_ONE_THING_OFF_THE_COUNTER,
]
