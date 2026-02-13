"""
Hearthstone Classic Set

Real Hearthstone cards with full mechanics:
- Battlecries
- Deathrattles
- Spells with effects
- Weapons
- Legendary minions
"""

from src.engine.game import make_minion, make_spell, make_weapon
from src.engine.types import Color, Event, EventType, CardType, GameObject, GameState, ZoneType


# =============================================================================
# Spell Effects
# =============================================================================

def fireball_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Fireball: Deal 6 damage."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0][0]
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 6, 'source': obj.id},
        source=obj.id
    )]


def frostbolt_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Frostbolt: Deal 3 damage and freeze."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0][0]
    target = state.objects.get(target_id)

    events = [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 3, 'source': obj.id},
        source=obj.id
    )]

    # Freeze the target (only if still on battlefield)
    if target and target.zone == ZoneType.BATTLEFIELD:
        target.state.frozen = True

    return events


def arcane_intellect_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Arcane Intellect: Draw 2 cards."""
    return [
        Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        ),
        Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )
    ]


def consecration_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Consecration: Deal 2 damage to all enemies."""
    events = []

    # Find all enemy minions
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for minion_id in battlefield.objects:
            minion = state.objects.get(minion_id)
            if minion and minion.controller != obj.controller:
                if CardType.MINION in minion.characteristics.types:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': minion_id, 'amount': 2, 'source': obj.id},
                        source=obj.id
                    ))

    # Damage enemy hero
    for player_id, player in state.players.items():
        if player_id != obj.controller and player.hero_id:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': player.hero_id, 'amount': 2, 'source': obj.id},
                source=obj.id
            ))

    return events


def backstab_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Backstab: Deal 2 damage to an undamaged minion."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0][0]
    target = state.objects.get(target_id)

    # Only works on undamaged minions
    if target and target.state.damage == 0:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': obj.id},
            source=obj.id
        )]

    return []


def arcane_missiles_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Arcane Missiles: Deal 3 damage randomly split among all enemies."""
    import random
    events = []

    # Get all valid enemy targets (hero + minions)
    enemy_targets = []

    # Find opponent
    for player_id, player in state.players.items():
        if player_id != obj.controller and player.hero_id:
            enemy_targets.append(player.hero_id)
            break

    # Find enemy minions
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for minion_id in battlefield.objects:
            minion = state.objects.get(minion_id)
            if minion and minion.controller != obj.controller:
                if CardType.MINION in minion.characteristics.types:
                    enemy_targets.append(minion_id)

    # Deal 3 missiles to random targets
    if enemy_targets:
        for _ in range(3):
            target_id = random.choice(enemy_targets)
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 1, 'source': obj.id},
                source=obj.id
            ))

    return events


# =============================================================================
# Battlecries
# =============================================================================

def acidic_swamp_ooze_battlecry(obj: GameObject, state: GameState) -> list[Event]:
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

    # Clear weapon stats on hero object too
    if opponent.hero_id:
        hero = state.objects.get(opponent.hero_id)
        if hero:
            hero.state.weapon_attack = 0
            hero.state.weapon_durability = 0

    # Move weapon cards to graveyard
    events = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for card_id in list(battlefield.objects):
            card = state.objects.get(card_id)
            if (card and card.controller == opponent_id and
                    CardType.WEAPON in card.characteristics.types):
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': card_id, 'reason': 'weapon_destroyed'},
                    source=obj.id
                ))

    return events


def shattered_sun_cleric_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give a friendly minion +1/+1."""
    # Find a random friendly minion (AI will need to target)
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
        import random
        target_id = random.choice(friendly_minions)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
            source=obj.id
        )]

    return []


def novice_engineer_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Draw a card."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )]


