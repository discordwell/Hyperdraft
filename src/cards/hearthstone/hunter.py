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
            # Set health to 1: reduce toughness and clear excess damage
            target_obj.characteristics.toughness = 1
            target_obj.state.damage = 0
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
    return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]


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
    from src.cards.hearthstone.tokens import leokk_setup
    choice = random.choice(['huffer', 'leokk', 'misha'])
    if choice == 'huffer':
        token = {'name': 'Huffer', 'power': 4, 'toughness': 2, 'types': {CardType.MINION}, 'subtypes': {'Beast'}, 'keywords': {'charge'}}
    elif choice == 'leokk':
        token = {'name': 'Leokk', 'power': 2, 'toughness': 4, 'types': {CardType.MINION}, 'subtypes': {'Beast'}, 'setup_interceptors': leokk_setup}
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
            Event(type=EventType.KEYWORD_GRANT, payload={'object_id': target, 'keyword': 'taunt', 'duration': 'permanent'}, source=obj.id)
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
def tundra_rhino_setup(obj, state):
    """Your Beasts have Charge — grant charge and remove summoning sickness from friendly Beasts."""
    def beast_charge_filter(event, s):
        if event.type != EventType.ZONE_CHANGE:
            return False
        summoned_id = event.payload.get('object_id')
        summoned = s.objects.get(summoned_id)
        return (summoned and summoned.controller == obj.controller and
                'Beast' in summoned.characteristics.subtypes)

    def beast_charge_handler(event, s):
        summoned_id = event.payload.get('object_id')
        summoned = s.objects.get(summoned_id)
        if summoned:
            if not any(a.get('keyword') == 'charge' for a in (summoned.characteristics.abilities or [])):
                summoned.characteristics.abilities.append({'keyword': 'charge'})
            summoned.state.summoning_sickness = False
        return InterceptorResult(action=InterceptorAction.REACT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=beast_charge_filter,
        handler=beast_charge_handler,
        duration='while_on_battlefield'
    )]

TUNDRA_RHINO = make_minion(
    name="Tundra Rhino",
    attack=2,
    health=5,
    mana_cost="{5}",
    subtypes={'Beast'},
    text="Your Beasts have Charge.",
    setup_interceptors=tundra_rhino_setup
)


# 10. STARVING_BUZZARD - 3/2 Beast, cost 5, Whenever you summon a Beast, draw a card
def starving_buzzard_setup(obj, state):
    def trigger_fn(event, state):
        if event.type == EventType.ZONE_CHANGE:
            summoned_id = event.payload.get('object_id')
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
    if not targets:
        return []
    target_id = targets[0]
    target_obj = state.objects.get(target_id)
    if not target_obj or 'Beast' not in target_obj.characteristics.subtypes:
        return []

    events = [Event(type=EventType.PT_MODIFICATION, payload={'object_id': target_id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'}, source=obj.id)]

    # Grant Immune keyword until end of turn
    if not target_obj.characteristics.abilities:
        target_obj.characteristics.abilities = []
    target_obj.characteristics.abilities.append({'keyword': 'immune'})

    # Register end-of-turn cleanup to remove Immune
    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def end_turn_handler(event, s):
        t = s.objects.get(target_id)
        if t and t.characteristics.abilities:
            t.characteristics.abilities = [a for a in t.characteristics.abilities if a.get('keyword') != 'immune']
        # Self-remove this interceptor
        int_id = end_turn_handler._interceptor_id
        if int_id in s.interceptors:
            del s.interceptors[int_id]
        return InterceptorResult(action=InterceptorAction.REACT)

    int_obj = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_turn_filter,
        handler=end_turn_handler,
        duration='until_end_of_turn'
    )
    end_turn_handler._interceptor_id = int_obj.id
    state.interceptors[int_obj.id] = int_obj

    return events


BESTIAL_WRATH = make_spell(
    name="Bestial Wrath",
    mana_cost="{1}",
    text="Give a friendly Beast +2 Attack and Immune this turn.",
    requires_target=True,
    spell_effect=bestial_wrath_effect
)


# 2. EXPLOSIVE_TRAP - 2 mana Secret, When your hero is attacked, deal 2 damage to all enemies
def _explosive_trap_filter(event, state):
    return event.type == EventType.ATTACK_DECLARED

def _explosive_trap_effect(obj, state):
    events = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in list(battlefield.objects):
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                events.append(Event(type=EventType.DAMAGE, payload={'target': mid, 'amount': 2, 'source': obj.id, 'from_spell': True}, source=obj.id))
    for pid, p in state.players.items():
        if pid != obj.controller and p.hero_id:
            events.append(Event(type=EventType.DAMAGE, payload={'target': p.hero_id, 'amount': 2, 'source': obj.id, 'from_spell': True}, source=obj.id))
    return events

EXPLOSIVE_TRAP = make_secret(
    name="Explosive Trap",
    mana_cost="{2}",
    text="Secret: When your hero is attacked, deal 2 damage to all enemies.",
    trigger_filter=_explosive_trap_filter,
    trigger_effect=_explosive_trap_effect
)


# 3. FREEZING_TRAP - 2 mana Secret, When an enemy minion attacks, return it to its owner's hand. It costs (2) more.
def _freezing_trap_setup(obj, state):
    """Secret: When an enemy minion attacks, return it to its owner's hand. It costs (2) more."""
    import re as _re
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def filter_fn(event, s):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        # Only trigger during opponent's turn
        if s.active_player == obj.controller:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = s.objects.get(attacker_id)
        return attacker and CardType.MINION in attacker.characteristics.types

    def handler_fn(event, s):
        attacker_id = event.payload.get('attacker_id')
        attacker = s.objects.get(attacker_id)
        events = []
        if attacker:
            # Increase cost by 2 before returning
            cost_str = attacker.characteristics.mana_cost or "{0}"
            numbers = _re.findall(r'\{(\d+)\}', cost_str)
            current_cost = sum(int(n) for n in numbers) if numbers else 0
            new_cost = current_cost + 2
            attacker.characteristics.mana_cost = "{" + str(new_cost) + "}"
            events.append(Event(type=EventType.RETURN_TO_HAND, payload={'object_id': attacker_id}, source=obj.id))
        # Destroy the secret after triggering
        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'from_zone_type': obj.zone, 'to_zone_type': ZoneType.GRAVEYARD},
            source=obj.id
        ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=f"secret_{obj.id}", source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=filter_fn, handler=handler_fn,
        duration='while_on_battlefield', uses_remaining=1
    )]

