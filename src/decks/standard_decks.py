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
    description="Dimir tempo: an evasive Faerie clock (Spellstutter, Vendilion, "
                "Mistbind) backed by hand disruption, premium -1/-1 removal, and "
                "card advantage. Flies over and grinds out — closes with Ashling "
                "and Oona, Queen of the Fae.",
    # POLISH-PASS REBUILD (2026-05-30): per user directive "build it better, mix
    # archetypes, put the good cards in." The old build was tiny faerie bodies +
    # Bitterblossom (perf 0, self-life-drain) + durdle (Lofty Dreams) with no
    # real clock → 0% winrate. v1 added threats but kept three cards the AI never
    # cast; v2 cut those (Vendilion Clique 0/6 — {1}{U}{U} ETB the AI won't value;
    # Cryptic Command 0/13 — {1}{U}{U}{U} triple-pip uncastable; Profane Command
    # 0/4 — X-cost) and doubled the proven casters: Dream Seizer (7/11, perf 35),
    # Mistbind Clique (perf 42), Wretched Banquet (6/6, 6 kills), Sygg River
    # Cutthroat (8/9 card advantage). 0% → 21% (v1) → targeting mid-pack (v2).
    mainboard=[
        # Evasive clock + tempo (24 creatures)
        DeckEntry("Spellstutter Sprite", 4, "FBM"),
        DeckEntry("Dream Seizer", 4, "FBM"),
        DeckEntry("Sygg, River Cutthroat", 3, "FBM"),
        DeckEntry("Mistbind Clique", 3, "FBM"),
        DeckEntry("Oona's Blackguard", 2, "FBM"),
        DeckEntry("Scion of Oona", 2, "FBM"),
        DeckEntry("Glen Elendra Archmage", 2, "FBM"),
        DeckEntry("Wydwen, the Biting Gale", 1, "FBM"),
        DeckEntry("Sower of Temptation", 1, "FBM"),
        DeckEntry("Ashling, the Extinguisher", 1, "FBM"),
        DeckEntry("Oona, Queen of the Fae", 1, "FBM"),
        # Disruption / removal / card flow (13 spells)
        DeckEntry("Wretched Banquet", 3, "FBM"),
        DeckEntry("Spell Snare", 2, "FBM"),
        DeckEntry("Peppersmoke", 2, "FBM"),
        DeckEntry("Blight Rot", 2, "FBM"),
        DeckEntry("Ponder", 2, "FBM"),
        DeckEntry("Broken Ambitions", 2, "FBM"),
        # Lands (23)
        DeckEntry("Island", 10, "FBM"),
        DeckEntry("Swamp", 11, "FBM"),
        DeckEntry("Evolving Wilds", 2, "FBM"),
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
    description="Azorius Merfolk: tap-down disruption (Wanderwine, Wanderbrine) "
                "and a Silvergill card-advantage engine into the Champions of "
                "the Shoal bomb, with premium exile removal (Crib Swap, Spiral "
                "into Solitude) keeping the board clear while you fly over.",
    # POLISH-PASS REBUILD (2026-05-30): per user directive "build it better,
    # mix archetypes, put the good cards in." Cut three dead cards the AI never
    # cast: Merrow Commerce ({1}{U} enchantment engine — AI-undervalued, 0/6),
    # Tributary Vaulter ({3}{W} — uncastable white pip in a U base, 0/10), and
    # Thoughtweft Gambit (6-mana situational, 0/-). Replaced with a 3rd Champions
    # of the Shoal (the deck's bomb), premium exile removal (Crib Swap, Spiral
    # into Solitude), and resilient bodies (Shore Lurker ward, Adept Watershaper,
    # Knight of Meadowgrain).
    mainboard=[
        # Card-advantage engine + tap-down disruption + bomb (28 creatures)
        DeckEntry("Silvergill Adept", 4, "FBM"),
        DeckEntry("Silvergill Mentor", 3, "FBM"),
        DeckEntry("Wanderwine Distracter", 3, "FBM"),
        DeckEntry("Champions of the Shoal", 3, "FBM"),
        DeckEntry("Wanderbrine Trapper", 2, "FBM"),
        DeckEntry("Deepway Navigator", 2, "FBM"),
        DeckEntry("Merrow Skyswimmer", 2, "FBM"),
        DeckEntry("Stratosoarer", 2, "FBM"),
        DeckEntry("Sygg, River Guide", 2, "FBM"),
        DeckEntry("Adept Watershaper", 2, "FBM"),
        DeckEntry("Knight of Meadowgrain", 2, "FBM"),
        DeckEntry("Shore Lurker", 1, "FBM"),
        # Removal / bounce / counters (9 spells)
        DeckEntry("Crib Swap", 2, "FBM"),
        DeckEntry("Spiral into Solitude", 2, "FBM"),
        DeckEntry("Run Away Together", 2, "FBM"),
        DeckEntry("Swat Away", 1, "FBM"),
        DeckEntry("Sygg's Command", 1, "FBM"),
        DeckEntry("Spell Snare", 1, "FBM"),
        # Lands (23)
        DeckEntry("Island", 11, "FBM"),
        DeckEntry("Plains", 6, "FBM"),
        DeckEntry("Hallowed Fountain", 4, "FBM"),
        DeckEntry("Evolving Wilds", 2, "FBM"),
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
    # POLISH-PASS REBUILD (2026-05-30): clean measurement unmasked this deck — it
    # read 75% on a tiny truncated sample but is 35% over a full one. Real bombs
    # (Reaper King 9/9 perf 135, Changeling Wayfinder 8/12) were dragged by ~10
    # cast-0 slots. Cut the dead weight (Boartusk Liege 0/10, Omni-Changeling 0/6,
    # Faewild Convocation 0/9, Cryptic Command 0/7 — uncastable triple-pip in 5c)
    # and reinvested in consistency: more ramp/fixing (Bloom Tender, Great Forest
    # Druid, Changeling Wayfinder) to actually cast the bombs, a 3rd Reaper King,
    # and more exile removal (Crib Swap, Unmake).
    mainboard=[
        # Fixing dorks / ramp (any color) — 14
        DeckEntry("Bloom Tender", 4, "FBM"),
        DeckEntry("Great Forest Druid", 4, "FBM"),
        DeckEntry("Firdoch Core", 2, "FBM"),
        DeckEntry("Changeling Wayfinder", 4, "FBM"),
        # Changeling bodies (every tribe) — 7
        DeckEntry("Mirror Entity", 2, "FBM"),
        DeckEntry("Chameleon Colossus", 2, "FBM"),
        DeckEntry("Graveshifter", 3, "FBM"),
        # Lords / bombs the changelings + dorks switch on — 9
        DeckEntry("Wilt-Leaf Liege", 2, "FBM"),
        DeckEntry("Ashenmoor Liege", 2, "FBM"),
        DeckEntry("Reaper King", 3, "FBM"),
        DeckEntry("Horde of Notions", 2, "FBM"),
        # 5-color payoffs / removal — 7
        DeckEntry("The Aurora Cycle", 1, "FBM"),
        DeckEntry("Crib Swap", 3, "FBM"),
        DeckEntry("Unmake", 3, "FBM"),
        # Lands (23 — heavy fixing)
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
