"""CATS — Sleek-category Cats (8 cards).

Sleek cats install the Sleek trick rule ("highest Value wins") when played as
Pounce. Mechanically they're the "normal cats" — clean, dignified, decisive.

Capabilities exercised: trick-time triggers (on_win, on_lose), pile-time
triggers (on_enter_pile), and a few vanilla cards.
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


# ---------------------------------------------------------------------------
# Helper: build a CATS_TRICK_RESOLVE on_win trigger
# ---------------------------------------------------------------------------

def _on_win_trigger(obj: GameObject, react_fn):
    """Build a REACT interceptor that fires when this object's card wins a trick.

    react_fn(event, state) -> list[Event] is invoked when the per-card phase
    'on_win' resolve event names this card_id.
    """
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_TRICK_RESOLVE:
            return False
        return ev.payload.get("phase") == "on_win" and ev.payload.get("card_id") == obj.id

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


def _on_lose_trigger(obj: GameObject, react_fn):
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_TRICK_RESOLVE:
            return False
        return ev.payload.get("phase") == "on_lose" and ev.payload.get("card_id") == obj.id

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


def _on_enter_pile_trigger(obj: GameObject, pile: str, react_fn):
    """REACT when this card enters the named pile."""
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_CLAIM_PILE:
            return False
        return ev.payload.get("card_id") == obj.id and ev.payload.get("pile") == pile

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
# Sleek 1: Mister Whiskers — peek when winning
# ---------------------------------------------------------------------------

def mister_whiskers_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        loser = ev.payload.get("winner")  # winner_id is on the master; on the per-card we'd derive
        # Per-card phase events don't carry "loser" directly; derive from trick
        trick = getattr(st, "cats_current_trick", {}) or {}
        loser_id = (
            trick.get("counter_player")
            if trick.get("pounce_player") == obj.controller
            else trick.get("pounce_player")
        )
        return [
            Event(
                type=EventType.LOOK_AT_HAND,
                payload={"player": obj.controller, "target": loser_id, "reason": "mister_whiskers"},
                source=obj.id,
            )
        ]
    return [_on_win_trigger(obj, react)]


MISTER_WHISKERS = make_cat_card(
    name="Mister Whiskers",
    value=7,
    category="Sleek",
    text="When Mister Whiskers wins a trick, peek at the opponent's hand. He has Opinions.",
    rarity="rare",
    setup_interceptors=mister_whiskers_setup,
)


# ---------------------------------------------------------------------------
# Sleek 2: Duchess Velvet — draw on win
# ---------------------------------------------------------------------------

def duchess_velvet_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "duchess_velvet"},
                source=obj.id,
            )
        ]
    return [_on_win_trigger(obj, react)]


DUCHESS_VELVET = make_cat_card(
    name="Duchess Velvet",
    value=6,
    category="Sleek",
    text="When Duchess Velvet wins a trick, draw a card. Velveteen is a lifestyle.",
    rarity="uncommon",
    setup_interceptors=duchess_velvet_setup,
)


# ---------------------------------------------------------------------------
# Sleek 3: Mittens McSophisticated — territory bonus
# ---------------------------------------------------------------------------

def mittens_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        # Marker: when entering Territory, demand attention as well.
        return [
            Event(
                type=EventType.CATS_PILE_ACTIVATE,
                payload={"player": obj.controller, "card_id": obj.id, "pile": "pile_attention", "reason": "mittens_demand"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_territory", react)]


MITTENS_MCSOPHISTICATED = make_cat_card(
    name="Mittens McSophisticated",
    value=5,
    category="Sleek",
    text="When Mittens enters your Territory pile, also drop a marker in your Attention pile. The couch is HERS.",
    rarity="uncommon",
    setup_interceptors=mittens_setup,
)


# ---------------------------------------------------------------------------
# Sleek 4: Lord Tufts — lose-then-rebound
# ---------------------------------------------------------------------------

def lord_tufts_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "lord_tufts_consolation"},
                source=obj.id,
            )
        ]
    return [_on_lose_trigger(obj, react)]


LORD_TUFTS = make_cat_card(
    name="Lord Tufts",
    value=3,
    category="Sleek",
    text="When Lord Tufts loses a trick, draw a card. The dignity remains.",
    rarity="common",
    setup_interceptors=lord_tufts_setup,
)


# ---------------------------------------------------------------------------
# Sleek 5: The Brigadier — high value, no effect (vanilla)
# ---------------------------------------------------------------------------

THE_BRIGADIER = make_cat_card(
    name="The Brigadier",
    value=9,
    category="Sleek",
    text="A cat of considerable bearing. No further commentary required.",
    rarity="uncommon",
)


# ---------------------------------------------------------------------------
# Sleek 6: Tabitha — vanilla low
# ---------------------------------------------------------------------------

TABITHA = make_cat_card(
    name="Tabitha",
    value=2,
    category="Sleek",
    text="Just Tabitha.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Sleek 7: Crumpet — vanilla mid
# ---------------------------------------------------------------------------

CRUMPET = make_cat_card(
    name="Crumpet",
    value=4,
    category="Sleek",
    text="Crumpet, as is her birthright, sits.",
    rarity="common",
)


# ---------------------------------------------------------------------------
# Sleek 8: The Magnificent Bartholomew — top of curve, on-enter-nap fires.
# ---------------------------------------------------------------------------

def bartholomew_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 2, "reason": "bartholomew_nap"},
                source=obj.id,
            )
        ]
    return [_on_enter_pile_trigger(obj, "pile_nap", react)]


THE_MAGNIFICENT_BARTHOLOMEW = make_cat_card(
    name="The Magnificent Bartholomew",
    value=10,
    category="Sleek",
    text="When Bartholomew enters your Nap pile, draw 2 cards. He sleeps for ALL of us.",
    rarity="rare",
    setup_interceptors=bartholomew_setup,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

SLEEK_CATS = [
    MISTER_WHISKERS,
    DUCHESS_VELVET,
    MITTENS_MCSOPHISTICATED,
    LORD_TUFTS,
    THE_BRIGADIER,
    TABITHA,
    CRUMPET,
    THE_MAGNIFICENT_BARTHOLOMEW,
]