FREEZING_TRAP = make_secret(
    name="Freezing Trap",
    mana_cost="{2}",
    text="Secret: When an enemy minion attacks, return it to its owner's hand. It costs (2) more.",
    setup_interceptors=_freezing_trap_setup
)


# 4. SNIPE - 2 mana Secret, When your opponent plays a minion, deal 4 damage to it
def _snipe_filter(event, state):
    return event.type == EventType.ZONE_CHANGE

def _snipe_effect(obj, state):
    # Deal 4 damage to most recently summoned enemy minion
    battlefield = state.zones.get('battlefield')
    if battlefield:
        enemy_minions = [mid for mid in battlefield.objects
                        if state.objects.get(mid) and state.objects[mid].controller != obj.controller
                        and CardType.MINION in state.objects[mid].characteristics.types]
        if enemy_minions:
            return [Event(type=EventType.DAMAGE, payload={'target': enemy_minions[-1], 'amount': 4, 'source': obj.id, 'from_spell': True}, source=obj.id)]
    return []

SNIPE = make_secret(
    name="Snipe",
    mana_cost="{2}",
    text="Secret: When your opponent plays a minion, deal 4 damage to it.",
    trigger_filter=_snipe_filter,
    trigger_effect=_snipe_effect
)


# 5. SNAKE_TRAP - 2 mana Secret, When a friendly minion is attacked, summon three 1/1 Snakes
def _snake_trap_filter(event, state):
    if event.type != EventType.ATTACK_DECLARED:
        return False
    target_id = event.payload.get('target_id')
    target = state.objects.get(target_id)
    return target and target.controller != state.active_player and CardType.MINION in target.characteristics.types

def _snake_trap_effect(obj, state):
    snake_token = {'name': 'Snake', 'power': 1, 'toughness': 1, 'types': {CardType.MINION}, 'subtypes': {'Beast'}}
    return [
        Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': snake_token}, source=obj.id),
        Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': snake_token}, source=obj.id),
        Event(type=EventType.CREATE_TOKEN, payload={'controller': obj.controller, 'token': snake_token}, source=obj.id),
    ]

SNAKE_TRAP = make_secret(
    name="Snake Trap",
    mana_cost="{2}",
    text="Secret: When one of your minions is attacked, summon three 1/1 Snakes.",
    trigger_filter=_snake_trap_filter,
    trigger_effect=_snake_trap_effect
)


