"""Pipeline-the-Game v0.2 starter decks.

Two 30-card decks anchored to interceptor mechanics that already exist in
`src/cards/`. Each card has a simplified `effect_fn` that emits the canonical
payload event (DAMAGE / LIFE_CHANGE / DRAW / OBJECT_DESTROYED) directly. The
"real" card bodies expect a full battlefield; porting them is a v0.3 task.

Stage budget per deck (~30 cards):
- 6 TRANSFORM (re-shape the event before it resolves)
- 7 PREVENT (cancel or soften the event)
- 10 RESOLVE (the spell — mandatory column, biased so hands always have one)
- 7 REACT (fire after resolution)

TODOs on individual cards mark places where the v0.3 wiring should pull the
real `effect_fn` from the source card's interceptor helpers.
"""

from __future__ import annotations

from typing import Callable

from .pipeline_game import EffectFn, InterceptorDef
from .types import Event, EventType


# ───────────────────────── effect-fn builders ──────────────────────────


def _damage(amount: int) -> EffectFn:
    """Deal `amount` damage to your opponent."""

    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={"target": opponent, "amount": amount},
                source=controller,
                controller=controller,
            )
        ]

    return fn


def _life(amount: int) -> EffectFn:
    """Gain `amount` life (positive) or lose (negative)."""

    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": controller, "amount": amount},
                source=controller,
                controller=controller,
            )
        ]

    return fn


def _draw(count: int = 1) -> EffectFn:
    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={"player": controller, "count": count},
                source=controller,
                controller=controller,
            )
        ]

    return fn


def _destroy(name_hint: str = "token") -> EffectFn:
    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": name_hint, "owner": opponent},
                source=controller,
                controller=controller,
            )
        ]

    return fn


def _prevent() -> EffectFn:
    """PREVENT-stage handler that cancels the triggering event."""

    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        return []  # Empty list → manager interprets as full prevention.

    return fn


def _react_drain(amount: int) -> EffectFn:
    """REACT-stage: drain `amount` from opponent and give it to controller."""

    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": opponent, "amount": -amount},
                source=controller,
                controller=controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": controller, "amount": amount},
                source=controller,
                controller=controller,
            ),
        ]

    return fn


def _transform_amplify(multiplier: int) -> EffectFn:
    """TRANSFORM-stage: amplify the triggering event's amount by multiplier.

    For v0.2 we approximate by emitting an extra DAMAGE event with delta.
    A future engine pass should set `transformed_event` on the
    InterceptorResult and re-fire the pipeline.
    """

    def fn(triggering: Event, controller: str, opponent: str) -> list[Event]:
        amount = int(triggering.payload.get("amount", 1))
        delta = amount * (multiplier - 1)
        if delta == 0:
            return []
        return [
            Event(
                type=EventType.DAMAGE,
                payload={"target": opponent, "amount": delta},
                source=controller,
                controller=controller,
            )
        ]

    return fn


# ───────────────────────── deck definitions ────────────────────────────


def _c(**kw) -> InterceptorDef:
    return InterceptorDef(**kw)


