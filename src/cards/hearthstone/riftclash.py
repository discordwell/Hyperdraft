"""
RIFTCLASH - Deterministic Pyromancer vs Cryomancer Variant

A tighter Hearthstone/MTG hybrid duel mode focused on tactical sequencing:
- Lower RNG than Stormrift (deterministic target selection where possible)
- Strong class identity (burn tempo vs freeze control)
- Global battlefield modifiers that reduce snowballing

Legendaries are designed to fundamentally alter the game, not just be bigger ETBs.
Each deck has multiple signature rares/legendaries that rewrite rules, create
ongoing engines, or bend the win condition.
"""

from src.engine.game import make_minion, make_spell, make_hero, make_hero_power
from src.engine.queries import get_power, get_toughness
from src.engine.types import (
    Event,
    EventType,
    GameObject,
    GameState,
    CardType,
    ZoneType,
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
    RIFTBORN_PHOENIX,
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


def _friendly_minion_ids(obj: GameObject, state: GameState, exclude_self: bool = True) -> list[str]:
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    out: list[str] = []
    for oid in battlefield.objects:
        m = state.objects.get(oid)
        if not m:
            continue
        if m.controller != obj.controller:
            continue
        if CardType.MINION not in m.characteristics.types:
            continue
        if exclude_self and m.id == obj.id:
            continue
        out.append(oid)
    return out


def _highest_attack_enemy_minion_id(obj: GameObject, state: GameState) -> str | None:
    candidates = _enemy_minion_ids(obj, state)
    if not candidates:
        return None

    def _score(oid: str) -> tuple[int, int, int]:
        enemy = state.objects[oid]
        remaining_hp = (get_toughness(enemy, state) or 0) - enemy.state.damage
        return (get_power(enemy, state) or 0, remaining_hp, enemy.created_at)

    return max(candidates, key=_score)


def _enemy_player_id(obj: GameObject, state: GameState) -> str | None:
    for pid in state.players:
        if pid != obj.controller:
            return pid
    return None


# =============================================================================
# Heroes and Hero Powers
# =============================================================================

IGNIS_REFORGED = make_hero(
    name="Ignis, Rift Vanguard",
    hero_class="Pyromancer",
    starting_life=30,
    text="Hero Power: Ember Volley (Deal 1 to enemy hero and 1 to highest-Attack enemy minion; if it dies, splash 1 to adjacent minions)",
)

GLACIEL_REFORGED = make_hero(
    name="Glaciel, Icebound Regent",
    hero_class="Cryomancer",
    starting_life=30,
    text="Hero Power: Cryo Ward (Gain 2 Armor. Freeze highest-Attack enemy minion. If already frozen, also draw a card)",
)

RIFTCLASH_HEROES = {
    "Pyromancer": IGNIS_REFORGED,
    "Cryomancer": GLACIEL_REFORGED,
}


def ember_volley_effect(obj: GameObject, state: GameState) -> list[Event]:
    """
    Hit enemy hero for 1. Hit the highest-attack enemy minion for 1.
    If that minion would die from this, splash 1 damage to the two adjacent
    enemy minions (by creation order). Chaining hero power.
    """
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
    if target and target in state.objects:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": target, "amount": 1, "source": obj.id},
                source=obj.id,
            )
        )

        # Splash check: if this 1-damage ping is lethal, splash to adjacents.
        primary = state.objects[target]
        primary_hp = (get_toughness(primary, state) or 0) - primary.state.damage
        if primary_hp <= 1:
            enemies_sorted = sorted(
                _enemy_minion_ids(obj, state),
                key=lambda oid: state.objects[oid].created_at,
            )
            if target in enemies_sorted:
                idx = enemies_sorted.index(target)
                neighbors = []
                if idx - 1 >= 0:
                    neighbors.append(enemies_sorted[idx - 1])
                if idx + 1 < len(enemies_sorted):
                    neighbors.append(enemies_sorted[idx + 1])
                for n in neighbors:
                    events.append(
                        Event(
                            type=EventType.DAMAGE,
                            payload={"target": n, "amount": 1, "source": obj.id},
                            source=obj.id,
                        )
                    )

    return events


