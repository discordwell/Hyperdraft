"""
Hearthstone Basic Card Set

Basic minions and spells available to all players.
"""

import random
from src.engine.game import make_minion, make_weapon, make_spell
from src.engine.types import Event, EventType, GameObject, GameState, CardType, ZoneType


# =============================================================================
# The Coin
# =============================================================================

def coin_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Gain 1 Mana Crystal this turn only."""
    player = state.players.get(obj.controller)
    if player:
        player.mana_crystals_available += 1
    return []

THE_COIN = make_spell(
    name="The Coin",
    mana_cost="{0}",
    text="Gain 1 Mana Crystal this turn only.",
    rarity="Common",
    spell_effect=coin_effect,
    requires_target=False
)


# Neutral Minions

WISP = make_minion(
    name="Wisp",
    attack=1,
    health=1,
    mana_cost="{0}",
    text="",
    rarity="Common"
)

def elven_archer_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 1 damage to a random enemy."""
    enemies = []
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            enemies.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                enemies.append(mid)
    if enemies:
        target_id = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 1, 'source': obj.id},
            source=obj.id
        )]
    return []

ELVEN_ARCHER = make_minion(
    name="Elven Archer",
    attack=1,
    health=1,
    mana_cost="{1}",
    text="Battlecry: Deal 1 damage",
    rarity="Common",
    battlecry=elven_archer_battlecry
)

STONETUSK_BOAR = make_minion(
    name="Stonetusk Boar",
    attack=1,
    health=1,
    mana_cost="{1}",
    subtypes={"Beast"},
    text="Charge",
    abilities=[{'keyword': 'charge'}],
    rarity="Common"
)

BLOODFEN_RAPTOR = make_minion(
    name="Bloodfen Raptor",
    attack=3,
    health=2,
    mana_cost="{2}",
    subtypes={"Beast"},
    text="",
    rarity="Common"
)

RIVER_CROCOLISK = make_minion(
    name="River Crocolisk",
    attack=2,
    health=3,
    mana_cost="{2}",
    subtypes={"Beast"},
    text="",
    rarity="Common"
)

def _other_friendly_minions(source: GameObject):
    """Filter factory: other minions you control (Hearthstone uses MINION, not CREATURE)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn

def raid_leader_setup(obj: GameObject, state: GameState):
    from src.cards.interceptor_helpers import make_static_pt_boost
    return make_static_pt_boost(obj, power_mod=1, toughness_mod=0,
                                affects_filter=_other_friendly_minions(obj))

RAID_LEADER = make_minion(
    name="Raid Leader",
    attack=2,
    health=2,
    mana_cost="{3}",
    text="Your other minions have +1 Attack",
    rarity="Common",
    setup_interceptors=raid_leader_setup
)

def shattered_sun_cleric_battlecry_basic(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give a friendly minion +1/+1."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []
    friendly_minions = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller == obj.controller and minion.id != obj.id:
            if CardType.MINION in minion.characteristics.types:
                friendly_minions.append(minion_id)
    if friendly_minions:
        target_id = random.choice(friendly_minions)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
            source=obj.id
        )]
    return []

SHATTERED_SUN_CLERIC = make_minion(
    name="Shattered Sun Cleric",
    attack=3,
    health=2,
    mana_cost="{3}",
    text="Battlecry: Give a friendly minion +1/+1",
    rarity="Common",
    battlecry=shattered_sun_cleric_battlecry_basic
)

CHILLWIND_YETI = make_minion(
    name="Chillwind Yeti",
    attack=4,
    health=5,
    mana_cost="{4}",
    text="",
    rarity="Common"
)

SEN_JIN_SHIELDMASTA = make_minion(
    name="Sen'jin Shieldmasta",
    attack=3,
    health=5,
    mana_cost="{4}",
    text="Taunt",
    abilities=[{'keyword': 'taunt'}],
    rarity="Common"
)

GNOMISH_INVENTOR = make_minion(
    name="Gnomish Inventor",
    attack=2,
    health=4,
    mana_cost="{4}",
    text="Battlecry: Draw a card",
    battlecry=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )],
    rarity="Common"
)

def stormpike_commando_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 2 damage to a random enemy."""
    enemies = []
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            enemies.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                enemies.append(mid)
    if enemies:
        target_id = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': obj.id},
            source=obj.id
        )]
    return []

