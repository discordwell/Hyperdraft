"""CATS — Fluffy-category Cats (8 cards).

Fluffy cats install the Fluffy rule when played as Pounce: highest Value wins,
ties go to whoever has fewer total cards across scoring piles (the underdog
cat wins social ties). Mechanically they reward "behind" play and have
pile-time triggers that scale by pile size.

Capabilities exercised: pile-time triggers (on_pile_cap_reached),
round-time triggers (on_round_start, on_round_end), some vanilla.
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

from .sleek_cats import _on_win_trigger, _on_enter_pile_trigger, _on_lose_trigger


# ---------------------------------------------------------------------------
# Helper: on round-start / round-end trigger
# ---------------------------------------------------------------------------

def _on_round_start_trigger(obj: GameObject, react_fn):
    def filter_fn(ev: Event, st: GameState) -> bool:
        return ev.type == EventType.CATS_ROUND_START

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        new_events = react_fn(ev, st) or []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration="forever",
    )


def _on_round_end_trigger(obj: GameObject, react_fn):
    def filter_fn(ev: Event, st: GameState) -> bool:
        return ev.type == EventType.CATS_ROUND_END

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        new_events = react_fn(ev, st) or []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration="forever",
    )


def _on_pile_cap_trigger(obj: GameObject, pile: str, react_fn):
    """REACT when ANY player's named pile hits its cap (filter on payload's player)."""
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_PILE_CAPPED:
            return False
        return (
            ev.payload.get("player") == obj.controller
            and ev.payload.get("pile") == pile
        )

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        new_events = react_fn(ev, st) or []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration="forever",
    )


# ---------------------------------------------------------------------------
# Fluffy 1: Sir Reginald Loafington II — pile-cap reward
# (The character also exists as a Commander; this is "II", his son.)
# ---------------------------------------------------------------------------

def reginald_ii_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": obj.controller, "amount": 3, "reason": "reginald_ii_nap_cap"},
                source=obj.id,
            )
        ]
    return [_on_pile_cap_trigger(obj, "pile_nap", react)]


SIR_REGINALD_LOAFINGTON_II = make_cat_card(
    name="Sir Reginald Loafington II",
    value=5,
    category="Fluffy",
    text="When your Nap pile fills, gain +3 score. The loaf legacy continues.",
    rarity="rare",
    setup_interceptors=reginald_ii_setup,
)


# ---------------------------------------------------------------------------
# Fluffy 2: Cinnamon Bun — round-start fluff
# ---------------------------------------------------------------------------

def cinnamon_bun_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        round_no = ev.payload.get("round_number", 0)
        if round_no % 3 != 0:
            return []
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "cinnamon_bun_warmth"},
                source=obj.id,
            )
        ]
    return [_on_round_start_trigger(obj, react)]


CINNAMON_BUN = make_cat_card(
    name="Cinnamon Bun",
    value=4,
    category="Fluffy",
    text="Every 3 rounds, gain a card from somewhere warm. A bun, you understand.",
    rarity="uncommon",
    setup_interceptors=cinnamon_bun_setup,
)


# ---------------------------------------------------------------------------
# Fluffy 3: Marshmallow — on-enter draw
# ---------------------------------------------------------------------------

def marshmallow_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "marshmallow_squish"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_territory", react)]


MARSHMALLOW = make_cat_card(
    name="Marshmallow",
    value=3,
    category="Fluffy",
    text="When Marshmallow enters your Territory pile, draw a card. He squishes most pleasingly.",
    rarity="common",
    setup_interceptors=marshmallow_setup,
)


# ---------------------------------------------------------------------------
# Fluffy 4: Sergeant Snuggles — vanilla anchor
# ---------------------------------------------------------------------------

SERGEANT_SNUGGLES = make_cat_card(
    name="Sergeant Snuggles",
    value=8,
    category="Fluffy",
    text="Reporting for duty. Duty is being snuggled.",
    rarity="uncommon",
)


# ---------------------------------------------------------------------------
# Fluffy 5: Pillow Princess — round-end bonus when you're behind
# ---------------------------------------------------------------------------

def pillow_princess_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        # Only if behind on total pile cards
        from src.engine.cats import _pile_total  # type: ignore[attr-defined]
        try:
            my_total = _pile_total(st, obj.controller)
            opp_total = max(
                (_pile_total(st, pid) for pid in st.players if pid != obj.controller),
                default=0,
            )
            if my_total >= opp_total:
                return []
        except Exception:
            return []
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "pillow_princess_solace"},
                source=obj.id,
            )
        ]
    return [_on_round_end_trigger(obj, react)]


PILLOW_PRINCESS = make_cat_card(
    name="Pillow Princess",
    value=6,
    category="Fluffy",
    text="At round end, if you're behind on pile cards, draw a card. She has been wronged.",
    rarity="rare",
    setup_interceptors=pillow_princess_setup,
)


# ---------------------------------------------------------------------------
# Fluffy 6: Biscuit — vanilla high
# ---------------------------------------------------------------------------

BISCUIT = make_cat_card(
    name="Biscuit",
    value=7,
    category="Fluffy",
    text="Biscuit kneads the air. Biscuit IS the bakery.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Fluffy 7: Toby the Tubster — value 1, fat and happy (vanilla)
# ---------------------------------------------------------------------------

TOBY_THE_TUBSTER = make_cat_card(
    name="Toby the Tubster",
    value=1,
    category="Fluffy",
    text="Toby is large. Toby has feelings about this. Toby continues.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Fluffy 8: Empress Pomf — top of curve, fires on win, draws AND life
# ---------------------------------------------------------------------------

def empress_pomf_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "empress_pomf"},
                source=obj.id,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": obj.controller, "amount": 2, "reason": "empress_pomf_grace"},
                source=obj.id,
            ),
        ]
    return [_on_win_trigger(obj, react)]


EMPRESS_POMF = make_cat_card(
    name="Empress Pomf",
    value=9,
    category="Fluffy",
    text="When Empress Pomf wins a trick, draw a card and gain 2 score. The fluff has spoken.",
    rarity="rare",
    setup_interceptors=empress_pomf_setup,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

FLUFFY_CATS = [
    SIR_REGINALD_LOAFINGTON_II,
    CINNAMON_BUN,
    MARSHMALLOW,
    SERGEANT_SNUGGLES,
    PILLOW_PRINCESS,
    BISCUIT,
    TOBY_THE_TUBSTER,
    EMPRESS_POMF,
]
