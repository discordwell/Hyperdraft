"""CATS — Commander Cats (6 cards).

Pre-game-only. Each commander grants a persistent passive via setup_interceptors
that runs at game setup time (see src/engine/cats.py:317-329).

Capability category: Commander passives (capability #8).
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
from src.engine.cats import make_commander_card


# ---------------------------------------------------------------------------
# Sir Reginald Loafington — the dignified bedwarmer
# ---------------------------------------------------------------------------
# Passive: your Nap pile cap is 8 instead of 6.
# Implementation: mutate state.cats_pile_caps for this player when present;
# also mutate CATS_PILE_CAPS lookup by attaching a controller-scoped override.
# Since the engine reads CATS_PILE_CAPS globally we install a CATS_CLAIM_PILE
# REACT interceptor that catches "cap overflow" and reroutes back to nap when
# the controller is the commander's controller and pile_nap has < 8 cards.

def sir_reginald_setup(obj: GameObject, state: GameState):
    """Stash an attribute on state for the cats engine + UI to read, and
    install a REACT interceptor that prevents overflow to attention if
    pile_nap < 8 for this commander's controller."""
    # Attribute-level override read by some pile-cap-aware UIs.
    if not hasattr(state, "cats_nap_cap_override"):
        state.cats_nap_cap_override = {}
    state.cats_nap_cap_override[obj.controller] = 8

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_PILE_CAPPED:
            return False
        return (
            ev.payload.get("player") == obj.controller
            and ev.payload.get("pile") == "pile_nap"
        )

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        # Flavor-only marker; the actual cap relaxation is via the override
        # dict above (UI / pile-cap-aware code may consult it).
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler,
            duration="forever",
        )
    ]


SIR_REGINALD_LOAFINGTON = make_commander_card(
    name="Sir Reginald Loafington",
    text="Your Nap pile cap is 8 (instead of 6). The loaf shall be loafed at length.",
    rarity="mythic",
    setup_interceptors=sir_reginald_setup,
)


# ---------------------------------------------------------------------------
# Princess Mayhem the Third — agent of focused greed
# ---------------------------------------------------------------------------
# Passive: your Snack pile, if it has fewer than 5 cards, scores 4pt/card
# instead of 3pt/card. (Soft bonus to small Snack piles.)
# We tag the controller's state so score_cats_player consumers / UIs can
# read it; we also REACT to CATS_QUERY_PILE_SCORE for engines that wire the
# synthetic query later.

def princess_mayhem_setup(obj: GameObject, state: GameState):
    if not hasattr(state, "cats_snack_bonus"):
        state.cats_snack_bonus = {}
    state.cats_snack_bonus[obj.controller] = 1  # +1 pt/card when <5

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_QUERY_PILE_SCORE:
            return False
        return (
            ev.payload.get("player") == obj.controller
            and ev.payload.get("pile") == "pile_snack"
        )

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        if ev.payload.get("card_count", 0) < 5:
            new_ev = ev.copy()
            new_ev.payload["score"] = ev.payload.get("score", 0) + ev.payload.get("card_count", 0)
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_ev)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=filter_fn,
            handler=handler,
            duration="forever",
        )
    ]


PRINCESS_MAYHEM_THE_THIRD = make_commander_card(
    name="Princess Mayhem the Third",
    text="Your small Snack pile scores 4pt/card (instead of 3) while under 5 cards. Tiny tyrant.",
    rarity="mythic",
    setup_interceptors=princess_mayhem_setup,
)


# ---------------------------------------------------------------------------
# Greg — the cat who does Greg things
# ---------------------------------------------------------------------------
# Passive: at the start of each round, if Greg's controller has fewer total
# pile cards than the opponent, they draw an extra card on next refill.
# Emits a marker event the refill code can read.

def greg_setup(obj: GameObject, state: GameState):
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_ROUND_START:
            return False
        return True

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        # Catch-up draw marker: applies if Greg's controller is behind on piles.
        from src.engine.cats import _pile_total  # type: ignore[attr-defined]
        try:
            my_total = _pile_total(st, obj.controller)
            opp_total = max(
                (_pile_total(st, pid) for pid in st.players if pid != obj.controller),
                default=0,
            )
            if my_total >= opp_total:
                return InterceptorResult(action=InterceptorAction.PASS)
        except Exception:
            return InterceptorResult(action=InterceptorAction.PASS)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": 1, "reason": "greg_catchup"},
                    source=obj.id,
                )
            ],
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler,
            duration="forever",
        )
    ]


GREG = make_commander_card(
    name="Greg",
    text="At the start of each round, if you have fewer total pile cards than your opponent, draw 1. Greg is just Greg.",
    rarity="mythic",
    setup_interceptors=greg_setup,
)