STORMPIKE_COMMANDO = make_minion(
    name="Stormpike Commando",
    attack=4,
    health=2,
    mana_cost="{5}",
    text="Battlecry: Deal 2 damage",
    rarity="Common",
    battlecry=stormpike_commando_battlecry
)

BOULDERFIST_OGRE = make_minion(
    name="Boulderfist Ogre",
    attack=6,
    health=7,
    mana_cost="{6}",
    text="",
    rarity="Common"
)

LORD_OF_THE_ARENA = make_minion(
    name="Lord of the Arena",
    attack=6,
    health=5,
    mana_cost="{6}",
    text="Taunt",
    abilities=[{'keyword': 'taunt'}],
    rarity="Common"
)

# Minions with special abilities

LEPER_GNOME = make_minion(
    name="Leper Gnome",
    attack=1,
    health=1,
    mana_cost="{1}",
    text="Deathrattle: Deal 2 damage to the enemy hero",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DAMAGE,
        payload={
            'target': next((p.hero_id for pid, p in state.players.items() if pid != obj.controller and p.hero_id), None),
            'amount': 2,
            'source': obj.id
        },
        source=obj.id
    )] if any(p.hero_id for pid, p in state.players.items() if pid != obj.controller) else [],
    rarity="Common"
)

HARVEST_GOLEM = make_minion(
    name="Harvest Golem",
    attack=2,
    health=3,
    mana_cost="{3}",
    subtypes={"Mech"},
    text="Deathrattle: Summon a 2/1 Damaged Golem",
    deathrattle=lambda obj, state: [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Damaged Golem',
                'power': 2,
                'toughness': 1,
                'types': {CardType.MINION},
                'subtypes': {'Mech'},
            }
        },
        source=obj.id
    )],
    rarity="Common"
)

def ironforge_rifleman_battlecry_basic(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 1 damage to a random enemy."""
    enemies = []
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            enemies.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                enemies.append(mid)
    if enemies:
        target_id = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 1, 'source': obj.id},
            source=obj.id
        )]
    return []

IRONFORGE_RIFLEMAN = make_minion(
    name="Ironforge Rifleman",
    attack=2,
    health=2,
    mana_cost="{3}",
    text="Battlecry: Deal 1 damage",
    rarity="Common",
    battlecry=ironforge_rifleman_battlecry_basic
)

NIGHTBLADE = make_minion(
    name="Nightblade",
    attack=4,
    health=4,
    mana_cost="{5}",
    text="Battlecry: Deal 3 damage to the enemy hero",
    battlecry=lambda obj, state: [Event(
        type=EventType.DAMAGE,
        payload={
            'target': next((p.hero_id for pid, p in state.players.items() if pid != obj.controller and p.hero_id), None),
            'amount': 3,
            'source': obj.id
        },
        source=obj.id
    )] if any(p.hero_id for pid, p in state.players.items() if pid != obj.controller) else [],
    rarity="Common"
)

def stormwind_champion_setup(obj: GameObject, state: GameState):
    from src.cards.interceptor_helpers import make_static_pt_boost
    return make_static_pt_boost(obj, power_mod=1, toughness_mod=1,
                                affects_filter=_other_friendly_minions(obj))

STORMWIND_CHAMPION = make_minion(
    name="Stormwind Champion",
    attack=6,
    health=6,
    mana_cost="{7}",
    text="Your other minions have +1/+1",
    rarity="Common",
    setup_interceptors=stormwind_champion_setup
)

# Additional Basic neutral minions

MURLOC_RAIDER = make_minion(
    name="Murloc Raider",
    attack=2,
    health=1,
    mana_cost="{1}",
    subtypes={"Murloc"},
    text="",
    rarity="Common"
)

GOLDSHIRE_FOOTMAN = make_minion(
    name="Goldshire Footman",
    attack=1,
    health=2,
    mana_cost="{1}",
    text="Taunt",
    abilities=[{'keyword': 'taunt'}],
    rarity="Common"
)

def voodoo_doctor_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Restore 2 Health."""
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id
    )]

