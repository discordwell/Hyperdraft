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
import random


# =============================================================================
# Spell Effects
# =============================================================================

def fireball_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Fireball: Deal 6 damage."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0]
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 6, 'source': obj.id, 'from_spell': True},
        source=obj.id
    )]


def frostbolt_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Frostbolt: Deal 3 damage and freeze."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0]

    # Damage first, then freeze (both go through event pipeline)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ),
        Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': target_id},
            source=obj.id
        )
    ]


def arcane_intellect_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
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


def consecration_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
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
                        payload={'target': minion_id, 'amount': 2, 'source': obj.id, 'from_spell': True},
                        source=obj.id
                    ))

    # Damage enemy hero
    for player_id, player in state.players.items():
        if player_id != obj.controller and player.hero_id:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': player.hero_id, 'amount': 2, 'source': obj.id, 'from_spell': True},
                source=obj.id
            ))

    return events


def backstab_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Backstab: Deal 2 damage to an undamaged minion."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0]
    target = state.objects.get(target_id)

    # Only works on undamaged minions
    if target and target.state.damage == 0:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]

    return []


def arcane_missiles_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
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
                payload={'target': target_id, 'amount': 1, 'source': obj.id, 'from_spell': True},
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
    subtypes={"Beast"}
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


def knife_juggler_setup(obj: GameObject, state: GameState):
    """After you summon a minion, deal 1 damage to a random enemy."""
    import random as rng
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def summon_filter(event, s):
        if event.type == EventType.ZONE_CHANGE:
            # A minion entered the battlefield under our control (not Knife Juggler itself)
            if (event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD and
                    event.payload.get('object_id') != obj.id):
                entering = s.objects.get(event.payload.get('object_id'))
                if entering and entering.controller == obj.controller:
                    if CardType.MINION in entering.characteristics.types:
                        return True
        if event.type == EventType.CREATE_TOKEN:
            if event.payload.get('controller') == obj.controller:
                return True
        return False

    def summon_handler(event, s):
        # Pick a random enemy (minion or hero)
        enemies = []
        for pid, player in s.players.items():
            if pid != obj.controller and player.hero_id:
                enemies.append(player.hero_id)
        battlefield = s.zones.get('battlefield')
        if battlefield:
            for mid in battlefield.objects:
                m = s.objects.get(mid)
                if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                    enemies.append(mid)
        if enemies:
            target = rng.choice(enemies)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DAMAGE,
                    payload={'target': target, 'amount': 1, 'source': obj.id},
                    source=obj.id
                )]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=summon_filter,
        handler=summon_handler,
        duration='while_on_battlefield'
    )]

KNIFE_JUGGLER = make_minion(
    name="Knife Juggler",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="After you summon a minion, deal 1 damage to a random enemy.",
    rarity="Rare",
    setup_interceptors=knife_juggler_setup
)


def water_elemental_setup(obj: GameObject, state: GameState):
    """Freeze any character damaged by this minion."""
    from src.cards.interceptor_helpers import make_damage_trigger

    def freeze_effect(event, s):
        target_id = event.payload.get('target')
        if target_id:
            return [Event(
                type=EventType.FREEZE_TARGET,
                payload={'target': target_id},
                source=obj.id
            )]
        return []

    return [make_damage_trigger(obj, freeze_effect)]

WATER_ELEMENTAL = make_minion(
    name="Water Elemental",
    attack=3,
    health=6,
    mana_cost="{4}",
    text="Freeze any character damaged by this minion.",
    rarity="Common",
    setup_interceptors=water_elemental_setup
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


def flamestrike_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Flamestrike: Deal 4 damage to all enemy minions."""
    events = []

    battlefield = state.zones.get('battlefield')
    if battlefield:
        for minion_id in battlefield.objects:
            minion = state.objects.get(minion_id)
            if minion and minion.controller != obj.controller:
                if CardType.MINION in minion.characteristics.types:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': minion_id, 'amount': 4, 'source': obj.id, 'from_spell': True},
                        source=obj.id
                    ))

    return events

FLAMESTRIKE = make_spell(
    name="Flamestrike",
    mana_cost="{7}",
    text="Deal 4 damage to all enemy minions.",
    colors={Color.RED},
    rarity="Common",
    spell_effect=flamestrike_effect,
    requires_target=False
)

def polymorph_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Transform a minion into a 1/1 Sheep."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0]
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

    # Clear damage and PT modifiers (Sheep is a fresh 1/1)
    target.state.damage = 0
    target.state.counters = {}
    if hasattr(target.state, 'pt_modifiers'):
        target.state.pt_modifiers = []

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

    # Clear card_def so interceptors can't re-register if Sheep re-enters battlefield
    target.card_def = None

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

def sprint_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
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

def mind_control_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Take control of an enemy minion."""
    if not targets or not targets[0]:
        return []

    target_id = targets[0]
    target = state.objects.get(target_id)

    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.MINION not in target.characteristics.types:
        return []

    # Check board limit: in Hearthstone, if the caster has 7 minions,
    # Mind Control destroys the target instead of stealing it
    if state.game_mode == "hearthstone":
        battlefield = state.zones.get('battlefield')
        if battlefield:
            minion_count = sum(
                1 for oid in battlefield.objects
                if oid in state.objects
                and state.objects[oid].controller == obj.controller
                and CardType.MINION in state.objects[oid].characteristics.types
            )
            if minion_count >= 7:
                return [Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': target_id, 'reason': 'mind_control_board_full'},
                    source=obj.id
                )]

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
        # Skip if already at max HP
        if player.life >= (getattr(player, 'max_life', 30) or 30):
            return InterceptorResult(action=InterceptorAction.PASS)
        # Emit full heal amount - pipeline's _handle_life_change caps at max_life
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
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
# Additional Classic Neutral Minions (1-Cost)
# =============================================================================

