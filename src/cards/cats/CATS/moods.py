"""CATS — Mood cards (10 cards).

Moods are Value 0; they distort the trick comparison rule. When played as
Pounce, a Mood replaces the Category Rule for the round. When played as
Counter-pounce, the Mood installs its rule BEFORE the comparison runs.

Capabilities exercised: Mood interceptors (capability #5 — replace trick
rule via CATS_TRICK_RULE_QUERY), on-enter-pile demands-attention triggers.
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
from src.engine.cats import make_mood_card

from .sleek_cats import _on_enter_pile_trigger


# ---------------------------------------------------------------------------
# Mood rule callables — each takes (card_a, card_b, state, ...) and returns
# the winning player_id. They mirror sleek_rule's signature but with twist.
# ---------------------------------------------------------------------------

def _value_of(state: GameState, obj_id: str) -> int:
    """Local Value reader (Moods=0, otherwise card_def.cats_value or power)."""
    obj = state.objects.get(obj_id) if state.objects else None
    if obj is None:
        return 0
    card_def = obj.card_def
    if card_def is not None:
        # Mood?
        try:
            from src.engine.types import CardType
            if CardType.CATS_MOOD in obj.characteristics.types:
                return 0
        except Exception:
            pass
        v = getattr(card_def, "cats_value", None)
        if v is not None:
            return int(v)
    pwr = obj.characteristics.power
    return int(pwr) if pwr is not None else 0


def _trick_players(state: GameState):
    trick = getattr(state, "cats_current_trick", {}) or {}
    return trick.get("pounce_player"), trick.get("counter_player")


def lowest_wins(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """3 a.m. Zoomies: lowest value wins this trick."""
    va = _value_of(state, card_a_id)
    vb = _value_of(state, card_b_id)
    pp, cp = _trick_players(state)
    if va < vb:
        return pp or ""
    if vb < va:
        return cp or ""
    return cp or pp or ""


def loudest_wins(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Bored: highest absolute value, ties to counter (lead)."""
    va = _value_of(state, card_a_id)
    vb = _value_of(state, card_b_id)
    pp, cp = _trick_players(state)
    if va > vb:
        return pp or ""
    if vb > va:
        return cp or ""
    return cp or pp or ""


