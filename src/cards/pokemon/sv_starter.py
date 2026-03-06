"""
Pokemon TCG Starter Set — Scarlet & Violet Era

Hand-curated set of real SV-era cards for engine testing.
Includes a mix of types, evolution lines, trainers, and energy
sufficient for 2 playable 30-card decks.
"""

from src.engine.game import (
    make_pokemon, make_trainer_item, make_trainer_supporter,
    make_trainer_stadium, make_pokemon_tool, make_basic_energy,
)
from src.engine.types import PokemonType


# =============================================================================
# FIRE POKEMON
# =============================================================================

CHARMANDER = make_pokemon(
    name="Charmander",
    hp=70,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Ember", "cost": [{"type": "R", "count": 1}], "damage": 30,
         "text": "Discard an Energy from this Pokemon."},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=1,
    rarity="common",
)

CHARMELEON = make_pokemon(
    name="Charmeleon",
    hp=100,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Charmander",
    attacks=[
        {"name": "Slash", "cost": [{"type": "C", "count": 2}], "damage": 30, "text": ""},
        {"name": "Fire Fang", "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 2}], "damage": 60, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    rarity="uncommon",
)

CHARIZARD_EX = make_pokemon(
    name="Charizard ex",
    hp=330,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 2",
    evolves_from="Charmeleon",
    attacks=[
        {"name": "Brave Wing", "cost": [{"type": "R", "count": 1}], "damage": 60, "text": ""},
        {"name": "Burning Dark", "cost": [{"type": "R", "count": 2}, {"type": "C", "count": 1}],
         "damage": 180, "text": "This attack does 30 more damage for each Prize card your opponent has taken."},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    is_ex=True,
    rarity="rare",
)

ARCANINE = make_pokemon(
    name="Arcanine",
    hp=130,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1",
    evolves_from="Growlithe",
    attacks=[
        {"name": "Heat Tackle", "cost": [{"type": "R", "count": 2}, {"type": "C", "count": 1}],
         "damage": 120, "text": "This Pokemon also does 30 damage to itself."},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    rarity="uncommon",
)

GROWLITHE = make_pokemon(
    name="Growlithe",
    hp=80,
    pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Bite", "cost": [{"type": "C", "count": 1}], "damage": 10, "text": ""},
        {"name": "Flare", "cost": [{"type": "R", "count": 1}, {"type": "C", "count": 1}], "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.WATER.value,
    retreat_cost=2,
    rarity="common",
)

# =============================================================================
# WATER POKEMON
# =============================================================================

SQUIRTLE = make_pokemon(
    name="Squirtle",
    hp=70,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Water Gun", "cost": [{"type": "W", "count": 1}], "damage": 20, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=1,
    rarity="common",
)

WARTORTLE = make_pokemon(
    name="Wartortle",
    hp=100,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 1",
    evolves_from="Squirtle",
    attacks=[
        {"name": "Wave Splash", "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}], "damage": 40, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=2,
    rarity="uncommon",
)

BLASTOISE_EX = make_pokemon(
    name="Blastoise ex",
    hp=330,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Stage 2",
    evolves_from="Wartortle",
    attacks=[
        {"name": "Surf", "cost": [{"type": "W", "count": 1}, {"type": "C", "count": 1}], "damage": 60, "text": ""},
        {"name": "Twin Cannons", "cost": [{"type": "W", "count": 2}, {"type": "C", "count": 1}],
         "damage": 280, "text": "Discard 2 Energy from this Pokemon."},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=3,
    is_ex=True,
    rarity="rare",
)

LAPRAS = make_pokemon(
    name="Lapras",
    hp=130,
    pokemon_type=PokemonType.WATER.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Icy Wind", "cost": [{"type": "W", "count": 1}], "damage": 30,
         "text": "Your opponent's Active Pokemon is now Asleep."},
        {"name": "Splash Arch", "cost": [{"type": "W", "count": 2}, {"type": "C", "count": 1}],
         "damage": 100, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    retreat_cost=2,
    rarity="uncommon",
)

# =============================================================================
# GRASS POKEMON
# =============================================================================

BULBASAUR = make_pokemon(
    name="Bulbasaur",
    hp=70,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Vine Whip", "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}], "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=1,
    rarity="common",
)

IVYSAUR = make_pokemon(
    name="Ivysaur",
    hp=100,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 1",
    evolves_from="Bulbasaur",
    attacks=[
        {"name": "Razor Leaf", "cost": [{"type": "G", "count": 1}, {"type": "C", "count": 1}], "damage": 50, "text": ""},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=2,
    rarity="uncommon",
)

VENUSAUR_EX = make_pokemon(
    name="Venusaur ex",
    hp=340,
    pokemon_type=PokemonType.GRASS.value,
    evolution_stage="Stage 2",
    evolves_from="Ivysaur",
    attacks=[
        {"name": "Razor Leaf", "cost": [{"type": "G", "count": 2}], "damage": 80, "text": ""},
        {"name": "Giant Bloom", "cost": [{"type": "G", "count": 2}, {"type": "C", "count": 2}],
         "damage": 260, "text": "Heal 30 damage from this Pokemon."},
    ],
    weakness_type=PokemonType.FIRE.value,
    retreat_cost=3,
    is_ex=True,
    rarity="rare",
)

# =============================================================================
# LIGHTNING POKEMON
# =============================================================================

PIKACHU = make_pokemon(
    name="Pikachu",
    hp=60,
    pokemon_type=PokemonType.LIGHTNING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Thunder Shock", "cost": [{"type": "L", "count": 1}], "damage": 20,
         "text": "Flip a coin. If heads, your opponent's Active Pokemon is now Paralyzed."},
    ],
    weakness_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="common",
)

RAICHU = make_pokemon(
    name="Raichu",
    hp=120,
    pokemon_type=PokemonType.LIGHTNING.value,
    evolution_stage="Stage 1",
    evolves_from="Pikachu",
    attacks=[
        {"name": "Thunderbolt", "cost": [{"type": "L", "count": 2}, {"type": "C", "count": 1}],
         "damage": 140, "text": "Discard all Energy from this Pokemon."},
    ],
    weakness_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="rare",
)

# =============================================================================
# PSYCHIC POKEMON
# =============================================================================

RALTS = make_pokemon(
    name="Ralts",
    hp=60,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Smack", "cost": [{"type": "C", "count": 1}], "damage": 10, "text": ""},
    ],
    weakness_type=PokemonType.DARKNESS.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="common",
)

KIRLIA = make_pokemon(
    name="Kirlia",
    hp=80,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 1",
    evolves_from="Ralts",
    attacks=[
        {"name": "Psychic Shot", "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 1}], "damage": 30, "text": ""},
    ],
    ability={"name": "Refinement", "text": "Once during your turn, you may discard a card from your hand. If you do, draw 2 cards.", "ability_type": "Ability"},
    weakness_type=PokemonType.DARKNESS.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="uncommon",
)

GARDEVOIR_EX = make_pokemon(
    name="Gardevoir ex",
    hp=310,
    pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Stage 2",
    evolves_from="Kirlia",
    attacks=[
        {"name": "Miracle Force", "cost": [{"type": "P", "count": 1}, {"type": "C", "count": 2}],
         "damage": 190, "text": ""},
    ],
    ability={"name": "Psychic Embrace", "text": "As often as you like during your turn, you may attach a Basic Psychic Energy from your discard pile to 1 of your Psychic Pokemon. If you attached Energy this way, put 2 damage counters on that Pokemon.", "ability_type": "Ability"},
    weakness_type=PokemonType.DARKNESS.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=2,
    is_ex=True,
    rarity="rare",
)

# =============================================================================
# FIGHTING POKEMON
# =============================================================================

RIOLU = make_pokemon(
    name="Riolu",
    hp=70,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Jab", "cost": [{"type": "F", "count": 1}], "damage": 30, "text": ""},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    rarity="common",
)

LUCARIO = make_pokemon(
    name="Lucario",
    hp=120,
    pokemon_type=PokemonType.FIGHTING.value,
    evolution_stage="Stage 1",
    evolves_from="Riolu",
    attacks=[
        {"name": "Aura Sphere", "cost": [{"type": "F", "count": 1}, {"type": "C", "count": 1}],
         "damage": 50, "text": "This attack also does 30 damage to 1 of your opponent's Benched Pokemon."},
    ],
    weakness_type=PokemonType.PSYCHIC.value,
    retreat_cost=1,
    rarity="rare",
)

# =============================================================================
# COLORLESS POKEMON
# =============================================================================

PIDGEY = make_pokemon(
    name="Pidgey",
    hp=60,
    pokemon_type=PokemonType.COLORLESS.value,
    evolution_stage="Basic",
    attacks=[
        {"name": "Gust", "cost": [{"type": "C", "count": 1}], "damage": 10, "text": ""},
    ],
    weakness_type=PokemonType.LIGHTNING.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    rarity="common",
)

PIDGEOT_EX = make_pokemon(
    name="Pidgeot ex",
    hp=280,
    pokemon_type=PokemonType.COLORLESS.value,
    evolution_stage="Stage 2",
    evolves_from="Pidgeotto",
    attacks=[
        {"name": "Blustery Wind", "cost": [{"type": "C", "count": 3}],
         "damage": 120, "text": "You may have your opponent switch their Active Pokemon with 1 of their Benched Pokemon."},
    ],
    ability={"name": "Quick Search", "text": "Once during your turn, you may search your deck for a card and put it into your hand. Then, shuffle your deck.", "ability_type": "Ability"},
    weakness_type=PokemonType.LIGHTNING.value,
    resistance_type=PokemonType.FIGHTING.value,
    retreat_cost=1,
    is_ex=True,
    rarity="rare",
)

# =============================================================================
# TRAINER CARDS
# =============================================================================

NEST_BALL = make_trainer_item(
    name="Nest Ball",
    text="Search your deck for a Basic Pokemon and put it onto your Bench. Then, shuffle your deck.",
    rarity="common",
)

ULTRA_BALL = make_trainer_item(
    name="Ultra Ball",
    text="Discard 2 cards from your hand. Search your deck for a Pokemon and put it into your hand. Then, shuffle your deck.",
    rarity="common",
)

RARE_CANDY = make_trainer_item(
    name="Rare Candy",
    text="Choose 1 of your Basic Pokemon in play. If you have a Stage 2 card in your hand that evolves from that Pokemon, put that card onto the Basic Pokemon to evolve it, skipping the Stage 1.",
    rarity="uncommon",
)

SWITCH = make_trainer_item(
    name="Switch",
    text="Switch your Active Pokemon with 1 of your Benched Pokemon.",
    rarity="common",
)

POTION = make_trainer_item(
    name="Potion",
    text="Heal 30 damage from 1 of your Pokemon.",
    rarity="common",
)

SUPER_ROD = make_trainer_item(
    name="Super Rod",
    text="Choose up to 3 in any combination of Pokemon and basic Energy cards from your discard pile and shuffle them into your deck.",
    rarity="uncommon",
)

BOSS_ORDERS = make_trainer_supporter(
    name="Boss's Orders",
    text="Switch in 1 of your opponent's Benched Pokemon to the Active Spot.",
    rarity="uncommon",
)

PROFESSOR_RESEARCH = make_trainer_supporter(
    name="Professor's Research",
    text="Discard your hand and draw 7 cards.",
    rarity="uncommon",
)

IONO = make_trainer_supporter(
    name="Iono",
    text="Each player shuffles their hand into their deck. Then, each player draws a card for each of their remaining Prize cards.",
    rarity="uncommon",
)

JUDGE = make_trainer_supporter(
    name="Judge",
    text="Each player shuffles their hand into their deck and draws 4 cards.",
    rarity="uncommon",
)

ARTAZON = make_trainer_stadium(
    name="Artazon",
    text="Once during each player's turn, that player may search their deck for a Basic Pokemon that doesn't have a Rule Box and put it onto their Bench. Then, that player shuffles their deck.",
    rarity="uncommon",
)

CHOICE_BELT = make_pokemon_tool(
    name="Choice Belt",
    text="The attacks of the Pokemon this card is attached to do 30 more damage to your opponent's Active Pokemon ex.",
    rarity="uncommon",
)

# =============================================================================
# ENERGY CARDS
# =============================================================================

FIRE_ENERGY = make_basic_energy("Fire Energy", PokemonType.FIRE.value)
WATER_ENERGY = make_basic_energy("Water Energy", PokemonType.WATER.value)
GRASS_ENERGY = make_basic_energy("Grass Energy", PokemonType.GRASS.value)
LIGHTNING_ENERGY = make_basic_energy("Lightning Energy", PokemonType.LIGHTNING.value)
PSYCHIC_ENERGY = make_basic_energy("Psychic Energy", PokemonType.PSYCHIC.value)
FIGHTING_ENERGY = make_basic_energy("Fighting Energy", PokemonType.FIGHTING.value)
DARKNESS_ENERGY = make_basic_energy("Darkness Energy", PokemonType.DARKNESS.value)
METAL_ENERGY = make_basic_energy("Metal Energy", PokemonType.METAL.value)

# =============================================================================
# CARD REGISTRY
# =============================================================================

SV_STARTER_CARDS = {
    # Fire
    "Charmander": CHARMANDER,
    "Charmeleon": CHARMELEON,
    "Charizard ex": CHARIZARD_EX,
    "Growlithe": GROWLITHE,
    "Arcanine": ARCANINE,
    # Water
    "Squirtle": SQUIRTLE,
    "Wartortle": WARTORTLE,
    "Blastoise ex": BLASTOISE_EX,
    "Lapras": LAPRAS,
    # Grass
    "Bulbasaur": BULBASAUR,
    "Ivysaur": IVYSAUR,
    "Venusaur ex": VENUSAUR_EX,
    # Lightning
    "Pikachu": PIKACHU,
    "Raichu": RAICHU,
    # Psychic
    "Ralts": RALTS,
    "Kirlia": KIRLIA,
    "Gardevoir ex": GARDEVOIR_EX,
    # Fighting
    "Riolu": RIOLU,
    "Lucario": LUCARIO,
    # Colorless
    "Pidgey": PIDGEY,
    "Pidgeot ex": PIDGEOT_EX,
    # Trainers
    "Nest Ball": NEST_BALL,
    "Ultra Ball": ULTRA_BALL,
    "Rare Candy": RARE_CANDY,
    "Switch": SWITCH,
    "Potion": POTION,
    "Super Rod": SUPER_ROD,
    "Boss's Orders": BOSS_ORDERS,
    "Professor's Research": PROFESSOR_RESEARCH,
    "Iono": IONO,
    "Judge": JUDGE,
    "Artazon": ARTAZON,
    "Choice Belt": CHOICE_BELT,
    # Energy
    "Fire Energy": FIRE_ENERGY,
    "Water Energy": WATER_ENERGY,
    "Grass Energy": GRASS_ENERGY,
    "Lightning Energy": LIGHTNING_ENERGY,
    "Psychic Energy": PSYCHIC_ENERGY,
    "Fighting Energy": FIGHTING_ENERGY,
    "Darkness Energy": DARKNESS_ENERGY,
    "Metal Energy": METAL_ENERGY,
}

# Pre-built decks for testing
def make_fire_deck() -> list:
    """30-card Fire deck for testing."""
    deck = []
    deck.extend([CHARMANDER] * 4)
    deck.extend([CHARMELEON] * 3)
    deck.extend([CHARIZARD_EX] * 2)
    deck.extend([GROWLITHE] * 2)
    deck.extend([ARCANINE] * 2)
    deck.extend([PIDGEY] * 2)
    deck.extend([NEST_BALL] * 2)
    deck.extend([ULTRA_BALL] * 1)
    deck.extend([SWITCH] * 1)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([FIRE_ENERGY] * 9)
    return deck  # 30 cards


def make_water_deck() -> list:
    """30-card Water deck for testing."""
    deck = []
    deck.extend([SQUIRTLE] * 4)
    deck.extend([WARTORTLE] * 3)
    deck.extend([BLASTOISE_EX] * 2)
    deck.extend([LAPRAS] * 2)
    deck.extend([PIDGEY] * 2)
    deck.extend([NEST_BALL] * 2)
    deck.extend([ULTRA_BALL] * 2)
    deck.extend([SWITCH] * 2)
    deck.extend([PROFESSOR_RESEARCH] * 2)
    deck.extend([WATER_ENERGY] * 9)
    return deck  # 30 cards