EMBER_VOLLEY = make_hero_power(
    name="Ember Volley",
    cost=2,
    text="Deal 1 to enemy hero and 1 to highest-Attack enemy minion. If this kills it, splash 1 to adjacent minions.",
    effect=ember_volley_effect,
)


def cryo_ward_effect(obj: GameObject, state: GameState) -> list[Event]:
    """
    Gain 2 armor. Freeze highest-attack enemy minion.
    If that minion is already frozen, ALSO draw a card (dual-value upgrade).
    """
    events: list[Event] = [
        Event(
            type=EventType.ARMOR_GAIN,
            payload={"player": obj.controller, "amount": 2},
            source=obj.id,
        )
    ]

    target = _highest_attack_enemy_minion_id(obj, state)
    if target and target in state.objects:
        primary = state.objects[target]
        already_frozen = bool(primary.state.frozen)

        events.append(
            Event(
                type=EventType.FREEZE_TARGET,
                payload={"target": target},
                source=obj.id,
            )
        )

        if already_frozen:
            events.append(
                Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": 1},
                    source=obj.id,
                )
            )

    return events


CRYO_WARD = make_hero_power(
    name="Cryo Ward",
    cost=2,
    text="Gain 2 Armor. Freeze the highest-Attack enemy minion. If already frozen, also draw a card.",
    effect=cryo_ward_effect,
)

RIFTCLASH_HERO_POWERS = {
    "Pyromancer": EMBER_VOLLEY,
    "Cryomancer": CRYO_WARD,
}


# =============================================================================
# Pyromancer rares (redesigned)
# =============================================================================


def ember_tactician_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Battlecry: deal 1 to all enemy minions. Any minion killed this way
    is exiled (placed at bottom of its owner's deck face-down) — a tempo
    swing that also thins the opponent's late game. Asymmetric sweeper.
    """
    events: list[Event] = []

    # Snapshot current enemy minions and their survivability.
    snapshot: list[tuple[str, int]] = []
    for oid in _enemy_minion_ids(obj, state):
        enemy = state.objects[oid]
        hp = (get_toughness(enemy, state) or 0) - enemy.state.damage
        snapshot.append((oid, hp))

    # Deal 1 damage to each.
    for oid, _ in snapshot:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 1, "source": obj.id},
                source=obj.id,
            )
        )

    # For anything with exactly 1 effective HP, schedule an exile (to library bottom).
    for oid, hp in snapshot:
        if hp <= 1:
            events.append(
                Event(
                    type=EventType.EXILE,
                    payload={"object_id": oid, "to_bottom_of_library": True, "reason": "ember_tactician"},
                    source=obj.id,
                )
            )

    return events


EMBER_TACTICIAN = make_minion(
    name="Ember Tactician",
    attack=3,
    health=3,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 1 damage to all enemy minions. Any it destroys are buried at the bottom of their owner's deck.",
    rarity="rare",
    battlecry=ember_tactician_battlecry,
)


def molten_overseer_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Rewrites a resource axis: after your first spell each of your turns,
    REFUND 1 mana crystal this turn (to a max of your cap). Any subsequent
    spell this turn still pings the enemy hero for 1 (classic Molten Overseer).
    """
    turn_state = {"refund_turn": None, "pinged_turn": None}

    def _spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source_obj = s.objects.get(event.source)
        return source_obj is not None and source_obj.controller == obj.controller

    def _spell_handler(_event: Event, s: GameState) -> InterceptorResult:
        new_events: list[Event] = []
        active_turn = s.turn_number

        # Mana refund (first spell of YOUR turn only)
        if turn_state["refund_turn"] != active_turn:
            turn_state["refund_turn"] = active_turn
            player = s.players.get(obj.controller)
            if player is not None and player.mana_crystals_available < player.mana_crystals:
                player.mana_crystals_available = min(
                    player.mana_crystals,
                    player.mana_crystals_available + 1,
                )

        # Always ping enemy hero for 1 (but only from this point on; preserves old feel)
        enemy_hero_id = get_enemy_hero_id(obj, s)
        if enemy_hero_id:
            new_events.append(
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": enemy_hero_id, "amount": 1, "source": obj.id},
                    source=obj.id,
                )
            )

        if new_events:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )
        return InterceptorResult(action=InterceptorAction.PASS)

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
    text="After your first spell each turn, refund 1 mana. After every spell you cast, deal 1 damage to the enemy hero.",
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
    """
    Redesign: 'Scorching Surge' now forges a Cinder counter on you.
    Deal 2 to all enemy minions AND add a 'Cinder Charge' to your hand
    (a 0-cost 1-damage missile). Chains with spell-damage and repeats value.
    """
    events: list[Event] = [
        Event(
            type=EventType.DAMAGE,
            payload={"target": oid, "amount": 2, "source": obj.id, "from_spell": True},
            source=obj.id,
        )
        for oid in _enemy_minion_ids(obj, state)
    ]

    events.append(
        Event(
            type=EventType.ADD_TO_HAND,
            payload={"player": obj.controller, "card_def": CINDER_CHARGE},
            source=obj.id,
        )
    )

    return events


