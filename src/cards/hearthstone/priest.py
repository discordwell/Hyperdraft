"""Hearthstone Priest Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_all_minions,
    get_enemy_hero_id, make_spell_damage_boost
)
from src.cards.hearthstone.classic import MIND_CONTROL


# ============================================================================
# BASIC PRIEST CARDS
# ============================================================================

def holy_smite_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 2 damage."""
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]
    return []

HOLY_SMITE = make_spell(
    name="Holy Smite",
    mana_cost="{1}",
    text="Deal 2 damage.",
    spell_effect=holy_smite_effect
)


def power_word_shield_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give a minion +2 Health. Draw a card."""
    events = []
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target_id = random.choice(friendly)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target_id, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
            source=obj.id
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    ))
    return events

POWER_WORD_SHIELD = make_spell(
    name="Power Word: Shield",
    mana_cost="{1}",
    text="Give a minion +2 Health. Draw a card.",
    spell_effect=power_word_shield_effect
)


def northshire_cleric_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a minion is healed, draw a card."""
    def heal_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        # Check for minion heal (object_id key) with positive amount
        object_id = event.payload.get('object_id')
        if object_id and object_id in s.objects:
            return event.payload.get('amount', 0) > 0
        return False

    def draw_handler(event: Event, s: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=heal_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )]

NORTHSHIRE_CLERIC = make_minion(
    name="Northshire Cleric",
    attack=1,
    health=3,
    mana_cost="{1}",
    text="Whenever a minion is healed, draw a card.",
    setup_interceptors=northshire_cleric_setup
)


def divine_spirit_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Double a minion's Health."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target_id = random.choice(friendly)
        m = state.objects.get(target_id)
        if m:
            from src.engine.queries import get_toughness
            current_health = get_toughness(m, state) - m.state.damage
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': target_id, 'power_mod': 0, 'toughness_mod': current_health, 'duration': 'permanent'},
                source=obj.id
            )]
    return []

DIVINE_SPIRIT = make_spell(
    name="Divine Spirit",
    mana_cost="{2}",
    text="Double a minion's Health.",
    spell_effect=divine_spirit_effect
)


def shadow_word_pain_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Destroy a minion with 3 or less Attack."""
    enemies = get_enemy_minions(obj, state)
    valid = [mid for mid in enemies if state.objects.get(mid) and state.objects[mid].characteristics.power <= 3]
    if valid:
        target = random.choice(valid)
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target, 'reason': 'shadow_word_pain'},
            source=obj.id
        )]
    return []

SHADOW_WORD_PAIN = make_spell(
    name="Shadow Word: Pain",
    mana_cost="{2}",
    text="Destroy a minion with 3 or less Attack.",
    spell_effect=shadow_word_pain_effect
)


def mind_blast_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 5 damage to the enemy hero."""
    hero_id = get_enemy_hero_id(obj, state)
    if hero_id:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': hero_id, 'amount': 5, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]
    return []

MIND_BLAST = make_spell(
    name="Mind Blast",
    mana_cost="{2}",
    text="Deal 5 damage to the enemy hero.",
    spell_effect=mind_blast_effect
)


def shadow_word_death_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Destroy a minion with 5 or more Attack."""
    enemies = get_enemy_minions(obj, state)
    valid = [mid for mid in enemies if state.objects.get(mid) and state.objects[mid].characteristics.power >= 5]
    if valid:
        target = random.choice(valid)
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target, 'reason': 'shadow_word_death'},
            source=obj.id
        )]
    return []

SHADOW_WORD_DEATH = make_spell(
    name="Shadow Word: Death",
    mana_cost="{3}",
    text="Destroy a minion with 5 or more Attack.",
    spell_effect=shadow_word_death_effect
)


def holy_nova_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 2 damage to all enemy minions. Restore 2 Health to all friendly characters."""
    events = []

    # Damage all enemy minions
    for mid in get_enemy_minions(obj, state):
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': mid, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    # Heal friendly hero
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id
    ))

    # Heal friendly minions (emit events so Northshire Cleric triggers)
    for mid in get_friendly_minions(obj, state, exclude_self=False):
        m = state.objects.get(mid)
        if m and m.state.damage > 0:
            heal_amount = min(m.state.damage, 2)
            m.state.damage -= heal_amount
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'object_id': mid, 'amount': heal_amount},
                source=obj.id
            ))

    return events