# 6. EAGLEHORN_BOW - 3/2 weapon, cost 3, Whenever a Secret is revealed, gain +1 Durability
def eaglehorn_bow_setup(obj, state):
    """Whenever a friendly Secret is revealed, gain +1 Durability."""
    def secret_filter(event, s):
        # Secrets are removed from play when triggered — look for SECRET_REVEALED or
        # ZONE_CHANGE of a secret leaving the battlefield
        if event.type == EventType.ZONE_CHANGE:
            leaving_id = event.payload.get('object_id')
            leaving = s.objects.get(leaving_id)
            if leaving and leaving.controller == obj.controller:
                if CardType.SPELL in leaving.characteristics.types:
                    if event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD:
                        return True
        return False

    def gain_durability(event, s):
        player = s.players.get(obj.controller)
        if player:
            player.weapon_durability += 1
            hero = s.objects.get(player.hero_id)
            if hero:
                hero.state.weapon_durability = player.weapon_durability
        return InterceptorResult(action=InterceptorAction.REACT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=secret_filter,
        handler=gain_durability,
        duration='while_on_battlefield'
    )]

EAGLEHORN_BOW = make_weapon(
    name="Eaglehorn Bow",
    attack=3,
    durability=2,
    mana_cost="{3}",
    text="Whenever a friendly Secret is revealed, gain +1 Durability.",
    setup_interceptors=eaglehorn_bow_setup
)


# 7. DEADLY_SHOT - 3 mana spell, Destroy a random enemy minion
def deadly_shot_effect(obj, state, targets):
    enemy_minions = get_enemy_minions(obj, state)
    if enemy_minions:
        target = random.choice(enemy_minions)
        return [Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': target, 'reason': 'deadly_shot'}, source=obj.id)]
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
            died_id = event.payload.get('object_id')
            died = state.objects.get(died_id)
            if died and died.controller == obj.controller and 'Beast' in died.characteristics.subtypes:
                return True
        return False

    def effect_fn(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.PT_MODIFICATION, payload={'object_id': obj.id, 'power_mod': 2, 'toughness_mod': 1, 'duration': 'permanent'}, source=obj.id)]
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
def gladiators_longbow_setup(obj, state):
    """Your hero is Immune while attacking."""
    controller_id = obj.controller

    # When hero attacks (ATTACK_DECLARED with hero as attacker), grant Immune
    def attack_filter(event, s):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        player = s.players.get(controller_id)
        return player and attacker_id == player.hero_id

    def attack_handler(event, s):
        player = s.players.get(controller_id)
        if not player or not player.hero_id:
            return InterceptorResult(action=InterceptorAction.REACT)
        hero = s.objects.get(player.hero_id)
        if hero:
            if not hero.characteristics.abilities:
                hero.characteristics.abilities = []
            hero.characteristics.abilities.append({'keyword': 'immune'})

        # Register a one-shot interceptor to remove Immune after combat resolves (after DAMAGE)
        def post_combat_filter(evt, st):
            # Remove immune after any damage event involving the hero as target or after attack completes
            return evt.type == EventType.DAMAGE or evt.type == EventType.TURN_END

        def post_combat_handler(evt, st):
            p = st.players.get(controller_id)
            if p and p.hero_id:
                h = st.objects.get(p.hero_id)
                if h and h.characteristics.abilities:
                    h.characteristics.abilities = [a for a in h.characteristics.abilities if a.get('keyword') != 'immune']
            # Self-remove
            pc_id = post_combat_handler._interceptor_id
            if pc_id in st.interceptors:
                del st.interceptors[pc_id]
            return InterceptorResult(action=InterceptorAction.REACT)

        pc_int = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=controller_id,
            priority=InterceptorPriority.REACT,
            filter=post_combat_filter,
            handler=post_combat_handler,
            duration='once'
        )
        post_combat_handler._interceptor_id = pc_int.id
        s.interceptors[pc_int.id] = pc_int

        return InterceptorResult(action=InterceptorAction.REACT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield'
    )]

GLADIATORS_LONGBOW = make_weapon(
    name="Gladiator's Longbow",
    attack=5,
    durability=2,
    mana_cost="{7}",
    text="Your hero is Immune while attacking.",
    setup_interceptors=gladiators_longbow_setup
)


