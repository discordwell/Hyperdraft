"""
Synergy packages for PKH spice cards.

Each entry maps a spice (focal) card name to a list of card names that
turn the focal from "vanilla" into "build-around-broken" when played in
the same deck. The capability-test harness
(`scripts/play/capability_test.py`) uses these to construct synergy decks
and measure each focal card's actual impact when its support is in place.

Convention:
- Partner names must already exist in POKEMON_HORIZONS_CARDS.
- 8-12 partners per focal — enough to fill ~24 of 36 spell slots when
  combined with 4 copies of the focal.
- Partners should plausibly enable the focal's text. For now (v1, before
  the Phase-2 redesign), some focals don't have a clean synergy package
  because their text is standalone — those packages list "tempo curve"
  partners (cheap creatures + burn) so the deck at least casts the focal.
"""

# Each list = the cards that should ride with the focal in its synergy deck.
PKH_SYNERGY_PACKAGES: dict[str, list[str]] = {
    # Charizard, Mega Evolved (current text: ETB damage divided + pump
    # activated). Synergy: cheap red creatures so the board is wide enough
    # for ETB to find targets, plus burn spells that finish what it weakens.
    "Charizard, Mega Evolved": [
        "Vulpix", "Charmander", "Cyndaquil", "Litten",
        "Ponyta", "Slugma", "Numel", "Torchic",
        "Flamethrower", "Fire Blast", "Overheat",
    ],

    # Moltres, Phoenix Reborn (dies → return to hand). Synergy: cheap
    # bodies that trade often (giving Moltres death triggers on opponent
    # boards), plus haste so re-cast Moltres attacks immediately.
    "Moltres, Phoenix Reborn": [
        "Slugma", "Numel", "Torchic", "Cyndaquil",
        "Charmander", "Vulpix", "Ponyta", "Flareon",
        "Flamethrower", "Fire Blast",
    ],

    # Pikachu, Thunder Champion (combat damage to player → draw).
    # Synergy: haste / unblockable enablers + cheap creatures that share
    # combat presence.
    "Pikachu, Thunder Champion": [
        "Voltorb", "Electrode", "Electabuzz", "Mankey",
        "Charmander", "Vulpix", "Ponyta", "Slugma",
        "Wild Charge", "Brick Break", "Close Combat",
    ],

    # Eevee, Evolution Vessel (ETB tutor for MV ≤ 3 creature). Synergy:
    # the cheap MV ≤ 3 creature pool it pulls from. The bigger the pool,
    # the more reliably Eevee finds something good.
    "Eevee, Evolution Vessel": [
        "Charmander", "Vulpix", "Cyndaquil", "Litten",
        "Torchic", "Numel", "Slugma", "Ponyta",
        "Mankey", "Voltorb", "Magikarp",
    ],

    # Master Ball ({2},{T}: tutor any creature). Synergy: a strong target
    # to find — top-end finishers worth tutoring for.
    "Master Ball": [
        "Charizard, Mega Evolved", "Moltres, Phoenix Reborn",
        "Magmortar", "Blaziken", "Infernape", "Rapidash",
        "Magmar", "Hitmonchan", "Lucario", "Primeape",
    ],

    # Volcanic Mantle (equip {1} → +3/+1 + haste + trample). Synergy:
    # cheap evasive / hasty creatures to equip turn 2-3.
    "Volcanic Mantle": [
        "Mankey", "Voltorb", "Charmander", "Vulpix",
        "Cyndaquil", "Litten", "Torchic", "Numel",
        "Magikarp", "Ponyta",
    ],

    # Reshiram, Truth Aspect ({4}{R}{R}, {2} less if 4+ creatures in GY).
    # Synergy: cheap creatures that die quickly (trade off) so Reshiram's
    # cost reduction kicks in. Eruption (X-spell) and burn finish the job.
    "Reshiram, Truth Aspect": [
        "Slugma", "Numel", "Torchic", "Charmander",
        "Vulpix", "Cyndaquil", "Magikarp", "Mankey",
        "Eruption", "Fire Blast",
    ],

    # Hyper Beam (sorcery, 6 damage). Synergy: setup that softens the
    # board so 6 dmg closes — cheap creatures pinging early + burn pile.
    "Hyper Beam": [
        "Charmander", "Vulpix", "Slugma", "Numel",
        "Torchic", "Cyndaquil", "Ponyta",
        "Flamethrower", "Fire Blast", "Overheat", "Wild Charge",
    ],
}


__all__ = ["PKH_SYNERGY_PACKAGES"]