HOLY_NOVA = make_spell(
    name="Holy Nova",
    mana_cost="{5}",
    text="Deal 2 damage to all enemy minions. Restore 2 Health to all friendly characters.",
    spell_effect=holy_nova_effect
)


def mind_vision_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Put a copy of a random card in your opponent's hand into your hand."""
    # Find opponent's hand
    for pid in state.players:
        if pid != obj.controller:
            hand_key = f"hand_{pid}"
            hand = state.zones.get(hand_key)
            if hand and hand.objects:
                # Pick a random card from opponent's hand
                card_id = random.choice(list(hand.objects))
                card = state.objects.get(card_id)
                if card and card.card_def:
                    # Create a copy in our hand using ADD_TO_HAND with the card's definition
                    return [Event(
                        type=EventType.ADD_TO_HAND,
                        payload={
                            'player': obj.controller,
                            'card_def': card.card_def
                        },
                        source=obj.id
                    )]
                elif card:
                    # Fallback: create a copy from characteristics if no card_def
                    return [Event(
                        type=EventType.ADD_TO_HAND,
                        payload={
                            'player': obj.controller,
                            'card_def': {
                                'name': card.name,
                                'mana_cost': card.characteristics.mana_cost,
                                'types': set(card.characteristics.types),
                                'subtypes': set(card.characteristics.subtypes) if card.characteristics.subtypes else set(),
                                'power': card.characteristics.power,
                                'toughness': card.characteristics.toughness,
                            }
                        },
                        source=obj.id
                    )]
            break
    return []

MIND_VISION = make_spell(
    name="Mind Vision",
    mana_cost="{1}",
    text="Put a copy of a random card in your opponent's hand into your hand.",
    spell_effect=mind_vision_effect
)


# ============================================================================
# CLASSIC PRIEST CARDS
# ============================================================================

def inner_fire_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Change a minion's Attack to be equal to its Health."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target_id = random.choice(friendly)
        m = state.objects.get(target_id)
        if m:
            from src.engine.queries import get_toughness
            health = get_toughness(m, state) - m.state.damage
            current_attack = m.characteristics.power
            diff = health - current_attack
            if diff != 0:
                return [Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': target_id, 'power_mod': diff, 'toughness_mod': 0, 'duration': 'permanent'},
                    source=obj.id
                )]
    return []

INNER_FIRE = make_spell(
    name="Inner Fire",
    mana_cost="{1}",
    text="Change a minion's Attack to be equal to its Health.",
    spell_effect=inner_fire_effect
)


def silence_spell_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Silence a minion."""
    all_minions = get_all_minions(state)
    if all_minions:
        target = random.choice(all_minions)
        return [Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': target},
            source=obj.id
        )]
    return []

SILENCE_SPELL = make_spell(
    name="Silence",
    mana_cost="{0}",
    text="Silence a minion.",
    spell_effect=silence_spell_effect
)


def lightwell_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the start of your turn, restore 3 Health to a damaged friendly character."""
    def upkeep_filter(event: Event, s: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('player') == obj.controller)

    def heal_handler(event: Event, s: GameState) -> InterceptorResult:
        # Find all damaged friendly characters (minions + hero)
        candidates = []
        for mid in get_friendly_minions(obj, s, exclude_self=False):
            m = s.objects.get(mid)
            if m and m.state.damage > 0:
                candidates.append(('minion', mid))

        player = s.players.get(obj.controller)
        if player and player.life < (getattr(player, 'max_life', 30) or 30):
            candidates.append(('hero', obj.controller))

        if not candidates:
            return InterceptorResult(action=InterceptorAction.PASS)

        choice_type, choice_id = random.choice(candidates)
        if choice_type == 'hero':
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': 3},
                    source=obj.id
                )]
            )
        else:
            m = s.objects[choice_id]
            heal_amount = min(m.state.damage, 3)
            m.state.damage -= heal_amount
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'object_id': choice_id, 'amount': heal_amount},
                    source=obj.id
                )]
            )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=heal_handler,
        duration='while_on_battlefield'
    )]

LIGHTWELL = make_minion(
    name="Lightwell",
    attack=0,
    health=5,
    mana_cost="{2}",
    text="At the start of your turn, restore 3 Health to a damaged friendly character.",
    setup_interceptors=lightwell_setup
)


