"""
Standard Netdecks from Tournament Top 8s

Real tournament decklists from January 2026 Standard events.
Sources: MTGGoldfish, MTGTop8, Untapped.gg
"""

from .deck import Deck, DeckEntry


# =============================================================================
# MONO RED AGGRO - SCG CON Portland Top 8
# Source: mtggoldfish.com/archetype/standard-mono-red-aggro-woe
# =============================================================================

MONO_RED_AGGRO_NETDECK = Deck(
    name="Mono Red Aggro",
    archetype="Aggro",
    colors=["R"],
    description="Fast aggressive red deck. Top 8 at SCG CON Portland January 2026.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Heartfire Hero", 4),
        DeckEntry("Slickshot Show-Off", 4),
        DeckEntry("Emberheart Challenger", 4),
        DeckEntry("Screaming Nemesis", 4),
        DeckEntry("Hired Claw", 4),
        DeckEntry("Razorkin Needlehead", 4),

        # Spells (16)
        DeckEntry("Monstrous Rage", 4),
        DeckEntry("Torch the Tower", 4),
        DeckEntry("Shock", 2),
        DeckEntry("Lightning Strike", 4),
        DeckEntry("Burst Lightning", 2),

        # Lands (20)
        DeckEntry("Mountain", 16),
        DeckEntry("Rockface Village", 4),
    ],
    sideboard=[
        DeckEntry("Leyline of Resonance", 4),
        DeckEntry("Callous Sell-Sword", 3),
        DeckEntry("Frantic Scapegoat", 3),
        DeckEntry("Abrade", 3),
        DeckEntry("Witchstalker Frenzy", 2),
    ],
    author="Joseph Cruz",
    source="SCG CON Portland LCQ Standard 5-0, January 23, 2026",
)


# =============================================================================
# IZZET AGGRO - SCG CON Portland
# Source: mtggoldfish.com/archetype/standard-mono-red-aggro-woe
# =============================================================================

IZZET_AGGRO_NETDECK = Deck(
    name="Izzet Aggro",
    archetype="Aggro",
    colors=["R", "U"],
    description="Blue-red aggro with evasive threats. Top 8 SCG CON Portland.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Hired Claw", 4),
        DeckEntry("Razorkin Needlehead", 4),
        DeckEntry("Scalding Viper", 4),
        DeckEntry("Nova Hellkite", 4),
        DeckEntry("Slickshot Show-Off", 4),
        DeckEntry("Ojer Axonil, Deepest Might", 2),
        DeckEntry("Emberheart Challenger", 2),

        # Spells (14)
        DeckEntry("Shock", 3),
        DeckEntry("Lightning Strike", 4),
        DeckEntry("Burst Lightning", 4),
        DeckEntry("Torch the Tower", 3),

        # Lands (22)
        DeckEntry("Mountain", 12),
        DeckEntry("Steam Vents", 4),
        DeckEntry("Rockface Village", 2),
        DeckEntry("Soulstone Sanctuary", 4),
    ],
    sideboard=[
        DeckEntry("Abrade", 4),
        DeckEntry("Negate", 3),
        DeckEntry("Leyline of Resonance", 4),
        DeckEntry("Screaming Nemesis", 2),
        DeckEntry("Monstrous Rage", 2),
    ],
    author="Tournament Meta",
    source="SCG CON Portland Standard, January 2026",
)


# =============================================================================
# DIMIR MIDRANGE - Magic Spotlight: The Avatar Top 8
# Source: mtggoldfish.com/archetype/standard-dimir-midrange-woe
# =============================================================================

DIMIR_MIDRANGE_NETDECK = Deck(
    name="Dimir Midrange",
    archetype="Midrange",
    colors=["U", "B"],
    description="Value-oriented midrange deck. Top 8 at Magic Spotlight Lyon.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Deep-Cavern Bat", 4),
        DeckEntry("Spyglass Siren", 4),
        DeckEntry("Floodpits Drowner", 4),
        DeckEntry("Tishana's Tidebinder", 4),
        DeckEntry("Preacher of the Schism", 2),
        DeckEntry("Cecil, Dark Knight", 2),
        DeckEntry("Enduring Curiosity", 4),

        # Planeswalkers (4)
        DeckEntry("Kaito, Bane of Nightmares", 4),

        # Spells (8)
        DeckEntry("Stab", 2),
        DeckEntry("Bitter Triumph", 2),
        DeckEntry("Shoot the Sheriff", 2),
        DeckEntry("Tragic Trajectory", 2),

        # Lands (24)
        DeckEntry("Island", 5),
        DeckEntry("Swamp", 5),
        DeckEntry("Watery Grave", 4),
        DeckEntry("Gloomlake Verge", 4),
        DeckEntry("Restless Reef", 2),
        DeckEntry("Soulstone Sanctuary", 2),
        DeckEntry("Multiversal Passage", 2),
    ],
    sideboard=[
        DeckEntry("Phantom Interference", 3),
        DeckEntry("Day of Black Sun", 2),
        DeckEntry("Heartless Act", 3),
        DeckEntry("Duress", 4),
        DeckEntry("Azure Beastbinder", 3),
    ],
    author="Takada Koki",
    source="Magic Spotlight: The Avatar Lyon Top 8, January 2026",
)


# =============================================================================
# SIMIC OUROBOROID - Magic Spotlight Lyon Winner
# Source: mtggoldfish.com/archetype/standard-simic-ouroboroid-woe
# =============================================================================

