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
                'types': {CardType.MINION},
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

    # Skip if already at max HP
    if player.life >= (getattr(player, 'max_life', 30) or 30):
        return []

    # Emit full heal amount - pipeline's _handle_life_change caps at max_life
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 2},
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

    events = []

    # Destroy existing weapon cards on battlefield (replacing old weapon)
    from src.engine.types import ZoneType
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for card_id in list(battlefield.objects):
            card = state.objects.get(card_id)
            if (card and card.controller == obj.controller and
                    CardType.WEAPON in card.characteristics.types):
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': card_id, 'reason': 'weapon_replaced'},
                    source=obj.id
                ))

    # Equip dagger
    player.weapon_attack = 1
    player.weapon_durability = 2
    hero.state.weapon_attack = 1
    hero.state.weapon_durability = 2

    events.append(Event(
        type=EventType.WEAPON_EQUIP,
        payload={'hero_id': hero.id, 'attack': 1, 'durability': 2},
        source=obj.id
    ))

    return events

DAGGER_MASTERY = make_hero_power(
    name="Dagger Mastery",
    cost=2,
    text="Equip a 1/2 Dagger",
    effect=dagger_mastery_effect
)


# Shaman Hero Power

def healing_totem_setup(obj: GameObject, state: GameState):
    """At the end of your turn, restore 1 Health to all friendly minions."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def end_turn_filter(event, s):
        return (event.type in (EventType.TURN_END, EventType.PHASE_END) and
                event.payload.get('player') == obj.controller)

    def end_turn_handler(event, s):
        battlefield = s.zones.get('battlefield')
        if battlefield:
            for mid in battlefield.objects:
                m = s.objects.get(mid)
                if (m and m.controller == obj.controller and
                        CardType.MINION in m.characteristics.types and
                        m.state.damage > 0):
                    m.state.damage = max(0, m.state.damage - 1)
        # Direct state manipulation - no events needed for minion heal
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


def wrath_of_air_setup(obj: GameObject, state: GameState):
    """Spell Damage +1: All spell damage events from the controller get +1."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def spell_damage_filter(event, s):
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('from_spell'):
            return False
        # Check source spell is controlled by same player
        source_id = event.payload.get('source') or event.source
        source_obj = s.objects.get(source_id)
        if source_obj and source_obj.controller == obj.controller:
            return True
        return False

    def spell_damage_handler(event, s):
        # Boost damage by 1
        modified = Event(
            type=event.type,
            payload={**event.payload, 'amount': event.payload.get('amount', 0) + 1},
            source=event.source,
            controller=event.controller
        )
        modified.timestamp = event.timestamp
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=modified
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=spell_damage_filter,
        handler=spell_damage_handler,
        duration='while_on_battlefield'
    )]


def totemic_call_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a random basic Totem (no duplicates of existing totems)."""
    import random
    totems = [
        ('Healing Totem', 0, 2, [], healing_totem_setup),
        ('Searing Totem', 1, 1, [], None),
        ('Stoneclaw Totem', 0, 2, [{'keyword': 'taunt'}], None),
        ('Wrath of Air Totem', 0, 2, [], wrath_of_air_setup),
    ]

    # Exclude totems already on the battlefield (Hearthstone: no duplicate basic totems)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        existing_names = set()
        for oid in battlefield.objects:
            o = state.objects.get(oid)
            if (o and o.controller == obj.controller and
                    'Totem' in o.characteristics.subtypes):
                existing_names.add(o.name)
        totems = [t for t in totems if t[0] not in existing_names]

    if not totems:
        return []  # All 4 basic totems already on board

    totem_name, power, toughness, abilities, setup_fn = random.choice(totems)

    token_data = {
        'name': totem_name,
        'power': power,
        'toughness': toughness,
        'types': {CardType.MINION},
        'subtypes': {'Totem'},
        'abilities': abilities,
    }
    if setup_fn:
        token_data['setup_interceptors'] = setup_fn

    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': token_data
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
    """Take 2 damage, then draw a card."""
    events = []

    # Take 2 damage to hero first (Hearthstone ordering: damage before draw)
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': player.hero_id, 'amount': 2, 'source': obj.id},
            source=obj.id
        ))

    # Then draw a card
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
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
    # Save pre-Shapeshift weapon state so cleanup can detect weapon replacements
    player._pre_shapeshift_weapon_attack = player.weapon_attack
    player.weapon_attack += 1
    # If no weapon equipped (durability 0), give 1 temporary durability so hero can attack
    if player.weapon_durability <= 0:
        player.weapon_durability = 1
    player._shapeshift_attack = True  # Mark as temporary for end-of-turn cleanup
    hero.state.weapon_attack = player.weapon_attack
    hero.state.weapon_durability = player.weapon_durability

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


# ============================================================================
# SHADOWFORM HERO POWERS (Priest - Shadowform spell upgrades)
# ============================================================================

def mind_spike_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to a random enemy."""
    import random
    from src.cards.interceptor_helpers import get_enemy_targets as _get_enemy_targets
    enemy_targets = _get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 2, 'source': obj.id},
        source=obj.id
    )]

MIND_SPIKE = make_hero_power(
    name="Mind Spike",
    cost=2,
    text="Hero Power: Deal 2 damage.",
    effect=mind_spike_effect
)


def mind_shatter_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 3 damage to a random enemy."""
    import random
    from src.cards.interceptor_helpers import get_enemy_targets as _get_enemy_targets
    enemy_targets = _get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 3, 'source': obj.id},
        source=obj.id
    )]

MIND_SHATTER = make_hero_power(
    name="Mind Shatter",
    cost=2,
    text="Hero Power: Deal 3 damage.",
    effect=mind_shatter_effect
)


# ============================================================================
# INFERNO HERO POWER (Warlock - Lord Jaraxxus)
# ============================================================================

def inferno_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a 6/6 Infernal."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Infernal',
                'power': 6,
                'toughness': 6,
                'types': {CardType.MINION},
                'subtypes': {'Demon'},
            }
        },
        source=obj.id
    )]

INFERNO_HERO_POWER = make_hero_power(
    name="INFERNO!",
    cost=2,
    text="Hero Power: Summon a 6/6 Infernal.",
    effect=inferno_effect
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