def abusive_sergeant_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give a minion +2 Attack this turn."""
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
            payload={'object_id': target_id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return []

ABUSIVE_SERGEANT = make_minion(
    name="Abusive Sergeant",
    attack=1,
    health=1,
    mana_cost="{1}",
    text="Battlecry: Give a minion +2 Attack this turn.",
    rarity="Common",
    battlecry=abusive_sergeant_battlecry
)

ARGENT_SQUIRE = make_minion(
    name="Argent Squire",
    attack=1,
    health=1,
    mana_cost="{1}",
    text="Divine Shield",
    rarity="Common",
    keywords={"divine_shield"}
)

WORGEN_INFILTRATOR = make_minion(
    name="Worgen Infiltrator",
    attack=2,
    health=1,
    mana_cost="{1}",
    text="Stealth",
    rarity="Common",
    keywords={"stealth"}
)

def young_priestess_setup(obj: GameObject, state: GameState):
    """At end of turn, give a random friendly minion +1 Health."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        if event.type == EventType.TURN_END:
            return event.payload.get('player') == obj.controller
        return False

    def end_turn_handler(event, s):
        battlefield = s.zones.get('battlefield')
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)

        friendly_minions = []
        for minion_id in battlefield.objects:
            minion = s.objects.get(minion_id)
            if minion and minion.controller == obj.controller and minion.id != obj.id:
                if CardType.MINION in minion.characteristics.types:
                    friendly_minions.append(minion_id)

        if friendly_minions:
            target_id = random.choice(friendly_minions)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': target_id, 'power_mod': 0, 'toughness_mod': 1, 'duration': 'permanent'},
                    source=obj.id
                )]
            )

        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_turn_filter,
        handler=end_turn_handler,
        duration='while_on_battlefield'
    )]

YOUNG_PRIESTESS = make_minion(
    name="Young Priestess",
    attack=2,
    health=1,
    mana_cost="{1}",
    text="At the end of your turn, give another random friendly minion +1 Health.",
    rarity="Rare",
    setup_interceptors=young_priestess_setup
)

HUNGRY_CRAB = make_minion(
    name="Hungry Crab",
    attack=1,
    health=2,
    mana_cost="{1}",
    subtypes={"Beast"},
    text="Battlecry: Destroy a Murloc and gain +2/+2. (Text only)",
    rarity="Epic"
)

# =============================================================================
# Additional Classic Neutral Minions (2-Cost)
# =============================================================================

DIRE_WOLF_ALPHA = make_minion(
    name="Dire Wolf Alpha",
    attack=2,
    health=2,
    mana_cost="{2}",
    subtypes={"Beast"},
    text="Your other minions have +1 Attack. (Simplified from adjacent)",
    rarity="Common"
)

FAERIE_DRAGON = make_minion(
    name="Faerie Dragon",
    attack=3,
    health=2,
    mana_cost="{2}",
    subtypes={"Dragon"},
    text="Can't be targeted by spells or Hero Powers.",
    rarity="Common"
)

def sunfury_protector_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give adjacent minions Taunt (simplified: give a random friendly minion Taunt)."""
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
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keyword': 'taunt'},
            source=obj.id
        )]

    return []

SUNFURY_PROTECTOR = make_minion(
    name="Sunfury Protector",
    attack=2,
    health=3,
    mana_cost="{2}",
    text="Battlecry: Give adjacent minions Taunt. (Simplified)",
    rarity="Rare",
    battlecry=sunfury_protector_battlecry
)

def wild_pyromancer_setup(obj: GameObject, state: GameState):
    """After you cast a spell, deal 1 damage to ALL minions."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def spell_filter(event, s):
        if event.type == EventType.SPELL_CAST:
            cast_obj = s.objects.get(event.payload.get('spell_id'))
            if cast_obj and cast_obj.controller == obj.controller:
                return True
        return False

    def spell_handler(event, s):
        events = []
        battlefield = s.zones.get('battlefield')
        if battlefield:
            for minion_id in list(battlefield.objects):
                minion = s.objects.get(minion_id)
                if minion and CardType.MINION in minion.characteristics.types:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': minion_id, 'amount': 1, 'source': obj.id},
                        source=obj.id
                    ))

        if events:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=events)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter,
        handler=spell_handler,
        duration='while_on_battlefield'
    )]

WILD_PYROMANCER = make_minion(
    name="Wild Pyromancer",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="After you cast a spell, deal 1 damage to ALL minions.",
    rarity="Rare",
    setup_interceptors=wild_pyromancer_setup
)

def bloodmage_thalnos_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deathrattle: Draw a card."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )]

BLOODMAGE_THALNOS = make_minion(
    name="Bloodmage Thalnos",
    attack=1,
    health=1,
    mana_cost="{2}",
    text="Spell Damage +1. Deathrattle: Draw a card.",
    rarity="Legendary",
    deathrattle=bloodmage_thalnos_deathrattle
)