def shadow_madness_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Gain control of an enemy minion with 3 or less Attack until end of turn."""
    enemy_minions = get_enemy_minions(obj, state)
    valid = [m for m in enemy_minions if state.objects.get(m) and state.objects[m].characteristics.power <= 3]
    if not valid:
        return []
    target_id = random.choice(valid)
    target_obj = state.objects[target_id]
    return [Event(
        type=EventType.GAIN_CONTROL,
        payload={
            'object_id': target_id,
            'new_controller': obj.controller,
            'duration': 'end_of_turn',
            'original_controller': target_obj.controller
        },
        source=obj.id
    )]

SHADOW_MADNESS = make_spell(
    name="Shadow Madness",
    mana_cost="{4}",
    text="Gain control of an enemy minion with 3 or less Attack until end of turn.",
    spell_effect=shadow_madness_effect
)


def holy_fire_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 5 damage. Restore 5 Health to your hero."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 5, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 5},
        source=obj.id
    ))
    return events

HOLY_FIRE = make_spell(
    name="Holy Fire",
    mana_cost="{6}",
    text="Deal 5 damage. Restore 5 Health to your hero.",
    spell_effect=holy_fire_effect
)


def temple_enforcer_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give a friendly minion +3 Health."""
    friendly = get_friendly_minions(obj, state, exclude_self=True)
    if friendly:
        target_id = random.choice(friendly)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target_id, 'power_mod': 0, 'toughness_mod': 3, 'duration': 'permanent'},
            source=obj.id
        )]
    return []

TEMPLE_ENFORCER = make_minion(
    name="Temple Enforcer",
    attack=6,
    health=6,
    mana_cost="{6}",
    text="Battlecry: Give a friendly minion +3 Health.",
    battlecry=temple_enforcer_battlecry
)


def cabal_shadow_priest_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Take control of an enemy minion that has 2 or less Attack (permanently)."""
    enemy_minions = get_enemy_minions(obj, state)
    valid = [m for m in enemy_minions if state.objects.get(m) and state.objects[m].characteristics.power <= 2]
    if not valid:
        return []
    target_id = random.choice(valid)
    return [Event(
        type=EventType.GAIN_CONTROL,
        payload={
            'object_id': target_id,
            'new_controller': obj.controller
        },
        source=obj.id
    )]

CABAL_SHADOW_PRIEST = make_minion(
    name="Cabal Shadow Priest",
    attack=4,
    health=5,
    mana_cost="{6}",
    text="Battlecry: Take control of an enemy minion with 2 or less Attack.",
    battlecry=cabal_shadow_priest_battlecry
)


def prophet_velen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double the damage and healing of your spells and Hero Power."""
    def spell_damage_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('from_spell'):
            return False
        source_id = event.payload.get('source') or event.source
        source = s.objects.get(source_id)
        return source is not None and source.controller == obj.controller

    def double_damage(event: Event, s: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload['amount'] = new_payload.get('amount', 0) * 2
        modified = Event(type=event.type, payload=new_payload, source=event.source)
        modified.timestamp = event.timestamp
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=modified)

    def healing_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False  # Not healing
        source_id = event.source
        source = s.objects.get(source_id)
        return source is not None and source.controller == obj.controller

    def double_healing(event: Event, s: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload['amount'] = new_payload.get('amount', 0) * 2
        modified = Event(type=event.type, payload=new_payload, source=event.source)
        modified.timestamp = event.timestamp
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=modified)

    return [
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM, filter=spell_damage_filter,
            handler=double_damage, duration='while_on_battlefield'
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM, filter=healing_filter,
            handler=double_healing, duration='while_on_battlefield'
        ),
    ]

PROPHET_VELEN = make_minion(
    name="Prophet Velen",
    attack=7,
    health=7,
    mana_cost="{7}",
    rarity="Legendary",
    text="Double the damage and healing of your spells and Hero Power.",
    setup_interceptors=prophet_velen_setup
)