def equal_wins_pounce(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Inscrutable: only ties win. Otherwise no one wins (engine fallback)."""
    va = _value_of(state, card_a_id)
    vb = _value_of(state, card_b_id)
    pp, cp = _trick_players(state)
    if va == vb:
        return pp or ""
    # Use default sleek to break the no-win edge
    if va > vb:
        return pp or ""
    return cp or ""


def fewer_hand_wins(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Whoever has the smaller hand wins (incentivizes spending cards)."""
    pp, cp = _trick_players(state)
    pp_hand = len(state.zones.get(f"HAND_{pp}", type("Z", (), {"objects": []})()).objects) if pp else 0
    cp_hand = len(state.zones.get(f"HAND_{cp}", type("Z", (), {"objects": []})()).objects) if cp else 0
    if pp_hand < cp_hand:
        return pp or ""
    if cp_hand < pp_hand:
        return cp or ""
    # Fall back to sleek
    return lowest_wins(card_a_id, card_b_id, state)  # arbitrary tiebreak


def more_pile_cards_wins(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Smug: whoever has more total pile cards wins."""
    from src.engine.cats import _pile_total  # type: ignore[attr-defined]
    pp, cp = _trick_players(state)
    pp_total = _pile_total(state, pp) if pp else 0
    cp_total = _pile_total(state, cp) if cp else 0
    if pp_total > cp_total:
        return pp or ""
    if cp_total > pp_total:
        return cp or ""
    return loudest_wins(card_a_id, card_b_id, state)


def fewer_pile_cards_wins(card_a_id: str, card_b_id: str, state: GameState) -> str:
    """Underdog: whoever has fewer total pile cards wins."""
    from src.engine.cats import _pile_total  # type: ignore[attr-defined]
    pp, cp = _trick_players(state)
    pp_total = _pile_total(state, pp) if pp else 0
    cp_total = _pile_total(state, cp) if cp else 0
    if pp_total < cp_total:
        return pp or ""
    if cp_total < pp_total:
        return cp or ""
    return lowest_wins(card_a_id, card_b_id, state)


# ---------------------------------------------------------------------------
# Mood setup function builder: registers a CATS_TRICK_RULE_QUERY interceptor
# that replaces the rule with this mood's rule_fn when the mood is in the
# current trick.
# ---------------------------------------------------------------------------

def _mood_setup_factory(rule_fn):
    def setup(obj: GameObject, state: GameState):
        def filter_fn(ev: Event, st: GameState) -> bool:
            if ev.type != EventType.CATS_TRICK_RULE_QUERY:
                return False
            trick = getattr(st, "cats_current_trick", {}) or {}
            return trick.get("pounce_card") == obj.id or trick.get("counter_card") == obj.id

        def handler(ev: Event, st: GameState) -> InterceptorResult:
            new_ev = ev.copy()
            new_ev.payload["current_rule"] = rule_fn
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_ev)

        # Also emit a marker to attention when the mood is claimed.
        def attn_filter(ev: Event, st: GameState) -> bool:
            if ev.type != EventType.CATS_CLAIM_PILE:
                return False
            return ev.payload.get("card_id") == obj.id

        def attn_handler(ev: Event, st: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[
                    Event(
                        type=EventType.CATS_PILE_ACTIVATE,
                        payload={
                            "player": ev.payload.get("player"),
                            "card_id": obj.id,
                            "pile": "pile_attention",
                            "reason": "mood_demands_attention",
                        },
                        source=obj.id,
                    )
                ],
            )

        return [
            Interceptor(
                id=new_id(),
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.TRANSFORM,
                filter=filter_fn,
                handler=handler,
                duration="forever",
            ),
            Interceptor(
                id=new_id(),
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.REACT,
                filter=attn_filter,
                handler=attn_handler,
                duration="forever",
            ),
        ]

    return setup


# ---------------------------------------------------------------------------
# The 10 Moods
# ---------------------------------------------------------------------------

THE_3AM_ZOOMIES = make_mood_card(
    name="The 3 a.m. Zoomies",
    text="Tonight, everyone is unhinged. Lowest Value wins this trick. Also demands attention.",
    rarity="rare",
    setup_interceptors=_mood_setup_factory(lowest_wins),
    rule_fn=lowest_wins,
)


SITTING_IN_THE_BOX = make_mood_card(
    name="Sitting In The Box",
    text="The box is small. The cat is also small, now. Whoever has fewer cards in hand wins this trick.",
    rarity="uncommon",
    setup_interceptors=_mood_setup_factory(fewer_hand_wins),
    rule_fn=fewer_hand_wins,
)


AGGRESSIVE_LOAFING = make_mood_card(
    name="Aggressive Loafing",
    text="The loaf is HOSTILE. Whoever has more pile cards wins this trick (smug supremacy).",
    rarity="rare",
    setup_interceptors=_mood_setup_factory(more_pile_cards_wins),
    rule_fn=more_pile_cards_wins,
)


KNOCKING_THINGS_OFF_TABLES = make_mood_card(
    name="Knocking Things Off Tables",
    text="Items will fall. Lowest Value wins (the small ones are doing the most damage).",
    rarity="common",
    setup_interceptors=_mood_setup_factory(lowest_wins),
    rule_fn=lowest_wins,
)


THE_QUIET_INTERROGATION = make_mood_card(
    name="The Quiet Interrogation",
    text="The stare. Highest Value wins this trick (presence matters in court).",
    rarity="common",
    setup_interceptors=_mood_setup_factory(loudest_wins),
    rule_fn=loudest_wins,
)


WET_FOOD_O_CLOCK = make_mood_card(
    name="Wet Food O'Clock",
    text="Everything stops. The lowest Value wins (the loudest yowling is from the cat already on the counter).",
    rarity="uncommon",
    setup_interceptors=_mood_setup_factory(lowest_wins),
    rule_fn=lowest_wins,
)


THE_DIGNIFIED_SULK = make_mood_card(
    name="The Dignified Sulk",
    text="No one is happy. Fewer-pile-cards wins (the wronged shall be vindicated).",
    rarity="rare",
    setup_interceptors=_mood_setup_factory(fewer_pile_cards_wins),
    rule_fn=fewer_pile_cards_wins,
)


SUDDEN_SUSPICION = make_mood_card(
    name="Sudden Suspicion",
    text="Something is wrong. (Nothing is wrong.) Highest Value wins.",
    rarity="common",
    setup_interceptors=_mood_setup_factory(loudest_wins),
    rule_fn=loudest_wins,
)


THE_DRAMATIC_RECOVERY = make_mood_card(
    name="The Dramatic Recovery",
    text="A miraculous bounce-back. Lowest Value wins (small cat, big drama).",
    rarity="uncommon",
    setup_interceptors=_mood_setup_factory(lowest_wins),
    rule_fn=lowest_wins,
)


THE_INSCRUTABLE_STARE = make_mood_card(
    name="The Inscrutable Stare",
    text="What does it want. Equal Values win (ties become wins).",
    rarity="mythic",
    setup_interceptors=_mood_setup_factory(equal_wins_pounce),
    rule_fn=equal_wins_pounce,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

MOODS = [
    THE_3AM_ZOOMIES,
    SITTING_IN_THE_BOX,
    AGGRESSIVE_LOAFING,
    KNOCKING_THINGS_OFF_TABLES,
    THE_QUIET_INTERROGATION,
    WET_FOOD_O_CLOCK,
    THE_DIGNIFIED_SULK,
    SUDDEN_SUSPICION,
    THE_DRAMATIC_RECOVERY,
    THE_INSCRUTABLE_STARE,
]
