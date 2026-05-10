"""Minecraft TCG card pool — Alpha + expansions."""

from pathlib import Path

from .alpha import (
    MINECRAFT_CARDS as ALPHA_CARDS,
    make_builder_deck,
    make_miner_deck,
    make_raider_deck,
)
from .phyrexia import PHYREXIA_CARDS
from .horror import HORROR_CARDS
from .tricky_trials import MCT_CARDS

# Aggregate set: alpha + Phyrexia + Box of Horrors + Tricky Trials.
MINECRAFT_CARDS: dict = {**ALPHA_CARDS, **PHYREXIA_CARDS, **HORROR_CARDS, **MCT_CARDS}


# ---------------------------------------------------------------------------
# Image-URL auto-wire
# ---------------------------------------------------------------------------

_CARD_ART_DIR = Path(__file__).resolve().parents[3] / "assets" / "card_art" / "minecraft"


def _slug(name: str) -> str:
    return (
        name.lower()
        .replace("'", "")
        .replace(",", "")
        .replace(":", "")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace("!", "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
        .strip("_")
    )


def _wire_image_urls() -> None:
    """For every card whose PNG exists on disk, set its image_url to the
    corresponding /api/card-art/minecraft/ path. Idempotent — preserves
    pre-set URLs."""
    if not _CARD_ART_DIR.exists():
        return
    for name, card in MINECRAFT_CARDS.items():
        png = _CARD_ART_DIR / f"{_slug(name)}.png"
        if png.exists() and not getattr(card, "image_url", None):
            card.image_url = f"/api/card-art/minecraft/{_slug(name)}.png"


_wire_image_urls()


# ---------------------------------------------------------------------------
# Starter decks
# ---------------------------------------------------------------------------

# Compleated Dominion: showcases Phyrexian mechanics with workers + bombs.
COMPLEATED_DOMINION_NAMES = [
    # Workers + ramp foundation
    "Bed", "Crafting Table", "Furnace", "Mycosynth Garden", "Oil Refinery",
    "Phyrexian Arena", "Compleated Steve", "Compleated Villager", "Allay Courier", "Panda Forager",
    # Mid-curve aggressive Phyrexian threats
    "Phyrexian Walker", "Carnophage", "Phyrexian Crusader", "Sangromancer", "Glissa, the Traitor",
    # Removal + sweepers
    "Disfigure", "Putrefy", "Sickening Dreams",
    # Card advantage + drain
    "Compulsive Research", "Sheoldred's Restoration", "Yawgmoth's Mandate",
    # World-ending bombs
    "Sheoldred, the Whispering One", "Vorinclex, Voice of Hunger", "Atraxa, Grand Unifier",
    "Herobrine, World's Eye",
]


def make_compleated_dominion_deck():
    return [MINECRAFT_CARDS[name] for name in COMPLEATED_DOMINION_NAMES for _ in range(2)]


# Box of Horrors: leans on Horror tribal, mind erosion, and cursed gear.
# 25 distinct × 2 = 50 cards (standard format). Cut Elder Phantom (needs D1),
# Lectern of Whispers (redundant draw), Fog Wall (pure defense), Phantom Wing
# (low synergy), Soul Sand Trap (slowest trap) to reach count.
BOX_OF_HORRORS_NAMES = [
    # Workers + redstone bootstrap
    "Strip Mine", "Allay Courier", "Steve's Helper", "Villager Mason",
    # Draw / engine structures
    "Cursed Bed", "Sculk Catalyst", "Soul Forge", "Eldritch Altar",
    # Defensive grid
    "Stalker's Den",
    # Mobs — cheap stalkers + spirits
    "Lost Soul", "Whispering Wraith", "Shadow Crawler", "Sleep-Stealer",
    "Endermite Cluster", "Cave Crawler", "Ratman",
    # Mid-range threats
    "Wither Skeleton", "Sculk Stalker", "The Old Watcher",
    # Boss
    "Cave Dweller",
    # Removal / utility actions
    "Whispering Curse", "Drag to the Dark", "Wither Skull", "Goatman's Hex",
    # Gear
    "Eldritch Bow",
]


def make_box_of_horrors_deck():
    return [MINECRAFT_CARDS[name] for name in BOX_OF_HORRORS_NAMES for _ in range(2)]


TRIAL_CHAMBERS_NAMES = [
    "Bed", "Cherry Grove", "Copper Mine", "Trial Supply Cache", "Trial Spawner",
    "Ominous Trial Spawner", "Vault of Rewards", "Trial Barrier", "Mud Brick Wall", "Copper Grate",
    "Trail Mapper", "Copper Miner", "Breeze", "Bogged Archer", "Vault Sentinel",
    "Breeze Caller", "Ominous Captain", "Chamber Champion", "Open the Vault", "Ominous Bottle",
    "Trial Cleave", "Spawn Wave", "Chamber Rewards", "Vault Jackpot", "Breeze Charge",
]


def make_trial_chambers_deck():
    return [MINECRAFT_CARDS[name] for name in TRIAL_CHAMBERS_NAMES for _ in range(2)]


TAMED_TRAILS_NAMES = [
    "Bed", "Cherry Grove", "Village Granary", "Map Room", "Best Friends Forever",
    "Trail Mapper", "Bamboo Farmer", "Armadillo Friend", "Wolf Companion", "Cat Familiar",
    "Camel Caravan", "Sniffer Calf", "Frog Choir", "Fox Courier", "Llama Trader",
    "Bee Swarm", "Panda Protector", "Pack Leader", "Stable Master", "Sniffer Elder",
    "Tame Wolf", "Brush the Trail", "Parrot Scout", "Pack Howl", "Friendship Feast",
]


def make_tamed_trails_deck():
    return [MINECRAFT_CARDS[name] for name in TAMED_TRAILS_NAMES for _ in range(2)]


COPPER_PULSE_NAMES = [
    "Bed", "Copper Mine", "Amethyst Vein", "Deep Ore Vein", "Geode Observatory",
    "Copper Grate", "Waxed Copper Door", "Copper Miner", "Geode Prospector", "Deep Delver",
    "Copper Bulb", "Crafter Array", "Observer Chain", "Auto Smelter", "Redstone Clock",
    "Copper Golem", "Redstone Engineer", "Piston Drone", "Repeater Mage", "Comparator Savant",
    "Redstone Titan", "Redstone Spark", "Overclock", "Automate Mine", "Lightning Trident",
]


def make_copper_pulse_deck():
    return [MINECRAFT_CARDS[name] for name in COPPER_PULSE_NAMES for _ in range(2)]


DEEP_DARK_ECHO_NAMES = [
    "Bed", "Tuff Quarry", "Amethyst Vein", "Deep Ore Vein", "Sculk Veil",
    "Geode Prospector", "Deep Delver", "Sculk Sensor", "Calibrated Sensor", "Sculk Library",
    "Echo Shrieker", "Sculk Wisp", "Sculk Crawler", "Echo Bat", "Deep Dark Stalker",
    "Shrieker Disciple", "Sonic Boomer", "Echo Warden", "Sonic Boom", "Sculk Bloom",
    "Echo Shards", "Darkness Falls", "Ancient Loot", "Wardens Warning", "Echo Compass",
]


def make_deep_dark_echo_deck():
    return [MINECRAFT_CARDS[name] for name in DEEP_DARK_ECHO_NAMES for _ in range(2)]


BASTION_RAID_NAMES = [
    "Bed", "Copper Mine", "Bastion Bridge", "Piglin Stash", "Bastion Barricade",
    "Piglin Scout", "Bastion Brute", "Gold Hoarder", "Hoglin Charger", "Strider Rider",
    "Magma Runt", "Nether Raider", "Bastion Captain", "Ghast Bombardier", "Wither Raider",
    "Piglin Warboss", "Netherite Juggernaut", "Raid Banner", "Barter for Blades", "Bastion Ambush",
    "Lava Bucket", "Raid the Bed", "Nether Shortcut", "Piglin Crossbow", "Netherite Axe",
]


def make_bastion_raid_deck():
    return [MINECRAFT_CARDS[name] for name in BASTION_RAID_NAMES for _ in range(2)]


END_VOYAGE_NAMES = [
    "Bed", "Ancient Dig Site", "Deep Ore Vein", "End Stone Shield", "Trail Mapper",
    "Ancient Miner", "End Gateway", "Chorus Grove", "Purpur Tower", "End Ship",
    "Dragon Perch", "Ancient Portal Lab", "Enderling", "Chorus Walker", "End Scout",
    "Shulker Guard", "End Crystal Adept", "Purpur Knight", "Dragon Herald", "Void Voyager",
    "Chorus Dragon", "Ender Sovereign", "Locate Stronghold", "Dragon Breath", "Ender Bow",
]


def make_end_voyage_deck():
    return [MINECRAFT_CARDS[name] for name in END_VOYAGE_NAMES for _ in range(2)]


ENDER_WARBOSS_MIDRANGE_NAMES = [
    "Bed", "Steve's Helper", "Allay Courier", "Copper Miner", "Deep Delver",
    "Crafting Table", "Furnace", "Copper Mine", "Ancient Dig Site", "Deep Ore Vein",
    "Chorus Grove", "End Ship", "Dragon Perch", "Strip Mine", "Find Diamonds",
    "Phyrexian Vault", "Yawgmoth's Mandate", "Locate Stronghold", "Disfigure", "Putrefy",
    "Piglin Warboss", "Ender Sovereign", "Chorus Dragon", "Dragon Herald", "Ender Bow",
]


def make_ender_warboss_midrange_deck():
    return [MINECRAFT_CARDS[name] for name in ENDER_WARBOSS_MIDRANGE_NAMES for _ in range(2)]


MINECRAFT_STARTER_DECKS = {
    "builder": make_builder_deck,
    "miner": make_miner_deck,
    "raider": make_raider_deck,
    "compleated_dominion": make_compleated_dominion_deck,
    "box_of_horrors": make_box_of_horrors_deck,
    "trial_chambers": make_trial_chambers_deck,
    "tamed_trails": make_tamed_trails_deck,
    "copper_pulse": make_copper_pulse_deck,
    "deep_dark_echo": make_deep_dark_echo_deck,
    "bastion_raid": make_bastion_raid_deck,
    "end_voyage": make_end_voyage_deck,
    "ender_warboss_midrange": make_ender_warboss_midrange_deck,
}


__all__ = [
    "MINECRAFT_CARDS",
    "ALPHA_CARDS",
    "PHYREXIA_CARDS",
    "HORROR_CARDS",
    "MCT_CARDS",
    "MINECRAFT_STARTER_DECKS",
    "make_builder_deck",
    "make_miner_deck",
    "make_raider_deck",
    "make_compleated_dominion_deck",
    "make_box_of_horrors_deck",
    "make_trial_chambers_deck",
    "make_tamed_trails_deck",
    "make_copper_pulse_deck",
    "make_deep_dark_echo_deck",
    "make_bastion_raid_deck",
    "make_end_voyage_deck",
    "make_ender_warboss_midrange_deck",
]