def master_swordsmith_setup(obj: GameObject, state: GameState):
    """At end of turn, give a random friendly minion +1 Attack."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        if event.type == EventType.TURN_END:
            return event.payload.get('player') == obj.controller
        return False

    def end_turn_handler(event, s):
        battlefield = s.zones.get('battlefield')
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)

        friendly_minions = []
        for minion_id in battlefield.objects:
            minion = s.objects.get(minion_id)
            if minion and minion.controller == obj.controller and minion.id != obj.id:
                if CardType.MINION in minion.characteristics.types:
                    friendly_minions.append(minion_id)

        if friendly_minions:
            target_id = random.choice(friendly_minions)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'permanent'},
                    source=obj.id
                )]
            )

        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_turn_filter,
        handler=end_turn_handler,
        duration='while_on_battlefield'
    )]

MASTER_SWORDSMITH = make_minion(
    name="Master Swordsmith",
    attack=1,
    health=3,
    mana_cost="{2}",
    text="At the end of your turn, give another random friendly minion +1 Attack.",
    rarity="Rare",
    setup_interceptors=master_swordsmith_setup
)

CRAZED_ALCHEMIST = make_minion(
    name="Crazed Alchemist",
    attack=2,
    health=2,
    mana_cost="{2}",
    text="Battlecry: Swap a minion's Attack and Health. (Text only)",
    rarity="Rare"
)

def mad_bomber_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 3 damage randomly split among all other characters."""
    events = []

    # Get all valid targets (all characters except Mad Bomber)
    targets = []

    # All heroes
    for player in state.players.values():
        if player.hero_id:
            targets.append(player.hero_id)

    # All minions except self
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for minion_id in battlefield.objects:
            if minion_id != obj.id:
                minion = state.objects.get(minion_id)
                if minion and CardType.MINION in minion.characteristics.types:
                    targets.append(minion_id)

    # Deal 3 damage randomly
    if targets:
        for _ in range(3):
            target_id = random.choice(targets)
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 1, 'source': obj.id},
                source=obj.id
            ))

    return events

MAD_BOMBER = make_minion(
    name="Mad Bomber",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="Battlecry: Deal 3 damage randomly split among all other characters.",
    rarity="Rare",
    battlecry=mad_bomber_battlecry
)

def amani_berserker_setup(obj: GameObject, state: GameState):
    """Enrage: +3 Attack."""
    from src.cards.interceptor_helpers import make_enrage_trigger
    return make_enrage_trigger(obj, attack_bonus=3)

AMANI_BERSERKER = make_minion(
    name="Amani Berserker",
    attack=2,
    health=3,
    mana_cost="{2}",
    text="Enrage: +3 Attack.",
    rarity="Common",
    setup_interceptors=amani_berserker_setup
)

def murloc_tidehunter_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Summon a 1/1 Murloc Scout."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Murloc Scout',
                'power': 1,
                'toughness': 1,
                'types': {CardType.MINION},
                'subtypes': {'Murloc'}
            }
        },
        source=obj.id
    )]

MURLOC_TIDEHUNTER = make_minion(
    name="Murloc Tidehunter",
    attack=2,
    health=1,
    mana_cost="{2}",
    subtypes={"Murloc"},
    text="Battlecry: Summon a 1/1 Murloc Scout.",
    rarity="Common",
    battlecry=murloc_tidehunter_battlecry
)

MAD_SCIENTIST = make_minion(
    name="Mad Scientist",
    attack=2,
    health=2,
    mana_cost="{2}",
    text="Deathrattle: Put a Secret from your deck into the battlefield. (Text only)",
    rarity="Common"
)

# =============================================================================
# Additional Classic Neutral Minions (3-Cost)
# =============================================================================

def earthen_ring_farseer_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Restore 3 Health to a random friendly character."""
    # Simplified: heal friendly hero
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 3},
        source=obj.id
    )]

EARTHEN_RING_FARSEER = make_minion(
    name="Earthen Ring Farseer",
    attack=3,
    health=3,
    mana_cost="{3}",
    text="Battlecry: Restore 3 Health.",
    rarity="Common",
    battlecry=earthen_ring_farseer_battlecry
)

JUNGLE_PANTHER = make_minion(
    name="Jungle Panther",
    attack=4,
    health=2,
    mana_cost="{3}",
    subtypes={"Beast"},
    text="Stealth",
    rarity="Common",
    keywords={"stealth"}
)

SCARLET_CRUSADER = make_minion(
    name="Scarlet Crusader",
    attack=3,
    health=1,
    mana_cost="{3}",
    text="Divine Shield",
    rarity="Common",
    keywords={"divine_shield"}
)

def questing_adventurer_setup(obj: GameObject, state: GameState):
    """Whenever you play a card, gain +1/+1."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def play_filter(event, s):
        if event.type in (EventType.CAST, EventType.SPELL_CAST, EventType.ZONE_CHANGE):
            source_id = event.payload.get('spell_id') or event.payload.get('object_id') or event.source
            source = s.objects.get(source_id)
            if source and source.controller == obj.controller and source.id != obj.id:
                return True
        return False

    def grow_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
                source=obj.id)]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=play_filter, handler=grow_handler,
        duration='while_on_battlefield'
    )]

QUESTING_ADVENTURER = make_minion(
    name="Questing Adventurer",
    attack=2,
    health=2,
    mana_cost="{3}",
    text="Whenever you play a card, gain +1/+1.",
    rarity="Rare",
    setup_interceptors=questing_adventurer_setup
)

def acolyte_of_pain_setup(obj: GameObject, state: GameState):
    """Whenever this minion takes damage, draw a card."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def damage_filter(event, s):
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == obj.id

    def draw_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=damage_filter, handler=draw_handler,
        duration='while_on_battlefield'
    )]

ACOLYTE_OF_PAIN = make_minion(
    name="Acolyte of Pain",
    attack=1,
    health=3,
    mana_cost="{3}",
    text="Whenever this minion takes damage, draw a card.",
    rarity="Common",
    setup_interceptors=acolyte_of_pain_setup
)

def injured_blademaster_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 4 damage to HIMSELF."""
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': obj.id, 'amount': 4, 'source': obj.id},
        source=obj.id
    )]

INJURED_BLADEMASTER = make_minion(
    name="Injured Blademaster",
    attack=4,
    health=7,
    mana_cost="{3}",
    text="Battlecry: Deal 4 damage to HIMSELF.",
    rarity="Rare",
    battlecry=injured_blademaster_battlecry
)

MIND_CONTROL_TECH = make_minion(
    name="Mind Control Tech",
    attack=3,
    health=3,
    mana_cost="{3}",
    text="Battlecry: If your opponent has 4 or more minions, take control of one at random. (Text only)",
    rarity="Rare"
)

