from src.engine.game import make_minion
from src.cards.interceptor_helpers import make_static_pt_boost, other_friendly_minions, make_spell_damage_boost

# Token definitions - uncollectible minions summoned by other cards

# Leokk setup - grants +1 Attack to other friendly minions
def leokk_setup(obj, state):
    return make_static_pt_boost(obj, power_mod=1, toughness_mod=0,
                                affects_filter=other_friendly_minions(obj))

# Wrath of Air Totem setup - grants Spell Damage +1
def wrath_of_air_setup(obj, state):
    return [make_spell_damage_boost(obj, amount=1)]

# Basic tokens
SHEEP = make_minion(
    name="Sheep",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Beast"},
    text=""
)

TREANT = make_minion(
    name="Treant",
    attack=2,
    health=2,
    mana_cost="{0}",
    text=""
)

BOAR = make_minion(
    name="Boar",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Beast"},
    text=""
)

SILVER_HAND_RECRUIT = make_minion(
    name="Silver Hand Recruit",
    attack=1,
    health=1,
    mana_cost="{0}",
    text=""
)

IMP = make_minion(
    name="Imp",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Demon"},
    text=""
)

DAMAGED_GOLEM = make_minion(
    name="Damaged Golem",
    attack=2,
    health=1,
    mana_cost="{0}",
    subtypes={"Mech"},
    text=""
)

FROG = make_minion(
    name="Frog",
    attack=0,
    health=1,
    mana_cost="{0}",
    subtypes={"Beast"},
    keywords={"taunt"},
    text="Taunt"
)

SPIRIT_WOLF = make_minion(
    name="Spirit Wolf",
    attack=2,
    health=3,
    mana_cost="{0}",
    keywords={"taunt"},
    text="Taunt"
)

SNAKE = make_minion(
    name="Snake",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Beast"},
    text=""
)

HOUND = make_minion(
    name="Hound",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Beast"},
    keywords={"charge"},
    text="Charge"
)

WHELP = make_minion(
    name="Whelp",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Dragon"},
    text=""
)

VIOLET_APPRENTICE = make_minion(
    name="Violet Apprentice",
    attack=1,
    health=1,
    mana_cost="{0}",
    text=""
)

INFERNAL = make_minion(
    name="Infernal",
    attack=6,
    health=6,
    mana_cost="{0}",
    subtypes={"Demon"},
    text=""
)

SQUIRE = make_minion(
    name="Squire",
    attack=2,
    health=2,
    mana_cost="{0}",
    text=""
)

GNOLL = make_minion(
    name="Gnoll",
    attack=2,
    health=2,
    mana_cost="{0}",
    keywords={"taunt"},
    text="Taunt"
)

HYENA = make_minion(
    name="Hyena",
    attack=2,
    health=2,
    mana_cost="{0}",
    subtypes={"Beast"},
    text=""
)

# Animal Companion tokens
PANTHER = make_minion(
    name="Panther",
    attack=3,
    health=2,
    mana_cost="{0}",
    subtypes={"Beast"},
    text=""
)

MISHA = make_minion(
    name="Misha",
    attack=4,
    health=4,
    mana_cost="{0}",
    subtypes={"Beast"},
    keywords={"taunt"},
    text="Taunt"
)

LEOKK = make_minion(
    name="Leokk",
    attack=2,
    health=4,
    mana_cost="{0}",
    subtypes={"Beast"},
    text="Your other minions have +1 Attack.",
    setup_interceptors=leokk_setup
)

HUFFER = make_minion(
    name="Huffer",
    attack=4,
    health=2,
    mana_cost="{0}",
    subtypes={"Beast"},
    keywords={"charge"},
    text="Charge"
)

# Totemic Call tokens
def _healing_totem_setup(obj, state):
    from src.cards.hearthstone.hero_powers import healing_totem_setup
    return healing_totem_setup(obj, state)

HEALING_TOTEM = make_minion(
    name="Healing Totem",
    attack=0,
    health=2,
    mana_cost="{0}",
    subtypes={"Totem"},
    text="At the end of your turn, restore 1 Health to all friendly minions.",
    setup_interceptors=_healing_totem_setup
)

SEARING_TOTEM = make_minion(
    name="Searing Totem",
    attack=1,
    health=1,
    mana_cost="{0}",
    subtypes={"Totem"},
    text=""
)

STONECLAW_TOTEM = make_minion(
    name="Stoneclaw Totem",
    attack=0,
    health=2,
    mana_cost="{0}",
    subtypes={"Totem"},
    keywords={"taunt"},
    text="Taunt"
)

WRATH_OF_AIR_TOTEM = make_minion(
    name="Wrath of Air Totem",
    attack=0,
    health=2,
    mana_cost="{0}",
    subtypes={"Totem"},
    text="Spell Damage +1",
    setup_interceptors=wrath_of_air_setup
)

# Export all tokens
ALL_TOKENS = [
    SHEEP,
    TREANT,
    BOAR,
    SILVER_HAND_RECRUIT,
    IMP,
    DAMAGED_GOLEM,
    FROG,
    SPIRIT_WOLF,
    SNAKE,
    HOUND,
    WHELP,
    VIOLET_APPRENTICE,
    INFERNAL,
    SQUIRE,
    GNOLL,
    HYENA,
    PANTHER,
    MISHA,
    LEOKK,
    HUFFER,
    HEALING_TOTEM,
    SEARING_TOTEM,
    STONECLAW_TOTEM,
    WRATH_OF_AIR_TOTEM
]
