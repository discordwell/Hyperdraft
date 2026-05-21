"""CATS — Trinket cards (6 cards).

Trinkets are persistent pile attachments. They install a TRANSFORM-priority
interceptor on CATS_QUERY_PILE_SCORE that rewrites the score for the pile
they're attached to. They also fire on-enter-pile triggers when the pile
they attach to is updated.

Capabilities exercised: static pile modifiers (capability #4 — Trinket
score mods), activated abilities (capability #7 — Trinkets often grant
pile-tap activations).
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
from src.engine.cats import make_trinket_card


# ---------------------------------------------------------------------------
# Helper: a TRANSFORM-priority interceptor on CATS_QUERY_PILE_SCORE
# ---------------------------------------------------------------------------

def _pile_score_mod(obj: GameObject, pile: str, mod_fn):
    """Build a TRANSFORM interceptor that rewrites this player's pile score.

    mod_fn(score, card_count, state) -> new_score.
    """
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_QUERY_PILE_SCORE:
            return False
        return (
            ev.payload.get("player") == obj.controller
            and ev.payload.get("pile") == pile
        )

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        old_score = ev.payload.get("score", 0)
        card_count = ev.payload.get("card_count", 0)
        new_score = mod_fn(old_score, card_count, st)
        if new_score == old_score:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_ev = ev.copy()
        new_ev.payload["score"] = new_score
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_ev)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        duration="forever",
    )


def _on_claim_trinket_pile(obj: GameObject, pile: str, react_fn):
    """REACT when a claim event sends a card into the named pile (any card)."""
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_CLAIM_PILE:
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
# Trinket 1: Yarn Ball — Territory: +1pt per Sleek cat in pile
# ---------------------------------------------------------------------------

def yarn_ball_setup(obj: GameObject, state: GameState):
    def mod_fn(score, card_count, st):
        # Count Sleek cats in this pile
        from src.engine.types import CardType
        piles = getattr(st, "cats_piles", {}).get(obj.controller, {})
        terr = piles.get("pile_territory", [])
        bonus = 0
        for cid in terr:
            o = st.objects.get(cid)
            if o is None or o.card_def is None:
                continue
            if getattr(o.card_def, "cats_category", None) == "Sleek":
                bonus += 1
        return score + bonus

    return [_pile_score_mod(obj, "pile_territory", mod_fn)]


YARN_BALL = make_trinket_card(
    name="Yarn Ball",
    text="Territory pile: +1 score per Sleek cat in this pile. The yarn is now territory.",
    rarity="uncommon",
    attaches_to="pile_territory",
    setup_interceptors=yarn_ball_setup,
)


# ---------------------------------------------------------------------------
# Trinket 2: Sunbeam — Nap: pile cap is 8 (override + score bonus)
# ---------------------------------------------------------------------------

def sunbeam_setup(obj: GameObject, state: GameState):
    def mod_fn(score, card_count, st):
        # Nerf: flat +2 -> flat +1 to dampen the Sunbeam + Heated Blanket
        # stack on Nap (was +14 from trinkets alone).
        return score + 1

    if not hasattr(state, "cats_nap_cap_override"):
        state.cats_nap_cap_override = {}
    # Don't override if commander already increased it (cap is whatever's higher).
    cur = state.cats_nap_cap_override.get(obj.controller, 6)
    state.cats_nap_cap_override[obj.controller] = max(cur, 8)

    return [_pile_score_mod(obj, "pile_nap", mod_fn)]


SUNBEAM = make_trinket_card(
    name="Sunbeam",
    text="Nap pile: cap is 8 (instead of 6); +1 score. The sunbeam moves; the cat follows. This is law.",
    rarity="rare",
    attaches_to="pile_nap",
    setup_interceptors=sunbeam_setup,
)


# ---------------------------------------------------------------------------
# Trinket 3: Window Perch — Territory: draw 2 when capped
# ---------------------------------------------------------------------------

def window_perch_setup(obj: GameObject, state: GameState):
    # Score mod: small bonus
    def mod_fn(score, card_count, st):
        return score + 1 if card_count >= 4 else score

    # On-claim react: when territory hits cap, draw 2
    def react_claim(ev: Event, st: GameState):
        piles = getattr(st, "cats_piles", {}).get(obj.controller, {})
        terr = piles.get("pile_territory", [])
        if len(terr) >= 8:
            return [
                Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": 2, "reason": "window_perch_full"},
                    source=obj.id,
                )
            ]
        return []

    return [
        _pile_score_mod(obj, "pile_territory", mod_fn),
        _on_claim_trinket_pile(obj, "pile_territory", react_claim),
    ]


WINDOW_PERCH = make_trinket_card(
    name="Window Perch",
    text="Territory pile: when capped, draw 2 cards. +1 score at 4+ cards. The view is mine.",
    rarity="rare",
    attaches_to="pile_territory",
    setup_interceptors=window_perch_setup,
)


# ---------------------------------------------------------------------------
# Trinket 4: The Cardboard Box — vanilla-ish: small Snack pile score bump
# ---------------------------------------------------------------------------

def cardboard_box_setup(obj: GameObject, state: GameState):
    def mod_fn(score, card_count, st):
        if card_count < 5:
            return score + 1
        return score

    return [_pile_score_mod(obj, "pile_snack", mod_fn)]


THE_CARDBOARD_BOX = make_trinket_card(
    name="The Cardboard Box",
    text="Snack pile: +1 score while under 5 cards. The box came with the snacks. THE BOX IS THE POINT.",
    rarity="common",
    attaches_to="pile_snack",
    setup_interceptors=cardboard_box_setup,
)


# ---------------------------------------------------------------------------
# Trinket 5: The Stolen Hair Tie — Attention boost
# ---------------------------------------------------------------------------

def hair_tie_setup(obj: GameObject, state: GameState):
    def react_claim(ev: Event, st: GameState):
        # When ANY claim happens, also drop a marker into attention.
        return [
            Event(
                type=EventType.CATS_PILE_ACTIVATE,
                payload={
                    "player": obj.controller,
                    "card_id": obj.id,
                    "pile": "pile_attention",
                    "reason": "hair_tie_steal",
                },
                source=obj.id,
            )
        ]

    # Attach to attention pile
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CATS_CLAIM_PILE:
            return False
        return ev.payload.get("player") == obj.controller

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=react_claim(ev, st),
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


THE_STOLEN_HAIR_TIE = make_trinket_card(
    name="The Stolen Hair Tie",
    text="Attention pile: whenever you claim a trick, mark Attention. Where did the tie go. (You know where.)",
    rarity="uncommon",
    attaches_to="pile_attention",
    setup_interceptors=hair_tie_setup,
)


# ---------------------------------------------------------------------------
# Trinket 6: The Heated Blanket — Nap pile bonus, lots of score
# ---------------------------------------------------------------------------

def heated_blanket_setup(obj: GameObject, state: GameState):
    def mod_fn(score, card_count, st):
        # Nerf: capped Nap bonus from +4 to +3 to keep the
        # Sunbeam + Heated Blanket stack from going degenerate
        # (was +14 from trinkets alone in Naptime Tyrants).
        return score + min(card_count, 3)

    return [_pile_score_mod(obj, "pile_nap", mod_fn)]


THE_HEATED_BLANKET = make_trinket_card(
    name="The Heated Blanket",
    text="Nap pile: +1 score per card (up to +3). It got warm. He REMAINS.",
    rarity="mythic",
    attaches_to="pile_nap",
    setup_interceptors=heated_blanket_setup,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

TRINKETS = [
    YARN_BALL,
    SUNBEAM,
    WINDOW_PERCH,
    THE_CARDBOARD_BOX,
    THE_STOLEN_HAIR_TIE,
    THE_HEATED_BLANKET,
]
