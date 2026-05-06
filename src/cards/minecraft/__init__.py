"""Minecraft TCG card pool — Alpha + Phyrexia Bedrock Edition + Box of Horrors."""

from pathlib import Path

from .alpha import (
    MINECRAFT_CARDS as ALPHA_CARDS,
    make_builder_deck,
    make_miner_deck,
    make_raider_deck,
)
from .phyrexia import PHYREXIA_CARDS
from .horror import HORROR_CARDS

# Aggregate set: alpha + phyrexia + box of horrors.
MINECRAFT_CARDS: dict = {**ALPHA_CARDS, **PHYREXIA_CARDS, **HORROR_CARDS}


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
BOX_OF_HORRORS_NAMES = [
    # Mana / draw structures
    "Cursed Bed", "Lectern of Whispers", "Sculk Catalyst", "Soul Forge", "Eldritch Altar",
    # Defensive grid
    "Fog Wall", "Soul Sand Trap", "Stalker's Den",
    # Mobs — cheap stalkers + spirits
    "Lost Soul", "Whispering Wraith", "Shadow Crawler", "Sleep-Stealer",
    "Endermite Cluster", "Phantom Wing", "Cave Crawler", "Ratman",
    # Mid-range threats
    "Wither Skeleton", "Sculk Stalker", "Elder Phantom", "The Old Watcher",
    # Bosses
    "Cave Dweller", "The Man From The Fog", "Wither Storm",
    # Removal / utility actions
    "Whispering Curse", "Drag to the Dark", "Wither Skull", "Goatman's Hex",
    # Gear
    "Eldritch Bow", "Wraith Cloak", "Reaper's Scythe",
]


def make_box_of_horrors_deck():
    return [MINECRAFT_CARDS[name] for name in BOX_OF_HORRORS_NAMES for _ in range(2)]


MINECRAFT_STARTER_DECKS = {
    "builder": make_builder_deck,
    "miner": make_miner_deck,
    "raider": make_raider_deck,
    "compleated_dominion": make_compleated_dominion_deck,
    "box_of_horrors": make_box_of_horrors_deck,
}


__all__ = [
    "MINECRAFT_CARDS",
    "ALPHA_CARDS",
    "PHYREXIA_CARDS",
    "HORROR_CARDS",
    "MINECRAFT_STARTER_DECKS",
    "make_builder_deck",
    "make_miner_deck",
    "make_raider_deck",
    "make_compleated_dominion_deck",
    "make_box_of_horrors_deck",
]