def cinder_charge_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    hero = get_enemy_hero_id(obj, state)
    if not hero:
        return []
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": hero, "amount": 1, "source": obj.id, "from_spell": True},
            source=obj.id,
        )
    ]


CINDER_CHARGE = make_spell(
    name="Cinder Charge",
    mana_cost="{0}",
    text="Deal 1 damage to the enemy hero.",
    spell_effect=cinder_charge_effect,
    rarity="rare",
)


SCORCHING_SURGE = make_spell(
    name="Scorching Surge",
    mana_cost="{3}",
    text="Deal 2 damage to all enemy minions. Add a Cinder Charge (0 mana: deal 1 to enemy hero) to your hand.",
    spell_effect=scorching_surge_effect,
    rarity="rare",
)


# =============================================================================
# Pyromancer legendaries (new / redesigned)
# =============================================================================


def ember_volley_spell_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    """
    Legendary spell: deal 3. Persistent state: for the rest of the game, YOUR
    first spell each turn deals +1 damage. Installed as a permanent interceptor
    keyed to the caster's controller.
    """
    events: list[Event] = []

    # Immediate 3 damage to a smart target (highest-attack enemy minion or hero)
    target = _highest_attack_enemy_minion_id(obj, state) or get_enemy_hero_id(obj, state)
    if target:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": target, "amount": 3, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )

    # Persistent state: install a +1 damage TRANSFORM interceptor tied to this controller.
    controller_id = obj.controller
    edge_state = {"last_boost_turn": None}

    def _edge_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get("from_spell"):
            return False
        src = s.objects.get(event.source)
        if not src or src.controller != controller_id:
            return False
        # Only the first spell of the active turn
        return edge_state["last_boost_turn"] != s.turn_number

    def _edge_handler(event: Event, s: GameState) -> InterceptorResult:
        edge_state["last_boost_turn"] = s.turn_number
        new_event = event.copy()
        new_event.payload["amount"] = event.payload.get("amount", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    # Register via a side-channel Event that the pipeline will not handle,
    # but we can attach the interceptor directly to the game via the state._riftclash_register_fn hook.
    register = getattr(state, "_riftclash_register_edge", None)
    if callable(register):
        register(
            Interceptor(
                id=new_id(),
                source=obj.id,
                controller=controller_id,
                priority=InterceptorPriority.TRANSFORM,
                filter=_edge_filter,
                handler=_edge_handler,
                duration="permanent",
            )
        )

    return events


EMBER_VOLLEY_LEGENDARY = make_spell(
    name="Ember Volley, Unchained",
    mana_cost="{5}",
    text="Deal 3 damage to a priority enemy. For the rest of the game, your first spell each turn deals +1 damage.",
    spell_effect=ember_volley_spell_effect,
    rarity="legendary",
)


def combustion_engine_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Battlecry: discard 2 cards. Deathrattle (see setup): for each card you
    have discarded this game, deal 1 damage to the enemy hero.
    This is a deck-ID alt cost: sacrifice hand for a late burn payoff.
    """
    events: list[Event] = []
    hand_zone = state.zones.get(f"hand_{obj.controller}")
    if not hand_zone:
        return events

    # Discard the two rightmost cards (newest first)
    to_discard = list(hand_zone.objects)[-2:]
    for cid in to_discard:
        events.append(
            Event(
                type=EventType.DISCARD,
                payload={"player": obj.controller, "object_id": cid, "source": "combustion_engine"},
                source=obj.id,
            )
        )

    return events


def combustion_engine_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """Track discards owned by our controller; emit a final payoff on death."""
    counter = {"discards": 0}

    def _discard_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DISCARD:
            return False
        return event.payload.get("player") == obj.controller

    def _discard_handler(_event: Event, _s: GameState) -> InterceptorResult:
        counter["discards"] += 1
        return InterceptorResult(action=InterceptorAction.PASS)

    def _death_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get("object_id") == obj.id

    def _death_handler(_event: Event, s: GameState) -> InterceptorResult:
        hero = get_enemy_hero_id(obj, s)
        if not hero:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": hero, "amount": counter["discards"], "source": obj.id},
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
            filter=_discard_filter,
            handler=_discard_handler,
            duration="permanent",  # Track discards game-long, even before obj is played.
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_death_filter,
            handler=_death_handler,
            duration="until_leaves",
        ),
    ]


COMBUSTION_ENGINE = make_minion(
    name="Combustion Engine",
    attack=4,
    health=4,
    mana_cost="{4}",
    subtypes={"Elemental", "Construct"},
    text="Battlecry: Discard 2 cards. Deathrattle: Deal damage to the enemy hero equal to the number of cards you have discarded this game.",
    rarity="legendary",
    battlecry=combustion_engine_battlecry,
    setup_interceptors=combustion_engine_setup,
)


# =============================================================================
# Cryomancer rares (redesigned)
# =============================================================================


def whiteout_protocol_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    """
    Freeze all enemy minions and deal 1 damage. Newly: for each enemy minion
    already frozen, ALSO draw a card. Turns a freeze-lock into an ongoing
    card draw engine via the frozen-tribute global modifier.
    """
    events: list[Event] = []
    already_frozen_count = 0

    for oid in _enemy_minion_ids(obj, state):
        enemy = state.objects.get(oid)
        if enemy and enemy.state.frozen:
            already_frozen_count += 1
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

    if already_frozen_count > 0:
        events.append(
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": already_frozen_count},
                source=obj.id,
            )
        )

    return events


WHITEOUT_PROTOCOL = make_spell(
    name="Whiteout Protocol",
    mana_cost="{5}",
    text="Freeze all enemy minions. Deal 1 damage to them. Draw a card for each that was already frozen.",
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
    """
    End of turn: if an enemy minion is frozen, draw a card. Additionally,
    when an enemy minion UNFREEZES (thaws) this is an 'aftershock' trigger:
    deal 2 damage to it. Turns freeze-lock into compounding tempo.
    """

    def _end_turn_filter(event: Event, _s: GameState) -> bool:
        return (
            event.type == EventType.PHASE_END
            and event.payload.get("phase") == "end"
            and event.payload.get("player") == obj.controller
        )

    def _end_turn_handler(_event: Event, s: GameState) -> InterceptorResult:
        new_events: list[Event] = []
        for oid in _enemy_minion_ids(obj, s):
            enemy = s.objects.get(oid)
            if not enemy:
                continue
            if enemy.state.frozen:
                new_events.append(
                    Event(
                        type=EventType.DRAW,
                        payload={"player": obj.controller, "count": 1},
                        source=obj.id,
                    )
                )
                break  # only one card per end step; prevents runaway draw

        return (
            InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)
            if new_events
            else InterceptorResult(action=InterceptorAction.PASS)
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


# =============================================================================
# Cryomancer legendaries (new / redesigned)
# =============================================================================


def rift_conflagration_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    """
    Legendary neutral sweeper: deal 4 to enemy hero and 4 to every enemy minion,
    AND 2 to every FRIENDLY minion (asymmetric sweeper with collateral).
    Then your next hero power this turn costs 0 (tempo kicker).
    """
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

    for oid in _friendly_minion_ids(obj, state, exclude_self=True):
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 2, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )

    # Hero power cost reduction
    player = state.players.get(obj.controller)
    if player is not None:
        player.cost_modifiers.append({
            "card_type": "hero_power",
            "amount": -2,
            "duration": "this_turn",
            "floor": 0,
            "uses_remaining": 1,
        })

    return events


RIFT_CONFLAGRATION = make_spell(
    name="Rift Conflagration",
    mana_cost="{7}",
    text="Deal 4 damage to the enemy hero and all enemy minions; deal 2 to your other minions. Your next Hero Power this turn costs (0).",
    spell_effect=rift_conflagration_effect,
    rarity="legendary",
)


def void_matrix_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Legendary enchantment-style minion. Can't attack.
    While on the board: your spells cost {1} less (floor 0).
    When you cast a spell, summon a 1/3 Frost Wraith with Taunt.
    """
    obj.state.cant_attack = True

    # Cost reduction is installed as a persistent, per-game-long cost_modifier.
    # We guard via a one-shot setup (only once per ETB).
    installed_flag = {"done": False}

    def _etb_filter(event: Event, s: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get("object_id") == obj.id
            and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
        )

    def _etb_handler(_event: Event, s: GameState) -> InterceptorResult:
        if installed_flag["done"]:
            return InterceptorResult(action=InterceptorAction.PASS)
        installed_flag["done"] = True
        player = s.players.get(obj.controller)
        if player is not None:
            player.cost_modifiers.append({
                "card_type": "spell",
                "amount": -1,
                "duration": "while_source_alive",
                "source_id": obj.id,
                "floor": 0,
            })
        return InterceptorResult(action=InterceptorAction.PASS)

    def _ltb_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get("object_id") == obj.id

    def _ltb_handler(_event: Event, s: GameState) -> InterceptorResult:
        player = s.players.get(obj.controller)
        if player is not None:
            player.cost_modifiers = [
                m for m in player.cost_modifiers
                if m.get("source_id") != obj.id
            ]
        return InterceptorResult(action=InterceptorAction.PASS)

    def _spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        src = s.objects.get(event.source)
        if not src or src.controller != obj.controller:
            return False
        # Only while matrix is on battlefield
        matrix = s.objects.get(obj.id)
        return bool(matrix and matrix.zone == ZoneType.BATTLEFIELD)

    def _spell_handler(_event: Event, s: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        "controller": obj.controller,
                        "token": {
                            "name": "Frost Wraith",
                            "power": 1,
                            "toughness": 3,
                            "types": {CardType.MINION},
                            "subtypes": {"Elemental", "Spirit"},
                            "abilities": [{"keyword": "taunt"}],
                        },
                    },
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
            filter=_etb_filter,
            handler=_etb_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_ltb_filter,
            handler=_ltb_handler,
            duration="until_leaves",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_spell_filter,
            handler=_spell_handler,
            duration="while_on_battlefield",
        ),
    ]