def coldlight_oracle_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Each player draws 2 cards."""
    events = []
    for player_id in state.players:
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': player_id, 'count': 2},
            source=obj.id
        ))
    return events

COLDLIGHT_ORACLE = make_minion(
    name="Coldlight Oracle",
    attack=2,
    health=2,
    mana_cost="{3}",
    subtypes={"Murloc"},
    text="Battlecry: Each player draws 2 cards.",
    rarity="Rare",
    battlecry=coldlight_oracle_battlecry
)

def imp_master_setup(obj: GameObject, state: GameState):
    """At the end of your turn, deal 1 damage to this minion and summon a 1/1 Imp."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def imp_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.DAMAGE, payload={'target': obj.id, 'amount': 1, 'source': obj.id}, source=obj.id),
                Event(type=EventType.CREATE_TOKEN, payload={
                    'controller': obj.controller,
                    'token': {'name': 'Imp', 'power': 1, 'toughness': 1, 'types': {CardType.MINION}, 'subtypes': {'Demon'}}
                }, source=obj.id)
            ]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=end_turn_filter, handler=imp_handler,
        duration='while_on_battlefield'
    )]

IMP_MASTER = make_minion(
    name="Imp Master",
    attack=1,
    health=5,
    mana_cost="{3}",
    text="At the end of your turn, deal 1 damage to this minion and summon a 1/1 Imp.",
    rarity="Rare",
    setup_interceptors=imp_master_setup
)

ALARM_O_BOT = make_minion(
    name="Alarm-o-Bot",
    attack=0,
    health=3,
    mana_cost="{3}",
    subtypes={"Mech"},
    text="At the start of your turn, swap this minion with a random one in your hand. (Text only)",
    rarity="Rare"
)

EMPEROR_COBRA = make_minion(
    name="Emperor Cobra",
    attack=2,
    health=3,
    mana_cost="{3}",
    subtypes={"Beast"},
    text="Destroy any minion damaged by this minion. (Poisonous - text only)",
    rarity="Rare"
)

def demolisher_setup(obj: GameObject, state: GameState):
    """At the start of your turn, deal 2 damage to a random enemy."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def turn_start_filter(event, s):
        return event.type == EventType.TURN_START and event.payload.get('player') == obj.controller

    def damage_handler(event, s):
        enemies = []
        for pid, player in s.players.items():
            if pid != obj.controller and player.hero_id:
                enemies.append(player.hero_id)
        battlefield = s.zones.get('battlefield')
        if battlefield:
            for mid in battlefield.objects:
                m = s.objects.get(mid)
                if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                    enemies.append(mid)
        if enemies:
            target = random.choice(enemies)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 2, 'source': obj.id}, source=obj.id)]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=turn_start_filter, handler=damage_handler,
        duration='while_on_battlefield'
    )]

DEMOLISHER = make_minion(
    name="Demolisher",
    attack=1,
    health=4,
    mana_cost="{3}",
    subtypes={"Mech"},
    text="At the start of your turn, deal 2 damage to a random enemy.",
    rarity="Rare",
    setup_interceptors=demolisher_setup
)

def raging_worgen_setup(obj: GameObject, state: GameState):
    """Enrage: Windfury and +1 Attack."""
    from src.cards.interceptor_helpers import make_enrage_trigger
    return make_enrage_trigger(obj, attack_bonus=1, keywords={'windfury'})

RAGING_WORGEN = make_minion(
    name="Raging Worgen",
    attack=3,
    health=3,
    mana_cost="{3}",
    text="Enrage: Windfury and +1 Attack.",
    rarity="Common",
    setup_interceptors=raging_worgen_setup
)

def ironbeak_owl_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Silence a random enemy minion."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []
    enemy_minions = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller != obj.controller and CardType.MINION in minion.characteristics.types:
            enemy_minions.append(minion_id)
    if enemy_minions:
        target_id = random.choice(enemy_minions)
        return [Event(type=EventType.SILENCE_TARGET, payload={'target': target_id}, source=obj.id)]
    return []

IRONBEAK_OWL = make_minion(
    name="Ironbeak Owl",
    attack=2,
    health=1,
    mana_cost="{3}",
    subtypes={"Beast"},
    text="Battlecry: Silence a minion.",
    rarity="Common",
    battlecry=ironbeak_owl_battlecry
)

# =============================================================================
# Additional Classic Neutral Minions (4-Cost)
# =============================================================================

def spellbreaker_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Silence a random enemy minion."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    enemy_minions = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller != obj.controller:
            if CardType.MINION in minion.characteristics.types:
                enemy_minions.append(minion_id)

    if enemy_minions:
        target_id = random.choice(enemy_minions)
        return [Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': target_id},
            source=obj.id
        )]

    return []

SPELLBREAKER = make_minion(
    name="Spellbreaker",
    attack=4,
    health=3,
    mana_cost="{4}",
    text="Battlecry: Silence a minion.",
    rarity="Common",
    battlecry=spellbreaker_battlecry
)

def dark_iron_dwarf_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give a minion +2 Attack this turn."""
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
            payload={'object_id': target_id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return []

DARK_IRON_DWARF = make_minion(
    name="Dark Iron Dwarf",
    attack=4,
    health=4,
    mana_cost="{4}",
    text="Battlecry: Give a minion +2 Attack this turn.",
    rarity="Common",
    battlecry=dark_iron_dwarf_battlecry
)

def defender_of_argus_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give adjacent minions +1/+1 and Taunt (simplified: 2 random friendly)."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    friendly_minions = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller == obj.controller and minion.id != obj.id:
            if CardType.MINION in minion.characteristics.types:
                friendly_minions.append(minion_id)

    events = []
    targets = random.sample(friendly_minions, min(2, len(friendly_minions)))
    for target_id in targets:
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keyword': 'taunt'},
            source=obj.id
        ))

    return events