def ironforge_rifleman_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 1 damage."""
    # Find any enemy target (minion or hero)
    enemies = []

    # Enemy hero
    for player_id, player in state.players.items():
        if player_id != obj.controller and player.hero_id:
            enemies.append(player.hero_id)

    # Enemy minions on battlefield
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for minion_id in battlefield.objects:
            minion = state.objects.get(minion_id)
            if minion and minion.controller != obj.controller:
                if CardType.MINION in minion.characteristics.types:
                    enemies.append(minion_id)

    if enemies:
        import random
        target_id = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 1, 'source': obj.id},
            source=obj.id
        )]

    return []


# =============================================================================
# Deathrattles
# =============================================================================

def loot_hoarder_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deathrattle: Draw a card."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )]


# =============================================================================
# Classic Minions
# =============================================================================

ACIDIC_SWAMP_OOZE = make_minion(
    name="Acidic Swamp Ooze",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="Battlecry: Destroy your opponent's weapon.",
    rarity="Common",
    battlecry=acidic_swamp_ooze_battlecry
)

BLOODFEN_RAPTOR = make_minion(
    name="Bloodfen Raptor",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="",
    rarity="Common",
    subtypes=["Beast"]
)

LOOT_HOARDER = make_minion(
    name="Loot Hoarder",
    attack=2,
    health=1,
    mana_cost="{2}",
    text="Deathrattle: Draw a card.",
    rarity="Common",
    deathrattle=loot_hoarder_deathrattle
)

NOVICE_ENGINEER = make_minion(
    name="Novice Engineer",
    attack=1,
    health=1,
    mana_cost="{2}",
    text="Battlecry: Draw a card.",
    rarity="Common",
    battlecry=novice_engineer_battlecry
)

IRONFORGE_RIFLEMAN = make_minion(
    name="Ironforge Rifleman",
    attack=2,
    health=2,
    mana_cost="{3}",
    text="Battlecry: Deal 1 damage.",
    rarity="Common",
    battlecry=ironforge_rifleman_battlecry
)

SHATTERED_SUN_CLERIC = make_minion(
    name="Shattered Sun Cleric",
    attack=3,
    health=2,
    mana_cost="{3}",
    text="Battlecry: Give a friendly minion +1/+1.",
    rarity="Common",
    battlecry=shattered_sun_cleric_battlecry
)

WOLFRIDER = make_minion(
    name="Wolfrider",
    attack=3,
    health=1,
    mana_cost="{3}",
    text="Charge",
    rarity="Common",
    keywords={"charge"}
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
    rarity="Common",
    keywords={"taunt"}
)

SILVERMOON_GUARDIAN = make_minion(
    name="Silvermoon Guardian",
    attack=3,
    health=3,
    mana_cost="{4}",
    text="Divine Shield",
    rarity="Common",
    keywords={"divine_shield"}
)

BOULDERFIST_OGRE = make_minion(
    name="Boulderfist Ogre",
    attack=6,
    health=7,
    mana_cost="{6}",
    text="",
    rarity="Common"
)

RECKLESS_ROCKETEER = make_minion(
    name="Reckless Rocketeer",
    attack=5,
    health=2,
    mana_cost="{6}",
    text="Charge",
    rarity="Common",
    keywords={"charge"}
)

def harvest_golem_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a 2/1 Damaged Golem."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Damaged Golem',
                'power': 2,
                'toughness': 1,
                'types': {CardType.MINION},
                'subtypes': {'Mech'}
            }
        },
        source=obj.id
    )]

HARVEST_GOLEM = make_minion(
    name="Harvest Golem",
    attack=2,
    health=3,
    mana_cost="{3}",
    subtypes={"Mech"},
    text="Deathrattle: Summon a 2/1 Damaged Golem.",
    rarity="Common",
    deathrattle=harvest_golem_deathrattle
)

ARGENT_COMMANDER = make_minion(
    name="Argent Commander",
    attack=4,
    health=2,
    mana_cost="{6}",
    text="Charge, Divine Shield",
    rarity="Rare",
    keywords={"charge", "divine_shield"}
)

def abomination_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to all characters."""
    events = []
    battlefield = state.zones.get('battlefield')

    # Damage all minions
    if battlefield:
        for minion_id in list(battlefield.objects):
            minion = state.objects.get(minion_id)
            if minion and CardType.MINION in minion.characteristics.types:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': minion_id, 'amount': 2, 'source': obj.id},
                    source=obj.id
                ))

    # Damage all heroes
    for player in state.players.values():
        if player.hero_id:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': player.hero_id, 'amount': 2, 'source': obj.id},
                source=obj.id
            ))

    return events