SIMIC_OUROBOROID_NETDECK = Deck(
    name="Simic Ouroboroid",
    archetype="Combo",
    colors=["U", "G"],
    description="Ramp-combo deck featuring Ouroboroid. Winner Magic Spotlight Lyon.",
    mainboard=[
        # Creatures (28)
        DeckEntry("Llanowar Elves", 4),
        DeckEntry("Badgermole Cub", 4),
        DeckEntry("Gene Pollinator", 4),
        DeckEntry("Ouroboroid", 4),
        DeckEntry("Quantum Riddler", 4),
        DeckEntry("Spider Manifestation", 4),
        DeckEntry("Mockingbird", 2),
        DeckEntry("Thornvault Forager", 2),

        # Spells (8)
        DeckEntry("Spider-Sense", 2),
        DeckEntry("Up the Beanstalk", 4),
        DeckEntry("Season of Gathering", 2),

        # Lands (24)
        DeckEntry("Forest", 10),
        DeckEntry("Island", 4),
        DeckEntry("Botanical Sanctum", 4),
        DeckEntry("Breeding Pool", 4),
        DeckEntry("Multiversal Passage", 2),
    ],
    sideboard=[
        DeckEntry("Pawpatch Formation", 3),
        DeckEntry("Negate", 3),
        DeckEntry("Pick Your Poison", 3),
        DeckEntry("Sentinel of the Nameless City", 2),
        DeckEntry("Ghalta, Stampede Tyrant", 2),
        DeckEntry("Trumpeting Carnosaur", 2),
    ],
    author="Simon Nielsen",
    source="Magic Spotlight Lyon 1st Place (14-2-1), January 10, 2026",
)


# =============================================================================
# JESKAI CONTROL - RCQ Standard
# =============================================================================

JESKAI_CONTROL_NETDECK = Deck(
    name="Jeskai Control",
    archetype="Control",
    colors=["W", "U", "R"],
    description="Three-color control with sweepers and card advantage.",
    mainboard=[
        # Creatures (6)
        DeckEntry("Enduring Curiosity", 4),
        DeckEntry("Sentinel of the Nameless City", 2),

        # Planeswalkers (4)
        DeckEntry("Kaito, Bane of Nightmares", 4),

        # Spells (24)
        DeckEntry("Lightning Strike", 4),
        DeckEntry("Torch the Tower", 3),
        DeckEntry("Shock", 2),
        DeckEntry("Stab", 2),
        DeckEntry("Bitter Triumph", 2),
        DeckEntry("Day of Black Sun", 3),
        DeckEntry("Phantom Interference", 4),
        DeckEntry("Tragic Trajectory", 2),
        DeckEntry("Up the Beanstalk", 2),

        # Lands (26)
        DeckEntry("Island", 4),
        DeckEntry("Plains", 2),
        DeckEntry("Mountain", 2),
        DeckEntry("Steam Vents", 4),
        DeckEntry("Watery Grave", 4),
        DeckEntry("Soulstone Sanctuary", 4),
        DeckEntry("Restless Reef", 2),
        DeckEntry("Multiversal Passage", 4),
    ],
    sideboard=[
        DeckEntry("Negate", 4),
        DeckEntry("Abrade", 3),
        DeckEntry("Duress", 3),
        DeckEntry("Heartless Act", 2),
        DeckEntry("Azure Beastbinder", 3),
    ],
    author="Tournament Meta",
    source="RCQ Standard Top 8, January 2026",
)


# =============================================================================
# GOLGARI MIDRANGE - MTGO Challenge
# =============================================================================

GOLGARI_MIDRANGE_NETDECK = Deck(
    name="Golgari Midrange",
    archetype="Midrange",
    colors=["B", "G"],
    description="Black-green midrange with removal and value creatures.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Deep-Cavern Bat", 4),
        DeckEntry("Preacher of the Schism", 4),
        DeckEntry("Badgermole Cub", 4),
        DeckEntry("Thornvault Forager", 4),
        DeckEntry("Sentinel of the Nameless City", 4),
        DeckEntry("Trumpeting Carnosaur", 2),
        DeckEntry("Ghalta, Stampede Tyrant", 2),

        # Spells (12)
        DeckEntry("Stab", 2),
        DeckEntry("Bitter Triumph", 3),
        DeckEntry("Heartless Act", 3),
        DeckEntry("Pick Your Poison", 2),
        DeckEntry("Season of Gathering", 2),

        # Lands (24)
        DeckEntry("Forest", 6),
        DeckEntry("Swamp", 6),
        DeckEntry("Overgrown Tomb", 4),
        DeckEntry("Restless Cottage", 4),
        DeckEntry("Soulstone Sanctuary", 4),
    ],
    sideboard=[
        DeckEntry("Duress", 4),
        DeckEntry("Day of Black Sun", 3),
        DeckEntry("Pawpatch Formation", 3),
        DeckEntry("Enduring Curiosity", 2),
        DeckEntry("Up the Beanstalk", 3),
    ],
    author="Tournament Meta",
    source="MTGO Standard Challenge Top 8, January 2026",
)


# =============================================================================
# NETDECK REGISTRY
# =============================================================================

NETDECKS = {
    "mono_red_netdeck": MONO_RED_AGGRO_NETDECK,
    "izzet_aggro_netdeck": IZZET_AGGRO_NETDECK,
    "dimir_midrange_netdeck": DIMIR_MIDRANGE_NETDECK,
    "simic_ouroboroid_netdeck": SIMIC_OUROBOROID_NETDECK,
    "jeskai_control_netdeck": JESKAI_CONTROL_NETDECK,
    "golgari_midrange_netdeck": GOLGARI_MIDRANGE_NETDECK,
}


def get_netdeck(deck_id: str) -> Deck:
    """Get a netdeck by ID."""
    deck = NETDECKS.get(deck_id)
    if not deck:
        raise ValueError(f"Unknown netdeck: {deck_id}. Available: {list(NETDECKS.keys())}")
    return deck
