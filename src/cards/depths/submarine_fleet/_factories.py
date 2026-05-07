"""
Card-builder factories for the SUBS set.

All five archetype files (wolfpack.py, silent_hunter.py, carrier.py,
deep_strike.py, neutral.py) import these so the card-shape contract
stays consistent across parallel agents.

The depths engine reads `mana_cost` as a `{1T,2S}`-format charge string
(parsed by `src.engine.depths.parse_charge_cost`). We reuse that field
rather than inventing a new `depths_cost` attribute.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from src.engine.types import (
    CardDefinition,
    Characteristics,
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)
from src.engine.depths import DepthBand


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _attach(card: CardDefinition, **attrs) -> CardDefinition:
    """Bolt depths-specific attributes onto a CardDefinition. Skips Nones."""
    for key, value in attrs.items():
        if value is None:
            continue
        setattr(card, key, value)
    return card


def _abilities(keywords: Optional[Iterable[str]]) -> list[dict]:
    """Convert a list/set of keyword strings to the ability dict shape
    that `Characteristics.abilities` expects."""
    return [{"keyword": k} for k in (keywords or set())]


# ---------------------------------------------------------------------------
# Vessel
# ---------------------------------------------------------------------------

def make_vessel(
    name: str,
    *,
    power: int,
    hull: int,
    cost: Optional[str],                # e.g. "{2T,1S}" or None for tokens
    subtypes: Optional[Iterable[str]] = None,
    default_depth: DepthBand = DepthBand.SURFACE,
    keywords: Optional[Iterable[str]] = None,
    setup_interceptors=None,
    text: str = "",
    is_legendary: bool = False,
    is_flagship: bool = False,
    is_token: bool = False,
) -> CardDefinition:
    """A submarine / destroyer / drone / flagship Vessel.

    `keywords` accepts engine keywords (e.g. "haste") AND depths-specific
    keywords from the design doc: "silent_running", "homing", "reach",
    "bottom_crawler", "stealth", "defender". They're stored as ability
    dicts on Characteristics — interceptors and combat helpers read them
    via the standard `has_ability(obj, kw)` query.
    """
    subs: set[str] = set(subtypes or {"Submarine"})
    if is_legendary:
        subs.add("Legendary")
    if is_flagship:
        subs.add("Flagship")

    card = CardDefinition(
        name=name,
        mana_cost=cost,
        domain="SUBS",
        text=text,
        characteristics=Characteristics(
            types={CardType.DEPTHS_VESSEL},
            subtypes=subs,
            power=power,
            toughness=hull,
            abilities=_abilities(keywords),
        ),
        setup_interceptors=setup_interceptors,
    )
    return _attach(
        card,
        depths_default_depth=default_depth,
        depths_is_flagship=is_flagship,
        depths_is_token=is_token,
        depths_keywords=set(keywords) if keywords else None,
    )


# ---------------------------------------------------------------------------
# Crew (equipment-style attachment)
# ---------------------------------------------------------------------------

def make_crew(
    name: str,
    *,
    cost: str,
    power_mod: int = 0,
    toughness_mod: int = 0,
    keywords_to_grant: Optional[Iterable[str]] = None,
    subtypes_to_add: Optional[Iterable[str]] = None,
    setup_interceptors=None,
    text: str = "",
) -> CardDefinition:
    """A Crew card — attaches to a Vessel and grants stat boosts / keywords.

    Crew use the existing `make_equipment_setup` helper from
    `src.cards.interceptor_helpers` if `setup_interceptors` is None and
    any of (power_mod / toughness_mod / keywords_to_grant /
    subtypes_to_add) are non-default.
    """
    if setup_interceptors is None and (
        power_mod or toughness_mod or keywords_to_grant or subtypes_to_add
    ):
        from src.cards.interceptor_helpers import make_equipment_setup
        setup_interceptors = make_equipment_setup(
            power_mod=power_mod,
            toughness_mod=toughness_mod,
            keywords=set(keywords_to_grant) if keywords_to_grant else None,
            subtypes_to_add=set(subtypes_to_add) if subtypes_to_add else None,
        )

    card = CardDefinition(
        name=name,
        mana_cost=cost,
        domain="SUBS",
        text=text,
        characteristics=Characteristics(
            types={CardType.DEPTHS_CREW},
            subtypes={"Crew"},
        ),
        setup_interceptors=setup_interceptors,
    )
    return card


# ---------------------------------------------------------------------------
# Weapon (attached, often with activated abilities)
# ---------------------------------------------------------------------------

def make_weapon(
    name: str,
    *,
    cost: str,
    power_mod: int = 0,
    toughness_mod: int = 0,
    keywords_to_grant: Optional[Iterable[str]] = None,
    granted_activated_abilities: Optional[list[dict]] = None,
    charges: int = 0,
    setup_interceptors=None,
    text: str = "",
) -> CardDefinition:
    """A Weapon card — attaches to a Vessel.

    `granted_activated_abilities` is a list of dicts in the shape
    accepted by the existing `make_equipment_setup` helper. `charges`
    decrements per use; a Weapon at 0 charges sinks.
    """
    if setup_interceptors is None and (
        power_mod or toughness_mod or keywords_to_grant or granted_activated_abilities
    ):
        from src.cards.interceptor_helpers import make_equipment_setup
        setup_interceptors = make_equipment_setup(
            power_mod=power_mod,
            toughness_mod=toughness_mod,
            keywords=set(keywords_to_grant) if keywords_to_grant else None,
            granted_activated_abilities=granted_activated_abilities,
        )

    card = CardDefinition(
        name=name,
        mana_cost=cost,
        domain="SUBS",
        text=text,
        characteristics=Characteristics(
            types={CardType.DEPTHS_WEAPON},
            subtypes={"Weapon"},
        ),
        setup_interceptors=setup_interceptors,
    )
    return _attach(card, depths_weapon_charges=charges if charges else None)


# ---------------------------------------------------------------------------
# Mine (battlefield permanent at a depth band)
# ---------------------------------------------------------------------------

def make_mine(
    name: str,
    *,
    cost: str,
    damage: int,
    default_depth: DepthBand = DepthBand.PERISCOPE,
    detect_triggering_vessel: bool = False,
    text: str = "",
) -> CardDefinition:
    """A Mine — sits at `default_depth`, fires the system interceptor's
    DEPTHS_MINE_TRIGGER when an opposing Vessel enters that band.

    The system interceptor in `src.engine.depths` reads the
    `depths_mine_damage` attribute. `detect_triggering_vessel=True`
    causes the mine to detect the triggering vessel as a side-effect.
    """
    card = CardDefinition(
        name=name,
        mana_cost=cost,
        domain="SUBS",
        text=text,
        characteristics=Characteristics(
            types={CardType.DEPTHS_MINE},
            subtypes={"Mine"},
        ),
    )
    return _attach(
        card,
        depths_mine_damage=damage,
        depths_default_depth=default_depth,
        depths_mine_detects=detect_triggering_vessel or None,
    )


# ---------------------------------------------------------------------------
# Action (one-shot spell)
# ---------------------------------------------------------------------------

def make_action(
    name: str,
    *,
    cost: str,
    text: str,
    cast_effect_fn: Optional[Callable] = None,
) -> CardDefinition:
    """An Action — sorcery-speed one-shot effect.

    `cast_effect_fn(obj, state) -> list[Event]` runs when the spell
    resolves. Reuses the engine's INSTANT card type so the existing
    cast pipeline routes it correctly.
    """
    card = CardDefinition(
        name=name,
        mana_cost=cost,
        domain="SUBS",
        text=text,
        characteristics=Characteristics(
            types={CardType.INSTANT},   # reuses cast pipeline
            subtypes={"Action"},
        ),
    )
    if cast_effect_fn is not None:
        card.cast_effect_fn = cast_effect_fn
    return card


# ---------------------------------------------------------------------------
# Doctrine (persistent global enchantment)
# ---------------------------------------------------------------------------

def make_doctrine(
    name: str,
    *,
    cost: str,
    text: str,
    setup_interceptors=None,
) -> CardDefinition:
    """A Doctrine — persistent global enchantment.

    Reuses ENCHANTMENT card type so existing enchantment-cast and
    leaves-battlefield handling work. The `setup_interceptors` callable
    registers the persistent effect (lord boosts, end-step triggers,
    etc.) when the Doctrine ETBs.
    """
    card = CardDefinition(
        name=name,
        mana_cost=cost,
        domain="SUBS",
        text=text,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes={"Doctrine"},
        ),
        setup_interceptors=setup_interceptors,
    )
    return card


# ---------------------------------------------------------------------------
# Token-vessel helper (Drones from Carrier)
# ---------------------------------------------------------------------------

def make_drone_token(
    *,
    name: str = "Drone",
    power: int = 1,
    hull: int = 1,
    keywords: Optional[Iterable[str]] = None,
    default_depth: DepthBand = DepthBand.SURFACE,
) -> CardDefinition:
    """The CardDefinition used as a token template by Carrier cards
    (Escort Carrier, Drone Swarm, etc.). Cost None — tokens aren't
    cast from hand. `is_token=True` flags it for the engine."""
    return make_vessel(
        name=name,
        power=power,
        hull=hull,
        cost=None,
        subtypes={"Drone"},
        default_depth=default_depth,
        keywords=keywords,
        is_token=True,
    )


__all__ = [
    "make_vessel",
    "make_crew",
    "make_weapon",
    "make_mine",
    "make_action",
    "make_doctrine",
    "make_drone_token",
    "DepthBand",
]
