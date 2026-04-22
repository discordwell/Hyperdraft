"""
STORMRIFT - A Hybrid MTG/Hearthstone Game Mode

In the Stormrift, elemental storms tear open rifts between realities.
Two factions battle for control of the rift nexus:

  PYROMANCER - Fire & Storm. Aggressive, spell-synergy, burn damage.
  CRYOMANCER - Ice & Void. Control, card advantage, defensive value.

Global Modifiers (installed at game start):
  1. Rift Storm   - Start of each turn, deal 1 damage to ALL minions.
  2. Soul Residue - First minion to die each turn creates a 1/1 Spirit for owner.
  3. Arcane Feedback - Whenever a spell is cast, deal 1 damage to a random enemy minion.

Two classes, 30-card decks, custom heroes + hero powers.

=== LEGENDARY DESIGN BAR ===
Every legendary (and top epic) in this set must *fundamentally alter* the
game rather than being a bigger vanilla ETB. See the "rubric" in the card
docstrings: alt win conditions, resource-axis breaks, persistent state
modifiers, ongoing engines, tutors, asymmetric sweepers, alt costs, or
reality-bending one-shots. Each legendary also reckons with the three
global modifiers (Rift Storm, Soul Residue, Arcane Feedback) -- either
surviving them, exploiting them, or amplifying them.
"""

import random
from src.engine.game import make_minion, make_spell, make_hero, make_hero_power
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id,
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_spell_cast_trigger,
    make_static_pt_boost, make_spell_damage_boost,
    get_enemy_targets, get_enemy_minions, get_friendly_minions,
    get_enemy_hero_id, other_friendly_minions,
)


# =============================================================================
# HEROES
# =============================================================================

IGNIS_HERO = make_hero(
    name="Ignis, the Riftburner",
    hero_class="Pyromancer",
    starting_life=30,
    text="Hero Power: Rift Spark (Deal 1 damage to the enemy hero)",
)

GLACIEL_HERO = make_hero(
    name="Glaciel, the Voidfrost",
    hero_class="Cryomancer",
    starting_life=30,
    text="Hero Power: Frost Rift (Gain 2 Armor)",
)

STORMRIFT_HEROES = {
    "Pyromancer": IGNIS_HERO,
    "Cryomancer": GLACIEL_HERO,
}


# =============================================================================
# HERO POWERS
# =============================================================================

def rift_spark_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 1 damage to the enemy hero (buffed to 3 while Ignis Ascendant is in play)."""
    hero_id = get_enemy_hero_id(obj, state)
    if not hero_id:
        return []
    amount = 1
    # Ignis Ascendant check -- any battlefield object flagged ascendant_pyromancer
    for o in state.objects.values():
        if o.zone == ZoneType.BATTLEFIELD and o.controller == obj.controller \
                and getattr(o.state, 'ascendant_pyromancer', False):
            amount = 3
            break
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': hero_id, 'amount': amount, 'source': obj.id},
        source=obj.id,
    )]

RIFT_SPARK = make_hero_power(
    name="Rift Spark",
    cost=2,
    text="Deal 1 damage to the enemy hero.",
    effect=rift_spark_effect,
)

def frost_rift_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Gain 2 Armor."""
    return [Event(
        type=EventType.ARMOR_GAIN,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id,
    )]

FROST_RIFT = make_hero_power(
    name="Frost Rift",
    cost=2,
    text="Gain 2 Armor",
    effect=frost_rift_effect,
)

STORMRIFT_HERO_POWERS = {
    "Pyromancer": RIFT_SPARK,
    "Cryomancer": FROST_RIFT,
}


# =============================================================================
# PYROMANCER MINIONS
# =============================================================================

# --- 1-cost ---

RIFT_SPARK_ELEMENTAL = make_minion(
    name="Rift Spark Elemental",
    attack=2, health=1,
    mana_cost="{1}",
    subtypes={"Elemental"},
    keywords={"charge"},
    text="Charge",
    rarity="common",
)

KINDLING_IMP = make_minion(
    name="Kindling Imp",
    attack=1, health=2,
    mana_cost="{1}",
    subtypes={"Demon", "Elemental"},
    text="Deathrattle: Deal 1 damage to the enemy hero.",
    rarity="common",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DAMAGE,
        payload={'target': get_enemy_hero_id(obj, state) or '', 'amount': 1, 'source': obj.id},
        source=obj.id,
    )] if get_enemy_hero_id(obj, state) else [],
)

# --- 2-cost ---

def ember_channeler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    RARE redesign: After you cast a spell, gain +1 Attack permanently, AND the
    next Rift Storm tick does not damage Ember Channeler this turn.

    Why it alters: rewards casting spells with both offense AND survival, so
    the Rift Storm modifier turns into an upside rather than a wash.
    """
    def spell_filter(event, s):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source = s.objects.get(event.source)
        return source is not None and source.controller == obj.controller

    def spell_handler(event, s):
        # Mark "storm_shielded_until_turn_end" on this object
        me = s.objects.get(obj.id)
        if me and me.zone == ZoneType.BATTLEFIELD:
            me.state.storm_shielded_this_turn = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'permanent'},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter, handler=spell_handler,
        duration='while_on_battlefield',
    )]

EMBER_CHANNELER = make_minion(
    name="Ember Channeler",
    attack=2, health=3,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="After you cast a spell, gain +1 Attack and ignore the next Rift Storm this turn.",
    rarity="rare",
    setup_interceptors=ember_channeler_setup,
)

STORM_ACOLYTE = make_minion(
    name="Storm Acolyte",
    attack=1, health=3,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="Spell Damage +1",
    rarity="common",
    setup_interceptors=lambda obj, state: [make_spell_damage_boost(obj, amount=1)],
)

# --- 3-cost ---

def rift_firehound_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to a random enemy minion."""
    targets = get_enemy_minions(obj, state)
    if not targets:
        return []
    target = random.choice(targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': False},
        source=obj.id,
    )]

RIFT_FIREHOUND = make_minion(
    name="Rift Firehound",
    attack=3, health=2,
    mana_cost="{3}",
    subtypes={"Beast", "Elemental"},
    text="Battlecry: Deal 2 damage to a random enemy minion.",
    rarity="common",
    battlecry=rift_firehound_battlecry,
)

PYROCLASM_ADEPT = make_minion(
    name="Pyroclasm Adept",
    attack=3, health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="",
    rarity="common",
)

# --- 4-cost ---

