"""
Standard Netdecks for Hyperdraft

Current Standard meta decks built from Edge of Eternities, Avatar: The Last Airbender,
Lorwyn Eclipsed, and other legal sets.

These decks are balanced with proper mana bases (~24 lands) and competitive card choices.
"""

import random
from .deck import Deck, DeckEntry


# =============================================================================
# MONO-RED AGGRO - Fast, aggressive red deck
# =============================================================================

MONO_RED_AGGRO = Deck(
    name="Mono-Red Aggro",
    archetype="Aggro",
    colors=["R"],
    description="Fast aggressive deck that aims to deal 20 damage as quickly as possible.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Chrono-Berserker", 4),
        DeckEntry("Time Rager", 4),
        DeckEntry("Accelerated Striker", 4),
        DeckEntry("Accelerated Scout", 4),
        DeckEntry("Rift Elemental", 4),
        DeckEntry("Temporal Phoenix", 2),
        DeckEntry("Accelerated Dragon", 2),

        # Spells (12)
        DeckEntry("Lightning Bolt", 4),
        DeckEntry("Accelerate", 4),
        DeckEntry("Temporal Storm", 2),
        DeckEntry("Chrono-Fury", 2),

        # Lands (24)
        DeckEntry("Mountain", 20),
        DeckEntry("Accelerated Peak", 4),
    ],
    sideboard=[
        DeckEntry("Shattered Timeline", 3),
        DeckEntry("Chaos Rift", 2),
        DeckEntry("Echo Flames", 4),
        DeckEntry("Blaze Through Time", 3),
        DeckEntry("Temporal Inferno", 3),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# MONO-GREEN RAMP - Big creatures and mana acceleration
# =============================================================================

MONO_GREEN_RAMP = Deck(
    name="Mono-Green Ramp",
    archetype="Midrange",
    colors=["G"],
    description="Ramp into big threats with mana acceleration and overwhelm with large creatures.",
    mainboard=[
        # Creatures (26)
        DeckEntry("Seedling of Ages", 4),
        DeckEntry("Elder Chronomancer", 4),
        DeckEntry("Chronicle Beast", 4),
        DeckEntry("Echo of the Wild", 4),
        DeckEntry("Ageless Oak", 3),
        DeckEntry("Primordial Titan", 3),
        DeckEntry("Chronicle Wolf", 2),
        DeckEntry("Timeless Elk", 2),

        # Spells (10)
        DeckEntry("Temporal Growth", 4),
        DeckEntry("Temporal Bloom", 4),
        DeckEntry("Nature Reclaims", 2),

        # Lands (24)
        DeckEntry("Forest", 20),
        DeckEntry("Timeless Forest", 4),
    ],
    sideboard=[
        DeckEntry("Cycle of Eternity", 3),
        DeckEntry("Primal Growth", 2),
        DeckEntry("Ageless Wurm", 2),
        DeckEntry("Timeless Vigor", 4),
        DeckEntry("Grove Tender", 4),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# DIMIR CONTROL - Blue/Black control with card advantage
# =============================================================================

DIMIR_CONTROL = Deck(
    name="Dimir Control",
    archetype="Control",
    colors=["U", "B"],
    description="Control the game with removal, counterspells, and card advantage.",
    mainboard=[
        # Creatures (8)
        DeckEntry("Temporal Vampire", 4),
        DeckEntry("Chrono-Reaper", 2),
        DeckEntry("Entropy Wraith", 2),

        # Spells (28)
        DeckEntry("Temporal Loop", 4),
        DeckEntry("Rewind Moment", 4),
        DeckEntry("Fate Unwritten", 4),
        DeckEntry("Stolen Moment", 4),
        DeckEntry("Timeless Decay", 3),
        DeckEntry("Grave Timeline", 3),
        DeckEntry("Glimpse Beyond Time", 4),
        DeckEntry("Temporal Torment", 2),

        # Lands (24)
        DeckEntry("Island", 10),
        DeckEntry("Swamp", 10),
        DeckEntry("Suspended Island", 2),
        DeckEntry("Entropy Pool", 2),
    ],
    sideboard=[
        DeckEntry("Echo of Death", 3),
        DeckEntry("Entropy Walker", 2),
        DeckEntry("Decay of Ages", 2),
        DeckEntry("Temporal Drain", 4),
        DeckEntry("Entropy Shade", 4),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# BOROS AGGRO - Red/White aggressive deck
# =============================================================================

BOROS_AGGRO = Deck(
    name="Boros Aggro",
    archetype="Aggro",
    colors=["R", "W"],
    description="Fast aggressive deck combining red's burn with white's efficient creatures.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Chrono-Paladin", 4),
        DeckEntry("Temporal Guardian", 4),
        DeckEntry("Accelerated Striker", 4),
        DeckEntry("Timeless Sentinel", 4),
        DeckEntry("Keeper of Moments", 4),
        DeckEntry("Eternity Warden", 4),

        # Spells (12)
        DeckEntry("Lightning Bolt", 4),
        DeckEntry("Moment of Clarity", 4),
        DeckEntry("Dawn of New Era", 2),
        DeckEntry("Preserved Memory", 2),

        # Lands (24)
        DeckEntry("Plains", 10),
        DeckEntry("Mountain", 10),
        DeckEntry("Accelerated Plains", 2),
        DeckEntry("Accelerated Peak", 2),
    ],
    sideboard=[
        DeckEntry("Chronicle of Ages", 3),
        DeckEntry("Temporal Sanctuary", 2),
        DeckEntry("Shattered Timeline", 2),
        DeckEntry("Echo Flames", 4),
        DeckEntry("Eternal Blessing", 4),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# SIMIC TEMPO - Blue/Green tempo with efficient threats
# =============================================================================

SIMIC_TEMPO = Deck(
    name="Simic Tempo",
    archetype="Tempo",
    colors=["U", "G"],
    description="Efficient creatures backed by counterspells and card draw.",
    mainboard=[
        # Creatures (22)
        DeckEntry("Echo of Tomorrow", 4),
        DeckEntry("Paradox Entity", 4),
        DeckEntry("Chronicle Beast", 4),
        DeckEntry("Echo of the Wild", 4),
        DeckEntry("Chronomancer Supreme", 2),
        DeckEntry("Time Weaver", 4),

        # Spells (14)
        DeckEntry("Temporal Loop", 4),
        DeckEntry("Rewind Moment", 4),
        DeckEntry("Temporal Growth", 4),
        DeckEntry("Nature Reclaims", 2),

        # Lands (24)
        DeckEntry("Island", 10),
        DeckEntry("Forest", 10),
        DeckEntry("Suspended Island", 2),
        DeckEntry("Timeless Forest", 2),
    ],
    sideboard=[
        DeckEntry("Glimpse Beyond Time", 3),
        DeckEntry("Cycle of Eternity", 2),
        DeckEntry("Primordial Titan", 2),
        DeckEntry("Chrono-Shift", 4),
        DeckEntry("Ageless Oak", 4),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# AVATAR AIRBENDER - Bant (WUG) Avatar-themed deck
# =============================================================================

AVATAR_AIRBENDER = Deck(
    name="Avatar Airbender",
    archetype="Midrange",
    colors=["W", "U", "G"],
    description="Avatar-themed deck featuring Aang and airbending synergies.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Aang, Swift Savior", 4),
        DeckEntry("Appa, Steadfast Guardian", 4),
        DeckEntry("Airbender Initiate", 4),
        DeckEntry("Air Acolyte", 4),
        DeckEntry("Badgermole Cub", 4),
        DeckEntry("Keeper of Moments", 4),

        # Spells (12)
        DeckEntry("Airbender Ascension", 4),
        DeckEntry("Airbender's Flight", 4),
        DeckEntry("Moment of Clarity", 4),

        # Lands (24)
        DeckEntry("Plains", 8),
        DeckEntry("Island", 8),
        DeckEntry("Forest", 8),
    ],
    sideboard=[
        DeckEntry("Air Temple", 2),
        DeckEntry("Airbending Scroll", 4),
        DeckEntry("Avatar State Fury", 2),
        DeckEntry("Preserved Memory", 4),
        DeckEntry("Nature Reclaims", 3),
    ],
    author="Meta",
    source="Avatar: The Last Airbender Set",
)


# =============================================================================
# FIRE NATION AGGRO - Red/Black Aggro Avatar deck
# =============================================================================

FIRE_NATION_AGGRO = Deck(
    name="Fire Nation Aggro",
    archetype="Aggro",
    colors=["R", "B"],
    description="Aggressive Fire Nation deck with burn and disruption.",
    mainboard=[
        # Creatures (20)
        DeckEntry("Azula, Cunning Usurper", 4),
        DeckEntry("Chrono-Berserker", 4),
        DeckEntry("Time Rager", 4),
        DeckEntry("Entropy Walker", 4),
        DeckEntry("Accelerated Striker", 4),

        # Spells (16)
        DeckEntry("Lightning Bolt", 4),
        DeckEntry("Accelerate", 4),
        DeckEntry("Fate Unwritten", 4),
        DeckEntry("Stolen Moment", 4),

        # Lands (24)
        DeckEntry("Mountain", 12),
        DeckEntry("Swamp", 10),
        DeckEntry("Entropy Marsh", 2),
    ],
    sideboard=[
        DeckEntry("Agni Kai", 4),
        DeckEntry("Chrono-Fury", 4),
        DeckEntry("Echo of Death", 3),
        DeckEntry("Temporal Torment", 2),
        DeckEntry("Shattered Timeline", 2),
    ],
    author="Meta",
    source="Avatar: The Last Airbender Set",
)


# =============================================================================
# LORWYN FAERIES - Blue/Black Faerie tribal
# =============================================================================

LORWYN_FAERIES = Deck(
    name="Lorwyn Faeries",
    archetype="Tempo",
    colors=["U", "B"],
    description="Classic Faerie tribal with flash creatures and countermagic.",
    mainboard=[
        # Creatures (20)
        DeckEntry("Glen Elendra Guardian", 4),
        DeckEntry("Flitterwing Nuisance", 4),
        DeckEntry("Glamermite", 4),
        DeckEntry("Dream Seizer", 4),
        DeckEntry("Gravelgill Scoundrel", 4),

        # Spells (16)
        DeckEntry("Temporal Loop", 4),
        DeckEntry("Rewind Moment", 4),
        DeckEntry("Blight Rot", 4),
        DeckEntry("Midnight Tilling", 4),

        # Lands (24)
        DeckEntry("Island", 12),
        DeckEntry("Swamp", 12),
    ],
    sideboard=[
        DeckEntry("Darkness Descends", 4),
        DeckEntry("Auntie's Sentence", 4),
        DeckEntry("Bloodline Bidding", 3),
        DeckEntry("Fate Unwritten", 4),
    ],
    author="Meta",
    source="Lorwyn Eclipsed Set",
)


# =============================================================================
# DECK REGISTRY
# =============================================================================

STANDARD_DECKS = {
    "mono_red_aggro": MONO_RED_AGGRO,
    "mono_green_ramp": MONO_GREEN_RAMP,
    "dimir_control": DIMIR_CONTROL,
    "boros_aggro": BOROS_AGGRO,
    "simic_tempo": SIMIC_TEMPO,
    "avatar_airbender": AVATAR_AIRBENDER,
    "fire_nation_aggro": FIRE_NATION_AGGRO,
    "lorwyn_faeries": LORWYN_FAERIES,
}


def get_deck(deck_id: str) -> Deck:
    """Get a deck by ID."""
    deck = STANDARD_DECKS.get(deck_id)
    if not deck:
        raise ValueError(f"Unknown deck: {deck_id}. Available: {list(STANDARD_DECKS.keys())}")
    return deck


def get_random_deck() -> Deck:
    """Get a random deck from the registry."""
    return random.choice(list(STANDARD_DECKS.values()))


def get_decks_by_archetype(archetype: str) -> list[Deck]:
    """Get all decks of a specific archetype."""
    return [d for d in STANDARD_DECKS.values() if d.archetype == archetype]


def get_decks_by_color(color: str) -> list[Deck]:
    """Get all decks containing a specific color."""
    return [d for d in STANDARD_DECKS.values() if color in d.colors]