DEFENDER_OF_ARGUS = make_minion(
    name="Defender of Argus",
    attack=2,
    health=3,
    mana_cost="{4}",
    text="Battlecry: Give adjacent minions +1/+1 and Taunt. (Simplified)",
    rarity="Rare",
    battlecry=defender_of_argus_battlecry
)

def twilight_drake_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Gain +1 Health for each card in your hand."""
    hand = state.zones.get(f"hand_{obj.controller}")
    if hand:
        hand_size = len(hand.objects)
        if hand_size > 0:
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': hand_size, 'duration': 'permanent'},
                source=obj.id
            )]
    return []

TWILIGHT_DRAKE = make_minion(
    name="Twilight Drake",
    attack=4,
    health=1,
    mana_cost="{4}",
    subtypes={"Dragon"},
    text="Battlecry: Gain +1 Health for each card in your hand.",
    rarity="Rare",
    battlecry=twilight_drake_battlecry
)

def ancient_brewmaster_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Return a friendly minion to your hand."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []
    friendly_minions = []
    for mid in battlefield.objects:
        m = state.objects.get(mid)
        if m and m.controller == obj.controller and m.id != obj.id and CardType.MINION in m.characteristics.types:
            friendly_minions.append(mid)
    if friendly_minions:
        target_id = random.choice(friendly_minions)
        return [Event(type=EventType.RETURN_TO_HAND, payload={'object_id': target_id}, source=obj.id)]
    return []

ANCIENT_BREWMASTER = make_minion(
    name="Ancient Brewmaster",
    attack=5,
    health=4,
    mana_cost="{4}",
    text="Battlecry: Return a friendly minion to your hand.",
    rarity="Common",
    battlecry=ancient_brewmaster_battlecry
)

def cult_master_setup(obj: GameObject, state: GameState):
    """Whenever one of your other minions dies, draw a card."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def death_filter(event, s):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        died_id = event.payload.get('object_id')
        if died_id == obj.id:
            return False
        died = s.objects.get(died_id)
        return died and died.controller == obj.controller and CardType.MINION in died.characteristics.types

    def draw_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=death_filter, handler=draw_handler,
        duration='while_on_battlefield'
    )]

CULT_MASTER = make_minion(
    name="Cult Master",
    attack=4,
    health=2,
    mana_cost="{4}",
    text="Whenever one of your other minions dies, draw a card.",
    rarity="Common",
    setup_interceptors=cult_master_setup
)

def violet_teacher_setup(obj: GameObject, state: GameState):
    """Whenever you cast a spell, summon a 1/1 Violet Apprentice."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def spell_filter(event, s):
        if event.type in (EventType.CAST, EventType.SPELL_CAST):
            caster = event.payload.get('caster') or event.controller
            return caster == obj.controller
        return False

    def summon_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Violet Apprentice', 'power': 1, 'toughness': 1, 'types': {CardType.MINION}}
            }, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=spell_filter, handler=summon_handler,
        duration='while_on_battlefield'
    )]

VIOLET_TEACHER = make_minion(
    name="Violet Teacher",
    attack=3,
    health=5,
    mana_cost="{4}",
    text="Whenever you cast a spell, summon a 1/1 Violet Apprentice.",
    rarity="Rare",
    setup_interceptors=violet_teacher_setup
)

ANCIENT_MAGE = make_minion(
    name="Ancient Mage",
    attack=2,
    health=5,
    mana_cost="{4}",
    text="Battlecry: Give adjacent minions Spell Damage +1. (Text only)",
    rarity="Rare"
)

STORMWIND_KNIGHT = make_minion(
    name="Stormwind Knight",
    attack=2,
    health=5,
    mana_cost="{4}",
    text="Charge",
    rarity="Common",
    keywords={"charge"}
)

# =============================================================================
# Additional Classic Neutral Minions (5-Cost)
# =============================================================================

def azure_drake_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Draw a card."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )]

AZURE_DRAKE = make_minion(
    name="Azure Drake",
    attack=4,
    health=4,
    mana_cost="{5}",
    subtypes={"Dragon"},
    text="Spell Damage +1. Battlecry: Draw a card.",
    rarity="Rare",
    battlecry=azure_drake_battlecry
)

def stampeding_kodo_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Destroy a random enemy minion with 2 or less Attack."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    valid_targets = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller != obj.controller:
            if CardType.MINION in minion.characteristics.types:
                if minion.characteristics.power <= 2:
                    valid_targets.append(minion_id)

    if valid_targets:
        target_id = random.choice(valid_targets)
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id, 'reason': 'stampeding_kodo'},
            source=obj.id
        )]

    return []

STAMPEDING_KODO = make_minion(
    name="Stampeding Kodo",
    attack=3,
    health=5,
    mana_cost="{5}",
    subtypes={"Beast"},
    text="Battlecry: Destroy a random enemy minion with 2 or less Attack.",
    rarity="Rare",
    battlecry=stampeding_kodo_battlecry
)

FACELESS_MANIPULATOR = make_minion(
    name="Faceless Manipulator",
    attack=3,
    health=3,
    mana_cost="{5}",
    text="Battlecry: Choose a minion and become a copy of it. (Text only)",
    rarity="Epic"
)

CAPTAIN_GREENSKIN = make_minion(
    name="Captain Greenskin",
    attack=5,
    health=4,
    mana_cost="{5}",
    subtypes={"Pirate"},
    text="Battlecry: Give your weapon +1/+1. (Text only)",
    rarity="Legendary"
)

HARRISON_JONES = make_minion(
    name="Harrison Jones",
    attack=5,
    health=4,
    mana_cost="{5}",
    text="Battlecry: Destroy your opponent's weapon and draw cards equal to its Durability. (Text only)",
    rarity="Legendary"
)

def silver_hand_knight_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Summon a 2/2 Squire."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Squire',
                'power': 2,
                'toughness': 2,
                'types': {CardType.MINION},
                'subtypes': set()
            }
        },
        source=obj.id
    )]

SILVER_HAND_KNIGHT = make_minion(
    name="Silver Hand Knight",
    attack=4,
    health=4,
    mana_cost="{5}",
    text="Battlecry: Summon a 2/2 Squire.",
    rarity="Common",
    battlecry=silver_hand_knight_battlecry
)

def big_game_hunter_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Destroy a minion with 7 or more Attack."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    valid_targets = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller != obj.controller:
            if CardType.MINION in minion.characteristics.types:
                if minion.characteristics.power >= 7:
                    valid_targets.append(minion_id)

    if valid_targets:
        target_id = random.choice(valid_targets)
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id, 'reason': 'big_game_hunter'},
            source=obj.id
        )]

    return []

BIG_GAME_HUNTER = make_minion(
    name="Big Game Hunter",
    attack=4,
    health=2,
    mana_cost="{5}",
    text="Battlecry: Destroy a minion with 7 or more Attack.",
    rarity="Epic",
    battlecry=big_game_hunter_battlecry
)

def leeroy_jenkins_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Summon two 1/1 Whelps for your opponent."""
    # Find opponent
    opponent_id = None
    for player_id in state.players:
        if player_id != obj.controller:
            opponent_id = player_id
            break

    if not opponent_id:
        return []

    events = []
    for _ in range(2):
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': opponent_id,
                'token': {
                    'name': 'Whelp',
                    'power': 1,
                    'toughness': 1,
                    'types': {CardType.MINION},
                    'subtypes': {'Dragon'}
                }
            },
            source=obj.id
        ))

    return events