def pyroclasm_drake_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Battlecry: Deal 1 damage to all enemy minions.
    The Rift Storm makes its sweep reliably lethal against 2-health minions -- this
    drake *synergises* with the global modifier.
    """
    targets = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 1, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

PYROCLASM_DRAKE = make_minion(
    name="Pyroclasm Drake",
    attack=4, health=4,
    mana_cost="{4}",
    subtypes={"Dragon", "Elemental"},
    text="Battlecry: Deal 1 damage to all enemy minions.",
    rarity="rare",
    battlecry=pyroclasm_drake_battlecry,
)

def rift_berserker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    RARE redesign: Whenever Arcane Feedback hits any minion, Rift Berserker
    gains +1 Attack this turn. Rift Storm survives the first tick (starts at
    4 health effective).

    Why it alters: this is the first card in the set that *feeds* on the
    global Arcane Feedback modifier instead of just tolerating it.
    """
    def feedback_filter(event, s):
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('source') == 'arcane_feedback'

    def feedback_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=feedback_filter, handler=feedback_handler,
        duration='while_on_battlefield',
    )]

RIFT_BERSERKER = make_minion(
    name="Rift Berserker",
    attack=4, health=4,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Charge. Whenever Arcane Feedback damages a minion, gain +1 Attack this turn.",
    keywords={"charge"},
    rarity="rare",
    setup_interceptors=rift_berserker_setup,
)

# --- 5-cost ---

INFERNO_GOLEM = make_minion(
    name="Inferno Golem",
    attack=5, health=6,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

def volatilerift_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """After you cast a spell, deal 1 damage to all enemy minions."""
    def spell_filter(event, s):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source = s.objects.get(event.source)
        return source is not None and source.controller == obj.controller

    def spell_handler(event, s):
        targets = get_enemy_minions(obj, s)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DAMAGE,
                    payload={'target': t, 'amount': 1, 'source': obj.id},
                    source=obj.id,
                )
                for t in targets
            ],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter, handler=spell_handler,
        duration='while_on_battlefield',
    )]

VOLATILERIFT_MAGE = make_minion(
    name="Volatilerift Mage",
    attack=4, health=5,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="After you cast a spell, deal 1 damage to all enemy minions.",
    rarity="epic",
    setup_interceptors=volatilerift_mage_setup,
)

# --- 6-cost ---

def stormrift_phoenix_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """
    RARE redesign -- turn the phoenix into a persistent engine.

    Deathrattle: Summon a 3/3 Phoenix Ember. Your spells deal +1 damage
    until end of your next turn.

    Why it alters: creates a scheduled "burst window" after it dies --
    the opponent must race to clear the board AND survive the window.
    """
    events: list[Event] = []

    # 1) Token
    events.append(Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'token': {
                'name': 'Phoenix Ember',
                'power': 3, 'toughness': 3,
                'types': {CardType.MINION},
                'subtypes': {'Elemental'},
                'keywords': {'charge'},
            },
        },
        source=obj.id,
    ))

    # 2) Register a persistent Spell-Damage +1 interceptor tied to the controller,
    #    not to Phoenix's object, and schedule its removal at end of the controller's
    #    NEXT turn.
    controller = obj.controller
    boost_id = f"phoenix_boost_{new_id()}"

    def boost_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('from_spell'):
            return False
        src = s.objects.get(event.source)
        return src is not None and src.controller == controller

    def boost_handler(event: Event, s: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    boost = Interceptor(
        id=boost_id, source='phoenix_boost', controller=controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=boost_filter, handler=boost_handler,
        duration='permanent',
    )
    state.interceptors[boost_id] = boost

    # Scheduling: remove at end of the controller's *next* turn start cycle.
    # Concretely: wait until we see our controller's turn END, then expire.
    turns_seen = {'count': 0}

    def sched_filter(event: Event, s: GameState) -> bool:
        return event.type == EventType.TURN_END and event.payload.get('player') == controller

    def sched_handler(event: Event, s: GameState) -> InterceptorResult:
        turns_seen['count'] += 1
        if turns_seen['count'] >= 1:
            s.interceptors.pop(boost_id, None)
            # Also remove the scheduler itself.
            s.interceptors.pop(sched_id, None)
        return InterceptorResult(action=InterceptorAction.PASS)

    sched_id = f"phoenix_boost_sched_{new_id()}"
    state.interceptors[sched_id] = Interceptor(
        id=sched_id, source='phoenix_boost', controller=controller,
        priority=InterceptorPriority.REACT,
        filter=sched_filter, handler=sched_handler,
        duration='permanent',
    )

    return events

STORMRIFT_PHOENIX = make_minion(
    name="Stormrift Phoenix",
    attack=5, health=5,
    mana_cost="{6}",
    subtypes={"Elemental", "Beast"},
    text="Deathrattle: Summon a 3/3 Phoenix Ember with Charge. Your spells deal +1 damage until the end of your next turn.",
    rarity="rare",
    deathrattle=stormrift_phoenix_deathrattle,
)

# --- 6-cost LEGENDARY: Ignis Ascendant ---

def _register_leave_cleanup(obj: GameObject, cleanup_fn, state: GameState) -> Interceptor:
    """Register an interceptor that runs cleanup_fn when obj leaves the battlefield or dies."""
    def leave_filter(event: Event, s: GameState) -> bool:
        if event.type == EventType.OBJECT_DESTROYED:
            return event.payload.get('object_id') == obj.id
        if event.type == EventType.ZONE_CHANGE:
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                    event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD)
        return False

    def leave_handler(event: Event, s: GameState) -> InterceptorResult:
        cleanup_fn(s)
        return InterceptorResult(action=InterceptorAction.PASS)

    icept = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=leave_filter, handler=leave_handler,
        duration='permanent',
    )
    state.interceptors[icept.id] = icept
    obj.interceptor_ids.append(icept.id)
    return icept