STARTER_A_LIGHTNING: list[InterceptorDef] = [
    # TRANSFORM (×6) — re-shape the event
    _c(id="A-t-furnace",   engine="MTG", stage="TRANSFORM", cost=3, art="tri", name="Furnace of Rath",
       text="Double the event's damage payload.",                                 effect_fn=_transform_amplify(2)),
    _c(id="A-t-quicken",   engine="MTG", stage="TRANSFORM", cost=1, art="tri", name="Quicken",
       text="Add 1 damage to whatever resolves.",                                 effect_fn=_damage(1)),
    _c(id="A-t-prep",      engine="HS",  stage="TRANSFORM", cost=1, art="tri", name="Preparation",
       text="Subtract 1 from the event's mitigation.",                            effect_fn=_damage(1)),
    _c(id="A-t-mnestic",   engine="SCP", stage="TRANSFORM", cost=4, art="tri", name="Mnestic Recall",
       text="Rewrite the source — your spell hits twice.",                        effect_fn=_transform_amplify(2)),
    _c(id="A-t-magnet",    engine="PKM", stage="TRANSFORM", cost=2, art="tri", name="Energy Magnet",
       text="Re-route the damage to opponent.",                                   effect_fn=_damage(2)),
    _c(id="A-t-arbitrage", engine="FIN", stage="TRANSFORM", cost=2, art="tri", name="Arbitrage",
       text="Re-price the event by 1 tick of damage.",                            effect_fn=_damage(1)),

    # PREVENT (×7)
    _c(id="A-p-shielding", engine="MTG", stage="PREVENT", cost=1, art="bar", name="Shielding Plate",
       text="Prevent the next 2 damage.",                                         effect_fn=_prevent()),
    _c(id="A-p-counter",   engine="MTG", stage="PREVENT", cost=2, art="bar", name="Counterspell",
       text="Counter target spell.",                                              effect_fn=_prevent()),
    _c(id="A-p-block",     engine="HS",  stage="PREVENT", cost=3, art="bar", name="Ice Block",
       text="Prevent lethal once this turn.",                                     effect_fn=_prevent()),
    _c(id="A-p-jammer",    engine="YGO", stage="PREVENT", cost=2, art="bar", name="Magic Jammer",
       text="Discard 1, negate a spell.",                                         effect_fn=_prevent()),
    _c(id="A-p-protect",   engine="PKM", stage="PREVENT", cost=1, art="bar", name="Protection Cube",
       text="Block 30 damage to a Pokémon.",                                      effect_fn=_prevent()),
    _c(id="A-p-silent",    engine="DPT", stage="PREVENT", cost=2, art="bar", name="Silent Running",
       text="Hide from sonar this round.",                                        effect_fn=_prevent()),
    _c(id="A-p-veil",      engine="SCP", stage="PREVENT", cost=3, art="bar", name="Veil Protocol",
       text="Cancel an anomalous trigger.",                                       effect_fn=_prevent()),

    # RESOLVE (×10) — the spell. Mandatory column.
    _c(id="A-r-bolt",      engine="MTG", stage="RESOLVE", cost=1, art="square", name="Lightning Bolt",
       text="Deal 3 damage to any target.",                                       effect_fn=_damage(3)),
    _c(id="A-r-wrath",     engine="MTG", stage="RESOLVE", cost=4, art="square", name="Wrath of God",
       text="Destroy all creatures.",                                             effect_fn=_destroy("wrath-board")),
    _c(id="A-r-fireball",  engine="HS",  stage="RESOLVE", cost=4, art="square", name="Fireball",
       text="Deal 6 damage.",                                                     effect_fn=_damage(6)),
    _c(id="A-r-poisoned",  engine="PKM", stage="RESOLVE", cost=2, art="square", name="Status: Poisoned",
       text="Apply 10 damage on resolve.",                                        effect_fn=_damage(2)),
    _c(id="A-r-raigeki",   engine="YGO", stage="RESOLVE", cost=3, art="square", name="Raigeki",
       text="Destroy all opponent monsters.",                                     effect_fn=_destroy("raigeki-board")),
    _c(id="A-r-pulse",     engine="MNR", stage="RESOLVE", cost=1, art="square", name="Redstone Pulse",
       text="Trigger an adjacent interceptor.",                                   effect_fn=_damage(1)),
    _c(id="A-r-short",     engine="FIN", stage="RESOLVE", cost=3, art="square", name="Short Squeeze",
       text="+1 trick if you held the long.",                                     effect_fn=_damage(3)),
    _c(id="A-r-torpedo",   engine="DPT", stage="RESOLVE", cost=3, art="square", name="Torpedo Salvo",
       text="Deal 4 to the active sub.",                                          effect_fn=_damage(4)),
    _c(id="A-r-breach",    engine="SCP", stage="RESOLVE", cost=5, art="square", name="Containment Breach",
       text="Resolve anomaly damage twice.",                                      effect_fn=_damage(7)),
    _c(id="A-r-bolt2",     engine="MTG", stage="RESOLVE", cost=1, art="square", name="Shock",
       text="Deal 2 damage to any target.",                                       effect_fn=_damage(2)),

    # REACT (×7)
    _c(id="A-k-soul",      engine="MTG", stage="REACT", cost=1, art="circle", name="Soul Warden",
       text="When damage resolves, gain 1 life per source.",                      effect_fn=_life(1)),
    _c(id="A-k-acolyte",   engine="HS",  stage="REACT", cost=2, art="circle", name="Acolyte of Pain",
       text="When dealt damage, draw a card.",                                    effect_fn=_draw(1)),
    _c(id="A-k-redstone",  engine="MNR", stage="REACT", cost=1, art="grid",   name="Redstone Latch",
       text="Trigger an adjacent interceptor.",                                   effect_fn=_damage(1)),
    _c(id="A-k-grit",      engine="PKM", stage="REACT", cost=2, art="circle", name="Survivor",
       text="Survive a KO with 10 HP once.",                                      effect_fn=_life(2)),
    _c(id="A-k-mirror",    engine="YGO", stage="REACT", cost=3, art="circle", name="Mirror Force",
       text="Destroy all attacking monsters.",                                    effect_fn=_destroy("mirror-attackers")),
    _c(id="A-k-amnestic",  engine="SCP", stage="REACT", cost=2, art="circle", name="Amnestic Dose",
       text="Forget the event happened.",                                         effect_fn=_draw(1)),
    _c(id="A-k-sonar",     engine="DPT", stage="REACT", cost=1, art="grid",   name="Sonar Pulse",
       text="Reveal one opponent card.",                                          effect_fn=_draw(1)),
]