def thoughtsteal_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Copy 2 cards from your opponent's deck and put them into your hand."""
    events = []
    for pid in state.players:
        if pid != obj.controller:
            lib_key = f"library_{pid}"
            library = state.zones.get(lib_key)
            if library and library.objects:
                # Pick up to 2 random cards from opponent's deck (without removing them)
                sample_size = min(2, len(library.objects))
                chosen_ids = random.sample(list(library.objects), sample_size)
                for card_id in chosen_ids:
                    card = state.objects.get(card_id)
                    if card and card.card_def:
                        events.append(Event(
                            type=EventType.ADD_TO_HAND,
                            payload={
                                'player': obj.controller,
                                'card_def': card.card_def
                            },
                            source=obj.id
                        ))
                    elif card:
                        events.append(Event(
                            type=EventType.ADD_TO_HAND,
                            payload={
                                'player': obj.controller,
                                'card_def': {
                                    'name': card.name,
                                    'mana_cost': card.characteristics.mana_cost,
                                    'types': set(card.characteristics.types),
                                    'subtypes': set(card.characteristics.subtypes) if card.characteristics.subtypes else set(),
                                    'power': card.characteristics.power,
                                    'toughness': card.characteristics.toughness,
                                }
                            },
                            source=obj.id
                        ))
            break
    return events

THOUGHTSTEAL = make_spell(
    name="Thoughtsteal",
    mana_cost="{3}",
    text="Copy 2 cards from your opponent's deck and put them into your hand.",
    spell_effect=thoughtsteal_effect
)


def mass_dispel_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Silence all enemy minions. Draw a card."""
    events = []
    for mid in get_enemy_minions(obj, state):
        events.append(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': mid},
            source=obj.id
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    ))
    return events

MASS_DISPEL = make_spell(
    name="Mass Dispel",
    mana_cost="{4}",
    text="Silence all enemy minions. Draw a card.",
    spell_effect=mass_dispel_effect
)


def auchenai_soulpriest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your cards and powers that restore Health now deal damage instead."""
    def healing_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False  # Not healing, nothing to convert
        # Check if the source of this healing is controlled by us
        source_id = event.source
        source = s.objects.get(source_id)
        if source and source.controller == obj.controller:
            return True
        return False

    def convert_to_damage(event: Event, s: GameState) -> InterceptorResult:
        amount = event.payload.get('amount', 0)
        # Determine the target: either a minion (object_id) or a player (player)
        target = event.payload.get('object_id') or event.payload.get('player')
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        # If target is a player ID, find their hero_id for damage targeting
        if target in s.players:
            hero_id = s.players[target].hero_id
            if hero_id:
                target = hero_id
            else:
                return InterceptorResult(action=InterceptorAction.PASS)
        # Replace healing with damage
        new_event = Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': amount, 'source': event.source},
            source=event.source
        )
        return InterceptorResult(action=InterceptorAction.REPLACE, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=healing_filter,
        handler=convert_to_damage, duration='while_on_battlefield'
    )]

AUCHENAI_SOULPRIEST = make_minion(
    name="Auchenai Soulpriest",
    attack=3,
    health=5,
    mana_cost="{4}",
    text="Your cards and powers that restore Health now deal damage instead.",
    setup_interceptors=auchenai_soulpriest_setup
)


def circle_of_healing_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Restore 4 Health to ALL minions."""
    events = []
    for mid in get_all_minions(state):
        m = state.objects.get(mid)
        if m and m.state.damage > 0:
            heal_amount = min(m.state.damage, 4)
            m.state.damage -= heal_amount
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'object_id': mid, 'amount': heal_amount},
                source=obj.id
            ))
    return events

CIRCLE_OF_HEALING = make_spell(
    name="Circle of Healing",
    mana_cost="{0}",
    text="Restore 4 Health to ALL minions.",
    spell_effect=circle_of_healing_effect
)


def lightspawn_setup(obj, state):
    """This minion's Attack is always equal to its Health."""
    def query_power_filter(event, s):
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def set_attack_to_health(event, s):
        source = s.objects.get(obj.id)
        if source:
            health = source.characteristics.toughness - source.state.damage
            new_event = event.copy()
            new_event.payload['value'] = health
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=query_power_filter, handler=set_attack_to_health,
        duration='while_on_battlefield'
    )]

LIGHTSPAWN = make_minion(
    name="Lightspawn",
    attack=0,
    health=5,
    mana_cost="{4}",
    text="This minion's Attack is always equal to its Health.",
    setup_interceptors=lightspawn_setup
)