LEEROY_JENKINS = make_minion(
    name="Leeroy Jenkins",
    attack=6,
    health=2,
    mana_cost="{5}",
    text="Charge. Battlecry: Summon two 1/1 Whelps for your opponent.",
    rarity="Legendary",
    keywords={"charge"},
    battlecry=leeroy_jenkins_battlecry
)

# =============================================================================
# Additional Classic Neutral Minions (6-Cost)
# =============================================================================

SUNWALKER = make_minion(
    name="Sunwalker",
    attack=4,
    health=5,
    mana_cost="{6}",
    text="Taunt. Divine Shield",
    rarity="Rare",
    keywords={"taunt", "divine_shield"}
)

def frost_elemental_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Freeze a random enemy character."""
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
        target = random.choice(enemies)
        return [Event(type=EventType.FREEZE_TARGET, payload={'target': target}, source=obj.id)]
    return []

FROST_ELEMENTAL = make_minion(
    name="Frost Elemental",
    attack=5,
    health=5,
    mana_cost="{6}",
    text="Battlecry: Freeze a character.",
    rarity="Common",
    battlecry=frost_elemental_battlecry
)

def sylvanas_windrunner_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deathrattle: Take control of a random enemy minion."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    enemy_minions = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller != obj.controller:
            if CardType.MINION in minion.characteristics.types:
                enemy_minions.append(minion_id)

    if enemy_minions:
        target_id = random.choice(enemy_minions)
        return [Event(
            type=EventType.CONTROL_CHANGE,
            payload={
                'object_id': target_id,
                'new_controller': obj.controller,
                'duration': 'permanent'
            },
            source=obj.id
        )]

    return []

SYLVANAS_WINDRUNNER = make_minion(
    name="Sylvanas Windrunner",
    attack=5,
    health=5,
    mana_cost="{6}",
    text="Deathrattle: Take control of a random enemy minion.",
    rarity="Legendary",
    deathrattle=sylvanas_windrunner_deathrattle
)

def cairne_bloodhoof_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deathrattle: Summon a 4/5 Baine Bloodhoof."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Baine Bloodhoof',
                'power': 4,
                'toughness': 5,
                'types': {CardType.MINION},
                'subtypes': set()
            }
        },
        source=obj.id
    )]

CAIRNE_BLOODHOOF = make_minion(
    name="Cairne Bloodhoof",
    attack=4,
    health=5,
    mana_cost="{6}",
    text="Deathrattle: Summon a 4/5 Baine Bloodhoof.",
    rarity="Legendary",
    deathrattle=cairne_bloodhoof_deathrattle
)

def the_black_knight_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Destroy a random enemy minion with Taunt."""
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    valid_targets = []
    for minion_id in battlefield.objects:
        minion = state.objects.get(minion_id)
        if minion and minion.controller != obj.controller:
            if CardType.MINION in minion.characteristics.types:
                if any(a.get('keyword') == 'taunt' for a in (minion.characteristics.abilities or [])):
                    valid_targets.append(minion_id)

    if valid_targets:
        target_id = random.choice(valid_targets)
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id, 'reason': 'the_black_knight'},
            source=obj.id
        )]

    return []

THE_BLACK_KNIGHT = make_minion(
    name="The Black Knight",
    attack=4,
    health=5,
    mana_cost="{6}",
    text="Battlecry: Destroy an enemy minion with Taunt.",
    rarity="Legendary",
    battlecry=the_black_knight_battlecry
)

WINDFURY_HARPY = make_minion(
    name="Windfury Harpy",
    attack=4,
    health=5,
    mana_cost="{6}",
    text="Windfury",
    rarity="Common",
    keywords={"windfury"}
)

# =============================================================================
# Additional Classic Neutral Minions (7+ Cost)
# =============================================================================

RAVENHOLDT_ASSASSIN = make_minion(
    name="Ravenholdt Assassin",
    attack=7,
    health=5,
    mana_cost="{7}",
    text="Stealth",
    rarity="Rare",
    keywords={"stealth"}
)

