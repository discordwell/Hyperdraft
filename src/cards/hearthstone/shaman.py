"""Hearthstone Shaman Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_all_minions,
    get_enemy_hero_id, other_friendly_minions, make_static_pt_boost,
    make_end_of_turn_trigger
)


# ============================================================================
# BASIC SHAMAN CARDS
# ============================================================================

def totemic_might_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give your Totems +2 Health."""
    events = []
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    for mid in friendly:
        m = state.objects.get(mid)
        if m and 'Totem' in m.characteristics.subtypes:
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': mid, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
                source=obj.id
            ))
    return events

TOTEMIC_MIGHT = make_spell(
    name="Totemic Might",
    mana_cost="{0}",
    text="Give your Totems +2 Health.",
    spell_effect=totemic_might_effect
)


def frost_shock_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 1 damage to an enemy character and Freeze it."""
    enemies = get_enemy_targets(obj, state)
    events = []
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': target},
            source=obj.id
        ))
    return events


FROST_SHOCK = make_spell(
    name="Frost Shock",
    mana_cost="{1}",
    text="Deal 1 damage to an enemy character and Freeze it.",
    spell_effect=frost_shock_effect
)


def rockbiter_weapon_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give a friendly character +3 Attack this turn."""
    friendly_targets = get_friendly_minions(obj, state, exclude_self=False)
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        friendly_targets.append(player.hero_id)  # Can target own hero
    events = []
    if friendly_targets:
        target = random.choice(friendly_targets)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        ))
    return events


ROCKBITER_WEAPON = make_spell(
    name="Rockbiter Weapon",
    mana_cost="{1}",
    text="Give a friendly character +3 Attack this turn.",
    spell_effect=rockbiter_weapon_effect
)


def windfury_spell_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give a friendly minion Windfury."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target_id = random.choice(friendly)
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            target.state.windfury = True
    return []


WINDFURY_SPELL = make_spell(
    name="Windfury",
    mana_cost="{2}",
    text="Give a minion Windfury.",
    spell_effect=windfury_spell_effect
)


def flametongue_totem_setup(obj: GameObject, state: GameState) -> list:
    """Adjacent minions have +2 Attack."""
    from src.cards.interceptor_helpers import get_adjacent_minions

    source_id = obj.id

    def adj_power_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        source = s.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        left, right = get_adjacent_minions(source_id, s)
        return target_id in (left, right)

    def adj_power_handler(event: Event, s: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=source_id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=adj_power_filter,
        handler=adj_power_handler,
        duration='while_on_battlefield'
    )]


FLAMETONGUE_TOTEM = make_minion(
    name="Flametongue Totem",
    attack=0,
    health=3,
    mana_cost="{2}",
    subtypes={"Totem"},
    text="Adjacent minions have +2 Attack.",
    setup_interceptors=flametongue_totem_setup
)


def hex_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Transform a minion into a 0/1 Frog with Taunt."""
    enemies = get_enemy_minions(obj, state)
    if not enemies:
        return []

    target_id = random.choice(enemies)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Transform into Frog
    target.characteristics.power = 0
    target.characteristics.toughness = 1
    target.characteristics.abilities = [{'keyword': 'taunt'}]
    target.characteristics.subtypes = {"Beast"}
    target.name = "Frog"
    target.state.damage = 0
    target.state.divine_shield = False
    target.state.stealth = False
    target.state.windfury = False
    target.state.frozen = False
    target.state.summoning_sickness = True

    if hasattr(target.state, 'pt_modifiers'):
        target.state.pt_modifiers = []

    # Remove all interceptors
    for int_id in list(target.interceptor_ids):
        if int_id in state.interceptors:
            del state.interceptors[int_id]
    target.interceptor_ids.clear()
    target.card_def = None

    return [Event(
        type=EventType.TRANSFORM,
        payload={'object_id': target_id, 'new_name': 'Frog'},
        source=obj.id
    )]


HEX = make_spell(
    name="Hex",
    mana_cost="{3}",
    text="Transform a minion into a 0/1 Frog with Taunt.",
    spell_effect=hex_effect
)


def lightning_bolt_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 3 damage. Overload: (1)."""
    enemies = get_enemy_targets(obj, state)
    events = []

    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 1

    return events


