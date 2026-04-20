"""
Bundle helpers: (Interceptor, str) pairs.

Each bundle returns both (a) an Interceptor (or list of Interceptors, for
static abilities whose P/T boost splits across QUERY_POWER/QUERY_TOUGHNESS)
and (b) a rules-text template using ``{this}`` as the card-name placeholder.

Usage in a card:

    def my_card_setup(obj, state):
        itc, _txt = etb_gain_life(obj, 3)
        return [itc]

    # Or, when composing a text= field on a CardDefinition:
    _itc, txt = etb_gain_life(obj, 3)   # txt = "When {this} enters the battlefield, you gain 3 life."
    text = substitute_card_name(txt, "Totoro")

These wrap existing primitives in ``interceptor_helpers`` and ``text_render``
so card files get both behaviour and auto-generated rules text from one call.
"""

from typing import Tuple, List, Sequence

from src.engine import (
    Event, EventType,
    Interceptor,
    GameObject, GameState, Color, CardType,
)

from src.cards import interceptor_helpers as ih
from src.cards import text_render as tr


# =============================================================================
# ETB BUNDLES
# =============================================================================

def etb_gain_life(obj: GameObject, amount: int) -> Tuple[Interceptor, str]:
    """Bundle: on ETB, controller gains ``amount`` life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
            controller=obj.controller,
        )]

    itc = ih.make_etb_trigger(obj, effect_fn)
    return itc, tr.render_etb_gain_life(amount)


def etb_lose_life(obj: GameObject, amount: int) -> Tuple[Interceptor, str]:
    """Bundle: on ETB, each opponent loses ``amount`` life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -amount},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    itc = ih.make_etb_trigger(obj, effect_fn)
    return itc, tr.render_etb_lose_life(amount)


def etb_draw(obj: GameObject, amount: int) -> Tuple[Interceptor, str]:
    """Bundle: on ETB, controller draws ``amount`` cards."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(amount)
        ]

    itc = ih.make_etb_trigger(obj, effect_fn)
    return itc, tr.render_etb_draw(amount)


def etb_create_token(
    obj: GameObject,
    power: int,
    toughness: int,
    subtype: str,
    count: int = 1,
    colors: set | None = None,
    keywords: list[str] | None = None,
) -> Tuple[Interceptor, str]:
    """Bundle: on ETB, create ``count`` P/T ``subtype`` creature tokens."""
    token_colors = set(colors) if colors else set()
    token_keywords = list(keywords) if keywords else []

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'token': True,
                    'name': subtype,
                    'power': power,
                    'toughness': toughness,
                    'colors': token_colors,
                    'subtypes': {subtype},
                    'keywords': token_keywords,
                    'controller': obj.controller,
                },
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(count)
        ]

    itc = ih.make_etb_trigger(obj, effect_fn)
    return itc, tr.render_etb_create_token(power, toughness, subtype, count)


def etb_deal_damage(
    obj: GameObject,
    amount: int,
    target: str = "each_opponent",
) -> Tuple[Interceptor, str]:
    """Bundle: on ETB, deal damage.

    Supported ``target`` values (matching abilities DSL EffectTargets):
        - ``'each_opponent'`` → one DAMAGE event per opponent player id
        - ``'this'`` → damage to {this} itself
        - ``'target_creature'`` → a damage event with ``target`` unset (caller
          wires targeting elsewhere). Kept for parity with DealDamage(...).
    """
    desc_map = {
        "each_opponent": "each opponent",
        "this": "{this}",
        "target_creature": "target creature",
    }
    if target not in desc_map:
        raise ValueError(f"Unsupported target for etb_deal_damage: {target!r}")

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        if target == "each_opponent":
            return [
                Event(
                    type=EventType.DAMAGE,
                    payload={'target': opp_id, 'amount': amount, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                )
                for opp_id in ih.all_opponents(obj, state)
            ]
        if target == "this":
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': obj.id, 'amount': amount, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            )]
        # target_creature: no target known at registration time; emit an empty
        # placeholder damage event. Real migrations should route through a
        # dedicated targeted-ETB helper.
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': None, 'amount': amount, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    itc = ih.make_etb_trigger(obj, effect_fn)
    return itc, tr.render_etb_deal_damage(amount, desc_map[target])


# =============================================================================
# DEATH BUNDLES
# =============================================================================

def death_drain(obj: GameObject, amount: int) -> Tuple[Interceptor, str]:
    """Bundle: on death, each opponent loses N life and you gain N life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -amount},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    itc = ih.make_death_trigger(obj, effect_fn)
    return itc, tr.render_death_drain(amount)