def ignis_ascendant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    LEGENDARY (Pyromancer, 6m, 5/6):
    "While Ignis Ascendant is on the battlefield, your spells deal +1 damage
    and your hero power deals 3 damage instead of 1."

    Rubric hit: PERSISTENT STATE MODIFIERS (#3) -- rewrites your hero power
    arithmetic while on board. Also resource-axis break (#2): 2-mana hero
    power now threatens lethal.

    Interacts with Rift Storm: Ignis has 6 HP, survives multiple ticks.
    Interacts with Arcane Feedback: every spell now pings for +1 with the boost.
    """
    interceptors: list[Interceptor] = []

    # Mark object so hero power reads the flag
    obj.state.ascendant_pyromancer = True

    def clear_flag(s: GameState):
        me = s.objects.get(obj.id)
        if me:
            me.state.ascendant_pyromancer = False

    _register_leave_cleanup(obj, clear_flag, state)

    # Spell damage +1
    interceptors.append(make_spell_damage_boost(obj, amount=1))

    return interceptors


IGNIS_ASCENDANT = make_minion(
    name="Ignis Ascendant",
    attack=5, health=6,
    mana_cost="{6}",
    subtypes={"Elemental", "Pyromancer"},
    text="Your spells deal +1 damage. Your hero power deals 3 damage instead of 1.",
    rarity="legendary",
    setup_interceptors=ignis_ascendant_setup,
)

# --- 7-cost LEGENDARY: Riftborn Phoenix (redesigned RIFTBORN_TITAN) ---

def riftborn_phoenix_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """
    LEGENDARY (Pyromancer, 7m, 6/6, redesigned):
    "Deathrattle: Resurrect Riftborn Phoenix as a 6/6 with Divine Shield.
    For the rest of the game, the first spell you cast each turn deals +2
    damage."

    Rubric: ONGOING ENGINE (#4) + persistent state (#3). A one-time resurrect
    plus a permanent game-rule amendment that creates a recurring burst tempo.
    Interacts with Rift Storm: the divine shield soaks the first tick each turn.
    """
    events: list[Event] = []

    # Prevent infinite loop by flagging when respawn already used
    if getattr(obj.state, 'phoenix_respawned', False):
        pass  # Already respawned; register persistent only once, below
    else:
        # Mark BEFORE creating token (token will check its own flag)
        obj.state.phoenix_respawned = True
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Riftborn Phoenix',
                    'power': 6, 'toughness': 6,
                    'types': {CardType.MINION},
                    'subtypes': {'Elemental', 'Phoenix'},
                    'keywords': {'divine_shield'},
                },
            },
            source=obj.id,
        ))

    # Register persistent "first spell each turn deals +2" ONCE.
    if not getattr(obj.state, 'phoenix_spell_boost_installed', False):
        obj.state.phoenix_spell_boost_installed = True
        controller = obj.controller
        spent_this_turn = {'turn': -1}

        def first_spell_boost_filter(event: Event, s: GameState) -> bool:
            if event.type != EventType.DAMAGE:
                return False
            if not event.payload.get('from_spell'):
                return False
            src = s.objects.get(event.source)
            if not src or src.controller != controller:
                return False
            # Only boost one damage-event-packet per turn: track by turn #.
            return spent_this_turn['turn'] != s.turn_number

        def first_spell_boost_handler(event: Event, s: GameState) -> InterceptorResult:
            spent_this_turn['turn'] = s.turn_number
            new_event = event.copy()
            new_event.payload['amount'] = event.payload.get('amount', 0) + 2
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event,
            )

        persistent = Interceptor(
            id=f"riftborn_phoenix_legacy_{new_id()}",
            source='riftborn_phoenix_legacy',
            controller=controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=first_spell_boost_filter,
            handler=first_spell_boost_handler,
            duration='permanent',  # Rest of the game
        )
        state.interceptors[persistent.id] = persistent

    return events

RIFTBORN_PHOENIX = make_minion(
    name="Riftborn Phoenix",
    attack=6, health=6,
    mana_cost="{7}",
    subtypes={"Elemental", "Phoenix"},
    text="Deathrattle: Resurrect as a 6/6 with Divine Shield. For the rest of the game, the first spell you cast each turn deals +2 damage.",
    rarity="legendary",
    deathrattle=riftborn_phoenix_deathrattle,
)


# =============================================================================
# PYROMANCER SPELLS
# =============================================================================

def singe_effect(obj, state, targets=None):
    """Deal 2 damage to a random enemy."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    )]

SINGE = make_spell(
    name="Singe",
    mana_cost="{1}",
    text="Deal 2 damage to a random enemy.",
    spell_effect=singe_effect,
    rarity="common",
)

def rift_bolt_effect(obj, state, targets=None):
    """Deal 3 damage to a random enemy."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 3, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    )]

RIFT_BOLT = make_spell(
    name="Rift Bolt",
    mana_cost="{2}",
    text="Deal 3 damage to a random enemy.",
    spell_effect=rift_bolt_effect,
    rarity="common",
)

def searing_rift_effect(obj, state, targets=None):
    """Deal 4 damage to a random enemy."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 4, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    )]

SEARING_RIFT = make_spell(
    name="Searing Rift",
    mana_cost="{4}",
    text="Deal 4 damage to a random enemy.",
    spell_effect=searing_rift_effect,
    rarity="rare",
)

def inferno_wave_effect(obj, state, targets=None):
    """Deal 3 damage to all enemy minions."""
    targets_list = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        )
        for t in targets_list
    ]

INFERNO_WAVE = make_spell(
    name="Inferno Wave",
    mana_cost="{5}",
    text="Deal 3 damage to all enemy minions.",
    spell_effect=inferno_wave_effect,
    rarity="rare",
)

def pyroclasm_effect(obj, state, targets=None):
    """Deal 5 damage to all enemies."""
    enemy_targets = get_enemy_targets(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 5, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        )
        for t in enemy_targets
    ]

PYROCLASM = make_spell(
    name="Pyroclasm",
    mana_cost="{7}",
    text="Deal 5 damage to all enemies.",
    spell_effect=pyroclasm_effect,
    rarity="epic",
)

