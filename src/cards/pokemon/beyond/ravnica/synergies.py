"""Beyond Ravnica Pokemon synergy packages.

These packages are the Pokemon-engine equivalent of custom-set capability
packages: each focal ex should have a coherent same-guild shell that helps it
evolve, power its typed attacks, and make its payoff matter.
"""

from __future__ import annotations


BRV_SYNERGY_PACKAGES: dict[str, list[str]] = {
    "Isperia, Supreme Judge ex": [
        "Isperilet", "Isperatra", "Tomlet", "Tomik, Distinguished Advokist",
        "Lavinia of the Tenth", "Soulsworn Jury", "Augury Owl",
        "Prahv, Spires of Order", "Teferi, Hero of Dominaria",
        "Azorius Cluestone", "Azorius Blend Energy",
    ],
    "Aurelia, the Warleader ex": [
        "Aurelet", "Aurelin", "Feathlet", "Feather, the Redeemed",
        "Boros Reckoner", "Razia, Boros Archangel", "Fencing Ace",
        "Sunhome, Fortress of the Legion", "Gideon Blackblade",
        "Boros Cluestone", "Boros Blend Energy",
    ],
    "Lazav, Dimir Mastermind ex": [
        "Lazlet", "Lazander", "Mirklet", "Mirko Vosk, Mind Drinker",
        "Dimir Cutpurse", "Notion Thief", "Dinrova Horror",
        "Duskmantle, House of Shadow", "Etrata, the Silencer",
        "Dimir Cluestone", "Dimir Blend Energy",
    ],
    "Jarad, Golgari Lich Lord ex": [
        "Jarlet", "Jaradite", "Izolet", "Izoni, Thousand-Eyed",
        "Mazirek, Kraul Death Priest", "Golgari Rotwurm",
        "Erstwhile Trooper", "Korozda, the Tangle",
        "Vraska, Golgari Queen", "Golgari Cluestone",
        "Golgari Blend Energy",
    ],
    "Borborygmos ex": [
        "Borblet", "Borborgrew", "Ruriclet", "Ruric Thar, the Unbowed",
        "Burning-Tree Emissary", "Wood Elves", "Skarrgan Hellkite",
        "Skarrg, the Rage Pits", "Domri Rade", "Gruul Cluestone",
        "Gruul Blend Energy",
    ],
    "Niv-Mizzet, Parun ex": [
        "Nivlet", "Mizzling", "Meklet", "Melek, Izzet Paragon",
        "Goblin Electromancer", "Mercurial Mageling", "Crackling Drake",
        "Beamsplitter Mage", "Niv-Mizzet's Tower", "Ral, Storm Conduit",
        "Izzet Signet", "Izzet Blend Energy",
    ],
    "Teysa Karlov ex": [
        "Teyslet", "Teyserin", "Obzlet", "Obzedat, Ghost Council",
        "Karlov of the Ghost Council", "Tithe Drinker",
        "Treasury Thrull", "Orzhova, the Church of Deals",
        "Kaya, Ghost Assassin", "Orzhov Cluestone",
        "Orzhov Blend Energy",
    ],
    # Spice-pack v1 second Orzhov ex (Stage 2 ghost-council). Uses the
    # Karlov-of-the-Ghost-Council line rather than Teyslet → Teyserin →
    # Teysa Karlov, so its partner list is the Karlov half of Orzhov.
    "Obzedat, Ghost Council ex": [
        "Karlov of the Ghost Council", "Obzlet", "Obzedat, Ghost Council",
        "Tithe Drinker", "Treasury Thrull", "Orzhova, the Church of Deals",
        "Kaya, Ghost Assassin", "Sanguine Sacrament", "Orzhov Cluestone",
        "Orzhov Blend Energy",
    ],
    "Rakdos, Lord of Riots ex": [
        "Rakdomling", "Rakdomore", "Bloodlet", "Bloodletter of Aclazotz",
        "Rakdos Cackler", "Hellhole Flailer", "Carnival Hellsteed",
        "Spawn of Mayhem", "Rix Maadi, Dungeon Palace",
        "Tibalt, Rakish Instigator", "Rakdos Cluestone",
        "Rakdos Blend Energy",
    ],
    "Trostani, Selesnya's Voice ex": [
        "Trostling", "Trostavia", "Emmlet", "Emmara, Soul of the Accord",
        "Centaur Healer", "Conclave Cavalier", "Selesnya Evangel",
        "Saproling Sentinel", "Vitu-Ghazi, the City-Tree",
        "Captain Sisay", "Selesnya Cluestone",
        "Selesnya Blend Energy",
    ],
    "Vannifar, Evolved Enigma ex": [
        "Vannet", "Vannifuse", "Momlet", "Momir Vig, Simic Visionary",
        "Master Biomancer", "Coiling Oracle", "Cytoplast Manipulator",
        "Edric, Spymaster of Trest", "Novijen, Heart of Progress",
        "Prime Speaker Zegana", "Simic Cluestone",
        "Simic Blend Energy",
    ],
}


def brv_synergy_package_errors() -> list[str]:
    """Return typo and shape errors for BRV synergy packages."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS, GUILD_REGISTRIES

    card_to_guild = {
        card_name: guild
        for guild, registry in GUILD_REGISTRIES.items()
        for card_name in registry
    }
    errors: list[str] = []
    for focal, partners in BRV_SYNERGY_PACKAGES.items():
        if focal not in BEYOND_RAVNICA_CARDS:
            errors.append(f"{focal}: missing focal")
            continue
        if not 8 <= len(partners) <= 12:
            errors.append(f"{focal}: expected 8-12 partners, got {len(partners)}")
        focal_guild = card_to_guild.get(focal)
        for partner in partners:
            if partner == focal:
                errors.append(f"{focal}: self listed as partner")
            if partner not in BEYOND_RAVNICA_CARDS:
                errors.append(f"{focal}: missing partner {partner}")
                continue
            if card_to_guild.get(partner) != focal_guild:
                errors.append(
                    f"{focal}: partner {partner} is {card_to_guild.get(partner)}, "
                    f"expected {focal_guild}"
                )
    return errors


__all__ = ["BRV_SYNERGY_PACKAGES", "brv_synergy_package_errors"]