def baron_geddon_setup(obj: GameObject, state: GameState):
    """At the end of your turn, deal 2 damage to ALL other characters."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def aoe_handler(event, s):
        events = []
        battlefield = s.zones.get('battlefield')
        if battlefield:
            for mid in list(battlefield.objects):
                if mid == obj.id:
                    continue
                m = s.objects.get(mid)
                if m and CardType.MINION in m.characteristics.types:
                    events.append(Event(type=EventType.DAMAGE, payload={'target': mid, 'amount': 2, 'source': obj.id}, source=obj.id))
        for pid, player in s.players.items():
            if player.hero_id:
                events.append(Event(type=EventType.DAMAGE, payload={'target': player.hero_id, 'amount': 2, 'source': obj.id}, source=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=end_turn_filter, handler=aoe_handler,
        duration='while_on_battlefield'
    )]

BARON_GEDDON = make_minion(
    name="Baron Geddon",
    attack=7,
    health=5,
    mana_cost="{7}",
    text="At the end of your turn, deal 2 damage to ALL other characters.",
    rarity="Legendary",
    setup_interceptors=baron_geddon_setup
)

def the_beast_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deathrattle: Summon a 3/3 Finkle Einhorn for your opponent."""
    # Find opponent
    opponent_id = None
    for player_id in state.players:
        if player_id != obj.controller:
            opponent_id = player_id
            break

    if not opponent_id:
        return []

    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': opponent_id,
            'token': {
                'name': 'Finkle Einhorn',
                'power': 3,
                'toughness': 3,
                'types': {CardType.MINION},
                'subtypes': set()
            }
        },
        source=obj.id
    )]

THE_BEAST = make_minion(
    name="The Beast",
    attack=9,
    health=7,
    mana_cost="{6}",
    subtypes={"Beast"},
    text="Deathrattle: Summon a 3/3 Finkle Einhorn for your opponent.",
    rarity="Legendary",
    deathrattle=the_beast_deathrattle
)

def gruul_setup(obj: GameObject, state: GameState):
    """At the end of each turn, gain +1/+1."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END

    def grow_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
                source=obj.id)]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=end_turn_filter, handler=grow_handler,
        duration='while_on_battlefield'
    )]

GRUUL = make_minion(
    name="Gruul",
    attack=7,
    health=7,
    mana_cost="{8}",
    text="At the end of each turn, gain +1/+1.",
    rarity="Legendary",
    setup_interceptors=gruul_setup
)

def ragnaros_setup(obj: GameObject, state: GameState):
    """At the end of your turn, deal 8 damage to a random enemy."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def fire_handler(event, s):
        enemies = []
        for pid, player in s.players.items():
            if pid != obj.controller and player.hero_id:
                enemies.append(player.hero_id)
        battlefield = s.zones.get('battlefield')
        if battlefield:
            for mid in battlefield.objects:
                m = s.objects.get(mid)
                if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                    enemies.append(mid)
        if enemies:
            target = random.choice(enemies)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 8, 'source': obj.id}, source=obj.id)]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=end_turn_filter, handler=fire_handler,
        duration='while_on_battlefield'
    )]

RAGNAROS_THE_FIRELORD = make_minion(
    name="Ragnaros the Firelord",
    attack=8,
    health=8,
    mana_cost="{8}",
    text="Can't Attack. At the end of your turn, deal 8 damage to a random enemy.",
    rarity="Legendary",
    setup_interceptors=ragnaros_setup
)

def alexstrasza_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Set a hero's remaining Health to 15."""
    # AI targets the enemy hero if they have more than 15 hp, else self
    for pid, player in state.players.items():
        if pid != obj.controller and player.life > 15:
            damage = player.life - 15
            return [Event(type=EventType.DAMAGE, payload={'target': player.hero_id, 'amount': damage, 'source': obj.id}, source=obj.id)]
    # Otherwise heal self to 15
    player = state.players.get(obj.controller)
    if player and player.life < 15:
        heal = 15 - player.life
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': heal}, source=obj.id)]
    return []

ALEXSTRASZA = make_minion(
    name="Alexstrasza",
    attack=8,
    health=8,
    mana_cost="{9}",
    subtypes={"Dragon"},
    text="Battlecry: Set a hero's remaining Health to 15.",
    rarity="Legendary",
    battlecry=alexstrasza_battlecry
)

def onyxia_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Summon 1/1 Whelps until your side is full."""
    # In Hearthstone, max 7 minions
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    friendly_minions = sum(
        1 for mid in battlefield.objects
        if mid in state.objects
        and state.objects[mid].controller == obj.controller
        and CardType.MINION in state.objects[mid].characteristics.types
    )

    # Onyxia already counts as 1, so summon up to 6 more
    whelps_to_summon = min(6, 7 - friendly_minions)

    events = []
    for _ in range(whelps_to_summon):
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Whelp',
                    'power': 1,
                    'toughness': 1,
                    'types': {CardType.MINION},
                    'subtypes': {'Dragon'}
                }
            },
            source=obj.id
        ))

    return events

ONYXIA = make_minion(
    name="Onyxia",
    attack=8,
    health=8,
    mana_cost="{9}",
    subtypes={"Dragon"},
    text="Battlecry: Summon 1/1 Whelps until your side of the battlefield is full.",
    rarity="Legendary",
    battlecry=onyxia_battlecry
)

MALYGOS = make_minion(
    name="Malygos",
    attack=4,
    health=12,
    mana_cost="{9}",
    subtypes={"Dragon"},
    text="Spell Damage +5",
    rarity="Legendary"
)

def ysera_setup(obj: GameObject, state: GameState):
    """At the end of your turn, add a Dream Card to your hand (simplified: draw a card)."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def dream_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=end_turn_filter, handler=dream_handler,
        duration='while_on_battlefield'
    )]