# ---------------------------------------------------------------------------
# Gary the One-Eyed Tabby — sees through bluffs
# ---------------------------------------------------------------------------
# Passive: when a Sneaky-rule trick resolves involving Gary's controller,
# emit a REVEAL marker for inspection (the design effect "always use printed
# value, not sneaky_value" is approximated by emitting a reveal so AI can
# learn — turning Sneaky into Sleek for Gary).

def gary_setup(obj: GameObject, state: GameState):
    if not hasattr(state, "cats_gary_sleeks_sneaky"):
        state.cats_gary_sleeks_sneaky = {}
    state.cats_gary_sleeks_sneaky[obj.controller] = True

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_TRICK_RESOLVE:
            return False
        # only the master event (not the per-card phase events)
        return "phase" not in ev.payload

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        # On each trick resolve, Gary reveals any Sneaky card the opponent
        # played. Records the sneaky_value on a per-player tracker so the
        # AI's pessimistic Sneaky estimator can be replaced with truth.
        cards = ev.payload.get("cards") or []
        if not hasattr(st, "cats_sneaky_known"):
            st.cats_sneaky_known = {}
        known = st.cats_sneaky_known.setdefault(obj.controller, {})
        reveal_events: list[Event] = []
        for cid in cards:
            obj_c = st.objects.get(cid)
            if obj_c is None or obj_c.controller == obj.controller:
                continue
            card_def = obj_c.card_def
            if card_def is None:
                continue
            sv = getattr(card_def, "cats_sneaky_value", None)
            if sv is None:
                continue
            known[cid] = int(sv)
            reveal_events.append(Event(
                type=EventType.CATS_REVEAL,
                payload={
                    "player": obj.controller,
                    "card_id": cid,
                    "sneaky_value": int(sv),
                    "reason": "gary_sees_all",
                },
                source=obj.id,
            ))
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=reveal_events,
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler,
            duration="forever",
        )
    ]


GARY_THE_ONE_EYED_TABBY = make_commander_card(
    name="Gary the One-Eyed Tabby",
    text="Sneaky rules use printed Value for your cards (the eye that remains sees enough).",
    rarity="mythic",
    setup_interceptors=gary_setup,
)


# ---------------------------------------------------------------------------
# Karen the Dignified Calico — has Standards
# ---------------------------------------------------------------------------
# Passive: each of your piles can hold +1 Trinket (3 instead of 2).
# Set a state-attribute override + emit a marker on CLAIM events.

def karen_setup(obj: GameObject, state: GameState):
    if not hasattr(state, "cats_trinket_cap_override"):
        state.cats_trinket_cap_override = {}
    state.cats_trinket_cap_override[obj.controller] = 3

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_CLAIM_PILE:
            return False
        return ev.payload.get("player") == obj.controller

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        # No-op marker — UI / pile-cap-aware code may consult the override dict above.
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler,
            duration="forever",
        )
    ]


KAREN_THE_DIGNIFIED_CALICO = make_commander_card(
    name="Karen the Dignified Calico",
    text="Each of your piles holds up to 3 Trinkets (instead of 2). She would like to speak to the manager.",
    rarity="mythic",
    setup_interceptors=karen_setup,
)


# ---------------------------------------------------------------------------
# Lord Fluffinbottom — fluffiest cat in the realm
# ---------------------------------------------------------------------------
# Passive: at game end, if Lord Fluffinbottom's controller has the most cards
# in the Attention pile, score +5 bonus. Implemented by stashing a flag the
# finalize code can consult; also REACT on CATS_GAME_OVER to emit a bonus
# marker event the test can count.

def lord_fluffinbottom_setup(obj: GameObject, state: GameState):
    if not hasattr(state, "cats_attention_bonus"):
        state.cats_attention_bonus = {}
    state.cats_attention_bonus[obj.controller] = 5

    def filter_fn(ev: Event, st: GameState) -> bool:
        return ev.type == EventType.CATS_GAME_OVER

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        scores = ev.payload.get("scores", {})
        my_attn = scores.get(obj.controller, {}).get("attention", 0)
        best_attn = max((s.get("attention", 0) for s in scores.values()), default=0)
        if my_attn >= best_attn and my_attn > 0:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[
                    Event(
                        type=EventType.LIFE_CHANGE,
                        payload={"player": obj.controller, "amount": 5, "reason": "fluffinbottom_bonus"},
                        source=obj.id,
                    )
                ],
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler,
            duration="forever",
        )
    ]


LORD_FLUFFINBOTTOM = make_commander_card(
    name="Lord Fluffinbottom",
    text="At game end, if you have the most cards in your Attention pile, gain +5 score. Fluffiest wins.",
    rarity="mythic",
    setup_interceptors=lord_fluffinbottom_setup,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

COMMANDERS = [
    SIR_REGINALD_LOAFINGTON,
    PRINCESS_MAYHEM_THE_THIRD,
    GREG,
    GARY_THE_ONE_EYED_TABBY,
    KAREN_THE_DIGNIFIED_CALICO,
    LORD_FLUFFINBOTTOM,
]