LIGHTNING_BOLT = make_spell(
    name="Lightning Bolt",
    mana_cost="{1}",
    text="Deal 3 damage. Overload: (1).",
    spell_effect=lightning_bolt_effect
)


def feral_spirit_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Summon two 2/3 Spirit Wolves with Taunt. Overload: (2)."""
    events = [
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Spirit Wolf',
                    'power': 2,
                    'toughness': 3,
                    'types': {CardType.MINION},
                    'keywords': {'taunt'}
                }
            },
            source=obj.id
        ),
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Spirit Wolf',
                    'power': 2,
                    'toughness': 3,
                    'types': {CardType.MINION},
                    'keywords': {'taunt'}
                }
            },
            source=obj.id
        )
    ]

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


FERAL_SPIRIT = make_spell(
    name="Feral Spirit",
    mana_cost="{3}",
    text="Summon two 2/3 Spirit Wolves with Taunt. Overload: (2).",
    spell_effect=feral_spirit_effect
)


def lava_burst_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 5 damage. Overload: (2)."""
    enemies = get_enemy_targets(obj, state)
    events = []

    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 5, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


LAVA_BURST = make_spell(
    name="Lava Burst",
    mana_cost="{3}",
    text="Deal 5 damage. Overload: (2).",
    spell_effect=lava_burst_effect
)


def bloodlust_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give your minions +3 Attack this turn."""
    events = []
    for mid in get_friendly_minions(obj, state, exclude_self=False):
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': mid, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        ))
    return events


BLOODLUST = make_spell(
    name="Bloodlust",
    mana_cost="{5}",
    text="Give your minions +3 Attack this turn.",
    spell_effect=bloodlust_effect
)


def fire_elemental_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 3 damage."""
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 3, 'source': obj.id},
            source=obj.id
        )]
    return []


FIRE_ELEMENTAL = make_minion(
    name="Fire Elemental",
    attack=6,
    health=5,
    mana_cost="{6}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 3 damage.",
    battlecry=fire_elemental_effect
)


# ============================================================================
# CLASSIC SHAMAN CARDS
# ============================================================================

def earth_shock_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Silence a minion, then deal 1 damage to it. Overload: (1)."""
    enemies = get_enemy_minions(obj, state)
    events = []

    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': target},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 1

    return events


EARTH_SHOCK = make_spell(
    name="Earth Shock",
    mana_cost="{1}",
    text="Silence a minion, then deal 1 damage to it. Overload: (1).",
    spell_effect=earth_shock_effect
)


def forked_lightning_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 2 damage to 2 random enemy minions. Overload: (2)."""
    enemies = get_enemy_minions(obj, state)
    events = []

    if enemies:
        # Pick up to 2 random targets
        targets_to_hit = random.sample(enemies, min(2, len(enemies)))
        for target in targets_to_hit:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
                source=obj.id
            ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


FORKED_LIGHTNING = make_spell(
    name="Forked Lightning",
    mana_cost="{1}",
    text="Deal 2 damage to 2 random enemy minions. Overload: (2).",
    spell_effect=forked_lightning_effect
)