def mindgames_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Put a copy of a random minion from your opponent's deck into the battlefield."""
    # Find opponent's library and pick a random minion
    for pid in state.players:
        if pid != obj.controller:
            lib_key = f"library_{pid}"
            library = state.zones.get(lib_key)
            if not library:
                continue
            minions = []
            for card_id in library.objects:
                card = state.objects.get(card_id)
                if card and CardType.MINION in card.characteristics.types:
                    minions.append(card)
            if minions:
                chosen = random.choice(minions)
                return [Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        'controller': obj.controller,
                        'token': {
                            'name': chosen.name,
                            'power': chosen.characteristics.power,
                            'toughness': chosen.characteristics.toughness,
                            'types': {CardType.MINION},
                            'subtypes': set(chosen.characteristics.subtypes) if chosen.characteristics.subtypes else set(),
                        }
                    },
                    source=obj.id
                )]
    # No minions found in opponent deck - summon a 0/1 Shadow of Nothing (HS flavor)
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Shadow of Nothing',
                'power': 0,
                'toughness': 1,
                'types': {CardType.MINION},
            }
        },
        source=obj.id
    )]

MINDGAMES = make_spell(
    name="Mindgames",
    mana_cost="{4}",
    text="Put a copy of a random minion from your opponent's deck into the battlefield.",
    spell_effect=mindgames_effect
)


def shadowform_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Your Hero Power becomes 'Deal 2 damage'. If already in Shadowform, becomes 'Deal 3 damage'."""
    from src.engine.types import Characteristics, ObjectState
    from src.cards.hearthstone.hero_powers import MIND_SPIKE, MIND_SHATTER

    player = state.players.get(obj.controller)
    if not player or not player.hero_power_id:
        return []

    current_hp = state.objects.get(player.hero_power_id)

    # Check if already in Shadowform (Mind Spike -> upgrade to Mind Shatter)
    if current_hp and current_hp.name == "Mind Spike":
        new_hp_def = MIND_SHATTER
    else:
        new_hp_def = MIND_SPIKE

    # Remove old hero power interceptors from state
    if current_hp:
        for iid in list(current_hp.interceptor_ids):
            state.interceptors.pop(iid, None)

    # Create new hero power object
    new_hp_id = new_id()
    new_hp = GameObject(
        id=new_hp_id,
        name=new_hp_def.name,
        owner=obj.controller,
        controller=obj.controller,
        zone=ZoneType.COMMAND,
        characteristics=Characteristics(
            types={CardType.HERO_POWER},
            mana_cost=new_hp_def.mana_cost,
        ),
        state=ObjectState(),
        card_def=new_hp_def,
        created_at=state.next_timestamp(),
        entered_zone_at=state.timestamp,
    )
    state.objects[new_hp_id] = new_hp

    # Run setup_interceptors from the hero power definition to register its activation handler
    if new_hp_def.setup_interceptors:
        interceptors = new_hp_def.setup_interceptors(new_hp, state)
        for interceptor in (interceptors or []):
            interceptor.timestamp = state.next_timestamp()
            state.interceptors[interceptor.id] = interceptor
            new_hp.interceptor_ids.append(interceptor.id)

    # Update player's hero power reference
    player.hero_power_id = new_hp_id
    player.hero_power_used = False  # Reset hero power usage for the new power
    return []

SHADOWFORM = make_spell(
    name="Shadowform",
    mana_cost="{3}",
    text="Your Hero Power becomes 'Deal 2 damage'.",
    spell_effect=shadowform_effect
)


# ============================================================================
# EXPORTS
# ============================================================================

PRIEST_BASIC = [
    HOLY_SMITE,
    POWER_WORD_SHIELD,
    NORTHSHIRE_CLERIC,
    DIVINE_SPIRIT,
    SHADOW_WORD_PAIN,
    SHADOW_WORD_DEATH,
    HOLY_NOVA,
    MIND_CONTROL,  # Re-exported from classic.py
    MIND_BLAST,
    MIND_VISION,
]

PRIEST_CLASSIC = [
    INNER_FIRE,
    SILENCE_SPELL,
    LIGHTWELL,
    SHADOW_MADNESS,
    HOLY_FIRE,
    TEMPLE_ENFORCER,
    CABAL_SHADOW_PRIEST,
    PROPHET_VELEN,
    THOUGHTSTEAL,
    MASS_DISPEL,
    AUCHENAI_SOULPRIEST,
    CIRCLE_OF_HEALING,
    LIGHTSPAWN,
    MINDGAMES,
    SHADOWFORM,
]

PRIEST_CARDS = PRIEST_BASIC + PRIEST_CLASSIC
