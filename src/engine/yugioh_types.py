"""
Yu-Gi-Oh! Type Definitions

Enums, constants, and data structures specific to the Yu-Gi-Oh! game mode.
"""

from enum import Enum, auto


class YGOAttribute(Enum):
    DARK = "DARK"
    LIGHT = "LIGHT"
    FIRE = "FIRE"
    WATER = "WATER"
    EARTH = "EARTH"
    WIND = "WIND"
    DIVINE = "DIVINE"


class YGOMonsterType(Enum):
    NORMAL = "Normal"
    EFFECT = "Effect"
    RITUAL = "Ritual"
    FUSION = "Fusion"
    SYNCHRO = "Synchro"
    XYZ = "Xyz"
    PENDULUM = "Pendulum"
    LINK = "Link"


class YGOSpellType(Enum):
    NORMAL = "Normal"
    QUICK_PLAY = "Quick-Play"
    CONTINUOUS = "Continuous"
    EQUIP = "Equip"
    FIELD = "Field"
    RITUAL = "Ritual"


class YGOTrapType(Enum):
    NORMAL = "Normal"
    CONTINUOUS = "Continuous"
    COUNTER = "Counter"


class YGOPosition(Enum):
    FACE_UP_ATK = "face_up_atk"
    FACE_UP_DEF = "face_up_def"
    FACE_DOWN_DEF = "face_down_def"


class SpellSpeed(Enum):
    SS1 = 1  # Normal Spells, Ignition Effects, Trigger Effects
    SS2 = 2  # Quick-Play Spells, Trap Cards, Quick Effects
    SS3 = 3  # Counter Traps


class YGOPhase(Enum):
    DRAW = "draw"
    STANDBY = "standby"
    MAIN1 = "main1"
    BATTLE_START = "battle_start"
    BATTLE_STEP = "battle_step"
    DAMAGE_STEP = "damage_step"
    DAMAGE_CALC = "damage_calc"
    BATTLE_END = "battle_end"
    MAIN2 = "main2"
    END = "end"


# Constants
STARTING_LP = 8000
MONSTER_ZONE_COUNT = 5
SPELL_TRAP_ZONE_COUNT = 5
MAX_HAND_SIZE = 6  # Discard to 6 during End Phase
STARTING_HAND_SIZE = 5
EXTRA_MONSTER_ZONE_COUNT = 2  # Shared between both players