VOODOO_DOCTOR = make_minion(
    name="Voodoo Doctor",
    attack=2,
    health=1,
    mana_cost="{1}",
    text="Battlecry: Restore 2 Health",
    rarity="Common",
    battlecry=voodoo_doctor_battlecry
)

FROSTWOLF_GRUNT = make_minion(
    name="Frostwolf Grunt",
    attack=2,
    health=2,
    mana_cost="{2}",
    text="Taunt",
    abilities=[{'keyword': 'taunt'}],
    rarity="Common"
)

def kobold_geomancer_setup(obj: GameObject, state: GameState):
    from src.cards.interceptor_helpers import make_spell_damage_boost
    return [make_spell_damage_boost(obj, amount=1)]

KOBOLD_GEOMANCER = make_minion(
    name="Kobold Geomancer",
    attack=2,
    health=2,
    mana_cost="{2}",
    text="Spell Damage +1",
    rarity="Common",
    setup_interceptors=kobold_geomancer_setup
)

def acidic_swamp_ooze_battlecry_basic(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Destroy opponent's weapon."""
    # Find opponent
    opponent_id = None
    for player_id in state.players:
        if player_id != obj.controller:
            opponent_id = player_id
            break

    if not opponent_id:
        return []

    opponent = state.players[opponent_id]
    if opponent.weapon_attack <= 0 and opponent.weapon_durability <= 0:
        return []

    # Clear weapon stats on player
    opponent.weapon_attack = 0
    opponent.weapon_durability = 0
    return []

ACIDIC_SWAMP_OOZE_BASIC = make_minion(
    name="Acidic Swamp Ooze",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="Battlecry: Destroy your opponent's weapon",
    rarity="Common",
    battlecry=acidic_swamp_ooze_battlecry_basic
)

NOVICE_ENGINEER_BASIC = make_minion(
    name="Novice Engineer",
    attack=1,
    health=1,
    mana_cost="{2}",
    text="Battlecry: Draw a card",
    battlecry=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )],
    rarity="Common"
)

def dalaran_mage_setup(obj: GameObject, state: GameState):
    from src.cards.interceptor_helpers import make_spell_damage_boost
    return [make_spell_damage_boost(obj, amount=1)]

DALARAN_MAGE = make_minion(
    name="Dalaran Mage",
    attack=1,
    health=4,
    mana_cost="{3}",
    text="Spell Damage +1",
    rarity="Common",
    setup_interceptors=dalaran_mage_setup
)

def razorfen_hunter_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Summon a 1/1 Boar."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Boar',
                'power': 1,
                'toughness': 1,
                'types': {CardType.MINION},
                'subtypes': {'Beast'},
            }
        },
        source=obj.id
    )]

RAZORFEN_HUNTER = make_minion(
    name="Razorfen Hunter",
    attack=2,
    health=3,
    mana_cost="{3}",
    text="Battlecry: Summon a 1/1 Boar",
    rarity="Common",
    battlecry=razorfen_hunter_battlecry
)

SILVERBACK_PATRIARCH = make_minion(
    name="Silverback Patriarch",
    attack=1,
    health=4,
    mana_cost="{3}",
    subtypes={"Beast"},
    text="Taunt",
    abilities=[{'keyword': 'taunt'}],
    rarity="Common"
)

OASIS_SNAPJAW = make_minion(
    name="Oasis Snapjaw",
    attack=2,
    health=7,
    mana_cost="{4}",
    subtypes={"Beast"},
    text="",
    rarity="Common"
)

def ogre_magi_setup(obj: GameObject, state: GameState):
    from src.cards.interceptor_helpers import make_spell_damage_boost
    return [make_spell_damage_boost(obj, amount=1)]

OGRE_MAGI = make_minion(
    name="Ogre Magi",
    attack=4,
    health=4,
    mana_cost="{4}",
    text="Spell Damage +1",
    rarity="Common",
    setup_interceptors=ogre_magi_setup
)

