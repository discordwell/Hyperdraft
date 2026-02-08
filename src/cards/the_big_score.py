"""
The Big Score (BIG) Card Implementations

Real card data fetched from Scryfall API.
30 cards in set.
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import make_etb_trigger
import re


# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

def _get_mana_value(mana_cost: str) -> int:
    """Calculate mana value from cost string like {2}{U}{U}."""
    if not mana_cost:
        return 0
    mv = 0
    for match in re.findall(r'\{(\d+|[WUBRGCX])\}', mana_cost):
        if match.isdigit():
            mv += int(match)
        elif match != 'X':
            mv += 1
    return mv


def simulacrum_synthesizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    When this artifact enters, scry 2.
    Whenever another artifact you control with mana value 3 or greater enters,
    create a 0/0 colorless Construct artifact creature token with
    "This token gets +1/+1 for each artifact you control."
    """
    interceptors = []

    # ETB: Scry 2
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'count': 2},
            source=obj.id,
            controller=obj.controller
        )]

    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Triggered ability: artifact with MV 3+ enters
    def artifact_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != obj.controller:
            return False
        if CardType.ARTIFACT not in entering.characteristics.types:
            return False
        # Check mana value >= 3
        mv = _get_mana_value(entering.characteristics.mana_cost or "")
        return mv >= 3

    def artifact_enters_handler(event: Event, state: GameState) -> InterceptorResult:
        # Create a 0/0 Construct with scaling P/T
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Construct',
                        'power': 0,
                        'toughness': 0,
                        'types': {CardType.ARTIFACT, CardType.CREATURE},
                        'subtypes': {'Construct'},
                        'colors': set(),
                        'text': 'This creature gets +1/+1 for each artifact you control.',
                        'scaling_pt': 'artifact_count'  # Engine flag for P/T scaling
                    }
                },
                source=obj.id,
                controller=obj.controller
            )]
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_enters_filter,
        handler=artifact_enters_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


def torpor_orb_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures entering don't cause abilities to trigger."""

    def filter_fn(event: Event, state: GameState) -> bool:
        # Prevent ETB triggers from creatures
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return CardType.CREATURE in entering.characteristics.types

    def handler_fn(event: Event, state: GameState) -> InterceptorResult:
        # Mark the event so ETB triggers are suppressed
        new_event = event.copy()
        new_event.payload['suppress_etb_triggers'] = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler_fn,
        duration='while_on_battlefield'
    )]


def grand_abolisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """During your turn, your opponents can't cast spells or activate abilities."""

    def filter_fn(event: Event, state: GameState) -> bool:
        # Only during our turn
        if state.active_player != obj.controller:
            return False
        # Block opponent spells and activations
        if event.type not in (EventType.CAST, EventType.SPELL_CAST, EventType.ACTIVATE):
            return False
        # Only block opponents
        return event.controller != obj.controller

    def handler_fn(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=filter_fn,
        handler=handler_fn,
        duration='while_on_battlefield'
    )]


