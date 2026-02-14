"""
Hearthstone Card Sets

Complete Basic + Classic card pool (~373 collectible cards).
"""

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import BASIC_CARDS, THE_COIN
from src.cards.hearthstone.classic import CLASSIC_CARDS, CLASSIC_MINIONS, CLASSIC_SPELLS, CLASSIC_WEAPONS
from src.cards.hearthstone.tokens import ALL_TOKENS
from src.cards.hearthstone.druid import DRUID_CARDS
from src.cards.hearthstone.hunter import HUNTER_CARDS
from src.cards.hearthstone.mage import MAGE_CARDS
from src.cards.hearthstone.paladin import PALADIN_CARDS
from src.cards.hearthstone.priest import PRIEST_CARDS
from src.cards.hearthstone.rogue import ROGUE_CARDS
from src.cards.hearthstone.shaman import SHAMAN_CARDS
from src.cards.hearthstone.warlock import WARLOCK_CARDS
from src.cards.hearthstone.warrior import WARRIOR_CARDS
from src.cards.hearthstone.decks import HEARTHSTONE_DECKS, get_deck_for_hero, validate_deck

# All class cards by class name
CLASS_CARDS = {
    "Druid": DRUID_CARDS,
    "Hunter": HUNTER_CARDS,
    "Mage": MAGE_CARDS,
    "Paladin": PALADIN_CARDS,
    "Priest": PRIEST_CARDS,
    "Rogue": ROGUE_CARDS,
    "Shaman": SHAMAN_CARDS,
    "Warlock": WARLOCK_CARDS,
    "Warrior": WARRIOR_CARDS,
}

# All collectible cards
ALL_CARDS = BASIC_CARDS + CLASSIC_CARDS
for class_cards in CLASS_CARDS.values():
    ALL_CARDS = ALL_CARDS + class_cards