def chain_lightning_effect(obj, state, targets=None):
    """Deal 2 damage to a random enemy, then 2 to another."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    events = []
    t1 = random.choice(enemy_targets)
    events.append(Event(
        type=EventType.DAMAGE,
        payload={'target': t1, 'amount': 2, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    ))
    remaining = [t for t in enemy_targets if t != t1]
    if remaining:
        t2 = random.choice(remaining)
    else:
        t2 = t1
    events.append(Event(
        type=EventType.DAMAGE,
        payload={'target': t2, 'amount': 2, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    ))
    return events

CHAIN_LIGHTNING = make_spell(
    name="Chain Lightning",
    mana_cost="{3}",
    text="Deal 2 damage to a random enemy, then 2 damage to another random enemy.",
    spell_effect=chain_lightning_effect,
    rarity="rare",
)


# --- LEGENDARY SPELL: Spell Echo ---

def spell_echo_effect(obj, state, targets=None):
    """
    LEGENDARY SPELL (Pyromancer, 5m):
    "Cast this. For the rest of the game, whenever you cast a damage-dealing
    spell, it triggers a second damage burst (2 damage to a random enemy)."

    Rubric: RESOURCE-AXIS BREAK (#2). Not a copy engine -- each cast kicks
    off an additional 2-damage Arcane-Feedback-style ping, stacking with the
    global Arcane Feedback for effective +3 per spell.
    Interacts with Arcane Feedback: amplifies it explicitly.
    """
    controller = obj.controller
    echo_id = f"spell_echo_{new_id()}"

    # Guard so we don't recurse: Arcane Feedback damage isn't a spell, but a
    # spell's own DAMAGE event is treated from_spell=True. We react on CAST
    # instead of DAMAGE so we only fire per *spell cast*, not per damage event.

    def echo_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        src = s.objects.get(event.source)
        if not src or src.controller != controller:
            return False
        # Don't echo the Spell Echo itself or further echoes
        return src.name != "Spell Echo"

    def echo_handler(event: Event, s: GameState) -> InterceptorResult:
        # Find an enemy target (minion or hero)
        src = s.objects.get(event.source)
        if not src:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Find enemy hero + enemy minions
        candidates: list[str] = []
        for pid, player in s.players.items():
            if pid != controller and player.hero_id:
                candidates.append(player.hero_id)
        bf = s.zones.get('battlefield')
        if bf:
            for oid in bf.objects:
                o = s.objects.get(oid)
                if o and o.controller != controller and CardType.MINION in o.characteristics.types:
                    candidates.append(oid)
        if not candidates:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = random.choice(candidates)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DAMAGE,
                payload={'target': target, 'amount': 2, 'source': 'spell_echo', 'from_spell': True},
                source='spell_echo',
            )],
        )

    state.interceptors[echo_id] = Interceptor(
        id=echo_id, source='spell_echo_global', controller=controller,
        priority=InterceptorPriority.REACT,
        filter=echo_filter, handler=echo_handler,
        duration='permanent',
    )

    # Also fire an initial 2-damage echo to visually confirm the cast did something
    enemy_targets = get_enemy_targets(obj, state)
    if enemy_targets:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': random.choice(enemy_targets), 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        )]
    return []


SPELL_ECHO = make_spell(
    name="Spell Echo",
    mana_cost="{5}",
    text="Deal 2 damage to a random enemy. For the rest of the game, each spell you cast also deals 2 damage to a random enemy.",
    spell_effect=spell_echo_effect,
    rarity="legendary",
)


# =============================================================================
# CRYOMANCER MINIONS
# =============================================================================

# --- 1-cost ---

FROST_WISP = make_minion(
    name="Frost Wisp",
    attack=1, health=2,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Deathrattle: Draw a card.",
    rarity="common",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    )],
)

VOID_SPRITE = make_minion(
    name="Void Sprite",
    attack=1, health=3,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

# --- 2-cost ---

GLACIAL_SENTINEL = make_minion(
    name="Glacial Sentinel",
    attack=2, health=3,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

def rift_watcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the end of your turn, draw a card."""
    def end_turn_filter(event, s):
        return (event.type in (EventType.TURN_END, EventType.PHASE_END) and
                event.payload.get('player') == obj.controller)

    def end_turn_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_turn_filter, handler=end_turn_handler,
        duration='while_on_battlefield',
    )]

RIFT_WATCHER = make_minion(
    name="Rift Watcher",
    attack=1, health=4,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="At the end of your turn, draw a card.",
    rarity="epic",
    setup_interceptors=rift_watcher_setup,
)

# --- 3-cost ---

VOID_SEER = make_minion(
    name="Void Seer",
    attack=2, health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Battlecry: Draw a card.",
    rarity="common",
    battlecry=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    )],
)

FROZEN_REVENANT = make_minion(
    name="Frozen Revenant",
    attack=3, health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

# --- 4-cost ---

ABYSSAL_LURKER = make_minion(
    name="Abyssal Lurker",
    attack=3, health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Deathrattle: Draw 2 cards.",
    rarity="rare",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 2},
        source=obj.id,
    )],
)

def voidcrystal_golem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your other minions have +0/+1."""
    return make_static_pt_boost(
        obj, power_mod=0, toughness_mod=1,
        affects_filter=other_friendly_minions(obj),
    )

VOIDCRYSTAL_GOLEM = make_minion(
    name="Voidcrystal Golem",
    attack=2, health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Your other minions have +0/+1.",
    rarity="rare",
    setup_interceptors=voidcrystal_golem_setup,
)

# --- 5-cost ---

def glacial_hourglass_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    LEGENDARY (Cryomancer, 5m, 3/6):
    "Whenever your opponent casts a spell, Freeze their hero for 1 turn.
    At the start of your turn, draw a card for each frozen enemy minion."

    Rubric: PERSISTENT STATE MODIFIERS (#3) + RESOURCE-AXIS BREAK (#2).
    Turns each opposing spell into a massive tempo tax while the engine
    draws you cards.

    Interacts with Arcane Feedback: AF already punishes spells; Glacial
    Hourglass turns every AF-triggering spell into a lock attempt.
    """
    interceptors: list[Interceptor] = []

    def freeze_filter(event, s):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        src = s.objects.get(event.source)
        return src is not None and src.controller != obj.controller

    def freeze_handler(event, s):
        enemy_hero = get_enemy_hero_id(obj, s)
        if not enemy_hero:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.FREEZE_TARGET,
                payload={'target': enemy_hero, 'source': obj.id},
                source=obj.id,
            )],
        )

    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=freeze_filter, handler=freeze_handler,
        duration='while_on_battlefield',
    ))

    def draw_filter(event, s):
        return (event.type == EventType.TURN_START and
                event.payload.get('player') == obj.controller)

    def draw_handler(event, s):
        # Count frozen enemy minions
        bf = s.zones.get('battlefield')
        count = 0
        if bf:
            for oid in bf.objects:
                o = s.objects.get(oid)
                if (o and o.controller != obj.controller
                        and CardType.MINION in o.characteristics.types
                        and getattr(o.state, 'frozen', False)):
                    count += 1
        if count <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': count},
                source=obj.id,
            )],
        )

    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=draw_filter, handler=draw_handler,
        duration='while_on_battlefield',
    ))

    return interceptors