def lightning_storm_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 2-3 damage to all enemy minions. Overload: (2)."""
    events = []

    for mid in get_enemy_minions(obj, state):
        damage = random.choice([2, 3])
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': mid, 'amount': damage, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


LIGHTNING_STORM = make_spell(
    name="Lightning Storm",
    mana_cost="{3}",
    text="Deal 2-3 damage to all enemy minions. Overload: (2).",
    spell_effect=lightning_storm_effect
)


def stormforged_axe_setup(obj, state):
    # Apply overload immediately when weapon is equipped
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 1
    return []


STORMFORGED_AXE = make_weapon(
    name="Stormforged Axe",
    attack=2,
    durability=3,
    mana_cost="{2}",
    text="Overload: (1).",
    setup_interceptors=stormforged_axe_setup
)


def unbound_elemental_setup(obj, state):
    """Whenever you play a card with Overload, gain +1/+1."""
    def overload_filter(event, s):
        # Trigger when any spell/minion with overload is played by same controller
        if event.type not in (EventType.CAST, EventType.SPELL_CAST, EventType.ZONE_CHANGE):
            return False
        # Check if the source card has overload text (simplified check)
        source_id = event.payload.get('spell_id') or event.payload.get('object_id') or event.source
        source_obj = s.objects.get(source_id)
        if source_obj and source_obj.controller == obj.controller:
            card_def = getattr(source_obj, 'card_def', None)
            if card_def and 'Overload' in (getattr(card_def, 'text', '') or ''):
                return True
        return False

    def gain_stats(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=overload_filter,
        handler=gain_stats,
        duration='while_on_battlefield'
    )]

UNBOUND_ELEMENTAL = make_minion(
    name="Unbound Elemental",
    attack=2,
    health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Whenever you play a card with Overload, gain +1/+1.",
    setup_interceptors=unbound_elemental_setup
)


def mana_tide_totem_setup(obj: GameObject, state: GameState) -> list:
    """At the end of your turn, draw a card."""
    def draw_effect(event: Event, s: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )]

    return [make_end_of_turn_trigger(obj, draw_effect)]


MANA_TIDE_TOTEM = make_minion(
    name="Mana Tide Totem",
    attack=0,
    health=3,
    mana_cost="{3}",
    subtypes={"Totem"},
    text="At the end of your turn, draw a card.",
    setup_interceptors=mana_tide_totem_setup
)


def earth_elemental_on_play(obj: GameObject, state: GameState) -> list[Event]:
    """Overload: (3)."""
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 3
    return []


EARTH_ELEMENTAL = make_minion(
    name="Earth Elemental",
    attack=7,
    health=8,
    mana_cost="{5}",
    subtypes={"Elemental"},
    keywords={"taunt"},
    text="Taunt. Overload: (3).",
    battlecry=earth_elemental_on_play
)


def doomhammer_setup(obj, state):
    """Windfury. Overload: (2). Grant Windfury to hero when equipped."""
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2
        # Grant Windfury to the hero
        hero = state.objects.get(player.hero_id)
        if hero:
            hero.state.windfury = True

    # Interceptor: remove Windfury from hero when weapon is destroyed
    def weapon_break_filter(event, s):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    def weapon_break_handler(event, s):
        p = s.players.get(obj.controller)
        if p:
            h = s.objects.get(p.hero_id)
            if h:
                h.state.windfury = False
        return InterceptorResult(action=InterceptorAction.REACT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=weapon_break_filter,
        handler=weapon_break_handler,
        duration='while_on_battlefield'
    )]


DOOMHAMMER = make_weapon(
    name="Doomhammer",
    attack=2,
    durability=8,
    mana_cost="{5}",
    text="Windfury. Overload: (2).",
    setup_interceptors=doomhammer_setup
)


AL_AKIR_THE_WINDLORD = make_minion(
    name="Al'Akir the Windlord",
    attack=3,
    health=5,
    mana_cost="{8}",
    subtypes={"Elemental"},
    keywords={"charge", "taunt", "windfury", "divine_shield"},
    text="Windfury, Charge, Divine Shield, Taunt.",
)


def far_sight_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Draw a card. It costs (3) less."""
    import re

    # Perform the draw directly (move top card from library to hand)
    lib_key = f"library_{obj.controller}"
    hand_key = f"hand_{obj.controller}"
    library = state.zones.get(lib_key)
    hand = state.zones.get(hand_key)
    if not library or not library.objects or not hand:
        return []

    # Check hand size limit (Hearthstone mode)
    if state.game_mode == "hearthstone" and len(hand.objects) >= state.max_hand_size:
        # Overdraw - burn the card, no cost reduction
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )]

    # Draw the card manually
    card_id = library.objects.pop(0)
    hand.objects.append(card_id)
    card = state.objects.get(card_id)
    if card:
        card.zone = ZoneType.HAND
        card.entered_zone_at = state.timestamp

        # Apply (3) cost reduction by modifying the card's mana_cost directly
        cost_str = card.characteristics.mana_cost or "{0}"
        numbers = re.findall(r'\{(\d+)\}', cost_str)
        current_cost = sum(int(n) for n in numbers)
        new_cost = max(0, current_cost - 3)
        card.characteristics.mana_cost = "{" + str(new_cost) + "}"

    return []


FAR_SIGHT = make_spell(
    name="Far Sight",
    mana_cost="{3}",
    text="Draw a card. It costs (3) less.",
    spell_effect=far_sight_effect
)


