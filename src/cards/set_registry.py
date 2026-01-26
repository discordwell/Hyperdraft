"""
Set Registry Module

Maps cards to their sets and provides set metadata.
This avoids modifying 7,850+ CardDefinition objects while still
enabling set-based browsing in the Gatherer interface.
"""

from dataclasses import dataclass
from typing import Optional

# Import all card registries
from . import (
    TEST_CARDS,
    WILDS_OF_ELDRAINE_CARDS,
    LOST_CAVERNS_IXALAN_CARDS,
    MURDERS_KARLOV_MANOR_CARDS,
    OUTLAWS_THUNDER_JUNCTION_CARDS,
    THE_BIG_SCORE_CARDS,
    BLOOMBURROW_CARDS,
    DUSKMOURN_CARDS,
    FOUNDATIONS_CARDS,
    AETHERDRIFT_CARDS,
    TARKIR_DRAGONSTORM_CARDS,
    EDGE_OF_ETERNITIES_CARDS,
    LORWYN_ECLIPSED_CARDS,
    SPIDER_MAN_CARDS,
    AVATAR_TLA_CARDS,
    FINAL_FANTASY_CARDS,
)

# Import custom sets
from .custom import (
    AVATAR_TLA_CUSTOM_CARDS,
    SPIDER_MAN_CUSTOM_CARDS,
    FINAL_FANTASY_CUSTOM_CARDS,
    TEMPORAL_HORIZONS_CARDS,
    LORWYN_CUSTOM_CARDS,
    STAR_WARS_CARDS,
    DEMON_SLAYER_CARDS,
    ONE_PIECE_CARDS,
    POKEMON_HORIZONS_CARDS,
    LEGEND_OF_ZELDA_CARDS,
    STUDIO_GHIBLI_CARDS,
    MY_HERO_ACADEMIA_CARDS,
    LORD_OF_THE_RINGS_CARDS,
    JUJUTSU_KAISEN_CARDS,
    ATTACK_ON_TITAN_CARDS,
    HARRY_POTTER_CARDS,
    MARVEL_AVENGERS_CARDS,
    NARUTO_CARDS,
    DRAGON_BALL_CARDS,
)


@dataclass
class SetInfo:
    """Metadata for a card set."""
    code: str           # Short code (e.g., "WOE", "BLB")
    name: str           # Full name (e.g., "Wilds of Eldraine")
    card_count: int     # Number of cards in set
    release_date: str   # ISO date string
    set_type: str       # "standard", "universes_beyond", "custom"
    icon: Optional[str] = None  # Optional icon/symbol


# =============================================================================
# Set Definitions
# =============================================================================