def death_draw(obj: GameObject, amount: int) -> Tuple[Interceptor, str]:
    """Bundle: on death, draw ``amount`` cards."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(amount)
        ]

    itc = ih.make_death_trigger(obj, effect_fn)
    return itc, tr.render_death_draw(amount)


# =============================================================================
# ATTACK BUNDLES
# =============================================================================

def attack_deal_damage(
    obj: GameObject,
    amount: int,
    target: str = "each_opponent",
) -> Tuple[Interceptor, str]:
    """Bundle: on attack declaration, deal damage."""
    desc_map = {
        "each_opponent": "each opponent",
        "this": "{this}",
        "target_creature": "target creature",
    }
    if target not in desc_map:
        raise ValueError(f"Unsupported target for attack_deal_damage: {target!r}")

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        if target == "each_opponent":
            return [
                Event(
                    type=EventType.DAMAGE,
                    payload={'target': opp_id, 'amount': amount, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                )
                for opp_id in ih.all_opponents(obj, state)
            ]
        if target == "this":
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': obj.id, 'amount': amount, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            )]
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': None, 'amount': amount, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    itc = ih.make_attack_trigger(obj, effect_fn)
    return itc, tr.render_attack_deal_damage(amount, desc_map[target])


def attack_add_counters(
    obj: GameObject,
    counter_type: str,
    count: int,
) -> Tuple[Interceptor, str]:
    """Bundle: on attack, put ``count`` ``counter_type`` counters on {this}."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': counter_type},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(count)
        ]

    itc = ih.make_attack_trigger(obj, effect_fn)
    return itc, tr.render_attack_add_counters(counter_type, count)


# =============================================================================
# STATIC PT-BOOST BUNDLES
# =============================================================================

def static_pt_boost_all_you_control(
    obj: GameObject,
    power: int,
    toughness: int,
) -> Tuple[List[Interceptor], str]:
    """'Creatures you control get +P/+T.' (includes {this}.)"""
    interceptors = ih.make_static_pt_boost(
        obj, power, toughness, ih.creatures_you_control(obj)
    )
    return interceptors, tr.render_static_pt_boost(
        power, toughness, scope="creatures you control"
    )


def static_pt_boost_other_you_control(
    obj: GameObject,
    power: int,
    toughness: int,
) -> Tuple[List[Interceptor], str]:
    """'Other creatures you control get +P/+T.' (excludes {this}.)"""
    interceptors = ih.make_static_pt_boost(
        obj, power, toughness, ih.other_creatures_you_control(obj)
    )
    return interceptors, tr.render_static_pt_boost(
        power, toughness, scope="other creatures you control"
    )


def static_pt_boost_by_subtype(
    obj: GameObject,
    power: int,
    toughness: int,
    subtype: str,
    include_self: bool = False,
) -> Tuple[List[Interceptor], str]:
    """'<Subtype> creatures you control get +P/+T.'

    By default (``include_self=False``) matches abilities-DSL
    ``CreaturesWithSubtypeFilter(include_self=False)`` → "Other <Subtype>
    creatures you control". Set ``include_self=True`` for the plain variant.
    """
    if include_self:
        filter_fn = ih.creatures_with_subtype(obj, subtype)
        scope = f"{subtype} creatures you control"
    else:
        filter_fn = ih.other_creatures_with_subtype(obj, subtype)
        scope = f"other {subtype} creatures you control"
    interceptors = ih.make_static_pt_boost(obj, power, toughness, filter_fn)
    return interceptors, tr.render_static_pt_boost(
        power, toughness, scope=scope
    )


# =============================================================================
# STATIC KEYWORD-GRANT BUNDLES
# =============================================================================

def static_keyword_grant_others(
    obj: GameObject,
    keywords: Sequence[str],
    scope: str = "other_creatures_you_control",
) -> Tuple[List[Interceptor], str]:
    """'Other creatures you control have <keywords>.' etc.

    Supported ``scope`` values:
        - ``'other_creatures_you_control'`` (default)
        - ``'creatures_you_control'``
        - ``'all_creatures'``
    """
    kws = list(keywords)
    if scope == "other_creatures_you_control":
        filter_fn = ih.other_creatures_you_control(obj)
        scope_text = "other creatures you control"
    elif scope == "creatures_you_control":
        filter_fn = ih.creatures_you_control(obj)
        scope_text = "creatures you control"
    elif scope == "all_creatures":
        filter_fn = ih.all_creatures_filter()
        scope_text = "all creatures"
    else:
        raise ValueError(f"Unsupported scope: {scope!r}")

    itc = ih.make_keyword_grant(obj, kws, filter_fn)
    return [itc], tr.render_static_keyword_grant(kws, scope_text)


# =============================================================================
# UPKEEP / SPELL-CAST BUNDLES
# =============================================================================

def upkeep_gain_life(obj: GameObject, amount: int) -> Tuple[Interceptor, str]:
    """Bundle: at the beginning of your upkeep, gain ``amount`` life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
            controller=obj.controller,
        )]

    itc = ih.make_upkeep_trigger(obj, effect_fn)
    return itc, tr.render_upkeep_gain_life(amount)


def spell_cast_draw(obj: GameObject, amount: int = 1) -> Tuple[Interceptor, str]:
    """Bundle: whenever you cast a spell, draw ``amount`` card(s)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(amount)
        ]

    itc = ih.make_spell_cast_trigger(obj, effect_fn)
    return itc, tr.render_spell_cast_draw(amount)
