# Custom/Themed Card Sets
"""
Custom card sets based on popular franchises and fan-made content.
These are separate from the main MTG Standard rotation.

Some sets are marked with _CUSTOM suffix to indicate they are fan-made
versions of real MTG Universes Beyond sets that were released after
our knowledge cutoff.
"""

# Fan-made versions of real UB sets (post-cutoff releases)
from .penultimate_avatar import AVATAR_TLA_CUSTOM_CARDS
from .man_of_pider import SPIDER_MAN_CUSTOM_CARDS
from .princess_catholicon import FINAL_FANTASY_CUSTOM_CARDS
from .temporal_horizons import TEMPORAL_HORIZONS_CARDS
from .lorwyn_custom import LORWYN_CUSTOM_CARDS

# Original custom/crossover sets
from .star_wars import STAR_WARS_CARDS
from .demon_slayer import DEMON_SLAYER_CARDS
from .one_piece import ONE_PIECE_CARDS
from .pokemon_horizons import POKEMON_HORIZONS_CARDS
from .legend_of_zelda import LEGEND_OF_ZELDA_CARDS
from .studio_ghibli import STUDIO_GHIBLI_CARDS
from .my_hero_academia import MY_HERO_ACADEMIA_CARDS
from .lord_of_the_rings import LORD_OF_THE_RINGS_CARDS
from .jujutsu_kaisen import JUJUTSU_KAISEN_CARDS
from .attack_on_titan import ATTACK_ON_TITAN_CARDS
from .harry_potter import HARRY_POTTER_CARDS
from .marvel_avengers import MARVEL_AVENGERS_CARDS
from .naruto import NARUTO_CARDS
from .dragon_ball import DRAGON_BALL_CARDS


_CARD_REF_SEP = "::"

# Domain (cardspace) -> set registry for custom sets.
#
# Important: This must not be a single dict keyed by bare card name, since many
# custom sets share names (e.g. basic lands) and will collide.
CUSTOM_SETS: dict[str, dict] = {
    # Fan-made versions of official UB sets / other large custom sets
    "TLAC": AVATAR_TLA_CUSTOM_CARDS,
    "SPMC": SPIDER_MAN_CUSTOM_CARDS,
    "FINC": FINAL_FANTASY_CUSTOM_CARDS,
    "TMH": TEMPORAL_HORIZONS_CARDS,
    "LRW": LORWYN_CUSTOM_CARDS,

    # Original custom/crossover sets
    "SWR": STAR_WARS_CARDS,
    "DMS": DEMON_SLAYER_CARDS,
    "OPC": ONE_PIECE_CARDS,
    "PKH": POKEMON_HORIZONS_CARDS,
    "ZLD": LEGEND_OF_ZELDA_CARDS,
    "GHB": STUDIO_GHIBLI_CARDS,
    "MHA": MY_HERO_ACADEMIA_CARDS,
    "LTR": LORD_OF_THE_RINGS_CARDS,
    "JJK": JUJUTSU_KAISEN_CARDS,
    "AOT": ATTACK_ON_TITAN_CARDS,
    "HPW": HARRY_POTTER_CARDS,
    "MVL": MARVEL_AVENGERS_CARDS,
    "NRT": NARUTO_CARDS,
    "DBZ": DRAGON_BALL_CARDS,
}


def _apply_domains() -> None:
    """Stamp `domain` on CardDefinitions for custom sets at import time."""
    for domain, cards in CUSTOM_SETS.items():
        for card_def in cards.values():
            try:
                card_def.domain = domain
            except Exception:
                # Some older card definitions may be plain dicts or otherwise not
                # have a writable attribute; ignore those safely.
                pass


_apply_domains()


def build_custom_registry() -> dict:
    """
    Build a combined registry of all custom/themed cards keyed by card ref.

    Key format: "{DOMAIN}::{CARD_NAME}" (e.g. "TMH::Chrono-Berserker").
    """
    registry: dict[str, object] = {}
    for domain, cards in CUSTOM_SETS.items():
        for name, card_def in cards.items():
            registry[f"{domain}{_CARD_REF_SEP}{name}"] = card_def
    return registry


CUSTOM_CARDS = build_custom_registry()

__all__ = [
    # Fan-made versions of real UB sets
    'AVATAR_TLA_CUSTOM_CARDS',
    'SPIDER_MAN_CUSTOM_CARDS',
    'FINAL_FANTASY_CUSTOM_CARDS',
    'TEMPORAL_HORIZONS_CARDS',
    'LORWYN_CUSTOM_CARDS',
    # Original custom sets
    'STAR_WARS_CARDS',
    'DEMON_SLAYER_CARDS',
    'ONE_PIECE_CARDS',
    'POKEMON_HORIZONS_CARDS',
    'LEGEND_OF_ZELDA_CARDS',
    'STUDIO_GHIBLI_CARDS',
    'MY_HERO_ACADEMIA_CARDS',
    'LORD_OF_THE_RINGS_CARDS',
    'JUJUTSU_KAISEN_CARDS',
    'ATTACK_ON_TITAN_CARDS',
    'HARRY_POTTER_CARDS',
    'MARVEL_AVENGERS_CARDS',
    'NARUTO_CARDS',
    'DRAGON_BALL_CARDS',
    # Combined
    'CUSTOM_CARDS',
    'CUSTOM_SETS',
    'build_custom_registry',
]