def ancestral_spirit_effect(obj, state, targets):
    """Give a minion 'Deathrattle: Resummon this minion.'"""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if not friendly:
        return []
    target_id = targets[0] if targets else random.choice(friendly)
    target = state.objects.get(target_id)
    if not target:
        return []

    # Store the minion's stats for resummon
    stored_name = target.name
    stored_power = target.characteristics.power
    stored_toughness = target.characteristics.toughness
    stored_subtypes = set(target.characteristics.subtypes) if target.characteristics.subtypes else set()
    stored_controller = target.controller

    def dr_filter(event, state):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == target_id

    def resummon(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.CREATE_TOKEN, payload={
                'controller': stored_controller,
                'token': {
                    'name': stored_name,
                    'power': stored_power,
                    'toughness': stored_toughness,
                    'types': {CardType.MINION},
                    'subtypes': stored_subtypes,
                }
            }, source=target_id)]
        )

    interceptor = Interceptor(
        id=new_id(), source=obj.id, controller=stored_controller,
        priority=InterceptorPriority.REACT, filter=dr_filter,
        handler=resummon, duration='once'
    )
    state.interceptors[interceptor.id] = interceptor
    return []

ANCESTRAL_SPIRIT = make_spell(
    name="Ancestral Spirit",
    mana_cost="{2}",
    text="Give a minion \"Deathrattle: Resummon this minion.\"",
    spell_effect=ancestral_spirit_effect
)


def ancestral_healing_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Restore a minion to full Health and give it Taunt."""
    all_minions = get_all_minions(state)
    if not all_minions:
        return []

    target_id = random.choice(all_minions)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = []
    # Heal to full via clearing damage
    if target.state.damage > 0:
        heal_amount = target.state.damage
        target.state.damage = 0
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'target': target_id, 'amount': heal_amount},
            source=obj.id
        ))

    # Grant Taunt via event
    events.append(Event(
        type=EventType.KEYWORD_GRANT,
        payload={'object_id': target_id, 'keyword': 'taunt'},
        source=obj.id
    ))

    return events


ANCESTRAL_HEALING = make_spell(
    name="Ancestral Healing",
    mana_cost="{0}",
    text="Restore a minion to full Health and give it Taunt.",
    spell_effect=ancestral_healing_effect
)


def dust_devil_on_play(obj: GameObject, state: GameState) -> list[Event]:
    """Overload: (2)."""
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2
    return []


DUST_DEVIL = make_minion(
    name="Dust Devil",
    attack=3,
    health=1,
    mana_cost="{1}",
    subtypes={"Elemental"},
    keywords={"windfury"},
    text="Windfury. Overload: (2).",
    battlecry=dust_devil_on_play
)


def windspeaker_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Give a friendly minion Windfury."""
    friendly = get_friendly_minions(obj, state, exclude_self=True)
    if friendly:
        target_id = random.choice(friendly)
        target = state.objects.get(target_id)
        if target:
            target.state.windfury = True
    return []

WINDSPEAKER = make_minion(
    name="Windspeaker",
    attack=3,
    health=3,
    mana_cost="{4}",
    text="Battlecry: Give a friendly minion Windfury.",
    battlecry=windspeaker_battlecry
)


# ============================================================================
# CARD LISTS
# ============================================================================

SHAMAN_BASIC = [
    TOTEMIC_MIGHT,
    FROST_SHOCK,
    ROCKBITER_WEAPON,
    WINDFURY_SPELL,
    FLAMETONGUE_TOTEM,
    HEX,
    LIGHTNING_BOLT,
    FERAL_SPIRIT,
    BLOODLUST,
    FIRE_ELEMENTAL,
]

SHAMAN_CLASSIC = [
    LAVA_BURST,
    EARTH_SHOCK,
    FORKED_LIGHTNING,
    LIGHTNING_STORM,
    STORMFORGED_AXE,
    UNBOUND_ELEMENTAL,
    MANA_TIDE_TOTEM,
    EARTH_ELEMENTAL,
    DOOMHAMMER,
    AL_AKIR_THE_WINDLORD,
    FAR_SIGHT,
    ANCESTRAL_SPIRIT,
    ANCESTRAL_HEALING,
    DUST_DEVIL,
    WINDSPEAKER,
]

SHAMAN_CARDS = SHAMAN_BASIC + SHAMAN_CLASSIC