SETS: dict[str, SetInfo] = {
    # Test set
    "TST": SetInfo("TST", "Test Cards", len(TEST_CARDS), "2024-01-01", "test"),

    # MTG Standard Rotation Sets
    "WOE": SetInfo("WOE", "Wilds of Eldraine", len(WILDS_OF_ELDRAINE_CARDS), "2023-09-08", "standard"),
    "LCI": SetInfo("LCI", "Lost Caverns of Ixalan", len(LOST_CAVERNS_IXALAN_CARDS), "2023-11-17", "standard"),
    "MKM": SetInfo("MKM", "Murders at Karlov Manor", len(MURDERS_KARLOV_MANOR_CARDS), "2024-02-09", "standard"),
    "OTJ": SetInfo("OTJ", "Outlaws of Thunder Junction", len(OUTLAWS_THUNDER_JUNCTION_CARDS), "2024-04-19", "standard"),
    "BIG": SetInfo("BIG", "The Big Score", len(THE_BIG_SCORE_CARDS), "2024-04-19", "standard"),
    "BLB": SetInfo("BLB", "Bloomburrow", len(BLOOMBURROW_CARDS), "2024-08-02", "standard"),
    "DSK": SetInfo("DSK", "Duskmourn: House of Horror", len(DUSKMOURN_CARDS), "2024-09-27", "standard"),
    "FDN": SetInfo("FDN", "Foundations", len(FOUNDATIONS_CARDS), "2024-11-15", "standard"),
    "DFT": SetInfo("DFT", "Aetherdrift", len(AETHERDRIFT_CARDS), "2025-02-14", "standard"),
    "TKR": SetInfo("TKR", "Tarkir Dragonstorm", len(TARKIR_DRAGONSTORM_CARDS), "2025-04-11", "standard"),

    # Universes Beyond (Official Sets from Scryfall)
    "EOE": SetInfo("EOE", "Edge of Eternities", len(EDGE_OF_ETERNITIES_CARDS), "2025-05-16", "universes_beyond"),
    "ECL": SetInfo("ECL", "Lorwyn Eclipsed", len(LORWYN_ECLIPSED_CARDS), "2025-05-23", "universes_beyond"),
    "SPM": SetInfo("SPM", "Spider-Man", len(SPIDER_MAN_CARDS), "2025-06-06", "universes_beyond"),
    "TLA": SetInfo("TLA", "Avatar: The Last Airbender", len(AVATAR_TLA_CARDS), "2025-06-13", "universes_beyond"),
    "FIN": SetInfo("FIN", "Final Fantasy", len(FINAL_FANTASY_CARDS), "2025-07-25", "universes_beyond"),

    # Custom Sets (Fan-Made with Interceptors)
    "TLAC": SetInfo("TLAC", "Avatar: TLA (Custom)", len(AVATAR_TLA_CUSTOM_CARDS), "2024-01-01", "custom"),
    "SPMC": SetInfo("SPMC", "Spider-Man (Custom)", len(SPIDER_MAN_CUSTOM_CARDS), "2024-01-01", "custom"),
    "FINC": SetInfo("FINC", "Final Fantasy (Custom)", len(FINAL_FANTASY_CUSTOM_CARDS), "2024-01-01", "custom"),
    "TMH": SetInfo("TMH", "Temporal Horizons", len(TEMPORAL_HORIZONS_CARDS), "2024-01-01", "custom"),
    "LRW": SetInfo("LRW", "Lorwyn (Custom)", len(LORWYN_CUSTOM_CARDS), "2024-01-01", "custom"),
    "SWR": SetInfo("SWR", "Star Wars", len(STAR_WARS_CARDS), "2024-01-01", "custom"),
    "DMS": SetInfo("DMS", "Demon Slayer", len(DEMON_SLAYER_CARDS), "2024-01-01", "custom"),
    "OPC": SetInfo("OPC", "One Piece", len(ONE_PIECE_CARDS), "2024-01-01", "custom"),
    "PKH": SetInfo("PKH", "Pokemon Horizons", len(POKEMON_HORIZONS_CARDS), "2024-01-01", "custom"),
    "ZLD": SetInfo("ZLD", "Legend of Zelda", len(LEGEND_OF_ZELDA_CARDS), "2024-01-01", "custom"),
    "GHB": SetInfo("GHB", "Studio Ghibli", len(STUDIO_GHIBLI_CARDS), "2024-01-01", "custom"),
    "MHA": SetInfo("MHA", "My Hero Academia", len(MY_HERO_ACADEMIA_CARDS), "2024-01-01", "custom"),
    "LTR": SetInfo("LTR", "Lord of the Rings", len(LORD_OF_THE_RINGS_CARDS), "2024-01-01", "custom"),
    "JJK": SetInfo("JJK", "Jujutsu Kaisen", len(JUJUTSU_KAISEN_CARDS), "2024-01-01", "custom"),
    "AOT": SetInfo("AOT", "Attack on Titan", len(ATTACK_ON_TITAN_CARDS), "2024-01-01", "custom"),
    "HPW": SetInfo("HPW", "Harry Potter", len(HARRY_POTTER_CARDS), "2024-01-01", "custom"),
    "MVL": SetInfo("MVL", "Marvel Avengers", len(MARVEL_AVENGERS_CARDS), "2024-01-01", "custom"),
    "NRT": SetInfo("NRT", "Naruto", len(NARUTO_CARDS), "2024-01-01", "custom"),
    "DBZ": SetInfo("DBZ", "Dragon Ball", len(DRAGON_BALL_CARDS), "2024-01-01", "custom"),
}


# =============================================================================
# Card to Set Mapping
# =============================================================================