# 12. FLARE - 2 mana spell, All enemy minions lose Stealth. Destroy all enemy Secrets. Draw a card.
def flare_effect(obj, state, targets):
    """All enemy minions lose Stealth. Destroy all enemy Secrets. Draw a card."""
    events = []

    # Remove Stealth from all enemy minions
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in list(battlefield.objects):
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                if m.state.stealth:
                    m.state.stealth = False

    # Destroy all enemy Secrets (secrets are on the battlefield with SECRET card type)
    if battlefield:
        for oid in list(battlefield.objects):
            o = state.objects.get(oid)
            if o and o.controller != obj.controller and CardType.SECRET in o.characteristics.types:
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': oid, 'reason': 'flare'},
                    source=obj.id
                ))

    # Draw a card
    events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
    return events


FLARE = make_spell(
    name="Flare",
    mana_cost="{2}",
    text="All enemy minions lose Stealth. Destroy all enemy Secrets. Draw a card.",
    spell_effect=flare_effect
)


# 13. MISDIRECTION - 2 mana Secret, When a character attacks your hero, instead it attacks another random character
def _misdirection_filter(event, state):
    if event.type != EventType.ATTACK_DECLARED:
        return False
    target_id = event.payload.get('target_id')
    target = state.objects.get(target_id)
    # Trigger when hero is attacked
    return target and CardType.MINION not in target.characteristics.types

def _misdirection_effect(obj, state):
    """Redirect the attack to a random other character."""
    # Find the attacking character from recent events
    attacker_id = None
    original_target = None
    for event in reversed(state.event_log[-5:]):
        if event.type == EventType.ATTACK_DECLARED:
            attacker_id = event.payload.get('attacker_id')
            original_target = event.payload.get('target_id')
            break

    if not attacker_id:
        return []

    # Get all possible redirect targets (all characters except attacker and original target)
    possible_targets = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for oid in battlefield.objects:
            o = state.objects.get(oid)
            if o and oid != attacker_id and oid != original_target:
                if CardType.MINION in o.characteristics.types:
                    possible_targets.append(oid)

    # Add heroes as possible targets (except original target and attacker)
    for pid, player in state.players.items():
        if player.hero_id and player.hero_id != attacker_id and player.hero_id != original_target:
            possible_targets.append(player.hero_id)

    if not possible_targets:
        return []

    new_target = random.choice(possible_targets)

    # Deal the attacker's damage to the new target
    attacker = state.objects.get(attacker_id)
    if not attacker:
        return []

    # Get attack power from the attacker
    attack_power = 0
    if CardType.MINION in attacker.characteristics.types:
        attack_power = attacker.characteristics.power or 0
    else:
        # Hero - use weapon attack
        for pid, p in state.players.items():
            if p.hero_id == attacker_id:
                attack_power = p.weapon_attack
                break

    if attack_power <= 0:
        return []

    return [Event(type=EventType.DAMAGE, payload={
        'target': new_target,
        'amount': attack_power,
        'source': attacker_id
    }, source=obj.id)]

MISDIRECTION = make_secret(
    name="Misdirection",
    mana_cost="{2}",
    text="Secret: When a character attacks your hero, instead it attacks another random character.",
    trigger_filter=_misdirection_filter,
    trigger_effect=_misdirection_effect
)


# 14. EXPLOSIVE_SHOT - 5 mana spell, Deal 5 damage to a minion and 2 damage to adjacent minions
def explosive_shot_effect(obj, state, targets):
    """Deal 5 damage to a minion and 2 damage to adjacent minions."""
    from src.cards.interceptor_helpers import get_adjacent_enemy_minions
    # Use provided target (targeted spell), fallback to random
    if targets:
        primary = targets[0]
    else:
        enemy_minions = get_enemy_minions(obj, state)
        if not enemy_minions:
            return []
        primary = random.choice(enemy_minions)
    events = [Event(type=EventType.DAMAGE, payload={'target': primary, 'amount': 5, 'source': obj.id, 'from_spell': True}, source=obj.id)]
    # Deal 2 damage to positionally adjacent minions
    adjacent = get_adjacent_enemy_minions(primary, state)
    for adj_id in adjacent:
        events.append(Event(type=EventType.DAMAGE, payload={'target': adj_id, 'amount': 2, 'source': obj.id, 'from_spell': True}, source=obj.id))
    return events


EXPLOSIVE_SHOT = make_spell(
    name="Explosive Shot",
    mana_cost="{5}",
    text="Deal 5 damage to a minion and 2 damage to adjacent minions.",
    spell_effect=explosive_shot_effect
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
    FLARE,
    MISDIRECTION,
    EXPLOSIVE_SHOT,
]

HUNTER_CARDS = HUNTER_BASIC + HUNTER_CLASSIC
