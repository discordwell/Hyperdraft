"""
RIFTCLASH - Deterministic Pyromancer vs Cryomancer Variant

A tighter Hearthstone/MTG hybrid duel mode focused on tactical sequencing:
- Lower RNG than Stormrift (deterministic target selection where possible)
- Strong class identity (burn tempo vs freeze control)
- Global battlefield modifiers that reduce snowballing
"""

from src.engine.game import make_minion, make_spell, make_hero, make_hero_power
from src.engine.queries import get_power, get_toughness
from src.engine.types import (
    Event,
    EventType,
    GameObject,
    GameState,
    CardType,
    Interceptor,
    InterceptorPriority,
    InterceptorAction,
    InterceptorResult,
    new_id,
)
from src.cards.interceptor_helpers import get_enemy_hero_id, get_enemy_minions

# Reuse stable Stormrift cards as a base chassis.
from src.cards.hearthstone.stormrift import (
    RIFT_SPARK_ELEMENTAL,
    KINDLING_IMP,
    EMBER_CHANNELER,
    STORM_ACOLYTE,
    PYROCLASM_DRAKE,
    INFERNO_GOLEM,
    VOLATILERIFT_MAGE,
    STORMRIFT_PHOENIX,
    RIFTBORN_TITAN,
    INFERNO_WAVE,
    FROST_WISP,
    VOID_SPRITE,
    GLACIAL_SENTINEL,
    RIFT_WATCHER,
    VOID_SEER,
    FROZEN_REVENANT,
    ABYSSAL_LURKER,
    VOIDCRYSTAL_GOLEM,
    BLIZZARD_GOLEM,
    RIFT_GUARDIAN,
    VOIDFROST_DRAGON,
    GLACIELS_AVATAR,
    ABSOLUTE_ZERO,
    NEXUS_GUARDIAN,
)


# =============================================================================
# Helper utilities
# =============================================================================


def _enemy_minion_ids(obj: GameObject, state: GameState) -> list[str]:
    return [oid for oid in get_enemy_minions(obj, state) if oid in state.objects]


def _highest_attack_enemy_minion_id(obj: GameObject, state: GameState) -> str | None:
    candidates = _enemy_minion_ids(obj, state)
    if not candidates:
        return None

    def _score(oid: str) -> tuple[int, int, int]:
        enemy = state.objects[oid]
        remaining_hp = (get_toughness(enemy, state) or 0) - enemy.state.damage
        return (get_power(enemy, state) or 0, remaining_hp, enemy.created_at)

    return max(candidates, key=_score)


# =============================================================================
# Heroes and Hero Powers
# =============================================================================

IGNIS_REFORGED = make_hero(
    name="Ignis, Rift Vanguard",
    hero_class="Pyromancer",
    starting_life=30,
    text="Hero Power: Ember Volley (Deal 1 to enemy hero and 1 to highest-Attack enemy minion)",
)

GLACIEL_REFORGED = make_hero(
    name="Glaciel, Icebound Regent",
    hero_class="Cryomancer",
    starting_life=30,
    text="Hero Power: Cryo Ward (Gain 2 Armor. Freeze highest-Attack enemy minion)",
)

RIFTCLASH_HEROES = {
    "Pyromancer": IGNIS_REFORGED,
    "Cryomancer": GLACIEL_REFORGED,
}


def ember_volley_effect(obj: GameObject, state: GameState) -> list[Event]:
    events: list[Event] = []

    enemy_hero_id = get_enemy_hero_id(obj, state)
    if enemy_hero_id:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": enemy_hero_id, "amount": 1, "source": obj.id},
                source=obj.id,
            )
        )

    target = _highest_attack_enemy_minion_id(obj, state)
    if target:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": target, "amount": 1, "source": obj.id},
                source=obj.id,
            )
        )

    return events


EMBER_VOLLEY = make_hero_power(
    name="Ember Volley",
    cost=2,
    text="Deal 1 damage to the enemy hero and 1 damage to the highest-Attack enemy minion.",
    effect=ember_volley_effect,
)


def cryo_ward_effect(obj: GameObject, state: GameState) -> list[Event]:
    events = [
        Event(
            type=EventType.ARMOR_GAIN,
            payload={"player": obj.controller, "amount": 2},
            source=obj.id,
        )
    ]

    target = _highest_attack_enemy_minion_id(obj, state)
    if target:
        events.append(
            Event(
                type=EventType.FREEZE_TARGET,
                payload={"target": target},
                source=obj.id,
            )
        )

    return events


CRYO_WARD = make_hero_power(
    name="Cryo Ward",
    cost=2,
    text="Gain 2 Armor. Freeze the highest-Attack enemy minion.",
    effect=cryo_ward_effect,
)