# Define which card registry belongs to which set
SET_REGISTRIES: list[tuple[str, dict]] = [
    # Test
    ("TST", TEST_CARDS),

    # Standard
    ("WOE", WILDS_OF_ELDRAINE_CARDS),
    ("LCI", LOST_CAVERNS_IXALAN_CARDS),
    ("MKM", MURDERS_KARLOV_MANOR_CARDS),
    ("OTJ", OUTLAWS_THUNDER_JUNCTION_CARDS),
    ("BIG", THE_BIG_SCORE_CARDS),
    ("BLB", BLOOMBURROW_CARDS),
    ("DSK", DUSKMOURN_CARDS),
    ("FDN", FOUNDATIONS_CARDS),
    ("DFT", AETHERDRIFT_CARDS),
    ("TKR", TARKIR_DRAGONSTORM_CARDS),

    # Universes Beyond
    ("EOE", EDGE_OF_ETERNITIES_CARDS),
    ("ECL", LORWYN_ECLIPSED_CARDS),
    ("SPM", SPIDER_MAN_CARDS),
    ("TLA", AVATAR_TLA_CARDS),
    ("FIN", FINAL_FANTASY_CARDS),

    # Custom
    ("TLAC", AVATAR_TLA_CUSTOM_CARDS),
    ("SPMC", SPIDER_MAN_CUSTOM_CARDS),
    ("FINC", FINAL_FANTASY_CUSTOM_CARDS),
    ("TMH", TEMPORAL_HORIZONS_CARDS),
    ("LRW", LORWYN_CUSTOM_CARDS),
    ("SWR", STAR_WARS_CARDS),
    ("DMS", DEMON_SLAYER_CARDS),
    ("OPC", ONE_PIECE_CARDS),
    ("PKH", POKEMON_HORIZONS_CARDS),
    ("ZLD", LEGEND_OF_ZELDA_CARDS),
    ("GHB", STUDIO_GHIBLI_CARDS),
    ("MHA", MY_HERO_ACADEMIA_CARDS),
    ("LTR", LORD_OF_THE_RINGS_CARDS),
    ("JJK", JUJUTSU_KAISEN_CARDS),
    ("AOT", ATTACK_ON_TITAN_CARDS),
    ("HPW", HARRY_POTTER_CARDS),
    ("MVL", MARVEL_AVENGERS_CARDS),
    ("NRT", NARUTO_CARDS),
    ("DBZ", DRAGON_BALL_CARDS),
]


def build_card_to_set_mapping() -> dict[str, list[str]]:
    """
    Build a mapping from card names to the sets they appear in.

    Returns a dict where keys are card names and values are lists of set codes.
    Cards can appear in multiple sets (e.g., reprints).
    """
    mapping: dict[str, list[str]] = {}

    for set_code, cards in SET_REGISTRIES:
        for card_name in cards.keys():
            if card_name not in mapping:
                mapping[card_name] = []
            mapping[card_name].append(set_code)

    return mapping


def build_set_to_cards_mapping() -> dict[str, dict]:
    """
    Build a mapping from set codes to their card registries.

    Returns a dict where keys are set codes and values are the card dicts.
    """
    return {set_code: cards for set_code, cards in SET_REGISTRIES}


# Pre-build mappings at module load time for performance
CARD_TO_SETS = build_card_to_set_mapping()
SET_TO_CARDS = build_set_to_cards_mapping()


# =============================================================================
# Helper Functions
# =============================================================================

def get_set_info(set_code: str) -> Optional[SetInfo]:
    """Get metadata for a set by its code."""
    return SETS.get(set_code.upper())


def get_sets_for_card(card_name: str) -> list[str]:
    """Get all set codes that contain a card."""
    return CARD_TO_SETS.get(card_name, [])


def get_cards_in_set(set_code: str) -> dict:
    """Get all cards in a set as a dict of name -> CardDefinition."""
    return SET_TO_CARDS.get(set_code.upper(), {})


def get_all_sets(set_type: Optional[str] = None) -> list[SetInfo]:
    """
    Get all sets, optionally filtered by type.

    Args:
        set_type: Filter by set type ("standard", "universes_beyond", "custom")

    Returns:
        List of SetInfo objects sorted by release date (newest first)
    """
    sets = list(SETS.values())

    if set_type:
        sets = [s for s in sets if s.set_type == set_type]

    # Sort by release date (newest first)
    sets.sort(key=lambda s: s.release_date, reverse=True)

    return sets


def get_set_types() -> list[str]:
    """Get all unique set types."""
    return sorted(set(s.set_type for s in SETS.values()))


def get_rarity_breakdown(set_code: str) -> dict[str, int]:
    """
    Get rarity breakdown for a set.

    Returns dict like {"mythic": 5, "rare": 40, "uncommon": 80, "common": 100}
    """
    cards = get_cards_in_set(set_code)
    breakdown: dict[str, int] = {
        "mythic": 0,
        "rare": 0,
        "uncommon": 0,
        "common": 0,
    }

    for card_def in cards.values():
        rarity = getattr(card_def, 'rarity', None) or 'common'
        rarity = rarity.lower()
        if rarity in breakdown:
            breakdown[rarity] += 1
        else:
            breakdown['common'] += 1  # Default unknown to common

    return breakdown


__all__ = [
    'SetInfo',
    'SETS',
    'CARD_TO_SETS',
    'SET_TO_CARDS',
    'get_set_info',
    'get_sets_for_card',
    'get_cards_in_set',
    'get_all_sets',
    'get_set_types',
    'get_rarity_breakdown',
]