YSERA = make_minion(
    name="Ysera",
    attack=4,
    health=12,
    mana_cost="{9}",
    subtypes={"Dragon"},
    text="At the end of your turn, add a Dream Card to your hand.",
    rarity="Legendary",
    setup_interceptors=ysera_setup
)

def deathwing_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Destroy all other minions and discard your hand."""
    events = []

    # Destroy all minions except Deathwing
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for minion_id in list(battlefield.objects):
            if minion_id != obj.id:
                minion = state.objects.get(minion_id)
                if minion and CardType.MINION in minion.characteristics.types:
                    events.append(Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': minion_id, 'reason': 'deathwing'},
                        source=obj.id
                    ))

    # Discard hand (simplified - just emit DISCARD event for all cards in hand)
    hand = state.zones.get(f"hand_{obj.controller}")
    if hand:
        for card_id in list(hand.objects):
            if card_id != obj.id:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': obj.controller, 'object_id': card_id},
                    source=obj.id
                ))

    return events

DEATHWING = make_minion(
    name="Deathwing",
    attack=12,
    health=12,
    mana_cost="{10}",
    subtypes={"Dragon"},
    text="Battlecry: Destroy all other minions and discard your hand.",
    rarity="Legendary",
    battlecry=deathwing_battlecry
)

SEA_GIANT = make_minion(
    name="Sea Giant",
    attack=8,
    health=8,
    mana_cost="{10}",
    text="Costs (1) less for each other minion on the battlefield. (Text only)",
    rarity="Epic"
)

MOUNTAIN_GIANT = make_minion(
    name="Mountain Giant",
    attack=8,
    health=8,
    mana_cost="{12}",
    text="Costs (1) less for each other card in your hand. (Text only)",
    rarity="Epic"
)

MOLTEN_GIANT = make_minion(
    name="Molten Giant",
    attack=8,
    health=8,
    mana_cost="{20}",
    text="Costs (1) less for each damage your hero has taken. (Text only)",
    rarity="Epic"
)

DREAD_CORSAIR = make_minion(
    name="Dread Corsair",
    attack=3,
    health=3,
    mana_cost="{4}",
    subtypes={"Pirate"},
    text="Taunt. Costs (1) less per Attack of your weapon. (Text only)",
    rarity="Rare",
    keywords={"taunt"}
)


# =============================================================================
# Card Collections
# =============================================================================

CLASSIC_MINIONS = [
    # 0-Cost
    WISP,
    # 1-Cost
    ABUSIVE_SERGEANT,
    ARGENT_SQUIRE,
    WORGEN_INFILTRATOR,
    YOUNG_PRIESTESS,
    HUNGRY_CRAB,
    # 2-Cost
    ACIDIC_SWAMP_OOZE,
    BLOODFEN_RAPTOR,
    DIRE_WOLF_ALPHA,
    FAERIE_DRAGON,
    KNIFE_JUGGLER,
    LOOT_HOARDER,
    NOVICE_ENGINEER,
    SUNFURY_PROTECTOR,
    WILD_PYROMANCER,
    BLOODMAGE_THALNOS,
    MASTER_SWORDSMITH,
    CRAZED_ALCHEMIST,
    MAD_BOMBER,
    AMANI_BERSERKER,
    MURLOC_TIDEHUNTER,
    MAD_SCIENTIST,
    # 3-Cost
    EARTHEN_RING_FARSEER,
    HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN,
    JUNGLE_PANTHER,
    SCARLET_CRUSADER,
    SHATTERED_SUN_CLERIC,
    QUESTING_ADVENTURER,
    ACOLYTE_OF_PAIN,
    INJURED_BLADEMASTER,
    MIND_CONTROL_TECH,
    COLDLIGHT_ORACLE,
    IMP_MASTER,
    ALARM_O_BOT,
    EMPEROR_COBRA,
    DEMOLISHER,
    RAGING_WORGEN,
    IRONBEAK_OWL,
    WOLFRIDER,
    # 4-Cost
    CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA,
    SILVERMOON_GUARDIAN,
    SPELLBREAKER,
    DARK_IRON_DWARF,
    DEFENDER_OF_ARGUS,
    TWILIGHT_DRAKE,
    ANCIENT_BREWMASTER,
    CULT_MASTER,
    VIOLET_TEACHER,
    ANCIENT_MAGE,
    STORMWIND_KNIGHT,
    WATER_ELEMENTAL,
    DREAD_CORSAIR,
    # 5-Cost
    ABOMINATION,
    STRANGLETHORN_TIGER,
    VENTURE_CO_MERCENARY,
    AZURE_DRAKE,
    STAMPEDING_KODO,
    FACELESS_MANIPULATOR,
    CAPTAIN_GREENSKIN,
    HARRISON_JONES,
    SILVER_HAND_KNIGHT,
    BIG_GAME_HUNTER,
    LEEROY_JENKINS,
    # 6-Cost
    BOULDERFIST_OGRE,
    RECKLESS_ROCKETEER,
    ARGENT_COMMANDER,
    SUNWALKER,
    FROST_ELEMENTAL,
    SYLVANAS_WINDRUNNER,
    CAIRNE_BLOODHOOF,
    THE_BLACK_KNIGHT,
    THE_BEAST,
    WINDFURY_HARPY,
    # 7+ Cost
    RAVENHOLDT_ASSASSIN,
    BARON_GEDDON,
    GRUUL,
    RAGNAROS_THE_FIRELORD,
    ALEXSTRASZA,
    ONYXIA,
    MALYGOS,
    YSERA,
    DEATHWING,
    SEA_GIANT,
    MOUNTAIN_GIANT,
    MOLTEN_GIANT,
]

CLASSIC_SPELLS = [
    ARCANE_MISSILES,
    FIREBALL,
    FLAMESTRIKE,
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