GLACIAL_HOURGLASS = make_minion(
    name="Glacial Hourglass",
    attack=3, health=6,
    mana_cost="{5}",
    subtypes={"Elemental", "Cryomancer"},
    text="Whenever an opponent casts a spell, Freeze their hero. At the start of your turn, draw a card for each frozen enemy minion.",
    rarity="legendary",
    setup_interceptors=glacial_hourglass_setup,
)


def blizzard_golem_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    RARE redesign: Battlecry: Freeze all enemy minions. (Instead of flat 2 dmg.)

    Why it alters: pairs with Rift Storm -- frozen minions get ticked by
    Rift Storm next turn while unable to attack, creating an asymmetric wipe.
    """
    targets = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': t, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

BLIZZARD_GOLEM = make_minion(
    name="Blizzard Golem",
    attack=4, health=6,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="Battlecry: Freeze all enemy minions.",
    rarity="rare",
    battlecry=blizzard_golem_battlecry,
)

RIFT_GUARDIAN = make_minion(
    name="Rift Guardian",
    attack=3, health=8,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

# --- 6-cost: Void Anchor LEGENDARY (replaces vanilla slot) ---

def void_anchor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    LEGENDARY (Cryomancer, 6m, 4/8, Taunt):
    "While Void Anchor is on the battlefield, enemy minions cost {1} more."

    Rubric: PERSISTENT STATE MODIFIERS (#3) + RESOURCE-AXIS BREAK (#2).
    Persistent mana-tax aura that reshapes the opponent's curve.

    Interacts with Rift Storm: 8 health is four Rift Storm ticks of head-room.
    """
    modifier_id = f"void_anchor_{obj.id}"

    for pid, player in state.players.items():
        if pid == obj.controller:
            continue
        if any(m.get('id') == modifier_id for m in player.cost_modifiers):
            continue
        player.cost_modifiers.append({
            'id': modifier_id,
            'player': pid,
            'card_type': CardType.MINION,
            'amount': -1,   # Convention: -N = +N cost
            'duration': 'while_on_battlefield',
            'source': obj.id,
            'floor': 0,
        })

    def cleanup(s: GameState):
        for p in s.players.values():
            p.cost_modifiers = [m for m in p.cost_modifiers if m.get('id') != modifier_id]

    _register_leave_cleanup(obj, cleanup, state)
    return []


VOID_ANCHOR = make_minion(
    name="Void Anchor",
    attack=4, health=8,
    mana_cost="{6}",
    subtypes={"Elemental", "Cryomancer"},
    text="Taunt. Enemy minions cost (1) more.",
    keywords={"taunt"},
    rarity="legendary",
    setup_interceptors=void_anchor_setup,
)


def voidfrost_dragon_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    EPIC redesign: Battlecry: Freeze all enemies. Draw a card for each frozen enemy minion.

    Why it alters: converts a flat AOE into a lockdown-plus-card-advantage
    engine. Asymmetric with Rift Storm since frozen minions take Storm
    damage while unable to trade back.
    """
    events: list[Event] = []
    # Freeze hero
    hero = get_enemy_hero_id(obj, state)
    if hero:
        events.append(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': hero, 'source': obj.id},
            source=obj.id,
        ))
    minions = get_enemy_minions(obj, state)
    for t in minions:
        events.append(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': t, 'source': obj.id},
            source=obj.id,
        ))
    if minions:
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': len(minions)},
            source=obj.id,
        ))
    return events

VOIDFROST_DRAGON = make_minion(
    name="Voidfrost Dragon",
    attack=5, health=6,
    mana_cost="{6}",
    subtypes={"Dragon", "Elemental"},
    text="Battlecry: Freeze all enemies. Draw a card for each frozen enemy minion.",
    rarity="epic",
    battlecry=voidfrost_dragon_battlecry,
)

# --- 7-cost: Glaciel's Avatar redesigned LEGENDARY ---

def glaciels_avatar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    LEGENDARY (Cryomancer, 7m, 4/8, Taunt): redesigned.

    "Both heroes can't take damage from spells while Glaciel's Avatar is on
    the battlefield. Rift Storm no longer damages your minions."

    Rubric: PERSISTENT STATE MODIFIERS (#3). The Avatar literally *edits*
    two of the game's core damage laws while on the board.

    Interacts with Rift Storm: fully negates it on your side -- a Cryomancer
    playset with Avatar is the only way to sidestep the board-cleanser.
    Interacts with Arcane Feedback: Arcane Feedback isn't 'from_spell', so
    it still pings, preserving a weakness.
    """
    interceptors: list[Interceptor] = []

    # 1) PREVENT spell damage to either hero
    def hero_spell_prevent_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('from_spell'):
            return False
        target_id = event.payload.get('target')
        if not target_id:
            return False
        target = s.objects.get(target_id)
        return bool(target and CardType.HERO in target.characteristics.types)

    def hero_spell_prevent_handler(event: Event, s: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=hero_spell_prevent_filter, handler=hero_spell_prevent_handler,
        duration='while_on_battlefield',
    ))

    # 2) PREVENT Rift Storm damage to your minions
    def rift_storm_prevent_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != 'rift_storm':
            return False
        target_id = event.payload.get('target')
        target = s.objects.get(target_id) if target_id else None
        return bool(target and target.controller == obj.controller
                    and CardType.MINION in target.characteristics.types)

    def rift_storm_prevent_handler(event: Event, s: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=rift_storm_prevent_filter, handler=rift_storm_prevent_handler,
        duration='while_on_battlefield',
    ))

    return interceptors

GLACIELS_AVATAR = make_minion(
    name="Glaciel's Avatar",
    attack=4, health=8,
    mana_cost="{7}",
    subtypes={"Elemental", "Cryomancer"},
    text="Taunt. Heroes can't take damage from spells. Rift Storm no longer damages your minions.",
    keywords={"taunt"},
    rarity="legendary",
    setup_interceptors=glaciels_avatar_setup,
)


# --- 9-cost RIFT COLOSSUS (redesigned) ---

