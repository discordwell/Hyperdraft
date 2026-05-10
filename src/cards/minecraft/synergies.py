"""
Hand-curated synergy packages for Minecraft TCG spice cards.

Each focal card maps to a list of partner card names from MINECRAFT_CARDS.
The capability test harness builds a 50-card deck from focal + partners +
filler from the BUILDER pool. A card "passes" if its capability score
(cast/game * win-correlation) >= 0.30 in this deck against the Raider
baseline.

Notes on Minecraft's economy:
  - 1 mining/turn (avatar action) is the baseline rate.
  - Premium materials (redstone, diamond) need explicit ramp.
  - Strip Mine (1 stone -> 1 iron + 1 redstone) is the only cheap entry
    into redstone; almost every spice deck runs it.
  - Find Diamonds (2 iron -> 1 diamond) is the diamond entry.

Spice candidates (build-around mythics; targeted for redesign):

  - Ender Dragon          Diamond-investment payoff
  - Elder Guardian        Worker mining payoff
  - Wither                Hostile tribal anchor
  - Iron Golem            Worker mining payoff (alt angle)
  - Ravager               Block-destruction siege engine
  - Blaze                 Redstone-fueled chip (control: not redesigned)
"""

MC_SYNERGY_PACKAGES: dict[str, list[str]] = {
    # Diamond ramp shell — needs Diamond Pickaxe + End Portal + Find Diamonds
    # to reach 3 diamonds reliably. Ender Dragon then deals 2x diamond-cost
    # permanents to opponent (Pickaxe + EPF + Enchanting Table + Diamond
    # Sword + Diamond Armor all qualify).
    "Ender Dragon": [
        "Diamond Pickaxe", "Find Diamonds", "End Portal Frame",
        "Enchanting Table", "Strip Mine", "Furnace",
        "Steve's Helper", "Villager Mason", "Crafting Table", "Bed",
    ],

    # Worker tribal — every Worker fueling Elder Guardian's mining-pump.
    # Bone Meal lets a Worker mine twice. Beacon adds a +1 ATK static.
    "Elder Guardian": [
        "Steve's Helper", "Alex's Scout", "Villager Mason",
        "Allay Courier", "Panda Forager", "Bone Meal",
        "Strip Mine", "Beacon", "Crafting Table", "Bed",
    ],

    # Hostile flood — many cheap hostiles, then Wither's ETB
    # = damage equal to hostile count.
    "Wither": [
        "Zombie", "Skeleton Archer", "Spider", "Creeper",
        "Piglin Raider", "Strip Mine", "Iron Sword",
        "Crafting Table", "Furnace", "Bed",
    ],

    # Worker ramp into Iron Golem ETB (deal damage = worker count).
    # Strip Mine is the redstone bridge.
    "Iron Golem": [
        "Steve's Helper", "Alex's Scout", "Villager Mason",
        "Allay Courier", "Panda Forager", "Strip Mine",
        "Bone Meal", "Wolf Pack", "Crafting Table", "Bed",
    ],

    # Block destruction — Siege keyword + TNT Blast turn block cracks
    # into +1/+1 counter chains on Ravager.
    "Ravager": [
        "TNT Blast", "Strip Mine", "Iron Sword", "Crossbow",
        "Bow", "Steve's Helper", "Alex's Scout",
        "Crafting Table", "Furnace", "Bed",
    ],

    # Redstone chain — Blaze's chip damage scales with hostile aggression
    # off a steady Redstone supply.
    "Blaze": [
        "Allay Courier", "Strip Mine", "Redstone Lamp",
        "Nether Expedition", "Iron Sword", "Bow",
        "Steve's Helper", "Furnace", "Crafting Table", "Bed",
    ],

    # MCT / Tricky Trials: Trial grid-control midrange.
    "Chamber Champion": [
        "Trial Spawner", "Ominous Trial Spawner", "Vault of Rewards",
        "Trial Barrier", "Trail Mapper", "Copper Miner",
        "Breeze", "Ominous Captain", "Open the Vault",
        "Chamber Rewards", "Vault Jackpot", "Bed",
    ],

    # MCT: Tame / Animal go-wide build-around.
    "Pack Leader": [
        "Stable Master", "Armadillo Friend", "Wolf Companion",
        "Cat Familiar", "Sniffer Calf", "Fox Courier",
        "Panda Protector", "Tame Wolf", "Pack Howl",
        "Friendship Feast", "Cherry Grove", "Bed",
    ],

    # MCT: Redstone-spend Pulse engine.
    "Redstone Titan": [
        "Copper Bulb", "Redstone Clock", "Observer Chain",
        "Copper Factory", "Redstone Engineer", "Repeater Mage",
        "Comparator Savant", "Overclock", "Automate Mine",
        "Redstone Drill", "Deep Delver", "Bed",
    ],

    # MCT: Deep Dark Echo death-value engine.
    "Echo Warden": [
        "Sculk Sensor", "Calibrated Sensor", "Sculk Library",
        "Echo Shrieker", "Sculk Wisp", "Sculk Crawler",
        "Deep Dark Stalker", "Sculk Bloom", "Echo Shards",
        "Ancient Loot", "Deep Delver", "Bed",
    ],

    # MCT: Bastion Raid aggression.
    "Piglin Warboss": [
        "Piglin Scout", "Bastion Brute", "Nether Raider",
        "Bastion Captain", "Ghast Bombardier", "Raid Banner",
        "Bastion Ambush", "Raid the Bed", "Nether Shortcut",
        "Piglin Crossbow", "Copper Mine", "Bed",
    ],

    # MCT: End Voyage diamond/aerial ramp.
    "Ender Sovereign": [
        "End Gateway", "Chorus Grove", "End Ship",
        "Dragon Perch", "Enderling", "End Scout",
        "Dragon Herald", "Void Voyager", "Locate Stronghold",
        "Dragon Breath", "Chorus Pickaxe", "Bed",
    ],
}