RIFTCLASH_HERO_POWERS = {
    "Pyromancer": EMBER_VOLLEY,
    "Cryomancer": CRYO_WARD,
}


# =============================================================================
# Pyromancer cards
# =============================================================================


def ember_tactician_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": oid, "amount": 1, "source": obj.id},
            source=obj.id,
        )
        for oid in _enemy_minion_ids(obj, state)
    ]


EMBER_TACTICIAN = make_minion(
    name="Ember Tactician",
    attack=3,
    health=3,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 1 damage to all enemy minions.",
    rarity="rare",
    battlecry=ember_tactician_battlecry,
)


def molten_overseer_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    def _spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source_obj = s.objects.get(event.source)
        return source_obj is not None and source_obj.controller == obj.controller

    def _spell_handler(_event: Event, s: GameState) -> InterceptorResult:
        enemy_hero_id = get_enemy_hero_id(obj, s)
        if not enemy_hero_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": enemy_hero_id, "amount": 1, "source": obj.id},
                    source=obj.id,
                )
            ],
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_spell_filter,
            handler=_spell_handler,
            duration="while_on_battlefield",
        )
    ]


MOLTEN_OVERSEER = make_minion(
    name="Molten Overseer",
    attack=4,
    health=5,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="After you cast a spell, deal 1 damage to the enemy hero.",
    rarity="epic",
    setup_interceptors=molten_overseer_setup,
)


def cinder_lance_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if target:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={"target": target, "amount": 3, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        ]

    hero = get_enemy_hero_id(obj, state)
    if hero:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={"target": hero, "amount": 3, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        ]
    return []


CINDER_LANCE = make_spell(
    name="Cinder Lance",
    mana_cost="{2}",
    text="Deal 3 damage to the highest-Attack enemy minion. If none, deal 3 damage to the enemy hero.",
    spell_effect=cinder_lance_effect,
    rarity="common",
)


def scorching_surge_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": oid, "amount": 2, "source": obj.id, "from_spell": True},
            source=obj.id,
        )
        for oid in _enemy_minion_ids(obj, state)
    ]


SCORCHING_SURGE = make_spell(
    name="Scorching Surge",
    mana_cost="{3}",
    text="Deal 2 damage to all enemy minions.",
    spell_effect=scorching_surge_effect,
    rarity="rare",
)


def rift_conflagration_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events: list[Event] = []
    enemy_hero_id = get_enemy_hero_id(obj, state)
    if enemy_hero_id:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": enemy_hero_id, "amount": 4, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )

    for oid in _enemy_minion_ids(obj, state):
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 4, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )

    return events


RIFT_CONFLAGRATION = make_spell(
    name="Rift Conflagration",
    mana_cost="{6}",
    text="Deal 4 damage to all enemies.",
    spell_effect=rift_conflagration_effect,
    rarity="epic",
)


# =============================================================================
# Cryomancer cards
# =============================================================================


def ice_shackle_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return []

    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": target, "amount": 2, "source": obj.id, "from_spell": True},
            source=obj.id,
        ),
        Event(
            type=EventType.FREEZE_TARGET,
            payload={"target": target},
            source=obj.id,
        ),
    ]


ICE_SHACKLE = make_spell(
    name="Ice Shackle",
    mana_cost="{2}",
    text="Deal 2 damage to the highest-Attack enemy minion and Freeze it.",
    spell_effect=ice_shackle_effect,
    rarity="common",
)


def glacial_insight_effect(obj: GameObject, _state: GameState, _targets=None) -> list[Event]:
    return [
        Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 2},
            source=obj.id,
        ),
        Event(
            type=EventType.ARMOR_GAIN,
            payload={"player": obj.controller, "amount": 1},
            source=obj.id,
        ),
    ]


GLACIAL_INSIGHT = make_spell(
    name="Glacial Insight",
    mana_cost="{3}",
    text="Draw 2 cards. Gain 1 Armor.",
    spell_effect=glacial_insight_effect,
    rarity="common",
)


def whiteout_protocol_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events: list[Event] = []
    for oid in _enemy_minion_ids(obj, state):
        events.append(
            Event(
                type=EventType.FREEZE_TARGET,
                payload={"target": oid},
                source=obj.id,
            )
        )
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 1, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )
    return events


WHITEOUT_PROTOCOL = make_spell(
    name="Whiteout Protocol",
    mana_cost="{5}",
    text="Freeze all enemy minions. Deal 1 damage to them.",
    spell_effect=whiteout_protocol_effect,
    rarity="rare",
)