def rift_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    LEGENDARY (Neutral, 9m, 7/9): REDESIGNED.

    "Taunt. Rift Armor (while you have 3+ Elementals, Divine Shield).
    For the rest of the game, whenever either hero takes damage, that
    hero's controller loses 1 additional life."

    Rubric: PERSISTENT STATE MODIFIERS (#3), REALITY-BEND (#8). Permanently
    amends the damage-math rule for every hero, for the rest of the game.
    A signature "the game just got weirder" card.

    Interacts with Rift Storm: the colossus has 9 HP and gets Divine Shield
    once the board is built, so it survives. Interacts with Arcane Feedback:
    unchanged -- Arcane Feedback pings minions, not heroes.
    """
    interceptors: list[Interceptor] = []

    # 1) Persistent "heroes take +1 per damage hit" interceptor. Survives
    # the colossus's own death, for the rest of the game.
    already_installed_id = f"rift_colossus_amend_{new_id()}"
    # Re-entrancy guard using payload key
    def amend_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('rift_colossus_amended'):
            return False
        target_id = event.payload.get('target')
        if not target_id:
            return False
        target = s.objects.get(target_id)
        return bool(target and CardType.HERO in target.characteristics.types)

    def amend_handler(event: Event, s: GameState) -> InterceptorResult:
        target_id = event.payload.get('target')
        target = s.objects.get(target_id)
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Find the hero's player
        player_id = target.controller
        extra = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': player_id, 'amount': -1, 'rift_colossus_amended': True},
            source='rift_colossus_amend',
        )
        # Mark original so we don't recurse
        new_event = event.copy()
        new_event.payload['rift_colossus_amended'] = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
            new_events=[extra],
        )

    amend_interceptor = Interceptor(
        id=already_installed_id,
        source='rift_colossus_global',
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=amend_filter, handler=amend_handler,
        duration='permanent',  # Survives death -- rest of game
    )
    # Only install once per game
    if not any(ic.source == 'rift_colossus_global' for ic in state.interceptors.values()):
        state.interceptors[already_installed_id] = amend_interceptor

    # 2) Divine Shield while you have 3+ Elementals: QUERY_ABILITIES
    def shield_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        me = s.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return False
        # Count friendly Elementals (including self)
        bf = s.zones.get('battlefield')
        if not bf:
            return False
        count = 0
        for oid in bf.objects:
            o = s.objects.get(oid)
            if (o and o.controller == obj.controller
                    and CardType.MINION in o.characteristics.types
                    and 'Elemental' in o.characteristics.subtypes):
                count += 1
        return count >= 3

    def shield_handler(event: Event, s: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'divine_shield' not in granted:
            granted.append('divine_shield')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=shield_filter, handler=shield_handler,
        duration='while_on_battlefield',
    ))

    # Also set divine_shield directly if condition already holds at ETB
    bf = state.zones.get('battlefield')
    if bf:
        count = 0
        for oid in bf.objects:
            o = state.objects.get(oid)
            if (o and o.controller == obj.controller
                    and CardType.MINION in o.characteristics.types
                    and 'Elemental' in o.characteristics.subtypes):
                count += 1
        if count >= 3:
            obj.state.divine_shield = True

    return interceptors

RIFT_COLOSSUS = make_minion(
    name="Rift Colossus",
    attack=7, health=9,
    mana_cost="{9}",
    subtypes={"Elemental"},
    text="Taunt. Rift Armor (while you control 3+ Elementals, this has Divine Shield). For the rest of the game, whenever either hero takes damage, that hero's controller loses 1 additional life.",
    keywords={"taunt"},
    rarity="legendary",
    setup_interceptors=rift_colossus_setup,
)


# --- 10-cost NEUTRAL MYTHIC LEGENDARY: Stormrift Apex Dragon ---

def apex_dragon_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    LEGENDARY (Neutral, 10m, 8/8): Mythic.

    "Battlecry: Choose one randomly --
       * Pyromantic: Deal 8 damage split among all enemies.
       * Cryomantic: Freeze all enemies. Draw 3 cards.
       * Riftshift: Swap hands with your opponent. Each player draws 2."

    Rubric: ONGOING MULTI-MODE (#4) + REALITY-BEND (#8) on the third mode.
    Random mode (not player-chosen) because the engine's modal-choice UI
    isn't used for HS battlecries -- but each mode is a genuine game-twist
    on its own.
    """
    mode = random.choice(['pyromantic', 'cryomantic', 'riftshift'])
    events: list[Event] = []

    if mode == 'pyromantic':
        # Split 8 damage -- 2 to face + 1 per enemy minion, remainder to face
        remaining = 8
        enemy_hero = get_enemy_hero_id(obj, state)
        enemies = get_enemy_minions(obj, state)
        for t in enemies:
            if remaining <= 0:
                break
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': t, 'amount': 1, 'source': obj.id},
                source=obj.id,
            ))
            remaining -= 1
        if enemy_hero and remaining > 0:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': enemy_hero, 'amount': remaining, 'source': obj.id},
                source=obj.id,
            ))
    elif mode == 'cryomantic':
        hero = get_enemy_hero_id(obj, state)
        if hero:
            events.append(Event(
                type=EventType.FREEZE_TARGET,
                payload={'target': hero, 'source': obj.id},
                source=obj.id,
            ))
        for t in get_enemy_minions(obj, state):
            events.append(Event(
                type=EventType.FREEZE_TARGET,
                payload={'target': t, 'source': obj.id},
                source=obj.id,
            ))
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 3},
            source=obj.id,
        ))
    else:  # riftshift
        # Swap hands: collect both players' hand object IDs, then reparent.
        # We implement via direct zone manipulation since there's no event for it.
        my_hand_key = f"hand_{obj.controller}"
        opp_id = None
        for pid in state.players:
            if pid != obj.controller:
                opp_id = pid
                break
        if opp_id:
            opp_hand_key = f"hand_{opp_id}"
            my_hand = state.zones.get(my_hand_key)
            opp_hand = state.zones.get(opp_hand_key)
            if my_hand and opp_hand:
                my_cards = list(my_hand.objects)
                opp_cards = list(opp_hand.objects)
                # Reparent owners
                for oid in my_cards:
                    if oid in state.objects:
                        state.objects[oid].controller = opp_id
                        state.objects[oid].owner = opp_id
                for oid in opp_cards:
                    if oid in state.objects:
                        state.objects[oid].controller = obj.controller
                        state.objects[oid].owner = obj.controller
                my_hand.objects = opp_cards
                opp_hand.objects = my_cards
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 2},
            source=obj.id,
        ))
        if opp_id:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': opp_id, 'count': 2},
                source=obj.id,
            ))

    return events


STORMRIFT_APEX_DRAGON = make_minion(
    name="Stormrift Apex Dragon",
    attack=8, health=8,
    mana_cost="{10}",
    subtypes={"Dragon", "Elemental", "Mythic"},
    text="Battlecry: A random rift-mode triggers: Pyromantic (8 dmg split), Cryomantic (freeze all enemies, draw 3), or Riftshift (swap hands, each draws 2).",
    rarity="legendary",
    battlecry=apex_dragon_battlecry,
)