STARTER_B_CONTROL: list[InterceptorDef] = [
    # TRANSFORM (×6)
    _c(id="B-t-furnace",   engine="MTG", stage="TRANSFORM", cost=3, art="tri", name="Furnace of Rath",
       text="Double the event's damage payload.",                                 effect_fn=_transform_amplify(2)),
    _c(id="B-t-redirect",  engine="MTG", stage="TRANSFORM", cost=2, art="tri", name="Reflect Damage",
       text="Redirect the next damage event back at its source.",                 effect_fn=_damage(2)),
    _c(id="B-t-mnestic",   engine="SCP", stage="TRANSFORM", cost=4, art="tri", name="Mnestic Recall",
       text="Rewrite event source.",                                              effect_fn=_transform_amplify(2)),
    _c(id="B-t-scry",      engine="MTG", stage="TRANSFORM", cost=1, art="tri", name="Scry",
       text="See the next event before it resolves.",                             effect_fn=_draw(1)),
    _c(id="B-t-magnet",    engine="PKM", stage="TRANSFORM", cost=2, art="tri", name="Energy Magnet",
       text="Reroute energy to your active.",                                     effect_fn=_life(2)),
    _c(id="B-t-amplify",   engine="FIN", stage="TRANSFORM", cost=3, art="tri", name="Leverage 2x",
       text="Double the event's payoff.",                                         effect_fn=_transform_amplify(2)),

    # PREVENT (×7)
    _c(id="B-p-counter",   engine="MTG", stage="PREVENT", cost=2, art="bar", name="Counterspell",
       text="Counter target spell.",                                              effect_fn=_prevent()),
    _c(id="B-p-spike",     engine="MTG", stage="PREVENT", cost=1, art="bar", name="Force Spike",
       text="Counter unless opp pays 1.",                                         effect_fn=_prevent()),
    _c(id="B-p-veil",      engine="SCP", stage="PREVENT", cost=3, art="bar", name="Veil Protocol",
       text="Cancel an anomalous trigger.",                                       effect_fn=_prevent()),
    _c(id="B-p-block",     engine="HS",  stage="PREVENT", cost=3, art="bar", name="Ice Block",
       text="Prevent lethal once this turn.",                                     effect_fn=_prevent()),
    _c(id="B-p-jammer",    engine="YGO", stage="PREVENT", cost=2, art="bar", name="Magic Jammer",
       text="Discard 1, negate a spell.",                                         effect_fn=_prevent()),
    _c(id="B-p-warden",    engine="MTG", stage="PREVENT", cost=2, art="bar", name="Ward of Bones",
       text="Prevent the next 3 damage.",                                         effect_fn=_prevent()),
    _c(id="B-p-silent",    engine="DPT", stage="PREVENT", cost=2, art="bar", name="Silent Running",
       text="Hide from sonar.",                                                   effect_fn=_prevent()),

    # RESOLVE (×10) — control-flavored
    _c(id="B-r-bolt",      engine="MTG", stage="RESOLVE", cost=1, art="square", name="Lightning Bolt",
       text="Deal 3 damage.",                                                     effect_fn=_damage(3)),
    _c(id="B-r-drain",     engine="MTG", stage="RESOLVE", cost=2, art="square", name="Drain Life",
       text="Drain 2 life from opponent.",                                        effect_fn=_react_drain(2)),
    _c(id="B-r-ponder",    engine="MTG", stage="RESOLVE", cost=1, art="square", name="Ponder",
       text="Draw a card.",                                                       effect_fn=_draw(1)),
    _c(id="B-r-wrath",     engine="MTG", stage="RESOLVE", cost=4, art="square", name="Wrath of God",
       text="Destroy all creatures.",                                             effect_fn=_destroy("wrath-board")),
    _c(id="B-r-flamestrike", engine="HS", stage="RESOLVE", cost=4, art="square", name="Flamestrike",
       text="Deal 4 damage to all enemies.",                                      effect_fn=_damage(4)),
    _c(id="B-r-raigeki",   engine="YGO", stage="RESOLVE", cost=3, art="square", name="Raigeki",
       text="Destroy all opp monsters.",                                          effect_fn=_destroy("raigeki-board")),
    _c(id="B-r-poisoned",  engine="PKM", stage="RESOLVE", cost=2, art="square", name="Status: Poisoned",
       text="Apply poison damage.",                                               effect_fn=_damage(2)),
    _c(id="B-r-margin",    engine="FIN", stage="RESOLVE", cost=4, art="square", name="Margin Call",
       text="Force liquidation — 4 damage.",                                      effect_fn=_damage(4)),
    _c(id="B-r-torpedo",   engine="DPT", stage="RESOLVE", cost=3, art="square", name="Torpedo Salvo",
       text="Deal 4 to the active sub.",                                          effect_fn=_damage(4)),
    _c(id="B-r-breach",    engine="SCP", stage="RESOLVE", cost=5, art="square", name="Containment Breach",
       text="Resolve anomaly damage twice.",                                      effect_fn=_damage(7)),

    # REACT (×7)
    _c(id="B-k-soul",      engine="MTG", stage="REACT", cost=1, art="circle", name="Soul Warden",
       text="Gain 1 life per source.",                                            effect_fn=_life(1)),
    _c(id="B-k-cycle",     engine="MTG", stage="REACT", cost=2, art="circle", name="Cycling Trigger",
       text="Draw a card when something cycles.",                                 effect_fn=_draw(1)),
    _c(id="B-k-acolyte",   engine="HS",  stage="REACT", cost=2, art="circle", name="Acolyte of Pain",
       text="When dealt damage, draw a card.",                                    effect_fn=_draw(1)),
    _c(id="B-k-mirror",    engine="YGO", stage="REACT", cost=3, art="circle", name="Mirror Force",
       text="Destroy all attackers.",                                             effect_fn=_destroy("mirror-attackers")),
    _c(id="B-k-margin",    engine="FIN", stage="REACT", cost=4, art="grid",   name="Margin Call (REACT)",
       text="On resolve, opponent pays 2.",                                       effect_fn=_react_drain(2)),
    _c(id="B-k-amnestic",  engine="SCP", stage="REACT", cost=2, art="circle", name="Amnestic Dose",
       text="Forget it happened.",                                                effect_fn=_draw(1)),
    _c(id="B-k-redstone",  engine="MNR", stage="REACT", cost=1, art="grid",   name="Redstone Latch",
       text="Trigger an adjacent interceptor.",                                   effect_fn=_damage(1)),
]


