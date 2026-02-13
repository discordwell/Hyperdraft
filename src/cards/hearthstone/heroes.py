"""
Hearthstone Hero Cards

The 9 classic Hearthstone heroes.
"""

from src.engine.game import make_hero


# Mage Hero
JAINA_PROUDMOORE = make_hero(
    name="Jaina Proudmoore",
    hero_class="Mage",
    starting_life=30,
    text="Hero Power: Fireblast (Deal 1 damage)",
    rarity="Basic"
)

# Warrior Hero
GARROSH_HELLSCREAM = make_hero(
    name="Garrosh Hellscream",
    hero_class="Warrior",
    starting_life=30,
    text="Hero Power: Armor Up! (Gain 2 Armor)",
    rarity="Basic"
)

# Hunter Hero
REXXAR = make_hero(
    name="Rexxar",
    hero_class="Hunter",
    starting_life=30,
    text="Hero Power: Steady Shot (Deal 2 damage to enemy hero)",
    rarity="Basic"
)

# Paladin Hero
UTHER_LIGHTBRINGER = make_hero(
    name="Uther Lightbringer",
    hero_class="Paladin",
    starting_life=30,
    text="Hero Power: Reinforce (Summon a 1/1 Silver Hand Recruit)",
    rarity="Basic"
)

# Priest Hero
ANDUIN_WRYNN = make_hero(
    name="Anduin Wrynn",
    hero_class="Priest",
    starting_life=30,
    text="Hero Power: Lesser Heal (Restore 2 Health)",
    rarity="Basic"
)

# Rogue Hero
VALEERA_SANGUINAR = make_hero(
    name="Valeera Sanguinar",
    hero_class="Rogue",
    starting_life=30,
    text="Hero Power: Dagger Mastery (Equip a 1/2 Dagger)",
    rarity="Basic"
)

# Shaman Hero
THRALL = make_hero(
    name="Thrall",
    hero_class="Shaman",
    starting_life=30,
    text="Hero Power: Totemic Call (Summon a random Totem)",
    rarity="Basic"
)

# Warlock Hero
GULDAN = make_hero(
    name="Gul'dan",
    hero_class="Warlock",
    starting_life=30,
    text="Hero Power: Life Tap (Draw a card and take 2 damage)",
    rarity="Basic"
)

# Druid Hero
MALFURION_STORMRAGE = make_hero(
    name="Malfurion Stormrage",
    hero_class="Druid",
    starting_life=30,
    text="Hero Power: Shapeshift (+1 Attack this turn, +1 Armor)",
    rarity="Basic"
)


# Hero registry for easy access
HEROES = {
    "Mage": JAINA_PROUDMOORE,
    "Warrior": GARROSH_HELLSCREAM,
    "Hunter": REXXAR,
    "Paladin": UTHER_LIGHTBRINGER,
    "Priest": ANDUIN_WRYNN,
    "Rogue": VALEERA_SANGUINAR,
    "Shaman": THRALL,
    "Warlock": GULDAN,
    "Druid": MALFURION_STORMRAGE,
}