ABOMINATION = make_minion(
    name="Abomination",
    attack=4,
    health=4,
    mana_cost="{5}",
    text="Taunt. Deathrattle: Deal 2 damage to all characters.",
    rarity="Rare",
    keywords={"taunt"},
    deathrattle=abomination_deathrattle
)

STRANGLETHORN_TIGER = make_minion(
    name="Stranglethorn Tiger",
    attack=5,
    health=5,
    mana_cost="{5}",
    subtypes={"Beast"},
    text="Stealth",
    rarity="Common",
    keywords={"stealth"}
)

VENTURE_CO_MERCENARY = make_minion(
    name="Venture Co. Mercenary",
    attack=7,
    health=6,
    mana_cost="{5}",
    text="Your minions cost (3) more.",
    rarity="Common"
)

# =============================================================================
# Classic Spells
# =============================================================================

FIREBALL = make_spell(
    name="Fireball",
    mana_cost="{4}",
    text="Deal 6 damage.",
    colors={Color.RED},
    rarity="Common",
    spell_effect=fireball_effect,
    requires_target=True
)

FROSTBOLT = make_spell(
    name="Frostbolt",
    mana_cost="{2}",
    text="Deal 3 damage to a character and Freeze it.",
    colors={Color.BLUE},
    rarity="Common",
    spell_effect=frostbolt_effect,
    requires_target=True
)

ARCANE_INTELLECT = make_spell(
    name="Arcane Intellect",
    mana_cost="{3}",
    text="Draw 2 cards.",
    colors={Color.BLUE},
    rarity="Common",
    spell_effect=arcane_intellect_effect,
    requires_target=False
)

CONSECRATION = make_spell(
    name="Consecration",
    mana_cost="{4}",
    text="Deal 2 damage to all enemies.",
    colors={Color.WHITE},
    rarity="Common",
    spell_effect=consecration_effect,
    requires_target=False
)

BACKSTAB = make_spell(
    name="Backstab",
    mana_cost="{0}",
    text="Deal 2 damage to an undamaged minion.",
    colors={Color.BLACK},
    rarity="Common",
    spell_effect=backstab_effect,
    requires_target=True
)

ARCANE_MISSILES = make_spell(
    name="Arcane Missiles",
    mana_cost="{1}",
    text="Deal 3 damage randomly split among all enemies.",
    colors={Color.BLUE},
    rarity="Common",
    spell_effect=arcane_missiles_effect,
    requires_target=False
)

def polymorph_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Transform a minion into a 1/1 Sheep."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0][0]
    target = state.objects.get(target_id)

    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.MINION not in target.characteristics.types:
        return []

    # Transform into Sheep - clear everything
    target.characteristics.power = 1
    target.characteristics.toughness = 1
    target.characteristics.abilities = []
    target.characteristics.subtypes = {"Sheep"}
    target.name = "Sheep"

    # Clear damage (Sheep is a fresh 1/1)
    target.state.damage = 0

    # Clear Hearthstone state flags
    target.state.divine_shield = False
    target.state.stealth = False
    target.state.windfury = False
    target.state.frozen = False
    target.state.summoning_sickness = True  # Sheep can't attack this turn

    # Remove all interceptors (deathrattles, triggers, etc.)
    for int_id in list(target.interceptor_ids):
        if int_id in state.interceptors:
            del state.interceptors[int_id]
    target.interceptor_ids.clear()

    return [Event(
        type=EventType.TRANSFORM,
        payload={'object_id': target_id, 'new_name': 'Sheep'},
        source=obj.id
    )]

POLYMORPH = make_spell(
    name="Polymorph",
    mana_cost="{4}",
    text="Transform a minion into a 1/1 Sheep.",
    colors={Color.BLUE},
    rarity="Common",
    spell_effect=polymorph_effect,
    requires_target=True
)