# =============================================================================
# CRYOMANCER SPELLS
# =============================================================================

def frost_spike_effect(obj, state, targets=None):
    """Deal 1 damage to a random enemy. Draw a card."""
    enemy_targets = get_enemy_targets(obj, state)
    events = []
    if enemy_targets:
        target = random.choice(enemy_targets)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    ))
    return events

FROST_SPIKE = make_spell(
    name="Frost Spike",
    mana_cost="{1}",
    text="Deal 1 damage to a random enemy. Draw a card.",
    spell_effect=frost_spike_effect,
    rarity="common",
)

def rift_sight_effect(obj, state, targets=None):
    """Draw 2 cards."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 2},
        source=obj.id,
    )]

RIFT_SIGHT = make_spell(
    name="Rift Sight",
    mana_cost="{3}",
    text="Draw 2 cards.",
    spell_effect=rift_sight_effect,
    rarity="common",
)

def void_barrier_effect(obj, state, targets=None):
    """Give all friendly minions +0/+2."""
    friendlies = get_friendly_minions(obj, state, exclude_self=False)
    return [
        Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': t, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
            source=obj.id,
        )
        for t in friendlies
    ]

VOID_BARRIER = make_spell(
    name="Void Barrier",
    mana_cost="{4}",
    text="Give all friendly minions +0/+2.",
    spell_effect=void_barrier_effect,
    rarity="rare",
)

def glacial_tomb_effect(obj, state, targets=None):
    """Deal 4 damage to a random enemy minion. Draw a card."""
    events = []
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 4, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    ))
    return events

GLACIAL_TOMB = make_spell(
    name="Glacial Tomb",
    mana_cost="{5}",
    text="Deal 4 damage to a random enemy minion. Draw a card.",
    spell_effect=glacial_tomb_effect,
    rarity="rare",
)

def absolute_zero_effect(obj, state, targets=None):
    """
    EPIC redesign: Freeze all enemies and deal 2 damage to all enemy minions.
    Any enemy minion that was already frozen takes 4 damage instead.

    Why it alters: massively punishes lockdown-play setups, and when paired
    with Voidfrost Dragon / Glacial Hourglass becomes an asymmetric wipe
    rather than a flat AOE.
    """
    events: list[Event] = []
    # Freeze hero
    hero = get_enemy_hero_id(obj, state)
    if hero:
        events.append(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': hero, 'source': obj.id},
            source=obj.id,
        ))
    # Minions: freeze + damage (2 normally, 4 if already frozen)
    for t in get_enemy_minions(obj, state):
        already_frozen = False
        target_obj = state.objects.get(t)
        if target_obj and getattr(target_obj.state, 'frozen', False):
            already_frozen = True
        events.append(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': t, 'source': obj.id},
            source=obj.id,
        ))
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 4 if already_frozen else 2, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    return events

ABSOLUTE_ZERO = make_spell(
    name="Absolute Zero",
    mana_cost="{7}",
    text="Freeze all enemies. Deal 2 damage to each enemy minion (4 instead if it was already frozen).",
    spell_effect=absolute_zero_effect,
    rarity="epic",
)

def void_drain_effect(obj, state, targets=None):
    """Deal 2 damage to a random enemy minion. Gain 2 Armor."""
    events = []
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    events.append(Event(
        type=EventType.ARMOR_GAIN,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id,
    ))
    return events

VOID_DRAIN = make_spell(
    name="Void Drain",
    mana_cost="{2}",
    text="Deal 2 damage to a random enemy minion. Gain 2 Armor.",
    spell_effect=void_drain_effect,
    rarity="common",
)


# =============================================================================
# NEUTRAL MINIONS (shared between both classes)
# =============================================================================

RIFT_WALKER = make_minion(
    name="Rift Walker",
    attack=1, health=1,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Battlecry: Draw a card.",
    rarity="common",
    battlecry=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    )],
)

STORM_HERALD = make_minion(
    name="Storm Herald",
    attack=2, health=2,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="",
    rarity="common",
)

RIFT_IMP = make_minion(
    name="Rift Imp",
    attack=3, health=3,
    mana_cost="{3}",
    subtypes={"Demon", "Elemental"},
    text="",
    rarity="common",
)

NEXUS_GUARDIAN = make_minion(
    name="Nexus Guardian",
    attack=4, health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

RIFT_CHAMPION = make_minion(
    name="Rift Champion",
    attack=5, health=5,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="",
    rarity="common",
)

RIFT_BEHEMOTH = make_minion(
    name="Rift Behemoth",
    attack=6, health=7,
    mana_cost="{6}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)


# =============================================================================
# DECKS
# =============================================================================

# Pyromancer deck: legendaries are 1-of (canonical HS rule)
PYROMANCER_DECK = [
    # 1-cost (6)
    RIFT_SPARK_ELEMENTAL, RIFT_SPARK_ELEMENTAL,
    KINDLING_IMP, KINDLING_IMP,
    SINGE, SINGE,
    # 2-cost (6)
    EMBER_CHANNELER, EMBER_CHANNELER,
    STORM_ACOLYTE, STORM_ACOLYTE,
    RIFT_BOLT, RIFT_BOLT,
    # 3-cost (4)
    RIFT_FIREHOUND, RIFT_FIREHOUND,
    CHAIN_LIGHTNING, CHAIN_LIGHTNING,
    # 4-cost (4)
    PYROCLASM_DRAKE, PYROCLASM_DRAKE,
    RIFT_BERSERKER, SEARING_RIFT,
    # 5-cost (3)
    INFERNO_GOLEM, VOLATILERIFT_MAGE,
    INFERNO_WAVE,
    # 6-cost (2)
    IGNIS_ASCENDANT,       # LEGENDARY
    STORMRIFT_PHOENIX,
    # 7-cost (2)
    RIFTBORN_PHOENIX,      # LEGENDARY
    PYROCLASM,
    # Legendary spell (1)
    SPELL_ECHO,            # LEGENDARY
    # Neutral filler (2)
    RIFT_WALKER, RIFT_WALKER,
]

# Cryomancer deck
CRYOMANCER_DECK = [
    # 1-cost (6)
    FROST_WISP, FROST_WISP,
    VOID_SPRITE, VOID_SPRITE,
    FROST_SPIKE, FROST_SPIKE,
    # 2-cost (6)
    GLACIAL_SENTINEL, GLACIAL_SENTINEL,
    RIFT_WATCHER, VOID_DRAIN,
    VOID_DRAIN, STORM_HERALD,
    # 3-cost (4)
    VOID_SEER, VOID_SEER,
    RIFT_SIGHT, RIFT_SIGHT,
    # 4-cost (3)
    ABYSSAL_LURKER, ABYSSAL_LURKER,
    VOIDCRYSTAL_GOLEM,
    # 5-cost (3)
    GLACIAL_HOURGLASS,      # LEGENDARY
    BLIZZARD_GOLEM, GLACIAL_TOMB,
    # 6-cost (2)
    VOID_ANCHOR,            # LEGENDARY
    VOIDFROST_DRAGON,
    # 7-cost (2)
    GLACIELS_AVATAR,        # LEGENDARY (redesigned)
    ABSOLUTE_ZERO,
    # 9-cost / 10-cost (2) -- shared with Pyro too, but Cryo can run big
    RIFT_COLOSSUS,          # LEGENDARY (redesigned)
    STORMRIFT_APEX_DRAGON,  # LEGENDARY (mythic)
    # Extra filler
    VOID_BARRIER, RIFT_BEHEMOTH,
]

STORMRIFT_DECKS = {
    "Pyromancer": PYROMANCER_DECK,
    "Cryomancer": CRYOMANCER_DECK,
}

assert len(PYROMANCER_DECK) == 30, f"Pyromancer deck has {len(PYROMANCER_DECK)} cards, expected 30"
assert len(CRYOMANCER_DECK) == 30, f"Cryomancer deck has {len(CRYOMANCER_DECK)} cards, expected 30"


# =============================================================================
# GLOBAL MODIFIERS (installed at game start via stress test)
# =============================================================================

def install_stormrift_modifiers(game) -> None:
    """
    Install the three global Stormrift modifiers as persistent interceptors.

    1. Rift Storm   - Start of each player's turn, deal 1 damage to ALL minions.
    2. Soul Residue - First minion death each turn creates a 1/1 Spirit for owner.
    3. Arcane Feedback - Whenever a spell is cast, deal 1 to a random enemy minion.
    """
    state = game.state
    player_ids = list(state.players.keys())
    if len(player_ids) < 2:
        return

    # Tracking state for Soul Residue (per-turn death tracking)
    _soul_residue_state = {'deaths_this_turn': set()}

    # --- MODIFIER 1: Rift Storm ---
    def rift_storm_filter(event, s):
        return event.type == EventType.TURN_START

    def rift_storm_handler(event, s):
        battlefield = s.zones.get('battlefield')
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)
        damage_events = []
        for oid in list(battlefield.objects):
            obj = s.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                # Ember Channeler's per-turn storm shield: skip & consume the flag
                if getattr(obj.state, 'storm_shielded_this_turn', False):
                    obj.state.storm_shielded_this_turn = False
                    continue
                damage_events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': oid, 'amount': 1, 'source': 'rift_storm'},
                    source='rift_storm',
                ))
        if damage_events:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=damage_events)
        return InterceptorResult(action=InterceptorAction.PASS)

    rift_storm = Interceptor(
        id=f"mod_rift_storm_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],  # Global, but needs a controller
        priority=InterceptorPriority.REACT,
        filter=rift_storm_filter,
        handler=rift_storm_handler,
        duration='permanent',
    )

    # --- MODIFIER 2: Soul Residue ---
    # Reset tracker at turn start (registered BEFORE Rift Storm so reset fires first)
    def soul_residue_reset_filter(event, s):
        return event.type == EventType.TURN_START

    def soul_residue_reset_handler(event, s):
        _soul_residue_state['deaths_this_turn'] = set()
        return InterceptorResult(action=InterceptorAction.PASS)

    soul_residue_reset = Interceptor(
        id=f"mod_soul_residue_reset_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],
        priority=InterceptorPriority.REACT,
        filter=soul_residue_reset_filter,
        handler=soul_residue_reset_handler,
        duration='permanent',
    )
    # Register Soul Residue reset FIRST (earlier timestamp -> fires before Rift Storm)
    game.register_interceptor(soul_residue_reset)
    # Then Rift Storm (deaths from Rift Storm count toward "first death this turn")
    game.register_interceptor(rift_storm)

    # Create Spirit on first death
    def soul_residue_filter(event, s):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        oid = event.payload.get('object_id')
        obj = s.objects.get(oid)
        if not obj or CardType.MINION not in obj.characteristics.types:
            return False
        return obj.controller not in _soul_residue_state['deaths_this_turn']

    def soul_residue_handler(event, s):
        oid = event.payload.get('object_id')
        obj = s.objects.get(oid)
        if not obj:
            return InterceptorResult(action=InterceptorAction.PASS)
        controller = obj.controller
        _soul_residue_state['deaths_this_turn'].add(controller)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': controller,
                    'token': {
                        'name': 'Rift Spirit',
                        'power': 1,
                        'toughness': 1,
                        'types': {CardType.MINION},
                        'subtypes': {'Spirit', 'Elemental'},
                    },
                },
                source='soul_residue',
            )],
        )

    soul_residue = Interceptor(
        id=f"mod_soul_residue_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],
        priority=InterceptorPriority.REACT,
        filter=soul_residue_filter,
        handler=soul_residue_handler,
        duration='permanent',
    )
    game.register_interceptor(soul_residue)

    # --- MODIFIER 3: Arcane Feedback ---
    def arcane_feedback_filter(event, s):
        return event.type in (EventType.CAST, EventType.SPELL_CAST)

    def arcane_feedback_handler(event, s):
        source_obj = s.objects.get(event.source)
        if not source_obj:
            return InterceptorResult(action=InterceptorAction.PASS)
        caster_id = source_obj.controller
        # Find enemy minions
        battlefield = s.zones.get('battlefield')
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)
        enemy_minions = [
            oid for oid in battlefield.objects
            if oid in s.objects
            and s.objects[oid].controller != caster_id
            and CardType.MINION in s.objects[oid].characteristics.types
        ]
        if not enemy_minions:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = random.choice(enemy_minions)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DAMAGE,
                payload={'target': target, 'amount': 1, 'source': 'arcane_feedback'},
                source='arcane_feedback',
            )],
        )

    arcane_feedback = Interceptor(
        id=f"mod_arcane_feedback_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],
        priority=InterceptorPriority.REACT,
        filter=arcane_feedback_filter,
        handler=arcane_feedback_handler,
        duration='permanent',
    )
    game.register_interceptor(arcane_feedback)