def darkscale_healer_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Restore 2 Health to all friendly characters."""
    events = []
    # Heal hero
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id
    ))
    # Heal friendly minions (reduce damage + emit events)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller == obj.controller and CardType.MINION in m.characteristics.types:
                if m.state.damage > 0:
                    heal_amount = min(m.state.damage, 2)
                    m.state.damage -= heal_amount
                    events.append(Event(
                        type=EventType.LIFE_CHANGE,
                        payload={'object_id': mid, 'amount': heal_amount},
                        source=obj.id
                    ))
    return events

DARKSCALE_HEALER = make_minion(
    name="Darkscale Healer",
    attack=4,
    health=5,
    mana_cost="{5}",
    text="Battlecry: Restore 2 Health to all friendly characters",
    rarity="Common",
    battlecry=darkscale_healer_battlecry
)

def gurubashi_berserker_setup(obj: GameObject, state: GameState):
    from src.cards.interceptor_helpers import make_whenever_takes_damage_trigger
    def take_damage_effect(event, s):
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
            source=obj.id
        )]
    return [make_whenever_takes_damage_trigger(obj, take_damage_effect)]

GURUBASHI_BERSERKER = make_minion(
    name="Gurubashi Berserker",
    attack=2,
    health=7,
    mana_cost="{5}",
    text="Whenever this minion takes damage, gain +3 Attack",
    rarity="Common",
    setup_interceptors=gurubashi_berserker_setup
)

def frostwolf_warlord_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Gain +1/+1 for each other friendly minion."""
    count = 0
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.id != obj.id and m.controller == obj.controller and CardType.MINION in m.characteristics.types:
                count += 1
    if count > 0:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': count, 'toughness_mod': count, 'duration': 'permanent'},
            source=obj.id
        )]
    return []

FROSTWOLF_WARLORD = make_minion(
    name="Frostwolf Warlord",
    attack=4,
    health=4,
    mana_cost="{5}",
    text="Battlecry: Gain +1/+1 for each other friendly minion",
    rarity="Common",
    battlecry=frostwolf_warlord_battlecry
)

MAGMA_RAGER = make_minion(
    name="Magma Rager",
    attack=5,
    health=1,
    mana_cost="{3}",
    text="",
    rarity="Common"
)

CORE_HOUND = make_minion(
    name="Core Hound",
    attack=9,
    health=5,
    mana_cost="{7}",
    subtypes={"Beast"},
    text="",
    rarity="Common"
)

WAR_GOLEM = make_minion(
    name="War Golem",
    attack=7,
    health=7,
    mana_cost="{7}",
    text="",
    rarity="Common"
)

# Basic weapons

LIGHT_S_JUSTICE = make_weapon(
    name="Light's Justice",
    attack=1,
    durability=4,
    mana_cost="{1}",
    text="",
    rarity="Common"
)

FIERY_WAR_AXE = make_weapon(
    name="Fiery War Axe",
    attack=3,
    durability=2,
    mana_cost="{3}",
    text="",
    rarity="Common"
)

ARCANITE_REAPER = make_weapon(
    name="Arcanite Reaper",
    attack=5,
    durability=2,
    mana_cost="{5}",
    text="",
    rarity="Common"
)


# All basic cards
BASIC_CARDS = [
    WISP,
    MURLOC_RAIDER,
    GOLDSHIRE_FOOTMAN,
    VOODOO_DOCTOR,
    ELVEN_ARCHER,
    STONETUSK_BOAR,
    BLOODFEN_RAPTOR,
    RIVER_CROCOLISK,
    FROSTWOLF_GRUNT,
    KOBOLD_GEOMANCER,
    ACIDIC_SWAMP_OOZE_BASIC,
    NOVICE_ENGINEER_BASIC,
    RAID_LEADER,
    DALARAN_MAGE,
    RAZORFEN_HUNTER,
    SILVERBACK_PATRIARCH,
    MAGMA_RAGER,
    SHATTERED_SUN_CLERIC,
    CHILLWIND_YETI,
    OASIS_SNAPJAW,
    SEN_JIN_SHIELDMASTA,
    OGRE_MAGI,
    GNOMISH_INVENTOR,
    DARKSCALE_HEALER,
    GURUBASHI_BERSERKER,
    FROSTWOLF_WARLORD,
    STORMPIKE_COMMANDO,
    BOULDERFIST_OGRE,
    LORD_OF_THE_ARENA,
    CORE_HOUND,
    WAR_GOLEM,
    LEPER_GNOME,
    HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN,
    NIGHTBLADE,
    STORMWIND_CHAMPION,
    LIGHT_S_JUSTICE,
    FIERY_WAR_AXE,
    ARCANITE_REAPER,
]
