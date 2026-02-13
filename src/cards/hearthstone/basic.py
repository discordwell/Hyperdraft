"""
Hearthstone Basic Card Set

Basic minions and spells available to all players.
"""

import random
from src.engine.game import make_minion, make_weapon
from src.engine.types import Event, EventType, GameObject, GameState, CardType, ZoneType


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

SHATTERED_SUN_CLERIC = make_minion(
    name="Shattered Sun Cleric",
    attack=3,
    health=2,
    mana_cost="{3}",
    text="Battlecry: Give a friendly minion +1/+1",
    rarity="Common"
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

IRONFORGE_RIFLEMAN = make_minion(
    name="Ironforge Rifleman",
    attack=2,
    health=2,
    mana_cost="{3}",
    text="Battlecry: Deal 1 damage",
    rarity="Common"
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
    ELVEN_ARCHER,
    STONETUSK_BOAR,
    BLOODFEN_RAPTOR,
    RIVER_CROCOLISK,
    RAID_LEADER,
    SHATTERED_SUN_CLERIC,
    CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA,
    GNOMISH_INVENTOR,
    STORMPIKE_COMMANDO,
    BOULDERFIST_OGRE,
    LORD_OF_THE_ARENA,
    LEPER_GNOME,
    HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN,
    NIGHTBLADE,
    STORMWIND_CHAMPION,
    LIGHT_S_JUSTICE,
    FIERY_WAR_AXE,
    ARCANITE_REAPER,
]
