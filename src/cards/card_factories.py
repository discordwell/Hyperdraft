"""
Canonical MTG-style card factories.

Previously these factories were copy-pasted into 30+ card files with slight
signature drift. This module is the single source of truth.

Parameters are keyword-only by convention (pass by name in all call sites).
The signatures are the superset gathered from every local variant so that any
prior caller still works.

These are MTG-mode factories. Hearthstone (make_minion / make_spell),
Pokemon, and Yu-Gi-Oh! have their own mode-specific factories and are not
consolidated here.
"""

from src.engine import (
    CardDefinition, Characteristics, CardType,
)


def make_instant(
    name: str,
    mana_cost: str,
    colors: set,
    text: str,
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    resolve=None,
    setup_interceptors=None,
):
    """Create an Instant card definition.

    `setup_interceptors` is accepted so spells with alt-cast mechanics
    (mayhem, web-slinging, flashback, etc.) can register the necessary
    interceptors when the card object is created in graveyard/exile/etc.
    """
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost,
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        resolve=resolve,
        setup_interceptors=setup_interceptors,
    )


def make_sorcery(
    name: str,
    mana_cost: str,
    colors: set,
    text: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    resolve=None,
    setup_interceptors=None,
):
    """Create a Sorcery card definition.

    `setup_interceptors` lets spells with alt-cast mechanics (mayhem,
    web-slinging, flashback, plot, etc.) wire up their card-side hooks.
    """
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost,
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        resolve=resolve,
        setup_interceptors=setup_interceptors,
    )


def make_artifact(
    name: str,
    mana_cost: str,
    text: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    setup_interceptors=None,
):
    """Create an Artifact card definition."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=mana_cost,
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )


def make_artifact_creature(
    name: str,
    power: int,
    toughness: int,
    mana_cost: str,
    colors: set = None,
    text: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    setup_interceptors=None,
):
    """Create an Artifact Creature card definition."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            power=power,
            toughness=toughness,
            mana_cost=mana_cost,
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )


def make_enchantment_creature(
    name: str,
    power: int,
    toughness: int,
    mana_cost: str,
    colors: set,
    text: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    setup_interceptors=None,
):
    """Create an Enchantment Creature card definition."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            power=power,
            toughness=toughness,
            mana_cost=mana_cost,
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )


def make_equipment(
    name: str,
    mana_cost: str,
    text: str = "",
    equip_cost: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    setup_interceptors=None,
):
    """Create an Equipment (Artifact - Equipment) card definition.

    The equip_cost (if provided) is appended to the card text as "Equip {X}".
    """
    base_subtypes = {"Equipment"}
    if subtypes:
        base_subtypes.update(subtypes)
    final_text = text
    if equip_cost:
        final_text = f"{text}\nEquip {equip_cost}" if text else f"Equip {equip_cost}"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=base_subtypes,
            supertypes=supertypes or set(),
            mana_cost=mana_cost,
        ),
        text=final_text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )


def make_land(
    name: str,
    text: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    setup_interceptors=None,
):
    """Create a Land card definition."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost="",
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )


def make_planeswalker(
    name: str,
    mana_cost: str,
    colors: set,
    loyalty: int,
    text: str = "",
    rarity: str = None,
    subtypes: set = None,
    supertypes: set = None,
    abilities: list = None,
    setup_interceptors=None,
):
    """Create a Planeswalker card definition.

    Loyalty is prepended to the text (Characteristics has no loyalty field).
    """
    loyalty_text = f"[Loyalty: {loyalty}] " + text if text else f"[Loyalty: {loyalty}]"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost,
        ),
        text=loyalty_text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )


__all__ = [
    "make_instant",
    "make_sorcery",
    "make_artifact",
    "make_artifact_creature",
    "make_enchantment_creature",
    "make_equipment",
    "make_land",
    "make_planeswalker",
]
