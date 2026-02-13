"""
Hearthstone Hero Power Cards

Hero powers for the 9 classic heroes.
"""

from src.engine.game import make_hero_power
from src.engine.types import Event, EventType, GameObject, GameState, CardType


# Mage Hero Power
def fireblast_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 1 damage to enemy hero (auto-target for AI)."""
    # Find opponent's hero
    opponent_id = None
    for pid in state.players.keys():
        if pid != obj.controller:
            opponent_id = pid
            break

    if not opponent_id:
        return []

    opponent = state.players[opponent_id]
    if not opponent.hero_id:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': opponent.hero_id, 'amount': 1, 'source': obj.id},
        source=obj.id
    )]

FIREBLAST = make_hero_power(
    name="Fireblast",
    cost=2,
    text="Deal 1 damage",
    effect=fireblast_effect
)


# Warrior Hero Power
def armor_up_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Gain 2 Armor."""
    player = state.players.get(obj.controller)
    if player:
        player.armor += 2
    return [Event(
        type=EventType.ARMOR_GAIN,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id
    )]

ARMOR_UP = make_hero_power(
    name="Armor Up!",
    cost=2,
    text="Gain 2 Armor",
    effect=armor_up_effect
)


# Hunter Hero Power
def steady_shot_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to enemy hero."""
    # Find opponent
    opponent_id = None
    for pid in state.players.keys():
        if pid != obj.controller:
            opponent_id = pid
            break

    if not opponent_id:
        return []

    opponent = state.players[opponent_id]
    if not opponent.hero_id:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': opponent.hero_id, 'amount': 2, 'source': obj.id},
        source=obj.id
    )]

STEADY_SHOT = make_hero_power(
    name="Steady Shot",
    cost=2,
    text="Deal 2 damage to the enemy hero",
    effect=steady_shot_effect
)


# Paladin Hero Power
def reinforce_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a 1/1 Silver Hand Recruit."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Silver Hand Recruit',
                'power': 1,
                'toughness': 1,
                'types': [CardType.MINION],
                'subtypes': set(),
            }
        },
        source=obj.id
    )]

REINFORCE = make_hero_power(
    name="Reinforce",
    cost=2,
    text="Summon a 1/1 Silver Hand Recruit",
    effect=reinforce_effect
)


# Priest Hero Power
def lesser_heal_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Restore 2 Health to own hero (auto-target for AI)."""
    player = state.players.get(obj.controller)
    if not player or not player.hero_id:
        return []

    # Heal hero (can't go above max)
    heal_amount = min(2, 30 - player.life)
    if heal_amount <= 0:
        return []

    # Only return the event - _handle_life_change will apply the change
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': heal_amount},
        source=obj.id
    )]

LESSER_HEAL = make_hero_power(
    name="Lesser Heal",
    cost=2,
    text="Restore 2 Health",
    effect=lesser_heal_effect
)


# Rogue Hero Power
def dagger_mastery_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Equip a 1/2 Dagger."""
    player = state.players.get(obj.controller)
    if not player or not player.hero_id:
        return []

    hero = state.objects.get(player.hero_id)
    if not hero:
        return []

    # Equip dagger (set on player, not hero state)
    player.weapon_attack = 1
    player.weapon_durability = 2

    return [Event(
        type=EventType.WEAPON_EQUIP,
        payload={'hero_id': hero.id, 'attack': 1, 'durability': 2},
        source=obj.id
    )]

DAGGER_MASTERY = make_hero_power(
    name="Dagger Mastery",
    cost=2,
    text="Equip a 1/2 Dagger",
    effect=dagger_mastery_effect
)


# Shaman Hero Power
def totemic_call_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a random Totem."""
    import random
    totems = [
        ('Healing Totem', 0, 2, []),
        ('Searing Totem', 1, 1, []),
        ('Stoneclaw Totem', 0, 2, [{'keyword': 'taunt'}]),
        ('Wrath of Air Totem', 0, 2, []),
    ]
    totem_name, power, toughness, abilities = random.choice(totems)

    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': totem_name,
                'power': power,
                'toughness': toughness,
                'types': [CardType.MINION],
                'subtypes': {'Totem'},
                'abilities': abilities,
            }
        },
        source=obj.id
    )]

TOTEMIC_CALL = make_hero_power(
    name="Totemic Call",
    cost=2,
    text="Summon a random Totem",
    effect=totemic_call_effect
)


# Warlock Hero Power
def life_tap_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Draw a card and take 2 damage."""
    events = []

    # Draw a card
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    ))

    # Take 2 damage to hero
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': player.hero_id, 'amount': 2, 'source': obj.id},
            source=obj.id
        ))

    return events

LIFE_TAP = make_hero_power(
    name="Life Tap",
    cost=2,
    text="Draw a card. Take 2 damage",
    effect=life_tap_effect
)


# Druid Hero Power
def shapeshift_effect(obj: GameObject, state: GameState) -> list[Event]:
    """+1 Attack this turn, +1 Armor."""
    player = state.players.get(obj.controller)
    if not player or not player.hero_id:
        return []

    hero = state.objects.get(player.hero_id)
    if not hero:
        return []

    events = []

    # +1 Attack this turn (temporary, cleared at end of turn)
    player.weapon_attack = 1
    player.weapon_durability = 1  # 1 use only
    player._shapeshift_attack = True  # Mark as temporary for end-of-turn cleanup

    # +1 Armor
    player.armor += 1
    events.append(Event(
        type=EventType.ARMOR_GAIN,
        payload={'player': obj.controller, 'amount': 1},
        source=obj.id
    ))

    return events

SHAPESHIFT = make_hero_power(
    name="Shapeshift",
    cost=2,
    text="+1 Attack this turn. +1 Armor",
    effect=shapeshift_effect
)


# Hero power registry
HERO_POWERS = {
    "Mage": FIREBLAST,
    "Warrior": ARMOR_UP,
    "Hunter": STEADY_SHOT,
    "Paladin": REINFORCE,
    "Priest": LESSER_HEAL,
    "Rogue": DAGGER_MASTERY,
    "Shaman": TOTEMIC_CALL,
    "Warlock": LIFE_TAP,
    "Druid": SHAPESHIFT,
}