DECK_REGISTRY: dict[str, Callable[[], list[InterceptorDef]]] = {
    "starter_a_lightning": lambda: list(STARTER_A_LIGHTNING),
    "starter_b_control":   lambda: list(STARTER_B_CONTROL),
}


def load_deck(deck_id: str) -> list[InterceptorDef]:
    """Return a fresh copy of the named deck."""
    factory = DECK_REGISTRY.get(deck_id)
    if factory is None:
        raise ValueError(f"unknown pipeline deck {deck_id!r}")
    return factory()


def default_event_deck() -> list[Event]:
    """A 14-event default deck mirroring the v0.1 frontend pool."""
    return [
        Event(type=EventType.DAMAGE,        payload={"amount": 3,  "target": "player_b"}, source="event-deck"),
        Event(type=EventType.LIFE_CHANGE,   payload={"amount": 2,  "player": "player_a"}, source="event-deck"),
        Event(type=EventType.ZONE_CHANGE,   payload={"from_zone": "battlefield", "to_zone": "graveyard"}, source="event-deck"),
        Event(type=EventType.DRAW,          payload={"count": 2,   "player": "player_a"}, source="event-deck"),
        Event(type=EventType.TURN_START,    payload={"turn": 5,    "active": "player_a"}, source="event-deck"),
        Event(type=EventType.OBJECT_CREATED, payload={"stats": "3/3", "controller": "player_b"}, source="event-deck"),
        Event(type=EventType.DAMAGE,        payload={"amount": 7,  "target": "player_a"}, source="event-deck"),
        Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": "wolf_02"}, source="event-deck"),
        Event(type=EventType.LIFE_CHANGE,   payload={"amount": -5, "player": "player_a"}, source="event-deck"),
        Event(type=EventType.DAMAGE,        payload={"amount": 4,  "target": "player_b"}, source="event-deck"),
        Event(type=EventType.DRAW,          payload={"count": 1,   "player": "player_b"}, source="event-deck"),
        Event(type=EventType.CAST,          payload={"spell": "fireball_01"},              source="event-deck"),
        Event(type=EventType.ATTACK_DECLARED, payload={"target": "player_a"},              source="event-deck"),
        Event(type=EventType.LIFE_CHANGE,   payload={"amount": -3, "player": "player_b"}, source="event-deck"),
    ]