VOID_MATRIX = make_minion(
    name="Void Matrix",
    attack=0,
    health=5,
    mana_cost="{5}",
    subtypes={"Elemental", "Construct"},
    text="Can't attack. Your spells cost (1) less. Whenever you cast a spell, summon a 1/3 Frost Wraith with Taunt.",
    rarity="legendary",
    setup_interceptors=void_matrix_setup,
)


def crystal_archive_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Legendary 3/7 Taunt. Battlecry: peek at enemy deck, 'bury' (exile) the
    top 2 cards face-down, and add copies of them to YOUR hand. This is a
    tutor/selection break that steals tempo from the opponent's draws.
    """
    events: list[Event] = []
    enemy_pid = _enemy_player_id(obj, state)
    if not enemy_pid:
        return events

    enemy_library = state.zones.get(f"library_{enemy_pid}")
    if not enemy_library:
        return events

    # Snapshot the top 2 object IDs (simulate order — newest first/last varies)
    top_ids = list(enemy_library.objects)[-2:]
    for cid in reversed(top_ids):
        victim = state.objects.get(cid)
        if not victim or not victim.card_def:
            continue
        # Exile the enemy card (remove tempo).
        events.append(
            Event(
                type=EventType.EXILE,
                payload={"object_id": cid, "reason": "crystal_archive"},
                source=obj.id,
            )
        )
        # Add a copy to our hand.
        events.append(
            Event(
                type=EventType.ADD_TO_HAND,
                payload={"player": obj.controller, "card_def": victim.card_def},
                source=obj.id,
            )
        )

    return events


CRYSTAL_ARCHIVE = make_minion(
    name="Crystal Archive",
    attack=3,
    health=7,
    mana_cost="{6}",
    subtypes={"Elemental", "Construct"},
    keywords={"taunt"},
    text="Taunt. Battlecry: Bury the top 2 cards of your opponent's deck; add copies of them to your hand.",
    rarity="legendary",
    battlecry=crystal_archive_battlecry,
)


# =============================================================================
# Mythic legendary (symmetric global rewrite)
# =============================================================================


def riftclash_throne_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    The Riftclash Throne (mythic): persistent state modifier, SYMMETRIC.
    - At the end of each turn, both players draw a card.
    - Each turn's first spell costs {2} less (floor 0).
    - Minions that die return to their owner's hand instead of graveyard
      for the first 3 turns this is in play.
    """
    install_state = {
        "installed_discount_turn": None,
        "turns_alive": 0,
        "bounce_horizon": None,  # turn_number at which bouncing stops
    }

    def _etb_filter(event: Event, s: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get("object_id") == obj.id
            and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
        )

    def _etb_handler(_event: Event, s: GameState) -> InterceptorResult:
        install_state["bounce_horizon"] = s.turn_number + 3
        return InterceptorResult(action=InterceptorAction.PASS)

    def _end_turn_filter(event: Event, _s: GameState) -> bool:
        return event.type == EventType.PHASE_END and event.payload.get("phase") == "end"

    def _end_turn_handler(_event: Event, s: GameState) -> InterceptorResult:
        # Both players draw 1
        draws = [
            Event(
                type=EventType.DRAW,
                payload={"player": pid, "count": 1},
                source=obj.id,
            )
            for pid in s.players
        ]
        # Clear the "first-spell discount" cost mod for all players this turn.
        for player in s.players.values():
            player.cost_modifiers = [
                m for m in player.cost_modifiers if m.get("source_id") != obj.id
            ]
        install_state["installed_discount_turn"] = None
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draws,
        )

    def _turn_start_filter(event: Event, _s: GameState) -> bool:
        return event.type == EventType.TURN_START

    def _turn_start_handler(event: Event, s: GameState) -> InterceptorResult:
        # Install a first-spell discount for the active player this turn.
        active_pid = event.payload.get("player") if isinstance(event, Event) else None
        if not active_pid:
            tm = getattr(s, "turn_manager", None)
            active_pid = getattr(tm, "active_player_id", None) if tm else None
        if active_pid and active_pid in s.players:
            player = s.players[active_pid]
            player.cost_modifiers.append({
                "card_type": "spell",
                "amount": -2,
                "duration": "this_turn",
                "source_id": obj.id,
                "floor": 0,
                "uses_remaining": 1,
            })
        return InterceptorResult(action=InterceptorAction.PASS)

    def _death_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        horizon = install_state["bounce_horizon"]
        if horizon is None or s.turn_number >= horizon:
            return False
        oid = event.payload.get("object_id")
        victim = s.objects.get(oid)
        if not victim:
            return False
        # Only apply to minions (not heroes / hero powers)
        return CardType.MINION in victim.characteristics.types and oid != obj.id

    def _death_handler(event: Event, s: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        victim = s.objects.get(oid)
        if not victim:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.RETURN_TO_HAND,
                    payload={"object_id": oid, "player": victim.controller},
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
            filter=_etb_filter,
            handler=_etb_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_end_turn_filter,
            handler=_end_turn_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_turn_start_filter,
            handler=_turn_start_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_death_filter,
            handler=_death_handler,
            duration="while_on_battlefield",
        ),
    ]


