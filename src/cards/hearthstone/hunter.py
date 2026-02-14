"""Hearthstone Hunter Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon, make_secret
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorResult, InterceptorAction, new_id
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_all_minions, get_enemy_hero_id,
    get_friendly_minions, other_friendly_minions, make_static_pt_boost
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _beast_filter(source):
    """Filter for other friendly Beasts"""
    def filter_fn(target, state):
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                'Beast' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def _has_friendly_beast(controller, state):
    """Check if controller has a Beast on battlefield"""
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller == controller and CardType.MINION in m.characteristics.types:
                if 'Beast' in m.characteristics.subtypes:
                    return True
    return False


# ============================================================================
# BASIC HUNTER CARDS
# ============================================================================

# 1. ARCANE_SHOT - 1 mana spell, Deal 2 damage
def arcane_shot_effect(obj, state, targets):
    if targets:
        return [Event(type=EventType.DAMAGE, payload={'target': targets[0], 'amount': 2, 'source': obj.id, 'from_spell': True}, source=obj.id)]
    return []


ARCANE_SHOT = make_spell(
    name="Arcane Shot",
    mana_cost="{1}",
    text="Deal 2 damage.",
    requires_target=True,
    spell_effect=arcane_shot_effect
)


# 2. HUNTERS_MARK - 1 mana spell, Change a minion's Health to 1
def hunters_mark_effect(obj, state, targets):
    if targets:
        target_obj = state.objects.get(targets[0])
        if target_obj and CardType.MINION in target_obj.characteristics.types:
            damage = target_obj.characteristics.toughness - 1
            if damage > 0:
                return [Event(type=EventType.DAMAGE, payload={'target': targets[0], 'amount': damage, 'source': obj.id, 'from_spell': True}, source=obj.id)]
    return []


HUNTERS_MARK = make_spell(
    name="Hunter's Mark",
    mana_cost="{1}",
    text="Change a minion's Health to 1.",
    requires_target=True,
    spell_effect=hunters_mark_effect
)


# 3. TIMBER_WOLF - 1/1 Beast, cost 1, Your other Beasts have +1 Attack
def timber_wolf_setup(obj, state):
    return make_static_pt_boost(obj, power_mod=1, toughness_mod=0, affects_filter=_beast_filter(obj))


TIMBER_WOLF = make_minion(
    name="Timber Wolf",
    attack=1,
    health=1,
    mana_cost="{1}",
    subtypes={'Beast'},
    text="Your other Beasts have +1 Attack.",
    setup_interceptors=timber_wolf_setup
)


# 4. TRACKING - 1 mana spell, Draw a card (Simplified from look at top 3 choose 1)
def tracking_effect(obj, state, targets):
    return [Event(type=EventType.DRAW, payload={'player': obj.controller}, source=obj.id)]


TRACKING = make_spell(
    name="Tracking",
    mana_cost="{1}",
    text="Draw a card.",
    spell_effect=tracking_effect
)


# 5. KILL_COMMAND - 3 mana spell, Deal 3 damage. If you have a Beast, deal 5 instead
def kill_command_effect(obj, state, targets):
    if targets:
        has_beast = _has_friendly_beast(obj.controller, state)
        damage = 5 if has_beast else 3
        return [Event(type=EventType.DAMAGE, payload={'target': targets[0], 'amount': damage, 'source': obj.id, 'from_spell': True}, source=obj.id)]
    return []


KILL_COMMAND = make_spell(
    name="Kill Command",
    mana_cost="{3}",
    text="Deal 3 damage. If you have a Beast, deal 5 instead.",
    requires_target=True,
    spell_effect=kill_command_effect
)


# 6. ANIMAL_COMPANION - 3 mana spell, Summon a random Beast companion
def animal_companion_effect(obj, state, targets):
    choice = random.choice(['huffer', 'leokk', 'misha'])
    if choice == 'huffer':
        token = {'name': 'Huffer', 'power': 4, 'toughness': 2, 'types': {CardType.MINION}, 'subtypes': {'Beast'}, 'keywords': {'charge'}}
    elif choice == 'leokk':
        token = {'name': 'Leokk', 'power': 2, 'toughness': 4, 'types': {CardType.MINION}, 'subtypes': {'Beast'}}
    else:  # misha
        token = {'name': 'Misha', 'power': 4, 'toughness': 4, 'types': {CardType.MINION}, 'subtypes': {'Beast'}, 'keywords': {'taunt'}}
    return [Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': token}, source=obj.id)]


ANIMAL_COMPANION = make_spell(
    name="Animal Companion",
    mana_cost="{3}",
    text="Summon a random Beast companion (Huffer 4/2 Charge, Leokk 2/4 +1 Attack to others, or Misha 4/4 Taunt).",
    spell_effect=animal_companion_effect
)


# 7. HOUNDMASTER - 4/3, cost 4, Battlecry: Give a friendly Beast +2/+2 and Taunt
def houndmaster_battlecry(obj, state):
    friendly = get_friendly_minions(obj, state)
    beasts = [mid for mid in friendly if mid != obj.id and 'Beast' in state.objects.get(mid, obj).characteristics.subtypes]
    if beasts:
        target = random.choice(beasts)
        return [
            Event(type=EventType.PT_MODIFICATION, payload={'object_id': target, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'}, source=obj.id),
            Event(type=EventType.KEYWORD_GRANT, payload={'target': target, 'keyword': 'taunt'}, source=obj.id)
        ]
    return []


HOUNDMASTER = make_minion(
    name="Houndmaster",
    attack=4,
    health=3,
    mana_cost="{4}",
    text="Battlecry: Give a friendly Beast +2/+2 and Taunt.",
    battlecry=houndmaster_battlecry
)


# 8. MULTI_SHOT - 4 mana spell, Deal 3 damage to 2 random enemy minions
def multi_shot_effect(obj, state, targets):
    enemy_minions = get_enemy_minions(obj, state)
    if len(enemy_minions) >= 2:
        targets = random.sample(enemy_minions, 2)
        return [
            Event(type=EventType.DAMAGE, payload={'target': targets[0], 'amount': 3, 'source': obj.id, 'from_spell': True}, source=obj.id),
            Event(type=EventType.DAMAGE, payload={'target': targets[1], 'amount': 3, 'source': obj.id, 'from_spell': True}, source=obj.id)
        ]
    elif len(enemy_minions) == 1:
        return [Event(type=EventType.DAMAGE, payload={'target': enemy_minions[0], 'amount': 3, 'source': obj.id, 'from_spell': True}, source=obj.id)]
    return []


MULTI_SHOT = make_spell(
    name="Multi-Shot",
    mana_cost="{4}",
    text="Deal 3 damage to 2 random enemy minions.",
    spell_effect=multi_shot_effect
)


# 9. TUNDRA_RHINO - 2/5 Beast, cost 5, Your Beasts have Charge
TUNDRA_RHINO = make_minion(
    name="Tundra Rhino",
    attack=2,
    health=5,
    mana_cost="{5}",
    subtypes={'Beast'},
    text="Your Beasts have Charge."
)


# 10. STARVING_BUZZARD - 3/2 Beast, cost 5, Whenever you summon a Beast, draw a card
def starving_buzzard_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.ZONE_CHANGE:
            summoned_id = event.payload.get('minion_id')
            summoned = state.objects.get(summoned_id)
            if summoned and summoned.controller == obj.controller and 'Beast' in summoned.characteristics.subtypes:
                return True
        return False

    def effect_fn(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={'player': obj.controller}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_fn,
        handler=effect_fn,
        duration='while_on_battlefield'
    )]


STARVING_BUZZARD = make_minion(
    name="Starving Buzzard",
    attack=3,
    health=2,
    mana_cost="{5}",
    subtypes={'Beast'},
    text="Whenever you summon a Beast, draw a card.",
    setup_interceptors=starving_buzzard_setup
)


# 11. SAVANNAH_HIGHMANE - 6/5 Beast, cost 6, Deathrattle: Summon two 2/2 Hyenas
SAVANNAH_HIGHMANE = make_minion(
    name="Savannah Highmane",
    attack=6,
    health=5,
    mana_cost="{6}",
    subtypes={'Beast'},
    text="Deathrattle: Summon two 2/2 Hyenas.",
    deathrattle=lambda obj, state: [
        Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': {'name': 'Hyena', 'power': 2, 'toughness': 2, 'types': {CardType.MINION}, 'subtypes': {'Beast'}}}, source=obj.id),
        Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': {'name': 'Hyena', 'power': 2, 'toughness': 2, 'types': {CardType.MINION}, 'subtypes': {'Beast'}}}, source=obj.id),
    ]
)


# ============================================================================
# CLASSIC HUNTER CARDS
# ============================================================================

# 1. BESTIAL_WRATH - 1 mana spell, Give a friendly Beast +2 Attack and Immune this turn
def bestial_wrath_effect(obj, state, targets):
    if targets:
        target_obj = state.objects.get(targets[0])
        if target_obj and 'Beast' in target_obj.characteristics.subtypes:
            return [Event(type=EventType.PT_MODIFICATION, payload={'target': targets[0], 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'}, source=obj.id)]
    return []


BESTIAL_WRATH = make_spell(
    name="Bestial Wrath",
    mana_cost="{1}",
    text="Give a friendly Beast +2 Attack and Immune this turn.",
    requires_target=True,
    spell_effect=bestial_wrath_effect
)


# 2. EXPLOSIVE_TRAP - 2 mana Secret, When your hero is attacked, deal 2 damage to all enemies
def explosive_trap_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.ATTACK_DECLARED:
            player = state.players.get(obj.controller)
            if player and event.payload.get('target') == player.hero_id:
                return True
        return False

    def effect_fn(event, state):
        events = []
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for mid in list(battlefield.objects):
                m = state.objects.get(mid)
                if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                    events.append(Event(type=EventType.DAMAGE, payload={'target': mid, 'amount': 2, 'source': obj.id}, source=obj.id))
        for pid, p in state.players.items():
            if pid != obj.controller and p.hero_id:
                events.append(Event(type=EventType.DAMAGE, payload={'target': p.hero_id, 'amount': 2, 'source': obj.id}, source=obj.id))
        if events:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=events)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_fn,
        handler=effect_fn,
        duration='while_on_battlefield'
    )]


EXPLOSIVE_TRAP = make_secret(
    name="Explosive Trap",
    mana_cost="{2}",
    text="Secret: When your hero is attacked, deal 2 damage to all enemies.",
    setup_interceptors=explosive_trap_setup
)


# 3. FREEZING_TRAP - 2 mana Secret, When an enemy minion attacks, return it to its owner's hand
def freezing_trap_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.ATTACK_DECLARED:
            attacker_id = event.payload.get('attacker')
            attacker = state.objects.get(attacker_id)
            if attacker and attacker.controller != obj.controller and CardType.MINION in attacker.characteristics.types:
                return True
        return False

    def effect_fn(event, state):
        attacker_id = event.payload.get('attacker')
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.RETURN_TO_HAND, payload={'target': attacker_id}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_fn,
        handler=effect_fn,
        duration='while_on_battlefield'
    )]


FREEZING_TRAP = make_secret(
    name="Freezing Trap",
    mana_cost="{2}",
    text="Secret: When an enemy minion attacks, return it to its owner's hand. It costs (2) more.",
    setup_interceptors=freezing_trap_setup
)


# 4. SNIPE - 2 mana Secret, When your opponent plays a minion, deal 4 damage to it
def snipe_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.ZONE_CHANGE:
            summoned_id = event.payload.get('minion_id')
            summoned = state.objects.get(summoned_id)
            if summoned and summoned.controller != obj.controller:
                return True
        return False

    def effect_fn(event, state):
        summoned_id = event.payload.get('minion_id')
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DAMAGE, payload={'target': summoned_id, 'amount': 4, 'source': obj.id}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_fn,
        handler=effect_fn,
        duration='while_on_battlefield'
    )]


SNIPE = make_secret(
    name="Snipe",
    mana_cost="{2}",
    text="Secret: When your opponent plays a minion, deal 4 damage to it.",
    setup_interceptors=snipe_setup
)


# 5. SNAKE_TRAP - 2 mana Secret, When a friendly minion is attacked, summon three 1/1 Snakes
def snake_trap_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.ATTACK_DECLARED:
            target_id = event.payload.get('target')
            target = state.objects.get(target_id)
            if target and target.controller == obj.controller and CardType.MINION in target.characteristics.types:
                return True
        return False

    def effect_fn(event, state):
        snake_token = {'name': 'Snake', 'power': 1, 'toughness': 1, 'types': {CardType.MINION}, 'subtypes': {'Beast'}}
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': snake_token}, source=obj.id),
                Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': snake_token}, source=obj.id),
                Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': snake_token}, source=obj.id),
            ]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_fn,
        handler=effect_fn,
        duration='while_on_battlefield'
    )]


SNAKE_TRAP = make_secret(
    name="Snake Trap",
    mana_cost="{2}",
    text="Secret: When one of your minions is attacked, summon three 1/1 Snakes.",
    setup_interceptors=snake_trap_setup
)


# 6. EAGLEHORN_BOW - 3/2 weapon, cost 3, Whenever a Secret is revealed, gain +1 Durability
EAGLEHORN_BOW = make_weapon(
    name="Eaglehorn Bow",
    attack=3,
    durability=2,
    mana_cost="{3}",
    text="Whenever a friendly Secret is revealed, gain +1 Durability."
)


# 7. DEADLY_SHOT - 3 mana spell, Destroy a random enemy minion
def deadly_shot_effect(obj, state, targets):
    enemy_minions = get_enemy_minions(obj, state)
    if enemy_minions:
        target = random.choice(enemy_minions)
        return [Event(type=EventType.OBJECT_DESTROYED, payload={'target': target}, source=obj.id)]
    return []


DEADLY_SHOT = make_spell(
    name="Deadly Shot",
    mana_cost="{3}",
    text="Destroy a random enemy minion.",
    spell_effect=deadly_shot_effect
)


# 8. UNLEASH_THE_HOUNDS - 3 mana spell, For each enemy minion, summon a 1/1 Hound with Charge
def unleash_the_hounds_effect(obj, state, targets):
    enemy_minions = get_enemy_minions(obj, state)
    hound_token = {'name': 'Hound', 'power': 1, 'toughness': 1, 'types': {CardType.MINION}, 'subtypes': {'Beast'}, 'keywords': {'charge'}}
    return [Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': hound_token}, source=obj.id) for _ in enemy_minions]


UNLEASH_THE_HOUNDS = make_spell(
    name="Unleash the Hounds",
    mana_cost="{3}",
    text="For each enemy minion, summon a 1/1 Hound with Charge.",
    spell_effect=unleash_the_hounds_effect
)


# 9. SCAVENGING_HYENA - 2/2 Beast, cost 2, Whenever a friendly Beast dies, gain +2/+1
def scavenging_hyena_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.OBJECT_DESTROYED:
            died_id = event.payload.get('permanent_id')
            died = state.objects.get(died_id)
            if died and died.controller == obj.controller and 'Beast' in died.characteristics.subtypes:
                return True
        return False

    def effect_fn(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.PT_MODIFICATION, payload={'target': obj.id, 'power': 2, 'toughness': 1, 'duration': 'permanent'}, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_fn,
        handler=effect_fn,
        duration='while_on_battlefield'
    )]


SCAVENGING_HYENA = make_minion(
    name="Scavenging Hyena",
    attack=2,
    health=2,
    mana_cost="{2}",
    subtypes={'Beast'},
    text="Whenever a friendly Beast dies, gain +2/+1.",
    setup_interceptors=scavenging_hyena_setup
)


# 10. KING_KRUSH - 8/8 Beast Dinosaur, cost 9, Charge (Legendary)
KING_KRUSH = make_minion(
    name="King Krush",
    attack=8,
    health=8,
    mana_cost="{9}",
    subtypes={'Beast', 'Dinosaur'},
    keywords={'charge'},
    text="Charge."
)


# 11. GLADIATORS_LONGBOW - 5/2 weapon, cost 7, Your hero is Immune while attacking
GLADIATORS_LONGBOW = make_weapon(
    name="Gladiator's Longbow",
    attack=5,
    durability=2,
    mana_cost="{7}",
    text="Your hero is Immune while attacking."
)


# ============================================================================
# CARD LISTS
# ============================================================================

HUNTER_BASIC = [
    ARCANE_SHOT,
    HUNTERS_MARK,
    TIMBER_WOLF,
    TRACKING,
    KILL_COMMAND,
    ANIMAL_COMPANION,
    HOUNDMASTER,
    MULTI_SHOT,
    TUNDRA_RHINO,
    STARVING_BUZZARD,
    SAVANNAH_HIGHMANE,
]

HUNTER_CLASSIC = [
    BESTIAL_WRATH,
    EXPLOSIVE_TRAP,
    FREEZING_TRAP,
    SNIPE,
    SNAKE_TRAP,
    EAGLEHORN_BOW,
    DEADLY_SHOT,
    UNLEASH_THE_HOUNDS,
    SCAVENGING_HYENA,
    KING_KRUSH,
    GLADIATORS_LONGBOW,
]

HUNTER_CARDS = HUNTER_BASIC + HUNTER_CLASSIC