def cryo_sentinel_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return []
    return [
        Event(
            type=EventType.FREEZE_TARGET,
            payload={"target": target},
            source=obj.id,
        )
    ]


CRYO_SENTINEL = make_minion(
    name="Cryo Sentinel",
    attack=3,
    health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    keywords={"taunt"},
    text="Taunt. Deathrattle: Freeze the highest-Attack enemy minion.",
    rarity="rare",
    deathrattle=cryo_sentinel_deathrattle,
)


def absolute_archivist_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    def _end_turn_filter(event: Event, _s: GameState) -> bool:
        return (
            event.type == EventType.PHASE_END
            and event.payload.get("phase") == "end"
            and event.payload.get("player") == obj.controller
        )

    def _end_turn_handler(_event: Event, s: GameState) -> InterceptorResult:
        enemy_minions = _enemy_minion_ids(obj, s)
        if not enemy_minions:
            return InterceptorResult(action=InterceptorAction.PASS)

        if not any(s.objects[oid].state.frozen for oid in enemy_minions if oid in s.objects):
            return InterceptorResult(action=InterceptorAction.PASS)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": 1},
                    source=obj.id,
                )
            ],
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_end_turn_filter,
            handler=_end_turn_handler,
            duration="while_on_battlefield",
        )
    ]


ABSOLUTE_ARCHIVIST = make_minion(
    name="Absolute Archivist",
    attack=5,
    health=7,
    mana_cost="{6}",
    subtypes={"Elemental"},
    text="At the end of your turn, if an enemy minion is frozen, draw a card.",
    rarity="epic",
    setup_interceptors=absolute_archivist_setup,
)


# =============================================================================
# Decks
# =============================================================================

RIFTCLASH_PYROMANCER_DECK = [
    RIFT_SPARK_ELEMENTAL,
    RIFT_SPARK_ELEMENTAL,
    KINDLING_IMP,
    KINDLING_IMP,
    EMBER_CHANNELER,
    EMBER_CHANNELER,
    STORM_ACOLYTE,
    STORM_ACOLYTE,
    EMBER_TACTICIAN,
    EMBER_TACTICIAN,
    PYROCLASM_DRAKE,
    PYROCLASM_DRAKE,
    INFERNO_GOLEM,
    INFERNO_GOLEM,
    MOLTEN_OVERSEER,
    MOLTEN_OVERSEER,
    VOLATILERIFT_MAGE,
    VOLATILERIFT_MAGE,
    STORMRIFT_PHOENIX,
    RIFTBORN_TITAN,
    NEXUS_GUARDIAN,
    NEXUS_GUARDIAN,
    CINDER_LANCE,
    CINDER_LANCE,
    SCORCHING_SURGE,
    SCORCHING_SURGE,
    INFERNO_WAVE,
    INFERNO_WAVE,
    RIFT_CONFLAGRATION,
    RIFT_CONFLAGRATION,
]

RIFTCLASH_CRYOMANCER_DECK = [
    FROST_WISP,
    FROST_WISP,
    VOID_SPRITE,
    VOID_SPRITE,
    GLACIAL_SENTINEL,
    GLACIAL_SENTINEL,
    RIFT_WATCHER,
    RIFT_WATCHER,
    VOID_SEER,
    VOID_SEER,
    FROZEN_REVENANT,
    FROZEN_REVENANT,
    ABYSSAL_LURKER,
    ABYSSAL_LURKER,
    VOIDCRYSTAL_GOLEM,
    CRYO_SENTINEL,
    CRYO_SENTINEL,
    BLIZZARD_GOLEM,
    BLIZZARD_GOLEM,
    RIFT_GUARDIAN,
    VOIDFROST_DRAGON,
    ABSOLUTE_ARCHIVIST,
    GLACIELS_AVATAR,
    ICE_SHACKLE,
    ICE_SHACKLE,
    GLACIAL_INSIGHT,
    GLACIAL_INSIGHT,
    WHITEOUT_PROTOCOL,
    WHITEOUT_PROTOCOL,
    ABSOLUTE_ZERO,
]

RIFTCLASH_DECKS = {
    "Pyromancer": RIFTCLASH_PYROMANCER_DECK,
    "Cryomancer": RIFTCLASH_CRYOMANCER_DECK,
}

assert len(RIFTCLASH_PYROMANCER_DECK) == 30
assert len(RIFTCLASH_CRYOMANCER_DECK) == 30


# =============================================================================
# Global modifiers
# =============================================================================


