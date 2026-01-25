# Custom/Themed Card Sets
"""
Custom card sets based on popular franchises.
These are separate from the main MTG Standard rotation.
"""

from .avatar_tla import AVATAR_TLA_CARDS
from .spider_man import SPIDER_MAN_CARDS
from .star_wars import STAR_WARS_CARDS
from .demon_slayer import DEMON_SLAYER_CARDS
from .one_piece import ONE_PIECE_CARDS
from .pokemon_horizons import POKEMON_HORIZONS_CARDS
from .legend_of_zelda import LEGEND_OF_ZELDA_CARDS
from .studio_ghibli import STUDIO_GHIBLI_CARDS
from .my_hero_academia import MY_HERO_ACADEMIA_CARDS
from .final_fantasy import FINAL_FANTASY_CARDS
from .lord_of_the_rings import LORD_OF_THE_RINGS_CARDS
from .jujutsu_kaisen import JUJUTSU_KAISEN_CARDS
from .attack_on_titan import ATTACK_ON_TITAN_CARDS
from .harry_potter import HARRY_POTTER_CARDS
from .marvel_avengers import MARVEL_AVENGERS_CARDS
from .naruto import NARUTO_CARDS
from .dragon_ball import DRAGON_BALL_CARDS


def build_custom_registry() -> dict:
    """Build a combined registry of all custom/themed card sets."""
    registry = {}
    registry.update(AVATAR_TLA_CARDS)
    registry.update(SPIDER_MAN_CARDS)
    registry.update(STAR_WARS_CARDS)
    registry.update(DEMON_SLAYER_CARDS)
    registry.update(ONE_PIECE_CARDS)
    registry.update(POKEMON_HORIZONS_CARDS)
    registry.update(LEGEND_OF_ZELDA_CARDS)
    registry.update(STUDIO_GHIBLI_CARDS)
    registry.update(MY_HERO_ACADEMIA_CARDS)
    registry.update(FINAL_FANTASY_CARDS)
    registry.update(LORD_OF_THE_RINGS_CARDS)
    registry.update(JUJUTSU_KAISEN_CARDS)
    registry.update(ATTACK_ON_TITAN_CARDS)
    registry.update(HARRY_POTTER_CARDS)
    registry.update(MARVEL_AVENGERS_CARDS)
    registry.update(NARUTO_CARDS)
    registry.update(DRAGON_BALL_CARDS)
    return registry


CUSTOM_CARDS = build_custom_registry()

__all__ = [
    'AVATAR_TLA_CARDS',
    'SPIDER_MAN_CARDS',
    'STAR_WARS_CARDS',
    'DEMON_SLAYER_CARDS',
    'ONE_PIECE_CARDS',
    'POKEMON_HORIZONS_CARDS',
    'LEGEND_OF_ZELDA_CARDS',
    'STUDIO_GHIBLI_CARDS',
    'MY_HERO_ACADEMIA_CARDS',
    'FINAL_FANTASY_CARDS',
    'LORD_OF_THE_RINGS_CARDS',
    'JUJUTSU_KAISEN_CARDS',
    'ATTACK_ON_TITAN_CARDS',
    'HARRY_POTTER_CARDS',
    'MARVEL_AVENGERS_CARDS',
    'NARUTO_CARDS',
    'DRAGON_BALL_CARDS',
    'CUSTOM_CARDS',
    'build_custom_registry',
]
