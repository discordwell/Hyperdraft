"""AI strategy hints for Beyond Kamigawa Yu-Gi-Oh! archetypes."""

from __future__ import annotations

from copy import deepcopy


KAMIGAWA_STRATEGIES: dict[str, dict] = {
    "samurai": {
        "name": "Eiganjo Samurai",
        "archetype": "Beatdown / Swarm",
        "description": "Curve out with Samurai bodies, then leverage lords and combat tricks.",
        "summon_priority": [
            "General Fumiko",
            "Konda's Banner-Bearer",
            "Hand of Honor",
            "Hand of Cruelty",
            "Sokenzan Renegade",
            "Isamaru, Hound of Konda",
            "Konda, Lord of Eiganjo",
        ],
        "set_priority": [
            "Devoted Retainer",
            "Imperial Recovery Unit",
        ],
    },
    "ninja": {
        "name": "Umezawa Ninja",
        "archetype": "Tempo / Control",
        "description": "Establish small Ninjas, then use removal and high-impact Ninjas to steal tempo.",
        "summon_priority": [
            "Ninja of the Deep Hours",
            "Mistblade Shinobi",
            "Ninja Grandmaster Sasuke",
            "Walker of Secret Ways",
            "Iga-Style Cooper",
            "Satoru Umezawa",
            "Throat Slitter",
            "Higure, the Still Wind",
        ],
        "set_priority": [
            "Higure's Apprentice",
        ],
    },
    "spirit_dragons": {
        "name": "Spirit Dragons of the Five Nights",
        "archetype": "Dragon Tribute / Recursion",
        "description": "Use low-level Spirits as tribute fodder and recursion fuel for the five Dragon bosses.",
        "summon_priority": [
            "Kami of Hopeful Strength",
            "Hikari, Twilight Guardian",
            "Daimyo's Spirit Steed",
            "Yosei, the Morning Star",
            "Kokusho, the Evening Star",
            "Keiga, the Tide Star",
            "Ryusei, the Falling Star",
        ],
        "set_priority": [
            "Petalmane Baku",
            "Hana Kami",
            "Kami of False Hope",
        ],
    },
    "moonfolk": {
        "name": "Soratami Moonfolk",
        "archetype": "Control",
        "description": "Trade resources with bounce, removal, and draw until a Moonfolk finisher takes over.",
        "summon_priority": [
            "Soratami Savant",
            "Soratami Mirror-Mage",
            "Reflect Lord of the Soratami",
            "Meloku the Clouded Mirror",
            "Misdirection Master",
        ],
        "set_priority": [
            "Soratami Mirror-Guard",
            "Eye of Nowhere Diviner",
        ],
    },
    "modified": {
        "name": "Modified Cyber-Kamigawa",
        "archetype": "Equipment Beatdown",
        "description": "Land efficient artifact bodies, then convert Equip density into large attacks.",
        "summon_priority": [
            "Disciple of Atsushi",
            "Kaito, Cunning Infiltrator",
            "Reckoner Bankbuster",
            "Voltron Construct",
            "The Wandering Emperor, Modified Variant",
            "Saheeli, Filigree Master",
        ],
        "set_priority": [
            "Cyber-Spirit Conduit",
            "Boseiju Mechanical Bridgekeeper",
        ],
    },
}


def kamigawa_strategy(archetype: str) -> dict:
    """Return a copy of the AI strategy hints for one Kamigawa archetype."""
    try:
        return deepcopy(KAMIGAWA_STRATEGIES[archetype])
    except KeyError as exc:
        available = ", ".join(sorted(KAMIGAWA_STRATEGIES))
        raise ValueError(f"Unknown Beyond Kamigawa strategy '{archetype}'. Available: {available}") from exc