def sprint_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Draw 4 cards."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 4},
        source=obj.id
    )]

SPRINT = make_spell(
    name="Sprint",
    mana_cost="{7}",
    text="Draw 4 cards.",
    colors={Color.BLACK},
    rarity="Common",
    spell_effect=sprint_effect,
    requires_target=False
)

def mind_control_effect(obj: GameObject, state: GameState, targets: list[list[str]]) -> list[Event]:
    """Take control of an enemy minion."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0][0]
    target = state.objects.get(target_id)

    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.MINION not in target.characteristics.types:
        return []

    # Only return the event - _handle_gain_control will change the controller
    return [Event(
        type=EventType.CONTROL_CHANGE,
        payload={
            'object_id': target_id,
            'new_controller': obj.controller,
            'duration': 'permanent'  # Mind Control is permanent, not end-of-turn
        },
        source=obj.id
    )]

MIND_CONTROL = make_spell(
    name="Mind Control",
    mana_cost="{10}",
    text="Take control of an enemy minion.",
    colors={Color.BLUE},
    rarity="Rare",
    spell_effect=mind_control_effect,
    requires_target=True
)

# =============================================================================
# Classic Weapons
# =============================================================================

FIERY_WAR_AXE = make_weapon(
    name="Fiery War Axe",
    attack=3,
    durability=2,
    mana_cost="{2}",
    text="",
    rarity="Common"
)

def truesilver_champion_setup(obj: GameObject, state: GameState):
    """Whenever your hero attacks, restore 2 Health to it."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult
    from src.engine.types import new_id

    def attack_filter(event, s):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        # Trigger when the weapon owner's hero attacks
        attacker_id = event.payload.get('attacker_id')
        attacker = s.objects.get(attacker_id)
        if not attacker:
            return False
        return (CardType.HERO in attacker.characteristics.types and
                attacker.controller == obj.controller)

    def attack_handler(event, s):
        player = s.players.get(obj.controller)
        if not player:
            return InterceptorResult(action=InterceptorAction.PASS)
        heal_amount = min(2, 30 - player.life)
        if heal_amount <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': heal_amount},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield'
    )]

TRUESILVER_CHAMPION = make_weapon(
    name="Truesilver Champion",
    attack=4,
    durability=2,
    mana_cost="{4}",
    text="Whenever your hero attacks, restore 2 Health to it.",
    rarity="Common",
    setup_interceptors=truesilver_champion_setup
)

ARCANITE_REAPER = make_weapon(
    name="Arcanite Reaper",
    attack=5,
    durability=2,
    mana_cost="{5}",
    text="",
    rarity="Common"
)

WISP = make_minion(
    name="Wisp",
    attack=1,
    health=1,
    mana_cost="{0}",
    text="",
    rarity="Common"
)


# =============================================================================
# Card Collections
# =============================================================================

CLASSIC_MINIONS = [
    WISP,
    ACIDIC_SWAMP_OOZE,
    BLOODFEN_RAPTOR,
    LOOT_HOARDER,
    NOVICE_ENGINEER,
    HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN,
    SHATTERED_SUN_CLERIC,
    WOLFRIDER,
    CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA,
    SILVERMOON_GUARDIAN,
    ABOMINATION,
    STRANGLETHORN_TIGER,
    VENTURE_CO_MERCENARY,
    BOULDERFIST_OGRE,
    RECKLESS_ROCKETEER,
    ARGENT_COMMANDER,
]

CLASSIC_SPELLS = [
    ARCANE_MISSILES,
    FIREBALL,
    FROSTBOLT,
    ARCANE_INTELLECT,
    POLYMORPH,
    CONSECRATION,
    BACKSTAB,
    SPRINT,
    MIND_CONTROL,
]

CLASSIC_WEAPONS = [
    FIERY_WAR_AXE,
    TRUESILVER_CHAMPION,
    ARCANITE_REAPER,
]

CLASSIC_CARDS = CLASSIC_MINIONS + CLASSIC_SPELLS + CLASSIC_WEAPONS