def install_riftclash_modifiers(game) -> None:
    """
    Install deterministic global modifiers for Riftclash.

    1. Convergence: If the active player starts their turn behind on board,
       they summon a 1/1 Riftling.
    2. Spell Edge: The first spell each player casts each turn deals 1 to
       the enemy hero.
    3. Frozen Tribute: Whenever a frozen minion dies, its controller draws 1.
    """

    state = game.state
    player_ids = list(state.players.keys())
    if not player_ids:
        return

    spell_edge_state = {"seen_this_turn": set()}

    def _count_minions_by_player(s: GameState) -> dict[str, int]:
        counts = {pid: 0 for pid in s.players.keys()}
        battlefield = s.zones.get("battlefield")
        if not battlefield:
            return counts

        for oid in battlefield.objects:
            obj = s.objects.get(oid)
            if not obj:
                continue
            if CardType.MINION in obj.characteristics.types:
                counts[obj.controller] = counts.get(obj.controller, 0) + 1
        return counts

    # Convergence + per-turn reset for Spell Edge
    def _turn_start_filter(event: Event, _s: GameState) -> bool:
        return event.type == EventType.TURN_START

    def _turn_start_handler(event: Event, s: GameState) -> InterceptorResult:
        spell_edge_state["seen_this_turn"] = set()

        active_pid = event.payload.get("player")
        if not active_pid or active_pid not in s.players:
            return InterceptorResult(action=InterceptorAction.PASS)

        counts = _count_minions_by_player(s)
        active_count = counts.get(active_pid, 0)
        max_other = max((c for pid, c in counts.items() if pid != active_pid), default=0)

        if active_count < max_other:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[
                    Event(
                        type=EventType.CREATE_TOKEN,
                        payload={
                            "controller": active_pid,
                            "token": {
                                "name": "Riftling",
                                "power": 1,
                                "toughness": 1,
                                "types": {CardType.MINION},
                                "subtypes": {"Elemental", "Spirit"},
                            },
                        },
                        source="riftclash_convergence",
                    )
                ],
            )

        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(
        Interceptor(
            id=f"mod_riftclash_turnstart_{new_id()}",
            source="global_modifier",
            controller=player_ids[0],
            priority=InterceptorPriority.REACT,
            filter=_turn_start_filter,
            handler=_turn_start_handler,
            duration="permanent",
        )
    )

    # Spell Edge
    def _spell_edge_filter(event: Event, _s: GameState) -> bool:
        return event.type in (EventType.CAST, EventType.SPELL_CAST)

    def _spell_edge_handler(event: Event, s: GameState) -> InterceptorResult:
        caster_id = event.payload.get("caster")
        if not caster_id:
            source_obj = s.objects.get(event.source)
            caster_id = source_obj.controller if source_obj else None

        if not caster_id:
            return InterceptorResult(action=InterceptorAction.PASS)

        if caster_id in spell_edge_state["seen_this_turn"]:
            return InterceptorResult(action=InterceptorAction.PASS)

        spell_edge_state["seen_this_turn"].add(caster_id)

        enemy_hero_id = None
        for pid, player in s.players.items():
            if pid != caster_id and player.hero_id:
                enemy_hero_id = player.hero_id
                break

        if not enemy_hero_id:
            return InterceptorResult(action=InterceptorAction.PASS)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": enemy_hero_id, "amount": 1, "source": "riftclash_spell_edge"},
                    source="riftclash_spell_edge",
                )
            ],
        )

    game.register_interceptor(
        Interceptor(
            id=f"mod_riftclash_spell_edge_{new_id()}",
            source="global_modifier",
            controller=player_ids[0],
            priority=InterceptorPriority.REACT,
            filter=_spell_edge_filter,
            handler=_spell_edge_handler,
            duration="permanent",
        )
    )

    # Frozen Tribute
    def _frozen_tribute_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        oid = event.payload.get("object_id")
        obj = s.objects.get(oid)
        if not obj:
            return False
        if CardType.MINION not in obj.characteristics.types:
            return False
        return bool(obj.state.frozen)

    def _frozen_tribute_handler(event: Event, s: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        obj = s.objects.get(oid)
        if not obj:
            return InterceptorResult(action=InterceptorAction.PASS)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": 1},
                    source="riftclash_frozen_tribute",
                )
            ],
        )

    game.register_interceptor(
        Interceptor(
            id=f"mod_riftclash_frozen_tribute_{new_id()}",
            source="global_modifier",
            controller=player_ids[0],
            priority=InterceptorPriority.REACT,
            filter=_frozen_tribute_filter,
            handler=_frozen_tribute_handler,
            duration="permanent",
        )
    )


__all__ = [
    "RIFTCLASH_HEROES",
    "RIFTCLASH_HERO_POWERS",
    "RIFTCLASH_DECKS",
    "install_riftclash_modifiers",
]