def rest_in_peace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If a card or token would be put into a graveyard, exile it instead."""

    # ETB: Exile all graveyards
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            gy_key = f"graveyard_{player_id}"
            gy = state.zones.get(gy_key)
            if gy:
                for card_id in list(gy.objects):
                    events.append(Event(
                        type=EventType.EXILE,
                        payload={'object_id': card_id},
                        source=obj.id,
                        controller=obj.controller
                    ))
        return events

    # make_etb_trigger returns a single Interceptor, not an iterable.
    interceptors = [make_etb_trigger(obj, etb_effect)]

    # Replacement effect: graveyard -> exile
    def replace_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        to_zone = event.payload.get('to_zone_type')
        return to_zone == ZoneType.GRAVEYARD

    def replace_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['to_zone_type'] = ZoneType.EXILE
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=replace_filter,
        handler=replace_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_instant(name: str, mana_cost: str, colors: set, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create instant card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        resolve=resolve
    )


def make_sorcery(name: str, mana_cost: str, colors: set, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_enchantment_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                              subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create enchantment creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", rarity: str = None, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create land card definitions."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, loyalty: int,
                      subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    base_supertypes = supertypes or set()
    loyalty_text = f"[Loyalty: {loyalty}] " + text if text else f"[Loyalty: {loyalty}]"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes or set(),
            supertypes=base_supertypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=loyalty_text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

COLLECTORS_CAGE = make_artifact(
    name="Collector's Cage",
    mana_cost="{1}{W}",
    text="Hideaway 5 (When this artifact enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\n{1}, {T}: Put a +1/+1 counter on target creature you control. Then if you control three or more creatures with different powers, you may play the exiled card without paying its mana cost.",
    rarity="mythic",
)

GRAND_ABOLISHER = make_creature(
    name="Grand Abolisher",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    text="During your turn, your opponents can't cast spells or activate abilities of artifacts, creatures, or enchantments.",
    rarity="mythic",
    setup_interceptors=grand_abolisher_setup,
)

OLTEC_MATTERWEAVER = make_creature(
    name="Oltec Matterweaver",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="Whenever you cast a creature spell, choose one —\n• Create a 1/1 colorless Gnome artifact creature token.\n• Create a token that's a copy of target artifact token you control.",
    rarity="mythic",
)

REST_IN_PEACE = make_enchantment(
    name="Rest in Peace",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile all graveyards.\nIf a card or token would be put into a graveyard from anywhere, exile it instead.",
    rarity="mythic",
    setup_interceptors=rest_in_peace_setup,
)

ESOTERIC_DUPLICATOR = make_artifact(
    name="Esoteric Duplicator",
    mana_cost="{2}{U}",
    text="Whenever you sacrifice this artifact or another artifact, you may pay {2}. If you do, at the beginning of the next end step, create a token that's a copy of that artifact.\n{2}, Sacrifice this artifact: Draw a card.",
    rarity="mythic",
    subtypes={"Clue"},
)

SIMULACRUM_SYNTHESIZER = make_artifact(
    name="Simulacrum Synthesizer",
    mana_cost="{2}{U}",
    text="When this artifact enters, scry 2.\nWhenever another artifact you control with mana value 3 or greater enters, create a 0/0 colorless Construct artifact creature token with \"This token gets +1/+1 for each artifact you control.\"",
    rarity="mythic",
    setup_interceptors=simulacrum_synthesizer_setup,
)

WORLDWALKER_HELM = make_artifact(
    name="Worldwalker Helm",
    mana_cost="{2}{U}",
    text="If you would create one or more artifact tokens, instead create those tokens plus an additional Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")\n{1}{U}, {T}: Create a token that's a copy of target artifact token you control.",
    rarity="mythic",
)

GREEDS_GAMBIT = make_enchantment(
    name="Greed's Gambit",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, you draw three cards, gain 6 life, and create three 2/1 black Bat creature tokens with flying.\nAt the beginning of your end step, you discard a card, lose 2 life, and sacrifice a creature.\nWhen this enchantment leaves the battlefield, you discard three cards, lose 6 life, and sacrifice three creatures.",
    rarity="mythic",
)

HARVESTER_OF_MISERY = make_creature(
    name="Harvester of Misery",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Menace\nWhen this creature enters, other creatures get -2/-2 until end of turn.\n{1}{B}, Discard this card: Target creature gets -2/-2 until end of turn.",
    rarity="mythic",
)

HOSTILE_INVESTIGATOR = make_creature(
    name="Hostile Investigator",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Ogre", "Rogue"},
    text="When this creature enters, target opponent discards a card.\nWhenever one or more players discard one or more cards, investigate. This ability triggers only once each turn. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    rarity="mythic",
)

GENEROUS_PLUNDERER = make_creature(
    name="Generous Plunderer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Menace\nAt the beginning of your upkeep, you may create a Treasure token. When you do, target opponent creates a tapped Treasure token.\nWhenever this creature attacks, it deals damage to defending player equal to the number of artifacts they control.",
    rarity="mythic",
)

LEGION_EXTRUDER = make_artifact(
    name="Legion Extruder",
    mana_cost="{1}{R}",
    text="When this artifact enters, it deals 2 damage to any target.\n{2}, {T}, Sacrifice another artifact: Create a 3/3 colorless Golem artifact creature token.",
    rarity="mythic",
)

MEMORY_VESSEL = make_artifact(
    name="Memory Vessel",
    mana_cost="{3}{R}{R}",
    text="{T}, Exile this artifact: Each player exiles the top seven cards of their library. Until your next turn, players may play cards they exiled this way, and they can't play cards from their hand. Activate only as a sorcery.",
    rarity="mythic",
)

MOLTEN_DUPLICATION = make_sorcery(
    name="Molten Duplication",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Create a token that's a copy of target artifact or creature you control, except it's an artifact in addition to its other types. It gains haste until end of turn. Sacrifice it at the beginning of the next end step.",
    rarity="mythic",
)

TERRITORY_FORGE = make_artifact(
    name="Territory Forge",
    mana_cost="{4}{R}",
    text="When this artifact enters, if you cast it, exile target artifact or land.\nThis artifact has all activated abilities of the exiled card.",
    rarity="mythic",
)

ANCIENT_CORNUCOPIA = make_artifact(
    name="Ancient Cornucopia",
    mana_cost="{2}{G}",
    text="Whenever you cast a spell that's one or more colors, you may gain 1 life for each of that spell's colors. Do this only once each turn.\n{T}: Add one mana of any color.",
    rarity="mythic",
)

BRISTLEBUD_FARMER = make_creature(
    name="Bristlebud Farmer",
    power=5, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Plant"},
    text="Trample\nWhen this creature enters, create two Food tokens. (They're artifacts with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever this creature attacks, you may sacrifice a Food. If you do, mill three cards. You may put a permanent card from among them into your hand.",
    rarity="mythic",
)

OMENPATH_JOURNEY = make_enchantment(
    name="Omenpath Journey",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, search your library for up to five land cards that have different names, exile them, then shuffle.\nAt the beginning of your end step, choose a card at random exiled with this enchantment and put it onto the battlefield tapped.",
    rarity="mythic",
)

SANDSTORM_SALVAGER = make_creature(
    name="Sandstorm Salvager",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Artificer", "Human"},
    text="When this creature enters, create a 3/3 colorless Golem artifact creature token.\n{2}, {T}: Put a +1/+1 counter on each creature token you control. They gain trample until end of turn.",
    rarity="mythic",
)

VAULTBORN_TYRANT = make_creature(
    name="Vaultborn Tyrant",
    power=6, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample\nWhenever this creature or another creature you control with power 4 or greater enters, you gain 3 life and draw a card.\nWhen this creature dies, if it's not a token, create a token that's a copy of it, except it's an artifact in addition to its other types.",
    rarity="mythic",
)

LOOT_THE_KEY_TO_EVERYTHING = make_creature(
    name="Loot, the Key to Everything",
    power=1, toughness=2,
    mana_cost="{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Beast", "Noble"},
    supertypes={"Legendary"},
    text="Ward {1}\nAt the beginning of your upkeep, exile the top X cards of your library, where X is the number of card types among other nonland permanents you control. You may play those cards this turn.",
    rarity="mythic",
)

PEST_CONTROL = make_sorcery(
    name="Pest Control",
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Destroy all nonland permanents with mana value 1 or less.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="mythic",
)

LOST_JITTE = make_artifact(
    name="Lost Jitte",
    mana_cost="{1}",
    text="Whenever equipped creature deals combat damage, put a charge counter on Lost Jitte.\nRemove a charge counter from Lost Jitte: Choose one —\n• Untap target land.\n• Target creature can't block this turn.\n• Put a +1/+1 counter on equipped creature.\nEquip {1}",
    rarity="mythic",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

LOTUS_RING = make_artifact(
    name="Lotus Ring",
    mana_cost="{3}",
    text="Indestructible\nEquipped creature gets +3/+3 and has vigilance and \"{T}, Sacrifice this creature: Add three mana of any one color.\"\nEquip {3}",
    rarity="mythic",
    subtypes={"Equipment"},
)

NEXUS_OF_BECOMING = make_artifact(
    name="Nexus of Becoming",
    mana_cost="{6}",
    text="At the beginning of combat on your turn, draw a card. Then you may exile an artifact or creature card from your hand. If you do, create a token that's a copy of the exiled card, except it's a 3/3 Golem artifact creature in addition to its other types.",
    rarity="mythic",
)

SWORD_OF_WEALTH_AND_POWER = make_artifact(
    name="Sword of Wealth and Power",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has protection from instants and from sorceries.\nWhenever equipped creature deals combat damage to a player, create a Treasure token. When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.\nEquip {2}",
    rarity="mythic",
    subtypes={"Equipment"},
)

TORPOR_ORB = make_artifact(
    name="Torpor Orb",
    mana_cost="{2}",
    text="Creatures entering don't cause abilities to trigger.",
    rarity="mythic",
    setup_interceptors=torpor_orb_setup,
)

TRANSMUTATION_FONT = make_artifact(
    name="Transmutation Font",
    mana_cost="{5}",
    text="{T}: Create your choice of a Blood token, a Clue token, or a Food token.\n{3}, {T}, Sacrifice three artifact tokens with different names: Search your library for an artifact card, put it onto the battlefield, then shuffle. Activate only as a sorcery.",
    rarity="mythic",
)

FOMORI_VAULT = make_land(
    name="Fomori Vault",
    text="{T}: Add {C}.\n{3}, {T}, Discard a card: Look at the top X cards of your library, where X is the number of artifacts you control. Put one of those cards into your hand and the rest on the bottom of your library in a random order.",
    rarity="mythic",
)

TARNATION_VISTA = make_land(
    name="Tarnation Vista",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.\n{1}, {T}: For each color among monocolored permanents you control, add one mana of that color.",
    rarity="mythic",
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

THE_BIG_SCORE_CARDS = {
    "Collector's Cage": COLLECTORS_CAGE,
    "Grand Abolisher": GRAND_ABOLISHER,
    "Oltec Matterweaver": OLTEC_MATTERWEAVER,
    "Rest in Peace": REST_IN_PEACE,
    "Esoteric Duplicator": ESOTERIC_DUPLICATOR,
    "Simulacrum Synthesizer": SIMULACRUM_SYNTHESIZER,
    "Worldwalker Helm": WORLDWALKER_HELM,
    "Greed's Gambit": GREEDS_GAMBIT,
    "Harvester of Misery": HARVESTER_OF_MISERY,
    "Hostile Investigator": HOSTILE_INVESTIGATOR,
    "Generous Plunderer": GENEROUS_PLUNDERER,
    "Legion Extruder": LEGION_EXTRUDER,
    "Memory Vessel": MEMORY_VESSEL,
    "Molten Duplication": MOLTEN_DUPLICATION,
    "Territory Forge": TERRITORY_FORGE,
    "Ancient Cornucopia": ANCIENT_CORNUCOPIA,
    "Bristlebud Farmer": BRISTLEBUD_FARMER,
    "Omenpath Journey": OMENPATH_JOURNEY,
    "Sandstorm Salvager": SANDSTORM_SALVAGER,
    "Vaultborn Tyrant": VAULTBORN_TYRANT,
    "Loot, the Key to Everything": LOOT_THE_KEY_TO_EVERYTHING,
    "Pest Control": PEST_CONTROL,
    "Lost Jitte": LOST_JITTE,
    "Lotus Ring": LOTUS_RING,
    "Nexus of Becoming": NEXUS_OF_BECOMING,
    "Sword of Wealth and Power": SWORD_OF_WEALTH_AND_POWER,
    "Torpor Orb": TORPOR_ORB,
    "Transmutation Font": TRANSMUTATION_FONT,
    "Fomori Vault": FOMORI_VAULT,
    "Tarnation Vista": TARNATION_VISTA,
}

print(f"Loaded {len(THE_BIG_SCORE_CARDS)} The Big Score cards")