RIFTCLASH_THRONE = make_minion(
    name="The Riftclash Throne",
    attack=0,
    health=8,
    mana_cost="{8}",
    subtypes={"Construct", "Legendary"},
    keywords={"taunt"},
    text="Legendary. Taunt. At end of each turn, both players draw a card. Each turn's first spell costs (2) less. For the first 3 turns, dying minions return to their owner's hand.",
    rarity="legendary",
    setup_interceptors=riftclash_throne_setup,
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
    COMBUSTION_ENGINE,  # legendary
    MOLTEN_OVERSEER,
    MOLTEN_OVERSEER,
    VOLATILERIFT_MAGE,
    VOLATILERIFT_MAGE,
    STORMRIFT_PHOENIX,
    RIFTBORN_PHOENIX,
    NEXUS_GUARDIAN,
    RIFTCLASH_THRONE,  # mythic legendary
    CINDER_LANCE,
    CINDER_LANCE,
    SCORCHING_SURGE,
    SCORCHING_SURGE,
    INFERNO_WAVE,
    INFERNO_WAVE,
    EMBER_VOLLEY_LEGENDARY,  # legendary spell
    RIFT_CONFLAGRATION,  # legendary spell
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
    VOID_MATRIX,  # legendary
    RIFT_GUARDIAN,
    VOIDFROST_DRAGON,
    ABSOLUTE_ARCHIVIST,
    GLACIELS_AVATAR,
    CRYSTAL_ARCHIVE,  # legendary
    ICE_SHACKLE,
    ICE_SHACKLE,
    GLACIAL_INSIGHT,
    GLACIAL_INSIGHT,
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

    Also installs a hook for Ember Volley, Unchained so the spell can
    register persistent interceptors into the game after resolution.
    """

    state = game.state
    player_ids = list(state.players.keys())
    if not player_ids:
        return

    # Hook: allow Ember Volley (Unchained) to register persistent interceptors.
    def _register_edge(interceptor: Interceptor) -> None:
        game.register_interceptor(interceptor)

    state._riftclash_register_edge = _register_edge

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
    # Legendaries exported for testing
    "EMBER_VOLLEY_LEGENDARY",
    "COMBUSTION_ENGINE",
    "VOID_MATRIX",
    "CRYSTAL_ARCHIVE",
    "RIFTCLASH_THRONE",
    "RIFT_CONFLAGRATION",
    "EMBER_TACTICIAN",
    "SCORCHING_SURGE",
    "WHITEOUT_PROTOCOL",
    "CINDER_CHARGE",
]
