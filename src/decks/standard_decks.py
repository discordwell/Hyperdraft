"""
Standard Netdecks for Hyperdraft

Current Standard meta decks built from Edge of Eternities, Avatar: The Last Airbender,
Lorwyn Eclipsed, and other legal sets.

These decks are balanced with proper mana bases (~24 lands) and competitive card choices.
"""

import random
from .deck import Deck, DeckEntry


# =============================================================================
# MONO-RED AGGRO - Fast, aggressive red deck
# =============================================================================

MONO_RED_AGGRO = Deck(
    name="Mono-Red Aggro",
    archetype="Aggro",
    colors=["R"],
    description="Fast aggressive deck that aims to deal 20 damage as quickly as possible.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Chrono-Berserker", 4, "TMH"),
        DeckEntry("Time Rager", 4, "TMH"),
        DeckEntry("Accelerated Striker", 4, "TMH"),
        DeckEntry("Accelerated Scout", 4, "TMH"),
        DeckEntry("Rift Elemental", 4, "TMH"),
        DeckEntry("Temporal Phoenix", 2, "TMH"),
        DeckEntry("Accelerated Dragon", 2, "TMH"),

        # Spells (12)
        DeckEntry("Lightning Bolt", 4),
        DeckEntry("Accelerate", 4, "TMH"),
        DeckEntry("Temporal Storm", 2, "TMH"),
        DeckEntry("Chrono-Fury", 2, "TMH"),

        # Lands (24)
        DeckEntry("Mountain", 20),
        DeckEntry("Accelerated Peak", 4, "TMH"),
    ],
    sideboard=[
        DeckEntry("Shattered Timeline", 3, "TMH"),
        DeckEntry("Chaos Rift", 2, "TMH"),
        DeckEntry("Echo Flames", 4, "TMH"),
        DeckEntry("Blaze Through Time", 3, "TMH"),
        DeckEntry("Temporal Inferno", 3, "TMH"),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# MONO-GREEN RAMP - Big creatures and mana acceleration
# =============================================================================

MONO_GREEN_RAMP = Deck(
    name="Mono-Green Ramp",
    archetype="Midrange",
    colors=["G"],
    description="Ramp into big threats with mana acceleration and overwhelm with large creatures.",
    mainboard=[
        # Creatures (26)
        DeckEntry("Seedling of Ages", 4, "TMH"),
        DeckEntry("Elder Chronomancer", 4, "TMH"),
        DeckEntry("Chronicle Beast", 4, "TMH"),
        DeckEntry("Echo of the Wild", 4, "TMH"),
        DeckEntry("Ageless Oak", 3, "TMH"),
        DeckEntry("Primordial Titan", 3, "TMH"),
        DeckEntry("Chronicle Wolf", 2, "TMH"),
        DeckEntry("Timeless Elk", 2, "TMH"),

        # Spells (10)
        DeckEntry("Temporal Growth", 4, "TMH"),
        DeckEntry("Temporal Bloom", 4, "TMH"),
        DeckEntry("Nature Reclaims", 2, "TMH"),

        # Lands (24)
        DeckEntry("Forest", 20),
        DeckEntry("Timeless Forest", 4, "TMH"),
    ],
    sideboard=[
        DeckEntry("Cycle of Eternity", 3, "TMH"),
        DeckEntry("Primal Growth", 2, "TMH"),
        DeckEntry("Ageless Wurm", 2, "TMH"),
        DeckEntry("Timeless Vigor", 4, "TMH"),
        DeckEntry("Grove Tender", 4, "TMH"),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# DIMIR CONTROL - Blue/Black control with card advantage
# =============================================================================

DIMIR_CONTROL = Deck(
    name="Dimir Control",
    archetype="Control",
    colors=["U", "B"],
    description="Control the game with removal, counterspells, and card advantage.",
    mainboard=[
        # Creatures (8)
        DeckEntry("Temporal Vampire", 4, "TMH"),
        DeckEntry("Chrono-Reaper", 2, "TMH"),
        DeckEntry("Entropy Wraith", 2, "TMH"),

        # Spells (28)
        DeckEntry("Temporal Loop", 4, "TMH"),
        DeckEntry("Rewind Moment", 4, "TMH"),
        DeckEntry("Fate Unwritten", 4, "TMH"),
        DeckEntry("Stolen Moment", 4, "TMH"),
        DeckEntry("Timeless Decay", 3, "TMH"),
        DeckEntry("Grave Timeline", 3, "TMH"),
        DeckEntry("Glimpse Beyond Time", 4, "TMH"),
        DeckEntry("Temporal Torment", 2, "TMH"),

        # Lands (24)
        DeckEntry("Island", 10),
        DeckEntry("Swamp", 10),
        DeckEntry("Suspended Island", 2, "TMH"),
        DeckEntry("Entropy Pool", 2, "TMH"),
    ],
    sideboard=[
        DeckEntry("Echo of Death", 3, "TMH"),
        DeckEntry("Entropy Walker", 2, "TMH"),
        DeckEntry("Decay of Ages", 2, "TMH"),
        DeckEntry("Temporal Drain", 4, "TMH"),
        DeckEntry("Entropy Shade", 4, "TMH"),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# BOROS AGGRO - Red/White aggressive deck
# =============================================================================

BOROS_AGGRO = Deck(
    name="Boros Aggro",
    archetype="Aggro",
    colors=["R", "W"],
    description="Fast aggressive deck combining red's burn with white's efficient creatures.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Chrono-Paladin", 4, "TMH"),
        DeckEntry("Temporal Guardian", 4, "TMH"),
        DeckEntry("Accelerated Striker", 4, "TMH"),
        DeckEntry("Timeless Sentinel", 4, "TMH"),
        DeckEntry("Keeper of Moments", 4, "TMH"),
        DeckEntry("Eternity Warden", 4, "TMH"),

        # Spells (12)
        DeckEntry("Lightning Bolt", 4),
        DeckEntry("Moment of Clarity", 4, "TMH"),
        DeckEntry("Dawn of New Era", 2, "TMH"),
        DeckEntry("Preserved Memory", 2, "TMH"),

        # Lands (24)
        DeckEntry("Plains", 10),
        DeckEntry("Mountain", 10),
        DeckEntry("Accelerated Plains", 2, "TMH"),
        DeckEntry("Accelerated Peak", 2, "TMH"),
    ],
    sideboard=[
        DeckEntry("Chronicle of Ages", 3, "TMH"),
        DeckEntry("Temporal Sanctuary", 2, "TMH"),
        DeckEntry("Shattered Timeline", 2, "TMH"),
        DeckEntry("Echo Flames", 4, "TMH"),
        DeckEntry("Eternal Blessing", 4, "TMH"),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# SIMIC TEMPO - Blue/Green tempo with efficient threats
# =============================================================================

SIMIC_TEMPO = Deck(
    name="Simic Tempo",
    archetype="Tempo",
    colors=["U", "G"],
    description="Efficient creatures backed by counterspells and card draw.",
    mainboard=[
        # Creatures (22)
        DeckEntry("Echo of Tomorrow", 4, "TMH"),
        DeckEntry("Paradox Entity", 4, "TMH"),
        DeckEntry("Chronicle Beast", 4, "TMH"),
        DeckEntry("Echo of the Wild", 4, "TMH"),
        DeckEntry("Chronomancer Supreme", 2, "TMH"),
        DeckEntry("Time Weaver", 4, "TMH"),

        # Spells (14)
        DeckEntry("Temporal Loop", 4, "TMH"),
        DeckEntry("Rewind Moment", 4, "TMH"),
        DeckEntry("Temporal Growth", 4, "TMH"),
        DeckEntry("Nature Reclaims", 2, "TMH"),

        # Lands (24)
        DeckEntry("Island", 10),
        DeckEntry("Forest", 10),
        DeckEntry("Suspended Island", 2, "TMH"),
        DeckEntry("Timeless Forest", 2, "TMH"),
    ],
    sideboard=[
        DeckEntry("Glimpse Beyond Time", 3, "TMH"),
        DeckEntry("Cycle of Eternity", 2, "TMH"),
        DeckEntry("Primordial Titan", 2, "TMH"),
        DeckEntry("Chrono-Shift", 4, "TMH"),
        DeckEntry("Ageless Oak", 4, "TMH"),
    ],
    author="Meta",
    source="Standard Meta January 2026",
)


# =============================================================================
# AVATAR AIRBENDER - Bant (WUG) Avatar-themed deck
# =============================================================================

AVATAR_AIRBENDER = Deck(
    name="Avatar Airbender",
    archetype="Midrange",
    colors=["W", "U", "G"],
    description="Avatar-themed deck featuring Aang and airbending synergies.",
    mainboard=[
        # Creatures (24)
        DeckEntry("Aang, Swift Savior", 4, "TLAC"),
        DeckEntry("Appa, Steadfast Guardian", 4, "TLAC"),
        DeckEntry("Airbender Initiate", 4, "TLAC"),
        DeckEntry("Air Acolyte", 4, "TLAC"),
        DeckEntry("Badgermole Cub", 4, "TLAC"),
        DeckEntry("Keeper of Moments", 4, "TMH"),

        # Spells (12)
        DeckEntry("Airbender Ascension", 4, "TLAC"),
        DeckEntry("Airbender's Flight", 4, "TLAC"),
        DeckEntry("Moment of Clarity", 4, "TMH"),

        # Lands (24)
        DeckEntry("Plains", 8),
        DeckEntry("Island", 8),
        DeckEntry("Forest", 8),
    ],
    sideboard=[
        DeckEntry("Air Temple", 2, "TLAC"),
        DeckEntry("Airbending Scroll", 4, "TLAC"),
        DeckEntry("Avatar State Fury", 2, "TLAC"),
        DeckEntry("Preserved Memory", 4, "TMH"),
        DeckEntry("Nature Reclaims", 3, "TMH"),
    ],
    author="Meta",
    source="Avatar: The Last Airbender Set",
)


# =============================================================================
# FIRE NATION AGGRO - Red/Black Aggro Avatar deck
# =============================================================================

FIRE_NATION_AGGRO = Deck(
    name="Fire Nation Aggro",
    archetype="Aggro",
    colors=["R", "B"],
    description="Aggressive Fire Nation deck with burn and disruption.",
    mainboard=[
        # Creatures (20)
        DeckEntry("Azula, Cunning Usurper", 4, "TLAC"),
        DeckEntry("Chrono-Berserker", 4, "TMH"),
        DeckEntry("Time Rager", 4, "TMH"),
        DeckEntry("Entropy Walker", 4, "TMH"),
        DeckEntry("Accelerated Striker", 4, "TMH"),

        # Spells (16)
        DeckEntry("Lightning Bolt", 4),
        DeckEntry("Accelerate", 4, "TMH"),
        DeckEntry("Fate Unwritten", 4, "TMH"),
        DeckEntry("Stolen Moment", 4, "TMH"),

        # Lands (24)
        DeckEntry("Mountain", 12),
        DeckEntry("Swamp", 10),
        DeckEntry("Entropy Marsh", 2, "TMH"),
    ],
    sideboard=[
        DeckEntry("Agni Kai", 4, "TLAC"),
        DeckEntry("Chrono-Fury", 4, "TMH"),
        DeckEntry("Echo of Death", 3, "TMH"),
        DeckEntry("Temporal Torment", 2, "TMH"),
        DeckEntry("Shattered Timeline", 2, "TMH"),
    ],
    author="Meta",
    source="Avatar: The Last Airbender Set",
)


# =============================================================================
# LORWYN FAERIES - Blue/Black Faerie tribal
# =============================================================================

LORWYN_FAERIES = Deck(
    name="Lorwyn Faeries",
    archetype="Tempo",
    colors=["U", "B"],
    description="Classic Faerie tribal with flash creatures and countermagic.",
    mainboard=[
        # Creatures (20)
        DeckEntry("Glen Elendra Guardian", 4),
        DeckEntry("Flitterwing Nuisance", 4),
        DeckEntry("Glamermite", 4),
        DeckEntry("Dream Seizer", 4),
        DeckEntry("Gravelgill Scoundrel", 4),

        # Spells (16)
        DeckEntry("Temporal Loop", 4, "TMH"),
        DeckEntry("Rewind Moment", 4, "TMH"),
        DeckEntry("Blight Rot", 4),
        DeckEntry("Midnight Tilling", 4),

        # Lands (24)
        DeckEntry("Island", 12),
        DeckEntry("Swamp", 12),
    ],
    sideboard=[
        DeckEntry("Darkness Descends", 4),
        DeckEntry("Auntie's Sentence", 4),
        DeckEntry("Bloodline Bidding", 3),
        DeckEntry("Fate Unwritten", 4, "TMH"),
    ],
    author="Meta",
    source="Lorwyn Eclipsed Set",
)


# =============================================================================
# ============  FAE BUT MID (FBM) — pinnacle archetype decks  ==================
# Custom fae-tribal set in src/cards/custom/fae_but_mid.py. These six decks
# give the set its first designed metagame (previously only auto-greedy decks
# existed, so most cards never got cast). One deck per tribal pillar; every
# card name is a key in FAE_BUT_MID_CARDS. Strategy doc:
# docs/strategy/fae_but_mid.md
# =============================================================================

# ---- 1. FAERIE TEMPO (UB) ----------------------------------------------------
# Bitterblossom + flyers + flash counters. Spellstutter/Mistbind/Oona scale
# with Faerie count; tap-down + countermagic protect a small evasive clock.
FBM_FAERIE_TEMPO = Deck(
    name="FBM Faerie Tempo",
    archetype="Tempo",
    colors=["U", "B"],
    description="Dimir Faeries: Bitterblossom tokens, flash flyers, and "
                "countermagic that scales with your Faerie count. Tempo out a "
                "small evasive clock behind Spellstutter Sprite and Cryptic Command.",
    mainboard=[
        # Token / clock engines
        DeckEntry("Bitterblossom", 3, "FBM"),
        DeckEntry("Oona's Blackguard", 2, "FBM"),
        # 1-2 drop flyers + flash counters
        DeckEntry("Spellstutter Sprite", 4, "FBM"),
        DeckEntry("Scion of Oona", 3, "FBM"),
        DeckEntry("Unwelcome Sprite", 2, "FBM"),
        DeckEntry("Wydwen, the Biting Gale", 2, "FBM"),
        DeckEntry("Shimmercreep", 2, "FBM"),
        # Disruptive bodies
        DeckEntry("Glen Elendra Archmage", 2, "FBM"),
        DeckEntry("Mistbind Clique", 3, "FBM"),
        DeckEntry("Sower of Temptation", 2, "FBM"),
        # Top-end
        DeckEntry("Oona, Queen of the Fae", 2, "FBM"),
        # Spells (removal / counters / card flow)
        DeckEntry("Peppersmoke", 2, "FBM"),
        DeckEntry("Spell Snare", 1, "FBM"),
        DeckEntry("Moonshadow", 2, "FBM"),
        DeckEntry("Lofty Dreams", 2, "FBM"),
        DeckEntry("Cryptic Command", 2, "FBM"),
        DeckEntry("Profane Command", 1, "FBM"),
        # Lands (23)
        DeckEntry("Island", 9, "FBM"),
        DeckEntry("Swamp", 10, "FBM"),
        DeckEntry("Evolving Wilds", 4, "FBM"),
    ],
    sideboard=[],
    author="Deckbuilder",
    source="Fae but Mid pinnacle decks",
    game="mtg",
)


# ---- 2. ELF RAMP / TRIBAL (GW) ----------------------------------------------
# Mana dorks -> Imperious Perfect & token spells -> wide Elf board that lords
# pump. Elvish Harbinger / Bloom Tender fix the white splash for Morcant +
# Rhys (token doubler). Jagged-Scar Archers & Moon-Vigil scale with the swarm.
FBM_ELF_RAMP = Deck(
    name="FBM Elf Ramp",
    archetype="Midrange",
    colors=["G", "W"],
    description="Golgari-free Selesnya Elves: accelerate on mana dorks into "
                "Imperious Perfect and token sorceries, then overrun with lords "
                "(High Perfect Morcant, Rhys) and count-scaling payoffs.",
    mainboard=[
        # Mana dorks / fixers
        DeckEntry("Heritage Druid", 3, "FBM"),
        DeckEntry("Bloom Tender", 3, "FBM"),
        DeckEntry("Elvish Harbinger", 3, "FBM"),
        DeckEntry("Lys Alana Dignitary", 2, "FBM"),
        # Lords / anthems
        DeckEntry("Imperious Perfect", 4, "FBM"),
        DeckEntry("High Perfect Morcant", 2, "FBM"),
        DeckEntry("Rhys the Redeemed", 2, "FBM"),
        # Payoffs that scale with the swarm
        DeckEntry("Jagged-Scar Archers", 2, "FBM"),
        DeckEntry("Moon-Vigil Adherents", 1, "FBM"),
        DeckEntry("Sun-Dappled Celebrant", 1, "FBM"),
        DeckEntry("Masked Admirers", 2, "FBM"),
        # Top-end bomb + value
        DeckEntry("Champions of the Perfect", 2, "FBM"),
        DeckEntry("Wilt-Leaf Liege", 2, "FBM"),
        # Token spells / removal
        DeckEntry("Hunting Triad", 2, "FBM"),
        DeckEntry("Gilt-Leaf Ambush", 2, "FBM"),
        DeckEntry("Scarblade's Malice", 1, "FBM"),
        DeckEntry("Blossoming Defense", 2, "FBM"),
        # Lands (24)
        DeckEntry("Forest", 13, "FBM"),
        DeckEntry("Plains", 4, "FBM"),
        DeckEntry("Temple Garden", 3, "FBM"),
        DeckEntry("Evolving Wilds", 4, "FBM"),
    ],
    sideboard=[],
    author="Deckbuilder",
    source="Fae but Mid pinnacle decks",
    game="mtg",
)


# ---- 3. KITHKIN GO-WIDE (GW) ------------------------------------------------
# Cheapest creatures in the set + token-makers + stacking +1/+1 lords. Spectral
# Procession & Clachan Festival flood the board; Kinbinding / Mistmeadow Council
# / Gaddock Teeg turn the swarm lethal. Catharsis is a board reset that refills
# YOUR side with Kithkin tokens.
FBM_KITHKIN_WIDE = Deck(
    name="FBM Kithkin Go-Wide",
    archetype="Aggro",
    colors=["G", "W"],
    description="Selesnya Kithkin tokens: dump a wide board of one-drops and "
                "token-makers, then stack anthems (Mistmeadow Council, Gaddock "
                "Teeg, Champion of the Clachan) and alpha strike.",
    mainboard=[
        # One-drops / counter-payoffs
        DeckEntry("Kinsbaile Aspirant", 4, "FBM"),
        DeckEntry("Goldmeadow Nomad", 1, "FBM"),
        DeckEntry("Figure of Destiny", 2, "FBM"),
        # Token-makers
        DeckEntry("Kithkeeper", 3, "FBM"),
        DeckEntry("Brigid, Clachan's Heart", 3, "FBM"),
        DeckEntry("Kinsbaile Borderguard", 2, "FBM"),
        DeckEntry("Cloudgoat Ranger", 2, "FBM"),
        # Lords / anthems
        DeckEntry("Gaddock Teeg", 2, "FBM"),
        DeckEntry("Mistmeadow Council", 3, "FBM"),
        DeckEntry("Champion of the Clachan", 2, "FBM"),
        DeckEntry("Thoughtweft Lieutenant", 2, "FBM"),
        # Go-wide spells / payoffs
        DeckEntry("Spectral Procession", 3, "FBM"),
        DeckEntry("Clachan Festival", 2, "FBM"),
        DeckEntry("Kinbinding", 2, "FBM"),
        DeckEntry("Gallant Fowlknight", 1, "FBM"),
        # Removal / reset
        DeckEntry("Spiral into Solitude", 2, "FBM"),
        DeckEntry("Catharsis", 2, "FBM"),
        # Lands (22 — low curve)
        DeckEntry("Plains", 12, "FBM"),
        DeckEntry("Forest", 6, "FBM"),
        DeckEntry("Temple Garden", 4, "FBM"),
    ],
    sideboard=[],
    author="Deckbuilder",
    source="Fae but Mid pinnacle decks",
    game="mtg",
)


# ---- 4. MERFOLK TEMPO (WU) --------------------------------------------------
# Tap-matters Merfolk. Merrow Commerce untaps the team each end step so tap
# abilities (Wanderbrine, Champions of the Shoal) fire every turn; evasion +
# bounce close behind a card-advantage engine (Silvergill Adept, Merrow
# Skyswimmer).
FBM_MERFOLK_TEMPO = Deck(
    name="FBM Merfolk Tempo",
    archetype="Tempo",
    colors=["W", "U"],
    description="Azorius Merfolk: tap your opponents down and keep your own "
                "team untapped with Merrow Commerce, grind card advantage off "
                "Silvergill Adept / Merrow Skyswimmer, and fly over.",
    mainboard=[
        # Engine
        DeckEntry("Merrow Commerce", 2, "FBM"),
        DeckEntry("Silvergill Adept", 4, "FBM"),
        DeckEntry("Silvergill Mentor", 3, "FBM"),
        # Tap-down / disruption Merfolk
        DeckEntry("Wanderwine Distracter", 3, "FBM"),
        DeckEntry("Wanderbrine Trapper", 2, "FBM"),
        DeckEntry("Tributary Vaulter", 3, "FBM"),
        DeckEntry("Champions of the Shoal", 2, "FBM"),
        # Evasion / card flow
        DeckEntry("Deepway Navigator", 2, "FBM"),
        DeckEntry("Merrow Skyswimmer", 2, "FBM"),
        DeckEntry("Sygg, River Guide", 2, "FBM"),
        DeckEntry("Stratosoarer", 2, "FBM"),
        # Spells (bounce / counters / removal)
        DeckEntry("Swat Away", 2, "FBM"),
        DeckEntry("Run Away Together", 2, "FBM"),
        DeckEntry("Sygg's Command", 2, "FBM"),
        DeckEntry("Spell Snare", 2, "FBM"),
        DeckEntry("Thoughtweft Gambit", 2, "FBM"),
        # Lands (23)
        DeckEntry("Island", 11, "FBM"),
        DeckEntry("Plains", 5, "FBM"),
        DeckEntry("Hallowed Fountain", 3, "FBM"),
        DeckEntry("Evolving Wilds", 4, "FBM"),
    ],
    sideboard=[],
    author="Deckbuilder",
    source="Fae but Mid pinnacle decks",
    game="mtg",
)


# ---- 5. GOBLIN AGGRO (RB) ---------------------------------------------------
# Lowest curve in the set + reach. Token-makers feed sacrifice outlets
# (Sting-Slinger, Murderous Redcap, Hovel Hurler, Boggart Cursecrafter) so the
# deck pushes the last points of damage even through a stall. Grub drains on
# every Goblin death.
FBM_GOBLIN_AGGRO = Deck(
    name="FBM Goblin Aggro",
    archetype="Aggro",
    colors=["B", "R"],
    description="Rakdos Goblins: flood cheap bodies and tokens, then convert "
                "them to reach with Sting-Slinger, Murderous Redcap, Hovel "
                "Hurler and Grub's death drain. Burn finishes.",
    mainboard=[
        # One-drops
        DeckEntry("Sting-Slinger", 4, "FBM"),
        DeckEntry("Knucklebone Witch", 2, "FBM"),
        DeckEntry("Tattermunge Maniac", 3, "FBM"),
        # Token-makers / aggro bodies
        DeckEntry("Elder Auntie", 3, "FBM"),
        DeckEntry("Sourbread Auntie", 3, "FBM"),
        DeckEntry("Boggart Cursecrafter", 2, "FBM"),
        DeckEntry("Hovel Hurler", 3, "FBM"),
        # Reach / payoffs
        DeckEntry("Murderous Redcap", 3, "FBM"),
        DeckEntry("Grub, Storied Matriarch", 2, "FBM"),
        DeckEntry("Boggart Ram-Gang", 1, "FBM"),
        DeckEntry("Wort, the Raidmother", 2, "FBM"),
        # Burn / removal
        DeckEntry("Tarfire", 3, "FBM"),
        DeckEntry("Lash Out", 2, "FBM"),
        DeckEntry("Lasting Tarfire", 2, "FBM"),
        DeckEntry("Fodder Launch", 2, "FBM"),
        DeckEntry("Impolite Entrance", 1, "FBM"),
        # Lands (22)
        DeckEntry("Mountain", 9, "FBM"),
        DeckEntry("Swamp", 9, "FBM"),
        DeckEntry("Blood Crypt", 4, "FBM"),
    ],
    sideboard=[],
    author="Deckbuilder",
    source="Fae but Mid pinnacle decks",
    game="mtg",
)


# ---- 6. FIVE-TRIBE CHANGELING GOOD-STUFF (WUBRG) ----------------------------
# Changelings are every tribe, so they turn on every lord at once: the
# wedge/allied Lieges (each pumps two colors), Reaper King, and the 5-color
# Aurora payoffs. Heaviest fixing in the format (any-color dorks + shocks +
# Eclipsed Realms). Slower, but every threat is a multi-format payoff.
FBM_CHANGELING_5C = Deck(
    name="FBM Five-Tribe Changeling",
    archetype="Midrange",
    colors=["W", "U", "B", "R", "G"],
    description="Five-color Changeling good-stuff: shapeshifters that are every "
                "tribe at once flip on every Liege, Reaper King and the Aurora "
                "payoffs simultaneously. Fix hard, then deploy undercosted lords.",
    mainboard=[
        # Fixing dorks / ramp (any color)
        DeckEntry("Bloom Tender", 3, "FBM"),
        DeckEntry("Great Forest Druid", 3, "FBM"),
        DeckEntry("Firdoch Core", 2, "FBM"),
        DeckEntry("Changeling Wayfinder", 3, "FBM"),
        # Changeling bodies (every tribe)
        DeckEntry("Mirror Entity", 2, "FBM"),
        DeckEntry("Chameleon Colossus", 2, "FBM"),
        DeckEntry("Omni-Changeling", 2, "FBM"),
        DeckEntry("Graveshifter", 2, "FBM"),
        # Lords / payoffs that the changelings + dorks switch on
        DeckEntry("Wilt-Leaf Liege", 2, "FBM"),
        DeckEntry("Ashenmoor Liege", 2, "FBM"),
        DeckEntry("Boartusk Liege", 2, "FBM"),
        DeckEntry("Reaper King", 2, "FBM"),
        DeckEntry("Horde of Notions", 2, "FBM"),
        DeckEntry("Faewild Convocation", 2, "FBM"),
        # 5-color payoffs / removal
        DeckEntry("The Aurora Cycle", 1, "FBM"),
        DeckEntry("Cryptic Command", 1, "FBM"),
        DeckEntry("Crib Swap", 2, "FBM"),
        DeckEntry("Unmake", 2, "FBM"),
        # Lands (25 — heavy fixing)
        DeckEntry("Forest", 3, "FBM"),
        DeckEntry("Island", 2, "FBM"),
        DeckEntry("Plains", 2, "FBM"),
        DeckEntry("Swamp", 2, "FBM"),
        DeckEntry("Mountain", 1, "FBM"),
        DeckEntry("Temple Garden", 1, "FBM"),
        DeckEntry("Hallowed Fountain", 1, "FBM"),
        DeckEntry("Overgrown Tomb", 1, "FBM"),
        DeckEntry("Steam Vents", 1, "FBM"),
        DeckEntry("Blood Crypt", 1, "FBM"),
        DeckEntry("Eclipsed Realms", 2, "FBM"),
        DeckEntry("Evolving Wilds", 6, "FBM"),
    ],
    sideboard=[],
    author="Deckbuilder",
    source="Fae but Mid pinnacle decks",
    game="mtg",
)


# =============================================================================
# DECK REGISTRY
# =============================================================================

STANDARD_DECKS = {
    "fbm_faerie_tempo": FBM_FAERIE_TEMPO,
    "fbm_elf_ramp": FBM_ELF_RAMP,
    "fbm_kithkin_wide": FBM_KITHKIN_WIDE,
    "fbm_merfolk_tempo": FBM_MERFOLK_TEMPO,
    "fbm_goblin_aggro": FBM_GOBLIN_AGGRO,
    "fbm_changeling_5c": FBM_CHANGELING_5C,
    "mono_red_aggro": MONO_RED_AGGRO,
    "mono_green_ramp": MONO_GREEN_RAMP,
    "dimir_control": DIMIR_CONTROL,
    "boros_aggro": BOROS_AGGRO,
    "simic_tempo": SIMIC_TEMPO,
    "avatar_airbender": AVATAR_AIRBENDER,
    "fire_nation_aggro": FIRE_NATION_AGGRO,
    "lorwyn_faeries": LORWYN_FAERIES,
}


def get_deck(deck_id: str) -> Deck:
    """Get a deck by ID."""
    deck = STANDARD_DECKS.get(deck_id)
    if not deck:
        raise ValueError(f"Unknown deck: {deck_id}. Available: {list(STANDARD_DECKS.keys())}")
    return deck


def get_random_deck() -> Deck:
    """Get a random deck from the registry."""
    return random.choice(list(STANDARD_DECKS.values()))


def get_decks_by_archetype(archetype: str) -> list[Deck]:
    """Get all decks of a specific archetype."""
    return [d for d in STANDARD_DECKS.values() if d.archetype == archetype]


def get_decks_by_color(color: str) -> list[Deck]:
    """Get all decks containing a specific color."""
    return [d for d in STANDARD_DECKS.values() if color in d.colors]
